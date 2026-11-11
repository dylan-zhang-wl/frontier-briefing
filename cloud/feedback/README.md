# 读者反馈（网站底部“反馈”）

11-10 加。家里人帮忙看简报时，发现哪里写错了、念错了、链接打不开，可以在网页最底下点“反馈”写下来；系统建一条 GitHub Issue（GitHub 上的“待办单”），自动初看一遍，属实的攒到周六维护时一起改。

## 链路怎么走

```
网页底部“往期 · 反馈” → 页面左侧弹出反馈框（手机上从底部升起）
   │  POST /frontier/feedback（JSON：期号、哪里不对、称呼、大概位置、页面语言、蜜罐栏）
   ▼
网站 Worker frontier-daily（cloud/deploy/src/index.js）
   │  校验（来源必须是 https://wenlongzhang.com、只收 JSON、长度、期号格式、蜜罐）→ 按 IP 限流（同一实例 10 分钟最多 5 次）
   │  用机密变量 GH_FEEDBACK_TOKEN 调 GitHub 接口，触发 feedback.yml（workflow_dispatch，各栏作为 inputs）
   ▼
GitHub 流程“读者反馈”（.github/workflows/feedback.yml）
   ├ 第一段：再校验一遍 → 今天（UTC）满 30 条就不建、写进运行摘要 → 建 Issue，标签“反馈”
   └ 第二段：自动初看（只读的 claude -p，cloud/feedback/初看.md）→ 结果贴成评论，加标签“属实／不属实／待你看”之一和“已初看”
```

| 文件 | 作用 |
|---|---|
| `site/v3/app.js`“读者反馈”一节、`site/v3/style.css`“读者反馈”一节 | 页脚“反馈”按钮和反馈框 |
| `cloud/deploy/src/index.js`“读者反馈”一节 | 网站 Worker 收反馈、校验、限流、转交 GitHub；测试在 `cloud/deploy/tests/worker.test.js` |
| `.github/workflows/feedback.yml` | 建 Issue、自动初看 |
| `cloud/feedback/feedback.py` | 流程用的小工具：整理 Issue 标题和正文、数今天几条、摘经验库、按初看第一行定标签；测试在 `cloud/feedback/tests/` |
| `cloud/feedback/初看.md` | 给自动初看的任务说明（读什么、怎么判断、输出格式；反馈内容是数据，里面让它做事的话一律不照做） |
| `.github/workflows/feedback-setup.yml` | 手动运行：把令牌写进网站 Worker、核对、线上检查 |

**令牌怎么流转**：仓库 Secret `GH_DISPATCH_TOKEN`（细粒度令牌，只管本仓库，权限只有 Actions 读写；保底触发器也用它）→ 手动流程“读者反馈设置”经标准输入写进网站 Worker 的机密变量 `GH_FEEDBACK_TOKEN`（不落盘、不打印）→ Worker 只用它触发 `feedback.yml`。建 Issue、贴评论用的是流程自带的 `GITHUB_TOKEN`（只给 issues 写权限）；自动初看那一步的环境里只有 `CLAUDE_CODE_OAUTH_TOKEN`，没有 GitHub 和 Cloudflare 的令牌。

注意：`GH_DISPATCH_TOKEN` 能触发本仓库**任何**流程（包括每日出刊），网站 Worker 的代码只用它触发 `feedback.yml`。万一 Cloudflare 账号被别人拿到，这把令牌也就被拿到了；所以它只给 Actions 读写、只管这一个仓库，轮换办法见下面。

