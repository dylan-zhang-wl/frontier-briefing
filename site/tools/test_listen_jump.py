#!/usr/bin/env python3
"""“听这一段”跳转测试（11-05 新建）：网页里某条放在一栏、播客却在别的章里讲它时，应跳到播客里主讲它的那一段。

起因：11-04 网页把墨芯（E010）放在“要闻”，播客却在“热点三”里讲（6:11 左右），“要闻”一章根本没提；
build_v3.py 的 listen_at 只在“要闻”里按文字找，找不到就退回“要闻”开头 7:37。

两部分：
    一、真实数据：用 11-04 这一期组装一次（期目录用软链接只读接过来，输出放项目外），
       E010 要落在热点三“国内这边，同一天也有几笔芯片融资见报”那一段（约 370 秒），
       其余 12 条和修之前完全一样；组装时不再报“听这一段”可能跳错。
    二、构造的几种情况（借第一部分组装后的函数，换掉分段和章节）：
       1. 网页在要闻、播客在热点三讲、开场也预告过 → 跳热点三那一段，不跳开场
       2. 要闻里讲了、热点里也顺带提到 → 仍在要闻里（本章讲了的不挪）
       3. 只在开场预告里提过、哪章都没讲 → 退回要闻开头（开场、结尾不算主讲）
       4. 热点一顺带提一句、热点三正式展开两段 → 跳热点三第一段（主讲那一章的开头，不是第一次提到）
       5. 快讯、今日一词照旧在本章里找

11-06 加（段首时间改用配音时的对齐数据，见 build_v3.py 的 para_times）：
    一、11-04 组装两遍：转写缓存换成空目录（FD_TTS_CACHE）时退回估算，13 条和修之前逐字相同；用真的缓存时，
       各条落在同一章、离原来不超过 2 秒，每段跳点都落在人声版的停顿里、离开口不到 1 秒。
       （转写缓存 14 天不用会被清掉；清掉以后这一半只核对退回估算，打印“跳过”。）
    三、11-06 真实数据（期目录先复制到草稿目录，不软链接、不碰 测试版/2026-11-06）：16 处“听这一段”和回听核对报告
       （11-06 检查报告里的播客与旁白回听，只在私有仓库）里转写出的这一条开头比，都在 ±1 秒以内、都落在停顿里、不切掉第一个字；
       E006、E206 不再落在上一条中间；E003（热点一）照旧跳本章开头（先放转场声，1.7 秒后开口，报告认为对）。
    二里另加：本章第一段是一句和这条沾边的短引子时从引子听；引子不沾边、两句以上的不算；停顿查找的几种情况。

用法（在项目根目录 frontier-daily/ 下）：
    ~/.venvs/frontier-daily/bin/python site/tools/test_listen_jump.py
草稿在项目外的 ~/.cache/frontier-daily/test_listen_jump/（每次重来）；项目里的文件、测试版/ 下的期目录都不改。
全部通过时退出码为 0。
"""
import contextlib
import io
import json
import os
import runpy
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True          # 项目在 iCloud 里，不生成 __pycache__
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DAY = "2026-11-04"
POD = os.path.join("05_配音", "播客_v3_带音效", "episode.mp3")     # 组装网页要的播客成品


def sample_issue(day, need=POD):
    """完整样期：仓库的 测试版/ 只存跨天要用的文字（选题、事件卡、文稿），没有配音、网页。
    按顺序找有 need 的那一份：环境变量 FD_SAMPLE_ROOT/<日期>、本机资料/归档/mini试运行_1031-1109/<日期>
    （mini 试运行那周的原件，只在本机、靠 iCloud 同步，不进 git）、测试版/<日期>。都没有返回 None（11-09 晚加）。"""
    bases = ([os.path.expanduser(os.environ["FD_SAMPLE_ROOT"])] if os.environ.get("FD_SAMPLE_ROOT") else []) + [
        os.path.join(ROOT, "本机资料", "归档", "mini试运行_1031-1109"), os.path.join(ROOT, "测试版")]
    return next((os.path.join(b, day) for b in bases if os.path.exists(os.path.join(b, day, need))), None)


REAL = sample_issue(DAY) or os.path.join(ROOT, "测试版", DAY)
CFG = os.path.join(HERE, "v3_issues", DAY + ".py")
SCR = os.path.expanduser("~/.cache/frontier-daily/test_listen_jump")

