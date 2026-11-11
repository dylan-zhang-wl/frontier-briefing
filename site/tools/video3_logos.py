#!/usr/bin/env python3
"""视频 v3 的品牌标志库：site/assets/logos/（标志文件）＋ site/assets/logos/来源.json（每个标志从哪来、什么许可、哪天取的）。

画面上的"标志小签"（磨砂玻璃小签里放公司标志）只用这个库里的文件，构建时把文件内容嵌进视频数据（data: 地址），
播放时不向外网要任何东西。标志只做"单色"处理（按画面的字色或主题色整块上色，CSS 遮罩），形状、比例一概不动；
构建时只把四周的空白裁掉（改 SVG 最外层的 viewBox，不碰图形本身）。

取标志的顺序（只取当期用得到的，取过的留在库里下次直接用）：
  1. Simple Icons（npm 包 simple-icons，CC0；先查有没有这个品牌）
  2. Wikimedia Commons（优先"公有领域·纯文字标志 PD-textlogo"，或写明 CC0 / CC BY / CC BY-SA 的）
  3. 品牌官方的新闻资料包（手动下载后用 add-file 登记，写明网址和使用条款）
  都没有 → add-text 登记成"文字小签"（画面上用名字代替标志）。

用法（在项目根运行）：
    PY=~/.venvs/frontier-daily/bin/python
    $PY site/tools/video3_logos.py list                                    # 库里有什么
    $PY site/tools/video3_logos.py si-search samsung 7-eleven              # 在 Simple Icons 里查
    $PY site/tools/video3_logos.py add-si samsung samsung --zh 三星 --en Samsung --alias 三星电子 --form wordmark
    $PY site/tools/video3_logos.py add-commons micron "File:Micron Technology logo 2024.svg" --zh 美光 --en Micron --form wordmark
    $PY site/tools/video3_logos.py add-file foo 下载的.svg --zh … --en … --source-url 官方资料包网址 --license "使用条款原文要点"
    $PY site/tools/video3_logos.py add-text wujie --zh 无界动力 --en "Wujie Dongli" --why "Simple Icons、Commons 都没有"
    $PY site/tools/video3_logos.py measure                                 # 量四周空白（用本机 Chrome；新加的标志要跑一次）
    $PY site/tools/video3_logos.py preview 输出.html                       # 出一页对照（原样／单色字色／单色主题色），人眼核一遍

分镜里怎么用：任何能挂标志的地方写 "logos": ["samsung", {"key": "micron", "cue": "美光"}]（键就是这里的键）。
构建时核对：标志对应的公司名（中文、英文、别名）必须出现在它挂的那张卡的字里或它引用的事件卡原文里，否则不挂（提醒）。
"""
import argparse
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LIB = ROOT / "site/assets/logos"
SOURCES = LIB / "来源.json"
CACHE = Path.home() / ".cache/frontier-daily/logos"          # Simple Icons 包、下载的原件（仓库外，避开 iCloud 同步区）
UA = "frontier-daily/1.0 (daily briefing video; logo library builder)"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
# Commons 上能用的许可：公有领域（含 PD-textlogo 等）、CC0、CC BY、CC BY-SA（要署名的会写进来源）
OK_LICENSE = re.compile(r"^(public domain|pd\b|cc0|cc by(-sa)? \d|cc-by(-sa)?-\d)", re.I)
PW = os.environ.get("PLAYWRIGHT") or str(Path.home() / ".npm/_npx/9833c18b2d85bc59/node_modules/playwright/index.mjs")

HEAD = {
    "说明": "视频 v3 的品牌标志库。每个键是分镜里写的标志键；file 为空表示没有可用标志，画面上用名字做文字小签。"
            "names 用来核对“这个标志该不该出现在这张卡上”（中文名、英文名、别名任一出现在卡片字或事件卡原文里才挂）。"
            "form：wordmark＝字标（单独放）、symbol＝图形标（旁边配名字）。crop＝四周空白裁掉后的取景框（SVG 用户坐标／PNG 像素），"
            "构建时只改最外层 viewBox，不改标志本身。商标权归各自所有者，这里只在新闻报道中用来指称公司。"
            "由 site/tools/video3_logos.py 维护，请用它的命令增改。",
}


def say(*a):
    print(*a, flush=True)


