#!/usr/bin/env python3
"""用 Antigravity CLI（agy，Google AI Pro 订阅额度，不另花钱）画一张配图，存到指定路径。

（2026-11-03：视频配图已接入，video3_images.py 先用它、没成再 Codex；网页配图和 steps.py 第 10 步还没接。）

    PY=~/.venvs/frontier-daily/bin/python
    $PY site/tools/agy_image.py --check                                   # 只查登录和额度：不画图、不花额度
    $PY site/tools/agy_image.py --out <期>/06_配图/e002.png --aspect 16:9 --prompt-file brief.txt
    $PY site/tools/agy_image.py --out x.png --aspect 1:1 --prompt "Image brief. ..." --log x.agy.json

怎么画：在一个临时空文件夹里跑 `agy -p`（无人值守的“打印模式”），由便宜的 Gemini 3.8 Flash (Low) 当调度，
它把活交给 agy 自带的 image-generator 子代理，子代理调用 generate_image（Nano Banana 2）。我们要求子代理
把提示词“一字不改”地交给画图工具；画好的图落在 ~/.gemini/antigravity-cli/brain/<对话号>/ 里（JPEG），
本脚本自己把它找出来、按 --out 的扩展名另存（.png 转成 PNG；.jpg 原样复制），不让 agent 动任何文件。
默认在提示词末尾加一段暖色白平衡、无品牌设备、禁用套路重申的补充（STYLES["warm"]，只对 agy 生效）；--style none 关掉。
"写实科技风"那段（11-06 起）在 video3_images.py 的 STYLE_TECH 里，随 palette_style 进提示词，agy 和 Codex 共用。

输出尺寸由 agy 固定（约 1K）：16:9 是 1376×768，1:1 是 1024×1024；没有更大尺寸的开关。
网页最大只用 1400 宽（build_v3.py），视频用 1600 以内，够用但比 Codex 的 1672×941 小一些。

退出码（主流程可据此决定换不换后备）：
    0 成功   1 其他错误   2 参数不对   3 额度用完   4 没登录/登录过期   5 超时   6 没拿到图或图不合格   7 本机没有 agy
"""
import argparse
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

AGY_DEFAULT = Path.home() / ".local/bin/agy"
BRAIN = Path.home() / ".gemini/antigravity-cli/brain"
ASPECTS = {"1:1": 1.0, "2:3": 2 / 3, "3:2": 1.5, "3:4": 0.75, "4:3": 4 / 3, "9:16": 9 / 16, "16:9": 16 / 9}   # generate_image 支持的比例
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
EXIT_MSG = {
    1: "agy 出错了（原因见上面的说明和日志）",
    2: "参数不对",
    3: "Antigravity 的额度用完了（Google AI Pro 的 5 小时或每周额度），等额度刷新后再画，或换后备",
    4: "agy 没登录或登录过期：需要用户本人在终端运行一次 agy 重新登录（出门在外时只能等回来）",
    5: "超时：agy 在限定时间内没画完",
    6: "agy 跑完了但没拿到合格的图",
    7: "本机没有 agy 命令",
}
QUOTA_RE = re.compile(r"quota|RESOURCE_EXHAUSTED|\b429\b|credits balance is too low|out of credits|rate.?limit|limit (?:reached|exceeded)|exhausted",
                      re.I)
AUTH_RE = re.compile(r"authentication required|not (?:signed|logged) in|sign[ -]?in|log[ -]?in|unauthenticated|\b401\b|invalid_grant|"
                     r"credential|eligibility check failed|ineligible", re.I)

# 只给 agy 加的画风补充（一处改）：11-03 对比发现 Nano Banana 2 比 Codex 偏冷偏暗，还会画出像 iMac 的显示器。
# 11-03 下午用户要求 agy 的图科技感再强一些，当时在这里加了 "Make it feel unmistakably high-tech" 一段。
# 11-06 午：那段挪进 video3_images.py 的 STYLE_TECH，agy 和 Codex 共用（"写实科技风"两家一致），并改成科技感来自基础设施、
# 实验设备、材料和光层；这里只留 agy 需要额外强调的：暖色白平衡、无品牌设备（11-04、11-06 退回的全是像 Mac Studio、iPhone、
# Studio Display、戴尔显示器的设备）、禁用套路（11-06 e006 画了挂锁）。
# 键名仍叫 "warm"（别处按这个名字引用）。默认 --style warm；--style none 关掉。补充接在提示词末尾，一起原样交给画图工具。
# 11-08 晚：不再一律暖光（去掉"整体暖色白平衡、金色夕阳、夜里暖灯、不要阴天和蓝调"）——光线跟着题材和场景走，白平衡按真实光源；
# 也不加任何数字光层（和 video3_images.py 的系列画风同一天改）。无品牌设备、禁用套路照旧。
STYLES = {
    "warm": ("\nRendering notes: realistic, well-exposed light that matches the scene and the subject (daylight, overcast, night practicals, cool "
             "white lab or cleanroom light or neutral indoor light, as the subject line asks); white balance true to the real light source, "
             "not pushed warm, and no golden-hour or sunset look unless the subject asks for it. No added glow layer, light trails or "
             "holographic overlay: every light comes from a real source in the scene. Premium magazine colour grading. "
             "Follow the 'Strictly avoid' list to the letter, even where the subject seems to ask for one of those motifs: no padlocks or "
             "keys, no globes, no glowing brains, no robots, no circuit-board or node-web patterns, no text or numbers. "
             "Every device is a generic, unbranded design that resembles no real product line: any computer, workstation or screen looks "
             "like plain industrial or lab equipment (boxy, matte, with visible screws, vents or handles), never a sleek, polished "
             "consumer gadget; keep phones, laptops and monitors out of close-up."),
    "none": "",
}
DEFAULT_MODEL = "gemini-3.8-flash-low"