# 修之前（11-04 实际组装）的各条跳转；只有 E010 应该变
BEFORE = {"E001": 46.95, "E003": 197.87, "E002": 334.4, "E004": 468.2, "E010": 457.25, "E059": 528.6,
          "E058": 600.0, "E060": 612.7, "E046": 622.5, "E206": 576.1, "E005": 635.6, "E057": 648.9, "term": 661.3}
EMPTY_CACHE = os.path.join(SCR + "_空缓存")       # 转写缓存换成空目录：退回按字数比例估算

# 11-06：回听核对报告里整期转写（审查_音频1106/whisper/podcast_segments.txt）这一条开头那句的起点（秒）。
# E003 是热点一，跳本章开头（先放 2.25 秒转场声），不和这句比
DAY6 = "2026-11-06"
REPORT_1106 = {"E029": 150.58, "E002": 189.74, "E142": 259.68, "E001": 322.90, "E004": 460.18, "E019": 494.86,
               "E006": 540.02, "E007": 576.62, "E009": 597.98, "E021": 617.58, "E012": 639.56, "E206": 655.82,
               "term": 673.22, "E176": 709.32, "E017": 748.90}
# 11-06 白天重做以后（播客只重配了块 4、5、10，整期从 800.1 秒变成 804.4 秒，后面各条往后挪了 1–4 秒）：
# 同一个办法（mlx-whisper large-v3-turbo，中文，不拿上一句当提示，整期转一遍）在重做后的网页版播客上重新量的这一条开头
REPORT_1106_REDO = {"E029": 150.58, "E002": 189.30, "E142": 261.94, "E001": 323.98, "E004": 461.14, "E019": 495.46,
                    "E006": 540.96, "E007": 577.20, "E009": 601.16, "E021": 620.62, "E012": 643.78, "E206": 660.08,
                    "term": 677.50, "E176": 713.64, "E017": 753.20}
POD_SECONDS_1106 = {800.1: REPORT_1106, 804.4: REPORT_1106_REDO}     # 期目录里播客成品的时长 → 用哪一套转写时间
BEFORE_1106 = {"E003": 51.76, "E029": 151.3, "E002": 189.92, "E142": 259.8, "E001": 323.1, "E004": 459.9, "E019": 495.6,
               "E006": 535.1, "E007": 576.3, "E009": 596.7, "E021": 619.8, "E012": 638.7, "E206": 652.5, "term": 672.7,
               "E176": 712.2, "E017": 748.7}

FAILS = []


def check(ok, what):
    print(("  通过  " if ok else "  不对  ") + what)
    if not ok:
        FAILS.append(what)


def build(day=DAY, cache=None, copy=False, tag=""):
    """把期目录的各子文件夹软链接（copy=True 时复制）到草稿目录（只读），组装到草稿目录，返回组装脚本的全局变量和输出。
    cache：转写缓存目录（FD_TTS_CACHE），不给就用真的 ~/.cache/frontier-daily/tts。"""
    real = sample_issue(day) or os.path.join(ROOT, "测试版", day)
    base = os.path.join(SCR, day + tag)
    shutil.rmtree(base, ignore_errors=True)
    iss = os.path.join(base, day)
    os.makedirs(iss)
    for name in os.listdir(real):
        if name.startswith(".") or name == "10_网页v3":
            continue
        src, dst = os.path.join(real, name), os.path.join(iss, name)
        if copy:
            (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)
        else:
            os.symlink(src, dst)
    argv0, env0 = sys.argv, os.environ.get("FD_TTS_CACHE")
    sys.argv = ["build_v3.py", iss, "--config", os.path.join(HERE, "v3_issues", day + ".py"), "--out", os.path.join(base, "site")]
    if cache:
        os.makedirs(cache, exist_ok=True)
        os.environ["FD_TTS_CACHE"] = cache
    else:
        os.environ.pop("FD_TTS_CACHE", None)
    buf = io.StringIO()
    cwd = os.getcwd()
    try:
        os.chdir(ROOT)
        with contextlib.redirect_stdout(buf):
            g = runpy.run_path(os.path.join(HERE, "build_v3.py"), run_name="__main__")
    finally:
        os.chdir(cwd)
        sys.argv = argv0
        if env0 is None:
            os.environ.pop("FD_TTS_CACHE", None)
        else:
            os.environ["FD_TTS_CACHE"] = env0
    return g, buf.getvalue(), iss