def today():
    return datetime.now().strftime("%Y-%m-%d")      # 写进长期文件的日期读系统时钟


def load():
    if SOURCES.exists():
        d = json.loads(SOURCES.read_text(encoding="utf-8"))
    else:
        d = dict(HEAD, logos={})
    d.setdefault("logos", {})
    return d


def save(d):
    LIB.mkdir(parents=True, exist_ok=True)
    d = dict(HEAD, **{k: v for k, v in d.items() if k not in HEAD})
    d["logos"] = dict(sorted(d["logos"].items()))
    SOURCES.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _ssl():
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:          # python.org 装的 Python 自己不带根证书：用系统那一份
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem") if Path("/etc/ssl/cert.pem").exists() else ssl.create_default_context()


def http(url, timeout=60):
    for k in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=timeout, context=_ssl()).read()
        except urllib.error.HTTPError as e:
            if e.code == 429:            # Commons 限流：等一会儿再试
                time.sleep(6 * (k + 1))
                continue
            raise
    raise SystemExit("取不到 %s（一直被限流）" % url)


# ---------------------------------------------------------------- Simple Icons
def si_root(version=None):
    """本机缓存的 Simple Icons 包（没有就从 npm 下载一次）；返回 (包目录, 版本)。"""
    if not version:
        cached = sorted(CACHE.glob("simple-icons-*/package/data/simple-icons.json"))
        if cached:
            p = cached[-1].parent.parent
            return p, p.parent.name.split("-", 2)[2]
        meta = json.loads(http("https://registry.npmjs.org/simple-icons/latest"))
        version = meta["version"]
    root = CACHE / ("simple-icons-%s" % version)
    if not (root / "package/data/simple-icons.json").exists():
        meta = json.loads(http("https://registry.npmjs.org/simple-icons/%s" % version))
        say("下载 Simple Icons %s（约 %d MB，只下一次）…" % (version, meta["dist"].get("unpackedSize", 0) // 1_000_000))
        data = http(meta["dist"]["tarball"], timeout=300)
        root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            for m in tf.getmembers():               # 只解包里的 data/ 和 icons/（不解可执行的东西）
                if m.isfile() and re.match(r"^package/(data/simple-icons\.json|icons/[a-z0-9_-]+\.svg|LICENSE\.md|DISCLAIMER\.md)$", m.name):
                    tf.extract(m, root, filter="data")
    return root / "package", version


def si_data():
    root, ver = si_root()
    icons = json.loads((root / "data/simple-icons.json").read_text(encoding="utf-8"))
    return root, ver, {i["slug"]: i for i in icons}


def si_search(words):
    _, ver, icons = si_data()
    for w in words:
        lw = w.lower().replace(" ", "")
        hits = [i for s, i in icons.items() if lw in s or lw in i["title"].lower().replace(" ", "")
                or lw in json.dumps(i.get("aliases") or {}, ensure_ascii=False).lower()]
        say("%s（Simple Icons %s）：%s" % (w, ver, "；".join("%s = %s" % (i["slug"], i["title"]) for i in hits[:12]) or "没有"))


def add_si(key, slug, names, form):
    root, ver, icons = si_data()
    ic = icons.get(slug)
    if not ic:
        raise SystemExit("Simple Icons %s 里没有 %s（先用 si-search 查）" % (ver, slug))
    LIB.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "icons" / (slug + ".svg"), LIB / (key + ".svg"))
    lic = ic.get("license") or {}
    d = load()
    d["logos"][key] = {
        "names": names, "file": key + ".svg", "form": form,
        "source": "Simple Icons %s（npm 包 simple-icons，图标 %s）" % (ver, ic["title"]),
        "source_url": "https://simpleicons.org/?q=%s" % urllib.parse.quote(slug),
        "upstream": ic.get("source"), "guidelines": ic.get("guidelines"),
        "license": (lic.get("type") or "CC0-1.0") + "（Simple Icons 收录的图形数据）；商标权归品牌所有者，仅在新闻报道中指称该公司",
        "retrieved": today(),
    }
    save(d)
    say("已加入 %s ← Simple Icons/%s" % (key, slug))


# ---------------------------------------------------------------- Wikimedia Commons
def commons_info(title):
    q = {"action": "query", "titles": title, "prop": "imageinfo|templates", "iiprop": "url|size|mime|extmetadata", "tllimit": 200,
         "iiextmetadatafilter": "LicenseShortName|UsageTerms|Artist|Credit|ImageDescription", "format": "json", "formatversion": "2"}
    r = json.loads(http(COMMONS_API + "?" + urllib.parse.urlencode(q)))
    p = r["query"]["pages"][0]
    if p.get("missing"):
        raise SystemExit("Commons 上没有 %s" % title)
    ii = p["imageinfo"][0]
    md = {k: re.sub(r"<[^>]+>", "", v.get("value") or "").strip() for k, v in (ii.get("extmetadata") or {}).items()}
    tpl = sorted({t["title"].replace("Template:", "") for t in p.get("templates") or []
                  if re.match(r"Template:(PD-|Cc-|CC-|Trademark)", t["title"], re.I) and "/" not in t["title"]})
    return {"title": p["title"], "url": ii["url"].split("?")[0], "page": ii["descriptionurl"], "mime": ii["mime"], "size": [ii["width"], ii["height"]],
            "license": md.get("LicenseShortName", ""), "artist": md.get("Artist", ""), "credit": md.get("Credit", ""), "templates": tpl}


def add_commons(key, title, names, form):
    if not title.startswith("File:"):
        title = "File:" + title
    info = commons_info(title)
    if not OK_LICENSE.match(info["license"] or ""):
        raise SystemExit("%s 的许可是「%s」，不在可用范围（公有领域、CC0、CC BY、CC BY-SA）" % (title, info["license"]))
    if info["mime"] not in ("image/svg+xml", "image/png"):
        raise SystemExit("%s 是 %s，标志只收 SVG 或带透明底的 PNG" % (title, info["mime"]))
    data = http(info["url"])
    ext = ".svg" if info["mime"] == "image/svg+xml" else ".png"
    if ext == ".svg" and re.search(rb"<script|foreignObject|\son[a-z]+\s*=|href\s*=\s*[\"']https?:", data, re.I):
        raise SystemExit("%s 里有脚本或外部链接，不收" % title)
    if ext == ".png":
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        if im.mode not in ("RGBA", "LA") and "transparency" not in im.info:
            raise SystemExit("%s 没有透明底：单色化会变成一整块色块（标志不能改，只能换一个文件）" % title)
    LIB.mkdir(parents=True, exist_ok=True)
    for old in LIB.glob(key + ".*"):
        if old.suffix in (".svg", ".png"):
            old.unlink()
    (LIB / (key + ext)).write_bytes(data)
    tm = any(t.lower().startswith("trademark") for t in info["templates"])
    d = load()
    d["logos"][key] = {
        "names": names, "file": key + ext, "form": form,
        "source": "Wikimedia Commons：%s" % info["title"], "source_url": info["page"],
        "license": info["license"] + ("（%s）" % "、".join(t for t in info["templates"] if t.upper().startswith(("PD", "CC"))) if info["templates"] else "")
                   + ("；注册商标，商标权归所有者，仅在新闻报道中指称该公司" if tm else "；商标权归所有者，仅在新闻报道中指称该公司"),
        "author": info["artist"] or None, "credit": info["credit"] or None, "retrieved": today(),
    }
    save(d)
    say("已加入 %s ← %s（%s）" % (key, info["title"], info["license"]))


def add_file(key, path, names, form, source_url, license_):
    src = Path(path)
    if src.suffix.lower() not in (".svg", ".png"):
        raise SystemExit("只收 SVG 或带透明底的 PNG")
    data = src.read_bytes()
    if src.suffix.lower() == ".svg" and re.search(rb"<script|foreignObject|\son[a-z]+\s*=|href\s*=\s*[\"']https?:", data, re.I):
        raise SystemExit("文件里有脚本或外部链接，不收")
    LIB.mkdir(parents=True, exist_ok=True)
    (LIB / (key + src.suffix.lower())).write_bytes(data)
    d = load()
    d["logos"][key] = {"names": names, "file": key + src.suffix.lower(), "form": form, "source": "品牌官方资料包", "source_url": source_url,
                       "license": license_ + "；商标权归所有者，仅在新闻报道中指称该公司", "retrieved": today()}
    save(d)
    say("已加入 %s ← %s" % (key, src.name))


def add_text(key, names, why):
    d = load()
    d["logos"][key] = {"names": names, "file": None, "form": "text", "status": why or "没找到可用的标志，用文字小签", "retrieved": today()}
    save(d)
    say("已登记 %s：文字小签（%s）" % (key, d["logos"][key]["status"]))


# ---------------------------------------------------------------- 取景（裁四周空白）
MEASURE_JS = r"""
import fs from 'fs'; import { pathToFileURL } from 'url';
const [pw, inp, outp] = process.argv.slice(2);
const { chromium } = await import(pathToFileURL(pw).href);
const items = JSON.parse(fs.readFileSync(inp, 'utf8'));
const b = await chromium.launch({ channel: 'chrome', headless: true });
const p = await b.newPage();
await p.setContent('<div id="box" style="width:400px;height:400px"></div>');
const out = {};
for (const it of items) {
  out[it.key] = await p.evaluate((svg) => {
    const box = document.getElementById('box'); box.innerHTML = svg;
    const s = box.querySelector('svg'); if (!s) return null;
    s.removeAttribute('width'); s.removeAttribute('height'); s.style.width = '400px'; s.style.height = '400px';
    const bb = s.getBBox(); const vb = s.viewBox && s.viewBox.baseVal && s.viewBox.baseVal.width ? s.viewBox.baseVal : null;
    return { x: bb.x, y: bb.y, w: bb.width, h: bb.height, vb: vb ? [vb.x, vb.y, vb.width, vb.height] : null };
  }, it.svg);
}
fs.writeFileSync(outp, JSON.stringify(out));
await b.close();
"""


def measure(keys=None):
    d = load()
    todo = [(k, v) for k, v in d["logos"].items() if v.get("file") and (keys is None or k in keys)]
    svgs = []
    for k, v in todo:
        f = LIB / v["file"]
        if f.suffix == ".png":
            from PIL import Image
            im = Image.open(f).convert("RGBA")
            bb = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
            v["crop"] = [bb[0], bb[1], bb[2] - bb[0], bb[3] - bb[1]] if bb else [0, 0, im.size[0], im.size[1]]
            v["px"] = list(im.size)
        else:
            svgs.append({"key": k, "svg": f.read_text(encoding="utf-8", errors="replace")})
    if svgs:
        with tempfile.TemporaryDirectory() as td:
            js, inp, outp = Path(td) / "m.mjs", Path(td) / "in.json", Path(td) / "out.json"
            js.write_text(MEASURE_JS, encoding="utf-8")
            inp.write_text(json.dumps(svgs), encoding="utf-8")
            subprocess.run(["node", str(js), PW, str(inp), str(outp)], check=True)
            res = json.loads(outp.read_text(encoding="utf-8"))
        for k, v in todo:
            r = res.get(k)
            if r and r["w"] > 0 and r["h"] > 0:
                pad = max(r["w"], r["h"]) * 0.02          # 留一点边（getBBox 不算描边粗细）
                v["crop"] = [round(r["x"] - pad, 3), round(r["y"] - pad, 3), round(r["w"] + 2 * pad, 3), round(r["h"] + 2 * pad, 3)]
    save(d)
    for k, v in todo:
        say("%-12s 取景 %s" % (k, v.get("crop")))


# ---------------------------------------------------------------- 构建时用：嵌进视频数据
def framed_svg(text, crop):
    """把最外层 <svg> 的 viewBox 换成裁好的取景框、去掉固定宽高（只动外框，不碰图形）。"""
    m = re.search(r"<svg\b[^>]*>", text)
    if not m:
        return text
    tag = m.group(0)
    new = re.sub(r'\s(width|height|viewBox|x|y)\s*=\s*("[^"]*"|\'[^\']*\')', "", tag)
    if crop:
        new = new[:-1].rstrip("/") + ' viewBox="%s" preserveAspectRatio="xMidYMid meet">' % " ".join("%g" % c for c in crop)
    if 'xmlns="http://www.w3.org/2000/svg"' not in new:
        new = new[:-1] + ' xmlns="http://www.w3.org/2000/svg">'
    return text[:m.start()] + new + text[m.end():]


def embed(keys, lib=None):
    """当期用到的标志 → {键: {n: {zh,en}, m: data: 地址或 None（文字小签）, ar: 宽高比, f: 形式}}。"""
    d = lib or load()
    out = {}
    for k in keys:
        v = d["logos"].get(k)
        if not v:
            continue
        names = v.get("names") or {}
        item = {"n": {"zh": names.get("zh") or names.get("en") or k, "en": names.get("en") or names.get("zh") or k}, "m": None, "ar": 1.0, "f": v.get("form") or "symbol"}
        f = LIB / v["file"] if v.get("file") else None
        if f and f.exists():
            crop = v.get("crop")
            if f.suffix == ".svg":
                svg = framed_svg(f.read_text(encoding="utf-8", errors="replace"), crop)
                if not crop:
                    vb = re.search(r'viewBox\s*=\s*"([^"]+)"', svg)
                    crop = [float(x) for x in re.split(r"[\s,]+", vb.group(1).strip())] if vb else [0, 0, 1, 1]
                item["m"] = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode()
            else:                                  # PNG：包一层 SVG 取景（图片本身不动）
                pw_, ph_ = v.get("px") or [1, 1]
                crop = crop or [0, 0, pw_, ph_]
                svg = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="%g %g %g %g">'
                       '<image width="%d" height="%d" xlink:href="data:image/png;base64,%s"/></svg>'
                       % (crop[0], crop[1], crop[2], crop[3], pw_, ph_, base64.b64encode(f.read_bytes()).decode()))
                item["m"] = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode()
            item["ar"] = round(crop[2] / crop[3], 3) if crop and crop[3] else 1.0
        out[k] = item
    return out


