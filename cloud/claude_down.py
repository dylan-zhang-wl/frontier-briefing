#!/usr/bin/env python3
"""认出"Claude 不能用"（2026-11-17 加）：云端第 4–9 步写稿、审片那两次 claude -p 失败以后，看是不是登录失效或额度用完。
是的话写一份记号 Claude不能用.json（期目录根上），流程据此把这一步交给 MiMo 备用（仓库变量 FD_MIMO_BACKUP 写 on 才切）。
照 cloud/codex_login_check.py 的路子：分"原话"和"宽认"两档，屏幕上只印类别，不印对话内容，配单元测试。

依据（cloud/tests/claude_down_samples/ 里是本机实测、洗掉本机路径的样本；见改动清单 1.1–1.3）：
  本机用"假 Anthropic 接口"和故意填错的令牌跑 claude -p --output-format stream-json --verbose（命令行 2.1.321，11-17）：
    令牌过期（401）：assistant 一行顶层 "error": "authentication_failed"、"api_error_status": 401；
                     result 一行 "is_error": true、"api_error_status": 401。退出码 1。
    5 小时额度用完（429）：rate_limit_event 一行 rate_limit_info.status "rejected"、overageStatus "rejected"、resetsAt（秒）；
                     assistant 一行 "error": "rate_limit"、"api_error": "usage_limit_reached"；result 一行 "api_error": "usage_limit_reached"。退出码 1。
  退出码两种都是 1，别的错（overloaded、轮数用完）也是 1，所以只看结构字段，不看退出码、不只看文字。
  公开 issue anthropics/claude-code#103820（11-17 还开着）：长会话里额度用完时，上面三样可能一样都不出，退出码照样 1；
    那句话只留在命令行自己的会话记录 ~/.claude/projects/<目录>/<会话>.jsonl 里，是一条带 isApiErrorMessage 的 assistant。

认法：
  原话：stream-json 末尾那一段（从最后往前，直到一条正常的模型回答、一条成功的 result 或一条 user 为止）里有——
    登录失效：assistant 的 error 是 authentication_failed；或 result 的 is_error 为真、api_error_status 是 401。
    额度用完：assistant 或 result 的 api_error 是 usage_limit_reached；或 rate_limit_event 的 status 是 rejected、
              overageStatus 不是 allowed／allowed_warning。
    只看 assistant、result、rate_limit_event；system/api_retry 不算（重试中途的 401 后来可能好了）。
  宽认（stream-json 末尾没有上面那些字段时才看）：
    (a) 这一步开始以后改过的会话记录（--sessions 下面 */*.jsonl，最新那份）里最后一条 assistant 带 isApiErrorMessage，
        而且 error／apiError／apiErrorStatus 或文字是登录失效、额度用完那几种（#103820 那种情况）；
    (b) stderr 里有 "Failed to authenticate""OAuth token has expired／revoked""Please run /login""hit your … limit"
        "usage_limit_reached"。
  都没有：不是登录或额度的问题（overloaded、server_error、轮数或预算用完、超时被停、普通 429、403 账号被停之类），照旧报错。
  rate_limit_event 是 allowed_warning、用量 ≥0.95 只印一句"快满了"，不算。
  两档认出来都切备用（宽认算不算，改动清单第 7 节第 6 条要用户定；现在按协调方的交代两档都切，记号里写明是哪一档）。

这一步要的东西已经做完了的，不切（只印一句）：
  写稿：fd 第 4–9 步都"做完"，而且选题、播客稿、网页稿、审读意见都在、改稿有处理记录（或审读必须改 0 条）——
        Claude 是写完以后、写总结时才倒的（改动清单 2.2③）。只看 fd_state.json 不够：测试时会把稿子挪开、状态还写着做完。
  审片：审片结论.json 能读、有"放行""立即"——Claude 审完才倒的。

记号 Claude不能用.json（期目录根上；W1 的放行判定、邮件读它，字段不随便改）：
  {"原因": "登录失效"|"额度用完"|"其他", "认法": "原话"|"宽认", "哪一步": ["写稿"]|["审片"]|["写稿","审片"],
   "恢复时间": "ISO 时间（UTC）或空", "连续第几天": 整数, "自动放行": true|false, "写于": "UTC 时间",
   "各步": {"写稿": {"原因", "认法", "恢复时间", "写于"}, …}}
  写稿、审片两次都认出时合并成一份：哪一步按写稿、审片的顺序；原因两次一样就是它，不一样写"其他"（各步里有明细）；
  认法有一次是宽认就写宽认；恢复时间取最近一次认出的（没有就沿用）；连续第几天沿用第一次算的。
  连续第几天：从昨天往前一天一天看 <--history>/<日期>/Claude不能用.json 在不在；周六不出刊，跳过（不算一天，也不打断）；
    其余日子在就加 1，不在就停；最多往前看 14 天；今天算第 1 天。--history 默认是期目录的上一层（测试版/）。
  自动放行：环境变量 FD_MIMO_AUTORELEASE 写 true 才是 true，其余都是 false（仓库变量，要用户同意才设）。

用法：
  python cloud/claude_down.py --issue 测试版/<日期> --step 写稿|审片 --stream <stream-json 文件> --stderr <stderr 文件> \
      --rc <claude 的退出码> [--since <这一步开始的秒数>] [--sessions ~/.claude/projects] [--history 测试版] [--dry]
  --dry：只判断、只印一句，不写记号（仓库变量没开时流程这样跑：正式运行一个文件都不多写）。
退出码（给流程用）：
  10 认出了，要切备用（没加 --dry 时已写好记号）；
  11 认出了，但这一步的东西已经做完了，不切（不写记号）；
  0  没认出（不是登录或额度的问题，或者 claude 退出码本来就是 0）；
  其他（1 程序出错、2 参数不对）：流程按"没认出"处理，照旧报错。
测试：python3 -m unittest discover -s cloud/tests -v
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

LOGIN, QUOTA, OTHER = "登录失效", "额度用完", "其他"
EXACT, LOOSE = "原话", "宽认"
STEPS = ("写稿", "审片")
MARKER = "Claude不能用.json"
EXIT_DOWN, EXIT_DONE_ALREADY, EXIT_NO = 10, 11, 0
MAX_BACK = 14
SATURDAY = 5                       # date.weekday()：周一 0 … 周六 5
OVERAGE_OK = ("allowed", "allowed_warning")
SESSION_TAIL = 400                 # 会话记录只看最后这么多行

LOGIN_TEXT = re.compile(r"Failed to authenticate|OAuth (?:access )?token has (?:expired|been revoked)|Please run /login"
                        r"|authentication_error|authentication_failed", re.I)
QUOTA_TEXT = re.compile(r"hit your [^\n]{0,40}?limit|usage_limit_reached", re.I)
SESSION_LOGIN_START = ("Failed to authenticate",)
SESSION_QUOTA_START = ("You've hit your", "You’ve hit your")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_of(sec):
    """resetsAt（秒）→ ISO 时间（UTC）；读不出返回空字符串。"""
    try:
        return datetime.fromtimestamp(float(sec), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def read_lines(path):
    """jsonl 逐行解析，坏行跳过；文件不在返回 []。"""
    out = []
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except (OSError, TypeError):
        return out
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)
        except ValueError:
            continue
        if isinstance(o, dict):
            out.append(o)
    return out


def _resets(params):
    """api_error_params／apiErrorParams 里的 rate_limit_info.resetsAt。"""
    info = ((params or {}).get("rate_limit_info") or {}) if isinstance(params, dict) else {}
    return info.get("resetsAt")


def terminal_block(objs):
    """stream-json 末尾那一段：从最后往前，直到一条正常的模型回答、一条成功的 result 或一条 user（工具往返）为止。
    只留 assistant、result、rate_limit_event（system/api_retry 之类跳过，不算证据也不打断）。"""
    out = []
    for o in reversed(objs):
        t = o.get("type")
        if t == "user":
            break
        if t == "assistant":
            if not (o.get("error") or o.get("is_api_error_message")):
                break                       # 正常的模型回答：再往前的错误后来好了，不算
            out.append(o)
        elif t == "result":
            if not o.get("is_error"):
                break
            out.append(o)
        elif t == "rate_limit_event":
            out.append(o)
    return list(reversed(out))


def from_stream(objs):
    """原话：stream-json 末尾那一段的结构字段。返回 (原因, 恢复时间秒或 None) 或 None。"""
    login = quota = False
    resets = None
    for o in terminal_block(objs):
        t = o.get("type")
        if t == "assistant":
            if o.get("error") == "authentication_failed" or (o.get("is_api_error_message") and o.get("api_error_status") == 401):
                login = True
            if o.get("api_error") == "usage_limit_reached":
                quota = True
                resets = _resets(o.get("api_error_params")) or resets
        elif t == "result":
            if o.get("api_error_status") == 401:
                login = True
            if o.get("api_error") == "usage_limit_reached":
                quota = True
        elif t == "rate_limit_event":
            info = o.get("rate_limit_info") or {}
            if info.get("status") == "rejected" and info.get("overageStatus") not in OVERAGE_OK:
                quota = True
                resets = info.get("resetsAt") or resets
    if login:
        return LOGIN, None              # 两样都有时按登录失效（那个要你动手）
    if quota:
        return QUOTA, resets
    return None


def near_full(objs):
    """最后一条 rate_limit_event 是 allowed_warning、用量 ≥0.95：只印一句，不算。"""
    for o in reversed(objs):
        if o.get("type") == "rate_limit_event":
            info = o.get("rate_limit_info") or {}
            if info.get("status") != "allowed_warning":
                return False
            us = [float(w.get("utilization") or 0) for w in (info.get("unifiedWindows") or {}).values() if isinstance(w, dict)]
            us.append(float(info.get("utilization") or 0))
            return max(us) >= 0.95
    return False


def _text_of(entry):
    msg = entry.get("message") or {}
    parts = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(parts, list):
        return "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))
    return str(parts or "")


def from_session(sessions_dir, since):
    """宽认 (a)：这一步开始以后改过的会话记录里，最新那份的最后一条 assistant。返回 (原因, 恢复时间秒或 None) 或 None。"""
    if not sessions_dir:
        return None
    root = Path(sessions_dir).expanduser()
    if not root.is_dir():
        return None
    files = []
    for f in root.glob("*/*.jsonl"):
        try:
            m = f.stat().st_mtime
        except OSError:
            continue
        if since is None or m >= since:
            files.append((m, f))
    if not files:
        return None
    newest = max(files)[1]
    objs = read_lines(newest)[-SESSION_TAIL:]
    last = next((o for o in reversed(objs) if o.get("type") == "assistant"), None)
    if not last or not last.get("isApiErrorMessage"):
        return None
    text = _text_of(last).lstrip()
    if last.get("error") == "authentication_failed" or last.get("apiErrorStatus") == 401 or text.startswith(SESSION_LOGIN_START):
        return LOGIN, None
    if last.get("apiError") == "usage_limit_reached" or text.startswith(SESSION_QUOTA_START):
        return QUOTA, _resets(last.get("apiErrorParams"))
    return None


def from_stderr(text):
    """宽认 (b)：stderr 里的字。"""
    if LOGIN_TEXT.search(text or ""):
        return LOGIN, None
    if QUOTA_TEXT.search(text or ""):
        return QUOTA, None
    return None


def classify(objs, stderr_text, rc, sessions_dir=None, since=None):
    """返回 {"原因", "认法", "恢复时间"}，没认出返回 None。claude 退出码是 0 时一律不算。"""
    if str(rc).strip() in ("0", ""):
        return None
    got = from_stream(objs)
    if got:
        return {"原因": got[0], "认法": EXACT, "恢复时间": iso_of(got[1]) if got[1] else ""}
    for fn in (lambda: from_session(sessions_dir, since), lambda: from_stderr(stderr_text)):
        got = fn()
        if got:
            return {"原因": got[0], "认法": LOOSE, "恢复时间": iso_of(got[1]) if got[1] else ""}
    return None


# ---------------------------------------------------------------- 这一步的东西是不是已经做完了
WRITE_STEPS = ("select", "cards", "write", "check", "review", "revise")
DONE = "做完"


def writing_done(issue):
    """fd 第 4–9 步都"做完"，而且产出都在：选题、播客稿、网页稿、审读意见；审读必须改不是 0 时还要有审读处理*.md。"""
    d = Path(issue)
    try:
        st = json.loads((d / "logs" / "fd_state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    steps = (st or {}).get("步骤") or {}
    if any((steps.get(k) or {}).get("状态") != DONE for k in WRITE_STEPS):
        return False
    if not (d / "02_选题" / "最终选题.json").is_file() or not (d / "04_文稿" / "claude_网页.json").is_file():
        return False
    if not (list((d / "04_文稿").glob("claude_播客_*.md")) or list((d / "04_文稿").glob("claude_对谈_*.md"))):
        return False
    rv = d / "审读意见.md"
    if not rv.is_file():
        return False
    first = (rv.read_text(encoding="utf-8", errors="replace").splitlines() or [""])[0]
    if re.match(r"\s*必须改\s*[：:]\s*0\s*$", first):
        return True
    return bool(list(d.glob("审读处理*.md")))


def review_done(issue):
    """审片结论.json 能读、是一个对象、有"放行"和"立即"。"""
    try:
        o = json.loads((Path(issue) / "审片结论.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(o, dict) and "放行" in o and "立即" in o


# ---------------------------------------------------------------- 连续第几天、记号
def streak(history, day, max_back=MAX_BACK):
    """今天算第 1 天；从昨天往前看 history/<日期>/Claude不能用.json；周六跳过（不算、不打断）；最多往前看 max_back 天。"""
    n = 1
    d = date.fromisoformat(day)
    for i in range(1, max_back + 1):
        x = d - timedelta(days=i)
        if x.weekday() == SATURDAY:
            continue
        if (Path(history) / x.isoformat() / MARKER).is_file():
            n += 1
        else:
            break
    return n


def autorelease():
    return os.environ.get("FD_MIMO_AUTORELEASE", "").strip() == "true"


def merge(old, step, got, day, history):
    """把这一次认出的并进记号（old 是已有的记号或 None）。"""
    now = now_iso()
    each = dict((old or {}).get("各步") or {})
    each[step] = {"原因": got["原因"], "认法": got["认法"], "恢复时间": got["恢复时间"], "写于": now}
    steps = [s for s in STEPS if s in each]
    reasons = {v["原因"] for v in each.values()}
    resets = got["恢复时间"] or (old or {}).get("恢复时间") or ""
    mk = {
        "原因": reasons.pop() if len(reasons) == 1 else OTHER,
        "认法": LOOSE if any(v["认法"] == LOOSE for v in each.values()) else EXACT,
        "哪一步": steps,
        "恢复时间": resets,
        "连续第几天": int((old or {}).get("连续第几天") or streak(history, day)),
        "自动放行": autorelease(),
        "写于": now,
        "各步": each,
        "说明": "cloud/claude_down.py 写的：Claude 写稿／审片的 claude -p 失败，认出是登录失效或额度用完。不含对话内容。",
    }
    return mk


def line_for(step, got):
    """屏幕上那一句：只有类别、认法、预计几点恢复。"""
    s = "Claude 不能用（%s）：%s（%s）" % (step, got["原因"], got["认法"])
    if got["恢复时间"]:
        s += "，预计 %s UTC 恢复" % got["恢复时间"].replace("T", " ")[:16]
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--issue", required=True, help="期目录（测试版/<日期>）；记号写在它根上")
    ap.add_argument("--step", required=True, choices=STEPS)
    ap.add_argument("--stream", required=True, help="claude -p 的 stream-json 输出")
    ap.add_argument("--stderr", help="claude -p 的 stderr")
    ap.add_argument("--rc", required=True, help="claude -p 的退出码")
    ap.add_argument("--since", type=float, help="这一步开始的时刻（秒）：会话记录只看这以后改过的")
    ap.add_argument("--sessions", default="~/.claude/projects", help="命令行自己的会话记录目录（宽认用）")
    ap.add_argument("--history", help="往期目录（算连续第几天）；默认是期目录的上一层")
    ap.add_argument("--day", help="这一期的日期（默认取期目录的名字）")
    ap.add_argument("--dry", action="store_true", help="只判断、只印一句，不写记号")
    a = ap.parse_args(argv)
    issue = Path(a.issue)
    day = a.day or issue.name
    date.fromisoformat(day)                       # 日期不对就出错（退出码 1），流程照旧报错
    objs = read_lines(a.stream)
    try:
        err = Path(a.stderr).read_text(encoding="utf-8", errors="replace") if a.stderr else ""
    except OSError:
        err = ""
    if near_full(objs):
        print("Claude 用量快满了（最后一次用量提醒是 allowed_warning、≥95%），这一条只记一笔，不算不能用")
    got = classify(objs, err, a.rc, a.sessions, a.since)
    if not got:
        print("Claude（%s）退出码 %s：不是登录或额度的问题，照旧报错" % (a.step, a.rc))
        return EXIT_NO
    done = writing_done(issue) if a.step == "写稿" else review_done(issue)
    if done:
        print(line_for(a.step, got) + "；但%s已经做完了（%s），不切备用" % (
            "第 4–9 步" if a.step == "写稿" else "审片", "产出都在" if a.step == "写稿" else "审片结论.json 能读"))
        return EXIT_DONE_ALREADY
    print(line_for(a.step, got))
    if a.dry:
        print("（只判断，没写记号：仓库变量 FD_MIMO_BACKUP 没开，这一步照旧报错）")
        return EXIT_DOWN
    p = issue / MARKER
    try:
        old = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except ValueError:
        old = None
    mk = merge(old if isinstance(old, dict) else None, a.step, got, day, a.history or str(issue.parent))
    issue.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(mk, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    json.loads(p.read_text(encoding="utf-8"))     # 写完再读一遍
    print("记号写好了：%s（哪一步 %s，连续第 %d 天，自动放行 %s）" % (
        MARKER, "、".join(mk["哪一步"]), mk["连续第几天"], "开" if mk["自动放行"] else "关"))
    return EXIT_DOWN


if __name__ == "__main__":
    sys.exit(main())
