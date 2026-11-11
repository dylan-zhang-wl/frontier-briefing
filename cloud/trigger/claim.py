#!/usr/bin/env python3
"""同一天只出一期："认领"一天、出错时把认领放回。只用 Python 标准库和 git，本机能用临时的 git 裸仓库测（tests/test_claim.py）。

做法：往仓库推一个 git 标签（tag）当"认领"，名字 issue/<日期>（不在 main 上跑时加前缀 drill/<分支>/，演练不占真日期）。
  - 推上去了＝这一天归这次运行；推不上去、标签已经在了＝别的运行已经认领，这次安静跳过。
  - 推送在 GitHub 那边是原子的（同一个标签只有一个人推得上去）。每次认领都新建一个"带说明的标签"（annotated tag，
    说明里写运行编号），所以两次运行在同一个提交上认领，标签内容也不一样：后来的那个一定被拒（git 会回"已经存在"），
    不会因为内容相同被当成"已经是最新"而误以为认领成功。
  - 放回时只删"自己推的那一个"（--force-with-lease 带上认领时记下的标签编号）：标签要是已经被人删了重建，就不动它。

用法（在仓库目录里；推送凭证由调用方经 GIT_CONFIG_* 环境变量临时给，本程序不碰令牌）：
  python3 cloud/trigger/claim.py tag-name --day 2026-11-10 --ref refs/heads/main      打印标签名
  python3 cloud/trigger/claim.py claim --tag issue/2026-11-10 [--note 说明] [--github-output 文件]
        退出码 0＝认领到了；10＝别人已经认领；2＝出错（推送失败 3 次，或标签名不对）
  python3 cloud/trigger/claim.py release --tag issue/2026-11-10 --expect <标签编号>
        退出码 0＝放回了（或者本来就没有了）；11＝标签已经不是自己那个，没动；2＝出错
  python3 cloud/trigger/claim.py started --jobs-json jobs.json [--stage4 started]
        看 GitHub 接口给的这次运行各 job 的步骤（gh api .../actions/runs/<编号>/jobs），判断 issue 这个 job
        的"第 4–9 步"开始了没有。打印 started 或 not-started；读不懂就退出码 2（调用方按"开始了"处理，标签留着）。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import uuid

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BOT = ["-c", "user.name=frontier-daily bot", "-c", "user.email=frontier-daily-bot@users.noreply.github.com"]
ISSUE_JOB = "issue"
STEP4_PREFIX = "第 4–9 步"          # .github/workflows/frontier-daily.yml 里第 4–9 步那一步名字的开头；改名要一起改
CLAIMED, TAKEN, KEPT, ERROR = 0, 10, 11, 2


def tag_name(day: str, ref: str) -> str:
    """main 上：issue/<日期>；别的分支上：drill/<分支>/issue/<日期>（演练，不占真日期）。"""
    if not DAY_RE.match(day or ""):
        raise ValueError("日期要 YYYY-MM-DD：%r" % day)
    if ref == "refs/heads/main":
        return "issue/%s" % day
    branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
    branch = re.sub(r"[^A-Za-z0-9._/-]", "-", branch).strip("/.") or "unknown"
    return "drill/%s/issue/%s" % (branch, day)


def git(*args, check=False):
    p = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError("git %s 失败：%s" % (" ".join(args[:2]), (p.stderr or p.stdout).strip()[-300:]))
    return p


def valid_tag(tag: str) -> bool:
    return bool(tag) and git("check-ref-format", "refs/tags/" + tag).returncode == 0


def push_flag(out: str, ref: str):
    """git push --porcelain 的输出里，这个标签那一行的记号：* 新建、= 已是最新、- 已删、! 被拒；找不到返回 None。"""
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1].endswith(":" + ref) and parts[0]:
            return parts[0][0], (parts[2] if len(parts) > 2 else "")
    return None, ""


def remote_sha(remote: str, ref: str):
    """远端这个标签指向哪个对象；没有返回 ""；连不上返回 None。"""
    p = git("ls-remote", remote, ref)
    if p.returncode != 0:
        return None
    for line in p.stdout.splitlines():
        sha, _, name = line.partition("\t")
        if name == ref:
            return sha
    return ""


def claim(tag: str, remote: str = "origin", note: str = "", attempts: int = 3, wait: float = 5.0):
    """返回 (退出码, 标签编号, 说明)。"""
    if not valid_tag(tag):
        return ERROR, "", "标签名不合 git 的规矩：%r" % tag
    ref = "refs/tags/" + tag
    # 说明末尾加一段随机字：同一台机器上再认领一次也是新的标签对象（不会被当成"已经是最新"）
    msg = "%s · %s" % (note or ("认领 " + tag), uuid.uuid4().hex[:8])
    git(*BOT, "tag", "-f", "-a", "-m", msg, tag, "HEAD", check=True)
    mine = git("rev-parse", ref, check=True).stdout.strip()
    last = ""
    for i in range(1, attempts + 1):
        p = git("push", "--porcelain", remote, "%s:%s" % (ref, ref))
        flag, summary = push_flag(p.stdout, ref)
        if p.returncode == 0 and flag == "*":
            return CLAIMED, mine, "认领到了：%s" % tag
        if flag == "=":        # 远端已经是自己这个标签（上一次其实推上去了，只是没收到回音）
            return CLAIMED, mine, "认领到了（远端已经是这次运行的标签）：%s" % tag
        now = remote_sha(remote, ref)
        if now == mine:
            return CLAIMED, mine, "认领到了（远端已经是这次运行的标签）：%s" % tag
        if now:                # 远端有，而且不是自己的
            return TAKEN, now, "%s 已经被别的运行认领（远端标签编号 %s），这次不出刊" % (tag, now[:12])
        last = (summary or p.stderr.strip() or p.stdout.strip())[-300:]
        if i < attempts:
            time.sleep(wait * i)
    return ERROR, mine, "认领推送失败 %d 次（最后一次：%s）" % (attempts, last)


def release(tag: str, expect: str, remote: str = "origin"):
    """只删自己推的那一个。返回 (退出码, 说明)。"""
    if not valid_tag(tag) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", expect or ""):
        return ERROR, "标签名或标签编号不对：%r %r" % (tag, expect)
    ref = "refs/tags/" + tag
    p = git("push", "--porcelain", "--force-with-lease=%s:%s" % (ref, expect), remote, ":" + ref)
    flag, summary = push_flag(p.stdout, ref)
    if p.returncode == 0 and flag == "-":
        return CLAIMED, "认领已放回（删掉了 %s）" % tag
    now = remote_sha(remote, ref)
    if now == "":
        return CLAIMED, "%s 本来就没有了，不用放回" % tag
    if now and now != expect:
        return KEPT, "%s 现在指向 %s，不是这次运行认领的那个（%s），没动" % (tag, now[:12], expect[:12])
    return ERROR, "放回失败：%s" % ((summary or p.stderr.strip() or p.stdout.strip())[-300:])


def step4_started(jobs_doc: dict, stage4: str = "") -> bool:
    """issue 这个 job 的第 4–9 步开始了没有（开始了就不放回：Claude 额度、Gemini 的钱可能已经花了）。
    认不出来时抛 ValueError，由调用方按"开始了"处理。"""
    if stage4 == "started":
        return True
    jobs = jobs_doc.get("jobs")
    if not isinstance(jobs, list) or not any(isinstance(j, dict) and j.get("name") == "claim" for j in jobs):
        raise ValueError("接口返回里没有 jobs，或者找不到 claim 这个 job，认不出来")
    issue = [j for j in jobs if isinstance(j, dict) and j.get("name") == ISSUE_JOB]
    if not issue:
        return False                      # issue 这个 job 根本没建起来，什么也没跑
    for j in issue:
        for s in j.get("steps") or []:
            if not str(s.get("name", "")).startswith(STEP4_PREFIX):
                continue
            if s.get("status") == "in_progress":
                return True
            if s.get("status") == "completed" and s.get("conclusion") != "skipped":
                return True
    return False


def write_outputs(path, **kv):
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write("%s=%s\n" % (k, v))


def main(argv=None):
    ap = argparse.ArgumentParser(description="认领一天 / 放回认领")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("tag-name")
    a.add_argument("--day", required=True)
    a.add_argument("--ref", required=True)
    c = sub.add_parser("claim")
    c.add_argument("--tag", required=True)
    c.add_argument("--remote", default="origin")
    c.add_argument("--note", default="")
    c.add_argument("--attempts", type=int, default=3)
    c.add_argument("--wait", type=float, default=5.0)
    c.add_argument("--github-output", default="")
    r = sub.add_parser("release")
    r.add_argument("--tag", required=True)
    r.add_argument("--expect", required=True)
    r.add_argument("--remote", default="origin")
    s = sub.add_parser("started")
    s.add_argument("--jobs-json", required=True)
    s.add_argument("--stage4", default="")
    o = ap.parse_args(argv)

    if o.cmd == "tag-name":
        try:
            print(tag_name(o.day, o.ref))
        except ValueError as e:
            print("✗ %s" % e, file=sys.stderr)
            return ERROR
        return 0
    if o.cmd == "claim":
        try:
            rc, sha, msg = claim(o.tag, o.remote, o.note, o.attempts, o.wait)
        except RuntimeError as e:
            rc, sha, msg = ERROR, "", str(e)
        print(msg)
        write_outputs(o.github_output, claimed="true" if rc == CLAIMED else "false", tag_sha=sha if rc == CLAIMED else "")
        return rc
    if o.cmd == "release":
        rc, msg = release(o.tag, o.expect, o.remote)
        print(msg)
        return rc
    try:
        with open(o.jobs_json, encoding="utf-8") as f:
            doc = json.load(f)
        print("started" if step4_started(doc, o.stage4) else "not-started")
        return 0
    except (OSError, ValueError) as e:
        print("✗ 认不出第 4 步开始了没有：%s" % e, file=sys.stderr)
        return ERROR


if __name__ == "__main__":
    sys.exit(main())
