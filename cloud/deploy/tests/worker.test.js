// Worker 的本机测试：cd cloud/deploy && node --test tests/worker.test.js（Node 22 及以上，不用装任何东西、不联网、不需要 wrangler）。
// 静态文件用假的对象代替；它和 Cloudflare 真的静态文件一样，不认 Range（总是回整段）。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker, { parseRange, cacheFor, CACHE, validateFeedback, RATE, FEEDBACK_LIMITS } from '../src/index.js';

const ORIGIN = 'https://wenlongzhang.com';
const AUDIO = new Uint8Array(100000).map((_, i) => i % 251);
const FILES = {
  '/frontier/index.html': ['text/html; charset=utf-8', '<!doctype html><meta name="robots" content="noindex, nofollow"><title>简报</title>'],
  '/frontier/past/index.html': ['text/html; charset=utf-8', '<!doctype html><title>往期</title>'],
  '/frontier/app.js': ['text/javascript', 'var x=1;'],
  '/frontier/issues/index.js': ['text/javascript', 'window.FD_INDEX={};'],
  '/frontier/issues/2026-11-08/issue.js': ['text/javascript', 'window.FD_ISSUES={};'],
  '/frontier/issues/2026-11-08/img/card-800.webp': ['image/webp', 'webp'],
  '/frontier/issues/2026-11-08/fonts/body-kai.woff2': ['font/woff2', 'woff2'],
  '/frontier/issues/2026-11-08/audio/podcast.mp3': ['audio/mpeg', AUDIO],
  '/frontier/vendor/echarts.min.js': ['text/javascript', 'echarts'],
};
const seen = [];
const ASSETS = {
  async fetch(req) {
    seen.push(req);
    const p = new URL(req.url).pathname;
    const f = FILES[p];
    if (!f) return new Response('nope', { status: 404 });
    if (req.headers.get('If-None-Match') === '"v1"') return new Response(null, { status: 304, headers: { ETag: '"v1"' } });
    const body = typeof f[1] === 'string' ? new TextEncoder().encode(f[1]) : f[1];
    // 分成几块送出，模拟真实的流
    const chunks = [];
    for (let i = 0; i < body.length; i += 16384) chunks.push(body.subarray(i, i + 16384));
    const stream = new ReadableStream({ pull(c) { if (chunks.length) c.enqueue(chunks.shift()); else c.close(); } });
    return new Response(req.method === 'HEAD' ? null : stream, {
      status: 200, headers: { 'Content-Type': f[0], 'Content-Length': String(body.length), ETag: '"v1"' },
    });
  },
};
const env = { ASSETS };
const hit = (path, init = {}) => worker.fetch(new Request(ORIGIN + path, init), env);

test('首页 200，带 noindex 头、每次核对缓存', async () => {
  const res = await hit('/frontier/');
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('X-Robots-Tag'), 'noindex, nofollow');
  assert.equal(res.headers.get('Cache-Control'), 'no-cache');
  assert.equal(res.headers.get('X-Content-Type-Options'), 'nosniff');
  assert.match(await res.text(), /noindex/);
});

test('/frontier 跳到 /frontier/，问号后面的参数带上', async () => {
  const res = await hit('/frontier?date=2026-11-08');
  assert.equal(res.status, 301);
  assert.equal(res.headers.get('Location'), '/frontier/?date=2026-11-08');
  assert.equal(res.headers.get('X-Robots-Tag'), 'noindex, nofollow');
});

test('/frontier/past 跳到 /frontier/past/，目录给 index.html', async () => {
  assert.equal((await hit('/frontier/past')).headers.get('Location'), '/frontier/past/');
  const res = await hit('/frontier/past/');
  assert.equal(res.status, 200);
  assert.match(await res.text(), /往期/);
});

test('每期好记的网址 /frontier/日期/ 跳到 ?date=', async () => {
  for (const p of ['/frontier/2026-11-09/', '/frontier/2026-11-09']) {
    const res = await hit(p);
    assert.equal(res.status, 302);
    assert.equal(res.headers.get('Location'), '/frontier/?date=2026-11-09');
  }
});

test('不在 /frontier 下的一律 404，不去读静态文件', async () => {
  const n = seen.length;
  for (const p of ['/', '/memory/', '/journals/', '/frontierx', '/frontier-old/index.html']) {
    const res = await hit(p);
    assert.equal(res.status, 404, p);
  }
  assert.equal(seen.length, n);
});

test('只许 GET 和 HEAD', async () => {
  for (const m of ['POST', 'PUT', 'DELETE', 'PATCH']) {
    const res = await hit('/frontier/', { method: m });
    assert.equal(res.status, 405, m);
    assert.equal(res.headers.get('Allow'), 'GET, HEAD');
    assert.equal(res.headers.get('X-Robots-Tag'), 'noindex, nofollow');
  }
  const head = await hit('/frontier/', { method: 'HEAD' });
  assert.equal(head.status, 200);
  assert.equal(await head.text(), '');
});

test('找不到的文件给中文 404 页，不缓存，也带 noindex', async () => {
  const res = await hit('/frontier/issues/2099-01-01/issue.js');
  assert.equal(res.status, 404);
  assert.equal(res.headers.get('Cache-Control'), 'no-store');
  assert.equal(res.headers.get('X-Robots-Tag'), 'noindex, nofollow');
  assert.match(await res.text(), /没有这个页面/);
});

test('缓存分两类：音频图片字体 7 天；网页和往期目录每次核对；程序和每期数据 10 分钟', async () => {
  assert.equal((await hit('/frontier/issues/2026-11-08/img/card-800.webp')).headers.get('Cache-Control'), CACHE.media);
  assert.equal((await hit('/frontier/issues/2026-11-08/fonts/body-kai.woff2')).headers.get('Cache-Control'), CACHE.media);
  assert.equal((await hit('/frontier/issues/2026-11-08/audio/podcast.mp3')).headers.get('Cache-Control'), CACHE.media);
  assert.equal((await hit('/frontier/issues/index.js')).headers.get('Cache-Control'), 'no-cache');
  assert.equal((await hit('/frontier/issues/2026-11-08/issue.js')).headers.get('Cache-Control'), CACHE.code);
  assert.equal((await hit('/frontier/app.js')).headers.get('Cache-Control'), CACHE.code);
  assert.equal((await hit('/frontier/vendor/echarts.min.js')).headers.get('Cache-Control'), CACHE.code);
  assert.equal(cacheFor('/frontier/past/'), 'no-cache');
  assert.equal(cacheFor('/frontier/index.html'), 'no-cache');
});

test('没变的文件回 304，照样带响应头', async () => {
  const res = await hit('/frontier/app.js', { headers: { 'If-None-Match': '"v1"' } });
  assert.equal(res.status, 304);
  assert.equal(res.headers.get('X-Robots-Tag'), 'noindex, nofollow');
});

test('音频：没带 Range 回整段并声明能拖动', async () => {
  const res = await hit('/frontier/issues/2026-11-08/audio/podcast.mp3');
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('Accept-Ranges'), 'bytes');
  const buf = new Uint8Array(await res.arrayBuffer());
  assert.deepEqual(buf, AUDIO);
});

test('音频：带 Range 回 206 和正确的那一段（跨块、到结尾、只要最后几字节）', async () => {
  const cases = [['bytes=0-1', 0, 1], ['bytes=16380-16390', 16380, 16390], ['bytes=50000-', 50000, 99999],
    ['bytes=-500', 99500, 99999], ['bytes=99999-200000', 99999, 99999]];
  for (const [r, a, b] of cases) {
    const res = await hit('/frontier/issues/2026-11-08/audio/podcast.mp3', { headers: { Range: r } });
    assert.equal(res.status, 206, r);
    assert.equal(res.headers.get('Content-Range'), `bytes ${a}-${b}/100000`, r);
    assert.equal(res.headers.get('Content-Length'), String(b - a + 1), r);
    assert.equal(res.headers.get('X-Robots-Tag'), 'noindex, nofollow');
    const buf = new Uint8Array(await res.arrayBuffer());
    assert.deepEqual(buf, AUDIO.subarray(a, b + 1), r);
  }
});

test('音频：Range 超出文件回 416；写法不认识就回整段', async () => {
  const bad = await hit('/frontier/issues/2026-11-08/audio/podcast.mp3', { headers: { Range: 'bytes=100000-' } });
  assert.equal(bad.status, 416);
  assert.equal(bad.headers.get('Content-Range'), 'bytes */100000');
  const multi = await hit('/frontier/issues/2026-11-08/audio/podcast.mp3', { headers: { Range: 'bytes=0-1,5-6' } });
  assert.equal(multi.status, 200);
  const stale = await hit('/frontier/issues/2026-11-08/audio/podcast.mp3', { headers: { Range: 'bytes=0-1', 'If-Range': '"old"' } });
  assert.equal(stale.status, 200);
});

// 线上的静态文件回应不带 Content-Length（11-09 晚上线后才发现，workers-sdk #8967）：假对象照样去掉它再测一遍
const ASSETS_NOLEN = {
  async fetch(req) {
    const res = await ASSETS.fetch(req);
    const h = new Headers(res.headers);
    h.delete('Content-Length');
    return new Response(res.body, { status: res.status, headers: h });
  },
};
const hitNoLen = (path, init = {}) => worker.fetch(new Request(ORIGIN + path, init), { ASSETS: ASSETS_NOLEN });

test('音频（线上那样不带长度）：带 Range 照样回 206 和正确的那一段', async () => {
  const cases = [['bytes=0-1', 0, 1], ['bytes=16380-16390', 16380, 16390], ['bytes=50000-', 50000, 99999],
    ['bytes=-500', 99500, 99999], ['bytes=99999-200000', 99999, 99999]];
  for (const [r, a, b] of cases) {
    const res = await hitNoLen('/frontier/issues/2026-11-08/audio/podcast.mp3', { headers: { Range: r } });
    assert.equal(res.status, 206, r);
    assert.equal(res.headers.get('Content-Range'), `bytes ${a}-${b}/100000`, r);
    assert.equal(res.headers.get('Content-Length'), String(b - a + 1), r);
    assert.equal(res.headers.get('X-Robots-Tag'), 'noindex, nofollow');
    const buf = new Uint8Array(await res.arrayBuffer());
    assert.deepEqual(buf, AUDIO.subarray(a, b + 1), r);
  }
});

test('音频（不带长度）：超出回 416；写法不认识、If-Range 过期、没带 Range 都回完整的整段', async () => {
  const bad = await hitNoLen('/frontier/issues/2026-11-08/audio/podcast.mp3', { headers: { Range: 'bytes=100000-' } });
  assert.equal(bad.status, 416);
  assert.equal(bad.headers.get('Content-Range'), 'bytes */100000');
  for (const headers of [{ Range: 'bytes=0-1,5-6' }, { Range: 'bytes=0-1', 'If-Range': '"old"' }, {}]) {
    const res = await hitNoLen('/frontier/issues/2026-11-08/audio/podcast.mp3', { headers });
    assert.equal(res.status, 200, JSON.stringify(headers));
    assert.deepEqual(new Uint8Array(await res.arrayBuffer()), AUDIO, JSON.stringify(headers));
  }
  const head = await hitNoLen('/frontier/issues/2026-11-08/audio/podcast.mp3', { method: 'HEAD', headers: { Range: 'bytes=0-1' } });
  assert.equal(head.status, 200);
});

