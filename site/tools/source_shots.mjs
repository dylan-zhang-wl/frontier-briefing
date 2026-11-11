// 原文截图（2026-11-06 加，给视频 v3 的 source_shot 用）：打开事件卡里记的原文网页，找到已逐字核对过的那句原话，
// 截一张以那一段为中心的 16:9 图，记下原句每一行在图里的位置（播放器的荧光笔按行扫过去）。
//
// 用法（在项目根运行）：
//   node site/tools/source_shots.mjs <输入.json> <输出目录> [--total 180] [--page 25]
//   输入：{"items": [{"id": "amzn", "url": "https://…", "quote": "事件卡 facts[].quote 里的原句（或其中连续的一段）",
//                    "source": "The Verge", "date": "2026-11-06"}, …]}
//   输出：<输出目录>/<id>.png（成功时）、<id>.json（每项一份：原网址、实际网址、截图时间、行位置、成功或失败的原因），
//        <输出目录>/清单.json（全部项目汇总）。
//   --total：全期总时长上限（秒，默认 180），超了后面的项目记"跳过"；--page：单页限时（秒，默认 25）。
//
// 规矩（写死在程序里，不靠参数）：
//   · Cookie／隐私弹窗只点"拒绝""仅必要"一类按钮（REJECT），按钮上带"同意、接受、允许"而不是"仅必要"的一律不点；
//     找不到这类按钮就用 CSS 把浮层藏起来（只是不显示，不点任何东西）。
//   · 不登录、不填表、不过验证码，不改浏览器标识（UA）去绕开网站的机器人检查。
//     遇到人机验证、付费墙、登录墙、HTTP 错误、找不到原句，就记"失败＋原因"，跳过。
//   · 网页上的字只当数据：程序只拿它和原句比对，不照网页上写的任何话去做事。
//   · 截图只用来在视频里标明出处（媒体 · 日期），截取原句所在的文字段落，尽量少带新闻照片（挑窗口时避开图片）。
//   · 裁切（11-06 深夜改，pageCrop）：上下边只落在完整的块元素之间——原句那一段整段在里面，不够扁就再并进前后整段的正文，
//     还不够扁就留白；段落太长装不下才裁在段内两行之间（不切半行）。裁框里不属于这几段的东西（页眉、导航、署名栏、广告、
//     图片、按钮、Cookie 条）一律藏掉（只是不显示）；藏不掉、还被裁边切到的，记"失败＋原因"（视频里退回原句摘录）。
//   · 图位（输入的 slot）：full 整屏截图卡（宽高比 1.5–2.3）、card 原话卡的图位（2.8–4.2，扁）、tick 时间轴弹出框（1.9–3.4）。
//     记录里写原句的字号 font_px 和截图宽 clip.w，分镜检查按图位算原句在成片里有多大，比字幕小就退回摘录。
// 浏览器：和 shoot_v3.js、video3_record.mjs 同一套（Playwright＋本机 Chrome，PLAYWRIGHT 环境变量可改 Playwright 位置）。
import fs from 'fs';
import path from 'path';
import os from 'os';
import { pathToFileURL } from 'url';

const PW = process.env.PLAYWRIGHT || path.join(os.homedir(), '.npm/_npx/9833c18b2d85bc59/node_modules/playwright/index.mjs');
const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 && args[i + 1] ? +args[i + 1] : d; };
const pos = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && args[i - 1].startsWith('--')));
if (pos.length < 2) { console.error('用法：node site/tools/source_shots.mjs <输入.json> <输出目录> [--total 180] [--page 25]'); process.exit(2); }
const [inFile, outDir] = pos.map(p => path.resolve(p));
const TOTAL = opt('--total', 180) * 1000, PAGE = opt('--page', 25) * 1000;
const VW = 1280, VH = 820, DPR = 2, DEBUG = args.includes('--debug');     // --debug：另存一张整屏截图，查截歪、截空时用
const items = (JSON.parse(fs.readFileSync(inFile, 'utf8')).items || []);
fs.mkdirSync(outDir, { recursive: true });

