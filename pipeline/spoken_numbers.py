#!/usr/bin/env python3
"""口播稿里的阿拉伯数字 → 念法（配音前自动转；字幕和画面仍显示阿拉伯数字）。

为什么：视频旁白要和字幕是同一份文字，字幕要显示 28.58%、300 亿美元、10 月 31 日；
配音模型最稳的读法是汉字（"百分之二十八点五八""三百亿美元""十月三十一日"）。
所以稿子只写一份（阿拉伯数字），配音前由这里转成念法；对齐时再把时间映射回稿子上的每个字。

只转"数字＋单位"和日期、百分数，其余不动：
    10 月 31 日 → 十月三十一日        12 月 → 十二月
    28.58% → 百分之二十八点五八        47% → 百分之四十七
    300 亿美元 → 三百亿美元            约 200 亿 → 约两百亿        110 亿 → 一百一十亿
    1 万亿 → 一万亿                    5,000 名 → 五千名          18 项 → 十八项
    10 美元 → 十美元                   2 个 → 两个
不转：型号和版本（iOS 27.3、GLM-5.3、千问 4、Qwen4-27B、v3.1）——数字前面紧挨着字母、连字符、点，
或者后面不跟单位，都原样留给配音模型按英文或按字念。
数字和汉字之间为排版加的空格，转完后一并去掉（"跌 28.58%" → "跌百分之二十八点五八"）。

2026-11-02 晚补（年份原来被当成"年"这个量词，"2026 年"念成了"两千零二十六年"）：
    2026 年 → 二零二六年（四位数 1000–2999 后面跟"年"，含"年度""年代""年内"这类）
    2026—2027 年、2026-2027 年、2026 至 2027 年、2026/27 财年 → 二零二六到二零二七年、……二零二六到二七财年
    2026 财年 → 二零二六财年        FY2026 → 二零二六财年
    年数不动：用了 3 年 → 三年，100 年 → 一百年，30 多年 原样；整千的 1000 年、2000 年仍念"一千年""两千年"；
    "距今""长达""历时""持续""过去""近""约""超过"后面的四位数也按年数念。
    年份逐位念，对应表一位对一位（字幕逐字变亮时，"2026"的每一位各自亮）。
另补两处原来会念错的：
    第 2 名 → 第二名（原来是"第两名"：前面有"第"时不念"两"）
    3-5 年、10—20 家、10%-20% → 三到五年、十到二十家、百分之十到百分之二十（原来"-"后面那个数不转，可能念成"减"）
转不了、要写稿的人换写法的（Q3、FY26、不跟"年"的 2026/27、H1）：risky_numbers() 列出来，配音前的检查当提醒报。
播客稿按规矩写读法（"二〇二六年"）：years_to_hanzi() 把阿拉伯数字的年份改成"二〇二六年"，lexicon_check.py 用它。

2026-11-06 补（11-06 播客把"Reflection Beam 501B""Muse Spark Open 816B"念成了 51B、81B）：
    数字＋单位缩写 B、M、K、T（参数量、上下文长度这类）：整数部分三位以上、或带小数的，转成汉字念法再接字母——
    视频旁白的念法：501B → 五百零一 B，816B → 八百一十六 B，1,000B → 一千 B，128K → 一百二十八 K，1.5T → 一点五 T。
    一两位的整数不动（65B、27B、8B、1M）：11-06 视频里"65B"念对了，这类短数字配音念得稳；它们还常出现在型号里
    （Ripple-65B Preview、Qwen4-27B，前面紧挨连字符，本来就不转），不转也让同一期里"65B"和型号里的"65B"念法一致。
    前面紧挨字母、数字、点、连字符、下划线、斜杠的不转（Ripple-65B、W4A4B、v1.5T）；后面紧跟字母、数字、连字符的也不转
    （235B-A22B 这类型号整个留给配音模型）。
    视频旁白：配音前经 spoken() 自动转成"五百零一 B"，字幕仍显示 501B（念的和屏幕上的一个字对一个字）。
    播客稿：按规矩写读法，abbr_to_hanzi() 把稿子里的 501B 改成"五千零一十亿参数"（B＝十亿、T＝万亿、M＝百万、K＝千，
    换成中文的亿、万；B、T 后面没说"参数""词元"的补"参数"），lexicon_check.py 用它（总调度第 7 步自动改）。
    播客不用"五百零一 B"：第 7 步的 script_check 要在事件卡里找到稿子的每个数字，它把事件卡里的 501B 认成 5010 亿，
    稿子写"五百零一 B"会被当成 501、找不到、整个自动运行停下；"五千零一十亿"对得上。只听不看的播客，"五千零一十亿参数"也更好懂。

用法：
    from spoken_numbers import spoken
    text, src = spoken("英特尔跌 28.58%")   # text＝念法；src[i]＝念法第 i 个字对应稿子里的哪一段 (起, 止)
    python pipeline/spoken_numbers.py "10 月 31 日，OpenAI 从 300 亿美元降到约 200 亿"
"""
import re
import sys

