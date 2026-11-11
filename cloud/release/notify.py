#!/usr/bin/env python3
"""出错邮件：有事才发（11-10 改，原来是“有备注就发”）。没出刊、没放行、发布出错或没发布、有要告诉你的备注时发；
正常发布、只有“多半转写听错”的请你耳听的日子不发。

三种情况（--kind auto 时自动判断）：
    没出刊   期目录没有，或没有 放行结论.json（制作没跑完，放行判定没轮到）：写卡在第几步、00_调度报告.md 开头几行
    没放行   放行结论.json 说不放行：写没满足哪几条、审片.md 开头几行、怎么手动放行
    放行     有事才发：备用声音（因花费上限）、配图退回程序封面、Codex 要重新登录、Codex 额度用完、审片判断“多半真念错”的请你耳听
             （旧格式没写判断的也算）；发布出错或发布开关没开也发。
哪些备注要告诉你，用 gate.py 的 split_notes（和放行结论“给人看”那段话同一个判断）。邮件里只列要告诉你的那几条；
“多半转写听错”的不列，末尾只写一行“另有 N 处多半是转写听错，记在这一期的 审片.md（仓库 测试版/<日期>/审片.md）”。
用法（在仓库根目录）：
    python cloud/release/notify.py --issue 测试版/2026-11-09 [--kind auto|没出刊|没放行|放行] [--published yes|no|failed] [--dry-run]
                                   [--claim released|kept --claim-tag issue/2026-11-09] [--saturday]
      --published  这次发布的结果（workflow 传）：yes 发布了；no 发布开关没开、只打包；failed 发布出错
      --dry-run    只打印要发的标题和正文，不发
      --claim      这次运行认领了这一天（同一天只出一期，标签 --claim-tag）：released＝第 4 步以前出错，认领会放回、
                   下一个时刻自动再试；kept＝第 4 步以后出错，认领留着，邮件里写怎么接着跑、怎么删标签重跑。只管"没出刊"
      --saturday   周六不出刊，只跑第 1–3 步；这封是那三步出错了
发信照期刊监控 scripts/monitor.py 的写法：环境变量 SENDER_EMAIL、EMAIL_APP_PASSWORD 都有才真发（Gmail，smtp.gmail.com:587，
先 STARTTLS 再登录；SMTP_SERVER、SMTP_PORT 可改），收件人 NOTIFY_EMAIL，没设就发给 SENDER_EMAIL 自己。
没设就只打印，不报错。密码不打印、不写进任何文件。
退出码：0 发了、打印了或不用发；3 真发时失败（workflow 里这一步设成出错也不挡别的）。

2026-11 拆成两个仓库以后（公开仓库出刊，私有仓库 dylan-zhang-wl/frontier-daily 放行、发布、发邮件）：
    这封邮件在私有仓库的"放行发布"流程里发。邮件里的"这次运行"、接着跑的 from_run 指公开仓库那次出刊运行：
    流程给环境变量 FD_RUN_REPO（公开仓库名）、FD_RUN_ID（那次运行的编号）；没给就用 GITHUB_REPOSITORY、GITHUB_RUN_ID（和以前一样）。
    整期文件包在私有仓库的发行版 run-<FD_RUN_ID> 里（不再是 Actions 产物）；手动放行在私有仓库的"放行发布"。
    认领标签、接着跑的命令都在公开仓库（REPO）。
11-11 加：期目录里有 logs/codex_额度用完.txt（cloud/codex_login_check.py 写的）就加一段“多半是 Codex 额度用完”，
    标题里写“Codex 额度用完”，放行了的那期光这一条也发；同时有登录失效的记号时只说登录失效（那个要你动手）。
"""
import argparse
import json
import os
import re
import smtplib
import sys
import time
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate  # noqa: E402  哪些备注要告诉你：和放行判定共用一个判断

