#!/usr/bin/env python3
"""视频 v3 动效尝试（2026-11-06 晚加）的测试：原文截图／摘录（source_shot、source_excerpt）、数字递进（num_chain）、
开场今日速览（headline_open）、数字滚动（quote_card / num_chain 的 "count": true）；
11-06 深夜补结合式：原话卡带原文截图（post_card / quote_card 的 shot）、时间轴日子带原文截图（ticks[].shot），
截图记录里的字号检查（原句不比字幕小）、尝试版命令的 tick 写法；
11-07 补配图＋动效结合：日子截图截不成时原来的小图留着、tile_row / compare_panel 压在配图上（photo）、对比卡的出处签（src_tag）和
条尾的数（bars[].val）、尝试版命令的 image_requests / --gen-images / --reuse-images。

查三件事：
  1. 分镜检查认得新模板，而且守住"事实只能来自事件卡"：原句要逐字在事件卡 quote 里、中文行只取同一条的 text_zh（或 said_zh）、
     出处签的媒体名要在事件卡来源里、数字要在事件卡里、触发词要在旁白里——核不上就停（SystemExit）；
     截图没成功自动退回 source_excerpt；网页日期和事件卡对不上时出处签不写日期；
  2. 编进播放器数据的样子（出处、原句、截图和行位置、开场速览的图和章名）；
  3. 播放器：用本机 node 跑 video3.js 里的 countHtml、chainNum（终值写法一字不差）；再用本机 Chrome 打开一页装了新模板的演示页，
     到几个时刻看画面状态（开场速览在、数字滚到终值、荧光笔扫完），页面不能报错（浏览器那一组，没有 Playwright/Chrome 就跳过）。
不写新模板的分镜行为不变：test_video3_storyboard.py 全部照旧通过；逐像素回归另外做（见 ~/.cache/frontier-daily/验证/动效尝试_报告.md）。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python site/tools/test_video3_motion.py        # 全部通过时退出码为 0
不调用任何模型、不联网；浏览器那一组只读项目里的 11-06 演示页（复制到临时目录里改），不写项目文件。
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
JS = ROOT / "site" / "v3" / "video3.js"
PW = os.environ.get("PLAYWRIGHT") or str(Path.home() / ".npm/_npx/9833c18b2d85bc59/node_modules/playwright/index.mjs")

# 事件卡（照 11-06 E003、E009 的样子，只留用得到的字段）
QUOTE = ("Following this week’s midterms where voters resoundingly voiced their opposition to data center expansion, OpenAI today "
         "announced new commitments to communities where it is working on data center projects, including that it won’t use "
         "non-disclosure agreements (NDAs) with public officials.")
CARDS = {
    "E003": {"event_id": "E003", "sources": [
        {"id": "s1", "name": "The Verge · AI", "url": "https://www.theverge.com/ai-artificial-intelligence/1028454/openai-data-center-nda",
         "date": "2026-11-06T00:37:56Z"},
        {"id": "s2", "name": "CNBC · 科技", "url": "https://www.cnbc.com/x.html", "date": "2026-11-05T13:44:45Z"}],
        "facts": [{"text_zh": "OpenAI 宣布对其数据中心项目所在社区作出新承诺，包括不再与公职人员使用保密协议（NDA）。", "source_id": "s1", "quote": QUOTE},
                  {"text_zh": "据 CNBC 汇总 Ballotpedia 的分析，10 个州共有 41 项地方投票措施，除一项外，选民全部支持限制措施或否决促开发措施。",
                   "source_id": "s2", "quote": "Out of 41 local ballot measures across 10 states, voters backed restrictions or rejected "
                                               "pro-development measures for all but one"}],
        "numbers": [], "who_said": []},
    "E009": {"event_id": "E009", "sources": [{"id": "s1", "name": "Artificial Analysis（经 Techmeme 收录）", "url": "https://artificialanalysis.ai/a",
                                              "date": "2026-11-06"}],
             "facts": [], "numbers": [],
             "who_said": [{"who": "Artificial Analysis", "said_zh": "按当前排名，权重放出后它将是非中国开发的得分最高的开源权重模型。", "source_id": "s1",
                           "quote": "Their plan to release its weights would make it the highest-scoring open weights model developed outside China"}]},
}
FACTS_SB = {"e003.nda": {"event": "E003", "field": "facts", "index": 0, "check": "不再与公职人员使用保密协议"},
            "e003.vote": {"event": "E003", "field": "facts", "index": 1, "check": "10 个州共有 41 项地方投票措施"},
            "e009.aa": {"event": "E009", "field": "who_said", "index": 0, "check": "得分最高的开源权重模型"}}
NARR = {"open": "11 月 6 日，选票给数据中心设下闸门，AI 越能动手，越要讲授权。",
        "vote": "本周中期选举，10 个州的 41 项数据中心投票措施，除了一项，选民都站在限制一边。周四，OpenAI 承诺不再和公职人员签保密协议。",
        "close": "合起来看。"}


def shot_block(**kw):
    b = {"type": "source_shot", "id": "verge_nda", "fact": "e003.nda",
         "quote": "it won’t use non-disclosure agreements (NDAs) with public officials", "zh": "包括不再与公职人员使用保密协议（NDA）",
         "source": {"zh": "The Verge", "en": "The Verge"}, "cues": {"show": "承诺不再和公职人员签保密协议", "mark": "不再和公职人员签保密协议"}}
    b.update(kw)
    return b


def chain_block(**kw):
    b = {"type": "num_chain", "id": "vote_chain", "head": LAB("数据中心地方投票措施", "Local ballot measures"),
         "items": [{"label": LAB("10 个州", "10 states", "e003.vote"), "cue": "10 个州"},
                   {"label": LAB("41 项", "41 measures", "e003.vote"), "cue": "41 项"},
                   {"label": LAB("除一项外", "All but one", "e003.vote"), "cue": "除了一项"}],
         "count": True}
    b.update(kw)
    return b


def head_block(**kw):
    b = {"type": "headline_open", "id": "glance",
         "items": [{"ch": "vote", "text": {"zh": "选票给数据中心设下闸门", "en": "Ballots gate data centres"},
                    "sub": LAB("41 项 · 除一项外", "41 · all but one", "e003.vote")}]}
    b.update(kw)
    return b


def storyboard(vote_blocks, open_blocks=None):
    return {"schema": SB.SCHEMA, "date": "2026-11-06", "facts": copy.deepcopy(FACTS_SB), "chapters": [
        {"id": "open", "kind": "open", "title": "开场", "label": LAB("开场", "Open"), "narration": NARR["open"], "cues": {"map": "11 月 6 日"},
         "blocks": copy.deepcopy(open_blocks or [])},
        {"id": "vote", "kind": "story", "title": "选票", "label": LAB("选票", "The vote"), "narration": NARR["vote"],
         "map_cue": "选票给数据中心设下闸门", "chip": {"name": LAB("选票", "The vote")}, "blocks": copy.deepcopy(vote_blocks)},
        {"id": "close", "kind": "close", "title": "收尾", "label": LAB("收尾", "End"), "narration": NARR["close"], "cues": {"map": "合起来看"}}]}


def run_checks(sb, issue):
    """和 video3_build.prepare 一样的顺序：structure → check_facts → check_labels（含 check_sources）。返回 structure 的提醒。"""
    warn = SB.structure(sb, issue)
    facts = SB.check_facts(sb, copy.deepcopy(CARDS))
    SB.check_labels(sb, facts)
    return warn


def write_shot(issue, sid, quote, ok=True, page_date=None, **extra):
    from PIL import Image
    d = issue / SB.SHOT_DIR
    d.mkdir(parents=True, exist_ok=True)
    rec = {"id": sid, "ok": ok, "url": CARDS["E003"]["sources"][0]["url"], "quote": quote, "shot_at": "2026-11-06 23:00:00 +0000",
           "reason": "" if ok else "人机验证或验证码（按规矩不处理）", "w": 320, "h": 180, "lines": [[0.1, 0.4, 0.8, 0.06], [0.1, 0.47, 0.3, 0.06]] if ok else None}
    if page_date:
        rec["page_date"] = page_date
    rec.update(extra)
    if ok:
        Image.new("RGB", (320, 180), (250, 250, 250)).save(d / (sid + ".png"))
        rec["png"] = sid + ".png"
    (d / (sid + ".json")).write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")


class Registered(unittest.TestCase):
    def test_templates_and_renderer(self):
        js = JS.read_text(encoding="utf-8")
        tpl = set(re.findall(r"\n  TPL\.(\w+) = \{", js))
        for t in ("source_shot", "source_excerpt", "num_chain", "headline_open"):
            self.assertIn(t, SB.TEMPLATES)
            self.assertIn(t, tpl)
        self.assertEqual(SB.TEMPLATES["headline_open"]["kinds"], ["open"])
        self.assertIn("num_chain", SB.RELATION_KINDS["数量变化"])
        self.assertNotIn("source_shot", SB.RELATION_BLOCKS)       # 截图只是出处，不算"画关系"


class Sources(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.issue = Path(self.tmp.name) / "2026-11-06"
        self.issue.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_shot_ok(self):
        write_shot(self.issue, "verge_nda", shot_block()["quote"])
        sb = storyboard([shot_block()])
        run_checks(sb, self.issue)
        b = sb["chapters"][1]["blocks"][0]
        self.assertEqual(b["type"], "source_shot")
        self.assertEqual(b["_src"]["name"], {"zh": "The Verge", "en": "The Verge"})
        self.assertEqual(b["_src"]["date"], {"zh": "11 月 6 日", "en": "Nov 6"})      # 按事件卡来源的日期（UTC 那一天）
        self.assertEqual(b["_src"]["full"], QUOTE)

    def test_no_shot_falls_back(self):
        sb = storyboard([shot_block()])
        warn = run_checks(sb, self.issue)
        self.assertEqual(sb["chapters"][1]["blocks"][0]["type"], "source_excerpt")
        self.assertTrue(any("退回 source_excerpt" in w and "没有截图记录" in w for w in warn), warn)

    def test_failed_shot_falls_back_with_reason(self):
        write_shot(self.issue, "verge_nda", shot_block()["quote"], ok=False)
        sb = storyboard([shot_block()])
        warn = run_checks(sb, self.issue)
        self.assertEqual(sb["chapters"][1]["blocks"][0]["type"], "source_excerpt")
        self.assertTrue(any("人机验证" in w for w in warn), warn)

    def test_shot_of_other_quote_falls_back(self):
        write_shot(self.issue, "verge_nda", "something else")
        sb = storyboard([shot_block()])
        warn = run_checks(sb, self.issue)
        self.assertEqual(sb["chapters"][1]["blocks"][0]["type"], "source_excerpt")
        self.assertTrue(any("对不上" in w for w in warn), warn)

    def test_quote_must_be_verbatim(self):
        for q in ("it won't use non-disclosure agreements (NDAs) with public officials",      # 直撇号换了弯撇号
                  "it won’t use non-disclosure agreements with public officials",              # 删了一段
                  "OpenAI will stop using NDAs"):                                              # 改写
            sb = storyboard([shot_block(type="source_excerpt", quote=q)])
            with self.assertRaises(SystemExit) as cm:
                run_checks(sb, self.issue)
            self.assertIn("逐字", str(cm.exception))

    def test_zh_only_from_same_fact(self):
        sb = storyboard([shot_block(type="source_excerpt", zh="OpenAI 不再签保密协议")])
        with self.assertRaises(SystemExit) as cm:
            run_checks(sb, self.issue)
        self.assertIn("text_zh", str(cm.exception))
        sb = storyboard([shot_block(type="source_excerpt", zh=True)])
        run_checks(sb, self.issue)
        self.assertEqual(sb["chapters"][1]["blocks"][0]["_src"]["zh"], CARDS["E003"]["facts"][0]["text_zh"])

    def test_said_zh_for_who_said(self):
        b = shot_block(type="source_excerpt", id="aa", fact="e009.aa", source={"zh": "Artificial Analysis", "en": "Artificial Analysis"},
                       quote="the highest-scoring open weights model developed outside China", zh="得分最高的开源权重模型", cues={"show": "周四"})
        sb = storyboard([b])
        run_checks(sb, self.issue)
        self.assertEqual(sb["chapters"][1]["blocks"][0]["_src"]["zh"], "得分最高的开源权重模型")

    def test_source_label_must_match_card(self):
        sb = storyboard([shot_block(type="source_excerpt", source={"zh": "纽约时报", "en": "The New York Times"})])
        with self.assertRaises(SystemExit) as cm:
            run_checks(sb, self.issue)
        self.assertIn("出处签", str(cm.exception))

    def test_default_source_name(self):
        b = shot_block(type="source_excerpt")
        b.pop("source")
        sb = storyboard([b])
        run_checks(sb, self.issue)
        self.assertEqual(sb["chapters"][1]["blocks"][0]["_src"]["name"], {"zh": "The Verge", "en": "The Verge"})   # "The Verge · AI" 去掉栏目
        self.assertEqual(SB.source_name("OpenAI 新闻（官方公告）"), "OpenAI 新闻")

    def test_unknown_fact(self):
        sb = storyboard([shot_block(type="source_excerpt", fact="e003.nope")])
        with self.assertRaises(SystemExit):
            run_checks(sb, self.issue)

    def test_page_date_mismatch_drops_date(self):
        write_shot(self.issue, "verge_nda", shot_block()["quote"], page_date="2026-11-05T19:37:56-05:00")
        sb = storyboard([shot_block()])
        run_checks(sb, self.issue)
        b = sb["chapters"][1]["blocks"][0]
        self.assertIsNone(b["_src"]["date"])
        self.assertTrue(any("不是同一天" in w for w in SB.source_warnings(sb)))

    def test_cue_must_be_in_narration(self):
        import video_align
        sb = storyboard([shot_block(type="source_excerpt", cues={"show": "周五", "mark": "保密协议"})])
        run_checks(sb, self.issue)
        with self.assertRaises(SystemExit):
            SB.check_cues(sb, video_align.norm)

    def test_screen_text_counts_quote(self):          # 旁白里的数字出现在截图那句里也算"上了画面"
        b = shot_block(type="source_excerpt", id="x", fact="e003.vote", source={"zh": "CNBC", "en": "CNBC"},
                       quote="Out of 41 local ballot measures across 10 states", zh=None)
        self.assertIn("41", SB.screen_text({"blocks": [b]}))


class ChainAndCount(unittest.TestCase):
    def test_numbers_checked(self):
        with tempfile.TemporaryDirectory() as d:
            sb = storyboard([chain_block()])
            run_checks(sb, Path(d))                   # 10、41 都在事件卡原文里
            bad = chain_block()
            bad["items"][1]["label"] = LAB("42 项", "42 measures", "e003.vote")
            with self.assertRaises(SystemExit) as cm:
                run_checks(storyboard([bad]), Path(d))
            self.assertIn("42", str(cm.exception))
            noref = chain_block()
            noref["items"][0]["label"] = {"zh": "10 个州", "en": "10 states"}
            with self.assertRaises(SystemExit):
                run_checks(storyboard([noref]), Path(d))

    def test_too_few_items_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            b = chain_block()
            b["items"] = b["items"][:1]
            sb = storyboard([b, shot_block(type="source_excerpt")])
            warn = SB.structure(sb, Path(d))
            self.assertTrue(any("num_chain/vote_chain" in w and "至少 2 项" in w for w in warn), warn)

    def test_count_warnings(self):
        sb = storyboard([chain_block(count="yes"), {"type": "column_compare", "id": "c", "count": True, "items": []},
                         {"type": "quote_card", "id": "q", "text": LAB("只读", "Read-only"), "count": True}, {"type": "tally", "id": "t", "count": {"value": 3}}])
        w = SB.count_problems(sb)
        self.assertEqual(len(w), 3, w)                # tally 的 count 是计数字段，不算
        self.assertTrue(any("true 或 false" in x for x in w))
        self.assertTrue(any("只在 quote_card、num_chain" in x for x in w))
        self.assertTrue(any("没有数字" in x for x in w))

    def test_relation_counts_chain(self):
        sb = storyboard([chain_block()])
        sb["chapters"][1]["relation"] = {"kind": ["占比"], "zh": "…", "ref": ["e003.vote"]}
        must, _warn = SB.check_relations(sb)
        self.assertEqual(must, [])


class Headline(unittest.TestCase):
    def test_open_chapter_default_cue(self):
        with tempfile.TemporaryDirectory() as d:
            sb = storyboard([chain_block()], [head_block()])
            run_checks(sb, Path(d))
            b = sb["chapters"][0]["blocks"][0]
            self.assertEqual(b["items"][0]["cue"], "选票给数据中心设下闸门")     # 没写 cue 就用那一章的 map_cue
            keys = [k for k, _i, _s in SB.cue_list(sb)]
            self.assertIn("open.glance.items0", keys)

    def test_bad_chapter_or_wrong_kind(self):
        with tempfile.TemporaryDirectory() as d:
            sb = storyboard([chain_block(), head_block()], [head_block(items=[{"ch": "nope", "text": LAB("x", "x")}])])
            warn = SB.structure(sb, Path(d))
            self.assertEqual(sb["chapters"][0]["blocks"], [])
            self.assertEqual([b["type"] for b in sb["chapters"][1]["blocks"]], ["num_chain"])
            self.assertTrue(any("headline_open" in w and "story 章" in w for w in warn), warn)
            self.assertTrue(any("不能放在 story 章" in w for w in warn), warn)


class Compile(unittest.TestCase):
    def test_compiled_fields(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            issue = Path(d) / "2026-11-06"
            (issue / "06_配图").mkdir(parents=True)
            Image.new("RGB", (200, 120), (90, 120, 200)).save(issue / "06_配图" / "v_vote.png")
            write_shot(issue, "verge_nda", shot_block()["quote"])
            h = head_block()
            h["items"][0]["image"] = "v_vote"
            sb = storyboard([chain_block(), shot_block()], [h])
            run_checks(sb, issue)
            T = {"open.glance.items0": 5.0, "vote.vote_chain.items0": 1.0, "vote.vote_chain.items1": 2.0, "vote.vote_chain.items2": 3.0,
                 "vote.verge_nda.show": 4.0, "vote.verge_nda.mark": 4.5}
            marks = [{"voice_start": 0.2, "voice_end": 5.5, "end": 6.0}, {"voice_start": 6.5, "voice_end": 9.0, "end": 9.5},
                     {"voice_start": 9.6, "voice_end": 10.0, "end": 11.0}]
            photos = {}
            chs = SB.compile_chapters(sb, T, marks, photos)
            hd = chs[0]["blocks"][0]
            self.assertEqual(hd["items"][0]["label"], {"zh": "选票", "en": "The vote"})
            self.assertEqual(hd["items"][0]["img"], "glance.items0")
            self.assertEqual(hd["tag"]["zh"], "今日速览")
            self.assertEqual(hd["t"], {"items0": 5.0})
            ss = chs[1]["blocks"][1]
            self.assertEqual(ss["type"], "source_shot")
            self.assertEqual(ss["quote"], shot_block()["quote"])
            self.assertEqual(ss["src"]["name"]["zh"], "The Verge")
            self.assertEqual(ss["shot"]["img"], "shot.verge_nda")
            self.assertEqual(len(ss["shot"]["lines"]), 2)
            self.assertEqual(photos["shot.verge_nda"]["kind"], "screenshot")
            self.assertTrue((issue / "11_视频v3" / photos["shot.verge_nda"]["src"]).exists())
            for k in ("_src", "_shot", "fact", "cues"):
                self.assertNotIn(k, ss)
            self.assertIs(chs[1]["blocks"][0]["count"], True)


# ---------------------------------------------------------------- 结合式（11-06 深夜）
VQ = "it won’t use non-disclosure agreements (NDAs) with public officials"


def card_shot(**kw):
    s = {"fact": "e003.nda", "quote": VQ, "zh": "包括不再与公职人员使用保密协议（NDA）", "source": {"zh": "The Verge", "en": "The Verge"},
         "cues": {"mark": "不再和公职人员签保密协议"}}
    s.update(kw)
    return s


def post_block(**kw):
    b = {"type": "post_card", "id": "pc", "image": "v_vote", "platform": {"kind": "statement"},
         "text": LAB("不再和公职人员签保密协议", "No NDAs with public officials"), "who": {"name": LAB("OpenAI", "OpenAI")},
         "cues": {"show": "周四"}, "shot": card_shot()}
    b.update(kw)
    return b


def tl_block(shot=None):
    t2 = {"date": LAB("周四", "Thursday"), "cap": LAB("OpenAI 发布承诺", "OpenAI pledges"), "at": "周四", "image": "v_vote"}
    if shot is not None:
        t2["shot"] = shot
    return {"type": "timeline", "id": "nda", "ticks": [{"date": LAB("本周", "This week"), "cap": LAB("中期选举", "Midterms"), "at": "本周"}, t2]}


class Combined(unittest.TestCase):
    """原话卡带原文截图、时间轴日子带原文截图：检查和 source_shot 一样严，截图不能用就在同一个图位退回摘录。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.issue = Path(self.tmp.name) / "2026-11-06"
        (self.issue / "06_配图").mkdir(parents=True)
        from PIL import Image
        Image.new("RGB", (200, 120), (90, 120, 200)).save(self.issue / "06_配图" / "v_vote.png")

    def tearDown(self):
        self.tmp.cleanup()

    def test_card_shot_ok_replaces_image(self):
        write_shot(self.issue, "pc", VQ, font_px=20, clip={"w": 600}, w=1200, h=360)     # 卡片图位的截图是扁的（3.3:1）
        sb = storyboard([post_block()])
        warn = run_checks(sb, self.issue)
        b = sb["chapters"][1]["blocks"][0]
        self.assertNotIn("image", b)                              # 截图放进图位，原来的配图不用、不备
        self.assertEqual(b["_image_replaced"], "v_vote")
        self.assertIn("_shot", b["shot"])
        self.assertEqual(b["shot"]["_src"]["name"], {"zh": "The Verge", "en": "The Verge"})
        self.assertEqual(b["shot"]["_src"]["date"], {"zh": "11 月 6 日", "en": "Nov 6"})
        self.assertFalse(any("摘录" in w for w in warn), warn)
        keys = {k for k, _i, _s in SB.cue_list(sb)}
        self.assertIn("vote.pc.shot_mark", keys)
        self.assertTrue(SB.has_real_layer(sb["chapters"][1]))
        self.assertIn("原文截图:pc", SB.photo_moments(sb["chapters"][1])[0])
        self.assertEqual(SB.shot_budget(sb), [])
        self.assertIn("non-disclosure", SB.screen_text(sb["chapters"][1]))
        T = {"vote.pc.show": 3.0, "vote.pc.shot_mark": 4.0}
        marks = [{"voice_start": 0.2, "voice_end": 2.0, "end": 2.5}, {"voice_start": 2.6, "voice_end": 8.0, "end": 9.0},
                 {"voice_start": 9.1, "voice_end": 9.5, "end": 10.0}]
        photos = {}
        nb = SB.compile_chapters(sb, T, marks, photos)[1]["blocks"][0]
        self.assertEqual(nb["t"], {"show": 3.0, "shot_mark": 4.0})
        self.assertNotIn("img", nb)
        self.assertEqual(nb["shot"]["img"], "shot.pc")
        self.assertEqual(nb["shot"]["quote"], VQ)
        self.assertEqual(nb["shot"]["zh"], "包括不再与公职人员使用保密协议（NDA）")
        self.assertEqual(len(nb["shot"]["lines"]), 2)
        for k in ("_src", "_shot", "fact", "cues", "source"):
            self.assertNotIn(k, nb["shot"])
        self.assertEqual(photos["shot.pc"]["kind"], "screenshot")
        self.assertEqual([k for k in photos if not k.startswith("shot.")], [])      # 被替代的配图没有备

    def test_card_shot_missing_record_falls_back(self):
        sb = storyboard([post_block()])
        warn = run_checks(sb, self.issue)
        b = sb["chapters"][1]["blocks"][0]
        self.assertIn("没有截图记录", b["shot"]["_shot_fail"])
        self.assertTrue(any("改用原句摘录" in w for w in warn), warn)
        nb = SB.compile_chapters(sb, {"vote.pc.show": 3.0}, [{"voice_start": 0, "voice_end": 1, "end": 2}] * 3, {})[1]["blocks"][0]
        self.assertNotIn("img", nb["shot"])                       # 播放器排成摘录
        self.assertEqual(nb["shot"]["full"], QUOTE)

    def test_card_shot_too_small_falls_back(self):
        write_shot(self.issue, "pc", VQ, font_px=12, clip={"w": 1100})
        sb = storyboard([post_block()])
        warn = run_checks(sb, self.issue)
        self.assertIn("比字幕小", sb["chapters"][1]["blocks"][0]["shot"]["_shot_fail"])
        self.assertTrue(any("比字幕小" in w for w in warn), warn)

    def test_card_shot_checked_verbatim(self):
        for kw, word in (({"quote": "it won't use non-disclosure agreements (NDAs) with public officials"}, "逐字"),
                         ({"zh": "OpenAI 不签保密协议"}, "text_zh"), ({"source": {"zh": "纽约时报", "en": "NYT"}}, "出处签")):
            sb = storyboard([post_block(shot=card_shot(**kw))])
            with self.assertRaises(SystemExit) as cm:
                run_checks(sb, self.issue)
            self.assertIn(word, str(cm.exception))

    def test_card_shot_missing_fields_dropped(self):
        sb = storyboard([post_block(shot={"quote": VQ})])
        warn = run_checks(sb, self.issue)
        b = sb["chapters"][1]["blocks"][0]
        self.assertNotIn("shot", b)
        self.assertEqual(b["image"], "v_vote")                    # 卡片照旧
        self.assertTrue(any("缺字段" in w for w in warn), warn)

    def test_quote_card_shot(self):
        write_shot(self.issue, "q", VQ, font_px=20, clip={"w": 600}, w=1200, h=360)
        qb = {"type": "quote_card", "id": "q", "text": LAB("不再签保密协议", "No NDAs"), "who": LAB("OpenAI", "OpenAI"), "cues": {"show": "周四"},
              "shot": card_shot()}
        sb = storyboard([qb])
        run_checks(sb, self.issue)
        self.assertEqual(SB.check_text_cards(sb), [])             # 带截图的要点卡不算"只有字"

    def test_tick_shot(self):
        write_shot(self.issue, "nda_t1", VQ, font_px=18, clip={"w": 630}, w=1260, h=370)
        sb = storyboard([tl_block(card_shot())])
        warn = run_checks(sb, self.issue)
        tk = sb["chapters"][1]["blocks"][0]["ticks"][1]
        self.assertNotIn("image", tk)
        self.assertIn("_shot", tk["shot"])
        self.assertFalse(any("摘录" in w for w in warn), warn)
        keys = {k for k, _i, _s in SB.cue_list(sb)}
        self.assertIn("vote.nda.ticks1_mark", keys)
        T = {"vote.nda.ticks0": 3.0, "vote.nda.ticks1": 5.0, "vote.nda.ticks1_mark": 6.0}
        marks = [{"voice_start": 0.2, "voice_end": 2.0, "end": 2.5}, {"voice_start": 2.6, "voice_end": 8.0, "end": 9.0},
                 {"voice_start": 9.1, "voice_end": 9.5, "end": 10.0}]
        photos = {}
        nb = SB.compile_chapters(sb, T, marks, photos)[1]["blocks"][0]
        self.assertEqual(nb["ticks"][1]["shot"]["img"], "shot.nda_t1")
        self.assertEqual(nb["ticks"][1].get("img"), "nda.ticks1")      # 11-08（K46）：截图成功时这一天原来的配图留着当小图（截图只在弹出框里）
        self.assertEqual(nb["t"]["ticks1_mark"], 6.0)
        self.assertIn("原文截图:nda_t1", SB.photo_moments(sb["chapters"][1])[0])
        # 画面检查：日子上的截图从说到那一天起算"真东西"
        kinds = [k for _a, _z, k in SB._moments(sb["chapters"][1]["blocks"][0], {"ticks0": 3.0, "ticks1": 5.0})]
        self.assertIn("img", kinds)

    def test_tick_shot_fail_keeps_image(self):
        """11-07 补：日子上的截图截不成、退回摘录时，这一天原来的小图留着当小图（原来变成只写媒体名的白卡）；截成时照旧替代。"""
        sb = storyboard([tl_block(card_shot())])                  # 没有截图记录 → 退回摘录
        warn = run_checks(sb, self.issue)
        tk = sb["chapters"][1]["blocks"][0]["ticks"][1]
        self.assertIn("没有截图记录", tk["shot"]["_shot_fail"])
        self.assertEqual(tk["image"], "v_vote")
        self.assertNotIn("_image_replaced", tk)
        self.assertTrue(any("改用原句摘录" in w for w in warn), warn)
        self.assertIn("v_vote", SB.image_names(sb))               # 小图真的出现，算配图
        photos = {}
        T = {"vote.nda.ticks0": 3.0, "vote.nda.ticks1": 5.0}
        marks = [{"voice_start": 0.2, "voice_end": 2.0, "end": 2.5}, {"voice_start": 2.6, "voice_end": 8.0, "end": 9.0},
                 {"voice_start": 9.1, "voice_end": 9.5, "end": 10.0}]
        nt = SB.compile_chapters(sb, T, marks, photos)[1]["blocks"][0]["ticks"][1]
        self.assertEqual(nt["img"], "nda.ticks1")                 # 小图备好了
        self.assertNotIn("img", nt["shot"])                        # 弹出框里仍是摘录
        self.assertIn("nda.ticks1", photos)

    def test_tick_shot_cue_must_be_in_narration(self):
        import video_align
        sb = storyboard([tl_block(card_shot(cues={"mark": "周五"}))])
        run_checks(sb, self.issue)
        with self.assertRaises(SystemExit):
            SB.check_cues(sb, video_align.norm)

    def test_slot_sizes(self):
        self.assertAlmostEqual(SB.shot_slot_u("tick", 3.4), SB.TL_SHOT_U - 1.5)
        self.assertAlmostEqual(SB.shot_slot_u("card", 4.0, {"type": "quote_card", "text": LAB("美国开放权重编程第一", "x")}), SB.SBX_CARD_U - SB.SBX_PAD_U)
        tall = SB.shot_slot_u("card", 1.2, {"type": "post_card", "text": LAB("权" * 60, "x"), "who": {"role": LAB("负责人", "x")}})
        self.assertLess(tall, SB.SBX_CARD_U - SB.SBX_PAD_U)       # 截图太高、字太多：卡片收窄
        self.assertGreater(SB.shot_slot_u("full", 1.78), 60)
        self.assertIsNone(SB.shot_font_u({"w": 10, "h": 5}, "tick"))     # 旧记录没有字号：不查

    def test_trial_tick_op_and_items(self):
        import video3_trial as TR
        sb = storyboard([tl_block(), post_block()])
        log = TR.apply_spec(sb, {"ops": [{"chapter": "vote", "set": "nda", "tick": 1, "fields": {"shot": card_shot(), "image": None}}]})
        self.assertIn("nda 第 2 个日子", log[0])
        tk = sb["chapters"][1]["blocks"][0]["ticks"][1]
        self.assertIn("shot", tk)
        self.assertNotIn("image", tk)
        with self.assertRaises(SystemExit):
            TR.apply_spec(copy.deepcopy(sb), {"ops": [{"chapter": "vote", "set": "nda", "tick": 5, "fields": {"x": 1}}]})
        (self.issue / "03_事件卡").mkdir()
        (self.issue / "03_事件卡" / "cards_写稿用.json").write_text(json.dumps(list(CARDS.values()), ensure_ascii=False), encoding="utf-8")
        items = TR.shot_items(self.issue, sb)
        self.assertEqual([(x["id"], x["slot"]) for x in items], [("nda_t1", "tick"), ("pc", "card")])
        self.assertTrue(all(x["url"].startswith("https://www.theverge.com/") for x in items))


