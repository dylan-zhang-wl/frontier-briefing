# frontier-daily：Horizon 与 AIHOT 代码评估报告

- 写于 2026-10-30（系统时钟）。只读评估：两个仓库各浅克隆一份，只读代码和文档，没有安装依赖，没有运行仓库里的任何脚本。
- 所核版本：Horizon `cdd95f8`（2026-10-30），AIHOT `5b2aaaa`（2026-10-30）。下文行号都按这两个版本。上游以后改动，行号会漂移。
- 本地副本：`<当时的临时目录，已清>/code-eval/horizon/`、`.../code-eval/aihot/`
- 对照的方案：`文档/方案/历史/方案讨论稿.md` 第二、五、八、九节。

**依据标记**
- 【代码】读代码确认。
- 【文档】只见 README 或项目文档的说法，没在代码里核实。
- 【注释】作者写在代码注释里的实测数字，我们无法复核。
- 【推断】我根据代码作的判断，需要实测才能确认。

---

## 〇、结论先行

**建议走 B：主干自己写（Python + uv + GitHub Actions + Cloudflare），Horizon 只拆零件；AIHOT 的规则和提示词按需移植进来。两边都保留 MIT 署名。**

三条最关键的理由：

1. **核心单位对不上。** Horizon 的处理单位是"单篇条目"：每条打一个分，再写几段自由文字（`src/models.py:58-118`）。我们的核心单位是"事件卡"：多来源归并成一件事，带事实、数字、原文引文和署名观点。事件卡、数字核对、口播稿、配音、Cloudflare 发布、反馈回流，在 Horizon 里都没有，fork（复制一份仓库到自己名下再改）后照样要新写。Horizon 真正省事的部分是采集和模型客户端，按 B 路线直接复制这几个文件就能拿到。按 2.9 节的粗估，A 反而多 3–4 天。
2. **上游的方向和我们相反。** Horizon 作者明确不想让程序"有状态"，也就是不保存跨天的记忆：有人提议用 SQLite 存抓取结果，作者答"一旦有状态以后维护成本会比较高"（issue #75，后关闭未做）；断点续跑的提案也被婉拒（#124）。我们的设计离不开状态：跨天的事件池、往期事件卡、你的反馈。fork 以后注定长期分叉，上游更新合不进来，fork 的主要好处就没了。仓库里约一半代码我们用不上，还得一直背着：MCP 服务、配置向导、微信、邮件、Webhook、X、Reddit、Telegram、OpenBB、ChatGPT 登录。
3. **该补的质量机制，AIHOT 已经做好。** Horizon 每条只打一次分，信源不分级，同题去重只看标题、标签和一句话摘要（作者在 #180 里也承认会漏），也没有任何数字或引文核对。AIHOT 补齐了这些：同一标准独立打两次分，按信源分级设门槛；结构化抽事实时要求原文逐字引文，程序再回原文核对；四种关系判断同一事件，相似度不高时换一家模型复核；热度按独立参与方算，24 小时减半；改写前后数字必须一致；周报导语里的数字和专名必须在条目里查得到。这些规则与语言无关，移植到 Python 不难。

---

## 一、几个术语（第一次出现时的说明汇总）

| 术语 | 一句话解释 |
|---|---|
| 仓库 / 上游 | 仓库是放代码的项目文件夹，带完整修改历史；上游指原作者那份仓库 |
| fork | 把别人的仓库复制一份到自己名下再改 |
| MIT 许可 | 可以复制、修改、商用，条件是保留原作者的版权声明和许可全文 |
| 提示词（prompt） | 发给大模型的指令文字 |
| OpenAI 兼容接口 | 按 OpenAI 的请求格式提供服务的模型接口，填一个地址（base_url）和一把钥匙（key）就能接 |
| JSON / JSON 模式 | JSON 是程序之间交换结构化数据的文本格式；JSON 模式是请模型保证只输出 JSON |
| 温度（temperature） | 模型回答的随机程度。0 表示同一问题每次几乎答得一样 |
| 向量 / 余弦相似度 | 把一段文字换成一串数字，意思相近的文字数字也相近；余弦相似度衡量两串数字有多接近，1 表示几乎相同 |
| 召回 | 先粗筛出"可能相关"的候选，再交给模型细判 |
| BM25 | 搜索引擎常用的关键词检索打分方法 |
| 半衰期 | 权重每过这么长时间减半；24 小时半衰期就是一天前的讨论只算一半 |
| 依赖 | 项目运行前要先装好的第三方程序包 |
| 自动化测试 / CI | 测试是程序自查代码是否按预期工作的小脚本；CI 是每次改代码都自动跑这些检查 |
| GitHub Pages / Jekyll | GitHub 自带的静态网站服务，以及它用来把 Markdown 变成网页的工具 |

---

## 二、Horizon（Thysrael/Horizon）细读

### 2.1 架构与模块【代码】

| 目录 / 文件 | 行数 | 做什么 |
|---|---:|---|
| `src/main.py` | 121 | 命令行入口：读 `.env`、载入配置、启动总调度 |
| `src/orchestrator.py` | 1151 | 总调度：一次运行的全部步骤都在这里串起来 |
| `src/models.py` | 623 | 数据结构与配置格式（条目、分析结果、各类信源配置） |
| `src/scrapers/` | 2875 | 采集：RSS、Hacker News、GitHub、Reddit、Telegram、X、OpenBB、OSS Insight、GDELT、Google News |
| `src/extractors/` | 170 | 正文抽取（trafilatura 本地抽取；Firecrawl 付费服务） |
| `src/ai/` | 3204 | 模型客户端、分类、打分、补写（enrich）、汇总渲染、提示词 |
| `src/processing/` | 519 | profile 载入、正文截取、往期检索（BM25）、联网搜索工具 |
| `src/storage/manager.py` | 161 | 读配置（支持 `${环境变量}`）、存每日 Markdown |
| `src/services/` | 2003 | 邮件、Webhook（飞书、Slack 等）、微信推送 |
| `src/mcp/` | 1769 | MCP 服务：让 AI 助手分阶段调用流水线，每阶段结果存 JSON |
| `src/setup/` | 1155 | 交互式配置向导 |
| `profiles/<id>/` | 共 279 | 4 个内置 profile，每个由 `profile.json` 加三份 Markdown 提示词组成 |

核心流水线（总调度、模型、分析、补写、渲染、检索、存储）约 5,000 行；`src/` 合计 14,036 行。

### 2.2 一天一次运行的流程【代码】

入口 `src/main.py:39-117` → `HorizonOrchestrator.run()`（`src/orchestrator.py:241-429`）：

