#!/usr/bin/env python3
"""自检.md 末尾补"第 10–17 步实际结果"（pipeline/orchestrator/selfcheck.py，fd 第 17 步调用）的测试（2026-11-09 加）。

查：这一节写在末尾、再跑一次整节换掉（不越补越长、上面第 9 步写的原样留着）；自检.md 不在就不写；
声音、配图张数和来源、导演版还是老路（旁白谁写的）、花费、验收都从 fd 的步骤记录和文件里取（例子照 11-09 正式运行的记录）；
第 17 步 Report.selfcheck 出错只记提醒、不抛错。
用法（在项目根运行）：~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_selfcheck.py
不调用任何模型、不花钱；读写只在临时目录。
"""
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
from orchestrator import selfcheck as SC, steps  # noqa: E402

TOP = "# 自检\n- 这一期第 1–9 步都做完了；没配音、没花钱。\n- 第 10–17 步这次没跑。\n"
STEPS_1109 = {
    "images": {"状态": "做完", "说明": "网页 8 张、视频 5 张都在"},
    "voice": {"状态": "做完", "说明": "播客：主声音；视频旁白：主声音",
              "附加": {"播客": "主声音", "视频旁白": "主声音", "视频引擎": "gemini"}},
    "mix": {"状态": "做完", "说明": "-16.0 LUFS"}, "web": {"状态": "做完", "说明": "网页"},
    "video": {"状态": "做完", "说明": "141.6 秒，7 章；导演版",
              "附加": {"视频导演": {"结果": "用导演版", "用时分钟": 23.0, "新画的图": ["v_cover", "v_memo"]}}},
    "web2": {"状态": "做完", "说明": "网页带视频"},
    "accept": {"状态": "做完", "说明": "三种视图无报错、不横滚、不缺字", "提醒": []},
}


def issue_dir():
    d = Path(tempfile.mkdtemp())
    (d / "06_配图" / "视频").mkdir(parents=True)
    for n in ("card", "e001"):
        (d / "06_配图" / (n + ".png")).write_bytes(b"x")
        (d / "06_配图" / ("log_%s.png.txt" % n)).write_text("codex", encoding="utf-8")
    for n in ("v_board", "v_cover", "wiki1"):
        (d / "06_配图" / "视频" / (n + ".png")).write_bytes(b"x")
    (d / "06_配图" / "视频" / "来源.json").write_text(json.dumps({
        "v_board": {"kind": "generated", "backend": "codex"}, "v_cover": {"kind": "generated", "backend": "codex"},
        "wiki1": {"kind": "commons"}}), encoding="utf-8")
    (d / "花费.json").write_text(json.dumps({"条目": [{"服务": "Gemini", "美元": 0.201}, {"服务": "Gemini", "美元": 0.0553},
                                                   {"服务": "MiMo", "美元": 0.0}]}), encoding="utf-8")
    return d


