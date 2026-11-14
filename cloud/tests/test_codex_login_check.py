#!/usr/bin/env python3
"""cloud/codex_login_check.py 的测试（2026-11-09 加）：图画成了就不报；没画成、日志里真有登录出错才报；编号里的 401 不算。
11-14 加：没画成、日志里有 Codex 额度用完的原话（或报错行里有 rate limit／429 一类，宽认），写 codex_额度用完.txt
（网页、视频各几张、第一次几点、依据）；和登录失效同时有时只报登录失效；画图说明里的"quota"不算。

用法（在项目根运行）：python3 -m unittest discover -s cloud/tests -v
不调 Codex、不联网、不花钱。
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import codex_login_check as C  # noqa: E402

# 11-09 正式运行 06_配图/log_card.png.txt 里让原来那行 grep 误报的一句（文件名里的编号带 4015）
UUID_LINE = ("bin/bash -lc \"cp /home/runner/work/_temp/codex/generated_images/01a1bfc5-b1b6-7153-988e-0e3739cd9430/"
             "exec-dad0f0bc-001e-4015-94db-41376fce6f6f.png '/home/runner/work/frontier-daily/card.png'\"")
REAL_401 = "ERROR: unexpected status 401 Unauthorized: Your access token could not be refreshed. Please log in again."


class Check(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def log(self, rid, text, img=True, sub=""):
        p = self.d / sub
        p.mkdir(parents=True, exist_ok=True)
        (p / ("log_%s.png.txt" % rid)).write_text("===== t =====\n--- stderr ---\n" + text + "\n", encoding="utf-8")
        if img:
            (p / (rid + ".png")).write_bytes(b"\x89PNG fake")

    def run_main(self):
        out = self.d / "logs" / "codex_登录失效.txt"
        self.assertEqual(C.main([str(self.d), "--out", str(out)]), 0)
        return out

    def test_1109_all_drawn_no_alarm(self):
        """11-09：图都画成了，日志里编号带 401 也不报（原来误报的就是这种）。"""
        self.log("card", UUID_LINE)
        self.log("v_board", "tokens used\n22,692", sub="视频")
        self.assertEqual(C.failures([self.d]), [])
        self.assertFalse(self.run_main().exists())

    def test_drawn_even_with_real_401_text_no_alarm(self):
        """画成了的图，日志里就算真有 401 字样（比如中途续期过一次）也不算失效。"""
        self.log("e001", REAL_401)
        self.assertEqual(C.failures([self.d]), [])

    def test_missing_image_with_login_error(self):
        self.log("e016", REAL_401, img=False)
        self.log("v_desk", "refresh_token was already used", img=False, sub="视频")
        got = C.failures([self.d])
        self.assertEqual([n for n, _ in got], ["e016.png", "v_desk.png"])
        out = self.run_main()
        self.assertTrue(out.exists())
        self.assertIn("e016.png", out.read_text(encoding="utf-8"))

    def test_missing_image_other_error_no_alarm(self):
        """没画成但不是登录问题（超时、编号里的 401、空图）：不报登录失效。"""
        self.log("e030", "超时（12 分钟）\n" + UUID_LINE, img=False)
        self.assertEqual(C.failures([self.d]), [])

    def test_empty_image_counts_as_missing(self):
        self.log("term", "Not logged in", img=False)
        (self.d / "term.png").write_bytes(b"")
        self.assertEqual([n for n, _ in C.failures([self.d])], ["term.png"])

    def test_401_boundaries(self):
        for s in ("status 401", "(401)", "HTTP/1.1 401 Unauthorized", "code=401\n"):
            self.assertTrue(C.LOGIN_ERR.search(s), s)
        for s in ("-4015-", "a401b", "14010", "exec-401f", "id 0401a"):
            self.assertFalse(C.LOGIN_ERR.search(s), s)

    def test_missing_dir_ok(self):
        self.assertEqual(C.failures([self.d / "没有"]), [])
        self.assertEqual(C.quota_failures([self.d / "没有"]), [])

    # ---- 11-14 加：额度用完（经验库第 76 件②）
    # Codex 官方 CLI 的原话（openai/codex codex-rs/protocol/src/error.rs，ed7ca22）：Plus 账号用完时 exec 在 stderr 打的那一行
    PLUS = ("ERROR: You\u2019ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit "
            "https://chatgpt.com/settings/usage to purchase more credits or try again at 3:45 PM.")
    # 画图说明原样抄在日志里（"user" 下面那段）：新闻里的 quota、rate limit 不能算
    BRIEF = ("user\nUse your built-in image generation tool to create exactly ONE image.\n"
             "Subject: a port crane under a new export quota; dashboards showing API rate limits\n")

    def qlog(self, rid, text, when, img=False, sub=""):
        p = self.d / sub
        p.mkdir(parents=True, exist_ok=True)
        (p / ("log_%s.png.txt" % rid)).write_text("===== %s =====\n%s\n\n--- stderr ---\n%s\n" % (when, p / (rid + ".png"), text),
                                                   encoding="utf-8")
        if img:
            (p / (rid + ".png")).write_bytes(b"\x89PNG fake")

    def test_quota_marker_counts_web_and_video_and_first_time(self):
        self.qlog("card", self.BRIEF + self.PLUS, "2026-11-12T05:04:10+00:00")
        self.qlog("e002", "ERROR: Quota exceeded. Check your plan and billing details.", "2026-11-12T05:02:31+00:00")
        self.qlog("v_lab", "ERROR: You've hit your usage limit for GPT-6.1-Sol. Switch to another model now, or try again later.",
                  "2026-11-12T05:06:00+00:00", sub="视频")
        self.qlog("e003", self.PLUS, "2026-11-12T05:01:00+00:00", img=True)                  # 画成了的不算
        self.qlog("e004", self.BRIEF + "超时（12 分钟）", "2026-11-12T05:00:00+00:00")         # 没画成、说明里有 quota：不算
        got = C.quota_failures([self.d])
        self.assertEqual(sorted(x[0] for x in got), ["card.png", "e002.png", "v_lab.png"])
        self.assertEqual({x[4] for x in got}, {"原话"})
        out = self.run_main()
        self.assertFalse(out.exists(), "没有登录出错：不写登录失效")
        text = out.with_name(C.QUOTA_NAME).read_text(encoding="utf-8")
        self.assertTrue(text.startswith("Codex 额度用完（"), text)
        self.assertIn("3 张没画成（网页 2 张、视频 1 张）", text)
        self.assertIn("第一次在 05:02 UTC", text)
        self.assertIn("网页=2\n视频=1\n第一次=2026-11-12 05:02\n依据=原话", text)

    def test_login_failure_wins_over_quota(self):
        """两种都有：只写登录失效，不写额度的记号。"""
        self.qlog("card", self.PLUS, "2026-11-12T05:04:10+00:00")
        self.qlog("e016", REAL_401, "2026-11-12T05:05:00+00:00")
        out = self.run_main()
        self.assertTrue(out.exists())
        self.assertFalse(out.with_name(C.QUOTA_NAME).exists())

    def test_quota_official_phrases(self):
        for s in (self.PLUS, "You've hit your usage limit. Try again at 3:45 PM.",
                  "Quota exceeded. Check your plan and billing details.",
                  "Your workspace is out of credits. Add credits to continue.",
                  "You hit your spend cap set in your workspace."):
            self.assertEqual(C.quota_words(s)[1], "原话", s)

    def test_quota_loose_only_on_error_lines(self):
        """宽认（待核）：只在带 error 的行里认 usage limit、rate limit、单独的 429、quota；画图说明里的不算。"""
        for s in ("ERROR: exceeded retry limit, last status: 429 Too Many Requests",
                  "stream error: rate_limit_exceeded", 'ERROR: {"error":{"type":"usage_limit_reached"}}', "error: quota"):
            self.assertEqual(C.quota_words(s), (C.quota_words(s)[0], "宽认"), s)
        for s in (self.BRIEF, "ERROR: stream disconnected before completion", "error code -4290-", "ERROR: a429b"):
            self.assertIsNone(C.quota_words(s), s)

    def test_quota_loose_marker_says_maybe(self):
        self.qlog("e005", "ERROR: exceeded retry limit, last status: 429 Too Many Requests", "2026-11-12T05:03:00+00:00")
        self.run_main()
        text = (self.d / "logs" / C.QUOTA_NAME).read_text(encoding="utf-8")
        self.assertTrue(text.startswith("Codex 多半是额度用完或被限流"), text)
        self.assertIn("依据=宽认", text)

    def test_quota_out_option_and_mtime_fallback(self):
        p = self.d / "06_配图"
        p.mkdir()
        (p / "log_term.png.txt").write_text("没有时间行\nERROR: Quota exceeded. Check your plan and billing details.\n",
                                            encoding="utf-8")
        q = self.d / "别处" / "额度.txt"
        self.assertEqual(C.main([str(self.d), "--out", str(self.d / "logs" / "codex_登录失效.txt"), "--quota-out", str(q)]), 0)
        self.assertIn("网页=1\n视频=0\n第一次=", q.read_text(encoding="utf-8"))

    def test_director_dir_counts_as_video(self):
        d = self.d / "11_视频v3_导演"
        d.mkdir()
        (d / "log_n1.png.txt").write_text("===== 2026-11-12T05:30:00+00:00 =====\n" + self.PLUS + "\n", encoding="utf-8")
        self.assertEqual([x[2] for x in C.quota_failures([d])], ["视频"])

    def test_no_quota_no_marker(self):
        self.qlog("e006", "超时（12 分钟）", "2026-11-12T05:03:00+00:00")
        out = self.run_main()
        self.assertFalse(out.exists())
        self.assertFalse(out.with_name(C.QUOTA_NAME).exists())


if __name__ == "__main__":
    unittest.main()