PROMPT_TMPL = (
    "Have the image generator make exactly ONE image. It must call generate_image once with AspectRatio \"{aspect}\" and use the text "
    "between <<<PROMPT and PROMPT>>> as the Prompt VERBATIM: do not rewrite, shorten, summarise or translate it. Only if the first result "
    "clearly breaks a rule in the text (visible text, logos, people) may it try again with the same prompt. Do not copy, move, convert or "
    "edit any file. Reply with only the absolute path of the final image.\n\n<<<PROMPT\n{prompt}\nPROMPT>>>")


def say(*a):
    print(*a, file=sys.stderr, flush=True)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")       # 写进长期文件的时间读系统时钟


def find_agy():
    p = shutil.which("agy")
    if p:
        return p
    return str(AGY_DEFAULT) if AGY_DEFAULT.is_file() else None


def clean_env():
    """只带 HOME/PATH/USER/LANG：不把本项目或别处的 GEMINI_API_KEY、GOOGLE_* 之类变量带进去，免得 agy 改走按量付费的密钥。"""
    env = {k: os.environ[k] for k in ("HOME", "PATH", "USER") if k in os.environ}
    env["LANG"] = "en_US.UTF-8"
    local_bin = str(Path.home() / ".local/bin")
    if local_bin not in env.get("PATH", "").split(":"):
        env["PATH"] = env.get("PATH", "/usr/bin:/bin") + ":" + local_bin
    return env


def run(cmd, cwd, timeout):
    """跑一个命令；超时就把它和它带起来的子进程一起结束。返回 (退出码, stdout, stderr, 是否超时)。"""
    p = subprocess.Popen(cmd, cwd=cwd, env=clean_env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
        return p.returncode, out or "", err or "", False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGTERM)
            time.sleep(3)
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        out, err = p.communicate()
        return -9, out or "", err or "", True


def parse_json(text):
    text = (text or "").strip()
    for cand in (text, text[text.find("{"):] if "{" in text else ""):
        try:
            return json.loads(cand)
        except (ValueError, TypeError):
            continue
    return {}


def check(agy, timeout=90):
    """查登录和额度（agy 自己回答 /usage，不开对话、不花额度）。返回 (退出码, 说明, 额度明细)。"""
    with tempfile.TemporaryDirectory(prefix="agy_check_") as ws:
        code, out, err, to = run([agy, "-p", "/usage", "--output-format", "json"], ws, timeout)
    if to:
        return 4, "查额度 %d 秒没有回音：多半是没登录或登录过期（也可能是网络）" % timeout, []
    d = parse_json(out)
    groups = (((d.get("command") or {}).get("data") or {}).get("groups")) or []
    if code != 0 or d.get("status") != "SUCCESS" or not groups:
        blob = " ".join([d.get("error") or "", err, out])
        if AUTH_RE.search(blob):
            return 4, "agy 说没登录：%s" % (d.get("error") or err.strip() or out.strip())[:300], []
        return 1, "查额度失败（退出码 %s）：%s" % (code, (d.get("error") or err.strip() or out.strip())[:300]), []
    rows = []
    for g in groups:
        for b in g.get("buckets") or []:
            rows.append({"group": g.get("name"), "id": b.get("id"), "window": b.get("window"),
                         "remaining": b.get("remaining_fraction"), "reset": b.get("reset_time")})
    gem = [r for r in rows if r["group"] == "Gemini Models"]     # Flash 调度和 Nano Banana 画图都记在 Gemini 这一组（11-03 实测）
    empty = [r for r in gem if (r["remaining"] or 0) <= 0.005]
    if empty:
        return 3, "Gemini 额度用完：%s" % "；".join("%s 窗口 %s 刷新" % (r["window"], r["reset"]) for r in empty), rows
    return 0, "；".join("%s %s 剩 %.1f%%" % (r["group"], r["window"], 100 * (r["remaining"] or 0)) for r in rows), rows