DIG = "零一二三四五六七八九"
CJK = re.compile(r"[　-〿㐀-鿿＀-￯]")      # 汉字和中文标点

# 跟在数字后面才转的单位（长的放前面）
UNITS = ("万亿", "亿", "万", "千", "美元", "元", "小时", "分钟", "季度", "月", "日", "年", "天", "周", "名", "项",
         "个", "倍", "家", "台", "款", "位", "次", "人", "岁", "秒", "张", "条", "篇", "件", "种", "所")
LIANG = ("万亿", "亿", "万", "千", "小时", "分钟", "季度", "年", "天", "周", "名", "项", "个", "倍", "家", "台", "款", "位",
         "次", "人", "岁", "秒", "张", "条", "篇", "件", "种", "所")   # 前面是 2 时念"两"（2 月、2 日仍念"二"）
_U = "|".join(UNITS)
_NUM = r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?"
_TO = r"\s*[—–\-~～至到]\s*"                     # 区间的连接：破折号、连字符、波浪号、"至""到"
_YEAR_ALTS = (
    r"FY\s?(?P<fy>[12]\d{3})(?!\d)"                                                 # FY2026
    r"|(?P<r1>[12]\d{3})(?P<rc>\s*[—–\-~～/至到]\s*)(?P<r2>[12]\d{3}|\d{2})(?![\d.])\s*(?=财年|年)"   # 2026—2027 年、2026/27 财年
    r"|(?P<y>[12]\d{3})(?![\d.])\s*(?=财年|年)")                                    # 2026 年、2026 财年
# 数字＋单位缩写（11-06 补）：整数三位以上（可带千分位、小数）或一两位带小数；后面不能再接字母、数字、连字符、下划线、斜杠、"点＋数字"；
# 前面是货币符号的（$501B）不转，留给写稿的人写成"五千零一十亿美元"
ABBR_UNITS = "BMKT"
_ABBR = (r"(?<![$€£¥＄])(?P<ab>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{3,}(?:\.\d+)?|\d{1,2}\.\d+)(?P<abu>[" + ABBR_UNITS + r"])"
         r"(?![A-Za-z0-9\-_/]|\.\d)")
ABBR_PAT = re.compile(r"(?<![A-Za-z0-9.\-_/])" + _ABBR)
PAT = re.compile(
    r"(?<![A-Za-z0-9.\-_/])(?:" + _YEAR_ALTS +
    r"|(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日"                                  # 10 月 31 日
    r"|(?P<q1>\d+(?:\.\d+)?)\s*%?(?P<qc>" + _TO + r")(?P<q2>\d+(?:\.\d+)?)\s*%"    # 10%-20%、10-20%
    r"|(?P<p>\d+(?:\.\d+)?)\s*%"                                                  # 28.58%
    r"|" + _ABBR +                                                                # 501B、1.5T（11-06 补）
    r"|(?P<g1>" + _NUM + r")(?P<gc>" + _TO + r")(?P<g2>" + _NUM + r")\s*(?=(?:" + _U + "))"   # 3-5 年、10—20 家
    r"|(?P<n>" + _NUM + r")\s*(?=(?:" + _U + "))"                                # 300 亿、5,000 名、1 万亿
    r")")
YEAR_PAT = re.compile(r"(?<![A-Za-z0-9.\-_/])(?:" + _YEAR_ALTS + ")")
# 这些词后面的四位数按"年数"念，不按年份（"距今 1500 年""长达 1200 年"）。
# 只收不会和年份连用的词："近""约""超过"不收——"接近 2026 年的两倍""约 2026 年""超过 2025 年全年"都是年份
DURATION_BEFORE = ("距今", "长达", "历时", "持续", "过去", "足足", "整整", "花了", "用了")


