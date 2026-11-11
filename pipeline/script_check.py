#!/usr/bin/env python3
"""稿子核对：口播稿里的数字、引语、英文名能不能在事件卡里找到；主播口吻守没守规矩。

用法（在项目根运行）：
    PY=~/.venvs/frontier-daily/bin/python
    $PY pipeline/script_check.py 稿.md --cards 测试版/2026-10-31/03_事件卡/cards_写稿用.json
    #   --cards 也可以给 04_文稿/写稿输入.json（取里面的 cards）；--json 输出机器可读结果

查什么：
  1. 数字：稿子里的数字（包括"一点二五万亿美元""百分之二十八点五八""十月三十一日"这类读法）
     换成阿拉伯数字后，要能在事件卡里找到同一个值。金额、百分比、日期、年份、带小数的数、
     10 以上的数找不到，算"要改"；不带单位的小数字（"三个词""两件大事"）多半是口头计数，
     找不到只列为"请人工看"。自己算出来的差值、比例（事件卡里没有）会被当成找不到。
  2. 引语：“…”和「…」里的话，要能在事件卡里逐字找到（忽略空格、标点、全半角和数字写法）。
  3. 英文名：稿子里的英文名、型号（如 Sam Altman、iOS 27.3）要在事件卡里出现过。
  4. 口吻：不说"我"（"我们"可以）——唯一的例外是开场那一章的自我介绍：含"我是 Shirley""我是 Dylan"的那一句（每个名字一次，
     2026-11-01 晚用户定；周日开场"我是 Shirley，今天和我一起聊的是 Dylan"整句都算自我介绍），别处再出现照样报；
     英文名检查不管主播名字（Shirley、Dylan 不在事件卡里是正常的）；单人稿（日常、周六）的主播名字只在开场、结尾出现，
     别处出现列为"请人工看"；对谈稿里两人在正文、结尾互称名字都正常（2026-11-01 晚改）；不报幕（"上半场""下半场"）；"我们的理解是"每期 2–3 次；
     不用夸张词；口播里不说"由 AI 生成"。另外提醒：像编亲身经历的说法、"我们之前聊过"
     （要有往期才能说）、超过 120 字的段落。
  5. 长度：不再按字数表，改按这份稿子对应的写稿提示词文末"程序检查"的"成片时长分钟"判，估法和配音程序同一套
     （单人稿 tts.estimate_script，对谈稿 dialog_tts.estimate_dialog）：日常 写稿_播客.md、周六 写稿_周六深度.md、
     周日 写稿_周日深谈.md（tts.DAY_RULES）；不给 --day-type 时自动认：对谈稿算周日，有"深度"开头的章算周六，其余算日常。
  6. 周日对谈稿（行首是"甲：""乙："，自动识别）：行首的说话人标记不算正文；
     正文每一行都要以"甲：""乙："开头，稿末要有 <!-- 语气 {"章名": {"甲": 情绪词, "乙": 情绪词}} -->（规则和 lexicon_check.py
     一样：第十轮起每章、每人都可以写色板里的词、写 fixed 或不写；写了色板以外的词列为"请人工看"，配音时换成默认词）；
     只有附和的一轮（单独一句"对""没错""是的"）算要改；一轮超过 4 句、互相称呼，列为"请人工看"。
只查正文：## 章节标题、<!-- 注释 -->、以 > 开头的备注行不查。事件卡里以 _ 开头的字段
（如 _removed_unverified：核对没通过、被拿掉的内容）和网址不算依据。
这只是字面核对：数字找得到，不等于用在了对的地方；整句意思有没有走样，要人读或另做逐句核查。
退出码：0 = 没有要改的；1 = 有要改的。
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

from lexicon_check import body_mask, dialog_problems, dialog_tone_notes, dialog_turns, is_dialog  # noqa: E402
from tts_qc import _cn_int, cn_numbers_to_arabic  # noqa: E402

# ============================ 可改区 ============================

UNDERSTAND = "我们的理解是"
UNDERSTAND_RANGE = (2, 3)
PARA_MAX = 120
TURN_SENTENCES_MAX = 4
FILLER = {"对", "对的", "对啊", "对呀", "没错", "是的", "是啊", "嗯", "确实", "可不是", "就是", "当然", "好", "好的"}
ADDRESS = ["搭档", "老师"]      # 对谈里这样互相称呼（正文里出现就提醒）；叫名字可以
HOSTS = ["Shirley", "Dylan"]    # 主播名字（2026-11-01 晚定）：开场自我介绍那一句里的"我"不报；英文名检查不管它们
INTRO_CHAPTER = "开场"
NAME_CHAPTERS = ("开场", "结尾", "收尾")   # 单人稿里主播名字只在这几章出现
HYPE = ["炸裂", "碾压", "颠覆", "王炸", "全面超越", "拭目以待"]
ANNOUNCE = ["上半场", "下半场", "上半部分", "下半部分", "第一部分", "第二部分"]
AI_CLAIM = [r"由\s*AI\s*生成", r"AI\s*辅助生成", r"合成语音", r"AI\s*合成", r"我们是\s*AI", r"作为\s*AI", r"真人主播"]
EXPERIENCE = [r"我们(昨天|今天|刚才)?(亲自)?(试了|试用|测了|测试了|体验了|采访|问了|用了)"]
STRONG_UNITS = ("美元", "元", "美分", "小时", "分钟", "名", "项", "倍", "个百分点", "token")
# 这些词里的数字不是数字（"三星"是公司，"一样""统一"是常用词），先遮住再找数字
NOT_NUMBERS = ["三星", "千问", "百度", "一些", "一样", "一起", "一直", "统一", "唯一", "一般", "一定",
               "万一", "一旦", "一度", "一切", "一致", "进一步", "一边", "一方面", "一口气", "一下",
               "一番", "一并", "一同", "一时", "之一", "一体", "一系列", "十足", "一手", "一眼"]

# ==============================================================

WEEKDAY = re.compile(r"(?:周|星期|礼拜)[一二三四五六日天]")
LATIN_PHRASE = re.compile(r"[A-Za-z][A-Za-z0-9'’.\-&+]*(?:\s+[A-Za-z0-9][A-Za-z0-9'’.\-&+]*)*|\d+[A-Za-z]+\b")
NUM = r"(\d{1,3}(?:,\d{3})+(?!\d)|\d+(?:\.\d+)?(?![\d.]))"
EN_MULT = {"thousand": 1e3, "k": 1e3, "million": 1e6, "mn": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9,
           "b": 1e9, "trillion": 1e12, "tn": 1e12, "t": 1e12}
CN_MULT = {"万": 1e4, "亿": 1e8, "万亿": 1e12}
QUOTE = re.compile(r"“([^”]{2,})”|「([^」]{2,})」|\"([^\"]{2,})\"")
PUNCT = re.compile(r"[\s，。、；：！？,.;:!?—…·《》〈〉「」『』“”‘’\"'()（）【】\[\]\-]")


def _num(s):
    return float(s.replace(",", ""))


def _r(v):
    return round(v, 6) if abs(v) < 1e6 else round(v / 1e6, 4) * 1e6


# ---------------------------------------------------------------- 取数字


CN_D = "零〇一二两三四五六七八九"


def _spoken_forms(s):
    """先处理两种普通数字规则会转错的读法：
    钟点"下午五点二十七分"→ 5:27；多段版本号"二点一点三一三"→ 2.1.313。"""
    s = re.sub(rf"([{CN_D}十]{{1,3}})点([{CN_D}十]{{1,3}})分",
               lambda m: f"{_cn_int(m.group(1))}:{int(_cn_int(m.group(2))):02d}"
               if _cn_int(m.group(1)) and _cn_int(m.group(2)) else m.group(0), s)
    s = re.sub(rf"[{CN_D}]+(?:点[{CN_D}]+){{2,}}",
               lambda m: ".".join("".join(str("零一二三四五六七八九".find(c) if c != "〇" and c != "两" else
                                              (0 if c == "〇" else 2)) for c in part)
                                  for part in m.group(0).split("点")), s)
    return s


def prepare(s):
    """事件卡和稿子用同一套写法：全半角统一，周几、常用词遮掉，中文数字转阿拉伯数字，去空白。"""
    s = unicodedata.normalize("NFKC", s)
    s = WEEKDAY.sub(lambda m: "□" * len(m.group(0)), s)
    for w in NOT_NUMBERS:
        s = s.replace(w, "□" * len(w))
    s = re.sub(r"一点(?![零〇一二两三四五六七八九\d])", "□□", s)     # "快一点"不是 1 点
    s = _spoken_forms(s)
    s = cn_numbers_to_arabic(s)
    return re.sub(r"\s+", "", s)


def numbers_in(s, english=False):
    """s 已经 prepare 过。返回 [{种类, 值, 原文, 字面}]；种类：日期/年/月/百分比/分数/序数/数。"""
    out, used = [], [False] * len(s)

    def take(m, item):
        a, b = m.span()
        if any(used[a:b]):
            return
        for i in range(a, b):
            used[i] = True
        item.update(原文=m.group(0), 位置=a)
        out.append(item)

    for m in re.finditer(r"(?<![\d.])\d+(?:\.\d+){2,}(?![\d.])", s):               # 版本号 2.1.313
        take(m, {"种类": "版本", "值": m.group(0)})
    for m in re.finditer(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])", s):              # 钟点 17:27
        take(m, {"种类": "钟点", "值": (int(m.group(1)) % 12, int(m.group(2)))})
    for m in re.finditer(r"(\d{1,2})月(\d{1,2})日", s):
        take(m, {"种类": "日期", "值": (int(m.group(1)), int(m.group(2)))})
    for m in re.finditer(r"(\d{4})-(\d{1,2})-(\d{1,2})", s):                 # 事件卡里的 2026-10-30
        take(m, {"种类": "日期", "值": (int(m.group(2)), int(m.group(3))), "年": int(m.group(1))})
    for m in re.finditer(r"(\d{4})年", s):
        take(m, {"种类": "年", "值": int(m.group(1))})
    for m in re.finditer(r"(?<![\d.])(\d{1,2})月(?!\d)", s):
        take(m, {"种类": "月", "值": int(m.group(1))})
    for m in re.finditer(r"(\d+)分之(\d+(?:\.\d+)?)", s):
        take(m, {"种类": "分数", "值": m.group(0)})
    for m in re.finditer(r"第" + NUM, s):
        take(m, {"种类": "序数", "值": m.group(0)})
    for m in re.finditer(NUM + r"%", s):
        take(m, {"种类": "百分比", "值": _r(_num(m.group(1)))})
    for m in re.finditer(r"(\d+)万(\d{1,4})(?![\d.%万亿])", s):                    # 26万2000 = 262000
        take(m, {"种类": "数", "值": _r(int(m.group(1)) * 1e4 + int(m.group(2))), "单位": "万"})
    for m in re.finditer(NUM + r"(多|余)?(万亿|亿|万)", s):
        take(m, {"种类": "数", "值": _r(_num(m.group(1)) * CN_MULT[m.group(3)]), "单位": m.group(3)})
    if english:
        for m in re.finditer(r"\$?" + NUM + r"-?(trillion|billion|million|thousand|tn|bn|mn|t|b|m|k)(?![a-z])",
                             s, flags=re.I):
            take(m, {"种类": "数", "值": _r(_num(m.group(1)) * EN_MULT[m.group(2).lower()])})
    for m in re.finditer(NUM, s):
        take(m, {"种类": "数", "值": _r(_num(m.group(1)))})
    for x in out:                                         # 字面：数字连同后面一个字，人工看时用
        b = x["位置"] + len(x["原文"])
        x["字面"] = x["原文"] + s[b:b + 1]
        x["后面"] = s[b:b + 6]
    return out


def strong(x):
    """找不到就必须改的数字：日期、钟点、版本号、年月、百分比、带万亿的金额、小数、10 以上、带强单位的。"""
    if x["种类"] in ("日期", "钟点", "版本", "年", "月", "百分比", "分数"):
        return True
    if x["种类"] == "序数":
        return False
    v = x["值"]
    return (x.get("单位") is not None or v != int(v) or v >= 10
            or any(x["后面"].lstrip("多余约").startswith(u) for u in STRONG_UNITS))


# ---------------------------------------------------------------- 事件卡


def load_cards(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return d["cards"] if isinstance(d, dict) and "cards" in d else d


def card_strings(cards):
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if str(k).startswith("_") or k == "url":
                    continue
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)
        elif isinstance(o, (str, int, float)):
            yield str(o)
    for c in cards:
        yield from walk(c)


class Evidence:
    """事件卡里能当依据的东西：数字集合、去空白的全文、英文词。"""

    def __init__(self, cards):
        strs = list(card_strings(cards))
        self.flat = "".join(prepare(s) for s in strs)
        self.quote_text = PUNCT.sub("", self.flat.lower())
        self.latin = " " + re.sub(r"\s+", " ", " ".join(
            unicodedata.normalize("NFKC", s).replace("’", "'").replace("-", " ") for s in strs)).lower() + " "
        self.vals = {"日期": set(), "钟点": set(), "年": set(), "月": set(), "百分比": set(), "数": set()}
        for s in strs:
            for x in numbers_in(prepare(s), english=True):
                k = x["种类"]
                if k == "日期":
                    self.vals["日期"].add(x["值"])
                    self.vals["月"].add(x["值"][0])
                    if x.get("年"):
                        self.vals["年"].add(x["年"])
                elif k in self.vals:
                    self.vals[k].add(x["值"])

    def has_number(self, x):
        k = x["种类"]
        if k in ("分数", "序数", "版本"):
            return x["值"] in self.flat
        if k in self.vals and x["值"] in self.vals[k]:
            return True
        return x["字面"] in self.flat if not strong(x) else False

    def has_quote(self, q):
        return PUNCT.sub("", prepare(q).lower()) in self.quote_text

    def has_latin(self, phrase):
        p = re.sub(r"\s+", " ", phrase.replace("’", "'").replace("-", " ")).lower().strip(" .'")
        if f" {p} " in self.latin or p in self.latin:
            return []
        missing = []
        for t in p.split(" "):
            t = t.strip(".'")
            if not t or re.fullmatch(r"[\d.]+", t):
                continue
            forms = {t, t.rstrip("s"), t + "s", t.removesuffix("'s")}
            if not any(re.search(r"(?<![a-z0-9])" + re.escape(f) + r"(?![a-z0-9])", self.latin) for f in forms):
                missing.append(t)
        return missing


# ---------------------------------------------------------------- 稿子


def body_lines(text):
    """正文逐行：[(行号, 文字)]，注释、标题、备注行已去掉。"""
    return [(i + 1, ln) for i, ln in enumerate(body_mask(text).split("\n")) if ln.strip()]


def chapter_of_lines(text):
    """每一行属于哪一章（## 章名；注释里的不算）：{行号: 章名}。"""
    plain = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    out, ch = {}, None
    for i, ln in enumerate(plain.split("\n"), 1):
        m = re.match(r"^\s*##\s+(.+?)\s*#*$", ln)
        if m and not ln.strip().startswith("###"):
            ch = m.group(1).strip()
        out[i] = ch
    return out


