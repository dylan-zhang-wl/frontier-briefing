#!/usr/bin/env python3
"""视频分镜数值字段检查（video3_storyboard.check_values）的测试（2026-11-03 加）。

11-03 bill.yield 把 {"zh": "2.08 美元"} 写进了 bar_shrink 的 from.value，播放器读不出数字，柱子塌成一块空玻璃、数字没出来；
分镜检查当时没拦住。这里查：当数字读的字段写成字、带引号、没写，当字显示的写成裸数字，都算"要改"；往期好的分镜不误报；
播放器（site/v3/video3.js）里每个把字段换算成数字的模板都在 NUM_FIELDS 里（以后加模板忘了登记，这一条会失败）。
同日补：配图露脸的提醒（check_relations）把国内外（contrast）章也算进来，一章一张配图都没有（标志小签不算）就提醒；
第 7 步时配图还没生成、被 structure 暂时去掉的图按分镜里写了算（Photos 一组）。
11-05 补：时间轨相邻日子挨得太近只提醒（check_timeline_gaps，经 structure 打出来），和播放器 tlSpread 用同一个间隔（TimelineGaps 一组；
  最后一条用本机 node 跑播放器里的 tlSpread，没有 node 就跳过）。
11-06 补（视频版式修理）：计数模板 tally 的州名核对（Tally：事件卡里没有的州名、和计数不是同一处原文的州名都拦下）；
  画面检查（Screen：按"画面上真有东西"算空档、章首主角、时间轨被打断，按字数估时也能跑；11-06 原件的已知空档都要报出来）；
  旁白数字、等级上没上画面（SpokenFacts）；帖子卡头像里的标志不溢出（Avatar：库里每个标志逐个算，和 video3.js 的 avatarFit 同一组数）；
  新图位编进播放器数据（Compile：要点卡题图、时间轨小图、计数模板的州界、关键帧总览要截的空档）。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python site/tools/test_video3_storyboard.py        # 全部通过时退出码为 0
不调用任何模型，只读项目里的文件（往期分镜、video3.js），不写。
"""
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import video3_storyboard as SB  # noqa: E402

LAB = lambda zh, en, *ref: {"zh": zh, "en": en, "ref": list(ref)}  # noqa: E731


def sb_with(*blocks):
    return {"chapters": [{"id": "bill", "kind": "story", "blocks": [copy.deepcopy(b) for b in blocks]}]}


def problems(*blocks):
    return SB.check_values(sb_with(*blocks))


# 11-03 原样：数字和单位写在 value 里，label 只写了季度名
YIELD_BAD = {"type": "bar_shrink", "id": "yield", "head": LAB("每 1 美元算力换回的收入", "Revenue per $1 of compute", "e002.yield"),
             "from": {"value": LAB("2.08 美元", "$2.08", "e002.yield"), "label": LAB("第二季度", "Q2", "e002.rev")},
             "to": {"value": LAB("1.72 美元", "$1.72", "e002.yield"), "label": LAB("第三季度", "Q3", "e002.rev")}}
# 改好的写法（和 10-31 money.raise 一样）：value 是数字，label 是带单位的字
YIELD_OK = {"type": "bar_shrink", "id": "yield", "head": YIELD_BAD["head"],
            "from": {"value": 2.08, "label": LAB("第二季度 2.08 美元", "Q2 $2.08", "e002.yield")},
            "to": {"value": 1.72, "label": LAB("第三季度 1.72 美元", "Q3 $1.72", "e002.yield")}}


class BarShrink(unittest.TestCase):
    def test_1103_text_in_value(self):
        out = problems(YIELD_BAD)
        self.assertEqual(len(out), 2, out)
        self.assertIn("bar_shrink/yield 的 from.value", out[0])
        self.assertIn("bar_shrink/yield 的 to.value", out[1])
        for m in out:
            self.assertIn("「bill」", m)
            self.assertIn("只写数字本身", m)
            self.assertIn("label", m)

    def test_fixed_passes(self):
        self.assertEqual(problems(YIELD_OK), [])

    def test_quoted_number(self):          # 播放器读得出 "2.08"，但核数字时会漏掉
        b = copy.deepcopy(YIELD_OK)
        b["from"]["value"] = "2.08"
        out = problems(b)
        self.assertEqual(len(out), 1)
        self.assertIn('写成了 "2.08"', out[0])

    def test_missing_value(self):
        b = copy.deepcopy(YIELD_OK)
        del b["to"]["value"]
        out = problems(b)
        self.assertEqual(len(out), 1)
        self.assertIn("to.value 没写", out[0])

    def test_done_optional(self):
        b = copy.deepcopy(YIELD_OK)
        self.assertEqual(problems(b), [])                    # 不写 done：不查
        b["done"] = {"value": 1.1, "label": LAB("已到账 1.1 美元", "$1.1 in", "x")}
        self.assertEqual(problems(b), [])
        b["done"]["value"] = LAB("1.1 美元", "$1.1", "x")
        self.assertIn("done.value", problems(b)[0])

    def test_bool_is_not_number(self):
        b = copy.deepcopy(YIELD_OK)
        b["to"]["value"] = True
        self.assertEqual(len(problems(b)), 1)


class OtherTemplates(unittest.TestCase):
    def test_twin_drop(self):
        b = {"type": "twin_drop", "id": "falls", "items": [{"name": LAB("甲", "A"), "value": -28.58}, {"name": LAB("乙", "B"), "value": "−29.22%"}]}
        out = problems(b)
        self.assertEqual(len(out), 1)
        self.assertIn("items 第 2 项的 value", out[0])
        self.assertIn("unit", out[0])

    def test_column_compare(self):
        b = {"type": "column_compare", "id": "growth", "items": [{"value": 144}, {"value": LAB("47%", "47%", "e002.rev")}]}
        out = problems(b)
        self.assertEqual(len(out), 1)
        self.assertIn("items 第 2 项的 value", out[0])

    def test_quota_bars(self):
        b = {"type": "quota_bars", "id": "price", "head": LAB("价格", "Price"), "stages": [{"label": LAB("一", "1"), "value": 30}, {"label": LAB("二", "2")}]}
        out = problems(b)
        self.assertEqual(len(out), 1)
        self.assertIn("stages 第 2 项的 value 没写", out[0])

    def test_compare_panel(self):
        ok = {"type": "compare_panel", "id": "eff", "head": LAB("效率", "Efficiency"), "kpi": {"value": LAB("48%", "48%", "x")},
              "bars": [{"label": LAB("甲", "A"), "value": 1.0}, {"label": LAB("乙", "B"), "value": 0.53}]}
        self.assertEqual(problems(ok), [])
        bad = copy.deepcopy(ok)
        bad["bars"][1]["value"] = 53                       # 条长要 0–1
        bad["kpi"]["value"] = 48                           # 大数字当字显示，裸数字显示成空白
        out = problems(bad)
        self.assertEqual(len(out), 2, out)
        self.assertTrue(any("bars 第 2 项的 value" in m and "0–1" in m for m in out))
        self.assertTrue(any("kpi.value" in m and "裸数字" in m for m in out))

    def test_particle_counter_text(self):
        self.assertEqual(problems({"type": "particle_counter", "id": "count", "value": {"zh": "5,000"}}), [])
        out = problems({"type": "particle_counter", "id": "count", "value": 5000})
        self.assertEqual(len(out), 1)
        self.assertIn("显示成空白", out[0])

    def test_timeline(self):
        ok = {"type": "timeline", "id": "dates", "ticks": [{"date": LAB("1 日", "1")}, {"date": LAB("2 日", "2")}]}
        self.assertEqual(problems(ok), [])                 # pos、wait 都可以不写
        bad = copy.deepcopy(ok)
        bad["ticks"][1]["pos"] = "0.5"
        bad["wait"] = {"label": LAB("等了", "waited"), "from": 0, "to": 1.5}
        out = problems(bad)
        self.assertEqual(len(out), 2, out)
        self.assertTrue(any("ticks 第 2 项的 pos" in m for m in out))
        self.assertTrue(any("wait.to" in m and "整数" in m for m in out))

    def test_scale(self):
        ok = {"type": "scale", "id": "rating", "bands": [{"label": LAB("A", "A")}, {"label": LAB("B", "B")}], "threshold": 1,
              "from": {"at": 0}, "to": {"at": 1}}
        self.assertEqual(problems(ok), [])
        bad = copy.deepcopy(ok)
        bad["threshold"] = "1"
        bad["to"]["at"] = LAB("BB", "BB")
        self.assertEqual(len(problems(bad)), 2)