1. **定时间窗**：默认抓过去 24 小时（`orchestrator.py:431-437`，配置项 `collection.time_window_hours`）。
2. **并发采集**：各类信源并发（`orchestrator.py:439-522`）。注意 RSS 内部是逐个源顺序抓的（`src/scrapers/rss.py:51-62`），源多了会慢。每个源的成功、失败和条数记进 `FetchReport`（`orchestrator.py:110-175`）；全部失败时整次运行报错（`orchestrator.py:275-276`）。
3. **同网址合并**：网址规范化（去掉 `utm_` 等追踪参数）后，同一网址只留内容最长的一份，其余来源的内容拼进去（`orchestrator.py:43-84`、`594-647`）。
4. **AI 分析**：每条先定 profile（信源指定了就直接用，否则让模型选），再按该 profile 的评分标准打 0–10 分，同时给理由、一句话摘要和标签（`src/ai/analyzer.py:88-182`）。回答不合格式时修一次（`analyzer.py:154-165`）。
5. **筛选**：按 profile 的分数线过滤（`orchestrator.py:896-911`）→ 同 profile 内用一次模型调用做"同题去重"（`orchestrator.py:649-770`）→ 分类配额与总数上限（`orchestrator.py:913-1033`）。
6. **补写**（第二轮 AI）：按 profile 定义的段落（摘要、背景、影响、社区讨论）逐条写，可调用"往期检索"和"联网搜索"两个工具（`src/ai/enricher.py:222-320`）。
7. **渲染与发布**：每种语言生成一份 Markdown，由程序拼版、不调模型（`src/ai/summarizer.py:210-274`）；存到 `data/summaries/`，再复制一份加 Jekyll 头信息到 `docs/_posts/` 给 GitHub Pages（`orchestrator.py:316-369`）；按配置发邮件、Webhook、微信（`orchestrator.py:371-391`）。

**定时运行**：仓库自带的 GitHub Actions 模板默认禁用（`.github/workflows/daily-summary.yml.disabled`），启用后每天 UTC 23:00 跑，然后把 `docs/` 推到 `gh-pages` 分支（第 51-59 行）。【推断】作者自己的演示站目前像是在服务器上用 cron 跑 `scripts/daily-run.sh`：这个脚本 10-23 还在修，也是推 `gh-pages`。

### 2.3 配置格式【代码】

一个 JSON 文件 `data/config.json`（示例 `data/config.example.json`、`data/config.github.json`），由 `src/models.py:609-623` 的 `Config` 校验，写错字段会直接报错（`extra="forbid"`）。

- **信源**：按类型分组。RSS 每个源写 `name`、`url`、`category`（分类配额用）、`content_extractor`（要不要抓全文）、`profile`（`src/models.py:293-301`）。网址里可以写 `${LWN_KEY}` 这类环境变量，密钥就不用写进文件（`src/storage/manager.py:30-54`）。
- **模型**：`ai.provider`、`model`、`base_url`、`api_key_env`（填环境变量的名字，不填密钥本身）、`temperature`（默认 0.3）、`max_tokens`（默认 4096）、`extra_body`、`languages`（如 `["zh","en"]`）（`src/models.py:193-245`）。
- **profile**：一个文件夹放四个文件（`docs/profiles.md`；载入代码 `src/processing/profiles.py:86-129`）：
  - `profile.json`：输出哪些段落、每段能用哪些工具、输入截取多少字；
  - `match.md`：什么内容归这个 profile；
  - `analysis.md`：0–10 分的评分标准（例：`profiles/tech-news/analysis.md`）；
  - `enrichment.md`：每段怎么写（例：`profiles/tech-news/enrichment.md`）。
  - 分数线写在主配置 `processing.profile_settings.<id>.threshold`，不写在 profile 里（`src/models.py:552-568`）。

### 2.4 存储与输出【代码】

- **只用文件，没有数据库。** 跨天的"记忆"只有两样：`data/summaries/horizon-<日期>-<语言>.md`（往期检索就读这些文件，`src/processing/history.py:58-88`），以及订阅者名单 `data/subscribers.json`。
- 这两样在 `.gitignore` 里都被排除（第 40-50 行）。在 GitHub Actions 上每次都是全新环境，往期检索什么也搜不到，除非自己在运行前把往期文件取回来。【代码＋推断】
- **输出**：Markdown（存 `data/summaries/`）、GitHub Pages（`docs/_posts/`，路径写死在 `orchestrator.py:335`）、邮件、Webhook、微信。没有 HTML 模板、音频和播客订阅源。
- MCP 模式会把每个阶段的条目存成 JSON（`raw` / `scored` / `filtered` / `enriched`，见 `src/mcp/run_store.py:16-21`）。这个"分阶段存档"的做法值得借：我们的"候选池"页面正需要当天全部候选及其得分。

### 2.5 模型调用【代码】

- **客户端**：`src/ai/client.py`。OpenAI 兼容接口用官方 `openai` 包（`AsyncOpenAI`，`client.py:226-377`），另有 Anthropic、Azure、Gemini 和 ChatGPT 账号登录几种。
- **能否换成任意 OpenAI 兼容接口：能。** 配 `"provider": "openai"`、`"base_url": "${MIMO_BASE_URL}"`、`"api_key_env": "MIMO_API_KEY"`、`"model": "..."` 即可（`client.py:253-263`、`276-289`）。`extra_body` 可以带服务商特有参数，比如关闭思考模式（`client.py:373-376`）。它还会自动适应不收 `temperature` 或 `max_tokens` 的模型：第一次被拒后就不再发（`client.py:316-340`）。
- **要注意的三点**：
  1. 除 MiniMax 外，它对所有 OpenAI 兼容服务都强制开 JSON 模式（`client.py:238`、`371-372`）。MiMo 是否支持要实测。【推断】AIHOT 的预设里有 `mimo-v2.6-flash`，写的是 `jsonMode: true` 并关闭思考（`aihot/site/models.ts:38-41`），说明有人这样配过，但我们没验证。
  2. **整次运行只有一个模型**（`orchestrator.py:236-239` 缓存一个客户端，分类、打分、去重、补写共用）。方案里"初筛用 flash、写稿用 pro"要改代码。
  3. 备用模型链（`provider_chain`）里的备选模型名取自内置默认值，不能单独指定（`client.py:680-726`；Anthropic 默认是 `claude-sonnet-5-5`，`src/models.py:138-142`）。
- **提示词在哪里**：分两层。
  - 通用规则写在 Python 字符串里：`src/ai/prompting/common.py`（防编造规则）、`analysis.py`、`classification.py`、`deduplication.py`、`enrichment.py`。
  - 各类内容的口味写在 `profiles/<id>/*.md` 里，改 Markdown 不用碰代码，容易改。
  - 全部是英文提示词。中文输出靠"Write the complete artifact in Simplified Chinese"这一句（`src/ai/prompting/enrichment.py:20-23`）。

### 2.6 打分、去重、分类配额、双语的具体实现【代码】