def intro_spans(lines, chapters):
    """开场那一章里的自我介绍句：含"我是 Shirley""我是 Dylan"的那一句（到句号、问号、叹号为止），每个名字只算第一次。
    返回 {行号: [(起, 止), …]}，这些范围里的"我"不报。"""
    spans, used = {}, set()
    for no, ln in lines:
        if chapters.get(no) != INTRO_CHAPTER:
            continue
        for m in re.finditer(r"[^。！？!?]+[。！？!?]*", ln):
            hit = re.search(r"我是\s*(" + "|".join(HOSTS) + r")", m.group(0))
            if hit and hit.group(1) not in used:
                used.add(hit.group(1))
                spans.setdefault(no, []).append((m.start(), m.end()))
    return spans


def check_dialog(text):
    """对谈稿：格式、附和、轮次长度、称呼、两人各说了多少。"""
    must, look = [], []
    for r in dialog_problems(text):
        must.append({"行": r["行"], "类": r["种类"], "原文": r["原文"], "说明": r["说明"]})
    for r in dialog_tone_notes(text):
        look.append({"行": r["行"], "类": r["种类"], "原文": r["原文"], "说明": r["说明"]})
    turns = dialog_turns(text)
    share = {"甲": 0, "乙": 0}
    for no, ch, sp, body in turns:
        share[sp] += len(re.findall(r"[一-鿿]", body))
        bare = re.sub(r"[\s，。、；：！？,.;:!?—…]", "", body)
        if bare in FILLER:
            must.append({"行": no, "类": "对谈", "原文": body, "说明": "只有附和的一轮：要么删掉，要么带上新内容"})
        n = len([x for x in re.split(r"[。！？!?]+", body) if x.strip()])
        if n > TURN_SENTENCES_MAX:
            look.append({"行": no, "类": "对谈", "原文": body[:16] + "…", "说明": f"这一轮 {n} 句，超过 {TURN_SENTENCES_MAX} 句"})
        for w in ADDRESS:
            if w in body:
                look.append({"行": no, "类": "对谈", "原文": w, "说明": "像在互相称呼：对谈里叫名字可以，不叫搭档、老师"})
    info = {"轮数": len(turns), "甲的字数": share["甲"], "乙的字数": share["乙"]}
    return must, look, info


