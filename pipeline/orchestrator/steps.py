"""步骤表：一期从抓取到报告的 17 步。

每一步写清楚：
  · 用哪个脚本、什么参数（command / run）；
  · 产出是什么（outputs）：产出在、上游没变，就算"做过了"，跳过；
  · 上游是什么（inputs）：上游变了，程序类的步骤自动重做（花钱的配音只重配改过的部分，缓存里有的不花钱）；
  · 怎么判过没过（verify）；
  · 没过怎么办（补救）：重做一次 → 放宽 → 换备用 → 停下来叫人，照 文档/经验/检查清单.yaml 写。
要模型写的几步（选题、写稿、审读、改稿）和配图这一版是"半自动"：产出已在就检查一遍、采纳；不在就停下，说清在会话里做什么、产出放哪。
"""
import json
import re
import shutil
import time
from pathlib import Path

from .common import (DONE, FAILED, SKIPPED, WAITING, PIPE, TOOLS, PROMPTS, PROFILE, HELPERS, PLAYWRIGHT, EDITIONS,
                     WEB_DRAFT, STORYBOARD, NARRATION, VIDEO_VOICE, CARDS, LINEUP, NO_PODCAST,
                     read_json, write_json, rel, fp_file, fp_dir, key_lines, tail, running_scripts, today_utc, hours_ago,
                     gemini_price_out, episode_title, iso, motion_switch, director_switch, narration_switch,
                     zh_wrap_switch)
from .ledger import usage_new_spend, chunk_spend_since, mimo_tokens_since

IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
TERMS = "02_选题/往期今日一词.json"     # 往期今日一词（pipeline/term_history.py 写，选题时读；11-03 加）


class R:
    """一步的结果。go_on=True：这一步没成，但按保底办法照常往下走（比如配音失败就出数据版）。"""

    def __init__(self, status, msg="", warns=None, extra=None, todo=None, go_on=False):
        self.status, self.msg = status, msg
        self.warns = [w for w in (warns or []) if w]
        self.extra = extra or {}
        self.todo = todo or []
        self.go_on = go_on


def _err(out):
    """报错那一行（✗ 开头或 xxxError: 那行），找不到再退回要紧的几行。"""
    rows = [x.strip() for x in (out or "").splitlines() if x.strip().startswith("✗") or re.search(r"\w+(Error|Exceeded|Exit): ", x)]
    return rows[-1][:200] if rows else "；".join(key_lines(out, 2))[:200]


def _han(text):
    return len(re.findall(r"[一-鿿]", text or ""))


def timbre_relisten_count(qc_text):
    """配音 qc.json 里真正标了"音色需人工听"的有几块（单人稿）或几轮（两人对谈）。
    11-05 改：原来数 qc.json 全文里"音色需人工听"这几个字出现几次，汇总表的键名"音色需人工听的块"本身就会被数成 1 处
    （11-04 列表是空的，报告却写"1 处"）。现在按 JSON 读：有汇总列表（tts.py 的"音色需人工听的块"、dialog_tts.py
    每个说话人的"音色需人工听的轮"）就数列表长度；没有汇总的旧格式，才数各块里"音色需人工听": true 的条数。"""
    try:
        q = json.loads(qc_text) if isinstance(qc_text, str) else qc_text
    except ValueError:
        return 0
    lists, flags = [], [0]

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("音色需人工听的块", "音色需人工听的轮") and isinstance(v, list):
                    lists.append(len(v))
                elif k == "音色需人工听" and v is True:
                    flags[0] += 1
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(q or {})
    return sum(lists) if lists else flags[0]


def _fail_round(c, key, cur_fp):
    """同一步"没过"的第几轮：只有产出真的改过（指纹变了）才算新一轮，没改就再跑一遍不算。"""
    rec = c.state.step(key) or {}
    seen = list((rec.get("附加") or {}).get("没过时的产出指纹") or [])
    if cur_fp and cur_fp not in seen:
        seen.append(cur_fp)
    return len(seen), seen


class Step:
    no, key, name = 0, "", ""
    who = "程序"
    kind = "程序"            # 程序／半自动
    adopt = False            # 产出已在、fd 没记录时：检查一遍就采纳（花钱或要模型的步骤），不重做
    stale_rerun = True       # 上游变了就重做
    always = False
    timeout = 1800
    check_text = ""          # 怎么判过没过（给说明文档和 --dry-run 用）
    fix_text = ""            # 没过怎么办

    # ---- 子类按需改
    def applies(self, c):
        return True, ""

    def outputs(self, c):
        return []

    def outputs_exist(self, c):
        return all(c.p(o).exists() for o in self.outputs(c))

    def inputs(self, c):
        return []

    def plan(self, c):
        return []

    def plan_adopt(self, c):
        return ["只检查一遍已有的产出，不重跑、不花钱"]

    def run(self, c, how):
        return R(DONE)

    # ---- 共用
    def input_fp(self, c):
        out = {}
        for i in self.inputs(c):
            if i.startswith("@step:"):
                k = i[6:]
                out[i] = ((c.state.step(k) or {}).get("产出指纹") or {}).get("_合") or ""
            elif i.startswith("="):
                out[i.split("=", 2)[1]] = i.split("=", 2)[2]
            else:
                out[i] = fp_file(c.p(i)) or ""
        return out

    def output_fp(self, c):
        d = {o: fp_file(c.p(o)) or "" for o in self.outputs(c)}
        d["_合"] = "|".join(d[k] for k in sorted(d))
        return d


