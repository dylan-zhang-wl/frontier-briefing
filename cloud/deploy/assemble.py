#!/usr/bin/env python3
"""做网站上线包：往期（从往期存档取）＋这一期（这次的成品）＋网页外壳（仓库里现在的模板）→ <上线包>/frontier/…

为什么要每次拼全部往期：Cloudflare 每发布一次就是一个新版本，新版本只有这次上传清单里的文件；
清单里没有的往期文件，新版本里就没有了（https://developers.cloudflare.com/workers/static-assets/direct-upload/ ：
"This manifest is used to track assets associated with each Worker version"）。没变的文件按内容指纹认出来，不会重复上传。

用法（在仓库根目录）：
    python cloud/deploy/assemble.py --archive <往期存档目录> --issue 测试版/2026-11-09 --out <上线包目录>
      --archive   往期存档（里面是 issues/<日期>/…，cloud/deploy/archive.py pull 取下来的）；没有往期时可以不给
      --issue     这一期：期目录（取它的 10_网页v3/issues/<日期>/），可给多次；和往期同一天时用这次的
      --out       上线包目录（必须不存在或是空的）；做好后里面是 frontier/index.html、frontier/issues/…、frontier/past/
      --repo      仓库根（默认本文件往上两层）：网页外壳从 <仓库>/site/v3、site/vendor 取，刊名从 site/tools/v3_site.py 取
      --summary   另写一份给人看的清单（Markdown，Actions 里给 $GITHUB_STEP_SUMMARY）

做法和 site/tools/build_v3.py 第 12 节“写出”一致（往期目录 issues/index.js、首页 index.html、外壳文件），另加三样：
    · 首页和往期页的 robots 标签写成 noindex, nofollow（和 Worker 的响应头一致）；
    · 往期目录页 frontier/past/index.html：日期、版别、标题，最新一期在最前；首页底部加一行“往期目录”链接；
    · 检查：文件数不超过 20,000、单个文件不超过 25 MiB（Workers 免费档上限，
      https://developers.cloudflare.com/workers/platform/limits/ ），网页里不引用外网的脚本和样式。
不调用模型、不联网、不改源目录。退出码：0 成功，1 检查没过，2 参数或输入不对。
"""
import argparse
import html
import importlib.util
import json
import os
import re
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_REPO = HERE.parent.parent
PREFIX = "frontier"
MAX_FILES = 20000
MAX_BYTES = 25 * 1024 * 1024
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHELL = ["app.js", "style.css", "video.css", "video2.css", "video2.js", "video3.css", "video3.js"]   # 同 build_v3.py
VENDOR = ["echarts.min.js", "gsap.min.js"]
THREE = ["three-bundle.min.js", "LICENSE-three.txt", "LICENSE-postprocessing.txt"]
ACCENT_HEX = {"blue": "#0071e3", "amber": "#e08a00", "coral": "#d04a35", "violet": "#7d4fe0"}       # 同 build_v3.py
EDITION = {None: ("工作日版", "Weekday"), "sat": ("周六版", "Saturday deep dive"), "sun": ("周日版", "Sunday conversation")}
WD_ZH = "一二三四五六日"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def read_issue_js(path):
    """issue.js 是 window.FD_ISSUES["日期"] = {...}; 取出那个对象。"""
    t = Path(path).read_text(encoding="utf-8")
    m = re.search(r'window\.FD_ISSUES\[(".*?")\]\s*=\s*', t)
    if not m:
        raise ValueError("%s 不是 build_v3.py 写的格式" % path)
    body = t[m.end():].rstrip().rstrip(";")
    return json.loads(m.group(1)), json.loads(body)


def find_issue_dir(p):
    """--issue 可以给期目录（测试版/日期）、10_网页v3、或直接 issues/日期。返回 (日期, issues/日期 目录)。"""
    p = Path(p).resolve()
    cands = [p]
    if DATE_RE.match(p.name):
        cands += [p / "10_网页v3" / "issues" / p.name]
    for c in cands:
        if DATE_RE.match(c.name) and (c / "issue.js").is_file() and (c / "summary.json").is_file():
            return c.name, c
    if (p / "issues").is_dir():
        ds = [d for d in sorted((p / "issues").iterdir()) if DATE_RE.match(d.name) and (d / "issue.js").is_file()]
        if len(ds) == 1:
            return ds[0].name, ds[0]
    raise ValueError("在 %s 下找不到这一期的 issues/<日期>/issue.js 和 summary.json（第 13 步网页组装没做完？）" % p)


