#!/usr/bin/env python3
"""生成某一天的网页 v3 配置（v3.2）：选题 + 事件卡 + 网页稿（含 page）+ 配图 → site/tools/v3_issues/<日期>.py

以前每期配置（主题色、今日数字、预告看板、对照、图表、配图说明……）是手写的；现在由写稿的 Claude 在网页稿的
page 对象里给出（格式见 pipeline/prompts/写稿_网页.md 的《page 怎么写》），这个程序负责核对、整理、写成配置，
组装脚本 build_v3.py 照旧读配置。新的一天不再需要手写配置，也不再沿用 v2 的配置。

用法（在项目根目录 frontier-daily/ 下）：
    ~/.venvs/frontier-daily/bin/python site/tools/make_issue_v3.py --day 2026-11-01
    … --lenient                 # 核对不上的数字不让整次失败，而是去掉那一项并提醒（流水线最后一级兜底用）
    … --images 06_配图/v3.1      # 配图在别的文件夹
    … --podcast 05_配音/某文件夹  # 指定播客（不写就自动找 05_配音 下最新的、带 episode.mp3 和 chapters.json 的文件夹）
    … --out 某路径.py            # 配置写到别处（测试用）
    … --fixture site/tools/fixtures/2026-10-31.json   # 旧的日子还没有 page：用这份补上 page 和选题里缺的 theme（测试用）

周末两版（11-01 起）：网页稿 sections 里没有头条、要闻，多一个 kind 为 "deep" 的条目（周六深度、周日深谈那一题，id 是专题卡编号 D1），
写法见 pipeline/prompts/写稿_网页_周末.md。这里只多认它几处：story_charts 可以写给它；它和头条、要闻一样要配图。
图表上写的 "layer"（中文层名）原样带过去，页面（site/v3/app.js 的 secDeep）按它把图放到那一层下面。
11-01 晚改版面（v3_site.py 的 WEEKEND）：周六今日数字最多 4 个；周日不单列今日数字（page.numbers 写了也去掉并提醒，
关键数字写在深谈那一条的 numbers 里、带 layer）；两天都没有今日一词，改成深度那一条里的 glossary（名词解释，3–5 个）。
这里只提醒、不拦：周日缺 question / conclusion、名词解释个数不在区间里、某一层的关键数字超过 3 个、层名写错。

读的文件（都在 测试版/<日期>/ 下）：
    02_选题/最终选题.json        theme {accent, why_zh}、storylines、cn_intl_pairs（含 relation）、term；缺了也能跑
    03_事件卡/cards_写稿用.json   核对的唯一依据
    04_文稿/claude_网页.json      正文 + page（numbers、watch、pairs、charts、story_charts、flash_chart、term_like、images）
    06_配图/                      card.png、term.png、e001.png……（按事件号小写命名，png / jpg / webp 都认）

核对规则（和 build_v3.py 一致，再严一点）：
    * 每个 ref = [事件号, "F3"/"N2", 核对片段]，核对片段必须原样出现在那一条里；
    * 页面上显示的每个数字（今日数字、图表数值、图表和数字卡里文字中的数字）都必须能在相关事件卡里找到
      （允许 亿↔B、万亿↔T 这类 10 的整数次方换算）。找不到就当作“可能编造的数字”：默认整次失败（退出码 1），
      --lenient 时去掉那一项并提醒。
    * 其余对不上的（预告某条的出处、对照里不在稿件中的条目、缺图、没写的图表）一律去掉那一项并提醒，页面照常。
预告看板按 date_iso / sort_date 排先后，最多 5 条；缺图的条目在页面上自动换成主题色的抽象封面。
"""
import argparse
import importlib.util
import json
import os
import pprint
import re
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ISSUES_ROOT = os.path.join(ROOT, "测试版")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SITE = load_module(os.path.join(HERE, "v3_site.py"), "v3_site")
CHART_TYPES = ("bars", "dumbbell", "steps", "timeline", "graph")
WATCH_STATUS = ("rumor", "teaser", "scheduled", "reported")
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
FIELDS = ("text_zh", "text_en", "quote", "value", "unit", "meaning_zh", "meaning_en", "compare_zh")   # 与 build_v3.ref() 相同

WARN, ERR = [], []


def warn(msg):
    WARN.append(msg)
    print("提醒：" + msg)


def err(msg):
    ERR.append(msg)
    print("错误：" + msg)