def day_type(text, dialog=None):
    """这份稿子按哪一天的规则：对谈稿 → 周日；有"深度"开头的章 → 周六；其余 → 日常。"""
    if dialog if dialog is not None else is_dialog(text):
        return "周日"
    titles = [m.group(1).strip() for m in re.finditer(r"^##\s+(.+?)\s*$", re.sub(r"<!--.*?-->", "", text, flags=re.S), re.M)]
    return "周六" if any(t.startswith("深度") for t in titles) else "日常"


def estimate_length(text, dialog, day=None):
    """按对应写稿提示词的"成片时长分钟"判长短，估法和配音程序同一套。返回 {"哪一天", "规则", "区间分钟", "估成片分钟", "符合"}。"""
    import tts       # noqa: E402  （在函数里导入：只判长短时才要）
    day = day or day_type(text, dialog)
    rp = Path(day) if str(day).endswith(".md") else tts.day_rules_path(day)
    rng = tts.duration_rules(rp)
    if dialog:
        import dialog_tts as D   # noqa: E402  （只读调用，接口不变）
        chapters, _ = D.parse_dialog(text)
        speakers, gaps, look = D.load_pairing()
        units = D.plan_units(chapters, speakers, D.load_dialog_styles(text), palette=True)
        secs = D.estimate_dialog(units, chapters, speakers, gaps, look, "v3")["成片秒数"]
    else:
        secs = tts.estimate_script(text)["成片秒数"]
    mins = round(secs / 60, 1)
    exact = secs / 60          # 判"符合"用不四舍五入的分钟数，和配音程序 tts.check_duration 一样（11-06 晚改：14.96 分钟这里原来算 15.0、过了，配音前却被拦下）
    return {"哪一天": day, "规则": rp.name, "区间分钟": rng, "估成片分钟": mins, "精确分钟": round(exact, 3),
            "符合": None if rng is None else rng[0] <= exact <= rng[1]}