def voice_db(iss):
    """人声版 episode.mp3 每 10 毫秒的响度，和换到带音效时间线的偏移（按章）。"""
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", os.path.join(iss, "05_配音", "播客_v3", "episode.mp3"),
                        "-ac", "1", "-ar", "8000", "-f", "f32le", "-"], capture_output=True, check=True)
    x = np.frombuffer(r.stdout, dtype=np.float32)
    m = len(x) // 80
    db = 20 * np.log10(np.sqrt((x[:m * 80].reshape(m, 80) ** 2).mean(axis=1)) + 1e-9)
    sq = json.load(open(os.path.join(iss, "05_配音", "播客_v3_带音效", "qc.json"), encoding="utf-8"))
    pq = json.load(open(os.path.join(iss, "05_配音", "播客_v3", "qc.json"), encoding="utf-8"))
    tl = {e["段"][3:]: e["开始秒"] for e in sq["时间线"] if e["段"].startswith("人声·")}
    first = {}
    for b in pq["各块"]:
        first.setdefault(b["章"], b["开始秒"])
    return db, {c: tl[c] - first[c] for c in tl if c in first}


def gap_to_voice(db, offs, ch, t):
    """带音效时间线上的跳点 t：(跳点是不是在停顿里, 离之后第一次连续 0.1 秒开口多少秒)。
    跳点在人声开始之前（开场第一段跳到片头里、人声进来前 0.3 秒）算停顿，从人声开头往后找开口。"""
    i = int(round((t - offs[ch]) * 100))
    if i < 0:
        k = 0
        while k < len(db) - 10 and not (db[k:k + 10] > -40).all():
            k += 1
        return True, round(k / 100 - i / 100, 2)
    k = i
    while k < len(db) - 10 and not (db[k:k + 10] > -40).all():
        k += 1
    return bool(db[i] < -40), round((k - i) / 100, 2)


def aligned(out):
    """组装输出里“听这一段的段首时间”那一行：有没有用上对齐数据。"""
    line = next((x for x in out.splitlines() if x.startswith("听这一段的段首时间")), "")
    return "对齐" in line.split("（")[0]


def real_data(g, out, label):
    print("一、11-04 真实数据（%s）" % label)
    got = {k: v.get("listen") for k, v in g["STORIES"].items()}
    check(set(got) == set(BEFORE), "条目和修之前一样（%d 条）" % len(got))
    t = got.get("E010")
    check(t is not None and g["chapter_at"](t) == "热点三", "E010 跳到热点三（%s，%s）" % (g["fmt_mmss"](t), g["chapter_at"](t) if t is not None else "-"))
    para = next((p for p in g["PARAS"] if p["text"].startswith("国内这边，同一天也有几笔芯片融资见报")), None)
    check(para is not None and t == g["jump_of"](para),
          "E010 落在“国内这边……芯片融资见报”那一段开头前（%s 秒，留 %s 秒）" % (t, para.get("lead") if para else "-"))
    check(t is not None and 365 <= t <= 375, "E010 在 6:05–6:15 之间（%s）" % g["fmt_mmss"](t))
    warns = [x for x in out.splitlines() if x.startswith("注意") and "听这一段" in x]
    check(not warns, "组装时不再报“听这一段”可能跳错" + ("：" + "；".join(warns) if warns else ""))
    return got


def fallback_1104():
    """转写缓存换成空目录：每段退回按字数比例估算，和 11-06 改之前逐字相同。"""
    g, out, _iss = build(cache=EMPTY_CACHE, tag="_估算")
    got = real_data(g, out, "没有对齐数据，退回估算")
    check(all(p.get("how") == "估算" for p in g["PARAS"]), "每段都标“估算”（%d 段）" % len(g["PARAS"]))
    same = [k for k in BEFORE if k != "E010" and got.get(k) == BEFORE[k]]
    check(len(same) == len(BEFORE) - 1, "其余 %d 条跳转和修之前完全一样（%d 条一样）" % (len(BEFORE) - 1, len(same)))
    check(got.get("E010") == 370.3, "E010 和 11-05 修好时一样（%s，应为 370.3）" % got.get("E010"))


