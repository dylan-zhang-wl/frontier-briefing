#!/usr/bin/env python3
"""今日一词的往期记录和去重检查（2026-11-03 加）。

起因：10-31 的今日一词是「开放权重 / open weights」，三天后 11-03 又选了「开源权重 / open weights」——同一个词，
中文名还不一样。选题时看不到往期讲过哪些词。

往期记录不另存一份要维护的账：每次从期目录的上一级（默认 测试版/）里、比今天早的各期现取（冻结的 10-31、11-01 只读）：
  · 今日一词：网页稿 04_文稿/claude_网页.json 的 daily_card.term（没有就取 term 那一节的标题"今日一词：…"），
    另取 term 那一节的正文、播客稿"## 今日一词"那一章，给"换个角度"作对照；
  · 名词解释：周末网页稿 deep 那一条的 glossary（3–5 个，只在网页侧栏、不单独播），优先级低：
    撞上它不算重复、不要求回调，只提醒中文名沿用。
同一个词：英文不分大小写、连字符当空格、词尾复数 s 去掉后相同（两个词以上的短语，一方整段包含另一方也算），
或中文名相同（三个字以上的，一方包含另一方也算）。中文定名另见 prompts/术语定名.json（往期写法不一致的词在那里定一个）。

用法（在项目根运行，只用标准库）：
    $PY pipeline/term_history.py show  --day 2026-11-04                  # 列出 2026-11-04 之前的往期今日一词
    $PY pipeline/term_history.py write --run-dir 测试版/2026-11-04       # 写 02_选题/往期今日一词.json（选题的输入；run_mimo.py compact 也写）
    $PY pipeline/term_history.py check --issue-dir 测试版/2026-11-03 [--edition weekday] [--json]
        # 第 7 步：今天的今日一词和近 30 天的重复时，要标 repeat_of、播客要点明哪天讲过、中文名要沿用；只读，不改稿
选题自查（run_mimo.py check，第 4 步）调 lineup_problems()。
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
ROOT = PIPE.parent
ISSUES = ROOT / "测试版"
DECISIONS = PIPE / "prompts" / "术语定名.json"
SELECT_FILE = "02_选题/往期今日一词.json"
WINDOW = 30                       # 近 30 天用过的词尽量不再用
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PODCASTS = ("04_文稿/claude_播客_v3.md", "04_文稿/claude_对谈_v3.md", "04_文稿/claude_播客_周六.md",
            "04_文稿/claude_播客_周日深谈.md")
WEEKEND = ("saturday_deep", "sunday_deep")      # 周末网页没有今日一词，改成名词解释；播客没有"今日一词"这一章
HAN = "〇一二三四五六七八九"
WEEK = "一二三四五六日"


# ---------------------------------------------------------------- 读文件
def _json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _cut(s, n):
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s if len(s) <= n else s[:n] + "……"


def podcast_section(text, name="今日一词"):
    """播客稿里"## 今日一词"那一章的正文（不含标题、注释、语气表）；没有就空串。"""
    out, on = [], False
    for line in (text or "").splitlines():
        if line.startswith("## "):
            on = line[3:].strip() == name
            continue
        if on:
            out.append(line)
    body = re.sub(r"<!--.*?-->", "", "\n".join(out), flags=re.S)
    return body.strip()


def find_podcast(issue):
    for rel in PODCASTS:
        p = Path(issue) / rel
        if p.exists():
            return p
    return None


def web_term(web):
    """网页稿里的今日一词：daily_card.term，补上 term 那一节的正文。没有就 None。"""
    web = web or {}
    t = dict((web.get("daily_card") or {}).get("term") or {})
    sec = next((s for s in web.get("sections") or [] if s.get("kind") == "term" and s.get("items")), None)
    it = (sec or {}).get("items", [{}])[0] if sec else {}
    if not (t.get("zh") or t.get("en")) and it:
        t["zh"] = re.sub(r"^今日一词[：:]\s*", "", it.get("title_zh") or "")
        t["en"] = re.sub(r"^Word of the day[：:]\s*", "", it.get("title_en") or "", flags=re.I)
        t.setdefault("explain_zh", it.get("summary_zh") or "")
    if not (t.get("zh") or t.get("en")):
        return None
    if it:
        t["_section_title_zh"] = re.sub(r"^今日一词[：:]\s*", "", it.get("title_zh") or "")
        t["_body_zh"] = it.get("body_zh") or ""
    return t


def glossary_terms(o):
    """网页稿里所有 glossary 列表的条目（周末 deep 那一条的名词解释）。"""
    out = []
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "glossary" and isinstance(v, list):
                out += [g for g in v if isinstance(g, dict) and (g.get("zh") or g.get("en"))]
            else:
                out += glossary_terms(v)
    elif isinstance(o, list):
        for v in o:
            out += glossary_terms(v)
    return out


def issue_terms(issue):
    """一期里用过的词：[{date, kind: 今日一词|名词解释, zh, en, explain_zh, explain_en, web_zh, podcast_zh}]。"""
    issue = Path(issue)
    web = _json(issue / "04_文稿" / "claude_网页.json")
    if not web:
        return []
    out = []
    t = web_term(web)
    if t:
        pod = find_podcast(issue)
        out.append({"date": issue.name, "kind": "今日一词", "zh": t.get("zh") or "", "en": t.get("en") or "",
                    "explain_zh": t.get("explain_zh") or "", "explain_en": t.get("explain_en") or "",
                    "web_zh": _cut(t.get("_body_zh"), 240),
                    "podcast_zh": _cut(podcast_section(pod.read_text(encoding="utf-8")), 320) if pod else ""})
    for g in glossary_terms(web):
        out.append({"date": issue.name, "kind": "名词解释", "zh": g.get("zh") or "", "en": g.get("en") or "",
                    "explain_zh": g.get("explain_zh") or "", "explain_en": g.get("explain_en") or ""})
    return out


def history(issues_root, before, days=None):
    """issues_root 下比 before 早的各期（目录名是日期的）用过的词，新的在前；每条加 days_ago。days 给了就只要这么多天以内的。"""
    root, d0 = Path(issues_root), date.fromisoformat(before)
    out = []
    if not root.is_dir():
        return out
    for d in sorted((p for p in root.iterdir() if p.is_dir() and DAY_RE.match(p.name) and p.name < before), reverse=True):
        ago = (d0 - date.fromisoformat(d.name)).days
        if days is not None and ago > days:
            continue
        for e in issue_terms(d):
            e["days_ago"] = ago
            out.append(e)
    return out


def decisions(path=DECISIONS):
    return (_json(path, {}) or {}).get("定名") or []


# ---------------------------------------------------------------- 比对
def norm_en(s):
    s = re.sub(r"[‐-―_/-]", " ", (s or "").lower())
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in s.split())


def norm_zh(s):
    return re.sub(r"[\s·・\-—–（）()《》“”\"'‘’、，,。]", "", s or "")


def _en_same(a, b):
    a, b = norm_en(a), norm_en(b)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short.split()) >= 2 and re.search(r"(^| )" + re.escape(short) + r"( |$)", long_) is not None


def _zh_same(a, b):
    a, b = norm_zh(a), norm_zh(b)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 3 and short in long_


def same_term(a, b):
    """两个词是不是同一个：英文或中文任一相同（定名表里"不用"的旧写法也算这个词）。"""
    zs_a = [a.get("zh")] + list(a.get("不用") or [])
    zs_b = [b.get("zh")] + list(b.get("不用") or [])
    return _en_same(a.get("en"), b.get("en")) or any(_zh_same(x, y) for x in zs_a for y in zs_b)


def decision_for(term, table=None):
    table = decisions() if table is None else table
    return next((d for d in table if same_term(term, d)), None)


def matches(term, hist, days=WINDOW, kind="今日一词"):
    """往期里和 term 是同一个词的记录（days 天以内、指定种类），新的在前。"""
    return [e for e in hist if e.get("kind") == kind and (days is None or e["days_ago"] <= days) and same_term(term, e)]


def expected_zh(term, hist, table=None):
    """这个词该用的中文名：(中文名, 依据)。有定名照定名；否则照往期第一次用的写法；往期没有就 (None, "")。"""
    d = decision_for(term, table)
    if d:
        return d["zh"], "%s 定名：%s" % (d.get("定于") or "", d.get("理由") or "")
    for kind in ("今日一词", "名词解释"):
        old = sorted(matches(term, hist, None, kind), key=lambda e: e["date"])
        if old:
            return old[0]["zh"], "%s第一次用的写法" % md(old[0]["date"])
    return None, ""


def md(day):
    d = date.fromisoformat(day)
    return "%d 月 %d 日" % (d.month, d.day)


def han_num(n):
    if n < 10:
        return HAN[n]
    t, u = divmod(n, 10)
    return ("" if t == 1 else HAN[t]) + "十" + (HAN[u] if u else "")


def date_forms(day, today=None):
    """播客里点明某一天的几种说法：10 月 31 日 / 10月31号 / 十月三十一日（号）；隔一两天的"昨天""前天"，一周内的"上周五"。"""
    d = date.fromisoformat(day)
    forms = [r"%d\s*月\s*%d\s*[日号]" % (d.month, d.day), "%s月%s[日号]?" % (han_num(d.month), han_num(d.day))]
    if today:
        gap = (date.fromisoformat(today) - d).days
        if gap == 1:
            forms.append("昨天")
        elif gap == 2:
            forms.append("前天")
        if 1 <= gap <= 7:
            wd = WEEK[d.weekday()] + ("|天" if d.weekday() == 6 else "")
            forms.append(r"(上|这|本)(个)?(周|星期|礼拜)(%s)" % wd)
    return forms


def mentions_date(text, day, today=None):
    return any(re.search(f, text or "") for f in date_forms(day, today))


def _bigrams(s):
    s = "".join(re.findall(r"[一-鿿]", s or ""))
    return {s[i:i + 2] for i in range(len(s) - 1)}


def similarity(a, b):
    """两段中文解释有多像（汉字两两相连的片段重合多少，0–1）；只用来提醒"和上次太像"。"""
    x, y = _bigrams(a), _bigrams(b)
    return len(x & y) / len(x | y) if x and y else 0.0


SIMILAR = 0.45


# ---------------------------------------------------------------- 给选题的输入
def selection_input(run_dir, table=None):
    """02_选题/往期今日一词.json 的内容：近 30 天的今日一词带解释，更早的只列名字；周末名词解释另列；定名表照抄。"""
    run_dir = Path(run_dir)
    table = decisions() if table is None else table
    hist = history(run_dir.parent, run_dir.name)

    def slim(e, full):
        d = decision_for(e, table)
        o = {"date": e["date"], "zh": e["zh"], "en": e["en"],
             "定名": d["zh"] if d and norm_zh(d["zh"]) != norm_zh(e["zh"]) else None}   # 当时的写法和定名不一样才写
        if full:
            o.update(explain_zh=e.get("explain_zh"), podcast_zh=e.get("podcast_zh"))
        return {k: v for k, v in o.items() if v}

    terms = [e for e in hist if e["kind"] == "今日一词"]
    return {
        "说明": ("往期今日一词（程序从%s各期网页稿、播客稿现取，%s 以前）。规则见选题指令第三节：近 %d 天当过今日一词的词尽量不再选；"
               "确实最贴切，在 term 里写 repeat_of 并沿用当时的中文名，写稿时播客点明哪天讲过、换个角度讲。"
               "周末名词解释里的词优先级低，不算重复，中文名同样沿用。写了「定名」的，以定名为准。")
              % (run_dir.parent.name + "/", run_dir.name, WINDOW),
        "近30天": [slim(e, True) for e in terms if e["days_ago"] <= WINDOW],
        "更早": [slim(e, False) for e in terms if e["days_ago"] > WINDOW],
        "周末名词解释": [slim(e, False) for e in hist if e["kind"] == "名词解释"],
        "定名": table,
    }


def write_selection_input(run_dir):
    run_dir = Path(run_dir)
    p = run_dir / SELECT_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    obj = selection_input(run_dir)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    return p, obj


# ---------------------------------------------------------------- 检查
def _show(e):
    return "%s / %s" % (e.get("zh") or "?", e.get("en") or "?")


def _when(hits):
    return "、".join(dict.fromkeys(md(e["date"]) for e in hits))


def _repeat_problems(term, hits, step7=False, exp=None):
    """term 里的 repeat_of 对不对：返回问题清单（空 = 没问题）。hits 是近 30 天的同一个词，新的在前；exp 是该用的中文名。"""
    ro = term.get("repeat_of")
    last = hits[0]
    name = exp or last["zh"]
    was = "当时叫「%s」" % last["zh"] + ("，定名「%s」" % exp if exp and norm_zh(exp) != norm_zh(last["zh"]) else "")
    eg = json.dumps({"date": last["date"], "zh": name, "explain_zh": _cut(last.get("explain_zh"), 40)}, ensure_ascii=False)
    if not ro:
        if step7:
            return ["今日一词「%s」在 %s已经讲过（%s），选题（02_选题/最终选题.json 的 term）和网页稿（daily_card.term）都没标 repeat_of："
                    "在网页稿 daily_card.term 里补 \"repeat_of\": %s（不用改选题，改选题会让事件卡重做），播客、网页照下面几条回调、换角度"
                    % (_show(term), _when(hits), was, eg)]
        return ["今日一词「%s」在 %s已经讲过（%s），选题里没标 repeat_of：先在今天的条目里换一个词；确实是今天最贴切的，"
                "就在 term 里写 \"repeat_of\": %s，在 why 里写清这次换什么角度讲" % (_show(term), _when(hits), was, eg)]
    if not isinstance(ro, dict) or ro.get("date") not in {e["date"] for e in hits}:
        return ["term.repeat_of 写的日期是 %s，可这个词是 %s 讲过的：照 %s 改" % (
            (ro or {}).get("date") if isinstance(ro, dict) else ro, _when(hits), eg)]
    return []


def lineup_problems(lu, run_dir, edition="weekday", table=None):
    """第 4 步选题自查（run_mimo.py check_lineup 调）：返回 (要改, 提醒)。周末没有今日一词，不查。"""
    term = (lu or {}).get("term") or {}
    if edition in WEEKEND or not (term.get("zh") or term.get("en")):
        return [], []
    run_dir = Path(run_dir)
    table = decisions() if table is None else table
    hist = history(run_dir.parent, run_dir.name)
    must, warn = [], []
    hits = matches(term, hist)
    exp, why = expected_zh(term, hist, table)
    if hits:
        must += _repeat_problems(term, hits, exp=exp)
    elif term.get("repeat_of"):
        must.append("term.repeat_of 写了 %s，可近 %d 天的今日一词里没有「%s」：不是重复就去掉 repeat_of"
                    % (json.dumps(term["repeat_of"], ensure_ascii=False)[:60], WINDOW, _show(term)))
    else:
        old = matches(term, hist, None)
        if old:
            warn.append("今日一词「%s」在 %s讲过（%d 天以前，不算重复）；中文名沿用往期的写法" % (_show(term), _when(old[:2]), old[0]["days_ago"]))
    if exp and norm_zh(exp) != norm_zh(term.get("zh")) and not term.get("rename_why"):
        must.append("今日一词的中文名「%s」和往期的「%s」不一样（%s）：沿用「%s」；确实要改名，在 term 里写 rename_why 说明为什么，"
                    "写稿时播客和网页都要说一句" % (term.get("zh"), exp, _cut(why, 80), exp))
    gl = matches(term, hist, WINDOW, "名词解释")
    if gl and not hits:
        warn.append("今日一词「%s」在 %s的周末名词解释里出现过（优先级低，不算重复）" % (_show(term), _when(gl)))
    return must, warn


def check_issue(issue, edition=None, table=None):
    """第 7 步：今天的稿子（网页稿、播客稿）对照往期今日一词。返回 {"要改": [...], "提醒": [...], "今天": …, "往期同一个词": […]}。只读。"""
    issue = Path(issue)
    table = decisions() if table is None else table
    st = _json(issue / "logs" / "fd_state.json", {}) or {}
    edition = edition or st.get("edition") or st.get("版别") or "weekday"
    hist = history(issue.parent, issue.name)
    web = _json(issue / "04_文稿" / "claude_网页.json", {}) or {}
    lu = _json(issue / "02_选题" / "最终选题.json", {}) or {}
    must, warn = [], []
    res = {"要改": must, "提醒": warn, "版别": edition, "往期条数": len(hist)}
    if edition in WEEKEND:                         # 周末：网页的名词解释只提醒
        for g in glossary_terms(web):
            hits = matches(g, hist)
            if hits:
                warn.append("名词解释「%s」在 %s当过今日一词：可以照当时的说法解释" % (_show(g), _when(hits)))
            exp, why = expected_zh(g, hist, table)
            if exp and norm_zh(exp) != norm_zh(g.get("zh")):
                warn.append("名词解释「%s」的中文名和往期的「%s」不一样（%s）：最好沿用" % (_show(g), exp, _cut(why, 60)))
        return res
    t = web_term(web)
    if not t:
        warn.append("网页稿里没找到今日一词（daily_card.term），这一项没查")
        return res
    res["今天"] = {k: t.get(k) for k in ("zh", "en", "explain_zh")}
    lt = lu.get("term") or {}
    marks = dict(lt if same_term(lt, t) else {})  # 选题定的词和网页用的是同一个，选题里的标记才算数
    for k in ("repeat_of", "rename_why"):
        if t.get(k):
            marks[k] = t[k]                       # 网页稿 daily_card.term 里补的标记也认（改选题会让事件卡重做）
    marks.update({"zh": t.get("zh"), "en": t.get("en")})
    pod_p = find_podcast(issue)
    pod = podcast_section(pod_p.read_text(encoding="utf-8")) if pod_p else ""
    # 今天自己几处的中文名要一致
    sec_zh = t.get("_section_title_zh")
    if sec_zh and norm_zh(sec_zh) != norm_zh(t.get("zh")):
        must.append("网页稿里今日一词的中文名两处不一样：日卡写「%s」，今日一词那一节写「%s」" % (t.get("zh"), sec_zh))
    if pod_p and not pod:
        warn.append("播客稿里没找到「## 今日一词」这一章（%s）" % pod_p.name)
    elif pod and t.get("zh") and norm_zh(t["zh"]) not in norm_zh(pod):
        must.append("播客「今日一词」这一章没说到网页上的中文名「%s」：两边要用同一个中文名" % t["zh"])
    hits = matches(t, hist)
    exp, why = expected_zh(t, hist, table)
    res["往期同一个词"] = [{k: e.get(k) for k in ("date", "zh", "en", "explain_zh")} for e in hits]
    if hits:
        must += _repeat_problems(marks, hits, step7=True, exp=exp)
        if pod and not any(mentions_date(pod, e["date"], issue.name) for e in hits):
            last = hits[0]
            must.append("播客「今日一词」没点明这个词在 %s讲过：开头加一句回调，比如\"%s我们讲过%s，今天换个角度\"；解释换个角度"
                        "（比如它在今天新闻里怎么用、和相近的词差在哪、常见的误解），不重复当时那句定义（当时说的是：%s）"
                        % (_when(hits), "%s月%s号" % (han_num(date.fromisoformat(last["date"]).month),
                                                   han_num(date.fromisoformat(last["date"]).day)),
                           exp or last["zh"], _cut(last.get("explain_zh"), 60)))
        last = hits[0]
        if similarity(t.get("explain_zh"), last.get("explain_zh")) >= SIMILAR:
            warn.append("网页上今日一词的解释和 %s 那次很像（%.0f%%）：换个角度写，不照抄上次的定义" % (
                md(last["date"]), 100 * similarity(t.get("explain_zh"), last.get("explain_zh"))))
        if pod and last.get("podcast_zh") and similarity(pod, last["podcast_zh"]) >= SIMILAR:
            warn.append("播客「今日一词」和 %s 那次很像（%.0f%%）：换个角度讲" % (md(last["date"]), 100 * similarity(pod, last["podcast_zh"])))
    else:
        if marks.get("repeat_of") and not matches(t, hist, None):
            warn.append("选题标了 repeat_of，可往期没查到「%s」：多半不用标" % _show(t))
        gl = matches(t, hist, WINDOW, "名词解释")
        if gl:
            warn.append("今日一词「%s」在 %s的周末名词解释里出现过（优先级低，不算重复）" % (_show(t), _when(gl)))
    if exp and norm_zh(exp) != norm_zh(t.get("zh")):
        if not marks.get("rename_why"):
            must.append("今日一词的中文名「%s」和往期的「%s」不一样（%s）：网页、播客都改回「%s」；确实要改名，在选题或网页稿的 term 里"
                        "写 rename_why，播客和网页各说一句为什么改" % (t.get("zh"), exp, _cut(why, 80), exp))
        elif pod and norm_zh(exp) not in norm_zh(pod):
            must.append("今日一词改了中文名（「%s」→「%s」），播客「今日一词」要提到旧名、说一句为什么改" % (exp, t.get("zh")))
    return res


# ---------------------------------------------------------------- 命令行
def main(argv=None):
    ap = argparse.ArgumentParser(description="今日一词的往期记录和去重检查（用法见文件开头）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("--day", required=True)
    s.add_argument("--issues", default=str(ISSUES))
    w = sub.add_parser("write")
    w.add_argument("--run-dir", required=True)
    c = sub.add_parser("check")
    c.add_argument("--issue-dir", required=True)
    c.add_argument("--edition")
    c.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "show":
        for e in history(a.issues, a.day):
            print("%s（%d 天前）%s「%s / %s」%s" % (e["date"], e["days_ago"], e["kind"], e["zh"], e["en"],
                                                  "　定名「%s」" % decision_for(e)["zh"] if decision_for(e) else ""))
        return 0
    if a.cmd == "write":
        p, obj = write_selection_input(Path(a.run_dir).expanduser().resolve())
        print("往期今日一词：近 %d 天 %d 个、更早 %d 个、周末名词解释 %d 个 → %s" % (
            WINDOW, len(obj["近30天"]), len(obj["更早"]), len(obj["周末名词解释"]), p))
        return 0
    res = check_issue(Path(a.issue_dir).expanduser().resolve(), a.edition)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for m in res["要改"]:
            print("✗ 要改：" + m)
        for m in res["提醒"]:
            print("提醒：" + m)
        if not res["要改"]:
            print("今日一词检查通过")
    return 1 if res["要改"] else 0


if __name__ == "__main__":
    sys.exit(main())
