#!/usr/bin/env python3
"""fd 各步失败时"说明"里写哪几行（pipeline/orchestrator/common.py 的 key_lines）的测试（2026-11-14 加）。

来历：11-13（公开仓库测试期）第 14 步视频真正的原因是组装程序报"旁白里找不到这些触发词：close.map（接下来看）"，
可是 00_调度报告.md、fd status、自检.md 写的都是它前面三行"提醒：读音表里还没有：…"，把真原因埋掉了。

查：
  · 用 11-13 第 14 步日志的真实末尾：取到的是"找不到触发词"那行，不带"提醒："行；第 14 步失败的说明也一样；
  · 只有提醒行时退回老办法（提醒行照样列出来，不会变成空的）；
  · 普通失败（✗、Traceback、xxxError）照旧取到报错行；成功、没有要紧行时是空的；
  · "注意：""⚠"开头的也算只提醒；报错行和提醒行混在一起时只列报错行，取最后 n 行。
用法（在项目根运行）：~/.venvs/frontier-daily/bin/python -m unittest pipeline/test_fd_key_lines.py
不调用任何模型、不花钱；不读写文件（第 14 步那一项只在临时目录）。
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))
from orchestrator import common, steps  # noqa: E402
from orchestrator.common import key_lines  # noqa: E402

# 11-13 第 14 步日志 logs/14_视频_20261112-160459.log 里 video3_build.py 那一段的输出（逐字照抄；略去 fd 自己写的 $、# 开始/结束 行和中间 4 行章节时间）
OUT_1113 = """\
  提醒：「open」headline_open/glance 找不到配图 e003，这一块不带图
  提醒：「open」headline_open/glance 找不到配图 e009，这一块不带图
  提醒：「open」headline_open/glance 找不到配图 e052，这一块不带图
  提醒：「decide」compare_panel/price 找不到配图 e003（photo），这一块照原样、不压在图上
  提醒：「search」compare_panel/users 找不到配图 e009（photo），这一块照原样、不压在图上
  提醒：「film」quote_card/film_total 找不到配图 e052，这一块不带图
  提醒：「film」没有配图也没有标志小签：画面只有字卡（每章至少要一层真东西）
分镜：6 章（open、genome、decide、search、film、close），9 个模板，13 条事实、79 处字已核对
旁白检查（pipeline/prompts/写稿_视频v3.md）：6 章、424 个汉字
  提醒：读音表里还没有：DeepMind
  提醒：读音表里还没有：DNA
  提醒：读音表里还没有：AlphaGenome
  提醒：读音表里还没有：Decision
  提醒：读音表里还没有：CloudRobo-WM1.2
时长：按字数估约 127 秒（上限 180 秒）
  混音（避让，底乐 bed_dreamer.flac）：-16.0 LUFS、真峰值 -3.6 dBTP；音乐说话时比人声低 -22.2 dB，章间空隙里 -12.2 dB
排好 05_配音/视频旁白_v3/video3.mp3：129.6 秒（人声 106.2 秒）
  open      说到  13.68，分界小节线  15.90（等 2.22 秒），下一章  16.50 开口
  片尾从 Lyria 第 17 拍起；收束拍在 126.30 秒（最后一个字 123.75 秒）
时长：配完音实际 130 秒（上限 180 秒）
旁白里找不到这些触发词：close.map（接下来看）
"""
REAL = "旁白里找不到这些触发词：close.map（接下来看）"


class KeyLines(unittest.TestCase):
    def test_1113_video_tail(self):
        got = key_lines(OUT_1113, 3)
        self.assertEqual(got, [REAL])
        self.assertFalse(any(x.startswith("提醒") for x in got), got)

    def test_notices_only_fall_back(self):
        out = "分镜：6 章\n  提醒：读音表里还没有：DNA\n  提醒：读音表里还没有：Decision\n注意：没有找到播客\n时长：127 秒\n"
        self.assertEqual(key_lines(out, 3), ["提醒：读音表里还没有：DNA", "提醒：读音表里还没有：Decision", "注意：没有找到播客"])
        self.assertEqual(key_lines(out, 2), ["提醒：读音表里还没有：Decision", "注意：没有找到播客"])

    def test_plain_failures(self):
        tb = ("开始组装\nTraceback (most recent call last):\n  File \"build_v3.py\", line 10, in <module>\n"
              "    main()\nKeyError: 'chapters'\n")
        self.assertEqual(key_lines(tb, 3), ["Traceback (most recent call last):", "KeyError: 'chapters'"])
        self.assertEqual(key_lines("抓到 0 条\n✗ 超时（240 秒），已停掉\n", 3), ["✗ 超时（240 秒），已停掉"])
        mixed = "  提醒：读音表里还没有：DNA\n✗ 数字核不上：e003 的 41%\n  ⚠ 首屏 2.3 MB\n错误：网页配置不在\n  提醒：Decision\n"
        self.assertEqual(key_lines(mixed, 3), ["✗ 数字核不上：e003 的 41%", "错误：网页配置不在"])
        self.assertEqual(key_lines(mixed, 1), ["错误：网页配置不在"])

    def test_success_or_nothing(self):
        self.assertEqual(key_lines("网页组装好了\n共 12 页\n", 3), [])
        self.assertEqual(key_lines("", 3), [])
        self.assertEqual(key_lines(None, 3), [])


class _Ctx:
    """第 14 步只用到的那几样：期目录、步骤记录、跑程序（组装视频照 11-13 退出码 1）。"""
    def __init__(self, issue):
        self.issue, self.offline, self.preview = Path(issue), True, False
        self.logs = self.issue / "logs"
        self.state = mock.Mock()
        self.state.step.return_value = {"附加": {"视频旁白": "主声音"}}

    def p(self, x):
        return self.issue / x

    def py(self, *a):
        return ["py"] + [str(x) for x in a]

    def run(self, step, cmd, label="", timeout=None, env=None):
        return (1, OUT_1113) if label == "组装视频" else (0, "")


class VideoFailMsg(unittest.TestCase):
    def test_step14_msg_names_real_cause(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(steps.Video, "shots", lambda self, c: ("", [], {})):
            r = steps.Video().run(_Ctx(d), "run")
        self.assertEqual(r.status, common.FAILED)
        self.assertEqual(r.msg, "视频没组装成，这一期网页不放视频：" + REAL)
        self.assertNotIn("读音表", r.msg)


if __name__ == "__main__":
    unittest.main()
