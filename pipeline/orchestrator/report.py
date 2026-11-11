"""本期报告：<期目录>/00_调度报告.md。开头先说这一期全不全（少了什么、要你做什么），再列每一步、提醒和花费。"""
from pathlib import Path

from .common import DONE, FAILED, SKIPPED, WAITING, TODO, RUNNING, stamp, rel, read_json, write_text, NO_PODCAST
from .steps import STEPS


def missing(c):
    """这一期少了什么（保底时）：从各步的记录里算出来，不另记。"""
    out = []
    st = {s.key: (c.state.step(s.key) or {}) for s in STEPS}
    v = st["voice"].get("附加") or {}
    if v.get("播客") == "没配成":
        out.append("播客音频（配音没成，主声音和备用都不行；网页不放'听'）")
    if v.get("视频旁白") == "没配成" or st["video"].get("状态") in (FAILED, SKIPPED) or \
            (st["web2"].get("状态") == DONE and (st["web2"].get("附加") or {}).get("带视频") is False):
        if st["video"] or v.get("视频旁白"):
            out.append("视频（%s）" % (st["video"].get("说明") or "视频旁白没配成"))
    if st["mix"].get("状态") == FAILED:
        out.append("播客的声音包（混音没成，网页挂的是不带音乐的人声版）")
    im = st["images"]
    if im.get("状态") == SKIPPED:
        ex = im.get("附加") or {}
        if ex.get("缺网页配图"):
            out.append("网页配图 %s（用程序画的主题色封面代替）" % "、".join(ex["缺网页配图"]))
        if ex.get("缺视频配图"):
            out.append("视频配图 %s（那几块不带图）" % "、".join(ex["缺视频配图"]))
    if st["accept"].get("状态") == FAILED:
        out.append("验收没过（%s）——不要发布" % "；".join((st["accept"].get("提醒") or [])[:3]))
    return out


