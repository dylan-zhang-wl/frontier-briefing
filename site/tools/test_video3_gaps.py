#!/usr/bin/env python3
"""11-21 维护：画面空档自动补图（开关"画面空档自动补图"）、卡片数值跟着旁白出（开关"卡片数值跟着旁白出"）的测试。
经验库第五部分第 94、95 件。

查这几件事：
  1. 新量法（screen_model 的 bare）：白卡上的动效（数字递进、摘录、分岔路的线和字牌、传播链）不算"有图"，立体关系模板动起来照算；
     11-18 评审章、11-20 口译章那种排法量得出来；
  2. fix_bare：白卡期间垫上一张露过脸的图（数字递进、传播链、摘录卡 _fb_photo，对比卡 photo，只有字的要点卡 image），
     分岔路章把路尽头的图提到画路的时候；补不了的留着；补完再量没有空档；
  3. card_cues：对比卡没写触发词的条、大数字、底注按旁白补时刻，写了的不动，一位数不找；
  4. 开关：默认关，环境变量能开，和 pipeline/orchestrator/common.py 同一套规则；关着时 post_align 什么都不做；
     第 14 步输入指纹关着是空字符串（往期不重做），开了才变；
  5. blank_spans 开着时写 opener、bare（章首那段不再被吞），关着时和原来一样；导演第二轮的空档说明认得 bare；
  6. compile_chapters：数字递进、传播链垫的图编成 photo_img，补图的标记不进播放器数据。
画面（播放器那一半）的核对用新旧并排截帧做，见 本机资料/试验/维护_1121/对比说明.md；这里不开浏览器。

用法（在项目根运行）：~/.venvs/frontier-daily/bin/python site/tools/test_video3_gaps.py
不调用任何模型、不联网、不写项目文件（临时目录里做）。
"""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]
for p in (TOOLS, ROOT / "pipeline"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import video3_storyboard as SB  # noqa: E402
import video_align  # noqa: E402

NOFILE = Path("/nonexistent/fd_开关.json")


def marks(*spans):
    """[(开口, 说完, 章末)] → marks；第 0 章是开场（不量）。"""
    out = [{"chapter": "open", "voice_start": 0.0, "voice_end": 5.0, "end": 9.0}]
    for v0, v1, end in spans:
        out.append({"chapter": "x", "voice_start": v0, "voice_end": v1, "end": end})
    return out


def sb_of(*chs):
    return {"chapters": [{"id": "open", "kind": "open", "blocks": []}] + list(chs)}


def review_case():
    """照 11-18 评审章的排法：带题图的要点卡 → 数字递进（白卡）→ 截图退回的摘录（没有垫图）。"""
    c = {"id": "review", "kind": "story", "narration": "", "blocks": [
        {"type": "quote_card", "id": "paper", "text": {"zh": "覆盖 718 家公司"}, "image": "v_tray"},
        {"type": "num_chain", "id": "flow", "items": [{"label": {"zh": "30%"}}, {"label": {"zh": "49%"}}, {"label": {"zh": "没有"}}]},
        {"type": "source_excerpt", "id": "peer", "quote": "x", "fact": "f"}]}
    T = {"review.paper.show": 10.1, "review.flow.head": 15.0, "review.flow.items0": 17.0, "review.flow.items1": 20.0,
         "review.flow.items2": 24.0, "review.peer.show": 28.0, "review.peer.mark": 29.0}
    return sb_of(c), T, marks((10.0, 40.0, 42.0))


def fork_case():
    """照 11-20 口译章的排法：分岔路打头，路尽头的配图 13 秒以后才出来，要点卡压在它上面。"""
    c = {"id": "interp", "kind": "story", "narration": "", "blocks": [
        {"type": "fork", "id": "split_paths", "a": {"zh": "常规问诊"}, "b": {"zh": "知情同意等"}},
        {"type": "image_card", "id": "clinic", "image": "e192"},
        {"type": "quote_card", "id": "pilot", "text": {"zh": "20 万欧元"}, "over_photo": True}]}
    T = {"interp.split_paths.fork": 10.1, "interp.split_paths.a": 14.0, "interp.split_paths.b": 17.0,
         "interp.clinic.in": 23.0, "interp.clinic.in.end": 23.6, "interp.pilot.show": 26.0}
    return sb_of(c), T, marks((10.0, 32.0, 34.0))


class BareModel(unittest.TestCase):
    def test_white_card_motion_is_not_a_picture(self):
        sb, T, mk = review_case()
        ch = SB.screen_model(sb, T, mk)[0]
        self.assertEqual([(round(a, 1), round(z, 1)) for a, z in ch["bare"] if z - a > 1], [(15.0, 40.0)])   # 要点卡的图 15 秒被数字递进接走
        self.assertFalse(any(a <= 18 and z >= 22 for a, z in ch["gaps"]))                    # 旧量法把数字递进算"有东西"

    def test_fork_lines_and_signs_are_not_a_picture(self):
        sb, T, mk = fork_case()
        ch = SB.screen_model(sb, T, mk)[0]
        self.assertAlmostEqual(ch["hero"], 23.0)
        self.assertEqual(SB.bare_spans(sb, T, mk), {"interp": [[10.0, 23.0, "opener"]]})

    def test_3d_relation_motion_still_counts(self):
        c = {"id": "q", "kind": "story", "blocks": [
            {"type": "quote_card", "id": "a", "text": {"zh": "x"}, "image": "v1"},
            {"type": "column_compare", "id": "b", "items": [{"label": {"zh": "1"}}, {"label": {"zh": "2"}}]}]}
        T = {"q.a.show": 10.1, "q.b.head": 13.0, "q.b.items0": 14.0, "q.b.items1": 17.0}
        sb, mk = sb_of(c), marks((10.0, 21.0, 22.0))
        self.assertEqual([x for x in SB.screen_model(sb, T, mk)[0]["bare"] if x[1] - x[0] > SB.SCREEN_GAP], [])


class FixBare(unittest.TestCase):
    def test_backdrop_previous_image(self):
        sb, T, mk = review_case()
        notes = SB.fix_bare(sb, T, mk, lambda n: True)
        bl = {b["id"]: b for b in sb["chapters"][1]["blocks"]}
        self.assertEqual(bl["flow"].get("_fb_photo"), "v_tray")
        self.assertEqual(bl["peer"].get("_fb_photo"), "v_tray")
        self.assertEqual(SB.bare_spans(sb, T, mk), {})
        self.assertTrue(notes and all("v_tray" in n for n in notes))

    def test_fork_image_moves_to_fork(self):
        sb, T, mk = fork_case()
        SB.fix_bare(sb, T, mk, lambda n: True)
        self.assertAlmostEqual(T["interp.clinic.in"], 10.1 + SB.BARE_LEAD)
        self.assertAlmostEqual(T["interp.clinic.in.end"] - T["interp.clinic.in"], 0.6)
        self.assertEqual(SB.bare_spans(sb, T, mk), {})

    def test_card_slots(self):
        c = {"id": "k", "kind": "story", "blocks": [
            {"type": "post_card", "id": "p0", "text": {"zh": "x"}, "who": {"zh": "y"}, "image": "v_first"},
            {"type": "compare_panel", "id": "cp", "head": {"zh": "h"}, "bars": [{"value": 1}, {"value": 0.5}]},
            {"type": "quote_card", "id": "qc", "text": {"zh": "z"}},
            {"type": "tile_row", "id": "tr", "items": [{"name": {"zh": "a"}}, {"name": {"zh": "b"}}]}]}
        T = {"k.p0.show": 10.1, "k.cp.show": 13.0, "k.cp.bars0": 14.0, "k.cp.bars1": 15.0, "k.qc.show": 20.0,
             "k.tr.head": 26.0, "k.tr.items0": 27.0, "k.tr.items1": 28.0}
        sb, mk = sb_of(c), marks((10.0, 34.0, 35.0))
        SB.fix_bare(sb, T, mk, lambda n: True)
        bl = {b["id"]: b for b in sb["chapters"][1]["blocks"]}
        self.assertEqual(bl["cp"].get("photo"), "v_first")
        self.assertEqual(bl["qc"].get("image"), "v_first")
        self.assertEqual(bl["tr"].get("photo"), "v_first")
        self.assertEqual(SB.bare_spans(sb, T, mk), {})

    def test_first_image_of_chapter_when_nothing_before(self):
        c = {"id": "n", "kind": "story", "blocks": [
            {"type": "num_chain", "id": "nc", "items": [{"label": {"zh": "1"}}, {"label": {"zh": "2"}}]},
            {"type": "quote_card", "id": "late", "text": {"zh": "x"}, "image": "v_late"}]}
        T = {"n.nc.head": 10.1, "n.nc.items0": 12.0, "n.nc.items1": 15.0, "n.late.show": 19.0}
        sb, mk = sb_of(c), marks((10.0, 24.0, 25.0))
        SB.fix_bare(sb, T, mk, lambda n: True)
        self.assertEqual(sb["chapters"][1]["blocks"][0].get("_fb_photo"), "v_late")

    def test_unfixable_left_alone(self):
        c = {"id": "t", "kind": "story", "blocks": [
            {"type": "timeline", "id": "tl", "ticks": [{"label": {"zh": "周一"}}, {"label": {"zh": "周二"}}]}]}
        T = {"t.tl.start": 10.1, "t.tl.ticks0": 12.0, "t.tl.ticks1": 15.0}
        sb, mk = sb_of(c), marks((10.0, 24.0, 25.0))
        before = copy.deepcopy((sb, T))
        self.assertEqual(SB.fix_bare(sb, T, mk, lambda n: True), [])
        self.assertEqual((sb, T), before)
        self.assertEqual(SB.bare_spans(sb, T, mk)["t"][0][2], "opener")

    def test_missing_image_not_used(self):
        sb, T, mk = review_case()
        self.assertEqual(SB.fix_bare(sb, T, mk, lambda n: False), [])


def fake_find(text, t0, step=0.2, scene=1):
    """旁白每个字 step 秒，从 t0 开始；和 video_align.find 一样只比字、字母、数字。"""
    units, t = [], t0
    for ch in text:
        if video_align.is_unit(ch):
            units.append({"c": ch.lower(), "s": round(t, 3), "e": round(t + step, 3), "scene": scene})
        t += step
    al = {"units": units}
    return lambda ph, after, i: (lambda f: f and (f[0], f[1]))(video_align.find(al, ph, after=after, scene=i))


class CardCues(unittest.TestCase):
    NARR = "扩大发行以后，它募资 813 亿美元，超过 SpaceX 今年 6 月最初的 750 亿美元；算上超额配售，SpaceX 的总额还要更高。"

    def case(self):
        c = {"id": "ipo", "kind": "story", "narration": self.NARR, "blocks": [
            {"type": "compare_panel", "id": "raise", "head": {"zh": "上市募资"},
             "kpi": {"value": {"zh": "813 亿美元"}},
             "bars": [{"value": 0.92, "val": {"zh": "750 亿"}}, {"value": 1.0, "val": {"zh": "813 亿"}}],
             "foot": {"zh": "算上超额配售，SpaceX 总额更高"}}]}
        return sb_of(c), {"ipo.raise.show": 20.0}, marks((19.0, 45.0, 46.0))

    def test_derive(self):
        sb, T, mk = self.case()
        find = fake_find(self.NARR, 19.0)
        notes = SB.card_cues(sb, T, mk, find)
        self.assertGreater(T["ipo.raise.bars0"], T["ipo.raise.bars1"])          # 先说 813、后说 750
        self.assertGreater(T["ipo.raise.kpi"], 20.0 + SB.SYNC_KPI_LATE)
        self.assertGreater(T["ipo.raise.foot"], T["ipo.raise.bars0"])
        self.assertEqual(len(notes), 4)

    def test_explicit_cue_kept_and_single_digit_skipped(self):
        sb, T, mk = self.case()
        b = sb["chapters"][1]["blocks"][0]
        T["ipo.raise.bars0"] = 21.0
        b["kpi"]["value"] = {"zh": "跌超 2%"}
        SB.card_cues(sb, T, mk, fake_find(self.NARR, 19.0))
        self.assertEqual(T["ipo.raise.bars0"], 21.0)
        self.assertNotIn("ipo.raise.kpi", T)

    def test_not_after_next_block(self):
        sb, T, mk = self.case()
        sb["chapters"][1]["blocks"].append({"type": "quote_card", "id": "nx", "text": {"zh": "x"}})
        T["ipo.nx.show"] = 22.0                       # 下一块 22 秒就来了：旁白后面才说到的都不补
        SB.card_cues(sb, T, mk, fake_find(self.NARR, 19.0))
        self.assertNotIn("ipo.raise.foot", T)


class Switches(unittest.TestCase):
    def test_default_off_and_env(self):
        with mock.patch.object(SB, "MOTION_SWITCH_FILE", NOFILE):
            for env in ("FD_BARE_FIX", "FD_CARD_SYNC"):
                with mock.patch.dict(os.environ, {env: ""}):
                    self.assertFalse((SB.bare_fix_switch if env == "FD_BARE_FIX" else SB.card_sync_switch)()[0])
                with mock.patch.dict(os.environ, {env: "on"}):
                    self.assertTrue((SB.bare_fix_switch if env == "FD_BARE_FIX" else SB.card_sync_switch)()[0])

    def test_same_rule_as_fd(self):
        from orchestrator import common
        for env in ("", "on", "off", "开", "关"):
            with mock.patch.dict(os.environ, {"FD_BARE_FIX": env, "FD_CARD_SYNC": env}):
                self.assertEqual(SB.bare_fix_switch()[0], common.bare_fix_switch()[0], env)
                self.assertEqual(SB.card_sync_switch()[0], common.card_sync_switch()[0], env)

    def test_fingerprint_default_does_not_redo(self):
        from orchestrator import runner
        old = {"=摘录卡压图=": ""}
        self.assertEqual(runner.diff_inputs(old, {"=摘录卡压图=": "", "=空档补图=": "", "=卡片数值跟旁白=": ""}), [])
        self.assertEqual(runner.diff_inputs(old, {"=摘录卡压图=": "", "=空档补图=": "开", "=卡片数值跟旁白=": ""}), ["=空档补图="])

    def test_post_align_off_does_nothing(self):
        import video3_build as VB
        sb, T, mk = review_case()
        before = copy.deepcopy((sb, T))
        with mock.patch.dict(os.environ, {"FD_BARE_FIX": "off", "FD_CARD_SYNC": "off"}):
            self.assertEqual(VB.post_align(Path("/nonexistent"), sb, T, mk, {"units": []}), {})
            self.assertEqual(SB.blank_spans(sb, T, mk), {"review": [[33.0, 40.0, "gap"]]})     # 旧量法，和原来一样
        self.assertEqual((sb, T), before)

    def test_blank_spans_on(self):
        sb, T, mk = fork_case()
        with mock.patch.dict(os.environ, {"FD_BARE_FIX": "on"}):
            self.assertEqual(SB.blank_spans(sb, T, mk), {"interp": [[10.0, 23.0, "opener"]]})
            w = SB.check_gaps(sb, T, mk)
        self.assertTrue(any("开口 3 秒内没有主角" in x for x in w))

    def test_director_note_knows_bare(self):
        import video3_director as VD
        media = {"chapters": [{"id": "r", "label": {"zh": "评审"}, "blank": [[86.0, 98.9, "bare"]]}]}
        self.assertIn("没有图", VD.blank_note(media))


class Compile(unittest.TestCase):
    def test_backdrop_compiled(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            issue = Path(td) / "2026-11-18"
            (issue / "06_配图/视频").mkdir(parents=True)
            Image.new("RGB", (64, 36), (120, 110, 100)).save(issue / "06_配图/视频/v_tray.png")
            sb, T, mk = review_case()
            sb["_issue"] = str(issue)
            for c in sb["chapters"]:
                c.setdefault("label", {"zh": c["id"]})
                c.setdefault("narration", "")
            SB.fix_bare(sb, T, mk, lambda n: SB.find_image(issue, n) is not None)
            photos = {}
            out = SB.compile_chapters(sb, T, mk, photos)
            bl = {b["id"]: b for b in out[1]["blocks"]}
            self.assertEqual(bl["flow"]["photo_img"], "flow.photo")
            self.assertIn("flow.photo", photos)
            for b in bl.values():
                self.assertFalse({"_bare_fix", "_bare_early", "_fb_photo"} & set(b))


if __name__ == "__main__":
    unittest.main(verbosity=1)