# ================================================================ 1 抓取
class Fetch(Step):
    no, key, name = 1, "fetch", "抓取"
    who = "程序（联网，不花钱）"
    adopt, stale_rerun = True, False
    timeout = 900
    check_text = "raw.jsonl 有条目；每源统计里失败的来源、总条数是否明显偏少、AINews 拆出的社交信号是不是 0"
    fix_text = ("单个来源出错：fetch.py 已自动重试一次，再不行跳过那个来源（照常出刊）；整次失败：再跑一次，还不行停下来叫人。"
                "离线（--offline）时不联网，没有材料就停。同一天定时抓取正在跑时不重复起跑")

    def outputs(self, c):
        return ["01_获取/raw.jsonl", "01_获取/每源统计.json"]

    def command(self, c):
        args = ["--day", c.day, "--out-dir", c.p("01_获取")]
        if c.day == today_utc():
            args += ["--since", hours_ago(36)]          # 窗口按开跑时刻往前 36 小时（经验 A2）
        return c.py(PIPE / "fetch.py", *args)

    def plan(self, c):
        return ["运行：" + c.show(self.command(c)), "约 10–40 秒，不花钱" + ("；离线模式不会抓" if c.offline else "")]

    def run(self, c, how):
        if how == "run":
            if c.offline:
                return R(FAILED, "离线模式不联网抓取，这一期又没有抓取材料（01_获取/raw.jsonl）")
            busy = running_scripts(["pipeline/fetch.py --day %s" % c.day])
            if busy:
                return R(FAILED, "已经有一个抓取在跑（进程 %d：%s），等它结束再来" % (busy[0][0], busy[0][1][:80]))
            out = ""
            for n in (1, 2):
                rc, out = c.run(self, self.command(c), "第 %d 次" % n)
                if rc == 0 and self.outputs_exist(c):
                    break
            else:
                return R(FAILED, "抓取两次都没成功：" + "；".join(key_lines(out, 3)))
        return self.verify(c)

    def verify(self, c):
        raw = c.p("01_获取/raw.jsonl")
        n, social = 0, 0
        with open(raw, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                n += 1
                if '"layer": "social"' in line or '"layer":"social"' in line:
                    social += 1
        stats = read_json(c.p("01_获取/每源统计.json"), []) or []
        fails = [s for s in stats if s.get("status") == "fail"]
        empty = [s for s in stats if s.get("status") == "empty"]
        warns = []
        if fails:
            warns.append("抓取失败的来源 %d 个：%s" % (len(fails), "、".join("%s（%s）" % (s.get("name"), (s.get("error") or "")[:40]) for s in fails[:6])))
        if n == 0:
            return R(FAILED, "一条也没抓到")
        if n < 150:
            warns.append("总条数只有 %d，比平时（400–750）明显偏少" % n)
        note = ""
        if social == 0:
            note, w = self.ainews_zero(stats)
            if w:
                warns.append(w)
        return R(DONE, "%d 条（社交信号 %d）；来源 %d 个，失败 %d、窗口内没有新条目 %d%s" % (n, social, len(stats), len(fails), len(empty),
                                                                          "；" + note if note else ""),
                 warns, extra={"条数": n})

    @staticmethod
    def ainews_zero(stats):
        """社交信号 0 条时分清原因（11-03 补）：AINews 窗口内没出新一期是常事，只写一句说明；
        抓到了新一期却一条没拆出来，才是"可能改版了"。返回 (说明, 提醒)，各自可能为空。"""
        a = next((s for s in stats if s.get("id") == "ainews"), None)
        if a is None:
            return "", "AINews 没拆出社交信号（0 条），每源统计里也没有 AINews 这一项，可能改版了（经验 A7）"
        if a.get("status") == "fail":
            return "", "AINews 抓取失败（%s），所以没有社交信号" % ((a.get("error") or "")[:40] or "原因见每源统计")
        if a.get("status") == "empty" or not a.get("in_window"):
            last = (a.get("newest") or "")[:10]
            return "AINews 窗口内没出新一期%s，所以没有社交信号" % ("（最新一期 %s）" % last if last else ""), ""
        return "", "AINews 窗口内有 %s 期，却没拆出社交信号（0 条），可能改版了（经验 A7）" % a.get("in_window")


# ================================================================ 2 粗筛归并
class Cluster(Step):
    no, key, name = 2, "cluster", "粗筛归并"
    adopt, stale_rerun = True, True
    timeout = 1200
    check_text = "粗筛保留条数、归并后的事件数（candidates.json 的 events）"
    fix_text = "出错再跑一次；还不行停下来叫人。事件太少只提醒（归并误差靠选题时判断，经验 B1–B4）"

    def outputs(self, c):
        return ["01_获取/prefilter.jsonl", "02_选题/candidates.json"]

    def inputs(self, c):
        return ["01_获取/raw.jsonl"]

    def commands(self, c):
        if c.default_issue:
            return [c.py(PIPE / "prefilter.py", "--day", c.day), c.py(PIPE / "cluster.py", "--day", c.day)]
        return [c.py(HELPERS, "cluster", "--issue-dir", c.issue)]

    def plan(self, c):
        return ["运行：" + c.show(x) for x in self.commands(c)] + ["约 30 秒，本机，不花钱"]

    def run(self, c, how):
        if how == "run":
            busy = running_scripts(["pipeline/prefilter.py --day %s" % c.day, "pipeline/cluster.py --day %s" % c.day])
            if busy and c.default_issue:
                return R(FAILED, "已经有一个粗筛／归并在跑（进程 %d），等它结束再来" % busy[0][0])
            ok, out = False, ""
            for n in (1, 2):
                ok = True
                for cmd in self.commands(c):
                    rc, out = c.run(self, cmd, "第 %d 次" % n)
                    if rc != 0:
                        ok = False
                        break
                if ok and self.outputs_exist(c):
                    break
            if not ok:
                return R(FAILED, "粗筛归并两次都没成功：" + "；".join(key_lines(out, 3)))
        d = read_json(c.p("02_选题/candidates.json"), {}) or {}
        ev = d.get("events") or []
        st = d.get("stats") or {}
        warns = ["事件只有 %d 个，偏少" % len(ev)] if len(ev) < 20 else []
        if not ev:
            return R(FAILED, "candidates.json 里一个事件也没有")
        return R(DONE, "粗筛保留 %s 条，归并成 %s 个事件，取热度前 %d 个当候选" % (st.get("n_kept", "?"), st.get("n_events", "?"), len(ev)),
                 warns)


# ================================================================ 3 事件库入库
class Ingest(Step):
    no, key, name = 3, "ingest", "事件库入库"
    timeout = 600
    check_text = "库里这一期的批次文件写成了、条目数大于 0"
    fix_text = "出错再跑一次；还不行只提醒（不影响当天出刊，周末汇总会少这一天）"

    def batch(self, c):
        return c.db / "批次" / ("%s.json" % c.day)

    def outputs(self, c):
        return [str(self.batch(c))]

    def inputs(self, c):
        return ["01_获取/prefilter.jsonl", "02_选题/candidates.json"]

    def command(self, c):
        if c.default_issue:
            return c.py(PIPE / "event_db.py", "ingest", "--day", c.day, "--db", c.db)
        return c.py(PIPE / "event_db.py", "ingest", "--dir", c.issue, "--label", c.day, "--kind", "issue",
                    "--date", c.day, "--db", c.db)

    def plan(self, c):
        return ["运行：" + c.show(self.command(c)), "库：%s" % rel(c.db)]

    def run(self, c, how):
        busy = running_scripts(["event_db.py ingest --day %s" % c.day])
        if busy and c.default_issue:
            return R(FAILED, "已经有一个入库在跑（进程 %d），等它结束再来" % busy[0][0])
        out = ""
        for n in (1, 2):
            rc, out = c.run(self, self.command(c), "第 %d 次" % n)
            if rc == 0 and self.batch(c).exists():
                break
        else:
            return R(FAILED, "入库没成功（不影响今天出刊，周末汇总会少这一天）：" + "；".join(key_lines(out, 2)), go_on=True)
        b = read_json(self.batch(c), {}) or {}
        return R(DONE, "条目 %s、讲过 %d、事件卡 %d → %s" % (b.get("n_items"), len(b.get("covered") or []),
                                                     len(b.get("cards") or []), rel(self.batch(c))))


# ================================================================ 4 选题（半自动）
class Select(Step):
    no, key, name = 4, "select", "选题"
    who = "Claude（会话里选）＋程序自查"
    kind = "半自动"
    adopt, stale_rerun = True, False
    check_text = ("run_mimo.py check：条数区间、主线 2–3 条、热点要闻挂主线、专业雷达最多 1 条、主题色和关系词在词表里、"
                  "中国相关不少于三成；今日一词近 30 天讲过的要标 repeat_of、中文名沿用往期（term_history.py）；周末另查深度那一题")
    fix_text = ("第一次没过：停下，把问题清单交回选题的人改；改过还不过：只是条数、比例、今日一词这类软规则就放宽、照常往下"
                "（今日一词第 7 步还会再查稿子），其余（主线、重复、词表）停下来叫人")

    def outputs(self, c):
        return [LINEUP]

    def rm(self, c, stage):
        return c.py(PIPE / "run_mimo.py", stage, "--day", c.day, "--edition", c.edition, "--run-dir", c.issue, "--db", c.db)

    def plan(self, c):
        lines = []
        if not c.p("02_选题/candidates_compact.json").exists():
            lines.append("先运行（程序，不花钱）：" + c.show(self.rm(c, "compact")))
        if not c.p(LINEUP).exists():
            lines.append("然后停下等你：在会话里按 pipeline/prompts/选题.md 写 02_选题/最终选题.json")
        lines.append("自查：" + c.show(self.rm(c, "check")))
        return lines

    def plan_adopt(self, c):
        return ["只做自查：" + c.show(self.rm(c, "check"))]

    def todo(self, c):
        weekend = c.edition in ("saturday_deep", "sunday_deep")
        t = ["在 Claude Code 会话里选题（主笔 Claude）：",
             "  指令：pipeline/prompts/选题.md（周末看第八节）",
             "  读：%s" % rel(c.p("02_选题/candidates_compact.json")),
             "  再读：%s（往期今日一词：近 30 天讲过的尽量不再选，中文名沿用；规则在选题.md 第三节）" % rel(c.p(TERMS))]
        if weekend:
            t.append("  周末再读：02_选题/本周话题.md、%s" % ("留给周日.json（周六不碰它）" if c.edition == "saturday_deep" else "周日候选.json"))
        t += ["  写：%s，和给人看的 02_选题/选题说明.md" % rel(c.p(LINEUP)),
              "写完再运行：%s" % c.again()]
        return t

    def parse_check(self, out):
        probs = [x.strip()[2:].strip() for x in out.splitlines() if x.strip().startswith("- ")]
        passed = "全部通过" in out
        return passed, probs

    @staticmethod
    def parse_notes(out):
        return [x.strip()[3:].strip() for x in (out or "").splitlines() if x.strip().startswith("提醒：")][:6]

    def run(self, c, how):
        if not c.p(LINEUP).exists():
            cc = c.p("02_选题/candidates_compact.json")
            cand = c.p("02_选题/candidates.json")
            if not cc.exists() or (cand.exists() and cand.stat().st_mtime > cc.stat().st_mtime):
                rc, out = c.run(self, self.rm(c, "compact"), "压缩候选")
                if rc != 0:
                    return R(FAILED, "候选压缩（run_mimo.py compact）没成功：" + "；".join(key_lines(out, 3)))
            warns = []
            if not c.p(TERMS).exists():         # compact 以前跑过、没写这份的（11-03 以前）：单独补
                rc, out = c.run(self, c.py(PIPE / "term_history.py", "write", "--run-dir", c.issue), "往期今日一词")
                if rc != 0:
                    warns.append("往期今日一词没写成（选题时看不到往期讲过哪些词，第 4、7 步仍会查）：" + "；".join(key_lines(out, 2)))
            return R(WAITING, "等你在会话里选题", warns, todo=self.todo(c))
        try:
            json.loads(c.p(LINEUP).read_text(encoding="utf-8"))
        except ValueError as e:
            return R(WAITING, "最终选题.json 不是合法的 JSON：%s" % e, todo=["改好 %s 再运行：%s" % (rel(c.p(LINEUP)), c.again())])
        rc, out = c.run(self, self.rm(c, "check"), "选题自查")
        passed, probs = self.parse_check(out)
        notes = self.parse_notes(out)
        if rc == 0 and passed:
            return R(DONE, "选题自查全部通过", notes)
        if rc != 0 and not probs:
            return R(FAILED, "选题自查程序出错：" + "；".join(key_lines(out, 3)))
        soft = [p for p in probs if re.search(r"条，规定|不到三成|今日一词|repeat_of", p)]
        n, seen = _fail_round(c, self.key, fp_file(c.p(LINEUP)))
        if n >= 2 and len(soft) == len(probs):
            return R(DONE, "放宽：改过一次仍有 %d 处软规则没过，照常往下" % len(probs), probs + notes, extra={"没过时的产出指纹": seen})
        return R(WAITING, "选题自查有 %d 处要改" % len(probs), probs + notes, extra={"没过时的产出指纹": seen},
                 todo=["按下面的问题改 %s（第 %d 轮）：" % (rel(c.p(LINEUP)), n)] + ["  - " + p for p in probs] +
                      ["改完再运行：%s" % c.again()])


# ================================================================ 5 事件卡
class Cards(Step):
    no, key, name = 5, "cards", "事件卡"
    who = "MiMo 抽事实（免费）＋程序逐字核对"
    adopt, stale_rerun = True, True
    timeout = 3600
    check_text = ("逐字核对（run_mimo.py 的 verify：每条事实、数字、原话的原文片段要在材料里找到，找不到的自动删掉）；"
                  "选题里每条都有卡；卡里通过核对的条数")
    fix_text = ("核对不上的条目自动删（现行）；整张卡没有通过核对的事实：提醒降为快讯或换题；"
                "MiMo 出错再跑一次，还不行停下来叫人（备用 Claude Sonnet 还没接）。离线时不能做卡")

    def outputs(self, c):
        return [CARDS, "03_事件卡/核对.md", "04_文稿/写稿输入.json"]

    def inputs(self, c):
        return [LINEUP]

    def rm(self, c, stage):
        return c.py(PIPE / "run_mimo.py", stage, "--day", c.day, "--edition", c.edition, "--run-dir", c.issue, "--db", c.db)

    def plan(self, c):
        return ["运行：" + c.show(self.rm(c, "cards")) + "（MiMo，免费期；约 2–5 分钟）",
                "再运行：" + c.show(self.rm(c, "assemble")) + "（程序，写 04_文稿/写稿输入.json）"]

    def run(self, c, how):
        warns = []
        if how == "run":
            if c.offline:
                return R(FAILED, "离线模式不能调 MiMo 做事件卡")
            since = iso()
            out = ""
            for n in (1, 2):
                rc, out = c.run(self, self.rm(c, "cards"), "第 %d 次" % n)
                if rc == 0 and c.p(CARDS).exists():
                    break
            else:
                return R(FAILED, "MiMo 做事件卡两次都没成功（备用 Claude Sonnet 还没接上），停下来叫人：" + "；".join(key_lines(out, 3)))
            tok, calls = mimo_tokens_since(c.p("03_事件卡/mimo_用量.json"), since)
            c.ledger.add(self.name, "MiMo", 0.0, rel(c.p("03_事件卡/mimo_用量.json")), "免费期，只记 token", token数=tok, 次数=calls)
            rc, out = c.run(self, self.rm(c, "assemble"), "写稿输入")
            if rc != 0:
                return R(FAILED, "写稿输入（run_mimo.py assemble）没成功：" + "；".join(key_lines(out, 3)))
        cards = read_json(c.p(CARDS), []) or []
        lineup = read_json(c.p(LINEUP), {}) or {}
        want = []
        for sec in ("hot", "brief", "flash", "teaser"):
            want += [x.get("event_id") for x in lineup.get(sec) or [] if x.get("event_id")]
        have = {x.get("event_id") for x in cards}
        miss = [e for e in want if e not in have]
        nfacts = sum(len(x.get("facts") or []) + len(x.get("numbers") or []) for x in cards)
        thin = [x.get("event_id") for x in cards if not (x.get("facts") or x.get("numbers"))]
        if miss:
            warns.append("选题里有 %d 条没有事件卡：%s" % (len(miss), "、".join(miss)))
        if thin:
            warns.append("这几张卡没有一条通过核对的事实，建议降为快讯或换题：%s" % "、".join(thin))
        if not cards:
            return R(FAILED, "cards_写稿用.json 里一张卡也没有")
        return R(DONE, "%d 张卡，%d 条事实和数字通过逐字核对" % (len(cards), nfacts), warns)


# ================================================================ 6 写稿（半自动）
class Write(Step):
    no, key, name = 6, "write", "写稿"
    who = "Claude（会话里写）"
    kind = "半自动"
    adopt, stale_rerun = True, False
    check_text = "播客（或对谈）稿、网页稿、视频分镜三份都在；两份 JSON 能读"
    fix_text = "缺哪份就停下，说清用哪份指令、写到哪；写完再跑。主笔自动切换（订阅令牌 → API → MiMo → 数据版）下一步接 claude -p"

    def outputs(self, c):
        return [c.ed["播客稿"], WEB_DRAFT, STORYBOARD]

    def plan(self, c):
        miss = [o for o in self.outputs(c) if not c.p(o).exists()]
        return (["停下等你写：" + "、".join(miss)] if miss else []) + ["指令：" + "；".join(
            "%s＝%s" % (k, "＋".join(v)) for k, v in c.ed["指令"].items())]

    def todo(self, c, miss):
        names = {c.ed["播客稿"]: "播客", WEB_DRAFT: "网页", STORYBOARD: "视频"}
        t = ["在 Claude Code 会话里写稿（主笔 Claude；事实只能来自 03_事件卡/cards_写稿用.json，输入是 04_文稿/写稿输入.json）："]
        for o in miss:
            k = names[o]
            t.append("  %s → %s；指令 pipeline/prompts/%s" % (k, rel(c.p(o)), "＋".join(c.ed["指令"][k])))
        t.append("  （这一期是%s。网页稿要带 page 对象；视频分镜不超过 3 分钟）" % c.ed["名字"])
        t.append("写完再运行：%s（会从第 7 步稿子检查接着跑）" % c.again())
        return t

    def run(self, c, how):
        miss = [o for o in self.outputs(c) if not c.p(o).exists()]
        if miss:
            return R(WAITING, "等你在会话里写：" + "、".join(Path(m).name for m in miss), todo=self.todo(c, miss))
        for o in (WEB_DRAFT, STORYBOARD):
            try:
                json.loads(c.p(o).read_text(encoding="utf-8"))
            except ValueError as e:
                return R(WAITING, "%s 不是合法的 JSON：%s" % (Path(o).name, e), todo=["改好再运行：%s" % c.again()])
        pod = c.p(c.ed["播客稿"]).read_text(encoding="utf-8")
        return R(DONE, "三份稿子都在（播客稿 %d 个汉字）" % _han(pod))


# ================================================================ 7 稿子检查
class Check(Step):
    no, key, name = 7, "check", "稿子检查"
    timeout = 900
    check_text = ("读音表（lexicon_check，能改的自动改）；数字、引语、英文名都在事件卡里、口吻、字数和估计时长（script_check）；"
                  "周末另跑 weekend_check；视频分镜的事实、数字、触发词、旁白禁用说法、不超过 3 分钟（video3_build 的配音前检查）；"
                  "网页稿上每个数字都在事件卡里（make_issue_v3 严格模式预检）；今日一词和近 30 天的重复时要标 repeat_of、"
                  "播客点明哪天讲过、中文名沿用往期（term_history.py check）；开场、收尾、速览和小结卡里的易歧义词只提醒（ambiguity_check，11-09 加）")
    fix_text = ("读音：自动改（改前备份在 logs/改前备份/）；第一次有'要改'：停下，把问题清单交回主笔改；改过还不过：只差长短的放宽"
                "（配音时也不再按时长拦）；只差读音表'首次补中文'（11-03 加）的也放宽，照原稿配音、时长照常查；数字、引语、禁用说法、分镜核不上的停下来叫人；网页数字核不上时可以加 --lenient 放宽")

    def outputs(self, c):
        return ["logs/检查_稿子.json"]

    def inputs(self, c):
        return [c.ed["播客稿"], WEB_DRAFT, STORYBOARD, CARDS]

    def plan(self, c):
        p = c.p(c.ed["播客稿"])
        lines = ["读音表：" + c.show(c.py(PIPE / "lexicon_check.py", p, "--json")) + "（要改时加 --fix 自动改）",
                 "稿子：" + c.show(c.py(HELPERS, "script-check", "--script", p, "--cards", c.p(CARDS), "--day-type", c.ed["日子"]))]
        if c.ed["周末检查"]:
            lines.append("周末：" + c.show(c.py(PIPE / "weekend_check.py", p, "--edition", c.ed["周末检查"], "--json")))
        lines += ["分镜：" + c.show(c.py(HELPERS, "storyboard", "--issue-dir", c.issue)),
                  "网页数字预检：make_issue_v3.py 严格模式，配置写到 logs/网页配置_预检.py",
                  "今日一词：" + c.show(self.term_cmd(c)),
                  "易歧义词（只提醒）：" + c.show(self.amb_cmd(c))]
        return lines

    def amb_cmd(self, c):
        return c.py(PIPE / "ambiguity_check.py", "--script", c.p(c.ed["播客稿"]), "--storyboard", c.p(STORYBOARD), "--json")

    def term_cmd(self, c):
        return c.py(PIPE / "term_history.py", "check", "--issue-dir", c.issue, "--edition", c.edition, "--json")

    # 这一组检查第 9 步改完稿还要再跑一遍，所以单独写成函数
    def suite(self, c):
        items, pod = [], c.p(c.ed["播客稿"])
        # 1 读音表
        rc, out = c.run(self, c.py(PIPE / "lexicon_check.py", pod, "--json"), "读音表")
        lx = _json_tail(out)
        fixed = 0
        if lx is not None and lx.get("要改"):
            bak = c.logs / "改前备份" / ("%s.%s" % (pod.name, c.run_id))
            bak.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pod, bak)
            rc, fout = c.run(self, c.py(PIPE / "lexicon_check.py", pod, "--fix", "--json"), "读音表自动改")
            rc, out = c.run(self, c.py(PIPE / "lexicon_check.py", pod, "--json"), "读音表复查")
            # 只数真改了的地方（--fix 报的"已自动改"）；只提醒、首次补中文这类不能自动改的不算（11-03 改：以前按要改的条数数，会多报）
            fj = _json_tail(fout)
            fixed = (len(fj.get("已自动改") or []) if isinstance(fj, dict) and "已自动改" in fj
                     else sum(1 for r in lx.get("要改") or [] if r.get("自动改")))
            lx = _json_tail(out)
        if lx is None:
            items.append({"名字": "读音表", "要改": ["lexicon_check 没给出结果：" + "；".join(key_lines(out, 2))], "软": []})
        else:
            row = lambda r: "第 %s 行 %s" % (r.get("行"), (r.get("说明") or r.get("原文") or ""))   # noqa: E731
            # "首次补中文"（英文原名第一次没补中文名，11-03 用户定）算软的：和"只差长短"一样，第一次交回主笔改，
            # 改过还不过就放宽、照常往下（用户出差，不能因为少补一个中文名卡住自动运行）
            # 11-06 晚加：配音单位开头夹心（一块、一轮开口就是英文名，后面只夹两三个字又接英文）只提醒，写稿那步改成中文起句；
            # 弱的（英文开头但后面中文够长）不摘
            opening = ["第 %s 行 配音单位开头：%s —— %s" % (r.get("行"), r.get("原文"), r.get("说明"))
                       for r in lx.get("提醒") or [] if r.get("种类") == "配音单位开头夹心"]
            items.append({"名字": "读音表", "要改": [row(r) for r in lx.get("要改") or []],
                          "软": [row(r) for r in lx.get("要改") or [] if r.get("种类") == "首次补中文"],
                          "提醒": (["自动改了 %d 处（改前备份在 logs/改前备份/）" % fixed] if fixed else []) + opening[:4],
                          "表里还没有": len(lx.get("表里还没有") or [])})
        # 2 稿子
        rc, out = c.run(self, c.py(HELPERS, "script-check", "--script", pod, "--cards", c.p(CARDS), "--day-type", c.ed["日子"]), "稿子")
        sc = _json_tail(out)
        if sc is None:
            items.append({"名字": "稿子", "要改": ["script_check 没给出结果：" + "；".join(key_lines(out, 2))]})
        else:
            # 11-06 晚加：script_check 按配音程序同一套估法算出"成片时长不在区间里"时，原来只进"请人工看"，第 7 步照过，
            # 到第 11 步配音前才被拦下（DurationOutOfRange → 停下等人）。周末尤其容易：周日稿 3,500–3,580 字、周六稿
            # 2,915–2,950 字时 weekend_check 按字数估是过的，配音程序估却不过。现在把这一条当"要改"里的软项（类＝长度）：
            # 第一次交回主笔改长短，改过还不过就按"只差长短"放宽，配音时加 --no-duration-gate，不在第 11 步卡住。
            #   "软"的写法要和"要改"一字不差（judge 按原句对哪几条是软的；原来两边写法不同，稿子这一项的软规则对不上）
            longs = [r for r in sc.get("请人工看") or [] if r.get("类") == "长度"]
            must = (sc.get("要改") or []) + longs
            fmt = lambda r: "%s [%s] %s —— %s" % ("第 %s 行" % r["行"] if r.get("行") else "全稿", r.get("类"),   # noqa: E731
                                                 r.get("原文"), r.get("说明"))
            items.append({"名字": "稿子",
                          "要改": [fmt(r) for r in must],
                          "软": [fmt(r) for r in must if re.search(r"长度|字数|时长", str(r.get("类")))],
                          "请人工看": len(sc.get("请人工看") or []) - len(longs),
                          "概况": (sc.get("概况") or {}).get("长度")})
        # 3 周末
        if c.ed["周末检查"]:
            rc, out = c.run(self, c.py(PIPE / "weekend_check.py", pod, "--edition", c.ed["周末检查"], "--json"), "周末规则")
            wk = _json_tail(out)
            if wk is None:
                items.append({"名字": "周末规则", "要改": ["weekend_check 没给出结果：" + "；".join(key_lines(out, 2))]})
            else:
                must = [_txt(r) for r in wk.get("要改") or []]
                items.append({"名字": "周末规则", "要改": must, "软": [m for m in must if re.search(r"字数|时长|分钟", m)],
                              "提醒": [_txt(r) for r in wk.get("提醒") or []][:6],
                              "估计分钟": (wk.get("数据") or {}).get("估计分钟")})
        # 4 视频分镜
        rc, out = c.run(self, c.py(HELPERS, "storyboard", "--issue-dir", c.issue), "视频分镜")
        items.append({"名字": "视频分镜", "要改": [] if rc == 0 else (key_lines(out, 6) or tail(out, 4)),
                      "提醒": [x.strip() for x in out.splitlines() if x.strip().startswith("提醒")][:8]})
        # 5 网页数字预检
        pre = c.logs / "网页配置_预检.py"
        args = ["--day", c.day, "--issue-dir", c.issue, "--podcast", NO_PODCAST, "--out", pre] + (["--lenient"] if c.lenient else [])
        rc, out = c.run(self, c.py(TOOLS / "make_issue_v3.py", *args), "网页数字预检")
        bad = [x.strip() for x in out.splitlines() if re.search(r"找不到|核对不上|对不上", x)]
        items.append({"名字": "网页数字", "要改": [] if rc == 0 else (bad[:10] or key_lines(out, 4))})
        # 6 今日一词（11-03 加）：和近 30 天的重复时，要标 repeat_of、播客点明哪天讲过、中文名沿用往期；周末的名词解释只提醒
        rc, out = c.run(self, self.term_cmd(c), "今日一词")
        th = _json_tail(out)
        if th is None:
            items.append({"名字": "今日一词", "要改": ["term_history 没给出结果：" + "；".join(key_lines(out, 2))]})
        else:
            items.append({"名字": "今日一词", "要改": th.get("要改") or [], "提醒": (th.get("提醒") or [])[:4]})
        # 7 易歧义词（11-09 加）：开场、收尾、速览和小结卡里出现小词表（pipeline/prompts/易歧义词.yaml）里的词，只提醒、不拦；
        #   这些词放对了地方没问题，要人读一遍那一句。按词归并：每个词一行，写几处、第一处在哪；完整的在 logs/检查_稿子.json
        rc, out = c.run(self, self.amb_cmd(c), "易歧义词")
        am = _json_tail(out) or {}
        by_word = {}
        for r in am.get("提醒") or []:
            by_word.setdefault(r.get("词"), []).append(r)
        items.append({"名字": "易歧义词（只提醒）", "要改": [],
                      "提醒": ["「%s」%d 处，如 %s：%s（%s）" % (w, len(rs), rs[0].get("位置"), rs[0].get("原文"), rs[0].get("说明"))
                             for w, rs in by_word.items()][:4] + ["注意：" + x for x in am.get("说明") or []][:1],
                      "明细": am.get("提醒") or []})
        must = [(it["名字"], m) for it in items for m in it.get("要改") or []]
        soft = [(it["名字"], m) for it in items for m in it.get("软") or []]
        res = {"时间": iso(), "检查": items, "要改合计": len(must)}
        write_json(c.p("logs/检查_稿子.json"), res)
        return res, must, soft

    def judge(self, c, res, must, soft, step_key=None):
        warns = []
        for it in res["检查"]:
            for w in it.get("提醒") or []:
                warns.append("%s：%s" % (it["名字"], w))
            if it.get("请人工看"):
                warns.append("%s：%d 处请人工看（见 logs/检查_稿子.json）" % (it["名字"], it["请人工看"]))
        summary = "；".join("%s %s" % (it["名字"], "过了" if not it.get("要改") else "%d 处要改" % len(it["要改"]))
                           for it in res["检查"])
        if not must:
            return R(DONE, summary, warns[:12])
        cur = "|".join(fp_file(c.p(i)) or "" for i in self.inputs(c))
        n, seen = _fail_round(c, step_key or self.key, cur)
        hard = [m for m in must if m not in soft]
        if n >= 2 and not hard:
            # 软的有两种（11-03 起）：长短（稿子、周末规则的字数、时长）放宽时配音也不再按时长拦；
            # 读音表的"首次补中文"只是照原稿往下，配音时长检查照常，不打"放宽时长"
            longs = [m for k, m in soft if k != "读音表" and (k, m) in must]
            zhs = [m for k, m in soft if k == "读音表" and (k, m) in must]
            if longs:
                why = "只差长短（%s）" % "；".join(longs)[:120]
                if zhs:
                    why += "和第一次补中文名（%s）" % "；".join(zhs)[:80]
                return R(DONE, "放宽：改过一次仍%s，照常往下，配音时不再按时长拦" % why,
                         warns[:12], extra={"放宽时长": True, "没过时的产出指纹": seen})
            return R(DONE, "只差第一次补中文名，放宽：照原稿配音（配音时长检查照常），写自检时提一句（%s）" % "；".join(zhs)[:120],
                     warns[:12], extra={"没过时的产出指纹": seen})
        todo = ["把下面的问题交回主笔改稿（在会话里改 %s 等），第 %d 轮：" % (rel(c.p(c.ed["播客稿"])), n)]
        todo += ["  - [%s] %s" % (k, m) for k, m in must[:20]]
        todo += ["改完再运行：%s" % c.again()]
        return R(WAITING, "稿子检查有 %d 处要改（%s）" % (len(must), summary), warns[:12], todo=todo,
                 extra={"没过时的产出指纹": seen})

    def run(self, c, how):
        res, must, soft = self.suite(c)
        return self.judge(c, res, must, soft)