def write(c, outcome, first, last):
    st = {s.key: (c.state.step(s.key) or {}) for s in STEPS}
    miss = missing(c)
    stop = outcome.get("停在")
    done_all = not stop and not outcome.get("原因") and last == STEPS[-1].no
    if st["report"].get("状态") != DONE and done_all:
        pass
    L = ["# %s · %s · 调度报告" % (c.day, c.ed["名字"]), "",
         "生成于 %s（系统时钟）。期目录：`%s`%s。" % (stamp(), c.issue, "" if c.default_issue else "（--issue-dir，测试用）"), ""]
    # ---- 一、先看这里
    L += ["## 一、先看这里", ""]
    if stop:
        s = next(x for x in STEPS if x.no == stop)
        L.append("- **没跑完：停在第 %d 步（%s）**：%s" % (stop, s.name, outcome.get("原因", "")))
        todo = outcome.get("要你做") or st[s.key].get("要你做") or []
        if todo:
            L.append("- **要你做**：")
            L += ["  " + ("- " + t.strip() if not t.startswith("  ") else "  " + t.strip()) for t in todo]
    elif outcome.get("原因"):
        L.append("- **没跑完**：%s" % outcome["原因"])
    elif last < STEPS[-1].no:
        L.append("- 这次只跑到第 %d 步（--until）。" % last)
    if miss:
        L.append("- **这一期是保底的'数据版'，少了**：")
        L += ["  - " + m for m in miss]
    elif not stop and not outcome.get("原因") and last == STEPS[-1].no:
        L.append("- **这一期齐了**：网页、播客、视频都有，各项检查都过了。")
    web = c.p("10_网页v3/index.html")
    if web.exists():
        L.append("- 网页：`10_网页v3/index.html`（双击打开）")
    wp = (st["web"].get("附加") or {}).get("播客")
    if wp and wp != "无":
        q = read_json(c.p(wp) / "qc.json", {}) or {}
        secs = (q.get("整集") or {}).get("整集秒数")
        L.append("- 播客：`%s/episode.mp3`%s" % (wp, "（%.1f 分钟）" % (secs / 60) if secs else ""))
    if c.p("11_视频v3/预览.mp4").exists() and st["video"].get("状态") == DONE:
        L.append("- 视频预览：`11_视频v3/预览.mp4`")
    led = c.ledger.status()
    L.append("- 花费：这一期 Gemini $%.3f；本月已记 $%.2f / 上限 $%.2f（%.0f%%）%s" % (
        c.ledger.issue_total("Gemini"), led["Gemini已记美元"], led["上限美元"], 100 * led["比例"],
        "——**到 90% 了，配音已改走 MiMo 备用**" if led["到90%"] else ""))
    v = st["voice"].get("附加") or {}
    d = v.get("决定") or {}
    if d.get("用备用"):
        if v.get("播客") == "没配成":
            L.append("- **配音改走 MiMo 备用**（%s），但备用也没配成，所以这一期没有播客。" % d.get("原因"))
        else:
            L.append("- **配音走了 MiMo 备用**：%s。听众听到的是 Shirley、Dylan 自己的复刻声音。" % d.get("原因"))
    elif str(v.get("播客", "")).startswith("MiMo"):
        L.append("- **播客改用了 MiMo 备用**：主声音（Gemini）这次没配成，见第三节提醒。")
    if c.offline:
        L.append("- 这次是离线跑（--offline）：不联网、不花钱，只用缓存。")
    L.append("")
    # ---- 二、每一步
    L += ["## 二、每一步", "", "| 步 | 做什么 | 谁做 | 状态 | 说明 | 用时 | 日志 |", "|---|---|---|---|---|---|---|"]
    for s in STEPS:
        r = st[s.key]
        if s.no < first or s.no > last:
            status, msg = (r.get("状态") or TODO), "（这次没查：--from/--until）" + (r.get("说明") or "")
        else:
            status, msg = r.get("状态") or TODO, r.get("说明") or ""
            if r.get("怎么来的") == "采纳已有产出" and status == DONE:
                msg = "采纳已有产出。" + msg
        logs = "、".join("`%s`" % Path(x).name for x in (r.get("日志") or [])[-2:])
        secs = r.get("用时秒")
        L.append("| %d | %s | %s | %s | %s | %s | %s |" % (s.no, s.name, s.who, status, msg.replace("|", "／"),
                                                        ("%.0f 秒" % secs) if secs is not None else "", logs))
    L.append("")
    # ---- 三、提醒
    warns = [(s, w) for s in STEPS for w in (st[s.key].get("提醒") or [])]
    if warns:
        L += ["## 三、提醒（不挡出刊，但值得看一眼）", ""]
        for s, w in warns:
            L.append("- 第 %d 步 %s：%s" % (s.no, s.name, w))
        L.append("")
    # ---- 四、花费
    issue = c.ledger.issue_data()
    L += ["## 四、花费", "", "钱数从各步产出的 usage.json 读（配音程序记的'这次新花的钱'），不是估的。", "",
          "| 服务 | 这一期 | 本月已记 | 说明 |", "|---|---|---|---|"]
    notes = {"Gemini": "配音（主账号 frontier-daily 项目的每月赠金）", "MiMo": "事件卡、备用配音（免费期，只记 token）",
             "Codex": "配图后备（ChatGPT 订阅，不另花钱）；配图先用 agy（Google AI Pro 订阅，不另花钱，不记账）", "Claude": "选题、写稿、审读（会话里做，订阅额度）"}
    for sv in ("Gemini", "MiMo", "Codex", "Claude"):
        L.append("| %s | $%.3f | $%.2f | %s |" % (sv, c.ledger.issue_total(sv), c.ledger.month_total(sv), notes[sv]))
    rows = [e for e in issue.get("条目") or [] if e.get("服务") != "Gemini" or e.get("美元")]
    if issue.get("条目"):
        L += ["", "明细（这一期）："]
        for e in issue["条目"][-12:]:
            extra = "，%s token" % e["token数"] if e.get("token数") else ""
            L.append("- %s %s · %s：$%.4f（%s%s）%s" % (e.get("时间", "")[5:16], e.get("步骤"), e.get("服务"), e.get("美元", 0),
                                                    e.get("数从哪来", ""), extra, "；" + e["说明"] if e.get("说明") else ""))
    L += ["", "本月账本：`%s`。fd 上线前手动跑的花费（10-31、11-01 和各轮配音测试）没记进去。" % rel(c.ledger.month_file), ""]
    # ---- 五、接着怎么跑
    L += ["## 五、接着怎么跑", "",
          "- 看每一步现在的状态：`./fd status --date %s%s`" % (c.day, "" if c.default_issue else " --issue-dir …"),
          "- 补好要你做的事以后：`%s`（做过的步骤会自动跳过，从停下的那步接着跑）" % c.again(),
          "- 某一步想重做：删掉它的产出，或加 `--redo 步骤名`；说明见 `文档/方案/总调度说明.md`。", ""]
    path = c.issue / "00_调度报告.md"
    write_text(path, "\n".join(L))
    return path
