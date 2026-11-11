"""fd run / fd status：按步骤表一步步跑、判断哪些做过了可以跳过、出错怎么接着跑。"""
import os
import re
import subprocess
import time
import traceback
from datetime import date
from pathlib import Path

from . import report
from .common import (DONE, FAILED, SKIPPED, WAITING, TODO, RUNNING, ROOT, PY, TESTDIR, DEFAULT_DB, DEFAULT_LEDGER, EDITIONS,
                     TOOLS, State, Lock, Busy, Proc, child_env, pick_edition, frozen_editions, stamp, iso, rel, fp_file,
                     write_json, motion_switch)
from .ledger import Ledger
from .steps import STEPS, BY_KEY, R, find_step


class Ctx:
    def __init__(self, a, dry_run):
        self.day = a.date
        try:
            date.fromisoformat(self.day)
        except ValueError:
            raise SystemExit("--date 要写成 YYYY-MM-DD，比如 2026-11-02")
        default = TESTDIR / self.day
        self.issue = Path(a.issue_dir).expanduser().resolve() if a.issue_dir else default
        self.default_issue = self.issue.resolve() == default.resolve()
        if self.issue.name != self.day:
            raise SystemExit("期目录的最后一级要是日期 %s（网页、视频组装都按目录名认日期）：%s" % (self.day, self.issue))
        self.edition = pick_edition(self.day, self.default_issue, getattr(a, "edition", None))
        self.ed = EDITIONS[self.edition]
        # 用 --issue-dir 时（测试、彩排），事件库和账本默认也放在期目录旁边，不碰正式的
        side = self.issue.parent
        self.db = Path(a.db).expanduser().resolve() if getattr(a, "db", None) else (DEFAULT_DB if self.default_issue else side / "往期事件库")
        led = getattr(a, "ledger_dir", None)
        self.ledger_dir = Path(led).expanduser().resolve() if led else (DEFAULT_LEDGER if self.default_issue else side / "月度账本")
        self.offline = bool(getattr(a, "offline", False))
        self.budget = 0.0 if self.offline else float(getattr(a, "budget_usd", 0.6) or 0)
        self.lenient = bool(getattr(a, "lenient", False))
        self.skip_images = bool(getattr(a, "skip_images", False))
        self.preview = not bool(getattr(a, "no_preview", False))
        self.force_backup = bool(getattr(a, "use_backup", False))
        self.verbose = bool(getattr(a, "verbose", False))
        self.redo = set()
        for x in (getattr(a, "redo", None) or "").split(","):
            if x.strip():
                self.redo.add(find_step(x).key)
        self.dry_run = dry_run
        self.state = State(self.issue, readonly=dry_run)
        self.ledger = Ledger(self.ledger_dir, self.issue, self.day, dry_run=dry_run)
        self.env = child_env(self.offline)
        self.logs = self.issue / "logs"
        self.run_id = time.strftime("%Y%m%d-%H%M%S")
        self.web_cfg = (TOOLS / "v3_issues" / ("%s.py" % self.day)) if self.default_issue else (self.issue / "10_网页配置.py")
        self.steps = BY_KEY
        self.proc = Proc(self)
        self.child = None
        self.args = a

    # ---- 给各步用的小工具
    def p(self, x):
        x = str(x)
        return Path(x) if os.path.isabs(x) else self.issue / x

    def py(self, *args):
        return [str(PY), "-u"] + [str(x) for x in args]

    def show(self, cmd):
        s = " ".join(str(x) for x in cmd)
        s = s.replace(str(PY) + " -u", "$PY")
        s = s.replace(str(self.issue), "<期目录>").replace(str(ROOT) + "/", "").replace(str(Path.home()), "~")
        return s

    def log_path(self, step):
        return self.logs / ("%02d_%s_%s.log" % (step.no, step.name, self.run_id))

    def run(self, step, cmd, label="", timeout=None, env=None):
        rc, out = self.proc.run(cmd, self.log_path(step), timeout=timeout or step.timeout, env=env, label=label)
        mark = "✓" if rc == 0 else "✗ 退出码 %s" % rc
        print("      %s %s" % (mark, label or ""), flush=True)
        return rc, out

    def quiet(self, cmd, timeout=120):
        try:
            r = subprocess.run([str(x) for x in cmd], cwd=str(ROOT), env=self.env, capture_output=True, text=True,
                               timeout=timeout, errors="replace")
            return r.returncode, (r.stdout or "") + (r.stderr or "")
        except (OSError, subprocess.TimeoutExpired) as e:
            return 1, str(e)

    def again(self):
        s = "./fd run --date %s" % self.day
        if not self.default_issue:
            s += " --issue-dir %s" % self.show([self.issue]).replace("<期目录>", str(self.issue).replace(str(Path.home()), "~"))
        if self.offline:
            s += " --offline"
        return s

    def record_extra(self, key, res, step):
        rec = dict(self.state.step(key) or {})
        rec.update({"状态": DONE, "怎么来的": "第 9 步改稿后复查通过", "结束": stamp(),
                    "输入指纹": step.input_fp(self), "产出指纹": step.output_fp(self)})
        self.state.set_step(key, rec)