SITE = "https://wenlongzhang.com/frontier/"
STEP_NAMES = ["抓取", "粗筛归并", "事件库入库", "选题", "事件卡", "写稿", "稿子检查", "独立审读", "改稿", "配图", "配音", "混音",
              "网页组装", "视频", "网页带视频再组装", "验收", "写本期报告"]
STEP_KEYS = ["fetch", "cluster", "ingest", "select", "cards", "write", "check", "review", "revise", "images", "voice", "mix",
             "web", "video", "web2", "accept", "report"]
NOTE_KINDS = gate.MAIL_KINDS          # 备用声音、配图退回、请你耳听（邮件里按这个顺序列）
CODEX_MARK = Path("logs") / "codex_登录失效.txt"
CODEX_LINE = "Codex 云端登录要重新登录，见 cloud/密钥与重置手册.md（这一期画不成的图已退回程序封面）。"
QUOTA_MARK = Path("logs") / "codex_额度用完.txt"
QUOTA_URL = "chatgpt.com/codex/settings/usage"
SEND_ATTEMPTS, RETRY_SECONDS = 2, 30
REPO = "dylan-zhang-wl/frontier-briefing"      # 出刊流程和认领标签所在的仓库（2026-11 起是公开仓库）
KEEP_DAYS = 14                                 # 私有仓库发行版 run-<编号> 留几天（放行发布.yml 清理）
# 每天的触发时刻（UTC）：Cloudflare 保底触发器 04:17（11-10 起当主力）、04:43、06:47（晚补）；
# 11-10 起叫出刊的是 Cloudflare 保底触发器 04:17（主力）、04:43、06:47；GitHub 自己的定时（04:17、05:11）实测从没准点来过，
# 不写进邮件，免得你以为 05:11 也会再试一次
TRIGGER_TIMES = "04:17、04:43、06:47"
OFFICIAL_RUN = ("gh workflow run frontier-daily.yml -R %s -f until=17 -f review=true -f upload_media=false "
                "-f test_mode=false -f gemini=default -f extra=none" % REPO)


def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def head_lines(p, n):
    """文件开头 n 行（跳过连续空行），没有就返回 None。"""
    try:
        rows = Path(p).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    out, blank = [], False
    for r in rows:
        if not r.strip():
            if blank:
                continue
            blank = True
        else:
            blank = False
        out.append(r)
        if len(out) >= n:
            break
    return "\n".join(out).strip()


def run_id():
    """出刊那次运行的编号：私有仓库的放行发布流程给 FD_RUN_ID（公开仓库那次运行）；没给就是这次运行自己。"""
    return os.environ.get("FD_RUN_ID") or os.environ.get("GITHUB_RUN_ID")


def run_url():
    s = os.environ.get("GITHUB_SERVER_URL")
    r = os.environ.get("FD_RUN_REPO") or os.environ.get("GITHUB_REPOSITORY")
    i = run_id()
    return "%s/%s/actions/runs/%s" % (s, r, i) if s and r and i else None


def bundle_where(day):
    """整期文件包在哪（一句话）。"""
    rid = run_id() or "<运行编号>"
    return "私有仓库发行版 run-%s 里的 issue-%s.tar.gz（不带音视频的小份；没发布的期另有带音视频的 media-%s.tar.gz），保留 %d 天" % (
        rid, day, day, KEEP_DAYS)


def quota_info(issue):
    """logs/codex_额度用完.txt → {"网页": a, "视频": b, "第一次": "2026-11-12 05:02"}；没有这个文件返回 None。读不出数的写 None。"""
    try:
        text = (Path(issue) / QUOTA_MARK).read_text(encoding="utf-8")
    except OSError:
        return None
    info = {"网页": None, "视频": None, "第一次": None}
    for k in info:
        m = re.search(r"^%s=(.+)$" % k, text, re.M)
        if m:
            v = m.group(1).strip()
            info[k] = int(v) if k != "第一次" and v.isdigit() else (v if k == "第一次" else None)
    return info


