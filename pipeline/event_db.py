#!/usr/bin/env python3
"""往期事件库（最小可用版）：把每天抓到的材料、选了什么、做了哪些事件卡存下来，周末能汇总一周。

为什么要有：周日深谈讲"这一周反复出现、不久还会有影响"的一件事，周六又要先把它让出来（周六不碰）。
这两件事都得知道"过去 7 天每个话题哪几天出现过"，单看当天 36 小时的候选看不出来。

用法（在项目根目录 frontier-daily/ 下；PY=~/.venvs/frontier-daily/bin/python）：
    # 1) 每天跑完 01–03 步（抓取、粗筛归并、选题、事件卡）以后，把这一期并进库
    $PY pipeline/event_db.py ingest --day 2026-11-01
    #    读 测试版/<日期>/ 的 01_获取/prefilter.jsonl、02_选题/candidates.json 和 最终选题.json、
    #    03_事件卡/cards_写稿用.json，有 04_文稿/claude_网页.json 再读网页上的预告（未来节点）。缺哪样就跳过哪样。

    # 2) 补抓的材料（目录里有 01_获取/raw.jsonl，比如定时任务漏了几天、或彩排要过去 7 天）
    $PY pipeline/fetch.py --day 2026-11-01 --since 2026-10-26T00:00:00Z --out-dir <目录>/01_获取
    $PY pipeline/event_db.py prep   --dir <目录>          # 对这个目录粗筛、归并（不写 测试版/）
    $PY pipeline/event_db.py ingest --dir <目录> --label 补抓_1026-1101

    # 3) 汇总一周：话题、出现在哪几天、热度怎么变、有哪些事件卡、未来节点、持续度分
    $PY pipeline/event_db.py week --asof 2026-11-01T06:00Z --md 摘要.md --json 话题.json

    # 4) 周六选题前：算出要留给周日的话题（周六的快讯和深度都不碰它）
    $PY pipeline/event_db.py reserve --asof 2026-10-31T06:00Z

    #   --db 换库目录（默认 测试版/往期事件库/）；--days 汇总几天（默认 7）

库长什么样：<库目录>/批次/<名字>.json，一次 ingest 一个文件（同名覆盖，重复并入不会重复计数）。
    每个批次存：条目（网址、标题、摘要前 400 字、发布时间、来源、层级、粗筛给的主题和地区）、
    我们讲过什么（选题里入选的事件，按网址记）、事件卡（标题、一句话、来源网址、事实条数）、网页上的预告。
    全是 JSON，人能直接打开看；删掉某个批次文件就等于把那天移出库。

一周怎么汇总（week）：
    1. 把库里所有条目按网址去重，只留 as-of 往前 N 天、粗筛保留的；
    2. 用 cluster.py 同一套办法（LaBSE 句向量＋标题专名）重新归并成"事件"（同一件事的几篇报道）；
    3. 再把事件按更宽的线并成"话题"（同一件事前后几天的几个进展，比如"提交上市文件"和"招股书里的风险"）：
       两组之间的平均相似度 ≥ TOPIC_MERGE 才并（平均连接，防止枢纽专名串成一大串），专名加减分和 cluster.py 相同；
    4. 每个话题算：出现在哪几天、每天的热度（当天各独立来源的层级权重之和，不衰减）、独立来源数、
       中外都有没有、对上了哪些事件卡和哪几期讲过、未来节点候选（标题、摘要、事件卡里"下周""11 月 4 日"这类说法）；
    5. 持续度分（0–100，见 persist_score）和周日选题四条标准里程序能判断的三条。第四条"有没有反差能开头"留给选题的人。

不调用任何模型接口，不花钱。LaBSE 模型从本机缓存离线加载（和 cluster.py 一样）。
"""
import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
ROOT = PIPE.parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

from fd_common import LAYER_LABELS, iso, parse_iso, read_jsonl  # noqa: E402
from horizon_borrowed import dedup_url_key  # noqa: E402

DEFAULT_DB = ROOT / "测试版" / "往期事件库"
SCHEMA = "fd-eventdb-batch/1"
UTC = timezone.utc

# ============================ 可改区 ============================
TOPIC_MERGE = 0.64        # 事件并成话题的线（两组事件之间的平均调整后相似度；事件内部是 0.78）。
                          # 11-01 彩排按 10-26–11-01 的 832 条试了 0.62／0.68：0.62 开始把不相干的模型新闻并进来，0.68 拆开了 Anthropic 上市
TOPIC_MAX_EVENTS = 12     # 一个话题最多并几个事件：防止"枢纽"公司把整周的新闻串成一串
LAYER_W = {"primary_intl": 1.5, "primary_cn": 1.5, "media_intl": 1.0, "media_cn": 1.0, "lang_edu": 1.0,
           "community": 0.8, "aggregator": 0.6, "social": 0.4}     # 和 cluster.py 的层级权重一致
