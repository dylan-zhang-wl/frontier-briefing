# -*- coding: utf-8 -*-
"""视频 v3 的中文整词换行（2026-11-09 加；开关在 fd_开关.json 的"视频中文整词换行"）。

全站的规矩：中文一个词不拆到两行，只在词与词之间、标点和空格处换行（经验库 9.3、第二部分）。网页早就做到了
（site/tools/zh_breaks.py 插换行点 + style.css 的 keep-all），视频以前没接上，11-09 燃气轮机那张卡的
"稀缺设备"就被拆成了"稀缺设｜备"。

做法：断点只加在显示那一层，用来匹配和计时的原文一个字不动。
  1. 组装最后（所有字定稿、英文名表也改完以后），把场景数据里要显示给人看的中文逐条过 zh_breaks.phrase_breaks
     （BudouX 切词组、jieba 把关，和网页同一套），得到"原文 → 带换行点的显示文字"的对照表，只写进数据的 zhwrap 一个键
     （一个点都不用加的短词组也进表，显示文字就是原文：播放器照样给它 keep-all，整个词组不从中间断）。
     分镜、旁白、触发词、字幕的字和逐字时间（cues[].text / t）、文字稿都还是原文：触发词按原文对旁白、配图按原文挂句子、
     字幕按字的序号对时间，全都不受影响。
  2. 播放器（site/v3/video3.js 的 wbWalk）建好每张卡片、标题、速览、弹出框的 HTML 以后，按元素里的文字去对照表找：
     找到了才把看不见的换行点（U+200B，"这里可以换行"）、连接符（U+2060，"这里不许换行"）插进那几个文本节点、
     数字和单位之间的空格换成不换行空格，元素加 v3wb（video3.css：word-break: keep-all; overflow-wrap: anywhere）；
     找不到（播放器自己拼出来的字）就原样不动。滚动数字一开始显示 0，对照时数字一段按一段算。
  3. 字幕仍是一个字一个 <i>（逐字变亮按 <i> 的序号对 cues[].t），换行点插在 <i> 和 <i> 之间、不进 <i>，序号和时间不变。

开关关着：数据里不写 zhwrap，播放器什么都不做，视频和加开关以前逐像素一样。
先看环境变量 FD_VIDEO_ZH_WRAP（只管这一次，如 FD_VIDEO_ZH_WRAP=off），再看 fd_开关.json；都没有或读不出来按"开"。
pipeline/orchestrator/common.py 的 zh_wrap_switch 是同一套规则（fd 只用标准库，不 import 这里），两边要一起改。
断行工具（budoux、jieba）没装或出错时只提醒，视频照常组装（等于这一期没开）。
"""
import json
import os
import re
from pathlib import Path

SWITCH_FILE = Path(__file__).resolve().parents[2] / "fd_开关.json"
SWITCH_KEY = "视频中文整词换行"
ENV = "FD_VIDEO_ZH_WRAP"
_OFF = ("off", "0", "false", "no", "关", "关闭", "关掉")
_ON = ("on", "1", "true", "yes", "开", "打开")

ZW, WJ, NBSP = "\u200b", "\u2060", "\u00a0"
CJK = re.compile(r"[\u3400-\u9fff]")
KEY = "zhwrap"                    # 场景数据里对照表的键名（video3.js 读它）
TOP = ("chapters", "S", "clusters", "cues", "transcript", "credits", "music", "logos")   # 这些键下面的字会显示出来
SKIP = ("narration", "T", "url", "m", "t")      # 不显示的：旁白全文（另有字幕和文字稿）、触发时刻、网址、标志遮罩图


def switch():
    """返回 (开着没有, 从哪来的一句话)。"""
    env = str(os.environ.get(ENV) or "").strip().lower()
    if env in _OFF:
        return False, "环境变量 %s=%s" % (ENV, env)
    if env in _ON:
        return True, "环境变量 %s=%s" % (ENV, env)
    try:
        v = str(json.loads(SWITCH_FILE.read_text(encoding="utf-8")).get(SWITCH_KEY) or "").strip().lower()
    except (OSError, ValueError, AttributeError):
        return True, "没有 fd_开关.json（或读不出来），按“开”"
    if v in _OFF:
        return False, "fd_开关.json 的“%s”写着“关”" % SWITCH_KEY
    return True, ("fd_开关.json 的“%s”写着“开”" % SWITCH_KEY if v in _ON
                  else "fd_开关.json 的“%s”值认不出（%r），按“开”" % (SWITCH_KEY, v))