| 功能 | 关键文件与行号 | 怎么做 | 对我们的意义 |
|---|---|---|---|
| 打分 | `src/ai/analyzer.py:88-182`；`src/ai/prompting/analysis.py:7-45`；`profiles/*/analysis.md` | 每条打一次 0–10 分，附理由、一句话摘要和 3–5 个标签。默认只给模型看正文前 1000 字（`src/processing/profiles.py:19`），而 RSS 正文没去掉 HTML 标签（`rss.py:168-200`），没配全文抽取时信息很少 | 一次打分、看得少；AIHOT 的打分方式更稳 |
| 按内容类型定标准 | `profiles/tech-news/analysis.md` 等 4 个；路由 `src/ai/classifier.py:33-101` | 不同内容类型（新闻、技术博客、财经、AI 创作素材）各有评分标准和分数线 | 思路可借；AIHOT 的"7 类内容 × 五轴权重"更细 |
| 同网址去重 | `orchestrator.py:43-84`、`594-647` | 规范化网址后合并 | **可直接复制** |
| 同题去重 | `orchestrator.py:649-770`；`src/ai/prompting/deduplication.py:3-21` | 过线条目的标题、标签和一句话摘要一次性交给模型，模型回答"哪几条是同一件事"，留分最高的一条。只在当天、同一 profile 内做，不跨天，也不统计热度 | 弱。issue #180 报告漏判（只看一句话摘要）；不如 AIHOT |
| 分类配额 | `orchestrator.py:913-1033`；`src/models.py:544-606` | 按信源配置里写死的 `category`（或按 profile）分组，每组限额，外加总数上限 | 逻辑可借；但分类来自信源而非 AI 判断，要改成按事件的 AI 分类 |
| 双语 | `src/ai/enricher.py:222-253`；`src/ai/localization.py:1-13`；`src/ai/summarizer.py:43-91` | 每种语言单独让模型写一遍（不是翻译）；中文输出再用 OpenCC 做繁转简；中英文之间自动加空格；中英界面词各一套 | 繁转简和加空格可复制；我们只要中文 |
| 往期关联 | `src/processing/history.py:33-168` | 对往期 Markdown 做 BM25 检索，中文按两个字一组切词，最多返回 3 条候选，由模型决定用不用 | 可改造来检索我们的往期事件卡 |
| 联网补背景 | `src/processing/tools.py:26-46` | 用 `ddgs` 包抓 DuckDuckGo 搜索结果（非官方接口） | 在 GitHub 机房的 IP 上可能被限流；我们用 Brave、Exa 等官方接口 |
| 引用核对 | `src/ai/enricher.py:467-502` | 只检查段落引用的编号确实存在，**不检查内容** | 没有数字核对，要新写 |

### 2.7 规模、依赖、测试、活跃度、近期 issue

- **规模**【代码】：`src/` 共 14,036 行 Python，核心约 5,000 行；测试 49 个文件、13,091 行、591 个测试函数。
- **依赖**【代码】：`pyproject.toml` 列了 19 个直接依赖，包括 `openai`、`anthropic`、`google-genai`、`mcp`、`trafilatura`、`ddgs`、`opencc`、`feedparser`、`pydantic` 等；锁文件 `uv.lock` 共 166 个包。用 uv 管理，与我们的习惯一致。
- **测试**【代码】：测试很多，但仓库里没有自动跑测试的 CI，只有部署文档网站的 `deploy-docs.yml`。贡献说明（`CONTRIBUTING.md`）也没写跑测试的要求，只有 `docs/profiles.md:97` 提到一条 pytest 命令。
- **活跃度**（GitHub 接口查询，10-30）：
  - 2026-02-20 建仓，主分支 299 次提交，39 位贡献者；作者 Thysrael 一人 227 次（约 76%），其余多为 1–2 次。
  - 近 26 周每周提交 0–33 次，忽冷忽热：7-26 那周 33 次，10-18 那周 22 次，9-27 和 10-04 两周都是 0。
  - 11.1k 星、1,665 个 fork；当前开着的 issue 2 个。
- **近期 issue 的主要问题**：
  - #188（10-30）：Anthropic 新模型拒收 `temperature`，导致整期为空；当天修复（`cdd95f8`，即本次所核版本）。模型参数兼容是反复出现的问题，还有 #125 GPT-5 的 `max_completion_tokens`、#70 DeepSeek 配置、#96 base_url。
  - #180：同题去重漏判，作者建议改 profile 的摘要写法，没改代码。
  - #186、#98、#89：Reddit 抓取报错或被封，Reddit 一直不稳定。
  - #153：新加的 profile 没被默认处理，演示站两天没更新。
  - #75、#124：存状态和断点续跑的提案未被采纳（见结论理由 2）。

### 2.8 对照我们的设计逐条评估

| 我们的设计 | Horizon 现状 | 判断 | 依据 |
|---|---|---|---|
| 采集 60–100 个源（RSS、HN、GitHub、GDELT），信源每天体检 | 有 RSS、HN、GitHub、GDELT 采集器，每源记录成功或失败 | **能直接用，小改**：RSS 改成并发；没配全文抽取的去掉 HTML；体检加"多久没更新" | `scrapers/*.py`、`orchestrator.py:110-175` |
| 同一事件归并（跨来源、跨天），热度按独立来源算 | 只有同网址合并和当天的同题去重；不算热度 | **新写**（移植 AIHOT 的召回、关系判断和热度） | 2.6 节 |
| 选题：热度、权威、新鲜度、你的兴趣，题材多样 | 单次打分加分类配额 | **要改**：打分换成 AIHOT 的两次打分和信源分级；配额逻辑可借，改按事件分类 | `orchestrator.py:913-1033` |
| 事件卡（事实、关键数字、来源链接、署名观点、为什么重要、往期关联） | 没有。每条只有自由文字段落和标签 | **新写**：结构参考 AIHOT 的 `structure.md`（事实框架、原文引文、适用条件）和 `content-understanding.md`（推荐理由、作者角色） | `src/models.py:58-100` |
| 稿件数字由程序回原文核对 | 没有，只在提示词里写了"不要编造"（`prompting/common.py:8-9`） | **新写**：移植 AIHOT 的引文核对（`analyze.ts:163-189`）、改写前后数字一致检查（`analyze.ts:410-411`）、`grounded()`（`compose.ts:165-174`），再加中文数字和单位的换算 | — |
| 由事件卡派生中文网页稿 | 有中文 Markdown 渲染（程序拼版），以单条为单位，Jekyll 格式 | **要改**：繁转简、加空格、转义函数可复制；版式（头条、要闻、快讯、来源卡、今日一词）新写 | `summarizer.py` |
| 由事件卡派生口播稿 | 没有 | **新写** | — |
| 配音（Gemini TTS、MiMo 备用），分块、转写对稿、统一响度 | 没有 | **新写**（从数字人项目搬） | — |
| 发布到 Cloudflare Worker、R2、D1 | 只会 GitHub Pages（Jekyll）加推送；路径写死 `docs/_posts` | **新写**发布步骤；删掉 gh-pages 部分 | `orchestrator.py:330-369`；workflow 模板 51-59 行 |
| 每天运行数据存 R2，不写回仓库 | 模板把 `docs/` 推到 `gh-pages` 分支，这仍是写进仓库；往期检索依赖本地文件 | **要改**：运行前从 R2 取近 N 天事件索引，运行后上传当天全部阶段产物（可借 MCP 的分阶段 JSON 格式） | `.gitignore:40-50`；`run_store.py` |
| 工作台"有用 / 没用"反馈影响第二天选题 | 没有任何反馈机制；分数线和 profile 都是静态的 | **新写**；AIHOT 也没有，但它的标注样本和评测格式可以用来把反馈变成校准数据（见 3.3） | — |
| 先审后发 | 没有审稿环节，跑完即发 | **新写**：草稿进 R2，你点"发布"后才公开 | — |
| MiMo 为主、Claude 对照，分步选模型 | 能接 MiMo；Claude 已修好 temperature 问题；但全程单模型 | **要改**：给每一步单独指定模型 | `client.py`、`orchestrator.py:236-239` |
| uv + GitHub Actions 每天定时 | 有 uv 和 Actions 模板 | **能直接用**：模板里装 uv、`uv sync`、注入密钥的写法可照抄 | `daily-summary.yml.disabled:16-46` |

### 2.9 三种做法比较与建议

**A：直接 fork Horizon 改造。** 不建议。

- 好处：第一天就有一条能跑通的流水线，配上 MiMo 和中文就能出一份 Markdown 简报；有 591 个测试兜底。
- 代价：我们要动的恰好是它的中段，数据单位、去重、补写、渲染都得重做，测试会大面积失效；前端、音频、发布、反馈全是新写。再加上上游不打算有状态，fork 合不回上游更新，等于背着一半用不上的代码自己维护。