# 帖子卡头像里标志怎么放（2026-11-06 加；和 site/v3/video3.js 的 AV、avatarFit 用同一组数，单位是画面宽的百分之一 --u）：
# 圆的直径 D；圆里能放的标志最宽 IN（再宽四角就出圆）、默认高 MH；放不进圆的（横长字标）改用胶囊，标志高 PH、最宽 PW。
# 11-06 OpenAI 字标（宽高比 3.367）塞进 3.2 的圆，宽约 5.7，左右各溢出一截压住名字；test_video3_storyboard.py 逐个标志核不溢出。
AVATAR = {"D": 3.2, "MH": 1.7, "IN": 2.5, "PH": 1.2, "PW": 7.0}


def avatar_fit(item):
    """embed() 出来的一项（要 ar、f、m）→ {"pill": 是否用胶囊, "h": 标志高, "w": 标志宽}；文字小签（没有图形）一律胶囊、w 为 None。"""
    A = AVATAR
    if not item.get("m"):
        return {"pill": True, "h": None, "w": None}
    ar = float(item.get("ar") or 1.0)
    if item.get("f") == "symbol" or ar <= A["IN"] / A["MH"] * 1.2:
        h = min(A["MH"], A["IN"] / ar)
        if h >= A["MH"] * 0.7:
            return {"pill": False, "h": h, "w": h * ar}
    h = min(A["PH"], A["PW"] / ar)
    return {"pill": True, "h": h, "w": h * ar}


