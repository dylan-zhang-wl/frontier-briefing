# 网站发布（Cloudflare Worker `frontier-daily`）

网址：**https://wenlongzhang.com/frontier/** 。不让搜索引擎收录：每个页面有 `noindex, nofollow` 标签，每个响应带 `X-Robots-Tag: noindex, nofollow`。默认不设口令，就是“不公开，但谁拿到网址都能打开”；11-10 起站长可以在设置页把网站切成“凭口令”（要输访问口令）或“只有我”（别人只看到“测试中”），见下面“开放程度”。

照期刊网站 `journals-observatory`（期刊监控仓库 `site/deploy/`）的做法：一个**独立的 Worker**，路由只截 `wenlongzhang.com/frontier` 和 `wenlongzhang.com/frontier/*`。主域名 wenlongzhang.com 是知识库（Worker `translatio-library`）的，`/memory` 是另一个网站的，`/journals` 是期刊网站的，都不受影响（Cloudflare 按最具体的路由匹配）。

**不用建子域名，也不用改 DNS（域名解析）**：路由挂在已有的 wenlongzhang.com 上，发布时 wrangler 自己把两条路由登记好。

## 网址怎么分

| 网址 | 是什么 |
|---|---|
| `/frontier/` | 最新一期（就是 `site/v3` 那一页，底部有“往期目录”链接，刊头日期旁的日历也能换期） |
| `/frontier/?date=2026-11-09` | 某一期（`site/v3/app.js` 原有的换期办法） |
| `/frontier/2026-11-09/` | 好记的写法，跳到上一行 |
| `/frontier/past/` | 往期目录：日期、版别、标题，最新一期在最前 |
| `/frontier/issues/<日期>/…` | 每期的数据、音频、图片、字体（页面自己读，不用直接打开） |
| `/frontier/feedback` | 只收 POST：页面底部“反馈”框提交到这里（11-10 加，见下面“读者反馈：唯一的 POST 例外”） |
| `/frontier/_visits` | 站长的访问统计页（11-10 加）：只有带站长 Cookie 的浏览器能看，别人看到的和普通“没有这个页面”一样（404）。见下面“访问统计” |
| `/frontier/?k=<钥匙>` | 钥匙对了就发站长 Cookie，跳回不带钥匙的网址（任一页面后面加都行）；不对就照常显示页面 |
| `/frontier/_access` | 站长的“开放程度”设置页（11-10 加）：只认站长 Cookie，别人 404。见下面“开放程度” |
| `/frontier/_enter` | 只收 POST：“凭口令”档时门页上的口令框提交到这里（11-10 加） |

每期为什么不直接放在 `/frontier/2026-11-09/` 目录里：网页是一页，按 `?date=` 读 `issues/日期/issue.js`；页面里的字体、脚本都写的相对地址（如 `issues/2026-11-09/fonts/…`），换到下一层目录就全错位。跳转一下最省事，`site/` 一行不用改。

## 文件

| 文件 | 作用 |
|---|---|
| `wrangler.toml` | Worker 配置：名字、两条路由、不开 `*.workers.dev`、静态文件目录（占位 `__ASSETS_DIR__`，运行时替换）；访问统计数据库 D1 `frontier-visits`（绑定名 `VISITS`，11-10 加）；没有定时任务；机密变量两个，都不写在这个文件里：`GH_FEEDBACK_TOKEN`（读者反馈用，由 `feedback-setup.yml` 写入）、`STATS_KEY_HASH`（站长钥匙的指纹，由 `stats-setup.yml` 写入） |
| `src/index.js` | 每个请求先过这里：只许 GET/HEAD（例外三个 POST：`/frontier/feedback` 收读者反馈，`/frontier/_enter`、`/frontier/_access` 是开放程度的）；站长钥匙 `?k=`；统计页、设置页的门；`/frontier` 跳 `/frontier/`；开放程度的门；目录给 `index.html`；加三个响应头；定浏览器缓存；音频按 Range 截段（见下）；不在 `/frontier` 下的一律 404 |
| `src/access.js` | 开放程度（11-10 加）：读写档位和访问口令（D1 的 `site_settings` 表）、门页、凭口令进入、站长设置页 |
| `src/visits.js` | 匿名访问统计（11-10 加）：判断要不要记、记哪些字段、写进 D1；顺手清 400 天以前的记录 |
| `src/stats.js` | 站长的统计页 `/frontier/_visits`（SQL 汇总 → 一页 HTML；导出 CSV） |
| `migrations/` | 数据库的表结构：`0001_visits.sql`（访问统计）、`0002_settings.sql`（开放程度，11-10 加）；`run_wrangler.py` 把它和 `src/` 一起复制到运行目录 |
| `tests/worker.test.js`、`package.json` | Worker 的本机测试：`cd cloud/deploy && node --test tests/worker.test.js`（Node 22.13 及以上，不用装任何东西；统计和开放程度的测试用 Node 自带的 SQLite 当假 D1，会打印一行“实验功能”的提示，不影响）。要整份文件一起跑：开放程度加上以后，“统计：不记的”“统计：数据库坏了”两条旧测试默认本实例已经读到过档位（由前面的测试读到），单独挑出来跑会失败 |
| `assemble.py` | 做上线包：往期（往期存档）＋这一期（`测试版/<日期>/10_网页v3/issues/<日期>/`）＋网页外壳（仓库里现在的 `site/v3`、`site/vendor`）→ `<上线包>/frontier/…`；写往期目录 `issues/index.js` 和往期页 `past/index.html`；检查文件数、单个文件大小、不引用外网、noindex |
| `archive.py` | 往期存档：已发布的每一期存在本仓库的 `site-archive` 分支；`pull` 取下来，`push` 存这一期 |
| `run_wrangler.py` | 运行 wrangler 的入口：把本目录复制到仓库以外的运行目录、填上上线包位置；发布前再检查一遍上线包 |
| `tests/test_deploy.py` | `assemble.py`、`archive.py` 的单元测试（存档用本机的假远端，不联网） |

