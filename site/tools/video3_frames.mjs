// 视频 v3：按指定时刻逐帧渲染演示页（不放声音），存成 PNG。动效尝试版的修前修后对比图、逐像素回归都用它（2026-11-06 晚加）。
//
// 用法（在项目根运行）：
//   node site/tools/video3_frames.mjs <期目录或它的 11_视频v3 目录> <输出目录> --t 5.2,20.3,46.8   # 这几个时刻
//   node site/tools/video3_frames.mjs <…> <输出目录> --every 3                                     # 从 0.5 秒起每 3 秒一帧，到片尾
//   可加 --w 1280 --h 720（默认 1280×720，和 video3_record.mjs 一样）、--dark（深色）。
// 输出：<输出目录>/f_<秒，两位小数>.png，和一份 帧.json（时刻、文件名、页面报错）。
// 渲染办法和 video3_record.mjs 的关键帧总览相同：renderAt(t−0.04)、renderAt(t)，等 150 毫秒（配图解码、字体），再 renderAt(t) 截图。
import fs from 'fs';
import path from 'path';
import os from 'os';
import { pathToFileURL } from 'url';

const PW = process.env.PLAYWRIGHT || path.join(os.homedir(), '.npm/_npx/9833c18b2d85bc59/node_modules/playwright/index.mjs');
const args = process.argv.slice(2);
const val = k => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
const pos = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && ['--t', '--every', '--w', '--h'].includes(args[i - 1])));
if (pos.length < 2) { console.error('用法：node site/tools/video3_frames.mjs <期目录或 11_视频v3> <输出目录> (--t 1,2,3 | --every 3) [--w 1280 --h 720] [--dark]'); process.exit(2); }
let dir = path.resolve(pos[0]);
if (!fs.existsSync(path.join(dir, 'index.html')) && fs.existsSync(path.join(dir, '11_视频v3', 'index.html'))) dir = path.join(dir, '11_视频v3');
const page = path.join(dir, 'index.html');
if (!fs.existsSync(page)) { console.error('找不到演示页：' + page); process.exit(1); }
const out = path.resolve(pos[1]); fs.mkdirSync(out, { recursive: true });
const W = +(val('--w') || 1280), H = +(val('--h') || 720), dark = args.includes('--dark');
const { chromium } = await import(pathToFileURL(PW).href);
// FD_CHROME_ARGS：别的机器上 Chrome 的显卡参数（空格分开）；没设时和原来一样。云端没有显卡，workflow 设成 SwiftShader 软件渲染那一组
const GPU_ARGS = process.env.FD_CHROME_ARGS ? process.env.FD_CHROME_ARGS.split(/\s+/).filter(Boolean) : ['--use-angle=metal', '--ignore-gpu-blocklist'];
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: GPU_ARGS });
const errs = [], done = [];
try {
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, colorScheme: dark ? 'dark' : 'light' });
  const p = await ctx.newPage();
  p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await p.goto(pathToFileURL(page).href + '?rec=1&eager=1&theme=' + (dark ? 'dark' : 'light'));
  await p.waitForFunction(() => window.__v3 && window.__v3.world, null, { timeout: 30000 });
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(1200);
  const dur = await p.evaluate(() => window.__v3.duration);
  let times = (val('--t') || '').split(',').map(Number).filter(x => isFinite(x) && x >= 0);
  if (val('--every')) { const st = +val('--every'); for (let t = 0.5; t < dur; t += st) times.push(Math.round(t * 100) / 100); }
  times = [...new Set(times)].sort((a, b) => a - b);
  for (const t0 of times) {
    const t = Math.min(t0, dur - 0.05);
    await p.evaluate(t => { window.__v3.renderAt(t - 0.04); window.__v3.renderAt(t); }, t);
    await p.waitForTimeout(150);
    await p.evaluate(t => window.__v3.renderAt(t), t);
    const f = 'f_' + t0.toFixed(2) + '.png';
    await p.screenshot({ path: path.join(out, f) });
    done.push({ t: t0, file: f });
  }
  await ctx.close();
} finally {
  await browser.close();
}
fs.writeFileSync(path.join(out, '帧.json'), JSON.stringify({ page, w: W, h: H, dark, frames: done, errors: errs }, null, 1));
console.log('逐帧：' + done.length + ' 帧 → ' + out + (errs.length ? '；页面报错：' + errs.join(' | ') : '；页面无报错'));