# ---------------------------------------------------------------- 这一步要不要做
def diff_inputs(old, new):
    changed = []
    for k, v in new.items():
        # 11-07：新加的"=名字=值"一类输入（如第 14 步的"新动效"开关），值是空字符串就等于默认状态；
        # 老记录里没有这个键时不算上游变了（免得加了开关以后，往期一重跑就从第 14 步起全部重做）
        if v == "" and k not in old and not k.startswith("@") and "/" not in k and "." not in k:
            continue
        if old.get(k, None) != v:
            changed.append(Path(k).name if not k.startswith("@") else k[6:] + " 的产出")
    return changed


def evaluate(c, s):
    ok, why = s.applies(c)
    if not ok:
        return "na", why
    rec = c.state.step(s.key) or {}
    st = rec.get("状态")
    exist = s.outputs_exist(c)
    if s.key in c.redo:
        return "run", "按 --redo 重做"
    if s.always:
        return "run", "每次都写"
    if st == DONE:
        if not exist:
            return "run", "上次做完了，但产出不见了"
        if s.stale_rerun:
            changed = diff_inputs(rec.get("输入指纹") or {}, s.input_fp(c))
            if changed:
                return "run", "上游变了：" + "、".join(dict.fromkeys(changed))
        return "skip", "做过了（%s）" % (rec.get("结束") or "")[:16]
    if exist and s.adopt and st != FAILED:
        return "adopt", "产出已在（不是 fd 跑出来的，或者等人时补上了），检查一遍就采纳"
    if st == FAILED:
        return "run", "上次失败了，再试：" + (rec.get("说明") or "")[:50]
    if st == WAITING:
        return "run", "上次在等人，再看一遍"
    if st == SKIPPED:
        return "run", "上次跳过了，再看一遍"
    return "run", "还没做"


# ---------------------------------------------------------------- fd run
def header(c):
    print("fd run %s · %s" % (c.day, c.ed["名字"]))
    print("  期目录：%s%s" % (c.issue, "" if c.default_issue else "（--issue-dir，测试用）"))
    fz = frozen_editions().get(c.day)
    if fz and not c.default_issue and fz != c.edition:
        print("  提醒：%s 在冻结表里是 %s；要复现那一期，加 --edition %s（副本默认按星期几定版别，和 run_mimo.py 一样）" % (c.day, fz, fz))
    print("  事件库：%s；账本：%s" % (rel(c.db), rel(c.ledger_dir)))
    st = c.ledger.status()
    print("  本月 Gemini 已记 $%.2f / 上限 $%.2f（%.0f%%）%s" % (st["Gemini已记美元"], st["上限美元"], 100 * st["比例"],
                                                            "，到 90% 了：配音走 MiMo 备用" if st["到90%"] else ""))
    mode = []
    if c.offline:
        mode.append("离线：不联网、预算 $0，只用缓存")
    else:
        mode.append("这一期 Gemini 最多花 $%.2f" % c.budget)
    if c.lenient:
        mode.append("网页数字核不上时放宽（--lenient）")
    if c.skip_images:
        mode.append("缺图不等（--skip-images）")
    if c.dry_run:
        mode.append("只列计划，不动任何文件（--dry-run）")
    print("  " + "；".join(mode))
    on, why = motion_switch()
    print("  新动效和原文截图：%s（%s）" % ("开" if on else "关，视频按 11-06 以前的画法出、不截图", why))
    print()


