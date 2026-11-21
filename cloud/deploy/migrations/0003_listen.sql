-- 耳听点选页（2026-11-21 加，src/listen.js）：站长在 /frontier/_listen 逐条听审片列出的“请你耳听”，点的结果存在这里。
-- 和访问统计、开放程度同一个 D1 数据库 frontier-visits（绑定 VISITS）。周六维护读它（导出：/frontier/_listen?export=json）。
-- Worker 第一次写之前自己也会执行一次同样的 CREATE TABLE IF NOT EXISTS，所以线上这条迁移还没跑时也能用。
-- 一条“请你耳听”一行，主键是（日期, 条目编号）：改了再点就覆盖，以最后一次为准。
--   date   期号 YYYY-MM-DD
--   item   条目编号：sha256(日期 + 位置 + 说明) 的前 10 位十六进制，同一期撞号时加 -2、-3（cloud/deploy/listen_items.py）
--   result right（念对了）／wrong（念错了）／unsure（没听出来）
--   note   可选的一句备注（最多 200 个字）
--   ts     最后一次点的时间：UTC 毫秒时间戳
CREATE TABLE IF NOT EXISTS listen_votes (
  date   TEXT    NOT NULL,
  item   TEXT    NOT NULL,
  result TEXT    NOT NULL,
  note   TEXT    NOT NULL DEFAULT '',
  ts     INTEGER NOT NULL,
  PRIMARY KEY (date, item)
);
