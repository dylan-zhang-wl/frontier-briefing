#!/usr/bin/env python3
"""对稿的"数字单位"一项（pipeline/tts_qc.py 的 unit_losses，2026-11-09 晚加）的测试。

为什么有它：11-09 云端那期视频"Anthropic 签下 34 亿美元的协议"转写成"34亿元"，少了"美"，美元变成了人民币；
整块字错率 2.75%、最长少 1 个字，原来的线拦不住，用户耳听才发现。这里查：
  · 那一块（转写原样取自 本机资料/成品/2026-11-09/05_配音/视频旁白_v3/qc.json 第 3 块）判"要重录"，原因写"数字单位少字：美"；
    同一块里念对了的那条（第 2 条）不报；
  · 只是写法不同的不报：数字写成汉字或阿拉伯数字、量级写法不同但数值一样（3.4万＝34000、1万7500＝17500）、
    同义单位（美元＝美金）、单位前后有空格、单位字换成同音同调的字（倍→被）、转写多出单位、数字本身念错；
  · 真丢了、换了的要报：美元→日元、万亿→万、百分之没了、亿变成"一"；
  · 没命中时结果和原来一模一样（没有"数字单位"这一栏）；
  · 有 mini 试运行那周的 qc.json（本机 本机资料/归档/，不进 git）时，再用真转写跑一遍：命中的正好是评估时列出的那 6 块。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_tts_qc_units.py
不调用任何模型、不转写、不花钱。
"""
import json
import os
import re
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))
import tts_qc as Q  # noqa: E402

_BASES = ([Path(os.environ["FD_SAMPLE_ROOT"]).expanduser()] if os.environ.get("FD_SAMPLE_ROOT") else []) + [
    PIPE.parent / "本机资料" / "归档" / "mini试运行_1031-1109"]
SAMPLE = next((b for b in _BASES if (b / "2026-11-09").exists()), _BASES[-1])

# 11-09 云端那期视频旁白第 3 块（"电"那一章，视频 57 秒前后）：原稿是配音用的念法，转写原样
REF_1109 = ("燃气轮机正在排长队。据路透社报道，AI 数据中心热潮让新设备的交货期排到了二零三零年代。到二零二八年，"
            "全球产能预计约 87 吉瓦，需求预计 129 吉瓦。据《金融时报》报道，Anthropic 签下三十四亿美元的协议，"
            "为数据中心生产燃气发电，绕开传统供应商，直接锁定稀缺设备。")
HYP_1109_TAKE1 = ("燃气轮机正在排长队据路透社报道AI数据中心热潮让新设备的交货期排到了2030年代到2028年全球产能预计约87级瓦"
                  "需求预计129级瓦据金融时报报道Anthropic签下34亿元的协议为数据中心生产燃气发电绕开传统供应商直接锁定稀缺设备")
HYP_1109_TAKE2 = ("燃气轮机正在排场队据路透社报道AI数据中心热潮让新设备的交货期排到了2030年代到2028年全球产能预计约87级瓦"
                  "需求预计129级瓦据金融时报报道Anthropic签下34亿美元的协议为数据中心生产燃气发电绕开传统供应商直接锁定稀缺设备")


def losses(ref, hyp):
    return [(x["原稿"], x["说明"]) for x in Q.unit_losses(ref, hyp)]


class Today(unittest.TestCase):
    """11-09 视频那一块。"""

    def test_take1_flagged(self):
        r = Q.check(REF_1109, HYP_1109_TAKE1)
        self.assertLess(r["字错率"], Q.CER_LIMIT)                 # 原来的线拦不住
        self.assertEqual(r["最长少掉"], 1)
        self.assertTrue(r["需重录"])
        self.assertEqual(r["数字单位"], [{"原稿": "34亿美元", "转写": "34亿元", "说明": "少字：美"}])
        self.assertEqual(r["原因"], ["数字单位少字：美（原稿 34亿美元，转写 34亿元），重录一次；还在就请你耳听"])
        self.assertTrue(Q.badness(r)[0])

    def test_take2_clean(self):
        r = Q.check(REF_1109, HYP_1109_TAKE2)
        self.assertFalse(r["需重录"])
        self.assertNotIn("数字单位", r)

    def test_retake_prefers_clean_take(self):
        """挑条时（badness 越小越好）念对的第 2 条排在前面。"""
        self.assertLess(Q.badness(Q.check(REF_1109, HYP_1109_TAKE2)), Q.badness(Q.check(REF_1109, HYP_1109_TAKE1)))


