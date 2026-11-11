#!/usr/bin/env python3
"""视频导演（2026-11-08 晚加，fd 第 14 步调用）：按 11-08 视频三方对比里 B（Claude 导演）的做法，让 Claude 看着画面重新导演这一期视频。

旁白不动（第 6 步写稿写的、第 11 步配好的音）；导演改的是画面：
  1. 第一轮：claude -p（Opus，只给读写自己工作文件夹的工具）照 pipeline/prompts/视频导演.md 写 镜头表.md 和 视频v3_分镜.json；
  2. 正式的分镜检查（旁白、章 id/kind/title/tone 没改＋video3_build.prepare），不过就把报错原样交回导演改（最多两次，
     检查一次只报一类错），还不过就退回；
  3. 截原文截图（同一句截过的不重截）、画导演新要的图（video3_images.ensure，按 FD_IMAGE_BACKENDS 选后端）、组装、出关键帧
     （总览＋单帧；单帧里一部分是固定位置，一部分是每轮不同的随机时刻，防止对着取样点调时间）；
  4. 第二轮：导演看关键帧改分镜、写 改动说明.md，再检查一次（不过改一次）；导演点名要换的图（新 id）才画；
  5. 出成片：按第二轮分镜组装好演示页，放在渲染副本的 11_视频v3/。换进这一期由 fd 做（pipeline/orchestrator/steps.py Video.director）。
任何一步失败、超时或超出总时间预算，就停下、在结果里写"退回"和原因；这一期照常用第 6 步分镜组装的那一版（fd 先组装好的老路）。

旁白归导演（2026-11-09 加，--narration；fd 按 fd_开关.json 的"视频旁白归导演"决定给不给）：
  1'. 第一轮导演同时写旁白、镜头表、分镜（章的数量、顺序、id、title、tone 都能改）；输入多了 能画出来的事实.md、审读意见、选题、读音表；
  2'. 检查换成第 7 步那一套（helpers.py storyboard：分镜、旁白禁用说法、读音表、时长、关系画面），再加稿子检查（script_check：
      数字、引语、英文名在事件卡里）、读音表命令行那一套（首次补中文等）、中文人名和头衔、术语定名，以及两条热点必须出现
      （选题 hot 的前两条，hot_missing；11-09 晚加）；不过交回导演改，最多两次；
  3'. 过了只重配视频旁白（video3_build.py --stage voice，在渲染副本里，照现有配音程序和把关；只有改过的章花钱），钱记进 结果.json；
  4'. 检查改两次还不过、配音没成、钱不够：旁白整段退回第 6 步写的现行旁白，导演再按现行旁白只导画面（上面 1–5 照旧）；
  5'. 第二轮导演也能小改旁白：改了就再查、再配改过的章；第二轮的旁白没过就用第一轮那一版（不再请导演）。
  这一期的 04_文稿/、05_配音/ 一律不动：导演写的旁白和配音留在 11_视频v3_导演/（终版_视频旁白.md、终版_配音/），成片音频在 11_视频v3/audio/。

文件放哪：
  <期目录>/11_视频v3_导演/            导演的工作文件夹（只有它交给 claude）：导演说明.md、输入/、镜头表.md、视频v3_分镜.json、改动说明.md、
                                     检查结果.txt、第一轮_*、关键帧_第1轮/、关键帧_第2轮/、日志_*.json、结果.json
  $FD_DIRECTOR_WORK/<日期>/渲染/      组装用的副本（默认 ~/.cache/frontier-daily/视频导演/；放在导演文件夹外面，导演看不到组装中间产物）

用法（项目根）：
    PY=~/.venvs/frontier-daily/bin/python
    $PY site/tools/video3_director.py 测试版/2026-11-08                 # 前提：这一期已经按老路组装过（11_视频v3/video3_media.json 在）
    $PY site/tools/video3_director.py <期目录> --no-new-images          # 测试用：不调任何画图工具，只用已有的图（导演也会被告知不能新画）
    $PY site/tools/video3_director.py <期目录> --budget 2700            # 总时间预算（秒，默认 2700，环境变量 FD_DIRECTOR_BUDGET 也行）
    $PY site/tools/video3_director.py <期目录> --resume                 # 上次第一轮之后退回的：接着往下走，不重跑第一轮
    $PY site/tools/video3_director.py <期目录> --narration --voice-budget 0.10   # 旁白也归导演写；重配视频旁白最多花 0.10 美元（--engine mimo 用备用声音）
环境变量：FD_DIRECTOR_MODEL（默认 opus）、FD_DIRECTOR_EFFORT（思考强度；默认不传、用 claude 自己的默认档。11-10 本机对比：Opus 5.5、Fable 5.2 设 xhigh
都在第一轮 1200 秒上限处超时、整段退回，所以默认不设；可写 low、medium、high、xhigh、max）、FD_DIRECTOR_WORK、FD_DIRECTOR_BUDGET、FD_DIRECTOR_NO_NEW_IMAGES=1（同 --no-new-images）、
FD_IMAGE_BACKENDS（画图后端，见 video3_images.py）。claude 用本机登录的订阅：调用时去掉 ANTHROPIC_API_KEY（FD_DIRECTOR_ALLOW_API_KEY=1 才保留）。
退出码：0 导演版做成（结果.json 状态"用导演版"）；3 退回（结果.json 写原因）；2 参数不对。
"""
import argparse
import contextlib
import io
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for p in (str(HERE), str(ROOT / "pipeline")):
    if p not in sys.path:
        sys.path.insert(0, p)

STORYBOARD = "04_文稿/视频v3_分镜.json"
MEDIA = "11_视频v3/video3_media.json"
DIR_NAME = "11_视频v3_导演"
PROMPT_FILE = ROOT / "pipeline/prompts/视频导演.md"
PROMPTS = ROOT / "pipeline/prompts"
KEEP = ("narration", "id", "kind", "title", "tone")
TOP_KEEP = ("schema", "edition", "date", "accent")
# 时间预算（秒）。11-08 对比时 B 两轮导演 523＋467 秒、两次组装 195＋419 秒（含画 12 张图、录 MP4），合计约 27 分钟。
# 这里给：每轮导演最多 20 分钟、改错一次最多 7 分钟；整个导演环节最多 45 分钟，超了就退回老路（fd 给这条命令再多 5 分钟余量）。
BUDGET = 2700
ROUND_MAX = 1200
FIX_MAX = 420
FIX_TRIES = 2                 # 检查不过交回导演改几次（11-08 实测：检查一次只报一类错，改完一类才露出下一类，改一次不够）
MIN_LEFT_FOR_ROUND2 = 600     # 第二轮开始前剩不到 10 分钟：直接退回（第二轮加成片组装通常要 10–15 分钟）
SHOT_TOTAL = 150
COPY_PARTS = ("03_事件卡", "04_文稿", "05_配音/视频旁白_v3", "06_配图", "10_网页v3")     # 组装要读的部分（播客音频等不拷）

P1 = ("你是这期视频的导演。请先完整阅读本文件夹里的 导演说明.md，然后按其中“第一轮”的要求，读 输入/ 里的材料（图片请打开看），"
      "在本文件夹根目录写出 镜头表.md 和 视频v3_分镜.json。只在本文件夹里读写，不要改 输入/ 里的文件。写完回复一句话说明完成。")
P2 = ("现在是第二轮。请重读本文件夹里的 导演说明.md 的“第二轮”一节，打开 输入/关键帧/ 里的关键帧（按你第一轮的分镜组装出来的），"
      "对照 输入/旁白与时间.md 和你的 镜头表.md 逐帧看，然后直接改 视频v3_分镜.json（旁白照样不能改），需要的话补画新图（用新的 id）、"
      "更新 镜头表.md，并写 改动说明.md。只在本文件夹里读写，不要改 输入/ 里的文件。写完回复一句话说明完成。")
PFIX = ("你写的 视频v3_分镜.json 没有通过程序检查。检查结果原样放在本文件夹的 检查结果.txt 里。请读它，按报错改 视频v3_分镜.json"
        "（导演说明.md 的要求照旧，旁白不能改），只在本文件夹里读写。改完回复一句话说明改了什么。")
