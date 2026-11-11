"""MiMo 一侧的测试流程：选题 → 事件卡 → 写稿。Claude 一侧由 Claude Code 用同一份指令和输入完成。

用法（在 pipeline/ 目录下，用 ~/.venvs/frontier-daily/bin/python；每一步都要给 --day）：
  python run_mimo.py compact --day 2026-11-01   # 候选压缩成两边共用的输入 02_选题/candidates_compact.json
                                                # （另写 02_选题/往期今日一词.json，见 term_history.py）
  python run_mimo.py select  --day 2026-11-01   # MiMo 选题 → 02_选题/mimo.json（并按规则自查）
  python run_mimo.py check   --day 2026-11-01   # 只按规则自查 02_选题/最终选题.json（不调模型；含今日一词去重、定名）
  python run_mimo.py cards   --day 2026-11-01   # 取原文、MiMo 抽事件卡、程序核对 → 03_事件卡/
  python run_mimo.py cards   --day 2026-11-01 --redo E004,E012   # 删掉这几张卡和材料，重取原文重做
  python run_mimo.py recheck --day 2026-11-01   # 不调模型，只重新核对
  python run_mimo.py assemble --day 2026-11-01  # 选题＋核对后的事件卡 → 04_文稿/写稿输入.json
  python run_mimo.py write   --day 2026-11-01   # MiMo 写播客稿（按版别选指令）、网页稿、视频稿 → 04_文稿/mimo_*

版别（--edition，默认 auto 按星期几定）：
  weekday        工作日版（周一到周五）
  saturday_deep  周六"快讯＋单人深度"：Shirley 一人，10–12 分钟（指令 写稿_周六深度.md）
  sunday_deep    周日"双人深谈"：Shirley、Dylan，15–17 分钟（指令 写稿_周日深谈.md）
  sunday_dialog  旧的周日对谈版（11-01 那期：工作日版面、播客两人对谈，指令 写稿_周日对谈.md），只为复现留着
已冻结的两期按当时的版别走，命令不变、目录和日期行与当时一字不差：
  python run_mimo.py <stage> --day 2026-10-31   # 工作日版面（那天是周六，但那期是工作日版面的测试）
  python run_mimo.py <stage> --day 2026-11-01   # 旧的周日对谈版
  （给了 --run-dir 时不按冻结表，按星期几走：彩排用）

周末版（11-01 晚定，方案 文档/方案/周末版与声音规范.md 第二、三节）还要读往期事件库（pipeline/event_db.py）：
  compact 阶段按 --asof（默认当天 06:00 UTC）汇总过去 7 天：
    周六：算出"这一周最持续的话题"留给周日，写 02_选题/留给周日.json，候选里和它重合的事件标 reserved_for_sunday（周六的快讯、深度都不碰）；
    周日：排出深谈候选（两三个），写 02_选题/周日候选.json；
    两天都写 02_选题/本周话题.md（给人看）。
  选题里写 deep（深度／深谈那一题：话题、角度、分层计划、材料网址）；cards 阶段另做一张"专题卡"（默认 D1）：
    把 deep.materials 里的网址重新取正文（就是"再补抓一次背景材料"），MiMo 抽事实，程序逐字核对，和别的事件卡放在一起。

其他参数：
  --run-dir 目录    这一期的目录（默认 测试版/<日期>）。彩排、补跑放别处，不碰 测试版/ 里的成品
  --db 目录         往期事件库（默认 测试版/往期事件库/，见 event_db.py）
  --asof 时刻       周末版汇总一周截到哪个时刻（默认当天 06:00 UTC）
"""
import argparse
import importlib.util
import json
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import keys
import llm

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROMPTS = HERE / "prompts"
PROGRAM = "每日前沿简报"
WEEKDAY_ZH = "一二三四五六日"

# 下面几个由 configure() 按 --day 设定
RUN = None
DATE_LINE = ""
EDITION = "weekday"
DB = None          # 往期事件库目录（周末版用）
ASOF = None        # 周末版汇总一周截到的时刻

EDITIONS = ("weekday", "saturday_deep", "sunday_deep", "sunday_dialog")
# 已冻结的两期：按当时的版别走（目录、日期行一字不差），只在用默认目录 测试版/<日期> 时生效
FROZEN_EDITION = {"2026-10-31": "weekday", "2026-11-01": "sunday_dialog"}
EDITION_NOTE = {
    "weekday": "本期是工作日版。",
    "saturday_deep": "本期是周六版：快讯＋单人深度（Shirley 一人）。",
    "sunday_deep": "本期是周日版：双人深谈（Shirley 和 Dylan）。",
    "sunday_dialog": "本期是周日双人对谈版：网页和视频按工作日版面，只有播客改成两位主持人对谈。",
}
EDITION_LABEL = {
    "weekday": "（工作日版）",
    "saturday_deep": "（周六版：快讯＋单人深度）",
    "sunday_deep": "（周日版：双人深谈）",
    "sunday_dialog": "（周日双人对谈版：网页、视频按工作日版面，播客为两人对谈）",
}
WEEKEND = ("saturday_deep", "sunday_deep")


