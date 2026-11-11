#!/usr/bin/env python3
"""读音表核对：口播稿里的人名、公司、产品、媒体是不是按《读音表》写的。

用法（在项目根运行）：
    PY=~/.venvs/frontier-daily/bin/python
    $PY pipeline/lexicon_check.py 稿.md                 # 只检查，列出问题
    $PY pipeline/lexicon_check.py 稿.md --fix           # 能自动改的改掉（原地改写稿子），再查一遍
    $PY pipeline/lexicon_check.py 稿.md --fix --out 新稿.md   # 改好的另存，不动原稿
    $PY pipeline/lexicon_check.py 稿.md --json          # 结果写成 JSON，给别的程序用
    #   --lexicon 换一份读音表（默认 pipeline/prompts/读音表.yaml）；--strict 时"表里还没有"也算问题

查五件事：
  1. 音译：读音表里列出的中文音译（如"奥尔特曼"）应写英文原名。--fix 自动换：
     带"·"的全名换成全名（萨姆·奥尔特曼 → Sam Altman），单独的姓换成姓（奥尔特曼 → Altman）。
  2. 写错语种：有通行中文名的公司、媒体写成了英文（Nvidia → 英伟达，Bloomberg → 彭博社）——
     引入术语的句式"中文名，英文叫 X""中文名，英文是 X"（写稿提示词规定的写法）不算错（2026-11-01 晚放行）；
     华人名字写成了英文（Lip-Bu Tan → 陈立武）。标了"只提醒"的只提醒、不自动改
     （比如 Intel 在"Intel 3"里是制程名，Apple 在"Apple 智能"里是官方产品名）。
  3. 人名第一次要说全名并带身份，之后只说姓：第一次就只说姓、后面又说全名，都会提醒。
     --fix 把第一次改成全名、后面的全名改成姓；身份要人来补（只提醒，不自动加）。
  4. 表里还没有的英文名：正文里出现、读音表里没有的英文词，列出来，定好写法补进表里。
  5. 中文里带"·"的名字（如"某某·某某"）多半是西方人名的音译，表里没有的也列出来。
只查正文：## 章节标题、<!-- 注释 -->（比如稿末的语气表）、以 > 开头的备注行不查。
周日对谈稿（行首是"甲：""乙："）：行首的说话人标记不查；另查格式——正文每一行都要以"甲：""乙："开头，
稿末要有 <!-- 语气 {"章名": {"甲": …, "乙": …}} -->。2026-11-01 晚（第十轮）放宽：语气表里每一格写这个人情绪色板里的一个词
（pipeline/voice_profile.json"情绪色板"，甲＝Shirley、乙＝Dylan，只认"可用"的词），也可以写 "fixed" 或不写这一章、不写这个人，
配音时用默认词；写了色板以外的词（比如整句英文）只"提醒"，配音时换成默认词并记进 qc.json。
退出码：0 = 没有要改的；1 = 还有要改的（音译、写错语种、人名首次没说全名；还有下面第 6、7 项的要改）。
"表里还没有"和"提醒"不影响退出码；加 --strict 时"表里还没有"也算。

2026-11-02 晚加（只在命令行查稿子时做；总调度第 7 步就是这样跑播客稿的。video3_build、build_v3 调 check() 不受影响）：
  6. 播客稿的数字：播客稿按规矩写读法（"二〇二六年""三百亿美元"），tts.py 不做数字转换。
     正文里阿拉伯数字的年份（2026 年、2026—2027 年、2026 财年、FY2026）算"要改"，--fix 自动改成"二〇二六年"这样；
     年数（3 年、100 年、30 多年）、整千（2000 年）不改。别的阿拉伯数字只"提醒"；型号（Opus 4.8、千问 4、W4A4、27B、
     LongCat-2.5）、名字里带数字的（36氪，见 DIGIT_NAMES）不算。--no-numbers 不查这一项（给视频旁白这类本来就写阿拉伯数字的稿子用）。
  --fix 原地改写时，改前的稿子先备份到 ~/.cache/frontier-daily/备份/读音表自动改/（报告里写明路径）。

2026-11-03 加（用户定的规则；同样只在命令行查稿子时做，check() 要传 first_zh=True 才查，video3_build、build_v3 调 check() 不受影响——
  视频旁白的配音前检查把"要改"一律当硬停，不能因为少补一个中文名卡住整期）：
  7. 英文原名第一次出现要补中文名：读音表里写了"中文名"的条目（如 MIT → 麻省理工学院，PIMCO → 品浩 / 太平洋投资管理公司），
     正文里它的"写法"或"也可写"第一次出现时，前后 30 个字以内要有任一个中文名（"MIT，也就是麻省理工学院""麻省理工学院 MIT"
     "MIT（麻省理工学院）"都算），或者中文名在这之前已经出现过（"麻省理工学院计算机科学与人工智能实验室"里含"麻省理工学院"，也算）。
     全文没出现就不查；第二次起只写英文不报。没补的算"要改"（种类"首次补中文"，退出码 1），不自动改，要人来补。

2026-11-05 加：读音表条目可以标"只改口播稿: true"（如融资轮次"C+ 轮"→ 口播写"C 加轮"）。这种条目的"应改""音译"
  只在命令行查稿子时算（check() 传 spoken=True；总调度第 7 步就是这样查播客稿、要改时 --fix 自动改）；
  build_v3（网页中文按读音表自动改）、video3_build（视频旁白配音前检查，要改一律硬停）调 check() 时不算，网页、视频不受影响，
  这时它的"写法""也可写"仍算认识的写法（不会报"表里还没有"）。读音表里放这类不是名字的写法的分类叫"其他"。

2026-11-06 加（11-06 回听核对报告暴露的三处念法问题；都只在命令行查口播稿时做，网页、视频旁白调 check() 不受影响）：
  · 只改口播稿的条目优先：别的条目把同一个写法算作"认识的"（如产品"Hy4"），口播稿里也按只改口播稿那一条改
    （"Hy4" → "HY4"，大写让配音按字母念）。种类：改成的说法是中文的（"设闸" → "设下闸门"）叫"口播改说法"，其余仍叫"应改写法"。
  · 读音表条目可以标"区分大小写: true"：这一条的写法按大小写认（平时不分大小写）。"Hy4"和"HY4"只差大小写，
    不分的话改完还会被认成要改的写法。
  · 8. 英文名后补停顿：两个词以上的英文名（Ricursive Intelligence、Thinking Machines Lab、GPT-6 Cyber）后面直接接
    "发布""推出""宣布"这类动词、中间没有标点时，在英文名后面加逗号（"Ricursive Intelligence，发布了"），算"要改"、能自动改。
    动词后面是"的""会""时""后""前""日"（"发布的模型""发布会"），或者这个分句里英文名前面有"据""由""被""在""和"这类介词、
    连词的，不加（加了会断错句）。check() 传 spoken=True 才查（总调度第 7 步就是这样查播客稿、要改时 --fix 自动改）。
    11-06 晚更正：逗号不够，要中文起句。11-06 下午加了逗号的视频旁白"Ricursive Intelligence，发布了 Ripple-65B Preview"
    两个转写模型照样写成 Fabula：毛病不在动词前少停顿，在"配音单位"的开头——视频一章、播客一块、对谈一轮都是单独一次配音请求，
    模型按开头几个字定读法，开口就是英文名、英文后面只夹两三个汉字又接英文（"GPT-6 Cyber 在 OpenAI 自己的框架里"的"在"
    也被吞了），中间那几个字就被带成英文腔。逗号这条留着（不坏事），真正的检查是下面的"配音单位开头"：
    每个配音单位开头，第一个英文名前汉字不到 OPEN_MIN_HAN（6）个，而且这个英文名后面只隔 SANDWICH_MAX_HAN（3）个以内的
    汉字（不跨句号）又接英文 → "提醒"（种类"配音单位开头夹心"），写稿那步改成中文起句（"前谷歌研究员创立的 Ricursive
    Intelligence，发布了……""网络安全这一项，按 OpenAI 自己的框架，GPT-6 Cyber 从……"）；只夹一个"的"的（"OpenAI 的 CEO
    Sam Altman"，往期没出事）和英文开头、后面跟着一长段中文的（"Anthropic 第三季度营收……""MIT 的研究者让……"）
    只记"配音单位英文开头"弱提醒，总调度不摘。只提醒、不自动改、不影响退出码（不能让 05:00 的自动运行停住）。
    配音单位怎么切和配音程序一致：单人稿按 tts.plan_chunks（一章一块，超过 120 秒才切），对谈稿按轮（同一人连着说的几行并成一轮），
    视频旁白一章一个（video3_storyboard.check_relations 调 voice_opening_rows 查分镜里的 narration，进第 7 步分镜检查的提醒）。
  · 6 的补充：播客稿里"数字＋单位缩写"（501B、1.5T，整数三位以上或带小数）算"要改"、能自动改成"五千零一十亿参数"
    "一点五万亿"（11-06 播客把 501B、816B 念成了 51B、81B）；65B、27B 这类一两位的不改。规则在 spoken_numbers.abbr_to_hanzi；
    为什么播客不写"五百零一 B"也在那里（script_check 核对数字时对不上事件卡）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

sys.dont_write_bytecode = True          # 不在 iCloud 里的项目目录生成 __pycache__
PIPE = Path(__file__).resolve().parent
LEXICON = PIPE / "prompts" / "读音表.yaml"
FIX_BACKUP = Path.home() / ".cache/frontier-daily/备份/读音表自动改"    # --fix 原地改写前，原稿备份到这里
DIGIT_NAMES = ("36氪",)                  # 名字里带数字的媒体、公司：数字检查不算它们（读音表里写了带数字的写法也不算）

CATEGORIES = ("人名", "公司", "产品", "媒体", "其他")     # 其他：不是名字的写法，如融资轮次 C+（2026-11-05 加）
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'.\-&+]*")
VERSION_RE = re.compile(r"^[A-Za-z]?\d+(?:\.\d+)*[A-Za-z]{0,2}$")    # 27.3、V4.1、27B、Q3、16e
ABBR_LETTERS = ("B", "M", "K", "T")      # "五百零一 B""一点五 T"这类读法里单独的字母（视频旁白的念法；有人照这样写进口播稿也不报，11-06 加）
ZH_NUM_END = re.compile(r"[零〇一二两三四五六七八九十百千万亿]\s?$")
DOT_NAME_RE = re.compile(r"[一-鿿]{1,6}(?:·[一-鿿]{1,8})+")
HAS_LATIN = re.compile(r"[A-Za-z]")


def _apos(s):
    return s.replace("’", "'").replace("‘", "'")


def _as_list(v):
    if v is None:
        return []
    return [str(x) for x in (v if isinstance(v, list) else [v])]


# ---------------------------------------------------------------- 读表


def load_lexicon(path=LEXICON):
    """返回 (条目列表, 版本)。每条：写法、之后、身份、也可写、音译、应改、例外、只提醒、中文名、类别。"""
    d = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    entries = []
    for cat in CATEGORIES:
        for e in d.get(cat) or []:
            entries.append({"类别": cat, "写法": str(e["写法"]),
                            "之后": str(e["之后"]) if e.get("之后") else None,
                            "身份": str(e.get("身份") or ""),
                            "也可写": _as_list(e.get("也可写")), "音译": _as_list(e.get("音译")),
                            "应改": _as_list(e.get("应改")), "例外": _as_list(e.get("例外")),
                            "只提醒": bool(e.get("只提醒")),
                            "只改口播稿": bool(e.get("只改口播稿")),
                            "区分大小写": bool(e.get("区分大小写")),
                            "中文名": _as_list(e.get("中文名"))})
    extra = []                                          # 缩写、常用英文词、型号后缀：都算"认识的"
    ab = d.get("缩写") or {}
    for v in (ab.values() if isinstance(ab, dict) else [ab]):
        extra += _as_list(v)
    extra += _as_list(d.get("常用英文词"))
    suffix = {x.lower() for x in _as_list(d.get("型号后缀"))}
    return entries, extra, suffix, str(d.get("版本") or "")


def _target(entry, form):
    """一个不对的写法该换成什么：人名里带空格或"·"的全名换全名，单独的姓换"之后"。"""
    if entry["类别"] == "人名" and entry["之后"] and not re.search(r"[ ·]", form):
        return entry["之后"]
    return entry["写法"]


def build_forms(entries, extra, spoken=False):
    """所有要认的写法：(写法文本, 种类, 条目, 应换成, 能否自动改)。种类：ok / 音译 / 应改。
    spoken=False 时，标了"只改口播稿"的条目只留认识的写法，不查它的音译、应改（见文件开头 2026-11-05 一段）。"""
    forms = []
    # 口播稿里，标了"只改口播稿"的条目要改的写法优先：别的条目把同一个写法算作认识的（产品"Hy4"），口播稿里也照改（2026-11-06 加）
    bad = [(_apos(f), e.get("区分大小写")) for e in entries if e.get("只改口播稿") for f in e["应改"] + e["音译"]] if spoken else []

    def spoken_bad(f):
        f = _apos(f)
        return any(f == b if cs else f.lower() == b.lower() for b, cs in bad)
    for e in entries:
        for f in [e["写法"], e["之后"]] + e["也可写"] + e["例外"]:
            if f and not spoken_bad(f):
                forms.append((f, "ok", e, None, False))
        if e.get("只改口播稿") and not spoken:
            continue
        for f in e["音译"]:
            forms.append((f, "音译", e, _target(e, f), True))
        for f in e["应改"]:
            forms.append((f, "应改", e, _target(e, f), not e["只提醒"]))
    for f in extra:
        forms.append((f, "ok", None, None, False))
    # 同一个写法只留一条（先到先得），再按长度从长到短：长的先认，"Apple 智能"不会被拆成"Apple"
    seen, out = set(), []
    for x in forms:
        cs = bool(x[2] and x[2].get("区分大小写"))
        k = (_apos(x[0]) if cs else _apos(x[0]).lower(), x[1], cs)
        if k not in seen:
            seen.add(k)
            out.append(x)
    return sorted(out, key=lambda x: -len(x[0]))


def _pattern(form, case=False):
    """case=True：按大小写认（读音表条目标了"区分大小写"，2026-11-06 加）。"""
    f = _apos(form)
    body = r"\s*".join(re.escape(p) for p in f.split(" "))
    if HAS_LATIN.search(f):
        pre = r"(?<![A-Za-z0-9])" if re.match(r"[A-Za-z0-9]", f) else ""
        post = r"(?![A-Za-z0-9])" if re.search(r"[A-Za-z0-9]$", f) else ""
        return re.compile(pre + body + post, 0 if case else re.I)
    return re.compile(body)


# ---------------------------------------------------------------- 读稿


SPEAKER_RE = re.compile(r"^(\s*)([甲乙])[：:]")      # 周日对谈稿每一轮开头的"甲：""乙："
SPEAKERS = ("甲", "乙")


def body_mask(text):
    """把不查的地方（注释、# 标题行、> 备注行、对谈稿行首的"甲：""乙："）换成空格，
    长度不变，方便按位置改回原文。"""
    chars = list(text)

    def blank(a, b):
        for i in range(a, b):
            if chars[i] != "\n":
                chars[i] = " "

    for m in re.finditer(r"<!--.*?-->", text, flags=re.S):
        blank(m.start(), m.end())
    pos = 0
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("#") or s.startswith(">"):
            blank(pos, pos + len(line))
        else:
            m = SPEAKER_RE.match(line)
            if m:
                blank(pos + m.start(2), pos + m.end())
        pos += len(line) + 1
    return _apos("".join(chars))


# ---------------------------------------------------------------- 对谈稿（周日版）


def is_dialog(text):
    """正文里有以"甲：""乙："开头的行，就按对谈稿处理。"""
    return any(SPEAKER_RE.match(ln) for ln in re.sub(r"<!--.*?-->", "", text, flags=re.S).split("\n"))


def dialog_turns(text):
    """对谈稿逐轮：[(行号, 章名, 说话人, 内容)]。"""
    out, chapter = [], ""
    plain = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    for i, ln in enumerate(plain.split("\n"), 1):
        h = re.match(r"^##\s+(.+?)\s*$", ln)
        if h:
            chapter = h.group(1)
            continue
        m = SPEAKER_RE.match(ln)
        if m:
            out.append((i, chapter, m.group(2), ln[m.end():].strip()))
    return out


def dialog_problems(text):
    """对谈稿的格式：正文每一行都以"甲：""乙："开头；稿末要有 <!-- 语气 {…} -->（第十轮起每章、每人都可以不写，写了要是情绪词）。
    返回 [{行, 种类, 原文, 说明}]，空 = 没问题。"""
    probs = []
    plain = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    chapters = []
    for i, ln in enumerate(plain.split("\n"), 1):
        s = ln.strip()
        if not s or s.startswith(">"):
            continue
        h = re.match(r"^##\s+(.+?)\s*$", s)
        if h:
            chapters.append(h.group(1))
        elif s.startswith("#"):
            probs.append({"行": i, "种类": "对谈格式", "原文": s[:20], "说明": "只用 ## 章节标题"})
        elif not SPEAKER_RE.match(ln):
            probs.append({"行": i, "种类": "对谈格式", "原文": s[:20], "说明": "正文每一行都要以 甲： 或 乙： 开头"})
        elif not ln[SPEAKER_RE.match(ln).end():].strip():
            probs.append({"行": i, "种类": "对谈格式", "原文": s[:20], "说明": "这一轮没有内容"})
    m = re.search(r"<!--\s*语气\s*(\{.*?\})\s*-->", text, flags=re.S)
    if not m:
        return probs + [{"行": 0, "种类": "语气表", "原文": "<!-- 语气 -->", "说明": "稿末没有风格表"}]
    try:
        style = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        return probs + [{"行": line_of(text, m.start()), "种类": "语气表", "原文": "<!-- 语气 -->",
                         "说明": f"不是合法的 JSON：{e}"}]
    for ch in chapters:
        v = style.get(ch)
        if v is None or isinstance(v, str):         # 第十轮：不写这一章 → 两人都用默认词；写一个字符串 → 两人共用
            continue
        if not isinstance(v, dict):
            probs.append({"行": 0, "种类": "语气表", "原文": ch, "说明": "这一章要写成 {\"甲\": 情绪词, \"乙\": 情绪词}"})
            continue
        for k in v:
            if k not in SPEAKERS:
                probs.append({"行": 0, "种类": "语气表", "原文": f"{ch}/{k}", "说明": "说话人只能是 甲 或 乙"})
    for ch in style:
        if not ch.startswith("_") and ch not in chapters:
            probs.append({"行": 0, "种类": "语气表", "原文": ch, "说明": "风格表里有、正文里没有这一章"})
    return probs


PROFILE = PIPE / "voice_profile.json"


def palette_for_speakers(profile=PROFILE):
    """{"甲": {情绪词…}, "乙": {…}}：周日搭档甲、乙的角色名（Shirley、Dylan）在情绪色板里"可用"的词（小写比）。读不到就空。"""
    try:
        prof = json.loads(Path(profile).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    pal = (prof.get("情绪色板") or {}).get("词") or {}
    pair = prof.get("周日搭档") or {}
    out = {}
    for sp in SPEAKERS:
        host = (pair.get(sp) or {}).get("角色名")
        if host:
            out[sp] = {w.lower() for w, e in pal.items() if ((e or {}).get(host) or {}).get("可用")}
    return out


def dialog_tone_notes(text, profile=PROFILE):
    """对谈稿语气表里写了色板以外的词：只提醒（配音时换成默认词）。返回 提醒 列表。"""
    m = re.search(r"<!--\s*语气\s*(\{.*?\})\s*-->", text, flags=re.S)
    if not m:
        return []
    try:
        style = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    ok = palette_for_speakers(profile)
    notes = []
    try:                                     # 色板里写了"不用于的章"的词（如开场问候句不用 warm），在那一章写了也只提醒
        prof = json.loads(Path(profile).read_text(encoding="utf-8"))
        pal = (prof.get("情绪色板") or {}).get("词") or {}
        hosts = {sp: ((prof.get("周日搭档") or {}).get(sp) or {}).get("角色名") for sp in SPEAKERS}
        banned = {sp: {w.lower(): ((e or {}).get(h) or {}).get("不用于的章") or [] for w, e in pal.items()} for sp, h in hosts.items()}
    except (OSError, json.JSONDecodeError):
        banned = {}
    for ch, v in style.items():
        if str(ch).startswith("_"):
            continue
        cells = {sp: v for sp in SPEAKERS} if isinstance(v, str) else (v if isinstance(v, dict) else {})
        for sp, w in cells.items():
            w = str(w or "").strip()
            if sp not in ok or not w or w.lower() == "fixed":
                continue
            wl = re.sub(r"[\s.;。；]+$", "", w.lower())
            if wl in ok[sp] and str(ch).strip() in (banned.get(sp) or {}).get(wl, []):
                notes.append({"行": line_of(text, m.start()), "种类": "语气表的词不用于这一章", "原文": f"{ch}/{sp}：{w}",
                              "说明": f"实测「{w}」用在「{ch}」会把音高抬高，配音时换成这一章的默认词", "上下文": f"{ch}/{sp}"})
            elif wl not in ok[sp]:
                notes.append({"行": line_of(text, m.start()), "种类": "语气表的词不在色板里", "原文": f"{ch}/{sp}：{w[:40]}",
                              "说明": f"配音时换成默认词；{sp} 能用的词：{'、'.join(sorted(ok[sp])) or '（色板里还没有）'}",
                              "上下文": f"{ch}/{sp}"})
    return notes


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def context(text, a, b, width=14):
    s = text[max(0, a - width):a] + "【" + text[a:b] + "】" + text[b:b + width]
    return s.replace("\n", " ")


# ---------------------------------------------------------------- 核对


INTRO_RE = r"[，,、：:\s]*(?:英文叫|英文是|英文名叫|英文名是|英文原名是|英文原名叫|英文写作)\s*$"


def _introduced(body, a, e):
    """位置 a 的英文原名前面紧挨着"<这一条的中文写法>，英文叫／英文是"——写稿提示词规定的引入术语句式，不算写错语种。"""
    before = body[max(0, a - 40):a]
    return any(re.search(re.escape(_apos(f)) + INTRO_RE, before) for f in [e["写法"]] + e["也可写"] if f)


FIRST_ZH_WINDOW = 30          # 7. 英文原名第一次出现时，中文名要在它前后这么多个字以内（或者更早已经出现过）


def first_zh_problems(text, body, entries, hits):
    """7. 写了"中文名"的条目：第一次出现（写法或也可写）时有没有补中文名。返回 要改 的行（不自动改）。
    hits 是 check() 里按 taken[] 认出来的位置：长名字先认，"MIT CSAIL"里的 MIT 不算 MIT 那一条的出现，不会重复报。"""
    rows = []
    for e in entries:
        zhs = [_apos(z) for z in e.get("中文名") or [] if z]
        if not zhs:
            continue
        pats = [_pattern(f, e.get("区分大小写")) for f in [e["写法"]] + e["也可写"] if f]
        first = next(((a, b) for a, b, kind, he, _t, _au, orig in hits
                      if he is e and kind == "ok" and any(p.fullmatch(_apos(orig)) for p in pats)), None)
        if first is None:
            continue                         # 全文没出现
        a, b = first
        starts = [m.start() for z in zhs for m in re.finditer(re.escape(z), body)]
        if any(s <= b + FIRST_ZH_WINDOW for s in starts):
            continue                         # 之前已出现过，或紧跟在后面 30 个字以内
        name, orig = e["写法"], text[a:b]
        tip = "第一次写 %s 要补中文名：%s（口播说'%s，也就是%s'）" % (orig, "或".join(zhs), name, zhs[0])
        rows.append((a, {"行": line_of(text, a), "种类": "首次补中文", "原文": orig, "应为": tip,
                         "自动改": False, "上下文": context(text, a, b), "说明": tip}))
    return [r for _a, r in sorted(rows, key=lambda x: x[0])]       # 按在稿子里的先后


# 8. 英文名后补停顿（2026-11-06 加，见文件开头）
LATIN_NAME_RE = re.compile(r"(?<![A-Za-z0-9'.\-&+_])[A-Za-z][A-Za-z0-9'.\-&+]*(?: [A-Za-z0-9][A-Za-z0-9'.\-&+]*)+")
PAUSE_VERBS = ("发布", "推出", "宣布", "开源", "上线", "发表", "公布", "披露", "放出", "发起", "启动", "完成", "获得", "拿到")
PAUSE_VERB_RE = re.compile(r"[ \u00a0]*(?:" + "|".join(PAUSE_VERBS) + r")(?![的会时后前日])")
PAUSE_NOT_AFTER = ("据", "根据", "按", "由", "被", "让", "给", "向", "跟", "对", "把", "用", "从", "经", "通过", "替", "比",
                   "在", "和", "与", "同", "及", "随", "为", "等", "待", "于")   # 分句里英文名前面有这些：英文名多半不是主语，加逗号会断错句
CLAUSE_START = re.compile(r"[，。！？；：、,!?;:（）()“”\"「」『』\n][^，。！？；：、,!?;:（）()“”\"「」『』\n]*$")


def pause_problems(text, body):
    """8. 两个词以上的英文名后面直接接"发布""推出"这类动词：要改，自动在英文名后面加逗号。返回 (要改的行, {(起, 止): "，"})。"""
    rows, fixes = [], {}
    for m in LATIN_NAME_RE.finditer(body):
        v = PAUSE_VERB_RE.match(body, m.end())
        if not v:
            continue
        head = body[:m.start()]
        c = CLAUSE_START.search(head)
        clause = head[c.start() + 1:] if c else head
        if any(w in clause for w in PAUSE_NOT_AFTER):
            continue
        a, b = m.end(), m.end() + len(v.group(0)) - len(v.group(0).lstrip(" \u00a0"))   # 英文名和动词之间的空格
        verb = v.group(0).lstrip(" \u00a0")
        tip = ("英文名后面直接接中文动词，口播稿在英文名后面加逗号；逗号只让中间停一下，挡不住开头的英文腔"
               "——配音单位开头要中文起句，见第 8 项后半的提醒")
        rows.append({"行": line_of(text, m.start()), "种类": "英文名后补停顿", "原文": text[m.start():b] + verb,
                     "应为": text[m.start():m.end()] + "，" + verb, "自动改": True,
                     "上下文": context(text, m.start(), b + len(verb)), "说明": tip})
        fixes[(a, b)] = "，"
    return rows, fixes


# 8 后半：配音单位开头（2026-11-06 晚加，见文件开头；只提醒）
OPEN_MIN_HAN = 6         # 配音单位开头，第一个英文名前至少这么多汉字才算"中文起句"
SANDWICH_MAX_HAN = 3     # 开头的英文名后面只隔这么几个汉字（不跨句号）就又接英文 → 夹心开头
HAN_CHAR = re.compile(r"[\u3400-\u9fff]")
LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9'’.\-&+_]*(?:[ \u00a0]+[A-Za-z0-9][A-Za-z0-9'’.\-&+_]*)*")
SENT_END = re.compile(r"[。！？!?\n]")


def opening_problem(text):
    """一个配音单位的开头有没有"英文名开口"的毛病。返回 None，或 {强弱: 强/弱, 原文: 开头一段, 前面汉字: n, 夹着: 字}。
    强：第一个英文名前汉字不到 OPEN_MIN_HAN 个，后面只隔 SANDWICH_MAX_HAN 个以内的汉字（不跨句号）又接英文，而且夹着的不只是一个"的"。
    弱：英文开头，但后面跟着一长段中文，或只夹一个"的"（"OpenAI 的 CEO Sam Altman"）。"""
    t = (text or "").lstrip()
    m = LATIN_RUN.search(t)
    if not m:
        return None
    # 阿拉伯数字配音时念成中文（视频旁白配音前转念法，播客稿本来就写读法），一位算一个汉字：“苹果在 2024 年 WWDC”前面有 8 个音节
    npre = len(HAN_CHAR.findall(t[:m.start()])) + len(re.findall(r"\d", t[:m.start()]))
    if npre >= OPEN_MIN_HAN:
        return None
    rest = t[m.end():]
    m2 = LATIN_RUN.search(rest)
    mid = rest[:m2.start()] if m2 else rest
    hm = "".join(re.findall(r"[\u3400-\u9fff\d]", mid))
    strong = bool(m2) and not SENT_END.search(mid) and len(hm) <= SANDWICH_MAX_HAN and hm != "的"
    end = m.end() + (m2.end() if m2 else min(len(rest), 12))
    return {"强弱": "强" if strong else "弱", "原文": t[:min(end, 60)].strip(), "前面汉字": npre, "夹着": hm if m2 else ""}


def voice_units(text):
    """这份口播稿一次一次发给配音模型的单位：[(行号, 在哪, 字)]。和配音程序切法一致：
    对谈稿（行首"甲：""乙："）按轮，同一章里同一个人连着说的几行并成一轮（dialog_tts.parse_dialog 的切法）；
    单人稿按 tts.plan_chunks（一章一块，估计超过 120 秒才切成几块）；tts 读不进来时退回"每章第一段"。"""
    if is_dialog(text):
        out = []
        for ln, chap, spk, body in dialog_turns(text):
            if out and out[-1][3] == chap and out[-1][4] == spk:
                out[-1][2] += body
            else:
                out.append([ln, "%s·%s" % (chap or "开头", spk), body, chap, spk])
        return [(a, b, c) for a, b, c, _d, _e in out]
    plain = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    try:
        import tts                      # pipeline/tts.py：和配音同一个切块函数
        chunks = [(c.get("chapter_title") or "", c["text"]) for c in tts.plan_chunks(tts.parse_script(text))]
    except Exception:  # noqa: BLE001
        chunks, chap, first = [], "", True
        for ln in plain.split("\n"):
            h = re.match(r"^##\s+(.+?)\s*$", ln)
            if h:
                chap, first = h.group(1), True
                continue
            if first and ln.strip() and not ln.lstrip().startswith(("#", ">")):
                chunks.append((chap, ln.strip()))
                first = False
    out = []
    for chap, body in chunks:
        head = body.strip()[:12]
        pos = plain.find(head) if head else -1
        out.append((line_of(text, pos) if pos >= 0 else 0, chap or "开头", body))
    return out


def voice_opening_rows(units, what="块"):
    """units：[(行号, 在哪, 字)] → 提醒行（强的种类"配音单位开头夹心"，弱的"配音单位英文开头"）。"""
    rows = []
    for ln, where, body in units:
        r = opening_problem(body)
        if not r:
            continue
        if r["强弱"] == "强":
            tip = ("这一%s单独配音，开口就是英文名、后面只隔“%s”又接英文：模型按开头几个字定读法，中间这几个字会被带成英文腔"
                   "（11-06 视频“Ricursive Intelligence，发布了”转写成 Fabula，加逗号也没用）。改成中文起句，"
                   "第一个英文名前至少 %d 个左右汉字（如“前谷歌研究员创立的 Ricursive Intelligence，发布了……”）"
                   % (what, r["夹着"] or "", OPEN_MIN_HAN))
            kind = "配音单位开头夹心"
        else:
            tip = "这一%s开口是英文名（前面 %d 个汉字）；后面中文够长，往期没出事，能顺手改成中文起句更稳" % (what, r["前面汉字"])
            kind = "配音单位英文开头"
        rows.append({"行": ln, "种类": kind, "原文": r["原文"], "说明": tip, "上下文": "【%s】%s" % (where, r["原文"]),
                     "强弱": r["强弱"]})
    return rows


def check(text, entries, extra, suffix, first_zh=False, spoken=False):
    """first_zh=True 时另查第 7 项（英文原名第一次出现要补中文名，见文件开头）；命令行查稿子时打开。
    spoken=True 时标了"只改口播稿"的条目也查（2026-11-05 加），另查第 8 项英文名后补停顿（2026-11-06 加）；同样只在命令行查稿子时打开。"""
    body = body_mask(text)
    taken = [False] * len(body)
    hits = []                       # (起, 止, 种类, 条目, 应换成, 能否自动改, 原文)
    for form, kind, e, tgt, auto in build_forms(entries, extra, spoken):
        for m in _pattern(form, bool(e and e.get("区分大小写"))).finditer(body):
            a, b = m.span()
            if a == b or any(taken[a:b]):
                continue
            for i in range(a, b):
                taken[i] = True
            hits.append((a, b, kind, e, tgt, auto, text[a:b]))
    hits.sort(key=lambda h: h[0])

    fixes, must, notes = {}, [], []          # fixes：{(起, 止): 换成什么}
    for a, b, kind, e, tgt, auto, orig in hits:
        if kind == "ok":
            continue
        if kind == "应改" and e is not None and not HAS_LATIN.search(tgt) and _introduced(body, a, e):
            continue                         # "私密云端运算，英文叫 Private Cloud Compute"：先说中文、再带出原名
        what = "音译" if kind == "音译" else ("应写中文" if not HAS_LATIN.search(tgt) else "应改写法")
        if e is not None and e.get("只改口播稿") and kind != "音译" and not HAS_LATIN.search(tgt):
            what = "口播改说法"                  # "设闸" → "设下闸门"：不是"写成中文名"，是口播换个不会念错的说法（11-06 加）
        row = {"行": line_of(text, a), "种类": what, "原文": orig, "应为": tgt,
               "自动改": auto, "上下文": context(text, a, b)}
        must.append(row)
        if auto:
            fixes[(a, b)] = tgt

    # 人名：第一次说全名并带身份，之后只说姓
    for e in entries:
        if e["类别"] != "人名" or not e["之后"] or not HAS_LATIN.search(e["写法"]):
            continue
        fulls = {_apos(x).lower() for x in [e["写法"]] + e["也可写"]}
        seq = []
        for a, b, kind, he, tgt, auto, orig in hits:
            if he is not e:
                continue
            shown = tgt if kind != "ok" else orig
            # 同姓不同人（11-09 加）：只说了姓、前面紧挨着别的名（"Daniel Roberts"，表里是 Luke Roberts），是另一个人，这一处不算
            given = re.search(r"([A-Z][a-z]+(?:-[A-Z][a-z]+)?)[ ·]$", text[max(0, a - 30):a])
            if given and _apos(shown).lower() not in fulls and ("%s %s" % (given.group(1), shown)).lower() not in fulls:
                continue
            seq.append((a, b, _apos(shown).lower() in fulls, kind))
        if not seq:
            continue
        a, b, is_full, kind = seq[0]
        if not is_full:
            must.append({"行": line_of(text, a), "种类": "人名首次要说全名", "原文": text[a:b],
                         "应为": e["写法"], "自动改": True, "上下文": context(text, a, b),
                         "说明": f"第一次提到要说全名并带身份：{e['身份'] or '（身份见当天事件卡）'}"})
            fixes[(a, b)] = e["写法"]           # 第一次是音译（"奥尔特曼"）也直接换成全名
        elif e["身份"]:
            role = re.sub(r"（.*?）|\(.*?\)", "", e["身份"])
            keys = [k for k in re.split(r"[的\s兼、]+", role) if len(k) >= 2]
            window = body[max(0, a - 30):a]
            if keys and not any(k.lower() in window.lower() for k in keys):
                notes.append({"行": line_of(text, a), "种类": "第一次提到最好带身份", "原文": text[a:b],
                              "说明": f"身份：{e['身份']}", "上下文": context(text, a, b)})
        for a2, b2, full2, kind2 in seq[1:]:
            if full2:
                must.append({"行": line_of(text, a2), "种类": "之后只说姓", "原文": text[a2:b2],
                             "应为": e["之后"], "自动改": True, "上下文": context(text, a2, b2)})
                fixes[(a2, b2)] = e["之后"]

    if first_zh:                             # 7. 英文原名第一次出现要补中文名（2026-11-03 用户定）
        must += first_zh_problems(text, body, entries, hits)
    if spoken:                               # 8. 英文名后补停顿（2026-11-06 加，只改口播稿）
        rows, fx = pause_problems(text, body)
        must += rows
        for k, v in fx.items():
            fixes.setdefault(k, v)
        try:                                 # 8 后半：配音单位开头（11-06 晚加，只提醒）
            notes += voice_opening_rows(voice_units(text), "轮" if is_dialog(text) else "块")
        except Exception as e:  # noqa: BLE001  只是提醒，出错不能拦住检查
            notes.append({"行": 0, "种类": "配音单位开头", "原文": "", "说明": "没查成（%s）" % e, "上下文": ""})

    # 表里还没有的英文名：认过的地方涂掉，剩下的英文词逐个看
    rest = "".join(" " if t else c for c, t in zip(body, taken))
    unknown = {}
    toks = [(m.start(), m.end(), m.group(0).rstrip(".-'")) for m in TOKEN_RE.finditer(rest)]
    phrase = None
    for a, b, tok in toks:
        ok = (not HAS_LATIN.search(tok) or VERSION_RE.match(tok) or tok.lower() in suffix
              or (tok in ABBR_LETTERS and ZH_NUM_END.search(rest[max(0, a - 2):a])))   # "五百零一 B"里的 B（11-06 加）
        if ok:
            phrase = None
            continue
        if phrase and re.fullmatch(r"\s+", rest[phrase["止"]:a]):
            phrase["词"] += rest[phrase["止"]:a] + tok
            phrase["止"] = b
        else:
            phrase = {"起": a, "止": b, "词": tok}
            unknown.setdefault(id(phrase), phrase)
    grouped = {}
    for p in unknown.values():
        w = re.sub(r"\s+", " ", p["词"])
        grouped.setdefault(w, []).append(line_of(text, p["起"]))
    missing = [{"英文": w, "次数": len(ls), "行": sorted(set(ls))} for w, ls in grouped.items()]

    # 带"·"的中文名
    for m in DOT_NAME_RE.finditer(body):
        a, b = m.span()
        if not any(taken[a:b]):
            notes.append({"行": line_of(text, a), "种类": "疑似西方人名的中文音译", "原文": m.group(0),
                          "说明": "读音表里没有；西方人名应写英文原名，查清后补进表里",
                          "上下文": context(text, a, b)})

    must.sort(key=lambda r: r["行"])
    notes.sort(key=lambda r: r["行"])
    dialog = dialog_problems(text) if is_dialog(text) else []
    if is_dialog(text):
        notes += dialog_tone_notes(text)
    return {"要改": must, "提醒": notes, "表里还没有": missing, "对谈格式": dialog, "_fixes": fixes}


NUM_RE = re.compile(r"(?<![A-Za-z0-9.\-_/])\d+(?:[.,]\d+)*(?![A-Za-z0-9])")
MODEL_BEFORE = re.compile(r"[A-Za-z][A-Za-z0-9.\-]*[  ]$")     # 前面紧挨着"英文词＋一个空格"：型号、版本（Opus 4.8、Gemini 4）


def podcast_numbers(text, entries):
    """6. 播客稿的数字（见文件开头）。返回 {"要改": 年份、数字＋单位缩写（都能自动改）, "提醒": 别的阿拉伯数字, "_fixes": {(起, 止): 改成}}。"""
    if str(PIPE) not in sys.path:
        sys.path.insert(0, str(PIPE))
    import spoken_numbers as SN          # noqa: E402
    body = body_mask(text)
    _new, changes = SN.years_to_hanzi(body)
    must, fixes = [], {}
    for c in changes:
        old, new = c["显示"].split(" → ")
        must.append({"行": line_of(text, c["起"]), "种类": "阿拉伯数字的年份", "原文": old, "应为": new, "自动改": True,
                     "上下文": context(text, c["起"], c["止"]), "说明": "播客稿写读法，tts.py 不转数字"})
        fixes[(c["起"], c["止"])] = c["改成"]
    _new, changes = SN.abbr_to_hanzi(body)                 # 501B → 五千零一十亿参数（2026-11-06 加）
    for c in changes:
        if any(a < c["止"] and c["起"] < b for a, b in fixes):
            continue
        old, new = c["显示"].split(" → ")
        must.append({"行": line_of(text, c["起"]), "种类": "数字加单位缩写", "原文": old, "应为": new, "自动改": True,
                     "上下文": context(text, c["起"], c["止"]),
                     "说明": "参数量这类三位以上的数字配音会念短（11-06 播客 501B 念成 51B），播客稿写读法"})
        fixes[(c["起"], c["止"])] = c["改成"]
    masked = list(body)
    for a, b in fixes:
        masked[a:b] = " " * (b - a)
    names = list(DIGIT_NAMES) + [f for e in entries for f in [e["写法"]] + e["也可写"] if re.search(r"\d", f)]
    masked = "".join(masked)
    for f in names:
        for m in re.finditer(re.escape(f), masked):
            masked = masked[:m.start()] + " " * len(f) + masked[m.end():]
    notes = []
    for m in NUM_RE.finditer(masked):
        if MODEL_BEFORE.search(masked[max(0, m.start() - 40):m.start()]):
            continue
        a, b = m.span()
        notes.append({"行": line_of(text, a), "种类": "阿拉伯数字", "原文": text[a:b + 2].strip(),
                      "说明": "播客稿数字写读法（如\"三百亿美元\"\"百分之十\"），配音不转念法；型号、版本不用改",
                      "上下文": context(text, a, b)})
    return {"要改": must, "提醒": notes, "_fixes": fixes}


_CJK = re.compile(r"[㐀-鿿]")
_LAT = re.compile(r"[A-Za-z0-9]")


def _spaced(out, a, b, tgt):
    """换字时顺手调空格：中文和英文之间留一个空格，中文和中文之间不留（本项目稿子的写法）。"""
    left, right = out[:a], out[b:]
    if tgt and _LAT.match(tgt[0]) and left and _CJK.match(left[-1]):
        tgt = " " + tgt
    elif tgt and _CJK.match(tgt[0]) and left.endswith(" ") and len(left) > 1 and _CJK.match(left[-2]):
        left = left[:-1]
    if tgt and _LAT.match(tgt[-1]) and right and _CJK.match(right[0]):
        tgt = tgt + " "
    elif tgt and _CJK.match(tgt[-1]) and right.startswith(" ") and len(right) > 1 and _CJK.match(right[1]):
        right = right[1:]
    return left + tgt + right


def apply_fixes(text, fixes):
    """fixes：{(起, 止): 换成什么}。从后往前换，位置不乱。"""
    done, out = [], text
    for (a, b), tgt in sorted(fixes.items(), key=lambda x: -x[0][0]):
        if out[a:b] != tgt:
            done.append({"行": line_of(text, a), "原文": text[a:b], "改成": tgt})
            out = _spaced(out, a, b, tgt)
    return out, sorted(done, key=lambda r: r["行"])


# ---------------------------------------------------------------- 输出


def report(path, res, version, n_entries, fixed=None):
    lines = [f"读音表核对：{path}（读音表 {version}，{n_entries} 条）"]
    if fixed:
        lines.append(f"已自动改 {len(fixed)} 处：")
        lines += [f"  第 {r['行']} 行  {r['原文'] if r['原文'].strip() else '（英文名后）'} → {r['改成']}" for r in fixed]
    if res["要改"]:
        lines.append(f"✗ 要改（{len(res['要改'])} 处）：")
        for r in res["要改"]:
            tail = "" if r["自动改"] else "（只提醒，要人来改）"
            extra = f"；{r['说明']}" if r.get("说明") and r["说明"] != r["应为"] else ""
            lines.append(f"  第 {r['行']} 行  {r['种类']}：{r['原文']} → {r['应为']}{tail}{extra}"
                         f"    …{r['上下文']}…")
    if res["提醒"]:
        lines.append(f"! 提醒（{len(res['提醒'])} 处）：")
        for r in res["提醒"]:
            lines.append(f"  第 {r['行']} 行  {r['种类']}：{r['原文']}；{r['说明']}    …{r['上下文']}…")
    if res["表里还没有"]:
        lines.append(f"? 读音表里还没有的英文名（{len(res['表里还没有'])} 个），定好写法补进 读音表.yaml：")
        for r in sorted(res["表里还没有"], key=lambda r: r["行"][0]):
            lines.append(f"  {r['英文']} ×{r['次数']}（第 {'、'.join(map(str, r['行']))} 行）")
    if res.get("对谈格式"):
        lines.append(f"✗ 对谈稿格式（{len(res['对谈格式'])} 处）：")
        for r in res["对谈格式"]:
            where = f"第 {r['行']} 行" if r["行"] else "风格表"
            lines.append(f"  {where}  {r['种类']}：{r['原文']} —— {r['说明']}")
    if not (res["要改"] or res["提醒"] or res["表里还没有"] or res.get("对谈格式")):
        lines.append("✓ 全部按读音表写，没有发现问题")
    elif not (res["要改"] or res.get("对谈格式")):
        lines.append("✓ 没有要改的地方")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="读音表核对（用法见文件开头）")
    ap.add_argument("script", help="口播稿（Markdown 或纯文本）")
    ap.add_argument("--lexicon", default=str(LEXICON), help="读音表（默认 pipeline/prompts/读音表.yaml）")
    ap.add_argument("--fix", action="store_true", help="能自动改的改掉；不给 --out 就原地改写")
    ap.add_argument("--out", help="--fix 时改好的稿子另存到这里")
    ap.add_argument("--json", action="store_true", help="结果输出成 JSON")
    ap.add_argument("--strict", action="store_true", help='"表里还没有"也算问题（退出码 1）')
    ap.add_argument("--no-numbers", action="store_true",
                    help="不查播客稿的数字（年份自动改成二〇二六年、别的阿拉伯数字提醒）；视频旁白这类本来写阿拉伯数字的稿子用")
    a = ap.parse_args(argv)

    entries, extra, suffix, version = load_lexicon(a.lexicon)
    text = Path(a.script).read_text(encoding="utf-8")

    def full_check(t):
        r = check(t, entries, extra, suffix, first_zh=True, spoken=True)   # 7. 首次补中文名（11-03 加）；只改口播稿的条目（11-05 加）
        if not a.no_numbers:                            # 6. 播客稿的数字（2026-11-02 晚加）
            nm = podcast_numbers(t, entries)
            r["要改"] = sorted(r["要改"] + nm["要改"], key=lambda x: x["行"])
            r["提醒"] = sorted(r["提醒"] + nm["提醒"], key=lambda x: x["行"])
            r["_fixes"].update(nm["_fixes"])
        return r

    res = full_check(text)
    fixed, backup = None, None
    if a.fix:
        new, fixed = apply_fixes(text, res["_fixes"])
        out = Path(a.out) if a.out else Path(a.script)
        if fixed and not a.out:                         # 原地改写：先备份原稿
            from datetime import datetime
            FIX_BACKUP.mkdir(parents=True, exist_ok=True)
            backup = FIX_BACKUP / f"{out.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{out.suffix}"
            backup.write_text(text, encoding="utf-8")
        if fixed or a.out:
            out.write_text(new, encoding="utf-8")
        text = new
        res = full_check(text)                          # 改完再查一遍，报剩下的
    res.pop("_fixes", None)
    if a.json:
        print(json.dumps(dict(res, 已自动改=fixed or [], **({"改前备份": str(backup)} if backup else {})),
                         ensure_ascii=False, indent=1))
    else:
        print(report(a.out or a.script, res, version, len(entries), fixed))
        if backup:
            print(f"改前的稿子备份在 {backup}")
    bad = bool(res["要改"]) or bool(res.get("对谈格式")) or (a.strict and bool(res["表里还没有"]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
