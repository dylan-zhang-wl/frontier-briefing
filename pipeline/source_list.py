#!/usr/bin/env python3
"""把信源清单（sources_test.yaml）整理成给人看的表：每个来源是哪国的、什么类型、某一天贡献了多少。

用途：增删来源前先看清现状；以后换领域（比如教育简报）时，照这张表逐条换掉来源即可。
贡献数据来自某一期的产物（--day）：窗口内条数取自 01_获取/每源统计.json，
"进候选"＝它出现在交给模型挑选的前 60 个事件里几次，"入选"＝它出现在最终选题的事件里几次。
一天的数据只能看个大概，删来源前至少看一周。

运行：~/.venvs/frontier-daily/bin/python pipeline/source_list.py --day 2026-10-31
输出：文档/信源清单.md（--out 可改）
"""

import argparse
import json
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

LAYER_ZH = {"primary_intl": "国际一手", "primary_cn": "中国一手", "media_intl": "国际媒体与商业",
            "media_cn": "中文媒体", "community": "社区信号", "aggregator": "二手整合",
            "lang_edu": "语言·翻译·教育"}
TYPE_ZH = {"rss": "订阅源", "hn": "Hacker News 接口", "hf_models": "Hugging Face 新模型",
           "hf_papers": "Hugging Face 每日论文", "github_search": "GitHub 搜索", "github_org_repos": "GitHub 新建仓库",
           "ainews": "AINews（含 X、Reddit 回顾）"}


def contributions(day_dir: Path):
    """某一期里每个来源的窗口内条数、进候选的事件数、入选的事件数。"""
    win, cand, final = {}, Counter(), Counter()
    stat_file = day_dir / "01_获取" / "每源统计.json"
    if stat_file.exists():
        for s in json.loads(stat_file.read_text(encoding="utf-8")):
            win[s["id"]] = s.get("kept", s.get("items", 0))
    cand_file, final_file = day_dir / "02_选题" / "candidates.json", day_dir / "02_选题" / "最终选题.json"
    if cand_file.exists() and final_file.exists():
        sel = json.loads(final_file.read_text(encoding="utf-8"))
        picked = {x.get("event_id") for k in ("hot", "brief", "flash", "teaser") for x in (sel.get(k) or [])}
        for e in json.loads(cand_file.read_text(encoding="utf-8"))["events"]:
            for sid in {m["source_id"] for m in e["members"]}:
                cand[sid] += 1
                if e["event_id"] in picked:
                    final[sid] += 1
    return win, cand, final


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sources", default=str(HERE / "sources_test.yaml"))
    ap.add_argument("--day", help="用哪一期的数据看贡献，如 2026-10-31；不给就只列清单")
    ap.add_argument("--out", default=str(ROOT / "文档" / "信源清单.md"))
    args = ap.parse_args()

    sources = yaml.safe_load(Path(args.sources).read_text(encoding="utf-8"))["sources"]
    win, cand, final = contributions(ROOT / "测试版" / args.day) if args.day else ({}, Counter(), Counter())
    # AINews 拆出的两类社交信号不在清单里，贡献算回 AINews 名下
    for derived in ("ainews-x", "ainews-reddit"):
        for table in (win, cand, final):
            if derived in table:
                table["ainews"] = table.get("ainews", 0) + table[derived]

    region = Counter("国内" if s["region"] == "cn" else "国外" for s in sources)
    lines = [f"# 信源清单（{len(sources)} 个）", "",
             f"由 `pipeline/source_list.py` 从 `{Path(args.sources).relative_to(ROOT)}` 生成，不要手改这份表；改来源请改那个文件。", "",
             f"- 国外 {region['国外']} 个，国内 {region['国内']} 个。",
             "- 按类型：" + "，".join(f"{LAYER_ZH.get(k, k)} {v}" for k, v in Counter(s['layer'] for s in sources).most_common()) + "。"]
    if args.day:
        silent = [s for s in sources if not cand[s["id"]]]
        lines += [f"- {args.day} 这一期：{sum(1 for s in sources if win.get(s['id']))} 个来源在时间窗内有新条目；"
                  f"{len(sources) - len(silent)} 个进了候选，{len(silent)} 个没进。一天只能看个大概，删来源前至少看一周。"]
    lines += ["", "## 怎么改", "",
              "- **删**：在 `pipeline/sources_test.yaml` 里删掉那一行，或在行首加 `#` 暂时停用。",
              "- **加**：复制同类的一行，改 `id`（不能重名）、`name`、`url`，再按说明填 `layer`（类型）和 `region`（cn 国内、intl 国外）。",
              "- **换领域**：整份换掉即可，程序不用改。比如做教育简报，就换成教育部门、教育媒体、教育研究的来源。",
              "- 改完跑一次抓取，看 `01_获取/每源统计.md` 里新来源有没有抓到东西。", ""]
    cols = "| 来源 | 国内/国外 | 抓取方式 | 专讲 AI |" + (" 窗口内条数 | 进候选 | 入选 |" if args.day else "") + " 备注 |"
    sep = "|---|---|---|---|" + ("---:|---:|---:|" if args.day else "") + "---|"
    for layer in LAYER_ZH:
        group = [s for s in sources if s["layer"] == layer]
        if not group:
            continue
        lines += [f"## {LAYER_ZH[layer]}（{len(group)} 个）", "", cols, sep]
        for s in group:
            note = (s.get("note") or "").replace("|", "／")
            note = note if len(note) <= 40 else note[:39] + "…"
            row = [s["name"], "国内" if s["region"] == "cn" else "国外", TYPE_ZH.get(s["type"], s["type"]),
                   "是" if s.get("ai_focused") else "否"]
            if args.day:
                row += [str(win.get(s["id"], 0)), str(cand[s["id"]]), str(final[s["id"]])]
            lines.append("| " + " | ".join(row + [note]) + " |")
        lines.append("")
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"✓ {args.out}")


if __name__ == "__main__":
    main()