def run_issue(a, dry_run=False):
    c = Ctx(a, dry_run)
    frozen = c.default_issue and c.day in frozen_editions()
    if frozen and not dry_run:
        raise SystemExit("%s 是已冻结的一期（测试版/%s），fd 不改它。要试就复制一份到缓存，用 --issue-dir 指过去。" % (c.day, c.day))
    first = find_step(a.from_step).no if a.from_step else 1
    last = find_step(a.until).no if a.until else STEPS[-1].no
    if first > last:
        raise SystemExit("--from 在 --until 后面了")
    header(c)
    if dry_run:
        return dry(c, first, last)
    c.issue.mkdir(parents=True, exist_ok=True)
    run_lock = Lock(c.issue, "run")
    try:
        run_lock.acquire()
    except Busy as e:
        info = e.args[0] if e.args else {}
        print("✗ 这一期已经有一个 fd run 在跑：进程 %s，%s 开始（%s）。这次不跑，免得两个一起写同一批文件。"
              % (info.get("进程号"), info.get("开始"), info.get("主机")))
        print("  确定那个已经不在了，就删掉锁文件再跑：%s" % run_lock.path)
        return 3
    if run_lock.note:
        print("  " + run_lock.note)
    c.state.data["运行记录"].append({"开始": stamp(), "命令": "fd " + " ".join(a.argv), "结果": RUNNING})
    c.state.save()
    outcome = {"停在": None, "原因": ""}
    try:
        for s in STEPS:
            if s.no < first or s.no > last:
                continue
            what, why = evaluate(c, s)
            tag = "[%2d/17] %s" % (s.no, s.name)
            if what == "na":
                print("%s：不适用（%s）" % (tag, why))
                continue
            if what == "skip":
                print("%s：%s（%s）" % (tag, DONE, why))
                continue
            print("%s：%s" % (tag, why), flush=True)
            r = run_one(c, s, what)
            print("      → %s：%s" % (r.status, r.msg), flush=True)
            for w in r.warns[:6]:
                print("        ! " + w)
            if len(r.warns) > 6:
                print("        ! ……还有 %d 条提醒，见报告" % (len(r.warns) - 6))
            if r.status in (FAILED, WAITING) and not r.go_on:
                outcome = {"停在": s.no, "原因": r.msg, "要你做": r.todo}
                if r.todo:
                    print()
                    for t in r.todo:
                        print("  " + t)
                break
    except KeyboardInterrupt:
        outcome = {"停在": None, "原因": "被中断（Ctrl-C）"}
        print("\n✗ 被中断")
    finally:
        try:
            path = report.write(c, outcome, first, last)
            print("\n报告：%s" % path)
        except Exception as e:     # noqa: BLE001  报告写不成也别把锁留下
            print("✗ 报告没写成：%s" % e)
        runs = c.state.data["运行记录"]
        runs[-1].update({"结束": stamp(), "结果": "停在第 %s 步：%s" % (outcome["停在"], outcome["原因"]) if outcome["停在"]
                         else (outcome["原因"] or "跑完")})
        c.state.save()
        run_lock.release()
    return 0 if not outcome["停在"] and not outcome["原因"] else (2 if outcome["停在"] else 1)


def run_one(c, s, how):
    lock = Lock(c.issue, "%02d_%s" % (s.no, s.key))
    try:
        lock.acquire()
    except Busy as e:
        info = e.args[0] if e.args else {}
        return R(FAILED, "第 %d 步正被另一个进程占着（进程 %s，%s 开始）" % (s.no, info.get("进程号"), info.get("开始")))
    t0 = time.time()
    how_label = {"run": "跑了", "adopt": "采纳已有产出"}.get(how, how)
    started = stamp()
    prev = c.state.step(s.key) or {}
    c.state.set_step(s.key, dict(prev, 状态=RUNNING, 开始=started, 怎么来的=how_label))
    r = R(FAILED, "被中断（Ctrl-C）")
    try:
        r = s.run(c, how)
    except SystemExit as e:
        r = R(FAILED, "程序停了：%s" % e)
    except Exception as e:      # noqa: BLE001
        c.logs.mkdir(parents=True, exist_ok=True)
        with open(c.log_path(s), "a", encoding="utf-8") as f:
            f.write("\n# fd 自己出错：\n" + traceback.format_exc())
        r = R(FAILED, "fd 在这一步出错：%s: %s（详情见日志）" % (type(e).__name__, e))
    finally:                      # Ctrl-C 也走到这里：记成失败、放掉锁
        logs = sorted(str(p.relative_to(c.issue)) for p in c.logs.glob("%02d_*_%s.log" % (s.no, c.run_id))) if c.logs.exists() else []
        ex = dict(r.extra)
        old_extra = dict(prev.get("附加") or {})
        if r.status != DONE and "没过时的产出指纹" not in ex and old_extra.get("没过时的产出指纹"):
            ex["没过时的产出指纹"] = old_extra["没过时的产出指纹"]
        rec = {"状态": r.status, "怎么来的": how_label, "开始": started, "结束": stamp(), "用时秒": round(time.time() - t0, 1),
               "说明": r.msg, "提醒": r.warns, "日志": logs, "附加": ex}
        if r.todo:
            rec["要你做"] = r.todo
        if r.go_on:
            rec["照常往下"] = True
        rec["输入指纹"] = s.input_fp(c)
        rec["产出指纹"] = s.output_fp(c)
        c.state.set_step(s.key, rec)
        lock.release()
    return r