# ---------------------------------------------------------------- 配图＋动效结合版（11-07）：压在配图上、尝试版生图
def tile_block(**kw):
    b = {"type": "tile_row", "id": "row", "head": LAB("两边的说法", "Two sides"),
         "items": [{"title": LAB("选民", "Voters"), "sub": LAB("都站在限制一边", "Backed curbs"), "kind": "plain", "cue": "选民"},
                   {"title": LAB("OpenAI", "OpenAI"), "sub": LAB("不再签保密协议", "No NDAs"), "kind": "plain", "cue": "周四"}],
         "cues": {"head": "本周中期选举"}}
    b.update(kw)
    return b


def panel_block(**kw):
    b = {"type": "compare_panel", "id": "cp", "head": LAB("地方投票措施", "Local measures"), "src_tag": LAB("Ballotpedia", "Ballotpedia"),
         "kpi": {"value": "41 项", "text": LAB("10 个州", "10 states", "e003.vote")},
         "bars": [{"label": LAB("投票措施", "Measures"), "value": 1.0, "me": True, "val": LAB("41 项", "41", "e003.vote")},
                  {"label": LAB("州", "States"), "value": 0.25, "val": LAB("10 个", "10", "e003.vote")}],
         "cues": {"show": "10 个州"}}
    b.update(kw)
    return b