SUNDAY_MIN_DAYS = 3       # 周日选题标准一：这一周至少三天出现
DEPTH_MIN_SOURCES = 4     # 标准三（粗估"材料撑得起五层"）：独立来源至少 4 个，且条目至少 6 条
DEPTH_MIN_ITEMS = 6
RELATED_LOW = 0.52        # "相关话题"的线（给选题的人看，不合并）
# ==============================================================


def say(*a):
    print(*a, flush=True)


def ukey(url):
    h, p, path, q = dedup_url_key(url or "")
    return f"{h}{':' + str(p) if p else ''}{path}{'?' + q if q else ''}"


def load_json(p, default=None):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def parse_asof(s):
    """--asof 可以写 2026-11-01（当天 06:00 UTC）或完整时刻 2026-11-01T06:00Z。"""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s or ""):
        return datetime.fromisoformat(s).replace(hour=6, tzinfo=UTC)
    return parse_iso(s)


# ───────────────────────── 1. 并入（ingest） ─────────────────────────
def _item_row(r):
    pf, ex = r.get("pf") or {}, r.get("extra") or {}
    return {"key": ukey(r.get("url")), "url": r.get("url"), "title": r.get("title") or "",
            "summary": (r.get("summary") or "")[:400], "published": r.get("published"),
            "source_id": r.get("source_id"), "source_name": r.get("source_name"), "layer": r.get("layer"),
            "lang": r.get("lang"), "region": ex.get("region"), "operator": ex.get("operator") or r.get("source_id"),
            "relevance": pf.get("relevance"), "topics": pf.get("topics") or [], "subject_region": pf.get("subject_region"),
            "roundup": bool(pf.get("roundup")), "window_exempt": bool(ex.get("window_exempt")),
            "engagement": {k: v for k, v in (r.get("engagement") or {}).items() if v}}


def _event_urls(cands):
    """candidates.json 里每个事件的成员网址（热度前 N、专业雷达、只有社交信号三处都收）。"""
    out = {}
    for pool in ("events", "lang_edu_column", "social_only"):
        for e in cands.get(pool) or []:
            out.setdefault(e["event_id"], [m.get("url") for m in e.get("members") or [] if m.get("url")])
    return out


FUTURE_ZH = re.compile(r"(下周[一二三四五六日天]?|下个?月|本周[一二三四五六日天]|月底|年底|年内|明年|"
                       r"(?<!\d)\d{1,2}\s*月\s*\d{1,2}\s*日|第[一二三四]季度|[一二三四]季度|"
                       r"即将|计划于|预计于|将于|定于)")
FUTURE_EN = re.compile(r"\b(next (week|month|quarter|year)|later this (week|month|year)|"
                       r"(this|next) (Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day|"
                       r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? \d{1,2}(?!\d)|"
                       r"Q[1-4] ?20\d\d|by (the )?end of (the )?(year|month|quarter)|expected to|is set to|plans to|"
                       r"scheduled|deadline|vote|pricing|earnings|launch(es|ing)? (on|in|next))\b", re.I)


def future_snippets(text, width=36):
    """文字里像"未来节点"的说法（下周、11 月 4 日、next week、expected to……）连同前后几十个字，只做候选。"""
    out = []
    for rx in (FUTURE_ZH, FUTURE_EN):
        for m in rx.finditer(text or ""):
            a, b = max(0, m.start() - width), min(len(text), m.end() + width)
            out.append({"hit": m.group(0), "text": re.sub(r"\s+", " ", text[a:b]).strip()})
    seen, uniq = set(), []
    for x in out:
        if x["text"] not in seen:
            seen.add(x["text"])
            uniq.append(x)
    return uniq[:6]


