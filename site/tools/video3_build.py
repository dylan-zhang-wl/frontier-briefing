#!/usr/bin/env python3
"""视频 v3（一镜到底的今日地图）组装：旁白检查 → 配音 → 按配乐的拍子排章节、混音 → 逐字对齐 → 场景数据 → 演示页。

一条命令做完（在项目根运行；任何一天都一样，画面全由那一期的分镜 04_文稿/视频v3_分镜.json 决定，说明见 site/tools/README_video3.md）：
    PY=~/.venvs/frontier-daily/bin/python
    $PY site/tools/video3_build.py --day 2026-11-01               # 核对分镜 → 配音（旁白改了才配，只配改过的章）→ 排拍子、混音、对齐 → 写演示页
    $PY site/tools/video3_build.py 测试版/2026-10-31              # 也可以直接给一期的目录
    $PY site/tools/video3_build.py --day 2026-10-31 --revoice     # 强制重配（换了声音时；没改的章仍走缓存）

旁白怎么写：按 pipeline/prompts/写稿_视频v3.md（写旁白的模型拿它当系统提示）。本脚本配音前读它文末"程序检查"一段，
  逐条查旁白：有指画面、教操作的话（"看这根柱子""点任意一片"……）、出现"我"（不是"我们"）、读音表要改的写法，就停，不配音；
  字数超出范围只提醒。

声音：读 pipeline/voice_profile.json（用户定的声音档案，别处不写死声音 ID）。
    # 默认：主声音（10-31 晚定的庚A）：Gemini（Vertex），项目、声音 ID 都从档案读；每章语气后面加档案里那一句
    # 11-01 起：各章用同一句基础语气（GEMINI_STYLE），开场、收尾最多在"温暖""稍慢"上微调（check_video_styles 查，
    #   不许写更亮、更高、更有活力）；配完每章量音高，和档案里庚A 的参考音高比，差超过 1.5 个半音就重录（tts_qc 音高把关）；
    #   再查音色像不像庚A 的档案（pipeline/voice_print.py，低于 0.60 重录、和音高共用最多再录；--no-timbre-gate 关）。
    # 11-01 晚（第十轮）起：语气改由 pipeline/tts.py 的 compose_style 拼（和工作日、对谈同一个函数）：固定层＋这一章的情绪词，
    #   情绪词取分镜这一章的 "tone"（只认 voice_profile.json"情绪色板"里 Shirley 可用的词），没写按章种类的"按章默认"，再没有用默认词；
    #   --no-palette 回到上面那套。每章人声另做句子级找平（--no-sentence-level 关）；语速微调默认不做（--tempo-adjust 开）。
    #   --voice-mode chapters（默认，见 VOICE_MODE）每章单独请求，配完量音高，超出就只重录那一章；
    #   --voice-mode whole 整篇旁白一次请求 Gemini、像一次录完，再按逐词时间切回各章（tts.make_episode_whole）。
    #   11-01 两种各配了一次的比较写在 VOICE_MODE 旁边。
    $PY site/tools/video3_build.py 测试版/2026-10-31 --revoice
    # 备用声音（Gemini 出错或当月配音费到上限时）：档案里的 MiMo 声音复刻（乙稍快：参考音＋人声加快 1.09 倍）
    $PY site/tools/video3_build.py 测试版/2026-10-31 --revoice --engine mimo
    #   MiMo 内置音色：--engine mimo --voice 冰糖；临时换 Gemini 声音：--engine gemini --voice voice_…
    项目 gen-lang-client-0665640995 另有用途、不许用：tts_engines.GCP_PROJECT 指向它时本脚本拒绝调 Gemini。

配乐：site/tools/video3_music.py（Lyria 片头乐句和片尾收束；底乐 2026-11-02 起和播客默认声音包一样，按人声起止"避让"：
  说话时退后、停顿时浮上来；11-02 选定的是 Kevin MacLeod《Dreamer》）。
  章与章之间不再留固定秒数，而是等到配乐的下一条小节线：镜头在强拍上起飞，空隙里音乐浮起，开口前压下；
  收尾骑在片尾那段 Lyria 上，最后的收束和弦落在最后一个字之后。--no-music 只出人声（旧做法的固定空隙）。
  --music-style b2：11-02 以前的混法（B2 亮底乐＋空隙层、三拍子小节线），原样复现用。

做了什么：
  1. 读 04_文稿/视频旁白_v3.md（每个"## 章"是视频的一章），按上面的规则检查；
     稿子里的阿拉伯数字（字幕直接显示）配音前由 pipeline/spoken_numbers.py 转成念法（28.58% → 百分之二十八点五八）；
     按章配音（pipeline/tts.py，只读调用），每章人声另存一份 WAV；念法没变的章直接用配音缓存，不重配、不花钱；
  2. 按配乐的拍子排好每章几秒开口（video3_music.plan），把人声和配乐混成一条音轨
     05_配音/视频旁白_v3/video3.mp3（立体声，−16 LUFS，真峰值 ≤ −1 dBTP），另出只有人声的 video3_voice.mp3；
  3. 用本机 Whisper 在只有人声的那一条上取逐词时间，和旁白原文逐字对齐（site/tools/video_align.py，只读调用），
     把 CUES 里的触发词换成秒数——画面上每个动作都按旁白说到的那个名词、数字、日期出现；
     "@end" 表示"这一章的末尾"，也就是分界的小节线（镜头起飞的强拍）；
  4. 每期的画面写在分镜 04_文稿/视频v3_分镜.json 里（几章、每章用哪几个模板、字和数字、触发词；
     结构和模板见 site/tools/video3_storyboard.py，写法见 写稿_视频v3.md）。画面上的数字全部指到分镜的 facts，
     逐条到事件卡（03_事件卡/cards_写稿用.json）里核对原文，核不上就停；来源按网址对到网页 v3 的来源编号；
     配音用的旁白 04_文稿/视频旁白_v3.md 由分镜生成；旁白改了（念法指纹变了）会自动重配，没改的章用缓存；
  5. 写出演示页 11_视频v3/：index.html、data.js（场景数据，script 标签读入，双击就能打开，不用联网）、
     audio/、img/（2.5D 视差用的配图和深度图）、fonts/（按用到的字截取的小字体包）、vendor/。

  6. 配乐的署名、拍点写进视频数据的 music（网页拿 music.credit 署名；画面拿 music.beats 把镜头落点对到拍子上）。

时长：成片不超过 3 分钟。配音前按字数估（每章念法的估计秒数 × EST_FACTOR，再按配乐的排法加上片头、章间、片尾），
  超过 170 秒提醒、超过 180 秒停下不配音（两个数写在 写稿_视频v3.md 的"程序检查"里）；配完音按实际时长再查一遍，超过也停。

花费：MiMo 不花钱；Gemini 由 --budget-usd 封顶（默认 0.05 美元，含为音高重录）。同一章同一配置再跑会复用缓存，不重复花钱。
配乐只剪现成素材，不调生成模型，不花钱。

之后录预览视频和关键帧总览（Playwright 录屏，约 2.5 分钟）：
    node site/tools/video3_record.mjs 测试版/2026-10-31            # 浅色 预览.mp4 ＋ 关键帧总览.jpg
    node site/tools/video3_record.mjs 测试版/2026-10-31 --dark     # 深色 预览_深色.mp4

接进主页面（app.js 由主会话改）：把 11_视频v3/video3_media.json 的内容放进 issue.media.video（v: 3），
按需加载 vendor/three/three-bundle.min.js、vendor/gsap.min.js、video3.js、video3.css，
然后 FDVideo3.mount(容器, issue.media.video, videoCtx())；ctx.jumpSource 缺省时会用 window.FD.jumpSource。
字体：build_v3 截字时要把 video3_media.json 里的字（S、clusters、transcript）算进标题和正文字体。
配乐署名：video3_media.json 的 music.credit（zh / en）就是要在网页上写的那一行（CC BY 4.0 要求署名）；
  播放器自己会在"文字稿"面板末尾写一遍，网页的版权／来源区最好也写上。音轨仍是 audio/video3.mp3 一个文件。
voice.placeholder 已去掉（v3.1 起是定稿声音）；voice.name 是声音档案里的叫法（如"庚A"）。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import wave
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SITE = ROOT / "site"
PIPE = ROOT / "pipeline"
for p in (str(HERE), str(PIPE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import video_align  # noqa: E402  （只读调用：逐字对齐）
import video3_music as MUS  # noqa: E402  （配乐：按拍子排章节、混音）
from spoken_numbers import risky_numbers, spoken, spoken_script  # noqa: E402  （稿子写阿拉伯数字，配音前自动转念法）
import video3_storyboard as SB  # noqa: E402  （每期的视频分镜：读入、校验、核对事实、编成播放器数据）
import video3_images as IMG  # noqa: E402  （视频配图：缺图时生成或取资料图、记来源、出署名）
import video3_logos as LG  # noqa: E402  （品牌标志库：site/assets/logos/）
import video3_zhwrap as ZWRAP  # noqa: E402  （11-09：中文整词换行，开关"视频中文整词换行"）

# ============================ 可改区 ============================

STORYBOARD = "04_文稿/视频v3_分镜.json"         # 每期的视频分镜（写稿模型按 写稿_视频v3.md 写；本脚本只读它）
NARRATION = "04_文稿/视频旁白_v3.md"             # 配音用的旁白：由分镜里的 narration 生成，不手改
VOICE_DIR = "05_配音/视频旁白_v3"
OUT_DIR = "11_视频v3"
ISSUE_V3 = "10_网页v3/issues/{date}/issue.js"     # 网页 v3 的来源编号从这里对
RULES = PIPE / "prompts/写稿_视频v3.md"            # 旁白规则：写稿模型的系统提示；文末"程序检查"一段本脚本配音前逐条查
VOICE_PROFILE = PIPE / "voice_profile.json"        # 用户定的声音档案（主声音、备用声音、每章语气后加的那一句）

NO_MUSIC_TIMING = {"开头": 2.2, "章间": 1.1, "结尾": 2.6}   # 只在 --no-music 时用：固定空隙

# 备用声音之外的 MiMo（--engine mimo --voice 冰糖 这类内置音色）用这段导演提示
MIMO_STYLE = ("角色：一档中文科技日报短视频的画外音解说，三十岁上下的女声，说标准普通话。\n"
              "场景：观众在看一段解释新闻的动态画面，解说把新闻讲明白：发生了什么、数字、意味着什么。\n"
              "指导：清楚、沉稳、有温度，像纪录片解说；不播新闻腔，不夸张。语速与顿挫：中等偏快；"
              "数字前后留一点停顿。气声与实声：实声为主。咬字肌理：数字、百分比和英文名念清楚，英文按英文读。")
MIMO_STYLE_MAP = {                # 按章的种类（open / story / contrast / close）换语气
    "open": MIMO_STYLE.replace("指导：清楚、沉稳、有温度", "指导：温暖、有精神，带一点好奇"),
    "close": MIMO_STYLE.replace("语速与顿挫：中等偏快", "语速与顿挫：放慢一点，轻柔地收束"),
}
# Gemini 的语气（2026-11-01 改）：视频旁白要像一次录完的同一个人，和工作日播客的庚A 是同一个声音（档案"主声音"，
# 每章后面照旧补档案里那句"抬高约两个半音"）。所以各章用同一句基础语气；开场、收尾最多在"温暖""稍慢"上微调，
# 不许写更亮、更高、更有活力的说法——11-01 开场写了"Warm, bright and inviting"又叠上那句抬高，开场比别的章高了
# 约 6 个半音；收尾写了"slower and reflective"，慢了三成。基础语气照第四、五轮定稿样音的写法：只写情绪、语调、快慢，短。
# check_video_styles() 每次配音前按下面三条查，不合规矩就停。
GEMINI_STYLE = "composed and engaged, explaining the news to a friend; an even, natural pace; crisp on numbers, dates and names"
GEMINI_TWEAKS = {"open": "warm", "close": "warm, a touch slower"}       # 按章的种类；其余种类（story、contrast）不加
GEMINI_WHOLE_TWEAK = "warm at the start, a touch slower in the last paragraph"   # 整段一次合成时只有一句语气，微调写进去
STYLE_TWEAK_OK = (r"^(?:(?:warm|warmly|gentle|gently|soft|softly|slower|slowing|slightly|a touch|a little|a bit|unhurried|"
                  r"and|at the start|at the end|in the last paragraph|in the final paragraph)[\s,;.]*)+$")
STYLE_BANNED = (r"bright|high|energ|lively|upbeat|excit|cheer|enthusias|animated|punchy|vivid|inviting|pitch|register|"
                r"louder|faster|brisk|quick|rapid|dramatic|playful|curio|sparkl|bubbly|peppy")
RESERVED_GCP = "gen-lang-client-0665640995"   # 另有用途、不许用：不在这个项目上调 Gemini
VOICE_MODE = "chapters"         # 默认配音方式：chapters＝每章单独请求；whole＝整篇一次请求再切章（两种都加音高把关）
# 为什么默认分章（2026-11-01 用同一篇 11-01 旁白、同一句基础语气各配一次，量的是切好、统一响度后的每章人声）：
#   各章音高最高最低差：分章 1.87 个半音、整段 2.05（改前 6.3）——两者差在测量误差（约 0.2 个半音）以内；
#   离参考最远：分章 0.97 个半音、整段 1.69（开场，又高又慢：3.5 字／秒，比参考慢两成）；各章语速：分章 3.9–4.3 很齐，整段 3.5–4.5；
#   整段第一条里最后一章就高了 2.7 个半音——一次录完的长段里 Gemini 照样会漂，一章不过就得整段重录（每次约 $0.023），
#   分章只重录那一章（约 $0.005）。整段的好处是对稿字错率略低（3.0% 对 4.6%，差别都是 Whisper 听错人名、同音字）、
#   五个切点都落在 0.4–0.9 秒的静音里、切开后单独转写首尾没有多字少字，也就是切章本身是准的；所以留作 --voice-mode whole。
EST_FACTOR = 0.95               # 配音前估时长：tts.est_seconds 的估计 × 这个数≈实际人声秒数（庚A 旧语气 0.88–0.91，11-01 新语气 0.93；取稍保守）

PHOTO_DIRS = SB.PHOTO_DIRS     # 配图按这个顺序找：06_配图/视频 → v3.1 → v3 → 06_配图
EN_NAMES = PIPE / "prompts/英文名表.yaml"         # 公司、品牌、媒体的英文名（全站唯一一份）：所有英文显示字按它改大小写、查写法
DEPTH_PY = Path.home() / ".venvs/culture-in-translation/bin/python"      # 有 onnxruntime 的环境
DEPTH_MODEL = Path.home() / ".cache/culture-in-translation/models/depth-anything-v2-small/model.onnx"

# ==============================================================


def say(*a):
    print(*a, flush=True)


def ffprobe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def ffmpeg(args):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y"] + args, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("ffmpeg 失败：" + r.stderr[-600:])
    return r.stderr


# ---------------------------------------------------------------- 0. 旁白检查（规则在 pipeline/prompts/写稿_视频v3.md 文末）
def load_rules():
    import yaml
    txt = RULES.read_text(encoding="utf-8")
    m = re.search(r"## 程序检查[^\n]*\n+```yaml\n(.*?)```", txt, re.S)
    if not m:
        raise SystemExit("规则文件 %s 里找不到“程序检查”那段 yaml" % RULES)
    return yaml.safe_load(m.group(1))


def lint_narration(issue):
    """配音前按规则查旁白：指画面、教操作的话，"我"，读音表要改的写法 → 停；字数超范围 → 提醒。"""
    import tts            # noqa: E402
    import lexicon_check  # noqa: E402
    rules = load_rules()
    text = (issue / NARRATION).read_text(encoding="utf-8")
    chs = tts.parse_script(text)
    bad, warn, total = [], [], 0
    lim = rules.get("每章汉字数") or {}
    for c in chs:
        body = "".join(c["paras"])
        n = len(re.findall(r"[一-鿿]", spoken(body)[0]))     # 按念法数（数字转成汉字以后）
        total += n
        lo, hi = lim.get(c["title"]) or lim.get("其他") or (0, 10 ** 6)
        if not lo <= n <= hi:
            warn.append("「%s」%d 字（建议 %d–%d）" % (c["title"], n, lo, hi))
        for pat in rules.get("禁用说法") or []:
            for mm in re.finditer(pat, body):
                bad.append("「%s」里有“%s”（规则：%s）" % (c["title"], body[max(0, mm.start() - 6):mm.end() + 6], pat))
        for mm in re.finditer(r"我(?!们)", body):
            bad.append("「%s」里有“%s”：主播只说“我们”" % (c["title"], body[max(0, mm.start() - 6):mm.end() + 6]))
        for r in risky_numbers(body):        # 2026-11-02 晚加：配音前转不了、可能念错的数字写法（Q3、FY26、2026/27……），只提醒
            warn.append("「%s」里的“%s”：%s" % (c["title"], r["写法"], r["说明"]))
    lo, hi = rules.get("汉字数") or (0, 10 ** 6)
    if not lo <= total <= hi:
        warn.append("全篇 %d 个汉字（规则 %d–%d）" % (total, lo, hi))
    ncol = sum(len(re.findall(r"[：:](?!\d)", "".join(c["paras"]))) for c in chs)
    if rules.get("冒号上限") is not None and ncol > rules["冒号上限"]:
        warn.append("全篇 %d 个冒号（规则最多 %d 个；冒号解释腔改成逗号、句号或直接陈述）" % (ncol, rules["冒号上限"]))
    ents, extra, suffix, _v = lexicon_check.load_lexicon()
    res = lexicon_check.check(text, ents, extra, suffix)
    for r in res.get("要改") or []:
        bad.append("读音表：%s" % json.dumps({k: v for k, v in r.items() if not k.startswith("_")}, ensure_ascii=False))
    for r in (res.get("表里还没有") or []):
        warn.append("读音表里还没有：%s" % ((r.get("词") or r.get("英文")) if isinstance(r, dict) else r))
    say("旁白检查（%s）：%d 章、%d 个汉字" % (RULES.relative_to(ROOT), len(chs), total))
    for w in warn:
        say("  提醒：" + w)
    if bad:
        raise SystemExit("旁白不合规则，先改稿再配音：\n  " + "\n  ".join(bad))
    return total


# ---------------------------------------------------------------- 1. 配音
def load_profile():
    return json.loads(VOICE_PROFILE.read_text(encoding="utf-8"))


def check_video_styles(styles, suffix=""):
    """配音前查视频旁白的语气（规矩见上面 GEMINI_STYLE 的注释）：①每一条都以同一句基础语气为主体；②开场、收尾加的微调
    只能是"温暖""稍慢"这类词（STYLE_TWEAK_OK）；③不许出现更亮、更高、更有活力的说法（STYLE_BANNED）。
    档案里那句"抬高约两个半音"是这个声音的固定设置，先去掉再查。不合规矩就停。"""
    bad = []
    for t, st in styles.items():
        core = st.strip()
        if suffix and core.endswith(suffix):
            core = core[:-len(suffix)].strip()
        if GEMINI_STYLE not in core:
            bad.append("「%s」没用基础语气：%s" % (t, core))
            continue
        tweak = core.replace(GEMINI_STYLE, "").strip(" ;,.")
        if re.search(STYLE_BANNED, core, re.I):
            bad.append("「%s」有更亮、更高、更有活力一类的说法：%s" % (t, re.search(STYLE_BANNED, core, re.I).group(0)))
        if tweak and not re.match(STYLE_TWEAK_OK, tweak, re.I):
            bad.append("「%s」的微调只能是温暖、稍慢一类：%s" % (t, tweak))
    if bad:
        raise SystemExit("视频旁白的语气不合规矩（各章同一句基础语气，开场收尾只许温暖、稍慢）：\n  " + "\n  ".join(bad))


def voice_plan(issue, a, sb):
    """这一期要怎么配：返回 {cfg, style_map（整段时为 None）, mode, tempo, name}。voice() 和"现有配音是不是这套设置"的检查共用。"""
    import tts               # noqa: E402  （只读调用 pipeline/tts.py）
    import tts_engines as E  # noqa: E402
    prof = load_profile()
    kinds = {c["title"]: c["kind"] for c in sb["chapters"]}
    titles = [c["title"] for c in tts.parse_script((issue / NARRATION).read_text(encoding="utf-8"))]
    tempo, mode = 1.0, a.voice_mode
    if a.engine == "gemini":
        main_v = prof["主声音"]
        project = (main_v.get("项目") or "").split("（")[0].strip()
        if getattr(E, "GCP_PROJECT", "") == RESERVED_GCP and not a.allow_reserved_gcp:
            raise SystemExit("停：pipeline/tts_engines.py 的 GCP_PROJECT 还是 %s（那笔赠金留给大论文）。" % RESERVED_GCP)
        if project and project != E.GCP_PROJECT:
            raise SystemExit("停：声音档案写的项目是 %s，pipeline/tts_engines.py 的 GCP_PROJECT 是 %s，两边对不上。"
                             % (project, E.GCP_PROJECT))
        extra = main_v.get("每章语气后面都加这一句", "").strip()
        add = (lambda st: (st + ". " + extra).strip() if extra else st)
        host = main_v.get("角色名") if not a.voice else None
        palette = host and not getattr(a, "no_palette", False)
        if palette:
            # 第十轮（2026-11-01 晚）：和工作日、对谈同一个函数拼语气（pipeline/tts.py 的 compose_style）：固定层＋这一章的情绪词。
            # 情绪词：分镜这一章写了 "tone" 就用它（只认色板里的词），没写按章种类的"按章默认"（open、close），再没有用默认词
            tones = {c["title"]: c.get("tone") for c in sb["chapters"]}
            recs = {t: tts.compose_style(host, tones.get(t), kinds.get(t)) for t in titles}
            style_map = {t: r[0] for t, r in recs.items()}
            whole_style = tts.compose_style(host, None, None)[0]
            palette_rec = {t: r[1] for t, r in recs.items()}
            for t, r in palette_rec.items():
                if r.get("说明"):
                    say("  情绪色板：「%s」%s" % (t, r["说明"]))
            words = dict({t: r["情绪词"] for t, r in palette_rec.items()}, 整段=tts.compose_style(host, None, None)[1]["情绪词"])
            for t, st in dict(style_map, 整段=whole_style).items():       # 固定层里不许有更亮、更高的字眼（情绪词已按色板实测过）
                w_ = words.get(t) or ""
                core = st.replace(extra, "").replace("; mood: " + w_, "").replace(w_ + "; ", "").strip(" .")
                if GEMINI_STYLE not in core or re.search(STYLE_BANNED, core.replace(GEMINI_STYLE, ""), re.I):
                    raise SystemExit("视频旁白的语气不合规矩（固定层要是基础语气）：「%s」%s" % (t, st))
        else:
            palette_rec = None

        def chapter_style(kind):
            tw = GEMINI_TWEAKS.get(kind)
            return ("%s; %s" % (tw, GEMINI_STYLE)) if tw else GEMINI_STYLE
        if not palette:
            style_map = {t: add(chapter_style(kinds.get(t))) for t in titles}
            whole_style = add("%s; %s" % (GEMINI_STYLE, GEMINI_WHOLE_TWEAK))
            check_video_styles(dict(style_map, 整段=whole_style), extra)
        if mode == "whole":
            cfg = tts.VoiceConfig("gemini", main_v.get("模型") or "flash", a.voice or main_v["声音ID"], whole_style)
            style_map = None
        else:
            cfg = tts.VoiceConfig("gemini", main_v.get("模型") or "flash", a.voice or main_v["声音ID"],
                                  whole_style if palette else add(GEMINI_STYLE))
        name = main_v.get("叫法") if not a.voice else a.voice
    else:
        palette_rec = None
        mode = "chapters"           # MiMo 只按章配（备用声音）
        if a.voice:
            cfg = tts.VoiceConfig("mimo", voice=a.voice, style=MIMO_STYLE)
            name = a.voice
        else:
            bk = prof["备用声音"]
            ref = Path(a.clone_ref) if a.clone_ref else PIPE.parent / bk["参考音"]
            if not ref.exists():
                raise SystemExit("找不到备用声音的参考音频：%s（或用 --voice 冰糖 改用内置音色）" % ref)
            cfg = tts.VoiceConfig("mimo", style=MIMO_STYLE, clone_ref=str(ref))
            m = re.search(r"atempo=([\d.]+)", bk.get("后期", ""))
            tempo = float(m.group(1)) if m else 1.0
            name = bk.get("叫法")
        host = tts.host_of(cfg, mimo=True) if not getattr(a, "no_palette", False) else None
        if host:
            # 第十轮（11-01 晚）：Shirley 的 MiMo 复刻备用也按色板换情绪：和 Gemini 同一个函数（tts.compose_style，mimo="视频"），
            # 分镜这一章的 tone → 中文指导；没写按章种类的默认；这个词对 MiMo 没过线就用视频模板的默认情绪。--no-palette 回到下面那套
            tones = {c["title"]: c.get("tone") for c in sb["chapters"]}
            recs = {t: tts.compose_style(host, tones.get(t), kinds.get(t), mimo="视频") for t in titles}
            style_map = {t: r[0] for t, r in recs.items()}
            palette_rec = {t: r[1] for t, r in recs.items()}
            cfg = cfg.with_style(tts.compose_style(host, None, None, mimo="视频")[0])
        else:
            style_map = {t: MIMO_STYLE_MAP.get(kinds.get(t), MIMO_STYLE) for t in titles}
    return {"cfg": cfg, "style_map": style_map, "mode": mode, "tempo": tempo, "name": name, "palette": palette_rec}


def voice(issue, a, sb):
    import tts               # noqa: E402  （只读调用 pipeline/tts.py）
    script = issue / NARRATION
    out = issue / VOICE_DIR
    vp = voice_plan(issue, a, sb)
    cfg, style_map, mode, tempo = vp["cfg"], vp["style_map"], vp["mode"], vp["tempo"]
    if a.engine == "gemini":
        say("声音：%s（%s，%s）；%s" % (vp["name"], cfg.voice, cfg.model,
                                     "整段一次合成再切章" if mode == "whole" else "每章单独合成"))
    elif tempo != 1.0:
        say("声音：备用 %s（MiMo 声音复刻，人声后期变速 ×%.2f，不改音高）" % (vp["name"], tempo))
    chap_dir = Path.home() / ".cache/frontier-daily/tts/chapters" / ("video3_" + issue.name)
    say("配音：", cfg.describe())
    # 稿子里的阿拉伯数字配音前转成念法（字幕仍显示稿子原文）；没改的章念法和上次一样，配音缓存直接复用、不花钱
    spoken_md = spoken_script(script.read_text(encoding="utf-8"))
    latin = list(dict.fromkeys(re.findall(r"[A-Za-z][A-Za-z0-9&.\-]+", spoken_md.split("\n## ", 1)[-1])))
    common = dict(title="今日地图 · %s" % issue.name, ledger=tts.Ledger(a.budget_usd), fresh=a.fresh,
                  chapter_wavs=str(chap_dir), pitch_ref=None if a.no_pitch_gate else "auto",
                  timbre=not getattr(a, "no_timbre_gate", False))    # 音色把关（voice_print）：每章每条判段、每章判章、整期判一次
    if vp.get("palette") and not a.no_pitch_gate:     # 第十轮：色板词标了"不补抬高那句"时，音高仍按"带抬高那句"的参考比
        import tts_qc as Q   # noqa: E402
        common["pitch_ref"] = Q.reference_for(cfg, raised=True) or "auto"
    if mode != "whole":       # 第十轮：句子级找平、语速微调（各有开关；都关时和原来逐字节相同）
        # 语速微调默认不开：11-01 视频各章 3.9–4.2 字／秒，比播客参考 4.48 慢 6–12%（旁白本来就慢一点，数字多的段落按"字"数也偏少），
        # 照播客参考调会把整条视频加快 3–8%；要视频自己的参考语速再说，先用 --tempo-adjust 手动开
        common.update(level=not getattr(a, "no_sentence_level", False), tempo=bool(getattr(a, "tempo_adjust", False)))
    if mode == "whole":
        res = tts.make_episode_whole(spoken_md, cfg, str(out), prompt="以下是简体中文的科技新闻解说" +
                                     ("：" + "、".join(latin) if latin else "") + "。", **common)
    else:
        res = tts.make_episode(spoken_md, cfg, str(out), style_map=style_map, **common)
    if vp.get("palette"):        # 情绪色板的记录（每章用了哪个词、有没有换成默认词）写进 qc.json，和工作日、对谈一样
        qp = out / "qc.json"
        d = json.loads(qp.read_text(encoding="utf-8"))
        d["整集"]["情绪色板"] = {"主播": "Shirley", "各章": vp["palette"],
                              "换成默认词的章": [t for t, r in vp["palette"].items() if r.get("说明")]}
        qp.write_text(json.dumps(d, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    files = [c["文件"] for c in res["chapter_wavs"]]
    if len(files) != len(sb["chapters"]):
        raise SystemExit("旁白配出 %d 章，分镜有 %d 章" % (len(files), len(sb["chapters"])))
    # 每章人声留一份在配音目录里（以后只重排、重混、重对齐时用，不必重配）
    keep = out / "chapters"
    keep.mkdir(exist_ok=True)
    for old in keep.glob("*.wav"):
        old.unlink()
    for f in files:
        dst = keep / Path(f).name
        if tempo != 1.0:      # 备用声音：只改快慢、不改音高
            ffmpeg(["-i", str(f), "-af", "atempo=%.3f" % tempo, "-ar", "24000", "-ac", "1", str(dst)])
        else:
            shutil.copy2(f, dst)
    (out / "voice.json").write_text(json.dumps(
        {"engine": cfg.engine, "model": cfg.model, "voice": cfg.voice, "叫法": vp["name"],
         "tempo": tempo, "mode": mode, **({"style": cfg.style} if mode == "whole" else {}), "styles": style_map,
         **({"情绪色板": vp["palette"]} if vp.get("palette") else {}),
         "spoken_sha": spoken_sha(issue), "音高把关": (res["整集"] or {}).get("音高把关"),
         "音色把关": (res["整集"] or {}).get("音色把关"),
         "定于": datetime.now().strftime("%Y-%m-%d %H:%M")},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def check_length(sb, rules, actual=None):
    """成片时长：actual 不给就按字数估（配音前），给了就是配完音排好拍子的实际秒数。
    超过"时长提醒秒"提醒，超过"时长上限秒"停（两个数在 写稿_视频v3.md 文末"程序检查"里）。返回秒数。"""
    import tts  # noqa: E402
    warn_s, max_s = float(rules.get("时长提醒秒") or 170), float(rules.get("时长上限秒") or 180)
    if actual is None:
        sec = SB.estimate_duration(sb, lambda t: tts.est_seconds(spoken(t)[0]), MUS.plan, EST_FACTOR)
        how = "按字数估约"
    else:
        sec, how = actual, "配完音实际"
    if sec > max_s:
        raise SystemExit("视频%s %.0f 秒，超过上限 %.0f 秒（3 分钟）：删短旁白再配（写稿_视频v3.md：按内容定长短，最长 3 分钟）"
                         % (how, sec, max_s))
    say("时长：%s %.0f 秒（上限 %.0f 秒）" % (how, sec, max_s) + ("；超过 %.0f 秒，偏长" % warn_s if sec > warn_s else ""))
    if sec > warn_s:
        say("  提醒：视频%s %.0f 秒，超过 %.0f 秒，接近 3 分钟上限" % (how, sec, warn_s))
    return sec


# ---------------------------------------------------------------- 2. 按配乐的拍子排章节、混音
def assemble(issue, sb, music=True):
    vdir = issue / VOICE_DIR
    wavs = sorted((vdir / "chapters").glob("*.wav"))
    ids = [c["id"] for c in sb["chapters"]]
    if len(wavs) != len(ids):
        raise SystemExit("配音目录里有 %d 章人声（分镜要 %d 章）：先加 --revoice 配音" % (len(wavs), len(ids)))
    lens = []
    for w in wavs:
        with wave.open(str(w)) as f:
            if f.getnchannels() != 1:
                raise SystemExit("%s 不是单声道" % w)
            lens.append(f.getnframes() / f.getframerate())
    if music:
        pl = MUS.plan(lens)
    else:
        t = NO_MUSIC_TIMING
        pl = MUS.plan_fixed(lens, t["开头"], [t["章间"]] * (len(lens) - 1), t["结尾"])
    mp3, vmp3 = vdir / "video3.mp3", vdir / "video3_voice.mp3"
    meas = MUS.render(pl, [str(w) for w in wavs], mp3, vmp3, "今日地图 · %s（视频 v3）" % issue.name, log=say)
    dur = pl["duration"]
    marks = []
    for i, cid in enumerate(ids):
        marks.append({"chapter": cid, "voice_start": pl["voice_starts"][i], "voice_end": pl["voice_ends"][i],
                      "end": pl["bounds"][i] if i < len(pl["bounds"]) else round(dur, 3)})
    (vdir / "video3_chapters.json").write_text(json.dumps(
        {"说明": ("video3.mp3 里每章人声的起止秒；end 是这一章和下一章的分界——配乐的小节线（镜头在这个强拍上起飞）。"
                "排法见 site/tools/video3_music.py。" if music else "video3.mp3 只有人声（--no-music），章间固定空隙 %s 秒" % NO_MUSIC_TIMING["章间"]),
         "duration": dur, "chapters": marks, "plan": {k: v for k, v in pl.items() if k not in ("beats", "downbeats")},
         "混音实测": meas}, ensure_ascii=False, indent=1), encoding="utf-8")
    say("排好 %s：%.1f 秒（人声 %.1f 秒）" % (mp3.relative_to(issue), dur, sum(m_["voice_end"] - m_["voice_start"] for m_ in marks)))
    for i, m_ in enumerate(marks[:-1]):
        w = (pl.get("waits") or [{}] * len(marks))[i]
        say("  %-9s 说到 %6.2f，分界小节线 %6.2f（等 %.2f 秒），下一章 %6.2f 开口" % (
            m_["chapter"], m_["voice_end"], m_["end"], m_["end"] - m_["voice_end"], marks[i + 1]["voice_start"]))
    if music:
        say("  片尾从 Lyria 第 %d 拍起；收束拍在 %.2f 秒（最后一个字 %.2f 秒）" % (pl["outro_from_beat"], pl["resolve_at"], marks[-1]["voice_end"]))
    return mp3, vmp3, marks, dur, pl, meas


# ---------------------------------------------------------------- 3. 逐字对齐
def narrations(issue):
    import tts  # noqa: E402
    chs = tts.parse_script((issue / NARRATION).read_text(encoding="utf-8"))
    if not chs:
        raise SystemExit("旁白是空的：%s" % (issue / NARRATION))
    return [c["title"] for c in chs], ["".join(c["paras"]) for c in chs]


def to_display(al, shown, dur):
    """对齐是在念法上做的（和配音一模一样的字）；这里把每个字的时间映射回稿子原文（字幕显示的阿拉伯数字）。
    没转的字一一对应；转过的一段（如"百分之二十八点五八"↔"28.58%"），稿子里那几个字均分这一段念法的时间。"""
    by = {(u["scene"], u["i"]): u for u in al["units"]}
    units = []
    for si, text in enumerate(shown):
        _sp, src = spoken(text)
        groups = {}
        for j, (a, b) in enumerate(src):
            u = by.get((si, j))
            if u:
                g = groups.setdefault((a, b), [u["s"], u["e"]])
                g[0], g[1] = min(g[0], u["s"]), max(g[1], u["e"])
        for (a, b), (t0, t1) in sorted(groups.items()):
            ks = [k for k in range(a, b) if video_align.is_unit(text[k])]
            for n, k in enumerate(ks):
                units.append({"c": text[k].lower(), "scene": si, "i": k,
                              "s": round(t0 + (t1 - t0) * n / len(ks), 3), "e": round(t0 + (t1 - t0) * (n + 1) / len(ks), 3)})
    units.sort(key=lambda u: (u["scene"], u["i"]))
    return dict(al, units=units, narrations=list(shown), scenes=video_align.scene_spans(units, shown),
                sentences=video_align.spans(units, shown, video_align.SENT_END),
                cues=video_align.subtitle_cues(units, shown, dur))


def align(issue, vmp3, marks, dur, sb):
    """在只有人声的那一条（时间轴和成片一样）上对齐：配乐不干扰 Whisper。
    比对用念法（和配音一样的字），再映射回稿子原文：字幕、触发词都按稿子上的写法（阿拉伯数字）。"""
    titles, shown = narrations(issue)
    narr = [spoken(t)[0] for t in shown]
    latin = list(dict.fromkeys(re.findall(r"[A-Za-z][A-Za-z0-9&.\-]+", "".join(narr))))
    cache = issue / VOICE_DIR / "whisper_words.json"
    words = video_align.load_words(str(vmp3), str(cache),
                                   prompt="以下是简体中文的科技新闻解说" + ("：" + "、".join(latin) if latin else "") + "。")
    if not words:
        raise SystemExit("没有逐词时间：本机找不到 mlx_whisper（%s）" % video_align.WHISPER_BIN)
    al = to_display(video_align.align(narr, words, str(vmp3), round(dur, 3), [m["voice_start"] for m in marks]), shown, round(dur, 3))
    narr = shown
    T, miss = {}, []
    for key, i, spec in SB.cue_list(sb):
        say_, off = spec["say"], spec["offset"]
        if say_ in ("@end", "@start"):           # 这一章的末尾（分界的小节线）/ 开头
            v = marks[i]["end"] if say_ == "@end" else (0.0 if i == 0 else marks[i - 1]["end"])
            T[key] = T[key + ".end"] = round(v + off, 3)
            continue
        f = video_align.find(al, say_, after=marks[i]["voice_start"] - 0.3, scene=i)
        if not f:
            miss.append("%s（%s）" % (key, say_))
            continue
        T[key] = round(f[0] + off, 3)
        T[key + ".end"] = round(f[1] + off, 3)
    if miss:
        raise SystemExit("旁白里找不到这些触发词：" + "；".join(miss))
    T["open.go"] = T["open.go.end"] = marks[0]["end"]     # 开场结束的那条小节线：镜头俯冲向第一片
    return al, T, titles, narr


# ---------------------------------------------------------------- 4. 分镜：读入、校验、核对事实（规则在 site/tools/video3_storyboard.py）
def spoken_sha(issue):
    """配音用的念法的指纹：分镜里的旁白改了，这个就变（据此决定要不要重配）。"""
    p = issue / NARRATION
    return hashlib.sha1(spoken_script(p.read_text(encoding="utf-8")).encode()).hexdigest()[:16] if p.exists() else None


def en_registry():
    """读 pipeline/prompts/英文名表.yaml（全站唯一一份）：[{zh: [中文写法…], en: 规范英文名, bad: [明确不用的写法…]}]。没有这个文件就空。"""
    if not EN_NAMES.exists():
        return []
    try:
        import yaml
        d = yaml.safe_load(EN_NAMES.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        say("  提醒：英文名表读不了（%s）" % e)
        return []
    out = []

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("en"), str) and x.get("zh"):
                zh = x["zh"] if isinstance(x["zh"], list) else [x["zh"]]
                note = str(x.get("note") or "")
                bad = re.findall(r"不[要再]写\s*([A-Za-z0-9][A-Za-z0-9 .&’'-]*[A-Za-z0-9])", note)       # 注里写明"不要写 X""不再写 X"
                for m in re.findall(r"有\s*([A-Za-z][^。；;]*?)\s*等写法", note):                    # "媒体有 A、B、C 等写法"
                    bad += [b.strip() for b in re.split(r"[、,，]", m) if b.strip()]
                out.append({"zh": [str(z) for z in zh if z], "en": x["en"], "bad": [b for b in bad if b != x["en"]]})
                return
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(d)
    return out


def en_fix(text, reg):
    """英文显示字按英文名表改成规范写法：大小写不同的（SanDisk → Sandisk、SK Hynix → SK hynix）和表里注明不用的写法（IT Home → ITHome）。
    返回 (改好的字, [(原写法, 规范写法)])。只改带大写字母的匹配，免得误改普通英文单词。"""
    changes = []
    for e in reg:
        for var in [e["en"]] + e["bad"]:
            pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(var) + r"(?![A-Za-z0-9])", re.I)

            def sub(m, e=e):
                got = m.group(0)
                if got == e["en"] or not re.search(r"[A-Z]", got):
                    return got
                changes.append((got, e["en"]))
                return e["en"]
            text = pat.sub(sub, text)
    return text, changes


def en_check_label(zh, en, reg):
    """一处中英成对的字：中文里出现了表里的名字，英文里却没有规范写法 → 返回 [(中文名, 规范英文名)]。"""
    miss = []
    for e in reg:
        z = next((z for z in e["zh"] if z and z in zh), None)
        if not z:
            continue
        can = re.sub(r"^the\s+", "", e["en"], flags=re.I)
        if can not in en:
            miss.append((z, e["en"]))
    return miss


def en_names_apply(x, reg, where, warn):
    """递归：所有 {zh, en} 成对的字（分镜、热点卡、标志名、署名）按英文名表改大小写、改掉明确不用的写法；对不上的提醒。"""
    if isinstance(x, dict):
        if isinstance(x.get("en"), str):
            fixed, ch = en_fix(x["en"], reg)
            for a, b in ch:
                warn.append("英文名表：%s 的「%s」改成「%s」" % (where, a, b))
            x["en"] = fixed
            if isinstance(x.get("zh"), str):
                for z, can in en_check_label(x["zh"], fixed, reg):
                    warn.append("英文名表：%s 中文有「%s」，英文应写 %s（现在：%s）" % (where, z, can, fixed))
        for k, v in x.items():
            if not (isinstance(v, str) and k in ("m", "src", "depth", "url", "page", "from", "file")):
                en_names_apply(v, reg, where + "." + str(k), warn)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            en_names_apply(v, reg, "%s[%d]" % (where, i), warn)


def en_name_warnings(sb, reg):
    """分镜里的英文字和英文名表对不上的 → 提醒（构建时显示的字会按表改大小写；中文名对应的英文写错了要改分镜）。"""
    warn = []
    import copy
    for c in sb["chapters"]:
        for k in ("chip", "note", "end", "blocks", "label"):
            if c.get(k):
                en_names_apply(copy.deepcopy(c[k]), reg, "%s.%s" % (c["id"], k), warn)
    if sb.get("title"):
        en_names_apply(copy.deepcopy(sb["title"]), reg, "title", warn)
    return warn


def prepare(issue, gen=True):
    """读分镜 → 补配图（image_requests）→ 结构检查（数据不够的模板去掉）→ 事实、数字、原话、标志核对 → 写配音用的旁白 → 触发词对旁白。核不上就停。"""
    sb = SB.load(issue / STORYBOARD)
    if SB.motion_off():               # 11-07：新动效总开关关着 → 组装前去掉新块和新字段，退回 11-06 以前的画法（开着时什么都不做）
        for w in SB.strip_motion(sb):
            say("  提醒：" + w)
    sb["_img_meta"] = IMG.ensure(issue, SB.image_requests(sb), sb.get("accent"), gen=gen)
    for w in SB.structure(sb, issue):
        say("  提醒：" + w)
    cards = {c["event_id"]: c for c in json.loads((issue / "03_事件卡/cards_写稿用.json").read_text(encoding="utf-8"))}
    facts = SB.check_facts(sb, cards)
    reg = en_registry()
    SB.NAME_TOKENS = sorted({t for e in reg for t in [e["en"]] + e["zh"] if re.search(r"\d", t) and re.search(r"[A-Za-z]", t)})
    n = SB.check_labels(sb, facts)
    for w in SB.check_posts(sb, facts) + SB.check_logos(sb, facts) + SB.check_layers(sb) + en_name_warnings(sb, reg) + SB.source_warnings(sb):
        say("  提醒：" + w)
    md = SB.narration_md(sb)
    p = issue / NARRATION
    if not p.exists() or p.read_text(encoding="utf-8") != md:
        p.write_text(md, encoding="utf-8")
    SB.check_cues(sb, video_align.norm)
    say("分镜：%d 章（%s），%d 个模板，%d 条事实、%d 处字已核对" % (
        len(sb["chapters"]), "、".join(c["id"] for c in sb["chapters"]), sum(len(c.get("blocks") or []) for c in sb["chapters"]), len(facts), n))
    return sb, cards, facts


# ---------------------------------------------------------------- 5. 来源：按网址对到网页 v3 的编号
def norm_url(u):
    u = (u or "").strip().split("#", 1)[0]
    m = re.match(r"^(https?)://([^/]+)(.*)$", u, re.I)
    if m:
        u = m.group(1).lower() + "://" + m.group(2).lower().replace("www.", "") + m.group(3)
    return u.rstrip("/")


def issue_sources(issue):
    p = issue / ISSUE_V3.format(date=issue.name)
    if not p.exists():
        return {}
    s = p.read_text(encoding="utf-8")
    m = re.search(r"window\.FD_ISSUES\[[^\]]+\]\s*=\s*(\{.*\});\s*$", s, re.S)
    if not m:
        return {}
    d = json.loads(m.group(1))
    return {norm_url(x["url"]): x for x in d.get("sources", [])}


# ---------------------------------------------------------------- 6. 配图：2.5D 视差用的图和深度图
DEPTH_CODE = r"""
import sys, numpy as np, onnxruntime as ort
from PIL import Image, ImageFilter
src, dst, model = sys.argv[1:4]
img = Image.open(src).convert("RGB")
w, h = img.size
k = 518 / min(w, h)
nw, nh = int(round(w * k / 14)) * 14, int(round(h * k / 14)) * 14
x = np.asarray(img.resize((nw, nh), Image.BICUBIC), dtype=np.float32) / 255.0
x = (x - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
sess = ort.InferenceSession(model, providers=["CPUExecutionProvider"])
d = np.squeeze(sess.run(None, {sess.get_inputs()[0].name: x.transpose(2, 0, 1)[None].astype(np.float32)})[0])
d = (d - d.min()) / (d.max() - d.min() + 1e-6)
im = Image.fromarray((d * 255).astype(np.uint8)).resize((768, int(768 * h / w)), Image.BICUBIC)
im.filter(ImageFilter.GaussianBlur(2.2)).save(dst, quality=90)
"""


def prep_photos(issue, out, sb):
    """画面里用到的配图：背景窗（image_card，带深度图做 2.5D）、小卡上半截（tile_row 的 items[].image）、帖子卡题图（post_card.image）。"""
    imgs = {}
    (out / "img").mkdir(parents=True, exist_ok=True)
    meta = sb.get("_img_meta") or {}
    for c in sb["chapters"]:
        for b in c.get("blocks") or []:
            if b["type"] == "image_card":
                imgs.update(prep_one(issue, out, b["id"], b["image"], meta, sb.get("accent"), depth=True))
            elif b["type"] == "post_card" and b.get("image"):
                imgs.update(prep_one(issue, out, b["id"], b["image"], meta, sb.get("accent"), depth=False, size=1200))
            elif b["type"] == "tile_row":
                for i, it in enumerate(b.get("items") or []):
                    if isinstance(it, dict) and it.get("image"):
                        imgs.update(prep_one(issue, out, "%s.items%d" % (b["id"], i), it["image"], meta, sb.get("accent"), depth=False, size=1000))
    keep = set()                       # 演示页目录是生成的：这一期没用到的旧配图删掉（深度图的指纹文件跟着它的图留）
    for ph in imgs.values():
        for k in ("src", "depth"):
            if ph.get(k):
                keep.add(Path(ph[k]).name)
                keep.add(Path(ph[k]).stem.replace("_depth", "_depth") + ".sha")
    for f in (out / "img").iterdir():
        if f.is_file() and f.name not in keep:
            f.unlink()
    return imgs


def prep_one(issue, out, key, name, meta, accent, depth=True, size=1600):
    from PIL import Image
    imgs = {}
    if True:
        src = SB.find_image(issue, name)
        if not src:
            say("注意：找不到配图 %s，这一块不带图" % name)
            return imgs
        kind = (meta.get(src.stem) or {}).get("kind") or "generated"
        stem = src.stem + ("" if size >= 1600 else "_%d" % size)
        im = Image.open(src).convert("RGB")
        im.thumbnail((size, size))
        if kind == "commons":          # 资料图：轻轻往当天的色调靠
            im = IMG.grade(im, accent)
        im.save(out / "img" / (stem + ".webp"), quality=80, method=6)
        if not depth:
            imgs[key] = {"src": "img/%s.webp" % stem, "depth": None, "w": im.size[0], "h": im.size[1], "kind": kind, "file": src.stem,
                         "from": str(src.relative_to(issue))}
            return imgs
        dep = out / "img" / (stem + "_depth.webp")
        # 深度图只依赖原图：原图没变就不重算
        sha = hashlib.sha1(src.read_bytes()).hexdigest()[:12]
        stamp = out / "img" / (stem + "_depth.sha")
        if not (dep.exists() and stamp.exists() and stamp.read_text() == sha):
            if DEPTH_PY.exists() and DEPTH_MODEL.exists():
                r = subprocess.run([str(DEPTH_PY), "-I", "-B", "-c", DEPTH_CODE, str(src), str(dep), str(DEPTH_MODEL)],
                                   capture_output=True, text=True)
                if r.returncode:
                    say("注意：深度图没算出来（%s），%s 退成平面缓推" % (r.stderr.strip()[-200:], name))
                else:
                    stamp.write_text(sha)
            else:
                say("注意：本机没有深度模型，%s 退成平面缓推" % name)
        imgs[key] = {"src": "img/%s.webp" % stem, "depth": ("img/%s_depth.webp" % stem) if dep.exists() else None,
                     "w": im.size[0], "h": im.size[1], "kind": kind, "file": src.stem, "from": str(src.relative_to(issue))}
    return imgs


# ---------------------------------------------------------------- 7. 字体：按用到的字截取（演示页用；接进主页面时由 build_v3 统一截）
def subset_fonts(out, title_text, body_text, latin_text):
    try:
        from fontTools import subset as ftsubset
        sys.path.insert(0, str(HERE))
        import v3_site  # noqa: E402
    except Exception as e:  # noqa: BLE001
        say("注意：截不了字体（%s），演示页用系统字体" % e)
        return ""
    fdir = Path(os.path.expanduser(v3_site.FONT_CACHE))
    (out / "fonts").mkdir(exist_ok=True)
    for f in (out / "fonts").glob("*.woff2"):
        f.unlink()
    faces = []

    def make(key, text, fname, family, weight, style="normal", local=()):
        src = fdir / v3_site.FONT_FILES[key]
        if not src.exists():
            say("注意：缺原字体 %s" % src)
            return
        opts = ftsubset.Options()
        opts.flavor = "woff2"
        opts.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]
        opts.name_languages = [0x409]
        opts.hinting = False
        opts.desubroutinize = True
        opts.notdef_outline = True
        opts.drop_tables += ["Debg"]
        font = ftsubset.load_font(str(src), opts)
        sub = ftsubset.Subsetter(opts)
        sub.populate(text=text)
        sub.subset(font)
        ftsubset.save_font(font, str(out / "fonts" / fname), opts)
        loc = "".join('local("%s"), ' % n for n in local)
        faces.append('@font-face{font-family:"%s";font-style:%s;font-weight:%s;font-display:swap;src:%surl("fonts/%s") format("woff2")}'
                     % (family, style, weight, loc, fname))

    ascii_ = "".join(chr(c) for c in range(0x20, 0x7f))
    make("title_700", "".join(sorted(set(title_text + ascii_ + "“”‘’—–…·×→−"))), "title-700.woff2", "FD Title", 700)
    make("kai_400", "".join(sorted(set(body_text + "“”‘’—…·（）《》「」：；，。！？、→−"))), "body-kai.woff2", "FD Kai", 400)
    make("display_400", ascii_ + "−–—’·×→", "display.woff2", "FD Display", 400)
    lat = "".join(sorted(set(latin_text + ascii_ + "‘’“”–—…·×−→")))
    make("latin_400", lat, "latin.woff2", "FD Latin", 400, local=("Times New Roman", "TimesNewRomanPSMT"))
    make("latin_700", lat, "latin-bold.woff2", "FD Latin", 700, local=("Times New Roman Bold", "TimesNewRomanPS-BoldMT"))
    for lic in ("OFL_LXGWWenKaiScreen.txt", "LICENSE_NotoSerifCJK.txt", "OFL_InstrumentSerif.txt"):
        if (fdir / lic).exists():
            shutil.copy2(fdir / lic, out / "fonts" / lic)
    return "\n".join(faces)


# ---------------------------------------------------------------- 8. 组装
def build(issue, mp3, marks, dur, al, T, titles, narr, sb, cards, facts, pl=None, meas=None):
    clusters = SB.clusters(sb)
    out = issue / OUT_DIR
    out.mkdir(exist_ok=True)

    # 来源：卡内编号（s1…）→ 网页 v3 的编号（s01…），网页里没有的按网址另编
    web = issue_sources(issue)
    sources, order = {}, []

    def gsrc(ev, local):
        card = cards[ev]
        s = next((x for x in card["sources"] if x["id"] == local), None)
        if not s:
            return None
        hit = web.get(norm_url(s["url"]))
        sid = hit["id"] if hit else "v%02d" % (len([k for k in sources if k.startswith("v")]) + 1)
        if sid not in sources:
            sources[sid] = {"id": sid, "name": (hit or s)["name"], "title": (hit or {}).get("title", ""),
                            "url": s["url"], "date": (s.get("date") or "")[:10]}
            order.append(sid)
        return sid

    for c in clusters:
        c_src = []
        for n in c["note"]:
            n["src"] = list(dict.fromkeys(filter(None, (gsrc(facts[r]["ev"], facts[r]["src"]) for r in n["ref"]))))
            c_src += n["src"]
        for ev in c["stories"]:                       # 该片相关事件的其余来源也列上
            for s in cards[ev]["sources"]:
                c_src.append(gsrc(ev, s["id"]))
        c["src"] = list(dict.fromkeys(filter(None, c_src)))
    for i, sid in enumerate(order):
        sources[sid]["n"] = i + 1

    photos = prep_photos(issue, out, sb)
    (out / "audio").mkdir(exist_ok=True)
    shutil.copy2(mp3, out / "audio" / "video3.mp3")
    qc = json.loads((issue / VOICE_DIR / "qc.json").read_text(encoding="utf-8")) if (issue / VOICE_DIR / "qc.json").exists() else {}
    usage = json.loads((issue / VOICE_DIR / "usage.json").read_text(encoding="utf-8")) if (issue / VOICE_DIR / "usage.json").exists() else {}
    conf = qc.get("配置", {})
    vinfo = json.loads((issue / VOICE_DIR / "voice.json").read_text(encoding="utf-8")) if (issue / VOICE_DIR / "voice.json").exists() else {}
    music = None
    if pl and pl.get("music") is not False:
        music = MUS.describe(pl)
        music["mix"] = meas or {}
        T["mus.in"] = pl["intro_down"]          # 片头乐句第一个强拍（片头字跟着它上推）
    chapters = SB.compile_chapters(sb, T, marks, photos)
    chapters[-1]["end"] = round(dur, 3)
    # 11-08（K42）：封面图。分镜 title.cover 写图名或 image_requests 的 id；不写就用开场速览第一屏的图。
    # 和 11-08 的其他渲染修复一样，新动效开关和视频导演开关都开着才起作用（数据里写 fix1108）；任一个关着，数据和 11-08 以前逐字节一样
    fix = SB.render_fix_on()
    cover = None
    cname = (sb.get("title") or {}).get("cover") if fix else None
    if fix and not cname:
        for c0 in sb["chapters"]:
            if c0.get("kind") != "open":
                continue
            for b0 in c0.get("blocks") or []:
                if b0.get("type") == "headline_open":
                    cname = next((it.get("image") for it in b0.get("items") or [] if isinstance(it, dict) and it.get("image")), None)
                    break
    if cname:
        cover = SB.ensure_photo(sb, photos, "title.cover", cname, 1600)
        if not cover:
            say("注意：封面图 %s 找不到，封面不带图" % cname)
    S = SB.strings(sb)
    txt = SB.txt
    # 标志：当期用到的嵌进数据（播放时不向外网要东西）；英文名按英文名表
    lkeys = SB.used_logos(sb)
    logos = LG.embed(lkeys)
    reg = en_registry()
    lib = LG.load()
    for k, v in logos.items():              # 标志小签显示的英文名：按英文名表（库里的别名可以留着，显示用规范写法）
        names = LG.names_of(lib["logos"].get(k) or {})
        hit = next((e["en"] for e in reg if any(z in names or z == v["n"]["zh"] for z in e["zh"])
                    or any(n.lower() == e["en"].lower() for n in names)), None)
        if hit:
            v["n"]["en"] = hit
    # 出处与署名（画面里不挂小标；这里的几行显示在文字稿面板末尾，网页的“参考来源”也读它）
    # 动效尝试（11-06 晚）：原文截图不算"视频配图"（不是 AI 画的），单独写一行出处；没有截图时和原来一模一样
    shots = [ph for ph in photos.values() if ph.get("kind") == "screenshot"]
    lines, used_img = [], sorted({ph["file"] for ph in photos.values() if ph.get("kind") != "screenshot"})
    if music and music.get("credit"):
        lines.append(music["credit"])
    il = IMG.credit_lines(used_img, sb.get("_img_meta") or {})
    if il:
        lines.append(il)
    if shots:
        nz = list(dict.fromkeys((ph.get("source") or {}).get("zh") or "" for ph in shots))
        ne = list(dict.fromkeys((ph.get("source") or {}).get("en") or "" for ph in shots))
        day = sorted({str(ph.get("shot_at") or "")[:10] for ph in shots if ph.get("shot_at")})
        lines.append({"zh": "画面中的原文截图取自 %s 的网页（截于 %s），只用来标明出处，版权归原网站。" % ("、".join(filter(None, nz)), "、".join(day) or "制作当天"),
                      "en": "Screenshots of source pages from %s (captured %s) are shown only to cite the source; rights belong to the sites."
                            % (", ".join(filter(None, ne)), ", ".join(day) or "on the day")})
    lcred = LG.credits([k for k in lkeys if (logos.get(k) or {}).get("m")], lib)
    if lcred:
        srcs = sorted({("Simple Icons（CC0）" if "Simple Icons" in (c["source"] or "") else "Wikimedia Commons（公有领域字标）") for c in lcred})
        srcs_en = sorted({("Simple Icons (CC0)" if "Simple Icons" in (c["source"] or "") else "Wikimedia Commons (public-domain text logos)") for c in lcred})
        lines.append({"zh": "画面中的公司标志取自 %s，只做单色处理；商标归各自所有者，仅用于指称。" % "、".join(srcs),
                      "en": "Company logos from %s, shown in a single colour; trademarks belong to their owners and are used only to identify them." % " and ".join(srcs_en)})
    credits = {"lines": lines,
               "images": [dict({"file": f}, **((sb.get("_img_meta") or {}).get(f) or {"kind": "generated"})) for f in used_img],
               "logos": lcred, "music": (music or {}).get("credit")}
    if shots:
        credits["shots"] = [{k: ph.get(k) for k in ("file", "url", "shot_at", "source")} for ph in shots]

    data = {
        "v": 3, "schema": SB.SCHEMA, "date": issue.name, "accent": sb.get("accent") or "amber", "duration": round(dur, 3), "audio": "audio/video3.mp3",
        "voice": {"engine": conf.get("engine"), "model": conf.get("model"), "name": vinfo.get("叫法"),
                  "cost_usd": (usage.get("合计") or {}).get("估计费用美元", 0.0)},
        "music": music,
        "sync": al["accuracy"],
        "chapters": chapters,
        "cues": [{k: c[k] for k in ("start", "end", "text", "t")} for c in al["cues"]],
        "transcript": [{"ch": s["scene"], "text": s["text"], "start": s["start"], "end": s["end"]} for s in al["sentences"]],
        "T": T,
        "S": {k: txt(v) for k, v in S.items()},
        "clusters": [{"id": c["id"], "ch": c["ch"], "name": c["name"], "key": txt(c["key"]), "sub": c["sub"],
                      "stories": c["stories"], "src": c["src"],
                      "note": [{"zh": n["zh"], "en": n["en"], "src": n["src"]} for n in c["note"]]} for c in clusters],
        "sources": sources,
        "images": photos,
        "logos": logos,
        "credits": credits,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    if fix:      # 11-08 渲染修复的开关（video3.js 读 fix1108）；封面图写在 cover。开关关着时这两个键都不写
        data["fix1108"] = True
        if cover:
            data["cover"] = cover
    # 所有英文显示字（章、模板、热点卡、片头片尾、标志名、署名）最后按英文名表过一遍：大小写和明确不用的写法直接改，中文名对不上的提醒
    nwarn = []
    for k in ("chapters", "clusters", "S", "logos", "credits"):
        en_names_apply(data.get(k), reg, k, nwarn)
    for w in dict.fromkeys(nwarn):
        say("  提醒：" + w)
    # 11-09：中文整词换行（开关"视频中文整词换行"，说明见 video3_zhwrap.py）。所有字定稿以后才算；只多写 zhwrap 一个键
    # （原文 → 带换行点的显示文字），播放器按它给卡片、标题、字幕插换行点。上面的字（触发词、字幕和逐字时间、文字稿）一个字不动。
    # 开关关着不写这个键，数据和加开关以前逐字节一样
    zon, zwhy = ZWRAP.switch()
    if zon:
        tbl, msg = ZWRAP.table(data, ZWRAP.terms(cards))
        if tbl:
            data[ZWRAP.KEY] = tbl
        say(("  " if tbl else "  提醒：") + msg)
    else:
        say("  中文整词换行：开关关着（%s），不加" % zwhy)
    js = "/* 视频 v3 场景数据 · %s · 由 site/tools/video3_build.py 生成，请勿手改 */\nwindow.FD_VIDEO3 = %s;\n" % (
        issue.name, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    (out / "data.js").write_text(js, encoding="utf-8")
    (out / "video3_media.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # 本地双击打开时，浏览器不许 WebGL 读本地图片文件：把图转成 data: 地址另放一个文件（网站上用普通网址）
    import base64
    assets = {}
    for ph in photos.values():
        for k in ("src", "depth"):
            if ph.get(k):
                assets[ph[k]] = "data:image/webp;base64," + base64.b64encode((out / ph[k]).read_bytes()).decode()
    (out / "assets.js").write_text("/* 双击打开（file://）用：配图的 data: 地址 */\nwindow.FD_VIDEO3_ASSETS = %s;\n"
                                   % json.dumps(assets), encoding="utf-8")

    # 播放器与库
    (out / "vendor").mkdir(exist_ok=True)
    for f, dst in ((SITE / "v3/video3.js", out / "video3.js"), (SITE / "v3/video3.css", out / "video3.css"),
                   (SITE / "vendor/gsap.min.js", out / "vendor/gsap.min.js"),
                   (SITE / "vendor/three/three-bundle.min.js", out / "vendor/three-bundle.min.js"),
                   (SITE / "vendor/echarts.min.js", out / "vendor/echarts.min.js")):
        if f.exists():
            shutil.copy2(f, dst)
    for lic in ("LICENSE-three.txt", "LICENSE-postprocessing.txt", "README.txt"):
        shutil.copy2(SITE / "vendor/three" / lic, out / "vendor" / lic)

    # 字体
    ui = ""
    vjs = SITE / "v3/video3.js"
    if vjs.exists():
        m = re.search(r"/\* I18N-ZH-START \*/(.*?)/\* I18N-ZH-END \*/", vjs.read_text(encoding="utf-8"), re.S)
        ui = m.group(1) if m else ""
    all_txt = json.dumps(data, ensure_ascii=False) + ui + PAGE_TEXT
    title_txt = "".join(v.get("zh", "") + v.get("en", "") for v in S.values()) + "".join(
        c["name"].get("zh", "") + c["key"].get("zh", "") for c in clusters) + "".join(c["label"].get("zh", "") for c in chapters) + PAGE_TEXT
    title_txt += json.dumps([c.get("blocks") for c in chapters], ensure_ascii=False)     # 模板里的标题、大字
    if data.get(ZWRAP.KEY):     # 11-09：整词换行开着时，标题字体也带上换行点、连接符和不换行空格（关着时不加，字体包和以前一样）
        title_txt += ZWRAP.ZW + ZWRAP.WJ + ZWRAP.NBSP
    faces = subset_fonts(out, title_txt, all_txt, all_txt)
    write_page(out, data, faces, sb)
    report(issue, out, data, dur, marks)


PAGE_TEXT = "视频 v3 演示 今日地图 一镜到底 每日AI科技前沿简报 参考来源 说明 双击打开 旁白为 AI 合成语音 配乐 自由看图"


def page_lede(sb):
    """演示页开头那句：按这一期的分镜写（几片、叫什么、有没有国内外）。"""
    names = [SB.txt((c.get("chip") or {}).get("name") or c.get("label")).get("zh", "") for c in sb["chapters"] if c["kind"] == "story"]
    con = any(c["kind"] == "contrast" for c in sb["chapters"])
    return ("一镜到底：镜头在一张三维的“今日地图”上飞行，依次经过%s%s片%s。播完停在全图，可以点任意一片看细节和出处。"
            % ("、".join(names), "一二三四"[len(names) - 1] if 1 <= len(names) <= 4 else "", "，最后把地图从中间分开看国内外" if con else ""))


def write_page(out, data, faces, sb=None):
    src_items = "".join(
        '<li id="src-%s"><span class="n">[%d]</span><span class="nm">%s</span> <a href="%s" target="_blank" rel="noopener noreferrer">%s</a> <span class="d">%s</span></li>'
        % (s["id"], s["n"], esc(s["name"]), esc(s["url"]), esc(s["title"] or s["url"]), esc(s["date"]))
        for s in sorted(data["sources"].values(), key=lambda x: x["n"]))
    voice, music = data["voice"], data.get("music")
    vnote = "旁白为 AI 合成语音（%s）。" % "，".join(x for x in (voice.get("name"), voice.get("model")) if x)
    for ln in (data.get("credits") or {}).get("lines") or ([music["credit"]] if music else []):
        vnote += " " + ln["zh"]
    html = PAGE.replace("{{FACES}}", faces).replace("{{SOURCES}}", src_items).replace("{{DATE}}", data["date"]) \
        .replace("{{DUR}}", "%d" % round(data["duration"])).replace("{{VNOTE}}", esc(vnote)).replace("{{LEDE}}", esc(page_lede(sb)) if sb else "")
    acc, vars_ = accent_vars(data.get("accent") or "amber")      # 演示页跟当期主题色走
    html = html.replace("{{ACCENT}}", acc).replace("{{ACC_L}}", _acc_css(vars_["light"])).replace("{{ACC_D}}", _acc_css(vars_["dark"]))
    (out / "index.html").write_text(html, encoding="utf-8")


ACCENT_CSS = SITE / "v3" / "style.css"     # 网页 v3 的主题色（blue／amber／coral／violet），演示页照它取色，不另写一份
ACCENT_FALLBACK = {"light": {"accent": "#9a5800", "accent-hi": "#b86400", "accent-rgb": "232 140 20", "on-accent": "#fff"},
                   "dark": {"accent": "#ffb340", "accent-hi": "#ffbf5f", "accent-rgb": "255 179 64", "on-accent": "#1f1300"}}


def accent_vars(name):
    """当期主题色 → 演示页用的四个变量（浅色、深色各一组）：从 site/v3/style.css 的 :root[data-accent="…"] 和
    :root[data-theme="dark"][data-accent="…"] 两行读（2026-11-01 晚改：原来写死琥珀色）。读不到就用琥珀色，并提醒。"""
    out = {}
    try:
        css = ACCENT_CSS.read_text(encoding="utf-8")
    except OSError:
        css = ""
    for mode, sel in (("light", r':root\[data-accent="%s"\]' % re.escape(name)),
                      ("dark", r':root\[data-theme="dark"\]\[data-accent="%s"\]' % re.escape(name))):
        m = re.search(sel + r"\s*\{([^}]*)\}", css)
        got = dict(re.findall(r"--(accent|accent-hi|accent-rgb|on-accent)\s*:\s*([^;]+?)\s*;", m.group(1))) if m else {}
        if len(got) < 4:
            say("  提醒：主题色 %s 在 %s 里没找到，演示页用琥珀色" % (name, ACCENT_CSS.relative_to(ROOT)))
            return "amber", ACCENT_FALLBACK
        out[mode] = got
    return name, out


def _acc_css(v):
    return "--accent:%s;--accent-hi:%s;--accent-rgb:%s;--on-accent:%s" % (v["accent"], v["accent-hi"], v["accent-rgb"], v["on-accent"])


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


PAGE = """<!doctype html>
<html lang="zh-CN" data-accent="{{ACCENT}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex">
<meta name="color-scheme" content="light dark">
<title>今日地图 · 视频 v3 演示</title>
<style>
{{FACES}}
:root{--bg:#f5f5f7;--ink:#1d1d1f;--ink-2:#3a3a3c;--ink-3:#636366;--hair:rgba(0,0,0,.08);{{ACC_L}};
  --font-ui:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --font-title:"FD Title","Noto Serif SC","Songti SC",serif;--font-body:"FD Latin","FD Kai","Kaiti SC","STKaiti",serif;--font-display:"FD Display","FD Latin","Times New Roman",serif}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#0a0a0c;--ink:#f5f5f7;--ink-2:#d1d1d6;--ink-3:#a1a1a6;--hair:rgba(255,255,255,.1);{{ACC_D}}}}
:root[data-theme="dark"]{--bg:#0a0a0c;--ink:#f5f5f7;--ink-2:#d1d1d6;--ink-3:#a1a1a6;--hair:rgba(255,255,255,.1);{{ACC_D}}}
*{box-sizing:border-box}html{background:var(--bg);color:var(--ink)}body{margin:0;font:400 17px/1.6 var(--font-ui);-webkit-font-smoothing:antialiased;background:var(--bg)}
.wrap{width:min(1160px,100% - 32px);margin:0 auto;padding:28px 0 64px}
h1{font:700 30px/1.25 var(--font-title);margin:0 0 6px}h1 small{font:400 15px/1 var(--font-ui);color:var(--ink-3);margin-left:10px}
.lede{color:var(--ink-2);font:400 17px/1.7 var(--font-body);margin:0 0 20px;max-width:46em}
.meta{font-size:14px;color:var(--ink-3);margin:14px 0 0}
.srcs{margin-top:34px}.srcs h2{font:700 20px/1.3 var(--font-title);margin:0 0 10px}
.srcs ol{list-style:none;padding:0;margin:0;display:grid;gap:8px}.srcs li{font-size:14px;line-height:1.5;color:var(--ink-2);padding:8px 12px;border-radius:12px;scroll-margin:80px}
.srcs li:target,.srcs li.flash{background:rgb(var(--accent-rgb)/.14)}.srcs .n{font-family:"FD Latin","Times New Roman",serif;color:var(--accent);margin-right:8px}
.srcs a{color:var(--accent);word-break:break-all}.srcs .d{color:var(--ink-3)}
/* ?rec=1：录预览视频用，舞台铺满窗口，隐藏页面其他部分 */
html.rec,html.rec body{margin:0;overflow:hidden;background:#f3efe8}html.rec .wrap{width:100vw;padding:0;margin:0}
html.rec h1,html.rec .lede,html.rec .meta,html.rec .srcs,html.rec .v3ctl,html.rec .v3pgr{display:none}
html.rec .v3stage{width:100vw;height:100vh;aspect-ratio:auto;border-radius:0;box-shadow:none}
</style>
<link rel="stylesheet" href="video3.css">
</head>
<body>
<main class="wrap">
  <h1>今日地图<small>视频 v3 演示 · {{DATE}} · 约 {{DUR}} 秒</small></h1>
  <p class="lede">{{LEDE}}</p>
  <div id="v3root" class="v3root"></div>
  <p class="meta">{{VNOTE}} 拖动画面可以转一转视角（暂停时）；键盘：空格播放、← → 快退快进、Shift+← → 换章、C 字幕。</p>
  <section class="srcs" aria-labelledby="srch"><h2 id="srch">参考来源</h2><ol>{{SOURCES}}</ol></section>
</main>
<script src="vendor/gsap.min.js"></script>
<script src="vendor/three-bundle.min.js"></script>
<script src="vendor/echarts.min.js"></script>
<script src="data.js"></script>
<script src="assets.js"></script>
<script src="video3.js"></script>
<script>
(function () {
  var q; try { q = new URLSearchParams(location.search); } catch (e) { q = { get: function () { return null; } }; }
  var th = q.get('theme'); if (th === 'light' || th === 'dark') document.documentElement.setAttribute('data-theme', th);
  if (q.get('rec') === '1') document.documentElement.classList.add('rec');
  var store = { get: function (k, d) { try { var v = localStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } },
                set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 隐私模式 */ } } };
  var ctx = {
    lang: function () { return q.get('lang') === 'en' ? 'en' : 'zh'; },
    asset: function (p) { return (window.FD_VIDEO3_ASSETS && window.FD_VIDEO3_ASSETS[p]) || p; },
    store: store,
    jumpSource: function (sid) {
      var li = document.getElementById('src-' + sid); if (!li) return;
      li.scrollIntoView({ behavior: 'smooth', block: 'center' });
      li.classList.remove('flash'); void li.offsetWidth; li.classList.add('flash');
    },
    eager: q.get('eager') === '1', static: q.get('static') === '1'
  };
  window.__v3 = window.FDVideo3 && window.FDVideo3.mount(document.getElementById('v3root'), window.FD_VIDEO3, ctx);
})();
</script>
</body>
</html>
"""


def report(issue, out, data, dur, marks):
    def kb(p):
        return round(p.stat().st_size / 1024)
    say("写出 %s：" % out.relative_to(issue))
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.suffix in (".html", ".js", ".css", ".mp3", ".webp", ".woff2", ".json"):
            say("  %-36s %6d KB" % (p.relative_to(out), kb(p)))
    say("视频 %.1f 秒，%d 章；人声 %.1f 秒；对齐中位误差 %s 秒" % (dur, len(marks), sum(m["voice_end"] - m["voice_start"] for m in marks),
                                                 data["sync"].get("median_abs_err")))


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="视频 v3 组装（用法见文件开头）")
    ap.add_argument("issue", nargs="?", help="一期的目录，如 测试版/2026-10-31")
    ap.add_argument("--day", help="日期，如 2026-11-01（等于给 测试版/<日期>）")
    ap.add_argument("--revoice", action="store_true", help="重新配音（换声音、改旁白后用）")
    ap.add_argument("--engine", choices=["mimo", "gemini"], default="gemini",
                    help="gemini（默认）：声音档案的主声音；mimo：声音档案的备用声音")
    ap.add_argument("--voice", help="临时换声音：gemini 给声音 ID；mimo 给内置音色名（不给就用声音档案）")
    ap.add_argument("--clone-ref", help="MiMo 声音复刻的参考音频（默认用声音档案里备用声音的参考音）")
    ap.add_argument("--no-music", action="store_true", help="不配乐，只出人声（章间用固定空隙）")
    ap.add_argument("--music-style", choices=MUS.STYLES, default=MUS.STYLE,
                    help="配乐做法：avoid（默认，11-02 起）＝和播客默认声音包一样的底乐＋避让；b2＝11-02 以前的混法（原样复现用）")
    ap.add_argument("--budget-usd", type=float, default=0.05, help="这次配音最多花多少美元（Gemini 才花钱）")
    ap.add_argument("--fresh", action="store_true", help="配音不用缓存")
    ap.add_argument("--voice-mode", choices=["whole", "chapters"], default=VOICE_MODE,
                    help="chapters：每章单独请求（默认）；whole：整篇旁白一次请求再按逐词时间切章")
    ap.add_argument("--no-pitch-gate", action="store_true", help="不做音高把关（默认按声音档案的参考音高把关）")
    ap.add_argument("--no-timbre-gate", action="store_true",
                    help="不做音色把关（默认按 pipeline/assets/voices/音色指纹/ 的档案把关，见 pipeline/voice_print.py）")
    ap.add_argument("--no-gen", action="store_true", help="缺的配图不生成（那些位置不带图）")
    ap.add_argument("--no-palette", action="store_true",
                    help="不用情绪色板：各章同一句基础语气，开场 warm、收尾 warm, a touch slower（11-01 的做法）")
    ap.add_argument("--no-sentence-level", action="store_true", help="不做句子级找平音量")
    ap.add_argument("--tempo-adjust", action="store_true",
                    help="做语速微调（默认不做：视频旁白比播客参考语速慢 6–12%%，照播客参考调会整条加快，见 voice() 里的注释）")
    ap.add_argument("--allow-reserved-gcp", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--stage", choices=["voice", "align", "all"], default="all", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if not (a.issue or a.day):
        ap.error("给一期的目录，或 --day 日期")
    MUS.STYLE = a.music_style                # 排拍子、估时长、混音、写配乐说明都按这一种做法
    raw = a.issue or ("测试版/" + a.day)
    issue = (ROOT / raw).resolve() if not os.path.isabs(raw) else Path(raw)
    sb, cards, facts = prepare(issue, gen=not a.no_gen)
    lint_narration(issue)
    rules = load_rules()
    check_length(sb, rules)                  # 配音前按字数估：超过 3 分钟就停
    vj = issue / VOICE_DIR / "voice.json"
    vinfo = json.loads(vj.read_text(encoding="utf-8")) if vj.exists() else {}
    old = vinfo.get("spoken_sha")
    nch = len(list((issue / VOICE_DIR / "chapters").glob("*.wav"))) if (issue / VOICE_DIR / "chapters").exists() else 0
    stale = nch != len(sb["chapters"]) or (old is not None and old != spoken_sha(issue))
    if stale and not a.revoice:
        say("旁白和现有配音对不上（改过分镜的 narration，或还没配过）：自动重配；没改的章直接用配音缓存，不花钱")
    if vinfo and not (a.revoice or stale):     # 配音规则改过（语气、合成方式），现有配音还是旧设置：只提醒，不自动重配（冻结的期不动）
        vp = voice_plan(issue, a, sb)
        if (vinfo.get("mode") or "chapters") != vp["mode"] or vinfo.get("styles") != vp["style_map"] or \
                (vp["mode"] == "whole" and vinfo.get("style") != vp["cfg"].style):
            say("  提醒：现有配音是旧设置（语气或合成方式和现在的规则不同）；要按现在的规则重配，加 --revoice")
    if a.revoice or stale:
        voice(issue, a, sb)
    if a.stage == "voice":
        return 0
    mp3, vmp3, marks, dur, pl, meas = assemble(issue, sb, music=not a.no_music)
    check_length(sb, rules, actual=dur)      # 配完音按实际时长再查一遍
    al, T, titles, narr = align(issue, vmp3, marks, dur, sb)
    say("对齐：", json.dumps(al["accuracy"], ensure_ascii=False))
    for w in SB.check_gaps(sb, T, marks):
        say("  提醒：" + w)
    for m in marks:
        say("  %-9s %6.2f – %6.2f" % (m["chapter"], m["voice_start"], m["voice_end"]))
    if a.stage == "align":
        for k in sorted(T, key=T.get):
            if not k.endswith(".end"):
                say("  %6.2f  %s" % (T[k], k))
        return 0
    build(issue, mp3, marks, dur, al, T, titles, narr, sb, cards, facts, pl, meas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
