-- 网站开放程度（11-10 加，src/access.js）：站长在设置页 /frontier/_access 切换的状态。和访问统计同一个 D1 数据库 frontier-visits（绑定 VISITS）。
-- 存在数据库里而不是代码或 wrangler.toml 里：每天自动出刊都会重新发布 Worker，代码和配置每天换新，数据库里的这一行不受影响，
-- 所以站长切的档位不会被每天的发布重置。
-- Worker 第一次写设置前自己也会执行一次同样的 CREATE TABLE IF NOT EXISTS，所以线上这条迁移还没跑时设置页也能用；
-- 表不存在或没有这一行时，网站按“公开”处理（和加这个功能以前一模一样）。
--   key = 'access_mode'：public（公开）／family（凭口令）／owner（只有我）
--   key = 'family_pw'  ：访问口令的“随机盐:SHA-256(盐+口令)”（盐是 16 字节的十六进制），不存口令本身
CREATE TABLE IF NOT EXISTS site_settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_ts INTEGER NOT NULL      -- 上次改动的时间：UTC 毫秒时间戳
);