// 只点这一类：拒绝／仅必要（整句匹配，不是"包含"）
const REJECT = [
  /^(reject|decline|deny|refuse|disagree)( all)?( cookies| non-essential( cookies)?| optional( cookies)?| additional cookies| tracking)?$/,
  /^(i )?(do not|don't) (accept|agree|consent)$/,
  /^(use |allow |accept )?(only )?(strictly )?(necessary|essential|required|functional)( cookies)?( only)?$/,
  /^(continue|proceed) without (accepting|agreeing|consent(ing)?)$/,
  /^(拒绝|全部拒绝|拒绝全部|拒绝所有|拒绝非必要|不同意|仅必要|仅限必要|只用必要)(的)?(cookie|cookies|小型文本文件)?$/
];
const ACCEPT = /accept|agree|allow|consent|ok\b|got it|同意|接受|允许|好的/;     // 带这些字的，除非整句就是"仅必要"，一律不点
const SLOT_AR = { full: [1.5, 2.3], card: [2.8, 4.2], tick: [1.9, 3.4] };      // 各图位截图的宽高比范围（见文件头）
// 裁框里一律藏掉的"网页零件"（不含原句所在的那一层）
const CHROME = 'nav, aside, footer, form, dialog, [role="banner"], [role="navigation"], [role="complementary"], [role="contentinfo"], [role="dialog"], ' +
  '[aria-modal="true"], [class*="cookie" i], [id*="cookie" i], [class*="consent" i], [class*="newsletter" i], [class*="subscribe" i], [class*="promo" i], ' +
  '[class*="advert" i], [id*="advert" i], [class*="ad-slot" i], [class*="related" i], [class*="share" i], [class*="social" i], [class*="byline" i], ' +
  '[class*="author" i], [class*="breadcrumb" i], [class*="storystream" i], header';
const HIDE_CSS = `
#onetrust-consent-sdk, #onetrust-banner-sdk, .onetrust-pc-dark-filter, [id^="sp_message_container"], .sp_veil, .message-overlay,
#qc-cmp2-container, .qc-cmp2-container, .fc-consent-root, .fc-dialog-overlay, #CybotCookiebotDialog, #CybotCookiebotDialogBodyUnderlay,
#usercentrics-root, #didomi-host, .didomi-popup-backdrop, #truste-consent-track, .truste_box_overlay, #consent_blackbar, .osano-cm-window,
#cookie-banner, #cookie-consent, .cookie-banner, .cookie-consent, .cc-window, .cc-banner, .cookie-notice, #cookie-notice,
[aria-label*="cookie" i][role="dialog"], [aria-label*="consent" i][role="dialog"], [class*="CookieBanner"], [class*="cookieBanner"],
[data-testid*="cookie" i], [data-testid*="consent" i] { display: none !important; visibility: hidden !important; }
html, body { overflow: auto !important; overflow-y: auto !important; }
[data-fdhide] { visibility: hidden !important; }
[data-fdcrop] { visibility: hidden !important; opacity: 0 !important; }`;

const now = () => { const d = new Date(), p = n => String(n).padStart(2, '0'), o = -d.getTimezoneOffset();
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())} ${o >= 0 ? '+' : '-'}${p(Math.floor(Math.abs(o) / 60))}${p(Math.abs(o) % 60)}`; };

// ---------- 在页面里跑的几个函数（只读页面、比对文字、量位置；不点链接、不填表） ----------
function pageConsent(arg) {
  const [rej, acc] = arg, REJ = rej.map(s => new RegExp(s.slice(1, s.lastIndexOf('/')), s.slice(s.lastIndexOf('/') + 1) + 'i')), ACC = new RegExp(acc, 'i');
  const lab = e => (e.getAttribute('aria-label') || e.innerText || e.value || '').replace(/\s+/g, ' ').trim().replace(/[.!。！]+$/, '').toLowerCase();
  const els = [...document.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"], a[role="button"]')];
  for (const e of els) {
    const r = e.getBoundingClientRect(); if (!r.width || !r.height) continue;
    const t = lab(e); if (!t || t.length > 60) continue;
    const isRej = REJ.some(re => re.test(t));
    if (!isRej) continue;
    if (ACC.test(t) && !/necessary|essential|required|functional|仅必要|必要/.test(t)) continue;     // "Accept all" 之类：不点
    if (e.tagName === 'INPUT' && e.type === 'submit' && e.form && !/necessary|essential|reject|decline|拒绝|必要/.test(t)) continue;
    e.click();
    return t;
  }
  return null;
}

function pageBlocked() {
  // 只认整页的拦截：标题是验证页，或页面上有 Cloudflare 一类的验证表单，或正文很短又写着验证。
  // 文章页里给订阅表单用的 reCAPTCHA 小部件不算（11-06 试跑时 The Verge、CNBC 因为它被误判过）。
  const title = (document.title || '').toLowerCase(), body = document.body ? document.body.innerText : '';
  const challengeTitle = /just a moment|attention required|请稍候|稍等片刻|verify you are human|are you a robot|security check|安全验证|人机验证|访问验证/;
  if (challengeTitle.test(title) || document.querySelector('#challenge-form, #cf-challenge-running, #challenge-running, iframe[src*="challenges.cloudflare.com"]')
      || (body.length < 1500 && /captcha|verify you are human|checking your browser|请完成安全验证|人机验证/i.test(body)))
    return '人机验证或验证码（按规矩不处理）';
  if (/access denied|403 forbidden|request blocked/.test(title) || (body.length < 1500 && /access denied|you don't have permission to access/i.test(body)))
    return '网站拒绝访问（Access Denied）';
  return null;
}

// 网页自己写的发表日期（meta、JSON-LD、<time>）：只拿来和事件卡记的日期比对，出处签上的日期仍只写事件卡里的
function pageDate() {
  const got = [];
  for (const m of document.querySelectorAll('meta[property="article:published_time"], meta[name="article:published_time"], meta[itemprop="datePublished"], meta[name="pubdate"], meta[name="publish-date"], meta[name="parsely-pub-date"], meta[name="sailthru.date"]'))
    if (m.content) got.push(m.content);
  for (const sc of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { const j = JSON.parse(sc.textContent); const arr = Array.isArray(j) ? j : (j && j['@graph'] ? j['@graph'] : [j]);
      for (const x of arr) if (x && typeof x.datePublished === 'string') got.push(x.datePublished); } catch (e) { /* 不是合法 JSON 就算了 */ }
  }
  const t = document.querySelector('article time[datetime], main time[datetime], time[datetime]'); if (t) got.push(t.getAttribute('datetime'));
  const v = got.find(x => /^\d{4}-\d{2}-\d{2}/.test(String(x).trim()));
  return v ? String(v).trim().slice(0, 40) : null;
}

function pageWall() {
  const t = (document.body ? document.body.innerText.slice(0, 20000) : '').toLowerCase();
  return /subscribe to (continue|read|keep reading)|subscribers only|for subscribers|already a subscriber|sign in to (continue|read|keep reading)|log in to (continue|read)|create a free account to (continue|read)|this (article|story) is (for|exclusive to) (subscribers|members)|订阅后阅读|登录后阅读|开通会员/.test(t);
}

function pageFind(quote) {
  const N = c => {
    if (/[‘’‚‛′`´]/.test(c)) return "'";
    if (/[“”„‟″«»]/.test(c)) return '"';
    if (/[‐‑‒–—―−]/.test(c)) return '-';
    if (/[​‌‍⁠­﻿]/.test(c)) return '';
    if (/\s|[  -   　]/.test(c)) return ' ';
    const l = c.toLowerCase(); return l.length === 1 ? l : c;
  };
  const normStr = s => { let o = ''; for (const c of s) { const n = N(c); if (n === ' ' && (o === '' || o.endsWith(' '))) continue; o += n; } return o.trim(); };
  const blockOf = el => { let e = el; while (e && e !== document.body) { const d = getComputedStyle(e).display; if (!/^inline/.test(d) && d !== 'contents') return e; e = e.parentElement; } return document.body; };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode: n => {
      const p = n.parentElement; if (!p || !n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
      if (p.closest('script, style, noscript, template, svg, head, [aria-hidden="true"], [hidden]')) return NodeFilter.FILTER_REJECT;
      if (!p.getClientRects().length) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }
  });
  let hay = '', map = [], prevBlock = null, n;
  while ((n = walker.nextNode())) {
    const b = blockOf(n.parentElement);
    if (prevBlock && b !== prevBlock && hay && !hay.endsWith(' ')) { hay += ' '; map.push(null); }
    prevBlock = b;
    const s = n.nodeValue;
    for (let i = 0; i < s.length; i++) {
      const c = N(s[i]); if (!c) continue;
      if (c === ' ' && (hay === '' || hay.endsWith(' '))) continue;
      hay += c; map.push([n, i]);
    }
  }
  const needle0 = normStr(quote), tries = [[needle0, '整句']];
  const strip = needle0.replace(/[\s.,;:!?"'。，；：！？]+$/, '');
  if (strip !== needle0) tries.push([strip, '整句（去掉句末标点）']);
  for (const L of [120, 90, 70, 50, 36]) {
    if (strip.length <= L + 8) continue;
    let sub = strip.slice(0, L); const sp = sub.lastIndexOf(' '); if (sp > L * 0.7) sub = sub.slice(0, sp);
    tries.push([sub, '开头 ' + sub.length + ' 个字符']);
  }
  const inMain = node => !!(node.parentElement && node.parentElement.closest('article, main, [role="main"], .article, .post, .entry-content'));
  for (const [nd, how] of tries) {
    if (!nd) continue;
    const hits = []; let k = hay.indexOf(nd);
    while (k >= 0 && hits.length < 20) { hits.push(k); k = hay.indexOf(nd, k + 1); }
    if (!hits.length) continue;
    if (how.startsWith('开头') && hits.length > 1) continue;       // 只用开头一段时要唯一，才有区分度
    const k0 = hits.find(h => map[h] && inMain(map[h][0])) ?? hits[0];
    let a = k0, z = k0 + nd.length - 1;
    while (a <= z && !map[a]) a++; while (z >= a && !map[z]) z--;
    const r = document.createRange();
    r.setStart(map[a][0], map[a][1]); r.setEnd(map[z][0], map[z][1] + 1);
    window.__fdRange = r;
    return { how, len: nd.length, of: needle0.length, text: r.toString().replace(/\s+/g, ' ').trim() };
  }
  return null;
}

function pageMeasure() {
  const r = window.__fdRange; if (!r || !document.contains(r.startContainer)) return null;
  // 只量范围里的文字（逐个文字节点取小范围），不量整块元素的外框（11-06 试跑：标题整块的外框把四行并成了一行）
  const rs = [], root = r.commonAncestorContainer.nodeType === 1 ? r.commonAncestorContainer : r.commonAncestorContainer.parentElement;
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let n = r.startContainer.nodeType === 3 ? r.startContainer : w.nextNode();
  if (r.startContainer.nodeType === 3) w.currentNode = n;
  while (n) {
    if (r.intersectsNode(n)) {
      const sub = document.createRange();
      sub.setStart(n, n === r.startContainer ? r.startOffset : 0);
      sub.setEnd(n, n === r.endContainer ? r.endOffset : n.nodeValue.length);
      for (const q of sub.getClientRects()) if (q.width > 1 && q.height > 4) rs.push(q);
    }
    if (n === r.endContainer) break;
    n = w.nextNode();
  }
  rs.sort((a, b) => a.top - b.top || a.left - b.left);
  const lines = [];
  for (const q of rs) {
    const cy = (q.top + q.bottom) / 2;
    const L = lines.find(l => Math.abs((l.t + l.b) / 2 - cy) < Math.min(l.b - l.t, q.height) * 0.45);
    if (L) { L.l = Math.min(L.l, q.left); L.r = Math.max(L.r, q.right); L.t = Math.min(L.t, q.top); L.b = Math.max(L.b, q.bottom); }
    else lines.push({ l: q.left, r: q.right, t: q.top, b: q.bottom });
  }
  const start = r.startContainer.parentElement;
  const para = (start && start.closest('p, li, blockquote, h1, h2, h3, h4, figcaption, dd, td, div')) || start;
  const pr = para ? para.getBoundingClientRect() : null;
  const vis = q => q.width > 0 && q.height > 0 && q.bottom > 0 && q.top < innerHeight;
  const media = [...document.querySelectorAll('img, picture, video, iframe, canvas, figure, svg, [class*="ad-" i], [id*="ad-" i], [class*="advert" i]')]
    .filter(e => !e.closest('[data-fdhide]')).map(e => e.getBoundingClientRect())
    .filter(q => q.width > 80 && q.height > 60 && vis(q)).map(q => [q.left, q.top, q.right, q.bottom]);
  const text = [...document.querySelectorAll('p, li, h1, h2, h3, h4, blockquote, figcaption')]
    .filter(e => (e.innerText || '').trim().length > 20 && !e.closest('[data-fdhide]')).map(e => e.getBoundingClientRect())
    .filter(vis).map(q => [q.left, q.top, q.right, q.bottom]);
  return { lines, para: pr ? [pr.left, pr.top, pr.right, pr.bottom] : null, media, text, vw: innerWidth, vh: innerHeight };
}

function pageScrollTo(frac) {
  const r = window.__fdRange; if (!r) return;
  const q = r.getBoundingClientRect();
  window.scrollTo(0, Math.max(0, window.scrollY + q.top - innerHeight * frac));
}

function pageHideFixed() {
  // 盖在文字上的固定栏（顶栏、底部广告条、浮层）：只是不显示，不点
  const r = window.__fdRange, keep = r ? r.startContainer.parentElement : null; let n = 0;
  for (const e of document.querySelectorAll('body *')) {
    const st = getComputedStyle(e);
    if (st.position !== 'fixed' && st.position !== 'sticky') continue;
    if (e.hasAttribute('data-fdhide') || (keep && e.contains(keep))) continue;
    const q = e.getBoundingClientRect(); if (!q.width || !q.height) continue;
    // 吸顶（sticky）的只藏贴着画面上下沿、不太高的那种（导航栏、底部条）；版面里本来就用 sticky 排的正文不动
    if (st.position === 'sticky' && !((q.top < 90 || q.bottom > innerHeight - 90) && q.height < innerHeight * 0.4)) continue;
    e.setAttribute('data-fdhide', '1'); n++;
  }
  return n;
}

// ---------- 裁切（11-06 深夜改）：按整块元素裁，裁框里不属于正文的藏掉 ----------
// 在页面里跑：量原句、原句所在的段落 P、页面上每一块"看得见的东西"（文字行、图片和按钮、带底色或边框的盒子，按所属的块元素归组），
// 选出上下边都落在块与块之间的裁框，把裁框里不该有的藏掉（data-fdcrop，只是不显示）。返回裁框（视口坐标）和原句每一行的位置。
function pageCrop(arg) {
  const [aMin, aMax, chromeSel] = arg;
  const r = window.__fdRange; if (!r || !document.contains(r.startContainer)) return { err: '原句的位置丢了（页面重画过）' };
  const vw = innerWidth, vh = innerHeight;
  const vis = e => !e.checkVisibility || e.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true, opacityProperty: true, visibilityProperty: true });
  const inl = d => d === 'inline' || d === 'contents';     // inline-block / inline-flex（按钮、徽标）自成一块
  const blockOf = el => { let e = el; while (e && e !== document.body) { if (!inl(getComputedStyle(e).display)) return e; e = e.parentElement; } return document.body; };
  const startEl = r.startContainer.nodeType === 3 ? r.startContainer.parentElement : r.startContainer;
  const P = blockOf(startEl);
  const fs = parseFloat(getComputedStyle(startEl).fontSize) || 16;
  // 原句每一行（只量范围里的文字）
  const qr = [];
  { const root = r.commonAncestorContainer.nodeType === 1 ? r.commonAncestorContainer : r.commonAncestorContainer.parentElement;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT); let n = r.startContainer.nodeType === 3 ? r.startContainer : w.nextNode();
    if (r.startContainer.nodeType === 3) w.currentNode = n;
    while (n) {
      if (r.intersectsNode(n)) { const sub = document.createRange(); sub.setStart(n, n === r.startContainer ? r.startOffset : 0); sub.setEnd(n, n === r.endContainer ? r.endOffset : n.nodeValue.length);
        for (const q of sub.getClientRects()) if (q.width > 1 && q.height > 4) qr.push(q); }
      if (n === r.endContainer) break; n = w.nextNode();
    } }
  const lineUp = rs => { const out = []; rs.slice().sort((a, b) => a.top - b.top || a.left - b.left).forEach(q => {
    const cy = (q.top + q.bottom) / 2, L = out.find(l => Math.abs((l.t + l.b) / 2 - cy) < Math.min(l.b - l.t, q.height) * 0.45);
    if (L) { L.l = Math.min(L.l, q.left); L.r = Math.max(L.r, q.right); L.t = Math.min(L.t, q.top); L.b = Math.max(L.b, q.bottom); } else out.push({ l: q.left, r: q.right, t: q.top, b: q.bottom }); }); return out; };
  const QL = lineUp(qr); if (!QL.length) return { err: '量不到原句在页面上的位置' };
  const qT = Math.min(...QL.map(l => l.t)), qB = Math.max(...QL.map(l => l.b));
  // 页面上看得见的东西 → 按所属的块归组（units）
  const units = new Map(), band = q => q.bottom > -vh * 0.5 && q.top < vh * 1.5 && q.right > 0 && q.left < vw;
  const unitOf = (el, kind) => {
    let o = el; if (P.contains(o)) o = P;
    let u = units.get(o); if (!u) { u = { el: o, l: 1e9, t: 1e9, r: -1e9, b: -1e9, text: 0, junk: 0, lines: [] }; units.set(o, u); }
    if (kind === 'text') u.text++; else u.junk++;
    return u; };
  const add = (u, q) => { u.l = Math.min(u.l, q.left); u.r = Math.max(u.r, q.right); u.t = Math.min(u.t, q.top); u.b = Math.max(u.b, q.bottom); };
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let tn;
  while ((tn = tw.nextNode())) {
    const pe = tn.parentElement; if (!pe || !tn.nodeValue.trim() || pe.closest('script, style, noscript, template, [data-fdhide], [data-fdcrop]') || !vis(pe)) continue;
    const rg = document.createRange(); rg.selectNodeContents(tn);
    for (const q of rg.getClientRects()) { if (q.width <= 1 || q.height <= 2 || !band(q)) continue; const u = unitOf(blockOf(pe), 'text'); add(u, q); if (u.el === P) u.lines.push(q); }
  }
  const pageBg = (() => { for (let e = P; e; e = e.parentElement) { const c = getComputedStyle(e).backgroundColor; const m = c.match(/[\d.]+/g); if (m && (m.length < 4 || +m[3] > 0.05)) return c; } return 'rgb(255, 255, 255)'; })();
  for (const e of document.querySelectorAll('body *')) {
    if (e === P || e.contains(P) || e.closest('[data-fdhide], [data-fdcrop]')) continue;
    const q = e.getBoundingClientRect(); if (q.width < 4 || q.height < 4 || !band(q)) continue;
    const tag = e.tagName.toLowerCase();
    const media = /^(img|picture|video|canvas|iframe|embed|object|input|button|select|textarea|hr)$/.test(tag) || (tag === 'svg' && !e.parentElement.closest('svg')) || e.getAttribute('role') === 'img';
    let paint = false;
    if (!media && !(e instanceof SVGElement)) {
      const st = getComputedStyle(e), bg = st.backgroundColor, m = bg.match(/[\d.]+/g);
      paint = (m && (m.length < 4 || +m[3] > 0.05) && bg !== pageBg) || st.backgroundImage !== 'none' ||
        ['Top', 'Right', 'Bottom', 'Left'].some(sd => parseFloat(st['border' + sd + 'Width']) > 0.5 && st['border' + sd + 'Style'] !== 'none' && !/rgba\([^)]*,\s*0\)|transparent/.test(st['border' + sd + 'Color']));
    }
    if (!media && !paint) continue;
    if (!vis(e)) continue;
    const own = P.contains(e) ? P : (inl(getComputedStyle(e).display) && !media ? blockOf(e) : e);
    add(unitOf(own, P.contains(e) ? 'text' : 'junk'), q);
  }
  const U = [...units.values()].filter(u => u.r > u.l && !u.el.contains(P) || u.el === P);
  const Pu = units.get(P); if (!Pu) return { err: '量不到原句所在的段落' };
  U.forEach(u => { const ch = u.el !== P && u.el.closest(chromeSel); u.chrome = !!(ch && !ch.contains(P)); u.kind = u.el === P ? 'p' : (u.junk || u.chrome || !u.text ? 'junk' : 'text'); });
  // 能并进来的正文：和 P 在同一个容器里（P 往上第一层装着别的正文段落的元素），不是网页零件
  let C = P.parentElement; while (C && C !== document.body && !U.some(u => u.kind === 'text' && u.el !== P && C.contains(u.el))) C = C.parentElement;
  const cL = Math.min(Pu.l, ...QL.map(l => l.l)), cR = Math.max(Pu.r, ...QL.map(l => l.r));
  const mx = Math.max(18, fs * 1.0), my = Math.max(14, fs * 0.8), colL = Math.max(0, cL - mx), colR = Math.min(vw, cR + mx), W = colR - colL;
  const inCol = u => u.r > colL + 1 && u.l < colR - 1;
  const ar = h => W / (h + 2 * my);
  let w0 = Pu.t, w1 = Pu.b, edge = '整块', added = 0, padded = 0, cutT = null, cutB = null;
  if (ar(w1 - w0) < aMin) {         // 段落太长：裁在段内两行之间，原句那几行在中间
    const PL = lineUp(Pu.lines.map(q => ({ left: q.left, right: q.right, top: q.top, bottom: q.bottom, height: q.bottom - q.top })));
    let i0 = PL.findIndex(l => l.b > qT + 1), i1 = PL.length - 1 - [...PL].reverse().findIndex(l => l.t < qB - 1);
    if (i0 < 0) i0 = 0; if (i1 >= PL.length) i1 = PL.length - 1; if (i1 < i0) i1 = i0;
    for (;;) {
      const up = i0 > 0 ? ar(PL[i1].b - PL[i0 - 1].t) : -1, dn = i1 < PL.length - 1 ? ar(PL[i1 + 1].b - PL[i0].t) : -1;
      const qc = (qT + qB) / 2, offU = up >= aMin ? Math.abs(qc - (PL[i0 - 1].t + PL[i1].b) / 2) : 1e9, offD = dn >= aMin ? Math.abs(qc - (PL[i0].t + PL[i1 + 1].b) / 2) : 1e9;
      if (offU === 1e9 && offD === 1e9) break;
      if (offU <= offD) i0--; else i1++;
    }
    w0 = PL[i0].t; w1 = PL[i1].b; edge = '段内两行之间（原句那一段太长）';
    if (i0 > 0) cutT = (PL[i0 - 1].b + PL[i0].t) / 2;
    if (i1 < PL.length - 1) cutB = (PL[i1].b + PL[i1 + 1].t) / 2;
  } else {
    for (let guard = 0; guard < 12 && ar(w1 - w0) > aMax; guard++) {      // 不够扁：并进前后整段的正文
      const near = (dir) => {
        const cand = U.filter(u => u.kind === 'text' && inCol(u) && C && C.contains(u.el) && (dir < 0 ? u.b <= w0 + 1 : u.t >= w1 - 1))
          .sort((a, b) => dir < 0 ? b.b - a.b : a.t - b.t)[0];
        if (!cand) return null;
        const lo = dir < 0 ? cand.b : w1, hi = dir < 0 ? w0 : cand.t;      // 中间夹着网页零件就不并
        if (U.some(u => u.kind === 'junk' && inCol(u) && u.b > lo + 1 && u.t < hi - 1)) return null;
        return cand; };
      const a = near(-1), b = near(1), qc = (qT + qB) / 2;
      const opt = [a && [Math.min(w0, a.t), w1, a], b && [w0, Math.max(w1, b.b), b]].filter(x => x && ar(x[1] - x[0]) >= aMin);
      if (!opt.length) break;
      opt.sort((x, y) => Math.abs(qc - (x[0] + x[1]) / 2) / (x[1] - x[0]) - Math.abs(qc - (y[0] + y[1]) / 2) / (y[1] - y[0]));
      w0 = opt[0][0]; w1 = opt[0][1]; added++;
    }
    if (ar(w1 - w0) > aMax) {          // 还是太扁：上下留白（留白里的东西都藏掉）
      const need = W / aMax - 2 * my - (w1 - w0); padded = Math.round(need);
      let t = w0 - need / 2, b = w1 + need / 2;
      if (t - my < 0) { b += my - t; t = my; } if (b + my > vh) { t -= b + my - vh; b = vh - my; }
      w0 = Math.max(my, t); w1 = Math.min(vh - my, b);
    }
  }
  const y = Math.max(0, cutT != null ? cutT : w0 - my), y2 = Math.min(vh, cutB != null ? cutB : w1 + my), x = colL;
  if (y2 - y < 20) return { err: '裁框太小' };
  // 裁框里不属于这几段的一律藏掉；藏不掉的（装着要留的段落）记下来
  const keep = U.filter(u => u.kind === 'p' || (u.kind === 'text' && u.t >= w0 - 1 && u.b <= w1 + 1 && u.l >= x - 1 && u.r <= x + W + 1 && C && C.contains(u.el)));
  const over = u => Math.min(u.r, x + W) - Math.max(u.l, x) > 0.5 && Math.min(u.b, y2) - Math.max(u.t, y) > 0.5;
  let hidden = 0; const stuck = [];
  for (const u of U) {
    if (keep.includes(u) || !over(u)) continue;
    if (keep.some(k => u.el.contains(k.el))) { stuck.push(u.el.tagName.toLowerCase()); continue; }
    u.el.setAttribute('data-fdcrop', '1'); hidden++;
  }
  const clip = { x: Math.round(x), y: Math.round(y), w: Math.round(W), h: Math.round(y2 - y) };
  const lines = QL.filter(l => l.b > clip.y && l.t < clip.y + clip.h).map(l => [(l.l - clip.x) / clip.w, Math.max(0, l.t - clip.y) / clip.h,
    (Math.min(clip.x + clip.w, l.r) - Math.max(clip.x, l.l)) / clip.w, (Math.min(clip.y + clip.h, l.b) - Math.max(clip.y, l.t)) / clip.h]);
  return { clip, lines, font_px: Math.round(fs * 100) / 100, edge, added, padded, hidden, stuck, cut: qT < clip.y || qB > clip.y + clip.h };
}