def ingest_dir(src, label, kind, date=None):
    """把一个目录（测试版/<日期>，或补抓目录）并进库，返回批次 dict。"""
    src = Path(src)
    pf = src / "01_获取" / "prefilter.jsonl"
    raw = src / "01_获取" / "raw.jsonl"
    if pf.exists():
        rows = [r for r in read_jsonl(pf) if (r.get("pf") or {}).get("keep")]
    elif raw.exists():
        raise SystemExit(f"{src} 只有 raw.jsonl、还没粗筛：先跑 event_db.py prep --dir {src}")
    else:
        rows = []
        say(f"  注意：{src} 没有 01_获取，只并入选题和事件卡")
    items = [_item_row(r) for r in rows if r.get("url")]
    stats = load_json(src / "01_获取" / "每源统计.json", [])
    cands = load_json(src / "02_选题" / "candidates.json", {}) or {}
    ev_urls = _event_urls(cands)
    lineup = load_json(src / "02_选题" / "最终选题.json") or {}
    cards = load_json(src / "03_事件卡" / "cards_写稿用.json", []) or []
    card_by = {c["event_id"]: c for c in cards}

    covered = []

    def cover(section, eid, title=None, storyline=None):
        if not eid:
            return
        c = card_by.get(eid) or {}
        urls = list(dict.fromkeys((ev_urls.get(eid) or []) + [s.get("url") for s in c.get("sources") or [] if s.get("url")]))
        covered.append({"section": section, "event_id": eid, "title_zh": c.get("title_zh") or title or "",
                        "one_line_zh": c.get("one_line_zh", ""), "storyline": storyline, "urls": urls})
    for sec in ("hot", "brief", "flash", "teaser"):
        for x in lineup.get(sec) or []:
            cover(sec, x.get("event_id"), x.get("title_zh"), x.get("storyline"))
    for p in lineup.get("cn_intl_pairs") or []:
        for side in ("intl_event_id", "cn_event_id"):
            if not any(c["event_id"] == p.get(side) for c in covered):
                cover("cn_intl", p.get(side))
    deep = lineup.get("deep") or {}            # 周六深度、周日深谈（新选题格式）
    for eid in deep.get("event_ids") or ([deep["event_id"]] if deep.get("event_id") else []):
        if not any(c["event_id"] == eid for c in covered):
            cover(deep.get("kind") or "deep", eid, deep.get("title_zh"))
    if deep:                                   # 专题卡本身：网址＝选题里的材料＋专题卡的来源
        cid = deep.get("card_id") or "D1"
        c = card_by.get(cid) or {}
        urls = [m.get("url") if isinstance(m, dict) else m for m in deep.get("materials") or []]
        urls = list(dict.fromkeys([u for u in urls if u] + [x.get("url") for x in c.get("sources") or [] if x.get("url")]))
        covered.append({"section": deep.get("kind") or "deep", "event_id": cid, "title_zh": deep.get("title_zh") or c.get("title_zh", ""),
                        "one_line_zh": c.get("one_line_zh", ""), "storyline": None, "urls": urls})

    card_rows = []
    for c in cards:
        text = " ".join(str(f.get(k) or "") for lst in (c.get("facts") or [], c.get("numbers") or []) for f in lst
                        for k in ("text_zh", "text_en", "meaning_zh", "quote"))
        card_rows.append({"event_id": c["event_id"], "title_zh": c.get("title_zh", ""), "one_line_zh": c.get("one_line_zh", ""),
                          "status": c.get("status"), "n_facts": len(c.get("facts") or []), "n_numbers": len(c.get("numbers") or []),
                          "urls": [s.get("url") for s in c.get("sources") or [] if s.get("url")],
                          "future": future_snippets(text),
                          "file": str((src / "03_事件卡" / "cards_写稿用.json").resolve())})
    web = load_json(src / "04_文稿" / "claude_网页.json") or {}
    watch = [{k: w.get(k) for k in ("when_zh", "date_iso", "sort_date", "status", "text_zh", "story")}
             for w in (web.get("page") or {}).get("watch") or []]
    fetched_at = max((s.get("newest") or "" for s in stats), default="") if stats else ""
    batch = {"schema": SCHEMA, "label": label, "kind": kind, "date": date,
             "ingested_at": iso(datetime.now(UTC)), "src_dir": str(src.resolve()),
             "n_items": len(items), "newest_item": fetched_at or max((i["published"] or "" for i in items), default=""),
             "items": items, "covered": covered, "cards": card_rows, "watch": watch}
    return batch


def save_batch(db, batch):
    out = Path(db) / "批次" / (batch["label"] + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(batch, ensure_ascii=False, indent=1), encoding="utf-8")
    say(f"并入 {batch['label']}（{batch['kind']}）：条目 {batch['n_items']}、讲过 {len(batch['covered'])}、"
        f"事件卡 {len(batch['cards'])}、预告 {len(batch['watch'])} → {out}")
    return out


def load_batches(db):
    d = Path(db) / "批次"
    if not d.exists():
        raise SystemExit(f"库是空的：{d}（先 ingest）")
    out = []
    for p in sorted(d.glob("*.json")):
        b = json.loads(p.read_text(encoding="utf-8"))
        if b.get("schema") == SCHEMA:
            out.append(b)
    return out


# ───────────────────────── 2. 补抓目录的粗筛、归并（prep） ─────────────────────────
def prep(src, top=5000):
    """对补抓目录跑 prefilter.py 和 cluster.py（两者只认 测试版/<日期>，这里把它们的目录换成 src，不改那两个文件）。"""
    import prefilter
    import cluster
    src = Path(src)
    prefilter.run_dir = lambda day: src
    cluster.run_dir = lambda day: src
    argv = sys.argv
    try:
        sys.argv = ["prefilter.py", "--day", "prep"]
        prefilter.main()
        sys.argv = ["cluster.py", "--day", "prep", "--top", str(top)]
        cluster.main()
    finally:
        sys.argv = argv