def _json_tail(out):
    """命令输出里最后一段 JSON（前面可能有几行说明）。"""
    s = (out or "").strip()
    i = s.find("{")
    while i != -1:
        try:
            return json.loads(s[i:])
        except ValueError:
            i = s.find("{", i + 1)
    return None


def _txt(r):
    if isinstance(r, dict):
        return "；".join("%s" % v for v in r.values() if v not in (None, ""))[:160]
    return str(r)[:160]


# ================================================================ 8 独立审读（半自动）
class Review(Step):
    no, key, name = 8, "review", "独立审读"
    who = "另开一个只读的 Claude（新会话或子代理）"
    kind = "半自动"
    adopt, stale_rerun = True, False
    check_text = "审读意见.md 在；第一行写了'必须改：N'（旧格式数'## 必须改'下面的条目）"
    fix_text = "不在就停下，说清怎么审、写到哪。放在配音之前：审出必须改的，改完再配音，不用重配（经验 G6）"

    def outputs(self, c):
        return ["审读意见.md"]

    def plan(self, c):
        return [] if c.p("审读意见.md").exists() else ["停下等你：另开一个只读审读，写 审读意见.md"]

    def run(self, c, how):
        p = c.p("审读意见.md")
        if not p.exists():
            return R(WAITING, "等一份独立审读", todo=[
                "另开一个只读的 Claude（新会话或子代理，别用写稿的那个）做独立审读：",
                "  对照 03_事件卡/cards_写稿用.json，查 %s、04_文稿/claude_网页.json、04_文稿/视频v3_分镜.json；" % c.ed["播客稿"],
                "  查事实分寸：条件说成已发生、先后说反、删了限定词、出处挂错、判断前后不一致；",
                "  附上已定规矩（文档/经验/问题与解决办法.md 第十五节），和规矩冲突的不算问题；",
                "  写到 %s，第一行写'必须改：N'，再分'必须改''建议改''可以更好'三节。" % rel(p),
                "写完再运行：%s" % c.again()])
        n = must_fix_count(p.read_text(encoding="utf-8"))
        if n is None:
            return R(DONE, "审读意见在，但没写清必须改几条，按'有'处理", ["审读意见.md 第一行请写'必须改：N'"], extra={"必须改": -1})
        return R(DONE, "必须改 %d 条" % n, extra={"必须改": n})