class RealIssues(unittest.TestCase):
    """往期分镜（只读）：数值字段一处都不该报。"""

    def test_past_storyboards(self):
        n = 0
        for day in ("2026-10-31", "2026-11-01", "2026-11-02"):
            p = ROOT / "测试版" / day / "04_文稿" / "视频v3_分镜.json"
            if not p.exists():
                continue
            n += 1
            self.assertEqual(SB.check_values(SB.load(p)), [], day)
        if not n:
            self.skipTest("没有往期分镜")


SPLIT = {"type": "split", "id": "split", "left": {"head": LAB("国外", "World")}, "right": {"head": LAB("国内", "China"), "logos": ["alibaba"]},
         "left_items": [{"text": LAB("一", "one"), "from": "bill"}], "right_items": [{"text": LAB("二", "two"), "from": "bill"}]}
POST_IMG = {"type": "post_card", "id": "post", "text": LAB("原话", "quote"), "who": {"name": LAB("某人", "Someone")}, "image": "e049"}


def photo_warns(sb):
    return [w for w in SB.check_relations(sb)[1] if "一张配图都没有" in w]


class Photos(unittest.TestCase):
    """配图露脸（11-03 补）：国内外（contrast）章也查；一章一张配图都没有（标志不算）只提醒，不算要改。"""

    def test_contrast_logo_only(self):          # 11-03 原样：split 只挂了一个小标志
        sb = {"chapters": [{"id": "contrast", "kind": "contrast", "blocks": [copy.deepcopy(SPLIT)]}]}
        must, warn = SB.check_relations(sb)
        self.assertEqual(must, [])
        w = photo_warns(sb)
        self.assertEqual(len(w), 1, warn)
        self.assertIn("「contrast」是国内外那一章", w[0])
        self.assertIn("post_card", w[0])

    def test_contrast_with_post_image(self):
        sb = {"chapters": [{"id": "contrast", "kind": "contrast", "blocks": [copy.deepcopy(SPLIT), copy.deepcopy(POST_IMG)]}]}
        self.assertEqual(photo_warns(sb), [])
        self.assertEqual(SB.photo_moments(sb["chapters"][0]), (["e049"], []))

    def test_story_zero_images(self):
        sb = sb_with(YIELD_OK)
        w = photo_warns(sb)
        self.assertEqual(len(w), 1)
        self.assertIn("「bill」一张配图都没有", w[0])

    def test_pending_images_count(self):         # 第 7 步在配图之前：structure 暂时去掉的图按写了算
        sb = sb_with(YIELD_OK)
        SB.pending(sb, sb["chapters"][0], "e003.png")
        self.assertEqual(sb["_pending_images"], {"bill": ["e003"]})
        self.assertEqual(photo_warns(sb), [])

    def test_structure_records_pending(self):    # 真实的 11-03 分镜放进一个没有配图的空目录：只剩国内外章那一条
        p = ROOT / "测试版" / "2026-11-03" / "04_文稿" / "视频v3_分镜.json"
        if not p.exists():
            self.skipTest("没有 11-03 分镜")
        with tempfile.TemporaryDirectory() as d:
            sb = SB.load(p)
            SB.structure(sb, Path(d) / "2026-11-03")
            self.assertTrue(sb.get("_pending_images"), "配图都不在，structure 应记下暂时去掉的图")
            w = photo_warns(sb)
            self.assertEqual(len(w), 1, w)
            self.assertIn("「contrast」", w[0])

    def test_past_counts(self):                  # 往期（只读）：10-31 三章、11-01 一章、11-03 一章一张配图都没有
        want = {"2026-10-31": ["money", "security", "contrast"], "2026-11-01": ["contrast"], "2026-11-02": [],
                "2026-11-03": ["contrast"]}
        for day, ids in want.items():
            issue = ROOT / "测试版" / day
            p = issue / "04_文稿" / "视频v3_分镜.json"
            if not p.exists():
                continue
            sb = SB.load(p)
            SB.structure(sb, issue)
            got = [re.match(r"「(\w+)」", w).group(1) for w in photo_warns(sb)]
            self.assertEqual(got, ids, day)

    def test_split_cards_image_slot(self):   # 11-06 晚：split 两边的小卡能带题图了（播放器、检查、提醒三处一致）
        js = (ROOT / "site" / "v3" / "video3.js").read_text(encoding="utf-8")
        m = re.search(r"\n  TPL\.split = \{(.*?)\n  \};", js, re.S)
        self.assertIsNotNone(m)
        self.assertIn("imgUrl", m.group(1))
        self.assertNotIn("contrast", SB.TEMPLATES["image_card"]["kinds"])
        self.assertIn("split", SB.IMAGE_SLOTS)
        src = (TOOLS / "video3_storyboard.py").read_text(encoding="utf-8")
        self.assertNotIn("split 两边的卡片现在不能带图", src)


def tl(*pos, **kw):
    """一个 timeline 模板：pos 给 None 就是不写这一项。"""
    ticks = []
    for i, p in enumerate(pos):
        t = {"date": LAB("日子%d" % (i + 1), "Day %d" % (i + 1)), "at": "日子%d" % (i + 1)}
        if p is not None:
            t["pos"] = p
        ticks.append(t)
    return dict({"type": "timeline", "id": "wait", "ticks": ticks}, **kw)


def gap_warns(*blocks):
    return SB.check_timeline_gaps(sb_with(*blocks))


