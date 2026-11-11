// 站长的访问统计页 /frontier/_visits（只有带有效 fd_pass Cookie 的浏览器能看，判断在 index.js 里）。
// 照期刊网站（期刊监控仓库 site/deploy/src/stats.js）：服务端用 SQL 汇总后直接输出一页 HTML：内联样式、亮暗两种配色跟随系统、手机可看，
// 不引用任何外部资源，图表是内联 SVG。多了“期号”和每期的“开始听”“开始看”。
// 参数：r = 7／30／90／all（时间范围，默认 30）；tz = uk／cn（明细用英国时间或北京时间，默认英国）；format=csv 导出 CSV。
// 按天的统计一律按英国时间的日期（记录时写进 day 一栏）。
// 顶部有去“开放程度”设置页（src/access.js，11-10 加）和回网站的链接。

import { ukDay } from './visits.js';

const RANGES = { '7': 7, '30': 30, '90': 90, all: 0 };
const RANGE_LABEL = { '7': '近 7 天', '30': '近 30 天', '90': '近 90 天', all: '全部' };
const DEVICE = { mobile: '手机', tablet: '平板', desktop: '电脑' };
export const KIND = { page: '打开页面', listen: '开始听（播客）', watch: '开始看（视频）' };
const SVG_H = 250;
const PAGE = "kind = 'page'";

