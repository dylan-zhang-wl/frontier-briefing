#!/usr/bin/env python3
"""稿子检查（pipeline/script_check.py，总调度第 7 步"稿子"那一道）读百分数、分数的测试（2026-11-14 加，经验库第 69 件）。

为什么有这组测试：常用词遮罩 NOT_NUMBERS 里有"之一"（"其中之一"不是数字），原来一律遮掉，结果"百分之一百五十"
成了"百分□□150"——百分号丢了，只剩一个光秃秃的 150，事件卡里的 -150% 是百分比、对不上，判成"事件卡里找不到"。
100%–199% 和"百分之一""百分之一点五"都这样。11-11 播客因此没念 OpenAI 调整后营业利润率 -150%→-109%、
CoreWeave 营收增长 168%、麒麟性能提升 140%；11-13 播客没写 Cerebras 第二季度增速 103%。
现在"之一"前面是"分"的（百分之一……、三分之一）不遮；分数也认事件卡里的"1/3"写法。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_script_check.py
不调用任何模型，不花钱；事件卡用文件里写好的几句（11-11、11-13 事件卡原文）。仓库里有 测试版/2026-11-11、2026-11-13 的
事件卡时另拿真事件卡核一遍，没有就跳过。
"""
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

import script_check as S  # noqa: E402

# 11-11 事件卡原文（OpenAI 那张的 text_zh、CoreWeave 标题、麒麟那张的说明）、11-13 事件卡原文（Cerebras），各取一句
CARDS = [{"facts": [
    {"text_zh": "The Information 同时指出，也有向好的迹象：调整后营业利润率从 -150% 改善到 -109%。"},
    {"text_zh": "同一时期，OpenAI 的经营亏损从 101 亿美元扩大到 109 亿美元。"},
    {"text_zh": "CoreWeave 三季度营收增168%至36.6亿美元，净亏损扩至7.09亿美元。"},
    {"text_zh": "「性能提升 140%、功耗降低 66%」两个数字材料里没有给对比基准。"},
    {"text_en": "Core revenue grew 70% from $135.7 million, slower than the 103% growth in the second quarter."},
    {"text_zh": "约三分之一的开发者每天使用；另一份调查写的是 1/4 的团队。"},
    {"text_zh": "支出只增长了 1.5%，七月是 1%。"},
]}]


def missing(text, cards=CARDS):
    """找不到就必须改的那几个数（strong；"第二季度"这类序数找不到只算请人工看，不在这里）。"""
    ev = S.Evidence(cards)
    return [(x["种类"], x["值"]) for x in S.numbers_in(S.prepare(text)) if not ev.has_number(x) and S.strong(x)]


def must_fix(text, cards=CARDS):
    res = S.check("## 热点\n\n" + text + "\n", S.Evidence(cards))
    return [r for r in res["要改"] if r["类"] == "数字"]


class Percent(unittest.TestCase):
    def test_three_digit_percent_reads_as_percent(self):
        for t, v in (("百分之一百", 100.0), ("百分之一百零三", 103.0), ("百分之一百一十", 110.0), ("百分之一百五十", 150.0),
                     ("百分之一百六十八", 168.0), ("百分之一百九十九", 199.0), ("百分之两百", 200.0)):
            got = [(x["种类"], x["值"]) for x in S.numbers_in(S.prepare(t))]
            self.assertEqual(got, [("百分比", v)], t)

    def test_negative_percent(self):
        """负数：事件卡写 -150%、稿子念"负百分之一百五十"，两边都按 150 的百分比比（正负号本来就不比）。"""
        self.assertEqual(missing("OpenAI 这个比例，从第二季度的负百分之一百五十，改善到第三季度的负百分之一百零九。"), [])
        self.assertEqual(must_fix("调整后营业利润率从负百分之一百五十改善到负百分之一百零九。"), [])

    def test_1111_and_1113_sentences(self):
        self.assertEqual(must_fix("CoreWeave 三季度营收增长了百分之一百六十八。"), [])
        self.assertEqual(must_fix("麒麟的新一代芯片，性能提升百分之一百四十、功耗降低百分之六十六。"), [])
        self.assertEqual(must_fix("它的核心营收增长了百分之七十，比第二季度百分之一百零三的增速慢了下来。"), [])

    def test_small_percent_with_yi(self):
        self.assertEqual(must_fix("支出只增长了百分之一点五，七月是百分之一。"), [])

    def test_wrong_percent_still_caught(self):
        """修了读法，找不到的照样拦：-150% 写成 -160%、103% 写成 130%。"""
        rows = must_fix("从负百分之一百六十改善到负百分之一百零九，比第二季度百分之一百三十的增速慢了下来。")
        self.assertEqual(sorted(r["原文"] for r in rows), ["130%", "160%"])
        self.assertTrue(all("百分比" in r["说明"] for r in rows))

    def test_zhi_yi_as_word_still_masked(self):
        """"其中之一""最大的市场之一"里的"一"不是数字，照旧遮掉。"""
        for t in ("这是其中之一", "最大的市场之一", "原因之一是"):
            self.assertEqual(S.numbers_in(S.prepare(t)), [], t)


class Fraction(unittest.TestCase):
    def test_fraction_with_yi(self):
        self.assertEqual([(x["种类"], x["值"]) for x in S.numbers_in(S.prepare("三分之一的用户"))], [("分数", "3分之1")])
        self.assertEqual(must_fix("约三分之一的开发者每天使用。"), [])

    def test_fraction_matches_slash_in_cards(self):
        """事件卡写 1/4，稿子念"四分之一"也算找得到；写成"五分之一"照样拦。"""
        self.assertEqual(must_fix("另一份调查里是四分之一的团队。"), [])
        self.assertEqual([r["原文"] for r in must_fix("另一份调查里是五分之一的团队。")], ["5分之1"])


class RealCards(unittest.TestCase):
    """仓库里有 11-11、11-13 的真事件卡时，拿当天审读建议、自检里提到没写成的那几句核一遍（没有就跳过）。"""
    ROOT = PIPE.parent / "测试版"

    def cards(self, day):
        p = self.ROOT / day / "03_事件卡" / "cards_写稿用.json"
        if not p.exists():
            self.skipTest("没有 %s（公开仓库里不带往期内容）" % p)
        return S.load_cards(p)

    def test_1111(self):
        c = self.cards("2026-11-11")
        self.assertEqual(missing("OpenAI 这个比例，从第二季度的负百分之一百五十，改善到第三季度的负百分之一百零九。", c), [])
        self.assertEqual(missing("CoreWeave 三季度营收增长了百分之一百六十八。", c), [])

    def test_1113(self):
        c = self.cards("2026-11-13")
        self.assertEqual(missing("它的核心营收增长了百分之七十，比第二季度百分之一百零三的增速慢了下来。", c), [])


if __name__ == "__main__":
    unittest.main()