def quota_line(q, published_ok):
    """邮件里那一段（11-11 定的写法；办法见经验库第五部分第 76 件）。"""
    web, vid = q.get("网页"), q.get("视频")
    if web is not None and vid is not None:
        count = "这一期有 %d 张没画成（网页 %d 张、视频 %d 张）" % (web + vid, web, vid)
    else:
        count = "这一期有几张没画成"
    when = q.get("第一次")
    when = "，第一次在 %s UTC" % when.split(" ")[-1] if when else ""
    return ("配图：%s，多半是 ChatGPT Plus 的 Codex 额度用完了（画图日志里有额度用完的提示%s）。已用程序画的封面顶上%s。"
            "不用重新登录；5 小时额度过几个小时自己恢复，每周额度要等到下周。看用了多少：%s 。"
            "连着几天都这样，见经验库第 76 件的办法（换更省额度的模型、减张数、买额外额度）。") % (
        count, when, "，这一期照常发布" if published_ok else "", QUOTA_URL)


def actions_url():
    s, r = os.environ.get("GITHUB_SERVER_URL"), os.environ.get("GITHUB_REPOSITORY")
    return "%s/%s/actions" % (s, r) if s and r else "GitHub 仓库的 Actions 页"


def stuck_at(issue):
    """卡在第几步：按 17 步顺序找第一个不是“做完”的（第 10 步“跳过”不算卡）；再看最后一次运行的“结果”。"""
    st = read_json(Path(issue) / "logs" / "fd_state.json")
    if st is None:
        return None, "没有 logs/fd_state.json：第 1 步之前就停了（装环境、取缓存或 claude 那一步出错），要看 Actions 运行日志"
    steps = st.get("步骤") or {}
    last = (st.get("运行记录") or [{}])[-1]
    for i, k in enumerate(STEP_KEYS, 1):
        s = (steps.get(k) or {}).get("状态")
        if s == "做完" or (k == "images" and s == "跳过"):
            continue
        why = (steps.get(k) or {}).get("说明") or ""
        return i, "第 %d 步%s：%s%s" % (i, STEP_NAMES[i - 1], s or "没做", "（%s）" % why[:200] if why else "")
    res = last.get("结果") or ""
    if res and res != "跑完":
        return None, "17 步都做完了，但最后一次运行的结果是：%s" % res[:200]
    return None, "17 步都做完了，可是放行判定没跑（看 Actions 运行日志）"


def claim_lines(day, claim, tag, stuck_no):
    """没出刊时，认领（同一天只出一期的标签）怎么处理。"""
    if claim == "released":
        return ["", "第 4 步还没开始（还没用 Claude、没花钱），这一天的认领（标签 %s）会放回：" % tag,
                "今天后面的触发时刻（UTC %s 里还没到的）会自动再试；再试成功、没有备注就不会另发邮件。" % TRIGGER_TIMES,
                "如果今天的时刻都过了，要再出这一期就手动按正式运行一次（在终端）：", "", "    " + OFFICIAL_RUN, "",
                "不要在运行页面上点 Re-run（重跑）：它沿用原来的认领结果，可能和别的运行同时出同一期。"]
    if claim == "kept":
        rid = run_id() or "<这次运行的编号>"
        step = stuck_no if stuck_no and stuck_no >= 4 else "<卡住的那一步，4–17>"
        delete = "gh api -X DELETE repos/%s/git/refs/tags/%s" % (REPO, tag)
        return ["", "这一期是第 4 步以后出的错（已经用了 Claude 额度，可能也花了配音的钱），所以不自动重跑：",
                "这一天的认领（标签 %s）留着，今天后面的触发时刻看到它就会跳过。要再出这一期，二选一：" % tag, "",
                "1. 接着跑（推荐，做完的步骤不重做、不重复花钱；接着跑不认领，不用删标签）：", "",
                "    %s -f from_run=%s -f from_step=%s" % (OFFICIAL_RUN, rid, step), "",
                "2. 从头重跑：重跑前要先删标签 %s，再按正式运行一次：" % tag, "",
                "    " + delete, "    " + OFFICIAL_RUN, "",
                "   （这一期的文字已经提交回仓库 测试版/%s 时，从头跑会被拦下，只能用第 1 种。）" % day, "",
                "不要在运行页面上点 Re-run（重跑）：它沿用原来的认领结果，可能和别的运行同时出同一期。"]
    return []


