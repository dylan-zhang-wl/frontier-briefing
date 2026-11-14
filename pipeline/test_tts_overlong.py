#!/usr/bin/env python3
"""配音废条（实际时长超过按字数估计的 2 倍、而且多出 30 秒以上）直接丢、不转写的测试（2026-11-14 加，经验库第 71 件①）。

为什么：11-11 播客块 1 为音高重录的第 2 条，Gemini 多念了 612 个字，181.5 秒（估计 55 秒），照旧整条转写（云端约 1 秒
音频 1 秒），白花 3 分钟才判出"多念""时长异常"。现在配完量了时长就判废条：不转写、不量音高音色，当"需重录"——
先占对稿的重录次数（retakes），把关时挑出来的还是废条，再占"最多再录"；都用完了还是废条才补量一次、标需人工复听。
音高允许值（1.5 个半音）不动。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_tts_overlong.py
假的配音引擎（按给定的秒数回一段静音）、假的转写、假的量音高；不调 Gemini、不跑 Whisper，不花钱；缓存指到临时目录。
"""
import io
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

import tts  # noqa: E402
import tts_qc as Q  # noqa: E402

TEXT = "大家好，我是 Shirley。今天是十一月十一日，先看三件事。"
GATE = {"允许偏差半音": 1.5, "最多再录": 2, "有声不足秒不判": 1.2, "语速允许偏差": 0.10}


def tiny_wav(rate=24000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * 2400)
    return buf.getvalue()


class SecondsEngine:
    """假的配音引擎：第 n 次调用回报 seconds[n] 秒（音频本身只是 0.1 秒静音，程序按回报的秒数判时长）。"""

    def __init__(self, seconds):
        self.seconds, self.calls = list(seconds), 0

    def synthesize(self, text, *a, **k):
        s = self.seconds[min(self.calls, len(self.seconds) - 1)]
        self.calls += 1
        return tiny_wav(), {"engine": "gemini", "seconds_audio": s, "seconds_wall": 0.0, "cost_usd": 0.0,
                            "finish_reason": "STOP"}


class Overlong(unittest.TestCase):
    def test_thresholds(self):
        self.assertIn("当废条丢掉重录", Q.overlong(181.5, 55))           # 11-11 那条
        self.assertTrue(Q.overlong(111, 55))                              # 2.02 倍、多 56 秒
        self.assertIsNone(Q.overlong(110, 55))                            # 正好 2 倍不算
        self.assertIsNone(Q.overlong(100, 55))                            # 1.8 倍：照旧转写
        self.assertIsNone(Q.overlong(25, 10))                             # 2.5 倍但只多 15 秒（短块）：照旧转写，由 check() 判
        self.assertIsNone(Q.overlong(None, 55))
        self.assertIsNone(Q.overlong(181.5, 0))

    def test_discarded_result_shape(self):
        r = Q.discarded(181.5, 55, Q.overlong(181.5, 55))
        self.assertTrue(r["需重录"] and r["废条"] and r["没转写"])
        self.assertEqual(r["时长比"], 3.3)
        self.assertIn("时长异常：实际 182 秒，估计 55 秒", r["原因"][0])
        self.assertEqual(Q.badness(r), (True, 0, float("inf")))     # 没转写、字错率空着也能比（排序靠 pick_take 看"废条"，见下）


