#!/usr/bin/env python3
"""第 7 步把"要改"的问题全部交回写稿的人（2026-11-16 加）。

来历：11-16 MiMo 备用稿第一轮视频分镜检查实际有 20 处，可是
  · pipeline/orchestrator/helpers.py 的 stop_lines 只印最后 12 条（[-12:]）；
  · pipeline/orchestrator/steps.py 第 7 步只摘最后 6 行要紧的（key_lines(out, 6)）记进 logs/检查_稿子.json；
所以前 8 处写稿的人根本没收到，改一轮以后"还有 12 处"，大半是没被告知。网页数字预检同理只取前 10 条。

查：
  · stop_lines 把 SystemExit 里的每一条都印成"✗ 要改"，20 条就是 20 条；
  · 第 7 步从分镜检查输出里取全部"✗ 要改"行（不截），一行 ✗ 都没有时照旧退回要紧的几行；
  · 网页数字预检取全部"找不到／核对不上／对不上"的行（不截）；
  · 要改的超过 20 条时，"要你做"只列前 20 条，另加一行"还有 N 处……全部在 logs/检查_稿子.json"。
用法（在项目根运行）：~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_storyboard_feedback.py
不调用任何模型、不花钱；只在临时目录读写。
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))
from orchestrator import helpers, steps  # noqa: E402

PROBLEMS = ["「qwen.f%d.label(zh)」里的数字 %d 在它引用的事件卡原文（n2.cost）里找不到" % (i, i) for i in range(20)]


def storyboard_output():
    """照 helpers.cmd_storyboard 没过时的样子：前面几行提醒，最后是 stop_lines 印的标题和每一条。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print("  提醒：配图 5 张第 10 步才画")
        rc = helpers.stop_lines(SystemExit("核对失败（画面数字只能来自事件卡）：\n" + "\n".join(PROBLEMS)))
    return rc, buf.getvalue()


class StopLines(unittest.TestCase):
    def test_all_twenty_printed(self):
        rc, out = storyboard_output()
        self.assertEqual(rc, 1)
        rows = [x for x in out.splitlines() if "✗ 要改" in x]
        self.assertEqual(len(rows), 20)
        self.assertIn("qwen.f0.label", rows[0])          # 原来 [-12:] 时，前 8 条（f0–f7）不印
        self.assertIn("分镜检查没过：核对失败", out)

    def test_single_line_message(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            helpers.stop_lines(SystemExit("成片按字数估 210 秒，超过 180 秒"))
        self.assertEqual(sum(1 for x in buf.getvalue().splitlines() if "✗ 要改" in x), 1)


class Step7Lists(unittest.TestCase):
    def test_storyboard_must_keeps_everything(self):
        _, out = storyboard_output()
        must = steps.storyboard_must(out)
        self.assertEqual(len(must), 20)
        self.assertTrue(all(m.startswith("✗ 要改") for m in must))

    def test_storyboard_must_falls_back_without_cross(self):
        out = "Traceback (most recent call last):\nValueError: 分镜 JSON 读不出来\n"
        self.assertTrue(steps.storyboard_must(out))      # 程序自己出错：照旧给出要紧的几行，不是空的

    def test_web_must_keeps_everything(self):
        out = "\n".join("错误：今日数字第 %d 个（E002）：E002 N%d 里找不到核对片段「x」" % (i, i) for i in range(15))
        out += "\n\n有 15 处数字核对不上（可能是编造的），没有写配置。"
        must = steps.web_must(out)
        self.assertEqual(len([m for m in must if "找不到核对片段" in m]), 15)

    def test_todo_lists_first_twenty_and_points_to_file(self):
        with tempfile.TemporaryDirectory() as t:
            issue = Path(t) / "2026-11-16"
            (issue / "04_文稿").mkdir(parents=True)
            for f in ("claude_播客_v3.md", "claude_网页.json", "视频v3_分镜.json"):
                (issue / "04_文稿" / f).write_text("x", encoding="utf-8")
            state = SimpleNamespace(step=lambda k: {}, set_step=lambda k, v: None)
            c = SimpleNamespace(issue=issue, state=state, ed={"播客稿": "04_文稿/claude_播客_v3.md"},
                                p=lambda x: issue / x, again=lambda: "./fd run --date 2026-11-16")
            _, out = storyboard_output()
            must = [("视频分镜", m) for m in steps.storyboard_must(out)] + [("网页数字", "E001 N1 里找不到核对片段「y」")] * 3
            res = {"检查": [{"名字": "视频分镜", "要改": [m for _, m in must[:20]]}, {"名字": "网页数字", "要改": ["y"] * 3}]}
            r = steps.STEPS[6].judge(c, res, must, [])
            self.assertEqual(r.status, steps.WAITING)
            listed = [x for x in r.todo if x.startswith("  - [")]
            self.assertEqual(len(listed), 20)
            self.assertTrue(any("还有 3 处" in x and "logs/检查_稿子.json" in x for x in r.todo))
            self.assertIn("23 处要改", r.msg)


if __name__ == "__main__":
    unittest.main()
