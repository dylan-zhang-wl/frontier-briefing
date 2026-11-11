#!/usr/bin/env python3
"""v3 网页组装（“发布会玻璃”）：site/v3 模板 + 一期数据 → <期目录>/10_网页v3/（双击 index.html 即可看）

用法（在项目根目录 frontier-daily/ 下）：
    ~/.venvs/frontier-daily/bin/python site/tools/build_v3.py 测试版/2026-10-31 --podcast 05_配音/v2_Claude稿_Gemini配音_带音效
    … --out 某个站点目录        # 多期共用一个站点目录，往期会出现在日期选择里

设置分两层：
    site/tools/v3_site.py            全站设置：中英文刊名、正文字体（楷/宋/黑 一个开关）、可选的主题色
    site/tools/v3_issues/<日期>.py    每期设置：主题色、配图、今日数字（箭头规则）、预告看板（最多 5 条）、今日一词图注；
                                     11-01 起由 site/tools/make_issue_v3.py 从网页稿的 page 自动生成（10-31 仍是手写的冻结参考）；
                                     没写的项目（用哪份稿、图表、对照、视频节拍）沿用 INHERIT 指向的 v2 同一期配置
核对规则与 v2 相同：配置里每个数字、每条预告都写 ref=(事件号, 条目, 核对片段)，对不上事件卡原文就报错停下。
字体：从 ~/.cache/frontier-daily/fonts/ 读原字体（只下载一次），按这一期实际用到的字截成 WOFF2 小字体包，
      放进 issues/<日期>/fonts/；网页运行时不连谷歌字体或任何外网，国内能打开。
只读输入，只写输出目录。依赖：Pillow、fontTools＋brotli、ffmpeg/ffprobe；视频沿用 v2 的逐字对齐（有缓存就不再跑 Whisper）。
v3.1 起还要 budoux、jieba（中文按词组换行，见 zh_breaks.py；uv pip install --python ~/.venvs/frontier-daily/bin/python budoux jieba）。
不调用任何模型接口。
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
TPL = os.path.join(SITE, "v3")

ap = argparse.ArgumentParser(description="组装 v3 网页")
ap.add_argument("issue_dir", help="期目录，如 测试版/2026-10-31")
ap.add_argument("--out", help="输出目录（默认 <期目录>/10_网页v3）")
ap.add_argument("--podcast", help="播客文件夹（相对期目录），覆盖配置里的 PODCAST_DIR")
ap.add_argument("--config", help="换一份每期配置（默认 site/tools/v3_issues/<日期>.py；边界测试 test_v3_edge.py 用）")
args = ap.parse_args()

SRC = os.path.normpath(os.path.join(ROOT, args.issue_dir))
DATE = os.path.basename(SRC)
if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", DATE):
    sys.exit("期目录名应是日期，如 2026-10-31")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SITECFG = load_module(os.path.join(HERE, "v3_site.py"), "v3_site")
cfg_path = os.path.abspath(args.config) if args.config else os.path.join(HERE, "v3_issues", DATE + ".py")
if not os.path.exists(cfg_path):
    sys.exit("找不到这一期的 v3 配置：" + os.path.relpath(cfg_path, ROOT))
CFG = load_module(cfg_path, "cfg_v3")
if getattr(CFG, "INHERIT", None):   # 没写的项目沿用 v2 同一期配置
    BASE_CFG = load_module(os.path.join(HERE, CFG.INHERIT), "cfg_base")
    for k in dir(BASE_CFG):
        if k.isupper() and not hasattr(CFG, k):
            setattr(CFG, k, getattr(BASE_CFG, k))

OUT = os.path.normpath(os.path.join(ROOT, args.out)) if args.out else os.path.join(SRC, "10_网页v3")
ISS = os.path.join(OUT, "issues", DATE)
PODCAST_DIR = args.podcast or getattr(CFG, "PODCAST_DIR", None)


# 配乐署名（11-03 改）：按这一期播客实际用的声音包写，不再用 v3_site.py 里写死的那一行（11-02 起默认包换成了
# Kevin MacLeod《Dreamer》，写死的还是 Castles in the Sky）。先读播客文件夹 qc.json（混音时记下的底乐文件和署名），
# 再读 usage.json 的“音乐素材”，都没有就读现在的默认声音包（pipeline/assets/music/v3/包.json，照“基于”一层层合并）。
# 底乐文件 → 给人看的中英文一行，用 video3_music.CREDITS（视频的署名也用这张表）；表里没有的底乐，就用声音包自己的“署名”原文。
def _pkg_merged(path, depth=0):
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    base = _pkg_merged(os.path.join(os.path.dirname(path), spec["基于"]), depth + 1) if spec.get("基于") and depth < 8 else {}
    out = dict(base)
    for k, v in spec.items():
        out[k] = dict(out.get(k) or {}, **v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def music_credit():
    bed = att = src = None
    pdir_ = os.path.join(SRC, PODCAST_DIR) if PODCAST_DIR else None
    if pdir_ and os.path.isfile(os.path.join(pdir_, "qc.json")):
        with open(os.path.join(pdir_, "qc.json"), encoding="utf-8") as f:
            qc = json.load(f)
        f_ = ((((qc.get("混音") or {}).get("素材") or {}).get("底乐")) or {}).get("文件")
        bed, att = (os.path.basename(f_) if f_ else None), (qc.get("声音包") or {}).get("署名")
        src = "播客 qc.json（%s）" % ((qc.get("声音包") or {}).get("名称") or "?")
    if not (bed or att) and pdir_ and os.path.isfile(os.path.join(pdir_, "usage.json")):
        with open(os.path.join(pdir_, "usage.json"), encoding="utf-8") as f:
            mu = next((v for k, v in json.load(f).items() if k.startswith("音乐素材")), None) or {}
        bed, att, src = mu.get("底乐文件"), mu.get("署名"), "播客 usage.json（%s）" % (mu.get("声音包") or "?")
    if not (bed or att):
        pk = os.path.join(ROOT, "pipeline/assets/music/v3/包.json")
        if os.path.isfile(pk):
            spec = _pkg_merged(pk)
            bed, att, src = (spec.get("素材") or {}).get("底乐"), spec.get("署名"), "默认声音包 包.json（%s）" % (spec.get("名称") or "?")
    table = {}
    try:
        sys.path.insert(0, HERE)
        import video3_music
        table = dict(video3_music.CREDITS)
        table.setdefault("bed_bright.flac", video3_music.CREDIT)      # B2 的亮底乐也是 Castles in the Sky
    except Exception as e:  # noqa: BLE001
        print("注意：读不到 video3_music 的署名表（%s），配乐署名用声音包原文" % e)
    row = table.get(bed or "")
    if row:
        line = (row["zh"].rstrip("。"), row["en"].rstrip("."))
    elif att:
        line = ("配乐：%s" % att, "Music: %s" % att)
    else:
        print("注意：找不到这一期用的声音包，配乐署名沿用 v3_site.py 的 MUSIC_CREDIT")
        return getattr(SITECFG, "MUSIC_CREDIT", None)
    print("配乐署名：%s（按 %s，底乐 %s）" % (line[0], src, bed or "?"))
    return line


_mc = music_credit()
if _mc:
    SITECFG.MUSIC_CREDIT = tuple(_mc)       # 后面字体子集、“看与听”下方、“参考来源”末尾都读这一个
for d in (OUT, os.path.join(OUT, "vendor"), os.path.join(ISS, "img"), os.path.join(ISS, "audio"), os.path.join(ISS, "fonts")):
    os.makedirs(d, exist_ok=True)

LAYOUT_NAMES = ("split-l", "split-r", "glass", "wide", "inset")   # app.js / style.css 认识的版式（v3.2）
THEME = getattr(CFG, "THEME", None) or {"accent": "blue"}
if THEME.get("accent") not in SITECFG.ACCENTS:
    sys.exit("主题色 %r 不在 v3_site.py 的 ACCENTS 里（可选：%s）" % (THEME.get("accent"), "、".join(SITECFG.ACCENTS)))
if SITECFG.BODY_FONT not in ("kai", "song", "hei"):
    sys.exit("v3_site.py 的 BODY_FONT 只能是 kai、song 或 hei")


def jload(rel):
    with open(os.path.join(SRC, rel), encoding="utf-8") as f:
        return json.load(f)


def ffprobe(path, entry):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=" + entry, "-of", "csv=p=0", path],
                       check=True, capture_output=True, text=True)
    return r.stdout.strip()


WEB = jload(CFG.WEB)
CARDS = {c["event_id"]: c for c in jload(CFG.CARDS)}
CANDS = jload(CFG.CANDIDATES) if getattr(CFG, "CANDIDATES", None) and os.path.isfile(os.path.join(SRC, CFG.CANDIDATES)) else {}
CJK = re.compile(r"[㐀-鿿]")

# ---------------------------------------------------------------- 1. 来源：按网址去重，配上原标题（与 v2 相同）
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

# v3.2：标题为空时，回到抓取原始数据（01_获取/raw.jsonl）里按网址找标题
_raw = os.path.join(SRC, "01_获取", "raw.jsonl")
if os.path.isfile(_raw):
    for _line in open(_raw, encoding="utf-8"):
        try:
            _d = json.loads(_line)
        except ValueError:
            continue
        _k = norm_url(_d.get("url"))
        _old = URL_TITLE.get(_k) or ""
        # 选题数据里的标题有时只截了合集页的第一段（“苹果官宣……”），原始数据里是全文：用更完整的那个
        if _d.get("title") and (not _old or (len(_d["title"]) > len(_old) and _d["title"].startswith(_old))):
            URL_TITLE[_k] = _d["title"]

# v3.2 英文名表（pipeline/prompts/英文名表.yaml）：参考来源、报道光谱、英文正文里的媒体名都照它写
import yaml  # noqa: E402

NAME_REG = []   # (中文写法, 英文写法, 类别)
_regp = os.path.join(ROOT, "pipeline", "prompts", "英文名表.yaml")
if os.path.isfile(_regp):
    for _grp in (yaml.safe_load(open(_regp, encoding="utf-8")) or {}).values():
        for _e in _grp or []:
            for _z in _e.get("zh") or []:
                NAME_REG.append((str(_z), str(_e["en"]), _e.get("kind", "")))
    NAME_REG.sort(key=lambda x: -len(x[0]))
FEED_NAME = {z: e for z, e, k in NAME_REG if k == "feed"}


def name_en(name):
    """来源名 → 英文：“IT之家（转引 Tom's Hardware）”→“ITHome (via Tom’s Hardware)”。查不到的中文部分去掉。"""
    name = FEED_NAME.get(name, name)
    m = re.match(r"^(.*?)\s*[（(](.*)[）)]\s*$", name)
    base, paren = (m.group(1), m.group(2)) if m else (name, "")
    base = re.sub(r"\s*·\s*(科技|AI|财经|商业)$", "", base).strip()

    def tr(t):
        for z, e, _ in NAME_REG:
            if z in t:
                t = t.replace(z, e)
        for a, b in (("该条文内注明出自", "citing "), ("原始报道为", "originally "), ("转引", "via "), ("转述", "relaying "),
                     ("经", "via "), ("报道", ""), ("数据", " data"), ("与", " and "), ("，", ", "), ("、", ", ")):
            t = t.replace(a, b)
        return re.sub(r"\s+", " ", t).strip(" ,")
    en = tr(base)
    if CJK.search(en):     # 名表里没有：去掉其中的中文，留下西文部分（“GitHub 仓库 deepseek-ai/…”→“GitHub deepseek-ai/…”）
        en = re.sub(r"\s+", " ", re.sub(r"[\u3400-\u9fff\uff00-\uffef]+", " ", en)).strip() or en
    en = re.sub(r"\b(.+?)(?:\s+\1\b)+", r"\1", en)   # “彭博 Bloomberg”“金融时报 FT”换完以后不重复
    if paren:
        pe = tr(paren)
        if not CJK.search(pe):
            en += " (" + pe + ")"
    return en