class TimelineGaps(unittest.TestCase):
    """时间轨相邻日子挨得太近（11-05 补，只提醒）：11-04 写了 0.96 和 1.0，两张标签叠成"11 月 4 日 月"。
    播放器（video3.js 的 tlSpread）会自动拉开，这里查分镜检查的提醒、和播放器用同一个间隔、拉开以后确实不叠。"""

    def test_1104_close_ticks(self):             # 11-04 原样：0、0.12、0.96、1.0
        w = gap_warns(tl(0.0, 0.12, 0.96, 1.0))
        self.assertEqual(len(w), 1, w)
        self.assertIn("「bill」timeline/wait", w[0])
        self.assertIn("第 1、2 个（日子1 → 日子2）只差 0.12", w[0])
        self.assertIn("第 3、4 个（日子3 → 日子4）只差 0.04", w[0])
        self.assertNotIn("第 2、3 个", w[0])
        self.assertIn("自动拉开", w[0])
        self.assertIn("wait", w[0])

    def test_spread_enough_or_no_pos(self):
        self.assertEqual(gap_warns(tl(0.0, 0.33, 0.67, 1.0)), [])
        self.assertEqual(gap_warns(tl(None, None, None)), [])           # 不写 pos：等分
        self.assertEqual(gap_warns(tl(0.4, 0.5, 0.6)), [])              # 只用了中间一段：拉满整条轨以后间隔 0.5
        self.assertEqual(gap_warns(tl(0.0, 0.2, 0.4, 0.6, 0.8, 1.0)), [])   # 正好 0.2，不提醒

    def test_seven_ticks_use_equal_split(self):  # 7 个日子放不下 0.2：按等分（1/6）算，等分的不提醒
        self.assertEqual(gap_warns(tl(*[i / 6 for i in range(7)])), [])
        self.assertEqual(len(gap_warns(tl(0, 0.1, 0.2, 0.3, 0.4, 0.5, 1.0))), 1)

    def test_backwards_pos(self):
        w = gap_warns(tl(0.0, 0.6, 0.5, 1.0))
        self.assertTrue(any("没按先后从小到大（第 3 个比前一个小）" in x for x in w), w)

    def test_not_other_templates(self):
        self.assertEqual(gap_warns(YIELD_OK), [])

    def test_structure_reports_it(self):          # 组装（video3_build.prepare）和第 7 步都打印 structure 的提醒：11-04 原件（只读）
        issue = ROOT / "测试版" / "2026-11-04"
        p = issue / "04_文稿" / "视频v3_分镜.json"
        if not p.exists():
            self.skipTest("没有 11-04 分镜")
        w = [x for x in SB.structure(SB.load(p), issue) if "timeline/" in x]
        self.assertEqual(len(w), 1, w)
        self.assertIn("「apple」timeline/wait", w[0])
        self.assertIn("11 月 4 日 → 12 月", w[0])

    def test_same_gap_as_renderer(self):
        js = (ROOT / "site" / "v3" / "video3.js").read_text(encoding="utf-8")
        m = re.search(r"var TL_GAP = ([\d.]+);", js)
        self.assertIsNotNone(m, "video3.js 里找不到 TL_GAP")
        self.assertEqual(float(m.group(1)), SB.TIMELINE_GAP)

    def test_renderer_spreads_ticks(self):        # 播放器的 tlSpread：顺序不变、两头拉满、相邻至少 TL_GAP（放不下时等分）
        node = shutil.which("node")
        if not node:
            self.skipTest("没有 node")
        js = (ROOT / "site" / "v3" / "video3.js").read_text(encoding="utf-8")
        fn = re.search(r"\n  function tlSpread\(p, gap\) \{.*?\n  \}\n", js, re.S)
        self.assertIsNotNone(fn, "video3.js 里找不到 tlSpread")
        cases = [[0, 0.12, 0.96, 1.0], [0, 0.301, 0.473, 0.645, 0.796, 1.0], [0.5, 0.4, 0.3], [0, 0, 0], [0.2, 0.25],
                 [0, 0.1, 0.2, 0.3, 0.4, 0.5, 1.0]]
        src = fn.group(0) + "\nconsole.log(JSON.stringify(%s.map(function (p) { return tlSpread(p, %s); })));" % (
            json.dumps(cases), SB.TIMELINE_GAP)
        out = json.loads(subprocess.run([node, "-e", src], capture_output=True, text=True, check=True).stdout)
        for p, u in zip(cases, out):
            self.assertEqual(len(u), len(p))
            self.assertAlmostEqual(u[0], 0, places=6)
            self.assertAlmostEqual(u[-1], 1, places=6)
            m = min(SB.TIMELINE_GAP, 1 / (len(p) - 1))
            for a, b in zip(u, u[1:]):
                self.assertGreaterEqual(b - a, m - 1e-6, (p, u))
        self.assertEqual([round(x, 3) for x in out[0]], [0, 0.2, 0.8, 1.0])   # 11-04：中间那段宽的匀出来


# ---------------------------------------------------------------- 11-06 补
FACTS_E003 = {   # 11-06 E003 的两条原文（摘要；测试只用到里面的州名和数字）
    "e003.vote": {"ev": "E003", "src": "s2", "text": "据 CNBC 汇总 Ballotpedia 的分析，10 个州共有 41 项地方投票措施，除一项外，选民全部支持限制措施或否决促开发措施。"},
    "e003.sites": {"ev": "E003", "src": "s2", "text": "OpenAI 今年 2 月告诉投资者……并已宣布在佐治亚州和俄亥俄州建设大型数据中心项目。 "
                                                  "has since announced massive data center projects in Georgia and Ohio."},
    "x.wv": {"ev": "E900", "src": "s1", "text": "Two projects are planned in West Virginia."},
}


def tally(**kw):
    b = {"type": "tally", "id": "ballot", "region": LAB("10 个州", "10 states", "e003.vote"),
         "count": {"value": 41, "label": LAB("41 项地方投票措施", "41 local ballot measures", "e003.vote")},
         "except": {"value": 1, "label": LAB("一项例外", "One exception", "e003.vote")},
         "cues": {"show": "10 个州", "count": "41 项", "except": "除了一项"}}
    b.update(kw)
    return b


class Tally(unittest.TestCase):
    """计数模板：只点亮事件卡点了名、而且和画面上的计数出自同一处原文的州；核不上和数字核不上一样停（check_labels）。"""

    def test_registered(self):
        self.assertIn("tally", SB.TEMPLATES)
        self.assertIn("tally", SB.NUM_FIELDS)
        self.assertIn("tally", SB.RELATION_KINDS["占比"])
        self.assertTrue(SB.is_relation_block(tally()))
        self.assertIsNotNone(SB.us_states(), "site/v3/us_states.json 读不了")
        self.assertEqual(len(SB.us_states()["states"]), 51)          # 50 个州＋华盛顿特区

    def test_no_states_is_fine(self):
        self.assertEqual(SB.check_tally(sb_with(tally()), FACTS_E003), [])
        geo = SB.tally_geo(tally())
        self.assertEqual(geo["lit"], [])
        self.assertTrue(geo["outline"].startswith("M"))

    def test_1106_states_from_other_fact_blocked(self):     # 卡里点名的佐治亚、俄亥俄是 OpenAI 项目所在地，不是 41 项投票措施所在地
        b = tally(states=["佐治亚州", "俄亥俄州"], states_ref=["e003.sites"])
        bad = SB.check_tally(sb_with(b), FACTS_E003)
        self.assertEqual(len(bad), 1, bad)
        self.assertIn("不在 region 或 count.label 的 ref 里", bad[0])

    def test_state_not_in_card(self):
        b = tally(states=["加州"], states_ref=["e003.vote"])
        bad = SB.check_tally(sb_with(b), FACTS_E003)
        self.assertEqual(len(bad), 1, bad)
        self.assertIn("「加州」在它引用的事件卡原文", bad[0])
        with self.assertRaises(SystemExit) as e:          # check_labels 一起停（"核对失败"，总调度第 7 步算要改）
            SB.check_labels(sb_with(b) | {"title": {}}, FACTS_E003)
        self.assertIn("核对失败", str(e.exception))
        self.assertIn("点亮的州", str(e.exception))

    def test_states_ok_when_same_fact(self):
        b = tally(region=LAB("2 个州", "2 states", "e003.sites"), states=["佐治亚州", "Ohio"], states_ref=["e003.sites"])
        self.assertEqual(SB.check_tally(sb_with(b), FACTS_E003), [])
        geo = SB.tally_geo(b)
        self.assertEqual([x["n"]["zh"] for x in geo["lit"]], ["佐治亚州", "俄亥俄州"])

    def test_missing_ref_and_unknown_name(self):
        bad = SB.check_tally(sb_with(tally(states=["佐治亚州"])), FACTS_E003)
        self.assertIn("却没写 states_ref", bad[0])
        b = tally(region=LAB("2 个州", "2 states", "e003.sites"), states=["加利福尼亚洲"], states_ref=["e003.sites"])
        self.assertIn("不认得", SB.check_tally(sb_with(b), FACTS_E003)[0])

    def test_longer_name_masked(self):              # 原文只有 West Virginia：写 Virginia 不算找到
        self.assertFalse(SB.state_in_text("Virginia", FACTS_E003["x.wv"]["text"]))
        self.assertTrue(SB.state_in_text("West Virginia", FACTS_E003["x.wv"]["text"]))
        self.assertFalse(SB.state_in_text("弗吉尼亚州", "西弗吉尼亚州有两个项目"))
        self.assertFalse(SB.state_in_text("Kansas", "Arkansas only"))

    def test_problem_fields(self):
        self.assertIsNone(SB.tally_problem(tally()))
        self.assertIn("整数", SB.tally_problem(tally(count={"value": 4.5})))
        self.assertIn("except.value", SB.tally_problem(tally(except_={"value": 1}, **{"except": {"value": 41}})))
        self.assertEqual(len(SB.check_values(sb_with(tally(count={"value": "41 项"})))), 1)


