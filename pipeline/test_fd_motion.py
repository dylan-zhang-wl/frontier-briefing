#!/usr/bin/env python3
"""新动效并入正式流程（2026-11-07）的测试：fd 第 14 步的原文截图、第 7 步分镜检查认得新块、一键关回的开关。

查这几件事：
  · 开关：环境变量 FD_MOTION 比 fd_开关.json 优先；文件没有、写坏了按"开"；fd（common.motion_switch）和组装程序
    （video3_storyboard.motion_switch）两边说法一致；
  · 关着时 strip_motion 去掉新块和新字段（tally 的 count 不动）；不写新块的分镜原样不变；
  · 第 14 步的输入指纹：开着和加开关以前的记录一样（往期不会因此重做），一换开关就重做；
  · 第 14 步：先截图后组装；截图超时、出错、没写结果，都照常组装，只写提醒；开关关着、离线、分镜里没有截图时不截；
  · 第 7 步：check_motion 的几条提醒；第 7 步日志里"第 10 步才画的图""第 14 步才截的图"并成一行；
    原句核不上算"要改"（helpers.py storyboard 退出码 1）；开关关着时同一份分镜能过；
  · helpers.py shots 端到端：本机起一个仿新闻页（只连 127.0.0.1），一处截成、一处找不到原句退回摘录，写进 本期截图.json
    （没有 Chrome、Playwright 就跳过这一项）。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_fd_motion.py
    ~/.venvs/frontier-daily/bin/python pipeline/test_fd_motion.py        # 全部通过时退出码为 0
不调用任何模型、不花钱；读写只在临时目录。
"""
import copy
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
ROOT = PIPE.parent
TOOLS = ROOT / "site" / "tools"
for p in (str(PIPE), str(TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from orchestrator import common, runner, steps  # noqa: E402
import video3_storyboard as SB  # noqa: E402

PY = Path.home() / ".venvs/frontier-daily/bin/python"
HELPERS = PIPE / "orchestrator" / "helpers.py"
PW = Path.home() / ".npm/_npx/9833c18b2d85bc59/node_modules/playwright/index.mjs"
LAB = lambda zh, en, *ref: {"zh": zh, "en": en, "ref": list(ref)}  # noqa: E731

QUOTE = ("Following this week’s midterms where voters resoundingly voiced their opposition to data center expansion, OpenAI today "
         "announced new commitments to communities where it is working on data center projects, including that it won’t use "
         "non-disclosure agreements (NDAs) with public officials.")
SHOT_Q = "it won’t use non-disclosure agreements (NDAs) with public officials"


def cards(url1="https://www.theverge.com/x", url2="https://www.cnbc.com/x.html"):
    return [{"event_id": "E003", "title_zh": "数据中心投票", "sources": [
        {"id": "s1", "name": "The Verge · AI", "url": url1, "date": "2026-11-06T00:37:56Z"},
        {"id": "s2", "name": "CNBC · 科技", "url": url2, "date": "2026-11-05T13:44:45Z"}],
        "facts": [{"text_zh": "OpenAI 宣布对其数据中心项目所在社区作出新承诺，包括不再与公职人员使用保密协议（NDA）。", "source_id": "s1", "quote": QUOTE},
                  {"text_zh": "据 CNBC 汇总 Ballotpedia 的分析，10 个州共有 41 项地方投票措施，除一项外，选民全部支持限制措施或否决促开发措施。",
                   "source_id": "s2", "quote": "Out of 41 local ballot measures across 10 states, voters backed restrictions or rejected "
                                               "pro-development measures for all but one"}],
        "numbers": [], "who_said": []}]


FACTS = {"e003.nda": {"event": "E003", "field": "facts", "index": 0, "check": "不再与公职人员使用保密协议"},
         "e003.vote": {"event": "E003", "field": "facts", "index": 1, "check": "10 个州共有 41 项地方投票措施"}}
NARR = {"open": "11 月 6 日，选票给数据中心设下闸门，各地社区都在看。",
        "vote": "本周中期选举里，10 个州的 41 项数据中心投票措施，除了一项，选民都站在限制一边。周四，OpenAI 承诺不再和公职人员签保密协议。",
        "close": "合起来看，选票先动了。"}


def timeline(shot=True):
    t = {"type": "timeline", "id": "days", "ticks": [
        {"date": LAB("本周", "This week"), "cap": LAB("中期选举", "Midterms"), "at": "本周中期选举", "logos": ["openai"]},
        {"date": LAB("周四", "Thursday"), "cap": LAB("不再签保密协议", "No NDAs"), "at": "周四", "hot": True}],
        "cues": {"start": "本周中期选举"}}
    if shot:
        t["ticks"][1]["shot"] = {"fact": "e003.nda", "quote": SHOT_Q, "source": {"zh": "The Verge", "en": "The Verge"},
                                 "cues": {"mark": "不再和公职人员签保密协议"}}
    return t


def post(shot=True):
    b = {"type": "post_card", "id": "nda", "platform": {"kind": "post", "name": LAB("帖子", "Post")},
         "text": LAB("不再与公职人员使用保密协议", "No NDAs with public officials", "e003.nda"),
         "who": {"name": LAB("OpenAI", "OpenAI"), "role": LAB("据 The Verge", "via The Verge")}, "cues": {"show": "承诺不再和公职人员"}}
    if shot:
        b["shot"] = {"fact": "e003.nda", "quote": SHOT_Q, "cues": {"mark": "签保密协议"}}
    return b


def tally():
    return {"type": "tally", "id": "ballot", "region": LAB("10 个州", "10 states", "e003.vote"),
            "count": {"value": 41, "label": LAB("41 项地方投票措施", "41 local measures", "e003.vote")},
            "except": {"value": 1, "label": LAB("一项例外", "One exception", "e003.vote")},
            "cues": {"show": "10 个州", "count": "41 项", "except": "除了一项"}}


def storyboard(vote_blocks, open_blocks=None):
    return {"schema": SB.SCHEMA, "date": "2026-11-06", "accent": "coral",
            "title": {"date": "11.06", "main": LAB("今日地图", "Today's map"), "line": LAB("每日AI科技前沿简报", "Frontier Briefing")},
            "facts": copy.deepcopy(FACTS), "chapters": [
                {"id": "open", "kind": "open", "title": "开场", "label": LAB("开场", "Open"), "narration": NARR["open"], "cues": {"map": "11 月 6 日"},
                 "blocks": copy.deepcopy(open_blocks or [])},
                {"id": "vote", "kind": "story", "title": "选票", "label": LAB("选票", "The vote"), "storyline": "选票给数据中心设下闸门",
                 "narration": NARR["vote"], "map_cue": "选票给数据中心设下闸门", "chip": {"name": LAB("选票", "The vote")},
                 "relation": {"kind": ["规模"], "zh": "10 个州 41 项", "ref": ["e003.vote"]}, "stories": ["E003"],
                 "blocks": copy.deepcopy(vote_blocks)},
                {"id": "close", "kind": "close", "title": "收尾", "label": LAB("收尾", "End"), "narration": NARR["close"], "cues": {"map": "合起来看"},
                 "end": {"title": LAB("今天的地图", "Today's map"), "lines": [{"zh": "选票先动了", "en": "Ballots moved first", "cue": "选票先动了"}]}}]}


def make_issue(d, sb, cds=None):
    issue = Path(d) / "2026-11-06"
    (issue / "03_事件卡").mkdir(parents=True)
    (issue / "04_文稿").mkdir(parents=True)
    (issue / "03_事件卡/cards_写稿用.json").write_text(json.dumps(cds or cards(), ensure_ascii=False), encoding="utf-8")
    (issue / "04_文稿/视频v3_分镜.json").write_text(json.dumps(sb, ensure_ascii=False), encoding="utf-8")
    return issue


class Env:
    """临时改环境变量 FD_MOTION 和开关文件的位置。"""

    def __init__(self, env=None, file_text=None):
        self.env, self.file_text = env, file_text

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        f = Path(self.tmp.name) / "fd_开关.json"
        if self.file_text is not None:
            f.write_text(self.file_text, encoding="utf-8")
        self.p = [mock.patch.object(common, "SWITCH_FILE", f), mock.patch.object(SB, "MOTION_SWITCH_FILE", f),
                  mock.patch.dict(os.environ, {"FD_MOTION": self.env} if self.env is not None else {}, clear=False)]
        for x in self.p:
            x.start()
        if self.env is None:
            os.environ.pop("FD_MOTION", None)
        return self

    def __exit__(self, *a):
        for x in reversed(self.p):
            x.stop()
        self.tmp.cleanup()


class Switch(unittest.TestCase):
    def both(self):
        a, b = common.motion_switch(), SB.motion_switch()
        self.assertEqual(a[0], b[0], (a, b))
        return a[0]

    def test_default_on(self):
        with Env(None, None):
            self.assertTrue(self.both())
        with Env(None, "{坏的"):
            self.assertTrue(self.both())
        with Env(None, json.dumps({"新动效和原文截图": "开"})):
            self.assertTrue(self.both())

    def test_file_off(self):
        with Env(None, json.dumps({"新动效和原文截图": "关"})):
            self.assertFalse(self.both())
            self.assertTrue(SB.motion_off())

    def test_env_wins(self):
        with Env("off", json.dumps({"新动效和原文截图": "开"})):
            self.assertFalse(self.both())
        with Env("on", json.dumps({"新动效和原文截图": "关"})):
            self.assertTrue(self.both())

    def test_project_file_is_on(self):            # 11-08 起正式默认开
        d = json.loads((ROOT / "fd_开关.json").read_text(encoding="utf-8"))
        self.assertEqual(d["新动效和原文截图"], "开")


class Strip(unittest.TestCase):
    def test_strip_all_new_things(self):
        sb = storyboard([timeline(), post(),
                         {"type": "num_chain", "id": "ch", "items": [{"label": LAB("10 个州", "10", "e003.vote"), "cue": "10 个州"},
                                                                    {"label": LAB("41 项", "41", "e003.vote"), "cue": "41 项"}]},
                         {"type": "source_shot", "id": "src", "fact": "e003.nda", "quote": SHOT_Q},
                         {"type": "quote_card", "id": "q", "text": LAB("41 项", "41", "e003.vote"), "count": True},
                         {"type": "tile_row", "id": "t", "photo": "v_x", "items": [{"title": LAB("甲", "A")}, {"title": LAB("乙", "B")}],
                          "cues": {"head": "本周", "photo": "本周"}},
                         {"type": "compare_panel", "id": "p", "head": LAB("对比", "Compare"), "photo": "v_y", "src_tag": LAB("CNBC", "CNBC"),
                          "bars": [{"label": LAB("甲", "A"), "value": 0.3, "val": LAB("1", "1")}, {"label": LAB("乙", "B"), "value": 1, "val": LAB("3", "3")}]},
                         tally()],
                        open_blocks=[{"type": "headline_open", "id": "glance", "items": [{"ch": "vote", "text": LAB("选票", "Vote")}]}])
        w = SB.strip_motion(sb)
        self.assertEqual(len(w), 1)
        s = json.dumps(sb, ensure_ascii=False)
        for k in ('"shot"', '"photo"', '"src_tag"', '"val"', "num_chain", "source_shot", "headline_open", '"count": true'):
            self.assertNotIn(k, s, k)
        t = next(b for b in sb["chapters"][1]["blocks"] if b["type"] == "tally")
        self.assertEqual(t["count"]["value"], 41)            # 计数模板的 count 是数据，不动
        self.assertEqual([b["id"] for b in sb["chapters"][1]["blocks"]], ["days", "nda", "q", "t", "p", "ballot"])

    def test_old_storyboard_untouched(self):
        for day in ("2026-10-31", "2026-11-03", "2026-11-07"):
            p = ROOT / "测试版" / day / "04_文稿/视频v3_分镜.json"
            if not p.exists():
                continue
            sb = json.loads(p.read_text(encoding="utf-8"))
            before = copy.deepcopy(sb)
            self.assertEqual(SB.strip_motion(sb), [], day)
            self.assertEqual(sb, before, day)


class InputsFingerprint(unittest.TestCase):
    def test_empty_new_key_is_not_a_change(self):
        old = {"04_文稿/视频v3_分镜.json": "a", "@step:web": "b"}
        self.assertEqual(runner.diff_inputs(old, dict(old, 新动效="")), [])
        self.assertEqual(runner.diff_inputs(old, dict(old, 新动效="关")), ["新动效"])
        self.assertEqual(runner.diff_inputs(dict(old, 新动效="关"), dict(old, 新动效="")), ["新动效"])
        self.assertEqual(runner.diff_inputs(old, dict(old, **{"05_配音/x.json": ""})), ["x.json"])    # 文件不见了照旧算变了

    def test_video_inputs_follow_switch(self):
        c = mock.Mock()
        with Env(None, None):
            self.assertIn("=新动效=", steps.Video().inputs(c))
        with Env("off", None):
            self.assertIn("=新动效=关", steps.Video().inputs(c))


class FakeCtx:
    def __init__(self, issue, offline=False, rc_shots=0, raise_shots=False, write_summary=True):
        self.issue, self.offline = Path(issue), offline
        self.calls, self.rc_shots, self.raise_shots, self.write_summary = [], rc_shots, raise_shots, write_summary
        self.preview = False
        self.logs = self.issue / "logs"
        self.state = mock.Mock()
        self.state.step.return_value = {"附加": {"视频旁白": "主声音"}}

    def p(self, x):
        return Path(x) if os.path.isabs(str(x)) else self.issue / x

    def py(self, *a):
        return ["py"] + [str(x) for x in a]

    def show(self, cmd):
        return " ".join(str(x) for x in cmd)

    def log_path(self, step):
        return self.logs / "x.log"

    def run(self, step, cmd, label="", timeout=None, env=None):
        self.calls.append(label)
        if label == "原文截图":
            if self.raise_shots:
                raise RuntimeError("截图程序起不来")
            if self.write_summary:
                p = self.issue / steps.SHOT_SUMMARY
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps({"处数": 2, "成功": 1, "退回摘录": 1, "用时秒": 3,
                                         "各处": [{"位置": "「vote」post_card/nda 的 shot", "结果": "用截图"},
                                                {"位置": "「vote」timeline/days 第 2 个日子的 shot", "结果": "退回原句摘录", "原因": "截图没成功：人机验证"}]},
                                        ensure_ascii=False), encoding="utf-8")
            return self.rc_shots, "✗ 超时（240 秒），已停掉" if self.rc_shots == 124 else ""
        if label == "视频导演":                    # 11-08 晚：导演环节（DirectorStep 用）
            return self.director(self) if callable(getattr(self, "director", None)) else (0, "")
        if label == "组装视频":
            d = self.issue / "11_视频v3"
            d.mkdir(parents=True, exist_ok=True)
            (d / "video3_media.json").write_text(json.dumps({"duration": 60, "chapters": [1, 2, 3]}), encoding="utf-8")
            return 0, "  提醒：「vote」timeline/days 第 2 个日子（周四） 的 shot 截图没成功：人机验证，这一处改用原句摘录（放在同一个图位，荧光笔照样扫）\n对齐中位误差 0.05 秒"
        return 0, ""


class VideoStep(unittest.TestCase):
    # 11-08 晚：这一组只测截图和组装，导演环节关掉（导演另有 DirectorStep 一组）
    def setUp(self):
        self._d = mock.patch.dict(os.environ, {"FD_DIRECTOR": "off"})
        self._d.start()

    def tearDown(self):
        self._d.stop()

    def run_step(self, sb, **kw):
        with tempfile.TemporaryDirectory() as d:
            issue = make_issue(d, sb)
            c = FakeCtx(issue, **kw)
            r = steps.Video().run(c, "run")
            return c, r

    def test_shots_then_build(self):
        with Env(None, None):
            c, r = self.run_step(storyboard([timeline(), post()]))
        self.assertEqual(c.calls, ["原文截图", "组装视频"])
        self.assertEqual(r.status, common.DONE)
        self.assertIn("原文截图 2 处：用截图 1、退回摘录 1", r.msg)
        self.assertTrue(any("人机验证" in w for w in r.warns))
        self.assertFalse(any("这一处改用原句摘录" in w for w in r.warns), r.warns)   # 组装程序的同一条提醒不重复列

    def test_timeout_still_builds(self):
        with Env(None, None):
            c, r = self.run_step(storyboard([timeline(), post()]), rc_shots=124, write_summary=False)
        self.assertEqual(c.calls, ["原文截图", "组装视频"])
        self.assertEqual(r.status, common.DONE)
        self.assertTrue(any("没截完" in w and "超时" in w for w in r.warns), r.warns)

    def test_crash_still_builds(self):
        with Env(None, None):
            c, r = self.run_step(storyboard([timeline(), post()]), raise_shots=True)
        self.assertEqual(c.calls, ["原文截图", "组装视频"])
        self.assertEqual(r.status, common.DONE)
        self.assertTrue(any("fd 出错" in w for w in r.warns), r.warns)

    def test_no_shots_when_off_offline_or_none(self):
        with Env("off", None):
            c, r = self.run_step(storyboard([timeline(), post()]))
            self.assertEqual(c.calls, ["组装视频"])
        with Env(None, None):
            c, r = self.run_step(storyboard([timeline(), post()]), offline=True)
            self.assertEqual(c.calls, ["组装视频"])
            self.assertIn("离线没截", r.msg)
            c, r = self.run_step(storyboard([timeline(shot=False), post(shot=False)]))
            self.assertEqual(c.calls, ["组装视频"])

    def test_dry_plan_reads_only(self):
        with tempfile.TemporaryDirectory() as d, Env(None, None):
            issue = Path(d) / "2026-11-09"
            c = FakeCtx(issue)
            line = steps.Video().shots_plan(c)
            self.assertIn("分镜写好以后", line)
            self.assertFalse(issue.exists())                 # --dry-run 不建目录



class DirectorStep(unittest.TestCase):
    """视频导演（11-08 晚加）：开关、退回、换成导演版。导演程序本身不跑（假的 c.run 直接写 结果.json）。"""

    def run_step(self, director=None, env=None, motion=None, **kw):
        with tempfile.TemporaryDirectory() as d:
            issue = make_issue(d, storyboard([timeline(shot=False), post(shot=False)]))
            c = FakeCtx(issue, **kw)
            if director:
                c.director = lambda cc: director(cc, Path(d))
            envs = {} if env is None else {"FD_DIRECTOR": env}
            with Env(motion, None), mock.patch.dict(os.environ, envs):
                if env is None:
                    os.environ.pop("FD_DIRECTOR", None)
                r = steps.Video().run(c, "run")
                inputs = steps.Video().inputs(c)
            v = json.loads((issue / "11_视频v3/video3_media.json").read_text(encoding="utf-8"))
            have = sorted(p.name for p in (issue / "06_配图/视频").glob("*")) if (issue / "06_配图/视频").exists() else []
            keep = (issue / steps.DIRECTOR_DIR / "老路_11_视频v3/video3_media.json").exists()
            return c, r, v, have, keep, inputs

    @staticmethod
    def write_result(c, res):
        p = c.issue / steps.DIRECTOR_DIR / "结果.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")

    def test_off_is_old_path(self):
        c, r, v, have, keep, inputs = self.run_step(env="off")
        self.assertEqual(c.calls, ["组装视频"])
        self.assertEqual(v["duration"], 60)
        self.assertIn("=视频导演=关", inputs)
        self.assertNotIn("导演", r.msg)

    def test_motion_off_skips_director(self):
        c, r, v, have, keep, inputs = self.run_step(motion="off")
        self.assertNotIn("视频导演", c.calls)
        self.assertIn("=视频导演=", inputs)          # 导演开关本身开着：空字符串（不让往期重做）

    def test_fallback_keeps_old(self):
        def director(c, d):
            self.write_result(c, {"状态": "退回", "原因": "导演 第一轮 超时（1200 秒）"})
            return 3, "导演环节退回：导演 第一轮 超时（1200 秒）"
        c, r, v, have, keep, inputs = self.run_step(director)
        self.assertEqual(c.calls, ["组装视频", "视频导演"])
        self.assertEqual(r.status, common.DONE)
        self.assertEqual(v["duration"], 60)
        self.assertIn("导演环节退回", r.msg)
        self.assertTrue(any("导演环节退回" in w and "超时" in w for w in r.warns), r.warns)
        self.assertFalse(keep)

    def test_timeout_and_no_result(self):
        c, r, v, *_ = self.run_step(lambda c, d: (124, "✗ 超时"))
        self.assertTrue(any("导演环节退回" in w and "被停掉" in w for w in r.warns), r.warns)
        self.assertEqual(v["duration"], 60)
        c, r, v, *_ = self.run_step(lambda c, d: (1, "Traceback …\nValueError: x"))
        self.assertTrue(any("没写结果" in w for w in r.warns), r.warns)

    def test_success_swaps_in(self):
        def director(c, d):
            new = d / "渲染/11_视频v3"
            new.mkdir(parents=True)
            (new / "index.html").write_text("<html></html>", encoding="utf-8")
            (new / "video3_media.json").write_text(json.dumps({"duration": 70, "chapters": [1, 2, 3]}), encoding="utf-8")
            img = d / "渲染/06_配图/视频"
            img.mkdir(parents=True)
            (img / "v_new.png").write_bytes(b"png")
            (img / "来源.json").write_text(json.dumps({"v_new": {"kind": "generated", "backend": "codex"}}), encoding="utf-8")
            self.write_result(c, {"状态": "用导演版", "成片目录": str(new), "渲染配图目录": str(img), "新画的图": ["v_new"],
                                  "导演": {"第一轮": {"秒": 500}, "第二轮": {"秒": 450}}})
            return 0, "导演环节完成"
        c, r, v, have, keep, inputs = self.run_step(director)
        self.assertEqual(v["duration"], 70)
        self.assertTrue(keep)                          # 老路那一版挪进导演文件夹留底
        self.assertIn("v_new.png", have)
        self.assertIn("来源.json", have)
        self.assertIn("导演版", r.msg)
        self.assertIn("500＋450", r.msg)

    def test_too_long_falls_back(self):
        def director(c, d):
            new = d / "渲染/11_视频v3"
            new.mkdir(parents=True)
            (new / "index.html").write_text("<html></html>", encoding="utf-8")
            (new / "video3_media.json").write_text(json.dumps({"duration": 200, "chapters": [1]}), encoding="utf-8")
            self.write_result(c, {"状态": "用导演版", "成片目录": str(new)})
            return 0, ""
        c, r, v, *_ = self.run_step(director)
        self.assertEqual(v["duration"], 60)
        self.assertTrue(any("超过 3 分钟" in w for w in r.warns), r.warns)

    def test_narration_switch_and_spend(self):
        """11-09：视频旁白归导演。开关进第 14 步的上游；导演重配旁白花的钱记账（退回现行旁白也记）。"""
        got = []

        class Led:
            def add(self, *a, **k):
                got.append(a)

        def director(c, d):
            c.ledger = Led()
            self.write_result(c, {"状态": "退回", "原因": "第二轮开始前时间预算只剩 100 秒", "旁白": "退回现行旁白：重配视频旁白没成",
                                  "配音": [{"轮": "第一轮"}], "配音花费美元": 0.042, "配音引擎": "gemini"})
            return 3, ""
        c, r, v, have, keep, inputs = self.run_step(director)
        self.assertIn("=导演旁白=", inputs)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][1], "Gemini")
        self.assertAlmostEqual(got[0][2], 0.042)
        self.assertEqual(v["duration"], 60)
        with mock.patch.dict(os.environ, {"FD_DIRECTOR_NARRATION": "off"}):
            c, r, v, have, keep, inputs = self.run_step()
        self.assertIn("=导演旁白=关", inputs)

