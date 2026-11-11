#!/usr/bin/env python3
"""对稿的"英文名漏念"一项（pipeline/tts_qc.py 的 name_drops，2026-11-10 加）的测试。

为什么有它：11-10 云端那期视频 21 秒"发布了 Claude Fable 5.2"，Fable 整个没念（用户耳听确认），转写是"Cloud 5.2"。
少一个英文词只算一两个错字，专名读音清单也只认"念成了什么"，认不出"没念"，原来的对稿全放过了。这里查：
  · 那一块（转写原样取自 本机资料/成品/2026-11-10/11_视频v3_导演/终版_配音/qc.json 第 2 块）判"要重录"，原因写"英文名漏念：……"；
  · 转写把名字拼成别的样子（Anthrobic、Sherly、Fabel、Faber、Growth）、写成汉字音译（奥特曼）、连写或拆开
    （HuggingFace、Deep Seek、LingBot Touch）、GR00T 写成 GROOT、有已知误读（Claude 转写成 cloud）的，都不算漏念；
  · 读音表里没有的名字不查；读音表读不了就不查这一项；没命中时结果和原来一模一样（没有"英文名漏念"这一栏）；
  · 用户最初说的"一次都没出现"单独一条会误报一大片：这里用往期的例子说明为什么还要第二条（对上的转写里没有英文字母、也没有汉字）；
  · 有 mini 试运行那周的 qc.json（本机 本机资料/归档/，不进 git）时，再用真转写跑一遍：一块都不命中。
    有 11-10 云端那期（本机 本机资料/成品/2026-11-10/）时：只命中视频 Fable 那一块。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_tts_qc_drops.py
不调用任何模型、不转写、不花钱。
"""
import json
import os
import re
import sys
import tempfile
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
_CLOUD = [b.parents[1] / "成品" / "2026-11-10" for b in _BASES] + [PIPE.parent / "本机资料" / "成品" / "2026-11-10"]
CLOUD_1110 = next((c for c in _CLOUD if c.exists()), _CLOUD[-1])     # 本机资料/成品/2026-11-10（FD_SAMPLE_ROOT 旁边）
TAG = re.compile(r"[（(\[]\s*[㐀-鿿][㐀-鿿，、 ]{0,11}\s*[）)\]]|<\s*[A-Za-z][A-Za-z \-]{0,30}\s*>")

# 11-10 云端那期视频旁白（导演版终版配音）第 2 块：原稿是配音用的念法，转写原样
REF_1110 = ("正在筹备上市的 Anthropic，发布了 Claude Fable 5.2。九月，一位研究员带着几十个智能体，用十一天首次完成了"
            "费马大定理证明的形式化。这一次，一千个智能体跑着它的早期版本，各自在不联网的沙箱里，只用二十八点七小时就复现了"
            "这份证明。公司的说法是，这个小实验表明，智能体团队可以在精心设计的安全边界内，完成有雄心的长程目标。")
HYP_1110 = ("正在筹备上市的Anthropic发布了Cloud 5.29月,一位研究员带着几十个智能体用11天首次完成了费马大定理证明的形式化"
            "这一次,1000个智能体跑着它的早期版本各自在不联网的沙箱里只用28.7小时就复现了这份证明公司的说法是,"
            "这个小实验表明智能体团队可以在精心设计的安全边界内完成有雄心的长城目标")


def lex(text):
    d = Path(tempfile.mkdtemp())
    p = d / "读音表.yaml"
    p.write_text(text, encoding="utf-8")
    return Q.load_lexicon_names(p)


TINY = lex("""人名:
  - 写法: Sam Altman
    之后: Altman
产品:
  - 写法: Claude
  - 写法: Claude Fable 5.2
    也可写: [Claude Fable, Fable 5.2, Fable]
  - 写法: GR00T
  - 写法: LingBot-Touch
公司:
  - 写法: Anthropic
  - 写法: Hugging Face
  - 写法: DeepSeek
  - 写法: 英伟达
    应改: [NVIDIA]
""")


def drops(ref, hyp, lexicon=TINY, **kw):
    return [(x["名字"], x["原稿"], x["转写"]) for x in Q.name_drops(ref, hyp, lexicon=lexicon, **kw)]


