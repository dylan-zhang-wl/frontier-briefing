#!/usr/bin/env python3
"""验收（第 16 步）："听这一段"跳到的地方，讲的是不是这一条（11-15 加）。

起因：11-15 周日对谈，网页快讯 E006（DeepSeek）的"听这一段"跳到 94.1 秒，那里还在讲上一条 ChatGPT Wallet 的尾巴，
"国内这边"要到约 110.1 秒才开口，跳早了约 16 秒。check_listen.js 只点前两个按钮、看播客有没有从某个时间开始放，
查不出这种"放了、但放的不是这一条"。

做法：每个"听这一段"从跳点往后截一段播客成品（默认 20 秒），用配音对稿同一个转写模型（pipeline/tts_qc.py 的
transcribe_many：本机 mlx-whisper，云端 cloud/whisper_standin）转写，逐小段和这一条、别的条目的网页文字比
（字对字相同几处，数字统一写法）。一小段和别的条目明显比和这一条像（多 2 处以上），算"在讲别的条目"；跳点之后、这一条开口之前，
"在讲别的条目"的说话合计 5 秒以上（整个窗口都没听到这一条时 3 秒以上），判"跳早了"，写明在讲哪一条、这一条约在第几秒才开口。
段首拿上一条起头的过渡句（11-09 E060"为什么要自己去抢设备？我们可以把它和……放在一起看"，约 4 秒）不判。
片头、桥段音乐、"再快看几条"这类和哪条都不沾的话不算；转写模型在音乐里编出来的字一般也不沾，不算。
只查"跳早"，不查"跳晚"（跳点前面那几句常常是这一条的引子，分不清）。只提醒、不挡发布。

用法（在仓库根目录）：
    ~/.venvs/frontier-daily/bin/python site/tools/check_listen_text.py <期目录> [--out 结果.json] [--window 20]
期目录里要有 10_网页v3/issues/<日期>/issue.js 和 audio/podcast.mp3（第 13、15 步组装的网页）。
输出：每条一行；--out 写 JSON（fd 第 16 步写 logs/听这一段_转写核对.json）。没有播客退出码 0、打印"跳过"；
转写没跑成退出码 3。截出来的音频放在 ~/.cache/frontier-daily/ 下的临时目录，用完就清；不调任何模型接口，不花钱。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

WINDOW = 20.0        # 从跳点往后转写几秒
EARLY_SEC = 5.0      # 这一条开口之前，"在讲别的条目"的说话合计超过这么多秒，判跳早了
EARLY_SEC_NONE = 3.0 # 整个窗口里都没听到这一条时，门槛放低到这么多秒（11-15 E006、11-12 热点二三对调都是这样）
MIN_HIT = 3          # 一小段和这一条至少有这么多处字对字相同、又比别的条目多，算这一条开口了
OTHER_HIT, OTHER_GAP = 4, 2   # 和别的条目至少 4 处、还比这一条多 2 处以上，才算"在讲别的条目"（11-11 E007 段首
                              # "谷歌 DeepMind 这周还发了一项研究，用的也是智能体"回头提上一条，只多 1 处，不算）
FIELDS = ("title_zh", "summary_zh", "tab_zh", "lead_zh", "why_zh", "read_zh", "question_zh", "conclusion_zh")
INVISIBLE = re.compile(r"[​⁠­﻿]")     # 网页按词组换行插进去的看不见的字符
CITE = re.compile(r"\[\^[^\]]*\]")


def load_issue(issue_dir):
    """期目录 → (日期, issue.js 里的数据, podcast.mp3 路径)。找不到返回 (日期, None, None)。"""
    day = os.path.basename(os.path.normpath(issue_dir))
    js = os.path.join(issue_dir, "10_网页v3", "issues", day, "issue.js")
    if not os.path.exists(js):
        return day, None, None
    s = open(js, encoding="utf-8").read()
    key = 'window.FD_ISSUES["%s"] = ' % day
    i = s.find(key)
    if i < 0:
        return day, None, None
    data, _ = json.JSONDecoder().raw_decode(s[i + len(key):])
    mp3 = os.path.join(issue_dir, "10_网页v3", "issues", day, "audio", "podcast.mp3")
    return day, data, (mp3 if os.path.exists(mp3) else None)


def story_text(st):
    out = []
    for k in FIELDS:
        v = st.get(k)
        for x in (v if isinstance(v, list) else [v]):
            if isinstance(x, str):
                out.append(CITE.sub("", INVISIBLE.sub("", x)))
    return "".join(out)


def make_grams():
    """字对字比较：和配音对稿同一种写法（tts_qc.tokens：数字统一成阿拉伯数字、繁转简、英文一个词算一个），两两相邻算一处。"""
    try:
        import tts_qc as Q
        tok = Q.tokens
    except Exception:  # noqa: BLE001
        def tok(s):
            return re.findall(r"[a-z]+|\d|[㐀-鿿]", (s or "").lower())

    def grams(s):
        t = tok(s or "")
        return {g for g in zip(t, t[1:]) if not (LIGHT & set(g)) and not any(x.isdigit() for x in g)}
    return grams


# 不算数的字：虚字和日期字。带数字的两两一处也不算——日期（“11 月 13 日”）哪条都有，11-15 E008 的
# “英国《卫报》11 月 13 日的一篇报道”因此被算成在讲 D1
LIGHT = set("的了是在和与也就都还又而及或把被对给从向这那其之个们年月日号%.")


def judge(sid, segs, texts, grams):
    """一条的转写小段 [(起, 止, 字)]（从跳点起算）→ 判断。texts：{条目: 文字}。"""
    mine = grams(texts[sid])
    others = {k: grams(v) for k, v in texts.items() if k != sid}
    first_own, early, who = None, 0.0, {}
    for a, b, tx in segs:
        g = grams(tx)
        own = len(g & mine)
        best, bk = max(((len(g & v), k) for k, v in others.items()), default=(0, None))
        if own >= MIN_HIT and own > best:
            first_own = a
            break
        if best >= OTHER_HIT and best >= own + OTHER_GAP:
            early += max(0.0, b - a)
            who[bk] = who.get(bk, 0.0) + max(0.0, b - a)
    head = "".join(tx for _, _, tx in segs)[:40]
    rec = {"这一条开口（跳点后几秒）": None if first_own is None else round(first_own, 1),
           "之前在讲别的条目（秒）": round(early, 1), "转写开头": head}
    if early >= (EARLY_SEC if first_own is not None else EARLY_SEC_NONE):
        rec["判断"] = "跳早了"
        rec["在讲"] = max(who, key=who.get)
    elif first_own is not None:
        rec["判断"] = "对上"
    else:
        rec["判断"] = "没判出"
    return rec


def transcribe(clips):
    """clips：{条目: wav 路径} → {条目: [(起, 止, 字)]}，一次进程转完（tts_qc.transcribe_many）。"""
    import tts_qc as Q
    work = {k: os.path.join(os.path.dirname(w), "whisper_" + k) for k, w in clips.items()}
    Q.transcribe_many([(w, work[k]) for k, w in clips.items()])
    out = {}
    for k, w in clips.items():
        f = os.path.join(work[k], os.path.splitext(os.path.basename(w))[0] + "_whisper.json")
        d = json.load(open(f, encoding="utf-8"))
        out[k] = [(float(s.get("start") or 0), float(s.get("end") or 0), (s.get("text") or "").strip())
                  for s in d.get("segments") or []]
    return out


def main():
    ap = argparse.ArgumentParser(description="'听这一段'跳到的地方讲的是不是这一条（转写核对）")
    ap.add_argument("issue_dir")
    ap.add_argument("--out", help="结果写成 JSON")
    ap.add_argument("--window", type=float, default=WINDOW, help="从跳点往后转写几秒（默认 %g）" % WINDOW)
    a = ap.parse_args()
    day, data, mp3 = load_issue(a.issue_dir)
    if data is None:
        print("找不到 %s 的网页数据（10_网页v3/issues/%s/issue.js）" % (day, day))
        sys.exit(2)
    stories = data.get("stories") or {}
    jumps = {k: float(v["listen"]) for k, v in stories.items() if isinstance(v.get("listen"), (int, float))}
    res = {"期": day, "窗口秒": a.window, "判跳早的门槛秒": [EARLY_SEC, EARLY_SEC_NONE], "各条": {}}
    if not mp3 or not jumps:
        print("跳过：这一期没有播客或没有'听这一段'")
        res["跳过"] = "没有播客或没有'听这一段'"
        if a.out:
            json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return
    texts = {k: story_text(v) for k, v in stories.items()}
    base = os.path.expanduser("~/.cache/frontier-daily")
    os.makedirs(base, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="check_listen_text_", dir=base)
    try:
        clips = {}
        for k, t in jumps.items():
            w = os.path.join(tmp, "%s.wav" % re.sub(r"[^A-Za-z0-9_-]", "_", k))
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", "%.2f" % t, "-t", "%.2f" % a.window,
                            "-i", mp3, "-ac", "1", "-ar", "16000", w], check=True)
            clips[k] = w
        try:
            segs = transcribe(clips)
        except Exception as e:  # noqa: BLE001
            print("转写没跑成：%s: %s" % (type(e).__name__, str(e)[-300:]))
            res["没跑成"] = "%s: %s" % (type(e).__name__, str(e)[-300:])
            if a.out:
                json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            sys.exit(3)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    grams = make_grams()
    n_bad = 0
    for k, t in jumps.items():
        r = judge(k, segs[k], texts, grams)
        r["跳点秒"] = t
        res["各条"][k] = r
        if r["判断"] == "跳早了":
            n_bad += 1
            on = r["这一条开口（跳点后几秒）"]
            print("跳早了  %s：跳到 %.1f 秒，之后约 %.0f 秒讲的像 %s（转写“%s……”）；%s"
                  % (k, t, r["之前在讲别的条目（秒）"], r["在讲"], r["转写开头"][:16],
                     "这一条约在 %.1f 秒才开口" % (t + on) if on is not None else "%g 秒内没听到这一条" % a.window))
        else:
            print("%s  %s：跳到 %.1f 秒%s" % (r["判断"], k, t,
                                          "，%.1f 秒后开口" % r["这一条开口（跳点后几秒）"] if r["判断"] == "对上" else ""))
    res["跳早了"] = n_bad
    print("'听这一段'转写核对：%d 条，跳早了 %d 条" % (len(jumps), n_bad))
    if a.out:
        json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
