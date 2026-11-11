#!/usr/bin/env python3
"""放行判定：这一期能不能自动发布到 wenlongzhang.com/frontier/。

按 文档/历史/全流程梳理_2026-11-08.md 第四节“‘没发现问题’用机器能判的条件写”的 9 条逐条判，全部满足才放行；
第 4 条按用户 11-08 晚的决定：因为月上限（花费上限）换成备用声音的照常放行，邮件里注明。

用法（在仓库根目录）：
    python cloud/release/gate.py --issue 测试版/2026-11-09
      --ledger-dir  月度账本目录（默认 <期目录>/../月度账本，即 测试版/月度账本）
      --profile     声音档案（默认 pipeline/voice_profile.json，读每月上限；月度账本里写了上限就以账本为准）
      --manual 说明  人工放行（用户在 GitHub 网页上手动运行“放行”）：照样逐条判、照样写结论，但不管判没判过都放行
      --out         结论写到哪（默认 <期目录>/放行结论.json）
      --check-made  只看这一期出刊了没有（跑完到第 17 步），不判放行：出了退出码 0，没出 1
退出码：0 放行，1 不放行，2 期目录不存在或参数不对（也是不放行）。

每条读哪个文件、哪个字段，都按 pipeline/orchestrator/ 的代码核过（行号见 文档/历史/发布与放行报告_2026-11-08.md 第 4 节）：
    1  logs/fd_state.json   步骤.<17 步>.状态 全是“做完”；唯一例外：第 10 步配图“跳过”（--skip-images，网页用程序画的封面）
    2  logs/验收.json        “没过”是空列表（steps.py Accept.run 写的）
    3  logs/fd_state.json   步骤.voice.附加.播客／视频旁白 不是“没配成”；步骤.web.附加.播客 不是“无”；步骤.web2.附加.带视频 为真
    4  logs/fd_state.json   步骤.voice.附加.决定（用备用、原因）、.播客、.视频旁白；05_配音/视频旁白_v3/voice.json 的 engine；
                            播客人声目录 usage.json 的“引擎”。用了 MiMo 备用：原因是花费上限（“本月 Gemini 已记…到上限”“剩下的钱不够”）
                            或命令行指定（--use-backup）→ 过、记备注；其余（主声音出错后换的、查不到原因）→ 不过
    5  logs/fd_state.json   运行记录.命令：做第 13 步网页组装的那次运行没带 --lenient；第 4、7、9 步的“放宽”只记备注
                            （steps.py 只有全是软规则时才会写“放宽”，硬的会停下等人，所以“放宽”本身不挡）
    6  00_调度报告.md        标题行“# 日期 · 版别 · 调度报告”：日期对、版别和星期几对得上（周一到周五工作日版、周六周六版、周日周日版）；
                            审片结论.json 的“版别”写了的话也要对得上
    7  11_视频v3/video3_media.json 的 duration ≤ 180 秒；播客人声目录 qc.json 的 整集.时长把关.配完按实际.通过 为真
    8  花费.json 合计美元.Gemini ≤ 这一期预算（那次运行的 --budget-usd，默认 0.6）；月度账本 <年-月>.json 的 Gemini 合计 ≤ 每月上限
    9  审片结论.json         有、能读、日期对、“放行”为 true、“立即”为空；“请你耳听”不挡、记备注。缺失＝不放行
只读期目录，只写放行结论一个文件。不调用模型、不联网。

“请你耳听”的分拣（11-10 加，用户同意）：审片给每条写“判断”（多半真念错／多半转写听错）和一句“依据”，原样记进备注。
它只管发不发邮件，不管放不放行。哪些备注要告诉你（listen_kind、split_notes）写在这里，notify.py 也用这两个函数，两边一样：
备用声音、配图退回、不是“多半转写听错”的请你耳听要告诉你；旧格式没写“判断”、写的认不出，一律当“多半真念错”（宁可多发）。
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
STEPS = [("fetch", "抓取"), ("cluster", "粗筛归并"), ("ingest", "事件库入库"), ("select", "选题"), ("cards", "事件卡"),
         ("write", "写稿"), ("check", "稿子检查"), ("review", "独立审读"), ("revise", "改稿"), ("images", "配图"),
         ("voice", "配音"), ("mix", "混音"), ("web", "网页组装"), ("video", "视频"), ("web2", "网页带视频再组装"),
         ("accept", "验收"), ("report", "写本期报告")]
DONE, SKIPPED = "做完", "跳过"
EDITIONS = {"weekday": ("工作日版", "工作日"), "saturday_deep": ("周六版", "周六"), "sunday_deep": ("周日版", "周日")}
HUMAN_DIR = {"weekday": "05_配音/播客_v3", "saturday_deep": "05_配音/周六_人声", "sunday_deep": "05_配音/周日深谈_人声"}
VIDEO_VOICE = "05_配音/视频旁白_v3/voice.json"
VIDEO_MAX = 180.0
DEFAULT_BUDGET = 0.6           # pipeline/orchestrator/cli.py --budget-usd 的默认值
DEFAULT_CAP = 8.0              # pipeline/orchestrator/common.py monthly_cap() 读不到时的默认值
CAP_REASON = re.compile(r"本月 Gemini 已记|到上限|剩下的钱不够")
MANUAL_REASON = "命令行要求用备用"
TITLES = {1: "17 步全部做完（配图退回程序封面除外）", 2: "第 16 步验收过了", 3: "不是数据版：播客、视频旁白都配成了",
          4: "没有因为出错换成备用声音（因花费上限换的照常放行）", 5: "网页没用 --lenient；放宽只限软规则",
          6: "版别和星期几对得上", 7: "视频不超过 180 秒，播客时长在区间里", 8: "这一期、这个月的花费没超",
          9: "审片跑完了，结论是放行，“立即”为空"}
LISTEN = "请你耳听"
LISTEN_REAL, LISTEN_ASR = "多半真念错", "多半转写听错"
MAIL_KINDS = ("备用声音", "配图退回", LISTEN)      # 已放行的那期有这几类备注才发邮件；“其他”（软规则放宽）不发


def listen_kind(x):
    """一条“请你耳听”（审片结论里的一项，或放行结论“备注”里的一条）算哪一类：
    “判断”写的是“多半转写听错”才算转写的毛病；没写（旧格式）、写错、不是字典，一律当“多半真念错”。"""
    j = x.get("判断") if isinstance(x, dict) else None
    return LISTEN_ASR if isinstance(j, str) and j.strip() == LISTEN_ASR else LISTEN_REAL


def listen_classified(x):
    """审片写了认得出的“判断”没有（旧格式没写、写的不是那两种，都返回 False）。"""
    j = x.get("判断") if isinstance(x, dict) else None
    return isinstance(j, str) and j.strip() in (LISTEN_REAL, LISTEN_ASR)


def split_notes(notes):
    """把放行结论的“备注”分成 (要告诉你的, 多半转写听错的请你耳听)。
    要告诉你的：备用声音、配图退回，加上不是“多半转写听错”的请你耳听（旧格式没写判断的也算）；“其他”两边都不进。
    “给人看”那段话和 notify.py 的邮件都按这个分。"""
    tell, asr = [], []
    for n in notes or []:
        k = n.get("类") if isinstance(n, dict) else None
        if k == LISTEN and listen_kind(n) == LISTEN_ASR:
            asr.append(n)
        elif k in MAIL_KINDS:
            tell.append(n)
    return tell, asr


def listen_note(x):
    """审片结论“请你耳听”的一项 → 放行结论的一条备注。审片写了“判断”“依据”就原样带上（去掉首尾空白），没写就不加。"""
    if not isinstance(x, dict):
        return {"类": LISTEN, "说明": str(x)}
    n = {"类": LISTEN, "说明": "%s：%s" % (x.get("位置", ""), x.get("说明", ""))}
    for k in ("判断", "依据"):
        if x.get(k) not in (None, ""):
            n[k] = str(x[k]).strip()
    return n


def usd(x):
    """钱数：至少两位小数，多的位数照写（0.3552 不写成 0.36）。"""
    s = ("%.4f" % float(x)).rstrip("0")
    return "$" + (s + "0" * (2 - len(s.split(".")[1])) if "." in s else s + ".00")


def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def edition_of(day):
    wd = date.fromisoformat(day).weekday()
    return "saturday_deep" if wd == 5 else "sunday_deep" if wd == 6 else "weekday"


def parse_stamp(s):
    """fd 记的时间："2026-11-08 05:42:31 GMT"。"""
    try:
        return datetime.strptime(str(s).replace(" GMT", ""), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def run_of(state, step_rec):
    """这一步是哪一次 ./fd run 做的：开始时间落在哪次运行的起止之间。找不到返回 None。"""
    t = parse_stamp((step_rec or {}).get("开始"))
    if not t:
        return None
    best = None
    for r in state.get("运行记录") or []:
        a, b = parse_stamp(r.get("开始")), parse_stamp(r.get("结束"))
        if a and a <= t and (b is None or t <= b):
            best = r
    return best


class Gate:
    def __init__(self, issue, ledger_dir=None, profile=None):
        self.issue = Path(issue)
        self.day = self.issue.name
        self.ed = edition_of(self.day)
        self.state = read_json(self.issue / "logs" / "fd_state.json")
        self.steps = (self.state or {}).get("步骤") or {}
        self.ledger_dir = Path(ledger_dir) if ledger_dir else self.issue.parent / "月度账本"
        self.profile = Path(profile) if profile else REPO / "pipeline" / "voice_profile.json"
        self.results = []

    def st(self, key):
        return self.steps.get(key) or {}

    def ex(self, key):
        return self.st(key).get("附加") or {}

    def add(self, no, ok, why, evidence, notes=None):
        self.results.append({"编号": no, "条件": TITLES[no], "过": bool(ok), "说明": why, "证据": evidence,
                             "备注": notes or []})

    # ---------------------------------------------------------------- 1
    def c1(self):
        ev = ["logs/fd_state.json 步骤.<17 步>.状态"]
        if self.state is None:
            return self.add(1, False, "没有 logs/fd_state.json（这一期没跑或文件坏了）", ev)
        bad, notes = [], []
        for i, (k, name) in enumerate(STEPS, 1):
            s = self.st(k).get("状态")
            if s == DONE:
                continue
            if k == "images" and s == SKIPPED:
                ex = self.ex("images")
                notes.append({"类": "配图退回", "说明": "配图退回程序画的封面（缺网页图：%s；缺视频图：%s）" % (
                    "、".join(ex.get("缺网页配图") or []) or "无", "、".join(ex.get("缺视频配图") or []) or "无")})
                continue
            bad.append("第 %d 步%s：%s" % (i, name, s or "没有记录"))
        if bad:
            return self.add(1, False, "；".join(bad), ev, notes)
        self.add(1, True, "17 步都是“做完”" + ("（第 10 步配图跳过，用程序画的封面）" if notes else ""), ev, notes)

    # ---------------------------------------------------------------- 2
    def c2(self):
        ev = ["logs/验收.json 没过"]
        a = read_json(self.issue / "logs" / "验收.json")
        if a is None:
            return self.add(2, False, "没有 logs/验收.json（第 16 步没做）", ev)
        if "没过" not in a:
            return self.add(2, False, "logs/验收.json 里没有“没过”这一栏，读不懂", ev)
        if a["没过"]:
            return self.add(2, False, "验收没过 %d 项：%s" % (len(a["没过"]), "；".join(map(str, a["没过"][:3]))), ev)
        self.add(2, True, "验收全过（三种视图无报错、上标不掉行、听这一段正常）", ev)

    # ---------------------------------------------------------------- 3
    def c3(self):
        ev = ["logs/fd_state.json 步骤.voice.附加.播客／视频旁白", "步骤.web.附加.播客", "步骤.web2.附加.带视频"]
        v, w, w2 = self.ex("voice"), self.ex("web"), self.ex("web2")
        bad = []
        if not self.st("voice"):
            bad.append("没有第 11 步配音的记录")
        if v.get("播客") == "没配成":
            bad.append("播客没配成")
        if v.get("视频旁白") == "没配成":
            bad.append("视频旁白没配成")
        if w.get("播客", "无") == "无":
            bad.append("网页没挂播客")
        if w2.get("带视频") is not True:
            bad.append("网页没带视频")
        if bad:
            return self.add(3, False, "这一期是数据版：" + "；".join(bad), ev)
        self.add(3, True, "播客（%s）、视频都在网页上" % w.get("播客"), ev)

    # ---------------------------------------------------------------- 4
    def c4(self):
        human = HUMAN_DIR.get(self.ed, HUMAN_DIR["weekday"])
        ev = ["logs/fd_state.json 步骤.voice.附加.决定／播客／视频旁白", VIDEO_VOICE + " engine", human + "/usage.json 引擎"]
        v = self.ex("voice")
        d = v.get("决定") or {}
        vj = read_json(self.issue / VIDEO_VOICE) or {}
        uj = read_json(self.issue / human / "usage.json") or {}
        pod_mimo = str(v.get("播客", "")).startswith("MiMo") or "mimo" in str(uj.get("引擎", "")).lower()
        vid_mimo = str(v.get("视频旁白", "")).startswith("MiMo") or str(vj.get("engine", "")).lower() == "mimo"
        if not (pod_mimo or vid_mimo):
            return self.add(4, True, "播客、视频旁白都是主声音（Gemini）", ev)
        which = "、".join(x for x, y in (("播客", pod_mimo), ("视频旁白", vid_mimo)) if y)
        why = str(d.get("原因") or "")
        if d.get("用备用") and CAP_REASON.search(why):
            return self.add(4, True, "%s用了 MiMo 备用声音，原因是花费上限（%s），照常放行" % (which, why), ev,
                            [{"类": "备用声音", "说明": "%s是备用声音（MiMo 复刻），因为花费上限：%s" % (which, why)}])
        if d.get("用备用") and why == MANUAL_REASON:
            return self.add(4, True, "%s用了 MiMo 备用声音，是运行时人为指定的（--use-backup），不是出错" % which, ev,
                            [{"类": "备用声音", "说明": "%s是备用声音（MiMo 复刻），运行时用 --use-backup 指定的" % which}])
        if not d:
            return self.add(4, False, "%s用了 MiMo 备用声音，但记录里查不到为什么换（配音是沿用已有的），按出错算" % which, ev)
        return self.add(4, False, "%s因为主声音（Gemini）出错换成了 MiMo 备用声音" % which, ev)

    # ---------------------------------------------------------------- 5
    def c5(self):
        ev = ["logs/fd_state.json 运行记录.命令（做第 13 步的那次）", "步骤.select／check／revise.说明"]
        if self.state is None:
            return self.add(5, False, "没有 logs/fd_state.json", ev)
        web = self.st("web")
        r = run_of(self.state, web)
        if r is not None:
            lenient = "--lenient" in str(r.get("命令", ""))
            where = "做第 13 步的那次运行（%s）" % r.get("开始")
        else:                                           # 对不上时间就保守：任何一次带过 --lenient 都算
            lenient = any("--lenient" in str(x.get("命令", "")) for x in self.state.get("运行记录") or [])
            where = "运行记录（对不上第 13 步是哪次跑的，按任何一次带过都算）"
        if lenient:
            return self.add(5, False, "网页用了 --lenient（核不上的数字去掉了照常出）：%s" % where, ev)
        notes = []
        for k, name in (("select", "第 4 步选题"), ("check", "第 7 步稿子检查"), ("revise", "第 9 步改稿")):
            msg = str(self.st(k).get("说明") or "")
            if "放宽" in msg:
                notes.append({"类": "其他", "说明": "%s放宽了软规则：%s" % (name, msg[:120])})
        self.add(5, True, "网页没用 --lenient" + ("；有放宽，但都是长短、条数、首次补中文这类软规则" if notes else "；没有放宽"), ev, notes)

    # ---------------------------------------------------------------- 6
    def c6(self):
        ev = ["00_调度报告.md 标题行", "审片结论.json 版别"]
        p = self.issue / "00_调度报告.md"
        try:
            first = p.read_text(encoding="utf-8").splitlines()[0]
        except (OSError, IndexError):
            return self.add(6, False, "没有 00_调度报告.md", ev)
        m = re.match(r"^#\s*(\d{4}-\d{2}-\d{2})\s*·\s*(.+?)\s*·\s*调度报告", first)
        if not m:
            return self.add(6, False, "调度报告标题行读不懂：%s" % first[:60], ev)
        want, key = EDITIONS[self.ed]
        wd = "星期" + "一二三四五六日"[date.fromisoformat(self.day).weekday()]
        if m.group(1) != self.day:
            return self.add(6, False, "调度报告写的是 %s，不是 %s" % (m.group(1), self.day), ev)
        if not m.group(2).startswith(want):
            return self.add(6, False, "%s是%s，应该出%s，调度报告写的是“%s”" % (self.day, wd, want, m.group(2)), ev)
        rv = read_json(self.issue / "审片结论.json") or {}
        ved = str(rv.get("版别") or "").strip()
        if ved and ved not in ("…", "...") and key not in ved:
            return self.add(6, False, "审片结论写的版别“%s”和%s（%s）对不上" % (ved, want, wd), ev)
        self.add(6, True, "%s是%s，出的是%s" % (self.day, wd, m.group(2)), ev)

    # ---------------------------------------------------------------- 7
    def c7(self):
        human = HUMAN_DIR.get(self.ed, HUMAN_DIR["weekday"])
        ev = ["11_视频v3/video3_media.json duration", human + "/qc.json 整集.时长把关.配完按实际"]
        bad, parts = [], []
        vm = read_json(self.issue / "11_视频v3" / "video3_media.json") or {}
        dur = vm.get("duration")
        if dur is None:
            m = re.search(r"([\d.]+) 秒", str(self.st("video").get("说明") or ""))
            dur = float(m.group(1)) if m else None
        if dur is None:
            bad.append("查不到视频时长")
        elif float(dur) > VIDEO_MAX:
            bad.append("视频 %.1f 秒，超过 180 秒" % float(dur))
        else:
            parts.append("视频 %.1f 秒" % float(dur))
        q = read_json(self.issue / human / "qc.json") or {}
        gate = ((q.get("整集") or {}).get("时长把关") or {}).get("配完按实际")
        if not gate:
            bad.append("播客没有“配完按实际”的时长把关记录（配音时关了时长把关，或没配成），查不了")
        elif not gate.get("通过"):
            bad.append("播客 %.1f 分钟，不在 %s 分钟的区间里" % (gate.get("时长分钟") or 0, gate.get("区间分钟")))
        else:
            parts.append("播客 %.1f 分钟（区间 %s）" % (gate.get("时长分钟") or 0, "–".join("%g" % x for x in gate.get("区间分钟") or [])))
        if any("实际时长不在区间里" in str(w) for w in self.st("voice").get("提醒") or []):
            bad.append("第 11 步提醒：播客配完的实际时长不在区间里")
        if bad:
            return self.add(7, False, "；".join(bad), ev)
        self.add(7, True, "；".join(parts), ev)

    # ---------------------------------------------------------------- 8
    def c8(self):
        month = self.day[:7]
        ev = ["花费.json 合计美元.Gemini", "做第 11 步那次运行的 --budget-usd", "月度账本/%s.json Gemini 合计、上限" % month]
        sp = read_json(self.issue / "花费.json")
        if sp is None:
            return self.add(8, False, "没有 花费.json", ev)
        issue_usd = float((sp.get("合计美元") or {}).get("Gemini") or 0)
        r = run_of(self.state or {}, self.st("voice"))
        m = re.search(r"--budget-usd[ =]([\d.]+)", str((r or {}).get("命令", "")))
        budget = float(m.group(1)) if m else DEFAULT_BUDGET
        led = read_json(self.ledger_dir / ("%s.json" % month))
        if led is None:
            return self.add(8, False, "这一期 Gemini %s；没有月度账本 %s，查不了这个月的" % (usd(issue_usd), self.ledger_dir / (month + ".json")), ev)
        month_usd = round(sum(float(e.get("美元") or 0) for e in led.get("条目") or [] if e.get("服务") == "Gemini"), 4)
        cap = led.get("上限美元（Gemini 配音）")
        if cap is None:
            cap = (read_json(self.profile) or {}).get("每月 Gemini 配音上限美元（建议）", DEFAULT_CAP)
        cap = float(cap)
        bad = []
        if issue_usd > budget + 1e-6:
            bad.append("这一期 Gemini %s，超过这一期预算 %s（做第 11 步那次运行的 --budget-usd；fd 的预算是整期合计）" % (usd(issue_usd), usd(budget)))
        if month_usd > cap + 1e-6:
            bad.append("这个月 Gemini %s，超过每月上限 %s" % (usd(month_usd), usd(cap)))
        msg = "这一期 Gemini %s（预算 %s）；这个月 %s（上限 %s，%.0f%%）" % (usd(issue_usd), usd(budget), usd(month_usd), usd(cap), 100 * month_usd / cap if cap else 0)
        if bad:
            return self.add(8, False, "；".join(bad), ev)
        self.add(8, True, msg, ev)

    # ---------------------------------------------------------------- 9
    def c9(self):
        ev = ["审片结论.json 日期／放行／立即／请你耳听"]
        p = self.issue / "审片结论.json"
        if not p.exists():
            return self.add(9, False, "没有 审片结论.json（审片没跑或没写完），按规矩不放行", ev)
        rv = read_json(p)
        if not isinstance(rv, dict):
            return self.add(9, False, "审片结论.json 读不出来（不是合法的 JSON）", ev)
        bad = []
        if rv.get("日期") != self.day:
            bad.append("审片结论的日期是 %s，不是 %s" % (rv.get("日期"), self.day))
        if rv.get("放行") is not True:
            bad.append("审片结论“放行”不是 true（是 %r）" % rv.get("放行"))
        now = rv.get("立即")
        if not isinstance(now, list):
            bad.append("审片结论没有“立即”这一栏")
        elif now:
            bad.append("审片标了 %d 处“立即”：%s" % (len(now), "；".join("%s %s" % (x.get("编号", ""), x.get("说明", ""))
                                                               if isinstance(x, dict) else str(x) for x in now[:3])))
        rep = self.issue / "00_调度报告.md"
        if rep.exists() and p.stat().st_mtime + 60 < rep.stat().st_mtime:
            bad.append("审片结论比调度报告旧（审的可能是上一版成品）")
        listen = rv.get("请你耳听") if isinstance(rv.get("请你耳听"), list) else []
        notes = [listen_note(x) for x in listen]
        if bad:
            return self.add(9, False, "；".join(bad), ev, notes)
        asr = sum(1 for x in listen if listen_kind(x) == LISTEN_ASR)
        if not listen:
            more = ""
        elif asr:
            more = "；有 %d 处请你耳听（%s %d 处、%s %d 处）" % (len(listen), LISTEN_REAL, len(listen) - asr, LISTEN_ASR, asr)
        else:
            more = "；有 %d 处请你耳听" % len(listen)
        self.add(9, True, "审片结论放行（过 %s、不过 %s、查不了 %s；%s 写）%s" % (
            rv.get("过", "?"), rv.get("不过", "?"), rv.get("查不了", "?"), rv.get("写于", "?"), more), ev, notes)

    def run(self):
        for f in (self.c1, self.c2, self.c3, self.c4, self.c5, self.c6, self.c7, self.c8, self.c9):
            try:
                f()
            except Exception as e:      # 某一条程序出错：这一条按没过算，别的照判
                no = int(f.__name__[1:])
                self.add(no, False, "判这一条时程序出错：%s: %s" % (type(e).__name__, e), [])
        return self.results


def human_text(day, ok, results, notes, manual):
    failed = [r for r in results if not r["过"]]
    if manual:
        head = "人工放行（%s）：%s" % (manual, "9 条本来都满足。" if not failed else "按条件本来不放行，第 %s 条没满足，由你手动放行。" %
                                     "、".join(str(r["编号"]) for r in failed))
    elif ok:
        head = "放行：%s 这一期 9 条都满足，自动发布。" % day
    else:
        head = "不放行：%s 这一期有 %d 条没满足，网站不动，继续显示上一期。" % (day, len(failed))
    lines = [head]
    for r in failed:
        lines.append("第 %d 条（%s）没满足：%s" % (r["编号"], r["条件"], r["说明"]))
    show, asr = split_notes(notes)          # 和邮件一样：多半转写听错的请你耳听只报个数
    if show:
        lines.append("备注：" + "；".join(n["说明"] for n in show))
    if asr:
        lines.append("另有 %d 处请你耳听多半是转写听错，记在这一期的 审片.md" % len(asr))
    return "\n".join(lines)


def made(issue):
    """这一期出刊了没有（制作跑完到第 17 步）：fd_state.json 在、最后一次运行的结果是“跑完”、第 17 步“做完”。
    返回 (出了没有, 一句话)。没出刊就不判放行，直接发“没出刊”的邮件。
    （--until 9 这类只跑一半的测试，最后结果也写“跑完”，所以还要看第 17 步。）"""
    st = read_json(Path(issue) / "logs" / "fd_state.json")
    if st is None:
        return False, "没有 logs/fd_state.json"
    last = (st.get("运行记录") or [{}])[-1]
    res = str(last.get("结果") or "")
    if res != "跑完":
        return False, "最后一次运行的结果是：%s" % (res or "没有记录")
    rep = ((st.get("步骤") or {}).get("report") or {}).get("状态")
    if rep != DONE:
        return False, "第 17 步写本期报告没做完（%s），这次只跑到一半" % (rep or "没做")
    return True, "跑完了 17 步（%s 结束）" % last.get("结束", "?")


def judge(issue, ledger_dir=None, profile=None, manual=None):
    g = Gate(issue, ledger_dir, profile)
    results = sorted(g.run(), key=lambda r: r["编号"])
    passed = all(r["过"] for r in results)
    notes = [n for r in results for n in r["备注"]]
    ok = passed or bool(manual)
    return {"日期": g.day, "放行": ok, "按条件放行": passed, "人工放行": manual or None,
            "没过": [r["编号"] for r in results if not r["过"]], "备注": notes,
            "写于": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "给人看": human_text(g.day, ok, results, notes, manual), "条件": results}


def main(argv=None):
    ap = argparse.ArgumentParser(description="放行判定（9 条）")
    ap.add_argument("--issue", required=True, help="期目录，如 测试版/2026-11-09")
    ap.add_argument("--ledger-dir")
    ap.add_argument("--profile")
    ap.add_argument("--manual", help="人工放行的说明（GitHub 网页上手动运行“放行”时给）")
    ap.add_argument("--out", help="结论写到哪（默认 <期目录>/放行结论.json）")
    ap.add_argument("--check-made", action="store_true", help="只看这一期出刊了没有：出了退出码 0，没出 1；不判放行、不写文件")
    a = ap.parse_args(argv)
    issue = Path(a.issue)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", issue.name):
        print("✗ 期目录名应是日期：%s" % issue, file=sys.stderr)
        return 2
    if not issue.is_dir():
        print("✗ 没有期目录 %s：这一期没出刊，不放行" % issue, file=sys.stderr)
        return 2
    if a.check_made:
        ok, why = made(issue)
        print(("出刊了：" if ok else "没出刊：") + why)
        return 0 if ok else 1
    res = judge(issue, a.ledger_dir, a.profile, a.manual)
    out = Path(a.out) if a.out else issue / "放行结论.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(res["给人看"])
    print("（逐条见 %s）" % out)
    return 0 if res["放行"] else 1


if __name__ == "__main__":
    sys.exit(main())