def aligned_1104():
    """用真的转写缓存：各条还在同一章、离原来不超过 2 秒；每段跳点都在停顿里、离开口不到 1 秒。返回组装结果给第二部分用。"""
    g, out, iss = build(tag="_对齐")
    if not aligned(out):
        print("  跳过  11-04 的转写缓存已经清掉（14 天不用就清），只核对了退回估算")
        return g
    got = real_data(g, out, "用配音时的对齐数据")
    moved = {k: (BEFORE[k], got.get(k)) for k in BEFORE if k != "E010" and got.get(k) is not None
             and (abs(got[k] - BEFORE[k]) > 2 or g["chapter_at"](got[k]) != g["chapter_at"](BEFORE[k]))}
    check(not moved, "其余 12 条还在原来那一章、离原来不超过 2 秒" + ("：%s" % moved if moved else ""))
    db, offs = voice_db(iss)
    bad = []
    for p in g["PARAS"]:
        if p["how"] == "估算":
            continue
        j = g["jump_of"](p)
        quiet, gap = gap_to_voice(db, offs, p["ch"], j)
        if not quiet or gap > 1.0:
            bad.append("%s %s：%s 秒，%s，离开口 %s 秒" % (p["ch"], p["text"][:10], j, "停顿里" if quiet else "说话中", gap))
    n = sum(1 for p in g["PARAS"] if p["how"] != "估算")
    check(not bad, "对齐过的 %d 段，跳点都在人声版的停顿里、离开口不到 1 秒" % n + ("：" + "；".join(bad) if bad else ""))
    return g


def issue_1106():
    """11-06：16 处“听这一段”和回听核对报告的转写比。期目录复制过来再组装，不碰 测试版/2026-11-06。"""
    print("三、11-06 真实数据（回听核对报告里的转写时间）")
    if not sample_issue(DAY6):
        print("  跳过  没有 11-06 的完整样期（仓库的 测试版/ 只存文字，没有播客）")
        return
    g, out, iss = build(DAY6, copy=True)
    got = {k: v.get("listen") for k, v in g["STORIES"].items()}
    check(set(got) == set(BEFORE_1106), "条目和组装那天一样（%d 条）" % len(got))
    if not aligned(out):
        print("  跳过  11-06 的转写缓存已经清掉（14 天不用就清），下面只看退回估算的结果")
        return
    check(got.get("E003") == BEFORE_1106["E003"], "E003（热点一）照旧跳本章开头（%s）" % got.get("E003"))
    ep = os.path.join(iss, "05_配音", "播客_v3_带音效", "episode.mp3")
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ep],
                               capture_output=True, text=True).stdout.strip() or 0)
    refs = next((v for d, v in POD_SECONDS_1106.items() if abs(dur - d) < 0.5), None)
    if refs is None:
        print("  跳过  11-06 的播客又重配过（成品 %.1f 秒，不是早上的 800.1 秒或白天重做后的 804.4 秒），手里没有对应的转写时间" % dur)
        return
    print("  （播客成品 %.1f 秒：按%s的转写时间比）" % (dur, "早上原件" if refs is REPORT_1106 else "白天重做后"))
    db, offs = voice_db(iss)
    rows = []
    for k, ref in refs.items():
        t = got.get(k)
        ch = g["chapter_at"](t)
        quiet, gap = gap_to_voice(db, offs, ch, t)
        ok = abs(t - ref) <= 1.0 and quiet and gap <= 1.0
        rows.append(ok)
        check(ok, "%s 跳到 %s（改前 %s），报告转写这一条开头 %s，差 %+.2f 秒；%s，离开口 %s 秒"
              % (k, t, BEFORE_1106[k], ref, t - ref, "落在停顿里" if quiet else "落在说话中", gap))
    check(got.get("E006", 0) >= 539.5 and got.get("E206", 0) >= 655.0, "E006、E206 不再早跳（%s、%s）" % (got.get("E006"), got.get("E206")))
    warns = [x for x in out.splitlines() if x.startswith("注意") and "听这一段" in x]
    check(not warns, "组装时没有报“听这一段”可能跳错" + ("：" + "；".join(warns) if warns else ""))


