#!/usr/bin/env python3
"""只印这一期 17 步各自的状态（做完／失败／跳过……），不印"原因／说明"（2026-11-11 加）。

为什么要它：拆成公开、私有两个仓库以后，公开仓库的运行日志、运行摘要谁都能看。`./fd status` 每一步后面的"原因／说明"
可能带选题、稿子、事件卡里的字，所以公开流程（.github/workflows/frontier-daily.yml）里改用这个：只读 logs/fd_state.json，
只印步号、步名、状态，和最近一次运行的开始、结束时间。步名表用 gate.py 的 STEPS（和放行判定同一份）。

用法：python cloud/release/steps_brief.py 测试版/<日期>
没有 fd_state.json 也不报错（退出码 0），只说一句"还没有"。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate  # noqa: E402


def brief(issue):
    """返回几行字。"""
    try:
        st = json.loads((Path(issue) / "logs" / "fd_state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["（%s 还没有 logs/fd_state.json）" % Path(issue).name]
    steps = st.get("步骤") or {}
    last = (st.get("运行记录") or [{}])[-1]
    out = ["最近一次运行：%s 开始，%s" % (last.get("开始") or "?", ("结束 " + last["结束"]) if last.get("结束") else "还没结束")]
    for i, (key, name) in enumerate(gate.STEPS, 1):
        out.append("  %2d %s：%s" % (i, name, (steps.get(key) or {}).get("状态") or "没做"))
    return out


if __name__ == "__main__":
    print("\n".join(brief(sys.argv[1] if len(sys.argv) > 1 else ".")))