// 裁边复查：裁框里看得见的东西（文字行、图片按钮、带底色边框的盒子）有没有被上下左右四条边切到（藏掉的不算）
function pageEdgeCheck(c) {
  const vis = e => !e.checkVisibility || e.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true, opacityProperty: true, visibilityProperty: true });
  const x0 = c.x, x1 = c.x + c.w, y0 = c.y, y1 = c.y + c.h, bad = [];
  const cross = (q, what) => {
    if (q.right <= x0 + 1 || q.left >= x1 - 1 || q.bottom <= y0 + 1 || q.top >= y1 - 1) return;
    const e = [q.top < y0 - 1 && '上', q.bottom > y1 + 1 && '下', q.left < x0 - 1 && '左', q.right > x1 + 1 && '右'].filter(Boolean);
    if (e.length) bad.push(what + '（' + e.join('') + '边）');
  };
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let tn;
  while ((tn = tw.nextNode()) && bad.length < 6) {
    const pe = tn.parentElement; if (!pe || !tn.nodeValue.trim() || pe.closest('script, style, noscript, template') || !vis(pe)) continue;
    const rg = document.createRange(); rg.selectNodeContents(tn);
    for (const q of rg.getClientRects()) if (q.width > 1 && q.height > 2) cross(q, '文字“' + tn.nodeValue.trim().slice(0, 24) + '”');
  }
  for (const e of document.querySelectorAll('img, picture, video, canvas, iframe, button, input, hr, svg')) {
    if (bad.length >= 6) break; if (e.tagName.toLowerCase() === 'svg' && e.parentElement.closest('svg')) continue;
    if (!vis(e)) continue; const q = e.getBoundingClientRect(); if (q.width > 4 && q.height > 4) cross(q, e.tagName.toLowerCase());
  }
  return bad;
}