def images_in(cid, since):
    d = BRAIN / cid
    if not cid or not d.is_dir():
        return []
    fs = [Path(f) for f in glob.glob(str(d / "*")) if f.lower().endswith(IMG_EXT)]
    fs = [f for f in fs if f.stat().st_mtime >= since - 5]
    return sorted(fs, key=lambda f: f.stat().st_mtime)


def subagent_calls(cid):
    """从子代理的记录里找出它实际调用 generate_image 的参数（用来核对提示词有没有被改写、画了几次）。"""
    calls = []
    for sj in glob.glob(str(BRAIN / cid / ".system_generated/subagents/*.json")):
        try:
            sid = json.loads(Path(sj).read_text(encoding="utf-8")).get("conversationId")
        except (OSError, ValueError):
            continue
        tf = BRAIN / str(sid) / ".system_generated/logs/transcript_full.jsonl"
        if not tf.is_file():
            continue
        for line in tf.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                st = json.loads(line)
            except ValueError:
                continue
            for tc in st.get("tool_calls") or []:
                if tc.get("name") == "generate_image":
                    calls.append(tc.get("args") or {})
            if st.get("type") == "GENERIC" and "error" in (st.get("content") or "").lower():
                calls.append({"_error": (st.get("content") or "")[:500]})
    return calls


def save_as(src, out):
    """按输出扩展名另存：.jpg/.jpeg 原样复制；.png/.webp 用 PIL 转。先写临时文件再改名，半成品不会冒充成品。"""
    from PIL import Image
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    ext = out.suffix.lower()
    with Image.open(src) as im:
        im.load()
        if ext in (".jpg", ".jpeg") and (im.format or "").upper() == "JPEG":
            shutil.copyfile(src, tmp)
        elif ext in (".jpg", ".jpeg"):
            im.convert("RGB").save(tmp, "JPEG", quality=95)
        elif ext == ".webp":
            im.convert("RGB").save(tmp, "WEBP", quality=92, method=6)
        else:
            im.convert("RGB").save(tmp, "PNG", optimize=True)
    os.replace(tmp, out)


def generate(agy, prompt, out, aspect="16:9", model=DEFAULT_MODEL, timeout=420, min_side=700, style="warm"):
    """画一张、存到 out。返回 (退出码, 一句话说明, 细节)。别的脚本可直接 import 调用（不做开画前检查，需要时先调 check）。"""
    out = Path(out)
    prompt = prompt.strip() + STYLES.get(style, "")
    info = {"tool": "Antigravity CLI generate_image（Nano Banana 2，Google AI Pro 订阅）", "model": model, "aspect": aspect, "style": style,
            "started": now(), "out": str(out)}
    t0 = time.time()
    ws = tempfile.mkdtemp(prefix="agy_img_")      # 空工作区：agent 看不到项目文件，也不会往项目里写东西
    try:
        cmd = [agy, "-p", PROMPT_TMPL.format(aspect=aspect, prompt=prompt.strip()), "--model", model, "--output-format", "json",
               "--print-timeout", "%ds" % timeout]
        code, outp, err, to = run(cmd, ws, timeout + 60)
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    info["secs"] = round(time.time() - t0)
    d = parse_json(outp)
    cid = d.get("conversation_id") or ""
    info.update({"exit": code, "status": d.get("status"), "conversation_id": cid, "usage": d.get("usage"),
                 "response": (d.get("response") or "")[-600:], "error": d.get("error"), "stderr": err[-1500:]})
    calls = subagent_calls(cid) if cid else []
    info["generate_image_calls"] = calls
    gen = [c for c in calls if "Prompt" in c]
    if gen:
        info["prompt_used"] = gen[-1].get("Prompt")
        info["prompt_verbatim"] = gen[-1].get("Prompt", "").strip() == prompt.strip()
        info["attempts"] = len(gen)
    imgs = images_in(cid, t0)
    # 回答里点名的那张优先（子代理最多试 3 次，回答里是最终那张）
    named = [Path(m) for m in re.findall(r"(/\S+?\.(?:jpe?g|png|webp))", info["response"] or "", re.I)]
    named = [p for p in named if p.is_file() and p in imgs] or imgs[-1:]
    # 判断失败原因时只看 agy 的报错和回答，不看提示词本身（提示词里可能碰巧有 "sign in" 之类的字）
    blob = " ".join(str(x) for x in (d.get("error"), err, info["response"], " ".join(c.get("_error", "") for c in calls)))
    if not named:
        if to:
            return 5, "超时（%d 秒）" % info["secs"], info
        if QUOTA_RE.search(blob):
            return 3, "agy 报额度不足：%s" % (d.get("error") or err.strip() or info["response"]).strip()[:300], info
        if AUTH_RE.search(blob) and code != 0:            # 没登录时 agy 先打印登录网址、约 60 秒后报 "authentication failed or timed out"
            return 4, "agy 报登录问题：%s" % (d.get("error") or err.strip()).strip()[:300], info
        if d.get("status") in ("CANCELED", "INTERRUPTED") or re.search(r"timed? ?out|deadline", blob, re.I):
            return 5, "agy 自己的时限到了（%d 秒）：%s" % (info["secs"], (d.get("error") or err.strip()).strip()[:200]), info
        return 6, "没找到生成的图（退出码 %s，状态 %s）：%s" % (code, d.get("status"), (d.get("error") or info["response"] or err).strip()[:300]), info
    src = named[0]
    info["source"] = str(src)
    from PIL import Image
    try:
        with Image.open(src) as im:
            im.verify()
        with Image.open(src) as im:
            w, h = im.size
    except Exception as e:  # noqa: BLE001
        return 6, "生成的图打不开：%s" % e, info
    info["size"] = [w, h]
    want = ASPECTS[aspect]
    if abs((w / h) - want) / want > 0.04:
        return 6, "比例不对：要 %s，拿到 %d×%d" % (aspect, w, h), info
    if min(w, h) < min_side:
        return 6, "图太小：%d×%d（短边要求至少 %d）" % (w, h, min_side), info
    save_as(src, out)
    info["finished"] = now()
    return 0, "%d×%d，%d 秒，%s" % (w, h, info["secs"], "提示词一字未改" if info.get("prompt_verbatim") else "注意：提示词被子代理改写过"), info