def credits(keys, lib=None):
    """署名清单（写进 video3_media.json 的 credits.logos）。"""
    d = lib or load()
    out = []
    for k in keys:
        v = d["logos"].get(k)
        if not v:
            continue
        out.append({"key": k, "name": (v.get("names") or {}).get("zh") or k, "file": v.get("file"), "source": v.get("source") or v.get("status"),
                    "url": v.get("source_url"), "license": v.get("license"), "author": v.get("author"), "retrieved": v.get("retrieved")})
    return out


def norm(s):
    return re.sub(r"[\s\-‐·・_.]", "", str(s or "")).lower()


def names_of(v):
    n = v.get("names") or {}
    return [x for x in [n.get("zh"), n.get("en")] + list(n.get("aliases") or []) if x]


def mentioned(v, text):
    """标志对应的公司名（中文、英文、别名）有没有出现在这段字里。"""
    t = norm(text)
    return any(norm(x) and norm(x) in t for x in names_of(v))


# ---------------------------------------------------------------- 对照页（人眼核：原样／单色）
def preview(out_html):
    d = load()
    keys = sorted(d["logos"])
    em = embed(keys, d)
    rows = []
    for k in keys:
        v, e = d["logos"][k], em[k]
        orig = ('<img src="%s">' % e["m"]) if e["m"] else '<span class="t">（文字小签）</span>'
        mono = ('<i class="mk" style="-webkit-mask-image:url(%s);mask-image:url(%s);aspect-ratio:%s"></i>' % (e["m"], e["m"], e["ar"])) if e["m"] else ""
        chip = '<span class="chip">%s%s</span>' % (mono, ("<b>%s</b>" % e["n"]["zh"]) if (not e["m"] or e["f"] == "symbol") else "")
        rows.append('<tr><td><code>%s</code><br><small>%s · %s</small></td><td class="o">%s</td><td>%s</td><td class="acc">%s</td><td class="dk">%s</td><td><small>%s<br>%s</small></td></tr>'
                    % (k, e["n"]["zh"], e["f"], orig, chip, chip, chip, v.get("source") or v.get("status"), v.get("license") or ""))
    html = """<!doctype html><meta charset="utf-8"><title>标志库对照</title><style>
body{font:14px/1.4 -apple-system,sans-serif;background:#f3efe8;margin:20px}table{border-collapse:collapse}td{padding:8px 12px;border-bottom:1px solid #0001;vertical-align:middle}
td.o img{height:34px;max-width:220px;background:repeating-conic-gradient(#ddd 0 25%,#fff 0 50%) 0/12px 12px}
.chip{display:inline-flex;align-items:center;gap:6px;padding:7px 11px;border-radius:99px;background:rgba(255,255,255,.7);border:1px solid #0001;color:#3a2f22;font-weight:600}
.chip .mk{display:inline-block;height:20px;background:currentColor;-webkit-mask-size:contain;mask-size:contain;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;-webkit-mask-position:center;mask-position:center}
td.acc .chip{color:#b86400}td.dk{background:#0d0b09}td.dk .chip{background:rgba(52,46,40,.82);color:#f5efe6;border-color:#fff2}
</style><table><tr><th>键</th><th>原件</th><th>单色·字色</th><th>单色·主题色</th><th>深色</th><th>来源·许可</th></tr>{{ROWS}}</table>""".replace("{{ROWS}}", "".join(rows))
    Path(out_html).write_text(html, encoding="utf-8")
    say("写出 %s" % out_html)