class CheckMotion(unittest.TestCase):
    def test_warnings(self):
        sb = storyboard([timeline(), post(),
                         {"type": "tile_row", "id": "t", "items": [{"title": LAB("甲", "A")}, {"title": LAB("乙", "B"), "sub": LAB("一句", "x")}]},
                         {"type": "compare_panel", "id": "p", "head": LAB("对比", "Compare"), "bars": []},
                         {"type": "quote_card", "id": "q1", "text": LAB("10 个州", "10", "e003.vote"), "count": True},
                         {"type": "quote_card", "id": "q2", "text": LAB("41 项", "41", "e003.vote"), "count": True},
                         {"type": "quote_card", "id": "q3", "text": LAB("41 项", "41", "e003.vote"), "count": True}],
                        open_blocks=[{"type": "headline_open", "id": "glance", "items": [
                            {"ch": "vote", "image": "card", "text": LAB("一", "1")}, {"ch": "vote", "image": "card", "text": LAB("二", "2")},
                            {"ch": "vote", "text": LAB("三", "3")}]}])
        sb["chapters"][1]["blocks"][0]["ticks"][0].pop("logos")
        w = "\n".join(SB.check_motion(sb))
        for k in ("一章最多一处", "数字滚动", "同一张图", "没写 image", "没挂小图也没挂标志", "只有名字", "白底上的字和数", "没有一张自己的图"):
            self.assertIn(k, w, k)
        self.assertIn("甲", w)
        self.assertNotIn("乙 只有名字", w)

    def test_quiet_when_fine(self):
        sb = storyboard([timeline(), {"type": "quote_card", "id": "q", "text": LAB("41 项", "41", "e003.vote"), "image": "v_vote"}])
        self.assertEqual(SB.check_motion(sb), [])

    def test_tidy_step7_noise(self):
        from orchestrator import helpers as H
        out = "\n".join(["分镜：…",
                         "  提醒：「vote」timeline/days 找不到配图 v_vote，这一块不带图",
                         "  提醒：「vote」去掉模板 image_card/fab：找不到配图 card",
                         "  提醒：「vote」quote_card/q 找不到配图 e0xx，这一块不带图",
                         "  提醒：「vote」tile_row/t 找不到配图 v_tile（photo），这一块照原样、不压在图上",
                         "  提醒：「vote」post_card/nda 的 shot 没有截图记录（06_配图/原文截图/nda.json），这一处改用原句摘录（放在同一个图位，荧光笔照样扫）",
                         "  提醒：别的提醒照旧"])
        t = H.tidy_warnings(out, {"v_vote", "card", "v_tile"})
        self.assertNotIn("找不到配图 v_vote", t)
        self.assertNotIn("找不到配图 card", t)
        self.assertIn("找不到配图 e0xx", t)                    # 不是第 10 步要画的：多半写错了，照旧单列
        self.assertIn("配图 3 张第 10 步才画（v_vote、card、v_tile）", t)
        self.assertIn("原文截图 1 处第 14 步才截", t)
        self.assertIn("别的提醒照旧", t)


