// 网页 v3 截图＋自检：等网页字体加载完再截（整页浅色、深色、手机），同时检查报错、横向滚动、字体是否缺字、首屏下载量。用法：
// PW=~/.npm/_npx/9833c18b2d85bc59/node_modules/playwright node site/tools/shoot_v3.js "<v3 index.html 的 file:// 地址>" <输出文件夹> [自检报告.json]
// 用本机 Google Chrome（channel: chrome）；npx 缓存里的 playwright 与已装浏览器版本不一致时就靠这一点。
const { chromium } = require(process.env.PW);
const fs = require('fs');
const path = require('path');
const base = process.argv[2], outDir = process.argv[3], reportPath = process.argv[4];

async function settle(page) {
  await page.evaluate(async () => { await document.fonts.ready; });
  // 截图模式下视频立即加载、图表立即画；等它们都到位
  await page.waitForFunction(() => {
    const v = document.querySelector('#video-root');
    const vOk = !v || v.querySelector('.vplayer');
    const charts = [...document.querySelectorAll('.chart')].filter(c => c.offsetWidth);
    const imgs = [...document.images].every(i => i.complete && i.naturalWidth > 0);
    return vOk && imgs && charts.every(c => c._ec || c.querySelector('svg, canvas, .chart-err'));
  }, null, { timeout: 20000 }).catch(() => {});
  await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map(i => i.decode ? i.decode().catch(() => {}) : 0)); });
  await page.waitForTimeout(1200);
}

