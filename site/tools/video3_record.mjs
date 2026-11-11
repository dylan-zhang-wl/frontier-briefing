// 视频 v3：录预览 MP4（Playwright 录屏 + ffmpeg 合上旁白）和关键帧总览图。
//
// 用法（在项目根运行；先用 site/tools/video3_build.py 组装好演示页）：
//   node site/tools/video3_record.mjs 测试版/2026-10-31            # 浅色：预览.mp4 ＋ 关键帧总览.jpg
//   node site/tools/video3_record.mjs 测试版/2026-10-31 --dark     # 深色：预览_深色.mp4（不出总览图）
//   node site/tools/video3_record.mjs 测试版/2026-10-31 --sheet    # 只出关键帧总览图
// 关键帧总览（11-06 补）：除了每个模板"触发词后 0.9 秒"，还截分镜检查找到的空档（video3_storyboard.blank_spans 写进
//   chapters[].blank：画面上没有真东西超过 4 秒的那几段、章首迟迟没有主角的那一段），格子上标红"空档"，人工看图时空画面也进总览。
// 环境变量 PLAYWRIGHT 可指定 Playwright 包的位置（默认用本机 npx 缓存里那一份），浏览器用本机 Chrome。
//
// 对齐办法：开播前整屏闪一下品红色，放完再开始播（不出声，按墙钟走，和录屏的时间轴一致）；
// 录完用 ffmpeg 找到品红色结束的那一帧，从那里剪开，再把旁白 MP3 从第 0 秒合进去。误差在一帧（40 毫秒）以内。
import fs from 'fs';
import path from 'path';
import os from 'os';
import { execFileSync } from 'child_process';
import { pathToFileURL } from 'url';

const PW = process.env.PLAYWRIGHT || path.join(os.homedir(), '.npm/_npx/9833c18b2d85bc59/node_modules/playwright/index.mjs');
// Playwright 录屏要用它自带的 ffmpeg（平时要另外下载）。这里不下载：在一个临时目录里按它要的位置放一个指向本机 ffmpeg
// （Homebrew，自带 VP8 编码器）的链接，再用 PLAYWRIGHT_BROWSERS_PATH 指过去；用的是本机 Chrome，所以不影响别的。
const pwTmp = fs.mkdtempSync(path.join(os.tmpdir(), 'fd-pw-'));
try {
  const bj = JSON.parse(fs.readFileSync(path.join(path.dirname(PW), '..', 'playwright-core', 'browsers.json'), 'utf8'));
  const rev = (bj.browsers.find(b => b.name === 'ffmpeg') || {}).revision || '1013';
  const sysFF = execFileSync('which', ['ffmpeg']).toString().trim();
  fs.mkdirSync(path.join(pwTmp, 'ffmpeg-' + rev), { recursive: true });
  fs.symlinkSync(sysFF, path.join(pwTmp, 'ffmpeg-' + rev, process.platform === 'darwin' ? 'ffmpeg-mac' : 'ffmpeg-linux'));
  if (!process.env.PLAYWRIGHT_BROWSERS_PATH) process.env.PLAYWRIGHT_BROWSERS_PATH = pwTmp;
} catch (e) { console.warn('没能接上本机 ffmpeg：', e.message); }
const { chromium } = await import(pathToFileURL(PW).href);
const args = process.argv.slice(2);
const issue = path.resolve(args.find(a => !a.startsWith('--')) || '测试版/2026-10-31');
const dark = args.includes('--dark'), sheetOnly = args.includes('--sheet');
const dir = path.join(issue, '11_视频v3'), page = path.join(dir, 'index.html');
if (!fs.existsSync(page)) { console.error('找不到演示页：' + page + '（先运行 site/tools/video3_build.py）'); process.exit(1); }
const W = 1280, H = 720, FPS = 25;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'fd-video3-'));
const url = pathToFileURL(page).href + '?rec=1&eager=1' + (dark ? '&theme=dark' : '&theme=light');
// FD_CHROME_ARGS：别的机器上 Chrome 的显卡参数（空格分开）；没设时和原来一样。云端没有显卡，workflow 设成 SwiftShader 软件渲染那一组
const GPU_ARGS = process.env.FD_CHROME_ARGS ? process.env.FD_CHROME_ARGS.split(/\s+/).filter(Boolean) : ['--use-angle=metal', '--ignore-gpu-blocklist'];
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: GPU_ARGS });
const ff = (a) => execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', ...a], { stdio: ['ignore', 'pipe', 'pipe'] });

