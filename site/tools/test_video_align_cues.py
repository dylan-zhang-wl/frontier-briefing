#!/usr/bin/env python3
"""D:5 这类整体不拆（2026-11-21 加，11-17 审片第 58 项）：字幕切段（video_align.subtitle_cues）和换行（zh_breaks）两半。

11-17 视频 81.75–88.4 秒字幕切成"借第三国数据中心，向总部在 D:"｜"5 国家组或澳门的企业远程出租大量算力，"：
字幕按 CLAUSE_END 里的标点切小段，半角冒号也在里面，"D:5"的冒号被当成停顿。网页和视频的换行点（zh_breaks）
也在"D:"和"5"之间放了一个。两处都改成：冒号前后紧挨 ASCII 字母或数字时，这个冒号是整体的一部分。
环境变量 FD_KEEP_TOKEN=off 两处一起退回原来的做法。

运行：~/.venvs/frontier-daily/bin/python site/tools/test_video_align_cues.py（不花钱、不联网；换行那几项要 budoux、jieba）
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import video_align as VA  # noqa: E402


def fake_units(narrations, step=0.2):
    """给每个参与比对的字排一个起止秒（一个接一个，0.2 秒一个字）。"""
    units, t = [], 0.0
    for si, text in enumerate(narrations):
        for i, ch in enumerate(text):
            if VA.is_unit(ch):
                units.append({"c": ch.lower(), "scene": si, "i": i, "s": round(t, 3), "e": round(t + step, 3)})
                t += step
        t += 1.0
    return units


D5 = "美国商务部发布临时最终规则。借第三国数据中心，向总部在 D:5 国家组或澳门的企业远程出租大量算力，同样要拿许可；许可的门槛，约合 750 张英伟达 H100 或 H200。"


class Cues(unittest.TestCase):
    def cues(self, narr, keep):
        return [c["text"] for c in VA.subtitle_cues(fake_units(narr), narr, 60.0, keep_tokens=keep)]

    def test_old_cut_splits_d5(self):           # 原来的切法：11-17 那样拆成两条（证明测试复现了毛病）
        old = self.cues([D5], False)
        self.assertIn("借第三国数据中心，向总部在 D:", old)
        self.assertIn("5 国家组或澳门的企业远程出租大量算力，", old)

    def test_new_cut_keeps_d5(self):
        new = self.cues([D5], True)
        self.assertTrue(any("D:5 国家组" in c for c in new), new)
        self.assertFalse(any(c.endswith("D:") for c in new))
        self.assertEqual("".join(new), D5)          # 字一个不少、顺序不变

    def test_time_and_ratio(self):              # 10:30、3:2、全角冒号夹在数字中间也算整体
        narr = ["发布会定在北京时间 10:30，比分是 3：2，他说：明天再谈，这一条要单独成句好让它够长。"]
        new = self.cues(narr, True)
        self.assertTrue(any("10:30" in c for c in new), new)
        self.assertTrue(any("3：2" in c for c in new), new)
        narr2 = ["这一句前面要够长才会单独切出来，他说：明天再谈，后面还有一段话要讲完，再加一句凑够长度好分开。"]
        self.assertEqual(self.cues(narr2, True), self.cues(narr2, False))     # 汉字后面的冒号：新旧切法一样

    def test_cjk_colon_still_breaks(self):      # 前面是汉字、后面隔了空格的冒号照旧是停顿
        self.assertTrue(VA.inside_token("D:5", 1))
        self.assertTrue(VA.inside_token("3：2", 1))
        self.assertFalse(VA.inside_token("他说：5", 2))
        self.assertFalse(VA.inside_token("D: 5", 1))
        self.assertFalse(VA.inside_token("D:", 1))
        self.assertFalse(VA.inside_token("5,000", 1))      # 千分位逗号原来就有自己的一条，这里不管
        self.assertFalse(VA.inside_token("千问 4：Max", 4))   # 全角冒号接英文：是在列举（10-31 网页），照旧算停顿
        self.assertFalse(VA.inside_token("MIT：GPT-6", 3))   # 引出处（11-03 网页）

    def test_same_without_pattern(self):        # 没有这类冒号的旁白：新旧切法一模一样（10-31、11-01 这类期不变）
        narr = ["11 月 17 日。加州起诉 OpenAI，诉状称它在测试中对智能体失去控制超过 80 次；美国的芯片管制，也伸到了远程算力。",
                "月之暗面披露，过滤后的模型在内部漏洞利用测试里得分 81.0%，没过滤的是 90.5%。规模 5,000 名，以后再说：先这样。"]
        u = fake_units(narr)
        self.assertEqual(VA.subtitle_cues(u, narr, 60.0), VA.subtitle_cues(u, narr, 60.0, keep_tokens=True))

    def test_switch(self):
        with mock.patch.dict(os.environ, {"FD_KEEP_TOKEN": "off"}):
            self.assertFalse(VA.token_switch())
        with mock.patch.dict(os.environ, {"FD_KEEP_TOKEN": ""}):
            self.assertTrue(VA.token_switch())
        env = dict(os.environ)
        env.pop("FD_KEEP_TOKEN", None)
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertTrue(VA.token_switch())


def has_breakers():
    try:
        import budoux  # noqa: F401
        import jieba  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(has_breakers(), "没装 budoux / jieba")
class Wrap(unittest.TestCase):
    def setUp(self):
        import zh_breaks
        self.zb = zh_breaks
        zh_breaks.load()

    def show(self, s):
        return self.zb.phrase_breaks(s).replace("\u200b", "｜")

    def show_off(self, s):
        with mock.patch.dict(os.environ, {"FD_KEEP_TOKEN": "off"}):
            return self.show(s)

    def test_no_break_after_colon(self):
        with mock.patch.dict(os.environ, {"FD_KEEP_TOKEN": "on"}):
            self.assertIn("D:5", self.show("向总部在 D:5 国家组或澳门的企业远程出租大量算力，"))
            self.assertIn("1:1", self.show("开发者甚至可以 1:1 复刻完整的模型"))
            self.assertIn("说：｜", self.show("他说：5 年内会改"))        # 汉字后面的冒号照旧可以折行
            self.assertIn("3：2", self.show("比分 3：2 落后的那一队"))
            for t in ("千问 4：Max、Flash、Plus、27B", "MIT：GPT-6 Astra能直接修改Qwen权重，数学能力暴涨6倍"):   # 10-31、11-03 网页原句
                self.assertEqual(self.show(t), self.show_off(t))

    def test_switch_off_is_old(self):
        with mock.patch.dict(os.environ, {"FD_KEEP_TOKEN": "off"}):
            self.assertIn("D:｜5", self.show("向总部在 D:5 国家组或澳门的企业远程出租大量算力，"))

    def test_only_removes_breaks(self):         # 开着只会少换行点、不会多；字一个不变
        for s in ("向总部在 D:5 国家组或澳门的企业远程出租大量算力，", "北京时间 10:30 开会，比分 3：2。", "今天没有冒号的句子照常切开。"):
            with mock.patch.dict(os.environ, {"FD_KEEP_TOKEN": "on"}):
                new = self.zb.phrase_breaks(s)
            with mock.patch.dict(os.environ, {"FD_KEEP_TOKEN": "off"}):
                old = self.zb.phrase_breaks(s)
            self.assertEqual(new.replace("\u200b", ""), old.replace("\u200b", ""))
            self.assertLessEqual(new.count("\u200b"), old.count("\u200b"))


if __name__ == "__main__":
    unittest.main()
