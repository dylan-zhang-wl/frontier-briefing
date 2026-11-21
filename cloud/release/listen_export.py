#!/usr/bin/env python3
"""耳听点选结果自动存回私有仓库（2026-11-21 加）：取站长页 /frontier/_listen?export=json 的导出，只留几栏，
存进私有仓库 dylan-zhang-wl/frontier-daily 的 main：测试版/耳听结果.json（内容没变就不提交）。

谁来跑：私有仓库的“放行发布”（publish.yml，每次发布以后）和“耳听点选结果”（listen-export.yml，每周五 20:23 UTC，也能手动跑）。
两处跑的都是这一个文件，分两步，钥匙和推送令牌不在同一步里：
    python cloud/release/listen_export.py fetch --out <文件>
        取导出。环境变量 STATS_KEY_HASH（私有仓库的 Secret：站长钥匙的指纹，也就是网站认的站长 Cookie fd_pass 的值），
        用 curl 带 Cookie 去要；Cookie 经标准输入交给 curl（curl -H @-），不出现在命令行和进程列表里。
        地址默认 https://wenlongzhang.com/frontier/_listen?export=json，本机测试用环境变量 FD_LISTEN_EXPORT_URL 换成本机地址。
        只留 日期、条目、位置、结果、备注、时间 六栏写进 <文件>（不写导出时间，内容没变时文件逐字节一样）。
    python cloud/release/listen_export.py save --file <文件> --repo-url <私有仓库地址> --work <临时目录>
        浅克隆私有仓库 main（只取 测试版/耳听结果.json 这一个文件），内容一样就不提交；不一样就以 frontier-daily bot（noreply）
        提交“耳听点选结果：N 条”，git pull --rebase 后推送，最多 3 次。推送凭证：环境变量 GH_PUSH_TOKEN（流程自带的
        github.token），只经 git 的环境变量配置交给这一次的 git 命令（同 publish.yml 存往期的做法），不写进 .git/config、不打印。
出任何错（没设钥匙、钥匙格式不对、钥匙不对、超时、连不上、被 Cloudflare 拦、回的不是 JSON、推不上去）都不让流程失败：
只打印一行原因（带 ::warning::，Actions 网页上显示成黄色提醒），并写进运行摘要 $GITHUB_STEP_SUMMARY，退出码 0。
fetch 没成时不写 <文件>，save 看到没有 <文件> 就说一句“没取到，不提交”。
不打印 Cookie、钥匙、令牌，也不打印响应全文；摘要只写“取到 N 条，最新一次点选在哪天”。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_URL = "https://wenlongzhang.com/frontier/_listen?export=json"
REPO_PATH = "测试版/耳听结果.json"
TIMEOUT = 30                      # curl --max-time（秒）
KEEP = (("日期", "日期"), ("条目", "条目"), ("位置", "位置"), ("结果", "结果"), ("备注", "备注"), ("时间", "点选时间"))
BOT = {"GIT_AUTHOR_NAME": "frontier-daily bot", "GIT_AUTHOR_EMAIL": "frontier-daily-bot@users.noreply.github.com",
       "GIT_COMMITTER_NAME": "frontier-daily bot", "GIT_COMMITTER_EMAIL": "frontier-daily-bot@users.noreply.github.com"}
NOTE = ("站长在耳听点选页 /frontier/_listen 点的结果（cloud/release/listen_export.py 从网站导出后存进来）。"
        "每条一行，改过的以最后一次为准；时间是 UTC。结果：念对了／念错了／没听出来。条目的原稿、转写、判断见那一期的 审片结论.json（按位置对）。")


def say(line, warn=False):
    """打印一行，并追加到运行摘要。warn=True 时前面加 ::warning::（Actions 显示成黄色提醒）。"""
    print(("::warning::" if warn else "") + line, flush=True)
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        try:
            with open(summ, "a", encoding="utf-8") as f:
                f.write("耳听点选结果：" + line + "\n\n")
        except OSError:
            pass


# ---------------------------------------------------------------- 取
def slim(data):
    """导出的 JSON → 要存的字典（只留六栏，按 日期 新到旧、时间 先后排）。格式不对抛 ValueError。"""
    if not isinstance(data, dict) or not isinstance(data.get("结果"), list):
        raise ValueError("导出里没有“结果”这一栏")
    rows = []
    for x in data["结果"]:
        if not isinstance(x, dict) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(x.get("日期", ""))):
            raise ValueError("导出里有一条格式不对")
        rows.append({k: ("" if x.get(src) is None else str(x.get(src))) for k, src in KEEP})
    rows.sort(key=lambda r: (r["日期"], r["时间"]), reverse=False)
    rows.sort(key=lambda r: r["日期"], reverse=True)
    return {"说明": NOTE, "条数": len(rows), "结果": rows}


def latest_text(rec):
    rows = rec["结果"]
    if not rows:
        return "取到 0 条（还没点过）"
    last = max(r["时间"] for r in rows)
    return "取到 %d 条，最新一次点选在 %s（UTC），最新一期是 %s" % (len(rows), last[:10] or "?", rows[0]["日期"])


def fetch(out, url=None, key=None, timeout=TIMEOUT):
    """取导出、写 out。返回 (成没成, 一行说明)。不往外抛。"""
    url = url or os.environ.get("FD_LISTEN_EXPORT_URL") or DEFAULT_URL
    key = (os.environ.get("STATS_KEY_HASH", "") if key is None else key).strip().lower()
    if not key:
        return False, "没有 STATS_KEY_HASH（这一步的环境变量没给），没取"
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        return False, "STATS_KEY_HASH 格式不对（不是 64 位十六进制），没取"
    if not shutil.which("curl"):
        return False, "这台机器上没有 curl，没取"
    cmd = ["curl", "-sS", "--max-time", str(timeout), "--connect-timeout", "10", "-H", "@-",
           "-H", "Accept: application/json", "-A", "frontier-daily-listen-export (GitHub Actions)",
           "-o", "-", "-w", "\n%{http_code}", url]
    try:
        r = subprocess.run(cmd, input=("Cookie: fd_pass=%s\n" % key).encode("ascii"), capture_output=True, timeout=timeout + 15)
    except subprocess.TimeoutExpired:
        return False, "超时（%d 秒）没取到" % timeout
    except OSError as e:
        return False, "curl 没跑起来（%s）" % type(e).__name__
    if r.returncode != 0:
        why = {6: "解析不了网址里的主机名", 7: "连不上", 28: "超时（%d 秒）" % timeout, 35: "TLS 握手出错", 60: "证书不对"}.get(r.returncode, "curl 出错")
        return False, "%s（curl 退出码 %d），没取到" % (why, r.returncode)
    body, _, code = r.stdout.rpartition(b"\n")
    code = code.decode("ascii", "replace").strip()
    if code == "404":
        return False, "网站回 404：站长钥匙指纹和网站上的对不上，或者网站上还没有点选页（还没合并发布）"
    if code in ("403", "503") or code.startswith("3"):
        return False, "网站回 %s（可能被 Cloudflare 的防机器人设置拦了，或者网站暂时打不开），没取到" % code
    if code != "200":
        return False, "网站回 %s，没取到" % (code or "?")
    try:
        rec = slim(json.loads(body.decode("utf-8")))
    except (ValueError, UnicodeDecodeError) as e:
        return False, "回的不是导出的 JSON（%s；可能被 Cloudflare 拦了），没存" % str(e)[:60]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True, latest_text(rec)


# ---------------------------------------------------------------- 存
def git_env():
    """给 git 的环境：GH_PUSH_TOKEN 有值时，经 GIT_CONFIG_* 加一个授权头（只对这一次的命令有效，不写进 .git/config）。"""
    env = dict(os.environ)
    tok = env.pop("GH_PUSH_TOKEN", "").strip()
    if tok:
        import base64
        env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                    "GIT_CONFIG_VALUE_0": "AUTHORIZATION: basic " + base64.b64encode(("x-access-token:" + tok).encode()).decode()})
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def git(cwd, *args, env, check=True):
    r = subprocess.run(["git", *args], cwd=str(cwd) if cwd else None, capture_output=True, env=env)
    if check and r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError("git %s 出错：%s" % (args[0], " / ".join(err[-2:])[:200]))
    return r


def save(file, repo_url, work, branch="main", tries=3, pause=10):
    """把 file 存进 repo_url 的 branch 上的 测试版/耳听结果.json。返回 (成没成, 一行说明)。不往外抛。"""
    file = Path(file)
    if not file.is_file():
        return True, "这次没取到结果，不提交"
    new = file.read_bytes()
    try:
        n = json.loads(new.decode("utf-8")).get("条数", "?")
    except (ValueError, UnicodeDecodeError, AttributeError):
        return False, "取到的文件读不出来，不提交"
    env = git_env()
    work = Path(work)
    try:
        if work.exists():
            shutil.rmtree(work)
        git(None, "clone", "-q", "--depth", "1", "--filter=blob:none", "--no-checkout", "--branch", branch, repo_url, str(work), env=env)
        git(work, "sparse-checkout", "set", "--no-cone", "/" + REPO_PATH, env=env)
        git(work, "checkout", "-q", branch, env=env)
        dest = work / REPO_PATH
        if dest.is_file() and dest.read_bytes() == new:
            return True, "和私有仓库里的 %s 一样，不提交（%s 条）" % (REPO_PATH, n)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(new)
        git(work, "add", "--sparse", "--", REPO_PATH, env=env)
        git(work, "commit", "-q", "-m", "耳听点选结果：%s 条" % n, env=dict(env, **BOT))
        for i in range(1, tries + 1):
            ok = git(work, "pull", "-q", "--rebase", "origin", branch, env=dict(env, **BOT), check=False).returncode == 0 \
                and git(work, "push", "-q", "origin", "HEAD:" + branch, env=env, check=False).returncode == 0
            if ok:
                return True, "已提交进私有仓库 %s 的 %s（%s 条）" % (branch, REPO_PATH, n)
            if i < tries:
                time.sleep(pause * i)
        return False, "推了 %d 次都没推上去，这次没存（下次运行会再试）" % tries
    except (RuntimeError, OSError) as e:
        return False, "存的时候出错（%s），这次没存" % str(e)[:200]


def main(argv=None):
    ap = argparse.ArgumentParser(description="耳听点选结果：取导出、存回私有仓库")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--out", required=True)
    s = sub.add_parser("save")
    s.add_argument("--file", required=True)
    s.add_argument("--repo-url", required=True)
    s.add_argument("--work", required=True)
    s.add_argument("--branch", default="main")
    a = ap.parse_args(argv)
    if a.cmd == "fetch":
        ok, line = fetch(a.out)
    else:
        ok, line = save(a.file, a.repo_url, a.work, a.branch)
    say(line, warn=not ok)
    return 0


if __name__ == "__main__":
    sys.exit(main())
