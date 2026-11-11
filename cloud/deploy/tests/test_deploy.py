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


if __name__ == "__main__":
    unittest.main()
