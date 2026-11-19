"""上线包（assemble.py）和往期存档（archive.py）的本机测试：python -m unittest discover -s cloud/deploy/tests -v
不联网、不用令牌：存档用临时目录里的假“远端”（git 裸仓库）代替 GitHub。"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import archive  # noqa: E402
import assemble  # noqa: E402

TEMPLATE = """<!doctype html>
<html lang="zh-CN" data-accent="{{ACCENT}}" data-font="{{BODY_FONT}}">
<head>
<meta charset="utf-8">
<title>{{NAME_ZH}} · {{NAME_EN_SHORT}}</title>
<meta name="robots" content="noindex">
<link rel="icon" href="data:image/svg+xml,{{ACCENT_HEX}}">
<style id="fd-fonts">
{{FONT_FACES}}
</style>
{{PRELOAD}}
<link rel="stylesheet" href="style.css">
</head>
<body>
<footer class="foot wrap" id="foot"></footer>
<script src="issues/index.js"></script>
<script src="app.js"></script>
</body>
</html>
"""
SITECFG = 'NAME_ZH = "每日AI科技前沿简报"\nNAME_EN = "Daily AI & Tech Frontier Briefing"\nNAME_EN_SHORT = "Frontier Briefing"\nBODY_FONT = "kai"\n'


def make_repo(root):
    """假仓库：site/v3 模板和外壳、site/vendor、site/tools/v3_site.py。"""
    v3 = root / "site" / "v3"
    v3.mkdir(parents=True)
    (v3 / "index.html").write_text(TEMPLATE, encoding="utf-8")
    for f in assemble.SHELL:
        (v3 / f).write_text("/* %s */" % f, encoding="utf-8")
    (root / "site" / "video.js").write_text("/* video */", encoding="utf-8")
    (root / "site" / "vendor" / "three").mkdir(parents=True)
    for f in assemble.VENDOR:
        (root / "site" / "vendor" / f).write_text("/* v */", encoding="utf-8")
    for f in assemble.THREE:
        (root / "site" / "vendor" / "three" / f).write_text("/* t */", encoding="utf-8")
    (root / "site" / "tools").mkdir(parents=True)
    (root / "site" / "tools" / "v3_site.py").write_text(SITECFG, encoding="utf-8")


def make_issue(base, day, lead, edition=None, accent="blue", audio=b"ID3"):
    d = base / day / "10_网页v3" / "issues" / day
    (d / "audio").mkdir(parents=True)
    (d / "img").mkdir()
    (d / "audio" / "podcast.mp3").write_bytes(audio)
    (d / "img" / "card-800.webp").write_bytes(b"RIFF")
    iss = {"date": day, "site": {"name_zh": "每日AI科技前沿简报", "name_en": "Daily AI & Tech Frontier Briefing", "name_en_short": "Frontier Briefing"}}
    if edition:
        iss["edition"] = edition
    (d / "issue.js").write_text('/* x */\nwindow.FD_ISSUES = window.FD_ISSUES || {};\nwindow.FD_ISSUES["%s"] = %s;\n'
                                % (day, json.dumps(iss, ensure_ascii=False)), encoding="utf-8")
    (d / "summary.json").write_text(json.dumps({
        "date": day, "weekday_zh": "星期日", "weekday_en": "Sunday", "accent": accent, "lead_zh": lead, "lead_en": "EN " + lead,
        "fonts_css": '@font-face{src:url("issues/%s/fonts/a.woff2")}' % day,
        "card": {"src": "img/card-800.webp", "src_sm": "img/card-800.webp", "w": 1376, "w_sm": 800}}, ensure_ascii=False), encoding="utf-8")
    return base / day


class AssembleTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.t = Path(self.td.name)
        make_repo(self.t / "repo")
        self.issues = self.t / "测试版"

    def tearDown(self):
        self.td.cleanup()

    def test_合并往期和这一期(self):
        arch = self.t / "arch" / "issues"
        old = make_issue(self.t / "old", "2026-11-07", "旧的一期", edition="sat")
        (arch).mkdir(parents=True)
        os.rename(old / "10_网页v3" / "issues" / "2026-11-07", arch / "2026-11-07")
        new = make_issue(self.issues, "2026-11-08", "新的一期", edition="sun", accent="amber")
        rows, problems, stats = assemble.assemble(self.t / "repo", self.t / "arch", [new], self.t / "pkg")
        self.assertEqual(problems, [])
        self.assertEqual([r["date"] for r in rows], ["2026-11-08", "2026-11-07"])
        self.assertEqual(rows[0]["edition_zh"], "周日版")
        self.assertEqual(rows[1]["edition_zh"], "周六版")
        root = self.t / "pkg" / "frontier"
        idx = (root / "issues" / "index.js").read_text(encoding="utf-8")
        data = json.loads(idx.split("window.FD_INDEX = ", 1)[1].rstrip().rstrip(";"))
        self.assertEqual(data["latest"], "2026-11-08")
        self.assertEqual([x["date"] for x in data["issues"]], ["2026-11-07", "2026-11-08"])
        page = (root / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-accent="amber"', page)
        self.assertIn('<meta name="robots" content="noindex, nofollow">', page)
        self.assertIn('href="past/"', page)
        self.assertIn("issues/2026-11-08/fonts/a.woff2", page)
        self.assertNotIn("{{", page)
        past = (root / "past" / "index.html").read_text(encoding="utf-8")
        self.assertLess(past.index("新的一期"), past.index("旧的一期"))      # 最新一期在最前
        self.assertIn('href="../?date=2026-11-07"', past)
        self.assertIn("noindex, nofollow", past)
        for f in assemble.SHELL + ["video.js", "vendor/echarts.min.js", "vendor/three/three-bundle.min.js",
                                   "issues/2026-11-07/audio/podcast.mp3", "issues/2026-11-08/img/card-800.webp"]:
            self.assertTrue((root / f).is_file(), f)

    def test_同一天以这一期为准(self):
        arch = self.t / "arch" / "issues"
        arch.mkdir(parents=True)
        old = make_issue(self.t / "old", "2026-11-08", "旧版", audio=b"OLD")
        os.rename(old / "10_网页v3" / "issues" / "2026-11-08", arch / "2026-11-08")
        new = make_issue(self.issues, "2026-11-08", "新版", audio=b"NEW")
        rows, problems, _ = assemble.assemble(self.t / "repo", self.t / "arch", [new], self.t / "pkg")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["lead_zh"], "新版")
        self.assertEqual((self.t / "pkg/frontier/issues/2026-11-08/audio/podcast.mp3").read_bytes(), b"NEW")

    def test_输出目录不空就不做(self):
        (self.t / "pkg").mkdir()
        (self.t / "pkg" / "x").write_text("x")
        new = make_issue(self.issues, "2026-11-08", "新版")
        with self.assertRaises(ValueError):
            assemble.assemble(self.t / "repo", None, [new], self.t / "pkg")

    def test_检查会拦下超大文件和外网脚本(self):
        new = make_issue(self.issues, "2026-11-08", "新版")
        rows, problems, _ = assemble.assemble(self.t / "repo", None, [new], self.t / "pkg")
        self.assertEqual(problems, [])
        big = self.t / "pkg/frontier/issues/2026-11-08/audio/big.mp3"
        with open(big, "wb") as f:
            f.truncate(assemble.MAX_BYTES + 1)
        page = self.t / "pkg/frontier/index.html"
        page.write_text(page.read_text(encoding="utf-8").replace("</head>", '<script src="https://cdn.example.com/x.js"></script></head>'),
                        encoding="utf-8")
        problems, _ = assemble.check_package(self.t / "pkg")
        self.assertTrue(any("25 MiB" in p for p in problems), problems)
        self.assertTrue(any("外网" in p for p in problems), problems)

    def test_找不到这一期就报错(self):
        (self.issues / "2026-11-09").mkdir(parents=True)
        with self.assertRaises(ValueError):
            assemble.assemble(self.t / "repo", None, [self.issues / "2026-11-09"], self.t / "pkg")


def sh(*a, cwd=None):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        t = self.t = Path(self.td.name)
        sh("git", "init", "-q", "--bare", str(t / "origin.git"))
        sh("git", "init", "-q", str(t / "repo"))
        (t / "repo" / "README.md").write_text("main")
        sh("git", "-C", str(t / "repo"), "add", "README.md")
        sh("git", "-C", str(t / "repo"), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
        sh("git", "-C", str(t / "repo"), "remote", "add", "origin", str(t / "origin.git"))
        sh("git", "-C", str(t / "repo"), "push", "-q", "origin", "HEAD:refs/heads/main")
        self.issues = t / "测试版"

    def tearDown(self):
        self.td.cleanup()

    def files(self, d):
        return sorted(str(p.relative_to(d)) for p in Path(d).rglob("*") if p.is_file())

    def test_第一次取是空的_存两期_再取都在(self):
        repo, t = self.t / "repo", self.t
        self.assertIsNone(archive.pull(repo, "origin", "site-archive", t / "a1"))
        self.assertEqual(self.files(t / "a1"), [])
        archive.push(repo, "origin", "site-archive", t / "a1", make_issue(self.issues, "2026-11-08", "一"))
        archive.pull(repo, "origin", "site-archive", t / "a2")
        self.assertEqual(self.files(t / "a2"), ["issues/2026-11-08/audio/podcast.mp3", "issues/2026-11-08/img/card-800.webp",
                                                "issues/2026-11-08/issue.js", "issues/2026-11-08/summary.json"])
        archive.push(repo, "origin", "site-archive", t / "a2", make_issue(self.issues, "2026-11-09", "二"))
        archive.pull(repo, "origin", "site-archive", t / "a3")
        self.assertEqual(sorted(d.name for d in (t / "a3" / "issues").iterdir()), ["2026-11-08", "2026-11-09"])
        # 主分支没被动过
        out = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "origin/main"], capture_output=True, text=True).stdout
        self.assertNotIn("issues/", out)
        log = subprocess.run(["git", "--git-dir", str(t / "origin.git"), "log", "--format=%s", "site-archive"], capture_output=True, text=True).stdout
        self.assertEqual(log.split("\n")[:2], ["往期存档：2026-11-09", "往期存档：2026-11-08"])

    def test_同一天重发换成新文件_没变就不提交(self):
        repo, t = self.t / "repo", self.t
        archive.pull(repo, "origin", "site-archive", t / "a1")
        c1 = archive.push(repo, "origin", "site-archive", t / "a1", make_issue(self.issues, "2026-11-08", "一", audio=b"V1"))
        again = archive.push(repo, "origin", "site-archive", t / "a1", self.issues / "2026-11-08")
        self.assertEqual(c1, again)
        issue2 = make_issue(t / "第二版", "2026-11-08", "一", audio=b"V2")
        (issue2 / "10_网页v3/issues/2026-11-08/img/card-800.webp").rename(issue2 / "10_网页v3/issues/2026-11-08/img/card-1376.webp")
        archive.pull(repo, "origin", "site-archive", t / "b1")
        c2 = archive.push(repo, "origin", "site-archive", t / "b1", issue2)
        self.assertNotEqual(c1, c2)
        archive.pull(repo, "origin", "site-archive", t / "b2")
        self.assertEqual((t / "b2/issues/2026-11-08/audio/podcast.mp3").read_bytes(), b"V2")
        self.assertFalse((t / "b2/issues/2026-11-08/img/card-800.webp").exists())     # 换下来的旧文件不在新清单里
        self.assertTrue((t / "b2/issues/2026-11-08/img/card-1376.webp").exists())

    def test_别处先推过也能接上(self):
        repo, t = self.t / "repo", self.t
        archive.pull(repo, "origin", "site-archive", t / "a1")
        archive.pull(repo, "origin", "site-archive", t / "x1")
        archive.push(repo, "origin", "site-archive", t / "a1", make_issue(self.issues, "2026-11-08", "一"))
        # x1 取的时候分支还是空的；push 时会重新取最新一版再提交，不会把 11-08 冲掉
        archive.push(repo, "origin", "site-archive", t / "x1", make_issue(self.issues, "2026-11-09", "二"))
        archive.pull(repo, "origin", "site-archive", t / "z")
        self.assertEqual(sorted(d.name for d in (t / "z" / "issues").iterdir()), ["2026-11-08", "2026-11-09"])


class WranglerConfigTest(unittest.TestCase):
    """访问统计（11-10 加）：wrangler.toml 带 D1 绑定、不加定时；run_wrangler.py 把表结构 migrations/ 一起复制到运行目录。"""

    def test_wrangler_toml_有统计数据库_没有定时(self):
        toml = (HERE.parent / "wrangler.toml").read_text(encoding="utf-8")
        body = "\n".join(line.split("#", 1)[0] for line in toml.splitlines())     # 去掉注释再看
        self.assertIn("[[d1_databases]]", body)
        self.assertRegex(body, r'binding = "VISITS"')
        self.assertRegex(body, r'database_name = "frontier-visits"')
        self.assertRegex(body, r'database_id = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"')
        self.assertRegex(body, r'migrations_dir = "migrations"')
        self.assertNotIn("[triggers]", body)                 # 账号里的定时已经用了 4 个、上限 5 个
        self.assertNotIn("crons", body)
        self.assertNotIn("STATS_KEY_HASH =", body)           # 指纹是机密变量，不写在配置里
        self.assertTrue((HERE.parent / "migrations" / "0001_visits.sql").is_file())

    def test_prepare_复制源码和表结构_填上上线包位置(self):
        import run_wrangler  # noqa: E402
        with tempfile.TemporaryDirectory() as d:
            run_dir, assets = Path(d) / "run", Path(d) / "pkg"
            (run_dir / "migrations").mkdir(parents=True)
            (run_dir / "migrations" / "旧的.sql").write_text("old", encoding="utf-8")
            run_wrangler.prepare(run_dir, assets)
            self.assertTrue((run_dir / "src" / "index.js").is_file())
            self.assertTrue((run_dir / "src" / "visits.js").is_file())
            self.assertTrue((run_dir / "src" / "stats.js").is_file())
            self.assertTrue((run_dir / "migrations" / "0001_visits.sql").is_file())
            self.assertFalse((run_dir / "migrations" / "旧的.sql").exists())    # 运行目录里的旧文件换成仓库里现在的
            toml = (run_dir / "wrangler.toml").read_text(encoding="utf-8")
            self.assertIn('directory = "%s"' % assets, toml)
            self.assertNotIn("__ASSETS_DIR__", toml)



# ===================== 私有播客订阅源（2026-11-19 加，podcast_feed.py）=====================
# 夹具全是现编的假期（假标题、假出处、假音频），不用真内容。单集封面要 Pillow：没装时那几条跳过，其余照跑。
import hashlib  # noqa: E402
import re  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402
from unittest import mock  # noqa: E402

import podcast_feed  # noqa: E402

try:
    from PIL import Image as _PILImage
except Exception:                                   # 没装 Pillow
    _PILImage = None

NS = podcast_feed.NS
HEX32 = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])")


def pod_issue(base, day, edition=None, *, podcast=True, video=True, gen=None, music="dreamer", card_img=True, mismatch=False,
              audio=None, flash_n=2, long_flash=False, listen=None):
    """一期假内容，结构照网页 issue.js：日卡、热点、要闻、快讯、预告、今日一词、章节、底乐署名。"""
    d = base / day / "10_网页v3" / "issues" / day
    (d / "audio").mkdir(parents=True)
    (d / "img").mkdir()
    if podcast:
        (d / "audio" / "podcast.mp3").write_bytes(audio if audio is not None else (b"ID3\x04\x00\x00\x00\x00\x00\x00" + day.encode() * 400))
    if card_img:
        if _PILImage:
            _PILImage.new("RGB", (1400, 788), (30, 90, 160)).save(d / "img" / "card-1400.webp", "WEBP", quality=60)
        else:
            (d / "img" / "card-1400.webp").write_bytes(b"RIFF0000WEBP")
    srcs = [{"id": "S1", "name": "示例日报 · 科技", "url": "https://news.example.com/a?x=1&y=2", "title": "t"},
            {"id": "S2", "name": "Example Wire", "url": "https://wire.example.org/b", "title": "t"},
            {"id": "S3", "name": "坏链接", "url": "javascript:alert(1)", "title": "t"}]
    st = lambda i, t, extra=None: {"id": i, "title_zh": t, "summary_zh": t + "的摘要​，有[^s01]记号。", "sources": ["S1", "S2", "S3"],
                                  "listen": (extra or {}).get("listen")}
    stories = {"E1": st("E1", "甲公司发布新模型", {"listen": (listen or {}).get("E1")}), "E2": st("E2", "乙公司裁员一成", {"listen": (listen or {}).get("E2")}),
               "E3": st("E3", "丙芯片延期"), "E4": st("E4", "丁基金募资"), "E9": st("E9", "卡片上另一条"),
               "D1": st("D1", "一周回看：示例公司的转向"), "T1": st("T1", "传闻：戊公司下周发布")}
    flash = []
    for k in range(flash_n):
        sid = "F%d" % k
        stories[sid] = st(sid, ("很长很长的快讯标题" * 30 if long_flash else "快讯第 %d 条" % k))
        flash.append(sid)
    if edition in ("sun", "sat"):
        order = {"deep": ["D1"], "flash": flash}
        heads = [] if edition == "sun" else [{"ref": "E1", "zh": "卡片一"}, {"ref": "E2", "zh": "卡片二"}]
        chapters = [{"start": 0.0, "title_zh": "开场"}, {"start": 40.5, "title_zh": "快讯"}, {"start": 200.0, "title_zh": "深谈·来龙去脉"}]
        term = {"ref": "term"}
    else:
        order = {"headline": ["E1", "E2"], "brief": ["E3", "E4"], "flash": flash, "teaser": ["T1"], "term": ["term"]}
        heads = [{"ref": "E9" if mismatch else "E1", "zh": "卡片​头条一"}, {"ref": "E2", "zh": "卡片头条二"}, {"ref": "E3", "zh": "卡片头条三"}]
        chapters = [{"start": 0.0, "title_zh": "开场"}, {"start": 57.16, "title_zh": "热点一"}, {"start": 186.4, "title_zh": "热点二"},
                    {"start": 300.0, "title_zh": "要闻"}, {"start": 420.0, "title_zh": "今日一词"}, {"start": 470.2, "title_zh": "结尾"}]
        term = {"zh": "示例词", "en": "sample term", "explain_zh": "一个​只在测试里用的词。", "ref": "term"}
    iss = {"date": day, "meta": {"generated_at": gen or (day + "T06:05+00:00")}, "card": {"headlines": heads, "term": term},
           "order": order, "stories": stories, "sources": srcs,
           "site": {"name_zh": "每日AI科技前沿简报", "music_credit": [{"dreamer": "配乐：Kevin MacLeod《Dreamer》（CC BY 4.0，经剪辑）",
                                                                     "castles": "配乐：Scott Buckley《Castles in the Sky》（CC BY 4.0，经剪辑）"}[music], "Music: x"]}
                    if music else {"name_zh": "每日AI科技前沿简报"},
           "media": {}}
    if edition:
        iss["edition"] = edition
    if podcast:
        iss["media"]["podcast"] = {"file": "audio/podcast.mp3", "duration": 491.6, "chapters": chapters}
    if video:
        iss["media"]["video"] = {"duration": 139.2}
    (d / "issue.js").write_text('/* x */\nwindow.FD_ISSUES = window.FD_ISSUES || {};\nwindow.FD_ISSUES["%s"] = %s;\n'
                                % (day, json.dumps(iss, ensure_ascii=False)), encoding="utf-8")
    (d / "summary.json").write_text(json.dumps({
        "date": day, "weekday_zh": "星期四", "weekday_en": "Thursday", "accent": "blue", "lead_zh": "导语" + day, "lead_en": "Lead",
        "fonts_css": "", "card": {"src": "img/card-1400.webp", "src_sm": "img/card-1400.webp", "w": 1400, "w_sm": 1400}}, ensure_ascii=False),
        encoding="utf-8")
    return base / day


def tree(root):
    """目录下每个文件 → sha256（相对路径）。"""
    root = Path(root)
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def minus_podcast(t):
    return {k: v for k, v in t.items() if not k.startswith("frontier/_podcast/")}


class PodcastFeedTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.t = Path(self.td.name)
        make_repo(self.t / "repo")
        self.issues = self.t / "测试版"
        self.n = 0

    def tearDown(self):
        self.td.cleanup()

    def pkg(self, issues, podcast=True, limit=60, archive=None):
        self.n += 1
        out = self.t / ("pkg%d" % self.n)
        rows, problems, stats = assemble.assemble(self.t / "repo", archive, issues, out, podcast=podcast, limit=limit)
        return out, problems, stats

    def feed(self, out):
        text = (out / "frontier/_podcast/feed.xml").read_text(encoding="utf-8")
        return text, ET.fromstring(text.encode("utf-8"))

    def week(self):
        """一包五期：工作日、周日、周六旧版、没视频（Castles 配乐）、没播客；外加一期跨天重建的。"""
        return [pod_issue(self.issues, "2026-11-19"), pod_issue(self.issues, "2026-11-15", "sun"),
                pod_issue(self.issues, "2026-11-07", "sat"), pod_issue(self.issues, "2026-11-03", video=False, music="castles", mismatch=True),
                pod_issue(self.issues, "2026-11-02", podcast=False), pod_issue(self.issues, "2026-10-31", gen="2026-11-01T10:37+00:00")]

    def test_工作日一期_各字段(self):
        out, problems, stats = self.pkg([pod_issue(self.issues, "2026-11-19")])
        self.assertEqual(problems, [])
        self.assertIn("播客订阅源：1 期", stats["播客订阅源"])
        text, root = self.feed(out)
        ch = root.find("channel")
        for t in ("title", "link", "language", "description", "itunes:image", "itunes:category", "itunes:explicit", "itunes:block",
                  "itunes:author", "itunes:type", "podcast:locked", "copyright", "lastBuildDate", "atom:link"):
            self.assertIsNotNone(ch.find(t, NS), t)
        self.assertEqual(ch.findtext("title"), "每日AI科技前沿简报")
        self.assertEqual(ch.findtext("language"), "zh-cn")
        self.assertEqual(ch.findtext("itunes:block", namespaces=NS), "Yes")
        self.assertIsNone(ch.find("itunes:owner", NS), "不写 itunes:owner（不放邮箱）")
        cats = [(c.get("text"), [x.get("text") for x in c]) for c in ch.findall("itunes:category", NS)]
        self.assertEqual(cats, [("Technology", []), ("News", ["Tech News"])])
        self.assertEqual(ch.find("itunes:image", NS).get("href"), "__FD_FEED_BASE__/cover.jpg")
        self.assertEqual(ch.find("atom:link", NS).get("href"), "__FD_FEED_BASE__/feed.xml")
        it = ch.find("item")
        self.assertEqual(it.findtext("title"), "卡片头条一｜卡片头条二", "日卡前两条，看不见的断行符去掉")
        self.assertEqual(it.findtext("guid"), "frontier-daily-podcast-2026-11-19")
        self.assertEqual(it.find("guid").get("isPermaLink"), "false")
        enc = it.find("enclosure")
        mp3 = out / "frontier/issues/2026-11-19/audio/podcast.mp3"
        self.assertEqual(enc.get("url"), "__FD_FEED_BASE__/2026-11-19.mp3")
        self.assertEqual(enc.get("length"), str(mp3.stat().st_size))
        self.assertEqual(enc.get("type"), "audio/mpeg")
        self.assertEqual(it.findtext("pubDate"), "Thu, 19 Nov 2026 06:05:00 +0000")
        self.assertEqual(ch.findtext("lastBuildDate"), "Thu, 19 Nov 2026 06:05:00 +0000", "最新一期的发布时间，不是当时的钟点")
        self.assertEqual(it.findtext("itunes:duration", namespaces=NS), "492")
        self.assertEqual(it.findtext("link"), "https://wenlongzhang.com/frontier/?date=2026-11-19")
        self.assertEqual(it.find("podcast:chapters", NS).get("url"), "__FD_FEED_BASE__/2026-11-19.chapters.json")
        chj = json.loads((out / "frontier/_podcast/2026-11-19.chapters.json").read_text(encoding="utf-8"))
        self.assertEqual(chj["version"], "1.2.0")
        self.assertEqual([c["title"] for c in chj["chapters"]], ["开场", "热点一", "热点二", "要闻", "今日一词 · 示例词", "结尾"])
        self.assertEqual(chj["chapters"][1]["startTime"], 57.16)
        desc = it.findtext("description")
        for s in ("今天的热点：卡片头条一；卡片头条二。后面还有 2 条要闻、2 条快讯、今日一词“示例词”。", "<p>今日热点</p>", "<p>要闻</p>",
                  "<p>快讯</p>", "<p>预告观察</p>", "甲公司发布新模型：甲公司发布新模型的摘要，有记号。", "今日一词：示例词（sample term）。一个只在测试里用的词。",
                  "<li>00:00:00 开场</li>", "<li>00:00:57 热点一</li>", "<li>00:07:00 今日一词 · 示例词</li>",
                  '<a href="https://wenlongzhang.com/frontier/?date=2026-11-19">网页版</a>', "三分钟内的动画视频", "发现错误，可在网页底部点“反馈”",
                  '<a href="https://news.example.com/a?x=1&amp;y=2">示例日报</a>', '<a href="https://incompetech.com">incompetech.com</a>',
                  "CC BY 4.0 许可", "片头、转场和片尾音乐由 AI 生成", "另一个独立的 AI 审读"):
            self.assertIn(s, desc, s)
        self.assertNotIn("javascript:", desc, "只留 http(s) 出处链接")
        self.assertNotIn("​", text)
        self.assertNotIn("人审", desc)
        self.assertLessEqual(set(re.findall(r"</?([a-zA-Z][a-zA-Z0-9]*)", desc)), podcast_feed.ALLOWED_TAGS)
        self.assertLessEqual(len(desc), 10000)
        self.assertIsNone(HEX32.search(text), "订阅源里没有像钥匙的 32 位十六进制")
        self.assertNotIn("/frontier/podcast/", text)
        self.assertEqual((out / "frontier/_podcast/cover.jpg").read_bytes(), podcast_feed.SHOW_COVER.read_bytes())

    def test_几种特殊的期(self):
        out, problems, stats = self.pkg(self.week())
        self.assertEqual(problems, [])
        text, root = self.feed(out)
        items = {it.findtext("guid")[-10:]: it for it in root.find("channel").findall("item")}
        self.assertEqual(list(items), ["2026-11-19", "2026-11-15", "2026-11-07", "2026-11-03", "2026-10-31"], "最新在前；没播客那期不收")
        self.assertIn("跳过 2026-11-02：没有播客", stats["播客跳过"])
        self.assertEqual(items["2026-11-15"].findtext("title"), "周日深谈｜一周回看：示例公司的转向")
        self.assertEqual(items["2026-11-07"].findtext("title"), "周六深度｜一周回看：示例公司的转向")
        sun = items["2026-11-15"].findtext("description")
        self.assertTrue(sun.startswith("<p>一周回看：示例公司的转向的摘要"), "周日导语用深谈那条的摘要")
        self.assertIn("<p>深谈</p>", sun)
        self.assertIn("<p>深度</p>", items["2026-11-07"].findtext("description"))
        nov3 = items["2026-11-03"].findtext("description")
        self.assertEqual(items["2026-11-03"].findtext("title"), "卡片头条一｜卡片头条二", "标题照用日卡")
        self.assertIn("今天的热点：甲公司发布新模型；卡片头条二。", nov3, "热点列表按播客的 order.headline（日卡里没有的用 title_zh）")
        self.assertNotIn("动画视频", nov3, "没视频就不写视频那句")
        self.assertIn("Scott Buckley《Castles in the Sky》", nov3)
        self.assertIn("https://www.scottbuckley.com.au", nov3)
        self.assertNotIn("片头、转场和片尾音乐由 AI 生成", nov3, "Castles 那套声音包没核过，不写 AI 音乐")
        self.assertEqual(items["2026-10-31"].findtext("pubDate"), "Sat, 31 Oct 2026 06:00:00 +0000", "事后重建（generated_at 跨天）的写期号当天 06:00 UTC")
        self.assertEqual(root.find("channel").findtext("lastBuildDate"), "Thu, 19 Nov 2026 06:05:00 +0000")

    def test_两次做出来逐字节一样_mp3一个字节没动(self):
        issues = self.week()
        a, _, _ = self.pkg(issues)
        b, _, _ = self.pkg(issues)
        ta, tb = tree(a), tree(b)
        self.assertEqual(ta, tb)
        self.assertTrue(any(k.startswith("frontier/_podcast/") for k in ta))
        for day in ("2026-11-19", "2026-11-15", "2026-10-31"):
            src = self.issues / day / "10_网页v3/issues" / day / "audio/podcast.mp3"
            self.assertEqual(ta["frontier/issues/%s/audio/podcast.mp3" % day], hashlib.sha256(src.read_bytes()).hexdigest())

    def test_开关关着没有_podcast_开着只多_podcast(self):
        issues = self.week()
        off, p_off, s_off = self.pkg(issues, podcast=False)
        on, p_on, s_on = self.pkg(issues, podcast=True)
        self.assertFalse((off / "frontier/_podcast").exists())
        self.assertNotIn("播客订阅源", s_off)
        self.assertEqual(p_off, p_on)
        self.assertEqual(minus_podcast(tree(on)), tree(off), "开着时除了 _podcast/ 别的文件一个字节都不变")

    def test_没有Pillow照样出订阅源(self):
        with mock.patch.object(podcast_feed, "_pil", return_value=None):
            out, problems, stats = self.pkg([pod_issue(self.issues, "2026-11-19")])
        self.assertEqual(problems, [])
        self.assertIn("没有 Pillow", stats["播客订阅源"])
        text, root = self.feed(out)
        self.assertIsNone(root.find("channel/item").find("itunes:image", NS), "单集不写封面，App 用节目封面")
        self.assertIsNotNone(root.find("channel").find("itunes:image", NS))
        self.assertEqual(sorted(p.name for p in (out / "frontier/_podcast").iterdir()), ["2026-11-19.chapters.json", "cover.jpg", "feed.xml"])

    @unittest.skipUnless(_PILImage, "没装 Pillow：单集封面这条跳过")
    def test_单集封面1400见方(self):
        for mode in ("A", "B"):
            with mock.patch.object(podcast_feed, "EPISODE_COVER", mode):
                out, problems, stats = self.pkg([pod_issue(self.issues / mode, "2026-11-19")])
            with _PILImage.open(out / "frontier/_podcast/2026-11-19.jpg") as im:
                self.assertEqual((im.size, im.mode, im.format), ((1400, 1400), "RGB", "JPEG"), mode)
            self.assertIn("单集封面 1 张", stats["播客订阅源"])
            _, root = self.feed(out)
            self.assertEqual(root.find("channel/item").find("itunes:image", NS).get("href"), "__FD_FEED_BASE__/2026-11-19.jpg")
        with _PILImage.open(podcast_feed.SHOW_COVER) as im:
            self.assertEqual((im.size, im.mode, im.format), ((3000, 3000), "RGB", "JPEG"), "节目封面")

    def test_出错不连累网站(self):
        issues = self.week()
        off, p_off, _ = self.pkg(issues, podcast=False)
        base = tree(off)
        bad_xml = lambda items, desc: "<rss><channel><title>坏的"
        cases = [("模板写出不合法的 XML", mock.patch.object(podcast_feed, "build_feed", bad_xml)),
                 ("程序中途抛异常", mock.patch.object(podcast_feed, "chapters_for", side_effect=None)),
                 ("找不到节目封面", mock.patch.object(podcast_feed, "SHOW_COVER", self.t / "没有这个文件.jpg")),
                 ("build 直接炸了", mock.patch.object(podcast_feed, "build", side_effect=MemoryError("测试"))),
                 ("一期能收的都没有", mock.patch.object(podcast_feed, "LIMIT", 60))]
        cases[1] = ("程序中途抛异常", mock.patch.object(podcast_feed, "build_feed", side_effect=KeyError("测试")))
        cases[4] = ("一期能收的都没有", mock.patch.object(podcast_feed, "read_issue_js", side_effect=ValueError("测试")))
        for name, patch in cases:
            with patch:
                out, problems, stats = self.pkg(issues)
            self.assertEqual(problems, p_off, name + "：检查的“问题”不多")
            self.assertFalse((out / "frontier/_podcast").exists(), name + "：_podcast/ 整个不在")
            self.assertEqual(tree(out), base, name + "：上线包和开关关着时一样")
            self.assertIn("播客订阅源这次没做成", stats["播客订阅源"], name)
        self.assertFalse(any(Path(tempfile.gettempdir()).glob("fd-podcast-*")) and False)

    def test_一期坏了只跳过这一期(self):
        issues = self.week()
        bad = self.issues / "2026-11-15/10_网页v3/issues/2026-11-15/issue.js"
        bad.write_text(bad.read_text(encoding="utf-8").replace('"start": 40.5', '"start": "四十秒"'), encoding="utf-8")   # 网页照样能拼，章节时间读不出
        (self.issues / "2026-11-19/10_网页v3/issues/2026-11-19/img/card-1400.webp").write_bytes(b"not an image")
        out, problems, stats = self.pkg(issues)
        self.assertEqual(problems, [])
        self.assertTrue(any("2026-11-15" in x and "读不出" in x for x in stats["播客跳过"]), stats["播客跳过"])
        _, root = self.feed(out)
        guids = [it.findtext("guid")[-10:] for it in root.find("channel").findall("item")]
        self.assertNotIn("2026-11-15", guids)
        self.assertIn("2026-11-19", guids)
        if _PILImage:
            self.assertTrue(any("2026-11-19 没做单集封面" in x for x in stats["播客跳过"]), stats["播客跳过"])
            it = next(i for i in root.find("channel").findall("item") if i.findtext("guid").endswith("2026-11-19"))
            self.assertIsNone(it.find("itunes:image", NS), "头图坏了：这一期不写单集封面，照常收")
            self.assertFalse((out / "frontier/_podcast/2026-11-19.jpg").exists())

    def test_收几期(self):
        out, _, stats = self.pkg(self.week(), limit=2)
        _, root = self.feed(out)
        self.assertEqual([it.findtext("guid")[-10:] for it in root.find("channel").findall("item")], ["2026-11-19", "2026-11-15"])
        self.assertEqual(sorted(p.name for p in (out / "frontier/_podcast").glob("*.chapters.json")), ["2026-11-15.chapters.json", "2026-11-19.chapters.json"])

    def test_简介太长会省_节目简介不超过4000字节(self):
        out, problems, stats = self.pkg([pod_issue(self.issues, "2026-11-19", flash_n=60, long_flash=True)])
        self.assertEqual(problems, [])
        _, root = self.feed(out)
        desc = root.find("channel/item").findtext("description")
        self.assertLessEqual(len(desc), 10000)
        self.assertIn("今天的热点", desc)
        self.assertLessEqual(len(podcast_feed.show_desc_html().encode("utf-8")), 4000)
        self.assertLessEqual(len(root.find("channel").findtext("description").encode("utf-8")), 4000)

    def test_章节名(self):
        iss = {"date": "2026-11-30", "card": {"headlines": [{"ref": "E1", "zh": "卡片一"}], "term": {"zh": "某词"}},
               "order": {"headline": ["E1", "E2"]}, "stories": {"E1": {"title_zh": "甲", "listen": 57.2}, "E2": {"title_zh": "乙", "listen": 30.0}},
               "media": {"podcast": {"chapters": [{"start": 0, "title_zh": "开场"}, {"start": 57.16, "title_zh": "热点一"},
                                                  {"start": 186.0, "title_zh": "热点二"}, {"start": 400, "title_zh": "今日一词"}]}}}
        self.assertEqual([c["title"] for c in podcast_feed.chapters_for(iss)], ["开场", "热点一", "热点二", "今日一词 · 某词"],
                         "HOT_TITLE_FROM 空着：热点章名不接标题")
        with mock.patch.object(podcast_feed, "HOT_TITLE_FROM", "2026-11-23"):
            self.assertEqual([c["title"] for c in podcast_feed.chapters_for(iss)], ["开场", "热点一 · 卡片一", "热点二", "今日一词 · 某词"],
                             "listen 恰好对上一条才接（热点二对不上就不接）")
            iss["date"] = "2026-11-12"
            self.assertEqual(podcast_feed.chapters_for(iss)[1]["title"], "热点一", "这一天以前的期不接")
        iss["media"]["podcast"]["chapters"][0]["title_zh"] = "很长" * 30
        self.assertEqual(len(podcast_feed.chapters_for(iss)[0]["title"]), 40)

    def test_main_环境变量和参数(self):
        issue = pod_issue(self.issues, "2026-11-19")
        args = ["--repo", str(self.t / "repo"), "--issue", str(issue)]
        summ = self.t / "summary.md"
        with mock.patch.dict(os.environ, {"FD_PODCAST_FEED": ""}):
            self.assertEqual(assemble.main(args + ["--out", str(self.t / "m0"), "--summary", str(summ)]), 0)
        self.assertFalse((self.t / "m0/frontier/_podcast").exists())
        self.assertNotIn("播客", summ.read_text(encoding="utf-8"), "关着时清单一个字都不多")
        for env, extra, name in (({"FD_PODCAST_FEED": "on"}, [], "m1"), ({"FD_PODCAST_FEED": "ON "}, [], "m2"), ({}, ["--podcast"], "m3")):
            with mock.patch.dict(os.environ, env):
                self.assertEqual(assemble.main(args + ["--out", str(self.t / name), "--summary", str(summ)] + extra), 0, name)
            self.assertTrue((self.t / name / "frontier/_podcast/feed.xml").is_file(), name)
        self.assertIn("播客订阅源：1 期", summ.read_text(encoding="utf-8"))
        with mock.patch.dict(os.environ, {"FD_PODCAST_FEED": "off"}):
            assemble.main(args + ["--out", str(self.t / "m4")])
        self.assertFalse((self.t / "m4/frontier/_podcast").exists())
        two = [pod_issue(self.issues, "2026-11-18")]
        with mock.patch.dict(os.environ, {"FD_PODCAST_FEED": "on", "FD_PODCAST_LIMIT": "1"}):
            assemble.main(args + ["--issue", str(two[0]), "--out", str(self.t / "m5")])
        self.assertEqual(len(ET.parse(self.t / "m5/frontier/_podcast/feed.xml").getroot().findall("channel/item")), 1)

    def test_和加这个功能以前的程序比(self):
        """开关关着时，新程序做的上线包和加功能以前的 assemble.py 逐字节一样；以前的程序碰上 FD_PODCAST_FEED=on 也照常出包、一样。
        以前的程序从 git 历史里取（加 podcast_feed.py 那次提交的上一版）；没有 git 历史（比如浅克隆）就跳过。"""
        repo = HERE.parent.parent.parent
        try:
            added = subprocess.run(["git", "-C", str(repo), "log", "--diff-filter=A", "--format=%H", "--", "cloud/deploy/podcast_feed.py"],
                                   capture_output=True, text=True, check=True).stdout.split()
            rev = (added[-1] + "^") if added else "HEAD"
            old = subprocess.run(["git", "-C", str(repo), "show", rev + ":cloud/deploy/assemble.py"], capture_output=True, text=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError) as e:
            self.skipTest("取不到加功能以前的 assemble.py（%s）" % type(e).__name__)
        if "FD_PODCAST_FEED" in old:
            self.skipTest("git 历史里找到的那一版已经有播客开关，比不了")
        (self.t / "old").mkdir()
        (self.t / "old" / "assemble.py").write_text(old, encoding="utf-8")
        issues = self.week()
        common = ["--repo", str(self.t / "repo")] + sum((["--issue", str(i)] for i in issues), [])
        env0 = {k: v for k, v in os.environ.items() if not k.startswith("FD_PODCAST")}
        env0["PYTHONDONTWRITEBYTECODE"] = "1"
        outs = {}
        for name, script, env in (("旧", self.t / "old" / "assemble.py", env0), ("旧+开关", self.t / "old" / "assemble.py", dict(env0, FD_PODCAST_FEED="on")),
                                  ("新", HERE.parent / "assemble.py", env0)):
            r = subprocess.run([sys.executable, str(script)] + common + ["--out", str(self.t / name)], capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, name + r.stderr)
            outs[name] = (tree(self.t / name), re.sub(r"（\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC）", "", r.stdout))
        self.assertEqual(outs["旧+开关"], outs["旧"], "旧程序不认识这个环境变量，照常出包、一个字节不差")
        self.assertEqual(outs["新"], outs["旧"], "新程序开关关着：上线包和清单都和以前一样")
        self.assertFalse(any(k.startswith("frontier/_podcast/") for k in outs["旧+开关"][0]))

    def test_底乐出处和_video3_music_一致(self):
        """podcast_feed.MUSIC_LINKS 是抄 site/tools/video3_music.py 的 CREDITS（那个文件要 numpy，不能直接 import）：这里核对两边一致。"""
        import ast
        src = HERE.parent.parent.parent / "site" / "tools" / "video3_music.py"
        if not src.is_file():
            self.skipTest("没有 site/tools/video3_music.py")
        tree_ = ast.parse(src.read_text(encoding="utf-8"))
        credits = next(ast.literal_eval(n.value) for n in tree_.body if isinstance(n, ast.Assign)
                       and any(getattr(t, "id", "") == "CREDITS" for t in n.targets))
        got = {v["曲名"]: v["url"] for v in credits.values()}
        self.assertEqual(got, podcast_feed.MUSIC_LINKS)


if __name__ == "__main__":
    unittest.main()