def collect(archive, issues):
    """日期 → 目录。往期在前，这一期覆盖同一天的往期。"""
    got, src = {}, {}
    if archive:
        root = Path(archive) / "issues"
        if root.is_dir():
            for d in sorted(root.iterdir()):
                if DATE_RE.match(d.name) and (d / "issue.js").is_file() and (d / "summary.json").is_file():
                    got[d.name], src[d.name] = d, "往期存档"
    for p in issues or []:
        day, d = find_issue_dir(p)
        got[day], src[day] = d, "这一期" if day not in got else "这一期（替换往期存档里的同一天）"
    return got, src


def copy_tree(src, dst):
    n = 0
    for root, dirs, files in os.walk(src):
        dirs.sort()
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for f in sorted(files):
            if f.startswith(".") or f == "Thumbs.db":
                continue
            shutil.copy2(Path(root) / f, dst / rel / f)
            n += 1
    return n


def zh_date(d):
    dt = date.fromisoformat(d)
    return "%d 年 %d 月 %d 日" % (dt.year, dt.month, dt.day), "星期" + WD_ZH[dt.weekday()]


def entry(day, d):
    s = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    _, iss = read_issue_js(d / "issue.js")
    ed = iss.get("edition")
    zh, en = EDITION.get(ed, EDITION[None])
    return s, iss, {"date": day, "weekday_zh": s.get("weekday_zh"), "weekday_en": s.get("weekday_en"),
                    "lead_zh": s.get("lead_zh", ""), "lead_en": s.get("lead_en", ""), "accent": s.get("accent"),
                    "edition_zh": zh, "edition_en": en}


def render_index(repo, sitecfg, latest_summary):
    """照 build_v3.py：模板里填上最新一期的主题色、字体和刊名；首屏日卡大图预先加载。"""
    tpl = (repo / "site" / "v3" / "index.html").read_text(encoding="utf-8")
    latest = latest_summary
    card = latest.get("card") or {}
    preload = ('<link rel="preload" as="image" href="issues/%s/%s" imagesrcset="issues/%s/%s %dw, issues/%s/%s %dw" '
               'imagesizes="(max-width: 900px) 100vw, 640px" fetchpriority="high">'
               % (latest["date"], card["src"], latest["date"], card["src_sm"], card["w_sm"], latest["date"], card["src"], card["w"])) \
        if card and card.get("src_sm") else ""
    accent = latest.get("accent") or "blue"
    for k, v in {"{{ACCENT}}": accent, "{{ACCENT_HEX}}": ACCENT_HEX.get(accent, ACCENT_HEX["blue"]).replace("#", "%23"),
                 "{{BODY_FONT}}": sitecfg.BODY_FONT, "{{NAME_ZH}}": sitecfg.NAME_ZH, "{{NAME_EN}}": sitecfg.NAME_EN.replace("&", "&amp;"),
                 "{{NAME_EN_SHORT}}": sitecfg.NAME_EN_SHORT, "{{FONT_FACES}}": latest.get("fonts_css", ""), "{{PRELOAD}}": preload}.items():
        tpl = tpl.replace(k, v)
    tpl = re.sub(r'<meta name="robots" content="[^"]*">', '<meta name="robots" content="noindex, nofollow">', tpl)
    if 'name="robots"' not in tpl:
        tpl = tpl.replace("<head>", '<head>\n<meta name="robots" content="noindex, nofollow">', 1)
    link = ('<p class="wrap fd-past" style="text-align:center;font-size:13px;margin:0 auto 44px"><a href="past/" '
            'style="color:var(--ink-3);text-decoration:none;border-bottom:1px solid var(--hair-2)">往期目录 · '
            '<span lang="en">All issues</span></a></p>')
    if '<footer class="foot wrap" id="foot"></footer>' in tpl:
        tpl = tpl.replace('<footer class="foot wrap" id="foot"></footer>', '<footer class="foot wrap" id="foot"></footer>\n' + link, 1)
    else:
        tpl = tpl.replace("</body>", link + "\n</body>", 1)
    return tpl


