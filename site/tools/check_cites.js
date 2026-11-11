// 验收：上标引用是否单独掉到下一行，以及各切换块的页签数（电脑 1440、手机 390 两种宽度）。
// 用法：PW=~/.npm/_npx/9833c18b2d85bc59/node_modules/playwright node site/tools/check_cites.js "<index.html 的 file:// 地址>"
// 输出 lonely 为空才算通过。
const { chromium } = require(process.env.PW);
(async () => {
  // FD_CHROME_ARGS：别的机器上 Chrome 的显卡参数（空格分开）；没设时和原来一样。云端没有显卡，workflow 设成 SwiftShader 软件渲染那一组
  const browser = await chromium.launch({ channel: 'chrome', args: (process.env.FD_CHROME_ARGS || '').split(/\s+/).filter(Boolean) });
  for (const vp of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const page = await (await browser.newContext({ viewport: vp })).newPage();
    await page.goto(process.argv[2], { waitUntil: 'load' });
    await page.evaluate(async () => { await document.fonts.ready; });
    await page.waitForTimeout(2000);
    const r = await page.evaluate(() => {
      const res = [];
      document.querySelectorAll('sup').forEach(s => {
        if (!s.offsetParent) return;
        const sr = s.getClientRects()[0]; if (!sr) return;
        // 取上标前面紧挨着的那个字（跨元素也算）
        const range = document.createRange();
        range.setStartBefore(s); range.collapse(true);
        const walker = document.createTreeWalker(s.parentNode.closest('p,li,div,section,article') || document.body, NodeFilter.SHOW_TEXT);
        let last = null, n;
        while ((n = walker.nextNode())) { if (s.contains(n)) break; if (n.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING && n.textContent.trim()) last = n; }
        if (!last) return;
        const t = last.textContent.replace(/\s+$/, '');
        // 周末"这一题的来源"一行（app.js deepSrcLine，类名 dl-src）：只有"来源"和一串上标，上标之间特意留了换行点 U+200B，
        // 手机上在上标之间折行是设计如此（11-01 晚定），不算"上标单独掉行"（11-06 晚加：周日彩排 16 个来源在 390 宽折到第二行被误报）
        if (s.closest('.dl-src') && /\u200b$/.test(t)) return;
        const rr = document.createRange();
        rr.setStart(last, t.length - 1); rr.setEnd(last, t.length);
        const cr = rr.getClientRects(); const c = cr[cr.length - 1]; if (!c) return;
        if (sr.top - c.top > c.height * 0.8) res.push({ sup: s.textContent, before: t.slice(-12), where: (s.closest('[id]') || {}).id || '' });
      });
      const tabs = [...document.querySelectorAll('[role="tablist"]')].map(t => (t.getAttribute('aria-label') || t.className).slice(0, 40) + ':' + t.querySelectorAll('[role="tab"]').length);
      return { lonely: res, tabs };
    });
    console.log(vp.width, JSON.stringify(r, null, 0));
  }
  await browser.close();
})();
