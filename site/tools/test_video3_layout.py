#!/usr/bin/env python3
"""画面防叠压、画面叠压检查（2026-11-22 加；fd_开关.json"画面防叠压""画面叠压检查"，都默认关）的测试。

11-22 审片两处：分岔对照（split）同侧两张小卡，前一张带题图时第二张压在第一张的字上（11-12 第 115 秒、11-22 第 113–120 秒）；
压在配图上的对比卡（compare_panel 写了 photo）高度写死，内容放不下，底注挤出卡片下沿、被字幕条盖住（11-22 第 70.5 秒）。

查四件事：
  1. 开关：先看环境变量（FD_LAYOUT_GUARD、FD_LAYOUT_CHECK），没设再看 fd_开关.json，都没有按关；组装程序和 fd 读到同一个值；
     第 14 步指纹只多"=画面防叠压="（关着是空字符串，往期不重做），叠压检查不进指纹；组装数据只在开着时多写 layoutguard。
  2. 播放器：新画法全在 LG 后面（LG = !!this.v.layoutguard）；第 14 步的叠压检查关着时一句话、提醒、附加都是空的；
     自检.md 那一行只在第 14 步记了检查结果时才有。
  3. 浏览器（11-06 演示页复制到临时目录里改数据，本机 Chrome；没有就跳过）：
     · 分岔对照左边"带图＋不带图"两张：关着两张外框相交（证明样稿碰得到），开着不相交、左右对齐；竖屏（400×500）开着也不相交；
     · 压图对比卡内容超高（编的字，长度和 11-22 那张相当）：关着 scrollHeight > clientHeight，开着放下、最后一行在卡片里、
       离下沿至少 8 像素；内容不超高的压图对比卡开着一个收紧的类都不加；
  4. 叠压检查程序 video3_overlap.mjs：关着那份报出"小卡相交""卡片内容超出卡片"，开着那份 0 处。

用法（在项目根运行）：
    PYTHONDONTWRITEBYTECODE=1 ~/.venvs/frontier-daily/bin/python site/tools/test_video3_layout.py
不调用任何模型、不联网、不写项目文件；浏览器那一组要 测试版/2026-11-06/11_视频v3（私有仓库那份拷进来，见 README 第五节），没有就跳过。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]
JS = ROOT / "site" / "v3" / "video3.js"
CSS = ROOT / "site" / "v3" / "video3.css"
BUILD = TOOLS / "video3_build.py"
DEMO = ROOT / "测试版" / "2026-11-06" / "11_视频v3"
PW = os.environ.get("PLAYWRIGHT") or str(Path.home() / ".npm/_npx/9833c18b2d85bc59/node_modules/playwright/index.mjs")
for _p in (TOOLS, ROOT / "pipeline"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import video3_storyboard as SB  # noqa: E402


class Switch(unittest.TestCase):
    def read(self, env_name, key, v, fv):
        """环境变量 env_name 写 v（None＝不设）、开关文件里 key 写 fv（None＝没有这个文件）时，组装程序和 fd 各读到什么。"""
        from orchestrator import common
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "fd_开关.json"
            if fv is not None:
                f.write_text(json.dumps({key: fv}, ensure_ascii=False), encoding="utf-8")
            env = dict(os.environ)
            env.pop(env_name, None)
            if v is not None:
                env[env_name] = v
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(SB, "MOTION_SWITCH_FILE", f), \
                    mock.patch.object(common, "SWITCH_FILE", f):
                if env_name == "FD_LAYOUT_GUARD":
                    return SB.layout_guard_switch()[0], common.layout_guard_switch()[0]
                return common.layout_check_switch()[0], common.layout_check_switch()[0]

    def test_guard_env_file_default(self):
        r = lambda v, fv: self.read("FD_LAYOUT_GUARD", "画面防叠压", v, fv)    # noqa: E731
        for v in ("on", "1", "开"):
            self.assertEqual(r(v, "关"), (True, True), v)       # 环境变量优先
        for v in ("off", "0", "关"):
            self.assertEqual(r(v, "开"), (False, False), v)
        self.assertEqual(r(None, "开"), (True, True))
        self.assertEqual(r(None, "关"), (False, False))
        self.assertEqual(r(None, None), (False, False))         # 没有开关文件：关
        self.assertEqual(r("maybe", "随便"), (False, False))    # 认不出：关
        for v in (None, "", "on", "off", "开", "x"):
            for fv in (None, "开", "关", "on", "x"):
                a, b = r(v, fv)
                self.assertEqual(a, b, (v, fv))                 # 组装程序和 fd 同一个值

    def test_check_env_file_default(self):
        r = lambda v, fv: self.read("FD_LAYOUT_CHECK", "画面叠压检查", v, fv)[0]  # noqa: E731
        self.assertTrue(r("on", "关"))
        self.assertFalse(r("off", "开"))
        self.assertTrue(r(None, "开"))
        self.assertFalse(r(None, None))
        self.assertFalse(r(None, "随便"))

    def test_repo_switch_file_has_both(self):
        sw = json.loads((ROOT / "fd_开关.json").read_text(encoding="utf-8"))
        for k in ("画面防叠压", "画面叠压检查"):
            self.assertIn(sw.get(k), ("开", "关"), k)
            self.assertIn(k + "_是什么", sw)

    def test_build_writes_key_only_when_on(self):
        src = BUILD.read_text(encoding="utf-8")
        self.assertEqual(src.count('data["layoutguard"]'), 1)
        i = src.index('data["layoutguard"] = True')
        self.assertIn("if gon:", src[i - 200:i])
        self.assertIn("gon, gwhy = SB.layout_guard_switch()", src[i - 300:i])

    def test_fingerprint(self):
        from orchestrator import runner, steps
        src = (ROOT / "pipeline" / "orchestrator" / "steps.py").read_text(encoding="utf-8")
        self.assertIn('"=画面防叠压=" + ("开" if layout_guard_switch()[0] else "")', src)
        self.assertNotIn("=画面叠压检查=", src)                  # 检查只量、不改成片：不进指纹
        old = {"=配图收截图卡=": ""}
        self.assertEqual(runner.diff_inputs(old, {"=配图收截图卡=": "", "=画面防叠压=": ""}), [])
        self.assertEqual(runner.diff_inputs(old, {"=配图收截图卡=": "", "=画面防叠压=": "开"}), ["=画面防叠压="])
        self.assertTrue(hasattr(steps, "layout_guard_switch") and hasattr(steps, "layout_check_switch"))


class OffChangesNothing(unittest.TestCase):
    def test_player_gated(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("var LG = false,", js)
        self.assertIn("LG = !!this.v.layoutguard;", js)
        self.assertEqual(js.count("lgFit(ch)"), 2)                                  # refLabels 一处、lgRefit 里一处（lgFit(lb.inEl…) 另算）
        self.assertIn("if (LG && lb.lgFit) lgFit(ch);", js)
        self.assertIn("if (LG) { li = lgTiles(li); ri = lgTiles(ri); }", js)
        self.assertIn("var zL = LG ? lgZ(li, gapL) : null, zR = LG ? lgZ(ri, gapR) : null;", js)
        self.assertIn("if (LG && this.lgCols)", js)                          # 到位以后按画面像素再挪（离位置越近挪得越足）
        self.assertIn("var near = 1 - sat(kq.at.distanceTo(kq.lgTo) / 4); if (!near) continue;", js)   # 飞进来、飞回去的半路不挪
        self.assertIn("if (LG && ovp) b._.o.lb.lgFit = true;", js)
        self.assertIn("if (LG && document.fonts)", js)
        css = CSS.read_text(encoding="utf-8")
        for k in ("lgt1", "lgt2", "lgt3", "lgt4"):
            self.assertTrue(all(".v3card.v3cp.ovp." in line for line in css.splitlines() if k in line and "{" in line), k)

    def test_step14_overlap_off(self):
        from orchestrator import steps
        with mock.patch.object(steps, "layout_check_switch", return_value=(False, "测试")):
            self.assertEqual(steps.Video().overlap(object()), ("", [], {}))

    def test_step14_overlap_on(self):
        """开着：跑 video3_overlap.mjs（这里换成假的），读它写的 JSON，提醒一行（只有处数、种类、时刻，不带卡片上的字），附加记处数。"""
        from orchestrator import steps
        with tempfile.TemporaryDirectory() as td:
            issue = Path(td)

            class Ctx:
                issue = Path(td)

                def p(self, rel):
                    return issue / rel

                def log_path(self, step):
                    return issue / "logs" / "14.log"

                def run(self, step, cmd, label, timeout=None):
                    self.cmd = [str(x) for x in cmd]
                    j = issue / "logs" / "视频_叠压检查.json"
                    j.parent.mkdir(parents=True, exist_ok=True)
                    j.write_text(json.dumps({"处数": 1, "各类": {"小卡相交": 1}, "各处": [
                        {"种类": "小卡相交", "从": 112.25, "到": 120.75, "卡片": "卡片上的字"}]}, ensure_ascii=False), encoding="utf-8")
                    return 0, "画面叠压检查：1 处"
            c = Ctx()
            with mock.patch.object(steps, "layout_check_switch", return_value=(True, "测试")):
                msg, warns, extra = steps.Video().overlap(c)
            self.assertIn("video3_overlap.mjs", " ".join(c.cmd))
            self.assertEqual(msg, "画面叠压检查：1 处")
            self.assertEqual(len(warns), 1)
            self.assertIn("112.25–120.75 秒", warns[0])
            self.assertNotIn("卡片上的字", warns[0])
            self.assertEqual(extra["画面叠压检查"]["处数"], 1)

            class Bad(Ctx):
                def run(self, step, cmd, label, timeout=None):
                    return 1, "画面叠压检查没量成：页面没起来"
            with mock.patch.object(steps, "layout_check_switch", return_value=(True, "测试")):
                (issue / "logs" / "视频_叠压检查.json").rename(issue / "旧.json")
                msg, warns, extra = steps.Video().overlap(Bad())
            self.assertEqual(msg, "")
            self.assertIn("没跑成", warns[0])                     # 只提醒，不抛错、不挡
            self.assertEqual(extra["画面叠压检查"]["结果"], "没跑成")

    def test_selfcheck_line(self):
        from orchestrator import selfcheck as SC
        self.assertEqual(SC.overlap_line({}), "")
        self.assertEqual(SC.overlap_line({"视频导演": "不做（测试）"}), "")
        self.assertIn("0 处", SC.overlap_line({"画面叠压检查": {"结果": "跑了", "处数": 0}}))
        s = SC.overlap_line({"画面叠压检查": {"结果": "跑了", "处数": 2, "各类": {"小卡相交": 1, "卡片内容超出卡片": 1},
                                           "文件": "logs/视频_叠压检查.json"}})
        self.assertIn("2 处", s)
        self.assertIn("小卡相交 1", s)
        self.assertIn("logs/视频_叠压检查.json", s)
        self.assertIn("没跑成", SC.overlap_line({"画面叠压检查": {"结果": "没跑成"}}))


def can_browse():
    return shutil.which("node") and Path(PW).exists() and Path("/Applications/Google Chrome.app").exists()


PROBE = r"""
import path from 'path'; import { pathToFileURL } from 'url';
const { chromium } = await import(pathToFileURL(process.env.PW).href);
const [page, t0, W, H] = process.argv.slice(2); const t = +t0;
const b = await chromium.launch({ channel: 'chrome', headless: true });
const p = await (await b.newContext({ viewport: { width: +W, height: +H }, deviceScaleFactor: 1 })).newPage();
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(pathToFileURL(page).href + '?rec=1&eager=1&theme=light');
await p.waitForFunction(() => window.__v3 && window.__v3.world, null, { timeout: 30000 });
await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(600);
await p.evaluate(t => { window.__v3.renderAt(t - 0.04); window.__v3.renderAt(t); }, t); await p.waitForTimeout(150); await p.evaluate(t => window.__v3.renderAt(t), t);
const r = await p.evaluate(() => {
  const R = e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
  const vis = e => getComputedStyle(e.closest('.v3l')).visibility === 'visible';
  const tiles = [...document.querySelectorAll('.v3tile')].filter(vis).map(e => ({ r: R(e), t: e.textContent.replace(/\u200b/g, '') }));
  const cards = [...document.querySelectorAll('.v3card.v3cp.ovp')].filter(vis).map(c => ({ r: R(c), cls: c.className, scroll: c.scrollHeight, client: c.clientHeight,
    last: R(c.lastElementChild), first: R(c.firstElementChild) }));
  return { tiles, cards };
});
r.errs = errs; console.log(JSON.stringify(r)); await b.close();
"""


@unittest.skipUnless(can_browse(), "没有 node / Playwright / Chrome")
class Browser(unittest.TestCase):
    """11-06 演示页复制到临时目录、换上本仓库的播放器，改数据（时刻是手写的），本机 Chrome 渲染几个时刻量外框。"""

    @classmethod
    def setUpClass(cls):
        if not (DEMO / "data.js").exists():
            raise unittest.SkipTest("没有 11-06 的演示页（测试版/2026-11-06/11_视频v3）")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.probe = Path(cls.tmp.name) / "probe.mjs"
        cls.probe.write_text(PROBE, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def page(self, name, lg, edit):
        out = Path(self.tmp.name) / name / "11_视频v3"
        shutil.copytree(DEMO, out)
        for f in ("video3.js", "video3.css"):
            shutil.copy2(ROOT / "site" / "v3" / f, out / f)
        s = (out / "data.js").read_text(encoding="utf-8")
        data = json.loads(re.search(r"window\.FD_VIDEO3 = (\{.*\});\s*$", s, re.S).group(1))
        data["fix1108"] = True                    # 线上那条路（新动效、导演开关都开着）
        if lg:
            data["layoutguard"] = True
        edit({c["id"]: c for c in data["chapters"]})
        (out / "data.js").write_text("window.FD_VIDEO3 = %s;\n" % json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return out

    def measure(self, out, t, w=1280, h=720):
        res = subprocess.run(["node", str(self.probe), str(out / "index.html"), str(t), str(w), str(h)], capture_output=True, text=True,
                             env=dict(os.environ, PW=PW), timeout=180)
        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
        r = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertEqual(r["errs"], [])
        return r

    @staticmethod
    def cut(a, b):
        return min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])

    # ---- 分岔对照：左边"带图＋不带图"两张（11-06 演示页左边原来一张带图，加一张编的字）
    @staticmethod
    def two_tiles(ch):
        b = next(x for x in ch["contrast"]["blocks"] if x["type"] == "split")
        b["left_items"].append({"text": {"zh": "第二张小卡写一句别的说法", "en": "Another view"}, "sub": {"zh": "某位分析师 · 据某媒体"}})
        b["t"]["left_items1"] = 106.5

    def left_two(self, r):
        ts = [x for x in r["tiles"] if "Ripple" in x["t"] or "第二张" in x["t"]]
        self.assertEqual(len(ts), 2, r["tiles"])
        return ts

    def test_split_image_then_text(self):
        off = self.left_two(self.measure(self.page("split_off", False, self.two_tiles), 110))
        w, h = self.cut(off[0]["r"], off[1]["r"])
        self.assertTrue(w > 4 and h > 4, off)                   # 关着：第二张压在第一张上（样稿碰得到这个毛病）
        on = self.left_two(self.measure(self.page("split_on", True, self.two_tiles), 110))
        w, h = self.cut(on[0]["r"], on[1]["r"])
        self.assertFalse(w > 0 and h > 0, on)                   # 开着：外框不相交
        self.assertGreaterEqual(on[1]["r"][1] - on[0]["r"][3], 10, on)          # 第二张在第一张下面，至少隔 10 像素
        c0, c1 = (on[0]["r"][0] + on[0]["r"][2]) / 2, (on[1]["r"][0] + on[1]["r"][2]) / 2
        self.assertLess(abs(c0 - c1), 4, on)                    # 左右对齐（透视下不再偏外）
        self.assertLess(on[1]["r"][3], 720 * 0.86, on)          # 不进字幕带
        por = self.left_two(self.measure(Path(self.tmp.name) / "split_on" / "11_视频v3", 110, 400, 500))
        w, h = self.cut(por[0]["r"], por[1]["r"])
        self.assertFalse(w > 0 and h > 0, por)                  # 竖屏（4:5）开着也不相交

    # ---- 压在配图上的对比卡：内容超高（编的字，长度和 11-22 那张相当）
    @staticmethod
    def tall_panel(ch):
        pb = ch["permit"]["blocks"]
        k = next(k for k, b in enumerate(pb) if b["id"] == "scope")
        pb[k] = {"type": "compare_panel", "id": "scope", "photo_img": "matin", "src_tag": {"zh": "某研究所"}, "head": {"zh": "收盘估值，两种口径"},
                 "sub": {"zh": "据某研究所（某网站转载）"}, "kpi": {"value": "约 2.4 万亿美元", "text": {"zh": "按流通股本计算"}}, "t": {"show": 79.3},
                 "bars": [{"label": {"zh": "全面摊薄口径"}, "value": 1.0, "val": {"zh": "约 3.15 万亿"}},
                          {"label": {"zh": "流通股本口径"}, "value": 0.76, "me": True, "val": {"zh": "约 2.4 万亿"}}],
                 "foot": {"zh": "同一交易日，两种算法"}}

    @staticmethod
    def short_panel(ch):
        pb = ch["permit"]["blocks"]
        k = next(k for k, b in enumerate(pb) if b["id"] == "scope")
        pb[k] = {"type": "compare_panel", "id": "scope", "photo_img": "matin", "src_tag": {"zh": "某研究所"}, "head": {"zh": "目标带宽"},
                 "kpi": {"value": "约 3 倍", "text": {"zh": "于上一代（目标）"}}, "t": {"show": 79.3},
                 "bars": [{"label": {"zh": "上一代"}, "value": 0.333, "val": {"zh": "1"}}, {"label": {"zh": "新一代"}, "value": 1.0, "me": True, "val": {"zh": "约 3"}}],
                 "foot": {"zh": "两家公司各自的说法"}}

    def test_compare_panel_tall(self):
        off = self.measure(self.page("panel_off", False, self.tall_panel), 84)["cards"]
        self.assertEqual(len(off), 1, off)
        self.assertGreater(off[0]["scroll"], off[0]["client"] + 1, off)      # 关着：放不下（样稿碰得到这个毛病）
        self.assertNotIn("lgt", off[0]["cls"])
        on = self.measure(self.page("panel_on", True, self.tall_panel), 84)["cards"]
        self.assertEqual(len(on), 1, on)
        c = on[0]
        self.assertIn("lgt1", c["cls"])
        self.assertLessEqual(c["scroll"], c["client"] + 1, c)                # 开着：放下了
        self.assertLessEqual(c["last"][3], c["r"][3] - 8, c)                 # 最后一行（底注）在卡片里，离下沿至少 8 像素
        self.assertGreaterEqual(c["first"][1], c["r"][1], c)                 # 出处签不顶出上沿

    def test_compare_panel_short_untouched(self):
        on = self.measure(self.page("short_on", True, self.short_panel), 84)["cards"]
        self.assertEqual(len(on), 1, on)
        self.assertNotIn("lgt", on[0]["cls"])                                # 放得下的卡一个收紧的类都不加

    # ---- 叠压检查程序：关着那份报得出，开着那份 0 处
    def test_overlap_checker(self):
        def both(ch):
            self.two_tiles(ch)
            self.tall_panel(ch)
        res = {}
        for lg in (False, True):
            out = self.page("check_%d" % lg, lg, both)
            j = Path(self.tmp.name) / ("check_%d.json" % lg)
            r = subprocess.run(["node", str(TOOLS / "video3_overlap.mjs"), str(out), "--out", str(j)], capture_output=True, text=True,
                               cwd=str(ROOT), env=dict(os.environ, PLAYWRIGHT=PW), timeout=240)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            self.assertIn("画面叠压检查：", r.stdout)
            self.assertEqual(len(r.stdout.strip().splitlines()), 1)          # 终端只印一行
            res[lg] = json.loads(j.read_text(encoding="utf-8"))
        kinds = res[False]["各类"]
        self.assertGreaterEqual(kinds.get("小卡相交", 0), 1, res[False])
        self.assertGreaterEqual(kinds.get("卡片内容超出卡片", 0), 1, res[False])
        self.assertTrue(all(s["到"] - s["从"] >= 1 for s in res[False]["各处"]))
        self.assertNotIn("/", "".join(res[False]["页面"].split("11_视频v3/")))  # 只写相对路径
        self.assertEqual(res[True]["处数"], 0, res[True]["各处"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
