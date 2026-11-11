"""花费账本：每期一份 <期目录>/花费.json，每月一份 <账本目录>/<年-月>.json，按服务分开记（Gemini、MiMo、Codex、Claude）。

钱数不自己估：一律从各步产出的 usage.json 读（配音程序写的"其中本次新花费美元"）。那一步中途失败、usage.json 没写成时，
从配音缓存里这一步期间新写的每条记录（~/.cache/frontier-daily/tts/chunks/*.json 的 cost_usd）加起来补记，并注明。
MiMo 现在免费，只记 token 数；Codex（ChatGPT 订阅）、Claude（订阅，会话里写）只记次数和说明，钱记 0。
"""
import fcntl
import os
from contextlib import contextmanager
from pathlib import Path

from .common import CACHE, read_json, write_json, iso, now_utc, monthly_cap, rel

SERVICES = ("Gemini", "MiMo", "Codex", "Claude")
CHUNKS = CACHE / "tts" / "chunks"


@contextmanager
def _flock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def month_key(dt=None):
    return (dt or now_utc()).strftime("%Y-%m")


class Ledger:
    def __init__(self, ledger_dir, issue, day, dry_run=False):
        self.dir = Path(ledger_dir)
        self.issue = Path(issue)
        self.day = day
        self.dry_run = dry_run
        self.month = month_key()
        self.month_file = self.dir / ("%s.json" % self.month)
        self.issue_file = self.issue / "花费.json"

    # ---- 读
    def month_data(self):
        d = read_json(self.month_file, None) or {}
        d.setdefault("条目", [])
        return d

    def month_total(self, service="Gemini"):
        return round(sum(float(e.get("美元") or 0) for e in self.month_data()["条目"] if e.get("服务") == service), 4)

    def issue_data(self):
        d = read_json(self.issue_file, None) or {}
        d.setdefault("条目", [])
        return d

    def issue_total(self, service="Gemini"):
        return round(sum(float(e.get("美元") or 0) for e in self.issue_data()["条目"] if e.get("服务") == service), 4)

    def cap(self):
        return monthly_cap()

    def status(self):
        cap = self.cap()
        spent = self.month_total("Gemini")
        return {"本月": self.month, "Gemini已记美元": spent, "上限美元": cap,
                "比例": (spent / cap) if cap else 0.0, "账本": str(self.month_file),
                "到90%": cap > 0 and spent >= 0.9 * cap}

    # ---- 写
    def add(self, step, service, usd=0.0, source="", note="", **extra):
        if self.dry_run:
            return None
        e = {"时间": iso(), "期": self.day, "期目录": str(self.issue), "步骤": step, "服务": service,
             "美元": round(float(usd or 0), 5), "数从哪来": source}
        if note:
            e["说明"] = note
        e.update({k: v for k, v in extra.items() if v is not None})
        with _flock(self.month_file):
            m = self.month_data()
            m["月份"] = self.month
            m["上限美元（Gemini 配音）"] = self.cap()
            m["说明"] = ("fd 记的本月花费，一条一笔；钱数都从各步的 usage.json 读。只有经 fd 跑的才在这里："
                       "fd 上线前手动跑的（10-31、11-01 和各轮配音测试）没记进来。")
            m["条目"].append(e)
            m["合计美元"] = {s: round(sum(float(x.get("美元") or 0) for x in m["条目"] if x.get("服务") == s), 4)
                         for s in SERVICES}
            write_json(self.month_file, m)
        d = self.issue_data()
        d["期"] = self.day
        d["说明"] = "这一期经 fd 跑的花费，一条一笔；月度合计见 %s" % rel(self.month_file)
        d["条目"].append(e)
        d["合计美元"] = {s: round(sum(float(x.get("美元") or 0) for x in d["条目"] if x.get("服务") == s), 4)
                     for s in SERVICES}
        write_json(self.issue_file, d)
        return e


def usage_new_spend(usage_path, since_ts):
    """读一份配音 usage.json 里"这次新花的钱"。文件在 since_ts 之后写过才算（不然是上一次的数）。返回 (美元, 说明) 或 None。"""
    p = Path(usage_path)
    try:
        if p.stat().st_mtime < since_ts - 1:
            return None
    except OSError:
        return None
    u = read_json(p, {}) or {}
    tot = u.get("合计") or (u.get("配音") or {}).get("合计") or {}
    if "其中本次新花费美元" in tot:
        return float(tot.get("其中本次新花费美元") or 0), "%s 的 合计.其中本次新花费美元" % rel(p)
    return None


def chunk_spend_since(since_ts):
    """配音缓存里 since_ts 之后新写的 Gemini 条目，把各条自己记的 cost_usd 加起来（usage.json 没写成时补记用）。"""
    total, n = 0.0, 0
    if not CHUNKS.is_dir():
        return 0.0, 0
    with os.scandir(CHUNKS) as it:
        for e in it:
            if not e.name.endswith(".json"):
                continue
            try:
                if e.stat().st_mtime < since_ts - 1:
                    continue
            except OSError:
                continue
            meta = read_json(e.path, {}) or {}
            if str(meta.get("engine", "")).startswith("gemini"):
                total += float(meta.get("cost_usd") or 0)
                n += 1
    return round(total, 5), n


def mimo_tokens_since(usage_path, since_iso):
    """03_事件卡/mimo_用量.json 里这一步新做的卡用了多少 token。"""
    u = read_json(usage_path, {}) or {}
    tok, calls = 0, 0
    for _, c in (u.get("cards") or {}).items():
        if str(c.get("at") or "") >= since_iso:
            tok += int(((c.get("usage") or {}).get("total_tokens")) or 0)
            calls += 1
    return tok, calls
