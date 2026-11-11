#!/usr/bin/env python3
"""视频 v3 分镜（每期一份 JSON）：读入、校验、核对事实，编成播放器要的数据。由 site/tools/video3_build.py 调用。

一期的分镜放在 测试版/<日期>/04_文稿/视频v3_分镜.json，由写稿模型按 pipeline/prompts/写稿_视频v3.md 写。结构：
    {"schema": "video3-storyboard/1", "date": "2026-10-31", "accent": "amber",
     "title": {"date": "10.31", "main": {zh,en}, "line": {zh,en}},
     "facts": {"e001.round": {"event": "E001", "field": "facts", "index": 0, "check": "事件卡原文里必须有的一段"}, …},
     "chapters": [
        {"id": "open", "kind": "open", "title": "开场", "label": {zh,en}, "narration": "…", "cues": {"map": "10 月 31 日"}},
        {"id": "money", "kind": "story", "title": "钱", "label": {zh,en}, "storyline": "钱在收紧", "map_cue": "钱在收紧",
         "chip": {"name": {zh,en}, "key": {zh,en,ref}, "sub": {zh,en}}, "note": [{zh,en,ref}], "stories": ["E001"],
         "narration": "…", "blocks": [{"type": "bar_shrink", "id": "raise", …, "cues": {…}}, …]},
        …（story 1–4 章；contrast 0–1 章；最后一章 close）
        {"id": "close", "kind": "close", "title": "收尾", "label": {zh,en}, "narration": "…",
         "end": {"title": {zh,en}, "lines": [{zh,en,cue}]}, "cues": {"map": "合起来看"}}]}

字（label）一律写成 {"zh": "…", "en": "…", "ref": ["facts 里的键", …]}：带数字的必须有 ref，数字要在 ref 指向的事件卡原文里出现。
触发词（cue）写旁白原文里的一小段（阿拉伯数字照写），或 {"say": "…", "offset": -0.3}；"@start"/"@end" 是这一章的开头/末尾。
每种模板要哪些字段、哪些触发词，见下面 TEMPLATES；模板目录（给写稿模型看的说明）在 写稿_视频v3.md。

真东西（v3.3）：
  · 标志小签："logos": ["samsung", {"key": "micron", "cue": "美光"}]，挂在模板支持的位置（LOGO_SLOTS）；键是标志库
    site/assets/logos/来源.json 里的键（site/tools/video3_logos.py 维护）。公司名要出现在它挂的卡上或引用的事件卡原文里，否则不挂。
  · 配图："image": "v_store"（本期 image_requests 里的 id，或 06_配图 里的文件名），可以给 image_card、tile_row 的每块小卡、post_card。
    "image_requests": [{"id": "v_store", "brief_en": "…", "placement": "tile", "events": ["E034"]}, …]：缺图时构建脚本调 Codex 生成到
    06_配图/视频/（或 "commons": "File:…" 从 Wikimedia Commons 取一张 CC0/公有领域/CC BY/CC BY-SA 的资料图）。
  · post_card：帖子／节目卡（平台小标＋日期＋原话＋署名，头像只用首字母或机构标志）；平台、日期、原话都要核得上事件卡，核不上平台就只标"原话"。

关系（v3.4，11-02 晚补）：每个 story 章写 "relation"（画什么关系），模板要能画出它；check_relations 查一排小卡撑场、
  没有关系模板的章、国内外章没用 split、同排小卡有的有图有的没图——总调度第 7 步（helpers.py storyboard）算"要改"。
数值字段（11-03 补）：check_values 查播放器当数字读的字段（NUM_FIELDS：bar_shrink 的 from/to/done.value 等）是不是 JSON 数字、
  当字显示的（TEXT_FIELDS）有没有写成裸数字——同样在第 7 步算"要改"。value 只写数字，带单位的字写在 label。

版式修理（11-06）：画面检查改准并前移到第 7 步（screen_model / check_screen：只剩线和点的时间轨、空玻璃柱、白卡上的字不算画面，
  关系模板只算触发词后几秒，认得穿插；章首 3 秒要有主角；时间轨被打断；旁白数字、等级上没上画面；一期配图张数——都只提醒，
  第 7 步按字数估时间）；新图位 quote_card.image、timeline.ticks[].image / .logos；新模板 tally（美国轮廓＋计数，点亮的州要能在
  事件卡原文里逐字找到、而且和计数出自同一条，核不上和数字一样停）。

动效（11-06 晚加；11-07 并入正式流程：写稿提示词《写稿_视频v3.md》"看得见出处"一节，fd 第 14 步自动截图；尝试版 video3_trial.py 照旧能用）：
  source_shot（原文截图＋荧光笔，截图由 source_shots.mjs 截到 06_配图/原文截图/）、source_excerpt（截图没成功时自动退回：
  事件卡原句排成报纸摘录）、num_chain（数字递进 A → B → C）、headline_open（开场"今日速览"，放在 open 章的 blocks 里）、
  quote_card / num_chain 的 "count": true（数字从 0 滚到终值）。原句必须逐字在事件卡 quote 里、中文译文只取同一条 fact 的
  text_zh、出处签的媒体名要在事件卡来源名或网址里，核不上和数字一样停（check_sources）。不写这些字段的分镜，行为和原来一样。
  总开关（11-07）：motion_switch / strip_motion，关着时组装前去掉这些块和字段（见下面"新动效的总开关"）；
  check_motion：几条只提醒的规矩（一章最多一处截图、数字递进和数字滚动的上限、速览每屏不同的图、时间轴日子挂图、只有名字的小卡、
  白底对比卡、章里没有自己的图），第 7 步挂在 check_relations 后面。

校验规则：核不上事实、触发词在旁白里找不到、章的结构不对 → 停（SystemExit），不配音。
数据不够画一个模板（比如时间轴只有一个日子、配图文件不存在）→ 去掉这个模板并提醒；一章的模板全去掉了 → 换成一张"要点卡"。
"""
import json
import os
import re
from pathlib import Path

SCHEMA = "video3-storyboard/1"
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)*")

# 模板：每种要的字段（required）、可选字段、触发词名（cues）、列表里的触发词（list_cues：列表字段 → 每项的 cue 字段）、
# 最少要几项（min：列表字段 → 个数）、放在哪种章（kinds）。JS 一侧的实现在 site/v3/video3.js 的 TPL。
TEMPLATES = {
    "bar_shrink": {"required": ["head", "from", "to"], "cues": ["head", "from", "to", "done", "half"], "kinds": ["story"],
                   "about": "一根柱子从原值缩到新值（断开、碎掉），可选：已完成量的芯、原值一半的虚线、状态小字"},
    "twin_drop": {"required": ["items"], "cues": ["head", "same", "note"], "list_cues": {"items": "cue"}, "min": {"items": 1},
                  "kinds": ["story"], "about": "1–3 个价位块从同一高度按跌幅掉下来（股价单日跌幅、降价幅度）"},
    "timeline": {"required": ["ticks"], "cues": ["start"], "list_cues": {"ticks": "at"}, "min": {"ticks": 2}, "kinds": ["story"],
                 "about": "一条时间轨，2–7 个日子依次立起（镜头装下整条轨），hot 的是重点日子（更大、发亮）；pos 只排先后；可选一道拱线标“等了多久”；"
                          "每个日子可挂 logos（公司标志）和一张小图 image（11-06 补，一条轨最多 3 张）"},
    "image_card": {"required": ["image"], "cues": ["in"], "kinds": ["story"],
                   "about": "本期配图做成 2.5D 视差的“窗”，放在这一章的背景里（不能单独成章）"},
    "phone_list": {"required": ["rows"], "cues": ["rise", "show", "foot"], "list_cues": {"rows": "cue"}, "min": {"rows": 1}, "kinds": ["story"],
                   "about": "一部玻璃手机，屏幕上 1–5 行功能，每行挂一个小标（谁接进来了），底部一行说明"},
    "chain": {"required": ["stations"], "cues": ["draw", "start", "mark", "window"], "list_cues": {"hops": None},
              "min": {"stations": 2}, "kinds": ["story"],
              "about": "等轴测的传播链（2–5 站：source/store/loop/devices/box），一件包裹按旁白一站站走，可被标红"},
    "particle_counter": {"required": ["value"], "cues": ["count"], "kinds": ["story"],
                         "about": "几千个点聚成一个数字（人数、台数），放在 chain 后面时从最后一站升起"},
    "fork": {"required": ["a", "b"], "cues": ["fork", "a", "b"], "kinds": ["story"],
             "about": "一条路分成两条（两种路线、两种打法）；后面紧跟的两个卡片模板分别站在两条路的尽头"},
    "compare_panel": {"required": ["head"], "cues": ["show"], "list_cues": {"bars": "cue"}, "kinds": ["story"], "panel": True,
                      "about": "玻璃卡片：标题、一个大数字、1–4 根对比条（条长只是示意，数字写在字里）"},
    "quota_bars": {"required": ["head", "stages"], "cues": ["show", "from", "to"], "min": {"stages": 2}, "kinds": ["story"], "panel": True,
                   "about": "玻璃卡片：从 A 到 B 的两个大字，加 2–6 根逐根长出的柱子（价格、额度、阶段）"},
    "quote_card": {"required": ["text"], "cues": ["show"], "kinds": ["story", "contrast"], "panel": True,
                   "about": "玻璃卡片上的一句原话或要点：出处和标志合成卡片顶上一行，短句自动放大、卡片压矮；可带一张题图 image（左图右字）"
                            "（原话必须出自事件卡 who_said / quote）"},
    "post_card": {"required": ["text", "who"], "cues": ["show"], "kinds": ["story", "contrast"], "panel": True,
                  "about": "帖子／节目卡：平台小标（播客、X、Threads、YouTube、官方声明、文件）、日期、原话、署名（头像只用首字母或机构标志），可带一张题图"},
    "scale": {"required": ["bands", "to"], "cues": ["head", "from", "to", "note"], "min": {"bands": 2}, "kinds": ["story", "contrast"],
              "about": "一根刻度尺分 2–6 档（信用评级、等级），一条门槛线，一个标记从原来的档落到（或升到）新的档；"
                       "open_top: true 时上沿不封口（材料没说最上面那档就是顶格，11-06 白天补）"},
    "column_compare": {"required": ["items"], "cues": ["head", "note"], "list_cues": {"items": "cue"}, "min": {"items": 2},
                       "kinds": ["story", "contrast"], "about": "2–4 根玻璃柱按数值长高（谁比谁多），重点那根带发光的芯"},
    "tile_row": {"required": ["items"], "cues": ["head"], "list_cues": {"items": "cue"}, "min": {"items": 2}, "kinds": ["story", "contrast"],
                 "about": "一排 2–5 块小卡（几个例子、两种说法），按旁白一块块立起来，每块一个状态小标"},
    "split": {"required": [], "cues": ["split", "left", "right"], "list_cues": {"left_items": "cue", "right_items": "cue"}, "kinds": ["contrast"],
              "about": "地图沿中缝对折成国外、国内两边，卡片从各自那一片飞过去（只在 contrast 章，放第一个）"},
    "next": {"required": ["items"], "cues": ["head", "flag"], "list_cues": {"items": "cue"}, "min": {"items": 1}, "kinds": ["contrast"],
             "about": "“接下来”的 1–3 个日子：已排期的日期翻牌，传闻的标“尚未证实”并抖一下"},
    # ---- 动效尝试（11-06 晚加；只在尝试版的分镜里出现，正式写稿提示词不提）
    "source_shot": {"required": ["fact", "quote"], "cues": ["show", "mark"], "kinds": ["story", "contrast"],
                    "about": "原文截图：原文网页截图放在纸感卡片里缓慢推近，旁白说到 mark 时荧光笔按行扫过原句；左上角出处签（媒体 · 日期，"
                             "按事件卡来源自动写）；可带一行中文 zh（只取同一条 fact 的 text_zh）。截图没成功自动退回 source_excerpt"},
    "source_excerpt": {"required": ["fact", "quote"], "cues": ["show", "mark"], "kinds": ["story", "contrast"],
                       "about": "原文摘录：事件卡里那条原文自己排成报纸摘录，原句那几行荧光笔扫过，出处签、中文行和 source_shot 一样"},
    "num_chain": {"required": ["items"], "cues": ["head"], "list_cues": {"items": "cue"}, "min": {"items": 2}, "kinds": ["story", "contrast"],
                  "about": "数字递进：2–4 个数 A → B → C 跟着旁白一个个出，最后一个用强调色；\"count\": true 时数字从 0 滚到终值"},
    "headline_open": {"required": ["items"], "cues": [], "list_cues": {"items": "cue"}, "min": {"items": 1}, "kinds": ["open"],
                      "about": "开场“今日速览”：每章一句大字标题压在该章配图上，跟着开场旁白依次出；角标写日期和“今日速览”（放在 open 章）"},
    "tally": {"required": ["count"], "cues": ["head", "show", "count", "except", "states"], "kinds": ["story"],
              "about": "计数（11-06 加）：美国本土轮廓＋大字“N 个州”（region）＋M 格方阵（count），说到“除了几项”时 M−k 格亮、k 格灰（except）；"
                       "只亮分镜点了名、又能在事件卡原文里逐字找到的州（states＋states_ref），不点名就不落到任何一个州；不用党派颜色"},
}
PANELS = {k for k, v in TEMPLATES.items() if v.get("panel")}

# 标志小签能挂在哪里（模板 → 位置）：block 层的 logos / head_logos、列表每一项的 logos、split 两边的 left/right.logos、post_card 的 who.logo
LOGO_SLOTS = {
    "tile_row": ["head_logos", "items[].logos"],
    "column_compare": ["head_logos", "items[].logos"],
    "scale": ["head_logos", "logos"],
    "split": ["left.logos", "right.logos", "left_items[].logos", "right_items[].logos"],
    "post_card": ["who.logo"],
    "quote_card": ["logos"],
    "timeline": ["ticks[].logos"],          # 11-06 补：每个日子可以挂标志
    "next": ["items[].logos"],              # 11-06 晚补："接下来"每一项可以挂标志（谁的计划）
}
# 配图能放在哪里：image_card（2.5D 背景窗）、tile_row 每块小卡的上半截、post_card 的题图；
# 11-06 补：quote_card 的题图（左图右字）、timeline 每个日子上方的小图
IMAGE_SLOTS = {"image_card": ["image"], "tile_row": ["items[].image"], "post_card": ["image"], "quote_card": ["image"],
               "timeline": ["ticks[].image"], "split": ["left_items[].image", "right_items[].image"],   # 11-06 晚补：国内外两边的小卡
               "headline_open": ["items[].image"]}                                                     # 动效尝试：开场速览每一屏的图
SOURCE_BLOCKS = ("source_shot", "source_excerpt")      # 动效尝试：原句只能逐字取自事件卡 quote（check_sources）
CARD_SHOT = ("post_card", "quote_card")                # 结合式（11-06 深夜）：原话卡写 shot 字段，原文截图放进这张卡的图位
PHOTO_BLOCKS = ("tile_row", "compare_panel")           # 压在配图上（11-07，动效尝试版）：写 "photo": 图 id，这一块后面立一张清楚的配图
SHOT_FIELDS = ("fact", "quote")                        # shot 字段必填（zh、source、id、cues.mark 可选），写法同 source_shot
SUB_U = 1.85             # 字幕字号（舞台宽度的百分之几，video3.css 的 .v3sub i）；原句在成片里不能比它小
COUNT_BLOCKS = ("quote_card", "num_chain")             # 动效尝试："count": true 只在这两种模板上起作用
SHOT_DIR = "06_配图/原文截图"                          # source_shots.mjs 截的图和记录（<id>.png、<id>.json）
SHOT_MAX = 3                                           # 一期最多几处原文截图（多了只提醒）
NUM_CHAIN_MAX = 4
SPLIT_SIDES = ("left_items", "right_items")
TICK_IMAGE_MAX = 3       # 一条时间轨最多几张小图（多了互相挤），超了提醒
# post_card 的平台：kind → 事件卡原文里应能看到的字（核平台用）
PLATFORMS = {"podcast": ["播客", "podcast"], "x": ["推文", "twitter", "tweet", "x 上", "在 x", "on x"], "threads": ["threads"],
             "youtube": ["youtube", "视频"], "statement": ["声明", "statement", "公告", "announcement"],
             "document": ["文件", "readme", "文档", "报告", "filing", "document", "仓库", "repository", "招股书"],
             "post": ["帖子", "发文", "post"]}
IMG_EXT = ("", ".png", ".jpg", ".jpeg", ".webp")


def say(*a):
    print(*a, flush=True)


def is_label(x):
    return isinstance(x, dict) and ("zh" in x or "en" in x) and not ("type" in x)


# ---------------------------------------------------------------- 新动效的总开关（2026-11-07 并入正式流程时加）
# 开（默认）：分镜里写了的原文截图、数字递进、开场速览、数字滚动、压在配图上的小卡和对比卡都照画。
# 关：组装前把这些块和字段去掉（strip_motion），退回 11-06 以前的画法；fd 第 14 步也不截图。
# 先看环境变量 FD_MOTION（只管这一次运行），再看项目根的 fd_开关.json；都没有或读不出来按"开"。
# pipeline/orchestrator/common.py 的 motion_switch 是同一套规则（fd 只用标准库，不 import 这里），两边要一起改。
MOTION_SWITCH_FILE = Path(__file__).resolve().parents[2] / "fd_开关.json"
MOTION_SWITCH_KEY = "新动效和原文截图"
MOTION_BLOCKS = ("source_shot", "source_excerpt", "num_chain", "headline_open")
_OFF = ("off", "0", "false", "no", "关", "关闭", "关掉")
_ON = ("on", "1", "true", "yes", "开", "打开")