SOURCES = {}
URL2ID = {}
SRC_EVENTS = {}   # 来源编号 → 引用它的事件（给“合集页”标题挑出对应的那一条用）


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


# ---------------------------------------------------------------- 3. 正文引用：每句话对回事件卡里最像的那条事实（与 v2 相同）
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
    _srcs = {s["id"]: s for s in card["sources"]}
    for f in card["facts"]:
        sid = gid(_srcs[f["source_id"]])
        lst.append({"sid": sid, "B": bigr(f.get("text_zh")), "W": words(f.get("text_en")),
                    "T": " ".join(str(f.get(k) or "") for k in ("text_zh", "text_en", "quote"))})
    for n in card["numbers"]:
        sid = gid(_srcs[n["source_id"]])
        lst.append({"sid": sid, "B": bigr((n.get("meaning_zh") or "") + str(n.get("value")) + (n.get("compare_zh") or "")),
                    "W": words((n.get("meaning_en") or "") + " " + str(n.get("value"))),
                    "T": " ".join(str(n.get(k) or "") for k in ("value", "unit", "meaning_zh", "meaning_en", "compare_zh", "quote"))})
    for w in card.get("who_said") or []:   # v3.2：当事人的话也能对上出处（“据三星方面转述，他说……”）
        if w.get("source_id") in _srcs:
            sid = gid(_srcs[w["source_id"]])
            lst.append({"sid": sid, "B": bigr(w.get("said_zh")), "W": words(w.get("said_en")),
                        "T": " ".join(str(w.get(k) or "") for k in ("said_zh", "said_en", "quote"))})
    for x in lst:
        SRC_EVENTS.setdefault(x["sid"], set()).add(ev)
    FACTS[ev] = lst

# 每个来源的“点名写法”：句子里写了“据 TechCrunch”“彭博社”时，优先挂这家的出处
OUTLET_ALIASES = {}


def outlet_aliases(sid):
    if sid not in OUTLET_ALIASES:
        nm, al = SOURCES[sid]["name"], set()
        for z, e, k in NAME_REG:
            if k in ("media", "org") and (z in nm or e in nm):
                al |= {z2 for z2, e2, _ in NAME_REG if e2 == e} | {e}
        OUTLET_ALIASES[sid] = {a for a in al if len(a) >= 2}
    return OUTLET_ALIASES[sid]

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
    # v3.2 两条规矩：句子点了哪家媒体的名，就优先挂哪家；句子里的数字（如 2027、35 台）只出现在某几条事实里，就优先挂那几条
    sn = {x for x in re.findall(r"\d+(?:\.\d+)?", re.sub(r"(?<=\d),(?=\d{3})", "", sent)) if len(x) >= 2}
    cands = [f for ev in evs for f in FACTS.get(ev, [])]
    with_num = {id(f) for f in cands if sn and sn & set(re.findall(r"\d+(?:\.\d+)?", re.sub(r"(?<=\d),(?=\d{3})", "", f.get("T", ""))))}

    def score(f):
        sc = len(S & f[key]) / denom
        if any(a in sent for a in outlet_aliases(f["sid"])):
            sc *= 1.6
        if with_num and id(f) not in with_num:
            sc *= 0.5
        return sc
    scored = sorted(((score(f), f["sid"]) for f in cands), key=lambda x: -x[0])
    named = [(sc, sid) for sc, sid in scored if sc >= TH[lang] and any(a in sent for a in outlet_aliases(sid))]
    if named:   # 句子点了名的媒体能对上，就只挂点了名的那家（“彭博社把它放在……”不再顺带挂别家）
        scored = named
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


_HIDE = {".": "\ue010", "!": "\ue011", "?": "\ue012", "。": "\ue013", "！": "\ue014", "？": "\ue015"}
_SHOW = {v: k for k, v in _HIDE.items()}


def split_sents(p, lang):
    # v3.2：引号里的句号（如专栏标题“… cheating. But …”）不算句末，上标也不会插进引号中间
    p = re.sub(r"“[^“”]{1,240}”", lambda m: re.sub(r"[.!?。！？](?!”)", lambda x: _HIDE[x.group(0)], m.group(0)), p)
    if lang == "zh":
        out = [s for s in re.split(r"(?<=[。！？])(?![”」』）)])", p) if s.strip()]
    else:
        out = [s.strip() for s in re.split(r"(?:(?<=[.!?])|(?<=[.!?][”\"’)]))\s+(?=[A-Z“\"‘(])", p) if s.strip()]
    return [re.sub("[\ue010-\ue015]", lambda x: _SHOW[x.group(0)], s) for s in out]


def clause_cites(s, evs, lang):
    """一句话里用分号连着两件出自不同来源的事（“……调整了预期；双方都拒绝向 TechCrunch 置评。”）：各挂各的出处。
    返回 [(分句, 出处)]；分句都能对上、而且出处不全相同时才拆，否则整句一个出处（和以前一样）。"""
    whole = cites_for(s, evs, lang)
    parts = [x for x in (re.split(r"(?<=；)", s) if lang == "zh" else re.split(r"(?<=;)\s+", s)) if x.strip()]
    if len(parts) > 1:
        cl = [cites_for(x, evs, lang) for x in parts]
        if all(cl) and len({tuple(c) for c in cl}) > 1:
            return list(zip(parts, cl))
    return [(s, whole)]


def tok(cs):
    return "".join("[^%s]" % c for c in cs)


def cite_paras(text, evs, lang):
    """text → (段落列表，带 [^sNN]；每句的 (句子, 出处) 列表)。同一出处连续几句，只在最后一句后标一次。"""
    paras, sents_all = [], []
    sp = " " if lang == "en" else ""
    for p in [x.strip() for x in re.split(r"\n+", text or "") if x.strip()]:
        sents = split_sents(p, lang)
        units = [(i, c, cs) for i, s in enumerate(sents) for c, cs in clause_cites(s, evs, lang)]
        buf, per = "", [""] * len(sents)
        for k, (i, c, cs) in enumerate(units):
            nxt = units[k + 1] if k + 1 < len(units) else None
            buf += c + (tok(cs) if cs and (nxt is None or nxt[2] != cs) else "") + (sp if nxt else "")
            # 导语（每段第一句）单独拿出来时，句末总要带上自己的出处
            same = nxt is not None and nxt[0] == i
            per[i] += c + (tok(cs) if cs and (not same or nxt[2] != cs) else "") + (sp if same else "")
        paras.append(buf)
        sents_all.append([(x, []) for x in per])
    return paras, sents_all


def lead3(sents_all):
    """“三句话”：每段第一句，不够三句就按顺序补。"""
    picked = [ps[0] for ps in sents_all if ps][:3]
    rest = [x for ps in sents_all for x in ps[1:]]
    while len(picked) < 3 and rest:
        picked.append(rest.pop(0))
    return [s + tok(c) for s, c in picked]


# ---------------------------------------------------------------- 4. 小工具
def fmt_num(x):
    return ("%.2f" % x).rstrip("0").rstrip(".")


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SPECIAL_EN = {"150亿至160亿": "15–16B", "约 11 小时 / 近 12 小时": "~11 h / ~12 h", "三个": "3", "两年半": "2.5 yrs"}


def value_en(v):
    s = str(v).strip()
    if s in SPECIAL_EN:
        return SPECIAL_EN[s]
    # v3.2：英文数字卡统一用 bn / tn；人民币写 RMB（“¥”只留给日元，免得英文读者分不清）
    m = re.fullmatch(r"(约\s*)?(-?[\d,]+(?:\.\d+)?)\s*亿美元(以上)?", s)
    if m:
        return ("~" if m.group(1) else "") + "$" + fmt_num(float(m.group(2).replace(",", "")) / 10) + "bn" + ("+" if m.group(3) else "")
    m = re.fullmatch(r"(约\s*)?(-?[\d,]+(?:\.\d+)?)\s*亿元", s)
    if m:
        return ("~" if m.group(1) else "") + "RMB " + fmt_num(float(m.group(2).replace(",", "")) / 10) + "bn"
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


# ---------------------------------------------------------------- 5. 配图：PNG → 两种宽度的 WebP（手机用小图，电脑用大图）
IMG_DIR = getattr(CFG, "IMAGE_DIR", "06_配图")
IMG = {}
CREDIT = getattr(CFG, "CREDIT", None) or {"credit_zh": "AI 生成配图", "credit_en": "AI-generated image"}
for key, spec_ in (getattr(CFG, "IMAGES", None) or {}).items():
    src = os.path.join(SRC, IMG_DIR, spec_.get("file") or "")
    if not spec_.get("file") or not os.path.isfile(src):
        print("缺图（页面会用主题色的抽象封面代替）：", os.path.join(IMG_DIR, spec_.get("file") or "?"))
        continue
    im0 = Image.open(src).convert("RGB")
    square = im0.width <= im0.height * 1.2
    widths = (600, 900) if square else (800, 1400)
    base = "card" if key == "card" else key.lower()
    made = []
    for w in widths:
        im = im0.resize((w, round(im0.height * w / im0.width)), Image.LANCZOS) if im0.width > w else im0
        name = "%s-%d.webp" % (base, im.width)
        im.save(os.path.join(ISS, "img", name), "WEBP", quality=80, method=6)
        made.append((name, im.width, im.height))
    (sm, smw, _), (lg, lgw, lgh) = made[0], made[-1]
    IMG[key] = {"src": "img/" + lg, "w": lgw, "h": lgh, "src_sm": "img/" + sm, "w_sm": smw,
                "alt_zh": spec_.get("alt_zh", ""), "alt_en": spec_.get("alt_en", ""), **CREDIT,
                **{k: spec_[k] for k in ("cap_zh", "cap_en") if spec_.get(k)}}   # 图注（v3.2）：只放“这张图对这条新闻意味着什么”，不是替代文字

# ---------------------------------------------------------------- 6. 播客：一版音频、章节、波形、每条“听这一段”的时刻（与 v2 相同）
# v3.2：没有播客（文件夹或 episode.mp3 缺了）也能组装，页面上就不出现“听”的按钮和播客面板
pdir = os.path.join(SRC, PODCAST_DIR) if PODCAST_DIR else None
p_src = os.path.join(pdir, "episode.mp3") if pdir else None
p_dst = os.path.join(ISS, "audio", "podcast.mp3")
HAS_POD = bool(p_src and os.path.isfile(p_src))
if os.path.exists(p_dst) and not HAS_POD:
    os.remove(p_dst)
chapters, peaks, p_dur = [], [], 0
# 周末版（11-01 定）的章名是"深度·层名""深谈·层名"：按"·"拆开，两半都认得就拼成英文（写稿规则见
# pipeline/prompts/写稿_周六深度.md、写稿_周日深谈.md 的章名表）；认不得就照旧用中文
CH_EN_PART = {"深度": "Deep dive", "深谈": "Deep talk", "发生了什么": "What happened", "为什么重要": "Why it matters",
              "接下来看什么": "What to watch", "来龙去脉": "The week", "怎么做到的": "How it works",
              "数字怎么读": "Reading the numbers", "各方怎么看": "Who says what", "意味着什么": "What it means"}


def ch_en(zh):
    parts = zh.split("·")
    if len(parts) > 1 and all(p in CH_EN_PART for p in parts):
        return " · ".join(CH_EN_PART[p] for p in parts)
    return next((v for k, v in CH_EN.items() if zh.startswith(k)), zh)


CH_EN = {"开场": "Opening", "热点一": "Top story 1", "热点二": "Top story 2", "热点三": "Top story 3", "要闻": "Key stories",
         "快讯": "In brief", "今日一词": "Word of the day", "预告观察": "On the radar", "预告": "On the radar", "结尾": "Closing"}
