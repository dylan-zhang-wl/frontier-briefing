"""frontier-daily 的大模型调用：小米 MiMo（OpenAI 兼容接口）。

密钥规则：只从环境变量 MIMO_API_KEY、MIMO_BASE_URL 读取。本机测试时用 load_local_env()
从本机 .env（位置只看环境变量 FD_ENV_FILE，没设就不读）读入这两个变量，绝不输出它们的值。
只允许 mimo-v2.6 一代（用户 2026-10-14 规定）。
"""
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

import certifi

# uv 装的独立 Python 不带系统证书，用 certifi 的证书库，否则 HTTPS 会报证书校验失败
_SSL = ssl.create_default_context(cafile=certifi.where())

# 本机 .env 的位置：只看环境变量 FD_ENV_FILE；没设就是 None，不读文件
ENV_FILE = Path(os.environ["FD_ENV_FILE"]).expanduser() if os.environ.get("FD_ENV_FILE") else None
FLASH = "mimo-v2.6-flash"
PRO = "mimo-v2.6-pro"


def load_local_env(wanted_keys=("MIMO_API_KEY", "MIMO_BASE_URL")):
    """从本机 .env（FD_ENV_FILE）读取所需变量注入环境（不输出值），返回各变量是否已就位。"""
    if ENV_FILE is not None and ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().removeprefix("export ").strip()
            if k in wanted_keys and not os.environ.get(k):
                os.environ[k] = v.strip().strip('"').strip("'")
    return {k: bool(os.environ.get(k)) for k in wanted_keys}


def _hide(text):
    key = os.environ.get("MIMO_API_KEY", "")
    return text.replace(key, "<已隐藏>") if key else text


def chat(model, system, user, max_tokens=8000, temperature=0.3, timeout=600, retries=3):
    """返回 {"content", "usage", "seconds", "model"}；失败抛 RuntimeError（信息里不含密钥）。"""
    if not str(model).startswith("mimo-v2.6"):
        raise ValueError(f"不允许使用旧模型 {model}，请用 {FLASH} 或 {PRO}")
    key, base = os.environ.get("MIMO_API_KEY", ""), os.environ.get("MIMO_BASE_URL", "")
    if not key or not base:
        raise RuntimeError("没有 MiMo 密钥（MIMO_API_KEY、MIMO_BASE_URL）")
    payload = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    req_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = base.rstrip("/") + "/chat/completions"
    last = ""
    for attempt in range(retries):
        t0 = time.time()
        req = urllib.request.Request(url, data=req_body, method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
                data = json.loads(r.read().decode("utf-8"))
            ch = data["choices"][0]
            if ch.get("finish_reason") == "content_filter":
                raise RuntimeError("MiMo 内容过滤，拒绝生成")
            return {"content": (ch["message"].get("content") or "").strip(),
                    "usage": data.get("usage", {}), "seconds": round(time.time() - t0, 1),
                    "model": model, "finish": ch.get("finish_reason")}
        except urllib.error.HTTPError as e:
            last = _hide(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(20 * (attempt + 1))
                continue
            raise RuntimeError(last) from None
        except (urllib.error.URLError, TimeoutError) as e:
            last = _hide(f"{e.__class__.__name__}: {str(e)[:200]}")
            if attempt < retries - 1:
                time.sleep(15 * (attempt + 1))
                continue
            raise RuntimeError(last) from None
    raise RuntimeError(last or "MiMo 调用失败")


def parse_json(text):
    """去掉代码块围栏后解析 JSON；模型偶尔在前后加说明文字，取第一个完整的 { … }。"""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        s, e = t.find("{"), t.rfind("}")
        if s >= 0 and e > s:
            return json.loads(t[s:e + 1])
        raise


def chat_json(model, system, user, **kw):
    """要求只输出 JSON；解析失败时补一句提醒再试一次。"""
    r = chat(model, system, user, **kw)
    try:
        return parse_json(r["content"]), r
    except (json.JSONDecodeError, ValueError):
        r2 = chat(model, system, user + "\n\n（再次提醒：只输出一个合法的 JSON 对象，不要任何说明文字。）", **kw)
        return parse_json(r2["content"]), r2