class Build(unittest.TestCase):
    def test_1109_like(self):
        d = issue_dir()
        sec = SC.build(d, STEPS_1109, SC.costs_of(d / "花费.json"), {"Gemini已记美元": 2.08, "上限美元": 8.0},
                       SC.images_summary(d, ["card", "e001", "e016"], ["v_board"]), "2026-11-09T12:00:00Z")
        self.assertTrue(sec.startswith(SC.HEAD))
        self.assertIn("| 11 | 配音 | 做完 | 播客：主声音；视频旁白：主声音 |", sec)
        self.assertIn("| 17 | 写本期报告 | 没跑 |", sec)               # 没给第 17 步的记录就写"没跑"
        self.assertIn("声音：播客 主声音，视频旁白 主声音（第 11 步引擎 gemini）", sec)
        self.assertIn("网页图：要 3 张，有 2 张（Codex 画的 2 张", sec)
        self.assertIn("缺 e016，网页上用程序画的主题色封面", sec)
        self.assertIn("06_配图/视频/ 里共 3 张（Codex 2 张、维基共享资源 1 张）", sec)
        self.assertIn("视频：导演版（导演环节 23.0 分钟，新画 2 张：v_cover、v_memo）", sec)
        self.assertIn("花费：这一期 Gemini $0.2563（花费.json）；本月 Gemini 已记 $2.08 / 上限 $8.00", sec)
        self.assertIn("验收：做完，三种视图无报错", sec)

    def test_fallback_and_narration(self):
        st = dict(STEPS_1109, video={"状态": "做完", "说明": "老路", "附加": {"视频导演": {
            "结果": "退回", "原因": "超过 50 分钟被停掉", "旁白": "退回现行旁白（检查没过）",
            "导演旁白配音": {"美元": 0.012, "引擎": "gemini", "次数": 3}}}})
        sec = SC.build(Path("/无"), st, {}, {}, [], "t")
        self.assertIn("视频：老路那一版（导演环节退回：超过 50 分钟被停掉）", sec)
        self.assertIn("视频旁白最后用的是：退回现行旁白（检查没过）（导演旁白重配 3 次，gemini $0.0120）", sec)
        self.assertIn("花费：这一期 没有花钱（花费.json）", sec)

    def test_no_video_step(self):
        st = {k: v for k, v in STEPS_1109.items() if k != "video"}
        self.assertIn("- 视频：第 14 步没跑", SC.build(Path("/无"), st, {}, {}, [], "t"))

    def test_director_not_done_string(self):
        """11-21：导演没做时第 14 步记的"视频导演"是一句话（字符串），以前这里当 dict 用、这一节写不出来。"""
        st = dict(STEPS_1109, video={"状态": "做完", "说明": "60.0 秒，3 章", "附加": {
            "视频导演": "不做（视频导演开关关着（环境变量 FD_DIRECTOR=off））"}})
        sec = SC.build(Path("/无"), st, {}, {}, [], "t")
        self.assertIn("- 视频：老路那一版（导演环节没做：视频导演开关关着（环境变量 FD_DIRECTOR=off））", sec)
        self.assertIn("- 声音：播客 主声音，视频旁白 主声音（第 11 步引擎 gemini）\n", sec)     # 没有"旁白最后用的是"
        st = dict(STEPS_1109, video={"状态": "做完", "说明": "60.0 秒，3 章", "附加": {}})       # 没记"视频导演"：照旧
        self.assertIn("- 视频：老路那一版（导演环节没做）\n", SC.build(Path("/无"), st, {}, {}, [], "t"))


class Write(unittest.TestCase):
    def test_append_then_replace(self):
        d = Path(tempfile.mkdtemp())
        p = d / "自检.md"
        p.write_text(TOP, encoding="utf-8")
        self.assertTrue(SC.write(p, SC.HEAD + "\n\n第一次\n"))
        self.assertTrue(SC.write(p, SC.HEAD + "\n\n第二次\n"))
        s = p.read_text(encoding="utf-8")
        self.assertTrue(s.startswith(TOP))                         # 第 9 步写的原样留着
        self.assertEqual(s.count(SC.HEAD), 1)
        self.assertNotIn("第一次", s)
        self.assertTrue(s.endswith("第二次\n"))

    def test_missing_file_not_created(self):
        p = Path(tempfile.mkdtemp()) / "自检.md"
        self.assertFalse(SC.write(p, "x"))
        self.assertFalse(p.exists())


