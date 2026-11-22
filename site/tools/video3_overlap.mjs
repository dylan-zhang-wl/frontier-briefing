// 视频 v3：画面叠压检查（2026-11-22 加；fd_开关.json"画面叠压检查"开着时，第 14 步在成片就位、预览录完以后调用）。只提醒：不挡第 14 步、
// 不进导演第二轮"必须改"。它另开一页、不截图，量完就关，和截关键帧、录预览不是同一页，成片一个像素不动。
//
// 做法：逐 0.5 秒（--step）把演示页渲染到第 t 秒——只算场景、镜头和 HTML 卡片的位置，不画三维画面（云端软件渲染也快）——
// 量看得见的卡片外框，三类：
//   ① 小卡相交：两张看得见的小卡（.v3tile，分岔对照两边那种）外框相交，横、竖都超过 4 像素（11-12 第 115 秒、11-22 第 113–120 秒那种）；
//   ② 卡片内容超出卡片：看得见的卡片（.v3card、.v3tile）最后一个子元素下沿比卡片内框低 1 像素以上（就是 scrollHeight 比 clientHeight
//      大 1 像素以上，只是按布局量、不算动画位移；高度写死、字放不下，11-22 第 70.5 秒那种）；
//      卡片自己裁边（overflow 不是 visible）的，要有字伸出卡片外框 1 像素以上才算（超出的是被裁掉的推近图那一截，不算）；
//   ③ 卡片字压在字幕条下：看得见的卡片里一行看得见的字，和字幕条（.v3sub p 那一条底色）相交，横、竖都超过 2 像素。
// "看得见"：卡片和上面各层的不透明度乘起来至少 0.95（小卡飞进来、章末飞回去那一下是 0.9 以下，不算）；字那一层至少 0.5。
// 同一张卡（另一张）、同一类，连续量到、首尾至少隔 1 秒（--min）才记一处，记首尾时刻和最重的那一刻。
//
// 用法（在项目根运行）：
//   node site/tools/video3_overlap.mjs <期目录或它的 11_视频v3> [--out <json>] [--step 0.5] [--min 1] [--w 1280 --h 720]
//   默认写 <期目录>/logs/视频_叠压检查.json（给的是 11_视频v3 目录时写到它上一级的 logs/）；JSON 里只写相对路径。
//   退出码 0＝量完了（不管有没有叠压），1＝没量成（找不到演示页、页面没起来）。终端只印一行汇总。
// 浏览器：本机 Chrome，显卡参数同 video3_record.mjs（FD_CHROME_ARGS）；Playwright 包位置同上（PLAYWRIGHT）。
import fs from 'fs';
import path from 'path';
import os from 'os';
import { pathToFileURL } from 'url';

const PW = process.env.PLAYWRIGHT || path.join(os.homedir(), '.npm/_npx/9833c18b2d85bc59/node_modules/playwright/index.mjs');
const args = process.argv.slice(2);
const val = k => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
const VALUED = ['--out', '--step', '--min', '--w', '--h'];
const pos = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && VALUED.includes(args[i - 1])));
if (!pos.length) { console.error('用法：node site/tools/video3_overlap.mjs <期目录或 11_视频v3> [--out <json>] [--step 0.5] [--min 1]'); process.exit(2); }
let dir = path.resolve(pos[0]);
if (!fs.existsSync(path.join(dir, 'index.html')) && fs.existsSync(path.join(dir, '11_视频v3', 'index.html'))) dir = path.join(dir, '11_视频v3');
const page = path.join(dir, 'index.html');
if (!fs.existsSync(page)) { console.error('画面叠压检查：找不到演示页 ' + page); process.exit(1); }
const issue = path.dirname(dir);
const out = path.resolve(val('--out') || path.join(issue, 'logs', '视频_叠压检查.json'));
const STEP = +(val('--step') || 0.5), MIN = +(val('--min') || 1), W = +(val('--w') || 1280), H = +(val('--h') || 720);
const KINDS = { tile: '小卡相交', over: '卡片内容超出卡片', sub: '卡片字压在字幕条下' };
const GPU_ARGS = process.env.FD_CHROME_ARGS ? process.env.FD_CHROME_ARGS.split(/\s+/).filter(Boolean) : ['--use-angle=metal', '--ignore-gpu-blocklist'];