// ---------- 截窗口（旧办法，11-06 晚；现在只在 pageCrop 量不到时不再用，留着对照）：16:9，以原句段落为中心，原句整句在里面，尽量避开图片 ----------
function pickClip(m) {
  const L = m.lines; if (!L.length) return null;
  const qL = Math.min(...L.map(l => l.l)), qR = Math.max(...L.map(l => l.r)), qT = Math.min(...L.map(l => l.t)), qB = Math.max(...L.map(l => l.b));
  const cL = Math.min(qL, m.para ? m.para[0] : qL), cR = Math.max(qR, m.para ? Math.min(m.para[2], m.vw) : qR);
  let W = Math.max(560, Math.min(1180, cR - cL + 2 * 56));
  const need = qB - qT + 2 * 28;
  if (W * 9 / 16 < need) W = Math.min(1180, need * 16 / 9);
  const H = Math.round(W * 9 / 16); W = Math.round(H * 16 / 9);
  const x = Math.round(Math.max(0, Math.min(m.vw - W, (cL + cR) / 2 - W / 2)));
  // 原句尽量落在窗口高度的 22%–78% 之间（推近时不贴边）；放不下再放宽到上下各留 28 像素
  let yMin = Math.max(0, qB - H * 0.78), yMax = Math.min(m.vh - H, qT - H * 0.22);
  if (yMax < yMin) { yMin = Math.max(0, qB + 28 - H); yMax = Math.min(m.vh - H, qT - 28); }
  const pref = (qT + qB) / 2 - H * 0.46;
  const cover = (list, y) => list.reduce((s, q) => s + Math.max(0, Math.min(q[2], x + W) - Math.max(q[0], x)) * Math.max(0, Math.min(q[3], y + H) - Math.max(q[1], y)), 0);
  const overlap = y => cover(m.media, y);
  // 挑窗口：图片（含广告位）越少越好、正文越多越好，原句尽量在中间偏上
  let best = null;
  if (yMax >= yMin) {
    for (let y = Math.floor(yMin); y <= yMax; y += 6) {
      const cost = overlap(y) + 0.25 * (W * H - cover(m.text || [], y)) + Math.abs(y - pref) * W * 0.35;
      if (!best || cost < best.cost) best = { y, cost };
    }
  }
  const y = best ? best.y : Math.max(0, Math.min(m.vh - H, Math.round(qT - 28)));
  const cut = qB > y + H || qT < y;
  const lines = L.filter(l => l.b > y && l.t < y + H).map(l => [l.l - x, Math.max(0, l.t - y), Math.min(W, l.r - x) - Math.max(0, l.l - x), Math.min(H, l.b - y) - Math.max(0, l.t - y)]);
  return { x, y: Math.round(y), w: W, h: H, lines, cut, media: Math.round(overlap(y) / (W * H) * 100) };
}

