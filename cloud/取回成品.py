#!/usr/bin/env python3
"""取回成品：把云端某一天的那期简报取回本机，拼成一份完整的期目录，放进成品库 本机资料/成品/<日期>/。

本机资料/ 写进了 .gitignore，不上传 GitHub，只靠 iCloud 在两台 Mac 间同步（2026-11-09 晚用户定）。不写死绝对路径：
本机资料/ 在哪看环境变量 FD_LOCAL_DATA（指向 本机资料 文件夹本身）；没设就是本文件所在仓库根目录下的 本机资料/（本文件在 <仓库根>/cloud/）。
2026-11 拆成两个仓库以后，代码在公开仓库的本机副本里，本机资料/ 留在私有仓库那份本机副本里：这时设 FD_LOCAL_DATA=<私有那份>/本机资料。
在本机（mini 或笔记本）运行，用已经登录好的 gh（GitHub 命令行），不碰任何密钥的值；只用 Python 标准库。

2026-11 起去哪取（拆成两个仓库以后）：
    出刊运行、认领标签 issue/<日期>     公开仓库 REPO_SLUG
    整期文件包                          私有仓库 STATE_SLUG 的发行版 run-<运行编号> 里的 issue-<日期>.tar.gz、media-<日期>.tar.gz
                                        （以前是那次运行的产物 issue-<日期>、media-<日期>；发行版留 14 天，放行发布流程清理）
    已发布的期                          私有仓库的 site-archive 分支

    python3 cloud/取回成品.py                       今天（UTC）那一期（在仓库根目录运行；别处运行写全路径）
    python3 cloud/取回成品.py --date 2026-11-10
    python3 cloud/取回成品.py --date 2026-11-10 --force      已经有这一天也重取（旧的移进废纸篓）
    python3 cloud/取回成品.py --dry-run             只列出要取哪一天、要清理哪几期，不下载、不移动、不 git pull

做什么（按顺序）：
  ① 在本机仓库（默认是放 本机资料/ 的那份，就是 FD_LOCAL_DATA 的上一级；没设时是本文件所在的仓库）里 git pull --ff-only
     （拉下云端提交回来的事件库、账本、每期文字；拆仓库以后它们提交进私有仓库）。
     仓库有没提交的改动、或者不在 main 上，就只提醒、不拉。拉不成也只提醒，接着往下做。
  ② 成品库里 <日期>/ 已经有了就跳过（不覆盖），加 --force 才重取；周六不出刊，没有成品可取。
  ③ 找那天的正式运行（看认领标签 issue/<日期> 的说明里写的运行编号；没有标签或标签说明里没有编号，比如 11-09 手动补的那个，
     就在 main 上最近的正式运行里找），把那次运行的两份文件包都下载下来、拼回一份期目录：带音视频的 media-<日期>（没发布的期才有）打底，
     小份 issue-<日期>（网页、日志、文稿、审片、报告、花费）补上缺的文件。
  ④ 网页 10_网页v3/ 要能双击打开：index.html、外壳（app.js、style.css、video3.js…）、vendor/、issues/index.js、
     issues/<日期>/（issue.js、字体、图、音频）都在。文件包里这一期的网页不全时（比如发行版过期清掉了、只剩已发布的存档），
     从仓库的 site-archive 分支取这一期（已发布的期都存在那里），外壳用本机仓库里现在的 site/v3、site/vendor 补齐。
  ⑤ 放到 本机资料/成品/<日期>/：目录和以前 mini 出的每期一样（00_调度报告.md、01_获取…04_文稿、05_配音、06_配图、10_网页v3、
     11_视频v3、11_视频v3_导演、审片.md、审片结论.json、自检.md、花费.json、logs/ 等），另多一个 取回说明.txt
     （从哪取的、哪次运行、什么时候取的、缺了什么）。下载和拼装先在 ~/.cache/frontier-daily-cloud/取回中/ 里做，
     拼好了才整个挪进成品库（iCloud 不会同步到半截的）。最后打印一句"取回了哪些、在哪"。
  ⑥ 清理（在取回之前做）：成品库里的期目录，满 7 天（按今天的 UTC 日期算，日期早于今天 7 天及以上）、并且这一期已经发布到网站
     （GitHub 上 site-archive 分支里有 issues/<日期>/）的，移进废纸篓（不直接删）；没发布的、不到 7 天的、名字不是日期的都不动。
     查不到 site-archive（没联网、分支还没有）就这次不清。--dry-run 只列出来。

退出码看取回那一步（清理在取回之前做，最后一行是取回的结果）：0＝取回了、或者不用取（已经有了、周六、--dry-run）；1＝还没有可取的（运行没跑完、没找到、文件包过期又没有存档）；2＝出错。
清理出错只打印提醒，不改退出码。
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True       # 仓库在 iCloud 里：import cloud/deploy/assemble.py 时不生成 __pycache__

REPO_SLUG = "dylan-zhang-wl/frontier-briefing"     # 出刊运行、认领标签所在的仓库（2026-11 起是公开仓库）
STATE_SLUG = "dylan-zhang-wl/frontier-daily"       # 私有仓库：整期文件包（发行版 run-<编号>）、site-archive 分支、测试版/ 的文字
WORKFLOW = "frontier-daily.yml"
HERE = Path(__file__).resolve().parent                                           # <仓库根>/cloud
LOCAL_DATA = Path(os.environ.get("FD_LOCAL_DATA") or HERE.parent / "本机资料").expanduser()   # 本机资料/（见文件开头）
DEFAULT_REPO = LOCAL_DATA.parent                                                 # 放 本机资料/ 的那份本机仓库（没设 FD_LOCAL_DATA 时就是本文件所在的仓库）
DEFAULT_OUT = LOCAL_DATA / "成品"                                                # 成品库（11-09 晚定；.gitignore 掉，只靠 iCloud 同步）
BUNDLE_EXT = ".tar.gz"                                                           # 发行版里文件包的后缀（名字去掉它就是以前的产物名）
WORK = Path.home() / ".cache" / "frontier-daily-cloud" / "取回中"                # 下载、拼装先在这里做，拼好再挪进成品库
KEEP_DAYS = 7                                                                    # 已发布的期在成品库里留几天，满了移进废纸篓
WEB_SHELL = ("index.html", "app.js", "style.css", "video3.js", "video3.css", "issues/index.js",
             "vendor/gsap.min.js", "vendor/echarts.min.js")                     # 10_网页v3/ 双击能打开要有的外壳文件
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
OFFICIAL_STEP = "提交跨天状态"       # 正式运行才做的那一步（frontier-daily.yml）；认领标签里没有运行编号时（11-09），靠它认出正式运行


def untar(src: Path, dest: Path):
    """解开一个 .tar.gz 文件包到 dest（只许普通文件和目录，不许绝对路径、..、链接）。"""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(src, "r:gz") as t:
        for m in t.getmembers():
            p = Path(m.name)
            if p.is_absolute() or ".." in p.parts or not (m.isfile() or m.isdir()):
                raise RuntimeError("文件包里有不该有的东西：%s" % m.name)
        try:
            t.extractall(dest, filter="data")
        except TypeError:                    # 老的 Python 没有 filter 参数（上面已经逐个查过）
            t.extractall(dest)


class NotYet(Exception):
    """还没有可取的（退出码 1）。"""


def sh(*cmd, cwd=None, check=False, binary=False):
    p = subprocess.run(list(cmd), cwd=cwd, capture_output=True)
    if not binary:
        p.stdout, p.stderr = p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    if check and p.returncode != 0:
        err = p.stderr if isinstance(p.stderr, str) else p.stderr.decode("utf-8", "replace")
        raise RuntimeError("%s 出错：%s" % (" ".join(cmd[:3]), err.strip()[-300:]))
    return p


class GH:
    """gh 命令行的薄包装（测试时换成假的）。"""

    def api(self, path, missing_ok=False):
        p = sh("gh", "api", path)
        if p.returncode != 0:
            if missing_ok and re.search(r"HTTP 404|Not Found", p.stderr + p.stdout):
                return None
            raise RuntimeError("gh api %s 出错：%s" % (path, (p.stderr or p.stdout).strip()[-300:]))
        return json.loads(p.stdout or "null")

    def run_list(self):
        p = sh("gh", "run", "list", "-R", REPO_SLUG, "-w", WORKFLOW, "-b", "main", "-L", "40",
               "--json", "databaseId,status,conclusion,createdAt,event", check=True)
        return json.loads(p.stdout)

    def releases(self):
        """私有仓库的发行版（含草稿：整期文件包放在草稿发行版里，不发通知、不建标签）。"""
        if not hasattr(self, "_releases"):
            self._releases = self.api("repos/%s/releases?per_page=100" % STATE_SLUG) or []
        return self._releases

    def download(self, run_id, name, dest):
        """把发行版 run-<编号> 里的 <name>.tar.gz 下载下来，解开到 dest。"""
        with tempfile.TemporaryDirectory(prefix="dl-", dir=str(Path(dest).parent)) as td:
            sh("gh", "release", "download", "run-%s" % run_id, "-R", STATE_SLUG, "-p", name + BUNDLE_EXT, "-D", td, check=True)
            untar(Path(td) / (name + BUNDLE_EXT), Path(dest))


# ---------------------------------------------------------------- ① 拉仓库
def pull(repo: Path, log=print):
    if not (repo / ".git").exists():
        log("⚠ 本机仓库 %s 不在，跳过 git pull" % repo)
        return False
    branch = sh("git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != "main":
        log("⚠ 本机仓库现在在 %s 分支上，不在 main：这次不拉（只提醒）" % branch)
        return False
    dirty = [l for l in sh("git", "-C", str(repo), "status", "--porcelain").stdout.splitlines() if l.strip()]
    if dirty:
        log("⚠ 本机仓库有 %d 处没提交的改动：这次不拉（只提醒），先处理好再拉" % len(dirty))
        return False
    p = sh("git", "-C", str(repo), "pull", "--ff-only", "-q")
    if p.returncode != 0:
        log("⚠ git pull --ff-only 没成（%s）：接着用本机现有的版本" % (p.stderr or p.stdout).strip()[-200:])
        return False
    log("本机仓库已拉到最新（main %s）" % sh("git", "-C", str(repo), "rev-parse", "--short", "HEAD").stdout.strip())
    return True


# ---------------------------------------------------------------- ③ 已发布：site-archive 分支
def archive_files(gh: GH, day: str):
    """site-archive 分支里这一天的文件：[(相对 issues/<日期>/ 的路径, blob 编号, 大小)]；没有返回 None。"""
    br = gh.api("repos/%s/branches/site-archive" % STATE_SLUG, missing_ok=True)
    if not br:
        return None
    root = gh.api("repos/%s/git/trees/%s" % (STATE_SLUG, br["commit"]["commit"]["tree"]["sha"]))
    issues = next((e for e in root.get("tree", []) if e["path"] == "issues" and e["type"] == "tree"), None)
    if not issues:
        return None
    days = gh.api("repos/%s/git/trees/%s" % (STATE_SLUG, issues["sha"]))
    d = next((e for e in days.get("tree", []) if e["path"] == day and e["type"] == "tree"), None)
    if not d:
        return None
    t = gh.api("repos/%s/git/trees/%s?recursive=1" % (STATE_SLUG, d["sha"]))
    if t.get("truncated"):
        raise RuntimeError("site-archive 里 %s 这一天的文件太多，接口只回了一部分" % day)
    return [(e["path"], e["sha"], e.get("size", 0)) for e in t.get("tree", []) if e["type"] == "blob"]


def archive_days(gh: GH):
    """site-archive 分支 issues/ 下有哪几天（已发布的期）：{日期}；没有这个分支或没有 issues/ 返回空集合。接口出错就抛出。"""
    br = gh.api("repos/%s/branches/site-archive" % STATE_SLUG, missing_ok=True)
    if not br:
        return set()
    root = gh.api("repos/%s/git/trees/%s" % (STATE_SLUG, br["commit"]["commit"]["tree"]["sha"]))
    issues = next((e for e in root.get("tree", []) if e["path"] == "issues" and e["type"] == "tree"), None)
    if not issues:
        return set()
    days = gh.api("repos/%s/git/trees/%s" % (STATE_SLUG, issues["sha"]))
    return {e["path"] for e in days.get("tree", []) if e["type"] == "tree" and DATE_RE.match(e["path"])}


def fetch_archive(gh: GH, day: str, files, dest: Path):
    for rel, sha, _ in files:
        if rel.startswith("/") or ".." in Path(rel).parts:
            raise RuntimeError("存档里有不该有的路径：%s" % rel)
        blob = gh.api("repos/%s/git/blobs/%s" % (STATE_SLUG, sha))
        out = dest / "issues" / day / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(blob["content"]))


# ---------------------------------------------------------------- ③ 没发布：找那天的正式运行
def run_from_tag(gh: GH, day: str):
    """认领标签 issue/<日期> 的说明里写着"运行 <编号>"。没有标签返回 None。"""
    ref = gh.api("repos/%s/git/ref/tags/issue/%s" % (REPO_SLUG, day), missing_ok=True)
    if not ref:
        return None
    obj = ref["object"]
    if obj["type"] != "tag":                      # 手动补的轻量标签（比如 11-09），说明里没有运行编号
        return None
    tag = gh.api("repos/%s/git/tags/%s" % (REPO_SLUG, obj["sha"]))
    m = re.search(r"运行 (\d+)", tag.get("message", ""))
    return int(m.group(1)) if m else None


def run_by_search(gh: GH, day: str, log=print):
    """没有认领标签时：main 上最近的运行里，私有发行版里有这一天的文件包、而且做了"提交跨天状态"那一步（正式运行才做）的那一次。"""
    running = []
    for r in gh.run_list():
        rid = r["databaseId"]
        if r["status"] != "completed":
            running.append(rid)
            continue
        if not bundles_of(gh, rid, day)[0]:
            continue
        jobs = (gh.api("repos/%s/actions/runs/%d/jobs?per_page=100" % (REPO_SLUG, rid)) or {}).get("jobs", [])
        if any(s["name"].startswith(OFFICIAL_STEP) and s.get("conclusion") not in (None, "skipped")
               for j in jobs if j["name"] == "issue" for s in j.get("steps") or []):
            return rid
    if running:
        log("main 上还有运行没跑完：%s（可能就是这一期，等它跑完再取）" % "、".join(str(x) for x in running))
    return None


def run_info(gh: GH, rid: int):
    return gh.api("repos/%s/actions/runs/%d" % (REPO_SLUG, rid))


def bundles_of(gh: GH, rid: int, day: str):
    """私有仓库发行版 run-<编号> 里这一天的文件包：({名字: 大小}, 发行版在不在)。名字去掉 .tar.gz，和以前的产物名一样。"""
    rel = next((r for r in gh.releases() if r.get("tag_name") == "run-%d" % rid), None)
    if rel is None:
        return {}, False
    want = ("media-" + day, "issue-" + day)
    have = {a["name"][:-len(BUNDLE_EXT)]: a.get("size", 0) for a in rel.get("assets") or []
            if a["name"].endswith(BUNDLE_EXT) and a["name"][:-len(BUNDLE_EXT)] in want}
    return have, True


def merge_fill(src: Path, dst: Path):
    """把 src 里 dst 还没有的文件拷进去（已有的不动）。返回拷了几个。"""
    n = 0
    for f in src.rglob("*"):
        if f.is_file():
            t = dst / f.relative_to(src)
            if not t.exists():
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, t)
                n += 1
    return n


def web_missing(web: Path, day: str):
    """10_网页v3/ 双击打开还缺什么：(缺的外壳文件, 这一期的数据缺不缺, 字体在不在)。"""
    shell = [f for f in WEB_SHELL if not (web / f).is_file()]
    data = not (web / "issues" / day / "issue.js").is_file()
    fonts = any((web / "issues" / day / "fonts").glob("*.woff2")) if (web / "issues" / day / "fonts").is_dir() else False
    return shell, data, fonts


# ---------------------------------------------------------------- ④ 拼成能打开的网页
def build_web(repo: Path, archive_dir: Path | None, issue_dir: Path | None, out: Path):
    """用 cloud/deploy/assemble.py 的做法拼一个只有这一期的网页包（外壳用 repo 里现在的 site/v3）。失败返回原因。"""
    spec = importlib.util.spec_from_file_location("fd_assemble", HERE / "deploy" / "assemble.py")
    asm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(asm)
    shell_repo = repo if (repo / "site" / "v3").is_dir() else HERE.parent
    try:
        asm.assemble(shell_repo, str(archive_dir) if archive_dir else None, [str(issue_dir)] if issue_dir else [], out)
    except (ValueError, OSError) as e:
        return str(e)
    return None


def to_trash(p: Path):
    trash = Path.home() / ".Trash"
    trash.mkdir(exist_ok=True)
    target = trash / ("%s %s" % (p.name, datetime.now().strftime("%H.%M.%S")))
    shutil.move(str(p), str(target))
    return target


def size_mb(p: Path):
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1048576


# ---------------------------------------------------------------- ⑥ 清理：满 7 天、已发布的期移进废纸篓
def clean_old(out_root: Path, gh: GH, today: date, dry_run=False, log=print, keep_days=KEEP_DAYS):
    """成品库里满 keep_days 天、而且已经在 site-archive 里（发布了）的期目录移进废纸篓。返回 (移走的, 留着没清的原因表)。
    没发布的不动（等用户看过再手动放行）；名字不是日期的不动；查不到 site-archive 就一个都不清。"""
    out_root = Path(out_root).expanduser()
    if not out_root.is_dir():
        return [], {}
    old = sorted(p for p in out_root.iterdir()
                 if p.is_dir() and DATE_RE.match(p.name) and (today - date.fromisoformat(p.name)).days >= keep_days)
    if not old:
        return [], {}
    try:
        published = archive_days(gh)
    except (RuntimeError, OSError, ValueError, KeyError) as e:
        log("⚠ 清理：查不到 site-archive 分支（%s），这次不清理" % str(e)[-200:])
        return [], {p.name: "查不到 site-archive" for p in old}
    moved, kept = [], {}
    for p in old:
        if p.name not in published:
            kept[p.name] = "没发布（site-archive 里没有 issues/%s/），不动" % p.name
            continue
        if dry_run:
            log("（试运行）会移进废纸篓：%s（满 %d 天、已发布）" % (p, keep_days))
        else:
            log("清理：%s 满 %d 天、已发布，移进了废纸篓：%s" % (p.name, keep_days, to_trash(p)))
        moved.append(p.name)
    for name, why in kept.items():
        log("清理：%s 满 %d 天但%s" % (name, keep_days, why))
    return moved, kept


def fetch(day: str, out_root: Path, repo: Path, force=False, do_pull=True, run_id=None, gh: GH | None = None, log=print, work=None,
          dry_run=False):
    gh = gh or GH()
    if do_pull and not dry_run:
        pull(repo, log)
    out_root = Path(out_root).expanduser()
    dest = out_root / day
    if dest.exists() and not force:
        log("%s 已经有了：%s（不覆盖；要重取加 --force，旧的会移进废纸篓）" % (day, dest))
        return 0
    if date.fromisoformat(day).isoweekday() == 6 and day >= "2026-11-14":
        log("%s 是周六，不出刊（只抓取、归并、入库），没有成品可取" % day)
        return 0
    if dry_run:
        log("（试运行）会取回 %s，放到 %s%s；这次不下载、不 git pull" % (day, dest, "（旧的先移进废纸篓）" if dest.exists() else ""))
        return 0
    work = Path(work) if work else WORK
    work.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="%s-" % day, dir=work))
    try:
        issue = tmp / day
        note = ["%s 这一期，取回于 %s（本机时间）。" % (day, datetime.now().strftime("%Y-%m-%d %H:%M"))]
        got, lack = [], []
        # ③ 那天的正式运行：media 打底、issue 补缺
        rid = run_id or run_from_tag(gh, day) or run_by_search(gh, day, log)
        info = None
        if rid:
            info = run_info(gh, rid)
            if info.get("status") != "completed":
                raise NotYet("%s 那次正式运行 %d 还没跑完（%s），等它跑完再取：%s" % (day, rid, info.get("status"), info.get("html_url")))
            have, exists = bundles_of(gh, rid, day)
            for name in ("media-" + day, "issue-" + day):
                if name not in have:
                    continue
                raw = tmp / ("_" + name)
                gh.download(rid, name, raw)
                if not issue.exists():
                    shutil.copytree(raw, issue)
                    added = None
                else:
                    added = merge_fill(raw, issue)
                shutil.rmtree(raw)
                got.append("%s（%.0f MB%s）" % (name, have[name] / 1048576, "，补了 %d 个文件" % added if added is not None else ""))
            note.append("来源：运行 %d（%s）的文件包（私有仓库发行版 run-%d）%s。" % (rid, info.get("html_url"), rid, "、".join(got) if got else "（没有可用的）"))
            if "media-" + day not in have:
                lack.append("没有带音视频的 media-%s（%s）：05_配音、11_视频v3 等目录里的音频、视频、图片不在，网页 10_网页v3 里的播客、视频照常能放" % (
                    day, "发行版已过期清掉或没传" if not exists else "发布了的期云端不传这一份"))
            if not exists:
                note.append("私有仓库发行版 run-%d 已过期（留 14 天，放行发布流程会清掉）或那次没传。" % rid)
        # ④ 网页要能双击打开：缺这一期的数据就从 site-archive 取；缺外壳就用本机仓库的 site/v3 补
        web = issue / "10_网页v3"
        shell, no_data, _ = web_missing(web, day)
        src_issue = issue if not no_data else None
        archive_note = ""
        if no_data:
            files = archive_files(gh, day)
            if files:
                arc = tmp / "_archive"
                fetch_archive(gh, day, files, arc)
                archive_note = "这一期的网页数据取自仓库 site-archive 分支 issues/%s/（已发布，%d 个文件）。" % (day, len(files))
            else:
                arc = None
        else:
            arc = None
        if (no_data and arc) or (shell and not no_data):
            packed = tmp / "_web"
            why = build_web(repo, arc, src_issue, packed)
            if why:
                lack.append("网页 10_网页v3 没拼成（%s）" % why)
            else:
                web.mkdir(parents=True, exist_ok=True)
                shutil.copytree(packed / "frontier", web, dirs_exist_ok=True)
                note.append((archive_note + " " if archive_note else "") + "网页外壳（index.html、app.js、vendor/ 等）用本机仓库里现在的 site/v3、site/vendor 补齐。")
                if arc:
                    got.append("site-archive 里的网页")
        if not issue.exists() or not any(issue.iterdir()):
            raise NotYet("%s 没有可取的：%s" % (day, "运行 %d 的文件包没有了，site-archive 里也没有这一天" % rid if rid else
                                                "还没发布，也没找到那天的正式运行（还没跑、没跑完，或者发行版已过期清掉了）"))
        shell, no_data, fonts = web_missing(web, day)
        if shell or no_data:
            lack.append("网页还缺：%s" % "、".join(shell + (["issues/%s/issue.js" % day] if no_data else [])))
        elif not fonts:
            lack.append("网页的字体文件（issues/%s/fonts/）不在：会用系统字体显示" % day)
        if (web / "index.html").is_file():
            note.append("网页：双击 10_网页v3/index.html 用浏览器打开；有的内容出不来时，在 10_网页v3 里运行 python3 -m http.server 8000，再开 http://localhost:8000/ 。")
        if lack:
            note += ["缺了什么："] + ["  · " + x for x in lack]
        (issue / "取回说明.txt").write_text("\n".join(note) + "\n", encoding="utf-8")
        out_root.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            log("旧的那份移进了废纸篓：%s" % to_trash(dest))
        shutil.move(str(issue), str(dest))
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)          # 本程序自己的临时目录（~/.cache/…/取回中/），用完就清；成品库里旧的只会移进废纸篓
    wf = dest / "10_网页v3" / "index.html"
    log("取回了 %s：%s → %s（%.0f MB）%s%s" % (day, "、".join(got) or "网页", dest, size_mb(dest),
                                       "；网页 %s" % wf if wf.is_file() else "；网页没拼成", "；缺：%s" % "；".join(lack) if lack else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="把云端某一天的那期简报取回本机，拼成完整的期目录放进成品库 本机资料/成品/；顺带清理满 7 天、已发布的期")
    ap.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"), help="哪一期，默认今天（UTC）")
    ap.add_argument("--force", action="store_true", help="成品库里已经有这一天也重取（旧的移进废纸篓）")
    ap.add_argument("--out-root", default=str(DEFAULT_OUT), help="成品库（默认 <本机资料>/成品，本机资料 见环境变量 FD_LOCAL_DATA；现在是 %s）" % DEFAULT_OUT)
    ap.add_argument("--repo", default=str(DEFAULT_REPO), help="git pull 哪份本机仓库（默认放 本机资料/ 的那份；现在是 %s）" % DEFAULT_REPO)
    ap.add_argument("--no-pull", action="store_true", help="不 git pull")
    ap.add_argument("--run", type=int, help="直接指定运行编号（不看认领标签）")
    ap.add_argument("--dry-run", action="store_true", help="只列出要取哪一天、要清理哪几期：不下载、不移动、不 git pull")
    ap.add_argument("--no-clean", action="store_true", help="这次不清理满 %d 天、已发布的期" % KEEP_DAYS)
    a = ap.parse_args(argv)
    if not DATE_RE.match(a.date):
        print("✗ 日期要 YYYY-MM-DD：%s" % a.date, file=sys.stderr)
        return 2
    gh = GH()
    if not a.no_clean:                 # 先清理再取回：最后一行仍是取回的结果（定时任务照最后一行报告）
        try:
            clean_old(Path(a.out_root), gh, datetime.now(timezone.utc).date(), dry_run=a.dry_run)
        except (RuntimeError, OSError, ValueError, KeyError) as e:
            print("⚠ 清理出错（不影响取回）：%s" % e, file=sys.stderr)
    try:
        return fetch(a.date, Path(a.out_root), Path(a.repo).expanduser(), a.force, not a.no_pull, a.run, gh=gh, dry_run=a.dry_run)
    except NotYet as e:
        print("还没有可取的：%s" % e)
        return 1
    except (RuntimeError, OSError, ValueError, KeyError) as e:
        print("✗ 出错：%s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
