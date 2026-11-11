#!/usr/bin/env python3
"""周末稿检查：按《写稿_周六深度.md》《写稿_周日深谈.md》文末"程序检查"那段 yaml，查章名和顺序、字数、估计时长、禁用说法。

用法（在项目根运行；PY=~/.venvs/frontier-daily/bin/python）：
    $PY pipeline/weekend_check.py 稿.md                     # 按稿子自动认版别（行首有"甲：""乙："就是周日）
    $PY pipeline/weekend_check.py 稿.md --edition saturday_deep
    $PY pipeline/weekend_check.py 稿.md --json             # 结果写成 JSON

查什么（规则全在指令文末，改规则只改指令）：
  1. 章名和顺序一字不差（程序按章名放转场声、配语气、对网页上的"听这一层"）；
  2. 全篇汉字数、每章汉字数（只数汉字；"甲：""乙："、章名、注释、> 备注不算），按"每分钟汉字"估时长，和"成片时长分钟"比（和配音程序同一个键）；
  3. 禁用说法（正则）、"我们的理解是"的次数、段落／每轮字数上限、第一人称（只许"我们"，自我介绍那句除外）；
  4. 周日另查：两人各占多少、Dylan 是不是开场就开口、快讯里有没有再开口、每轮句数、叫名字的次数；
  5. 快讯条数：按快讯章里报出处的句子粗数（"某某报道""据某某"），只提醒。
不查数字、引语、读音（那是 script_check.py、lexicon_check.py 的事），不调用任何模型。
退出码：0 = 没有要改的；1 = 有要改的（章名不对、总字数或估计时长超出、禁用说法、第一人称）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
PROMPT = {"saturday_deep": PIPE / "prompts" / "写稿_周六深度.md", "sunday_deep": PIPE / "prompts" / "写稿_周日深谈.md"}
HAN = re.compile(r"[一-鿿]")
SPEAKER = re.compile(r"^\s*([甲乙])[：:]\s*")
SELF_INTRO = re.compile(r"我是\s*(Shirley|Dylan)|和我一起聊的是\s*Dylan")   # 自我介绍（方案第四节的例外）
NAMES = ("Shirley", "Dylan")


def rules_of(edition):
    txt = PROMPT[edition].read_text(encoding="utf-8")
    m = re.search(r"## 程序检查[^\n]*\n+```yaml\n(.*?)```", txt, re.S)
    if not m:
        raise SystemExit(f"{PROMPT[edition].name} 里找不到“程序检查”那段 yaml")
    return yaml.safe_load(m.group(1))


def parse(text):
    """→ [(章名, [(说话人或 None, 一段文字)])]；注释、> 备注、# 总标题不算。"""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    chs, cur = [], None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            cur = (s[3:].strip(), [])
            chs.append(cur)
        elif not s or s.startswith("#") or s.startswith(">") or cur is None:
            continue
        else:
            m = SPEAKER.match(s)
            cur[1].append((m.group(1) if m else None, s[m.end():] if m else s))
    return chs


def han(s):
    return len(HAN.findall(s))


MODEL_TOKEN = re.compile(r"[A-Za-z][A-Za-z\-]*\s?\d+(?:\.\d+)*[A-Za-z]*|\bv\d+")   # 型号（Opus 5.5、GPT-6、K3.1）不算数字


def key_numbers(text):
    """一段话里的"关键数字"：金额、百分比、分数、倍数、10 以上的数和小数；日期、年份、月份、序数、型号不算。
    用 script_check 的数字读法（中文数字转阿拉伯数字），只读调用。"""
    import script_check as SC
    s = SC.prepare(MODEL_TOKEN.sub(" ", text))
    out = []
    for x in SC.numbers_in(s):
        if x["种类"] in ("日期", "年", "月", "序数", "版本", "钟点"):
            continue
        if x["种类"] == "数":
            v, after = x["值"], x.get("后面", "")
            unit = re.match(r"(美元|元|分|倍|%|亿|万|个百分点|小时|秒)", after or "")
            if isinstance(v, float) and v.is_integer() and v < 10 and not unit:
                continue
        out.append(x["原文"] + (x.get("后面", "")[:2] if x["种类"] == "数" else ""))
    return out