浏览器缓存分两类：网页（html、目录）和往期目录 `issues/index.js` 每次向服务器核对（没变时只回“没变”，很快）；每期的音频、图片、字体缓存 7 天。其余（每期的 `issue.js`、程序 css/js、`vendor/`）10 分钟——文件名不带版本号，缓存太久会“新页面配旧程序”。同一天重新发布、换了音频的话，已经打开过的浏览器最多 7 天内可能还听到旧的。

音频拖动：Cloudflare 的静态文件不认 Range 请求头（浏览器说“只要第几到第几个字节”），总是回整个文件（[官方说明](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/)）。苹果手机的 Safari 放音频要靠它，所以 `.mp3` 这类文件由 Worker 自己截出那一段、回 206。本机测试过各种写法；真机（尤其 iPhone）上能不能拖动，第一次上线后要试一下。

11-09 晚第一次上线后核对出一个本机测不到的问题：线上 `env.ASSETS.fetch` 的回应**不带 Content-Length**（[workers-sdk #8967](https://github.com/cloudflare/workers-sdk/issues/8967)），Worker 拿不到文件大小就放弃截段，带 Range 也回 200 整段。已改成不带长度时把整个文件读进来再截（提交 d191f51），本机测试补了“像线上那样不带长度”的两条用例（旧代码上失败、新代码上通过）。重新发布后核对：11-09 播客、视频旁白、10-31 播客带 `Range: bytes=1000-1999` 都回 206、1000 字节，内容和本机文件逐字节相同；浏览器里点“听这一段 6:56”直接跳到那里接着播。iPhone 真机还没试。

## 读者反馈：POST 例外之一（11-10 加）

除了 GET、HEAD，Worker 只多收三种请求：**POST `/frontier/feedback`**（页面底部“往期 · 反馈”点开的反馈框提交到这里），以及开放程度的 POST `/frontier/_enter`、`/frontier/_access`（见下面“开放程度”）。别的地址的 POST、PUT、DELETE 等照旧回 405。网站不是公开档时，不放行的人提交反馈回 403 `{"ok":false,"error":"网站暂未开放"}`，不转交。

- 校验：`Origin` 必须是 `https://wenlongzhang.com`（否则 403）；只收 `application/json`（否则 415）、不超过 8 KB（否则 413）；期号 `YYYY-MM-DD`、“哪里不对”必填且最多 1000 字、称呼最多 40 字、位置最多 80 字（否则 400，回中英文说明）；蜜罐栏 `website` 有值就当机器人，回 202 但不转交。
- 限流：按 `CF-Connecting-IP`，同一 Worker 实例内存里 10 分钟最多 5 次（否则 429，带 `Retry-After: 600`）。
- 转交：用机密变量 `GH_FEEDBACK_TOKEN` 调 GitHub 接口触发本仓库的 `feedback.yml`（workflow_dispatch，`ref: main`），成功回 202 `{"ok":true}`；GitHub 回错或连不上回 502“稍后再试”；没设机密变量回 503“反馈功能还没设置好”。
- 日志只记状态码，不记令牌、不记反馈内容。回应都是 JSON、`Cache-Control: no-store`，照样带三个公共响应头。
- 机密变量由手动流程“读者反馈设置”（`.github/workflows/feedback-setup.yml`）写入；以后每次 `wrangler deploy` 都不会删它（[官方](https://developers.cloudflare.com/workers/wrangler/configuration/)：“Wrangler will not delete your secrets … unless you run `wrangler secret delete <key>`”）。
- 整条链路、后台在哪看、周六怎么处理、怎么停用：`cloud/feedback/README.md`。

## 访问统计（11-10 加，照期刊网站）

照期刊网站 `wenlongzhang.com/journals` 的那套（期刊监控仓库 `site/deploy/` 的 `src/visits.js`、`src/stats.js`、`README.md`“访问统计”一节）。不用任何第三方统计工具，数据只在你自己的 Cloudflare 账号里。

**记什么**：三种，每次一行。

| 类型 | 什么时候记 |
|---|---|
| 打开页面 | GET `/frontier/`（带不带 `?date=` 都算）、`/frontier/past/`，状态 200 或 304（304 是“页面没变、浏览器用自己存的那份”，回头客再打开时多半是它，也算一次）。期号从 `?date=` 取；不带期号（或期号不存在）的记成当时的最新一期（Worker 读往期目录 `issues/index.js` 得知是哪天），另标“没带期号” |
| 开始听 | GET 某期的 `audio/podcast.mp3`，而且是“从头要”：不带 Range，或 Range 从第 0 个字节开始。Safari 会先要头 2 个字节（`bytes=0-1`）探一下，这一下不算；拖动进度条（从中间要）不算 |
| 开始看 | 同上，换成视频旁白 `audio/video3.mp3` |

“开始听”“开始看”同一访客同一期 30 分钟内只记一次（Safari 探完还会再从头要一次；切换中英文时视频会重新读旁白）。

每行的字段：

| 字段 | 内容 |
|---|---|
| 时间 | UTC 时间戳；另存英国时间的日期，按天统计用 |
| 类型、期号 | 打开页面／开始听／开始看；期号 `YYYY-MM-DD`（往期目录记空）；“没带期号”标记 |
| 页面 | 路径；只留 `?date=`，其余参数（钥匙 `k`、`theme`、`static` 等）一律去掉 |
| 国家／地区、地区、城市 | Cloudflare 按网络推断（`request.cf`），不一定准 |
| 设备类型 | 手机／平板／电脑，按浏览器标识粗分（iPad 新系统会自称电脑） |
| 浏览器、系统 | 粗分（微信、QQ、Chrome、Safari、Edge……；iOS、Android、HarmonyOS、Windows、macOS……） |
| 来源网站 | 只存主机名（如 `mp.weixin.qq.com`）；站内跳转记“站内”；没有来源信息记“直接打开” |
| 访客编号 | 随机编号，打开页面时发，存在访客浏览器的 Cookie `fd_vid` 里（一年，只在 `/frontier` 下有效），用来分新访客与回头客；和人没有对应关系。音频请求不发编号，带着就记，没带就记空（没带编号的“开始听”不按访客查重） |
| 是否新访客 | 这次才发编号的记为新访客 |
| 语言 | 浏览器语言（`Accept-Language` 第一项） |

**不记**：IP 地址、完整的浏览器标识、完整的来源网址；数据、程序、字体、图片等别的文件；HEAD 请求；跳转（`/frontier`、`/frontier/2026-11-09/` 这种只跳一下，跳到的那一页才记）；爬虫与自动程序（标识里有 bot、spider、crawler、preview、headless、curl、wget、python 等，或 Cloudflare 认定的已知机器人）；浏览器预取；**站长本人**（带有效站长 Cookie `fd_pass` 的浏览器）。写库在页面和音频返回后于后台进行（`ctx.waitUntil`），失败也不影响页面和音频。读者反馈（POST `/frontier/feedback`）不进统计。

**“开始看”偏多，要知道**：视频播放器滚到附近才加载，加载时网页（`site/v3/video3.js`）设的是 `preload = 'metadata'`，浏览器会先从头读一小段旁白，**没按播放也会算一次“开始看”**。播客（`site/v3/app.js`）设的是 `preload = 'none'`，按了播放才读，“开始听”基本就是按了播放。要让“开始看”准确，得改网页（比如把 video3.js 的 preload 改成 `'none'`，或按播放时另发一个记录），这次没动 `site/`。另外，同一台设备 7 天内再听同一期，浏览器可能直接用自己存的那份、不来要文件，就不会再记。iPhone 上 Safari 对 preload 的实际做法待核。

**统计页**：https://wenlongzhang.com/frontier/_visits 。只有带有效站长 Cookie（`fd_pass`，值等于钥匙指纹 `STATS_KEY_HASH`）的浏览器能看，其他人看到的和普通“没有这个页面”一样（404，不暴露这一页存在）。

- 内容：今天／近 7 天／近 30 天的打开次数、访客数、新访客数和开始听、开始看次数；每天打开次数与访客数的柱状图（手指按住或鼠标停在柱子上看那天的开始听、开始看）；**每期的打开、开始听、开始看**（次数和人数，最新一期在最前）；最常看的期号、最常打开的页面、来源网站、国家／地区、城市、设备、浏览器、系统、语言排行；最近 100 次明细（英国时间，可切北京时间）；时间范围 7／30／90 天／全部；“导出 CSV”（UTF-8 带 BOM，Excel 直接打开）。按天统计一律按英国时间的日期。
- 页面是 Worker 直接生成的一页：样式写在页面里，亮暗配色跟随系统，手机能看，不引用任何外网资源。

**钥匙**：网站只存钥匙的指纹（SHA-256，64 位十六进制），叫 `STATS_KEY_HASH`，是 Worker 的机密变量。钥匙本身不进仓库、不进 GitHub、不进 Cloudflare，只在你手里。

- 打开 `https://wenlongzhang.com/frontier/?k=<钥匙>`：指纹对上就发站长 Cookie（一年），再跳回不带钥匙的网址。每台要看统计的设备（电脑、手机）各打开一次就行。浏览器历史里会留一条带钥匙的网址，介意的话在历史记录里删掉这一条。
- 钥匙不对：照常显示页面，不提示。**指纹没设时**：统计照记，统计页一律 404。
- 可以**沿用期刊网站那把钥匙**（记得它的话），也可以**新设一把**；两种做法下面的命令一样，只是第 1 步不同。沿用的话，两个网站的指纹相同，但 Cookie 分开存（`/journals` 和 `/frontier` 各一张），所以在 `/frontier/?k=` 也要打开一次。

**设钥匙：你在 Mac 终端里做**（钥匙不显示在屏幕上、不写进任何文件、不进命令历史；`printf` 是终端自带的命令，值不会出现在进程列表里）。要先把本分支合进 `main`，第 4 步的流程才能运行。

1. 准备钥匙，二选一：
   - 沿用期刊网站那把：直接到第 2 步，粘贴它。
   - 新设一把：运行下面这行，生成一把随机钥匙（32 个字符）直接放进剪贴板，屏幕上不显示；先把它粘进你的密码管理器存好，再做第 2 步。
     ```bash
     openssl rand -hex 16 | tr -d '\n' | pbcopy
     ```
2. 把钥匙读进这个终端窗口（粘贴后回车；屏幕上什么都不显示是正常的）：
   ```zsh
   read -rs "K?粘贴钥匙后回车（不显示）："; echo; echo "读到 ${#K} 个字符"
   ```
   （Mac 终端默认是 zsh；用 bash 的话这一行换成 `read -rsp "粘贴钥匙后回车（不显示）：" K; echo; echo "读到 ${#K} 个字符"`。）字符数是 0 就是没粘上，重做这一步。
3. 本机算指纹，直接交给 GitHub（只传指纹，不传钥匙），然后把钥匙从这个窗口里清掉：
   ```bash
   printf '%s' "$K" | shasum -a 256 | cut -d' ' -f1 | tr -d '\n' | gh secret set STATS_KEY_HASH -R dylan-zhang-wl/frontier-daily
   unset K
   ```
4. 把指纹写进网站 Worker（手动流程“访问统计设置”），等它跑完看结果：
   ```bash
   gh workflow run stats-setup.yml -R dylan-zhang-wl/frontier-daily -f action=put
   sleep 10; gh run watch -R dylan-zhang-wl/frontier-daily $(gh run list -R dylan-zhang-wl/frontier-daily --workflow stats-setup.yml --limit 1 --json databaseId --jq '.[0].databaseId')
   ```
   流程最后一步会说统计页“能打开”还是“还打不开”：还打不开多半是网站还是没有统计的旧代码，等下一次发布（每天出刊或手动放行）后再跑一次 `-f action=check`。
5. 在每台要看统计的设备上打开一次 `https://wenlongzhang.com/frontier/?k=<钥匙>`（从密码管理器复制钥匙），再打开 https://wenlongzhang.com/frontier/_visits 。

换钥匙：重做第 1–5 步（第 1 步选“新设一把”）。旧钥匙和各设备上的旧站长 Cookie 随之失效。不想要统计页、只留记录：`gh secret delete STATS_KEY_HASH -R dylan-zhang-wl/frontier-daily`，并在 Cloudflare 网页 → Workers & Pages → `frontier-daily` → Settings → Variables and Secrets 删掉同名机密变量（之后统计页一律 404）。

**数据在哪**：Cloudflare D1 数据库 `frontier-visits`（免费版，11-10 建在西欧 WEUR，编号写在 `wrangler.toml`，编号不是密钥），表 `visits`。Cloudflare 网页 → Storage & Databases → D1 → frontier-visits 也能看。记录保存 400 天：**不用定时任务**（账号里的定时已经用了 4 个、上限 5 个），改成每写进第 1000、2000……条时顺手删一次 400 天以前的，站长打开统计页时也删一次；访问少的时候，过期的记录可能多留几周再删。

**常用命令**（在仓库根目录，本机 wrangler 已登录；11-10 用 `wrangler whoami` 核对过）：

```bash
python3 cloud/deploy/run_wrangler.py d1 migrations apply frontier-visits --remote     # 建表（11-10 已做；以后加新迁移文件时再运行）
python3 cloud/deploy/run_wrangler.py d1 execute frontier-visits --remote --command "SELECT COUNT(*) FROM visits"   # 只读看条数
python3 cloud/deploy/run_wrangler.py d1 execute frontier-visits --remote --command "DELETE FROM visits WHERE day < '2026-12-01'"   # 删某天以前的（不可恢复，先导出 CSV）
```

**发布**：每天的发布（`frontier-daily.yml`、`release.yml` 里的 `run_wrangler.py ... deploy`）照旧，`wrangler.toml` 里的 D1 绑定会跟着带上去，流程文件不用改。发布用的令牌（`CLOUDFLARE_API_TOKEN`，Edit Cloudflare Workers 模板）不用加 D1 权限：期刊网站 10-17 实测，这种令牌在 Actions 里发布绑定了 D1 的 Worker 能成功；只有在 Actions 里建表、查数据库才要加。本站第一次带绑定发布后看一眼发布那一步成没成；万一报错并提到 D1：Cloudflare 网页 → My Profile → API Tokens → “frontier-daily 发布”右边 ⋯ → Edit → + Add more → Account / D1 / Edit → Continue to summary → Update token（令牌值不变，GitHub Secrets 不用改）。

**只停用统计、不停用网站**：把 `wrangler.toml` 的 `[[d1_databases]]` 一节删掉再发布，页面和音频照常，统计不再记录，也不再发访客 Cookie（统计页显示“还没有连上统计数据库”）。数据库留着不动，想恢复把那一节加回来再发布。**注意（11-10 起）**：开放程度也存在这个数据库里，删掉这一节后网站一律按“公开”处理，设置页显示“没连上数据库，开放设置用不了”。

**本机模拟**（不连线上，不用真钥匙）：在一个临时运行目录建本地表，写一个测试用的指纹，再起本机服务：

```bash
R=~/.cache/frontier-daily-cloud/stats-dev; P=<上线包目录>
python3 cloud/deploy/run_wrangler.py --assets $P --run-dir $R d1 migrations apply frontier-visits --local --persist-to $R/state
printf 'STATS_KEY_HASH="%s"\n' "$(printf '%s' test-key-local | shasum -a 256 | cut -d' ' -f1)" > $R/.dev.vars    # 测试钥匙 test-key-local，不是真钥匙
python3 cloud/deploy/run_wrangler.py --assets $P --run-dir $R dev --local --ip 127.0.0.1 --port 8791 --persist-to $R/state
```

浏览器打开 `http://127.0.0.1:8791/frontier/?k=test-key-local`。已知问题（11-10 发现，和统计无关）：本机 `wrangler dev` 会报“Incorrect type for map entry 'FEEDBACK_ORIGIN'”起不来——本机的运行环境把 `src/index.js` 导出的每个常量都当入口检查（读者反馈那几行，11-09 加）；线上不受影响（反馈在线上能用）。临时绕过：在运行目录里加一个文件 `src/_dev_entry.js`，内容 `export { default } from './index.js';`，把运行目录里 `wrangler.toml` 的 `main` 改指它，再在运行目录里直接运行 wrangler 的 `dev` 那一串（`run_wrangler.py` 每次会重写运行目录）。11-10 就是这样在本机核对的。

## 开放程度（11-10 加）

**是什么**：你（站长）在一个只有你能打开的设置页里切三档，决定别人打开网站时看到什么。你自己（带站长 Cookie 的浏览器）任何一档都照常看全部内容。程序在 `src/access.js`，测试在 `tests/worker.test.js` 最后一节。

| 档位 | 别人打开任何页面（首页、往期、某一期、音频、图片……）看到的 |
|---|---|
| **公开**（默认） | 和以前完全一样：有链接就能看 |
| **凭口令** | 先看到“这个网站目前只对部分人开放”（英文 “This site is currently open to selected visitors only.”）和一个口令框、“进入”按钮——别人看得到的门页上不出现说明这一档给谁用的字眼（11-10 用户定）。输对一次，这台设备 180 天内不用再输；你改了口令以后，所有凭口令进来的人都要用新口令重输一次 |
| **只有我** | 只看到“网站在测试中，暂时没有开放”，没有输入框 |

被挡下时不管要的是网页、数据、图片还是音频，回的都是这一页（403，不缓存），程序不去取文件；读者反馈也收不进来。门页、输口令、设置页都不计入访问统计；凭口令进来的人进来以后的访问照常记，你自己的照旧不记。门页不提示站长钥匙、不暴露设置页。纯跳转（`/frontier` → `/frontier/`、`/frontier/2026-11-09/` → `?date=`）照旧先跳，跳到的那一页再过门。

**状态存在哪**：Cloudflare D1 数据库 `frontier-visits`（和访问统计同一个）的 `site_settings` 表，两行：`access_mode`（public／family／owner）、`family_pw`（访问口令的“随机盐:SHA-256(盐+口令)”，**不存口令本身**，设置页也绝不显示口令）。**每天自动出刊重新发布网站不会把它改回去**：发布换的是程序和网页文件，数据库里的数据不动。表不存在或还没设过，网站按“公开”处理，和加这个功能以前一模一样。

**生效多快**：每个 Worker 实例把档位在内存里存 15 秒。你在设置页改了，最多 15 秒内对所有人生效。

**你怎么操作（手机、电脑都一样）**：

1. 这台设备第一次用：打开 `https://wenlongzhang.com/frontier/?k=<你的钥匙>`（钥匙就是看访问统计那把，从密码管理器复制）。它会跳回首页、地址栏里不再有钥匙，这台设备就记住你是站长了（一年）。已经这样打开过、能看统计页的设备，跳过这一步。
2. 打开 **https://wenlongzhang.com/frontier/_access** （也可以在统计页 `/frontier/_visits` 顶部点“开放程度设置”）。页面上写着“现在”是哪一档、上次改动的时间（英国时间）。
3. 想只给知道口令的人看：
   1. 先在“访问口令”一栏输两遍新口令（4–64 个字，首尾空格不算），点“设新口令”。顶部显示“访问口令已更新”。
   2. 再点大按钮“凭口令”。顶部显示“已改成‘凭口令’”。（还没设口令时点“凭口令”不会生效，会提示先设口令。）
   3. 把口令告诉你想给看的人。他们打开网址 → 看到口令框 → 输口令 → 点“进入”。
4. 想暂时谁都不给看：点“只有我”。想恢复成谁都能看：点“公开”。
5. 换口令：再设一次新口令就行，旧口令和所有设备上的“已输过”一起失效，大家要用新口令重输。

**怎么停用**：设置页点“公开”就和以前完全一样（访问口令留着不碍事）。要连设置页一起去掉，只能把代码退回加这个功能以前的提交再发布（数据库里那两行留着也不影响）。

**线上的表**：不用专门建——你第一次在设置页设口令或切档时，程序自己先建表（`CREATE TABLE IF NOT EXISTS`）。想先建好也可以（要你同意再做，会改线上数据库）：`python3 cloud/deploy/run_wrangler.py d1 migrations apply frontier-visits --remote`（执行 `migrations/0002_settings.sql`；程序已经建过表时它什么都不改）。只读看现在是哪一档：`python3 cloud/deploy/run_wrangler.py d1 execute frontier-visits --remote --command "SELECT key, updated_ts FROM site_settings"`（不显示口令记录的值）。

**已知限制**（要知道）：

- 这是“别让拿到链接的人随手打开”，不是银行级的门：口令 Cookie 被人从手机里拷走也能用；输错次数的限制（同一 IP 10 分钟 10 次）只记在单个实例的内存里，实例会换、有好几个，挡不住有心人慢慢试——口令别用生日、别太短。
- 已经打开过的设备上，浏览器自己存的东西还在：音频、图片、字体最多 7 天，每期数据、程序 10 分钟；切到“只有我”不会把它们从别人手机里删掉，已经下载、转发出去的文件也收不回。切到非公开档以后，放行的回应都标成 `private`（只让访客自己的浏览器存，中间的共享缓存不存）；切换以前公开档时可能被公司、运营商的代理存过的音频图片，最多 7 天内那里还可能有。
- 同一个读者，换一个浏览器（比如 Safari 和微信里打开）、清了 Cookie、用无痕模式，都要重输一次。微信内置浏览器能不能把 Cookie 存住 180 天，没在真机上试过（待核）；iPhone Safari 真机也还没试。
- 数据库出故障时：读到过档位的实例照旧用上次读到的；新开的实例读不到，就对你以外的所有人显示“网站暂时打不开，请过一会儿再刷新”（503，公开档时也是），宁可挡住也不放出去；你照常能看。
- 统计页、设置页只认站长 Cookie，口令 Cookie 打不开。
- 手动流程“访问统计设置”“读者反馈设置”的线上检查：首页 200（公开）或 403 且是门页（非公开）都算正常，会打印“网站当前不是公开档”；非公开档时匿名反馈被挡下，那一步只能确认“网站暂未开放”，核对不了反馈令牌，想核对先切回公开再跑 `check`。
- 设置页的提交要求来源（Origin）是 `https://wenlongzhang.com`：本机 `wrangler dev`（http://127.0.0.1）上用浏览器点按钮会回 403，本机试用 curl 带上 `Origin: https://wenlongzhang.com`。

**本机试过**（11-10，本机 `wrangler dev --local`，端口 8791，假的上线包和本机专用钥匙 test-key-local、假口令）：先删掉本地的 `site_settings` 表，再走一遍公开 → 只有我（匿名首页、mp3 带 Range、HEAD、反馈都 403，站长 200／206）→ 没设口令切凭口令被拦 → 设口令、切凭口令（匿名看到口令框）→ 输错 403“口令不对”→ 输对 303 拿到口令 Cookie、首页 200、mp3 206 → 改口令后旧 Cookie 403 → 切回公开 200；表由程序自己建出来，口令记录是“盐:指纹”。做法同上面“本机模拟”（同样要 `_dev_entry.js` 的临时绕过）。

## 往期从哪来（存放）

Cloudflare 每发布一次就是一个新版本，新版本只有这次上传清单里的文件（[官方说明](https://developers.cloudflare.com/workers/static-assets/direct-upload/)：清单 "is used to track assets associated with each Worker version"）。没变的文件按内容指纹认出来，不会重复上传，但清单里必须有。云端每次是空机器，所以每次发布前都要把全部往期拿回来。

现在的做法（试运行用）：**发布成功的每一期，网页文件提交到本仓库的 `site-archive` 分支**（只放 `issues/<日期>/`，每期约 10 MB，九成是播客 mp3）。发布前 `archive.py pull` 取下来，`assemble.py` 和这一期拼成上线包，发布成功后 `archive.py push` 把这一期存进去。主分支不受影响（`actions/checkout` 默认只取主分支），用的是流程自带的推送权限，不另用令牌。

11-09 晚第一次上线：10-31～11-08 八期（mini 试运行那周的成品，本机 `本机资料/归档/mini试运行_1031-1109/`）先在本机一个临时浅克隆里用 `archive.py push` 补进 `site-archive`（不在 iCloud 那份仓库里做：`archive.py` 用 `git fetch --depth 1`，会把完整仓库变浅）；11-09 再由"手动放行"从云端正式运行 42594242663 的产物发布并存入。本机推一期约 10 MB 时 GitHub 回过 HTTP 400（`RPC failed`，最后一行却是 `Everything up-to-date`），`archive.py` 已改成推送时临时加大缓冲、出错写全最后几行。

三种做法比过：

| | 提交回仓库（选这个） | Actions 缓存 | R2 |
|---|---|---|---|
| 会不会丢 | 不会，有历史 | 会：7 天没用就删；整个仓库 10 GB，和模型缓存（3–4 GB）共用，满了删最旧的（[官方](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)）。一丢，下次发布网站上的往期就全没了 | 不会 |
| 要你做什么 | 什么都不用 | 什么都不用 | 开通 R2（官方写要“完成结账流程”加订阅，[官方](https://developers.cloudflare.com/r2/get-started/)；要不要绑付款方式官方页没写，第三方说要，待核）；令牌加 R2 权限 |
| 免费额度 | 仓库建议 1 GB 以内、最好别过 5 GB；单个文件超过 100 MiB 推不上去（[官方](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)） | 10 GB | 每月 10 GB 存储、100 万次写、1000 万次读，下载不收钱（[官方](https://developers.cloudflare.com/r2/pricing/)） |
| 撑多久 | 每期约 10 MB，一个月约 300 MB，三个月左右到 1 GB | — | 约 1000 期 |
| 别的 | 公开仓库不能用（内容会公开）| 缓存内容不能改，每天要换新名字 | 音频原生支持 Range；往期不用每次都带；不受 Workers 每版 2 万个文件的限制 |

Workers 静态文件的上限（免费档）：每个版本最多 20,000 个文件，单个文件最多 25 MiB（[官方](https://developers.cloudflare.com/workers/platform/limits/)）。现在每期约 30–45 个文件、最大的播客约 7 MB，远在线内。`run_worker_first = true` 时每个请求都算一次 Worker 调用，免费档每天 10 万次，超了回 429（[官方](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/)）；一页约 40 个文件，自己看够用。

### 以后换成 R2（试运行稳了、换公开仓库之前）

1. Cloudflare 网页 → R2 → 开通（按页面提示），建一个桶，比如 `frontier-daily-media`；令牌加一项 Account · Workers R2 Storage · Edit。
2. `wrangler.toml` 加 `[[r2_buckets]]`（binding `MEDIA`）；`src/index.js` 里 `/frontier/issues/<日期>/` 下的音频、图片、字体改从 `env.MEDIA.get(…, { range })` 读（R2 自己支持 Range），找不到再退回静态文件。
3. 发布时只把这一期的媒体传进 R2（`wrangler r2 object put`），上线包里只留网页外壳和每期的小文件；`archive.py` 换成从 R2 列往期。
4. `site-archive` 分支不带进公开仓库。

## 本机（不发布，可重复）

```bash
cd cloud/deploy && node --test tests/worker.test.js && cd ../..          # Worker 测试
python3 -m unittest discover -s cloud/deploy/tests -v                    # 上线包、往期存档测试
python3 cloud/deploy/assemble.py --issue 测试版/2026-11-08 --out /tmp/fd-pkg      # 做上线包（输出目录要不存在或是空的）
python3 cloud/deploy/run_wrangler.py --assets /tmp/fd-pkg deploy --dry-run --outdir /tmp/fd-dry   # 只打包检查，不发布、不用令牌
```

## 首次上线：要你做的只有一件事

在 Cloudflare 建一个令牌，填进新仓库的 Secrets。值只由你本人粘贴，不经过我。

1. Cloudflare 网页 → 右上角头像 → My Profile → API Tokens → Create Token → 模板 **Edit Cloudflare Workers** → Use template。
   - Account Resources：Include · *wenlongzhang.com 所在的那个账号*
   - Zone Resources：Include · Specific zone · *wenlongzhang.com*
   - Continue to summary → Create Token → 复制令牌（只显示一次）。
   - 想收窄权限，可以改用 Custom token，只给三项：Account · **Workers Scripts · Edit**；Account · **Account Settings · Read**；Zone（wenlongzhang.com）· **Workers Routes · Edit**（和期刊网站一样）。
   - 建议单独建一个，名字写 `frontier-daily Actions`，以后要停可以单独作废，不影响期刊网站。
2. 在 Mac 的终端里运行（会提示你粘贴，粘贴时屏幕上不显示）：
   ```bash
   gh secret set CLOUDFLARE_API_TOKEN -R dylan-zhang-wl/frontier-daily
   ```

账号 ID 不是密钥，但不写进公开仓库：编号记在私有仓库的 `cloud/密钥与重置手册.md`，放在私有仓库的 Secret `CLOUDFLARE_ACCOUNT_ID` 里，发布流程从那里取（`run_wrangler.py` 只读环境变量 `CLOUDFLARE_ACCOUNT_ID`）。本机运行 `run_wrangler.py` 时先 `export CLOUDFLARE_ACCOUNT_ID=<编号>`。

令牌填好后，发布还要打开开关（试跑几天、你看过再开；11-09 19:23 UTC 已打开）：
```bash
gh variable set SITE_DEPLOY_ENABLED -R dylan-zhang-wl/frontier-daily --body true
```
不设或设成别的值，流程只打包、跑 `wrangler deploy --dry-run` 检查，不发布、不存往期。

### 第一次发布后检查

```bash
curl -sI https://wenlongzhang.com/frontier | head -3                                  # 301 → /frontier/
curl -sI https://wenlongzhang.com/frontier/ | grep -i -E "x-robots|cache-control"    # noindex, nofollow；no-cache
curl -s -o /dev/null -w "%{http_code}\n" https://wenlongzhang.com/                    # 知识库照常
curl -s -o /dev/null -w "%{http_code}\n" https://wenlongzhang.com/memory/             # 另一个网站照常
curl -s -o /dev/null -w "%{http_code}\n" https://wenlongzhang.com/journals/           # 期刊网站照常
```
再用手机（最好也用国内网络）打开最新一期和往期页，播客拖动一下进度条。

## 回退、暂停、下线

- **回到上一个版本**：`python3 cloud/deploy/run_wrangler.py rollback`（只影响本 Worker）。看历史：`run_wrangler.py deployments list`。
- **暂停自动发布**：仓库变量 `SITE_DEPLOY_ENABLED` 改成 `false`（或删掉）。
- **让网站下线**：Cloudflare 网页 → Workers & Pages → `frontier-daily` → Settings → Domains & Routes，删掉两条 `/frontier` 路由（之后 `/frontier` 交回知识库处理）；或 `run_wrangler.py delete` 删掉整个 Worker。都不影响知识库和同一域名下的另外两个网站。
