#!/usr/bin/env python3
"""对稿的专名读音清单（pipeline/tts_qc.py 的 name_misreads，清单在 pipeline/prompts/专名读音.yaml）的测试（2026-11-09 加）。

为什么有它：11-09 播客 Claude 三处转写成 cloud、Gurman 一处转写成 German、"黄仁勋"选用的那条转写成"黄仁荀"、
拼音 Yao Shunyu 被念怪（转写成"姚书怀"），对稿按整块字错率判，全放过了。这里查：
  · 今天这几处都拦得住（例句取自 11-09 qc.json 的转写）；
  · 原稿本来就有的同一个词不算（Google Cloud、Cloudflare、German 政府）；英文按整词、不分大小写；繁体转写照样认；
  · 命中后 check() 判"要重录"、原因里写清；没命中时结果和原来一模一样（没有"专名读音"这一栏）；
  · 清单标了"只提醒"的（Claude，11-09 用户同意）：命中不判"要重录"、原因里不写，只记进"专名读音"（带"只提醒"）；
    同一块里别的名字（Gurman）照旧要重录；
  · 清单坏了、不在：不查这一项，照常对稿；
  · 有 11-09 那期的 qc.json（只在 mini 上有）时，再用真转写跑一遍：命中的正好是今天那三块，别的块不报；
  · 11-09 晚加 Ternus（Weston）、Thurrock（Sorrock、FAROC……），例句取自 11-09 云端那期播客的转写；
    当晚试配的同音写法（Turnus、Ternes、Thorak、The Rock……）不算误读；
  · 11-10 加特朗普（川普）、GR00T（GR002、G2002），例句取自 11-10 云端那期的转写；当天试配的转写不算误读。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_tts_qc_names.py
不调用任何模型、不转写、不花钱。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))
import tts_qc as Q  # noqa: E402

# mini 11-09 05:07 那期的对稿结果（11-09 晚起在本机 本机资料/归档/mini试运行_1031-1109/，不进 git；也可用 FD_SAMPLE_ROOT 指别处）
_QC_1109 = Path("2026-11-09") / "05_配音" / "播客_v3" / "qc.json"
_BASES = ([Path(os.environ["FD_SAMPLE_ROOT"]).expanduser()] if os.environ.get("FD_SAMPLE_ROOT") else []) + [
    PIPE.parent / "本机资料" / "归档" / "mini试运行_1031-1109"]
MINI_1109 = next((b / _QC_1109 for b in _BASES if (b / _QC_1109).exists()), _BASES[-1] / _QC_1109)


def names(ref, hyp, **kw):
    return [(x["名字"], x["转写成"], x["处数"]) for x in Q.name_misreads(ref, hyp, **kw)]


class Today(unittest.TestCase):
    """11-09 那几处（转写原样取自 qc.json）。"""

    def test_claude(self):
        ref = "据 IT之家报道，Anthropic 发布了一份研究报告，看科学家都拿 Claude 做什么。写作与沟通占了 Claude 科研会话的百分之三十二。"
        hyp = "据IT之家报道Anthropic发布了一份研究报告看科学家都拿Cloud做什么写作与沟通占了Cloud科研绘画的32%"
        self.assertEqual(names(ref, hyp), [("Claude", "cloud", 2)])

    def test_gurman(self):
        self.assertEqual(names("这些时间点都出自 Gurman 的消息，苹果官方没有确认。", "这些时间点都出自German的消息,苹果官方"),
                         [("Gurman", "german", 1)])

    def test_huang(self):
        ref = "起因是近来有报道称，公司创始人兼 CEO 黄仁勋，成了一次外国情报活动的目标。公司网站还发布了黄仁勋写给员工的一份备忘录。"
        self.assertEqual(names(ref, "司创始人见CEO黄仁荀成了一次外国情公司网站还发布了黄仁荀写给员工的一份"), [("黄仁勋", "黄仁荀", 2)])
        self.assertEqual(names(ref, "司创始人兼CEO黄仁勋成了一次外国情公司网站还发布了黄仁勋写给员工的一份"), [])

    def test_yao_pinyin(self):
        ref = "据南华早报报道，腾讯首席 AI 科学家 Yao Shunyu，也是前 OpenAI 研究员，周六在香港说……"
        self.assertEqual(names(ref, "讯首席AI科学家姚书怀也是前OpenAI研究员"), [("Yao Shunyu", "姚书怀", 1)])

    def test_ternus(self):
        """11-09 晚加：云端那期播客 7:33、7:50 两处转写成 Weston（正式音频 medium 转写另有一处 Wesdon）。"""
        ref = ("据彭博社记者 Mark Gurman 十一月八日的爆料，苹果 CEO John Ternus 正在施压软件负责人 Craig Federighi。"
               "虎嗅转述的报道说，Ternus 在公开场合对苹果 AI 态度积极。")
        self.assertEqual(names(ref, "苹果CEOJohn Weston正在施压虎秀转述的报道说,Weston在公开场合"), [("Ternus", "weston", 2)])
        self.assertEqual(names(ref, "蘋果CEOJohn Weston正在施虎秀轉述的報道說Wesdon在公開場合"),
                         [("Ternus", "weston", 1), ("Ternus", "wesdon", 1)])

    def test_thurrock(self):
        """11-09 晚加：云端那期播客 8:23、11:59 转写成 Sorrock、FAROC（审片另一次是 Sirrock；medium 是 SOROC、Farrock）。"""
        self.assertEqual(names("要求谷歌放弃在伦敦以东约二十四公里的 Thurrock 建大型数据中心。", "伦敦以东约24公里的Sorrock建大"),
                         [("Thurrock", "sorrock", 1)])
        self.assertEqual(names("还有 Thurrock 那座数据中心明年年初的审批。", "还有FAROC那座数据中心明年"), [("Thurrock", "faroc", 1)])
        self.assertEqual(names("还有 Thurrock 那座数据中心。", "還有Farrock那座數據中心"), [("Thurrock", "farrock", 1)])

    def test_trump_1110(self):
        """11-10 加：云端那期视频 75 秒"特朗普就听过"转写成"川普"，用户耳听确认念的就是"川普"。试配的 8 次转写都是"特朗普"，不报。"""
        ref = "约一年前，据 The Verge 转引《纽约时报》，特朗普就听过相关的情报简报，但没有据此行动。"
        self.assertEqual(names(ref, "约一年前据The Verge转印纽约时报,川普就听过相关的情报简报,但没有据此行动。"),
                         [("特朗普", "川普", 1)])
        self.assertEqual(names(ref, "約一年前據The Verge轉引紐約時報特朗普就聽過相關的情報簡報"), [])

    def test_groot_1110(self):
        """11-10 加：云端那期播客 7:00"发布了 GR00T 2"转写成"GR002 2.0"（medium 单切另有 G2002），用户耳听确认念得不对。
        试配原写法的转写 GR00TR、GROOT2、GR00T2 不报。"""
        ref = "英伟达在机器人学习大会 CoRL 上发布了 GR00T 2，这个世界动作模型用机器人和人类的数据训练。"
        self.assertEqual(names(ref, "英伟达在机器人学习大会Core上发布了GR002 2.0这个世界动作模型"), [("GR00T", "GR002", 1)])
        self.assertEqual(names(ref, "英伟达在机器人学习大会Core上发布了G2002 2.0这个世界动作模型"), [("GR00T", "G2002", 1)])
        for hyp in ("发布了GR00TR,这个世界动作模型", "发布了GROOT2这个世界动作模型", "發布了GR00T2這個世界動作模型"):
            self.assertEqual(names(ref, hyp), [], hyp)

    def test_title_1110(self):
        """11-10 晚加：播客 10:41"董事长、总经理胡伟武"被念成"董事长兼总裁"，你认定头衔被改是错；原稿本来写着"总裁"的不算。"""
        ref = "龙芯中科董事长、总经理胡伟武在业绩说明会上说，"
        self.assertEqual(names(ref, "龙芯中科董事长兼总裁胡伟乌在业绩说明会上说"), [("总经理", "总裁", 1)])
        self.assertEqual(names(ref, "龙芯中科董事长总经理胡伟武在业绩说明会上说"), [])
        self.assertEqual(names("这家公司的总裁兼总经理表示，", "这家公司的总裁兼总经理表示"), [])

    def test_check_flags_retake(self):
        r = Q.check("这些时间点都出自 Gurman 的消息。", "这些时间点都出自German的消息")
        self.assertTrue(r["需重录"])
        self.assertTrue(any(x.startswith("专名读音：Gurman") for x in r["原因"]))
        self.assertEqual(r["专名读音"][0]["转写成"], "german")
        self.assertNotIn("只提醒", r["专名读音"][0])
        self.assertTrue(Q.badness(r)[0])

    def test_claude_remind_only(self):
        """Claude 只提醒、不重录（11-09 用户同意）：不判要重录、原因里不写，"专名读音"里照记、带"只提醒"。"""
        r = Q.check("看科学家都拿 Claude 做什么。", "看科学家都拿Cloud做什么")
        self.assertFalse(r["需重录"])
        self.assertEqual(r["原因"], [])
        self.assertEqual([(x["名字"], x["转写成"], x.get("只提醒")) for x in r["专名读音"]], [("Claude", "cloud", True)])
        self.assertFalse(Q.badness(r)[0])

    def test_claude_and_gurman_same_block(self):
        """同一块里 Claude 只提醒、Gurman 照旧重录：要重录，原因里只有 Gurman，两条都记进"专名读音"。"""
        r = Q.check("Gurman 说 Claude 要涨价。", "German说Cloud要涨价")
        self.assertTrue(r["需重录"])
        self.assertEqual([x for x in r["原因"] if x.startswith("专名读音")],
                         ["专名读音：Gurman 转写成了 german（1 处），重录一次；还在就请你耳听"])
        self.assertEqual(sorted((x["名字"], bool(x.get("只提醒"))) for x in r["专名读音"]),
                         [("Claude", True), ("Gurman", False)])


class NoFalseAlarm(unittest.TestCase):
    def test_word_already_in_script(self):
        self.assertEqual(names("Google Cloud 涨价，Claude 也涨价。", "Google Cloud涨价Claude也涨价"), [])
        # 原稿有一个 Cloud，转写出两个：多出来的一个才算
        self.assertEqual(names("Google Cloud 涨价，Claude 也涨价。", "Google Cloud涨价Cloud也涨价"), [("Claude", "cloud", 1)])

    def test_whole_word_and_case(self):
        self.assertEqual(names("Claude 和 Cloudflare", "Claude和Cloudflare"), [])
        self.assertEqual(names("Claude 和 Cloudflare", "CLOUD和Cloudflare"), [("Claude", "cloud", 1)])

    def test_name_not_in_script(self):
        self.assertEqual(names("德国政府说", "German政府说"), [])
        self.assertEqual(names("据 Gurman 说，German 政府……", "据Gurman说German政府"), [])

    def test_traditional_transcript(self):
        self.assertEqual(names("黄仁勋说", "黃仁荀說"), [("黄仁勋", "黄仁荀", 1)])

    def test_trial_transcripts_not_flagged(self):
        """11-09 晚试配原写法和候选写法的转写（同音写法、th 还在的）不算误读。"""
        ref = "苹果 CEO John Ternus 正在施压。Ternus 在公开场合……还有 Thurrock 那座数据中心。"
        for hyp in ("苹果CEO John Turnus正在施压Ternus在公开场合还有Thorak那座数据中心",
                    "苹果CEOJohn Ternes正在施压Turness在公开场合还有The Rock那座数据中心",
                    "苹果CEO John Turnis正在施压Ternus在公开场合还有Thirrock那座数据中心"):
            self.assertEqual(names(ref, hyp), [])

    def test_western_in_script(self):
        self.assertEqual(names("Ternus 和 Western Digital 都说……", "Ternus和Western Digital都说"), [])
        self.assertEqual(names("Ternus 和 Western Digital 都说……", "Western和Western Digital都说"), [("Ternus", "western", 1)])

    def test_clean_result_unchanged(self):
        r = Q.check("今天是十一月九日。", "今天是11月9日")
        self.assertNotIn("专名读音", r)
        self.assertFalse(r["需重录"])


class ListFile(unittest.TestCase):
    def test_real_list_has_todays_names(self):
        got = {e["名字"] for e in Q.load_names()}
        for n in ("Claude", "Gurman", "黄仁勋", "姚顺雨", "Yao Shunyu", "Ternus", "Thurrock", "特朗普", "GR00T"):
            self.assertIn(n, got)

    def test_real_list_only_claude_remind(self):
        self.assertEqual(sorted(e["名字"] for e in Q.load_names() if e["只提醒"]), ["Claude"])

    def test_bad_or_missing_list(self):
        d = Path(tempfile.mkdtemp())
        bad = d / "bad.yaml"
        bad.write_text("名字: [\n", encoding="utf-8")
        self.assertEqual(Q.load_names(bad), [])
        self.assertEqual(Q.load_names(d / "无.yaml"), [])
        self.assertEqual(names("黄仁勋说", "黄仁荀说", names=Q.load_names(bad)), [])

    def test_custom_list(self):
        d = Path(tempfile.mkdtemp())
        p = d / "n.yaml"
        p.write_text("名字:\n  - 写法: [Mistral, Mistral AI]\n    已知误读: mistro\n", encoding="utf-8")
        self.assertEqual(names("Mistral AI 发布", "Mistro AI发布", names=Q.load_names(p)), [("Mistral", "mistro", 1)])

    def test_custom_list_remind_only(self):
        """只提醒要写成 true 才算；写别的（"是"、字符串）一律当没写，照旧重录。"""
        d = Path(tempfile.mkdtemp())
        p = d / "n.yaml"
        p.write_text("名字:\n  - 写法: Mistral\n    已知误读: mistro\n    只提醒: true\n"
                     "  - 写法: Qwen\n    已知误读: queen\n    只提醒: 是\n", encoding="utf-8")
        got = Q.name_misreads("Mistral 和 Qwen", "Mistro和Queen", names=Q.load_names(p))
        self.assertEqual([(x["名字"], x.get("只提醒", False)) for x in got], [("Mistral", True), ("Qwen", False)])


@unittest.skipUnless(MINI_1109.exists(), "这台机器上没有 mini 11-09 那期的 qc.json（在本机 本机资料/归档/ 里，不进 git）")
class Real1109(unittest.TestCase):
    """用 11-09 那期真实的转写：命中的块正好是热点一第 2 块（选用的那条）、要闻第 7 块、快讯第 9 块。"""

    def test_hits(self):
        d = json.loads(MINI_1109.read_text(encoding="utf-8"))
        hit = {}
        for b in d["各块"]:
            for t in b["各条"]:
                r = Q.name_misreads(b["原稿"], t.get("转写") or "")
                if r:
                    hit.setdefault(b["块"], {})[t["第几条"]] = sorted({x["名字"] for x in r})
        self.assertEqual(sorted(hit), [2, 7, 9])
        self.assertEqual(hit[2], {2: ["黄仁勋"]})               # 只有选用的第 2 条转写成"黄仁荀"，另两条不报
        self.assertEqual(hit[7][2], ["Claude", "Gurman"])
        self.assertEqual(set(hit[9]), {1, 2, 3})


if __name__ == "__main__":
    unittest.main()
