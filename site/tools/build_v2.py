#!/usr/bin/env python3
"""v2 网页组装：site/v2 模板 + 一期数据 → <期目录>/08_网页v2/（双击 index.html 即可看）

用法（在项目根目录 frontier-daily/ 下）：
    python3 site/tools/build_v2.py 测试版/2026-10-31
    python3 site/tools/build_v2.py 测试版/2026-10-31 --podcast 05_配音/v2_xxx    # 换成 v2 播客
    python3 site/tools/build_v2.py 测试版/2026-10-31 --out 某个站点目录           # 多期共用一个站点目录
每期的编辑决定（今日数字、图表、预告看板、对照、配图说明、视频节拍）在 site/tools/v2_issues/<日期>.py。
视频 v2：旁白逐字对齐（video_align.py，本机 Whisper，离线）→ 场景计划与模板选择（video_plan.py）→ site/v2/video2.js 播放。
只读输入，只写输出目录。依赖：Python 标准库、Pillow、ffmpeg/ffprobe；视频 v2 首次组装要本机 mlx_whisper（之后用缓存）。不调用任何模型接口。
"""
import argparse
import array
import copy
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(HERE)
ROOT = os.path.dirname(SITE)

ap = argparse.ArgumentParser(description="组装 v2 网页")
ap.add_argument("issue_dir", help="期目录，如 测试版/2026-10-31")
ap.add_argument("--out", help="输出目录（默认 <期目录>/08_网页v2）")
ap.add_argument("--podcast", help="播客文件夹（相对期目录），覆盖配置里的 PODCAST_DIR")
args = ap.parse_args()

SRC = os.path.normpath(os.path.join(ROOT, args.issue_dir))
DATE = os.path.basename(SRC)
if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", DATE):
    sys.exit("期目录名应是日期，如 2026-10-31")
spec = importlib.util.spec_from_file_location("cfg", os.path.join(HERE, "v2_issues", DATE + ".py"))
CFG = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CFG)
OUT = os.path.normpath(os.path.join(ROOT, args.out)) if args.out else os.path.join(SRC, "08_网页v2")
ISS = os.path.join(OUT, "issues", DATE)
PODCAST_DIR = args.podcast or CFG.PODCAST_DIR
for d in (OUT, os.path.join(OUT, "vendor"), os.path.join(ISS, "img"), os.path.join(ISS, "audio")):
    os.makedirs(d, exist_ok=True)


def jload(rel):
    with open(os.path.join(SRC, rel), encoding="utf-8") as f:
        return json.load(f)


def ffprobe(path, entry):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=" + entry, "-of", "csv=p=0", path],
                       check=True, capture_output=True, text=True)
    return r.stdout.strip()


WEB = jload(CFG.WEB)
CARDS = {c["event_id"]: c for c in jload(CFG.CARDS)}
CANDS = jload(CFG.CANDIDATES)
CJK = re.compile(r"[㐀-鿿]")

# ---------------------------------------------------------------- 1. 来源：按网址去重，配上原标题
URL_TITLE = {}
EVENT_MEMBERS = {}
REGION = {}


def norm_url(u):
    u = (u or "").strip().split("#", 1)[0]
    m = re.match(r"^(https?)://([^/]+)(.*)$", u, re.I)
    if m:
        u = m.group(1).lower() + "://" + m.group(2).lower().replace("www.", "") + m.group(3)
    return u.rstrip("/")


for pool in ("events", "social_only", "lang_edu_column"):
    for ev in CANDS.get(pool, []):
        EVENT_MEMBERS.setdefault(ev["event_id"], ev.get("members", []))
        if ev.get("subject_region"):
            REGION.setdefault(ev["event_id"], ev["subject_region"])
        for m in ev.get("members", []):
            URL_TITLE.setdefault(norm_url(m.get("url")), m.get("title") or "")

SOURCES = {}
URL2ID = {}


def gid(s):
    key = norm_url(s.get("url")) or (s.get("name", "") + "|" + s.get("date", ""))
    if key not in URL2ID:
        sid = "s%02d" % (len(URL2ID) + 1)
        URL2ID[key] = sid
        name = re.sub(r"[：:]\s*[A-Za-z].*$", "", s.get("name", "")).strip()
        SOURCES[sid] = {"id": sid, "name": name, "title": URL_TITLE.get(key, ""), "url": s.get("url", ""),
                        "date": (s.get("date") or "")[:10], "type": s.get("type") or "media"}
    return URL2ID[key]


