// 网站开放程度（11-10 加）：站长在设置页 /frontier/_access 切换三档，决定别人打开网站时看到什么。
//
// · 三档（站长本人——带有效站长 Cookie fd_pass 的浏览器——任何一档都照常看全部内容）：
//   - public（公开）：有链接就能看，和加这个功能以前完全一样；
//   - family（凭口令）：别人打开任何页面，先看到“这个网站目前只对部分人开放”和一个口令框（别人看得到的地方不出现说明这一档给谁用的字眼，11-10 用户定）；输对一次发一张 180 天的口令 Cookie
//     （fd_family），这台设备之后不用再输；站长改口令以后，旧 Cookie 全部失效，所有凭口令进来的人都要重输；
//   - owner（只有我）：别人只看到“网站在测试中，暂时没有开放”，没有输入框。
// · 状态存在 D1（和访问统计同一个数据库 frontier-visits，绑定 VISITS）的 site_settings 表（migrations/0002_settings.sql）：
//   access_mode（public／family／owner）、family_pw（访问口令的“随机盐:SHA-256(盐+口令)”，不存口令本身）。
//   存在 D1 而不是写在代码或 wrangler.toml 里，是因为每天自动出刊都会重新发布 Worker：代码和配置每天换新，D1 里的数据不受影响，
//   所以站长切的档位不会被每天的发布重置。
// · 读状态：每个 Worker 实例在内存里存 15 秒（ACCESS_TTL_MS）；站长在设置页改了以后，处理这次修改的实例立即更新，
//   别的实例最多 15 秒后读到新值。
//   - 表不存在、或者没有这一行 → public（上线后、站长还没改过时，网站和以前一模一样）；
//   - 没有 VISITS 绑定 → public（设置页提示“没连上数据库，开放设置用不了”）；
//   - 别的读库错误 → 用本实例上次读到的值；本实例从没读到过 → 不放行（回 503“网站暂时打不开”，站长照常放行）。
// · 门（gate）的判断在 index.js：所有 /frontier 下的 GET/HEAD 都要过门；被挡下的一律回门页（本文件 gatePage），不去取静态文件。
// · 凭口令进入 POST /frontier/_enter、站长设置页 GET/POST /frontier/_access 也在这里（index.js 调用）。
// · 页面都是这里直接生成的一页 HTML：样式写在页面里、亮暗配色跟随系统、手机可看、不引用任何外部资源、不用 JavaScript、noindex。

export const ACCESS_PATH = '/frontier/_access';
export const ENTER_PATH = '/frontier/_enter';
export const FAMILY_COOKIE = 'fd_family';
export const FAMILY_MAX_AGE = 15552000;                  // 180 天
export const SITE_ORIGIN = 'https://wenlongzhang.com';
export const MODES = ['public', 'family', 'owner'];
export const MODE_LABEL = { public: '公开', family: '仅家人', owner: '只有我' };
export const ACCESS_TTL_MS = 15 * 1000;
export const FORM_MAX_BYTES = 2048;
export const PW_MIN = 4, PW_MAX = 64;
// 凭口令进入的限流：同一 IP、同一实例 10 分钟最多试 10 次（照 index.js 的 rateOk，单独一张表）
export const ENTER_RATE = { windowMs: 10 * 60 * 1000, max: 10, seen: new Map() };

const PREFIX = '/frontier';
const PW_RE = /^[0-9a-f]{32}:[0-9a-f]{64}$/;             // 盐（16 字节十六进制）:指纹
const DEFAULT = { mode: 'public', pw: '', token: '', modeTs: 0, pwTs: 0 };
const BASE = {
  'X-Robots-Tag': 'noindex, nofollow',
  'Referrer-Policy': 'same-origin',
  'X-Content-Type-Options': 'nosniff',
};

export const CREATE_TABLE = `CREATE TABLE IF NOT EXISTS site_settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_ts INTEGER NOT NULL
)`;
const SELECT = "SELECT key, value, updated_ts FROM site_settings WHERE key IN ('access_mode', 'family_pw')";
const UPSERT = 'INSERT INTO site_settings (key, value, updated_ts) VALUES (?, ?, ?) '
  + 'ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_ts = excluded.updated_ts';

