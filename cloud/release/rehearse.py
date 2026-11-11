#!/usr/bin/env python3
"""本机排练"放行 → 发布 → 发邮件"那一段：直接读现行的流程文件，
取里面从"出刊了没有"（id: made）到"发邮件"的几步，把每一步的 run 脚本原样用 bash 跑一遍
（if 条件按 GitHub 的写法手工判断），"发布"那一步换成 wrangler deploy --dry-run 并当作发布成功，
"核对 Cloudflare 令牌"跳过，密钥一律不带（邮件因此只打印、不发）。按正式运行排练（不是测试运行）。

2026-11 拆成两个仓库以后，这一段在私有仓库的 .github/workflows/publish.yml（"放行发布"），公开仓库里没有这个文件：
    流程文件按这个顺序找：环境变量 FD_PUBLISH_WF → <仓库目录>/.github/workflows/publish.yml；都没有就说明一句、退出码 0（跳过）。
    （拆仓库以前的 frontier-daily.yml 里也是同样这几步，FD_PUBLISH_WF 指向它也能排练。）
    往期存档推到哪：publish.yml 里用环境变量 ARCHIVE_REMOTE（排练时这里设成 <仓库目录> 的 origin，就是本机的裸仓库）。

用法：python3 cloud/release/rehearse.py <仓库目录> <日期> <true|false：假装 SITE_DEPLOY_ENABLED>
仓库目录里要有 cloud/、site/（v3 模板、vendor、tools/v3_site.py）、
测试版/<日期>/（完整期目录）、测试版/月度账本/，并且 origin 指向一个可以推送的仓库（排练时用本机的 git 裸仓库，不要指向 GitHub）。
草稿放在 <仓库目录>/../runner-<日期>/。

来历：2026-11-08 用 11-06、11-07、11-08 的副本排练过 cloud/release/workflow_片段.yml（放行发布两期、没放行、没出刊三条路都走通）。
片段之后流程文件又改过，排练片段说明不了现行流程，所以 11-09 晚改成读现行流程文件，片段移到 文档/历史/。
流程文件里这一段的步骤有增减时，这里会报"没认出的步骤"，照着补上判断。
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

repo, day, enabled = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
WF = Path(os.environ.get("FD_PUBLISH_WF") or repo / ".github" / "workflows" / "publish.yml")
if not WF.is_file():
    print("跳过排练：找不到放行发布的流程文件 %s。2026-11 起它在私有仓库（dylan-zhang-wl/frontier-daily 的 "
          ".github/workflows/publish.yml）；用环境变量 FD_PUBLISH_WF 指过去再运行。" % WF)
    sys.exit(0)
jobs = yaml.safe_load(open(WF, encoding="utf-8"))["jobs"]
all_steps = next(j["steps"] for j in jobs.values() if any(s.get("id") == "made" for s in j.get("steps") or []))
i0 = next(i for i, s in enumerate(all_steps) if s.get("id") == "made")
i1 = next(i for i, s in enumerate(all_steps) if str(s.get("name", "")).startswith("发邮件"))
steps = all_steps[i0:i1 + 1]

tmp = repo.parent / ("runner-" + day)
tmp.mkdir(exist_ok=True)
summary = tmp / "summary.md"
summary.touch()
# 前面"定日期"那一步（id: day）的输出：按正式运行、不是周六、要出刊
# publish.yml 的"定参数"（id: day）还多给 mode（auto＝公开仓库叫的）、test_mail；"取成品"（id: fetch）当作成功
out = {"day": {"day": day, "test": "false", "produce": "true", "saturday": "false", "mode": "auto", "test_mail": "false"},
       "mark4": {"stage4": "started"}}
outcome = {"fetch": "success"}
origin = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
if not origin or origin.startswith(("http://", "https://", "git@")):
    raise SystemExit("排练要 <仓库目录> 的 origin 指向本机的 git 裸仓库（现在是：%s），不要指向 GitHub" % (origin or "没有 origin"))
base = dict(os.environ, DAY=day, RUNNER_TEMP=str(tmp), GITHUB_STEP_SUMMARY=str(summary), PYTHONDONTWRITEBYTECODE="1",
            GITHUB_SERVER_URL="https://github.com", GITHUB_REPOSITORY="dylan-zhang-wl/frontier-daily", GITHUB_RUN_ID="排练",
            IN_CLAIM_TAG="", IN_CLAIM="", FD_RUN_ID="排练", ARCHIVE_REMOTE=origin)
for k in ("SENDER_EMAIL", "EMAIL_APP_PASSWORD", "NOTIFY_EMAIL", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "GH_PUSH_TOKEN"):
    base.pop(k, None)

EXPR = re.compile(r"\$\{\{\s*(.+?)\s*\}\}")


def value(e):
    """一个 ${{ … }} 表达式在排练里的值；用到密钥或 github.token 的返回 None（这个环境变量不给）。"""
    if "secrets." in e or "github.token" in e:
        return None
    m = re.fullmatch(r"steps\.(\w+)\.outputs\.(\w+)", e)
    if m:
        return out.get(m.group(1), {}).get(m.group(2), "")
    m = re.fullmatch(r"steps\.(\w+)\.outcome", e)
    if m:
        return outcome.get(m.group(1), "skipped")
    if e == "vars.SITE_DEPLOY_ENABLED":
        return enabled
    raise SystemExit("没认出的表达式：${{ %s }}" % e)


def cond(s):
    i, n = s.get("id"), s["name"]
    release = out.get("gate", {}).get("release") == "true"
    if i == "made":
        return True
    if i == "gate":
        return out.get("made", {}).get("made") == "true"
    if n.startswith("取往期存档") or i == "pkg":
        return release
    if n.startswith("核对 Cloudflare 令牌"):
        return False                                # 排练不带密钥
    if n.startswith("只打包检查"):
        return outcome.get("pkg") == "success" and enabled != "true"
    if i == "deploy":
        return outcome.get("pkg") == "success" and enabled == "true"
    if n.startswith("存进往期存档"):
        return outcome.get("deploy") == "success"
    if n.startswith("发邮件"):
        return True
    raise SystemExit("没认出的步骤：" + n)


for s in steps:
    if not cond(s):
        print("\n—— 跳过：" + s["name"])
        outcome[s.get("id")] = "skipped"
        continue
    print("\n—— 运行：" + s["name"])
    env = dict(base)
    for k, v in (s.get("env") or {}).items():
        v = str(v)
        vals = [value(e) for e in EXPR.findall(v)]
        if any(x is None for x in vals):
            continue                                # 排练不用任何密钥
        it = iter(vals)
        env[k] = EXPR.sub(lambda _m: next(it), v)
    if s.get("id") == "deploy":                     # 不真发布：换成 dry-run，当作发布成功
        script = 'python3 cloud/deploy/run_wrangler.py --assets "$RUNNER_TEMP/site-pkg" --run-dir "$RUNNER_TEMP/wr" deploy --dry-run --outdir "$RUNNER_TEMP/worker-deploy-dry"'
    else:
        script = re.sub(r"\bpython ", "python3 ", s["run"])
    ofile = tmp / ("out-%s" % (s.get("id") or "x"))
    ofile.write_text("")
    env["GITHUB_OUTPUT"] = str(ofile)
    if "run_wrangler.py" in script and "--run-dir" not in script:
        script = script.replace("run_wrangler.py --assets", 'run_wrangler.py --run-dir "$RUNNER_TEMP/wr" --assets')
    r = subprocess.run(["bash", "-e", "-c", script], cwd=repo, env=env)
    outcome[s.get("id")] = "success" if r.returncode == 0 else "failure"
    if s.get("id"):
        out[s["id"]] = dict(line.split("=", 1) for line in ofile.read_text().splitlines() if "=" in line)
    print("   → %s %s" % (outcome[s.get("id")], out.get(s.get("id"), "")))
    if r.returncode != 0 and not s.get("continue-on-error"):
        print("   （这一步出错；后面带 always() 的照样跑）")
print("\n===== 摘要 =====\n" + summary.read_text())
