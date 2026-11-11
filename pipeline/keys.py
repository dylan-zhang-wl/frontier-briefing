#!/usr/bin/env python3
"""密钥：只读进进程环境，绝不输出。

从本机的 .env 文件里只取 MIMO_API_KEY、MIMO_BASE_URL 两个变量注入 os.environ，环境里已经有的不覆盖。
.env 在哪只看环境变量 FD_ENV_FILE，没设就不读任何文件（GitHub Actions 上由 Secrets 直接给环境变量，不读文件）。

规矩：
    · 任何日志、报错、文件都不得出现密钥值；要打印的文字一律先过 hide()。
    · requests 等库的异常信息可能带请求头原文，所以 install_excepthook() 会把未捕获异常的
      整段回溯也先抹掉密钥再打印。
    · 自检只报"有没有""是哪种密钥""地址的主机名"，不报值：
          python pipeline/keys.py
"""
import os
import sys
import traceback
from pathlib import Path
from urllib.parse import urlparse

# 本机 .env 的位置：只看环境变量 FD_ENV_FILE；没设就是 None，不读文件
ENV_FILE = Path(os.environ["FD_ENV_FILE"]).expanduser() if os.environ.get("FD_ENV_FILE") else None
MIMO_VARS = ("MIMO_API_KEY", "MIMO_BASE_URL")
SECRET_VARS = ("MIMO_API_KEY",)          # 只有它是秘密；地址不是，但也只报主机名
HIDDEN = "<已隐藏>"


class KeyReadDenied(RuntimeError):
    """系统不让读 .env（权限或沙箱）。调用方据此停掉 MiMo 部分。"""


def load_local_env(wanted_keys=MIMO_VARS):
    """从 .env 读入指定变量（不输出值），返回 {变量名: 是否就位}。"""
    if all(os.environ.get(k) for k in wanted_keys):
        return {k: True for k in wanted_keys}
    if ENV_FILE is None:                      # 没设 FD_ENV_FILE：不读文件，只看环境变量
        return {k: bool(os.environ.get(k)) for k in wanted_keys}
    try:
        text = ENV_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {k: bool(os.environ.get(k)) for k in wanted_keys}
    except (PermissionError, OSError) as e:
        raise KeyReadDenied(f"读取 .env 被系统拒绝（{type(e).__name__}）") from None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        if k in wanted_keys and not os.environ.get(k):
            os.environ[k] = v.strip().strip('"').strip("'")
    del text
    return {k: bool(os.environ.get(k)) for k in wanted_keys}


def hide(text):
    """把文字里出现的密钥值换成 <已隐藏>。"""
    s = str(text)
    for name in SECRET_VARS:
        v = os.environ.get(name, "")
        if v and len(v) >= 6:
            s = s.replace(v, HIDDEN)
    return s


def install_excepthook():
    """未捕获异常的回溯先抹密钥再打印。"""
    def _hook(tp, val, tb):
        sys.stderr.write(hide("".join(traceback.format_exception(tp, val, tb))))
    sys.excepthook = _hook


def mimo_key_kind():
    """tp- 开头是 Token Plan，sk- 开头是按量付费；只看前缀，不碰其余部分。"""
    k = os.environ.get("MIMO_API_KEY", "")
    if not k:
        return "缺失"
    if k.startswith("tp-"):
        return "Token Plan（tp-）"
    if k.startswith("sk-"):
        return "按量付费（sk-）"
    return "未知前缀"


def mimo_base_host():
    """只报主机名，便于说明走的是哪条线路。"""
    b = os.environ.get("MIMO_BASE_URL", "")
    return urlparse(b).hostname or ("缺失" if not b else "无法解析")


def mimo_chat_url(base=None):
    """MIMO_BASE_URL（一般以 /v1 结尾）拼上 /chat/completions；已经带了就不重复。"""
    b = (base if base is not None else os.environ.get("MIMO_BASE_URL", "")).strip().rstrip("/")
    if not b:
        raise RuntimeError("没有 MIMO_BASE_URL")
    return b if b.endswith("/chat/completions") else b + "/chat/completions"


if __name__ == "__main__":
    install_excepthook()
    try:
        ok = load_local_env()
    except KeyReadDenied as e:
        print(f"✗ {e}")
        sys.exit(2)
    print("变量就位：", ok)
    print("密钥类型：", mimo_key_kind())
    print("地址主机：", mimo_base_host())