def motion_switch():
    """返回 (开着没有, 从哪来的一句话)。"""
    env = str(os.environ.get("FD_MOTION") or "").strip().lower()
    if env in _OFF:
        return False, "环境变量 FD_MOTION=%s" % env
    if env in _ON:
        return True, "环境变量 FD_MOTION=%s" % env
    try:
        v = str(json.loads(MOTION_SWITCH_FILE.read_text(encoding="utf-8")).get(MOTION_SWITCH_KEY) or "").strip().lower()
    except (OSError, ValueError, AttributeError):
        return True, "没有 fd_开关.json（或读不出来），按“开”"
    if v in _OFF:
        return False, "fd_开关.json 写着“关”"
    return True, "fd_开关.json 写着“开”" if v in _ON else "fd_开关.json 里的值认不出（%r），按“开”" % v


def motion_off():
    return not motion_switch()[0]


# 视频导演开关（2026-11-08 晚加；pipeline/orchestrator/common.py 的 director_switch 是同一套规则，两边要一起改）：
# 先看环境变量 FD_DIRECTOR，再看 fd_开关.json 的"视频导演"；都没有或读不出来按"开"。
# 组装这边只用它决定 11-08 的渲染修复（fix1108：封面图、对比卡长数值、卡片及时收起、柱子、时间轴小图与小字、对比卡压图不出画、
# 滚动数字千位逗号）开不开：要新动效开关和导演开关都开着才开。导演开关关着时，视频和加导演以前逐像素一样。
DIRECTOR_SWITCH_KEY = "视频导演"


def director_switch():
    """返回 (开着没有, 从哪来的一句话)。"""
    env = str(os.environ.get("FD_DIRECTOR") or "").strip().lower()
    if env in _OFF:
        return False, "环境变量 FD_DIRECTOR=%s" % env
    if env in _ON:
        return True, "环境变量 FD_DIRECTOR=%s" % env
    try:
        v = str(json.loads(MOTION_SWITCH_FILE.read_text(encoding="utf-8")).get(DIRECTOR_SWITCH_KEY) or "").strip().lower()
    except (OSError, ValueError, AttributeError):
        return True, "没有 fd_开关.json（或读不出来），按“开”"
    if v in _OFF:
        return False, "fd_开关.json 的“视频导演”写着“关”"
    return True, "fd_开关.json 的“视频导演”写着“开”" if v in _ON else "fd_开关.json 的“视频导演”值认不出（%r），按“开”" % v


def render_fix_on():
    """11-08 渲染修复开不开：新动效开关和视频导演开关都开着。"""
    return motion_switch()[0] and director_switch()[0]


def strip_motion(sb):
    """开关关着时，组装前去掉 11-06 晚以后加的新动效（块和字段），返回一句提醒（没有可去的返回 []）。
    去掉的块：source_shot、source_excerpt、num_chain、headline_open；去掉的字段：原话卡和时间轴日子的 shot、quote_card 的 count、
    tile_row / compare_panel 的 photo、compare_panel 的 src_tag 和 bars[].val、title 的 cover（11-08 加）。一章的模板全去掉了，structure 照旧换成一张要点卡。"""
    gone = []
    for c in sb.get("chapters") or []:
        if not c.get("blocks"):
            continue
        keep = []
        for b in c.get("blocks") or []:
            if not isinstance(b, dict):
                keep.append(b)
                continue
            t, tag = b.get("type"), "「%s」%s/%s" % (c.get("id"), b.get("type"), b.get("id"))
            if t in MOTION_BLOCKS:
                gone.append(tag)
                continue
            f = []
            if t in CARD_SHOT and "shot" in b:
                b.pop("shot")
                f.append("shot")
            if t == "quote_card" and "count" in b:
                b.pop("count")
                f.append("count")
            if t in PHOTO_BLOCKS and "photo" in b:
                b.pop("photo")
                (b.get("cues") or {}).pop("photo", None)
                f.append("photo")
            if t == "compare_panel":
                if "src_tag" in b:
                    b.pop("src_tag")
                    f.append("src_tag")
                if any(isinstance(x, dict) and "val" in x for x in b.get("bars") or []):
                    for x in b.get("bars") or []:
                        if isinstance(x, dict):
                            x.pop("val", None)
                    f.append("bars[].val")
            if t == "timeline" and any(isinstance(k, dict) and "shot" in k for k in b.get("ticks") or []):
                for k in b.get("ticks") or []:
                    if isinstance(k, dict):
                        k.pop("shot", None)
                f.append("ticks[].shot")
            if f:
                gone.append("%s 的 %s" % (tag, "、".join(f)))
            keep.append(b)
        c["blocks"] = keep
    if isinstance(sb.get("title"), dict) and "cover" in sb["title"]:      # 11-08（K42）：封面图也算新动效，关着时不用
        sb["title"].pop("cover")
        gone.append("title 的 cover（封面图）")
    if not gone:
        return []
    return ["新动效开关关着（%s）：组装时去掉了 %s，视频按 11-06 以前的画法出" % (motion_switch()[1], "；".join(gone))]


# ---------------------------------------------------------------- 读入、结构校验
def load(path):
    p = Path(path)
    if not p.exists():
        raise SystemExit("找不到视频分镜：%s（按 pipeline/prompts/写稿_视频v3.md 写一份）" % p)
    try:
        sb = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit("视频分镜不是合法的 JSON：%s（%s）" % (p, e))
    if sb.get("schema") != SCHEMA:
        raise SystemExit("视频分镜的 schema 应为 %s（现在是 %r）" % (SCHEMA, sb.get("schema")))
    return sb


def pending(sb, c, name):
    """structure 因为配图文件还不在而去掉的图，按章记在 sb["_pending_images"]（第 7 步在第 10 步配图之前跑，图本来就还没生成）；
    check_relations 算"这一章有没有配图"时把它们算上。不进播放器数据（video3_build 只取列出的字段）。"""
    if name:
        sb.setdefault("_pending_images", {}).setdefault(c.get("id"), []).append(Path(str(name)).stem)


def structure(sb, issue):
    """检查章的结构；数据不够的模板去掉（提醒），返回提醒列表。结构不对就停。"""
    warn, bad = [], []
    sb["_issue"] = str(issue)      # 11-06：编播放器数据时给新图位（quote_card、时间轨小图）备图用；不进播放器数据
    chs = sb.get("chapters") or []
    kinds = [c.get("kind") for c in chs]
    if not chs or kinds[0] != "open" or kinds[-1] != "close":
        bad.append("第一章要是 open、最后一章要是 close（现在：%s）" % kinds)
    n_story = kinds.count("story")
    if not 1 <= n_story <= 4:
        bad.append("story 章要 1–4 章（现在 %d）" % n_story)
    if kinds.count("contrast") > 1 or ("contrast" in kinds and kinds.index("contrast") != len(kinds) - 2):
        bad.append("contrast 章最多一章，而且放在 close 前面")
    if not 3 <= len(chs) <= 7:
        bad.append("一共要 3–7 章（现在 %d）" % len(chs))
    ids = [c.get("id") for c in chs]
    if len(set(ids)) != len(ids) or not all(isinstance(i, str) and re.match(r"^[a-z][a-z0-9_]*$", i) for i in ids):
        bad.append("章 id 要唯一、小写字母开头（现在：%s）" % ids)
    for c in chs:
        if not (c.get("narration") or "").strip():
            bad.append("「%s」没有旁白" % c.get("id"))
        if not c.get("title"):
            bad.append("「%s」没有 title（旁白里的章名）" % c.get("id"))
        if c.get("kind") == "story" and not c.get("map_cue"):
            bad.append("「%s」没有 map_cue（开场里说到它的那几个字）" % c.get("id"))
        if c.get("kind") in ("story", "contrast") and not c.get("chip"):
            bad.append("「%s」没有 chip（地图上的热点卡）" % c.get("id"))
    if bad:
        raise SystemExit("视频分镜结构不对：\n  " + "\n  ".join(bad))
    # 模板：不认识的、数据不够的去掉
    for c in chs:
        keep = []
        for b in c.get("blocks") or []:
            t, tp = b.get("type"), TEMPLATES.get(b.get("type"))
            why = None
            if not tp:
                why = "不认识的模板"
            elif c["kind"] not in tp["kinds"]:
                why = "这种模板不能放在 %s 章" % c["kind"]
            else:
                miss = [f for f in tp["required"] if not b.get(f)]
                few = [f for f, n in (tp.get("min") or {}).items() if len(b.get(f) or []) < n]
                if miss:
                    why = "缺字段 %s" % "、".join(miss)
                elif few:
                    why = "数据太少（%s）" % "、".join("%s 至少 %d 项" % (f, tp["min"][f]) for f in few)
                elif t == "image_card" and not find_image(issue, b.get("image")):
                    why = "找不到配图 %s" % b.get("image")
                    pending(sb, c, b.get("image"))
                elif t == "split" and not (b.get("left_items") or b.get("right_items")):
                    why = "两边都没有卡片"
                elif t == "tally":
                    why = tally_problem(b)
                elif t == "source_shot":           # 动效尝试：截图没成功就退回 source_excerpt（版式、时间不变）
                    shot_fallback(issue, c, b, warn)
                elif t in CARD_SHOT and "shot" in b:   # 结合式：原话卡带原文截图
                    card_shot(issue, c, b, warn)
                elif t == "timeline" and any(isinstance(k, dict) and "shot" in k for k in b.get("ticks") or []):
                    tick_shots(issue, c, b, warn)      # 结合式：时间轴日子带原文截图
                elif t == "headline_open":
                    why = headline_problem(sb, b)
            if not why and t in PHOTO_BLOCKS and b.get("photo") and not find_image(issue, b["photo"]):   # 11-07：压在配图上，图找不到就照原样
                warn.append("「%s」%s/%s 找不到配图 %s（photo），这一块照原样、不压在图上" % (c["id"], t, b.get("id"), b["photo"]))
                pending(sb, c, b.pop("photo"))
            if not why:          # 小卡、帖子卡、要点卡、时间轨日子上的配图找不到：只去掉这张图，版式和时间不变
                owners = ((b.get("items") or []) if t in ("tile_row", "headline_open") else (b.get("ticks") or []) if t == "timeline"
                          else [b] if t in ("post_card", "quote_card")
                          else [x for f in SPLIT_SIDES for x in b.get(f) or []] if t == "split" else [])
                for it in owners:
                    if isinstance(it, dict) and it.get("image") and not find_image(issue, it["image"]):
                        warn.append("「%s」%s/%s 找不到配图 %s，这一块不带图" % (c["id"], t, b.get("id"), it["image"]))
                        sb.setdefault("_pending_items", []).append(id(it))     # 11-07：check_motion 认得这一项原来写了图（第 7 步时还没画）
                        pending(sb, c, it.pop("image"))
            if why:
                warn.append("「%s」去掉模板 %s/%s：%s" % (c["id"], t, b.get("id"), why))
                continue
            b.setdefault("id", "%s%d" % (t, len(keep) + 1))
            keep.append(b)
        if c["kind"] in ("story", "contrast") and not [b for b in keep if b["type"] != "image_card"]:
            chip = c.get("chip") or {}
            keep = [{"type": "quote_card", "id": "fallback", "text": chip.get("sub") or chip.get("name") or {"zh": c.get("storyline", "")},
                     "who": chip.get("name"), "cues": {"show": "@start"}}]
            warn.append("「%s」没有能画的模板，换成一张要点卡" % c["id"])
        c["blocks"] = keep
    return warn + check_timeline_gaps(sb) + count_problems(sb) + shot_budget(sb)


# ---------------------------------------------------------------- 时间轨的间隔（2026-11-05 补，只提醒）
# 播放器（site/v3/video3.js 的 tlSpread）里 timeline 的 pos 只排先后、不按真实时间比例：整段先拉满整条轨，相邻两个日子
# 至少隔开整条轨的 TIMELINE_GAP（JS 一侧是 TL_GAP，两边要一样；7 个日子放不下时等分），挨得更近的自动拉开，标签才不叠。
# 11-04 国行 AI 那一章照真实时间写了 0.96 和 1.0，"11 月 4 日"和"12 月"两张标签叠成了"11 月 4 日 月"。
# 渲染照样能出（自动拉开），所以只提醒，告诉写稿的人画面上的间隔不是他写的比例；"等了很久"要用 wait 拱线表达。
TIMELINE_GAP = 0.2


def _tick_name(t):
    d = t.get("date")
    return (d.get("zh") or d.get("en") or "") if isinstance(d, dict) else str(d or "")


def check_timeline_gaps(sb):
    """timeline 相邻日子的 pos：倒退的、拉满整条轨以后间隔小于 TIMELINE_GAP 的，提醒（不拦）。算法和播放器一致。"""
    warn = []
    for c in sb.get("chapters") or []:
        for b in c.get("blocks") or []:
            if not isinstance(b, dict) or b.get("type") != "timeline":
                continue
            ticks = [t for t in (b.get("ticks") or [])[:7] if isinstance(t, dict)]
            n = len(ticks)
            if n < 2 or all(t.get("pos") is None for t in ticks):
                continue                                  # 不写 pos 就是等分，不用查
            where = "「%s」timeline/%s" % (c.get("id"), b.get("id"))
            raw = []
            for i, t in enumerate(ticks):
                v = t.get("pos")
                ok = isinstance(v, (int, float)) and not isinstance(v, bool) and v == v
                raw.append(min(1.0, max(0.0, float(v))) if ok else i / (n - 1))
            back = [i for i in range(1, n) if raw[i] < raw[i - 1]]
            if back:
                warn.append("%s 的 pos 没按先后从小到大（第 %s 个比前一个小）：播放器把倒退的当成和前一个同一处，再拉开；"
                            "pos 只排先后，按日子的顺序写" % (where, "、".join(str(i + 1) for i in back)))
            q = raw[:]
            for i in range(1, n):
                q[i] = max(q[i], q[i - 1])
            tot = q[-1] - q[0]
            m = min(TIMELINE_GAP, 1.0 / (n - 1))
            near = []
            for i in range(n - 1):
                g = (q[i + 1] - q[i]) / tot if tot > 1e-6 else 1.0 / (n - 1)
                if g < m - 1e-6:
                    near.append("第 %d、%d 个（%s → %s）只差 %.2f" % (i + 1, i + 2, _tick_name(ticks[i]), _tick_name(ticks[i + 1]), g))
            if near:
                warn.append("%s 相邻日子挨得太近：%s（按整条轨算，不到 %.2f）。播放器会自动拉开到至少 %.2f，标签不会叠，"
                            "但画面上的间隔不再是写的比例——pos 只排先后；要表达“等了很久”，用 wait 拱线"
                            % (where, "；".join(near), m, m))
    return warn


