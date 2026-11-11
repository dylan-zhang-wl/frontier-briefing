#!/usr/bin/env python3
"""视频导演半路要新图时，叫私有仓库用 Codex 画（2026-11-11 加，拆成公开、私有两个仓库以后）。

为什么要它：公开仓库里没有 Codex 登录（登录只在私有仓库）。第 10 步以前的一批图由私有仓库的"配图"（images.yml）先画好；
第 14 步视频导演看着画面改分镜时，还可能点名要几张新图（11-09 新画 6 张，11-11 新画 1 张）。以前同一台机器上直接调 Codex；
现在由这个程序把"要画哪几张"送去私有仓库画，画好取回来，导演接着做。

两头都用这个文件：
  公开仓库（video3_images.ensure 在 FD_IMAGE_BACKENDS=remote 时调 draw()）：
    1. 把要画的几张（id、画面描述、版式、新闻背景、主题色）写成一张小单子 director-req-<编号>.json，
       放进私有仓库草稿发行版 run-<运行编号>（和第 10 步以前那批图同一个发行版）；
    2. 叫私有仓库的"配图"（images.yml，mode=director，req=单子的名字）；
    3. 每 20 秒看一眼发行版里有没有 director-img-<编号>.tar.gz，最多等 FD_REMOTE_IMAGES_WAIT 秒（默认 720，即 12 分钟）；
    4. 回来了：图和画图日志放进 06_配图/视频/，每张的结果交回 ensure 照常记账；等不到：这几张算没画成，那一块不带图（和画不成时一样）。
  私有仓库（images.yml 的 mode=director 那一步）：
    python cloud/remote_images.py serve <单子.json> <输出文件夹>
    照 video3_images.gen_one 一张张画（只用 Codex，同时最多 4 张），图、画图日志、每张的结果 outs.json 都写进输出文件夹。

环境变量（公开流程第 10–17 步给；本机不设 FD_IMAGE_BACKENDS=remote 就完全用不到这个文件）：
  FD_REMOTE_IMAGES_TOKEN   只对私有仓库有效的细粒度令牌（公开仓库 Secret STATE_REPO_TOKEN）。只交给 gh 子进程，不打印；
                           视频导演的 claude -p 拿不到（video3_director.run_claude 去掉了它）。
  FD_REMOTE_IMAGES_REPO    私有仓库（没设就用 STATE_REPO）
  FD_REMOTE_IMAGES_RUN     公开仓库这次运行的编号（没设就用 GITHUB_RUN_ID）
  FD_REMOTE_IMAGES_SHA     公开代码的提交编号，私有那边按它取程序（没设就用 GITHUB_SHA）
  FD_REMOTE_IMAGES_DAY     这一期的日期（没设就用 DAY）
  FD_REMOTE_IMAGES_WAIT    最多等几秒（默认 720）
  FD_REMOTE_IMAGES_MAX     最多画几张（测试运行给 1，省 Codex 额度；空＝不限）

测试：python3 -m unittest discover -s cloud/tests -v（用假的 gh、假的 codex，不联网、不花钱）
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = "images.yml"
WAIT_DEFAULT = 720
POLL = 20
WORKERS = 4
ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$")
REQ_RE = re.compile(r"^director-req-[0-9]+-[0-9]+\.json$")
KEYS = ("id", "placement", "format", "brief_en", "context_en", "events")      # 单子里只带画图要用的几项
MARKS = ("codex_登录失效.txt", "codex_额度用完.txt")


def say(*a):
    print(*a, flush=True)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fail(r, note, secs=0):
    return {"ok": False, "backend": "remote", "code": -1, "note": note, "secs": secs, "tokens": None, "finished": now(),
            "prompt": None, "tried": []}


def config():
    e = os.environ
    return {"token": e.get("FD_REMOTE_IMAGES_TOKEN", ""),
            "repo": e.get("FD_REMOTE_IMAGES_REPO") or e.get("STATE_REPO", ""),
            "run": e.get("FD_REMOTE_IMAGES_RUN") or e.get("GITHUB_RUN_ID", ""),
            "sha": e.get("FD_REMOTE_IMAGES_SHA") or e.get("GITHUB_SHA", ""),
            "day": e.get("FD_REMOTE_IMAGES_DAY") or e.get("DAY", ""),
            "wait": int(e.get("FD_REMOTE_IMAGES_WAIT") or WAIT_DEFAULT),
            "max": int(e.get("FD_REMOTE_IMAGES_MAX") or 0)}


def gh(cfg, *args, timeout=120):
    """调 gh：令牌只放进这个子进程的环境（GH_TOKEN），别的变量一概不带。返回 (退出码, 标准输出)。"""
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG") if k in os.environ}
    env["GH_TOKEN"] = cfg["token"]
    env["GH_PROMPT_DISABLED"] = "1"
    try:
        p = subprocess.run(["gh", *args], env=env, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return p.returncode, p.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return -1, str(e)


def retry(cfg, *args, tries=3):
    for i in range(1, tries + 1):
        rc, out = gh(cfg, *args)
        if rc == 0:
            return True
        if i < tries:
            time.sleep(i * 5)
    return False


def assets(cfg, rel):
    rc, out = gh(cfg, "release", "view", rel, "-R", cfg["repo"], "--json", "assets", "--jq", ".assets[].name", timeout=60)
    return set(out.split()) if rc == 0 else set()


def draw(d, reqs, accent):
    """公开仓库这边：把 reqs 送去私有仓库画。返回 [(r, 结果)]，结果的样子和 video3_images.gen_one 一样（ok、backend、secs …）。"""
    d = Path(d)
    cfg = config()
    miss = [k for k in ("token", "repo", "run") if not cfg[k]]
    if miss:
        say("  远程画图：没配好（缺 %s），这几张不画" % "、".join(miss))
        return [(r, fail(r, "远程画图没配好")) for r in reqs]
    send = [r for r in reqs if ID_RE.match(str(r.get("id") or ""))]
    outs = [(r, fail(r, "图的名字不合规矩")) for r in reqs if r not in send]
    if cfg["max"] and len(send) > cfg["max"]:
        outs += [(r, fail(r, "测试运行最多远程画 %d 张" % cfg["max"])) for r in send[cfg["max"]:]]
        send = send[:cfg["max"]]
    if not send:
        return outs
    tag = "%d-%d" % (int(time.time()), os.getpid())
    req_name, ans_name = "director-req-%s.json" % tag, "director-img-%s.tar.gz" % tag
    rel = "run-%s" % cfg["run"]
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="fd-remote-img-") as td:
        td = Path(td)
        body = {"day": cfg["day"], "accent": accent, "made": now(), "reqs": [{k: r[k] for k in KEYS if k in r} for r in send]}
        (td / req_name).write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
        say("  远程画图：叫私有仓库画 %d 张（%s；单子 %s）" % (len(send), "、".join(r["id"] for r in send), req_name))
        if gh(cfg, "release", "view", rel, "-R", cfg["repo"], "--json", "name", timeout=60)[0] != 0:
            retry(cfg, "release", "create", rel, "-R", cfg["repo"], "--draft", "--target", "main", "--title", "%s（%s）" % (rel, cfg["day"]),
                  "--notes", "公开仓库运行 %s 的文件包。放行发布流程 14 天后清掉。" % cfg["run"])
        if not retry(cfg, "release", "upload", rel, "-R", cfg["repo"], "--clobber", str(td / req_name)):
            say("  远程画图：单子没放进私有仓库发行版，这几张不画")
            return outs + [(r, fail(r, "单子没放进私有仓库")) for r in send]
        args = ["workflow", "run", WORKFLOW, "-R", cfg["repo"], "--ref", "main", "-f", "mode=director", "-f", "date=" + cfg["day"],
                "-f", "run_id=" + cfg["run"], "-f", "req=" + req_name, "-f", "test=false"]
        if cfg["sha"]:
            args += ["-f", "sha=" + cfg["sha"]]
        if not retry(cfg, *args):
            say("  远程画图：没叫成私有仓库的配图，这几张不画")
            return outs + [(r, fail(r, "没叫成私有仓库的配图")) for r in send]
        got = False
        while time.time() - t0 < cfg["wait"]:
            time.sleep(POLL)
            if ans_name in assets(cfg, rel):
                got = True
                break
        secs = round(time.time() - t0)
        if not got:
            say("  远程画图：%d 秒内没回来，这几张不带图" % secs)
            return outs + [(r, fail(r, "私有仓库 %d 秒内没画回来" % secs, secs)) for r in send]
        back = td / "back"
        back.mkdir()
        rc, _ = gh(cfg, "release", "download", rel, "-R", cfg["repo"], "-p", ans_name, "-D", str(td), "--clobber", timeout=300)
        try:
            if rc != 0:
                raise OSError("下载没成")
            with tarfile.open(td / ans_name) as tf:
                tf.extractall(back, filter="data")
            res_all = json.loads((back / "outs.json").read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            say("  远程画图：取回来的包打不开（%s），这几张不带图" % type(e).__name__)
            return outs + [(r, fail(r, "取回来的包打不开", secs)) for r in send]
        why = ("，多半是 Codex 登录失效" if (back / MARKS[0]).exists() else
               "，多半是 Codex 额度用完" if (back / MARKS[1]).exists() else "")
        d.mkdir(parents=True, exist_ok=True)
        n = 0
        for r in send:
            rid = r["id"]
            res = res_all.get(rid) if isinstance(res_all.get(rid), dict) else None
            img = back / (rid + ".png")
            if res and res.get("ok") and img.is_file() and img.stat().st_size > 0:
                shutil.copyfile(img, d / (rid + ".png"))
                n += 1
            elif res:
                res = dict(res, ok=False, note=(res.get("note") or "没画成") + why)
            else:
                res = fail(r, "私有仓库没交回这一张的结果" + why, secs)
            log = back / ("log_%s.png.txt" % rid)
            if log.is_file():
                shutil.copyfile(log, d / log.name)
            res.setdefault("tried", [])
            outs.append((r, res))
        say("  远程画图：等了 %d 秒，画回来 %d/%d 张%s" % (secs, n, len(send), why))
    return outs


def serve(req_path, out_dir):
    """私有仓库这边：照单子一张张画（只用 Codex），图、画图日志、outs.json 写进 out_dir。返回退出码（0 全画成，1 有没画成的，2 单子不对）。"""
    sys.path.insert(0, str(ROOT / "site/tools"))
    os.environ["FD_IMAGE_BACKENDS"] = "codex"          # 私有仓库里只有 Codex；不许再转成 remote
    import video3_images as V                           # noqa: E402
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    try:
        body = json.loads(Path(req_path).read_text(encoding="utf-8"))
        reqs = [r for r in body["reqs"] if ID_RE.match(str(r.get("id") or "")) and r.get("brief_en")]
    except Exception as e:  # noqa: BLE001
        say("单子读不了：%s" % type(e).__name__)
        (out / "outs.json").write_text("{}", encoding="utf-8")
        return 2
    accent = body.get("accent")
    say("导演要画 %d 张：%s" % (len(reqs), "、".join(r["id"] for r in reqs)))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        res = dict(ex.map(lambda r: (r["id"], V.gen_one(out, r, accent)), reqs))
    (out / "outs.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for v in res.values() if v.get("ok"))
    say("画成 %d/%d 张，用了 %d 秒" % (ok, len(reqs), round(time.time() - t0)))
    return 0 if ok == len(reqs) else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 3 and argv[0] == "serve":
        return serve(argv[1], argv[2])
    say(__doc__.split("\n\n")[0])
    say("用法：python cloud/remote_images.py serve <单子.json> <输出文件夹>（私有仓库用；公开那边由 video3_images 调 draw()）")
    return 2


if __name__ == "__main__":
    sys.exit(main())
