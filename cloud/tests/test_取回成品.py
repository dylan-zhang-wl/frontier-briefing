"""取回成品（cloud/取回成品.py）的本机测试：python3 -m unittest discover -s cloud/tests -v
不联网：gh 换成假的（按预先写好的接口回应答复）；网页外壳用 cloud/deploy/tests 里那套假仓库；git pull 用临时的裸仓库。
成品库、临时目录都在测试自己的临时文件夹里，不碰 iCloud、不碰 ~/.cache。
2026-11-09 晚改：成品放进成品库，从 media、issue 两份产物拼回完整期目录，10_网页v3 要能双击打开。
2026-11-09 晚再改：成品库换成仓库根目录下的 本机资料/成品/<日期>/（按程序自己的位置找仓库根）；加满 7 天、已发布的期移进废纸篓，--dry-run 只列。
2026-11-11 改（拆成公开、私有两个仓库）：运行和认领标签在公开仓库，整期文件包在私有仓库的发行版 run-<编号>（.tar.gz），
site-archive 在私有仓库；本机资料/ 的位置可用环境变量 FD_LOCAL_DATA 指定。假 gh 里"产物"换成"发行版里的文件包"，过期＝发行版不在了。"""
import base64
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fetch_issue", HERE.parent / "取回成品.py")
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
sys.path.insert(0, str(HERE.parent / "deploy" / "tests"))
sys.path.insert(0, str(HERE.parent / "deploy"))
from test_deploy import make_repo, make_issue  # noqa: E402  网站上线包测试里那套假仓库、假期目录

DAY = "2026-11-10"


class FakeGH:
    def __init__(self, archive=None, tag_run=None, runs=(), artifacts=None, steps=None, srcs=None, run_status=None, expired=(),
                 published=(), broken=False):
        self.archive = archive or {}          # 相对 issues/<日期>/ 的路径 → 字节；空＝site-archive 没有这一天
        self.published = set(published)      # site-archive 里另外有哪几天（只给清理用，里面没有文件）
        self.broken = broken                  # True：site-archive 的接口出错（没联网之类）
        self.tag_run, self.runs = tag_run, list(runs)
        self.artifacts = artifacts or {}      # 运行编号 → [文件包名（不带 .tar.gz）]；发行版 run-<编号> 里的
        self.steps = steps or {}              # 运行编号 → "提交跨天状态" 那一步的 conclusion
        self.srcs = srcs or {}                # 产物名 → 下载时拷过去的目录
        self.run_status, self.expired = run_status or {}, set(expired)     # expired：那几个文件包没了；全没了＝发行版不在
        self.downloads, self.calls = [], []

    def api(self, path, missing_ok=False):
        self.calls.append(path)
        pub, priv = "repos/" + F.REPO_SLUG + "/", "repos/" + F.STATE_SLUG + "/"
        if path.startswith(priv):                     # 私有仓库：site-archive、发行版
            p = path[len(priv):]
            if p.startswith("git/ref/") or p.startswith("actions/"):
                raise AssertionError("认领标签、运行在公开仓库，不该去私有仓库找：" + path)
        elif path.startswith(pub):                    # 公开仓库：认领标签、运行
            p = path[len(pub):]
            if p.startswith("branches/") or p.startswith("git/trees") or p.startswith("git/blobs") or p.startswith("releases"):
                raise AssertionError("site-archive、发行版在私有仓库，不该去公开仓库找：" + path)
        else:
            raise AssertionError("没想到的仓库：" + path)
        if p == "releases?per_page=100":
            out = []
            for rid, names in self.artifacts.items():
                left = [n for n in names if n not in self.expired]
                if left:
                    out.append({"tag_name": "run-%d" % rid, "draft": True,
                                "assets": [{"name": n + ".tar.gz", "size": 123 * 1048576} for n in left] + [{"name": "画图材料.tar.gz", "size": 1}]})
            out.append({"tag_name": "v1.0", "draft": False, "assets": []})
            return out
        if p == "branches/site-archive":
            if self.broken:
                raise RuntimeError("gh api %s 出错：连不上" % path)
            return {"commit": {"commit": {"tree": {"sha": "root"}}}} if (self.archive or self.published) else None
        if p == "git/trees/root":
            return {"tree": [{"path": "issues", "type": "tree", "sha": "issues"}, {"path": "README.md", "type": "blob", "sha": "r"}]}
        if p == "git/trees/issues":
            days = set(self.published) | ({DAY} if self.archive else set())
            return {"tree": [{"path": d, "type": "tree", "sha": "day" if d == DAY else "d:" + d} for d in sorted(days)]
                    + [{"path": "index.json", "type": "blob", "sha": "i"}]}
        if p == "git/trees/day?recursive=1":
            return {"truncated": False, "tree": [{"path": k, "type": "blob", "sha": "b:" + k, "size": len(v)} for k, v in self.archive.items()]}
        if p.startswith("git/blobs/b:"):
            return {"content": base64.b64encode(self.archive[p[len("git/blobs/b:"):]]).decode(), "encoding": "base64"}
        if p == "git/ref/tags/issue/" + DAY:
            return {"object": {"type": "tag", "sha": "tagobj"}} if self.tag_run else None
        if p == "git/tags/tagobj":
            return {"message": "认领 %s：运行 %d（触发 schedule，%s 04:17:30 UTC） · 1a2b3c4d" % (DAY, self.tag_run, DAY)}
        if p.startswith("actions/runs/") and "/jobs" in p:
            rid = int(p.split("/")[2])
            return {"jobs": [{"name": "issue", "steps": [{"name": "提交跨天状态（事件库、账本、这一期的文字，进私有仓库）", "conclusion": self.steps.get(rid, "skipped")}]}]}
        if p.startswith("actions/runs/"):
            rid = int(p.split("/")[2])
            st = self.run_status.get(rid, ("completed", "success"))
            return {"status": st[0], "conclusion": st[1], "html_url": "https://github.com/%s/actions/runs/%d" % (F.REPO_SLUG, rid)}
        raise AssertionError("没想到的接口：" + path)

    def run_list(self):
        return [{"databaseId": r, "status": self.run_status.get(r, ("completed",))[0], "conclusion": "success", "createdAt": "", "event": "schedule"} for r in self.runs]

    def releases(self):
        return F.GH.releases(self)

    def download(self, run_id, name, dest):
        self.downloads.append((run_id, name))
        shutil.copytree(self.srcs[name], Path(dest))


