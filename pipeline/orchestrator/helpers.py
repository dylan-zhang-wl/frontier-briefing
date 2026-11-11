#!/usr/bin/env python3
"""总调度在子进程里用的几个小工具：借现有脚本里的函数，换个目录或换种输出，不改那些脚本。

    $PY -u pipeline/orchestrator/helpers.py cluster      --issue-dir <期目录>        # 对任意期目录跑粗筛、归并（原脚本只认 测试版/<日期>）
    $PY -u pipeline/orchestrator/helpers.py script-check --script 稿.md --cards 卡.json [--day-type 日常]
                                                           # script_check.check() 的结果写成 JSON（原脚本 --json 遇到 numpy 布尔值会报错）
    $PY -u pipeline/orchestrator/helpers.py storyboard   --issue-dir <期目录>        # 视频分镜、旁白、时长：配音前的那几道检查，不配音、不生图
    $PY -u pipeline/orchestrator/helpers.py shots        --issue-dir <期目录> [--total 150]
                                                           # 原文截图（11-07 并入正式流程，第 14 步调）：截到 06_配图/原文截图/，
                                                           # 结果写 本期截图.json；截不到的组装时退回原句摘录；退出码总是 0
    $PY -u pipeline/orchestrator/helpers.py mix          --speech <人声目录> --out <混音目录> --title 标题 [--dialog]
                                                           # podcast_mix.mix_package；--dialog 时带上 voice_profile.json"周日搭档"的"声音包调整"
                                                           # （和 dialog_tts.py 自己混音时一模一样）
每个都只读输入、只写给定的输出目录，不调任何模型接口（shots 会打开事件卡里记的原文网页：Cookie 只点"拒绝／仅必要"，不登录、不过验证码）。
"""
import argparse
import contextlib
import io
import json
import re
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
PIPE, TOOLS = ROOT / "pipeline", ROOT / "site" / "tools"
for p in (str(PIPE), str(TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _plain(o):
    """numpy 的数、布尔值等转成普通 Python 值。"""
    for attr in ("item",):
        if hasattr(o, attr):
            try:
                return o.item()
            except (TypeError, ValueError):
                pass
    if isinstance(o, (set, tuple)):
        return list(o)
    if isinstance(o, Path):
        return str(o)
    return str(o)


def cmd_cluster(a):
    issue = Path(a.issue_dir).expanduser().resolve()
    import prefilter
    import cluster
    prefilter.run_dir = lambda day: issue           # 和 event_db.prep 同一个办法：只换目录，不改那两个文件
    cluster.run_dir = lambda day: issue
    argv0 = sys.argv
    try:
        sys.argv = ["prefilter.py", "--day", issue.name]
        prefilter.main()
        sys.argv = ["cluster.py", "--day", issue.name] + (["--top", str(a.top)] if a.top else [])
        cluster.main()
    finally:
        sys.argv = argv0
    return 0


def cmd_script_check(a):
    import script_check as S
    ev = S.Evidence(S.load_cards(a.cards))
    res = S.check(Path(a.script).read_text(encoding="utf-8"), ev, day=a.day_type)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=_plain))
    return 1 if res.get("要改") else 0