def must_fix_count(text):
    m = re.search(r"必须改\s*[：:]\s*(\d+)", text)
    if m:
        return int(m.group(1))
    sec = re.search(r"^##\s*必须改.*?$(.*?)(?=^##\s)", text, re.M | re.S)
    if sec:
        body = sec.group(1)
        n = len(re.findall(r"^###\s", body, re.M)) or len(re.findall(r"^\s*\d+[.、]\s", body, re.M))
        return n
    return None


# ================================================================ 9 改稿（半自动）
class Revise(Step):
    no, key, name = 9, "revise", "改稿"
    who = "Claude（会话里改）＋程序复查"
    kind = "半自动"
    adopt, stale_rerun = True, False
    check_text = "审读没有必须改的就直接过；有的话要有 审读处理*.md（逐条怎么处理的），改完的稿子再过一遍第 7 步全部检查"
    fix_text = "没有处理记录就停下等改稿；复查没过同第 7 步（交回主笔改，改过还只差长短就放宽）"

    def must(self, c):
        rec = (c.state.step("review") or {}).get("附加") or {}
        if "必须改" in rec:
            return rec["必须改"]
        p = c.p("审读意见.md")
        return must_fix_count(p.read_text(encoding="utf-8")) if p.exists() else None

    def handled(self, c):
        return sorted(c.issue.glob("审读处理*.md"))

    def outputs_exist(self, c):
        return self.must(c) == 0 or bool(self.handled(c))

    def outputs(self, c):
        h = self.handled(c)
        return [h[0].name] if h else []

    def plan(self, c):
        if self.must(c) == 0:
            return ["审读没有必须改的，直接过"]
        return (["停下等你改稿，处理记录写进 审读处理.md"] if not self.handled(c) else []) + ["改完重跑第 7 步那一组检查"]

    def run(self, c, how):
        n = self.must(c)
        if n == 0:
            return R(DONE, "审读没有必须改的，不用改稿")
        if not self.handled(c):
            return R(WAITING, "等你按审读意见改稿", todo=[
                "在会话里按 审读意见.md 改稿：必须改的都改；和已定规矩冲突的不采纳，写明理由；",
                "  只改稿子（%s、04_文稿/claude_网页.json、04_文稿/视频v3_分镜.json），不添新事实；" % c.ed["播客稿"],
                "  逐条怎么处理的写进 %s；" % rel(c.p("审读处理.md")),
                "改完再运行：%s（会再跑一遍稿子检查）" % c.again()])
        chk = c.steps["check"]
        res, must, soft = chk.suite(c)
        r = chk.judge(c, res, must, soft, step_key=self.key)
        if r.status == DONE:
            c.record_extra("check", res, chk)             # 第 7 步的记录跟着更新，免得下次又说"上游变了"
            return R(DONE, "处理记录 %s；改后复查：%s" % (self.handled(c)[0].name, r.msg), r.warns, extra=r.extra)
        r.msg = "改后复查没过：" + r.msg
        return r


# ================================================================ 10 配图（半自动）
class Images(Step):
    no, key, name = 10, "images", "配图"
    who = "先 agy（Google AI Pro 订阅），没成再 Codex（ChatGPT 订阅）；会话里生成，都不另花钱"
    kind = "半自动"
    adopt, stale_rerun = True, False
    check_text = ("网页要的图（日卡、今日一词、头条、要闻、深度那一题）和视频分镜 image_requests 要生成的图都在 06_配图/；"
                  "缺图时顺带跑 agy_image.py --check，报告里写明今天 agy 能不能用（只查登录和额度，不画图、不花额度）")
    fix_text = ("缺图：停下等你在会话里生成——先 agy（site/tools/agy_image.py；视频图 video3_images.py 自己先 agy），"
                "没成或画面不合格（可读文字、品牌产品、真人、禁用套路、跑题）改用 Codex，Codex 两次都不行就加 --skip-images（离线时自动这样）"
                "——网页缺图画主题色抽象封面，视频那几块不带图（现行兜底）")

    def agy_status(self, c):
        """今天 agy 能不能用：跑一次 agy_image.py --check（只查登录和额度）。返回 (能用, 一句话)；离线不查。一次运行只查一次。"""
        if c.offline:
            return None, "离线，没查 agy"
        if getattr(c, "_agy_status", None) is None:
            rc, out = c.quiet(c.py(TOOLS / "agy_image.py", "--check"), timeout=150)
            line = next((x.strip() for x in out.splitlines() if x.strip()[:1] in ("✓", "✗")), out.strip()[-120:]).lstrip("✓✗ ").strip()
            gem = re.findall(r"Gemini Models (weekly|5h) 剩 ([\d.]+%)", line)          # 画图和调度都记在 Gemini 这一组
            detail = ("Gemini 额度 " + "，".join("%s 剩 %s" % (w, v) for w, v in gem)) if gem else line[:120]
            head = {0: "agy 今天能用", 3: "agy 额度用完", 4: "agy 没登录或登录过期", 7: "本机没有 agy"}.get(rc, "agy 检查出错（退出码 %s）" % rc)
            c._agy_status = (rc == 0, "%s（%s）" % (head, detail))
        return c._agy_status

    def wanted(self, c):
        web = read_json(c.p(WEB_DRAFT), {}) or {}
        want = ["card"]
        for s in web.get("sections") or []:
            k = s.get("kind")
            if k == "term":
                want.append("term")
            elif k in ("headline", "brief", "deep"):
                want += [str(it.get("id")).lower() for it in s.get("items") or [] if it.get("id")]
        sb = read_json(c.p(STORYBOARD), {}) or {}
        vid = [r.get("id") for r in sb.get("image_requests") or [] if r.get("id") and not r.get("commons")]
        return list(dict.fromkeys(want)), vid

    def missing(self, c):
        want, vid = self.wanted(c)
        have = {f.stem.lower() for f in c.p("06_配图").glob("*") if f.suffix.lower() in IMG_EXT} if c.p("06_配图").is_dir() else set()
        vhave = {f.stem for f in c.p("06_配图/视频").glob("*") if f.suffix.lower() in IMG_EXT} if c.p("06_配图/视频").is_dir() else set()
        return [w for w in want if w not in have], [v for v in vid if v not in vhave], want, vid

    def outputs_exist(self, c):
        mw, mv, _, _ = self.missing(c)
        return not mw and not mv

    def plan(self, c):
        mw, mv, want, vid = self.missing(c)
        if not mw and not mv:
            return ["网页 %d 张、视频 %d 张都在" % (len(want), len(vid))]
        if c.offline or c.skip_images:
            how = "跳过，用程序画的封面"
        else:
            ok, note = self.agy_status(c)
            how = "停下等你生成：先 agy，没成再 Codex，都不行 --skip-images（%s）" % (note if ok else note + "，这次直接用 Codex")
        return ["缺：网页 %s；视频 %s → %s" % ("、".join(mw) or "无", "、".join(mv) or "无", how)]

    def plan_adopt(self, c):
        return self.plan(c)

    def run(self, c, how):
        mw, mv, want, vid = self.missing(c)
        if not mw and not mv:
            return R(DONE, "网页 %d 张、视频 %d 张都在" % (len(want), len(vid)))
        msg = "缺图：网页 %s；视频 %s" % ("、".join(mw) or "无", "、".join(mv) or "无")
        if c.offline or c.skip_images:
            return R(SKIPPED, msg + "。网页缺图画主题色抽象封面，视频那几块不带图", go_on=True,
                     extra={"缺网页配图": mw, "缺视频配图": mv})
        ok, note = self.agy_status(c)
        warns = [] if ok else ["%s：这一期配图直接用 Codex" % note]
        return R(WAITING, msg + "；" + note, warns, extra={"agy": note}, todo=[
            "在会话里生成配图（都走订阅，不另花钱；没有文字、商标、真人）：先 agy，没成再 Codex，Codex 两次都不行就 --skip-images。",
            "  今天：%s" % (note if ok else note + "，跳过 agy、直接用 Codex"),
            "  网页：放进 %s，文件名 %s（.png）；每张一条 agy_image.py 命令，Codex 后备命令也在 进度备忘.md'规矩'里配图那一行；" % (
                rel(c.p("06_配图")), "、".join(mw) or "无"),
            "  每张 agy 图都要打开看：有可读文字、可认出的品牌产品、真人、出现禁用套路（挂锁和钥匙、地球仪、发光大脑、机器人或人形、电路板纹、节点网、二进制、数据雨、连帽黑客；画面描述里要了也算）或明显跑题，就改用 Codex 重画，重画前先把画面描述里的禁用套路或消费设备主角改掉（和 文档/方案/每日自动运行.md 第 10 步一致，11-06 补）；",
            "  视频：%s" % ("运行 %s（它自己先 agy 再 Codex；只用 Codex 就在前面加 FD_IMAGE_BACKENDS=codex）" % c.show(
                c.py(TOOLS / "video3_images.py", c.issue)) if mv else "不缺"),
            "Codex 也失败两次：加 --skip-images 重跑（网页用主题色封面，视频那几块不带图）",
            "生成完再运行：%s" % c.again()])