class PhotoBacked(unittest.TestCase):
    """tile_row、compare_panel 写 photo（压在配图上）：检查一侧认得这张图（真东西、清楚露脸、配图张数），编进播放器的是 photo_img。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.issue = Path(self.tmp.name) / "2026-11-06"
        (self.issue / "06_配图" / "视频").mkdir(parents=True)
        from PIL import Image
        Image.new("RGB", (320, 180), (90, 120, 200)).save(self.issue / "06_配图" / "视频" / "v_hbm.png")

    def tearDown(self):
        self.tmp.cleanup()

    def test_photo_counts_and_compiles(self):
        sb = storyboard([tile_block(photo="v_hbm", cues={"head": "本周中期选举", "photo": "本周中期选举"}), panel_block(photo="v_hbm")])
        warn = run_checks(sb, self.issue)
        self.assertFalse(any("photo" in w for w in warn), warn)
        c = sb["chapters"][1]
        self.assertTrue(SB.has_real_layer(c))
        self.assertIn("v_hbm", SB.photo_moments(c)[0])
        self.assertEqual(SB.image_names(sb), ["v_hbm"])
        kinds = [k for _a, _z, k in SB._moments(c["blocks"][0], {"photo": 3.0, "head": 3.2, "items0": 4.0})]
        self.assertIn("img", kinds)
        self.assertIn("vote.row.photo", {k for k, _i, _s in SB.cue_list(sb)})
        T = {"vote.row.photo": 3.0, "vote.row.head": 3.2, "vote.row.items0": 4.0, "vote.row.items1": 5.0, "vote.cp.show": 6.0}
        marks = [{"voice_start": 0.2, "voice_end": 2.0, "end": 2.5}, {"voice_start": 2.6, "voice_end": 8.0, "end": 9.0},
                 {"voice_start": 9.1, "voice_end": 9.5, "end": 10.0}]
        photos = {}
        nbs = SB.compile_chapters(sb, T, marks, photos)[1]["blocks"]
        self.assertEqual([nb.get("photo_img") for nb in nbs], ["row.photo", "cp.photo"])
        self.assertEqual(nbs[0]["t"]["photo"], 3.0)
        self.assertIn("row.photo", photos)
        self.assertEqual(nbs[1]["bars"][0]["val"], {"zh": "41 项", "en": "41"})
        self.assertEqual(nbs[1]["src_tag"], {"zh": "Ballotpedia", "en": "Ballotpedia"})

    def test_missing_photo_dropped(self):
        sb = storyboard([tile_block(photo="v_none")])
        warn = run_checks(sb, self.issue)
        self.assertNotIn("photo", sb["chapters"][1]["blocks"][0])
        self.assertTrue(any("找不到配图 v_none" in w for w in warn), warn)

    def test_val_numbers_checked(self):
        sb = storyboard([panel_block(bars=[{"label": LAB("支持限制", "Curbs"), "value": 1.0, "val": LAB("39 项", "39", "e003.vote")}])])
        with self.assertRaises(SystemExit):
            run_checks(sb, self.issue)

    def test_without_photo_unchanged(self):
        """不写 photo / src_tag / val：编出来的数据里没有新字段（播放器走原来的路）。"""
        sb = storyboard([tile_block(), panel_block(src_tag=None, bars=[{"label": LAB("支持限制", "Curbs"), "value": 1.0}])])
        sb["chapters"][1]["blocks"][1].pop("src_tag")
        run_checks(sb, self.issue)
        nbs = SB.compile_chapters(sb, {"vote.row.head": 3.2, "vote.cp.show": 6.0}, [{"voice_start": 0, "voice_end": 1, "end": 2}] * 3, {})[1]["blocks"]
        for nb in nbs:
            self.assertFalse({"photo_img", "photo", "src_tag"} & set(nb), nb)
        self.assertNotIn("val", nbs[1]["bars"][0])


class TrialImages(unittest.TestCase):
    """尝试版命令：加块说明的 image_requests、--gen-images 照正式流程生图、--reuse-images 留住上次画的图。"""

    def test_spec_image_requests(self):
        import video3_trial as TR
        sb = storyboard([tile_block()])
        sb["image_requests"] = [{"id": "v_old", "brief_en": "x", "placement": "tile"}]
        log = TR.apply_spec(sb, {"image_requests": [{"id": "v_new", "brief_en": "a lab bench", "placement": "card", "events": ["E003"]}], "ops": []})
        self.assertEqual([r["id"] for r in sb["image_requests"]], ["v_old", "v_new"])
        self.assertIn("image_requests 加 v_new（生成）", log)
        with self.assertRaises(SystemExit):
            TR.apply_spec(copy.deepcopy(sb), {"image_requests": [{"id": "v_old", "brief_en": "y", "placement": "tile"}]})
        sb2 = storyboard([tile_block()])
        TR.apply_spec(sb2, {"ops": []})
        self.assertNotIn("image_requests", sb2)                   # 不写就不碰

    def test_gen_images_uses_ensure(self):
        import video3_trial as TR
        import video3_images as IMG
        got = {}
        orig = IMG.ensure
        IMG.ensure = lambda issue, reqs, accent, gen=True, redo=(): got.update(issue=issue, ids=[r["id"] for r in reqs], gen=gen) or {}
        try:
            sb = storyboard([tile_block(photo="v_new")])
            sb["image_requests"] = [{"id": "v_new", "brief_en": "a lab bench", "placement": "card"}]
            TR.gen_images(Path("/nonexistent"), sb)
        finally:
            IMG.ensure = orig
        self.assertEqual(got["ids"], ["v_new"])
        self.assertTrue(got["gen"])

    def test_reuse_images(self):
        import video3_trial as TR
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src, dst, bin_ = d / "src", d / "dst", d / "bin"
            (src / "04_文稿").mkdir(parents=True)
            (src / "04_文稿" / "视频v3_分镜.json").write_text("{}", encoding="utf-8")
            bin_.mkdir()
            moved = []

            def fake_trash(p):                                    # 测试里不往用户的废纸篓里放东西
                p = Path(p)
                if not p.exists():
                    return None
                t = bin_ / ("%s_%d" % (p.name, len(moved)))
                shutil.move(str(p), str(t))
                moved.append(t)
                return t
            orig = TR.trash
            TR.trash = fake_trash
            try:
                (dst / TR.IMG_DIR).mkdir(parents=True)
                (dst / TR.IMG_DIR / "v_new.png").write_bytes(b"png")
                (dst / TR.IMG_DIR / "来源.json").write_text(json.dumps({"v_new": {"kind": "generated"}}), encoding="utf-8")
                TR.copy_issue(src, dst, keep_shots=False, keep_images=True)
                self.assertEqual((dst / TR.IMG_DIR / "v_new.png").read_bytes(), b"png")
                self.assertIn("v_new", json.loads((dst / TR.IMG_DIR / "来源.json").read_text(encoding="utf-8")))
                TR.copy_issue(src, dst, keep_shots=False)          # 不写 --reuse-images：照原期重新复制，图不留
                self.assertFalse((dst / TR.IMG_DIR / "v_new.png").exists())
            finally:
                TR.trash = orig


def node_eval(src):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("没有 node")
    return json.loads(subprocess.run([node, "-e", src], capture_output=True, text=True, check=True).stdout)


class RendererFunctions(unittest.TestCase):
    """video3.js 里的 countHtml、chainNum：终值写法要和原标签一字不差（80.52、3200 万、94.49%、1,200）。"""

    def test_count_html(self):
        js = JS.read_text(encoding="utf-8")
        esc = re.search(r"\n  var esc = function \(s\) \{.*?\n  \};\n", js, re.S).group(0)
        fn = re.search(r"\n  function countHtml\(s\) \{.*?\n  \}\n", js, re.S).group(0)
        ch = re.search(r"\n  function chainNum\(s, cnt\) \{.*?\n  \}\n", js, re.S).group(0)
        src = esc + fn + ch + ("console.log(JSON.stringify(['研发成本 3200 万美元', '80.52', '94.49%', '1,200 台', '只读'].map(function (s) { var r = countHtml(s); "
                               "return [r.v, r.dec, r.fin, r.html]; }).concat([chainNum('41 项', true).html, chainNum('除一项外', true).html])));")
        out = node_eval(src)
        self.assertEqual(out[0][:3], [3200, 0, "3200"])
        self.assertIn('data-c="3200">0</span> 万美元', out[0][3])
        self.assertEqual(out[1][:3], [80.52, 2, "80.52"])
        self.assertEqual(out[2][:3], [94.49, 2, "94.49"])
        self.assertIn("</span>%", out[2][3])                   # 单位留在外面
        self.assertEqual(out[3][:3], [1200, 0, "1,200"])
        self.assertIsNone(out[4][0])
        self.assertIn('class="n v3n"', out[5])
        self.assertIn('class="w"', out[6])


def plain(x):
    """11-09 晚：中文整词换行开着时，画面文字的 textContent 里多了换行点（U+200B、U+2060）、数字和单位之间是不换行空格；
    这几项查的是字对不对，比之前先去掉这些看不见的记号。"""
    if isinstance(x, str):
        return x.replace("\u200b", "").replace("\u2060", "").replace("\u00a0", " ")
    if isinstance(x, list):
        return [plain(v) for v in x]
    if isinstance(x, dict):
        return {k: plain(v) for k, v in x.items()}
    return x


def can_browse():
    return shutil.which("node") and Path(PW).exists() and Path("/Applications/Google Chrome.app").exists()


@unittest.skipUnless(can_browse(), "没有 node / Playwright / Chrome")
class Browser(unittest.TestCase):
    """把 11-06 的演示页复制到临时目录，往数据里加四种新块（时间是手写的），用本机 Chrome 渲几个时刻看状态。"""

    def test_new_blocks_render(self):
        src = ROOT / "测试版" / "2026-11-06" / "11_视频v3"
        if not (src / "data.js").exists():
            self.skipTest("没有 11-06 的演示页")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "11_视频v3"
            shutil.copytree(src, out)
            shutil.copy2(ROOT / "site" / "v3" / "video3.js", out / "video3.js")
            shutil.copy2(ROOT / "site" / "v3" / "video3.css", out / "video3.css")
            s = (out / "data.js").read_text(encoding="utf-8")
            m = re.search(r"window\.FD_VIDEO3 = (\{.*\});\s*$", s, re.S)
            data = json.loads(m.group(1))
            ch = {c["id"]: c for c in data["chapters"]}
            img_key = next(k for k, v in data["images"].items() if not v.get("depth"))
            data["images"]["shot.test"] = dict(data["images"][img_key], kind="screenshot")
            ch["open"]["blocks"] = [{"type": "headline_open", "id": "glance", "t": {"items0": 5.0, "items1": 7.6},
                                     "tag": {"zh": "今日速览", "en": "Today at a glance"},
                                     "items": [{"ch": "vote", "text": {"zh": "选票给数据中心设下闸门"}, "label": {"zh": "选票"}, "img": img_key},
                                               {"ch": "code", "text": {"zh": "开放权重在争第一"}, "label": {"zh": "开放权重"}}]}]
            vb = ch["vote"]["blocks"]
            i = next(k for k, b in enumerate(vb) if b["type"] == "tally")
            vb[i] = {"type": "num_chain", "id": "vote_chain", "count": True, "head": {"zh": "数据中心地方投票措施"},
                     "t": {"items0": 19.2, "items1": 20.3, "items2": 22.2},
                     "items": [{"label": {"zh": "10 个州"}}, {"label": {"zh": "41 项"}}, {"label": {"zh": "除一项外"}}]}
            vb.insert(i + 1, {"type": "source_shot", "id": "verge", "t": {"show": 27.0, "mark": 27.4}, "quote": "it won’t use NDAs",
                              "full": "including that it won’t use NDAs with public officials.", "zh": "不再与公职人员使用保密协议",
                              "src": {"name": {"zh": "The Verge"}, "date": {"zh": "11 月 6 日"}},
                              "shot": {"img": "shot.test", "w": 1600, "h": 900, "lines": [[0.1, 0.4, 0.7, 0.06], [0.1, 0.47, 0.3, 0.06]]}})
            cb = ch["code"]["blocks"]
            k = next(k for k, b in enumerate(cb) if b["id"] == "ripple")
            cb[k] = {"type": "source_excerpt", "id": "ripple", "t": {"show": 40.6, "mark": 46.2}, "quote": "achieving U.S. open-weight state-of-the-art (80.52)",
                     "full": "Ripple-65B Preview delivers strong results on agentic coding, achieving U.S. open-weight state-of-the-art (80.52) on TerminalBench 2.1",
                     "src": {"name": {"zh": "Ricursive Intelligence"}, "date": {"zh": "11 月 4 日"}}}
            next(b for b in cb if b["id"] == "cost")["count"] = True
            (out / "data.js").write_text("window.FD_VIDEO3 = %s;\n" % json.dumps(data, ensure_ascii=False), encoding="utf-8")
            probe = r"""