def later_images(issue):
    """第 7 步时还没画、第 10 步会画的图：分镜 image_requests 的 id，加网页稿要的图（日卡、今日一词、头条、要闻、深度那一题；
    和 steps.Images.wanted 同一个算法）。这些图第 7 步找不到是正常的。"""
    def load(p):
        try:
            return json.loads((issue / p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    out = {"card"}
    for s in (load("04_文稿/claude_网页.json") or {}).get("sections") or []:
        if s.get("kind") == "term":
            out.add("term")
        elif s.get("kind") in ("headline", "brief", "deep"):
            out |= {str(it.get("id")).lower() for it in s.get("items") or [] if it.get("id")}
    for r in (load("04_文稿/视频v3_分镜.json") or {}).get("image_requests") or []:
        if isinstance(r, dict) and r.get("id"):
            out.add(str(r["id"]))
    return out


def tidy_warnings(text, later):
    """第 7 步的提醒去掉两种"本来就会这样"的噪声（2026-11-07 补），各并成一行放在最后：
      · 第 10 步才画的配图现在找不到（"找不到配图 X"，X 在 later 里）——不在 later 里的照旧单列，那多半是写错了文件名；
      · 第 14 步才截的原文截图现在没有记录（"没有截图记录"）——原句、中文行、出处签已经按事件卡逐字核过。
    别的行原样留着、顺序不变。"""
    keep, imgs, shots = [], [], []
    for line in (text or "").splitlines():
        s = line.strip()
        m = re.search(r"找不到配图 (\S+?)(?:（photo）)?(?:[，,]|$)", s)
        if s.startswith("提醒：") and m and Path(m.group(1)).stem in later:
            imgs.append(Path(m.group(1)).stem)
            continue
        if s.startswith("提醒：") and "没有截图记录" in s:
            shots.append(re.sub(r"\s*没有截图记录.*$", "", s[3:]).strip())
            continue
        keep.append(line)
    if imgs:
        keep.append("  配图 %d 张第 10 步才画（%s），这一步先按写了算" % (len(set(imgs)), "、".join(dict.fromkeys(imgs))))
    if shots:
        keep.append("  原文截图 %d 处第 14 步才截（%s）；原句、中文行、出处签已按事件卡逐字核过，截不到时自动退回原句摘录"
                    % (len(shots), "；".join(shots)))
    return "\n".join(keep)


def motion_summary(sb):
    """分镜里用了哪些新动效（给日志看，不是提醒）。"""
    import video3_storyboard as SB
    n = {}
    for c in sb.get("chapters") or []:
        for b in c.get("blocks") or []:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            names = ([{"headline_open": "开场速览", "num_chain": "数字递进"}[t]] if t in ("headline_open", "num_chain") else []) + \
                (["数字滚动"] if b.get("count") is True and t in SB.COUNT_BLOCKS else []) + \
                (["压在配图上"] if t in SB.PHOTO_BLOCKS and b.get("photo") else [])
            for k in names:
                n[k] = n.get(k, 0) + 1
    shots = len(SB.shot_owners(sb))
    if shots:
        n["原文截图／摘录"] = shots
    return "、".join("%s %d 处" % (k, v) for k, v in n.items())


def weekend_warnings(issue, sb):
    """周末视频旁白的禁用说法（《写稿_视频v3_周末.md》"程序检查"：周末、第几层、Dylan……；2026-11-07 补）。
    原来只有无声样片 video3_preview.py 查，第 7 步没查；现在第 7 步也查，只提醒、不拦（周日第一次真跑，不因为它停住）。"""
    from datetime import date
    ed = sb.get("edition")
    try:
        wk = ed in ("saturday_deep", "sunday_deep") or (not ed and date.fromisoformat(issue.name).weekday() in (5, 6))
    except ValueError:
        wk = False
    if not wk:
        return
    try:
        import video3_preview as PV
        bad, (lo, hi) = PV.weekend_lint(issue, sb)
    except Exception as e:  # noqa: BLE001  只是提醒
        print("  提醒：周末规则没查成（%s）" % e)
        return
    for x in bad:
        print("  提醒：周末规则：" + x + "——改掉再配音")
    n = sum(1 for c in sb.get("chapters") or [] if c.get("kind") == "story")
    if ed and not lo <= n <= hi:
        print("  提醒：周末规则：story 章 %d 章（%s 规定 %d–%d）" % (n, ed, lo, hi))


def stop_lines(e):
    """核对、旁白检查、时长检查停下来的原因（SystemExit 的话）逐条写成"✗ 要改"放在最后，返回退出码 1（2026-11-07 补）。
    总调度第 7 步只摘末几行带 ✗ 的交回写稿；原来只摘得到"核对失败""旁白不合规则"那一行标题，看不出是哪一句原话、哪个数字。"""
    lines = [x.strip() for x in str(e.code if e.code is not None else "").splitlines() if x.strip()]
    print("分镜检查没过：%s" % (lines[0] if lines else "检查没过"))
    for x in (lines[1:] or lines)[-12:]:
        print("  ✗ 要改：" + x)
    return 1


def cmd_storyboard(a):
    issue = Path(a.issue_dir).expanduser().resolve()
    import video3_build as V
    import video3_storyboard as SB
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            sb, cards, facts = V.prepare(issue, gen=False)       # 结构、事实、数字、触发词；核不上会 SystemExit
    except SystemExit as e:
        print(tidy_warnings(buf.getvalue(), later_images(issue)), flush=True)
        return stop_lines(e)
    print(tidy_warnings(buf.getvalue(), later_images(issue)), flush=True)
    weekend_warnings(issue, sb)
    if SB.motion_off():
        print("新动效开关关着（%s）：分镜里的新块和新字段这一期不用" % SB.motion_switch()[1])
    else:
        ms = motion_summary(sb)
        if ms:
            print("新动效：" + ms)
    try:
        V.lint_narration(issue)                          # 旁白禁用说法、"我"、读音表
        rules = V.load_rules()
        V.check_length(sb, rules)                        # 按字数估，超过 3 分钟就 SystemExit
    except SystemExit as e:
        return stop_lines(e)
    # 数值字段（2026-11-03 补）：播放器当数字读的 value 等写成了字（11-03 bill.yield 柱子塌掉、数字没出来）→ 要改
    vals = V.SB.check_values(sb)
    # 关系画面（2026-11-02 晚补）：一排小卡撑场、章里没有画关系的模板、国内外章没用 split、同排小卡有图没图混着 → 要改
    must, warn = V.SB.check_relations(sb)
    for w in warn:
        print("  提醒：" + w)
    if vals or must:         # 总调度只摘日志最后几行要紧的，所以"要改"放在最后
        what = (["数值字段 %d 处" % len(vals)] if vals else []) + (["关系画面 %d 处" % len(must)] if must else [])
        print("分镜检查没过：%s要改（规则见 写稿_视频v3.md「分镜 JSON：模板目录」%s）"
              % ("、".join(what), "「画面要画出关系」" if must else ""))
        for m in vals + must:
            print("  ✗ 要改：" + m)
        return 1
    print("分镜检查通过：%d 章" % len(sb.get("chapters") or []))
    return 0


SHOT_DIR = "06_配图/原文截图"
SHOT_SUMMARY = "06_配图/原文截图/本期截图.json"


def cmd_shots(a):
    """原文截图（2026-11-07 并入正式流程，fd 第 14 步组装视频之前调）：分镜里每一处 source_shot、原话卡的 shot、时间轴日子的 shot，
    按 fact 到事件卡找原句和来源网址，交给 site/tools/source_shots.mjs 截到 06_配图/原文截图/（同一网址、同一句、同一图位已经截成的不重截）。
    截不到（人机验证、付费墙、找不到原句、超时……）只记原因，组装时那一处自动退回原句摘录。结果写进 本期截图.json，
    每处一行打在屏幕上（fd 的日志和报告读它）。不管截没截成，退出码都是 0；出错也只写进 本期截图.json，不挡出片。"""
    issue = Path(a.issue_dir).expanduser().resolve()
    import video3_storyboard as SB
    import video3_trial as TR
    t0 = time.time()
    res = {"说明": "fd 第 14 步的原文截图（helpers.py shots）；截不到的那一处组装时退回原句摘录", "时间": time.strftime("%Y-%m-%d %H:%M:%S %z"),
           "开关": "开", "处数": 0, "成功": 0, "退回摘录": 0, "各处": []}
    out = issue / SHOT_SUMMARY
    try:
        if SB.motion_off():
            res["开关"] = "关（%s）" % SB.motion_switch()[1]
            print("新动效开关关着（%s）：不截图" % SB.motion_switch()[1])
            return 0
        sb = SB.load(issue / "04_文稿/视频v3_分镜.json")
        owners = [o for o in SB.shot_owners(sb) if o[1].get("type") != "source_excerpt" and o[2].get("fact")]
        res["处数"] = len(owners)
        if not owners:
            print("分镜里没有要截图的地方")
            return 0
        items = TR.shot_items(issue, sb)
        print("原文截图：%d 处（总时长最多 %d 秒，单页 25 秒）" % (len(items), a.total), flush=True)
        if a.offline:
            print("  离线：不截图，%d 处组装时退回原句摘录" % len(owners))
        elif items:
            TR.run_shots(issue, items, True, a.total)
        urls = {it["id"]: it["url"] for it in items}
        for c, b, o, slot, sid, where in owners:
            rec, png, why = SB.shot_problem(issue, sid, o, slot, b)
            ok = not why
            row = {"位置": where, "截图": str(sid), "网址": urls.get(str(sid)) or "", "结果": "用截图" if ok else "退回原句摘录"}
            if why:
                row["原因"] = why
            elif rec:
                row["截于"] = rec.get("shot_at")
            res["各处"].append(row)
            res["成功" if ok else "退回摘录"] += 1
            print("  %s %s：%s" % ("✓" if ok else "提醒：截图没用上", where, "截图（%s）" % sid if ok else why + "，退回原句摘录"))
    except BaseException as e:      # noqa: BLE001  截图只是锦上添花：出什么错都只记下来，不挡出片
        res["出错"] = "%s: %s" % (type(e).__name__, e)
        print("提醒：原文截图这一步出错（%s），截图处退回原句摘录" % res["出错"])
    finally:
        res["用时秒"] = round(time.time() - t0, 1)
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as e:
            print("提醒：本期截图.json 没写成（%s）" % e)
    print("原文截图：%d 处，用截图 %d、退回摘录 %d（%.0f 秒）" % (res["处数"], res["成功"], res["退回摘录"], res["用时秒"]))
    return 0


def cmd_mix(a):
    import podcast_mix as M
    overrides = None
    if a.dialog:
        import dialog_tts as D
        _, _, look = D.load_pairing()
        overrides = look.get("_声音包调整")
    r = M.mix_package(a.speech, a.out, package=a.package, title=a.title, overrides=overrides)
    brief = {k: v for k, v in (r or {}).items() if k not in ("时间线",)} if isinstance(r, dict) else r
    print("混音完成：" + json.dumps(brief, ensure_ascii=False, default=_plain)[:600])
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="总调度的子进程小工具（用法见文件开头）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cluster")
    c.add_argument("--issue-dir", required=True)
    c.add_argument("--top", type=int)
    s = sub.add_parser("script-check")
    s.add_argument("--script", required=True)
    s.add_argument("--cards", required=True)
    s.add_argument("--day-type")
    b = sub.add_parser("storyboard")
    b.add_argument("--issue-dir", required=True)
    sh = sub.add_parser("shots")
    sh.add_argument("--issue-dir", required=True)
    sh.add_argument("--total", type=int, default=150, help="截图总时长上限（秒，交给 source_shots.mjs）")
    sh.add_argument("--offline", action="store_true", help="不联网：不截图，全部退回原句摘录")
    m = sub.add_parser("mix")
    m.add_argument("--speech", required=True)
    m.add_argument("--out", required=True)
    m.add_argument("--title")
    m.add_argument("--package", default="v3")
    m.add_argument("--dialog", action="store_true")
    a = ap.parse_args(argv)
    fn = {"cluster": cmd_cluster, "script-check": cmd_script_check, "storyboard": cmd_storyboard, "shots": cmd_shots, "mix": cmd_mix}[a.cmd]
    return fn(a)


if __name__ == "__main__":
    sys.exit(main())