// 在页面里跑：第 t 秒看得见的卡片、三类叠压
function measure() {
  const VIS = 0.95, TXT = 0.5;
  const op = e => {          // 自己和上面各层的不透明度乘起来；看不见（visibility、display）就是 0
    const cs0 = getComputedStyle(e);
    if (cs0.visibility === 'hidden' || cs0.display === 'none') return 0;
    let o = 1;
    for (let x = e; x && x !== document.body; x = x.parentElement) { const cs = getComputedStyle(x); if (cs.display === 'none') return 0; o *= +cs.opacity; }
    return o;
  };
  const R = r => [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)];
  const cut = (a, b) => [Math.min(a.right, b.right) - Math.max(a.left, b.left), Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)];
  const name = e => (e.textContent || '').replace(/[\u200b\u2060]/g, '').replace(/\s+/g, ' ').trim().slice(0, 24);
  const vw = innerWidth, vh = innerHeight, found = [];
  const all = [...document.querySelectorAll('.v3card, .v3tile')];
  const cards = [];
  all.forEach((e, i) => {
    const r = e.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || r.right <= 0 || r.bottom <= 0 || r.left >= vw || r.top >= vh) return;
    if (op(e) < VIS) return;
    cards.push({ e, i, r, tile: e.classList.contains('v3tile') });
  });
  // ① 小卡相交
  for (let a = 0; a < cards.length; a++) for (let b = a + 1; b < cards.length; b++) {
    const A = cards[a], B = cards[b];
    if (!A.tile || !B.tile) continue;
    const [w, h] = cut(A.r, B.r);
    if (w > 4 && h > 4) found.push({ k: 'tile', key: 'tile:' + A.i + ':' + B.i, card: name(A.e), other: name(B.e), box: R(A.r), box2: R(B.r), size: [Math.round(w), Math.round(h)], sev: w * h });
  }
  // ② 卡片内容超出卡片：scrollHeight 比 clientHeight 大 1 像素以上。卡片自己裁边（overflow 不是 visible，带题图的帖子卡、要点卡）时，
  //   超出的多半是推近放大的那一截图、本来就裁掉，只有字伸出卡片外框才算（11-03 第 85–91 秒那张帖子卡：多 16 像素，字都在框里）
  const textOut = (c) => {
    let out = 0;
    const tw = document.createTreeWalker(c.e, NodeFilter.SHOW_TEXT);
    for (let n = tw.nextNode(); n; n = tw.nextNode()) {
      if (!n.nodeValue.replace(/[\s\u200b\u2060]/g, '')) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const r of rg.getClientRects()) out = Math.max(out, r.bottom - c.r.bottom, c.r.top - r.top);
    }
    return out;
  };
  // 按布局量（offsetTop）：最后一个子元素下沿比卡片内框低多少。和 scrollHeight − clientHeight 一样，只是不算动画位移
  //   （卡片数值跟着旁白出那几样没出场时往下错开 6 像素、出场时淡入上移），和播放器 video3.js 的 lgFit 同一个量法
  const below = (e) => {
    let bot = -Infinity;
    for (const k of e.children) bot = Math.max(bot, k.offsetTop - (k.offsetParent === e ? 0 : e.offsetTop + e.clientTop) + k.offsetHeight);
    return e.children.length ? bot - e.clientHeight : 0;
  };
  cards.forEach(c => {
    const d = Math.round(below(c.e));
    if (d <= 1) return;
    if (getComputedStyle(c.e).overflowY !== 'visible' && textOut(c) <= 1) return;
    found.push({ k: 'over', key: 'over:' + c.i, card: name(c.e), box: R(c.r), px: d, sev: d });
  });
  // ③ 卡片字压在字幕条下
  const sp = document.querySelector('.v3sub p');
  const subs = sp && (sp.textContent || '').trim() && op(sp) >= TXT ? [...sp.getClientRects()].filter(r => r.width > 1 && r.height > 1) : [];
  if (subs.length) cards.forEach(c => {
    const tw = document.createTreeWalker(c.e, NodeFilter.SHOW_TEXT);
    let worst = null;
    for (let n = tw.nextNode(); n; n = tw.nextNode()) {
      if (!n.nodeValue.replace(/[\s\u200b\u2060]/g, '')) continue;
      if (!n.parentElement || op(n.parentElement) < TXT) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const r of rg.getClientRects()) for (const s of subs) {
        const [w, h] = cut(r, s);
        if (w > 2 && h > 2 && (!worst || w * h > worst.sev)) worst = { line: R(r), bar: R(s), size: [Math.round(w), Math.round(h)], sev: w * h, text: n.nodeValue.replace(/[\u200b\u2060]/g, '').trim().slice(0, 24) };
      }
    }
    if (worst) found.push({ k: 'sub', key: 'sub:' + c.i, card: name(c.e), box: R(c.r), line: worst.line, bar: worst.bar, size: worst.size, text: worst.text, sev: worst.sev });
  });
  return found;
}