NO_NEW_NOTE = ("（这一次是测试，不能新画图：只用 输入/素材清单.md 里已有的图、截图和标志，image_requests 里不要加新的 id；"
               "导演说明里关于新画图的部分这次跳过。）")
# 旁白归导演（11-09 加）：三句开场提示都多一句，点名 导演说明.md 最后一节
NARR_NOTE = ("（这一期旁白也归你写：按 导演说明.md 最后一节“旁白也归你写”办，那一节和前面“旁白不能改”冲突时以那一节为准；"
             "旁白写在每章的 narration 里，现行旁白在 输入/现分镜.json 和 输入/现行旁白与时间.md，只当参考。）")
NARR_NOTE2 = ("（这一期旁白归你写：输入/旁白与时间.md 现在是你第一轮写的旁白配好音以后的真实时间。旁白只在必须时改，"
              "改了的章要重新配音；改了在 改动说明.md 里写明改了哪句、为什么。）")
NARR_BACK_NOTE = ("（你写的旁白没有通过检查（或没配成音），这一期旁白整段退回第 6 步写的现行旁白：现在按 导演说明.md 前面的规矩只导画面，"
                  "旁白一个字都不能改，章的 id、顺序也照 输入/现分镜.json。你上一版的文件已挪到 旁白没过/ 留底，不用再看。）")
NARR_FILES = ("审读意见.md", "审读处理.md")                       # 期目录根上的独立审读结果，旁白归导演时放进 输入/
LINEUP = "02_选题/最终选题.json"
NARRATION = "04_文稿/视频旁白_v3.md"
VOICE_DIR = "05_配音/视频旁白_v3"
VOICE_MAX = 900               # 重配一次视频旁白最多几秒（一期 6 章约 1–3 分钟，含音高、音色把关重录）
VOICE_MAX_MIMO = 1800         # 备用声音 MiMo 慢得多（11-10 测试运行：云端 15 分钟只配完 6 章里的 4 章），给它 30 分钟；fd 那边同时把导演总预算加 20 分钟
# 中文头衔：旁白里出现就要在事件卡里也出现（英文头衔如 CEO 由稿子检查的英文名那一项管）
TITLE_WORDS = ("联合创始人", "创始人", "首席执行官", "首席科学家", "首席技术官", "首席财务官", "首席运营官", "董事长", "董事会主席",
               "副总裁", "总裁", "总经理", "负责人", "发言人", "部长", "高管", "分析师", "研究员", "教授", "院士", "总监", "掌门人", "掌舵人")


class Fallback(Exception):
    """导演环节退回老路的原因（一句话）。"""


class NarrFallback(Exception):
    """旁白归导演时：旁白整段退回现行旁白的原因（一句话）；导演环节照常往下，只是改回只导画面。"""



EFFORTS = ("low", "medium", "high", "xhigh", "max")


def director_effort():
    """导演的思考强度。环境变量 FD_DIRECTOR_EFFORT 可改；没设、写 default（或 none、off）就不传 --effort，用 claude 自己的默认档。
    11-10 本机对比（本机资料/试验/导演模型对比_1110/）：xhigh 在现行时限（每轮 1200 秒、总 2700 秒）下第一轮就超时退回，
    所以默认不设；要用 xhigh 得先放宽时限再测。写了认不出的值也不传，只提醒一句，不让导演因此退回。"""
    v = (os.environ.get("FD_DIRECTOR_EFFORT") or "default").strip().lower()
    if v in ("default", "none", "off", ""):
        return None
    if v not in EFFORTS:
        print("  注意：FD_DIRECTOR_EFFORT=%r 认不出（可写 %s 或 default），这次不传 --effort" % (v, "、".join(EFFORTS)))
        return None
    return v


def say(*a):
    print(*a, flush=True)


def stamp():
    return time.strftime("%Y-%m-%d %H:%M:%S %Z")


def stash(path, work_root):
    """不删除：本机（macOS）移进废纸篓，别处（云端 Linux）移进 $FD_DIRECTOR_WORK/_旧/。"""
    path = Path(path)
    if not path.exists():
        return None
    tr = Path.home() / ".Trash"
    base = tr if (sys.platform == "darwin" and tr.is_dir()) else Path(work_root) / "_旧"
    base.mkdir(parents=True, exist_ok=True)
    dst = base / ("%s_%s_%s" % (path.parent.name, path.name, time.strftime("%Y%m%d-%H%M%S")))
    shutil.move(str(path), str(dst))
    return dst


# ---------------------------------------------------------------- 输入包
def edition_prompts(edition):
    files = ["写稿_视频v3.md"]
    if edition and edition != "weekday" and (PROMPTS / "写稿_视频v3_周末.md").exists():
        files.append("写稿_视频v3_周末.md")
    return files + ["英文名表.yaml"]


def thumb(src, dst, w=1024):
    from PIL import Image
    im = Image.open(src).convert("RGB")
    size = im.size
    im.thumbnail((w, w))
    im.save(dst, quality=82)
    return size