**B：主干自写，按需复制 Horizon 零件，移植 AIHOT 规则。** 建议采用。

- 复制的文件在仓库里放一份 `THIRD_PARTY_NOTICES`，写明出处和两份 MIT 许可全文。
- 以固定版本（`cdd95f8`、`5b2aaaa`）为准复制，不追上游。

**C：其他。** 两种都不建议。

- C1：直接部署 AIHOT 整站做后端。需要 24 小时在线的服务器、PostgreSQL 和 Docker，和"GitHub Actions + Cloudflare、无服务器"的路线冲突，运维和月费都会上升；你也说了不打算整体用。
- C2：把 Horizon 当第三方库引用、只调它的分阶段函数。它还没发布到 PyPI（README 的计划里写着要发），接口随作者重构频繁变化，我们要换的又正是中段。
- 可选：B 路线开工前，本机原样跑一次 Horizon（MiMo、中文、我们的信源），拿一份"开箱即用"的结果做基线，和我们第一期样刊对照。约 0.5 天，不影响主线。

**工作量粗估**：按"熟练开发者全职一天"计；不含你审稿、标注和盲听的时间。由 agent 写代码时编码会快，但调提示词、校准门槛、配音对稿、上线排错都要等真实数据和你的判断，日历时间不会同比缩短。

| 模块（第 1 期：样刊、每天自动跑、"今日""往期"两页） | 零件来源 | B 粗估（天） | A 粗估（天） |
|---|---|---:|---:|
| 项目骨架、配置、运行记录与阶段产物存 R2 | 新写（参考 Horizon 的 FetchReport 和 RunStore） | 1–1.5 | 1（删减模块）+ 1（接 R2，改写死的路径） |
| 采集与信源体检（RSS、HN、GitHub、GDELT、正文抽取、网址去重） | 复制 Horizon，改并发和去 HTML | 1.5–2 | 0.5–1 |
| 模型客户端（MiMo 主、Claude 备、分步选模型、用量记账） | 复制 Horizon `client.py` 改 | 0.5–1 | 0.5–1（要改各调用处） |
| 预筛、两次打分、分级门槛、结构化（事实与原文引文核对） | 移植 AIHOT | 2–3 | 2.5–3.5（要塞进 profile 机制） |
| 归并（召回、关系判断、复核、跨天事件池）与独立来源热度 | 移植 AIHOT | 2–3 | 3–4（要给无状态程序加状态） |
| 事件卡、数字核对、网页稿、口播稿 | 新写，借 AIHOT 写作规则和核对函数 | 3–4 | 3–4 |
| 配音、自动对稿、统一响度 | 从数字人项目搬 | 2–3 | 2–3 |
| 发布：Worker 两页、R2 音频、口令访问 | 新写，借期刊网站 | 2–3 | 2–3 |
| GitHub Actions 定时、密钥、失败告警 | 参考 Horizon 模板 | 0.5–1 | 0.5 |
| 修改或停用现有测试、与上游结构磨合 | — | — | 2–3 |
| **合计** | | **约 15–21** | **约 18–25** |

- 第 1 期如果再压缩成"最小样刊"：不上向量（用文字重合度兜底）、不做复核模型、配音先不自动重录，B 约 9–12 天。
- 第 2 期（候选池、反馈回流、话题追踪、来源管理、费用面板）两条路线差不多，约 6–9 天。
- 方案讨论稿给第 1 期排了 1–2 周，按上表偏紧。建议第 1 期就按"最小样刊"的范围定。

**B 路线的风险**：

- 所有代码归我们自己维护（好在只留要用的部分）。
- TypeScript 改写成 Python 时会有细节差异，比如正则对汉字的处理、宽松解析的默认值。要用 AIHOT 自带的样例文件做对照测试。
- 署名漏写会违反 MIT 条件。

---

## 三、AIHOT（KKKKhazix/AIHOT）：可搬的规则与提示词

### 3.1 一条资料在 AIHOT 里怎么走【代码】

总说明在 `packages/backend/src/editorial/analyze.ts:1-13`，归组在 `packages/backend/src/events/group.ts:1-17`：

1. 收进来；只有标题、没有正文的先等材料，不评分（`analyze.ts:451-454`、`477-480`）。
2. **预筛**：是不是本行业的事。只有 BLOCK 会拦下（`analyze.ts:231-249`、`481-482`）。
3. **结构化**：与打分同时跑（`analyze.ts:484-485`），抽分类、标签、主体公司、资料范围和"本次发生的事实"，事实带原文引文。
4. **两次独立打分**：按信源分级门槛判是否入选（`analyze.ts:268-303`、`456-474`）。
5. **写中文标题和摘要**：入选和接近入选的用"内容理解"提示词，其余用便宜的摘要提示词；用了禁用词就只改那几处，数字必须不变（`analyze.ts:486-494`、`378-413`）。
6. **归组**：召回候选事实 → 四种关系判断，同时判断"相对已精选内容有没有新信息" → 相似度不高时换模型复核 → 写入（`group.ts:267-503`）。
7. **热度、日报、周报月报**：按规则计算和编排，日报不调模型（`events/hot.ts`、`reports/edition.ts`、`reports/compose.ts`）。

### 3.2 逐项说明

> 提示词全部在 `industry/prompts/`，**全是中文**（JSON 字段名用英文）。代码注释是英文。模板只有两种写法：`{{名字}}` 由程序填值，`{{> 文件名}}` 插入另一份提示词；缺值直接报错。提示词版本号等于所用文件内容的哈希（`packages/backend/src/editorial/prompts.ts:15`、`47-72`）。

#### （1）预筛 `industry/prompts/prefilter.md`

- **做什么**：宽松判断"是不是 AI 相关"。PASS 放行，BLOCK 拦下，UNKNOWN 先留着等补材料。要求拿出"确认无关"的正面依据才能 BLOCK，"没提到 AI"不能当依据（第 2-5 行）。
- **输入**：来源、作者、发布时间、标题、引用、正文、材料质量，打包成一个 JSON 字符串（`writing.ts:81-115`；注释说"提示词是按这种形式调出来的"）。
- **输出**：`{"label":"PASS|BLOCK|UNKNOWN","reason":"20字内"}`；温度 0，最多 512 token（`analyze.ts:234-245`）。没有文字证据的 BLOCK 自动改成 UNKNOWN（`analyze.ts:247`）。
- **移植注意**：
  - 它只认 AI。我们的范围是"AI 为主、科技商业为辅"，PASS 条件要加科技和商业，否则不带 AI 的商业新闻会被 BLOCK。
  - 想把多条打包成一次调用省钱，就偏离了它调好的输入形式，要重新评测。

#### （2）两次独立打分 `industry/prompts/selection-score.md` + `industry/selection.ts`

- **做什么**：评估"这条材料代表的事件"对读者今天的注意力价值，输出 0–100 的整数。
  - 模型在心里先归入 7 类之一：模型发布、产品、工具或 Prompt、论文、行业事件、观点、教程（第 22-30 行）。
  - 再打五轴，每轴 0–10：实质份量 sig、信息增量 nov、证据强度 cred、共振面 reson、可用性 act（第 32-38 行）。
  - 按类型加权求和，每行权重和为 10（第 40-52 行）。例如模型发布 3/2/2/2/1，论文 5/3/1/0/1。
  - "必须正常评价"和"必须压住"两张清单给出各轴上限，例如例行小版本 `sig ≤ 3`，营销软文 `sig ≤ 2`（第 58-77 行）。
  - "事件口径校正"一节防止把稿件长短、口吻误当事件价值（第 99-109 行）。
