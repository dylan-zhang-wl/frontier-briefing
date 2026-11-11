// 匿名访问统计（11-10 加，照期刊网站 journals-observatory 的 site/deploy/src/visits.js）：判断一次请求要不要记、记哪些字段，
// 写进 D1 数据库（绑定名 VISITS）。表结构见 migrations/0001_visits.sql。
//
// · 记三种：
//   - page   打开页面：GET /frontier/（带不带 ?date= 都算）、/frontier/past/，状态 200 或 304（304 = 页面没变、浏览器用自己存的那份，
//            回头客再打开时多半是 304，也算一次）。期号从 ?date= 取；不带期号（或期号不存在）的记成当时的最新一期，另标 latest = 1。
//   - listen 开始听：GET 某期的 audio/podcast.mp3；
//   - watch  开始看：GET 某期的 audio/video3.mp3（视频旁白）。
//   后两种只在“从头要”的那一次记：不带 Range，或 Range 从第 0 个字节开始（Safari 先要头 2 个字节 bytes=0-1 探一下，这一下不算）；
//   拖动进度条（Range 从中间开始）不记。同一访客同一期 30 分钟内只记一次（Safari 探完还会再从 0 要一次）。状态 200 或 206 才记。
// · 不记：数据、程序、字体、图片等其他文件；HEAD；爬虫与自动程序（浏览器标识里有 bot、spider、curl、python 等，或 Cloudflare 认定的已知机器人）；
//   浏览器的预取请求；站长本人（带有效 fd_pass Cookie 的浏览器）。
// · 不存 IP 地址、不存完整的浏览器标识、不存完整的来源网址（只存主机名）。
// · 访客编号：浏览器第一次打开页面时发一个随机编号（Cookie fd_vid，一年，只在 /frontier 下有效），用来区分新访客与回头客；
//   编号和人没有任何对应关系。音频请求不发编号，带着就记，没带就记空。
// · 写库放在 ctx.waitUntil 里：页面和音频先返回，写库在后台做；写库失败一律忽略，不影响页面和音频。
// · 记录保存 400 天。没有定时任务（账号里的定时已经用了 4 个、上限 5 个）：每写进第 1000、2000……条时顺手删一次 400 天以前的，
//   站长打开统计页时也删一次（index.js 里调用）。

export const VID_COOKIE = 'fd_vid';
export const RETENTION_DAYS = 400;
export const CLEANUP_EVERY = 1000;               // 每写进第 1000、2000……条（按自增编号）顺手清一次
export const PLAY_ONCE_MS = 30 * 60 * 1000;      // 同一访客同一期的“开始听／开始看”30 分钟内只记一次
const DAY_MS = 86400000;
const PREFIX = '/frontier';
const DATE_Q = /^\d{4}-\d{2}-\d{2}$/;

const BOT_RE = /bot|crawl|spider|slurp|preview|headless|curl|wget|python|httpclient|http-client|okhttp|axios|node-fetch|undici|go-http|java\/|libwww|perl|ruby|php\/|scrapy|feedfetcher|facebookexternalhit|embedly|whatsapp|telegram|discord|skype|monitor|uptime|pingdom|lighthouse|pagespeed|gtmetrix|phantom|selenium|puppeteer|playwright|archiver|wayback|validator|scanner|fetch\//i;

export function isBot(req) {
  const ua = req.headers.get('User-Agent') || '';
  if (!ua.trim()) return true;
  if (BOT_RE.test(ua)) return true;
  const cf = req.cf || {};
  if (cf.verifiedBotCategory) return true;
  if (cf.botManagement && cf.botManagement.verifiedBot) return true;
  return false;
}

// 浏览器的预取、预渲染（用户还没真正打开页面）
export function isPrefetch(req) {
  const p = (req.headers.get('Sec-Purpose') || req.headers.get('Purpose') || req.headers.get('X-Purpose') || '').toLowerCase();
  return p.includes('prefetch') || p.includes('preview') || p.includes('prerender');
}