def _below_10k(n):
    s, zero = "", False
    for val, u in ((1000, "千"), (100, "百"), (10, "十"), (1, "")):
        d, n = divmod(n, val)
        if d:
            if zero:
                s += "零"
            s += DIG[d] + u
            zero = False
        elif s:
            zero = True
    return s


def int_zh(n):
    """整数念法：110 → 一百一十，18 → 十八，200 → 两百，5000 → 五千，20000 → 两万。"""
    if n == 0:
        return "零"
    if n >= 10 ** 8:
        hi, lo = divmod(n, 10 ** 8)
        return int_zh(hi) + "亿" + (("零" if lo < 10 ** 7 else "") + int_zh(lo) if lo else "")
    if n >= 10 ** 4:
        hi, lo = divmod(n, 10 ** 4)
        s = int_zh(hi) + "万"
        return s + (("零" if lo < 1000 else "") + _below_10k(lo) if lo else "")
    s = _below_10k(n)
    if s.startswith("一十"):
        s = s[1:]
    if n >= 100 and s.startswith("二"):
        s = "两" + s[1:]
    return s


def num_zh(tok, unit="", ordinal=False):
    tok = tok.replace(",", "")
    whole, _, frac = tok.partition(".")
    if not frac and int(whole or 0) == 2 and unit in LIANG and not ordinal:
        return "两"
    return int_zh(int(whole or 0)) + ("点" + "".join(DIG[int(c)] for c in frac) if frac else "")


def abbr_zh(num, letter):
    """数字＋单位缩写的念法：501, B → "五百零一 B"；1.5, T → "一点五 T"（数字念汉字，字母照写，中间一个空格）。"""
    return num_zh(num) + " " + letter


def digits_zh(s, zero="零"):
    """逐位念：2026 → 二零二六（播客稿写法用 zero="〇"：二〇二六）。"""
    return "".join(zero if c == "0" else DIG[int(c)] for c in s)


def _is_year(text, m):
    """YEAR_PAT／PAT 的单个年份那一支：整千（1000、2000）和"距今""长达"这类后面的，按年数念，不算年份。"""
    if not m.group("y"):
        return True
    if int(m.group("y")) % 1000 == 0:
        return False
    return not text[:m.start()].rstrip().endswith(DURATION_BEFORE)


def _year_pieces(m, zero="零"):
    """年份那几支 → [(念法, (起, 止))]：年份一位对一位，连接词（到）对连接那一段，"财年"对"FY"。"""
    out = []

    def digs(g):
        a = m.start(g)
        out.extend((digits_zh(c, zero), (a + i, a + i + 1)) for i, c in enumerate(m.group(g)))
    if m.group("fy"):
        digs("fy")
        out.append(("财年", (m.start(), m.start("fy"))))
    elif m.group("r1"):
        digs("r1")
        out.append(("到", m.span("rc")))
        digs("r2")
    else:
        digs("y")
    return out


def _pieces(text, m):
    """PAT 的一处匹配 → [(念法, (起, 止))]。原有的几种写法（日期、百分数、数字＋单位）整段对整段，和 11-02 以前一样。"""
    whole = (m.start(), m.end())
    ordinal = text[:m.start()].rstrip().endswith("第")          # 第 2 名 → 第二名（不念"两"）
    if (m.group("fy") or m.group("r1") or m.group("y")) and _is_year(text, m):
        return _year_pieces(m)
    if m.group("y"):                                             # 整千、年数：按原来的"数字＋年"念
        return [(num_zh(m.group("y"), "年", ordinal), whole)]
    if m.group("m"):
        return [(int_zh(int(m.group("m"))) + "月" + int_zh(int(m.group("d"))) + "日", whole)]
    if m.group("q1"):
        return [("百分之" + num_zh(m.group("q1")), (m.start(), m.start("qc"))), ("到", m.span("qc")),
                ("百分之" + num_zh(m.group("q2")), (m.end("qc"), m.end()))]
    if m.group("p"):
        return [("百分之" + num_zh(m.group("p")), whole)]
    if m.group("ab"):                                            # 501B → 五百零一 B（11-06 补；播客稿另用 abbr_to_hanzi）
        return [(abbr_zh(m.group("ab"), m.group("abu")), whole)]
    unit = next(u for u in UNITS if text.startswith(u, m.end()))
    if m.group("g1"):
        return [(num_zh(m.group("g1"), unit, ordinal), m.span("g1")), ("到", m.span("gc")),
                (num_zh(m.group("g2"), unit), (m.start("g2"), m.end()))]
    return [(num_zh(m.group("n"), unit, ordinal), whole)]


