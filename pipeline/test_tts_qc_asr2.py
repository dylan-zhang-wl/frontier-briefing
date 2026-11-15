#!/usr/bin/env python3
"""对稿"第二个听写模型复核"（pipeline/tts_qc.py 的 suspects、confirm，2026-11-15 加；fd_开关.json"对稿第二个听写模型"）的测试。

为什么有它：11-15 播客"损害"念成"损失"、"有着落了吗"少了"落"（用户耳听确认），逐字比只算一两个错字，不重录；
可 Whisper 自己也常听错同音近音字（11-13 实验：会话→绘画、芯片→型片），只看 Whisper 就重录会白花钱。
判法照 11-13 实验报告：不带声调的拼音对不上的地方，交给 SenseVoiceSmall、Paraformer-zh 各听一遍，
至少一个新模型也听得和原稿不一样才算念错。这里查（用一个假的听写进程代替真模型，不载入模型、不花钱）：
  · 挑可疑处：同音字不挑；英文名不挑；只多出字不挑；只差语气词不挑（"了→为"照挑）；数字归"数字不符"；
  · 至少一个新模型也不一样 → 念错、要重录；两个都听成原稿 → Whisper 听错、不重录；两个都没听清 → 不重录；
  · 数字不符被两个新模型推翻（11-15 视频"十六次"转写成"是 6 次"）→ 去掉那条原因；新模型也听错 → 照旧重录；
  · 新模型没装好：字词可疑处只记"没复核"，数字不符照旧重录，配音不停；
  · 截哪几秒（按 Whisper 分段时间）、两头可以对不上的对齐、结果缓存（重跑不再听）。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_tts_qc_asr2.py
"""
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))
import tts_qc as Q  # noqa: E402
from test_tts_qc_numbers import Env  # noqa: E402

# 假的听写进程：按截取起点（取整秒）回话，答案表从环境变量 FAKE_ASR2 给的 json 文件读；每听一次记一行到 FAKE_ASR2_LOG
FAKE = textwrap.dedent('''
    import json, os, sys
    table = json.load(open(os.environ["FAKE_ASR2"], encoding="utf-8"))
    if table.get("_fail_load"):
        print(json.dumps({"ready": False, "错误": "装坏了"}), flush=True); sys.exit(1)
    print(json.dumps({"ready": True, "载入秒": 0.1}), flush=True)
    for line in sys.stdin:
        job = json.loads(line)
        key = str(int(float(job["start"])))
        open(os.environ["FAKE_ASR2_LOG"], "a").write(key + "\\n")
        ans = table.get(key) or {}
        print(json.dumps(dict(ans, id=job["id"], 秒=0.01), ensure_ascii=False), flush=True)
''')

# 11-15 周日深谈第 2 轮（播客 0:23）的一段：原稿、Whisper 转写
REF = "据路透社报道，公司说没有理由相信客户的数据受到损害，正在调查。"
HYP = "据路透社报道公司说没有理由相信客户的数据受到损失正在调查"


def even_times(hyp_text, seconds):
    """假的分段时间：转写每个记号平均占时。"""
    n = len(Q.tokens(hyp_text))
    return [(seconds * i / n, seconds * (i + 1) / n) for i in range(n)]


