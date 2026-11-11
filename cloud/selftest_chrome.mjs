// 云端自检：Chrome 在这台没有显卡的机器上能不能建 WebGL（网页里的三维视频播放器 site/v3/video3.js 要它）。
// 用法：PLAYWRIGHT=<playwright/index.mjs> FD_CHROME_ARGS="…" node cloud/selftest_chrome.mjs
// 输出一行 json：webgl1、webgl2 能不能建、渲染器名字（SwiftShader 就是软件渲染）。只看不改，不联网。
import { pathToFileURL } from 'url';

const PW = process.env.PLAYWRIGHT;
const { chromium } = await import(pathToFileURL(PW).href);
const args = (process.env.FD_CHROME_ARGS || '').split(/\s+/).filter(Boolean);
const t0 = Date.now();
const browser = await chromium.launch({ channel: 'chrome', headless: true, args });
try {
  const p = await (await browser.newContext()).newPage();
  await p.setContent('<canvas id=c width=64 height=64></canvas>');
  const r = await p.evaluate(() => {
    const out = {};
    for (const k of ['webgl', 'webgl2']) {
      const gl = document.getElementById('c').getContext(k) || document.createElement('canvas').getContext(k);
      out[k] = !!gl;
      if (gl) {
        const ext = gl.getExtension('WEBGL_debug_renderer_info');
        out[k + '_renderer'] = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
      }
    }
    return out;
  });
  console.log(JSON.stringify({ chrome: browser.version(), args, ...r, ms: Date.now() - t0 }));
  if (!r.webgl && !r.webgl2) process.exitCode = 1;
} finally {
  await browser.close();
}
