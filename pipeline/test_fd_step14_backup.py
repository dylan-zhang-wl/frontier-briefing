#!/usr/bin/env python3
"""第 14 步重配视频旁白时改不改走 MiMo 备用（2026-11-28，经验库第 100 件）。

11-22 云端测试（运行 45023502009，gemini=off，带 --use-backup --budget-usd 0）从第 14 步接着跑：第 11 步的记录来自
那天早上用 Gemini 的正式运行（"视频引擎": "gemini"），文件包里又没有视频旁白的人声，第 14 步组装时要重配，
预算 $0、引擎 Gemini，报 BudgetExceeded。原因是 Video.engine() 只看第 11 步的记录，不看命令行 --use-backup。

查这几件事：
  · 命令行 --use-backup、第 11 步记的是 Gemini：组装、导演重配旁白都带 --engine mimo，旁白预算 0；
  · 什么都没要求、第 11 步用 Gemini 配好了旁白：组装命令和改以前一字不差（正式运行不变）；
  · 11-25 那种：第 11 步用 Gemini，月度已经过 90%：第 14 步照旧用 Gemini，不半路换声音；
  · 第 11 步记"做完"、视频旁白人声却不在、不离线：改走备用；离线、或第 11 步还没做（--dry-run 计划）时照旧；
  · 第 14 步自己改走备用时，附加记"视频引擎"和原因、提醒一行；第 11 步本来就是备用、或用主声音时不多记。
用法（在项目根运行）：~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_fd_step14_backup.py
不调用任何模型、不花钱；只在临时目录读写，跑子程序的地方都换成假的。
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

from orchestrator import common, steps  # noqa: E402
from test_fd_video_off_10to17 import Env, FakeCtx, FakeLedger, FakeState, make_issue  # noqa: E402

VV = common.VIDEO_VOICE


def voice_rec(engine="gemini", status=common.DONE):
    return {"voice": {"状态": status, "附加": {"播客": "主声音", "视频旁白": "主声音" if engine == "gemini" else "MiMo 备用",
                                              "视频引擎": engine}}}


def put_voice(issue, engine="gemini"):
    d = Path(issue) / VV
    (d / "chapters").mkdir(parents=True, exist_ok=True)
    (d / "voice.json").write_text(json.dumps({"engine": engine}), encoding="utf-8")
    (d / "chapters" / "01.wav").write_bytes(b"RIFF")


class Ledger90(FakeLedger):
    def status(self):
        return {"上限美元": 8.0, "Gemini已记美元": 7.3, "到90%": True, "比例": 0.9125}


class Step14Engine(unittest.TestCase):
    def ctx(self, d, engine="gemini", status=common.DONE, voice=True, force=False, offline=False, ledger=None):
        issue = make_issue(d)
        if voice:
            put_voice(issue, engine)
        c = FakeCtx(issue, state=FakeState(voice_rec(engine, status)), offline=offline)
        c.force_backup = force
        if ledger is not None:
            c.ledger = ledger
        return c

    def base_cmd(self, c):
        return ["py", str(common.TOOLS / "video3_build.py"), str(c.issue), "--no-gen", "--budget-usd", "0"]

    def test_use_backup_overrides_gemini_record(self):
        """11-22 那次：--use-backup，第 11 步记 Gemini，旁白人声不在 → 组装和导演都用 MiMo。"""
        with tempfile.TemporaryDirectory() as d, Env():
            c = self.ctx(d, voice=False, force=True)
            v = steps.Video()
            self.assertEqual(v.engine_why(c), ("mimo", "命令行要求用备用（--use-backup）"))
            self.assertEqual(v.command(c), self.base_cmd(c) + ["--engine", "mimo"])
            self.assertEqual(v.narration_budget(c), (0.0, "mimo"))
            dc = [str(x) for x in v.director_cmd(c)]
            self.assertEqual(dc[dc.index("--engine") + 1], "mimo")
            self.assertEqual(dc[dc.index("--voice-budget") + 1], "0.000")

    def test_use_backup_with_voice_present(self):
        with tempfile.TemporaryDirectory() as d, Env():
            c = self.ctx(d, force=True)
            self.assertEqual(steps.Video().command(c), self.base_cmd(c) + ["--engine", "mimo"])

    def test_formal_gemini_unchanged(self):
        """正式运行：第 11 步用 Gemini 配好了旁白、没要求备用 → 和改以前一字不差。"""
        with tempfile.TemporaryDirectory() as d, Env():
            c = self.ctx(d)
            v = steps.Video()
            self.assertEqual(v.engine_why(c), ("gemini", ""))
            self.assertEqual(v.command(c), self.base_cmd(c))
            self.assertEqual(v.narration_budget(c), (0.1, "gemini"))
            self.assertEqual(v.director_budget(c), steps.DIRECTOR_BUDGET)

    def test_month_past_90_does_not_switch_midissue(self):
        """11-25 那种：第 11 步用 Gemini 配完，月度才过 90% → 第 14 步不半路换成备用。"""
        with tempfile.TemporaryDirectory() as d, Env():
            c = self.ctx(d, ledger=Ledger90())
            self.assertEqual(steps.Video().engine(c), "gemini")
            self.assertEqual(steps.Video().command(c), self.base_cmd(c))

    def test_step11_mimo_kept(self):
        with tempfile.TemporaryDirectory() as d, Env():
            c = self.ctx(d, engine="mimo")
            self.assertEqual(steps.Video().engine_why(c), ("mimo", "第 11 步视频旁白用的是 MiMo 备用"))

    def test_missing_voice_after_step11_done(self):
        """第 11 步记"做完"、旁白人声却不在（接着跑的文件包里没有）、不离线 → 备用；离线 → 照旧 Gemini。"""
        with tempfile.TemporaryDirectory() as d, Env():
            c = self.ctx(d, voice=False)
            eng, why = steps.Video().engine_why(c)
            self.assertEqual(eng, "mimo")
            self.assertIn("没有视频旁白的人声", why)
        with tempfile.TemporaryDirectory() as d, Env():
            c = self.ctx(d, voice=False, offline=True)
            self.assertEqual(steps.Video().engine(c), "gemini")

    def test_voice_json_without_wavs_counts_as_missing(self):
        with tempfile.TemporaryDirectory() as d, Env():
            c = self.ctx(d)
            (c.issue / VV / "chapters" / "01.wav").unlink()
            self.assertEqual(steps.Video().engine(c), "mimo")

    def test_dry_run_before_step11_unchanged(self):
        """第 11 步还没做（--dry-run 看计划）：不因为还没有人声就写成备用。"""
        with tempfile.TemporaryDirectory() as d, Env():
            c = self.ctx(d, voice=False, status=common.TODO)
            self.assertEqual(steps.Video().command(c), self.base_cmd(c))
        with tempfile.TemporaryDirectory() as d, Env():
            issue = make_issue(d)
            c = FakeCtx(issue)              # 状态里根本没有第 11 步
            self.assertEqual(steps.Video().command(c), self.base_cmd(c))

    def run14(self, c):
        with mock.patch.object(steps.Video, "shots", lambda self, c: ("", [], {})), \
                mock.patch.object(steps.Video, "director", lambda self, c: ("", [], {})), \
                mock.patch.object(steps.Video, "overlap", lambda self, c: ("", [], {})):
            return steps.Video().run(c, "run")

    def test_run_records_own_switch(self):
        with tempfile.TemporaryDirectory() as d, Env():
            c = self.ctx(d, voice=False, force=True)
            r = self.run14(c)
            self.assertEqual(r.status, common.DONE)
            self.assertEqual(r.extra.get("视频引擎"), {"引擎": "mimo", "原因": "命令行要求用备用（--use-backup）"})
            self.assertTrue(any("MiMo 备用" in w for w in r.warns))
            self.assertIn("--engine", dict(c.cmds)["组装视频"])

    def test_run_records_nothing_extra_normally(self):
        for engine in ("gemini", "mimo"):
            with tempfile.TemporaryDirectory() as d, Env():
                c = self.ctx(d, engine=engine)
                r = self.run14(c)
                self.assertEqual(r.status, common.DONE)
                self.assertNotIn("视频引擎", r.extra)
                self.assertFalse(any("MiMo 备用" in w for w in r.warns))


if __name__ == "__main__":
    unittest.main()
