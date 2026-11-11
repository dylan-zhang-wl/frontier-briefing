#!/usr/bin/env python3
"""视频 v2 场景计划：节拍（内容＋触发词）→ 按内容挑模板 → 触发词换成秒 → 播放器 site/v2/video2.js 要的数据。

节拍来自每期配置的 VIDEO_BEATS（写法见 site/tools/v2_issues/2026-10-31.py 末尾）；没有时由 from_script()
从第一版视频稿（claude_视频_定时.json 的 8 个场景）自动拆出来，长场景先放一屏配图再讲数字。
数字把关：配置里凡是带数字的元素都要有 ref，build_v2.py 用事件卡逐条核对；自动拆的节拍没有 ref，会提示“未核对”。
"""
import re

from video_align import find, norm, num_zh

# 模板库：名字 → 用途。播放器里每种模板一个函数（site/v2/video2.js 的 TPL）。
TEMPLATES = {
    "kinetic": "动态标题：词按旁白逐个弹出，数字等宽放大，可划掉旧数字",
    "counter": "关键数字：从 0 滚到实际值，带涨跌箭头",
    "bars": "条形图生长：几项数值比大小，可加参考线（如“一半”）",
    "dumbbell": "哑铃图：之前 → 之后，点沿刻度滑过去，中间标出差值",
    "split": "左右分屏对照：两块并排，右块的数从左块的值滚过去",
    "timeline": "时间线推进：刻度上的游标走到每个日子，依次亮出事件",
    "quote": "引语逐字高亮：引语里的字随旁白逐字变亮，下附原文措辞",
    "graph": "关系图生长：节点按旁白出现，连线逐条画出，关键连线流动",
    "kenburns": "配图缓推：配图慢慢推近，前景标签反向平移形成视差",
    "cascade": "要点依次落下：一条条从上方落入",
    "glitch": "不确定：轻微故障（错位、色散、扫描线）＋“未确认”印章",
    "recap": "结尾回顾宫格＋来源：每条一块，点了跳到网页对应条目",
}
# 内容形状 → 可用模板（按优先顺序）。挑选规则：不和上一屏相同；ROTATE 里的形状几种模板同样合适，优先本期还没用过的、
# 都用过就挑最久没用的；其余形状一律用第一个（最合适的），只有和上一屏相同时才退到第二个。
SHAPES = {
    "hook": ["kinetic", "kenburns"], "image": ["kenburns", "kinetic"], "change": ["dumbbell", "split"],
    "amounts": ["bars", "cascade"], "number": ["counter", "kinetic"], "quote": ["quote", "kinetic"],
    "relation": ["graph", "cascade"], "dates": ["timeline", "cascade"], "points": ["cascade", "kinetic"],
    "contrast": ["split", "cascade"], "uncertain": ["glitch", "kinetic"], "recap": ["recap", "cascade"],
}
ROTATE = {"hook", "change", "points"}
LEAD_BEAT = 0.22   # 一屏比它的第一个字早这么多秒切进来（转场本身要 0.3 秒左右）
LEAD_EL = 0.08     # 元素比对应的字早这么多秒开始动（动画头几帧还看不清，这样“说到”时正好显出来）
TEXT_KEYS = ("zh", "en", "text_zh", "text_en", "when_zh", "when_en", "v_zh", "v_en", "label_zh", "label_en")
DIGIT = re.compile(r"\d")


class PlanError(Exception):
    pass


def choose(beats):
    used, prev = {}, None
    for i, b in enumerate(beats):
        if not b.get("tpl"):
            opts = SHAPES.get(b["shape"]) or ["kinetic"]
            cands = [c for c in opts if c != prev] or opts
            fresh = [c for c in cands if c not in used]
            if b["shape"] in ROTATE:
                b["tpl"] = fresh[0] if fresh else min(cands, key=lambda c: used[c])
            else:
                b["tpl"] = cands[0]
        if b["tpl"] not in TEMPLATES:
            raise PlanError("第 %d 屏：没有“%s”这种模板" % (i + 1, b["tpl"]))
        used[b["tpl"]] = i
        prev = b["tpl"]
    for i in range(1, len(beats)):
        if beats[i]["tpl"] == beats[i - 1]["tpl"]:
            raise PlanError("第 %d、%d 屏模板相同（%s）：给其中一屏换个 shape 或写 tpl" % (i, i + 1, beats[i]["tpl"]))
    return beats