- **输入**：只给发布时间（北京时间）、标题和全文，正文最长 60,000 字（`analyze.ts:89-105`、`writing.ts:16`）。**故意不给信源名称和分级**，提示词也要求不猜（第 13 行）。信源权威只通过门槛起作用。
- **输出**：`{"attentionScore": 整数}`。
- **门槛数字**【代码】：
  - 同一输入调用 2 次（`SCORE_CALLS = 2`，`analyze.ts:54`），两次之和 ≥ 2 × 门槛才入选（`analyze.ts:471-474`）；页面显示平均分向下取整（`analyze.ts:462-465`）。
  - 门槛按信源分级：官方一手 T1 60、官方账号或准官方 T1_5 65、媒体与个人 T2 76；`EXCLUDE_MP` 不参与（`industry/selection.ts:13`）。
  - 平均分高于 `understandFloor = 50` 的未入选资料，也按精选写法写（`selection.ts:18`）。
  - 打分默认温度 0.2，最多 1024 token（`analyze.ts:68`）。作者给 GLM 的打分预设用的是温度 1 加高强度推理（`site/models.ts:15-20`）。两次调用依次发出，以复用服务商的提示词缓存（`analyze.ts:280`）。
- **移植注意**：
  - **两次打分要"独立"，前提是温度大于 0。** 温度为 0 时两次几乎一样，等于白付一次钱。先在样本上看 MiMo 两次分数的差异，差异很小就考虑只打一次，或换成开推理、温度 1。
  - 五轴是"心里算"，不输出过程。不开思考模式的模型可能算不好，所以打分这一步建议用 MiMo pro 并开思考，要实测。
  - 全文送两次很费 token。300–800 条一天就是几百万 token，建议先归并、只给每个事件的代表稿打分，或截取开头、中间、结尾（可借 Horizon 的 `select_content`）。这会偏离它调好的口径，要重新校准。
  - "读者画像"一段（第 3 行）和两张清单要改成你的口味：外语教师、翻译研究者，关心 AI × 语言、翻译、教育。

#### （3）结构化与原文引文核对 `industry/prompts/structure.md` + `analyze.ts:131-189`

- **做什么**：
  - 抽分类（6 类，带判别说明，见 `industry/taxonomy.ts:14-21`）。
  - 标签：第一个必须是分类标签，其余只能取自白名单。
  - 主体公司。
  - 资料范围：single 单一事件 / composite 讲多件事的综合稿 / unknown。
  - **本次发生的事实**：`title`、`subject`、`action`、`object`、`occurredAt`。
  - **evidence**：一句原文，≤600 字符。
  - **conditions**：最多 4 句决定适用范围的原文短句，每句 ≤400 字符。优先免费或收费的具体操作，其次套餐、人群、地区和限额，再次申请、预览等限制（第 29-32 行）。
  - 一系列规则把"本次动作"和背景里的旧发布分开，比如"上周发布、今天讲用法"要写成讲解，不能写成发布（第 22-28、34 行）。
- **程序核对**【代码】：`normalizeStructure`（`analyze.ts:163-189`）把空白压缩后，要求引文同时出现在"模型看到的材料"和"原始正文"里，**查不到的引文直接丢弃**；综合稿和没有正文的资料，事实一律置空。
- **输出示例**：`{category, tags, subjects, scope, fact:{title,subject,action,object,occurredAt,evidence,conditions:[{quote}]}}`；温度 0.2，最多 1200 token（`analyze.ts:315-331`）。
- **对我们的意义**：这几乎就是事件卡里"发生了什么、证据、适用条件"三栏，而且自带"引文必须逐字可查"的机制，是数字核对的地基。
  - **要补**：它不单独抽"关键数字"和"署名观点"。我们加两个字段，`numbers:[{value, unit, quote}]` 和 `opinions:[{speaker, quote}]`，同样要求 quote 逐字可查。

#### （4）中文标题、摘要和推荐理由

- **主提示词**：`industry/prompts/content-understanding.md`，由 `understand.md` 组装，后面拼上下列四份规则。
- **四份共用规则**：
  - `rules-domain.md`：AI 术语译法；专名、版本号、数字单位一字不改，例如不把 $10B 改写成"数百亿"（第 40-45 行）。
  - `rules-anti-hallucination.md`：只写原文有的；相对时间照抄、不补年份；不强化语气。
  - `rules-self-contained-title.md`：标题要点出主体；How、Why、Review 类不得写成"发布"。
  - `rules-answer-first-summary.md`：第一句直接答"谁做了什么、结果是什么"，30–70 字，全文 2–3 句。
- **做什么**：一次输出 `itemType`（7 类）、`authorRole`（当事方 principal / 亲历者 observer / 转述者 relayer）、`tags`、`editorialJudgment`、`titleZh`、`summaryZh`。
  - 推荐理由 45–70 字，只写背景、比较、影响、可迁移方法中的一层。
  - 有一张禁用词清单：必读、重磅、颠覆、首次、这意味着、仍需验证等，并禁用冒号和破折号（第 46-50 行）。
- **程序把关**【代码】：
  - 摘要长度不合规时，按整句截短（`writing.ts:231-268`）。
  - **身份守卫**：中文稿里出现原文没提到的公司时，标题退回原标题，摘要清空（`writing.ts:214-227`；公司名的匹配规则写在 `industry/taxonomy.ts:101-155`）。
- **便宜路径**：不入选的资料用 `summarize-article.md`（80–160 字、最多 3 句）和推文用的 `summarize-*-post.md`。输出是 `title_zh:`、`summary_zh:` 这样的分行文本，不是 JSON，由 `writing.ts:317-372` 解析。
- **移植注意**：
  - 我们只给入选事件写中文，用 content-understanding 加四份规则这一路即可。
  - 关于"保留原文数字和单位"的规则（`rules-domain.md:40-45`），见第四节"数字核对"的说明。

#### （5）改词与数字不变检查 `industry/prompts/mend-wording.md` + `analyze.ts:378-413` + `industry/wording.ts`

- **做什么**：写好的标题、摘要和理由里出现站点禁用词（清单在 `industry/wording.ts:5`，**默认是空的**）时，让模型只改那几处。
- **把关**【代码】：改完必须同时满足三条，否则沿用原稿（`analyze.ts:410-411`）：
  1. 改后的稿子里抽出的所有数字（`\d+(?:[.,]\d+)*`）排序后与改前完全一致；
  2. 禁用词变少；
  3. 身份守卫通过。
- **对我们的意义**：任何"润色、改写"步骤都应套这道"数字不变"闸门。

#### （6）同一事件判断：召回 → 关系 → 复核 → 有没有新信息

- **提示词**：
  - `group-definitions.md`：四种关系的定义。
    - SAME_OCCURRENCE：同一次发生。同批发布的多个型号，以及这次发布的价格、开放计划，都算同一次。
    - SAME_STORY：同一事件的直接进展，如预告与发布、发布与上架、评测、回应。
    - UNRELATED：不同的事，即使公司或产品相同。
    - ROUNDUP：一方是多话题汇总。
  - `group-method.md`：判断方法。先查是不是综合稿；拿不准时问自己"世界上发生了一件事，还是先后两件"。
  - `group-batch.md`：新报道对多个候选逐个判关系，**同时判断相对已公开精选有没有新信息（addsValue）**。第 12-15 行列出"算新增"和"不算新增"的情形，比如换个说法再介绍已披露能力、只上架到别的平台，都不算新增。
  - `group-pair.md`：两篇报道一对一判断，用于复核。
  - `group-signal.md`：社交讨论帖挂到哪个事件。
