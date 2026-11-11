// 每日AI科技前沿简报的"保底触发器"：Cloudflare 上一个独立的小 Worker（名字 frontier-daily-trigger），没有网址，只有三个定时。
//
// · 为什么要它：GitHub 自己的定时是"尽量准时"，高峰时会推迟、负载够大会丢（11-09 06:17 那次就没触发）。
//   11-10 实测更糟：流程文件里 GitHub 自己的两个定时（04:17、05:11 UTC）合进 main 以后一次也没触发过
//   （gh run list --event schedule 是空的），同一账号的期刊监控仓库，定时实际晚 3.5 到 10 小时、有的天直接丢；
//   11-10 那期是这里 04:43 叫起来的。所以 11-10 起主力是这里的 04:17 UTC，04:43、06:47 UTC（最后这个是晚补）是保底。
//   GitHub 那两个定时留着不动。叫几次都没关系：出刊流程第一段"认领"一天（cloud/trigger/claim.py），
//   同一天只有第一个认领到的真出刊，其余一分钟左右安静跳过。
// · 怎么叫：GitHub 官方接口 "Create a workflow dispatch event"
//   POST https://api.github.com/repos/dylan-zhang-wl/frontier-briefing/actions/workflows/frontier-daily.yml/dispatches
//   （2026-11 起叫公开仓库 frontier-briefing 的出刊流程；私有仓库 frontier-daily 里旧的出刊流程停用、留作退路）
//   （https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event），在 main 上按正式的输入跑。
//   带 return_run_details: true 时接口回 200 和运行编号（2026-02-19 起），不带或老做法回 204；两种都算成功。
// · 令牌：Worker 的机密变量 GH_DISPATCH_TOKEN（只对这个仓库有 Actions 读写的细粒度令牌，由部署流程从仓库 Secret 写进来）。
//   日志里只记状态码、成没成、运行编号和 GitHub 回的那句错误说明，不记令牌。
// · 出错：网络错、GitHub 回 5xx 或 429 时隔一会儿再试，最多 3 次；401、403、404、422 这类不重试（重试也没用）。
//   最后不成就抛错，Cloudflare 网页上这次定时会记成失败（Workers & Pages → frontier-daily-trigger → 日志／Cron Events）。
// · 没有网址：wrangler.toml 里 workers_dev = false、不挂路由；也没有 fetch 处理函数。
// · 本机测试：cd cloud/trigger && node --test tests/（不联网，用假的 GitHub 接口）。

export const REPO = 'dylan-zhang-wl/frontier-briefing';      // 出刊流程所在的仓库（2026-11 起是公开仓库）
export const WORKFLOW = 'frontier-daily.yml';
export const API = 'https://api.github.com';
export const API_VERSION = '2022-11-28';       // GitHub 至少支持到新版本（2026-03-10）发布后 24 个月
export const USER_AGENT = 'frontier-daily-trigger (Cloudflare Worker)';

// 正式的输入（和 GitHub 定时触发时一样；date 留空＝当天 UTC）。接口要的值都是字符串。
export const OFFICIAL_INPUTS = {
  until: '17', review: 'true', upload_media: 'false', test_mode: 'false', gemini: 'default', extra: 'none',
};
// 部署流程里"真发一次测试触发"用：只抓取、归并、入库，不用 Claude、不花钱、不发邮件、不发布
export const TEST_INPUTS = {
  until: '3', review: 'false', upload_media: 'false', test_mode: 'true', gemini: 'off', extra: 'none',
};

const RETRY_STATUS = new Set([429, 500, 502, 503, 504]);
const sleepMs = (ms) => new Promise((r) => setTimeout(r, ms));

export function headers(token) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': API_VERSION,
    'User-Agent': USER_AGENT,
  };
}

async function shortMessage(res) {
  try {
    const d = await res.json();
    return String(d && d.message ? d.message : '').slice(0, 200);
  } catch {
    return '';
  }
}