def configure(day, edition="auto", run_dir=None, db=None, asof=None):
    """按日期定运行目录、日期行和版别。冻结的两期（10-31、11-01）用默认目录时按当时的版别和日期行。"""
    global RUN, DATE_LINE, EDITION, DB, ASOF
    d = date.fromisoformat(day)
    wd = d.weekday()                      # 0=星期一 … 6=星期日
    RUN = Path(run_dir).expanduser().resolve() if run_dir else ROOT / "测试版" / d.isoformat()
    if RUN.name != d.isoformat():
        raise SystemExit(f"--run-dir 的最后一级要是日期 {d.isoformat()}（网页、视频组装都按目录名认日期）：{RUN}")
    frozen = FROZEN_EDITION.get(d.isoformat()) if not run_dir else None
    if edition == "auto":
        EDITION = frozen or ("saturday_deep" if wd == 5 else "sunday_deep" if wd == 6 else "weekday")
    else:
        EDITION = edition
    head = f"今天是 {d.year} 年 {d.month} 月 {d.day} 日，星期{WEEKDAY_ZH[wd]}；"
    if frozen == "weekday" and EDITION == "weekday" and wd == 5:
        note = "本次按工作日版面测试。"     # 10-31 那期：与当时的日期行一字不差
    else:
        note = EDITION_NOTE[EDITION]
    DATE_LINE = head + note
    DB = Path(db).expanduser() if db else ROOT / "测试版" / "往期事件库"
    ASOF = asof or f"{d.isoformat()}T06:00:00Z"
    return d


def weekday_label():
    d = date.fromisoformat(RUN.name)
    s = f"星期{WEEKDAY_ZH[d.weekday()]}"
    if EDITION == "weekday" and d.weekday() == 5 and FROZEN_EDITION.get(RUN.name) == "weekday":
        return s + "（本次按工作日版面测试）"
    return s + EDITION_LABEL[EDITION]


PODCAST_PROMPT = {"weekday": ("写稿_播客.md", "mimo_播客.md"),
                  "saturday_deep": ("写稿_周六深度.md", "mimo_播客_周六深度.md"),
                  "sunday_deep": ("写稿_周日深谈.md", "mimo_播客_周日深谈.md"),
                  "sunday_dialog": ("写稿_周日对谈.md", "mimo_播客_对谈.md")}


def system_prompt(name, extra=()):
    """指令＋写作指南（＋口播稿的读音表）。extra：接在指令后面的补充指令（如周末的视频、网页差异）。"""
    guide = (PROMPTS / "写作指南.md").read_text(encoding="utf-8")
    text = (PROMPTS / name).read_text(encoding="utf-8")
    for x in extra:
        text += "\n\n---\n\n" + (PROMPTS / x).read_text(encoding="utf-8")
    text += "\n\n---\n\n# 附：写作指南\n\n" + guide
    lexicon = PROMPTS / "读音表.yaml"           # 口播稿指令要求按读音表写人名、公司、产品、媒体
    if name in {v[0] for v in PODCAST_PROMPT.values()} and lexicon.exists():
        text += "\n\n---\n\n# 附：读音表\n\n" + lexicon.read_text(encoding="utf-8")
    return text


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    print("  写入", path.relative_to(RUN))


def load_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


# ───────────── 候选 ─────────────
def eid(e):
    return str(e.get("event_id") or e.get("id"))


def members(e):
    return e.get("members") or e.get("items") or []


def _raw():
    data = json.loads((RUN / "02_选题" / "candidates.json").read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"events": data}
    if not (data.get("events") or data.get("candidates")):
        data = {"events": list(data.values())[0]}
    return data


def load_candidates():
    """热度前 N 个事件（candidates.json 的 events）。"""
    data = _raw()
    return data.get("events") or data.get("candidates")


def load_extras():
    """热度前 N 之外、但 candidates.json 里点了名的事件：专业雷达栏（lang_edu_column）、
    只有社交信号的（social_only）、中外对照候选里的另一半（cn_intl_contrast_pairs）。
    这些条目在 candidates.json 里只有标题和网址，摘要从 01_获取/prefilter.jsonl 按网址或标题补上。"""
    data = _raw()
    top = {eid(e) for e in load_candidates()}
    pf_file = RUN / "01_获取" / "prefilter.jsonl"
    rows = [json.loads(x) for x in pf_file.read_text(encoding="utf-8").splitlines() if x.strip()] if pf_file.exists() else []
    by_url, by_title = {}, {}
    for r in rows:
        if not r.get("pf", {}).get("keep", True):
            continue
        by_url.setdefault(r.get("url"), r)
        by_title.setdefault((r.get("title") or "").strip(), r)

    def enrich(m):
        r = by_url.get(m.get("url")) or by_title.get((m.get("title") or "").strip()) or {}
        return {**{k: r.get(k) for k in ("source_id", "source_name", "layer", "lang", "summary", "url", "title", "published")
                   if r.get(k)}, **{k: v for k, v in m.items() if v}, "summary": r.get("summary") or m.get("summary") or ""}

    out = {}
    for pool, lst in (("专业雷达候选", data.get("lang_edu_column") or []), ("只有社交信号", data.get("social_only") or [])):
        for e in lst:
            if eid(e) in top or eid(e) in out:
                continue
            out[eid(e)] = {**e, "pool": pool, "members": [enrich(m) for m in members(e)]}
    for p in data.get("cn_intl_contrast_pairs") or []:
        for side in ("a", "b"):
            i = str(p.get(side))
            if i in top or i in out:
                continue
            r = by_title.get((p.get(f"{side}_title") or "").strip())
            mem = [enrich({"title": r["title"], "url": r["url"]})] if r else []
            out[i] = {"event_id": i, "title_zh": p.get(f"{side}_title") if re.search(r"[一-鿿]", p.get(f"{side}_title") or "") else "",
                      "title_en": "" if re.search(r"[一-鿿]", p.get(f"{side}_title") or "") else p.get(f"{side}_title"),
                      "subject_region": p.get(f"{side}_subject"), "independent_sources": len(mem) or None,
                      "pool": "中外对照候选的另一半", "members": mem}
    return list(out.values())