# ───────────────────────── 3. 汇总一周（week） ─────────────────────────
def gather(batches, since, asof, covered_before=None):
    """库里所有条目按网址去重，只留 [since, asof] 之间发布的；讲过的（covered）只算 covered_before 之前那几期的。"""
    items = {}
    for b in batches:
        for it in b["items"]:
            p = it.get("published")
            if not p:
                continue
            t = parse_iso(p)
            if not (since <= t <= asof) or it.get("window_exempt"):
                continue
            old = items.get(it["key"])
            if not old or len(it.get("summary") or "") > len(old.get("summary") or ""):
                items[it["key"]] = dict(it, _batches=sorted(set((old or {}).get("_batches", [])) | {b["label"]}))
            else:
                old["_batches"] = sorted(set(old["_batches"]) | {b["label"]})
    cov, cards, watch = [], [], []
    cut = (covered_before or asof).date().isoformat()
    for b in batches:
        d = b.get("date")
        if b.get("covered") and d and d < cut:
            cov += [dict(c, date=d, batch=b["label"]) for c in b["covered"]]
        if d is None or d <= asof.date().isoformat():
            cards += [dict(c, date=d, batch=b["label"]) for c in b.get("cards") or []]
            watch += [dict(w, date=d, batch=b["label"]) for w in b.get("watch") or []]
    return list(items.values()), cov, cards, watch


def _as_pipeline_item(it):
    """库里的条目 → cluster.py 认的形状（只补它要读的字段）。"""
    return {"id": it["key"], "title": it["title"], "summary": it.get("summary") or "", "url": it["url"],
            "published": it["published"], "source_id": it.get("source_id"), "source_name": it.get("source_name"),
            "layer": it.get("layer"), "lang": it.get("lang"), "engagement": it.get("engagement") or {},
            "extra": {"region": it.get("region"), "operator": it.get("operator")},
            "pf": {"relevance": it.get("relevance") or "other", "topics": it.get("topics") or [],
                   "subject_region": it.get("subject_region") or "none", "roundup": it.get("roundup")}}


def day_of(ts, tz_hours=0.0):
    return (parse_iso(ts) + timedelta(hours=tz_hours)).date().isoformat()


def build_topics(items, tz_hours=0.0):
    """条目 → 事件（cluster.py 的线）→ 话题（TOPIC_MERGE）。返回 [话题]，每个话题带它的事件和条目。"""
    import numpy as np
    import cluster as C
    rows = [_as_pipeline_item(it) for it in items if not it.get("roundup")]
    if not rows:
        return []
    E = C.encode([C.embed_text(r) for r in rows])
    toks = [C.specific_tokens(r["title"]) for r in rows]
    groups = C.agglomerate(E, toks)                       # 事件：和每天的归并同一条线
    events = []
    for g in groups:
        cent = E[g].sum(0)
        cent /= np.linalg.norm(cent)
        tc = Counter(t for i in g for t in toks[i])
        events.append({"idx": g, "cent": cent, "core": C.core_tokens(tc, len(g)) if len(g) > 1 else set(toks[g[0]]),
                       "tok": tc})
    # 话题：把事件当成一个个"点"再并一次。用"平均连接"（两组之间所有事件两两相似度的平均）而不是质心：
    # 11-01 彩排试过质心法，"谷歌""Claude"这类枢纽专名会把一周的模型新闻串成一大串；平均连接不会。
    # 两两相似度 = 事件质心余弦 ＋ cluster.py 的专名加减分（用事件的核心专名）。一组最多 TOPIC_MAX_EVENTS 个事件。
    tgroups = avg_link([e["cent"] for e in events], [e["core"] for e in events], TOPIC_MERGE, TOPIC_MAX_EVENTS)
    topics = [sorted(tg, key=lambda k: -len(events[k]["idx"])) for tg in tgroups]
    by_key = {it["key"]: it for it in items}
    out = []
    for tg in topics:
        evs = []
        for k in tg:
            mem = [by_key[rows[i]["id"]] for i in events[k]["idx"]]
            evs.append({"items": mem, "key_terms": [t for t, _ in events[k]["tok"].most_common(5)]})
        cent = sum(events[k]["cent"] * len(events[k]["idx"]) for k in tg)
        out.append({"events": evs, "_cent": cent / np.linalg.norm(cent),
                    "_core": set().union(*(events[k]["core"] for k in tg))})
    return out