test('非媒体文件不理 Range', async () => {
  const res = await hit('/frontier/app.js', { headers: { Range: 'bytes=0-1' } });
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('Accept-Ranges'), null);
  assert.equal(await res.text(), 'var x=1;');
});

test('parseRange 各种写法', () => {
  assert.deepEqual(parseRange('bytes=0-9', 10), { start: 0, end: 9 });
  assert.deepEqual(parseRange('bytes=5-', 10), { start: 5, end: 9 });
  assert.deepEqual(parseRange('bytes=-3', 10), { start: 7, end: 9 });
  assert.deepEqual(parseRange('bytes=-30', 10), { start: 0, end: 9 });
  assert.equal(parseRange('bytes=-0', 10), 'bad');
  assert.equal(parseRange('bytes=10-12', 10), 'bad');
  assert.equal(parseRange('bytes=6-5', 10), 'bad');
  assert.equal(parseRange('items=0-1', 10), null);
  assert.equal(parseRange('', 10), null);
});


// ===================== 读者反馈：POST /frontier/feedback（11-10 加）=====================
// GitHub 接口用假的 fetch 代替（不联网）；console.log 也接住，核对日志里没有令牌、没有反馈内容。
const TOKEN = 'github_pat_TEST_ONLY_not_a_real_token_1234567890';
const FB_URL = 'https://api.github.com/repos/dylan-zhang-wl/frontier-daily/actions/workflows/feedback.yml/dispatches';
const GOOD = { date: '2026-11-09', text: '头条第 2 条的金额和原文对不上', name: '妈妈', where: '播客 7:33', lang: 'zh', website: '' };

async function withFakes(fn, { status = 204, throws = false } = {}) {
  const calls = [], logs = [];
  const realFetch = globalThis.fetch, realLog = console.log;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    if (throws) throw new TypeError('network down');
    return new Response(status === 204 ? null : JSON.stringify({ message: 'Bad credentials' }), { status });
  };
  console.log = (...a) => logs.push(a.join(' '));
  try { await fn(calls, logs); } finally { globalThis.fetch = realFetch; console.log = realLog; }
}
const post = (body, { origin = ORIGIN, type = 'application/json', token = TOKEN, ip = '203.0.113.7', raw } = {}) => {
  const headers = { 'Content-Type': type, 'CF-Connecting-IP': ip };
  if (origin) headers.Origin = origin;
  const req = new Request(ORIGIN + '/frontier/feedback', { method: 'POST', headers, body: raw != null ? raw : JSON.stringify(body) });
  return worker.fetch(req, token ? { ASSETS, GH_FEEDBACK_TOKEN: token } : { ASSETS });
};

test('反馈：没设机密变量回 503，说“反馈功能还没设置好”，不去调 GitHub', async () => {
  RATE.seen.clear();
  await withFakes(async (calls) => {
    const res = await post(GOOD, { token: '' });
    assert.equal(res.status, 503);
    assert.equal(res.headers.get('Content-Type'), 'application/json; charset=utf-8');
    assert.equal(res.headers.get('Cache-Control'), 'no-store');
    assert.equal(res.headers.get('X-Robots-Tag'), 'noindex, nofollow');
    const d = await res.json();
    assert.equal(d.ok, false);
    assert.match(d.error, /反馈功能还没设置好/);
    assert.equal(calls.length, 0);
  });
});

test('反馈：Origin 不是 https://wenlongzhang.com（或没有）回 403', async () => {
  RATE.seen.clear();
  await withFakes(async (calls) => {
    for (const origin of ['https://evil.example', 'http://wenlongzhang.com', 'https://wenlongzhang.com.evil.example', 'null', '']) {
      const res = await post(GOOD, { origin });
      assert.equal(res.status, 403, origin);
    }
    assert.equal(calls.length, 0);
  });
});

test('反馈：只收 JSON；坏 JSON、太大的请求都不转交', async () => {
  RATE.seen.clear();
  await withFakes(async (calls) => {
    assert.equal((await post(GOOD, { type: 'text/plain' })).status, 415);
    assert.equal((await post(GOOD, { type: 'application/x-www-form-urlencoded' })).status, 415);
    assert.equal((await post(null, { raw: '{"date":', ip: '203.0.113.8' })).status, 400);
    assert.equal((await post(null, { raw: '[1,2]', ip: '203.0.113.8' })).status, 400);
    const big = JSON.stringify({ ...GOOD, text: 'x'.repeat(FEEDBACK_LIMITS.body) });
    assert.equal((await post(null, { raw: big, ip: '203.0.113.9' })).status, 413);
    assert.equal(calls.length, 0);
  });
});

test('反馈：各栏校验（期号、必填、长度、控制字符）', () => {
  assert.equal(validateFeedback(GOOD).ok, true);
  for (const date of ['', '2026-1-9', '2026-13-01', '2026-02-30', '20261109', '2026-11-09T00:00', '1999-01-01', 12]) {
    assert.equal(validateFeedback({ ...GOOD, date }).ok, false, String(date));
  }
  assert.equal(validateFeedback({ ...GOOD, text: '   \n ' }).ok, false);
  assert.equal(validateFeedback({ ...GOOD, text: undefined }).ok, false);
  assert.equal(validateFeedback({ ...GOOD, text: '错'.repeat(1000) }).ok, true);           // 1000 个汉字刚好
  assert.equal(validateFeedback({ ...GOOD, text: '错'.repeat(1001) }).ok, false);
  assert.equal(validateFeedback({ ...GOOD, text: '😀'.repeat(1000) }).ok, true);            // 按“字”数，不按 UTF-16 长度
  assert.equal(validateFeedback({ ...GOOD, name: '名'.repeat(41) }).ok, false);
  assert.equal(validateFeedback({ ...GOOD, where: '位'.repeat(81) }).ok, false);
  assert.equal(validateFeedback(null).ok, false);
  assert.equal(validateFeedback([]).ok, false);
  const v = validateFeedback({ date: '2026-11-09', text: ' 第一行\r\n第二行\u0007‮ ', name: '妈\n妈', where: 7, lang: 'fr' });
  assert.deepEqual(v.data, { date: '2026-11-09', text: '第一行\n第二行', name: '妈 妈', where: '', lang: 'zh' });
});

test('反馈：蜜罐栏有值，照样回“收到”，但不转交', async () => {
  RATE.seen.clear();
  await withFakes(async (calls) => {
    const res = await post({ ...GOOD, website: 'http://spam.example' });
    assert.equal(res.status, 202);
    assert.deepEqual(await res.json(), { ok: true });
    assert.equal(calls.length, 0);
  });
});

test('反馈：合格的转交 GitHub（feedback.yml、main、各栏作为 inputs），回 202；日志不记令牌和内容', async () => {
  RATE.seen.clear();
  await withFakes(async (calls, logs) => {
    const res = await post(GOOD);
    assert.equal(res.status, 202);
    const text = await res.text();
    assert.deepEqual(JSON.parse(text), { ok: true });
    assert.ok(!text.includes(TOKEN));
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, FB_URL);
    const h = new Headers(calls[0].init.headers);
    assert.equal(calls[0].init.method, 'POST');
    assert.equal(h.get('Authorization'), 'Bearer ' + TOKEN);
    assert.equal(h.get('Accept'), 'application/vnd.github+json');
    assert.ok(h.get('User-Agent'));
    const sent = JSON.parse(calls[0].init.body);
    assert.deepEqual(sent, { ref: 'main', inputs: { date: '2026-11-09', text: GOOD.text, name: '妈妈', where: '播客 7:33', lang: 'zh' } });
    for (const v of Object.values(sent.inputs)) assert.equal(typeof v, 'string');
    const all = logs.join('\n');
    assert.ok(!all.includes(TOKEN), '日志里有令牌');
    assert.ok(!all.includes(GOOD.text), '日志里有反馈内容');
    assert.match(all, /204/);
  });
});

test('反馈：GitHub 回错或连不上时回 502“稍后再试”，不把 GitHub 的话转给读者', async () => {
  RATE.seen.clear();
  await withFakes(async () => {
    const res = await post(GOOD, { ip: '198.51.100.1' });
    assert.equal(res.status, 502);
    const d = await res.json();
    assert.match(d.error, /稍后再试/);
    assert.ok(!JSON.stringify(d).includes('Bad credentials'));
  }, { status: 401 });
  await withFakes(async () => {
    const res = await post(GOOD, { ip: '198.51.100.2' });
    assert.equal(res.status, 502);
  }, { throws: true });
});

test('反馈：同一 IP 10 分钟内最多 5 次，第 6 次回 429；别的 IP 不受影响', async () => {
  RATE.seen.clear();
  await withFakes(async (calls) => {
    for (let i = 0; i < RATE.max; i++) assert.equal((await post(GOOD, { ip: '192.0.2.1' })).status, 202, `第 ${i + 1} 次`);
    const res = await post(GOOD, { ip: '192.0.2.1' });
    assert.equal(res.status, 429);
    assert.equal(res.headers.get('Retry-After'), '600');
    assert.equal((await post(GOOD, { ip: '192.0.2.2' })).status, 202);
    assert.equal(calls.length, RATE.max + 1);
  });
  RATE.seen.clear();
});

test('反馈：只有 POST /frontier/feedback 这一条口子；别处 POST 仍回 405，GET 这个地址照常 404', async () => {
  for (const p of ['/frontier/', '/frontier/feedback/', '/frontier/feedbackx', '/frontier/issues/index.js']) {
    const res = await worker.fetch(new Request(ORIGIN + p, { method: 'POST', headers: { Origin: ORIGIN, 'Content-Type': 'application/json' }, body: '{}' }), { ASSETS, GH_FEEDBACK_TOKEN: TOKEN });
    assert.equal(res.status, 405, p);
  }
  for (const m of ['PUT', 'DELETE', 'PATCH']) {
    const res = await worker.fetch(new Request(ORIGIN + '/frontier/feedback', { method: m }), { ASSETS, GH_FEEDBACK_TOKEN: TOKEN });
    assert.equal(res.status, 405, m);
  }
  assert.equal((await hit('/frontier/feedback')).status, 404);
  assert.equal((await worker.fetch(new Request(ORIGIN + '/feedback', { method: 'POST' }), env)).status, 404);
});