# ================================================================ 11 配音
class Voice(Step):
    no, key, name = 11, "voice", "配音"
    who = "Gemini（花钱）；备用 MiMo 复刻（免费）"
    adopt, stale_rerun = True, True
    timeout = 5400
    check_text = ("配音程序自己的把关：对稿（多念漏念、字错率）、音高、音色、句子级找平、语速、成片时长；"
                  "fd 另管钱：本月 Gemini 到上限 90% 就整期走 MiMo 备用，这一期最多花 --budget-usd")
    fix_text = ("Gemini 出错或超预算：换 MiMo 备用（Shirley、Dylan 自己的复刻）；备用也不行：这一期出'数据版'（网页不带播客），"
                "报告开头写明；稿子长短不合要求（配音前估）：停，退回写稿；项目是禁用的那个：停，叫人")

    def outputs(self, c):
        s = c.ed["人声"]
        return ["%s/episode.mp3" % s, "%s/chapters.json" % s, "%s/qc.json" % s, "%s/voice.json" % VIDEO_VOICE]

    def inputs(self, c):
        return [c.ed["播客稿"], STORYBOARD, str(PROFILE)]

    # ---- 用哪个声音、给多少钱
    def decide(self, c):
        st = c.ledger.status()
        cap, spent = st["上限美元"], st["Gemini已记美元"]
        backup, why = False, ""
        if c.force_backup:
            backup, why = True, "命令行要求用备用"
        elif st["到90%"]:
            backup, why = True, "本月 Gemini 已记 $%.2f，到上限 $%.2f 的 %.0f%%" % (spent, cap, 100 * st["比例"])
        avail = 0.0 if c.offline else max(0.0, min(c.budget - c.ledger.issue_total("Gemini"), cap - spent))
        if not backup and not c.offline and avail < 0.02:
            backup, why = True, "这一期或本月剩下的钱不够（还剩 $%.3f）" % avail
        vid_b = round(min(0.10, avail * 0.25), 3)
        pod_b = round(max(0.0, avail - vid_b), 3)
        return {"用备用": backup, "原因": why, "播客预算": 0.0 if backup else pod_b, "视频预算": 0.0 if backup else vid_b,
                "本月已记": spent, "上限": cap}

    def pod_cmd(self, c, backup, budget, loose):
        e, pod = c.ed, c.p(c.ed["播客稿"])
        title = episode_title(c.day, c.edition)
        if e["配音方式"] == "单人":
            a = [PIPE / "tts.py", pod] + (["--use-backup"] if backup else ["--host", "Shirley"]) + [
                "--style-map", pod, "--chapter-wavs", "--out", c.p(e["人声"]), "--title", title,
                "--budget-usd", "%.3f" % budget, "--day-type", e["日子"]]
        else:
            a = [PIPE / "dialog_tts.py", pod, "--out", c.p(e["混音"]), "--speech-out", c.p(e["人声"]), "--no-mix",
                 "--title", title, "--budget-usd", "%.3f" % budget, "--day-type", e["日子"]] + (["--use-backup"] if backup else [])
        if loose:
            a.append("--no-duration-gate")
        return c.py(*a)

    def vid_cmd(self, c, backup, budget):
        return c.py(TOOLS / "video3_build.py", c.issue, "--stage", "voice", "--no-gen", "--budget-usd", "%.3f" % budget,
                    *(["--engine", "mimo"] if backup else []))

    def estimate(self, c):
        """只用来给 --dry-run 估钱：按配音程序 --plan 的估算（不调模型），缓存里已有的部分实际不花钱。"""
        price = gemini_price_out()
        pod = c.p(c.ed["播客稿"])
        est = {"播客": None, "视频": None}
        if pod.exists():
            if c.ed["配音方式"] == "对谈":
                rc, out = c.quiet(c.py(PIPE / "dialog_tts.py", pod, "--plan"))
                m = re.search(r"Gemini 估计 \$([\d.]+)", out)
                if m:
                    est["播客"] = round(float(m.group(1)) * 1.3, 3)
            else:
                rc, out = c.quiet(c.py(PIPE / "tts.py", pod, "--plan", "--host", "Shirley", "--style-map", pod))
                m = re.search(r"估计 ([\d.]+) 分钟\s*$", out.strip(), re.M)
                if m:
                    est["播客"] = round(float(m.group(1)) * 60 * 25 * price / 1e6 * 1.3, 3)
        else:
            mins = {"日常": 13, "周六": 11, "周日": 16}[c.ed["日子"]]
            est["播客"] = round(mins * 60 * 25 * price / 1e6 * 1.3, 3)
        nar = c.p(NARRATION)
        han = _han(nar.read_text(encoding="utf-8")) if nar.exists() else 420
        est["视频"] = round(han / 4.1 * 25 * price / 1e6 * 1.5, 3)
        return est

    def plan(self, c):
        d = self.decide(c)
        lines = []
        if d["用备用"]:
            lines.append("声音：整期改走 MiMo 备用（%s）；Gemini 预算 0" % d["原因"])
        else:
            lines.append("声音：主声音（Gemini）；这一期播客最多 $%.3f、视频旁白最多 $%.3f（本月已记 $%.2f / 上限 $%.2f）"
                         % (d["播客预算"], d["视频预算"], d["本月已记"], d["上限"]))
        lines.append("播客：" + c.show(self.pod_cmd(c, d["用备用"], d["播客预算"], False)))
        lines.append("视频旁白：" + c.show(self.vid_cmd(c, d["用备用"], d["视频预算"])))
        if not d["用备用"] and not c.offline:
            est = self.estimate(c)
            lines.append("估计花费（全部重配的上限，缓存里有的不花钱）：播客约 $%.3f、视频约 $%.3f" % (est["播客"] or 0, est["视频"] or 0))
        elif c.offline:
            lines.append("离线：预算 0，只用缓存；缓存里没有的配不出来 → 出数据版")
        else:
            lines.append("估计花费：$0（MiMo 免费期）")
        return lines

    def plan_adopt(self, c):
        return ["沿用已有的配音（不重配、不花钱），只读它的 qc.json 看把关结果"]

    def classify(self, out):
        if re.search(r"ForbiddenProject|大论文", out):
            return "禁用项目"
        if "DurationOutOfRange" in out:
            return "稿子长短"
        if "✗ 时长把关" in out:
            return "配完时长"
        if "BudgetExceeded" in out or "预算 $" in out:
            return "超预算"
        return "出错"

    def spend(self, c, label, usage, t0):
        got = usage_new_spend(usage, t0)
        if got is not None:
            usd, src = got
            note = ""
        else:
            usd, n = chunk_spend_since(t0)
            src, note = "~/.cache/frontier-daily/tts/chunks（这一步期间新写的 %d 条）" % n, "usage.json 没写成，按配音缓存里每条自己记的钱补记"
        if usd or got is not None:
            c.ledger.add("%s·%s" % (self.name, label), "Gemini", usd, src, note)
        return usd

    def run(self, c, how):
        e = c.ed
        speech = c.p(e["人声"])
        warns, extra = [], {}
        if how == "run":
            busy = running_scripts(["(tts|dialog_tts|video3_build)\\.py .*%s" % c.day])
            if busy:
                return R(FAILED, "这一天已经有配音在跑（进程 %d），等它结束再来" % busy[0][0])
            d = self.decide(c)
            extra.update({"决定": d})
            loose = bool(((c.state.step("check") or {}).get("附加") or {}).get("放宽时长") or
                         ((c.state.step("revise") or {}).get("附加") or {}).get("放宽时长"))
            # ---- 播客
            pod_ok, engine = False, "MiMo 备用" if d["用备用"] else "主声音"
            for attempt, backup in ((1, d["用备用"]), (2, True)):
                if attempt == 2 and d["用备用"]:
                    break
                t0 = time.time()
                rc, out = c.run(self, self.pod_cmd(c, backup, 0.0 if backup else d["播客预算"], loose),
                                "播客·%s" % ("MiMo 备用" if backup else "主声音"))
                spent = self.spend(c, "播客", speech / "usage.json", t0)
                kind = None if rc == 0 else self.classify(out)
                if rc == 0 or (kind == "配完时长" and (speech / "episode.mp3").exists()):
                    pod_ok, engine = True, "MiMo 备用" if backup else "主声音"
                    if kind == "配完时长":
                        warns.append("播客配完的实际时长不在区间里（音频已配好，请人工听一下长短）")
                    break
                if kind == "禁用项目":
                    return R(FAILED, "配音要用的 Google 项目是留给大论文的那个，停下来叫人（改 pipeline/tts_engines.py）")
                if kind == "稿子长短":
                    return R(WAITING, "稿子长短不合要求，配音前就拦下了（没花钱）", key_lines(out, 3), todo=[
                        "把播客稿改到规定时长（%s，见对应写稿指令文末'程序检查'），再运行：%s" % (e["日子"], c.again())])
                warns.append("播客%s没配成（%s%s）：%s" % ("主声音" if not backup else "备用", kind,
                                                    "，已花 $%.3f" % spent if spent else "", _err(out)))
            extra["播客"] = engine if pod_ok else "没配成"
            # ---- 视频旁白
            vid_ok, vengine = False, ""
            for attempt, backup in ((1, d["用备用"]), (2, True)):
                if attempt == 2 and d["用备用"]:
                    break
                t0 = time.time()
                rc, out = c.run(self, self.vid_cmd(c, backup, 0.0 if backup else d["视频预算"]),
                                "视频旁白·%s" % ("MiMo 备用" if backup else "主声音"))
                spent = self.spend(c, "视频旁白", c.p(VIDEO_VOICE) / "usage.json", t0)
                if rc == 0:
                    vj = read_json(c.p(VIDEO_VOICE) / "voice.json", {}) or {}
                    real = "MiMo 备用" if str(vj.get("engine", "")).lower() == "mimo" else "主声音"
                    vid_ok, vengine = True, real
                    if "旁白和现有配音对不上" not in out:
                        vengine = real + "（旁白没改，沿用已有配音）"
                    break
                kind = self.classify(out)
                if kind == "禁用项目":
                    return R(FAILED, "配音要用的 Google 项目是留给大论文的那个，停下来叫人")
                last = "\n".join(tail(out, 8))
                if re.search(r"旁白不合规则|超过上限|核对失败|触发词对不上|视频分镜结构不对|视频分镜不是合法|找不到视频分镜|语气不合规矩", last):
                    warns.append("视频分镜或旁白没过配音前检查（不是声音的问题，换备用也没用）：" + "；".join(key_lines(last, 2))[:160])
                    break
                warns.append("视频旁白%s没配成（%s）：%s" % ("主声音" if not backup else "备用", kind, _err(out)))
            extra["视频旁白"] = vengine if vid_ok else "没配成"
            extra["视频引擎"] = "mimo" if vengine.startswith("MiMo") else "gemini"
        else:
            extra.update({"播客": "沿用已有", "视频旁白": "沿用已有", "视频引擎": "gemini"})
            vj = read_json(c.p(VIDEO_VOICE) / "voice.json", {}) or {}
            extra["视频引擎"] = "mimo" if str(vj.get("engine", "")).lower() == "mimo" else "gemini"
        # ---- 看配音程序自己的把关结果
        if extra["播客"] != "没配成":
            q = (speech / "qc.json").read_text(encoding="utf-8") if (speech / "qc.json").exists() else ""
            n_relisten = len(re.findall(r'"需人工复听":\s*true', q))
            n_timbre = timbre_relisten_count(q)
            if n_relisten:
                warns.append("播客有 %d 处标了'需人工复听'（见 %s/qc.json）" % (n_relisten, e["人声"]))
            if n_timbre:
                warns.append("播客有 %d 处'音色需人工听'" % n_timbre)
        pod_bad, vid_bad = extra["播客"] == "没配成", extra["视频旁白"] == "没配成"
        if pod_bad and vid_bad:
            return R(FAILED, "播客和视频旁白都没配成：这一期出数据版（网页不带音频）", warns, extra, go_on=True)
        if pod_bad:
            return R(FAILED, "播客没配成：这一期网页不放播客（数据版）；视频旁白%s" % extra["视频旁白"], warns, extra, go_on=True)
        msg = "播客：%s；视频旁白：%s" % (extra["播客"], extra["视频旁白"])
        if vid_bad:
            warns.append("视频旁白没配成：这一期不出视频")
        return R(DONE, msg, warns, extra)