import path from 'path'; import { pathToFileURL } from 'url';
const { chromium } = await import(pathToFileURL(process.env.PW).href);
const b = await chromium.launch({ channel: 'chrome', headless: true });
const p = await (await b.newContext({ viewport: { width: 1280, height: 720 } })).newPage();
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
await p.goto(pathToFileURL(process.argv[2]).href + '?rec=1&eager=1&theme=light');
await p.waitForFunction(() => window.__v3 && window.__v3.world, null, { timeout: 30000 });
await p.waitForTimeout(800);
const at = async (t, fn) => p.evaluate(([t, fn]) => { window.__v3.renderAt(t); return (new Function('return ' + fn))()(); }, [t, fn.toString()]);
const r = {};
r.hlBefore = await at(2.0, () => getComputedStyle(document.querySelector('.v3hl')).visibility);
r.hlOn = await at(6.0, () => [getComputedStyle(document.querySelector('.v3hl')).visibility, document.querySelector('.v3hl .tg').textContent,
  getComputedStyle(document.querySelector('.v3hl .it[data-i="0"]')).opacity]);
r.hlOff = await at(16.0, () => getComputedStyle(document.querySelector('.v3hl')).visibility);
r.chain = await at(24.0, () => [...document.querySelectorAll('.v3chain .it')].map(e => e.textContent.replace(/\s+/g, '')));
r.chainMid = await at(19.3, () => document.querySelector('.v3chain .it[data-i="0"] [data-c]').textContent);
r.hl = await at(30.0, () => [...document.querySelectorAll('.v3src i.hl')].map(e => getComputedStyle(e).transform));
r.hl0 = await at(27.2, () => [...document.querySelectorAll('.v3src i.hl')].map(e => getComputedStyle(e).transform));
r.tag = await at(30.0, () => document.querySelector('.v3src .tag').textContent);
r.mark = await at(49.0, () => getComputedStyle(document.querySelector('.v3src.exc mark.hl')).backgroundSize);
r.cost = await at(68.0, () => document.querySelector('.v3qc [data-c]') && document.querySelector('.v3qc [data-c]').closest('.hd').textContent);
r.errs = errs;
console.log(JSON.stringify(r));
await b.close();
"""
            js = Path(d) / "probe.mjs"
            js.write_text(probe, encoding="utf-8")
            res = subprocess.run(["node", str(js), str(out / "index.html")], capture_output=True, text=True, env=dict(os.environ, PW=PW), timeout=180)
            self.assertEqual(res.returncode, 0, res.stderr[-2000:])
            r = plain(json.loads(res.stdout.strip().splitlines()[-1]))
            self.assertEqual(r["errs"], [])
            self.assertEqual(r["hlBefore"], "hidden")
            self.assertEqual(r["hlOn"][0], "visible")
            self.assertIn("今日速览", r["hlOn"][1])
            self.assertEqual(r["hlOff"], "hidden")
            self.assertEqual(r["chain"], ["10个州", "41项", "除一项外"])
            self.assertNotEqual(r["chainMid"], "10")                   # 说到时正在从 0 往上滚
            self.assertTrue(all(x in ("none", "matrix(1, 0, 0, 1, 0, 0)") for x in r["hl"]), r["hl"])   # 荧光笔扫完
            self.assertTrue(any(x.startswith("matrix(0") for x in r["hl0"]), r["hl0"])                    # 扫之前是 0 宽
            self.assertIn("The Verge", r["tag"])
            self.assertTrue(r["mark"].startswith("100%"), r["mark"])
            self.assertEqual(r["cost"], "研发成本 3200 万美元")


    def test_combined_render(self):
        """结合式：帖子卡图位放截图、要点卡图位放摘录、时间轴"周四"弹出截图；查弹出框的位置大小、荧光扫完、缩回，卡片截图够宽。"""
        src = ROOT / "测试版" / "2026-11-06" / "11_视频v3"
        if not (src / "data.js").exists():
            self.skipTest("没有 11-06 的演示页")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "11_视频v3"
            shutil.copytree(src, out)
            shutil.copy2(ROOT / "site" / "v3" / "video3.js", out / "video3.js")
            shutil.copy2(ROOT / "site" / "v3" / "video3.css", out / "video3.css")
            s = (out / "data.js").read_text(encoding="utf-8")
            data = json.loads(re.search(r"window\.FD_VIDEO3 = (\{.*\});\s*$", s, re.S).group(1))
            ch = {c["id"]: c for c in data["chapters"]}
            img_key = next(k for k, v in data["images"].items() if not v.get("depth"))
            data["images"]["shot.t"] = dict(data["images"][img_key], kind="screenshot")
            src_lab = {"name": {"zh": "The Verge", "en": "The Verge"}, "date": {"zh": "11 月 6 日", "en": "Nov 6"}}
            shot = {"src": src_lab, "quote": VQ, "full": QUOTE, "zh": "包括不再与公职人员使用保密协议（NDA）", "img": "shot.t",
                    "lines": [[0.34, 0.59, 0.62, 0.12], [0.03, 0.75, 0.27, 0.12]], "w": 1260, "h": 370}
            nda = next(b for b in ch["vote"]["blocks"] if b["type"] == "timeline")
            nda["ticks"][2]["shot"] = shot
            nda["ticks"][2].pop("img", None)
            nda["t"]["ticks2_mark"] = 27.3
            aa = next(b for b in ch["contrast"]["blocks"] if b["id"] == "aa")
            aa["shot"] = dict(shot, w=1834, h=436, zh=None)
            aa.pop("img", None)
            aa["t"]["shot_mark"] = 119.6
            rp = next(b for b in ch["code"]["blocks"] if b["id"] == "ripple")
            rp["shot"] = {"src": {"name": {"zh": "Ricursive Intelligence"}, "date": {}}, "quote": "achieving U.S. open-weight state-of-the-art (80.52)",
                          "full": "Ripple-65B Preview delivers strong results on agentic coding, achieving U.S. open-weight state-of-the-art (80.52) on TerminalBench 2.1"}
            rp.pop("img", None)
            rp["t"]["shot_mark"] = 46.2
            (out / "data.js").write_text("window.FD_VIDEO3 = %s;\n" % json.dumps(data, ensure_ascii=False), encoding="utf-8")
            probe = r"""
