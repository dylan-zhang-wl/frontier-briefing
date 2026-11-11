// 每日AI科技前沿简报网站的 Cloudflare Worker：网址 https://wenlongzhang.com/frontier/ ，不设口令，但不让搜索引擎收录。
// 照期刊网站 journals-observatory（期刊监控仓库 site/deploy/src/index.js）的写法（站长钥匙和访问统计 11-10 照那边加上，见本文件开头最后两条）。
//
// · 网址：wrangler.toml 的 routes 只截 wenlongzhang.com/frontier 与 /frontier/*；主域名其余部分（知识库、/memory、/journals）不受影响。
//   万一有别的路径被路由进来，一律 404，不处理。
// · 文件：上线包（cloud/deploy/assemble.py 做的）是 Worker 自带的静态文件，目录结构就是 frontier/…，网址路径与文件路径一一对应。
//   /frontier 跳到 /frontier/（页面里的地址都是相对的，要以 / 结尾才对）；以 / 结尾的目录请求给该目录的 index.html。
// · 每期的网址：网页本身是一页，按 ?date=YYYY-MM-DD 换期（site/v3/app.js 原有的做法）。
//   好记的写法 /frontier/2026-11-09/ 跳到 /frontier/?date=2026-11-09（不能直接在那个目录里放网页：页面里的相对地址会错位）。
// · 只许 GET、HEAD（只能看，不能改）。例外只有三个 POST：/frontier/feedback（读者反馈，11-10 加，见下面“读者反馈”一节）、
//   /frontier/_enter（输访问口令）和 /frontier/_access（站长设置页），后两个是“开放程度”（11-10 加，见本文件开头最后一条和 src/access.js）。
// · 所有响应都加：X-Robots-Tag: noindex, nofollow（不收录、不顺着链接爬；页面里另有同样的 meta 标签）、
//   Referrer-Policy: same-origin（点外链时不把本站网址告诉对方）、X-Content-Type-Options: nosniff（浏览器严格按类型处理文件）。
// · 浏览器缓存分两类：
//   - 网页（html、目录）和往期目录 issues/index.js：每次向服务器核对（没变时只回“没变”，很快）；
//   - 每期的音频、图片、字体（issues/日期/audio|img|fonts|video/）：7 天，内容不变；
//   - 其余：每期数据 issue.js 等、程序 css/js、vendor 10 分钟（文件名不带版本号，缓存太久会“新页面配旧程序”）。
// · 音频拖动：Cloudflare 的静态文件不认 Range 请求头，总是回整段文件（200）。苹果手机的 Safari 放音频要靠 Range，
//   所以 .mp3 等媒体文件由这里按 Range 截出那一段，回 206。
//   出处：https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/
// · 不开 *.workers.dev 地址。
// · 站长钥匙（11-10 加）：任一页面加 ?k=<钥匙> 时核对钥匙的 SHA-256 指纹（机密变量 STATS_KEY_HASH），对了就发一张一年的站长 Cookie
//   （fd_pass，值就是指纹，只在 /frontier 下有效）并跳回不带钥匙的网址；不对就照常显示页面（不提示）。站长 Cookie 的用处：
//   打开访问统计页 /frontier/_visits；站长自己的访问不计入统计。没设指纹（或设的不是 64 位十六进制）时谁都不是站长。
// · 匿名访问统计（11-10 加，src/visits.js）：打开页面、开始听播客、开始看视频在后台写进 D1 数据库（绑定 VISITS），不拖慢页面和音频，
//   写库失败也不影响；统计页（src/stats.js）只有带有效站长 Cookie 的浏览器能看，其他人看到和普通“没有这个页面”一样的 404。
//   不用定时任务：400 天以前的记录在写入时顺手删（见 visits.js），站长打开统计页时也删一次。
// · 开放程度（11-10 加，src/access.js）：站长在设置页 /frontier/_access 切三档——公开（和以前一样）／凭口令（别人先输访问口令）／
//   只有我（别人只看到“测试中”）。状态存在 D1 的 site_settings 表（不在代码里，所以每天自动发布 Worker 不会把它改回去）。
//   顺序：?k= 站长登录 → /frontier 跳 /frontier/ 这类纯跳转 → 统计页、设置页（只认站长，别人 404）→ 门 → 静态文件。
//   门挡下的请求一律回门页（403，no-store），不去取静态文件；放行的回应在非公开档把 Cache-Control 的 public 换成 private。
//   表不存在或没设过 → 公开，和加这个功能以前一模一样。