def all_events():
    return {eid(e): e for e in load_candidates() + load_extras()}


def compact_one(e, pool=None):
    o = {
        "event_id": eid(e),
        "title_zh": e.get("title_zh") or e.get("rep_title_zh") or "",
        "title_en": e.get("title_en") or e.get("rep_title_en") or "",
        "heat": e.get("heat") or e.get("heat_score"),
        "independent_sources": e.get("independent_sources") or e.get("n_sources"),
        "layers": e.get("layers"), "langs": e.get("langs"),
        "cn_and_intl": e.get("cn_intl") or e.get("china_and_intl") or e.get("cn_and_intl"),
        "subject_region": e.get("subject_region"), "topics": e.get("topics"),
        "first_seen": e.get("first_seen"), "last_seen": e.get("last_seen"),
        "related": e.get("related") or e.get("related_events"),
        "items": [{"source": m.get("source_name") or m.get("source_id"), "layer": m.get("layer"),
                   "lang": m.get("lang"), "title": m.get("title"), "url": m.get("url"),
                   "published": m.get("published"), "summary": (m.get("summary") or "")[:220]}
                  for m in members(e)[:4]],
    }
    if pool:
        o["pool"] = pool
    return {k: v for k, v in o.items() if v not in (None, [], {})} | {"event_id": eid(e)}


def compact():
    out = [compact_one(e) for e in load_candidates()]
    out += [compact_one(e, e.get("pool")) for e in load_extras()]
    hints = _raw().get("cn_intl_contrast_pairs") or []
    if EDITION in WEEKEND:
        weekend_context(out)
    save(RUN / "02_选题" / "candidates_compact.json", out)
    if hints:
        save(RUN / "02_选题" / "candidates_pairs.json",
             [{k: h.get(k) for k in ("a", "a_title", "a_subject", "b", "b_title", "b_subject", "shared_topics", "sim")} for h in hints])
    n_extra = sum(1 for x in out if x.get("pool"))
    print(f"  候选 {len(out) - n_extra} 个＋补充 {n_extra} 个（专业雷达、只有社交信号、对照候选的另一半）")
    import term_history                              # 往期今日一词（11-03 加）：选题时去重、沿用中文名
    p, th = term_history.write_selection_input(RUN)
    print(f"  往期今日一词：近 {term_history.WINDOW} 天 {len(th['近30天'])} 个、更早 {len(th['更早'])} 个 → {p.relative_to(RUN)}")
    return out


# ───────────── 周末：往期事件库 ─────────────
def _event_db():
    import event_db
    return event_db


def weekend_context(compacted):
    """周末版：从往期事件库汇总过去 7 天。周六算出留给周日的话题并在候选里标出来；周日排出深谈候选。"""
    E = _event_db()
    asof = E.parse_asof(ASOF)
    try:
        w = E.week(DB, asof)
    except SystemExit as e:
        print(f"  注意：往期事件库用不了（{e}）。周六不知道该让出哪个话题，周日没有深谈候选：请先 event_db.py ingest")
        return
    (RUN / "02_选题").mkdir(parents=True, exist_ok=True)
    save(RUN / "02_选题" / "本周话题.md", E.to_md(w))
    slim = lambda t: {k: t.get(k) for k in ("topic_id", "title_zh", "title_en", "key_terms", "days", "heat_by_day", "n_sources",  # noqa: E731
                                           "n_items", "cn_and_intl", "persist", "persist_parts", "sunday_checks", "covered",
                                           "future", "related", "events")}
    if EDITION == "saturday_deep":
        r = E.reserve(w)
        save(RUN / "02_选题" / "留给周日.json", dict(slim(r), item_keys=r["item_keys"]) if r else {})
        if r:
            by_id = all_events()
            n = 0
            for c in compacted:
                urls = [m.get("url") for m in members(by_id.get(c["event_id"], {}))] + [x.get("url") for x in c.get("items") or []]
                if E.overlaps(urls, r):
                    c["reserved_for_sunday"] = True
                    n += 1
            print(f"  留给周日：{r['title_zh'] or r['title_en']}（{r['n_days']} 天，持续度 {r['persist']}）；候选里 {n} 个事件和它重合，已标 reserved_for_sunday")
    else:
        cands = E.sunday_candidates(w)
        save(RUN / "02_选题" / "周日候选.json", [dict(slim(t), item_keys=t["item_keys"]) for t in cands])
        print("  周日深谈候选：" + "；".join(f"{t['topic_id']} {t['title_zh'] or t['title_en']}（{t['n_days']} 天）" for t in cands))


def weekend_inputs():
    """选题时附给模型的周末材料（没有就空串）。"""
    out = ""
    if EDITION == "saturday_deep":
        r = load_json(RUN / "02_选题" / "留给周日.json", {})
        if r:
            r = {k: v for k, v in r.items() if k != "item_keys"}
            out += "\n\n留给周日的话题（这一周最持续的话题；周六的快讯和深度都不碰它，候选里标了 reserved_for_sunday 的事件不选）：\n" + json.dumps(r, ensure_ascii=False)
    elif EDITION == "sunday_deep":
        c = load_json(RUN / "02_选题" / "周日候选.json", [])
        if c:
            c = [{k: v for k, v in t.items() if k != "item_keys"} for t in c]
            out += "\n\n周日深谈候选（往期事件库按持续度排的，按选题指令第八节再判断）：\n" + json.dumps(c, ensure_ascii=False)
    return out