import { pathToFileURL } from 'url';
const { chromium } = await import(pathToFileURL(process.env.PW).href);
const b = await chromium.launch({ channel: 'chrome', headless: true });
const p = await (await b.newContext({ viewport: { width: 1280, height: 720 } })).newPage();
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
await p.goto(pathToFileURL(process.argv[2]).href + '?rec=1&eager=1&theme=light');
await p.waitForFunction(() => window.__v3 && window.__v3.world, null, { timeout: 30000 });
await p.waitForTimeout(800);
const at = async (t, fn) => p.evaluate(([t, fn]) => { window.__v3.renderAt(t); return (new Function('return ' + fn))()(); }, [t, fn.toString()]);
const pop = () => { const e = document.querySelector('.v3tpop'), r = e.getBoundingClientRect(), st = getComputedStyle(e), w = document.querySelector('.v3world').getBoundingClientRect();
  const th = document.querySelector('.v3tick.wshot .ph');
  return { vis: st.visibility, op: +st.opacity, l: r.left - w.left, w: r.width, top: r.top - w.top, bottom: r.bottom - w.top, stageW: w.width, stageH: w.height,
    th: th ? th.style.opacity : null, hl: [...e.querySelectorAll('i.hl')].map(x => getComputedStyle(x).transform) }; };
