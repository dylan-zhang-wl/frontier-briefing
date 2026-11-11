#!/usr/bin/env python3
"""把一期测试版组装成能双击打开的网页：site/ 模板 + 04_文稿 / 05_配音 / 06_配图 的真数据 → <测试版目录>/07_网页/

用法（在项目根目录 frontier-daily/ 下）：
    python3 site/tools/build_testpage.py 测试版/2026-10-31
只读输入目录，只写 07_网页/。依赖：Python 标准库 + Pillow，ffprobe（量音频时长）。不调用任何模型接口。
每期需要改的地方：前面的 IMAGES（配图对应哪条），文末 ISSUE 里的 date、weekday 和 meta 说明文字。
"""
import base64
import copy
import io
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, sys.argv[1] if len(sys.argv) > 1 else "测试版/2026-10-31")
SITE = os.path.join(ROOT, "site")
OUT = os.path.join(SRC, "07_网页")
A = os.path.join(OUT, "assets")
os.makedirs(A, exist_ok=True)


def jload(rel):
    with open(os.path.join(SRC, rel), encoding="utf-8") as f:
        return json.load(f)


def duration(path):
    return round(float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                      check=True, capture_output=True, text=True).stdout.strip()), 2)


# ---------------------------------------------------------------- 1. template
for f in ("app.js", "video.js", "style.css"):
    shutil.copy2(os.path.join(SITE, f), os.path.join(OUT, f))
with open(os.path.join(SITE, "index.html"), encoding="utf-8") as f:
    html = f.read()
html = html.replace('<meta name="fd-issue" content="issue.js mock/issue.js">', '<meta name="fd-issue" content="issue.js">')
html = html.replace("<!-- 本期数据：依次尝试，先找到的那份生效；也可以用 ?issue=相对路径/issue.js 指定 -->",
                    "<!-- 测试版 2026-10-31：数据在同目录的 issue.js，素材在 assets/；由 site/ 模板组装 -->")
html = html.replace("<title>每日前沿简报</title>", "<title>每日前沿简报 · 测试版 2026-10-31</title>")
with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
    f.write(html)

# ---------------------------------------------------------------- 2. pictures: PNG → web JPEG (~1400 px wide)
def to_jpeg(src, dst, width, quality):
    im = Image.open(src).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    if dst:
        with open(dst, "wb") as f:
            f.write(buf.getvalue())
    return buf.getvalue(), im.size


sizes = {}
for name in ("card", "e001", "e002"):
    data, size = to_jpeg(os.path.join(SRC, "06_配图", name + ".png"), os.path.join(A, name + ".jpg"), 1400, 82)
    sizes[name] = (size, len(data))
# the day card picture is also inlined (data URI) so "保存为图片" can draw it even when the page is opened by double-click (file://)
card_inline, _ = to_jpeg(os.path.join(SRC, "06_配图", "card.png"), None, 1080, 78)
CARD_URI = "data:image/jpeg;base64," + base64.b64encode(card_inline).decode("ascii")

CREDIT = {"credit_zh": "配图：AI 生成（Codex）", "credit_en": "Image: AI-generated (Codex)"}
IMAGES = {
    "E001": dict(src="assets/e001.jpg", alt_zh="配图：左侧几股深青色的流体向右收束，汇入一个由节点和连线组成的大脑",
                 alt_en="Illustration: teal streams narrowing as they flow into a brain made of connected nodes", **CREDIT),
    "E002": dict(src="assets/e002.jpg", alt_zh="配图：内存条从一台家用电脑飞出，排成弧线落向远处成排的数据中心机柜",
                 alt_en="Illustration: memory sticks flying out of a home PC in an arc toward rows of data-centre racks", **CREDIT),
}
CARD_ALT = dict(alt_zh="日卡配图：浅滩上由发光球形节点搭成的高塔，远处是厂房和落日",
                alt_en="Day card art: a glowing tower of spherical nodes on tidal flats, with plants and a setting sun beyond")

# ---------------------------------------------------------------- 3. audio and transcripts
AUDIO = {
    "video_claude.mp3": "05_配音/视频旁白_claude稿/episode.mp3",
    "video_mimo.mp3": "05_配音/视频旁白_mimo稿/episode.mp3",
    "podcast_claude_gemini.mp3": "05_配音/Claude稿_Gemini配音/episode.mp3",
    "podcast_claude_mimo.mp3": "05_配音/Claude稿_MiMo配音/episode.mp3",
    "podcast_mimo_gemini.mp3": "05_配音/MiMo稿_Gemini配音/episode.mp3",
}
for dst, src in AUDIO.items():
    shutil.copy2(os.path.join(SRC, src), os.path.join(A, dst))
