#!/usr/bin/env python3
"""视频配图卡收起前一张截图卡（2026-11-21 尝试版；环境变量 FD_VIDEO_IMAGE_TAKE，播放器 site/v3/video3.js 的 TAKE）的测试。

11-16 审片第 56 项：英伟达章 CNBC 截图停了约 12 秒（118.8–131 秒），导演安排 127.0 秒说到"董事会"时回到会议室图，成片没换；
DeepSeek 章 68.8 秒该回到机房图，IT之家截图仍盖满画面。原因：配图卡（image_card）不算章里的一块，截图卡的"下一块开始"是空的，
就一直留到章末；配图要么挂在截图卡右后方（被挡住），要么立在分岔路尽头（镜头不在那里）。

查三件事：
  1. 开关：只认环境变量 FD_VIDEO_IMAGE_TAKE 写 on／1／开……，没设或别的值都是关；组装数据只在开着、而且 fix1108 也写了时多写 imgtake。
  2. 播放器：新画法全在 TAKE 后面（TAKE = FX && imgtake），没有 imgtake 的数据走原来的路；takeOver 只在 TAKE 开着时调；
     用 node 把 takeOver 那几个小函数单独跑一遍，11-16 两处都接手、时刻对，不该接手的（截图卡刚开讲、分岔路上的卡、
     章里有 over_photo 要点卡、不是截图卡）都不接手。
  3. 逐帧（只在有 11-16 成品副本时，设 FD_IMGTAKE_ISSUE 指向那一期的 11_视频v3 目录）：不在这里跑，结果写在维护报告里。

用法（在项目根运行）：
    PYTHONDONTWRITEBYTECODE=1 ~/.venvs/frontier-daily/bin/python site/tools/test_video3_imgtake.py
不调用任何模型、不联网、不写项目文件；没有 node 就跳过第 2 件的后半。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]
JS = ROOT / "site" / "v3" / "video3.js"
BUILD = TOOLS / "video3_build.py"


class Switch(unittest.TestCase):
    def on(self, v):
        src = BUILD.read_text(encoding="utf-8")
        fn = re.search(r"\ndef image_take_on\(\):\n.*?\n\n", src, re.S).group(0)
        ns = {"os": os, "IMAGE_TAKE_ENV": "FD_VIDEO_IMAGE_TAKE"}
        exec(fn, ns)                      # 只取这一个函数（整份组装程序要载很多东西）
        with mock.patch.dict(os.environ, {"FD_VIDEO_IMAGE_TAKE": v}):
            return ns["image_take_on"]()

    def test_env(self):
        for v in ("on", "1", "开", "TRUE"):
            self.assertTrue(self.on(v), v)
        for v in ("", "off", "0", "关", "maybe"):
            self.assertFalse(self.on(v), v)

    def test_build_writes_key_only_when_on(self):
        src = BUILD.read_text(encoding="utf-8")
        i = src.index('data["fix1108"] = True')
        block = src[i:src.index("\n    # ", i)]
        self.assertIn("if image_take_on():", block)          # 挂在 fix 那一段里：fix1108 没写，imgtake 也不写
        self.assertIn('data["imgtake"] = True', block)
        self.assertEqual(src.count('data["imgtake"]'), 1)


class Player(unittest.TestCase):
    def setUp(self):
        self.js = JS.read_text(encoding="utf-8")

    def test_gated(self):
        js = self.js
        self.assertIn("var TAKE = false;", js)
        self.assertIn("TAKE = FX && !!this.v.imgtake;", js)
        self.assertEqual(js.count("takeOver("), 2)                  # 定义一处、调用一处
        self.assertEqual(js.count("if (TAKE) takeOver(b, real);"), 1)
        self.assertIn("if (TAKE) real.forEach(function (b) { if (b._.takeT != null)", js)
        # 'take' 这个模式只有 takeOver 会写；image_card.build 认到它才走新画法
        self.assertEqual(js.count("o.mode = 'take'"), 1)
        self.assertEqual(js.count("b._.mode === 'take'"), 1)

    def node(self, src):
        node = shutil.which("node")
        if not node:
            self.skipTest("没有 node")
        return json.loads(subprocess.run([node, "-e", src], capture_output=True, text=True, check=True).stdout)

    def run_take(self, chapters):
        """把 bt、firstT、startT、shotCard、takeOver 这几个函数从播放器里原样取出来，在 node 里对假数据跑。"""
        js = self.js
        fns = []
        for name in ("bt", "firstT", "startT", "shotCard", "takeOver"):
            m = re.search(r"\n  function %s\(.*?\n(?=  function |  //|  /\*|  var |  TPL)" % name, js, re.S)
            self.assertIsNotNone(m, name)
            fns.append(m.group(0))
        prog = ("var clamp=function(v,a,b){return Math.min(b,Math.max(a,v));};var TPL={source_shot:{},quote_card:{},post_card:{},tile_row:{},fork:{},image_card:{},"
                "compare_panel:{startT:function(b){return bt(b,'show',firstT(b));}}};" + "".join(fns) +
                "var out=[];var CH=%s;CH.forEach(function(c){var real=c.real.map(function(b){b._={rel:[1,0,0]};return b;});"
                "for(var i=0;i<real.length-1;i++)real[i]._.next=real[i+1];(c.fork||[]).forEach(function(k){real[k]._.fork=true;});"
                "c.images.forEach(function(b){b._={mode:b.mode||'backdrop'};takeOver(b,real);"
                "out.push({id:b.id,mode:b._.mode,host:b._.host?b._.host.id:null,takeT:b._.host?b._.host._.takeT:null,hideAt:b._.hideAt===undefined?null:b._.hideAt});});});"
                "console.log(JSON.stringify(out));") % json.dumps(chapters, ensure_ascii=False)
        return self.node(prog)

    def test_take_rules(self):
        noann = {"type": "source_shot", "id": "noann", "t": {"show": 64.175, "mark": 67.716}, "shot": {"lines": [[0.2, 0.4, 0.7, 0.06]]}}
        spokes = {"type": "quote_card", "id": "spokes", "t": {"show": 118.813, "shot_mark": 121.056},
                  "shot": {"lines": [[0.05, 0.1, 0.9, 0.13], [0.03, 0.3, 0.14, 0.13]]}}
        chs = [
            {"real": [{"type": "tile_row", "id": "limits", "t": {"head": 47.985}}, noann],          # 11-16 DeepSeek 章
             "images": [{"type": "image_card", "id": "hall", "t": {"in": 68.786}}]},
            {"real": [{"type": "fork", "id": "two", "t": {"fork": 101.188}}, spokes],             # 11-16 英伟达章（配图本来立在岔路尽头）
             "images": [{"type": "image_card", "id": "board", "mode": "fork", "t": {"in": 126.996}}]},
            {"real": [{"type": "source_shot", "id": "early", "t": {"show": 10.0, "mark": 11.0}}],   # 截图卡刚开讲 1 秒：照旧做背景
             "images": [{"type": "image_card", "id": "bg", "t": {"in": 11.0}}]},
            {"real": [{"type": "quote_card", "id": "plain", "t": {"show": 20.0}}],                 # 不是截图卡
             "images": [{"type": "image_card", "id": "bg2", "t": {"in": 25.0}}]},
            {"real": [{"type": "fork", "id": "f", "t": {"fork": 30.0}}, {"type": "quote_card", "id": "br", "t": {"show": 31.0}, "shot": {}}],
             "fork": [1], "images": [{"type": "image_card", "id": "bg3", "t": {"in": 36.0}}]},       # 站在分岔路上的卡
            {"real": [{"type": "quote_card", "id": "ov", "over_photo": True, "t": {"show": 40.0}},
                      {"type": "source_shot", "id": "s2", "t": {"show": 41.0, "mark": 42.0}}],
             "images": [{"type": "image_card", "id": "fk", "mode": "fork", "t": {"in": 46.0}}]},      # 有要压在配图上的要点卡
            {"real": [{"type": "source_shot", "id": "s3", "t": {"show": 50.0, "mark": 51.0}}, {"type": "compare_panel", "id": "nx", "t": {"show": 60.0}}],
             "images": [{"type": "image_card", "id": "mid", "t": {"in": 55.0}}]},                    # 后面还有一块：配图到下一块前 0.3 秒收
        ]
        got = {r["id"]: r for r in self.run_take(chs)}
        self.assertEqual((got["hall"]["mode"], got["hall"]["host"]), ("take", "noann"))
        self.assertAlmostEqual(got["hall"]["takeT"], 67.716 + 1.22 + 0.3, places=3)   # 一行：扫 1.22 秒，扫完再过 0.3 秒（晚于触发词 68.786）
        self.assertIsNone(got["hall"]["hideAt"])
        self.assertEqual((got["board"]["mode"], got["board"]["host"]), ("take", "spokes"))
        self.assertAlmostEqual(got["board"]["takeT"], 126.996, places=3)               # 早就扫完了：按触发词
        self.assertEqual(got["bg"]["mode"], "backdrop")
        self.assertEqual(got["bg2"]["mode"], "backdrop")
        self.assertEqual(got["bg3"]["mode"], "backdrop")
        self.assertEqual(got["fk"]["mode"], "fork")
        self.assertEqual((got["mid"]["mode"], got["mid"]["host"]), ("take", "s3"))
        self.assertAlmostEqual(got["mid"]["hideAt"], 59.7, places=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
