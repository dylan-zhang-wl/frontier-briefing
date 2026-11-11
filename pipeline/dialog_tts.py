#!/usr/bin/env python3
"""周日对谈配音：甲乙两人的对谈稿 → 每章人声 WAV ＋ 章节表 →（接 podcast_mix.py 的声音包）整集 MP3。

用法（在项目根运行）：
    PY=~/.venvs/frontier-daily/bin/python
    # 先看怎么分轮、每轮多长、换人停多久、Gemini 大概花多少（不调模型、不花钱）
    $PY pipeline/dialog_tts.py 对谈稿.md --plan
    # 配音＋混音（默认配声音包 v3，和工作日同一套：6 秒片头、亮底乐 −26 dB、转场、片尾）
    $PY pipeline/dialog_tts.py 测试版/2026-11-01/04_文稿/claude_对谈_v3.md \
        --out 测试版/2026-11-01/05_配音/对谈_v3_带音效 --speech-out 测试版/2026-11-01/05_配音/对谈_v3 \
        --title "每日AI科技前沿简报 · 2026年11月1日（周日对谈）"
    #   人声和混音两个目录并排放，site/tools/build_v3.py --podcast 05_配音/对谈_v3_带音效 能直接用（"听这一段"也对得上）
    #   --package v3/A 换声音包；--no-mix 只出人声；--budget-usd 0.3 这次 Gemini 最多花多少（默认 0.5）；
    #   --fresh 不用缓存全部重配；--no-qc 不对稿；--reviewed 稿子已人工审过（写进音频文件信息）；
    #   --use-backup 乙（或 甲、或两个都写）直接用备用声音；--no-fallback Gemini 出错就停，不自动换备用声音

稿子格式（写稿的 agent 照这个写）：
    ## 开场 / ## 热点一 / … / ## 结尾      章名和工作日一样；标题不念
    甲：……                                 每句以"甲："或"乙："开头（全角、半角冒号都认）
    乙：……
    <!-- 语气 {"开场": {"甲": "fixed", "乙": "…"}, …} -->   稿末的分章语气表（注释不念；甲那一格照抄 "fixed"，程序不用）
    没写"甲：""乙："的一行，算上一个人接着说（会提醒）；"# 总标题"、> 备注、其他 <!-- 注释 --> 都不念。
    甲的语气由程序固定（profile"周日搭档.甲"的"语气固定用默认"）：和视频旁白一样用工作日庚A 的基础语气，只在开场、结尾
    按 video3_build.GEMINI_TWEAKS 加 "warm" / "warm, a touch slower"；稿末语气表里甲那一列不用（写了也不用）。
    乙的语气照语气表用，写英文、短（Gemini 指南：只写情绪、语调、快慢）；表里没写的章用乙的"默认语气"。
    换成 MiMo 备用声音的那位不用表里的英文语气，整期用自己的中文导演模式默认语气（MiMo 文档：角色／场景／指导）；
    反过来，写成中文导演模式的那句也不发给 Gemini。甲的语气（默认语气、微调）用 site/tools/video3_build.py 的
    STYLE_BANNED（和视频旁白同一份）查，不许有更亮、更高、更有活力的字眼。

两个声音从 pipeline/voice_profile.json 的"周日搭档"读（2026-11-01 用户定）：
    甲（主持）＝庚A：取自"主声音"，和工作日播客、视频旁白同一个声音、同样的设置——Gemini 3.8 Flash TTS，走 Vertex
        （tts_engines.py 的项目和账号，令牌每次现取），每轮语气后面照工作日补"主声音"那句"音区抬高"，音高参考用
        "带抬高那句"（163.7 Hz）。语气固定＝video3_build.py 的 GEMINI_STYLE（工作日庚A 的基础语气）＋一小句"和搭档聊"，
        开场、结尾按视频旁白的写法微调（稿末语气表里甲那一列不用）。
    乙（搭档）＝男声03：第七轮 03 Gemini·沉稳带笑，声音 ID、参考音高都写在"周日搭档.乙"里；"对谈加速"写 1.0 就不变速，
        也可以写小于 1 放慢（后期 atempo，只改快慢、不改音高）。
    Gemini 出错（重试后仍失败）时自动换备用声音：乙整期改用"乙备用"（男声06，MiMo 声音复刻）；甲按工作日规则整期改用
        "备用声音"（乙稍快，MiMo，atempo 1.09，profile"甲备用"）。谁出错换谁，没出错的那位照旧；换了什么记进 qc.json。
        项目在禁用名单里（tts_engines.FORBIDDEN_PROJECTS）是配置错，直接停、不换。
    Gemini 一次请求只能用一个声音，所以一轮一轮分开配，再拼起来。

怎么做：
    1. 分轮：同一个人连着说的几行并成一次请求（一"轮"）；一轮估计超过 100 秒才按句号再切。
    2. 配音：每轮按说话人用各自的引擎（同时发几条，Gemini 3 条、MiMo 2 条）；音频按"文字＋声音＋语气＋第几条"
       存缓存，再跑一字没改的轮不花钱。
    3. 对稿：本机 Whisper 转写回来和原稿比（tts_qc.py，一次进程转完一集），多念、漏念、字错率过高就重录一次；
       两条都不理想时留较好的一条，标"需人工复听"。≤8 个字的短句按拼音比（短句里一个同音字就是两成错误率）。
       音高把关：每轮量音高中位数，和这个人自己的参考音高比，差超过 1.5 个半音就重录（profile"音高把关"）；
       短问句（整轮不超过 4 秒、问号结尾，句尾上扬）只量、只标，不重录。
       MiMo 另有"跑偏"把关：时长超过估计的 1.5 倍、或音高离参考差 3 个半音以上，就再录（免费，最多 3 次）。
       音色把关（pipeline/voice_print.py）：每条原声和这个人的音色档案比，低于 0.60 重录（和音高共用"最多再录"）；
       挑哪一条：先挑音高、音色都过的，其中音高最接近参考的；都没过音色线就取最像的，标"音色需人工听"；
       每章每人、整期每人再各判一次，只提醒。
    4. 后期：去首尾静音 → 按"对谈加速"变速 → 每轮统一响度（甲 −16 LUFS，乙按"乙比甲低LU"低一点）→
       两人引擎不同（用到 MiMo 备用）时才让乙往甲的音色靠一点（只看 1–8 kHz，1 kHz 以下不改形状）→
       一轮里超过 0.7 秒的停顿缩到 0.55 秒（模型偶尔在短句中间停很久）→ 按章拼接，
       换人时留 0.22–0.5 秒（快问之后最短，长段之后稍长）→ 两人引擎不同时才整章过同一个很轻的"小房间"混响 →
       整章量响度、乘一个固定增益到 −16 LUFS → 只削尖峰的真峰值限制器（带预读，−1.7 dBTP；不是压缩）→
       量成品里两人差多少 LU，偏离"乙比甲低LU"0.1 以上就按差再校（最多两次，本机，不花钱）。参数在 profile"周日搭档"里。
    5. 产出每章人声 WAV（放缓存）和 qc.json、usage.json——格式和 tts.py --chapter-wavs 一样，
       podcast_mix.py 直接能混；默认接着调 podcast_mix 的声音包混出整集。对谈换人的空白都不到 1 秒，底乐整章压着，
       所以按 profile"声音包调整"把章与章之间留长一点（1.6 秒），并让底乐在章间浮起来透口气（工作日不受影响）。
       qc.json"配置"、usage.json"声音"记着两人各用的引擎、模型、声音 ID（或参考音）。

产出（--out 目录）：
    episode.mp3       整集（带声音包）：−16 LUFS，立体声 96 kbps，带章节和音频文件信息
    chapters.json     每章开始秒数（Podcasting 2.0 格式）
    qc.json、usage.json   混音记录、用量（podcast_mix.py 写的）
    人声/（或 --speech-out 指定的目录）  不带音乐的对谈人声：episode.mp3（好挑毛病）、chapters.json、
                      qc.json（每轮的对稿、响度、停顿，两人的响度和音色对比）、usage.json
第十轮（11-01 晚加，命令行默认开，各有开关；四个都关时和原来逐字节相同）：
    --no-palette：情绪色板（甲、乙都按 tts.compose_style 拼语气，稿末语气表每格写一个色板里的词，或写 fixed／不写用默认词）；
    --no-sentence-level：每轮句子级找平；--no-tempo-adjust：每轮语速微调＋两人语速差不超过 5%；
    --no-duration-gate：按 --day-type（默认 周日）写稿提示词的"成片时长分钟"把关成片时长（配音前估、混音后查）。
    备用声音（profile"周日搭档"）11-01 晚换成两人自己定稿录音的 MiMo 复刻（甲备用＝Shirley 备用，乙备用＝Dylan 备用）。
    备用也按色板换情绪：同一个情绪词改用"情绪色板.MiMo固定层.<主播>.对谈"模板和这个词的中文指导（MiMo 没过线的词用默认情绪）；
    只在 --no-palette 时才用的旧语气设置挪进了各人那一节的"旧做法（--no-palette 时才用）"（_get 照样读得到）。
缓存：~/.cache/frontier-daily/tts/（和 tts.py 共用 chunks、whisper、chapters 三个目录，14 天没用到自动清）。
"""
import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import threading
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
ROOT = PIPE.parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

import keys                      # noqa: E402  （MiMo 密钥只经 keys.load_local_env() 读进环境，不输出）
import podcast_mix as M          # noqa: E402
import tts                       # noqa: E402
import tts_engines as E          # noqa: E402
import tts_qc as Q               # noqa: E402
import voice_print as VP         # noqa: E402  （音色把关；模型用到才加载，装不上就只记"未判"）

# ============================ 可改区 ============================

PROFILE = PIPE / "voice_profile.json"
CACHE = tts.CACHE                # ~/.cache/frontier-daily/tts
SR = 24000
TARGET_LUFS = -16.0
MAX_TURN_S = 100                 # 一轮估计超过这么多秒才切开（两个引擎实测都能一次念 110 秒左右）
RETAKES = 1
WORKERS = {"gemini": 3, "gemini-api": 3, "mimo": 2}   # 每个引擎同时发几条请求
SHORT_TOKENS = 8                 # 这么短的句子按拼音判断要不要重录
CHAPTER_GAP = 0.8                # 只在"人声/episode.mp3"里用；混音时章与章之间由声音包决定
BUDGET_USD = 0.5
FORBIDDEN_PROJECTS = E.FORBIDDEN_PROJECTS   # 禁用的 Google 项目只在 tts_engines.py 写一份（建 Vertex 客户端时查）
TP_CEILING_DB = -1.7             # 整章到 −16 LUFS 后，真峰值限制器把尖峰削到这么多 dBTP 以下（约 −1.5，留 0.2 dB 给编码和测量误差），
                                 # 后面 podcast_mix 整集统一响度（loudnorm，真峰值目标 −1.5）才能走线性方式
LIMIT_RAMP_S = 0.010             # 限制器：提前这么久开始压（预读），压完用这么久回来（只在尖峰附近动，不是压缩）
LIMIT_HOLD_S = 0.030             # 限制器：压下去以后至少保持这么久再回来，免得一个音节里忽上忽下
B_QUIETER_LU = 0.0               # 乙比甲低多少 LU；profile"周日搭档"的"乙比甲低LU"会覆盖这里
CALIBRATE_LU = 0.10              # 成品里量出来的两人响度差偏离目标超过这么多，就按差再校（最多两次，本机，不花钱）
# MiMo 偶尔"跑偏"（第七轮实测：06 的一轮念了 20 分钟，另一轮拖到两倍长、音调也变了），对稿有时还能过。
# 时长超过估计的"时长比"倍、或音高离这个声音的参考差"音高半音"以上，就再录（MiMo 免费），最多"最多再录"次，挑最正常的一条
MIMO_ODD = {"时长比": 1.5, "音高半音": 3.0, "最多再录": 3}

# 换人停顿（秒）：说完到下一个人开口之间的空白。profile"周日搭档"里的"换人停顿秒"会覆盖这里
GAPS = {"快问之后": 0.24, "提问之后": 0.32, "短回应之前": 0.27, "长段之后": 0.45, "一般": 0.36,
        "同一人接着说": 0.40, "浮动": 0.03, "最短": 0.22, "最长": 0.50}
# 一轮里面的停顿：模型偶尔在短句中间停很久（10-31 实测 MiMo 在 2.4 秒的"这条线，我们会接着跟"里停了 0.87 秒），
# 超过"超过"秒的静音缩到"缩到"秒。profile"周日搭档"里的"句中停顿秒"会覆盖这里；"超过"写 0 就不缩
PAUSE = {"超过": 0.7, "缩到": 0.55}
QUICK_QUESTION_S = 4.0           # 不超过这么长的问句算"快问"；也是"短问句不判音高"的界线（整轮不超过这么多秒、问号结尾：只量、只标，不重录）
SHORT_REPLY_S = 1.6              # 不超过这么长的一轮算"短回应"（"对。""没错。"）
LONG_TURN_S = 15.0
# 统一音色：profile"周日搭档"里的"统一音色"会覆盖这里
# （11-01 改：两人同一个引擎就都不做；均衡只看 1–8 kHz，不再从 200 Hz 起把男声的中低音往女声那边削）
LOOK = {"只在两人引擎不同时做": True, "乙向甲靠的均衡强度": 0.6, "均衡最多改dB": 4.0, "均衡看的频段Hz": [1000, 8000],
        "共用小房间": {"混响时间秒": 0.25, "湿声比干声低dB": 22}}

# ==============================================================

HAN = r"[㐀-鿿]"
BANDS = 1000 * 2 ** (np.arange(-10, 11) / 3)      # 三分之一倍频程中心频率，约 99 Hz – 10 kHz
RANGES = {"低频 200–500 Hz": (200, 500), "中频 500–2000 Hz": (500, 2000), "中高频 2–5 kHz": (2000, 5000),
          "高频 5–8 kHz": (5000, 8000), "最高 8–10 kHz": (8000, 10500)}
SPK_RE = re.compile(r"^([甲乙])\s*[：:]\s*(.*)$")