def past_lineups(n=3):
    """往期已讲：测试版里比今天早的、已经有 最终选题.json 的最近 n 期，列出入选事件的标题（跨天去重用）。"""
    today = RUN.name
    out = []
    for d in sorted((p for p in RUN.parent.iterdir() if p.is_dir() and p.name < today), reverse=True)[:n]:
        lu = load_json(d / "02_选题" / "最终选题.json")
        if not lu:
            continue
        cards_ = {c["event_id"]: c for c in load_json(d / "03_事件卡" / "cards_写稿用.json", [])}
        items = []
        for sec in ("hot", "brief", "flash", "teaser"):
            for x in lu.get(sec, []):
                c = cards_.get(x.get("event_id"), {})
                items.append({"section": sec, "title_zh": c.get("title_zh") or x.get("title_zh"),
                              "one_line_zh": c.get("one_line_zh", "")})
        for p in lu.get("cn_intl_pairs", []):
            c = cards_.get(p.get("cn_event_id"), {})
            if c:
                items.append({"section": "cn_intl", "title_zh": c.get("title_zh"), "one_line_zh": c.get("one_line_zh", "")})
        dp = lu.get("deep") or {}
        if dp:                                    # 周末那一题（周日要知道周六深度讲了什么）
            c = cards_.get(dp.get("card_id") or "D1", {})
            items.append({"section": dp.get("kind") or "deep", "title_zh": dp.get("title_zh") or c.get("title_zh"),
                          "one_line_zh": c.get("one_line_zh", "")})
        out.append({"date": d.name, "items": items})
    return out


def select():
    cands = json.loads((RUN / "02_选题" / "candidates_compact.json").read_text(encoding="utf-8"))
    pairs = load_json(RUN / "02_选题" / "candidates_pairs.json", [])
    past = past_lineups()
    user = DATE_LINE + "\n\n候选事件（JSON）：\n" + json.dumps(cands, ensure_ascii=False)
    if pairs:
        user += "\n\n程序找出的中外对照候选（只是语义相近，关系要你判断，可以不用）：\n" + json.dumps(pairs, ensure_ascii=False)
    user += "\n\n往期已讲（JSON；没有就是第一期）：\n" + json.dumps(past, ensure_ascii=False)
    terms = load_json(RUN / "02_选题" / "往期今日一词.json")
    if terms:
        user += "\n\n往期今日一词（JSON；今日一词去重、沿用中文名，见第三节）：\n" + json.dumps(terms, ensure_ascii=False)
    user += weekend_inputs()
    t0 = time.time()
    obj, r = llm.chat_json(llm.PRO, system_prompt("选题.md"), user, max_tokens=24000, temperature=0.3)
    save(RUN / "02_选题" / "mimo.json", obj)
    save(RUN / "02_选题" / "mimo_用量.json", {"model": r["model"], "usage": r["usage"],
                                             "seconds": round(time.time() - t0, 1)})
    report_check(obj, "mimo.json")