PAST_CSS = """
:root { --pl-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif;
        --pl-serif: "Songti SC", "Noto Serif SC", "Source Han Serif SC", "STSong", "Times New Roman", serif; }
body { font-family: var(--pl-sans); color: var(--ink); background: var(--bg); margin: 0; }
.pl { padding: 40px 0 64px; max-width: 760px; }
.pl-top { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; font-size: 15px; }
.pl-top a { color: var(--accent); text-decoration: none; }
.pl-top button { font: inherit; color: var(--ink-2); background: var(--chip); border: 1px solid var(--hair); border-radius: 999px; padding: 4px 12px; cursor: pointer; }
.pl h1 { font-family: var(--pl-serif); font-weight: 900; font-size: clamp(30px, 6vw, 44px); line-height: 1.2; margin: 28px 0 6px; letter-spacing: .02em; }
.pl-sub { color: var(--ink-3); margin: 0 0 28px; font-size: 15px; }
.pl-sub span[lang=en] { font-family: "Times New Roman", serif; font-style: italic; }
.pl-month { font-size: 13px; letter-spacing: .08em; color: var(--ink-3); margin: 26px 4px 10px; font-weight: 600; }
.pl-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.pl-item a { display: grid; grid-template-columns: 7.2em 1fr; gap: 4px 16px; padding: 16px 18px; border-radius: 18px; text-decoration: none; color: inherit;
  background: var(--glass); border: 1px solid var(--hair); box-shadow: var(--shadow); -webkit-backdrop-filter: blur(18px) saturate(1.6); backdrop-filter: blur(18px) saturate(1.6);
  transition: transform .2s ease, border-color .2s ease; }
.pl-item a:hover, .pl-item a:focus-visible { transform: translateY(-1px); border-color: var(--accent); outline: none; }
.pl-when { grid-row: span 2; display: flex; flex-direction: column; gap: 2px; }
.pl-when time { font-family: var(--pl-serif); font-weight: 700; font-size: 18px; }
.pl-when small { color: var(--ink-3); font-size: 13px; }
.pl-meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 13px; color: var(--ink-3); }
.pl-ed { padding: 1px 9px; border-radius: 999px; background: var(--chip); color: var(--ink-2); }
.pl-new { padding: 1px 9px; border-radius: 999px; background: var(--accent); color: var(--on-accent); }
.pl-t { font-family: var(--pl-serif); font-size: 18px; line-height: 1.5; font-weight: 700; }
.pl-en { grid-column: 2; color: var(--ink-3); font-size: 14px; font-family: "Times New Roman", serif; font-style: italic; }
.pl-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
.pl-dot.blue { background: #0071e3; } .pl-dot.amber { background: #e08a00; } .pl-dot.coral { background: #d04a35; } .pl-dot.violet { background: #7d4fe0; }
.pl-foot { margin-top: 36px; color: var(--ink-3); font-size: 13px; text-align: center; }
@media (max-width: 560px) { .pl { padding-top: 24px; } .pl-item a { grid-template-columns: 1fr; padding: 14px 16px; } .pl-when { grid-row: auto; flex-direction: row; gap: 8px; align-items: baseline; } .pl-en { grid-column: 1; } }
@media (prefers-reduced-motion: reduce) { .pl-item a { transition: none; } .blob { animation: none !important; } }
"""