# ---------------------------------------------------------------- --dry-run
def dry(c, first, last):
    total_est = 0.0
    for s in STEPS:
        if s.no < first or s.no > last:
            continue
        what, why = evaluate(c, s)
        tag = "[%2d/17] %s（%s）" % (s.no, s.name, s.who)
        label = {"skip": "跳过：" + why, "adopt": "采纳：" + why, "run": "要做：" + why, "na": "不适用：" + why}[what]
        print("%s\n      %s" % (tag, label))
        if what in ("run", "adopt"):
            for line in (s.plan(c) if what == "run" else s.plan_adopt(c)):
                print("      · " + line)
                if "估计花费" in line:
                    total_est += sum(float(x) for x in re.findall(r"\$([\d.]+)", line))
    print()
    print("估计这一次要花：Gemini 约 $%.3f（全部重配时的上限；缓存里有的不花钱）%s" % (
        total_est, "；离线模式实际是 $0" if c.offline else ""))
    print("（--dry-run 只读，没有写任何文件。）")
    return 0


# ---------------------------------------------------------------- fd status
def status(a):
    c = Ctx(a, dry_run=True)
    print("fd status %s · %s" % (c.day, c.ed["名字"]))
    print("  期目录：%s%s" % (c.issue, "" if c.issue.exists() else "（还不存在）"))
    runs = c.state.data.get("运行记录") or []
    if runs:
        r = runs[-1]
        print("  最近一次：%s 开始，%s；%s" % (r.get("开始"), ("结束 " + r["结束"]) if r.get("结束") else "还没结束", r.get("结果")))
    st = c.ledger.status()
    print("  本月 Gemini 已记 $%.2f / 上限 $%.2f（%.0f%%）；这一期 $%.3f" % (
        st["Gemini已记美元"], st["上限美元"], 100 * st["比例"], c.ledger.issue_total("Gemini")))
    print()
    print("  %-4s %-16s %-6s %s" % ("步", "做什么", "状态", "原因／说明"))
    for s in STEPS:
        rec = c.state.step(s.key) or {}
        lk = Lock(c.issue, "%02d_%s" % (s.no, s.key))
        li = lk.info()
        if li and lk.stale_reason(li) is None:
            stt, why = RUNNING, "进程 %s，%s 开始" % (li.get("进程号"), li.get("开始"))
        elif rec:
            stt = rec.get("状态") or TODO
            why = rec.get("说明") or ""
            if rec.get("结束"):
                why += "（%s，%s）" % (rec.get("怎么来的", ""), rec["结束"][5:16])
            if stt == RUNNING:
                stt, why = FAILED, "上次跑到一半就断了（进程已不在）"
        else:
            ok, na = s.applies(c)
            if not ok:
                stt, why = SKIPPED, "不适用：" + na
            elif s.outputs_exist(c) and s.outputs(c):
                stt, why = TODO, "产出已在，fd 还没检查过（下次 run 会检查后采纳）"
            else:
                stt, why = TODO, ""
        print("  %-4s %-16s %-6s %s" % (s.no, s.name, stt, why[:110]))
        if rec.get("要你做") and stt == WAITING:
            for t in rec["要你做"][:4]:
                print("         ↳ " + t[:120])
    miss = report.missing(c)
    if miss:
        print("\n  这一期少了：" + "；".join(miss))
    return 0