def avg_link(cents, cores, thr, maxsize):
    """平均连接凝聚聚类：每次并平均相似度最高的两组，直到最高的也低于 thr；并完超过 maxsize 个的那一对跳过。"""
    import numpy as np
    import cluster as C
    n = len(cents)
    if n == 0:
        return []
    V = np.stack(cents)
    S = V @ V.T
    for i in range(n):
        for j in range(i + 1, n):
            a = C.token_adjust(cores[i], cores[j])
            if a:
                S[i, j] += a
                S[j, i] += a
    np.fill_diagonal(S, -9)
    size = np.ones(n)
    mem = [[i] for i in range(n)]
    act = np.ones(n, dtype=bool)
    while True:
        k = int(np.argmax(S))
        i, j = divmod(k, n)
        if S[i, j] < thr:
            break
        if len(mem[i]) + len(mem[j]) > maxsize:
            S[i, j] = S[j, i] = -9
            continue
        row = (S[i] * size[i] + S[j] * size[j]) / (size[i] + size[j])
        size[i] += size[j]
        mem[i] += mem[j]
        act[j] = False
        S[j, :] = -9
        S[:, j] = -9
        row[~act] = -9
        row[i] = -9
        S[i, :] = row
        S[:, i] = row
    return [mem[i] for i in np.where(act)[0]]


def _title(mem, lang):
    pri = {"media_intl": 0, "media_cn": 0, "lang_edu": 0, "primary_intl": 1, "primary_cn": 1, "aggregator": 2, "community": 3, "social": 4}
    c = [m for m in mem if m.get("lang") == lang and 6 <= len(m["title"]) <= (80 if lang == "zh" else 160)]
    return sorted(c, key=lambda m: (pri.get(m.get("layer"), 9), m["published"]))[0]["title"] if c else ""


def describe(topic, cov, cards, watch, asof, days, tz_hours=0.0):
    """一个话题的各项：几天、每天热度、来源、讲过、事件卡、未来节点、持续度分。"""
    mem = [m for e in topic["events"] for m in e["items"]]
    keys = {m["key"] for m in mem}
    ops = {}
    per_day = defaultdict(dict)
    for m in mem:
        d = day_of(m["published"], tz_hours)
        op = m.get("operator") or m.get("source_id")
        w = LAYER_W.get(m.get("layer"), 0.5)
        per_day[d][op] = max(per_day[d].get(op, 0), w)
        if w > ops.get(op, (0, None))[0]:
            ops[op] = (w, m.get("layer"))
    window = [(asof - timedelta(days=k)).date().isoformat() for k in range(days - 1, -1, -1)]
    heat = {d: round(sum(per_day[d].values()), 2) for d in window if d in per_day}
    # 只有社交信号的那天算半天（AINews 转述的帖子不等于正式报道）
    day_score = sum(1.0 if any(LAYER_W.get(m.get("layer"), 0) > 0.4 for m in mem if day_of(m["published"], tz_hours) == d) else 0.5
                    for d in heat)
    regions = {m.get("region") for m in mem if m.get("layer") != "social"}
    ai_share = round(sum(1 for m in mem if m.get("relevance") in ("ai", "lang_edu")) / len(mem), 2)
    n_src = len(ops)
    n_primary = sum(1 for w, lay in ops.values() if lay in ("primary_intl", "primary_cn"))
    n_rich = sum(1 for m in mem if len(m.get("summary") or "") >= 200)
    kt = Counter(t for e in topic["events"] for t in e["key_terms"])
    # 讲过 / 事件卡：按网址对
    said = [c for c in cov if keys & {ukey(u) for u in c.get("urls") or []}]
    tcards = [c for c in cards if keys & {ukey(u) for u in c.get("urls") or []}]
    # 未来节点候选：条目标题和摘要、对上的事件卡、对上的网页预告
    fut = []
    for m in sorted(mem, key=lambda m: m["published"], reverse=True):
        for s in future_snippets((m["title"] or "") + "。" + (m.get("summary") or "")):
            fut.append(dict(s, src=m.get("source_name"), date=m["published"][:10]))
    for c in tcards:
        for s in c.get("future") or []:
            fut.append(dict(s, src="事件卡 " + c["event_id"], date=c.get("date")))
    card_ids = {c["event_id"] for c in tcards}
    for w in watch:
        if w.get("story") in card_ids:
            fut.append({"hit": w.get("when_zh"), "text": w.get("text_zh"), "src": "网页预告", "date": w.get("date"),
                        "date_iso": w.get("date_iso")})
    seen, fut2 = set(), []
    for f in fut:
        if f["text"] not in seen:
            seen.add(f["text"])
            fut2.append(f)
    last2 = {(asof - timedelta(days=k)).date().isoformat() for k in (0, 1)}
    last3 = last2 | {(asof - timedelta(days=2)).date().isoformat()}
    score, parts = persist_score(day_score, bool(set(heat) & last2), bool(set(heat) & last3), n_src, bool(fut2),
                                 n_primary, n_rich, len(mem))
    top_ev = max(topic["events"], key=lambda e: len(e["items"]))
    return {
        # 代表标题取最大那个事件的（没有中文标题就只有英文，免得拿别的事件的中文标题顶替）
        "title_zh": _title(top_ev["items"], "zh"),
        "title_en": _title(top_ev["items"], "en") or ("" if _title(top_ev["items"], "zh") else _title(mem, "en")),
        "key_terms": [t for t, _ in kt.most_common(6)],
        "days": sorted(heat), "n_days": len(heat), "day_score": day_score, "heat_by_day": heat,
        "n_events": len(topic["events"]), "n_items": len(mem), "n_sources": n_src, "n_primary": n_primary,
        "cn_and_intl": {"cn", "intl"} <= regions, "ai_share": ai_share,
        "first_seen": min(m["published"] for m in mem), "last_seen": max(m["published"] for m in mem),
        "covered": [{"date": c["date"], "section": c["section"], "title_zh": c["title_zh"]} for c in said],
        "cards": [{"date": c.get("date"), "event_id": c["event_id"], "title_zh": c["title_zh"], "n_facts": c["n_facts"],
                   "file": c.get("file")} for c in tcards],
        "future": fut2[:8],
        "persist": score, "persist_parts": parts,
        "sunday_checks": {
            "一周至少三天出现": day_score >= SUNDAY_MIN_DAYS,
            "以 AI 为主": ai_share >= 0.5,
            "未来一到四周有节点（候选，要人或模型确认）": bool(fut2),
            "材料撑得起五层（粗估）": n_src >= DEPTH_MIN_SOURCES and len(mem) >= DEPTH_MIN_ITEMS,
            "有反差能开头": None,
        },
        "events": [{"title": _title(e["items"], "zh") or _title(e["items"], "en") or e["items"][0]["title"],
                    "n_items": len(e["items"]), "days": sorted({day_of(m["published"], tz_hours) for m in e["items"]}),
                    "urls": [m["url"] for m in sorted(e["items"], key=lambda m: m["published"])][:12]}
                   for e in sorted(topic["events"], key=lambda e: min(m["published"] for m in e["items"]))],
        "item_keys": sorted(keys),
    }


