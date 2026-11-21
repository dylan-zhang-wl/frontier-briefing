#!/usr/bin/env python3
"""耳听点选页的条目（2026-11-21 加）：把审片结论里的“请你耳听”做成站长点选页 /frontier/_listen 要读的数据。

两头都挂在环境变量 FD_LISTEN_PAGE=on 后面（on／1／true／yes，不分大小写），没设时什么都不做：
    · archive.py push：把这一期 审片结论.json 里原样的“请你耳听”（只留 位置、说明、判断、依据、关乎事实 五栏）
      存进往期存档的 listen/<日期>.json（site-archive 分支，私有仓库），以后每次发布从存档取回来。
    · assemble.py：上线包里每一期都现算一遍条目，写 frontier/_listen/<日期>.json 和 frontier/_listen/index.json。
      这一期从 --issue 那个期目录的 审片结论.json 取；往期从存档的 listen/<日期>.json 取（存档里没有的期就没有点选页）。
      存的是原始条目、每次现算，所以以后改了时刻的认法，往期也跟着用新认法；条目编号只看日期、位置、说明，不受影响。
_listen/ 下的文件 Worker 对谁都不直接给（src/index.js），只在站长打开 /frontier/_listen 时由 Worker 自己读出来、做成页面。

每条算出来的东西：
    · id：条目编号，sha256(日期 + 位置 + 说明) 的前 10 位十六进制；同一期里撞了号（同样的位置和说明写了两遍）加 -2、-3。
    · clips：能直接放的几段，每段 {src: 播客|视频, a: 起秒, b: 止秒, label: 给人看的时刻}。
      一条可能有几段（“播客 11:29（另 11:55、12:00）”“视频 47 秒；播客 7:07”），投票仍按一条算。
      播客用网页上那份 issues/<日期>/audio/podcast.mp3（审片的播客时刻按它算）；视频用网页上的视频旁白 issues/<日期>/audio/video3.mp3：
      审片的视频时刻按 11_视频v3/预览.mp4 算，预览.mp4 的声音就是这个文件从第 0 秒合进去的（site/tools/video3_record.mjs），
      网页上那份是同一个文件拷过去的（site/tools/build_v3.py 7c 节），11-04、11-06 两期实测偏移 0 秒。
    · 起止：一个时刻放“前 PRE 秒到后 POST 秒”；一段区间放“起点前 PRE 秒到终点后 POST 秒”；写着“一带、前后、左右”的放宽到
      前 WIDE_PRE 后 WIDE_POST；写着“起”的放到后 FROM_POST 秒；“3:5x”这种个位不定的当 3:50–3:59。起点不小于 0；
      终点不知道音频多长，超过结尾浏览器自己会停。
    · group：front（多半真念错、拿不准、没写判断）／mid（多半转写听错，但只是一两个时刻）／batch（多半转写听错的成批条目：
      区间长到 BATCH_SPAN 秒以上、时刻有 BATCH_POINTS 个以上、写着“多处、起、等”、或者认不出时刻；页面上折起来放最后，写“可不听”）。
      排序：组 → 关乎事实的在前 → 多半真念错、没写判断、拿不准、多半转写听错 → 先视频后播客 → 时刻先后 → 原来的顺序。
    · 认不出时刻的（“其余”“播客多处”“播客、视频多处同音字”）照样列出来，clips 为空，页面上只显示文字、提示去播客或视频里听。
不调用模型、不联网、不读音频文件；同样的输入两次做出来逐字节一样（不写生成时间）。
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- 可以改的
PRE, POST = 2.0, 4.0              # 一个时刻：前 2 秒到后 4 秒（主会话定）
WIDE_PRE, WIDE_POST = 4.0, 8.0    # 写着“一带、前后、左右”的
FROM_POST = 20.0                  # 写着“起”的：从这里往后放 20 秒
BATCH_SPAN = 10.0                 # 多半转写听错里，区间长到这么多秒以上算成批
BATCH_POINTS = 4                  # 多半转写听错里，时刻有这么多个以上算成批

# ---------------------------------------------------------------- 固定的
PREFIX = "frontier"
OUT_DIR = "_listen"               # 上线包里的目录：frontier/_listen/（Worker 挡住，谁都不能直接下载）
ARCHIVE_DIR = "listen"            # 往期存档里的目录：listen/<日期>.json（原始条目）
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FIELDS = ("位置", "说明", "判断", "依据", "关乎事实")
AUDIO = {"播客": "audio/podcast.mp3", "视频": "audio/video3.mp3"}
JUDGE_RANK = {"多半真念错": 0, "": 1, "拿不准": 2, "多半转写听错": 3}
MED_RE = re.compile(r"播客|视频")
DASH = r"\s*[–—\-~～至到]\s*"
MMSS = r"(\d{1,2}):([0-5])([0-9xX])"
NUM = r"(\d{1,4}(?:\.\d+)?)"
MOD = r"\s*(一带|前后|左右|起)?"
POD_TOKEN = re.compile(MMSS + r"(?:" + DASH + MMSS + r")?" + MOD)
VID_TOKEN = re.compile(NUM + r"(?:\s*秒)?(?:" + DASH + NUM + r")?(?:\s*秒)?" + MOD)
VID_STRICT = re.compile(NUM + r"(?:" + DASH + NUM + r")?\s*秒" + MOD)
MANY_RE = re.compile(r"多处|等")
SEPS = "；;、，,"
OPEN, CLOSE = "（(", "）)"


def wanted():
    """开关：环境变量 FD_LISTEN_PAGE 是 on／1／true／yes（不分大小写）。"""
    return os.environ.get("FD_LISTEN_PAGE", "").strip().lower() in ("on", "1", "true", "yes")


# ---------------------------------------------------------------- 认时刻
def _split_top(s):
    """按 ；、， 分段，括号里的不分。返回 [(括号外的字, [括号里的字…])]。"""
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch in OPEN:
            depth += 1
        elif ch in CLOSE:
            depth = max(0, depth - 1)
        if ch in SEPS and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    out = []
    for p in parts:
        main, inner, depth, buf = [], [], 0, []
        for ch in p:
            if ch in OPEN:
                if depth == 0:
                    buf = []
                else:
                    buf.append(ch)
                depth += 1
            elif ch in CLOSE and depth > 0:
                depth -= 1
                if depth == 0:
                    inner.append("".join(buf))
                else:
                    buf.append(ch)
            elif depth > 0:
                buf.append(ch)
            else:
                main.append(ch)
        if depth > 0:                                    # 括号没合上：当括号外的字
            main.append("".join(buf))
        out.append(("".join(main), inner))
    return out


def _mmss(m, s, x):
    """3:5x → (230, 239)；3:58 → (238, 238)。"""
    base = int(m) * 60 + int(s) * 10
    if x in "xX":
        return float(base), float(base + 9)
    return float(base + int(x)), float(base + int(x))


def _clip(src, a, b, mod, fuzzy):
    """一处 → 一段 {src, a, b, kind}。a、b 是审片写的起止（同一时刻时 a == b）。"""
    if mod == "起":
        lo, hi = a - PRE, max(a, b) + FROM_POST
        kind = "起"
    elif mod in ("一带", "前后", "左右"):
        lo, hi = a - WIDE_PRE, b + WIDE_POST
        kind = "约"
    else:
        lo, hi = a - PRE, b + POST
        kind = "段" if (b > a or fuzzy) else "点"
    return {"src": src, "a": round(max(0.0, lo), 1), "b": round(max(hi, 0.0), 1), "kind": kind, "at": [a, b]}


def _pod_clips(text):
    out = []
    for m in POD_TOKEN.finditer(text):
        a, a2 = _mmss(m.group(1), m.group(2), m.group(3))
        fuzzy = m.group(3) in "xX"
        if m.group(4):
            b1, b = _mmss(m.group(4), m.group(5), m.group(6))
            fuzzy = fuzzy or m.group(6) in "xX"
        else:
            b = a2
        if b < a:
            a, b = b, a
        out.append(_clip("播客", a, b, m.group(7), fuzzy))
    return out


def _vid_clips(text, strict):
    out = []
    for m in (VID_STRICT if strict else VID_TOKEN).finditer(text):
        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else a
        if b < a:
            a, b = b, a
        out.append(_clip("视频", a, b, m.group(3), False))
    return out


def parse_position(pos):
    """位置 → (clips, many)。clips 见文件头；many：写着“多处、等、起”这类“不止这几处”的字。认不出时刻返回 ([], many)。
    · 每段先看有没有“播客”“视频”，有就换成它，没有接着用前一段的（“…；10:11（Shirley 第 34 轮）”还是播客）；
    · 播客只认 m:ss（含 3:5x），视频认数字（跟着“秒”，或整个位置里写了“秒”）；
    · 括号里的字只认严格的写法：播客 m:ss、视频“N 秒”，所以“（另 11:55、12:00）”算，“（共 6 处）”“（第 41 轮）”不算；
    · 还没出现“播客”“视频”就见到时刻的：m:ss 当播客，“N 秒”当视频。"""
    s = str(pos or "").replace("　", " ").replace("：", ":")
    has_sec = "秒" in s
    med, clips = None, []
    for main, inner in _split_top(s):
        found = MED_RE.findall(main)
        if found:
            # 一段里先后写了两种（少见），按出现的位置切开各算各的
            pieces, last, cur = [], 0, med
            for m in MED_RE.finditer(main):
                if m.start() > last:
                    pieces.append((cur, main[last:m.start()]))
                cur, last = m.group(0), m.end()
            pieces.append((cur, main[last:]))
            med = cur
        else:
            pieces = [(med, main)]
        for pm, txt in pieces:
            if pm == "播客":
                clips += _pod_clips(txt)
            elif pm == "视频":
                clips += _vid_clips(txt, strict=not has_sec)
            else:
                got = _pod_clips(txt)
                clips += got if got else _vid_clips(txt, strict=True)
        for t in inner:
            if med == "播客":
                clips += _pod_clips(t)
            elif med == "视频":
                clips += _vid_clips(t, strict=True)
            else:
                clips += _pod_clips(t) or _vid_clips(t, strict=True)
    many = bool(MANY_RE.search(s)) or any(c["kind"] == "起" for c in clips)
    return clips, many


def fmt_time(src, t):
    t = max(0.0, float(t))
    if src == "播客":
        n = int(round(t))
        return "%d:%02d" % (n // 60, n % 60)
    return ("%d" % round(t)) if abs(t - round(t)) < 0.05 else ("%.1f" % t)


def clip_label(c):
    """给人看的“播客 3:38”“视频 51–53 秒”（审片写的那一处，不是放的起止）。"""
    a, b = c["at"]
    if c["src"] == "播客":
        t = fmt_time("播客", a) + ("–" + fmt_time("播客", b) if b > a else "")
        return "播客 " + t + {"起": " 起", "约": " 前后"}.get(c["kind"], "")
    t = fmt_time("视频", a) + ("–" + fmt_time("视频", b) if b > a else "")
    return "视频 " + t + " 秒" + {"起": " 起", "约": " 前后"}.get(c["kind"], "")


# ---------------------------------------------------------------- 说明拆成“原稿那句”“转写成什么”
def split_note(note):
    """'原稿“X”，转写成“Y”' → (X, Y)；'原稿“X”，转写成：Y' → (X, Y)；'原稿“X”，程序那次…' → (X, 程序那次…)。
    不是“原稿…”开头的返回 ('', '')，页面上整句当“说明”显示。"""
    s = str(note or "").strip()
    if not s.startswith("原稿“"):
        return "", ""
    body = s[len("原稿“"):]
    m = re.search(r"”\s*[，,；;]", body)
    if not m:
        return "", ""
    say, rest = body[:m.start()], body[m.end():].strip()
    rest = re.sub(r"^(?:两次)?转写(?:都)?(?:成|是)\s*[:：]?\s*", "", rest)
    if rest.startswith("“") and rest.endswith("”") and rest.count("“") == 1:
        rest = rest[1:-1]
    return say.strip(), rest.strip()


# ---------------------------------------------------------------- 一期的条目
def raw_items(listen):
    """审片结论.json 的“请你耳听”（或存档 listen/<日期>.json 的同名一栏）→ 只留五栏的列表；不是字典的条目当说明。"""
    out = []
    for x in listen or []:
        if isinstance(x, dict):
            out.append({k: x[k] for k in FIELDS if k in x})
        elif isinstance(x, str) and x.strip():
            out.append({"位置": "", "说明": x.strip()})
    return out


def item_id(day, pos, note):
    return hashlib.sha256(("%s\n%s\n%s" % (day, pos, note)).encode("utf-8")).hexdigest()[:10]


def _group(judge, clips, many):
    if judge != "多半转写听错":
        return "front"
    if not clips or many:
        return "batch"
    if len(clips) >= BATCH_POINTS or any(c["at"][1] - c["at"][0] >= BATCH_SPAN for c in clips):
        return "batch"
    return "mid"


GROUP_RANK = {"front": 0, "mid": 1, "batch": 2}


def build_issue(day, raw, audio=("播客", "视频"), edition=""):
    """一期 → 点选页的数据（字典）。audio：这一期网页上有哪几个音频（没有的那种，段落标成放不了）。"""
    items, seen = [], {}
    for i, x in enumerate(raw_items(raw)):
        pos, note = str(x.get("位置") or "").strip(), str(x.get("说明") or "").strip()
        judge = str(x.get("判断") or "").strip()
        fact = x.get("关乎事实")
        fact = fact if isinstance(fact, bool) else None
        clips, many = parse_position(pos)
        iid = item_id(day, pos, note)
        seen[iid] = seen.get(iid, 0) + 1
        if seen[iid] > 1:
            iid = "%s-%d" % (iid, seen[iid])
        say, heard = split_note(note)
        cl = [{"src": c["src"], "a": c["a"], "b": c["b"], "label": clip_label(c), "ok": c["src"] in audio} for c in clips]
        items.append({"id": iid, "pos": pos, "note": note, "say": say, "heard": heard, "judge": judge, "basis": str(x.get("依据") or "").strip(),
                      "fact": fact, "group": _group(judge, clips, many), "clips": cl, "parsed": bool(clips), "_i": i,
                      "_med": 0 if (clips and clips[0]["src"] == "视频") else 1, "_t": clips[0]["at"][0] if clips else 1e9})
    items.sort(key=lambda it: (GROUP_RANK[it["group"]], 0 if it["fact"] else 1, JUDGE_RANK.get(it["judge"], 1), it["_med"], it["_t"], it["_i"]))
    for n, it in enumerate(items, 1):
        it["n"] = n
        for k in ("_i", "_med", "_t"):
            del it[k]
    return {"v": 1, "date": day, "edition": edition, "audio": {k: (k in audio) for k in AUDIO},
            "count": len(items), "groups": {g: sum(1 for it in items if it["group"] == g) for g in GROUP_RANK}, "items": items}


# ---------------------------------------------------------------- 往期存档里的原始条目
def archive_record(issue_dir):
    """期目录 → 要存进往期存档 listen/<日期>.json 的字典；没有审片结论或没有“请你耳听”返回 None。"""
    p = Path(issue_dir)
    try:
        j = json.loads((p / "审片结论.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    raw = raw_items(j.get("请你耳听") if isinstance(j, dict) else None)
    if not raw:
        return None
    return {"v": 1, "日期": p.name, "版别": str(j.get("版别") or ""), "请你耳听": raw}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def issue_root(p, day):
    """--issue 给的路径（期目录、10_网页v3、issues/<日期>）→ 放 审片结论.json 的期目录（名字是日期的那一层）；找不到返回 None。"""
    p = Path(p).resolve()
    for c in [p] + list(p.parents)[:4]:
        if c.name == day and (c / "审片结论.json").is_file():
            return c
    return None


def source_of(day, issue_dirs, archive):
    """这一天的原始条目从哪来：--issue 给的期目录里的 审片结论.json 优先，其次存档的 listen/<日期>.json。返回 (记录, 从哪来) 或 (None, '')。"""
    for d in issue_dirs.get(day, []):
        rec = archive_record(d)
        if rec:
            return rec, "这一期的审片结论"
    if archive:
        f = Path(archive) / ARCHIVE_DIR / ("%s.json" % day)
        if f.is_file():
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(rec, dict) and raw_items(rec.get("请你耳听")):
                    return rec, "往期存档"
            except ValueError:
                pass
    return None, ""


def build(out, issue_dirs, archive):
    """在上线包 out 里做 frontier/_listen/。issue_dirs：日期 → [期目录…]（--issue 给的）；archive：往期存档目录或 None。
    先做在临时目录，做完才整个挪进上线包。返回 {"line": 一行说明, "notes": [跳过的期…]}；出错往外抛（assemble.py 接住）。"""
    out = Path(out)
    root = out / PREFIX
    days = sorted((d.name for d in (root / "issues").iterdir() if DATE_RE.match(d.name)), reverse=True) if (root / "issues").is_dir() else []
    tmp = Path(tempfile.mkdtemp(prefix="fd-listen-"))
    try:
        stage = tmp / OUT_DIR
        stage.mkdir()
        index, notes, unparsed, total = [], [], 0, 0
        for day in days:
            rec, frm = source_of(day, issue_dirs, archive)
            if not rec:
                continue
            audio = tuple(k for k, rel in AUDIO.items() if (root / "issues" / day / rel).is_file())
            data = build_issue(day, rec.get("请你耳听"), audio=audio, edition=str(rec.get("版别") or ""))
            (stage / ("%s.json" % day)).write_text(dumps(data), encoding="utf-8")
            bad = sum(1 for it in data["items"] if not it["parsed"])
            unparsed += bad
            total += data["count"]
            index.append({"date": day, "edition": data["edition"], "count": data["count"], "groups": data["groups"]})
        (stage / "index.json").write_text(dumps({"v": 1, "issues": index}), encoding="utf-8")
        dest = root / OUT_DIR
        if dest.exists():
            raise RuntimeError("上线包里已经有 %s/%s" % (PREFIX, OUT_DIR))
        shutil.move(str(stage), str(dest))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if not index:
        return {"line": "耳听点选页：这次没有哪一期有“请你耳听”的原始条目（往期存档里还没存过，这一期也没有审片结论），页面上列表是空的。", "notes": notes}
    return {"line": "耳听点选页：%d 期、%d 条（%s 到 %s），其中 %d 条认不出时刻、只显示文字。" % (
        len(index), total, index[-1]["date"], index[0]["date"], unparsed), "notes": notes}