# ---------------------------------------------------------------- 2. 指回事件卡：数字和事实必须能在原条目里找到
def ref(r):
    ev, key, check = r
    card = CARDS[ev]
    ent = card["facts" if key[0] == "F" else "numbers"][int(key[1:])]
    text = " ".join(str(ent.get(k) or "") for k in
                    ("text_zh", "text_en", "quote", "value", "unit", "meaning_zh", "meaning_en", "compare_zh"))
    if check not in text:
        sys.exit(f"核对失败：{ev} {key} 里找不到「{check}」。图表、今日数字、预告看板只能用事件卡里有出处的数字和事实。")
    src = next(s for s in card["sources"] if s["id"] == ent["source_id"])
    return gid(src)


# ---------------------------------------------------------------- 3. 正文引用：每句话对回事件卡里最像的那条事实，用那条的出处
def bigr(s):
    s = re.sub(r"[\s，。：:、“”\"'‘’（）()·；;,.!?！？《》「」【】—/-]", "", (s or "").lower())
    return {s[i:i + 2] for i in range(len(s) - 1)}


STOP = set("the a an of to in on at by for with from as is are was were be been that this it its their his her has have had "
           "not but or than then into over about after before more less also said says say per via who what which when how "
           "and so up out".split())


def words(s):
    return {w for w in re.findall(r"[a-z0-9][a-z0-9.'’%-]*[a-z0-9%]|[a-z0-9]", (s or "").lower()) if w not in STOP}


FACTS = {}
for ev, card in CARDS.items():
    lst = []
    for f in card["facts"]:
        sid = gid(next(s for s in card["sources"] if s["id"] == f["source_id"]))
        lst.append({"sid": sid, "B": bigr(f.get("text_zh")), "W": words(f.get("text_en"))})
    for n in card["numbers"]:
        sid = gid(next(s for s in card["sources"] if s["id"] == n["source_id"]))
        lst.append({"sid": sid, "B": bigr((n.get("meaning_zh") or "") + str(n.get("value")) + (n.get("compare_zh") or "")),
                    "W": words((n.get("meaning_en") or "") + " " + str(n.get("value")))})
    FACTS[ev] = lst

INTERP = re.compile(r"我们的理解|我们的判断|[Oo]ur read")
TH = {"zh": 0.3, "en": 0.3}


def cites_for(sent, evs, lang):
    if INTERP.search(sent):
        return []
    S = bigr(sent) if lang == "zh" else words(sent)
    if not S:
        return []
    denom = max(16, len(S)) if lang == "zh" else max(8, len(S))
    key = "B" if lang == "zh" else "W"
    scored = sorted(((len(S & f[key]) / denom, f["sid"]) for ev in evs for f in FACTS.get(ev, [])), key=lambda x: -x[0])
    out = []
    best = scored[0][0] if scored else 0
    for sc, sid in scored:
        if sc < TH[lang] or sc < best * 0.7:
            break
        if sid not in out:
            out.append(sid)
        if len(out) == 2:
            break
    return out


def split_sents(p, lang):
    if lang == "zh":
        return [s for s in re.split(r"(?<=[。！？])(?![”」』）)])", p) if s.strip()]
    return [s.strip() for s in re.split(r"(?:(?<=[.!?])|(?<=[.!?][”\"’)]))\s+(?=[A-Z“\"‘(])", p) if s.strip()]


def tok(cs):
    return "".join("[^%s]" % c for c in cs)


def cite_paras(text, evs, lang):
    """text → (段落列表，带 [^sNN]；每句的 (句子, 出处) 列表)。同一出处连续几句，只在最后一句后标一次。"""
    paras, sents_all = [], []
    for p in [x.strip() for x in re.split(r"\n+", text or "") if x.strip()]:
        sents = split_sents(p, lang)
        cs = [cites_for(s, evs, lang) for s in sents]
        buf = ""
        for i, s in enumerate(sents):
            buf += s
            if cs[i] and (i == len(sents) - 1 or cs[i + 1] != cs[i]):
                buf += tok(cs[i])
            if lang == "en" and i < len(sents) - 1:
                buf += " "
        paras.append(buf)
        sents_all.append(list(zip(sents, cs)))
    return paras, sents_all