# ================================================================ 12 混音
class Mix(Step):
    no, key, name = 12, "mix", "混音"
    timeout = 1800
    check_text = "整集 −16 LUFS（±0.7）、真峰值不超过 −1 dBTP（读混音的 qc.json）"
    fix_text = "混音失败或量出来不合格：网页改用不带音乐的人声版（照样能听）；没有人声就跳过"

    def outputs(self, c):
        m = c.ed["混音"]
        return ["%s/episode.mp3" % m, "%s/chapters.json" % m, "%s/qc.json" % m]

    def inputs(self, c):
        s = c.ed["人声"]
        return ["%s/episode.mp3" % s, "%s/chapters.json" % s, "%s/qc.json" % s]

    def command(self, c):
        return c.py(HELPERS, "mix", "--speech", c.p(c.ed["人声"]), "--out", c.p(c.ed["混音"]),
                    "--title", episode_title(c.day, c.edition), *(["--dialog"] if c.ed["配音方式"] == "对谈" else []))

    def plan(self, c):
        return ["运行：" + c.show(self.command(c)) + "（声音包 v3；本机，不花钱）"]

    def run(self, c, how):
        v = (c.state.step("voice") or {}).get("附加") or {}
        if v.get("播客") == "没配成" or not c.p(c.ed["人声"]).joinpath("episode.mp3").exists():
            return R(SKIPPED, "没有人声，不混音", go_on=True)
        rc, out = c.run(self, self.command(c), "混音")
        if rc != 0:
            return R(FAILED, "混音没成功，网页改用不带音乐的人声版：" + "；".join(key_lines(out, 2)), go_on=True,
                     extra={"用人声版": True})
        q = read_json(c.p(c.ed["混音"]) / "qc.json", {}) or {}
        whole = q.get("整集") or {}
        L, tp, secs = whole.get("响度LUFS"), whole.get("真峰值dBTP"), whole.get("整集秒数")
        if L is None or tp is None:
            return R(FAILED, "混音的 qc.json 里没有响度、真峰值，网页改用人声版", go_on=True, extra={"用人声版": True})
        if abs(L + 16) > 0.7 or tp > -1.0:
            return R(FAILED, "混音量出来不合格（%.1f LUFS、真峰值 %.1f dBTP），网页改用人声版" % (L, tp), go_on=True,
                     extra={"用人声版": True})
        return R(DONE, "%.1f LUFS，真峰值 %.1f dBTP，%.1f 分钟" % (L, tp, (secs or 0) / 60))


def podcast_choice(c):
    """网页挂哪一版播客：混好音的 → 不带音乐的人声版 → 没有（数据版）。"""
    v = (c.state.step("voice") or {}).get("附加") or {}
    m = c.state.step("mix") or {}
    mix_ep = c.p(c.ed["混音"]) / "episode.mp3"
    sp_ep = c.p(c.ed["人声"]) / "episode.mp3"
    if v.get("播客") == "没配成":
        return NO_PODCAST
    if m.get("状态") in (DONE, None) and mix_ep.exists():     # None：还没经 fd 混过（--dry-run 预览时），按混好的那版算
        return c.ed["混音"]
    if sp_ep.exists():
        return c.ed["人声"]
    return NO_PODCAST


# ================================================================ 13 网页组装
class Web(Step):
    no, key, name = 13, "web", "网页组装"
    timeout = 1200
    check_text = "make_issue_v3 严格模式（每个出处、页面上每个数字都要在事件卡里），build_v3 组装成功；'听这一段'可疑的跳转提醒"
    fix_text = "数字核不上：停，改网页稿重来；最后一级兜底时加 --lenient 去掉那几项、照常出（现行）。组装出错：停下来叫人"

    def outputs(self, c):
        return ["10_网页v3/issues/%s/issue.js" % c.day, "10_网页v3/index.html", str(c.web_cfg)]

    def inputs(self, c):
        pc = podcast_choice(c)
        return [WEB_DRAFT, CARDS, LINEUP, "06_配图", "=播客=" + pc, "%s/episode.mp3" % pc, "%s/chapters.json" % pc]

    def make_cmd(self, c):
        return c.py(TOOLS / "make_issue_v3.py", "--day", c.day, "--issue-dir", c.issue, "--podcast", podcast_choice(c),
                    "--out", c.web_cfg, *(["--lenient"] if c.lenient else []))

    def build_cmd(self, c):
        return c.py(TOOLS / "build_v3.py", c.issue, "--config", c.web_cfg)

    def plan(self, c):
        mk = c.show(self.make_cmd(c))
        voiced = ((c.state.step("voice") or {}).get("附加") or {}).get("播客")
        if podcast_choice(c) == NO_PODCAST and voiced != "没配成":
            mk = mk.replace(NO_PODCAST, c.ed["混音"]) + "（播客按配音、混音都成算；不成就不放播客）"
        return ["生成配置：" + mk, "组装：" + c.show(self.build_cmd(c)),
                "（网页要先于视频组装：视频的来源编号读这一步写的 issue.js）"]

    def run(self, c, how):
        pc = podcast_choice(c)
        warns = []
        if pc == NO_PODCAST:
            warns.append("这一期没有播客，网页不放'听'")
        elif pc == c.ed["人声"]:
            warns.append("网页挂的是不带音乐的人声版播客（混音没成）")
        rc, out = c.run(self, self.make_cmd(c), "生成配置")
        if rc != 0:
            bad = [x.strip() for x in out.splitlines() if re.search(r"找不到|对不上", x)][:8]
            if "数字核对不上" in out:
                return R(WAITING, "网页稿有数字在事件卡里找不到（可能是编造的），没写配置", bad, todo=[
                    "改 04_文稿/claude_网页.json 里那几处（见日志 %s），再运行：%s" % (rel(c.log_path(self)), c.again()),
                    "实在来不及：加 --lenient 重跑，去掉那几项照常出"])
            return R(FAILED, "生成网页配置出错：" + "；".join(key_lines(out, 3)))
        warns += ["配置：" + x.strip()[2:] for x in out.splitlines() if x.strip().startswith("- ")][:6]
        rc, out = c.run(self, self.build_cmd(c), "组装")
        if rc != 0:
            return R(FAILED, "网页组装出错：" + "；".join(key_lines(out, 3)))
        warns += [x.strip() for x in out.splitlines() if x.strip().startswith("注意")][:8]
        return R(DONE, "配置 %s；播客 %s" % (rel(c.web_cfg), "无" if pc == NO_PODCAST else pc), warns,
                 extra={"播客": "无" if pc == NO_PODCAST else pc})


# ================================================================ 14 视频
SHOT_SUMMARY = "06_配图/原文截图/本期截图.json"      # helpers.py shots 写的这一期截图结果
SHOT_TOTAL = 150          # 截图总时长上限（秒）：交给 source_shots.mjs，超了后面的记"跳过"、退回摘录
SHOT_TIMEOUT = 240        # 整个截图子步骤的硬上限（秒）：到了 fd 直接停掉它，照常组装视频
# 视频导演（11-08 晚加）：老路组装完再请 Claude 导演（site/tools/video3_director.py）。时间预算：
#   11-08 对比时 B 两轮导演约 16 分钟（523＋467 秒），加两次组装（截图、画图约 1 分钟一张、组装、关键帧）合计约 27 分钟；
#   导演程序自己最多用 DIRECTOR_BUDGET 秒（每轮导演最多 20 分钟、改错一次最多 7 分钟），超了就退回；
#   fd 再多给 5 分钟余量，到了直接停掉它、退回老路。第 14 步整步最坏约：截图 4 分钟＋老路组装 1 分钟＋导演 45＋5 分钟＋录预览 3 分钟 ≈ 58 分钟。
DIRECTOR_BUDGET = 2700
DIRECTOR_MIMO_EXTRA = 1200    # 11-09：旁白归导演、又是 MiMo 备用声音时，重配旁白慢（云端约 4 分钟一章），导演总预算多给 20 分钟
DIRECTOR_DIR = "11_视频v3_导演"


def storyboard_shots(sb):
    """分镜里要截图的地方（和 video3_storyboard.shot_owners 同一个口径，只用标准库）：source_shot 块、post_card / quote_card 的 shot、
    时间轴日子的 shot。source_excerpt 本来就不截。返回 ["「章」块" …]。"""
    out = []
    for ch in (sb or {}).get("chapters") or []:
        for b in ch.get("blocks") or []:
            if not isinstance(b, dict):
                continue
            t, where = b.get("type"), "「%s」%s" % (ch.get("id"), b.get("id"))
            if t == "source_shot":
                out.append(where)
            elif t in ("post_card", "quote_card") and isinstance(b.get("shot"), dict):
                out.append(where)
            elif t == "timeline":
                out += ["%s 第 %d 个日子" % (where, i + 1) for i, k in enumerate(b.get("ticks") or [])
                        if isinstance(k, dict) and isinstance(k.get("shot"), dict)]
    return out