def main(argv=None):
    ap = argparse.ArgumentParser(description="用 agy（Google AI Pro 订阅）画一张配图")
    ap.add_argument("--check", action="store_true", help="只查登录和额度，不画图")
    ap.add_argument("--prompt", help="提示词文本")
    ap.add_argument("--prompt-file", help="从文件读提示词（UTF-8）")
    ap.add_argument("--out", help="输出路径（.png / .jpg / .webp）")
    ap.add_argument("--aspect", default="16:9", choices=sorted(ASPECTS), help="画幅比例，默认 16:9")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="调度用的模型（只负责转交，画图模型固定是 Nano Banana 2）")
    ap.add_argument("--style", default="warm", choices=sorted(STYLES), help="给 agy 加的画风补充：warm（默认，暖色、无品牌设备、禁用套路）/ none")
    ap.add_argument("--timeout", type=int, default=420, help="单张最长等多少秒，默认 420")
    ap.add_argument("--min-side", type=int, default=700, help="短边至少多少像素，默认 700（16:9 实际是 768）")
    ap.add_argument("--log", help="把这次的细节（实际提示词、对话号、耗时、尺寸）写成 JSON")
    ap.add_argument("--no-precheck", action="store_true", help="跳过开画前的额度检查")
    a = ap.parse_args(argv)

    agy = find_agy()
    if not agy:
        say("✗ " + EXIT_MSG[7])
        return 7
    if a.check:
        code, msg, _ = check(agy)
        say(("✓ " if code == 0 else "✗ ") + msg + ("" if code == 0 else "\n  → " + EXIT_MSG[code]))
        return code
    if not a.out or not (a.prompt or a.prompt_file):
        say("✗ 要给 --out 和 --prompt / --prompt-file（或者只用 --check）")
        return 2
    try:
        prompt = a.prompt if a.prompt else Path(a.prompt_file).read_text(encoding="utf-8")
    except OSError as e:
        say("✗ 读不到提示词文件：%s" % e)
        return 2
    if not prompt.strip():
        say("✗ 提示词是空的")
        return 2
    out = Path(a.out).expanduser().resolve()
    if out.suffix.lower() not in IMG_EXT:
        say("✗ 输出扩展名要是 .png / .jpg / .jpeg / .webp")
        return 2
    if not a.no_precheck:
        code, msg, _ = check(agy)
        if code != 0:
            say("✗ 开画前检查没过：" + msg + "\n  → " + EXIT_MSG[code])
            return code
    code, msg, info = generate(agy, prompt, out, a.aspect, a.model, a.timeout, a.min_side, a.style)
    if a.log:
        Path(a.log).write_text(json.dumps(info, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if code == 0:
        say("✓ %s ← agy（%s）" % (out, msg))
        print(out)
    else:
        say("✗ %s\n  → %s" % (msg, EXIT_MSG.get(code, EXIT_MSG[1])))
    return code


if __name__ == "__main__":
    sys.exit(main())
