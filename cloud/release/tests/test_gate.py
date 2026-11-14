"""放行判定的单元测试：python -m unittest discover -s cloud/release/tests -v（不联网、不用密钥）。"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import gate  # noqa: E402
from fixtures import make_issue, edit_json, wj, GOOD_DAY  # noqa: E402


class GateTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.issue = make_issue(self.root)
        self.state = self.issue / "logs" / "fd_state.json"

    def tearDown(self):
        self.td.cleanup()

    def judge(self, **kw):
        return gate.judge(self.issue, self.root / "月度账本", self.root / "无", **kw)

    def failed(self, res):
        return res["没过"]

    def test_全都满足就放行_退出码0(self):
        res = self.judge()
        self.assertTrue(res["放行"], res["给人看"])
        self.assertEqual(res["没过"], [])
        self.assertEqual(len(res["条件"]), 9)
        rc = gate.main(["--issue", str(self.issue), "--ledger-dir", str(self.root / "月度账本")])
        self.assertEqual(rc, 0)
        out = json.loads((self.issue / "放行结论.json").read_text(encoding="utf-8"))
        self.assertTrue(out["放行"])
        self.assertIn("给人看", out)

    def test_1_有一步失败或等人(self):
        edit_json(self.state, lambda d: d["步骤"]["mix"].update({"状态": "失败"}))
        self.assertEqual(self.failed(self.judge()), [1])
        edit_json(self.state, lambda d: (d["步骤"]["mix"].update({"状态": "做完"}), d["步骤"].pop("report")))
        res = self.judge()
        self.assertEqual(self.failed(res), [1])
        self.assertIn("没有记录", res["条件"][0]["说明"])

    def test_1_配图跳过照常放行但记备注(self):
        edit_json(self.state, lambda d: d["步骤"]["images"].update({"状态": "跳过", "附加": {"缺网页配图": ["card"], "缺视频配图": []}}))
        res = self.judge()
        self.assertTrue(res["放行"])
        self.assertEqual([n["类"] for n in res["备注"]], ["配图退回"])

    def test_2_验收没过(self):
        wj(self.issue / "logs" / "验收.json", {"没过": ["截图_手机.png：横向滚动 12 像素"]})
        self.assertEqual(self.failed(self.judge()), [2])
        (self.issue / "logs" / "验收.json").rename(self.issue / "logs" / "验收_旧.json")
        self.assertEqual(self.failed(self.judge()), [2])

    def test_3_数据版(self):
        edit_json(self.state, lambda d: d["步骤"]["voice"]["附加"].update({"播客": "没配成"}))
        self.assertIn(3, self.failed(self.judge()))
        make_issue(self.root)       # 复原
        edit_json(self.state, lambda d: d["步骤"]["web2"]["附加"].update({"带视频": False}))
        self.assertEqual(self.failed(self.judge()), [3])

    def test_4_因月上限用备用照常放行(self):
        def f(d):
            d["步骤"]["voice"]["附加"].update({"决定": {"用备用": True, "原因": "本月 Gemini 已记 $7.30，到上限 $8.00 的 91%"},
                                             "播客": "MiMo 备用", "视频旁白": "MiMo 备用", "视频引擎": "mimo"})
        edit_json(self.state, f)
        wj(self.issue / "05_配音" / "视频旁白_v3" / "voice.json", {"engine": "mimo"})
        res = self.judge()
        self.assertTrue(res["放行"], res["给人看"])
        self.assertEqual([n["类"] for n in res["备注"]], ["备用声音"])
        self.assertIn("花费上限", res["备注"][0]["说明"])

    def test_4_出错换备用不放行(self):
        edit_json(self.state, lambda d: d["步骤"]["voice"]["附加"].update({"播客": "MiMo 备用"}))
        res = self.judge()
        self.assertEqual(self.failed(res), [4])
        self.assertIn("出错", res["条件"][3]["说明"])

    def test_4_只看文件也能发现备用(self):
        wj(self.issue / "05_配音" / "视频旁白_v3" / "voice.json", {"engine": "mimo"})
        self.assertEqual(self.failed(self.judge()), [4])

    def test_4_命令行指定备用照常放行(self):
        edit_json(self.state, lambda d: d["步骤"]["voice"]["附加"].update({"决定": {"用备用": True, "原因": "命令行要求用备用"},
                                                                         "播客": "MiMo 备用", "视频旁白": "MiMo 备用"}))
        res = self.judge()
        self.assertTrue(res["放行"])
        self.assertIn("--use-backup", res["备注"][0]["说明"])

    def test_4_查不到原因按出错算(self):
        edit_json(self.state, lambda d: d["步骤"]["voice"].update({"附加": {"播客": "沿用已有", "视频旁白": "沿用已有", "视频引擎": "mimo"}}))
        wj(self.issue / "05_配音" / "视频旁白_v3" / "voice.json", {"engine": "mimo"})
        self.assertEqual(self.failed(self.judge()), [4])

    def test_5_网页用了lenient(self):
        edit_json(self.state, lambda d: d["运行记录"][1].update({"命令": "fd run --date %s --lenient" % GOOD_DAY}))
        self.assertEqual(self.failed(self.judge()), [5])

    def test_5_lenient只在更早的运行里_不算(self):
        edit_json(self.state, lambda d: d["运行记录"][0].update({"命令": "fd run --date %s --lenient" % GOOD_DAY}))
        self.assertTrue(self.judge()["放行"])

    def test_5_软规则放宽只记备注(self):
        edit_json(self.state, lambda d: d["步骤"]["check"].update({"说明": "放宽：改过一次仍只差长短（全稿 [长度] …），照常往下"}))
        res = self.judge()
        self.assertTrue(res["放行"])
        self.assertEqual([n["类"] for n in res["备注"]], ["其他"])
        self.assertNotIn("放宽", res["给人看"])     # “其他”类备注不进给人看的那段话（也不触发邮件）

    def test_6_版别不对(self):
        (self.issue / "00_调度报告.md").write_text("# %s · 周日版（Shirley、Dylan 双人深谈） · 调度报告\n" % GOOD_DAY, encoding="utf-8")
        res = self.judge()
        self.assertEqual(self.failed(res), [6])
        self.assertIn("星期一", res["条件"][5]["说明"])

    def test_6_审片结论的版别对不上(self):
        edit_json(self.issue / "审片结论.json", lambda d: d.update({"版别": "周六深度版"}))
        self.assertEqual(self.failed(self.judge()), [6])

    def test_6_周六周日(self):
        for day in ("2026-11-14", "2026-11-15"):
            iss = make_issue(self.root, day)
            res = gate.judge(iss, self.root / "月度账本", self.root / "无")
            self.assertTrue(res["放行"], (day, res["给人看"]))

    def test_7_视频超长和播客不在区间(self):
        wj(self.issue / "11_视频v3" / "video3_media.json", {"duration": 181.2})
        self.assertEqual(self.failed(self.judge()), [7])
        wj(self.issue / "11_视频v3" / "video3_media.json", {"duration": 100})
        edit_json(self.issue / "05_配音" / "播客_v3" / "qc.json",
                  lambda d: d["整集"]["时长把关"]["配完按实际"].update({"通过": False, "时长分钟": 16.2}))
        self.assertEqual(self.failed(self.judge()), [7])
        wj(self.issue / "05_配音" / "播客_v3" / "qc.json", {"整集": {}})
        self.assertEqual(self.failed(self.judge()), [7])

    def test_8_这一期超预算或这个月超上限(self):
        edit_json(self.issue / "花费.json", lambda d: d["合计美元"].update({"Gemini": 0.61}))
        self.assertEqual(self.failed(self.judge()), [8])
        edit_json(self.state, lambda d: d["运行记录"][1].update({"命令": "fd run --date %s --budget-usd 0.8" % GOOD_DAY}))
        self.assertTrue(self.judge()["放行"])
        wj(self.root / "月度账本" / "2026-11.json", {"上限美元（Gemini 配音）": 8.0, "条目": [{"服务": "Gemini", "美元": 8.2}]})
        self.assertEqual(self.failed(self.judge()), [8])

    def test_8_没有月度账本(self):
        (self.root / "月度账本" / "2026-11.json").rename(self.root / "月度账本" / "旧.json")
        self.assertEqual(self.failed(self.judge()), [8])

    def test_9_缺审片结论不放行(self):
        (self.issue / "审片结论.json").rename(self.issue / "审片结论_旧.json")
        res = self.judge()
        self.assertEqual(self.failed(res), [9])
        self.assertFalse(res["放行"])
        self.assertEqual(gate.main(["--issue", str(self.issue), "--ledger-dir", str(self.root / "月度账本")]), 1)

    def test_9_审片说不放行或有立即(self):
        edit_json(self.issue / "审片结论.json", lambda d: d.update({"放行": False}))
        self.assertEqual(self.failed(self.judge()), [9])
        edit_json(self.issue / "审片结论.json", lambda d: d.update({"放行": True, "立即": [{"编号": "3", "说明": "版别不对"}]}))
        res = self.judge()
        self.assertEqual(self.failed(res), [9])
        self.assertIn("版别不对", res["给人看"])
        (self.issue / "审片结论.json").write_text("{坏的", encoding="utf-8")
        self.assertEqual(self.failed(self.judge()), [9])

    def test_9_请你耳听不挡放行但记备注(self):
        edit_json(self.issue / "审片结论.json", lambda d: d.update({"请你耳听": [{"位置": "播客 6:10", "说明": "“亿”可能念成“一”"}]}))
        res = self.judge()
        self.assertTrue(res["放行"])
        self.assertEqual(res["备注"], [{"类": "请你耳听", "说明": "播客 6:10：“亿”可能念成“一”"}])
        self.assertIn("播客 6:10", res["给人看"])

    def test_9_请你耳听带判断_原样记进备注_给人看只列真念错(self):
        edit_json(self.issue / "审片结论.json", lambda d: d.update({"请你耳听": [
            {"位置": "播客 3:02", "说明": "5.5 转写成 5.2", "判断": "多半真念错", "依据": "两次转写一样"},
            {"位置": "播客 10:52", "说明": "7A3000 转写成 7A300", "判断": " 多半转写听错 ", "依据": "程序那次对上了"},
            {"位置": "播客 7:37", "说明": "多出点赞订阅", "判断": "多半转写听错", "依据": "常见幻觉句"}]}))
        res = self.judge()
        self.assertTrue(res["放行"])                      # 判断不管放不放行
        self.assertEqual(res["备注"][0], {"类": "请你耳听", "说明": "播客 3:02：5.5 转写成 5.2", "判断": "多半真念错", "依据": "两次转写一样"})
        self.assertEqual(res["备注"][1]["判断"], "多半转写听错")       # 首尾空白去掉
        self.assertIn("有 3 处请你耳听（多半真念错 1 处、多半转写听错 2 处）", res["条件"][8]["说明"])
        self.assertIn("播客 3:02", res["给人看"])
        self.assertNotIn("7A3000", res["给人看"])
        self.assertIn("另有 2 处请你耳听多半是转写听错", res["给人看"])

    def test_9_只有转写听错_给人看没有备注那行(self):
        edit_json(self.issue / "审片结论.json", lambda d: d.update({"请你耳听": [
            {"位置": "播客 7:37", "说明": "多出点赞订阅", "判断": "多半转写听错", "依据": "常见幻觉句"}]}))
        res = self.judge()
        self.assertTrue(res["放行"])
        self.assertNotIn("备注：", res["给人看"])
        self.assertIn("另有 1 处请你耳听多半是转写听错", res["给人看"])

    def test_请你耳听分拣_旧格式和认不出的都当真念错(self):
        self.assertEqual(gate.listen_kind({"位置": "x", "说明": "y"}), gate.LISTEN_REAL)                  # 旧格式没写
        self.assertEqual(gate.listen_kind({"判断": "较可能念错"}), gate.LISTEN_REAL)                       # 写的认不出
        self.assertEqual(gate.listen_kind({"判断": "多半转写听错（指标）"}), gate.LISTEN_REAL)             # 多了字也认不出
        self.assertEqual(gate.listen_kind({"判断": ""}), gate.LISTEN_REAL)
        self.assertEqual(gate.listen_kind({"判断": ["多半转写听错"]}), gate.LISTEN_REAL)
        self.assertEqual(gate.listen_kind("播客 6:10 亿念成一"), gate.LISTEN_REAL)                         # 不是字典
        self.assertEqual(gate.listen_kind({"判断": "多半转写听错"}), gate.LISTEN_ASR)
        self.assertEqual(gate.listen_kind({"判断": "多半转写听错\n"}), gate.LISTEN_ASR)
        self.assertFalse(gate.listen_classified({"说明": "y"}))
        self.assertFalse(gate.listen_classified({"判断": "较可能念错"}))
        self.assertTrue(gate.listen_classified({"判断": "多半真念错"}))

    def test_请你耳听分拣_拿不准和语速(self):
        self.assertEqual(gate.listen_kind({"判断": "拿不准"}), gate.LISTEN_UNSURE)
        self.assertEqual(gate.listen_kind({"判断": "多半真念错", "说明": "（语速指标）5.14 字／秒"}), gate.LISTEN_UNSURE)
        self.assertEqual(gate.listen_kind({"类": "请你耳听", "说明": "视频 4–17 秒：（语速指标）慢约 14%"}), gate.LISTEN_UNSURE)
        self.assertEqual(gate.listen_kind({"判断": "多半转写听错", "说明": "语速"}), gate.LISTEN_ASR)
        self.assertTrue(gate.listen_classified({"判断": "拿不准"}))
        tell, quiet = gate.split_notes([{"类": "请你耳听", "说明": "a", "判断": "拿不准"}, {"类": "请你耳听", "说明": "b", "判断": "多半真念错"}])
        self.assertEqual([n["说明"] for n in tell], ["b"])
        self.assertEqual(gate.quiet_text(quiet), "1 处拿不准（英文名、英文词、语速）")

    def test_关乎事实_原样带进备注(self):
        n = gate.listen_note({"位置": "播客 4:48", "说明": "x", "判断": "多半真念错", "依据": "y", "关乎事实": True})
        self.assertIs(n["关乎事实"], True)
        self.assertNotIn("关乎事实", gate.listen_note({"位置": "p", "说明": "x", "关乎事实": "是"}))
        self.assertTrue(gate.listen_fact({"依据": "两次转写一样，版本号 3.8 成了 3.0"}))
        self.assertFalse(gate.listen_fact({"依据": "版本号", "关乎事实": False}))

    def test_split_notes_各类备注怎么分(self):
        notes = [{"类": "配图退回", "说明": "a"}, {"类": "其他", "说明": "放宽"}, {"类": "请你耳听", "说明": "旧"},
                 {"类": "请你耳听", "说明": "真", "判断": "多半真念错"}, {"类": "请你耳听", "说明": "转", "判断": "多半转写听错"},
                 {"类": "备用声音", "说明": "b"}, {"类": "请你耳听", "说明": "错字", "判断": "转写听错"}, "坏的", {}]
        tell, asr = gate.split_notes(notes)
        self.assertEqual([n["说明"] for n in tell], ["a", "旧", "真", "b", "错字"])
        self.assertEqual([n["说明"] for n in asr], ["转"])
        self.assertEqual(gate.split_notes(None), ([], []))

    def test_9_请你耳听是字符串的旧写法也照记(self):
        edit_json(self.issue / "审片结论.json", lambda d: d.update({"请你耳听": ["播客 6:10 亿可能念成一"]}))
        res = self.judge()
        self.assertEqual(res["备注"], [{"类": "请你耳听", "说明": "播客 6:10 亿可能念成一"}])
        self.assertIn("播客 6:10", res["给人看"])

    def test_9_审片结论比成品旧(self):
        old = time.time() - 3600
        os.utime(self.issue / "审片结论.json", (old, old))
        self.assertEqual(self.failed(self.judge()), [9])

    def test_人工放行(self):
        (self.issue / "审片结论.json").rename(self.issue / "审片结论_旧.json")
        res = self.judge(manual="用户在 GitHub 网页上手动放行")
        self.assertTrue(res["放行"])
        self.assertFalse(res["按条件放行"])
        self.assertEqual(res["没过"], [9])
        self.assertIn("人工放行", res["给人看"])

    def test_出刊了没有(self):
        self.assertEqual(gate.made(self.issue)[0], True)
        self.assertEqual(gate.main(["--issue", str(self.issue), "--check-made"]), 0)
        edit_json(self.state, lambda d: d["运行记录"][-1].update({"结果": "停在第 4 步：等你在会话里选题"}))
        self.assertFalse(gate.made(self.issue)[0])
        self.assertEqual(gate.main(["--issue", str(self.issue), "--check-made"]), 1)
        edit_json(self.state, lambda d: (d["运行记录"][-1].update({"结果": "跑完"}), d["步骤"]["report"].update({"状态": "没做"})))
        self.assertIn("只跑到一半", gate.made(self.issue)[1])
        self.assertFalse((self.issue / "放行结论.json").exists())     # 只看不写

    def test_没有期目录(self):
        self.assertEqual(gate.main(["--issue", str(self.root / "2026-11-30")]), 2)

    def test_什么都没有也不会崩(self):
        empty = self.root / "2026-11-20"
        empty.mkdir()
        res = gate.judge(empty, self.root / "月度账本", self.root / "无")
        self.assertFalse(res["放行"])
        self.assertEqual(len(res["条件"]), 9)


if __name__ == "__main__":
    unittest.main()