def log_default(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- 读稿


def parse_dialog(text):
    """返回 (章列表, 提醒)。章 = {"title", "turns": [{"speaker", "text", "lines"}]}；同一人连着说的行已经并成一轮。"""
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    chapters, notes, cur = [], [], None
    for raw in body.splitlines():
        s = raw.strip()
        if not s:
            continue
        m = re.match(r"^##\s+(.+?)\s*#*$", s)
        if m and not s.startswith("###"):
            cur = {"title": m.group(1).strip(), "turns": []}
            chapters.append(cur)
            continue
        if s.startswith("#") or s.startswith(">"):
            continue
        s = s.replace("**", "").replace("__", "").replace("`", "").strip()
        if cur is None:
            cur = {"title": None, "turns": []}
            chapters.append(cur)
        m = SPK_RE.match(s)
        if m:
            spk, line = m.group(1), m.group(2).strip()
        elif cur["turns"]:
            spk, line = cur["turns"][-1]["speaker"], s
            notes.append(f"「{cur['title']}」有一行没写甲／乙，算{spk}接着说：{s[:24]}…")
        else:
            notes.append(f"「{cur['title']}」开头有一行没写甲／乙，不念：{s[:24]}…")
            continue
        if not line:
            continue
        last = cur["turns"][-1] if cur["turns"] else None
        if last and last["speaker"] == spk:
            last["text"] = tts._join_lines([last["text"], line])
            last["lines"] += 1
        else:
            cur["turns"].append({"speaker": spk, "text": line, "lines": 1})
    return [c for c in chapters if c["turns"]], notes


def load_dialog_styles(text):
    """稿末 <!-- 语气 {"章名": {"甲": "…", "乙": "…"}} --> → {章名: {"甲": …, "乙": …}}。
    某章写成一个字符串时两个人都用它；以 _ 开头的键不读。"""
    m = re.search(r"<!--\s*语气\s*(.*?)-->", text, flags=re.S)
    if not m:
        return {}
    blob = m.group(1)
    a, b = blob.find("{"), blob.rfind("}")
    if a < 0 or b < a:
        raise ValueError("稿末的 <!-- 语气 … --> 里没找到 {…}")
    try:
        d = json.loads(blob[a:b + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"稿末语气表不是合法的 JSON：{e}") from None
    out = {}
    for ch, v in d.items():
        if str(ch).startswith("_") or not v:
            continue
        if isinstance(v, str):
            out[str(ch).strip()] = {"甲": v.strip(), "乙": v.strip()}
        elif isinstance(v, dict):
            out[str(ch).strip()] = {k: str(x).strip() for k, x in v.items() if k in ("甲", "乙") and x}
    return out


# ---------------------------------------------------------------- 两个声音


_VIDEO_RULES = {}


def video_style_rules():
    """甲的语气规矩和视频旁白共用 site/tools/video3_build.py 里的一份（不另写）：GEMINI_STYLE＝工作日庚A 的基础语气
    （11-01 下午统一的那句），GEMINI_TWEAKS＝按章的微调（开场 warm、收尾 warm, a touch slower），
    STYLE_BANNED＝更亮、更高、更有活力一类的字眼。只读这三个常量；
    导入后把 sys.path 还原（video3_build 导入时会往里加 site/tools）。"""
    if not _VIDEO_RULES:
        tools = str(ROOT / "site" / "tools")
        saved = list(sys.path)
        try:
            if tools not in sys.path:
                sys.path.insert(0, tools)
            import video3_build as V          # noqa: E402
        finally:
            sys.path[:] = saved
        _VIDEO_RULES.update({"基础语气": V.GEMINI_STYLE, "禁用": re.compile(V.STYLE_BANNED, re.I),
                             "按章微调": dict(V.GEMINI_TWEAKS),
                             "来自": "site/tools/video3_build.py 的 GEMINI_STYLE、STYLE_BANNED"})
    return _VIDEO_RULES


def banned_word(style):
    """语气里有没有更亮、更高、更有活力一类的字眼（video3_build.STYLE_BANNED）；有就返回碰到的那个词。"""
    m = video_style_rules()["禁用"].search(style or "")
    return m.group(0) if m else None


def _is_chinese(style):
    """这句语气主要是中文写的吗（MiMo 的导演模式是中文；给 Gemini 的写英文）。"""
    s = re.sub(r"\s", "", style or "")
    return bool(s) and len(re.findall(HAN, s)) / len(s) > 0.3


def _family(engine):
    return "gemini" if engine in tts.GEMINI_ENGINES else engine


def _join_style(style, suffix):
    """语气后面补一句（和 video3_build 一样：前一句没有句号就补个句号再接）。"""
    style, suffix = (style or "").strip(), (suffix or "").strip()
    if not suffix:
        return style
    if not style:
        return suffix
    return f"{style}{'' if style[-1] in '.!?。！？' else '.'} {suffix}"


OLD_KEY = "旧做法（--no-palette 时才用）"     # profile"周日搭档"里各人那一节：只在不开情绪色板时才用的旧语气设置（第八轮的固定语气）


def _get(entry, key, default=None):
    """先看这一节本身，没有再看它的"旧做法"子节（2026-11-01 晚把只在 --no-palette 时用的字段挪进去了，读法不变）。"""
    if key in entry:
        return entry[key]
    return (entry.get(OLD_KEY) or {}).get(key, default)


class Speaker:
    """一位主持：引擎配置（不含语气）＋默认语气＋要补的语气句＋后期变速＋音高参考。
    entry 是 profile"周日搭档"里这个人的一节；src 是声音本身那一节（entry 写了"取自"就是那一节，没写就是 entry 自己）。"""

    def __init__(self, label, entry, src, prof=None, key=None):
        self.label, self.key = label, key or label        # key：profile 里这一节叫什么（甲、乙、甲备用、乙备用）
        self.role = entry.get("角色", "")
        self.name = entry.get("叫法") or src.get("叫法") or label
        self.host = None                                    # 第十轮：情绪色板认的主播名（Shirley／Dylan）；Gemini 和它们的 MiMo 复刻
        self.palette = False                                # make_dialog 开了色板时设成 True（只影响 describe 的说明）
        self.no_brighter = bool(_get(entry, "不许更亮更高"))
        self.fixed_style = bool(_get(entry, "语气固定用默认"))   # 甲：不用稿末语气表那一列，各章只按视频旁白的写法微调
        self.chapter_kinds = {k: v for k, v in (_get(entry, "按章微调") or {}).items() if not str(k).startswith("_")}
        base = (_get(entry, "默认语气") or "").strip()
        if _get(entry, "默认语气取自"):                     # 甲：工作日庚A 的基础语气（video3_build.GEMINI_STYLE），后面最多加一小句
            add = (_get(entry, "默认语气后面加") or "").strip()
            base = video_style_rules()["基础语气"] + (f"; {add}" if add else "")
        self.default_style = base or None
        if self.no_brighter and banned_word(self.default_style):
            raise ValueError(f"\"周日搭档\".{self.key} 的默认语气里有「{banned_word(self.default_style)}」（更亮、更高、更有活力一类），"
                             "甲和工作日是同一个声音，不许这样写")
        engine = str(src.get("引擎", ""))
        tempo = entry.get("对谈加速")
        if engine.startswith("gemini"):
            eng = "gemini-api" if "Gemini API" in engine else "gemini"
            if eng == "gemini":
                E.check_project(E.GCP_PROJECT)            # 禁用名单只在 tts_engines.py；建客户端时还会再查
            self.cfg = tts.VoiceConfig(eng, src.get("模型") or "flash", src["声音ID"], None)
            self.host = entry.get("角色名") or src.get("角色名")
            self.suffix = (src.get("每章语气后面都加这一句") or "").strip()
            if entry.get("对谈不加抬高那句"):              # 旧写法（11-01 凌晨方案 B）；现在的 profile 已不写
                self.suffix = ""
            self.tempo = None
        elif engine.startswith("mimo"):
            ref = ROOT / src["参考音"]
            if not ref.exists():
                raise FileNotFoundError(f"{self.name} 的参考音不在：{ref}")
            self.cfg = tts.VoiceConfig("mimo", model=src.get("模型"), clone_ref=str(ref))
            self.host = entry.get("角色名") or src.get("角色名")   # Shirley／Dylan 的 MiMo 复刻：色板用中文指导
            self.suffix = ""
            m = re.search(r"atempo\s*=\s*([\d.]+)", str(src.get("后期", "")))
            self.tempo = float(m.group(1)) if m else None
        else:
            raise ValueError(f"{label}（{self.name}）的引擎写的是「{engine}」，不认识")
        if tempo is not None and tempo != "":            # 对谈里另用一档（Gemini、MiMo 都认；1.0＝不变速，<1 放慢）
            tempo = float(tempo)
            if not 0.5 <= tempo <= 2.0:
                raise ValueError(f"\"周日搭档\".{self.key}.对谈加速 = {tempo}，atempo 只能 0.5–2.0")
            self.tempo = tempo
        if self.tempo is not None and abs(self.tempo - 1) < 1e-3:
            self.tempo = None
        # 音高参考：这一节自己写了"参考"就用它；否则按声音去档案里找（主声音补了抬高那句就用"带抬高那句"）
        own = entry.get("参考") if isinstance(entry.get("参考"), dict) else (src.get("参考") if src is entry else None)
        if isinstance(own, dict) and own.get("音高Hz"):
            self.ref = {"音高Hz": own.get("音高Hz"), "语速": own.get("语速字每秒"),
                        "来自": f"周日搭档.{self.key}：{own.get('来自', '')}"}
        else:
            raised = {"带抬高那句": True, "不带抬高那句": False}.get(entry.get("音高参考"), bool(self.suffix))
            self.ref = Q.reference_for(self.cfg, prof or {}, raised=raised)

    def tweak_for(self, chapter):
        """固定语气时这一章加的微调：profile"按章微调"把章名对到视频旁白的章种类（开场→open、结尾→close），
        微调的字眼取 video3_build.GEMINI_TWEAKS（开场 warm、收尾 warm, a touch slower）；其余章不加。"""
        kind = self.chapter_kinds.get((chapter or "").strip())
        return video_style_rules()["按章微调"].get(kind) if kind else None

    def resolve(self, style, chapter=None, palette=False):
        """这一轮实际发给模型的语气：(语气, 来自哪里)。
        palette=True（第十轮）且这位是 Shirley／Dylan 的 Gemini 声音：稿末语气表这一格当情绪词，用 tts.compose_style 拼
        （固定层＋色板里的词；不在色板里的换成默认词），来自哪里写成"情绪色板：…"。MiMo 备用照下面原来的规矩。
        固定语气的人（甲）：不看稿末语气表，用默认语气，开场、结尾前面加视频旁白那样的微调（"warm; …"）。
        其余的人：稿末语气表那句写给另一种引擎的（Gemini 收英文、MiMo 收中文导演模式），
        或者有更亮、更高一类的字眼（不许更亮更高的人），就换成默认语气。最后补上要补的那句（甲：抬高音区）。"""
        if palette and self.host:
            s, rec = tts.compose_style(self.host, style, chapter, dialog=True,
                                       mimo="对谈" if self.cfg.engine == "mimo" else None)
            self.last_rec = rec
            return s, "情绪色板：" + rec["情绪词"] + ("（" + rec["来自"] + "）" if rec["来自"] != "稿子" else "")
        if self.fixed_style and self.default_style:
            tw = self.tweak_for(chapter)
            s = f"{tw}; {self.default_style}" if tw else self.default_style
            why = "固定默认语气" + (f"（这一章加「{tw}」）" if tw else "") + ("，稿末语气表里那句不用" if (style or "").strip() else "")
            if self.no_brighter and banned_word(s):
                raise ValueError(f"\"周日搭档\".{self.key} 的固定语气里有「{banned_word(s)}」，不许这样写")
            return _join_style(s, self.suffix), why
        s, why = (style or "").strip(), "稿末语气表"
        if s and _is_chinese(s) != (self.cfg.engine == "mimo"):
            s, why = "", f"profile 默认语气（稿末那句是写给{'Gemini' if self.cfg.engine == 'mimo' else 'MiMo'}的）"
        if s and self.no_brighter and banned_word(s):
            s, why = "", f"profile 默认语气（稿末那句有「{banned_word(s)}」，更亮、更高、更有活力一类，不用）"
        if not s:
            s = self.default_style or ""
            why = why if why != "稿末语气表" else ("profile 默认语气" if s else "无")
        return (_join_style(s, self.suffix) or None), why

    def style_for(self, style, chapter=None):
        return self.resolve(style, chapter)[0]

    def cfg_for(self, style, chapter=None):
        return self.cfg.with_style(self.style_for(style, chapter))

    def voice_id(self):
        return self.cfg.voice or (Path(self.cfg.clone_ref).name if self.cfg.clone_ref else None)

    def describe(self):
        d = {"叫法": self.name, "角色": self.role, "profile 里的一节": f"周日搭档.{self.key}", **self.cfg.describe()}
        d.pop("style", None)
        if self.palette and self.host:                  # 开了色板：每轮按稿末语气表的情绪词拼（旧的固定语气不用）
            d["语气"] = ("按情绪色板：tts.compose_style（" + ("MiMo 中文指导，对谈模板" if self.cfg.engine == "mimo"
                                                         else "固定层＋这一轮的情绪词") + "），每轮的结果见 qc.json\"各轮.语气记录\"")
            if self.suffix:
                d["每轮语气后面补的一句"] = self.suffix + "（色板里标了不补的词、章除外）"
            d["后期"] = f"atempo={self.tempo}（只改快慢，不改音高）" if self.tempo else "不变速"
            if self.ref:
                d["音高参考"] = self.ref
            return d
        if self.default_style:
            d["默认语气"] = self.default_style
        if self.fixed_style:
            d["语气"] = "固定用默认语气（稿末语气表里这一列不用）" + (
                "；按章微调：" + "、".join(f"{k}加「{self.tweak_for(k)}」" for k in self.chapter_kinds) if self.chapter_kinds else "")
        if self.suffix:
            d["每轮语气后面补的一句"] = self.suffix
        d["后期"] = f"atempo={self.tempo}（只改快慢，不改音高）" if self.tempo else "不变速"
        if self.ref:
            d["音高参考"] = self.ref
        return d


def _speaker_from(prof, pair, label, key):
    entry = pair.get(key)
    if not entry:
        return None
    if entry.get("取自"):
        src = prof.get(entry["取自"])
        if not src:
            raise ValueError(f"\"周日搭档\".{key} 说取自「{entry['取自']}」，profile 里没有这一节")
    else:
        src = entry                                   # 声音写在这一节自己里面（男声03、男声06）
    return Speaker(label, entry, src, prof, key)


def load_pairing(path=PROFILE):
    prof = json.loads(Path(path).read_text(encoding="utf-8"))
    pair = prof.get("周日搭档")
    if not pair:
        raise ValueError(f"{path} 里还没有\"周日搭档\"一节")
    speakers = {label: _speaker_from(prof, pair, label, label) for label in ("甲", "乙")}
    gaps = dict(GAPS, **{k: v for k, v in (pair.get("换人停顿秒") or {}).items() if not k.startswith("_")})
    gaps["_句中"] = dict(PAUSE, **{k: v for k, v in (pair.get("句中停顿秒") or {}).items() if not k.startswith("_")})
    look = json.loads(json.dumps(LOOK))
    for k, v in (pair.get("统一音色") or {}).items():
        if k.startswith("_"):
            continue
        look[k] = dict(look.get(k, {}), **v) if isinstance(v, dict) else v

    def no_notes(d):
        return {k: no_notes(v) if isinstance(v, dict) else v for k, v in d.items() if not str(k).startswith("_")}

    look["_声音包调整"] = no_notes(pair.get("声音包调整") or {}) or None    # 交给 podcast_mix.mix_package(overrides=…)
    return speakers, gaps, look


def load_backups(path=PROFILE):
    """Gemini 出错时各自改用谁：{"甲": profile"甲备用"（取自"备用声音"）, "乙": profile"乙备用"}；没写的是 None。"""
    prof = json.loads(Path(path).read_text(encoding="utf-8"))
    pair = prof.get("周日搭档") or {}
    return {label: _speaker_from(prof, pair, label, f"{label}备用") for label in ("甲", "乙")}


def b_quieter_lu(path=PROFILE):
    pair = json.loads(Path(path).read_text(encoding="utf-8")).get("周日搭档") or {}
    v = pair.get("乙比甲低LU")
    return float(v) if v is not None else B_QUIETER_LU


# ---------------------------------------------------------------- 分轮与停顿


def plan_units(chapters, speakers, styles, palette=False):
    """每次请求一个单位：一轮，或长轮切开后的一段。palette：第十轮情绪色板（见 Speaker.resolve）。"""
    units = []
    for ci, ch in enumerate(chapters):
        st = styles.get(ch["title"], {})
        for ti, turn in enumerate(ch["turns"]):
            sp = speakers[turn["speaker"]]
            sp.last_rec = None
            style, why = sp.resolve(st.get(turn["speaker"]), ch["title"], palette=palette)
            rec = getattr(sp, "last_rec", None)
            est = tts.est_seconds(turn["text"])
            parts = [turn["text"]]
            if est > MAX_TURN_S:
                sents = tts._split_sentences(turn["text"])
                parts = ["".join(g) for g in tts._balanced(sents, math.ceil(est / MAX_TURN_S))]
            for pi, p in enumerate(parts):
                units.append({"index": len(units), "chapter": ci, "chapter_title": ch["title"], "turn": ti,
                              "part": pi, "speaker": turn["speaker"], "text": p, "cfg": sp.cfg.with_style(style),
                              "style_from": why, "est": round(tts.est_seconds(p), 1),
                              **({"style_rec": rec} if rec else {})})
    return units


def is_question(text):
    s = re.sub(r"[”’\"'）)」』\s]+$", "", tts.spoken(text))
    return s.endswith(("？", "?"))


def gap_after(prev, nxt, gaps, prev_secs=None, next_secs=None):
    """prev 说完到 nxt 开口之间留多少秒（只看说话的部分，不算音频首尾的静音）。返回 (秒数, 理由)。"""
    ps = prev_secs if prev_secs is not None else prev["est"]
    ns = next_secs if next_secs is not None else nxt["est"]
    if prev["speaker"] == nxt["speaker"]:
        why = "同一人接着说"
    elif is_question(prev["text"]) and ps <= QUICK_QUESTION_S:
        why = "快问之后"
    elif is_question(prev["text"]):
        why = "提问之后"
    elif ns <= SHORT_REPLY_S:
        why = "短回应之前"
    elif ps >= LONG_TURN_S:
        why = "长段之后"
    else:
        why = "一般"
    h = int(hashlib.sha1((prev["text"] + "|" + nxt["text"]).encode("utf-8")).hexdigest()[:4], 16) / 65535
    g = gaps[why] + (2 * h - 1) * gaps["浮动"]      # 每处差一点点，免得停顿整齐得像节拍器；同样的稿子每次一样
    return round(min(gaps["最长"], max(gaps["最短"], g)), 3), why


# ---------------------------------------------------------------- 配音与对稿


def _est_cost(cfg, unit):
    """预算检查用的估计费用。音频秒数按估计时长算（11-01 整集实测：庚A 实际只有估计的 0.88），
    不再像 tts.py 那样乘 1.4，免得一集还没开始就被预算拦下；实际花费照接口报的记账。"""
    if cfg.engine not in tts.GEMINI_ENGINES:
        return 0.0
    return E.gemini_cost(cfg.model, len(unit["text"]) + len(cfg.style or "") // 3 + 40,
                         unit["est"] * E.AUDIO_TOKENS_PER_SEC)


class SynthFailed(E.TTSError):
    """synth_batch 里有几条出错（别的条照样做完、存进了缓存）。speakers：出错的是谁（甲／乙）；engines：出错的引擎。
    make_dialog 据此把出错的那位换成备用声音。"""

    def __init__(self, msg, speakers=(), engines=()):
        super().__init__(msg)
        self.speakers, self.engines = set(speakers), set(engines)


class _Run:
    """一次运行里共享的东西：引擎（用到才建）、花费账、锁、这次新配的条目（换备用声音重排后，缓存里刚配的也算"本次新调用"）。"""

    def __init__(self, ledger, fresh, log):
        self.ledger, self.fresh, self.log = ledger, fresh, log
        self.engines, self.lock = {}, threading.Lock()
        self.new_keys = set()

    def engine(self, cfg):
        with self.lock:
            if cfg.engine not in self.engines:
                if cfg.engine == "mimo":
                    state = keys.load_local_env()         # 只经 keys.py 读 MiMo 的两个变量进环境，不输出值
                    if not all(state.values()):
                        raise E.TTSError(f"MiMo 变量不全：{state}")
                    self.engines["mimo"] = E.MiMo()
                elif cfg.engine == "gemini":
                    g = E.Gemini()
                    g._token()                             # 先在主线程取一次令牌，几条请求同时发时不用各取各的
                    self.engines["gemini"] = g
                else:
                    self.engines[cfg.engine] = E.GeminiAPI()
            return self.engines[cfg.engine]


def _paths(key):
    return CACHE / "chunks" / f"{key}.wav", CACHE / "chunks" / f"{key}.json"


def _synth_one(run, unit, take):
    cfg = unit["cfg"]
    key = tts._key(cfg, unit["text"], take)
    raw, meta_p = _paths(key)
    if raw.exists() and meta_p.exists() and (not run.fresh or key in getattr(run, "new_keys", ())):
        raw.touch()                                        # 记下"最近用过"，免得被 tts.prune_cache 清掉
        return {"key": key, "raw": raw, "take": take,
                "usage": dict(json.loads(meta_p.read_text(encoding="utf-8")),
                              本次新调用=key in getattr(run, "new_keys", ()))}
    wav, usage = tts._synth(run.engine(cfg), cfg, unit["text"])
    usage["生成于"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    raw.write_bytes(wav)
    meta_p.write_text(json.dumps(usage, ensure_ascii=False, indent=1), encoding="utf-8")
    with run.lock:
        run.ledger.add(usage.get("cost_usd"))
        if hasattr(run, "new_keys"):
            run.new_keys.add(key)
    return {"key": key, "raw": raw, "take": take, "usage": dict(usage, 本次新调用=True)}


def synth_batch(run, jobs):
    """jobs：[(unit, 第几条)]。同样的文字＋配置只配一次。返回 {(unit 序号, 第几条): 记录}。"""
    by_key = {}
    for u, t in jobs:
        by_key.setdefault(tts._key(u["cfg"], u["text"], t), (u, t))
    todo = [(k, u, t) for k, (u, t) in by_key.items()
            if (run.fresh and k not in getattr(run, "new_keys", ())) or not all(p.exists() for p in _paths(k))]
    est = sum(_est_cost(u["cfg"], u) for _, u, _ in todo)
    if est:
        run.ledger.check(est, f"这批 {len(todo)} 条 ")
    if todo:
        run.log(f"  要新配 {len(todo)} 条（其余 {len(by_key) - len(todo)} 条用缓存），Gemini 估计 ${est:.4f}")
    sems = {e: threading.Semaphore(n) for e, n in WORKERS.items()}

    def work(u, t):
        with sems[u["cfg"].engine]:
            return _synth_one(run, u, t)

    done, errors, who, fatal = {}, [], [], None
    with ThreadPoolExecutor(max_workers=sum(WORKERS.values())) as ex:
        futs = {ex.submit(work, u, t): (k, u, t) for k, (u, t) in by_key.items()}
        for f in as_completed(futs):
            k, u, t = futs[f]
            try:
                rec = f.result()
            except Exception as e:                       # 别的条照样做完（存进缓存），最后再报错
                errors.append(keys.hide(f"{u['speaker']} 第{u['index'] + 1}轮：{type(e).__name__}: {e}"))
                if isinstance(e, E.TTSError):            # 引擎出错（重试后仍失败）：可以换备用声音
                    who.append((u["speaker"], u["cfg"].engine))
                elif fatal is None:                      # 禁用项目、读不到密钥、程序错：不换备用，原样报
                    fatal = e
                continue
            done[k] = rec
            us = rec["usage"]
            if us.get("本次新调用"):
                run.log(f"    {u['speaker']} 第{u['index'] + 1}轮【{u['chapter_title']}】第{t + 1}条："
                        f"{us['seconds_audio']:.1f} 秒，用时 {us['seconds_wall']:.0f} 秒"
                        + (f"，约 ${us['cost_usd']:.4f}" if u["cfg"].engine in tts.GEMINI_ENGINES else ""))
    if fatal is not None:
        raise fatal
    if errors:
        raise SynthFailed("；".join(errors[:3]) + (f"（共 {len(errors)} 条出错）" if len(errors) > 3 else ""),
                          speakers=[s for s, _ in who], engines=[e for _, e in who])
    return {(u["index"], t): done[tts._key(u["cfg"], u["text"], t)] for u, t in jobs}


def judge(unit, hyp, seconds):
    """对稿：tts_qc.check 的结果，外加两处对谈稿的调整——短句按拼音判断；时长差不到 1.5 秒不算异常
    （音频首尾自带零点几秒静音，短句的时长比很容易超出范围）。"""
    res = Q.check(tts.spoken(unit["text"]), hyp)
    reasons = list(res["原因"])
    per = res.get("拼音错误率")
    if res["原稿字数"] <= SHORT_TOKENS and per is not None and per < Q.CER_LIMIT:
        reasons = [r for r in reasons if not r.startswith("字错率")]
    ratio = seconds / unit["est"] if unit["est"] else None
    if ratio and not Q.DURATION_RANGE[0] <= ratio <= Q.DURATION_RANGE[1] and abs(seconds - unit["est"]) > 1.5:
        reasons.append(f"时长异常：实际 {seconds:.1f} 秒，估计 {unit['est']:.1f} 秒")
    res.update({"原因": reasons, "需重录": bool(reasons), "时长比": round(ratio, 2) if ratio else None})
    return res


def qc_batch(run, recs, units_by_index):
    """recs：{(unit 序号, 第几条): 记录}。没转写过的一次进程转完，结果按文件缓存（和 tts.py 同一个位置）。"""
    need, hyps = [], {}
    for rec in recs.values():
        wdir = CACHE / "whisper" / rec["key"]
        done = wdir / f"{rec['raw'].stem}_whisper.json"
        if not rec["usage"].get("本次新调用") and done.exists():
            hyps[rec["key"]] = (json.loads(done.read_text(encoding="utf-8")).get("text") or "").strip()
            done.touch()
        elif rec["key"] not in {k for k, _ in need}:
            need.append((rec["key"], (rec["raw"], wdir)))
    if need:
        run.log(f"  Whisper 对稿 {len(need)} 条…")
        got = Q.transcribe_many([x for _, x in need])
        for k, (raw, _) in need:
            hyps[k] = got[str(raw)]
    for (ui, t), rec in recs.items():
        u = units_by_index[ui]
        rec["qc"] = judge(u, hyps[rec["key"]], rec["usage"]["seconds_audio"])


# ---------------------------------------------------------------- 后期


def decode(raw, tempo=None):
    """任意音频 → 24 kHz 单声道 float64；tempo 给了就用 atempo 加快（不改音高）。"""
    af = f"atempo={tempo:.4f}" if tempo and abs(tempo - 1) > 1e-3 else "anull"
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(raw), "-af", af, "-f", "f32le",
                        "-ac", "1", "-ar", str(SR), "-"], capture_output=True)
    if r.returncode:
        raise RuntimeError(f"读不了 {raw}：{r.stderr.decode()[-300:]}")
    return np.frombuffer(r.stdout, dtype=np.float32).astype(np.float64)


def trim(x, thresh_db=-50.0, head=0.02, tail=0.05, fade=0.008):
    """去首尾静音（10 毫秒一窗，低于 −50 dBFS 算静音），首留 20 毫秒、尾留 50 毫秒，两头各 8 毫秒淡入淡出。
    返回 (音频, 开头留的秒数, 结尾留的秒数, 中间最长的停顿秒数)。"""
    win = int(SR * 0.01)
    m = len(x) // win
    if m == 0:
        return x, 0.0, 0.0, 0.0
    db = 20 * np.log10(np.sqrt((x[:m * win].reshape(m, win) ** 2).mean(axis=1)) + 1e-9)
    loud = np.flatnonzero(db > thresh_db)
    if not len(loud):
        return x, 0.0, 0.0, 0.0
    a = max(0, loud[0] * win - int(head * SR))
    b = min(len(x), (loud[-1] + 1) * win + int(tail * SR))
    y = x[a:b].copy()
    k = min(len(y) // 2, int(fade * SR))
    if k:
        w = np.sin(np.linspace(0, np.pi / 2, k)) ** 2
        y[:k] *= w
        y[-k:] *= w[::-1]
    quiet = np.diff(loud) - 1                          # 说话中间连着几窗是静音
    longest = float(quiet.max()) * 0.01 if len(quiet) else 0.0
    return y, (loud[0] * win - a) / SR, (b - (loud[-1] + 1) * win) / SR, round(longest, 2)


def cap_pauses(y, over, to, thresh_db=-50.0):
    """一轮里面超过 over 秒的静音缩到 to 秒（从静音中间剪掉，接口处 10 毫秒交叉淡化）。返回 (音频, 缩了哪几处 [(原秒数, 位置秒)])。"""
    if not over or to >= over:
        return y, []
    win = int(SR * 0.01)
    m = len(y) // win
    db = 20 * np.log10(np.sqrt((y[:m * win].reshape(m, win) ** 2).mean(axis=1)) + 1e-9)
    loud = np.flatnonzero(db > thresh_db)
    cuts = []
    for i, j in zip(loud[:-1], loud[1:]):
        n = j - i - 1                                  # 两段声音之间有几窗静音
        if n * 0.01 > over:
            mid = (i + 1 + j) * win // 2
            drop = int(round((n * 0.01 - to) * SR))
            cuts.append((mid - drop // 2, mid - drop // 2 + drop, round(n * 0.01, 2)))
    if not cuts:
        return y, []
    out, pos, x = [], 0, int(0.01 * SR)
    for a, b, _ in cuts:
        out.append(y[pos:a])
        pos = b
    out.append(y[pos:])
    z = out[0]
    for seg in out[1:]:                                # 交叉淡化，免得剪口有咔哒声
        k = min(x, len(z), len(seg))
        w = np.linspace(0, 1, k)
        z = np.concatenate([z[:len(z) - k], z[len(z) - k:] * (1 - w) + seg[:k] * w, seg[k:]])
    return z, [(s, round(a / SR, 2)) for a, _, s in cuts]


def lufs(x):
    return M.lufs(x, sr=SR) if len(x) else -70.0


def band_levels(clips):
    """几段音频合起来的平均频谱，按三分之一倍频程（BANDS）给出各频带的 dB。"""
    from scipy.signal import welch
    x = np.concatenate(clips) if clips else np.zeros(SR)
    f, p = welch(x, fs=SR, nperseg=2048, noverlap=1024)
    out = []
    for fc in BANDS:
        sel = (f >= fc / 2 ** (1 / 6)) & (f < fc * 2 ** (1 / 6))
        out.append(10 * np.log10(p[sel].mean() + 1e-20))
    return np.array(out)


def tone_summary(ref_db, src_db, lo=200, hi=8000):
    """src 比 ref 在各频段亮多少 dB（先扣掉 lo–hi 之间的平均差，只看形状、不看总响度）。"""
    d = src_db - ref_db
    k = (BANDS >= lo) & (BANDS <= hi)
    d = d - d[k].mean()
    return {name: round(float(d[(BANDS >= a) & (BANDS < b)].mean()), 1) for name, (a, b) in RANGES.items()}


def match_eq(ref_db, src_db, amount, max_db, lo=200, hi=8000, sigma_bands=1.5):
    """算一条往 ref 靠的均衡曲线：lo–hi 之间各频带的差值（扣掉平均，只看形状）在频带之间做高斯平滑
    （约半个八度宽，只要大的走势，不追每个共振峰——两个人的共振峰本来就不同），乘以强度、限在 ±max_db；
    lo 以下、hi 以上保持边上的值。返回 (FIR 滤波器, 各频带增益 dB)。"""
    from scipy.signal import firwin2
    k = np.flatnonzero((BANDS >= lo) & (BANDS <= hi))
    d = ref_db[k] - src_db[k]
    d = d - d.mean()
    idx = np.arange(len(k))
    w = np.exp(-0.5 * ((idx[:, None] - idx[None, :]) / sigma_bands) ** 2)
    sm = np.clip(amount * (w @ d) / w.sum(axis=1), -max_db, max_db)
    xs = np.log2(BANDS[k])

    def curve(freqs):
        return np.interp(np.log2(np.clip(freqs, BANDS[k[0]], BANDS[k[-1]])), xs, sm)

    freqs = np.linspace(0, SR / 2, 1025)
    h = firwin2(2049, freqs, 10 ** (curve(freqs) / 20), fs=SR)
    return h, {f"{fc:.0f}": round(float(g), 1) for fc, g in zip(BANDS, curve(BANDS))}


def apply_fir(x, h):
    from scipy.signal import fftconvolve
    return fftconvolve(x, h, mode="same")              # 对称的 FIR，mode=same 正好抵掉延迟


def room_ir(rt60, seed=7):
    """一间小录音室的脉冲响应（只有反射声，不含直达声）：几条早期反射＋按 rt60 衰减、偏暗的尾巴，能量归一。"""
    from scipy.signal import butter, sosfilt
    rng = np.random.default_rng(seed)
    n = int(SR * min(1.0, rt60 * 1.3))
    h = np.zeros(n)
    for d, g in ((0.0031, 0.8), (0.0053, -0.7), (0.0079, 0.6), (0.0112, -0.5), (0.0146, 0.42), (0.0190, -0.33)):
        h[int(d * SR)] += g
    t = np.arange(n) / SR
    tail = rng.standard_normal(n) * np.exp(-6.91 * t / rt60)
    tail[:int(0.012 * SR)] = 0
    tail = sosfilt(butter(2, [200, 5000], btype="band", fs=SR, output="sos"), tail)
    h += tail * np.sqrt(1.5 * (h ** 2).sum() / ((tail ** 2).sum() + 1e-20))
    return h / np.sqrt((h ** 2).sum())


def add_room(x, room):
    from scipy.signal import fftconvolve
    if not room or not room.get("湿声比干声低dB"):
        return x
    wet = fftconvolve(x, room_ir(float(room.get("混响时间秒", 0.25))))[:len(x)]
    return x + wet * 10 ** (-float(room["湿声比干声低dB"]) / 20)


def write_f32(x, path):
    raw = Path(path).with_suffix(".f32")
    raw.write_bytes(np.ascontiguousarray(x, dtype=np.float32).tobytes())
    tts._ffmpeg(["-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", str(raw), "-c:a", "pcm_f32le", str(path)])
    raw.unlink(missing_ok=True)


def true_peak(x, over=8):
    """真峰值（8 倍过采样估：24 kHz → 192 kHz，和 ffmpeg ebur128 量真峰值的倍数一样）：返回每个采样点附近的最大绝对值。"""
    from scipy.signal import resample_poly
    up = np.abs(resample_poly(x, over, 1))[:len(x) * over]
    if len(up) < len(x) * over:
        up = np.pad(up, (0, len(x) * over - len(up)))
    return np.maximum(up.reshape(-1, over).max(axis=1), np.abs(x))


def peak_limit(x, ceiling_db=TP_CEILING_DB, ramp=LIMIT_RAMP_S, hold=LIMIT_HOLD_S):
    """只削尖峰的真峰值限制器（带预读）：哪个点的真峰值会超过 ceiling_db，就只在它附近把音量压到刚好不超——
    提前 ramp 秒开始压（预读），压完至少保持 hold 秒，再用 ramp 秒回来；其余地方一点不动。不是压缩：整体响度、
    两个人的响度差几乎不变（每次都量，记进 qc.json）。做法：每点需要的增益 → 在 [n − hold, n + ramp] 里取最小 →
    再取过去 ramp 秒的平均（变成斜坡，且每个尖峰处一定压够）。返回 (音频, 记录)。"""
    ceil = 10 ** (ceiling_db / 20)
    r, h = max(1, int(ramp * SR)), max(0, int(hold * SR))
    y, total = x, np.ones(len(x))
    for _ in range(3):                                  # 过采样估的峰和压完再量会差一点，最多补两遍
        need = np.minimum(1.0, ceil / np.maximum(true_peak(y), 1e-12))
        if need.min() >= 0.9999:
            break
        env = _past_mean(_window_min(need, h, r), r)
        y = y * env
        total *= env
    info = {"压了的时间占比": round(float((total < 0.9999).mean()), 4),
            "压了 1 dB 以上的时间占比": round(float((total < 10 ** (-1 / 20)).mean()), 4),
            "最多压dB": round(float(-20 * np.log10(total.min())), 2) if len(total) else 0.0,
            "削完真峰值dBTP（8 倍过采样估）": round(float(20 * np.log10(true_peak(y).max() + 1e-12)), 2)}
    return y, info


def _window_min(a, back, fwd):
    """out[n] = min(a[n − back : n + fwd + 1])，两头之外当 1。"""
    from scipy.ndimage import minimum_filter1d
    size = back + fwd + 1
    return minimum_filter1d(a, size=size, origin=back - size // 2, mode="constant", cval=1.0)


def _past_mean(a, n):
    """out[i] = mean(a[i − n + 1 : i + 1])，开头之前当 1。"""
    c = np.cumsum(np.concatenate([np.ones(n), a]))
    return (c[n:] - c[:-n]) / n


def finish_chapter(x, work, dst, ceiling_db=TP_CEILING_DB):
    """一章统一到 −16 LUFS（2026-11-01 改）：先量整章响度，整章乘一个固定增益（线性）到 −16 LUFS；
    真峰值会超过 ceiling_db（−1.7 dBTP）的那几个尖峰，用 peak_limit 只在尖峰附近削掉（带预读，几毫秒的事），
    不压缩、不整章降音量。削完再量一次，差零点几就再补一个固定增益。写成 24 kHz 单声道 16 位。
    为什么这样：①loudnorm 在短文件上会改用"动态"方式，把乙比甲低的那点抹平（第七轮）；②只乘固定增益、峰值超了就整章降，
    Gemini 原声峰值高（乘到 −16 LUFS 会到 +2.7 dBFS），整章得降 4 dB，后面 podcast_mix 整集统一响度要补回 4 dB，
    峰值又超，只好走动态方式（第八轮第一版）。现在章已经是 −16 LUFS、真峰值在 −1.5 以下，整集那一步只用线性。
    work 参数不再用，留着是为了调用方不用改。"""
    before = lufs(x)
    g = TARGET_LUFS - before
    lim = {}
    for _ in range(3):                               # 削峰让响度掉了一点：把固定增益补一点再从头削，最多三遍
        y, lim = peak_limit(x * 10 ** (g / 20), ceiling_db)
        d = TARGET_LUFS - lufs(y)
        if abs(d) < 0.03:
            break
        g += d
    y = np.clip(y, -1, 1)
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.round(y * 32767).astype(np.int16).tobytes())
    return {"处理前": round(float(before), 2), "处理后": round(float(lufs(y)), 2),
            "方式": "整章乘固定增益到 −16 LUFS，再只削尖峰（真峰值限制器，限在 %.1f dBTP）" % ceiling_db,
            "增益dB": round(float(g), 2), "削峰": lim,
            "峰值dBFS": round(float(20 * np.log10(float(np.abs(y).max()) + 1e-12)), 2) if len(y) else None}


def load_style_override(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: {kk: vv for kk, vv in v.items() if kk in ("甲", "乙")} for k, v in d.items()
            if not str(k).startswith("_") and isinstance(v, dict)}


def merge_styles(styles, override, log=log_default):
    """语气调整盖在稿末语气表上：只换写到的章、写到的人，其余照稿子。"""
    out = {k: dict(v) for k, v in styles.items()}
    for ch, v in override.items():
        for spk, st in v.items():
            log(f"  语气调整：「{ch}」{spk} 改用 {st[:50]}…")
            out.setdefault(ch, {})[spk] = st
    return out


def f0_track(x, fmin=70, fmax=420, frame=0.04, hop=0.02, thresh=0.15):
    """音高（Hz，每 20 毫秒一个，不发声的帧是 nan）。YIN 算法（de Cheveigné & Kawahara 2002），
    和 配音测试/第四轮 的 yin_f0 同样的做法和参数，只是差分函数用 FFT 一次算整批帧，快几十倍。"""
    W, H = int(frame * SR), int(hop * SR)
    tmin, tmax = int(SR / fmax), int(SR / fmin)
    n = (len(x) - W - tmax) // H
    if n <= 0:
        return np.array([])
    out = np.full(n, np.nan)
    starts = np.arange(n) * H
    rms_all = np.sqrt(np.array([(x[s:s + W] ** 2).mean() for s in starts]))
    gate = rms_all.max() * 10 ** (-35 / 20)
    L = 1 << int(np.ceil(np.log2(2 * W + tmax)))
    lag = np.arange(1, tmax + 1)
    for a0 in range(0, n, 1024):
        idx = np.arange(a0, min(n, a0 + 1024))
        idx = idx[rms_all[idx] > gate]
        if not len(idx):
            continue
        seg = x[starts[idx][:, None] + np.arange(W + tmax)]
        a = seg[:, :W]
        corr = np.fft.irfft(np.fft.rfft(a[:, ::-1], L) * np.fft.rfft(seg, L), L)[:, W - 1:W + tmax]
        cs = np.concatenate([np.zeros((len(idx), 1)), np.cumsum(seg ** 2, axis=1)], axis=1)
        d = (a ** 2).sum(axis=1)[:, None] + (cs[:, W:W + tmax + 1] - cs[:, :tmax + 1]) - 2 * corr
        d = np.maximum(d, 0)
        cm = np.ones_like(d)
        cm[:, 1:] = d[:, 1:] * lag / np.maximum(np.cumsum(d[:, 1:], axis=1), 1e-12)
        below = cm[:, tmin:] < thresh
        has = below.any(axis=1)
        t = np.where(has, below.argmax(axis=1) + tmin, 0)
        for _ in range(40):                            # 顺着往下走到这个谷的底
            nxt = np.minimum(t + 1, tmax)
            go = has & (t + 1 <= tmax) & (cm[np.arange(len(t)), nxt] < cm[np.arange(len(t)), t])
            if not go.any():
                break
            t = np.where(go, t + 1, t)
        ok = has & (t >= 1) & (t < tmax)
        r = np.arange(len(t))[ok]
        tt = t[ok]
        c0, c1, c2 = cm[r, tt - 1], cm[r, tt], cm[r, tt + 1]
        den = c0 - 2 * c1 + c2
        tf = tt + np.where(den != 0, 0.5 * (c0 - c2) / np.where(den != 0, den, 1), 0)
        out[idx[ok]] = SR / tf
    return out


def articulation(y):
    """(整体语速, 去掉停顿的语速)：字或英文词／秒；超过 150 毫秒、低于 −45 dBFS 的静音算停顿。"""
    win = int(SR * 0.01)
    m = len(y) // win
    if not m:
        return None, None
    loud = 20 * np.log10(np.sqrt((y[:m * win].reshape(m, win) ** 2).mean(axis=1)) + 1e-9) > -45
    edges = np.flatnonzero(np.diff(np.concatenate([[1], loud.astype(int), [1]])))
    runs = edges[1::2] - edges[::2]                    # 每段连续静音有几窗
    pause = runs[runs >= 15].sum() * 0.01
    return len(y) / SR, len(y) / SR - pause


PITCH_MIN_SEMITONES = 2.0      # 同一章里两人音高中位数差不到这么多个半音，就提醒（听众可能分不清谁在说）
RATE_MAX_DIFF = 0.08           # 两人语速（去掉停顿）差超过这么多，就提醒


def voice_checks(units, rows, chap_arrays, chapters):
    """量每章两人的音高、两人的语速；音高太近、语速差太多时给出提醒。"""
    per = {}
    tok, tot, art = {"甲": 0, "乙": 0}, {"甲": 0.0, "乙": 0.0}, {"甲": 0.0, "乙": 0.0}
    for u in units:
        r = rows[u["index"]]
        y = chap_arrays[u["chapter"]][int(r["章内开始秒"] * SR):int(r["章内结束秒"] * SR)]
        f = f0_track(y)
        per.setdefault(u["chapter_title"], {}).setdefault(u["speaker"], []).append(f[~np.isnan(f)])
        n = len(Q.tokens(tts.spoken(u["text"])))
        a, b = articulation(y)
        if a:
            tok[u["speaker"]] += n
            tot[u["speaker"]] += a
            art[u["speaker"]] += b
    warnings, chap_pitch = [], {}
    all_f = {"甲": [], "乙": []}
    for ch in [c["title"] for c in chapters]:
        med = {}
        for s, fs in per.get(ch, {}).items():
            v = np.concatenate(fs) if fs else np.array([])
            all_f[s].append(v)
            med[s] = round(float(np.median(v)), 1) if len(v) else None
        row = {f"{s}Hz": med.get(s) for s in ("甲", "乙")}
        if med.get("甲") and med.get("乙"):
            st = 12 * np.log2(med["乙"] / med["甲"])
            row["差几个半音"] = round(float(st), 1)
            if abs(st) < PITCH_MIN_SEMITONES:
                warnings.append(f"「{ch}」两人音高只差 {abs(st):.1f} 个半音（甲 {med['甲']:.0f} Hz、乙 {med['乙']:.0f} Hz），"
                                f"听众可能分不清谁在说；先看甲这一章的语气有没有要更亮、更高的声音——不过同一句每次合成音高能差几十赫兹"
                                f"（11-01 实测），改语气不一定压得下来")
        chap_pitch[ch] = row
    whole = {s: round(float(np.median(np.concatenate(v))), 1) for s, v in all_f.items() if v and len(np.concatenate(v))}
    rate = {s: {"整体（字／秒）": round(tok[s] / tot[s], 2), "去掉停顿（字／秒）": round(tok[s] / art[s], 2)}
            for s in tok if tot[s] and art[s]}
    if len(rate) == 2:
        ratio = rate["甲"]["去掉停顿（字／秒）"] / rate["乙"]["去掉停顿（字／秒）"]
        rate["甲比乙快"] = f"{(ratio - 1) * 100:+.0f}%"
        if abs(ratio - 1) > RATE_MAX_DIFF:
            warnings.append(f"两人语速（去掉停顿）差 {(ratio - 1) * 100:+.0f}%（甲 {rate['甲']['去掉停顿（字／秒）']}、"
                            f"乙 {rate['乙']['去掉停顿（字／秒）']} 字／秒）；乙的对谈加速可以改成约现在的 {ratio:.2f} 倍"
                            "（profile\"周日搭档\".乙.对谈加速，后期做的，重跑不花钱）")
    return {"各章": chap_pitch, "全集Hz": whole}, rate, warnings


def read_wav(path):
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768


# ---------------------------------------------------------------- 主流程


def make_dialog(script, out_dir, profile=PROFILE, title=None, ledger=None, fresh=False, qc=True,
                retakes=RETAKES, package="v3", reviewed=False, bitrate=tts.BITRATE_KBPS, log=log_default,
                speech_dir=None, style_override=None, pitch_gate=True, fallback=True, use_backup=(), timbre=True,
                palette=False, level=False, tempo=False, duration=None):
    """script 可以是文件路径或稿子全文。返回摘要（各项也写进人声目录和 out_dir 的几个 json）。
    package=None 时只出人声，不混音。speech_dir：人声放哪儿，默认 out_dir/人声；
    正式一期按 build_v3.py 的习惯和混音目录并排放（如 05_配音/对谈_v3 ＋ 05_配音/对谈_v3_带音效）。
    pitch_gate（默认开）：每轮配完量音高中位数，和这个说话人自己的参考音高比（Speaker.ref：profile 里这个人那一节写了
    "参考"就用它，否则用他"取自"的那个声音的"参考"；甲补了抬高那句，用"带抬高那句"），差超过"音高把关"的允许偏差就重录，
    最多再录几次，挑最接近的；有声不到 1.2 秒的短句不判。为音高重录受预算约束：预算不够的那几轮就不再录（不报错），记进 qc.json。
    MiMo 的轮另有"跑偏"把关（MIMO_ODD，免费，和 pitch_gate 开不开无关）。
    timbre（默认开）：音色把关（pipeline/voice_print.py）：每个说话人对自己的档案，每条判段（量加速、均衡、混响之前的原声），
    低于重录线就重录（和音高共用"最多再录"和预算）；每章对每人判一次、收尾每人判一次整期，只提醒。档案里没有的声音不把关。
    fallback（默认开）：某位的 Gemini 请求出错（重试后仍失败），这一位整期换成 profile 里的备用声音（乙→乙备用，甲→甲备用），
    重新排一遍（已经配好的条目走缓存，不重复花钱）。use_backup：一开始就让这几位（"甲""乙"）用备用声音。
    第十轮（2026-11-01 晚）加的四样，Python 里默认关（命令行默认开），关掉时和原来逐字节相同：
    palette：甲、乙（Shirley、Dylan 的 Gemini 声音）都按情绪色板拼语气（tts.compose_style）：稿末语气表那一格当情绪词，
        没写或写 fixed 用按章默认／默认词，写了色板以外的换成默认词，记进 qc.json"各轮.语气记录"；甲原来的"固定默认语气＋开场、
        结尾微调"不再用（微调已并进色板的"按章默认"）。MiMo 备用照原来的中文默认语气。
    level：每轮句子级找平（tts.level_sentences），在去首尾静音、缩句中停顿之后、统一响度之前。
    tempo：每轮（够"对谈一轮至少秒"的）量语速，和这个人的参考 × 色板语速系数比（tts.tempo_decision）：6% 以内不动、6–12% 后期
        变速、超过 12% 重录（和音高、音色共用最多再录、预算）；全部挑完后两人（去掉停顿的）语速差超过"两人之差不超过"（5%），
        乙整期再乘一个后期变速，调到差 3% 以内（最多 8%）。
    duration：{"区间分钟": [下限, 上限], "声音包": "v3"}：配音前按字数、两人的参考语速、换人停顿和声音包估成片时长，超出就
        抛 tts.DurationOutOfRange、不配音；混音后按实际时长再查，写进人声 qc.json"整集.时长把关"。"""
    p = Path(script) if isinstance(script, (str, Path)) and len(str(script)) < 400 and Path(script).exists() else None
    text = p.read_text(encoding="utf-8") if p else str(script)
    chapters, notes = parse_dialog(text)
    if not chapters:
        raise ValueError("稿子里没有\"甲：\"\"乙：\"开头的对话")
    for n in notes:
        log(f"  注意：{n}")
    styles = load_dialog_styles(text)
    if style_override:
        styles = merge_styles(styles, style_override, log)
    missing = [k for k in styles if k not in {c["title"] for c in chapters}]
    if missing:
        log(f"  注意：语气表里这些章名在稿子里找不到，不起作用：{missing}")
    speakers, gaps, look = load_pairing(profile)
    backups = load_backups(profile)
    for sp_ in list(speakers.values()) + [b for b in backups.values() if b]:
        sp_.palette = bool(palette)
    b_quieter = b_quieter_lu(profile)
    switched = {}
    for s_ in use_backup or ():
        if not backups.get(s_):
            raise ValueError(f"profile\"周日搭档\"里没有\"{s_}备用\"，没法 --use-backup {s_}")
        switched[s_] = {"原来": speakers[s_].name, "改用": backups[s_].name, "原因": "命令行 --use-backup"}
        speakers[s_] = backups[s_]
    out_dir = Path(out_dir)
    speech_dir = Path(speech_dir) if speech_dir else out_dir / "人声"
    speech_dir.mkdir(parents=True, exist_ok=True)
    ledger = ledger or tts.Ledger(BUDGET_USD)
    tts.prune_cache()
    (CACHE / "chunks").mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha1(str(out_dir.resolve()).encode("utf-8")).hexdigest()[:6]
    work = CACHE / "runs" / f"dialog_{tts._safe_name(out_dir.name)}_{tag}"
    work.mkdir(parents=True, exist_ok=True)
    run = _Run(ledger, fresh, log)
    gate = Q.gate_settings(profile)
    tst = tts.tempo_settings(profile)
    dur_rec = {}

    def rate_target(u):
        """语速微调的目标（第十轮）：这个人的参考语速 × 这一轮情绪词的语速系数；没开、没有参考就 None。"""
        if not tempo:
            return None
        r_ = (speakers[u["speaker"]].ref or {}).get("语速")
        return round(r_ * (u.get("style_rec") or {}).get("语速系数", 1.0), 3) if r_ else None

    def voice_all():
        """第 1 步：配音、对稿、不过就重录；音高把关；MiMo 跑偏把关。返回 (units, by_index, takes, refs, pitch_info)。"""
        units = plan_units(chapters, speakers, styles, palette=palette)
        by_index = {u["index"]: u for u in units}
        if palette:
            for s_ in ("甲", "乙"):
                if speakers[s_].host:
                    ws = {u["chapter_title"]: u["style_rec"]["情绪词"] for u in units if u["speaker"] == s_ and u.get("style_rec")}
                    log(f"  情绪色板 {s_}（{speakers[s_].host}）：" + "；".join(f"{k}＝{v}" for k, v in ws.items()))
            swapped = sorted({(u["chapter_title"], u["speaker"], u["style_rec"]["说明"]) for u in units
                              if (u.get("style_rec") or {}).get("说明")})
            for ch_, s_, why_ in swapped:
                log(f"  注意：「{ch_}」{s_}：{why_}")
        if duration:
            est = estimate_dialog(units, chapters, speakers, gaps, look, duration.get("声音包", "v3"), log)
            dur_rec["配音前估"] = dict(tts.check_duration(est["成片秒数"], duration.get("区间分钟"), "配音前按字数估", log),
                                   人声秒数=round(est["人声秒数"], 1), 两人参考语速=est["两人参考语速"])
            if not dur_rec["配音前估"]["通过"]:
                raise tts.DurationOutOfRange(dur_rec["配音前估"]["说明"] + "：退回写稿，不配音")
        log(f"  {len(chapters)} 章，{sum(len(c['turns']) for c in chapters)} 轮，{len(units)} 次请求；"
            + "，".join(f"{s}＝{speakers[s].name}（{speakers[s].cfg.engine}，{speakers[s].voice_id()}"
                       + (f"，atempo {speakers[s].tempo}" if speakers[s].tempo else "") + "）" for s in ("甲", "乙")))
        for s_ in ("甲", "乙"):
            if speakers[s_].fixed_style and not (palette and speakers[s_].host):
                log(f"  {s_}（{speakers[s_].name}）固定用默认语气，稿末语气表里{s_}那一列不用"
                    + (f"；按章微调：{'、'.join(f'{k}加「{speakers[s_].tweak_for(k)}」' for k in speakers[s_].chapter_kinds)}"
                       if speakers[s_].chapter_kinds else ""))
        seen_note = set()
        for u in units:
            if u["style_from"].startswith(("固定默认语气", "情绪色板")):
                continue
            if u["style_from"] not in ("稿末语气表", "profile 默认语气", "无") and (u["speaker"], u["chapter_title"]) not in seen_note:
                seen_note.add((u["speaker"], u["chapter_title"]))
                log(f"  注意：「{u['chapter_title']}」{u['speaker']}用{u['style_from']}")

        # —— 1) 配音、对稿、不过就重录 ——
        takes = {u["index"]: [] for u in units}
        jobs = [(u, 0) for u in units]
        while jobs:
            recs = synth_batch(run, jobs)
            if qc:
                qc_batch(run, recs, by_index)
            for (ui, _), rec in recs.items():
                takes[ui].append(rec)
            jobs = []
            for (ui, t), rec in recs.items():
                if qc and rec["qc"]["需重录"]:
                    u = by_index[ui]
                    log(f"    ✗ {u['speaker']} 第{ui + 1}轮第{t + 1}条：{'；'.join(rec['qc']['原因'])}"
                        + ("，重录" if t < retakes else ""))
                    if t < retakes:
                        jobs.append((u, t + 1))

        # —— 1b) 音高把关（各人按自己的参考音高）＋ 音色把关（各人对自己的档案）＋ MiMo 跑偏把关：挑出来的那条不行就再录 ——
        refs = {u["index"]: speakers[u["speaker"]].ref for u in units}
        chks = {s_: (VP.Checker.for_cfg(speakers[s_].cfg) if timbre else None) for s_ in ("甲", "乙")}
        if timbre:
            for s_ in ("甲", "乙"):
                c_ = chks[s_]
                log(f"  音色把关 {s_}（{speakers[s_].name}）：" + (
                    f"和 {c_.voice} 的档案比，每条低于 {c_.gate['段重录线']:g} 重录（和音高共用最多再录），"
                    f"低于 {c_.gate['段提醒线']:g} 提醒；量加速、均衡、混响之前的原声" if c_ else "音色指纹档案里没有这个声音，不把关"))
        pitch_info = {}
        if pitch_gate:
            for s_ in ("甲", "乙"):
                r_ = speakers[s_].ref
                log(f"  音高把关 {s_}（{speakers[s_].name}）：" + (
                    f"参考 {r_['音高Hz']} Hz（{r_['来自'][:60]}…），差超过 {gate['允许偏差半音']:g} 个半音重录，"
                    f"最多再录 {gate['最多再录']} 次" if r_ and r_.get("音高Hz") else "声音档案里没有参考音高，不把关"))

        def measure(rec, u):
            if "音高" not in rec:
                ref = refs.get(u["index"]) or {}
                st = Q.pitch_stats(rec["raw"])
                rec["音高"] = Q.pitch_verdict(st, ref.get("音高Hz") if pitch_gate else None, gate["允许偏差半音"],
                                             gate["有声不足秒不判"])
                secs = len(trim(decode(rec["raw"]))[0]) / SR         # 去掉首尾静音、没变速的秒数
                tempo_ = speakers[u["speaker"]].tempo or 1.0
                if is_question(u["text"]) and secs / tempo_ <= QUICK_QUESTION_S:
                    # 短问句（整轮不超过 4 秒、问号结尾）：句尾上扬，音高中位数天然偏高，重录也压不下来（第八轮：
                    # 甲两句短问句各重录两次都在 190–276 Hz）。只量、只标，不为音高重录
                    rec["音高"]["短问句只标不重录"] = True
                    if rec["音高"].get("超出"):
                        rec["音高"]["超出"] = False
                        rec["音高"]["说明"] = (rec["音高"].get("说明") or "") + "；短问句只标、不重录"
                        rec["音高"]["要是长句就算超出"] = True
                if u["cfg"].engine == "mimo":         # 跑偏：时长、音高离谱（量没变速的原声；atempo 不改音高）
                    ratio = secs / u["est"] if u["est"] else None
                    hz, vs = st.get("音高中位数Hz"), st.get("有声秒数") or 0
                    dev = Q.semitones(hz, ref["音高Hz"]) if (ref.get("音高Hz") and hz and vs >= gate["有声不足秒不判"]) else None
                    why = ([f"时长是估计的 {ratio:.2f} 倍"] if ratio and ratio > MIMO_ODD["时长比"] else []) + \
                          ([f"音高离参考 {dev:+.1f} 个半音"] if dev is not None and abs(dev) > MIMO_ODD["音高半音"] else [])
                    rec["跑偏"] = {"时长比": round(ratio, 2) if ratio else None,
                                 "离参考半音": round(dev, 2) if dev is not None else None, "跑偏": bool(why), "原因": why}
                c_ = chks.get(u["speaker"])
                if c_ is not None:                   # 音色：原始合成（没变速、没均衡、没混响）
                    rec["音色"] = c_.segment(rec["raw"])
                rt = rate_target(u)
                if rt and secs >= tst["对谈一轮至少秒"]:   # 语速（第十轮）：量没变速的原声，和 参考 × 色板语速系数 比
                    rec["语速判"] = tts.tempo_decision(Q.speech_rate(tts.spoken(u["text"]), tts.trimmed_seconds(rec["raw"])),
                                                     rt, tst)
            return rec["音高"]

        def is_odd(r):
            return bool((r.get("跑偏") or {}).get("跑偏"))

        def pick(tk):
            # 先对稿、再 MiMo 跑偏、再音色（有过线的只在过线的里挑；都没过线取最像的）、再音高离参考多远（tts.pick_take）
            return tts.pick_take(tk, qc, extra=is_odd)

        checked = [u for u in units if (pitch_gate and (refs.get(u["index"]) or {}).get("音高Hz"))
                   or u["cfg"].engine == "mimo" or chks.get(u["speaker"]) is not None or rate_target(u)]
        if checked:
            extra = {u["index"]: 0 for u in units}        # 为音高、音色再录了几次（两道共用；预算不够时直接记满，不再试）
            odd_n = {u["index"]: 0 for u in units}        # MiMo 为跑偏再录了几次
            while True:
                want = []
                for u in checked:
                    ui = u["index"]
                    for rec in takes[ui]:
                        measure(rec, u)
                    best = pick(takes[ui])
                    if best["音高"].get("超出") and extra[ui] < gate["最多再录"]:
                        want.append((u, len(takes[ui]), "音高"))
                    elif tts.timbre_failed(best) and extra[ui] < gate["最多再录"]:
                        want.append((u, len(takes[ui]), "音色"))
                    elif tts.rate_failed(best) and extra[ui] < gate["最多再录"]:
                        want.append((u, len(takes[ui]), "语速"))
                    elif is_odd(best) and odd_n[ui] < MIMO_ODD["最多再录"]:
                        want.append((u, len(takes[ui]), "跑偏"))
                if not want:
                    break
                jobs, acc, why_of = [], 0.0, {}
                for u, t, why in want:                  # 预算够几条就录几条，其余的记下来（不报错）
                    cached = not run.fresh and all(x.exists() for x in _paths(tts._key(u["cfg"], u["text"], t)))
                    est = 0.0 if cached else _est_cost(u["cfg"], u)   # 上次已经录过的那条在缓存里，不花钱
                    if est and ledger.spent + acc + est > ledger.budget:
                        pitch_info.setdefault(u["index"], {})["说明"] = "预算不够，没再录"
                        extra[u["index"]] = gate["最多再录"]
                        continue
                    acc += est
                    jobs.append((u, t))
                    why_of[u["index"]] = why
                if not jobs:
                    break
                n_why = {w: sum(1 for x in why_of.values() if x == w) for w in ("音高", "音色", "跑偏", "语速")}
                log(f"  把关：{n_why['音高']} 轮音高超出、{n_why['音色']} 轮音色不像、{n_why['跑偏']} 轮 MiMo 跑偏"
                    + (f"、{n_why['语速']} 轮语速差超过 12%" if n_why["语速"] else "") + "，重录"
                    + (f"（Gemini 估计 ${acc:.4f}）" if acc else ""))
                for ui, w in why_of.items():
                    r0 = pick(takes[ui])
                    if w == "跑偏":
                        log(f"    ⚠ {by_index[ui]['speaker']} 第{ui + 1}轮跑偏（{'、'.join(r0['跑偏']['原因'])}），再录")
                    elif w == "音色":
                        log(f"    ⚠ {by_index[ui]['speaker']} 第{ui + 1}轮{r0['音色'].get('说明', '音色不像')}")
                recs = synth_batch(run, jobs)
                if qc:
                    qc_batch(run, recs, by_index)
                for (ui, _), rec in recs.items():
                    takes[ui].append(rec)
                    key_ = {"音高": "为音高再录", "音色": "为音色再录", "跑偏": "为跑偏再录", "语速": "为语速再录"}[why_of[ui]]
                    if why_of[ui] == "跑偏":
                        odd_n[ui] += 1
                    else:
                        extra[ui] += 1
                    info = pitch_info.setdefault(ui, {})
                    info[key_] = info.get(key_, 0) + 1
                    measure(rec, by_index[ui])
        return units, by_index, takes, refs, pitch_info, pick, chks

    while True:
        try:
            units, by_index, takes, refs, pitch_info, pick, chks = voice_all()
            break
        except SynthFailed as e:
            bad = sorted(s_ for s_ in e.speakers if _family(speakers[s_].cfg.engine) == "gemini" and s_ not in switched)
            if not fallback or not bad or any(not backups.get(s_) for s_ in bad):
                raise
            for s_ in bad:
                switched[s_] = {"原来": speakers[s_].name, "改用": backups[s_].name, "原因": keys.hide(str(e))[:300]}
                log(f"  ⚠ {s_}（{speakers[s_].name}）的 Gemini 请求出错，整期改用备用声音 {backups[s_].name}"
                    f"（{backups[s_].cfg.engine}）：{keys.hide(str(e))[:160]}")
                speakers[s_] = backups[s_]

    # —— 2) 每轮：挑最好的一条 → 解码（按对谈加速变速）→ 去首尾静音 → 缩过长的句中停顿 ——
    rows, clips, turn_tempo = [], {}, {}
    for u in units:
        tk = takes[u["index"]]
        best = pick(tk)                     # 没有把关、不对稿时就是第一条（和原来一样）
        sp = speakers[u["speaker"]]
        rd = best.get("语速判") or {}
        tf = rd.get("变速倍数") if rd.get("处理") in ("后期调", "重录") else None   # 第十轮语速微调：这一轮后期变速多少
        turn_tempo[u["index"]] = tf
        y, head, tail, inner = trim(decode(best["raw"], (sp.tempo or 1.0) * tf if tf else sp.tempo))
        y, capped = cap_pauses(y, float(gaps["_句中"]["超过"]), float(gaps["_句中"]["缩到"]))
        clips[u["index"]] = y
        rows.append({"轮": u["index"] + 1, "章": u["chapter_title"], "说话人": f"{u['speaker']}（{sp.name}）",
                     "引擎": u["cfg"].engine, "声音": sp.voice_id(),
                     "原稿": u["text"], "估计秒数": u["est"], "语气来自": u["style_from"], "语气": u["cfg"].style,
                     "选用第几条": best["take"] + 1, "共录几条": len(tk),
                     "需人工复听": bool(qc and best["qc"]["需重录"]),
                     **({"专名读音（请你耳听）": best["qc"]["专名读音"]} if qc and best["qc"].get("专名读音") else {}),
                     **({"数字单位（请你耳听）": best["qc"]["数字单位"]} if qc and best["qc"].get("数字单位") else {}),
                     **({"英文名漏念（请你耳听）": best["qc"]["英文名漏念"]} if qc and best["qc"].get("英文名漏念") else {}),
                     "秒数": round(len(y) / SR, 2), "中间最长停顿秒（缩之前）": inner,
                     **({"缩短的句中停顿": [{"原来秒数": s, "位置秒": at} for s, at in capped]} if capped else {}),
                     "_head": head, "_tail": tail,
                     **({"音高": best["音高"], "音高把关": dict({"为音高再录": 0}, **pitch_info.get(u["index"], {}),
                                                                 参考=refs.get(u["index"]))}
                        if best.get("音高") else {}),
                     **({"跑偏把关": best["跑偏"]} if best.get("跑偏") else {}),
                     **({"音色": best["音色"]} if best.get("音色") else {}),
                     **({"音色需人工听": True} if tts.timbre_failed(best) else {}),
                     "各条": [{"第几条": r["take"] + 1, "原始音频": str(r["raw"]), "原始秒数": r["usage"]["seconds_audio"],
                               "本次新调用": r["usage"].get("本次新调用"),
                               **({k: v for k, v in r["qc"].items()} if qc else {}),
                               **({"音高": r["音高"]} if r.get("音高") else {}),
                               **({"跑偏": r["跑偏"]} if r.get("跑偏") else {}),
                               **({"音色": r["音色"]} if r.get("音色") else {}),
                               **({"语速判": r["语速判"]} if r.get("语速判") else {})} for r in tk]})
        if u.get("style_rec"):
            rows[-1]["语气记录"] = u["style_rec"]
        if tempo and rate_target(u):
            rows[-1]["语速微调"] = dict(rd or {"处理": f"不判（不到 {tst['对谈一轮至少秒']:g} 秒）"},
                                     为语速再录=pitch_info.get(u["index"], {}).get("为语速再录", 0), 用了变速=tf or 1.0)
        ref_ = refs.get(u["index"]) or {}
        if ref_.get("语速") and u["est"] >= 3:        # 语速：去掉首尾静音后的整轮（按变速后的比），差超过一成标出来
            rows[-1]["语速"] = Q.rate_verdict(tts.spoken(u["text"]), rows[-1]["秒数"], round(ref_["语速"] * (sp.tempo or 1), 2),
                                              gate["语速允许偏差"])
        if rows[-1]["需人工复听"]:
            log(f"    ⚠ {u['speaker']} 第{u['index'] + 1}轮重录后仍不理想，先用第{best['take'] + 1}条，需人工复听")
        if best.get("跑偏", {}).get("跑偏"):
            log(f"    ⚠ {u['speaker']} 第{u['index'] + 1}轮再录 {MIMO_ODD['最多再录']} 次仍跑偏（{'、'.join(best['跑偏']['原因'])}），需人工复听")
        if tts.timbre_failed(best):
            log(f"    ⚠ {u['speaker']} 第{u['index'] + 1}轮录了 {len(tk)} 条音色都在重录线下，用最像的第 {best['take'] + 1} 条，需人工听")

    # —— 2a) 第十轮：两人语速差（去掉停顿）超过 5%，乙整期再乘一个后期变速；然后每轮句子级找平 ——
    pair_rate = None
    if tempo:
        def art_rate(s_):
            n_ = sum(len(Q.tokens(tts.spoken(u["text"]))) for u in units if u["speaker"] == s_)
            sec_ = sum((articulation(clips[u["index"]])[1] or 0.0) for u in units if u["speaker"] == s_)
            return n_ / sec_ if sec_ else None
        ra, rb = art_rate("甲"), art_rate("乙")
        if ra and rb:
            ratio = ra / rb
            pair_rate = {"甲（去掉停顿，字／秒）": round(ra, 3), "乙（去掉停顿，字／秒）": round(rb, 3),
                         "甲比乙快": f"{(ratio - 1) * 100:+.1f}%", "上限": tst["两人之差不超过"], "乙整期再变速": 1.0}
            if abs(ratio - 1) > tst["两人之差不超过"]:
                g_ = ratio / (1 + np.sign(ratio - 1) * tst["调到以内"])
                g_ = float(min(1 + tst["最多调"], max(1 - tst["最多调"], g_)))
                for u in units:
                    if u["speaker"] != "乙":
                        continue
                    best = pick(takes[u["index"]])
                    sp = speakers["乙"]
                    t_ = (sp.tempo or 1.0) * (turn_tempo[u["index"]] or 1.0) * g_
                    y, head, tail, inner = trim(decode(best["raw"], t_))
                    y, capped = cap_pauses(y, float(gaps["_句中"]["超过"]), float(gaps["_句中"]["缩到"]))
                    clips[u["index"]] = y
                    r = rows[u["index"]]
                    r.update({"秒数": round(len(y) / SR, 2), "中间最长停顿秒（缩之前）": inner, "_head": head, "_tail": tail})
                    r.pop("缩短的句中停顿", None)
                    if capped:
                        r["缩短的句中停顿"] = [{"原来秒数": s, "位置秒": at} for s, at in capped]
                    if r.get("语速微调"):
                        r["语速微调"]["乙整期再变速"] = round(g_, 4)
                rb2 = art_rate("乙")
                pair_rate.update({"乙整期再变速": round(g_, 4), "变速后乙（去掉停顿，字／秒）": round(rb2, 3),
                                  "变速后甲比乙快": f"{(ra / rb2 - 1) * 100:+.1f}%"})
            log(f"  两人语速（去掉停顿）：甲 {ra:.2f}、乙 {rb:.2f} 字／秒，甲比乙快 {(ratio - 1) * 100:+.1f}%"
                + (f"，超过 {tst['两人之差不超过']:.0%}：乙整期后期变速 ×{pair_rate['乙整期再变速']}（之后 {pair_rate['变速后甲比乙快']}）"
                   if pair_rate["乙整期再变速"] != 1.0 else "，在范围内"))
    if level:
        n_adj = 0
        for u in units:
            y, rec_ = tts.level_sentences(clips[u["index"]], SR, u["text"])
            clips[u["index"]] = y
            rows[u["index"]]["句子级找平"] = rec_
            n_adj += rec_.get("调了几句", 0)
        log(f"  句子级找平：{sum(r['句子级找平']['句数'] for r in rows)} 句里调了 {n_adj} 句")

    # —— 2b) 音色：每章对每个人判一次（这个人这一章选用的各条原声拼起来），收尾每人判一次整期 ——
    timbre_sum = {}
    for s_ in ("甲", "乙"):
        c_ = chks.get(s_)
        if c_ is None:
            continue
        per_ch = {}
        for ci, chap in enumerate(chapters):
            raws = [rows[u["index"]]["各条"][rows[u["index"]]["选用第几条"] - 1]["原始音频"]
                    for u in units if u["chapter"] == ci and u["speaker"] == s_]
            if raws:
                per_ch[chap["title"] or "全文"] = c_.chapter(raws)
        ep = c_.episode()
        rs = [r for r in rows if r["说话人"].startswith(s_) and r.get("音色")]
        timbre_sum[s_] = {"声音": c_.voice, "门槛": c_.gate,
                          "各轮相似度": {r["轮"]: r["音色"].get("相似度") for r in rs},
                          "各轮判定": {r["轮"]: r["音色"].get("判定") for r in rs},
                          "为音色重录次数": sum((r.get("音高把关") or {}).get("为音色再录", 0) for r in rows
                                         if r["说话人"].startswith(s_)),
                          "音色需人工听的轮": [r["轮"] for r in rs if r.get("音色需人工听")],
                          "提醒的轮": [r["轮"] for r in rs if r["音色"].get("判定") == "提醒"],
                          "各章": per_ch, "提醒的章": [k for k, v in per_ch.items() if v.get("判定") == "提醒"],
                          "整期": ep}
        sims = [v for v in timbre_sum[s_]["各轮相似度"].values() if v is not None]
        log(f"  音色 {s_}（和 {c_.voice} 档案）：判了 {len(sims)} 轮，最低 {min(sims) if sims else '—'}；"
            f"为音色重录 {timbre_sum[s_]['为音色重录次数']} 次"
            + (f"；需人工听：第 {timbre_sum[s_]['音色需人工听的轮']} 轮" if timbre_sum[s_]["音色需人工听的轮"] else "")
            + (f"；提醒的章：{timbre_sum[s_]['提醒的章']}" if timbre_sum[s_]["提醒的章"] else "")
            + f"；整期 {ep.get('整期对档案', '—')}（{ep.get('判定')}）")

    # —— 3、4) 响度（乙比甲低一点）、音色（引擎不同才做）→ 按章拼接（换人停顿）→（引擎不同才加）共用小房间 → 整章固定增益 ——
    who = {s: [u["index"] for u in units if u["speaker"] == s] for s in ("甲", "乙")}
    fams = {_family(speakers[s].cfg.engine) for s in who if who[s]}
    do_look = len(fams) > 1 or not look.get("只在两人引擎不同时做", True)
    raw_loud = {s: round(lufs(np.concatenate([clips[i] for i in who[s]])), 1) if who[s] else None for s in who}
    cdir = CACHE / "chapters" / f"dialog_{tts._safe_name(out_dir.name)}_{tag}"
    if cdir.exists():
        shutil.rmtree(cdir)
    cdir.mkdir(parents=True)

    def gains_for(idx_list, target, cl):
        """每轮补多少 dB 到 target；不到 1 秒的轮量不准，用这个人各轮的中位数；离中位数最多 ±6 dB。"""
        meas = {i: lufs(cl[i]) for i in idx_list}
        long_ = [target - meas[i] for i in idx_list if len(cl[i]) >= SR]
        med = float(np.median(long_)) if long_ else float(np.median([target - v for v in meas.values()]))
        return {i: (min(med + 6, max(med - 6, target - meas[i])) if len(cl[i]) >= SR else med)
                for i in idx_list}, meas

    def build(b_q):
        """按"乙每轮比甲低 b_q LU"做一遍后期，写出每章人声。返回这一遍的结果（再校一次时整个重做，本机算、不花钱）。"""
        cl = dict(clips)
        target = {"甲": TARGET_LUFS, "乙": TARGET_LUFS - b_q}
        g0 = {}
        for s in who:
            if who[s]:
                g0.update(gains_for(who[s], target[s], cl)[0])
        leveled = {i: cl[i] * 10 ** (g0[i] / 20) for i in cl}
        eq_info = {"做了": False}
        if who["甲"] and who["乙"]:
            ref = band_levels([leveled[i] for i in who["甲"]])
            src = band_levels([leveled[i] for i in who["乙"]])
            eq_info["乙比甲（处理前，dB）"] = tone_summary(ref, src)
            if do_look and look.get("乙向甲靠的均衡强度"):
                lo, hi = look.get("均衡看的频段Hz", [1000, 8000])
                h, curve = match_eq(ref, src, float(look["乙向甲靠的均衡强度"]), float(look["均衡最多改dB"]), lo, hi)
                for i in who["乙"]:
                    cl[i] = apply_fir(cl[i], h)
                eq_info.update({"做了": True, "频段Hz": [lo, hi], "强度": look["乙向甲靠的均衡强度"],
                                "最多改dB": look["均衡最多改dB"], "乙的均衡（各频带 dB）": curve})
            elif not do_look:
                eq_info["没做的原因"] = "两人同一个引擎（%s），不做均衡、不加共用小房间混响" % "、".join(sorted(fams))
        gains, meas = {}, {}
        for s in who:
            if who[s]:
                g, m_ = gains_for(who[s], target[s], cl)
                gains.update(g)
                meas.update(m_)
        for i in cl:
            cl[i] = cl[i] * 10 ** (gains[i] / 20)
        for r in rows:
            r["响度"] = {"处理前LUFS": round(meas[r["轮"] - 1], 1), "补的增益dB": round(gains[r["轮"] - 1], 1),
                       "这一轮的目标LUFS": round(target[units[r["轮"] - 1]["speaker"]], 2)}
        if eq_info["做了"]:
            eq_info["乙比甲（处理后，dB）"] = tone_summary(band_levels([cl[i] for i in who["甲"]]),
                                                        band_levels([cl[i] for i in who["乙"]]))
        chapter_files, chap_arrays, gap_rows = [], [], []
        for ci, chap in enumerate(chapters):
            us = [u for u in units if u["chapter"] == ci]
            parts, pos = [], 0
            for k, u in enumerate(us):
                r = rows[u["index"]]
                if k:
                    prev = us[k - 1]
                    pr = rows[prev["index"]]
                    g, why = gap_after(prev, u, gaps, pr["秒数"], r["秒数"])
                    sil = max(0.0, g - pr["_tail"] - r["_head"])
                    parts.append(np.zeros(int(round(sil * SR))))
                    pos += len(parts[-1])
                    r["前面停顿秒"], r["停顿理由"] = g, why
                    gap_rows.append({"章": chap["title"], "在第几轮前": u["index"] + 1, "秒数": g, "理由": why,
                                     "换人": prev["speaker"] != u["speaker"]})
                r["章内开始秒"] = round(pos / SR + r["_head"], 3)
                parts.append(cl[u["index"]])
                pos += len(parts[-1])
                r["章内结束秒"] = round(pos / SR - r["_tail"], 3)
            x = np.concatenate(parts)
            if do_look:
                x = add_room(x, look.get("共用小房间"))
            dst = cdir / f"{len(chapter_files) + 1:02d}_{tts._safe_name(chap['title'] or '全文')}.wav"
            ln = finish_chapter(x, work, dst)
            y = read_wav(dst)
            chap_arrays.append(y)
            chapter_files.append({"章": chap["title"] or "全文", "文件": str(dst), "秒数": round(len(y) / SR, 2),
                                  "响度": ln})
        final = {"甲": [], "乙": []}
        for u in units:
            y = chap_arrays[u["chapter"]]              # 每章都有对话，所以第几个文件就是第几章
            r = rows[u["index"]]
            final[u["speaker"]].append(y[int(r["章内开始秒"] * SR):int(r["章内结束秒"] * SR)])
        final_loud = {s: round(lufs(np.concatenate(v)), 2) if v else None for s, v in final.items()}
        return {"chapter_files": chapter_files, "chap_arrays": chap_arrays, "gap_rows": gap_rows, "final": final,
                "final_loud": final_loud, "eq_info": eq_info, "乙每轮压低dB": b_q}

    built = build(b_quieter)
    calib = []
    q = b_quieter
    for _ in range(2):        # 每轮各自统一响度后，整章合起来量会差零点几（门限、停顿、削峰——甲的尖峰多，削得多），按差再校，最多两次
        fl = built["final_loud"]
        if fl["甲"] is None or fl["乙"] is None:
            break
        got = fl["甲"] - fl["乙"]
        if abs(got - b_quieter) <= CALIBRATE_LU:
            break
        q = round(q + (b_quieter - got), 2)
        log(f"  响度：乙比甲低 {got:.2f} LU（目标 {b_quieter:g}），乙每轮改成压低 {q:.2f} dB 再做一遍（本机，不花钱）")
        built = build(q)
        calib.append({"量到乙比甲低LU": round(got, 2), "乙每轮改成压低dB": q,
                      "再量乙比甲低LU": round(built["final_loud"]["甲"] - built["final_loud"]["乙"], 2)})
    calib = calib or None
    chapter_files, chap_arrays, gap_rows = built["chapter_files"], built["chap_arrays"], built["gap_rows"]
    final, final_loud, eq_info = built["final"], built["final_loud"], built["eq_info"]
    for r in rows:
        r.pop("_head", None)
        r.pop("_tail", None)

    # —— 5) 量一下：成品里两个人各多响；停顿；音高、语速 ——
    changes = [g for g in gap_rows if g["换人"]]
    gap_stats = ({"换人停顿秒": {"最短": min(g["秒数"] for g in changes), "中位": round(float(np.median([g["秒数"] for g in changes])), 2),
                              "最长": max(g["秒数"] for g in changes), "处数": len(changes)},
                  "各类": {w: round(float(np.mean([g["秒数"] for g in changes if g["理由"] == w])), 2)
                         for w in sorted({g["理由"] for g in changes})}} if changes else {})
    pitch_stats_, rate_info, warnings = voice_checks(units, rows, chap_arrays, chapters)
    diff = round(final_loud["甲"] - final_loud["乙"], 2) if final_loud["甲"] is not None and final_loud["乙"] is not None else None
    if diff is not None and abs(diff - b_quieter) > 0.3:
        warnings.append(f"成品人声里乙比甲低 {diff:.2f} LU，目标 {b_quieter:g}（校过一次仍差 0.3 以上）")
    for w in warnings:
        log(f"  ⚠ {w}")
    gate_sum = {}
    for s_ in ("甲", "乙"):
        rs = [r for r in rows if r["说话人"].startswith(s_) and r.get("音高")]
        if not rs:
            continue
        judged = [r for r in rs if r["音高"].get("偏差半音") is not None]
        gate_sum[s_] = {"参考Hz": rs[0]["音高"].get("参考Hz"), "判了几轮": len(judged),
                        "各轮偏差半音": {r["轮"]: r["音高"]["偏差半音"] for r in judged},
                        "仍超出的轮": [r["轮"] for r in rs if r["音高"].get("超出")],
                        "短问句只标的轮": [r["轮"] for r in rs if r["音高"].get("短问句只标不重录")],
                        "短问句里偏差超过允许的轮": [r["轮"] for r in rs if r["音高"].get("要是长句就算超出")],
                        "为音高重录次数": sum(r["音高把关"].get("为音高再录", 0) for r in rs),
                        "为跑偏重录次数": sum(r["音高把关"].get("为跑偏再录", 0) for r in rs),
                        "预算不够没再录的轮": [r["轮"] for r in rs if r["音高把关"].get("说明") == "预算不够，没再录"],
                        "语速标出的轮": [r["轮"] for r in rows if r["说话人"].startswith(s_) and (r.get("语速") or {}).get("标出")]}
        if gate_sum[s_]["仍超出的轮"]:
            nb = len(gate_sum[s_]["预算不够没再录的轮"])
            log(f"  ⚠ 音高把关 {s_}：{len(gate_sum[s_]['仍超出的轮'])} 轮（第 {gate_sum[s_]['仍超出的轮']} 轮）"
                f"仍比参考差 {gate['允许偏差半音']:g} 个半音以上" + (f"，其中 {nb} 轮是预算不够没再录" if nb else "，已用最接近的一条"))
    if gate_sum:
        gate_sum["允许偏差半音"], gate_sum["最多再录"] = gate["允许偏差半音"], gate["最多再录"]

    # —— 6) 写人声目录：qc.json、usage.json、chapters.json、episode.mp3（不带音乐）——
    chapters_out, t, pieces = [], 0.0, []
    for i, y in enumerate(chap_arrays):
        if i:
            pieces.append(np.zeros(int(CHAPTER_GAP * SR)))
            t += CHAPTER_GAP
        chapters_out.append({"startTime": round(t, 2), "title": chapter_files[i]["章"]})
        pieces.append(y)
        t += len(y) / SR
    up = work / "speech_24k.wav"
    write_f32(np.concatenate(pieces), up)
    disclosure = "本节目由 AI 辅助生成，" + ("经人工审核，" if reviewed else "") + "使用 AI 合成语音（两位主持都是合成声音）。"
    mp3, loud, master_r, _ = M._master(up, work, speech_dir, (title or out_dir.name) + "（人声）", disclosure,
                                       chapters_out, t, bitrate)
    (speech_dir / "chapters.json").write_text(json.dumps({"version": "1.2.0", "chapters": chapters_out},
                                                         ensure_ascii=False, indent=1), encoding="utf-8")
    chosen = [r["各条"][r["选用第几条"] - 1] for r in rows]
    ref_n = sum(c.get("原稿字数") or 0 for c in chosen)
    err_n = sum(sum(c.get(k) or 0 for k in ("替换", "少掉", "多出")) for c in chosen)
    py_n = sum((c.get("拼音错误率") or 0) * (c.get("原稿字数") or 0) for c in chosen)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    voices = {s: {"叫法": speakers[s].name, "引擎": speakers[s].cfg.engine, "模型": speakers[s].cfg.model,
                  ("声音ID" if speakers[s].cfg.voice else "参考音"): speakers[s].voice_id(),
                  "后期": f"atempo={speakers[s].tempo}" if speakers[s].tempo else "不变速"} for s in ("甲", "乙")}
    overall = {"字错率": round(err_n / ref_n, 4) if qc and ref_n else None,
               "拼音错误率": round(py_n / ref_n, 4) if qc and ref_n else None,
               "两人": voices, **({"改用备用声音": switched} if switched else {}),
               "轮数": sum(len(c["turns"]) for c in chapters), "请求数": len(units),
               "重录轮数": sum(1 for r in rows if r["共录几条"] > 1),
               "需人工复听轮数": sum(1 for r in rows if r["需人工复听"] or (r.get("跑偏把关") or {}).get("跑偏")
                                   or r.get("音色需人工听")),
               "人声秒数": {s: round(sum(len(v) for v in final[s]) / SR, 1) for s in final},
               "整集秒数（不带音乐，章间 0.8 秒）": round(t, 1),
               "响度": {"处理前各自LUFS": raw_loud, "处理后各自LUFS": final_loud,
                        "乙比甲低LU（目标）": b_quieter, "乙比甲低LU（成品人声实测）": diff,
                        **({"校准": calib} if calib else {}),
                        "处理后相差LU": round(abs(diff), 2) if diff is not None else None,
                        "整章怎么统一": "整章乘固定增益到 −16 LUFS，再只削尖峰（真峰值限制器，%.1f dBTP）" % TP_CEILING_DB},
               "停顿": gap_stats, "音色": eq_info,
               "共用小房间": look.get("共用小房间") if do_look else "没加（两人同一个引擎）",
               "音高": pitch_stats_, "语速": rate_info, "提醒": warnings,
               **({"音高把关": gate_sum} if gate_sum else {}),
               **({"音色把关": timbre_sum} if timbre_sum else {}),
               **({"情绪色板": {s_: {r["章"]: r["语气记录"]["情绪词"] for r in rows if r["说话人"].startswith(s_) and r.get("语气记录")}
                               for s_ in ("甲", "乙")},
                   "换成默认词": sorted({f"{r['章']}/{r['说话人']}：{r['语气记录']['说明']}" for r in rows
                                     if (r.get("语气记录") or {}).get("说明")})} if palette else {}),
               **({"语速微调": {"设置": tst, "变速的轮": [r["轮"] for r in rows if (r.get("语速微调") or {}).get("用了变速", 1.0) != 1.0],
                               "为语速重录次数": sum((r.get("语速微调") or {}).get("为语速再录", 0) for r in rows),
                               "两人": pair_rate}} if tempo else {}),
               **({"句子级找平": {"设置": tts.level_settings(profile),
                                "调了几句": sum(r["句子级找平"].get("调了几句", 0) for r in rows),
                                "句数": sum(r["句子级找平"]["句数"] for r in rows)}} if level else {}),
               **({"时长把关": dur_rec} if dur_rec else {}),
               "人声MP3响度LUFS": round(loud["I"], 1), "人声MP3真峰值dBTP": round(loud["TP"], 1),
               "人声MP3统一响度方式": (master_r or {}).get("normalization_type")}
    conf = {"甲": speakers["甲"].describe(), "乙": speakers["乙"].describe(),
            "备用声音": {s: (backups[s].describe() if backups.get(s) and s not in switched else
                         ("已换上" if s in switched else None)) for s in ("甲", "乙")},
            **({"改用备用声音": switched} if switched else {}),
            "来源": f"{Path(profile).name} 的\"周日搭档\"", "乙比甲低LU": b_quieter, "换人停顿秒": gaps,
            "统一音色": dict(look, 这期做了吗=do_look),
            "甲的语气规矩": video_style_rules()["来自"] if speakers["甲"].no_brighter else None,
            "分章语气": styles or None, **({"语气调整（盖在稿末语气表上）": style_override} if style_override else {})}
    (speech_dir / "qc.json").write_text(json.dumps(
        {"生成于": stamp, "稿子": str(p) if p else None, "配置": conf, "整集": overall, "章节人声": chapter_files,
         "停顿": gap_rows, "各轮": rows,
         # 给 site/tools/build_v3.py："听这一段"按它找时间（和 tts.py 的"各块"同样的键；开始秒是在人声 episode.mp3 里的位置）
         "各块": [{"块": r["轮"], "章": r["章"], "说话人": r["说话人"], "原稿": r["原稿"], "秒数": r["秒数"],
                   "开始秒": round(chapters_out[units[r["轮"] - 1]["chapter"]]["startTime"] + r["章内开始秒"], 2)}
                  for r in rows]}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    seen, uniq = set(), []
    for ui, tk in takes.items():                      # 同样的文字＋配置（同一个缓存文件）只算一次
        cfg_ = by_index[ui]["cfg"]
        for r in tk:
            if r["key"] not in seen:
                seen.add(r["key"])
                uniq.append(dict(r["usage"], 轮=ui + 1, 第几条=r["take"] + 1, 说话人=by_index[ui]["speaker"],
                                 声音=cfg_.voice or (Path(cfg_.clone_ref).name if cfg_.clone_ref else None)))
    gem = [c for c in uniq if c.get("engine") in tts.GEMINI_ENGINES]
    mim = [c for c in uniq if c.get("engine") == "mimo"]

    def per(cs):
        return {"调用次数": len(cs), "其中本次新调用": sum(1 for c in cs if c.get("本次新调用")),
                "音频秒数": round(sum(c["seconds_audio"] for c in cs), 1)}
    tot = {"调用次数": len(uniq), "其中本次新调用": sum(1 for c in uniq if c.get("本次新调用")),
           "音频秒数": round(sum(c["seconds_audio"] for c in uniq), 1),
           **({"Gemini": dict(per(gem), 输入token=sum(c.get("prompt_tokens") or 0 for c in gem),
                              **{"音频token（接口报）": sum(c.get("audio_tokens_reported") or 0 for c in gem),
                                 "估计费用美元": round(sum(c.get("cost_usd") or 0 for c in gem), 4),
                                 "其中本次新花费美元": round(sum(c.get("cost_usd") or 0 for c in gem if c.get("本次新调用")), 4)})}
              if gem else {}),
           **({"MiMo": per(mim)} if mim else {}),
           "各人": {s: dict(per([c for c in uniq if c["说话人"] == s]), 叫法=speakers[s].name) for s in ("甲", "乙")},
           "估计费用美元": round(sum(c.get("cost_usd") or 0 for c in gem), 4),
           "其中本次新花费美元": round(sum(c.get("cost_usd") or 0 for c in gem if c.get("本次新调用")), 4),
           "本次运行记账美元": round(ledger.spent, 4)}
    note = ("Gemini 走 Vertex（主账号 frontier-daily 项目），按 Gemini API 价目估算，2027-01-01 起单价翻倍；MiMo 声音复刻限时免费，"
            "只记次数。费用含这一集用到的全部条目（含重录、含早先生成后复用缓存的），\"其中本次新…\"才是这次运行新花的。")
    (speech_dir / "usage.json").write_text(json.dumps(
        {"生成于": stamp, "引擎": f"{speakers['甲'].cfg.engine}（甲）+ {speakers['乙'].cfg.engine}（乙）",
         "模型": f"{speakers['甲'].cfg.model}（甲）+ {speakers['乙'].cfg.model}（乙）", "声音": voices,
         **({"改用备用声音": switched} if switched else {}), "合计": tot, "说明": note,
         "各次调用": uniq}, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"  ✓ 人声 {t / 60:.1f} 分钟；两人响度 甲 {final_loud['甲']} / 乙 {final_loud['乙']} LUFS（乙比甲低 {diff} LU，目标 {b_quieter:g}）；"
        f"字错率 {overall['字错率']}；需人工复听 {overall['需人工复听轮数']} 轮；Gemini 本次 ${tot['其中本次新花费美元']:.4f}")
    shutil.rmtree(work, ignore_errors=True)

    result = {"人声目录": str(speech_dir), "人声": overall, "用量": tot, "章节人声": chapter_files}
    if package:
        log(f"  混音：声音包 {package}")
        result["混音"] = M.mix_package(speech_dir, out_dir, package=package, title=title or out_dir.name,
                                      reviewed=reviewed, bitrate=bitrate, log=log, overrides=look.get("_声音包调整"))
    if duration:                       # 第十轮：混音后按实际成片时长再查一遍（没混音就按人声加上声音包的排法算）
        if package:
            total_ = result["混音"]["秒数"]
        else:
            total_ = M.package_seconds([(c["章"], c["秒数"]) for c in chapter_files], duration.get("声音包", "v3"),
                                       overrides=look.get("_声音包调整"))
        dur_rec["配完按实际"] = tts.check_duration(total_, duration.get("区间分钟"), "配完按实际", log)
        if dur_rec.get("配音前估"):
            dur_rec["估计误差"] = f"{(dur_rec['配音前估']['时长分钟'] / dur_rec['配完按实际']['时长分钟'] - 1) * 100:+.1f}%"
        qp = speech_dir / "qc.json"
        d_ = json.loads(qp.read_text(encoding="utf-8"))
        d_["整集"]["时长把关"] = dur_rec
        qp.write_text(json.dumps(d_, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        result["时长把关"] = dur_rec
    return result


def estimate_dialog(units, chapters, speakers, gaps, look, package="v3", log=log_default):
    """配音前估对谈成片时长（第十轮）：每轮字数 ÷（这个人的参考语速 × 情绪词语速系数 × 对谈加速）→ 每轮比参考的量法少
    约 0.16 秒首尾留白（对谈的去静音留 0.02／0.05 秒，参考是 0.08／0.15）→ 按 gap_after 的规矩加换人停顿 → 每章 →
    podcast_mix.package_seconds 按声音包和"声音包调整"排。返回 {"人声秒数", "成片秒数", "各章秒数", "两人参考语速"}。"""
    secs = {}
    for u in units:
        sp = speakers[u["speaker"]]
        r_ = ((sp.ref or {}).get("语速") or tts.SYLLABLES_PER_SEC) * (u.get("style_rec") or {}).get("语速系数", 1.0) * (sp.tempo or 1.0)
        secs[u["index"]] = max(0.3, len(Q.tokens(tts.spoken(u["text"]))) / r_ - 0.16)
    chap = []
    for ci, chap_ in enumerate(chapters):
        us = [u for u in units if u["chapter"] == ci]
        t_ = sum(secs[u["index"]] for u in us)
        for k in range(1, len(us)):
            t_ += gap_after(us[k - 1], us[k], gaps, secs[us[k - 1]["index"]], secs[us[k]["index"]])[0] - 0.07
        chap.append((chap_["title"] or "全文", t_ + 0.07))
    voice = sum(x for _, x in chap) + CHAPTER_GAP * (len(chap) - 1)
    total = M.package_seconds(chap, package, overrides=look.get("_声音包调整")) if package else voice
    return {"人声秒数": voice, "成片秒数": total, "各章秒数": {k: round(v, 1) for k, v in chap},
            "两人参考语速": {s_: (speakers[s_].ref or {}).get("语速") for s_ in ("甲", "乙")}}


def show_plan(script, profile=PROFILE, palette=True, duration=None):
    text = Path(script).read_text(encoding="utf-8")
    chapters, notes = parse_dialog(text)
    styles = load_dialog_styles(text)
    speakers, gaps, look = load_pairing(profile)
    units = plan_units(chapters, speakers, styles, palette=palette)
    for n in notes:
        print(f"注意：{n}")
    cost, cur = 0.0, None
    for k, u in enumerate(units):
        if u["chapter"] != cur:
            cur = u["chapter"]
            print(f"\n## {u['chapter_title']}")
        elif k:
            g, why = gap_after(units[k - 1], u, gaps)
            print(f"      ……停 {g:.2f} 秒（{why}）")
        cost += _est_cost(u["cfg"], u)
        print(f"  {u['speaker']} 第{u['index'] + 1}轮 {len(re.findall(HAN, u['text']))} 字，约 {u['est']:.1f} 秒"
              f"（语气：{u['style_from']}）：{u['text'][:28]}…")
    total = sum(u["est"] for u in units)
    by = {s: sum(u["est"] for u in units if u["speaker"] == s) for s in ("甲", "乙")}
    print(f"\n共 {len(chapters)} 章 {len(units)} 次请求，人声估计 {total / 60:.1f} 分钟"
          f"（甲 {by['甲']:.0f} 秒、乙 {by['乙']:.0f} 秒）；Gemini 估计 ${cost:.4f}（不含重录）")
    print("甲＝%s（%s），乙＝%s（%s）" % (speakers["甲"].name, speakers["甲"].voice_id(), speakers["乙"].name,
                                     speakers["乙"].voice_id()))
    est = estimate_dialog(units, chapters, speakers, gaps, look, (duration or {}).get("声音包", "v3"))
    print(f"按两人参考语速估：人声 {est['人声秒数'] / 60:.1f} 分钟，成片（带声音包）{est['成片秒数'] / 60:.1f} 分钟"
          + (f"，区间 {duration['区间分钟']} 分钟" if duration else ""))


def main(argv=None):
    keys.install_excepthook()
    ap = argparse.ArgumentParser(description="周日对谈配音（用法见文件开头）")
    ap.add_argument("script", help="对谈稿（Markdown，每句以 甲：/乙： 开头）")
    ap.add_argument("--out", help="产出目录（混音后的整集放这里）")
    ap.add_argument("--speech-out", help="人声放哪儿，默认 --out 下的 人声/")
    ap.add_argument("--title", help="写进 MP3 的标题")
    ap.add_argument("--plan", action="store_true", help="只看分轮和停顿，不调模型")
    ap.add_argument("--package", default="v3", help="声音包（默认 v3，同工作日）")
    ap.add_argument("--no-mix", action="store_true", help="只出人声，不混音")
    ap.add_argument("--reviewed", action="store_true", help="稿子已人工审核")
    ap.add_argument("--profile", default=str(PROFILE))
    ap.add_argument("--style-override", help='语气调整 JSON：{"章名": {"甲": "…"}}，盖在稿末语气表上（不改稿子）')
    ap.add_argument("--fresh", action="store_true", help="不用缓存，全部重配")
    ap.add_argument("--no-qc", action="store_true", help="跳过 Whisper 对稿")
    ap.add_argument("--retakes", type=int, default=RETAKES)
    ap.add_argument("--bitrate", type=int, default=tts.BITRATE_KBPS)
    ap.add_argument("--budget-usd", type=float, default=BUDGET_USD)
    ap.add_argument("--no-pitch-gate", action="store_true", help="不做音高把关（默认按声音档案的参考音高把关）")
    ap.add_argument("--use-backup", nargs="*", choices=["甲", "乙"],
                    help="直接用备用声音（profile\"周日搭档\"的甲备用／乙备用）；只写 --use-backup 就是两个都换")
    ap.add_argument("--no-fallback", action="store_true", help="Gemini 出错就停（默认自动换备用声音）")
    ap.add_argument("--no-timbre-gate", action="store_true", help="不做音色把关（默认按 pipeline/assets/voices/音色指纹/ 的档案把关）")
    # 第十轮（2026-11-01 晚）：下面四样默认开，各有一个开关关掉；四个都关时和原来逐字节相同
    ap.add_argument("--no-palette", action="store_true", help="不用情绪色板（甲固定默认语气＋开场结尾微调、乙照稿末语气表原句，旧做法）")
    ap.add_argument("--no-sentence-level", action="store_true", help="不做句子级找平音量")
    ap.add_argument("--no-tempo-adjust", action="store_true", help="不做语速微调（每轮和两人之差）")
    ap.add_argument("--day-type", default="周日",
                    help="按哪一天的区间把关成片时长（默认 周日），读对应写稿提示词文末\"程序检查\"的\"成片时长分钟\"；也可以直接给提示词文件路径")
    ap.add_argument("--no-duration-gate", action="store_true", help="不把关成片时长（试音、只配一两章时用）")
    a = ap.parse_args(argv)
    use_backup = (a.use_backup or ["甲", "乙"]) if a.use_backup is not None else []
    duration = None
    if not a.no_duration_gate:
        rp = Path(a.day_type) if Path(a.day_type).suffix == ".md" else tts.day_rules_path(a.day_type)
        rng = tts.duration_rules(rp)
        if rng:
            duration = {"区间分钟": rng, "声音包": a.package, "规则": str(rp)}
        else:
            print(f"  时长把关：{rp} 里没有\"程序检查\"的\"成片时长分钟\"，这次不把关", file=sys.stderr)
    if a.plan:
        show_plan(a.script, a.profile, palette=not a.no_palette, duration=duration)
        return 0
    if not a.out:
        ap.error("要给 --out（或者用 --plan 只看分轮）")
    try:
        res = make_dialog(a.script, a.out, profile=a.profile, title=a.title, ledger=tts.Ledger(a.budget_usd),
                    fresh=a.fresh, qc=not a.no_qc, retakes=a.retakes, package=None if a.no_mix else a.package,
                    reviewed=a.reviewed, bitrate=a.bitrate, speech_dir=a.speech_out,
                    style_override=load_style_override(a.style_override) if a.style_override else None,
                    pitch_gate=not a.no_pitch_gate, fallback=not a.no_fallback, use_backup=use_backup,
                    timbre=not a.no_timbre_gate, palette=not a.no_palette, level=not a.no_sentence_level,
                    tempo=not a.no_tempo_adjust, duration=duration)
        if not ((res.get("时长把关") or {}).get("配完按实际") or {}).get("通过", True):
            print("✗ 时长把关：" + res["时长把关"]["配完按实际"]["说明"] + "（音频已配好，先别发布）", file=sys.stderr)
            return 1
    except (tts.BudgetExceeded, E.TTSError, keys.KeyReadDenied, RuntimeError, ValueError, FileNotFoundError) as e:
        print(keys.hide(f"✗ {type(e).__name__}: {e}"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