// ===================== 匿名访问统计、站长钥匙、统计页（11-10 加）=====================
// 假的 D1：用 Node 自带的 SQLite（node:sqlite，Node 22.13 起不用加参数；会打印一行“实验功能”的提示，不影响）建一个内存数据库，
// 按 migrations/0001_visits.sql 建表，接口照 D1 的 prepare().bind().run()/all()、batch() 写。这样 SQL 是真跑的。
// 钥匙用测试专用的假值，不是真钥匙。
import { readFileSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import {
  playStarts, playInfo, cleanPath, pageKind, writeVisit, buildRecord, cleanupVisits, INDEX_CACHE, CLEANUP_EVERY, PLAY_ONCE_MS, RETENTION_DAYS, ukDay,
} from '../src/visits.js';
import { collectStats, toCSV } from '../src/stats.js';

const MIGRATION = readFileSync(new URL('../migrations/0001_visits.sql', import.meta.url), 'utf8');
class FakeStmt {
  constructor(db, q, args = []) { this.db = db; this.q = q; this.args = args; }
  bind(...a) { return new FakeStmt(this.db, this.q, a); }
  check() { this.db.log.push(this.q); if (this.db.fail) throw new Error('D1 坏了（测试）'); }
  async run() {
    this.check();
    const r = this.db.sql.prepare(this.q).run(...this.args);
    return { success: true, meta: { changes: Number(r.changes), last_row_id: Number(r.lastInsertRowid) } };
  }
  async all() { this.check(); return { success: true, results: this.db.sql.prepare(this.q).all(...this.args).map((x) => ({ ...x })) }; }
}
class FakeD1 {
  constructor() { this.sql = new DatabaseSync(':memory:'); this.sql.exec(MIGRATION); this.log = []; this.fail = false; }
  prepare(q) { return new FakeStmt(this, q); }
  async batch(stmts) { return Promise.all(stmts.map((s) => s.all())); }
  rows() { return this.sql.prepare('SELECT * FROM visits ORDER BY id').all().map((x) => ({ ...x })); }
}
const makeCtx = () => ({ tasks: [], waitUntil(p) { this.tasks.push(p); }, async done() { await Promise.all(this.tasks); } });

const KEY = 'test-key-only-for-unit-tests-123';
const sha = async (s) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))].map((b) => b.toString(16).padStart(2, '0')).join('');
const KEY_HASH = await sha(KEY);
const UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1';
const VID = '11111111-2222-4333-8444-555555555555';
const INDEX_JS = 'window.FD_INDEX = {"latest": "2026-11-08", "issues": [{"date": "2026-11-07"}, {"date": "2026-11-08"}], "site": {}};';
const ASSETS_STATS = {
  async fetch(req) {
    if (new URL(req.url).pathname === '/frontier/issues/index.js') {
      return new Response(INDEX_JS, { status: 200, headers: { 'Content-Type': 'text/javascript', ETag: '"i1"' } });
    }
    return ASSETS_NOLEN.fetch(req);          // 照线上那样不带长度
  },
};
// 发一个请求，等后台写库做完。返回 { res, db, ctx }
async function visit(path, { headers = {}, method = 'GET', db = new FakeD1(), hash = KEY_HASH, cf, envExtra = {} } = {}) {
  const ctx = makeCtx();
  const req = new Request(ORIGIN + path, { method, headers: { 'User-Agent': UA, ...headers } });
  if (cf) Object.defineProperty(req, 'cf', { value: cf });
  const e = { ASSETS: ASSETS_STATS, VISITS: db, ...(hash ? { STATS_KEY_HASH: hash } : {}), ...envExtra };
  const res = await worker.fetch(req, e, ctx);
  await ctx.done();
  return { res, db, ctx };
}
const ownerCookie = { Cookie: `fd_pass=${KEY_HASH}` };
const AUDIO_PATH = '/frontier/issues/2026-11-08/audio/podcast.mp3';
const VIDEO_PATH = '/frontier/issues/2026-11-08/audio/video3.mp3';
FILES[VIDEO_PATH] = ['audio/mpeg', AUDIO];
FILES['/frontier/issues/2026-11-07/audio/podcast.mp3'] = ['audio/mpeg', AUDIO];

test('统计：打开首页记一行（期号从 ?date= 取，别的参数不存，不存 IP），新访客发 fd_vid Cookie、只让自己的浏览器存', async () => {
  INDEX_CACHE.dates = null;
  const { res, db } = await visit('/frontier/?date=2026-11-07&theme=dark&k=wrong', { headers: { 'CF-Connecting-IP': '203.0.113.5', Referer: 'https://mp.weixin.qq.com/s/abc?x=1', 'Accept-Language': 'zh-CN,zh;q=0.9' }, cf: { country: 'CN', region: 'Guangdong', city: 'Guangzhou' } });
  assert.equal(res.status, 200);
  assert.match(await res.text(), /简报/);
  const ck = res.headers.get('Set-Cookie');
  assert.match(ck, /^fd_vid=[0-9a-f-]{36}; Path=\/frontier; Max-Age=31536000; HttpOnly; Secure; SameSite=Lax$/);
  assert.equal(res.headers.get('Cache-Control'), 'private, no-cache');
  const rows = db.rows();
  assert.equal(rows.length, 1);
  const r = rows[0];
  assert.equal(r.kind, 'page');
  assert.equal(r.path, '/frontier/?date=2026-11-07');
  assert.equal(r.issue, '2026-11-07');
  assert.equal(r.latest, 0);
  assert.equal(r.is_new, 1);
  assert.equal(r.vid, ck.split(';')[0].split('=')[1]);
  assert.equal(r.country, 'CN');
  assert.equal(r.city, 'Guangzhou');
  assert.equal(r.device, 'mobile');
  assert.equal(r.browser, 'Safari');
  assert.equal(r.os, 'iOS');
  assert.equal(r.referrer, 'mp.weixin.qq.com');
  assert.equal(r.lang, 'zh-CN');
  assert.equal(r.day, ukDay(r.ts));
  assert.ok(!JSON.stringify(rows).includes('203.0.113.5'), '不该存 IP');
  assert.ok(!JSON.stringify(rows).includes('Mozilla'), '不该存完整的浏览器标识');
  assert.ok(!JSON.stringify(rows).includes('wrong'), '不该存钥匙参数');
});

test('统计：不带期号（或期号不存在）记成当时的最新一期、latest = 1；往期目录记一行、期号空；回头客不再发 Cookie', async () => {
  INDEX_CACHE.dates = null;
  const db = new FakeD1();
  const back = { Cookie: `fd_vid=${VID}` };
  const a = await visit('/frontier/', { db, headers: back });
  assert.equal(a.res.headers.get('Set-Cookie'), null);
  assert.equal(a.res.headers.get('Cache-Control'), 'no-cache');
  await visit('/frontier/?date=2099-01-01', { db, headers: back });
  await visit('/frontier/index.html', { db, headers: back });
  await visit('/frontier/past/', { db, headers: back });
  await visit('/frontier/past/index.html', { db, headers: { ...back, 'If-None-Match': '"v1"' } });   // 304 也算
  const rows = db.rows();
  assert.deepEqual(rows.map((x) => [x.path, x.issue, x.latest, x.vid, x.is_new]), [
    ['/frontier/', '2026-11-08', 1, VID, 0],
    ['/frontier/?date=2099-01-01', '2026-11-08', 1, VID, 0],
    ['/frontier/', '2026-11-08', 1, VID, 0],
    ['/frontier/past/', '', 0, VID, 0],
    ['/frontier/past/', '', 0, VID, 0],
  ]);
  assert.ok(rows.every((x) => x.kind === 'page' && x.referrer === ''));
});

test('统计：读不到往期目录时，不带期号的记“最新一期（日期没取到）”，页面照常', async () => {
  INDEX_CACHE.dates = null;
  const db = new FakeD1();
  const ctx = makeCtx();
  const res = await worker.fetch(new Request(ORIGIN + '/frontier/', { headers: { 'User-Agent': UA } }), { ASSETS, VISITS: db }, ctx);  // 这个假静态文件里的 index.js 没有 latest
  await ctx.done();
  assert.equal(res.status, 200);
  assert.deepEqual(db.rows().map((x) => [x.issue, x.latest]), [['', 1]]);
  INDEX_CACHE.dates = null;
});

test('统计：不记的——别的文件、HEAD、跳转、404、爬虫和自动程序、预取、站长本人、没绑数据库', async () => {
  const db = new FakeD1();
  for (const p of ['/frontier/app.js', '/frontier/issues/index.js', '/frontier/issues/2026-11-08/issue.js', '/frontier/issues/2026-11-08/img/card-800.webp',
    '/frontier/issues/2026-11-08/fonts/body-kai.woff2', '/frontier/vendor/echarts.min.js', '/frontier', '/frontier/past', '/frontier/2026-11-08/', '/frontier/nope.html']) {
    const { res } = await visit(p, { db });
    assert.equal(res.headers.get('Set-Cookie'), null, p);
  }
  await visit('/frontier/', { db, method: 'HEAD' });
  for (const ua of ['Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)', 'curl/8.4.0', 'python-requests/2.31', '',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/120.0 Safari/537.36', 'facebookexternalhit/1.1']) {
    await visit('/frontier/', { db, headers: { 'User-Agent': ua } });
  }
  await visit('/frontier/', { db, cf: { verifiedBotCategory: 'Search Engine Crawler' } });
  await visit('/frontier/', { db, headers: { 'Sec-Purpose': 'prefetch;prerender' } });
  const own = await visit('/frontier/', { db, headers: ownerCookie });
  assert.equal(own.res.headers.get('Set-Cookie'), null);
  assert.equal(db.rows().length, 0);
  assert.equal(db.log.length, 0, '一条都不该写');
  // 没绑数据库：页面照常，不发访客 Cookie
  const ctx = makeCtx();
  const res = await worker.fetch(new Request(ORIGIN + '/frontier/', { headers: { 'User-Agent': UA } }), { ASSETS }, ctx);
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('Set-Cookie'), null);
  assert.equal(ctx.tasks.length, 0);
});

test('统计：播客、视频旁白“从头要”的那一次记“开始听”“开始看”，带期号；拖动不记；Safari 先探 2 个字节不记；音频内容一字不差', async () => {
  const db = new FakeD1();
  const h = { Cookie: `fd_vid=${VID}` };
  // Safari：先 bytes=0-1 探一下，再从 0 要整段，再拖到中间
  const probe = await visit(AUDIO_PATH, { db, headers: { ...h, Range: 'bytes=0-1' } });
  assert.equal(probe.res.status, 206);
  assert.deepEqual(new Uint8Array(await probe.res.arrayBuffer()), AUDIO.subarray(0, 2));
  assert.equal(db.rows().length, 0, '探测不算');
  const full = await visit(AUDIO_PATH, { db, headers: { ...h, Range: 'bytes=0-99999' } });
  assert.equal(full.res.status, 206);
  assert.deepEqual(new Uint8Array(await full.res.arrayBuffer()), AUDIO);
  assert.equal(full.res.headers.get('Set-Cookie'), null, '音频不发 Cookie');
  assert.equal(full.res.headers.get('Cache-Control'), CACHE.media, '音频的缓存头不变');
  const mid = await visit(AUDIO_PATH, { db, headers: { ...h, Range: 'bytes=50000-' } });
  assert.equal(mid.res.status, 206);
  assert.deepEqual(new Uint8Array(await mid.res.arrayBuffer()), AUDIO.subarray(50000));
  // Chrome：视频旁白 bytes=0-
  const v = await visit(VIDEO_PATH, { db, headers: { ...h, Range: 'bytes=0-' } });
  assert.equal(v.res.status, 206);
  // 不带 Range 的整段请求（另一位、没 Cookie 的访客）
  const plain200 = await visit(AUDIO_PATH, { db });
  assert.equal(plain200.res.status, 200);
  assert.deepEqual(new Uint8Array(await plain200.res.arrayBuffer()), AUDIO);
  const rows = db.rows();
  assert.deepEqual(rows.map((x) => [x.kind, x.issue, x.path, x.vid, x.is_new, x.latest]), [
    ['listen', '2026-11-08', AUDIO_PATH, VID, 0, 0],
    ['watch', '2026-11-08', VIDEO_PATH, VID, 0, 0],
    ['listen', '2026-11-08', AUDIO_PATH, '', 0, 0],
  ]);
});