class Suspects(unittest.TestCase):
    def sus(self, ref, hyp, numbers=True):
        return [(x["原稿"], x["转写"]) for x in Q.suspects(Q.tokens(ref), Q.tokens(hyp), numbers=numbers)]

    def test_picks(self):
        self.assertEqual(self.sus(REF, HYP), [("害", "失")])
        self.assertEqual(self.sus("正式的人选现在有着落了吗？", "正式的人选现在有着了吗"), [("落", "")])
        self.assertEqual(self.sus("营收增长了两成", "营收增长为两成"), [("了", "为")])     # 11-13 用户确认的真错
        self.assertEqual(self.sus("美银研究的报告", "美营研究的报告"), [("银", "营")])

    def test_skips(self):
        self.assertEqual(self.sus("会话和即时通讯", "绘画和及时通讯"), [])                 # 同音字（不带声调）
        self.assertEqual(self.sus("据 Semafor 报道", "据Summerford报道"), [])            # 英文名：拿不准
        self.assertEqual(self.sus("增长了", "增长"), [])                                 # 只差语气词
        self.assertEqual(self.sus("我们看", "我们来看"), [])                             # 只多出字
        self.assertEqual(self.sus("一共一千零九页", "一共109页"), [])                    # 数字归数字不符
        self.assertEqual(self.sus("一共一千零九页", "一共109页", numbers=False), [("0", "")])

    def test_minus_sign_is_fu(self):
        """11-11 视频：原稿"负百分之一百五十"，转写写成"-150%"——减号当"负"，不算少了"负"；型号里的连字符不动。"""
        ref, hyp = "利润率从负百分之一百五十改善到负百分之一百零九。", "利润率从-150%改善到-109%"
        self.assertEqual([(x["原稿"], x["转写"]) for x in Q.suspects(Q.qc_tokens(ref), Q.qc_tokens(hyp))], [])
        self.assertEqual(Q.number_mismatches(ref, hyp), [])
        self.assertEqual("".join(Q.qc_tokens("GPT-5 和 10-20 家")), "gpt5和1020家")
        self.assertEqual(self.sus(ref, "利润率从150%改善到109%"), [("负", ""), ("负", "")])   # 真没有"负"才报

    def test_check_carries_todo_only_when_on(self):
        with Env(FD_QC_NUMBERS="on", FD_QC_ASR2="off"):
            self.assertNotIn("待复核", Q.check(REF, HYP))
        with Env(FD_QC_NUMBERS="on", FD_QC_ASR2="on"):
            r = Q.check(REF, HYP)
        self.assertEqual([(x["类"], x["原稿"]) for x in r["待复核"]], [("字词", "害")])
        self.assertFalse(r["需重录"])                                                   # 复核以前不重录


