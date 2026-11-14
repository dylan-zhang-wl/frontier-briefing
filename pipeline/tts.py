#!/usr/bin/env python3
"""frontier-daily 配音：口播稿 → 整集 MP3、章节表、每块对稿结果、用量。

用法（在项目根运行）：
    PY=~/.venvs/frontier-daily/bin/python

    # 先看怎么切块、每块估计多长（不调模型、不花钱）
    $PY pipeline/tts.py 稿.md --plan

    # Gemini 3.8 Flash TTS，走 Gemini API（主账号 AI Studio 密钥、AI Pro 额度；10-31 晚起配音用这条）。
    #   声音 ID 见 配音测试/声音记录.json 的"Gemini声音（主账号项目）"；密钥从钥匙串现取，见 tts_engines.py
    $PY pipeline/tts.py 稿.md --engine gemini-api --voice voice_… --style-map 稿_语气.json --out 产出/11-01_gemini
    # 同一个模型走 Vertex（当时是另一个不许用的项目，配音不再用；F1、M1 两个声音建在那里）
    $PY pipeline/tts.py 稿.md --engine gemini --voice voice_… \
        --style "Clear, steady morning news delivery in standard Mandarin." --out 产出/11-01_gemini
    #   换 Flash-Lite 加 --model lite；用预置声音写 --voice charon

    # MiMo 内置音色（限时免费）
    $PY pipeline/tts.py 稿.md --engine mimo --voice 冰糖 --style "用标准普通话播报……" --out 产出/11-01_mimo
    # MiMo 声音设计：每块都按描述重新"设计"一次，块与块之间音色可能对不上；
    #   这个模型单次最多约 60 秒，会自动按 ≤45 秒切块
    $PY pipeline/tts.py 稿.md --engine mimo --design "三十岁左右的女性新闻主播……" --out …
    # MiMo 声音复刻：拿一条满意的样音当参考，各块音色一致，块长照常（实测整段 111 秒一次念完）
    $PY pipeline/tts.py 稿.md --engine mimo --clone-ref 参考.wav --style "……" --out …

    # 按章节换语气：--style-map 给一个 JSON，{"章名": "风格说明", …}（以 _ 开头的键不读）；
    #   也可以直接给稿子本身，读稿末 <!-- 语气 {…} --> 注释里的风格表（写稿指令要求模型这样附上）。
    #   表里有的章用表里的风格，没有的章用 --style（都没有就不给风格）；不传 --style-map 时行为同前。
    #   Gemini 放 speechMetadata.style，MiMo 放 user 消息（可以写成导演模式的"角色/场景/指导"）
    $PY pipeline/tts.py 稿.md --engine gemini --voice voice_… --style-map 稿_语气.json --out …
    # 要混音（pipeline/podcast_mix.py）时加 --chapter-wavs：另存每章人声 WAV（默认放缓存目录），
    #   路径记进 qc.json，混音脚本从那里读
    $PY pipeline/tts.py 稿.md … --style-map 稿_语气.json --chapter-wavs --out …

在别的 Python 代码里调用：
    import tts
    tts.make_episode("稿.md", tts.VoiceConfig("gemini", "flash", "voice_…", "Clear, steady …"), "产出/…")
    tts.make_episode("稿.md", tts.VoiceConfig("mimo", voice="冰糖", style="用标准普通话……"), "产出/…")
    tts.make_episode("稿.md", cfg, "产出/…", style_map={"开场": "Warm …", "快讯": "Brisk …"})
    tts.make_episode("稿.md", cfg, "产出/…", style_map=…, pitch_ref="auto")   # 加音高把关（Python 里默认不开）
    tts.make_episode_whole("稿.md", cfg, "产出/…", chapter_wavs="auto")        # 整段一次合成再切章（默认把关）

输入稿：Markdown 或纯文本。空行分段；"## 章节名" 开新章（标题不念）。"# 总标题"、"###" 以下标题、
以 > 开头的备注行、<!-- 注释 --> 都不念。正文一字不改地发给模型（只去掉 ** 和 ` 这类排版符号），
例外只有下面的"配音写法"。
配音写法（2026-11-07 加）：读音表 pipeline/prompts/读音表.yaml 里写了"配音写法"的条目（任何分类都算），发给配音模型前
      把它的"写法""也可写"换成配音写法，如 DRAM → D-RAM（11-07 视频定案章把 DRAM 念成了一个音节的 dram；写成 D-RAM 实测念 dee-ram）。
      · 只换送去配音的那份文字（voice_text，在 _synth 里换）：稿子文件、字幕、网页、读音表检查、配完的对稿（tts_qc.check 比的是原稿）
        都还是原来的写法；英文按整词换（SDRAM 不换，DRAM-on-logic 换成 D-RAM-on-logic），大小写按条目的"区分大小写"。
      · 单人播客、视频旁白（site/tools/video3_build.py 调 make_episode）、周日对谈（dialog_tts.py 调 _key、_synth）都经过这一处。
      · 内容指纹（_key）按换过的文字算：没有要换的词的块指纹和以前一模一样，缓存照用；含这个词的块，读音表新加或改了配音写法后
        下次配音会重配（花钱）。要保留某一块的旧录音，只能手动把缓存里旧指纹的那条复制到新指纹名下（11-07 推手章就是这样留的）。
      · 读音表读不了（格式坏了）时只提醒一句、不换，照常配音，不会让 fd 第 11 步因此停下转备用声音。
      · 实际换了的记进用量（usage.json 每条调用的"配音写法"、缓存里那条的 .json）和日志。
MiMo 的行内标记（如"（轻笑）""（温柔 活泼）"，括号里只有汉字、不超过 12 个字）照样发给模型，
但对稿和估时长时不算进原稿；Gemini 的尖括号标记（如 <short pause>）同样处理。

切块：每块约 60–120 秒，只在段落之间切，不跨章节；一段本身超过 120 秒才按句号再切。
      （MiMo 声音设计例外，见上。）短章节（如开场、结尾）自成一块，会短于 60 秒。
对稿：每块用本机 Whisper 转写回来和原稿比（见 tts_qc.py），多念、漏念大段就自动重录一次，
      两条都不理想时留较好的一条，并在 qc.json 里标"需人工复听"。专名念成已知误读（11-09 加）、数字后面的单位字
      少了或换了（11-09 晚加，"34 亿美元"转写成"34 亿元"）也算要重录；重录后还在，qc.json 那一块另写
      "专名读音（请你耳听）""数字单位（请你耳听）"。读音表里的英文名整个没念出来（11-10 加，"Claude Fable 5.2"
      念成"Claude 5.2"）也一样，重录后还在写"英文名漏念（请你耳听）"。
      废条（11-14 加，tts_qc.overlong）：配出来的一条比按字数估计的长 2 倍以上、而且多出 30 秒以上（11-11 有一条 181 秒、
      估计 55 秒，多念了 612 个字），不转写、不量音高音色，直接当"需重录"丢掉重录，算进现有的重录次数
      （先占对稿的 retakes，把关时再占"最多再录"），各条记"废条""没转写"；全是废条时才补量一次选中的那条、标需人工复听。
音高把关（11-01 加，命令行默认开）：同一个声音每次合成的音高会漂。每块配完量音高中位数，和声音档案
      （voice_profile.json 各声音的"参考"）里的参考音高比，差超过 1.5 个半音就重录，最多再录 2 次，挑最接近的；
      语速和参考差超过一成在 qc.json 里标出来。阈值在档案的"音高把关"里；--pitch-ref off 关掉、给数字就用那个 Hz。
      档案里没有的声音（试音用的新声音）不把关。为音高重录受 --budget-usd 约束：预算不够就不再录，不报错。
音色把关（11-01 加，默认开，--no-timbre-gate 关）：每块的每一条量"音色指纹"，和这个声音的档案比（pipeline/voice_print.py，
      档案在 pipeline/assets/voices/音色指纹/）。低于段重录线（0.60）就重录，和音高把关共用"最多再录"和预算；挑哪一条：
      先挑音高、音色都过的，其中音高最接近参考的；没有一条音色过线就取最像的，标"音色需人工听"。每章、整期再各判一次，
      只提醒。门槛在档案的"音色把关"；档案里没有的声音、模型没装时只记"未判"，照常配音。
第十轮（11-01 晚加，命令行默认开，各有开关；四个都关时和原来逐字节相同）：
    · 情绪色板（--no-palette 关）：声音是 Shirley（--host Shirley，或 --voice 给主声音的 ID）时，--style-map／稿末语气表的值
      当情绪词，用 compose_style 拼最终语气（固定层＝基础语气＋音区抬高那句，自动补；变化层＝这一章的情绪词，只认
      voice_profile.json"情绪色板"里可用的词，别的换成默认词，记进 qc.json）。--style 不用。
    · 句子级找平（--no-sentence-level 关）：每块按停顿切成句，整句响度偏离这一块中位数超过 1.5 LU 的拉到 0.5 LU 以内（线性、
      接缝 20 毫秒），在统一响度之前做。
    · 语速微调（--no-tempo-adjust 关）：每条和 参考语速 × 色板语速系数 比，6% 以内不动、6–12% 后期变速（不改音高，最多 8%）、
      超过 12% 重录（共用最多再录和预算）。
    · 按日子把关时长（--no-duration-gate 关；--day-type 日常／周六／周日）：读那一天写稿提示词文末"程序检查"的"成片时长分钟"，
      配音前按字数估（含块间停顿、声音包），超出就停、不配音；配完按实际再算，超出时退出码 1。
    日常一期：$PY pipeline/tts.py 稿.md --host Shirley --style-map 稿.md --chapter-wavs --out 产出/人声
    Gemini 出错那天用备用：把 --host Shirley 换成 --use-backup（Shirley 自己的 MiMo 复刻；语气按色板的中文指导，
      "情绪色板.MiMo固定层.Shirley.单人"；后期变速、音高和语速参考、音色档案都从声音档案读，见 voice_profile.json"声音一览"）
整段一次合成（--whole，11-01 加，视频旁白用）：几章放进同一次请求，像一次录完，再按逐词时间切回各章。
后期：每块去掉首尾静音 → loudnorm 两遍法统一到 −16 LUFS → 块间加 0.4 秒静音 → 单声道 MP3
      （转 MP3 后响度会掉零点几 LU，编码后再量一次、补线性增益，真峰值不越过 −1 dBTP）。

产出（--out 目录）：
    episode.mp3     整集，单声道 96 kbps（--bitrate 可改，64–96）
    chapters.json   每章开始秒数（Podcasting 2.0 章节格式，可直接挂到 RSS）
    qc.json         每块的对稿结果（字错率、差异位置、重录次数、开始时间）
    usage.json      用量：Gemini 记 token 数与估计费用，MiMo 记调用次数
分块原始音频、Whisper 中间文件放 ~/.cache/frontier-daily/tts/（iCloud 之外）。同一块同一配置再跑
直接复用缓存、不重复花钱；--fresh 强制重做。--budget-usd（默认 1 美元）超了就停。
"""
import argparse
import copy
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True          # 不在 iCloud 里的项目目录生成 __pycache__
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

import keys                      # noqa: E402
import tts_engines as E          # noqa: E402
import tts_qc as Q               # noqa: E402
import voice_print as VP         # noqa: E402  （音色把关；模型用到才加载，装不上就只记"未判"）

# ============================ 可改区 ============================

CACHE = Path.home() / ".cache/frontier-daily/tts"
TARGET_LUFS = -16.0
TRUE_PEAK = -1.5            # 每块 loudnorm 的真峰值目标（dBTP）
FINAL_PEAK = -1.0           # 整集 MP3 补增益时真峰值的上限（播客通行要求 ≤ −1 dBTP）
LRA = 11
GAP_SECONDS = 0.4
BITRATE_KBPS = 96
MP3_RATE = 44100            # 播客平台通行的采样率；原声 24 kHz，升采样不损音质

CHUNK_MAX = 120             # 秒。一章估计超过这个长度才切成几块
# 个别模型单次念不了那么长：MiMo 声音设计 2026-10-31 实测每次最多约 60 秒（两次都停在 59.8 秒，
# 前后还跳掉大段），所以按 45 秒估计值切
CHUNK_MAX_BY_MODEL = {"mimo-v2.5-tts-voicedesign": 45}
SYLLABLES_PER_SEC = 4.1     # 估时长用的语速（音节/秒）。2026-10-31 测试稿实测：Gemini 新造女声 4.2、MiMo 冰糖 4.0
RETAKES = 1                 # 对稿不过时重录几次
CACHE_DAYS = 14             # 分块原始音频缓存保留几天（按最后一次用到的时间算；约 35 MB / 12 分钟一集）
WHOLE_MAX = 150             # 秒。整段一次合成（--whole，视频旁白用）时一次请求最多估计多长；超过就在章与章之间分成几次
                            # （tts_qc 的音高把关阈值在 voice_profile.json 的"音高把关"里）

# ==============================================================

HAN = r"[\u3400-\u9fff]"
GEMINI_ENGINES = ("gemini", "gemini-api")   # gemini：Vertex（现行配音走 frontier-daily 项目）；gemini-api：主账号 AI Studio 密钥


class BudgetExceeded(RuntimeError):
    pass


class DurationOutOfRange(ValueError):
    """按字数估的成片时长不在这一天的区间里（第十轮"按日子把关时长"）：退回写稿，不配音。"""


# ---------------------------------------------------------------- 读稿与切块


def _join_lines(lines):
    out = ""
    for ln in lines:
        if out and not (re.search(HAN + r"$|[，。！？；：、“”（）]$", out) and re.match(HAN, ln)):
            out += " "
        out += ln
    return out


def parse_script(text):
    """返回 [{"title": 章名或 None, "paras": [段落, …]}]。"""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    chapters, cur, buf = [], {"title": None, "paras": []}, []

    def flush():
        if buf:
            p = _join_lines(buf).replace("**", "").replace("__", "").replace("`", "").strip()
            if p:
                cur["paras"].append(p)
            buf.clear()

    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^##\s+(.+?)\s*#*$", s)
        if m and not s.startswith("###"):
            flush()
            if cur["paras"] or cur["title"]:
                chapters.append(cur)
            cur = {"title": m.group(1).strip(), "paras": []}
            continue
        if not s:
            flush()
            continue
        if s.startswith("#") or s.startswith(">"):
            flush()
            continue
        buf.append(s)
    flush()
    if cur["paras"]:
        chapters.append(cur)
    return [c for c in chapters if c["paras"]]