class Series(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache0 = tts.CACHE
        tts.CACHE = Path(self.tmp.name) / "tts"
        (tts.CACHE / "chunks").mkdir(parents=True)
        self.t0, self.heard = Q.transcribe, []

        def fake_transcribe(raw, wdir):
            self.heard.append(raw)
            return tts.spoken(TEXT)                     # 转写出来和原稿一字不差
        Q.transcribe = fake_transcribe
        self.logs = []

    def tearDown(self):
        Q.transcribe = self.t0
        tts.CACHE = self.cache0
        self.tmp.cleanup()

    def taker(self, seconds, retakes=1):
        tk = tts._Taker(tts.Ledger(1.0), fresh=False, qc=True, retakes=retakes, log=self.logs.append, gate=GATE)
        tk.engine = SecondsEngine(seconds)
        return tk

    def measure(self, over):
        """假的量音高：over 里列的第几条判"超出"。记下量了哪几条。"""
        self.measured = []

        def m(tk):
            self.measured.append(tk["take"])
            bad = tk["take"] in over
            return {"音高": {"音高中位数Hz": 195.0 if bad else 160.0, "参考Hz": 164.0,
                           "偏差半音": 3.0 if bad else -0.4, "超出": bad}}
        return m

    def test_waste_not_transcribed_then_retake(self):
        """第 1 条 181.5 秒（估计 55 秒）：不转写，直接重录；第 2 条正常，选第 2 条。"""
        t = self.taker([181.5, 50.0])
        takes, best, info = t.series(tts.VoiceConfig("gemini", "flash", "voice_test", "calm"), TEXT, 55.0, "块1", 1)
        self.assertEqual(len(takes), 2)
        self.assertEqual(len(self.heard), 1)                         # 只转写了第 2 条
        self.assertTrue(takes[0]["废条"] and takes[0]["qc"]["没转写"])
        self.assertEqual(best["take"], 2)
        self.assertFalse(best["qc"]["需重录"])
        self.assertIsNone(info)
        self.assertTrue(any("当废条丢掉重录" in x for x in self.logs))

    def test_1111_case_pitch_retake_is_waste(self):
        """照 11-11 块 1：第 1 条音高超出 → 为音高重录的第 2 条是 181.5 秒的废条（不转写、不量）→ 再为音高重录第 3 条，选第 3 条。
        重录次数和原来一样（为音高再录 2 次，用满"最多再录"），只是第 2 条不再白转写 3 分钟。"""
        t = self.taker([45.5, 181.5, 51.7])
        takes, best, info = t.series(tts.VoiceConfig("gemini", "flash", "voice_test", "calm"), TEXT, 55.0, "块1", 1,
                                     self.measure(over={1}))
        self.assertEqual([x["take"] for x in takes], [1, 2, 3])
        self.assertEqual(len(self.heard), 2)                         # 第 2 条没转写
        self.assertEqual(self.measured, [1, 3])                      # 第 2 条也没量音高
        self.assertEqual(best["take"], 3)
        self.assertEqual(info["为音高再录"], 2)
        self.assertNotIn("为废条再录", info)
        self.assertEqual(t.engine.calls, 3)

    def test_all_waste_uses_existing_caps_then_flags(self):
        """一直是废条：对稿重录 1 次（retakes），再占"最多再录"2 次，一共配 4 条就停；最后补量一次选中的那条，需人工听。"""
        t = self.taker([200.0])
        takes, best, info = t.series(tts.VoiceConfig("gemini", "flash", "voice_test", "calm"), TEXT, 55.0, "块1", 1,
                                     self.measure(over=set()))
        self.assertEqual(t.engine.calls, 4)
        self.assertEqual(len(self.heard), 0)
        self.assertEqual(info["为废条再录"], 2)
        self.assertTrue(best["废条"] and best["qc"]["需重录"])
        self.assertEqual(self.measured, [best["take"]])               # 补量的就是选中的那条（整段合成要靠它切章）
        self.assertIn("都是废条", info["说明"])
        self.assertEqual(tts._gate_fields(best, info, {"音高Hz": 164.0})["为废条再录"], 2)

    def test_short_overrun_still_transcribed(self):
        """短块 2 倍出头、只多十几秒：照旧转写，由 check() 的"时长异常"判需重录（和原来一样）。"""
        t = self.taker([25.0, 9.0], retakes=1)
        short = "先看三件事。"
        takes, best, _ = t.series(tts.VoiceConfig("gemini", "flash", "voice_test", "calm"), short, 10.0, "块1", 1)
        self.assertEqual(len(self.heard), 2)
        self.assertFalse(takes[0].get("废条"))
        self.assertTrue(any("时长异常" in r for r in takes[0]["qc"]["原因"]))


class Pick(unittest.TestCase):
    @staticmethod
    def take(n, need, cer=0.0, waste=False, dev=None):
        qc = Q.discarded(200, 55, "废") if waste else {"需重录": need, "最长多出": 9 if need else 0, "最长少掉": 0, "字错率": cer}
        x = {"take": n, "qc": qc}
        if waste:
            x["废条"] = True
        if dev is not None:
            x["音高"] = {"偏差半音": dev, "超出": abs(dev) > 1.5}
        return x

    def test_waste_ranks_after_transcribed(self):
        """废条排在转写过的各条后面，哪怕那条对稿也不过、音高也超出。"""
        ts = [self.take(1, False, waste=True), self.take(2, True, cer=0.5, dev=3.0)]
        self.assertEqual(tts.pick_take(ts)["take"], 2)

    def test_no_waste_same_as_before(self):
        ts = [self.take(1, False, dev=2.0), self.take(2, False, dev=0.3), self.take(3, True, dev=0.0)]
        self.assertEqual(tts.pick_take(ts)["take"], 2)


if __name__ == "__main__":
    unittest.main()