test('统计：同一访客同一期 30 分钟内“开始听”只记一次；换一期、换成视频、过了 30 分钟都另记', async () => {
  const db = new FakeD1();
  const h = { Cookie: `fd_vid=${VID}` };
  for (let i = 0; i < 3; i++) await visit(AUDIO_PATH, { db, headers: { ...h, Range: 'bytes=0-' } });
  await visit(AUDIO_PATH, { db, headers: h });                                                // 不带 Range 也算从头，但 30 分钟内已经有了
  await visit('/frontier/issues/2026-11-07/audio/podcast.mp3', { db, headers: { ...h, Range: 'bytes=0-' } });
  await visit(VIDEO_PATH, { db, headers: { ...h, Range: 'bytes=0-' } });
  assert.deepEqual(db.rows().map((x) => [x.kind, x.issue]), [['listen', '2026-11-08'], ['listen', '2026-11-07'], ['watch', '2026-11-08']]);
  // 过了 30 分钟（直接用写库的函数，换时间）
  const req = new Request(ORIGIN + AUDIO_PATH, { headers: { 'User-Agent': UA } });
  const t0 = db.rows()[0].ts;
  const later = buildRecord(req, new URL(req.url), { kind: 'listen', path: AUDIO_PATH, issue: '2026-11-08', vid: VID }, t0 + PLAY_ONCE_MS + 1000);
  assert.equal(await writeVisit(db, later, { once: true }), true);
  const sooner = buildRecord(req, new URL(req.url), { kind: 'listen', path: AUDIO_PATH, issue: '2026-11-08', vid: VID }, t0 + PLAY_ONCE_MS + 2000);
  assert.equal(await writeVisit(db, sooner, { once: true }), false);
  assert.equal(db.rows().filter((x) => x.kind === 'listen' && x.issue === '2026-11-08').length, 2);
});

test('统计：音频不记的——HEAD、416、多段、爬虫、站长、别的音频文件', async () => {
  const db = new FakeD1();
  assert.equal((await visit(AUDIO_PATH, { db, method: 'HEAD' })).res.status, 200);
  assert.equal((await visit(AUDIO_PATH, { db, headers: { Range: 'bytes=100000-' } })).res.status, 416);
  assert.equal((await visit(AUDIO_PATH, { db, headers: { Range: 'bytes=0-1,5-6' } })).res.status, 200);
  await visit(AUDIO_PATH, { db, headers: { 'User-Agent': 'Wget/1.21' } });
  await visit(AUDIO_PATH, { db, headers: { ...ownerCookie, Range: 'bytes=0-' } });
  FILES['/frontier/issues/2026-11-08/audio/other.mp3'] = ['audio/mpeg', AUDIO];
  await visit('/frontier/issues/2026-11-08/audio/other.mp3', { db, headers: { Range: 'bytes=0-' } });
  assert.equal(db.rows().length, 0);
});

test('统计：数据库坏了，页面和音频照常（后台写库的出错被吞掉）', async () => {
  const db = new FakeD1();
  db.fail = true;
  const page = await visit('/frontier/?date=2026-11-08', { db });
  assert.equal(page.res.status, 200);
  assert.match(await page.res.text(), /简报/);
  const a = await visit(AUDIO_PATH, { db, headers: { Range: 'bytes=16380-16390' } });
  assert.equal(a.res.status, 206);
  assert.deepEqual(new Uint8Array(await a.res.arrayBuffer()), AUDIO.subarray(16380, 16391));
  const b = await visit(AUDIO_PATH, { db, headers: { Range: 'bytes=0-' } });
  assert.equal(b.res.status, 206);
  assert.ok(db.log.length >= 2, '确实去写了');
  // prepare 一调就抛错的数据库也一样
  const bad = { prepare() { throw new Error('boom'); } };
  const c = await visit('/frontier/', { db: bad });
  assert.equal(c.res.status, 200);
  const d = await visit(AUDIO_PATH, { db: bad, headers: { Range: 'bytes=0-' } });
  assert.equal(d.res.status, 206);
});

test('统计：每写进第 1000、2000……条时顺手删 400 天以前的记录；别的时候不删', async () => {
  const db = new FakeD1();
  const now = Date.now();
  const req = new Request(ORIGIN + '/frontier/', { headers: { 'User-Agent': UA } });
  const old = buildRecord(req, new URL(req.url), { vid: VID }, now - (RETENTION_DAYS + 5) * 86400000);
  assert.equal(await writeVisit(db, old), true);
  assert.equal(await writeVisit(db, buildRecord(req, new URL(req.url), { vid: VID }, now)), true);
  assert.equal(db.rows().length, 2, '第 2 条不删');
  db.sql.exec(`UPDATE sqlite_sequence SET seq = ${CLEANUP_EVERY - 1} WHERE name = 'visits'`);   // 下一条的编号就是 1000
  assert.equal(await writeVisit(db, buildRecord(req, new URL(req.url), { vid: VID }, now)), true);
  const rows = db.rows();
  assert.equal(rows.length, 2, '400 天以前的那条删掉了');
  assert.equal(rows[rows.length - 1].id, CLEANUP_EVERY);
  assert.ok(rows.every((x) => x.ts >= now - RETENTION_DAYS * 86400000));
  await cleanupVisits(null);                         // 没有数据库也不出错
});

test('钥匙：?k= 对了发站长 Cookie（值是指纹、只在 /frontier 下）并跳回不带钥匙的网址；本身不记访问', async () => {
  const db = new FakeD1();
  const cases = [['/frontier/?k=' + encodeURIComponent(KEY), '/frontier/'], ['/frontier?k=' + encodeURIComponent(KEY), '/frontier/'],
    ['/frontier/?date=2026-11-08&k=' + encodeURIComponent(KEY), '/frontier/?date=2026-11-08'], ['/frontier/_visits?k=' + encodeURIComponent(KEY) + '&r=7', '/frontier/_visits?r=7']];
  for (const [p, loc] of cases) {
    const { res } = await visit(p, { db });
    assert.equal(res.status, 302, p);
    assert.equal(res.headers.get('Location'), loc, p);
    assert.equal(res.headers.get('Set-Cookie'), `fd_pass=${KEY_HASH}; Path=/frontier; Max-Age=31536000; HttpOnly; Secure; SameSite=Lax`);
    assert.equal(res.headers.get('Cache-Control'), 'no-store');
    assert.equal(res.headers.get('X-Robots-Tag'), 'noindex, nofollow');
  }
  assert.equal(db.rows().length, 0);
});

test('钥匙：不对、没设指纹、指纹格式不对（比如误填了钥匙本身）、HEAD，都不发站长 Cookie，页面照常', async () => {
  const db = new FakeD1();
  const tries = [
    ['/frontier/?k=wrong-key', KEY_HASH], ['/frontier/?k=', KEY_HASH], ['/frontier/?k=' + encodeURIComponent(KEY), ''],
    ['/frontier/?k=' + encodeURIComponent(KEY), KEY], ['/frontier/?k=' + encodeURIComponent(KEY), KEY_HASH.slice(0, 63)],
    ['/frontier/?k=' + KEY_HASH, KEY_HASH],                 // 拿指纹当钥匙也不行
  ];
  for (const [p, hash] of tries) {
    const { res } = await visit(p, { db, hash });
    assert.equal(res.status, 200, p);
    assert.ok(!String(res.headers.get('Set-Cookie') || '').includes('fd_pass'), p);
  }
  const head = await visit('/frontier/?k=' + encodeURIComponent(KEY), { db, method: 'HEAD' });
  assert.equal(head.res.status, 200);
  assert.equal(head.res.headers.get('Set-Cookie'), null);
  // 指纹大写、前后有空白也认
  const up = await visit('/frontier/?k=' + encodeURIComponent(KEY), { db, hash: ` ${KEY_HASH.toUpperCase()}\n` });
  assert.equal(up.res.status, 302);
});

test('统计页的门：没有站长 Cookie、Cookie 不对、没设指纹，一律和普通“没有这个页面”一样 404；别的写法也 404', async () => {
  const db = new FakeD1();
  const normal = await (await visit('/frontier/no-such-page', { db })).res.text();
  for (const [headers, hash] of [[{}, KEY_HASH], [{ Cookie: 'fd_pass=' + 'a'.repeat(64) }, KEY_HASH], [{ Cookie: 'fd_pass=' + KEY }, KEY_HASH], [ownerCookie, '']]) {
    const { res } = await visit('/frontier/_visits', { db, headers, hash });
    assert.equal(res.status, 404, JSON.stringify(headers));
    assert.equal(res.headers.get('Cache-Control'), 'no-store');
    assert.equal(await res.text(), normal);
    assert.equal((await visit('/frontier/_visits?format=csv', { db, headers, hash })).res.status, 404);
  }
  for (const p of ['/frontier/_visits/', '/frontier/_visits.csv', '/frontier/_visits/x', '/frontier/_visits.html']) {
    assert.equal((await visit(p, { db, headers: ownerCookie })).res.status, 404, p);
  }
  assert.equal(db.rows().length, 0);
});

