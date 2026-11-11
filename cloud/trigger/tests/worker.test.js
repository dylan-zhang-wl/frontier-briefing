// 保底触发器的本机测试：cd cloud/trigger && node --test tests/worker.test.js（Node 22 及以上，不用装任何东西、不联网、不需要 wrangler）。
// GitHub 和 Cloudflare 的接口都用假的 fetch 代替，记下每次请求，按设定回状态码。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import worker, { dispatch, checkToken, OFFICIAL_INPUTS, TEST_INPUTS, API_VERSION } from '../src/index.js';
import { main as tools, countCrons, OUR_CRONS, WORKER } from '../tools.mjs';

const TOKEN = 'github_pat_FAKE_0123456789abcdef';
const DISPATCH_URL = 'https://api.github.com/repos/dylan-zhang-wl/frontier-briefing/actions/workflows/frontier-daily.yml/dispatches';

function fakeFetch(...replies) {
  const calls = [];
  const fn = async (url, init = {}) => {
    calls.push({ url, init, body: init.body ? JSON.parse(init.body) : undefined });
    const r = replies.length > 1 ? replies.shift() : replies[0];
    if (r instanceof Error) throw r;
    if (typeof r === 'function') return r(url, init);
    const [status, body] = r;
    return new Response(body === undefined ? null : JSON.stringify(body), { status });
  };
  fn.calls = calls;
  return fn;
}
const quiet = () => { const lines = []; const log = (s) => lines.push(String(s)); log.lines = lines; return log; };
const noSleep = async () => {};

test('204 算成功：请求地址、方法、请求头、正式的输入都对', async () => {
  const f = fakeFetch([204]);
  const log = quiet();
  const r = await dispatch(TOKEN, { fetchImpl: f, log, sleep: noSleep });
  assert.equal(r.ok, true);
  assert.equal(r.status, 204);
  assert.equal(f.calls.length, 1);
  const { url, init, body } = f.calls[0];
  assert.equal(url, DISPATCH_URL);
  assert.equal(init.method, 'POST');
  assert.equal(init.headers.Authorization, `Bearer ${TOKEN}`);
  assert.equal(init.headers.Accept, 'application/vnd.github+json');
  assert.equal(init.headers['X-GitHub-Api-Version'], API_VERSION);
  assert.match(init.headers['User-Agent'], /frontier-daily-trigger/);
  assert.doesNotMatch(init.headers['User-Agent'], /@/);              // 不写邮箱
  assert.deepEqual(body, { ref: 'main', inputs: OFFICIAL_INPUTS, return_run_details: true });
  assert.deepEqual(body.inputs, { until: '17', review: 'true', upload_media: 'false', test_mode: 'false', gemini: 'default', extra: 'none' });
  assert.equal('date' in body.inputs, false);                         // date 留空＝当天 UTC
  for (const v of Object.values(body.inputs)) assert.equal(typeof v, 'string');
});

test('200 带运行编号也算成功，日志里记编号', async () => {
  const f = fakeFetch([200, { workflow_run_id: 4242, run_url: 'x', html_url: 'y' }]);
  const log = quiet();
  const r = await dispatch(TOKEN, { fetchImpl: f, log, sleep: noSleep });
  assert.equal(r.ok, true);
  assert.equal(r.runId, 4242);
  assert.match(log.lines.join('\n'), /状态码 200，运行编号 4242/);
});

test('日志里不出现令牌', async () => {
  for (const reply of [[204], [401, { message: 'Bad credentials' }], [500, { message: 'oops' }], new TypeError('fetch failed')]) {
    const log = quiet();
    await dispatch(TOKEN, { fetchImpl: fakeFetch(reply), log, sleep: noSleep });
    await checkToken(TOKEN, { fetchImpl: fakeFetch(reply), log });
    assert.doesNotMatch(log.lines.join('\n'), /FAKE_0123/);
  }
});

test('401、403、404、422 不重试', async () => {
  for (const s of [401, 403, 404, 422]) {
    const f = fakeFetch([s, { message: 'nope' }]);
    const log = quiet();
    const r = await dispatch(TOKEN, { fetchImpl: f, log, sleep: noSleep });
    assert.equal(r.ok, false);
    assert.equal(r.status, s);
    assert.equal(f.calls.length, 1, String(s));
    assert.match(log.lines.join('\n'), new RegExp(`状态码 ${s}（nope）`));
  }
});