for name in ("claude_播客.md", "mimo_播客.md"):
    with open(os.path.join(SRC, "04_文稿", name), encoding="utf-8") as f:
        text = f.read()
    # same text, saved with a UTF-8 signature so browsers show the Chinese correctly when the .md is opened directly
    with open(os.path.join(A, name), "w", encoding="utf-8-sig") as f:
        f.write(text)

# ---------------------------------------------------------------- helpers
CJK = re.compile(r"[㐀-鿿]")


def norm_url(u):
    u = (u or "").strip()
    if not u:
        return ""
    u = u.split("#", 1)[0]
    m = re.match(r"^(https?)://([^/]+)(.*)$", u, re.I)
    if m:
        u = m.group(1).lower() + "://" + m.group(2).lower() + m.group(3)
    return u.rstrip("/")


URL2ID = {}
SRCINFO = {}


def gid(s):
    key = norm_url(s.get("url")) or (s.get("name", "") + "|" + s.get("date", ""))
    if key not in URL2ID:
        URL2ID[key] = "s%02d" % (len(URL2ID) + 1)
        SRCINFO[URL2ID[key]] = {
            "id": URL2ID[key], "name": s.get("name", ""), "url": s.get("url", ""),
            "date": (s.get("date") or "")[:10], "type": s.get("type") or "media",
        }
    return URL2ID[key]


def fmt_num(x):
    s = ("%.2f" % x).rstrip("0").rstrip(".")
    return s


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SPECIAL_EN = {"150亿至160亿": "15–16B", "约 11 小时 / 近 12 小时": "~11 h / ~12 h", "三个": "3", "两年半": "2.5 yrs"}