def prompt_subjects(d):
    """06_配图/视频/提示词记录.md 每张一行：`<id>.png`（placement，events）：画面。返回 {id: 画面}。"""
    out = {}
    p = d / "提示词记录.md"
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^- \S+ `([^`]+)\.(?:png|jpg|jpeg|webp)`（[^）]*）：(.*)$", ln)
            if m:      # 行尾是 video3_images 写的"agy，N 秒""Codex，用量 …""**失败**…"，去掉
                out[m.group(1)] = re.sub(r"\s+(?:agy，\d+ 秒|Codex，用量|\*\*失败\*\*).*$", "", m.group(2)).strip()
    return out


def narration_md(media, sb):
    titles = {c["id"]: c.get("title") for c in sb["chapters"]}
    L = ["# 旁白与配好音的时间（%s，已配音，一个字都不能改）" % media.get("date", ""), "",
         "时间单位：秒，从视频开头算。整片 %.1f 秒。每章：章的起止（start/end，含章间音乐空隙）、人声起止（vs/ve）；下面逐句列出这句话说出的起止时间。" % media["duration"],
         "触发词（cues）写这一章旁白里的一小段原文，画面在说到它的那一刻出现；可以按下面的句子时间估每个画面能停多久。", ""]
    for ci, c in enumerate(media["chapters"]):
        t = titles.get(c["id"])
        L += ["## %s（id: %s，kind: %s）" % (t.get("zh") if isinstance(t, dict) else t, c["id"], c["kind"]), "",
              "- 章：%.2f – %.2f 秒；人声：%.2f – %.2f 秒（人声约 %.1f 秒）" % (c["start"], c["end"], c["vs"], c["ve"], c["ve"] - c["vs"]), "",
              "旁白原文：", "", "> " + (c.get("narration") or next((x.get("narration") for x in sb["chapters"] if x["id"] == c["id"]), "")), "",
              "逐句：", ""]
        for s in media.get("transcript") or []:
            if s["ch"] == ci:
                L.append("- %.2f – %.2f（%.1f 秒）：%s" % (s["start"], s["end"], s["end"] - s["start"], s["text"]))
        L.append("")
    return "\n".join(L)


IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
DATE_RE = re.compile(r"\d{4} ?年|\d{1,2} ?月 ?\d{1,2} ?日|\d{1,2} ?月|周[一二三四五六日天]|星期[一二三四五六日天]|上周|本周|下周|昨天|今天|明天|"
                     r"此前|随后|之后|之前|预计|计划|将于|今年|明年|去年|春季|夏季|秋季|冬季|季度|月底|年底")


def _jieba():
    """jieba 的词性切分（找人名、地名用）；没装就返回 None。它自己的老写法会冒一串 SyntaxWarning，导入时压掉。"""
    import warnings
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import jieba
            import jieba.posseg as pseg
        jieba.setLogLevel(60)
        return pseg
    except ImportError:
        return None


def _logo_names(L):
    """标志库每个键 → 它的名字（中文、英文、别名）；只收有图形文件的（文字小签不算标志）。"""
    out = {}
    for k, v in L.items():
        if not isinstance(v, dict) or not v.get("file"):
            continue
        n = v.get("names") or {}
        vals = ([n.get("zh"), n.get("en")] + list(n.get("aliases") or [])) if isinstance(n, dict) else ([n] if isinstance(n, str) else list(n))
        out[k] = [x for x in vals if isinstance(x, str) and len(x) >= 2]
    return out


def _strings(o):
    """一张事件卡里所有的字（只要值，不要键名）。"""
    if isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)
    elif isinstance(o, str):
        yield o


def drawable_md(issue, sb):
    """能画出来的事实（11-09 加，旁白归导演时给导演）：每张事件卡里画得出来的事——数字、时间先后、地点、原话、现成配图和截图、标志。
    程序按字面从事件卡里摘，不判断重要不重要；口径（单位、谁报的）原样写在后面，口径不同的数不能放进同一张图。"""
    cards = json.loads((issue / "03_事件卡/cards_写稿用.json").read_text(encoding="utf-8"))
    img = issue / "06_配图"
    web = {p.stem.lower() for p in img.glob("*") if p.suffix.lower() in IMG_EXT}
    vids = {}
    meta = {}
    try:
        meta = json.loads((img / "视频/来源.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    for k, v in (meta or {}).items():
        for e in (v or {}).get("events") or [] if isinstance(v, dict) else []:
            vids.setdefault(str(e).upper(), set()).add(k)
    for r in sb.get("image_requests") or []:
        if isinstance(r, dict) and (img / "视频" / (str(r.get("id")) + ".png")).exists():
            for e in r.get("events") or []:
                vids.setdefault(str(e).upper(), set()).add(r["id"])
    shots = {}
    for jp in sorted((img / "原文截图").glob("*.json")) if (img / "原文截图").exists() else []:
        try:
            rec = json.loads(jp.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("ok") and rec.get("url"):
            shots.setdefault(rec["url"].rstrip("/"), []).append("%s（%s）" % (jp.stem, rec.get("quote") or ""))
    try:
        lg = json.loads((ROOT / "site/assets/logos/来源.json").read_text(encoding="utf-8"))
        names = _logo_names(lg.get("logos", lg))
    except (OSError, ValueError):
        names = {}
    pseg = _jieba()
    L = ["# 能画出来的事实（%s，程序从事件卡里摘的；旁白归你写时先看这份）" % issue.name, "",
         "每张卡按画面能画的几类列出：数字（对比、规模、数量变化）、时间先后（时间线、过程）、地点、原话（原话卡、帖子卡）、"
         "现成的图和截图、标志。`facts` 里引用时写 `{\"event\": 卡号, \"field\": \"facts\"/\"numbers\"/\"who_said\", \"index\": 第几条（从 0 数）, "
         "\"check\": 原文里逐字的一段}`。数字后面括号里是口径：单位、谁报的、和谁比；**口径不同的数不放进同一张柱状图或同一组对比条**。"
         "这里只是摘录，事实以事件卡原文为准。", ""]
    for c in cards:
        eid = c.get("event_id")
        L += ["## %s %s（%s）" % (eid, c.get("title_zh"), c.get("status") or ""), ""]
        have = []
        if eid and eid.lower() in web:
            have.append("网页配图 `%s`" % eid.lower())
        if vids.get(str(eid).upper()):
            have.append("已画的视频配图 " + "、".join("`%s`" % x for x in sorted(vids[str(eid).upper()])))
        for s in c.get("sources") or []:
            for x in shots.get(str(s.get("url") or "").rstrip("/"), []):
                have.append("原文截图 %s" % x)
        L.append("- 现成的图：" + ("；".join(have) if have else "没有（要图就新画，写进 image_requests）"))
        blob = " ".join(str(x) for x in _strings(c))
        lg_hit = [k for k, ns in names.items() if any(re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(n), blob) for n in ns)]
        if lg_hit:
            L.append("- 标志库里有：" + "、".join("`%s`" % k for k in sorted(lg_hit)))
        nums = []
        for i, n in enumerate(c.get("numbers") or []):
            if isinstance(n, dict):
                cmp_ = n.get("compare_zh") or ""
                nums.append("  - numbers[%d]：%s %s —— %s%s" % (i, n.get("value"), n.get("unit") or "", n.get("meaning_zh") or "",
                                                              "（和谁比：%s）" % cmp_ if cmp_ else ""))
        for i, f in enumerate(c.get("facts") or []):
            t = (f or {}).get("text_zh") or ""
            if re.search(r"\d", t):
                nums.append("  - facts[%d]：%s" % (i, t))
        if nums:
            L += ["- 数字（可画对比、规模、数量变化）："] + nums
        times = ["  - facts[%d]：%s" % (i, (f or {}).get("text_zh")) for i, f in enumerate(c.get("facts") or [])
                 if DATE_RE.search((f or {}).get("text_zh") or "")]
        if times:
            L += ["- 时间、先后（可画时间线、过程）："] + times
        if pseg:
            places = []
            for f in c.get("facts") or []:
                for w, flag in pseg.cut((f or {}).get("text_zh") or ""):
                    if flag == "ns" and len(w) >= 2 and w not in places:
                        places.append(w)
            if places:
                L.append("- 地点（可画地点）：" + "、".join(places))
        quotes = ["  - who_said[%d]：%s ——「%s」" % (i, q.get("who"), (q.get("said_zh") or "")[:90])
                  for i, q in enumerate(c.get("who_said") or []) if isinstance(q, dict)]
        if quotes:
            L += ["- 原话（可画原话卡、帖子卡）："] + quotes
        L.append("")
    return "\n".join(L)