export function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function addDays(day, n) {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

let regionNames = null;
export function countryName(code) {
  if (!code || code === 'XX' || code === 'T1') return code === 'T1' ? '匿名网络（Tor）' : '未知';
  try {
    regionNames ||= new Intl.DisplayNames(['zh-CN'], { type: 'region' });
    return regionNames.of(code) || code;
  } catch (_) { return code; }
}

export function referrerLabel(r) {
  if (!r) return '直接打开';
  if (r === 'internal') return '站内跳转';
  return r;
}

// 期号 → 读者看得懂的名字
export function issueLabel(issue, latest) {
  if (issue) return `${issue} 期`;
  return latest ? '最新一期（日期没取到）' : '—';
}

// 路径 → 读者看得懂的名字
export function pageLabel(path) {
  const p = String(path || '');
  if (p === '/frontier/') return '首页（没带期号，看到最新一期）';
  if (p === '/frontier/past/') return '往期目录';
  let m = /^\/frontier\/\?date=(\d{4}-\d{2}-\d{2})$/.exec(p);
  if (m) return `${m[1]} 期（网址带期号）`;
  m = /^\/frontier\/issues\/(\d{4}-\d{2}-\d{2})\/audio\/(podcast|video3)\.mp3$/.exec(p);
  if (m) return `${m[2] === 'podcast' ? '播客' : '视频旁白'}：${m[1]} 期`;
  return p;
}

function fmtTime(ms, tz) {
  const zone = tz === 'cn' ? 'Asia/Shanghai' : 'Europe/London';
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })
    .formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second}`;
}

function parseParams(url) {
  const r = Object.prototype.hasOwnProperty.call(RANGES, url.searchParams.get('r')) ? url.searchParams.get('r') : '30';
  const tz = url.searchParams.get('tz') === 'cn' ? 'cn' : 'uk';
  return { r, tz };
}

async function runAll(db, list) {
  const stmts = list.map(([sql, ...args]) => db.prepare(sql).bind(...args));
  if (typeof db.batch === 'function') return (await db.batch(stmts)).map((x) => x.results || []);
  return Promise.all(stmts.map((s) => s.all().then((x) => x.results || [])));
}

// 一段时间的五个数：打开次数、访客、新访客（都只算打开页面）、开始听、开始看
function periodCols(tag, op) {
  return [
    `COUNT(CASE WHEN ${PAGE} AND day ${op} ? THEN 1 END) AS v${tag}`,
    `COUNT(DISTINCT CASE WHEN ${PAGE} AND day ${op} ? THEN vid END) AS u${tag}`,
    `COUNT(DISTINCT CASE WHEN ${PAGE} AND day ${op} ? AND is_new = 1 THEN vid END) AS n${tag}`,
    `COUNT(CASE WHEN kind = 'listen' AND day ${op} ? THEN 1 END) AS l${tag}`,
    `COUNT(CASE WHEN kind = 'watch' AND day ${op} ? THEN 1 END) AS w${tag}`,
  ];
}

// 汇总数据（统计页与测试共用）
export async function collectStats(db, r, now = Date.now()) {
  const today = ukDay(now);
  const d7 = addDays(today, -6), d30 = addDays(today, -29);
  const n = RANGES[r];
  const from = n ? addDays(today, -(n - 1)) : '0000-00-00';
  const lo = from < d30 ? from : d30;
  const periods = [['0', '=', today], ['7', '>=', d7], ['30', '>=', d30], ['r', '>=', from]];
  const sumSql = `SELECT ${periods.flatMap(([t, op]) => periodCols(t, op)).join(', ')} FROM visits WHERE day >= ?`;
  const sumArgs = [...periods.flatMap(([, , d]) => [d, d, d, d, d]), lo];
  const grp = (col, limit = 15, extra = '') =>
    [`SELECT ${col}, COUNT(*) AS v, COUNT(DISTINCT vid) AS u FROM visits WHERE ${PAGE} AND day >= ?${extra} GROUP BY ${col} ORDER BY v DESC, u DESC LIMIT ${limit}`, from];
  const [sum, daily, first, pages, issues, perIssue, countries, cities, devices, browsers, oses, refs, langs, recent] = await runAll(db, [
    [sumSql, ...sumArgs],
    [`SELECT day, COUNT(CASE WHEN ${PAGE} THEN 1 END) AS v, COUNT(DISTINCT CASE WHEN ${PAGE} THEN vid END) AS u,
       COUNT(CASE WHEN kind = 'listen' THEN 1 END) AS l, COUNT(CASE WHEN kind = 'watch' THEN 1 END) AS w
     FROM visits WHERE day >= ? GROUP BY day ORDER BY day`, n ? from : addDays(today, -399)],
    ['SELECT MIN(day) AS d, COUNT(*) AS total FROM visits'],
    grp('path'),
    [`SELECT issue, COUNT(*) AS v, COUNT(DISTINCT vid) AS u, SUM(latest) AS l FROM visits WHERE ${PAGE} AND day >= ? AND (issue != '' OR latest = 1)
      GROUP BY issue ORDER BY v DESC, u DESC LIMIT 15`, from],
    [`SELECT issue,
       COUNT(CASE WHEN ${PAGE} THEN 1 END) AS pv, COUNT(DISTINCT CASE WHEN ${PAGE} THEN vid END) AS pu,
       COUNT(CASE WHEN kind = 'listen' THEN 1 END) AS lv, COUNT(DISTINCT CASE WHEN kind = 'listen' AND vid != '' THEN vid END) AS lu,
       COUNT(CASE WHEN kind = 'watch' THEN 1 END) AS wv, COUNT(DISTINCT CASE WHEN kind = 'watch' AND vid != '' THEN vid END) AS wu
     FROM visits WHERE day >= ? AND issue != '' GROUP BY issue ORDER BY issue DESC LIMIT 90`, from],
    grp('country'),
    [`SELECT country, region, city, COUNT(*) AS v, COUNT(DISTINCT vid) AS u FROM visits WHERE ${PAGE} AND day >= ? AND city != '' GROUP BY country, region, city ORDER BY v DESC, u DESC LIMIT 15`, from],
    grp('device'),
    grp('browser', 10),
    grp('os', 10),
    grp('referrer'),
    grp('lang', 10),
    ['SELECT ts, kind, path, issue, latest, country, region, city, device, browser, os, referrer, vid, is_new, lang FROM visits WHERE day >= ? ORDER BY ts DESC LIMIT 100', from],
  ]);
  const s = sum[0] || {};
  const firstDay = (first[0] && first[0].d) || today;
  const chartFrom = n ? from : (firstDay > addDays(today, -399) ? firstDay : addDays(today, -399));
  const byDay = new Map(daily.map((x) => [x.day, x]));
  const series = [];
  for (let d = chartFrom; d <= today; d = addDays(d, 1)) {
    const x = byDay.get(d);
    series.push({ day: d, v: x ? Number(x.v) : 0, u: x ? Number(x.u) : 0, l: x ? Number(x.l) : 0, w: x ? Number(x.w) : 0 });
  }
  const num = (k) => Number(s[k] || 0);
  const card = (label, t) => ({ label, v: num('v' + t), u: num('u' + t), n: num('n' + t), l: num('l' + t), w: num('w' + t) });
  return {
    today, from, r,
    summary: [card('今天', '0'), card('近 7 天', '7'), card('近 30 天', '30'), ...(r === '7' || r === '30' ? [] : [card(RANGE_LABEL[r], 'r')])],
    series, totalAll: Number((first[0] && first[0].total) || 0), firstDay: first[0] && first[0].d,
    pages, issues, perIssue, countries, cities, devices, browsers, oses, refs, langs, recent,
  };
}

/* ── 页面 ── */

const CSS = `
:root{color-scheme:light dark;--bg:#f5f5f7;--card:#fff;--ink:#1d1d1f;--mute:#636366;--line:#e3e3e8;--acc:#0062c4;--acc2:#b86400;--bar:#dfeafa;--on:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#0a0a0c;--card:#1c1c1e;--ink:#f5f5f7;--mute:#a1a1a6;--line:#2c2c2e;--acc:#4ea1ff;--acc2:#ffb340;--bar:#1d3350;--on:#06121f}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:20px 16px 48px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:0 0 10px}
.note{color:var(--mute);font-size:13px;margin:0}
a{color:var(--acc)}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:16px 0}
.bar a,.bar span.on{padding:4px 12px;border:1px solid var(--line);border-radius:999px;text-decoration:none;font-size:14px;color:var(--ink);background:var(--card)}
.bar span.on{background:var(--acc);border-color:var(--acc);color:var(--on);font-weight:600}
.bar .sp{flex:1}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;min-width:0}
.kpi h3{margin:0 0 6px;font-size:14px;color:var(--mute);font-weight:600}
.kpi .nums{display:flex;gap:16px;flex-wrap:wrap}
.kpi b{display:block;font-size:24px;line-height:1.2}
.kpi small{color:var(--mute);font-size:12px}
.kpi .play{margin-top:6px;font-size:13px;color:var(--mute)}
.kpi .play b{display:inline;font-size:15px;color:var(--ink)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-top:12px}
.full{margin-top:12px}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:5px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mute);font-weight:600;font-size:12px;white-space:nowrap}
td.n,th.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
td.n small{color:var(--mute)}
td.nw{white-space:nowrap}
.rank td.name{width:60%;position:relative}
.rank .fill{position:absolute;left:0;top:3px;bottom:3px;background:var(--bar);border-radius:4px;z-index:0}
.rank .txt{position:relative;z-index:1;padding-left:4px;word-break:break-word}
.recent td{white-space:nowrap}
.recent td.path{white-space:normal;min-width:160px}
.empty{color:var(--mute);font-size:14px;padding:8px 0}
svg text{fill:var(--mute);font-size:15px}
.legend{display:flex;gap:16px;font-size:13px;color:var(--mute);margin-bottom:6px}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:4px;vertical-align:-1px}
`;

function rankTable(rows, label, unit = '次') {
  if (!rows.length) return '<div class="empty">这段时间还没有记录。</div>';
  const max = Math.max(...rows.map((x) => Number(x.v) || 0), 1);
  const tr = rows.map((x) => `<tr><td class="name"><span class="fill" style="width:${((Number(x.v) / max) * 100).toFixed(1)}%"></span><span class="txt">${esc(label(x))}</span></td><td class="n">${x.v} ${unit}</td><td class="n">${x.u} 人</td></tr>`).join('');
  return `<table class="rank"><thead><tr><th>名称</th><th class="n">访问</th><th class="n">访客</th></tr></thead><tbody>${tr}</tbody></table>`;
}

// 每期：打开、开始听、开始看（次数和人数），最新一期在最前
function perIssueTable(rows) {
  if (!rows.length) return '<div class="empty">这段时间还没有记录。</div>';
  const cell = (v, u) => `<td class="n">${Number(v) || 0} 次 <small>${Number(u) || 0} 人</small></td>`;
  const tr = rows.map((x) => `<tr><td class="nw">${esc(issueLabel(x.issue))}</td>${cell(x.pv, x.pu)}${cell(x.lv, x.lu)}${cell(x.wv, x.wu)}</tr>`).join('');
  return `<div class="scroll"><table><thead><tr><th>期号</th><th class="n">打开</th><th class="n">开始听<br><small>播客</small></th><th class="n">开始看<br><small>视频</small></th></tr></thead><tbody>${tr}</tbody></table></div>`;
}

// 横轴日期标签抽稀（照期刊网站）：标签“月-日”约 44 个画布单位宽，相邻两个之间至少留 10 个单位；最后一个放不下就右对齐。返回要显示标签的下标。
export const AXIS_LABEL_W = 44, AXIS_LABEL_GAP = 10;
export function axisLabelIndices(n, step, lastEnd = true, labelW = AXIS_LABEL_W, gap = AXIS_LABEL_GAP) {
  if (n <= 0) return [];
  if (n === 1) return [0];
  const k = Math.max(1, Math.ceil((labelW + gap) / step));
  const last = n - 1;
  const lastLeft = last * step - (lastEnd ? labelW : labelW / 2);
  const out = [];
  for (let i = 0; i < last; i += k) {
    if (i === 0 || i * step + labelW / 2 + gap <= lastLeft) out.push(i);
  }
  out.push(last);
  return out;
}

export function chartSVG(series) {
  // 天数少（7 天）时画布窄一些，手机上字也清楚；天数多时画布宽，手机上可左右滑动（默认停在最右边、即最近几天）
  const short = series.length <= 14;
  const SVG_W = short ? 480 : 800;
  const padL = 44, padR = 12, padT = 14, padB = 34;
  const w = SVG_W - padL - padR, h = SVG_H - padT - padB;
  const max = Math.max(1, ...series.map((x) => x.v));
  const nice = max <= 5 ? 5 : Math.ceil(max / 5) * 5;
  const step = w / Math.max(series.length, 1);
  const bw = Math.max(1, Math.min(28, step * 0.7));
  const y = (v) => padT + h - (v / nice) * h;
  const lastEnd = series.length > 1 && padL + step * (series.length - 0.5) + AXIS_LABEL_W / 2 + 4 > SVG_W;
  const labels = new Set(axisLabelIndices(series.length, step, lastEnd));
  let out = `<svg viewBox="0 0 ${SVG_W} ${SVG_H}" style="width:100%;min-width:${short ? 0 : 560}px;height:auto;display:block" role="img" aria-label="每天打开次数与访客数">`;
  for (const t of [0, nice / 2, nice]) {
    out += `<line x1="${padL}" x2="${SVG_W - padR}" y1="${y(t).toFixed(1)}" y2="${y(t).toFixed(1)}" stroke="var(--line)" stroke-width="1"/>`;
    out += `<text x="${padL - 6}" y="${(y(t) + 5).toFixed(1)}" text-anchor="end">${Number.isInteger(t) ? t : t.toFixed(1)}</text>`;
  }
  const pts = [];
  series.forEach((x, i) => {
    const cx = padL + step * i + step / 2;
    out += `<rect x="${(cx - bw / 2).toFixed(1)}" y="${y(x.v).toFixed(1)}" width="${bw.toFixed(1)}" height="${(padT + h - y(x.v)).toFixed(1)}" fill="var(--acc)" opacity="0.85" rx="2"><title>${x.day}：打开 ${x.v} 次，访客 ${x.u} 人，开始听 ${x.l || 0} 次，开始看 ${x.w || 0} 次</title></rect>`;
    pts.push(`${cx.toFixed(1)},${y(x.u).toFixed(1)}`);
    if (labels.has(i)) out += `<text x="${cx.toFixed(1)}" y="${SVG_H - 10}" text-anchor="${i === series.length - 1 && lastEnd ? 'end' : 'middle'}">${x.day.slice(5)}</text>`;
  });
  if (pts.length > 1) out += `<polyline points="${pts.join(' ')}" fill="none" stroke="var(--acc2)" stroke-width="2.5" stroke-linejoin="round"/>`;
  if (series.length <= 45) for (const p of pts) { const [cx, cy] = p.split(','); out += `<circle cx="${cx}" cy="${cy}" r="3.2" fill="var(--acc2)"/>`; }
  return out + '</svg>';
}

function link(params, label, on) {
  if (on) return `<span class="on">${esc(label)}</span>`;
  const q = new URLSearchParams(params).toString();
  return `<a href="/frontier/_visits${q ? '?' + q : ''}">${esc(label)}</a>`;
}

export function renderPage(st, { r, tz, dbError = '' }) {
  const lbl = { tz: tz === 'cn' ? '北京时间' : '英国时间' };
  const ranges = ['7', '30', '90', 'all'].map((k) => link({ r: k, ...(tz === 'cn' ? { tz } : {}) }, RANGE_LABEL[k], k === r)).join('');
  const tzs = link({ r }, '英国时间', tz === 'uk') + link({ r, tz: 'cn' }, '北京时间', tz === 'cn');
  const csv = `<a href="/frontier/_visits?${new URLSearchParams({ r, ...(tz === 'cn' ? { tz } : {}), format: 'csv' })}">导出 CSV</a>`;
  const kpis = st.summary.map((x) => `<div class="card kpi"><h3>${esc(x.label)}</h3><div class="nums"><div><b>${x.v}</b><small>打开次数</small></div><div><b>${x.u}</b><small>访客</small></div><div><b>${x.n}</b><small>新访客</small></div></div><div class="play">开始听 <b>${x.l}</b> 次 · 开始看 <b>${x.w}</b> 次</div></div>`).join('');
  const rl = RANGE_LABEL[r];
  const recent = st.recent.length ? `<div class="scroll"><table class="recent"><thead><tr><th>时间（${lbl.tz}）</th><th>类型</th><th>期号</th><th>页面</th><th>国家／地区</th><th>城市</th><th>设备</th><th>浏览器</th><th>系统</th><th>来源</th><th>访客</th><th>语言</th></tr></thead><tbody>${
    st.recent.map((x) => `<tr><td>${esc(fmtTime(x.ts, tz))}</td><td>${esc(KIND[x.kind] || x.kind)}</td><td>${esc(x.kind === 'page' && !x.issue && !x.latest ? '' : issueLabel(x.issue, x.latest))}${x.latest ? ' <small style="color:var(--acc)">最新</small>' : ''}</td><td class="path">${esc(pageLabel(x.path))}</td><td>${esc(countryName(x.country))}</td><td>${esc([x.city, x.region].filter(Boolean).join('，'))}</td><td>${esc(DEVICE[x.device] || x.device)}</td><td>${esc(x.browser)}</td><td>${esc(x.os)}</td><td>${esc(referrerLabel(x.referrer))}</td><td title="匿名访客编号">${esc(String(x.vid || '').slice(0, 8) || '—')}${x.is_new ? ' <small style="color:var(--acc)">新</small>' : ''}</td><td>${esc(x.lang)}</td></tr>`).join('')
  }</tbody></table></div>` : '<div class="empty">这段时间还没有记录。</div>';
  const dbNote = dbError ? `<p class="note" style="color:var(--acc2)">${esc(dbError)}，下面的数字都是 0。</p>` : '';
  return `<!doctype html><html lang="zh-Hans"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex, nofollow"><meta name="color-scheme" content="light dark"><link rel="icon" href="data:,"><title>访问统计 · 每日AI科技前沿简报</title><style>${CSS}</style></head>