class Today(unittest.TestCase):
    """11-10 视频 Fable 那一块（用项目里的读音表和专名读音清单）。"""

    def test_fable_flagged(self):
        r = Q.check(REF_1110, HYP_1110)
        self.assertLess(r["字错率"], Q.CER_LIMIT)               # 原来的线拦不住
        self.assertTrue(r["需重录"])
        self.assertEqual([(x["名字"], x["原稿"], x["转写"]) for x in r["英文名漏念"]],
                         [("Claude Fable 5.2", "claude fable 5.2", "cloud 5.2")])
        self.assertIn("英文名漏念：Claude Fable 5.2（原稿 claude fable 5.2，转写 cloud 5.2），重录一次；还在就请你耳听", r["原因"])
        self.assertNotIn("专名读音", [x.split("：")[0] for x in r["原因"]])   # Claude→cloud 只提醒，不另算要重录
        self.assertTrue(Q.badness(r)[0])

    def test_trial_takes_not_flagged(self):
        """11-10 试配（原写法、前面垫"新模型"各两条）两个转写模型的结果：Fable、Fabel、Faber 都算念到了。"""
        for name in ("Claude Fable", "Cloud Fable", "Claude Fabel", "Claude Faber", "Cloud Faber"):
            hyp = f"正在筹备上市的Anthropic发布了{name} 5.29月,一位研究员带着几十个智能体"
            self.assertEqual(Q.name_drops(REF_1110[:60], hyp), [], name)

    def test_retake_prefers_clean_take(self):
        good = HYP_1110.replace("Cloud 5.2", "Claude Fable 5.2")
        self.assertLess(Q.badness(Q.check(REF_1110, good)), Q.badness(Q.check(REF_1110, HYP_1110)))


class NoFalseAlarm(unittest.TestCase):
    def test_spelled_differently(self):
        self.assertEqual(drops("据 Anthropic 官方说", "据Anthrobic官方说"), [])
        self.assertEqual(drops("发布了 Claude Fable 5.2。", "发布了Claude Faber 5.2"), [])
        self.assertEqual(drops("开源了 LingBot-Touch，", "开源了Limbo Touch"), [])     # 拼法差太多，但字母还在
        self.assertEqual(drops("发布了 GR00T 2，", "发布了Growth 2"), [])

    def test_transliterated_in_hanzi(self):
        """转写写成汉字音译：不是没念（10-31、11-01 Altman 转写成"奥特曼"）。"""
        self.assertEqual(drops("OpenAI 的 CEO Sam Altman 说，Altman 认为", "OpenAI的CEO萨姆奥特曼说奥特曼认为"), [])

    def test_joined_or_split(self):
        self.assertEqual(drops("在 Hugging Face 上开源", "在HuggingFace上开源"), [])
        self.assertEqual(drops("DeepSeek 发布", "Deep Seek发布"), [])
        self.assertEqual(drops("开源了 LingBot-Touch，", "开源了Lingbot Touch"), [])

    def test_zero_as_o(self):
        self.assertEqual(drops("发布了 GR00T 2，", "发布了GROOTR"), [])       # 11-10 播客第 7 块第 2 条
        self.assertEqual(drops("发布了 GR00T 2，", "发布了GR00T2"), [])

    def test_known_misread_counts_as_said(self):
        """Claude 转写成 cloud：专名读音清单里的已知误读，算念到了（念得对不对归专名读音那一项）。"""
        names = Q.load_names()
        self.assertEqual(drops("看科学家都拿 Claude 做什么。", "看科学家都拿Cloud做什么", names=names), [])
        # 清单不在：cloud 也不认，但"cloud"字母够多，照样不算被吞
        self.assertEqual(drops("看科学家都拿 Claude 做什么。", "看科学家都拿Cloud做什么", names=[]), [])

    def test_said_elsewhere_in_block(self):
        """同一块里别处念到了（转写里出现过）：不算。只照"一次都没出现"这一条，同一个名字念了一次就够。"""
        self.assertEqual(drops("Anthropic 说，Anthropic 认为", "Anthropic说认为"), [])

    def test_not_in_lexicon_or_chinese_name(self):
        self.assertEqual(drops("Mythos 5.2 找到的漏洞", "找到的漏洞"), [])          # 表里没有
        self.assertEqual(drops("英伟达发布了", "发布了"), [])                      # 中文写法不查

    def test_clean_result_unchanged(self):
        r = Q.check("今天是十一月十日。", "今天是11月10日")
        self.assertNotIn("英文名漏念", r)
        self.assertFalse(r["需重录"])
        self.assertEqual(r["原因"], [])

    def test_bad_or_missing_lexicon(self):
        d = Path(tempfile.mkdtemp())
        (d / "bad.yaml").write_text("人名: [\n", encoding="utf-8")
        self.assertEqual(Q.load_lexicon_names(d / "bad.yaml"), [])
        self.assertEqual(Q.load_lexicon_names(d / "无.yaml"), [])
        self.assertEqual(Q.name_drops(REF_1110, HYP_1110, lexicon=[]), [])


