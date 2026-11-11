#!/usr/bin/env python3
"""spoken_numbers（配音前把阿拉伯数字转成念法）和 lexicon_check 播客数字规则的测试（2026-11-02 晚加）。
2026-11-06 加 Abbr：数字＋单位缩写。视频旁白配音前 501B → 五百零一 B、1.5T → 一点五 T；播客稿 501B → 五千零一十亿参数
（script_check 能对上事件卡）；65B、型号里的数字不动。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python pipeline/test_spoken_numbers.py        # 全部通过时退出码为 0
不调用任何模型，不读写项目里的文件。
"""
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

from spoken_numbers import abbr_to_hanzi, risky_numbers, spoken, years_to_hanzi  # noqa: E402


def say(s):
    return spoken(s)[0]


class Years(unittest.TestCase):
    """四位数（1000–2999）＋"年"按年份逐位念。"""

    def test_listed(self):        # 11-02 视频旁白里念错的三处
        self.assertEqual(say("截至 2026 年 6 月"), "截至二零二六年六月")
        self.assertEqual(say("接近 2026 年的两倍"), "接近二零二六年的两倍")
        self.assertEqual(say("2027 年预算"), "二零二七年预算")
        self.assertEqual(say("出资是 2026 年内约 26 亿美元现金"), "出资是二零二六年内约二十六亿美元现金")

    def test_forms(self):
        self.assertEqual(say("2026年"), "二零二六年")
        self.assertEqual(say("1999 年代"), "一九九九年代")
        self.assertEqual(say("2026 年度"), "二零二六年度")
        self.assertEqual(say("2026 年 11 月 2 日"), "二零二六年十一月二日")
        self.assertEqual(say("2010 年"), "二零一零年")

    def test_ranges(self):
        for s in ("2026—2027 年", "2026-2027 年", "2026–2027 年", "2026 至 2027 年", "2026 到 2027 年", "2026~2027 年"):
            self.assertEqual(say(s), "二零二六到二零二七年", s)
        self.assertEqual(say("2026—2027 财年"), "二零二六到二零二七财年")
        self.assertEqual(say("2026/27 财年"), "二零二六到二七财年")
        self.assertEqual(say("2026 年至 2027 年"), "二零二六年至二零二七年")

    def test_fiscal(self):
        self.assertEqual(say("2026 财年"), "二零二六财年")
        self.assertEqual(say("FY2026"), "二零二六财年")
        self.assertEqual(say("苹果 FY2026 营收"), "苹果二零二六财年营收")

    def test_durations_untouched(self):   # 年数照原来的念法
        self.assertEqual(say("用了 3 年"), "用了三年")
        self.assertEqual(say("100 年"), "一百年")
        self.assertEqual(say("30 多年"), "30 多年")
        self.assertEqual(say("2 年"), "两年")
        self.assertEqual(say("近 5 年"), "近五年")
        self.assertEqual(say("2000 年"), "两千年")              # 整千仍念"两千年"（年份、年数都这么说）
        self.assertEqual(say("1000 年"), "一千年")
        self.assertEqual(say("距今 1500 年"), "距今一千五百年")
        self.assertEqual(say("长达 1200 年"), "长达一千二百年")


class Mapping(unittest.TestCase):
    """对应表：念法每个字指回稿子里的位置（字幕逐字变亮靠它）。"""

    def test_year_digit_by_digit(self):
        s = "截至 2026 年 6 月"
        t, src = spoken(s)
        self.assertEqual(len(t), len(src))
        pairs = [(ch, s[a:b]) for ch, (a, b) in zip(t, src)]
        self.assertEqual(pairs[2:7], [("二", "2"), ("零", "0"), ("二", "2"), ("六", "6"), ("年", "年")])

    def test_range_connector(self):
        s = "2026—2027 年"
        t, src = spoken(s)
        got = [(ch, s[a:b]) for ch, (a, b) in zip(t, src)]
        self.assertEqual(got[4], ("到", "—"))
        self.assertEqual(got[5:9], [("二", "2"), ("零", "0"), ("二", "2"), ("七", "7")])

    def test_fy(self):
        s = "FY2026"
        t, src = spoken(s)
        got = [(ch, s[a:b]) for ch, (a, b) in zip(t, src)]
        self.assertEqual(got, [("二", "2"), ("零", "0"), ("二", "2"), ("六", "6"), ("财", "FY"), ("年", "FY")])

    def test_spans_valid_everywhere(self):
        s = ("11 月 2 日，截至 2026 年 6 月，2026—2027 年、FY2026、5,000 名、1.6 万亿、约 26 亿美元、10%、10%-20%、"
             "3-5 年、第 2 名、iOS 27.3、W4A4、LongCat-2.5、800V、Q3、2026/27、Reflection Beam 501B、1.5T、65B")
        t, src = spoken(s)
        self.assertEqual(len(t), len(src))
        for a, b in src:
            self.assertTrue(0 <= a < b <= len(s))
        self.assertEqual(sorted(src, key=lambda x: x[0])[0][0], 0)