def value_en(v):
    s = str(v).strip()
    if s in SPECIAL_EN:
        return SPECIAL_EN[s]
    m = re.fullmatch(r"(约\s*)?(-?[\d,]+(?:\.\d+)?)\s*亿美元", s)
    if m:
        return ("~" if m.group(1) else "") + "$" + fmt_num(float(m.group(2).replace(",", "")) / 10) + "B"
    m = re.fullmatch(r"(约\s*)?(-?[\d,]+(?:\.\d+)?)\s*亿元", s)
    if m:
        return ("~" if m.group(1) else "") + "¥" + fmt_num(float(m.group(2).replace(",", "")) / 10) + "B"
    m = re.fullmatch(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", s)
    if m:
        return MONTHS[int(m.group(1)) - 1] + " " + m.group(2)
    m = re.fullmatch(r"(\d{1,2})\s*月", s)
    if m:
        return MONTHS[int(m.group(1)) - 1]
    return None


def split_label(label):
    label = str(label or "").strip()
    if "/" in label:
        left, right = label.split("/", 1)
        if CJK.search(left) and re.match(r"\s*[A-Za-z]", right):
            return left.strip(), right.strip()
    m = re.match(r"^(.*[一-鿿）)])\s*([A-Za-z].*)$", label)
    if m and CJK.search(m.group(1)):
        return m.group(1).strip(), m.group(2).strip()
    return label, label


def fix_chart(ch, local):
    if not ch:
        return ch
    ch = copy.deepcopy(ch)
    unit = str(ch.get("unit") or "")
    billions = unit.startswith("十亿美元")
    dollars = unit.startswith("美元")
    for s in ch.get("series", []):
        zh, en = split_label(s.get("label"))
        s["label"], s["label_en"] = zh, en
        v = float(s.get("value") or 0)
        if billions:
            s["value_en"] = "$" + fmt_num(v)
            s["value"] = round(v * 10, 2) if v * 10 != int(v * 10) else int(v * 10)
        elif dollars:
            s["value_en"] = "$" + fmt_num(v)
    if billions:
        ch.update(unit="亿美元", unit_en="B", unit_note_zh="亿美元", unit_note_en="US$ billion")
    elif dollars:
        ch.update(unit="美元", unit_en="", unit_note_zh="美元", unit_note_en="US$")
    if ch.get("source_id"):
        ch["source_id"] = local.get(ch["source_id"])
    return ch


def bigrams(s):
    s = re.sub(r"[\s，。：:、“”\"'（）()·]", "", s or "")
    return {s[i:i + 2] for i in range(len(s) - 1)}


# ---------------------------------------------------------------- 4. web drafts → editions
def build_sections(web):
    web = copy.deepcopy(web)
    used = []
    for sec in web["sections"]:
        for it in sec["items"]:
            local = {}
            new_sources = []
            for s in it.get("sources") or []:
                g = gid(s)
                local[s.get("id")] = g
                if g not in [x["id"] for x in new_sources]:
                    new_sources.append({"id": g})
                if g not in used:
                    used.append(g)
            it["sources"] = new_sources
            for n in it.get("numbers") or []:
                n["source_id"] = local.get(n.get("source_id")) if n.get("source_id") else None
                if n["source_id"] is None:
                    n.pop("source_id")
                ve = value_en(n.get("value"))
                if ve:
                    n["value_en"] = ve
            if it.get("chart"):
                it["chart"] = fix_chart(it["chart"], local)
            if it.get("id") in IMAGES and sec["kind"] in ("headline", "brief"):
                it["image"] = dict(IMAGES[it["id"]])
            if sec["kind"] == "term":
                it["id"] = "term"
                term = web["daily_card"]["term"]
                it["title_zh"], it["title_en"] = term["zh"], term["en"]
            if sec["kind"] == "cn_intl":
                it.setdefault("region", "cn")
    return web, used


def link_headlines(web):
    items = [(it["id"], (it.get("title_zh") or "") + (it.get("summary_zh") or ""))
             for sec in web["sections"] if sec["kind"] != "term" for it in sec["items"]]
    out = []
    for h in web["daily_card"]["headlines"]:
        hb = bigrams(h["zh"])
        best = max(items, key=lambda x: len(hb & bigrams(x[1])))
        out.append(dict(h, ref=best[0]))
    return out


# ---------------------------------------------------------------- 5. video drafts
def weight(ch):
    if CJK.match(ch):
        return 1.0
    if ch.isdigit():
        return 1.1
    if ch.isascii() and ch.isalpha():
        return 0.3
    if ch in "，。；：！？、,.;:!?":
        return 0.6
    return 0.15


def wlen(s):
    return sum(weight(c) for c in s)


def clauses(text, maxw=22):
    parts, buf = [], ""
    for ch in text:
        buf += ch
        if ch in "，。；：！？,.;:!?":
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    out, cur = [], ""
    for p in parts:
        if cur and wlen(cur + p) > maxw:
            out.append(cur.strip())
            cur = p
        else:
            cur += p
    if cur.strip():
        out.append(cur.strip())
    return out


def anchor(sc, text):
    """time at which `text` (or its first few characters) is spoken in this scene's narration, if it can be found"""
    narr = sc.get("narration_zh") or ""
    t = re.sub(r"\s+", "", str(text or ""))
    n2 = re.sub(r"\s+", "", narr)
    for k in (6, 5, 4, 3, 2):
        key = t[:k]
        if len(key) < 2:
            continue
        i = n2.find(key)
        if i >= 0:
            total = wlen(n2) or 1
            frac = wlen(n2[:i]) / total
            t0, span = sc["start"] + 0.15, max(0.5, sc["end"] - sc["start"] - 0.4)
            return round(t0 + span * frac, 2)
    return None


def build_video(v, audio):
    v = copy.deepcopy(v)
    subs = []
    for sc in v["scenes"]:
        start, end = sc["start"], sc["end"]
        t0, t1 = start + 0.15, end - 0.25
        # zh subtitles: the scene's narration, cut into short clauses, timed by length
        chunks = clauses(sc.get("narration_zh") or "")
        total = sum(wlen(c) for c in chunks) or 1
        acc = 0.0
        for c in chunks:
            w = wlen(c)
            subs.append({"start": round(t0 + (t1 - t0) * acc / total, 2), "end": round(t0 + (t1 - t0) * (acc + w) / total, 2), "zh": c})
            acc += w
        # en subtitles: no English narration, so show the on-screen heading, then the body
        he, be = sc.get("heading_en"), sc.get("body_en")
        if he and be:
            mid = round((t0 + t1) / 2, 2)
            subs.append({"start": round(t0, 2), "end": mid, "en": he})
            subs.append({"start": mid, "end": round(t1, 2), "en": be})
        elif he or be:
            subs.append({"start": round(t0, 2), "end": round(t1, 2), "en": he or be})
        # bilingual bar labels / units
        for b in sc.get("bars") or []:
            zh, en = split_label(b.get("label"))
            b["label"], b["label_en"] = zh, en
            if b.get("unit") == "亿美元":
                b["value_en"], b["unit_en"] = "$" + fmt_num(float(b["value"]) / 10), "B"
        if sc.get("stat"):
            ve = value_en(sc["stat"].get("value"))
            if ve:
                sc["stat"]["value_en"] = ve
        # reveal steps: heading at once, the rest when the narration reaches them (if found)
        steps = {"heading": round(start + 0.15, 2)}
        last = end - 0.7
        if sc.get("bars"):
            bt = [anchor(sc, b["label"]) for b in sc["bars"]]
            if all(x is not None for x in bt) and bt == sorted(bt):
                steps["bars"] = [min(x, last) for x in bt]
        items = sc.get("items_zh") or []
        if items:
            it_t = [anchor(sc, x) for x in items]
            if all(x is not None for x in it_t) and it_t == sorted(it_t):
                steps["items"] = [min(x, last) for x in it_t]
            else:  # spread evenly over the scene instead of bunching at the start
                span = max(1.0, (end - start) * 0.7)
                steps["items"] = [round(start + 0.6 + span * k / max(1, len(items)), 2) for k in range(len(items))]
        if sc.get("stat"):
            st = anchor(sc, sc["stat"].get("value")) or anchor(sc, sc["stat"].get("label_zh"))
            if st is not None:
                steps["stat"] = min(max(st - 0.2, start + 0.3), last)
                steps["label"] = min(steps["stat"] + 0.5, last)
        if sc.get("quote"):
            q = anchor(sc, sc["quote"].get("text_zh"))
            if q is not None:
                steps["quote"] = min(max(q - 0.2, start + 0.3), last)
        if sc.get("source") and sc["type"] != "source":
            steps["source"] = round(start + 1.0, 2)
        sc["steps"] = steps
        if sc["type"] == "title":
            sc["background"] = {"src": "assets/card.jpg", "flip": True}
    v["subtitles"] = subs
    v["audio"] = audio
    real = duration(os.path.join(OUT, audio))
    if abs(real - v["duration"]) > 0.5:
        print("WARN video duration", audio, v["duration"], "vs audio", real)
    return v


# ---------------------------------------------------------------- 6. podcast
CH_EN = {"开场": "Opening", "热点一": "Top story 1", "热点二": "Top story 2", "要闻": "Briefs", "快讯": "In brief",
         "今日一词": "Word of the day", "预告观察": "Teaser watch", "结尾": "Closing"}


def chapters(rel):
    out = []
    for c in jload(rel)["chapters"]:
        zh = c["title"].strip()
        en = next((v for k, v in CH_EN.items() if zh.startswith(k)), zh)
        out.append({"start": round(float(c["startTime"]), 2), "title_zh": zh, "title_en": en})
    return out


def variant(vid, writer, voice, folder, mp3, transcript):
    model = {"Gemini": "Gemini 3.8 Flash TTS", "MiMo": "MiMo-V2.5-TTS"}[voice]
    return {
        "id": vid,
        "label_zh": f"{writer} 稿 · {voice} 配音", "label_en": f"{writer} script · {voice} voice",
        "file": "assets/" + mp3, "duration": duration(os.path.join(A, mp3)),
        "chapters": chapters(f"05_配音/{folder}/chapters.json"),
        "note_zh": f"{writer} 写稿，{model} 配音（AI 合成语音）。",
        "note_en": f"Script by {writer}; voiced by {model} (synthetic voice).",
        "transcript": {"href": "assets/" + transcript, "label_zh": f"读文字稿（{writer} 稿）", "label_en": f"Read the script ({writer})"},
    }


PODCAST = {
    "title_zh": "每日前沿简报 · 10 月 31 日", "title_en": "Frontier Daily · Oct 31",
    "variants": [
        variant("claude-gemini", "Claude", "Gemini", "Claude稿_Gemini配音", "podcast_claude_gemini.mp3", "claude_播客.md"),
        variant("claude-mimo", "Claude", "MiMo", "Claude稿_MiMo配音", "podcast_claude_mimo.mp3", "claude_播客.md"),
        variant("mimo-gemini", "MiMo", "Gemini", "MiMo稿_Gemini配音", "podcast_mimo_gemini.mp3", "mimo_播客.md"),
    ],
}
PODCAST["chapters"] = PODCAST["variants"][0]["chapters"]

# ---------------------------------------------------------------- 7. assemble
DISCLOSURE_ZH = ("本页由 AI 辅助生成，尚未经人工终审；每条均附原文链接，数字以原文为准。“为什么重要”是解读，与事实分开写。"
                 "视频和播客使用 AI 合成语音。文稿和音频里“经人工审核”的说法来自写稿模板，这一版还没有做人工终审。")
DISCLOSURE_EN = ("This page was drafted with AI assistance and has not yet had a final human review; every item links to its sources, "
                 "and the originals take precedence for any number. 'Why it matters' is interpretation, kept apart from the facts. "
                 "Video and podcast use synthetic voices. Where the scripts or audio say 'reviewed by a human editor', that is template "
                 "wording; this build has not been through final review.")

editions = []
for eid, label_zh, label_en in (("claude", "Claude 稿", "Claude draft"), ("mimo", "MiMo 稿", "MiMo draft")):
    web, used = build_sections(jload(f"04_文稿/{eid}_网页.json"))
    heads = link_headlines(web)
    term = dict(web["daily_card"]["term"], ref="term")
    vid = build_video(jload(f"04_文稿/{eid}_视频_定时.json"), f"assets/video_{eid}.mp3")
    editions.append({
        "id": eid, "label_zh": label_zh, "label_en": label_en,
        "daily_card": {"headlines": heads, "term": term},
        "video": vid,
        "sections": web["sections"],
        "sources": [SRCINFO[i] for i in used],
        "disclosure_zh": DISCLOSURE_ZH, "disclosure_en": DISCLOSURE_EN,
    })
    print(eid, "headline refs:", [(h["zh"][:12], h["ref"]) for h in heads], "| sources:", len(used),
          "| scenes:", len(vid["scenes"]), "| subtitles:", len(vid["subtitles"]),
          "| steps:", [sorted(s["steps"].keys()) for s in vid["scenes"]])

now = datetime.now(timezone.utc).astimezone()
ISSUE = {
    "date": "2026-10-31",
    "weekday_zh": "星期六",
    "weekday_en": "Saturday",
    "meta": {
        "edition_zh": "测试版：按工作日版面", "edition_en": "Test build: weekday layout",
        "notice_tag_zh": "测试版", "notice_tag_en": "Test build",
        "notice_zh": "真实数据，2026-10-29 至 10-31；AI 辅助生成，未经人工终审。",
        "notice_en": "Real data from Oct 29–31, 2026; AI-assisted, not yet given a final human review.",
        "card_foot_zh": "AI 辅助生成 · 未经人工终审", "card_foot_en": "AI-assisted · not yet human-reviewed",
        "site": "frontier.wenlongzhang.com",
        "generated_at": now.isoformat(timespec="minutes"),
        "how_zh": "选题、事件卡与写稿：Claude 和 MiMo 各写一版（页面顶部切换）；配音：Gemini 3.8 Flash TTS 与 MiMo-V2.5-TTS；配图：Codex 生成；网页由 site/ 模板组装。",
        "how_en": "Story selection, event cards and writing: one version each by Claude and MiMo (switch at the top); voices: Gemini 3.8 Flash TTS and MiMo-V2.5-TTS; images: generated with Codex; page assembled from the site/ template.",
        "contact_zh": "测试版，暂不公开。", "contact_en": "Test build, not public.",
    },
    "daily_card": {"image": dict(src=CARD_URI, **CARD_ALT)},
    "podcast": PODCAST,
    "default_edition": "claude",
    "editions": editions,
}

head = ("/* frontier-daily · 测试版 2026-10-31（真实数据，按工作日版面）\n"
        " * 由 site/tools/build_testpage.py 从 04_文稿、05_配音、06_配图 组装；页面代码来自 site/ 模板。\n"
        " * editions：Claude 稿 / MiMo 稿；播客三个版本共用。日卡配图以 data URI 内嵌，便于双击打开时也能“保存为图片”。 */\n")
with open(os.path.join(OUT, "issue.js"), "w", encoding="utf-8") as f:
    f.write(head + "window.ISSUE = " + json.dumps(ISSUE, ensure_ascii=False, indent=1) + ";\n")

print("images:", {k: (v[0], round(v[1] / 1024)) for k, v in sizes.items()}, "| card inline KB:", round(len(card_inline) / 1024))
print("podcast:", [(v["id"], v["duration"], len(v["chapters"])) for v in PODCAST["variants"]])
print("issue.js KB:", round(os.path.getsize(os.path.join(OUT, "issue.js")) / 1024))
