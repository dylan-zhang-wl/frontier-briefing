#!/usr/bin/env python3
"""对稿"数字整数比对"（pipeline/tts_qc.py 的 number_mismatches，2026-11-15 加；fd_开关.json"对稿数字整数比对"）的测试。

为什么有它：11-15 播客"一共一千零九页"念成"109 页"（用户耳听确认）。逐字比只差"少掉 1 个 0"，第 8 轮字错率 0.064，
到不了重录线；数字单位那一条只管数后面的单位字。这里查：
  · 那一轮（原稿、转写照 本机资料/成品/2026-11-15/05_配音/周日深谈_人声/qc.json 第 8 轮第 1 条）判"数字不符"、要重录；
  · 只是写法不同的不报：汉字和阿拉伯数字、三点八＝3.8、一万七千五百＝17500、三点四万＝34000、日期、百分数、
    型号里按英文念的数（Qwen 4 转写成 for，"Gemini 4 Carbon"转写成一个词 geminiforcarbon）；
  · 不是"数"的词不报：一个、一家、统一、十分重要、三星；
  · 不在数字上下文里的"一"（统一、小一）不换成 1（2026-11-16 加，11-16 播客"小艺"转写成"小一"），
    数字上下文里的照旧换（一千零九＝1009、第一、一个、一亿、百分之一、三点一），真数字照旧比；
  · 真不一样的要报：3.8→3.0、十六→是 6、三到五年→三到四年；只差量级的（1.25万亿→1.25万）归"数字单位"，这里不重复；
  · 开关关着（默认，没写这一项也按关）时，check() 的结果和加这一项以前一模一样；
  · 配音重录：数字不符最多重录 2 次（对稿原来只重录 1 次）；重录预算不够时不报错、不重录，照旧标需人工复听；
  · 有本机成品（环境变量 FD_LOCAL_DATA 指私有仓库那份 本机资料/）时，拿 11-11、11-13、11-15 的真转写跑一遍。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_tts_qc_numbers.py
不调用任何模型、不转写、不花钱。
"""
import io
import json
import os
import re
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))
import tts_qc as Q  # noqa: E402

LOCAL = Path(os.environ["FD_LOCAL_DATA"]).expanduser() if os.environ.get("FD_LOCAL_DATA") else PIPE.parent / "本机资料"
DONE = LOCAL / "成品"
TAG = re.compile(r"[（(\[]\s*[㐀-鿿][㐀-鿿，、 ]{0,11}\s*[）)\]]|<\s*[A-Za-z][A-Za-z \-]{0,30}\s*>")

# 11-15 周日深谈第 8 轮（播客 2:44）：原稿照 qc.json，转写是第 1 条（选用的那条）
REF_1115_8 = "它的篇幅很直观：一共一千零九页，写了五十五年，每周一页，编号一直编到 1009。"
HYP_1115_8 = "它的篇幅很直观一共109页写了55年每周一页编号一直编到1009"


class Env:
    """临时改环境变量（两个开关），用完还原。"""

    def __init__(self, **kv):
        self.kv, self.old = kv, {}

    def __enter__(self):
        for k, v in self.kv.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def mism(ref, hyp):
    return [(x["原稿"], x["转写"]) for x in Q.number_mismatches(ref, hyp)]


