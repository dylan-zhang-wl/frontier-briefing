#!/usr/bin/env python3
"""第 7 步分镜检查"一次报全"的测试（2026-11-17 加）。

来历：分镜检查原来前一道没过就不往下查（结构→事实核对→画面字和数字→帖子卡原话→触发词→旁白规则→时长→数值字段、关系画面），
写稿的人改完一道才看到下一道。11-16 MiMo 备用稿改了三轮，每轮只看到同一处，后面还排着四类、16 处没报出来。

硬要求（这几个测试守着）：
  · 过不过和原来一模一样：有一道没过就退出码 1，全过才 0；每一道怎么判一条没改；
  · 原来第一道就停的稿子，原来印的那些字（提醒＋第一道没过的那几行）逐字照旧在最前面，多查出来的接在 MORE_HEAD 后面；
  · video3_build.prepare 不给 on_fail 时（组装视频等别处都这样用）和原来一样，第一道没过就 SystemExit；
  · "画面字和数字""帖子卡原话"要用事实核对的结果：事实核对没过就不查它们，说一声。
另外用真实稿子回归过（改前改后各跑一遍、比退出码和输出），见提交说明。
用法（在项目根运行）：~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_storyboard_check_all.py
不调用任何模型、不花钱；只在临时目录读写。
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
ROOT = PIPE.parent
for p in (str(PIPE), str(ROOT / "site" / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)
from orchestrator import helpers  # noqa: E402
import video3_build as V  # noqa: E402


def fake_issue(t):
    issue = Path(t) / "2026-11-16"
    (issue / "04_文稿").mkdir(parents=True)
    (issue / "03_事件卡").mkdir(parents=True)
    (issue / "03_事件卡" / "cards_写稿用.json").write_text("[]", encoding="utf-8")
    return issue


class PrepareStages(unittest.TestCase):
    """video3_build.prepare：把各道核对换成假的，只看先后和停不停。"""

    def patches(self, facts_err=None, labels_err=None, posts_err=None, cues_err=None, calls=None):
        calls = calls if calls is not None else []

        def mk(name, err, ret):
            def f(*a, **k):
                calls.append(name)
                if err:
                    raise SystemExit(err)
                return ret
            return f
        sb = {"chapters": [{"id": "open", "blocks": []}]}
        return [mock.patch.object(V.SB, "load", lambda p: sb), mock.patch.object(V.SB, "motion_off", lambda: False),
                mock.patch.object(V.IMG, "ensure", lambda *a, **k: {}), mock.patch.object(V.SB, "image_requests", lambda s: []),
                mock.patch.object(V.SB, "structure", lambda s, i: ["结构提醒"]),
                mock.patch.object(V.SB, "check_facts", mk("facts", facts_err, {"k": 1})),
                # 11-21 合并加：网页／视频那一路在事实核对之后调 attach_datelines（记原文电头日期），这里的假 facts 不是真卡，换成什么都不做
                mock.patch.object(V.SB, "attach_datelines", lambda f, i: 0),
                mock.patch.object(V, "en_registry", lambda: []),
                mock.patch.object(V.SB, "check_labels", mk("labels", labels_err, 3)),
                mock.patch.object(V.SB, "check_posts", mk("posts", posts_err, ["帖子提醒"])),
                mock.patch.object(V.SB, "check_logos", mk("logos", None, [])), mock.patch.object(V.SB, "check_layers", lambda s: []),
                mock.patch.object(V, "en_name_warnings", lambda s, r: []), mock.patch.object(V.SB, "source_warnings", lambda s: []),
                mock.patch.object(V.SB, "narration_md", lambda s: "## 开场\n旁白\n"),
                mock.patch.object(V.SB, "check_cues", mk("cues", cues_err, None))], calls

    def run_prepare(self, on_fail=None, **errs):
        ps, calls = self.patches(**errs)
        with tempfile.TemporaryDirectory() as t, contextlib.ExitStack() as st:
            for p in ps:
                st.enter_context(p)
            issue = fake_issue(t)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                try:
                    r = V.prepare(issue, gen=False, on_fail=on_fail)
                    exc = None
                except SystemExit as e:
                    r, exc = None, e
            md = (issue / V.NARRATION).exists()
        return r, exc, calls, buf.getvalue(), md

    def test_default_stops_at_first_failure_like_before(self):
        _, exc, calls, out, md = self.run_prepare(facts_err="核对失败：A", cues_err="触发词：C")
        self.assertEqual(str(exc.code), "核对失败：A")
        self.assertEqual(calls, ["facts"])                     # 后面几道都没查
        self.assertFalse(md)                                  # 原来事实核对没过时不写旁白文件

    def test_default_all_pass_prints_summary(self):
        r, exc, calls, out, md = self.run_prepare()
        self.assertIsNone(exc)
        self.assertEqual(calls, ["facts", "labels", "posts", "logos", "cues"])
        self.assertIn("分镜：1 章", out)
        self.assertIn("帖子提醒", out)

    def test_collect_goes_on_and_skips_dependent(self):
        got = []
        r, exc, calls, out, md = self.run_prepare(on_fail=lambda n, e: got.append((n, e and str(e.code))),
                                                 facts_err="核对失败：A", cues_err="触发词：C")
        self.assertIsNone(exc)
        self.assertEqual(calls, ["facts", "cues"])              # 画面字和数字、帖子卡要用事实核对的结果：没查
        self.assertEqual(got, [("事实核对", "核对失败：A"), ("画面字和数字、帖子卡原话", None), ("触发词", "触发词：C")])
        self.assertTrue(md)                                   # 触发词、旁白规则要读旁白：照写
        self.assertNotIn("已核对", out)                       # 有一道没过就不写"已核对"

    def test_collect_labels_and_posts_both_checked(self):
        got = []
        _, _, calls, _, _ = self.run_prepare(on_fail=lambda n, e: got.append(n), labels_err="核对失败：L", posts_err="帖子：P")
        self.assertEqual(got, ["画面字和数字", "帖子卡原话"])
        self.assertNotIn("logos", calls)       # 标志那一步会往 site/assets/logos 补文件：前两道没过时照旧不走

    def test_collect_labels_fail_still_skips_logos(self):
        _, _, calls, _, _ = self.run_prepare(on_fail=lambda n, e: None, labels_err="核对失败：L")
        self.assertEqual(calls, ["facts", "labels", "posts", "cues"])


class CmdStoryboard(unittest.TestCase):
    """helpers.cmd_storyboard：原来印的字逐字在前、多查出来的接在后面、退出码不变。"""

    def run_cmd(self, prepare_script, lint_err=None, length_err=None, vals=(), must=(), calls=None):
        def fake_prepare(issue, gen=False, on_fail=None):
            for kind, x in prepare_script:
                if kind == "print":
                    print(x)
                elif on_fail is None:                          # 原来的样子：第一道没过就停
                    raise SystemExit(x)
                else:
                    on_fail(kind, SystemExit(x) if x else None)
            return {"chapters": [{"id": "open"}]}, {}, {}

        calls = calls if calls is not None else []

        def raiser(msg, name):
            def f(*a, **k):
                calls.append(name)
                if msg:
                    raise SystemExit(msg)
            return f
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(V, "prepare", fake_prepare), \
                mock.patch.object(V, "lint_narration", raiser(lint_err, "lint")), \
                mock.patch.object(V, "check_length", raiser(length_err, "length")), \
                mock.patch.object(V, "load_rules", lambda: {}), \
                mock.patch.object(V.SB, "check_values", lambda sb: list(vals)), \
                mock.patch.object(V.SB, "check_relations", lambda sb: (list(must), ["关系提醒"])), \
                mock.patch.object(V.SB, "motion_off", lambda: False), \
                mock.patch.object(helpers, "weekend_warnings", lambda i, s: None), \
                mock.patch.object(helpers, "motion_summary", lambda s: ""):
            issue = fake_issue(t)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = helpers.cmd_storyboard(type("A", (), {"issue_dir": str(issue)})())
        return rc, buf.getvalue()

    def old_output(self, warnings, err):
        """改之前（第一道没过就停）印的字：提醒整理一遍，再 stop_lines。"""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print(helpers.tidy_warnings("".join(w + "\n" for w in warnings), set()), flush=True)
            helpers.stop_lines(SystemExit(err))
        return buf.getvalue()

    def test_prepare_failure_prefix_identical_then_more(self):
        script = [("print", "  提醒：甲"), ("事实核对", "核对失败：\n  e1 找不到"), ("print", "  提醒：乙"),
                  ("画面字和数字、帖子卡原话", None), ("触发词", "触发词对不上：\n  c1\n  c2")]
        rc, out = self.run_cmd(script, lint_err="旁白不合规则：\n  我", length_err="视频约 228 秒，超过上限 180 秒",
                               must=["关系 1"])
        self.assertEqual(rc, 1)
        old = self.old_output(["  提醒：甲"], "核对失败：\n  e1 找不到")
        self.assertTrue(out.startswith(old), out)
        rest = out[len(old):]
        self.assertTrue(rest.startswith(helpers.MORE_HEAD))
        for s in ("提醒：乙", "要用事实核对的结果", "分镜检查没过：触发词对不上", "✗ 要改：c2", "分镜检查没过：旁白不合规则",
                  "超过上限 180 秒", "关系画面 1 处要改", "✗ 要改：关系 1"):
            self.assertIn(s, rest)
        self.assertLess(rest.index("触发词对不上"), rest.index("旁白不合规则"))
        self.assertLess(rest.index("旁白不合规则"), rest.index("超过上限"))

    def test_lint_failure_prefix_identical_then_length_and_relations(self):
        rc, out = self.run_cmd([("print", "  提醒：甲")], lint_err="旁白不合规则：\n  我", length_err="约 228 秒",
                               vals=["数值 1"])
        self.assertEqual(rc, 1)
        i = out.index(helpers.MORE_HEAD)
        self.assertTrue(out[:i].rstrip().endswith("✗ 要改：我"))       # 原来最后一行
        self.assertIn("约 228 秒", out[i:])
        self.assertIn("✗ 要改：数值 1", out[i:])

    def test_length_failure_does_not_rerun_lint(self):
        calls = []
        rc, out = self.run_cmd([], length_err="约 228 秒", calls=calls)
        self.assertEqual(rc, 1)
        self.assertEqual(calls, ["lint", "length"])            # 旁白查过一次、时长查过一次，不重复
        self.assertIn(helpers.MORE_HEAD, out)

    def test_prepare_failure_runs_lint_and_length_once_each(self):
        calls = []
        self.run_cmd([("触发词", "触发词对不上：\n  c1")], calls=calls)
        self.assertEqual(calls, ["lint", "length"])

    def test_all_pass_unchanged(self):
        rc, out = self.run_cmd([("print", "  提醒：甲")])
        self.assertEqual(rc, 0)
        self.assertNotIn(helpers.MORE_HEAD, out)
        self.assertTrue(out.rstrip().endswith("分镜检查通过：1 章"))

    def test_only_last_block_fails_unchanged(self):
        rc, out = self.run_cmd([], must=["关系 1"])
        self.assertEqual(rc, 1)
        self.assertNotIn(helpers.MORE_HEAD, out)               # 最后一道才没过：后面没有可多查的，和原来一样
        self.assertTrue(out.rstrip().endswith("✗ 要改：关系 1"))


if __name__ == "__main__":
    unittest.main()