// 发一次"按正式跑"的请求。返回 { ok, status, attempts, runId?, message? }；不抛错。
export async function dispatch(token, { inputs = OFFICIAL_INPUTS, ref = 'main', fetchImpl = fetch, sleep = sleepMs,
  log = console.log, attempts = 3, waitMs = 20000, label = '正式' } = {}) {
  if (!token) {
    log('保底触发：没有机密变量 GH_DISPATCH_TOKEN，没发请求');
    return { ok: false, status: 0, attempts: 0, message: 'no token' };
  }
  const url = `${API}/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;
  let details = true;            // 要运行编号；万一接口不认这个参数（回 422 且说的是它），去掉再发一次
  let last = { ok: false, status: 0, attempts: 0 };
  for (let i = 1; i <= attempts; i++) {
    const body = JSON.stringify(details ? { ref, inputs, return_run_details: true } : { ref, inputs });
    let res;
    try {
      res = await fetchImpl(url, { method: 'POST', headers: { ...headers(token), 'Content-Type': 'application/json' }, body });
    } catch (e) {
      last = { ok: false, status: 0, attempts: i, message: `network: ${String(e && e.name || 'error')}` };
      log(`保底触发（${label}）第 ${i} 次：连不上 GitHub（${last.message}）`);
      if (i < attempts) await sleep(waitMs * i);
      continue;
    }
    if (res.status === 204) {
      log(`保底触发（${label}）：成功，状态码 204`);
      return { ok: true, status: 204, attempts: i };
    }
    if (res.status === 200) {
      let runId;
      try { runId = (await res.json()).workflow_run_id; } catch { /* 有些回应不带正文 */ }
      log(`保底触发（${label}）：成功，状态码 200${runId ? `，运行编号 ${runId}` : ''}`);
      return { ok: true, status: 200, attempts: i, runId };
    }
    const message = await shortMessage(res);
    last = { ok: false, status: res.status, attempts: i, message };
    log(`保底触发（${label}）第 ${i} 次：失败，状态码 ${res.status}${message ? `（${message}）` : ''}`);
    if (res.status === 422 && details && /return_run_details/.test(message)) { details = false; continue; }
    if (!RETRY_STATUS.has(res.status)) break;
    if (i < attempts) await sleep(waitMs * i);
  }
  return last;
}

// 只读核对令牌：读这个流程的信息（GET .../actions/workflows/frontier-daily.yml），200 就说明令牌能读这个仓库的 Actions。
export async function checkToken(token, { fetchImpl = fetch, log = console.log } = {}) {
  if (!token) {
    log('核对令牌：没有 GH_DISPATCH_TOKEN');
    return { ok: false, status: 0 };
  }
  let res;
  try {
    res = await fetchImpl(`${API}/repos/${REPO}/actions/workflows/${WORKFLOW}`, { headers: headers(token) });
  } catch (e) {
    log(`核对令牌：连不上 GitHub（${String(e && e.name || 'error')}）`);
    return { ok: false, status: 0 };
  }
  if (res.status === 200) {
    let state = '';
    try { state = (await res.json()).state || ''; } catch { /* 不要紧 */ }
    log(`核对令牌：成功，状态码 200，流程 ${WORKFLOW} 状态 ${state}`);
    return { ok: true, status: 200, state };
  }
  const message = await shortMessage(res);
  log(`核对令牌：失败，状态码 ${res.status}${message ? `（${message}）` : ''}`);
  return { ok: false, status: res.status, message };
}

export default {
  async scheduled(controller, env, ctx) {
    console.log(`保底触发：定时 ${controller.cron} 到了（${new Date(controller.scheduledTime).toISOString()}）`);
    const r = await dispatch(env.GH_DISPATCH_TOKEN);
    if (!r.ok) throw new Error(`保底触发失败：状态码 ${r.status}`);
  },
};