class Others(unittest.TestCase):
    """别的写法：原来就对的不变，原来会念错的修好，转不了的列提醒。"""

    def test_unchanged(self):
        for s, want in (("5,000 名", "五千名"), ("1.6 万亿", "一点六万亿"), ("约 26 亿美元", "约二十六亿美元"),
                        ("10%", "百分之十"), ("28.58%", "百分之二十八点五八"), ("10 月 31 日", "十月三十一日"),
                        ("2 个", "两个"), ("110 亿", "一百一十亿"), ("约 200 亿", "约两百亿"), ("12 月", "十二月")):
            self.assertEqual(say(s), want, s)

    def test_models_untouched(self):
        for s in ("800V", "W4A4", "LongCat-2.5", "iOS 27.3", "GLM-5.3", "千问 4", "Qwen4-27B", "v3.1", "S-1", "K15", "Q3",
                  "2026/27", "FY26", "GPT-6.2"):
            self.assertEqual(say(s), s, s)

    def test_fixed(self):
        self.assertEqual(say("第 2 名"), "第二名")              # 原来"第两名"
        self.assertEqual(say("第 2 季度"), "第二季度")
        self.assertEqual(say("3-5 年"), "三到五年")             # 原来"3-五年"
        self.assertEqual(say("2-3 个"), "两到三个")
        self.assertEqual(say("10—20 家"), "十到二十家")
        self.assertEqual(say("10%-20%"), "百分之十到百分之二十")
        self.assertEqual(say("10-20%"), "百分之十到百分之二十")

    def test_risky(self):
        got = [r["写法"] for r in risky_numbers("Q3 财报、FY26、2026/27 赛季、H1 营收、Audi Q3")]
        self.assertEqual(got, ["Q3", "FY26", "2026/27", "H1", "Q3"])
        self.assertEqual(risky_numbers("2026/27 财年、2026 年、iOS 27.3、W4A4、800V"), [])


