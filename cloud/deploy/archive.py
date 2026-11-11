#!/usr/bin/env python3
"""往期存档：已发布的每一期网页文件（issues/<日期>/…）存在本仓库一个单独的分支 site-archive 上。

为什么要存：云端每次都是一台空机器，而 Cloudflare 每次发布都要拿到全部往期（见 assemble.py 开头）。
为什么放单独的分支：主分支（程序）照常小巧，actions/checkout 默认只取主分支；这个分支只放网页文件，
不和程序混在一起，也不和主流程往主分支提交的事件库、账本抢着推送。

用法（在仓库根目录，也就是 actions/checkout 取下来的那个目录；用的是它已有的推送权限，不另用令牌）：
    python cloud/deploy/archive.py pull --dir <存档目录>
        取 site-archive 的最新一版，解到 <存档目录>/issues/…；这个分支还没有（第一次发布）就给一个空目录。
    python cloud/deploy/archive.py push --dir <存档目录> --issue 测试版/<日期> [--date <日期>]
        把这一期的 issues/<日期>/ 放进存档目录，提交到 site-archive 并推送。同一天再发布时，整天的文件换成新的。
        推送被拒（别处刚推过）就重新取、重新提交，最多 3 次。
    参数 --branch（默认 site-archive）、--remote（默认 origin）、--repo（默认当前目录）。

做法只用 git 的底层命令（fetch、archive、read-tree、write-tree、commit-tree、push），不切换分支、不动主分支的文件和暂存区。
本程序不删除任何文件：存档目录里同一天的旧文件只在“写进提交的那份清单”里被替换。
以后换成 R2 时，这个文件整体换掉（见 cloud/deploy/README.md“以后换成 R2”）。
"""
import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BOT = {"GIT_AUTHOR_NAME": "frontier-daily bot", "GIT_AUTHOR_EMAIL": "frontier-daily-bot@users.noreply.github.com",
       "GIT_COMMITTER_NAME": "frontier-daily bot", "GIT_COMMITTER_EMAIL": "frontier-daily-bot@users.noreply.github.com"}


def git(repo, *args, env=None, check=True, binary=False):
    e = dict(os.environ, **(env or {}))
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=e)
    if check and r.returncode != 0:
        raise RuntimeError("git %s 出错：%s" % (" ".join(args[:3]), r.stderr.decode("utf-8", "replace").strip()[:300]))
    return r if binary else type("R", (), {"returncode": r.returncode, "out": r.stdout.decode("utf-8", "replace").strip(),
                                           "err": r.stderr.decode("utf-8", "replace").strip()})()


def fetch(repo, remote, branch):
    """取远端分支（只取最新一版）。返回那一版的提交号；分支还没有就返回 None。"""
    ref = "refs/remotes/%s/%s" % (remote, branch)
    r = git(repo, "fetch", "--depth", "1", remote, "+refs/heads/%s:%s" % (branch, ref), check=False)
    if r.returncode != 0:
        if re.search(r"couldn't find remote ref|not found|no such ref", r.err, re.I):
            return None
        raise RuntimeError("取 %s 分支出错：%s" % (branch, r.err[:300]))
    return git(repo, "rev-parse", ref).out