class Switch(unittest.TestCase):
    def test_off_by_default(self):
        """没写这一项按关：fd_开关.json 指到一个没有这两项的文件。"""
        old = Q.SWITCH_FILE
        with tempfile.TemporaryDirectory() as d, Env(FD_QC_NUMBERS=None, FD_QC_ASR2=None):
            Q.SWITCH_FILE = Path(d) / "fd_开关.json"
            Q.SWITCH_FILE.write_text(json.dumps({"视频导演": "开"}), encoding="utf-8")
            try:
                self.assertFalse(Q.numbers_switch()[0])
                self.assertFalse(Q.asr2_switch()[0])
                Q.SWITCH_FILE.write_text(json.dumps({"对稿数字整数比对": "开", "对稿第二个听写模型": "关"}), encoding="utf-8")
                self.assertTrue(Q.numbers_switch()[0])
                self.assertFalse(Q.asr2_switch()[0])
                with Env(FD_QC_NUMBERS="off"):
                    self.assertFalse(Q.numbers_switch()[0])          # 环境变量优先
                Q.SWITCH_FILE.unlink()
                self.assertFalse(Q.numbers_switch()[0])              # 文件没有也按关
            finally:
                Q.SWITCH_FILE = old

    def test_off_result_identical(self):
        with Env(FD_QC_NUMBERS="off", FD_QC_ASR2="off"):
            a = Q.check(REF_1115_8, HYP_1115_8)
        self.assertNotIn("数字不符", a)
        self.assertNotIn("待复核", a)
        self.assertFalse(a["需重录"])                                  # 这就是 11-15 漏掉的那一条
        with Env(FD_QC_NUMBERS="on", FD_QC_ASR2="off"):
            b = Q.check(REF_1115_8, HYP_1115_8)
        for k in a:
            if k not in ("需重录", "原因"):
                self.assertEqual(a[k], b[k], k)
        with Env(FD_QC_NUMBERS="on", FD_QC_ASR2="off"):
            c = Q.check("今天是十一月十五日，营收三十亿美元。", "今天是11月15日营收30亿美元")
        with Env(FD_QC_NUMBERS="off", FD_QC_ASR2="off"):
            d = Q.check("今天是十一月十五日，营收三十亿美元。", "今天是11月15日营收30亿美元")
        self.assertEqual(c, d)                                        # 没有不符时开着关着一模一样


class Catches(unittest.TestCase):
    def test_1115_thousand_nine(self):
        self.assertEqual(mism(REF_1115_8, HYP_1115_8), [("1009", "109")])
        with Env(FD_QC_NUMBERS="on", FD_QC_ASR2="off"):
            r = Q.check(REF_1115_8, HYP_1115_8)
        self.assertTrue(r["需重录"])
        self.assertEqual(r["原因"], ["数字不符：原稿 1009，转写 109，重录；还在就请你耳听"])
        self.assertEqual(r["数字不符"], [{"原稿": "1009", "转写": "109"}])
        self.assertTrue(Q.misread(r) and Q.misread_only(r))

    def test_version(self):
        self.assertEqual(mism("和 Gemini 三点八 Flash 相比", "和Gemini 3.0 Flash相比"), [("3.8", "3.0")])
        self.assertEqual(mism("和 Gemini 3.8 Flash 相比", "和Gemini 三点零 Flash相比"), [("3.8", "3.0")])

    def test_sixteen_heard_as_shi_six(self):
        """11-15 视频 61 秒：转写模型自己把"十六次"写成"是 6 次"——这里照报，第二个听写模型开着时由它推翻。"""
        self.assertEqual(mism("Alphabet 出现了十六次。", "Alphabet出现了是6次"), [("16", "是6")])

    def test_ranges(self):
        self.assertEqual(mism("要三到五年。", "要3到4年"), [("5", "4")])
        self.assertEqual(mism("要三到五年。", "要4到5年"), [("3", "4")])

    def test_dates_and_counts(self):
        self.assertEqual(mism("十一月十五日", "11月16日"), [("15", "16")])
        self.assertEqual(mism("一共三家公司", "一共两家公司"), [("3", "2")])
        self.assertEqual(mism("排第四", "排第一"), [("4", "1")])     # 11-06 那一处
        self.assertEqual(mism("一共一千零九页", "一共页"), [("1009", "")])

    def test_magnitude_only_left_to_units(self):
        """1.25万亿→1.25万：数字样子一样、只差量级，归"数字单位"那一条（它会报"少字：亿"），这里不重复。"""
        self.assertEqual(mism("一点二五万亿美元", "1.25万美元"), [])
        self.assertEqual([x["说明"] for x in Q.unit_losses("一点二五万亿美元", "1.25万美元")], ["少字：亿"])


