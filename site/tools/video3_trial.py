#!/usr/bin/env python3
"""视频 v3 动效尝试版（2026-11-06 晚加；深夜补结合式：原话卡、时间轴日子带原文截图）：拿某一期的副本试新动效（原文截图＋荧光笔、数字递进、开场今日速览、数字滚动），
不动正式那一期，不配音、不生图、不花钱。

一条命令做完：
  1. 把 测试版/<日期>/ 复制到 ~/.cache/frontier-daily/动效尝试/<日期>/（原来有就整个移到废纸篓，不永久删）；
     原期的 11_视频v3/ 另存一份 修前_11_视频v3/（对比图的"修前"）；
  2. 按"加块说明"（JSON）改副本的分镜 04_文稿/视频v3_分镜.json：加块、换块、改字段、删块（写法见 site/tools/README_video3.md「动效尝试版」）；
  3. 分镜里每个 source_shot：按它的 fact 到事件卡找原句和来源网址，交给 site/tools/source_shots.mjs 截图（存到副本的 06_配图/原文截图/）；
     截不成的，组装时自动退回 source_excerpt（事件卡原句自己排版）；
  4. 用这一期现成的配音重组（video3_build.py --no-gen；旁白和现有配音对不上就停，绝不重配）；
  5. 录 预览.mp4 和 关键帧总览.jpg（video3_record.mjs），另拷一份放在副本根目录；
  6. 可选 --compare：同一时刻修前、修后并排的对比图。

用法（项目根）：
    PY=~/.venvs/frontier-daily/bin/python
    $PY site/tools/video3_trial.py --day 2026-11-07 --spec ~/.cache/frontier-daily/动效尝试/加块说明_1107.json
    $PY site/tools/video3_trial.py --day 2026-11-07 --spec … --reuse-shots      # 同一网址、同一句已经截过就不重截
    $PY site/tools/video3_trial.py --day 2026-11-07 --spec … --no-record        # 只重组演示页，不录预览（快，约 1 分钟）
    $PY site/tools/video3_trial.py --day 2026-11-07 --spec … --compare 6.2,21.5,47.0 [--compare-out <目录>]
    $PY site/tools/video3_trial.py --day 2026-11-07 --check-only --spec …       # 只复制、加块、过一遍分镜检查（不截图、不重组）
正式流程（fd 的 17 步、写稿提示词）不调用它；新模板只在尝试版的分镜里出现。

11-07 补（配图＋动效结合版，默认都不起作用）：
  · 加块说明可写顶层 "image_requests"（写法同正式分镜），补进副本分镜的 image_requests；id 和分镜里已有的重名就停。
  · --gen-images：重组之前给副本缺的视频配图生图（video3_images.ensure：先 agy、没成再 Codex，都是订阅），存到副本的 06_配图/视频/；
    不写就不生图（缺的图那一块不带图，和 --no-gen 一样）。重组本身仍是 --no-gen。
  · --reuse-images：同一个副本目录里上次生成的 06_配图/视频/ 留着（和 --reuse-shots 一样先暂存、复制完放回），不重画。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for p in (str(HERE), str(ROOT / "pipeline")):
    if p not in sys.path:
        sys.path.insert(0, p)

TRIAL_ROOT = Path.home() / ".cache/frontier-daily/动效尝试"
STORYBOARD = "04_文稿/视频v3_分镜.json"
SHOT_DIR = "06_配图/原文截图"
IMG_DIR = "06_配图/视频"            # 视频配图（image_requests 生成的；11-07 补 --gen-images / --reuse-images）
BEFORE = "修前_11_视频v3"


def say(*a):
    print(*a, flush=True)


def trash(path):
    """移到废纸篓（~/.Trash，同名的加时间戳），不永久删除。"""
    path = Path(path)
    if not path.exists():
        return None
    tr = Path.home() / ".Trash"
    tr.mkdir(exist_ok=True)
    dst = tr / ("%s_%s" % (path.name, time.strftime("%Y%m%d-%H%M%S")))
    shutil.move(str(path), str(dst))
    return dst


# ---------------------------------------------------------------- 1. 复制
def copy_issue(src, dst, keep_shots, keep_images=False):
    old_shots = old_imgs = None
    if dst.exists():
        if keep_shots and (dst / SHOT_DIR).exists():
            old_shots = Path(str(dst) + "_截图暂存")
            if old_shots.exists():
                trash(old_shots)
            shutil.copytree(dst / SHOT_DIR, old_shots)
        if keep_images and (dst / IMG_DIR).exists():      # 11-07：上次在副本里生成的视频配图（--reuse-images）
            old_imgs = Path(str(dst) + "_配图暂存")
            if old_imgs.exists():
                trash(old_imgs)
            shutil.copytree(dst / IMG_DIR, old_imgs)
        t = trash(dst)
        say("旧的尝试版移到了废纸篓：%s" % t)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, symlinks=True, ignore=shutil.ignore_patterns(".DS_Store", "logs"))
    if (dst / "11_视频v3").exists():
        shutil.copytree(dst / "11_视频v3", dst / BEFORE)
    if old_shots:
        (dst / SHOT_DIR).parent.mkdir(parents=True, exist_ok=True)
        if (dst / SHOT_DIR).exists():
            trash(dst / SHOT_DIR)                # 副本里刚复制来的（正式那一期本来没有截图，这里只是保险；移到废纸篓）
        shutil.move(str(old_shots), str(dst / SHOT_DIR))
    if old_imgs:
        restore_images(old_imgs, dst / IMG_DIR)
    say("副本：%s（来自 %s）" % (dst, src))


def restore_images(stash, d):
    """把暂存的视频配图放回副本：原期里已有的同名文件以原期为准（不覆盖），其余放回；来源.json 只补原期没有的键。暂存目录移到废纸篓。"""
    d.mkdir(parents=True, exist_ok=True)
    back = []
    for f in sorted(stash.iterdir()):
        if f.name == "来源.json" and (d / f.name).exists():
            try:
                cur = json.loads((d / f.name).read_text(encoding="utf-8"))
                old = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            add = {k: v for k, v in old.items() if k not in cur}
            if add:
                cur.update(add)
                (d / f.name).write_text(json.dumps(cur, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                back.append("来源.json（补 %s）" % "、".join(add))
            continue
        if (d / f.name).exists():
            continue
        shutil.move(str(f), str(d / f.name))
        back.append(f.name)
    trash(stash)
    if back:
        say("  上次生成的视频配图放回副本：%s" % "、".join(back))


# ---------------------------------------------------------------- 2. 加块说明
def apply_spec(sb, spec):
    """按加块说明改分镜。ops 每一项：
         {"chapter": 章 id, "add": 块, "after": 块 id | "before": 块 id}   不写 after/before 就加在这一章最后
         {"chapter": 章 id, "replace": 块 id, "with": 块}
         {"chapter": 章 id, "set": 块 id, "fields": {字段: 值}}            字段写 null 表示去掉这个字段
         {"chapter": 章 id, "set": 块 id, "tick": 第几个日子（从 0 数）, "fields": {…}}   改时间轴某一个日子的字段（结合式的 shot 用）
         {"chapter": 章 id, "remove": 块 id}
       facts：要补进分镜 facts 的键（已有同名键时必须一模一样）。返回改动说明。"""
    log, bad = [], []
    facts = sb.setdefault("facts", {})
    for k, v in (spec.get("facts") or {}).items():
        if k in facts and facts[k] != v:
            bad.append("facts 里已有 %s，和加块说明里写的不一样" % k)
        facts[k] = v
    if spec.get("image_requests"):          # 11-07：尝试版新画的视频配图（写法同正式分镜的 image_requests）
        reqs = sb.setdefault("image_requests", [])
        have = {r.get("id") for r in reqs if isinstance(r, dict)}
        for r in spec["image_requests"]:
            rid = r.get("id") if isinstance(r, dict) else None
            if not rid or rid in have:
                bad.append("image_requests 的 %r %s" % (rid, "和分镜里已有的重名" if rid else "没写 id"))
                continue
            have.add(rid)
            reqs.append(r)
            log.append("image_requests 加 %s（%s）" % (rid, "生成" if r.get("brief_en") else "资料图" if r.get("commons") else "?"))
    chs = {c.get("id"): c for c in sb.get("chapters") or []}
    for i, op in enumerate(spec.get("ops") or []):
        c = chs.get(op.get("chapter"))
        if not c:
            bad.append("第 %d 条：没有这一章 %r" % (i + 1, op.get("chapter")))
            continue
        bl = c.setdefault("blocks", [])
        ids = [b.get("id") for b in bl]

        def at(bid):
            if bid not in ids:
                bad.append("第 %d 条：「%s」里没有块 %r（现有：%s）" % (i + 1, c["id"], bid, "、".join(map(str, ids))))
                return None
            return ids.index(bid)
        if "add" in op:
            b = op["add"]
            if b.get("id") in ids:
                bad.append("第 %d 条：「%s」里已经有块 %s" % (i + 1, c["id"], b.get("id")))
                continue
            k = len(bl)
            if op.get("after"):
                j = at(op["after"])
                if j is None:
                    continue
                k = j + 1
            elif op.get("before"):
                j = at(op["before"])
                if j is None:
                    continue
                k = j
            bl.insert(k, b)
            log.append("「%s」加 %s/%s（第 %d 块）" % (c["id"], b.get("type"), b.get("id"), k + 1))
        elif "replace" in op:
            j = at(op["replace"])
            if j is None:
                continue
            old = bl[j]
            bl[j] = op["with"]
            log.append("「%s」%s/%s 换成 %s/%s" % (c["id"], old.get("type"), old.get("id"), op["with"].get("type"), op["with"].get("id")))
        elif "set" in op:
            j = at(op["set"])
            if j is None:
                continue
            tgt, what = bl[j], op["set"]
            if "tick" in op:                     # 时间轴某一个日子
                ticks = bl[j].get("ticks") or []
                k = op["tick"]
                if not isinstance(k, int) or isinstance(k, bool) or not 0 <= k < len(ticks) or not isinstance(ticks[k], dict):
                    bad.append("第 %d 条：「%s」%s 没有第 %r 个日子（从 0 数，共 %d 个）" % (i + 1, c["id"], op["set"], k, len(ticks)))
                    continue
                tgt, what = ticks[k], "%s 第 %d 个日子" % (op["set"], k + 1)
            for f, v in (op.get("fields") or {}).items():
                if v is None:
                    tgt.pop(f, None)
                else:
                    tgt[f] = v
            log.append("「%s」%s 改字段 %s" % (c["id"], what, "、".join(op.get("fields") or {})))
        elif "remove" in op:
            j = at(op["remove"])
            if j is None:
                continue
            old = bl.pop(j)
            log.append("「%s」去掉 %s/%s" % (c["id"], old.get("type"), old.get("id")))
        else:
            bad.append("第 %d 条：不认识的操作（要 add / replace / set / remove）" % (i + 1))
    if bad:
        raise SystemExit("加块说明有问题：\n  " + "\n  ".join(bad))
    note = spec.get("说明")
    if note:
        sb["说明"] = (sb.get("说明") or "") + "（动效尝试版：%s）" % note
    return log


# ---------------------------------------------------------------- 3. 截图
def shot_items(issue, sb):
    """分镜里每一处要截图的地方 → 截图工具的输入（id、网址、原句、出处名、日期、图位），按事件卡来源找网址。
    要截的：source_shot（图位 full）、post_card / quote_card 的 shot（card）、时间轴日子的 shot（tick）；source_excerpt 不截。
    图位决定截图的宽高比（source_shots.mjs 的 SLOT_AR）：卡片图位要扁一些，弹出框居中。"""
    import video3_storyboard as SB
    cards = {c["event_id"]: c for c in json.loads((issue / "03_事件卡/cards_写稿用.json").read_text(encoding="utf-8"))}
    items, bad = [], []
    for c, b, o, slot, sid, where in SB.shot_owners(sb):
        if b.get("type") == "source_excerpt" or not o.get("fact"):
            continue
        f = (sb.get("facts") or {}).get(o.get("fact")) or {}
        card = cards.get(f.get("event"))
        lst = (card or {}).get(f.get("field")) or []
        e = lst[f["index"]] if isinstance(f.get("index"), int) and f["index"] < len(lst) else None
        if not isinstance(e, dict):
            bad.append("%s：fact %r 在事件卡里找不到" % (where, o.get("fact")))
            continue
        src = next((s for s in card.get("sources") or [] if s.get("id") == e.get("source_id")), None)
        if not src:
            bad.append("%s：事件卡 %s 里找不到这条的来源" % (where, f.get("event")))
            continue
        items.append({"id": sid, "url": src["url"], "quote": o.get("quote") or "", "slot": slot,
                      "source": src.get("name") or "", "date": (src.get("date") or "")[:10]})
    for x in bad:
        say("  提醒：" + x)
    return items


def run_shots(issue, items, reuse, total):
    out = issue / SHOT_DIR
    out.mkdir(parents=True, exist_ok=True)
    todo = []
    for it in items:
        jp = out / (it["id"] + ".json")
        if reuse and jp.exists():
            try:
                rec = json.loads(jp.read_text(encoding="utf-8"))
            except ValueError:
                rec = {}
            if (rec.get("ok") and rec.get("url") == it["url"] and rec.get("quote") == it["quote"] and rec.get("slot", "full") == it.get("slot", "full")
                    and (out / (rec.get("png") or "")).is_file()):
                say("  截图：%s 已有（%s），不重截" % (it["id"], rec.get("shot_at")))
                continue
        todo.append(it)
    if not todo:
        return
    inp = out / "输入.json"
    inp.write_text(json.dumps({"items": todo}, ensure_ascii=False, indent=1), encoding="utf-8")
    r = subprocess.run(["node", str(HERE / "source_shots.mjs"), str(inp), str(out), "--total", str(total)], cwd=str(ROOT))
    if r.returncode:
        say("  提醒：截图工具退出码 %d（截不成的块组装时会退回摘录）" % r.returncode)


def shot_report(issue, sb):
    import video3_storyboard as SB
    rows = []
    for c, b, o, slot, sid, where in SB.shot_owners(sb):
        if b.get("type") == "source_excerpt":
            continue
        jp = issue / SHOT_DIR / (str(sid) + ".json")
        rec = json.loads(jp.read_text(encoding="utf-8")) if jp.exists() else {}
        if rec.get("ok"):
            fu = SB.shot_font_u(rec, slot, b, o)
            info = "%s；%s%s" % (rec.get("match") or "", rec.get("edge") or "", "；原句约 %.2f（字幕 %.2f）" % (fu, SB.SUB_U) if fu else "")
        else:
            info = rec.get("reason") or "没截"
        rows.append("  %s %s（%s）：%s" % ("成功" if rec.get("ok") else "失败", where, sid, info))
    return rows


# ---------------------------------------------------------------- 3b. 视频配图（11-07 补，--gen-images 才做）
def gen_images(issue, sb):
    """副本分镜 image_requests 里缺的图：照正式流程生成（video3_images.ensure，先 agy 再 Codex），存到副本的 06_配图/视频/。已有的不重画。"""
    import video3_images as IMG
    import video3_storyboard as SB
    reqs = SB.image_requests(sb)
    if not reqs:
        return {}
    say("视频配图：%d 张（缺的才画）" % len(reqs))
    return IMG.ensure(issue, reqs, sb.get("accent"), gen=True)


# ---------------------------------------------------------------- 4. 重组（不配音）
def rebuild(issue):
    import video3_build as VB

    def no_voice(*_a, **_k):
        raise SystemExit("尝试版不配音：旁白和这一期现有的配音对不上（加块说明不能改 narration），停")
    VB.voice = no_voice
    return VB.main([str(issue), "--no-gen"])


# ---------------------------------------------------------------- 6. 对比图
def compare(issue, times, outdir):
    from PIL import Image, ImageDraw, ImageFont
    outdir.mkdir(parents=True, exist_ok=True)
    tmp = outdir / "_帧"
    for name, d in (("修前", issue / BEFORE), ("修后", issue / "11_视频v3")):
        subprocess.run(["node", str(HERE / "video3_frames.mjs"), str(d), str(tmp / name), "--t", ",".join("%.2f" % t for t in times)],
                       cwd=str(ROOT), check=True)
    font = None
    for fp in ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/STHeiti Medium.ttc"):
        try:                              # 11-06 深夜：这台机器上 PingFang 打不开，标题成了方框，按顺序找能显示中文的字体
            font = ImageFont.truetype(fp, 26)
            break
        except OSError:
            continue
    font = font or ImageFont.load_default()
    pairs = []
    for t in times:
        a = Image.open(tmp / "修前" / ("f_%.2f.png" % t)).convert("RGB")
        b = Image.open(tmp / "修后" / ("f_%.2f.png" % t)).convert("RGB")
        w, h = a.size
        im = Image.new("RGB", (w * 2 + 24, h + 56), (40, 36, 31))
        im.paste(a, (0, 56)), im.paste(b, (w + 24, 56))
        dr = ImageDraw.Draw(im)
        dr.text((12, 12), "修前 · %.1f 秒" % t, fill=(255, 255, 255), font=font)
        dr.text((w + 36, 12), "修后（动效尝试版）· %.1f 秒" % t, fill=(255, 220, 200), font=font)
        p = outdir / ("对比_%06.2f秒.jpg" % t)
        im.save(p, quality=88)
        pairs.append(im)
    if pairs:       # 总览：每对缩成一行
        sw = 1280
        rows = [p.resize((sw, int(p.size[1] * sw / p.size[0]))) for p in pairs]
        sheet = Image.new("RGB", (sw, sum(r.size[1] for r in rows) + 8 * len(rows)), (40, 36, 31))
        y = 0
        for r in rows:
            sheet.paste(r, (0, y))
            y += r.size[1] + 8
        sheet.save(outdir / "对比总览.jpg", quality=85)
    say("对比图：%d 组 → %s（单帧原图在 %s）" % (len(pairs), outdir, tmp))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", required=True, help="哪一期（测试版/<日期>）")
    ap.add_argument("--spec", required=True, help="加块说明 JSON")
    ap.add_argument("--src", help="从哪个目录复制（默认 测试版/<日期>，只读）")
    ap.add_argument("--out", help="副本放哪里（默认 ~/.cache/frontier-daily/动效尝试/<日期>）")
    ap.add_argument("--reuse-shots", action="store_true", help="同一网址、同一句已经截过就不重截")
    ap.add_argument("--no-shots", action="store_true", help="不截图（source_shot 全部退回摘录）")
    ap.add_argument("--shots-total", type=int, default=180, help="截图总时长上限（秒）")
    ap.add_argument("--gen-images", action="store_true", help="重组前给副本缺的视频配图生图（先 agy 再 Codex，订阅额度）；不写就不生图")
    ap.add_argument("--reuse-images", action="store_true", help="同一个副本目录里上次生成的视频配图留着，不重画")
    ap.add_argument("--no-record", action="store_true", help="只重组演示页，不录预览")
    ap.add_argument("--sheet-only", action="store_true", help="不录预览视频，只出关键帧总览")
    ap.add_argument("--check-only", action="store_true", help="只复制、加块、过分镜检查")
    ap.add_argument("--compare", help="对比图的时刻（秒，逗号隔开）")
    ap.add_argument("--compare-out", help="对比图放哪里（默认 副本/对比图）")
    a = ap.parse_args(argv)
    # 11-07：尝试版本来就是试新动效的，fd_开关.json 关着也照画（命令前写 FD_MOTION=off 才关）
    os.environ.setdefault("FD_MOTION", "on")
    src = Path(a.src).expanduser().resolve() if a.src else ROOT / "测试版" / a.day
    dst = Path(a.out).expanduser().resolve() if a.out else TRIAL_ROOT / a.day
    if not (src / STORYBOARD).exists():
        raise SystemExit("找不到 %s" % (src / STORYBOARD))
    if dst.resolve() == src.resolve() or str(dst.resolve()).startswith(str((ROOT / "测试版").resolve())):
        raise SystemExit("副本不能放在 测试版/ 里（正式那一期只读）")
    spec = json.loads(Path(a.spec).expanduser().read_text(encoding="utf-8"))
    if spec.get("date") and spec["date"] != a.day:
        raise SystemExit("加块说明写的是 %s，命令给的是 %s" % (spec["date"], a.day))
    copy_issue(src, dst, keep_shots=a.reuse_shots, keep_images=a.reuse_images)
    shutil.copy2(Path(a.spec).expanduser(), dst / "加块说明.json")
    sbp = dst / STORYBOARD
    sb = json.loads(sbp.read_text(encoding="utf-8"))
    narr0 = [c.get("narration") for c in sb.get("chapters") or []]
    for x in apply_spec(sb, spec):
        say("  " + x)
    if [c.get("narration") for c in sb.get("chapters") or []] != narr0:
        raise SystemExit("加块说明改了旁白：尝试版只用现成配音，旁白一个字都不能动")
    sbp.write_text(json.dumps(sb, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.check_only:
        import video3_build as VB
        VB.prepare(dst, gen=False)
        say("分镜检查通过（--check-only：没截图、没重组）")
        return 0
    if not a.no_shots:
        items = shot_items(dst, sb)
        if items:
            say("截图：%d 处（source_shot 和结合式的 shot）" % len(items))
            run_shots(dst, items, a.reuse_shots, a.shots_total)
    for r in shot_report(dst, sb):
        say(r)
    if a.gen_images:
        gen_images(dst, sb)
    rc = rebuild(dst)
    if rc:
        return rc
    if not a.no_record:
        cmd = ["node", str(HERE / "video3_record.mjs"), str(dst)] + (["--sheet"] if a.sheet_only else [])
        subprocess.run(cmd, cwd=str(ROOT), check=True)
        for f in ("预览.mp4", "关键帧总览.jpg"):
            if (dst / "11_视频v3" / f).exists():
                shutil.copy2(dst / "11_视频v3" / f, dst / f)
    if a.compare:
        ts = [float(x) for x in re.split(r"[,，\s]+", a.compare.strip()) if x]
        compare(dst, ts, Path(a.compare_out).expanduser() if a.compare_out else dst / "对比图")
    say("尝试版：%s" % dst)
    for f in ("预览.mp4", "关键帧总览.jpg"):
        if (dst / f).exists():
            say("  %s" % (dst / f))
    return 0


if __name__ == "__main__":
    sys.exit(main())
