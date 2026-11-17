"""MiMo 备用那天的放行判定和邮件（2026-11-17 加，feat/mimo-release）：python -m unittest discover -s cloud/release/tests -v

假期目录三种情况：
  · 正常那天（全都过）、正常那天视频真坏了：判定和说明和改之前一样（9 条、没过哪几条、每条的说明一字不差）；
  · 备用而且不出视频（fd 记着第 14、15 步“视频：关”，期目录有 备用写稿.json、“视频”写“关”）：第 1、3、7 条放过、写明；
    第 9 条按 Claude不能用.json 的“自动放行”：true 才放行，没写、写错、文件没有、读不出都不放行；手动放行照旧放行；
  · 只有一个记号（只有 fd 关了视频，或只有 备用写稿.json）：照旧不过。
邮件：第 1 天、第 3 天（标题【第 3 天，要处理】、第一段是换令牌的步骤）、没自动放行（写清怎么手动放行）、额度用完带恢复时间、
备用写稿也停下（没出刊）、要人看、宽认。不联网、不真发。
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
sys.path.insert(0, str(HERE))
import gate  # noqa: E402
import notify  # noqa: E402
from fixtures import make_issue, edit_json, wj, GOOD_DAY  # noqa: E402

CLEAN_ENV = {k: v for k, v in os.environ.items() if k not in (
    "SENDER_EMAIL", "EMAIL_APP_PASSWORD", "NOTIFY_EMAIL", "GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID",
    "FD_RUN_ID", "FD_RUN_REPO")}


def fd_video_off(d):
    """fd 关着视频跑完的样子（照 pipeline/orchestrator/steps.py 第 11、14、15 步关着时写的记录）。"""
    d["步骤"]["voice"]["附加"].update({"视频旁白": "不配（视频：关）", "视频开关": "关"})
    d["步骤"]["voice"]["附加"].pop("视频引擎", None)
    d["步骤"]["voice"]["说明"] = "播客：主声音；视频旁白：不配（视频：关）"
    d["步骤"]["video"].update({"状态": "跳过", "说明": "视频：关，这一期不出视频", "照常往下": True, "附加": {"视频开关": "关"}})
    d["步骤"]["web2"].update({"状态": "跳过", "说明": "视频：关，第 13 步的网页就是成品", "照常往下": True,
                             "附加": {"带视频": False, "视频开关": "关"}})


def video_broken(d):
    """正常那天视频真坏了：组装失败，网页不带视频（fd 照常往下）。"""
    d["步骤"]["video"].update({"状态": "失败", "说明": "视频没组装成，这一期网页不放视频：✗ 出错", "照常往下": True})
    d["步骤"]["web2"].update({"状态": "跳过", "说明": "没有视频，第 13 步的网页就是成品", "照常往下": True, "附加": {}})


BW = {"说明": "这一期第 4–9 步由 MiMo 备用写稿", "写稿": "MiMo（备用）", "结果": "第 4–9 步做完", "调用次数": 12,
      "token合计": 1386000, "其中缓存命中": 900000, "credits约": 463000000,
      "视频": "关：这一期不出视频，只写了播客和网页（FD_VIDEO=off）"}


class Base(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.issue = make_issue(self.root)
        self.state = self.issue / "logs" / "fd_state.json"
        self.env = mock.patch.dict(os.environ, CLEAN_ENV, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.td.cleanup()

    def judge(self, **kw):
        return gate.judge(self.issue, self.root / "月度账本", self.root / "无", **kw)

    def backup_day(self, auto=None, reason="登录失效", days=1, resume="", review=True, bw=None, down=True, video_off=True):
        """备用而且不出视频的一期。auto=None：Claude不能用.json 里不写“自动放行”。"""
        if video_off:
            edit_json(self.state, fd_video_off)
            old = self.issue / "11_视频v3" / "video3_media.json"
            if old.exists():                       # 同一个测试里可能叫好几次
                old.rename(self.issue / "旧视频_挪开.json")
        wj(self.issue / "备用写稿.json", dict(BW, **(bw or {})))
        if down:
            d = {"原因": reason, "认法": "原话", "哪一步": ["写稿", "审片"], "恢复时间": resume, "连续第几天": days,
                 "写于": "2026-11-09T04:20:00Z"}
            if auto is not None:
                d["自动放行"] = auto
            wj(self.issue / "Claude不能用.json", d)
        if review:
            edit_json(self.issue / "审片结论.json", lambda x: x.update({"审片": "MiMo（备用）"}))

    def verdict(self, **kw):
        res = self.judge(**kw)
        (self.issue / "放行结论.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        return res

    def cond(self, res, no):
        return [c for c in res["条件"] if c["编号"] == no][0]


# ================================================================ 放行判定
class GateNormalDays(Base):
    def test_正常那天_和改之前一样(self):
        res = self.judge()
        self.assertTrue(res["放行"])
        self.assertEqual(res["备注"], [])
        self.assertEqual(self.cond(res, 1)["说明"], "17 步都是“做完”")
        self.assertEqual(self.cond(res, 3)["说明"], "播客（05_配音/播客_v3_带音效）、视频都在网页上")
        self.assertEqual(self.cond(res, 7)["说明"], "视频 108.0 秒；播客 11.0 分钟（区间 10–15）")
        self.assertEqual(self.cond(res, 9)["说明"], "审片结论放行（过 44、不过 7、查不了 2；07:50 写）")
        self.assertEqual(self.cond(res, 9)["证据"], ["审片结论.json 日期／放行／立即／请你耳听"])

    def test_正常那天视频真坏了_照旧不放行_说明一字不差(self):
        edit_json(self.state, video_broken)
        (self.issue / "11_视频v3" / "video3_media.json").rename(self.issue / "x.json")
        res = self.judge()
        self.assertFalse(res["放行"])
        self.assertEqual(res["没过"], [1, 3, 7])
        self.assertEqual(self.cond(res, 1)["说明"], "第 14 步视频：失败；第 15 步网页带视频再组装：跳过")
        self.assertEqual(self.cond(res, 3)["说明"], "这一期是数据版：网页没带视频")
        self.assertEqual(self.cond(res, 7)["说明"], "查不到视频时长")
        self.assertEqual(res["备注"], [])

    def test_只有fd关了视频_没有备用写稿_照旧不过(self):
        edit_json(self.state, fd_video_off)
        (self.issue / "11_视频v3" / "video3_media.json").rename(self.issue / "x.json")
        res = self.judge()
        self.assertEqual(res["没过"], [1, 3, 7])
        self.assertEqual(self.cond(res, 1)["说明"], "第 14 步视频：跳过；第 15 步网页带视频再组装：跳过")

    def test_只有备用写稿_fd没关视频_视频真坏了_照旧不过(self):
        self.backup_day(auto=True, video_off=False)
        edit_json(self.state, video_broken)
        (self.issue / "11_视频v3" / "video3_media.json").rename(self.issue / "x.json")
        res = self.judge()
        self.assertEqual(res["没过"], [1, 3, 7])

    def test_备用写稿的视频一栏不是关_照旧不过(self):
        self.backup_day(auto=True, bw={"视频": "开"})
        self.assertEqual(self.judge()["没过"], [1, 3, 7])
        self.backup_day(auto=True, bw={"视频": None})
        self.assertEqual(self.judge()["没过"], [1, 3, 7])

    def test_MiMo审片_不是备用写稿那天_照常按放行立即判(self):
        edit_json(self.issue / "审片结论.json", lambda x: x.update({"审片": "MiMo（备用）"}))
        res = self.judge()
        self.assertTrue(res["放行"])
        self.assertEqual([n["类"] for n in res["备注"]], ["MiMo 审片"])
        self.assertIn("MiMo（备用）审片", self.cond(res, 9)["说明"])
        edit_json(self.issue / "审片结论.json", lambda x: x.update({"立即": [{"编号": 40, "说明": "验收没过"}]}))
        self.assertEqual(self.judge()["没过"], [9])


class GateBackupDay(Base):
    def test_备用不出视频_自动放行true_放行_写明(self):
        self.backup_day(auto=True)
        res = self.judge()
        self.assertTrue(res["放行"], res["给人看"])
        self.assertTrue(res["按条件放行"])
        self.assertEqual(len(res["条件"]), 9)
        self.assertIn("第 14、15 步跳过", self.cond(res, 1)["说明"])
        self.assertEqual(self.cond(res, 3)["说明"], "播客（05_配音/播客_v3_带音效）在网页上；视频：关（MiMo 备用写稿那天按规矩不出视频）")
        self.assertIn("不查视频时长", self.cond(res, 7)["说明"])
        self.assertIn("播客 11.0 分钟", self.cond(res, 7)["说明"])
        self.assertEqual([n["类"] for n in res["备注"]], ["MiMo 备用", "MiMo 备用", "MiMo 审片"])
        self.assertIn("设定是审片过了就自动放行", res["给人看"])
        tell, quiet = gate.split_notes(res["备注"])
        self.assertEqual(len(tell), 3)                       # 三条都要告诉你：放行了也发信

    def test_备用不出视频_没写自动放行_不放行(self):
        self.backup_day(auto=None)
        res = self.judge()
        self.assertFalse(res["放行"])
        self.assertEqual(res["没过"], [9])
        self.assertEqual(self.cond(res, 9)["说明"], gate.NO_AUTO_RELEASE)
        self.assertIn("备用写稿.json", self.cond(res, 9)["证据"])

    def test_自动放行不是明明白白的true_都不放行(self):
        for v in (False, "true", 1, None):
            self.backup_day(auto=v)
            self.assertEqual(self.judge()["没过"], [9], v)
        self.backup_day(down=False)                                      # 没有 Claude不能用.json
        (self.issue / "Claude不能用.json").exists() and (self.issue / "Claude不能用.json").rename(self.issue / "挪开.json")
        res = self.judge()
        self.assertEqual(res["没过"], [9])
        self.assertIn("没有 Claude不能用.json", res["给人看"])
        (self.issue / "Claude不能用.json").write_text("{坏的", encoding="utf-8")   # 读不出
        self.assertEqual(self.judge()["没过"], [9])

    def test_手动放行照旧放行(self):
        self.backup_day(auto=None)
        res = self.judge(manual="看过了")
        self.assertTrue(res["放行"])
        self.assertFalse(res["按条件放行"])
        self.assertEqual(res["没过"], [9])

    def test_没有审片结论_两个理由都写_备注照记(self):
        self.backup_day(auto=None, review=False)
        (self.issue / "审片结论.json").rename(self.issue / "x.json")
        res = self.judge()
        self.assertEqual(res["没过"], [9])
        why = self.cond(res, 9)["说明"]
        self.assertIn("没有 审片结论.json", why)
        self.assertIn(gate.NO_AUTO_RELEASE, why)
        self.assertIn("MiMo 备用", [n["类"] for n in self.cond(res, 9)["备注"]])

    def test_MiMo审片标了立即_不放行(self):
        self.backup_day(auto=True)
        edit_json(self.issue / "审片结论.json", lambda x: x.update({"立即": [{"编号": 5, "说明": "整期换成备用声音"}]}))
        res = self.judge()
        self.assertEqual(res["没过"], [9])
        self.assertIn("立即", self.cond(res, 9)["说明"])

    def test_视频关却还带着旧视频_第3条不过(self):
        self.backup_day(auto=True)
        edit_json(self.state, lambda d: d["步骤"]["web2"].update({"状态": "做完", "附加": {"带视频": True, "视频开关": "关"}}))
        res = self.judge()
        self.assertEqual(res["没过"], [3])
        self.assertIn("网页却带着视频", self.cond(res, 3)["说明"])


MISSED_11 = [{"项": 11, "是什么": "人名、头衔在原文里", "为什么": "时间到了"}]
WHY_11 = "MiMo 审片第 11 项（人名、头衔在原文里）没查成：等你看过再手动放行"


class GateMimoMissed(Base):
    """11-17 晚：审片结论的“MiMo没查成”。开关 gate.MIMO_REVIEW_INCOMPLETE_BLOCKS 开着（默认）第 9 条不过；
    关着时过没过、说明、证据和没有这一栏时一字不差，只多一条“MiMo 没查成”备注。"""

    def missed(self, missed=MISSED_11, who="MiMo（备用）"):
        edit_json(self.issue / "审片结论.json", lambda x: x.update({"审片": who, gate.MIMO_MISSED: missed}))

    def test_默认开着(self):
        self.assertIs(gate.MIMO_REVIEW_INCOMPLETE_BLOCKS, True)

    def test_备用那天_自动放行true_第11项没查成_不放行(self):
        self.backup_day(auto=True)
        self.missed()
        res = self.judge()
        self.assertFalse(res["放行"])
        self.assertEqual(res["没过"], [9])
        self.assertEqual(self.cond(res, 9)["说明"], WHY_11)
        note = [n for n in res["备注"] if n["类"] == gate.MIMO_MISSED_KIND][0]
        self.assertEqual(note["项"], [11])
        self.assertIn("第 11 项（人名、头衔在原文里）：时间到了", note["说明"])
        self.assertIn("第 9 条（%s）没满足：%s" % (gate.TITLES[9], WHY_11), res["给人看"])
        self.assertIn("要你自己看一眼", res["给人看"])

    def test_没开自动放行_两句理由先后一定(self):
        self.backup_day(auto=None)
        self.missed()
        self.assertEqual(self.cond(self.judge(), 9)["说明"], gate.NO_AUTO_RELEASE + "；" + WHY_11)

    def test_Claude写稿_MiMo审片_也挡(self):
        self.missed()                                    # 没有 备用写稿.json：这一期是 Claude 写的，只有审片是 MiMo
        res = self.judge()
        self.assertEqual(res["没过"], [9])
        self.assertEqual(self.cond(res, 9)["说明"], WHY_11)

    def test_超过3项只写编号(self):
        self.missed([{"项": n, "是什么": "某项", "为什么": "时间到了"} for n in (6, 7, 8, 11)])
        self.assertEqual(self.cond(self.judge(), 9)["说明"], "MiMo 审片第 6、7、8、11 项没查成：等你看过再手动放行")

    def test_开关关着_和没有这一栏一字不差_只多备注(self):
        for backup in (True, False):
            with self.subTest(backup=backup):
                self.tearDown()
                self.setUp()
                if backup:
                    self.backup_day(auto=True)
                else:
                    edit_json(self.issue / "审片结论.json", lambda x: x.update({"审片": "MiMo（备用）"}))
                before = self.judge()
                self.missed()
                with mock.patch.object(gate, "MIMO_REVIEW_INCOMPLETE_BLOCKS", False):
                    after = self.judge()
                self.assertTrue(after["放行"])
                for k in ("放行", "按条件放行", "没过"):
                    self.assertEqual(before[k], after[k])
                for a, b in zip(before["条件"], after["条件"]):
                    self.assertEqual((a["编号"], a["过"], a["说明"], a["证据"]), (b["编号"], b["过"], b["说明"], b["证据"]))
                extra = [n for n in after["备注"] if n not in before["备注"]]
                self.assertEqual([n["类"] for n in extra], [gate.MIMO_MISSED_KIND])
                self.assertEqual([n for n in after["备注"] if n["类"] != gate.MIMO_MISSED_KIND], before["备注"])

    def test_没有这一栏_空列表_Claude审片写了_都照旧(self):
        self.backup_day(auto=True)
        base = self.judge()
        self.missed([])
        self.assertEqual(self.judge()["条件"], base["条件"])
        self.missed(who="")                             # Claude 审片：不认这一栏
        edit_json(self.issue / "审片结论.json", lambda x: x.pop("审片"))
        res = self.judge()
        self.assertTrue(res["放行"])
        self.assertNotIn(gate.MIMO_MISSED_KIND, [n["类"] for n in res["备注"]])

    def test_写坏了也挡(self):
        self.missed("第 11 项")
        res = self.judge()
        self.assertEqual(res["没过"], [9])
        self.assertIn("没查成：等你看过再手动放行", self.cond(res, 9)["说明"])


# ================================================================ 邮件
class Mail(Base):
    def build(self, **kw):
        return notify.build(self.issue, **kw)

    def test_第1天_自动放行_放行了也发(self):
        self.backup_day(auto=True)
        self.verdict()
        need, subject, body = self.build(published="yes")
        self.assertTrue(need)
        self.assertEqual(subject, "【前沿简报】%s 已发布（MiMo 备用写稿、MiMo 审片；Claude 登录失效，连续第 1 天）" % GOOD_DAY)
        first = body.splitlines()[0]
        self.assertEqual(first, "Claude 不能用：云端的 Claude 登录失效（令牌过期或被撤销）。这是连续第 1 天。")
        self.assertIn("由 MiMo 备用写稿（调用 12 次、约 138.6 万 token、约 4.63 亿 credits）", body)
        self.assertIn("这一期不出视频", body)
        self.assertIn("审片由 MiMo（备用）做：只看了文字，没听音频。", body)
        self.assertIn("已发布：https://wenlongzhang.com/frontier/?date=%s" % GOOD_DAY, body)
        self.assertIn("claude setup-token", body)                   # 登录失效不会自己好：步骤放在后面
        self.assertNotIn("【要你处理】", body)
        self.assertNotIn("- MiMo 备用：", body)                       # 开头那段写过了，备注里不再逐条列
        self.assertLess(body.index("Claude 不能用"), body.index("已发布"))

    def test_第3天_标题要处理_第一段是步骤(self):
        self.backup_day(auto=True, days=3)
        self.verdict()
        need, subject, body = self.build(published="yes")
        self.assertTrue(subject.startswith("【第 3 天，要处理】【前沿简报】%s 已发布（" % GOOD_DAY))
        self.assertIn("连续第 3 天", subject)
        lines = body.splitlines()
        self.assertEqual(lines[0], "【要你处理】Claude 已经连续 3 天不能用，照下面做：")
        self.assertIn("    claude setup-token", lines[:8])
        self.assertIn("gh secret set CLAUDE_CODE_OAUTH_TOKEN -R dylan-zhang-wl/frontier-briefing", body)
        self.assertIn("gh secret set CLAUDE_CODE_OAUTH_TOKEN -R dylan-zhang-wl/frontier-daily", body)
        self.assertIn("cloud/密钥与重置手册.md 补一行", body)
        self.assertEqual(body.count("claude setup-token"), 1)       # 第一段写了，后面不再重复

    def test_没自动放行_写清怎么手动放行(self):
        self.backup_day(auto=None)
        res = self.verdict()
        self.assertFalse(res["放行"])
        need, subject, body = self.build()
        self.assertTrue(need)
        self.assertEqual(subject, "【前沿简报】%s 没放行：第 9 条没满足（MiMo 备用写稿、MiMo 审片；Claude 登录失效，连续第 1 天）" % GOOD_DAY)
        self.assertIn(gate.NO_AUTO_RELEASE, body)
        for s in ("私有仓库 dylan-zhang-wl/frontier-daily", "https://github.com/dylan-zhang-wl/frontier-daily/actions",
                  "左边选“放行发布”", "Run workflow", "（date）填 %s" % GOOD_DAY, "（run_id）留空", "（reason）写放行理由"):
            self.assertIn(s, body)
        self.assertNotIn("- MiMo 备用：", body)

    def test_额度用完_写恢复时间_不叫你换令牌(self):
        self.backup_day(auto=True, reason="额度用完", resume="2026-11-09T09:30:00Z", days=2)
        self.verdict()
        need, subject, body = self.build(published="yes")
        self.assertIn("Claude 额度用完，连续第 2 天", subject)
        self.assertIn("Claude 订阅的额度用完了，预计 2026-11-09 09:30 UTC 恢复", body)
        self.assertNotIn("setup-token", body)
        self.backup_day(auto=True, reason="额度用完", resume="2026-11-09T09:30:00Z", days=4)
        self.verdict()
        need, subject, body = self.build(published="yes")
        self.assertTrue(subject.startswith("【第 4 天，要处理】"))
        self.assertTrue(body.startswith("【要你处理】Claude 已经连续 4 天不能用"))
        self.assertIn("claude.ai/settings/usage", body.split("\n\n")[1])          # 第一段：步骤
        self.assertNotIn("setup-token", body)

    def test_备用写稿也停下_没出刊(self):
        self.backup_day(auto=True, review=False, bw={"结果": "停下：第 7 步交回改过还不过，停下等人"})
        edit_json(self.state, lambda d: (d["步骤"]["check"].update({"状态": "等人", "说明": "稿子 3 处要改"}),
                                         d["运行记录"][-1].update({"结果": "停在第 7 步：稿子 3 处要改"})))
        need, subject, body = self.build(kind="没出刊")
        self.assertEqual(subject, "【前沿简报】%s 没出刊（MiMo 备用写稿；Claude 登录失效，连续第 1 天）" % GOOD_DAY)
        self.assertIn("卡在哪：第 7 步稿子检查：等人（稿子 3 处要改）\nClaude 不能用，MiMo 备用写稿也停在第 7 步：第 7 步交回改过还不过，停下等人", body)

    def test_停在第16步_不把视频关的第14步当卡住(self):
        self.backup_day(auto=True)
        edit_json(self.state, lambda d: d["步骤"]["accept"].update({"状态": "失败", "说明": "验收没过 1 项"}))
        self.assertEqual(notify.stuck_at(self.issue)[0], 16)

    def test_要人看_宽认_没有Claude不能用(self):
        self.backup_day(auto=True, bw={"要人看": ["播客总长 2,699 字，低于下限", {"说明": "E040 摘要请核对出处"}]})
        edit_json(self.issue / "Claude不能用.json", lambda d: d.update({"认法": "宽认"}))
        self.verdict()
        need, subject, body = self.build(published="yes")
        self.assertIn("MiMo 备用写稿记下的、要你看一眼的：\n- 播客总长 2,699 字，低于下限\n- E040 摘要请核对出处", body)
        self.assertIn("按宽一点的认法判的，待核", body)
        (self.issue / "Claude不能用.json").rename(self.issue / "挪开.json")
        self.verdict()
        need, subject, body = self.build()
        self.assertIn("没放行", subject)
        self.assertIn("Claude 不能用，连续第 1 天", subject)
        self.assertIn("原因没记下", body)

    def test_备用那天有请你耳听_标题带上(self):
        self.backup_day(auto=True)
        edit_json(self.issue / "审片结论.json", lambda x: x.update({"请你耳听": [
            {"位置": "播客 3:02", "说明": "原稿“5.5”，转写“5.2”", "判断": "多半真念错", "依据": "版本号", "关乎事实": True}]}))
        self.verdict()
        need, subject, body = self.build(published="yes")
        self.assertTrue(subject.endswith("连续第 1 天；请你耳听 1 处）"), subject)
        self.assertIn("【事实】请你耳听：播客 3:02", body)

    def test_平常的日子_一封都不多发(self):
        self.verdict()
        self.assertIsNone(notify.backup_info(self.issue))
        need, subject, body = self.build(published="yes")
        self.assertFalse(need)

    def test_没查成_没放行_标题正文都写哪一项(self):
        self.backup_day(auto=True)
        edit_json(self.issue / "审片结论.json", lambda x: x.update({gate.MIMO_MISSED: MISSED_11}))
        self.verdict()
        need, subject, body = self.build()
        self.assertTrue(need)
        self.assertEqual(subject, "【前沿简报】%s 没放行：第 9 条没满足（MiMo 备用写稿、MiMo 审片；Claude 登录失效，连续第 1 天；"
                                  "MiMo 审片第 11 项没查成）" % GOOD_DAY)
        self.assertIn("- 第 9 条 %s：%s" % (gate.TITLES[9], WHY_11), body)
        self.assertIn("- MiMo 没查成：MiMo 审片有 1 项没查成，没人查过，要你自己看一眼：第 11 项（人名、头衔在原文里）：时间到了", body)
        self.assertIn("（run_id）留空", body)

    def test_没查成_开关关着_放行了也写(self):
        self.backup_day(auto=True)
        edit_json(self.issue / "审片结论.json", lambda x: x.update({gate.MIMO_MISSED: MISSED_11}))
        with mock.patch.object(gate, "MIMO_REVIEW_INCOMPLETE_BLOCKS", False):
            res = self.verdict()
        self.assertTrue(res["放行"])
        need, subject, body = self.build(published="yes")
        self.assertEqual(subject, "【前沿简报】%s 已发布（MiMo 备用写稿、MiMo 审片；Claude 登录失效，连续第 1 天；"
                                  "MiMo 审片第 11 项没查成）" % GOOD_DAY)
        self.assertIn("第 11 项（人名、头衔在原文里）：时间到了", body)

    def test_main_dry_run(self):
        self.backup_day(auto=True)
        self.verdict()
        import io
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(notify.main(["--issue", str(self.issue), "--published", "yes", "--dry-run"]), 0)
        self.assertIn("标题：【前沿简报】%s 已发布（MiMo 备用写稿" % GOOD_DAY, out.getvalue())

    def test_main_dry_run_没查成(self):
        """dry-run（放行 --published yes，和 auto）：标题、正文都提到第 11 项。"""
        import io
        from contextlib import redirect_stdout
        self.backup_day(auto=True)
        edit_json(self.issue / "审片结论.json", lambda x: x.update({gate.MIMO_MISSED: MISSED_11}))
        self.verdict()
        for args in (["--kind", "放行", "--published", "yes"], []):
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(notify.main(["--issue", str(self.issue), "--dry-run"] + args), 0)
            text = out.getvalue()
            title = [x for x in text.splitlines() if x.startswith("标题：")][0]
            self.assertIn("MiMo 审片第 11 项没查成", title, args)
            self.assertIn("第 11 项（人名、头衔在原文里）：时间到了", text.split("正文：", 1)[1], args)


if __name__ == "__main__":
    unittest.main()