# ───────────── 选题自查（不调模型） ─────────────
def _site_vocab():
    """主题色、关系词表以网页的全站设置为准（site/tools/v3_site.py），只读不改。"""
    try:
        spec = importlib.util.spec_from_file_location("v3_site", ROOT / "site" / "tools" / "v3_site.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return set(m.ACCENTS), set(m.RELATIONS)
    except Exception:  # noqa: BLE001  读不到就用写死的一份
        return {"blue", "amber", "coral", "violet"}, {"呼应", "竞争（良性）", "对抗", "合作", "拉锯", "互补", "跟进", "分化"}


RANGES = {"hot": (2, 3), "brief": (2, 4), "flash": (3, 6), "teaser": (0, 5), "cn_intl_pairs": (0, 3)}
# 周末两版的条数（选题.md 第八节）：没有热点、要闻；快讯周六 5–6 条、周日 3–4 条；另有 deep（深度／深谈那一题）
RANGES_WEEKEND = {
    "saturday_deep": {"hot": (0, 0), "brief": (0, 0), "flash": (5, 6), "teaser": (0, 3), "cn_intl_pairs": (0, 1)},
    "sunday_deep": {"hot": (0, 0), "brief": (0, 0), "flash": (3, 4), "teaser": (0, 3), "cn_intl_pairs": (0, 1)},
}


def check_deep(lu, probs):
    """周末那一题（deep）：字段齐、材料够；周日还要有两三个候选和四条标准的判断。"""
    d = lu.get("deep")
    if not isinstance(d, dict):
        probs.append("周末版要有 deep（深度／深谈那一题）")
        return
    want = "saturday_deep" if EDITION == "saturday_deep" else "sunday_deep"
    if d.get("kind") != want:
        probs.append(f"deep.kind 应为 {want}（现在 {d.get('kind')}）")
    for k in ("card_id", "title_zh", "angle", "layers", "materials"):
        if not d.get(k):
            probs.append(f"deep 缺 {k}")
    n_layers = 3 if EDITION == "saturday_deep" else 5
    if d.get("layers") and len(d["layers"]) != n_layers:
        probs.append(f"deep.layers 应有 {n_layers} 层（现在 {len(d['layers'])}）")
    mats = d.get("materials") or []
    if mats and not 3 <= len(mats) <= 16:
        probs.append(f"deep.materials 要 3–16 条网址（现在 {len(mats)}）")
    if EDITION == "sunday_deep":
        c = lu.get("sunday_candidates") or []
        if not 2 <= len(c) <= 3:
            probs.append(f"sunday_candidates 要两三个候选（现在 {len(c)}）")
        if not d.get("hook_zh"):
            probs.append("周日 deep 缺 hook_zh（开头的那个反差）")
        if not d.get("nodes"):
            probs.append("周日 deep 缺 nodes（未来一到四周看得见的节点）")
    if EDITION == "saturday_deep":
        r = load_json(RUN / "02_选题" / "留给周日.json", {}) if RUN else {}
        if r and r.get("item_keys"):
            E = _event_db()
            by_id = all_events() if (RUN / "02_选题" / "candidates.json").exists() else {}
            for sec in ("flash", "teaser"):
                for x in lu.get(sec) or []:
                    if E.overlaps([m.get("url") for m in members(by_id.get(x.get("event_id"), {}))], r):
                        probs.append(f"{sec} {x.get('event_id')} 是留给周日的话题，周六不碰")
            if E.overlaps([m.get("url") if isinstance(m, dict) else m for m in mats], r):
                probs.append("周六的深度和留给周日的话题重合（deep.materials 里有它的报道）")


def check_lineup(lu):
    """按 选题.md 的硬性规则查一遍，返回问题清单（空 = 通过）。中国三成、公司 2 条要看事件卡或人工，这里只查有字段可查的。"""
    accents, relations = _site_vocab()
    probs = []
    weekend = EDITION in WEEKEND
    if weekend:
        check_deep(lu, probs)
    for k, (lo, hi) in (RANGES_WEEKEND[EDITION] if weekend else RANGES).items():
        n = len(lu.get(k) or [])
        if not lo <= n <= hi:
            probs.append(f"{k} 有 {n} 条，规定 {lo}–{hi}")
    sl = lu.get("storylines") or []
    ids = {s.get("id") for s in sl}
    if not (1 <= len(sl) <= 2 if weekend else 2 <= len(sl) <= 3):
        probs.append(f"主线 {len(sl)} 条，规定 {'1–2' if weekend else '2–3'} 条")
    seen, nulls = {}, 0
    radar_id = (lu.get("radar") or {}).get("event_id") if isinstance(lu.get("radar"), dict) else None
    for sec in ("hot", "brief", "flash", "teaser"):
        for x in lu.get(sec) or []:
            e = x.get("event_id")
            if e in seen:
                probs.append(f"{e} 同时出现在 {seen[e]} 和 {sec}")
            seen[e] = sec
            s = x.get("storyline", "缺")
            if s == "缺":
                probs.append(f"{sec} {e} 没有 storyline 字段")
            elif s is None:
                nulls += 1 if not weekend else 0          # 周末快讯本来就不挂主线
                if sec in ("hot", "brief") and e != radar_id:
                    probs.append(f"{sec} {e} 没挂主线（热点、要闻必须挂，专业雷达那一条除外）")
            elif s not in ids:
                probs.append(f"{sec} {e} 的 storyline {s} 不在主线里")
    if nulls > 2:
        probs.append(f"没挂主线的条目 {nulls} 条，规定最多 2 条")
    for s in sl if not weekend else []:
        if not any(x.get("storyline") == s.get("id") for sec in ("hot", "brief") for x in lu.get(sec) or []):
            probs.append(f"主线 {s.get('id')} 下面没有热点或要闻")
    th = lu.get("theme") or {}
    if th.get("accent") not in accents:
        probs.append(f"主题色 {th.get('accent')} 不在 {sorted(accents)} 里")
    for p in lu.get("cn_intl_pairs") or []:
        if p.get("relation") not in relations:
            probs.append(f"对照 {p.get('intl_event_id')}–{p.get('cn_event_id')} 的关系「{p.get('relation')}」不在 8 个词里")
    rd = lu.get("radar")
    if rd:
        if isinstance(rd, list):
            probs.append("radar 应是一个对象或 null，每期最多 1 条")
        elif rd.get("event_id") not in seen:
            probs.append(f"专业雷达 {rd.get('event_id')} 没有放进要闻或快讯")
    sc = lu.get("self_check") or {}
    china, total = sc.get("china_related_ids") or [], sc.get("total_items")
    if total and len(china) / total < 0.3:
        probs.append(f"自报中国相关 {len(china)}/{total}，不到三成")
    probs += term_check(lu)[0]
    return probs


def term_check(lu):
    """今日一词：近 30 天讲过的要标 repeat_of、中文名沿用往期（term_history.py，11-03 加）。返回 (要改, 提醒)。"""
    if RUN is None:
        return [], []
    import term_history
    return term_history.lineup_problems(lu, RUN, EDITION)


def report_check(lu, name):
    probs = check_lineup(lu)
    print(f"  选题自查（{name}）：" + ("全部通过" if not probs else f"{len(probs)} 处"))
    for p in probs:
        print("   -", p)
    for w in term_check(lu)[1]:
        print("  提醒：" + w)
    return probs


def check():
    report_check(json.loads((RUN / "02_选题" / "最终选题.json").read_text(encoding="utf-8")), "最终选题.json")


# ───────────── 事件卡 ─────────────
SKIP_HOSTS = ("x.com", "twitter.com", "reddit.com")


def fetch_text(url):
    """取正文；X、Reddit 不抓（只用摘要）；失败返回空串。"""
    if not url or any(h in url for h in SKIP_HOSTS):
        return ""
    try:
        import trafilatura
        html = trafilatura.fetch_url(url)
        if not html:
            return ""
        return (trafilatura.extract(html, include_comments=False, include_tables=False) or "")[:6000]
    except Exception:  # noqa: BLE001  抓不到就用摘要
        return ""


def norm(s):
    """比对用：全角半角统一、小写、去掉所有空白和引号差异。"""
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", "", s)


def number_in(value, quote):
    """数字是否出现在原文片段里：去掉约、~ 等前缀；"64% / 51%" 这类复合值逐个查；
    "$20B" 能匹配 "$20 billion"（去空白后 "$20b" 是 "$20billion" 的前缀）。"""
    parts = [p for p in re.split(r"[/、,，]| to |–|-", str(value)) if p.strip()]
    for p in parts or [str(value)]:
        p = norm(p).lstrip("~≈约近超逾")
        if p and p not in quote and p.rstrip("bmkt") not in quote:
            return False
    return True


def verify(card, materials):
    """逐字核对：quote 要能在原文里找到；数字要出现在 quote 里。
    problems 是真问题（原文找不到）；soft 是格式差异，供人工看。"""
    texts = {m["id"]: norm(m["title"] + " " + m["summary"] + " " + m["text"]) for m in materials}
    alltext = "".join(texts.values())
    problems, soft, bad = [], [], set()
    for field in ("facts", "numbers", "who_said"):
        for i, x in enumerate(card.get(field) or []):
            # 只去掉片段首尾的引号（11-01：模型抄萨克斯原话时在开头多加了一个“，原文那句话前没有引号），
            # 中间的字一个不放过
            q = norm(x.get("quote")).strip("\"'「」『』《》")
            if not q:
                problems.append(f"{field}[{i}] 没有原文片段")
                bad.add((field, i))
            elif q not in alltext:
                problems.append(f"{field}[{i}] 原文里找不到：{(x.get('quote') or '')[:60]}")
                bad.add((field, i))
            elif field == "numbers" and not number_in(x.get("value"), q):
                soft.append(f"numbers[{i}] 数字 {x.get('value')} 与原文写法不同，请人工看")
    return problems, soft, bad


def clean_card(card, bad):
    """写稿只用核对通过的事实：去掉原文里找不到的条目，另存 _removed 备查。"""
    c = {k: v for k, v in card.items() if not k.startswith("_")}
    removed = []
    for field in ("facts", "numbers", "who_said"):
        keep = []
        for i, x in enumerate(card.get(field) or []):
            (removed if (field, i) in bad else keep).append(x)
        c[field] = keep
    c["_removed_unverified"] = removed
    return c


def lineup_ids(lineup):
    ids = []
    for k in ("hot", "brief", "flash", "teaser"):
        ids += [x["event_id"] for x in lineup.get(k, []) if x.get("event_id")]
    for p in lineup.get("cn_intl_pairs", []):           # 中外对照里配对的那一条也要有事件卡
        ids += [p.get("intl_event_id"), p.get("cn_event_id")]
    return [i for i in dict.fromkeys(ids) if i]


def build_materials(e):
    mats = []
    for i, m in enumerate(members(e)[:3], 1):
        mats.append({"id": f"s{i}", "name": m.get("source_name") or m.get("source_id"), "url": m.get("url"),
                     "date": m.get("published"), "layer": m.get("layer"), "title": m.get("title") or "",
                     "summary": m.get("summary") or "", "text": fetch_text(m.get("url"))})
    return mats


def card_for(e):
    mats = build_materials(e)
    save(RUN / "03_事件卡" / "材料" / f"{eid(e)}.json", mats)
    user = DATE_LINE + f"\n\n事件 ID：{eid(e)}\n\n材料（JSON）：\n" + json.dumps(mats, ensure_ascii=False)
    t0 = time.time()
    obj, r = llm.chat_json(llm.PRO, system_prompt("事件卡.md"), user, max_tokens=16000, temperature=0.2)
    obj["event_id"] = eid(e)
    r["seconds"] = round(time.time() - t0, 1)
    return obj, mats, r


def recheck():
    """不重新调模型：重新取材料（没存过的才取），用新规则核对全部事件卡，并生成写稿用的干净版。"""
    by_id = all_events()
    cards_ = json.loads((RUN / "03_事件卡" / "cards.json").read_text(encoding="utf-8"))
    report = ["# 事件卡核对", "", "程序逐字核对每条事实、数字、引语的原文片段（比对时忽略空白、全半角和引号差异）。",
              "「原文找不到」的条目已从写稿材料里去掉；「写法不同」只提示，不去掉。", ""]
    clean = []
    for c in cards_:
        f = RUN / "03_事件卡" / "材料" / f"{c['event_id']}.json"
        if not f.exists() and c["event_id"] not in by_id:
            print(f"  注意：{c['event_id']} 没有存下的材料，也不在候选里，没法核对，跳过")
            continue
        mats = json.loads(f.read_text(encoding="utf-8")) if f.exists() else build_materials(by_id[c["event_id"]])
        if not f.exists():
            save(f, mats)
        probs, soft, bad = verify(c, mats)
        n_all = sum(len(c.get(k) or []) for k in ("facts", "numbers", "who_said"))
        c["_check"] = {"problems": probs, "soft": soft, "fulltext_sources": sum(1 for m in mats if m["text"]),
                       "kept": n_all - len(bad), "total": n_all}
        clean.append(clean_card(c, bad))
        report += [f"## {c.get('title_zh') or c['event_id']}（{c['event_id']}）",
                   f"- 取到正文的来源：{c['_check']['fulltext_sources']}/{len(mats)}；"
                   f"通过 {n_all - len(bad)}/{n_all} 条（事实、数字、引语合计）",
                   "- 核对：" + ("全部通过" if not probs else f"{len(probs)} 处原文找不到，已从写稿材料去掉"),
                   *[f"  - {p}" for p in probs], *[f"  - （提示）{s}" for s in soft], ""]
    save(RUN / "03_事件卡" / "cards.json", cards_)
    save(RUN / "03_事件卡" / "cards_写稿用.json", clean)
    save(RUN / "03_事件卡" / "核对.md", "\n".join(report))


DEEP_NOTE = {
    "saturday_deep": ("这是周六深度那一题的专题卡：材料是这一两天关于同一件事的几篇报道和官方页面。"
                      "facts 尽量覆盖讲透它要用的三层：发生了什么（时间、谁、做了什么）；为什么重要（它怎么运作、关键数字和口径）；"
                      "接下来看什么（已排期的日子、当事方说的下一步）。官方没有公开的不要写成事实。"),
    "sunday_deep": ("这是周日深谈那一题的专题卡：材料是过去一周关于同一件事的多篇报道、官方页面和第三方评测。"
                    "facts 尽量覆盖讲深它要用的五层：一周里的几个节点（哪天、谁、做了什么）；技术上公开了什么、怎么做到的（官方没公开的不写）；"
                    "关键数字和各自的口径（价格、算力、评测分数，谁测的、怎么测的）；各方说法（官方、第三方评测、竞品、国内同类）；"
                    "接下来的节点。来源之间说法不一的两种都写，并在 open_questions_zh 里注明。"),
}


def deep_materials(deep):
    """deep.materials（网址，或 {url, title, source_name, published, summary}）→ 事件卡材料：每条都重新取正文（补抓背景材料）。"""
    known = {}
    for e in all_events().values():
        for m in members(e):
            if m.get("url"):
                known.setdefault(m["url"], m)
    mats = []
    for i, m in enumerate(deep.get("materials") or [], 1):
        m = {"url": m} if isinstance(m, str) else dict(m)
        k = known.get(m["url"]) or {}
        mats.append({"id": f"s{i}", "name": m.get("source_name") or k.get("source_name") or m.get("name") or "",
                     "url": m["url"], "date": m.get("published") or k.get("published") or m.get("date"),
                     "layer": m.get("layer") or k.get("layer"), "title": m.get("title") or k.get("title") or "",
                     "summary": m.get("summary") or k.get("summary") or "", "text": fetch_text(m["url"])})
    return mats


def deep_card(lineup, redo=False):
    """周末那一题的专题卡（默认 D1）：重新取 deep.materials 的正文，MiMo 抽事实，存进 cards.json，再统一核对。"""
    deep = lineup.get("deep") or {}
    if not deep:
        return None
    cid = deep.get("card_id") or "D1"
    mfile = RUN / "03_事件卡" / "材料" / f"{cid}.json"
    if redo:
        mfile.unlink(missing_ok=True)
    mats = json.loads(mfile.read_text(encoding="utf-8")) if mfile.exists() else deep_materials(deep)
    save(mfile, mats)
    got = sum(1 for m in mats if m["text"])
    print(f"  专题卡 {cid}：材料 {len(mats)} 条，取到正文 {got} 条")
    note = DEEP_NOTE.get(deep.get("kind") or EDITION, DEEP_NOTE["sunday_deep"])
    user = (DATE_LINE + f"\n\n事件 ID：{cid}\n\n{note}\n话题：{deep.get('title_zh', '')}\n\n材料（JSON）：\n"
            + json.dumps(mats, ensure_ascii=False))
    t0 = time.time()
    obj, r = llm.chat_json(llm.PRO, system_prompt("事件卡.md"), user, max_tokens=24000, temperature=0.2)
    obj["event_id"] = cid
    r["seconds"] = round(time.time() - t0, 1)
    return cid, obj, r


def cards(lineup_file, redo=()):
    lineup = json.loads((RUN / "02_选题" / lineup_file).read_text(encoding="utf-8"))
    by_id = all_events()
    want = [i for i in lineup_ids(lineup) if i in by_id]
    missing = [i for i in lineup_ids(lineup) if i not in by_id]
    if missing:
        print("  注意：这些 event_id 在候选里找不到，跳过：", ", ".join(missing))
    old_file = RUN / "03_事件卡" / "cards.json"
    done = {c["event_id"]: c for c in json.loads(old_file.read_text(encoding="utf-8"))} if old_file.exists() else {}
    for i in redo:                                       # 重做：删卡、删材料，重新取原文
        done.pop(i, None)
        (RUN / "03_事件卡" / "材料" / f"{i}.json").unlink(missing_ok=True)
    todo = [by_id[i] for i in want if i not in done]      # 已做过的事件卡不重做
    print(f"  选题共 {len(want)} 条，已有 {len(want) - len(todo)} 张，这次要做 {len(todo)} 张")
    new = {}
    usage_file = RUN / "03_事件卡" / "mimo_用量.json"
    usage = load_json(usage_file, {"model": llm.PRO, "cards": {}})
    with ThreadPoolExecutor(max_workers=3) as ex:
        for e, (card, mats, r) in zip(todo, ex.map(card_for, todo)):
            new[eid(e)] = card
            usage["cards"][eid(e)] = {"usage": r["usage"], "seconds": r["seconds"],
                                      "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    results = [done.get(i) or new[i] for i in want]
    deep = lineup.get("deep") or {}
    if deep:                                             # 周末那一题的专题卡（已做过就不重做，--redo D1 重做）
        cid = deep.get("card_id") or "D1"
        if cid in done and cid not in redo:
            results.append(done[cid])
        else:
            cid, card, r = deep_card(lineup, redo=cid in redo)
            results.append(card)
            usage["cards"][cid] = {"usage": r["usage"], "seconds": r["seconds"],
                                   "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    tot = {}
    for v in usage["cards"].values():
        for k, n in (v.get("usage") or {}).items():
            if isinstance(n, int):
                tot[k] = tot.get(k, 0) + n
    usage["total"] = tot
    save(usage_file, usage)
    save(RUN / "03_事件卡" / "cards.json", results)
    recheck()


# ───────────── 写稿输入 ─────────────
def assemble(lineup_file, notes=""):
    """选题＋核对后的事件卡 → 04_文稿/写稿输入.json（与 10-31 同一形状，另加 edition）。"""
    lineup = json.loads((RUN / "02_选题" / lineup_file).read_text(encoding="utf-8"))
    clean = {c["event_id"]: c for c in json.loads((RUN / "03_事件卡" / "cards_写稿用.json").read_text(encoding="utf-8"))}
    ids = lineup_ids(lineup) + ([(lineup.get("deep") or {}).get("card_id") or "D1"] if lineup.get("deep") else [])
    lost = [i for i in ids if i not in clean]
    if lost:
        raise SystemExit(f"这些条目还没有核对过的事件卡：{', '.join(lost)}")
    out = {"date": RUN.name, "weekday": weekday_label(), "edition": EDITION, "program": PROGRAM,
           "lineup": {k: v for k, v in lineup.items() if not k.startswith("_") and k not in ("dropped_notable", "self_check")},
           "cards": [{k: v for k, v in clean[i].items() if not k.startswith("_")} for i in ids],
           "notes": notes or lineup.get("_notes_for_writers", "")}
    save(RUN / "04_文稿" / "写稿输入.json", out)


# ───────────── 写稿 ─────────────
def write():
    inp = json.loads((RUN / "04_文稿" / "写稿输入.json").read_text(encoding="utf-8"))
    user = DATE_LINE + "\n\n今天的选题与事件卡（JSON）：\n" + json.dumps(inp, ensure_ascii=False)
    meta = {}
    pod_prompt, pod_out = PODCAST_PROMPT[EDITION]
    if not (PROMPTS / pod_prompt).exists():
        raise SystemExit(f"缺少播客指令 prompts/{pod_prompt}")
    t0 = time.time()
    r = llm.chat(llm.PRO, system_prompt(pod_prompt), user, max_tokens=24000, temperature=0.6)
    save(RUN / "04_文稿" / pod_out, r["content"])
    meta["播客"] = {"prompt": pod_prompt, "usage": r["usage"], "seconds": round(time.time() - t0, 1)}
    # 网页、视频：工作日照旧；周末在工作日指令后面接上"周末差异"（只写和工作日不同的地方），视频用 v3 分镜
    jobs = ((("网页", "写稿_网页.md", ()), ("视频", "写稿_视频.md", ())) if EDITION not in WEEKEND else
            (("网页", "写稿_网页.md", ("写稿_网页_周末.md",)), ("视频", "写稿_视频v3.md", ("写稿_视频v3_周末.md",))))
    for name, fn, extra in jobs:
        t0 = time.time()
        obj, r = llm.chat_json(llm.PRO, system_prompt(fn, extra), user, max_tokens=24000, temperature=0.4)
        save(RUN / "04_文稿" / f"mimo_{name}.json", obj)
        meta[name] = {"usage": r["usage"], "seconds": round(time.time() - t0, 1)}
    save(RUN / "04_文稿" / "mimo_用量.json", meta)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["compact", "select", "check", "cards", "recheck", "assemble", "write", "dateline"])
    ap.add_argument("--day", required=True, help="YYYY-MM-DD，对应 测试版/<日期>/")
    ap.add_argument("--edition", default="auto", choices=["auto", *EDITIONS])
    ap.add_argument("--run-dir", help="这一期的目录（默认 测试版/<日期>；最后一级要是日期）")
    ap.add_argument("--db", help="往期事件库目录（默认 测试版/往期事件库/）")
    ap.add_argument("--asof", help="周末版汇总一周截到哪个时刻（默认当天 06:00 UTC）")
    ap.add_argument("--lineup", default="最终选题.json")
    ap.add_argument("--redo", default="", help="cards 阶段重做的事件，逗号分隔，如 E004,E012（专题卡写 D1）")
    ap.add_argument("--notes", default="", help="assemble 阶段写进 写稿输入.json 的 notes")
    a = ap.parse_args()
    configure(a.day, a.edition, a.run_dir, a.db, a.asof)
    if a.stage == "dateline":                       # 只看日期行和版别，不读密钥
        print(RUN, EDITION, DATE_LINE, sep="\n")
        sys.exit(0)
    if a.stage in ("select", "cards", "write"):
        keys.install_excepthook()                   # 未捕获的报错也先抹掉密钥再打印
        print("MiMo 密钥就位：", keys.load_local_env())
    {"compact": compact, "select": select, "check": check, "recheck": recheck, "write": write,
     "assemble": lambda: assemble(a.lineup, a.notes),
     "cards": lambda: cards(a.lineup, [x.strip() for x in a.redo.split(",") if x.strip()])}[a.stage]()
    sys.exit(0)