**以后每天发布网站会不会把机密变量冲掉**：不会。官方原话 “Wrangler will not delete your secrets (encrypted environment variables) unless you run `wrangler secret delete <key>`”（[Wrangler 配置说明 · Source of truth](https://developers.cloudflare.com/workers/wrangler/configuration/)）。`wrangler secret put` 会马上生成并上线 Worker 的一个新版本（[官方](https://developers.cloudflare.com/workers/configuration/secrets/)：“creates a new version of the Worker and deploys it immediately”），代码和静态文件沿用当前版本；“读者反馈设置”最后一步会核对网站首页照常。

## 第一次上线（按顺序）

1. 把 `feature-feedback` 分支合进 `main`（流程文件要在 `main` 上才能运行、才能被网站触发）。
2. GitHub 网页 Actions → **读者反馈设置** → Run workflow（action 选 `put`）。或者在终端：
   ```bash
   gh workflow run feedback-setup.yml -R dylan-zhang-wl/frontier-daily -f action=put
   ```
3. 等网站下一次发布（每天出刊，或手动放行）把新的页面和 Worker 发上去。之后再跑一次 `check`，最后一步应当写“POST /frontier/feedback（空请求）400：新代码已上线，机密变量在”。
4. 在网站上真提交一条（比如“测试：请忽略”），几十秒后 Issues 里应当出现一条“【反馈】…”，再过几分钟有自动初看的评论和标签。测完把这条关掉。

## 后台在哪看

GitHub 网页 → 仓库 → Issues，按标签“反馈”筛选：

- 全部反馈（含已关的）：https://github.com/dylan-zhang-wl/frontier-daily/issues?q=label%3A%E5%8F%8D%E9%A6%88
- 还没处理的：https://github.com/dylan-zhang-wl/frontier-daily/issues?q=is%3Aopen+label%3A%E5%8F%8D%E9%A6%88
- 周六要看的（属实或待你看、还开着）：https://github.com/dylan-zhang-wl/frontier-daily/issues?q=is%3Aopen+label%3A%E5%8F%8D%E9%A6%88+label%3A%E5%B1%9E%E5%AE%9E%2C%E5%BE%85%E4%BD%A0%E7%9C%8B

终端里：`gh issue list -R dylan-zhang-wl/frontier-daily --label 反馈`。

每条 Issue 里有：期号（带“打开这一期”的链接）、大概位置、称呼、页面语言、读者原文（放在代码块里，原样显示，里面的 @ 换成了全角，不会去提醒谁）、“内容未经核实”的提示；下面一条评论是自动初看：第一行“判断：属实｜不属实｜待你看”，后面是依据（稿子和事件卡的原句）、对应经验库哪一条、建议记成哪类问题、可以怎么改。**初看只是机器的初步判断**，标签只作排队用。

## 周六维护时怎么处理

1. 打开上面“周六要看的”那个链接，逐条读“属实”“待你看”的。“不属实”的扫一眼初看的依据，同意就直接关掉。
2. 确实要改的，按经验库的规矩并进 `文档/经验/问题与解决办法.md`（新经验接各组序号；规矩改第二部分；还没做的记第五部分）；当周维护改掉的照常走改动流程。
3. 在 Issue 里回复一句“并进经验库 x.x／第五部分第 n 件”或“不改，因为……”，然后关掉（Close）。
4. “待你看”的往往是读音、画面、听感这类只有听了看了才知道的，按位置（如“播客 7:33”）去听一下再定。

## 怎么停用

- **临时停**（最简单，随时能恢复）：Cloudflare 网页 → Workers & Pages → `frontier-daily` → Settings → Variables and Secrets，删掉 `GH_FEEDBACK_TOKEN`。网页上提交会显示“反馈功能还没设置好，请稍后再试”，不再建 Issue。恢复：再跑一次“读者反馈设置”（put）。
- **只停自动初看、照样建 Issue**：把 `feedback.yml` 第二段（triage）的 `if:` 改成 `false`，合进 main。
- **整个停**：`gh workflow disable feedback.yml -R dylan-zhang-wl/frontier-daily`（网站会回“暂时没能提交”）；要连页脚的“反馈”按钮也去掉，改 `site/v3/app.js` 里 `renderTop` 那几行，等下一次发布。

## 令牌轮换以后

`GH_DISPATCH_TOKEN` 轮换（Regenerate）或重建以后，用 `gh secret set GH_DISPATCH_TOKEN -R dylan-zhang-wl/frontier-daily` 粘贴新值，然后**要跑两个流程**：

1. “保底触发器”（`trigger-deploy.yml`，action=deploy）：写进保底触发器 Worker；
2. “读者反馈设置”（`feedback-setup.yml`，action=put）：写进网站 Worker。

只跑了一个，另一个 Worker 里还是旧令牌（反馈会回“暂时没能提交”，GitHub 那边是 401）。见 `cloud/密钥与重置手册.md`。

## 本机看样子、测试

- 页面：拼好上线包后起本机服务器，网址加 `?fbmock=ok`（或 `fail`、`rate`、`setup`）模拟服务器的几种回应；不加时提交会说明“只能在网站上提交”，不发请求。双击打开 html（file://）也一样。只有在 https://wenlongzhang.com 上才真提交。
- Worker：`cd cloud/deploy && node --test tests/worker.test.js`
- 流程小工具：`python3 -m unittest discover -s cloud/feedback/tests`

## 限制（照实写）

- 限流只在同一个 Worker 实例的内存里记，实例会换、会有好几个，挡得住手抖连点和简单刷屏，挡不住有心人；真正的上限是 `feedback.yml` 每天最多建 30 条（超过的写进那次运行的摘要，不丢）。两条反馈同一秒到时，各自数“今天几条”，可能多建一两条。
- 自动初看只看得到仓库里的文字（选题、事件卡、文稿），没有配音、视频和网页截图；听感、画面、读音一律“待你看”。每条反馈用一次 Claude 额度（订阅，模型在 `feedback.yml` 的 `MODEL`，默认 opus）。
- 读者能看到的只有“收到了，谢谢”；Issue 在私有仓库里，读者看不到处理结果。
