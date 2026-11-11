# -*- coding: utf-8 -*-
"""中文按词组换行（v3.1）：组装时在词组之间插入看不见的换行点 U+200B（零宽空格），
网页上配合 CSS 的 word-break: keep-all，一行只在这些点、空格和标点处断开，不会把“融资”拆成两行。

怎么切：
1. BudouX（Google 出的开源断行工具，Apache-2.0，用它的简体中文模型）先按“词组”切。
2. 它的中文模型偶尔会切进词里面（10-31 实测：“融资现寻求”切成 融｜资现，“数据中心”切成 数据｜中｜心，
   “开放权重”切成 开｜放权｜重），所以再用 jieba（开源中文分词，MIT）把关：只保留 jieba 也认为是词边界的切点。
3. 几条排版规矩：书名号《》里不切；10 个字以内的引号“…”里不切；括号开头后、标点前不切；英文单词和数字内部不切；
   空格旁不加（空格本来就能换行）；数字和后面的单位、日期的“月”和日子之间不断（那个空格换成不换行空格）。
4. 上标记号 [^s07] 和粗体记号 ** 原样保留，不往里面插。

依赖（只在组装时用，网页运行时不需要）：budoux、jieba，装在 ~/.venvs/frontier-daily：
    uv pip install --python ~/.venvs/frontier-daily/bin/python budoux jieba
"""
import logging
import os
import re

WJ = "\u2060"     # 连接符（word joiner）：看不见，表示“这里不许换行”
ZW = "\u200b"     # 零宽空格：看不见，只表示“这里可以换行”
NBSP = "\u00a0"   # 不换行空格：看起来是空格，但不在这里换行
TOKEN = re.compile(r"(\[\^s\d+\]|\*\*)")
CJK = re.compile(r"[\u3400-\u9fff]")
OPEN = "（「『“‘《〈【〔([{"
CLOSE = "）」』”’》〉】〕)]}，。、；：！？…—·%,.;:!?"
LATIN = re.compile(r"[A-Za-z0-9'’.\-_&+/]")   # 英文单词、数字和词里面的撇号、连字符、小数点
MONEY_UNIT = re.compile(r"(?:美|欧|日|港|人民)?元|英镑|美金")

_parser = None
_jieba = None
_NAMES = None   # 不许从中间断开的名字（v3.2）：来自《英文名表》《读音表》里的中文写法，如 IT之家、36氪、SK 海力士、Apple 智能


def _load_names():
    """读《英文名表》《读音表》里所有带中文的多字名字；含西文和中文混写的（IT之家、Apple 智能）也在内。"""
    global _NAMES
    if _NAMES is not None:
        return _NAMES
    names = set()
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        import yaml
        for fn in ("英文名表.yaml", "读音表.yaml"):
            p = os.path.join(root, "pipeline", "prompts", fn)
            if not os.path.isfile(p):
                continue

            def walk(x, key=""):
                if isinstance(x, dict):
                    for k, v in x.items():
                        walk(v, k)
                elif isinstance(x, list):
                    for v in x:
                        walk(v, key)
                elif isinstance(x, str) and key in ("zh", "写法", "也可写", "音译", "") and len(x) <= 16:
                    names.add(x.strip())
            walk(yaml.safe_load(open(p, encoding="utf-8")))
    except ImportError:
        pass
    # 只留：带中文、至少两个字、而且不是整句话的名字
    names = {n.strip("《》") for n in names if CJK.search(n) and len(n.strip("《》")) >= 2 and not re.search(r"[，。；：！？]", n)}
    _NAMES = sorted(names, key=len, reverse=True)
    return _NAMES
STATS = {"strings": 0, "budoux": 0, "kept": 0, "extra": 0}


def load(extra_words=()):
    """第一次用时载入 BudouX 和 jieba；extra_words 是要整体保留的词（如今日一词、事件卡里的术语）。"""
    global _parser, _jieba
    if _parser is None:
        try:
            import budoux
            import jieba
        except ImportError:
            raise SystemExit("缺少断行工具：请运行 uv pip install --python ~/.venvs/frontier-daily/bin/python budoux jieba")
        _parser = budoux.load_default_simplified_chinese_parser()
        jieba.setLogLevel(logging.WARNING)
        cache = os.path.expanduser("~/.cache/frontier-daily/jieba")   # jieba 的词典缓存放在 iCloud 之外
        os.makedirs(cache, exist_ok=True)
        jieba.dt.tmp_dir = cache
        _jieba = jieba
    for w in extra_words:
        w = (w or "").strip()
        if len(w) >= 2 and CJK.search(w) and not re.search(r"\s", w):
            _jieba.add_word(w, freq=200000)


def _cuts(chunks):
    out, pos = set(), 0
    for c in chunks[:-1]:
        pos += len(c)
        out.add(pos)
    return out


def _protected(seg):
    """不许切的位置：书名号里、短引号里。"""
    no = set()
    for m in re.finditer(r"《[^《》]*》", seg):
        no.update(range(m.start() + 1, m.end()))
    for m in re.finditer(r"[“「‘]([^“”「」‘’]{1,10})[”」’]", seg):
        no.update(range(m.start() + 1, m.end()))
    for m in re.finditer(r"第[〇一二三四五六七八九十百千0-9]+[大小多高低]?", seg):   # 第二大、第三
        no.update(range(m.start() + 1, m.end()))
    # v3.2：名字中间不切——表里的名字（IT之家、36氪、SK 海力士……），以及西文紧贴中文、中间没空格的短名（IT之家这一类）
    for n in _load_names():
        k = n.replace(" ", NBSP)
        for m in re.finditer(re.escape(k), seg):
            no.update(range(m.start() + 1, m.end()))
    for m in re.finditer(r"(?<![A-Za-z0-9])[A-Za-z0-9]{1,4}[\u4e00-\u9fff]{1,2}(?=[^\u4e00-\u9fff]|$)", seg):
        no.update(range(m.start() + 1, m.end()))
    return no