async function ready(p) {
  await p.goto(url);
  await p.waitForFunction(() => window.__v3 && window.__v3.world, null, { timeout: 30000 });
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(1200);       // 等配图解码、字体就位
}

// ---------- 1. 录屏 ----------
async function record() {
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, colorScheme: dark ? 'dark' : 'light',
    recordVideo: { dir: tmp, size: { width: W, height: H } } });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await ready(p);
  await p.evaluate(() => { const o = document.createElement('div'); o.id = 'syncflash'; o.style.cssText = 'position:fixed;inset:0;background:#ff00ff;z-index:99999'; document.body.appendChild(o); });
  await p.waitForTimeout(600);
  await p.evaluate(() => new Promise(res => requestAnimationFrame(() => { document.getElementById('syncflash').remove(); const v = window.__v3; v.userSilent = true; v.play(); res(); })));
  const dur = await p.evaluate(() => window.__v3.duration);
  await p.waitForFunction(() => window.__v3.ended, null, { timeout: (dur + 30) * 1000, polling: 500 });
  await p.waitForTimeout(1200);
  const video = p.video();
  await ctx.close();
  const webm = await video.path();
  // 找品红色结束的那一帧
  const raw = execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-i', webm, '-vf', `fps=${FPS},scale=8:4`, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 28 });
  const fsz = 8 * 4 * 3; let inFlash = false, start = -1;
  for (let i = 0; i * fsz < raw.length; i++) {
    let mag = 0; for (let k = 0; k < 32; k++) { const r = raw[i * fsz + k * 3], g = raw[i * fsz + k * 3 + 1], b = raw[i * fsz + k * 3 + 2]; if (r > 200 && g < 90 && b > 200) mag++; }
    if (mag > 24) inFlash = true; else if (inFlash) { start = i; break; }
  }
  if (start < 0) throw new Error('录屏里没找到对齐用的品红闪屏');
  const ss = (start / FPS).toFixed(3);
  const out = path.join(dir, dark ? '预览_深色.mp4' : '预览.mp4');
  // 先把录屏从开播那一帧剪开（只剪画面），再把旁白从第 0 秒合进去
  const vOnly = path.join(tmp, 'v.mp4');
  ff(['-i', webm, '-ss', ss, '-an', '-vf', `fps=${FPS},format=yuv420p`, '-c:v', 'libx264', '-preset', 'slow', '-crf', '19', '-profile:v', 'high', vOnly]);
  ff(['-i', vOnly, '-i', path.join(dir, 'audio', 'video3.mp3'), '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-shortest', out]);
  const probe = execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration,size', '-of', 'json', out]).toString();
  console.log('预览视频：' + path.relative(process.cwd(), out), JSON.parse(probe).format, '剪掉开头', ss, '秒', errs.length ? '页面报错：' + errs.join(' | ') : '页面无报错');
}