def run_helper(*args, env=None):
    e = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    e.update(env or {})
    return subprocess.run([str(PY), "-u", str(HELPERS)] + [str(a) for a in args], capture_output=True, text=True, cwd=str(ROOT),
                          timeout=600, env=e)


class Step7(unittest.TestCase):
    """helpers.py storyboard（第 7 步那一项）在临时期目录上真跑。"""

    def test_bad_quote_is_must_fix_and_switch_off_passes(self):
        bad = timeline()
        bad["ticks"][1]["shot"]["quote"] = "it will not use NDAs"          # 不是事件卡里逐字的一段
        sb = storyboard([tally(), bad])
        with tempfile.TemporaryDirectory() as d:
            issue = make_issue(d, sb)
            r = run_helper("storyboard", "--issue-dir", issue, env={"FD_MOTION": "on"})
            self.assertNotEqual(r.returncode, 0, r.stdout[-800:])
            self.assertIn("核对失败", r.stdout + r.stderr)
            # 第 7 步摘的是末几行带 ✗ 的：要看得出是哪一句原话没核上
            from orchestrator.common import key_lines
            self.assertTrue(any("✗ 要改" in x and "原句不是事件卡" in x for x in key_lines(r.stdout, 6)), r.stdout[-800:])
            r = run_helper("storyboard", "--issue-dir", issue, env={"FD_MOTION": "off"})
            self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-1500:])
            self.assertIn("新动效开关关着", r.stdout)

    def test_good_storyboard_passes_with_summary(self):
        sb = storyboard([tally(), timeline(), post()])
        with tempfile.TemporaryDirectory() as d:
            issue = make_issue(d, sb)
            r = run_helper("storyboard", "--issue-dir", issue, env={"FD_MOTION": "on"})
            self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-1500:])
            self.assertIn("原文截图 2 处第 14 步才截", r.stdout)
            self.assertIn("新动效：原文截图／摘录 2 处", r.stdout)
            self.assertIn("一章最多一处", r.stdout)

    def test_weekend_words_are_reminders(self):          # 周末禁用说法第 7 步只提醒（原来第 7 步不查）
        sb = storyboard([tally(), timeline(), post()])
        sb["edition"] = "sunday_deep"
        sb["chapters"][2]["narration"] = "合起来看，选票先动了，第二层留给周末。"
        with tempfile.TemporaryDirectory() as d:
            issue = make_issue(d, sb)
            r = run_helper("storyboard", "--issue-dir", issue, env={"FD_MOTION": "on"})
            self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-1500:])
            self.assertIn("提醒：周末规则：", r.stdout)
            self.assertIn("story 章 1 章", r.stdout)


