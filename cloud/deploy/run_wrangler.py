"""运行 Cloudflare 的命令行工具 wrangler（每日AI科技前沿简报网站的 Worker `frontier-daily`）。
照期刊监控仓库 site/deploy/run_wrangler.py 的写法。

Worker 的源码在 cloud/deploy/；运行时先复制到仓库以外的运行目录（本机 ~/.cache/frontier-daily-cloud/worker-run/，
Actions 里 $RUNNER_TEMP/frontier-worker-run/），把 wrangler.toml 里的 __ASSETS_DIR__ 换成上线包目录再运行——
wrangler 会在运行目录里生成临时文件（.wrangler/），这样不进仓库。

用法（在仓库根目录）：
  python cloud/deploy/run_wrangler.py --assets <上线包目录> deploy --dry-run --outdir <临时目录>   只打包检查，不发布、不用令牌
  python cloud/deploy/run_wrangler.py --assets <上线包目录> deploy                             正式发布（要 CLOUDFLARE_API_TOKEN）
  python cloud/deploy/run_wrangler.py rollback                                                 回到上一个版本
  python cloud/deploy/run_wrangler.py deployments list                                         看发布历史
  python cloud/deploy/run_wrangler.py d1 migrations apply frontier-visits --remote             在线上的访问统计数据库建表（11-10 已做；加新迁移文件时再运行）
  python cloud/deploy/run_wrangler.py d1 execute frontier-visits --remote --command "SELECT COUNT(*) FROM visits"   只读看条数

上线包由 cloud/deploy/assemble.py 做（里面是 frontier/…）。发布前会再检查一遍（文件数、单个文件大小、不引用外网、noindex），
不通过就不运行 wrangler。

用哪个 wrangler：环境变量 WRANGLER（整条命令，如 "npx --yes wrangler@4.151.0"）优先；否则用环境变量 FD_WRANGLER_BIN
指的本机已经装好的 wrangler（可选，没设或文件不在就跳过）；都没有就用 npx --yes wrangler@4.151.0（Actions 里就是这样）。
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

WRANGLER_VERSION = "4.151.0"
# 本机已经装好的 wrangler（可选）：位置写在环境变量 FD_WRANGLER_BIN 里，不写死在仓库里；没设就用 npx
LOCAL_WRANGLER = Path(os.environ["FD_WRANGLER_BIN"]).expanduser() if os.environ.get("FD_WRANGLER_BIN") else None
# Cloudflare 账号（wenlongzhang.com 所在的那个）。账号编号不是密码，但不写进公开仓库：发布流程（私有仓库）从 Secret
# CLOUDFLARE_ACCOUNT_ID 给；本机运行时自己 export CLOUDFLARE_ACCOUNT_ID=…（编号记在私有仓库的密钥手册里）。
ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")


def default_run_dir():
    if os.environ.get("RUNNER_TEMP"):
        return Path(os.environ["RUNNER_TEMP"]) / "frontier-worker-run"
    return Path.home() / ".cache" / "frontier-daily-cloud" / "worker-run"


def wrangler_cmd():
    if os.environ.get("WRANGLER"):
        return shlex.split(os.environ["WRANGLER"])
    if LOCAL_WRANGLER is not None and LOCAL_WRANGLER.exists():
        return [str(LOCAL_WRANGLER)]
    return ["npx", "--yes", f"wrangler@{WRANGLER_VERSION}"]


def prepare(run_dir, assets):
    """把 cloud/deploy 的配置和源码复制到运行目录，填上上线包位置。"""
    run_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("src", "migrations"):           # Worker 源码；访问统计数据库的表结构（d1 migrations 用，11-10 加）
        if (run_dir / sub).exists():
            shutil.rmtree(run_dir / sub)        # 运行目录是本程序自己建的临时目录
        if (HERE / sub).is_dir():
            shutil.copytree(HERE / sub, run_dir / sub)
    toml = (HERE / "wrangler.toml").read_text(encoding="utf-8")
    if "__ASSETS_DIR__" not in toml:
        sys.exit("wrangler.toml 里没有 __ASSETS_DIR__ 占位")
    (run_dir / "wrangler.toml").write_text(toml.replace("__ASSETS_DIR__", str(assets)), encoding="utf-8")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    assets, run_dir = None, default_run_dir()
    while argv and argv[0] in ("--assets", "--run-dir"):
        if len(argv) < 2:
            sys.exit(f"{argv[0]} 后面要跟目录")
        if argv[0] == "--assets":
            assets = Path(argv[1]).expanduser().resolve()
        else:
            run_dir = Path(argv[1]).expanduser().resolve()
        argv = argv[2:]
    args = argv or ["--version"]

    if args[0] in ("dev", "deploy", "versions"):
        if not assets or not (assets / "frontier" / "index.html").is_file():
            sys.exit(f"还没有上线包（{assets}/frontier/index.html 不存在）：先运行 cloud/deploy/assemble.py，再用 --assets 指过来")
        import assemble  # noqa: E402
        problems, stats = assemble.check_package(assets)
        if problems:
            sys.exit("上线包检查没通过，不运行 wrangler：\n  " + "\n  ".join(problems))
        print("上线包：%(文件数)d 个文件，%(总大小MB).1f MB" % stats, flush=True)
    prepare(run_dir, assets or run_dir / "_no_assets")

    env = dict(os.environ, WRANGLER_SEND_METRICS="false")
    if not env.get("CLOUDFLARE_ACCOUNT_ID") and ACCOUNT_ID:
        env["CLOUDFLARE_ACCOUNT_ID"] = ACCOUNT_ID
    cmd = wrangler_cmd() + args
    print("运行：", " ".join(shlex.quote(c) for c in cmd), f"（目录 {run_dir}）", flush=True)
    return subprocess.call(cmd, cwd=run_dir, env=env)


if __name__ == "__main__":
    sys.exit(main())