def put(d, rel, data=b"x"):
    f = d / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


class FetchTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.repo = self.root / "repo"
        make_repo(self.repo)
        self.small = make_issue(self.root / "small", DAY, "今天的头条")      # 小份 issue-<日期>：<small>/<日期>/10_网页v3/issues/<日期>/…
        for rel in ("00_调度报告.md", "审片.md", "审片结论.json", "自检.md", "花费.json", "04_文稿/claude_播客_v3.md", "logs/fd_state.json"):
            put(self.small, rel, "小份 " + rel)
        # 带音视频的 media-<日期>：整期目录（网页外壳齐全、有字体），没有"审片.md"（用来看小份补缺）
        self.media = self.root / "media" / DAY
        shutil.copytree(self.small, self.media)
        (self.media / "审片.md").unlink()
        put(self.media, "00_调度报告.md", "media 调度报告")
        put(self.media, "05_配音/播客_v3_带音效/episode.mp3", b"ID3")
        put(self.media, "11_视频v3/预览.mp4", b"mp4")
        put(self.media, "11_视频v3_导演/结果.json", "{}")
        for f in F.WEB_SHELL:
            put(self.media / "10_网页v3", f, "/* 云端那次的 %s */" % f)
        put(self.media / "10_网页v3", "issues/%s/fonts/body-kai.woff2" % DAY, b"wOF2")
        self.out = self.root / "成品库" / "测试版"
        self.work = self.root / "取回中"
        self.lines = []

    def tearDown(self):
        self.td.cleanup()

    def run_fetch(self, gh, **kw):
        return F.fetch(kw.pop("day", DAY), self.out, self.repo, do_pull=False, gh=gh, log=self.lines.append, work=self.work, **kw)

    def web_files(self):
        d = self.small / "10_网页v3" / "issues" / DAY
        return {str(p.relative_to(d)): p.read_bytes() for p in d.rglob("*") if p.is_file()}

    def assert_clean(self):
        self.assertEqual(list(self.work.iterdir()) if self.work.exists() else [], [])        # 临时目录清干净了
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), [DAY])                  # 成品库里只有这一天

    def test_没发布_media打底_小份补缺_拼成完整期目录(self):
        gh = FakeGH(tag_run=4242, artifacts={4242: ["issue-" + DAY, "media-" + DAY, "state-" + DAY]},
                    srcs={"media-" + DAY: self.media, "issue-" + DAY: self.small})
        self.assertEqual(self.run_fetch(gh), 0)
        self.assertEqual(gh.downloads, [(4242, "media-" + DAY), (4242, "issue-" + DAY)])
        dest = self.out / DAY
        self.assertEqual((dest / "00_调度报告.md").read_text(encoding="utf-8"), "media 调度报告")   # media 打底，已有的不被小份盖掉
        self.assertEqual((dest / "审片.md").read_text(encoding="utf-8"), "小份 审片.md")             # 小份补上缺的
        for rel in ("05_配音/播客_v3_带音效/episode.mp3", "11_视频v3/预览.mp4", "11_视频v3_导演/结果.json", "自检.md", "花费.json",
                    "logs/fd_state.json", "10_网页v3/issues/%s/issue.js" % DAY):
            self.assertTrue((dest / rel).is_file(), rel)
        self.assertEqual((dest / "10_网页v3" / "index.html").read_text(encoding="utf-8"), "/* 云端那次的 index.html */")  # 外壳齐了就不重拼
        note = (dest / "取回说明.txt").read_text(encoding="utf-8")
        self.assertIn("运行 4242", note)
        self.assertNotIn("缺了什么", note)
        self.assertFalse((dest / "整期目录").exists() or (dest / "网页").exists())
        self.assertIn("取回了 %s：media-%s" % (DAY, DAY), self.lines[-1])
        self.assert_clean()

    def test_只有小份_外壳用仓库补齐_网页能双击(self):
        gh = FakeGH(tag_run=4242, artifacts={4242: ["issue-" + DAY]}, srcs={"issue-" + DAY: self.small})
        self.assertEqual(self.run_fetch(gh), 0)
        self.assertEqual(gh.downloads, [(4242, "issue-" + DAY)])
        web = self.out / DAY / "10_网页v3"
        for f in F.WEB_SHELL + ("issues/%s/issue.js" % DAY, "issues/%s/audio/podcast.mp3" % DAY):
            self.assertTrue((web / f).is_file(), f)
        self.assertIn('src="app.js"', (web / "index.html").read_text(encoding="utf-8"))
        note = (self.out / DAY / "取回说明.txt").read_text(encoding="utf-8")
        self.assertIn("没有带音视频的 media-%s" % DAY, note)
        self.assertIn("字体文件", note)                                   # 假期目录没有字体：照实写
        self.assert_clean()

    def test_产物过期_从site_archive取网页(self):
        gh = FakeGH(tag_run=4242, artifacts={4242: ["issue-" + DAY, "media-" + DAY]}, expired={"issue-" + DAY, "media-" + DAY},
                    archive=self.web_files())
        self.assertEqual(self.run_fetch(gh), 0)
        self.assertEqual(gh.downloads, [])
        web = self.out / DAY / "10_网页v3"
        self.assertTrue((web / "index.html").is_file())
        self.assertTrue((web / "issues" / DAY / "audio" / "podcast.mp3").is_file())
        note = (self.out / DAY / "取回说明.txt").read_text(encoding="utf-8")
        self.assertIn("site-archive", note)
        self.assertIn("已过期", note)
        self.assert_clean()

    def test_没有标签_在main上找正式运行_跳过测试运行(self):
        gh = FakeGH(runs=[9, 8, 7], artifacts={9: ["issue-" + DAY], 8: ["media-" + DAY], 7: ["media-" + DAY]},
                    steps={9: "skipped", 8: "success", 7: "success"}, srcs={"media-" + DAY: self.media})
        self.assertEqual(self.run_fetch(gh), 0)
        self.assertEqual(gh.downloads, [(8, "media-" + DAY)])

    def test_运行还没跑完_退出码1_什么也不留(self):
        gh = FakeGH(tag_run=4242, run_status={4242: ("in_progress", None)})
        with self.assertRaises(F.NotYet):
            self.run_fetch(gh)
        self.assertFalse(self.out.exists())
        self.assertEqual(list(self.work.iterdir()), [])

    def test_找不到运行也没有存档(self):
        gh = FakeGH(runs=[5], run_status={5: ("in_progress", None)})
        with self.assertRaises(F.NotYet):
            self.run_fetch(gh)
        self.assertTrue(any("还有运行没跑完：5" in l for l in self.lines))
        self.assertFalse(self.out.exists())

    def test_已经有这一天就跳过_force把旧的移进废纸篓(self):
        put(self.out / DAY, "00_调度报告.md", "mini 那期")                  # 比如 mini 以前出的 2026-11-09
        gh = FakeGH(tag_run=4242, artifacts={4242: ["media-" + DAY]}, srcs={"media-" + DAY: self.media})
        self.assertEqual(self.run_fetch(gh), 0)
        self.assertIn("已经有了", self.lines[-1])
        self.assertEqual(gh.calls, [])
        self.assertEqual((self.out / DAY / "00_调度报告.md").read_text(encoding="utf-8"), "mini 那期")
        moved = []
        orig = F.to_trash
        F.to_trash = lambda p: moved.append(p.name) or p.rename(self.root / ("废纸篓-" + p.name))
        try:
            self.assertEqual(self.run_fetch(gh, force=True), 0)
        finally:
            F.to_trash = orig
        self.assertEqual(moved, [DAY])
        self.assertEqual((self.root / ("废纸篓-" + DAY) / "00_调度报告.md").read_text(encoding="utf-8"), "mini 那期")
        self.assertEqual((self.out / DAY / "00_调度报告.md").read_text(encoding="utf-8"), "media 调度报告")
        self.assert_clean()

    def test_周六不出刊_不用取(self):
        gh = FakeGH()
        self.assertEqual(self.run_fetch(gh, day="2026-11-14"), 0)
        self.assertIn("周六", self.lines[-1])
        self.assertEqual(gh.calls, [])

    def test_默认成品库是仓库根目录下的本机资料成品_不写死绝对路径(self):
        root = HERE.parent.parent                                    # 本测试在 <仓库根>/cloud/tests/
        self.assertEqual(F.DEFAULT_REPO, root)
        self.assertEqual(F.DEFAULT_OUT, root / "本机资料" / "成品")
        src = (HERE.parent / "取回成品.py").read_text(encoding="utf-8")
        self.assertNotIn('"/' + 'Users/', src)                       # 程序里没有写死的本机绝对路径（拆开写，免得本文件自己也带着它）
        self.assertNotIn("前沿简报成品", src)
        self.assertNotIn('"Projects"', src)                           # 不再默认 ~/Projects/frontier-daily-cloud
        ign = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("本机资料/", ign)                               # 成品库不进 git

    def test_本机资料可用环境变量指定_仓库跟着它(self):
        local = self.root / "私有那份" / "本机资料"
        with mock_env({"FD_LOCAL_DATA": str(local)}):
            spec2 = importlib.util.spec_from_file_location("fetch_issue_env", HERE.parent / "取回成品.py")
            F2 = importlib.util.module_from_spec(spec2)
            spec2.loader.exec_module(F2)
        self.assertEqual(F2.DEFAULT_OUT, local / "成品")
        self.assertEqual(F2.DEFAULT_REPO, local.parent)

    def test_文件包解开_只许普通文件(self):
        tgz = self.root / "x.tar.gz"
        with tarfile.open(tgz, "w:gz") as t:
            t.add(self.small, arcname=".")
        F.untar(tgz, self.root / "解开")
        self.assertEqual((self.root / "解开" / "审片.md").read_text(encoding="utf-8"), "小份 审片.md")
        bad = self.root / "bad.tar.gz"
        with tarfile.open(bad, "w:gz") as t:
            t.add(self.small / "审片.md", arcname="../越界.md")
        with self.assertRaises(RuntimeError):
            F.untar(bad, self.root / "解开2")
        self.assertFalse((self.root / "越界.md").exists())

    def test_试运行_不下载不拉(self):
        gh = FakeGH(tag_run=4242, artifacts={4242: ["media-" + DAY]}, srcs={"media-" + DAY: self.media})
        self.assertEqual(F.fetch(DAY, self.out, self.repo, do_pull=True, gh=gh, log=self.lines.append, work=self.work, dry_run=True), 0)
        self.assertEqual(gh.calls, [])
        self.assertEqual(gh.downloads, [])
        self.assertFalse(self.out.exists())
        self.assertIn("试运行", self.lines[-1])