test('5xx、429、连不上：隔一会儿再试，最多 3 次', async () => {
  const waits = [];
  const sleep = async (ms) => { waits.push(ms); };
  let f = fakeFetch([502, {}], new TypeError('fetch failed'), [204]);
  let r = await dispatch(TOKEN, { fetchImpl: f, log: quiet(), sleep, waitMs: 1000 });
  assert.equal(r.ok, true);
  assert.equal(r.attempts, 3);
  assert.deepEqual(waits, [1000, 2000]);
  f = fakeFetch([503, {}]);
  r = await dispatch(TOKEN, { fetchImpl: f, log: quiet(), sleep: noSleep });
  assert.equal(r.ok, false);
  assert.equal(f.calls.length, 3);
  f = fakeFetch([429, {}], [204]);
  r = await dispatch(TOKEN, { fetchImpl: f, log: quiet(), sleep: noSleep });
  assert.equal(r.ok, true);
});

test('接口不认 return_run_details（422 且说的是它）：去掉再发一次', async () => {
  const f = fakeFetch([422, { message: 'Invalid request. "return_run_details" is not a permitted key.' }], [204]);
  const r = await dispatch(TOKEN, { fetchImpl: f, log: quiet(), sleep: noSleep });
  assert.equal(r.ok, true);
  assert.equal(f.calls.length, 2);
  assert.equal('return_run_details' in f.calls[1].body, false);
});

test('没有令牌：不发请求', async () => {
  const f = fakeFetch([204]);
  const r = await dispatch('', { fetchImpl: f, log: quiet() });
  assert.equal(r.ok, false);
  assert.equal(f.calls.length, 0);
});

test('定时到了：用机密变量 GH_DISPATCH_TOKEN 发正式触发；失败就抛错（Cloudflare 记成失败）', async () => {
  const orig = globalThis.fetch;
  const origLog = console.log;
  const lines = [];
  console.log = (s) => lines.push(String(s));
  try {
    globalThis.fetch = fakeFetch([204]);
    await worker.scheduled({ cron: '43 4 * * *', scheduledTime: Date.UTC(2026, 10, 10, 4, 43) }, { GH_DISPATCH_TOKEN: TOKEN }, {});
    assert.equal(globalThis.fetch.calls[0].init.headers.Authorization, `Bearer ${TOKEN}`);
    assert.equal(globalThis.fetch.calls[0].body.inputs.test_mode, 'false');
    globalThis.fetch = fakeFetch([401, { message: 'Bad credentials' }]);
    await assert.rejects(worker.scheduled({ cron: '47 6 * * *', scheduledTime: Date.now() }, { GH_DISPATCH_TOKEN: TOKEN }, {}), /状态码 401/);
    await assert.rejects(worker.scheduled({ cron: '47 6 * * *', scheduledTime: Date.now() }, {}, {}), /失败/);
  } finally {
    globalThis.fetch = orig;
    console.log = origLog;
  }
  assert.match(lines.join('\n'), /定时 43 4 \* \* \* 到了（2026-11-10T04:43:00.000Z）/);
  assert.doesNotMatch(lines.join('\n'), /FAKE_0123/);
});

test('Worker 没有网址：没有 fetch 处理函数', () => {
  assert.equal(typeof worker.fetch, 'undefined');
});

test('测试触发：只抓取、不花钱', async () => {
  assert.deepEqual(TEST_INPUTS, { until: '3', review: 'false', upload_media: 'false', test_mode: 'true', gemini: 'off', extra: 'none' });
  const f = fakeFetch([200, { workflow_run_id: 7 }]);
  const log = quiet();
  assert.equal(await tools(['test-dispatch'], { GH_DISPATCH_TOKEN: TOKEN }, { fetchImpl: f, log }), 0);
  assert.deepEqual(f.calls[0].body.inputs, TEST_INPUTS);
  assert.match(log.lines.join('\n'), /actions\/runs\/7/);
});

test('只读核对令牌：读这个流程的信息', async () => {
  const f = fakeFetch([200, { state: 'active' }]);
  const log = quiet();
  assert.equal(await tools(['check-token'], { GH_DISPATCH_TOKEN: TOKEN }, { fetchImpl: f, log }), 0);
  assert.equal(f.calls[0].url, 'https://api.github.com/repos/dylan-zhang-wl/frontier-briefing/actions/workflows/frontier-daily.yml');
  assert.equal(f.calls[0].init.method, undefined);                    // GET
  assert.equal(await tools(['check-token'], { GH_DISPATCH_TOKEN: TOKEN }, { fetchImpl: fakeFetch([403, { message: 'Resource not accessible' }]), log }), 1);
  assert.equal(await tools(['check-token'], {}, { fetchImpl: fakeFetch([200, {}]), log }), 1);
});