if HAS_POD:
    rate = int(ffprobe(p_src, "bit_rate") or 0)
    if rate > 80000:   # 单声道 64 kbps 足够听清人声
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", p_src, "-ac", "1", "-b:a", "64k", "-map_metadata", "-1", p_dst], check=True)
    else:
        shutil.copy2(p_src, p_dst)
    p_dur = round(float(ffprobe(p_dst, "duration")), 2)
    chp_path = os.path.join(pdir, "chapters.json")
    for c in (json.load(open(chp_path, encoding="utf-8"))["chapters"] if os.path.exists(chp_path) else []):
        zh = c["title"].strip()
        chapters.append({"start": round(float(c["startTime"]), 2), "title_zh": zh,
                         "title_en": ch_en(zh)})

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p_dst, "-ac", "1", "-ar", "2000", "-f", "s16le", "-"],
                         check=True, capture_output=True).stdout
    pcm = array.array("h")
    pcm.frombytes(raw[: len(raw) // 2 * 2])
    NB = 160
    step = max(1, len(pcm) // NB)
    for i in range(NB):
        seg = pcm[i * step:(i + 1) * step]
        peaks.append(math.sqrt(sum(x * x for x in seg) / len(seg)) if len(seg) else 0)
    top = max(peaks) if peaks else 1
    top = top or 1
    peaks = [round(math.sqrt(p / top), 2) for p in peaks]
else:
    print("注意：没有找到播客（%s），页面上不放播客和“听这一段”" % (os.path.relpath(p_src, ROOT) if p_src else "配置里没写 PODCAST_DIR"))

PARAS = []


def qc_blocks(folder):
    p = os.path.join(folder, "qc.json")
    if not os.path.exists(p):
        return []
    q = json.load(open(p, encoding="utf-8"))
    if q.get("各块"):            # _人声开始秒、_人声目录：这一块在人声版 episode.mp3 里的位置（“听这一段”找停顿用，11-06 加）
        return [dict(b, _人声开始秒=b["开始秒"], _人声目录=folder) for b in q["各块"]]
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


# 周日是两人对谈（v3.2）：稿子每行以“甲：”“乙：”开头。说话人记号不念出来，算时间和比对文字时都先去掉。
SPEAKER = re.compile(r"^\s*(?:\*\*)?[甲乙丙丁](?:\*\*)?\s*[：:]\s*")

# 每段从第几秒开始念（11-06 改）：原来按“这段在这一块里排第几个字”的比例估，语速、停顿不匀就偏（11-06 E006 早 4.9 秒、
# E206 早 3.3 秒，落在上一条的句子中间）。现在先用配音时已有的对齐数据：
#   ① 这一块选用那一条的 Whisper 转写（tts.py 对稿时存在 ~/.cache/frontier-daily/tts/whisper/<块的指纹>/，带每一小段的起止秒）
#      和原稿逐字比对，得到每段第一个字在原始音频里的时刻，再按后期的变速、去掉的开头静音换到成品的时间上；
#      Whisper 的段首常落在前一个停顿的开头（11-06 中位早 0.4 秒），所以
#   ② 再到人声版 episode.mp3（配音目录里，没有底乐）里，在 ① 前后 1 秒内找停顿（低于 −40 dBFS 连续 0.15 秒以上），
#      段首取停顿结束、开口的那一刻。
# 跳转点：吸到停顿上的跳开口前 0.3 秒（停顿不到 0.6 秒就跳停顿正中）；没吸上的直接跳 ① 的时刻；
# 每块第一段跳到块开头前 0.3 秒（块间有 0.4 秒静音）。
# 找不到对齐数据（转写缓存过了 14 天被清掉、对谈稿、读不到 tts_qc），或者某段对不上、比估算差出 15 秒以上、前后顺序乱了，
# 那一段退回原来的比例估算、往前留 0.5 秒，和 11-05 以前逐字相同。
# 测试时设环境变量 FD_TTS_CACHE 指向别的目录（比如空目录），就能看退回估算时的结果（site/tools/test_listen_jump.py）。
TTS_CACHE = os.environ.get("FD_TTS_CACHE") or os.path.expanduser("~/.cache/frontier-daily/tts")
LISTEN_STAT = {}            # 这一期各段用了哪种算法：{"对齐＋停顿": n, "对齐": n, "块首": n, "估算": n}
VOICE_DB = {}               # 人声目录 → 人声版 episode.mp3 每 10 毫秒的响度（dBFS），读不到是 None
try:
    sys.path.insert(0, os.path.join(ROOT, "pipeline"))
    import tts_qc as _TQ    # 只借它的 tokens()：和配音对稿用同一种写法比（数字统一成阿拉伯数字、繁转简）
except Exception as _e:  # noqa: BLE001
    _TQ = None
    print("注意：读不到 pipeline/tts_qc.py（%s），“听这一段”按字数比例估时间" % _e)
_MIMO_TAG = re.compile(r"[（(\[]\s*[㐀-鿿][㐀-鿿，、 ]{0,11}\s*[）)\]]")     # 和 tts.spoken 一样：行内标记不念
_GEM_TAG = re.compile(r"<\s*[A-Za-z][A-Za-z \-]{0,30}\s*>")
CHAR_S = 1 / 4.4            # 段首几个字没对上时，按每字约 0.23 秒往回推（Shirley 实测约 4.4 字／秒）


def _head_trim(raw, tempo):
    """原始音频开头被 tts.trim_silence 去掉了多少秒（换到变速以后的时间）：第一个响过 −50 dBFS 的 10 毫秒窗之前，留 80 毫秒。"""
    import wave
    try:
        import numpy as np
        with wave.open(raw) as w:
            sr, nch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
            if sw != 2:
                return 0.0
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)[::nch].astype(np.float32) / 32768
    except Exception:  # noqa: BLE001
        return 0.0
    win = max(1, int(sr * 0.01))
    m = len(x) // win
    if not m:
        return 0.0
    db = 20 * np.log10(np.sqrt((x[:m * win].reshape(m, win) ** 2).mean(axis=1)) + 1e-9)
    loud = np.where(db > -50.0)[0]
    return max(0.0, float(loud[0]) * win / sr / tempo - 0.08) if len(loud) else 0.0


def voice_db(folder):
    """人声版 episode.mp3（没有底乐，块与块之间是静音）每 10 毫秒一窗的响度；读不到就 None。"""
    if folder not in VOICE_DB:
        VOICE_DB[folder] = None
        mp3 = os.path.join(folder, "episode.mp3") if folder else ""
        if os.path.isfile(mp3):
            try:
                import numpy as np
                r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", mp3, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                                   check=True, capture_output=True)
                x = np.frombuffer(r.stdout[: len(r.stdout) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768
                m = len(x) // 80
                VOICE_DB[folder] = 20 * np.log10(np.sqrt((x[:m * 80].reshape(m, 80) ** 2).mean(axis=1)) + 1e-9)
            except Exception as e:  # noqa: BLE001
                print("注意：读不到人声版 %s（%s），“听这一段”不按停顿校准" % (os.path.relpath(mp3, ROOT), e))
    return VOICE_DB[folder]


def pause_near(db, t, lo, hi, quiet=-40.0, min_len=0.15, reach=1.0, long_=0.35):
    """人声版里 t 前后 reach 秒内的停顿（只在 lo–hi 秒之间找）：返回 (起, 止)，没有就 None。
    停顿＝低于 quiet dBFS 连续 min_len 秒以上（中间冒出来不到 0.1 秒的气声不算断开）；和 t 前后 reach 秒有交集就算候选
    （停顿本身可以伸出这个范围）。候选里有 long_ 秒以上的（段落之间的停顿），只在这些里挑；挑离 t 最近的（t 落在停顿里就是它）。"""
    a, b = max(0, int(lo * 100)), min(len(db), int(hi * 100))
    runs, j = [], a
    while j < b:
        if db[j] < quiet:
            k = j
            while k < b and db[k] < quiet:
                k += 1
            if (runs and j - int(round(runs[-1][1] * 100)) <= 10 and k - j >= 10
                    and runs[-1][1] - runs[-1][0] >= 0.1):         # 两段静音（各 0.1 秒以上）只隔一下气声：并成一段
                runs[-1] = (runs[-1][0], k / 100)
            else:
                runs.append((j / 100, k / 100))
            j = k
        else:
            j += 1
    runs = [r for r in runs if r[1] - r[0] >= min_len and r[0] > a / 100 and r[1] < b / 100]   # 两头都要有声：切在 lo、hi 上的不算
    cand = [r for r in runs if r[1] >= t - reach and r[0] <= t + reach]
    if any(r[1] - r[0] >= long_ for r in cand):
        cand = [r for r in cand if r[1] - r[0] >= long_]
    if not cand:
        return None
    return min(cand, key=lambda r: 0 if r[0] <= t <= r[1] else min(abs(t - r[0]), abs(t - r[1])))


def para_times(b, ps):
    """一块里每段从块内第几秒开始：[(秒, 跳转往前留几秒, 算法)]。算法见上面的说明；对齐那一步出任何错，整块退回估算，不让组装停下。"""
    try:
        return _para_times(b, ps)
    except Exception as e:  # noqa: BLE001
        print("注意：第 %s 块“听这一段”的对齐出错（%s），这一块按字数比例估" % (b.get("块"), e))
        return _para_times(b, ps, estimate_only=True)


def _para_times(b, ps, estimate_only=False):
    total = sum(len(p) for p in ps) or 1
    est, acc = [], 0
    for p in ps:
        est.append(b["秒数"] * acc / total)
        acc += len(p)
    fallback = [(e, 0.5, "估算") for e in est]
    if estimate_only:
        return fallback
    takes = b.get("各条") or []
    k = (b.get("选用第几条") or 1) - 1
    raw = takes[k].get("原始音频") if _TQ is not None and 0 <= k < len(takes) else None
    if not raw:
        return fallback
    key = os.path.splitext(os.path.basename(raw))[0]
    wj = os.path.join(TTS_CACHE, "whisper", key, key + "_whisper.json")
    try:
        segs = json.load(open(wj, encoding="utf-8")).get("segments") or []
    except (OSError, ValueError):
        return fallback
    tempo = float(b.get("备用后期变速") or 1.0) * float((b.get("语速微调") or {}).get("用了变速") or 1.0)
    head = _head_trim(raw, tempo) if os.path.exists(raw) else 0.0
    hyp, ht = [], []
    for sg in segs:
        tk = _TQ.tokens(sg.get("text") or "")
        for j, c in enumerate(tk):
            hyp.append(c)
            ht.append(sg["start"] + (sg["end"] - sg["start"]) * j / len(tk))
    ref, own = [], []
    for i, p in enumerate(ps):
        tk = _TQ.tokens(_GEM_TAG.sub("", _MIMO_TAG.sub("", p)))
        ref += tk
        own += [i] * len(tk)
    import difflib
    hit = {}
    for a, c, n in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_matching_blocks():
        for j in range(n):
            hit[a + j] = ht[c + j]
    db = voice_db(b.get("_人声目录"))
    v0 = b.get("_人声开始秒")
    out, prev = [(0.0, 0.3, "块首")], 0.0
    for i in range(1, len(ps)):
        idx = [j for j, o in enumerate(own) if o == i]
        t = next((hit[j] / tempo - head - CHAR_S * n for n, j in enumerate(idx[:6]) if j in hit), None)
        if t is None or abs(t - est[i]) > 15 or t <= prev + 0.5 or t >= b["秒数"]:
            out.append(fallback[i])
            prev = est[i]
            continue
        pz = pause_near(db, v0 + t, v0 + prev + 0.3, v0 + b["秒数"]) if db is not None and v0 is not None else None
        if pz is not None and pz[1] - v0 > prev + 0.5:
            on = pz[1] - v0
            out.append((on, min(0.3, (pz[1] - pz[0]) / 2), "对齐＋停顿"))
            prev = on
        else:
            out.append((t, 0.0, "对齐"))
            prev = t
    return out


for b in (qc_blocks(pdir) if HAS_POD else []):
    ps = [SPEAKER.sub("", p) for p in (b.get("原稿") or "").split("\n") if p.strip()]
    ps = [p for p in ps if p.strip()]
    for p, (off, lead, how) in zip(ps, para_times(b, ps)):
        PARAS.append({"ch": b.get("章", ""), "t": round(b["开始秒"] + off, 1), "text": p, "lead": lead, "how": how})
        LISTEN_STAT[how] = LISTEN_STAT.get(how, 0) + 1


def jump_of(p):
    """“听这一段”跳到这一段之前多少秒：对齐过的按 para_times 给的留量，估算的照旧往前留 0.5 秒。"""
    return max(0, round(p["t"] - p.get("lead", 0.5), 1))


def with_lead_in(p, text):
    """这一段是本章第二段、本章第一段只是一句不超过 20 个字、和这条沾边（字对字至少有一处相同）的引子
    （11-06 预告观察“在美国国会那边，有一个更激进的声音。”，接着才讲那位众议员）：从引子开始听（11-06 加）。
    本章第一段有两句以上的（要闻开头“再快速看看别的消息。先接着……”）、和这条一个字对都不沾的（“再快看几条消息。”），不算引子。"""
    same = [x for x in PARAS if x["ch"] == p["ch"]]
    if len(same) >= 2 and same[1] is p:
        q = same[0]
        n_han = len(re.findall(r"[\u4e00-\u9fff]", q["text"]))
        if (n_han <= 20 and len(re.findall(r"[。！？!?]", q["text"])) == 1 and re.search(r"[。！？!?]\s*$", q["text"])
                and bigr(q["text"]) & bigr(text)):
            return q
    return p
KIND_CH = {"headline": ("热点", "头条"), "brief": ("要闻",), "cn_intl": ("对照",), "flash": ("快讯",),
           "deep": ("深度·", "深谈·"),                     # 周末那一题（11-01 定）：跳到它的第一章，不按文字找
           "term": ("一词",), "teaser": ("预告",)}


def has_key(title, keys):
    return any(k in title for k in keys)


def para_scores(text, cand):
    B = bigr(text)
    return [len(B & bigr(p["text"])) for p in cand]


PREVIEW_CH = ("开场", "结尾")   # 开场预告、结尾回顾只提一句，不算“主讲”


def main_talk(text):
    """整集里主讲这条的那一段：先找最像它的那一轮（开场、结尾不算），再在那一轮所在章里取第一段够像的
    （分数≥4 且≥最高分的六成，即这一章开始正式展开它的地方）。找不到返回 (None, 0)。"""
    body = [p for p in PARAS if not has_key(p["ch"], PREVIEW_CH)]
    if not body:
        return None, 0
    sc = para_scores(text, body)
    top_ = max(sc)
    if top_ < 4:
        return None, top_
    ch = body[sc.index(top_)]["ch"]
    first = next(p for p, x in zip(body, sc) if p["ch"] == ch and x >= max(4, top_ * 0.6))
    return first, top_


def listen_at(kind, text, nth=None):
    """“听这一段”跳到哪一秒。有自己章节的栏目（热点、要闻、快讯、一词、预告）在本章里按文字找；
    没有自己章节的（国内外对照的条目：在对谈里可能夹在热点或快讯里讲）在整集的逐轮（逐段）文字里找最像的那一轮。
    11-05 改：网页放在某一栏、播客却在别的章里讲的（11-04 墨芯：网页在要闻，播客在热点三），本章里几乎找不到它
    （本章最高分不到 4，或不到整集最高分的六成，与 listen_check 的判据相同），就跳到整集里主讲它的那一段，
    不再退回本章开头。"""
    if not HAS_POD:
        return None
    keys = KIND_CH.get(kind, ())
    own = [c for c in chapters if has_key(c["title_zh"], keys)]
    if kind == "headline" and nth is not None and nth < len(own):
        return own[nth]["start"]
    if kind == "deep" and own:          # 周末的深度／深谈：从第一层那一章开头听（按文字找常落在开场的预告上，11-01 彩排遇到）
        return own[0]["start"]
    if own:
        cand = [p for p in PARAS if has_key(p["ch"], keys)] or PARAS
        top_ = 0
        if cand:
            sc = para_scores(text, cand)
            top_ = max(sc)
        best, g_top = main_talk(text)
        if best is not None and not has_key(best["ch"], keys) and top_ < max(4, g_top * 0.6):
            return jump_of(with_lead_in(best, text))
        if top_ >= 4:
            first = next(p for p, x in zip(cand, sc) if x >= max(4, top_ * 0.6))
            return jump_of(with_lead_in(first, text))
        return own[0]["start"]
    if PARAS:                                       # 没有自己的章节：整集里找分数最高的那一轮（同分取靠前的）
        sc = para_scores(text, PARAS)
        top_ = max(sc)
        if top_ >= 4:
            best = PARAS[sc.index(top_)]
            return jump_of(with_lead_in(best, text))
    return None


def chapter_at(t):
    cur = None
    for c in chapters:
        if c["start"] <= t + 0.6:
            cur = c
    return cur["title_zh"] if cur else None


def listen_check(sid, text, t):
    """组装时自检：跳到的时刻所在章节，和整集里最像这条的那一轮所在章节，不一致就提醒（可能跳错了）。"""
    if t is None or not PARAS:
        return
    sc = para_scores(text, PARAS)
    top_ = max(sc)
    if top_ < 4:
        return
    best, here = PARAS[sc.index(top_)], chapter_at(t)
    in_ch = max([x for x, p in zip(sc, PARAS) if p["ch"] == here] or [0])
    if here != best["ch"] and in_ch < top_ * 0.6:   # 跳到的章节里根本没怎么讲它，才提醒（今日一词这类在本章和别处都讲的，不算）
        print("注意：“听这一段” %s 跳到 %s（%s），但整集里最像它的话在“%s” %s；请核对"
              % (sid, fmt_mmss(t), chapter_at(t), best["ch"], fmt_mmss(best["t"])))


def fmt_mmss(t):
    t = int(round(t or 0))
    return "%d:%02d" % (t // 60, t % 60)


# ---------------------------------------------------------------- 7. 视频：第一版定时稿（只在没有 v2 对齐时用）
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


# v3.2：视频稿或旁白音频缺了也能组装（下面 7c 的 v3 视频另算）；三样都没有时页面上不放视频
_vs, _va = getattr(CFG, "VIDEO_SCRIPT", None), getattr(CFG, "VIDEO_AUDIO", None)
HAS_V12 = bool(_vs and _va and os.path.isfile(os.path.join(SRC, _vs)) and os.path.isfile(os.path.join(SRC, _va)))
VIDEO, v_real = None, 0.0
if HAS_V12:
    shutil.copy2(os.path.join(SRC, CFG.VIDEO_AUDIO), os.path.join(ISS, "audio", "video.mp3"))
    VIDEO = build_video(jload(CFG.VIDEO_SCRIPT), "audio/video.mp3", IMG.get("card", {}).get("src"))
    v_real = float(ffprobe(os.path.join(ISS, "audio", "video.mp3"), "duration"))
    if abs(v_real - VIDEO["duration"]) > 0.5:
        print("注意：视频时间轴", VIDEO["duration"], "与旁白音频", round(v_real, 2), "不一致")

# ---------------------------------------------------------------- 7b. 视频 v2：逐字对齐 → 场景计划 → video2.js（与 v2 相同）
sys.path.insert(0, HERE)
import video_align  # noqa: E402
import video_plan  # noqa: E402

VDIR = os.path.join(ISS, "video")
os.makedirs(VDIR, exist_ok=True)
WORDS = None
if HAS_V12:
    V_SCRIPT = jload(CFG.VIDEO_SCRIPT)
    V_AUDIO = os.path.join(SRC, CFG.VIDEO_AUDIO)
    V_NARR = [sc.get("narration_zh") or "" for sc in V_SCRIPT["scenes"]]
    latin = list(dict.fromkeys(re.findall(r"[A-Za-z][A-Za-z0-9&.\-]+", "".join(V_NARR))))
    WCACHE = os.path.join(VDIR, "whisper_words.json")
    if not os.path.exists(WCACHE):   # 同一段旁白在 v2 网页里对齐过，就借它的缓存（音频指纹一致才会被采用），不必再跑 Whisper
        for other in ("08_网页v2", "07_网页", "10_网页v3"):
            c = os.path.join(SRC, other, "issues", DATE, "video", "whisper_words.json")
            if os.path.exists(c):
                shutil.copy2(c, WCACHE)
                break
    WORDS = video_align.load_words(V_AUDIO, WCACHE,
                                   prompt="以下是简体中文的科技新闻解说" + ("：" + "、".join(latin) if latin else "") + "。")


def vref(r):
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
    n = SOURCES[sid]["name"]
    m = re.match(r"^(.+?)（转述(.+?)相关报道）$", n)
    zh = m.group(2) + "（经 " + m.group(1) + "）" if m else re.sub(r"（.*?）|\s*·\s*科技$", "", n).strip()
    en = zh
    for a, b in EN_MEDIA:
        en = en.replace(a, b)
    return zh, en


# ---------------------------------------------------------------- 7c. 视频 v3（一镜到底的今日地图，site/tools/video3_build.py 产出）
# 期目录里有 11_视频v3/video3_media.json 就用 v3 视频（覆盖 v2）；没有就照旧用 v2。
V3_MEDIA = os.path.join(SRC, "11_视频v3", "video3_media.json")
VIDEO3 = None
if os.path.exists(V3_MEDIA):
    with open(V3_MEDIA, encoding="utf-8") as f:
        VIDEO3 = json.load(f)
    v3dir = os.path.dirname(V3_MEDIA)
    v3files = [VIDEO3.get("audio")] + [im[k] for im in VIDEO3.get("images", {}).values() for k in ("src", "depth") if im.get(k)]
    missing = [rel for rel in v3files if not rel or not os.path.isfile(os.path.join(v3dir, rel))]
    if missing:                               # 视频 v3 的素材不全（比如正在重配旁白）：这一期先不用 v3 视频
        print("注意：11_视频v3 缺素材 %s，这次不放 v3 视频" % "、".join(str(m) for m in missing))
        VIDEO3 = None
if VIDEO3:
    for rel in v3files:                       # audio/video3.mp3、img/e007.webp…：路径都相对期目录，和网页里其他素材一样
        os.makedirs(os.path.dirname(os.path.join(ISS, rel)), exist_ok=True)
        shutil.copy2(os.path.join(v3dir, rel), os.path.join(ISS, rel))
    # 双击打开（file://）时，浏览器把本地图片当成跨源，三维画面用不了它们；另存一份 data: 地址，只在 file:// 下按需加载
    import base64  # noqa: E402
    v3assets = {}
    for im in VIDEO3.get("images", {}).values():
        for k in ("src", "depth"):
            if im.get(k):
                with open(os.path.join(v3dir, im[k]), "rb") as f:
                    v3assets[im[k]] = "data:image/webp;base64," + base64.b64encode(f.read()).decode("ascii")
    with open(os.path.join(ISS, "video3_assets.js"), "w", encoding="utf-8") as f:
        f.write("/* 只在双击打开（file://）时加载：视频 v3 的 2.5D 配图 */\nwindow.FD_VIDEO3_ASSETS = %s;\n" % json.dumps(v3assets))

VIDEO2, PLAN, AL = None, None, None
if WORDS:
    chp = os.path.join(os.path.dirname(V_AUDIO), "chapters.json")
    bounds = [c["startTime"] for c in json.load(open(chp, encoding="utf-8"))["chapters"]] if os.path.exists(chp) else None
    AL = video_align.align(V_NARR, WORDS, V_AUDIO, round(v_real, 3), bounds if bounds and len(bounds) == len(V_NARR) else None)
    beats_cfg = getattr(CFG, "VIDEO_BEATS", None)
    bfile = getattr(CFG, "VIDEO_BEATS_FILE", None)
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
        json.dump({"说明": "视频 v2 场景计划：每屏的模板、起止秒和元素出现时刻（由 build_v3.py 生成，播放器读 issue.js 里的同一份）",
                   "templates_library": video_plan.TEMPLATES, **{k: v for k, v in VIDEO2.items() if k != "cues"}},
                  f, ensure_ascii=False, indent=1)
elif HAS_V12:
    print("注意：没有旁白的逐词时间（本机没有 mlx_whisper，也没有缓存），视频沿用第一版")


# ---------------------------------------------------------------- 8. 稿件条目 → stories（与 v2 相同）
def coverage(ev):
    out = {"zh": [], "en": [], "social": []}
    names_en = {}
    for m in EVENT_MEMBERS.get(ev, []):
        name = re.sub(r"（.*?）", "", m.get("source_name") or "").strip()
        name = FEED_NAME.get(name, name)   # 抓取源分类名（“中国 AI 实验室 GitHub 新建仓库”）换成 GitHub
        if not name:
            continue
        layer = m.get("layer") or ""
        # v3.2：没标语言的报道按标题文字判断（Ars Technica 的英文报道以前会被算成“社区/社交”）
        lang = m.get("lang") or (("zh" if CJK.search(m.get("title") or "") else "en") if m.get("title") else None)
        grp = "social" if layer in ("community", "social") or not lang else ("zh" if lang == "zh" else "en")
        if name not in out[grp]:
            out[grp].append(name)
        if name_en(name) != name:
            names_en[name] = name_en(name)
    if names_en:
        out["names_en"] = names_en
    return out


READ_RE = {"zh": re.compile(r"(?:我们的理解是|我们的判断是|我们的理解|我们的判断)[，,：:]?\s*"),
           "en": re.compile(r"(?:Our (?:read|reading|understanding|view)(?: is| here is)?(?: that)?)[:,]?\s*")}


def split_read(why, read, L):
    """“为什么重要”分两层（v3.2）：转述别人的判断，和我们自己的理解（页面上用一个小标签隔开，不再每句都写“我们的理解是”）。
    稿子写了 read_zh / read_en 就直接用；没写就在 why 里找“我们的理解是 / Our read”从那里切开。"""
    if read:
        return why, read
    m = READ_RE[L].search(why or "")
    if not m:
        return why, ""
    rest = why[m.end():].strip()
    if L == "en" and rest:
        rest = rest[0].upper() + rest[1:]
    return why[:m.start()].strip(), rest


STORIES, ORDER = {}, {}
n_head = 0
for sec in WEB.get("sections") or []:
    kind = sec["kind"]
    for it in sec.get("items") or []:
        ev = it["id"]
        sid = "term" if kind == "term" else ev
        local = {s["id"]: gid(s) for s in it.get("sources") or []}
        evs = [ev] + ([r["id"] for r in it.get("related") or []] if kind == "term" else [])
        st = {"id": sid, "ev": ev, "kind": kind, "status": it.get("status") or "reported",
              "region": REGION.get(ev) or ("cn" if kind == "cn_intl" else "intl"),
              "title_zh": it.get("title_zh", ""), "title_en": it.get("title_en", ""),
              "summary_zh": it.get("summary_zh", ""), "summary_en": it.get("summary_en", ""),
              "tab_zh": it.get("tab_zh") or "", "tab_en": it.get("tab_en") or "",   # v3.2 页签上的短标题（没写就用标题）
              "sources": list(dict.fromkeys(local.values()))}
        for L in ("zh", "en"):
            body, sents = cite_paras(it.get("body_" + L), evs, L)
            st["body_" + L] = body
            st["lead_" + L] = lead3(sents)
            why_t, read_t = split_read(it.get("why_" + L) or "", it.get("read_" + L) or "", L)
            st["why_" + L] = cite_paras(why_t, evs, L)[0]
            st["read_" + L] = [x.strip() for x in re.split(r"\n+", read_t) if x.strip()]   # “我们的理解”：不挂出处
        nums = []
        for n in it.get("numbers") or []:
            x = {"value": n.get("value"), "label_zh": n.get("label_zh", ""), "label_en": n.get("label_en", "")}
            if local.get(n.get("source_id")):
                x["cite"] = local[n["source_id"]]
            ve = n.get("value_en") or value_en(n.get("value"))
            if ve:
                x["value_en"] = ve
            if n.get("layer"):                 # 周末（11-01 晚）：这个数放在深度／深谈的哪一层下面
                x["layer"] = n["layer"]
            nums.append(x)
        st["numbers"] = nums
        if kind == "deep":                     # 周末卡片上的核心问题、一句话结论，和深度那一块里折叠的名词解释（11-01 晚）
            for k in ("question_zh", "question_en", "conclusion_zh", "conclusion_en"):
                st[k] = (it.get(k) or "").strip()
            gl = []
            for e in it.get("glossary") or []:
                if not ((e.get("zh") or "").strip() and (e.get("explain_zh") or "").strip()):
                    print("注意：名词解释“%s”缺 zh 或 explain_zh，不放" % (e.get("zh") or e.get("en") or "?"))
                    continue
                g = {"zh": e["zh"].strip(), "en": (e.get("en") or "").strip(),
                     "explain_zh": e["explain_zh"].strip(), "explain_en": (e.get("explain_en") or "").strip()}
                if e.get("layer"):
                    g["layer"] = e["layer"]
                if local.get(e.get("source_id")):
                    g["cite"] = local[e["source_id"]]
                gl.append(g)
            st["glossary"] = gl
        st["related"] = [{"id": r["id"], "note_zh": r.get("note_zh", ""), "note_en": r.get("note_en", ""),
                          **({"relation": r["relation"]} if r.get("relation") else {})} for r in it.get("related") or []]
        st["coverage"] = coverage(ev)
        if (sid if kind == "term" else ev) in IMG:
            st["image"] = IMG[sid if kind == "term" else ev]
        _lt = (it.get("title_zh") or "") + (it.get("summary_zh") or "")
        st["listen"] = listen_at(kind, _lt, n_head if kind == "headline" else None)
        if kind != "deep":                     # 深度／深谈固定跳第一层，开场里的预告和它很像，不再报"可能跳错"
            listen_check(sid, _lt, st["listen"])
        if kind == "headline":
            n_head += 1
            st["charts"] = (getattr(CFG, "STORY_CHARTS", None) or {}).get(ev, [])
        STORIES[sid] = st
        ORDER.setdefault(kind, []).append(sid)

if VIDEO3:                                    # "看这一段"：v3 播放器的 scenes 就是各章，按章对到条目
    ch_index = {c["id"]: i for i, c in enumerate(VIDEO3["chapters"])}
    for cl in VIDEO3.get("clusters", []):
        i = ch_index.get(cl.get("ch"))
        for ev in cl.get("stories", []):
            if i is not None and ev in STORIES and "watch" not in STORIES[ev]:
                STORIES[ev]["watch"] = {"scene": i, "t": VIDEO3["chapters"][i]["start"]}
elif VIDEO2:
    for i, b in enumerate(VIDEO2["beats"]):
        if b.get("ev") in STORIES and b["tpl"] != "recap" and "watch" not in STORIES[b["ev"]]:
            STORIES[b["ev"]]["watch"] = {"scene": i, "t": b["start"]}
SCENE_OWNER = {}
for k, st in ({} if (VIDEO2 or VIDEO3 or not VIDEO) else STORIES).items():
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

items_text = [(k, (v["title_zh"] or "") + (v["summary_zh"] or "")) for k, v in STORIES.items() if v["kind"] != "term"]
heads = []
DCARD = WEB.get("daily_card") or {}
for h in DCARD.get("headlines") or []:
    hb = bigr(h.get("zh"))
    best = max(items_text, key=lambda x: len(hb & bigr(x[1]))) if items_text else (None, "")
    heads.append(dict(h, ref=best[0]))
term_card = dict(DCARD.get("term") or {})
if getattr(CFG, "TERM_LIKE", None):
    term_card["like_zh"] = CFG.TERM_LIKE.get("zh", "")
    term_card["like_en"] = CFG.TERM_LIKE.get("en", "")

# ---------------------------------------------------------------- 9. 今日数字、图表、预告看板、对照（全部过 ref 核对）
# 今日数字的箭头规则：写了 dir（涨跌箭头）就必须有 change——要么有出处的“之前”值，要么这个数本身就是涨跌幅。
NUMBERS = []
for n in getattr(CFG, "NUMBERS", None) or []:
    ch = n.get("change") or {}
    if n.get("dir") and not (ch.get("before") is not None or ch.get("delta")):
        sys.exit("今日数字 %s：只有真实的前后变化或涨跌幅才能画箭头。单纯的计数请去掉 dir；"
                 "有前后对比请写 change=dict(before=…, ref=…)，本身是涨跌幅请写 change=dict(delta=True)。" % n["story"])
    x = {k: v for k, v in n.items() if k not in ("ref", "sub_ref", "change")}
    x["zh"], x["en"] = dict(n["zh"]), dict(n["en"])
    cites = [ref(n["ref"])] + ([ref(n["sub_ref"])] if n.get("sub_ref") else [])
    if ch.get("before") is not None:
        if not ch.get("ref"):
            sys.exit("今日数字 %s：change 里的 before 也要写 ref（出处）。" % n["story"])
        cites.append(ref(ch["ref"]))
        x["zh"]["from"] = ch["before"]
        x["en"]["from"] = ch.get("before_en", ch["before"])
        x["change"] = "before"
    elif ch.get("delta"):
        x["change"] = "delta"
    if not n.get("dir"):
        x["dir"] = None
    x["cite"] = list(dict.fromkeys(cites))
    NUMBERS.append(x)

CHARTS = {}
for cid, ch in (getattr(CFG, "CHARTS", None) or {}).items():
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

CFG_WATCH = getattr(CFG, "WATCH", None) or []
if len(CFG_WATCH) > 5:
    sys.exit("预告看板最多 5 条（宁缺毋滥），现在配置里有 %d 条，请删到 5 条以内。" % len(CFG_WATCH))
WATCH = []
for w in CFG_WATCH:
    x = {k: v for k, v in w.items() if k != "refs"}
    if x.get("status") not in ("rumor", "teaser", "scheduled", "reported"):
        print("预告看板：状态 %r 不认识，按“报道称”显示（可选 rumor / teaser / scheduled / reported）" % x.get("status"))
        x["status"] = "reported"
    x["cite"] = list(dict.fromkeys(ref(r) for r in w.get("refs") or []))
    WATCH.append(x)


# v3.2 预告看板画成时间轴，节点按配置里的先后排（配置要求“按时间先后排”）。
# 能读出具体月份的几条（“11 月 4 日”“12 月”）顺手核一下先后，排反了只提醒、不改顺序（“下周”“第四季度”这类说法没法精确比较）。
def _when_key(s):
    m = re.search(r"(\d{1,2})\s*月(?:\s*(\d{1,2})\s*日)?", s or "")
    if not m:
        return None
    mon, day = int(m.group(1)), int(m.group(2) or 15)
    if mon < int(DATE[5:7]):   # 跨年：比这一期的月份小，算明年
        mon += 12
    return mon * 40 + day


_keys = [(w.get("when_zh"), _when_key(w.get("when_zh"))) for w in WATCH]
_dated = [(t, k) for t, k in _keys if k is not None]
for (t1, k1), (t2, k2) in zip(_dated, _dated[1:]):
    if k2 < k1:
        print("注意：预告看板里“%s”排在“%s”后面，但日期更早；时间轴按配置顺序画，请检查先后" % (t2, t1))

# ---------------------------------------------------------------- 9b. 国内外对照：关系类型（v3.2）
# 每一对写 relation（词表在 site/tools/v3_site.py 的 RELATIONS）；配置没写就读网页稿 related 里的 relation；
# 都没有或不在词表里，按“呼应”。中间那句“我们的理解”取自稿件 related 的 note，去掉“中外对照：”之类的前缀。
REL_INDEX = {}
for name, r in SITECFG.RELATIONS.items():
    for alias in [name, r["key"], r["label_zh"], r["en"]] + list(r.get("alias", ())):
        REL_INDEX[re.sub(r"[\s（）()·]", "", alias).lower()] = name


def relation_of(raw):
    k = re.sub(r"[\s（）()·]", "", str(raw or "")).lower()
    return REL_INDEX.get(k)


def strip_pair_prefix(s, lang):
    if lang == "zh":
        return re.sub(r"^\s*(?:国内外对照|中外对照|中外|对照)\s*[：:]\s*", "", s or "")
    return re.sub(r"^\s*(?:China|International|World)[^:]{0,32}?\bpair\s*:\s*", "", s or "", flags=re.I)


PAIRS = []
for p in getattr(CFG, "PAIRS", None) or []:
    if p.get("cn") not in STORIES or p.get("intl") not in STORIES:
        print("注意：国内外对照 %s × %s 有一边不在稿件里，跳过这一对" % (p.get("intl"), p.get("cn")))
        continue
    cn = STORIES[p["cn"]]
    note = next((r for r in cn["related"] if r["id"] == p["intl"]), None) or \
        next((r for r in STORIES[p["intl"]]["related"] if r["id"] == p["cn"]), {})
    raw = p.get("relation") or note.get("relation")
    name = relation_of(raw)
    if not name:
        print("国内外对照 %s × %s：%s，按“呼应”画" % (p["intl"], p["cn"], ("关系 %r 不在词表里" % raw) if raw else "没写关系"))
        name = "呼应"
    R = SITECFG.RELATIONS[name]
    cn["region"] = "cn"   # 对照里国内那一边，地区一律是“国内”（选题数据里常缺 subject_region）
    PAIRS.append(dict(p, note_zh=strip_pair_prefix(p.get("note_zh") or note.get("note_zh", ""), "zh"),
                      note_en=strip_pair_prefix(p.get("note_en") or note.get("note_en", ""), "en"),
                      label_zh=p.get("label_zh") or cn["title_zh"], label_en=p.get("label_en") or cn["title_en"],
                      **{k: p[k] for k in ("intl_zh", "intl_en", "cn_zh", "cn_en") if p.get(k)},   # 对照卡片里两边各一句（不写就用摘要）
                      relation={"k": R["key"], "name": name, "label_zh": R["label_zh"], "label_en": R["en"],
                                "lead": p.get("lead") if p.get("lead") in ("intl", "cn") else None}))

# ---------------------------------------------------------------- 9c. 头条、要闻的配图版式（v3.2）
# 版式名单在 site/tools/v3_site.py 的 LAYOUTS。每条按“日期＋条目号”的哈希挑一种（重新组装结果不变），
# 头条到要闻一路排下来：相邻两条不用同一种，而且这一期没用过的版式优先（五条以内不会重复）。
# 想给某条指定版式：每期配置里写 LAYOUT = {"E001": "glass"}。
import hashlib  # noqa: E402

_lay_pool = [x for x in getattr(SITECFG, "LAYOUTS", None) or [] if x in LAYOUT_NAMES] or ["split-l"]
_lay_fix = getattr(CFG, "LAYOUT", None) or {}
_prev, _used = None, set()
for sid in ORDER.get("headline", []) + ORDER.get("brief", []):
    h = int(hashlib.sha1((DATE + "|" + sid).encode("utf-8")).hexdigest(), 16)
    cands = [x for x in _lay_pool if x != _prev and x not in _used] or [x for x in _lay_pool if x != _prev] or _lay_pool
    lay = _lay_fix.get(sid) if _lay_fix.get(sid) in LAYOUT_NAMES else cands[h % len(cands)]
    STORIES[sid]["layout"] = _prev = lay
    _used.add(lay)
    if len(_used) >= len(_lay_pool):
        _used = set()
print("配图版式：", {sid: STORIES[sid]["layout"] for sid in ORDER.get("headline", []) + ORDER.get("brief", [])})

# ---------------------------------------------------------------- 9d. 参考来源的标题和英文名（v3.2）
# 合集页（标题里用“；”串起几条新闻，如“……；DeepSeek 完成第二轮融资……｜极客早知道”）：只显示和本条有关的那一段，注明出自合集，
# 免得读者以为出处挂错了。英文名照《英文名表》。
for sid, src in SOURCES.items():
    t = src.get("title") or ""
    segs = [x.strip() for x in re.split(r"[；;]", re.sub(r"\s*[｜|]\s*[^｜|]*$", "", t)) if x.strip()]
    digest = (re.search(r"[｜|]\s*([^｜|]+)$", t) or [None, ""])[1].strip()
    if len(segs) >= 2:
        ref_txt = " ".join((CARDS[e].get("title_zh") or "") + (CARDS[e].get("one_line_zh") or "") for e in SRC_EVENTS.get(sid, ()) if e in CARDS)
        B = bigr(ref_txt)
        best = max(segs, key=lambda x: len(B & bigr(x)))
        if B and len(B & bigr(best)) >= 3:
            src["title"] = "%s（%s中的一条）" % (best, ("《%s》合集" % digest) if digest else "合集页")
            src["title_en"] = "%s (one item in a %sdigest)" % (best, (digest + " ") if not CJK.search(digest) else "")
    ne = name_en(src["name"])
    if ne and ne != src["name"]:
        src["name_en"] = ne

# ---------------------------------------------------------------- 10. 组装这一期的数据
podcast = {
    "file": "audio/podcast.mp3", "duration": p_dur, "chapters": chapters, "peaks": peaks,
    "title_zh": "%s · %d 月 %d 日" % (SITECFG.NAME_ZH, int(DATE[5:7]), int(DATE[8:10])),
    "title_en": "%s · %s %d" % (SITECFG.NAME_EN_SHORT, MONTHS[int(DATE[5:7]) - 1], int(DATE[8:10])),
} if HAS_POD else None
now = datetime.now(timezone.utc).astimezone()
_dt = datetime.strptime(DATE, "%Y-%m-%d")
WEEKDAY = getattr(CFG, "WEEKDAY", None) or ("星期" + "一二三四五六日"[_dt.weekday()], _dt.strftime("%A"))
ISSUE = {
    "date": DATE, "weekday_zh": WEEKDAY[0], "weekday_en": WEEKDAY[1],
    "meta": {"test": True, "generated_at": now.isoformat(timespec="minutes"), "site": SITECFG.SITE_HOST,
             "draft": CFG.WEB, "podcast_dir": PODCAST_DIR, "builder": "build_v3.py"},
    "theme": {"accent": THEME["accent"], "name_zh": SITECFG.ACCENTS[THEME["accent"]],
              "name_en": getattr(SITECFG, "ACCENTS_EN", {}).get(THEME["accent"], THEME["accent"]), "why_zh": THEME.get("why_zh", "")},
    "card": {"headlines": heads, "term": dict(term_card, ref="term"), "image": IMG.get("card")},
    "numbers": NUMBERS,
    "media": {"video": VIDEO3 or VIDEO2 or VIDEO, "podcast": podcast},
    "stories": STORIES, "order": ORDER,
    "charts": CHARTS, "flash_chart": getattr(CFG, "FLASH_CHART", None),
    "watch": WATCH, "pairs": PAIRS,
    "sources": [SOURCES[k] for k in sorted(SOURCES)],
}
# 周末两版（11-01 晚定）：网页稿里有深度／深谈那一条，周六按 "sat"、周日按 "sun" 排版（版面设置在 v3_site.py 的 WEEKEND）。
# 工作日不加这两个键，页面数据和以前完全一样。
EDITION = ("sun" if _dt.weekday() == 6 else "sat") if ORDER.get("deep") else None
if EDITION:
    ISSUE["edition"] = EDITION
    ISSUE["weekend"] = dict(SITECFG.WEEKEND.get(EDITION) or {}, layer_numbers_max=SITECFG.LAYER_NUMBERS_MAX)

# ---------------------------------------------------------------- 10a. 西文引号、撇号改成印刷体（v3.2）
# Tom's → Tom’s、"tampered" → “tampered”：网页上显示的所有文字（含参考来源原标题、视频字幕数据）都过一遍，只改排印不改字词；
# 网址和代码样的片段不碰。规则见 site/tools/typo_quotes.py。要在 10b 读音表、10c 换行点之前做（换行点会隔开撇号两边）。
import typo_quotes  # noqa: E402

_tq = {}
ISSUE = typo_quotes.tree(ISSUE, stats=_tq)
# v3.2：英文正文里不该出现中文媒体名（“IT之家”→“ITHome”），照《英文名表》换；参考来源的原文标题不动
_MEDIA_ZH = [(z, e) for z, e, k in NAME_REG if k in ("media", "feed") and CJK.search(z)]


def en_names(x, key="", top=False):
    if isinstance(x, dict):
        return {k: (v if top and k == "sources" else en_names(v, k)) for k, v in x.items()}
    if isinstance(x, list):
        return [en_names(v, key) for v in x]
    if isinstance(x, str) and key.endswith("_en"):
        for z, e in _MEDIA_ZH:
            x = x.replace(z, e)
    return x


ISSUE = en_names(ISSUE, top=True)
print("印刷体引号：改了 %d 段文字里的直引号/直撇号" % _tq.get("changed", 0))

# ---------------------------------------------------------------- 10b. 人名写法按读音表（和播客稿用同一张表）
# 网页上我们自己写的中文（键名以 _zh 结尾的标题、摘要、正文、注释）也按《读音表》写：奥尔特曼 → Altman。
# 不动的：参考来源里的原文标题（键名 title）、引语译文（键名含 quote 或 said）、
# 视频（旁白音频还是旧稿的读法，字幕要和声音对得上；视频 v3 重做时一起改）。
LEX = load_module(os.path.join(ROOT, "pipeline", "lexicon_check.py"), "lexicon_check")
LEX_ENTRIES, LEX_EXTRA, LEX_SUFFIX, _ = LEX.load_lexicon()
LEX_DONE = []


def lex_zh(x, key=""):
    if isinstance(x, dict):
        return {k: (v if k == "media" and not key else lex_zh(v, k)) for k, v in x.items()}
    if isinstance(x, list):
        return [lex_zh(v, key) for v in x]
    if (isinstance(x, str) and key.endswith("_zh") and "quote" not in key and "said" not in key
            and re.search(r"[\u4e00-\u9fff]", x)):
        out, done = LEX.apply_fixes(x, LEX.check(x, LEX_ENTRIES, LEX_EXTRA, LEX_SUFFIX)["_fixes"])
        LEX_DONE.extend(done)
        return out
    return x


ISSUE = lex_zh(ISSUE)
# 日卡“今日三件事”的中文键名是 zh（不是 *_zh），单独过一遍；图表节点之类的短标签（也叫 zh）不动，免得“千问 Qwen”变成“千问千问”
ISSUE["card"]["headlines"] = [dict(h, zh=lex_zh(h.get("zh", ""), "headline_zh")) for h in ISSUE["card"].get("headlines") or []]
if LEX_DONE:
    print("读音表：网页中文里改了 %d 处人名写法（%s）"
          % (len(LEX_DONE), "、".join(sorted({d["原文"] + "→" + d["改成"] for d in LEX_DONE}))))

# ---------------------------------------------------------------- 10c. 中文按词组换行（v3.1）
# 我们自己写的中文（键名以 _zh 结尾的标题、摘要、正文、注释、标签，以及日卡三件事）在词组之间插入看不见的换行点 U+200B；
# 网页上配合 CSS 的 word-break: keep-all，一行只在词组之间断开，不会把“融资”拆成两行。怎么切见 site/tools/zh_breaks.py
# （BudouX 切词组，jieba 分词把关）。必须在 10b 读音表之后做：读音表按原文匹配人名，插了换行点就对不上了。
# 不动的：参考来源（原文标题、媒体名）、报道光谱里的媒体名（coverage）、视频和播客（media：视频字幕是逐字动画，插了会多出空格子）、
# 图表里画在图上的短标签（ECharts 不按它换行；时间线是网页文字，照插）、今日一词这个词本身（一个词，不拆）。
import zh_breaks  # noqa: E402

zh_breaks.load([term_card.get("zh", "")] + [t_.get("zh", "") for c_ in CARDS.values() for t_ in (c_.get("terms") or [])])
BX = zh_breaks.phrase_breaks


def bx_tree(x, key="", top=False):
    if isinstance(x, dict):
        return {k: (v if (top and k in ("media", "sources", "charts", "card")) or k == "coverage" else bx_tree(v, k))
                for k, v in x.items()}
    if isinstance(x, list):
        return [bx_tree(v, key) for v in x]
    return BX(x) if isinstance(x, str) and key.endswith("_zh") else x


def bx_chart(ch):
    ch = dict(ch)
    for k in ("title_zh", "note_zh"):
        if ch.get(k):
            ch[k] = BX(ch[k])
    if ch.get("type") == "timeline":
        ch["items"] = [dict(it, **{k: BX(it[k]) for k in ("text_zh", "when_zh") if it.get(k)}) for it in ch.get("items", [])]
    return ch


ISSUE = bx_tree(ISSUE, top=True)
ISSUE["charts"] = {cid: bx_chart(ch) for cid, ch in ISSUE["charts"].items()}
_card = ISSUE["card"]
ISSUE["card"] = dict(_card, headlines=[dict(h, zh=BX(h["zh"])) for h in _card["headlines"]],
                     term={k: (BX(v) if k.endswith("_zh") else v) for k, v in _card["term"].items()})
print("中文按词组换行：%d 段文字；BudouX 切点 %d 个，保留 %d 个（其余落在词中间、空格旁或标点前，已去掉）；过长词组里按词边界补 %d 个"
      % (zh_breaks.STATS["strings"], zh_breaks.STATS["budoux"], zh_breaks.STATS["kept"], zh_breaks.STATS["extra"]))

# ---------------------------------------------------------------- 11. 字体：按这一期实际用到的字截取，打成 WOFF2
from fontTools import subset as ftsubset  # noqa: E402

FONT_DIR = os.path.expanduser(SITECFG.FONT_CACHE)
# v3.2：加上 U+2018-2019（‘ ’）：中文页面里英文的撇号 Tom’s 也用 Times，不会被楷体排成全角；中文的双引号 “” 仍归中文字体
LATIN_RANGE = ("U+0020-007E, U+00A0-00FF, U+0100-017F, U+0192, U+02C6, U+02DC, U+2010-2013, U+2018-2019, U+2030, U+2032-2033, "
               "U+20AC, U+2122, U+2212")
ASCII = "".join(chr(i) for i in range(0x20, 0x7F))


def all_strings(x, out):
    if isinstance(x, str):
        out.append(x)
    elif isinstance(x, dict):
        for k, v in x.items():
            if k not in ("url", "src", "src_sm", "file", "audio", "peaks"):
                all_strings(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            all_strings(v, out)
    return out


def tpl_text():
    """模板里会显示的中文：app.js 的界面文字（I18N 中文段）和 index.html 里的静态文字。"""
    js = open(os.path.join(TPL, "app.js"), encoding="utf-8").read()
    m = re.search(r"/\* I18N-ZH-START \*/(.*?)/\* I18N-ZH-END \*/", js, re.S)
    if not m:
        sys.exit("app.js 里找不到 I18N-ZH-START / I18N-ZH-END 标记，没法确定界面文字要用哪些字。")
    html = re.sub(r"<!--.*?-->|<script.*?</script>|<style.*?</style>", "", open(os.path.join(TPL, "index.html"), encoding="utf-8").read(), flags=re.S)
    sec = re.findall(r"\bsec_[a-z_]+:\s*'([^']*)'", m.group(1))
    return m.group(1), html, sec


UI_ZH, HTML_TXT, SEC_ZH = tpl_text()
REL_TXT = "".join(r["label_zh"] + r["en"] for r in SITECFG.RELATIONS.values())
EVERY = ("".join(all_strings(ISSUE, [])) + UI_ZH + HTML_TXT + SITECFG.NAME_ZH + SITECFG.NAME_EN + SITECFG.NAME_EN_SHORT
         + SITECFG.FOOT_ZH + SITECFG.FOOT_EN + "".join(SITECFG.FOOT_PAST) + "".join(SITECFG.ACCENTS.values()) + REL_TXT
         + "".join(getattr(SITECFG, "MUSIC_CREDIT", ())))


def chars_of(*texts):
    return "".join(sorted(set("".join(texts)) - set("\n\r\t")))


def is_wide(c):
    o = ord(c)
    return o >= 0x2E80 or 0x2014 <= o <= 0x2027 or o in (0x00B7, 0x00D7)


# 标题字体（思源宋体）：各条标题、三件事、对照两边的标题、预告条目、刊名、版块名、今日一词，以及视频画面上的大字
title_texts = [SITECFG.NAME_ZH, SITECFG.NAME_EN, "".join(SEC_ZH)]
for st in STORIES.values():
    title_texts += [st["title_zh"], st["title_en"]]
    title_texts += [str(n.get(k) or "") for n in st.get("numbers") or [] for k in ("value", "value_en")]   # 数字卡的大字（.kn-i b）也用宋体粗
    title_texts += [str(g.get(k) or "") for g in st.get("glossary") or [] for k in ("zh", "en")]           # 周末名词解释的词条也用宋体粗
for n in NUMBERS:                                                     # 今日数字的单位（“万亿日元”“亿美元”）也用宋体粗
    title_texts += [str((n.get(L) or {}).get(k) or "") for L in ("zh", "en") for k in ("pre", "suf")]
for h in heads:
    title_texts += [h["zh"], h.get("en", "")]
title_texts += [term_card.get("zh", ""), term_card.get("en", "")]
for w in WATCH:
    title_texts += [w["text_zh"], w["text_en"], w["when_zh"], w["when_en"]]
if VIDEO2:
    title_texts += all_strings(VIDEO2["beats"], [])
if VIDEO3:                                    # 视频画面上的大字也用思源宋体
    title_texts += all_strings(VIDEO3, [])
TITLE_700 = chars_of(ASCII, "“”‘’—–…·×→\u200b\u00a0", *title_texts)   # \u200b 换行点、\u00a0 不换行空格（10c 插入的）
TITLE_900 = chars_of(ASCII, SITECFG.NAME_ZH, "".join(SEC_ZH), term_card.get("zh", ""), "今日三件事",
                     *(all_strings(VIDEO3.get("S", {}), []) if VIDEO3 else []))   # 视频 v3 的大标题（如"今日地图"）用特粗
BODY_CJK = chars_of("".join(c for c in EVERY if is_wide(c)), "“”‘’—…·（）《》「」：；，。！？、\u200b")
LATIN_USED = chars_of(ASCII, "‘’“”–—…·×−€™", "".join(c for c in EVERY if not is_wide(c) and ord(c) >= 0x20))
DISPLAY = chars_of(ASCII, "−–—‘’“”·×")


def subset_to(src_name, text, out_name):
    src = os.path.join(FONT_DIR, src_name)
    if not os.path.exists(src):
        sys.exit("缺原字体 %s：请先把它下载到 %s（来源见 site/tools/v3_site.py 的 FONT_FILES 注释）" % (src_name, FONT_DIR))
    opts = ftsubset.Options()
    opts.flavor = "woff2"
    opts.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]   # 保留版权和许可证说明
    opts.name_languages = [0x409]
    opts.hinting = False
    opts.desubroutinize = True
    opts.notdef_outline = True
    opts.drop_tables += ["Debg"]   # Tinos 带的调试表，网页用不上
    font = ftsubset.load_font(src, opts)
    sub = ftsubset.Subsetter(opts)
    sub.populate(text=text)
    sub.subset(font)
    ftsubset.save_font(font, os.path.join(ISS, "fonts", out_name), opts)
    return out_name


for f in os.listdir(os.path.join(ISS, "fonts")):
    os.remove(os.path.join(ISS, "fonts", f))
FONT_URL = "issues/%s/fonts/" % DATE
faces, font_report = [], []


def face(family, weight, style, file_name, local=(), urange=None):
    src = ", ".join(['local("%s")' % n for n in local] + ['url("%s%s") format("woff2")' % (FONT_URL, file_name)])
    faces.append('@font-face{font-family:"%s";font-style:%s;font-weight:%s;font-display:swap;src:%s;%s}'
                 % (family, style, weight, src, ("unicode-range:%s" % urange) if urange else ""))


def make(key, text, out, family, weight, style="normal", local=(), urange=None, also=()):
    subset_to(SITECFG.FONT_FILES[key], text, out)
    face(family, weight, style, out, local, urange)
    for fam in also:
        face(fam, weight, style, out, local, None)
    font_report.append((out, len(text), os.path.getsize(os.path.join(ISS, "fonts", out))))


make("title_700", TITLE_700, "title-700.woff2", "FD Title", 700)
make("title_900", TITLE_900, "title-900.woff2", "FD Title", 900)
if SITECFG.BODY_FONT == "kai":
    make("kai_400", BODY_CJK, "body-kai.woff2", "FD Kai", 400)
elif SITECFG.BODY_FONT == "song":
    make("song_400", BODY_CJK, "body-song.woff2", "FD Song", 400)
make("display_400", DISPLAY, "display.woff2", "FD Display", 400)
make("display_400i", DISPLAY, "display-italic.woff2", "FD Display", 400, "italic")
# 正文里的西文和数字：先用本机的 Times New Roman，没有时（安卓等）才下载 Tinos。
#   FD Latin 只管西文字符（中文引号、破折号仍归中文字体）；FD Latin Full 给英文界面用，全部字符都归它。
make("latin_400", LATIN_USED, "latin.woff2", "FD Latin", 400, local=("Times New Roman", "TimesNewRomanPSMT"), urange=LATIN_RANGE)
make("latin_700", LATIN_USED, "latin-bold.woff2", "FD Latin", 700, local=("Times New Roman Bold", "TimesNewRomanPS-BoldMT"), urange=LATIN_RANGE)
make("latin_400i", LATIN_USED, "latin-italic.woff2", "FD Latin", 400, "italic", local=("Times New Roman Italic", "TimesNewRomanPS-ItalicMT"), urange=LATIN_RANGE)
# v3.1 FD Num：同一份 Times / Tinos，只管数字和几个数字符号；排在界面字体（黑体）、英文展示字体和图表字体的最前面，
#   这样按钮、标签、日期、图表里的数字也都是 Times New Roman，字母和中文不受影响。不多下载任何文件。
NUM_RANGE = "U+0024-0025, U+0028-0029, U+002B-003A, U+005B, U+005D, U+00D7, U+2013, U+2212"
for (wt, sty, file_, loc) in ((400, "normal", "latin.woff2", ("Times New Roman", "TimesNewRomanPSMT")),
                              (700, "normal", "latin-bold.woff2", ("Times New Roman Bold", "TimesNewRomanPS-BoldMT")),
                              (400, "italic", "latin-italic.woff2", ("Times New Roman Italic", "TimesNewRomanPS-ItalicMT"))):
    face("FD Num", wt, sty, file_, loc, NUM_RANGE)
for (fam, wt, sty, file_, loc) in (("FD Latin Full", 400, "normal", "latin.woff2", ("Times New Roman", "TimesNewRomanPSMT")),
                                  ("FD Latin Full", 700, "normal", "latin-bold.woff2", ("Times New Roman Bold", "TimesNewRomanPS-BoldMT")),
                                  ("FD Latin Full", 400, "italic", "latin-italic.woff2", ("Times New Roman Italic", "TimesNewRomanPS-ItalicMT"))):
    face(fam, wt, sty, file_, loc)
FONTS_CSS = "\n".join(faces)
ISSUE["fonts_css"] = FONTS_CSS
ISSUE["site"] = {"name_zh": SITECFG.NAME_ZH, "name_en": SITECFG.NAME_EN, "name_en_short": SITECFG.NAME_EN_SHORT,
                 "body_font": SITECFG.BODY_FONT, "foot_zh": SITECFG.FOOT_ZH, "foot_en": SITECFG.FOOT_EN,
                 "foot_past": list(SITECFG.FOOT_PAST), "music_credit": list(getattr(SITECFG, "MUSIC_CREDIT", ()))}


# v3.2 署名都放在折叠的“参考来源”末尾，只放给人看的几行（每种语言约 4 行）：配乐、配图由 AI 生成、视频画面里的标志来源、
# 真实照片的署名（有才放，一张一行）。视频数据里的逐条记录（编号、时间戳、每个标志的许可证）不上页面，留在数据文件里。
def _line(x):
    if isinstance(x, dict) and (x.get("zh") or x.get("en")):
        return {"zh": x.get("zh") or x.get("en"), "en": x.get("en") or x.get("zh")}
    if isinstance(x, (list, tuple)) and len(x) == 2 and all(isinstance(v, str) for v in x):
        return {"zh": x[0], "en": x[1]}
    return None


def _ckey(t):
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", t or "").lower()


_lines = []
_music = _line(getattr(SITECFG, "MUSIC_CREDIT", None))
if _music:
    _lines.append(_music)
_img = _line(getattr(SITECFG, "IMAGE_CREDIT", None)) if IMG else None
_vc = (VIDEO3 or {}).get("credits") if VIDEO3 else None
_vlines = [l for l in (_line(x) for x in ((_vc or {}).get("lines") or [] if isinstance(_vc, dict) else [])) if l]
_vlines += [l for l in [_line((VIDEO3.get("music") or {}).get("credit"))] if l] if VIDEO3 else []
_v_ai = any("AI" in (l["zh"] or "") and ("配图" in l["zh"] or "图" in l["zh"]) for l in _vlines) or \
    any((r or {}).get("kind") == "generated" for r in ((_vc or {}).get("images") or [] if isinstance(_vc, dict) else []))
if _img:   # 网页配图和视频场景图都由 AI 生成时合成一行
    _lines.append(_line(getattr(SITECFG, "IMAGE_CREDIT_WITH_VIDEO", None)) if _v_ai and getattr(SITECFG, "IMAGE_CREDIT_WITH_VIDEO", None) else _img)
for l in _vlines:
    if "AI" in (l["zh"] or "") and "生成" in (l["zh"] or "") and _img:
        continue   # 已并进上面那一行
    _lines.append(l)
if isinstance(_vc, dict):
    if (_vc.get("logos") or []) and not any("标志" in (l["zh"] or "") for l in _vlines) and getattr(SITECFG, "LOGO_CREDIT", None):
        _lines.append(_line(SITECFG.LOGO_CREDIT))   # 视频没给现成的一句：用一句通用说明，不列逐个标志
    for r in _vc.get("photos") or [r for r in (_vc.get("images") or []) if (r or {}).get("kind") not in (None, "generated")]:
        if isinstance(r, dict) and (r.get("credit_zh") or r.get("author")):   # 真实照片：一张一行
            zh = r.get("credit_zh") or "照片：%s（%s）" % (r.get("author"), r.get("license") or "")
            _lines.append({"zh": zh, "en": r.get("credit_en") or "Photo: %s (%s)" % (r.get("author"), r.get("license") or "")})
_credits, _seen = [], []
for c in _lines:
    k = _ckey(c["zh"])
    if not k or any(k in o or o in k for o in _seen):
        continue
    _seen.append(k)
    _credits.append(c)
ISSUE["credits"] = _credits
for lic in ("OFL_LXGWWenKaiScreen.txt", "LICENSE_NotoSerifCJK.txt", "OFL_InstrumentSerif.txt"):
    if os.path.exists(os.path.join(FONT_DIR, lic)):
        shutil.copy2(os.path.join(FONT_DIR, lic), os.path.join(ISS, "fonts", lic))
with open(os.path.join(ISS, "fonts", "README.txt"), "w", encoding="utf-8") as f:
    f.write("这些字体文件是按 %s 这一期用到的字截取的小字体包（WOFF2），只供本网页显示用，不是可安装的桌面字体。\n"
            "原字体均为 SIL Open Font License 1.1：思源宋体 Noto Serif SC（Adobe / Google）、霞鹜文楷屏幕阅读版 LXGW WenKai Screen（LXGW）、"
            "Instrument Serif（The Instrument Serif Project Authors）、Tinos（The Tinos Project Authors）。许可证全文见同目录 .txt 文件，"
            "也可在 https://openfontlicense.org 查看。\n" % DATE)

# ---------------------------------------------------------------- 12. 写出
with open(os.path.join(ISS, "issue.js"), "w", encoding="utf-8") as f:
    f.write("/* %s · %s · 由 site/tools/build_v3.py 组装，请勿手改 */\n" % (SITECFG.NAME_ZH, DATE))
    f.write("window.FD_ISSUES = window.FD_ISSUES || {};\n")
    f.write("window.FD_ISSUES[%s] = %s;\n" % (json.dumps(DATE), json.dumps(ISSUE, ensure_ascii=False, separators=(",", ":"))))
_lead = [{"zh": STORIES[ORDER["deep"][0]]["title_zh"], "en": STORIES[ORDER["deep"][0]]["title_en"]}] if EDITION else heads   # 周末往期列表写深度那一题
with open(os.path.join(ISS, "summary.json"), "w", encoding="utf-8") as f:
    json.dump({"date": DATE, "weekday_zh": WEEKDAY[0], "weekday_en": WEEKDAY[1], "accent": THEME["accent"],
               "lead_zh": _lead[0]["zh"] if _lead else "", "lead_en": _lead[0].get("en", "") if _lead else "",
               "fonts_css": FONTS_CSS, "card": IMG.get("card")}, f, ensure_ascii=False)

idx = []
for d in sorted(os.listdir(os.path.join(OUT, "issues"))):
    sp = os.path.join(OUT, "issues", d, "summary.json")
    if os.path.exists(sp):
        idx.append(json.load(open(sp, encoding="utf-8")))
latest = idx[-1]
with open(os.path.join(OUT, "issues", "index.js"), "w", encoding="utf-8") as f:
    f.write("/* 往期目录与全站设置：由 build_v3.py 扫描 issues/日期/summary.json 生成 */\n")
    f.write("window.FD_INDEX = %s;\n" % json.dumps({
        "latest": latest["date"],
        "issues": [{k: v for k, v in x.items() if k in ("date", "weekday_zh", "weekday_en", "lead_zh", "lead_en", "accent")} for x in idx],
        "site": ISSUE["site"]}, ensure_ascii=False))

# 模板：index.html 里填上最新一期的主题色、字体和刊名（页面打开时不闪一下）；首屏日卡大图预先加载
ACCENT_HEX = {"blue": "#0071e3", "amber": "#e08a00", "coral": "#d04a35", "violet": "#7d4fe0"}
html = open(os.path.join(TPL, "index.html"), encoding="utf-8").read()
card = latest.get("card") or {}
preload = ('<link rel="preload" as="image" href="issues/%s/%s" imagesrcset="issues/%s/%s %dw, issues/%s/%s %dw" '
           'imagesizes="(max-width: 900px) 100vw, 640px" fetchpriority="high">'
           % (latest["date"], card["src"], latest["date"], card["src_sm"], card["w_sm"], latest["date"], card["src"], card["w"])) if card else ""
for k, v in {"{{ACCENT}}": latest.get("accent", THEME["accent"]), "{{ACCENT_HEX}}": ACCENT_HEX[latest.get("accent", THEME["accent"])].replace("#", "%23"),
             "{{BODY_FONT}}": SITECFG.BODY_FONT, "{{NAME_ZH}}": SITECFG.NAME_ZH, "{{NAME_EN}}": SITECFG.NAME_EN.replace("&", "&amp;"),
             "{{NAME_EN_SHORT}}": SITECFG.NAME_EN_SHORT, "{{FONT_FACES}}": latest["fonts_css"], "{{PRELOAD}}": preload}.items():
    html = html.replace(k, v)
with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
    f.write(html)
for f in ("app.js", "style.css", "video.css", "video2.css", "video2.js", "video3.css", "video3.js"):
    shutil.copy2(os.path.join(TPL, f), os.path.join(OUT, f))
shutil.copy2(os.path.join(SITE, "video.js"), os.path.join(OUT, "video.js"))   # 第一版视频播放器，只给旧格式的往期用（按需加载）
for f in ("echarts.min.js", "gsap.min.js"):
    shutil.copy2(os.path.join(SITE, "vendor", f), os.path.join(OUT, "vendor", f))
if VIDEO3:                                    # three.js＋postprocessing 打包文件和许可证，只有 v3 视频要
    os.makedirs(os.path.join(OUT, "vendor", "three"), exist_ok=True)
    for f in ("three-bundle.min.js", "LICENSE-three.txt", "LICENSE-postprocessing.txt"):
        shutil.copy2(os.path.join(SITE, "vendor", "three", f), os.path.join(OUT, "vendor", "three", f))


# ---------------------------------------------------------------- 13. 报告
def kb(p):
    return round(os.path.getsize(p) / 1024)


print("期：", DATE, "| 输出：", os.path.relpath(OUT, ROOT), "| 主题色：", THEME["accent"], SITECFG.ACCENTS[THEME["accent"]],
      "| 正文字体：", SITECFG.BODY_FONT, "| 英文刊名：", SITECFG.NAME_EN)
print("来源：", len(SOURCES), "| 条目：", {k: v for k, v in ORDER.items()})
if EDITION:
    _dp = STORIES[ORDER["deep"][0]]
    print("周末版：", {"sat": "周六（今日深度卡＋今日数字）", "sun": "周日（本周深谈卡，不单列今日数字）"}[EDITION],
          "| 名词解释：", "、".join(g["zh"] for g in _dp.get("glossary") or []) or "没有",
          "| 分层的关键数字：", sum(1 for n in _dp["numbers"] if n.get("layer")))
print("配图：", {k: v["src"] for k, v in IMG.items()})
print("今日数字：", [(n["story"], n.get("dir") or "无箭头", n.get("change") or "计数") for n in NUMBERS])
print("预告看板：", len(WATCH), "条")
print("听这一段：", {k: v.get("listen") for k, v in STORIES.items()})
if PARAS:
    print("听这一段的段首时间：%s（块首＝每块第一段，块的开头是准的；对齐＝按配音时的 Whisper 转写定位；"
          "对齐＋停顿＝再校准到人声版里的停顿；估算＝按字数比例，没有对齐数据时用）"
          % "，".join("%s %d 段" % (k, v) for k, v in LISTEN_STAT.items()))
print("看这一段：", {k: "第 %d 屏 %s" % (v["watch"]["scene"] + 1, fmt_num(v["watch"]["t"])) for k, v in STORIES.items() if v.get("watch")})
if VIDEO3:
    vo = VIDEO3.get("voice", {})
    print("视频 v3：", len(VIDEO3["chapters"]), "章 |", VIDEO3["duration"], "秒 | 配音", vo.get("engine"), "（占位）" if vo.get("placeholder") else "")
if VIDEO2:
    a = AL["accuracy"]
    print("视频 v2：", len(VIDEO2["beats"]), "屏 | 模板", " → ".join(b["tpl"] for b in VIDEO2["beats"]),
          "| 逐字对齐：比上", a["matched_ratio"], "| 误差中位", a.get("median_abs_err"), "秒")
print("播客：", ("%s %s 秒 %d KB | 章节 %d" % (PODCAST_DIR, p_dur, kb(p_dst), len(chapters))) if HAS_POD else "没有（页面上不放播客）")
if not (VIDEO3 or VIDEO2 or VIDEO):
    print("视频：没有（页面上不放视频）")
print("字体（截取后）：", " | ".join("%s %d 字 %d KB" % (n, c, round(s / 1024)) for n, c, s in font_report))
print("体积 KB：issue.js", kb(os.path.join(ISS, "issue.js")), "| 图片",
      {f: kb(os.path.join(ISS, "img", f)) for f in sorted(os.listdir(os.path.join(ISS, "img")))})