export async function sha256hex(text) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

// 两个字符串是否相同（逐字比完，不因为早早对不上就提前返回）。原在 index.js（站长钥匙用），11-10 挪到这里，两边共用
export function same(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

export function cookieValue(req, name) {
  const m = (req.headers.get('Cookie') || '').match(new RegExp('(?:^|;\\s*)' + name + '=([^;]+)'));
  return m ? m[1].trim() : '';
}

export function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ===================== 读、写状态 =====================

// 本实例内存里的状态：value 是上次读到的（{ mode, pw, token, modeTs, pwTs }），at 是读到的时间
export const ACCESS_STATE = { at: 0, value: null };
export function resetAccessCache() { ACCESS_STATE.at = 0; ACCESS_STATE.value = null; }

// 口令 Cookie 的值：SHA-256(当前 family_pw 记录 + ':fd_family')。改口令 → 记录变 → 值变 → 旧 Cookie 自动失效
export async function familyToken(pw) { return pw ? sha256hex(pw + ':fd_family') : ''; }

// 从数据库读一次（不看缓存）。表不存在当作“没设过”（public）；别的错误往外抛
export async function loadSettings(db) {
  let rows;
  try {
    const res = await db.prepare(SELECT).all();
    rows = (res && res.results) || [];
  } catch (e) {
    if (/no such table/i.test(String((e && e.message) || e))) return { ...DEFAULT };
    throw e;
  }
  const m = rows.find((x) => x.key === 'access_mode');
  const p = rows.find((x) => x.key === 'family_pw');
  const mode = m && MODES.includes(m.value) ? m.value : 'public';
  const pw = p && PW_RE.test(String(p.value)) ? String(p.value) : '';
  return { mode, pw, token: await familyToken(pw), modeTs: m ? Number(m.updated_ts) || 0 : 0, pwTs: p ? Number(p.updated_ts) || 0 : 0 };
}

// 现在是哪一档。返回 { mode, pw, token, modeTs, pwTs }，另可能带 noDb（没绑数据库）；mode 为 null 表示读不到、本实例也从没读到过。
export async function readAccess(env, now = Date.now()) {
  const db = env && env.VISITS;
  if (!db) return { ...DEFAULT, noDb: true };
  if (ACCESS_STATE.value && now - ACCESS_STATE.at < ACCESS_TTL_MS) return ACCESS_STATE.value;
  try {
    const v = await loadSettings(db);
    ACCESS_STATE.value = v;
    ACCESS_STATE.at = now;
    return v;
  } catch (e) {
    console.log(`开放程度：读数据库出错（${String((e && e.name) || 'error')}），${ACCESS_STATE.value ? '用本实例上次读到的值' : '本实例从没读到过，先不放行'}`);
    if (ACCESS_STATE.value) { ACCESS_STATE.at = now; return ACCESS_STATE.value; }   // 15 秒后再试
    return { ...DEFAULT, mode: null };
  }
}

// 写一项设置（第一次写之前先建表：线上迁移还没跑也能用）。写完更新本实例的缓存
async function writeSetting(db, key, value, now) {
  await db.prepare(CREATE_TABLE).run();
  await db.prepare(UPSERT).bind(key, value, now).run();
}

// 访问口令 → “随机盐:SHA-256(盐+口令)”
export async function makePwRecord(pw) {
  const salt = [...crypto.getRandomValues(new Uint8Array(16))].map((b) => b.toString(16).padStart(2, '0')).join('');
  return `${salt}:${await sha256hex(salt + pw)}`;
}

export async function checkPw(record, pw) {
  if (!PW_RE.test(String(record || '')) || typeof pw !== 'string' || !pw) return false;
  const [salt, hash] = record.split(':');
  return same(await sha256hex(salt + pw), hash);
}

// ===================== 门 =====================

// 这次请求放不放行。返回 { allow, mode, private, page }：
//   allow   放行；
//   private 放行的回应要把 Cache-Control 的 public 换成 private（不是公开档，或者档位读不到）；
//   page    不放行时回哪种门页：'family'（口令框）、'owner'（测试中）、'error'（503 暂时打不开）。
export async function decide(req, env, owner, now = Date.now()) {
  const st = await readAccess(env, now);
  const priv = st.mode !== 'public';
  if (owner) return { allow: true, mode: st.mode, private: priv, st };
  if (st.mode === null) return { allow: false, mode: null, private: true, page: 'error', st };
  if (st.mode === 'public') return { allow: true, mode: 'public', private: false, st };
  if (st.mode === 'family' && st.token && same(cookieValue(req, FAMILY_COOKIE), st.token)) return { allow: true, mode: 'family', private: true, st };
  return { allow: false, mode: st.mode, private: true, page: st.mode === 'family' ? 'family' : 'owner', st };
}

// 放行的回应在非公开档时只让访客自己的浏览器存：public 换成 private；没写 public 的（网页的 no-cache）前面加 private；no-store 不动
export function privatize(cc) {
  const s = String(cc || '');
  if (!s || /no-store|\bprivate\b/.test(s)) return s;
  if (/\bpublic\b/.test(s)) return s.replace(/\bpublic\b/, 'private');
  return 'private, ' + s;
}

// 登录后要回到的地址：只认 /frontier/ 开头的站内路径；含 //、反斜杠、. 或 .. 这一级、控制字符、别的怪字符的一律回 /frontier/（防跳到外站或站外）
export function safeNext(v) {
  const s = typeof v === 'string' ? v : '';
  if (!s.startsWith(PREFIX + '/') || s.length > 512) return PREFIX + '/';
  if (s.includes('//') || s.includes('\\') || /%2e|%2f|%5c/i.test(s)) return PREFIX + '/';
  if (!/^[A-Za-z0-9\-._~!$&'()*+,;=:@/?%]*$/.test(s)) return PREFIX + '/';
  const pathPart = s.split('?')[0];
  if (pathPart.split('/').some((seg) => seg === '.' || seg === '..')) return PREFIX + '/';
  return s;
}

// 门页里的“回到哪里”：这次请求的路径和参数（去掉站长钥匙参数 k）
export function nextOf(url) {
  const u = new URL(url.href);
  u.searchParams.delete('k');
  return safeNext(u.pathname + u.search);
}

const GATE_CSS = `:root{color-scheme:light dark;--bg:#f5f5f7;--card:#fff;--ink:#1d1d1f;--mute:#636366;--line:#d2d2d7;--acc:#0062c4;--on:#fff;--warn:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#0a0a0c;--card:#1c1c1e;--ink:#f5f5f7;--mute:#a1a1a6;--line:#3a3a3c;--acc:#4ea1ff;--on:#06121f;--warn:#ff8a80}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--bg);color:var(--ink);font:16px/1.8 -apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;text-align:center}
main{width:100%;max-width:420px;padding:24px 16px}
h1{font-size:21px;line-height:1.5;margin:0 0 4px}
.en{color:var(--mute);font-size:14px;margin:0 0 18px}
.msg{color:var(--warn);font-size:15px;margin:0 0 14px}
form{display:flex;flex-direction:column;gap:10px;text-align:left}
label{font-size:14px;color:var(--mute)}
input{font:inherit;font-size:17px;padding:12px 14px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink);width:100%}
button{font:inherit;font-size:17px;font-weight:600;padding:12px 14px;min-height:48px;border:0;border-radius:10px;background:var(--acc);color:var(--on);cursor:pointer}
.note{color:var(--mute);font-size:13px;margin:16px 0 0}`;

const GATE_TEXT = {
  family: ['这个网站目前只对部分人开放', 'This site is currently open to selected visitors only.', '只对部分人开放'],
  owner: ['网站在测试中，暂时没有开放', 'This site is being tested and isn’t open yet.', '暂时没有开放'],
  error: ['网站暂时打不开，请过一会儿再刷新', 'The site can’t be opened right now. Please refresh in a little while.', '暂时打不开'],
};
export const GATE_MSG = {
  wrong: ['口令不对', 'That password isn’t right.'],
  many: ['试得太多了，请 10 分钟后再试', 'Too many tries. Please wait 10 minutes and try again.'],
};

// 门页里的标记 <meta name="fd-gate" content="…">（两个手动流程的线上检查认它）：用不带“给谁用”意思的词，别人看网页源码也看不出
const GATE_MARK = { family: 'password', owner: 'closed', error: 'error' };

// 门页 HTML。kind = family／owner／error；msg = GATE_MSG 的键（只在口令框那页用）；next = 输对后回到的地址
export function gateHTML(kind, { next = PREFIX + '/', msg = '' } = {}) {
  const [zh, en, title] = GATE_TEXT[kind] || GATE_TEXT.owner;
  const m = GATE_MSG[msg];
  const msgHTML = m ? `<p class="msg" role="alert">${esc(m[0])}<br>${esc(m[1])}</p>` : '';
  const form = kind === 'family' ? `${msgHTML}<form method="post" action="${ENTER_PATH}">
<input type="hidden" name="next" value="${esc(safeNext(next))}">
<label for="pw">口令 · Password</label>
<input id="pw" name="password" type="password" autocomplete="current-password" required maxlength="${PW_MAX}" autofocus>
<button type="submit">进入 · Enter</button>
</form>
<p class="note">输对一次，这台设备之后不用再输。<br>Enter it once and this device will remember it.</p>` : '';
  return `<!doctype html><html lang="zh-Hans"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex, nofollow"><meta name="color-scheme" content="light dark"><meta name="fd-gate" content="${esc(GATE_MARK[kind] || 'closed')}"><link rel="icon" href="data:,">
<title>${esc(title)} · 每日AI科技前沿简报</title><style>${GATE_CSS}</style></head>
<body><main><h1>${esc(zh)}</h1><p class="en">${esc(en)}</p>${form}</main></body></html>`;
}

// 门页回应：family／owner 403，error 503；一律 no-store，带三个公共响应头；HEAD 不带正文
export function gatePage(method, kind, opts = {}) {
  const status = opts.status || (kind === 'error' ? 503 : 403);
  const h = new Headers({ 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', ...BASE });
  if (kind === 'error') h.set('Retry-After', '60');
  if (opts.retryAfter) h.set('Retry-After', String(opts.retryAfter));
  return new Response(method === 'HEAD' ? null : gateHTML(kind, opts), { status, headers: h });
}

function plain(status, text) {
  return new Response(text, { status, headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store', ...BASE } });
}

function seeOther(location, cookie) {
  const h = new Headers({ Location: location, 'Cache-Control': 'no-store', ...BASE });
  if (cookie) h.append('Set-Cookie', cookie);
  return new Response(null, { status: 303, headers: h });
}

// 同一实例内存里的简单限流（照 index.js 的 rateOk）：每个 IP 在 windowMs 内最多 max 次。返回 true＝放行
export function enterRateOk(ip, now = Date.now(), table = ENTER_RATE) {
  const key = ip || 'unknown';
  const list = (table.seen.get(key) || []).filter((t) => now - t < table.windowMs);
  if (list.length >= table.max) { table.seen.set(key, list); return false; }
  list.push(now);
  table.seen.set(key, list);
  if (table.seen.size > 2000) {
    for (const [k, v] of table.seen) if (!v.some((t) => now - t < table.windowMs)) table.seen.delete(k);
  }
  return true;
}

// 读表单（application/x-www-form-urlencoded，不超过 2 KB）。返回 URLSearchParams，或一个错误回应
async function readForm(req) {
  const type = (req.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase();
  if (type !== 'application/x-www-form-urlencoded') return plain(415, '只收表单');
  const len = Number(req.headers.get('Content-Length'));
  if (Number.isFinite(len) && len > FORM_MAX_BYTES) return plain(413, '内容太长了');
  let raw;
  try { raw = await req.text(); } catch { return plain(400, '没读到内容'); }
  if (new TextEncoder().encode(raw).byteLength > FORM_MAX_BYTES) return plain(413, '内容太长了');
  return new URLSearchParams(raw);
}

// ===================== 凭口令进入：POST /frontier/_enter =====================
// 门页的口令框提交到这里。Origin 有值且不是 https://wenlongzhang.com → 403；没有 Origin 也收（有的浏览器不带）。
// 现在不是 family 档：public → 直接跳回去；owner → 测试中的门页。口令对 → 发口令 Cookie、303 跳回 next；不对 → 门页加“口令不对”。
export async function handleEnter(req, env, owner, now = Date.now()) {
  const origin = req.headers.get('Origin');
  if (origin && origin !== SITE_ORIGIN) return plain(403, '只能从网站页面提交');
  const form = await readForm(req);
  if (form instanceof Response) return form;
  const next = safeNext(form.get('next') || '');
  const st = await readAccess(env, now);
  if (owner) return seeOther(next);
  if (st.mode === null) return gatePage('POST', 'error');
  if (st.mode === 'public') return seeOther(next);
  if (st.mode !== 'family') return gatePage('POST', 'owner');
  if (!enterRateOk(req.headers.get('CF-Connecting-IP'), now)) return gatePage('POST', 'family', { next, msg: 'many', status: 429, retryAfter: 600 });
  const pw = String(form.get('password') || '').trim();
  if (st.pw && st.token && pw && await checkPw(st.pw, pw)) {
    return seeOther(next, `${FAMILY_COOKIE}=${st.token}; Path=${PREFIX}; Max-Age=${FAMILY_MAX_AGE}; HttpOnly; Secure; SameSite=Lax`);
  }
  return gatePage('POST', 'family', { next, msg: 'wrong' });
}

// ===================== 站长设置页：/frontier/_access =====================
// GET：显示当前档位、上次改动时间、访问口令设没设；三个大按钮、设新口令的表单。只认站长（判断在 index.js，别人 404）。
// POST：Origin 必须是 https://wenlongzhang.com（否则 403）；只收表单、不超过 2 KB；处理完 303 回设置页，用 ?msg= 说改成了什么。

const MSG = {
  'mode-public': ['ok', '已改成“公开”：有链接就能看。'],
  'mode-family': ['ok', '已改成“仅家人”：别人要先输家人口令。'],
  'mode-owner': ['ok', '已改成“只有我”：别人只看到“网站在测试中”。'],
  pwset: ['ok', '家人口令已更新。已经进来的家人要用新口令重新输一次。'],
  nopw: ['err', '还没设家人口令：先在下面设一个口令，再切到“仅家人”。'],
  pwlen: ['err', `口令要 ${PW_MIN}–${PW_MAX} 个字（首尾空格不算）。`],
  pwdiff: ['err', '两遍输的口令不一样，请重输。'],
  nodb: ['err', '没连上数据库，开放设置用不了。'],
  dberr: ['err', '写数据库出错，没改成。过一会儿再试。'],
  bad: ['err', '没看懂这次提交，什么都没改。'],
};

function fmtUK(ms) {
  if (!ms) return '';
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })
    .formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second}`;
}

const ACCESS_CSS = `:root{color-scheme:light dark;--bg:#f5f5f7;--card:#fff;--ink:#1d1d1f;--mute:#636366;--line:#d2d2d7;--acc:#0062c4;--on:#fff;--ok:#1e7d32;--warn:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#0a0a0c;--card:#1c1c1e;--ink:#f5f5f7;--mute:#a1a1a6;--line:#3a3a3c;--acc:#4ea1ff;--on:#06121f;--ok:#7ddc84;--warn:#ff8a80}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.75 -apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif}
.wrap{max-width:720px;margin:0 auto;padding:20px 16px 48px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:0 0 8px}
a{color:var(--acc)}
.top{display:flex;gap:16px;flex-wrap:wrap;font-size:14px;margin:0 0 14px}
.note{color:var(--mute);font-size:14px;margin:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-top:14px}
.flash{border-radius:10px;padding:10px 14px;margin-top:14px;font-weight:600}
.flash.ok{border:1px solid var(--ok);color:var(--ok)}.flash.err{border:1px solid var(--warn);color:var(--warn)}
.now{font-size:20px;font-weight:700}
.modes{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:10px}
.modes button{font:inherit;min-height:84px;padding:12px 10px;border:2px solid var(--line);border-radius:12px;background:var(--bg);color:var(--ink);cursor:pointer;text-align:center}
.modes button b{display:block;font-size:19px}
.modes button small{display:block;font-size:13px;color:var(--mute);line-height:1.5}
.modes button.on{background:var(--acc);border-color:var(--acc);color:var(--on)}
.modes button.on small{color:var(--on)}
.modes button:disabled{opacity:.55;cursor:not-allowed}
form.pw{display:flex;flex-direction:column;gap:8px;max-width:420px}
form.pw label{font-size:14px;color:var(--mute)}
form.pw input{font:inherit;font-size:17px;padding:11px 13px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink)}
form.pw button{font:inherit;font-size:17px;font-weight:600;min-height:50px;border:0;border-radius:10px;background:var(--acc);color:var(--on);cursor:pointer}
ul{margin:6px 0 0;padding-left:20px;color:var(--mute);font-size:14px}
@media (max-width:560px){.modes{grid-template-columns:1fr}.modes button{min-height:64px}}`;

const MODE_HINT = { public: '有链接就能看', family: '要输家人口令', owner: '别人看到“测试中”' };

export function renderAccessPage(st, { msg = '', dbNote = '' } = {}) {
  const f = MSG[msg];
  const flash = f ? `<div class="flash ${f[0]}" role="status">${esc(f[1])}</div>` : '';
  const noDb = !!st.noDb;
  const dis = noDb || st.mode === null ? ' disabled' : '';
  const cur = st.mode;
  const btn = (m) => {
    const hint = m === 'family' && !st.pw ? '先设口令' : MODE_HINT[m];
    return `<button type="submit" name="mode" value="${m}"${m === cur ? ' class="on" aria-pressed="true"' : ' aria-pressed="false"'}${dis}><b>${esc(MODE_LABEL[m])}</b><small>${esc(m === cur ? '现在是这一档' : hint)}</small></button>`;
  };
  const nowLine = cur === null
    ? '<span class="now">读不到</span>'
    : `<span class="now">${esc(MODE_LABEL[cur])}</span>　<span class="note">${st.modeTs ? `上次改动：${esc(fmtUK(st.modeTs))}（英国时间）` : '还没改过（默认公开）'}</span>`;
  const pwLine = st.pw ? `已设${st.pwTs ? `（上次改动：${esc(fmtUK(st.pwTs))}，英国时间）` : ''}` : '还没设';
  const top = '<div class="top"><a href="/frontier/_visits">← 访问统计</a><a href="/frontier/">回到网站</a></div>';
  const warn = noDb ? '<div class="flash err">没连上数据库，开放设置用不了（Worker 缺少 VISITS 绑定）。网站现在按“公开”处理。</div>'
    : (dbNote ? `<div class="flash err">${esc(dbNote)}</div>` : '');
  return `<!doctype html><html lang="zh-Hans"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex, nofollow"><meta name="color-scheme" content="light dark"><link rel="icon" href="data:,"><title>开放程度 · 每日AI科技前沿简报</title><style>${ACCESS_CSS}</style></head>
<body><div class="wrap">
${top}
<h1>开放程度</h1>
<p class="note">只有你（带站长 Cookie 的浏览器）能看到这一页。你自己任何一档都照常看全部内容。</p>
${warn}${flash}
<div class="card"><h2>现在</h2>${nowLine}</div>
<div class="card"><h2>切换</h2>
<form method="post" action="${ACCESS_PATH}"><input type="hidden" name="op" value="mode"><div class="modes">${MODES.map(btn).join('')}</div></form>
<ul><li>公开：有链接就能看，和以前一样。</li><li>仅家人：别人打开任何页面，先看到“这个网站目前只对部分人开放”和口令框（门页上不出现“家人”二字）；输对一次，这台设备 180 天内不用再输。</li><li>只有我：别人只看到“网站在测试中，暂时没有开放”，没有输入框。</li></ul>
</div>
<div class="card"><h2>家人口令：${esc(pwLine)}</h2>
<p class="note" style="margin-bottom:10px">这里不会显示口令；忘了就设一个新的。口令 ${PW_MIN}–${PW_MAX} 个字，首尾空格不算。</p>
<form class="pw" method="post" action="${ACCESS_PATH}"><input type="hidden" name="op" value="pw">
<label for="pw1">新口令</label><input id="pw1" name="pw1" type="password" autocomplete="new-password" required minlength="${PW_MIN}" maxlength="${PW_MAX}"${dis}>
<label for="pw2">再输一遍</label><input id="pw2" name="pw2" type="password" autocomplete="new-password" required minlength="${PW_MIN}" maxlength="${PW_MAX}"${dis}>
<button type="submit"${dis}>设新口令</button></form>
</div>
<div class="card"><h2>要知道</h2><ul>
<li>改了口令，已经进来的家人要用新口令重新输一次。</li>
<li>改动最多 15 秒内对所有人生效。</li>
<li>已经听过、看过的音频和图片，可能还留在对方浏览器里（最多 7 天）；切到“只有我”不会把它们从别人手机里删掉。</li>
<li>每天自动出刊重新发布网站，不会把这里的设置改回去（设置存在数据库里，不在程序里）。</li>
</ul></div>
</div></body></html>`;
}

// 设置页不许被别的网站嵌进框里（X-Frame-Options、frame-ancestors）
const NO_STORE = { 'Cache-Control': 'no-store', ...BASE, 'X-Frame-Options': 'DENY', 'Content-Security-Policy': "frame-ancestors 'none'" };

export async function accessGet(req, env, now = Date.now()) {
  const url = new URL(req.url);
  const msg = url.searchParams.get('msg') || '';
  const db = env && env.VISITS;
  let st, dbNote = '';
  if (!db) st = { ...DEFAULT, noDb: true };
  else {
    try {
      st = await loadSettings(db);                          // 设置页读最新的（不看缓存），顺手更新本实例的缓存
      ACCESS_STATE.value = st;
      ACCESS_STATE.at = now;
    } catch (e) {
      st = ACCESS_STATE.value || { ...DEFAULT, mode: null };
      dbNote = `读数据库出错（${String((e && e.message) || e).slice(0, 160)}）${ACCESS_STATE.value ? '，下面是本实例上次读到的' : ''}。`;
    }
  }
  const html = renderAccessPage(st, { msg: Object.prototype.hasOwnProperty.call(MSG, msg) ? msg : '', dbNote });
  return new Response(req.method === 'HEAD' ? null : html, { status: 200, headers: { ...NO_STORE, 'Content-Type': 'text/html; charset=utf-8' } });
}

const back = (msg) => seeOther(`${ACCESS_PATH}?msg=${msg}`);
const charLen = (s) => Array.from(s).length;

// POST /frontier/_access（index.js 已确认是站长）
export async function accessPost(req, env, now = Date.now()) {
  if (req.headers.get('Origin') !== SITE_ORIGIN) return plain(403, '只能从网站页面提交');
  const form = await readForm(req);
  if (form instanceof Response) return form;
  const db = env && env.VISITS;
  if (!db) return back('nodb');
  const op = form.get('op');
  try {
    if (op === 'mode') {
      const mode = form.get('mode');
      if (!MODES.includes(mode)) return back('bad');
      const cur = await loadSettings(db);
      if (mode === 'family' && !cur.pw) return back('nopw');
      await writeSetting(db, 'access_mode', mode, now);
      ACCESS_STATE.value = { ...cur, mode, modeTs: now };
      ACCESS_STATE.at = now;
      console.log(`开放程度：站长改成 ${mode}`);
      return back('mode-' + mode);
    }
    if (op === 'pw') {
      const p1 = String(form.get('pw1') || '').trim();
      const p2 = String(form.get('pw2') || '').trim();
      if (charLen(p1) < PW_MIN || charLen(p1) > PW_MAX) return back('pwlen');
      if (p1 !== p2) return back('pwdiff');
      const cur = await loadSettings(db);
      const rec = await makePwRecord(p1);
      await writeSetting(db, 'family_pw', rec, now);
      ACCESS_STATE.value = { ...cur, pw: rec, token: await familyToken(rec), pwTs: now };
      ACCESS_STATE.at = now;
      console.log('开放程度：站长设了新的家人口令');      // 不记口令
      return back('pwset');
    }
  } catch (e) {
    console.log(`开放程度：写数据库出错（${String((e && e.name) || 'error')}）`);
    return back('dberr');
  }
  return back('bad');
}
