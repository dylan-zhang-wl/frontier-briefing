# -*- coding: utf-8 -*-
"""西文引号和撇号改成印刷体（v3.2）：组装时对网页上显示的所有文字做一遍，只改排印，不改字词。

    Tom's        → Tom’s           （词中撇号）
    'later'      → ‘later’         （英文单引号）
    "tampered"   → “tampered”      （双引号；中文里的直引号也换成“”，中文本来就用这对弯引号）
    investors'   → investors’

不动的：网址（http…、www.…）、反引号里的代码、上标记号 [^s07]、带 = { } < > | \\ 的“代码样”片段；
中文语境里的直单引号（中文不用 ' 作撇号）原样留着。
已经是弯引号的不再处理，所以重复运行结果不变。

单独运行这个文件会跑一组小例子自检：  ~/.venvs/frontier-daily/bin/python site/tools/typo_quotes.py
"""
import re

_PROTECT = re.compile(r"https?://\S+|www\.\S+|`[^`]*`|\[\^s\d+\]|<[^<>]*>|\S*[={}<>|\\]\S*")
_PH = "%d"
_PH_RE = re.compile("(\\d+)")
_CJK = "㐀-鿿　-〿＀-￯"

_RULES = [
    # 年代缩写 '90s → ’90s
    (re.compile(r"'(?=\d0s\b)"), "’"),
    # 词中撇号：Tom's、don't、Cursor's
    (re.compile(r"(?<=[A-Za-z0-9])'(?=[A-Za-z])"), "’"),
    # 英文单引号开头：前面是开头、空白、括号、破折号、斜杠或双引号，后面紧跟字母数字
    (re.compile(r"(^|[\s(\[{“\"—–/\-])'(?=[A-Za-z0-9])"), r"\1‘"),
    # 其余跟在西文后面的单引号：收尾或复数所有格（investors'）
    (re.compile(r"(?<=[A-Za-z0-9.,;:!?%)\]…’])'"), "’"),
]


def _doubles(t):
    """直双引号成对处理：一开一合交替；开引号后面必须紧跟文字，否则当作收尾。"""
    out, is_open = [], False
    for i, ch in enumerate(t):
        if ch != '"':
            out.append(ch)
            continue
        nxt = t[i + 1] if i + 1 < len(t) else ""
        if not is_open and nxt and not nxt.isspace() and nxt not in ".,;:!?)]}，。；：！？）":
            out.append("“")
            is_open = True
        else:
            out.append("”")
            is_open = False
    return "".join(out)


def smart(s):
    """一段文字里的直引号、直撇号 → 弯引号。没有 ' 或 " 的文字原样返回。"""
    if not isinstance(s, str) or ("'" not in s and '"' not in s):
        return s
    kept = []

    def hide(m):
        kept.append(m.group(0))
        return _PH % (len(kept) - 1)
    t = _PROTECT.sub(hide, s)
    for pat, rep in _RULES:
        t = pat.sub(rep, t)
    if '"' in t:
        t = _doubles(t)
    return _PH_RE.sub(lambda m: kept[int(m.group(1))], t)


# 这些键的值不是给人看的文字（网址、文件路径、编号、样式…），整棵子树都不碰
SKIP_KEYS = {"url", "src", "src_sm", "file", "audio", "depth", "peaks", "fonts_css", "href", "id", "ev", "story",
             "kind", "status", "region", "date", "type", "tpl", "cite", "cites", "sid", "layout", "accent",
             "css", "style", "svg", "path", "d", "html", "class", "k"}


def tree(x, key="", stats=None):
    """递归处理一整份数据（dict / list / str），返回新的一份；stats 记改了几段文字。"""
    if isinstance(x, dict):
        return {k: (v if k in SKIP_KEYS else tree(v, k, stats)) for k, v in x.items()}
    if isinstance(x, list):
        return [tree(v, key, stats) for v in x]
    if isinstance(x, str):
        y = smart(x)
        if stats is not None and y != x:
            stats["changed"] = stats.get("changed", 0) + 1
        return y
    return x


if __name__ == "__main__":
    cases = [
        ("Tom's Hardware", "Tom’s Hardware"),
        ("a beta 'later this month'", "a beta ‘later this month’"),
        ('publish a "tampered" copy', "publish a “tampered” copy"),
        ("Mistral Large 4 'Le Chonk' arrives", "Mistral Large 4 ‘Le Chonk’ arrives"),
        ("the investors' money", "the investors’ money"),
        ("据 Tom's Hardware 报道，他说\"相当糟糕\"。", "据 Tom’s Hardware 报道，他说“相当糟糕”。"),
        ("see https://x.com/a'b?q=\"c\" now", "see https://x.com/a'b?q=\"c\" now"),
        ("run `echo 'hi'` first", "run `echo 'hi'` first"),
        ("already “curly” and Tom’s", "already “curly” and Tom’s"),
        ("in the '90s", "in the ’90s"),
        ("(Cursor: 'at most')", "(Cursor: ‘at most’)"),
        ("他说'好'", "他说'好'"),
        ("Who's who[^s07]", "Who’s who[^s07]"),
    ]
    bad = 0
    for a, b in cases:
        got = smart(a)
        ok = got == b
        bad += not ok
        print("OK " if ok else "BAD", repr(a), "→", repr(got))
    raise SystemExit(1 if bad else 0)