const r = {};
r.before = await at(25.0, pop);
r.out = await at(27.0, pop);
r.swept = await at(29.4, pop);
r.back = await at(31.4, pop);
r.card = await at(121.8, () => { const e = document.querySelector('.v3post.v3sbxc .v3sbx .shot'), s = document.querySelector('.v3world').getBoundingClientRect();
  return e ? { w: e.getBoundingClientRect().width, stageW: s.width, hl: [...document.querySelectorAll('.v3post.v3sbxc i.hl')].map(x => getComputedStyle(x).transform),
    q: document.querySelector('.v3post.v3sbxc .q').textContent, tag: document.querySelector('.v3post.v3sbxc .tag').textContent } : null; });
r.exc = await at(49.0, () => { const m = document.querySelector('.v3qc.v3sbxc.exc mark.hl'); return m ? [getComputedStyle(m).backgroundSize, document.querySelector('.v3qc.v3sbxc .hd').textContent] : null; });
r.errs = errs;
console.log(JSON.stringify(r));
await b.close();
"""
            js = Path(d) / "probe.mjs"
            js.write_text(probe, encoding="utf-8")
            res = subprocess.run(["node", str(js), str(out / "index.html")], capture_output=True, text=True, env=dict(os.environ, PW=PW), timeout=180)
            self.assertEqual(res.returncode, 0, res.stderr[-2000:])
            r = plain(json.loads(res.stdout.strip().splitlines()[-1]))
            self.assertEqual(r["errs"], [])
            self.assertEqual(r["before"]["vis"], "hidden")                    # 说到"周四"之前不出
            o = r["out"]
            self.assertEqual(o["vis"], "visible")
            self.assertAlmostEqual(o["w"] / o["stageW"], SB.TL_SHOT_U / 100, delta=0.01)      # 弹出框横屏 70u 宽
            self.assertAlmostEqual(o["l"] + o["w"] / 2, o["stageW"] / 2, delta=3)          # 居中
            self.assertGreater(o["top"], 0)
            self.assertLess(o["bottom"], o["stageH"] * 0.9)                                 # 下沿不压字幕
            self.assertEqual(o["th"], "0")                                                  # 小图"飞"出去了
            self.assertTrue(any(x.startswith("matrix(0") for x in o["hl"]), o["hl"])       # 还没扫
            self.assertTrue(all(x in ("none", "matrix(1, 0, 0, 1, 0, 0)") for x in r["swept"]["hl"]), r["swept"]["hl"])
            self.assertEqual(r["back"]["vis"], "hidden")                                    # 缩回小图
            self.assertEqual(r["back"]["th"], "")
            c = r["card"]
            self.assertIsNotNone(c)
            want = SB.shot_slot_u("card", 1834 / 436, {"type": "post_card", "text": {"zh": c["q"].strip("“”")}, "who": {}})
            self.assertGreaterEqual(c["w"] / c["stageW"] * 100, want - 1.5, (c["w"], want))  # 分镜检查估的截图宽不比实际宽
            self.assertTrue(all(x in ("none", "matrix(1, 0, 0, 1, 0, 0)") for x in c["hl"]), c["hl"])
            self.assertIn("The Verge", c["tag"])
            self.assertIsNotNone(r["exc"])
            self.assertTrue(r["exc"][0].startswith("100%"), r["exc"])                     # 截不到：要点卡图位里是摘录，荧光扫完
            self.assertIn("美国开放权重编程第一", r["exc"][1])


    def test_photo_backed_render(self):
        """11-07：小卡一排、对比卡压在配图上（photo_img）：配图出现又收起、卡片在画面里、出处签和条尾的数在；
        时间轴日子截图截不成时，小图位里是原来的配图（不是只写媒体名的白卡）。"""
        src = ROOT / "测试版" / "2026-11-06" / "11_视频v3"
        if not (src / "data.js").exists():
            self.skipTest("没有 11-06 的演示页")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "11_视频v3"
            shutil.copytree(src, out)
            shutil.copy2(ROOT / "site" / "v3" / "video3.js", out / "video3.js")
            shutil.copy2(ROOT / "site" / "v3" / "video3.css", out / "video3.css")
            s = (out / "data.js").read_text(encoding="utf-8")
            data = json.loads(re.search(r"window\.FD_VIDEO3 = (\{.*\});\s*$", s, re.S).group(1))
            ch = {c["id"]: c for c in data["chapters"]}
            vb = ch["vote"]["blocks"]
            i = next(k for k, b in enumerate(vb) if b["type"] == "tally")
            vb[i] = {"type": "tile_row", "id": "ballot", "photo_img": "lehane", "head": {"zh": "两边的说法"}, "t": {"photo": 19.6, "head": 20.2, "items0": 20.8, "items1": 21.6},
                     "items": [{"title": {"zh": "选民"}, "sub": {"zh": "都站在限制一边"}, "kind": "plain"}, {"title": {"zh": "OpenAI"}, "sub": {"zh": "不再签保密协议"}, "kind": "plain"}]}
            nda = next(b for b in vb if b["type"] == "timeline")
            nda["ticks"][2]["shot"] = {"src": {"name": {"zh": "The Verge"}, "date": {}}, "quote": VQ, "full": QUOTE}     # 截图截不成：没有 img
            nda["ticks"][2]["img"] = "nda.ticks1"                                                               # 这一天原来的小图
            pb = ch["permit"]["blocks"]
            k = next(k for k, b in enumerate(pb) if b["id"] == "scope")
            pb[k] = {"type": "compare_panel", "id": "scope", "photo_img": "matin", "src_tag": {"zh": "Counterpoint Research"}, "head": {"zh": "目标带宽"},
                     "kpi": {"value": "约 3 倍", "text": {"zh": "于 HBM5E（目标）"}}, "t": {"show": 79.3},
                     "bars": [{"label": {"zh": "HBM5E"}, "value": 0.333, "val": {"zh": "1"}}, {"label": {"zh": "DRAM-on-logic"}, "value": 1.0, "me": True, "val": {"zh": "约 3"}}]}
            (out / "data.js").write_text("window.FD_VIDEO3 = %s;\n" % json.dumps(data, ensure_ascii=False), encoding="utf-8")
            probe = r"""
