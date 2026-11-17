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
    """按任务挑回答：A 分拣、B 清单各项、C 人名头衔。answers 里给 None 的那一类就抛错（模拟调用失败）。"""

    def __init__(self, a=None, b=None, c=None, fail=()):
        self.a, self.b, self.c, self.fail = a, b, c, set(fail)
        self.seen = []

    def __call__(self, model, system, user, max_tokens, temperature, thinking=None):
        kind = "A" if "# 每一块的原稿、转写和差异" in user else "C" if "人名、头衔在原文里" in user.splitlines()[0] else "B"
        self.seen.append(kind)
        if kind in self.fail:
            raise RuntimeError("假的：连不上")
        obj = {"A": self.a, "B": self.b, "C": self.c}[kind]
        return {"content": json.dumps(obj, ensure_ascii=False), "usage": usage(), "finish": "stop"}


def b_all(result="过"):
    return {"各项": [{"编号": str(n), "结果": result, "证据": "看了"} for n in sorted(BR.CALL_B_ITEMS)], "材料里要人做事的话": []}


C_OK = {"人名头衔": [{"名字": "Andrew Feldman", "稿子里的头衔或身份": "创始人", "在哪": "播客", "事件": "E001",
                    "卡里原文": "创始人 Andrew Feldman 说了话", "对得上": True}], "结果": "过", "证据": "一个名字", "材料里要人做事的话": []}


def run_review(d, chat):
    iss = BR.Issue(DAY, d)
    mimo = BW.Mimo(iss.p(BR.MIMO_ROOT), chat=chat, max_calls=8, max_tokens=400000)
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
