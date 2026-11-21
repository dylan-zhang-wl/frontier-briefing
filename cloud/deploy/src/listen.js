// 耳听点选页（2026-11-21 加）：站长逐条听审片列出的“请你耳听”，点“念对了／念错了／没听出来”，结果存进 D1，周六维护直接读。
//
// · 网址只有一个：/frontier/_listen（index.js 判断：只认站长 Cookie，和 /frontier/_access 同一套；别人一律 404，不暴露这一页存在；
//   路径的大小写、%5F、双斜杠、多一层目录等变体，谁来都 404）。
//   - GET 不带参数：最近 14 期的列表（哪天、几处、点了几处）；
//   - GET ?date=YYYY-MM-DD：那一期的逐条点选页；
//   - GET ?export=json：导出全部结果（JSON 文件，带日期、位置、说明、判断、关乎事实、结果、备注、时间），给周六维护用；
//   - POST（表单）：存一条的结果。Origin 必须是 https://wenlongzhang.com（照设置页）。页面用脚本提交、不刷新；没有脚本时普通表单提交，303 回到那一条。
// · 条目从哪来：上线包里的 frontier/_listen/<日期>.json 和 index.json（cloud/deploy/listen_items.py 做的，发布时开关 FD_LISTEN_PAGE=on 才有）。
//   这些文件谁都不能直接下载（index.js 挡在门前）；只在站长打开这一页时，由这里经 env.ASSETS 读出来、做成页面。
// · 结果存在 D1（和访问统计、开放程度同一个数据库 frontier-visits，绑定 VISITS）的 listen_votes 表（migrations/0003_listen.sql；
//   第一次写之前程序自己 CREATE TABLE IF NOT EXISTS）。一条一行，主键（日期, 条目编号）：改了再点就覆盖，以最后一次为准。
// · 读库出错：页面照样显示条目，只是没有已选的结果（顶上写一句）；POST 回错误（503）。没绑数据库：页面照样显示，点了回“没连上数据库”。
// · 放音频：页面里的 <audio> 直接要网页上那份 mp3（issues/<日期>/audio/podcast.mp3、video3.mp3），浏览器自己带 Range，
//   index.js 照旧回 206；站长的请求不记访问统计。点“播放”从这一段的起点放到终点自动停，可以重播；不另切音频文件。
// · 页面是这里直接生成的一页：样式、脚本写在页面里，亮暗配色跟随系统，手机优先（按钮至少 48px 高、一处一张卡），
//   不引用任何外网资源（Content-Security-Policy 只许本站），不计入访问统计，不缓存，不许别的网站嵌进框里。

import { esc, SITE_ORIGIN } from './access.js';

export const LISTEN_PATH = '/frontier/_listen';
const LISTEN_DIR = '/frontier/_listen/';
export const LIST_DAYS = 14;
export const NOTE_MAX = 200;
export const FORM_MAX = 2048;
export const RESULT = { right: '念对了', wrong: '念错了', unsure: '没听出来' };
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
export const ITEM_RE = /^[0-9a-f]{10}(?:-\d{1,3})?$/;
const AUDIO_FILE = { 播客: 'podcast.mp3', 视频: 'video3.mp3' };
const BASE = { 'X-Robots-Tag': 'noindex, nofollow', 'Referrer-Policy': 'same-origin', 'X-Content-Type-Options': 'nosniff' };
const CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; media-src 'self'; connect-src 'self'; "
  + "form-action 'self'; base-uri 'none'; frame-ancestors 'none'";