def persist_score(day_score, recent2, recent3, n_src, has_future, n_primary, n_rich, n_items):
    """持续度分 0–100：天数 40、近两天还在 20、来源多寡 20、有未来节点 10、材料厚度 10。
    天数封顶 5 天；来源按 log 算（15 个独立来源满分）；材料厚度 =（一手来源 ×2 ＋ 摘要够长的条目）/ 20。"""
    p = {"天数": round(min(day_score, 5) / 5 * 40, 1),
         "近两天还在": 20.0 if recent2 else (10.0 if recent3 else 0.0),
         "来源多寡": round(min(1.0, math.log2(1 + n_src) / math.log2(16)) * 20, 1),
         "未来节点": 10.0 if has_future else 0.0,
         "材料厚度": round(min(1.0, (n_primary * 2 + n_rich) / 20) * 10, 1)}
    return round(sum(p.values()), 1), p


def week(db, asof, days=7, tz_hours=0.0, covered_before=None, min_items=2):
    batches = load_batches(db)
    since = asof - timedelta(days=days)
    items, cov, cards, watch = gather(batches, since, asof, covered_before)
    say(f"库里 {len(batches)} 个批次；{iso(since)} 到 {iso(asof)} 之间的条目 {len(items)} 条；归并中……")
    topics = build_topics(items, tz_hours)
    out = [dict(describe(t, cov, cards, watch, asof, days, tz_hours), _cent=t["_cent"], _core=t["_core"]) for t in topics]
    out = [t for t in out if t["n_items"] >= min_items]
    out.sort(key=lambda t: (-t["persist"], -t["n_sources"]))
    for i, t in enumerate(out, 1):
        t["topic_id"] = f"T{i:03d}"
    related_topics(out)
    for t in out:
        t.pop("_cent", None)
        t.pop("_core", None)
    return {"asof": iso(asof), "since": iso(since), "days": days, "n_items": len(items), "n_batches": len(batches),
            "batches": [{"label": b["label"], "kind": b["kind"], "date": b.get("date"), "n_items": b["n_items"]} for b in batches],
            "params": {"TOPIC_MERGE": TOPIC_MERGE, "TOPIC_MAX_EVENTS": TOPIC_MAX_EVENTS, "SUNDAY_MIN_DAYS": SUNDAY_MIN_DAYS},
            "topics": out}


def related_topics(topics, low=RELATED_LOW, k=4):
    """每个话题列出几个"相关话题"（质心余弦＋专名加减分 ≥ low）：周日深谈"串上相关的事"时从这里找线索。"""
    import cluster as C
    for t in topics:
        sims = []
        for o in topics:
            if o is t:
                continue
            s = float(t["_cent"] @ o["_cent"]) + C.token_adjust(t["_core"], o["_core"])
            if s >= low:
                sims.append((s, o))
        sims.sort(key=lambda x: -x[0])
        t["related"] = [{"topic_id": o["topic_id"], "title": o["title_zh"] or o["title_en"], "sim": round(s, 2),
                         "days": o["days"], "n_items": o["n_items"]} for s, o in sims[:k]]