test('统计页：站长打开 200，中文、不缓存、noindex、不引外网资源，数字对得上；站长自己的访问不计入；顺手删 400 天以前的', async () => {
  const db = new FakeD1();
  const now = Date.now();
  const req = new Request(ORIGIN + '/frontier/', { headers: { 'User-Agent': UA } });
  const u = new URL(req.url);
  const add = (o, t = now) => writeVisit(db, buildRecord(req, u, o, t));
  await add({ path: '/frontier/', issue: '2026-11-08', latest: 1, vid: 'aaaaaaaaaaaaaaaa1', isNew: true });
  await add({ path: '/frontier/?date=2026-11-07', issue: '2026-11-07', vid: 'aaaaaaaaaaaaaaaa1' });
  await add({ path: '/frontier/?date=2026-11-08', issue: '2026-11-08', vid: 'bbbbbbbbbbbbbbbb2', isNew: true });
  await add({ path: '/frontier/past/', vid: 'bbbbbbbbbbbbbbbb2' });
  await add({ kind: 'listen', path: AUDIO_PATH, issue: '2026-11-08', vid: 'aaaaaaaaaaaaaaaa1' });
  await add({ kind: 'listen', path: AUDIO_PATH, issue: '2026-11-08', vid: '' });
  await add({ kind: 'watch', path: VIDEO_PATH, issue: '2026-11-08', vid: 'bbbbbbbbbbbbbbbb2' });
  await add({ path: '/frontier/', issue: '2026-11-01', latest: 1, vid: 'cccccccccccccccc3' }, now - 10 * 86400000);   // 10 天前
  await add({ path: '/frontier/', issue: '2025-01-01', latest: 1, vid: 'dddddddddddddddd4' }, now - (RETENTION_DAYS + 1) * 86400000);   // 400 天以前

  const st = await collectStats(db, '30', now);
  assert.deepEqual(st.summary.map((x) => [x.label, x.v, x.u, x.n, x.l, x.w]), [
    ['今天', 4, 2, 2, 2, 1], ['近 7 天', 4, 2, 2, 2, 1], ['近 30 天', 5, 3, 2, 2, 1]]);
  const per = Object.fromEntries(st.perIssue.map((x) => [x.issue, [x.pv, x.pu, x.lv, x.lu, x.wv, x.wu]]));
  assert.deepEqual(per['2026-11-08'], [2, 2, 2, 1, 1, 1]);          // 没带编号的那次“开始听”算次数、不算人数
  assert.deepEqual(per['2026-11-07'], [1, 1, 0, 0, 0, 0]);
  assert.equal(st.issues[0].issue, '2026-11-08');
  assert.equal(st.issues[0].v, 2);
  assert.equal(st.issues[0].l, 1);
  assert.equal(st.series.length, 30);
  assert.equal(st.series[st.series.length - 1].v, 4);
  assert.equal(st.series[st.series.length - 1].l, 2);

  const { res, ctx } = await visit('/frontier/_visits', { db, headers: ownerCookie });
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('Content-Type'), 'text/html; charset=utf-8');
  assert.equal(res.headers.get('Cache-Control'), 'no-store');
  assert.equal(res.headers.get('X-Robots-Tag'), 'noindex, nofollow');
  const html = await res.text();
  for (const s of ['访问统计', '今天', '近 7 天', '近 30 天', '每期：打开、开始听、开始看', '最常看的期号', '最常打开的页面', '来源网站', '国家／地区', '设备类型', '最近 100 次', '导出 CSV', '2026-11-08 期', '往期目录', 'prefers-color-scheme:dark', 'name="viewport"']) {
    assert.ok(html.includes(s), s);
  }
  assert.ok(!/<script[^>]+src=|<link[^>]+stylesheet|@import|url\(|https?:\/\//i.test(html), '不该引用外部资源');
  assert.equal(ctx.tasks.length, 1, '顺手清理');
  assert.ok(db.rows().every((x) => x.issue !== '2025-01-01'), '400 天以前的删掉了');
  assert.equal(db.rows().length, 8, '站长打开统计页不计入');

  for (const r of ['7', '90', 'all']) assert.equal((await visit('/frontier/_visits?r=' + r + '&tz=cn', { db, headers: ownerCookie })).res.status, 200, r);
  const head = await visit('/frontier/_visits', { db, headers: ownerCookie, method: 'HEAD' });
  assert.equal(head.res.status, 200);
  assert.equal(await head.res.text(), '');
});

test('统计页：导出 CSV（UTF-8 带 BOM、各类型都在、防公式）；没绑数据库时页面照常打开并说明', async () => {
  const db = new FakeD1();
  const req = new Request(ORIGIN + '/frontier/', { headers: { 'User-Agent': UA, Referer: 'https://=evil.example/' } });
  await writeVisit(db, buildRecord(req, new URL(req.url), { path: '/frontier/?date=2026-11-08', issue: '2026-11-08', vid: VID, isNew: true }));
  await writeVisit(db, buildRecord(req, new URL(req.url), { kind: 'listen', path: AUDIO_PATH, issue: '2026-11-08', vid: VID }));
  await writeVisit(db, buildRecord(req, new URL(req.url), { kind: 'watch', path: VIDEO_PATH, issue: '2026-11-08', vid: '' }));
  const { res } = await visit('/frontier/_visits?format=csv&r=7', { db, headers: ownerCookie });
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('Content-Type'), 'text/csv; charset=utf-8');
  assert.match(res.headers.get('Content-Disposition'), /^attachment; filename="frontier-visits-7d-\d{4}-\d{2}-\d{2}\.csv"$/);
  assert.equal(res.headers.get('Cache-Control'), 'no-store');
  const buf = new Uint8Array(await res.arrayBuffer());
  assert.deepEqual([...buf.subarray(0, 3)], [0xef, 0xbb, 0xbf]);
  const text = new TextDecoder().decode(buf);
  const lines = text.trim().split('\r\n');
  assert.equal(lines.length, 4);
  assert.match(lines[0], /时间（英国）.*类型.*期号/);
  assert.match(lines[1], /打开页面,2026-11-08,否,2026-11-08 期（网址带期号）/);
  assert.match(lines[2], /开始听（播客）,2026-11-08/);
  assert.match(lines[3], /开始看（视频）,2026-11-08/);
  assert.ok(!/,=/.test(text), '以 = 开头的内容要加引号前缀');
  assert.match(toCSV([{ ts: 0, day: '1970-01-01', kind: 'page', path: '=1+1', issue: '', latest: 0, vid: '', is_new: 0 }]), /,'=1\+1,/);

  const ctx = makeCtx();
  const r2 = await worker.fetch(new Request(ORIGIN + '/frontier/_visits', { headers: { 'User-Agent': UA, ...ownerCookie } }), { ASSETS, STATS_KEY_HASH: KEY_HASH }, ctx);
  assert.equal(r2.status, 200);
  assert.match(await r2.text(), /还没有连上统计数据库/);
  const r3 = await worker.fetch(new Request(ORIGIN + '/frontier/_visits?format=csv', { headers: ownerCookie }), { ASSETS, STATS_KEY_HASH: KEY_HASH }, ctx);
  assert.equal(r3.status, 200);
});

test('统计：读者反馈和别的请求照旧，不写统计', async () => {
  RATE.seen.clear();
  const db = new FakeD1();
  await withFakes(async (calls) => {
    const ctx = makeCtx();
    const req = new Request(ORIGIN + '/frontier/feedback', { method: 'POST', headers: { Origin: ORIGIN, 'Content-Type': 'application/json', 'CF-Connecting-IP': '203.0.113.77', 'User-Agent': UA }, body: JSON.stringify(GOOD) });
    const res = await worker.fetch(req, { ASSETS, VISITS: db, GH_FEEDBACK_TOKEN: TOKEN, STATS_KEY_HASH: KEY_HASH }, ctx);
    await ctx.done();
    assert.equal(res.status, 202);
    assert.equal(calls.length, 1);
  });
  assert.equal(db.rows().length, 0);
  RATE.seen.clear();
});

test('统计的小函数：playStarts、playInfo、pageKind、cleanPath', () => {
  const R = (range) => new Request(ORIGIN + AUDIO_PATH, range == null ? {} : { headers: { Range: range } });
  assert.equal(playStarts(R()), true);
  for (const r of ['bytes=0-', 'bytes=0-2', 'bytes=0-99999', ' bytes=0- ']) assert.equal(playStarts(R(r)), true, r);
  for (const r of ['bytes=0-0', 'bytes=0-1', 'bytes=1-', 'bytes=50000-', 'bytes=-500', 'bytes=0-1,5-6', 'items=0-', '']) assert.equal(playStarts(R(r)), false, r);
  assert.deepEqual(playInfo('/frontier/issues/2026-11-09/audio/podcast.mp3'), { kind: 'listen', issue: '2026-11-09' });
  assert.deepEqual(playInfo('/frontier/issues/2026-11-09/audio/video3.mp3'), { kind: 'watch', issue: '2026-11-09' });
  for (const p of ['/frontier/issues/2026-11-09/audio/video.mp3', '/frontier/issues/2026-11-09/podcast.mp3', '/frontier/issues/x/audio/podcast.mp3', '/frontier/issues/2026-11-09/audio/podcast.mp3/']) {
    assert.equal(playInfo(p), null, p);
  }
  assert.equal(pageKind('/frontier/'), 'issue');
  assert.equal(pageKind('/frontier/index.html'), 'issue');
  assert.equal(pageKind('/frontier/past/'), 'past');
  for (const p of ['/frontier', '/frontier/past', '/frontier/app.js', '/frontier/_visits', '/frontier/issues/index.js', '/frontier/x/index.html']) assert.equal(pageKind(p), null, p);
  const C = (s) => cleanPath(new URL(ORIGIN + s));
  assert.equal(C('/frontier/?date=2026-11-09&k=secret&theme=dark'), '/frontier/?date=2026-11-09');
  assert.equal(C('/frontier/?date=2026-11-9'), '/frontier/');
  assert.equal(C('/frontier/index.html?static=1'), '/frontier/');
  assert.equal(C('/frontier/past/index.html?date=2026-11-09'), '/frontier/past/');
});


// ===================== 开放程度：公开／凭口令／只有我（11-10 加，src/access.js）=====================
// 假 D1 照上面（Node 自带 SQLite），另按 migrations/0002_settings.sql 建 site_settings 表。口令、钥匙都是测试专用的假值。
// 每条测试开头清掉本实例的档位缓存（ACCESS_STATE，15 秒）和凭口令进入的限流表，互不影响。
import {
  resetAccessCache, ACCESS_STATE, ACCESS_TTL_MS, ENTER_RATE, FORM_MAX_BYTES, safeNext, privatize, loadSettings, checkPw, makePwRecord,
} from '../src/access.js';

const MIGRATION2 = readFileSync(new URL('../migrations/0002_settings.sql', import.meta.url), 'utf8');
const PW = '测试口令-only-for-tests';
const FORM = { 'Content-Type': 'application/x-www-form-urlencoded' };
const NO_EXTERNAL = /<script[^>]+src=|<link[^>]+stylesheet|@import|url\(|https?:\/\//i;
function settingsDb({ mode, migrate = true } = {}) {
  const db = new FakeD1();
  if (migrate) db.sql.exec(MIGRATION2);
  if (mode) db.sql.prepare('INSERT INTO site_settings (key, value, updated_ts) VALUES (?, ?, ?)').run('access_mode', mode, Date.now());
  return db;
}
const setting = (db, key) => { try { return db.sql.prepare('SELECT value FROM site_settings WHERE key = ?').get(key); } catch (_) { return undefined; } };
// 发一个请求（可带正文），等后台写库做完。Worker 的日志接进 LOGS（中文日志直接打到测试进程的输出里，
// Node 的测试运行器偶尔会报“Unable to deserialize cloned data”，所以接住不打）
const LOGS = [];
async function send(path, { method = 'GET', headers = {}, body, db, hash = KEY_HASH, extra = {} } = {}) {
  const ctx = makeCtx();
  const init = { method, headers: { 'User-Agent': UA, ...headers } };
  if (body != null) init.body = body;
  const e = { ASSETS: ASSETS_STATS, ...(db ? { VISITS: db } : {}), ...(hash ? { STATS_KEY_HASH: hash } : {}), ...extra };
  const realLog = console.log;
  console.log = (...a) => LOGS.push(a.join(' '));
  try {
    const res = await worker.fetch(new Request(ORIGIN + path, init), e, ctx);
    await ctx.done();
    return res;
  } finally { console.log = realLog; }
}
const form = (o) => new URLSearchParams(o).toString();
const ownerPost = (db, fields, { origin = ORIGIN, cookie = ownerCookie } = {}) =>
  send('/frontier/_access', { method: 'POST', db, headers: { ...FORM, ...cookie, ...(origin ? { Origin: origin } : {}) }, body: form(fields) });
const enter = (db, fields, { origin = ORIGIN, ip = '198.51.100.50', cookie } = {}) =>
  send('/frontier/_enter', { method: 'POST', db, headers: { ...FORM, 'CF-Connecting-IP': ip, ...(origin ? { Origin: origin } : {}), ...(cookie ? { Cookie: cookie } : {}) }, body: form(fields) });
const fbPost = (db, headers = {}) => send('/frontier/feedback', {
  method: 'POST', db, headers: { Origin: ORIGIN, 'Content-Type': 'application/json', 'CF-Connecting-IP': '203.0.113.90', ...headers }, body: JSON.stringify(GOOD), extra: { GH_FEEDBACK_TOKEN: TOKEN },
});
const visitRows = (db) => db.rows();
function fresh() { resetAccessCache(); ENTER_RATE.seen.clear(); RATE.seen.clear(); INDEX_CACHE.dates = null; }
// 站长设口令、切到凭口令；返回口令 Cookie 的“名=值”
async function familySetup(db, pw = PW) {
  assert.equal((await ownerPost(db, { op: 'pw', pw1: pw, pw2: pw })).headers.get('Location'), '/frontier/_access?msg=pwset');
  assert.equal((await ownerPost(db, { op: 'mode', mode: 'family' })).headers.get('Location'), '/frontier/_access?msg=mode-family');
}
async function login(db, pw = PW, opts = {}) {
  const res = await enter(db, { password: pw, next: '/frontier/' }, opts);
  assert.equal(res.status, 303);
  return res.headers.get('Set-Cookie').split(';')[0];
}

test('开放程度：默认（没有表、表里没有这一行、值写错、没绑数据库）一律公开，和以前一样', async () => {
  for (const make of [() => new FakeD1(), () => settingsDb(), () => settingsDb({ mode: 'xyz' }), () => null]) {
    fresh();
    const db = make();
    const back = { Cookie: `fd_vid=${VID}` };
    const page = await send('/frontier/', { db, headers: back });
    assert.equal(page.status, 200);
    assert.equal(page.headers.get('Cache-Control'), 'no-cache');
    assert.match(await page.text(), /简报/);
    const a = await send(AUDIO_PATH, { db, headers: { Range: 'bytes=0-1' } });
    assert.equal(a.status, 206);
    assert.equal(a.headers.get('Cache-Control'), CACHE.media);
    assert.equal((await send('/frontier/issues/2026-11-08/issue.js', { db })).headers.get('Cache-Control'), CACHE.code);
    await withFakes(async (calls) => {
      assert.equal((await fbPost(db)).status, 202);
      assert.equal(calls.length, 1);
    });
  }
  fresh();
});

test('开放程度：只有我——匿名的网页、issue.js、图片、mp3（含 Range）、HEAD、往期页都回“测试中”门页，不取静态文件、不记访问；反馈 POST 回 403', async () => {
  fresh();
  const db = settingsDb({ mode: 'owner' });
  const n = seen.length;
  for (const [p, headers] of [['/frontier/', {}], ['/frontier/?date=2026-11-08', {}], ['/frontier/past/', {}], ['/frontier/issues/2026-11-08/issue.js', {}],
    ['/frontier/issues/index.js', {}], ['/frontier/issues/2026-11-08/img/card-800.webp', {}], [AUDIO_PATH, {}], [AUDIO_PATH, { Range: 'bytes=0-1' }],
    [AUDIO_PATH, { Range: 'bytes=50000-' }], [VIDEO_PATH, { Range: 'bytes=0-' }], ['/frontier/app.js', { 'If-None-Match': '"v1"' }], ['/frontier/nope.html', {}],
    ['/frontier/_enter', {}], ['/frontier/?k=wrong-key', {}]]) {
    const res = await send(p, { db, headers: { Cookie: `fd_vid=${VID}`, ...headers } });
    assert.equal(res.status, 403, p);
    assert.equal(res.headers.get('Cache-Control'), 'no-store', p);
    assert.equal(res.headers.get('Content-Type'), 'text/html; charset=utf-8', p);
    assert.equal(res.headers.get('X-Robots-Tag'), 'noindex, nofollow', p);
    assert.equal(res.headers.get('Referrer-Policy'), 'same-origin', p);
    assert.equal(res.headers.get('X-Content-Type-Options'), 'nosniff', p);
    assert.equal(res.headers.get('Set-Cookie'), null, p);
    const html = await res.text();
    assert.match(html, /网站在测试中，暂时没有开放/, p);
    assert.match(html, /isn’t open yet/, p);
    assert.ok(!/<form|<input|_access|_visits|k=|钥匙/.test(html), '测试中那页没有输入框、不提示钥匙和设置页');
    assert.ok(!NO_EXTERNAL.test(html), '不引外部资源');
  }
  const head = await send('/frontier/', { db, method: 'HEAD' });
  assert.equal(head.status, 403);
  assert.equal(await head.text(), '');
  assert.equal(seen.length, n, '被挡下的请求一个静态文件都没取');
  // 纯跳转照旧（跳到的那一页再过门）
  assert.equal((await send('/frontier', { db })).status, 301);
  assert.equal((await send('/frontier/past', { db })).status, 301);
  assert.equal((await send('/frontier/2026-11-09/', { db })).status, 302);
  await withFakes(async (calls) => {
    const res = await fbPost(db);
    assert.equal(res.status, 403);
    assert.equal(res.headers.get('Content-Type'), 'application/json; charset=utf-8');
    const d = await res.json();
    assert.equal(d.ok, false);
    assert.equal(d.error, '网站暂未开放');
    assert.ok(d.error_en);
    assert.equal(calls.length, 0, '不转交 GitHub');
  });
  assert.equal(visitRows(db).length, 0, '门页不记访问');
  fresh();
});

test('开放程度：只有我——站长照常 200／206，非公开档 Cache-Control 换成 private；钥匙登录照旧；站长的访问不记', async () => {
  fresh();
  const db = settingsDb({ mode: 'owner' });
  const page = await send('/frontier/', { db, headers: ownerCookie });
  assert.equal(page.status, 200);
  assert.equal(page.headers.get('Cache-Control'), 'private, no-cache');
  assert.match(await page.text(), /简报/);
  const full = await send(AUDIO_PATH, { db, headers: ownerCookie });
  assert.equal(full.status, 200);
  assert.equal(full.headers.get('Cache-Control'), 'private, max-age=604800');
  assert.deepEqual(new Uint8Array(await full.arrayBuffer()), AUDIO);
  const part = await send(AUDIO_PATH, { db, headers: { ...ownerCookie, Range: 'bytes=16380-16390' } });
  assert.equal(part.status, 206);
  assert.equal(part.headers.get('Cache-Control'), 'private, max-age=604800');
  assert.deepEqual(new Uint8Array(await part.arrayBuffer()), AUDIO.subarray(16380, 16391));
  assert.equal((await send('/frontier/issues/2026-11-08/issue.js', { db, headers: ownerCookie })).headers.get('Cache-Control'), 'private, max-age=600');
  const nm = await send('/frontier/app.js', { db, headers: { ...ownerCookie, 'If-None-Match': '"v1"' } });
  assert.equal(nm.status, 304);
  assert.equal(nm.headers.get('Cache-Control'), 'private, max-age=600');
  const head = await send('/frontier/', { db, method: 'HEAD', headers: ownerCookie });
  assert.equal(head.status, 200);
  const nf = await send('/frontier/nope.html', { db, headers: ownerCookie });
  assert.equal(nf.status, 404);
  assert.equal(nf.headers.get('Cache-Control'), 'no-store');
  const key = await send('/frontier/?k=' + encodeURIComponent(KEY), { db });
  assert.equal(key.status, 302);
  assert.match(key.headers.get('Set-Cookie'), /^fd_pass=/);
  await withFakes(async (calls) => {
    assert.equal((await fbPost(db, ownerCookie)).status, 202);
    assert.equal(calls.length, 1);
  });
  assert.equal(visitRows(db).length, 0, '站长不记');
  fresh();
});

test('开放程度：仅家人——门页有口令表单（不靠 JavaScript）；口令错 403“口令不对”；对了发 180 天家人 Cookie、303 跳回原来的地址', async () => {
  fresh();
  const db = settingsDb();
  await familySetup(db);
  const gate = await send('/frontier/?date=2026-11-08&k=wrong', { db });
  assert.equal(gate.status, 403);
  assert.equal(gate.headers.get('Cache-Control'), 'no-store');
  const html = await gate.text();
  for (const s of ['这个网站目前只对部分人开放', 'This site is currently open to selected visitors only.', '<title>只对部分人开放 · ', '<form method="post" action="/frontier/_enter">', 'name="password"', 'type="password"',
    'name="next" value="/frontier/?date=2026-11-08"', '进入', 'name="viewport"', 'prefers-color-scheme:dark', 'noindex, nofollow']) assert.ok(html.includes(s), s);
  assert.ok(!/<script/i.test(html), '不靠 JavaScript');
  assert.ok(!NO_EXTERNAL.test(html), '不引外部资源');
  assert.ok(!/_access|_visits|钥匙|口令不对/.test(html), '不提示设置页、钥匙；没输错时不显示“口令不对”');
  assert.ok(!/家人|family/i.test(html), '别人看得到的门页（连源码）不出现“家人”“family”');
  for (const s of ['口令 · Password', '进入 · Enter', '输对一次，这台设备之后不用再输']) assert.ok(html.includes(s), s);
  // 口令错
  const bad = await enter(db, { password: 'wrong-pw', next: '/frontier/?date=2026-11-08' });
  assert.equal(bad.status, 403);
  assert.equal(bad.headers.get('Set-Cookie'), null);
  assert.equal(bad.headers.get('Cache-Control'), 'no-store');
  const badHtml = await bad.text();
  assert.match(badHtml, /口令不对/);
  assert.ok(badHtml.includes('name="next" value="/frontier/?date=2026-11-08"'), '输错了还记得要回哪');
  assert.equal((await enter(db, { password: '', next: '/frontier/' })).status, 403);
  // 口令对（首尾空格不算）
  const ok = await enter(db, { password: `  ${PW} `, next: '/frontier/?date=2026-11-08' });
  assert.equal(ok.status, 303);
  assert.equal(ok.headers.get('Location'), '/frontier/?date=2026-11-08');
  assert.equal(ok.headers.get('Cache-Control'), 'no-store');
  const ck = ok.headers.get('Set-Cookie');
  assert.match(ck, /^fd_family=[0-9a-f]{64}; Path=\/frontier; Max-Age=15552000; HttpOnly; Secure; SameSite=Lax$/);
  assert.ok(!ck.includes(PW));
  assert.equal(visitRows(db).length, 0, '门页、登录都不记访问');
  // 没有 Origin 也收；Origin 是别的网站 403
  assert.equal((await enter(db, { password: PW, next: '/frontier/' }, { origin: '' })).status, 303);
  for (const origin of ['https://evil.example', 'http://wenlongzhang.com', 'null']) assert.equal((await enter(db, { password: PW, next: '/frontier/' }, { origin })).status, 403, origin);
  // 只收表单、不超过 2 KB
  const json = await send('/frontier/_enter', { method: 'POST', db, headers: { Origin: ORIGIN, 'Content-Type': 'application/json' }, body: '{}' });
  assert.equal(json.status, 415);
  assert.equal((await enter(db, { password: PW, next: '/frontier/' + 'x'.repeat(FORM_MAX_BYTES) })).status, 413);
  fresh();
});

test('开放程度：仅家人——带家人 Cookie 能看网页、issue.js、mp3（含 Range）、提交反馈；家人的访问照常记；Cookie 不对仍是门页', async () => {
  fresh();
  const db = settingsDb();
  await familySetup(db);
  const fam = await login(db);
  const page = await send('/frontier/?date=2026-11-08', { db, headers: { Cookie: fam } });
  assert.equal(page.status, 200);
  assert.match(page.headers.get('Cache-Control'), /^private/);
  assert.match(await page.text(), /简报/);
  assert.match(page.headers.get('Set-Cookie') || '', /^fd_vid=/, '家人第一次来照常发访客编号');
  const js = await send('/frontier/issues/2026-11-08/issue.js', { db, headers: { Cookie: fam } });
  assert.equal(js.status, 200);
  assert.equal(js.headers.get('Cache-Control'), 'private, max-age=600');
  const mp3 = await send(AUDIO_PATH, { db, headers: { Cookie: `${fam}; fd_vid=${VID}`, Range: 'bytes=0-' } });
  assert.equal(mp3.status, 206);
  assert.equal(mp3.headers.get('Cache-Control'), 'private, max-age=604800');
  assert.deepEqual(new Uint8Array(await mp3.arrayBuffer()), AUDIO);
  assert.deepEqual(visitRows(db).map((x) => x.kind), ['page', 'listen'], '家人进来以后的访问照常记');
  await withFakes(async (calls) => {
    assert.equal((await fbPost(db, { Cookie: fam })).status, 202);
    assert.equal((await fbPost(db)).status, 403, '没带家人 Cookie 的反馈挡下');
    assert.equal(calls.length, 1);
  });
  for (const c of ['fd_family=' + 'a'.repeat(64), 'fd_family=', fam.toUpperCase(), `fd_pass=${'0'.repeat(64)}`]) {
    const res = await send('/frontier/', { db, headers: { Cookie: c } });
    assert.equal(res.status, 403, c);
    assert.match(await res.text(), /只对部分人开放/);
  }
  // 切到“只有我”：口令 Cookie 也进不来；切回“凭口令”又能进
  await ownerPost(db, { op: 'mode', mode: 'owner' });
  const blocked = await send('/frontier/', { db, headers: { Cookie: fam } });
  assert.equal(blocked.status, 403);
  assert.match(await blocked.text(), /网站在测试中/);
  await ownerPost(db, { op: 'mode', mode: 'family' });
  assert.equal((await send('/frontier/', { db, headers: { Cookie: fam } })).status, 200);
  fresh();
});

test('开放程度：站长改口令后，旧家人 Cookie 和旧口令都失效，新口令发的是新 Cookie', async () => {
  fresh();
  const db = settingsDb();
  await familySetup(db);
  const old = await login(db);
  assert.equal((await send('/frontier/', { db, headers: { Cookie: old } })).status, 200);
  const NEW = '新的家人口令';
  assert.equal((await ownerPost(db, { op: 'pw', pw1: NEW, pw2: NEW })).headers.get('Location'), '/frontier/_access?msg=pwset');
  const after = await send('/frontier/', { db, headers: { Cookie: old } });
  assert.equal(after.status, 403, '本实例立刻失效');
  assert.match(await after.text(), /只对部分人开放/);
  assert.match(await (await enter(db, { password: PW, next: '/frontier/' })).text(), /口令不对/);
  const neu = await login(db, NEW);
  assert.notEqual(neu, old);
  assert.equal((await send('/frontier/', { db, headers: { Cookie: neu } })).status, 200);
  // 同一个口令再设一次（换了随机盐）也让旧 Cookie 失效
  await ownerPost(db, { op: 'pw', pw1: NEW, pw2: NEW });
  assert.equal((await send('/frontier/', { db, headers: { Cookie: neu } })).status, 403);
  fresh();
});

test('开放程度：登录后回到的地址只认站内 /frontier/ 路径，别的一律回 /frontier/', async () => {
  fresh();
  const bad = ['https://evil.com', '//evil.com', '/frontier/..//x', '/frontier//evil.com', '/\\evil.com', '/frontier/\\evil.com', '/frontier/../x',
    '/frontier/./x', '/frontier/%2e%2e/x', '/frontier/%2F%2Fevil.com', '/frontier/%5cevil.com', 'javascript:alert(1)', '', '/frontierx/', '/frontier',
    '/frontier/\nSet-Cookie:x=1', '/frontier/ x', '/frontier/"><script>', 'https://wenlongzhang.com/frontier/', '/frontier/' + 'a'.repeat(600)];
  for (const v of bad) assert.equal(safeNext(v), '/frontier/', JSON.stringify(v));
  assert.equal(safeNext(undefined), '/frontier/');
  for (const v of ['/frontier/', '/frontier/?date=2026-11-08', '/frontier/past/', '/frontier/issues/2026-11-08/audio/podcast.mp3']) assert.equal(safeNext(v), v);
  const db = settingsDb();
  await familySetup(db);
  for (const next of ['https://evil.com', '//evil.com', '/frontier/..//x', '/\\evil.com']) {
    const res = await enter(db, { password: PW, next });
    assert.equal(res.status, 303, next);
    assert.equal(res.headers.get('Location'), '/frontier/', next);
  }
  fresh();
});

test('开放程度：家人登录同一 IP 10 分钟最多试 10 次，第 11 次 429“试得太多了”（口令对也不行）；别的 IP 不受影响', async () => {
  fresh();
  const db = settingsDb();
  await familySetup(db);
  for (let i = 0; i < ENTER_RATE.max; i++) assert.equal((await enter(db, { password: 'nope', next: '/frontier/' }, { ip: '192.0.2.10' })).status, 403, `第 ${i + 1} 次`);
  const res = await enter(db, { password: PW, next: '/frontier/' }, { ip: '192.0.2.10' });
  assert.equal(res.status, 429);
  assert.equal(res.headers.get('Retry-After'), '600');
  assert.equal(res.headers.get('Set-Cookie'), null);
  assert.match(await res.text(), /试得太多了，请 10 分钟后再试/);
  assert.equal((await enter(db, { password: PW, next: '/frontier/' }, { ip: '192.0.2.11' })).status, 303);
  // 10 分钟以后又能试（换时间：把记下的时间往前挪）
  ENTER_RATE.seen.set('192.0.2.10', ENTER_RATE.seen.get('192.0.2.10').map((t) => t - ENTER_RATE.windowMs - 1));
  assert.equal((await enter(db, { password: PW, next: '/frontier/' }, { ip: '192.0.2.10' })).status, 303);
  fresh();
});

test('开放程度：不是“仅家人”档时的 /_enter——公开档跳回去，“只有我”档给测试中门页，站长直接跳回', async () => {
  fresh();
  const pub = settingsDb();
  const a = await enter(pub, { password: 'x', next: '/frontier/?date=2026-11-08' });
  assert.equal(a.status, 303);
  assert.equal(a.headers.get('Location'), '/frontier/?date=2026-11-08');
  assert.equal(a.headers.get('Set-Cookie'), null);
  fresh();
  const own = settingsDb({ mode: 'owner' });
  const b = await enter(own, { password: 'x', next: '/frontier/' });
  assert.equal(b.status, 403);
  const html = await b.text();
  assert.match(html, /网站在测试中/);
  assert.ok(!/<form/.test(html));
  const c = await enter(own, { password: 'x', next: '/frontier/past/' }, { cookie: ownerCookie.Cookie });
  assert.equal(c.status, 303);
  assert.equal(c.headers.get('Location'), '/frontier/past/');
  fresh();
});

test('开放程度：设置页的门——匿名、家人 Cookie、坏站长 Cookie 的 GET／POST 一律和普通“没有这个页面”一样 404；站长坏 Origin 403；别的 POST 仍 405', async () => {
  fresh();
  const db = settingsDb();
  await familySetup(db);
  const fam = await login(db);
  const normal = await (await send('/frontier/no-such-page', { db, headers: ownerCookie })).text();
  for (const headers of [{}, { Cookie: fam }, { Cookie: 'fd_pass=' + 'a'.repeat(64) }]) {
    const g = await send('/frontier/_access', { db, headers });
    assert.equal(g.status, 404, JSON.stringify(headers));
    assert.equal(g.headers.get('Cache-Control'), 'no-store');
    assert.equal(await g.text(), normal);
    const p = await send('/frontier/_access', { method: 'POST', db, headers: { ...FORM, Origin: ORIGIN, ...headers }, body: form({ op: 'mode', mode: 'public' }) });
    assert.equal(p.status, 404, JSON.stringify(headers));
    assert.equal(await p.text(), normal);
  }
  assert.equal((await send('/frontier/_access', { db, headers: ownerCookie, hash: '' })).status, 404, '没设指纹时谁都不是站长');
  for (const p of ['/frontier/_access/', '/frontier/_access.html', '/frontier/_access/x']) assert.equal((await send(p, { db, headers: ownerCookie })).status, 404, p);
  for (const origin of ['https://evil.example', 'http://wenlongzhang.com', '']) {
    const res = await ownerPost(db, { op: 'mode', mode: 'public' }, { origin });
    assert.equal(res.status, 403, origin || '(没有 Origin)');
  }
  assert.equal(setting(db, 'access_mode').value, 'family', '都没改成');
  const json = await send('/frontier/_access', { method: 'POST', db, headers: { ...ownerCookie, Origin: ORIGIN, 'Content-Type': 'application/json' }, body: '{}' });
  assert.equal(json.status, 415);
  assert.equal((await ownerPost(db, { op: 'pw', pw1: 'x'.repeat(FORM_MAX_BYTES), pw2: 'x' })).status, 413);
  for (const p of ['/frontier/_access/', '/frontier/_enter/', '/frontier/_visits', '/frontier/past/']) {
    assert.equal((await send(p, { method: 'POST', db, headers: { ...FORM, ...ownerCookie, Origin: ORIGIN }, body: 'op=mode&mode=public' })).status, 405, p);
  }
  for (const m of ['PUT', 'DELETE', 'PATCH']) {
    assert.equal((await send('/frontier/_enter', { method: m, db })).status, 405, m);
    assert.equal((await send('/frontier/_access', { method: m, db, headers: ownerCookie })).status, 405, m);
  }
  fresh();
});

test('开放程度：设置页——站长打开 200：当前档位、三个按钮、口令没设；不缓存、noindex、不引外网、不用 JavaScript；不记访问；统计页有去设置页的链接', async () => {
  fresh();
  const db = settingsDb();
  const res = await send('/frontier/_access', { db, headers: ownerCookie });
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('Cache-Control'), 'no-store');
  assert.equal(res.headers.get('X-Robots-Tag'), 'noindex, nofollow');
  assert.equal(res.headers.get('Content-Type'), 'text/html; charset=utf-8');
  assert.equal(res.headers.get('X-Frame-Options'), 'DENY', '不许别的网站把设置页嵌进框里');
  const html = await res.text();
  for (const s of ['开放程度', '公开', '仅家人', '只有我', '现在是这一档', '还没改过（默认公开）', '家人口令：还没设', '先设口令', '设新口令', 'name="pw1"', 'name="pw2"',
    'value="public" class="on"', 'href="/frontier/_visits"', 'href="/frontier/"', '改了口令，已经进来的家人要用新口令重新输一次', '最多 15 秒内对所有人生效',
    '已经听过', 'name="viewport"', 'prefers-color-scheme:dark', 'noindex, nofollow']) assert.ok(html.includes(s), s);
  assert.ok(!/<script/i.test(html));
  assert.ok(!NO_EXTERNAL.test(html), '不引外部资源');
  assert.equal((await send('/frontier/_access', { db, headers: ownerCookie, method: 'HEAD' })).status, 200);
  assert.equal(visitRows(db).length, 0);
  const stats = await (await send('/frontier/_visits', { db, headers: ownerCookie })).text();
  assert.ok(stats.includes('href="/frontier/_access"'), '统计页顶部有去设置页的链接');
  fresh();
});

test('开放程度：设置页——没口令不能切“仅家人”；口令 4–64 个字、两遍一致；口令只存盐和指纹；改档后本实例立刻生效，回设置页显示“已改成……”', async () => {
  fresh();
  const db = settingsDb();
  let r = await ownerPost(db, { op: 'mode', mode: 'family' });
  assert.equal(r.status, 303);
  assert.equal(r.headers.get('Location'), '/frontier/_access?msg=nopw');
  assert.equal(r.headers.get('Cache-Control'), 'no-store');
  assert.match(await (await send('/frontier/_access?msg=nopw', { db, headers: ownerCookie })).text(), /还没设家人口令：先在下面设一个口令/);
  assert.equal(setting(db, 'access_mode'), undefined, '没改');
  assert.equal((await send('/frontier/', { db })).status, 200);
  for (const [p1, p2, msg] of [['abc', 'abc', 'pwlen'], ['  abc  ', '  abc  ', 'pwlen'], ['x'.repeat(65), 'x'.repeat(65), 'pwlen'], ['', '', 'pwlen'],
    ['abcd', 'abce', 'pwdiff'], ['家人口令', '家人口令 ', 'pwset']]) {
    r = await ownerPost(db, { op: 'pw', pw1: p1, pw2: p2 });
    assert.equal(r.headers.get('Location'), `/frontier/_access?msg=${msg}`, JSON.stringify([p1, p2]));
  }
  assert.equal((await ownerPost(db, { op: 'pw', pw1: '密'.repeat(64), pw2: '密'.repeat(64) })).headers.get('Location'), '/frontier/_access?msg=pwset', '64 个汉字刚好');
  assert.equal((await ownerPost(db, { op: 'pw', pw1: '😀😀😀😀', pw2: '😀😀😀😀' })).headers.get('Location'), '/frontier/_access?msg=pwset', '按“字”数');
  const rec = setting(db, 'family_pw').value;
  assert.match(rec, /^[0-9a-f]{32}:[0-9a-f]{64}$/);
  assert.ok(!rec.includes('😀'));
  assert.equal(await checkPw(rec, '😀😀😀😀'), true);
  assert.equal(await checkPw(rec, '😀😀😀'), false);
  assert.notEqual(await makePwRecord('abcd'), await makePwRecord('abcd'), '每次换随机盐');
  // 切到“只有我”：本实例立刻生效（不等 15 秒）
  assert.equal((await send('/frontier/', { db })).status, 200);
  r = await ownerPost(db, { op: 'mode', mode: 'owner' });
  assert.equal(r.headers.get('Location'), '/frontier/_access?msg=mode-owner');
  assert.equal((await send('/frontier/', { db })).status, 403);
  let page = await (await send('/frontier/_access?msg=mode-owner', { db, headers: ownerCookie })).text();
  assert.ok(page.includes('已改成“只有我”'));
  assert.ok(page.includes('value="owner" class="on"'));
  assert.ok(page.includes('家人口令：已设'));
  assert.ok(/上次改动：\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}（英国时间）/.test(page));
  assert.ok(!page.includes('😀'), '设置页绝不显示口令');
  r = await ownerPost(db, { op: 'mode', mode: 'family' });
  assert.equal(r.headers.get('Location'), '/frontier/_access?msg=mode-family');
  assert.match(await (await send('/frontier/', { db })).text(), /只对部分人开放/);
  r = await ownerPost(db, { op: 'mode', mode: 'public' });
  assert.equal(r.headers.get('Location'), '/frontier/_access?msg=mode-public');
  assert.equal((await send('/frontier/', { db })).status, 200);
  for (const f of [{ op: 'mode', mode: 'everyone' }, { op: 'nope' }, {}]) assert.equal((await ownerPost(db, f)).headers.get('Location'), '/frontier/_access?msg=bad', JSON.stringify(f));
  page = await (await send('/frontier/_access?msg=%3Cscript%3E', { db, headers: ownerCookie })).text();
  assert.ok(!page.includes('<script'), '不认识的 msg 不显示');
  // 只记了公开档时匿名打开的 3 次首页；设置页、门页（凭口令、只有我时那几次）都不记
  assert.deepEqual(visitRows(db).map((x) => x.path), ['/frontier/', '/frontier/', '/frontier/']);
  fresh();
});