<body><div class="wrap">
<div class="bar" style="margin:0 0 12px"><a href="/frontier/_access">开放程度设置</a><a href="/frontier/">回到网站</a></div>
<h1>访问统计</h1>
<p class="note">只有你（带站长 Cookie 的浏览器）能看到这一页；你自己的访问不计入。按天统计都按英国时间的日期。数据保存 400 天。</p>
${dbNote}
<div class="bar">${ranges}<span class="sp"></span>${tzs}${csv}</div>
<div class="kpis">${kpis}</div>
<div class="card full"><h2>每天打开次数与访客数（${esc(rl)}）</h2><div class="legend"><span><i style="background:var(--acc)"></i>打开次数</span><span><i style="background:var(--acc2)"></i>访客数</span></div><div class="scroll" id="chart">${chartSVG(st.series)}</div><p class="note" style="margin-top:6px">手指按住或鼠标停在柱子上，能看到那天的开始听、开始看次数。</p></div>
<div class="card full"><h2>每期：打开、开始听、开始看（${esc(rl)}）</h2><p class="note" style="margin-bottom:8px">“开始听”：播客从头被请求了一次（按了播放）。“开始看”：视频旁白从头被请求了一次——视频播放器滚到附近就会先读一小段旁白，所以没按播放也可能算进来，这一栏偏多。同一访客同一期 30 分钟内只算一次；拖动进度条不算。</p>${perIssueTable(st.perIssue)}</div>
<div class="grid">
  <div class="card"><h2>最常看的期号</h2>${rankTable(st.issues, (x) => issueLabel(x.issue, x.l) + (Number(x.l) ? `（其中 ${x.l} 次没带期号，看到的是最新一期）` : ''))}</div>
  <div class="card"><h2>最常打开的页面</h2>${rankTable(st.pages, (x) => pageLabel(x.path))}</div>
  <div class="card"><h2>来源网站</h2>${rankTable(st.refs, (x) => referrerLabel(x.referrer))}</div>
  <div class="card"><h2>国家／地区</h2>${rankTable(st.countries, (x) => countryName(x.country))}</div>
  <div class="card"><h2>城市</h2>${rankTable(st.cities, (x) => `${x.city}（${[x.region, countryName(x.country)].filter(Boolean).join('，')}）`)}</div>
  <div class="card"><h2>设备类型</h2>${rankTable(st.devices, (x) => DEVICE[x.device] || x.device || '未知')}</div>
  <div class="card"><h2>浏览器</h2>${rankTable(st.browsers, (x) => x.browser || '未知')}</div>
  <div class="card"><h2>系统</h2>${rankTable(st.oses, (x) => x.os || '未知')}</div>
  <div class="card"><h2>浏览器语言</h2>${rankTable(st.langs, (x) => x.lang || '未知')}</div>
