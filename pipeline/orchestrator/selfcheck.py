"""自检.md 末尾补"第 10–17 步实际结果"（2026-11-09 加）。

为什么要有它：云端的 自检.md 是第 9 步时主会话写的（那时还没配音、没配图、没出视频），第 17 步以后没人更新，
11-09 那期写着"没配音、没花钱""第 10–17 步这次没跑"，和成品对不上。审片和人看 自检.md 时会被它带偏。

做法：第 17 步（写本期报告）每次跑完，由程序在 自检.md 末尾写一节（只用 fd 的步骤记录 logs/fd_state.json、
花费.json、月度账本、06_配图/ 里的文件和 来源.json，不用模型）：第 10–17 步各步的状态和说明、声音、配图张数和来源、
视频是导演版还是老路（旁白谁写的）、花费、验收。这一节以固定标题开头；再跑一次就整节换掉，不会越补越长。
自检.md 不在（第 9 步没写）就不补。
"""
import json
import re
from pathlib import Path

HEAD = "## 第 10–17 步实际结果（程序补写）"
NOTE = ("上面是第 9 步时写的（那时还没配音、配图、出视频）。这一节是第 17 步后程序按 fd 的步骤记录和期目录里的文件补的，"
        "不经模型；两边说法不一样时以这一节为准。")
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
STEP_KEYS = [(10, "images", "配图"), (11, "voice", "配音"), (12, "mix", "混音"), (13, "web", "网页组装"),
             (14, "video", "视频"), (15, "web2", "网页带视频"), (16, "accept", "验收"), (17, "report", "写本期报告")]
BACKEND = {"codex": "Codex", "agy": "agy"}