def spoken(text):
    """稿子 → (念法, 对应表)。对应表 src[i] = 念法第 i 个字来自稿子的 (起, 止) 位置。"""
    out, src, pos = [], [], 0
    for m in PAT.finditer(text):
        for k in range(pos, m.start()):
            out.append(text[k])
            src.append((k, k + 1))
        for r, span in _pieces(text, m):
            for ch in r:
                out.append(ch)
                src.append(span)
        pos = m.end()
    for k in range(pos, len(text)):
        out.append(text[k])
        src.append((k, k + 1))
    # 数字和汉字之间排版用的空格：两边都是汉字（或中文标点）时去掉
    keep_o, keep_s = [], []
    for i, ch in enumerate(out):
        if ch == " " and keep_o and i + 1 < len(out) and CJK.match(keep_o[-1]) and CJK.match(out[i + 1]):
            continue
        keep_o.append(ch)
        keep_s.append(src[i])
    return "".join(keep_o), keep_s


def spoken_script(md):
    """整份 Markdown 稿子：只转正文行（# 标题、> 备注、<!-- 注释 --> 不动）。"""
    lines = []
    for ln in md.split("\n"):
        s = ln.lstrip()
        lines.append(ln if (s.startswith("#") or s.startswith(">") or s.startswith("<!--")) else spoken(ln)[0])
    return "\n".join(lines)


_CJK_CHAR = re.compile(r"[㐀-鿿]")


def years_to_hanzi(text, zero="〇"):
    """播客稿用（2026-11-02 晚加）：阿拉伯数字的年份改成读法——2026 年 → 二〇二六年，2026—2027 年 → 二〇二六到二〇二七年，
    2026 财年／FY2026 → 二〇二六财年。年数（3 年、100 年、30 多年）、整千（2000 年）、"距今""长达"后面的不改。
    年份和前面汉字之间排版用的空格一并去掉（"在 2026 年" → "在二〇二六年"）。返回 (新稿, [{起, 止, 原文, 改成}])，起止是原稿里的位置。"""
    changes = []
    for m in YEAR_PAT.finditer(text):
        if not _is_year(text, m):
            continue
        a, b = m.span()
        if a >= 2 and text[a - 1] == " " and _CJK_CHAR.match(text[a - 2]):
            a -= 1
        new = "".join(r for r, _ in _year_pieces(m, zero))
        word = "" if m.group("fy") else ("财年" if text.startswith("财年", b) else "年")
        if m.group("fy") and b + 1 < len(text) and text[b] == " " and _CJK_CHAR.match(text[b + 1]):
            b += 1                       # "FY2026 和" → "二〇二六财年和"
        changes.append({"起": a, "止": b, "原文": text[a:b], "改成": new,
                        "显示": "%s → %s" % ((text[a:b] + word).strip(), new + word)})
    out = text
    for c in reversed(changes):
        out = out[:c["起"]] + c["改成"] + out[c["止"]:]
    return out, changes


ABBR_MULT = {"K": 10 ** 3, "M": 10 ** 6, "B": 10 ** 9, "T": 10 ** 12}
PARAM_NEAR = ("参数", "词元", "token", "个", "条", "次")   # B、T 后面已经说了这些（或前面 12 个字里说了"参数"），就不补"参数"