class Video(Step):
    no, key, name = 14, "video", "视频"
    timeout = 1800
    check_text = ("先给分镜里的原文截图截图（helpers.py shots，总时长最多 %d 秒，截不到退回原句摘录，出错也照常往下）；"
                  "再 video3_build 组装（配音已在第 11 步，这里预算 0、不生图）；成片不超过 180 秒；预览 MP4 录成" % SHOT_TOTAL)
    fix_text = ("截图没成、超时、出错：那一处退回原句摘录，写进提醒，照常组装；组装失败：这一期网页不放视频，照常出；预览没录成只提醒。"
                "新动效整期不要：FD_MOTION=off（只管这一次）或把 fd_开关.json 改成\"关\"，第 14 步会自动重做。"
                "视频导演（开关开着时）任何一步失败或超时：用老路那一版，报告写\"导演环节退回\"；不要导演：FD_DIRECTOR=off 或 fd_开关.json 的\"视频导演\"改成\"关\"")

    def outputs(self, c):
        return ["11_视频v3/video3_media.json", "11_视频v3/index.html"]

    def inputs(self, c):
        # 新动效开关：开着是空字符串（和加开关以前的记录一样，不会让往期重做），关着是"关"；一换开关，第 14 步自动重做
        # 11-08：视频导演开关同样做法（开着是空字符串，不让往期重做；一换开关，第 14 步自动重做）
        return [STORYBOARD, "%s/voice.json" % VIDEO_VOICE, CARDS, "@step:web", "=新动效=" + ("" if motion_switch()[0] else "关"),
                "=视频导演=" + ("" if director_switch()[0] else "关"),
                "=导演旁白=" + ("" if narration_switch()[0] else "关"),       # 11-09：视频旁白归导演开关，同样做法
                "=中文整词换行=" + ("" if zh_wrap_switch()[0] else "关")]     # 11-09 晚：视频中文整词换行开关，同样做法

    def shots_plan(self, c):
        on, why = motion_switch()
        if not on:
            return "原文截图：不截（新动效开关关着：%s；新块和新字段组装时去掉）" % why
        if not c.p(STORYBOARD).exists():
            return "原文截图：分镜写好以后，组装前给里面的原文截图截图（总时长最多 %d 秒，截不到退回原句摘录，不挡出片）" % SHOT_TOTAL
        n = storyboard_shots(read_json(c.p(STORYBOARD), {}))
        if not n:
            return "原文截图：分镜里没有要截的地方"
        if c.offline:
            return "原文截图：%d 处，离线不截，组装时退回原句摘录" % len(n)
        return "原文截图：%d 处（%s）→ %s（联网，Cookie 只点'拒绝／仅必要'；总时长最多 %d 秒，截不到退回原句摘录）" % (
            len(n), "、".join(n), c.show(self.shots_cmd(c)), SHOT_TOTAL)

    def shots_cmd(self, c):
        return c.py(HELPERS, "shots", "--issue-dir", c.issue, "--total", str(SHOT_TOTAL))

    def shots(self, c):
        """组装前的原文截图。返回 (一句话, 提醒, 附加)。任何情况都不抛错、不挡组装：截不到的那一处组装时退回原句摘录。"""
        try:
            on, why = motion_switch()
            if not on:
                return "新动效开关关着，没截图", [], {"原文截图": "开关关着（%s）" % why}
            n = storyboard_shots(read_json(c.p(STORYBOARD), {}))
            if not n:
                return "", [], {}
            if c.offline:
                return "原文截图 %d 处：离线没截，退回原句摘录" % len(n), [], {"原文截图": "离线没截"}
            summ = c.p(SHOT_SUMMARY)
            t0 = time.time()
            rc, out = c.run(self, self.shots_cmd(c), "原文截图", timeout=SHOT_TIMEOUT)
            res = read_json(summ, {}) or {}
            fresh = summ.exists() and summ.stat().st_mtime >= t0 - 1
            if rc == 124 or not fresh:
                return ("原文截图 %d 处没截完（%s），退回原句摘录" % (len(n), "超过 %d 秒被停掉" % SHOT_TIMEOUT if rc == 124 else "截图程序没写结果"),
                        ["原文截图没截完（%s），%d 处组装时退回原句摘录；日志 %s" % (
                            "超时" if rc == 124 else _err(out) or "退出码 %s" % rc, len(n), rel(c.log_path(self)))],
                        {"原文截图": "没截完"})
            warns = ["原文截图没用上：%s（%s），退回原句摘录" % (r.get("位置"), r.get("原因")) for r in res.get("各处") or []
                     if r.get("结果") != "用截图"]
            if res.get("出错"):
                warns.append("原文截图这一步出错（%s），截图处退回原句摘录" % res["出错"][:120])
            msg = "原文截图 %s 处：用截图 %s、退回摘录 %s" % (res.get("处数", len(n)), res.get("成功", 0), res.get("退回摘录", 0))
            return msg, warns, {"原文截图": {k: res.get(k) for k in ("处数", "成功", "退回摘录", "用时秒")}}
        except Exception as e:      # noqa: BLE001  截图只是锦上添花：fd 自己出错也照常组装
            return "原文截图这一步出错，退回原句摘录", ["原文截图这一步 fd 出错（%s: %s），照常组装" % (type(e).__name__, e)], {}

    def engine(self, c):
        return ((c.state.step("voice") or {}).get("附加") or {}).get("视频引擎") or "gemini"

    def command(self, c):
        return c.py(TOOLS / "video3_build.py", c.issue, "--no-gen", "--budget-usd", "0",
                    *(["--engine", "mimo"] if self.engine(c) == "mimo" else []))

    def record_cmd(self, c):
        return ["node", TOOLS / "video3_record.mjs", c.issue]

    def director_on(self):
        """导演环节做不做：(做不做, 一句话)。新动效开关关着时不做（导演用的模板和渲染修复都挂在新动效开关后面）。"""
        on, why = director_switch()
        if not on:
            return False, "视频导演开关关着（%s）" % why
        mon, mwhy = motion_switch()
        if not mon:
            return False, "新动效开关关着（%s），导演环节不做" % mwhy
        return True, why

    def narration_on(self, c):
        """旁白归导演做不做：(做不做, 一句话)。离线时不做（要重配视频旁白）。"""
        on, why = narration_switch()
        if not on:
            return False, why
        if c.offline:
            return False, "离线，不能重配视频旁白"
        return True, why

    def narration_budget(self, c):
        """重配视频旁白最多花多少（11-09）：和第 11 步同一个口径——这一期还剩的、本月上限还剩的，再封顶 $0.10；
        第 11 步视频旁白用的是备用声音（MiMo，不花钱）就照样用备用。返回 (美元, 引擎)。"""
        if self.engine(c) == "mimo":
            return 0.0, "mimo"
        led = getattr(c, "ledger", None)
        if led is None:
            return 0.0, "gemini"
        try:
            st = led.status()
            avail = max(0.0, min(float(c.budget) - led.issue_total("Gemini"), st["上限美元"] - st["Gemini已记美元"]))
        except Exception:      # noqa: BLE001  账本读不出来就不花钱：导演那边会因为钱不够退回现行旁白
            return 0.0, "gemini"
        return round(min(0.10, avail), 3), "gemini"

    def director_budget(self, c):
        """导演环节最多几秒：平时 DIRECTOR_BUDGET；旁白归导演而且用 MiMo 备用声音时多给 DIRECTOR_MIMO_EXTRA。"""
        if self.narration_on(c)[0] and self.narration_budget(c)[1] == "mimo":
            return DIRECTOR_BUDGET + DIRECTOR_MIMO_EXTRA
        return DIRECTOR_BUDGET

    def director_cmd(self, c):
        cmd = c.py(TOOLS / "video3_director.py", c.issue, "--budget", str(self.director_budget(c)))
        if self.narration_on(c)[0]:
            usd, eng = self.narration_budget(c)
            cmd += ["--narration", "--voice-budget", "%.3f" % usd, "--engine", eng]
        return cmd

    def plan(self, c):
        don, dwhy = self.director_on()
        return [self.shots_plan(c), "组装（老路，第 6 步的分镜）：" + c.show(self.command(c)) + "（本机，不花钱）",
                ("视频导演：" + c.show(self.director_cmd(c)) + "（Claude 订阅；两轮导演＋画导演要的图＋组装，最多 %d 分钟，失败或超时用老路那一版）" % (
                    self.director_budget(c) // 60 + 5)) if don else "视频导演：不做（%s）" % dwhy] + (
            ["视频旁白：%s" % ("归导演写（%s）；过了第 7 步那套检查才重配视频旁白（Gemini，最多 $%.3f），不过就整段用第 6 步的旁白" % (
                self.narration_on(c)[1], self.narration_budget(c)[0]) if self.narration_on(c)[0] else "不归导演（%s），用第 6 步写、第 11 步配好的" % self.narration_on(c)[1])]
             if don else []) + (
            ["预览：" + c.show(self.record_cmd(c)) + "（录屏约 2.5 分钟）"] if c.preview else ["不录预览（--no-preview）"])

    def narration_record(self, c, res, t0):
        """旁白归导演时（11-09）：导演重配视频旁白花的钱记进账本（退回了也记，钱已经花了），旁白最后用的是谁的写进附加。"""
        out = {"附加": {}, "提醒": []}
        if not res or "旁白" not in res:
            return out
        out["附加"]["旁白"] = res.get("旁白")
        usd = float(res.get("配音花费美元") or 0)
        eng = res.get("配音引擎") or "gemini"
        if res.get("配音"):
            out["附加"]["导演旁白配音"] = {"美元": round(usd, 4), "引擎": eng, "次数": len(res.get("配音") or [])}
            led = getattr(c, "ledger", None)
            if led is not None and (usd or eng == "gemini"):
                led.add("%s·导演旁白配音" % self.name, "MiMo" if eng == "mimo" else "Gemini", usd,
                        "%s/结果.json 的 配音花费美元（各次 usage.json 的 合计.其中本次新花费美元）" % DIRECTOR_DIR,
                        "" if res.get("旁白") == "导演写" else "导演写的旁白最后没用上（%s），钱照记" % res.get("旁白"))
        out["提醒"] += [x for x in res.get("提醒") or [] if "旁白" in x or "复听" in x][:3]
        return out

    def director(self, c):
        """老路组装完以后的导演环节。返回 (一句话, 提醒, 附加)。任何情况都不抛错：失败、超时就留着老路那一版。"""
        don, dwhy = self.director_on()
        if not don:
            return "", [], {"视频导演": "不做（%s）" % dwhy}
        res_p = c.p(DIRECTOR_DIR + "/结果.json")
        t0 = time.time()
        try:
            rc, out = c.run(self, self.director_cmd(c), "视频导演", timeout=self.director_budget(c) + 300)
            res = read_json(res_p, {}) or {}
            fresh = res_p.exists() and res_p.stat().st_mtime >= t0 - 1
            mins = (time.time() - t0) / 60
            nar = self.narration_record(c, res if fresh else {}, t0)
            if rc == 124:
                why = "超过 %d 分钟被停掉" % (self.director_budget(c) // 60 + 5)
            elif not fresh:
                why = "导演程序没写结果（%s）" % (_err(out) or "退出码 %s" % rc)
            elif res.get("状态") != "用导演版":
                why = res.get("原因") or "退出码 %s" % rc
            else:
                why = ""
            new = Path(res.get("成片目录") or "/nonexistent")
            if not why:
                media = read_json(new / "video3_media.json", {}) or {}
                if not (new / "index.html").exists() or not media:
                    why = "导演版的演示页不全（%s）" % new
                elif float(media.get("duration") or 0) > 180:
                    why = "导演版 %.0f 秒，超过 3 分钟" % float(media.get("duration") or 0)
            if why:
                return ("导演环节退回（%s），用第 6 步分镜那一版" % why,
                        ["导演环节退回：%s；这一期用第 6 步写稿给的分镜组装的那一版。导演的文件在 %s，日志 %s" % (
                            why, rel(c.p(DIRECTOR_DIR)), rel(c.log_path(self)))] + nar.get("提醒", []),
                        {"视频导演": dict({"结果": "退回", "原因": why, "用时分钟": round(mins, 1)}, **nar.get("附加", {}))})
            # 换成导演版：老路那一版挪进导演文件夹留底（不删），导演版拷进 11_视频v3/；导演新画的图拷进 06_配图/视频/ 留档
            old = c.p("11_视频v3")
            keep = c.p(DIRECTOR_DIR + "/老路_11_视频v3")
            if keep.exists():
                shutil.move(str(keep), str(c.p(DIRECTOR_DIR + "/老路_11_视频v3_%s" % time.strftime("%H%M%S"))))
            shutil.move(str(old), str(keep))
            shutil.copytree(new, old, ignore=shutil.ignore_patterns("关键帧总览.jpg", "预览*.mp4"))
            got = [x for x in res.get("新画的图") or []]
            src_dir = Path(res.get("渲染配图目录") or "/nonexistent")
            vdir = c.p("06_配图/视频")
            if got and src_dir.is_dir():
                vdir.mkdir(parents=True, exist_ok=True)
                meta_new = read_json(src_dir / "来源.json", {}) or {}
                meta = read_json(vdir / "来源.json", {}) or {}
                for i in got:
                    for f in src_dir.glob(i + ".*"):
                        if not (vdir / f.name).exists():
                            shutil.copy2(f, vdir / f.name)
                    if i in meta_new and i not in meta:
                        meta[i] = meta_new[i]
                write_json(vdir / "来源.json", meta)
            d = res.get("导演") or {}
            return ("导演版（两轮导演 %s 秒、新画 %d 张%s，整个导演环节 %.0f 分钟）" % (
                        "＋".join(str((d.get(k) or {}).get("秒", "?")) for k in ("第一轮", "第二轮")), len(got),
                        "；旁白导演写" if res.get("旁白") == "导演写" else ("；旁白退回现行旁白" if str(res.get("旁白", "")).startswith("退回") else ""), mins),
                    (["导演改错用了一次：%s" % "、".join(res.get("改错"))] if res.get("改错") else []) + nar.get("提醒", []),
                    {"视频导演": dict({"结果": "用导演版", "用时分钟": round(mins, 1), "新画的图": got,
                                     "改错": res.get("改错") or [], "导演文件夹": rel(c.p(DIRECTOR_DIR))}, **nar.get("附加", {}))})
        except Exception as e:      # noqa: BLE001  导演只是锦上添花：fd 自己出错也用老路那一版
            if not c.p("11_视频v3/index.html").exists() and c.p(DIRECTOR_DIR + "/老路_11_视频v3/index.html").exists():
                shutil.move(str(c.p(DIRECTOR_DIR + "/老路_11_视频v3")), str(c.p("11_视频v3")))     # 换到一半出错：放回老路那一版
            return ("导演环节退回（fd 出错），用第 6 步分镜那一版",
                    ["导演环节退回：fd 换版时出错（%s: %s），这一期用第 6 步写稿给的分镜组装的那一版" % (type(e).__name__, e)],
                    {"视频导演": {"结果": "退回", "原因": "fd 出错：%s" % e}})

    def run(self, c, how):
        v = (c.state.step("voice") or {}).get("附加") or {}
        if v.get("视频旁白") == "没配成":
            return R(SKIPPED, "视频旁白没配成，这一期不出视频", go_on=True)
        smsg, swarns, sextra = self.shots(c)            # 11-07：组装前截原文截图；不管成没成都往下
        rc, out = c.run(self, self.command(c), "组装视频")
        if rc != 0:
            return R(FAILED, "视频没组装成，这一期网页不放视频：" + "；".join(key_lines(out, 3)), swarns, sextra, go_on=True)
        dmsg, dwarns, dextra = self.director(c)          # 11-08 晚：老路组装成了再请导演；失败、超时都留着老路那一版
        sextra = dict(sextra, **dextra)
        # 组装程序对每一处退回摘录也会提醒一遍，和上面截图的结果重复，不再列（截图结果在 06_配图/原文截图/本期截图.json）
        warns = swarns + [x.strip() for x in out.splitlines() if x.strip().startswith("提醒")
                          and not (sextra.get("原文截图") and re.search(r"原句摘录|退回 source_excerpt", x))][:6]
        media = read_json(c.p("11_视频v3/video3_media.json"), {}) or {}
        dur = float(media.get("duration") or 0)
        warns += dwarns
        if dur > 180:
            return R(FAILED, "视频 %.0f 秒，超过 3 分钟" % dur, warns, sextra, go_on=True)
        if c.preview:
            rc2, out2 = c.run(self, self.record_cmd(c), "录预览", timeout=900)
            if rc2 != 0:
                warns.append("预览 MP4 没录成（不影响网页）：" + "；".join(key_lines(out2, 2)))
        m = re.search(r"对齐中位误差 ([\d.]+) 秒", out)
        return R(DONE, "%.1f 秒，%d 章%s%s%s" % (dur, len(media.get("chapters") or []), "，对齐中位误差 %s 秒" % m.group(1) if m else "",
                                                "；" + smsg if smsg else "", "；" + dmsg if dmsg else ""), warns, sextra)


# ================================================================ 15 网页带视频再组装
class Web2(Step):
    no, key, name = 15, "web2", "网页带视频再组装"
    timeout = 1200
    check_text = "build_v3 再组装一次，页面数据里有视频（v3）"
    fix_text = "视频没成：把旧的 11_视频v3 挪开（改名留底），网页不放视频；组装出错：停下来叫人"

    def outputs(self, c):
        return ["10_网页v3/issues/%s/issue.js" % c.day]

    def inputs(self, c):
        return ["@step:web", "11_视频v3/video3_media.json"]

    def run(self, c, how):
        vs = (c.state.step("video") or {}).get("状态")
        vdir = c.p("11_视频v3")
        warns = []
        if vs in (FAILED, SKIPPED):
            if vdir.exists():
                aside = c.p("11_视频v3_未用_%s" % c.run_id)
                vdir.rename(aside)
                warns.append("视频没成，旧的 11_视频v3 挪到 %s（留底，网页不放）" % aside.name)
            elif vs == SKIPPED:
                return R(SKIPPED, "没有视频，第 13 步的网页就是成品", go_on=True)
        if not Path(c.web_cfg).exists():
            # 11-09：接着跑（from_run）的新机器上没有第 13 步写在仓库里的网页配置（site/tools/v3_issues/<日期>.py）；
            #   照第 13 步同样的命令重新生成（只读期目录里的网页稿、事件卡、选题，不花钱），再组装
            rc, out = c.run(self, c.steps["web"].make_cmd(c), "补生成网页配置")
            if rc != 0:
                return R(FAILED, "网页配置 %s 不在，重新生成也出错：%s" % (rel(c.web_cfg), "；".join(key_lines(out, 3))))
            warns.append("网页配置 %s 不在（接着跑的新机器上没有第 13 步写的那份），按第 13 步同样的命令重新生成了" % rel(c.web_cfg))
        rc, out = c.run(self, c.py(TOOLS / "build_v3.py", c.issue, "--config", c.web_cfg), "再组装")
        if rc != 0:
            return R(FAILED, "网页再组装出错：" + "；".join(key_lines(out, 3)))
        js = c.p(self.outputs(c)[0]).read_text(encoding="utf-8")
        has_video = '"v":3' in js or '"v": 3' in js
        warns += [x.strip() for x in out.splitlines() if x.strip().startswith("注意")][:6]
        return R(DONE, "网页%s视频" % ("带" if has_video else "不带"), warns, extra={"带视频": has_video})


# ================================================================ 16 验收
class Accept(Step):
    no, key, name = 16, "accept", "验收"
    timeout = 900
    check_text = ("shoot_v3（浅色、深色、手机）：无报错、不横向滚动、不缺字；首屏超过 2 MB 提醒；"
                  "check_cites：上标不单独掉行；check_listen：'听这一段'从对的时间放")
    fix_text = "任何一项不过：标'验收没过，不要发布'，停下来叫人（现在本来也不自动发布）"

    def outputs(self, c):
        return ["logs/验收.json"]

    def inputs(self, c):
        return ["10_网页v3/issues/%s/issue.js" % c.day, "10_网页v3/index.html"]

    def url(self, c):
        return c.p("10_网页v3/index.html").resolve().as_uri()

    def plan(self, c):
        return ["截图自检：node site/tools/shoot_v3.js <网页> 10_网页v3 10_网页v3/自检报告.json",
                "上标：node site/tools/check_cites.js <网页>；听这一段：node site/tools/check_listen.js <网页>"]

    def run(self, c, how):
        env = dict(c.env, PW=str(PLAYWRIGHT))
        url = self.url(c)
        probs, warns, res = [], [], {"时间": iso(), "网页": str(c.p("10_网页v3/index.html"))}
        rep = c.p("10_网页v3/自检报告.json")
        rc, out = c.run(self, ["node", TOOLS / "shoot_v3.js", url, c.p("10_网页v3"), rep], "截图自检", env=env)
        sh = read_json(rep, None) if rc == 0 else None
        if sh is None:
            probs.append("截图自检没跑成：" + "；".join(key_lines(out, 2)))
        else:
            for k, v in sh.items():
                if not isinstance(v, dict):
                    continue
                if v.get("errors"):
                    probs.append("%s：页面报错 %d 处（%s）" % (k, len(v["errors"]), str(v["errors"][0])[:80]))
                if v.get("overflowX"):
                    probs.append("%s：横向滚动 %s 像素" % (k, v["overflowX"]))
                if ((v.get("glyphs") or {}).get("fallbackCount")):
                    probs.append("%s：有 %d 处字落到了系统字体（字体包缺字）" % (k, v["glyphs"]["fallbackCount"]))
                if k.startswith("首屏") and float(v.get("totalKB") or 0) > 2048:
                    warns.append("%s下载量 %s KB，超过 2 MB" % (k, v["totalKB"]))
            res["截图"] = {k: {kk: v.get(kk) for kk in ("overflowX", "totalKB") if isinstance(v, dict)} for k, v in sh.items()}
        rc, out = c.run(self, ["node", TOOLS / "check_cites.js", url], "上标", env=env)
        lonely = {}
        for line in out.splitlines():
            m = re.match(r"^(\d+)\s+(\{.*\})\s*$", line.strip())
            if m:
                try:
                    lonely[m.group(1)] = json.loads(m.group(2)).get("lonely") or []
                except ValueError:
                    pass
        if rc != 0 or not lonely:
            probs.append("上标检查没跑成")
        for w, l in lonely.items():
            if l:
                probs.append("%s 像素宽：%d 个上标单独掉行（%s）" % (w, len(l), "、".join(x.get("before", "")[-6:] for x in l[:3])))
        res["上标单独掉行"] = lonely
        rc, out = c.run(self, ["node", TOOLS / "check_listen.js", url], "听这一段", env=env)
        has_pod = (c.state.step("web") or {}).get("附加", {}).get("播客", "无") != "无"
        if "按钮数：0" in out:
            if has_pod:
                probs.append("页面有播客，但没有'听这一段'按钮")
            res["听这一段"] = "没有播客，跳过"
        else:
            jr = _json_list(out)
            ok = bool(jr) and all(any(not a.get("paused") and float(a.get("t") or 0) > 0 for a in r.get("audio") or []) for r in jr)
            if rc != 0 or not ok:
                probs.append("'听这一段'点了没有从对的时间放：" + "；".join(tail(out, 2))[:120])
            res["听这一段"] = jr
        res["没过"], res["提醒"] = probs, warns
        write_json(c.p("logs/验收.json"), res)
        if probs:
            return R(FAILED, "验收没过 %d 项，不要发布" % len(probs), probs + warns, go_on=True)
        return R(DONE, "三种视图无报错、不横滚、不缺字；上标不掉行；'听这一段'正常", warns)


def _json_list(out):
    s = out or ""
    i = s.find("[")
    while i != -1:
        try:
            v = json.loads(s[i:])
            return v if isinstance(v, list) else None
        except ValueError:
            i = s.find("[", i + 1)
    return None


# ================================================================ 17 写本期报告
class Report(Step):
    no, key, name = 17, "report", "写本期报告"
    always = True
    check_text = "00_调度报告.md、花费.json 写成；事件库补记这一期讲过的事；自检.md 末尾补第 10–17 步实际结果（11-09 加）"
    fix_text = "—"

    def outputs(self, c):
        return ["00_调度报告.md"]

    def plan(self, c):
        return ["写 00_调度报告.md、花费.json；事件库再入库一次（补记讲过的事）；自检.md 末尾补第 10–17 步实际结果（程序，11-09 加）"]

    def run(self, c, how):
        warns = []
        if c.p(LINEUP).exists() and (c.state.step("ingest") or {}).get("状态") == DONE:
            rc, out = c.run(self, c.steps["ingest"].command(c), "补记讲过的事")
            if rc != 0:
                warns.append("事件库补记没成功：" + "；".join(key_lines(out, 2)))
        if not c.ledger.issue_file.exists():
            write_json(c.ledger.issue_file, {"期": c.day, "说明": "这一期经 fd 跑的花费；没有花钱的步骤", "条目": [],
                                             "合计美元": {"Gemini": 0, "MiMo": 0, "Codex": 0, "Claude": 0}})
        warns += self.selfcheck(c)
        return R(DONE, "报告 00_调度报告.md", warns)

    def selfcheck(self, c):
        """11-09 加：自检.md 是第 9 步写的，第 17 步后由程序在末尾补"第 10–17 步实际结果"（selfcheck.py；不用模型，
        再跑一次整节换掉）。自检.md 不在就不补。出错只记一条提醒，不挡这一步。返回提醒列表。"""
        from . import selfcheck as SC
        try:
            steps_now = dict((c.state.data or {}).get("步骤") or {})
            steps_now[self.key] = {"状态": DONE, "说明": "报告 00_调度报告.md（这一次）"}
            want, vid = c.steps["images"].wanted(c) if hasattr(c.steps.get("images"), "wanted") else (None, None)
            try:
                month = c.ledger.status()
            except Exception:      # noqa: BLE001  账本读不出来就不写本月那半句
                month = {}
            sec = SC.build(c.issue, steps_now, SC.costs_of(c.ledger.issue_file), month,
                           SC.images_summary(c.issue, want, vid), iso())
            SC.write(c.p("自检.md"), sec)
            return []
        except Exception as e:      # noqa: BLE001
            return ["自检.md 末尾没补上第 10–17 步实际结果：%s: %s" % (type(e).__name__, e)]


STEPS = [Fetch(), Cluster(), Ingest(), Select(), Cards(), Write(), Check(), Review(), Revise(), Images(),
         Voice(), Mix(), Web(), Video(), Web2(), Accept(), Report()]
BY_KEY = {s.key: s for s in STEPS}


def find_step(x):
    """--from/--until 认三种写法：编号（11）、英文键（voice）、中文名（配音）。"""
    x = str(x).strip()
    if x.isdigit():
        n = int(x)
        for s in STEPS:
            if s.no == n:
                return s
    for s in STEPS:
        if x in (s.key, s.name) or (len(x) >= 2 and s.name.startswith(x)):
            return s
    raise SystemExit("不认识的步骤：%s（可以写 1–17、英文键如 voice，或中文名如 配音）" % x)