def sample_dirs():
    """完整样期：仓库的 测试版/ 只存跨天要用的文字（选题、事件卡、文稿），没有 logs、分镜、配音、视频。
    按顺序找：环境变量 FD_SAMPLE_ROOT/<日期>、本机资料/归档/mini试运行_1031-1109/<日期>（mini 试运行那周的原件，
    只在本机、靠 iCloud 同步，不进 git）、测试版/<日期>（11-09 晚加）。"""
    out = [Path(os.environ["FD_SAMPLE_ROOT"]).expanduser()] if os.environ.get("FD_SAMPLE_ROOT") else []
    return out + [ROOT / "本机资料" / "归档" / "mini试运行_1031-1109", ROOT / "测试版"]


def issue_of(day, rel):
    """第一份有 rel 的样期目录；都没有就是仓库里的 测试版/<日期>。"""
    return next((b / day for b in sample_dirs() if (b / day / rel).exists()), ROOT / "测试版" / day)


def orig(day, rel):
    """这一期"改前"的那份（11-06 白天重做以后，早上 06:00 的原件留在 期目录/logs/改前备份/<文件名>.<时间>；
    测试里"已知的问题要报出来"拿它当考题）。没有改前备份就用现在的。"""
    for b in sample_dirs():
        baks = sorted((b / day / "logs" / "改前备份").glob(Path(rel).name + ".*"))
        if baks:
            return baks[0]
    return issue_of(day, rel) / rel


def media(day, original=True):
    rel = "11_视频v3/video3_media.json"
    p = orig(day, rel) if original else issue_of(day, rel) / rel
    m = json.loads(p.read_text(encoding="utf-8"))
    return m["T"], [{"voice_start": c["vs"], "voice_end": c["ve"], "end": c["end"]} for c in m["chapters"]]


def sb_issue(day, original=True):
    rel = "04_文稿/视频v3_分镜.json"
    issue = issue_of(day, rel)
    sb = SB.load(orig(day, rel) if original else issue / rel)
    SB.structure(sb, issue)
    return sb


def need_sample(case, day, *rels):
    """要的样期文件不在（仓库里只有文字）就跳过这一项，写明原因（11-09 晚加：原来直接报"找不到文件"，盖住真正的回归）。"""
    miss = [r for r in rels if not (issue_of(day, r) / r).exists()]
    if miss:
        case.skipTest("%s 的 %s 不在：仓库的 测试版/ 只存文字；要跑这一项，设 FD_SAMPLE_ROOT 指向完整样期所在的文件夹" % (day, "、".join(miss)))


class Screen(unittest.TestCase):
    """画面检查（11-06 改准）：只剩线和点的时间轨、空玻璃柱、白卡上的字不算；关系模板只算触发词后 SCREEN_HOLD 秒；认得穿插。"""

    def setUp(self):
        if not (issue_of("2026-11-06", "11_视频v3/video3_media.json") / "11_视频v3" / "video3_media.json").exists():
            self.skipTest("没有 11-06 成品")
        self.sb = sb_issue("2026-11-06")
        self.T, self.marks = media("2026-11-06")

    def test_1106_known_gaps(self):                  # 审查报告逐段表里的空场：30–35 秒只剩点的时间轨、42–50 秒、71–78 秒两段章首
        gaps = {ch["c"]["id"]: [(round(a), round(z)) for a, z in ch["gaps"] if z - a > SB.SCREEN_GAP] for ch in SB.screen_model(self.sb, self.T, self.marks)}
        self.assertIn((28, 36), gaps["vote"])
        self.assertTrue(any(a <= 43 and z >= 50 for a, z in gaps["code"]), gaps["code"])
        self.assertTrue(any(a <= 72 and z >= 78 for a, z in gaps["permit"]), gaps["permit"])

    def test_1106_interrupt_and_opener(self):
        w = SB.check_gaps(self.sb, self.T, self.marks)
        self.assertTrue(any("timeline/nda 被 compare_panel/ballot 从中间打断" in x and "“周四”" in x for x in w), w)
        self.assertTrue(any("「code」开口 3 秒内没有主角" in x for x in w), w)

    def test_1106_redo_fixed(self):                  # 白天重做以后（现在的分镜＋配完音的实际时间）：这三章不再有超过 4 秒的空档，开口 3 秒内有主角
        live = issue_of("2026-11-06", "04_文稿/视频v3_分镜.json") / "04_文稿" / "视频v3_分镜.json"
        if live == orig("2026-11-06", "04_文稿/视频v3_分镜.json"):
            self.skipTest("没有重做过")
        sb = sb_issue("2026-11-06", original=False)
        T, marks = media("2026-11-06", original=False)
        for ch in SB.screen_model(sb, T, marks):
            if ch["c"]["id"] in ("vote", "code", "permit"):
                self.assertEqual([g for g in ch["gaps"] if g[1] - g[0] > SB.SCREEN_GAP], [], ch["c"]["id"])
                self.assertLessEqual(ch["hero"], ch["v0"] + SB.OPENER_SEC, ch["c"]["id"])

    def test_logos_on_ticks_fill_timeline(self):     # 日子挂上标志、小图以后，选票章前半段就有东西了
        sb = copy.deepcopy(self.sb)
        tl0 = sb["chapters"][1]["blocks"][0]
        tl0["ticks"][0]["logos"] = ["amazon"]
        tl0["ticks"][2]["logos"] = ["openai"]
        ch = [x for x in SB.screen_model(sb, self.T, self.marks) if x["c"]["id"] == "vote"][0]
        self.assertFalse([g for g in ch["gaps"] if g[0] < 22 and g[1] - g[0] > SB.SCREEN_GAP], ch["gaps"])
        self.assertLessEqual(ch["hero"], ch["v0"] + SB.OPENER_SEC + 1.0)

    def test_columns_count_only_after_cue(self):     # 柱状图：标题出来时只有空玻璃，不算；说到第一个数之后 SCREEN_HOLD 秒才算
        b = {"type": "column_compare", "id": "tb", "items": [{"value": 1}, {"value": 2}]}
        m = SB._moments(b, {"head": 50.6, "items0": 52.7, "items1": 55.5})
        self.assertEqual(sorted((a, z) for a, z, _k in m), [(52.7, 52.7 + SB.SCREEN_HOLD), (55.5, 55.5 + SB.SCREEN_HOLD)])

    def test_blank_spans_for_sheet(self):
        bl = SB.blank_spans(self.sb, self.T, self.marks)
        self.assertIn("vote", bl)
        self.assertTrue(all(len(x) == 3 and x[1] > x[0] for v in bl.values() for x in v))

    def test_estimate_timing(self):                   # 第 7 步没配音：按字数估，和实际对齐差不了太多
        if str(ROOT / "pipeline") not in sys.path:
            sys.path.insert(0, str(ROOT / "pipeline"))
        T, marks = SB.estimate_timing(self.sb)
        self.assertIsNotNone(T)
        keys = [k for k, _i, _s in SB.cue_list(self.sb)]
        self.assertEqual([k for k in keys if k not in T], [])
        for k in ("vote.nda.ticks2", "code.tb.head", "permit.scope.head", "contrast.aa.show"):
            self.assertLess(abs(T[k] - self.T[k]), 4.0, k)
        w = SB.check_screen(self.sb)
        self.assertTrue(any("时间按字数估" in x for x in w), w)

    def test_check_relations_carries_screen(self):    # 总调度第 7 步只调 check_relations：画面检查的提醒要跟着出来，但不算要改
        if str(ROOT / "pipeline") not in sys.path:
            sys.path.insert(0, str(ROOT / "pipeline"))
        must, warn = SB.check_relations(self.sb)
        self.assertEqual(must, [])
        self.assertTrue(any("画面上没有真东西" in x for x in warn), warn)

    def test_minimal_storyboard_quiet(self):          # 测试里那种没有旁白的小分镜：估不出时间就不查，不报错
        self.assertEqual(SB.estimate_timing(sb_with(YIELD_OK)), (None, None))


