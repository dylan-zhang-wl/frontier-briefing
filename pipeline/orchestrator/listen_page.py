"""试听页：把一期成品（播客、视频、网页截图）做成手机能直接打开的私密页（claude.ai 上的 Artifact）。

用法（在项目根目录）：
    $PY pipeline/orchestrator/listen_page.py build --date 2026-11-03 --out <临时目录>
        → <临时目录>/index.html、files.json（发布路径 → 本机文件，null 表示删掉）、state.next.json
        然后用 Artifact 工具发布：file_path=<临时目录>/index.html，url=试听页地址，files=files.json 的内容
    $PY pipeline/orchestrator/listen_page.py commit --out <临时目录>
        → 发布成功后再记账：state.next.json 变成正式的 state.json
    $PY pipeline/orchestrator/listen_page.py extra add --id music_ab --title … --note … --file "A 版=路径" …
    $PY pipeline/orchestrator/listen_page.py extra remove --id music_ab
        → "待你选"那一栏（小样、对比版）；改完再 build 一次

只用标准库和 ffmpeg/ffprobe。页面只留最近 --keep 天（默认 7），更早的文件在 files.json 里写成 null。
状态放在本机缓存 ~/.cache/frontier-daily/试听页/state.json，不进 iCloud。
"""
import argparse
import html
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CACHE, TESTDIR, read_json, write_json  # noqa: E402

URL = "https://claude.ai/artifact/Fr9YZTJKGfAaDE8GCfRtkR"
STATE = CACHE / "试听页" / "state.json"
WEEK = "一二三四五六日"
SHOT_MAX_H = 4400          # 手机浏览器对超长图片解码有上限，截图切成这么高一段
VIDEO_CRF = 27             # 1280×720 两分多钟约 8 MB