# ---------------------------------------------------------------- 动效尝试（2026-11-06 晚加）：原文截图、开场速览
def find_shot(issue, sid):
    """06_配图/原文截图/<sid>.json：source_shots.mjs 的记录。返回 (记录, png 路径)；没有、失败、缺图返回 (记录或 None, None)。"""
    if not issue or not sid or not re.match(r"^[A-Za-z0-9_]+$", str(sid)):
        return None, None
    jp = Path(issue) / SHOT_DIR / (str(sid) + ".json")
    try:
        rec = json.loads(jp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    png = Path(issue) / SHOT_DIR / str(rec.get("png") or (str(sid) + ".png"))
    if not rec.get("ok") or not png.is_file() or not rec.get("lines"):
        return rec, None
    return rec, png


def shot_problem(issue, sid, owner, slot, b):
    """一处原文截图能不能用：记录要在、截图成功、截的是同一句、裁得干净、原句在成片里不比字幕小。返回 (记录, png, 不能用的原因)。"""
    rec, png = find_shot(issue, sid)
    why = None
    if rec is None:
        why = "没有截图记录（%s/%s.json）" % (SHOT_DIR, sid)
    elif png is None:
        why = "截图没成功：%s" % (rec.get("reason") or "缺图或没量到行位置")
    elif str(rec.get("quote") or "") != str(owner.get("quote") or ""):
        why = "截图截的不是这一句（记录里的原句和分镜对不上）"
    else:
        fu = shot_font_u(rec, slot, b, owner)
        if fu is not None and fu < SUB_U - 1e-6:
            why = "原句在成片里约 %.2f（字幕 %.2f，按舞台宽度的百分之几算），比字幕小" % (fu, SUB_U)
    return rec, png, why


def shot_fallback(issue, c, b, warn):
    """source_shot：截图要在、成功、截的是同一句原话、原句不比字幕小；不行就把这一块换成 source_excerpt（同样的字段、触发词、位置），并提醒为什么。"""
    sid = b.get("shot") or b.get("id")
    rec, png, why = shot_problem(issue, sid, b, "full", b)
    if why:
        warn.append("「%s」source_shot/%s %s，退回 source_excerpt（原句自己排版，荧光笔照样扫）" % (c.get("id"), b.get("id"), why))
        b["type"] = "source_excerpt"
        b["_shot_fail"] = why
        return
    b["_shot"] = {"png": str(png), "rec": rec}


def _owner_shot(issue, where, b, owner, slot, sid, warn):
    """结合式的一处 shot：截图能用就记 _shot；不能用记 _shot_fail（播放器在同一个图位换成原句摘录，荧光笔照样扫），并提醒为什么。"""
    rec, png, why = shot_problem(issue, sid, owner, slot, b)
    if why:
        warn.append("%s %s，这一处改用原句摘录（放在同一个图位，荧光笔照样扫）" % (where, why))
        owner["_shot_fail"] = why
        owner.pop("_shot", None)
        return
    owner.pop("_shot_fail", None)
    owner["_shot"] = {"png": str(png), "rec": rec}


def _shot_fields_ok(where, s, warn):
    if not isinstance(s, dict) or any(not s.get(f) for f in SHOT_FIELDS):
        warn.append("%s 的 shot 要写成 {fact, quote, …}（缺字段），这一处不带截图" % where)
        return False
    if s.get("id") is not None and not re.match(r"^[A-Za-z0-9_]+$", str(s["id"])):
        warn.append("%s 的 shot.id 只能用字母、数字、下划线（现在 %r），这一处不带截图" % (where, s["id"]))
        return False
    return True


def card_shot(issue, c, b, warn):
    """post_card / quote_card 的 shot：截图放进这张卡的图位、替代 image（image 记进 _image_replaced，不备图、不算配图）；
    字段不全就去掉 shot，卡片照旧（带原来的 image）。"""
    where = "「%s」%s/%s" % (c.get("id"), b.get("type"), b.get("id"))
    if not _shot_fields_ok(where, b.get("shot"), warn):
        b.pop("shot", None)
        return
    if b.get("image"):
        b["_image_replaced"] = b.pop("image")
    _owner_shot(issue, where + " 的 shot", b, b["shot"], "card", b["shot"].get("id") or b.get("id"), warn)


def tick_shots(issue, c, b, warn):
    """timeline 某个日子的 shot：截图当这一天的小图（替代这一天的 image）；截图 id 默认 <块 id>_t<第几个，从 0 数>。"""
    for k, tk in enumerate(b.get("ticks") or []):
        if not isinstance(tk, dict) or "shot" not in tk:
            continue
        where = "「%s」timeline/%s 第 %d 个日子（%s）" % (c.get("id"), b.get("id"), k + 1, _tick_name(tk))
        if not _shot_fields_ok(where, tk.get("shot"), warn):
            tk.pop("shot", None)
            continue
        if tk.get("image"):
            tk["_image_replaced"] = tk.pop("image")
        _owner_shot(issue, where + " 的 shot", b, tk["shot"], "tick", tk["shot"].get("id") or "%s_t%d" % (b.get("id"), k), warn)
        # 11-07 补：截图不能用、退回摘录时，这一天原来的小图留着当小图（弹出框里照样是摘录、荧光照样扫）；
        # 原来小图会变成只写媒体名的白卡（11-07 尝试版"11 月 6 日"那天）。截图成功时照旧替代 image。
        if tk["shot"].get("_shot_fail") and tk.get("_image_replaced"):
            tk["image"] = tk.pop("_image_replaced")


# 原句在成片里有多大（2026-11-06 深夜加）：字号按舞台宽度的百分之一（u）算，和字幕（SUB_U）比。
# 截图记录里有原句的字号（font_px，网页上的 CSS 像素）和截图宽（clip.w，同一种像素），播放器里截图框有多宽（u）按图位算：
#   full：source_shot 整屏卡片（video3.js srcBuild：卡片宽 SRC_W=11.6、镜头装下 1.08 倍宽、1.24 倍高，卡片内边距 0.75u）；
#   card：结合式原话卡（video3.js sbxCardBuild：最宽 84.9u、左右内边距共 2.8u、整张卡最高 46u，超了按比例收窄）；
#   tick：时间轴弹出框（.v3tpop 宽 70u，内边距 0.75u）。
# 都按 16:9 横屏（成片 1280×720）算；竖屏另有版式，不在这里查。两边的数要一起改。
STAGE_ASP = 16 / 9
SRC_W, SRC_FW, SRC_FH = 11.6, 1.08, 1.24
SBX_CARD_U, SBX_PAD_U, SBX_HMAX_U = 84.9, 2.8, 46.0
TL_SHOT_U = 70.0


def _zh_lines(s, per):
    n = len(re.sub(r"\s", "", str(s or "")))
    return max(1, -(-n // max(6, int(per)))) if n else 1


def _lab_zh(v):
    return (v.get("zh") or "") if isinstance(v, dict) else str(v or "")


def shot_slot_u(slot, ar, b=None, owner=None):
    """截图框在成片里有多宽（u）。ar：截图宽高比。b：所在的块（card 要它的字估卡片高），owner：写着 zh 的那一层。"""
    owner = owner or {}
    zh = owner.get("zh")
    zlen = 40 if zh is True else len(str(zh or ""))
    if slot == "tick":
        return TL_SHOT_U - 1.5
    if slot == "card":
        b = b or {}
        card = SBX_CARD_U
        for _ in range(3):           # 和 video3.js sbxExtra / sbxCardU 同一个算法
            w = card - SBX_PAD_U
            ex = 1.1 + 1.3 + 2.2 + 0.6
            if zlen:
                ex += 0.6 + 1.4 * 1.45 * _zh_lines("字" * zlen, (w - 1.1) / 1.4)
            if b.get("type") == "post_card":
                role = _lab_zh((b.get("who") or {}).get("role"))
                ex += 0.9 + 1.6 + 0.9 + 2.1 * 1.45 * _zh_lines(_lab_zh(b.get("text")), w / 2.1) + 0.9 + (3.4 if role else 2.6)
            else:
                ex += 0.9 + 1.3 * 1.25 + 0.9 + 3.0 * 1.2 * _zh_lines(_lab_zh(b.get("text")), w / 3.0)
            card = max(40.0, min(SBX_CARD_U, (SBX_HMAX_U - ex) * ar + SBX_PAD_U))
        return card - SBX_PAD_U
    # full：srcBuild 的卡片高（世界单位）估法，再看镜头是按宽还是按高装
    w = SRC_W
    uw = w * SRC_FW / 100
    h = (w - 1.5 * uw) / ar + (1.5 + 2.2 + 0.6) * uw + ((0.6 + 2.1) * uw if zlen else 0)
    vis = max(w * SRC_FW, h * SRC_FH * STAGE_ASP)
    return 100 * w / vis - 1.5


def shot_font_u(rec, slot, b=None, owner=None):
    """原句在成片里的字号（u）；记录里没有字号（旧记录）返回 None（不查）。"""
    try:
        fpx, cw = float(rec.get("font_px")), float((rec.get("clip") or {}).get("w"))
        ar = float(rec.get("w")) / float(rec.get("h"))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if fpx <= 0 or cw <= 0:
        return None
    return fpx / cw * shot_slot_u(slot, ar, b, owner)


def shot_owners(sb):
    """分镜里每一处原文截图／摘录：[(章, 块, owner, 图位, 截图 id, 位置说明)]。owner 是写着 fact、quote、zh、source 的那一层：
    source_shot / source_excerpt 是块本身（图位 full），post_card / quote_card 是它的 shot（card），时间轴日子是那一天的 shot（tick）。"""
    out = []
    for c in sb.get("chapters") or []:
        for b in c.get("blocks") or []:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t in SOURCE_BLOCKS:
                out.append((c, b, b, "full", b.get("shot") or b.get("id"), "「%s」%s/%s" % (c.get("id"), t, b.get("id"))))
            elif t in CARD_SHOT and isinstance(b.get("shot"), dict):
                out.append((c, b, b["shot"], "card", b["shot"].get("id") or b.get("id"), "「%s」%s/%s 的 shot" % (c.get("id"), t, b.get("id"))))
            elif t == "timeline":
                for k, tk in enumerate(b.get("ticks") or []):
                    if isinstance(tk, dict) and isinstance(tk.get("shot"), dict):
                        out.append((c, b, tk["shot"], "tick", tk["shot"].get("id") or "%s_t%d" % (b.get("id"), k),
                                    "「%s」timeline/%s 第 %d 个日子的 shot" % (c.get("id"), b.get("id"), k + 1)))
    return out


def headline_problem(sb, b):
    """headline_open：每一屏写 ch（哪一章，story / contrast 章的 id）和 text；没写 cue 就用那一章的 map_cue（开场里说到它的那几个字）。
    返回去掉这一块的原因（None 表示能画）。"""
    chs = {c.get("id"): c for c in sb.get("chapters") or []}
    items = [it for it in b.get("items") or [] if isinstance(it, dict)]
    if not items:
        return "没有能画的一屏"
    for it in items:
        ch = chs.get(it.get("ch"))
        if not ch or ch.get("kind") not in ("story", "contrast"):
            return "items 的 ch 要写 story 或 contrast 章的 id（现在：%r）" % it.get("ch")
        if not is_label(it.get("text")):
            return "items 每一屏要写 text（{zh, en}）"
        if not it.get("cue") and ch.get("map_cue"):
            it["cue"] = ch["map_cue"]
    b["items"] = items
    return None


def has_real_layer(c):
    """这一章有没有"真东西"：配图（背景窗、小卡上的图、帖子卡／要点卡题图、时间轨小图）、标志小签，或计数模板的美国轮廓（11-06）。"""
    for b in c.get("blocks") or []:
        if b["type"] in ("image_card", "tally", "source_shot") or b.get("image") or b.get("logos") or b.get("head_logos"):
            return True
        if b["type"] in PHOTO_BLOCKS and b.get("photo"):                     # 11-07：压在配图上
            return True
        if b["type"] in CARD_SHOT and isinstance(b.get("shot"), dict):        # 结合式：卡上的原文截图（或摘录）
            return True
        for f in ("items", "left_items", "right_items", "ticks"):
            if any(isinstance(it, dict) and (it.get("image") or it.get("logos") or isinstance(it.get("shot"), dict)) for it in b.get(f) or []):
                return True
        if any(isinstance(b.get(k), dict) and (b[k].get("logos") or b[k].get("logo")) for k in ("left", "right", "who")):
            return True
    return False


def check_layers(sb):
    """每个 story / contrast 章至少一层配图或标志（写稿规则，见 写稿_视频v3.md）；没有就提醒。"""
    return ["「%s」没有配图也没有标志小签：画面只有字卡（每章至少要一层真东西）" % c["id"]
            for c in sb["chapters"] if c["kind"] in ("story", "contrast") and not has_real_layer(c)]


# ---------------------------------------------------------------- 数值字段（2026-11-03 补）
# 播放器（site/v3/video3.js 的 TPL）把下面这些字段当数字读（+x、Math.abs(+x)），读不出数字时不报错，悄悄当成 0 或 1 画：
# 11-03 bill.yield 把 {"zh": "2.08 美元"} 写进了 bar_shrink 的 from.value，柱子塌成一块空玻璃、上半截飞走、数字没出来。
# 模板 → [(字段路径, 必填, 种类)]；"items[]" 是列表每一项；带 "?" 的前缀是可选的那一层（比如 done 不写就不查 done.value）。
# 种类：num 数值、frac 0–1 的示意长度或位置、band 落在第几档（从 0 数，可带小数）、idx 从 0 数的整数序号。
# 只认 JSON 数字：带引号的 "2.08" 播放器虽然读得出，但 check_labels 的"数字对事件卡"只核真正的数字，带引号就漏核了，所以也算要改。
NUM_FIELDS = {
    "bar_shrink": [("from.value", True, "num"), ("to.value", True, "num"), ("done?.value", True, "num")],
    "twin_drop": [("items[].value", True, "num")],
    "column_compare": [("items[].value", True, "num")],
    "quota_bars": [("stages[].value", True, "num")],
    "compare_panel": [("bars[].value", True, "frac")],
    "timeline": [("ticks[].pos", False, "frac"), ("wait?.from", False, "idx"), ("wait?.to", False, "idx")],
    "scale": [("from?.at", False, "band"), ("to.at", False, "band"), ("threshold", False, "idx")],
    "tally": [("count.value", True, "num"), ("except?.value", True, "num")],       # 11-06 加：方阵几格、灰几格
}
# 反过来：播放器把这几个当字显示（tx()），写成裸数字会显示成空白
TEXT_FIELDS = {"particle_counter": ["value"], "compare_panel": ["kpi?.value"]}
NUM_HINT = {"num": "%s 只写数字本身（如 2.08，不加引号、不带单位），画面上要显示的字（带单位的数字，如“第二季度 2.08 美元”）写进同一层的 label",
            "frac": "%s 写 0–1 之间的数字（不加引号）",
            "band": "%s 写落在第几档（从 0 数起的数字，不加引号）",
            "idx": "%s 写从 0 数起的整数序号（不加引号）"}
NUM_HINT_EXTRA = {"twin_drop": "；twin_drop 的单位写进 unit（默认 %）", "quota_bars": "；quota_bars 每根柱子下面的名字写进 label",
                  "tally": "；tally 的 count.value 是方阵格数（整数），except.value 是灰掉的格数，带单位的字写进各自的 label"}


def _field_values(b, path):
    """按 "a[].b"、"a?.b" 这样的路径取值：[(位置说明, 有没有这个字段, 值)]；可选的那一层不在就不算。"""
    out = [("", b)]
    parts = path.split(".")
    for k, part in enumerate(parts):
        last = k == len(parts) - 1
        key, many, opt = part.rstrip("?").replace("[]", ""), part.endswith("[]"), part.endswith("?")
        nxt = []
        for where, obj in out:
            if not isinstance(obj, dict):
                continue
            if last:
                nxt.append((where + key, key in obj, obj.get(key)))
            elif many:
                for i, it in enumerate(obj.get(key) or []):
                    nxt.append(("%s%s 第 %d 项的 " % (where, key, i + 1), it))
            elif opt and obj.get(key) is None:
                continue
            else:
                nxt.append((where + key + ".", obj.get(key)))
        out = nxt
    return out


def _show(v):
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= 40 else s[:38] + "…"


def check_values(sb):
    """模板里播放器当数字读的字段不是数字、当字显示的写成了裸数字 → 要改（总调度第 7 步"视频分镜"那一项跑它）。返回要改的列表。"""
    must = []
    for c in sb.get("chapters") or []:
        for b in c.get("blocks") or []:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            where0 = "「%s」%s/%s" % (c.get("id"), t, b.get("id"))
            for path, required, kind in NUM_FIELDS.get(t, []):
                for where, has, v in _field_values(b, path):
                    hint = NUM_HINT[kind] % where.split(" ")[-1] + (NUM_HINT_EXTRA.get(t, "") if kind == "num" else "")
                    if not has or v is None:
                        if required:
                            must.append("%s 的 %s 没写：播放器读不到数字，会把它当 0 或 1 画。%s" % (where0, where, hint))
                        continue
                    ok = isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")
                    if ok and kind == "frac":
                        ok = 0 <= v <= 1
                    if ok and kind in ("band", "idx"):
                        ok = v >= 0 and (kind == "band" or float(v).is_integer())
                    if not ok:
                        must.append("%s 的 %s 写成了 %s，不是播放器要的数字（读不出来就悄悄当 0 或 1 画：柱子塌掉、数字不出来）。%s"
                                    % (where0, where, _show(v), hint))
            for path in TEXT_FIELDS.get(t, []):
                for where, has, v in _field_values(b, path):
                    if has and isinstance(v, (int, float)):
                        must.append("%s 的 %s 写成了裸数字 %s：这里播放器当字显示，裸数字会显示成空白。写成字 "
                                    "{\"zh\": \"…\", \"en\": \"…\", \"ref\": [...]}（数字照原文带单位）" % (where0, where, _show(v)))
    return must


# ---------------------------------------------------------------- 关系（2026-11-02 晚补，v3.4）
# 画面要画出事情之间的关系，不是几块卡片摆着（写稿_视频v3.md"画面要画出关系"一节）。
# 关系 → 能把它画出来的模板；分镜每个 story 章写 "relation": {"kind": [...], "zh": "…", "ref": [facts 键]}。
# tile_row 只算"并列"（几个并列的例子），一期最多一章靠它撑。
RELATION_KINDS = {
    "对比": ["column_compare", "compare_panel", "twin_drop", "quota_bars"],
    "先后": ["timeline", "next"],
    "因果": ["chain"],
    "链条": ["chain"],
    "分化": ["fork"],
    "规模": ["compare_panel", "column_compare", "particle_counter", "scale", "tally", "num_chain"],
    "刻度": ["scale"],
    "占比": ["compare_panel", "column_compare", "tally", "num_chain"],
    "数量变化": ["bar_shrink", "twin_drop", "quota_bars", "compare_panel", "column_compare", "num_chain"],
    "国内对国外": ["split"],
    "并列": ["tile_row"],
}
RELATION_BLOCKS = {t for k, ts in RELATION_KINDS.items() if k != "并列" for t in ts}


def is_relation_block(b):
    """这个模板本身画的是关系（不算 tile_row：它只画并列）。compare_panel 至少两根对比条才算（一个大数字只是字卡）。"""
    t = b.get("type")
    if t not in RELATION_BLOCKS:
        return False
    return t != "compare_panel" or len(b.get("bars") or []) >= 2


def _relation_kinds(r):
    k = r.get("kind") if isinstance(r, dict) else r
    if isinstance(k, str):
        k = re.split(r"[、,，/ ]+", k)
    return [x.strip() for x in k or [] if isinstance(x, str) and x.strip()]


def check_relations(sb):
    """关系画面的检查，返回 (要改, 提醒)。要改：
      · 靠一排小卡撑起来的章（tile_row 所在的章没有别的关系模板）有两章以上——tile_row 只画并列，一期最多一次；
      · 某个 story 章没有任何画关系的模板（这一期唯一一章 tile_row 撑的"并列"章不算）；
      · contrast（国内外）章没用 split；
      · 同一个 tile_row 里有的小卡有图、有的没有（没图的那块会显示一个空的浅色图位）；
      · 写了 relation 的：关系种类不认识、这一章没有能画它的模板、没写 ref 或 ref 不在 facts 里。
    提醒：story 章没写 relation（11-02 以前的分镜都没有，只按模板查）；一期 tile_row 总数满两个（写明在哪几章、各几个）；
    11-06 起还带上 check_screen 的提醒（按字数估时间的空档、章首主角、时间轨被打断；旁白数字和等级上没上画面；一期配图张数）；
    story 章的配图只在背景窗里、没有清楚露脸的时刻，或背景窗的图在这一章没先露过脸（photo_moments）；
    story / contrast 章一张配图都没写（标志小签不算；11-03 补：那天国内外章只挂了一个小标志，没人提醒）。
    配图文件还没生成（第 7 步在第 10 步配图之前）、被 structure 暂时去掉的，按分镜里写了算（sb["_pending_images"]）。"""
    must, warn = [], []
    chs = [c for c in sb.get("chapters") or [] if c.get("kind") in ("story", "contrast")]
    facts = sb.get("facts") or {}
    blocks = lambda c: [b for b in c.get("blocks") or [] if isinstance(b, dict)]  # noqa: E731
    rel = lambda c: [b for b in blocks(c) if is_relation_block(b)]  # noqa: E731
    alone = [c for c in chs if not rel(c) and any(b.get("type") == "tile_row" for b in blocks(c))]
    if len(alone) >= 2:
        must.append("%d 章靠一排小卡（tile_row）撑着、没有画关系的模板（%s）：tile_row 只画几个并列的例子，一期最多一次；"
                    "其余章先定讲什么关系，再按模板目录换" % (len(alone), "、".join(c["id"] for c in alone)))
    for c in chs:
        if c["kind"] != "story" or rel(c):
            continue
        if len(alone) == 1 and c is alone[0]:
            continue            # 这一期唯一的"并列"章
        has = "、".join(dict.fromkeys(b.get("type", "?") for b in blocks(c))) or "没有模板"
        must.append("「%s」没有画关系的模板（现在是 %s）：先定这一章讲什么关系（对比、先后、因果或链条、分化、规模或刻度、占比、数量变化），"
                    "再选能画它的模板" % (c["id"], has))
    for c in chs:
        if c["kind"] == "contrast" and not any(b.get("type") == "split" for b in blocks(c)):
            must.append("「%s」是国内外那一章，没用 split（contrast 章固定用 split，放第一个）" % c["id"])
    mixed = []
    for c in chs:
        for b in blocks(c):
            if b.get("type") != "tile_row":
                continue
            items = [it for it in b.get("items") or [] if isinstance(it, dict)]
            no = [str(i + 1) for i, it in enumerate(items) if not it.get("image")]
            if no and len(no) < len(items):
                mixed.append("「%s」tile_row/%s 第 %s 块" % (c["id"], b.get("id"), "、".join(no)))
    if mixed:
        must.append("%s没写 image，同一排别的小卡有图——没图的那块会显示空的浅色图位；要么都配图，要么都不带图" % "；".join(mixed))
    for c in chs:
        r = c.get("relation")
        if r is None:
            continue
        kinds = _relation_kinds(r)
        bad = [k for k in kinds if k not in RELATION_KINDS]
        if not kinds or bad:
            must.append("「%s」relation 的关系种类%s（可写：%s）" % (c["id"], "不认识：" + "、".join(bad) if bad else "没写",
                                                           "、".join(RELATION_KINDS)))
            continue
        types = {b.get("type") for b in (rel(c) + [b for b in blocks(c) if b.get("type") == "tile_row"])}
        if not any(t in types for k in kinds for t in RELATION_KINDS[k]):
            must.append("「%s」relation 写的是%s，这一章却没有能画它的模板（可用：%s）" % (
                c["id"], "、".join(kinds), "、".join(dict.fromkeys(t for k in kinds for t in RELATION_KINDS[k]))))
        refs = r.get("ref") if isinstance(r, dict) else None
        refs = [refs] if isinstance(refs, str) else (refs or [])
        miss = [x for x in refs if x not in facts]
        if not refs or miss:
            must.append("「%s」relation %s：画出来的关系要有事件卡原文作依据（ref 指到 facts）" % (
                c["id"], "引用了 facts 里没有的键 " + "、".join(miss) if miss else "没写 ref"))
    no_rel = [c["id"] for c in chs if c["kind"] == "story" and c.get("relation") is None]
    if no_rel:
        warn.append("没写 relation 的 story 章：%s（这一章画什么关系；只按模板查了）" % "、".join(no_rel))
    # 一期 tile_row 总数满两个只提醒（11-02 晚定）：上面"要改"只数靠小卡撑着的章，挨着关系模板的小卡不数；这里全数，给人看一眼
    per = [(c["id"], sum(1 for b in blocks(c) if b.get("type") == "tile_row")) for c in chs]
    per = [(i, n) for i, n in per if n]
    total = sum(n for _, n in per)
    if total >= 2:
        warn.append("这一期用了 %d 个 tile_row（%s）：规矩是一期最多一次，只画几个并列的例子；挨着关系模板的也看看是不是其实是对比、先后"
                    % (total, "、".join("%s %d 个" % (i, n) for i, n in per)))
    # 配图要有清楚露脸的时刻（11-02 晚定，只提醒）：背景窗会虚化、常被玻璃卡片挡住，只能做氛围
    # 11-03 补：国内外（contrast）章也查；一章一张配图都没写的（标志不算）单独提醒
    for c in chs:
        clear, back = photo_moments(c)
        later = (sb.get("_pending_images") or {}).get(c["id"]) or []
        if not (clear or back or later):
            if c["kind"] == "contrast":
                warn.append("「%s」是国内外那一章，一张配图都没有（标志小签不算）：split 两边的小卡可以带题图"
                            "（left_items / right_items 每项写 image，优先用网页已有的图），"
                            "或在 split 后面加一张带题图的 post_card（这组对照里有一句可引的原话时）" % c["id"])
            else:
                warn.append("「%s」一张配图都没有（标志小签不算）：这一章要有一刻让配图清楚露脸"
                            "（带题图的 post_card、并列那一排 tile_row，或跟在 fork 后面立在路尽头）" % c["id"])
            continue
        if back and not clear:
            warn.append("「%s」的配图只在背景窗里（%s）：背景窗会虚化、压在关系模板后面；这一章要有一刻让配图清楚露脸"
                        "（带题图的 post_card、并列那一排 tile_row，或跟在 fork 后面立在路尽头）" % (c["id"], "、".join(back)))
        elif set(back) - set(clear):
            warn.append("「%s」背景窗里的 %s 这一章没有先清楚露过脸：同一张图先露脸，再放到关系模板后面做底"
                        % (c["id"], "、".join(x for x in back if x not in clear)))
    # 11-06 晚补：旁白每章单独配音，章首开口就是英文名、后面只夹两三个字又接英文的（11-06“Ricursive Intelligence，发布了”
    # 转写成 Fabula、“GPT-6 Cyber 在 OpenAI”的“在”被吞）提醒改成中文起句；放在最前面，免得被画面提醒挤出第 7 步摘的前 8 条
    try:
        warn = check_voice_openings(sb) + warn
    except Exception as e:  # noqa: BLE001  只是提醒，出错不能拦住分镜
        warn.append("旁白开头检查没跑成（%s）" % e)
    # 11-06 补：画面检查前移到第 7 步（总调度第 7 步只调 check_relations 和 check_values，所以挂在这里；只提醒）
    try:
        warn += check_screen(sb)
    except Exception as e:  # noqa: BLE001  画面检查只是提醒，出错不能拦住分镜
        warn.append("画面检查没跑成（%s），这次只查了关系" % e)
    try:                    # 11-07 并入正式流程的几条规矩（只提醒）
        warn += check_motion(sb)
    except Exception as e:  # noqa: BLE001
        warn.append("新动效和配图规矩的检查没跑成（%s）" % e)
    return must, warn


def check_voice_openings(sb):
    """视频旁白每章单独一次配音请求（video3_build 默认 chapters）：章首开口是英文名、后面只夹两三个汉字又接英文的 → 提醒。
    判断和播客、对谈用同一个函数（pipeline/lexicon_check.py 第 8 项后半 opening_problem）；只报"强"的，弱的不报。"""
    import sys
    pipe = str(Path(__file__).resolve().parents[2] / "pipeline")
    if pipe not in sys.path:
        sys.path.append(pipe)
    import lexicon_check as LX
    units = [(0, c.get("id"), c.get("narration") or "") for c in sb.get("chapters") or []]
    return ["「%s」旁白开头：%s（“%s”）" % (r["上下文"].split("】")[0].lstrip("【"), r["说明"], r["原文"])
            for r in LX.voice_opening_rows(units, "章") if r["强弱"] == "强"]


def photo_moments(c):
    """一章（story 或 contrast）里的配图分两类：(清楚露脸的, 只做背景窗的)，都按文件名（不带扩展名）记。
    contrast 章不能放 image_card；能露脸的是带题图的 post_card、quote_card、tile_row 小卡，和 split 两边带题图的小卡（11-06 晚补）。
    清楚露脸：post_card、quote_card 的题图、tile_row 小卡上的图、时间轨日子上的小图（播放器里是网页图片，不虚化）、
    章里有 fork 时的第一张 image_card（立在两条路尽头的中间，
    占画面大半，略柔化）。其余 image_card 是背景窗：着色器按低一档的清晰度取样（刻意虚化），挂在模板右后方，常被玻璃卡片挡住一半。"""
    stem = lambda x: Path(str(x)).stem  # noqa: E731
    blocks = [b for b in c.get("blocks") or [] if isinstance(b, dict)]
    fork = any(b.get("type") == "fork" for b in blocks)
    clear, back, first = [], [], True
    for b in blocks:
        t = b.get("type")
        if t in PHOTO_BLOCKS and b.get("photo"):     # 11-07：压在配图上（清楚、不虚化，镜头装下整张图）
            clear.append(stem(b["photo"]))
        if t == "image_card" and b.get("image"):
            (clear if fork and first else back).append(stem(b["image"]))
            first = False
        elif t in CARD_SHOT and isinstance(b.get("shot"), dict):     # 结合式：卡上的原文截图（不算配图张数）
            clear.append("原文截图:%s" % (b["shot"].get("id") or b.get("id")))
        elif t in ("post_card", "quote_card") and b.get("image"):
            clear.append(stem(b["image"]))
        elif t == "timeline":
            clear += [stem(k["image"]) for k in b.get("ticks") or [] if isinstance(k, dict) and k.get("image")]
            clear += ["原文截图:%s_t%d" % (b.get("id"), j) for j, k in enumerate(b.get("ticks") or []) if isinstance(k, dict) and isinstance(k.get("shot"), dict)]
        elif t == "tile_row":
            clear += [stem(it["image"]) for it in b.get("items") or [] if isinstance(it, dict) and it.get("image")]
        elif t == "split":          # 11-06 晚补：国内外小卡上的题图（网页图片，不虚化）
            clear += [stem(it["image"]) for f in SPLIT_SIDES for it in b.get(f) or [] if isinstance(it, dict) and it.get("image")]
        elif t == "source_shot":    # 动效尝试：原文截图也是清楚露脸的真东西（不算配图张数）
            clear.append("原文截图:%s" % b.get("id"))
    return clear, back


PHOTO_DIRS = ("06_配图/视频", "06_配图/v3.1", "06_配图/v3", "06_配图")
VIDEO_IMG_DIR = "06_配图/视频"        # 视频专用配图（image_requests 生成或取来的）


def find_image(issue, name):
    """配图文件：按 PHOTO_DIRS 顺序找；name 可以是文件名，也可以是 image_requests 的 id（不带扩展名）。"""
    if not name:
        return None
    for d in PHOTO_DIRS:
        for ext in IMG_EXT:
            p = issue / d / (name + ext)
            if (ext or Path(name).suffix) and p.is_file():
                return p
    return None


def image_requests(sb):
    """分镜里的 image_requests 检查格式；返回 [{id, brief_en | commons, placement, events}]，格式不对就停。"""
    reqs, bad, seen = [], [], set()
    for r in sb.get("image_requests") or []:
        i = r.get("id")
        if not (isinstance(i, str) and re.match(r"^[a-z][a-z0-9_]*$", i)) or i in seen:
            bad.append("image_requests 的 id 要唯一、小写字母开头：%r" % i)
            continue
        seen.add(i)
        if not (r.get("brief_en") or r.get("commons")):
            bad.append("%s 既没有 brief_en（生成）也没有 commons（取资料图）" % i)
        if r.get("placement") not in ("tile", "backdrop", "inset", "card"):
            bad.append("%s 的 placement 要是 tile / backdrop / inset / card" % i)
        reqs.append(r)
    if bad:
        raise SystemExit("视频分镜的 image_requests 不对：\n  " + "\n  ".join(bad))
    used = set()
    for c in sb.get("chapters") or []:
        for b in c.get("blocks") or []:
            used.add(b.get("image"))
            used.add(b.get("photo"))
            for it in (b.get("items") or []) + (b.get("ticks") or []) + [x for f in SPLIT_SIDES for x in b.get(f) or []]:
                if isinstance(it, dict):
                    used.add(it.get("image"))
    for r in reqs:
        if r["id"] not in used:
            print("注意：image_requests 里的 %s 没有地方用到" % r["id"], flush=True)
    return reqs


# ---------------------------------------------------------------- 事实核对
def entry_text(e):
    if isinstance(e, str):
        return e
    return " ".join(str(e.get(k) or "") for k in ("text_zh", "text_en", "value", "unit", "meaning_zh", "meaning_en", "compare_zh",
                                                  "said_zh", "said_en", "quote", "who", "name", "url", "date", "type"))


def check_facts(sb, cards):
    """facts 逐条到事件卡里找原文；返回 {键: {ev, src, text}}。"""
    out, bad = {}, []
    for k, f in (sb.get("facts") or {}).items():
        ev, field, i, check = f.get("event"), f.get("field"), f.get("index"), f.get("check") or ""
        c = cards.get(ev)
        lst = (c or {}).get(field) or []
        if not c or not isinstance(i, int) or i >= len(lst):
            bad.append("%s：%s 没有 %s[%s]" % (k, ev, field, i))
            continue
        txt = entry_text(lst[i])
        if not check or check not in txt:
            bad.append("%s：%s %s[%d] 里找不到「%s」" % (k, ev, field, i, check))
            continue
        out[k] = {"ev": ev, "src": lst[i].get("source_id") if isinstance(lst[i], dict) else None, "text": txt,
                  "entry": lst[i], "card_sources": c.get("sources") or []}     # 动效尝试：原文摘句要逐字核 quote、取出处（check_sources）
    if bad:
        raise SystemExit("核对失败（画面数字只能来自事件卡）：\n  " + "\n  ".join(bad))
    return out


NAME_TOKENS = []     # 名字里本来就带数字的（7Fresh Coffee、7-Eleven、36Kr）：核数字时不算；video3_build 按英文名表填


def check_numbers(where, text, refs, facts, bad):
    for tok in sorted(NAME_TOKENS, key=len, reverse=True):
        text = re.sub(r"(?<![A-Za-z0-9])" + re.escape(tok) + r"(?![A-Za-z0-9])", " ", text or "", flags=re.I)
    nums = [n.replace(",", "") for n in NUM_RE.findall(text or "")]
    if not nums:
        return
    if not refs:
        bad.append("「%s」带数字（%s），但没写 ref" % (where, text))
        return
    miss_ref = [r for r in refs if r not in facts]
    if miss_ref:
        bad.append("「%s」引用了 facts 里没有的键 %s" % (where, "、".join(miss_ref)))
        return
    pool = " ".join(facts[r]["text"] for r in refs).replace(",", "")
    pool_nums = set(NUM_RE.findall(pool))
    miss = [n for n in nums if n not in pool_nums and n not in pool]
    if miss:
        bad.append("「%s」里的数字 %s 在它引用的事件卡原文（%s）里找不到" % (where, "、".join(miss), "、".join(refs)))


def walk_labels(x, path, out, inherit=None):
    """找出所有字（{zh,en,ref}）；数值字段 value 记下来，按同一层或上一层的 ref 核对。"""
    if is_label(x):
        out.append((path, x, x.get("ref") or inherit))
        return
    if isinstance(x, dict):
        lab = x.get("label")
        ref = x.get("ref") or (lab.get("ref") if isinstance(lab, dict) else None)
        for k, v in x.items():
            if k in ("cues", "ref", "check", "facts", "cue", "at", "say", "image", "_src", "_shot", "_image_replaced") and not is_label(v):
                continue
            if k == "value" and isinstance(v, (int, float)) and not isinstance(v, bool):
                out.append((path + ".value", {"zh": ("%g" % abs(v)), "_num": True}, ref or inherit))
                continue
            if k == "shot" and isinstance(v, dict):      # 结合式的 shot：原句、中文行按事件卡逐字核（check_sources），这里只看出处签等别的字
                walk_labels({kk: vv for kk, vv in v.items() if kk not in ("zh", "quote")}, path + ".shot", out, ref or inherit)
                continue
            walk_labels(v, path + "." + k, out, ref or inherit)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            walk_labels(v, "%s[%d]" % (path, i), out, inherit)


def check_labels(sb, facts):
    bad, labels = [], []
    walk_labels({k: v for k, v in sb.items() if k in ("title",)}, "title", labels)
    for c in sb["chapters"]:
        for k in ("chip", "note", "end", "relation"):          # relation：这一章画的关系，里面的数字也按 ref 核
            if isinstance(c.get(k), (dict, list)) and c.get(k):
                walk_labels(c[k], "%s.%s" % (c["id"], k), labels)
        for b in c.get("blocks") or []:
            if b["type"] == "compare_panel":       # 对比条的长度只是示意，不是事实数字
                b2 = dict(b, bars=[{k: v for k, v in bar.items() if k != "value"} for bar in b.get("bars") or []])
            elif b["type"] == "quota_bars":       # 柱子的数值按 stages_ref 核
                b2 = dict(b, stages=[dict(s, ref=b.get("stages_ref")) for s in b.get("stages") or []])
            else:
                b2 = b
            walk_labels(b2, "%s.%s" % (c["id"], b["id"]), labels)
    for path, lab, refs in labels:
        if path == "title.date":
            continue
        refs = lab.get("ref") or refs
        if isinstance(refs, str):
            refs = [refs]
        for lang in ("zh", "en"):
            if lab.get(lang):
                check_numbers("%s(%s)" % (path, lang), lab[lang], refs, facts, bad)
    states = check_tally(sb, facts)          # 11-06：计数模板点亮的州也只能来自事件卡（核不上同样停）
    srcs = check_sources(sb, facts)          # 动效尝试：原文截图／摘录的原句、中文行、出处签也只能来自事件卡（核不上同样停）
    if bad or states or srcs:
        raise SystemExit("核对失败（画面上的数字%s只能来自事件卡）：\n  " % (("、点亮的州" if states else "") + ("、原文摘句" if srcs else ""))
                         + "\n  ".join(bad + states + srcs))
    return len(labels)


# ---------------------------------------------------------------- 原文截图／摘录（动效尝试，2026-11-06 晚加）
MONTH_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def source_date(raw):
    """事件卡来源的日期（2026-11-06 或 2026-11-06T00:37:56Z）→ 出处签上的 {zh: "11 月 6 日", en: "Nov 6"}；读不出返回 None。
    只取写在事件卡里的那一天（UTC 记的就按 UTC 那天），不按网页上显示的日期改。"""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(raw or ""))
    if not m:
        return None
    mo, d = int(m.group(2)), int(m.group(3))
    return {"zh": "%d 月 %d 日" % (mo, d), "en": "%s %d" % (MONTH_EN[mo - 1], d)}


def source_name(name):
    """事件卡来源名（"The Verge · AI""CNBC · 科技""OpenAI 新闻（官方公告）"）→ 出处签默认写法（"The Verge""CNBC""OpenAI 新闻"）。"""
    return re.split(r"\s*[·（(]", str(name or "").strip())[0].strip()


def check_sources(sb, facts):
    """source_shot / source_excerpt：
      · fact 指到 facts 里的一条，那一条要有 quote；
      · quote（画面上荧光笔扫的那句）要逐字是那条 quote 里连续的一段（不改一个字母、标点）；
      · zh（可选，画面下方的中文一行）只能取同一条的 text_zh：写 true 就整句用，写字就要逐字是 text_zh 里连续的一段；
      · source（可选，出处签上的媒体名 {zh, en}）要出现在事件卡来源名或网址里；不写就按来源名自动取；日期按事件卡来源的日期写。
    核不上的返回问题列表（check_labels 里一起停）；核得上的把出处、全文写进 b["_src"]（编播放器数据时用）。
    结合式（11-06 深夜）：post_card / quote_card 的 shot、时间轴日子的 shot 一样核（shot_owners），结果写进那个 shot 的 _src。"""
    bad = []
    for _c, _blk, b, _slot, _sid, where in shot_owners(sb):
        f = facts.get(b.get("fact"))
        e = (f or {}).get("entry")
        if not f or not isinstance(e, dict) or not e.get("quote"):
            bad.append("%s 的 fact %r 不在 facts 里，或那一条没有 quote（原句只能取自事件卡 facts[].quote）" % (where, b.get("fact")))
            continue
        q, full = b.get("quote"), str(e["quote"])
        if not isinstance(q, str) or not q.strip() or q not in full:
            bad.append("%s 的原句不是事件卡 %s 那条 quote 里逐字的一段：%r" % (where, f["ev"], (q or "")[:80]))
            continue
        zh, zpool = b.get("zh"), str(e.get("text_zh") or e.get("said_zh") or "")      # who_said 那一类的中文写在 said_zh
        if zh is True:
            zh = zpool
        if zh not in (None, False, "") and (not isinstance(zh, str) or zh not in zpool):
            bad.append("%s 的中文行只能取同一条的 text_zh（逐字的一段）：%r" % (where, zh))
            continue
        src = next((x for x in f.get("card_sources") or [] if x.get("id") == f.get("src")), None)
        if not src or not src.get("url"):
            bad.append("%s：事件卡 %s 里找不到这条 quote 的来源（source_id %r）" % (where, f["ev"], f.get("src")))
            continue
        pool = (str(src.get("name") or "") + " " + str(src.get("url") or "")).lower()
        lab = b.get("source")
        if lab is not None:
            if not is_label(lab) or any(v and str(v).lower() not in pool for v in (lab.get("zh"), lab.get("en"))):
                bad.append("%s 的出处签 %r 在事件卡来源（%s）里找不到" % (where, lab, src.get("name")))
                continue
            name = txt(lab)
        else:
            nm = source_name(src.get("name"))
            name = {"zh": nm, "en": nm}
        date, warn = source_date(src.get("date")), None
        pd = ((b.get("_shot") or {}).get("rec") or {}).get("page_date")
        if date and pd and str(pd)[:10] != str(src.get("date") or "")[:10]:
            # 网页自己写的日期和事件卡记的不是同一天（多半是时区：事件卡按 UTC 记）：签上不写日期，免得和截图里的日期打架
            warn = "%s：网页上写的日期 %s 和事件卡记的 %s 不是同一天，出处签只写媒体名、不写日期" % (where, str(pd)[:10], str(src.get("date"))[:10])
            date = None
        b["_src"] = {"name": name, "date": date, "url": src["url"], "full": full, "zh": zh or None, "ev": f["ev"], "warn": warn}
    return bad


def source_warnings(sb):
    """check_sources 记下的提醒（网页日期和事件卡对不上等）；video3_build.prepare 打印。没有原文截图／摘录的分镜返回 []。"""
    return [o["_src"]["warn"] for _c, _b, o, _s, _i, _w in shot_owners(sb) if isinstance(o.get("_src"), dict) and o["_src"].get("warn")]


def shot_budget(sb):
    """一期原文截图／摘录（含结合式）超过 SHOT_MAX 处只提醒（看多了就不新鲜；写稿草案建议 2–3 处）。"""
    n = len(shot_owners(sb))
    return ["这一期用了 %d 处原文截图／摘录：建议最多 %d 处，挑旁白正好讲到原话的那几句" % (n, SHOT_MAX)] if n > SHOT_MAX else []


def count_problems(sb):
    """"count": true（数字从 0 滚到终值）：只在 quote_card、num_chain 上起作用；写成别的值、或字里没有数字的提醒。"""
    warn = []
    for c in sb.get("chapters") or []:
        for b in c.get("blocks") or []:
            if not isinstance(b, dict) or "count" not in b or b.get("type") == "tally":
                continue
            where = "「%s」%s/%s" % (c.get("id"), b.get("type"), b.get("id"))
            if b.get("type") not in COUNT_BLOCKS:
                warn.append("%s 写了 count：数字滚动只在 quote_card、num_chain 上起作用，这里不滚" % where)
            elif b["count"] is not True and b["count"] is not False:
                warn.append("%s 的 count 要写 true 或 false（现在 %r），这次不滚" % (where, b["count"]))
            elif b["count"] is True:
                labs = [b.get("text")] if b["type"] == "quote_card" else [it.get("label") for it in b.get("items") or [] if isinstance(it, dict)]
                if not any(re.search(r"\d", str((x or {}).get("zh") or "")) for x in labs if isinstance(x, dict)):
                    warn.append("%s 写了 count: true，但字里没有数字，没有可滚的" % where)
    return warn


# ---------------------------------------------------------------- 计数模板 tally（2026-11-06 加）：美国轮廓＋“N 个州”＋M 格方阵
# 州界在 site/v3/us_states.json（us-atlas 3.0.1 的 states-albers-10m.json 转来，来源和许可写在文件里，也记在 README_video3.md）。
# 只有分镜写了 states、而且每个州名都能在 states_ref 指到的事件卡原文里逐字找到，才点亮具体的州；核不上就停（和数字核不上一样）。
# 没写 states：只画轮廓，不落到任何一个州。不用党派颜色（播放器里点亮用字色，例外用灰）。
US_STATES = Path(__file__).resolve().parents[1] / "v3" / "us_states.json"
TALLY_MAX = 120          # 方阵最多几格（再多格子太小）
_US = {}


def us_states():
    """州界数据（读一次）。读不到返回 None：播放器退成只有计数（大字＋方阵），不画轮廓。"""
    if "d" not in _US:
        try:
            _US["d"] = json.loads(US_STATES.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _US["d"] = None
    return _US["d"]


def _state_names():
    """[(写法, FIPS)]：中文名、英文名、别名都算一种写法。"""
    d = us_states() or {}
    out = []
    for fid, v in (d.get("states") or {}).items():
        for nm in [v.get("zh"), v.get("en")] + list(v.get("aka") or []):
            if nm:
                out.append((nm, fid))
    return out


def state_id(name):
    """州名 → FIPS（中文写法逐字比，英文不分大小写）；认不出返回 None。"""
    n = str(name or "").strip()
    for nm, fid in _state_names():
        if n == nm or (n.isascii() and n.lower() == nm.lower()):
            return fid
    return None


def state_in_text(name, text):
    """州名能不能在原文里逐字找到：先把包含它的更长的州名（West Virginia、西弗吉尼亚）遮掉，英文按整词、不分大小写。"""
    n = str(name or "").strip()
    if not n:
        return False
    t = str(text or "")
    for nm, _ in sorted(_state_names(), key=lambda x: -len(x[0])):
        if len(nm) > len(n) and (n in nm or (n.isascii() and n.lower() in nm.lower())):
            t = re.sub(re.escape(nm), " ", t, flags=re.I)
    if n.isascii():
        return re.search(r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])", t, flags=re.I) is not None
    return n in t


def tally_problem(b):
    """数据不够画的计数模板：返回原因（structure 据此去掉它并提醒）；能画返回 None。"""
    cnt = b.get("count") if isinstance(b.get("count"), dict) else {}
    v = cnt.get("value")
    if not (isinstance(v, (int, float)) and not isinstance(v, bool) and float(v).is_integer() and 1 <= v <= TALLY_MAX):
        return "count.value 要写 1–%d 的整数（方阵几格），现在是 %s" % (TALLY_MAX, _show(v))
    ex = b.get("except")
    if ex is not None:
        e = ex.get("value") if isinstance(ex, dict) else None
        if not (isinstance(e, (int, float)) and not isinstance(e, bool) and float(e).is_integer() and 0 <= e < v):
            return "except.value 要写 0 到 count.value−1 之间的整数（灰掉几格），现在是 %s" % _show(e)
    st = b.get("states")
    if st is not None and not (isinstance(st, list) and all(isinstance(x, str) and x.strip() for x in st)):
        return "states 要写州名的列表（写法照事件卡原文）"
    return None


def check_tally(sb, facts):
    """计数模板点亮的州：每个州名要认得，而且要在 states_ref 指到的事件卡原文里逐字找到。返回要改的列表（check_labels 一起停）。"""
    bad = []
    for c in sb.get("chapters") or []:
        for b in c.get("blocks") or []:
            if not isinstance(b, dict) or b.get("type") != "tally" or not b.get("states"):
                continue
            where = "「%s」tally/%s" % (c.get("id"), b.get("id"))
            refs = b.get("states_ref")
            refs = [refs] if isinstance(refs, str) else list(refs or [])
            miss = [r for r in refs if r not in facts]
            if not refs or miss:
                bad.append("%s 写了要点亮的州，%s：点亮的州必须是事件卡原文点了名的（states_ref 指到 facts）" % (
                    where, "states_ref 引用了 facts 里没有的键 " + "、".join(miss) if miss else "却没写 states_ref"))
                continue
            # 点亮的州要和画面上的计数出自同一处原文：states_ref 要在 region 或 count.label 的 ref 里（11-06：E003 点名的佐治亚、俄亥俄
            # 是 OpenAI 数据中心项目所在地，不是 41 项投票措施所在地；只核"卡里有这个名字"拦不住这种张冠李戴）
            own = set()
            for lab in (b.get("region"), (b.get("count") or {}).get("label") if isinstance(b.get("count"), dict) else None):
                r0 = lab.get("ref") if isinstance(lab, dict) else None
                own |= set([r0] if isinstance(r0, str) else (r0 or []))
            off = [r for r in refs if r not in own]
            if off:
                bad.append("%s 的 states_ref（%s）不在 region 或 count.label 的 ref 里：点亮的州要和画面上的计数出自同一处原文，"
                           "卡里别处点名的州（比如公司项目所在地）不能亮在这张计数上" % (where, "、".join(off)))
                continue
            pool = " ".join(facts[r]["text"] for r in refs)
            if us_states() is None:
                bad.append("%s：州界数据 %s 读不了，点不了州" % (where, US_STATES))
                continue
            for nm in b["states"]:
                if not state_id(nm):
                    bad.append("%s 的州名「%s」不认得（写法见 site/v3/us_states.json 的 zh、en、aka）" % (where, nm))
                elif not state_in_text(nm, pool):
                    bad.append("%s 的州名「%s」在它引用的事件卡原文（%s）里找不到：只能点亮事件卡点了名的州；"
                               "卡里没点名就别写 states，只画轮廓和计数" % (where, nm, "、".join(refs)))
    return bad


def tally_geo(b):
    """编播放器数据时给计数模板附上要画的几何：本土轮廓、州界细线、点亮的州（只附用得到的，数据小）。"""
    d = us_states()
    if not d:
        return None
    lit, inset = [], False
    for nm in b.get("states") or []:
        fid = state_id(nm)
        v = (d.get("states") or {}).get(fid) if fid else None
        if v:
            lit.append({"d": v["d"], "n": {"zh": v.get("zh"), "en": v.get("en")}})
            inset = inset or fid in ("02", "15")
    geo = {"vb": d["full"] if inset else d["viewBox"], "outline": d["outline"], "borders": d.get("borders") or "", "lit": lit}
    if inset:       # 点到阿拉斯加、夏威夷：整幅画（两块插图也描出来）
        geo["outline"] += "".join((d["states"].get(f) or {}).get("d", "") for f in ("02", "15"))
    return geo


# ---------------------------------------------------------------- 标志小签、帖子卡
def logo_slots(b):
    """这个模板上挂标志的位置：[(触发词里的位置名, 挂在哪个 dict 上, 字段名, 额外的上下文)]。"""
    out = []
    for spec in LOGO_SLOTS.get(b.get("type"), []):
        if spec == "head_logos" and b.get("head_logos"):
            out.append(("hl", b, "head_logos", None))
        elif spec == "logos" and b.get("logos"):
            out.append(("lg", b, "logos", None))
        elif spec.endswith("[].logos"):
            f = spec.split("[")[0]
            for i, it in enumerate(b.get(f) or []):
                if isinstance(it, dict) and it.get("logos"):
                    out.append(("%s%d.lg" % (f, i), it, "logos", None))
        elif spec in ("left.logos", "right.logos"):
            side = spec.split(".")[0]
            if isinstance(b.get(side), dict) and b[side].get("logos"):
                out.append(("%s.lg" % side, b[side], "logos", b.get(side + "_items")))
        elif spec == "who.logo" and isinstance(b.get("who"), dict) and b["who"].get("logo"):
            out.append(("who", b["who"], "logo", b))
    return out


def owner_text(owner, facts, extra=None):
    """一张卡上的字（中英文）＋它引用的事件卡原文：核"这个公司有没有出现在这张卡上"用。"""
    labels = []
    walk_labels(owner, "x", labels)
    if extra is not None:
        walk_labels(extra, "x", labels)
    txts, refs = [], set()
    for _, lab, r in labels:
        txts += [str(lab.get("zh") or ""), str(lab.get("en") or "")]
        refs |= set([r] if isinstance(r, str) else (r or []))
    for r in owner.get("ref") or [] if isinstance(owner.get("ref"), list) else []:
        refs.add(r)
    txts += [facts[r]["text"] for r in refs if r in facts]
    return " ".join(txts)


def _logo_lib():
    import video3_logos as LG       # 同目录：site/tools/video3_logos.py
    return LG, LG.load()


def check_logos(sb, facts):
    """标志小签：键要在标志库里（Simple Icons 有的自动取来），公司名要出现在这张卡上；不合格的不挂（提醒）。返回提醒。"""
    warn = []
    try:
        LG, lib = _logo_lib()
    except Exception as e:  # noqa: BLE001
        lib, LG = {"logos": {}}, None
        warn.append("标志库读不了（%s），这一期不挂标志" % e)
    for c in sb["chapters"]:
        for b in c.get("blocks") or []:
            for slot, owner, field, extra in logo_slots(b):
                refs = owner[field] if field != "logo" else [owner[field]]
                keep = []
                for r in refs if isinstance(refs, list) else [refs]:
                    key = r if isinstance(r, str) else (r.get("key") if isinstance(r, dict) else None)
                    if not key:
                        warn.append("「%s」%s 的标志写法不对：%r" % (c["id"], b["id"], r))
                        continue
                    v = lib["logos"].get(key)
                    if not v and LG:          # 库里没有：Simple Icons 有同名的就取来（只取用得到的，取过的留在库里）
                        try:
                            _, _, icons = LG.si_data()
                            ic = icons.get(key)
                            if ic:
                                aka = list((ic.get("aliases") or {}).get("aka") or [])
                                LG.add_si(key, key, {"zh": ic["title"], "en": ic["title"], "aliases": aka}, "symbol")
                                LG.measure([key])
                                lib = LG.load()
                                v = lib["logos"].get(key)
                        except Exception as e:  # noqa: BLE001
                            warn.append("取 Simple Icons 的 %s 没成功（%s）" % (key, e))
                    if not v:
                        warn.append("「%s」%s：标志库里没有 %s（用 site/tools/video3_logos.py 加进来），这次不挂" % (c["id"], b["id"], key))
                        continue
                    if not LG.mentioned(v, owner_text(owner if field != "logo" else extra, facts, extra if field != "logo" else None)):
                        warn.append("「%s」%s：%s（%s）没出现在这张卡的字或引用的原文里，不挂" % (c["id"], b["id"], key, "／".join(LG.names_of(v))))
                        continue
                    keep.append(r)
                if field == "logo":
                    if keep:
                        owner[field] = keep[0] if isinstance(keep[0], str) else keep[0]["key"]
                    else:
                        owner.pop(field)
                elif keep:
                    owner[field] = keep
                else:
                    owner.pop(field)
    return warn


def used_logos(sb):
    keys = []
    for c in sb["chapters"]:
        for b in c.get("blocks") or []:
            for _, owner, field, _ in logo_slots(b):
                for r in (owner[field] if field != "logo" else [owner[field]]):
                    k = r if isinstance(r, str) else r.get("key")
                    if k and k not in keys:
                        keys.append(k)
            if b["type"] == "post_card":
                pk = (b.get("platform") or {}).get("kind")
                if pk in ("x", "threads", "youtube") and pk not in keys:
                    keys.append(pk)        # 平台图标：库里有就用标志，没有就用通用小图标
    return keys


def _qnorm(s):
    return re.sub(r"[\s“”\"'‘’「」『』《》（）()…·.,，。、:：;；!！?？—–-]", "", str(s or "")).lower()


def check_posts(sb, facts):
    """post_card：原话要能在引用的事件卡原文里找到（找不到就停）；平台、日期核不上就只标"原话"、不写日期（提醒）。"""
    warn, bad = [], []
    for c in sb["chapters"]:
        for b in c.get("blocks") or []:
            if b["type"] != "post_card":
                continue
            where = "%s.%s" % (c["id"], b["id"])
            text = b.get("text") or {}
            refs = [r for r in (text.get("ref") or []) if r in facts]
            pool = " ".join(facts[r]["text"] for r in refs)
            if not refs or _qnorm(text.get("zh")) not in _qnorm(pool):
                bad.append("%s：原话「%s」在它引用的事件卡原文里找不到（%s）" % (where, text.get("zh"), "、".join(text.get("ref") or []) or "没写 ref"))
            elif text.get("en") and _qnorm(text["en"]) not in _qnorm(pool):
                b["en_para"] = True      # 英文不是逐字原话（比如事件卡里只有中文引语）：英文页面不加引号，按转述显示
                warn.append("%s：英文那句不是事件卡里的逐字原话，英文页面按转述显示（不加引号）" % where)
            pf = b.get("platform") or {}
            ok = False
            if pf.get("kind") in PLATFORMS and isinstance(pf.get("name"), dict):
                prefs = [r for r in (pf["name"].get("ref") or []) if r in facts]
                ppool = " ".join(facts[r]["text"] for r in prefs).lower()
                kind_ok = any(w in ppool for w in PLATFORMS[pf["kind"]])
                generic = [w for ws in PLATFORMS.values() for w in ws] + ["节目", "频道", "官方", "账号", "的"]
                core = pf["name"].get("zh") or pf["name"].get("en") or ""
                for w in sorted(generic, key=len, reverse=True):
                    core = re.sub(re.escape(w), " ", core, flags=re.I)
                toks = [t for t in re.split(r"[\s·/]+", core) if len(t) >= 2]
                ok = bool(prefs) and kind_ok and (not toks or any(t.lower() in ppool for t in toks))
            if not ok:
                if pf:
                    warn.append("%s：平台（%s）在事件卡原文里核不上，卡上只标“原话”" % (where, (pf.get("name") or {}).get("zh") or pf.get("kind")))
                b["platform"] = {"kind": "quote"}
            dt = b.get("date")
            if isinstance(dt, dict) and not [r for r in (dt.get("ref") or []) if r in facts]:
                warn.append("%s：日期没写 ref，卡上不写日期" % where)
                b.pop("date")
    if bad:
        raise SystemExit("核对失败（帖子卡的原话只能来自事件卡）：\n  " + "\n  ".join(bad))
    return warn


# ---------------------------------------------------------------- 旁白、触发词
def narration_md(sb):
    """分镜里的旁白 → 配音用的 Markdown（每章一个 ## 章名；配音、读音表检查、旁白检查都读它）。"""
    head = ["# 视频旁白 v3 · %s（今日地图）" % sb.get("date", ""), "",
            "> 由 site/tools/video3_build.py 从 04_文稿/视频v3_分镜.json 生成，请改分镜里的 narration，不要直接改这里。",
            "> 写法见 pipeline/prompts/写稿_视频v3.md；数字写阿拉伯数字，配音前自动转念法。", ""]
    body = []
    for c in sb["chapters"]:
        body += ["## " + c["title"], "", c["narration"].strip(), ""]
    return "\n".join(head + body)


def _spec(x):
    if x is None:
        return None
    if isinstance(x, str):
        return {"say": x, "offset": 0.0}
    if isinstance(x, dict) and x.get("say"):
        return {"say": x["say"], "offset": float(x.get("offset") or 0.0)}
    return None


def cue_list(sb):
    """所有触发词：[(键, 章序号, {"say", "offset"})]。键：open.map、<章>.map、<章>.<模板>.<名>、close.map、close.l1…"""
    out = []
    chs = sb["chapters"]
    ci = {c["id"]: i for i, c in enumerate(chs)}
    for c in chs:
        i = ci[c["id"]]
        for name, v in (c.get("cues") or {}).items():
            s = _spec(v)
            if s:
                out.append(("%s.%s" % ("open" if c["kind"] == "open" else ("close" if c["kind"] == "close" else c["id"]), name), i, s))
        if c["kind"] == "story":
            out.append(("%s.map" % c["id"], 0, _spec(c["map_cue"])))
        if c["kind"] == "close":
            for k, ln in enumerate((c.get("end") or {}).get("lines") or []):
                s = _spec(ln.get("cue"))
                if s:
                    out.append(("close.l%d" % (k + 1), i, s))
        for b in c.get("blocks") or []:
            pre = "%s.%s." % (c["id"], b["id"])
            for name, v in (b.get("cues") or {}).items():
                s = _spec(v)
                if s:
                    out.append((pre + name, i, s))
            tp = TEMPLATES[b["type"]]
            for field, key in (tp.get("list_cues") or {}).items():
                for k, it in enumerate(b.get(field) or []):
                    s = _spec(it if key is None else (it.get(key) if isinstance(it, dict) else None))
                    if s:
                        out.append(("%s%s%d" % (pre, field, k), i, s))
            if b["type"] == "timeline" and isinstance(b.get("wait"), dict) and _spec(b["wait"].get("at")):
                out.append((pre + "wait", i, _spec(b["wait"]["at"])))
            # 结合式（11-06 深夜）：shot 里的 cues.mark（荧光笔开始扫）：原话卡记成 <块>.shot_mark，时间轴日子记成 <块>.ticks<k>_mark
            if b["type"] in CARD_SHOT and isinstance(b.get("shot"), dict):
                s = _spec((b["shot"].get("cues") or {}).get("mark"))
                if s:
                    out.append((pre + "shot_mark", i, s))
            if b["type"] == "timeline":
                for k, tk in enumerate(b.get("ticks") or []):
                    s = _spec(((tk.get("shot") or {}).get("cues") or {}).get("mark")) if isinstance(tk, dict) and isinstance(tk.get("shot"), dict) else None
                    if s:
                        out.append(("%sticks%d_mark" % (pre, k), i, s))
            for slot, owner, field, _ in logo_slots(b):      # 标志小签：各自的触发词（说到这家公司时出现）
                if field == "logo":
                    continue
                for j, r in enumerate(owner[field]):
                    s = _spec(r.get("cue")) if isinstance(r, dict) else None
                    if s:
                        out.append(("%s%s%d" % (pre, slot, j), i, s))
    return out


def estimate_duration(sb, est_fn, plan_fn, factor=1.0):
    """按字数估成片秒数（配音前用，video3_build.check_length 调）：每章旁白估计的人声秒数（est_fn 按念法估）× factor，
    交给配乐的排法 plan_fn（video3_music.plan：片头 6 拍、章与章之间等到下一条小节线、片尾收束拍落在末字之后）得出总长。
    上限 3 分钟：写稿_视频v3.md 文末"程序检查"的 时长上限秒 / 时长提醒秒。"""
    lens = [est_fn(c.get("narration") or "") * factor for c in sb["chapters"]]
    return float(plan_fn(lens)["duration"])


def check_cues(sb, norm):
    """每个触发词都要能在它那一章的旁白里找到（按对齐时的规则：只看字、字母、数字）。"""
    bad = []
    chs = sb["chapters"]
    for key, i, s in cue_list(sb):
        if s["say"].startswith("@"):
            continue
        if norm(s["say"]) not in norm(chs[i]["narration"]):
            bad.append("%s：「%s」在「%s」章的旁白里找不到" % (key, s["say"], chs[i]["title"]))
    if bad:
        raise SystemExit("触发词对不上旁白（画面没法跟着旁白走）：\n  " + "\n  ".join(bad))


# ---------------------------------------------------------------- 画面里有没有东西（2026-11-06 改准，并前移到总调度第 7 步）
# 11-06 那期 118.7 秒人声里约 21 秒画面基本是空的：原来的检查把关系模板从它开始一直算到下一个模板（只剩线和点的时间轨、
# 三根空玻璃柱都算"有东西"），只看每个模板的开头（认不出"时间线 → 对比卡 → 再回到时间线"这种穿插），而且只在配完音以后跑。
# 现在按"画面上真有东西"的那几段算：
#   · 配图（背景窗、帖子卡／要点卡题图、小卡上的图、时间轨日子上的小图）、标志小签、计数模板的美国轮廓：从出现到这个模板下场；
#   · 关系模板的动效只算每个触发词之后 SCREEN_HOLD 秒（柱子长出、条伸出、标记落档、包裹一站站走那几秒），之后的静止不算；
#   · 只剩线和点的时间轨（日子没挂标志、小图）、空玻璃柱、白卡上一两行字（对比卡的大数字、要点卡、没有题图和标志的帖子卡、"接下来"）不算；
#   · "这一刻画面上是哪一个模板"按触发词的实际先后排：最近一个说到的触发词属于谁，镜头就在谁那里，所以能认出穿插。
# 第 7 步还没配音，用 estimate_timing 按字数估时间（和 video3_preview 同一套估法，误差一两秒）；第 14 步配完音按实际对齐再查一遍。
# 都只提醒，不拦。
SCREEN_HOLD = 4.0        # 关系模板一个触发词之后算"有画面"的秒数
SCREEN_GAP = 4.0         # 单段空画面超过这么多秒就提醒
OPENER_SEC = 3.0         # 每章开口这么多秒内要有主角（配图或标志）
HERO = ("img", "logo", "map")
_INF = float("inf")
MOTION_CUES = {          # 关系模板：哪些触发词之后的那几秒算"在动"（列表项写成 items*）
    "bar_shrink": ["head", "from", "to", "done", "half"], "twin_drop": ["items*", "same"], "column_compare": ["items*"],
    "scale": ["head", "from", "to"], "fork": ["a", "b"], "quota_bars": ["from", "to"], "compare_panel": ["bars*"],
    "phone_list": ["show", "rows*"], "split": ["left_items*", "right_items*"], "timeline": ["wait"],
    "num_chain": ["items*"], "source_excerpt": ["mark"],           # 动效尝试：数字递进一个个出、摘录上荧光笔扫过那几秒
}


def _block_times(c, b, T):
    pre = "%s.%s." % (c.get("id"), b.get("id"))
    return {k[len(pre):]: v for k, v in (T or {}).items()
            if k.startswith(pre) and not k.endswith(".end") and isinstance(v, (int, float))}


def fork_photo(c):
    """这一章有没有立在分岔路尽头的配图（有 fork，且有 image_card：播放器把第一张 image_card 立在两条路尽头的中间）。"""
    bl = [b for b in c.get("blocks") or [] if isinstance(b, dict)]
    return any(b.get("type") == "fork" for b in bl) and any(b.get("type") == "image_card" and b.get("image") for b in bl)


def _moments(b, ts, over_ok=False):
    """一个模板"画面上真有东西"的几段：[(起, 止, 种类)]，种类 img / logo / map / motion；止是无穷大的表示一直到这个模板下场。
    over_ok：这一章有立在路尽头的配图（fork_photo），写了 over_photo 的要点卡压在它上面，算有图（11-06 晚补）。"""
    t, out = b.get("type"), []
    first = min(ts.values()) if ts else None
    g = lambda k, d=None: ts.get(k, d)  # noqa: E731
    for name in MOTION_CUES.get(t, []):
        if t == "compare_panel" and len(b.get("bars") or []) < 2:
            break
        keys = [k for k in ts if re.fullmatch(re.escape(name[:-1]) + r"\d+", k)] if name.endswith("*") else [name]
        out += [(ts[k], ts[k] + SCREEN_HOLD, "motion") for k in keys if k in ts]
    if t == "chain" and ts:
        out.append((first, max(ts.values()) + SCREEN_HOLD, "motion"))
    if t == "particle_counter" and "count" in ts:
        out.append((ts["count"] - 0.6, ts["count"] + SCREEN_HOLD, "motion"))
    if t == "tally" and first is not None:
        out.append((g("show", first), _INF, "map"))
    if t in CARD_SHOT and isinstance(b.get("shot"), dict):     # 结合式：截图在图位（截图没成功时是摘录：只算荧光笔扫的那几秒）
        if b["shot"].get("_shot_fail"):
            out.append((g("shot_mark", g("show", first)), g("shot_mark", g("show", first)) + SCREEN_HOLD, "motion"))
        else:
            out.append((g("show", first), _INF, "img"))
    elif t in ("post_card", "quote_card") and b.get("image"):
        out.append((g("show", first), _INF, "img"))
    elif t == "source_shot" and first is not None:              # 动效尝试：原文截图从出现到下场都算
        out.append((g("show", first), _INF, "img"))
    elif t == "quote_card" and b.get("over_photo") and over_ok:
        out.append((g("show", first), _INF, "img"))
    if t in PHOTO_BLOCKS and b.get("photo") and first is not None:    # 11-07：压在配图上，配图从出现到这一块下场都算
        out.append((g("photo", first), _INF, "img"))
    for f in ("items", "ticks") + SPLIT_SIDES:
        for k, it in enumerate(b.get(f) or []):
            if isinstance(it, dict) and it.get("image") and t in ("tile_row", "timeline", "split"):
                out.append((g("%s%d" % (f, k), first), _INF, "img"))
            elif t == "timeline" and f == "ticks" and isinstance(it, dict) and isinstance(it.get("shot"), dict):   # 结合式：日子上的截图
                out.append((g("ticks%d" % k, first), _INF, "img"))
    for slot, owner, field, _ in logo_slots(b):        # 标志：自己的触发词，没有就跟着它挂的那一项出来
        base = {"hl": g("head", first), "lg": g("show", g("from", first)), "who": g("show", first),
                "left.lg": g("left", g("split", first)), "right.lg": g("right", g("split", first))}.get(slot)
        if base is None:
            base = g(slot.split(".")[0], first)
        lst = owner.get(field) if field != "logo" else [owner.get(field)]
        for j, _r in enumerate(lst if isinstance(lst, list) else [lst]):
            at = g("%s%d" % (slot, j)) if field != "logo" else None
            if at is not None or base is not None:
                out.append((at if at is not None else base, _INF, "logo"))
    return [(a, z, k) for a, z, k in out if a is not None]


def screen_model(sb, T, marks):
    """每个 story / contrast 章：画面上真有东西的几段、空档、第一次出现主角（配图或标志）的时刻、时间轨被打断的地方。"""
    out = []
    for i, c in enumerate(sb.get("chapters") or []):
        if c.get("kind") not in ("story", "contrast") or i >= len(marks or []):
            continue
        m = marks[i]
        v0, v1, cend = m["voice_start"], m["voice_end"], m["end"]
        c0 = marks[i - 1]["end"] if i else 0.0
        blocks = [b for b in c.get("blocks") or [] if isinstance(b, dict)]
        tms = [_block_times(c, b, T) for b in blocks]
        starts = [min(ts.values()) if ts else None for ts in tms]
        # 镜头这一刻在哪个模板：最近一个说到的触发词属于谁（背景配图不抢镜头）
        ev = sorted((v, j) for j, (b, ts) in enumerate(zip(blocks, tms)) if b.get("type") != "image_card" for v in ts.values())
        own = {}
        for k, (v, j) in enumerate(ev):
            a = min(c0, v) if k == 0 else v
            z = ev[k + 1][0] if k + 1 < len(ev) else cend
            if z > a:
                own.setdefault(j, []).append((a, z))
        pieces = []
        for j, (b, ts) in enumerate(zip(blocks, tms)):
            if b.get("type") == "image_card":
                tin = ts.get("in", v0)
                nxt = min([x for jj, x in enumerate(starts) if x is not None and x > tin + 1e-6 and blocks[jj].get("type") != "image_card"]
                          or [cend])
                pieces.append((tin, nxt, "img", b))
                continue
            for a, z, kind in _moments(b, ts, over_ok=fork_photo(c)):
                for oa, oz in own.get(j, []):
                    lo, hi = max(a, oa), min(z, oz)
                    if hi > lo + 1e-6:
                        pieces.append((lo, hi, kind, b))
        pieces.sort(key=lambda x: x[0])
        gaps, cur = [], v0
        for a, z, _k, _b in pieces:
            if a > cur:
                gaps.append((cur, a))
            cur = max(cur, z)
        if cur < v1:
            gaps.append((cur, v1))
        gaps = [(a, min(z, v1)) for a, z in gaps if min(z, v1) > a]
        heroes = [a for a, z, k, _b in pieces if k in HERO and z > v0]
        hero = max(v0, min(heroes)) if heroes else None
        # 时间轨被别的模板从中间打断：它的日子有的说在别的模板开始之后（贴在尽头的手机也算，和播放器 tlSegments 一样）
        cuts = []
        for j, (b, ts) in enumerate(zip(blocks, tms)):
            if b.get("type") != "timeline":
                continue
            tk = sorted(v for k, v in ts.items() if re.fullmatch(r"ticks\d+", k))
            if len(tk) < 2:
                continue
            for jj, b2 in enumerate(blocks):
                if jj == j or starts[jj] is None or b2.get("type") == "image_card":
                    continue
                if tk[0] < starts[jj] < tk[-1] - 0.05:
                    later = [k for k, v in sorted(ts.items(), key=lambda x: x[1]) if re.fullmatch(r"ticks\d+", k) and v > starts[jj]]
                    cuts.append({"tl": b, "by": b2, "at": starts[jj], "later": later})
        # 11-09：引语卡孤零零占着画面——镜头在这张 quote_card 上的时候，既没有配图（自己的 image、over_photo、截图、背景配图），
        #   也没有在动的模板；只挂了标志也算孤零零。连续超过 SCREEN_GAP 秒就提醒（和空画面一样只提醒）
        cover = sorted((a, z) for a, z, k, _b in pieces if k in ("img", "motion"))
        lonely = []
        for j, b in enumerate(blocks):
            if b.get("type") != "quote_card":
                continue
            for oa, oz in own.get(j, []):
                cur, lo, hi = max(oa, v0), max(oa, v0), min(oz, v1)
                for a, z in cover:
                    if z <= cur or a >= hi:
                        continue
                    if a > cur:
                        lonely.append((cur, a, b))
                    cur = max(cur, z)
                if hi > cur:
                    lonely.append((cur, hi, b))
        out.append({"c": c, "i": i, "v0": v0, "v1": v1, "pieces": pieces, "gaps": gaps, "hero": hero, "cuts": cuts,
                    "lonely": [(a, z, b) for a, z, b in lonely if z > a]})
    return out


def _tick_label(b, key):
    k = int(key[5:])
    t = (b.get("ticks") or [])[k] if k < len(b.get("ticks") or []) else {}
    return "“%s”" % _tick_name(t) if isinstance(t, dict) and _tick_name(t) else key


def screen_warnings(sb, T, marks, est=False, limit=SCREEN_GAP):
    """空档、章首主角、时间轨被打断的提醒（都只提醒）。est：时间是按字数估的。"""
    warn, tag = [], "（时间按字数估，误差一两秒）" if est else ""
    for ch in screen_model(sb, T, marks):
        c, v0 = ch["c"], ch["v0"]
        for a, z in ch["gaps"]:
            if z - a > limit:
                warn.append("「%s」%.1f–%.1f 秒（%.1f 秒）画面上没有真东西（只剩线和点的时间轨、空玻璃柱、白卡上一两行字不算；"
                            "建议不超过 %g 秒）：给这一段挂配图或标志（时间轨日子可挂 logos、image，要点卡可带 image），"
                            "或把下一个模板的触发词提前%s" % (c["id"], a, z, z - a, limit, tag))
        for a, z, b in ch.get("lonely") or []:
            if z - a > limit and not any(ga < z and gz > a and gz - ga > limit for ga, gz in ch["gaps"]):     # 已经报了空画面的不重复报
                warn.append("「%s」quote_card/%s 只有一张引语卡 %.1f–%.1f 秒（%.1f 秒）：引语卡不能孤零零占着画面（只挂标志也算），"
                            "压在配图上（image、over_photo、原文截图），或配一个会动的现成模板（如 num_chain 数字递进）%s" % (
                                c["id"], b.get("id") or "?", a, z, z - a, tag))
        if ch["hero"] is None or ch["hero"] > v0 + OPENER_SEC:
            when = "整章都没有" if ch["hero"] is None else "第一个在 %.1f 秒（开口后 %.1f 秒）" % (ch["hero"], ch["hero"] - v0)
            warn.append("「%s」开口 %g 秒内没有主角（配图或标志）：%s。给第一个模板挂上主角的标志（时间轨日子、柱子、要点卡都能挂），"
                        "或先放带题图的卡片、计数模板%s" % (c["id"], OPENER_SEC, when, tag))
        for x in ch["cuts"]:
            warn.append("「%s」timeline/%s 被 %s/%s 从中间打断（%.1f 秒开始，之后还有 %s）：镜头要飞回时间轨、日子标签要重新出；"
                        "能挪就把 %s 挪到时间轨说完之后，或把后面的日子并进下一个模板%s" % (
                            c["id"], x["tl"].get("id"), x["by"].get("type"), x["by"].get("id"), x["at"],
                            "、".join(_tick_label(x["tl"], k) for k in x["later"]), x["by"].get("type"), tag))
    return warn


def check_gaps(sb, T, marks, limit=SCREEN_GAP):
    """对齐以后（第 14 步、无声样片）：按实际时间再查一遍空档、章首主角、时间轨被打断（都只提醒）。"""
    return screen_warnings(sb, T, marks, est=False, limit=limit)


def blank_spans(sb, T, marks, limit=SCREEN_GAP):
    """给关键帧总览用：每章的空档（超过 limit 秒的）和章首迟迟没有主角的那一段 → {章 id: [[起, 止, 原因], …]}。"""
    out = {}
    for ch in screen_model(sb, T, marks):
        lst = [[round(a, 2), round(z, 2), "gap"] for a, z in ch["gaps"] if z - a > limit]
        if ch["hero"] is None or ch["hero"] > ch["v0"] + OPENER_SEC:
            z = ch["hero"] if ch["hero"] is not None else ch["v1"]
            if not any(a <= ch["v0"] + 0.5 for a, _z, _w in lst):
                lst.insert(0, [round(ch["v0"], 2), round(z, 2), "opener"])
        if lst:
            out[ch["c"]["id"]] = lst
    return out


def estimate_timing(sb, factor=None):
    """配音前按字数估每个触发词的秒数（和 video3_preview 同一套：tts.est_seconds × EST_FACTOR，按配乐的排法排章，章内按字均分）。
    返回 (T, marks)；估不出来（缺旁白、缺模块、触发词对不上）返回 (None, None)。"""
    try:
        import tts                                   # pipeline/（总调度、组装脚本都已加进 sys.path）
        from spoken_numbers import spoken
        import video3_music as MUS
        import video_align as VA
    except Exception:  # noqa: BLE001
        return None, None
    chs = sb.get("chapters") or []
    texts = [(c.get("narration") or "").strip() for c in chs]
    if not chs or not all(texts):
        return None, None
    if factor is None:
        import sys
        factor = getattr(sys.modules.get("video3_build"), "EST_FACTOR", 0.95)
    try:
        pl = MUS.plan([tts.est_seconds(spoken(t)[0]) * factor for t in texts])
    except Exception:  # noqa: BLE001
        return None, None
    dur = float(pl["duration"])
    marks = [{"chapter": c.get("id"), "voice_start": pl["voice_starts"][i], "voice_end": pl["voice_ends"][i],
              "end": pl["bounds"][i] if i < len(pl["bounds"]) else round(dur, 3)} for i, c in enumerate(chs)]
    flats = []
    for i, t in enumerate(texts):
        u = [ch.lower() for ch in t if VA.is_unit(ch)]
        flats.append(("".join(u), marks[i]["voice_start"], (marks[i]["voice_end"] - marks[i]["voice_start"]) / max(1, len(u))))
    T = {}
    try:
        cues = cue_list(sb)
    except Exception:  # noqa: BLE001
        return None, None
    for key, i, spec in cues:
        say_, off = spec["say"], spec["offset"]
        if say_ in ("@end", "@start"):
            v = marks[i]["end"] if say_ == "@end" else (0.0 if i == 0 else marks[i - 1]["end"])
            T[key] = round(v + off, 3)
            continue
        flat, v0, step = flats[i]
        k = flat.find(VA.norm(say_))
        if k < 0:
            continue
        T[key] = round(v0 + k * step + off, 3)
    T["open.go"] = marks[0]["end"]
    return T, marks


# ---------------------------------------------------------------- 旁白里的数字、等级有没有上画面（2026-11-06 加，只提醒）
# 11-06：“3200 万美元”“从 High 升到 Critical”旁白说了，画面上没有。写稿规则早就要求"数字、日期、名字由画面打出来"，现在查。
LEVEL_RE = re.compile(r"(?<![A-Za-z])(?:Low|Medium|High|Critical|Severe|Moderate|Elevated|Extreme|Minimal)(?![A-Za-z])"
                      r"|(?<![A-Za-z0-9])(?:AAA|AA[+-]?|A[+-]|BBB[+-]?|BB[+-]?|B[+-]|CCC[+-]?|Aaa|Aa[1-3]|Baa[1-3]|Ba[1-3]|Caa[1-3]|L[0-5])(?![A-Za-z0-9])"
                      r"|[一二三四五六七八九十]级")


def screen_text(c):
    """这一章模板上的字（中英文都算；原文截图／摘录上荧光笔扫的那句和中文行也算）。"""
    labels = []
    for b in c.get("blocks") or []:
        if isinstance(b, dict):
            walk_labels(b, "x", labels)
    extra = [str(o.get(k) or "") for _c, _b, o, _s, _i, _w in shot_owners({"chapters": [c]})       # 含结合式的 shot
             for k in ("quote", "zh") if isinstance(o.get(k), str)]
    return " ".join([str(lab.get(k) or "") for _p, lab, _r in labels for k in ("zh", "en") if not lab.get("_num")] + extra)


def check_spoken_facts(sb):
    """story / contrast 章旁白里的数字、等级，这一章画面上的字里找不到的 → 提醒。"""
    warn = []
    for c in sb.get("chapters") or []:
        if c.get("kind") not in ("story", "contrast"):
            continue
        narr = c.get("narration") or ""
        for tok in sorted(NAME_TOKENS, key=len, reverse=True):
            narr = re.sub(r"(?<![A-Za-z0-9])" + re.escape(tok) + r"(?![A-Za-z0-9])", " ", narr, flags=re.I)
        scr = screen_text(c).replace(",", "")
        miss, seen = [], set()
        for m in list(NUM_RE.finditer(narr)) + list(LEVEL_RE.finditer(narr)):
            tok = m.group(0).replace(",", "")
            if tok in seen:
                continue
            seen.add(tok)
            if tok[0].isdigit():
                found = re.search(r"(?<![\d.])" + re.escape(tok) + r"(?!\.?\d)", scr)
            else:
                found = re.search(r"(?<![A-Za-z0-9])" + re.escape(tok) + r"(?![A-Za-z0-9])", scr)
            if not found:          # 数字带上后面的单位（“3200 万美元”），等级只写它自己
                miss.append("“%s”" % (re.match(r"[^，。、；：！？,;:!?]{0,%d}" % (len(m.group(0)) + 4), narr[m.start():]).group(0).strip() if tok[0].isdigit() else tok))
        if miss:
            warn.append("「%s」旁白里说到的 %s 这一章画面上没出现：数字、等级要有一个模板把它打出来（数量用计数 tally、柱子或对比卡；"
                        "等级变化用 scale，只画事件卡里出现的档位，不暗示是最高档）" % (c["id"], "、".join(miss)))
    return warn


# ---------------------------------------------------------------- 一期配图几张（2026-11-06 加，只提醒）
# 11-08 晚：用户定配图张数按内容需要、不设上限（视频导演对比后），两个上限改成 None＝不按张数提醒；时间轴小图的上限（版式）照旧
VIDEO_IMG_MAX = None       # 原来 8：视频一期最多几张配图
VIDEO_IMG_NEW_MAX = None   # 原来 4：其中新画的（image_requests 里写 brief_en 的）最多几张


def image_names(sb):
    out = []
    for c in sb.get("chapters") or []:
        for b in c.get("blocks") or []:
            if not isinstance(b, dict):
                continue
            for it in [b] + [x for f in ("items", "ticks") + SPLIT_SIDES for x in b.get(f) or [] if isinstance(x, dict)]:
                if it.get("image"):
                    out.append(Path(str(it["image"])).stem)
            if b.get("type") in PHOTO_BLOCKS and b.get("photo"):
                out.append(Path(str(b["photo"])).stem)
    for lst in (sb.get("_pending_images") or {}).values():
        out += lst
    return list(dict.fromkeys(out))


def check_image_budget(sb):
    warn, used = [], image_names(sb)
    reqs = {r.get("id"): r for r in sb.get("image_requests") or [] if isinstance(r, dict)}
    new = [i for i in used if i in reqs and reqs[i].get("brief_en")]
    if (VIDEO_IMG_MAX is not None and len(used) > VIDEO_IMG_MAX) or (VIDEO_IMG_NEW_MAX is not None and len(new) > VIDEO_IMG_NEW_MAX):
        warn.append("这一期视频用了 %d 张配图，其中新画 %d 张（%s）：规矩是一期最多 %d 张、新画的不超过 %d 张，"
                    "优先复用网页已用过的图（06_配图 里的文件名直接写进 image）" % (
                        len(used), len(new), "、".join(new) or "无", VIDEO_IMG_MAX, VIDEO_IMG_NEW_MAX))
    for c in sb.get("chapters") or []:
        for b in c.get("blocks") or []:
            if isinstance(b, dict) and b.get("type") == "timeline":
                n = sum(1 for k in b.get("ticks") or [] if isinstance(k, dict) and k.get("image"))
                if n > TICK_IMAGE_MAX:
                    warn.append("「%s」timeline/%s 挂了 %d 张小图：一条时间轨最多 %d 张，多了互相挤" % (c["id"], b.get("id"), n, TICK_IMAGE_MAX))
    return warn


def check_text_cards(sb):
    """要点卡（quote_card）只有字：没写题图 image，没挂真标志（文字小签不算），也不是压在路尽头配图上的（over_photo）→ 提醒。
    11-06 晚补：那天"研发成本 3200 万美元""只读，不能动钱"两张卡只有字，画面空。只提醒。"""
    try:
        _LG, lib = _logo_lib()
        real = lambda k: bool(((lib.get("logos") or {}).get(k) or {}).get("file"))  # noqa: E731
    except Exception:  # noqa: BLE001
        real = lambda k: True  # noqa: E731
    warn = []
    for c in sb.get("chapters") or []:
        if c.get("kind") not in ("story", "contrast"):
            continue
        for b in c.get("blocks") or []:
            if not isinstance(b, dict) or b.get("type") != "quote_card" or b.get("image") or isinstance(b.get("shot"), dict):   # 结合式：带原文截图的不算
                continue
            if b.get("over_photo") and fork_photo(c):
                continue
            keys = [r if isinstance(r, str) else (r or {}).get("key") for r in b.get("logos") or []]
            if any(k and real(k) for k in keys):
                continue
            warn.append("「%s」要点卡 %s 只有字（“%s”）：没有题图，也没有标志（文字小签不算）。带一张题图 image（优先复用网页图、"
                        "同一章已露过脸的图）、挂上主角的标志，或跟在 fork 后面时写 \"over_photo\": true 压在路尽头的配图上"
                        % (c["id"], b.get("id"), txt(b.get("text")).get("zh", "")))
    return warn


NUM_CHAIN_PER_ISSUE = 1      # 一期最多几处数字递进（11-07 并入正式流程，草案第五节"每期上限"）
COUNT_PER_ISSUE = 2          # 一期最多几处数字滚动（"count": true）


def check_motion(sb):
    """11-07 并入正式流程的规矩（《写稿_视频v3.md》"看得见出处"一节和"画面要有真东西"末尾"11-07 补"），第 7 步只提醒、不拦：
      · 一章超过一处原文截图／摘录（含结合式）；一期超过 3 处由 shot_budget 提醒；
      · 数字递进超过 1 处、数字滚动超过 2 处（宁少勿多）；
      · 开场速览有一屏没图，或两屏用了同一张图；
      · 时间轴有日子既没挂小图、也没挂标志、也没带原文截图（只剩线和点）；
      · tile_row 有小卡只有名字（没有一句解读 sub、也没有图）；
      · compare_panel 没压在配图上（白底上的字和数）；
      · story 章没有一张自己的图（清楚露脸的图都是前面的章露过的，或者只在背景窗里；开场速览不算"露过"）。
    第 7 步时还没画的图（structure 暂时去掉、记在 _pending_items / _pending_images 里的）当作已经写了图。"""
    warn, chs = [], sb.get("chapters") or []
    per = {}
    for c, _b, _o, _s, _sid, where in shot_owners(sb):
        per.setdefault(c.get("id"), []).append(where)
    for cid, ws in per.items():
        if len(ws) > 1:
            warn.append("「%s」有 %d 处原文截图／摘录（%s）：一章最多一处，留旁白最想让人看见出处的那一句" % (cid, len(ws), "；".join(ws)))
    blocks = [(c, b) for c in chs for b in c.get("blocks") or [] if isinstance(b, dict)]
    nc = ["「%s」%s" % (c.get("id"), b.get("id")) for c, b in blocks if b.get("type") == "num_chain"]
    if len(nc) > NUM_CHAIN_PER_ISSUE:
        warn.append("这一期用了 %d 处数字递进 num_chain（%s）：一期最多 %d 处" % (len(nc), "、".join(nc), NUM_CHAIN_PER_ISSUE))
    cn = ["「%s」%s" % (c.get("id"), b.get("id")) for c, b in blocks if b.get("count") is True and b.get("type") in COUNT_BLOCKS]
    if len(cn) > COUNT_PER_ISSUE:
        warn.append("这一期用了 %d 处数字滚动 count（%s）：一期 1–2 处就够，只用在旁白特意停下来报的那个数上" % (len(cn), "、".join(cn)))
    later = set(sb.get("_pending_items") or [])            # 写了图、只是第 7 步时还没画（structure 暂时去掉的）：当作有图
    has_img = lambda it: bool(it.get("image")) or id(it) in later  # noqa: E731
    for c, b in blocks:
        t, where = b.get("type"), "「%s」%s/%s" % (c.get("id"), b.get("type"), b.get("id"))
        if t == "headline_open":
            imgs = [Path(str(it.get("image"))).stem if it.get("image") else ("…" if id(it) in later else None)
                    for it in b.get("items") or [] if isinstance(it, dict)]
            if None in imgs:
                warn.append("%s 有 %d 屏没写 image：速览每一屏是一整屏配图，没图就是空底" % (where, imgs.count(None)))
            dup = sorted({x for x in imgs if x and x != "…" and imgs.count(x) > 1})
            if dup:
                warn.append("%s 有几屏用了同一张图（%s）：每屏用不同的图，最好就是那一章露脸的那张" % (where, "、".join(dup)))
        elif t == "timeline":
            bare = [_tick_name(k) or str(i + 1) for i, k in enumerate(b.get("ticks") or [])
                    if isinstance(k, dict) and not (has_img(k) or k.get("logos") or isinstance(k.get("shot"), dict))]
            if bare:
                warn.append("%s 的日子 %s 没挂小图也没挂标志：只剩线和点不算真东西；说到哪家公司就挂它的 logos（库里没有的按 video3_logos.py "
                            "的顺序去取，取不到登记文字小签），说到一件事就挂那件事的小图 image（一条轴最多 3 张）" % (where, "、".join(bare)))
        elif t == "tile_row":
            thin = [txt(it.get("title")).get("zh", "") or str(i + 1) for i, it in enumerate(b.get("items") or [])
                    if isinstance(it, dict) and not it.get("sub") and not has_img(it)]
            if thin:
                warn.append("%s 的小卡 %s 只有名字：每块补一句事件卡里逐字有的解读（sub），画面空时整排写 photo 压在这一章的配图上"
                            % (where, "、".join(thin)))
        elif t == "compare_panel" and not b.get("photo"):
            warn.append("%s 是白底上的字和数：按“三句”判断画面空的话，写 photo 压在这一章的配图上，能比就画两根对比条（条尾写 val），"
                        "顶上挂出处签 src_tag" % where)
    # "自己的图"：按章的先后，这一章清楚露脸的图里至少有一张是前面的章没露过的（开场速览预告各章的图，不算）；
    # 写了、第 7 步时还没画的图也算这一章的
    seen = set()
    for c in chs:
        if c.get("kind") not in ("story", "contrast"):
            continue
        clear, _back = photo_moments(c)
        mine = {x for x in clear if not x.startswith("原文截图:")} | set((sb.get("_pending_images") or {}).get(c.get("id")) or [])
        if c.get("kind") == "story" and not (mine - seen):
            warn.append("「%s」没有一张自己的图%s：每个 story 章至少一张前面没露过脸的图、有一刻清楚露脸；网页图不够就在 image_requests 新画"
                        "（张数按内容需要，第 10 步先 agy 再 Codex）" % (
                            c.get("id"), "（%s 前面的章已经露过脸）" % "、".join(sorted(mine)) if mine else "（只有背景窗或一张都没有）"))
        seen |= mine
    return warn


def check_screen(sb):
    """第 7 步的画面检查（只提醒）：按字数估时间查空档、章首主角、时间轨被打断，再查旁白数字和等级上没上画面、一期配图张数、
    要点卡只有字（11-06 晚补）。"""
    warn = check_spoken_facts(sb) + check_image_budget(sb) + check_text_cards(sb)
    T, marks = estimate_timing(sb)
    if T is not None:
        warn = screen_warnings(sb, T, marks, est=True) + warn
    return warn


# ---------------------------------------------------------------- 编成播放器数据
def txt(v):
    return {k: v[k] for k in ("zh", "en") if isinstance(v, dict) and v.get(k)}


def strip_labels(x):
    """数据里的字只留 zh/en（ref 用完了）；cue 规格换成时间以后也去掉。
    11-06 白天补：at 有两种——时间轨日子的 at 是触发词（字或 {say, offset}），去掉；刻度尺 from/to 的 at 是档位序号（数字），
    要留着。原来一律去掉，播放器只好按默认（从第 0 档落到第 1 档）画：11-01 碰巧就是 0 → 1 没露馅，
    11-06 的 High → Critical（1 → 0）会被画成 Critical 降到 High。"""
    if is_label(x):
        return txt(x)
    if isinstance(x, dict):
        return {k: strip_labels(v) for k, v in x.items()
                if k not in ("cues", "ref", "check", "stages_ref", "cue", "at") or (k == "at" and isinstance(v, (int, float))
                                                                                   and not isinstance(v, bool))}
    if isinstance(x, list):
        return [strip_labels(v) for v in x]
    return x


VIDEO_OUT = "11_视频v3"        # 演示页目录（和 video3_build.OUT_DIR 一样）：新图位的配图压缩后放进它的 img/


def ensure_photo(sb, photos, key, name, size):
    """新图位（quote_card 题图、时间轨日子上的小图；11-06 加）的配图：video3_build.prep_photos 不认得这些位置，这里补上。
    同一张图已经按不小于这个尺寸备过（比如同一张图也做了帖子卡题图）就直接共用；否则照 prep_photos 的办法压成 webp 放进 img/。
    photos 就是写进播放器数据的 images（和 prep_photos 返回的是同一个字典），所以网页那边照样会拷这些文件。返回 key，备不了返回 None。"""
    if key in photos:
        return key
    issue = Path(sb["_issue"]) if sb.get("_issue") else None
    src = find_image(issue, name) if issue else None
    if not src:
        return None
    for ph in list(photos.values()):
        if ph.get("file") == src.stem and not ph.get("depth") and max(ph.get("w") or 0, ph.get("h") or 0) >= size * 0.75:
            photos[key] = dict(ph)
            return key
    try:
        from PIL import Image
        kind = ((sb.get("_img_meta") or {}).get(src.stem) or {}).get("kind") or "generated"
        im = Image.open(src).convert("RGB")
        im.thumbnail((size, size))
        if kind == "commons":
            import video3_images as IMG        # 资料图轻轻往当天的色调靠（和 prep_photos 一样）
            im = IMG.grade(im, sb.get("accent"))
        out = issue / VIDEO_OUT / "img"
        out.mkdir(parents=True, exist_ok=True)
        stem = "%s_%d" % (src.stem, size)
        im.save(out / (stem + ".webp"), quality=80, method=6)
    except Exception as e:  # noqa: BLE001
        say("注意：配图 %s 没备好（%s），这一处不带图" % (name, e))
        return None
    photos[key] = {"src": "img/%s.webp" % stem, "depth": None, "w": im.size[0], "h": im.size[1], "kind": kind, "file": src.stem,
                   "from": str(src.relative_to(issue))}
    return key


def ensure_shot(sb, photos, key, shot):
    """原文截图（PNG，2 倍清晰度）压成 webp 放进演示页的 img/，登记进 images（kind: screenshot，署名另写一行，不算 AI 配图）。"""
    issue = Path(sb["_issue"]) if sb.get("_issue") else None
    png, rec = Path(shot["png"]), shot.get("rec") or {}
    if not issue or not png.is_file():
        return None
    try:
        from PIL import Image
        im = Image.open(png).convert("RGB")
        im.thumbnail((1600, 1600))
        out = issue / VIDEO_OUT / "img"
        out.mkdir(parents=True, exist_ok=True)
        stem = "shot_" + re.sub(r"[^A-Za-z0-9_]", "_", key)
        im.save(out / (stem + ".webp"), quality=86, method=6)
    except Exception as e:  # noqa: BLE001
        say("注意：原文截图 %s 没备好（%s），这一块退回摘录" % (png.name, e))
        return None
    try:
        rel = str(png.relative_to(issue))
    except ValueError:
        rel = png.name
    photos["shot." + key] = {"src": "img/%s.webp" % stem, "depth": None, "w": im.size[0], "h": im.size[1], "kind": "screenshot",
                             "file": stem, "from": rel, "url": rec.get("final_url") or rec.get("url"), "shot_at": rec.get("shot_at"),
                             "source": shot.get("name") or {}}
    return "shot." + key


def shot_data(sb, photos, owner, key):
    """结合式的 shot 编进播放器的字段：{src, quote, full, zh} 加上截图（img、lines、w、h）；截图不能用（_shot_fail）就不带图，播放器排成摘录。"""
    s0 = owner.get("_src") or {}
    out = {"src": {"name": s0.get("name") or {}, "date": s0.get("date") or {}, "url": s0.get("url")},
           "quote": owner.get("quote"), "full": s0.get("full") or owner.get("quote"), "zh": s0.get("zh")}
    sh = owner.get("_shot") or {}
    if sh and not owner.get("_shot_fail"):
        k = ensure_shot(sb, photos, key, dict(sh, name=(s0.get("name") or {})))
        rec = sh.get("rec") or {}
        if k:
            out.update({"img": k, "lines": rec.get("lines") or [], "w": rec.get("w"), "h": rec.get("h")})
    return out


def source_data(sb, photos, b):
    """source_shot / source_excerpt 编进播放器的字段：出处签、原句、全文（摘录用）、中文行；截图成功的再带图和每一行的位置。"""
    s0 = b.get("_src") or {}
    out = {"src": {"name": s0.get("name") or {}, "date": s0.get("date") or {}, "url": s0.get("url")},
           "quote": b.get("quote"), "full": s0.get("full") or b.get("quote"), "zh": s0.get("zh")}
    if b["type"] == "source_shot":
        sh = b.get("_shot") or {}
        key = ensure_shot(sb, photos, b["id"], dict(sh, name=(s0.get("name") or {}))) if sh else None
        rec = sh.get("rec") or {}
        if key:
            out["shot"] = {"img": key, "lines": rec.get("lines") or [], "w": rec.get("w"), "h": rec.get("h")}
        else:
            out["type"] = "source_excerpt"
    return out


def compile_chapters(sb, T, marks, photos):
    """按对齐好的触发词时间（T）把每章、每个模板编成播放器要的结构。"""
    out = []
    try:
        blanks = blank_spans(sb, T, marks)       # 关键帧总览要截的空档（video3_record.mjs 读 chapters[].blank）
    except Exception:  # noqa: BLE001
        blanks = {}
    for i, c in enumerate(sb["chapters"]):
        m = marks[i]
        start = 0.0 if i == 0 else marks[i - 1]["end"]
        ch = {"id": c["id"], "n": i + 1, "kind": c["kind"], "label": txt(c["label"]), "start": start, "end": m["end"],
              "vs": m["voice_start"], "ve": m["voice_end"], "narration": c["narration"],
              "handoff": c.get("handoff"), "blocks": []}
        for b in c.get("blocks") or []:
            pre = "%s.%s." % (c["id"], b["id"])
            b2 = json.loads(json.dumps(b, ensure_ascii=False))
            lkeys = set()
            for slot, owner, field, _ in logo_slots(b2):          # 标志：换成 {k: 键, t: 出现的秒数（没有触发词就是 null）}
                if field == "logo":
                    continue
                lst = []
                for j, r in enumerate(owner[field]):
                    ck = "%s%s%d" % (pre, slot, j)
                    lkeys.add(ck)
                    lst.append({"k": r if isinstance(r, str) else r["key"], "t": T.get(ck)})
                owner[field] = lst
            nb = strip_labels(b2)
            nb["t"] = {k[len(pre):]: v for k, v in T.items() if k.startswith(pre) and not k.endswith(".end") and k not in lkeys}
            if b["type"] == "image_card":
                nb["img"] = b["id"] if b["id"] in photos else None
            for key in ([b["id"]] if b["type"] == "post_card" and b.get("image") else []):
                nb["img"] = key if key in photos else None
            for i2, it in enumerate(nb.get("items") or [] if b["type"] == "tile_row" else []):
                if isinstance(it, dict) and it.get("image"):
                    k2 = "%s.items%d" % (b["id"], i2)
                    it["img"] = k2 if k2 in photos else None
            if b["type"] == "quote_card" and b.get("image"):          # 11-06：要点卡题图
                nb["img"] = ensure_photo(sb, photos, b["id"], b["image"], 1200)
            if b["type"] in PHOTO_BLOCKS and b.get("photo"):           # 11-07：压在配图上（动效尝试版）
                nb["photo_img"] = ensure_photo(sb, photos, "%s.photo" % b["id"], b["photo"], 1600)
            for i2, tk in enumerate(nb.get("ticks") or [] if b["type"] == "timeline" else []):    # 11-06：时间轨日子上的小图
                if isinstance(tk, dict) and tk.get("image"):
                    tk["img"] = ensure_photo(sb, photos, "%s.ticks%d" % (b["id"], i2), tk["image"], 800)
            for f in SPLIT_SIDES if b["type"] == "split" else ():                           # 11-06 晚：国内外小卡上的题图
                for i2, it in enumerate(nb.get(f) or []):
                    if isinstance(it, dict) and it.get("image"):
                        it["img"] = ensure_photo(sb, photos, "%s.%s%d" % (b["id"], f, i2), it["image"], 800)
            if b["type"] == "tally":                                   # 11-06：计数模板要画的州界（只带用得到的）
                nb["geo"] = tally_geo(b)
                nb.pop("states_ref", None)
            if b["type"] in SOURCE_BLOCKS:                             # 动效尝试：原文截图／摘录
                nb.update(source_data(sb, photos, b))
                for k in ("_src", "_shot", "_shot_fail", "fact", "shot_id"):
                    nb.pop(k, None)
            if b["type"] in CARD_SHOT and isinstance(b.get("shot"), dict):     # 结合式：原话卡带原文截图（替代 image）
                nb["shot"] = shot_data(sb, photos, b["shot"], b["shot"].get("id") or b["id"])
                nb.pop("img", None)
                nb.pop("_image_replaced", None)
            for i2, tk in enumerate(nb.get("ticks") or [] if b["type"] == "timeline" else []):    # 结合式：时间轴日子带原文截图
                src_tk = (b.get("ticks") or [])[i2] if i2 < len(b.get("ticks") or []) else {}
                if isinstance(tk, dict) and isinstance(src_tk, dict) and isinstance(src_tk.get("shot"), dict):
                    tk["shot"] = shot_data(sb, photos, src_tk["shot"], src_tk["shot"].get("id") or "%s_t%d" % (b["id"], i2))
                    tk.pop("_image_replaced", None)
                    if src_tk.get("_image_replaced") and not tk.get("img"):     # 11-08（K46）：截图成功时这一天原来的配图留着当小图（只有开关开着才截图）
                        tk["img"] = ensure_photo(sb, photos, "%s.ticks%d" % (b["id"], i2), src_tk["_image_replaced"], 800)
            if b["type"] == "headline_open":                           # 动效尝试：开场速览每一屏的图、章名、角标的字
                nb.setdefault("tag", {"zh": "今日速览", "en": "Today at a glance"})
                idx = {c2.get("id"): (k2, c2) for k2, c2 in enumerate(sb["chapters"])}
                for i2, it in enumerate(nb.get("items") or []):
                    if not isinstance(it, dict):
                        continue
                    k2, c2 = idx.get(it.get("ch"), (None, None))
                    if c2:
                        it["label"] = txt(c2.get("label"))
                    if it.get("image"):
                        it["img"] = ensure_photo(sb, photos, "%s.items%d" % (b["id"], i2), it["image"], 1600)
            ch["blocks"].append(nb)
        if c["kind"] == "close":
            ch["end_card"] = strip_labels(c.get("end") or {})
        if blanks.get(c["id"]):
            ch["blank"] = blanks[c["id"]]
        out.append(ch)
    return out


def clusters(sb):
    out = []
    for c in sb["chapters"]:
        if c["kind"] not in ("story", "contrast"):
            continue
        chip = c.get("chip") or {}
        out.append({"id": c["id"], "ch": c["id"], "name": txt(chip.get("name")), "key": dict(txt(chip.get("key")), ref=(chip.get("key") or {}).get("ref")),
                    "sub": txt(chip.get("sub")), "stories": c.get("stories") or [],
                    "note": [{"zh": n.get("zh", ""), "en": n.get("en", ""), "ref": n.get("ref") or []} for n in c.get("note") or []]})
    return out


def strings(sb):
    """片头、片尾的大字（播放器用 S 取；网页截字体也读它）。"""
    t = sb.get("title") or {}
    close = next(c for c in sb["chapters"] if c["kind"] == "close")
    end = close.get("end") or {}
    lines = end.get("lines") or []
    return {"title.date": {"zh": t.get("date") or ""}, "title.main": txt(t.get("main")), "title.line": txt(t.get("line")),
            "close.title": txt(end.get("title")),
            "close.hint": {"zh": " · ".join(l.get("zh", "") for l in lines), "en": " · ".join(l.get("en", "") for l in lines)}}