_TAG_RE = re.compile(r"[（(\[]\s*[㐀-鿿][㐀-鿿，、 ]{0,11}\s*[）)\]]")
# Gemini 3.8 TTS 的行内标记是尖括号里的英文词，如 <short pause>、<breath>（Google 官方 prompting guide）
_GEMINI_TAG_RE = re.compile(r"<\s*[A-Za-z][A-Za-z \-]{0,30}\s*>")


def spoken(text):
    """去掉行内标记（MiMo：括号里只有汉字的短语；Gemini：尖括号里的英文词），剩下的才是要念出来的字。"""
    return _GEMINI_TAG_RE.sub("", _TAG_RE.sub("", text))


def est_seconds(text):
    """按音节估时长：一个汉字一个音节，英文词按长度折算，数字每位约 1.3 个音节。"""
    t = Q.normalize(spoken(text))
    han = len(re.findall(HAN, t))
    eng = sum(max(1, round(len(w) / 3)) for w in re.findall(r"[a-z]+", t))
    digits = len(re.findall(r"\d", t))
    return (han + eng + 1.3 * digits) / SYLLABLES_PER_SEC


def _split_sentences(p):
    parts = re.findall(r"[^。！？!?]+[。！？!?”」]*", p)
    return [x.strip() for x in parts if x.strip()] or [p]


def _balanced(units, n):
    """把 units 按顺序切成 n 组，让各组估计时长尽量接近。"""
    lens = [est_seconds(u) for u in units]
    total, cuts, acc, k = sum(lens), [], 0.0, 1
    for i, L in enumerate(lens[:-1]):
        acc += L
        if k < n and acc >= total * k / n:
            # 在这一段之前切还是之后切，取离目标更近的
            if acc - total * k / n > L / 2 and (not cuts or cuts[-1] < i):
                cuts.append(i)
            else:
                cuts.append(i + 1)
            k += 1
    groups, start = [], 0
    for c in sorted(set(cuts)):
        if c > start:
            groups.append(units[start:c])
            start = c
    groups.append(units[start:])
    return [g for g in groups if g]


def plan_chunks(chapters, max_s=CHUNK_MAX):
    """返回块列表，每块不跨章节。"""
    chunks = []
    for ci, ch in enumerate(chapters):
        units = []
        for p in ch["paras"]:
            units += _split_sentences(p) if est_seconds(p) > max_s else [p]
        total = sum(est_seconds(u) for u in units)
        n = max(1, math.ceil(total / max_s))
        while True:
            groups = _balanced(units, n)
            if all(sum(est_seconds(u) for u in g) <= max_s * 1.15 for g in groups) or n >= len(units):
                break
            n += 1
        for g in groups:
            text = "\n".join(g)
            chunks.append({"index": len(chunks), "chapter": ci, "chapter_title": ch["title"],
                           "text": text, "chars": len(re.findall(HAN, text)),
                           "est_seconds": round(est_seconds(text), 1)})
    return chunks


# ---------------------------------------------------------------- 配置与缓存


class VoiceConfig:
    """一套配音配置。engine=gemini 时 voice 是声音 ID 或预置名；engine=mimo 时见 tts_engines.MiMo。"""

    def __init__(self, engine, model=None, voice=None, style=None, design=None,
                 clone_ref=None, language_code=None):
        self.engine = engine
        if engine in GEMINI_ENGINES:
            self.model = {"lite": E.GEMINI_LITE, "flash": E.GEMINI_FLASH, None: E.GEMINI_FLASH}.get(model, model)
            if not voice:
                raise ValueError("Gemini 要给 --voice（声音 ID 或预置声音名）")
        elif engine == "mimo":
            self.model = model or (E.MIMO_DESIGN if design else E.MIMO_CLONE if clone_ref else E.MIMO_BUILTIN)
        else:
            raise ValueError(f"不认识的引擎 {engine}")
        self.voice, self.style, self.design = voice, style, design
        self.clone_ref, self.language_code = clone_ref, language_code

    def ident(self):
        d = {"engine": self.engine, "model": self.model, "voice": self.voice, "style": self.style,
             "design": self.design, "language_code": self.language_code}
        if self.clone_ref:
            d["clone_ref_sha1"] = hashlib.sha1(Path(self.clone_ref).read_bytes()).hexdigest()
        return d

    def describe(self):
        d = {k: v for k, v in self.ident().items() if v}
        if self.clone_ref:
            d["clone_ref"] = str(self.clone_ref)
        return d

    def with_style(self, style):
        """同一配置换一句风格说明（按章节换语气用）。"""
        c = copy.copy(self)
        c.style = style
        return c


class Ledger:
    """一次运行（可跨多集）的花费账；超预算就停。"""

    def __init__(self, budget_usd=1.0):
        self.budget, self.spent = budget_usd, 0.0

    def check(self, est_usd, what=""):
        if self.spent + est_usd > self.budget:
            raise BudgetExceeded(f"预算 ${self.budget:.2f}：已花 ${self.spent:.3f}，"
                                 f"{what}预计还要 ${est_usd:.3f}，停下")

    def add(self, usd):
        self.spent += usd or 0.0


# ---------------------------------------------------------------- 配音写法（2026-11-07 加，说明见文件开头"配音写法"一段）

LEXICON = PIPE / "prompts" / "读音表.yaml"
_VOICE_FORMS = {}            # 读音表路径 → (修改时间, 规则)；表改了自动重读


def _voice_pattern(form, case):
    """和 lexicon_check._pattern 同样的认法：英文写法按整词认（前后紧挨字母、数字的不算），写法里的空格可多可少。"""
    body = r"\s*".join(re.escape(p) for p in form.split(" "))
    pre = r"(?<![A-Za-z0-9])" if re.match(r"[A-Za-z0-9]", form) else ""
    post = r"(?![A-Za-z0-9])" if re.search(r"[A-Za-z0-9]$", form) else ""
    return re.compile(pre + body + post, 0 if case else re.I)


def voice_forms(path=None, log=print):
    """读音表里写了"配音写法"的条目 → [(写法, 配音写法, 正则)]，长的写法在前（"Apple 智能"先于"Apple"）。
    任何分类（人名、公司、产品、媒体、其他……）里的条目都算，"写法""也可写"都换。读不了表时返回 []、提醒一句，照常配音。"""
    p = Path(path) if path else LEXICON
    try:
        mtime = p.stat().st_mtime_ns
    except OSError:
        mtime = None
    hit = _VOICE_FORMS.get(str(p))
    if hit and hit[0] == mtime:
        return hit[1]
    rules = []
    try:
        import yaml
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for sec in d.values():
            for e in sec if isinstance(sec, list) else []:
                if not (isinstance(e, dict) and e.get("配音写法") and e.get("写法")):
                    continue
                to = str(e["配音写法"])
                also = e.get("也可写") or []
                for f in [str(e["写法"])] + [str(x) for x in (also if isinstance(also, list) else [also])]:
                    if f and f != to:
                        rules.append((f, to, _voice_pattern(f, bool(e.get("区分大小写")))))
    except Exception as ex:  # noqa: BLE001  表坏了不能让整期配音停下（fd 第 11 步会因此整期转备用声音）
        log(f"  注意：读音表 {p} 读不了（{ex}），这次配音不换配音写法")
        rules = []
    rules.sort(key=lambda r: -len(r[0]))
    _VOICE_FORMS[str(p)] = (mtime, rules)
    return rules


def voice_text(text, forms=None):
    """送去配音的文字：按读音表的"配音写法"换（如 DRAM → D-RAM）。返回 (换好的文字, [{"写法", "配音写法", "处数"}])。
    只在 _synth（发给模型）和 _key（内容指纹）里用；稿子、对稿（tts_qc.check）、字幕都用原来的 text。"""
    forms = voice_forms() if forms is None else forms
    if not forms:
        return text, []
    # 一遍换完（各条拼成一个正则，长的在前）：换出来的字不再被别的条目认一遍（"Foo Bar"→"Foo-Bar" 后不会再把 Foo 换掉）
    alt = "|".join("(%s)" % (p.pattern if not (p.flags & re.I) else "(?i:%s)" % p.pattern) for _, _, p in forms)
    counts = [0] * len(forms)

    def rep(m):
        k = m.lastindex - 1
        counts[k] += 1
        return forms[k][1]
    text = re.sub(alt, rep, text)
    return text, [{"写法": f, "配音写法": to, "处数": n} for (f, to, _), n in zip(forms, counts) if n]


def _key(cfg, text, take):
    """内容指纹：按真正送去配音的文字算（换过配音写法的）。没有要换的词时和 11-07 以前算出来的一模一样，旧缓存照用。"""
    blob = json.dumps([cfg.ident(), voice_text(text)[0], take], ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:20]


# ---------------------------------------------------------------- 语气：固定层＋情绪色板（2026-11-01 晚加，第十轮）
# 三条配音路径（本文件的工作日播客、dialog_tts.py 的周日对谈、site/tools/video3_build.py 的视频旁白）都用 compose_style()
# 拼最终发给 Gemini 的语气，规矩只写这一处：
#   最终语气 ＝ 情绪词; 基础语气[; 对谈时后面加][. 抬高那句]
#   · 固定层（定死"这是谁"）：profile"情绪色板.固定层"里这个人的基础语气；Shirley 再补"主声音.每章语气后面都加这一句"（音区抬高）；
#   · 变化层：每章一个情绪词，只认 profile"情绪色板.词"里这个人"可用"的词。稿子没写（或写 fixed）→ 按章默认（开场 warm、
#     结尾 warm, a touch slower）→ 默认词；写了色板以外的词或整句英文 → 换成默认词，记录里写明原因（调用方写进 qc.json）。

PROFILE = PIPE / "voice_profile.json"