def note_lines(day, notes, head):
    """备注那一段：只列要告诉你的（gate.split_notes），多半转写听错的请你耳听末尾只报个数。
    返回 (几行字, 要告诉你的备注, 多半转写听错的个数)。"""
    tell, asr = gate.split_notes(notes)
    lines = []
    if tell:
        lines += ["", head]
        order = {k: i for i, k in enumerate(NOTE_KINDS)}
        for n in sorted(tell, key=lambda n: order.get(n["类"], 9)):      # 同一类保持审片写的先后
            s = "- %s：%s" % (n["类"], n["说明"])
            if n["类"] == gate.LISTEN and gate.listen_classified(n) and n.get("依据"):
                s += "（审片的依据：%s）" % n["依据"]
            lines.append(s)
        listen = [n for n in tell if n["类"] == gate.LISTEN]
        raw = [n for n in listen if not gate.listen_classified(n)]
        if raw:
            who = "这几处" if len(raw) == len(listen) else "其中 %d 处" % len(raw)
            lines += ["", "%s审片结论里没写“判断”（旧格式）或写的认不出，按“%s”列出来。" % (who, gate.LISTEN_REAL)
                      + "“请你耳听”是转写模型对不上原稿的地方，不一定念错；打开网页上的播客或视频，拖到那个时间听一下。"]
        elif listen:
            lines += ["", "审片判断这几处多半是配音真念错了%s，但还没人耳听过，不一定对；" % (
                "（括号里是审片的依据）" if any(n.get("依据") for n in listen) else "")
                      + "打开网页上的播客或视频，拖到那个时间听一下。"]
    if asr:
        lines += ["", "另有 %d 处多半是转写听错，记在这一期的 审片.md（仓库 测试版/%s/审片.md）" % (len(asr), day)]
    return lines, tell, len(asr)


def kinds_of(tell, codex=False, quota=False):
    """标题括号里的几类：请你耳听写上几处。"""
    out = []
    for k in NOTE_KINDS:
        m = [n for n in tell if n["类"] == k]
        if m:
            out.append("%s %d 处" % (k, len(m)) if k == gate.LISTEN else k)
    if codex:
        out.append("Codex 要重新登录")
    if quota:
        out.append("Codex 额度用完")
    return out