class AlignFit(unittest.TestCase):
    def test_free_ends(self):
        ref, hyp = Q.tokens("前面几个字受到损害正在调查后面"), Q.tokens("到损害正在调")
        ops = Q.align_fit(ref, hyp)
        pos = Q._ref_positions(ops)
        hit = "".join(ref[ri] for op, ri, _ in pos if op == "E")
        self.assertEqual(hit, "到损害正在调")

    def test_window(self):
        times = even_times(HYP, 20.0)
        x = Q.suspects(Q.tokens(REF), Q.tokens(HYP))[0]
        a, b, r0, r1, c0, c1 = Q._clip_window(x, times, len(times))
        mid = times[x["转写起"]][0]
        self.assertAlmostEqual(a, round(max(0.0, mid - Q.ASR2_PAD_S), 2), delta=0.05)
        self.assertGreaterEqual(b - a, Q.ASR2_MIN_CLIP_S)
        self.assertLessEqual(r0, c0)
        self.assertLessEqual(c0, x["起"])
        self.assertGreaterEqual(c1, x["止"])

    def test_whisper_json_times(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a_whisper.json"
            p.write_text(json.dumps({"text": "受到损失正在调查", "segments": [
                {"start": 1.0, "end": 3.0, "text": "受到损失"}, {"start": 3.5, "end": 5.5, "text": "正在调查"}]},
                ensure_ascii=False), encoding="utf-8")
            t = Q.whisper_times(p, 8)
            self.assertEqual(t[0], (1.0, 1.5))
            self.assertEqual(t[4], (3.5, 4.0))
            self.assertEqual(len(Q.whisper_times(p, 16)), 16)          # 对不上时按比例
            self.assertIsNone(Q.whisper_times(Path(d) / "没有.json", 8))


class Confirm(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        for sub in ("SenseVoiceSmall", "paraformer-zh"):
            (d / "models" / sub).mkdir(parents=True)
            (d / "models" / sub / "model.pt").write_text("假的")
        (d / "fake.py").write_text(FAKE, encoding="utf-8")
        (d / "audio.wav").write_bytes(b"RIFF")
        self.audio = d / "audio.wav"
        self.table = d / "table.json"
        self.log = d / "heard.log"
        self.worker0 = Q.ASR2_WORKER
        Q.ASR2_WORKER = d / "fake.py"
        Q._ASR2_ONE.close()
        Q._ASR2_ONE = Q._ASR2()
        self.env = Env(FD_QC_NUMBERS="on", FD_QC_ASR2="on", FD_ASR2_PYTHON=sys.executable,
                       FD_ASR2_MODELS=str(d / "models"), FD_ASR2_CACHE=str(d / "cache"),
                       FAKE_ASR2=str(self.table), FAKE_ASR2_LOG=str(self.log))
        self.env.__enter__()

    def tearDown(self):
        Q._ASR2_ONE.close()
        Q._ASR2_ONE = Q._ASR2()
        Q.ASR2_WORKER = self.worker0
        self.env.__exit__()
        self.tmp.cleanup()

    def answers(self, table):
        self.table.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")

    def run_one(self, ref, hyp, seconds=20.0):
        r = Q.check(ref, hyp)
        start = None
        if r.get("待复核"):
            x = r["待复核"][0]
            times = even_times(hyp, seconds)
            start = str(int(Q._clip_window(x, times, len(times))[0]))
        return r, start, even_times(hyp, seconds)

    def heard(self):
        return self.log.read_text().split() if self.log.exists() else []

    def test_one_model_also_wrong_is_misread(self):
        r, start, times = self.run_one(REF, HYP)
        self.answers({start: {"SenseVoice": "公司说没有理由相信客户的数据受到损害正在调查",
                              "Paraformer": "公司说没有理由相信客户的数据受到损失正在调查"}})
        Q.confirm([(r, REF, self.audio, times)], log=lambda *_: None)
        self.assertTrue(r["需重录"])
        self.assertEqual(len(r["复核念错"]), 1)
        row = r["复核念错"][0]
        self.assertEqual((row["原稿"], row["判"], row["各模型"]), ("害", "念错", {"SenseVoice": "照原稿", "Paraformer": "也不一样"}))
        self.assertIn("复核念错：原稿「害」，Whisper「失」", r["原因"][0])
        self.assertTrue(Q.misread(r) and Q.misread_only(r))
        self.assertNotIn("待复核", r)
        self.assertEqual(list(Q.listen_fields(r)), ["复核念错（请你耳听）"])

    def test_both_models_heard_original(self):
        r, start, times = self.run_one(REF, HYP)
        self.answers({start: {"SenseVoice": "说没有理由相信客户的数据受到损害正在调查", "Paraformer": "相信客户的数据受到损害正在调"}})
        Q.confirm([(r, REF, self.audio, times)], log=lambda *_: None)
        self.assertFalse(r["需重录"])
        self.assertEqual(r["复核"][0]["判"], "转写听错")
        self.assertNotIn("复核念错", r)
        self.assertEqual(Q.listen_fields(r), {})

    def test_garbage_is_not_evidence(self):
        r, start, times = self.run_one(REF, HYP)
        self.answers({start: {"SenseVoice": "音乐", "Paraformer": ""}})
        Q.confirm([(r, REF, self.audio, times)], log=lambda *_: None)
        self.assertFalse(r["需重录"])
        self.assertEqual(r["复核"][0]["判"], "没听清")

    def test_number_overturned(self):
        ref, hyp = "据报道，Alphabet 一共出现了十六次。", "据报道Alphabet一共出现了是6次"
        r, start, times = self.run_one(ref, hyp)
        self.assertTrue(r["需重录"])                                     # 只开数字比对时会重录
        self.answers({start: {"SenseVoice": "alphabet一共出现了16次", "Paraformer": "阿尔法贝特一共出现了十六次"}})
        Q.confirm([(r, ref, self.audio, times)], log=lambda *_: None)
        self.assertFalse(r["需重录"])
        self.assertEqual(r["原因"], [])
        self.assertNotIn("数字不符", r)
        self.assertEqual(r["复核"][0]["判"], "转写听错")

    def test_number_confirmed(self):
        ref, hyp = "它的篇幅很直观，一共一千零九页，写了五十五年。", "它的篇幅很直观一共109页写了55年"
        r, start, times = self.run_one(ref, hyp)
        self.answers({start: {"SenseVoice": "它的篇幅很直观一共109页写了55年", "Paraformer": "它的篇幅很直观一共一百零九页写了五十五年"}})
        Q.confirm([(r, ref, self.audio, times)], log=lambda *_: None)
        self.assertTrue(r["需重录"])
        self.assertEqual(r["数字不符"], [{"原稿": "1009", "转写": "109"}])
        self.assertEqual(r["复核"][0]["各模型"], {"SenseVoice": "也不一样", "Paraformer": "也不一样"})

    def test_number_not_homophone_not_overturned(self):
        """11-15 播客 2:44：两个新模型都听成"一千零九"，可 Whisper 三次都是 109、用户耳听也是 109。
        109 和"一千零九"不同音，不是写法问题：新模型听成原稿也照重录。"""
        ref, hyp = "它的篇幅很直观，一共一千零九页，写了五十五年。", "它的篇幅很直观一共109页写了55年"
        r, start, times = self.run_one(ref, hyp)
        self.assertIs(r["待复核"][0]["同音写法"], False)
        self.answers({start: {"SenseVoice": "它的篇幅很直观一共1009页写了55年", "Paraformer": "它的篇幅很直观一共一千零九页写了五十五年"}})
        Q.confirm([(r, ref, self.audio, times)], log=lambda *_: None)
        self.assertTrue(r["需重录"])
        self.assertEqual(r["复核"][0]["判"], "念错")
        self.assertIn("不同音", r["复核"][0]["说明"])
        self.assertTrue(Q.misread(r))

    def test_worker_missing(self):
        with Env(FD_ASR2_PYTHON="/没有这个/python"):
            Q._ASR2_ONE = Q._ASR2()
            ref = "一共一千零九页，数据受到损害。"
            hyp = "一共109页数据受到损失"
            r = Q.check(ref, hyp)
            Q.confirm([(r, ref, self.audio, even_times(hyp, 10.0))], log=lambda *_: None)
        self.assertTrue(r["需重录"])
        self.assertEqual([x.split("：")[0] for x in r["原因"]], ["数字不符"])   # 数字照旧重录，字词不重录
        self.assertEqual({x["判"] for x in r["复核"]}, {"没复核"})
        self.assertIn("没有第二个听写模型的环境", r["复核"][1]["说明"])

    def test_load_failure(self):
        r, start, times = self.run_one(REF, HYP)
        self.answers({"_fail_load": True})
        Q.confirm([(r, REF, self.audio, times)], log=lambda *_: None)
        self.assertFalse(r["需重录"])
        self.assertIn("载入失败", r["复核"][0]["说明"])

    def test_cache(self):
        r, start, times = self.run_one(REF, HYP)
        self.answers({start: {"SenseVoice": "受到损害正在调查", "Paraformer": "受到损害正在调查"}})
        Q.confirm([(r, REF, self.audio, times)], log=lambda *_: None)
        r2 = Q.check(REF, HYP)
        Q.confirm([(r2, REF, self.audio, times)], log=lambda *_: None)
        self.assertEqual(self.heard(), [start])                          # 第二次读缓存，不再听
        self.assertEqual(r2["复核"][0]["判"], "转写听错")

    def test_switch_off_noop(self):
        r, _, times = self.run_one(REF, HYP)
        with Env(FD_QC_ASR2="off"):
            Q.confirm([(r, REF, self.audio, times)], log=lambda *_: None)
        self.assertNotIn("复核", r)
        self.assertEqual(self.heard(), [])
        self.assertIsNone(Q._ASR2_ONE.state)                              # 进程都没起


if __name__ == "__main__":
    unittest.main()
