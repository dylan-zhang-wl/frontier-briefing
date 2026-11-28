#!/usr/bin/env python3
"""listen_pinyin（审片分拣"请你耳听"时判同音字）的测试（2026-11-28 加）。

11-28 改：多音字逐字比时罕见读音不算（"才"在 pypinyin 里挂着 zai，"在过冬→才果冻"原来被判成同音）。
这里测 B2 第 2 步写着的例子照旧（同音的还同音、不同音的还不同音），才／在、也／已、可／合这类只靠罕见读音
对上的改成不同音，长／常、校／教、地／的、重／冲这类常用的多音字读音照旧算同音。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python pipeline/test_listen_pinyin.py        # 全部通过时退出码为 0
不调用任何模型，不读写项目里的文件。
"""
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

import listen_pinyin as LP  # noqa: E402


@unittest.skipIf(LP.pinyin is None, "没装 pypinyin：用 ~/.venvs/frontier-daily/bin/python 跑")
class SameToneless(unittest.TestCase):
    def test_b2_examples_same(self):
        # 每日审片.md B2 第 2 步"只差同音字"一条的例子
        for a, b in [("会话", "绘画"), ("即时", "及时"), ("梳理", "书里"), ("词元", "磁源"), ("博客", "播客"),
                     ("周期长", "周期厂"), ("通上电", "通商店"), ("它", "他")]:
            self.assertEqual(LP.judge(a, b), LP.SAME, (a, b))

    def test_b2_examples_diff(self):
        for a, b in [("援引", "引用"), ("微软", "美软"), ("传奇", "禅奇"), ("字节", "智节"), ("随后", "最后"),
                     ("告别信", "告别镜")]:
            self.assertEqual(LP.judge(a, b), LP.DIFF, (a, b))

    def test_rare_reading_not_same(self):
        # 才 cái 在 pypinyin 里还挂着罕见的 zai；没有哪个词这样念，不算
        self.assertEqual(LP.judge("在过冬", "才果冻"), LP.DIFF)
        self.assertEqual(LP.judge("在", "才"), LP.DIFF)
        self.assertEqual(LP.judge("才", "在"), LP.DIFF)
        self.assertEqual(LP.judge("也", "已"), LP.DIFF)          # 也 ye 挂着 yi
        self.assertEqual(LP.judge("可", "合"), LP.DIFF)          # 可 ke 挂着 ge
        self.assertEqual(LP.common_readings("才"), {"cai"})

    def test_common_heteronyms_kept(self):
        # 常用的多音字读音照旧：长 chang（长对话）、校 jiao（审校）、地 de、重 chong（重启）、没 mo（浸没）
        for a, b in [("长", "常"), ("校", "教"), ("地", "的"), ("冲突", "重吐"), ("重启", "充起"), ("浸没", "金默")]:
            self.assertEqual(LP.judge(a, b), LP.SAME, (a, b))
        self.assertEqual(LP.common_readings("长"), {"zhang", "chang"})

    def test_latin_and_digits(self):
        self.assertEqual(LP.judge("3.8", "3.0"), LP.LATIN)
        self.assertEqual(LP.judge("Claude", "claude"), LP.SAME)


if __name__ == "__main__":
    unittest.main()
