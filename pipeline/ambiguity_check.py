#!/usr/bin/env python3
"""开场、收尾、速览和小结卡里的易歧义词：只提醒、不拦（fd 第 7 步，2026-11-09 加）。

查哪里（这几处的话最短，听的人、看的人只拿到这一句）：
    · 播客稿（工作日、周六、周日都一样）的"## 开场""## 结尾"两章；
    · 视频分镜 open、close 两章的旁白（narration）；速览 headline_open 每屏的大字（text）、小字（sub）；
      各章的 storyline、chip 的 key 和 sub；收尾 end 的 title 和每一行（lines）。只看中文。
查什么：pipeline/prompts/易歧义词.yaml 小词表里的词，按字面找。找到就列出来（位置、词、原句、说明）。
为什么只提醒：这些词放对了地方没有问题（"安装程序""机场入口"），要人读一遍那一句再定改不改。

用法：
    python pipeline/ambiguity_check.py --script 04_文稿/claude_播客_v3.md --storyboard 04_文稿/视频v3_分镜.json [--json]
    任一个文件不在就跳过那一个。退出码总是 0（只提醒）；词表读不了时也照常退出 0，结果里写一句。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
WORDS = PIPE / "prompts" / "易歧义词.yaml"
PODCAST_CHAPTERS = ("开场", "结尾")        # 三种版别的播客稿都用这两个章名
VIDEO_KINDS = ("open", "close")


def load_words(path=WORDS):
    """小词表 → [(词, 说明)]，长词在前（"基座"和"底座"互不包含，但以后加"算力账单"这类时先认长的）。"""
    import yaml
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    out = []
    for e in d.get("词") or []:
        if isinstance(e, dict) and str(e.get("词") or "").strip():
            out.append((str(e["词"]).strip(), str(e.get("说明") or "").strip()))
    return sorted(out, key=lambda x: -len(x[0]))


def podcast_spots(text):
    """播客稿里开场、结尾两章的每一句 → [(位置, 句子)]。注释（<!-- -->）和 > 备注不算。"""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    spots, ch = [], None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            ch = m.group(1)
            continue
        if ch not in PODCAST_CHAPTERS or not line.strip() or line.lstrip().startswith(">"):
            continue
        body = re.sub(r"^[甲乙][：:]\s*", "", line.strip())
        for s in re.findall(r"[^。！？!?]+[。！？!?]?", body):
            if s.strip():
                spots.append(("播客·%s" % ch, s.strip()))
    return spots


def _zh(x):
    if isinstance(x, dict):
        return str(x.get("zh") or "")
    return str(x or "") if isinstance(x, str) else ""


def storyboard_spots(sb):
    """视频分镜里要查的那几处 → [(位置, 文字)]。"""
    spots = []
    for ch in sb.get("chapters") or []:
        cid = ch.get("id") or ch.get("kind") or "?"
        kind = ch.get("kind")
        if kind in VIDEO_KINDS and ch.get("narration"):
            spots.append(("视频·%s 旁白" % cid, str(ch["narration"])))
        if ch.get("storyline"):
            spots.append(("视频·%s 主线名" % cid, _zh(ch["storyline"]) or str(ch["storyline"])))
        chip = ch.get("chip") or {}
        for k in ("key", "sub"):
            if _zh(chip.get(k)):
                spots.append(("视频·%s 名牌 %s" % (cid, k), _zh(chip[k])))
        for b in ch.get("blocks") or []:
            if b.get("type") == "headline_open":
                for i, it in enumerate(b.get("items") or [], 1):
                    for k in ("text", "sub"):
                        if _zh(it.get(k)):
                            spots.append(("视频·速览第 %d 屏 %s" % (i, k), _zh(it[k])))
        end = ch.get("end") or {}
        if _zh(end.get("title")):
            spots.append(("视频·%s 小结卡标题" % cid, _zh(end["title"])))
        for i, ln in enumerate(end.get("lines") or [], 1):
            if _zh(ln):
                spots.append(("视频·%s 小结卡第 %d 行" % (cid, i), _zh(ln)))
    return spots


def find(spots, words):
    """每处文字里找词；同一处同一个词只报一次。"""
    out = []
    for where, text in spots:
        seen = set()
        for w, why in words:
            if w in text and w not in seen:
                seen.add(w)
                out.append({"位置": where, "词": w, "原文": text[:80], "说明": why})
    return out


def check(script=None, storyboard=None, words_path=WORDS):
    res = {"提醒": [], "查了": [], "说明": []}
    try:
        words = load_words(words_path)
    except Exception as e:  # noqa: BLE001  词表坏了不能挡第 7 步
        res["说明"].append("易歧义词表读不了（%s），这次没查" % e)
        return res
    spots = []
    if script and Path(script).exists():
        spots += podcast_spots(Path(script).read_text(encoding="utf-8"))
        res["查了"].append(str(script))
    if storyboard and Path(storyboard).exists():
        try:
            spots += storyboard_spots(json.loads(Path(storyboard).read_text(encoding="utf-8")))
            res["查了"].append(str(storyboard))
        except (ValueError, AttributeError) as e:
            res["说明"].append("分镜读不了（%s），只查了播客稿" % e)
    res["提醒"] = find(spots, words)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--script", help="播客稿")
    ap.add_argument("--storyboard", help="视频分镜 JSON")
    ap.add_argument("--words", default=str(WORDS), help="小词表（默认 pipeline/prompts/易歧义词.yaml）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = check(a.script, a.storyboard, a.words)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for r in res["提醒"]:
            print("提醒 %s「%s」：%s —— %s" % (r["位置"], r["词"], r["原文"], r["说明"]))
        for x in res["说明"]:
            print("注意：" + x)
        if not res["提醒"]:
            print("易歧义词：没有")
    return 0


if __name__ == "__main__":
    sys.exit(main())