- **召回**【代码】（`events/recall.ts`）：
  - 比对文本是"标题 + 摘要前 300 字"（`relate.ts:192-194`），在最近 14 天的报道里找（`RECALL_DAYS = 14`，`recall.ts:16`）。
  - 配了向量服务就比余弦相似度；没配就比"两字一组"的重合率，门槛 0.25（`relate.ts:197-207`、`recall.ts:132`）。
  - 同网址、或回复和引用同一条 X 帖，直接算候选（`recall.ts:268-283`）。
  - 已精选内容在 60 天内都作为"读者已看过"的阅读背景（`READING_DAYS = 60`，`recall.ts:18`）。
- **门槛数字**【代码】（`group.ts:39-46`、`relate.ts:174`、`189`）：
  - 召回最低余弦 0.6，最多 10 个候选事实。
  - **余弦低于 0.85 的合并，要另一个模型用一对一提示词复核同意才写入**；复核模型可以单独换一家（`group.ts:88-94`、`395-430`；`editorial/models.ts:32`）。
  - 认定"两件事牢牢相连"要置信度 ≥ 0.8；合并两个事件的复核门槛 0.75。
  - 讨论帖：余弦 ≥ 0.72 才判，≥ 0.92 直接挂上。
  - 关系判断温度 0，最多 400 + 120 × 候选数 token（`group.ts:82`）。
- **结果**：
  - SAME_OCCURRENCE 并入同一事实。
  - SAME_STORY 且候选是该事件的起点，就作为新进展挂到该事件。只挂起点，防止事件"链式越长越大"（`relate.ts:157-160`）。
  - 综合稿只记"提及"，不参与归组（`group.ts:349-376`）。
  - 缺答案按"失败"处理，不当作"无关"（`relate.ts:138-148`）。
- 【注释】`relate.ts:9-10`：作者实测过，改成"是不是同一件、拿不准就说不是"的是非题，会漏掉一半真正该合并的。`relate.ts:184-189`：门槛 0.75 时查准率 0.944、查全率 0.962；0.8 时分别是 0.964、0.896。
- **移植注意**：
  - 余弦门槛和所用的向量模型绑定。AIHOT 示例是 OpenAI `text-embedding-3-small` 或阿里百炼 `text-embedding-v4`（`.env.example:40-46`）；我们换了向量模型（比如 Gemini 的），0.6、0.85、0.72、0.92 都要用标注样本重新定。
  - 第一期可以先只用"两字一组"兜底（0.25），不接向量服务。
  - AIHOT 的事件池在数据库里。我们一天跑一次，把近 14 天的事件索引（标题、摘要、事实框架）存成 JSON 放 R2，或放 D1，运行前取回即可。
  - addsValue 正好用来决定"往期报过的事今天要不要跟进"。

#### （7）热度：按独立参与方计算 `packages/backend/src/events/hot.ts`

- **规则**【代码】：
  - 窗口 48 小时，半衰期 24 小时，至少 2 个参与方（`hot.ts:57-60`）。
  - 每个事件里，**每个独立参与方只算一次**，取其最近一次出现，贡献 `0.5^(距今小时数 / 24)`，全部相加就是热度（`hot.ts:138-177`，衰减式在第 142 行）。
  - 进榜要求：参与方 ≥ 2，且至少 1 个是"编辑型"信源（新闻源，不只是讨论帖）（`hot.ts:185`）；取前 10。
  - **谁算一个参与方**（`hot.ts:113-129`）：
    - HN、DEV 社区按发帖人账号区分；
    - 同一运营方的媒体矩阵算一个；
    - 同一公司的各官方渠道算一个；
    - 其余每个信源算一个。
  - 标记（`hot.ts:224-229`）：6 小时内新增参与方 ≥ 3 且占一半以上标"飙升"；首报不满 6 小时标"新"；比 6 小时前涨 15% 以上标"上升"。
  - 来源抓取落后时，不拿它做涨跌比较（`hot.ts:96-103`）。
- **移植注意**：
  - 纯计算，不调模型，Python 几十行就能写完。
  - 我们每个信源要在配置里标好"属于哪个公司 / 哪个运营方"。
  - 需要昨天的数据才能凑满 48 小时窗口，所以也要存近两天的条目索引。
  - "至少 1 个编辑型参与方"这条，正好落实方案"社交媒体负责发现，一手来源负责事实"。

#### （8）日报编排（不调模型）`packages/backend/src/reports/edition.ts` + `compose.ts`

- **重要性分数**（`edition.ts:289-291`）：`(入选报道最高分，缺省 50) + 5 × log2(1 + 当天独立参与方数) + (有官方原帖 +5) − (往期报过的跟进 −6)`。
- **版面规则**（`edition.ts:25-34`、`396-410`）：
  - 正文 12 条，每个信源最多 2 条，再往后最多 10 条一行快讯。
  - 最近 7 期报过的事，只有当事方自己有新动作，或这条进展有 ≥ 4 家信源报道时才进正文，否则进快讯。教程、观点类的跟进一律进快讯。
  - 第 1 条是头条，第 2–4 条是看点（`compose.ts:89-117`）。
- **代表稿选择**（`publication/representative.ts:15-40`）：官方一手优先 → 核实过的官方账号（机构先于个人） → 有全文的 → 分高的 → 发得早的。
- **对我们的意义**："2 条头条 + 5 条要闻 + 快讯"可以直接用这套打分和约束，只改条数。程序决定选什么、怎么排，模型只负责写，正好对应"事实只核一次"。

#### （9）周报月报导语与"名字、数字必须在条目里"`industry/prompts/report-period*.md` + `compose.ts:142-174`

- **做什么**：模型只写总述和栏目导读，不增删条目（`report-period.md`）。
- **把关**【代码】：`grounded()`（`compose.ts:165-174`）检查生成文字里的三类内容：
  - 每个带大写字母或数字的拉丁词（如 Acme、Nova-2.5）；
  - 每个三位以上、带小数点或百分号的数字；
  - 词表里的每个公司（中英文名都认）。
  只要有一样在条目原文里查不到，这段话就不用：总述换成模板句，栏目导读不放。行业通用词（`taxonomy.ts:31` 的 `PLAIN_TERMS`）不受限制。
- **对我们的意义**：这就是"稿件数字回原文核对"的现成雏形。我们把"条目原文"换成"事件卡中已核实的引文和数字"，对网页稿和口播稿逐段检查；不通过就重写一次，再不通过就退回模板或人工。

#### （10）事件综述 `industry/prompts/story-digest.md`

- **做什么**：给第一次了解这件事的读者写 100–300 字概览。
  - 第一句写核心变化和目前结论；
  - 需要归于提出者的说法写明"某某称"；
  - 新旧报道有矛盾要明说；
  - 收费、额度、地域等条件要绑在对应对象上，不能把"某操作免费"推广成"全部免费"。
- **输出**：`{"title","digest"}`；温度 0.3，最多 1200 token（`events/digest.ts:16-22`）。
- **对我们的意义**：头条段落"发生了什么 → 关键数字 → 谁怎么评价 → 为什么重要"可以在它基础上改。口播稿要另写提示词（口语化、数字读法、每段 1–2 分钟）。