def same_text(raw, disp):
    """显示文字去掉换行点和连接符以后，要和原文一个字一个字对得上（只许把空格换成不换行空格）。"""
    t = disp.replace(ZW, "").replace(WJ, "")
    return len(t) == len(raw) and all(a == b or (a == " " and b == NBSP) for a, b in zip(raw, t))


def display(s, breaks=None):
    """一段字的显示版本（带换行点）；没有中文、或者对不回原文，返回 None（播放器就不动这段）。
    一个点都不用加的（"董事会""据彭博社报道"这种一个词组的）照样返回原文：播放器给它 keep-all，整个词组不从中间断，和网页一样。"""
    if not isinstance(s, str) or not CJK.search(s):
        return None
    if breaks is None:
        import zh_breaks
        breaks = zh_breaks.phrase_breaks
    d = breaks(s)
    if not isinstance(d, str) or not same_text(s, d):
        return None
    return d


def excerpt(b):
    """原句摘录（截图没成功时）画面上那一段：和 video3.js 的 excerptParts 同一个算法（前后各留一点上下文，太长就省略）。"""
    full, q = str(b.get("full") or b.get("quote") or ""), str(b.get("quote") or "")
    i = full.find(q)
    if i < 0:
        full, i = q, 0
    pre, post, room = full[:i], full[i + len(q):], max(40, 260 - len(q))
    if len(pre) > room * 0.55:
        pre = pre[len(pre) - _jsround(room * 0.55):]
        pre = "…" + pre[pre.find(" ") + 1:]
    if len(post) > room * 0.45:
        post = post[:_jsround(room * 0.45)]
        post = post[:post.rfind(" ")] + "…"          # 找不到空格时 rfind 是 -1，和 JS 的 slice(0, -1) 一样去掉最后一个字
    return pre + q + post


def _jsround(x):
    return int(x + 0.5)


def strings(data):
    """场景数据里会显示给人看的字（按出现顺序，去重以前）。"""
    def walk(x, key=""):
        if key in SKIP:
            return
        if isinstance(x, dict):
            if isinstance(x.get("quote"), str):           # 原文截图、原句摘录：画面上是截过的那一段
                yield excerpt(x)
            for k, v in x.items():
                yield from walk(v, k)
        elif isinstance(x, list):
            for v in x:
                yield from walk(v, key)
        elif isinstance(x, str):
            yield x
    for k in TOP:
        if k == "cues":
            for c in data.get("cues") or []:
                yield c.get("text")
        elif k == "transcript":
            for s in data.get("transcript") or []:
                yield s.get("text")
        else:
            yield from walk(data.get(k), k)
    hint = ((data.get("S") or {}).get("close.hint") or {})            # 片尾提示：播放器按"·"拆成几行
    for x in (hint.values() if isinstance(hint, dict) else [hint]):
        if isinstance(x, str):
            yield from (p for p in re.split(r"\s*·\s*", x) if p)


def terms(cards):
    """事件卡里的术语（整体保留，不从中间断开；网页那边也加这些）。"""
    out = []
    for c in (cards or {}).values():
        for t in (c.get("terms") or []) if isinstance(c, dict) else []:
            if isinstance(t, dict) and isinstance(t.get("zh"), str):
                out.append(t["zh"])
    return out


def table(data, extra_words=()):
    """返回 (对照表 {原文: 显示文字}, 一句话)。断行工具没装或出错时对照表是 None。"""
    try:
        import zh_breaks
        zh_breaks.load(extra_words)
    except SystemExit as e:
        return None, "断行工具没装（%s），这一期视频不加整词换行" % e
    except Exception as e:  # noqa: BLE001  断行出错不挡出片
        return None, "断行工具载入出错（%s: %s），这一期视频不加整词换行" % (type(e).__name__, e)
    out, seen = {}, set()
    try:
        for s in strings(data):
            if not isinstance(s, str) or s in seen:
                continue
            seen.add(s)
            d = display(s, zh_breaks.phrase_breaks)
            if d:
                out[s] = d
    except Exception as e:  # noqa: BLE001
        return None, "断行出错（%s: %s），这一期视频不加整词换行" % (type(e).__name__, e)
    n, m = sum(d.count(ZW) for d in out.values()), sum(1 for d in out.values() if ZW in d)
    return out, "中文整词换行：%d 段中文（%d 段带换行点，共 %d 个点；其余是一个词组、整段不断），播放器按它换行" % (len(out), m, n)
