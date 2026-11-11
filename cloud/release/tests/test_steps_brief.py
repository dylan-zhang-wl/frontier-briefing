"""cloud/release/steps_brief.py 的测试（2026-11-11 加）：只印步名和状态，不印"说明"里的字。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import steps_brief as B  # noqa: E402


class BriefTest(unittest.TestCase):
    def test_只印状态不印说明(self):
        with tempfile.TemporaryDirectory() as td:
            issue = Path(td) / "2026-11-20"
            (issue / "logs").mkdir(parents=True)
            st = {"步骤": {"fetch": {"状态": "做完", "说明": "抓到 300 条"}, "select": {"状态": "失败", "说明": "选题：某公司发布新模型"}},
                  "运行记录": [{"开始": "2026-11-20 04:20", "结束": "2026-11-20 06:10", "结果": "停在第 4 步：某公司发布新模型"}]}
            (issue / "logs" / "fd_state.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
            text = "\n".join(B.brief(issue))
        self.assertIn(" 1 抓取：做完", text)
        self.assertIn(" 4 选题：失败", text)
        self.assertIn("17 写本期报告：没做", text)
        self.assertIn("结束 2026-11-20 06:10", text)
        self.assertNotIn("某公司", text)
        self.assertNotIn("300 条", text)

    def test_没有状态文件(self):
        self.assertIn("还没有", B.brief(Path("/不存在/2026-11-20"))[0])


if __name__ == "__main__":
    unittest.main()
