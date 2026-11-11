#!/usr/bin/env python3
"""云端画网页图（日卡、头条、要闻、深度、今日一词）：照写稿时网页稿里的画面描述，用 Codex 一张张画（2026-11-08 晚加）。

为什么要它：mini 上网页图是会话里照 `04_文稿/claude_网页.json` 的 `page.images.<id>.brief_en` 一张张画的（先 agy、不行再 Codex，
见 进度备忘.md"规矩"里配图那一行），fd 第 10 步只会停下等人画。云端没有人，也没有 agy，所以由这个程序按同样的画面描述、
同样的画风（video3_images.py 的 prompt_for：HEAD + palette_style）调 Codex 画，存成 `06_配图/<id>.png`（id 小写，和 fd 第 10 步认的一样）。
调 Codex 用的就是 video3_images.py 的 gen_codex（干净环境，带 CODEX_HOME），一张约 40 秒、不另花钱（ChatGPT 订阅）。
画不成的那一张不管它：第 10–17 步带着 --skip-images，缺的网页图用程序画的主题色封面。

要画哪些：和 pipeline/orchestrator/steps.py 的 Images.wanted 一样——日卡 card、今日一词 term（方图）、headline/brief/deep 各条的 id。
已经有图的不重画。

用法（在仓库根目录，用项目环境的 Python）：
    ~/.venvs/frontier-daily/bin/python cloud/web_images.py 测试版/2026-11-09            # 画
    ~/.venvs/frontier-daily/bin/python cloud/web_images.py 测试版/2026-11-09 --dry-run  # 只列要画哪几张、提示词开头，不调 Codex
    ~/.venvs/frontier-daily/bin/python cloud/web_images.py 测试版/2026-11-09 --max 1    # 最多画 1 张（测试通路用，省 Codex 额度；其余退回程序封面）
退出码：0 全部画成或没有要画的；1 有画不成的（不挡后面）；2 参数或输入不对。
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site/tools"))

import video3_images as V          # noqa: E402

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
WORKERS = 3


def wanted(web):
    """同 steps.py Images.wanted 的网页部分：返回小写 id 列表。"""
    want = ["card"]
    for s in web.get("sections") or []:
        k = s.get("kind")
        if k == "term":
            want.append("term")
        elif k in ("headline", "brief", "deep"):
            want += [str(it.get("id")).lower() for it in s.get("items") or [] if it.get("id")]
    return list(dict.fromkeys(want))


def main(argv=None):
    ap = argparse.ArgumentParser(description="云端画网页图（Codex）")
    ap.add_argument("issue")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, help="最多画几张（测试用，11-11 加：私有仓库的配图流程测试时给 1；其余不画，退回程序封面）")
    a = ap.parse_args(argv)
    issue = (ROOT / a.issue).resolve() if not Path(a.issue).is_absolute() else Path(a.issue)
    webf = issue / "04_文稿/claude_网页.json"
    if not webf.exists():
        print("✗ 没有网页稿 %s" % webf)
        return 2
    web = json.loads(webf.read_text(encoding="utf-8"))
    briefs = {str(k).lower(): v for k, v in ((web.get("page") or {}).get("images") or {}).items() if isinstance(v, dict)}
    sb = issue / "04_文稿/视频v3_分镜.json"
    accent = (json.loads(sb.read_text(encoding="utf-8")).get("accent") if sb.exists() else None) or "blue"
    out = issue / "06_配图"
    out.mkdir(parents=True, exist_ok=True)
    have = {f.stem.lower() for f in out.iterdir() if f.suffix.lower() in IMG_EXT}
    jobs, nobrief = [], []
    for rid in wanted(web):
        if rid in have:
            continue
        b = (briefs.get(rid) or {}).get("brief_en")
        if not b:
            nobrief.append(rid)
            continue
        jobs.append({"id": rid, "format": "square" if rid == "term" else "card", "brief_en": b})
    capped = []
    if a.max is not None and len(jobs) > max(a.max, 0):
        capped, jobs = [r["id"] for r in jobs[max(a.max, 0):]], jobs[:max(a.max, 0)]
    print("网页图：要 %d 张，已有 %d 张，这次画 %d 张%s；主题色 %s" % (
        len(wanted(web)), len(have & set(wanted(web))), len(jobs),
        "（没有画面描述、画不了：%s）" % "、".join(nobrief) if nobrief else "", accent))
    if capped:
        print("（--max %d：这次不画 %s，退回程序封面）" % (a.max, "、".join(capped)))
    if a.dry_run:
        for r in jobs:
            print("  %s（%s）：%s" % (r["id"], V.FORMATS[r["format"]], V.prompt_for(r, accent)[:160].replace("\n", " ")))
        return 0
    if not jobs:
        return 0
    with ThreadPoolExecutor(WORKERS) as ex:
        res = list(ex.map(lambda r: (r["id"], V.gen_codex(out, r, accent)), jobs))
    bad = [rid for rid, x in res if not x.get("ok")]
    for rid, x in res:
        print("  %s：%s（%s 秒，退出码 %s）" % (rid, "画成" if x.get("ok") else "没成", x.get("secs"), x.get("code")))
    print("画成 %d 张，没成 %d 张%s" % (len(res) - len(bad), len(bad), "（%s，用程序封面）" % "、".join(bad) if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
