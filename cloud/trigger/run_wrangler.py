"""运行 Cloudflare 的命令行工具 wrangler（保底触发器 Worker `frontier-daily-trigger`）。照 cloud/deploy/run_wrangler.py 的写法。

Worker 的源码在 cloud/trigger/；运行时先复制到仓库以外的运行目录（本机 ~/.cache/frontier-daily-cloud/trigger-run/，
Actions 里 $RUNNER_TEMP/frontier-trigger-run/）再运行——wrangler 会在运行目录里生成临时文件（.wrangler/），这样不进仓库。

用法（在仓库根目录）：
  python cloud/trigger/run_wrangler.py deploy --dry-run --outdir <临时目录>   只打包检查，不部署、不用令牌
  python cloud/trigger/run_wrangler.py deploy                                部署（要 CLOUDFLARE_API_TOKEN）
  python cloud/trigger/run_wrangler.py secret-put GH_DISPATCH_TOKEN          把同名环境变量的值经标准输入写进 Worker 的机密变量
                                                                             （值不出现在命令行、不打印）
  python cloud/trigger/run_wrangler.py secret list                           只列机密变量的名字
  python cloud/trigger/run_wrangler.py deployments list                      看部署历史

用哪个 wrangler：和网站那个 Worker 一样（cloud/deploy/run_wrangler.py 的 wrangler_cmd：环境变量 WRANGLER 优先，
否则环境变量 FD_WRANGLER_BIN 指的本机 wrangler，都没有就 npx --yes wrangler@4.151.0）。
"""
from __future__ import annotations

import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 和网站那个 Worker 用同一个账号、同一个 wrangler 版本：直接借 cloud/deploy/run_wrangler.py 里的写法（两个文件同名，按路径载入）
_spec = importlib.util.spec_from_file_location("deploy_run_wrangler", HERE.parent / "deploy" / "run_wrangler.py")
_deploy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_deploy)
ACCOUNT_ID, wrangler_cmd, WRANGLER_VERSION = _deploy.ACCOUNT_ID, _deploy.wrangler_cmd, _deploy.WRANGLER_VERSION

SECRET_NAMES = ("GH_DISPATCH_TOKEN",)


def default_run_dir():
    if os.environ.get("RUNNER_TEMP"):
        return Path(os.environ["RUNNER_TEMP"]) / "frontier-trigger-run"
    return Path.home() / ".cache" / "frontier-daily-cloud" / "trigger-run"


def prepare(run_dir):
    """把 cloud/trigger 的配置和源码复制到运行目录（只复制 wrangler.toml 和 src/）。"""
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "src").exists():
        shutil.rmtree(run_dir / "src")          # 运行目录是本程序自己建的临时目录
    shutil.copytree(HERE / "src", run_dir / "src")
    shutil.copy2(HERE / "wrangler.toml", run_dir / "wrangler.toml")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    run_dir = default_run_dir()
    if argv[:1] == ["--run-dir"]:
        if len(argv) < 2:
            sys.exit("--run-dir 后面要跟目录")
        run_dir = Path(argv[1]).expanduser().resolve()
        argv = argv[2:]
    args = argv or ["--version"]
    prepare(run_dir)
    env = dict(os.environ, WRANGLER_SEND_METRICS="false")
    if not env.get("CLOUDFLARE_ACCOUNT_ID") and ACCOUNT_ID:
        env["CLOUDFLARE_ACCOUNT_ID"] = ACCOUNT_ID
    if env.get("CLOUDFLARE_API_TOKEN"):
        env["CLOUDFLARE_API_TOKEN"] = "".join(env["CLOUDFLARE_API_TOKEN"].split())    # 粘贴时带的换行、空格去掉

    stdin_value = None
    if args[0] == "secret-put":
        if len(args) != 2 or args[1] not in SECRET_NAMES:
            sys.exit("secret-put 只认这几个名字：%s" % "、".join(SECRET_NAMES))
        name = args[1]
        stdin_value = "".join((os.environ.get(name) or "").split())
        if not stdin_value:
            sys.exit("环境变量 %s 是空的（仓库 Secret 还没建？），没写" % name)
        args = ["secret", "put", name]

    cmd = wrangler_cmd() + args
    print("运行：", " ".join(shlex.quote(c) for c in cmd), f"（目录 {run_dir}）", flush=True)
    if stdin_value is None:
        return subprocess.call(cmd, cwd=run_dir, env=env)
    # 机密变量的值只经标准输入给 wrangler（wrangler secret put 在没有终端时从标准输入读值），不在命令行、不打印
    return subprocess.run(cmd, cwd=run_dir, env=env, input=stdin_value, text=True).returncode


if __name__ == "__main__":
    sys.exit(main())
