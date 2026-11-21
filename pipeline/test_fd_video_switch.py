#!/usr/bin/env python3
"""fd 的"视频"开关（2026-11-17 加）：关着时这一期不出视频，第 6–9 步不要求、不查视频分镜。

查这几件事：
  · 开关读法：环境变量 FD_VIDEO 比 fd_开关.json 的"视频"优先；文件没有、写坏了、值认不出按"开"；项目里的文件现在写"开"；
  · 第 6 步：开着要三份稿子（和原来一样），关着只要播客、网页两份；
  · 第 7 步：关着时分镜检查（helpers.py storyboard）不跑，易歧义词不带 --storyboard，摘要写"视频：关，分镜不查"；
    开着时照原来跑分镜检查、检查结果里没有新字段；
  · 第 7 步的输入指纹：开着时和加开关以前一字不差（往期不会因此重查），关着多一项"=视频=关"；从关换回开也会重查；
  · 第 8、9 步要人做的说明：关着时不提分镜文件，开着时照旧。
用法（在项目根运行）：~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_fd_video_switch.py
不调用任何模型、不花钱；只在临时目录读写。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
ROOT = PIPE.parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

from orchestrator import common, runner, steps  # noqa: E402

POD = "04_文稿/claude_播客_v3.md"


class Env:
    """临时改环境变量 FD_VIDEO 和开关文件的位置。env=None：环境里没有 FD_VIDEO。"""

    def __init__(self, env=None, file_text=None):
        self.env, self.file_text = env, file_text

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        f = Path(self.tmp.name) / "fd_开关.json"
        if self.file_text is not None:
            f.write_text(self.file_text, encoding="utf-8")
        self.p = [mock.patch.object(common, "SWITCH_FILE", f),
                  mock.patch.dict(os.environ, {"FD_VIDEO": self.env} if self.env is not None else {}, clear=False)]
        for x in self.p:
            x.start()
        if self.env is None:
            os.environ.pop("FD_VIDEO", None)
        return self

    def __exit__(self, *a):
        for x in reversed(self.p):
            x.stop()
        self.tmp.cleanup()


class Switch(unittest.TestCase):
    def test_default_on(self):
        with Env(None, None):
            self.assertTrue(common.video_switch()[0])
        with Env(None, "{坏的"):
            self.assertTrue(common.video_switch()[0])
        with Env(None, json.dumps({"视频": "开"})):
            self.assertTrue(common.video_switch()[0])
        with Env(None, json.dumps({"视频": "随便"})):
            on, why = common.video_switch()
            self.assertTrue(on)
            self.assertIn("认不出", why)
        with Env(None, json.dumps({"视频导演": "关", "视频中文整词换行": "关"})):    # 别的"视频…"开关不算
            self.assertTrue(common.video_switch()[0])

    def test_file_off(self):
        for v in ("关", "off", "关闭"):
            with Env(None, json.dumps({"视频": v})):
                on, why = common.video_switch()
                self.assertFalse(on)
                self.assertIn("fd_开关.json", why)

    def test_env_wins(self):
        with Env("off", json.dumps({"视频": "开"})):
            on, why = common.video_switch()
            self.assertFalse(on)
            self.assertIn("FD_VIDEO", why)
        with Env("on", json.dumps({"视频": "关"})):
            self.assertTrue(common.video_switch()[0])

    def test_project_file_is_on(self):
        d = json.loads((ROOT / "fd_开关.json").read_text(encoding="utf-8"))
        self.assertEqual(d["视频"], "开")


class FakeState:
    def __init__(self, rec=None):
        self.rec = rec or {}

    def step(self, key):
        return self.rec.get(key)


class FakeCtx:
    """第 7 步 suite 用到的那几样。c.run 按标签给假输出，记下每条命令。"""

    def __init__(self, issue, state=None, storyboard_rc=0):
        self.issue = Path(issue)
        self.logs = self.issue / "logs"
        self.state = state or FakeState()
        self.ed = {"播客稿": POD, "周末检查": None, "日子": "weekday", "名字": "工作日版",
                   "指令": {"播客": ["写稿_播客.md"], "网页": ["写稿_网页.md"], "视频": ["写稿_视频v3.md"]}}
        self.day, self.edition, self.lenient, self.run_id = self.issue.name, "weekday", False, "x"
        self.cmds = []
        self.storyboard_rc = storyboard_rc

    def p(self, x):
        return Path(x) if os.path.isabs(str(x)) else self.issue / x

    def py(self, *a):
        return ["py"] + [str(x) for x in a]

    def show(self, cmd):
        return " ".join(str(x) for x in cmd)

    def again(self):
        return "./fd run --date %s" % self.day

    def run(self, step, cmd, label="", timeout=None, env=None):
        self.cmds.append((label, [str(x) for x in cmd]))
        out = {"读音表": '{"要改": [], "提醒": [], "表里还没有": []}',
               "稿子": '{"要改": [], "请人工看": [], "概况": {}}',
               "今日一词": '{"要改": [], "提醒": []}',
               "易歧义词": '{"提醒": [], "说明": []}'}
        if label == "视频分镜":
            return self.storyboard_rc, ("分镜检查通过：6 章" if self.storyboard_rc == 0 else "✗ 要改：触发词「x」在旁白里找不到")
        return 0, out.get(label, "")


def make_issue(root, storyboard=True):
    d = Path(root) / "2026-11-16"
    (d / "04_文稿").mkdir(parents=True)
    (d / "03_事件卡").mkdir(parents=True)
    (d / POD).write_text("## 开场\n\n我是 Shirley。\n", encoding="utf-8")
    (d / common.WEB_DRAFT).write_text("{}", encoding="utf-8")
    (d / common.CARDS).write_text("[]", encoding="utf-8")
    if storyboard:
        (d / common.STORYBOARD).write_text("{}", encoding="utf-8")
    return d


class Step6(unittest.TestCase):
    def test_outputs_follow_switch(self):
        c = mock.Mock(ed={"播客稿": POD})
        with Env(None, None):
            self.assertEqual(steps.Write().outputs(c), [POD, common.WEB_DRAFT, common.STORYBOARD])
        with Env("off", None):
            self.assertEqual(steps.Write().outputs(c), [POD, common.WEB_DRAFT])

    def test_run_without_storyboard(self):
        with tempfile.TemporaryDirectory() as t:
            c = FakeCtx(make_issue(t, storyboard=False))
            with Env("off", None):
                r = steps.Write().run(c, "run")
                self.assertEqual(r.status, steps.DONE)
                self.assertIn("视频：关", r.msg)
            with Env(None, None):
                r = steps.Write().run(c, "run")
                self.assertEqual(r.status, steps.WAITING)          # 开着：照旧要分镜
                self.assertIn("视频v3_分镜.json", r.msg)


class Step7(unittest.TestCase):
    def test_off_skips_storyboard_and_says_so(self):
        with tempfile.TemporaryDirectory() as t:
            c = FakeCtx(make_issue(t), storyboard_rc=1)         # 分镜哪怕在、哪怕会不过，关着时也不查
            chk = steps.Check()
            with Env("off", None):
                res, must, soft = chk.suite(c)
                r = chk.judge(c, res, must, soft)
            labels = [x for x, _ in c.cmds]
            self.assertNotIn("视频分镜", labels)
            self.assertFalse(any("storyboard" in " ".join(cmd) for _, cmd in c.cmds if "helpers.py" in " ".join(cmd)))
            amb = [cmd for x, cmd in c.cmds if x == "易歧义词"][0]
            self.assertNotIn("--storyboard", amb)
            self.assertEqual(r.status, steps.DONE)
            self.assertIn("视频：关，分镜不查", r.msg)
            self.assertNotIn("视频分镜 过了", r.msg)
            saved = json.loads((c.issue / "logs/检查_稿子.json").read_text(encoding="utf-8"))
            self.assertEqual([i for i in saved["检查"] if i["名字"] == "视频分镜"][0]["不查"], "视频：关，分镜不查")

    def test_on_runs_storyboard_as_before(self):
        with tempfile.TemporaryDirectory() as t:
            c = FakeCtx(make_issue(t), storyboard_rc=1)
            chk = steps.Check()
            with Env(None, None):
                res, must, soft = chk.suite(c)
                r = chk.judge(c, res, must, soft)
            sb = [cmd for x, cmd in c.cmds if x == "视频分镜"]
            self.assertEqual(len(sb), 1)
            self.assertEqual(sb[0][-3:], ["storyboard", "--issue-dir", str(c.issue)])
            amb = [cmd for x, cmd in c.cmds if x == "易歧义词"][0]
            self.assertIn("--storyboard", amb)
            self.assertEqual(r.status, steps.WAITING)
            self.assertIn("视频分镜 1 处要改", r.msg)
            self.assertFalse(any("不查" in i for i in res["检查"]))             # 开着时检查结果没有新字段
            self.assertEqual(["读音表", "稿子", "视频分镜", "网页数字预检", "今日一词", "易歧义词"], [x for x, _ in c.cmds])

    def test_plan_lines(self):
        with tempfile.TemporaryDirectory() as t:
            c = FakeCtx(make_issue(t))
            with Env("off", None):
                lines = steps.Check().plan(c)
            self.assertIn("分镜：视频：关，分镜不查", lines)
            with Env(None, None):
                lines = steps.Check().plan(c)
            self.assertTrue(any(x.startswith("分镜：py ") and "storyboard" in x for x in lines))


class Step7Fingerprint(unittest.TestCase):
    def test_on_inputs_same_as_before(self):
        c = FakeCtx("/nonexistent/2026-11-16")
        with Env(None, None):
            self.assertEqual(steps.Check().inputs(c), [POD, common.WEB_DRAFT, common.STORYBOARD, common.CARDS])
        c.state = FakeState({"check": {"输入指纹": {POD: "a"}}})         # 往期记录（没有"视频"这一项）
        with Env(None, None):
            self.assertEqual(steps.Check().inputs(c), [POD, common.WEB_DRAFT, common.STORYBOARD, common.CARDS])

    def test_off_adds_marker_and_switching_reruns(self):
        with tempfile.TemporaryDirectory() as t:
            issue = make_issue(t)
            c = FakeCtx(issue)
            chk = steps.Check()
            with Env(None, None):
                fp_on = chk.input_fp(c)
            self.assertNotIn("视频", fp_on)
            with Env("off", None):
                self.assertIn("=视频=关", chk.inputs(c))
                fp_off = chk.input_fp(c)
            self.assertEqual(fp_off["视频"], "关")
            self.assertEqual(runner.diff_inputs(fp_on, fp_off), ["视频"])           # 开 → 关：重查
            c.state = FakeState({"check": {"输入指纹": fp_off}})
            with Env(None, None):
                fp_back = chk.input_fp(c)
            self.assertEqual(fp_back["视频"], "")
            self.assertEqual(runner.diff_inputs(fp_off, fp_back), ["视频"])         # 关 → 开：也重查，把分镜补查上
            c.state = FakeState({"check": {"输入指纹": fp_back}})
            with Env(None, None):
                self.assertEqual(runner.diff_inputs(fp_back, chk.input_fp(c)), [])  # 再开着跑：不再重查


class Step8And9Todo(unittest.TestCase):
    def todo_text(self, step, c):
        r = step.run(c, "run")
        return "\n".join(r.todo)

    def test_todo_mentions_storyboard_only_when_on(self):
        with tempfile.TemporaryDirectory() as t:
            c = FakeCtx(make_issue(t))
            c.state = FakeState({"review": {"附加": {"必须改": 2}}})
            for step in (steps.Review(), steps.Revise()):
                with Env(None, None):
                    self.assertIn("视频v3_分镜.json", self.todo_text(step, c))
                with Env("off", None):
                    txt = self.todo_text(step, c)
                    self.assertNotIn("视频v3_分镜.json", txt)
                    self.assertIn("视频：关", txt)


class Header(unittest.TestCase):
    def test_header_line_only_when_off(self):
        import contextlib
        import io
        c = mock.Mock(day="2026-11-16", issue=Path("/x/2026-11-16"), default_issue=False, edition="weekday",
                      ed={"名字": "工作日版"}, db=Path("/x/db"), ledger_dir=Path("/x/l"), offline=True, lenient=False,
                      skip_images=False, dry_run=False)
        c.ledger.status.return_value = {"Gemini已记美元": 0.0, "上限美元": 8.0, "比例": 0.0, "到90%": False}
        for env, want in ((None, False), ("off", True)):
            buf = io.StringIO()
            with Env(env, None), contextlib.redirect_stdout(buf):
                runner.header(c)
            self.assertEqual("视频：关" in buf.getvalue(), want)


if __name__ == "__main__":
    unittest.main()