def _ok(seg, i, no):
    a, b = seg[i - 1], seg[i]
    if i in no or a.isspace() or b.isspace() or a in OPEN or b in CLOSE:
        return False
    if LATIN.match(a) and LATIN.match(b):   # 英文单词、数字内部（Tom's、GLM-5.3、1.25）不切
        return False
    if a == WJ or b == WJ:   # 连接符两边都不切
        return False
    if a == "," and b.isdigit() and i >= 2 and seg[i - 2].isdigit():   # v3.2：千分位 1,000 不在逗号后折行
        return False
    if b in "后前时" and CJK.match(a):   # v3.2：“上市后”“发布前”这类不把“后/前/时”单独甩到下一行
        return False
    if a in "万亿千百" and MONEY_UNIT.match(seg, i):
        return False
    return True


LONG = 7   # 一个词组超过 7 个字宽时，组内的词边界也可以换行（窄的小卡片、手机上放得下；词本身仍不拆）


def _width(t):
    return sum(1 if CJK.match(c) or "\u3000" <= c <= "\u303f" or "\uff00" <= c <= "\uffef" or c in "“”‘’" else 0.5
               for c in t)


def _segment(seg):
    if not CJK.search(seg):
        return seg
    bud = _cuts(_parser.parse(seg))
    words = _cuts(list(_jieba.cut(seg, HMM=True)))
    no = _protected(seg)
    keep = sorted(i for i in bud & words if _ok(seg, i, no))
    kept0 = len(keep)
    # 太长的词组（如“（对比数据中心全天候运行）”）里再按词边界补换行点
    edges, extra = [0] + keep + [len(seg)], []
    for a, b in zip(edges, edges[1:]):
        if _width(seg[a:b]) > LONG:
            extra += [i for i in words if a < i < b and _ok(seg, i, no)]
    keep = sorted(set(keep) | set(extra))
    STATS["budoux"] += len(bud)
    STATS["kept"] += kept0
    STATS["extra"] += len(keep) - kept0
    out, last = [], 0
    for i in keep:
        out.append(seg[last:i])
        last = i
    out.append(seg[last:])
    return ZW.join(out)


def glue(s):
    """数字和单位、日期之间的空格换成不换行空格：200 亿、11 小时、10 月 31 日、iOS 27.3 不会被拆到两行。"""
    s = re.sub(r"(?<![A-Za-z0-9.,])([0-9][0-9.,]*%?)[ ](?=[\u4e00-\u9fff])", lambda m: m.group(1) + NBSP, s)   # 200 亿美元、5% 的（Kimi K3 这类型号不算）
    s = re.sub(r"(?<=[第年月])[ ](?=[0-9])", NBSP, s)                    # 第 3、10 月 31 日
    s = re.sub(r"(?<=[A-Za-z])[ ](?=[0-9][0-9.]*(?![0-9.]*\s*[年月日号]))", NBSP, s)   # iOS 27.3、Large 4（日期不算）
    # 两个词的英文名（Claude Code、Sam Altman、The Verge）不拆到两行；三个词以上的长名照常在空格处换行，免得一整串放不下
    s = re.sub(r"(?<![A-Za-z0-9] )(?<![A-Za-z0-9])([A-Z][A-Za-z0-9'’.\-]*) ([A-Z][A-Za-z0-9'’.\-]*)(?![A-Za-z0-9'’.\-])(?![ \u00a0][A-Z])",
               lambda m: m.group(1) + NBSP + m.group(2), s)
    for n in _load_names():   # 表里带空格的名字（SK 海力士、广东 7-ELEVEN）整体不拆
        if " " in n and n in s:
            s = s.replace(n, n.replace(" ", NBSP))
    s = re.sub(r"(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])", "-" + WJ, s)
    s = re.sub(r"(?<![A-Za-z0-9])([A-Z]{1,3}) (?=[类级型档轮])", lambda m: m.group(1) + NBSP, s)   # v3.2：F 类、BB 级不拆开
    s = re.sub(r"(?<=[\u4e00-\u9fff])(?=“[^“”]{1,8}”)", WJ, s)   # v3.2：短引号前不折行，免得一行以“开头、引号悬在行首   # GLM-5.3、Qwen4-27B：连字符后不折行（WJ 看不见，只表示“这里不许断”）
    return s


def phrase_breaks(s):
    """给一段中文加上词组换行点。没有中文的字符串原样返回。"""
    if not isinstance(s, str) or not CJK.search(s):
        return s
    if _parser is None:
        load()
    STATS["strings"] += 1
    parts = TOKEN.split(s.replace(ZW, ""))
    out = "".join(p if (TOKEN.fullmatch(p) or not p) else _segment(glue(p)) for p in parts)
    return re.sub(ZW + r"(?=\[\^s\d+\])", "", out)   # 上标前面不留换行点（上标要和前一个字粘在一起）
