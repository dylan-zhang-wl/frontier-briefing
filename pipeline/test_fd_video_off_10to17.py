#!/usr/bin/env python3
"""fd 的"视频"开关管到第 10–17 步（2026-11-17 加，feat/mimo-release）。

查这几件事（开关关着＝这一期不出视频；开着＝和加开关以前一样）：
  · 第 10 步：关着不读分镜、不要视频图，说法写"视频：关"；开着照旧读分镜里的 image_requests；
  · 第 11 步：关着一次都不叫 video3_build（不花钱），附加记"视频旁白": "不配（视频：关）"、"视频开关": "关"，钱全给播客，
    产出里没有视频旁白的 voice.json；开着照旧先配播客、再配视频旁白；
  · 第 11、14、15 步的输入指纹：开着和加开关以前一字不差，关着多一项"=视频=关"，开换关、关换开都重做；
  · 第 14 步：关着"跳过"，说明带"视频：关"，附加"视频开关": "关"；
  · 第 15 步：关着没有旧视频就"跳过"（说明带"视频：关"），有旧的 11_视频v3 就挪开、再组装，附加"带视频": False；
  · 第 16 步：关着在 验收.json 记一笔，说明写"视频：关"；
  · 第 17 步：报告不把视频算"少了"，写"这一期齐了：网页、播客都有……视频：关"；自检.md 写"视频：关"；
  · fd run 开头那一行。
用法（在项目根运行）：~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_fd_video_off_10to17.py
不调用任何模型、不花钱；只在临时目录读写，跑子程序的地方都换成假的。
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

from orchestrator import common, report, runner, selfcheck as SC, steps  # noqa: E402

POD = "04_文稿/claude_播客_v3.md"
HUMAN = "05_配音/播客_v3"
ED = {"播客稿": POD, "人声": HUMAN, "混音": "05_配音/播客_v3_带音效", "配音方式": "单人", "日子": "日常", "名字": "工作日版",
      "周末检查": None}


class Env:
    """临时设环境变量 FD_VIDEO（None＝环境里没有），开关文件指到一个不存在的地方（按"开"）。"""

    def __init__(self, env=None):
        self.env = env

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = [mock.patch.object(common, "SWITCH_FILE", Path(self.tmp.name) / "没有.json"),
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


class FakeState:
    def __init__(self, rec=None):
        self.rec = rec or {}

    def step(self, key):
        return self.rec.get(key)


class FakeLedger:
    def __init__(self):
        self.added = []

    def status(self):
        return {"上限美元": 8.0, "Gemini已记美元": 1.0, "到90%": False, "比例": 0.125}

    def issue_total(self, sv):
        return 0.0

    def add(self, *a):
        self.added.append(a)


class FakeCtx:
    """各步 run 用到的那几样。c.run 记下每条命令，按标签给假输出；label 在 fail 里的返回退出码 1。"""

    def __init__(self, issue, state=None, offline=False, skip_images=False, fail=()):
        self.issue = Path(issue)
        self.logs = self.issue / "logs"
        self.state = state or FakeState()
        self.ed, self.edition, self.day = ED, "weekday", self.issue.name
        self.offline, self.skip_images, self.preview, self.lenient = offline, skip_images, False, False
        self.budget, self.force_backup = 0.6, False
        self.ledger = FakeLedger()
        self.run_id = "20261117-120000"
        self.web_cfg = self.issue / "10_网页配置.py"
        self.env = {}
        self.cmds = []
        self.fail = set(fail)
        self.steps = steps.BY_KEY

    def p(self, x):
        return Path(x) if os.path.isabs(str(x)) else self.issue / x

    def py(self, *a):
        return ["py"] + [str(x) for x in a]

    def show(self, cmd):
        return " ".join(str(x) for x in cmd)

    def again(self):
        return "./fd run --date %s" % self.day

    def log_path(self, step):
        return self.logs / ("%02d_%s.log" % (step.no, step.name))

    def run(self, step, cmd, label="", timeout=None, env=None):
        self.cmds.append((label, [str(x) for x in cmd]))
        return (1 if label in self.fail else 0), ""

    def quiet(self, cmd, timeout=120):
        return 0, ""


def make_issue(root, storyboard=True):
    d = Path(root) / "2026-11-16"
    for sub in ("04_文稿", "03_事件卡", "06_配图", HUMAN, "logs"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    (d / POD).write_text("## 开场\n\n我是 Shirley。\n", encoding="utf-8")
    (d / common.WEB_DRAFT).write_text(json.dumps({"sections": [{"kind": "headline", "items": [{"id": "E001"}]}]}),
                                      encoding="utf-8")
    if storyboard:
        (d / common.STORYBOARD).write_text(json.dumps({"image_requests": [{"id": "v_a"}, {"id": "v_wiki", "commons": True}]}),
                                           encoding="utf-8")
    for n in ("card", "e001"):
        (d / "06_配图" / (n + ".png")).write_bytes(b"x")
    for n in ("episode.mp3", "chapters.json", "qc.json"):
        (d / HUMAN / n).write_text("{}", encoding="utf-8")
    return d


# ================================================================ 第 10 步
class Step10(unittest.TestCase):
    def test_wanted(self):
        with tempfile.TemporaryDirectory() as t:
            c = FakeCtx(make_issue(t))
            with Env(None):
                self.assertEqual(steps.Images().wanted(c), (["card", "e001"], ["v_a"]))     # 开着：照旧读分镜
            with Env("off"):
                self.assertEqual(steps.Images().wanted(c), (["card", "e001"], []))          # 关着：分镜哪怕在也不读

    def test_run_off_and_on(self):
        with tempfile.TemporaryDirectory() as t:
            c = FakeCtx(make_issue(t), offline=True)
            with Env("off"):
                r = steps.Images().run(c, "run")
                self.assertEqual(r.status, steps.DONE)
                self.assertIn("视频：关", r.msg)
                self.assertEqual(r.extra, {"视频开关": "关"})
                self.assertTrue(steps.Images().outputs_exist(c))
                self.assertEqual(steps.Images().plan(c), ["网页 2 张都在（视频：关，不要视频图）"])
            with Env(None):
                r = steps.Images().run(c, "run")                     # 开着：缺视频图 v_a，离线 → 跳过（和原来一样）
                self.assertEqual(r.status, steps.SKIPPED)
                self.assertEqual(r.msg, "缺图：网页 无；视频 v_a。网页缺图画主题色抽象封面，视频那几块不带图")
                self.assertEqual(r.extra, {"缺网页配图": [], "缺视频配图": ["v_a"]})

    def test_off_missing_web_image(self):
        with tempfile.TemporaryDirectory() as t:
            issue = make_issue(t)
            (issue / "06_配图" / "e001.png").rename(issue / "e001_挪开.png")
            c = FakeCtx(issue, skip_images=True)
            with Env("off"):
                r = steps.Images().run(c, "run")
            self.assertEqual(r.status, steps.SKIPPED)
            self.assertEqual(r.extra["缺网页配图"], ["e001"])
            self.assertEqual(r.extra["缺视频配图"], [])
            self.assertNotIn("视频那几块", r.msg)
            c = FakeCtx(issue)
            with Env("off"), mock.patch.object(steps.Images, "agy_status", return_value=(True, "agy 今天能用")):
                r = steps.Images().run(c, "run")
            self.assertEqual(r.status, steps.WAITING)
            todo = "\n".join(r.todo)
            self.assertIn("视频：关，这一期不要视频图", todo)
            self.assertNotIn("video3_images.py", todo)


# ================================================================ 第 11 步
class Step11(unittest.TestCase):
    def test_outputs_inputs(self):
        c = FakeCtx("/nonexistent/2026-11-16")
        old_out = ["%s/episode.mp3" % HUMAN, "%s/chapters.json" % HUMAN, "%s/qc.json" % HUMAN, "05_配音/视频旁白_v3/voice.json"]
        with Env(None):
            self.assertEqual(steps.Voice().outputs(c), old_out)                                   # 开着：和原来一字不差
            self.assertEqual(steps.Voice().inputs(c), [POD, common.STORYBOARD, str(common.PROFILE)])
        with Env("off"):
            self.assertEqual(steps.Voice().outputs(c), old_out[:3])
            self.assertEqual(steps.Voice().inputs(c), [POD, str(common.PROFILE), "=视频=关"])

    def test_decide_budget(self):
        c = FakeCtx("/nonexistent/2026-11-16")
        with Env(None):
            d = steps.Voice().decide(c)
        self.assertEqual((d["播客预算"], d["视频预算"]), (0.5, 0.1))                             # 0.6：视频 min(0.10, 0.15)
        with Env("off"):
            d = steps.Voice().decide(c)
        self.assertEqual((d["播客预算"], d["视频预算"]), (0.6, 0.0))

    def run_voice(self, env, how="run"):
        with tempfile.TemporaryDirectory() as t:
            c = FakeCtx(make_issue(t))
            with Env(env), mock.patch.object(steps, "running_scripts", return_value=[]), \
                    mock.patch.object(steps, "usage_new_spend", return_value=(0.0, "usage.json")):
                r = steps.Voice().run(c, how)
            return r, [x for x, _ in c.cmds]

    def test_run_off_never_calls_video_build(self):
        r, labels = self.run_voice("off")
        self.assertEqual(labels, ["播客·主声音"])                     # 只配播客，一次都不叫 video3_build
        self.assertEqual(r.status, steps.DONE)
        self.assertEqual(r.extra["视频旁白"], "不配（视频：关）")
        self.assertEqual(r.extra["视频开关"], "关")
        self.assertNotIn("视频引擎", r.extra)
        self.assertEqual(r.msg, "播客：主声音；视频旁白：不配（视频：关）")
        self.assertFalse(any("没配成" in w for w in r.warns))

    def test_run_on_as_before(self):
        r, labels = self.run_voice(None)
        self.assertEqual(labels, ["播客·主声音", "视频旁白·主声音"])
        self.assertEqual(r.extra["视频旁白"], "主声音（旁白没改，沿用已有配音）")
        self.assertEqual(r.extra["视频引擎"], "gemini")
        self.assertNotIn("视频开关", r.extra)

    def test_adopt(self):
        r, labels = self.run_voice("off", "adopt")
        self.assertEqual(labels, [])
        self.assertEqual(r.extra, {"播客": "沿用已有", "视频旁白": "不配（视频：关）", "视频开关": "关"})
        r, _ = self.run_voice(None, "adopt")
        self.assertEqual(r.extra, {"播客": "沿用已有", "视频旁白": "沿用已有", "视频引擎": "gemini"})

    def test_plan_off(self):
        with tempfile.TemporaryDirectory() as t:
            c = FakeCtx(make_issue(t), offline=True)
            with Env("off"):
                lines = steps.Voice().plan(c)
            self.assertIn("视频旁白：不配（视频：关）", lines)
            self.assertFalse(any("video3_build" in x for x in lines))
            with Env(None):
                lines = steps.Voice().plan(c)
            self.assertTrue(any(x.startswith("视频旁白：py ") and "video3_build.py" in x for x in lines))


# ================================================================ 输入指纹（第 11、14、15 步）
class Fingerprints(unittest.TestCase):
    def test_on_same_as_before_and_switching_reruns(self):
        with tempfile.TemporaryDirectory() as t:
            c = FakeCtx(make_issue(t))
            for step in (steps.Voice(), steps.Video(), steps.Web2()):
                c.state = FakeState()
                with Env(None):
                    fp_on = step.input_fp(c)
                self.assertNotIn("视频", fp_on, step.key)                       # 开着：和加开关以前一字不差
                with Env("off"):
                    fp_off = step.input_fp(c)
                self.assertEqual(fp_off["视频"], "关")
                self.assertIn("视频", runner.diff_inputs(fp_on, fp_off), step.key)        # 开 → 关：重做
                c.state = FakeState({step.key: {"输入指纹": fp_off}})
                with Env(None):
                    fp_back = step.input_fp(c)
                self.assertEqual(fp_back["视频"], "")
                self.assertIn("视频", runner.diff_inputs(fp_off, fp_back), step.key)      # 关 → 开：也重做
                c.state = FakeState({step.key: {"输入指纹": fp_back}})
                with Env(None):
                    self.assertEqual(runner.diff_inputs(fp_back, step.input_fp(c)), [])  # 再开着跑：不再重做

    def test_video_inputs_on_literal(self):
        c = FakeCtx("/nonexistent/2026-11-16")
        with Env(None), mock.patch.dict(os.environ, {}, clear=False):
            for k in ("FD_MOTION", "FD_DIRECTOR", "FD_DIRECTOR_NARRATION", "FD_VIDEO_ZH_WRAP", "FD_EXCERPT_PHOTO"):
                os.environ.pop(k, None)
            # 11-21 合并加"=摘录卡压图="（网页／视频那一路 11-15 加的开关）：这里 fd_开关.json 换成了不存在的文件，摘录卡开关按"关"，
            # 所以是"=摘录卡压图=关"；视频开关开着时这一列表和只合了网页／视频那一路时一字不差，后面不多"=视频="
            self.assertEqual(steps.Video().inputs(c), [common.STORYBOARD, "05_配音/视频旁白_v3/voice.json", common.CARDS,
                                                       "@step:web", "=新动效=", "=视频导演=", "=导演旁白=", "=中文整词换行=",
                                                       "=摘录卡压图=关"])
            self.assertEqual(steps.Web2().inputs(c), ["@step:web", "11_视频v3/video3_media.json"])


# ================================================================ 第 14、15 步
class Step14And15(unittest.TestCase):
    def test_video_skipped_when_off(self):
        with tempfile.TemporaryDirectory() as t:
            c = FakeCtx(make_issue(t))
            with Env("off"):
                r = steps.Video().run(c, "run")
                plan = steps.Video().plan(c)
            self.assertEqual(r.status, steps.SKIPPED)
            self.assertIn("视频：关", r.msg)
            self.assertTrue(r.go_on)
            self.assertEqual(r.extra, {"视频开关": "关"})
            self.assertEqual(c.cmds, [])
            self.assertEqual(len(plan), 1)
            self.assertIn("视频：关", plan[0])

    def test_web2_off_no_old_video(self):
        with tempfile.TemporaryDirectory() as t:
            c = FakeCtx(make_issue(t), state=FakeState({"video": {"状态": steps.SKIPPED}}))
            with Env("off"):
                r = steps.Web2().run(c, "run")
            self.assertEqual(r.status, steps.SKIPPED)
            self.assertIn("视频：关", r.msg)
            self.assertEqual(r.extra, {"带视频": False, "视频开关": "关"})
            self.assertEqual(c.cmds, [])

    def web2_rebuild(self, env, video_state, js):
        with tempfile.TemporaryDirectory() as t:
            issue = make_issue(t)
            (issue / "11_视频v3").mkdir()
            (issue / "11_视频v3" / "video3_media.json").write_text("{}", encoding="utf-8")
            (issue / "10_网页配置.py").write_text("#", encoding="utf-8")
            out = issue / "10_网页v3" / "issues" / issue.name / "issue.js"
            out.parent.mkdir(parents=True)
            out.write_text(js, encoding="utf-8")
            c = FakeCtx(issue, state=FakeState({"video": {"状态": video_state}}))
            with Env(env):
                r = steps.Web2().run(c, "run")
            return r, [x for x, _ in c.cmds], (issue / "11_视频v3").exists(), sorted(p.name for p in issue.iterdir())

    def test_web2_off_moves_old_video_aside(self):
        # 第 14 步哪怕记着"做完"（以前开着跑过），关着时旧的 11_视频v3 也挪开、再组装，网页不带视频
        r, labels, still, names = self.web2_rebuild("off", steps.DONE, 'window.ISSUE={"media":{}}')
        self.assertEqual(labels, ["再组装"])
        self.assertFalse(still)
        self.assertIn("11_视频v3_未用_20261117-120000", names)
        self.assertEqual(r.status, steps.DONE)
        self.assertEqual(r.msg, "网页不带视频（视频：关）")
        self.assertEqual(r.extra, {"带视频": False, "视频开关": "关"})
        self.assertTrue(any("视频：关" in w for w in r.warns))

    def test_web2_off_chart_number_is_not_video(self):
        # 图表里的 "v":3.98 不算视频（11-17 云端那期就有）；真的视频 "video":{"v":3, 才算
        r, _, _, _ = self.web2_rebuild("off", steps.DONE, '{"items":[{"label_zh":"x","v":3.98}]}')
        self.assertEqual(r.extra["带视频"], False)
        r, _, _, _ = self.web2_rebuild("off", steps.DONE, '{"media":{"video":{"v":3,"schema":"video3-storyboard/1"}}}')
        self.assertEqual(r.extra["带视频"], True)

    def test_web2_on_as_before(self):
        r, labels, still, _ = self.web2_rebuild(None, steps.DONE, 'x={"v":3}')
        self.assertEqual((labels, still), (["再组装"], True))
        self.assertEqual((r.status, r.msg, r.extra), (steps.DONE, "网页带视频", {"带视频": True}))
        r, labels, still, _ = self.web2_rebuild(None, steps.FAILED, 'x={}')
        self.assertEqual((labels, still), (["再组装"], False))
        self.assertEqual((r.msg, r.extra), ("网页不带视频", {"带视频": False}))
        self.assertTrue(any(w.startswith("视频没成，旧的 11_视频v3 挪到") for w in r.warns))


# ================================================================ 第 16 步
class Step16(unittest.TestCase):
    def run_accept(self, env):
        with tempfile.TemporaryDirectory() as t:
            issue = make_issue(t)
            web = issue / "10_网页v3"
            web.mkdir()
            (web / "index.html").write_text("<html></html>", encoding="utf-8")
            (web / "自检报告.json").write_text(json.dumps({"首屏": {"errors": [], "overflowX": 0, "totalKB": 900}}), encoding="utf-8")
            c = FakeCtx(issue, state=FakeState({"web": {"附加": {"播客": "无"}}}))
            outs = {"截图自检": "", "上标": '390 {"lonely": []}', "听这一段": "按钮数：0"}
            c.run = lambda step, cmd, label="", timeout=None, env=None: (0, outs[label])
            with Env(env):
                r = steps.Accept().run(c, "run")
            return r, json.loads((issue / "logs" / "验收.json").read_text(encoding="utf-8"))

    def test_off_notes_it(self):
        r, res = self.run_accept("off")
        self.assertEqual(r.status, steps.DONE)
        self.assertTrue(r.msg.endswith("（视频：关，这一期没有视频）"))
        self.assertEqual(res["视频开关"], "关")
        r, res = self.run_accept(None)
        # 11-21："听这一段"那半句按实际查了什么写（这里没有播客），不再一律写"正常"
        self.assertEqual(r.msg, "三种视图无报错、不横滚、不缺字；上标不掉行；'听这一段'：没有播客，不查")
        self.assertNotIn("视频开关", res)


# ================================================================ 第 17 步：报告、自检
OFF_STATE = {
    "voice": {"状态": "做完", "说明": "播客：主声音；视频旁白：不配（视频：关）",
              "附加": {"播客": "主声音", "视频旁白": "不配（视频：关）", "视频开关": "关"}},
    "video": {"状态": "跳过", "说明": "视频：关，这一期不出视频", "附加": {"视频开关": "关"}},
    "web2": {"状态": "跳过", "说明": "视频：关，第 13 步的网页就是成品", "附加": {"带视频": False, "视频开关": "关"}},
}


class Report(unittest.TestCase):
    def ctx(self, rec):
        c = mock.Mock()
        c.state = FakeState(rec)
        return c

    def test_missing(self):
        self.assertEqual(report.missing(self.ctx(OFF_STATE)), [])
        broken = {"voice": {"附加": {"视频旁白": "主声音"}}, "video": {"状态": "失败", "说明": "视频没组装成"}}
        self.assertEqual(report.missing(self.ctx(broken)), ["视频（视频没组装成）"])     # 开着那天视频真坏了：照旧算少了

    def test_selfcheck_off(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d / "06_配图").mkdir()
            sec = SC.build(d, OFF_STATE, {}, {}, SC.images_summary(d, ["card"], [], video_off=SC.video_off(OFF_STATE)),
                           "2026-11-17T12:00:00Z")
        self.assertIn("- 视频：关，这一期不出视频（第 14 步跳过，第 15 步网页不带视频）", sec)
        self.assertIn("- 视频图：视频：关，这一期不要视频图", sec)
        self.assertNotIn("老路", sec)
        self.assertIn("视频旁白 不配（视频：关）", sec)
        self.assertFalse(SC.video_off({"video": {"附加": None}, "web2": {}}))

    def test_write_says_complete_without_video(self):
        with tempfile.TemporaryDirectory() as t:
            issue = Path(t) / "2026-11-16"
            issue.mkdir()
            rec = {s.key: {"状态": steps.DONE, "说明": "x"} for s in steps.STEPS}
            rec.update(OFF_STATE)
            c = mock.Mock(day="2026-11-16", issue=issue, default_issue=False, ed={"名字": "工作日版"}, offline=False)
            c.state = FakeState(rec)
            c.p = lambda x: issue / x
            c.again.return_value = "./fd run"
            c.ledger.status.return_value = {"Gemini已记美元": 1.0, "上限美元": 8.0, "比例": 0.1, "到90%": False}
            c.ledger.issue_total.return_value = 0.0
            c.ledger.month_total.return_value = 0.0
            c.ledger.issue_data.return_value = {}
            c.ledger.month_file = issue / "账本.json"
            path = report.write(c, {"停在": None, "原因": ""}, 1, 17)
            text = path.read_text(encoding="utf-8")
        self.assertIn("- **这一期齐了**：网页、播客都有，各项检查都过了；视频：关，这一期不出视频（第 14 步跳过，第 15 步网页不带视频）。", text)
        self.assertNotIn("数据版", text)


class Header(unittest.TestCase):
    def test_header_line(self):
        c = mock.Mock(day="2026-11-16", issue=Path("/x/2026-11-16"), default_issue=False, edition="weekday",
                      ed={"名字": "工作日版"}, db=Path("/x/db"), ledger_dir=Path("/x/l"), offline=True, lenient=False,
                      skip_images=False, dry_run=False)
        c.ledger.status.return_value = {"Gemini已记美元": 0.0, "上限美元": 8.0, "比例": 0.0, "到90%": False}
        buf = io.StringIO()
        with Env("off"), contextlib.redirect_stdout(buf):
            runner.header(c)
        self.assertIn("第 14 步跳过，第 15 步网页不带视频", buf.getvalue())
        self.assertNotIn("还没跟着改", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