@contextlib.contextmanager
def mock_env(env):
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class CleanTest(unittest.TestCase):
    """满 7 天、而且 site-archive 里有（已发布）的期目录才移进废纸篓；别的都不动。"""
    TODAY = F.date(2026, 11, 20)

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.out = self.root / "本机资料" / "成品"
        for d in ("2026-11-09", "2026-11-12", "2026-11-13", "2026-11-14", "2026-11-19", "试验的东西"):
            put(self.out / d, "00_调度报告.md", d)
        put(self.out, "README.md", "说明")
        self.trash = self.root / "废纸篓"
        self.trash.mkdir()
        self.orig = F.to_trash
        F.to_trash = lambda p: p.rename(self.trash / p.name) or (self.trash / p.name)
        self.lines = []

    def tearDown(self):
        F.to_trash = self.orig
        self.td.cleanup()

    def left(self):
        return sorted(p.name for p in self.out.iterdir())

    def test_满7天且已发布才清_没发布的和不满7天的不动(self):
        gh = FakeGH(published={"2026-11-09", "2026-11-13", "2026-11-14", "2026-11-19"})
        moved, kept = F.clean_old(self.out, gh, self.TODAY, log=self.lines.append)
        self.assertEqual(moved, ["2026-11-09", "2026-11-13"])          # 11-20 往前满 7 天：11-13 及更早
        self.assertEqual(sorted(p.name for p in self.trash.iterdir()), ["2026-11-09", "2026-11-13"])
        self.assertIn("2026-11-12", kept)                               # 满 7 天但没发布：不动
        self.assertEqual(self.left(), ["2026-11-12", "2026-11-14", "2026-11-19", "README.md", "试验的东西"])

    def test_试运行只列不动(self):
        gh = FakeGH(published={"2026-11-09", "2026-11-13"})
        moved, _ = F.clean_old(self.out, gh, self.TODAY, dry_run=True, log=self.lines.append)
        self.assertEqual(moved, ["2026-11-09", "2026-11-13"])
        self.assertEqual(list(self.trash.iterdir()), [])
        self.assertEqual(len(self.left()), 7)
        self.assertTrue(any("试运行" in l for l in self.lines))

    def test_网站还没发布过_一个都不清(self):
        moved, kept = F.clean_old(self.out, FakeGH(), self.TODAY, log=self.lines.append)
        self.assertEqual(moved, [])
        self.assertEqual(sorted(kept), ["2026-11-09", "2026-11-12", "2026-11-13"])
        self.assertEqual(len(self.left()), 7)

    def test_查不到site_archive_一个都不清(self):
        moved, _ = F.clean_old(self.out, FakeGH(published={"2026-11-09"}, broken=True), self.TODAY, log=self.lines.append)
        self.assertEqual(moved, [])
        self.assertEqual(len(self.left()), 7)
        self.assertIn("这次不清理", self.lines[-1])

    def test_main_先清理再取回_最后一行是取回的结果(self):
        put(self.out / DAY, "00_调度报告.md", "已有")
        put(self.out / "2026-10-01", "00_调度报告.md", "很早的一期")       # main 按真实的今天算：这一期一定满 7 天
        gh = FakeGH(published={"2026-10-01"})
        orig_gh = F.GH
        F.GH = lambda: gh
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = F.main(["--date", DAY, "--out-root", str(self.out), "--no-pull", "--dry-run"])
        finally:
            F.GH = orig_gh
        lines = buf.getvalue().splitlines()
        self.assertEqual(rc, 0)
        self.assertEqual(list(self.trash.iterdir()), [])                # 试运行：没移
        self.assertIn("已经有了", lines[-1])
        self.assertTrue(any("2026-10-01" in l and "试运行" in l for l in lines[:-1]))


class PullTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        r = Path(self.td.name)
        self.remote, self.repo, self.other = r / "remote.git", r / "repo", r / "other"
        g = lambda *a, cwd=None: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True, capture_output=True)
        g("init", "-q", "--bare", "-b", "main", str(self.remote))
        g("clone", "-q", str(self.remote), str(self.other))
        g("checkout", "-q", "-b", "main", cwd=self.other)
        g("commit", "-q", "--allow-empty", "-m", "一", cwd=self.other)
        g("push", "-q", "origin", "main", cwd=self.other)
        g("clone", "-q", "-b", "main", str(self.remote), str(self.repo))
        g("commit", "-q", "--allow-empty", "-m", "二", cwd=self.other)
        g("push", "-q", "origin", "main", cwd=self.other)
        self.g = g

    def tearDown(self):
        self.td.cleanup()

    def head(self, d):
        return subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    def test_干净就拉(self):
        lines = []
        self.assertTrue(F.pull(self.repo, lines.append))
        self.assertEqual(self.head(self.repo), self.head(self.other))

    def test_有没提交的改动_只提醒不拉(self):
        (self.repo / "草稿.txt").write_text("x", encoding="utf-8")
        lines = []
        self.assertFalse(F.pull(self.repo, lines.append))
        self.assertIn("没提交的改动", lines[0])
        self.assertNotEqual(self.head(self.repo), self.head(self.other))

    def test_不在main上_只提醒不拉(self):
        self.g("checkout", "-q", "-b", "别的", cwd=self.repo)
        lines = []
        self.assertFalse(F.pull(self.repo, lines.append))
        self.assertIn("不在 main", lines[0])


if __name__ == "__main__":
    unittest.main()
