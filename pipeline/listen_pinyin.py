#!/usr/bin/env python3
"""审片给"请你耳听"分拣时用：原稿和转写只差同音字吗（按不带声调的拼音比）。

11-14 维护加（经验库第 67 件）。11-13 用户耳听：会话→绘画、即时→及时、梳理→书里、词元→磁源、博客→播客
这类拼音一样（声调可以不同）的，配音都没念错，是转写模型选错了字；声调靠模型选字推出来，不可靠。
所以审片判"多半转写听错"的条件改成"不带声调的拼音一样"。真念错的（微软→美软、传奇→禅奇、字节→智节、
随后→最后、这起→这些）都错在声母或韵母上，这个工具会报"不同音"。

用法（审片在云端也这样用，项目环境里有 pypinyin）：
    ~/.venvs/frontier-daily/bin/python pipeline/listen_pinyin.py 会话 绘画 微软 美软 3.8 3.0
每两个一对（原稿、转写），每对打一行：同音（不带声调）／不同音／含英文或数字。
含英文字母或数字的不按拼音比：数字、版本号不同就是不同（3.8→3.0），英文名拼法不同按审片 B2 的"拿不准"处理。
只读不写，不联网、不调模型。
"""
import re
import sys

sys.dont_write_bytecode = True

try:
    from pypinyin import Style, lazy_pinyin, pinyin
except Exception:              # 没装就说清楚，别让审片误以为"同音"
    pinyin = lazy_pinyin = None

HAN = re.compile(r"[一-鿿]")
LATIN_DIGIT = re.compile(r"[A-Za-z0-9０-９]")
SAME, DIFF, LATIN = "同音（不带声调）", "不同音", "含英文或数字"


def _han(s):
    return "".join(HAN.findall(s or ""))


def same_toneless(a, b):
    """两段中文（只看汉字）不带声调的拼音一样吗。多音字：整词读法一样，或者逐字有一个读法对得上，都算一样
    （"周期长"和"周期厂"都有 chang）。字数不同一律算不一样（"援引"→"引用"是换了词，不是同音）。"""
    if pinyin is None:
        raise RuntimeError("没装 pypinyin：用 ~/.venvs/frontier-daily/bin/python 跑")
    a, b = _han(a), _han(b)
    if not a or len(a) != len(b):
        return False
    if a == b:
        return True
    if lazy_pinyin(a) == lazy_pinyin(b):
        return True
    pa = pinyin(a, style=Style.NORMAL, heteronym=True)
    pb = pinyin(b, style=Style.NORMAL, heteronym=True)
    return all(set(x) & set(y) for x, y in zip(pa, pb))


def judge(a, b):
    """一对（原稿、转写）→ SAME / DIFF / LATIN。"""
    if LATIN_DIGIT.search(a or "") or LATIN_DIGIT.search(b or ""):
        return SAME if (a or "").strip().lower() == (b or "").strip().lower() else LATIN
    return SAME if same_toneless(a, b) else DIFF


def main(argv):
    if len(argv) < 2 or len(argv) % 2:
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2
    for a, b in zip(argv[0::2], argv[1::2]):
        r = judge(a, b)
        extra = ""
        if r != LATIN and pinyin is not None:
            extra = "  [%s | %s]" % (" ".join(lazy_pinyin(_han(a))), " ".join(lazy_pinyin(_han(b))))
        print("%s → %s：%s%s" % (a, b, r, extra))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