def pull(repo, remote, branch, dest):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    head = fetch(repo, remote, branch)
    if head is None:
        (dest / "issues").mkdir(exist_ok=True)
        print("存档分支 %s 还没有（第一次发布）：往期为空" % branch)
        return None
    data = git(repo, "archive", "--format=tar", head, binary=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        for m in tf.getmembers():                      # 只解普通文件和目录，路径不许跑出存档目录
            if not (m.isfile() or m.isdir()) or m.name.startswith("/") or ".." in Path(m.name).parts:
                raise RuntimeError("存档里有不该有的条目：%s" % m.name)
        tf.extractall(dest)
    (dest / "issues").mkdir(exist_ok=True)
    days = sorted(d.name for d in (dest / "issues").iterdir() if DATE_RE.match(d.name))
    print("取到存档 %s（%s）：%d 期%s" % (branch, head[:7], len(days), "，最新 " + days[-1] if days else ""))
    return head


def issue_web_dir(issue, day=None):
    p = Path(issue).resolve()
    day = day or p.name
    for c in (p / "10_网页v3" / "issues" / day, p / "issues" / day, p):
        if c.name == day and (c / "issue.js").is_file():
            return day, c
    raise ValueError("在 %s 下找不到 issues/%s/issue.js" % (p, day))


def push(repo, remote, branch, dest, issue, day=None, message=None, tries=3):
    day, src = issue_web_dir(issue, day)
    if not DATE_RE.match(day):
        raise ValueError("日期不对：%s" % day)
    dest = Path(dest)
    stage = dest / "issues" / day
    if stage.resolve() != src.resolve():
        if stage.exists():                              # 同一天重新发布：先放到一边，不删
            keep = Path(tempfile.mkdtemp(prefix="old-%s-" % day, dir=dest))
            stage.rename(keep / day)
        shutil.copytree(src, stage)
    gitdir = git(repo, "rev-parse", "--absolute-git-dir").out
    for attempt in range(1, tries + 1):
        parent = fetch(repo, remote, branch)
        with tempfile.TemporaryDirectory() as td:
            env = dict(BOT, GIT_INDEX_FILE=str(Path(td) / "index"))
            if parent:
                git(repo, "read-tree", parent, env=env)
            git(repo, "rm", "-r", "-q", "--cached", "--ignore-unmatch", "issues/%s" % day, env=env)   # 只改清单，不碰文件
            add = subprocess.run(["git", "--git-dir", gitdir, "--work-tree", str(dest.resolve()), "add", "-f", "issues/%s" % day],
                                 cwd=str(dest), capture_output=True, env=dict(os.environ, **env))
            if add.returncode != 0:
                raise RuntimeError("git add 出错：" + add.stderr.decode("utf-8", "replace")[:300])
            tree = git(repo, "write-tree", env=env).out
        if parent and tree == git(repo, "rev-parse", parent + "^{tree}").out:
            print("存档里 %s 已经是这一版，不用提交" % day)
            return parent
        args = ["commit-tree", tree, "-m", message or "往期存档：%s" % day] + (["-p", parent] if parent else [])
        commit = git(repo, *args, env=BOT).out
        # 推送缓冲调到 500 MB：默认 1 MB，一期约 10 MB 走 HTTPS 分块上传时 GitHub 会回 400（11-09 晚在本机遇到：
        # "RPC failed; HTTP 400"，最后一行却是 "Everything up-to-date"）。只对这一条命令生效，不改 git 设置。
        r = git(repo, "-c", "http.postBuffer=524288000", "push", remote, "%s:refs/heads/%s" % (commit, branch), check=False)
        if r.returncode == 0:
            print("已把 %s 存进 %s（%s）" % (day, branch, commit[:7]))
            return commit
        why = " / ".join(r.err.splitlines()[-4:]) if r.err else "原因不明"      # 真正的原因常在倒数几行，只看最后一行会被误导
        print("第 %d 次推送没成（%s），重新取一次再试" % (attempt, why))
    raise RuntimeError("推送 %s 分支 %d 次都没成" % (branch, tries))


def main(argv=None):
    ap = argparse.ArgumentParser(description="往期存档（site-archive 分支）")
    ap.add_argument("cmd", choices=("pull", "push"))
    ap.add_argument("--dir", required=True, help="存档目录（里面是 issues/<日期>/）")
    ap.add_argument("--issue", help="push：这一期的期目录（测试版/<日期>）")
    ap.add_argument("--date", help="push：日期（默认取期目录名）")
    ap.add_argument("--repo", default=".", help="仓库目录（默认当前目录）")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--branch", default="site-archive")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "pull":
            pull(a.repo, a.remote, a.branch, a.dir)
        else:
            if not a.issue:
                ap.error("push 要给 --issue")
            push(a.repo, a.remote, a.branch, a.dir, a.issue, a.date)
    except (RuntimeError, ValueError, OSError) as e:
        print("✗ " + str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