class Lets(unittest.TestCase):
    def test_written_differently(self):
        for ref, hyp in [("三点八", "3.8"), ("一万七千五百人", "17500人"), ("三点四万人", "34000人"),
                         ("十一月十五日", "11月15日"), ("百分之十二点七五", "12.75%"), ("二零二六年", "2026年"),
                         ("一千零九页", "一千零九页"), ("五千多名", "5000多名"), ("十几个", "十几个"),
                         ("两家", "2家"), ("零点零一六", "0.016")]:
            self.assertEqual(mism(ref, hyp), [], (ref, hyp))

    def test_english_digits_in_model_names(self):
        self.assertEqual(mism("和千问 4 搭配", "和千问for搭配"), [])
        self.assertEqual(mism("前沿模型 Gemini 4 Carbon、Gemini 4 Argon", "前沿模型geminiforcarbongeminiforargon"), [])

    def test_not_numbers(self):
        for ref, hyp in [("一个模型", "这个模型"), ("统一口径", "通用口径"), ("十分重要", "实分重要"),
                         ("三星电子", "山星电子"), ("这一周", "这周"), ("一家公司", "那家公司"), ("四处都是", "似处都是")]:
            self.assertEqual(mism(ref, hyp), [], (ref, hyp))

    def test_lone_yi(self):
        """2026-11-16：数字上下文里的"一"照旧当 1，其余（统一、唯一、一起、小一、之一）照"一"这个字比。"""
        for text, want in [("一千零九页", "1009页"), ("第一条", "第1条"), ("一个", "1个"), ("一亿美元", "1亿美元"),
                           ("百分之一", "1%"), ("三点一", "3.1"), ("一点五", "1.5"), ("十一月", "11月"), ("一到三年", "1到3年"),
                           ("三分之一", "3分之1"), ("Qwen 一", "qwen1"),
                           ("统一", "统一"), ("唯一的", "唯一的"), ("一起", "一起"), ("小一的", "小一的"), ("公司之一", "公司之一")]:
            self.assertEqual("".join(Q.qc_tokens(text)), want, text)
        self.assertEqual("".join(Q.tokens("统一")), "统1")                             # 老的记号不变（开关关着时一模一样）
        self.assertEqual(mism("一共一千零九页", "一共109页"), [("1009", "109")])         # 真数字照旧
        self.assertEqual(mism("排第一", "排第七"), [("1", "7")])
        for ref, hyp in [("第一条", "第1条"), ("第一条", "低一条"), ("一个模型", "1个模型"), ("一亿美元", "1亿美元")]:
            self.assertEqual(mism(ref, hyp), [], (ref, hyp))                           # 转写写成数字、写错前一个字都不算不符

    def test_ten_minutes_is_a_number(self):
        self.assertEqual(mism("等了十分钟", "等了四分钟"), [("10", "4")])


def tiny_wav(rate=24000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * 2400)
    return buf.getvalue()


class Engine:
    def __init__(self):
        self.calls = 0

    def synthesize(self, text, *a, **k):
        self.calls += 1
        return tiny_wav(), {"engine": "gemini", "seconds_audio": 12.0, "seconds_wall": 0.0, "cost_usd": 0.01,
                            "finish_reason": "STOP"}