// 页面：首页（每期都是这一页，按 ?date= 换期）和往期目录。返回 'issue'（首页）、'past'（往期目录）或 null（不是要记的页面）
export function pageKind(path) {
  if (path === PREFIX + '/' || path === PREFIX + '/index.html') return 'issue';
  if (path === PREFIX + '/past/' || path === PREFIX + '/past/index.html') return 'past';
  return null;
}

// 页面路径：index.html 记成目录；首页只留 ?date=（格式对才留），其余参数（钥匙 k、theme、static、accent 等）一律不存
export function cleanPath(url) {
  const kind = pageKind(url.pathname);
  if (kind === 'past') return PREFIX + '/past/';
  if (kind === 'issue') {
    const d = url.searchParams.get('date') || '';
    return DATE_Q.test(d) ? `${PREFIX}/?date=${d}` : PREFIX + '/';
  }
  return url.pathname.slice(0, 200);
}

// 播放：某期的播客、视频旁白。返回 { kind: 'listen'|'watch', issue } 或 null
const PLAY_RE = /^\/frontier\/issues\/(\d{4}-\d{2}-\d{2})\/audio\/(podcast|video3)\.mp3$/;
export function playInfo(path) {
  const m = PLAY_RE.exec(path);
  return m ? { kind: m[2] === 'podcast' ? 'listen' : 'watch', issue: m[1] } : null;
}

// “从头要”：不带 Range，或 Range 是 bytes=0-… 的一段（bytes=0-0、bytes=0-1 这种只要一两个字节的探测不算；多段不算）
export function playStarts(req) {
  const r = req.headers.get('Range');
  if (r == null) return true;
  const m = /^bytes=(\d+)-(\d*)$/.exec(String(r).trim());
  if (!m || Number(m[1]) !== 0) return false;
  return m[2] === '' || Number(m[2]) >= 2;
}

export function deviceType(ua) {
  if (/iPad|Tablet|PlayBook|Silk|Kindle|SM-T\d|Android(?!.*Mobile)/i.test(ua)) return 'tablet';
  if (/Mobi|iPhone|iPod|Android|Windows Phone|HarmonyOS.*Phone/i.test(ua)) return 'mobile';
  return 'desktop';
}

