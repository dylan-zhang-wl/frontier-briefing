#!/usr/bin/env python3
"""调度报告花费那一行"到 90% 了"后面那句（2026-11-28 改）。

原来只要月度 Gemini 过了 90% 就写"配音已改走 MiMo 备用"：11-25 那期是用 Gemini 配完才过 90%（第 11 步"播客：主声音；
视频旁白：主声音"），11-28 周六只跑到第 3 步、没有配音，也都写了这句。现在按这一期实际用的声音写：
  · 整期改走备用（第 11 步 决定.用备用），或用到的几路都是备用 → "配音已改走 MiMo 备用"（和原来一字不差）；
  · 只一路是备用（主声音出错换的、或第 14 步自己改走的）→ 写清是哪一路，从下一期起整期改走；
  · 都是主声音（记录里确有一路写着主声音）→ "这一期配音用的是主声音（Gemini），从下一期起改走 MiMo 备用"；
  · 这一期没跑配音（没有第 11 步的记录），或查不出用的是哪个声音 → 不写；
  · 没到 90% → 什么都不加（和原来一样）。
用法（在项目根运行）：~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_fd_report_over90.py
不调用任何模型、不花钱；只在临时目录读写。往期 测试版/ 一个字不碰。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

from orchestrator import report, steps  # noqa: E402

HUMAN = "05_配音/播客_v3"
USED = "——**到 90% 了，配音已改走 MiMo 备用**"
NEXT = "——**到 90% 了：这一期配音用的是主声音（Gemini），从下一期起改走 MiMo 备用**"


class FakeState:
    def __init__(self, rec):
        self.rec = rec

    def step(self, key):
        return self.rec.get(key)


def gemini_voice():
    return {"状态": steps.DONE, "说明": "播客：主声音；视频旁白：主声音",
            "附加": {"决定": {"用备用": False, "原因": ""}, "播客": "主声音", "视频旁白": "主声音", "视频引擎": "gemini"}}


def backup_voice():
    why = "本月 Gemini 已记 $7.25，到上限 $8.00 的 91%"
    return {"状态": steps.DONE, "说明": "播客：MiMo 备用；视频旁白：MiMo 备用",
            "附加": {"决定": {"用备用": True, "原因": why}, "播客": "MiMo 备用", "视频旁白": "MiMo 备用", "视频引擎": "mimo"}}


class Over90(unittest.TestCase):
    def ctx(self, d, rec, over=True, usage=None):
        issue = Path(d) / "2026-11-25"
        (issue / HUMAN).mkdir(parents=True, exist_ok=True)
        if usage is not None:
            (issue / HUMAN / "usage.json").write_text(json.dumps(usage), encoding="utf-8")
        c = mock.Mock(day=issue.name, issue=issue, default_issue=True, ed={"名字": "工作日版", "人声": HUMAN}, offline=False)
        c.state = FakeState(rec)
        c.p = lambda x: issue / x
        c.again.return_value = "./fd run"
        c.ledger.status.return_value = ({"Gemini已记美元": 7.25, "上限美元": 8.0, "比例": 0.906, "到90%": True} if over else
                                        {"Gemini已记美元": 1.0, "上限美元": 8.0, "比例": 0.125, "到90%": False})
        c.ledger.issue_total.return_value = 0.465
        c.ledger.month_total.return_value = 7.25
        c.ledger.issue_data.return_value = {}
        c.ledger.month_file = issue / "账本.json"
        return c

    def money_line(self, c, last=17):
        text = report.write(c, {"停在": None, "原因": ""}, 1, last).read_text(encoding="utf-8")
        return next(x for x in text.splitlines() if x.startswith("- 花费："))

    def note(self, d, rec, **kw):
        c = self.ctx(d, rec, **kw)
        return report.over90_note(c, {s.key: (c.state.step(s.key) or {}) for s in steps.STEPS})

    def test_1125_gemini_then_over90(self):
        """11-25：用 Gemini 配完才过 90% → 不再说"已改走"，说从下一期起。"""
        with tempfile.TemporaryDirectory() as d:
            line = self.money_line(self.ctx(d, {"voice": gemini_voice()}))
        self.assertTrue(line.endswith(NEXT), line)
        self.assertNotIn("已改走", line)

    def test_backup_used(self):
        with tempfile.TemporaryDirectory() as d:
            line = self.money_line(self.ctx(d, {"voice": backup_voice()}))
        self.assertTrue(line.endswith(USED), line)

    def test_1128_no_voice_step(self):
        """11-28 周六：只跑到第 3 步，没有第 11 步的记录 → 这句不写。"""
        with tempfile.TemporaryDirectory() as d:
            rec = {k: {"状态": steps.DONE, "说明": "x"} for k in ("fetch", "dedupe", "ingest")}
            line = self.money_line(self.ctx(d, rec), last=3)
        self.assertNotIn("90%", line.split("）", 1)[1] if "）" in line else line)
        self.assertNotIn("MiMo", line)
        self.assertTrue(line.endswith("（91%）"), line)

    def test_under90_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            line = self.money_line(self.ctx(d, {"voice": backup_voice()}, over=False))
        self.assertTrue(line.endswith("（12%）"), line)

    def test_partial_backup_names_track(self):
        """主声音出错、只视频旁白换了备用 → 写清是哪一路。"""
        v = gemini_voice()
        v["附加"].update({"视频旁白": "MiMo 备用", "视频引擎": "mimo"})
        with tempfile.TemporaryDirectory() as d:
            n = self.note(d, {"voice": v})
        self.assertEqual(n, "——**到 90% 了：这一期视频旁白用的是 MiMo 备用，从下一期起配音整期改走 MiMo 备用**")

    def test_step14_own_switch_counts(self):
        """第 14 步自己改走备用（附加.视频引擎）也算这一期视频旁白用了备用。"""
        with tempfile.TemporaryDirectory() as d:
            n = self.note(d, {"voice": gemini_voice(),
                              "video": {"状态": steps.DONE, "附加": {"视频引擎": {"引擎": "mimo", "原因": "命令行要求用备用（--use-backup）"}}}})
        self.assertIn("这一期视频旁白用的是 MiMo 备用", n)

    def test_adopted_podcast_reads_usage(self):
        """第 11 步采纳已有产出（"沿用已有"）：播客用的声音按配音程序自己的 usage.json 看。"""
        v = {"状态": steps.DONE, "附加": {"播客": "沿用已有", "视频旁白": "沿用已有", "视频引擎": "mimo"}}
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.note(d, {"voice": v}, usage={"引擎": "MiMo 复刻"}), USED)
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("这一期视频旁白用的是 MiMo 备用", self.note(d, {"voice": v}, usage={"引擎": "gemini"}))

    def test_no_evidence_writes_nothing(self):
        """查不出这一期用的是哪个声音：不写"用的是主声音"。"""
        cases = [{"状态": steps.FAILED},                                                     # 第 11 步失败、没留附加
                 {"状态": steps.FAILED, "附加": {"决定": {"用备用": False}, "播客": "没配成", "视频旁白": "没配成"}},
                 {"状态": steps.DONE, "附加": {"播客": "沿用已有", "视频旁白": "沿用已有", "视频引擎": "gemini"}}]  # 没有 usage.json
        for v in cases:
            with tempfile.TemporaryDirectory() as d:
                self.assertEqual(self.note(d, {"voice": v}), "", v)
        with tempfile.TemporaryDirectory() as d:          # 沿用已有、usage.json 写着 Gemini：算确有主声音
            v = {"状态": steps.DONE, "附加": {"播客": "沿用已有", "视频旁白": "沿用已有", "视频引擎": "gemini"}}
            self.assertEqual(self.note(d, {"voice": v}, usage={"引擎": "gemini-2.5-flash-tts"}), NEXT)

    def test_video_off_podcast_backup_is_whole(self):
        v = {"状态": steps.DONE, "附加": {"决定": {"用备用": False}, "播客": "MiMo 备用", "视频旁白": "不配（视频：关）", "视频开关": "关"}}
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.note(d, {"voice": v}), USED)


if __name__ == "__main__":
    unittest.main()