def can_browse():
    return shutil.which("node") and PW.exists() and Path("/Applications/Google Chrome.app").exists()


@unittest.skipUnless(can_browse(), "没有 node / Playwright / Chrome")
class ShotsEndToEnd(unittest.TestCase):
    def test_one_ok_one_fallback(self):
        html = """<!doctype html><meta charset="utf-8"><style>body{margin:0;font:20px/1.6 Georgia,serif;background:#fff}
article{width:640px;margin:40px auto}article p{margin:0 0 26px}</style>
<article><p>%s</p><p>Many data center projects have come under scrutiny for relying on NDAs to hide discussions between developers and
local officials, and several towns have asked for more disclosure.</p><p>Short closing paragraph.</p></article>""" % QUOTE
        with tempfile.TemporaryDirectory() as d:
            web = Path(d) / "web"
            web.mkdir()
            (web / "a.html").write_text(html, encoding="utf-8")
            (web / "b.html").write_text("<!doctype html><meta charset='utf-8'><p>Nothing to see here.</p>", encoding="utf-8")

            class Quiet(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *_a):
                    pass
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(web)))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                base = "http://127.0.0.1:%d/" % srv.server_address[1]
                # 原话卡的 shot 指 s1（页面上有这句），时间轴日子的 shot 换成 s2 的那条（页面上没有这句 → 找不到原句）
                cds = cards(base + "a.html", base + "b.html")
                tl = timeline()
                tl["ticks"][1]["shot"] = {"fact": "e003.vote", "quote": "Out of 41 local ballot measures across 10 states",
                                          "cues": {"mark": "10 个州的 41 项"}}
                sb = storyboard([tl, post()])
                issue = make_issue(d, sb, cds)
                t0 = time.time()
                r = run_helper("shots", "--issue-dir", issue, "--total", "90", env={"FD_MOTION": "on", "PLAYWRIGHT": str(PW)})
                self.assertLess(time.time() - t0, 200)
            finally:
                srv.shutdown()
                srv.server_close()
            self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-1500:])
            res = json.loads((issue / steps.SHOT_SUMMARY).read_text(encoding="utf-8"))
            self.assertEqual(res["处数"], 2, res)
            self.assertEqual(res["成功"], 1, res)
            self.assertEqual(res["退回摘录"], 1, res)
            ok = next(x for x in res["各处"] if x["结果"] == "用截图")
            self.assertIn("post_card/nda", ok["位置"])
            self.assertTrue((issue / "06_配图/原文截图/nda.png").is_file())
            # 再跑一次：截成的不重截（记录的截图时间不变）
            rec0 = json.loads((issue / "06_配图/原文截图/nda.json").read_text(encoding="utf-8"))["shot_at"]
            r2 = run_helper("shots", "--issue-dir", issue, "--total", "30", env={"FD_MOTION": "on"})
            self.assertEqual(r2.returncode, 0)
            self.assertIn("已有", r2.stdout)
            self.assertEqual(json.loads((issue / "06_配图/原文截图/nda.json").read_text(encoding="utf-8"))["shot_at"], rec0)

    def test_off_writes_summary_only(self):
        with tempfile.TemporaryDirectory() as d:
            issue = make_issue(d, storyboard([timeline(), post()]))
            r = run_helper("shots", "--issue-dir", issue, env={"FD_MOTION": "off"})
            self.assertEqual(r.returncode, 0)
            self.assertIn("不截图", r.stdout)
            res = json.loads((issue / steps.SHOT_SUMMARY).read_text(encoding="utf-8"))
            self.assertTrue(res["开关"].startswith("关"))
            self.assertFalse(list((issue / "06_配图/原文截图").glob("*.png")))


if __name__ == "__main__":
    unittest.main(verbosity=1)