class SpokenFacts(unittest.TestCase):
    def test_1106(self):
        p = orig("2026-11-06", "04_文稿/视频v3_分镜.json")         # 早上的原件（白天重做前）
        if not p.exists():
            self.skipTest("没有 11-06 分镜")
        w = SB.check_spoken_facts(SB.load(p))
        self.assertEqual(len(w), 2, w)
        self.assertIn("「code」", w[0])
        self.assertIn("“3200 万美元”", w[0])
        self.assertIn("“High”、“Critical”", w[1])

    def test_1106_redo(self):                          # 11-06 白天重做以后：3200 万美元、High、Critical 都上了画面
        p = issue_of("2026-11-06", "04_文稿/视频v3_分镜.json") / "04_文稿" / "视频v3_分镜.json"
        if p == orig("2026-11-06", "04_文稿/视频v3_分镜.json"):
            self.skipTest("没有重做过")
        self.assertEqual(SB.check_spoken_facts(SB.load(p)), [])

    def test_past_quiet(self):
        for day in ("2026-10-31", "2026-11-03", "2026-11-04"):
            p = ROOT / "测试版" / day / "04_文稿" / "视频v3_分镜.json"
            if p.exists():
                self.assertEqual(SB.check_spoken_facts(SB.load(p)), [], day)

    def test_image_budget(self):
        reqs = [{"id": "v%d" % i, "brief_en": "x", "placement": "card"} for i in range(5)]
        blocks = [dict(POST_IMG, id="p%d" % i, image="v%d" % i) for i in range(5)]
        # 11-08 晚：张数按内容需要，不再按张数提醒（原来新画 5 张会提醒"新画的不超过 4 张"）
        self.assertEqual(SB.check_image_budget(dict(sb_with(*blocks), image_requests=reqs)), [])
        self.assertEqual(SB.check_image_budget(dict(sb_with(*blocks[:4]), image_requests=reqs[:4])), [])


class Avatar(unittest.TestCase):
    """帖子卡头像里的标志（11-06：OpenAI 字标塞进圆里压住了"Chris"）：库里每个标志按 avatar_fit 放，都不出圆、不出胶囊；
    和 video3.js 的 AV、avatarFit 是同一组数、同一个算法（用本机 node 跑一遍对照）。"""

    def setUp(self):
        import video3_logos as LG
        self.LG = LG
        self.items = LG.embed(list(LG.load()["logos"]))

    def test_no_overflow(self):
        A = self.LG.AVATAR
        for k, it in self.items.items():
            f = self.LG.avatar_fit(it)
            if not f["pill"]:
                self.assertLessEqual(f["w"], A["IN"] + 1e-9, k)
                self.assertLessEqual((f["w"] / 2) ** 2 + (f["h"] / 2) ** 2, (A["D"] / 2) ** 2, k)     # 四角都在圆里
            elif f["w"] is not None:
                self.assertLessEqual(f["w"], A["PW"] + 1e-9, k)
                self.assertLessEqual(f["h"], A["PH"] + 1e-9, k)
        self.assertTrue(self.LG.avatar_fit(self.items["openai"])["pill"])
        self.assertFalse(self.LG.avatar_fit(self.items["anthropic"])["pill"])

    def test_same_as_renderer(self):
        js = (ROOT / "site" / "v3" / "video3.js").read_text(encoding="utf-8")
        m = re.search(r"var AV = (\{[^}]*\});", js)
        self.assertIsNotNone(m, "video3.js 里找不到 AV")
        av = json.loads(re.sub(r"(\w+):", r'"\1":', m.group(1)))
        self.assertEqual(av, self.LG.AVATAR)
        node = shutil.which("node")
        if not node:
            self.skipTest("没有 node")
        fn = re.search(r"\n  function avatarFit\(lg\) \{.*?\n  \}\n", js, re.S)
        self.assertIsNotNone(fn)
        src = m.group(0) + fn.group(0) + "\nconsole.log(JSON.stringify(%s.map(avatarFit)));" % json.dumps(list(self.items.values()))
        out = json.loads(subprocess.run([node, "-e", src], capture_output=True, text=True, check=True).stdout)
        for (k, it), o in zip(self.items.items(), out):
            if not it.get("m"):
                continue                                   # 文字小签：播放器直接用名字做胶囊，不调 avatarFit
            py = self.LG.avatar_fit(it)
            self.assertEqual(o["pill"], py["pill"], k)
            self.assertAlmostEqual(o["h"], py["h"], places=6, msg=k)


