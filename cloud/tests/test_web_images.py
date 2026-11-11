#!/usr/bin/env python3
"""cloud/web_images.py 的测试（2026-11-11 加）：--max 只画前几张，其余不画（退回程序封面）。只用 --dry-run，不调 Codex、不联网、不花钱。

用法（在项目根运行）：python3 -m unittest discover -s cloud/tests -v
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import web_images as W  # noqa: E402

WEB = {"page": {"images": {"card": {"brief_en": "a server hall"}, "E001": {"brief_en": "a wafer"}, "e002": {"brief_en": "a lab bench"},
                           "term": {"brief_en": "a cable tray"}}},
       "sections": [{"kind": "headline", "items": [{"id": "E001"}]}, {"kind": "brief", "items": [{"id": "e002"}]}, {"kind": "term"}]}


class MaxTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.issue = Path(self.td.name) / "2026-11-20"
        (self.issue / "04_文稿").mkdir(parents=True)
        (self.issue / "04_文稿" / "claude_网页.json").write_text(json.dumps(WEB), encoding="utf-8")

    def tearDown(self):
        self.td.cleanup()

    def run_main(self, *extra):
        with redirect_stdout(io.StringIO()) as out:
            rc = W.main([str(self.issue), "--dry-run", *extra])
        return rc, out.getvalue()

    def test_without_max_lists_all(self):
        rc, out = self.run_main()
        self.assertEqual(rc, 0)
        self.assertIn("这次画 4 张", out)
        self.assertNotIn("--max", out)

    def test_max_1_only_first(self):
        rc, out = self.run_main("--max", "1")
        self.assertEqual(rc, 0)
        self.assertIn("这次画 1 张", out)
        self.assertIn("这次不画 e001、e002、term，退回程序封面", out)
        self.assertIn("  card（", out)

    def test_max_counts_after_existing(self):
        (self.issue / "06_配图").mkdir()
        (self.issue / "06_配图" / "card.png").write_bytes(b"\x89PNG fake")
        rc, out = self.run_main("--max", "1")
        self.assertIn("已有 1 张，这次画 1 张", out)
        self.assertIn("  e001（", out)


if __name__ == "__main__":
    unittest.main()