import { pathToFileURL } from 'url';
const { chromium } = await import(pathToFileURL(process.env.PW).href);
const b = await chromium.launch({ channel: 'chrome', headless: true });
const p = await (await b.newContext({ viewport: { width: 1280, height: 720 } })).newPage();
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
await p.goto(pathToFileURL(process.argv[2]).href + '?rec=1&eager=1&theme=light');
await p.waitForFunction(() => window.__v3 && window.__v3.world, null, { timeout: 30000 });
await p.waitForTimeout(800);
const at = async (t, fn) => p.evaluate(([t, fn]) => { window.__v3.renderAt(t); return (new Function('return ' + fn))()(); }, [t, fn.toString()]);
const ph = (id) => () => { const bl = window.__v3.world.blocks.find(x => x.id === ID); return bl && bl._.o.ovp ? +bl._.o.ovp.material.uniforms.uReveal.value.toFixed(2) : null; };
const inStage = (sel) => `() => { const w = document.querySelector('.v3world').getBoundingClientRect();
  return [...document.querySelectorAll(${JSON.stringify(sel)})].filter(e => getComputedStyle(e.closest('.v3l')).visibility === 'visible').map(e => { const r = e.getBoundingClientRect();
    return r.left >= w.left - 1 && r.right <= w.right + 1 && r.top >= w.top - 1 && r.bottom <= w.bottom - w.height * 0.08; }); }`;