def lead3(sents_all):
    """“三句话”：每段第一句，不够三句就按顺序补。"""
    picked = [ps[0] for ps in sents_all if ps][:3]
    rest = [x for ps in sents_all for x in ps[1:]]
    while len(picked) < 3 and rest:
        picked.append(rest.pop(0))
    return [s + tok(c) for s, c in picked]


# ---------------------------------------------------------------- 4. 小工具（与第一版 build_testpage.py 相同的口径）
def fmt_num(x):
    return ("%.2f" % x).rstrip("0").rstrip(".")


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


# ---------------------------------------------------------------- 5. 配图：PNG → 约 1400 宽的 WebP
IMG = {}
for key, spec_ in CFG.IMAGES.items():
    src = os.path.join(SRC, "06_配图", spec_["file"])
    if not os.path.exists(src):
        print("缺图（页面会用占位样式）：", spec_["file"])
        continue
    im = Image.open(src).convert("RGB")
    width = 900 if im.width <= im.height else 1400
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    name = ("card" if key == "card" else key.lower()) + ".webp"
    im.save(os.path.join(ISS, "img", name), "WEBP", quality=78, method=6)
    IMG[key] = {"src": "img/" + name, "w": im.width, "h": im.height, "alt_zh": spec_["alt_zh"], "alt_en": spec_["alt_en"],
                **CFG.CREDIT}

# ---------------------------------------------------------------- 6. 播客：一版音频、章节、波形、每条“听这一段”的时刻
pdir = os.path.join(SRC, PODCAST_DIR)
p_src = os.path.join(pdir, "episode.mp3")
p_dst = os.path.join(ISS, "audio", "podcast.mp3")
rate = int(ffprobe(p_src, "bit_rate") or 0)
if rate > 80000:   # 单声道 64 kbps 足够听清人声，体积约为原来的三分之二
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", p_src, "-ac", "1", "-b:a", "64k", "-map_metadata", "-1", p_dst], check=True)
else:
    shutil.copy2(p_src, p_dst)
p_dur = round(float(ffprobe(p_dst, "duration")), 2)

CH_EN = {"开场": "Opening", "热点一": "Top story 1", "热点二": "Top story 2", "热点三": "Top story 3", "要闻": "Briefs",
         "快讯": "In brief", "今日一词": "Word of the day", "预告观察": "On the radar", "预告": "On the radar", "结尾": "Closing"}
chapters = []
for c in json.load(open(os.path.join(pdir, "chapters.json"), encoding="utf-8"))["chapters"]:
    zh = c["title"].strip()
    chapters.append({"start": round(float(c["startTime"]), 2), "title_zh": zh,
                     "title_en": next((v for k, v in CH_EN.items() if zh.startswith(k)), zh)})

# 波形：解码成 2 kHz 单声道，切 160 段取均方根（真实音量，不是装饰）
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p_dst, "-ac", "1", "-ar", "2000", "-f", "s16le", "-"],
                     check=True, capture_output=True).stdout
