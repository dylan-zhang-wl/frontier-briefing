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

11-28 维护改（11-25 审片：pypinyin 给"才"列了罕见的 zai 读音，"在过冬→才果冻"被判成同音）：多音字逐字比时，
一个字只用它的默认读音和 pypinyin 自带词组库里真用到的读音（common_readings），只在字典里挂着、
没有哪个词这样念的罕见读音不算（才 zai、也 yi、可 ge）。长 zhang/chang、校 xiao/jiao、地 di/de、重 zhong/chong 都留着。
"""
import re
import sys

sys.dont_write_bytecode = True

try:
    from pypinyin import Style, lazy_pinyin, pinyin
except Exception:              # 没装就说清楚，别让审片误以为"同音"
    pinyin = lazy_pinyin = None

HAN = re.compile(r"[一-鿿]")
_USED = None                   # 字 → pypinyin 词组库里这个字用到的读音（不带声调），第一次用时建
LATIN_DIGIT = re.compile(r"[A-Za-z0-9０-９]")
SAME, DIFF, LATIN = "同音（不带声调）", "不同音", "含英文或数字"


def _han(s):
    return "".join(HAN.findall(s or ""))


def common_readings(ch):
    """一个字算数的读音（不带声调）：默认读音，加 pypinyin 词组库（phrases_dict）里这个字真用到的读音。
    pypinyin 开多音字（heteronym）时把字典里挂着的读音全给出来，包括"才"zai 这类没有哪个词这样念的（11-25 才/在）；
    pypinyin 没有"常用读音"的开关，官方文档的办法是 load_single_dict 改全局字典，会连带别的程序，所以在这里筛。
    筛完是空的（不会出现：默认读音总在）就用全部读音。"""
    global _USED
    if _USED is None:
        from pypinyin.phrases_dict import phrases_dict
        from pypinyin.style import convert
        _USED = {}
        for w, pys in phrases_dict.items():
            if len(w) == len(pys):
                for c, py in zip(w, pys):
                    _USED.setdefault(c, set()).add(convert(py[0], style=Style.NORMAL, strict=False))
    allr = pinyin(ch, style=Style.NORMAL, heteronym=True)[0]
    keep = {r for r in allr if r == allr[0] or r in _USED.get(ch, ())}
    return keep or set(allr)


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
    # 罕见读音不算（11-28 加）：逐字只留 common_readings 里有的
    return all(set(px) & common_readings(x) & set(py) & common_readings(y) for x, y, px, py in zip(a, b, pa, pb))


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