def render_past(sitecfg, rows, accent):
    e = html.escape
    by_month = {}
    for r in rows:
        by_month.setdefault(r["date"][:7], []).append(r)
    parts = []
    for i, (m, items) in enumerate(by_month.items()):
        parts.append('<h2 class="pl-month">%d 年 %d 月 <span lang="en">· %s</span></h2>' % (
            int(m[:4]), int(m[5:7]), date.fromisoformat(m + "-01").strftime("%B %Y")))
        parts.append('<ol class="pl-list">')
        for r in items:
            zd, wd = zh_date(r["date"])
            new = '<span class="pl-new">最新</span>' if r is rows[0] else ""
            parts.append(
                '<li class="pl-item"><a href="../?date=%s">'
                '<span class="pl-when"><time datetime="%s">%s</time><small>%s</small></span>'
                '<span class="pl-meta"><i class="pl-dot %s" aria-hidden="true"></i><span class="pl-ed">%s</span>%s</span>'
                '<span class="pl-t">%s</span>%s</a></li>' % (
                    e(r["date"]), e(r["date"]), e(zd.split(" 年 ")[1]), e(wd), e(r.get("accent") or ""), e(r["edition_zh"]), new,
                    e(r["lead_zh"] or "（没有标题）"),
                    ('<span class="pl-en" lang="en">%s</span>' % e(r["lead_en"])) if r.get("lead_en") else ""))
        parts.append("</ol>")
    latest = zh_date(rows[0]["date"])[0] if rows else "—"
    icon = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='14' fill='"
            + ACCENT_HEX.get(accent, ACCENT_HEX["blue"]).replace("#", "%23") + "'/%3E%3C/svg%3E")
    return """<!doctype html>
<html lang="zh-CN" data-accent="%(accent)s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>往期 · %(name_zh)s</title>
<meta name="robots" content="noindex, nofollow">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="%(icon)s">
<link rel="stylesheet" href="../style.css">
<script>
(function () {
  var d = document.documentElement, t = null;
  try { t = new URLSearchParams(location.search).get('theme') || localStorage.getItem('fd3.theme'); } catch (e) {}
  if (t === 'light' || t === 'dark') d.setAttribute('data-theme', t);
})();
</script>
<style>%(css)s</style>
</head>
<body>
<div class="bg" aria-hidden="true"><i class="blob f1"></i><i class="blob f2"></i><i class="blob f3"></i></div>
<main class="wrap pl">
  <div class="pl-top"><a href="../">← 回到最新一期</a><button type="button" id="pl-theme" aria-label="切换深浅色">深浅色</button></div>
  <h1>往期</h1>
  <p class="pl-sub">%(name_zh)s · <span lang="en">%(name_en)s</span><br>共 %(n)d 期，最新一期是 %(latest)s。点一期打开。</p>
  %(body)s
  <p class="pl-foot">本站由 AI 自动化工作流生成，不对搜索引擎开放。</p>
</main>
<script>
(function () {
  var d = document.documentElement, b = document.getElementById('pl-theme');
  var mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  b.addEventListener('click', function () {
    var cur = d.getAttribute('data-theme') || (mq && mq.matches ? 'dark' : 'light');
    var next = cur === 'dark' ? 'light' : 'dark';
    d.setAttribute('data-theme', next);
    try { localStorage.setItem('fd3.theme', next); } catch (e) {}
  });
})();
</script>
</body>
</html>
""" % {"accent": e(accent), "name_zh": e(sitecfg.NAME_ZH), "name_en": e(sitecfg.NAME_EN), "icon": icon, "css": PAST_CSS,
       "n": len(rows), "latest": e(latest), "body": "\n  ".join(parts) or "<p>还没有往期。</p>"}


EXTERNAL = re.compile(r'<(?:script[^>]+src|link[^>]+href)=["\'](?:https?:)?//', re.I)


def check_package(out):
    """上线包检查。返回 (问题列表, 统计)。"""
    out = Path(out)
    problems, n, total, biggest = [], 0, 0, (0, "")
    root = out / PREFIX
    if not (root / "index.html").is_file():
        problems.append("没有 %s/index.html" % PREFIX)
    for p in out.rglob("*"):
        if p.is_file():
            n += 1
            sz = p.stat().st_size
            total += sz
            if sz > biggest[0]:
                biggest = (sz, str(p.relative_to(out)))
            if sz > MAX_BYTES:
                problems.append("%s 有 %.1f MiB，超过单个文件 25 MiB 的上限" % (p.relative_to(out), sz / 1048576))
            if not str(p.relative_to(out)).startswith(PREFIX + "/"):
                problems.append("%s 不在 %s/ 下面（网址对不上）" % (p.relative_to(out), PREFIX))
    if n > MAX_FILES:
        problems.append("一共 %d 个文件，超过 Workers 免费档每个版本 20,000 个的上限" % n)
    for page in (root / "index.html", root / "past" / "index.html"):
        if page.is_file():
            t = page.read_text(encoding="utf-8")
            if EXTERNAL.search(t):
                problems.append("%s 引用了外网的脚本或样式" % page.relative_to(out))
            if not re.search(r'<meta name="robots" content="noindex, nofollow">', t):
                problems.append("%s 没有 noindex, nofollow 标签" % page.relative_to(out))
    return problems, {"文件数": n, "总大小MB": round(total / 1048576, 1), "最大的文件": biggest[1], "最大MB": round(biggest[0] / 1048576, 1)}