def build(issue, kind="auto", published=None, claim=None, claim_tag=None, saturday=False):
    """返回 (要不要发, 标题, 正文)。claim、claim_tag、saturday 只管"没出刊"这一种。"""
    issue = Path(issue)
    day = issue.name
    verdict = read_json(issue / "放行结论.json") if issue.is_dir() else None
    if kind == "auto":
        kind = "没出刊" if verdict is None else ("放行" if verdict.get("放行") else "没放行")
    url = run_url()
    tail = ["", "—— 这封邮件由 frontier-daily 云端流程自动发出（cloud/release/notify.py）。"]
    if url:
        tail.insert(1, "这次运行：%s" % url)
    # Codex 云端登录失效（workflow 查到画图日志里有 401、refresh 失败时写这个记号）：哪种邮件都加一句；放行了的那期光这一条也发（11-08 晚加，11-10 改成单独也发）
    codex = (issue / CODEX_MARK).exists()
    if codex:
        tail = ["", CODEX_LINE] + tail
    # Codex 额度用完（11-11 加；codex_login_check.py 写的记号）：和登录失效同时有时只说登录失效
    quota = None if codex else quota_info(issue)
    if quota is not None:
        verdict_ok = kind == "放行" and published in (None, "yes")
        tail = ["", quota_line(quota, verdict_ok)] + tail

    if kind == "没出刊":
        if saturday:
            lines = ["%s 是周六，不出刊，只跑第 1–3 步（抓取、粗筛归并、入库）；这三步出错了，往期事件库可能少了今天的材料。" % day, ""]
        else:
            lines = ["%s 这一期没出刊，网站不动，继续显示上一期。" % day, ""]
        no = None
        if not issue.is_dir():
            lines.append("卡在哪：期目录 %s 都没有建起来（第 1 步之前就停了），要看 Actions 运行日志。" % issue.as_posix())
        else:
            no, why = stuck_at(issue)
            lines.append("卡在哪：" + why)
            rep = head_lines(issue / "00_调度报告.md", 14)
            if not saturday:
                lines += ["", "00_调度报告.md 开头：", "", rep or "（没有 00_调度报告.md）"]
        if claim in ("released", "kept") and claim_tag:
            lines += claim_lines(day, claim, claim_tag, no)
        lines += ["", "整期目录在%s，可以下载来看。" % bundle_where(day)]
        if saturday:
            subject = "【前沿简报】%s（周六）抓取入库出错" % day
        else:
            subject = "【前沿简报】%s 没出刊" % day
        if claim == "released" and claim_tag:
            subject += "，稍后自动再试"
        return True, subject, "\n".join(lines + tail)

    if kind == "没放行":
        v = verdict or {}
        failed = [c for c in v.get("条件") or [] if not c.get("过")]
        lines = ["%s 这一期做出来了，但没满足自动发布的条件，网站不动，继续显示上一期。" % day, "", "没满足的：", ""]
        lines += ["- 第 %s 条 %s：%s" % (c.get("编号"), c.get("条件"), c.get("说明")) for c in failed] or ["- （放行结论里没写哪一条）"]
        lines += note_lines(day, v.get("备注"), "另外记下的：")[0]
        rv = head_lines(issue / "审片.md", 12)
        lines += ["", "审片.md 开头：", "", rv or "（没有 审片.md：审片没跑或没写完）"]
        lines += ["", "你看过觉得能发：打开 %s → 左边选“放行发布” → Run workflow → 填日期 %s → Run（手动放行）。" % (actions_url(), day),
                  "成品整期目录在%s，手动放行就从那里取。" % bundle_where(day)]
        return True, "【前沿简报】%s 没放行：第 %s 条没满足" % (day, "、".join(str(c.get("编号")) for c in failed) or "?"), "\n".join(lines + tail)

    # 放行：有事才发
    v = verdict or {}
    nlines, tell, asr = note_lines(day, v.get("备注"), "有几处要你知道：")
    if not tell and not codex and quota is None and published in (None, "yes"):
        if asr:
            return False, "", "%s 正常放行，只有 %d 处请你耳听多半是转写听错（记在 测试版/%s/审片.md），不发邮件。" % (day, asr, day)
        return False, "", "%s 正常放行、没有备注，不发邮件。" % day
    link = "%s?date=%s" % (SITE, day)
    if published == "failed":
        head = "%s 这一期满足放行条件，但发布到网站时出错了，网站还是上一期。看这次运行的日志；修好后可以手动放行重发。" % day
    elif published == "no":
        head = "%s 这一期满足放行条件，但发布开关没开（仓库变量 SITE_DEPLOY_ENABLED 不是 true），这次只打包检查、没发布。" % day
    else:
        head = "%s 这一期已发布：%s" % (day, link)
    if v.get("人工放行"):
        head += "（人工放行：%s）" % v["人工放行"]
    lines = [head] + nlines
    subject = {"failed": "发布出错", "no": "放行了但没发布"}.get(published, "已发布，有备注")
    return True, "【前沿简报】%s %s（%s）" % (day, subject, "、".join(kinds_of(tell, codex, quota is not None)) or "无备注"), "\n".join(lines + tail)