class NoFalseAlarm(unittest.TestCase):
    def test_number_written_differently(self):
        self.assertEqual(losses("签下三十四亿美元的协议", "签下34亿美元的协议"), [])
        self.assertEqual(losses("签下 34 亿美元的协议", "签下三十四亿美元的协议"), [])
        self.assertEqual(losses("占百分之六十五点二", "占65.2%"), [])
        self.assertEqual(losses("占百分之六十五点二", "占百分之65.2"), [])
        self.assertEqual(losses("五点四六亿用户", "5.46亿用户"), [])
        self.assertEqual(losses("两千零一十亿参数", "2010亿参数"), [])

    def test_magnitude_written_differently_same_value(self):
        self.assertEqual(losses("约三点四万人", "约34000人"), [])
        self.assertEqual(losses("超过一万七千五百个会话", "超过17500个会话"), [])     # 11-06 播客：1万7500 是一个数
        self.assertEqual(losses("一点二五万亿美元", "12500亿美元"), [])
        self.assertEqual(losses("三千万美元", "3千万美元"), [])

    def test_synonym_units(self):
        self.assertEqual(losses("三十四亿美元的协议", "34亿美金的协议"), [])
        self.assertEqual(losses("三十二万亿日元", "32万亿日圆"), [])
        self.assertEqual(losses("五十亿港元", "50亿港币"), [])
        self.assertEqual(losses("上升零点五个百分点", "上升0.5百分点"), [])
        self.assertEqual(losses("一百亿元人民币", "100亿人民币"), [])

    def test_spaces(self):
        self.assertEqual(losses("签下 34 亿 美元 的协议", "签下34亿美元的协议"), [])
        self.assertEqual(losses("签下三十四亿美元的协议", "签下 34 亿 美元 的协议"), [])
        self.assertEqual(losses("增长 3 倍", "增长 三 倍"), [])

    def test_same_sound_same_tone(self):
        """单位字换成同音同调的字：转写挑错字，不是没念出来。"""
        self.assertEqual(losses("翻了一倍", "翻了一被"), [])

    def test_extra_unit_or_wrong_digit_not_ours(self):
        self.assertEqual(losses("融资三十四亿", "融资34亿元"), [])        # 多出单位不归这条管
        self.assertEqual(losses("三十四亿美元", "35亿美元"), [])          # 数字本身念错不归这条管

    def test_units_outside_list(self):
        self.assertEqual(losses("需求预计 129 吉瓦", "需求预计129级瓦"), [])   # 吉瓦不在单位表里
        self.assertEqual(losses("排到了二零三零年代", "排到了2030年代"), [])

    def test_clean_result_unchanged(self):
        r = Q.check("今天是十一月九日，营收三十亿美元。", "今天是11月9日营收30亿美元")
        self.assertNotIn("数字单位", r)
        self.assertFalse(r["需重录"])
        self.assertEqual(r["原因"], [])


class Catches(unittest.TestCase):
    def test_currency_swapped(self):
        self.assertEqual(losses("三十四亿美元的协议", "34亿日元的协议"), [("34亿美元", "换字：美元→日元")])

    def test_trillion_to_ten_thousand(self):
        self.assertEqual(losses("一点二五万亿美元", "1.25万美元"), [("1.25万亿美元", "少字：亿")])

    def test_percent_lost(self):
        self.assertEqual(losses("只占全部参数的百分之零点零一六。", "只占全部参数的0.016"), [("0.016%", "少字：百分之")])

    def test_yi_heard_as_one(self):
        """亿（yì）念成一（yī）：声调不同，算丢了；数值也不对（341 ≠ 34 亿）。"""
        self.assertEqual(losses("三十四亿美元", "三十四一美元"), [("34亿美元", "少字：亿")])

    def test_times_lost(self):
        self.assertEqual(losses("增长了三倍。", "增长了3"), [("3倍", "少字：倍")])

    def test_unit_and_magnitude_both(self):
        self.assertEqual(losses("三十四亿美元的协议", "34元的协议"), [("34亿美元", "少字：美、亿")])

    def test_in_check_with_other_reasons(self):
        r = Q.check("据彭博记者 Gurman 说，甲骨文取消了和腾讯一项七十亿美元的交易。", "据彭博记者German说甲骨文取消了和腾讯1项70亿元的交易")
        self.assertTrue(r["需重录"])
        self.assertEqual([x.split("（")[0] for x in r["原因"]], ["专名读音：Gurman 转写成了 german", "数字单位少字：美"])


@unittest.skipUnless((SAMPLE / "2026-11-09").exists(), "这台机器上没有 mini 试运行那周的 qc.json（在本机 本机资料/归档/ 里，不进 git）")
class RealArchive(unittest.TestCase):
    """mini 试运行那周各期（不含 _带音效）：新规则命中的正好是 11-09 晚评估时列出的那 6 块。"""

    def test_hits(self):
        tag = re.compile(r"[（(\[]\s*[㐀-鿿][㐀-鿿，、 ]{0,11}\s*[）)\]]|<\s*[A-Za-z][A-Za-z \-]{0,30}\s*>")
        hit = {}
        for f in sorted(SAMPLE.glob("*/05_配音/*/qc.json")):
            if "带音效" in f.parent.name:
                continue
            d = json.loads(f.read_text(encoding="utf-8"))
            for b in (d.get("各块") or []) + (d.get("各轮") or []):
                for t in b.get("各条") or []:
                    if t.get("转写") is None:
                        continue
                    u = Q.unit_losses(tag.sub("", b["原稿"]), t["转写"])
                    if u:
                        key = (f.parts[-4], f.parent.name, b.get("块", b.get("轮")))
                        hit.setdefault(key, {})[t["第几条"]] = [x["说明"] for x in u]
        self.assertEqual(hit, {
            ("2026-11-01", "视频旁白_v3", 3): {1: ["少字：亿"]},          # 32万亿日元 → 32万元日元
            ("2026-11-03", "播客_v3", 5): {1: ["少字：百分之"]},         # 0.016% → 0.016
            ("2026-11-04", "播客_v3", 10): {1: ["少字：美"]},            # 70亿美元 → 70亿元
            ("2026-11-07", "周六_人声", 3): {1: ["少字：亿"]},           # 27万亿 → 27万1
            ("2026-11-08", "周日深谈_人声", 32): {1: ["少字：亿"]},      # 1.25万亿美元 → 1.25万美元（用户耳听没问题：误报）
            ("2026-11-09", "播客_v3", 9): {1: ["少字：美"], 3: ["少字：美"]},   # 34亿美元 → 34亿元
        })


if __name__ == "__main__":
    unittest.main()