def full_sb(*blocks):
    """structure 认得的最小分镜：开场、一章 story（id 是 bill）、收尾。"""
    return {"chapters": [
        {"id": "open", "kind": "open", "title": "开场", "label": LAB("开场", "Open"), "narration": "开场。", "cues": {}},
        {"id": "bill", "kind": "story", "title": "钱", "label": LAB("钱", "Money"), "narration": "钱的旁白。", "map_cue": "开场",
         "chip": {"name": LAB("钱", "Money")}, "blocks": [copy.deepcopy(b) for b in blocks]},
        {"id": "close", "kind": "close", "title": "收尾", "label": LAB("收尾", "End"), "narration": "收尾。"}]}


MARKS3 = [{"voice_start": 0.2, "voice_end": 0.4, "end": 0.5}, {"voice_start": 0.5, "voice_end": 9.0, "end": 9.5},
          {"voice_start": 9.6, "voice_end": 10.0, "end": 11.0}]


class Compile(unittest.TestCase):
    """新图位编进播放器数据：要点卡题图、时间轨日子小图（video3_build.prep_photos 不认得，compile_chapters 补上）、计数模板的州界、空档。"""

    def test_new_slots(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            issue = Path(d) / "2026-11-06"
            (issue / "06_配图").mkdir(parents=True)
            Image.new("RGB", (64, 40), (200, 120, 90)).save(issue / "06_配图" / "e006.png")
            q = {"type": "quote_card", "id": "readonly", "text": LAB("只读，不能动钱", "Read-only"), "image": "e006", "cues": {"show": "@start"}}
            t = tl(None, None, None)
            t["ticks"][1]["image"] = "e006"
            sb = full_sb(t, q, tally())
            SB.structure(sb, issue)
            self.assertEqual([b["type"] for b in sb["chapters"][1]["blocks"]], ["timeline", "quote_card", "tally"])
            photos = {}
            T = {"bill.wait.ticks0": 1.0, "bill.wait.ticks1": 2.0, "bill.wait.ticks2": 3.0, "bill.readonly.show": 4.0, "bill.ballot.show": 6.0}
            ch = SB.compile_chapters(sb, T, MARKS3, photos)[1]
            q2, t2, y2 = ch["blocks"][1], ch["blocks"][0], ch["blocks"][2]
            self.assertEqual(q2["img"], "readonly")
            self.assertEqual(t2["ticks"][1]["img"], "wait.ticks1")
            self.assertTrue((issue / "11_视频v3" / photos["readonly"]["src"]).exists())
            self.assertEqual(photos["wait.ticks1"]["file"], "e006")
            self.assertTrue(y2["geo"]["outline"])
            self.assertNotIn("states_ref", y2)
            self.assertEqual(SB.photo_moments(sb["chapters"][1])[0], ["e006", "e006"])

    def test_missing_image_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            t = tl(None, None)
            t["ticks"][0]["image"] = "nope"
            q = {"type": "quote_card", "id": "q", "text": LAB("一句", "one"), "image": "nope"}
            sb = full_sb(t, q)
            w = SB.structure(sb, Path(d) / "2026-11-06")
            self.assertEqual(len([x for x in w if "找不到配图 nope" in x]), 2, w)
            self.assertEqual(sb["_pending_images"], {"bill": ["nope", "nope"]})

    def test_every_template_has_renderer(self):
        js = (ROOT / "site" / "v3" / "video3.js").read_text(encoding="utf-8")
        tpl = set(re.findall(r"\n  TPL\.(\w+) = \{", js))
        self.assertEqual(sorted(set(SB.TEMPLATES) - tpl), [])

    def test_timeline_segments_in_renderer(self):     # 播放器 tlSegments：11-06 选票章的时刻，"周四"另成一段，段尾是下一个模板开始
        node = shutil.which("node")
        if not node:
            self.skipTest("没有 node")
        js = (ROOT / "site" / "v3" / "video3.js").read_text(encoding="utf-8")
        fn = re.search(r"\n  function tlSegments\(b, tt\) \{.*?\n  \}\n", js, re.S)
        self.assertIsNotNone(fn)
        src = ("function startT(x) { return x.st; }" + fn.group(0) +
               "var tl = {_: {}}, c = {end: 42.3, _real: [tl, {st: 22.685, _: {}}, {st: 35.725, _: {}}]}; tl._.c = c;"
               "console.log(JSON.stringify(tlSegments(tl, [17.025, 20.865, 27.921])));")
        out = json.loads(subprocess.run([node, "-e", src], capture_output=True, text=True, check=True).stdout)
        self.assertEqual([(s["i0"], s["i1"], s["end"]) for s in out], [(0, 1, 22.685), (2, 2, 35.725)])


class Redo1106(unittest.TestCase):
    """11-06 白天重做时补的几处：刻度尺的档位序号（at）编进播放器数据、往上升也画得对；数字强调不拆型号；
    时间轨日子上的小图弹出后镜头先停一会儿再飞走（用本机 node 跑 video3.js 里的函数）。"""

    def test_strip_labels_keeps_scale_at(self):       # 原来 at 一律去掉，刻度尺只能按默认从第 0 档落到第 1 档
        b = {"type": "scale", "from": {"at": 1, "label": {"zh": "上一代", "ref": ["x"]}}, "to": {"at": 0},
             "ticks": [{"at": "10 月"}, {"at": {"say": "本周", "offset": 0.2}}], "cues": {"to": "Critical"}}
        out = SB.strip_labels(b)
        self.assertEqual((out["from"]["at"], out["to"]["at"]), (1, 0))
        self.assertEqual(out["from"]["label"], {"zh": "上一代"})
        self.assertEqual([("at" in t) for t in out["ticks"]], [False, False])
        self.assertNotIn("cues", out)

    def js(self, names, tail):
        node = shutil.which("node")
        if not node:
            self.skipTest("没有 node")
        js = (ROOT / "site" / "v3" / "video3.js").read_text(encoding="utf-8")
        parts = [re.search(r"\n  var esc = function \(s\) \{.*?\n  \};\n", js, re.S).group(0)]
        for n in names:
            m = (re.search(r"\n  function %s\([^\n]*\}\n" % n, js) or               # 一行写完的函数
                 re.search(r"\n  (?:function %s\(.*?\n  \}\n|var %s = [^\n]*;\n)" % (n, n), js, re.S))
            self.assertIsNotNone(m, n)
            parts.append(m.group(0))
        return json.loads(subprocess.run([node, "-e", "".join(parts) + tail], capture_output=True, text=True, check=True).stdout)

    def test_scale_at_and_emph(self):
        out = self.js(["scAt", "emph"], "console.log(JSON.stringify([scAt({at: 0}, 1), scAt({}, 1), scAt(null, 0), scAt({at: '2'}, 0),"
                      " emph('GPT-6 Cyber'), emph('94.49%'), emph('Q2 $2.08'), emph('-28.58%')]));")
        self.assertEqual(out[:4], [0, 1, 0, 2])
        self.assertNotIn("<span", out[4])                       # 型号里的数字不强调
        self.assertIn('<span class="v3n em ">94.49%</span>', out[5])
        self.assertEqual(out[6].count("<span"), 1)               # Q2 不强调，2.08 照旧
        self.assertIn(">-28.58%<", out[7])                       # 负数照旧（前面不是字母）

    def test_tick_image_hold(self):                    # 11-06 选票章：小图 20.5 秒弹出，计数卡那一镜原本 21.6 秒就起飞
        out = self.js(["TL_IMG_HOLD", "tlImagePops", "tlImageHold"],
                      "var tl = {type: 'timeline', _: {o: {ticks: [{img: false}, {img: true}, {img: false}], tt: [17.025, 20.355, 27.921]}}},"
                      " ta = {type: 'tally', _: {}}, ks = [{t: 17.7, dur: 1.3, b: tl}, {t: 22.885, dur: 1.3, b: ta}, {t: 28.82, dur: 1.2, b: tl}];"
                      " tlImageHold([tl, ta], ks); console.log(JSON.stringify(ks.map(function (k) { return Math.round(k.t * 1000) / 1000; })));")
        self.assertEqual(out, [17.7, round(20.355 + 0.15 + 1.8 + 1.3, 3), 28.82])
        out = self.js(["TL_IMG_HOLD", "tlImagePops", "tlImageHold"],           # 没挂小图：一点不动
                      "var tl = {type: 'timeline', _: {o: {ticks: [{}, {}], tt: [17, 20.3]}}}, ks = [{t: 21.7, dur: 1.3, b: {}}];"
                      " tlImageHold([tl], ks); console.log(JSON.stringify(ks[0].t));")
        self.assertEqual(out, 21.7)


def split_block(**kw):
    b = {"type": "split", "id": "split",
         "left": {"head": LAB("国外", "World")}, "right": {"head": LAB("国内", "China")},
         "left_items": [{"text": LAB("Ripple-65B 自称美国开放权重编程第一", "x", "e002.claim"), "cue": "美国第一"}],
         "right_items": [{"text": LAB("Kimi K3.1 Pro 放出权重", "y", "e142.weights"), "cue": "Kimi"}],
         "cues": {"split": "国内外", "left": "Ripple", "right": "月之暗面"}}
    b.update(kw)
    return b


class Eve1106(unittest.TestCase):
    """11-06 晚修补的几处：旁白每章开头的英文夹心（check_voice_openings，判断在 pipeline/lexicon_check.py 第 8 项后半）；
    国内外 split 小卡带题图、"接下来"挂标志；要点卡只有字（check_text_cards）；要点卡压在路尽头的配图上（over_photo）。"""

    @classmethod
    def setUpClass(cls):
        if str(ROOT / "pipeline") not in sys.path:
            sys.path.insert(0, str(ROOT / "pipeline"))

    def eve_before(self):                               # 11-06 晚修前（下午重做版）的分镜：期目录 logs/改前备份/ 里时间最晚的那份
        baks = sorted((issue_of("2026-11-06", "logs/改前备份") / "logs" / "改前备份").glob("视频v3_分镜.json.*"))
        if len(baks) < 2:
            self.skipTest("没有 11-06 晚修前的分镜")
        return SB.load(baks[-1])

    def test_voice_openings_1106(self):
        w = SB.check_voice_openings(self.eve_before())
        self.assertEqual([re.match(r"「(\w+)」", x).group(1) for x in w], ["code", "permit"])
        self.assertTrue(any("发布了" in x for x in w) and any("“在”" in x for x in w), w)
        morning = SB.check_voice_openings(SB.load(orig("2026-11-06", "04_文稿/视频v3_分镜.json")))     # 早上那份（没加逗号）同样两章
        self.assertEqual([re.match(r"「(\w+)」", x).group(1) for x in morning], ["code", "permit"])
        live = SB.load(issue_of("2026-11-06", "04_文稿/视频v3_分镜.json") / "04_文稿" / "视频v3_分镜.json")
        self.assertEqual(SB.check_voice_openings(live), [])

    def test_voice_openings_past_quiet(self):          # 往期：10-31、11-01（OpenAI 的 CEO Sam Altman）、11-03（Anthropic、MIT）都不报
        for day in ("2026-10-31", "2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"):
            p = ROOT / "测试版" / day / "04_文稿" / "视频v3_分镜.json"
            if p.exists():
                self.assertEqual(SB.check_voice_openings(SB.load(p)), [], day)

    def test_voice_openings_in_relations(self):        # 第 7 步只调 check_relations：这条提醒放在最前面，不算要改
        sb = self.eve_before()
        SB.structure(sb, issue_of("2026-11-06", "04_文稿/视频v3_分镜.json"))
        must, warn = SB.check_relations(sb)
        self.assertEqual(must, [])
        self.assertIn("旁白开头", warn[0])

    def test_text_cards(self):
        sb = self.eve_before()
        self.assertEqual([re.match(r"「(\w+)」要点卡 (\w+)", x).groups() for x in SB.check_text_cards(sb)], [("code", "cost")])
        live = SB.load(issue_of("2026-11-06", "04_文稿/视频v3_分镜.json") / "04_文稿" / "视频v3_分镜.json")
        self.assertEqual(SB.check_text_cards(live), [])
        q = {"type": "quote_card", "id": "q", "text": LAB("研发成本 3200 万美元", "$32M", "e002.cost"), "over_photo": True}
        self.assertEqual(len(SB.check_text_cards(sb_with(q))), 1)          # 写了 over_photo、这一章却没有立在路尽头的配图：照样提醒
        fork = {"type": "fork", "id": "route", "a": LAB("稠密", "Dense"), "b": LAB("混合专家", "MoE")}
        img = {"type": "image_card", "id": "photo", "image": "v_code"}
        self.assertEqual(SB.check_text_cards(sb_with(fork, img, q)), [])
        q2 = dict(q, over_photo=False, logos=["ricursive"])                   # 文字小签不算标志
        self.assertEqual(len(SB.check_text_cards(sb_with(q2))), 1)
        q3 = dict(q, over_photo=False, logos=["anthropic"])
        self.assertEqual(SB.check_text_cards(sb_with(q3)), [])

    def test_over_photo_counts_as_image(self):
        q = {"type": "quote_card", "id": "cost", "text": LAB("研发成本 3200 万美元", "$32M"), "over_photo": True}
        self.assertEqual(SB._moments(q, {"show": 66.5}), [])
        self.assertEqual([(a, k) for a, _z, k in SB._moments(q, {"show": 66.5}, over_ok=True)], [(66.5, "img")])
        js = (ROOT / "site" / "v3" / "video3.js").read_text(encoding="utf-8")
        self.assertIn("b.over_photo && b.type === 'quote_card' && b._.fork && fph", js)

    def test_split_images(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            issue = Path(d) / "2026-11-06"
            (issue / "06_配图").mkdir(parents=True)
            Image.new("RGB", (64, 40), (200, 120, 90)).save(issue / "06_配图" / "e142.png")
            sp = split_block()
            sp["right_items"][0]["image"] = "e142"
            sp["left_items"][0]["image"] = "nope"
            sb = full_sb()
            sb["chapters"].insert(2, {"id": "contrast", "kind": "contrast", "title": "国内外", "label": LAB("国内外", "CN"),
                                      "narration": "国内外跑在同一条赛道上。Ripple 争美国第一，月之暗面放出 Kimi。",
                                      "chip": {"name": LAB("国内外", "CN")}, "blocks": [sp]})
            w = SB.structure(sb, issue)
            self.assertTrue(any("split/split 找不到配图 nope" in x for x in w), w)       # 找不到的只去掉图
            c = sb["chapters"][2]
            self.assertEqual(SB.photo_moments(c), (["e142"], []))
            self.assertEqual(SB.image_names(sb), ["e142", "nope"])
            T = {"contrast.split.split": 10.0, "contrast.split.left": 11.0, "contrast.split.right": 11.4,
                 "contrast.split.left_items0": 12.0, "contrast.split.right_items0": 13.0}
            imgs = [(a, k) for a, _z, k in SB._moments(c["blocks"][0], {k.split(".")[-1]: v for k, v in T.items()}) if k == "img"]
            self.assertEqual(imgs, [(13.0, "img")])
            photos = {}
            marks = MARKS3[:2] + [{"voice_start": 10.0, "voice_end": 16.0, "end": 16.5}, {"voice_start": 16.6, "voice_end": 17.0, "end": 18.0}]
            ch = SB.compile_chapters(sb, T, marks, photos)[2]
            self.assertEqual(ch["blocks"][0]["right_items"][0]["img"], "split.right_items0")
            self.assertNotIn("img", ch["blocks"][0]["left_items"][0])
            self.assertEqual(photos["split.right_items0"]["file"], "e142")

    def test_next_logos(self):
        self.assertEqual(SB.LOGO_SLOTS["next"], ["items[].logos"])
        facts = {"e009.next": {"text": "官方表示，计划于下周以 Apache 2.0 许可证开放完整权重。"},
                 "e009.tml": {"text": "Thinking Machines Lab 发布第二代模型 Inkling 2 Small。"}}
        nx = {"type": "next", "id": "next", "items": [{"when": LAB("下周", "Next week", "e009.next"),
                                                        "text": LAB("Inkling 2 Small 放出权重", "weights", "e009.next", "e009.tml"),
                                                        "logos": ["thinkingmachines"]}]}
        sb = {"chapters": [{"id": "contrast", "kind": "contrast", "blocks": [copy.deepcopy(nx)]}]}
        self.assertEqual([w for w in SB.check_logos(sb, facts) if "thinkingmachines" in w], [])
        self.assertEqual(sb["chapters"][0]["blocks"][0]["items"][0]["logos"], ["thinkingmachines"])
        nx["items"][0]["text"]["ref"] = ["e009.next"]                          # 原文里没有这家公司：不挂
        sb = {"chapters": [{"id": "contrast", "kind": "contrast", "blocks": [nx]}]}
        self.assertTrue(any("thinkingmachines" in w for w in SB.check_logos(sb, facts)))
        self.assertNotIn("logos", sb["chapters"][0]["blocks"][0]["items"][0])
        m = SB._moments({"type": "next", "items": [{"logos": ["thinkingmachines"]}]}, {"head": 113.9, "items0": 113.9})
        self.assertEqual([(a, k) for a, _z, k in m], [(113.9, "logo")])

    def test_1106_contrast_fixed(self):                # 晚修以后（现在的分镜＋配完音的实际时间）：国内外章开口 3 秒内有主角，没有超过 4 秒的空档
        need_sample(self, "2026-11-06", "04_文稿/视频v3_分镜.json", "11_视频v3/video3_media.json")
        live = issue_of("2026-11-06", "04_文稿/视频v3_分镜.json") / "04_文稿" / "视频v3_分镜.json"
        sb = sb_issue("2026-11-06", original=False)
        if not any(b.get("type") == "split" and (b.get("right") or {}).get("logos") for c in sb["chapters"] for b in c.get("blocks") or []):
            self.skipTest("还没晚修")
        T, marks = media("2026-11-06", original=False)
        if "contrast.split.right" not in T or T["contrast.split.right"] > T["contrast.split.split"] + 3:
            self.skipTest("成品还没按晚修的分镜重渲")
        ch = [x for x in SB.screen_model(sb, T, marks) if x["c"]["id"] == "contrast"][0]
        self.assertEqual([g for g in ch["gaps"] if g[1] - g[0] > SB.SCREEN_GAP], [])
        self.assertLessEqual(ch["hero"], ch["v0"] + SB.OPENER_SEC)
        self.assertTrue(live.exists())

    def test_original_contrast_opener_reported(self):  # 下午加的"章首 3 秒内没主角"：拿 11-06 早上的原件按字数估时间，国内外章要报出来
        need_sample(self, "2026-11-06", "04_文稿/视频v3_分镜.json")
        sb = sb_issue("2026-11-06")
        T, marks = SB.estimate_timing(sb)
        self.assertIsNotNone(T)
        w = SB.screen_warnings(sb, T, marks, est=True)
        self.assertTrue(any("「contrast」开口 3 秒内没有主角" in x for x in w), w)


class RendererCoverage(unittest.TestCase):
    """video3.js 里把字段换算成数字（+x）的模板，都要登记在 NUM_FIELDS。"""

    def test_all_numeric_templates_listed(self):
        js = (ROOT / "site" / "v3" / "video3.js").read_text(encoding="utf-8")
        coerce = re.compile(r"\+\(*[\w.\[\]]+(?:\s*\|\|\s*\{\}\))?\.(?:value|pos|threshold|at)\b|\+at\b")
        found = {m.group(1) for m in re.finditer(r"\n  TPL\.(\w+) = \{(.*?)\n  \};", js, re.S) if coerce.search(m.group(2))}
        self.assertTrue(found, "video3.js 里没找到模板，正则可能要跟着改")
        self.assertEqual(sorted(found - set(SB.NUM_FIELDS)), [], "这些模板把字段当数字读，但 NUM_FIELDS 里没有")
        self.assertEqual(sorted(set(SB.NUM_FIELDS) - set(SB.TEMPLATES)), [])


class LonelyQuote(unittest.TestCase):
    """11-09：引语卡孤零零占着画面（镜头在 quote_card 上、没有配图也没有在动的模板，只挂标志也算）超过 4 秒就提醒。"""

    def model(self, **qc):
        q = dict({"type": "quote_card", "id": "q", "text": {"zh": "会适时通报进展"}, "who": {"zh": "英伟达董事会"},
                  "logos": ["nvidia"]}, **qc)
        sb = {"chapters": [{"id": "open", "kind": "open", "narration": "今天。", "blocks": []},
                           {"id": "s1", "kind": "story", "narration": "董事会说会适时通报进展。", "blocks": [q]}]}
        T = {"s1.q.show": 11.0}
        marks = [{"voice_start": 0.5, "voice_end": 9.0, "end": 10.0}, {"voice_start": 10.5, "voice_end": 20.0, "end": 21.0}]
        return sb, T, marks

    def test_logo_only_reported(self):
        sb, T, marks = self.model()
        w = SB.screen_warnings(sb, T, marks)
        self.assertTrue(any("quote_card/q 只有一张引语卡" in x for x in w), w)
        self.assertFalse(any("画面上没有真东西" in x and "11.0–20.0" in x for x in w), w)     # 有标志，不算空画面

    def test_with_image_quiet(self):
        sb, T, marks = self.model(image="v_board")
        self.assertFalse(any("只有一张引语卡" in x for x in SB.screen_warnings(sb, T, marks)))

    def test_short_quiet(self):
        sb, T, marks = self.model()
        marks[1]["voice_end"] = 14.5                                     # 只占 3.5 秒
        self.assertFalse(any("只有一张引语卡" in x for x in SB.screen_warnings(sb, T, marks)))

    def test_no_logo_reported_once_as_gap(self):
        sb, T, marks = self.model(logos=None)
        w = SB.screen_warnings(sb, T, marks)
        self.assertTrue(any("画面上没有真东西" in x for x in w), w)
        self.assertFalse(any("只有一张引语卡" in x for x in w), w)        # 已经报了空画面，不重复报


if __name__ == "__main__":
    unittest.main(verbosity=1)