#### （11）其他可借的小件

- `industry/prompts/safety.md`：一句防"提示词注入"的通用安全要求，即材料里的指令一律不执行。
- `industry/prompts/identity-context.md`：给模型"已核验的发布主体"，防张冠李戴。
- `industry/prompts/translate-body.md`：逐段翻译并保留 HTML 标签、链接和占位符。我们出于版权考虑不发全文翻译，可以不用。
- `editorial/models.ts:25-32`：每一步可单独指定模型（预筛、打分、写作、结构化、归组、复核、综述……）。我们照这个思路做"分步选模型"。

### 3.3 用样本校准门槛：它是怎么说的【文档＋代码】

- **选题校准**（`docs/selection.md:36-95`）：
  - 从自己的信源挑 100–200 条，逐条标"该选 / 不该选 / 两可（either）"，存成 `.data/gold.jsonl`。格式见 `industry/gold.example.jsonl`：每行含材料、信源分级、是否一手，以及 `benchmarkSplit`（开发集 development 或留出集 holdout）和自定分组 `samplingStratum`。
  - **多放难例**；留出一部分做最后检查，免得提示词被调成"只会做这几道题"。
  - 标注的人最好就是以后的读者。
  - 评测只跑预筛和两次打分，不含去重，所以按"这条本身该不该选"来标。
  - 输出：查准率、查全率、F1、**覆盖率**（模型成功给出判断的比例）、**完整准确率**（把调用失败也算错）。门槛从 40 到 90 每 2 分扫一遍，看各门槛下的结果（指标在 `scripts/eval-selection-core.ts`，门槛扫描在 `scripts/eval-selection.ts:149-155`）。
  - **先改标准，再动门槛**：
    - 该选没选上，就在"必须正常评价"里写清这类价值；
    - 不该选却选上，就写进"必须压住"；
    - 只有整体偏松或偏紧、错例分数都贴着门槛时，才移动门槛。
- **同一事件判断校准**（`docs/grouping.md:12-78`）：
  - 成对标注四种关系，格式见 `industry/relation-gold.example.jsonl`。
  - 输出 4×4 对照表、各关系的查准和查全，以及不同置信度门槛下"并入同一事件"的效果。
- **事件综述**（`docs/story-digest-evaluation.md`）：没有自动分数，新旧提示词在同一批事件上并排跑，人工逐条看。一次最多 18 次调用。
- **对我们的反馈回流的启发**：你在工作台点的"有用 / 没用"，可以直接存成这种 gold 格式：有用记"该选"，没用记"不该选"。
  - 每周用它跑一次"选题评测"，决定改评分标准还是挪门槛，这是慢回路。
  - 当天的"提上来 / 压下去"另做一个简单的加减分（按主题和信源的权重），影响第二天的排序，这是快回路。AIHOT 没有快回路，要新写。

### 3.4 移植到 Python 的通用注意事项

1. **宽松解析**：AIHOT 用 zod（TypeScript 的数据格式校验工具）大量写 `.catch(默认值)`，字段不合格时用默认值而不是报错（例：`analyze.ts:109-147`）。Python 用 pydantic，要逐字段写同样的宽松规则。并保留它的原则："答案缺失 = 失败"，不能当成"否定"（`relate.ts:138-148`）。
2. **正则与汉字**：`\p{Script=Han}` 这类写法 Python 自带的 `re` 不支持，要用 `regex` 包或明确的汉字范围。
3. **时区**：打分输入的时间固定写成北京时间 `+08:00`，注释说"提示词是按这个形式调的"（`analyze.ts:75-83`）。我们按英国早 7 点出刊，但模型输入可以继续用北京时间，统一即可。
4. **去掉数据库机制**：AIHOT 为长期在线的网站设计了数据库、任务队列、版本号、撤回、人工锁等机制，我们一天批处理一次，大部分用不上。值得保留的是"回执"思路：每次模型调用按（模型、提示词版本、输入）的哈希缓存结果，手动重跑时不重复付费（`providers/llm.ts:118-128`）。
5. **提示词改名**：`{{siteName}}` 换成我们的刊名；不得使用"AIHOT"名称和 Logo（`NOTICE` 第 4-5 行）。
6. **调用量**：AIHOT 每条资料约 5 次模型调用（预筛 1、打分 2、结构化 1、写作 1），归组还要再加 1–2 次。每天 300–800 条就是 1,500–4,000 次以上。建议的顺序（第一期先做这个，再看费用）：
   1. 按网址和文字重合度粗归并；
   2. 预筛只看代表稿；
   3. 打分只给通过预筛的事件；
   4. 结构化和写作只给入选和接近入选的事件。

### 3.5 AIHOT 的规模与维护【代码＋GitHub 接口】

- **规模**：TypeScript 约 41,900 行（不含测试），测试约 22,400 行，数据库迁移脚本 1,324 行。技术栈：Node.js 24、PostgreSQL 17、Docker（README）。
- **CI**：每次提交在全新 PostgreSQL 上跑类型检查、测试和冒烟测试（`.github/workflows/check.yml`）。
- **活跃度**：2026-09-28 建仓，169 次提交，23 位贡献者，8.9k 星。
- **作者说明**【文档】：这个仓库是从线上站"导出"的，"不保证每一次都同步"（`README.md:54`）。所以我们按固定版本搬，不追上游。

---

## 四、B 路线下的零件地图（我们的流水线 ← 零件来源）

| 我们的步骤（方案第五节） | 主要零件 | 来源 |
|---|---|---|
| 1 采集 | RSS、HN、GitHub、GDELT 采集器；正文抽取；防恶意网址；失败报告 | Horizon `src/scrapers/{base,rss,hackernews,github,gdelt}.py`、`src/extractors/trafilatura.py`、`src/url_security.py`、`orchestrator.py:110-175` |
| 2 归并 | 网址规范化；同网址合并；文字重合度或向量召回；四种关系判断与复核；跨天事件池 | Horizon `orchestrator.py:43-84`、`594-647`；AIHOT `relate.ts`、`recall.ts`、`group.ts` 的规则和 `group-*.md` |
| 3 选题 | 预筛；两次打分；信源分级门槛；独立参与方热度；重要性公式与版面约束；你的兴趣加权（新写） | AIHOT `prefilter.md`、`selection-score.md`、`selection.ts`、`hot.ts`、`edition.ts`；Horizon 配额逻辑 `orchestrator.py:913-1033` |
| 4 核实与事件卡 | 结构化事实、原文引文、适用条件；补"关键数字""署名观点"两栏（新写）；代表稿选择；往期关联检索 | AIHOT `structure.md`、`analyze.ts:163-189`、`representative.ts`；Horizon `processing/history.py`（改成检索往期事件卡） |
| 5 写作 | 中文标题、摘要、推荐理由；头条概览；口播稿（新写）；数字与专名核对；改写时数字不变 | AIHOT `content-understanding.md`、`rules-*.md`、`story-digest.md`、`writing.ts:214-268`、`compose.ts:165-174`、`analyze.ts:410-411` |
| 6 可视化 | — | 新写 |
| 7 配音 | — | 数字人项目 |
| 8 发布 | Worker、R2、D1 | 期刊网站；Horizon 只借 Actions 模板 |
| 运行记录、费用 | 每源成败；token 用量；分阶段 JSON 产物 | Horizon `FetchReport`、`src/ai/tokens.py`、`src/mcp/run_store.py` |

