#!/usr/bin/env python3
"""视频导演（video3_director.py，11-08 晚加）的小测试：不调 claude、不组装、不联网。
用法（项目根）：~/.venvs/frontier-daily/bin/python site/tools/test_video3_director.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import video3_director as DR  # noqa: E402

ORIG = {"schema": "video3", "edition": "weekday", "date": "2026-11-09", "accent": "amber",
        "chapters": [{"id": "open", "kind": "open", "title": "开场", "tone": "x", "narration": "今天两件事。"},
                     {"id": "a", "kind": "story", "title": {"zh": "甲"}, "tone": "y", "narration": "甲说了一句话。"}]}
MEDIA = {"duration": 30.0, "chapters": [{"id": "open", "kind": "open", "start": 0, "end": 8, "vs": 2, "ve": 7},
                                        {"id": "a", "kind": "story", "start": 8, "end": 30, "vs": 9, "ve": 28}],
         "transcript": [{"ch": 0, "start": 2.1, "end": 6.9, "text": "今天两件事。"},
                        {"ch": 1, "start": 9.2, "end": 15.0, "text": "甲说了"}, {"ch": 1, "start": 15.5, "end": 27.5, "text": "一句话。"}]}


class LoadDirector(unittest.TestCase):
    def check(self, sb):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "视频v3_分镜.json").write_text(sb if isinstance(sb, str) else json.dumps(sb, ensure_ascii=False), encoding="utf-8")
            return DR.load_director(Path(d), ORIG)

    def test_same_ok(self):
        sb, bad = self.check(json.loads(json.dumps(ORIG)))
        self.assertEqual(bad, "")

    def test_narration_or_order_changed(self):
        x = json.loads(json.dumps(ORIG))
        x["chapters"][1]["narration"] = "甲说了两句话。"
        self.assertIn("narration", self.check(x)[1])
        x = json.loads(json.dumps(ORIG))
        x["chapters"].reverse()
        self.assertIn("顺序", self.check(x)[1])
        x = json.loads(json.dumps(ORIG))
        x["accent"] = "blue"
        self.assertIn("accent", self.check(x)[1])

    def test_bad_json(self):
        sb, bad = self.check("{不是 JSON")
        self.assertIsNone(sb)
        self.assertIn("不是合法 JSON", bad)


class Effort(unittest.TestCase):
    """导演的思考强度（11-10 加）：默认不传（11-10 本机对比 xhigh 超时退回）；default／none／off 不传；认不出的不传、不退回。"""

    def run_with(self, value):
        import os
        old = os.environ.get("FD_DIRECTOR_EFFORT")
        try:
            if value is None:
                os.environ.pop("FD_DIRECTOR_EFFORT", None)
            else:
                os.environ["FD_DIRECTOR_EFFORT"] = value
            return DR.director_effort()
        finally:
            if old is None:
                os.environ.pop("FD_DIRECTOR_EFFORT", None)
            else:
                os.environ["FD_DIRECTOR_EFFORT"] = old

    def test_default_is_not_set(self):
        self.assertIsNone(self.run_with(None))
        self.assertIsNone(self.run_with(""))              # 仓库变量没设时，流程传进来的是空字符串
        self.assertEqual(self.run_with("xhigh"), "xhigh")

    def test_levels_and_off(self):
        self.assertEqual(self.run_with("High"), "high")
        for v in ("default", "none", "off"):
            self.assertIsNone(self.run_with(v))
        self.assertIsNone(self.run_with("ultra"))


class FrameTimes(unittest.TestCase):
    def test_fixed_plus_random_and_seed_changes(self):
        a = DR.frame_times(MEDIA, "s1")
        b = DR.frame_times(MEDIA, "s2")
        for t in (2.6, 10.0, 27.2):                 # 固定位置：片头、每章开头 1 秒、结尾前 0.8 秒（太近的只留一张）
            self.assertIn(t, a)
        self.assertNotEqual(a, b)                    # 随机的那几帧每轮不同
        self.assertTrue(all(y - x >= 0.6 for x, y in zip(a, a[1:])))
        self.assertTrue(all(0 < t < MEDIA["duration"] for t in a))
        fixed = {2.6, 3.0, 4.5, 6.2, 10.0, 18.5, 27.2, 13.75, 23.25}
        self.assertTrue(set(a) - fixed)              # 有不在固定取样点的帧


class Subjects(unittest.TestCase):
    def test_prompt_record_parse(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "提示词记录.md").write_text("# x\n\n- 2026-11-08T19:15:02+00:00 `v_racks.png`（card，D1）：a plain photo of racks Codex，用量 76,517 token，128 秒\n"
                                                    "- 2026-11-08T05:42:10+00:00 `v_road.png`（tile，D2）：a hall agy，52 秒\n", encoding="utf-8")
            s = DR.prompt_subjects(Path(d))
        self.assertEqual(s["v_racks"], "a plain photo of racks")
        self.assertEqual(s["v_road"], "a hall")


class Narration(unittest.TestCase):
    """旁白归导演（11-09 加）：结构检查放开、旁白检查（稿子检查、读音表、中文人名头衔）、改没改旁白的比较。"""
    CARDS = [{"event_id": "E001", "title_zh": "英伟达董事会启动独立调查", "status": "confirmed",
              "facts": [{"text_zh": "英伟达董事会宣布启动独立调查，起因是有报道称创始人兼CEO黄仁勋成为外国情报活动的目标。", "source_id": "s1",
                         "quote": "The NVIDIA Board is initiating an independent investigation"}],
              "numbers": [{"value": "18", "unit": "小时", "meaning_zh": "仿真耗时", "source_id": "s1", "quote": "about 18 hours"}],
              "who_said": [], "sources": [{"id": "s1", "url": "https://example.com/a"}]}]

    def issue(self, d, narration):
        R = Path(d)
        (R / "03_事件卡").mkdir(parents=True)
        (R / "04_文稿").mkdir(parents=True)
        (R / "03_事件卡/cards_写稿用.json").write_text(json.dumps(self.CARDS, ensure_ascii=False), encoding="utf-8")
        (R / "04_文稿/视频旁白_v3.md").write_text("# 视频旁白 v3\n\n## 开场\n\n" + narration + "\n", encoding="utf-8")
        return R

    def test_structure_open_when_narration(self):
        x = json.loads(json.dumps(ORIG))
        x["chapters"][1]["narration"] = "甲说了两句话。"
        x["chapters"].append({"id": "b", "kind": "story", "title": "乙", "narration": "乙。"})
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "视频v3_分镜.json").write_text(json.dumps(x, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(DR.load_director(Path(d), ORIG, narr=True)[1], "")
            x["date"] = "2026-11-10"
            (Path(d) / "视频v3_分镜.json").write_text(json.dumps(x, ensure_ascii=False), encoding="utf-8")
            self.assertIn("date", DR.load_director(Path(d), ORIG, narr=True)[1])

    def test_checks_pass_on_card_facts(self):
        with tempfile.TemporaryDirectory() as d:
            must, soft, warn = DR.narration_checks(self.issue(d, "英伟达董事会启动独立调查，创始人兼 CEO 黄仁勋成了外国情报活动的目标。仿真用了约 18 小时。"))
        self.assertEqual(must, [], must)

    def test_checks_catch_numbers_names_titles(self):
        with tempfile.TemporaryDirectory() as d:
            must, soft, warn = DR.narration_checks(self.issue(d, "英伟达首席科学家张三丰说，营收 300 亿美元。我们的理解是一，我们的理解是二。"))
        txt = "\n".join(must)
        for k in ("300", "张三丰", "首席科学家", "最多一次"):
            self.assertIn(k, txt, k)

    def test_narr_key(self):
        a = json.loads(json.dumps(ORIG))
        b = json.loads(json.dumps(ORIG))
        self.assertEqual(DR.narr_key(a), DR.narr_key(b))
        b["chapters"][0]["narration"] = "今天三件事。"
        self.assertNotEqual(DR.narr_key(a), DR.narr_key(b))


class HotTopics(unittest.TestCase):
    """11-09：旁白归导演时，选题 hot 的前两条必须在视频里讲到（stories 写了它，或旁白有字的章画面上有 ref 指向它的事实）。"""
    LINEUP = {"hot": [{"event_id": "E001", "title_zh": "英伟达董事会启动独立调查"},
                      {"event_id": "E016", "title_zh": "Anthropic 自建燃气发电"},
                      {"event_id": "E048", "title_zh": "千问办公 2.0"}]}

    def sb(self):
        return {"facts": {"e016.deal": {"event": "E016", "field": "facts", "index": 0, "check": "x"}},
                "chapters": [{"id": "open", "kind": "open", "narration": "今天。", "stories": ["E016"]},
                             {"id": "board", "kind": "story", "narration": "董事会启动调查。", "stories": ["E001"]},
                             {"id": "power", "kind": "story", "narration": "燃气轮机排队。", "stories": ["E060"],
                              "blocks": [{"type": "quote_card", "text": {"zh": "签下协议", "ref": ["e016.deal"]}}]}]}

    def test_both_present(self):
        self.assertEqual(DR.hot_missing(self.sb(), self.LINEUP), [])       # E016 靠画面上的 ref；第三条热点不要求

    def test_missing_second(self):
        sb = self.sb()
        sb["chapters"][2]["blocks"] = []
        self.assertEqual(DR.hot_missing(sb, self.LINEUP), [("E016", "Anthropic 自建燃气发电")])   # open 章的 stories 不算

    def test_no_hot_weekend(self):
        self.assertEqual(DR.hot_missing(self.sb(), {"hot": []}), [])
        self.assertEqual(DR.hot_missing(self.sb(), None), [])

    def test_case_and_empty_narration(self):
        sb = self.sb()
        sb["chapters"][1]["stories"] = ["e001"]
        sb["chapters"][2]["narration"] = ""                              # 旁白空着的章，画面上的 ref 不算
        self.assertEqual(DR.hot_missing(sb, self.LINEUP), [("E016", "Anthropic 自建燃气发电")])


class VoicePitchGate(unittest.TestCase):
    """11-09：导演重配的视频旁白照播客的音高把关（超出允许偏差重录，最多再录次数和播客同一个设置）：命令里不能关音高把关。"""

    def test_voice_cmd_keeps_pitch_gate(self):
        import inspect
        src = inspect.getsource(DR.voice_narration)
        self.assertIn('"--stage", "voice"', src)
        self.assertNotIn("--no-pitch-gate", src)

    def test_same_profile_as_podcast(self):
        prof = json.loads((Path(__file__).resolve().parents[2] / "pipeline/voice_profile.json").read_text(encoding="utf-8"))
        self.assertEqual(prof["音高把关"]["最多再录"], 2)


class IssueDateAndReason(unittest.TestCase):
    """11-09：导演旁白的稿子检查只放行这期的日期（开场的"11 月 10 日"）；退回原因写真正的报错，不写提醒。"""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipeline"))
        import script_check as S
        self.S = S
        self.d = Path(tempfile.mkdtemp())
        self.R = self.d / "2026-11-10" / "渲染"
        (self.R / "04_文稿").mkdir(parents=True)
        (self.R / "04_文稿" / "视频v3_分镜.json").write_text(json.dumps({"date": "2026-11-10"}), encoding="utf-8")

    def must(self, text):
        ev = self.S.Evidence([{"event_id": "E001", "facts": [{"text_zh": "11 月 9 日，彭博社报道。"}]}])
        DR.allow_issue_date(ev, self.R)
        return [r["原文"] for r in self.S.check(text, ev, day="日常")["要改"] if r["类"] == "数字"]

    def test_issue_date_allowed(self):
        self.assertEqual(self.must("## 开场\n\n11 月 10 日。谷歌给 TPU 加了两个版本。\n"), [])

    def test_other_dates_still_checked(self):
        self.assertEqual(self.must("## 开场\n\n11 月 11 日。谷歌给 TPU 加了两个版本。\n"), ["11月11日"])
        self.assertTrue(any("2025" in x for x in self.must("## 开场\n\n2025 年 11 月 10 日，谷歌发布了。\n")))   # 别的年份照旧拦
        self.assertEqual(self.must("## 开场\n\n11 月 9 日，彭博社报道。\n"), [])          # 事件卡里有的照常过

    def test_date_from_dir_when_no_storyboard(self):
        (self.R / "04_文稿" / "视频v3_分镜.json").unlink()
        self.assertEqual(str(DR.issue_date(self.R)), "2026-11-10")

    def test_fail_reason_skips_reminders(self):
        (self.d / "检查结果.txt").write_text(
            "没通过（第一轮_改错2后，t）\n\n## 一、第 7 步分镜检查\n\n提醒：「robot」timeline/units 的 shot 原句比字幕小\n"
            "提醒：这一期用了 4 处原文截图／摘录\n## 二、旁白\n\n  ✗ 要改：稿子检查：第 8 行 [数字] 11月10日 —— 日期\n", encoding="utf-8")
        self.assertEqual(DR.fail_reason(self.d), ["要改：稿子检查：第 8 行 [数字] 11月10日 —— 日期"])


if __name__ == "__main__":
    unittest.main()