class Abbr(unittest.TestCase):
    """数字＋单位缩写（2026-11-06 加；11-06 播客把 501B、816B 念成了 51B、81B）。"""

    def test_listed(self):        # 11-06 念错的两处，和同一期别的写法
        self.assertEqual(say("Reflection Beam 501B 是 80.1"), "Reflection Beam 五百零一 B 是 80.1")   # 不带单位的 80.1 照旧不转
        self.assertEqual(say("Meta 的 Muse Spark Open 816B"), "Meta 的 Muse Spark Open 八百一十六 B")
        self.assertEqual(say("Thinking Machines Inkling 975B"), "Thinking Machines Inkling 九百七十五 B")

    def test_forms(self):
        for s, want in (("1.5T 个词元", "一点五 T 个词元"), ("128K 上下文", "一百二十八 K 上下文"), ("1,000B", "一千 B"),
                        ("2.5B 参数", "二点五 B 参数"), ("200M", "两百 M"), ("是 501B 的", "是五百零一 B 的"),
                        ("594B／17B", "五百九十四 B／17B")):
            self.assertEqual(say(s), want, s)

    def test_untouched(self):     # 一两位的整数、型号里的数字、后面还接着型号的、货币
        for s in ("65B", "是 65B 的", "8B", "1M 上下文", "4K", "Ripple-65B Preview", "Qwen4-27B", "Qwen3 235B-A22B", "v1.5T",
                  "W4A4", "A100", "H100", "GPT-4o", "501Bx", "$501B", "501 B"):
            self.assertEqual(say(s), s, s)

    def test_mapping(self):       # 字幕仍显示 501B：念法每个字都指回 501B 这一段
        s = "Beam 501B 是"
        t, src = spoken(s)
        self.assertEqual(t, "Beam 五百零一 B 是")
        self.assertEqual({s[a:b] for a, b in src[5:11]}, {"501B"})          # "五百零一 B"六个字（含空格）

    def test_podcast(self):
        new, ch = abbr_to_hanzi("对手里，Reflection Beam 501B 是八十点一，Muse Spark Open 816B 是七十六点四；Ripple 是 65B。")
        self.assertEqual(new, "对手里，Reflection Beam 五千零一十亿参数是八十点一，Muse Spark Open 八千一百六十亿参数是七十六点四；Ripple 是 65B。")
        self.assertEqual([c["显示"] for c in ch], ["501B → 五千零一十亿参数", "816B → 八千一百六十亿参数"])
        for s, want in (("在 1.5T 个词元上", "在一点五万亿个词元上"), ("总参数 594B，", "总参数五千九百四十亿，"),
                        ("支持 128K 上下文", "支持十二万八千上下文"), ("200M 用户", "两亿用户"), ("1,000B", "一万亿参数"),
                        ("2.5B 参数", "二十五亿参数"), ("Inkling 975B。", "Inkling 九千七百五十亿参数。"), ("1.5K", "一千五百")):
            self.assertEqual(abbr_to_hanzi(s)[0], want, s)

    def test_podcast_matches_script_check(self):
        """播客稿改完的数字，script_check（总调度第 7 步核对数字）要能在事件卡里找到：它把事件卡里的 501B 认成 5010 亿。"""
        import script_check as SC
        for card, s in (("Reflection Beam 501B (80.1)", "Reflection Beam 501B 是八十点一"), ("Inkling 975B，63.8 分", "Inkling 975B。"),
                        ("200M 用户", "200M 用户"), ("2.5B 参数", "2.5B 参数")):
            ev = SC.Evidence([{"facts": [{"text_zh": card}]}])
            new = abbr_to_hanzi(s)[0]
            got = [x for x in SC.numbers_in(SC.prepare(new)) if not ev.has_number(x)]
            self.assertEqual(got, [], (card, new))

    def test_podcast_model_names(self):
        """前面是"版本号＋空格"的规格（型号名字的一部分）不改（11-06 晚加）：改了第 7 步数字核不上，会卡住自动运行。"""
        import script_check as SC
        for s in ("小模型 Gemma 3 270M 做对照", "Llama 3.1 405B 仍是最大的", "Kimi K3 1.5T 参数", "DeepSeek V4 671B 总参数",
                  "GPT-5 400K 上下文"):
            new, ch = abbr_to_hanzi(s)
            self.assertEqual((new, ch), (s, []), s)
            r = SC.check("## 开场\n\n" + new + "。\n", SC.Evidence([{"facts": [{"text_zh": s}]}]), day="日常")
            self.assertEqual([x for x in r["要改"] if x["类"] == "数字"], [], s)
        self.assertEqual(abbr_to_hanzi("Ripple 是 501B 的")[0], "Ripple 是五千零一十亿参数的")      # 前面不是版本号的照改
        self.assertEqual(abbr_to_hanzi("第 3 名是 501B")[0], "第 3 名是五千零一十亿参数")


class Podcast(unittest.TestCase):
    """播客稿：阿拉伯数字的年份改成"二〇二六年"，年数不动；lexicon_check 的数字规则。"""

    def test_years_to_hanzi(self):
        new, ch = years_to_hanzi("在 2026 年，2026—2027 年度、FY2026 和 2026 财年；用了 3 年，100 年，30 多年，2000 年。")
        self.assertEqual(new, "在二〇二六年，二〇二六到二〇二七年度、二〇二六财年和二〇二六财年；用了 3 年，100 年，30 多年，2000 年。")
        self.assertEqual(len(ch), 4)

    def test_lexicon_rule(self):
        import lexicon_check as L
        ents, extra, suffix, _v = L.load_lexicon()
        text = ("# 稿\n\n## 开场\n\n截至 2026 年 6 月，36氪报道，Claude Opus 4.8 和千问 4 都在；用了 3 年。\n\n"
                "<!-- 语气 2026 年 -->\n")
        r = L.podcast_numbers(text, ents)
        self.assertEqual([x["应为"] for x in r["要改"]], ["二〇二六年"])          # 注释里的 2026 年不算
        flagged = [x["原文"] for x in r["提醒"]]
        self.assertEqual(len(flagged), 2, flagged)                               # 6 月、3 年；36氪、Opus 4.8、千问 4 不算
        self.assertTrue(flagged[0].startswith("6") and flagged[1].startswith("3"), flagged)
        new, done = L.apply_fixes(text, r["_fixes"])
        self.assertIn("截至二〇二六年 6 月", new)
        self.assertIn("<!-- 语气 2026 年 -->", new)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False, verbosity=1).result.wasSuccessful() else 1)