const { chromium } = await import(pathToFileURL(PW).href);
let browser = null, errs = [], res = null;
try {
  browser = await chromium.launch({ channel: 'chrome', headless: true, args: GPU_ARGS });
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, colorScheme: 'light' });
  const p = await ctx.newPage();
  p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await p.goto(pathToFileURL(page).href + '?rec=1&eager=1&theme=light');
  await p.waitForFunction(() => window.__v3 && window.__v3.world, null, { timeout: 60000 });
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(1200);
  const info = await p.evaluate(() => {
    const v = window.__v3; v.world.draw = function () {};       // 只量卡片位置：三维画面不画（这一页不截图，只在这一页里改）
    return { dur: v.duration, chapters: v.chapters.map(c => ({ id: c.id, l: (c.label && (c.label.zh || c.label.en)) || c.id, s: c.start, e: c.end })) };
  });
  const times = [];
  for (let t = STEP / 2; t < info.dur; t += STEP) times.push(Math.round(t * 100) / 100);
  const hits = {};          // key → [{t, …}]
  for (const t of times) {
    const f = await p.evaluate(([t, fn]) => { window.__v3.renderAt(t - 0.04); window.__v3.renderAt(t); return (new Function('return ' + fn))()(); }, [t, measure.toString()]);
    f.forEach(x => { (hits[x.key] = hits[x.key] || []).push(Object.assign({ t }, x)); });
  }
  await ctx.close();
  // 连续量到的合成一段；首尾至少隔 MIN 秒才算一处
  const spans = [];
  Object.values(hits).forEach(list => {
    let cur = [];
    const flush = () => {
      if (cur.length && cur[cur.length - 1].t - cur[0].t >= MIN - 1e-6) {
        const worst = cur.reduce((a, b) => (b.sev > a.sev ? b : a));
        const ch = info.chapters.filter(c => c.s <= cur[0].t + 1e-6).pop() || info.chapters[0] || {};
        const o = { 种类: KINDS[worst.k], 章: ch.l || '', 章id: ch.id || '', 从: cur[0].t, 到: cur[cur.length - 1].t, 卡片: worst.card };
        if (worst.other) o.另一张 = worst.other;
        o.最重的一刻 = Object.assign({ 秒: worst.t, 卡片外框: worst.box },
          worst.k === 'tile' ? { 另一张外框: worst.box2, 相交宽高: worst.size } :
          worst.k === 'over' ? { 超出像素: worst.px } : { 那一行字: worst.text, 那一行外框: worst.line, 字幕条外框: worst.bar, 相交宽高: worst.size });
        spans.push(o);
      }
      cur = [];
    };
    list.forEach(x => { if (cur.length && x.t - cur[cur.length - 1].t > STEP * 1.5) flush(); cur.push(x); });
    flush();
  });
  spans.sort((a, b) => a.从 - b.从 || a.种类.localeCompare(b.种类));
  const kinds = {};
  spans.forEach(s => { kinds[s.种类] = (kinds[s.种类] || 0) + 1; });
  res = { 说明: '画面叠压检查（fd_开关.json"画面叠压检查"；site/tools/video3_overlap.mjs）：只提醒，不挡。量法见程序文件头。',
    页面: path.relative(issue, page).split(path.sep).join('/'), 画幅: [W, H], 步长秒: STEP, 至少连续秒: MIN, 时长秒: info.dur, 量了几个时刻: times.length,
    量于: new Date().toISOString().replace(/\.\d+Z$/, 'Z'), 处数: spans.length, 各类: kinds, 各处: spans, 页面报错: errs.slice(0, 10) };
} catch (e) {
  console.error('画面叠压检查没量成：' + (e && e.message ? e.message.split('\n')[0] : e));
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
}
if (res) {
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, JSON.stringify(res, null, 1));
  const ks = Object.entries(res.各类).map(([k, n]) => k + ' ' + n).join('、');
  console.log('画面叠压检查：' + res.处数 + ' 处' + (res.处数 ? '（' + ks + '）：' + res.各处.map(s => s.从 + '–' + s.到 + ' 秒').join('、') : '') +
    '；量了 ' + res.量了几个时刻 + ' 个时刻（每 ' + STEP + ' 秒）' + (errs.length ? '；页面报错 ' + errs.length + ' 条' : '') + ' → ' + path.basename(path.dirname(out)) + '/' + path.basename(out));
}