# ---------------------------------------------------------------- 核对
class Checker:
    def __init__(self, cards):
        self.cards = {c["event_id"]: c for c in cards}

    def entry(self, r):
        """ref → (那一条的全部文字, 出错原因)。"""
        if not isinstance(r, (list, tuple)) or len(r) != 3:
            return None, "出处格式不对（应为 [事件号, F/N 条目, 核对片段]）：%r" % (r,)
        ev, key, check = r
        card = self.cards.get(ev)
        if not card:
            return None, "事件卡里没有 %s" % ev
        m = re.fullmatch(r"([FN])(\d+)", str(key))
        if not m:
            return None, "%s 的条目 %r 不是 F数字 或 N数字" % (ev, key)
        lst = card.get("facts" if m.group(1) == "F" else "numbers") or []
        i = int(m.group(2))
        if i >= len(lst):
            return None, "%s 只有 %d 条 %s，没有 %s" % (ev, len(lst), "facts" if m.group(1) == "F" else "numbers", key)
        text = " ".join(str(lst[i].get(k) or "") for k in FIELDS)
        if not check or str(check) not in text:
            return None, "%s %s 里找不到核对片段「%s」" % (ev, key, check)
        return text, None

    def card_text(self, ev):
        c = self.cards.get(ev) or {}
        parts = [c.get("title_zh", ""), c.get("title_en", ""), c.get("one_line_zh", ""), c.get("one_line_en", "")]
        for lst in (c.get("facts") or [], c.get("numbers") or []):
            for e in lst:
                parts += [str(e.get(k) or "") for k in FIELDS]
        return " ".join(parts)


NUM = re.compile(r"\d+(?:\.\d+)?")


def nums_in(text):
    t = re.sub(r"(?<=\d),(?=\d{3})", "", str(text or ""))
    return [float(x) for x in NUM.findall(t)]


def num_found(v, pool):
    """v 能不能在 pool（一串数字）里找到；允许 10 的整数次方换算（200 亿美元 ↔ $20B，1.25 万亿 ↔ $1.25T）。"""
    try:
        v = abs(float(v))
    except (TypeError, ValueError):
        return False
    for c in pool:
        for f in (1, 10, 0.1, 100, 0.01, 1000, 0.001, 1e4, 1e-4):
            x = c * f
            if (v == 0 and x == 0) or (v and abs(x - v) <= max(1e-9, abs(v) * 0.002)):
                return True
    return False


def loose_nums(text):
    """文字里要核对的数字：忽略 1 位的序号式小整数（第一、3 种、两个……这类太常见，核对没有意义）。"""
    return [x for x in nums_in(text) if not (x < 10 and float(x).is_integer())]


# ---------------------------------------------------------------- 小工具
def rel_or_abs(path, base):
    path = os.path.abspath(path)
    try:
        r = os.path.relpath(path, base)
        return r if not r.startswith("..") else path
    except ValueError:
        return path


