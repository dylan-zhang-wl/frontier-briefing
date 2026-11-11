#!/usr/bin/env python3
"""视频 v3 无声样片：不配音，按字数估时间，出演示页（11_视频v3/），再用 video3_record.mjs --sheet 出关键帧总览。

为什么要有：周末版（11-01 定）要先看分镜和画面、不花钱；video3_build.py 一跑就配音。这个脚本走同一套核对和组装，
只是把"配音 → 对齐"换成"按字数估"：
  1. 读分镜、核对事实和数字、查触发词（和 video3_build.prepare 完全相同；不生成配图）；
  2. 旁白按 video3_build.lint_narration 查一遍（指画面、"我"、读音表）；周末另按《写稿_视频v3_周末.md》"程序检查"的禁用说法查；
  3. 每章人声秒数 = tts.est_seconds(念法) × EST_FACTOR，按配乐的排法（video3_music.plan）排出章的起止和总长；
  4. 每个字的时间按它在这一章里的位置均分，照 video3_build.align 的办法把触发词换成秒数、生成字幕；
  5. 音轨是一条静音占位（只为播放器能走时间轴），调 video3_build.build 写演示页。
画面、数字、出处和真跑一样；时间是估的（误差大约一两秒），声音没有。

用法（项目根目录）：
    PY=~/.venvs/frontier-daily/bin/python
    $PY site/tools/video3_preview.py <期目录>                      # 期目录的最后一级是日期
    node site/tools/video3_record.mjs <期目录> --sheet              # 关键帧总览.jpg
不调用任何模型接口，不花钱；不改 05_配音/（占位音轨放在 05_配音/视频旁白_v3_无声样片/）。
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for p in (str(HERE), str(ROOT / "pipeline")):
    if p not in sys.path:
        sys.path.insert(0, p)

import video3_build as VB  # noqa: E402  （只读调用：核对、组装都用它的）
import video_align  # noqa: E402
from spoken_numbers import spoken  # noqa: E402

WEEKEND_RULES = ROOT / "pipeline" / "prompts" / "写稿_视频v3_周末.md"


def weekend_lint(issue, sb):
    """周末差异里的禁用说法（周末、深度节目、第几层、Dylan……）。"""
    import yaml
    m = re.search(r"## 程序检查[^\n]*\n+```yaml\n(.*?)```", WEEKEND_RULES.read_text(encoding="utf-8"), re.S)
    rules = yaml.safe_load(m.group(1)) if m else {}
    bad = []
    for c in sb["chapters"]:
        for pat in rules.get("禁用说法") or []:
            for mm in re.finditer(pat, c["narration"]):
                bad.append("「%s」里有“%s”（周末规则：%s）" % (c["title"], c["narration"][max(0, mm.start() - 6):mm.end() + 6], pat))
    lo, hi = (rules.get("story章数") or {}).get(sb.get("edition") or "", (0, 99))
    return bad, (lo, hi)


def fake_align(sb, shown, marks, dur):
    """每章的字在这一章人声的起止之间均分时间：得到和 video_align 一样形状的结果（units、句子、字幕）。"""
    units = []
    for si, text in enumerate(shown):
        ks = [k for k, ch in enumerate(text) if video_align.is_unit(ch)]
        v0, v1 = marks[si]["voice_start"], marks[si]["voice_end"]
        step = (v1 - v0) / max(1, len(ks))
        for n, k in enumerate(ks):
            units.append({"c": text[k].lower(), "scene": si, "i": k, "s": round(v0 + n * step, 3), "e": round(v0 + (n + 1) * step, 3)})
    al = {"units": units, "narrations": list(shown), "scenes": video_align.scene_spans(units, shown),
          "sentences": video_align.spans(units, shown, video_align.SENT_END),
          "cues": video_align.subtitle_cues(units, shown, dur),
          "accuracy": {"note": "无声样片：时间按字数估，没有对齐", "median_abs_err": None}}
    T, miss = {}, []
    for key, i, spec in VB.SB.cue_list(sb):
        say_, off = spec["say"], spec["offset"]
        if say_ in ("@end", "@start"):
            v = marks[i]["end"] if say_ == "@end" else (0.0 if i == 0 else marks[i - 1]["end"])
            T[key] = T[key + ".end"] = round(v + off, 3)
            continue
        f = video_align.find(al, say_, after=marks[i]["voice_start"] - 0.3, scene=i)
        if not f:
            miss.append("%s（%s）" % (key, say_))
            continue
        T[key] = round(f[0] + off, 3)
        T[key + ".end"] = round(f[1] + off, 3)
    if miss:
        raise SystemExit("旁白里找不到这些触发词：" + "；".join(miss))
    T["open.go"] = T["open.go.end"] = marks[0]["end"]
    return al, T


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("issue", help="一期的目录（最后一级是日期）")
    a = ap.parse_args(argv)
    issue = Path(a.issue).expanduser().resolve()
    import tts  # noqa: E402
    sb, cards, facts = VB.prepare(issue, gen=False)
    VB.lint_narration(issue)
    bad, (lo, hi) = weekend_lint(issue, sb)
    if bad:
        raise SystemExit("旁白不合周末规则：\n  " + "\n  ".join(bad))
    n_story = sum(1 for c in sb["chapters"] if c["kind"] == "story")
    if not lo <= n_story <= hi:
        print("  提醒：story 章 %d 章（周末规则 %d–%d）" % (n_story, lo, hi))
    rules = VB.load_rules()
    VB.check_length(sb, rules)
    titles, shown = VB.narrations(issue)
    lens = [tts.est_seconds(spoken(t)[0]) * VB.EST_FACTOR for t in shown]
    pl = VB.MUS.plan(lens)
    dur = float(pl["duration"])
    marks = [{"chapter": c["id"], "voice_start": pl["voice_starts"][i], "voice_end": pl["voice_ends"][i],
              "end": pl["bounds"][i] if i < len(pl["bounds"]) else round(dur, 3)} for i, c in enumerate(sb["chapters"])]
    al, T = fake_align(sb, shown, marks, dur)
    for w in VB.SB.check_gaps(sb, T, marks):
        print("  提醒：" + w)
    vdir = issue / "05_配音" / "视频旁白_v3_无声样片"
    vdir.mkdir(parents=True, exist_ok=True)
    mp3 = vdir / "silent.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "%.2f" % dur,
                    "-b:a", "32k", str(mp3)], check=True)
    (vdir / "时间表.json").write_text(json.dumps({"说明": "无声样片：按字数估的章起止（秒）", "duration": dur, "chapters": marks},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    VB.build(issue, mp3, marks, dur, al, T, titles, shown, sb, cards, facts, pl=None, meas=None)
    print("无声样片：%.1f 秒，%d 章（%s）→ %s" % (dur, len(marks), "、".join(m["chapter"] for m in marks), issue / VB.OUT_DIR))
    print("关键帧总览：node site/tools/video3_record.mjs %s --sheet" % issue)
    return 0


if __name__ == "__main__":
    sys.exit(main())