test('开放程度：线上迁移还没跑（没有 site_settings 表）时，设置页第一次写之前自己建表', async () => {
  fresh();
  const db = new FakeD1();                       // 只有 visits 表
  assert.equal((await send('/frontier/_access', { db, headers: ownerCookie })).status, 200);
  assert.equal((await ownerPost(db, { op: 'pw', pw1: PW, pw2: PW })).headers.get('Location'), '/frontier/_access?msg=pwset');
  assert.ok(db.log.some((q) => /CREATE TABLE IF NOT EXISTS site_settings/.test(q)));
  assert.equal((await ownerPost(db, { op: 'mode', mode: 'owner' })).headers.get('Location'), '/frontier/_access?msg=mode-owner');
  assert.equal(setting(db, 'access_mode').value, 'owner');
  assert.equal((await send('/frontier/', { db })).status, 403);
  fresh();
});

test('开放程度：别的实例最多 15 秒后读到新值（本实例缓存 15 秒）', async () => {
  fresh();
  const db = settingsDb();
  assert.equal((await send('/frontier/', { db })).status, 200);
  db.sql.prepare('INSERT INTO site_settings (key, value, updated_ts) VALUES (?, ?, ?)').run('access_mode', 'owner', Date.now());   // 别的实例改的
  assert.equal((await send('/frontier/', { db })).status, 200, '15 秒内还用缓存');
  ACCESS_STATE.at = Date.now() - ACCESS_TTL_MS - 1;
  assert.equal((await send('/frontier/', { db })).status, 403, '过了 15 秒读到新值');
  fresh();
});