const PAGE_HEADERS = { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', ...BASE, 'X-Frame-Options': 'DENY', 'Content-Security-Policy': CSP };

export const CREATE_TABLE = `CREATE TABLE IF NOT EXISTS listen_votes (
  date   TEXT    NOT NULL,
  item   TEXT    NOT NULL,
  result TEXT    NOT NULL,
  note   TEXT    NOT NULL DEFAULT '',
  ts     INTEGER NOT NULL,
  PRIMARY KEY (date, item)
)`;
const UPSERT = 'INSERT INTO listen_votes (date, item, result, note, ts) VALUES (?, ?, ?, ?, ?) '
  + 'ON CONFLICT(date, item) DO UPDATE SET result = excluded.result, note = excluded.note, ts = excluded.ts';

// ===================== 读条目、读结果 =====================

async function readJSON(env, url, file) {
  const res = await env.ASSETS.fetch(new Request(new URL(LISTEN_DIR + file, url.origin), { method: 'GET' }));
  if (res.status !== 200) {
    if (res.body) res.body.cancel().catch(() => {});
    return null;
  }
  try { return await res.json(); } catch { return null; }
}

// 一期的条目（{ date, items: [...] }），没有返回 null
export async function readIssue(env, url, date) {
  if (!DATE_RE.test(date)) return null;
  const j = await readJSON(env, url, date + '.json');
  return j && Array.isArray(j.items) ? j : null;
}

// 那一期已选的结果：Map(条目编号 → { result, note, ts })。表不存在当作还没点过；别的错误往外抛
export async function loadVotes(db, date) {
  try {
    const r = await db.prepare('SELECT item, result, note, ts FROM listen_votes WHERE date = ?').bind(date).all();
    return new Map(((r && r.results) || []).map((x) => [String(x.item), { result: String(x.result), note: String(x.note || ''), ts: Number(x.ts) || 0 }]));
  } catch (e) {
    if (/no such table/i.test(String((e && e.message) || e))) return new Map();
    throw e;
  }
}

// 各期点了几条：Map(日期 → 条数)，只数 since 及以后的
async function countVotes(db, since) {
  try {
    const r = await db.prepare('SELECT date, COUNT(*) AS n FROM listen_votes WHERE date >= ? GROUP BY date').bind(since).all();
    return new Map(((r && r.results) || []).map((x) => [String(x.date), Number(x.n) || 0]));
  } catch (e) {
    if (/no such table/i.test(String((e && e.message) || e))) return new Map();
    throw e;
  }
}

// ===================== 页面 =====================

const CSS = `:root{color-scheme:light dark;--bg:#f5f5f7;--card:#fff;--ink:#1d1d1f;--mute:#636366;--line:#d2d2d7;--acc:#0062c4;--on:#fff;
--ok:#1e7d32;--okbg:#e7f4e8;--bad:#b3261e;--badbg:#fbe9e7;--mid:#5f6368;--midbg:#eceff1;--fact:#8a4b00;--factbg:#fff1d6;--warn:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#0a0a0c;--card:#1c1c1e;--ink:#f5f5f7;--mute:#a1a1a6;--line:#3a3a3c;--acc:#4ea1ff;--on:#06121f;
--ok:#7ddc84;--okbg:#12301a;--bad:#ff8a80;--badbg:#3a1714;--mid:#c4c7c5;--midbg:#2a2c2e;--fact:#ffc46b;--factbg:#3a2a0c;--warn:#ff8a80}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 -apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;-webkit-text-size-adjust:100%}
.wrap{max-width:760px;margin:0 auto;padding:16px 16px 120px}
h1{font-size:22px;line-height:1.4;margin:6px 0 4px}h2{font-size:17px;margin:22px 0 8px}
a{color:var(--acc)}
.top{display:flex;gap:14px;flex-wrap:wrap;font-size:14px;margin:0 0 8px}
.note{color:var(--mute);font-size:14px;margin:0}
.flash{border-radius:10px;padding:10px 14px;margin:12px 0 0;font-weight:600;border:1px solid var(--warn);color:var(--warn)}
.flash.ok{border-color:var(--ok);color:var(--ok)}
.sum{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 0;font-size:14px}
.pill{display:inline-block;padding:1px 10px;border-radius:999px;background:var(--midbg);color:var(--mid);font-size:13px;line-height:1.8;white-space:nowrap}
.pill.fact{background:var(--factbg);color:var(--fact);font-weight:700}
.pill.right{background:var(--okbg);color:var(--ok)}.pill.wrong{background:var(--badbg);color:var(--bad)}
.issues{list-style:none;margin:12px 0 0;padding:0;display:grid;gap:10px}
.issues a{display:flex;justify-content:space-between;align-items:center;gap:12px;min-height:64px;padding:12px 16px;border-radius:14px;background:var(--card);border:1px solid var(--line);color:inherit;text-decoration:none}
.issues b{font-size:18px}.issues small{display:block;color:var(--mute);font-size:13px}
.issues .go{color:var(--acc);font-weight:600;white-space:nowrap}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin-top:12px;scroll-margin-top:12px}
.card.done{border-color:var(--acc)}
.head{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:6px}
.no{font-size:13px;color:var(--mute)}
.pos{font-size:17px;font-weight:700;margin:2px 0 6px;word-break:break-word}
dl{margin:0;display:grid;grid-template-columns:4.6em 1fr;gap:2px 10px;font-size:15px}
dt{color:var(--mute)}dd{margin:0;word-break:break-word}
details.basis{margin-top:6px;font-size:14px;color:var(--mute)}details.basis summary{cursor:pointer}
.clips{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 4px}
.clip{font:inherit;font-size:16px;font-weight:600;min-height:48px;padding:8px 14px;border:2px solid var(--acc);border-radius:12px;background:var(--bg);color:var(--acc);cursor:pointer;flex:1 1 auto}
.clip small{display:block;font-size:12px;font-weight:400;color:var(--mute)}
.clip.playing{background:var(--acc);color:var(--on)}.clip.playing small{color:var(--on)}
.noclip{font-size:14px;color:var(--mute);margin:10px 0 4px}
form.vote{margin-top:10px}
form.vote input[type=text]{font:inherit;font-size:16px;width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink)}
.btns{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px}
.btns button{font:inherit;font-size:16px;font-weight:700;min-height:52px;padding:6px 4px;border-radius:12px;border:2px solid var(--line);background:var(--bg);color:var(--ink);cursor:pointer}
.btns button[value=right][aria-pressed=true]{background:var(--ok);border-color:var(--ok);color:var(--on)}
.btns button[value=wrong][aria-pressed=true]{background:var(--bad);border-color:var(--bad);color:var(--on)}
.btns button[value=unsure][aria-pressed=true]{background:var(--mid);border-color:var(--mid);color:var(--on)}
.btns button:disabled{opacity:.6}
.state{font-size:13px;color:var(--mute);margin:6px 0 0;min-height:1.5em}.state.err{color:var(--warn);font-weight:600}
details.batch{margin-top:22px}details.batch>summary{cursor:pointer;font-size:16px;font-weight:700;padding:12px 14px;border-radius:12px;background:var(--midbg);color:var(--mid);list-style-position:inside}
.export{display:inline-block;margin-top:18px;padding:12px 16px;min-height:48px;border-radius:12px;border:2px solid var(--acc);color:var(--acc);font-weight:600;text-decoration:none}
#bar{position:fixed;left:0;right:0;bottom:0;background:var(--card);border-top:1px solid var(--line);padding:10px 16px calc(10px + env(safe-area-inset-bottom));display:none;z-index:9}
#bar.on{display:block}
#bar .in{max-width:760px;margin:0 auto;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
#bar .what{flex:1 1 180px;font-size:14px}#bar .what b{display:block;font-size:15px}
#bar progress{width:100%;height:6px}
#bar button{font:inherit;font-size:15px;font-weight:600;min-height:44px;padding:6px 14px;border-radius:10px;border:2px solid var(--acc);background:var(--bg);color:var(--acc);cursor:pointer}
#bar label{font-size:14px;color:var(--mute);display:flex;align-items:center;gap:6px;min-height:44px}
@media (max-width:420px){.btns button{font-size:15px}dl{grid-template-columns:4.2em 1fr}}`;

const weekday = (d) => '星期' + '日一二三四五六'[new Date(d + 'T00:00:00Z').getUTCDay()];
const top = '<div class="top"><a href="/frontier/_listen">耳听点选</a><a href="/frontier/_access">开放程度</a><a href="/frontier/_visits">访问统计</a><a href="/frontier/">回到网站</a></div>';

function fmtUK(ms) {
  if (!ms) return '';
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    .formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  return `${p.month}-${p.day} ${p.hour}:${p.minute}`;
}

function shell(title, body, script = '') {
  return `<!doctype html><html lang="zh-Hans"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex, nofollow"><meta name="color-scheme" content="light dark"><meta name="referrer" content="same-origin"><link rel="icon" href="data:,">
<title>${esc(title)} · 每日AI科技前沿简报</title><style>${CSS}</style></head>
<body><div class="wrap">${top}${body}</div>${script}</body></html>`;
}

const MSG = {
  saved: ['ok', '存好了。'],
  nodb: ['err', '没连上数据库，这次没存上。'],
  dberr: ['err', '写数据库出错，这次没存上。过一会儿再点一次。'],
  bad: ['err', '没看懂这次提交，什么都没存。'],
};

// 列表页：最近 14 期
export function renderList(index, counts, { dbNote = '', msg = '' } = {}) {
  const f = MSG[msg];
  const flash = (f ? `<div class="flash ${f[0]}" role="status">${esc(f[1])}</div>` : '') + (dbNote ? `<div class="flash">${esc(dbNote)}</div>` : '');
  const rows = ((index && index.issues) || []).filter((x) => x && DATE_RE.test(String(x.date))).sort((a, b) => (a.date < b.date ? 1 : -1)).slice(0, LIST_DAYS);
  let list;
  if (!index) {
    list = '<p class="note" style="margin-top:14px">还没有点选页的条目：要等打开了耳听点选页（FD_LISTEN_PAGE）的那次发布以后才有。</p>';
  } else if (!rows.length) {
    list = '<p class="note" style="margin-top:14px">最近没有哪一期有“请你耳听”。</p>';
  } else {
    list = '<ul class="issues">' + rows.map((r) => {
      const n = Number(r.count) || 0;
      const batch = Number((r.groups || {}).batch) || 0;
      const done = counts ? Math.min(n, counts.get(r.date) || 0) : null;
      const state = done == null ? '读不到点了几处' : done === 0 ? '还没点' : done >= n ? `点完了（${done} 处）` : `点了 ${done} 处`;
      return `<li><a href="/frontier/_listen?date=${esc(r.date)}"><span><b>${esc(r.date.slice(5))}</b> <span class="no">${esc(weekday(r.date))}${r.edition ? ' · ' + esc(r.edition) : ''}</span>`
        + `<small>${n} 处${batch ? `（其中 ${batch} 条成批的多半是转写听错，可不听）` : ''} · ${esc(state)}</small></span><span class="go">去听 ›</span></a></li>`;
    }).join('') + '</ul>';
  }
  return shell('耳听点选', `<h1>请你耳听 · 逐条点选</h1>
<p class="note">只有你（带站长 Cookie 的浏览器）能打开这一页。每期审片列出的“请你耳听”在这里逐条放给你听，点“念对了／念错了／没听出来”，结果自动存下来，周六维护直接读。</p>
${flash}${list}
<a class="export" href="/frontier/_listen?export=json">导出全部结果（JSON）</a>
<p class="note" style="margin-top:8px">导出的文件里有每一条的日期、位置、原稿、转写、判断、关乎事实、你点的结果、备注和时间。</p>`);
}

function clipButtons(date, it, audio) {
  const clips = Array.isArray(it.clips) ? it.clips : [];
  const ok = clips.filter((c) => c && AUDIO_FILE[c.src] && audio[c.src] !== false && Number.isFinite(+c.a) && Number.isFinite(+c.b));
  const page = `<a href="/frontier/?date=${esc(date)}">打开这一期的网页</a>`;
  if (!clips.length) return `<p class="noclip">这一条没写具体时刻（或者没认出来），只能${page}，到播客或视频里找。</p>`;
  if (!ok.length) return `<p class="noclip">这一期网站上没有这段音频，去视频或播客里听（${page}）。</p>`;
  const fmt = (src, t) => {
    if (src !== '播客') return `${Math.round(t * 10) / 10}`;
    const n = Math.round(t);
    return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`;
  };
  return '<div class="clips">' + ok.map((c) => {
    const a = +c.a, b = +c.b;
    const span = c.src === '播客' ? `${fmt('播客', a)}–${fmt('播客', b)}` : `${fmt('视频', a)}–${fmt('视频', b)} 秒`;
    return `<button type="button" class="clip" data-url="/frontier/issues/${esc(date)}/audio/${AUDIO_FILE[c.src]}" data-a="${a}" data-b="${b}" data-label="${esc(c.label || c.src)}">▶ ${esc(c.label || c.src)}<small>放 ${esc(span)}</small></button>`;
  }).join('') + (clips.length > ok.length ? `<p class="noclip">另有 ${clips.length - ok.length} 处这一期网站上没有那段音频，去视频或播客里听。</p>` : '') + '</div>';
}

function card(date, it, vote, total, audio) {
  const id = esc(it.id);
  const pressed = (k) => (vote && vote.result === k ? 'true' : 'false');
  const judge = it.judge ? `<span class="pill">${esc(it.judge)}</span>` : '<span class="pill">没写判断</span>';
  const body = it.say || it.heard
    ? `<dl>${it.say ? `<dt>原稿</dt><dd>${esc(it.say)}</dd>` : ''}${it.heard ? `<dt>转写成</dt><dd>${esc(it.heard)}</dd>` : ''}<dt>判断</dt><dd>${esc(it.judge || '没写')}</dd></dl>`
    : `<dl><dt>说明</dt><dd>${esc(it.note || '（没写）')}</dd><dt>判断</dt><dd>${esc(it.judge || '没写')}</dd></dl>`;
  const basis = it.basis ? `<details class="basis"><summary>审片的依据</summary>${esc(it.basis)}</details>` : '';
  const state = vote ? `已选：${esc(RESULT[vote.result] || vote.result)}${vote.ts ? ' · ' + esc(fmtUK(vote.ts)) + '（英国时间）' : ''}` : '';
  return `<section class="card${vote ? ' done' : ''}" id="i-${id}" data-item="${id}">
<div class="head">${it.fact ? '<span class="pill fact">【事实】</span>' : ''}${judge}<span class="no">第 ${Number(it.n) || 0} 处／共 ${total} 处</span></div>
<div class="pos">${esc(it.pos || '（没写位置）')}</div>
${body}${basis}
${clipButtons(date, it, audio)}
<form class="vote" method="post" action="/frontier/_listen"><input type="hidden" name="date" value="${esc(date)}"><input type="hidden" name="item" value="${id}">
<input type="text" name="note" maxlength="${NOTE_MAX}" value="${esc(vote ? vote.note : '')}" placeholder="想补一句写这里（可不填；比如哪一处念错了）" aria-label="备注" autocomplete="off">
<div class="btns"><button type="submit" name="result" value="right" aria-pressed="${pressed('right')}">念对了</button><button type="submit" name="result" value="wrong" aria-pressed="${pressed('wrong')}">念错了</button><button type="submit" name="result" value="unsure" aria-pressed="${pressed('unsure')}">没听出来</button></div>
<p class="state" aria-live="polite">${state}</p></form></section>`;
}

// 逐条点选页。votes：Map 或 null（读不到）
export function renderIssue(data, votes, { dbNote = '', msg = '' } = {}) {
  const date = String(data.date);
  const items = data.items.filter((it) => it && ITEM_RE.test(String(it.id)));
  const audio = data.audio || {};
  const total = items.length;
  const v = (it) => (votes ? votes.get(it.id) : null);
  const done = items.filter((it) => v(it)).length;
  const facts = items.filter((it) => it.fact).length;
  const main = items.filter((it) => it.group !== 'batch');
  const batch = items.filter((it) => it.group === 'batch');
  const f = MSG[msg];
  const flash = (f ? `<div class="flash ${f[0]}" role="status">${esc(f[1])}</div>` : '') + (dbNote ? `<div class="flash">${esc(dbNote)}</div>` : '');
  const sum = `<div class="sum"><span class="pill">共 ${total} 处</span>${facts ? `<span class="pill fact">【事实】${facts} 处，排在最前</span>` : ''}`
    + `<span class="pill" id="done">${votes ? `已点 ${done} 处` : '读不到已点的结果'}</span>${batch.length ? `<span class="pill">成批的 ${batch.length} 条在最后，可不听</span>` : ''}</div>`;
  const cards = main.map((it) => card(date, it, v(it), total, audio)).join('');
  const folded = batch.length ? `<details class="batch"><summary>多半是转写听错的成批条目 · ${batch.length} 条 · 可不听（点开）</summary>${batch.map((it) => card(date, it, v(it), total, audio)).join('')}</details>` : '';
  return shell(`耳听 ${date}`, `<h1>${esc(date)} ${esc(weekday(date))}${data.edition ? ' · ' + esc(data.edition) : ''}</h1>
<p class="note">点“▶”放那一处（前 2 秒到后 4 秒，放完自动停，可以重播；底下的条可以勾“前后多放 5 秒”）。听完点念对了、念错了或没听出来，可以改，以最后一次为准。时刻：播客按网页上的播客，视频按视频的旁白。</p>
${flash}${sum}${cards || '<p class="note" style="margin-top:14px">这一期没有条目。</p>'}${folded}
<p class="note" style="margin-top:22px"><a href="/frontier/_listen">← 回到列表</a></p>
<div id="bar" role="region" aria-label="正在放"><div class="in"><span class="what"><b id="bar-l"></b><span id="bar-t"></span></span>
<label><input type="checkbox" id="bar-x">前后多放 5 秒</label><button type="button" id="bar-r">重播</button><button type="button" id="bar-s">停</button><progress id="bar-p" max="1" value="0"></progress></div></div>`, SCRIPT);
}

// 页面脚本：放音频（一种音频一个 <audio>，先要元数据再跳，照 site/v3/app.js 播客的做法）；表单改成不刷新提交
const SCRIPT = `<script>
(function () {
  var players = {}, cur = null, extra = 0, raf = 0;
  var bar = document.getElementById('bar'), L = document.getElementById('bar-l'), T = document.getElementById('bar-t'), P = document.getElementById('bar-p');
  var X = document.getElementById('bar-x');
  if (!bar) return;
  function fmt(t) { t = Math.max(0, t); var m = Math.floor(t / 60), s = Math.floor(t % 60); return m + ':' + (s < 10 ? '0' : '') + s; }
  function audio(url) {
    var a = players[url];
    if (a) return a;
    a = players[url] = new Audio();
    a.preload = 'none';
    a.src = url;
    a.addEventListener('loadedmetadata', function () { if (a._pend != null) { try { a.currentTime = a._pend; } catch (e) {} a._pend = null; } });
    a.addEventListener('ended', function () { if (cur && cur.a === a) stop(); });
    a.addEventListener('error', function () { if (cur && cur.a === a) { T.textContent = '　音频没打开（网络或文件问题），过一会儿再点'; stop(true); } });
    return a;
  }
  function stop(keep) {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
    Object.keys(players).forEach(function (k) { try { players[k].pause(); } catch (e) {} });
    if (cur && cur.btn) cur.btn.classList.remove('playing');
    if (!keep) { bar.classList.remove('on'); }
    cur = null;
  }
  function loop() {
    if (!cur) return;
    var a = cur.a, t = a.currentTime || 0;
    if (a._pend == null && !a.seeking && t >= cur.e) { stop(); return; }
    P.value = Math.max(0, Math.min(1, (t - cur.s) / Math.max(0.1, cur.e - cur.s)));
    T.textContent = '　' + fmt(t) + '（放到 ' + fmt(cur.e) + ' 停）';
    raf = requestAnimationFrame(loop);
  }
  function play(btn) {
    stop(true);
    var s = Math.max(0, +btn.getAttribute('data-a') - extra), e = +btn.getAttribute('data-b') + extra;
    var a = audio(btn.getAttribute('data-url'));
    cur = { a: a, s: s, e: e, btn: btn };
    btn.classList.add('playing');
    L.textContent = btn.getAttribute('data-label');
    T.textContent = '　正在打开…';
    P.value = 0;
    bar.classList.add('on');
    if (a.readyState < 1) { a._pend = s; try { a.currentTime = s; } catch (x) {} } else { a.currentTime = s; }
    var pr = a.play();
    if (pr && pr.catch) pr.catch(function (err) { if (err && err.name !== 'AbortError') { T.textContent = '　放不了（' + err.name + '），再点一次'; } });
    raf = requestAnimationFrame(loop);
  }
  X.addEventListener('change', function () { extra = X.checked ? 5 : 0; });
  document.getElementById('bar-s').addEventListener('click', function () { stop(); });
  document.getElementById('bar-r').addEventListener('click', function () { if (cur && cur.btn) play(cur.btn); else if (bar._last) play(bar._last); });
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest && ev.target.closest('button.clip');
    if (b) { bar._last = b; play(b); return; }
    var v = ev.target.closest && ev.target.closest('form.vote button[name=result]');
    if (!v || !window.fetch || !window.URLSearchParams) return;
    ev.preventDefault();
    var form = v.form, st = form.querySelector('.state'), btns = form.querySelectorAll('button[name=result]');
    var body = new URLSearchParams();                // 按 name 取输入框：表单控件集合上的 item 是“取第几个”的方法，不是叫 item 的那一栏
    ['date', 'item', 'note'].forEach(function (k) { var el = form.querySelector('input[name=' + k + ']'); body.set(k, el ? el.value : ''); });
    body.set('result', v.value);
    st.className = 'state'; st.textContent = '正在存…';
    Array.prototype.forEach.call(btns, function (b) { b.disabled = true; });
    fetch(form.action, { method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json' }, body: body })
      .then(function (r) { return r.json().catch(function () { return { ok: false, error: '回应看不懂（' + r.status + '）' }; }); })
      .then(function (j) {
        Array.prototype.forEach.call(btns, function (b) { b.disabled = false; });
        if (!j || !j.ok) { st.className = 'state err'; st.textContent = (j && j.error) || '没存上，再点一次'; return; }
        Array.prototype.forEach.call(btns, function (b) { b.setAttribute('aria-pressed', b.value === j.result ? 'true' : 'false'); });
        var cardEl = form.closest('.card');
        if (cardEl && !cardEl.classList.contains('done')) { cardEl.classList.add('done'); var d = document.getElementById('done'); if (d) { var n = (+(d.getAttribute('data-n') || d.textContent.replace(/\\D/g, '')) || 0) + 1; d.setAttribute('data-n', n); d.textContent = '已点 ' + n + ' 处'; } }
        st.textContent = '已选：' + j.label + (j.when ? ' · ' + j.when + '（英国时间）' : '') + ' · 存好了';
      })
      .catch(function () { Array.prototype.forEach.call(btns, function (b) { b.disabled = false; }); st.className = 'state err'; st.textContent = '网络没通，没存上，再点一次'; });
  });
})();
</script>`;

// ===================== GET =====================

export async function listenGet(req, url, env, now = Date.now()) {
  if (url.searchParams.get('export') === 'json') return exportVotes(req, url, env, now);
  const db = env && env.VISITS;
  const msg = Object.prototype.hasOwnProperty.call(MSG, url.searchParams.get('msg') || '') ? url.searchParams.get('msg') : '';
  const date = url.searchParams.get('date') || '';
  let html;
  if (DATE_RE.test(date)) {
    const data = await readIssue(env, url, date);
    if (!data) {
      html = shell(`耳听 ${date}`, `<h1>${esc(date)}</h1><p class="note" style="margin-top:12px">这一期没有点选页的条目：可能这一期没有“请你耳听”，或者它发布时还没打开耳听点选页。</p><p class="note"><a href="/frontier/_listen">← 回到列表</a></p>`);
    } else {
      let votes = null, dbNote = '';
      if (!db) dbNote = '没连上数据库（Worker 缺少 VISITS 绑定）：条目照常显示，点了存不上。';
      else {
        try { votes = await loadVotes(db, date); } catch (e) { dbNote = `读数据库出错（${String((e && e.message) || e).slice(0, 120)}）：条目照常显示，看不到已选的结果；点了可能也存不上。`; }
      }
      html = renderIssue(data, votes, { dbNote, msg });
    }
  } else {
    const index = await readJSON(env, url, 'index.json');
    let counts = null, dbNote = '';
    const rows = ((index && index.issues) || []).map((x) => String((x && x.date) || '')).filter((d) => DATE_RE.test(d)).sort().reverse().slice(0, LIST_DAYS);
    if (!db) dbNote = '没连上数据库（Worker 缺少 VISITS 绑定）：看不到点了几处，点了也存不上。';
    else if (rows.length) {
      try { counts = await countVotes(db, rows[rows.length - 1]); } catch (e) { dbNote = `读数据库出错（${String((e && e.message) || e).slice(0, 120)}）：看不到点了几处。`; }
    } else counts = new Map();
    html = renderList(index, counts, { dbNote, msg });
  }
  return new Response(req.method === 'HEAD' ? null : html, { status: 200, headers: PAGE_HEADERS });
}

// 导出全部结果（JSON），按日期新到旧、条目在页面上的先后。每条带上条目本身的字（从 _listen/<日期>.json 查），不只有编号
async function exportVotes(req, url, env, now) {
  const db = env && env.VISITS;
  const h = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...BASE };
  if (!db) return new Response(JSON.stringify({ ok: false, error: '没连上数据库' }), { status: 503, headers: h });
  let rows;
  try {
    const r = await db.prepare('SELECT date, item, result, note, ts FROM listen_votes ORDER BY date DESC, ts ASC').all();
    rows = (r && r.results) || [];
  } catch (e) {
    if (/no such table/i.test(String((e && e.message) || e))) rows = [];
    else return new Response(JSON.stringify({ ok: false, error: '读数据库出错' }), { status: 503, headers: h });
  }
  const issues = new Map();
  for (const d of [...new Set(rows.map((x) => String(x.date)))]) {
    const data = await readIssue(env, url, d);
    issues.set(d, new Map(((data && data.items) || []).map((it) => [String(it.id), it])));
  }
  const out = rows.map((x) => {
    const it = (issues.get(String(x.date)) || new Map()).get(String(x.item));
    return {
      日期: String(x.date), 条目: String(x.item), 结果: RESULT[x.result] || String(x.result), 结果码: String(x.result), 备注: String(x.note || ''),
      点选时间: new Date(Number(x.ts) || 0).toISOString(),
      ...(it ? { 第几处: it.n, 位置: it.pos, 原稿: it.say, 转写成: it.heard, 说明: it.note, 判断: it.judge, 关乎事实: it.fact, 依据: it.basis, 分组: it.group }
        : { 找不到条目: '这一期的条目里没有这个编号（审片结论改过，或者那一期不在网站上了）' }),
    };
  }).sort((a, b) => (a.日期 === b.日期 ? (a.第几处 || 999) - (b.第几处 || 999) : (a.日期 < b.日期 ? 1 : -1)));
  const body = JSON.stringify({
    说明: '耳听点选页的结果（https://wenlongzhang.com/frontier/_listen）。每条一行，改过的以最后一次为准；时间是 UTC。结果：念对了／念错了／没听出来。',
    导出于: new Date(now).toISOString(), 条数: out.length, 结果: out,
  }, null, 1);
  const day = new Date(now).toISOString().slice(0, 10);
  h['Content-Disposition'] = `attachment; filename="listen-votes-${day}.json"; filename*=UTF-8''${encodeURIComponent('耳听结果_' + day + '.json')}`;
  return new Response(req.method === 'HEAD' ? null : body, { status: 200, headers: h });
}

// ===================== POST =====================

function reply(req, status, data, back) {
  if ((req.headers.get('Accept') || '').includes('application/json')) {
    return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...BASE } });
  }
  return new Response(null, { status: 303, headers: { Location: back, 'Cache-Control': 'no-store', ...BASE } });
}

// POST /frontier/_listen（index.js 已确认是站长）
export async function listenPost(req, env, now = Date.now()) {
  if (req.headers.get('Origin') !== SITE_ORIGIN) {
    return new Response(JSON.stringify({ ok: false, error: '只能从网站页面提交' }), { status: 403, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...BASE } });
  }
  const bad = (status, error) => reply(req, status, { ok: false, error }, `${LISTEN_PATH}?msg=bad`);
  const type = (req.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase();
  if (type !== 'application/x-www-form-urlencoded') return bad(415, '只收表单');
  const len = Number(req.headers.get('Content-Length'));
  if (Number.isFinite(len) && len > FORM_MAX) return bad(413, '内容太长了');
  let raw;
  try { raw = await req.text(); } catch { return bad(400, '没读到内容'); }
  if (new TextEncoder().encode(raw).byteLength > FORM_MAX) return bad(413, '内容太长了');
  const form = new URLSearchParams(raw);
  const date = String(form.get('date') || '');
  const item = String(form.get('item') || '');
  const result = String(form.get('result') || '');
  let note = String(form.get('note') || '').replace(/[\u0000-\u001F\u007F​-‏‪-‮⁠-⁤﻿]+/g, ' ').replace(/ {2,}/g, ' ').trim();
  if (!DATE_RE.test(date) || !ITEM_RE.test(item) || !Object.prototype.hasOwnProperty.call(RESULT, result)) return bad(400, '没看懂这次提交，什么都没存');
  if (Array.from(note).length > NOTE_MAX) return bad(400, `备注最多 ${NOTE_MAX} 个字`);
  const url = new URL(req.url);
  const back = (msg) => `${LISTEN_PATH}?date=${date}&msg=${msg}#i-${item}`;
  const data = await readIssue(env, url, date);
  if (!data || !data.items.some((it) => it && it.id === item)) return reply(req, 400, { ok: false, error: '这一期没有这一条' }, back('bad'));
  const db = env && env.VISITS;
  if (!db) return reply(req, 503, { ok: false, error: '没连上数据库，这次没存上' }, back('nodb'));
  try {
    await db.prepare(CREATE_TABLE).run();
    await db.prepare(UPSERT).bind(date, item, result, note, now).run();
  } catch (e) {
    console.log(`耳听点选：写数据库出错（${String((e && e.name) || 'error')}）`);
    return reply(req, 503, { ok: false, error: '写数据库出错，这次没存上；过一会儿再点一次' }, back('dberr'));
  }
  return reply(req, 200, { ok: true, date, item, result, label: RESULT[result], note, ts: now, when: fmtUK(now) }, back('saved'));
}
