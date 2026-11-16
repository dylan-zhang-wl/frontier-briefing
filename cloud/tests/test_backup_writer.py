"""cloud/backup_writer.py（备用写稿）的单元测试：不联网、不调 MiMo、不跑 fd。

MiMo 用假回答，fd 用假的"跑一轮"（按剧本写 logs/fd_state.json、返回退出码），测驱动逻辑：
停在哪一步做什么、每一步最多交回改一次、超上限就停、用量每次都记、审读意见第一行和条数一致。

    python3 -m unittest discover -s cloud/tests -v
"""
import json
import sys
import tempfile
import unittest
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

    def __call__(self, model, system, user, max_tokens, temperature):
        self.got.append({"system": system, "user": user, "max_tokens": max_tokens})
        for i, (needle, reply, finish) in enumerate(self.replies):
            if needle in user:
                self.replies.pop(i)
                if isinstance(reply, Exception):
                    raise reply
                return {"content": reply, "usage": usage(), "finish": finish, "model": model}
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
        items = BW.review_items({"must": [{"where": "a"}], "suggest": [{"where": "b", "files": ["视频", "瞎写"]}]})
        self.assertEqual(items[0]["_files"], list(BW.KINDS))
        self.assertEqual(items[1]["_files"], ["视频"])
        self.assertEqual([i["_label"] for i in items], ["必须改 1", "建议改 1"])

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
    def driver(self, iss, chat, script, **kw):
        fd = FakeFd(iss.dir, script)
        sel = lambda: ("选题系统提示", "候选事件……")          # noqa: E731
        d = BW.Driver(iss, BW.Mimo(iss.dir, chat=chat, **kw), fd_runner=fd, sel_inputs=sel, rerun=lambda n: [])
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
            self.assertIn("停下", json.loads(iss.p(BW.MARKER).read_text(encoding="utf-8"))["结果"])

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


if __name__ == "__main__":
    unittest.main()