def check(text, ev, day=None):
    must, look, info = [], [], {}
    lines = body_lines(text)
    dialog = is_dialog(text)
    if dialog:
        m2, l2, i2 = check_dialog(text)
        must += m2
        look += l2
        info.update(i2)
    for no, ln in lines:
        # 英文名、型号：整段对照事件卡；里面的数字（iOS 27.3 的 27.3）不再当数字查
        for m in LATIN_PHRASE.finditer(ln):
            phrase = " ".join(t for t in m.group(0).split() if t.strip(".,'’") not in HOSTS)   # 主播名字不查事件卡
            miss = ev.has_latin(phrase) if phrase else []
            if miss:
                must.append({"行": no, "类": "英文名", "原文": m.group(0),
                             "说明": f"事件卡里找不到：{'、'.join(miss)}"})
        masked = LATIN_PHRASE.sub(lambda m: "□" * len(m.group(0)), ln)
        for x in numbers_in(prepare(masked)):
            if ev.has_number(x):
                continue
            row = {"行": no, "类": "数字", "原文": x["原文"], "说明": f"{x['种类']}，前后：{x['字面']}…"}
            (must if strong(x) else look).append(row)
        for m in QUOTE.finditer(ln):
            q = next(g for g in m.groups() if g)
            if not ev.has_quote(q):
                must.append({"行": no, "类": "引语", "原文": q, "说明": "事件卡里找不到这句原话"})

    # 口吻
    chapters = chapter_of_lines(text)
    intro = intro_spans(lines, chapters)
    for no, ln in lines:
        for m in re.finditer(r"我(?!们)", ln):
            if any(a <= m.start() < b for a, b in intro.get(no, [])):
                continue                      # 开场自我介绍那一句（"我是 Shirley""我是 Dylan"）
            again = re.match(r"我是\s*(" + "|".join(HOSTS) + r")", ln[m.start():])
            must.append({"行": no, "类": "口吻", "原文": ln[max(0, m.start() - 8):m.end() + 8],
                         "说明": ('自我介绍只在开场说一次，别处不说"我是…"' if again else '主播只说"我们"，不说"我"')})
        if not dialog and chapters.get(no) not in NAME_CHAPTERS:      # 对谈稿里两人互称名字正常，不提醒
            for h in HOSTS:
                if h in ln:
                    look.append({"行": no, "类": "口吻", "原文": h, "说明": "单人稿里主播名字只在开场、结尾出现"})
        for w in ANNOUNCE:
            if w in ln:
                must.append({"行": no, "类": "口吻", "原文": w, "说明": "口播里不报幕"})
        for w in HYPE:
            if w in ln:
                must.append({"行": no, "类": "口吻", "原文": w, "说明": "写作指南禁用的夸张词"})
        for p in AI_CLAIM:
            for m in re.finditer(p, ln):
                must.append({"行": no, "类": "口吻", "原文": m.group(0),
                             "说明": "AI 声明只放节目说明和网页，不进口播"})
        for p in EXPERIENCE:
            for m in re.finditer(p, ln):
                look.append({"行": no, "类": "口吻", "原文": m.group(0), "说明": "像在编亲身经历，看一下"})
        if "我们之前聊过" in ln:
            look.append({"行": no, "类": "口吻", "原文": "我们之前聊过", "说明": "要有往期才能这么说"})
        han = len(re.findall(r"[一-鿿]", ln))
        if han > PARA_MAX:
            look.append({"行": no, "类": "段落", "原文": ln[:16] + "…", "说明": f"这段 {han} 字，超过 {PARA_MAX} 字"})
    body = "\n".join(ln for _, ln in lines)
    n_und = body.count(UNDERSTAND)
    if not UNDERSTAND_RANGE[0] <= n_und <= UNDERSTAND_RANGE[1]:
        must.append({"行": 0, "类": "口吻", "原文": UNDERSTAND,
                     "说明": f"出现 {n_und} 次，指令要求每期 {UNDERSTAND_RANGE[0]}–{UNDERSTAND_RANGE[1]} 次"})
    han_total = len(re.findall(r"[一-鿿]", body))
    est = estimate_length(text, dialog, day)
    rng = est["区间分钟"]
    info.update({"汉字数": han_total, UNDERSTAND + "次数": n_und, "时长估算": est,
                 "长度": (f"估成片约 {est['估成片分钟']} 分钟，{est['哪一天']}的区间 {rng[0]:g}–{rng[1]:g} 分钟，"
                        + ("符合" if est["符合"] else "不在区间里")) if rng else
                 f"估成片约 {est['估成片分钟']} 分钟；{est['规则']} 里没有\"成片时长分钟\"，不判"})
    if rng and not est["符合"]:
        look.append({"行": 0, "类": "长度", "原文": f"约 {est['精确分钟']:.2f} 分钟",
                     "说明": f"不在 {est['哪一天']}的 {rng[0]:g}–{rng[1]:g} 分钟以内（{est['规则']}\"程序检查\"；配音前会被拦下）"})
    for k in ("我们注意到", "在我们看来", "我们比较好奇的是", "我们之前聊过"):
        info[k + "次数"] = body.count(k)
    return {"要改": must, "请人工看": look, "概况": info}