def assemble(repo, archive, issues, out):
    repo, out = Path(repo).resolve(), Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("上线包目录 %s 不是空的：换一个新目录（本程序不删文件）" % out)
    got, src = collect(archive, issues)
    if not got:
        raise ValueError("一期都没有：既没有往期存档，也没有给 --issue")
    sitecfg = load_module(repo / "site" / "tools" / "v3_site.py", "v3_site")
    root = out / PREFIX
    (root / "issues").mkdir(parents=True, exist_ok=True)
    rows, summaries, site = [], {}, None
    for day in sorted(got):
        n = copy_tree(got[day], root / "issues" / day)
        s, iss, row = entry(day, got[day])
        row["_files"], row["_from"] = n, src[day]
        rows.append(row)
        summaries[day] = s
        site = iss.get("site") or site
    latest = max(got)
    keep = ("date", "weekday_zh", "weekday_en", "lead_zh", "lead_en", "accent", "edition_zh", "edition_en")
    with open(root / "issues" / "index.js", "w", encoding="utf-8") as f:
        f.write("/* 往期目录与全站设置：由 cloud/deploy/assemble.py 按 issues/日期/summary.json 生成（格式同 build_v3.py，多了 edition_zh/en） */\n")
        f.write("window.FD_INDEX = %s;\n" % json.dumps({
            "latest": latest, "issues": [{k: r[k] for k in keep} for r in rows],
            "site": site or {"name_zh": sitecfg.NAME_ZH, "name_en": sitecfg.NAME_EN, "name_en_short": sitecfg.NAME_EN_SHORT}},
            ensure_ascii=False))
    (root / "index.html").write_text(render_index(repo, sitecfg, summaries[latest]), encoding="utf-8")
    for f in SHELL:
        shutil.copy2(repo / "site" / "v3" / f, root / f)
    shutil.copy2(repo / "site" / "video.js", root / "video.js")
    (root / "vendor").mkdir(exist_ok=True)
    for f in VENDOR:
        shutil.copy2(repo / "site" / "vendor" / f, root / "vendor" / f)
    if (repo / "site" / "vendor" / "three").is_dir():
        (root / "vendor" / "three").mkdir(exist_ok=True)
        for f in THREE:
            if (repo / "site" / "vendor" / "three" / f).is_file():
                shutil.copy2(repo / "site" / "vendor" / "three" / f, root / "vendor" / "three" / f)
    (root / "past").mkdir(exist_ok=True)
    newest_first = sorted(rows, key=lambda r: r["date"], reverse=True)
    (root / "past" / "index.html").write_text(render_past(sitecfg, newest_first, summaries[latest].get("accent") or "blue"),
                                              encoding="utf-8")
    problems, stats = check_package(out)
    return newest_first, problems, stats


def main(argv=None):
    ap = argparse.ArgumentParser(description="做网站上线包（往期＋这一期＋外壳）")
    ap.add_argument("--archive", help="往期存档目录（里面是 issues/<日期>/）")
    ap.add_argument("--issue", action="append", default=[], help="这一期的期目录，可给多次")
    ap.add_argument("--out", required=True, help="上线包目录（不存在或空）")
    ap.add_argument("--repo", default=str(DEFAULT_REPO), help="仓库根（默认本文件往上两层）")
    ap.add_argument("--summary", help="另写一份给人看的清单（Markdown，追加）")
    a = ap.parse_args(argv)
    try:
        rows, problems, stats = assemble(a.repo, a.archive, a.issue, a.out)
    except (ValueError, OSError) as e:
        print("✗ " + str(e), file=sys.stderr)
        return 2
    lines = ["### 网站上线包（%s）" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "",
             "一共 %d 期，最新 %s；%d 个文件，%.1f MB（最大的 %s，%.1f MB）。" % (
                 len(rows), rows[0]["date"], stats["文件数"], stats["总大小MB"], stats["最大的文件"], stats["最大MB"]), "",
             "| 日期 | 版别 | 标题 | 文件数 | 从哪来 |", "|---|---|---|---|---|"]
    lines += ["| %s | %s | %s | %d | %s |" % (r["date"], r["edition_zh"], r["lead_zh"].replace("|", "／"), r["_files"], r["_from"]) for r in rows]
    lines += [""] + (["**检查没过**："] + ["- " + p for p in problems] if problems else ["检查通过：文件数、单个文件大小、不引用外网、noindex 标签。"])
    text = "\n".join(lines) + "\n"
    print(text)
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write(text)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
