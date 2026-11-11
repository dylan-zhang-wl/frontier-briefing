#!/usr/bin/env python3
"""易歧义词提醒（pipeline/ambiguity_check.py，fd 第 7 步只提醒）的测试（2026-11-09 加）。

查：只看开场、结尾两章和视频的开场、收尾、速览、名牌、小结卡；正文里的同一个词不报；词表可以换；
文件不在、词表坏了都不报错（第 7 步不能因为它停）；退出码总是 0。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_ambiguity_check.py
不调用任何模型，不花钱；只写临时目录。
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))
import ambiguity_check as A  # noqa: E402

SCRIPT = """## 开场

早上好，欢迎收听每日AI科技前沿简报，我是 Shirley。智能体在抢入口。

## 热点一

董事会公布了调查程序，入口和账单这里都不报。

## 结尾

董事会先把程序摆到前面。我们下期见。

<!-- 语气
{"开场": "calm and steady", "结尾": "程序"}
-->
"""

SB = {"chapters": [
    {"id": "open", "kind": "open", "narration": "算力的账单落到了水和债上。",
     "blocks": [{"type": "headline_open", "items": [{"text": {"zh": "智能体在抢入口", "en": "x"}, "sub": {"zh": "DeepSeek 日活 154 万"}}]}]},
    {"id": "nvda", "kind": "story", "narration": "正文里的程序、入口、账单不查。", "storyline": "董事会启动调查",
     "chip": {"key": {"zh": "底座换代"}, "sub": {"zh": "暂无理由认为机密受损"}}, "blocks": []},
    {"id": "close", "kind": "close", "narration": "智能体还在学着办事。",
     "end": {"title": {"zh": "今天的地图"}, "lines": [{"zh": "程序摆在前面"}, {"zh": "账单落到水和债上"}]}},
]}


class T(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "s.md").write_text(SCRIPT, encoding="utf-8")
        (self.d / "sb.json").write_text(json.dumps(SB, ensure_ascii=False), encoding="utf-8")

    def hits(self, **kw):
        r = A.check(self.d / "s.md", self.d / "sb.json", **kw)
        return [(x["位置"], x["词"]) for x in r["提醒"]], r

    def test_only_open_close_and_cards(self):
        h, _ = self.hits()
        self.assertIn(("播客·开场", "入口"), h)
        self.assertIn(("播客·结尾", "程序"), h)
        self.assertIn(("视频·open 旁白", "账单"), h)
        self.assertIn(("视频·速览第 1 屏 text", "入口"), h)
        self.assertIn(("视频·nvda 名牌 key", "底座"), h)
        self.assertIn(("视频·close 小结卡第 1 行", "程序"), h)
        self.assertIn(("视频·close 小结卡第 2 行", "账单"), h)
        self.assertFalse([x for x in h if "热点一" in x[0]], "播客正文不该报")
        self.assertFalse([x for x in h if x[0] == "视频·nvda 旁白"], "视频 story 章旁白不该报")
        self.assertFalse([x for x in h if x[1] == "程序" and x[0] == "播客·开场"])
        # 语气注释里的字不算
        self.assertEqual(sum(1 for x in h if x[0] == "播客·结尾"), 1)

    def test_custom_words(self):
        w = self.d / "w.yaml"
        w.write_text("词:\n  - 词: 学着办事\n    说明: 测试\n", encoding="utf-8")
        h, _ = self.hits(words_path=w)
        self.assertEqual(h, [("视频·close 旁白", "学着办事")])

    def test_missing_files_and_bad_table(self):
        r = A.check(self.d / "无.md", self.d / "无.json")
        self.assertEqual(r["提醒"], [])
        bad = self.d / "bad.yaml"
        bad.write_text("词: [\n", encoding="utf-8")
        r = A.check(self.d / "s.md", self.d / "sb.json", words_path=bad)
        self.assertEqual(r["提醒"], [])
        self.assertTrue(r["说明"])

    def test_cli_exit_zero(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(A.main(["--script", str(self.d / "s.md"), "--storyboard", str(self.d / "sb.json"), "--json"]), 0)

    def test_real_table_has_user_words(self):
        words = [w for w, _ in A.load_words()]
        for w in ("程序", "入口", "账单", "底座"):
            self.assertIn(w, words)


if __name__ == "__main__":
    unittest.main()