def email_config():
    cfg = {"smtp_server": os.environ.get("SMTP_SERVER") or "smtp.gmail.com",
           "smtp_port": int(os.environ.get("SMTP_PORT") or 587),
           "sender": (os.environ.get("SENDER_EMAIL") or "").strip(),
           # Google 的应用专用密码显示成"xxxx xxxx xxxx xxxx"，粘贴进 Secrets 时常带着空格：登录前把空白全去掉（11-08 晚加）
           "password": re.sub(r"\s+", "", os.environ.get("EMAIL_APP_PASSWORD") or "")}
    cfg["to"] = (os.environ.get("NOTIFY_EMAIL") or "").strip() or cfg["sender"]
    return cfg if cfg["sender"] and cfg["password"] else None


def send(subject, body, cfg):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header("前沿简报云端", "utf-8")), cfg["sender"]))
    msg["To"] = cfg["to"]
    for attempt in range(1, SEND_ATTEMPTS + 1):
        try:
            server = smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"], timeout=60)
            server.starttls()
            server.login(cfg["sender"], cfg["password"])
            server.send_message(msg)
            server.quit()
            return True, "已发到 %s" % cfg["to"]
        except smtplib.SMTPAuthenticationError as e:       # 应用专用密码失效或被撤销：重试没用
            return False, "发信被拒（检查 EMAIL_APP_PASSWORD）：%s" % type(e).__name__
        except Exception as e:  # noqa: BLE001
            if attempt < SEND_ATTEMPTS:
                time.sleep(RETRY_SECONDS)
            else:
                return False, "发信失败（%d 次）：%s: %s" % (SEND_ATTEMPTS, type(e).__name__, str(e)[:120])
    return False, "发信失败"


def main(argv=None):
    ap = argparse.ArgumentParser(description="出错邮件")
    ap.add_argument("--issue", required=True, help="期目录，如 测试版/2026-11-09（不存在也行：那就是没出刊）")
    ap.add_argument("--kind", default="auto", choices=("auto", "没出刊", "没放行", "放行"))
    ap.add_argument("--published", choices=("yes", "no", "failed"), help="这次发布的结果")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不发")
    ap.add_argument("--claim", choices=("released", "kept"), help="认领了这一天：released 会放回、自动再试；kept 留着、由人处理")
    ap.add_argument("--claim-tag", help="认领的标签名，如 issue/2026-11-10")
    ap.add_argument("--saturday", action="store_true", help="周六只跑第 1–3 步，这封是那三步出错")
    ap.add_argument("--test-mail", action="store_true",
                    help="只发一封固定的测试邮件（验证 SENDER_EMAIL、EMAIL_APP_PASSWORD、NOTIFY_EMAIL 三项能用），不看期目录")
    a = ap.parse_args(argv)
    if a.test_mail:
        subject = "前沿简报云端测试（11-08 晚）"
        body = ("这是云端流程的一封测试邮件，只为确认发信的三项设置能用，不用回复。\n"
                "—— frontier-daily 云端流程（cloud/release/notify.py --test-mail）")
        cfg = None if a.dry_run else email_config()
        if cfg is None:
            print("（%s：只打印，不发）\n标题：%s\n正文：\n%s" % ("--dry-run" if a.dry_run else "没设 SENDER_EMAIL / EMAIL_APP_PASSWORD", subject, body))
            return 0
        ok, msg = send(subject, body, cfg)
        print(("✓ " if ok else "✗ ") + msg + "：" + subject)
        return 0 if ok else 3
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", Path(a.issue).name):
        print("✗ 期目录名应是日期：%s" % a.issue, file=sys.stderr)
        return 2
    need, subject, body = build(a.issue, a.kind, a.published, a.claim, a.claim_tag, a.saturday)
    if not need:
        print(body)
        return 0
    cfg = None if a.dry_run else email_config()
    if cfg is None:
        print("（%s：只打印，不发）" % ("--dry-run" if a.dry_run else "没设 SENDER_EMAIL / EMAIL_APP_PASSWORD"))
        print("标题：" + subject)
        print("正文：")
        print(body)
        return 0
    ok, msg = send(subject, body, cfg)
    print(("✓ " if ok else "✗ ") + msg + "：" + subject)
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