</div>
<div class="card full"><h2>最近 100 次（${esc(rl)}）</h2><p class="note" style="margin-bottom:8px">时间为${lbl.tz}${tz === 'cn' ? '' : '（北京时间比英国时间快 8 小时，英国夏令时期间快 7 小时）'}。访客一栏是随机编号的前 8 位，“新”表示这次是第一次来；“—”表示这次请求没带编号。“最新”表示网址没带期号，看到的是当时的最新一期。“直接打开”指没有来源信息：输入网址、书签、多数聊天软件里点开的链接都算这一类。</p>${recent}</div>
<p class="note" style="margin-top:16px">记录的内容：时间、类型（打开页面／开始听／开始看）、期号、页面、国家／地区与城市（Cloudflare 按网络推断，不一定准）、设备类型、浏览器与系统（粗分）、来源网站的域名、浏览器语言、随机访客编号。不记录 IP 地址、完整的浏览器标识和完整的来源网址；爬虫与自动程序不记。共有记录 ${st.totalAll} 条${st.firstDay ? `，最早 ${esc(st.firstDay)}` : ''}。</p>
</div><script>var c=document.getElementById('chart');if(c)c.scrollLeft=c.scrollWidth;</script></body></html>`;
}

function csvCell(v) {
  let s = String(v == null ? '' : v);
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;          // 防止 Excel 把内容当公式
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export async function csvRows(db, r, now = Date.now()) {
  const today = ukDay(now);
  const n = RANGES[r];
  const from = n ? addDays(today, -(n - 1)) : '0000-00-00';
  const res = await db.prepare('SELECT ts, day, kind, path, issue, latest, country, region, city, device, browser, os, referrer, vid, is_new, lang FROM visits WHERE day >= ? ORDER BY ts LIMIT 200000').bind(from).all();
  return res.results || [];
}

export function toCSV(rows) {
  const head = ['时间（英国）', '时间（北京）', '日期（英国）', '类型', '期号', '没带期号（最新一期）', '页面', '路径', '国家／地区', '国家代码', '地区', '城市', '设备', '浏览器', '系统', '来源', '访客编号', '新访客', '语言'];
  const lines = [head.map(csvCell).join(',')];
  for (const x of rows) {
    lines.push([fmtTime(x.ts, 'uk'), fmtTime(x.ts, 'cn'), x.day, KIND[x.kind] || x.kind, x.issue, x.latest ? '是' : '否', pageLabel(x.path), x.path,
      countryName(x.country), x.country, x.region, x.city, DEVICE[x.device] || x.device, x.browser, x.os, referrerLabel(x.referrer), x.vid,
      x.is_new ? '是' : '否', x.lang].map(csvCell).join(','));
  }
  return '﻿' + lines.join('\r\n') + '\r\n';
}

const NO_STORE = { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow', 'Referrer-Policy': 'same-origin', 'X-Content-Type-Options': 'nosniff' };

export async function statsResponse(req, url, env, now = Date.now()) {
  const { r, tz } = parseParams(url);
  const db = env && env.VISITS;
  if (url.searchParams.get('format') === 'csv') {
    let rows = [];
    try { if (db) rows = await csvRows(db, r, now); } catch (_) { rows = []; }
    const name = `frontier-visits-${r === 'all' ? 'all' : r + 'd'}-${ukDay(now)}.csv`;
    return new Response(req.method === 'HEAD' ? null : toCSV(rows), {
      status: 200, headers: { ...NO_STORE, 'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': `attachment; filename="${name}"` },
    });
  }
  let st = null, dbError = '';
  if (!db) dbError = '还没有连上统计数据库（Worker 缺少 VISITS 绑定）';
  else {
    try { st = await collectStats(db, r, now); } catch (e) { dbError = `读取统计数据库出错（${String((e && e.message) || e).slice(0, 200)}）`; }
  }
  st ||= { summary: [], series: [], pages: [], issues: [], perIssue: [], countries: [], cities: [], devices: [], browsers: [], oses: [], refs: [], langs: [], recent: [], totalAll: 0 };
  const html = renderPage(st, { r, tz, dbError });
  return new Response(req.method === 'HEAD' ? null : html, { status: 200, headers: { ...NO_STORE, 'Content-Type': 'text/html; charset=utf-8' } });
}
