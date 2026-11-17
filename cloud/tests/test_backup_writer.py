"""cloud/backup_writer.py（备用写稿）的单元测试：不联网、不调 MiMo、不跑 fd。

MiMo 用假回答，fd 用假的"跑一轮"（按剧本写 logs/fd_state.json、返回退出码），测驱动逻辑：
停在哪一步做什么、每一步最多交回改一次、超上限就停、用量每次都记、审读意见第一行和条数一致。

    python3 -m unittest discover -s cloud/tests -v
"""
import json
import sys
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "pipeline"))
import backup_writer as BW  # noqa: E402
from orchestrator.steps import must_fix_count  # noqa: E402

DAY = "2026-11-16"          # 星期一：工作日版

CARD = {"event_id": "E001", "title_zh": "示例", "facts": [{"text_zh": "甲", "quote": "A said"}, {"text_zh": "乙", "quote": "B"}],
        "numbers": [{"value": "3", "quote": "3 units"}], "who_said": [{"who": "某人", "quote": "hello"}], "sources": []}
LINEUP = {"storylines": [{"id": "S1", "zh": "主线", "thesis_zh": "判断"}], "theme": {"accent": "blue", "why_zh": "新模型"},
          "hot": [{"event_id": "E001", "title_zh": "示例", "storyline": "S1", "why": "因为"}], "brief": [], "flash": [], "teaser": [],
          "term": {"zh": "词", "en": "term", "why": "串起两条"}}
POD = "## 开场\n\n我是 Shirley。\n\n## 结尾\n\n下期见。\n\n<!-- 语气\n{\"开场\": \"calm and steady\"}\n-->\n"
WEB = {"daily_card": {}, "sections": [], "page": {}}
SB = {"schema": "video3-storyboard/1", "date": DAY, "chapters": []}


def usage(i=1000, o=200, cached=0, think=50):
    return {"prompt_tokens": i, "completion_tokens": o, "total_tokens": i + o,
            "prompt_tokens_details": {"cached_tokens": cached}, "completion_tokens_details": {"reasoning_tokens": think}}


class FakeChat:
    """按提示里的任务句挑回答；记下每次收到的系统提示和任务。"""

    def __init__(self, replies):
        self.replies = replies          # [(提示里要有的一句, 回答文字或 Exception, finish)]
        self.got = []

    def __call__(self, model, system, user, max_tokens, temperature, **kw):
        self.got.append({"system": system, "user": user, "max_tokens": max_tokens, "thinking": kw.get("thinking")})
        for i, row in enumerate(self.replies):
            needle, reply, finish = row[:3]
            if needle in user:
                self.replies.pop(i)
                if isinstance(reply, Exception):
                    raise reply
                return {"content": reply, "usage": row[3] if len(row) > 3 else usage(), "finish": finish, "model": model}
        raise AssertionError("假 MiMo 没准备这一问：" + user[-200:])