def abbr_amount_zh(num, letter):
    """播客稿的读法：501, B → "五千零一十亿"；1.5, T → "一点五万亿"；128, K → "十二万八千"；200, M → "两亿"。"""
    from decimal import Decimal
    v = Decimal(num.replace(",", "")) * ABBR_MULT[letter]

    def zh(x, unit):
        x = x.normalize()
        if x == x.to_integral_value():
            return num_zh(str(int(x)), unit) + unit
        return num_zh(format(x, "f"), unit) + unit
    if v >= 10 ** 12:
        return zh(v / 10 ** 12, "万亿")
    if v >= 10 ** 8:
        return zh(v / 10 ** 8, "亿")
    if v == v.to_integral_value():
        return int_zh(int(v))
    return zh(v / 10 ** 4, "万") if v >= 10 ** 4 else num_zh(format(v.normalize(), "f"))


def abbr_to_hanzi(text):
    """播客稿用（2026-11-06 加）：数字＋单位缩写改成读法——501B → 五千零一十亿参数，1.5T 个词元 → 一点五万亿个词元，
    128K → 十二万八千（规则见文件开头 11-06 一段）。数字和前后汉字之间排版用的空格一并去掉（"是 501B 的" → "是五千零一十亿参数的"）。
    返回 (新稿, [{起, 止, 原文, 改成, 显示}])，起止是原稿里的位置。"""
    changes = []
    for m in ABBR_PAT.finditer(text):
        a, b = m.span()
        # 11-06 晚加：前面是"版本号＋空格"的（Gemma 3 270M、Llama 3.1 405B、Kimi K3 1.5T、DeepSeek V4 671B、GPT-5 400K）
        # 是型号名字的一部分，不改。改了会卡住第 7 步：script_check 核数字时去掉空格，事件卡里的"Gemma 3 270M"成了 3270M，
        # 稿子里改出来的"二点七亿"就对不上（11-03 播客稿用现行规则重跑时被拦下）。这种照原样留给配音模型念，和 11-06 以前一样。
        if re.search(r"\d[  ]+$", text[max(0, a - 4):a]):
            continue
        letter = m.group("abu")
        new = abbr_amount_zh(m.group("ab"), letter)
        after = text[b:b + 8].lstrip(" ")
        if letter in "BT" and not after.lower().startswith(PARAM_NEAR) and "参数" not in text[max(0, a - 12):a]:
            new += "参数"
        if a >= 2 and text[a - 1] == " " and _CJK_CHAR.match(text[a - 2]):
            a -= 1
        if b + 1 < len(text) and text[b] == " " and _CJK_CHAR.match(text[b + 1]):
            b += 1
        changes.append({"起": a, "止": b, "原文": text[a:b], "改成": new, "显示": "%s → %s" % (m.group(0), new)})
    out = text
    for c in reversed(changes):
        out = out[:c["起"]] + c["改成"] + out[c["止"]:]
    return out, changes


RISKY = [
    (re.compile(r"(?<![A-Za-z0-9])Q[1-4](?![A-Za-z0-9])"), "季度写成\"第三季度\"这样（Q3 可能念成\"Q三\"；车型 Audi Q3 这类型号不用改）"),
    (re.compile(r"(?<![A-Za-z0-9])H[12](?![A-Za-z0-9])"), "半年写成\"上半年\"\"下半年\"（H1 可能按字母念）"),
    (re.compile(r"(?<![A-Za-z0-9])FY\s?\d{2}(?!\d)"), "财年写四位：\"2026 财年\"（FY26 年份不全，配音会按字母加数字念）"),
    (re.compile(r"(?<![A-Za-z0-9.\-_/])[12]\d{3}\s*/\s*\d{2,4}(?!\d)(?!\s*(?:财年|年))"),
     "年份区间后面要跟\"年\"或\"财年\"（写\"2026—2027 年\"或\"2026/27 财年\"）；只写 2026/27 可能念成\"斜杠\""),
]


def risky_numbers(text):
    """配音前转不了、可能念错的数字写法：[{写法, 位置, 说明}]。视频旁白检查（video3_build.lint_narration）当提醒报。"""
    out = []
    for pat, why in RISKY:
        for m in pat.finditer(text):
            out.append({"写法": m.group(0), "位置": m.start(), "说明": why})
    return sorted(out, key=lambda r: r["位置"])


if __name__ == "__main__":
    for a in sys.argv[1:] or ["10 月 31 日，OpenAI 本轮融资目标从 300 亿美元降到约 200 亿；英特尔跌 28.58%；iOS 27.3、GLM-5.3、千问 4；5,000 名；1 万亿；2 个"]:
        print(spoken(a)[0])
