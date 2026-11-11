// 验收："听全集"和"听这一段"按钮是否让播客从对应时间开始放（记录页面里新建的 Audio 对象）。
// 用法：PW=~/.npm/_npx/9833c18b2d85bc59/node_modules/playwright node site/tools/check_listen.js "<index.html 的 file:// 地址>"
const { chromium } = require(process.env.PW);
(async () => {
  // FD_CHROME_ARGS：别的机器上 Chrome 的显卡参数（空格分开）；没设时和原来一样。云端没有显卡，workflow 设成 SwiftShader 软件渲染那一组
  const browser = await chromium.launch({ channel: 'chrome', args: (process.env.FD_CHROME_ARGS || '').split(/\s+/).filter(Boolean) });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => {
    const A = window.Audio; window.__aud = [];
    window.Audio = function (...args) { const a = new A(...args); window.__aud.push(a); return a; };
    window.Audio.prototype = A.prototype;
  });
  const page = await ctx.newPage();
  await page.goto(process.argv[2], { waitUntil: 'load' });
  await page.waitForTimeout(1500);
  const results = [];
  const btns = page.locator('button[data-act="listen"]:visible');
  const n = await btns.count();
  if (!n) { console.log('听这一段按钮数：0（这一期没有播客，跳过）'); await browser.close(); return; }
  for (const i of [0, Math.min(1, n - 1)]) {
    const b = btns.nth(i); await b.scrollIntoViewIfNeeded();
    const label = (await b.evaluate(el => (el.closest('button,a') || el).textContent.trim())).slice(0, 30);
    await b.click(); await page.waitForTimeout(2500);
    const st = await page.evaluate(() => window.__aud.map(a => ({ src: (a.currentSrc || a.src).split('/').slice(-2).join('/'), t: +a.currentTime.toFixed(1), dur: +(a.duration || 0).toFixed(1), paused: a.paused })));
    results.push({ button: label, audio: st });
    await page.evaluate(() => window.__aud.forEach(a => a.pause()));
  }
  console.log('听这一段按钮数：', n); console.log(JSON.stringify(results, null, 1));
  await browser.close();
})();