import { shouldRecord, recordVisit, shouldRecordPlay, recordPlay, cleanupVisits } from './visits.js';
import { statsResponse } from './stats.js';
import { ACCESS_PATH, ENTER_PATH, decide, privatize, gatePage, nextOf, handleEnter, accessGet, accessPost, sha256hex, same, cookieValue } from './access.js';

const PREFIX = '/frontier';
const STATS_PATH = PREFIX + '/_visits';
const PASS_COOKIE = 'fd_pass';
const BASE_HEADERS = {
  'X-Robots-Tag': 'noindex, nofollow',
  'Referrer-Policy': 'same-origin',
  'X-Content-Type-Options': 'nosniff',
};
export const CACHE = {
  html: 'no-cache',
  media: 'public, max-age=604800',
  code: 'public, max-age=600',
  other: 'public, max-age=600',
  redirect: 'public, max-age=3600',
  error: 'no-store',
};
const MEDIA_RE = /\.(mp3|m4a|aac|wav|ogg|oga|opus|mp4|webm)$/i;
const DATE_RE = /^\/frontier\/(\d{4}-\d{2}-\d{2})\/?$/;

export function cacheFor(path) {
  if (path.endsWith('/') || /\.html?$/i.test(path)) return CACHE.html;
  if (path === PREFIX + '/issues/index.js') return CACHE.html;
  if (/^\/frontier\/issues\/\d{4}-\d{2}-\d{2}\/(audio|img|fonts|video)\//.test(path)) return CACHE.media;
  if (/\.(css|js|mjs|json)$/i.test(path)) return CACHE.code;
  return CACHE.other;
}

function withBase(headers) {
  for (const [k, v] of Object.entries(BASE_HEADERS)) headers.set(k, v);
  return headers;
}

function plain(status, text, extra = {}) {
  const h = withBase(new Headers({ 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': CACHE.error, ...extra }));
  return new Response(text, { status, headers: h });
}

function redirect(status, location) {
  return new Response(null, { status, headers: withBase(new Headers({ Location: location, 'Cache-Control': CACHE.redirect })) });
}

const NOT_FOUND = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex, nofollow"><meta name="color-scheme" content="light dark"><link rel="icon" href="data:,"><title>没有这个页面</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f5f5f7;color:#1d1d1f;font:16px/1.9 -apple-system,'PingFang SC',sans-serif;text-align:center}
a{color:#0062c4}@media (prefers-color-scheme:dark){body{background:#0a0a0c;color:#f5f5f7}a{color:#4ea1ff}}</style>
<div style="padding:24px">没有这个页面。<br><a href="/frontier/">回到每日AI科技前沿简报</a></div>`;

function notFound(method) {
  const h = withBase(new Headers({ 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': CACHE.error }));
  return new Response(method === 'HEAD' ? null : NOT_FOUND, { status: 404, headers: h });
}

// 解析 Range: bytes=起-止（只认一段；多段或写法不对返回 null＝照常回整段）。超出文件返回 'bad'（416）。
export function parseRange(header, size) {
  const m = /^bytes=(\d*)-(\d*)$/.exec(String(header || '').trim());
  if (!m || (m[1] === '' && m[2] === '')) return null;
  let start, end;
  if (m[1] === '') {
    const n = Number(m[2]);
    if (n === 0) return 'bad';
    start = Math.max(0, size - n);
    end = size - 1;
  } else {
    start = Number(m[1]);
    end = m[2] === '' ? size - 1 : Math.min(Number(m[2]), size - 1);
  }
  if (!Number.isFinite(start) || !Number.isFinite(end) || start >= size || start > end) return 'bad';
  return { start, end };
}

// 从整段文件的流里只放出 [start, end] 这一段（不把整个文件读进内存）
export function sliceStream(body, start, end) {
  const reader = body.getReader();
  let pos = 0;
  let left = end - start + 1;
  return new ReadableStream({
    async pull(ctrl) {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) { ctrl.close(); return; }
        const from = pos;
        pos += value.byteLength;
        if (pos <= start) continue;
        const a = Math.max(0, start - from);
        const b = Math.min(value.byteLength, a + left);
        if (b > a) { ctrl.enqueue(value.subarray(a, b)); left -= b - a; }
        if (left <= 0) { ctrl.close(); reader.cancel().catch(() => {}); }
        return;
      }
    },
    cancel(reason) { return reader.cancel(reason); },
  });
}

// 返回 206／416 的回应；返回 null 表示照常回整段（这时 res.body 没动过）。
// 11-09 晚上线后发现：线上静态文件的回应不带 Content-Length（https://github.com/cloudflare/workers-sdk/issues/8967），
// 本机测试的假对象带着，所以没测出来，上线后带 Range 也回 200 整段。不带长度时先把整个文件读进来再截
// （每期播客最大约 7 MB，Workers 内存 128 MB；读文件是等网络，不怎么占 CPU 时间）。
async function rangeResponse(req, res, h) {
  const ifRange = req.headers.get('If-Range');
  if (ifRange && ifRange !== res.headers.get('ETag')) return null;
  let size = Number(res.headers.get('Content-Length'));
  let buf = null;
  if (!(Number.isFinite(size) && size > 0)) {
    if (req.method === 'HEAD' || !res.body) return null;
    buf = new Uint8Array(await res.arrayBuffer());
    size = buf.byteLength;
  }
  const r = size > 0 ? parseRange(req.headers.get('Range'), size) : null;
  if (r === null) {
    if (!buf) return null;
    h.set('Content-Length', String(size));            // 读进来了就自己回整段（res.body 已经用掉）
    return new Response(buf, { status: 200, headers: h });
  }
  if (r === 'bad') {
    if (!buf && res.body) res.body.cancel().catch(() => {});
    h.set('Content-Range', `bytes */${size}`);
    h.set('Cache-Control', CACHE.error);
    h.delete('Content-Length');
    return new Response(null, { status: 416, headers: h });
  }
  h.set('Content-Range', `bytes ${r.start}-${r.end}/${size}`);
  h.set('Content-Length', String(r.end - r.start + 1));
  if (req.method === 'HEAD' || !(buf || res.body)) return new Response(null, { status: 206, headers: h });
  const body = buf ? buf.slice(r.start, r.end + 1) : sliceStream(res.body, r.start, r.end);
  return new Response(body, { status: 206, headers: h });
}

// ===================== 站长钥匙（11-10 加，照期刊网站）=====================
// sha256hex、cookieValue、逐字比较 same()（两个字符串是否相同，逐字比完、不因为早早对不上就提前返回）
// 11-10 加开放程度时挪进了 src/access.js，访问口令、口令 Cookie 也用它们；这里从那边引入，写法一字没改。

// 机密变量 STATS_KEY_HASH：钥匙的 SHA-256 指纹（64 位十六进制）。没设或格式不对返回 ''（谁都不是站长，统计页一律 404）
function wantHash(env) {
  const h = String((env && env.STATS_KEY_HASH) || '').trim().toLowerCase();
  return /^[0-9a-f]{64}$/.test(h) ? h : '';
}

// 带有效站长 Cookie（值等于钥匙指纹）
function isOwner(req, env) {
  const want = wantHash(env);
  return !!want && same(cookieValue(req, PASS_COOKIE), want);
}

// ?k=<钥匙>：对了就发站长 Cookie 并跳回不带钥匙的网址；不对或没带返回 null（照常处理，不提示）
async function keyLogin(req, url, env) {
  if (req.method !== 'GET' || !url.searchParams.has('k')) return null;
  const want = wantHash(env);
  const k = url.searchParams.get('k') || '';
  if (!want || !k || k.length > 512 || !same(await sha256hex(k), want)) return null;
  url.searchParams.delete('k');
  const path = url.pathname === PREFIX ? PREFIX + '/' : url.pathname;
  const h = withBase(new Headers({ Location: path + url.search, 'Cache-Control': CACHE.error }));
  h.append('Set-Cookie', `${PASS_COOKIE}=${want}; Path=${PREFIX}; Max-Age=31536000; HttpOnly; Secure; SameSite=Lax`);
  return new Response(null, { status: 302, headers: h });
}

// ===================== 读者反馈（11-10 加）=====================
// 页面底部“反馈”框（site/v3/app.js 的“读者反馈”一节）把一条反馈 POST 到 /frontier/feedback（JSON）。这里只做三件事：
//   1. 校验：Origin 必须是 https://wenlongzhang.com；只收 application/json、不超过 8 KB；期号是 YYYY-MM-DD；
//      “哪里不对”必填、最多 1000 字；称呼最多 40 字、位置最多 80 字；去掉看不见的控制字符。
//      蜜罐栏 website（页面上看不到的输入框）有值就当机器人：照样回“收到”，但不转交。
//   2. 限流：按访问者 IP（Cloudflare 给的 CF-Connecting-IP），同一个 Worker 实例的内存里记，10 分钟内最多 5 次。
//      实例会换、会有好几个，所以这只是挡住手抖连点和简单的刷屏；真正的上限在 GitHub 那边（.github/workflows/feedback.yml 每天最多建 30 条）。
//   3. 转交：用机密变量 GH_FEEDBACK_TOKEN（和仓库 Secret GH_DISPATCH_TOKEN 同一个值，由 .github/workflows/feedback-setup.yml 写进来）
//      调 GitHub 接口，触发本仓库的流程 feedback.yml（workflow_dispatch），各栏作为 inputs 传过去；那个流程建 Issue、做自动初看。
//      没有这个机密变量就回 503“反馈功能还没设置好”。日志只记状态码，不记令牌、不记反馈内容。
// 回应都是 JSON：{ ok: true } 或 { ok: false, error: 中文说明, error_en: 英文说明 }，不缓存。说明见 cloud/feedback/README.md。
export const FEEDBACK_PATH = PREFIX + '/feedback';
export const FEEDBACK_ORIGIN = 'https://wenlongzhang.com';
export const FEEDBACK_REPO = 'dylan-zhang-wl/frontier-daily';
export const FEEDBACK_WORKFLOW = 'feedback.yml';
export const FEEDBACK_LIMITS = { body: 8192, text: 1000, name: 40, where: 80 };
export const RATE = { windowMs: 10 * 60 * 1000, max: 5, seen: new Map() };

function json(status, data, extra = {}) {
  const h = withBase(new Headers({ 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': CACHE.error, ...extra }));
  return new Response(JSON.stringify(data), { status, headers: h });
}
const fbErr = (status, zh, en, extra) => json(status, { ok: false, error: zh, error_en: en }, extra);

// 去掉控制字符（保留换行和制表），统一换行，去掉首尾空白；按“字”（码点）数长度
function clean(v, multiline) {
  let s = typeof v === 'string' ? v : '';
  s = s.replace(/\r\n?/g, '\n');
  if (multiline) s = s.replace(/[\u0000-\u0008\u000B-\u001F\u007F]/g, '');            // 多行（哪里不对）：留换行和制表
  else s = s.replace(/[\u0000-\u001F\u007F]+/g, ' ').replace(/ {2,}/g, ' ');           // 单行（称呼、位置）：换行等换成一个空格
  s = s.replace(/[\u200B-\u200F\u202A-\u202E\u2060-\u2064\uFEFF]/g, '');     // 看不见的方向符、零宽字符
  return s.trim();
}
const chars = (s) => Array.from(s).length;

// 校验反馈。返回 { ok: true, data } 或 { ok: false, zh, en }。data 里都是字符串（GitHub 接口要的 inputs 就是字符串）。
export function validateFeedback(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return { ok: false, zh: '格式不对', en: 'Malformed request' };
  const date = typeof body.date === 'string' ? body.date.trim() : '';
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  const d = m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])) : null;
  if (!m || !d || d.getUTCMonth() !== +m[2] - 1 || d.getUTCDate() !== +m[3] || +m[1] < 2026 || +m[1] > 2100) {
    return { ok: false, zh: '期号不对', en: 'Bad issue date' };
  }
  const text = clean(body.text, true);
  const name = clean(body.name, false);
  const where = clean(body.where, false);
  if (!text) return { ok: false, zh: '先写一下哪里不对。', en: 'Please say what’s wrong first.' };
  if (chars(text) > FEEDBACK_LIMITS.text) return { ok: false, zh: `内容太长了，最多 ${FEEDBACK_LIMITS.text} 字。`, en: `Too long: ${FEEDBACK_LIMITS.text} characters at most.` };
  if (chars(name) > FEEDBACK_LIMITS.name) return { ok: false, zh: `称呼太长了，最多 ${FEEDBACK_LIMITS.name} 字。`, en: `Name too long: ${FEEDBACK_LIMITS.name} characters at most.` };
  if (chars(where) > FEEDBACK_LIMITS.where) return { ok: false, zh: `位置写得太长了，最多 ${FEEDBACK_LIMITS.where} 字。`, en: `Location too long: ${FEEDBACK_LIMITS.where} characters at most.` };
  const lang = body.lang === 'en' ? 'en' : 'zh';
  return { ok: true, data: { date, text, name, where, lang } };
}

// 同一实例内存里的简单限流：每个 IP 在 windowMs 内最多 max 次。返回 true＝放行
export function rateOk(ip, now = Date.now()) {
  const key = ip || 'unknown';
  const list = (RATE.seen.get(key) || []).filter((t) => now - t < RATE.windowMs);
  if (list.length >= RATE.max) { RATE.seen.set(key, list); return false; }
  list.push(now);
  RATE.seen.set(key, list);
  if (RATE.seen.size > 2000) {                       // 别让表无限长：清掉都过期的
    for (const [k, v] of RATE.seen) if (!v.some((t) => now - t < RATE.windowMs)) RATE.seen.delete(k);
  }
  return true;
}

async function handleFeedback(req, env) {
  if (req.headers.get('Origin') !== FEEDBACK_ORIGIN) return fbErr(403, '只能从网站页面提交', 'Only accepted from the website');
  const token = env && typeof env.GH_FEEDBACK_TOKEN === 'string' ? env.GH_FEEDBACK_TOKEN.trim() : '';
  if (!token) {
    console.log('反馈：没有机密变量 GH_FEEDBACK_TOKEN，回 503');
    return fbErr(503, '反馈功能还没设置好，请稍后再试。', 'Feedback isn’t set up yet. Please try again later.');
  }
  const type = (req.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase();
  if (type !== 'application/json') return fbErr(415, '只收 JSON', 'JSON only');
  const len = Number(req.headers.get('Content-Length'));
  if (Number.isFinite(len) && len > FEEDBACK_LIMITS.body) return fbErr(413, '内容太长了', 'Too large');
  if (!rateOk(req.headers.get('CF-Connecting-IP'))) {
    return fbErr(429, '提交得有点频繁，请过几分钟再试。', 'Too many in a row. Please wait a few minutes.', { 'Retry-After': '600' });
  }
  let raw;
  try { raw = await req.text(); } catch { return fbErr(400, '没读到内容', 'Could not read the request'); }
  if (new TextEncoder().encode(raw).byteLength > FEEDBACK_LIMITS.body) return fbErr(413, '内容太长了', 'Too large');
  let body;
  try { body = JSON.parse(raw); } catch { return fbErr(400, '格式不对', 'Malformed request'); }
  if (body && typeof body === 'object' && typeof body.website === 'string' && body.website.trim()) {
    console.log('反馈：蜜罐栏有值，当机器人，不转交');
    return json(202, { ok: true });
  }
  const v = validateFeedback(body);
  if (!v.ok) return fbErr(400, v.zh, v.en);

  const url = `https://api.github.com/repos/${FEEDBACK_REPO}/actions/workflows/${FEEDBACK_WORKFLOW}/dispatches`;
  let res;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'frontier-daily-feedback (Cloudflare Worker)', 'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ref: 'main', inputs: v.data }),
    });
  } catch (e) {
    console.log(`反馈：连不上 GitHub（${String((e && e.name) || 'error')}）`);
    return fbErr(502, '暂时没能提交，请稍后再试。', 'Couldn’t send just now. Please try again later.');
  }
  console.log(`反馈：转交 GitHub，状态码 ${res.status}`);
  if (res.status === 204 || res.status === 200) return json(202, { ok: true });
  return fbErr(502, '暂时没能提交，请稍后再试。', 'Couldn’t send just now. Please try again later.');
}

// 站长专用页（统计页、设置页）的写法：没有站长 Cookie 的、或者写法不是这一页本身（多了 /、.csv 之类）的，一律当作“没有这个页面”
const ownerPage = (path, page) => path === page || path.startsWith(page + '/') || path.startsWith(page + '.');

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const path = url.pathname;
    if (path !== PREFIX && !path.startsWith(PREFIX + '/')) return plain(404, 'not found');
    if (req.method === 'POST' && path === FEEDBACK_PATH) {
      // 开放程度：不放行的人提交反馈回 403（站长、公开档、带对口令 Cookie 的照常）
      const gate = await decide(req, env, isOwner(req, env));
      if (!gate.allow && gate.page === 'error') return fbErr(503, '网站暂时打不开，请过一会儿再试。', 'The site can’t be reached right now. Please try again later.');
      if (!gate.allow) return fbErr(403, '网站暂未开放', 'The site isn’t open yet');
      return handleFeedback(req, env);
    }
    if (req.method === 'POST' && path === ENTER_PATH) return handleEnter(req, env, isOwner(req, env));     // 输访问口令
    if (req.method === 'POST' && path === ACCESS_PATH) {                                                  // 站长设置页提交
      if (!isOwner(req, env)) return notFound('POST');
      return accessPost(req, env);
    }
    if (req.method !== 'GET' && req.method !== 'HEAD') return plain(405, '只能看，不能改', { Allow: 'GET, HEAD' });
    const login = await keyLogin(req, url, env);
    if (login) return login;
    const owner = isOwner(req, env);
    if (path === PREFIX) return redirect(301, PREFIX + '/' + url.search);
    if (path === PREFIX + '/past') return redirect(301, PREFIX + '/past/' + url.search);
    const d = DATE_RE.exec(path);
    if (d) return redirect(302, PREFIX + '/?date=' + d[1]);
    // 访问统计页：没有站长 Cookie 的一律当作“没有这个页面”（不暴露这一页存在）
    if (ownerPage(path, STATS_PATH)) {
      if (!owner || path !== STATS_PATH) return notFound(req.method);
      if (env && env.VISITS && ctx && typeof ctx.waitUntil === 'function') ctx.waitUntil(cleanupVisits(env.VISITS));
      return statsResponse(req, url, env);
    }
    // 开放程度设置页：同上，只认站长
    if (ownerPage(path, ACCESS_PATH)) {
      if (!owner || path !== ACCESS_PATH) return notFound(req.method);
      return accessGet(req, env);
    }

    // 门：这一档不放行的，回门页（不去取静态文件、不记访问）
    const gate = await decide(req, env, owner);
    if (!gate.allow) return gatePage(req.method, gate.page, { next: nextOf(url) });

    const assetPath = path.endsWith('/') ? path + 'index.html' : path;
    const fwd = new Headers(req.headers);
    fwd.delete('Range');
    fwd.delete('If-Range');
    const res = await env.ASSETS.fetch(new Request(new URL(assetPath, url.origin), { method: req.method, headers: fwd }));
    if (res.status === 404) return notFound(req.method);

    const h = withBase(new Headers(res.headers));
    if (res.status >= 200 && res.status < 400) h.set('Cache-Control', cacheFor(path));
    else h.set('Cache-Control', CACHE.error);
    if (gate.private) h.set('Cache-Control', privatize(h.get('Cache-Control')));   // 非公开档：别让中间的共享缓存存一份
    if (MEDIA_RE.test(path) && res.status === 200) {
      h.set('Accept-Ranges', 'bytes');
      if (req.headers.has('Range')) {
        const partial = await rangeResponse(req, res, h);
        if (partial) {
          if (shouldRecordPlay(req, url, partial.status, owner, env)) recordPlay(req, url, env, ctx);
          return partial;
        }
      }
      if (shouldRecordPlay(req, url, res.status, owner, env)) recordPlay(req, url, env, ctx);
    }
    if (shouldRecord(req, url, res.status, owner, env)) recordVisit(req, url, h, env, ctx);
    return new Response(req.method === 'HEAD' ? null : res.body, { status: res.status, statusText: res.statusText, headers: h });
  },
};
