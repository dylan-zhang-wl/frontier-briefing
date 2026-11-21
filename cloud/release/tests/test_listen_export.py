"""耳听点选结果自动存回（listen_export.py）的本机测试：python -m unittest discover -s cloud/release/tests -v
不联网：网站用本机一个临时的小 HTTP 服务代替（核对 Cookie），私有仓库用临时目录里的 git 裸仓库代替。钥匙指纹是测试现编的。"""
import hashlib
import http.server
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import listen_export as L  # noqa: E402

HASH = hashlib.sha256(b"test-key-only-for-listen-export").hexdigest()
EXPORT = {"说明": "x", "导出于": "2026-11-30T07:00:00.000Z", "条数": 3, "结果": [
    {"日期": "2026-11-29", "条目": "a1b2c3d4e5", "结果": "念错了", "结果码": "wrong", "备注": "测试备注", "点选时间": "2026-11-29T20:01:00.000Z",
     "第几处": 1, "位置": "播客 1:23", "原稿": "测试原稿", "转写成": "测试转写", "说明": "测试说明", "判断": "多半真念错", "关乎事实": True, "依据": "测试依据"},
    {"日期": "2026-11-30", "条目": "b2c3d4e5f6", "结果": "念对了", "结果码": "right", "备注": "", "点选时间": "2026-11-30T06:10:00.000Z",
     "第几处": 2, "位置": "视频 12 秒", "原稿": "", "转写成": "", "说明": "", "判断": "拿不准", "关乎事实": False, "依据": ""},
    {"日期": "2026-11-30", "条目": "c3d4e5f6a7", "结果": "没听出来", "结果码": "unsure", "备注": "", "点选时间": "2026-11-30T06:05:00.000Z",
     "找不到条目": "这一期的条目里没有这个编号"},
]}


class Site(http.server.BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        Site.seen.append((self.path, self.headers.get("Cookie"), self.headers.get("User-Agent")))
        if self.path.startswith("/slow"):
            time.sleep(3)
        if self.path.startswith("/html"):
            body, code, typ = b"<html>Just a moment...</html>", 200, "text/html"
        elif self.path.startswith("/blocked"):
            body, code, typ = b"<html>blocked</html>", 403, "text/html"
        elif self.headers.get("Cookie") == "fd_pass=" + HASH:
            body, code, typ = json.dumps(Site.data, ensure_ascii=False).encode("utf-8"), 200, "application/json"
        else:
            body, code, typ = "没有这个页面".encode("utf-8"), 404, "text/html"
        self.send_response(code)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def sh(*a, cwd=None):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)


class ListenExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Site)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Site.data = json.loads(json.dumps(EXPORT))
        Site.seen.clear()
        self.td = tempfile.TemporaryDirectory()
        self.t = Path(self.td.name)
        self.summary = self.t / "summary.md"
        self.env = mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(self.summary), "STATS_KEY_HASH": HASH,
                                                "FD_LISTEN_EXPORT_URL": self.base + "/frontier/_listen?export=json"})
        self.env.start()
        os.environ.pop("GH_PUSH_TOKEN", None)
        # 假的私有仓库：main 上有 测试版/别的.txt
        self.origin = self.t / "origin.git"
        sh("git", "init", "-q", "--bare", "-b", "main", str(self.origin))
        seed = self.t / "seed"
        sh("git", "init", "-q", "-b", "main", str(seed))
        (seed / "测试版").mkdir()
        (seed / "测试版" / "别的.txt").write_text("不能动", encoding="utf-8")
        sh("git", "-C", str(seed), "add", ".")
        sh("git", "-C", str(seed), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
        sh("git", "-C", str(seed), "push", "-q", str(self.origin), "main")

    def tearDown(self):
        self.env.stop()
        self.td.cleanup()

    def run_main(self, *args):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(L.main(list(args)), 0, "出什么事都回 0，不挡流程")
        return out.getvalue()

    def log(self):
        return subprocess.run(["git", "--git-dir", str(self.origin), "log", "--format=%an <%ae>|%s", "main"], capture_output=True, text=True).stdout.splitlines()

    def show(self):
        r = subprocess.run(["git", "--git-dir", str(self.origin), "show", "main:" + L.REPO_PATH], capture_output=True)
        return r.stdout if r.returncode == 0 else None

    def test_取到_只留六栏_不带钥匙_摘要只写条数和日子(self):
        out = self.t / "x" / "耳听结果.json"
        text = self.run_main("fetch", "--out", str(out))
        rec = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(rec["条数"], 3)
        self.assertEqual([list(r) for r in rec["结果"]], [["日期", "条目", "位置", "结果", "备注", "时间"]] * 3)
        self.assertEqual([(r["日期"], r["条目"]) for r in rec["结果"]],
                         [("2026-11-30", "c3d4e5f6a7"), ("2026-11-30", "b2c3d4e5f6"), ("2026-11-29", "a1b2c3d4e5")], "日期新到旧、同一天按时间")
        self.assertEqual(rec["结果"][2], {"日期": "2026-11-29", "条目": "a1b2c3d4e5", "位置": "播客 1:23", "结果": "念错了", "备注": "测试备注",
                                          "时间": "2026-11-29T20:01:00.000Z"})
        raw = out.read_text(encoding="utf-8")
        for bad in (HASH, "导出于", "测试原稿", "测试依据", "关乎事实"):
            self.assertNotIn(bad, raw)
        summ = self.summary.read_text(encoding="utf-8")
        self.assertIn("取到 3 条，最新一次点选在 2026-11-30（UTC），最新一期是 2026-11-30", summ)
        for s in (text, summ):
            self.assertNotIn(HASH, s, "不打印钥匙")
            self.assertNotIn("测试备注", s, "不打印响应内容")
        path, cookie, ua = Site.seen[-1]
        self.assertEqual(path, "/frontier/_listen?export=json")
        self.assertEqual(cookie, "fd_pass=" + HASH, "照 Worker 认站长 Cookie 的写法")
        self.assertIn("frontier-daily", ua)
        # 同样的导出（导出时间不同）做两次，文件逐字节一样
        first = out.read_bytes()
        Site.data["导出于"] = "2026-12-01T00:00:00.000Z"
        self.run_main("fetch", "--out", str(out))
        self.assertEqual(out.read_bytes(), first)

    def test_钥匙不对_没设_格式不对_不通_超时_被拦_不是JSON_都只写原因(self):
        out = self.t / "y.json"
        cases = [
            ("钥匙不对", {"STATS_KEY_HASH": "f" * 64}, "网站回 404"),
            ("没设", {"STATS_KEY_HASH": ""}, "没有 STATS_KEY_HASH"),
            ("格式不对", {"STATS_KEY_HASH": "not-a-hash"}, "格式不对"),
            ("不通", {"FD_LISTEN_EXPORT_URL": "http://127.0.0.1:9/frontier/_listen?export=json"}, "连不上"),
            ("被拦", {"FD_LISTEN_EXPORT_URL": self.base + "/blocked"}, "网站回 403"),
            ("不是 JSON", {"FD_LISTEN_EXPORT_URL": self.base + "/html"}, "回的不是导出的 JSON"),
        ]
        for name, env, want in cases:
            with mock.patch.dict(os.environ, env):
                text = self.run_main("fetch", "--out", str(out))
            self.assertIn("::warning::", text, name)
            self.assertIn(want, text, name)
            self.assertFalse(out.exists(), name + "：没取到就不写文件")
            self.assertNotIn(HASH, text)
            self.assertNotIn("f" * 64, text)
        with mock.patch.object(L, "TIMEOUT", 1), mock.patch.dict(os.environ, {"FD_LISTEN_EXPORT_URL": self.base + "/slow"}):
            ok, line = L.fetch(out, timeout=1)
        self.assertFalse(ok)
        self.assertIn("超时", line)
        self.assertIn("网站回 404", self.summary.read_text(encoding="utf-8"))
        # 没取到 → save 说一句、不提交
        text = self.run_main("save", "--file", str(out), "--repo-url", str(self.origin), "--work", str(self.t / "w0"))
        self.assertIn("这次没取到结果，不提交", text)
        self.assertEqual(len(self.log()), 1)

    def test_存回私有仓库_一样不提交_变了才提交_别的文件不动(self):
        f = self.t / "r.json"
        self.run_main("fetch", "--out", str(f))
        text = self.run_main("save", "--file", str(f), "--repo-url", str(self.origin), "--work", str(self.t / "w1"))
        self.assertIn("已提交进私有仓库 main 的 测试版/耳听结果.json（3 条）", text)
        self.assertEqual(self.show(), f.read_bytes())
        self.assertEqual(self.log()[0], "frontier-daily bot <frontier-daily-bot@users.noreply.github.com>|耳听点选结果：3 条")
        # 内容一样：不提交
        text = self.run_main("save", "--file", str(f), "--repo-url", str(self.origin), "--work", str(self.t / "w2"))
        self.assertIn("一样，不提交", text)
        self.assertEqual(len(self.log()), 2)
        # 改了一条：提交
        Site.data["结果"][1]["结果"] = "念错了"
        self.run_main("fetch", "--out", str(f))
        self.run_main("save", "--file", str(f), "--repo-url", str(self.origin), "--work", str(self.t / "w3"))
        self.assertEqual(len(self.log()), 3)
        self.assertIn("念错了", json.loads(self.show().decode("utf-8"))["结果"][1]["结果"])
        # 别的文件原样
        other = subprocess.run(["git", "--git-dir", str(self.origin), "show", "main:测试版/别的.txt"], capture_output=True, text=True).stdout
        self.assertEqual(other, "不能动")

    def test_别处先推过也能接上_推不上去只写原因(self):
        f = self.t / "r.json"
        self.run_main("fetch", "--out", str(f))
        # 克隆以后、推送以前，别处往 main 推了一个提交：pull --rebase 接上
        real_git = L.git
        state = {"done": False}

        def racing(cwd, *args, env, check=True):
            if args[:1] == ("pull",) and not state["done"]:
                state["done"] = True
                other = self.t / "other"
                sh("git", "clone", "-q", str(self.origin), str(other))
                (other / "测试版" / "新的.txt").write_text("别处", encoding="utf-8")
                sh("git", "-C", str(other), "add", ".")
                sh("git", "-C", str(other), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "别处")
                sh("git", "-C", str(other), "push", "-q", "origin", "main")
            return real_git(cwd, *args, env=env, check=check)
        with mock.patch.object(L, "git", racing):
            ok, line = L.save(f, str(self.origin), self.t / "w1", pause=0)
        self.assertTrue(ok, line)
        self.assertEqual([x.split("|")[1] for x in self.log()][:2], ["耳听点选结果：3 条", "别处"])
        # 地址不对：只写原因
        ok, line = L.save(f, str(self.t / "没有这个仓库.git"), self.t / "w2", pause=0)
        self.assertFalse(ok)
        self.assertIn("存的时候出错", line)

    def test_推送令牌只进git的环境_不进命令行(self):
        with mock.patch.dict(os.environ, {"GH_PUSH_TOKEN": "ghs_TEST_ONLY_not_real"}):
            env = L.git_env()
        self.assertNotIn("GH_PUSH_TOKEN", env)
        self.assertEqual(env["GIT_CONFIG_KEY_0"], "http.https://github.com/.extraheader")
        self.assertTrue(env["GIT_CONFIG_VALUE_0"].startswith("AUTHORIZATION: basic "))
        self.assertNotIn("ghs_TEST_ONLY_not_real", env["GIT_CONFIG_VALUE_0"], "base64 过，不是原文")
        with mock.patch.dict(os.environ, {"GH_PUSH_TOKEN": ""}):
            self.assertNotIn("GIT_CONFIG_COUNT", L.git_env())


if __name__ == "__main__":
    unittest.main()