// ---------- 一项 ----------
async function shootOne(browser, it) {
  const slot = SLOT_AR[it.slot] ? it.slot : 'full';
  const rec = { id: it.id, url: it.url, source: it.source || '', date: it.date || '', quote: it.quote, slot, shot_at: now(), ok: false, reason: '', notes: [] };
  const ctx = await browser.newContext({ viewport: { width: VW, height: VH }, deviceScaleFactor: DPR, colorScheme: 'light', reducedMotion: 'reduce',
    serviceWorkers: 'block', acceptDownloads: false, permissions: [] });
  const p = await ctx.newPage();
  p.on('dialog', d => d.dismiss().catch(() => {}));                 // 网页弹出的对话框一律关掉
  await p.route('**/*', r => (['media'].includes(r.request().resourceType()) ? r.abort() : r.continue()));
  try {
    let resp = null;
    try { resp = await p.goto(it.url, { waitUntil: 'domcontentloaded', timeout: 15000 }); }
    catch (e) { rec.reason = '打不开网页（' + String(e.message).split('\n')[0].slice(0, 120) + '）'; return rec; }
    await p.waitForLoadState('load', { timeout: 6000 }).catch(() => {});
    await p.waitForTimeout(1500);
    rec.final_url = p.url(); rec.status = resp ? resp.status() : null; rec.title = (await p.title().catch(() => '')).slice(0, 200);
    const blocked = await p.evaluate(pageBlocked).catch(() => null);
    if (blocked) { rec.reason = blocked; return rec; }
    if (rec.status && rec.status >= 400) { rec.reason = 'HTTP ' + rec.status; return rec; }
    // Cookie／隐私弹窗：主页面和各个 iframe 里找"拒绝／仅必要"
    let clicked = null;
    for (const f of p.frames()) {
      clicked = await f.evaluate(pageConsent, [REJECT.map(String), ACCEPT.source]).catch(() => null);
      if (clicked) { rec.notes.push('隐私弹窗：点了「' + clicked + '」'); break; }
    }
    if (clicked) await p.waitForTimeout(2500);                      // 点完拒绝，有的网站会重画整页（CNBC），等它画完
    await p.addStyleTag({ content: HIDE_CSS }).catch(() => {});
    if (!clicked) rec.notes.push('隐私弹窗：没找到"拒绝／仅必要"按钮，用 CSS 藏起常见浮层（没点任何按钮）');
    // 找原句 → 滚到画面中上部 → 等懒加载 → 藏固定栏 → 再找一遍、量位置（页面中途重画过，旧的位置就作废，最多试三次）
    let found = null, m = null, clip = null, hidden = 0;
    for (let k = 0; k < 3 && !(clip && clip.lines.length); k++) {
      if (k) await p.waitForTimeout(1500);
      found = await p.evaluate(pageFind, it.quote).catch(e => ({ err: String(e.message).slice(0, 120) }));
      if (!found || found.err) continue;
      await p.evaluate(pageScrollTo, 0.4);
      await p.waitForTimeout(900);                                  // 等懒加载的图片、吸顶栏就位
      hidden += await p.evaluate(pageHideFixed).catch(() => 0);
      found = await p.evaluate(pageFind, it.quote).catch(e => ({ err: String(e.message).slice(0, 120) }));
      if (!found || found.err) continue;
      await p.evaluate(pageScrollTo, 0.4);
      await p.waitForTimeout(500);
      m = await p.evaluate(pageCrop, [...SLOT_AR[slot], CHROME]).catch(e => ({ err: String(e.message).split('\n')[0].slice(0, 160) }));
      clip = m && !m.err && m.lines && m.lines.length ? m : null;
    }
    if (!found || found.err) {
      const wall = await p.evaluate(pageWall).catch(() => false);
      rec.reason = wall ? '付费墙或登录墙（页面上没有原句，按规矩不登录）' : '找不到原句' + (found && found.err ? '（' + found.err + '）' : '');
      return rec;
    }
    rec.match = found.how; rec.found_text = found.text;
    rec.page_date = await p.evaluate(pageDate).catch(() => null);
    if (hidden) rec.notes.push('藏起 ' + hidden + ' 个固定栏或浮层（只是不显示）');
    if (!clip || !clip.lines.length) { rec.reason = '找到原句但量不到它在页面上的位置' + (m && m.err ? '（' + m.err + '）' : '（可能被折叠或藏起来了）'); return rec; }
    const C = clip.clip;
    rec.font_px = clip.font_px; rec.edge = clip.edge;
    rec.crop = { 并进整段: clip.added, 上下留白: clip.padded, 藏起: clip.hidden, 藏不掉: clip.stuck };
    if (clip.hidden) rec.notes.push('裁框里藏起 ' + clip.hidden + ' 块不属于正文的东西（只是不显示）');
    await p.waitForTimeout(200);
    const cutBy = await p.evaluate(pageEdgeCheck, C).catch(e => ['复查出错：' + String(e.message).slice(0, 80)]);
    if (DEBUG) await p.screenshot({ path: path.join(outDir, it.id + '_debug_viewport.png') }).catch(() => {});
    if (cutBy.length) { rec.reason = '裁不干净：裁边切到 ' + cutBy.join('、') + '（按规矩不用，退回原句摘录）'; rec.clip = C; return rec; }
    if (clip.cut) { rec.reason = '原句太长，一张截图装不下（退回原句摘录）'; rec.clip = C; return rec; }
    const png = path.join(outDir, it.id + '.png');
    await p.screenshot({ path: png, clip: { x: C.x, y: C.y, width: C.w, height: C.h }, animations: 'disabled', caret: 'hide' });
    rec.ok = true; rec.reason = '';
    rec.png = path.basename(png); rec.dpr = DPR; rec.clip = C;
    rec.w = C.w * DPR; rec.h = C.h * DPR;
    rec.lines = clip.lines.map(l => l.map(v => Math.round(v * 10000) / 10000));
    return rec;
  } finally {
    await ctx.close().catch(() => {});
  }
}