def check(text, edition):
    R = rules_of(edition)
    chs = parse(text)
    must, warn, info = [], [], {}
    names = [c for c, _ in chs]
    want = R.get("章节") or []
    if names != want:
        must.append(f"章名或顺序不对：现在 {names}，规定 {want}")
    per = {c: sum(han(t) for _, t in ps) for c, ps in chs}
    total = sum(per.values())
    lo, hi = R.get("汉字数") or (0, 10 ** 9)
    rate = float(R.get("每分钟汉字") or 250)
    mins = total / rate
    tlo, thi = R.get("成片时长分钟") or R.get("时长分钟") or (0, 10 ** 9)   # 键名和配音程序（tts.DAY_RULES）对齐
    info.update({"汉字数": total, "每分钟汉字": rate, "估计分钟": round(mins, 1), "每章汉字数": per})
    if not lo <= total <= hi:
        must.append(f"全篇 {total} 个汉字，规定 {lo}–{hi}")
    if not tlo <= mins <= thi:
        must.append(f"按每分钟 {rate:g} 字估约 {mins:.1f} 分钟，规定 {tlo}–{thi} 分钟")
    for c, (a, b) in (R.get("每章汉字数") or {}).items():
        if c in per and not a <= per[c] <= b:
            warn.append(f"「{c}」{per[c]} 字（建议 {a}–{b}）")
    body = [(c, sp, t) for c, ps in chs for sp, t in ps]
    alltext = "\n".join(t for _, _, t in body)
    for pat in R.get("禁用说法") or []:
        for m in re.finditer(pat, alltext):
            must.append(f"禁用说法「{alltext[max(0, m.start() - 8):m.end() + 8]}」（规则：{pat}）")
    for c, sp, t in body:
        t2 = SELF_INTRO.sub("", t)
        for m in re.finditer(r"(?<!自)我(?!们)", t2):            # "自我改进"里的"我"不算
            must.append(f"「{c}」里有“{t2[max(0, m.start() - 6):m.end() + 6]}”：只说“我们”（自我介绍那句除外）")
    n_read = alltext.count("我们的理解是")
    a, b = R.get("我们的理解是") or (0, 99)
    info["我们的理解是"] = n_read
    if not a <= n_read <= b:
        warn.append(f"“我们的理解是” {n_read} 次（规定 {a}–{b}）")
    cap = R.get("段落字数上限") or R.get("每轮字数上限")
    for c, sp, t in body:
        if cap and han(t) > cap:
            warn.append(f"「{c}」有一段 {han(t)} 字（上限 {cap}）：{t[:16]}…")
    if edition == "sunday_deep":
        spk = {"甲": 0, "乙": 0}
        for _, sp, t in body:
            if sp in spk:
                spk[sp] += han(t)
        tot = sum(spk.values()) or 1
        share = {k: round(v / tot, 2) for k, v in spk.items()}
        info["两人各占"] = share
        a, b = R.get("两人各占") or (0, 1)
        for k, v in share.items():
            if not a <= v <= b:
                warn.append(f"{'Shirley' if k == '甲' else 'Dylan'}（{k}）占 {v:.0%}（建议 {a:.0%}–{b:.0%}）")
        if any(sp is None for _, sp, _ in body):
            must.append("有的行没以“甲：”“乙：”开头")
        first_b = next((c for c, sp, _ in body if sp == "乙"), None)
        if first_b != (R.get("乙最晚开口") or "开场"):
            must.append(f"Dylan 第一次开口在「{first_b}」，规定在「{R.get('乙最晚开口') or '开场'}」")
        if not any(c == "快讯" and sp == "乙" for c, sp, _ in body):
            warn.append("快讯里 Dylan 一句也没说：到深谈时会像突然加入")
        smax = R.get("每轮句数上限") or 99
        for c, sp, t in body:
            n = len([x for x in re.split(r"[。！？?!]", t) if x.strip()])
            if n > smax:
                warn.append(f"「{c}」{sp} 有一轮 {n} 句（上限 {smax}）：{t[:16]}…")
        cut = {"开场", "结尾"}
        nm = sum(t.count(n) for c, _, t in body if c not in cut for n in NAMES)
        info["正文叫名字"] = nm
        nlo, nhi = R.get("叫名字") or (0, R.get("叫名字上限") or 99)
        if not nlo <= nm <= nhi:
            warn.append(f"正文里叫名字 {nm} 次（开场、结尾不算；规定 {nlo}–{nhi}）")
        info["轮数"] = len(body)
    # ---- 11-01 复核后加的几项可数规则（指令第五节：不一问一答、给耳朵减负、分清证据分量）
    layers = [c for c in want if c.startswith(("深度·", "深谈·"))]
    qmax = R.get("短问句上限")
    if qmax is not None:
        short_q = {}
        for c, sp, t in body:
            if c not in layers:
                continue
            for q in re.findall(r"[^。！？!?]*[？?]", t):
                core = re.sub(r"[\s，、；：,;:“”\"'‘’]", "", q)
                if len(core) <= 15:
                    short_q.setdefault(c, []).append(q.strip())
        info["每层短问句"] = {c: len(v) for c, v in short_q.items()}
        for c, qs in short_q.items():
            if len(qs) > qmax:
                must.append(f"「{c}」有 {len(qs)} 句不超过 15 个字的问句（上限 {qmax}，别变成一问一答）：" + "｜".join(qs))
    nmax = R.get("每层关键数字上限")
    if nmax is not None:
        groups = {c: [t for cc, _, t in body if cc == c] for c in layers}
        if edition == "saturday_deep":                     # 周六快讯按每条（每段）算
            groups.update({f"快讯第{i + 1}段": [t] for i, t in enumerate(t for c, _, t in body if c == "快讯")})
        cnt = {k: key_numbers(" ".join(v)) for k, v in groups.items()}
        info["每层关键数字"] = {k: len(v) for k, v in cnt.items()}
        for k, v in cnt.items():
            if len(v) > nmax:
                warn.append(f"「{k}」有 {len(v)} 个关键数字（建议不超过 {nmax}）：{'、'.join(v)}")
    for key, pat, label in (("英文叫上限", r"英文叫", "“英文叫”"), ("社交平台转述上限", r"社交平台上", "“社交平台上”")):
        lim = R.get(key)
        if lim is not None:
            n = len(re.findall(pat, alltext))
            info[label] = n
            if n > lim:
                must.append(f"全集 {label} {n} 次（上限 {lim}）")
    flash = [t for c, _, t in body if c == "快讯"]
    n_flash = len(re.findall(r"(报道|援引|据[^，。]{1,12}(说|称)|发文|官方说|宣布|公告)", "".join(flash)))
    info["快讯里报出处的说法（粗数）"] = n_flash
    return {"版别": edition, "要改": must, "提醒": warn, "数据": info}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script")
    ap.add_argument("--edition", choices=list(PROMPT))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    text = Path(a.script).read_text(encoding="utf-8")
    ed = a.edition or ("sunday_deep" if re.search(r"^\s*[甲乙][：:]", text, re.M) else "saturday_deep")
    r = check(text, ed)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        d = r["数据"]
        print(f"周末稿检查（{ed}，规则：{PROMPT[ed].name} 文末）：{d['汉字数']} 个汉字，按每分钟 {d['每分钟汉字']:g} 字估约 {d['估计分钟']} 分钟")
        print("  每章：" + "，".join(f"{k} {v}" for k, v in d["每章汉字数"].items()))
        for k in ("我们的理解是", "两人各占", "正文叫名字", "轮数", "快讯里报出处的说法（粗数）"):
            if k in d:
                print(f"  {k}：{d[k]}")
        print("  要改：" + ("无" if not r["要改"] else ""))
        for x in r["要改"]:
            print("   - " + x)
        print("  提醒：" + ("无" if not r["提醒"] else ""))
        for x in r["提醒"]:
            print("   - " + x)
    return 1 if r["要改"] else 0


if __name__ == "__main__":
    sys.exit(main())