def sunday_candidates(w, n=3):
    """周日深谈候选：以 AI 为主、过了程序能判断的标准一和标准三的话题，按持续度排；不够就放宽到只看标准一。
    这一周已经做过周末深度的话题（讲过的记录里有 saturday_deep）跳过。"""
    ck = lambda t, k: t["sunday_checks"][k]   # noqa: E731
    # 已经做过周末深度／深谈的话题（比如周六刚讲透的）不再当周日候选
    deep_done = lambda t: any(c.get("section") in ("saturday_deep", "sunday_deep", "deep") for c in t.get("covered") or [])   # noqa: E731
    pool = [t for t in w["topics"] if not deep_done(t)]
    ok = [t for t in pool if ck(t, "一周至少三天出现") and ck(t, "以 AI 为主") and ck(t, "材料撑得起五层（粗估）")]
    more = [t for t in pool if ck(t, "一周至少三天出现") and ck(t, "以 AI 为主") and t not in ok]
    return (ok + more)[:n]


def reserve(w):
    """留给周日的话题：周日候选里的第一个。返回它的条目网址键（周六选题按这个排除）。"""
    c = sunday_candidates(w, 1)
    return c[0] if c else None


def overlaps(event_members_urls, topic):
    keys = set(topic.get("item_keys") or [])
    return bool(keys & {ukey(u) for u in event_members_urls if u})


# ───────────────────────── 4. 给人看的摘要 ─────────────────────────
def spark(heat, window):
    bars = "▁▂▃▄▅▆▇█"
    mx = max(heat.values()) if heat else 1
    return "".join(bars[min(7, int(heat[d] / mx * 7))] if d in heat else "·" for d in window)


def to_md(w, top=15):
    asof = parse_iso(w["asof"])
    window = [(asof - timedelta(days=k)).date().isoformat() for k in range(w["days"] - 1, -1, -1)]
    L = [f"# 往期事件库 · 一周汇总（截至 {w['asof']}）", "",
         f"- 范围：{w['since']} 到 {w['asof']}，库里 {w['n_batches']} 个批次（" +
         "、".join(f"{b['label']}·{b['kind']}·{b['n_items']} 条" for b in w["batches"]) + f"），窗口内条目 {w['n_items']} 条。",
         f"- 话题：事件之间平均调整后相似度 ≥ {w['params']['TOPIC_MERGE']} 并成话题（事件内部 0.78，平均连接），一个话题最多 {w['params']['TOPIC_MAX_EVENTS']} 个事件。",
         "- 持续度分 0–100：天数 40（封顶 5 天，只有社交信号的那天算半天）、近两天还在 20、独立来源多寡 20、有未来节点候选 10、材料厚度 10。",
         "- 热度条：从左到右是 " + window[0][5:] + " 到 " + window[-1][5:] + "，每天当天各独立来源的层级权重之和（不衰减）；· 是那天没出现。",
         "- 周日标准：①一周至少三天出现 ②未来一到四周有节点 ③材料撑得起五层 ④有反差能开头。程序只判断①③（另要求 AI 相关条目过半），②给候选句，④留给选题的人。",
         "", "## 周日深谈候选（程序排的，选题时再判断②④）", ""]
    for i, t in enumerate(sunday_candidates(w), 1):
        L.append(f"{i}. **{t['title_zh'] or t['title_en']}**（{t['topic_id']}，持续度 {t['persist']}，{t['n_days']} 天，"
                 f"{t['n_sources']} 个独立来源，{t['n_items']} 条）")
    L += ["", f"## 持续度前 {top} 的话题", "",
          "| # | 话题 | 持续度 | 天数 | 热度（逐日） | 来源 | 中外 | 讲过 | 事件卡 | 标准①③ |", "|---:|---|---:|---:|---|---:|:---:|---|---:|---|"]
    for t in w["topics"][:top]:
        ck = t["sunday_checks"]
        L.append(f"| {t['topic_id']} | {(t['title_zh'] or t['title_en'])[:46]} | {t['persist']} | {t['n_days']} | `{spark(t['heat_by_day'], window)}` | "
                 f"{t['n_sources']} | {'✓' if t['cn_and_intl'] else ''} | {'、'.join(sorted({c['date'][5:] for c in t['covered']})) or ''} | "
                 f"{len(t['cards'])} | {'①' if ck['一周至少三天出现'] else ''}{'③' if ck['材料撑得起五层（粗估）'] else ''} |")
    L += ["", "## 前几个话题的细节", ""]
    for t in w["topics"][:8]:
        L += [f"### {t['topic_id']} {t['title_zh'] or t['title_en']}", "",
              f"- 英文：{t['title_en']}" if t["title_en"] and t["title_zh"] else None,
              f"- 专名：{'、'.join(t['key_terms'])}；首见 {t['first_seen'][:16]}，最近 {t['last_seen'][:16]}",
              f"- 逐日热度：" + "，".join(f"{d[5:]} {h}" for d, h in t["heat_by_day"].items()),
              f"- 持续度 {t['persist']} ＝ " + " ＋ ".join(f"{k} {v}" for k, v in t["persist_parts"].items()),
              f"- 讲过：" + ("；".join(f"{c['date']} {c['section']}「{c['title_zh']}」" for c in t["covered"]) or "没有"),
              f"- 事件卡：" + ("；".join(f"{c['date']} {c['event_id']}「{c['title_zh']}」{c['n_facts']} 条事实" for c in t["cards"]) or "没有"),
              f"- AI 相关条目占 {int(t['ai_share'] * 100)}%；相关话题（可以串进来讲的线索）：" +
              ("；".join(f"{r['topic_id']}「{r['title'][:40]}」{r['sim']}" for r in t.get("related") or []) or "没有"),
              "- 包含的事件（按首次出现）："]
        for e in t["events"][:8]:
            L.append(f"  - {'、'.join(d[5:] for d in e['days'])}：{e['title'][:90]}（{e['n_items']} 条）")
        if t["future"]:
            L.append("- 未来节点候选（程序按“下周”“11 月 4 日”“next week”这类说法找的，要人确认）：")
            for f in t["future"][:5]:
                L.append(f"  - 「{f['hit']}」…{f['text']}…（{f.get('src')}，{f.get('date')}）")
        L.append("")
    return "\n".join(x for x in L if x is not None)


