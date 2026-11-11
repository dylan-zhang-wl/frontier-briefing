"""认领／放回的本机测试：python3 -m unittest discover -s cloud/trigger/tests -v
在临时目录里建一个 git 裸仓库当"GitHub"，几个克隆当几次运行；不联网、不碰真仓库。"""
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "claim.py"
sys.path.insert(0, str(HERE.parent))
import claim as C  # noqa: E402


def sh(*args, cwd=None):
    return subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, check=True).stdout


class ClaimTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.remote = self.root / "remote.git"
        sh("git", "init", "-q", "--bare", "-b", "main", str(self.remote))   # 指明 main：GitHub 的机器上 git 默认分支是 master，克隆会没有 HEAD
        seed = self.clone("seed")
        sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init", cwd=seed)
        sh("git", "push", "-q", "origin", "HEAD:main", cwd=seed)

    def tearDown(self):
        self.td.cleanup()

    def clone(self, name):
        d = self.root / name
        subprocess.run(["git", "clone", "-q", str(self.remote), str(d)], capture_output=True, check=True)
        return d

    def run_claim(self, cwd, *args):
        p = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def remote_tags(self):
        out = sh("git", "ls-remote", str(self.remote), "refs/tags/*")
        return {line.split("\t")[1]: line.split("\t")[0] for line in out.splitlines() if not line.endswith("^{}")}

    def test_标签名_main_上是真日期_别的分支加前缀(self):
        self.assertEqual(C.tag_name("2026-11-10", "refs/heads/main"), "issue/2026-11-10")
        self.assertEqual(C.tag_name("2026-11-10", "refs/heads/daily-trigger"), "drill/daily-trigger/issue/2026-11-10")
        self.assertEqual(C.tag_name("2026-11-10", "refs/heads/a b"), "drill/a-b/issue/2026-11-10")
        with self.assertRaises(ValueError):
            C.tag_name("2026-1-10", "refs/heads/main")

    def test_第一次认领到_第二次被拒_输出给后面的_job(self):
        a, b = self.clone("run1"), self.clone("run2")
        out_a, out_b = self.root / "out_a", self.root / "out_b"
        rc, msg = self.run_claim(a, "claim", "--tag", "issue/2026-11-10", "--note", "认领 2026-11-10：运行 1", "--github-output", str(out_a))
        self.assertEqual(rc, 0, msg)
        self.assertIn("认领到了", msg)
        self.assertIn("claimed=true", out_a.read_text())
        sha = dict(line.split("=", 1) for line in out_a.read_text().splitlines())["tag_sha"]
        self.assertEqual(self.remote_tags()["refs/tags/issue/2026-11-10"], sha)
        rc, msg = self.run_claim(b, "claim", "--tag", "issue/2026-11-10", "--note", "认领 2026-11-10：运行 2", "--github-output", str(out_b))
        self.assertEqual(rc, 10, msg)
        self.assertIn("已经被别的运行认领", msg)
        self.assertIn("claimed=false", out_b.read_text())
        self.assertEqual(self.remote_tags()["refs/tags/issue/2026-11-10"], sha)      # 第一次的那个没被盖掉

    def test_同一个提交_同样的说明_也只有一个认领到(self):
        """两次运行在同一个提交上、说明一样：标签对象也不同（说明末尾有随机字），后来的不会被当成"已是最新"。"""
        a, b = self.clone("run1"), self.clone("run2")
        self.assertEqual(self.run_claim(a, "claim", "--tag", "issue/2026-11-11", "--note", "同样的说明")[0], 0)
        self.assertEqual(self.run_claim(b, "claim", "--tag", "issue/2026-11-11", "--note", "同样的说明")[0], 10)
        self.assertEqual(self.run_claim(a, "claim", "--tag", "issue/2026-11-11", "--note", "同样的说明")[0], 10)

    def test_八次同时认领_只有一个认领到(self):
        clones = [self.clone("r%d" % i) for i in range(8)]
        with ThreadPoolExecutor(8) as ex:
            rcs = list(ex.map(lambda d: self.run_claim(d, "claim", "--tag", "issue/2026-11-12", "--note", "并发 %s" % d.name)[0], clones))
        self.assertEqual(sorted(rcs), [0] + [10] * 7)

    def test_放回_只删自己那个(self):
        a, b = self.clone("run1"), self.clone("run2")
        out = self.root / "out"
        self.run_claim(a, "claim", "--tag", "issue/2026-11-13", "--github-output", str(out))
        mine = dict(line.split("=", 1) for line in out.read_text().splitlines())["tag_sha"]
        rc, msg = self.run_claim(a, "release", "--tag", "issue/2026-11-13", "--expect", mine)
        self.assertEqual(rc, 0, msg)
        self.assertIn("已放回", msg)
        self.assertNotIn("refs/tags/issue/2026-11-13", self.remote_tags())
        # 再放一次：本来就没有了，也算成
        rc, msg = self.run_claim(a, "release", "--tag", "issue/2026-11-13", "--expect", mine)
        self.assertEqual(rc, 0, msg)
        self.assertIn("本来就没有了", msg)
        # 放回以后下一次运行能认领到；旧的那次再来放回，不许删掉新认领的
        self.assertEqual(self.run_claim(b, "claim", "--tag", "issue/2026-11-13")[0], 0)
        rc, msg = self.run_claim(a, "release", "--tag", "issue/2026-11-13", "--expect", mine)
        self.assertEqual(rc, 11, msg)
        self.assertIn("refs/tags/issue/2026-11-13", self.remote_tags())

    def test_连不上远端_试三次后出错(self):
        a = self.clone("run1")
        sh("git", "remote", "set-url", "origin", str(self.root / "没有这个仓库.git"), cwd=a)
        rc, msg = self.run_claim(a, "claim", "--tag", "issue/2026-11-14", "--wait", "0")
        self.assertEqual(rc, 2, msg)
        self.assertIn("失败 3 次", msg)

    def test_标签名不对_出错(self):
        a = self.clone("run1")
        self.assertEqual(self.run_claim(a, "claim", "--tag", "issue/bad..name")[0], 2)
        self.assertEqual(self.run_claim(a, "release", "--tag", "issue/2026-11-14", "--expect", "abc")[0], 2)


