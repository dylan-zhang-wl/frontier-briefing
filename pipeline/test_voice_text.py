#!/usr/bin/env python3
"""配音写法（读音表的"配音写法"一栏，pipeline/tts.py 的 voice_text）的测试（2026-11-07 加）。

为什么有这一栏：11-07 视频旁白定案章把 DRAM 念成了一个音节的英文词 dram；读音表把 DRAM 改成"配音写法: D-RAM"，
配音程序发给模型前换成 D-RAM（实测念 dee-ram），稿子、字幕、对稿都还是 DRAM。这里查：
  · 读音表里 DRAM 的规则在、换得对（3D DRAM、DRAM-on-logic 换，SDRAM、小写 dram、RAM 不换）；
  · 别的词也能用（任何分类、"也可写"、不区分大小写、长的先换），不是只为 DRAM 写死；
  · 内容指纹：没有要换的词时和 11-07 以前一模一样（旧缓存照用），有要换的词时按换过的文字算；
  · 送去模型的是换过的字，对稿（tts_qc.check）比的仍是原稿；周日对谈（dialog_tts._synth_one）同样换；
  · 读音表坏了不报错、不换。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_voice_text.py
    ~/.venvs/frontier-daily/bin/python pipeline/test_voice_text.py        # 全部通过时退出码为 0
不调用任何模型，不花钱；读写只在临时目录（配音缓存也指到临时目录）。
"""
import hashlib
import io
import json
import sys
import tempfile
import threading
import unittest
import wave
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

import tts  # noqa: E402

DINGAN = ("对手早就在做 3D DRAM，三星内部已经完成 16 层堆叠验证。从十一月六日的报道算起，"
          "台积电路线图上的 DRAM-on-logic，排在二零二九年。")


def say(text, forms=None):
    return tts.voice_text(text, forms)[0]


