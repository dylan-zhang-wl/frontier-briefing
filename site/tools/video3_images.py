#!/usr/bin/env python3
"""视频 v3 的配图：分镜里的 image_requests 缺图时生成（先 agy 再 Codex）或从 Wikimedia Commons 取资料图；记来源、出署名。

由 site/tools/video3_build.py 调用（配音之前），也可以单独跑：
    PY=~/.venvs/frontier-daily/bin/python
    $PY site/tools/video3_images.py --day 2026-11-01          # 只补缺的图，已有的不动、不重画
    $PY site/tools/video3_images.py --day 2026-11-01 --redo v_store   # 重画某一张（旧图改名留底）

分镜里怎么写（写稿规则见 pipeline/prompts/写稿_视频v3.md）：
    "image_requests": [
      {"id": "v_store", "placement": "tile", "events": ["E034"],
       "context_en": "a payment robot started work in a convenience store",       # 新闻背景（可选，进提示词的括号里）
       "brief_en": "a bright convenience-store counter at night …"},             # 画面：真实场景、具体对象，光线按场景写
      {"id": "v_shop", "placement": "tile", "commons": "File:….jpg"}            # 资料图：只收 CC0 / 公有领域 / CC BY / CC BY-SA
    ]
生成的图放 06_配图/视频/<id>.png，每张一行记进 06_配图/视频/提示词记录.md，完整提示词、用量、每次尝试用的后端在 results.json，
agy 的记录在 log_<id>.agy.json，Codex 原始输出在 log_<id>.png.txt；
来源（生成还是资料图、哪个后端画的、资料图的作者和许可）记在 06_配图/视频/来源.json，构建时据此写署名（画面里不挂任何小标，署名只进文字稿面板的出处）。

生图后端（2026-11-03 起）：默认先 agy（Antigravity CLI，Google AI Pro 订阅，经 site/tools/agy_image.py），没成再 Codex（ChatGPT 订阅）；
两家都不另花钱。顺序只在 IMAGE_BACKENDS_DEFAULT 一处改，或临时用环境变量：FD_IMAGE_BACKENDS=codex 恢复旧做法（只用 Codex）。
agy 开画前查一次登录和额度；额度用完 / 没登录 / 没装（agy_image 退出码 3、4、7）就整轮不再试 agy；超时、没拿到图、其他错误（5、6、1）只这一张改走 Codex；
竖图（portrait 4:5）agy 画不了，直接 Codex。每张约 1 分钟，最多同时 4 张。后端都没成：版式和时间轴不变，那一块就不带图。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DIR = "06_配图/视频"
UA = "frontier-daily/1.0 (daily briefing video; image credits)"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
OK_LICENSE = re.compile(r"^(public domain|pd\b|cc0|cc by(-sa)? \d|cc-by(-sa)?-\d)", re.I)

# 当天主题色 → 提示词里的颜色说法（琥珀与 10-31 v3.1 用户认可的那段一字不差）
PALETTE = {
    "amber": ("honey amber", "#E2A13A"),
    "blue": ("ocean blue", "#4EA1FF"),
    "coral": ("warm coral", "#E85C44"),
    "violet": ("soft violet", "#7D4FE0"),
}
FORMATS = {"tile": "landscape 16:9 (wide)", "backdrop": "landscape 16:9 (wide)", "inset": "landscape 16:9 (wide)", "card": "landscape 16:9 (wide)",
           "square": "square 1:1", "portrait": "portrait 4:5"}

# 生图后端顺序（只改这一处）：先 agy（Google AI Pro 订阅）再 Codex（ChatGPT 订阅）。环境变量 FD_IMAGE_BACKENDS 可临时覆盖，
# 例如 FD_IMAGE_BACKENDS=codex 恢复 11-03 以前的做法；写错的名字忽略，全写错就只用 Codex。
IMAGE_BACKENDS_DEFAULT = "agy,codex"
TOOL_NAME = {"agy": "Antigravity CLI 内置画图（Nano Banana 2，Google AI Pro 订阅）", "codex": "Codex CLI 内置画图（ChatGPT 订阅）"}
AGY_ASPECT = {"landscape 16:9 (wide)": "16:9", "square 1:1": "1:1"}       # portrait 4:5 agy 画不了 → 只走 Codex
AGY_STOP = (3, 4, 7)                                                     # agy_image 退出码：额度用完、没登录、没装 → 这一轮不再试 agy
HEAD = ("Use your built-in image generation tool to create exactly ONE image, at the highest quality setting and the largest output resolution "
        "the tool allows. Save it in the current directory as {name} and reply with only the full saved path. Do nothing else: no other files, "
        "no edits, no extra variants.\n\nImage brief.\nFormat: {fmt}.\nSubject{ctx}: {brief}\n")
# 整个系列的画风（"数字前沿遇见真实世界"，10-31 v3.1 定稿；只换当天主题色）。agy 和 Codex 都用这一段（网页图的提示词也从 palette_style 现取）。
# 11-06 午：把 11-03 只给 agy 加的"科技感"挪进来、两家共用（STYLE_TECH），并改成科技感主要来自基础设施、实验设备、材料和数字光层，
# 不再把电脑、显示器、手机推成近景主角（11-04、11-06 agy 退回的图全是"像品牌产品"）；去掉 brushed metal；光层形态随题材变；
# 禁用清单末尾写明"清单优先于画面描述"（11-06 e006 的 brief 自己要了挂锁）。其余三段与 v3.1 一字不差。
# 11-08 晚（视频导演对比后用户定）：去掉"画面上加一层和新闻有关的（当天主题色）数字光"——B 导演看关键帧发现它就是配图比喻感、
# 电路纹的来源；光线不再默认黄昏暖调，跟着题材和场景走、白平衡按真实光源。写实、科技感（来自真实设备和材料）、禁用清单照旧。
STYLE_TECH = (
    "Realistic high-tech feel (unmistakably technological, never sci-fi): let the technology come from real infrastructure, lab and industrial "
    "equipment and materials, for example server racks and cable trays, fibre-optic bundles, silicon wafers and chip packages, test "
    "benches and instruments, rugged equipment enclosures, cleanroom or data-hall architecture. Favour industrial precision materials: powder-coated or "
    "bead-blasted metal, perforated steel panels, machined fittings, glass, ceramic, matte composites and neatly dressed cables. Consumer devices "
    "(computers, monitors, laptops, tablets, phones) are never the hero or the close-up; if the brief needs one, keep it secondary in the frame and make "
    "it a generic, unbranded, industrial-looking unit (a plain boxy housing with visible screws, vents or handles), not a sleek consumer design. Unless "
    "the brief asks for a wide view, frame the key technology as a medium shot rather than a distant panorama. The technological feel comes from the real "
    "equipment itself (its precision, cabling, status LEDs and materials), not from added graphics.\n")
STYLE = (
    "Visual language for the whole series (a daily AI and technology briefing): the digital frontier meeting the real world. A premium, photorealistic "
    "editorial image, like a feature opener in a high-end technology magazine: a real place or real objects, photographed with a realistic lens, "
    "as a documentary photographer would find them; every light in the frame comes from a real source in the scene (no added glow layer, light "
    "trails, holographic panels or graphic overlay).\n"
    "Palette: real-world tones stay natural and true to the place and its light (stone, sand, wood, concrete, steel, soft greys). Restrained and "
    "elegant: no neon, no oversaturation, no cold sci-fi blue glow.\n"
    "Lighting and camera: the light follows the subject and the scene, not a fixed time of day. Choose what a real photographer would actually find at "
    "that place for this story: clear daylight, overcast daylight, night with practical lights, cool white lab or cleanroom light, or neutral indoor "
    "artificial light are all fine; do not default to golden hour or warm dawn/dusk light, and follow the lighting the subject line asks for. Keep the "
    "white balance true to the real light source. Realistic contrast, realistic depth of field with the key element tack-sharp and the background "
    "falling into soft bokeh. Composition: one clear subject and one clear action, slightly off-centre, uncluttered, with breathing room; it must still "
    "read when shown small.\n"
    + STYLE_TECH +
    "Strictly avoid: any text, letters, numbers, digits, punctuation, currency symbols, logos, trademarks, brand marks or readable interface (every screen, "
    "label, tag, card and sign stays blank or abstract); recognisable real product designs (all devices generic and unbranded, no camera bumps or signature "
    "shapes); people, faces, hands or silhouettes; robots or humanoids, glowing brains, neural-network node webs, circuit-board patterns, binary code, data "
    "rain, padlocks and keys, hooded hackers, globes, sci-fi HUD clutter; cartoon, paper-craft or flat-vector styles; watermarks or borders. This list "
    "overrides the subject line: if the subject seems to call for one of these motifs, express the idea through the scene and the light instead.")


def say(*a):
    print(*a, flush=True)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")      # 写进长期文件的时间读系统时钟


def palette_style(accent):
    pname, phex = PALETTE.get(accent or "amber", PALETTE["amber"])
    return STYLE.replace("{pname}", pname).replace("{phex}", phex)


def prompt_for(r, accent):
    if r.get("context_en"):
        ctx = " (news: %s)" % r["context_en"].strip().rstrip(".")
    else:
        ctx = ""
    fmt = FORMATS.get(r.get("format") or r.get("placement") or "tile", FORMATS["tile"])
    return HEAD.format(name=r["id"] + ".png", fmt=fmt, ctx=ctx, brief=r["brief_en"].strip()) + palette_style(accent)


def load_meta(d):
    p = d / "来源.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_meta(d, meta):
    (d / "来源.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def existing(d, rid):
    return next((d / (rid + e) for e in (".png", ".jpg", ".jpeg", ".webp") if (d / (rid + e)).is_file()), None)


# ---------------------------------------------------------------- 生成（先 agy，再 Codex）
def image_backends():
    raw = os.environ.get("FD_IMAGE_BACKENDS", IMAGE_BACKENDS_DEFAULT)
    out = [b for b in (x.strip().lower() for x in raw.split(",")) if b in TOOL_NAME]
    return list(dict.fromkeys(out)) or ["codex"]


_AGY = {"checked": False, "path": None, "off": ""}      # 这一轮 agy 能不能用：开画前查一次；额度用完 / 没登录就整轮关掉
_AGY_LOCK = threading.Lock()


def _agy_mod():
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import agy_image
    return agy_image


def agy_ready():
    """返回 agy 命令路径；不能用（没装、没登录、额度用完）返回 None。查额度不花额度。"""
    with _AGY_LOCK:
        if not _AGY["checked"]:
            _AGY["checked"] = True
            AG = _agy_mod()
            p = AG.find_agy()
            if not p:
                _AGY["off"] = "本机没有 agy"
            else:
                code, msg, _ = AG.check(p)
                if code == 0:
                    _AGY["path"] = p
                else:
                    _AGY["off"] = msg
            if _AGY["off"]:
                say("  注意：这一轮不用 agy（%s），改用 Codex" % _AGY["off"])
        return _AGY["path"]


def agy_off(why):
    with _AGY_LOCK:
        if _AGY["path"]:
            _AGY["path"], _AGY["off"] = None, why
            say("  注意：agy 这一轮停用（%s），剩下的图改用 Codex" % why)


def gen_agy(d, r, accent, agy, aspect):
    """agy 画一张。提示词和 Codex 用同一段画面描述和画风（含两家共用的科技感 STYLE_TECH），只去掉开头那句写给 Codex 的“用内置工具、存成某文件”；
    agy_image 会再接上它自己的补充（agy_image.STYLES["warm"]：暖色白平衡、无品牌设备、禁用套路重申）。"""
    AG = _agy_mod()
    rid = r["id"]
    p = prompt_for(r, accent)
    brief = p[p.index("Image brief."):]
    t0 = time.time()
    try:
        code, msg, info = AG.generate(agy, brief, d / (rid + ".png"), aspect=aspect)
    except Exception as e:  # noqa: BLE001
        code, msg, info = 1, "agy_image 出错：%s" % e, {}
    (d / ("log_%s.agy.json" % rid)).write_text(json.dumps(dict(info, exit_code=code, note=msg), ensure_ascii=False, indent=1) + "\n",
                                               encoding="utf-8")
    sent = info.get("prompt_used") or (brief.strip() + AG.STYLES.get(info.get("style") or "warm", ""))
    return {"ok": code == 0 and (d / (rid + ".png")).is_file(), "backend": "agy", "code": code, "note": msg, "secs": round(time.time() - t0),
            "tokens": None, "finished": now(), "prompt": sent, "verbatim": info.get("prompt_verbatim"), "conversation_id": info.get("conversation_id")}


def gen_one(d, r, accent):
    """一张图：按 image_backends() 的顺序试（默认 agy → Codex），成了就停。返回最后那次的结果；之前没成的几次放在 "tried" 里。"""
    fmt = FORMATS.get(r.get("format") or r.get("placement") or "tile", FORMATS["tile"])
    tried = []
    for b in image_backends():
        if b == "agy":
            if fmt not in AGY_ASPECT:
                continue                                       # 竖图 agy 画不了
            agy = agy_ready()
            if not agy:
                continue
            res = gen_agy(d, r, accent, agy, AGY_ASPECT[fmt])
            if not res["ok"]:
                if res["code"] in AGY_STOP:
                    agy_off(res["note"])
                say("  %s：agy 没成（%s）" % (r["id"], res["note"]))
        else:
            res = gen_codex(d, r, accent)
        if res["ok"]:
            res["tried"] = tried
            return res
        tried.append(res)
    if tried:
        last = tried.pop()
        last["tried"] = tried
        return last
    return {"ok": False, "backend": None, "code": -1, "note": "没有可用的生图后端", "secs": 0, "tokens": None, "finished": now(),
            "prompt": prompt_for(r, accent), "tried": []}


def gen_codex(d, r, accent):
    rid = r["id"]
    prompt = prompt_for(r, accent)
    # 干净环境（不带本项目的任何密钥变量）；CODEX_HOME：云端把 Codex 的登录放在别处（$RUNNER_TEMP/codex），没设时和原来一样
    env = {k: os.environ[k] for k in ("HOME", "PATH", "USER", "LANG", "CODEX_HOME") if k in os.environ}
    t0 = time.time()
    try:
        p = subprocess.run(["codex", "exec", "--skip-git-repo-check", "-s", "workspace-write", "-C", str(d), prompt],
                           env=env, capture_output=True, text=True, timeout=720, stdin=subprocess.DEVNULL)
        code, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        code, out, err = -9, e.stdout or "", "超时（12 分钟）"
    except FileNotFoundError:
        code, out, err = -1, "", "本机没有 codex 命令"
    secs = round(time.time() - t0)
    (d / ("log_%s.png.txt" % rid)).write_text("===== %s =====\n%s\n\n--- stdout ---\n%s\n\n--- stderr ---\n%s\n" % (now(), d / (rid + ".png"), out, err),
                                               encoding="utf-8")
    m = re.search(r"tokens used\s*\n\s*([\d,]+)", (err or "") + "\n" + (out or ""))
    ok = False
    f = d / (rid + ".png")
    if code == 0 and f.exists():
        try:
            from PIL import Image
            with Image.open(f) as im:
                im.verify()
            ok = True
        except Exception:  # noqa: BLE001
            ok = False
    return {"ok": ok, "backend": "codex", "code": code, "secs": secs, "tokens": m.group(1) if m else None, "finished": now(), "prompt": prompt}


# ---------------------------------------------------------------- 资料图（Wikimedia Commons）
def _ssl():
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem") if Path("/etc/ssl/cert.pem").exists() else ssl.create_default_context()


def http(url, timeout=90):
    import urllib.request
    for k in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=timeout, context=_ssl()).read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(6 * (k + 1))
                continue
            raise
    raise RuntimeError("一直被限流：%s" % url)


def commons_one(d, r):
    title = r["commons"] if r["commons"].startswith("File:") else "File:" + r["commons"]
    q = {"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url|mime|extmetadata", "iiurlwidth": 2000,
         "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|Credit|ImageDescription", "format": "json", "formatversion": "2"}
    pg = json.loads(http(COMMONS_API + "?" + urllib.parse.urlencode(q)))["query"]["pages"][0]
    if pg.get("missing"):
        raise RuntimeError("Commons 上没有 %s" % title)
    ii = pg["imageinfo"][0]
    md = {k: re.sub(r"<[^>]+>", "", v.get("value") or "").strip() for k, v in (ii.get("extmetadata") or {}).items()}
    lic = md.get("LicenseShortName", "")
    if not OK_LICENSE.match(lic):
        raise RuntimeError("%s 的许可是「%s」，不在可用范围（CC0、公有领域、CC BY、CC BY-SA）" % (title, lic))
    if ii.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
        raise RuntimeError("%s 不是照片（%s）" % (title, ii.get("mime")))
    data = http(ii.get("thumburl") or ii["url"])
    ext = ".png" if ii["mime"] == "image/png" else ".jpg"
    (d / (r["id"] + ext)).write_bytes(data)
    return {"kind": "commons", "title": pg["title"], "page": ii["descriptionurl"], "license": lic, "license_url": md.get("LicenseUrl") or None,
            "author": md.get("Artist") or None, "credit": md.get("Credit") or None, "retrieved": now()[:10]}


# ---------------------------------------------------------------- 入口
def ensure(issue, reqs, accent, gen=True, redo=()):
    """缺的图补上；返回 {id: 来源}。不会因为某张图失败而停：失败的那块不带图（构建时自动去掉）。"""
    d = issue / DIR
    if not reqs:
        return load_meta(d) if d.exists() else {}
    d.mkdir(parents=True, exist_ok=True)
    meta = load_meta(d)
    for rid in redo:
        f = existing(d, rid)
        if f:
            f.rename(f.with_name("%s.旧%s%s" % (f.stem, datetime.now().strftime("%m%d%H%M"), f.suffix)))
    todo_gen = [r for r in reqs if r.get("brief_en") and not r.get("commons") and not existing(d, r["id"])]
    todo_com = [r for r in reqs if r.get("commons") and not existing(d, r["id"])]
    for r in reqs:                       # 已有的图：补记来源（生成的默认记为 AI 生成）
        if existing(d, r["id"]) and r["id"] not in meta:
            meta[r["id"]] = {"kind": "commons" if r.get("commons") else "generated", "note": "构建前就已在文件夹里"}
    for r in todo_com:
        try:
            meta[r["id"]] = commons_one(d, r)
            say("  资料图 %s ← %s（%s）" % (r["id"], meta[r["id"]]["title"], meta[r["id"]]["license"]))
        except Exception as e:  # noqa: BLE001
            say("  注意：资料图 %s 没取到（%s），这一块不带图" % (r["id"], e))
    if todo_gen and not gen:
        say("  注意：有 %d 张配图还没生成（--no-gen），这些位置不带图" % len(todo_gen))
        todo_gen = []
    if todo_gen:
        order = image_backends()
        say("  生成配图 %d 张（顺序 %s，都是订阅、不另花钱；同时最多 4 张）…" % (len(todo_gen), " → ".join(order)))
        if "agy" in order:
            agy_ready()                                        # 先查一次登录和额度（不花额度），不能用就整轮直接 Codex
        res_p = d / "results.json"
        results = json.loads(res_p.read_text(encoding="utf-8")) if res_p.exists() else {}
        with ThreadPoolExecutor(max_workers=4) as ex:
            outs = list(ex.map(lambda r: (r, gen_one(d, r, accent)), todo_gen))
        log = d / "提示词记录.md"
        if not log.exists():
            log.write_text("# %s 视频配图 · 提示词记录\n\n每张一行：时间、文件、放在哪、画面（英文提示词的 Subject 一段）、哪个后端画的、用时。完整提示词和每次尝试在 results.json，"
                           "agy 的记录在 log_<id>.agy.json，Codex 原始输出在 log_<id>.png.txt。画风沿用 v3.1“数字前沿遇见真实世界”，配色随当天主题色；"
                           "没有文字、商标、真人。\n\n" % issue.name, encoding="utf-8")

        def how(res):
            if not res["ok"]:
                return "**失败**（%s，%d 秒），这一块不带图" % ("；".join("%s 退出码 %s" % (t.get("backend"), t.get("code")) for t in res["tried"] + [res]), res["secs"])
            s = ("agy，%d 秒" % res["secs"]) if res["backend"] == "agy" else ("Codex，用量 %s token，%d 秒" % (res["tokens"], res["secs"]))
            if res["tried"]:
                s += "（先试 %s 没成：%s）" % ("、".join(t.get("backend") or "?" for t in res["tried"]),
                                         "；".join(str(t.get("note") or "退出码 %s" % t.get("code")) for t in res["tried"]))
            return s

        with log.open("a", encoding="utf-8") as fh:
            for r, res in outs:
                tried = res.pop("tried", [])
                res["tried"] = tried                           # 写记录时还要用
                results.setdefault(r["id"], {"attempts": []})["attempts"].extend(tried + [{k: v for k, v in res.items() if k != "tried"}])
                if res["ok"]:
                    meta[r["id"]] = {"kind": "generated", "backend": res["backend"], "tool": TOOL_NAME[res["backend"]], "created": res["finished"],
                                     "events": r.get("events") or []}
                fh.write("- %s `%s.png`（%s%s）：%s %s\n" % (res["finished"], r["id"], r.get("placement"),
                                                             "，" + "、".join(r.get("events") or []) if r.get("events") else "",
                                                             r["brief_en"].strip(), how(res)))
                say("  %s %s（%s，%d 秒）" % ("✓" if res["ok"] else "✗", r["id"], res.get("backend") or "无后端", res["secs"]))
        res_p.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    save_meta(d, meta)
    return meta


def grade(im, accent):
    """资料图轻轻往当天的色调靠（暖一点、对比柔一点），不改内容。"""
    from PIL import Image, ImageEnhance
    rgb = {"amber": (232, 160, 70), "blue": (90, 150, 230), "coral": (232, 120, 100), "violet": (150, 120, 230)}.get(accent or "amber", (232, 160, 70))
    im = ImageEnhance.Color(im).enhance(0.88)
    im = ImageEnhance.Contrast(im).enhance(0.94)
    return Image.blend(im, Image.new("RGB", im.size, rgb), 0.07)


def credit_lines(used, meta):
    """署名一行（中英）：视频配图由 AI 生成（资料图除外：作者、许可、出处）。used：这一期画面里真用到的图 id/文件名。"""
    com = []
    for k in used:
        m = meta.get(k) or {}
        if m.get("kind") == "commons":
            com.append(m)
    if not used:
        return None
    if not com:
        return {"zh": "视频配图由 AI 生成。", "en": "Images in the video are AI-generated."}
    zh = "；".join("%s，%s，%s，Wikimedia Commons" % (m["title"].replace("File:", ""), m.get("author") or "作者不详", m["license"]) for m in com)
    en = "; ".join("%s by %s, %s, via Wikimedia Commons" % (m["title"].replace("File:", ""), m.get("author") or "unknown", m["license"]) for m in com)
    if len(com) == len(used):
        return {"zh": "视频配图为资料图：%s。" % zh, "en": "Images in the video are file photos: %s." % en}
    return {"zh": "视频配图由 AI 生成（资料图除外：%s）。" % zh, "en": "Images in the video are AI-generated (except file photos: %s)." % en}


def main(argv=None):
    sys.path.insert(0, str(HERE))
    import video3_storyboard as SB
    ap = argparse.ArgumentParser(description="视频 v3 配图（用法见文件开头）")
    ap.add_argument("issue", nargs="?")
    ap.add_argument("--day")
    ap.add_argument("--redo", action="append", default=[], help="重画这一张（旧图改名留底）")
    a = ap.parse_args(argv)
    raw = a.issue or ("测试版/" + a.day)
    issue = (ROOT / raw).resolve()
    sb = SB.load(issue / "04_文稿/视频v3_分镜.json")
    meta = ensure(issue, SB.image_requests(sb), sb.get("accent"), redo=a.redo)
    for k, v in meta.items():
        say("%-12s %s" % (k, v.get("kind")))


if __name__ == "__main__":
    main()