const r = {};
r.tBefore = await at(18.0, ph().toString().replace('ID', "'ballot'"));
r.thumb = await at(31.0, () => { const e = document.querySelectorAll('.v3tick')[2].querySelector('.ph'); const i = e && e.querySelector('i');
  return e ? [e.className, i ? getComputedStyle(i).backgroundImage.slice(0, 4) : null, !!e.querySelector('span')] : null; });
r.tOn = await at(23.0, ph().toString().replace('ID', "'ballot'"));
r.tiles = await at(23.0, inStage('.v3tc.ovp'));
r.tileSub = await at(23.0, () => [...document.querySelectorAll('.v3tc.ovp .sb')].map(e => e.textContent));
r.tOff = await at(36.0, ph().toString().replace('ID', "'ballot'"));
r.pOn = await at(83.0, ph().toString().replace('ID', "'scope'"));
r.panel = await at(83.0, () => { const c = document.querySelector('.v3cp.ovp'); return c ? [c.querySelector('.stag').textContent, [...c.querySelectorAll('.bar .v')].map(e => e.textContent),
  [...c.querySelectorAll('[data-bar]')].map(e => getComputedStyle(e).transform)] : null; });
r.pIn = await at(83.0, inStage('.v3cp.ovp'));
r.errs = errs;
console.log(JSON.stringify(r));
await b.close();
"""
            js = Path(d) / "probe.mjs"
            js.write_text(probe, encoding="utf-8")
            res = subprocess.run(["node", str(js), str(out / "index.html")], capture_output=True, text=True, env=dict(os.environ, PW=PW), timeout=180)
            self.assertEqual(res.returncode, 0, res.stderr[-2000:])
            r = plain(json.loads(res.stdout.strip().splitlines()[-1]))
            self.assertEqual(r["errs"], [])
            self.assertEqual(r["tBefore"], 0)                                 # 配图在 photo 触发词前不出
            self.assertGreater(r["tOn"], 1.0)                                 # 说到以后整张显出来
            self.assertEqual(r["tOff"], 0)                                    # 这一块收场后收起
            self.assertTrue(r["tiles"] and all(r["tiles"]), r["tiles"])      # 小卡都在画面里、不压字幕区
            self.assertEqual(r["tileSub"], ["都站在限制一边", "不再签保密协议"])
            self.assertGreater(r["pOn"], 1.0)
            self.assertEqual(r["panel"][0], "Counterpoint Research")
            self.assertEqual(r["panel"][1], ["1", "约 3"])
            self.assertTrue(all(x != "none" and not x.startswith("matrix(0,") for x in r["panel"][2]), r["panel"][2])   # 对比条长出来了
            self.assertTrue(r["pIn"] and all(r["pIn"]), r["pIn"])
            self.assertIsNotNone(r["thumb"])
            self.assertNotIn("exc", r["thumb"][0])                            # 截不成：小图位里不是白卡
            self.assertEqual(r["thumb"][1], "url(")                          # 是原来那张配图
            self.assertFalse(r["thumb"][2])

    def test_crop_whole_blocks(self):
        """截图裁切（11-06 深夜改）：本机起一个仿新闻页（页眉、署名栏、正文、按钮、图片），裁框上下边不能切到任何东西，
        页眉、署名栏不进图；段落太长时裁在段内两行之间。只连 127.0.0.1，不联网。"""
        import functools
        import http.server
        import threading
        from PIL import Image
        para = ("Following this week’s midterms where voters resoundingly voiced their opposition to data center expansion, OpenAI today "
                "announced new commitments to communities where it is working on data center projects, including that it won’t use "
                "non-disclosure agreements (NDAs) with public officials.")
        long_p = " ".join(["Filler sentence number %d keeps this paragraph going for a long while." % i for i in range(40)]) + " " + \
                 "The quoted line sits right here in the middle of a very long paragraph. " + \
                 " ".join(["More filler %d follows the quote." % i for i in range(30)])
        html = """<!doctype html><meta charset="utf-8"><style>body{margin:0;font:20px/1.6 Georgia,serif;background:#fff}
.top{display:flex;gap:20px;padding:10px 40px;border-bottom:1px solid #ddd;font:13px sans-serif}.top b{font:700 22px sans-serif}
.bio{display:flex;gap:16px;align-items:center;padding:12px 140px;font:15px sans-serif;color:#333}.bio img{width:48px;height:48px;border-radius:50%%}
article{width:640px;margin:0 auto}article p{margin:0 0 26px}.btn{display:inline-block;background:#7c3aed;color:#fff;padding:8px 16px;border-radius:8px;font:15px sans-serif}
figure{margin:0 0 26px}figure img{width:640px;height:300px;display:block}</style>
<div class="top"><b>data centers</b><span>SEE ALL UPDATES</span></div>
<div class="byline bio"><img src="a.png" alt=""><span>Jay Peters is a senior reporter. He joined The Verge in 2019 after nearly two years at Techmeme.</span></div>
<article><p>%s</p><p>Many data center projects have come under scrutiny for relying on NDAs to hide discussions between developers and local officials.</p>
<p><span class="btn">See model page</span></p><figure><img src="a.png" alt=""></figure><p>%s</p><p>Short closing paragraph.</p></article>""" % (para, long_p)
        with tempfile.TemporaryDirectory() as d:
            web = Path(d) / "web"
            web.mkdir()
            (web / "index.html").write_text(html, encoding="utf-8")
            Image.new("RGB", (64, 64), (120, 140, 200)).save(web / "a.png")
            class Quiet(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *_a):
                    pass
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(web)))
            th = threading.Thread(target=srv.serve_forever, daemon=True)
            th.start()
            try:
                url = "http://127.0.0.1:%d/index.html" % srv.server_address[1]
                items = [{"id": "tick", "url": url, "quote": VQ, "slot": "tick"}, {"id": "card", "url": url, "quote": VQ, "slot": "card"},
                         {"id": "full", "url": url, "quote": VQ, "slot": "full"},
                         {"id": "long", "url": url, "quote": "The quoted line sits right here in the middle of a very long paragraph.", "slot": "card"}]
                (Path(d) / "in.json").write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
                res = subprocess.run(["node", str(TOOLS / "source_shots.mjs"), str(Path(d) / "in.json"), str(Path(d) / "out"), "--total", "120"],
                                     capture_output=True, text=True, cwd=str(ROOT), timeout=200, env=dict(os.environ, PLAYWRIGHT=PW))
            finally:
                srv.shutdown()
                srv.server_close()
            self.assertEqual(res.returncode, 0, res.stderr[-1500:])
            rng = {"tick": (1.9, 3.4), "card": (2.8, 4.2), "full": (1.5, 2.3)}
            for it in items:
                rec = json.loads((Path(d) / "out" / (it["id"] + ".json")).read_text(encoding="utf-8"))
                self.assertTrue(rec["ok"], rec)
                self.assertEqual(rec["slot"], it["slot"])
                self.assertGreater(rec["font_px"], 10)
                im = Image.open(Path(d) / "out" / rec["png"]).convert("L")
                w, h = im.size
                for band in ((0, 4), (h - 4, h)):              # 上下边各 2 个 CSS 像素里没有一点字或图（没切到东西）
                    self.assertGreater(im.crop((0, band[0], w, band[1])).getextrema()[0], 235, (it["id"], band))
                if it["id"] != "long":
                    lo, hi = rng[it["slot"]]
                    self.assertTrue(lo - 0.05 <= rec["w"] / rec["h"] <= hi + 0.05, (it["id"], rec["w"] / rec["h"]))
                    self.assertEqual(rec["edge"], "整块")
                else:
                    self.assertIn("段内两行之间", rec["edge"])
            full = json.loads((Path(d) / "out" / "full.json").read_text(encoding="utf-8"))
            self.assertEqual(full["crop"]["并进整段"], 1)          # 整屏图位不够高：并进下一整段，不把页眉、署名栏并进来
            self.assertTrue(all(0.0 <= v <= 1.0 for ln in full["lines"] for v in ln))


if __name__ == "__main__":
    unittest.main(verbosity=1)