def build(beats_cfg, al, duration, vref, src_name, images, script=None, strict=True):
    """beats_cfg：配置里的节拍（None → 从 script 自动拆）；al：video_align.align() 的结果；
    vref((事件, 条目, 片段)) → 来源编号或 None（核对不过就报错）；src_name(编号) → (中文名, 英文名)；images：配图表。"""
    auto = beats_cfg is None
    src = from_script(script, al, images) if auto else [dict(b) for b in beats_cfg]
    strict = strict and not auto
    # 1. 每一屏的起点：找到它开头那几个字
    starts, ats, after = [], [], 0.0
    for i, b in enumerate(src):
        f = find(al, b.get("at") or "", after)
        if not f:
            raise PlanError("第 %d 屏：旁白里（%.1f 秒之后）找不到开头「%s」" % (i + 1, after, b.get("at")))
        s = 0.0 if i == 0 else max(f[0] - LEAD_BEAT, starts[-1] + 0.8)
        starts.append(round(s, 2))
        ats.append(f[0])
        after = f[0]
    ends = starts[1:] + [round(duration, 2)]
    keywords, out = [], []
    for i, b in enumerate(src):
        lo, hi, at0 = starts[i], ends[i], ats[i]
        cites, stagger = [], [0]

        def take(r):
            sid = vref(r)
            if sid and sid not in cites:
                cites.append(sid)
            return sid

        def cue_t(phrase, what):
            f = find(al, phrase, at0 - 0.01)
            if (not f or f[0] > hi + 0.05) and not strict:
                return None                     # 自动拆分时找不到就按顺序出现，不报错
            if not f or f[0] > hi + 0.05:
                raise PlanError("第 %d 屏（%s）：这一屏的旁白里找不到「%s」" % (i + 1, what, phrase))
            keywords.append({"beat": i, "cue": phrase, "t": round(f[0], 3), "t_end": round(f[1], 3)})
            return f

        def walk(o, has_ref, path):
            if isinstance(o, list):
                for k, x in enumerate(o):
                    walk(x, has_ref, path + "[%d]" % k)
                return
            if not isinstance(o, dict):
                return
            mine = False
            for k in [k for k in o if k == "ref" or k.endswith("_ref")]:
                sid = take(o.pop(k))
                if k == "ref":
                    o["cite"] = sid
                mine = True
            if "refs" in o:
                o["cite"] = [take(r) for r in o.pop("refs")]
                mine = True
            for k in TEXT_KEYS:
                if strict and isinstance(o.get(k), str) and DIGIT.search(o[k]) and not (mine or has_ref):
                    raise PlanError("第 %d 屏 %s：「%s」带数字，但没写 ref（数字只能来自事件卡）" % (i + 1, path, o[k]))
            if "cue" in o:
                f = cue_t(o["cue"], path) if o["cue"] else None
                if f:
                    o["t"] = round(max(lo + 0.05, f[0] - LEAD_EL), 2)
                    o["t_end"] = round(f[1], 2)
                else:
                    o.pop("cue")
            if path and "t" not in o and any(k in o for k in TEXT_KEYS + ("v", "to", "id", "sync")):
                o["t"] = round(lo + 0.3 + 0.2 * stagger[0], 2)     # 没写触发词：这一屏开头依次出现
                stagger[0] += 1
            if o.get("strike"):
                f = cue_t(o.pop("strike"), path + ".strike")
                if f:
                    o["strike_t"] = round(f[0], 2)
            if o.get("sync"):
                f = cue_t(o["sync"], path + ".sync")
                if f:
                    o["t"] = round(max(lo + 0.05, f[0] - 0.4), 2)
                    o["ct"] = char_times_for(al, f[2], o["sync"], o.get("zh") or "")
            for k, v in list(o.items()):
                if isinstance(v, (dict, list)):
                    walk(v, has_ref or (mine and path != ""), path + "." + k)   # 顶层的 *_ref 只核对刻度，不替子元素担保

        d = {k: v for k, v in b.items() if k not in ("at", "chip", "kicker", "src")}
        walk(d, False, "")
        for tile in d.get("tiles") or []:      # 回顾宫格：每块写上它自己的来源
            c = tile.get("cite")
            nm = list(dict.fromkeys(src_name(x) for x in (c if isinstance(c, list) else [c]) if x))
            if nm:
                tile["src_zh"], tile["src_en"] = " · ".join(n[0] for n in nm), " · ".join(n[1] for n in nm)
        d.update(i=i, start=lo, end=hi)
        for key in ("chip", "kicker"):
            pair = b.get(key) or ("", "")
            d[("label" if key == "chip" else key) + "_zh"], d[("label" if key == "chip" else key) + "_en"] = pair
        names = [src_name(s) for s in cites if s]
        names = [n for k, n in enumerate(names) if n not in names[:k]][:3]
        if b.get("src"):
            d["src_zh"], d["src_en"] = b["src"]
        elif names:
            d["src_zh"] = " · ".join(n[0] for n in names)
            d["src_en"] = " · ".join(n[1] for n in names)
        if d.get("image") and isinstance(d["image"], str):
            im = images.get(d["image"])
            d["image"] = {"src": im["src"], "alt_zh": im["alt_zh"], "alt_en": im["alt_en"]} if im else None
        out.append(d)
    choose(out)
    used = sorted({b["tpl"] for b in out})
    return {"beats": out, "keywords": keywords, "templates_used": used, "auto": auto, "checked": strict}