// 假的 Cloudflare 接口：账号里有这几个 Worker 和定时
function fakeCF(workers) {
  return fakeFetch((url, init) => {
    const u = new URL(url);
    const m = u.pathname.match(/^\/client\/v4\/accounts\/ACC\/workers\/scripts(?:\/([^/]+)\/schedules)?$/);
    if (!m) return new Response(JSON.stringify({ success: false, errors: [{ code: 7003, message: 'no route' }] }), { status: 404 });
    if (!m[1]) return new Response(JSON.stringify({ success: true, result: Object.keys(workers).map((id) => ({ id })) }));
    const name = decodeURIComponent(m[1]);
    if (init.method === 'PUT') workers[name] = JSON.parse(init.body).map((x) => x.cron);
    return new Response(JSON.stringify({ success: true, result: { schedules: (workers[name] || []).map((cron) => ({ cron })) } }));
  });
}

test('数定时：别的 Worker 加上这三个不超过 5 个才放行', async () => {
  const env = { CLOUDFLARE_API_TOKEN: 'cf-fake\n', CLOUDFLARE_ACCOUNT_ID: 'ACC' };
  let log = quiet();
  const ok = { 'translatio-library': [], 'other-site': [], 'journals-observatory': ['17 3 * * *'], 'frontier-daily': [] };
  assert.equal(await tools(['count-crons'], env, { fetchImpl: fakeCF(ok), log }), 0);
  assert.match(log.lines.join('\n'), /别的 Worker 占了 1 个定时.*部署后一共 4 个，免费版上限 5 个/);
  // 正好 5 个放行，6 个就不放行
  assert.equal(await tools(['count-crons'], env, { fetchImpl: fakeCF({ a: ['1 * * * *', '2 * * * *'] }), log: quiet() }), 0);
  log = quiet();
  assert.equal(await tools(['count-crons'], env, { fetchImpl: fakeCF({ a: ['1 * * * *', '2 * * * *', '3 * * * *'] }), log }), 1);
  assert.match(log.lines.join('\n'), /部署后会是 6 个/);
  const full = { a: ['1 * * * *', '2 * * * *'], b: ['3 * * * *', '4 * * * *'], [WORKER]: OUR_CRONS.slice() };
  log = quiet();
  assert.equal(await tools(['count-crons'], env, { fetchImpl: fakeCF(full), log }), 1);
  assert.match(log.lines.join('\n'), /超了/);
  const r = await countCrons({ token: 't', account: 'ACC', fetchImpl: fakeCF(full) });
  assert.equal(r.others, 4);
  assert.equal(r.ours, 3);
  assert.equal(await tools(['count-crons'], { CLOUDFLARE_ACCOUNT_ID: 'ACC' }, { fetchImpl: fakeCF(ok), log: quiet() }), 1);
});

test('看定时、停：清空保底触发器的定时', async () => {
  const env = { CLOUDFLARE_API_TOKEN: 'cf-fake', CLOUDFLARE_ACCOUNT_ID: 'ACC' };
  const ws = { [WORKER]: OUR_CRONS.slice() };
  const f = fakeCF(ws);
  assert.equal(await tools(['schedules'], env, { fetchImpl: f, log: quiet() }), 0);
  assert.equal(await tools(['stop'], env, { fetchImpl: f, log: quiet() }), 0);
  assert.deepEqual(ws[WORKER], []);
  const put = f.calls.find((c) => c.init.method === 'PUT');
  assert.deepEqual(put.body, []);
  assert.equal(await tools(['schedules'], env, { fetchImpl: f, log: quiet() }), 1);
  // Cloudflare 回错时说清状态码，不出现账号编号以外的东西
  const log = quiet();
  assert.equal(await tools(['schedules'], { ...env, CLOUDFLARE_ACCOUNT_ID: 'OTHER' }, { fetchImpl: f, log }), 1);
  assert.match(log.lines.join('\n'), /状态码 404/);
  assert.doesNotMatch(log.lines.join('\n'), /cf-fake/);
});

test('wrangler.toml：名字、没有网址、三个定时（04:17 主力；和 tools.mjs 里的一致）', () => {
  const toml = readFileSync(new URL('../wrangler.toml', import.meta.url), 'utf8');
  const code = toml.split('\n').filter((l) => !l.trim().startsWith('#')).join('\n');
  assert.match(code, /^name = "frontier-daily-trigger"$/m);
  assert.match(code, /^workers_dev = false/m);
  assert.match(code, /^preview_urls = false/m);
  assert.doesNotMatch(code, /^routes|^route\s*=/m);
  const crons = JSON.parse(code.match(/^crons = (\[.*\])$/m)[1]);
  assert.deepEqual(crons, OUR_CRONS);
  assert.deepEqual(crons, ['17 4 * * *', '43 4 * * *', '47 6 * * *']);
  assert.doesNotMatch(code, /GH_DISPATCH_TOKEN\s*=/);                   // 机密变量不写在配置里
});
