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


if __name__ == "__main__":
    unittest.main()