def char_times_for(al, i0, sync, text):
    """引语逐字高亮：引语里每个字对应旁白里同一个字的时间（引号等标点跟前一个字）。"""
    units = al["units"][i0:i0 + len(norm(sync))]
    out, j, last = [], 0, units[0]["s"] if units else 0
    for ch in text:
        c = ch.lower()
        if j < len(units) and norm(ch) and units[j]["c"] == c:
            last = units[j]["s"]
            j += 1
        out.append(round(last, 3))
    return out


# ---------------------------------------------------------------- 没有节拍表时：从第一版视频稿自动拆
NUM = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)")


def reading_cue(value):
    """'约 110 亿美元' → '一百一十'；'-28.58%' → '百分之二十八点五八'（在旁白里找这个读法）"""
    s = str(value or "")
    m = NUM.search(s)
    if not m:
        return None
    tok = m.group(1).lstrip("-").replace(",", "")
    return num_zh(tok + ("%" if "%" in s[m.end():m.end() + 2] else ""))


def first_clause(text, n=6):
    return norm(re.split(r"[，。；：！？]", text or "")[0])[:n]


def from_script(script, al, images):
    beats, seen_img = [], set()
    scenes = script["scenes"]
    for si, sc in enumerate(scenes):
        narr = sc.get("narration_zh") or ""
        at = norm(narr)[:6]
        ev = sc.get("event_id")
        base = dict(at=at, ev=ev, chip=(sc.get("heading_zh") or "", sc.get("heading_en") or ""),
                    kicker=(sc.get("heading_zh") or "", sc.get("heading_en") or ""),
                    sub_en=" ".join(x for x in (sc.get("heading_en"), sc.get("body_en")) if x))
        clauses = [c for c in re.split(r"(?<=[，。；：！？])", narr) if norm(c)]
        span = (sc.get("end") or 0) - (sc.get("start") or 0)
        typ = sc.get("type")
        if typ not in ("title", "source", "image") and span > 9 and ev in images and ev not in seen_img and len(clauses) > 1:
            # 长场景先放一屏配图：讲到第一个离开头至少 2.5 秒、离结尾至少 3 秒的分句时，切到这一场景本来的画面
            t0 = (find(al, at, sc.get("start", 0) - 0.5) or (sc.get("start", 0),))[0]
            cut = None
            for c in clauses[1:]:
                f = find(al, norm(c)[:6], t0)
                if f and f[0] - t0 >= 2.5 and (sc.get("end") or 0) - f[0] >= 3.0:
                    cut = norm(c)[:6]
                    break
            if cut:
                beats.append(dict(base, shape="image", image=ev,
                                  title=dict(zh=sc.get("heading_zh") or "", en=sc.get("heading_en") or "")))
                seen_img.add(ev)
                base = dict(base, at=cut)
        if typ == "title":
            beats.append(dict(base, shape="hook", lines=[[dict(cue=first_clause(narr, 4), zh=sc.get("heading_zh"), en=sc.get("heading_en"))],
                                                         [dict(zh=sc.get("body_zh"), en=sc.get("body_en"))]]))
        elif typ == "compare":
            bars = sc.get("bars") or []
            items = [dict(cue=reading_cue(x.get("value")), label_zh=str(x.get("label")).split(" ")[0], label_en=str(x.get("label")),
                          v=float(x.get("value") or 0), v_en=float(x.get("value") or 0)) for x in bars]
            if len(items) == 2:
                beats.append(dict(base, shape="change", title=dict(zh=sc.get("heading_zh"), en=sc.get("heading_en")),
                                  unit=(bars[0].get("unit") or "", bars[0].get("unit") or ""), max=max(i["v"] for i in items) * 1.08,
                                  frm=dict(items[0], text_zh=str(bars[0]["value"]), text_en=str(bars[0]["value"])),
                                  to=dict(items[1], text_zh=str(bars[1]["value"]), text_en=str(bars[1]["value"]))))
            else:
                beats.append(dict(base, shape="amounts", title=dict(zh=sc.get("heading_zh"), en=sc.get("heading_en")),
                                  unit=(bars[0].get("unit") or "", "") if bars else ("", ""), items=items,
                                  max=max([i["v"] for i in items] + [1])))
        elif typ == "stat":
            st = sc.get("stat") or {}
            val = str(st.get("value") or "")
            m = NUM.search(val)
            num = m.group(1).replace(",", "") if m else "0"
            beats.append(dict(base, shape="number", name=dict(zh=sc.get("heading_zh"), en=sc.get("heading_en")),
                              label=dict(zh=st.get("label_zh"), en=st.get("label_en")),
                              value=dict(cue=reading_cue(val), to=abs(float(num)), dec=len(num.split(".")[1]) if "." in num else 0,
                                         pre=("−" if num.startswith("-") else "") + (val[:m.start()].strip() if m else ""),
                                         suf=val[m.end():].strip() if m else "", dir="down" if num.startswith("-") else None)))
        elif typ == "quote":
            q = sc.get("quote") or {}
            qt = norm(q.get("text_zh"))
            nn = norm(narr)
            best = max((qt[a:b] for a in range(len(qt)) for b in range(a + 2, len(qt) + 1) if qt[a:b] in nn), key=len, default="")
            beats.append(dict(base, shape="quote", quote=dict(sync=best or None, cue=None if best else first_clause(narr, 4),
                                                              zh=q.get("text_zh"), en=q.get("text_en") or q.get("text_zh")),
                              who=(q.get("who") or "", q.get("who_en") or q.get("who") or "")))
        elif typ == "list":
            its = sc.get("items_zh") or []
            ens = sc.get("items_en") or its
            nn = norm(narr)
            items = []
            for k, x in enumerate(its):
                key = next((norm(x)[a:a + 3] for a in range(max(1, len(norm(x)) - 2)) if norm(x)[a:a + 3] in nn), None)
                items.append(dict(cue=key, zh=x, en=ens[k] if k < len(ens) else x))
            beats.append(dict(base, shape="points", title=dict(zh=sc.get("heading_zh"), en=sc.get("heading_en")), items=items))
        elif typ == "image":
            beats.append(dict(base, shape="image", image=ev, title=dict(zh=sc.get("heading_zh"), en=sc.get("heading_en"))))
        else:   # source 或其他：结尾回顾
            tiles, done = [], set()
            for s2 in scenes[:si]:
                e2 = s2.get("event_id")
                if e2 and e2 not in done:
                    done.add(e2)
                    tiles.append(dict(ev=e2, k_zh=s2.get("heading_zh"), k_en=s2.get("heading_en"), v_zh="", v_en=""))
            beats.append(dict(base, shape="recap", tiles=tiles[:3], cta=dict(cue=first_clause(narr, 4), zh=sc.get("body_zh") or "",
                                                                             en=sc.get("body_en") or "")))
    # 去掉找不到读法的触发词（自动模式宁可按顺序出现，也不报错）
    for b in beats:
        for v in b.values():
            for o in (v if isinstance(v, list) else [v]):
                for o2 in (o if isinstance(o, list) else [o]):
                    if isinstance(o2, dict) and o2.get("cue") and not find(al, o2["cue"]):
                        o2["cue"] = None
    return beats