class ReportStep(unittest.TestCase):
    def fake_c(self, d, broken=False):
        led = SimpleNamespace(issue_file=d / "花费.json",
                              status=(lambda: 1 / 0) if broken else (lambda: {"Gemini已记美元": 1.0, "上限美元": 8.0}))
        return SimpleNamespace(issue=d, p=lambda x: d / x, state=SimpleNamespace(data={"步骤": dict(STEPS_1109)}),
                               ledger=led, steps={"images": SimpleNamespace(wanted=lambda c: (["card"], ["v_board"]))})

    def test_report_writes_section(self):
        d = issue_dir()
        (d / "自检.md").write_text(TOP, encoding="utf-8")
        self.assertEqual(steps.Report().selfcheck(self.fake_c(d)), [])
        s = (d / "自检.md").read_text(encoding="utf-8")
        self.assertIn("| 17 | 写本期报告 | 做完 | 报告 00_调度报告.md（这一次） |", s)
        self.assertIn("本月 Gemini 已记 $1.00 / 上限 $8.00", s)

    def test_report_director_not_done(self):
        """11-21：导演"不做"（字符串）时第 17 步照常补这一节，不是只记一条"没补上"的提醒。"""
        d = issue_dir()
        (d / "自检.md").write_text(TOP, encoding="utf-8")
        c = self.fake_c(d)
        c.state.data["步骤"]["video"] = {"状态": "做完", "说明": "60.0 秒，3 章", "附加": {
            "视频导演": "不做（新动效开关关着（环境变量 FD_MOTION=off），导演环节不做）"}}
        self.assertEqual(steps.Report().selfcheck(c), [])
        s = (d / "自检.md").read_text(encoding="utf-8")
        self.assertIn("- 视频：老路那一版（导演环节没做：新动效开关关着（环境变量 FD_MOTION=off），导演环节不做）", s)

    def test_report_never_raises(self):
        d = issue_dir()
        (d / "自检.md").write_text(TOP, encoding="utf-8")
        self.assertEqual(steps.Report().selfcheck(self.fake_c(d, broken=True)), [])     # 账本坏了：不写本月那半句
        c = self.fake_c(d)
        c.steps = {}                                                                      # 更糟的情况：只记一条提醒
        c.state = None
        w = steps.Report().selfcheck(c)
        self.assertEqual(len(w), 1)
        self.assertIn("自检.md 末尾没补上", w[0])


# 2026-11-21（11-16、11-17、11-18 审片清单第 6 项）："听这一段"不再一律写"正常"
LISTEN_OUT = '听这一段按钮数： 14\n[{"button": "听 13 分钟", "audio": [{"t": 2, "paused": false}]}, ' \
             '{"button": "听这一段0:45", "audio": [{"t": 47.6, "paused": false}]}]'
WEB_WARN_1116 = ["注意：“听这一段” E002 跳到 0:45（热点一），但整集里最像它的话在“热点二” 3:20；请核对",
                 "注意：“听这一段” E004 跳到 3:20（热点二），但整集里最像它的话在“热点三” 5:24；请核对",
                 "注意：“听这一段” E001 跳到 5:14（热点三），但整集里最像它的话在“热点一” 2:50；请核对",
                 "注意：别的提醒，不算"]


class ListenSaid(unittest.TestCase):
    def test_no_podcast(self):
        self.assertEqual(steps.listen_said({"听这一段": "没有播客，跳过"}, "按钮数：0"), "'听这一段'：没有播客，不查")

    def test_only_two_clicked(self):            # 转写核对没跑（旧状态、没有这一栏）：只说点了前几个
        s = steps.listen_said({"听这一段": [{}, {}]}, LISTEN_OUT)
        self.assertEqual(s, "'听这一段'点了前 2 个能从对的时间放（共 14 个）")
        self.assertNotIn("正常", s)

    def test_late_and_early(self):              # 11-17 那样：4 条跳晚
        res = {"听这一段": [{}, {}], "听这一段转写核对": {"E016": "对", "E178": "对", "E013": "对", "E051": "对", "E050": "对", "E006": "跳早了"},
               "听这一段可能跳晚": ["E016", "E178", "E013", "E051"], "听这一段可能跳早": ["E006"]}
        s = steps.listen_said(res, LISTEN_OUT)
        self.assertIn("转写核对 6 条：可能跳晚 4 条（E016、E178、E013、E051），可能跳早 1 条（E006），请耳听", s)

    def test_clean_and_not_run(self):
        self.assertIn("转写核对 3 条没听出跳早、跳晚", steps.listen_said({"听这一段": [{}], "听这一段转写核对": {"a": "对", "b": "对", "c": "对"}}, ""))
        self.assertTrue(steps.listen_said({"听这一段": [{}], "听这一段转写核对": "没跑成"}, "").endswith("；转写核对没跑成"))
        self.assertIn("转写核对跳过（没有人声版）", steps.listen_said({"听这一段": [{}], "听这一段转写核对": "没有人声版"}, ""))

    def test_selfcheck_takes_real_accept_msg(self):     # 自检.md 那一节照验收的话写，不会再出现"正常"
        res = {"听这一段": [{}, {}], "听这一段转写核对": {"E016": "对"}, "听这一段可能跳晚": ["E016"]}
        st = dict(STEPS_1109, accept={"状态": "做完", "说明": "三种视图无报错、不横滚、不缺字；上标不掉行；" + steps.listen_said(res, LISTEN_OUT),
                                      "提醒": ["'听这一段' E016 可能跳晚了：……"]})
        sec = SC.build(Path("/无"), st, {}, {}, [], "t")
        self.assertIn("可能跳晚 1 条（E016）", sec)
        self.assertNotIn("'听这一段'正常", sec)
        self.assertIn("；提醒 1 条（见 00_调度报告.md 第 16 步）", sec)