---

## 五、可直接搬的清单

**从 Horizon 复制（保留 MIT 声明，固定在 `cdd95f8`）**

- [ ] `src/scrapers/base.py`：采集结果加失败记录。
- [ ] `src/scrapers/rss.py`：要改两处，各源并发抓取；没配全文抽取时去掉 HTML。
- [ ] `src/scrapers/hackernews.py`：官方 Firebase 接口，可带前 5 条评论。
- [ ] `src/scrapers/github.py`：仓库发布记录。
- [ ] `src/scrapers/gdelt.py`
- [ ] `src/extractors/trafilatura.py` + `src/url_security.py`
- [ ] `src/orchestrator.py:43-84`、`594-647`：网址规范化与同网址合并。
- [ ] `src/orchestrator.py:110-175`：FetchReport，即每个源的体检记录。
- [ ] `src/ai/client.py`：OpenAI 兼容和 Anthropic 两个客户端，含参数自适应和备用链。改成每一步可选模型；Azure、Gemini、ChatGPT 登录去掉。
- [ ] `src/ai/utils.py`：从模型回答里稳妥地抠出 JSON。
- [ ] `src/ai/tokens.py`：用量记账。
- [ ] `src/processing/content.py`：长文按开头、中间、结尾截取。
- [ ] `src/processing/history.py`：BM25 往期检索，中文两字一组切词。
- [ ] `src/ai/localization.py` + `src/ai/summarizer.py` 里的 `_pangu`、`_escape_markdown`、`_safe_url`：繁转简、中英空格、安全转义。
- [ ] `src/ai/prompting/common.py`、`src/ai/prompting/enrichment.py:11-17`：英文版防编造、接地规则，与 AIHOT 中文规则合并使用。
- [ ] `.github/workflows/daily-summary.yml.disabled:16-46`：Actions 里装 uv、注入密钥的写法。

**从 AIHOT 移植（规则与提示词，保留 MIT 声明，固定在 `5b2aaaa`）**

- [ ] 提示词（需改读者画像、行业范围和刊名）：
  - `prefilter.md`、`selection-score.md`、`structure.md`；
  - `group-definitions.md`、`group-method.md`、`group-batch.md`、`group-pair.md`（`group-signal.md` 可选）；
  - `content-understanding.md`、`rules-domain.md`、`rules-anti-hallucination.md`、`rules-self-contained-title.md`、`rules-answer-first-summary.md`；
  - `safety.md`、`identity-context.md`、`mend-wording.md`、`story-digest.md`、`report-period.md`、`report-period-sections.md`、`report-period-no-sections.md`；
  - 可选便宜路径：`summarize-article.md`。
- [ ] 模板与版本哈希：`editorial/prompts.ts`。
- [ ] 门槛与规则数字：
  - `selection.ts`：T1 60、T1_5 65、T2 76，understandFloor 50，两次之和 ≥ 2 × 门槛；
  - `group.ts:39-46`：0.6、10、0.85、0.72、0.92；
  - `relate.ts`：0.8、0.75，文字重合度 0.25；
  - `recall.ts`：14 天、60 天；
  - `hot.ts`：48 小时、半衰期 24 小时、≥ 2 个参与方且 ≥ 1 个编辑型；
  - `edition.ts`：重要性公式、12、10、每源 2 条、跟进需 4 家、记 7 期。
- [ ] 程序把关函数：
  - `normalizeStructure`：引文逐字核对；
  - `enforceIdentity`：公司身份守卫；
  - `compactAnswerFirstSummary`、`answerFirstSummaryLengthOk`：摘要长度；
  - `mendWording` 的数字不变检查；
  - `grounded()`、`fitted()`：生成文字核对与按整句截断；
  - `pickRepresentative`：代表稿选择；
  - `lexicalSimilarity`：两字一组重合率。
- [ ] 分类、标签白名单和公司词表的组织方式（`industry/taxonomy.ts`），内容按我们的范围重写。
- [ ] 校准：`gold.example.jsonl`、`relation-gold.example.jsonl` 的格式；`docs/selection.md`、`docs/grouping.md` 的方法与指标（覆盖率、完整准确率、门槛扫描）。

**不要搬**：X（Apify 或浏览器抓取，与 X 条款冲突）、Reddit（11-13 停 RSS）、Telegram、OpenBB、微信公众号付费抓取、MCP、配置向导、邮件、Webhook、微信推送、ChatGPT 登录、AIHOT 的网站前端与数据库。

---

## 六、风险与待实测项

| 风险 | 说明 | 怎么处理 |
|---|---|---|
| 门槛和提示词不对口 | AIHOT 的 60/65/76 和评分标准，是按它的读者（AI 重度用户、产品经理）和它用的模型调的【文档】 | 第一期"先审后发"兜住；第一周你标 100–200 条做 gold 样本，按 3.3 节校准 |
| 调用量与额度 | 照搬 AIHOT 每条约 5 次调用（另加归组 1–2 次），每天 1,500–4,000 次以上；全文送两次很费 token【推断】 | 先归并再打分、分层调用（3.4 第 6 条）；第一天实测 MiMo credits 消耗，再核对方案第九节的估算 |
| MiMo 兼容性 | Horizon 强制 JSON 模式；AIHOT 预设关闭思考。两者都未实测【推断】 | 开工第一天用 3 条样例测：JSON 模式、关闭或开启思考、温度 0.2 和 1 时两次打分的差异 |
| 两次打分的意义 | 温度低时两次几乎相同，等于双倍花费【推断】 | 用样本看两次分差，决定保留两次还是改一次 |
| 向量服务未定 | 余弦门槛绑定向量模型；MiMo 有没有向量接口未查 | 第一期先用文字重合度（0.25）；以后接 Gemini 或别家向量时用成对标注重定门槛 |
| 数字核对的中文难点 | 网页稿要保留原文数字形式才好核对，口播稿要读成"100 亿美元" | 核对在网页稿和事件卡层做；口播稿的数字由程序按事件卡换成读法，不让模型自由改写，再用转写对稿 |
| 范围偏 AI | AIHOT 的预筛和术语规则只认 AI（`rules-domain.md` 写明"100% 是 AI 内容"） | 改预筛的 PASS 条件，加科技商业；术语规则另加科技商业部分 |
| 上游单人维护 | Horizon 76% 的提交出自一人；AIHOT 是线上站导出，不保证同步 | 固定版本复制，不追上游；不依赖它们的发布节奏 |
| 署名与名称 | 两边都是 MIT；AIHOT 的名称和 Logo 不在许可内 | 仓库放 `THIRD_PARTY_NOTICES`（两份许可全文和出处）；不用"AIHOT"字样 |
| 联网补背景 | Horizon 的 `ddgs` 是非官方抓取，在 GitHub 机房 IP 上可能被限【推断】 | 改用方案里的 Brave、Exa、Tavily 免费额度，或 Jina Reader |

---

## 附：核对方式

- 克隆：`git clone --depth 1 https://github.com/Thysrael/Horizon.git horizon`、`git clone --depth 1 https://github.com/KKKKhazix/AIHOT.git aihot`（10-30 21:32 GMT 前后）。
- 活跃度：`gh api repos/<owner>/<repo>`、`/contributors`、`/stats/commit_activity`、`/commits`、`/issues`，只读查询（10-30）。
- 没有安装任何依赖，没有运行仓库里的脚本或测试；"读代码确认"指逐行读了相关函数，不代表运行验证过。