class FakeFd:
    """剧本：每跑一轮取一项 (退出码, 停在第几步, 状态, 要你做, 这一轮要不要先做的事)。"""

    def __init__(self, issue, script):
        self.issue, self.script, self.n = Path(issue), list(script), 0

    def __call__(self):
        rc, no, status, todo, before = self.script.pop(0)
        self.n += 1
        if before:
            before(self.issue)
        st = {"步骤": {}, "运行记录": [{"结果": "跑完" if rc == 0 else "停在第 %s 步：示例" % no}]}
        if no:
            st["步骤"][BW.STEP_KEYS[no]] = {"状态": status, "说明": "示例", "要你做": todo or []}
        (self.issue / "logs").mkdir(parents=True, exist_ok=True)
        (self.issue / "logs" / "fd_state.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        return rc


def make_issue(root, with_input=True):
    d = Path(root) / DAY
    (d / "04_文稿").mkdir(parents=True)
    (d / "02_选题").mkdir(parents=True)
    if with_input:
        inp = {"date": DAY, "edition": "weekday", "lineup": LINEUP, "cards": [CARD], "notes": ""}
        (d / BW.WRITE_INPUT).write_text(json.dumps(inp, ensure_ascii=False), encoding="utf-8")
    return BW.Issue(DAY, str(d))


def write_check(issue, items):
    (issue / "logs").mkdir(parents=True, exist_ok=True)
    (issue / "logs" / "检查_稿子.json").write_text(json.dumps({"检查": items, "要改合计": sum(len(i["要改"]) for i in items)},
                                                          ensure_ascii=False), encoding="utf-8")


class Pure(unittest.TestCase):
    def test_numbered_input_labels_and_keeps_original(self):
        inp = {"cards": [json.loads(json.dumps(CARD))]}
        out = BW.numbered_input(inp)
        c = out["cards"][0]
        self.assertEqual([f["编号"] for f in c["facts"]], ["F0", "F1"])
        self.assertEqual(c["numbers"][0]["编号"], "N0")
        self.assertEqual(c["who_said"][0]["编号"], "W0")
        self.assertNotIn("编号", inp["cards"][0]["facts"][0])           # 文件里那份不动
        self.assertEqual(c["facts"][1]["quote"], "B")

    def test_output_caps_leave_room_for_reasoning(self):
        # 11-16 真跑：选题那次光思考就 20,899 token；上限要给正文留足地方
        for k, v in BW.MAX_OUT.items():
            self.assertGreaterEqual(v, 40000, k)
        self.assertGreaterEqual(BW.CALL_TIMEOUT, 1200)

    def test_parse_json_reply(self):
        self.assertEqual(BW.parse_json_reply('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(BW.parse_json_reply('好的，下面是 JSON：\n{"a": {"b": 2}}\n希望有用'), {"a": {"b": 2}})
        with self.assertRaises(ValueError):
            BW.parse_json_reply("没有 JSON")

    def test_clean_text_reply(self):
        self.assertTrue(BW.clean_text_reply("```markdown\n" + POD + "```").startswith("## 开场"))
        self.assertTrue(BW.clean_text_reply("好的，稿子如下。\n\n" + POD).startswith("## 开场"))

    def test_split_marked(self):
        p = BW.split_marked('前言\n===处理===\n[{"条": "必须改 1"}]\n===稿子===\n## 开场\n正文\n===完===\n', ["处理", "稿子"])
        self.assertEqual(json.loads(p["处理"])[0]["条"], "必须改 1")
        self.assertEqual(p["稿子"], "## 开场\n正文")
        with self.assertRaises(ValueError):
            BW.split_marked("===稿子===\nx", ["处理", "稿子"])

    def test_review_first_line_matches_count_and_fd_reads_it(self):
        rv = {"must": [{"where": "播客", "files": ["播客"]}, {"where": "网页", "files": ["网页"]}], "suggest": [{"where": "x"}]}
        md = BW.render_review(rv, {"04_文稿/claude_播客_v3.md": "abc", "_day": DAY})
        self.assertEqual(md.splitlines()[0], "必须改：2")
        self.assertEqual(must_fix_count(md), 2)
        md0 = BW.render_review({"must": [], "suggest": [{"where": "x"}]}, {})
        self.assertEqual(must_fix_count(md0), 0)

    def test_review_items_default_all_files(self):
        items = BW.review_items({"must": [{"where": "a"}, {"where": "b", "files": ["视频", "瞎写"]}],
                                 "suggest": [{"where": "c", "files": ["播客"]}], "better": [{"where": "d"}]})
        self.assertEqual(items[0]["_files"], list(BW.KINDS))
        self.assertEqual(items[1]["_files"], ["视频"])
        # 11-17 改：备用模式改稿只交必须改，建议改、可以更好不交
        self.assertEqual([i["_label"] for i in items], ["必须改 1", "必须改 2"])
        self.assertTrue(all(i["_must"] for i in items))

    def test_credits(self):
        noon = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
        night = datetime(2026, 11, 16, 20, tzinfo=timezone.utc)
        u = usage(1000, 100, cached=400)
        self.assertEqual(BW.credits_of("mimo-v2.6-pro", u, noon), 600 * 300 + 400 * 2.5 + 100 * 600)
        self.assertEqual(BW.credits_of("mimo-v2.6-pro", u, night), round((600 * 300 + 400 * 2.5 + 100 * 600) * 0.8))

    def test_check_problems_mapping(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            write_check(iss.dir, [{"名字": "读音表", "要改": ["第 3 行 x"]}, {"名字": "视频分镜", "要改": ["✗ 触发词找不到"]},
                                  {"名字": "网页数字", "要改": []}, {"名字": "今日一词", "要改": ["网页稿里今日一词的中文名两处不一样"]},
                                  {"名字": "易歧义词（只提醒）", "要改": []}])
            p = BW.check_problems(iss, rerun=lambda name: ["✗ 另一处触发词"])
            self.assertEqual(p["播客"], ["[读音表] 第 3 行 x"])
            self.assertEqual(p["视频"], ["[视频分镜] ✗ 触发词找不到", "[视频分镜] ✗ 另一处触发词"])
            self.assertEqual(p["网页"], ["[今日一词] 网页稿里今日一词的中文名两处不一样"])

    def test_task_sections_found_in_real_docs(self):
        sec = BW.task_sections()
        self.assertIn("视频分镜要画出关系", sec["写稿"])
        self.assertIn("必须改的逐条核对卡片", sec["改稿"])
        self.assertIn("唯一的事实依据是", sec["审读"])
        self.assertNotIn("**回报**", sec["审读"])
        self.assertIn("已定规矩", BW.rule_parts())

    def test_common_material_has_fact_rule_and_cards(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            m = BW.common_material(iss)
            self.assertIn("cards_写稿用.json", m)
            self.assertIn("唯一的事实依据", m)
            self.assertIn('"编号":"F1"', m)
            self.assertEqual(m, BW.common_material(iss))         # 一字不差：每次调用前缀相同才能命中缓存
            # 写稿任务里不重复放写作指南、读音表（它们在共同材料里）
            self.assertNotIn("写作指南.md", iss.prompt_files("播客"))
            self.assertIn("写稿_播客.md", iss.prompt_files("播客"))
            self.assertIn("写稿_视频v3.md", iss.prompt_files("视频"))


class MimoClient(unittest.TestCase):
    def test_records_usage_and_caps_calls(self):
        with tempfile.TemporaryDirectory() as t:
            chat = FakeChat([("任务一", "回答一", "stop"), ("任务二", "回答二", "stop")])
            m = BW.Mimo(t, chat=chat, max_calls=1)
            self.assertEqual(m.call(6, "写", "系统", "任务一", 100, 0.1), "回答一")
            with self.assertRaises(BW.Stop):
                m.call(6, "写", "系统", "任务二", 100, 0.1)
            log = json.loads((Path(t) / BW.USAGE).read_text(encoding="utf-8"))
            self.assertEqual(log["合计"]["次数"], 1)
            self.assertEqual(log["调用"][0]["输入token"], 1000)
            self.assertEqual(log["调用"][0]["其中思考"], 50)
            self.assertTrue((Path(t) / BW.CALL_DIR / "01_第6步_写_回答.txt").exists())

    def test_token_cap(self):
        with tempfile.TemporaryDirectory() as t:
            m = BW.Mimo(t, chat=FakeChat([("a", "x", "stop"), ("b", "y", "stop")]), max_tokens=1100)
            m.call(6, "写", "s", "a", 10, 0.1)
            with self.assertRaises(BW.Stop):
                m.call(6, "写", "s", "b", 10, 0.1)

    def test_segment_cap_counts_only_this_segment_and_next_call(self):
        with tempfile.TemporaryDirectory() as t:
            m0 = BW.Mimo(t, chat=FakeChat([("前", "x", "stop")]))
            m0.call(6, "写", "s", "前", 100, 0.1)                       # 上一段用掉 1,200，不算在这一段里
            chat = FakeChat([("a", "x", "stop"), ("b", "y", "stop"), ("c", "z", "stop")])
            m = BW.Mimo(t, chat=chat, segment="续跑", segment_max_tokens=2500)
            m.call(7, "改", "s", "a", 100, 0.1)                         # 这一段：0 ＋ 约 100 ≤ 2,500
            m.call(7, "改", "s", "b", 100, 0.1)                         # 1,200 ＋ 约 100 ≤ 2,500
            with self.assertRaises(BW.Stop):
                m.call(7, "改", "s", "c", 200, 0.1)                     # 2,400 ＋ 约 200 > 2,500：不调
            self.assertEqual(m.segment_used(), 2400)
            self.assertEqual(len(chat.got), 2)
            m2 = BW.Mimo(t, chat=chat, segment="续跑", segment_max_tokens=2500)   # 重开程序：起点不变
            self.assertEqual(m2.segment_used(), 2400)

    def test_no_new_calls_after_deadline(self):
        with tempfile.TemporaryDirectory() as t:
            now = [datetime(2026, 11, 17, 3, 29, tzinfo=timezone.utc)]
            m = BW.Mimo(t, chat=FakeChat([("a", "x", "stop"), ("b", "y", "stop")]),
                        deadline=datetime(2026, 11, 17, 3, 30, tzinfo=timezone.utc), clock=lambda: now[0])
            self.assertEqual(m.call(6, "写", "s", "a", 10, 0.1), "x")
            now[0] = datetime(2026, 11, 17, 3, 30, tzinfo=timezone.utc)
            with self.assertRaises(BW.Stop):
                m.call(6, "写", "s", "b", 10, 0.1)
            self.assertEqual(m.totals()["次数"], 1)

    def test_truncated_and_failed_calls_are_recorded(self):
        with tempfile.TemporaryDirectory() as t:
            m = BW.Mimo(t, chat=FakeChat([("截", "半截", "length"), ("坏", RuntimeError("HTTP 500"), None)]))
            with self.assertRaises(BW.CallFailed):
                m.call(6, "写", "s", "截", 10, 0.1)
            with self.assertRaises(BW.CallFailed):
                m.call(6, "写", "s", "坏", 10, 0.1)
            calls = json.loads((Path(t) / BW.USAGE).read_text(encoding="utf-8"))["调用"]
            self.assertEqual([c["结果"][:3] for c in calls], ["被截断", "失败："])


def put(rel, text):
    def f(issue):
        p = issue / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return f


class DriverLoop(unittest.TestCase):
    def driver(self, iss, chat, script, sb=None, **kw):
        fd = FakeFd(iss.dir, script)
        sel = lambda: ("选题系统提示", "候选事件……")          # noqa: E731
        sb = list(sb or [])

        def sb_runner():                                     # 假的分镜检查：按剧本给结果，剧本用完就"过了"
            return sb.pop(0) if sb else (0, "分镜检查通过：6 章")
        d = BW.Driver(iss, BW.Mimo(iss.dir, chat=chat, **kw), fd_runner=fd, sel_inputs=sel, rerun=lambda n: [],
                      sb_runner=sb_runner)
        return d, fd

    def test_happy_path(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            write_check(iss.dir, [{"名字": "视频分镜", "要改": ["✗ 触发词「x」在旁白里找不到"]}])
            chat = FakeChat([
                ("候选事件", json.dumps(LINEUP, ensure_ascii=False), "stop"),
                ("写这一期的播客稿", POD, "stop"),
                ("写这一期的网页稿", json.dumps(WEB), "stop"),
                ("写这一期的视频稿", "```json\n" + json.dumps(SB) + "\n```", "stop"),
                ("按程序检查的问题改视频稿", json.dumps(dict(SB, fixed=True)), "stop"),
                ("独立审读", json.dumps({"must": [{"where": "播客开场", "files": ["播客"], "fix": "改"}],
                                     "suggest": [{"where": "视频", "files": ["视频"]}]}, ensure_ascii=False), "stop"),
                ("按独立审读的意见改播客稿", '===处理===\n[{"条": "必须改 1", "怎么处理": "改了", "说明": "E001 F0"}]\n'
                                       "===稿子===\n" + POD + "===完===", "stop"),
            ])
            script = [(2, 4, BW.WAITING, None, None), (2, 6, BW.WAITING, None, None), (2, 7, BW.WAITING, ["  - x"], None),
                      (2, 8, BW.WAITING, None, None), (2, 9, BW.WAITING, None, None), (0, None, None, None, None)]
            d, fd = self.driver(iss, chat, script)
            self.assertEqual(d.run(), 0)
            self.assertEqual(json.loads(iss.p(BW.LINEUP).read_text(encoding="utf-8"))["theme"]["accent"], "blue")
            self.assertTrue(iss.p("02_选题/选题说明.md").exists())
            self.assertTrue(json.loads(iss.p(BW.STORYBOARD).read_text(encoding="utf-8"))["fixed"])
            self.assertTrue(iss.p(BW.WEB_DRAFT).exists())
            self.assertEqual(must_fix_count(iss.p(BW.REVIEW).read_text(encoding="utf-8")), 1)
            handled = iss.p(BW.HANDLED).read_text(encoding="utf-8")
            self.assertIn("播客稿：改了", handled)
            mk = json.loads(iss.p(BW.MARKER).read_text(encoding="utf-8"))
            self.assertEqual(mk["写稿"], "MiMo（备用）")
            self.assertEqual(mk["调用次数"], 7)
            self.assertEqual(mk["结果"], "第 4–9 步做完")
            # 审读另起一次调用：任务里没有写稿那几次的任务句（只有稿子本身）
            rv_user = [g["user"] for g in chat.got if "你是\"每日AI科技前沿简报\"" in g["user"] and "独立审读" in g["user"]][0]
            self.assertNotIn("你是这一期的主笔", rv_user)
            self.assertIn("稿子不是你写的", rv_user)
            # 写稿、审读、改稿的系统提示（共同材料）一字不差
            systems = {g["system"] for g in chat.got[1:]}
            self.assertEqual(len(systems), 1)
            self.assertIn("唯一的事实依据", systems.pop())
            # 只改了有必须改的那份（视频只有建议改，不单花一次调用）
            self.assertFalse(any("按独立审读的意见改视频稿" in g["user"] for g in chat.got))

    def test_only_one_fix_round_then_stop(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            for k in BW.KINDS:
                put(iss.files[k], POD if k == "播客" else json.dumps(WEB))(iss.dir)
            write_check(iss.dir, [{"名字": "网页数字", "要改": ["E001 的 3 找不到"]}])
            chat = FakeChat([("按程序检查的问题改网页稿", json.dumps(WEB), "stop")])
            script = [(2, 7, BW.WAITING, None, None), (2, 7, BW.WAITING, None, None), (0, None, None, None, None)]
            d, fd = self.driver(iss, chat, script)
            self.assertEqual(d.run(), 2)
            self.assertEqual(fd.n, 2)                       # 第二次还停在第 7 步就停下，不再交回改
            self.assertEqual(len(chat.got), 1)
            snap = json.loads(iss.p("logs/备用写稿_检查_第7步交回改时.json").read_text(encoding="utf-8"))
            self.assertEqual(snap["交回改的问题"]["网页"], ["[网页数字] E001 的 3 找不到"])
            self.assertIn("停下", json.loads(iss.p(BW.MARKER).read_text(encoding="utf-8"))["结果"])

    def test_checker_crash_is_not_sent_to_mimo(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            for k in BW.KINDS:
                put(iss.files[k], POD if k == "播客" else json.dumps(WEB))(iss.dir)
            write_check(iss.dir, [{"名字": "稿子", "要改": ["script_check 没给出结果：FileNotFoundError: 找不到声音包 v3"]}])
            chat = FakeChat([])
            d, fd = self.driver(iss, chat, [(2, 7, BW.WAITING, None, None)])
            self.assertEqual(d.run(), 2)
            self.assertEqual(chat.got, [])                   # 检查程序自己出错：不花一次 MiMo 去"改"
            self.assertIn("检查程序自己出错", json.loads(iss.p(BW.MARKER).read_text(encoding="utf-8"))["结果"])

    def test_select_fix_once_then_stop(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            chat = FakeChat([("候选事件", json.dumps(LINEUP), "stop"), ("说下面几处要改", json.dumps(LINEUP), "stop")])
            todo = ["按下面的问题改 02_选题/最终选题.json（第 1 轮）：", "  - 主线 S2 只挂了 1 条", "改完再运行：./fd run"]
            script = [(2, 4, BW.WAITING, None, None), (2, 4, BW.WAITING, todo, None), (2, 4, BW.WAITING, todo, None)]
            d, fd = self.driver(iss, chat, script)
            self.assertEqual(d.run(), 2)
            self.assertEqual(len(chat.got), 2)
            self.assertIn("主线 S2 只挂了 1 条", chat.got[1]["user"])

    def test_fd_failure_stops_without_calls(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t, with_input=False)
            chat = FakeChat([])
            d, fd = self.driver(iss, chat, [(2, 5, BW.FAILED, None, None)])
            self.assertEqual(d.run(), 2)
            self.assertEqual(chat.got, [])

    def test_bad_json_twice_stops_and_nothing_written(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            put(iss.files["播客"], POD)(iss.dir)
            chat = FakeChat([("写这一期的网页稿", "不是 JSON", "stop"), ("再次提醒", "还不是", "stop")])
            d, fd = self.driver(iss, chat, [(2, 6, BW.WAITING, None, None)])
            self.assertEqual(d.run(), 2)
            self.assertFalse(iss.p(BW.WEB_DRAFT).exists())
            self.assertEqual(json.loads(iss.p(BW.USAGE).read_text(encoding="utf-8"))["合计"]["次数"], 2)

    def test_thinking_runaway_retries_once_without_thinking(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            put(iss.files["播客"], POD)(iss.dir)
            put(iss.files["网页"], json.dumps(WEB))(iss.dir)
            runaway = usage(1000, 64000, think=64003)
            chat = FakeChat([("写这一期的视频稿", "", "length", runaway), ("写这一期的视频稿", json.dumps(SB), "stop")])
            d, fd = self.driver(iss, chat, [(2, 6, BW.WAITING, None, None), (0, None, None, None, None)])
            self.assertEqual(d.run(), 0)
            self.assertEqual([g["thinking"] for g in chat.got], [None, "disabled"])
            self.assertTrue(iss.p(BW.STORYBOARD).exists())
            calls = json.loads(iss.p(BW.USAGE).read_text(encoding="utf-8"))["调用"]
            self.assertEqual([c["做什么"] for c in calls], ["写视频稿", "写视频稿_关思考"])
            self.assertEqual(calls[1]["深度思考"], "关")

    def test_thinking_runaway_twice_stops(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            put(iss.files["播客"], POD)(iss.dir)
            put(iss.files["网页"], json.dumps(WEB))(iss.dir)
            runaway = usage(1000, 64000, think=64003)
            chat = FakeChat([("写这一期的视频稿", "", "length", runaway), ("写这一期的视频稿", "", "length", runaway)])
            d, fd = self.driver(iss, chat, [(2, 6, BW.WAITING, None, None)])
            self.assertEqual(d.run(), 2)
            self.assertEqual(len(chat.got), 2)
            self.assertFalse(iss.p(BW.STORYBOARD).exists())

    def test_after_runaway_same_kind_fix_starts_without_thinking(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            for k in BW.KINDS:
                put(iss.files[k], POD if k == "播客" else json.dumps(SB if k == "视频" else WEB))(iss.dir)
            m0 = BW.Mimo(iss.dir, chat=FakeChat([("x", "", "length", usage(1000, 64000, think=64003))]))
            with self.assertRaises(BW.ThinkingRunaway):
                m0.call(6, "写视频稿", "s", "x", 64000, 0.4)
            write_check(iss.dir, [{"名字": "视频分镜", "要改": ["✗ 要改：数字 650 找不到"]}, {"名字": "稿子", "要改": ["第 1 行 [口吻] 我"]}])
            chat = FakeChat([("按程序检查的问题改播客稿", POD, "stop"), ("按程序检查的问题改视频稿", json.dumps(SB), "stop")])
            d, fd = self.driver(iss, chat, [(2, 7, BW.WAITING, None, None), (0, None, None, None, None)])
            self.assertEqual(d.run(), 0)
            self.assertEqual([g["thinking"] for g in chat.got], [None, "disabled"])     # 播客照旧开思考，视频直接关

    def test_long_call_dropped_by_server_counts_as_runaway(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            put(iss.files["播客"], POD)(iss.dir)
            put(iss.files["网页"], json.dumps(WEB))(iss.dir)
            clock = iter([0.0, 900.6, 1000.0, 1072.0])
            orig = BW.time.time
            BW.time.time = lambda: next(clock)
            try:
                chat = FakeChat([("写这一期的视频稿", RuntimeError("IncompleteRead(178 bytes read)"), None),
                                 ("写这一期的视频稿", json.dumps(SB), "stop")])
                d, fd = self.driver(iss, chat, [(2, 6, BW.WAITING, None, None), (0, None, None, None, None)])
                self.assertEqual(d.run(), 0)
            finally:
                BW.time.time = orig
            self.assertEqual([g["thinking"] for g in chat.got], [None, "disabled"])
            calls = json.loads(iss.p(BW.USAGE).read_text(encoding="utf-8"))["调用"]
            self.assertIn("不知道", calls[0]["用量"])

    def test_short_transport_error_is_not_runaway(self):
        rec = {"结果": "失败：IncompleteRead(10 bytes read)", "秒": 30}
        self.assertFalse(BW.thinking_ran_out(rec))
        self.assertTrue(BW.thinking_ran_out({"结果": "失败：IncompleteRead(178 bytes read)", "秒": 900.6}))
        self.assertFalse(BW.thinking_ran_out({"结果": "失败：HTTP 400: bad", "秒": 900.6}))

    def test_long_answer_truncation_is_not_treated_as_runaway(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            put(iss.files["播客"], POD)(iss.dir)
            put(iss.files["网页"], json.dumps(WEB))(iss.dir)
            chat = FakeChat([("写这一期的视频稿", "{半截", "length", usage(1000, 64000, think=20000))])
            d, fd = self.driver(iss, chat, [(2, 6, BW.WAITING, None, None)])
            self.assertEqual(d.run(), 2)                    # 正文太长被截断：不关思考重来，停下
            self.assertEqual(len(chat.got), 1)

    def test_resume_after_runaway_rewrites_without_thinking(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            put(iss.files["播客"], POD)(iss.dir)
            put(iss.files["网页"], json.dumps(WEB))(iss.dir)
            # 上一个进程：写视频稿那次思考用光了上限，程序停了（还没来得及关思考重写）
            first = FakeChat([("写这一期的视频稿", "", "length", usage(1000, 64000, think=64003))])
            m0 = BW.Mimo(iss.dir, chat=first)
            with self.assertRaises(BW.ThinkingRunaway):
                m0.call(6, "写视频稿", "s", "写这一期的视频稿", 64000, 0.4)
            (iss.dir / "logs").mkdir(exist_ok=True)
            (iss.p(BW.RECORD)).write_text(json.dumps({"次数": {"write_视频": 1}, "经过": []}), encoding="utf-8")
            chat = FakeChat([("写这一期的视频稿", json.dumps(SB), "stop")])
            d, fd = self.driver(iss, chat, [(2, 6, BW.WAITING, None, None), (0, None, None, None, None)])
            self.assertEqual(d.run(), 0)
            self.assertEqual([g["thinking"] for g in chat.got], ["disabled"])
            self.assertEqual(json.loads(iss.p(BW.USAGE).read_text(encoding="utf-8"))["合计"]["次数"], 2)

    def test_storyboard_precheck_rounds_then_fd(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            put(iss.files["播客"], POD)(iss.dir)
            put(iss.files["网页"], json.dumps(WEB))(iss.dir)
            bad1 = (1, "分镜检查没过：核对失败\n  ✗ 要改：「a」里的数字 650 在它引用的事件卡原文（n3）里找不到\n"
                       "  ✗ 要改：「b」带数字（x），但没写 ref\n")
            bad2 = (1, "分镜检查没过：触发词对不上旁白\n  ✗ 要改：qwen.claim.show：「x」在「千问」章的旁白里找不到\n")
            chat = FakeChat([("写这一期的视频稿", json.dumps(SB), "stop"),
                             ("按程序检查的问题改视频稿", json.dumps(SB), "stop"), ("按程序检查的问题改视频稿", json.dumps(SB), "stop")])
            d, fd = self.driver(iss, chat, [(2, 6, BW.WAITING, None, None), (0, None, None, None, None)], sb=[bad1, bad2])
            self.assertEqual(d.run(), 0)
            fixes = [g["user"] for g in chat.got if "按程序检查的问题改视频稿" in g["user"]]
            self.assertEqual(len(fixes), 2)
            self.assertIn("没写 ref", fixes[0])                  # 第一轮把两条都交回去
            self.assertIn("旁白里找不到", fixes[1])
            log = json.loads(iss.p(BW.SB_LOG).read_text(encoding="utf-8"))["每一次检查"]
            self.assertEqual([x["过了"] for x in log], [False, False, True])
            self.assertEqual(log[0]["种类"], {"数字在引用的事件卡原文里找不到": 1, "带数字却没写 ref": 1})
            self.assertEqual(d.count("sb_fix"), 2)

    def test_sb_rounds_base_restarts_count(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            for k in BW.KINDS:
                put(iss.files[k], POD if k == "播客" else json.dumps(WEB))(iss.dir)
            (iss.dir / "logs").mkdir(exist_ok=True)
            iss.p(BW.RECORD).write_text(json.dumps({"次数": {"sb_fix": 3}, "经过": []}), encoding="utf-8")
            bad = (1, "分镜检查没过：触发词对不上旁白\n  ✗ 要改：c1 在旁白里找不到\n")
            write_check(iss.dir, [{"名字": "视频分镜", "要改": ["✗ 要改：c1 在旁白里找不到"]},
                                  {"名字": "稿子", "要改": ["第 1 行 [口吻] x"]}])
            chat = FakeChat([("按程序检查的问题改播客稿", POD, "stop")] + [("按程序检查的问题改视频稿", json.dumps(SB), "stop")] * 3)
            fd = FakeFd(iss.dir, [(2, 7, BW.WAITING, None, None), (0, None, None, None, None)])
            sbq = [bad, bad, bad]
            d = BW.Driver(iss, BW.Mimo(iss.dir, chat=chat), fd_runner=fd, sel_inputs=lambda: ("", ""), rerun=lambda n: [],
                          sb_runner=lambda: sbq.pop(0) if sbq else (0, "分镜检查通过"), sb_base=3)
            self.assertEqual(d.run(), 0)
            # 新计法：fd 那一轮改分镜算第 1 轮，预查再改 2 轮，一共 3 轮；播客、分镜在同一轮一起交回
            self.assertEqual(sum(1 for g in chat.got if "按程序检查的问题改视频稿" in g["user"]), 3)
            self.assertEqual(sum(1 for g in chat.got if "按程序检查的问题改播客稿" in g["user"]), 1)
            self.assertEqual(d.sb_used(), 3)

    def test_snapshot_before_review(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            for k in BW.KINDS:
                put(iss.files[k], POD if k == "播客" else json.dumps(WEB))(iss.dir)
            snap = Path(t) / "_第7步过后"
            chat = FakeChat([("你是\"每日AI科技前沿简报\"", json.dumps({"must": [], "suggest": []}), "stop")])
            fd = FakeFd(iss.dir, [(2, 8, BW.WAITING, None, None), (0, None, None, None, None)])
            d = BW.Driver(iss, BW.Mimo(iss.dir, chat=chat), fd_runner=fd, sel_inputs=lambda: ("", ""), rerun=lambda n: [],
                          sb_runner=lambda: (0, ""), snap_before_review=str(snap))
            self.assertEqual(d.run(), 0)
            self.assertEqual((snap / "04_文稿" / "claude_播客_v3.md").read_text(encoding="utf-8"), POD)
            self.assertTrue(iss.p(BW.REVIEW).exists())

    def test_storyboard_rounds_capped_then_fd_stops_without_more_calls(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            put(iss.files["播客"], POD)(iss.dir)
            put(iss.files["网页"], json.dumps(WEB))(iss.dir)
            bad = (1, "分镜检查没过：核对失败\n  ✗ 要改：「a」里的数字 650 在它引用的事件卡原文（n3）里找不到\n")
            chat = FakeChat([("写这一期的视频稿", json.dumps(SB), "stop")] +
                            [("按程序检查的问题改视频稿", json.dumps(SB), "stop")] * 3)
            write_check(iss.dir, [{"名字": "视频分镜", "要改": ["✗ 要改：「a」里的数字 650 找不到"]}])
            d, fd = self.driver(iss, chat, [(2, 6, BW.WAITING, None, None), (2, 7, BW.WAITING, None, None)], sb=[bad] * 4)
            self.assertEqual(d.run(), 2)
            self.assertEqual(sum(1 for g in chat.got if "按程序检查的问题改视频稿" in g["user"]), BW.SB_ROUNDS)
            self.assertIn("改满 3 轮", json.loads(iss.p(BW.MARKER).read_text(encoding="utf-8"))["结果"])

    def test_storyboard_problems_get_location_hints(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            card = {"event_id": "E001", "facts": [{"quote": "A said"}, {"quote": "B"}], "numbers": [{"quote": "3 units"}],
                    "who_said": [{"quote": "hello world"}]}
            (iss.dir / "03_事件卡").mkdir()
            iss.p(BW.CARDS).write_text(json.dumps([card]), encoding="utf-8")
            sb = dict(SB, facts={"n1.x": {"event": "E001", "field": "numbers", "index": 0, "check": "3 units"}})
            iss.p(BW.STORYBOARD).write_text(json.dumps(sb), encoding="utf-8")
            rows = BW.annotate_sb_problems(iss, ["✗ 要改：e.k：E001 facts[0] 里找不到「hello world」",
                                                 "✗ 要改：「a.b(zh)」里的数字 650 在它引用的事件卡原文（n1.x）里找不到",
                                                 "✗ 要改：别的问题"])
            self.assertIn("在 E001 who_said[0] 里", rows[0])
            self.assertIn("facts[0] 那一条的原文是「A said」", rows[0])
            self.assertIn('分镜里写成 "event": "E001", "field": "who_said", "index": 0（材料里的编号 W0）', rows[0])
            self.assertIn("摘句不用改", rows[0])
            self.assertIn("n1.x 指向 E001 numbers[0]，原文「3 units」", rows[1])
            self.assertEqual(rows[2], "✗ 要改：别的问题")

    def test_key_rules_are_verbatim_existing_lines(self):
        text = BW.key_rules_text()
        for kind, f, start in BW.KEY_RULES:
            self.assertIn(start, text)
            whole = (BW.ROOT / f).read_text(encoding="utf-8")
            line = [x.strip() for x in whole.splitlines() if x.strip().startswith(start)][0]
            self.assertIn("原文（%s）：%s" % (f, line), text)        # 原样摘，不改字
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            self.assertIn("材料一之二", BW.common_material(iss))
            rv = BW.review_task(iss, BW.task_sections(), {"播客": POD, "网页": "{}", "视频": "{}"})
            for k in ("出处写清是谁说的", "作者的观点不算到媒体头上", "不自己做加减、换算", "不写卡里没有的关联",
                      "并列的事不画成先后", "中文名的拼音要对"):
                self.assertIn(k, rv)

    def test_review_extra_check_only_in_review_and_verbatim(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            sec = BW.task_sections()
            rv = BW.review_task(iss, sec, {"播客": POD, "网页": "{}", "视频": "{}"})
            title, src = BW.REVIEW_EXTRA
            self.assertIn("7. " + title, rv)
            # 11-17 改：对不上摘录的先去抓取材料原文里核，核得到的不算必须改；原来那两句（一律算必须改、原始材料给不了）都不在了
            self.assertNotIn("一律算必须改", rv)
            self.assertNotIn("这一次给不了你", rv)
            self.assertIn("核得到的不算必须改", title)
            self.assertIn("材料原文里也核不到的才算必须改", rv)
            for f, start in src:
                line = [x.strip() for x in (BW.ROOT / f).read_text(encoding="utf-8").splitlines() if x.strip().startswith(start)][0]
                self.assertIn("原文（%s）：%s" % (f, line), rv)          # 原样摘
            self.assertNotIn(title, BW.common_material(iss))              # 写稿共用的材料里没有这一项
            self.assertNotIn(title, BW.write_task(iss, "网页", sec))

    def test_call_cap_stops_midway(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            chat = FakeChat([("写这一期的播客稿", POD, "stop"), ("写这一期的网页稿", json.dumps(WEB), "stop")])
            d, fd = self.driver(iss, chat, [(2, 6, BW.WAITING, None, None)], max_calls=2)
            self.assertEqual(d.run(), 2)
            self.assertEqual(len(chat.got), 2)
            self.assertFalse(iss.p(BW.STORYBOARD).exists())

    def test_review_not_written_by_backup_is_not_revised(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            put(BW.REVIEW, "必须改：1\n")(iss.dir)
            d, fd = self.driver(iss, FakeChat([]), [(2, 9, BW.WAITING, None, None)])
            self.assertEqual(d.run(), 2)

    def test_fd_command_uses_issue_dir_and_extra(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            d = BW.Driver(iss, BW.Mimo(iss.dir, chat=FakeChat([])), fd_extra=["--budget-usd", "0"], fd_runner=lambda: 0)
            cmd = d.fd_cmd()
            self.assertEqual(cmd[1:8], ["run", "--date", DAY, "--from", "4", "--until", "9"])
            self.assertEqual(cmd[-2:], ["--budget-usd", "0"])
            self.assertIn("--issue-dir", cmd)


class NoVideo(unittest.TestCase):
    """无视频（2026-11-17 加，--no-video／fd_开关.json"视频"写"关"）：只写、审、改播客和网页，不做分镜预查，每一次 ./fd 都带 FD_VIDEO=off。"""

    def driver(self, iss, chat, script, **kw):
        fd = FakeFd(iss.dir, script)

        def sb_runner():
            raise AssertionError("无视频时不该做分镜预查")
        d = BW.Driver(iss, BW.Mimo(iss.dir, chat=chat, **kw), fd_runner=fd, sel_inputs=lambda: ("选题系统提示", "候选事件……"),
                      rerun=lambda n: [], sb_runner=sb_runner, video=False)
        return d, fd

    def test_happy_path_only_podcast_and_web(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            write_check(iss.dir, [{"名字": "稿子", "要改": ["第 3 行 [口吻] 我 —— 只许开场自称一次"]},
                                  {"名字": "视频分镜", "要改": [], "不查": "视频：关，分镜不查"}])
            chat = FakeChat([
                ("写这一期的播客稿", POD, "stop"),
                ("写这一期的网页稿", json.dumps(WEB), "stop"),
                ("按程序检查的问题改播客稿", POD, "stop"),
                ("独立审读", json.dumps({"must": [{"where": "播客开场", "files": ["播客"], "fix": "改"},
                                              {"where": "两处", "files": ["视频"], "fix": "改"}]}, ensure_ascii=False), "stop"),
                ("按独立审读的意见改播客稿", '===处理===\n[{"条": "必须改 1", "怎么处理": "改了", "说明": "E001 F0"},'
                                       '{"条": "必须改 2", "怎么处理": "改了", "说明": "E001 F1"}]\n===稿子===\n' + POD + "===完===", "stop"),
                ("按独立审读的意见改网页稿", '===处理===\n[{"条": "必须改 2", "怎么处理": "改了", "说明": "E001 F1"}]\n'
                                       "===稿子===\n" + json.dumps(WEB) + "\n===完===", "stop"),
            ])
            script = [(2, 6, BW.WAITING, None, None), (2, 7, BW.WAITING, ["  - x"], None),
                      (2, 8, BW.WAITING, None, None), (2, 9, BW.WAITING, None, None), (0, None, None, None, None)]
            d, fd = self.driver(iss, chat, script)
            self.assertEqual(d.run(), 0)
            self.assertFalse(iss.p(BW.STORYBOARD).exists())                       # 没写分镜
            self.assertFalse(any("视频稿" in g["user"][-400:] for g in chat.got))   # 没有一次是写、改视频稿
            rv_user = [g["user"] for g in chat.got if "稿子不是你写的" in g["user"]][0]
            self.assertNotIn("# 指令：pipeline/prompts/写稿_视频v3", rv_user)        # 审读任务里没有视频指令、没有分镜稿
            self.assertNotIn("要审的视频稿", rv_user)
            self.assertIn("要审的播客稿", rv_user)
            self.assertIn("要审的网页稿", rv_user)
            self.assertIn(BW.NO_VIDEO_NOTE, rv_user)
            self.assertIn("每一项对两份稿子（播客、网页中英文）都要查", rv_user)
            self.assertNotIn("并列的事不画成先后", rv_user[rv_user.find("# 必查项"):rv_user.find("每一项对")])
            self.assertIn('"files": ["播客", "网页"]', rv_user)
            for g in chat.got:
                if "按独立审读的意见改" in g["user"] or "按程序检查的问题改" in g["user"]:
                    self.assertIn(BW.NO_VIDEO_NOTE, g["user"])
                    self.assertNotIn("# 指令：pipeline/prompts/写稿_视频v3", g["user"])
            # 写了"视频"的那条审读意见：这一期没有视频，按播客、网页两份都涉及
            handled = iss.p(BW.HANDLED).read_text(encoding="utf-8")
            self.assertIn("网页稿：改了", handled)
            self.assertNotIn("视频稿", handled)
            mk = json.loads(iss.p(BW.MARKER).read_text(encoding="utf-8"))
            self.assertIn("关", mk["视频"])
            self.assertEqual(mk["调用次数"], 6)

    def test_every_fd_call_carries_switch(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            got = []

            def fake_run(cmd, **kw):
                got.append(kw.get("env"))
                return mock.Mock(returncode=0)
            for video, want in ((False, "off"), (True, None)):
                d = BW.Driver(iss, BW.Mimo(iss.dir, chat=FakeChat([])), video=video)
                with mock.patch.object(BW.subprocess, "run", fake_run), mock.patch.dict(BW.os.environ, {}, clear=False):
                    BW.os.environ.pop("FD_VIDEO", None)
                    d._fd()
                env = got[-1]
                if want:
                    self.assertEqual(env["FD_VIDEO"], want)
                else:
                    self.assertIsNone(env)                 # 开视频：和加开关以前一样，不另给环境

    def test_storyboard_problem_from_fd_stops_without_calls(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            write_check(iss.dir, [{"名字": "视频分镜", "要改": ["✗ 要改：触发词「x」在旁白里找不到"]}])
            chat = FakeChat([])
            d, fd = self.driver(iss, chat, [(2, 7, BW.WAITING, ["  - x"], None)])
            self.assertEqual(d.run(), 2)
            self.assertEqual(chat.got, [])
            self.assertIn("FD_VIDEO=off 没传到 fd", json.loads(iss.p(BW.MARKER).read_text(encoding="utf-8"))["结果"])

    def test_on_write_with_both_drafts_present_stops(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            put(iss.files["播客"], POD)(iss.dir)
            put(iss.files["网页"], json.dumps(WEB))(iss.dir)
            d, fd = self.driver(iss, FakeChat([]), [(2, 6, BW.WAITING, None, None)])
            self.assertEqual(d.run(), 2)                   # 没有分镜不算"缺"：两份都在还停在写稿，就停下

    def test_main_no_video_sets_env_and_driver(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            seen = {}

            class FakeDriver:
                def __init__(self, *a, **kw):
                    seen.update(kw)
                    seen["FD_VIDEO"] = BW.os.environ.get("FD_VIDEO")

                def run(self):
                    return 0
            with mock.patch.object(BW, "Driver", FakeDriver), mock.patch.dict(BW.os.environ, {}, clear=False):
                BW.os.environ.pop("FD_VIDEO", None)
                self.assertEqual(BW.main(["run", "--date", DAY, "--issue-dir", str(iss.dir), "--no-video"]), 0)
            self.assertIs(seen["video"], False)
            self.assertEqual(seen["FD_VIDEO"], "off")
            seen.clear()
            with mock.patch.object(BW, "Driver", FakeDriver), mock.patch.dict(BW.os.environ, {}, clear=False):
                BW.os.environ.pop("FD_VIDEO", None)
                with mock.patch.object(BW, "video_switch", lambda: (True, "测试")):
                    BW.main(["run", "--date", DAY, "--issue-dir", str(iss.dir)])
            self.assertIs(seen["video"], True)
            self.assertIsNone(seen["FD_VIDEO"])

    def test_video_on_prompts_unchanged_shape(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            sec = BW.task_sections()
            self.assertEqual(BW.review_out(True), BW.REVIEW_OUT)
            on = BW.review_task(iss, sec, {"播客": POD, "网页": "{}", "视频": "{}"})
            self.assertEqual(on, BW.review_task(iss, sec, {"播客": POD, "网页": "{}", "视频": "{}"}, BW.KINDS))
            self.assertIn("要审的视频稿", on)
            self.assertNotIn(BW.NO_VIDEO_NOTE, on)
            for k in BW.KINDS:
                self.assertNotIn(BW.NO_VIDEO_NOTE, BW.write_task(iss, k, sec))
                self.assertNotIn(BW.NO_VIDEO_NOTE, BW.fix_task(iss, k, sec, ["x"], "稿", "第 7 步"))
                self.assertNotIn(BW.NO_VIDEO_NOTE, BW.revise_task(iss, k, sec, [], "稿"))

    def test_added_prompt_text_is_generic(self):
        """无视频多出来的提示字只说范围，不带哪一期的内容：没有英文词、事件号、数字（审读输出格式里的英文词都是原来就有的）。"""
        import re
        self.assertIsNone(re.search(r"[A-Za-z0-9]", BW.NO_VIDEO_NOTE))
        words = lambda t: set(re.findall(r"[A-Za-z_]+", t))          # noqa: E731
        self.assertLessEqual(words(BW.review_out(False)), words(BW.REVIEW_OUT))
        self.assertIsNone(re.search(r"\bE\d{3}\b", BW.review_out(False).replace("E002 的 body_zh", "")))



# Claude 写的审读意见（合成的，和真的一样分"## 必须改""## 建议改"，每条一个"### "）
CLAUDE_REVIEW = """必须改：3

# 2026-11-16 独立审读意见（示例）

- 审读人：示例

## 必须改

### 1. 播客开场把甲说成乙

- 原句：……
- 依据：E001 F0

### 2. 网页 E001 标题丢了限定词

- 原句：……

### 3. 视频第二章画面把并列画成先后

- 原句：……

## 建议改

### 1. 网页某处可以更顺（这一条不交给改稿）
"""


def han_pod(n):
    """一份播客稿：正文恰好 n 个汉字（章名、注释、语气表不算）。"""
    body = "甲" * n
    return "## 开场\n\n" + body + "\n\n<!-- 语气\n{\"开场\": \"calm and steady\"}\n-->\n"


class Takeover1117(unittest.TestCase):
    """11-17 加：Claude 写到一半倒下时 MiMo 接手；只交必须改；审读核材料原文；改稿后数播客字数。"""

    def driver(self, iss, chat, script, video=False, **kw):
        fd = FakeFd(iss.dir, script)

        def sb_runner():
            raise AssertionError("这几个测试不做分镜预查")
        d = BW.Driver(iss, BW.Mimo(iss.dir, chat=chat, **kw), fd_runner=fd, sel_inputs=lambda: ("选题系统提示", "候选事件……"),
                      rerun=lambda n: [], sb_runner=sb_runner, video=video)
        return d, fd

    def marker(self, iss):
        return json.loads(iss.p(BW.MARKER).read_text(encoding="utf-8"))

    def test_review_task_has_materials_only_in_review(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            mats = [{"id": "s1", "name": "示例来源", "title": "T", "text": "founder of Example Corp said hello"}]
            put("03_事件卡/材料/E001.json", json.dumps(mats, ensure_ascii=False))(iss.dir)
            sec = BW.task_sections()
            rv = BW.review_task(iss, sec, {"播客": POD, "网页": "{}"}, BW.KINDS_NO_VIDEO)
            i = rv.find("## 抓取材料原文")
            self.assertGreater(i, rv.find("## 要审的网页稿"))                     # 附在任务最后、稿子后面
            self.assertIn("### E001（03_事件卡/材料/E001.json）", rv)
            self.assertIn(json.dumps(mats, ensure_ascii=False, separators=(",", ":")), rv)   # 原样
            self.assertNotIn("抓取材料原文（", BW.common_material(iss))              # 共同材料不变（缓存）
            self.assertNotIn("founder of Example", BW.write_task(iss, "播客", sec))
            # 没存下材料的卡写明"没有"
            (iss.dir / "03_事件卡" / "材料" / "E001.json").rename(iss.dir / "挪开.json")
            self.assertIn("E001：没有存下这张卡的材料", BW.review_task(iss, sec, {"播客": POD, "网页": "{}"}, BW.KINDS_NO_VIDEO))

    def test_revise_task_only_must_wording(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            sec = BW.task_sections()
            for video in (True, False):
                task = BW.revise_task(iss, "播客", sec, [{"_label": "必须改 1"}], POD, video)
                mine = task[task.find("# 你这一次的任务：按独立审读"):task.find("## 审读意见")]
                self.assertNotIn("建议改的，能直接替换", mine)       # 程序自己写的这段不再叫它采纳建议改
                self.assertIn("这一次只交必须改的几条", mine)
                # 任务说明_云端.md 第 9 步那一段原样摘（里面有"建议改的……就采纳"），这次不改原文；交过去的条目里没有建议改
                self.assertIn(sec["改稿"], task)

    def test_suggest_not_sent_to_revise(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            for k in BW.KINDS_NO_VIDEO:
                put(iss.files[k], POD if k == "播客" else json.dumps(WEB))(iss.dir)
            chat = FakeChat([
                ("独立审读", json.dumps({"must": [{"where": "必须改的位置甲", "files": ["播客"], "fix": "改"}],
                                     "suggest": [{"where": "建议改的位置乙", "files": ["播客", "网页"], "fix": "压缩"}],
                                     "better": [{"where": "可以更好的位置丙", "files": ["网页"]}]}, ensure_ascii=False), "stop"),
                ("按独立审读的意见改播客稿", '===处理===\n[{"条": "必须改 1", "怎么处理": "改了", "说明": "E001 F0"}]\n'
                                       "===稿子===\n" + POD + "===完===", "stop"),
            ])
            script = [(2, 8, BW.WAITING, None, None), (2, 9, BW.WAITING, None, None), (0, None, None, None, None)]
            d, fd = self.driver(iss, chat, script)
            self.assertEqual(d.run(), 0)
            rev = [g["user"] for g in chat.got if "按独立审读的意见改" in g["user"]]
            self.assertEqual(len(rev), 1)                                         # 网页只有建议改、可以更好：不花一次调用
            self.assertIn("必须改的位置甲", rev[0])
            self.assertNotIn("建议改的位置乙", rev[0])
            self.assertNotIn("建议改 1", iss.p(BW.HANDLED).read_text(encoding="utf-8"))
            self.assertEqual(self.marker(iss)["审读"], "MiMo（备用）：另起一次调用")

    def test_claude_review_revised_without_rereview(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            for k in BW.KINDS:
                put(iss.files[k], POD if k == "播客" else json.dumps(WEB))(iss.dir)
            put(BW.REVIEW, CLAUDE_REVIEW)(iss.dir)
            chat = FakeChat([
                ("按独立审读的意见改播客稿", '===处理===\n[{"条": "必须改 1", "怎么处理": "改了", "说明": "E001 F0"}]\n'
                                       "===稿子===\n" + POD + "===完===", "stop"),
                ("按独立审读的意见改网页稿", '===处理===\n[{"条": "必须改 2", "怎么处理": "改了", "说明": "E001 F1"}]\n'
                                       "===稿子===\n" + json.dumps(WEB) + "\n===完===", "stop"),
            ])
            script = [(2, 9, BW.WAITING, None, None), (0, None, None, None, None)]
            d, fd = self.driver(iss, chat, script)
            self.assertEqual(d.run(), 0)
            self.assertFalse(any("稿子不是你写的" in g["user"] for g in chat.got))   # 没有重审
            self.assertEqual(len(chat.got), 2)
            pod = [g["user"] for g in chat.got if "按独立审读的意见改播客稿" in g["user"]][0]
            self.assertIn("### 1. 播客开场把甲说成乙", pod)                       # 那一条原样交过去
            self.assertNotIn("### 2. 网页", pod)
            self.assertNotIn("这一条不交给改稿", pod)                              # 建议改不交
            web = [g["user"] for g in chat.got if "按独立审读的意见改网页稿" in g["user"]][0]
            self.assertIn("### 2. 网页 E001 标题丢了限定词", web)
            handled = iss.p(BW.HANDLED).read_text(encoding="utf-8")
            self.assertIn("只涉及视频分镜：这一期不出视频", handled)                # 第 3 条只涉及视频，无视频时不改
            self.assertIn("播客稿：改了", handled)
            mk = self.marker(iss)
            self.assertIn("Claude（备用接手前写好的）", mk["审读"])
            self.assertEqual(mk["谁写的"], {"播客": "Claude（备用接手前写好的）", "网页": "Claude（备用接手前写好的）"})
            self.assertEqual(mk["接手时"]["审读意见"], "接手前就在（Claude 写的）")
            self.assertNotIn("播客开场", json.dumps(mk, ensure_ascii=False))     # 记号里没有审读的字

    def test_claude_review_count_mismatch_stops(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            for k in BW.KINDS_NO_VIDEO:
                put(iss.files[k], POD if k == "播客" else json.dumps(WEB))(iss.dir)
            put(BW.REVIEW, CLAUDE_REVIEW.replace("必须改：3", "必须改：4"))(iss.dir)
            chat = FakeChat([])
            d, fd = self.driver(iss, chat, [(2, 9, BW.WAITING, None, None)])
            self.assertEqual(d.run(), 2)
            self.assertEqual(chat.got, [])
            self.assertIn("对不上", self.marker(iss)["结果"])
            n, items = BW.claude_review_items(CLAUDE_REVIEW, BW.KINDS)
            self.assertEqual((n, len(items)), (3, 3))
            self.assertEqual([i["_files"] for i in items], [["播客"], ["网页"], ["视频"]])

    def test_claude_used_fix_round_mimo_gets_one_more(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            for k in BW.KINDS_NO_VIDEO:
                put(iss.files[k], POD if k == "播客" else json.dumps(WEB))(iss.dir)
            # 接手前：fd 第 7 步已记了两版没过的稿子（Claude 写一版、交回改一版，还没过）
            put("logs/fd_state.json", json.dumps({"步骤": {"check": {"状态": BW.WAITING, "附加": {"没过时的产出指纹": ["a", "b"]}}},
                                                  "运行记录": [{"结果": "停在第 7 步：示例"}]}, ensure_ascii=False))(iss.dir)
            write_check(iss.dir, [{"名字": "网页数字", "要改": ["E001 的 3 找不到"]}])
            chat = FakeChat([("按程序检查的问题改网页稿", json.dumps(WEB), "stop")])
            script = [(2, 7, BW.WAITING, None, None), (0, None, None, None, None)]
            d, fd = self.driver(iss, chat, script)
            self.assertEqual(d.run(), 0)
            self.assertEqual(len(chat.got), 1)                                    # MiMo 接手再给了一轮
            mk = self.marker(iss)
            self.assertEqual(mk["接手时"]["第 7 步没过几版"], 2)
            self.assertTrue(any("Claude 已用掉 fd 的交回改一轮" in x and "用了 1 轮" in x for x in mk["交回改"]))

    def test_partial_write_who_wrote(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            put(iss.files["播客"], POD)(iss.dir)                                   # Claude 写好了播客，网页还没写
            chat = FakeChat([("写这一期的网页稿", json.dumps(WEB), "stop")])
            script = [(2, 6, BW.WAITING, None, None), (2, 7, BW.WAITING, None, None)]
            write_check(iss.dir, [{"名字": "稿子", "要改": ["script_check 没给出结果：示例"]}])
            d, fd = self.driver(iss, chat, script)
            self.assertEqual(d.run(), 2)
            self.assertEqual(len(chat.got), 1)
            self.assertNotIn("写这一期的播客稿", chat.got[0]["user"])
            mk = self.marker(iss)
            self.assertEqual(mk["谁写的"], {"播客": "Claude（备用接手前写好的）", "网页": "MiMo"})
            self.assertEqual(mk["接手时"]["已有的稿子"], ["播客"])
            self.assertEqual(mk["要人看"], [])

    def test_podcast_length_out_of_range_needs_look_no_extra_call(self):
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            lo, hi, f = BW.podcast_range(iss)
            for k in BW.KINDS_NO_VIDEO:
                put(iss.files[k], han_pod(lo + 10) if k == "播客" else json.dumps(WEB))(iss.dir)
            for short, want_note in ((lo - 1, True), (lo, False)):
                with tempfile.TemporaryDirectory() as t2:
                    import shutil
                    d2 = Path(t2) / DAY
                    shutil.copytree(iss.dir, d2)
                    iss2 = BW.Issue(DAY, str(d2))
                    chat = FakeChat([
                        ("独立审读", json.dumps({"must": [{"where": "开场", "files": ["播客"], "fix": "改"}],
                                             "suggest": [{"where": "全篇压缩到四千字以下", "files": ["播客"]}]},
                                            ensure_ascii=False), "stop"),
                        ("按独立审读的意见改播客稿", '===处理===\n[{"条": "必须改 1", "怎么处理": "改了", "说明": "E001 F0"}]\n'
                                               "===稿子===\n" + han_pod(short) + "===完===", "stop"),
                    ])
                    script = [(2, 8, BW.WAITING, None, None), (2, 9, BW.WAITING, None, None), (0, None, None, None, None)]
                    d, fd = self.driver(iss2, chat, script)
                    self.assertEqual(d.run(), 0)
                    self.assertEqual(len(chat.got), 2)                            # 出了区间也不再调 MiMo
                    mk = self.marker(iss2)
                    self.assertEqual(mk["播客字数"]["改稿后"], short)
                    self.assertEqual(mk["播客字数"]["区间"], [lo, hi])
                    self.assertEqual(bool(mk["要人看"]), want_note, short)
                    if want_note:
                        self.assertIn("不在《%s》写的总长" % f, mk["要人看"][0])

    def test_podcast_range_read_from_prompt_verbatim(self):
        """区间照这一期播客写稿指令的原文读（工作日、周六、周日各一份），不在程序里写数。"""
        for day in ("2026-11-16", "2026-11-14", "2026-11-15"):
            with tempfile.TemporaryDirectory() as t:
                d = Path(t) / day
                d.mkdir()
                iss = BW.Issue(day, str(d))
                lo, hi, f = BW.podcast_range(iss)
                line = [x for x in BW.prompt_text(f).splitlines() if x.startswith("总长")][0]
                self.assertIn(format(lo, ","), line)
                self.assertIn(format(hi, ","), line)
                self.assertLess(lo, hi)

    def test_han_count_like_script_check(self):
        text = ("# 标题不算\n\n> 备注不算\n\n## 开场\n\n今天 AI 很忙。\n\n<!-- 注释不算 -->\n"
                "甲：对谈的甲乙标签不算，正文算\n乙：好\n")
        self.assertEqual(BW.han_count(text), len("今天很忙") + len("对谈的甲乙标签不算正文算") + len("好"))

    def test_new_prompt_text_is_generic(self):
        """这次加、改的提示字只说做法，不带哪一期的内容（没有事件号、人名、数字）。"""
        import re
        with tempfile.TemporaryDirectory() as t:
            iss = make_issue(t)
            task = BW.revise_task(iss, "播客", BW.task_sections(), [], POD, False)
            new = [BW.REVIEW_EXTRA[0], task[task.find("# 你这一次的任务：按独立审读"):task.find("## 审读意见")],
                   BW.materials_text(iss).splitlines()[0]]
        for x in new:
            x = re.sub(r"第 \d 步|03_事件卡|最多 3 篇", "", x)     # 步号、目录名、"每张卡最多 3 篇"不算内容
            self.assertIsNone(re.search(r"\bE\d{3}\b|\d", x), x[:80])


if __name__ == "__main__":
    unittest.main()