def make_inputs(issue, D, sb, media, no_new, narration=False):
    inp = D / "输入"
    inp.mkdir(parents=True)
    (inp / "素材").mkdir()
    shutil.copy2(issue / "03_事件卡/cards_写稿用.json", inp / "事件卡_cards_写稿用.json")
    shutil.copy2(issue / STORYBOARD, inp / "现分镜.json")
    for f in edition_prompts(sb.get("edition")) + (["读音表.yaml"] if narration else []):
        if (PROMPTS / f).exists():
            shutil.copy2(PROMPTS / f, inp / f)
    # 旁白归导演时，第 6 步的旁白只是参考（叫"现行旁白"）；第二轮前程序再按导演自己那份旁白的配音写 旁白与时间.md
    (inp / ("现行旁白与时间.md" if narration else "旁白与时间.md")).write_text(narration_md(media, sb), encoding="utf-8")
    if narration:
        for f in NARR_FILES:
            if (issue / f).exists():
                shutil.copy2(issue / f, inp / f)
        if (issue / LINEUP).exists():
            shutil.copy2(issue / LINEUP, inp / "选题.json")
        (inp / "能画出来的事实.md").write_text(drawable_md(issue, sb), encoding="utf-8")
    rows = ["# 能用的素材（%s）" % issue.name, "",
            "分镜里写图名（不带扩展名）就能用；新画的图写进 image_requests，用它的 id%s。缩略图在 `素材/` 里，打开看。" %
            ("（这一次测试不能新画）" if no_new else ""), "", "## 一、网页图（06_配图/，网页那边用的配图）", ""]
    img = issue / "06_配图"
    for p in sorted(x for x in img.glob("*") if x.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")):
        sz = thumb(p, inp / "素材" / (p.stem + ".jpg"))
        t = img / "提示词" / (p.stem + ".txt")
        brief = next((x[len("Subject: "):] for x in t.read_text(encoding="utf-8").splitlines() if x.startswith("Subject: ")), "") if t.exists() else ""
        rows.append("- `%s`（%d×%d）：缩略图 `素材/%s.jpg`。画面描述：%s" % (p.stem, sz[0], sz[1], p.stem, brief or "（没有记录）"))
    rows += ["", "## 二、已画好的视频配图（06_配图/视频/）", ""]
    vd = img / "视频"
    briefs = {r.get("id"): r.get("brief_en") for r in sb.get("image_requests") or [] if isinstance(r, dict)}
    subj = prompt_subjects(vd) if vd.exists() else {}
    for p in sorted(x for x in vd.glob("*") if x.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and ".旧" not in x.name) if vd.exists() else []:
        sz = thumb(p, inp / "素材" / (p.stem + ".jpg"))
        rows.append("- `%s`（%d×%d）：缩略图 `素材/%s.jpg`。画面描述：%s" % (p.stem, sz[0], sz[1], p.stem, briefs.get(p.stem) or subj.get(p.stem) or "（没有记录）"))
    rows += ["", "## 三、原文截图（06_配图/原文截图/，已经截好的；记录原样放在 `素材/截图记录/`）", "",
             "用法见《写稿_视频v3.md》“看得见出处”一节。要复用现成截图：`shot` 里写同样的 `fact`、同样的 `quote`，再写 `\"id\": \"<截图 id>\"`，"
             "图位（原话卡＝card、时间轴日子＝tick、整块 source_shot＝full）也要和原来一样；否则程序会按新的 id 去原网页重截（截不成就自动退回原句摘录）。", ""]
    sd = img / "原文截图"
    (inp / "素材/截图记录").mkdir()
    for jp in sorted(sd.glob("*.json")) if sd.exists() else []:
        try:
            rec = json.loads(jp.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if not isinstance(rec, dict) or not rec.get("ok") or not (sd / (rec.get("png") or "")).is_file():
            continue
        shutil.copy2(jp, inp / "素材/截图记录" / jp.name)
        thumb(sd / rec["png"], inp / "素材" / ("截图_" + jp.stem + ".jpg"), 1400)
        rows.append("- 截图 id `%s`：图位 %s；%s；原句：%s；缩略图 `素材/截图_%s.jpg`" % (jp.stem, rec.get("slot", "full"), rec.get("url"), rec.get("quote"), jp.stem))
    lg = json.loads((ROOT / "site/assets/logos/来源.json").read_text(encoding="utf-8"))
    L = lg.get("logos", lg)
    rows += ["", "## 四、公司标志库（`logos` 字段写键名；只挂旁白或事件卡原文里出现的公司）", ""]
    for k in sorted(L):
        v = L[k]
        n = (v.get("names") or v.get("name") or v.get("n") or "") if isinstance(v, dict) else ""
        rows.append("- `%s`：%s" % (k, json.dumps(n, ensure_ascii=False) if not isinstance(n, str) else n))
    rows += ["", "媒体（CNBC、IT之家、金融时报等）大多没有标志，出处用文字（`who`、`src_tag`、截图左上角的出处签）。", ""]
    (inp / "素材清单.md").write_text("\n".join(rows), encoding="utf-8")


# ---------------------------------------------------------------- claude
def run_claude(D, prompt, timeout, tag):
    exe = shutil.which("claude")
    if not exe:
        raise Fallback("本机没有 claude 命令")
    if timeout < 60:
        raise Fallback("时间预算用完（%s 前只剩 %d 秒）" % (tag, timeout))
    env = dict(os.environ)
    if os.environ.get("FD_DIRECTOR_ALLOW_API_KEY") != "1":
        env.pop("ANTHROPIC_API_KEY", None)          # 走订阅登录，不走按量付费的密钥
    # 导演只读写自己的文件夹，用不着别的钥匙（11-11 加：公开仓库第 10–17 步的环境里有配音和远程画图的钥匙，不往导演那里带）
    for k in ("MIMO_API_KEY", "MIMO_BASE_URL", "GCP_ACCESS_TOKEN", "FD_REMOTE_IMAGES_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        env.pop(k, None)
    model = os.environ.get("FD_DIRECTOR_MODEL") or "opus"
    effort = director_effort()
    cmd = [exe, "-p", prompt, "--model", model] + (["--effort", effort] if effort else []) + ["--add-dir", str(D),
           "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep",
           "--disallowedTools", "Bash", "WebFetch", "WebSearch", "Task", "Agent", "NotebookEdit",
           "--strict-mcp-config", "--output-format", "json"]
    t0 = time.time()
    say("导演 %s：claude -p --model %s%s（最多 %d 秒）开始 %s" % (tag, model, (" --effort " + effort) if effort else "", timeout, stamp()))
    with open(D / ("日志_%s.json" % tag), "w", encoding="utf-8") as fo, open(D / ("日志_%s.err" % tag), "w", encoding="utf-8") as fe:
        p = subprocess.Popen(cmd, cwd=str(D), env=env, stdin=subprocess.DEVNULL, stdout=fo, stderr=fe, start_new_session=True)
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(p.pid, signal.SIGTERM)
            with contextlib.suppress(subprocess.TimeoutExpired):
                p.wait(timeout=20)
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(p.pid, signal.SIGKILL)
            raise Fallback("导演 %s 超时（%d 秒）" % (tag, timeout))
    sec = round(time.time() - t0)
    info = {}
    try:
        info = json.loads((D / ("日志_%s.json" % tag)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    use = {"秒": sec, "退出码": rc, "轮数": info.get("num_turns"), "是否出错": info.get("is_error"),
           "标价折算美元": info.get("total_cost_usd"), "回复": (info.get("result") or "")[:300]}
    say("导演 %s：退出码 %s，%d 秒，%s 轮" % (tag, rc, sec, info.get("num_turns")))
    if rc != 0 or info.get("is_error"):
        err = (D / ("日志_%s.err" % tag)).read_text(encoding="utf-8", errors="replace").strip()[-200:]
        raise Fallback("导演 %s 没成（退出码 %s%s）" % (tag, rc, "：" + (err or (info.get("result") or "")[:160]) if (err or info.get("result")) else ""))
    return use


# ---------------------------------------------------------------- 检查、组装
def load_director(D, orig, narr=False):
    """narr（旁白归导演）：章的 narration、id、kind、title、tone 和章数、顺序都能改，只查顶层那几项。"""
    p = D / "视频v3_分镜.json"
    if not p.exists():
        return None, "没有找到 视频v3_分镜.json"
    try:
        sb = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        return None, "视频v3_分镜.json 不是合法 JSON：%s" % e
    if not isinstance(sb, dict):
        return None, "视频v3_分镜.json 顶层不是一个对象"
    oc, nc = orig["chapters"], sb.get("chapters") or []
    bad = []
    if narr:
        pass
    elif [c.get("id") for c in nc if isinstance(c, dict)] != [c["id"] for c in oc] or len(nc) != len(oc):
        bad.append("章的 id 或顺序变了：%s（应为 %s）" % ([c.get("id") for c in nc if isinstance(c, dict)], [c["id"] for c in oc]))
    else:
        for a, b in zip(oc, nc):
            for k in KEEP:
                if a.get(k) != b.get(k):
                    bad.append("「%s」章的 %s 和原来不一样（这些不能改）：原来 %r，现在 %r" % (a["id"], k, a.get(k), b.get(k)))
    for k in TOP_KEEP:
        if sb.get(k) != orig.get(k):
            bad.append("顶层 %s 和原来不一样：原来 %r，现在 %r" % (k, orig.get(k), sb.get(k)))
    return sb, "\n".join(bad)


def copy_issue(issue, R, work_root):
    """组装副本：只拷组装要读的部分。已有的副本整个挪走（不删），重新拷。"""
    if R.exists():
        stash(R, work_root)
    R.mkdir(parents=True)
    for part in COPY_PARTS:
        s = issue / part
        if s.exists():
            (R / part).parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(s, R / part, symlinks=True, ignore=shutil.ignore_patterns(".DS_Store"))
    if (issue / "11_视频v3").exists():          # 只拷老路的组装记录（不拷图和音频；组装时整个重写）
        (R / "11_视频v3").mkdir()


class Tee(io.StringIO):
    def write(self, s):
        sys.__stdout__.write(s)
        return super().write(s)


def _json_tail(out):
    s = (out or "").strip()
    i = s.find("{")
    while i != -1:
        try:
            return json.loads(s[i:])
        except ValueError:
            i = s.find("{", i + 1)
    return None


def _norm(s):
    return re.sub(r"[\W_]+", "", str(s or ""))


def issue_date(R):
    """这一期的日期（分镜顶层的 date，导演不能改；没有就看渲染副本上一层的目录名）→ date 或 None。"""
    from datetime import date as _d
    for v in (_read_date(R / STORYBOARD), R.parent.name, R.name):
        try:
            return _d.fromisoformat(str(v))
        except (TypeError, ValueError):
            continue
    return None


def _read_date(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8")).get("date")
    except (OSError, ValueError, AttributeError):
        return None


def allow_issue_date(ev, R):
    """11-09 加：开场念的"这期的日期"（11 月 10 日）不是事件卡里的事实，稿子检查别把它当成找不到的数字。
    只放行这一个日期（月、日对上；写了年的，年也要对上）；别的日期照旧要在事件卡里找得到。"""
    d = issue_date(R)
    if d is None:
        return
    orig = ev.has_number

    def has_number(x):
        if x.get("种类") == "日期" and tuple(x.get("值") or ()) == (d.month, d.day) and x.get("年") in (None, d.year):
            return True
        return orig(x)
    ev.has_number = has_number


def fail_reason(D):
    """检查结果.txt 里真正的报错（✗ 要改、检查停下），提醒类的不算；返回最多两条。"""
    try:
        rows = [x.strip() for x in (D / "检查结果.txt").read_text(encoding="utf-8").splitlines()[2:] if x.strip() and not x.startswith("#")]
    except OSError:
        return []
    hard = [r.replace("✗", "").strip() for r in rows if "✗" in r or r.startswith(("检查停下", "检查出错", "分镜检查没过", "旁白检查程序出错"))]
    return hard[:2] or [r for r in rows if not r.startswith("提醒")][:2]


def narration_checks(R):
    """旁白归导演时，第 7 步对稿子的那几道（不改它们的程序，直接调用）再加中文人名、头衔、术语定名。
    返回 (要改, 软的要改, 提醒)：软的是读音表的"首次补中文"（第 7 步对播客稿也是改过一次仍不过就放宽）。"""
    import script_check as S
    must, soft, warn = [], [], []
    nar, cards_p = R / NARRATION, R / "03_事件卡/cards_写稿用.json"
    text = nar.read_text(encoding="utf-8")
    # 1 稿子检查（script_check，第 7 步"稿子"那一项）：数字、引语、英文名在事件卡里，口吻。
    #   播客才有的两条不用：“我们的理解是”每期 2–3 次（视频最多一次，下面另查）、播客的 10–15 分钟时长
    ev = S.Evidence(S.load_cards(str(cards_p)))
    allow_issue_date(ev, R)
    res = S.check(text, ev, day="日常")
    for r in res.get("要改") or []:
        if r.get("类") == "口吻" and r.get("原文") == S.UNDERSTAND and not r.get("行"):
            continue
        must.append("稿子检查：第 %s 行 [%s] %s —— %s" % (r.get("行"), r.get("类"), r.get("原文"), r.get("说明")))
    for r in res.get("请人工看") or []:
        if r.get("类") != "长度":
            warn.append("稿子检查（请人工看）：第 %s 行 [%s] %s —— %s" % (r.get("行"), r.get("类"), r.get("原文"), r.get("说明")))
    n_und = text.count(S.UNDERSTAND)
    if n_und > 1:
        must.append("口吻：“%s”出现 %d 次，视频全篇最多一次" % (S.UNDERSTAND, n_und))
    # 2 读音表（第 7 步对播客稿的命令行那一套：音译、写错语种、人名首次全名、首次补中文、只改口播稿；数字那一项视频不用）
    r = subprocess.run([sys.executable, "-u", str(ROOT / "pipeline/lexicon_check.py"), str(nar), "--json", "--no-numbers"],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    lx = _json_tail(r.stdout)
    if lx is None:
        must.append("读音表：lexicon_check 没给出结果（%s）" % (r.stderr or r.stdout).strip()[-160:])
    else:
        for x in lx.get("要改") or []:
            row = "读音表：第 %s 行 [%s] %s —— %s" % (x.get("行"), x.get("种类"), x.get("原文"), x.get("说明"))
            (soft if x.get("种类") == "首次补中文" else must).append(row)
        for x in (lx.get("提醒") or [])[:6]:
            warn.append("读音表提醒：第 %s 行 [%s] %s —— %s" % (x.get("行"), x.get("种类"), x.get("原文"), x.get("说明")))
    # 3 中文人名、头衔（总规矩 1：人名头衔必须在事件卡里找得到；英文名、英文头衔由上面的稿子检查管）
    cards_txt = cards_p.read_text(encoding="utf-8")
    blob = _norm(json.dumps(json.loads(cards_txt), ensure_ascii=False))
    body = "\n".join(x for x in re.sub(r"<!--.*?-->", "", text, flags=re.S).splitlines()
                     if x.strip() and not x.lstrip().startswith(("#", ">")))
    pseg = _jieba()
    if pseg:
        seen = set()
        for w, flag in pseg.cut(body):
            if flag in ("nr", "nrfg", "nrt") and len(w) >= 2 and w not in seen:
                seen.add(w)
                if _norm(w) not in blob:
                    must.append("人名：旁白里的“%s”（像是人名）在事件卡里找不到" % w)
    else:
        warn.append("没装 jieba，中文人名没查")
    for t in TITLE_WORDS:
        if t in body and t not in cards_txt and not any(t in u and u != t and u in body for u in TITLE_WORDS):
            must.append("头衔：旁白里的“%s”在事件卡里找不到（原文没写的头衔不写）" % t)
    # 4 术语定名（pipeline/prompts/术语定名.json 的"不用"写法）
    try:
        dec = json.loads((PROMPTS / "术语定名.json").read_text(encoding="utf-8")).get("定名") or []
    except (OSError, ValueError):
        dec = []
    for d in dec:
        for bad in d.get("不用") or []:
            if bad and bad in body:
                must.append("术语定名：写“%s”，不写“%s”" % (d.get("zh"), bad))
    return must, soft, warn


HOT_MUST = 2                  # 旁白归导演时：选题里 hot 的前几条必须在视频里讲到（11-09 用户定"两条热点必须出现"）


def hot_missing(sb, lineup, n=HOT_MUST):
    """选题 hot 的前 n 条里，视频没讲到的：[(event_id, 标题)]。"讲到"＝有一个 story／contrast 章的 stories 写了它，
    或这一章旁白有字、画面上有一处 ref 指向它的事实（顶层 facts 的 event）。没有 hot（周末版）就不查。"""
    hot = [h for h in (lineup or {}).get("hot") or [] if isinstance(h, dict) and h.get("event_id")][:n]
    if not hot:
        return []
    facts = sb.get("facts") if isinstance(sb.get("facts"), dict) else {}
    ev_of = {str(k).lower(): str((v or {}).get("event") or "").upper() for k, v in facts.items() if isinstance(v, dict)}
    seen = set()
    for c in sb.get("chapters") or []:
        if not isinstance(c, dict) or c.get("kind") not in ("story", "contrast"):
            continue
        seen |= {str(x).upper() for x in c.get("stories") or [] if x}
        if str(c.get("narration") or "").strip():
            seen |= {ev_of[x.lower()] for x in _strings(c) if x.lower() in ev_of}
    return [(h["event_id"], h.get("title_zh") or "") for h in hot if str(h["event_id"]).upper() not in seen]


def check(D, R, orig, tag, log, narr=False, soft_ok=False):
    """正式的分镜检查：不能改的没改＋video3_build.prepare（不生图）。结果写 检查结果.txt。返回 (过没过, 分镜)。
    narr（旁白归导演）：改用第 7 步的分镜检查（helpers.py storyboard，含旁白规则、读音表、时长、关系画面），再加 narration_checks；
    soft_ok：只剩"软的"（首次补中文）时算过（最后一次改错之后用）。"""
    import video3_build as VB
    sb, bad = load_director(D, orig, narr=narr)
    buf = Tee()
    ok = False
    if sb is not None and not bad:
        (R / STORYBOARD).write_text(json.dumps(sb, ensure_ascii=False, indent=1), encoding="utf-8")
        if not narr:
            with contextlib.redirect_stdout(buf):
                try:
                    VB.prepare(R, gen=False)
                    ok = True
                except SystemExit as e:
                    print("检查停下：%s" % (e.code if not isinstance(e.code, int) else "退出码 %d" % e.code))
                except Exception as e:  # noqa: BLE001
                    print("检查出错：%r" % e)
        else:
            r = subprocess.run([sys.executable, "-u", str(ROOT / "pipeline/orchestrator/helpers.py"), "storyboard", "--issue-dir", str(R)],
                               cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            buf.write("## 一、第 7 步分镜检查（helpers.py storyboard）\n\n" + (r.stdout or "") + (("\n" + r.stderr[-800:]) if r.returncode and r.stderr else "") + "\n")
            if r.returncode == 0:
                try:
                    must, soft, warn = narration_checks(R)
                except Exception as e:  # noqa: BLE001
                    must, soft, warn = ["旁白检查程序出错：%r" % e], [], []
                # 11-09：两条热点必须出现（可以很短：一个画面＋一句"意味着什么"）；缺了交回导演改
                try:
                    lineup = json.loads((D / "输入/选题.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    lineup = None
                for eid, title in hot_missing(sb, lineup):
                    must.append("两条热点必须出现：选题里的热点 %s（%s）这一期视频没讲到（没有一章的 stories 写它，画面上也没有指向它的事实）。"
                                "可以很短：在相关的章里加一个画面、一句它意味着什么，或单独成一章" % (eid, title))
                buf.write("## 二、旁白（稿子检查、读音表、中文人名和头衔、术语定名）\n\n")
                for m in must + soft:
                    buf.write("  ✗ 要改：" + m + "\n")
                for w in warn:
                    buf.write("  提醒：" + w + "\n")
                if not (must + soft):
                    buf.write("  都过了\n")
                ok = not must and (not soft or soft_ok)
                if ok and soft:
                    log.setdefault("提醒", []).append("旁白只差第一次补中文名，改过仍没补，放宽：%s" % "；".join(soft)[:200])
                say("".join("  ✗ " + m + "\n" for m in (must + soft)[:8]).rstrip())
    txt = ("通过" if ok else "没通过") + "（%s，%s）\n\n" % (tag, stamp()) + (bad + "\n" if bad else "") + buf.getvalue()
    (D / "检查结果.txt").write_text(txt, encoding="utf-8")
    (D / ("检查结果_%s.txt" % tag)).write_text(txt, encoding="utf-8")       # 每次检查留一份
    log.setdefault("检查", []).append({"轮": tag, "结果": "通过" if ok else "没通过", "时间": stamp()})
    say("分镜检查（%s）：%s" % (tag, "通过" if ok else "没通过"))
    return ok, sb


def check_or_fix(D, R, orig, tag, log, deadline, narr=False):
    """narr：检查不过改两次还不过，抛 NarrFallback（旁白整段退回现行旁白），不抛 Fallback。"""
    fix = PFIX + (NARR_NOTE if narr else "")
    ok, sb = check(D, R, orig, tag, log, narr=narr)
    k = 0
    while not ok:
        if k >= FIX_TRIES:
            why = "%s的分镜交回导演改了 %d 次仍没通过检查（最后一次的报错：%s）" % (tag, FIX_TRIES, "；".join(fail_reason(D))[:300] or "见检查结果.txt")
            raise NarrFallback(why) if narr else Fallback(why)
        k += 1
        name = "%s_改错%d" % (tag, k)
        log.setdefault("改错", []).append(name)
        log.setdefault("导演", {})[name] = run_claude(D, fix, min(FIX_MAX, int(deadline - time.time())), name)
        ok, sb = check(D, R, orig, name + "后", log, narr=narr, soft_ok=narr and k >= FIX_TRIES)
    return sb


def voice_narration(R, D, tag, log, budget, engine, deadline):
    """旁白归导演：在渲染副本里只重配视频旁白（video3_build.py --stage voice：配音前检查、Gemini 主声音、音高音色把关；
    念法没变的章走缓存、不花钱）。花的钱记进 log["配音花费美元"]。没配成抛 NarrFallback。"""
    if engine != "mimo" and budget < 0.01:
        raise NarrFallback("重配视频旁白的钱不够（这一期还能花 $%.3f）" % budget)
    left = int(deadline - time.time()) - 120
    cap = VOICE_MAX_MIMO if engine == "mimo" else VOICE_MAX
    if left < 180:
        raise NarrFallback("时间不够重配视频旁白（只剩 %d 秒）" % (left + 120))
    cmd = [sys.executable, "-u", str(HERE / "video3_build.py"), str(R), "--stage", "voice", "--no-gen",
           "--budget-usd", "%.3f" % (0 if engine == "mimo" else budget)] + (["--engine", "mimo"] if engine == "mimo" else [])
    t0 = time.time()
    say("重配视频旁白（%s）：%s，预算 $%.3f，开始 %s" % (tag, "MiMo 备用" if engine == "mimo" else "Gemini 主声音", budget, stamp()))
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=min(cap, left))
        rc, out = r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        rc, out = 124, "%s\n超时（%d 秒）" % ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), min(cap, left))
    (D / ("配音_%s.log" % tag)).write_text(out, encoding="utf-8")
    usd = 0.0
    up = R / VOICE_DIR / "usage.json"
    try:
        if up.stat().st_mtime >= t0 - 1:
            u = json.loads(up.read_text(encoding="utf-8"))
            usd = float(((u.get("合计") or {}).get("其中本次新花费美元")) or 0)
    except (OSError, ValueError):
        pass
    log["配音花费美元"] = round(float(log.get("配音花费美元") or 0) + usd, 5)
    rec = {"轮": tag, "退出码": rc, "秒": round(time.time() - t0), "新花费美元": usd, "引擎": engine}
    qc = {}
    try:
        qc = json.loads((R / VOICE_DIR / "qc.json").read_text(encoding="utf-8")) if rc == 0 else {}
    except (OSError, ValueError):
        pass
    q = json.dumps(qc, ensure_ascii=False)
    rec["需人工复听"] = len(re.findall(r'"需人工复听":\s*true', q))
    whole = qc.get("整集") or {}
    pitch = whole.get("音高把关") or {}
    rec["字错率"] = whole.get("字错率")
    if pitch.get("仍超出的块"):           # 配音程序重录到上限仍偏的块，只记不拦（和第 11 步一样）；写进提醒，审片时耳听
        names = [b.get("章") for b in qc.get("各块") or [] if b.get("块") in pitch["仍超出的块"]]
        devs = pitch.get("各块偏差半音") or []
        rec["音高仍偏的块"] = names
        log.setdefault("提醒", []).append("导演旁白的配音：%s 音高重录到上限仍偏（%s 半音，允许 %s），请你耳听" % (
            "、".join(str(n) for n in names), "、".join("%+.1f" % devs[i - 1] for i in pitch["仍超出的块"] if 0 < i <= len(devs)),
            pitch.get("允许偏差半音")))
    log.setdefault("配音", []).append(rec)
    say("重配视频旁白（%s）：退出码 %s，%d 秒，新花 $%.4f" % (tag, rc, rec["秒"], usd))
    if rc != 0:
        last = [x.strip() for x in out.splitlines() if x.strip()][-3:]
        raise NarrFallback("重配视频旁白没成（退出码 %s：%s）" % (rc, "；".join(last)[:200]))
    if rec["需人工复听"]:
        log.setdefault("提醒", []).append("导演旁白的配音有 %d 处标了需人工复听（%s/qc.json）" % (rec["需人工复听"], VOICE_DIR))
    return usd


def narr_key(sb):
    """旁白那几样（章的 id、title、tone、narration），第二轮改没改旁白就比它。"""
    return [(c.get("id"), json.dumps(c.get("title"), ensure_ascii=False), c.get("tone"), c.get("narration")) for c in sb.get("chapters") or []]


def frame_times(media, seed):
    """给导演看的单帧时刻：固定位置（每章开头 1 秒、中间、结尾前 0.8 秒；故事章再加四分之一、四分之三）＋每句话里一个随机时刻（每轮不同）。"""
    fixed = [2.6]
    for c in media["chapters"]:
        vs, ve = c["vs"], c["ve"]
        fixed += [vs + 1.0, (vs + ve) / 2, ve - 0.8] if c["kind"] != "close" else [vs + 1.0, ve - 0.5]
        if c["kind"] == "story":
            fixed += [vs + (ve - vs) * 0.25, vs + (ve - vs) * 0.75]
    rnd = random.Random(seed)
    extra = []
    for s in media.get("transcript") or []:
        a, b = s["start"] + 0.3, max(s["start"] + 0.4, s["end"] - 0.2)
        extra.append(rnd.uniform(a, b))
    dur = media["duration"]
    ts = sorted({round(min(max(t, 0.1), dur - 0.1), 2) for t in fixed + extra})
    out, last = [], -9
    for t in ts:                      # 太近的（不到 0.6 秒）只留一张
        if t - last >= 0.6:
            out.append(t)
            last = t
    return out


def shots(R, sb, log):
    import video3_trial as TR
    t0 = time.time()
    try:
        items = TR.shot_items(R, sb)
        if items:
            TR.run_shots(R, items, True, SHOT_TOTAL)
        log.setdefault("截图秒", []).append(round(time.time() - t0))
    except Exception as e:  # noqa: BLE001  截图只是锦上添花：截不成的组装时退回原句摘录
        say("  提醒：原文截图出错（%r），截图处退回原句摘录" % e)


def images(R, sb, no_new, log):
    import video3_images as IMG
    import video3_storyboard as SB
    reqs = SB.image_requests(sb)
    d = R / IMG.DIR
    have = {f.stem for f in d.glob("*")} if d.exists() else set()
    new = [r["id"] for r in reqs if r.get("id") not in have]
    t0 = time.time()
    if no_new:
        if new:
            say("  测试（不新画）：分镜要的 %s 没有现成的图，这几块不带图" % "、".join(new))
            log.setdefault("没画的图", []).extend(new)
        reqs = [r for r in reqs if r.get("id") in have]
        IMG.ensure(R, reqs, sb.get("accent"), gen=False)
        return []
    if new:
        say("  导演要新画 %d 张：%s（后端顺序 %s）" % (len(new), "、".join(new), " → ".join(IMG.image_backends())))
    IMG.ensure(R, reqs, sb.get("accent"), gen=True)
    got = [i for i in new if IMG.existing(d, i)]
    miss = [i for i in new if i not in got]
    log.setdefault("画图秒", []).append(round(time.time() - t0))
    log.setdefault("新画的图", []).extend(got)
    if miss:
        log.setdefault("没画成的图", []).extend(miss)
        say("  提醒：%s 没画成，这几块不带图" % "、".join(miss))
    return got


def assemble(R, sb, rnd, D, no_new, log, seed, sheet=True):
    """截图 → 画图 → 组装（不配音）→ 关键帧总览（--sheet）→ 单帧。返回关键帧目录。"""
    import video3_trial as TR
    t0 = time.time()
    shots(R, sb, log)
    images(R, sb, no_new, log)
    if (R / "11_视频v3").exists() and any((R / "11_视频v3").iterdir()):
        stash(R / "11_视频v3", R.parent)
    try:
        rc = TR.rebuild(R)
    except SystemExit as e:
        raise Fallback("第 %s 轮组装停下：%s" % (rnd, e.code))
    if rc:
        raise Fallback("第 %s 轮组装没成（退出码 %s）" % (rnd, rc))
    media = json.loads((R / MEDIA).read_text(encoding="utf-8"))
    if float(media.get("duration") or 0) > 180:
        raise Fallback("第 %s 轮组装出来 %.0f 秒，超过 3 分钟" % (rnd, media["duration"]))
    out = D / ("关键帧_第%s轮" % rnd)
    if out.exists():
        stash(out, R.parent)
    out.mkdir(parents=True)
    if sheet:
        r = subprocess.run(["node", str(HERE / "video3_record.mjs"), str(R), "--sheet"], cwd=str(ROOT), capture_output=True, text=True, timeout=600)
        if r.returncode or not (R / "11_视频v3/关键帧总览.jpg").exists():
            raise Fallback("第 %s 轮关键帧总览没出来：%s" % (rnd, (r.stderr or r.stdout).strip()[-160:]))
        shutil.copy2(R / "11_视频v3/关键帧总览.jpg", out / "关键帧总览.jpg")
    ts = frame_times(media, seed)
    png = R.parent / ("_帧_第%s轮" % rnd)
    if png.exists():
        stash(png, R.parent)
    r = subprocess.run(["node", str(HERE / "video3_frames.mjs"), str(R / "11_视频v3"), str(png), "--t", ",".join("%.2f" % t for t in ts)],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise Fallback("第 %s 轮单帧没截成：%s" % (rnd, (r.stderr or r.stdout).strip()[-160:]))
    from PIL import Image
    chs = media["chapters"]
    for t in ts:
        ch = next((c["id"] for c in chs if c["start"] <= t < c["end"]), chs[-1]["id"])
        Image.open(png / ("f_%.2f.png" % t)).convert("RGB").save(out / ("%06.2f秒_%s.jpg" % (t, ch)), quality=86)
    log.setdefault("组装秒", {})["第%s轮" % rnd] = round(time.time() - t0)
    log.setdefault("单帧时刻", {})["第%s轮" % rnd] = ts
    say("第 %s 轮组装：%.1f 秒的片子，关键帧 %d 张 → %s（%d 秒）" % (rnd, media["duration"], len(ts), out, time.time() - t0))
    return out


# ---------------------------------------------------------------- 主流程
def read_log(D):
    try:
        return json.loads((D / "结果.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def narration_back(issue, D, R, work_root, log, why):
    """旁白整段退回现行旁白：导演写的文件挪进 旁白没过/ 留底，输入换回第 6 步旁白的时间，渲染副本重拷（配音回到第 11 步那一份）。"""
    log["旁白"] = "退回现行旁白：%s" % why
    log.setdefault("提醒", []).append("导演写的旁白没用上（%s），这一期旁白用第 6 步写的现行旁白，导演只导画面" % why)
    say("旁白退回现行旁白：%s" % why)
    keep = D / "旁白没过"
    if keep.exists():
        keep = D / ("旁白没过_%s" % time.strftime("%H%M%S"))
    keep.mkdir(parents=True)
    for f in ("镜头表.md", "视频v3_分镜.json", "改动说明.md", "检查结果.txt"):
        if (D / f).exists():
            shutil.move(str(D / f), str(keep / f))
    if (D / "输入/现行旁白与时间.md").exists():
        shutil.copy2(D / "输入/现行旁白与时间.md", D / "输入/旁白与时间.md")
    copy_issue(issue, R, work_root)


def keep_final_voice(R, D):
    """旁白归导演、用了导演版：终版旁白和配音记录（qc、usage、voice、章节时间）留进导演文件夹，给审片和以后查。"""
    shutil.copy2(R / NARRATION, D / "终版_视频旁白.md")
    vd = D / "终版_配音"
    if vd.exists():
        shutil.move(str(vd), str(D / ("终版_配音_旧_%s" % time.strftime("%H%M%S"))))
    vd.mkdir()
    for f in ("qc.json", "usage.json", "voice.json", "video3_chapters.json", "chapters.json"):
        if (R / VOICE_DIR / f).exists():
            shutil.copy2(R / VOICE_DIR / f, vd / f)


def direct(issue, no_new=False, budget=BUDGET, work_root=None, resume=False, narration=False, voice_budget=0.0, engine="gemini"):
    """resume：上次在第一轮之后退回的，接着用导演文件夹里现有的分镜往下走（不重跑第一轮，省一轮导演）。
    narration（11-09 加）：旁白也归导演写；voice_budget 是重配视频旁白最多花的美元，engine 是 gemini 或 mimo（第 11 步用了备用声音时）。"""
    t0 = time.time()
    deadline = t0 + budget
    work_root = Path(work_root or os.environ.get("FD_DIRECTOR_WORK") or Path.home() / ".cache/frontier-daily/视频导演").expanduser()
    D = issue / DIR_NAME
    R = work_root / issue.name / "渲染"
    log = {"状态": "进行中", "开始": stamp(), "预算秒": budget, "不新画（测试）": bool(no_new), "导演文件夹": str(D), "渲染副本": str(R),
           "旁白": "导演写" if narration else "不动（第 6 步写、第 11 步配好的）"}
    if narration:
        log.update({"配音预算美元": round(float(voice_budget), 3), "配音引擎": engine, "配音花费美元": 0.0})

    def save():
        log["用时秒"] = round(time.time() - t0)
        (D / "结果.json").write_text(json.dumps(log, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    prev = {}
    if narration and resume:
        say("旁白归导演时不支持 --resume，从头来")
        resume = False
    if resume and (D / "第一轮_视频v3_分镜.json").exists() and (D / "视频v3_分镜.json").exists():
        prev = read_log(D)
        log["接着上次"] = "接着 %s 那次（第一轮不重跑）" % prev.get("开始", "?")
        log["导演"] = {k: v for k, v in (prev.get("导演") or {}).items()}
        log["上次"] = {k: prev.get(k) for k in ("状态", "原因", "检查", "改错", "用时秒")}
        for old in (D / "输入/关键帧", D / "关键帧_第1轮", D / "关键帧_第2轮"):
            if old.exists():
                stash(old, work_root)
    else:
        resume = False
        if D.exists():
            stash(D, work_root)
        D.mkdir(parents=True)
    try:
        if not (issue / STORYBOARD).exists() or not (issue / MEDIA).exists():
            raise Fallback("这一期还没按老路组装过（缺 %s 或 %s）" % (STORYBOARD, MEDIA))
        orig = json.loads((issue / STORYBOARD).read_text(encoding="utf-8"))
        media0 = json.loads((issue / MEDIA).read_text(encoding="utf-8"))
        if not resume:
            shutil.copy2(PROMPT_FILE, D / "导演说明.md")
            make_inputs(issue, D, orig, media0, no_new, narration=narration)
        copy_issue(issue, R, work_root)
        save()
        note = NO_NEW_NOTE if no_new else ""
        narr = narration
        # 第一轮（旁白归导演：导演写旁白＋镜头表＋分镜 → 第 7 步那套检查 → 只重配视频旁白；哪一步不成就整段退回现行旁白）
        if narr:
            try:
                log.setdefault("导演", {})["第一轮"] = run_claude(D, P1 + NARR_NOTE + note, min(ROUND_MAX, int(deadline - time.time())), "第一轮")
                for f in ("镜头表.md", "视频v3_分镜.json"):
                    if (D / f).exists():
                        shutil.copy2(D / f, D / ("第一轮_" + f))
                sb = check_or_fix(D, R, orig, "第一轮", log, deadline, narr=True)
                save()
                voice_narration(R, D, "第一轮", log, voice_budget, engine, deadline)
                shutil.copy2(D / "视频v3_分镜.json", D / "第一轮终_视频v3_分镜.json")
                save()
            except NarrFallback as e:
                narr = False
                narration_back(issue, D, R, work_root, log, str(e))
                save()
        if not narr:
            tag = "第一轮" if not narration else "第一轮_旁白退回"
            if not resume:
                log.setdefault("导演", {})[tag] = run_claude(D, P1 + (NARR_BACK_NOTE if narration else "") + note,
                                                            min(ROUND_MAX, int(deadline - time.time())), tag)
                for f in ("镜头表.md", "视频v3_分镜.json"):
                    if (D / f).exists():
                        shutil.copy2(D / f, D / ("%s_%s" % (tag, f)))
            sb = check_or_fix(D, R, orig, tag + ("_接着" if resume else ""), log, deadline)
        save()
        kdir = assemble(R, sb, 1, D, no_new, log, "%s-1-%d" % (issue.name, int(t0)))
        shutil.copytree(kdir, D / "输入/关键帧")
        if narr:          # 第二轮给导演看的旁白时间，换成导演自己那份旁白配好音的真实时间
            (D / "输入/旁白与时间.md").write_text(narration_md(json.loads((R / MEDIA).read_text(encoding="utf-8")), sb), encoding="utf-8")
        save()
        if deadline - time.time() < MIN_LEFT_FOR_ROUND2:
            raise Fallback("第二轮开始前时间预算只剩 %d 秒" % (deadline - time.time()))
        # 第二轮
        log["导演"]["第二轮"] = run_claude(D, P2 + (NARR_NOTE2 if narr else "") + note, min(ROUND_MAX, int(deadline - time.time())), "第二轮")
        if not narr:
            sb = check_or_fix(D, R, orig, "第二轮", log, deadline)
        else:
            sb1 = sb
            try:
                sb = check_or_fix(D, R, orig, "第二轮", log, deadline, narr=True)
                if narr_key(sb) != narr_key(sb1):
                    log["第二轮改了旁白"] = True
                    voice_narration(R, D, "第二轮", log, max(0.0, voice_budget - float(log.get("配音花费美元") or 0)), engine, deadline)
            except NarrFallback as e:     # 第二轮的旁白没过或没配成：用第一轮那一版（检查过、配过音），不再请导演
                log["第二轮"] = "没过，用第一轮那一版：%s" % e
                log.setdefault("提醒", []).append("第二轮没过（%s），成片用第一轮那一版" % e)
                if (D / "视频v3_分镜.json").exists():
                    shutil.move(str(D / "视频v3_分镜.json"), str(D / "第二轮没过_视频v3_分镜.json"))
                shutil.copy2(D / "第一轮终_视频v3_分镜.json", D / "视频v3_分镜.json")
                ok, sb = check(D, R, orig, "第一轮那一版", log, narr=True, soft_ok=True)
                if not ok:
                    raise Fallback("第二轮没过，第一轮那一版再查也没过")
                voice_narration(R, D, "第一轮那一版", log, max(0.0, voice_budget - float(log.get("配音花费美元") or 0)), engine, deadline)
        save()
        assemble(R, sb, 2, D, no_new, log, "%s-2-%d" % (issue.name, int(t0)), sheet=False)
        if time.time() > deadline:
            raise Fallback("成片组装完时已超出时间预算（%d 秒）" % budget)
        shutil.copy2(R / STORYBOARD, D / "终版_视频v3_分镜.json")
        if narr:
            keep_final_voice(R, D)
        media = json.loads((R / MEDIA).read_text(encoding="utf-8"))
        log.update({"状态": "用导演版", "成片目录": str(R / "11_视频v3"), "时长秒": media.get("duration"),
                    "渲染配图目录": str(R / "06_配图/视频")})
        save()
        say("导演环节完成：%s（%d 秒）" % (R / "11_视频v3", time.time() - t0))
        return 0, log
    except (Fallback, NarrFallback) as e:
        log.update({"状态": "退回", "原因": str(e)})
    except Exception as e:  # noqa: BLE001  导演环节出任何错都退回老路，不挡出片
        log.update({"状态": "退回", "原因": "导演环节程序出错：%s: %s" % (type(e).__name__, str(e)[:200])})
    save()
    say("导演环节退回：%s" % log["原因"])
    return 3, log


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("issue", help="期目录（已经按老路组装过）")
    ap.add_argument("--no-new-images", action="store_true", help="测试用：不调画图工具，只用已有的图")
    ap.add_argument("--budget", type=int, default=int(os.environ.get("FD_DIRECTOR_BUDGET") or BUDGET), help="总时间预算（秒）")
    ap.add_argument("--work", help="组装副本放哪（默认 $FD_DIRECTOR_WORK 或 ~/.cache/frontier-daily/视频导演）")
    ap.add_argument("--resume", action="store_true",
                    help="上次第一轮之后退回的：接着用导演文件夹里现有的分镜往下走，不重跑第一轮（环境变量 FD_DIRECTOR_RESUME=1 也行）")
    ap.add_argument("--narration", action="store_true", help="旁白也归导演写（11-09 加；fd 按 fd_开关.json 的“视频旁白归导演”决定给不给）")
    ap.add_argument("--voice-budget", type=float, default=0.0, help="旁白归导演时，重配视频旁白最多花多少美元（Gemini）")
    ap.add_argument("--engine", choices=["gemini", "mimo"], default="gemini", help="旁白归导演时用哪个声音（第 11 步用了备用就给 mimo）")
    a = ap.parse_args(argv)
    issue = Path(a.issue).expanduser()
    issue = (issue if issue.is_absolute() else ROOT / issue).resolve()
    if not issue.is_dir():
        ap.error("找不到期目录 %s" % issue)
    rc, _ = direct(issue, no_new=a.no_new_images or os.environ.get("FD_DIRECTOR_NO_NEW_IMAGES") == "1", budget=a.budget, work_root=a.work,
                   resume=a.resume or os.environ.get("FD_DIRECTOR_RESUME") == "1",
                   narration=a.narration, voice_budget=a.voice_budget, engine=a.engine)
    return rc


if __name__ == "__main__":
    sys.exit(main())