def tiny_wav(seconds=0.5, rate=24000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


class FakeEngine:
    """假的配音引擎：记下收到的文字，回一段静音。"""

    def __init__(self):
        self.sent = []

    def synthesize(self, text, *a, **k):
        self.sent.append(text)
        return tiny_wav(), {"engine": "gemini", "seconds_audio": 0.5, "seconds_wall": 0.0, "cost_usd": 0.0,
                            "finish_reason": "STOP"}


def gemini_cfg(style="calm"):
    return tts.VoiceConfig("gemini", "flash", "voice_test", style)


def write_lexicon(d, text):
    p = Path(d) / "读音表.yaml"
    p.write_text(text, encoding="utf-8")
    return p


class Lexicon(unittest.TestCase):
    """项目里的读音表：DRAM 的配音写法。"""

    def test_dram_rule_in_table(self):
        rules = {(f, to) for f, to, _ in tts.voice_forms()}
        self.assertIn(("DRAM", "D-RAM"), rules)

    def test_dram_entry_documents_reading(self):
        import yaml
        d = yaml.safe_load(tts.LEXICON.read_text(encoding="utf-8"))
        e = [x for x in d["其他"] if x.get("写法") == "DRAM"]
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["配音写法"], "D-RAM")
        self.assertIn("dee-ram", e[0]["读音"])
        self.assertNotIn("DRAM", d["缩写"]["按单词读"])       # 挪到"其他"了，不再写成"按单词读"

    def test_claude_candidate_not_active(self):
        """Claude 的 Klawd 只记在"配音写法（待启用）"，程序不认：配音照原写法 Claude（11-09，待用户耳听后启用）。"""
        import yaml
        self.assertNotIn("Claude", {f for f, _, _ in tts.voice_forms()})
        self.assertEqual(say("Claude Code 和 Claude"), "Claude Code 和 Claude")
        d = yaml.safe_load(tts.LEXICON.read_text(encoding="utf-8"))
        e = [x for sec in d.values() if isinstance(sec, list) for x in sec if isinstance(x, dict) and x.get("写法") == "Claude"]
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0].get("配音写法（待启用）"), "Klawd")
        self.assertNotIn("配音写法", e[0])

    def test_ternus_thurrock_not_active(self):
        """11-09 晚实测：Ternus、Thurrock 原写法这次都没念错，候选没显出更好，都没启用（Ternus 的 Tur-nus 记在单列一条的
        "配音写法（待启用）"，Thurrock 没定配音写法）：配音照原写法，送去模型的字一个不动。"""
        import yaml
        active = {f for f, _, _ in tts.voice_forms()}
        self.assertFalse(active & {"Ternus", "John Ternus", "Thurrock"})
        s = "苹果 CEO John Ternus 正在施压。Ternus 在公开场合……伦敦以东约二十四公里的 Thurrock。"
        self.assertEqual(say(s), s)
        d = yaml.safe_load(tts.LEXICON.read_text(encoding="utf-8"))
        rows = [x for sec in d.values() if isinstance(sec, list) for x in sec if isinstance(x, dict)]
        t = [x for x in rows if x.get("写法") == "Ternus"]
        self.assertEqual(len(t), 1)
        self.assertEqual(t[0].get("配音写法（待启用）"), "Tur-nus")
        self.assertNotIn("配音写法", t[0])
        j = [x for x in rows if x.get("写法") == "John Ternus"]
        self.assertEqual(len(j), 1)
        self.assertIn("TUR-nəs", j[0]["读音"])
        self.assertNotIn("配音写法", j[0])           # 人名条目不写配音写法：会把"John Ternus"整个换成一个词
        r = [x for x in d["其他"] if x.get("写法") == "Thurrock"]
        self.assertEqual(len(r), 1)
        self.assertIn("THUR-ək", r[0]["读音"])
        self.assertFalse({"配音写法", "配音写法（待启用）"} & set(r[0]))

    def test_groot_fable_not_active_1110(self):
        """11-10 实测：GR00T 的 Groot 念成一个音节，但转写只有一条是 Groot，只记在"配音写法（待启用）"；Fable 原写法这次
        4 条都念出来了，没定配音写法。配音照原写法，送去模型的字一个不动。"""
        import yaml
        active = {f for f, _, _ in tts.voice_forms()}
        self.assertFalse(active & {"GR00T", "GR00T 2", "Claude Fable 5.2", "Claude Fable", "Fable 5.2", "Fable",
                                   "Marco Rubio", "Rubio", "LingBot-Touch"})
        s = "英伟达发布了 GR00T 2。正在筹备上市的 Anthropic，发布了 Claude Fable 5.2。美国国务卿 Marco Rubio。LingBot-Touch。"
        self.assertEqual(say(s), s)
        d = yaml.safe_load(tts.LEXICON.read_text(encoding="utf-8"))
        g = [x for x in d["产品"] if x.get("写法") == "GR00T"]
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0].get("配音写法（待启用）"), "Groot")
        self.assertNotIn("配音写法", g[0])
        self.assertNotIn("也可写", g[0])             # 单列一个词：启用后"GR00T 2"换成"Groot 2"，版本号留着
        f = [x for x in d["产品"] if x.get("写法") == "Claude Fable 5.2"]
        self.assertEqual(len(f), 1)
        self.assertIn("FAY-bəl", f[0]["读音"])
        self.assertFalse({"配音写法", "配音写法（待启用）"} & set(f[0]))

    def test_groot_if_enabled(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_lexicon(d, "产品:\n  - 写法: GR00T\n    配音写法: Groot\n")
            forms = tts.voice_forms(p, log=lambda *_: None)
            self.assertEqual(say("发布了 GR00T 2，", forms), "发布了 Groot 2，")
            self.assertEqual(say("GR00Tx 不换", forms), "GR00Tx 不换")

    def test_ternus_single_word_entry_if_enabled(self):
        """Ternus 单列一个词的用意：启用后（"配音写法（待启用）"改名成"配音写法"）全名、只说姓都换，John 留着。"""
        with tempfile.TemporaryDirectory() as d:
            p = write_lexicon(d, "其他:\n  - 写法: Ternus\n    配音写法: Tur-nus\n")
            forms = tts.voice_forms(p, log=lambda *_: None)
            self.assertEqual(say("苹果 CEO John Ternus 说，Ternus 认为", forms), "苹果 CEO John Tur-nus 说，Tur-nus 认为")
            self.assertEqual(say("Ternusx 不换", forms), "Ternusx 不换")

    def test_dingan_chapter(self):        # 11-07 定案章念错的两处
        out, subs = tts.voice_text(DINGAN)
        self.assertIn("3D D-RAM，", out)
        self.assertIn("的 D-RAM-on-logic，", out)
        self.assertNotIn(" DRAM", out)
        self.assertEqual(subs, [{"写法": "DRAM", "配音写法": "D-RAM", "处数": 2}])
        self.assertEqual(out.replace("D-RAM", "DRAM"), DINGAN)           # 别的字一个不动

    def test_whole_words_only(self):
        self.assertEqual(say("SDRAM 和 DRAMs"), "SDRAM 和 DRAMs")         # 前后紧挨字母的不算
        self.assertEqual(say("RAM、HBM5E、DDR5"), "RAM、HBM5E、DDR5")
        self.assertEqual(say("dram 是亚美尼亚货币"), "dram 是亚美尼亚货币")   # DRAM 这一条区分大小写
        self.assertEqual(say("HBM-DRAM 混合"), "HBM-D-RAM 混合")            # 连字符不算字母
        self.assertEqual(say("（DRAM）"), "（D-RAM）")

    def test_tags_untouched(self):
        s = "<short pause> 3D DRAM（轻笑）"
        self.assertEqual(say(s), "<short pause> 3D D-RAM（轻笑）")
        self.assertEqual(tts.spoken(say(s)).strip(), "3D D-RAM")

    def test_already_spelled(self):       # 稿子里已经是 D-RAM 的，不会再变
        self.assertEqual(say("3D D-RAM"), "3D D-RAM")


class Generic(unittest.TestCase):
    """规则从读音表读，任何分类、任何词都能用。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = write_lexicon(self.tmp.name, (
            "版本: 测试\n"
            "产品:\n"
            "  - 写法: Foo Bar\n"
            "    也可写: [FooBar]\n"
            "    配音写法: Foo-Bar\n"
            "  - 写法: Foo\n"
            "    配音写法: Fu\n"
            "媒体:\n"
            "  - 写法: APPSO\n"
            "    也可写: [AppSo]\n"
            "  - 写法: XYZ\n"
            "    配音写法: X-Y-Z\n"
            "    区分大小写: true\n"
            "缩写:\n"
            "  按字母读: [AI]\n"))
        self.forms = tts.voice_forms(self.p, log=lambda *_: None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_any_category_and_aliases(self):
        self.assertEqual(say("用 foobar 和 Foo  Bar", self.forms), "用 Foo-Bar 和 Foo-Bar")   # 不分大小写、空格可多可少
        self.assertEqual(say("Foo 单独出现", self.forms), "Fu 单独出现")
        self.assertEqual(say("Foo Bar 先换长的", self.forms), "Foo-Bar 先换长的")
        self.assertEqual(say("XYZ 和 xyz", self.forms), "X-Y-Z 和 xyz")
        self.assertEqual(say("APPSO 没写配音写法", self.forms), "APPSO 没写配音写法")

    def test_reload_after_edit(self):
        self.p.write_text("其他:\n  - 写法: Foo\n    配音写法: Fuu\n", encoding="utf-8")
        import os
        st = self.p.stat()
        os.utime(self.p, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
        self.assertEqual(say("Foo", tts.voice_forms(self.p, log=lambda *_: None)), "Fuu")

    def test_broken_table_does_not_stop(self):
        bad = write_lexicon(self.tmp.name, "版本: 坏的: 这里多了冒号\n")
        logs = []
        self.assertEqual(tts.voice_forms(bad, log=logs.append), [])
        self.assertTrue(logs and "读不了" in logs[0])
        self.assertEqual(tts.voice_forms(Path(self.tmp.name) / "没有这个.yaml", log=logs.append), [])


class Fingerprint(unittest.TestCase):
    """内容指纹（配音缓存的文件名）。"""

    @staticmethod
    def old_key(cfg, text, take):       # 11-07 以前的算法
        blob = json.dumps([cfg.ident(), text, take], ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:20]

    def test_unchanged_without_subs(self):
        cfg = gemini_cfg()
        for s in ("台积电回应说，不评论市场传闻。", "SK 海力士和 HBM5E", "Counterpoint Research 说"):
            for t in range(3):
                self.assertEqual(tts._key(cfg, s, t), self.old_key(cfg, s, t))

    def test_follows_sent_text(self):
        cfg = gemini_cfg()
        self.assertNotEqual(tts._key(cfg, DINGAN, 0), self.old_key(cfg, DINGAN, 0))
        self.assertEqual(tts._key(cfg, DINGAN, 0), self.old_key(cfg, say(DINGAN), 0))


class SentToModel(unittest.TestCase):
    """送去模型的是换过的字；对稿比原稿；对谈也换。配音缓存指到临时目录。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache0 = tts.CACHE
        tts.CACHE = Path(self.tmp.name)
        (tts.CACHE / "chunks").mkdir(parents=True)

    def tearDown(self):
        tts.CACHE = self.cache0
        self.tmp.cleanup()

    def test_synth(self):
        eng = FakeEngine()
        _, usage = tts._synth(eng, gemini_cfg(), DINGAN)
        self.assertEqual(eng.sent, [say(DINGAN)])
        self.assertEqual(usage["配音写法"][0]["处数"], 2)
        eng2 = FakeEngine()
        _, usage2 = tts._synth(eng2, gemini_cfg(), "没有要换的词。")
        self.assertEqual(eng2.sent, ["没有要换的词。"])
        self.assertNotIn("配音写法", usage2)

    def test_synth_mimo(self):
        eng = FakeEngine()
        tts._synth(eng, tts.VoiceConfig("mimo", voice="冰糖", style="平稳"), "3D DRAM")
        self.assertEqual(eng.sent, ["3D D-RAM"])

    def test_taker_checks_against_original(self):
        Q = tts.Q
        seen, t0, c0 = {}, Q.transcribe, Q.check

        def fake_transcribe(raw, wdir):
            return "对手早就在做3D DRAM"

        def spy_check(ref, hyp, *a, **k):
            seen["ref"] = ref
            return c0(ref, hyp, *a, **k)
        Q.transcribe, Q.check = fake_transcribe, spy_check
        try:
            logs = []
            tk = tts._Taker(tts.Ledger(1.0), fresh=False, qc=True, retakes=0, log=logs.append)
            tk.engine = FakeEngine()
            text = "对手早就在做 3D DRAM"
            r = tk.one(gemini_cfg(), text, 2.0, 0, "块1", 1)
        finally:
            Q.transcribe, Q.check = t0, c0
        self.assertEqual(tk.engine.sent, ["对手早就在做 3D D-RAM"])
        self.assertEqual(seen["ref"], text)                         # 对稿用原稿
        self.assertEqual(r["key"], tts._key(gemini_cfg(), text, 0))
        self.assertTrue((tts.CACHE / "chunks" / f"{r['key']}.wav").exists())
        self.assertTrue(any("DRAM → D-RAM" in x for x in logs))
        self.assertIn("配音写法", json.loads((tts.CACHE / "chunks" / f"{r['key']}.json").read_text(encoding="utf-8")))

    def test_dialog_uses_same_place(self):
        import dialog_tts
        cache0 = dialog_tts.CACHE
        dialog_tts.CACHE = tts.CACHE
        eng = FakeEngine()

        class Run:
            fresh, lock, new_keys = False, threading.Lock(), set()

            class ledger:
                @staticmethod
                def add(x):
                    pass

            @staticmethod
            def engine(cfg):
                return eng
        try:
            unit = {"cfg": gemini_cfg(), "text": "乙：不，3D DRAM 是把存储单元垂直堆起来。"}
            rec = dialog_tts._synth_one(Run, unit, 0)
        finally:
            dialog_tts.CACHE = cache0
        self.assertEqual(eng.sent, ["乙：不，3D D-RAM 是把存储单元垂直堆起来。"])
        self.assertEqual(rec["key"], tts._key(unit["cfg"], unit["text"], 0))


if __name__ == "__main__":
    unittest.main(verbosity=1)
