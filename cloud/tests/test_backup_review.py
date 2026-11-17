"""cloud/backup_review.py（MiMo 备用审片）的单元测试：不联网、不调 MiMo。

MiMo 用假回答；期目录是临时目录里造的一期（内容全是自造的，和真实哪一期都无关）。测的是：
程序判的几项（第 2 项"视频：关"跳过算做完、第 3/5/40 项照放行判定）、"立即"由程序定、放行只看"立即"、
"判断"只准三个词（不对的改成多半真念错；数字、不同音的程序复核）、两个文件的格式（放行判定的读法读得懂）、
只写允许的文件、视频开着不审、MiMo 全没成时不放行。

    python3 -m unittest discover -s cloud/tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "release"))
sys.path.insert(0, str(HERE.parents[1] / "pipeline"))
import backup_review as BR  # noqa: E402
import backup_writer as BW  # noqa: E402
import gate  # noqa: E402

DAY = "2026-11-18"          # 星期三：工作日版
STEP_KEYS = [k for k, _ in gate.STEPS]

# 自造的一期：两块播客。第 1 块转写里有一处同音字（会话→绘画）、一处不同音（传奇→禅奇）；第 2 块有数字变了（3.8→3.0）、英文名拼法（Feldman→Fjellman）
BLOCK1 = "今天先说会话的事。这是一个传奇故事。"
HYP1 = "今天先说绘画的事这是一个禅奇故事"
BLOCK2 = "新版本叫 Gemini 3.8。创始人 Andrew Feldman 说了话。"
HYP2 = "新版本叫Gemini 3.0创始人Andrew Fjellman说了话"
POD = "## 开场\n\n%s\n\n## 结尾\n\n%s\n" % (BLOCK1, BLOCK2)
CARDS = [{"event_id": "E001", "title_zh": "示例", "title_en": "Example",
          "facts": [{"text_zh": "甲说了话", "text_en": "A spoke", "quote": "创始人 Andrew Feldman 说了话"}],
          "numbers": [], "who_said": [{"who": "Andrew Feldman", "quote": "Andrew Feldman said hello"}], "sources": []}]


def usage(i=1000, o=200, cached=0, think=50):
    return {"prompt_tokens": i, "completion_tokens": o, "total_tokens": i + o,
            "prompt_tokens_details": {"cached_tokens": cached}, "completion_tokens_details": {"reasoning_tokens": think}}


def wj(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def wt(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def qc_block(n, ch, start, secs, ref, hyp):
    import tts_qc as Q
    r = Q.check(ref, hyp)
    return {"块": n, "章": ch, "原稿": ref, "开始秒": start, "秒数": secs, "选用第几条": 2, "共录几条": 2,
            "各条": [{"第几条": 1, "转写": ref, "差异": []}, {"第几条": 2, "转写": hyp, "差异": r["差异"]}]}


def make_issue(root, video_off=True, accept_fail=False):
    d = Path(root) / DAY
    steps = {}
    for k in STEP_KEYS:
        steps[k] = {"状态": "做完", "说明": "", "附加": {}}
    steps["voice"]["附加"] = {"播客": "主声音", "视频旁白": "不出（视频：关）", "决定": {"用备用": False, "原因": ""}}
    steps["web"]["附加"] = {"播客": "05_配音/播客_v3_带音效"}
    if video_off:
        steps["video"] = {"状态": "跳过", "说明": "视频：关（MiMo 备用那天按规矩不出视频）", "附加": {"视频开关": "关"}}
        steps["web2"] = {"状态": "跳过", "说明": "视频：关，第 13 步的网页就是成品", "附加": {"视频开关": "关"}}
    wj(d / "logs/fd_state.json", {"步骤": steps, "运行记录": [{"开始": "2026-11-18 04:20:00 GMT", "命令": "fd run --date %s" % DAY,
                                                          "结果": "跑完", "结束": "2026-11-18 06:00:00 GMT"}]})
    wj(d / "logs/验收.json", {"没过": ["手机视图横滚"] if accept_fail else [], "提醒": []})
    wt(d / "00_调度报告.md", "# %s · 工作日版 · 调度报告\n\n- **这一期齐了**\n" % DAY)
    wt(d / "04_文稿/claude_播客_v3.md", POD)
    wj(d / "04_文稿/claude_网页.json", {"sections": [], "notes": []})
    wt(d / "审读意见.md", "必须改：0\n")
    wt(d / "审读处理.md", "# 审读处理\n")
    wt(d / "自检.md", "# 自检\n")
    wt(d / "10_网页v3/index.html", "<html></html>")
    wt(d / "05_配音/播客_v3_带音效/episode.mp3", "x")
    wt(d / "每日运行日志_云端.md", "- %s 跑完\n" % DAY)
    wj(d / "花费.json", {"合计美元": {"Gemini": 0.2}})
    wj(d.parent / "月度账本/2026-11.json", {"条目": [{"服务": "Gemini", "美元": 1.0}], "上限美元（Gemini 配音）": 8.0})
    wj(d / "03_事件卡/cards_写稿用.json", CARDS)
    human = {"整集": {"需人工复听块数": 0, "音高把关": {"仍超出的块": [], "语速标出的块": [], "允许偏差半音": 1.5},
                     "音色把关": {"音色需人工听的块": []},
                     "时长把关": {"配完按实际": {"时长分钟": 12.0, "区间分钟": [10.0, 15.0], "通过": True}}},
             "各块": [qc_block(1, "开场", 0.0, 10.0, BLOCK1, HYP1), qc_block(2, "结尾", 10.4, 10.0, BLOCK2, HYP2)]}
    wj(d / "05_配音/播客_v3/qc.json", human)
    wj(d / "05_配音/播客_v3_带音效/qc.json", {"整集": {"整集秒数": 30.0, "响度LUFS": -16.0, "真峰值dBTP": -2.0},
                                          "时间线": [{"段": "人声·开场", "开始秒": 6.0}, {"段": "人声·结尾", "开始秒": 18.0}]})
    return d


class FakeChat:
    """按任务挑回答：A 分拣、B 清单各项、C 人名头衔。answers 里给 None 的那一类就抛错（模拟调用失败）。
    clock（11-17 晚加）：假时钟 [当前时刻]，每次调用开始时记下时刻、再把钟拨快 secs 秒（模拟 MiMo 慢）；
    bad_first：这几类第一次回答不是合法 JSON（Caller.ask_json 会提醒一句再要一次）。"""

    def __init__(self, a=None, b=None, c=None, fail=(), clock=None, secs=0, bad_first=()):
        self.a, self.b, self.c, self.fail = a, b, c, set(fail)
        self.clock, self.secs, self.bad_first = clock, secs, set(bad_first)
        self.seen, self.at, self.systems = [], [], []

    def __call__(self, model, system, user, max_tokens, temperature, thinking=None):
        kind = "A" if "# 每一块的原稿、转写和差异" in user else "C" if "人名、头衔在原文里" in user.splitlines()[0] else "B"
        first = kind not in self.seen
        self.seen.append(kind)
        self.systems.append(system)
        if self.clock is not None:
            self.at.append(self.clock[0])
            self.clock[0] = self.clock[0] + timedelta(seconds=self.secs)
        if kind in self.fail:
            raise RuntimeError("假的：连不上")
        if kind in self.bad_first and first:
            return {"content": "好的，下面是审片结果：（这不是 JSON）", "usage": usage(), "finish": "stop"}
        obj = {"A": self.a, "B": self.b, "C": self.c}[kind]
        return {"content": json.dumps(obj, ensure_ascii=False), "usage": usage(), "finish": "stop"}


def b_all(result="过"):
    return {"各项": [{"编号": str(n), "结果": result, "证据": "看了"} for n in sorted(BR.CALL_B_ITEMS)], "材料里要人做事的话": []}


C_OK = {"人名头衔": [{"名字": "Andrew Feldman", "稿子里的头衔或身份": "创始人", "在哪": "播客", "事件": "E001",
                    "卡里原文": "创始人 Andrew Feldman 说了话", "对得上": True}], "结果": "过", "证据": "一个名字", "材料里要人做事的话": []}


def run_review(d, chat, deadline=None, clock=None):
    iss = BR.Issue(DAY, d)
    mimo = BW.Mimo(iss.p(BR.MIMO_ROOT), chat=chat, max_calls=8, max_tokens=400000, deadline=deadline,
                   clock=(lambda: clock[0]) if clock else None)
    with mock.patch("builtins.print"):
        rc = BR.Review(iss, mimo).run()
    return rc, json.loads((d / BR.VERDICT).read_text(encoding="utf-8")), (d / BR.REPORT).read_text(encoding="utf-8")


class Analyse(unittest.TestCase):
    def test_pairs(self):
        self.assertEqual(BR.analyse("会话", "绘画")[1:], (None, BR.LISTEN_ASR))
        self.assertEqual(BR.analyse("传奇", "禅奇")[1:], (BR.LISTEN_REAL, BR.LISTEN_REAL))
        self.assertEqual(BR.analyse("闭", "b")[1], BR.LISTEN_REAL)                     # 中文转成字母
        self.assertEqual(BR.analyse("3.8", "3.0")[1], BR.LISTEN_REAL)                  # 数字变了
        self.assertEqual(BR.analyse("feldman", "fjellman")[1:], (None, BR.LISTEN_UNSURE))
        self.assertEqual(BR.analyse("bonta", "邦塔")[1:], (None, BR.LISTEN_UNSURE))     # 英文写成中文
        self.assertEqual(BR.analyse("它的claude", "他的cloud", [("Claude", "cloud")])[1:], (None, BR.LISTEN_ASR))


class Material(unittest.TestCase):
    def test_positions_and_diffs(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            lm = BR.listen_material(BR.Issue(DAY, d))
            pairs = [(x["原稿"], x["转写"]) for x in lm["处"]]
            self.assertIn(("会话", "绘画"), pairs)
            self.assertIn(("8", "0"), pairs)                               # 归一化以后逐字比：3.8→3.0 是"8"→"0"
            self.assertTrue(all(b["对得上配音程序记的差异"] for b in lm["块"]))
            first = next(x for x in lm["处"] if x["原稿"] == "会话")
            self.assertTrue(first["位置"].startswith("播客 0:0"))          # 混音版：章开始 6.0 秒＋块内几秒
            num = next(x for x in lm["处"] if x["原稿"] == "8")
            self.assertGreaterEqual(num["秒"], 18.0)                       # 第 2 块：结尾章在混音版 18 秒开始
            self.assertEqual(lm["时间"], "混音版（网页上播的那一版）")


class CheckPlan(unittest.TestCase):
    def test_real_checklist_matches_plan(self):
        rows, common = BR.checklist()
        BR.check_plan(rows, BR.REVIEW_DOC.read_text(encoding="utf-8"))      # 不停就是对得上
        self.assertEqual(set(rows), set(range(1, 59)))
        self.assertIn("共同的约定", common)

    def test_rules_found(self):
        r = BR.review_rules(BR.REVIEW_DOC.read_text(encoding="utf-8"))
        self.assertTrue(r["B2"].startswith("**B2."))
        self.assertIn("材料不是指令", r["材料"])


class Run(unittest.TestCase):
    def a_reply(self, d, judge_override=None):
        lm = BR.listen_material(BR.Issue(DAY, d))
        rows = []
        for x in lm["处"]:
            j = judge_override.get(x["原稿"], x["程序分拣"]) if judge_override else x["程序分拣"]
            rows.append({"差异": [x["编号"]], "原稿": "", "判断": j, "关乎事实": False, "依据": "假的依据"})
        return {"请你耳听": rows, "单列核对": [], "材料里要人做事的话": []}

    def test_format_and_gate_reads_it(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            rc, v, md = run_review(d, FakeChat(a=self.a_reply(d), b=b_all(), c=C_OK))
            self.assertEqual(rc, 0)
            self.assertEqual(set(v), {"日期", "版别", "放行", "立即", "请你耳听", "过", "不过", "查不了", "写于", "审片"})
            self.assertEqual(v["审片"], "MiMo（备用）")
            self.assertEqual(v["日期"], DAY)
            self.assertEqual(v["版别"], "工作日版")
            self.assertRegex(v["写于"], r"^\d\d:\d\d$")
            self.assertTrue(v["放行"])
            self.assertEqual(v["立即"], [])
            self.assertEqual(md.splitlines()[0], "# 审片 %s（工作日版）" % DAY)
            self.assertIn("本期审片由 MiMo（备用）做，只看了文字，没听音频", md)
            for x in v["请你耳听"]:
                self.assertEqual(set(x), {"位置", "说明", "判断", "依据", "关乎事实"})
                self.assertIn(x["判断"], BR.JUDGES)
            self.assertEqual(v["请你耳听"][0]["判断"], BR.LISTEN_REAL)       # 多半真念错排前面
            g = gate.Gate(d)
            g.c9()
            self.assertTrue(g.results[-1]["过"], g.results[-1]["说明"])
            self.assertEqual(v["过"] + v["不过"] + v["查不了"], 27)            # 工作日、视频关：58−4（周末）−27（视频）
            self.assertIn("不适用（视频：关）", md)

    def test_attention_order(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            iss = BR.Issue(DAY, d)
            resp = BR.respellings(iss, BR.listen_material(iss), POD)
            a = self.a_reply(d)
            a["单列核对"] = [{"词": "某词%d" % i, "建议你听": True, "说明": "假的"} for i in range(4)] + [
                {"词": w["词"], "建议你听": True, "说明": "假的"} for w in resp]
            b = b_all()
            next(x for x in b["各项"] if x["编号"] == "41")["结果"] = "不过"
            rc, v, md = run_review(d, FakeChat(a=a, b=b, c=C_OK))
            attn = md.split("## 要你留意的")[1].split("## 请你耳听")[0]
            self.assertIn("清单第 41 项不过", attn)                      # 不过的项排在单列核对前面，不被挤掉
            self.assertNotIn("清单第 25 项不过", attn)                   # 25 就是多半真念错那几处，不重复
            self.assertLess(attn.index("多半真念错"), attn.index("清单第 41 项不过"))

    def test_judge_words_corrected_and_floor(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            # MiMo 把"传奇→禅奇"（不同音）判成转写听错、把"会话→绘画"写成认不出的词
            a = self.a_reply(d, {"传": BR.LISTEN_ASR, "会话": "念错了"})
            rc, v, md = run_review(d, FakeChat(a=a, b=b_all(), c=C_OK))
            by = {x["说明"].split("→")[0]: x for x in v["请你耳听"]}
            j = {k: x["判断"] for k, x in by.items()}
            self.assertTrue(any("传" in k and val == BR.LISTEN_REAL for k, val in j.items()), j)
            self.assertTrue(any("会话" in k and val == BR.LISTEN_REAL for k, val in j.items()), j)
            self.assertIn("改成“多半真念错”", md)
            num = [x for x in v["请你耳听"] if "“8”" in x["说明"]]
            self.assertEqual(num[0]["判断"], BR.LISTEN_REAL)

    def test_release_follows_now_only(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t, accept_fail=True)          # 验收没过 → 第 40 项立即
            rc, v, md = run_review(d, FakeChat(a=self.a_reply(d), b=b_all(), c=C_OK))
            self.assertFalse(v["放行"])
            self.assertEqual([x["编号"] for x in v["立即"]], ["40"])
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            rc, v, md = run_review(d, FakeChat(a=self.a_reply(d), b=b_all("不过"), c=dict(C_OK, 结果="不过")))
            self.assertTrue(v["放行"])                    # MiMo 判的项再多不过也不挡放行
            self.assertGreater(v["不过"], 5)

    def test_video_skip_counts_as_done_but_plain_skip_does_not(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            res = BR.program_items(BR.Issue(DAY, d), POD)
            self.assertEqual(res[2][0], BR.PASS)
            st = json.loads((d / "logs/fd_state.json").read_text(encoding="utf-8"))
            st["步骤"]["video"]["说明"] = "视频旁白没配成"
            wj(d / "logs/fd_state.json", st)
            rc, v, md = run_review(d, FakeChat(a={}, b=b_all(), c=C_OK))
            self.assertFalse(v["放行"])
            self.assertEqual(v["立即"][0]["编号"], "2")
            self.assertIn("这期还没出齐", md.splitlines()[0])

    def test_only_allowed_files_written(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            before = BR.snapshot(d)
            rc, v, md = run_review(d, FakeChat(a=self.a_reply(d), b=b_all(), c=C_OK))
            after = BR.snapshot(d)
            changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
            self.assertTrue(changed)
            self.assertTrue(all(BR.allowed(k) for k in changed), changed)
            self.assertTrue(any(k.startswith("logs/备用审片_MiMo/") for k in changed))

    def test_stray_write_is_caught(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            chat = FakeChat(a=self.a_reply(d), b=b_all(), c=C_OK)

            def sneaky(*a, **k):
                (d / "自检.md").write_text("改了", encoding="utf-8")
                return chat(*a, **k)
            rc, v, md = run_review(d, sneaky)
            self.assertEqual(rc, 1)

    def test_all_mimo_fail_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            rc, v, md = run_review(d, FakeChat(fail={"A", "B", "C"}))
            self.assertFalse(v["放行"])
            self.assertEqual(v["立即"][-1]["编号"], "审片")
            self.assertTrue(v["请你耳听"])                 # 程序自己分拣的照样写
            self.assertTrue(all(x["判断"] in BR.JUDGES for x in v["请你耳听"]))

    def test_one_call_fails_items_cant(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            rc, v, md = run_review(d, FakeChat(a=self.a_reply(d), c=C_OK, fail={"B"}))
            self.assertTrue(v["放行"])
            self.assertIn("查不了：MiMo 调用 B 没成", md)

    def test_quote_not_in_cards_downgrades(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            c = json.loads(json.dumps(C_OK))
            c["人名头衔"][0]["卡里原文"] = "卡里没有的一句话"
            rc, v, md = run_review(d, FakeChat(a=self.a_reply(d), b=b_all(), c=c))
            self.assertIn("| 11 | 查不了 |", md)


class BackupDayGate(unittest.TestCase):
    """合并 feat/mimo-release 以后（11-17）：备用那天放行判定第 9 条多了"MiMo 备用""MiMo 审片"两类备注，
    没开自动放行时第 9 条又会因为 gate.NO_AUTO_RELEASE 那一句不过。审片程序写完结论用放行判定的读法自查，要认得这两件事。"""

    def backup_day(self, d, auto=None):
        wj(d / "备用写稿.json", {"写稿": "MiMo（备用）", "结果": "第 4–9 步做完",
                                "视频": "关：这一期不出视频，只写了播客和网页（FD_VIDEO=off）"})
        if auto is not None:
            wj(d / "Claude不能用.json", {"原因": "登录失效", "认法": "原话", "哪一步": ["写稿", "审片"], "连续第几天": 1,
                                         "自动放行": auto, "写于": "2026-11-18T04:20:00Z"})

    def record(self, d):
        return json.loads((d / BR.RECORD).read_text(encoding="utf-8"))["gate 读法自查"]

    def kinds(self, d):
        g = gate.Gate(d)
        g.c9()
        r = g.results[-1]
        return r, [n.get("类") for n in r["备注"]]

    def test_no_autorelease_counts_as_match(self):
        for auto in (None, False):                      # Claude不能用.json 没有、写着 false：都不自动放行
            with tempfile.TemporaryDirectory() as t:
                d = make_issue(t)
                self.backup_day(d, auto)
                rc, v, md = run_review(d, FakeChat(a=Run.a_reply(None, d), b=b_all(), c=C_OK))
                self.assertEqual(rc, 0)
                self.assertTrue(v["放行"])
                r, kinds = self.kinds(d)
                self.assertFalse(r["过"])
                self.assertEqual(r["说明"], gate.NO_AUTO_RELEASE)
                self.assertIn(gate.BACKUP_KIND, kinds)
                self.assertIn(gate.MIMO_REVIEW_KIND, kinds)
                self.assertEqual(kinds.count(gate.LISTEN), len(v["请你耳听"]))
                self.assertGreater(len(kinds), len(v["请你耳听"]))      # 备注总数比请你耳听多：只数"请你耳听"那类才对得上
                self.assertTrue(self.record(d)["对得上"], self.record(d))

    def test_autorelease_passes(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            self.backup_day(d, True)
            rc, v, md = run_review(d, FakeChat(a=Run.a_reply(None, d), b=b_all(), c=C_OK))
            self.assertEqual(rc, 0)
            r, kinds = self.kinds(d)
            self.assertTrue(r["过"], r["说明"])
            self.assertEqual(kinds[:2], [gate.BACKUP_KIND, gate.MIMO_REVIEW_KIND])
            self.assertTrue(self.record(d)["对得上"])

    def test_not_released_still_matches(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t, accept_fail=True)          # 第 40 项立即 → 结论不放行；第 9 条两条理由都在
            self.backup_day(d, None)
            rc, v, md = run_review(d, FakeChat(a=Run.a_reply(None, d), b=b_all(), c=C_OK))
            self.assertEqual(rc, 0)
            self.assertFalse(v["放行"])
            self.assertTrue(self.record(d)["对得上"])

    def test_other_reason_still_caught(self):
        """第 9 条除了"没开自动放行"还有别的理由（这里是结论日期写错）：不能当成对得上。"""
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            self.backup_day(d, None)
            v = {"日期": "2026-11-17", "版别": "工作日版", "放行": True, "立即": [], "请你耳听": [], "过": 1, "不过": 0,
                 "查不了": 0, "写于": "05:00", "审片": BR.REVIEWER}
            wj(d / BR.VERDICT, v)
            ok, why = BR.gate_check(BR.Issue(DAY, d), v)
            self.assertFalse(ok)
            self.assertIn(gate.NO_AUTO_RELEASE, why)
            self.assertIn("日期", why)

    def test_listen_count_mismatch_caught(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            self.backup_day(d, True)
            x = {"位置": "播客 0:01", "说明": "“甲”→“乙”", "判断": BR.LISTEN_REAL, "依据": "假的", "关乎事实": False}
            wj(d / BR.VERDICT, {"日期": DAY, "版别": "工作日版", "放行": True, "立即": [], "请你耳听": [x],
                                "过": 1, "不过": 0, "查不了": 0, "写于": "05:00", "审片": BR.REVIEWER})
            ok, _ = BR.gate_check(BR.Issue(DAY, d), {"放行": True, "请你耳听": [x, x]})
            self.assertFalse(ok)


T0 = datetime(2026, 11, 18, 6, 0, tzinfo=timezone.utc)
B_TODAY = sorted(n for n in BR.CALL_B_ITEMS if n not in BR.DAYS_ONLY)       # 工作日审的 B 那几项


class OrderAndMissed(unittest.TestCase):
    """11-17 晚：调用顺序 A → C → B；没查成的写进“MiMo没查成”；放行判定第 9 条按开关挡不挡。
    假时钟：每次调用把钟拨快 850 秒（接近 MiMo 约 900 秒断开），截止是开始后 40 分钟（2,400 秒）。
    照原来的顺序 A → B →（B 重给 JSON）→ C：A 0–850、B 850–1700、重给 1700–2550、C 2550 开始时已过截止，C 不跑——
    就是 11-17 云端试跑的样子。新顺序 C 在 850 秒就跑了，被挤掉的是 B 的重给。"""

    def slow(self, d, secs=850, minutes=40, bad_first=("B",), **kw):
        clock = [T0]
        chat = FakeChat(a=Run.a_reply(None, d), b=b_all(), c=C_OK, clock=clock, secs=secs, bad_first=bad_first, **kw)
        rc, v, md = run_review(d, chat, deadline=T0 + timedelta(minutes=minutes), clock=clock)
        return chat, rc, v, md

    def test_c_runs_before_deadline_when_a_b_slow_and_b_retries(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            chat, rc, v, md = self.slow(d)
            self.assertEqual(rc, 0)
            self.assertEqual(chat.seen, ["A", "C", "B"])                     # B 的重给 JSON 到 2550 秒已过截止，没开
            c_at = chat.at[chat.seen.index("C")]
            self.assertLess(c_at, T0 + timedelta(minutes=40))
            self.assertEqual(c_at, T0 + timedelta(seconds=850))              # 紧跟 A，不等 B
            self.assertIn("| 11 | 过 |", md)
            missed = v[gate.MIMO_MISSED]
            self.assertEqual([x["项"] for x in missed], B_TODAY)            # 没查成的是 B 那几项，没有第 11 项、没有周末才审的 9、17
            self.assertTrue(all(x["为什么"] == "时间到了" for x in missed), missed)
            self.assertEqual(next(x for x in missed if x["项"] == 18)["是什么"], "审读必须改都处理了")

    def test_b_retry_still_follows_b_and_shares_cache_prefix(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            chat, rc, v, md = self.slow(d, minutes=60)                       # 时间够：B 重给一次也赶得上
            self.assertEqual(chat.seen, ["A", "C", "B", "B"])
            self.assertNotIn(gate.MIMO_MISSED, v)                            # 全查成了：结论和以前一样，没有这一栏
            self.assertEqual(set(v), {"日期", "版别", "放行", "立即", "请你耳听", "过", "不过", "查不了", "写于", "审片"})
            self.assertEqual(chat.systems[1], chat.systems[2])               # C、B 系统提示一字不差：前缀缓存照旧
            self.assertIn("审片B_清单各项：回答不是合法的 JSON，提醒一句再要一次", md)

    def test_missed_c_written_and_gate_blocks_or_not(self):
        """C 真没跑（时间到了）：结论里记第 11 项；开关开着第 9 条不过，关着照旧放行；两种情况审片程序的自查都对得上。"""
        nums = sorted(B_TODAY + [11])
        for blocks in (True, False):
            with tempfile.TemporaryDirectory() as t, mock.patch.object(gate, "MIMO_REVIEW_INCOMPLETE_BLOCKS", blocks):
                d = make_issue(t)
                BackupDayGate.backup_day(None, d, True)                     # 备用那天、设定是自动放行
                chat, rc, v, md = self.slow(d, secs=2500, bad_first=())     # A 0–2500：C、B 开始时都已过 40 分钟
                self.assertEqual(rc, 0, blocks)                              # 写完自查对得上（开关开着时第 9 条不过也算）
                self.assertEqual(chat.seen, ["A"])
                self.assertTrue(v["放行"])                                  # “放行”照旧只看“立即”
                missed = v[gate.MIMO_MISSED]
                self.assertEqual([x["项"] for x in missed], nums)
                self.assertEqual(next(x for x in missed if x["项"] == 11),
                                 {"项": 11, "是什么": "人名、头衔在原文里", "为什么": "时间到了"})
                self.assertIn("| 11 | 查不了 |", md)
                g = gate.Gate(d)
                g.c9()
                r = g.results[-1]
                kinds = [n.get("类") for n in r["备注"]]
                self.assertIn(gate.MIMO_MISSED_KIND, kinds)                  # 开关开着、关着都记备注
                if blocks:
                    self.assertFalse(r["过"])
                    self.assertEqual(r["说明"], "MiMo 审片第 %s 项没查成：等你看过再手动放行" % "、".join(map(str, nums)))
                else:
                    self.assertTrue(r["过"], r["说明"])
                rec = json.loads((d / BR.RECORD).read_text(encoding="utf-8"))
                self.assertTrue(rec["gate 读法自查"]["对得上"], rec["gate 读法自查"])
                att = md.split("## 要你留意的")[1].split("## 请你耳听")[0]
                self.assertIn("**MiMo 审片第 %s 项没查成**" % "、".join(map(str, nums)), att)
                self.assertIn("第 11 项 人名、头衔在原文里：时间到了", att)
                self.assertLess(att.index("没查成"), att.index("多半真念错"))   # 排在请你耳听前面
                self.assertIn("没查成", md.split("**一句话结论**")[1].splitlines()[0])
                self.assertIn("等你看过再手动放行" if blocks else "这几项要你自己看一眼", md)

    def test_gate_check_single_item(self):
        """只有第 11 项没查成：第 9 条的理由带项名；只因为这条（和没开自动放行）不过，自查算对得上；多一条别的理由就不算。"""
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            BackupDayGate.backup_day(None, d, None)                         # 没开自动放行：两句设定理由都在
            v = {"日期": DAY, "版别": "工作日版", "放行": True, "立即": [], "请你耳听": [], "过": 1, "不过": 0, "查不了": 1,
                 "写于": "05:00", "审片": BR.REVIEWER,
                 gate.MIMO_MISSED: [{"项": 11, "是什么": "人名、头衔在原文里", "为什么": "时间到了"}]}
            wj(d / BR.VERDICT, v)
            ok, why = BR.gate_check(BR.Issue(DAY, d), v)
            self.assertTrue(ok, why)
            self.assertEqual(why, gate.NO_AUTO_RELEASE + "；MiMo 审片第 11 项（人名、头衔在原文里）没查成：等你看过再手动放行")
            wj(d / BR.VERDICT, dict(v, 日期="2026-11-17"))
            ok, why = BR.gate_check(BR.Issue(DAY, d), v)
            self.assertFalse(ok)

    def test_a_fails_counts_25(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            rc, v, md = run_review(d, FakeChat(b=b_all(), c=C_OK, fail={"A"}))
            self.assertEqual([x["项"] for x in v[gate.MIMO_MISSED]], [25])
            self.assertIn("程序按 B2 自己分拣", v[gate.MIMO_MISSED][0]["为什么"])
            self.assertTrue(v["请你耳听"])                                 # 程序自己分拣的照写

    def test_bad_json_twice_reason(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            chat = FakeChat(a=Run.a_reply(None, d), b=b_all(), c=C_OK)

            def twice_bad(*a, **k):                                         # B 两次都回一段说明文字
                r = chat(*a, **k)
                return dict(r, content="还是一段说明文字，没有 JSON") if chat.seen[-1] == "B" else r
            rc, v, md = run_review(d, twice_bad)
            self.assertEqual(chat.seen, ["A", "C", "B", "B"])
            self.assertEqual([x["项"] for x in v[gate.MIMO_MISSED]], B_TODAY)
            self.assertEqual({x["为什么"] for x in v[gate.MIMO_MISSED]}, {"两次回答都不是合法的 JSON"})

    def test_why_short(self):
        self.assertEqual(BR.why_short(BW.Stop("已过 2026-11-17 15:06（UTC），不再新开 MiMo 调用")), "时间到了")
        self.assertEqual(BR.why_short(BW.Stop("MiMo 调用已到上限 8 次，不再调用")), "调用次数到上限")
        self.assertEqual(BR.why_short(BW.Stop("MiMo 用量已到上限 400,000 token，不再调用")), "用量到上限")
        self.assertEqual(BR.why_short(BW.CallFailed("MiMo 调用失败（审片C_人名头衔）：连不上")), "调用失败")
        self.assertEqual(BR.why_short(ValueError("Expecting value: line 1 column 1 (char 0)")), "两次回答都不是合法的 JSON")

    def test_item_names(self):
        rows, _ = BR.checklist()
        self.assertEqual(BR.item_name(rows[11]), "人名、头衔在原文里")
        self.assertEqual(BR.item_name(rows[25]), "数字、序数、改过的词、专名念对")
        self.assertEqual(BR.item_name(rows[7]), "\"补前一天\"例外没被误用")
        self.assertTrue(all("；" not in BR.item_name(rows[n]) and "[" not in BR.item_name(rows[n]) for n in rows))


class ItemOne(unittest.TestCase):
    """第 1 项“当天这期在不在”：MiMo 备用写稿那天不要 自检.md（11-17 云端试跑因此误判不过、一句话结论写了“网页、播客不齐”），
    改核播客稿、网页稿、配音、网页；Claude 写稿那天照旧。"""

    def mimo_day(self, d):
        BackupDayGate.backup_day(None, d, True)
        (d / "自检.md").rename(d / "自检_挪开.md")
        wt(d / "05_配音/播客_v3/episode.mp3", "x")

    def test_mimo_day_no_selfcheck_passes(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            self.mimo_day(d)
            r, ev = BR.program_items(BR.Issue(DAY, d), POD)[1]
            self.assertEqual(r, BR.PASS, ev)
            self.assertIn("不要 自检.md", ev)
            rc, v, md = run_review(d, FakeChat(a=Run.a_reply(None, d), b=b_all(), c=C_OK))
            self.assertIn("网页、播客都在", md)

    def test_mimo_day_checks_what_should_be_there(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            self.mimo_day(d)
            (d / "04_文稿/claude_网页.json").rename(d / "网页稿_挪开.json")
            (d / "05_配音/播客_v3/episode.mp3").rename(d / "人声_挪开.mp3")
            r, ev = BR.program_items(BR.Issue(DAY, d), POD)[1]
            self.assertEqual(r, BR.FAIL)
            self.assertEqual(ev, "缺：04_文稿/claude_网页.json；05_配音/播客_v3/episode.mp3")

    def test_claude_day_unchanged(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            (d / "自检.md").rename(d / "自检_挪开.md")
            r, ev = BR.program_items(BR.Issue(DAY, d), POD)[1]
            self.assertEqual((r, ev), (BR.FAIL, "缺：自检.md"))                 # 和改之前一字不差
            (d / "自检_挪开.md").rename(d / "自检.md")
            r, ev = BR.program_items(BR.Issue(DAY, d), POD)[1]
            self.assertEqual(ev, "网页 index.html、自检.md、播客 mp3（episode.mp3）、当天运行日志都在；视频文件不要求（视频：关）")

    def test_marker_not_mimo_counts_as_claude(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            wj(d / "备用写稿.json", {"写稿": "Claude"})
            (d / "自检.md").rename(d / "自检_挪开.md")
            self.assertEqual(BR.program_items(BR.Issue(DAY, d), POD)[1], (BR.FAIL, "缺：自检.md"))


class CardsText(unittest.TestCase):
    def test_quotes_and_newlines_found(self):
        cards = [{"facts": [{"quote": 'He said "hello"\nand left'}]}]
        flat = BR.cards_text(cards)
        self.assertIn('Hesaid"hello"andleft', flat)               # 照抄的原文带直引号、换行也找得到
        self.assertNotIn("\\", flat)


class Cli(unittest.TestCase):
    def test_video_on_writes_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            d = make_issue(t)
            before = BR.snapshot(d)
            with mock.patch.dict(os.environ, {"FD_VIDEO": "on"}), mock.patch("builtins.print"):
                rc = BR.main(["run", "--date", DAY, "--issue-dir", str(d)])
            self.assertEqual(rc, 2)
            self.assertEqual(before, BR.snapshot(d))


if __name__ == "__main__":
    unittest.main()