# ───────────────────────── 命令行 ─────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["ingest", "prep", "week", "reserve", "list"])
    ap.add_argument("--db", default=str(DEFAULT_DB), help="库目录（默认 测试版/往期事件库/）")
    ap.add_argument("--day", help="ingest：并入 测试版/<日期>")
    ap.add_argument("--dir", help="ingest / prep：并入或粗筛这个目录（补抓材料、彩排）")
    ap.add_argument("--label", help="ingest --dir 的批次名（默认用目录名）")
    ap.add_argument("--kind", default=None, help="批次种类：issue（正式一期）、backfill（补抓）、rehearsal（彩排）")
    ap.add_argument("--date", help="ingest --dir：这一批是哪一期（有选题时，讲过的事按这个日期记）")
    ap.add_argument("--asof", help="week / reserve：截至哪个时刻（2026-11-01 = 当天 06:00 UTC）")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--tz-hours", type=float, default=0.0, help="按哪个时区分天（伦敦冬令时 0；北京 8）")
    ap.add_argument("--covered-before", help="只算这一天之前讲过的（默认 = asof 那天）")
    ap.add_argument("--md", help="week：摘要写到这个 Markdown 文件")
    ap.add_argument("--json", help="week：全部话题写到这个 JSON 文件")
    a = ap.parse_args(argv)

    if a.cmd == "prep":
        if not a.dir:
            ap.error("prep 要给 --dir")
        prep(a.dir)
        return 0
    if a.cmd == "ingest":
        if a.day:
            b = ingest_dir(ROOT / "测试版" / a.day, a.label or a.day, a.kind or "issue", a.date or a.day)
        elif a.dir:
            b = ingest_dir(a.dir, a.label or Path(a.dir).name, a.kind or "backfill", a.date)
        else:
            ap.error("ingest 要给 --day 或 --dir")
        save_batch(a.db, b)
        return 0
    if a.cmd == "list":
        for b in load_batches(a.db):
            say(f"{b['label']:<24} {b['kind']:<10} {b.get('date') or '—':<11} 条目 {b['n_items']:>5}  讲过 {len(b['covered']):>3}  "
                f"事件卡 {len(b['cards']):>3}  最新 {b.get('newest_item', '')[:16]}")
        return 0
    if not a.asof:
        ap.error("week / reserve 要给 --asof")
    asof = parse_asof(a.asof)
    cb = parse_asof(a.covered_before) if a.covered_before else None
    w = week(a.db, asof, a.days, a.tz_hours, cb)
    if a.cmd == "reserve":
        r = reserve(w)
        if not r:
            say("这一周没有过标准一（至少三天出现）的话题：周六不用让，周日退回普通热点讲")
            return 0
        say(f"留给周日：{r['title_zh'] or r['title_en']}（{r['topic_id']}，持续度 {r['persist']}，{r['n_days']} 天，"
            f"{r['n_sources']} 个来源）")
        if a.json:
            Path(a.json).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        return 0
    md = to_md(w)
    if a.md:
        Path(a.md).write_text(md, encoding="utf-8")
        say("写入", a.md)
    if a.json:
        Path(a.json).write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
        say("写入", a.json)
    if not a.md:
        say(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