def _read(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _cut(s, n=160):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def images_summary(issue, want_web=None, want_vid=None):
    """配图：网页图几张（谁画的）、视频图几张（按 来源.json 分来源）。want_* 是第 10 步要的图（没给就只数有的）。"""
    issue = Path(issue)
    web_dir, vid_dir = issue / "06_配图", issue / "06_配图" / "视频"
    web = {f.stem.lower() for f in web_dir.glob("*") if f.suffix.lower() in IMG_EXT} if web_dir.is_dir() else set()
    vid = {f.stem for f in vid_dir.glob("*") if f.suffix.lower() in IMG_EXT} if vid_dir.is_dir() else set()
    lines = []
    if want_web is not None:
        miss = [w for w in want_web if w not in web]
        codex = sum(1 for w in want_web if w in web and (web_dir / ("log_%s.png.txt" % w)).exists())
        lines.append("网页图：要 %d 张，有 %d 张%s%s" % (
            len(want_web), len(want_web) - len(miss),
            "（Codex 画的 %d 张，按 06_配图/log_<名字>.png.txt 数）" % codex if codex else "",
            "；缺 %s，网页上用程序画的主题色封面" % "、".join(miss) if miss else ""))
    else:
        lines.append("网页图：06_配图/ 里 %d 张" % len(web))
    meta = _read(vid_dir / "来源.json", {}) or {}
    kinds = {}
    for k in sorted(vid):
        m = meta.get(k) or {}
        if m.get("kind") == "commons":
            src = "维基共享资源"
        elif m.get("kind") == "generated":
            src = BACKEND.get(m.get("backend"), "新画（来源.json 没写后端）")
        else:
            src = "来源.json 里没记"
        kinds[src] = kinds.get(src, 0) + 1
    by = "、".join("%s %d 张" % (k, n) for k, n in kinds.items())
    if want_vid is not None:
        miss = [v for v in want_vid if v not in vid]
        lines.append("视频图：分镜要新画 %d 张，06_配图/视频/ 里共 %d 张%s%s" % (
            len(want_vid), len(vid), "（%s）" % by if by else "", "；缺 %s，那几块不带图" % "、".join(miss) if miss else ""))
    else:
        lines.append("视频图：06_配图/视频/ 里 %d 张%s" % (len(vid), "（%s）" % by if by else ""))
    return lines


def build(issue, steps, costs, month, image_lines, now):
    """拼这一节（纯函数，好测）。steps：fd_state 的"步骤"；costs：{服务: 美元}；month：ledger.status()（可以是空的）。"""
    st = lambda k: steps.get(k) or {}         # noqa: E731
    L = [HEAD, "", "写于 %s（系统时钟，UTC）。%s" % (now, NOTE), ""]
    L += ["| 步 | 做什么 | 状态 | 说明 |", "|---|---|---|---|"]
    for no, key, name in STEP_KEYS:
        r = st(key)
        L.append("| %d | %s | %s | %s |" % (no, name, r.get("状态") or "没跑", _cut(r.get("说明"), 140).replace("|", "／") or "—"))
    L.append("")
    v = st("voice").get("附加") or {}
    vid = st("video").get("附加") or {}
    dr = vid.get("视频导演") or {}
    voice = "声音：播客 %s，视频旁白 %s" % (v.get("播客") or "（没记）", v.get("视频旁白") or "（没记）")
    if v.get("视频引擎"):
        voice += "（第 11 步引擎 %s）" % v["视频引擎"]
    if dr.get("旁白"):
        voice += "；视频旁白最后用的是：%s" % dr["旁白"]
        if dr.get("导演旁白配音"):
            p = dr["导演旁白配音"]
            voice += "（导演旁白重配 %s 次，%s $%.4f）" % (p.get("次数"), p.get("引擎"), float(p.get("美元") or 0))
    L.append("- " + voice)
    L += ["- " + x for x in image_lines]
    if not st("video"):
        L.append("- 视频：第 14 步没跑")
    elif dr.get("结果") == "用导演版":
        L.append("- 视频：导演版（导演环节 %s 分钟，新画 %d 张：%s）" % (
            dr.get("用时分钟"), len(dr.get("新画的图") or []), "、".join(dr.get("新画的图") or []) or "无"))
    elif dr.get("结果") == "退回":
        L.append("- 视频：老路那一版（导演环节退回：%s）" % (dr.get("原因") or "没写原因"))
    else:
        L.append("- 视频：老路那一版（%s）" % ("导演环节没做" if st("video").get("状态") else "第 14 步没跑"))
    tot = "、".join("%s $%.4f" % (k, x) for k, x in costs.items() if x) or "没有花钱"
    mline = ""
    if month and month.get("上限美元") is not None:
        mline = "；本月 Gemini 已记 $%.2f / 上限 $%.2f" % (float(month.get("Gemini已记美元") or 0), float(month["上限美元"]))
    L.append("- 花费：这一期 %s（花费.json）%s" % (tot, mline))
    a = st("accept")
    L.append("- 验收：%s%s%s" % (a.get("状态") or "没跑", "，" + _cut(a.get("说明"), 120) if a.get("说明") else "",
                              "；提醒 %d 条（见 00_调度报告.md 第 16 步）" % len(a.get("提醒") or []) if a.get("提醒") else ""))
    return "\n".join(L) + "\n"


def write(path, section):
    """把这一节写到 自检.md 末尾；已有这一节就整节换掉（这一节总在最后）。文件不在就不写，返回 False。"""
    p = Path(path)
    if not p.exists():
        return False
    s = p.read_text(encoding="utf-8")
    i = s.find("\n" + HEAD)
    if i < 0 and s.startswith(HEAD):
        i = 0
    body = (s[:i] if i >= 0 else s).rstrip("\n")
    p.write_text(body + "\n\n" + section, encoding="utf-8")
    return True


def costs_of(issue_file):
    d = _read(issue_file, {}) or {}
    out = {}
    for e in d.get("条目") or []:
        k = e.get("服务") or "其他"
        out[k] = round(out.get(k, 0.0) + float(e.get("美元") or 0), 4)
    return out
