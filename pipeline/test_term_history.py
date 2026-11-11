#!/usr/bin/env python3
"""今日一词去重（term_history.py，第 4 步选题自查、第 7 步稿子检查）的测试（2026-11-03 加）。

起因：10-31 讲了「开放权重 / open weights」，11-03 又讲「开源权重 / open weights」——同一个词三天后重复，中文名还换了。
这里查：同一个词怎么认（英文大小写、单复数、连字符，中文名，定名表里的旧写法）；近 30 天重复没标 repeat_of、
播客没点明哪天讲过、中文名和往期不一样，都算要改；标对了、换了词、超过 30 天、周末名词解释都不误报。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python pipeline/test_term_history.py        # 全部通过时退出码为 0
不调用任何模型；假的往期放在系统临时目录里，真实的往期（测试版/ 下 10-31 到 11-03）只读。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

import term_history as T  # noqa: E402

TABLE = [{"en": "open weights", "zh": "开放权重", "不用": ["开源权重"], "定于": "2026-11-03", "理由": "测试用"}]
OW_1031 = {"zh": "开放权重", "en": "open weights", "explain_zh": "模型的参数文件公开可下载，开发者能自行部署、微调；许可条款可能有限制，不完全等同于开源软件。"}


def make_issue(root, day, term=None, podcast_term=None, glossary=None, lineup_term=None):
    """在 root/day 下写一期假的网页稿（daily_card.term 或周末 glossary）、播客稿、选题。"""
    d = Path(root) / day
    (d / "04_文稿").mkdir(parents=True, exist_ok=True)
    (d / "02_选题").mkdir(parents=True, exist_ok=True)
    web = {"daily_card": {"headlines": []}, "sections": []}
    if term:
        web["daily_card"]["term"] = dict(term)
        web["sections"].append({"kind": "term", "items": [{"id": "E001", "title_zh": "今日一词：" + term["zh"],
                                                            "title_en": "Word of the day: " + term["en"], "body_zh": "正文"}]})
    if glossary:
        web["sections"].append({"kind": "deep", "items": [{"id": "D1", "glossary": glossary}]})
    (d / "04_文稿" / "claude_网页.json").write_text(json.dumps(web, ensure_ascii=False), encoding="utf-8")
    if podcast_term is not None:
        (d / "04_文稿" / "claude_播客_v3.md").write_text(
            "# 稿\n\n## 开场\n\n早上好。\n\n## 今日一词\n\n%s\n\n## 结尾\n\n我们下期见。\n" % podcast_term, encoding="utf-8")
    (d / "02_选题" / "最终选题.json").write_text(json.dumps({"term": lineup_term or term or {}}, ensure_ascii=False), encoding="utf-8")
    return d


class SameTerm(unittest.TestCase):
    def test_english_forms(self):
        self.assertTrue(T.same_term({"en": "open weights"}, {"en": "Open-Weight"}))
        self.assertTrue(T.same_term({"en": "token"}, {"en": "Tokens"}))
        self.assertTrue(T.same_term({"en": "open weights"}, {"en": "open-weight models"}))   # 两个词以上的短语整段包含
        self.assertFalse(T.same_term({"en": "token"}, {"en": "token budget"}))               # 单个词不按包含算
        self.assertFalse(T.same_term({"en": "open weights"}, {"en": "open source"}))
        self.assertFalse(T.same_term({"en": "class"}, {"en": "clas"}))                      # ss 结尾不去 s

    def test_chinese_forms(self):
        self.assertTrue(T.same_term({"zh": "开放权重"}, {"zh": "开放权重模型"}))
        self.assertFalse(T.same_term({"zh": "词元"}, {"zh": "词元预算"}))                    # 两个字的不按包含算
        self.assertTrue(T.same_term({"zh": "词元", "en": "x"}, {"zh": "词元", "en": "y"}))   # 中文名相同也算

    def test_decision_old_name(self):
        self.assertEqual(T.decision_for({"zh": "开源权重"}, TABLE)["zh"], "开放权重")    # 定名表"不用"里的旧写法也认
        self.assertIsNone(T.decision_for({"zh": "词元", "en": "token"}, TABLE))

    def test_real_decision_table(self):
        d = T.decision_for({"en": "open weights"})
        self.assertIsNotNone(d, "术语定名.json 里应有 open weights")
        self.assertEqual(d["zh"], "开放权重")


class Dates(unittest.TestCase):
    def test_han(self):
        self.assertEqual([T.han_num(n) for n in (1, 10, 11, 20, 21, 31)], ["一", "十", "十一", "二十", "二十一", "三十一"])

    def test_mentions(self):
        for s in ("十月三十一号我们讲过开放权重", "10 月 31 日讲过", "10月31号", "十月三十一日"):
            self.assertTrue(T.mentions_date(s, "2026-10-31", "2026-11-03"), s)
        self.assertTrue(T.mentions_date("上周五我们讲过它", "2026-10-30", "2026-11-03"))     # 10-30 是星期五
        self.assertTrue(T.mentions_date("昨天讲过", "2026-11-02", "2026-11-03"))
        self.assertFalse(T.mentions_date("昨天讲过", "2026-10-31", "2026-11-03"))
        self.assertFalse(T.mentions_date("今天的词是开放权重", "2026-10-31", "2026-11-03"))
        self.assertFalse(T.mentions_date("十月三十日", "2026-10-31", "2026-11-03"))


class Fake(unittest.TestCase):
    """假的往期：09-30 一词（34 天前）、10-31 开放权重、11-02 周末名词解释；今天 11-03。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_issue(self.root, "2026-09-30", {"zh": "推理", "en": "inference", "explain_zh": "模型用起来的那一步"}, "推理")
        make_issue(self.root, "2026-10-31", OW_1031, "来看今日一词：开放权重，英文叫 open weights。")
        make_issue(self.root, "2026-11-02", glossary=[{"zh": "留出测试", "en": "held-out test", "explain_zh": "没见过的题"}])
        self.today = self.root / "2026-11-03"

    def tearDown(self):
        self.tmp.cleanup()

    def lineup(self, **term):
        return T.lineup_problems({"term": term}, self.today, "weekday", TABLE)

    def test_history(self):
        h = T.history(self.root, "2026-11-03")
        self.assertEqual([(e["date"], e["kind"]) for e in h],
                         [("2026-11-02", "名词解释"), ("2026-10-31", "今日一词"), ("2026-09-30", "今日一词")])
        self.assertEqual(h[1]["days_ago"], 3)
        self.assertIn("开放权重", h[1]["podcast_zh"])

    # ---- 第 4 步
    def test_1103_case(self):          # 11-03 原样：开源权重，没标 repeat_of
        must, warn = self.lineup(zh="开源权重", en="open weights")
        self.assertEqual(len(must), 2, must)
        self.assertIn("10 月 31 日", must[0])
        self.assertIn("repeat_of", must[0])
        self.assertIn("「开放权重」", must[1])
        self.assertIn("rename_why", must[1])

    def test_marked_repeat_passes(self):
        must, warn = self.lineup(zh="开放权重", en="Open Weights",
                                 repeat_of={"date": "2026-10-31", "zh": "开放权重", "explain_zh": "……"})
        self.assertEqual(must, [])

    def test_wrong_date(self):
        must, _ = self.lineup(zh="开放权重", en="open weights", repeat_of={"date": "2026-10-30", "zh": "开放权重"})
        self.assertEqual(len(must), 1)
        self.assertIn("2026-10-30", must[0])

    def test_rename_with_reason(self):
        must, _ = self.lineup(zh="开源权重", en="open weights", repeat_of={"date": "2026-10-31", "zh": "开放权重"},
                              rename_why="测试")
        self.assertEqual(must, [])

    def test_new_term_passes(self):
        self.assertEqual(self.lineup(zh="经营亏损", en="operating loss"), ([], []))

    def test_old_term_only_warns(self):    # 34 天前讲过：不算重复，只提醒
        must, warn = self.lineup(zh="推理", en="inference")
        self.assertEqual(must, [])
        self.assertEqual(len(warn), 1)
        self.assertIn("不算重复", warn[0])

    def test_old_term_name_still_kept(self):   # 超过 30 天，中文名也要沿用
        must, _ = self.lineup(zh="推断", en="inference")
        self.assertEqual(len(must), 1)
        self.assertIn("「推理」", must[0])

    def test_glossary_low_priority(self):
        must, warn = self.lineup(zh="留出测试", en="held-out test")
        self.assertEqual(must, [])
        self.assertTrue(any("名词解释" in w for w in warn), warn)

    def test_repeat_of_without_history(self):
        must, _ = self.lineup(zh="经营亏损", en="operating loss", repeat_of={"date": "2026-10-31"})
        self.assertEqual(len(must), 1)

    def test_weekend_skipped(self):
        self.assertEqual(T.lineup_problems({"term": {"zh": "开源权重", "en": "open weights"}}, self.today, "sunday_deep", TABLE), ([], []))

    # ---- 第 7 步
    def check(self, term, podcast, lineup_term=None, edition="weekday", glossary=None):
        make_issue(self.root, "2026-11-03", term, podcast, glossary=glossary, lineup_term=lineup_term)
        return T.check_issue(self.today, edition, TABLE)

    def test_step7_1103_case(self):
        r = self.check({"zh": "开源权重", "en": "open weights", "explain_zh": "参数数值公开出来"},
                       "今天的词是开源权重，英文叫 open weights。")
        self.assertEqual(len(r["要改"]), 3, r["要改"])
        self.assertIn("repeat_of", r["要改"][0])
        self.assertIn("没点明", r["要改"][1])
        self.assertIn("十月三十一号", r["要改"][1])
        self.assertIn("「开放权重」", r["要改"][2])

    def test_step7_fixed(self):
        r = self.check({"zh": "开放权重", "en": "open weights", "explain_zh": "看它在今天新闻里的分寸"},
                       "十月三十一号我们讲过开放权重，今天换个角度。",
                       lineup_term={"zh": "开放权重", "en": "open weights", "repeat_of": {"date": "2026-10-31", "zh": "开放权重"}})
        self.assertEqual(r["要改"], [])

    def test_step7_mark_in_web_draft(self):   # 选题没标，网页稿 daily_card.term 里补了也认
        r = self.check({"zh": "开放权重", "en": "open weights", "explain_zh": "换个角度",
                        "repeat_of": {"date": "2026-10-31", "zh": "开放权重"}},
                       "十月三十一日讲过开放权重，今天换个角度。", lineup_term={"zh": "开放权重", "en": "open weights"})
        self.assertEqual(r["要改"], [])

    def test_step7_podcast_web_mismatch(self):
        r = self.check({"zh": "经营亏损", "en": "operating loss", "explain_zh": "x"}, "今天的词是营业亏损。")
        self.assertEqual(len(r["要改"]), 1)
        self.assertIn("「经营亏损」", r["要改"][0])

    def test_step7_rename_needs_old_name_in_podcast(self):
        lt = {"zh": "开源权重", "en": "open weights", "repeat_of": {"date": "2026-10-31", "zh": "开放权重"}, "rename_why": "测试"}
        r = self.check({"zh": "开源权重", "en": "open weights", "explain_zh": "x"}, "十月三十一号讲过，今天叫开源权重。", lineup_term=lt)
        self.assertEqual(len(r["要改"]), 1)
        self.assertIn("旧名", r["要改"][0])

    def test_step7_similar_explain_warns(self):
        r = self.check(dict(OW_1031), "十月三十一号我们讲过开放权重。",
                       lineup_term={"zh": "开放权重", "en": "open weights", "repeat_of": {"date": "2026-10-31", "zh": "开放权重"}})
        self.assertEqual(r["要改"], [])
        self.assertTrue(any("很像" in w for w in r["提醒"]), r["提醒"])

    def test_step7_weekend_only_warns(self):
        r = self.check(None, None, edition="saturday_deep",
                       glossary=[{"zh": "开源权重", "en": "open weights", "explain_zh": "x"}])
        self.assertEqual(r["要改"], [])
        self.assertEqual(len(r["提醒"]), 2, r["提醒"])       # 当过今日一词；中文名和定名不一样

    def test_selection_input(self):
        make_issue(self.root, "2026-11-01", {"zh": "开源权重", "en": "open weights", "explain_zh": "y"}, "开源权重")
        obj = T.selection_input(self.today, TABLE)
        self.assertEqual([e["date"] for e in obj["近30天"]], ["2026-11-01", "2026-10-31"])
        self.assertEqual(obj["近30天"][0].get("定名"), "开放权重")      # 当时写成开源权重，注明定名
        self.assertNotIn("定名", obj["近30天"][1])
        self.assertEqual([e["date"] for e in obj["更早"]], ["2026-09-30"])
        self.assertEqual([e["zh"] for e in obj["周末名词解释"]], ["留出测试"])


class RealIssues(unittest.TestCase):
    """真实往期（只读）：11-03 应报三处要改；10-31 到 11-02 不该报。"""

    def test_1103(self):
        issue = T.ISSUES / "2026-11-03"
        if not (issue / "04_文稿" / "claude_网页.json").exists():
            self.skipTest("没有 11-03")
        r = T.check_issue(issue, "weekday")
        self.assertEqual(len(r["要改"]), 3, r["要改"])
        self.assertEqual([e["date"] for e in r["往期同一个词"]], ["2026-10-31"])

    def test_earlier_clean(self):
        for day, ed in (("2026-10-31", "weekday"), ("2026-11-01", "sunday_dialog"), ("2026-11-02", "weekday")):
            issue = T.ISSUES / day
            if (issue / "04_文稿" / "claude_网页.json").exists():
                self.assertEqual(T.check_issue(issue, ed)["要改"], [], day)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False, verbosity=1).result.wasSuccessful() else 1)