def jobs(*steps, issue=True, claim=True):
    js = []
    if claim:
        js.append({"name": "claim", "status": "completed", "conclusion": "success", "steps": []})
    if issue:
        js.append({"name": "issue", "status": "completed", "conclusion": "failure",
                   "steps": [{"name": n, "status": st, "conclusion": co} for n, st, co in steps]})
    js.append({"name": "收尾：第 4 步以前出错就放回认领", "status": "in_progress", "conclusion": None, "steps": []})
    return {"total_count": len(js), "jobs": js}


STEP4 = "第 4–9 步：选题到改稿（claude -p）"


class Step4Test(unittest.TestCase):
    def test_第1到3步出错_第4步跳过_算没开始(self):
        d = jobs(("第 1–3 步：抓取、粗筛归并、入库", "completed", "failure"), (STEP4, "completed", "skipped"))
        self.assertFalse(C.step4_started(d))

    def test_第4步跑过_不管成败都算开始(self):
        for co in ("success", "failure", "cancelled"):
            self.assertTrue(C.step4_started(jobs((STEP4, "completed", co))), co)
        self.assertTrue(C.step4_started(jobs((STEP4, "in_progress", None))))

    def test_排队时被取消_一步都没跑_算没开始(self):
        self.assertFalse(C.step4_started(jobs()))
        self.assertFalse(C.step4_started(jobs(issue=False)))
        self.assertFalse(C.step4_started(jobs((STEP4, "pending", None))))

    def test_job_输出说开始了_就算开始(self):
        self.assertTrue(C.step4_started(jobs((STEP4, "completed", "skipped")), stage4="started"))

    def test_认不出来就报错_调用方按开始了处理(self):
        with self.assertRaises(ValueError):
            C.step4_started({"message": "Bad credentials"})
        with self.assertRaises(ValueError):
            C.step4_started(jobs(claim=False))

    def test_命令行(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "jobs.json"
            f.write_text(json.dumps(jobs((STEP4, "completed", "skipped"))), encoding="utf-8")
            p = subprocess.run([sys.executable, str(SCRIPT), "started", "--jobs-json", str(f)], capture_output=True, text=True)
            self.assertEqual((p.returncode, p.stdout.strip()), (0, "not-started"))
            f.write_text("{}", encoding="utf-8")
            p = subprocess.run([sys.executable, str(SCRIPT), "started", "--jobs-json", str(f)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)

    def test_工作流里第4步的名字和这里一致(self):
        wf = (HERE.parents[2] / ".github" / "workflows" / "frontier-daily.yml").read_text(encoding="utf-8")
        self.assertIn("- name: " + C.STEP4_PREFIX, wf)
        self.assertIn("  %s:\n" % C.ISSUE_JOB, wf)


if __name__ == "__main__":
    unittest.main()