class Catches(unittest.TestCase):
    def test_word_swallowed(self):
        self.assertEqual(drops("发布了 Claude Fable 5.2。", "发布了Cloud 5.2"),
                         [("Claude Fable 5.2", "claude fable 5.2", "cloud 5.2")])
        self.assertEqual(drops("据 Anthropic 官方说", "据官方说"), [("Anthropic", "anthropic", "")])

    def test_only_first_literal_rule_would_overflag(self):
        """只照"一次都没出现"会把拼错的也算进来（往期 279 块里 76 块）；加了第二条，拼错的不算。"""
        lexicon = TINY
        hyp = "据Anthrobic官方说"
        self.assertFalse(any(f in Q._squash(hyp) for e in lexicon if e["名字"] == "Anthropic" for f in e["认"]))  # 第一条成立
        self.assertEqual(drops("据 Anthropic 官方说", hyp), [])                                                  # 第二条不成立


class LexiconFile(unittest.TestCase):
    def test_real_lexicon_has_todays_names(self):
        got = {e["名字"] for e in Q.load_lexicon_names()}
        for n in ("Claude Fable 5.2", "GR00T", "Marco Rubio", "LingBot-Touch", "Claude", "Anthropic"):
            self.assertIn(n, got)


@unittest.skipUnless((SAMPLE / "2026-11-09").exists(), "这台机器上没有 mini 试运行那周的 qc.json（在本机 本机资料/归档/ 里，不进 git）")
class RealArchive(unittest.TestCase):
    """mini 试运行那周各期（不含 _带音效）：一块都不命中（11-10 评估时的结果）。"""

    def test_no_hits(self):
        hit = []
        for f in sorted(SAMPLE.glob("*/05_配音/*/qc.json")):
            if "带音效" in f.parent.name:
                continue
            d = json.loads(f.read_text(encoding="utf-8"))
            for b in (d.get("各块") or []) + (d.get("各轮") or []):
                for t in b.get("各条") or []:
                    if t.get("转写") is not None and Q.name_drops(TAG.sub("", b["原稿"]), t["转写"]):
                        hit.append((f.parts[-4], f.parent.name, b.get("块", b.get("轮")), t["第几条"]))
        self.assertEqual(hit, [])


@unittest.skipUnless((CLOUD_1110 / "11_视频v3_导演" / "终版_配音" / "qc.json").exists(),
                     "这台机器上没有 11-10 云端那期的成品（本机 本机资料/成品/2026-11-10/，不进 git）")
class Real1110(unittest.TestCase):
    def test_only_fable_block(self):
        hit = []
        for f in sorted(CLOUD_1110.glob("05_配音/*/qc.json")) + [CLOUD_1110 / "11_视频v3_导演" / "终版_配音" / "qc.json"]:
            if "带音效" in f.parent.name:
                continue
            d = json.loads(f.read_text(encoding="utf-8"))
            for b in d.get("各块") or []:
                for t in b.get("各条") or []:
                    for x in Q.name_drops(TAG.sub("", b["原稿"]), t.get("转写") or ""):
                        hit.append((f.parent.name, b["块"], t["第几条"], x["名字"]))
        self.assertEqual(hit, [("终版_配音", 2, 1, "Claude Fable 5.2")])


if __name__ == "__main__":
    unittest.main()