test('开放程度：读库出错——本实例读到过就用上次的值；从没读到过就不放行（503“暂时打不开”），站长照常', async () => {
  // 一：读到过（只有我），之后数据库坏了、缓存也过期了 → 仍按“只有我”
  fresh();
  const db = settingsDb({ mode: 'owner' });
  assert.equal((await send('/frontier/', { db })).status, 403);
  db.fail = true;
  ACCESS_STATE.at = 0;
  LOGS.length = 0;
  const a = await send('/frontier/', { db });
  assert.equal(a.status, 403);
  assert.match(await a.text(), /网站在测试中/);
  assert.equal((await send('/frontier/', { db, headers: ownerCookie })).status, 200);
  assert.ok(LOGS.some((x) => /用本实例上次读到的值/.test(x)));
  // 读到过的是“凭口令”：口令 Cookie 照样能进
  fresh();
  const fdb = settingsDb();
  await familySetup(fdb);
  const fam = await login(fdb);
  fdb.fail = true;
  ACCESS_STATE.at = 0;
  assert.equal((await send('/frontier/', { db: fdb, headers: { Cookie: fam } })).status, 200);
  assert.equal((await send('/frontier/', { db: fdb })).status, 403);
  // 二：本实例从没读到过 → 不放行
  fresh();
  const bdb = settingsDb();
  bdb.fail = true;
  {
    for (const [p, headers] of [['/frontier/', {}], [AUDIO_PATH, { Range: 'bytes=0-1' }], ['/frontier/issues/2026-11-08/issue.js', {}]]) {
      const res = await send(p, { db: bdb, headers });
      assert.equal(res.status, 503, p);
      assert.equal(res.headers.get('Cache-Control'), 'no-store');
      assert.equal(res.headers.get('X-Robots-Tag'), 'noindex, nofollow');
      const html = await res.text();
      assert.match(html, /网站暂时打不开，请过一会儿再刷新/);
      assert.ok(!/<form/.test(html));
    }
    const own = await send('/frontier/', { db: bdb, headers: ownerCookie });
    assert.equal(own.status, 200, '站长照常');
    assert.equal(own.headers.get('Cache-Control'), 'private, no-cache', '读不到档位时按非公开处理缓存');
    const fb = await fbPost(bdb);
    assert.equal(fb.status, 503);
    assert.equal((await fb.json()).ok, false);
    const ent = await enter(bdb, { password: PW, next: '/frontier/' });
    assert.equal(ent.status, 503);
    const sp = await send('/frontier/_access', { db: bdb, headers: ownerCookie });
    assert.equal(sp.status, 200);
    assert.match(await sp.text(), /读数据库出错/);
    assert.equal((await ownerPost(bdb, { op: 'pw', pw1: PW, pw2: PW })).headers.get('Location'), '/frontier/_access?msg=dberr');
    assert.equal((await ownerPost(bdb, { op: 'mode', mode: 'owner' })).headers.get('Location'), '/frontier/_access?msg=dberr');
  }
  assert.ok(LOGS.some((x) => /本实例从没读到过，先不放行/.test(x)));
  assert.ok(!LOGS.join('\n').includes(PW), '日志里没有口令');
  assert.equal(ACCESS_STATE.value, null, '读不到时不缓存，下次再试');
  bdb.fail = false;
  assert.equal((await send('/frontier/', { db: bdb })).status, 200, '数据库好了就恢复');
  fresh();
});

