"""出错邮件的单元测试：python -m unittest discover -s cloud/release/tests -v（不联网、不真发：发信用假的 SMTP 代替）。"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import gate  # noqa: E402
import notify  # noqa: E402
from fixtures import make_issue, edit_json, wj, GOOD_DAY  # noqa: E402

NO_MAIL_ENV = {k: v for k, v in os.environ.items() if k not in ("SENDER_EMAIL", "EMAIL_APP_PASSWORD", "NOTIFY_EMAIL")}


def write_verdict(issue, root, **kw):
    res = gate.judge(issue, root / "月度账本", root / "无", **kw)
    (issue / "放行结论.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return res


class NotifyTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.issue = make_issue(self.root)

    def tearDown(self):
        self.td.cleanup()

    def test_正常放行没有备注_不发(self):
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue, published="yes")
        self.assertFalse(need)
        with mock.patch.dict(os.environ, NO_MAIL_ENV, clear=True), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(notify.main(["--issue", str(self.issue), "--published", "yes"]), 0)
        self.assertIn("不发邮件", out.getvalue())

    def test_放行有备注_发(self):
        edit_json(self.issue / "审片结论.json", lambda d: d.update({"请你耳听": [{"位置": "播客 6:10", "说明": "“亿”可能念成“一”"}]}))
        edit_json(self.issue / "logs" / "fd_state.json", lambda d: d["步骤"]["images"].update({"状态": "跳过", "附加": {"缺网页配图": ["card"]}}))
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue, published="yes")
        self.assertTrue(need)
        self.assertIn("已发布，有备注", subject)
        self.assertIn("配图退回", subject)
        self.assertIn("请你耳听：播客 6:10", body)
        self.assertIn("https://wenlongzhang.com/frontier/?date=%s" % GOOD_DAY, body)

    # ---------------- 11-10：有事才发（请你耳听分“多半真念错”“多半转写听错”） ----------------
    REAL = {"位置": "播客 3:02", "说明": "原稿“5.5”，两次转写都是“5.2”", "判断": "多半真念错", "依据": "两次转写一样，版本号不同"}
    ASR1 = {"位置": "播客 10:52", "说明": "原稿“7A3000”，另跑的一次转写成“7A300”", "判断": "多半转写听错", "依据": "程序那次对上了"}
    ASR2 = {"位置": "播客 7:37", "说明": "转写多出“点赞订阅”", "判断": "多半转写听错", "依据": "常见的转写幻觉句"}

    def listen(self, items):
        edit_json(self.issue / "审片结论.json", lambda d: d.update({"请你耳听": items}))

    def test_只有多半转写听错_正常发布_不发(self):
        self.listen([self.ASR1, self.ASR2])
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue, published="yes")
        self.assertFalse(need)
        self.assertIn("只有 2 处请你耳听多半是转写听错", body)
        env = dict(NO_MAIL_ENV, SENDER_EMAIL="bot@example.com", EMAIL_APP_PASSWORD="not-a-real-password")
        with mock.patch.dict(os.environ, env, clear=True), redirect_stdout(io.StringIO()) as out, mock.patch("smtplib.SMTP") as smtp:
            self.assertEqual(notify.main(["--issue", str(self.issue), "--published", "yes"]), 0)
        smtp.assert_not_called()                     # 有发信设置也不发
        self.assertIn("不发邮件", out.getvalue())

    def test_有多半真念错_只列这几条_末尾写另有几处(self):
        self.listen([self.REAL, self.ASR1, self.ASR2])
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue, published="yes")
        self.assertTrue(need)
        self.assertEqual(subject, "【前沿简报】%s 已发布，有备注（请你耳听 1 处）" % GOOD_DAY)
        self.assertIn("- 请你耳听：播客 3:02：原稿“5.5”，两次转写都是“5.2”（审片的依据：两次转写一样，版本号不同）", body)
        self.assertNotIn("7A3000", body)
        self.assertNotIn("点赞订阅", body)
        self.assertIn("审片判断这几处多半是配音真念错了", body)
        last = "另有 2 处多半是转写听错，记在这一期的 审片.md（仓库 测试版/%s/审片.md）" % GOOD_DAY
        self.assertIn(last, body)
        self.assertLess(body.index("审片判断这几处多半是配音真念错了"), body.index(last))     # 在备注段末尾、署名之前
        self.assertLess(body.index(last), body.index("—— 这封邮件"))

    def test_只有多半真念错_不写另有几处(self):
        self.listen([self.REAL])
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue, published="yes")
        self.assertTrue(need)
        self.assertNotIn("另有", body)

    def test_旧格式没写判断_照发全列(self):
        old = [{"位置": "播客 3:02", "说明": "5.5 转写成 5.2"}, {"位置": "播客 10:52", "说明": "7A3000 转写成 7A300"}]
        self.listen(old)
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue, published="yes")
        self.assertTrue(need)
        self.assertIn("请你耳听 2 处", subject)
        self.assertIn("播客 3:02", body)
        self.assertIn("播客 10:52", body)
        self.assertIn("这几处审片结论里没写“判断”（旧格式）或写的认不出，按“多半真念错”列出来", body)
        self.assertNotIn("另有", body)

    def test_旧版放行结论_备注里没有判断_照发(self):
        """11-10 以前的 gate.py 写的放行结论：备注只有“类”“说明”。"""
        write_verdict(self.issue, self.root)
        edit_json(self.issue / "放行结论.json", lambda d: d.update({"备注": [{"类": "请你耳听", "说明": "播客 7:37：多出点赞订阅"}]}))
        need, subject, body = notify.build(self.issue, published="yes")
        self.assertTrue(need)
        self.assertIn("- 请你耳听：播客 7:37：多出点赞订阅", body)

    def test_判断写错_当多半真念错_照发(self):
        self.listen([dict(self.ASR1, 判断="较可能是转写听错")])
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue, published="yes")
        self.assertTrue(need)
        self.assertIn("7A3000", body)
        self.assertIn("写的认不出", body)

    def test_新旧混着_旧的也列_说其中几处没写判断(self):
        self.listen([self.REAL, {"位置": "视频 75 秒", "说明": "特朗普转写成川普"}, self.ASR1])
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue, published="yes")
        self.assertIn("请你耳听 2 处", subject)
        self.assertIn("视频 75 秒", body)
        self.assertIn("其中 1 处审片结论里没写“判断”", body)
        self.assertIn("另有 1 处多半是转写听错", body)

    def test_只有转写听错_但有别的事_照发_不列转写的(self):
        self.listen([self.ASR1])
        cases = [
            ("备用声音", lambda: edit_json(self.issue / "logs" / "fd_state.json", lambda d: d["步骤"]["voice"]["附加"].update(
                {"决定": {"用备用": True, "原因": "本月 Gemini 已记 $7.3，到上限的九成"}, "播客": "MiMo 备用"})), "yes", "备用声音"),
            ("配图退回", lambda: edit_json(self.issue / "logs" / "fd_state.json", lambda d: d["步骤"]["images"].update(
                {"状态": "跳过", "附加": {"缺网页配图": ["card"]}})), "yes", "配图退回"),
            ("发布出错", lambda: None, "failed", "发布出错"),
            ("发布开关没开", lambda: None, "no", "放行了但没发布"),
            ("Codex 要重新登录", lambda: (self.issue / "logs" / "codex_登录失效.txt").write_text("401", encoding="utf-8"), "yes",
             "Codex 要重新登录"),
        ]
        for name, setup, pub, want in cases:
            with self.subTest(name):
                td = tempfile.TemporaryDirectory()
                self.addCleanup(td.cleanup)
                self.root = Path(td.name)
                self.issue = make_issue(self.root)
                self.listen([self.ASR1])
                setup()
                write_verdict(self.issue, self.root)
                need, subject, body = notify.build(self.issue, published=pub)
                self.assertTrue(need, name)
                self.assertIn(want, subject)
                self.assertNotIn("7A3000", body)
                self.assertIn("另有 1 处多半是转写听错，记在这一期的 审片.md（仓库 测试版/%s/审片.md）" % GOOD_DAY, body)
                self.assertNotIn("请你耳听 ", subject)

    def test_Codex要重新登录_光这一条也发(self):
        (self.issue / "logs" / "codex_登录失效.txt").write_text("401", encoding="utf-8")
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue, published="yes")
        self.assertTrue(need)
        self.assertEqual(subject, "【前沿简报】%s 已发布，有备注（Codex 要重新登录）" % GOOD_DAY)
        self.assertIn("Codex 云端登录要重新登录", body)
        self.assertLess(body.index("Codex 云端登录"), body.index("—— 这封邮件"))

    def test_没出刊和没放行_也带Codex那句(self):
        (self.issue / "logs" / "codex_登录失效.txt").write_text("401", encoding="utf-8")
        need, subject, body = notify.build(self.issue)              # 还没有放行结论＝没出刊
        self.assertIn("没出刊", subject)
        self.assertIn("Codex 云端登录要重新登录", body)
        (self.issue / "审片结论.json").rename(self.issue / "审片结论_旧.json")
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue)
        self.assertIn("没放行", subject)
        self.assertIn("Codex 云端登录要重新登录", body)

    # ---------------- 11-11：Codex 额度用完（logs/codex_额度用完.txt，cloud/codex_login_check.py 写） ----------------
    QUOTA = "Codex 多半是额度用完（……）：3 张没画成（网页 2 张、视频 1 张），第一次在 05:02 UTC：card.png（usage limit）\n网页=2\n视频=1\n第一次=2026-11-12 05:02\n"

    def test_Codex额度用完_光这一条也发_写清张数和时间(self):
        (self.issue / "logs" / "codex_额度用完.txt").write_text(self.QUOTA, encoding="utf-8")
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue, published="yes")
        self.assertTrue(need)
        self.assertEqual(subject, "【前沿简报】%s 已发布，有备注（Codex 额度用完）" % GOOD_DAY)
        self.assertIn("配图：这一期有 3 张没画成（网页 2 张、视频 1 张），多半是 ChatGPT Plus 的 Codex 额度用完了", body)
        self.assertIn("第一次在 05:02 UTC", body)
        self.assertIn("这一期照常发布", body)
        self.assertIn("chatgpt.com/codex/settings/usage", body)
        self.assertIn("经验库第 76 件", body)
        self.assertNotIn("Codex 云端登录要重新登录", body)
        self.assertLess(body.index("配图："), body.index("—— 这封邮件"))

    def test_Codex额度用完_没放行时不说照常发布(self):
        (self.issue / "logs" / "codex_额度用完.txt").write_text(self.QUOTA, encoding="utf-8")
        (self.issue / "审片结论.json").rename(self.issue / "审片结论_旧.json")
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue)
        self.assertIn("没放行", subject)
        self.assertIn("多半是 ChatGPT Plus 的 Codex 额度用完了", body)
        self.assertNotIn("照常发布", body)

    def test_Codex额度和登录失效都有_只说登录失效(self):
        (self.issue / "logs" / "codex_额度用完.txt").write_text(self.QUOTA, encoding="utf-8")
        (self.issue / "logs" / "codex_登录失效.txt").write_text("401", encoding="utf-8")
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue, published="yes")
        self.assertEqual(subject, "【前沿简报】%s 已发布，有备注（Codex 要重新登录）" % GOOD_DAY)
        self.assertNotIn("额度用完", body)

    def test_Codex额度记号读不出数_照样发(self):
        (self.issue / "logs" / "codex_额度用完.txt").write_text("旧格式，只有一句话\n", encoding="utf-8")
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue, published="yes")
        self.assertTrue(need)
        self.assertIn("这一期有几张没画成，多半是", body)

    def test_拆仓库以后_运行链接和接着跑指公开仓库那次运行_文件包在私有发行版(self):
        edit_json(self.issue / "logs" / "fd_state.json", lambda d: d["步骤"]["voice"].update({"状态": "失败", "说明": "Vertex 回 500"}))
        env = {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "dylan-zhang-wl/frontier-daily", "GITHUB_RUN_ID": "1",
               "FD_RUN_REPO": "dylan-zhang-wl/frontier-briefing", "FD_RUN_ID": "42700000002"}
        with mock.patch.dict(os.environ, env):
            need, subject, body = notify.build(self.issue, claim="kept", claim_tag="issue/%s" % GOOD_DAY)
        self.assertIn("这次运行：https://github.com/dylan-zhang-wl/frontier-briefing/actions/runs/42700000002", body)
        self.assertIn("-f from_run=42700000002 -f from_step=11", body)
        self.assertIn("gh workflow run frontier-daily.yml -R dylan-zhang-wl/frontier-briefing", body)
        self.assertIn("私有仓库发行版 run-42700000002 里的 issue-%s.tar.gz" % GOOD_DAY, body)
        self.assertNotIn("artifact", body)

    def test_没放行_手动放行指私有仓库的放行发布(self):
        (self.issue / "审片结论.json").rename(self.issue / "审片结论_旧.json")
        write_verdict(self.issue, self.root)
        env = {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "dylan-zhang-wl/frontier-daily", "FD_RUN_ID": "42700000003"}
        with mock.patch.dict(os.environ, env):
            need, subject, body = notify.build(self.issue)
        self.assertIn("打开 https://github.com/dylan-zhang-wl/frontier-daily/actions → 左边选“放行发布”", body)
        self.assertIn("run-42700000003", body)

    def test_没放行_只列真念错_另有几处(self):
        self.listen([self.REAL, self.ASR1, self.ASR2])
        edit_json(self.issue / "审片结论.json", lambda d: d.update({"放行": False, "立即": [{"编号": "55", "说明": "数字找不到出处"}]}))
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue)
        self.assertTrue(need)
        self.assertIn("没放行：第 9 条", subject)
        self.assertIn("另外记下的：", body)
        self.assertIn("播客 3:02", body)
        self.assertNotIn("7A3000", body)
        self.assertIn("另有 2 处多半是转写听错", body)

    def test_放行和邮件两边一致(self):
        """给人看那段话列出来的请你耳听、报的“另有几处”，和邮件里的一样。"""
        combos = [[], [self.REAL], [self.ASR1], [self.REAL, self.ASR1, self.ASR2], [{"位置": "旧", "说明": "旧格式"}, self.ASR2]]
        for items in combos:
            with self.subTest(n=len(items)):
                self.listen(items)
                res = write_verdict(self.issue, self.root)
                need, subject, body = notify.build(self.issue, published="yes")
                tell = [x for x in items if x.get("判断") != "多半转写听错"]
                asr = len(items) - len(tell)
                self.assertEqual(need, bool(tell))
                for x in items:
                    self.assertEqual(x["位置"] in res["给人看"], x in tell)
                    self.assertEqual(x["位置"] in body, need and x in tell)
                if asr:
                    self.assertIn("另有 %d 处请你耳听多半是转写听错" % asr, res["给人看"])
                    self.assertIn(("另有 %d 处多半是转写听错" % asr) if need else ("只有 %d 处请你耳听多半是转写听错" % asr), body)

    def test_放行了但发布出错或没开开关_也发(self):
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue, published="failed")
        self.assertTrue(need)
        self.assertIn("发布出错", subject)
        need, subject, body = notify.build(self.issue, published="no")
        self.assertTrue(need)
        self.assertIn("SITE_DEPLOY_ENABLED", body)

    def test_没放行(self):
        (self.issue / "审片结论.json").rename(self.issue / "审片结论_旧.json")
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue)
        self.assertTrue(need)
        self.assertIn("没放行：第 9 条", subject)
        self.assertIn("审片.md 开头", body)
        self.assertIn("这期能放心看", body)
        self.assertIn("手动放行", body)

    def test_没出刊_卡在第几步(self):
        edit_json(self.issue / "logs" / "fd_state.json",
                  lambda d: d["步骤"]["voice"].update({"状态": "失败", "说明": "配音要用的 Google 项目是留给大论文的那个，停下来叫人"}))
        need, subject, body = notify.build(self.issue)
        self.assertTrue(need)
        self.assertIn("没出刊", subject)
        self.assertIn("第 11 步配音：失败", body)
        self.assertIn("00_调度报告.md 开头", body)

    def test_没出刊_期目录都没有(self):
        need, subject, body = notify.build(self.root / "2026-11-30")
        self.assertTrue(need)
        self.assertIn("都没有建起来", body)

    def test_没出刊_第4步以前出错_认领放回_说会自动再试(self):
        edit_json(self.issue / "logs" / "fd_state.json", lambda d: d["步骤"]["fetch"].update({"状态": "失败", "说明": "62 个来源都抓不到"}))
        need, subject, body = notify.build(self.issue, claim="released", claim_tag="issue/%s" % GOOD_DAY)
        self.assertTrue(need)
        self.assertEqual(subject, "【前沿简报】%s 没出刊，稍后自动再试" % GOOD_DAY)
        self.assertIn("第 1 步抓取：失败", body)
        self.assertIn("标签 issue/%s）会放回" % GOOD_DAY, body)
        self.assertIn("04:17、04:43、06:47", body)
        self.assertIn("gh workflow run frontier-daily.yml", body)
        self.assertNotIn("删标签", body)
        self.assertIn("不要在运行页面上点 Re-run", body)

    def test_没出刊_第4步以后出错_认领留着_写怎么接着跑和删标签(self):
        edit_json(self.issue / "logs" / "fd_state.json", lambda d: d["步骤"]["voice"].update({"状态": "失败", "说明": "Vertex 回 500"}))
        with mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "42600000001"}):
            need, subject, body = notify.build(self.issue, claim="kept", claim_tag="issue/%s" % GOOD_DAY)
        self.assertTrue(need)
        self.assertEqual(subject, "【前沿简报】%s 没出刊" % GOOD_DAY)
        self.assertIn("重跑前要先删标签 issue/%s" % GOOD_DAY, body)
        self.assertIn("gh api -X DELETE repos/dylan-zhang-wl/frontier-briefing/git/refs/tags/issue/%s" % GOOD_DAY, body)
        self.assertIn("-f from_run=42600000001 -f from_step=11", body)
        self.assertIn("test_mode=false -f gemini=default", body)

    def test_认领只管没出刊_没放行和放行不加(self):
        (self.issue / "审片结论.json").rename(self.issue / "审片结论_旧.json")
        write_verdict(self.issue, self.root)
        need, subject, body = notify.build(self.issue, claim="kept", claim_tag="issue/%s" % GOOD_DAY)
        self.assertIn("没放行", subject)
        self.assertNotIn("删标签", body)

    def test_周六_只跑第1到3步出错(self):
        day = "2026-11-14"
        issue = make_issue(self.root, day=day)
        edit_json(issue / "logs" / "fd_state.json", lambda d: d["步骤"]["cluster"].update({"状态": "失败", "说明": "LaBSE 载入失败"}))
        need, subject, body = notify.build(issue, kind="没出刊", saturday=True, claim="released", claim_tag="issue/" + day)
        self.assertTrue(need)
        self.assertEqual(subject, "【前沿简报】%s（周六）抓取入库出错，稍后自动再试" % day)
        self.assertIn("是周六，不出刊，只跑第 1–3 步", body)
        self.assertIn("第 2 步粗筛归并：失败", body)
        self.assertNotIn("00_调度报告.md 开头", body)
        with mock.patch.dict(os.environ, NO_MAIL_ENV, clear=True), redirect_stdout(io.StringIO()) as out:
            rc = notify.main(["--issue", str(issue), "--kind", "没出刊", "--saturday", "--claim", "released", "--claim-tag", "issue/" + day, "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("标题：【前沿简报】%s（周六）抓取入库出错，稍后自动再试" % day, out.getvalue())

    def test_没设发信环境变量_只打印(self):
        with mock.patch.dict(os.environ, NO_MAIL_ENV, clear=True), redirect_stdout(io.StringIO()) as out, \
                mock.patch("smtplib.SMTP") as smtp:
            self.assertEqual(notify.main(["--issue", str(self.root / "2026-11-30")]), 0)
        smtp.assert_not_called()
        self.assertIn("只打印", out.getvalue())
        self.assertIn("标题：【前沿简报】2026-11-30 没出刊", out.getvalue())

    def test_dry_run_有环境变量也不发(self):
        env = dict(NO_MAIL_ENV, SENDER_EMAIL="bot@example.com", EMAIL_APP_PASSWORD="not-a-real-password")
        with mock.patch.dict(os.environ, env, clear=True), redirect_stdout(io.StringIO()) as out, mock.patch("smtplib.SMTP") as smtp:
            notify.main(["--issue", str(self.root / "2026-11-30"), "--dry-run"])
        smtp.assert_not_called()
        self.assertNotIn("not-a-real-password", out.getvalue())

    def test_有环境变量就真发_照期刊监控的写法(self):
        env = dict(NO_MAIL_ENV, SENDER_EMAIL="bot@example.com", EMAIL_APP_PASSWORD="not-a-real-password", NOTIFY_EMAIL="me@example.com")
        with mock.patch.dict(os.environ, env, clear=True), redirect_stdout(io.StringIO()) as out, mock.patch("smtplib.SMTP") as smtp:
            rc = notify.main(["--issue", str(self.root / "2026-11-30")])
        self.assertEqual(rc, 0)
        smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=60)
        server = smtp.return_value
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("bot@example.com", "not-a-real-password")
        msg = server.send_message.call_args[0][0]
        self.assertEqual(msg["To"], "me@example.com")
        self.assertNotIn("not-a-real-password", out.getvalue())


if __name__ == "__main__":
    unittest.main()