def report(path, res):
    out = [f"稿子核对：{path}"]
    i = res["概况"]
    if "轮数" in i:
        out.append(f"  对谈稿：{i['轮数']} 轮；甲 {i['甲的字数']} 字，乙 {i['乙的字数']} 字")
    out.append(f"  汉字 {i['汉字数']}；{i['长度']}；\"我们的理解是\" {i[UNDERSTAND + '次数']} 次；"
               + "；".join(f"\"{k[:-2]}\" {v} 次" for k, v in i.items()
                          if k.endswith("次数") and k != UNDERSTAND + "次数" and v))
    for title, key in (("✗ 要改", "要改"), ("? 请人工看", "请人工看")):
        rows = res[key]
        if rows:
            out.append(f"{title}（{len(rows)} 处）：")
            for r in sorted(rows, key=lambda r: r["行"]):
                where = f"第 {r['行']} 行" if r["行"] else "全稿"
                out.append(f"  {where}  [{r['类']}] {r['原文']} —— {r['说明']}")
    if not res["要改"]:
        out.append("✓ 数字、引语、英文名都能在事件卡里找到，口吻没有越界")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="稿子核对（用法见文件开头）")
    ap.add_argument("script", help="口播稿（Markdown）")
    ap.add_argument("--cards", required=True, help="cards_写稿用.json 或 写稿输入.json")
    ap.add_argument("--json", action="store_true", help="结果输出成 JSON")
    ap.add_argument("--day-type", help="按哪一天判长短：日常／周六／周日，或写稿提示词路径；不给就自动认（对谈稿＝周日，有\"深度\"章＝周六）")
    a = ap.parse_args(argv)
    ev = Evidence(load_cards(a.cards))
    res = check(Path(a.script).read_text(encoding="utf-8"), ev, day=a.day_type)
    print(json.dumps(res, ensure_ascii=False, indent=1) if a.json else report(a.script, res))
    return 1 if res["要改"] else 0


if __name__ == "__main__":
    sys.exit(main())