class Retakes(unittest.TestCase):
    """配音那一头（tts._Taker.series）：数字不符最多重录 2 次，预算不够不报错。假的引擎和转写，不花钱。"""

    def setUp(self):
        import tts
        self.tts = tts
        self.tmp = tempfile.TemporaryDirectory()
        self.cache0 = tts.CACHE
        tts.CACHE = Path(self.tmp.name) / "tts"
        (tts.CACHE / "chunks").mkdir(parents=True)
        self.t0 = Q.transcribe
        self.hyps = []
        Q.transcribe = lambda raw, wdir: self.hyps.pop(0)
        self.logs = []
        self.env = Env(FD_QC_NUMBERS="on", FD_QC_ASR2="off")
        self.env.__enter__()

    def tearDown(self):
        self.env.__exit__()
        Q.transcribe = self.t0
        self.tts.CACHE = self.cache0
        self.tmp.cleanup()

    def series(self, hyps, budget=1.0):
        self.hyps = list(hyps)
        t = self.tts._Taker(self.tts.Ledger(budget), fresh=False, qc=True, retakes=1, log=self.logs.append)
        t.engine = Engine()
        cfg = self.tts.VoiceConfig("gemini", "flash", "voice_test", "calm")
        return t, t.series(cfg, REF_1115_8, 12.0, "块8", 8)

    def test_two_retakes_then_clean(self):
        t, (takes, best, _) = self.series([HYP_1115_8, HYP_1115_8, REF_1115_8])
        self.assertEqual(len(takes), 3)                    # 原来对稿只重录 1 次，这里第 3 条才念对
        self.assertEqual(best["take"], 3)
        self.assertFalse(best["qc"]["需重录"])
        self.assertEqual(Q.listen_fields(best["qc"]), {})

    def test_still_wrong_after_two_retakes(self):
        t, (takes, best, _) = self.series([HYP_1115_8] * 3)
        self.assertEqual(len(takes), 3)                    # 最多重录 2 次
        self.assertTrue(best["qc"]["需重录"])
        self.assertEqual(Q.listen_fields(best["qc"]), {"数字不符（请你耳听）": [{"原稿": "1009", "转写": "109"}]})

    def test_budget_short_no_error(self):
        """预算只够配第一条：数字不符的重录不录、不报错（不像多念漏念那样超预算就停）。"""
        t, (takes, best, _) = self.series([HYP_1115_8] * 3, budget=0.011)
        self.assertEqual(len(takes), 1)
        self.assertTrue(any("预算不够，没为数字不符" in x for x in self.logs))

    def test_off_same_as_before(self):
        with Env(FD_QC_NUMBERS="off"):
            t, (takes, best, _) = self.series([HYP_1115_8] * 3)
        self.assertEqual(len(takes), 1)                    # 关着：这一条照旧算通过，就是 11-15 那样


@unittest.skipUnless((DONE / "2026-11-15").exists(), "没有本机成品（FD_LOCAL_DATA 指私有仓库那份 本机资料/）")
class RealIssues(unittest.TestCase):
    """本机成品里 11-11、11-13、11-15 各块选用的那条：数字不符报出的正好是下面这些（11-15 回放时逐条看过）。"""

    EXPECT = {
        ("2026-11-15", "周日深谈_人声"): [("1009", "109")],
        ("2026-11-15", "终版_配音"): [("16", "是6")],
        ("2026-11-13", "播客_v3"): [("3.8", "3.0")],
        ("2026-11-11", "视频旁白_v3"): [("70", "7078"), ("78美元", "7078美元")],
    }

    def test_hits(self):
        got = {}
        with Env(FD_QC_NUMBERS="on", FD_QC_ASR2="off"):
            for day in ("2026-11-11", "2026-11-13", "2026-11-15"):
                for f in sorted(list((DONE / day / "05_配音").glob("*/qc.json")) +
                                list((DONE / day / "11_视频v3_导演").glob("*/qc.json"))):
                    if "带音效" in f.parent.name:
                        continue
                    d = json.loads(f.read_text(encoding="utf-8"))
                    for b in d.get("各轮") or d.get("各块") or []:
                        for t in b.get("各条") or []:
                            if t.get("转写") is None or t.get("第几条") != b.get("选用第几条"):
                                continue
                            for x in Q.number_mismatches(TAG.sub("", b["原稿"]), t["转写"]):
                                got.setdefault((day, f.parent.name), []).append((x["原稿"], x["转写"]))
        self.assertEqual(got, self.EXPECT)


if __name__ == "__main__":
    unittest.main()
