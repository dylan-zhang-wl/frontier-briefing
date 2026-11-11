#!/usr/bin/env python3
"""读音表核对（lexicon_check.py）第 7 项"英文原名第一次出现要补中文名"的测试（2026-11-03 加，用户定的规则）。

规则（读音表.yaml 的"中文名"字段）：MIT、PIMCO 这类写法是英文、有官方中文名的，第一次出现时前后 30 个字以内要有中文名
（"MIT，也就是麻省理工学院""麻省理工学院 MIT""MIT（麻省理工学院）"都算），或者中文名更早已经出现过；没补的算"要改"，不自动改。
这里查：几种写法都放行；只在后面很远才说中文的要改；第二次起不报；全文没有不报；MIT CSAIL 配全称时 MIT 那条也算满足、
只点明"麻省理工学院"也算 MIT CSAIL 补了中文（11-03 定）；
PIMCO 两个中文名都认；没有"中文名"的条目、默认不开这一项的 check()（video3_build、build_v3 这样调）行为不变；
原有的读音核对不回退（"奥尔特曼"仍报音译，"英伟达，英文叫 Nvidia"仍放行）。
2026-11-05 加（SpokenOnly）："只改口播稿"的条目：命令行查口播稿时"C+ 轮"自动改成"C 加轮"；网页、视频旁白那样调 check() 不改、
不报；C++、B+ 轮、单独的 C+ 不误伤；11-04 播客稿补表后要改只剩这一处。
2026-11-06 加（Issue1106）：口播"设闸"自动改"设下闸门"、"Hy4"自动改"HY4"（只改口播稿的写法压过产品条目里同样的写法；区分大小写）；
第 8 项英文名后补停顿（"Ricursive Intelligence 发布" → "Ricursive Intelligence，发布"，"发布的""据 X 发布"这类不加）；
播客稿数字"501B" → "五千零一十亿参数"；改完的稿子 script_check 照样过（数字、英文名都对得上事件卡）；
11-06 播客稿补表后"表里还没有"清零，网页、视频旁白那样调 check() 仍然不改、不报。

用法（在项目根运行）：
    ~/.venvs/frontier-daily/bin/python pipeline/test_lexicon_check.py        # 全部通过时退出码为 0
不调用任何模型；用真的读音表（只读），临时文件放在系统临时目录里；11-03 那期的播客稿只读。
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

import lexicon_check as L  # noqa: E402

ENTRIES, EXTRA, SUFFIX, _VERSION = L.load_lexicon()
FILLER = "让一个模型直接修改另一个模型的权重，只改了很少一部分参数，数学成绩明显上升，这件事值得多看两眼。"   # 超过 30 个字


def run(text, first_zh=True):
    return L.check(text, ENTRIES, EXTRA, SUFFIX, first_zh=first_zh)


def first_zh_rows(text, first_zh=True):
    return [r for r in run(text, first_zh)["要改"] if r["种类"] == "首次补中文"]


def sample_dirs():
    """完整样期：仓库的 测试版/ 只存跨天要用的文字（选题、事件卡、文稿），没有 logs、配音、配图、网页、视频。
    按顺序找：环境变量 FD_SAMPLE_ROOT/<日期>、本机资料/归档/mini试运行_1031-1109/<日期>（mini 试运行那周的原件，
    只在本机、靠 iCloud 同步，不进 git）、测试版/<日期>。"""
    out = [Path(os.environ["FD_SAMPLE_ROOT"]).expanduser()] if os.environ.get("FD_SAMPLE_ROOT") else []
    return out + [PIPE.parent / "本机资料" / "归档" / "mini试运行_1031-1109", PIPE.parent / "测试版"]


class Table(unittest.TestCase):
    """读音表里的新字段和新条目。"""

    def test_fields(self):
        by = {e["写法"]: e for e in ENTRIES}
        self.assertEqual(by["MIT"]["中文名"], ["麻省理工学院"])
        self.assertEqual(by["MIT CSAIL"]["中文名"], ["麻省理工学院计算机科学与人工智能实验室", "麻省理工学院"])
        self.assertEqual(by["MIT CSAIL"]["也可写"], ["CSAIL"])
        self.assertEqual(by["PIMCO"]["中文名"], ["品浩", "太平洋投资管理公司"])
        self.assertEqual(by["Rikiya Takehi"]["之后"], "Takehi")
        self.assertEqual(by["《科创板日报》"]["也可写"], ["科创板日报"])
        self.assertEqual(by["OpenAI"]["中文名"], [])                    # 没写这个字段的条目是空列表
        self.assertEqual(sum(1 for e in ENTRIES if e["写法"] in ("MIT", "MIT CSAIL", "PIMCO", "Rikiya Takehi")), 4)  # 没有重复条目


class FirstZh(unittest.TestCase):
    """第 7 项：英文原名第一次出现要补中文名。"""

    def test_english_then_chinese(self):
        self.assertEqual(first_zh_rows("再看一项研究。MIT，也就是麻省理工学院，提出了一种新方法。"), [])

    def test_chinese_then_english(self):
        self.assertEqual(first_zh_rows("再看一项研究。麻省理工学院 MIT 提出了一种新方法。"), [])

    def test_web_brackets(self):
        self.assertEqual(first_zh_rows("MIT（麻省理工学院）的研究人员提出了一种新方法。"), [])

    def test_chinese_too_far_after(self):
        text = "再看一项研究。\n\nMIT 的研究者" + FILLER + "这项研究来自麻省理工学院。后来 MIT 又发了一篇。"
        rows = first_zh_rows(text)
        self.assertEqual(len(rows), 1, rows)                            # 只报第一次，不报后面那个 MIT
        r = rows[0]
        self.assertEqual((r["行"], r["原文"], r["自动改"]), (3, "MIT", False))
        self.assertIn("麻省理工学院", r["应为"])
        self.assertEqual(r["说明"], "第一次写 MIT 要补中文名：麻省理工学院（口播说'MIT，也就是麻省理工学院'）")
        res = run(text)
        self.assertEqual(L.apply_fixes(text, res["_fixes"])[0], text)  # 不自动插入

    def test_window_boundary(self):
        def gap(n):
            return "MIT" + "研" * n + "麻省理工学院。"
        self.assertEqual(first_zh_rows(gap(30)), [])                    # 中文名从第 30 个字处开始：算
        self.assertEqual(len(first_zh_rows(gap(31))), 1)                 # 第 31 个字：不算

    def test_later_mentions_not_reported(self):
        text = "MIT，也就是麻省理工学院，提出了新方法。" + FILLER + "MIT 的团队还说，MIT 会继续做。"
        self.assertEqual(first_zh_rows(text), [])

    def test_absent(self):
        self.assertEqual(first_zh_rows("OpenAI 的 CEO Sam Altman 说，Altman 很看好这件事。"), [])

    def test_csail_full_name(self):
        text = ("MIT CSAIL，也就是麻省理工学院计算机科学与人工智能实验室，提出了一种新方法。" + FILLER
                + "和 MIT 那项研究放在一起看。")
        self.assertEqual(first_zh_rows(text), [])                       # MIT 那条：长名字里含"麻省理工学院"，更早出现过
        text2 = "麻省理工学院计算机科学与人工智能实验室 MIT CSAIL 提出了一种新方法。"
        self.assertEqual(first_zh_rows(text2), [])                      # 只有 MIT CSAIL，没有单独的 MIT：MIT 那条不查

    def test_csail_short_chinese(self):
        """口播里全称太长，点明是麻省理工学院就够（11-03 定）。"""
        self.assertEqual(first_zh_rows("再看一项研究。麻省理工学院的一个 AI 实验室，MIT CSAIL，提出了一种新方法。"), [])
        self.assertEqual(first_zh_rows("MIT CSAIL，麻省理工学院的一个 AI 实验室，提出了一种新方法。"), [])

    def test_csail_without_chinese_no_duplicates(self):
        text = "MIT CSAIL 提出了一种新方法。" + FILLER + "MIT 的团队还说。"
        rows = first_zh_rows(text)
        self.assertEqual([r["原文"] for r in rows], ["MIT CSAIL", "MIT"], rows)   # 两条各报一次；MIT CSAIL 里的 MIT 不算 MIT 的第一次
        self.assertEqual(len({(r["行"], r["上下文"]) for r in rows}), 2)
        rows2 = first_zh_rows("CSAIL 的研究者提出了一种新方法。")
        self.assertEqual([r["原文"] for r in rows2], ["CSAIL"])           # "也可写"也算第一次出现
        self.assertIn("MIT CSAIL，也就是麻省理工学院计算机科学与人工智能实验室", rows2[0]["说明"])

    def test_pimco(self):
        self.assertEqual(first_zh_rows("PIMCO，中文名品浩，它的首席执行官 Emmanuel Roman 说。"), [])
        self.assertEqual(first_zh_rows("太平洋投资管理公司 PIMCO 的首席执行官 Emmanuel Roman 说。"), [])
        self.assertEqual(first_zh_rows("PIMCO（品浩）首席执行官 Emmanuel Roman 说。"), [])
        rows = first_zh_rows("PIMCO 首席执行官 Emmanuel Roman 在香港的一场金融峰会上说，未来五年与 AI 相关的融资可能很大。")
        self.assertEqual(len(rows), 1)
        self.assertIn("品浩或太平洋投资管理公司", rows[0]["说明"])

    def test_masked_parts_dont_count(self):
        self.assertEqual(first_zh_rows("## MIT 的研究\n\nMIT，也就是麻省理工学院，提出了新方法。"), [])   # 标题里的 MIT 不是第一次
        rows = first_zh_rows("<!-- 麻省理工学院 -->\n\nMIT 的研究者" + FILLER)
        self.assertEqual(len(rows), 1)                                   # 注释里的中文名不算

    def test_off_by_default(self):
        """check() 默认不查这一项：video3_build（视频旁白配音前检查，要改一律硬停）、build_v3 这样调，行为不变。"""
        text = "PIMCO 首席执行官 Emmanuel Roman 说。MIT 的研究者" + FILLER
        self.assertEqual([r for r in L.check(text, ENTRIES, EXTRA, SUFFIX)["要改"] if r["种类"] == "首次补中文"], [])
        self.assertEqual(len(first_zh_rows(text)), 2)

    def test_entries_without_field_unchanged(self):
        """没有"中文名"的条目：开不开这一项，结果一模一样。"""
        text = ("OpenAI 的 CEO 萨姆·奥尔特曼说，Nvidia 的芯片不够。英伟达，英文叫 Nvidia。Sam Altman 后来又说，"
                "Altman 认为 Reddit 和 Cursor 都在涨。彭博社报道说，Bloomberg 的数据也一样。")
        a, b = run(text, True), run(text, False)
        self.assertEqual(a, b)
        with tempfile.TemporaryDirectory() as d:                         # 一份不带"中文名"字段的读音表
            p = Path(d) / "表.yaml"
            p.write_text("版本: 测试\n公司:\n  - 写法: MIT\n  - 写法: 英伟达\n    应改: [Nvidia]\n", encoding="utf-8")
            ents, ex, suf, _v = L.load_lexicon(p)
            self.assertEqual([e["中文名"] for e in ents], [[], []])
            t2 = "MIT 的研究者" + FILLER + "Nvidia 也在。"
            self.assertEqual(L.check(t2, ents, ex, suf, first_zh=True), L.check(t2, ents, ex, suf))


class Regression(unittest.TestCase):
    """原有的读音核对不回退。"""

    def test_transliteration(self):
        rows = run("OpenAI 的 CEO 奥尔特曼说，萨姆·奥尔特曼很看好。")["要改"]
        self.assertIn(("音译", "奥尔特曼"), [(r["种类"], r["原文"]) for r in rows])
        self.assertIn(("音译", "萨姆·奥尔特曼"), [(r["种类"], r["原文"]) for r in rows])

    def test_intro_phrase_allowed(self):
        rows = run("英伟达，英文叫 Nvidia，是一家芯片公司。")["要改"]
        self.assertEqual([r for r in rows if r["原文"] == "Nvidia"], [])
        rows2 = run("Nvidia 是一家芯片公司。")["要改"]
        self.assertEqual([(r["种类"], r["应为"]) for r in rows2], [("应写中文", "英伟达")])

    def test_known_names_not_missing(self):
        text = "麻省理工学院的一个 AI 实验室，MIT CSAIL，提出了新方法。研究由 Rikiya Takehi 等四位研究者完成，发在 Takehi 的博客上。"
        res = run(text)
        self.assertEqual(res["表里还没有"], [])
        self.assertEqual([r for r in res["要改"] if r["种类"] in ("人名首次要说全名", "之后只说姓")], [])


class CommandLine(unittest.TestCase):
    """命令行（总调度第 7 步这样跑播客稿）：这一项算要改、退出码 1、--fix 不动它。"""

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "稿.md"
            text = "## 开场\n\nPIMCO 首席执行官 Emmanuel Roman 说，未来五年与 AI 相关的融资可能很大。\n"
            p.write_text(text, encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = L.main([str(p), "--json"])
            self.assertEqual(rc, 1)
            got = json.loads(buf.getvalue())
            self.assertEqual([(r["种类"], r["行"]) for r in got["要改"]], [("首次补中文", 3)])
            self.assertTrue(got["要改"][0]["说明"].startswith("第一次写 PIMCO 要补中文名"))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = L.main([str(p), "--fix"])
            self.assertEqual(rc, 1)
            self.assertEqual(p.read_text(encoding="utf-8"), text)            # 不自动插入
            self.assertEqual(buf.getvalue().count("第一次写 PIMCO 要补中文名"), 1)   # 应为和说明一样时只印一次
            p.write_text(text.replace("PIMCO 首席", "PIMCO，中文名品浩，它的首席"), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(L.main([str(p), "--json"]), 0)

    def test_issue_1103(self):
        """11-03 那期的播客稿（只读）：MIT CSAIL 前面说了"麻省理工学院的一个 AI 实验室"、MIT 前面已有"麻省理工学院"，都放行；
        PIMCO 第一次没补中文名。"""
        p = PIPE.parent / "测试版" / "2026-11-03" / "04_文稿" / "claude_播客_v3.md"
        if not p.exists():
            self.skipTest("没有 11-03")
        rows = first_zh_rows(p.read_text(encoding="utf-8"))
        self.assertEqual([r["原文"] for r in rows], ["PIMCO"], rows)


class SpokenOnly(unittest.TestCase):
    """2026-11-05 加："只改口播稿"的条目（C+ 轮 → C 加轮）只在命令行查口播稿时算；网页（build_v3）、视频旁白（video3_build）
    调 check() 不改、不报，"C+"也不算"表里还没有"。"""

    def spoken(self, text):
        return L.check(text, ENTRIES, EXTRA, SUFFIX, first_zh=True, spoken=True)

    def test_entry(self):
        e = next(e for e in ENTRIES if e["写法"] == "C 加轮")
        self.assertEqual((e["类别"], e["只改口播稿"], e["也可写"]), ("其他", True, ["C+"]))
        self.assertFalse(next(e for e in ENTRIES if e["写法"] == "OpenAI")["只改口播稿"])

    def test_podcast_fix(self):
        for src, want in (("墨芯完成近十亿元的 C+ 轮融资。", "墨芯完成近十亿元的 C 加轮融资。"),
                          ("墨芯完成近十亿元的C+轮融资。", "墨芯完成近十亿元的 C 加轮融资。"),
                          ("一笔 c+ 轮融资。", "一笔 C 加轮融资。")):
            res = self.spoken(src)
            self.assertEqual([(r["种类"], r["应为"], r["自动改"]) for r in res["要改"]], [("应改写法", "C 加轮", True)], src)
            self.assertEqual(L.apply_fixes(src, res["_fixes"])[0], want)

    def test_web_and_video_untouched(self):
        text = "墨芯完成近 10 亿元 C+ 轮融资，凌川科技完成 10 亿元 B 轮。"
        res = L.check(text, ENTRIES, EXTRA, SUFFIX)                       # build_v3、video3_build 这样调
        self.assertEqual(res["要改"], [])
        self.assertEqual(res["_fixes"], {})
        self.assertNotIn("C+", [r["英文"] for r in res["表里还没有"]])

    def test_no_collateral(self):
        """别的写法不误伤：C++、B+ 轮、单独的 C+（评级）、ABC+ 轮都不动。"""
        for text in ("用 C++ 写的程序。", "完成 B+ 轮融资。", "信用评级是 C+。", "ABC+ 轮是个假名字。"):
            res = self.spoken(text)
            self.assertEqual([r for r in res["要改"] if r["应为"] == "C 加轮"], [], text)
            self.assertNotIn("C 加轮", L.apply_fixes(text, res["_fixes"])[0], text)

    def test_cli_fix(self):
        with tempfile.TemporaryDirectory() as d:
            p, out = Path(d) / "稿.md", Path(d) / "改后.md"
            p.write_text("## 热点三\n\n深圳的墨芯宣布完成近十亿元人民币的 C+ 轮融资。\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(L.main([str(p), "--fix", "--out", str(out)]), 0)
            self.assertIn("C 加轮融资", out.read_text(encoding="utf-8"))
            self.assertIn("C+ 轮", p.read_text(encoding="utf-8"))           # --out 时原稿不动

    def test_issue_1104(self):
        """11-04 播客稿（只读）：补表以后，要改只剩 C+ 轮（能自动改）、Bing 第一次没补"必应"（11-05 补表），
        以及 11-06 起口播里的 Hy4 一律改成 HY4（5 处，能自动改；11-06 定按字母念，见读音表"其他"）；表里还没有只剩 3 个普通词或待定的。
        预期值 11-06 改过：原来只有前两处，多出来的 5 处 Hy4 是这次新加的"只改口播稿"条目带来的，不是回退。"""
        p = PIPE.parent / "测试版" / "2026-11-04" / "04_文稿" / "claude_播客_v3.md"
        if not p.exists():
            self.skipTest("没有 11-04")
        res = self.spoken(p.read_text(encoding="utf-8"))
        self.assertEqual([(r["行"], r["原文"], r["种类"]) for r in res["要改"]],
                         [(55, "C+ 轮", "应改写法"), (71, "Bing", "首次补中文")] + [(n, "Hy4", "应改写法") for n in (75, 75, 77, 79, 99)])
        self.assertTrue(all(r["自动改"] for r in res["要改"] if r["原文"] == "Hy4"))
        # 11-06 晚加的"配音单位开头"：热点二第二块开口"不足也不少。APPSO 用 iPhone 16 Pro"（APPSO 前只有 5 个汉字、
        # 后面只隔一个"用"又接英文）。11-05 回听时这一处的 APPSO 正好转写成了 Epson，所以报它是对的，不是误报；别的提醒没有
        self.assertEqual([(r["行"], r["种类"], r["原文"]) for r in res["提醒"]],
                         [(41, "配音单位开头夹心", "不足也不少。APPSO 用 iPhone 16 Pro")])
        self.assertEqual(sorted(r["英文"] for r in res["表里还没有"]), ["K-12", "inference", "reasoning"])


class Issue1106(unittest.TestCase):
    """2026-11-06 加：11-06 回听核对报告暴露的念法问题，只在命令行查口播稿（spoken=True）时改；网页、视频旁白不受影响。"""

    def spoken(self, text):
        return L.check(text, ENTRIES, EXTRA, SUFFIX, first_zh=True, spoken=True)

    def fixed(self, text):
        return L.apply_fixes(text, self.spoken(text)["_fixes"])[0]

    def test_sezha(self):
        self.assertEqual(self.fixed("和政治设闸有关的，还有一笔并购。"), "和政治设下闸门有关的，还有一笔并购。")
        rows = self.spoken("选票在设闸。")["要改"]
        self.assertEqual([(r["种类"], r["应为"], r["自动改"]) for r in rows], [("口播改说法", "设下闸门", True)])
        for text in ("水库要设闸门。", "建设闸坝的工程。", "选票给数据中心设下闸门。"):    # 例外、已经改过的不动
            self.assertEqual(self.fixed(text), text, text)

    def test_hy4(self):
        self.assertEqual(self.fixed("Vals 的独立评测里，腾讯 Hy4 在开放权重模型中排第四。"),
                         "Vals 的独立评测里，腾讯 HY4 在开放权重模型中排第四。")
        self.assertEqual(self.fixed("腾讯发布了 Hy4 preview。"), "腾讯发布了 HY4 preview。")
        res = self.spoken("腾讯 HY4 排第四，HY4 preview 也在。")                     # 改过以后再查：不再报，也不算表里没有（区分大小写）
        self.assertEqual((res["要改"], res["表里还没有"]), ([], []))
        web = L.check("腾讯 Hy4 和 HY4 都在。", ENTRIES, EXTRA, SUFFIX)               # 网页、视频：两种都认识，不改
        self.assertEqual((web["要改"], web["表里还没有"]), ([], []))

    def test_pause(self):
        for src, want in (("Ricursive Intelligence 发布 Ripple-65B Preview。", "Ricursive Intelligence，发布 Ripple-65B Preview。"),
                          ("Thinking Machines Lab 发布了 Inkling 2 Small。", "Thinking Machines Lab，发布了 Inkling 2 Small。"),
                          ("新消息，GPT-6 Cyber 上线了。", "新消息，GPT-6 Cyber，上线了。"),
                          ("Ricursive Intelligence发布了模型。", "Ricursive Intelligence，发布了模型。")):
            rows = [r for r in self.spoken(src)["要改"] if r["种类"] == "英文名后补停顿"]
            self.assertEqual(len(rows), 1, src)
            self.assertTrue(rows[0]["自动改"])
            self.assertEqual(self.fixed(src), want, src)

    def test_pause_not_added(self):
        for text in ("Ricursive Intelligence，发布了 Ripple。",                    # 已经有逗号
                     "OpenAI 发布了 GPT-6 Cyber。",                               # 一个词的英文名
                     "Thinking Machines Lab 发布的 Inkling 2 Small 很大。",         # 发布的：定语
                     "Thinking Machines Lab 发布会上说。",                         # 发布会：名词
                     "据 The Information 披露，公司要融资。",                       # 据……披露
                     "12 月随 iOS 27.3 推出，首批约 18 项功能。",                   # 随……推出
                     "在 Thinking Machines Lab 发布 Inkling 的同时。",             # 在……发布
                     "Chris Lehane 说，这是一个很高的底线。",                       # 说、表示这类不加
                     "## Ricursive Intelligence 发布\n\n正文。",                   # 标题不查
                     "<!-- Ricursive Intelligence 发布 -->"):                     # 注释不查
            rows = [r for r in self.spoken(text)["要改"] if r["种类"] == "英文名后补停顿"]
            self.assertEqual(rows, [], text)

    def test_web_and_video_untouched(self):
        """build_v3（网页）、video3_build（视频旁白）那样调 check()：设闸、Hy4、英文名后接动词都不改、不报。"""
        text = "选票给数据中心设闸。Ricursive Intelligence 发布 Ripple-65B Preview，腾讯 Hy4 排第四，Reflection Beam 501B 是 80.1。"
        res = L.check(text, ENTRIES, EXTRA, SUFFIX)
        self.assertEqual((res["要改"], res["_fixes"], res["表里还没有"]), ([], {}, []))

    def test_cli_numbers(self):
        """命令行查播客稿：501B、816B 算要改、--fix 自动改成读法；65B、型号里的 Ripple-65B 不改。"""
        with tempfile.TemporaryDirectory() as d:
            p, out = Path(d) / "稿.md", Path(d) / "改后.md"
            p.write_text("## 热点二\n\nRipple-65B Preview 是 65B 的模型，对手 Reflection Beam 501B 是八十点一，"
                         "Muse Spark Open 816B 是七十六点四。\n", encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(L.main([str(p), "--json"]), 1)
            got = json.loads(buf.getvalue())
            self.assertEqual([(r["种类"], r["原文"], r["应为"]) for r in got["要改"]],
                             [("数字加单位缩写", "501B", "五千零一十亿参数"), ("数字加单位缩写", "816B", "八千一百六十亿参数")])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(L.main([str(p), "--fix", "--out", str(out)]), 0)
            new = out.read_text(encoding="utf-8")
            self.assertIn("Reflection Beam 五千零一十亿参数是八十点一", new)
            self.assertIn("Muse Spark Open 八千一百六十亿参数是七十六点四", new)
            self.assertIn("Ripple-65B Preview 是 65B 的模型", new)
            res = L.check("对手是五百零一 B 的模型。", ENTRIES, EXTRA, SUFFIX)
            self.assertNotIn("B", [r["英文"] for r in res["表里还没有"]])                # 有人写成"五百零一 B"：这个 B 认识
            res = L.check("一点五 T 个词元，T-Mobile 和 K-12 教育。", ENTRIES, EXTRA, SUFFIX)
            self.assertEqual(sorted(r["英文"] for r in res["表里还没有"]), ["K-12", "T-Mobile"])  # 别处的单独字母照旧报
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(L.main([str(p), "--json", "--no-numbers"]), 0)   # 视频旁白这类稿子：数字不查

    def test_issue_1106(self):
        """11-06 播客稿（只读）：要改正好是 501B、816B、Hy4、设闸、Thinking Machines Lab 后补逗号这 5 处，都能自动改；
        表里还没有从 33 个清零（11-06 补表）；改完再查没有要改的。"""
        p = PIPE.parent / "测试版" / "2026-11-06" / "04_文稿" / "claude_播客_v3.md"
        if not p.exists():
            self.skipTest("没有 11-06")
        # 11-06 白天重做时第 7 步已经把这 5 处自动改进了稿子（改前那份留在期目录 logs/改前备份/ 里）：
        # 拿改前那份当考题；现在的稿子要已经改好、再查没有要改的。
        # 仓库的 测试版/ 只存改好的稿子、没有 logs/，改前备份要到完整样期里找（见 sample_dirs）；找不到就跳过：
        # 拿改好的稿子当考题，5 处早已改掉，必然"失败"，盖住真正的回归（11-09 晚改）
        baks = []
        for base in sample_dirs():
            baks = sorted((base / "2026-11-06" / "logs" / "改前备份").glob("claude_播客_v3.md.*"))
            if baks:
                break
        if not baks:
            self.skipTest("11-06 的改前备份（logs/改前备份/）不在：仓库只存改好的稿子；要跑这道题，设 FD_SAMPLE_ROOT 指向完整样期所在的文件夹")
        live = p.read_text(encoding="utf-8")
        self.assertEqual(self.spoken(live)["要改"] + L.podcast_numbers(live, ENTRIES)["要改"], [])
        p = baks[0]
        text = p.read_text(encoding="utf-8")
        res = self.spoken(text)
        nm = L.podcast_numbers(text, ENTRIES)
        rows = sorted(res["要改"] + nm["要改"], key=lambda r: (r["行"], r["原文"]))
        self.assertEqual([(r["行"], r["种类"], r["原文"]) for r in rows],
                         [(37, "数字加单位缩写", "501B"), (37, "数字加单位缩写", "816B"), (49, "应改写法", "Hy4"),
                          (101, "口播改说法", "设闸"), (105, "英文名后补停顿", "Thinking Machines Lab 发布")])
        self.assertTrue(all(r["自动改"] for r in rows))
        self.assertEqual(res["表里还没有"], [])
        fx = dict(res["_fixes"])
        fx.update(nm["_fixes"])
        new = L.apply_fixes(text, fx)[0]
        again = self.spoken(new)
        self.assertEqual(again["要改"] + L.podcast_numbers(new, ENTRIES)["要改"], [])
        for s_ in ("Reflection Beam 五千零一十亿参数是八十点一", "Muse Spark Open 八千一百六十亿参数是七十六点四", "腾讯 HY4 在",
                   "和政治设下闸门有关的", "Thinking Machines Lab，发布了 Inkling 2 Small"):
            self.assertIn(s_, new)
        # 总调度第 7 步接着跑 script_check：改完的稿子，数字、英文名都要还能在事件卡里找到（不然自动运行会停下）
        import script_check as SC
        cards = PIPE.parent / "测试版" / "2026-11-06" / "03_事件卡" / "cards_写稿用.json"
        res = SC.check(new, SC.Evidence(SC.load_cards(cards)), "日常")
        self.assertEqual([(r["类"], r["原文"]) for r in res["要改"]], [])

    def test_video_1106(self):
        """11-06 视频旁白（只读）：照 video3_build 的调法，没有要改（不会硬停），表里还没有也清零。"""
        p = PIPE.parent / "测试版" / "2026-11-06" / "04_文稿" / "视频旁白_v3.md"
        if not p.exists():
            self.skipTest("没有 11-06")
        res = L.check(p.read_text(encoding="utf-8"), ENTRIES, EXTRA, SUFFIX)
        self.assertEqual((res["要改"], res["表里还没有"]), ([], []))



class VoiceOpening(unittest.TestCase):
    """2026-11-06 晚加：第 8 项改准——配音单位（视频一章、播客一块、对谈一轮）开口就是英文名、后面只夹两三个汉字又接英文，提醒改中文起句。
    11-06 视频两句原稿要报；往期四个开口是英文、配出来没事的章首不报（或只记弱提醒）；改成中文起句以后不报。只提醒，不改稿、不影响退出码。"""

    BAD = ("Ricursive Intelligence，发布了 Ripple-65B Preview，自称美国开放权重的编程第一。",       # 11-06 下午版（加了逗号也没用）
           "Ricursive Intelligence 发布 Ripple-65B Preview，自称美国开放权重的编程第一。",          # 11-06 早上版
           "GPT-6 Cyber 在 OpenAI 自己的框架里，从上一代的 High 升到了 Critical。")              # "在"被吞
    OK_PAST = ("Anthropic 第三季度营收约 170 亿美元，环比增长约 47%，比第二季度的 144% 慢了不少，还录得 5.6 亿美元经营亏损。",  # 11-03 bill
               "OpenAI 的 CEO Sam Altman 10 月 31 日在韩国见了约 50 名三星高管，彭博社说是谈存储芯片供应。",             # 11-01 memory
               "MIT 的研究者让 GPT-6 Astra 直接改千问一个小模型的权重，只动了 0.016% 的参数。",                         # 11-03 rewrite
               "据报道，OpenAI 本轮融资目标从 300 亿美元降到约 200 亿，已获承诺约 110 亿，不到一半。")                    # 10-31 money
    FIXED = ("前谷歌研究员创立的 Ricursive Intelligence，发布了 Ripple-65B Preview，自称美国开放权重的编程第一。",
             "网络安全这一项，按 OpenAI 自己的框架，GPT-6 Cyber 从上一代的 High 升到了 Critical。")

    def test_rule(self):
        for t in self.BAD:
            r = L.opening_problem(t)
            self.assertEqual(r and r["强弱"], "强", t)
        for t in self.OK_PAST:
            r = L.opening_problem(t)
            self.assertTrue(r is None or r["强弱"] == "弱", t)
        for t in self.FIXED:
            self.assertIsNone(L.opening_problem(t), t)
        self.assertIsNone(L.opening_problem("11 月 6 日，选票给数据中心设下闸门，开放权重在争第一，AI 越能动手，越要讲授权。"))
        self.assertEqual(L.opening_problem("换到产品。DeepSeek 团队在 GitHub 上放出了代码。")["强弱"], "强")   # 只有 4 个汉字垫底也算
        self.assertEqual(L.opening_problem("AI 也在改写手机的入口。国行 Apple 智能等了约两年半。")["强弱"], "弱")  # 句号隔开：不算夹心

    def test_units_single(self):
        """单人稿：按 tts.plan_chunks 切块，只看每块开头；块中间的“Thinking Machines Lab，发布了”不报。"""
        text = ("## 热点一\n\nGPT-6 Cyber 在 OpenAI 自己的框架里升了一档。后面还有很长一段中文。\n\n"
                "## 快讯\n\n再快速看几条别的消息。Thinking Machines Lab，发布了 Inkling 2 Small。\n")
        res = L.check(text, ENTRIES, EXTRA, SUFFIX, first_zh=True, spoken=True)
        rows = [r for r in res["提醒"] if r["种类"].startswith("配音单位")]
        self.assertEqual([(r["种类"], r["行"]) for r in rows], [("配音单位开头夹心", 3)])
        self.assertIn("【热点一】", rows[0]["上下文"])
        web = L.check(text, ENTRIES, EXTRA, SUFFIX)                                        # 网页、视频旁白那样调：不查
        self.assertEqual([r for r in web["提醒"] if r["种类"].startswith("配音单位")], [])

    def test_units_dialog(self):
        """对谈稿：同一人连着说的几行并成一轮，只看每轮开头。"""
        text = ("## 热点一\n\n甲：先说一件和安全有关的事。\n甲：GPT-6 Cyber 在 OpenAI 里升了一档。\n乙：GPT-6 Cyber 在 OpenAI 里升了一档。\n"
                "<!-- 语气 {} -->\n")
        units = L.voice_units(text)
        self.assertEqual([(u[1], u[2][:6]) for u in units], [("热点一·甲", "先说一件和安"), ("热点一·乙", "GPT-6 ")])
        rows = L.voice_opening_rows(units, "轮")
        self.assertEqual([(r["种类"], r["上下文"][:7]) for r in rows], [("配音单位开头夹心", "【热点一·乙】")])

    def test_cli_not_blocking(self):
        """只提醒：命令行退出码不变（第 7 步不会因此停下），--fix 不改这一处。"""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "稿.md"
            p.write_text("## 热点三\n\nGPT-6 Cyber 在 OpenAI 自己的框架里，从上一代的一档升了一档，后面是很长一段中文说明。\n", encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = L.main([str(p), "--json", "--no-numbers"])
            got = json.loads(buf.getvalue())
            self.assertEqual(rc, 0)
            self.assertEqual([r["种类"] for r in got["提醒"]], ["配音单位开头夹心"])
            with contextlib.redirect_stdout(io.StringIO()):
                L.main([str(p), "--fix", "--no-numbers"])
            self.assertTrue(p.read_text(encoding="utf-8").startswith("## 热点三\n\nGPT-6 Cyber 在 OpenAI"))

    def test_past_podcasts(self):
        """往期播客稿（只读）：11-06 没有夹心开头（块 10 的“Thinking Machines Lab，发布了”在块中间）；11-04 只有 APPSO 那一处。"""
        for day, want in (("2026-11-06", []), ("2026-11-04", [41]), ("2026-11-03", []), ("2026-11-02", [])):
            p = PIPE.parent / "测试版" / day / "04_文稿" / "claude_播客_v3.md"
            if not p.exists():
                continue
            res = L.check(p.read_text(encoding="utf-8"), ENTRIES, EXTRA, SUFFIX, first_zh=True, spoken=True)
            self.assertEqual([r["行"] for r in res["提醒"] if r["种类"] == "配音单位开头夹心"], want, day)


class SameSurname(unittest.TestCase):
    """11-09 加：同姓不同人。表里是 Luke Roberts（之后只说 Roberts），稿子写 Daniel Roberts 是另一个人，不报"首次要说全名"、不自动改。"""

    def kinds(self, text):
        return [(r["种类"], r["原文"]) for r in L.check(text, ENTRIES, EXTRA, SUFFIX)["要改"] if "全名" in r["种类"] or "只说姓" in r["种类"]]

    def test_other_person_quiet(self):
        self.assertEqual(self.kinds("同行 IREN 的联席 CEO Daniel Roberts 说，问题已经从合同有多大，变成钱从哪来。"), [])

    def test_same_person_still_checked(self):
        self.assertEqual(self.kinds("安全公司 Phorian 的 CTO Roberts 说，漏洞已经修好。"), [("人名首次要说全名", "Roberts")])
        self.assertEqual(self.kinds("安全公司 Phorian 的 CTO 兼联合创始人 Luke Roberts 说，漏洞已经修好。Roberts 还说……"), [])

    def test_gurman_still_hits(self):
        """Mark Gurman：只说姓照旧要报、说了全名不报；别的名加 Gurman（另一个人）不报。"""
        self.assertEqual(self.kinds("据彭博社记者 Gurman 爆料，苹果在施压。"), [("人名首次要说全名", "Gurman")])
        self.assertEqual(self.kinds("据彭博社记者 Mark Gurman 爆料，苹果在施压。之后 Gurman 又说……"), [])
        self.assertEqual(self.kinds("研究员 Daniel Gurman 说，这件事还没定。"), [])

    def test_chinese_full_name_unaffected(self):
        self.assertEqual(self.kinds("腾讯首席 AI 科学家姚顺雨说"), [])


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False, verbosity=1).result.wasSuccessful() else 1)