// ---------- 2. 关键帧总览图（逐个时刻渲染，比录屏清楚） ----------
async function sheet() {
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, colorScheme: 'light' });
  const p = await ctx.newPage();
  await ready(p);
  const info = await p.evaluate(() => {
    const v = window.__v3, T = v.v.T;
    // 取哪些时刻：片头、全图，每个模板的几个触发词之后 0.9 秒（按分镜里的模板走，不写死某一期的触发词），收尾；多于 20 个就均匀挑 20 个
    const out = [2.6, (T['open.map'] || 4) + 6];
    v.chapters.forEach(c => (c.blocks || []).forEach(b => {
      if (b.type === 'image_card') return;
      const ts = Object.values(b.t || {}).filter(x => typeof x === 'number').sort((x, y) => x - y);
      if (!ts.length) return;
      const k = ts.length >= 5 ? [ts[0], ts[Math.floor(ts.length / 2)], ts[ts.length - 1]] : (ts.length >= 2 ? [ts[0], ts[ts.length - 1]] : [ts[0]]);
      k.forEach(x => out.push(x + 0.9));
    }));
    const lastLine = Object.keys(T).filter(k => /^close\.l\d+$/.test(k)).map(k => T[k]).sort((x, y) => y - x)[0];
    out.push((lastLine || T['close.map'] || v.duration - 4) + 0.9);
    let times = [...new Set(out.map(x => Math.round(x * 100) / 100))].sort((x, y) => x - y);
    if (times.length > 20) { const keep = [times[0]]; for (let i = 1; i < 19; i++) keep.push(times[Math.round(i * (times.length - 1) / 19)]); keep.push(times[times.length - 1]); times = keep; }
    // 空档：每段截中间那一刻（最长的 8 段），和上面的按时间排在一起
    const blanks = [];
    v.chapters.forEach(c => (c.blank || []).forEach(g => blanks.push({ t: g[0] + Math.min(2.0, (g[1] - g[0]) / 2), a: g[0], z: g[1], why: g[2] })));
    blanks.sort((x, y) => (y.z - y.a) - (x.z - x.a));
    const shots = times.map(t => ({ t, blank: null })).concat(blanks.slice(0, 8).map(b => ({ t: Math.round(b.t * 100) / 100, blank: b })));
    shots.sort((x, y) => x.t - y.t);
    return { shots, chapters: v.chapters.map(c => ({ s: c.start, l: c.label.zh })) };
  });
  const dirF = path.join(tmp, 'sheet'); fs.mkdirSync(dirF, { recursive: true });
  for (let i = 0; i < info.shots.length; i++) {
    const sh = info.shots[i], t = Math.min(sh.t, (await p.evaluate(() => window.__v3.duration)) - 0.1);
    let lab = ''; info.chapters.forEach(c => { if (c.s <= t) lab = c.l; });
    const txt = t.toFixed(1) + ' 秒 · ' + lab + (sh.blank ? (sh.blank.why === 'opener' ? ' · 空档：章首没主角 ' : ' · 空档 ') + sh.blank.a.toFixed(1) + '–' + sh.blank.z.toFixed(1) : '');
    await p.evaluate(([t, txt, blank]) => {
      window.__v3.renderAt(t - 0.04); window.__v3.renderAt(t);
      let tag = document.getElementById('captag');
      if (!tag) { tag = document.createElement('div'); tag.id = 'captag'; tag.style.cssText = 'position:fixed;left:0;bottom:0;z-index:99;padding:6px 12px;color:#fff;font:600 18px/1 -apple-system,sans-serif;border-top-right-radius:10px'; document.body.appendChild(tag); }
      tag.style.background = blank ? 'rgba(196,38,30,.92)' : 'rgba(20,16,12,.78)';
      tag.textContent = txt;
    }, [t, txt, !!sh.blank]);
    await p.waitForTimeout(150);
    await p.evaluate(t => window.__v3.renderAt(t), t);
    await p.screenshot({ path: path.join(dirF, `f_${String(i).padStart(3, '0')}.png`) });
  }
  await ctx.close();
  const out = path.join(dir, '关键帧总览.jpg');
  const rows = Math.max(1, Math.ceil(info.shots.length / 4));
  ff(['-framerate', '1', '-i', path.join(dirF, 'f_%03d.png'), '-vf', `scale=480:-1,tile=4x${rows}:padding=8:margin=8:color=0x28241f`, '-frames:v', '1', '-q:v', '3', out]);
  const nb = info.shots.filter(x => x.blank).length;
  console.log('关键帧总览：' + path.relative(process.cwd(), out) + '（' + info.shots.length + ' 格' + (nb ? '，其中空档 ' + nb + ' 格' : '') + '）');
}

try {
  if (sheetOnly) await sheet();
  else { await record(); if (!dark) await sheet(); }
} finally {
  await browser.close();
  fs.rmSync(tmp, { recursive: true, force: true });
  fs.rmSync(pwTmp, { recursive: true, force: true });
}