def parse_day(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def guess_date(when_zh, day):
    """读不出 sort_date 时，从“11 月 4 日”“12 月”这类说法估一个日子（只用来排序）。"""
    m = re.search(r"(\d{1,2})\s*月(?:\s*(\d{1,2})\s*日)?", when_zh or "")
    if not m:
        return None
    mon, d_ = int(m.group(1)), int(m.group(2) or 15)
    y = day.year + (1 if mon < day.month else 0)
    try:
        return date(y, mon, d_)
    except ValueError:
        return None


def find_podcast(issue):
    base = os.path.join(issue, "05_配音")
    if not os.path.isdir(base):
        return None
    cands = []
    for d in os.listdir(base):
        p = os.path.join(base, d)
        if os.path.isfile(os.path.join(p, "episode.mp3")) and os.path.isfile(os.path.join(p, "chapters.json")) and not d.startswith("视频"):
            # 优先：混好音效的成品 > 主声音（不是 MiMo 备用）> 最新
            cands.append(("带音效" in d, "mimo" not in d.lower(), os.path.getmtime(os.path.join(p, "episode.mp3")), d))
    return "05_配音/" + sorted(cands)[-1][3] if cands else None


# ---------------------------------------------------------------- 各部分
def make_numbers(page, ck, stories, lenient, cap=5):
    out = []
    for i, n in enumerate(page.get("numbers") or []):
        tag = "今日数字第 %d 个（%s）" % (i + 1, n.get("story"))
        if n.get("story") not in stories:
            warn(tag + "：链接的条目不在稿件里，去掉")
            continue
        probs = []
        text, why = ck.entry(n.get("ref"))
        if why:
            probs.append(why)
        zh, en = dict(n.get("zh") or {}), dict(n.get("en") or {})
        if "to" not in zh:
            probs.append("缺 zh.to（显示的数值）")
        elif text is not None:   # 中文、英文两种口径显示的数值都要各自核对
            for lab, v in (("中文", zh.get("to")), ("英文", en.get("to", zh.get("to")))):
                if not num_found(v, nums_in(text)):
                    probs.append("%s显示的数值 %s 在 %s 里找不到" % (lab, v, n.get("ref")))
        en.setdefault("to", zh.get("to"))
        ch = n.get("change") or None
        if ch and ch.get("before") is not None:
            t2, why2 = ck.entry(ch.get("ref"))
            if why2:
                probs.append("“之前”值：" + why2)
            else:
                for v in (ch["before"], ch.get("before_en", ch["before"])):
                    if not num_found(v, nums_in(t2)):
                        probs.append("“之前”值 %s 在出处里找不到" % v)
        pool = nums_in(ck.card_text(n["story"]) + " " + ck.card_text((n.get("ref") or [""])[0]))
        if n.get("sub_ref"):
            t3, why3 = ck.entry(n["sub_ref"])
            if why3:
                warn(tag + "：小字的出处对不上（%s），去掉小字" % why3)
                n = {k: v for k, v in n.items() if k not in ("sub_zh", "sub_en", "sub_ref")}
            else:
                pool += nums_in(ck.card_text(n["sub_ref"][0]))
        for k in ("label_zh", "label_en", "sub_zh", "sub_en"):
            bad = [x for x in loose_nums(n.get(k)) if not num_found(x, pool)]
            if bad:
                probs.append("%s 里的数字 %s 在事件卡里找不到" % (k, "、".join("%g" % x for x in bad)))
        if probs:
            (warn if lenient else err)(tag + "：" + "；".join(probs) + ("，去掉这一项" if lenient else ""))
            continue
        x = {"story": n["story"], "ref": list(n["ref"]), "zh": zh, "en": en,
             "label_zh": n.get("label_zh", ""), "label_en": n.get("label_en", "")}
        for k in ("sub_zh", "sub_en"):
            if n.get(k):
                x[k] = n[k]
        if n.get("sub_ref"):
            x["sub_ref"] = list(n["sub_ref"])
        d = n.get("dir") if n.get("dir") in ("up", "down") else None
        if d and not (ch and (ch.get("before") is not None or ch.get("delta"))):
            warn(tag + "：写了箭头却没写 change（前后值或涨跌幅），去掉箭头")
            d = None
        x["dir"] = d
        if d and ch:
            x["change"] = ({"before": ch["before"], "before_en": ch.get("before_en", ch["before"]), "ref": list(ch["ref"])}
                           if ch.get("before") is not None else {"delta": True})
        out.append(x)
    if len(out) > cap:
        warn("今日数字有 %d 个，只留前 %d 个" % (len(out), cap))
        out = out[:cap]
    return out


def make_charts(page, ck, lenient):
    out = {}
    for cid, c in (page.get("charts") or {}).items():
        tag = "图表 %s" % cid
        if not isinstance(c, dict) or c.get("type") not in CHART_TYPES:
            warn(tag + "：类型 %r 不认识（可用 %s），去掉" % ((c or {}).get("type"), "、".join(CHART_TYPES)))
            continue
        c = json.loads(json.dumps(c))
        probs, evs = [], set()

        def val(o, where, need_value=True):
            text, why = ck.entry(o.get("ref"))
            if why:
                return why
            evs.add(o["ref"][0])
            if need_value and "v" in o:
                for v in (o["v"], o.get("v_en", o["v"])):
                    if not num_found(v, nums_in(text)):
                        return "%s 的数值 %s 在出处里找不到" % (where, v)
            return None
        if c["type"] == "dumbbell":
            for row in c.get("rows") or []:
                for p in row.get("points") or []:
                    e = val(p, pick_label(p))
                    if e:
                        probs.append(e)
        elif c["type"] in ("bars", "steps"):
            for it in c.get("items") or []:
                e = val(it, pick_label(it))
                if e:
                    probs.append(e)
                if it.get("extra_ref"):
                    t2, why = ck.entry(it["extra_ref"])
                    if why:
                        warn(tag + "：%s 的补充说明出处对不上（%s），去掉补充说明" % (pick_label(it), why))
                        for k in ("extra_zh", "extra_en", "extra_ref"):
                            it.pop(k, None)
                    else:
                        evs.add(it["extra_ref"][0])
            if c.get("base"):
                e = val(c["base"], pick_label(c["base"]))
                if e:
                    probs.append(e)
        elif c["type"] == "timeline":
            keep = []
            for it in c.get("items") or []:
                e = val(it, it.get("when_zh", ""), need_value=False)
                if e:
                    warn(tag + "：时间线“%s”出处对不上（%s），去掉这一格" % (it.get("when_zh"), e))
                else:
                    keep.append(it)
            c["items"] = keep
            if len(keep) < 2:
                warn(tag + "：时间线不到 2 格，去掉整张图")
                continue
        elif c["type"] == "graph":
            ids = {n.get("id") for n in c.get("nodes") or []}
            keep = []
            for l in c.get("links") or []:
                e = val(l, "%s→%s" % (l.get("s"), l.get("t")), need_value=False)
                if e or l.get("s") not in ids or l.get("t") not in ids:
                    warn(tag + "：连线 %s→%s 去掉（%s）" % (l.get("s"), l.get("t"), e or "两端节点不全"))
                else:
                    keep.append(l)
            c["links"] = keep
            if not keep:
                warn(tag + "：关系图一条连线都没剩，去掉整张图")
                continue
        if c.get("note_ref"):
            t2, why = ck.entry(c["note_ref"])
            if why:
                warn(tag + "：注释出处对不上（%s），去掉注释" % why)
                for k in ("note_zh", "note_en", "note_ref"):
                    c.pop(k, None)
            else:
                evs.add(c["note_ref"][0])
        # 图上文字（标题、注释、标签、时间）里的数字也要在相关事件卡里找得到
        pool = []
        for ev in evs:
            pool += nums_in(ck.card_text(ev))
        texts = [c.get(k) for k in ("title_zh", "title_en", "note_zh", "note_en")]
        for coll in ("items", "rows"):
            for it in c.get(coll) or []:
                texts += [it.get(k) for k in ("label_zh", "label_en", "when_zh", "when_en", "text_zh", "text_en", "extra_zh", "extra_en")]
        for l in c.get("links") or []:
            texts += [l.get("zh"), l.get("en")]
        for n in c.get("nodes") or []:
            texts += [n.get("zh"), n.get("en")]
        bad = sorted({x for t in texts for x in loose_nums(t) if not num_found(x, pool)})
        if bad:
            probs.append("图上文字里的数字 %s 在事件卡里找不到" % "、".join("%g" % x for x in bad))
        if probs:
            (warn if lenient else err)(tag + "：" + "；".join(probs) + ("，去掉整张图" if lenient else ""))
            continue
        out[cid] = c
    return out


def pick_label(o):
    return o.get("label_zh") or o.get("label_en") or "?"


def make_watch(page, ck, stories, day):
    out = []
    for i, w in enumerate(page.get("watch") or []):
        tag = "预告第 %d 条（%s）" % (i + 1, w.get("when_zh") or w.get("story"))
        refs = w.get("refs") or ([w["ref"]] if w.get("ref") else [])
        if not refs:
            warn(tag + "：没有出处，去掉")
            continue
        whys = [why for _, why in (ck.entry(r) for r in refs) if why]
        if whys:
            warn(tag + "：" + "；".join(whys) + "，去掉")
            continue
        pool = []
        for r in refs:
            pool += nums_in(ck.card_text(r[0]))
        bad = sorted({x for k in ("when_zh", "when_en", "text_zh", "text_en") for x in loose_nums(w.get(k)) if not num_found(x, pool)})
        if bad:
            warn(tag + "：文字里的数字 %s 在事件卡里找不到，去掉" % "、".join("%g" % x for x in bad))
            continue
        st = w.get("status") if w.get("status") in WATCH_STATUS else "reported"
        if st != w.get("status"):
            warn(tag + "：状态 %r 不认识，按“报道称”" % w.get("status"))
        d = parse_day(w.get("date_iso")) or parse_day(w.get("sort_date")) or guess_date(w.get("when_zh"), day)
        if not d:
            warn(tag + "：没有可排序的日期（date_iso / sort_date），排到最后")
        x = {"status": st, "when_zh": w.get("when_zh", ""), "when_en": w.get("when_en", ""), "story": w.get("story"),
             "text_zh": w.get("text_zh", ""), "text_en": w.get("text_en", ""), "refs": [list(r) for r in refs]}
        if parse_day(w.get("date_iso")):
            x["date_iso"] = str(parse_day(w.get("date_iso")))
        x["sort_date"] = str(d) if d else None
        if w.get("story") and w["story"] not in stories:
            warn(tag + "：链接的条目不在稿件里，页面上不放“看原条”按钮")
        out.append(x)
    out.sort(key=lambda x: (x["sort_date"] is None, x["sort_date"] or ""))   # 稳定排序：同一天保持稿件里的先后
    if len(out) > 5:
        warn("预告有 %d 条，只留时间最早的 5 条" % len(out))
        out = out[:5]
    return out


def make_pairs(page, sel, stories, charts):
    rel_names = list(SITE.RELATIONS)
    alias = {}
    for name, r in SITE.RELATIONS.items():
        for a in [name, r["key"], r["label_zh"], r["en"]] + list(r.get("alias", ())):
            alias[re.sub(r"[\s（）()·]", "", a).lower()] = name
    norm = lambda x: alias.get(re.sub(r"[\s（）()·]", "", str(x or "")).lower())   # noqa: E731
    sel_rel = {}
    for p in (sel.get("cn_intl_pairs") or []):
        k = (p.get("intl_event_id") or p.get("intl"), p.get("cn_event_id") or p.get("cn"))
        sel_rel[k] = norm(p.get("relation"))
    src = page.get("pairs")
    if src is None:   # 网页稿没写 pairs：用选题里的配对
        src = [{"intl": a, "cn": b} for (a, b) in sel_rel]
    out = []
    for p in src:
        tag = "对照 %s × %s" % (p.get("intl"), p.get("cn"))
        if p.get("intl") not in stories or p.get("cn") not in stories:
            warn(tag + "：有一边不在稿件里，去掉")
            continue
        rel = norm(p.get("relation")) or sel_rel.get((p["intl"], p["cn"]))
        if not rel:
            warn(tag + "：关系 %r 不在词表里（%s），页面按“呼应”" % (p.get("relation"), "、".join(rel_names)))
        x = {"intl": p["intl"], "cn": p["cn"]}
        if rel:
            x["relation"] = rel
        for k in ("label_zh", "label_en", "lead", "intl_zh", "intl_en", "cn_zh", "cn_en"):
            if p.get(k):
                x[k] = p[k]
        if p.get("chart_cn"):
            if p["chart_cn"] in charts:
                x["chart_cn"] = p["chart_cn"]
            else:
                warn(tag + "：图表 %s 没有（或没通过核对），不放" % p["chart_cn"])
        out.append(x)
    if len(out) > 3:
        warn("对照有 %d 对，只留前 3 对" % len(out))
        out = out[:3]
    return out


def norm_q(s):
    return re.sub(r"[\s“”\"'‘’「」『』]", "", str(s or ""))


def make_caption(k, a, ck):
    """图注（v3.2）：caption_zh/en 是一句“这张图对这条新闻意味着什么”（≤24 字，不含数字，不加新事实）；
    或者 quote = {zh, en, ref}：一句有出处的原话，逐字核对。都没有就没有图注（页面不显示图注框）。"""
    if a.get("caption_zh"):
        cz, ce = a["caption_zh"].strip(), (a.get("caption_en") or "").strip()
        if re.search(r"(?<![A-Za-z\-])\d", cz + ce):   # 型号、文件名里的数字（S-1、GPT-5）不算
            warn("配图 %s 的图注里有数字（图注不放数字），不用这句图注" % k)
            return {}
        if len(re.sub(r"\s", "", cz)) > 24:
            warn("配图 %s 的图注超过 24 个字，页面上可能折成两三行" % k)
        return {"cap_zh": cz, "cap_en": ce}
    q = a.get("quote") or {}
    if q.get("zh"):
        text, why = ck.entry(q.get("ref"))
        if why or norm_q(q["zh"]) not in norm_q(text) or (q.get("en") and norm_q(q["en"]) not in norm_q(text)):
            warn("配图 %s 的引语核对不上（%s），不放图注" % (k, why or "原话不在出处那一条里"))
            return {}
        return {"cap_zh": "“%s”" % q["zh"].strip("“”\" "), "cap_en": ("“%s”" % q["en"].strip("“”\" ")) if q.get("en") else ""}
    return {}


def make_images(page, issue, img_dir, web, stories, ck):
    imgs = page.get("images") or {}
    folder = os.path.join(issue, img_dir)
    files = {}
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            b, e = os.path.splitext(f)
            if e.lower() in IMG_EXT:
                files.setdefault(b.lower(), f)
    titles = {it["id"]: it for s in web.get("sections") or [] for it in s.get("items") or []}
    keys = ["card", "term"] + [sid for sid in stories if sid != "term"]
    out = {}
    for k in keys:
        f = files.get(k.lower())
        if not f:
            continue
        a = imgs.get(k) or imgs.get(k.lower()) or imgs.get(k.upper()) or {}
        cap = make_caption(k, a, ck)
        if not (a.get("alt_zh") and a.get("alt_en")):
            it = titles.get(k) or {}
            a = {"alt_zh": a.get("alt_zh") or ("配图：" + (it.get("title_zh") or ("日卡" if k == "card" else "今日一词"))),
                 "alt_en": a.get("alt_en") or ("Illustration: " + (it.get("title_en") or ("day card" if k == "card" else "word of the day")))}
            warn("配图 %s 没有替代文字，先用标题代替" % f)
        out[k] = {"file": f, "alt_zh": a["alt_zh"], "alt_en": a["alt_en"], **cap}
    want = {"card"} | {sid for sid, kind in stories.items() if kind in ("headline", "brief", "deep")}
    miss = sorted(k for k in want if k not in out)
    if miss:
        warn("缺配图（页面会用主题色抽象封面）：" + "、".join(miss))
    return out


# ---------------------------------------------------------------- 周末（11-01 晚）：哪一版、深度那一条的新字段
LAYER_RE = re.compile(r"^[\s​⁠]*【([^】]{1,30})】")


def edition_of(day, stories):
    """网页稿里有 deep 那一条才算周末版：周日 "sun"，其余（周六）"sat"；没有就是工作日（None）。"""
    if "deep" not in stories.values():
        return None
    return "sun" if day.weekday() == 6 else "sat"


def deep_layers(it):
    return [m.group(1).strip() for p in str(it.get("body_zh") or "").split("\n") for m in [LAYER_RE.match(p)] if m]


def check_deep(web, page, edition):
    """深度／深谈那一条：周日的核心问题和一句话结论、名词解释、每层的关键数字、图表的层名。只提醒，页面照常。"""
    lo, hi = SITE.GLOSSARY_RANGE
    for s in web.get("sections") or []:
        if s.get("kind") == "term":
            warn("周末网页不放“今日一词”（改成深度那一块里的“名词解释”），网页稿里的 term 条目页面上不显示")
        if s.get("kind") != "deep":
            continue
        for it in s.get("items") or []:
            tag = "%s %s" % ("深谈" if edition == "sun" else "深度", it.get("id"))
            layers = deep_layers(it)
            if not layers:
                warn(tag + "：正文里没找到【层名】段，页面没法分层")
            if edition == "sun":
                for k, name in (("question", "核心问题"), ("conclusion", "一句话结论")):
                    zh = (it.get(k + "_zh") or "").strip()
                    if not zh:
                        warn(tag + "：没写 %s_zh（%s），本周深谈卡上少这一行" % (k, name))
                        continue
                    if not (it.get(k + "_en") or "").strip():
                        warn(tag + "：没写 %s_en（%s的英文），英文页面用中文" % (k, name))
                    if len(re.sub(r"\s", "", zh)) > 40:
                        warn(tag + "：%s超过 40 个字，卡片上会折成好几行" % name)
            g = it.get("glossary") or []
            if not lo <= len(g) <= hi:
                warn(tag + "：名词解释有 %d 个（建议 %d–%d 个）" % (len(g), lo, hi))
            for e in g:
                if not ((e.get("zh") or "").strip() and (e.get("explain_zh") or "").strip()):
                    warn(tag + "：名词解释“%s”缺 zh 或 explain_zh，页面不放这一个" % (e.get("zh") or e.get("en") or "?"))
                elif e.get("layer") and e["layer"] not in layers:
                    warn(tag + "：名词解释“%s”的层名 %r 不在正文的层里（%s），页面不标是哪一层" % (e["zh"], e["layer"], "、".join(layers)))
            per = {}
            for n in it.get("numbers") or []:
                L = n.get("layer")
                if L and L not in layers:
                    warn(tag + "：关键数字 %s 的层名 %r 不在正文的层里（%s）" % (n.get("value"), L, "、".join(layers)))
                elif L:
                    per[L] = per.get(L, 0) + 1
                elif edition == "sun":
                    warn(tag + "：关键数字 %s 没写 layer，页面放进“数字怎么读”那一层" % n.get("value"))
            for L, c in per.items():
                if c > SITE.LAYER_NUMBERS_MAX:
                    warn(tag + "：“%s”这一层有 %d 个关键数字，页面只放前 %d 个" % (L, c, SITE.LAYER_NUMBERS_MAX))
            for cid, c in (page.get("charts") or {}).items():
                if isinstance(c, dict) and c.get("layer") and layers and c["layer"] not in layers:
                    warn("图表 %s 的层名 %r 不在正文的层里（%s），页面放在整块最后" % (cid, c["layer"], "、".join(layers)))


# ---------------------------------------------------------------- 主程序
def main():
    ap = argparse.ArgumentParser(description="生成某一天的网页 v3 配置")
    ap.add_argument("--day", required=True, help="日期，如 2026-11-01")
    ap.add_argument("--issue-dir", help="期目录（默认 测试版/<日期>）")
    ap.add_argument("--web", default="04_文稿/claude_网页.json")
    ap.add_argument("--selection", default="02_选题/最终选题.json")
    ap.add_argument("--images", default="06_配图")
    ap.add_argument("--podcast")
    ap.add_argument("--fixture", help="补 page 和选题字段的 JSON（测试旧日子用）")
    ap.add_argument("--out", help="写到哪（默认 site/tools/v3_issues/<日期>.py）")
    ap.add_argument("--lenient", action="store_true", help="数字核对不上时去掉那一项而不是失败")
    a = ap.parse_args()

    day = parse_day(a.day)
    if not day:
        sys.exit("--day 应是 YYYY-MM-DD")
    issue = os.path.abspath(a.issue_dir) if a.issue_dir else os.path.join(ISSUES_ROOT, a.day)
    J = lambda p: p if os.path.isabs(p) else os.path.join(issue, p)   # noqa: E731
    if not os.path.isfile(J(a.web)):
        sys.exit("找不到网页稿 " + J(a.web))
    web = json.load(open(J(a.web), encoding="utf-8"))
    cards = json.load(open(J("03_事件卡/cards_写稿用.json"), encoding="utf-8"))
    sel = json.load(open(J(a.selection), encoding="utf-8")) if os.path.isfile(J(a.selection)) else {}
    if not sel:
        warn("没有选题文件 %s，主题色和对照关系只能靠网页稿" % a.selection)
    page = web.get("page") or {}
    if a.fixture:
        fx = json.load(open(a.fixture, encoding="utf-8"))
        page = fx.get("page") or page
        sel = dict(sel, **(fx.get("selection") or {}))
    if not page:
        warn("网页稿里没有 page：今日数字、预告、图表、配图说明都会是空的")
    ck = Checker(cards)
    stories = {}
    for s in web.get("sections") or []:
        for it in s.get("items") or []:
            stories["term" if s["kind"] == "term" else it["id"]] = s["kind"]

    # 主题色：选题定（storylines 决定当天主线），网页稿的 page.theme 只是后备
    th = sel.get("theme") or page.get("theme") or {}
    accent = th.get("accent")
    if accent not in SITE.ACCENTS:
        warn("主题色 %r 不在 v3_site.py 的 ACCENTS 里（%s），先用 blue" % (accent, "、".join(SITE.ACCENTS)))
        accent = "blue"
    why = th.get("why_zh") or next((s.get("title_zh") or s.get("zh") for s in (sel.get("storylines") or []) if isinstance(s, dict)), "")

    # 正文里的数字（标题、摘要、正文、为什么重要、条目自带的数字卡）也过一遍：只提醒、不拦——
    # 正文可能合理地回扣往期（写稿输入里的 notes），也可能有换算；但找不到的数字值得人工看一眼。
    notes_pool = []
    for extra in (J("04_文稿/写稿输入.json"),):
        if os.path.isfile(extra):
            notes_pool += nums_in(json.dumps((json.load(open(extra, encoding="utf-8")) or {}).get("notes", ""), ensure_ascii=False))
    notes_pool += nums_in(json.dumps(sel.get("_notes_for_writers", ""), ensure_ascii=False))
    edition = edition_of(day, stories)
    if edition:
        check_deep(web, page, edition)
    for s_ in web.get("sections") or []:
        for it in s_.get("items") or []:
            pool = notes_pool + nums_in(ck.card_text(it["id"]) + " " + " ".join(ck.card_text(r.get("id")) for r in it.get("related") or []))
            txt = " ".join(str(it.get(k) or "") for k in ("title_zh", "title_en", "summary_zh", "summary_en", "body_zh", "body_en", "why_zh", "why_en"))
            txt += " " + " ".join("%s %s %s" % (n.get("value"), n.get("label_zh", ""), n.get("label_en", "")) for n in it.get("numbers") or [])
            if s_["kind"] == "deep":   # 周末：卡片上的核心问题、一句话结论，和名词解释里的数字也过一遍
                txt += " " + " ".join(str(it.get(k) or "") for k in ("question_zh", "question_en", "conclusion_zh", "conclusion_en"))
                txt += " " + " ".join("%s %s" % (e.get("explain_zh", ""), e.get("explain_en", "")) for e in it.get("glossary") or [])
            bad = sorted({x for x in loose_nums(txt) if not num_found(x, pool)})
            if bad:
                warn("正文数字核对：%s（%s）里的 %s 在事件卡里找不到，请人工看一眼" % (it["id"], s_["kind"], "、".join("%g" % x for x in bad)))

    # 英文里加了引号的话，必须是事件卡里的英文原话（quote）；从中文回译的话不能加引号当原话（v3.2 审读意见）
    en_quotes = " ".join(str(e.get("quote") or "") for c in cards for lst in (c.get("facts") or [], c.get("numbers") or [], c.get("who_said") or [])
                         for e in lst)
    nq = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())   # noqa: E731
    pool_q = nq(en_quotes)
    for s_ in web.get("sections") or []:
        for it in s_.get("items") or []:
            ks = ("title_en", "summary_en", "body_en", "why_en", "read_en") + (("question_en", "conclusion_en") if s_["kind"] == "deep" else ())
            for k in ks:
                for q in re.findall(r"[“\"]([^”\"]{12,})[”\"]", str(it.get(k) or "")):
                    if len(q.split()) >= 4 and nq(q) not in pool_q:
                        warn("英文引号核对：%s 的 %s 里“%s…”在事件卡的英文原话里找不到（可能是从中文回译的），改成转述、去掉引号"
                             % (it["id"], k, q[:40]))

    cap = SITE.WEEKEND[edition]["numbers_max"] if edition else 5
    if cap == 0:   # 周日：不单列今日数字，关键数字在深谈各层里
        if page.get("numbers"):
            warn("周日不单列今日数字：page.numbers 的 %d 个都不放（关键数字写进深谈那一条的 numbers，带 layer）" % len(page["numbers"]))
        numbers = []
    else:
        numbers = make_numbers(page, ck, stories, a.lenient, cap)
    charts = make_charts(page, ck, a.lenient)
    story_charts = {}
    for sid, ids in (page.get("story_charts") or {}).items():
        if stories.get(sid) not in ("headline", "deep"):
            warn("story_charts：%s 不是头条，也不是周末的深度／深谈，去掉" % sid)
            continue
        ok = [c for c in ids if c in charts]
        if len(ok) < len(ids):
            warn("story_charts：%s 的图 %s 没有（或没通过核对），去掉" % (sid, "、".join(c for c in ids if c not in charts)))
        if ok:
            story_charts[sid] = ok[:2]
    flash = page.get("flash_chart")
    if flash and flash not in charts:
        warn("flash_chart：图表 %s 没有（或没通过核对），快讯旁不放图" % flash)
        flash = None
    watch = make_watch(page, ck, stories, day)
    pairs = make_pairs(page, sel, stories, charts)
    images = make_images(page, issue, a.images, web, stories, ck)
    tl = page.get("term_like") or {}
    podcast = a.podcast or find_podcast(issue)
    if not podcast:
        warn("05_配音 下没找到播客（episode.mp3 + chapters.json），页面上不放播客")

    if ERR:
        print("\n有 %d 处数字核对不上（可能是编造的），没有写配置。改好网页稿再跑；或者加 --lenient 去掉这些项。" % len(ERR))
        sys.exit(1)

    out = os.path.abspath(a.out) if a.out else os.path.join(HERE, "v3_issues", a.day + ".py")
    rel = lambda p: rel_or_abs(J(p), issue)   # noqa: E731
    wd = ("星期" + "一二三四五六日"[day.weekday()], day.strftime("%A"))
    cfg = [
        ("WEEKDAY", wd),
        ("WEB", rel(a.web)),
        ("CARDS", "03_事件卡/cards_写稿用.json"),
        ("CANDIDATES", "02_选题/candidates.json" if os.path.isfile(J("02_选题/candidates.json")) else None),
        ("PODCAST_DIR", podcast),
        ("VIDEO_SCRIPT", None),   # 新的日子只用 11_视频v3（build_v3.py 自动找）；第一版、第二版视频不再生成
        ("VIDEO_AUDIO", None),
        ("THEME", {"accent": accent, "why_zh": why}),
        ("IMAGE_DIR", a.images),
        ("IMAGES", images),
        ("TERM_LIKE", {"zh": tl.get("zh", ""), "en": tl.get("en", "")} if tl.get("zh") and not edition else None),   # 周末没有今日一词
        ("NUMBERS", numbers),
        ("CHARTS", charts),
        ("STORY_CHARTS", story_charts),
        ("FLASH_CHART", flash),
        ("WATCH", watch),
        ("PAIRS", pairs),
    ]
    head = ['# -*- coding: utf-8 -*-',
            '"""%s 这一期的 v3 网页配置。由 site/tools/make_issue_v3.py 自动生成（%s），请勿手改：' % (a.day, datetime.now().strftime("%Y-%m-%d %H:%M")),
            '要改内容，改网页稿 %s 的 page，或改选题，再重新生成。' % rel(a.web),
            '每个 ref = [事件号, 条目, 核对片段]，组装时 build_v3.py 还会再核对一遍。',
            '生成时的提醒（%d 条）：' % len(WARN)] + ['  - ' + w.replace('"""', "'''") for w in WARN] + ['"""', '']
    body = []
    for k, v in cfg:
        body.append("%s = %s" % (k, pprint.pformat(v, width=150, sort_dicts=False)))
        body.append("")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(head + body))
    print("已写配置：%s" % rel_or_abs(out, ROOT))
    print("  %s主题色 %s · 今日数字 %d · 图表 %d · 预告 %d（%s）· 对照 %d · 配图 %d · 播客 %s · 提醒 %d 条"
          % ({"sat": "周六版 · ", "sun": "周日版 · "}.get(edition, ""),
             accent, len(numbers), len(charts), len(watch), " → ".join(w["when_zh"] for w in watch), len(pairs),
             len(images), podcast or "无", len(WARN)))


if __name__ == "__main__":
    main()