def load_profile(profile=None):
    if isinstance(profile, dict):
        return profile
    try:
        return json.loads(Path(profile or PROFILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _norm_word(w):
    return re.sub(r"\s+", " ", re.sub(r"[\s.;。；]+$", "", str(w or "").strip().lower()))


def host_of(cfg, profile=None, mimo=False):
    """按配音配置认出是哪位主播（profile 里的"角色名"：主声音→Shirley，周日搭档.乙→Dylan）；认不出返回 None。
    默认只认 Gemini 声音 ID；mimo=True 时也认 MiMo 复刻的参考音（备用声音→Shirley，周日搭档.乙备用→Dylan，按文件名）。"""
    prof = load_profile(profile)
    voice = getattr(cfg, "voice", None) if not isinstance(cfg, str) else cfg
    secs = [prof.get("主声音") or {}, prof.get("备用声音") or {}] + \
        [v for v in (prof.get("周日搭档") or {}).values() if isinstance(v, dict)]
    if voice:
        for sec in secs:
            if sec.get("声音ID") == voice and sec.get("角色名"):
                return sec["角色名"]
    clone = getattr(cfg, "clone_ref", None) if mimo and not isinstance(cfg, str) else None
    if clone:
        for sec in secs:
            if sec.get("参考音") and sec.get("角色名") and Path(str(sec["参考音"])).name == Path(str(clone)).name:
                return sec["角色名"]
    return None


def palette_words(host, profile=None, tested_only=True):
    """这位主播能用的情绪词（profile"情绪色板.词"里这个人"可用"的）；tested_only=False 时返回全部候选（第十轮测色板用）。"""
    pal = load_profile(profile).get("情绪色板") or {}
    out = []
    for w, e in (pal.get("词") or {}).items():
        if w.startswith("_"):
            continue
        if not tested_only or ((e or {}).get(host) or {}).get("可用"):
            out.append(w)
    return out


def palette_default(host, chapter=None, profile=None, tested_only=True):
    """这一章没写情绪词时用哪个：先看"按章默认"（章名或视频的章种类），再看"默认词"。返回 (词, 来自)。"""
    pal = load_profile(profile).get("情绪色板") or {}
    ok = {_norm_word(w): w for w in palette_words(host, profile, tested_only)}
    by_ch = {k: v for k, v in (pal.get("按章默认") or {}).items() if not k.startswith("_")}
    w = by_ch.get((chapter or "").strip())
    if w and _norm_word(w) in ok:
        return ok[_norm_word(w)], f"按章默认（{chapter}）"
    d = pal.get("默认词")
    d = d.get(host) if isinstance(d, dict) else d
    if d and _norm_word(d) in ok:
        return ok[_norm_word(d)], "默认词"
    return None, "色板里没有可用的默认词"


def compose_mimo_style(host, word=None, chapter=None, context="单人", profile=None, tested_only=True):
    """MiMo 复刻备用的语气（中文导演模式）：profile"情绪色板.MiMo固定层.<主播>.<单人／对谈／视频>"的模板，{情绪} 换成这个词的
    "MiMo指导"。选词和 compose_style 一样（只认这个人 Gemini 色板里可用的词；"不用于的章"照样换成按章默认），另外这个词对这个人的
    MiMo 实测（"词.<词>.<主播>.MiMo.可用"）没过线就用模板的默认情绪，记录里写明。返回 (语气, 记录)。"""
    prof = load_profile(profile)
    pal = prof.get("情绪色板") or {}
    layer = ((pal.get("MiMo固定层") or {}).get(host) or {})
    tpl = layer.get(context) or layer.get("对谈" if context == "单人" else "单人") or next(iter(layer.values()), None)
    if not tpl:
        raise ValueError(f"profile\"情绪色板.MiMo固定层\"里没有 {host}")
    _, rec = compose_style(host, word, chapter, profile=prof, tested_only=tested_only)
    use = rec["情绪词"]
    e = (pal.get("词") or {}).get(use) or {}
    m = (e.get(host) or {}).get("MiMo") or {}
    phrase = e.get("MiMo指导")
    if phrase and tested_only and not m.get("可用"):
        rec["MiMo说明"] = f"「{use}」的中文指导对 {host} 的 MiMo 复刻没过线（或没测），用默认情绪"
        phrase = None
    rec.update({"引擎": "mimo", "MiMo模板": context, "MiMo指导": phrase or tpl["默认情绪"],
                "语速系数": m.get("语速系数", 1.0) if phrase else 1.0})
    rec.pop("位置", None)
    rec.pop("不补抬高那句", None)
    return tpl["模板"].replace("{情绪}", phrase or tpl["默认情绪"]), rec


def compose_style(host, word=None, chapter=None, dialog=False, profile=None, tested_only=True, position=None,
                  no_raise=None, mimo=None):
    """拼一章（一轮）最终的语气。host：Shirley / Dylan；word：稿子给的情绪词（None、""、"fixed" 都算没写）；
    chapter：章名或视频的章种类（找按章默认用）；dialog=True 时基础语气后面加"对谈时后面加"那一小句（周日对谈）。
    返回 (语气, 记录)；记录写进 qc.json：{"主播", "情绪词", "稿子写的", "来自", "语速系数", "说明"?}。
    词放在哪（前／后）：先看这个词对这位主播的实测记录里的"位置"，没有再看"情绪词位置"；
    这个词的记录写了"不补抬高那句": true（第十轮补测：去掉那句音高才落回来），就不补 Shirley 的抬高那句（音高把关仍按"带抬高那句"的参考）；
    写了"不补抬高那句的章": [章名…]，只在这几章不补（开场问候句：calm and steady 在"开场"不补）；
    写了"不用于的章": [章名…]，稿子在这几章写了它也换成默认（开场问候句用 warm 音高偏高）。
    position、no_raise 给了就按给的（测色板用）。
    mimo（2026-11-01 晚加）：给了 "单人"／"对谈"／"视频" 就拼 MiMo 复刻备用的中文语气（compose_mimo_style）。
    色板里没有这位主播（profile 没写固定层）就抛 ValueError——调用方应先用 host_of 判断。"""
    if mimo:
        return compose_mimo_style(host, word, chapter, mimo, profile, tested_only)
    prof = load_profile(profile)
    pal = prof.get("情绪色板") or {}
    fixed = (pal.get("固定层") or {}).get(host)
    if not fixed or not fixed.get("基础语气"):
        raise ValueError(f"profile\"情绪色板.固定层\"里没有 {host}")
    ok = {_norm_word(w): w for w in palette_words(host, prof, tested_only)}
    given = (word or "").strip()
    rec = {"主播": host, "稿子写的": given or None}
    ch = (chapter or "").strip()
    banned_here = (((pal.get("词") or {}).get(ok.get(_norm_word(given), "")) or {}).get(host) or {}).get("不用于的章") or []
    if given and given.lower() != "fixed" and _norm_word(given) in ok and ch not in banned_here:
        use, rec["来自"] = ok[_norm_word(given)], "稿子"
    else:
        use, src = palette_default(host, chapter, prof, tested_only)
        rec["来自"] = src
        if given and given.lower() != "fixed":
            rec["来自"] = "换成默认（稿子写的不在色板里）" if ch not in banned_here else f"换成默认（这个词不用于「{ch}」）"
            rec["说明"] = (f"「{given[:60]}」不是 {host} 色板里的词，换成「{use}」" if ch not in banned_here else
                         f"「{given}」实测用在「{ch}」会把音高抬高，换成「{use}」")
    rec["情绪词"] = use
    entry = ((pal.get("词") or {}).get(use) or {}).get(host) or {}
    rec["语速系数"] = entry.get("语速系数", 1.0)
    base = fixed["基础语气"].strip()
    if dialog and (fixed.get("对谈时后面加") or "").strip():
        base = f"{base}; {fixed['对谈时后面加'].strip()}"
    pos = pal.get("情绪词位置") or "前"      # 前：情绪词; 基础语气（11-01 视频、对谈原来的写法）；后：基础语气; mood: 情绪词
    pos = position or entry.get("位置") or (pos.get(host, "前") if isinstance(pos, dict) else pos)
    rec["位置"] = pos
    skip_raise = (bool(entry.get("不补抬高那句")) or ch in (entry.get("不补抬高那句的章") or [])) if no_raise is None else bool(no_raise)
    if not use:
        style = base
    elif pos == "后":
        style = f"{base}; mood: {use}"
    else:
        style = f"{use}; {base}"
    if skip_raise and fixed.get("补抬高那句"):
        rec["不补抬高那句"] = True
    elif fixed.get("补抬高那句"):
        src = prof.get(fixed.get("声音") or "主声音") or prof.get("主声音") or {}
        suffix = (src.get("每章语气后面都加这一句") or "").strip()
        if suffix:
            style = f"{style}{'' if style[-1] in '.!?' else '.'} {suffix}"
    return style, rec


# ---------------------------------------------------------------- 音频处理


def _ffmpeg(args):
    # 2026-11-02：ffmpeg 打印很长的音频文件信息（如带署名的 comment）时，一行到约 1 KB 就截断，可能截在一个汉字中间；
    # 原来按严格 UTF-8 解码会报错。改成按字节读、解不开的那一个字替换掉，换行照旧统一成 \n——能正常解码时结果和原来一字不差。
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y"] + args, capture_output=True)
    err = r.stderr.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    if r.returncode:
        raise RuntimeError(f"ffmpeg 失败：{err[-400:]}")
    return err


def _last_json(s):
    i = s.rfind("{")
    while i >= 0:
        try:
            return json.loads(s[i:s.find("}", i) + 1])
        except json.JSONDecodeError:
            i = s.rfind("{", 0, i)
    raise RuntimeError("没读到 loudnorm 的测量结果")


def measure_loudness(path):
    """返回 {"I": 整体响度 LUFS, "TP": 真峰值 dBTP, "LRA": 响度范围}。"""
    m = _last_json(_ffmpeg(["-i", str(path), "-af",
                            f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA={LRA}:print_format=json",
                            "-f", "null", "-"]))
    return {"I": float(m["input_i"]), "TP": float(m["input_tp"]), "LRA": float(m["input_lra"])}


def to_pcm24k(src, dst):
    _ffmpeg(["-i", str(src), "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(dst)])


def trim_silence(src, dst, thresh_db=-50.0, head=0.08, tail=0.15):
    """去掉首尾静音（10 毫秒一窗，低于 −50 dBFS 算静音），首留 80 毫秒、尾留 150 毫秒。"""
    with wave.open(str(src)) as w:
        sr, n = w.getframerate(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype=np.int16)
    win = max(1, int(sr * 0.01))
    m = len(x) // win
    if m == 0:
        shutil.copy(src, dst)
        return 0.0
    frames = x[:m * win].astype(np.float32).reshape(m, win) / 32768.0
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    loud = np.where(db > thresh_db)[0]
    if len(loud) == 0:
        shutil.copy(src, dst)
        return 0.0
    a = max(0, loud[0] * win - int(head * sr))
    b = min(len(x), (loud[-1] + 1) * win + int(tail * sr))
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(x[a:b].tobytes())
    return (len(x) - (b - a)) / sr


def loudnorm_two_pass(src, dst):
    """loudnorm 两遍法：先测，再按测量值做（能线性就线性），输出 24 kHz 单声道。"""
    base = f"I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA={LRA}"
    m = _last_json(_ffmpeg(["-i", str(src), "-af", f"loudnorm={base}:print_format=json",
                            "-f", "null", "-"]))
    second = (f"loudnorm={base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
              f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
              f"offset={m['target_offset']}:linear=true:print_format=json")
    r = _last_json(_ffmpeg(["-i", str(src), "-af", second, "-ar", "24000", "-ac", "1",
                            "-c:a", "pcm_s16le", str(dst)]))
    return {"处理前": float(m["input_i"]), "处理后": float(r["output_i"]),
            "方式": r.get("normalization_type")}


def concat_wavs(paths, dst, gap=GAP_SECONDS):
    """按顺序拼接（全是 24 kHz 单声道 16 位），块之间插 gap 秒静音。返回每块的开始秒数与时长。"""
    marks, pos = [], 0
    with wave.open(str(dst), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24000)
        silence = b"\x00\x00" * int(round(gap * 24000))
        for i, p in enumerate(paths):
            with wave.open(str(p)) as w:
                if w.getframerate() != 24000 or w.getnchannels() != 1:
                    raise RuntimeError(f"{p} 不是 24 kHz 单声道")
                data = w.readframes(w.getnframes())
            if i:
                out.writeframes(silence)
                pos += len(silence) // 2
            marks.append({"start": round(pos / 24000, 2), "seconds": round(len(data) / 2 / 24000, 2)})
            out.writeframes(data)
            pos += len(data) // 2
    return marks, pos / 24000


# ---------------------------------------------------------------- 句子级找平音量、语速微调、时长估算（2026-11-01 晚加，第十轮）
# 参数在 profile"音量找平""语速微调""时长把关"三节，这里是没写时的默认值。三样都能关（各脚本的开关），关掉时和原来逐字节相同。

LEVEL_DEFAULTS = {"偏离超过LU": 1.5, "拉到以内LU": 0.5, "接缝淡入淡出秒": 0.02, "句间停顿至少秒": 0.25,
                  "一句至少秒": 1.5, "静音比最响低dB": 40.0}
TEMPO_DEFAULTS = {"不动以内": 0.06, "后期调以内": 0.12, "调到以内": 0.03, "最多调": 0.08, "两人之差不超过": 0.05,
                  "对谈一轮至少秒": 8.0}


def _section(name, defaults, profile=None):
    d = (load_profile(profile).get(name) or {})
    return {k: float(d.get(k, v)) for k, v in defaults.items()}


def level_settings(profile=None):
    return _section("音量找平", LEVEL_DEFAULTS, profile)


def tempo_settings(profile=None):
    return _section("语速微调", TEMPO_DEFAULTS, profile)


def _frame_db(x, sr, win_s=0.01):
    w = max(1, int(sr * win_s))
    m = len(x) // w
    if m == 0:
        return w, np.zeros(0)
    return w, 20 * np.log10(np.sqrt((x[:m * w].reshape(m, w) ** 2).mean(axis=1)) + 1e-9)


def sentence_spans(x, sr=24000, text=None, st=None):
    """按停顿把一段人声切成句：静音（比最响一窗低"静音比最响低dB"以下，10 毫秒一窗）连续超过"句间停顿至少秒"的地方是候选；
    给了原稿就最多取（句末标点数 − 1）个最长的停顿当句界（Gemini 有时在逗号处也停很久）；说话不到"一句至少秒"的短句并进
    停顿更短的那一边。返回 [(起样本, 止样本)]，句界落在停顿正中。"""
    st = st or level_settings()
    w, db = _frame_db(x, sr)
    if not len(db):
        return [(0, len(x))]
    quiet = db < max(db.max() - st["静音比最响低dB"], -60.0)
    pauses, i = [], 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            if i > 0 and j < len(quiet) and (j - i) * w / sr >= st["句间停顿至少秒"]:
                pauses.append(((i + j) // 2 * w, (j - i) * w / sr))
            i = j
        else:
            i += 1
    if text:
        n = len(re.findall(r"[。！？!?]+", spoken(text))) or 1
        if len(pauses) > n - 1:
            pauses = sorted(sorted(pauses, key=lambda p: -p[1])[:max(0, n - 1)])
    cuts = [p[0] for p in pauses]
    lens = [p[1] for p in pauses]
    spans = [(a, b) for a, b in zip([0] + cuts, cuts + [len(x)])]

    def speech_s(a, b):
        _, d = _frame_db(x[a:b], sr)
        return float((d >= max(db.max() - st["静音比最响低dB"], -60.0)).sum()) * 0.01

    k = 0
    while len(spans) > 1 and k < len(spans):
        if speech_s(*spans[k]) >= st["一句至少秒"]:
            k += 1
            continue
        if k == 0:
            j = 0
        elif k == len(spans) - 1:
            j = k - 1
        else:
            j = k - 1 if lens[k - 1] <= lens[k] else k
        spans[j:j + 2] = [(spans[j][0], spans[j + 1][1])]
        del lens[j]
        k = 0
    return spans


def level_sentences(x, sr=24000, text=None, st=None):
    """句子级找平：一块（一轮）里每句量响度（BS.1770，K 计权、门限），和这一块各句的中位数比；偏离超过"偏离超过LU"的句子
    乘一个固定增益拉到"拉到以内LU"（只拉到边上，不拉到中间，保留正常的轻重），句界在停顿正中，增益在接缝处用
    "接缝淡入淡出秒"（20 毫秒）的余弦斜坡过渡。不压缩：每句内部的起伏原样。返回 (音频, 记录)。"""
    import podcast_mix as M          # 用它在内存里量响度（BS.1770）；在函数里导入，免得两个模块互相导入
    st = st or level_settings()
    x = np.asarray(x, dtype=np.float64)
    spans = sentence_spans(x, sr, text, st)
    loud = [M.lufs(x[a:b], sr=sr) for a, b in spans]
    rec = {"句数": len(spans), "各句起止秒": [[round(a / sr, 2), round(b / sr, 2)] for a, b in spans]}
    if len(spans) < 2:
        return x, dict(rec, 调了几句=0, 各句偏离LU_改前=[0.0], 各句偏离LU_改后=[0.0], 各句增益dB=[0.0])
    med = float(np.median(loud))
    dev = [v - med for v in loud]
    gains = [(-(d - np.sign(d) * st["拉到以内LU"]) if abs(d) > st["偏离超过LU"] else 0.0) for d in dev]
    # 往上拉的句子：峰值不超过这一块原来最高的峰（否则后面统一响度、转 MP3 补增益时会被真峰值卡住，整集差零点几 LU）
    top = float(np.abs(x).max()) or 1.0
    for k, ((a, b), g) in enumerate(zip(spans, gains)):
        if g > 0:
            pk = float(np.abs(x[a:b]).max()) or top
            gains[k] = min(g, max(0.0, 20 * np.log10(top / pk)))
    rec.update({"中位数LUFS": round(med, 2), "各句偏离LU_改前": [round(d, 2) for d in dev],
                "各句增益dB": [round(g, 2) for g in gains], "调了几句": sum(1 for g in gains if g)})
    if not rec["调了几句"]:
        rec["各句偏离LU_改后"] = rec["各句偏离LU_改前"]
        return x, rec
    env = np.ones(len(x))
    for (a, b), g in zip(spans, gains):
        env[a:b] = 10 ** (g / 20)
    r = max(1, int(st["接缝淡入淡出秒"] * sr))
    for (a, _), (_, _) in zip(spans[1:], spans[1:]):          # 每个句界：左右两边的增益之间做余弦过渡
        lo, hi = max(0, a - r // 2), min(len(x), a + r - r // 2)
        g0, g1 = env[lo - 1] if lo > 0 else env[lo], env[hi] if hi < len(x) else env[hi - 1]
        t = (1 - np.cos(np.linspace(0, np.pi, hi - lo))) / 2
        env[lo:hi] = g0 + (g1 - g0) * t
    y = x * env
    after = [M.lufs(y[a:b], sr=sr) for a, b in spans]
    rec["各句偏离LU_改后"] = [round(v - float(np.median(after)), 2) for v in after]
    return y, rec


def trimmed_seconds(src, sr=24000, thresh_db=-50.0, head=0.08, tail=0.15):
    """和 trim_silence 同样的去首尾静音后有多少秒（不写文件；参考语速就是按这个秒数量的）。"""
    x = Q.read_audio(src, sr) if isinstance(src, (str, Path)) else np.asarray(src, dtype=np.float64)
    w, db = _frame_db(x, sr)
    loud = np.where(db > thresh_db)[0]
    if not len(loud):
        return len(x) / sr
    a = max(0, loud[0] * w - int(head * sr))
    b = min(len(x), (loud[-1] + 1) * w + int(tail * sr))
    return (b - a) / sr


def tempo_decision(rate, target, st=None):
    """语速微调：rate（这一块／一轮的字／秒）和 target（参考 × 色板语速系数）比。返回 {"相差", "处理", "变速倍数"}：
    差在"不动以内"（6%）→ 不动；在"后期调以内"（12%）→ 后期变速（atempo，不改音高）调到差"调到以内"（3%），最多调"最多调"（8%）；
    再多 → "重录"（调用方按音高、音色把关同样的规矩再录，共用最多再录和预算；录不了就用最接近的一条，再按上限变速）。"""
    st = st or tempo_settings()
    if not rate or not target:
        return {"相差": None, "处理": "不判", "变速倍数": 1.0}
    d = rate / target - 1
    out = {"字每秒": round(rate, 3), "目标字每秒": round(target, 3), "相差": round(d, 4)}
    if abs(d) <= st["不动以内"]:
        return dict(out, 处理="不动", 变速倍数=1.0)
    want = (1 + np.sign(d) * st["调到以内"]) / (1 + d)        # atempo 倍数：>1 加快、<1 放慢
    f = float(min(1 + st["最多调"], max(1 - st["最多调"], want)))
    return dict(out, 处理="后期调" if abs(d) <= st["后期调以内"] else "重录", 变速倍数=round(f, 4),
                调后相差=round(rate * f / target - 1, 4))


def backup_tempo_for(cfg, profile=None):
    """MiMo 声音复刻的备用声音在 profile 里写的后期变速（"后期"里的 atempo=…，或"对谈加速"）：按参考音文件名找
    （顶层各节和"周日搭档"里各人那一节）。不是 MiMo 复刻、找不到就返回 None。视频（video3_build）、对谈（dialog_tts）
    原来就按这一项变速；工作日 tts.py 第十轮补上（--no-backup-tempo 关）。"""
    clone = getattr(cfg, "clone_ref", None)
    if getattr(cfg, "engine", None) != "mimo" or not clone:
        return None
    prof = load_profile(profile)
    secs = [v for v in prof.values() if isinstance(v, dict)]
    secs += [v for v in (prof.get("周日搭档") or {}).values() if isinstance(v, dict)]
    for sec in secs:
        if sec.get("参考音") and Path(str(sec["参考音"])).name == Path(str(clone)).name:
            m = re.search(r"atempo\s*=\s*([\d.]+)", str(sec.get("后期", "")))
            t = float(m.group(1)) if m else None
            return t if t and abs(t - 1) > 1e-3 else None
    return None


def palette_rate(host, word, profile=None):
    """色板里这个词对这位主播的语速系数（没测过就 1.0）。"""
    e = (((load_profile(profile).get("情绪色板") or {}).get("词") or {}).get(word) or {}).get(host) or {}
    return float(e.get("语速系数") or 1.0)


def duration_rules(path):
    """读写稿提示词文末"程序检查"那段 yaml 里的"成片时长分钟"（[下限, 上限]）。没有就返回 None。"""
    import yaml
    try:
        txt = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"## 程序检查[^\n]*\n+```yaml\n(.*?)```", txt, re.S)
    if not m:
        return None
    rng = (yaml.safe_load(m.group(1)) or {}).get("成片时长分钟")
    return [float(rng[0]), float(rng[1])] if isinstance(rng, (list, tuple)) and len(rng) == 2 else None


# 哪一天读哪份写稿提示词的"程序检查"里的"成片时长分钟"（周六、周日两份由另一位 agent 写）
DAY_RULES = {"日常": "写稿_播客.md", "周六": "写稿_周六深度.md", "周日": "写稿_周日深谈.md"}


def day_rules_path(day):
    return PIPE / "prompts" / DAY_RULES.get(day, day)


def estimate_episode(chapters, chunks, rate_of, package="v3", overrides=None, gap=GAP_SECONDS):
    """配音前估成片时长：每块字数（和对稿同一种数法）÷ rate_of(块)（这个声音的参考语速 × 色板语速系数，参考语速本身
    含句间停顿）→ 每章＝各块之和＋块间 gap 秒 → podcast_mix.package_seconds 按声音包排（片头、转场、章间、片尾）。
    返回 {"人声秒数", "成片秒数", "各章秒数"}。package=None 时成片＝人声（不加声音包）。"""
    per = {}
    for ch in chunks:
        per.setdefault(ch["chapter"], []).append(len(Q.tokens(spoken(ch["text"]))) / rate_of(ch))
    chap = [(chapters[ci]["title"] or "全文", sum(v) + gap * (len(v) - 1)) for ci, v in sorted(per.items())]
    voice = sum(x for _, x in chap) + gap * (len(chap) - 1)
    if package:
        import podcast_mix as M
        total = M.package_seconds(chap, package, overrides=overrides)
    else:
        total = voice
    return {"人声秒数": voice, "成片秒数": total, "各章秒数": {k: round(v, 1) for k, v in chap}}


def style_map_from_text(text):
    """稿末 <!-- 语气 {…} --> 里的分章语气表（没有就空）。"""
    m = re.search(r"<!--\s*语气\s*(\{.*?\})\s*-->", text, flags=re.S)
    if not m:
        return {}
    try:
        d = json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}
    return {str(k).strip(): str(v).strip() for k, v in d.items() if not str(k).startswith("_") and isinstance(v, str) and v}


def estimate_script(text, cfg=None, package="v3", palette=True):
    """单人稿（日常、周六）配音前估成片时长——和 make_episode(duration=…) 配音前那一步同一套：Shirley（主声音）的参考语速
    × 每章情绪词的语速系数（稿末语气表），每块字数相除，加块间停顿，再按声音包排。script_check.py 也用它判稿子长短。
    返回 estimate_episode 的结果，另加"参考语速"。"""
    chapters = parse_script(text)
    if not chapters:
        return {"人声秒数": 0.0, "成片秒数": 0.0, "各章秒数": {}, "参考语速": None}
    if cfg is None:
        main = load_profile().get("主声音") or {}
        cfg = VoiceConfig("gemini", main.get("模型") or "flash", main.get("声音ID"))
    chunks = plan_chunks(chapters, CHUNK_MAX_BY_MODEL.get(cfg.model, CHUNK_MAX))
    style_map = style_map_from_text(text)
    host = host_of(cfg) if palette else None
    styles = {ci: compose_style(host, style_map.get(c["title"]), c["title"]) for ci, c in enumerate(chapters)} if host else {}
    first = cfg.with_style(styles[0][0]) if host else cfg.with_style(style_map.get(chapters[0]["title"], cfg.style))
    rref = Q.reference_for(first, raised=True if host else None) or {}
    rate = rref.get("语速") or SYLLABLES_PER_SEC
    est = estimate_episode(chapters, chunks, lambda ch: rate * (styles[ch["chapter"]][1].get("语速系数", 1.0) if host else 1.0),
                           package)
    return dict(est, 参考语速=rref.get("语速"))


def check_duration(seconds, rng, when, log=print):
    """成片秒数和区间（分钟）比：返回 {"时长分钟", "区间分钟", "通过", "何时"}。"""
    mins = seconds / 60
    ok = rng is None or (rng[0] <= mins <= rng[1])
    rec = {"何时": when, "时长分钟": round(mins, 2), "区间分钟": rng, "通过": bool(ok)}
    if rng is None:
        rec["说明"] = "没有时长区间，不把关"
    elif not ok:
        rec["说明"] = f"成片{when}约 {mins:.1f} 分钟，不在 {rng[0]:g}–{rng[1]:g} 分钟以内"
    log(f"  时长把关（{when}）：约 {mins:.1f} 分钟" + (f"，区间 {rng[0]:g}–{rng[1]:g} 分钟，{'通过' if ok else '✗ 超出'}" if rng else "，没有区间"))
    return rec


# ---------------------------------------------------------------- 主流程


def _engine(cfg):
    if cfg.engine == "gemini-api":
        return E.GeminiAPI()
    return E.Gemini() if cfg.engine == "gemini" else E.MiMo()


def _synth(engine, cfg, text):
    """配一条。text 是原稿这一块；发给模型前按读音表换配音写法（voice_text），换了什么记进用量的"配音写法"。
    单人播客、视频旁白（make_episode / make_episode_whole 经 _Taker.one）和周日对谈（dialog_tts._synth_one）都走这里。"""
    sent, subs = voice_text(text)
    if cfg.engine in GEMINI_ENGINES:
        wav, usage = engine.synthesize(sent, cfg.voice, style=cfg.style, model=cfg.model,
                                       language_code=cfg.language_code)
    else:
        wav, usage = engine.synthesize(sent, model=cfg.model, voice=cfg.voice, style=cfg.style,
                                       design=cfg.design, clone_ref=cfg.clone_ref)
    if subs:
        usage = dict(usage, 配音写法=subs)
    return wav, usage


def _est_cost(cfg, chunk):
    if cfg.engine not in GEMINI_ENGINES:
        return 0.0
    return E.gemini_cost(cfg.model, len(chunk["text"]) + 40,
                         chunk["est_seconds"] * 1.4 * E.AUDIO_TOKENS_PER_SEC)


def prune_cache(days=CACHE_DAYS):
    """删掉超过 days 天没用到的分块缓存和 Whisper 中间文件。"""
    cutoff = time.time() - days * 86400
    for sub in ("chunks", "whisper", "chapters"):
        d = CACHE / sub
        if not d.exists():
            continue
        for f in d.rglob("*"):
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
    runs = CACHE / "runs"                     # 中途崩掉留下的中间 WAV，两天后清
    if runs.exists():
        for d in runs.iterdir():
            if d.is_dir() and d.stat().st_mtime < time.time() - 2 * 86400:
                shutil.rmtree(d, ignore_errors=True)


def load_style_map(path):
    """读 --style-map：{"章名": "风格说明"}；以 _ 开头的键当备注，不读。
    可以是单独的 .json，也可以直接给稿子本身——写稿指令让模型把风格表放在稿末的
    <!-- 语气 {…} --> 注释里（注释不念），这里把它取出来。"""
    text = Path(path).read_text(encoding="utf-8")
    m = re.search(r"<!--\s*语气\s*(\{.*?\})\s*-->", text, flags=re.S)
    if m:
        text = m.group(1)
    elif not Path(path).suffix.lower() == ".json":
        raise ValueError(f"{path} 里没找到 <!-- 语气 {{…}} --> 风格表")
    d = json.loads(text)
    if not isinstance(d, dict):
        raise ValueError('--style-map 要是一个 JSON 对象：{"章名": "风格说明", …}')
    return {str(k).strip(): str(v).strip() for k, v in d.items()
            if not str(k).startswith("_") and v}


def _safe_name(s):
    return re.sub(r"[^\w\u4e00-\u9fff-]+", "_", s)


class _Taker:
    """配一段文字：一条或几条（缓存、记账、对稿、音高把关）。make_episode 和 make_episode_whole 共用。
    gate：tts_qc.gate_settings() 的阈值；为音高重录时预算不够就不再录（不报错），对稿重录仍按原来的规矩（超预算就停）。"""

    def __init__(self, ledger, fresh, qc, retakes, log, gate=None):
        self.ledger, self.fresh, self.qc, self.retakes, self.log = ledger, fresh, qc, retakes, log
        self.gate = gate or Q.gate_settings()
        self.engine = None
        self.calls = []

    def one(self, cfg, text, est, t, tag, block, measure=None, soft=False):
        key = _key(cfg, text, t)
        if t == 0:
            subs = voice_text(text)[1]
            if subs:
                self.log("    配音写法（只换送去配音的字）：" + "、".join(
                    f"{x['写法']} → {x['配音写法']}（{x['处数']} 处）" for x in subs))
        raw = CACHE / "chunks" / f"{key}.wav"
        meta_p = CACHE / "chunks" / f"{key}.json"
        if raw.exists() and meta_p.exists() and not self.fresh:
            usage = dict(json.loads(meta_p.read_text(encoding="utf-8")), 本次新调用=False)
            raw.touch()                     # 记下"最近用过"，免得被 prune_cache 清掉
            self.log(f"    第{t + 1}条：复用缓存（{usage['seconds_audio']:.1f} 秒）")
        else:
            try:
                self.ledger.check(_est_cost(cfg, {"text": text, "est_seconds": est}), f"{tag} ")
            except BudgetExceeded:
                if soft:
                    return None
                raise
            self.engine = self.engine or _engine(cfg)
            wav, usage = _synth(self.engine, cfg, text)
            usage["生成于"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            raw.write_bytes(wav)
            meta_p.write_text(json.dumps(usage, ensure_ascii=False, indent=1), encoding="utf-8")
            self.ledger.add(usage.get("cost_usd"))
            usage = dict(usage, 本次新调用=True)
            self.log(f"    第{t + 1}条：{usage['seconds_audio']:.1f} 秒，用时 {usage['seconds_wall']:.0f} 秒"
                     + (f"，约 ${usage['cost_usd']:.4f}" if cfg.engine in GEMINI_ENGINES else ""))
        self.calls.append(dict(usage, 块=block, 第几条=t + 1))
        seconds = usage["seconds_audio"]
        waste = Q.overlong(seconds, est) if self.qc else None
        if waste:            # 11-14：时长超过估计 2 倍、多 30 秒以上的废条，不转写、不量音高音色，直接重录（经验库第 71 件①）
            res = Q.discarded(seconds, est, waste)
            self.log(f"    对稿：{waste}")
        elif self.qc:
            wdir = CACHE / "whisper" / key
            done = wdir / f"{raw.stem}_whisper.json"      # tts_qc.transcribe 的输出名
            # 这条音频是复用缓存的、上次也转写过，就直接读上次的转写，不再跑一遍 Whisper
            if not usage.get("本次新调用") and done.exists():
                hyp = (json.loads(done.read_text(encoding="utf-8")).get("text") or "").strip()
                done.touch()
            else:
                hyp = Q.transcribe(raw, wdir)
            res = Q.check(spoken(text), hyp, seconds, est)
            flag = "；".join(res["原因"]) if res["需重录"] else "通过"
            soft = [x["名字"] for x in res.get("专名读音") or [] if x.get("只提醒")]
            if soft:       # 11-09：清单标了只提醒的名字（Claude）不重录，qc.json 那一块写"专名读音（请你耳听）"
                flag += "；专名读音只提醒、不重录：" + "、".join(dict.fromkeys(soft))
            self.log(f"    对稿：字错率 {res['字错率']:.1%}，{flag}")
        else:
            res = {"需重录": False, "字错率": None, "原因": [], "最长多出": 0, "最长少掉": 0}
        tk = {"take": t + 1, "raw": raw, "seconds": seconds, "qc": res, "finish": usage.get("finish_reason"), "key": key}
        if waste:
            tk["废条"] = True
        if measure and not waste:
            tk.update(measure(tk))
            p = tk.get("音高") or {}
            if p.get("偏差半音") is not None and p.get("音高中位数Hz") and p.get("参考Hz"):
                self.log(f"    音高：{p['音高中位数Hz']:.0f} Hz（参考 {p['参考Hz']:.0f}，{p['偏差半音']:+.1f} 个半音）"
                         + ("，超出" if p.get("超出") else ""))
            v = tk.get("音色") or {}
            if v.get("相似度") is not None:
                self.log(f"    音色：和 {v.get('声音')} 档案 {v['相似度']:.2f}，{v.get('判定')}")
        return tk

    def pick(self, takes):
        """挑一条（pick_take）：先看对稿，再看音色有没有掉到重录线下，再看音高离参考多远，再看最大的一处多念/漏念、字错率；
        没有一条音色过线就取音色最像的。没有音高、音色把关时和原来一样。"""
        return pick_take(takes, self.qc)

    def series(self, cfg, text, est, tag, block, measure=None):
        """先配 1 条；对稿不过就重录（最多 retakes 次）；给了 measure（量音高和／或音色）就再把关：
        挑出来的那条音高超出允许范围、或音色掉到重录线下，就再录——两道共用 gate["最多再录"] 次和预算——
        挑法见 pick_take。返回 (各条, 选中的, 把关记录)。
        废条（11-14 加，tts_qc.overlong：时长超过估计 2 倍、多 30 秒以上）不转写、不量，当"需重录"：先占对稿的重录次数；
        把关时挑出来的还是废条（各条都是废条），再占"最多再录"重录（记"为废条再录"）。都用完了还是废条，才补量一次、照旧标需人工复听。"""
        takes = [self.one(cfg, text, est, 0, tag, block, measure)]
        while takes[-1]["qc"].get("需重录") and len(takes) < 1 + self.retakes:
            takes.append(self.one(cfg, text, est, len(takes), tag, block, measure))
        info, best = None, None
        if measure:
            info = {"为音高再录": 0}
            timbre = any(x.get("音色") for x in takes)
            if timbre:
                info["为音色再录"] = 0
            if any(x.get("语速判") for x in takes):
                info["为语速再录"] = 0
            while (info["为音高再录"] + info.get("为音色再录", 0) + info.get("为语速再录", 0) + info.get("为废条再录", 0)
                   < self.gate["最多再录"]):
                b = self.pick(takes)
                if b.get("废条"):
                    why = "为废条再录"
                    self.log("    各条都是废条（时长超过估计 2 倍）：再录")
                elif (b.get("音高") or {}).get("超出"):
                    why = "为音高再录"
                    self.log(f"    音高{b['音高'].get('说明', '超出')}：为音高重录")
                elif timbre_failed(b):
                    why = "为音色再录"
                    self.log(f"    {b['音色'].get('说明', '音色不像')}")
                elif rate_failed(b):
                    why = "为语速再录"
                    self.log(f"    语速和目标差 {b['语速判']['相差']:+.1%}（超过 12%）：为语速重录")
                else:
                    break
                tk = self.one(cfg, text, est, len(takes), tag, block, measure, soft=True)
                if tk is None:
                    info["说明"] = f"预算不够，没再录（预算 ${self.ledger.budget:.2f}，已花 ${self.ledger.spent:.3f}）"
                    self.log("    " + info["说明"])
                    break
                takes.append(tk)
                info[why] = info.get(why, 0) + 1
            best = self.pick(takes)
            if best.get("废条"):            # 重录次数用完了还是废条：补量一次（整段合成要靠它切章），照旧标需人工复听
                best.update(measure(best))
                note = f"录了 {len(takes)} 条都是废条（时长超过估计 2 倍），先用第 {best['take']} 条，需人工听"
                info["说明"] = (info["说明"] + "；" if info.get("说明") else "") + note
                self.log("    ⚠ " + note)
            if (best.get("音高") or {}).get("超出"):
                note = (f"录了 {len(takes)} 条都超出，用最接近的第 {best['take']} 条" if len(takes) > 1
                        else "只有这一条，音高超出，先用它")
                info["说明"] = (info["说明"] + "；" if info.get("说明") else "") + note
                self.log("    ⚠ " + note)
            if timbre_failed(best):
                note = f"录了 {len(takes)} 条音色都在重录线下，用最像的第 {best['take']} 条，需人工听"
                info["说明"] = (info["说明"] + "；" if info.get("说明") else "") + note
                self.log("    ⚠ " + note)
        return takes, best if best is not None else self.pick(takes), info


def timbre_failed(x):
    """这一条的音色判了"重录"（低于段重录线）。没判、通过、提醒都不算。"""
    return (x.get("音色") or {}).get("判定") == "重录"


def rate_failed(x):
    """这一条的语速和目标差超过"后期调以内"（12%），判了"重录"（第十轮加；没量语速就不算）。"""
    return (x.get("语速判") or {}).get("处理") == "重录"


def pick_take(takes, qc=True, extra=None):
    """几条里挑一条（tts.py、dialog_tts.py 共用）。先看对稿（需不需要重录）；再看 extra(x)（dialog_tts 的 MiMo 跑偏，没有就跳过）；
    再看音色：有音色过线的，就只在过线的里挑，取音高离参考最近的（音高过线的自然排在前面），再看最大一处多念／漏念、字错率；
    一条音色都没过线，就取音色相似度最高的（调用方标"音色需人工听"）。没有音高、音色把关时和原来的挑法完全一样。"""
    any_ok = any(not timbre_failed(x) for x in takes if not x.get("废条"))
    has_rate = any(x.get("语速判") for x in takes)      # 第十轮：量了语速才多看两样——音高有没有超出、语速要不要重录（没量时和原来一样）
    # 11-14：废条（时长超过估计 2 倍、没转写、没量）紧跟在"需不需要重录"后面，排在所有转写过的条后面；没有废条时这一位都是 False，挑法和原来一样

    def k(x):
        b = Q.badness(x["qc"]) if qc else (False, 0, 0)
        dev = (x.get("音高") or {}).get("偏差半音")
        dev = abs(dev) if dev is not None else 0.0
        e = (extra(x),) if extra else ()
        r = (bool((x.get("音高") or {}).get("超出")), rate_failed(x)) if has_rate else ()
        w = (bool(x.get("废条")),)
        if any_ok:
            return (b[0],) + w + e + (timbre_failed(x),) + r + (dev, b[1], b[2])
        return (b[0],) + w + e + (-((x.get("音色") or {}).get("相似度") or 0.0),) + r + (dev, b[1], b[2])
    return min(takes, key=k)


def timbre_checker(cfg, timbre=True, log=print):
    """这个配置对应的音色把关（voice_print.Checker）；关掉、或档案里认不出这个声音就返回 None。"""
    if not timbre:
        return None
    chk = VP.Checker.for_cfg(cfg)
    if chk is None:
        log("  音色把关：音色指纹档案里没有这个声音，不把关")
    return chk


def timbre_summary(rows, chapter_results, episode):
    """qc.json"整集"里的音色汇总：各块判定、相似度，重录、提醒、需人工听，各章、整期。"""
    rs = [r for r in rows if r.get("音色")]
    out = {"门槛": VP.settings(),
           "各块相似度": [r["音色"].get("相似度") for r in rs],
           "各块判定": [r["音色"].get("判定") for r in rs],
           "为音色重录次数": sum((r.get("音色把关") or {}).get("为音色再录", 0) for r in rows),
           "音色需人工听的块": [r.get("块") for r in rows if r.get("音色需人工听")],
           "提醒的块": [r.get("块") for r in rs if r["音色"].get("判定") == "提醒"],
           "各章": chapter_results, "整期": episode}
    out["提醒的章"] = [c for c, v in chapter_results.items() if (v or {}).get("判定") == "提醒"]
    if (episode or {}).get("判定") == "提醒":
        out["整期提醒"] = episode.get("说明")
    return out


def _resolve_ref(pitch_ref, cfg, rate_ref=None):
    """pitch_ref：None 不把关；"auto" 按声音档案找（tts_qc.reference_for）；数字就是参考音高 Hz。"""
    if pitch_ref is None or pitch_ref is False:
        return None
    if pitch_ref == "auto":
        return Q.reference_for(cfg)
    if isinstance(pitch_ref, dict):
        return pitch_ref
    return {"音高Hz": float(pitch_ref), "语速": rate_ref, "来自": "调用时给的"}


def _pitch_measure(ref, gate, chk=None, rate_target=None, text=None):
    """每一条配完要量的：音高（有参考才量）、音色（有音色把关才量，用原始块）、语速（第十轮：给了 rate_target 才量，
    字数 ÷ 去首尾静音秒数，和目标比，见 tempo_decision）。都没有就返回 None。"""
    has_pitch = bool(ref and ref.get("音高Hz"))
    if not has_pitch and chk is None and not rate_target:
        return None

    def m(tk):
        out = {}
        if has_pitch:
            out["音高"] = Q.pitch_verdict(Q.pitch_stats(tk["raw"]), ref["音高Hz"], gate["允许偏差半音"],
                                         gate["有声不足秒不判"])
        if chk is not None:
            out["音色"] = chk.segment(tk["raw"])
        if rate_target:
            secs = trimmed_seconds(tk["raw"])
            out["语速判"] = tempo_decision(Q.speech_rate(spoken(text), secs), rate_target)
        return out
    return m


def _gate_fields(best, info, ref):
    """qc.json 每块里的把关记录：音高、音高把关（有音高才写，和原来一样）；音色、音色把关、音色需人工听（有音色才写）。"""
    out = {}
    if info is None:
        return out
    if info.get("为废条再录"):
        out["为废条再录"] = info["为废条再录"]
    if best.get("音高"):
        out["音高"] = best["音高"]
        out["音高把关"] = dict({k: v for k, v in info.items() if k not in ("为音色再录", "为语速再录", "为废条再录")}, 参考=ref)
    if best.get("音色"):
        out["音色"] = best["音色"]
        out["音色把关"] = {"为音色再录": info.get("为音色再录", 0)}
        if timbre_failed(best):
            out["音色需人工听"] = True
    return out


def _timbre_finish(chk, chapters, chapter_of, qc_rows, log, chapter_srcs=None):
    """每章（这一章选用的各块原始音频拼起来）、整期各判一次音色，返回给 qc.json"整集"的 {"音色把关": …}；没有音色把关返回 None。
    chapter_srcs：{第几章: [音频或 (数组, sr)]}，不给就按 qc_rows 里选用那条的原始音频。"""
    if chk is None:
        return None
    res = {}
    for ci, chap in enumerate(chapters):
        if chapter_srcs is not None:
            srcs = chapter_srcs.get(ci) or []
            r = chk.chapter([a for a, _ in srcs], sr=srcs[0][1]) if srcs else None
        else:
            srcs = [row["各条"][row["选用第几条"] - 1]["原始音频"] for row, c in zip(qc_rows, chapter_of) if c == ci]
            r = chk.chapter(srcs) if srcs else None
        if r is not None:
            name = chap["title"] or "全文"
            res[name if name not in res else f"{name}（第{ci + 1}章）"] = r
    ep = chk.episode()
    summ = timbre_summary(qc_rows, res, ep)
    log(f"  音色：各块 {summ['各块相似度']}（和 {chk.voice} 档案）；为音色重录 {summ['为音色重录次数']} 次"
        + (f"；需人工听：块 {summ['音色需人工听的块']}" if summ["音色需人工听的块"] else "")
        + (f"；提醒的章：{summ['提醒的章']}" if summ["提醒的章"] else "")
        + f"；整期 {ep.get('整期对档案', '—')}（{ep.get('判定')}）")
    return {"音色把关": summ}


def _take_row(x):
    return {"第几条": x["take"], "秒数": x["seconds"], "原始音频": str(x["raw"]), "finish_reason": x["finish"],
            **{k: v for k, v in x["qc"].items()}, **({"音高": x["音高"]} if x.get("音高") else {}),
            **({"音色": x["音色"]} if x.get("音色") else {}), **({"语速判": x["语速判"]} if x.get("语速判") else {})}


def _gate_summary(rows, gate):
    """qc.json"整集"里的音高、语速汇总。"""
    ps = [r["音高"] for r in rows if r.get("音高")]
    if not ps:
        return None
    hz = [p["音高中位数Hz"] for p in ps if p.get("音高中位数Hz")]
    out = {"参考Hz": sorted({p["参考Hz"] for p in ps if p.get("参考Hz")}),
           "允许偏差半音": gate["允许偏差半音"], "最多再录": gate["最多再录"],
           "各块音高Hz": [p.get("音高中位数Hz") for p in ps],
           "各块偏差半音": [p.get("偏差半音") for p in ps],
           "最高最低差半音": round(Q.semitones(max(hz), min(hz)), 2) if len(hz) > 1 else 0.0,
           "仍超出的块": [r.get("块") for r in rows if (r.get("音高") or {}).get("超出")],
           "为音高重录次数": sum((r.get("音高把关") or {}).get("为音高再录", 0) for r in rows)}
    rs = [r for r in rows if r.get("语速")]
    if rs:
        out["语速允许偏差"] = gate["语速允许偏差"]
        out["各块语速（字／秒）"] = [r["语速"].get("字每秒") for r in rs]
        out["语速标出的块"] = [r.get("块") for r in rs if r["语速"].get("标出")]
    return out


def _finish(chapters, chunks, finals, qc_rows, calls, cfg, out_dir, run, title, qc, bitrate, keep_work, log,
            style_map, chapter_wavs, chapter_of=None, extra_overall=None, extra_conf=None):
    """后半段（make_episode 和 make_episode_whole 共用）：拼整集、另存每章人声、转 MP3 补增益、写 chapters/qc/usage。
    finals[i] 是第 i 块统一响度后的 WAV，qc_rows[i] 是它的记录；chapter_of[i] 是第 i 块属于第几章（默认看 chunks）。"""
    chapter_of = chapter_of or [c["chapter"] for c in chunks]
    episode_wav = run / "episode.wav"
    marks, total = concat_wavs(finals, episode_wav)
    chapter_files = []
    if chapter_wavs:                # 每章人声单独存一份，给 podcast_mix.py 混音
        cdir = (CACHE / "chapters" / _safe_name(out_dir.name)) if chapter_wavs == "auto" else Path(chapter_wavs)
        cdir.mkdir(parents=True, exist_ok=True)
        for old in cdir.glob("*.wav"):
            old.unlink()
        for ci, chap in enumerate(chapters):
            parts = [f for f, c in zip(finals, chapter_of) if c == ci]
            if not parts:
                continue
            dst = cdir / f"{len(chapter_files) + 1:02d}_{_safe_name(chap['title'] or '全文')}.wav"
            _, secs = concat_wavs(parts, dst)
            chapter_files.append({"章": chap["title"] or "全文", "文件": str(dst), "秒数": round(secs, 2)})
        log(f"  每章人声另存到 {cdir}（{len(chapter_files)} 个文件）")
    # 实测转 MP3 后整体响度会掉 0.4–0.5 LU（与码率、采样率无关），loudnorm 压峰值时也常差零点几。
    # 所以编码后量一次 MP3，差 0.15 LU 以上就带着补偿增益重编一次；补偿不让真峰值超过 FINAL_PEAK。
    mp3 = out_dir / "episode.mp3"
    meta = ["-metadata", f"title={title}"] if title else []
    gain = 0.0                      # 已经编进 MP3 的补偿增益
    for attempt in range(3):
        af = ["-af", f"volume={gain:.2f}dB"] if gain else []
        _ffmpeg(["-i", str(episode_wav)] + af + ["-ac", "1", "-ar", str(MP3_RATE), "-c:a", "libmp3lame",
                                                 "-b:a", f"{bitrate}k"] + meta + [str(mp3)])
        loud = measure_loudness(mp3)
        extra = TARGET_LUFS - loud["I"]
        if extra > 0:
            extra = min(extra, FINAL_PEAK - loud["TP"])
        if abs(extra) < 0.15 or attempt == 2:
            break
        gain = round(gain + extra, 2)

    for row, mk in zip(qc_rows, marks):
        row["开始秒"], row["秒数"] = mk["start"], mk["seconds"]
        ref = row.pop("_ref", None)
        if ref and ref.get("语速"):         # 语速：和这个声音的参考值差超过一成就标出来（只标，不重录）
            row["语速"] = Q.rate_verdict(spoken(row["原稿"]), mk["seconds"], ref["语速"], Q.gate_settings()["语速允许偏差"])
    chapters_out, seen = [], set()
    for row, ci in zip(qc_rows, chapter_of):
        if ci not in seen:
            seen.add(ci)
            chapters_out.append({"startTime": row["开始秒"], "title": row["章"] or "全文"})
    (out_dir / "chapters.json").write_text(json.dumps(
        {"version": "1.2.0", "chapters": chapters_out}, ensure_ascii=False, indent=1), encoding="utf-8")

    chosen = [r["各条"][r["选用第几条"] - 1] for r in qc_rows]
    ref_n = sum(c.get("原稿字数", 0) or 0 for c in chosen)
    err_n = sum(sum(c.get(k, 0) or 0 for k in ("替换", "少掉", "多出")) for c in chosen)
    py_n = sum((c.get("拼音错误率") or 0) * (c.get("原稿字数") or 0) for c in chosen)
    overall = {"字错率": round(err_n / ref_n, 4) if (qc and ref_n) else None,
               "拼音错误率": round(py_n / ref_n, 4) if (qc and ref_n and chosen[0].get("拼音错误率") is not None) else None,
               "拼接后补的增益dB": gain,
               "块数": len(qc_rows), "重录块数": sum(1 for r in qc_rows if r["共录几条"] > 1),
               "需人工复听块数": sum(1 for r in qc_rows if r["需人工复听"]),
               "整集秒数": round(total, 1), "整集响度LUFS": round(loud["I"], 1),
               "真峰值dBTP": round(loud["TP"], 1)}
    gs = _gate_summary(qc_rows, Q.gate_settings())
    if gs:
        if "为音高重录整段次数" in (extra_overall or {}):      # 整段合成：重录的是整段，不是哪一章
            gs["为音高重录次数"] = extra_overall["为音高重录整段次数"]
        overall["音高把关"] = gs
    overall.update(extra_overall or {})
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    conf = cfg.describe()
    if style_map:
        conf["分章风格"] = style_map
    conf.update(extra_conf or {})
    (out_dir / "qc.json").write_text(json.dumps(
        {"生成于": stamp, "配置": conf, "整集": overall,
         **({"章节人声": chapter_files} if chapter_files else {}), "各块": qc_rows},
        ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    new = [c for c in calls if c.get("本次新调用")]
    tot = {"调用次数": len(calls), "其中本次新调用": len(new),
           "音频秒数": round(sum(c["seconds_audio"] for c in calls), 1)}
    if cfg.engine in GEMINI_ENGINES:
        tot.update({"输入token": sum(c.get("prompt_tokens") or 0 for c in calls),
                    "音频token（接口报）": sum(c.get("audio_tokens_reported") or 0 for c in calls),
                    "音频token（按25/秒估）": sum(c.get("audio_tokens_estimated") or 0 for c in calls),
                    "估计费用美元": round(sum(c.get("cost_usd") or 0 for c in calls), 4),
                    "其中本次新花费美元": round(sum(c.get("cost_usd") or 0 for c in new), 4)})
        note = ("按 Gemini API 价目估算（Vertex 价目页未抓到原文）；2027-01-01 起单价翻倍。"
                + ("走 Gemini API（主账号 AI Studio 项目，AI Pro 额度）。" if cfg.engine == "gemini-api" else "走 Vertex。")
                + "调用次数和费用含这一集用到的全部条目（含重录、含早先生成后复用缓存的），"
                "\"其中本次新…\"才是这次运行新花的。")
    else:
        note = ("MiMo-V2.5-TTS 限时免费（价目页未写截止日期），只记调用次数；"
                "调用次数含重录和复用缓存的条目。")
    (out_dir / "usage.json").write_text(json.dumps(
        {"生成于": stamp, "引擎": cfg.engine, "模型": cfg.model, "合计": tot, "说明": note,
         "各次调用": calls}, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"  ✓ {mp3}  {total / 60:.1f} 分钟，{loud['I']:.1f} LUFS，字错率 "
        f"{overall['字错率'] if overall['字错率'] is not None else '未对稿'}")
    if gs:
        log(f"  音高：各块 {gs['各块音高Hz']} Hz（参考 {gs['参考Hz']}），最高最低差 {gs['最高最低差半音']} 个半音；"
            f"为音高重录 {gs['为音高重录次数']} 次" + (f"；仍超出：块 {gs['仍超出的块']}" if gs["仍超出的块"] else "")
            + (f"；语速标出：块 {gs['语速标出的块']}" if gs.get("语速标出的块") else ""))
    if not keep_work:
        shutil.rmtree(run, ignore_errors=True)
    return {"mp3": str(mp3), "work_dir": str(run) if keep_work else None, "整集": overall, "用量": tot,
            "chapters": chapters_out, "qc": qc_rows, "chapter_wavs": chapter_files}


def _post(src_wav, base, tempo=None, level_text=None, info=None):
    """后期：转 24k 单声道（tempo 给了就同时用 atempo 变速，不改音高）→ 去首尾静音 →（level_text 给了就句子级找平，
    按这段原稿数句子）→ 统一响度。返回 (统一响度后的 WAV, 去掉的静音秒数, 响度记录)；info 是字典时把找平记录放进去。
    tempo、level_text 都不给时和 11-01 的做法逐字节相同。"""
    if tempo and abs(tempo - 1) > 1e-4:
        _ffmpeg(["-i", str(src_wav), "-af", f"atempo={tempo:.4f}", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
                 f"{base}_pcm.wav"])
    else:
        to_pcm24k(src_wav, f"{base}_pcm.wav")
    trimmed = trim_silence(f"{base}_pcm.wav", f"{base}_trim.wav")
    if level_text is not None:
        with wave.open(f"{base}_trim.wav") as w:
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
        y, rec = level_sentences(x, 24000, level_text)
        if rec.get("调了几句"):
            with wave.open(f"{base}_trim.wav", "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(24000)
                w.writeframes(np.round(np.clip(y, -1, 32767 / 32768) * 32768).astype(np.int16).tobytes())
        if info is not None:
            info["找平"] = rec
    ln = loudnorm_two_pass(f"{base}_trim.wav", f"{base}_norm.wav")
    return f"{base}_norm.wav", trimmed, ln


def _read_script(script):
    p = Path(script) if isinstance(script, (str, Path)) and len(str(script)) < 400 and Path(script).exists() else None
    return p.read_text(encoding="utf-8") if p else str(script)


def make_episode(script, cfg, out_dir, title=None, ledger=None, fresh=False, qc=True,
                 retakes=RETAKES, bitrate=BITRATE_KBPS, keep_work=False, log=print,
                 style_map=None, chapter_wavs=None, pitch_ref=None, gate=None, timbre=True,
                 palette=False, level=False, tempo=False, duration=None, backup_tempo=False):
    """script 可以是文件路径或稿子全文。返回结果摘要（也写进 out_dir 的几个 json）。
    keep_work=True 时保留中间 WAV（每块统一响度后的、整集无损版），默认做完就删。
    style_map={"章名": "风格说明"}：这些章换用各自的风格，其余章用 cfg.style。
    chapter_wavs=目录：另存每章人声（24 kHz 单声道，已统一响度，块间 0.4 秒静音），混音用；
    给 "auto" 就放缓存目录 chapters/<产出目录名>/。
    pitch_ref（2026-11-01 加）：音高把关。None（默认）不把关；"auto" 按声音档案 voice_profile.json 找这个声音的参考音高
    （找不到就不把关）；也可以直接给 Hz。每块配完量音高中位数，和参考差超过 gate["允许偏差半音"]（默认 1.5）就重录，
    最多再录 gate["最多再录"]（默认 2）次，挑最接近的；语速和参考差超过一成在 qc.json 里标出来。gate 默认读档案的"音高把关"。
    timbre（2026-11-01 加，默认开）：音色把关（voice_print），每条判段、每章判章、收尾判整期，见文件开头；
    判"重录"时和音高把关共用"最多再录"和预算。档案里没有这个声音就不把关。
    第十轮（2026-11-01 晚）加的四样，Python 里默认都关（命令行默认开），关掉时和原来逐字节相同：
    palette：这个声音是 Shirley／Dylan（host_of）时，style_map 的值当情绪词，用 compose_style 拼语气（自动补固定层、
        Shirley 的抬高那句；不在色板里的换成默认词，记进 qc.json"各块.语气"）；cfg.style 不用。
    level：句子级找平（level_sentences），每块去首尾静音之后、统一响度之前。
    tempo：语速微调。每条量语速，和 参考语速 × 色板语速系数 比（tempo_decision）：6% 以内不动，6–12% 后期变速，
        超过 12% 重录（和音高、音色共用"最多再录"和预算；录不了就用最接近的一条，按 8% 上限变速）。
    duration：{"区间分钟": [下限, 上限], "声音包": "v3"}——配音前按字数和这个声音的参考语速（乘语速系数）估成片时长
        （含块间 0.4 秒、声音包的片头、转场、片尾，podcast_mix.package_seconds），超出就抛 DurationOutOfRange、不配音；
        配完按实际每章秒数再算一遍，写进 qc.json"整集.时长把关"，返回值"时长把关.通过"为 False 时命令行退出码是 1。
    backup_tempo：用的是 MiMo 复刻的备用声音时，照 profile 那一节"后期"写的 atempo 整期变速（Shirley 备用 0.93），
        和视频、对谈一样；语速微调的倍数乘在它上面。视频组装自己会变速，所以 video3_build 不开这一项。"""
    text = _read_script(script)
    chapters = parse_script(text)
    if not chapters:
        raise ValueError("稿子里没有可念的正文")
    chunks = plan_chunks(chapters, CHUNK_MAX_BY_MODEL.get(cfg.model, CHUNK_MAX))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = ledger or Ledger()
    style_map = {k: v for k, v in (style_map or {}).items() if not k.startswith("_")}
    if style_map:
        missing = [k for k in style_map if k not in {c["title"] for c in chapters}]
        if missing:
            log(f"  注意：风格表里这些章名在稿子里找不到，不起作用：{missing}")
    host = host_of(cfg, mimo=True) if palette else None
    mimo_ctx = "单人" if (host and cfg.engine == "mimo") else None      # Shirley 的 MiMo 复刻备用：按色板用中文指导
    if palette and not host:
        log("  情绪色板：这个声音不是 Shirley／Dylan（Gemini 或它们的 MiMo 复刻），色板不管它，照原来的语气用")
    styles = {}                       # 第几章 → (语气, 记录)：开了色板时按章拼好
    if host:
        for ci, c in enumerate(chapters):
            styles[ci] = compose_style(host, style_map.get(c["title"]), c["title"], mimo=mimo_ctx)
        swapped = {chapters[ci]["title"]: r["说明"] for ci, (_, r) in styles.items() if r.get("说明")}
        log(f"  情绪色板（{host}）：" + "；".join(f"{chapters[ci]['title']}＝{r['情绪词']}" for ci, (_, r) in styles.items())
            + (f"；换成默认词的章：{swapped}" if swapped else ""))
    run_id = [cfg.ident(), text] + ([style_map] if style_map else []) + (
        [{"第十轮": [palette, level, tempo]}] if (palette or level or tempo) else [])
    run = CACHE / "runs" / (_safe_name(out_dir.name) + "_" +
                            hashlib.sha1(json.dumps(run_id, ensure_ascii=False)
                                         .encode()).hexdigest()[:8])
    prune_cache()
    run.mkdir(parents=True, exist_ok=True)
    (CACHE / "chunks").mkdir(parents=True, exist_ok=True)
    gate = gate or Q.gate_settings()
    taker = _Taker(ledger, fresh, qc, retakes, log, gate)
    qc_rows, finals = [], []
    if cfg.engine == "mimo" and cfg.model == E.MIMO_DESIGN and len(chunks) > 1:
        log("  注意：声音设计模型每块都会重新设计一次音色，块与块之间可能对不上；要稳就改用 --clone-ref")
    log(f"  {len(chapters)} 章，切成 {len(chunks)} 块；配置 {cfg.describe()}"
        + (f"；{len(style_map)} 章按风格表换语气" if style_map else ""))

    def chunk_cfg(ch):
        if host:
            return cfg.with_style(styles[ch["chapter"]][0])
        return cfg.with_style(style_map.get(ch["chapter_title"], cfg.style)) if style_map else cfg

    def rate_coef(ch):
        return styles[ch["chapter"]][1].get("语速系数", 1.0) if host else 1.0

    bt = backup_tempo_for(cfg) if backup_tempo else None
    if bt:
        log(f"  备用声音后期变速：整期 atempo {bt}（profile 里这个声音的\"后期\"）")
    dur_rec = {}
    if duration:
        rng = duration.get("区间分钟")
        rref = Q.reference_for(chunk_cfg(chunks[0]), raised=True if host else None) or {}
        if not rref.get("语速"):
            log("  时长把关：声音档案里没有这个声音的参考语速，估不了，不把关")
        else:
            est = estimate_episode(chapters, chunks, lambda ch: rref["语速"] * rate_coef(ch) * (bt or 1.0),
                                   duration.get("声音包", "v3"))
            dur_rec["配音前估"] = dict(check_duration(est["成片秒数"], rng, "配音前按字数估", log),
                                   人声秒数=round(est["人声秒数"], 1), 参考语速=rref["语速"])
            if not dur_rec["配音前估"]["通过"]:
                raise DurationOutOfRange(dur_rec["配音前估"]["说明"] + "：退回写稿，不配音")
    refs_logged = set()
    chk = timbre_checker(cfg, timbre, log)
    if chk is not None:
        log(f"  音色把关：和 {chk.voice} 的档案比，每条低于 {chk.gate['段重录线']:g} 重录（和音高共用最多再录 {gate['最多再录']} 次），"
            f"低于 {chk.gate['段提醒线']:g} 提醒")

    for ch in chunks:
        tag = f"块{ch['index'] + 1}/{len(chunks)}"
        log(f"  {tag}【{ch['chapter_title'] or '正文'}】{ch['chars']} 字，估计 {ch['est_seconds']:.0f} 秒")
        ccfg = chunk_cfg(ch)
        ref = _resolve_ref(pitch_ref, ccfg)
        if host and pitch_ref == "auto":   # 色板里标了"不补抬高那句"的词，语气里没有那句，音高仍按"带抬高那句"的参考比
            ref = Q.reference_for(ccfg, raised=True)
        if ref and ref.get("来自") not in refs_logged:
            refs_logged.add(ref.get("来自"))
            log(f"  音高把关：参考 {ref.get('音高Hz')} Hz、语速 {ref.get('语速')} 字／秒（{ref.get('来自')}），"
                f"差超过 {gate['允许偏差半音']:g} 个半音重录，最多再录 {gate['最多再录']} 次")
        elif pitch_ref == "auto" and not ref and "未找到" not in refs_logged:
            refs_logged.add("未找到")
            log("  音高把关：声音档案里没有这个声音的参考音高，不把关")
        rate_target = None
        if tempo:
            rref = ref if (ref and ref.get("语速")) else (Q.reference_for(ccfg) or {})
            rate_target = round(rref["语速"] * rate_coef(ch), 3) if rref.get("语速") else None
        takes, best, info = taker.series(ccfg, ch["text"], ch["est_seconds"], tag, ch["index"] + 1,
                                         _pitch_measure(ref, gate, chk, rate_target, ch["text"]))
        if best["qc"].get("需重录"):
            log(f"    ⚠ {tag} 重录后仍不理想，先用第{best['take']}条，需人工复听")
        # 后期：转 24k 单声道（语速微调时同时变速）→ 去首尾静音 →（句子级找平）→ 统一响度
        rd = best.get("语速判") or {}
        f = rd.get("变速倍数") if rd.get("处理") in ("后期调", "重录") else None
        if f:
            log(f"    语速：{rd['字每秒']} 字／秒，目标 {rd['目标字每秒']}（差 {rd['相差']:+.1%}），后期变速 ×{f}")
        pinfo = {}
        total_t = round((bt or 1.0) * (f or 1.0), 4) if (bt or f) else None
        norm, trimmed, ln = _post(best["raw"], run / f"chunk{ch['index'] + 1:02d}", tempo=total_t,
                                  level_text=ch["text"] if level else None, info=pinfo)
        if pinfo.get("找平", {}).get("调了几句"):
            lv = pinfo["找平"]
            log(f"    找平：{lv['句数']} 句里调了 {lv['调了几句']} 句（增益 {[g for g in lv['各句增益dB'] if g]} dB）")
        finals.append(norm)
        qc_rows.append({"块": ch["index"] + 1, "章": ch["chapter_title"], "原稿": ch["text"],
                        "汉字数": ch["chars"], "估计秒数": ch["est_seconds"],
                        "选用第几条": best["take"], "共录几条": len(takes),
                        "需人工复听": bool(best["qc"].get("需重录")),
                        **({"专名读音（请你耳听）": best["qc"]["专名读音"]} if best["qc"].get("专名读音") else {}),
                        **({"数字单位（请你耳听）": best["qc"]["数字单位"]} if best["qc"].get("数字单位") else {}),
                        **({"英文名漏念（请你耳听）": best["qc"]["英文名漏念"]} if best["qc"].get("英文名漏念") else {}),
                        "去掉首尾静音秒数": round(trimmed, 2), "响度": ln,
                        **({"风格": ccfg.style} if (style_map or host) else {}),
                        **({"语气": styles[ch["chapter"]][1]} if host else {}),
                        **_gate_fields(best, info, ref),
                        **({"语速微调": dict(rd, 为语速再录=(info or {}).get("为语速再录", 0), 用了变速=f or 1.0)}
                           if rate_target else {}),
                        **({"句子级找平": pinfo["找平"]} if "找平" in pinfo else {}),
                        **({"备用后期变速": bt} if bt else {}),
                        "_ref": dict(ref, 语速=round(ref["语速"] * bt, 2)) if (bt and ref and ref.get("语速")) else ref,
                        "各条": [_take_row(x) for x in takes]})

    extra = _timbre_finish(chk, chapters, [c["chapter"] for c in chunks], qc_rows, log)
    news = {}
    if host:
        news["情绪色板"] = {"主播": host, "各章": {chapters[ci]["title"]: r for ci, (_, r) in styles.items()},
                        "换成默认词的章": [chapters[ci]["title"] for ci, (_, r) in styles.items() if r.get("说明")]}
    if level:
        lvs = [r["句子级找平"] for r in qc_rows if r.get("句子级找平")]
        news["句子级找平"] = {"设置": level_settings(), "调了几句": sum(x.get("调了几句", 0) for x in lvs),
                         "句数": sum(x.get("句数", 0) for x in lvs)}
    if tempo:
        rs = [r.get("语速微调") or {} for r in qc_rows]
        news["语速微调"] = {"设置": tempo_settings(), "变速的块": [r["块"] for r, t in zip(qc_rows, rs)
                                                            if (t.get("用了变速") or 1.0) != 1.0],
                        "为语速重录次数": sum(t.get("为语速再录", 0) for t in rs)}
    if dur_rec:
        news["时长把关"] = dur_rec
    if bt:
        news["备用后期变速"] = {"atempo": bt, "说明": "profile 里这个声音\"后期\"写的整期变速，不改音高"}
    if news:
        extra = dict(extra or {}, **news)
    res = _finish(chapters, chunks, finals, qc_rows, taker.calls, cfg, out_dir, run, title, qc, bitrate, keep_work,
                  log, style_map, chapter_wavs, extra_overall=extra)
    if duration:                       # 配完按实际每章秒数再算一遍成片时长（podcast_mix 的排法），写回 qc.json
        secs = {}
        for r in res["qc"]:
            secs.setdefault(r["章"] or "全文", []).append(r["秒数"])
        chap = [(k, sum(v) + GAP_SECONDS * (len(v) - 1)) for k, v in secs.items()]
        import podcast_mix as M
        total = M.package_seconds(chap, duration.get("声音包", "v3"))
        dur_rec["配完按实际"] = check_duration(total, duration.get("区间分钟"), "配完按实际", log)
        if dur_rec.get("配音前估"):
            dur_rec["估计误差"] = f"{(dur_rec['配音前估']['时长分钟'] / dur_rec['配完按实际']['时长分钟'] - 1) * 100:+.1f}%"
        qp = out_dir / "qc.json"
        d = json.loads(qp.read_text(encoding="utf-8"))
        d["整集"]["时长把关"] = dur_rec
        qp.write_text(json.dumps(d, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        res["时长把关"] = dur_rec
    return res


def make_episode_whole(script, cfg, out_dir, title=None, ledger=None, fresh=False, qc=True,
                       retakes=RETAKES, bitrate=BITRATE_KBPS, keep_work=False, log=print,
                       chapter_wavs=None, pitch_ref="auto", gate=None, max_seconds=WHOLE_MAX, prompt="",
                       timbre=True):
    """整段一次合成（2026-11-01 加，视频旁白用）：好几章放进同一次请求，像一次录完；再按逐词时间切回各章。
    · 章与章之间在稿子里是空行（模型会停一下）；整篇估计超过 max_seconds 秒才在章与章之间分成几次请求。
    · 每次请求：对稿（整段 Whisper）不过就重录；切开后每章量音高中位数，有一章和参考差超过允许范围就整段重录
      （最多 gate["最多再录"] 次，挑"最离谱的那一章"最接近参考的一条）。
    · 切点：逐词对齐后，在上一章末字和下一章首字之间找最长的一段静音，切在正中（tts_qc.chapter_cuts）；
      切开后每章再单独转写对稿，查首尾有没有切掉或多带了字。
    · 之后和 make_episode 一样：每章去首尾静音、统一响度，产出 episode.mp3、chapters.json、qc.json、usage.json，
      chapter_wavs 另存每章人声。qc.json 的"各块"一章一条（"整段"记在"整集"里）。
    只用 cfg.style 一种语气（同一次请求里没法分章换语气）。
    timbre：音色把关，切开后每章各判一次段（有一章掉到重录线下就整段重录，和音高共用"最多再录"），选中那条每章再判章，收尾判整期。"""
    import numpy as np
    text = _read_script(script)
    chapters = parse_script(text)
    if not chapters:
        raise ValueError("稿子里没有可念的正文")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = ledger or Ledger()
    gate = gate or Q.gate_settings()
    ref = _resolve_ref(pitch_ref, cfg)
    run = CACHE / "runs" / (_safe_name(out_dir.name) + "_whole_" + hashlib.sha1(
        json.dumps([cfg.ident(), text], ensure_ascii=False).encode()).hexdigest()[:8])
    prune_cache()
    run.mkdir(parents=True, exist_ok=True)
    (CACHE / "chunks").mkdir(parents=True, exist_ok=True)
    taker = _Taker(ledger, fresh, qc, retakes, log, gate)
    # 分组：按章累加，估计超过 max_seconds 就另起一次请求（通常整篇一次）
    texts = ["\n".join(c["paras"]) for c in chapters]
    groups, cur, acc = [], [], 0.0
    for ci, t in enumerate(texts):
        e = est_seconds(t)
        if cur and acc + e > max_seconds:
            groups.append(cur)
            cur, acc = [], 0.0
        cur.append(ci)
        acc += e
    groups.append(cur)
    log(f"  {len(chapters)} 章，整段合成：{len(groups)} 次请求（{'、'.join(str(len(g)) + ' 章' for g in groups)}）；"
        f"配置 {cfg.describe()}")
    if ref:
        log(f"  音高把关：参考 {ref.get('音高Hz')} Hz、语速 {ref.get('语速')} 字／秒（{ref.get('来自')}），"
            f"切开后任何一章差超过 {gate['允许偏差半音']:g} 个半音就整段重录，最多再录 {gate['最多再录']} 次")
    elif pitch_ref == "auto":
        log("  音高把关：声音档案里没有这个声音的参考音高，不把关")
    chk = timbre_checker(cfg, timbre, log)

    finals, qc_rows, chapter_of, whole_rows, chapter_srcs = [], [], [], [], {}
    for gi, g in enumerate(groups):
        gtext = "\n\n".join(texts[ci] for ci in g)
        gest = round(sum(est_seconds(texts[ci]) for ci in g), 1)
        tag = f"整段{gi + 1}/{len(groups)}"
        log(f"  {tag}：第 {g[0] + 1}–{g[-1] + 1} 章，{len(re.findall(HAN, gtext))} 字，估计 {gest:.0f} 秒")
        wdir_words = CACHE / "whisper" / "words"

        def split_take(tk, g=g):
            """一条整段录音 → 切点、每章的音频（24k 数组）和音高。结果放进 tk 里，选中后直接用。"""
            x = Q.read_audio(tk["raw"])
            cuts = []
            if len(g) > 1:
                words = Q.transcribe_words(tk["raw"], wdir_words / tk["key"], prompt=prompt)
                cuts = Q.chapter_cuts([spoken(texts[ci]) for ci in g], words, x)
            edges = [0] + [int(c["秒"] * Q.SR) for c in cuts] + [len(x)]
            pieces = [x[edges[k]:edges[k + 1]] for k in range(len(g))]
            per = [Q.pitch_verdict(Q.pitch_stats(y), (ref or {}).get("音高Hz"), gate["允许偏差半音"],
                                   gate["有声不足秒不判"]) for y in pieces]
            devs = [abs(p["偏差半音"]) for p in per if p.get("偏差半音") is not None]
            worst = max(devs) if devs else None
            whole = Q.pitch_verdict(Q.pitch_stats(x), (ref or {}).get("音高Hz"), gate["允许偏差半音"],
                                    gate["有声不足秒不判"])
            summary = dict(whole, 偏差半音=(round(worst, 2) if worst is not None else None),
                           超出=any(p.get("超出") for p in per),
                           整段偏差半音=whole.get("偏差半音"), 各章Hz=[p.get("音高中位数Hz") for p in per],
                           各章偏差半音=[p.get("偏差半音") for p in per])
            if summary["超出"]:
                bad = [f"第{g[k] + 1}章 {p['偏差半音']:+.1f}" for k, p in enumerate(per) if p.get("超出")]
                summary["说明"] = "有章超出：" + "、".join(bad) + " 个半音"
            out = {"音高": summary, "_cuts": cuts, "_pieces": pieces, "_per": per}
            if chk is not None:                      # 音色：切开后每章各判一段，整段按最差的那章算
                tv = [chk.segment(y, sr=Q.SR) for y in pieces]
                sims = [v["相似度"] for v in tv if v.get("判定") != "未判" and v.get("相似度") is not None]
                order = ["重录", "提醒", "通过"]
                verdict = next((o for o in order if any(v.get("判定") == o for v in tv)), "未判")
                out["音色"] = {"判定": verdict, "相似度": min(sims) if sims else None, "声音": chk.voice,
                               "各章相似度": [v.get("相似度") for v in tv], "各章判定": [v.get("判定") for v in tv],
                               **({"说明": "有章音色掉到重录线下"} if verdict == "重录" else {})}
                out["_tv"] = tv
            return out

        takes, best, info = taker.series(cfg, gtext, gest, tag, gi + 1, split_take)
        if not (ref and ref.get("音高Hz")):          # 没有参考音高：只为切开才量，不算音高把关
            for x in takes:
                x.pop("音高", None)
            if chk is None:
                info = None
        if best["qc"].get("需重录"):
            log(f"    ⚠ {tag} 重录后仍不理想，先用第{best['take']}条，需人工复听")
        cuts, pieces, per = best["_cuts"], best["_pieces"], best["_per"]
        # 切开后每章单独转写一遍，看首尾有没有切掉或多带了字
        piece_wavs = []
        for k, y in enumerate(pieces):
            pw = run / f"g{gi + 1}_ch{g[k] + 1:02d}_raw.wav"
            with wave.open(str(pw), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(Q.SR)
                w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
            piece_wavs.append(pw)
        hyps = Q.transcribe_many([(pw, run / "whisper_pieces") for pw in piece_wavs]) if qc else {}
        whole_rows.append({"整段": gi + 1, "章": [chapters[ci]["title"] for ci in g], "估计秒数": gest,
                           "选用第几条": best["take"], "共录几条": len(takes),
                           "切点": cuts, **{k: v for k, v in _gate_fields(best, info, ref).items() if k != "音高"},
                           "各条": [_take_row({k: v for k, v in x.items() if not k.startswith("_")}) for x in takes]})
        for k, ci in enumerate(g):
            ch_text = texts[ci]
            res = Q.check(spoken(ch_text), hyps[str(piece_wavs[k])]) if qc else {
                "需重录": False, "字错率": None, "原因": [], "最长多出": 0, "最长少掉": 0}
            if qc and res["需重录"]:
                log(f"    ⚠ 第{ci + 1}章切开后对稿：{'；'.join(res['原因'])}")
            norm, trimmed, ln = _post(piece_wavs[k], run / f"chapter{ci + 1:02d}")
            finals.append(norm)
            chapter_of.append(ci)
            chapter_srcs[ci] = [(pieces[k], Q.SR)]
            qc_rows.append({"块": ci + 1, "章": chapters[ci]["title"], "原稿": ch_text,
                            "汉字数": len(re.findall(HAN, ch_text)), "估计秒数": round(est_seconds(ch_text), 1),
                            "整段": gi + 1, "选用第几条": 1, "共录几条": 1,
                            "需人工复听": bool(best["qc"].get("需重录") or res["需重录"]),
                            **({"专名读音（请你耳听）": res["专名读音"]} if res.get("专名读音") else {}),
                            **({"数字单位（请你耳听）": res["数字单位"]} if res.get("数字单位") else {}),
                            **({"英文名漏念（请你耳听）": res["英文名漏念"]} if res.get("英文名漏念") else {}),
                            "去掉首尾静音秒数": round(trimmed, 2), "响度": ln,
                            **({"音高": per[k]} if ref and ref.get("音高Hz") else {}),
                            **({"音色": best["_tv"][k]} if best.get("_tv") else {}),
                            **({"音色需人工听": True} if best.get("_tv") and best["_tv"][k].get("判定") == "重录" else {}),
                            "_ref": ref,
                            "各条": [{"第几条": 1, "秒数": round(len(pieces[k]) / Q.SR, 2),
                                      "原始音频": f"{best['raw']}（整段第 {best['take']} 条，"
                                                  f"{edges_s(cuts, k, len(pieces[k]))}）",
                                      "finish_reason": best["finish"], **res}]})
    extra = {"整段合成": whole_rows, "为音高重录整段次数": 0}
    for r in whole_rows:
        if r.get("音高把关"):
            extra["为音高重录整段次数"] = extra.get("为音高重录整段次数", 0) + r["音高把关"].get("为音高再录", 0)
    tex = _timbre_finish(chk, chapters, chapter_of, qc_rows, log, chapter_srcs=chapter_srcs)
    if tex:
        tex["音色把关"]["为音色重录次数"] = sum((r.get("音色把关") or {}).get("为音色再录", 0) for r in whole_rows)
        extra.update(tex)
    res = _finish(chapters, None, finals, qc_rows, taker.calls, cfg, out_dir, run, title, qc, bitrate, keep_work,
                  log, None, chapter_wavs, chapter_of=chapter_of, extra_overall=extra,
                  extra_conf={"合成方式": "整段一次合成，按逐词时间切回各章"})
    return res


def edges_s(cuts, k, n_samples):
    a = cuts[k - 1]["秒"] if k > 0 else 0.0
    return f"{a:.2f}–{a + n_samples / Q.SR:.2f} 秒"


def main(argv=None):
    keys.install_excepthook()
    ap = argparse.ArgumentParser(description="frontier-daily 配音（用法见文件开头）")
    ap.add_argument("script", help="口播稿（Markdown 或纯文本）")
    ap.add_argument("--engine", choices=["gemini-api", "gemini", "mimo"])
    ap.add_argument("--model", help="gemini：flash（默认）/ lite / 完整模型名；mimo：一般不用填")
    ap.add_argument("--voice", help="gemini：声音 ID 或预置名；mimo：内置音色名（如 冰糖）")
    ap.add_argument("--style", help="风格说明（Gemini 放 speechMetadata.style，MiMo 放 user 消息）")
    ap.add_argument("--style-file")
    ap.add_argument("--style-map", help='按章节换语气的 JSON：{"章名": "风格说明"}；表里没有的章用 --style')
    ap.add_argument("--chapter-wavs", nargs="?", const="auto",
                    help="另存每章人声 WAV 给混音用；不写目录就放缓存 chapters/<产出目录名>/")
    ap.add_argument("--design", help="MiMo 声音设计的音色描述")
    ap.add_argument("--design-file")
    ap.add_argument("--clone-ref", help="MiMo 声音复刻的参考音频（wav/mp3）")
    ap.add_argument("--language-code", help="Gemini speechConfig.languageCode，默认不填（自动识别）")
    ap.add_argument("--out", help="产出目录")
    ap.add_argument("--title", help="写进 MP3 的标题")
    ap.add_argument("--plan", action="store_true", help="只看切块，不调模型")
    ap.add_argument("--fresh", action="store_true", help="不用缓存，全部重新合成")
    ap.add_argument("--no-qc", action="store_true", help="跳过 Whisper 对稿")
    ap.add_argument("--retakes", type=int, default=RETAKES)
    ap.add_argument("--bitrate", type=int, default=BITRATE_KBPS)
    ap.add_argument("--budget-usd", type=float, default=1.0)
    ap.add_argument("--pitch-ref", default="auto",
                    help="音高把关：auto（默认，按 voice_profile.json 找这个声音的参考音高，找不到就不把关）／off／直接给 Hz")
    ap.add_argument("--no-timbre-gate", action="store_true",
                    help="不做音色把关（默认按 pipeline/assets/voices/音色指纹/ 的档案把关；档案里没有的声音自动不把关）")
    ap.add_argument("--whole", action="store_true",
                    help="整段一次合成：几章放进同一次请求（像一次录完），再按逐词时间切回各章（只用 --style 一种语气）")
    # 第十轮（2026-11-01 晚）：下面四样默认开，各有一个开关关掉；四个都关时和原来逐字节相同
    ap.add_argument("--host", choices=["Shirley"],
                    help="按声音档案的主播配（Shirley＝主声音：Gemini Vertex＋声音 ID，不用再写 --engine、--voice）")
    ap.add_argument("--no-palette", action="store_true",
                    help="不用情绪色板：--style-map 的值原样当语气，也不自动补固定层（旧做法）")
    ap.add_argument("--no-sentence-level", action="store_true", help="不做句子级找平音量")
    ap.add_argument("--no-tempo-adjust", action="store_true", help="不做语速微调（只像原来那样在 qc.json 里标出）")
    ap.add_argument("--day-type", default="日常",
                    help="按哪一天的区间把关成片时长：日常（默认）／周六／周日，读对应写稿提示词文末\"程序检查\"的\"成片时长分钟\"；"
                         "也可以直接给提示词文件路径")
    ap.add_argument("--no-duration-gate", action="store_true", help="不把关成片时长（试音、只配几章时用）")
    ap.add_argument("--package", default="v3", help="估成片时长时按哪个声音包排（默认 v3，和 podcast_mix.py 一样）")
    ap.add_argument("--use-backup", action="store_true",
                    help="用声音档案的备用声音（Shirley 备用：MiMo 复刻，参考音、后期变速都从档案读；语气按色板的中文指导）")
    ap.add_argument("--no-backup-tempo", action="store_true",
                    help="用 MiMo 备用声音时不按 profile\"后期\"那一项变速（默认照做，和视频、对谈一样）")
    a = ap.parse_args(argv)
    if a.use_backup:
        bk = load_profile().get("备用声音") or {}
        a.engine, a.voice, a.model = "mimo", None, a.model or bk.get("模型")
        a.clone_ref = a.clone_ref or str(PIPE.parent / bk["参考音"])
    elif a.host:
        prof = load_profile()
        main_v = prof.get("主声音") or {}
        a.engine = a.engine or ("gemini" if str(main_v.get("引擎", "")).startswith("gemini") else None)
        a.voice = a.voice or main_v.get("声音ID")
        a.model = a.model or main_v.get("模型")

    text = Path(a.script).read_text(encoding="utf-8")
    if a.plan:
        chapters = parse_script(text)
        model = a.model
        if a.engine == "mimo" and not model:
            model = E.MIMO_DESIGN if (a.design or a.design_file) else None
        chunks = plan_chunks(chapters, CHUNK_MAX_BY_MODEL.get(model, CHUNK_MAX))
        for c in chunks:
            print(f"块{c['index'] + 1}【{c['chapter_title'] or '正文'}】{c['chars']} 字，估计 "
                  f"{c['est_seconds']:.0f} 秒：{c['text'][:30]}…")
        print(f"共 {len(chapters)} 章 {len(chunks)} 块，估计 {sum(c['est_seconds'] for c in chunks) / 60:.1f} 分钟")
        return 0
    if not a.engine or not a.out:
        ap.error("要给 --engine 和 --out（或者用 --plan 只看切块）")
    style = Path(a.style_file).read_text(encoding="utf-8").strip() if a.style_file else a.style
    design = Path(a.design_file).read_text(encoding="utf-8").strip() if a.design_file else a.design
    cfg = VoiceConfig(a.engine, model=a.model, voice=a.voice, style=style, design=design,
                      clone_ref=a.clone_ref, language_code=a.language_code)
    pitch_ref = None if str(a.pitch_ref).lower() in ("off", "none", "no", "0") else (
        "auto" if a.pitch_ref == "auto" else float(a.pitch_ref))
    duration = None
    if not a.no_duration_gate and not a.whole:
        rp = Path(a.day_type) if Path(a.day_type).suffix == ".md" else day_rules_path(a.day_type)
        rng = duration_rules(rp)
        if rng:
            duration = {"区间分钟": rng, "声音包": a.package, "规则": str(rp)}
        else:
            print(f"  时长把关：{rp} 里没有\"程序检查\"的\"成片时长分钟\"，这次不把关", file=sys.stderr)
    try:
        style_map = load_style_map(a.style_map) if a.style_map else None
        if a.whole:
            if style_map:
                print("注意：--whole 只用一种语气（--style），--style-map 不起作用", file=sys.stderr)
            make_episode_whole(a.script, cfg, a.out, title=a.title, ledger=Ledger(a.budget_usd), fresh=a.fresh,
                               qc=not a.no_qc, retakes=a.retakes, bitrate=a.bitrate, chapter_wavs=a.chapter_wavs,
                               pitch_ref=pitch_ref, timbre=not a.no_timbre_gate)
        else:
            res = make_episode(a.script, cfg, a.out, title=a.title, ledger=Ledger(a.budget_usd), fresh=a.fresh,
                               qc=not a.no_qc, retakes=a.retakes, bitrate=a.bitrate, style_map=style_map,
                               chapter_wavs=a.chapter_wavs, pitch_ref=pitch_ref, timbre=not a.no_timbre_gate,
                               palette=not a.no_palette, level=not a.no_sentence_level, tempo=not a.no_tempo_adjust,
                               duration=duration, backup_tempo=not a.no_backup_tempo)
            if not ((res.get("时长把关") or {}).get("配完按实际") or {}).get("通过", True):
                print("✗ 时长把关：" + res["时长把关"]["配完按实际"]["说明"] + "（音频已配好，先别混音发布）", file=sys.stderr)
                return 1
    except (BudgetExceeded, E.TTSError, keys.KeyReadDenied, RuntimeError, ValueError) as e:
        print(keys.hide(f"✗ {type(e).__name__}: {e}"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