def synthetic(g):
    print("二、构造的几种情况")
    real_paras, real_ch = list(g["PARAS"]), list(g["chapters"])
    ch = [{"start": 0.0, "title_zh": "开场"}, {"start": 50.0, "title_zh": "热点一"}, {"start": 200.0, "title_zh": "热点二"},
          {"start": 300.0, "title_zh": "热点三"}, {"start": 400.0, "title_zh": "要闻"}, {"start": 500.0, "title_zh": "快讯"},
          {"start": 600.0, "title_zh": "今日一词"}, {"start": 650.0, "title_zh": "结尾"}]
    MO = "深圳的墨芯宣布完成近十亿元人民币的 C+ 轮融资，距上一轮只隔了约五个月，两轮累计近二十亿元。"
    MO_WEB = "墨芯完成近十亿元 C+ 轮融资墨芯近十亿元 C+ 轮投向推理芯片，距上一轮约五个月，两轮累计近二十亿元。"
    filler = {"热点一": "谷歌发布了一批教育方面的更新，学校管理员没法只关掉一项。",
              "热点二": "苹果随开发者测试版向中国用户开放了新的功能。",
              "要闻": "ChatGPT 的搜索量追到了谷歌的两成，这是 OpenAI 自己的口径。",
              "快讯": "Meta 发行美元债券融资一百五十亿美元，认购需求稳健。",
              "今日一词": "今天的词是推理，英文叫 inference，就是让训练好的模型去干活。",
              "结尾": "今天就到这里，明天见。"}

    def setup(extra):
        """extra：{章名: [文字, …]}，加在各章填充段后面；每段 10 秒。"""
        paras = []
        for c in ch:
            texts = ([filler[c["title_zh"]]] if c["title_zh"] in filler else ["欢迎收听。"]) + extra.get(c["title_zh"], [])
            for i, x in enumerate(texts):
                paras.append({"ch": c["title_zh"], "t": c["start"] + 1 + 10 * i, "text": x})
        g["PARAS"][:] = paras
        g["chapters"][:] = ch

    setup({"开场": ["后面还会说到墨芯近十亿元的 C+ 轮融资，两轮累计近二十亿元。"], "热点三": [MO, "墨芯做的是稀疏推理芯片。"]})
    t = g["listen_at"]("brief", MO_WEB)
    check(t == 310.5, "1. 网页在要闻、播客在热点三讲、开场也预告过 → 跳热点三那一段（%s，应为 310.5）" % t)

    setup({"热点三": ["国内也有芯片公司融资，墨芯两轮累计近二十亿元。"], "要闻": [MO]})
    t = g["listen_at"]("brief", MO_WEB)
    check(t == 410.5, "2. 要闻里讲了、热点里也顺带提到 → 仍在要闻（%s，应为 410.5）" % t)

    setup({"开场": [MO]})
    t = g["listen_at"]("brief", MO_WEB)
    check(t == 400.0, "3. 只在开场预告里提过 → 退回要闻开头（%s，应为 400.0）" % t)

    setup({"热点一": ["顺带一提，墨芯也在融资。"], "热点三": [MO, "墨芯近十亿元 C+ 轮融资投向推理芯片，两轮累计近二十亿元。"]})
    t = g["listen_at"]("brief", MO_WEB)
    check(t == 310.5, "4. 热点一顺带一句、热点三正式展开 → 跳热点三第一段（%s，应为 310.5）" % t)

    setup({"热点三": [MO], "快讯": ["墨芯完成近十亿元 C+ 轮融资。"]})
    t = g["listen_at"]("flash", "墨芯完成近十亿元 C+ 轮融资")
    check(t == 510.5, "5a. 快讯里讲了 → 仍在快讯（%s，应为 510.5）" % t)
    setup({"热点三": [MO]})
    t = g["listen_at"]("term", "今日一词：推理让已经训练好的模型去干活，英文叫 inference")
    check(t == 600.5, "5b. 今日一词照旧在本章（%s，应为 600.5）" % t)

    # 6. 11-06 加：本章第一段是一句和这条沾边的短引子 → 从引子听；不沾边的、两句以上的不算
    TEASE = "在美国国会那边，有一个更激进的声音。"
    ANS = "亚利桑那州的民主党众议员 Yassamin Ansari 发帖说，民主党第一天的议程最该做的，是暂停先进 AI 开发。"
    ANS_WEB = "美国众议员发帖呼吁暂停先进 AI 开发：亚利桑那州民主党众议员 Yassamin Ansari 在 X 上称，民主党第一天就该暂停先进 AI 开发。"
    teaser_ch = [{"start": 0.0, "title_zh": "开场"}, {"start": 700.0, "title_zh": "预告观察"}]

    def setup2(first, rest):
        g["chapters"][:] = teaser_ch
        g["PARAS"][:] = [{"ch": "开场", "t": 1.0, "text": "欢迎收听。"}] + [
            {"ch": "预告观察", "t": 701.0 + 4 * i, "text": x} for i, x in enumerate([first] + rest)]
    setup2(TEASE, [ANS])
    t = g["listen_at"]("teaser", ANS_WEB)
    check(t == 700.5, "6a. 预告观察第一段是一句沾边的短引子 → 从引子听（%s，应为 700.5）" % t)
    setup2("欢迎收听。", [ANS])
    t = g["listen_at"]("teaser", ANS_WEB)
    check(t == 704.5, "6b. 第一段和这条不沾边 → 照旧从讲它的那段听（%s，应为 704.5）" % t)
    setup2("再快看几条消息。先说美国国会那边。", [ANS])
    t = g["listen_at"]("teaser", ANS_WEB)
    check(t == 704.5, "6c. 第一段有两句 → 不算引子（%s，应为 704.5）" % t)
    setup2(TEASE, ["另一条来自 Airbnb，公司计划推出旅行智能体。", ANS])
    t = g["listen_at"]("teaser", ANS_WEB)
    check(t == 708.5, "6d. 讲它的是本章第三段 → 不往前找引子（%s，应为 708.5）" % t)

    # 7. 11-06 加：停顿查找（人声版每 10 毫秒的响度）
    import numpy as np
    db = np.full(1000, -20.0)                    # 10 秒，全是说话
    db[300:360] = -60                            # 3.0–3.6 秒：段落之间的停顿
    db[500:520] = -60                            # 5.0–5.2 秒：逗号那样的短停顿
    db[700:715] = -60                            # 7.0–7.15 秒：一段停顿
    db[715:720] = -30                            # 中间冒一下气声
    db[720:760] = -60                            # 7.2–7.6 秒：气声后面接着停
    pn = g["pause_near"]
    check(pn(db, 3.3, 0, 10) == (3.0, 3.6), "7a. 估计落在停顿里 → 就是这一段（%s）" % (pn(db, 3.3, 0, 10),))
    check(pn(db, 2.6, 0, 10) == (3.0, 3.6), "7b. 估计早了 0.4 秒（Whisper 常这样）→ 吸到后面的停顿（%s）" % (pn(db, 2.6, 0, 10),))
    check(pn(db, 5.1, 0, 10) == (5.0, 5.2), "7c. 附近只有短停顿 → 用短停顿（%s）" % (pn(db, 5.1, 0, 10),))
    check(pn(db, 4.2, 0, 10) == (3.0, 3.6), "7d. 1 秒内长短都有 → 挑长的（%s）" % (pn(db, 4.2, 0, 10),))
    check(pn(db, 7.3, 0, 10) == (7.0, 7.6), "7e. 中间冒一下气声的停顿算一段（%s）" % (pn(db, 7.3, 0, 10),))
    check(pn(db, 9.0, 0, 10) is None, "7f. 1 秒内没有停顿 → 不吸（%s）" % (pn(db, 9.0, 0, 10),))
    check(pn(db, 3.3, 3.2, 10) is None, "7g. 停顿伸到查找范围外 → 不算（%s）" % (pn(db, 3.3, 3.2, 10),))

    # 8. 11-06 加：没有对齐数据的块（对谈稿 qc 里没有原始音频）→ 按字数比例、往前留 0.5 秒，和原来一样
    blk = {"秒数": 30.0, "原稿": "一二三四五六七八九十\n一二三四五六七八九十一二三四五六七八九十", "各条": [{}], "选用第几条": 1}
    ps = blk["原稿"].split("\n")
    check(g["para_times"](blk, ps) == [(0.0, 0.5, "估算"), (10.0, 0.5, "估算")],
          "8. 没有对齐数据 → 按字数比例（%s）" % (g["para_times"](blk, ps),))

    g["PARAS"][:], g["chapters"][:] = real_paras, real_ch


def main():
    if not os.path.isdir(REAL):
        sys.exit("找不到 %s" % REAL)
    if not os.path.exists(os.path.join(REAL, POD)):
        print("跳过：%s 的完整样期（%s）不在。仓库的 测试版/ 只存文字；要跑这个测试，设 FD_SAMPLE_ROOT 指向完整样期所在的文件夹，"
              "或在有 本机资料/归档/mini试运行_1031-1109/ 的本机上跑" % (DAY, POD))
        sys.exit(0)
    if not os.path.exists(CFG):              # 旧期网页配置只在私有仓库（2026-11 拆仓库）
        print("跳过：%s 不在（往期内容只在私有仓库；把私有仓库的 site/tools/v3_issues/ 拷进来再跑）" % os.path.relpath(CFG, ROOT))
        sys.exit(0)
    fallback_1104()
    g = aligned_1104()
    synthetic(g)
    issue_1106()
    print("全部通过" if not FAILS else "没通过 %d 项：%s" % (len(FAILS), "；".join(FAILS)))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