export function browserName(ua) {
  const rules = [
    [/MicroMessenger/i, '微信'], [/\bQQ\//i, 'QQ'], [/MQQBrowser|QQBrowser/i, 'QQ 浏览器'], [/UCBrowser|UCWEB/i, 'UC 浏览器'],
    [/Quark/i, '夸克'], [/baiduboxapp|BaiduBrowser|bdbrowser/i, '百度'], [/HuaweiBrowser/i, '华为浏览器'],
    [/MiuiBrowser|XiaoMi\/MiuiBrowser/i, '小米浏览器'], [/SamsungBrowser/i, '三星浏览器'], [/DingTalk/i, '钉钉'],
    [/Edg(e|A|iOS)?\//, 'Edge'], [/OPR\/|Opera/, 'Opera'], [/Firefox|FxiOS/, 'Firefox'],
    [/Chrome|CriOS|Chromium/, 'Chrome'], [/Safari/, 'Safari'],
  ];
  for (const [re, name] of rules) if (re.test(ua)) return name;
  return '其他';
}

export function osName(ua) {
  const rules = [
    [/HarmonyOS|OpenHarmony/i, 'HarmonyOS'], [/iPhone|iPad|iPod/, 'iOS'], [/Android/, 'Android'], [/CrOS/, 'ChromeOS'],
    [/Windows/, 'Windows'], [/Mac OS X|Macintosh/, 'macOS'], [/Linux/, 'Linux'],
  ];
  for (const [re, name] of rules) if (re.test(ua)) return name;
  return '其他';
}

// 来源：只存主机名。站内跳转记 internal；没有来源（直接打开、书签、多数聊天软件）记空。
export function referrerHost(req, url) {
  const ref = req.headers.get('Referer') || '';
  if (ref) {
    try {
      const r = new URL(ref);
      if (r.host === url.host && (r.pathname === PREFIX || r.pathname.startsWith(PREFIX + '/'))) return 'internal';
      return (r.hostname || '').toLowerCase().replace(/^www\./, '').slice(0, 100);
    } catch (_) { return ''; }
  }
  if ((req.headers.get('Sec-Fetch-Site') || '') === 'same-origin') return 'internal';
  return '';
}

export function firstLanguage(req) {
  const first = (req.headers.get('Accept-Language') || '').split(',')[0].split(';')[0].trim();
  return /^[A-Za-z]{1,8}(-[A-Za-z0-9]{1,8}){0,3}$/.test(first) ? first.slice(0, 24) : '';
}

const ukDayFmt = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/London', year: 'numeric', month: '2-digit', day: '2-digit' });
export function ukDay(ms) { return ukDayFmt.format(new Date(ms)); }

export function readVid(req) {
  const m = (req.headers.get('Cookie') || '').match(/(?:^|;\s*)fd_vid=([^;]+)/);
  const v = m ? m[1].trim() : '';
  return /^[A-Za-z0-9-]{16,40}$/.test(v) ? v : '';
}

export function vidCookie(vid) {
  return `${VID_COOKIE}=${vid}; Path=${PREFIX}; Max-Age=31536000; HttpOnly; Secure; SameSite=Lax`;
}

function cut(s, n) { return String(s == null ? '' : s).slice(0, n); }

// 由请求拼出一行记录（不含 IP、完整 UA、完整来源）
export function buildRecord(req, url, { kind = 'page', path, issue = '', latest = 0, vid = '', isNew = false }, now = Date.now()) {
  const ua = req.headers.get('User-Agent') || '';
  const cf = req.cf || {};
  return {
    ts: now, day: ukDay(now), kind, path: path || cleanPath(url), issue: cut(issue, 10), latest: latest ? 1 : 0,
    country: cut(cf.country, 8), region: cut(cf.region, 80), city: cut(cf.city, 80),
    device: deviceType(ua), browser: browserName(ua), os: osName(ua),
    referrer: referrerHost(req, url), vid, is_new: isNew ? 1 : 0, lang: firstLanguage(req),
  };
}

export const COLS = ['ts', 'day', 'kind', 'path', 'issue', 'latest', 'country', 'region', 'city', 'device', 'browser', 'os', 'referrer', 'vid', 'is_new', 'lang'];
const INSERT = `INSERT INTO visits (${COLS.join(', ')}) VALUES (${COLS.map(() => '?').join(', ')})`;
// 播放：同一访客、同一种、同一期，30 分钟内已经有一条就不再写（一条语句里查和写，D1 一次只执行一条写语句，不会两条同时写进去）
const INSERT_ONCE = `INSERT INTO visits (${COLS.join(', ')}) SELECT ${COLS.map(() => '?').join(', ')} `
  + 'WHERE NOT EXISTS (SELECT 1 FROM visits WHERE vid = ? AND kind = ? AND issue = ? AND ts > ?)';

// 写一行。once = 播放（按访客查重）。返回 true = 写进去了。失败一律吞掉，不影响页面和音频。
export async function writeVisit(db, r, { once = false } = {}) {
  try {
    const vals = COLS.map((c) => r[c]);
    const stmt = once && r.vid
      ? db.prepare(INSERT_ONCE).bind(...vals, r.vid, r.kind, r.issue, r.ts - PLAY_ONCE_MS)
      : db.prepare(INSERT).bind(...vals);
    const res = await stmt.run();
    const meta = (res && res.meta) || {};
    const wrote = Number(meta.changes) > 0;
    if (wrote && Number(meta.last_row_id) > 0 && Number(meta.last_row_id) % CLEANUP_EVERY === 0) await cleanupVisits(db, r.ts);
    return wrote;
  } catch (_) { return false; /* 写库失败不影响页面 */ }
}

export async function cleanupVisits(db, now = Date.now()) {
  if (!db) return;
  try {
    await db.prepare('DELETE FROM visits WHERE ts < ?').bind(now - RETENTION_DAYS * DAY_MS).run();
  } catch (_) { /* 下次再删 */ }
}

// 往期目录 issues/index.js 里的最新一期和全部期号（不带期号的首页记成哪一期用）。同一个 Worker 实例里存 10 分钟；
// 每次发布是新版本、新实例，自然会重读。读不到就返回空（记成“最新一期（日期没取到）”）。
const INDEX_TTL_MS = 10 * 60 * 1000;
export const INDEX_CACHE = { at: 0, latest: '', dates: null };
export async function issueIndex(env, origin, now = Date.now()) {
  if (INDEX_CACHE.dates && now - INDEX_CACHE.at < INDEX_TTL_MS) return INDEX_CACHE;
  try {
    const res = await env.ASSETS.fetch(new Request(new URL(PREFIX + '/issues/index.js', origin)));
    if (res.ok) {
      const t = await res.text();
      const latest = (/"latest"\s*:\s*"(\d{4}-\d{2}-\d{2})"/.exec(t) || [])[1] || '';
      const dates = new Set(Array.from(t.matchAll(/"date"\s*:\s*"(\d{4}-\d{2}-\d{2})"/g), (m) => m[1]));
      if (latest) dates.add(latest);
      Object.assign(INDEX_CACHE, { at: now, latest, dates });
    }
  } catch (_) { /* 记成“日期没取到” */ }
  return INDEX_CACHE;
}

// 首页记成哪一期：?date= 是存在的一期就是它；否则（没带、写错、不存在）是最新一期，latest = 1。
// 和网页 site/v3/app.js 的选法一致：DATE = q 在往期里 ? q : INDEX.latest
export async function resolveIssue(env, url, now = Date.now()) {
  const q = url.searchParams.get('date') || '';
  const idx = await issueIndex(env, url.origin, now);
  if (DATE_Q.test(q) && (!idx.dates || idx.dates.has(q))) return { issue: q, latest: 0 };
  return { issue: idx.latest || '', latest: 1 };
}

function later(ctx, p) {
  if (ctx && typeof ctx.waitUntil === 'function') ctx.waitUntil(p);
  else p.catch(() => {});
}

// 这次页面响应要不要记
export function shouldRecord(req, url, status, isOwner, env) {
  return !!(env && env.VISITS) && req.method === 'GET' && (status === 200 || status === 304)
    && !!pageKind(url.pathname) && !isOwner && !isBot(req) && !isPrefetch(req);
}

// 记一次页面打开（后台），按需给响应加上访客编号 Cookie。返回要用的响应头（可能多一个 Set-Cookie）。
export function recordVisit(req, url, headers, env, ctx) {
  try {
    let vid = readVid(req);
    const isNew = !vid;
    if (isNew) {
      vid = crypto.randomUUID();
      headers.append('Set-Cookie', vidCookie(vid));
      headers.set('Cache-Control', 'private, no-cache');   // 带 Cookie 的页面只让访客自己的浏览器存
    }
    const now = Date.now();
    const kind = pageKind(url.pathname);
    const p = (async () => {
      const is = kind === 'issue' ? await resolveIssue(env, url, now) : { issue: '', latest: 0 };
      await writeVisit(env.VISITS, buildRecord(req, url, { kind: 'page', ...is, vid, isNew }, now));
    })().catch(() => {});
    later(ctx, p);
  } catch (_) { /* 统计出错不影响页面 */ }
  return headers;
}

// 这次音频响应要不要记一次“开始听／开始看”
export function shouldRecordPlay(req, url, status, isOwner, env) {
  return !!(env && env.VISITS) && req.method === 'GET' && (status === 200 || status === 206)
    && !!playInfo(url.pathname) && playStarts(req) && !isOwner && !isBot(req) && !isPrefetch(req);
}

// 记一次“开始听／开始看”（后台）。不发 Cookie、不改音频的响应头。
export function recordPlay(req, url, env, ctx) {
  try {
    const info = playInfo(url.pathname);
    const r = buildRecord(req, url, { kind: info.kind, path: url.pathname, issue: info.issue, vid: readVid(req) });
    later(ctx, writeVisit(env.VISITS, r, { once: true }));
  } catch (_) { /* 统计出错不影响音频 */ }
}
