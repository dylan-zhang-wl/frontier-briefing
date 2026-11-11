#!/usr/bin/env python3
"""云端最小试配：确认 GitHub Actions 用 Workload Identity 换来的令牌能调 Vertex 的 Gemini 配音（2026-11-08 晚加）。

只配一句很短的话（几个字，约 2 秒音频，按价目估不到 0.1 美分），用 Shirley 的主声音。
令牌从环境变量 GCP_ACCESS_TOKEN 读（workflow 里 google-github-actions/auth 给的，一小时有效），本程序不打印它。
项目照 pipeline/tts_engines.py 的 GCP_PROJECT；禁用项目的检查（check_project）照旧在 Gemini() 里做，这里不动。
花费按程序原来的记法记进当月账本（pipeline/orchestrator/ledger.py 的 Ledger.add）：钱数用 Vertex 返回的 token 数
按 tts_engines 的价目算（和配音缓存里每条的 cost_usd 同一算法）。这一条的"期目录"是 <期目录>/logs/云端试配，
不写进这一期的 花费.json（不然放行判定第 8 条会把它算成这一期的配音花费）。

用法（在仓库根目录，用项目环境的 Python）：
    ~/.venvs/frontier-daily/bin/python cloud/gemini_trial.py --date 2026-11-09
输出：<期目录>/logs/云端试配/试配.wav、usage.json；屏幕上一行结果。退出码 0 成功，1 失败。
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

import tts_engines as E                      # noqa: E402
from orchestrator.ledger import Ledger      # noqa: E402

TEXT = "云端试配，一切正常。"
STYLE = "calm and steady"
LIMIT_USD = 0.01


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--ledger-dir", default=str(ROOT / "测试版/月度账本"))
    a = ap.parse_args(argv)
    if not os.environ.get("GCP_ACCESS_TOKEN"):
        print("✗ 没有 GCP_ACCESS_TOKEN（取令牌那一步没成？）")
        return 1
    out = ROOT / "测试版" / a.date / "logs" / "云端试配"
    out.mkdir(parents=True, exist_ok=True)
    prof = json.loads((ROOT / "pipeline/voice_profile.json").read_text(encoding="utf-8")).get("主声音") or {}
    voice = prof.get("声音ID")
    model = {"lite": E.GEMINI_LITE, "flash": E.GEMINI_FLASH, None: E.GEMINI_FLASH}.get(prof.get("模型"), prof.get("模型"))
    g = E.Gemini()                              # 这里查禁用项目
    print("试配：项目 %s，模型 %s，声音 %s…，%d 个字" % (g.project, model, str(voice)[:14], len(TEXT)))
    t0 = time.time()
    try:
        wav, usage = g.synthesize(TEXT, voice, style=STYLE, model=model)
    except Exception as e:                      # noqa: BLE001  报错里不会有令牌（令牌只在请求头里）
        print("✗ 试配失败：%s: %s" % (type(e).__name__, str(e)[:400]))
        return 1
    (out / "试配.wav").write_bytes(wav)
    usage = dict(usage, 文本=TEXT, 项目=g.project, 时间=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    (out / "usage.json").write_text(json.dumps(usage, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    usd = float(usage.get("cost_usd") or 0)
    Ledger(a.ledger_dir, out, a.date).add(
        "云端试配·Gemini 身份", "Gemini", usd,
        "cloud/gemini_trial.py：Vertex 返回的 token 数按 tts_engines 价目算（同配音缓存每条的 cost_usd）",
        "GitHub Actions 上 Workload Identity 令牌验证，只配一句：%s" % TEXT)
    print("✓ 试配成功：音频 %.2f 秒，用时 %.1f 秒，输入 %s token、音频 %s token，估 $%.5f（已记进 %s）%s" % (
        usage["seconds_audio"], time.time() - t0, usage.get("prompt_tokens"), usage.get("audio_tokens_reported"),
        usd, Path(a.ledger_dir).name + "/" + time.strftime("%Y-%m") + ".json",
        "" if usd < LIMIT_USD else "；注意：超过 1 美分"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