// 页面上用标题、正文、展示字体排的字，有没有不在这一期字体子集里的（缺了会退回系统字体）。
// 办法：让浏览器自己报告每个元素的文字实际用了哪些字体（开发者工具协议 CSS.getPlatformFontsForNode）；
//   样式指定了我们的字体、实际却用到了系统字体（苹方、宋体等），就说明子集缺字。
const OURS = /^(Noto Serif SC( Black)?|LXGW WenKai Screen|Instrument Serif|Tinos|Times New Roman)$/;
async function glyphCheck(page) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('DOM.enable'); await cdp.send('CSS.enable');
  const { root } = await cdp.send('DOM.getDocument', { depth: -1 });
  const { nodeIds } = await cdp.send('DOM.querySelectorAll', { nodeId: root.nodeId, selector: 'body *' });
  const bad = [], seen = { title: 0, body: 0, display: 0 };
  for (const id of nodeIds) {
    let st;
    try { st = await cdp.send('CSS.getComputedStyleForNode', { nodeId: id }); } catch (e) { continue; }
    const get = n => (st.computedStyle.find(x => x.name === n) || {}).value || '';
    if (get('display') === 'none' || get('visibility') === 'hidden') continue;
    // v3.1 起字体栈最前面常是 FD Num / FD Latin（数字和西文用 Times），按栈里有没有我们的中文/展示字体来分类
    const fams = get('font-family').split(',').map(f => f.replace(/["']/g, '').trim());
    const role = fams.includes('FD Title') ? 'title' : fams.includes('FD Display') ? 'display'
      : (fams.includes('FD Kai') || fams.includes('FD Latin Full') || fams[0] === 'FD Latin') ? 'body' : null;
    if (!role) continue;
    let pf;
    try { pf = await cdp.send('CSS.getPlatformFontsForNode', { nodeId: id }); } catch (e) { continue; }
    if (!pf.fonts.length) continue;
    seen[role]++;
    const others = pf.fonts.filter(f => !OURS.test(f.familyName));
    if (others.length) {
      const { outerHTML } = await cdp.send('DOM.getOuterHTML', { nodeId: id });
      bad.push(role + ' ← ' + others.map(f => f.familyName + '×' + f.glyphCount).join(', ') + ' · ' + outerHTML.replace(/<[^>]+>/g, '').slice(0, 40));
    }
  }
  await cdp.detach();
  return { elementsChecked: seen, fallbackUsed: bad.slice(0, 30), fallbackCount: bad.length };
}

// 整页截图。很长的页面在高分屏下会超过 Chrome 一次能截的高度（约 16000 像素），超出部分会重复上面的内容；
// 这时分段截，再用 Python（Pillow）拼成一张。
const PY = process.env.PY || path.join(process.env.HOME, '.venvs/frontier-daily/bin/python');
async function fullShot(page, file, dpr) {
  const H = await page.evaluate(() => document.documentElement.scrollHeight);
  const W = await page.evaluate(() => document.documentElement.clientWidth);
  const step = Math.floor(15000 / dpr);
  if (H <= step) { await page.screenshot({ path: file, fullPage: true }); return; }
  const parts = [];
  for (let y = 0, k = 0; y < H; y += step, k++) {
    const p = file + '.part' + k + '.png';
    await page.screenshot({ path: p, fullPage: true, clip: { x: 0, y, width: W, height: Math.min(step, H - y) } });
    parts.push(p);
  }
  require('child_process').execFileSync(PY, ['-c',
    'import sys\nfrom PIL import Image\nps=[Image.open(p) for p in sys.argv[2:]]\nout=Image.new("RGB",(ps[0].width,sum(p.height for p in ps)))\ny=0\nfor p in ps:\n    out.paste(p,(0,y)); y+=p.height\nout.save(sys.argv[1])',
    file].concat(parts));
  parts.forEach(p => fs.unlinkSync(p));
}

(async () => {
  // FD_CHROME_ARGS：别的机器上 Chrome 的显卡参数（空格分开）；没设时和原来一样。云端没有显卡，workflow 设成 SwiftShader 软件渲染那一组
  const browser = await chromium.launch({ channel: 'chrome', args: (process.env.FD_CHROME_ARGS || '').split(/\s+/).filter(Boolean) });
  const shots = [
    { name: '截图_浅色.png', q: 'theme=light&static=1', vp: { width: 1440, height: 900 }, dpr: 1 },
    { name: '截图_深色.png', q: 'theme=dark&static=1', vp: { width: 1440, height: 900 }, dpr: 1 },
    { name: '截图_手机.png', q: 'theme=light&static=1', vp: { width: 390, height: 844 }, dpr: 2, mobile: true },
  ];
  const report = {};
  for (const s of shots) {
    const ctx = await browser.newContext({ viewport: s.vp, deviceScaleFactor: s.dpr, isMobile: !!s.mobile, hasTouch: !!s.mobile });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', e => errs.push('pageerror: ' + String(e)));
    page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') errs.push(m.type() + ': ' + m.text()); });
    page.on('requestfailed', r => { const f = r.failure(); if (!(f && /ERR_ABORTED/.test(f.errorText) && /\.mp3$/.test(r.url()))) errs.push('failed: ' + r.url().split('/').slice(-2).join('/') + ' ' + (f && f.errorText)); });
    await page.goto(`${base}?${s.q}`, { waitUntil: 'load' });
    await settle(page);
    const info = await page.evaluate(() => ({
      overflowX: document.documentElement.scrollWidth - window.innerWidth,
      height: document.documentElement.scrollHeight,
      accent: document.documentElement.getAttribute('data-accent'),
      fontsLoaded: [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family.replace(/"/g, '') + ' ' + f.weight + (f.style === 'italic' ? 'i' : '')).filter((v, i, a) => a.indexOf(v) === i),
    }));
    const glyphs = await glyphCheck(page);
    await fullShot(page, path.join(outDir, s.name), s.dpr);
    report[s.name] = Object.assign(info, { glyphs, errors: errs });
    console.log(s.name, JSON.stringify(report[s.name]));
    await ctx.close();
  }

  // 首屏下载量：正常打开（不是截图模式）、不滚动；记下所有请求的字节数（不含音频）
  for (const vp of [{ width: 1440, height: 900, dpr: 1, name: '电脑' }, { width: 390, height: 844, dpr: 3, name: '手机', mobile: true }]) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: vp.dpr, isMobile: !!vp.mobile, hasTouch: !!vp.mobile });
    const page = await ctx.newPage();
    const errs = [];
    page.on('pageerror', e => errs.push('pageerror: ' + String(e)));
    page.on('console', m => { if (m.type() === 'error') errs.push('error: ' + m.text()); });
    const cdp = await ctx.newCDPSession(page);
    await cdp.send('Network.enable');
    const reqs = {};
    cdp.on('Network.responseReceived', e => { reqs[e.requestId] = { url: e.response.url, bytes: 0 }; });
    cdp.on('Network.dataReceived', e => { if (reqs[e.requestId]) reqs[e.requestId].bytes += e.dataLength; });
    cdp.on('Network.loadingFinished', e => { if (reqs[e.requestId] && e.encodedDataLength > reqs[e.requestId].bytes) reqs[e.requestId].bytes = e.encodedDataLength; });
    await page.goto(base, { waitUntil: 'load' });
    await page.evaluate(async () => { await document.fonts.ready; });
    await page.waitForTimeout(2500);
    const list = Object.values(reqs).filter(r => !/\.mp3/.test(r.url) && !r.url.startsWith('data:'));
    let total = 0;
    const rows = list.map(r => { total += r.bytes; return [decodeURIComponent(r.url.split('/').slice(-2).join('/')), Math.round(r.bytes / 1024)]; }).sort((a, b) => b[1] - a[1]);
    report['首屏_' + vp.name] = { totalKB: Math.round(total / 1024), files: rows, errors: errs };
    console.log('首屏（' + vp.name + '，不含音频）', Math.round(total / 1024), 'KB', JSON.stringify(rows), errs.length ? 'ERR ' + errs.join(' | ') : '');
    await ctx.close();
  }
  if (reportPath) fs.writeFileSync(reportPath, JSON.stringify(report, null, 1));
  await browser.close();
})();