const { chromium } = await import(pathToFileURL(PW).href);
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const t0 = Date.now(), out = [];
try {
  for (const it of items) {
    let rec;
    if (!it || !it.id || !/^[a-z0-9_]+$/i.test(it.id) || !/^https?:\/\//.test(it.url || '') || !it.quote) {
      rec = { id: (it && it.id) || '?', url: (it && it.url) || '', ok: false, reason: '输入不全（要 id、http(s) 网址、原句）', shot_at: now(), notes: [] };
    } else if (Date.now() - t0 > TOTAL) {
      rec = { id: it.id, url: it.url, ok: false, reason: '跳过：全期截图总时长到上限（' + TOTAL / 1000 + ' 秒）', shot_at: now(), notes: [] };
    } else {
      let timer;
      rec = await Promise.race([shootOne(browser, it), new Promise(res => { timer = setTimeout(() => res({ id: it.id, url: it.url, ok: false, reason: '超时（单页 ' + PAGE / 1000 + ' 秒）', shot_at: now(), notes: [] }), PAGE); })]);
      clearTimeout(timer);
    }
    rec.source = rec.source || (it && it.source) || ''; rec.date = rec.date || (it && it.date) || ''; rec.quote = rec.quote || (it && it.quote) || '';
    rec.sec = Math.round((Date.now() - t0) / 100) / 10;
    if (!rec.ok) { try { fs.rmSync(path.join(outDir, rec.id + '.png'), { force: true }); } catch (e) { /* 没有就算了 */ } }
    fs.writeFileSync(path.join(outDir, rec.id + '.json'), JSON.stringify(rec, null, 1));
    out.push(rec);
    console.log((rec.ok ? '成功 ' : '失败 ') + rec.id + '  ' + (rec.ok ? (rec.match + (rec.notes.length ? '；' + rec.notes.join('；') : '')) : rec.reason) + '  ' + rec.url);
  }
} finally {
  await browser.close();
}
fs.writeFileSync(path.join(outDir, '清单.json'), JSON.stringify({ 说明: '原文截图（site/tools/source_shots.mjs）', 生成: now(), items: out }, null, 1));
console.log('原文截图：成功 ' + out.filter(r => r.ok).length + ' / ' + out.length + '，用时 ' + Math.round((Date.now() - t0) / 1000) + ' 秒 → ' + outDir);