# ---------------------------------------------------------------- 小工具
def probe_seconds(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def probe_size(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    w, h = out.stdout.strip().split(",")[:2]
    return int(w), int(h)


def mmss(sec):
    sec = int(round(sec or 0))
    return f"{sec // 60}:{sec % 60:02d}"


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def first_lines(p, n):
    if not p.exists():
        return []
    lines = [l.strip() for l in p.read_text(encoding="utf-8").splitlines()]
    return [l for l in lines if l and not l.startswith("#")][:n]


# ---------------------------------------------------------------- 一期的资料
def edition_label(d, issue):
    st = read_json(issue / "logs" / "fd_state.json", {}) or {}
    ed = st.get("edition") or st.get("版别")
    names = {"weekday": "工作日版", "saturday_deep": "周六深度版", "sunday_deep": "周日深谈版", "sunday_dialog": "周日对谈版"}
    if ed in names:
        return names[ed]
    return {5: "周六深度版", 6: "周日深谈版"}.get(d.weekday(), "工作日版")


def find_episode(issue):
    cands = sorted(issue.glob("05_配音/*带音效/episode.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


HOT_NAMES = tuple("热点" + n for n in "一二三四五")     # 播客章名：热点有几条就到几（11-03 那期有三条，原来只配了前两条）


def chapter_notes(web, lineup=None):
    """工作日几章的固定名字 → 这一章讲什么（从网页稿取标题；网页头条比播客热点少时，用选题里 hot 的标题补）。周末的章名本身就是说明。"""
    notes = {"开场": "Shirley 打招呼，预告今天几条主线"}
    secs = {s.get("kind"): s.get("items", []) for s in (web or {}).get("sections", [])}
    t = lambda i: (i.get("title_zh") or i.get("title") or "").strip()
    head = [t(i) for i in secs.get("headline", [])]
    hot = [t(i) for i in (lineup or {}).get("hot") or [] if isinstance(i, dict)]
    for n, k in enumerate(HOT_NAMES):
        title = head[n] if n < len(head) else (hot[n] if n < len(hot) else "")
        if title:
            notes[k] = title
    if secs.get("brief"):
        notes["要闻"] = "；".join(t(i) for i in secs["brief"])
    if secs.get("flash"):
        notes["快讯"] = f"{len(secs['flash'])} 条：" + "；".join(t(i) for i in secs["flash"][:3]) + ("……" if len(secs["flash"]) > 3 else "")
    term = ((web or {}).get("daily_card") or {}).get("term") or {}
    if secs.get("term"):
        notes["今日一词"] = t(secs["term"][0]).replace("今日一词：", "")
    elif term.get("zh"):
        notes["今日一词"] = term["zh"]
    if secs.get("teaser"):
        notes["预告观察"] = t(secs["teaser"][0])
    return notes


def gather(day, out):
    """读一期的成品，把要上传的文件做到 out/d/<日期>/ 下。返回 (这一天的记录, {发布路径: 本机文件})。"""
    d = date.fromisoformat(day)
    issue = TESTDIR / day
    if not issue.exists():
        raise SystemExit(f"没有这一期：{issue}")
    dest = out / "d" / day
    dest.mkdir(parents=True, exist_ok=True)
    files, missing = {}, []
    web = read_json(issue / "04_文稿" / "claude_网页.json", {}) or {}

    meta = {"date": day, "weekday": WEEK[d.weekday()], "edition": edition_label(d, issue),
            "headlines": [h.get("zh", "") for h in (web.get("daily_card") or {}).get("headlines", [])]}

    ep = find_episode(issue)
    if ep:
        shutil.copyfile(ep, dest / "podcast.mp3")
        files[f"d/{day}/podcast.mp3"] = str(dest / "podcast.mp3")
        meta["podcast"] = f"d/{day}/podcast.mp3"
        meta["podcast_sec"] = probe_seconds(ep)
        notes = chapter_notes(web, read_json(issue / "02_选题" / "最终选题.json", {}) or {})
        chs = (read_json(ep.parent / "chapters.json", {}) or {}).get("chapters", [])
        meta["chapters"] = [{"t": c.get("startTime", 0), "title": c.get("title", ""),
                             "note": notes.get(c.get("title", ""), "")} for c in chs]
    else:
        missing.append("播客")

    vid = issue / "11_视频v3" / "预览.mp4"
    if vid.exists():
        ffmpeg("-i", str(vid), "-c:v", "libx264", "-crf", str(VIDEO_CRF), "-preset", "slow",
               "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(dest / "video.mp4"))
        files[f"d/{day}/video.mp4"] = str(dest / "video.mp4")
        meta["video"] = f"d/{day}/video.mp4"
        meta["video_sec"] = probe_seconds(vid)
    else:
        missing.append("视频")

    shot = issue / "10_网页v3" / "截图_手机.png"
    if shot.exists():
        w, h = probe_size(shot)
        n = max(1, -(-h // SHOT_MAX_H))
        step = -(-h // n)
        meta["shots"] = []
        for i in range(n):
            y, hh = i * step, min(step, h - i * step)
            name = f"p{i + 1}.jpg"
            ffmpeg("-i", str(shot), "-vf", f"crop={w}:{hh}:0:{y}", "-q:v", "4", str(dest / name))
            files[f"d/{day}/{name}"] = str(dest / name)
            meta["shots"].append({"src": f"d/{day}/{name}", "w": w, "h": hh})
    else:
        missing.append("网页截图")

    items = (read_json(issue / "花费.json", {}) or {}).get("条目") or []
    meta["cost_usd"] = sum(float(x.get("美元", 0) or 0) for x in items) if items else None
    first = first_lines(issue / "审读意见.md", 1)
    if first and first[0].startswith("必须改"):
        meta["review"] = first[0].replace(" ", "")
    meta["report"] = [l.lstrip("-* ").replace("**", "") for l in first_lines(issue / "00_调度报告.md", 3)]
    meta["selfcheck"] = [l.lstrip("-* ").replace("**", "") for l in first_lines(issue / "自检.md", 6)]
    meta["missing"] = missing
    meta["files"] = sorted(files)
    return meta, files


# ---------------------------------------------------------------- 页面
CSS = """
  /* 单栏、手机优先：最新一期在上（播客按章跳听 → 视频 → 网页截图），待你选、往期在下。 */
  :root {
    --bg: #f3f5f7; --surface: #ffffff; --fg: #17212b; --muted: #5b6b7a; --line: #dbe2e8;
    --accent: #1f5f8b; --accent-soft: #e3eef6; --mark: #8a5a00; --mark-soft: #fbf1dc;
    --bad: #a3322a; --bad-soft: #fbe6e3;
    --display: "Noto Serif SC", "Songti SC", "STSong", serif;
    --body: -apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #0f151b; --surface: #17212b; --fg: #e6edf3; --muted: #93a4b4; --line: #2a3742;
      --accent: #7fb6dd; --accent-soft: #1d3446; --mark: #e8b65a; --mark-soft: #3a2e17;
      --bad: #f08a80; --bad-soft: #3d1f1c; color-scheme: dark;
    }
  }
  :root[data-theme="dark"] {
    --bg: #0f151b; --surface: #17212b; --fg: #e6edf3; --muted: #93a4b4; --line: #2a3742;
    --accent: #7fb6dd; --accent-soft: #1d3446; --mark: #e8b65a; --mark-soft: #3a2e17;
    --bad: #f08a80; --bad-soft: #3d1f1c; color-scheme: dark;
  }
  body { background: var(--bg); color: var(--fg); font-family: var(--body); font-size: 16px; line-height: 1.6; }
  .wrap { max-width: 640px; margin: 0 auto; padding-left: max(16px, env(safe-area-inset-left, 0px));
          padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 28px 48px; display: grid; gap: 32px; }
  .issue, section { display: grid; gap: 14px; min-width: 0; }
  header { display: grid; gap: 6px; }
  .eyebrow { font-size: 13px; letter-spacing: .08em; color: var(--accent); }
  h1 { font-family: var(--display); font-weight: 700; font-size: 32px; line-height: 1.2; margin: 0; text-wrap: balance; }
  h2 { font-family: var(--display); font-weight: 500; font-size: 20px; margin: 0; }
  h3 { font-size: 15px; margin: 0; color: var(--muted); font-weight: 600; }
  .meta { color: var(--muted); font-size: 14px; font-variant-numeric: tabular-nums; }
  .heads { margin: 0; padding-left: 1.2em; display: grid; gap: 2px; }
  .note { color: var(--muted); font-size: 14px; margin: 0; }
  audio, video { width: 100%; display: block; border-radius: 10px; }
  video { background: #000; aspect-ratio: 16 / 9; max-width: 100%; }
  .chapters { list-style: none; margin: 0; padding: 0; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
  .chapters li + li { border-top: 1px solid var(--line); }
  .chapters button { all: unset; box-sizing: border-box; width: 100%; cursor: pointer; display: grid;
                     grid-template-columns: 3.4em 1fr; gap: 2px 12px; padding: 11px 14px; align-items: baseline; }
  .chapters button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  .chapters button.on { background: var(--accent-soft); }
  .t { font-variant-numeric: tabular-nums; color: var(--accent); font-size: 14px; }
  .name { font-weight: 600; min-width: 0; }
  .what { grid-column: 2; color: var(--muted); font-size: 14px; min-width: 0; }
  .box { border-radius: 12px; padding: 12px 16px; font-size: 15px; display: grid; gap: 4px; }
  .box ul { margin: 0; padding-left: 1.2em; }
  .ok { background: var(--accent-soft); }
  .warn { background: var(--mark-soft); }
  .bad { background: var(--bad-soft); }
  .box strong { color: var(--accent); }
  .warn strong { color: var(--mark); }
  .bad strong { color: var(--bad); }
  .shots { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; background: var(--surface); }
  .shots img { display: block; width: 100%; height: auto; }
  details { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 12px 16px; }
  details[open] { display: grid; gap: 14px; }
  summary { cursor: pointer; font-weight: 600; }
  summary .meta { font-weight: 400; margin-left: 6px; }
  .extra-item { display: grid; gap: 6px; }
  footer { color: var(--muted); font-size: 13px; }
"""

JS = """
  document.querySelectorAll('.chapters').forEach(function (list) {
    var audio = document.getElementById(list.dataset.audio);
    if (!audio) return;
    var buttons = Array.prototype.slice.call(list.querySelectorAll('button'));
    var starts = buttons.map(function (b) { return parseFloat(b.dataset.t); });
    buttons.forEach(function (b, i) {
      b.addEventListener('click', function () {
        audio.currentTime = starts[i];
        var p = audio.play();
        if (p && p.catch) p.catch(function () {});
      });
    });
    audio.addEventListener('timeupdate', function () {
      var t = audio.currentTime, cur = 0;
      for (var i = 0; i < starts.length; i++) if (t >= starts[i]) cur = i;
      buttons.forEach(function (b, i) { b.classList.toggle('on', i === cur && t > 0); });
    });
  });
  document.querySelectorAll('audio, video').forEach(function (m) {
    m.addEventListener('play', function () {
      document.querySelectorAll('audio, video').forEach(function (o) { if (o !== m) o.pause(); });
    });
  });
"""

e = html.escape


def issue_html(m, latest):
    day = m["date"]
    aid = "a" + day.replace("-", "")
    md = date.fromisoformat(day)
    parts = []
    stats = []
    if m.get("podcast_sec"):
        stats.append(f"播客 {mmss(m['podcast_sec'])}")
    if m.get("video_sec"):
        stats.append(f"视频 {mmss(m['video_sec'])}")
    if m.get("cost_usd") is not None:
        stats.append(f"配音花费 ${m['cost_usd']:.2f}")
    if m.get("review"):
        stats.append(f"审读{m['review']}（配音前已改）")
    title = f"{md.month} 月 {md.day} 日 星期{m['weekday']}"
    if latest:
        parts.append(f'<header><div class="eyebrow">每日 AI 科技前沿简报 · {e(m["edition"])}</div>'
                     f'<h1>{e(title)}</h1><div class="meta">{e(" · ".join(stats))}</div></header>')
    if m.get("headlines"):
        parts.append('<ul class="heads">' + "".join(f"<li>{e(h)}</li>" for h in m["headlines"]) + "</ul>")
    if m.get("missing"):
        parts.append(f'<div class="box bad"><strong>这一期不完整：</strong>少了{e("、".join(m["missing"]))}。'
                     + "".join(f"<div>{e(l)}</div>" for l in m.get("report", [])) + "</div>")
    if m.get("selfcheck"):
        parts.append('<div class="box warn"><strong>自检</strong><ul>'
                     + "".join(f"<li>{e(l)}</li>" for l in m["selfcheck"]) + "</ul></div>")
    if m.get("podcast"):
        parts.append(f'<h2>播客</h2><audio id="{aid}" controls preload="{"metadata" if latest else "none"}" src="{e(m["podcast"])}"></audio>')
        if m.get("chapters"):
            rows = "".join(
                f'<li><button data-t="{c["t"]}"><span class="t">{mmss(c["t"])}</span><span class="name">{e(c["title"])}</span>'
                + (f'<span class="what">{e(c["note"])}</span>' if c.get("note") else "") + "</button></li>"
                for c in m["chapters"])
            parts.append(f'<p class="note">点任一章，从那里开始播放。</p><ul class="chapters" data-audio="{aid}">{rows}</ul>')
    if m.get("video"):
        parts.append(f'<h2>视频</h2><video controls playsinline preload="{"metadata" if latest else "none"}" src="{e(m["video"])}"></video>')
    if m.get("shots"):
        imgs = "".join(f'<img src="{e(s["src"])}" alt="网页截图第 {i + 1} 段" loading="lazy" width="{s["w"]}" height="{s["h"]}">'
                       for i, s in enumerate(m["shots"]))
        parts.append(f'<h2>网页（手机版整页截图）</h2><div class="shots">{imgs}</div>')
    body = "".join(parts)
    if latest:
        return f'<article class="issue">{body}</article>'
    head = f'{md.month} 月 {md.day} 日 星期{m["weekday"]} · {m["edition"]}'
    return f'<details><summary>{e(head)}<span class="meta">{e(" · ".join(stats[:2]))}</span></summary>{body}</details>'


def extras_html(extras):
    if not extras:
        return ""
    out = ['<section><h2>待你选</h2>']
    for x in extras:
        items = []
        for f in x.get("files", []):
            src = e(f["path"])
            if f["path"].endswith((".mp3", ".m4a", ".wav")):
                items.append(f'<div class="extra-item"><h3>{e(f["label"])}</h3><audio controls preload="none" src="{src}"></audio></div>')
            elif f["path"].endswith(".mp4"):
                items.append(f'<div class="extra-item"><h3>{e(f["label"])}</h3><video controls playsinline preload="none" src="{src}"></video></div>')
            else:
                items.append(f'<div class="extra-item"><h3>{e(f["label"])}</h3><img src="{src}" alt="{e(f["label"])}" loading="lazy"></div>')
        out.append(f'<div class="box warn"><strong>{e(x["title"])}</strong><div>{e(x.get("note", ""))}</div></div>' + "".join(items))
    out.append("</section>")
    return "".join(out)


def page(state):
    days = sorted(state.get("days", {}).values(), key=lambda m: m["date"], reverse=True)
    body = []
    if days:
        body.append(issue_html(days[0], True))
    else:
        body.append('<header><div class="eyebrow">每日 AI 科技前沿简报</div><h1>还没有成品</h1></header>')
    body.append(extras_html(state.get("extras", [])))
    if len(days) > 1:
        body.append("<section><h2>往期</h2>" + "".join(issue_html(m, False) for m in days[1:]) + "</section>")
    body.append('<footer>每天早上在 Mac mini 上自动生成，只放在这个私密页，不对外发布。'
                '听完有意见，直接在对话里说哪天、第几分钟、哪里不对。</footer>')
    return ('<title>前沿简报试听台</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@500;700&display=swap">\n'
            f"<style>{CSS}</style>\n<div class=\"wrap\">{''.join(body)}</div>\n<script>{JS}</script>\n")


# ---------------------------------------------------------------- 命令
def load_state():
    return read_json(STATE, {}) or {}


def cmd_build(a):
    out = Path(a.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    state = load_state()
    state.setdefault("days", {})
    drops = state.pop("drop_next", [])                  # 上次撤下的"待你选"文件，发布成功（commit）后才算删掉
    meta, files = gather(a.date, out)
    for p in drops:
        files[p] = None
    state["days"][a.date] = meta
    keep = sorted(state["days"], reverse=True)[:a.keep]
    for d in list(state["days"]):
        if d not in keep:
            for p in state["days"][d].get("files", []):
                files[p] = None
            del state["days"][d]
    for p in a.drop or []:
        files[p] = None
    for x in state.get("extras", []):
        for f in x.get("files", []):
            if f.get("pending"):
                files[f["path"]] = f["src"]
    (out / "index.html").write_text(page(state), encoding="utf-8")
    write_json(out / "files.json", files)
    for x in state.get("extras", []):
        for f in x.get("files", []):
            f.pop("pending", None)
    write_json(out / "state.next.json", state)
    sent = {k: v for k, v in files.items() if v}
    mb = sum(Path(v).stat().st_size for v in sent.values()) / 1e6
    print(f"页面：{out / 'index.html'}")
    print(f"要上传 {len(sent)} 个文件（约 {mb:.1f} MB），要删掉 {len(files) - len(sent)} 个；清单：{out / 'files.json'}")
    print(f"这一期少了：{'、'.join(meta['missing']) or '无'}")
    print(f"发布：Artifact 工具 file_path={out / 'index.html'}，url={URL}，files=files.json 的内容；成功后运行 commit --out {out}")


def cmd_commit(a):
    out = Path(a.out).expanduser().resolve()
    nxt = out / "state.next.json"
    if not nxt.exists():
        raise SystemExit("没有 state.next.json：先 build、发布成功后再 commit")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(nxt, STATE)
    print(f"已记下：{STATE}")


def cmd_extra(a):
    state = load_state()
    extras = [x for x in state.get("extras", []) if x["id"] != a.id]
    if a.action == "add":
        files = []
        for spec in a.file or []:
            label, _, src = spec.partition("=")
            src = Path(src).expanduser().resolve()
            files.append({"label": label, "path": f"x/{a.id}/{src.name}", "src": str(src), "pending": True})
        extras.append({"id": a.id, "title": a.title or a.id, "note": a.note or "", "files": files})
    else:
        old = [x for x in state.get("extras", []) if x["id"] == a.id]
        state.setdefault("drop_next", []).extend(f["path"] for x in old for f in x.get("files", []))
    state["extras"] = extras
    STATE.parent.mkdir(parents=True, exist_ok=True)
    write_json(STATE, state)
    print(f"待你选：{[x['id'] for x in extras]}；下一次 build 时生效")


def main():
    ap = argparse.ArgumentParser(description="试听页")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--date", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--keep", type=int, default=7)
    b.add_argument("--drop", action="append", help="另外要从页面上删掉的发布路径")
    c = sub.add_parser("commit")
    c.add_argument("--out", required=True)
    x = sub.add_parser("extra")
    x.add_argument("action", choices=["add", "remove"])
    x.add_argument("--id", required=True)
    x.add_argument("--title")
    x.add_argument("--note")
    x.add_argument("--file", action="append", help="'标签=本机路径'")
    a = ap.parse_args()
    if a.cmd == "build":
        cmd_build(a)
    elif a.cmd == "commit":
        cmd_commit(a)
    else:
        cmd_extra(a)


if __name__ == "__main__":
    main()
