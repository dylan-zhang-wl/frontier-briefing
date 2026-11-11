// 保底触发器的几样手动工具（部署流程 .github/workflows/trigger-deploy.yml 里用；本机也能跑）。只用 Node 22 自带的 fetch，不装任何东西。
//
//   node cloud/trigger/tools.mjs check-token       用 GH_DISPATCH_TOKEN 只读核对：能不能读出刊流程 frontier-daily.yml（在 src/index.js 的 REPO 那个仓库）
//   node cloud/trigger/tools.mjs test-dispatch     用 GH_DISPATCH_TOKEN 真发一次测试触发（test_mode=true、until=3、gemini=off：只抓取，不花钱）
//   node cloud/trigger/tools.mjs count-crons       用 CLOUDFLARE_API_TOKEN 数账号里各个 Worker 已经占了几个定时；
//                                                  加上保底触发器的三个超过免费版上限（5 个）就退出码 1
//   node cloud/trigger/tools.mjs schedules         看保底触发器现在的定时
//   node cloud/trigger/tools.mjs stop              停：把保底触发器的定时清空（Worker 留着，重新部署就恢复）
//
// 令牌只从环境变量读，不打印；账号编号读 CLOUDFLARE_ACCOUNT_ID（不是秘密）。
import { pathToFileURL } from 'node:url';
import { checkToken, dispatch, TEST_INPUTS } from './src/index.js';

export const WORKER = 'frontier-daily-trigger';
export const OUR_CRONS = ['17 4 * * *', '43 4 * * *', '47 6 * * *'];   // 和 wrangler.toml 一致（测试里核对）；04:17 是主力
export const FREE_LIMIT = 5;          // https://developers.cloudflare.com/workers/platform/limits/ ："Number of Cron Triggers per account"
const CF = 'https://api.cloudflare.com/client/v4';

async function cf(path, { token, method = 'GET', body, fetchImpl = fetch } = {}) {
  const res = await fetchImpl(CF + path, {
    method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let d = {};
  try { d = await res.json(); } catch { /* 没有正文 */ }
  if (!res.ok || d.success === false) {
    const errs = (d.errors || []).map((e) => `${e.code} ${e.message}`).join('；');
    const err = new Error(`Cloudflare 接口 ${method} ${path.replace(/accounts\/[^/]+/, 'accounts/…')} 失败：状态码 ${res.status}${errs ? `（${errs}）` : ''}`);
    err.status = res.status;
    throw err;
  }
  return d.result;
}

// 数账号里每个 Worker 的定时。返回 { perWorker: {名字: [cron…]}, others: 不算保底触发器的个数, ours: 保底触发器现有的个数 }
export async function countCrons({ token, account, fetchImpl = fetch } = {}) {
  const scripts = await cf(`/accounts/${account}/workers/scripts`, { token, fetchImpl });
  const perWorker = {};
  for (const s of scripts || []) {
    const name = s.id;
    const r = await cf(`/accounts/${account}/workers/scripts/${encodeURIComponent(name)}/schedules`, { token, fetchImpl });
    perWorker[name] = ((r && r.schedules) || []).map((x) => x.cron);
  }
  let others = 0;
  for (const [name, crons] of Object.entries(perWorker)) if (name !== WORKER) others += crons.length;
  return { perWorker, others, ours: (perWorker[WORKER] || []).length };
}

export async function schedules({ token, account, fetchImpl = fetch } = {}) {
  const r = await cf(`/accounts/${account}/workers/scripts/${WORKER}/schedules`, { token, fetchImpl });
  return ((r && r.schedules) || []).map((x) => x.cron);
}

export async function stop({ token, account, fetchImpl = fetch } = {}) {
  const r = await cf(`/accounts/${account}/workers/scripts/${WORKER}/schedules`, { token, method: 'PUT', body: [], fetchImpl });
  return ((r && r.schedules) || []).map((x) => x.cron);
}

export async function main(argv = process.argv.slice(2), env = process.env, { fetchImpl = fetch, log = console.log } = {}) {
  const cmd = argv[0];
  const cfToken = (env.CLOUDFLARE_API_TOKEN || '').replace(/\s+/g, '');      // 粘贴时带的换行、空格去掉
  const ghToken = (env.GH_DISPATCH_TOKEN || '').replace(/\s+/g, '');
  const account = env.CLOUDFLARE_ACCOUNT_ID || '';
  try {
    if (cmd === 'check-token') {
      return (await checkToken(ghToken, { fetchImpl, log })).ok ? 0 : 1;
    }
    if (cmd === 'test-dispatch') {
      const r = await dispatch(ghToken, { inputs: TEST_INPUTS, fetchImpl, log, label: '测试', waitMs: 10000 });
      if (r.ok && r.runId) log(`测试运行：https://github.com/dylan-zhang-wl/frontier-briefing/actions/runs/${r.runId}`);
      return r.ok ? 0 : 1;
    }
    if (!cfToken || !account) {
      log('没有 CLOUDFLARE_API_TOKEN 或 CLOUDFLARE_ACCOUNT_ID');
      return 1;
    }
    if (cmd === 'count-crons') {
      const { perWorker, others, ours } = await countCrons({ token: cfToken, account, fetchImpl });
      for (const [name, crons] of Object.entries(perWorker)) log(`  ${name}：${crons.length} 个${crons.length ? `（${crons.join('、')}）` : ''}`);
      const total = others + OUR_CRONS.length;
      log(`账号里 ${Object.keys(perWorker).length} 个 Worker；别的 Worker 占了 ${others} 个定时，保底触发器现有 ${ours} 个；`
        + `部署后一共 ${total} 个，免费版上限 ${FREE_LIMIT} 个`);
      if (total > FREE_LIMIT) {
        log(`超了：部署后会是 ${total} 个，大于 ${FREE_LIMIT}。先腾出定时，或者把 cloud/trigger/wrangler.toml 的定时减少几个`);
        return 1;
      }
      return 0;
    }
    if (cmd === 'schedules') {
      const crons = await schedules({ token: cfToken, account, fetchImpl });
      log(`${WORKER} 现在的定时：${crons.length ? crons.join('、') : '（没有）'}`);
      const same = crons.length === OUR_CRONS.length && OUR_CRONS.every((c) => crons.includes(c));
      log(same ? '和 wrangler.toml 里写的一样' : `和 wrangler.toml 里写的（${OUR_CRONS.join('、')}）不一样`);
      return same ? 0 : 1;
    }
    if (cmd === 'stop') {
      const crons = await stop({ token: cfToken, account, fetchImpl });
      log(`${WORKER} 的定时已清空，现在：${crons.length ? crons.join('、') : '（没有）'}。Worker 还在，重新部署就恢复 ${OUR_CRONS.length} 个定时`);
      return crons.length === 0 ? 0 : 1;
    }
    log(`不认识的命令：${cmd || '（空）'}；可用 check-token、test-dispatch、count-crons、schedules、stop`);
    return 2;
  } catch (e) {
    log(String(e && e.message || e));
    return 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().then((rc) => { process.exitCode = rc; });
}