# ---------------------------------------------------------------- 命令行
def main(argv=None):
    ap = argparse.ArgumentParser(description="视频 v3 品牌标志库（用法见文件开头）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    s = sub.add_parser("si-search"); s.add_argument("words", nargs="+")
    for name in ("add-si", "add-commons", "add-file", "add-text"):
        s = sub.add_parser(name)
        s.add_argument("key")
        if name != "add-text":
            s.add_argument("what", help="Simple Icons 的 slug / Commons 的 File: 标题 / 本机文件")
        s.add_argument("--zh", required=True); s.add_argument("--en", required=True)
        s.add_argument("--alias", action="append", default=[])
        s.add_argument("--form", choices=["wordmark", "symbol"], default="symbol")
        s.add_argument("--why", default=""); s.add_argument("--source-url", default=""); s.add_argument("--license", default="")
    s = sub.add_parser("measure"); s.add_argument("keys", nargs="*")
    s = sub.add_parser("preview"); s.add_argument("out")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for k, v in sorted(load()["logos"].items()):
            say("%-12s %-10s %-9s %s" % (k, (v.get("names") or {}).get("zh", ""), v.get("form", ""), v.get("source") or v.get("status")))
    elif a.cmd == "si-search":
        si_search(a.words)
    elif a.cmd in ("add-si", "add-commons", "add-file", "add-text"):
        names = {"zh": a.zh, "en": a.en, "aliases": a.alias}
        if a.cmd == "add-si":
            add_si(a.key, a.what, names, a.form)
        elif a.cmd == "add-commons":
            add_commons(a.key, a.what, names, a.form)
        elif a.cmd == "add-file":
            add_file(a.key, a.what, names, a.form, a.source_url, a.license)
        else:
            add_text(a.key, names, a.why)
        if a.cmd != "add-text":
            measure([a.key])
    elif a.cmd == "measure":
        measure(a.keys or None)
    elif a.cmd == "preview":
        preview(a.out)


if __name__ == "__main__":
    main()