class ListenLine(unittest.TestCase):
    def test_web2_warnings_1116(self):          # 11-16：第 15 步报了三条头条串位的"请核对"，自检要带上
        st = dict(STEPS_1109, web2={"状态": "做完", "说明": "网页带视频", "提醒": WEB_WARN_1116})
        sec = SC.build(Path("/无"), st, {}, {}, [], "t")
        self.assertIn("- '听这一段'：第 15 步组装网页时报了 3 条请核对（E002、E004、E001），验收没逐条核，见 00_调度报告.md 第 15 步", sec)

    def test_falls_back_to_step13_and_silent_when_none(self):
        st = {k: v for k, v in dict(STEPS_1109, web={"状态": "做完", "说明": "网页", "提醒": WEB_WARN_1116[:1]}).items() if k != "web2"}
        self.assertIn("第 13 步组装网页时报了 1 条请核对（E002）", SC.listen_line(st))
        st2 = dict(st, web2={"状态": "做完", "说明": "网页带视频", "提醒": []})      # 最后那一步没报：不写
        self.assertEqual(SC.listen_line(st2), "")
        self.assertNotIn("'听这一段'：", SC.build(Path("/无"), STEPS_1109, {}, {}, [], "t"))


class AcceptListen(unittest.TestCase):
    """第 16 步真走一遍（假的命令输出）：转写核对报了跳晚，验收那句话、验收.json 都照实写。"""

    def test_accept_msg_follows_listen_text(self):
        import os
        from unittest import mock
        from orchestrator import common
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "2026-11-17"
            (d / "10_网页v3").mkdir(parents=True)
            (d / "logs").mkdir()
            (d / "10_网页v3" / "index.html").write_text("<html></html>", encoding="utf-8")
            (d / "10_网页v3" / "自检报告.json").write_text(json.dumps({"首屏": {"errors": [], "overflowX": 0, "totalKB": 900}}), encoding="utf-8")
            jt = {"窗口秒": 20, "各条": {"E016": {"判断": "对", "跳晚": True, "跳点秒": 418.3, "跳点前在讲这一条（秒）": 14, "这一条约从（跳点前几秒）": 19},
                                       "E050": {"判断": "对"}}}

            def run(step, cmd, label="", timeout=None, env=None):
                if label == "听这一段转写核对":
                    (d / "logs" / "听这一段_转写核对.json").write_text(json.dumps(jt, ensure_ascii=False), encoding="utf-8")
                    return 0, ""
                return 0, {"截图自检": "", "上标": '390 {"lonely": []}', "听这一段": LISTEN_OUT}[label]
            c = SimpleNamespace(issue=d, p=lambda x: d / x, env={}, run=run, py=lambda *a: ["py"] + [str(x) for x in a],
                                state=SimpleNamespace(step=lambda k: {"附加": {"播客": "带音效"}} if k == "web" else None))
            with mock.patch.object(common, "SWITCH_FILE", Path(t) / "没有.json"), mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("FD_VIDEO", None)
                r = steps.Accept().run(c, "run")
            res = json.loads((d / "logs" / "验收.json").read_text(encoding="utf-8"))
        self.assertEqual(r.status, steps.DONE)
        self.assertEqual(r.msg, "三种视图无报错、不横滚、不缺字；上标不掉行；'听这一段'点了前 2 个能从对的时间放（共 14 个）；"
                                "转写核对 2 条：可能跳晚 1 条（E016），请耳听")
        self.assertEqual(res["听这一段可能跳晚"], ["E016"])
        self.assertEqual(res["听这一段可能跳早"], [])
        self.assertTrue(any("E016 可能跳晚了" in w for w in r.warns))


if __name__ == "__main__":
    unittest.main()
