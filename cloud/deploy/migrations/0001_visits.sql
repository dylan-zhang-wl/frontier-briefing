-- 每日AI科技前沿简报网站的匿名访问统计（Cloudflare D1 数据库 frontier-visits，Worker 里的绑定名 VISITS）。照期刊网站 journals-visits 的表，
-- 多了三栏：kind（打开页面／开始听播客／开始看视频）、issue（期号）、latest（没带期号、看到的是最新一期）。
-- 每行是一次页面打开，或一次“开始听”“开始看”。不存 IP 地址、不存完整的浏览器标识（User-Agent）、不存完整的来源网址。
-- 记录保存 400 天：不用定时任务，Worker 每写进第 1000、2000……条时顺手删掉更早的，站长打开统计页时也删一次（src/visits.js 的 cleanupVisits）。
CREATE TABLE IF NOT EXISTS visits (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  ts       INTEGER NOT NULL,                -- 时间：UTC 毫秒时间戳
  day      TEXT    NOT NULL,                -- 英国时间的日期 YYYY-MM-DD（按天统计用）
  kind     TEXT    NOT NULL DEFAULT 'page', -- page = 打开页面；listen = 开始听播客（podcast.mp3）；watch = 开始看视频（旁白 video3.mp3）
  path     TEXT    NOT NULL,                -- 页面路径（/frontier/、/frontier/?date=…、/frontier/past/）或音频路径；只留 ?date=，别的参数一律去掉
  issue    TEXT    NOT NULL DEFAULT '',     -- 期号 YYYY-MM-DD；往期目录记 ''
  latest   INTEGER NOT NULL DEFAULT 0,      -- 1 = 网址没带期号（或期号不存在），看到的是当时的最新一期
  country  TEXT    NOT NULL DEFAULT '',     -- 国家或地区（两位代码，来自 Cloudflare）
  region   TEXT    NOT NULL DEFAULT '',     -- 省、州等
  city     TEXT    NOT NULL DEFAULT '',     -- 城市
  device   TEXT    NOT NULL DEFAULT '',     -- mobile／tablet／desktop
  browser  TEXT    NOT NULL DEFAULT '',     -- 浏览器（粗分，如 Chrome、Safari、微信）
  os       TEXT    NOT NULL DEFAULT '',     -- 系统（粗分，如 iOS、Android、Windows）
  referrer TEXT    NOT NULL DEFAULT '',     -- 来源网站的主机名；'' = 直接打开，'internal' = 站内跳转
  vid      TEXT    NOT NULL DEFAULT '',     -- 匿名访客编号（随机，存在访客浏览器的 fd_vid Cookie 里）；没有 Cookie 的音频请求记 ''
  is_new   INTEGER NOT NULL DEFAULT 0,      -- 1 = 这次才发编号的新访客
  lang     TEXT    NOT NULL DEFAULT ''      -- 浏览器语言（Accept-Language 第一项）
);
CREATE INDEX IF NOT EXISTS visits_day ON visits(day);
CREATE INDEX IF NOT EXISTS visits_ts ON visits(ts);
CREATE INDEX IF NOT EXISTS visits_vid_ts ON visits(vid, ts);   -- “开始听”“开始看”30 分钟内同一访客同一期只记一次，查重用
