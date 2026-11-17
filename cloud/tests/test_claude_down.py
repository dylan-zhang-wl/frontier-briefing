#!/usr/bin/env python3
"""cloud/claude_down.py 的测试（2026-11-17 加）：认出"Claude 不能用"（登录失效、额度用完），分原话、宽认两档。

样本在 cloud/tests/claude_down_samples/：
  401_*、429_*：本机用"假 Anthropic 接口"和故意填错的令牌跑 claude -p --output-format stream-json --verbose 的真输出
    （命令行 2.1.321，11-17；洗掉了带本机路径的 init 行，时区那几个字换成了 UTC）；
  103820_session.jsonl：429 那次命令行自己的会话记录，只留 user 和 isApiErrorMessage 那两条（去掉 cwd 等本机字段）。
    拿它造 anthropics/claude-code#103820 那种情况：stream-json 一个字没有、退出码 1，那句话只在会话记录里。
其余情况（overloaded、轮数用完、普通 429、中途 401 后来好了、403 账号被停）在测试里按同样的字段手写。

用法（在项目根运行）：python3 -m unittest discover -s cloud/tests -v
不调 Claude、不联网、不花钱。
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import claude_down as C  # noqa: E402

S = HERE / "claude_down_samples"
DAY = "2026-11-18"          # 星期三


def objs(name):
    return C.read_lines(S / name)


def done_state():
    return {"步骤": {k: {"状态": "做完"} for k in C.WRITE_STEPS}, "运行记录": [{"结果": "跑完"}]}


class Samples(unittest.TestCase):
    def test_401_exact(self):
        got = C.classify(objs("401_stream.jsonl"), (S / "401_stderr.log").read_text(), 1)
        self.assertEqual(got, {"原因": C.LOGIN, "认法": C.EXACT, "恢复时间": ""})

    def test_429_exact_with_reset_time(self):
        got = C.classify(objs("429_stream.jsonl"), (S / "429_stderr.log").read_text(), 1)
        self.assertEqual(got["原因"], C.QUOTA)
        self.assertEqual(got["认法"], C.EXACT)
        self.assertEqual(got["恢复时间"], "2026-11-17T13:29:25Z")        # rate_limit_event 的 resetsAt 1794922165

    def test_rc_zero_never_counts(self):
        self.assertIsNone(C.classify(objs("401_stream.jsonl"), "", 0))

    def test_api_retry_alone_is_not_evidence(self):
        """只有两条 system/api_retry（error 也写着 authentication_failed），后面没有 assistant、result：原话不算。"""
        retry = [o for o in objs("401_stream.jsonl") if o.get("type") == "system"]
        self.assertEqual(len(retry), 2)
        self.assertIsNone(C.from_stream(retry))
        self.assertIsNone(C.classify(retry, "", 1))

    def test_103820_empty_stream_session_record_is_loose(self):
        """#103820：stream-json 空、退出码 1，会话记录里最后一条 assistant 是额度用完的原话 → 宽认。"""
        with tempfile.TemporaryDirectory() as t:
            proj = Path(t) / "projects" / "-home-runner-work-x"
            proj.mkdir(parents=True)
            (proj / "sess.jsonl").write_text((S / "103820_session.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
            got = C.classify([], "", 1, Path(t) / "projects", since=time.time() - 60)
            self.assertEqual(got, {"原因": C.QUOTA, "认法": C.LOOSE, "恢复时间": "2026-11-17T13:29:25Z"})
            # 会话记录是这一步开始以前的（比如前一次写稿的）：不算
            old = time.time() - 3600
            os.utime(proj / "sess.jsonl", (old, old))
            self.assertIsNone(C.classify([], "", 1, Path(t) / "projects", since=time.time() - 60))

    def test_103820_login_variant_by_text(self):
        """会话记录里只有文字、没有结构字段时，按文字开头认（登录失效）。"""
        row = json.loads((S / "103820_session.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        for k in ("error", "apiError", "apiErrorStatus", "apiErrorParams"):
            row.pop(k, None)
        row["message"]["content"] = [{"type": "text", "text": "Failed to authenticate. API Error: 401 …"}]
        with tempfile.TemporaryDirectory() as t:
            proj = Path(t) / "p" / "x"
            proj.mkdir(parents=True)
            (proj / "s.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            self.assertEqual(C.classify([], "", 1, Path(t) / "p")["原因"], C.LOGIN)

    def test_exit1_with_no_evidence_anywhere_is_not_recognized(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "projects").mkdir()
            self.assertIsNone(C.classify([], "Warning: no stdin data received in 3s, proceeding without it.", 1,
                                         Path(t) / "projects", since=time.time()))

    def test_stderr_loose(self):
        self.assertEqual(C.classify([], "Error: Please run /login · API Error: 401", 1)["原因"], C.LOGIN)
        self.assertEqual(C.classify([], "You've hit your weekly limit · resets Nov 20", 1),
                         {"原因": C.QUOTA, "认法": C.LOOSE, "恢复时间": ""})


def a(**kw):
    return dict({"type": "assistant", "message": {"content": [{"type": "text", "text": "x"}]}}, **kw)


def r(**kw):
    return dict({"type": "result", "subtype": "success", "is_error": False}, **kw)


class NotDown(unittest.TestCase):
    """这些照旧报错，不切备用。"""

    def test_other_errors(self):
        cases = {
            "overloaded": [a(error="overloaded", is_api_error_message=True, api_error_status=529),
                           r(is_error=True, api_error_status=529, terminal_reason="api_error")],
            "server_error": [a(error="server_error", is_api_error_message=True, api_error_status=500),
                             r(is_error=True, api_error_status=500)],
            "轮数用完": [a(), r(subtype="error_max_turns", is_error=True, terminal_reason="max_turns")],
            "普通 429（没有 usage_limit_reached）": [a(error="rate_limit", is_api_error_message=True, api_error_status=429),
                                               r(is_error=True, api_error_status=429)],
            "403 账号被停": [a(error="account_on_hold", is_api_error_message=True, api_error_status=403),
                         r(is_error=True, api_error_status=403)],
            "超时被停（没有 result）": [a(), {"type": "user"}, a()],
        }
        for name, rows in cases.items():
            self.assertIsNone(C.classify(rows, "", 1), name)

    def test_401_midway_then_recovered_not_counted(self):
        rows = objs("401_stream.jsonl")[:3] + [a(), r(subtype="error_max_turns", is_error=True)]
        self.assertIsNone(C.classify(rows, "", 1))

    def test_rate_limit_rejected_with_overage_allowed_is_not_quota(self):
        ev = {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "overageStatus": "allowed", "resetsAt": 1}}
        self.assertIsNone(C.from_stream([ev]))

    def test_near_full_warning_only_notes(self):
        ev = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning",
                                                             "unifiedWindows": {"seven_day": {"utilization": 0.96}}}}
        self.assertTrue(C.near_full([ev]))
        self.assertIsNone(C.classify([ev, a(), r(subtype="error_max_turns", is_error=True)], "", 1))


class Main(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.hist = Path(self.t.name) / "测试版"
        self.issue = self.hist / DAY
        (self.issue / "logs").mkdir(parents=True)
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("FD_MIMO_AUTORELEASE", None)

    def tearDown(self):
        self.env.stop()
        self.t.cleanup()

    def run_main(self, step, sample, *extra):
        args = ["--issue", str(self.issue), "--step", step, "--stream", str(S / ("%s_stream.jsonl" % sample)),
                "--stderr", str(S / ("%s_stderr.log" % sample)), "--rc", "1", "--sessions", str(Path(self.t.name) / "无")]
        return C.main(args + list(extra))

    def marker(self):
        return json.loads((self.issue / C.MARKER).read_text(encoding="utf-8"))

    def test_write_step_marker_fields(self):
        self.assertEqual(self.run_main("写稿", "401"), C.EXIT_DOWN)
        mk = self.marker()
        self.assertEqual(mk["原因"], C.LOGIN)
        self.assertEqual(mk["认法"], C.EXACT)
        self.assertEqual(mk["哪一步"], ["写稿"])
        self.assertEqual(mk["恢复时间"], "")
        self.assertEqual(mk["连续第几天"], 1)
        self.assertIs(mk["自动放行"], False)
        self.assertRegex(mk["写于"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        for k in ("原因", "认法", "哪一步", "恢复时间", "连续第几天", "自动放行", "写于"):
            self.assertIn(k, mk)

    def test_merge_write_and_review(self):
        self.assertEqual(self.run_main("写稿", "401"), C.EXIT_DOWN)
        os.environ["FD_MIMO_AUTORELEASE"] = "true"
        self.assertEqual(self.run_main("审片", "429"), C.EXIT_DOWN)
        mk = self.marker()
        self.assertEqual(mk["哪一步"], ["写稿", "审片"])
        self.assertEqual(mk["原因"], C.OTHER)                     # 两次原因不一样
        self.assertEqual(mk["各步"]["写稿"]["原因"], C.LOGIN)
        self.assertEqual(mk["各步"]["审片"]["原因"], C.QUOTA)
        self.assertEqual(mk["恢复时间"], "2026-11-17T13:29:25Z")
        self.assertIs(mk["自动放行"], True)
        self.assertEqual(mk["连续第几天"], 1)

    def test_autorelease_only_exact_true(self):
        for v, want in (("true", True), ("True", False), ("1", False), ("on", False), ("", False)):
            os.environ["FD_MIMO_AUTORELEASE"] = v
            self.assertIs(C.autorelease(), want, v)

    def test_dry_writes_nothing(self):
        self.assertEqual(self.run_main("写稿", "429", "--dry"), C.EXIT_DOWN)
        self.assertFalse((self.issue / C.MARKER).exists())

    def test_not_down_exit_zero_no_marker(self):
        args = ["--issue", str(self.issue), "--step", "写稿", "--stream", str(Path(self.t.name) / "没有.jsonl"),
                "--rc", "1", "--sessions", str(Path(self.t.name) / "无")]
        self.assertEqual(C.main(args), C.EXIT_NO)
        self.assertFalse((self.issue / C.MARKER).exists())

    def test_writing_already_done_does_not_switch(self):
        """Claude 写完第 4–9 步、写总结时才用完额度：不切（2.2③）。"""
        d = self.issue
        (d / "logs" / "fd_state.json").write_text(json.dumps(done_state(), ensure_ascii=False), encoding="utf-8")
        for rel, text in (("02_选题/最终选题.json", "{}"), ("04_文稿/claude_网页.json", "{}"), ("04_文稿/claude_播客_v3.md", "## 开场\n"),
                          ("审读意见.md", "必须改：2\n"), ("审读处理.md", "# 处理\n")):
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(text, encoding="utf-8")
        self.assertTrue(C.writing_done(d))
        self.assertEqual(self.run_main("写稿", "429"), C.EXIT_DONE_ALREADY)
        self.assertFalse((d / C.MARKER).exists())
        # 测试时把稿子挪开、fd 状态还写着做完：不算做完，要切
        (d / "04_文稿" / "claude_网页.json").rename(d / "网页挪开.json")
        self.assertFalse(C.writing_done(d))
        self.assertEqual(self.run_main("写稿", "429"), C.EXIT_DOWN)
        # 审读必须改 0 条时不要处理记录
        (d / "网页挪开.json").rename(d / "04_文稿" / "claude_网页.json")
        (d / "审读处理.md").rename(d / "处理挪开.md")
        self.assertFalse(C.writing_done(d))
        (d / "审读意见.md").write_text("必须改：0\n", encoding="utf-8")
        self.assertTrue(C.writing_done(d))

    def test_review_already_done_does_not_switch(self):
        (self.issue / "审片结论.json").write_text(json.dumps({"放行": True, "立即": []}), encoding="utf-8")
        self.assertEqual(self.run_main("审片", "401"), C.EXIT_DONE_ALREADY)
        (self.issue / "审片结论.json").write_text("{写坏了", encoding="utf-8")
        self.assertEqual(self.run_main("审片", "401"), C.EXIT_DOWN)

    def test_bad_day_is_program_error(self):
        bad = self.hist / "不是日期"
        bad.mkdir()
        with self.assertRaises(ValueError):
            C.main(["--issue", str(bad), "--step", "写稿", "--stream", str(S / "401_stream.jsonl"), "--rc", "1"])


class Streak(unittest.TestCase):
    def mark(self, root, *days):
        for d in days:
            (Path(root) / d).mkdir(parents=True, exist_ok=True)
            (Path(root) / d / C.MARKER).write_text("{}", encoding="utf-8")

    def test_today_is_day_one(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(C.streak(t, "2026-11-18"), 1)

    def test_saturday_skipped_not_breaking(self):
        with tempfile.TemporaryDirectory() as t:
            # 2026-11-16 周一：往前 15 日周日、14 日周六（跳过）、13 日周五
            self.mark(t, "2026-11-15", "2026-11-13")
            self.assertEqual(C.streak(t, "2026-11-16"), 3)
            # 周六那天就算有记号也不算一天
            self.mark(t, "2026-11-14")
            self.assertEqual(C.streak(t, "2026-11-16"), 3)

    def test_gap_stops(self):
        with tempfile.TemporaryDirectory() as t:
            self.mark(t, "2026-11-17", "2026-11-15")           # 11-16 没有
            self.assertEqual(C.streak(t, "2026-11-18"), 2)

    def test_at_most_14_days_back(self):
        with tempfile.TemporaryDirectory() as t:
            from datetime import date, timedelta
            d0 = date(2026, 11, 30)
            self.mark(t, *[(d0 - timedelta(days=i)).isoformat() for i in range(1, 30)])
            # 往前 14 天里有 2 个周六（11-28、11-21），算 12 天，加今天 13
            self.assertEqual(C.streak(t, d0.isoformat()), 13)


class SamplesArePublicSafe(unittest.TestCase):
    def test_no_local_paths(self):
        for f in S.iterdir():
            text = f.read_text(encoding="utf-8")
            for bad in ("/Users/", "/private/", "/home/", "scratchpad", "London", '"cwd"', "api-request-blob"):
                self.assertNotIn(bad, text, "%s 里有 %s" % (f.name, bad))


if __name__ == "__main__":
    unittest.main()