test('开放程度：没绑数据库——网站按公开；设置页提示“没连上数据库，开放设置用不了”，提交回 nodb', async () => {
  fresh();
  const res = await send('/frontier/_access', { headers: ownerCookie });
  assert.equal(res.status, 200);
  const html = await res.text();
  assert.ok(html.includes('没连上数据库，开放设置用不了'));
  assert.ok(/<button type="submit" name="mode" value="owner"[^>]*disabled/.test(html), '按钮不能点');
  assert.equal((await ownerPost(undefined, { op: 'mode', mode: 'owner' })).headers.get('Location'), '/frontier/_access?msg=nodb');
  assert.equal((await send('/frontier/')).status, 200);
  assert.equal(ACCESS_STATE.value, null);
  fresh();
});

test('开放程度的小函数：privatize、loadSettings', async () => {
  assert.equal(privatize('public, max-age=600'), 'private, max-age=600');
  assert.equal(privatize('public, max-age=604800'), 'private, max-age=604800');
  assert.equal(privatize('no-cache'), 'private, no-cache');
  assert.equal(privatize('private, no-cache'), 'private, no-cache');
  assert.equal(privatize('no-store'), 'no-store');
  assert.deepEqual(await loadSettings(new FakeD1()), { mode: 'public', pw: '', token: '', modeTs: 0, pwTs: 0 });
  const db = settingsDb({ mode: 'family' });
  db.sql.prepare('INSERT INTO site_settings (key, value, updated_ts) VALUES (?, ?, ?)').run('family_pw', 'not-a-record', 1);
  const st = await loadSettings(db);
  assert.equal(st.mode, 'family');
  assert.equal(st.pw, '', '记录格式不对当作没设（谁都进不来）');
  assert.equal(st.token, '');
  const bad = new FakeD1();
  bad.fail = true;
  await assert.rejects(loadSettings(bad));
  fresh();
});