pcm = array.array("h")
pcm.frombytes(raw[: len(raw) // 2 * 2])
NB = 160
step = max(1, len(pcm) // NB)
peaks = []
for i in range(NB):
    seg = pcm[i * step:(i + 1) * step]
    peaks.append(math.sqrt(sum(x * x for x in seg) / len(seg)) if len(seg) else 0)
top = max(peaks) or 1
peaks = [round(math.sqrt(p / top), 2) for p in peaks]

# 每段文字在音频里的大致起点：qc.json 有分块的起止时间和原稿，块内按字数比例估算。
# 两种 qc.json 都认：① 纯人声版，直接有“各块”；② 混了片头曲、转场音的版本，有“时间线”（人声·某章 从第几秒开始）
#    和“人声来源”（纯人声版文件夹），这时用纯人声版的分块，再按章平移到混音后的时间上。
PARAS = []


def qc_blocks(folder):
    p = os.path.join(folder, "qc.json")
    if not os.path.exists(p):
        return []
    q = json.load(open(p, encoding="utf-8"))
    if q.get("各块"):
        return q["各块"]
    src = q.get("人声来源")
    tl = {x.get("段", "")[3:]: x["开始秒"] for x in q.get("时间线", []) if x.get("段", "").startswith("人声·")}
    if not src or not tl:
        return []
    vdir = src if os.path.isabs(src) else os.path.join(ROOT, src)
    if not os.path.isdir(vdir):
        vdir = os.path.join(SRC, "05_配音", os.path.basename(os.path.normpath(src)))
    blocks = qc_blocks(vdir)
    first = {}
    for b in blocks:
        first.setdefault(b.get("章", ""), b["开始秒"])
    out = []
    for b in blocks:
        ch = b.get("章", "")
        if ch in tl:
            out.append(dict(b, 开始秒=round(tl[ch] + b["开始秒"] - first[ch], 2)))
    return out


for b in qc_blocks(pdir):
    ps = [p for p in (b.get("原稿") or "").split("\n") if p.strip()]
    total = sum(len(p) for p in ps) or 1
    acc = 0
    for p in ps:
        PARAS.append({"ch": b.get("章", ""), "t": round(b["开始秒"] + b["秒数"] * acc / total, 1), "text": p})
        acc += len(p)
KIND_CH = {"headline": ("热点", "头条"), "brief": ("要闻",), "cn_intl": ("要闻", "对照"), "flash": ("快讯",),
           "term": ("一词",), "teaser": ("预告",)}


def has_key(title, keys):
    return any(k in title for k in keys)


def listen_at(kind, text, nth=None):
    keys = KIND_CH.get(kind, ())
    if kind == "headline" and nth is not None:
        hot = [c for c in chapters if has_key(c["title_zh"], keys)]
        if nth < len(hot):
            return hot[nth]["start"]
    cand = [p for p in PARAS if has_key(p["ch"], keys)] or PARAS
    if cand:
        B = bigr(text)
        sc = [len(B & bigr(p["text"])) for p in cand]
        top = max(sc)
        if top >= 4:
            first = next(p for p, x in zip(cand, sc) if x >= max(4, top * 0.6))
            return max(0, round(first["t"] - 0.5, 1))
    ch = next((c for c in chapters if has_key(c["title_zh"], keys)), None)
    return ch["start"] if ch else None


# ---------------------------------------------------------------- 7. 视频：沿用第一版播放器和定时稿（video.js 不改）
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
    narr = re.sub(r"\s+", "", sc.get("narration_zh") or "")
    t = re.sub(r"\s+", "", str(text or ""))
    for k in (6, 5, 4, 3, 2):
        key = t[:k]
        if len(key) < 2:
            continue
        i = narr.find(key)
        if i >= 0:
            frac = wlen(narr[:i]) / (wlen(narr) or 1)
            t0, span = sc["start"] + 0.15, max(0.5, sc["end"] - sc["start"] - 0.4)
            return round(t0 + span * frac, 2)
    return None


def build_video(v, audio, card_src):
    v = copy.deepcopy(v)
    subs = []
    for sc in v["scenes"]:
        start, end = sc["start"], sc["end"]
        t0, t1 = start + 0.15, end - 0.25
        chunks = clauses(sc.get("narration_zh") or "")
        total = sum(wlen(c) for c in chunks) or 1
        acc = 0.0
        for c in chunks:
            w = wlen(c)
            subs.append({"start": round(t0 + (t1 - t0) * acc / total, 2), "end": round(t0 + (t1 - t0) * (acc + w) / total, 2), "zh": c})
            acc += w
        he, be = sc.get("heading_en"), sc.get("body_en")
        if he and be:
            mid = round((t0 + t1) / 2, 2)
            subs.append({"start": round(t0, 2), "end": mid, "en": he})
            subs.append({"start": mid, "end": round(t1, 2), "en": be})
        elif he or be:
            subs.append({"start": round(t0, 2), "end": round(t1, 2), "en": he or be})
        for b in sc.get("bars") or []:
            zh, en = split_label(b.get("label"))
            b["label"], b["label_en"] = zh, en
            if b.get("unit") == "亿美元":
                b["value_en"], b["unit_en"] = "$" + fmt_num(float(b["value"]) / 10), "B"
        if sc.get("stat"):
            ve = value_en(sc["stat"].get("value"))
            if ve:
                sc["stat"]["value_en"] = ve
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
            else:
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
        if sc["type"] == "title" and card_src:
            sc["background"] = {"src": card_src, "flip": True}
    v["subtitles"] = subs
    v["audio"] = audio
    return v


shutil.copy2(os.path.join(SRC, CFG.VIDEO_AUDIO), os.path.join(ISS, "audio", "video.mp3"))
VIDEO = build_video(jload(CFG.VIDEO_SCRIPT), "audio/video.mp3", IMG.get("card", {}).get("src"))
v_real = float(ffprobe(os.path.join(ISS, "audio", "video.mp3"), "duration"))
if abs(v_real - VIDEO["duration"]) > 0.5:
    print("注意：视频时间轴", VIDEO["duration"], "与旁白音频", round(v_real, 2), "不一致")

# ---------------------------------------------------------------- 7b. 视频 v2：逐字对齐 → 场景计划（模板按内容自动选）→ video2.js
sys.path.insert(0, HERE)
import video_align  # noqa: E402
import video_plan  # noqa: E402

VDIR = os.path.join(ISS, "video")
os.makedirs(VDIR, exist_ok=True)
V_SCRIPT = jload(CFG.VIDEO_SCRIPT)
V_AUDIO = os.path.join(SRC, CFG.VIDEO_AUDIO)
V_NARR = [sc.get("narration_zh") or "" for sc in V_SCRIPT["scenes"]]
latin = list(dict.fromkeys(re.findall(r"[A-Za-z][A-Za-z0-9&.\-]+", "".join(V_NARR))))
WORDS = video_align.load_words(V_AUDIO, os.path.join(VDIR, "whisper_words.json"),
                               prompt="以下是简体中文的科技新闻解说" + ("：" + "、".join(latin) if latin else "") + "。")


def vref(r):
    """视频节拍里的 ref：F/N 同上面的 ref()；Q 指事件卡 open_questions_zh 的第几条（编辑判断，没有单独出处）"""
    ev, key, check = r
    if key[0] == "Q":
        qs = CARDS[ev].get("open_questions_zh") or []
        if int(key[1:]) >= len(qs) or check not in qs[int(key[1:])]:
            sys.exit(f"核对失败：{ev} {key} 里找不到「{check}」。")
        return None
    return ref(r)


EN_MEDIA = [("彭博 Bloomberg", "Bloomberg"), ("《金融时报》", "Financial Times"), ("《华尔街日报》", "WSJ"), ("虎嗅", "Huxiu"),
            ("（经 ", " (via "), ("）", ")")]


def src_name(sid):
    """来源的短名：“Techmeme（转述《金融时报》相关报道）”→“《金融时报》（经 Techmeme）”"""
    n = SOURCES[sid]["name"]
    m = re.match(r"^(.+?)（转述(.+?)相关报道）$", n)
    zh = m.group(2) + "（经 " + m.group(1) + "）" if m else re.sub(r"（.*?）|\s*·\s*科技$", "", n).strip()
    en = zh
    for a, b in EN_MEDIA:
        en = en.replace(a, b)
    return zh, en


VIDEO2, PLAN, AL = None, None, None
if WORDS:
    chp = os.path.join(os.path.dirname(V_AUDIO), "chapters.json")
    bounds = [c["startTime"] for c in json.load(open(chp, encoding="utf-8"))["chapters"]] if os.path.exists(chp) else None
    AL = video_align.align(V_NARR, WORDS, V_AUDIO, round(v_real, 3), bounds if bounds and len(bounds) == len(V_NARR) else None)
    beats_cfg = getattr(CFG, "VIDEO_BEATS", None)          # 每期配置里手写的节拍表
    bfile = getattr(CFG, "VIDEO_BEATS_FILE", None)          # 或者流水线写视频稿时一起输出的节拍表 JSON（同样的结构）
    if beats_cfg is None and bfile and os.path.exists(os.path.join(SRC, bfile)):
        beats_cfg = jload(bfile)
    try:
        PLAN = video_plan.build(beats_cfg, AL, v_real, vref, src_name, IMG, V_SCRIPT)
    except video_plan.PlanError as e:
        sys.exit("视频节拍有问题：" + str(e))
    VIDEO2 = {"v": 2, "title_zh": V_SCRIPT.get("title_zh", ""), "title_en": V_SCRIPT.get("title_en", ""),
              "audio": "audio/video.mp3", "duration": round(v_real, 2), "beats": PLAN["beats"],
              "cues": [{k: c[k] for k in ("start", "end", "text", "t")} for c in AL["cues"]],
              "templates": PLAN["templates_used"], "auto_plan": PLAN["auto"], "numbers_checked": PLAN["checked"],
              "sync": AL["accuracy"]}
    with open(os.path.join(VDIR, "align.json"), "w", encoding="utf-8") as f:
        json.dump({"说明": "旁白逐字对齐：每个字（units）、每句（sentences）、每段字幕（cues，含逐字时间 t）、每个触发词（keywords）的出现秒数",
                   "audio": "../audio/video.mp3", "script": CFG.VIDEO_SCRIPT, "engine": AL["engine"], "accuracy": AL["accuracy"],
                   "scenes": AL["scenes"], "sentences": AL["sentences"], "keywords": PLAN["keywords"], "cues": AL["cues"],
                   "units": AL["units"]}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(VDIR, "plan.json"), "w", encoding="utf-8") as f:
        json.dump({"说明": "视频 v2 场景计划：每屏的模板、起止秒和元素出现时刻（由 build_v2.py 生成，播放器读 issue.js 里的同一份）",
                   "templates_library": video_plan.TEMPLATES, **{k: v for k, v in VIDEO2.items() if k != "cues"}},
                  f, ensure_ascii=False, indent=1)
else:
    print("注意：没有旁白的逐词时间（本机没有 mlx_whisper，也没有缓存），视频沿用第一版")


# ---------------------------------------------------------------- 8. 稿件条目 → stories
def coverage(ev):
    out = {"zh": [], "en": [], "social": []}
    for m in EVENT_MEMBERS.get(ev, []):
        name = re.sub(r"（.*?）", "", m.get("source_name") or "").strip()
        if not name:
            continue
        layer = m.get("layer") or "social"
        grp = "social" if layer in ("community", "social") or not m.get("lang") else ("zh" if m.get("lang") == "zh" else "en")
        if name not in out[grp]:
            out[grp].append(name)
    return out


STORIES, ORDER = {}, {}
n_head = 0
for sec in WEB["sections"]:
    kind = sec["kind"]
    for it in sec["items"]:
        ev = it["id"]
        sid = "term" if kind == "term" else ev
        local = {s["id"]: gid(s) for s in it.get("sources") or []}
        evs = [ev] + ([r["id"] for r in it.get("related") or []] if kind == "term" else [])
        st = {"id": sid, "ev": ev, "kind": kind, "status": it.get("status") or "reported", "region": REGION.get(ev, "intl"),
              "title_zh": it.get("title_zh", ""), "title_en": it.get("title_en", ""),
              "summary_zh": it.get("summary_zh", ""), "summary_en": it.get("summary_en", ""),
              "sources": list(dict.fromkeys(local.values()))}
        for L in ("zh", "en"):
            body, sents = cite_paras(it.get("body_" + L), evs, L)
            st["body_" + L] = body
            st["lead_" + L] = lead3(sents)
            st["why_" + L] = cite_paras(it.get("why_" + L), evs, L)[0]
        nums = []
        for n in it.get("numbers") or []:
            x = {"value": n.get("value"), "label_zh": n.get("label_zh", ""), "label_en": n.get("label_en", "")}
            if local.get(n.get("source_id")):
                x["cite"] = local[n["source_id"]]
            ve = value_en(n.get("value"))
            if ve:
                x["value_en"] = ve
            nums.append(x)
        st["numbers"] = nums
        st["related"] = [{"id": r["id"], "note_zh": r.get("note_zh", ""), "note_en": r.get("note_en", "")} for r in it.get("related") or []]
        st["coverage"] = coverage(ev)
        if (sid if kind == "term" else ev) in IMG:
            st["image"] = IMG[sid if kind == "term" else ev]
        st["listen"] = listen_at(kind, (it.get("title_zh") or "") + (it.get("summary_zh") or ""), n_head if kind == "headline" else None)
        if kind == "headline":
            n_head += 1
            st["charts"] = CFG.STORY_CHARTS.get(ev, [])
        STORIES[sid] = st
        ORDER.setdefault(kind, []).append(sid)

# “看这一段”：视频 v2 按节拍的事件号，取这条事件最早出现的那一屏；第一版按标题相似度归属场景
if VIDEO2:
    for i, b in enumerate(VIDEO2["beats"]):
        if b.get("ev") in STORIES and b["tpl"] != "recap" and "watch" not in STORIES[b["ev"]]:
            STORIES[b["ev"]]["watch"] = {"scene": i, "t": b["start"]}
SCENE_OWNER = {}
for k, st in ({} if VIDEO2 else STORIES).items():
    if st["kind"] == "term":
        continue
    B = bigr(st["title_zh"])
    for i, sc in enumerate(VIDEO["scenes"]):
        if sc["type"] in ("title", "source"):
            continue
        s = len(B & bigr((sc.get("heading_zh") or "") + (sc.get("narration_zh") or ""))) / (len(B) or 1)
        if s >= 0.3 and s > SCENE_OWNER.get(i, (None, 0))[1]:
            SCENE_OWNER[i] = (k, s)
for i in sorted(SCENE_OWNER):
    k = SCENE_OWNER[i][0]
    STORIES[k].setdefault("watch", {"scene": i, "t": VIDEO["scenes"][i]["start"]})

# 日卡三件事 → 对应条目
items_text = [(k, (v["title_zh"] or "") + (v["summary_zh"] or "")) for k, v in STORIES.items() if v["kind"] != "term"]
heads = []
for h in WEB["daily_card"]["headlines"]:
    hb = bigr(h["zh"])
    best = max(items_text, key=lambda x: len(hb & bigr(x[1])))
    heads.append(dict(h, ref=best[0]))
term_card = WEB["daily_card"]["term"]

# ---------------------------------------------------------------- 9. 今日数字、图表、预告看板、对照（全部过 ref 核对）
NUMBERS = []
for n in CFG.NUMBERS:
    x = {k: v for k, v in n.items() if k not in ("ref", "sub_ref")}
    x["cite"] = [ref(n["ref"])] + ([ref(n["sub_ref"])] if n.get("sub_ref") else [])
    x["cite"] = list(dict.fromkeys(x["cite"]))
    NUMBERS.append(x)

CHARTS = {}
for cid, ch in CFG.CHARTS.items():
    ch = copy.deepcopy(ch)
    cites = []

    def take(o, k="ref"):
        if o.get(k):
            s = ref(o.pop(k))
            o["cite" if k == "ref" else k.replace("ref", "cite")] = s
            cites.append(s)
    for row in ch.get("rows", []):
        for p in row["points"]:
            take(p)
    for k in ("items", "links"):
        for o in ch.get(k, []):
            take(o)
            take(o, "extra_ref")
    if ch.get("base"):
        take(ch["base"])
    take(ch, "note_ref")
    ch["cites"] = list(dict.fromkeys(cites))
    CHARTS[cid] = ch

WATCH = []
for w in CFG.WATCH:
    x = {k: v for k, v in w.items() if k != "refs"}
    x["cite"] = list(dict.fromkeys(ref(r) for r in w["refs"]))
    WATCH.append(x)

PAIRS = []
for p in CFG.PAIRS:
    cn = STORIES[p["cn"]]
    note = next((r for r in cn["related"] if r["id"] == p["intl"]), None) or \
        next((r for r in STORIES[p["intl"]]["related"] if r["id"] == p["cn"]), {})
    PAIRS.append(dict(p, note_zh=note.get("note_zh", ""), note_en=note.get("note_en", "")))

# ---------------------------------------------------------------- 10. 写出
podcast = {
    "file": "audio/podcast.mp3", "duration": p_dur, "chapters": chapters, "peaks": peaks,
    "title_zh": "每日AI科技前沿简报 · %d 月 %d 日" % (int(DATE[5:7]), int(DATE[8:10])),
    "title_en": "Daily AI & Tech Frontier · %s %d" % (MONTHS[int(DATE[5:7]) - 1], int(DATE[8:10])),
}
now = datetime.now(timezone.utc).astimezone()
ISSUE = {
    "date": DATE, "weekday_zh": CFG.WEEKDAY[0], "weekday_en": CFG.WEEKDAY[1],
    "meta": {"test": True, "generated_at": now.isoformat(timespec="minutes"), "site": "frontier.wenlongzhang.com",
             "draft": CFG.WEB, "podcast_dir": PODCAST_DIR},
    "card": {"headlines": heads, "term": dict(term_card, ref="term"), "image": IMG.get("card")},
    "numbers": NUMBERS,
    "media": {"video": VIDEO2 or VIDEO, "podcast": podcast},
    "stories": STORIES, "order": ORDER,
    "charts": CHARTS, "flash_chart": CFG.FLASH_CHART,
    "watch": WATCH, "pairs": PAIRS,
    "sources": [SOURCES[k] for k in sorted(SOURCES)],
}
with open(os.path.join(ISS, "issue.js"), "w", encoding="utf-8") as f:
    f.write("/* 每日AI科技前沿简报 · %s · 由 site/tools/build_v2.py 组装，请勿手改 */\n" % DATE)
    f.write("window.FD_ISSUES = window.FD_ISSUES || {};\n")
    f.write("window.FD_ISSUES[%s] = %s;\n" % (json.dumps(DATE), json.dumps(ISSUE, ensure_ascii=False, separators=(",", ":"))))
with open(os.path.join(ISS, "summary.json"), "w", encoding="utf-8") as f:
    json.dump({"date": DATE, "weekday_zh": CFG.WEEKDAY[0], "weekday_en": CFG.WEEKDAY[1],
               "lead_zh": heads[0]["zh"] if heads else "", "lead_en": heads[0]["en"] if heads else ""}, f, ensure_ascii=False)

# 往期目录：扫描 issues/*/summary.json
idx = []
for d in sorted(os.listdir(os.path.join(OUT, "issues"))):
    sp = os.path.join(OUT, "issues", d, "summary.json")
    if os.path.exists(sp):
        idx.append(json.load(open(sp, encoding="utf-8")))
with open(os.path.join(OUT, "issues", "index.js"), "w", encoding="utf-8") as f:
    f.write("/* 往期目录：由 build_v2.py 扫描 issues/日期/summary.json 生成 */\n")
    f.write("window.FD_INDEX = %s;\n" % json.dumps({"latest": idx[-1]["date"], "issues": idx}, ensure_ascii=False))

# 模板
for f in ("index.html", "app.js", "style.css", "video.css", "video2.js", "video2.css"):
    shutil.copy2(os.path.join(SITE, "v2", f), os.path.join(OUT, f))
shutil.copy2(os.path.join(SITE, "video.js"), os.path.join(OUT, "video.js"))
for f in ("echarts.min.js", "gsap.min.js"):
    shutil.copy2(os.path.join(SITE, "vendor", f), os.path.join(OUT, "vendor", f))

# ---------------------------------------------------------------- 11. 报告
def kb(p):
    return round(os.path.getsize(p) / 1024)


print("期：", DATE, "| 输出：", os.path.relpath(OUT, ROOT))
print("来源：", len(SOURCES), "| 条目：", {k: v for k, v in ORDER.items()})
print("配图：", {k: v["src"] for k, v in IMG.items()})
print("听这一段：", {k: v.get("listen") for k, v in STORIES.items()})
print("看这一段：", {k: "第 %d 屏 %s" % (v["watch"]["scene"] + 1, fmt_num(v["watch"]["t"])) for k, v in STORIES.items() if v.get("watch")})
if VIDEO2:
    a = AL["accuracy"]
    print("视频 v2：", len(VIDEO2["beats"]), "屏 | 模板", " → ".join(b["tpl"] for b in VIDEO2["beats"]),
          "| 用了", len(PLAN["templates_used"]), "种", "| 自动拆分" if PLAN["auto"] else "", "" if PLAN["checked"] else "| 数字未逐条核对")
    if len(PLAN["templates_used"]) < 6:
        print("注意：视频只用了", len(PLAN["templates_used"]), "种模板（目标每期至少 6 种），可在节拍表里换 shape 或写 tpl")
    print("逐字对齐：比上", a["matched_ratio"], "| 整体平移", a["offset_applied"], "秒 | 停顿后开口误差 中位",
          a.get("median_abs_err"), "秒、九成以内", a.get("p90_abs_err"), "秒、最大", a.get("max_abs_err"), "秒（已吸附", a["snapped_to_onset"], "处）")
print("播客：", PODCAST_DIR, p_dur, "秒", kb(p_dst), "KB | 章节", len(chapters))
print("体积 KB：issue.js", kb(os.path.join(ISS, "issue.js")), "| 图片",
      {f: kb(os.path.join(ISS, "img", f)) for f in sorted(os.listdir(os.path.join(ISS, "img")))})
other = sorted(d for d in os.listdir(os.path.join(SRC, "05_配音"))
               if d.startswith("v2_") and os.path.exists(os.path.join(SRC, "05_配音", d, "episode.mp3")))
if other and not PODCAST_DIR.split("/")[-1].startswith("v2_"):
    print("提示：发现 v2 播客文件夹", other, "，要换上就加 --podcast 05_配音/" + other[-1], "或改配置里的 PODCAST_DIR")
