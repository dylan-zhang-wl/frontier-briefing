#!/usr/bin/env python3
"""视频 v3 中文整词换行（2026-11-09 晚加，开关"视频中文整词换行"，说明见 video3_zhwrap.py）的测试。

查三件事：
  1. 开关：环境变量 FD_VIDEO_ZH_WRAP 比 fd_开关.json 优先；没有文件、写坏了、值认不出按"开"；组装程序（video3_zhwrap.switch）
     和 fd（pipeline/orchestrator/common.py 的 zh_wrap_switch）说法一致；第 14 步的输入指纹开着是空字符串（往期不重做）、关着是"关"；
     项目里现在是"开"。
  2. 组装：显示文字只多了换行点（去掉以后和原文一个字一个字对得上）；"稀缺设备"不拆；对照表只是多出来的一个键，
     场景数据里原来的字（触发词、字幕和逐字时间、文字稿、旁白）一个字不动；摘录的截法和 video3.js 的 excerptParts 一样（node 跑同一段 JS 比）。
  3. 播放器（本机 Chrome）：把 video3.js 里整词换行那一段和 renderSub 拿出来，在一页小页面里：
     卡片标题插好换行点，各种宽度下"设备""供应商"都不被拆开（不插时同样的宽度会拆，证明测得到）；滚动数字（先显示 0）也对得上；
     标题的扫光副本和正文的换行点一样；对不上的字原样不动、不加类；
     字幕 <i> 的个数、顺序、逐字高亮的序号照旧，换行点不进 <i>，数字那一组后面的换行点在 </span> 外面；
     没有 zhwrap 时字幕的 HTML 和改之前那段代码出来的一模一样。

用法（在项目根运行）：
    PYTHONDONTWRITEBYTECODE=1 ~/.venvs/frontier-daily/bin/python site/tools/test_video3_zhwrap.py
不调用任何模型、不联网、不写项目文件；浏览器那一组没有 node / Playwright / Chrome 就跳过，断行工具（budoux、jieba）没装也跳过。
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
from unittest import mock

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]
for p in (str(TOOLS), str(ROOT / "pipeline")):
    if p not in sys.path:
        sys.path.insert(0, p)

import video3_zhwrap as ZW  # noqa: E402
from orchestrator import common, steps  # noqa: E402

JS = ROOT / "site" / "v3" / "video3.js"
CSS = ROOT / "site" / "v3" / "video3.css"
PW = os.environ.get("PLAYWRIGHT") or str(Path.home() / ".npm/_npx/9833c18b2d85bc59/node_modules/playwright/index.mjs")
CARD = "绕过传统供应商，直接锁定稀缺设备"          # 11-09 燃气轮机那张卡（成片约 61 秒，原来拆成"稀缺设｜备"）


def have_breaker():
    try:
        import budoux  # noqa: F401
        import jieba  # noqa: F401
        return True
    except ImportError:
        return False


class Env:
    """临时改环境变量 FD_VIDEO_ZH_WRAP 和开关文件（组装程序、fd 两边一起换）。"""

    def __init__(self, env=None, file_text=None):
        self.env, self.file_text = env, file_text

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        f = Path(self.tmp.name) / "fd_开关.json"
        if self.file_text is not None:
            f.write_text(self.file_text, encoding="utf-8")
        envs = {k: v for k, v in os.environ.items() if k != ZW.ENV}
        if self.env is not None:
            envs[ZW.ENV] = self.env
        self.p = [mock.patch.object(ZW, "SWITCH_FILE", f), mock.patch.object(common, "SWITCH_FILE", f),
                  mock.patch.dict(os.environ, envs, clear=True)]
        for x in self.p:
            x.start()
        return self

    def __exit__(self, *a):
        for x in reversed(self.p):
            x.stop()
        self.tmp.cleanup()

    @staticmethod
    def both():
        a, b = ZW.switch()[0], common.zh_wrap_switch()[0]
        assert a == b, (ZW.switch(), common.zh_wrap_switch())
        return a


class Switch(unittest.TestCase):
    def test_rules(self):
        with Env():                                               # 没有文件
            self.assertTrue(Env.both())
        with Env(file_text="{坏了"):
            self.assertTrue(Env.both())
        with Env(file_text=json.dumps({"视频中文整词换行": "关"})):
            self.assertFalse(Env.both())
        with Env(file_text=json.dumps({"视频中文整词换行": "开"})):
            self.assertTrue(Env.both())
        with Env(file_text=json.dumps({"视频中文整词换行": "随便"})):
            self.assertTrue(Env.both())
        with Env(file_text=json.dumps({"新动效和原文截图": "关"})):   # 别的开关不影响它
            self.assertTrue(Env.both())
        with Env("off", json.dumps({"视频中文整词换行": "开"})):     # 环境变量优先
            self.assertFalse(Env.both())
        with Env("on", json.dumps({"视频中文整词换行": "关"})):
            self.assertTrue(Env.both())

    def test_step14_inputs(self):
        with Env(file_text=json.dumps({"视频中文整词换行": "开"})):
            self.assertIn("=中文整词换行=", steps.Video().inputs(None))      # 开着是空字符串：和加开关以前的记录一样，往期不重做
        with Env("off"):
            self.assertIn("=中文整词换行=关", steps.Video().inputs(None))    # 一换开关，第 14 步自动重做

    def test_project_file_is_on(self):
        d = json.loads((ROOT / "fd_开关.json").read_text(encoding="utf-8"))
        self.assertEqual(d["视频中文整词换行"], "开")
        self.assertIn("视频中文整词换行_是什么", d)


def sample_data():
    """一份像场景数据的小样：章（带旁白全文）、模板、原文截图、字幕、文字稿、片头片尾。"""
    return {
        "v": 3, "date": "2026-11-09",
        "chapters": [
            {"id": "power", "kind": "story", "label": {"zh": "电", "en": "Power"},
             "narration": "燃气轮机正在排长队。据路透社报道，AI 数据中心热潮让新设备的交货期排到了 2030 年代。",
             "blocks": [{"type": "quote_card", "id": "bypass", "text": {"zh": CARD, "en": "Bypassing traditional suppliers"},
                         "who": {"zh": "据《金融时报》", "en": "Per the Financial Times"}, "t": {"show": 61.326}, "img": "bypass"},
                        {"type": "quote_card", "id": "delay", "text": {"zh": "燃气轮机供不应求"},
                         "shot": {"quote": "新设备的交货期甚至排到了 2030 年代",
                                  "full": "据路透社今天（9 日）下午报道，AI 数据中心建设热潮让燃气轮机供不应求，新设备的交货期甚至排到了 2030 年代。",
                                  "src": {"name": {"zh": "IT之家", "en": "ITHome"}, "date": {"zh": "11 月 9 日"}}, "url": "https://www.ithome.com/1/024/313.htm"}},
                        {"type": "compare_panel", "id": "gap", "head": {"zh": "2028 年全球燃气轮机（预计）"},
                         "kpi": {"value": "129GW", "text": {"zh": "预计需求"}}}]}],
        "cues": [{"start": 3.99, "end": 6.41, "text": "英伟达董事会启动独立调查，", "t": [3.99 + 0.2 * k for k in range(13)]},
                 {"start": 41.0, "end": 44.0, "text": "到 2028 年，全球产能预计约 87 吉瓦", "t": [41.0 + 0.1 * k for k in range(20)]}],
        "transcript": [{"ch": 0, "text": "燃气轮机正在排长队。", "start": 40.5, "end": 42.0}],
        "T": {"power.bypass.show": 61.326},
        "S": {"title.main": {"zh": "今日地图", "en": "Today's map"}, "close.hint": {"zh": "点任意一片看细节 · 拖动可以转视角", "en": "Tap a tile"}},
        "clusters": [{"id": "power", "name": {"zh": "电"}, "key": {"zh": "129GW"}, "sub": {"zh": "燃气轮机排长队"},
                      "note": [{"zh": "全球产能预计约 87 吉瓦，需求预计 129 吉瓦。", "en": "", "src": ["s01"]}]}],
        "sources": {"s01": {"name": "路透社", "title": "燃气轮机供不应求"}},
    }


@unittest.skipUnless(have_breaker(), "没装断行工具 budoux / jieba")
class Build(unittest.TestCase):
    def test_display_only_adds_marks(self):
        d = ZW.display(CARD)
        self.assertIsNotNone(d)
        self.assertEqual(d.replace(ZW.ZW, ""), CARD)
        self.assertIn("稀缺" + ZW.ZW + "设备", d)                 # 词和词之间可以断
        for w in ("设备", "稀缺", "供应商", "传统", "锁定"):       # 词里面没有换行点
            self.assertIn(w, d)
        g = ZW.display("到 2028 年，全球产能预计约 87 吉瓦")
        self.assertTrue(ZW.same_text("到 2028 年，全球产能预计约 87 吉瓦", g))
        self.assertIn("2028" + ZW.NBSP + "年", g)                 # 数字和单位之间不断
        self.assertIsNone(ZW.display("Per the Financial Times"))  # 没有中文
        self.assertIsNone(ZW.display(""))
        self.assertEqual(ZW.display("董事会"), "董事会")             # 一个词组：不加点，但照样进表（播放器给 keep-all，整个词组不断）
        self.assertIsNone(ZW.display(CARD, breaks=lambda s: s.replace("设备", "设" + ZW.ZW + "被")))   # 对不回原文的不要

    def test_table_leaves_data_alone(self):
        data = sample_data()
        before = copy.deepcopy(data)
        tbl, msg = ZW.table(data)
        self.assertEqual(data, before)                            # 原来的字（触发词、字幕和逐字时间、文字稿、旁白）一个字不动
        self.assertIn("中文整词换行", msg)
        self.assertIn(CARD, tbl)
        self.assertNotIn(data["chapters"][0]["narration"], tbl)   # 旁白全文不显示，不进表
        self.assertIn("英伟达董事会启动独立调查，", tbl)           # 字幕按原文查
        self.assertIn("点任意一片看细节", tbl)                     # 片尾提示按"·"拆开的几行
        exc = ZW.excerpt(data["chapters"][0]["blocks"][1]["shot"])
        self.assertEqual(exc, data["chapters"][0]["blocks"][1]["shot"]["full"])   # 不长，整段照放
        self.assertIn(exc, tbl)
        self.assertNotIn("路透社", tbl)                            # 参考来源不在画面上，不进表
        for k, v in tbl.items():
            self.assertTrue(ZW.same_text(k, v), k)
        data2 = copy.deepcopy(data)
        data2[ZW.KEY] = tbl
        json.dumps(data2, ensure_ascii=False)

    def test_table_without_breaker(self):
        import zh_breaks
        with mock.patch.object(zh_breaks, "load", side_effect=SystemExit("缺少断行工具")):
            tbl, msg = ZW.table(sample_data())
        self.assertIsNone(tbl)
        self.assertIn("不加整词换行", msg)

    def test_terms(self):
        self.assertEqual(ZW.terms({"E1": {"terms": [{"zh": "燃气轮机"}, {"en": "x"}]}, "E2": {}}), ["燃气轮机"])

    def test_sample_issue(self):
        """完整样期（有的话）：对照表的每一项都对得回原文，原数据不变。"""
        roots = [Path(os.environ["FD_SAMPLE_ROOT"]).expanduser()] if os.environ.get("FD_SAMPLE_ROOT") else []
        roots.append(ROOT / "本机资料" / "归档" / "mini试运行_1031-1109")
        f = next((r / "2026-11-06" / "11_视频v3" / "video3_media.json" for r in roots
                  if (r / "2026-11-06" / "11_视频v3" / "video3_media.json").exists()), None)
        if not f:
            self.skipTest("没有 11-06 完整样期（设 FD_SAMPLE_ROOT 指向样期所在的文件夹）")
        data = json.loads(f.read_text(encoding="utf-8"))
        data.pop(ZW.KEY, None)
        before = copy.deepcopy(data)
        tbl, _ = ZW.table(data)
        self.assertEqual(data, before)
        self.assertGreater(len(tbl), 50)
        self.assertTrue(all(ZW.same_text(k, v) for k, v in tbl.items()))
        self.assertTrue(all(c["text"] in tbl or ZW.display(c["text"]) is None for c in data["cues"]))


def node_json(src):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("没有 node")
    return json.loads(subprocess.run([node, "-e", src], capture_output=True, text=True, check=True).stdout)


class Excerpt(unittest.TestCase):
    """原句摘录：Python 这边的截法要和 video3.js 的 excerptParts 一字不差（不然对照表里找不到画面上那一段）。"""

    def test_same_as_js(self):
        js = JS.read_text(encoding="utf-8")
        fn = re.search(r"\n  function excerptParts\(b\) \{.*?\n  \}\n", js, re.S).group(0)
        long_en = "word " * 80
        cases = [{"quote": "新设备的交货期甚至排到了 2030 年代", "full": "据路透社报道，AI 数据中心建设热潮让燃气轮机供不应求，新设备的交货期甚至排到了 2030 年代。"},
                 {"quote": "it won’t use NDAs", "full": long_en + "including that it won’t use NDAs with public officials. " + long_en},
                 {"quote": "中间这句", "full": "前" * 300 + "中间这句" + "后" * 300},
                 {"quote": "找不到的原句", "full": "整段里没有它"},
                 {"quote": "只有原句"}]
        out = node_json(fn + "console.log(JSON.stringify(%s.map(function (b) { return excerptParts(b).join(''); })));" % json.dumps(cases, ensure_ascii=False))
        self.assertEqual(out, [ZW.excerpt(b) for b in cases])


def can_browse():
    return shutil.which("node") and Path(PW).exists() and Path("/Applications/Google Chrome.app").exists()


OLD_SUB = r"""
function oldSub(cue) {      // 改之前 renderSub 里拼字幕 HTML 的那几行（原样抄来作对照）
  var chars = function (x) { return x.split('').map(function (ch) { return '<i>' + esc(ch) + '</i>'; }).join(''); };
  var html = '', txt = cue ? cue.text : '', re = /\d[\d,.]*%?(?: ?(?:美元|[月日年亿万名项个倍]))?/g, last = 0, mm;
  while (cue && (mm = re.exec(txt))) { html += chars(txt.slice(last, mm.index)) + '<span class="nw">' + chars(mm[0]) + '</span>'; last = mm.index + mm[0].length; }
  return cue ? '<p>' + html + chars(txt.slice(last)) + '</p>' : '';
}
"""

PROBE = r"""
import { pathToFileURL } from 'url';
import fs from 'fs';
const { chromium } = await import(pathToFileURL(process.env.PW).href);
const inp = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const b = await chromium.launch({ channel: 'chrome', headless: true });
const p = await (await b.newContext({ viewport: { width: 900, height: 700 } })).newPage();
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.setContent('<!doctype html><meta charset="utf-8"><style>' + inp.css + '</style><body style="font: 20px/1.5 \'PingFang SC\', \'Hiragino Sans GB\', sans-serif"><div class="v3p" id="root"></div></body>');
const r = await p.evaluate((inp) => {
  (0, eval)(inp.code);
  const ix = wbIndex(inp.map), root = document.getElementById('root'), out = {};
  const mk = (html) => { const d = document.createElement('div'); d.innerHTML = html; root.appendChild(d); return d.firstElementChild; };
  // 每个看得见的字在第几行（按字的上沿）
  const tops = (el) => { const a = []; const w = document.createTreeWalker(el, 4); for (let n = w.nextNode(); n; n = w.nextNode()) for (let i = 0; i < n.data.length; i++) {
    if (/[\u200b\u2060]/.test(n.data[i])) continue; const rg = document.createRange(); rg.setStart(n, i); rg.setEnd(n, i + 1); const rc = rg.getClientRects()[0]; a.push([n.data[i], rc ? Math.round(rc.top) : null]); } return a; };
  const splits = (el, words) => { const t = tops(el), s = t.map(x => x[0]).join(''), bad = [];
    words.forEach(w => { let k = s.indexOf(w); while (k >= 0) { const ys = new Set(t.slice(k, k + w.length).map(x => x[1])); if (ys.size > 1) bad.push(w); k = s.indexOf(w, k + 1); } }); return bad; };
  // ① 卡片标题：各种宽度都不拆词；不插换行点的同一句在某些宽度会拆（证明测得到）
  const words = ['绕过', '传统', '供应商', '直接', '锁定', '稀缺', '设备'];
  const on = mk('<div class="v3card"><div class="hd" style="white-space:normal">' + esc(inp.card) + '</div></div>');
  wbWalk(ix, on, false);
  const hd = on.querySelector('.hd');
  out.cardClass = on.className; out.cardText = hd.textContent;     // 整张卡只有这一句：在最外层就对上了，类加在外层
  const off = mk('<div class="v3card"><div class="hd" style="white-space:normal">' + esc(inp.card) + '</div></div>').querySelector('.hd');
  out.badOn = []; out.badOff = [];
  for (let w = 3.0; w <= 16; w += 0.25) { hd.style.width = off.style.width = w + 'em'; out.badOn.push(...splits(hd, words)); out.badOff.push(...splits(off, words)); }
  // ② 滚动数字：画面上先显示 0，也要对得上
  const cnt = mk('<div class="v3line">' + esc(inp.cntPre) + '<span class="v3n em"><span data-c="94.49">0</span>%</span>' + esc(inp.cntPost) + '</div>');
  wbWalk(ix, cnt, false);
  out.cnt = [cnt.className, cnt.textContent, cnt.querySelector('[data-c]').textContent];
  // ③ 标题：正文和扫光副本换行点一样
  const tt = mk('<div class="v3title"><span class="ln"><span class="m">' + esc(inp.title) + '<i class="v3sweep">' + esc(inp.title) + '</i></span></span></div>');
  wbWalk(ix, tt, false);
  const m = tt.querySelector('.m');
  out.title = [m.className, m.firstChild.data, m.querySelector('.v3sweep').textContent, m.querySelector('.v3sweep').className];
  // ④ 对不上的字原样不动
  const no = mk('<div class="v3card"><div class="hd">表里没有的一句话</div></div>');
  wbWalk(ix, no, false);
  out.none = [no.innerHTML, root.querySelectorAll('.v3wbn').length];
  // ⑤ 父层对上、子层没对上：子层恢复普通换行
  const mix = mk('<div class="c">' + esc(inp.card) + '<small>表里没有的小字</small></div>');
  wbWalk(ix, mix, false);
  out.mix = [mix.className, mix.querySelector('small').className];
  // ⑥ 字幕
  var P = {}; eval(inp.sub);     // 直接 eval：renderSub 挂到这里的 P 上
  out.subs = inp.cues.map(function (cue) {
    const el = document.createElement('div'); el.className = 'v3sub'; root.appendChild(el);
    const self = { L: 'zh', cc: true, started: true, exploring: false, cues: [cue], subEl: el, wb: ix, _cue: null };
    const t = cue.t[5] + 0.001;
    P.renderSub.call(self, t);
    const is = [...el.querySelectorAll('i')], pEl = el.querySelector('p');
    const marks = [...pEl.childNodes].concat([...pEl.querySelectorAll('span.nw')].flatMap(s => [...s.childNodes])).filter(n => n.nodeType === 3).map(n => n.data).join('');
    const res = { n: is.length, text: is.map(x => x.textContent).join(''), inI: is.some(x => /[\u200b\u2060]/.test(x.textContent)), cls: pEl.className,
                  marks: (marks.match(/\u200b/g) || []).length, cur: is.findIndex(x => x.className === 'on cur'), on: is.filter(x => /on/.test(x.className)).length,
                  nwTail: [...pEl.querySelectorAll('span.nw')].map(s => /[\u200b\u2060]$/.test(s.textContent)) };
    const el2 = document.createElement('div'); el2.className = 'v3sub'; root.appendChild(el2);
    const plain = { L: 'zh', cc: true, started: true, exploring: false, cues: [cue], subEl: el2, wb: null, _cue: null };
    P.renderSub.call(plain, t);
    // 逐字高亮加的类不算
    res.plainSame = el2.innerHTML.replace(/<i class="[^"]*">/g, '<i>') === (function () { const x = document.createElement('div'); x.innerHTML = oldSub(cue); return x.innerHTML; })();
    res.plainCur = [...el2.querySelectorAll('i')].findIndex(x => x.className === 'on cur');
    return res;
  });
  out.len = wbLen('稀缺\u200b设备\u2060');
  return out;
}, inp);
r.errs = errs;
console.log(JSON.stringify(r));
await b.close();
"""


@unittest.skipUnless(can_browse(), "没有 node / Playwright / Chrome")
@unittest.skipUnless(have_breaker(), "没装断行工具 budoux / jieba")
class Browser(unittest.TestCase):
    def test_player(self):
        js = JS.read_text(encoding="utf-8")
        esc = re.search(r"\n  var esc = function \(s\) \{.*?\n  \};\n", js, re.S).group(0)
        wb = re.search(r"\n  /\* ---- 中文整词换行.*?\n  function wbLen\(s\) \{[^\n]*\n", js, re.S).group(0)
        sub = re.search(r"\n  P\.renderSub = function \(t\) \{.*?\n  \};\n", js, re.S).group(0)
        cues = sample_data()["cues"]
        pre, post, title = "截至", "的员工担心被取代", "今日地图测试标题"
        strs = [CARD, title, pre + "94.49%" + post] + [c["text"] for c in cues]
        inp = {"code": esc + wb + OLD_SUB, "sub": sub, "css": CSS.read_text(encoding="utf-8"),
               "map": {s: ZW.display(s) for s in strs if ZW.display(s)}, "card": CARD, "cntPre": pre, "cntPost": post, "title": title, "cues": cues}
        self.assertIn(CARD, inp["map"])
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "in.json").write_text(json.dumps(inp, ensure_ascii=False), encoding="utf-8")
            (Path(d) / "probe.mjs").write_text(PROBE, encoding="utf-8")
            res = subprocess.run(["node", str(Path(d) / "probe.mjs"), str(Path(d) / "in.json")], capture_output=True, text=True,
                                 env=dict(os.environ, PW=PW), timeout=120)
        self.assertEqual(res.returncode, 0, res.stderr[-2000:])
        r = json.loads(res.stdout.strip().splitlines()[-1])
        self.assertEqual(r["errs"], [])
        self.assertIn("v3wb", r["cardClass"])
        self.assertEqual(r["cardText"], inp["map"][CARD])           # 换行点插进了文本节点
        self.assertEqual(r["badOn"], [])                             # 插了：哪种宽度都不拆词
        self.assertIn("设备", r["badOff"])                           # 不插：有的宽度会把"设备"拆开（测得到）
        self.assertIn("v3wb", r["cnt"][0])
        self.assertIn(ZW.ZW, r["cnt"][1])
        self.assertEqual(r["cnt"][2], "0")                           # 滚动数字本身不动
        self.assertIn("v3wb", r["title"][0])
        self.assertEqual(r["title"][1], r["title"][2])               # 扫光副本和正文一样
        self.assertIn("v3wb", r["title"][3])
        self.assertEqual(r["none"], ['<div class="hd">表里没有的一句话</div>', 0])
        self.assertEqual(r["mix"], ["c v3wb", "v3wbn"])
        for cue, s in zip(cues, r["subs"]):
            disp = inp["map"][cue["text"]]
            self.assertEqual(s["n"], len(cue["text"]))               # <i> 个数不变：逐字时间照旧对得上
            self.assertEqual(s["text"].replace(ZW.NBSP, " "), cue["text"])
            self.assertFalse(s["inI"])                               # 换行点不进 <i>
            self.assertEqual(s["cls"], "v3wb")
            self.assertEqual(s["marks"], disp.count(ZW.ZW))
            self.assertEqual(s["cur"], 5)                            # 说到第 6 个字，第 6 个 <i> 是当前字
            self.assertEqual(s["cur"], s["plainCur"])
            self.assertEqual(s["on"], 6)
            self.assertFalse(any(s["nwTail"]))                       # 数字那一组后面的换行点在 </span> 外面
            self.assertTrue(s["plainSame"])                          # 没有 zhwrap：和改之前一模一样
        self.assertEqual(r["len"], 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
