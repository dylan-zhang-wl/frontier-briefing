#!/usr/bin/env python3
"""cloud/remote_images.py 的测试（2026-11-11 加）：视频导演半路要新图时叫私有仓库画。

用假的 gh（发行版放在临时文件夹里；"叫配图"时当场按私有仓库那样 serve、查登录和额度、打包）和假的 codex（写一张 1×1 的图），
不联网、不调 Codex、不花钱。也查：令牌只交给 gh、不带别的变量；video3_images 在 FD_IMAGE_BACKENDS=remote 时整批走远程；
视频导演的 claude -p 环境里没有 MiMo、Gemini、远程画图的钥匙。

用法（在项目根运行）：python3 -m unittest discover -s cloud/tests -v
"""
import base64
import io
import json
import os
import stat
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))
sys.path.insert(0, str(ROOT / "site/tools"))
import remote_images as RI  # noqa: E402
import video3_images as V  # noqa: E402

PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

FAKE_CODEX = '''#!/bin/sh
# 假 codex：codex exec --skip-git-repo-check -s workspace-write -C <目录> <提示词>
dir="$6"; prompt="$7"
name=$(printf '%s' "$prompt" | grep -o '[A-Za-z0-9_.-]*\\.png' | head -1)
case "$name" in
  *fail*) echo "ERROR: You've hit your usage limit." >&2; exit 1 ;;
esac
printf '%s' "{png}" | base64 -d > "$dir/$name"
echo "tokens used"; echo "1,234"
'''

FAKE_GH = '''#!{py}
# 假 gh：发行版是 {store}/<发行版名>/ 文件夹；"workflow run" 当场照私有仓库 images.yml 的 director 那几步做
import json, os, shutil, subprocess, sys, tarfile
from pathlib import Path
store, root, log = Path({store!r}), Path({root!r}), Path({log!r})
a = sys.argv[1:]
with log.open("a") as fh:
    fh.write(json.dumps({{"argv": a, "env": sorted(os.environ)}}) + "\\n")
if os.environ.get("GH_TOKEN") != "fake-token":
    sys.exit(4)
def opt(k):
    return a[a.index(k) + 1] if k in a else None
if a[:2] == ["release", "view"]:
    d = store / a[2]
    if not d.is_dir():
        sys.exit(1)
    if opt("--json") == "assets":
        print("\\n".join(sorted(p.name for p in d.iterdir())))
    sys.exit(0)
if a[:2] == ["release", "create"]:
    (store / a[2]).mkdir(parents=True, exist_ok=True); sys.exit(0)
if a[:2] == ["release", "upload"]:
    d = store / a[2]
    if not d.is_dir():
        sys.exit(1)
    shutil.copy(a[-1], d / Path(a[-1]).name); sys.exit(0)
if a[:2] == ["release", "download"]:
    shutil.copy(store / a[2] / opt("-p"), Path(opt("-D")) / opt("-p")); sys.exit(0)
if a[:2] == ["workflow", "run"]:
    if (store / "NOSERVE").exists():
        sys.exit(0)
    f = dict(x.split("=", 1) for x in a[a.index("-f") + 1::2] if "=" in x)
    rel = store / ("run-" + f["run_id"]); req = f["req"]
    work = store / "_private"; out = work / "视频"
    shutil.rmtree(work, ignore_errors=True); work.mkdir()
    shutil.copy(rel / req, work / req)
    env = dict(os.environ, PATH={bindir!r} + os.pathsep + os.environ["PATH"])
    subprocess.run([sys.executable, str(root / "cloud/remote_images.py"), "serve", str(work / req), str(out)], env=env,
                   stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(root / "cloud/codex_login_check.py"), str(out), "--out", str(out / "codex_登录失效.txt")],
                   stdout=subprocess.DEVNULL)
    ans = req.replace("director-req-", "director-img-")[:-len(".json")] + ".tar.gz"
    with tarfile.open(rel / ans, "w:gz") as tf:
        tf.add(out, arcname=".")
    sys.exit(0)
sys.exit(2)
'''


def make_exec(p, text):
    p.write_text(text, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


REQS = [{"id": "v_lab", "placement": "tile", "events": ["E001"], "brief_en": "a quiet lab bench at dawn"},
        {"id": "v_rack", "placement": "tile", "brief_en": "a row of server racks", "context_en": "a new data centre opened"}]


class Base(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        t = Path(self.td.name)
        self.store, self.bin, self.log = t / "store", t / "bin", t / "gh.log"
        self.store.mkdir()
        (self.store / "run-123").mkdir()
        self.bin.mkdir()
        make_exec(self.bin / "codex", FAKE_CODEX.replace("{png}", PNG))
        make_exec(self.bin / "gh", FAKE_GH.format(py=sys.executable, store=str(self.store), root=str(ROOT), log=str(self.log),
                                                 bindir=str(self.bin)))
        self.issue = t / "渲染"
        self.d = self.issue / V.DIR
        self.env = mock.patch.dict(os.environ, {
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
            "FD_REMOTE_IMAGES_TOKEN": "fake-token", "FD_REMOTE_IMAGES_REPO": "owner/private", "FD_REMOTE_IMAGES_RUN": "123",
            "FD_REMOTE_IMAGES_SHA": "abc1234", "FD_REMOTE_IMAGES_DAY": "2026-11-20", "FD_REMOTE_IMAGES_WAIT": "30",
            "FD_REMOTE_IMAGES_MAX": "", "MIMO_API_KEY": "should-not-leak"})
        self.env.start()
        self.poll = mock.patch.object(RI, "POLL", 0)
        self.poll.start()

    def tearDown(self):
        self.poll.stop()
        self.env.stop()
        self.td.cleanup()

    def draw(self, reqs):
        with redirect_stdout(io.StringIO()) as out:
            res = RI.draw(self.d, reqs, "blue")
        return {r["id"]: x for r, x in res}, out.getvalue()

    def gh_calls(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []


class DrawTest(Base):
    def test_both_drawn_and_copied(self):
        res, out = self.draw(REQS)
        self.assertTrue(res["v_lab"]["ok"] and res["v_rack"]["ok"], res)
        self.assertEqual(res["v_lab"]["backend"], "codex")
        for rid in ("v_lab", "v_rack"):
            self.assertTrue((self.d / (rid + ".png")).stat().st_size > 0)
            self.assertTrue((self.d / ("log_%s.png.txt" % rid)).exists())
        self.assertIn("画回来 2/2 张", out)
        run = [c for c in self.gh_calls() if c["argv"][:2] == ["workflow", "run"]][0]["argv"]
        self.assertIn("mode=director", run)
        self.assertIn("sha=abc1234", run)
        req = json.loads(next((self.store / "run-123").glob("director-req-*.json")).read_text(encoding="utf-8"))
        self.assertEqual(req["accent"], "blue")
        self.assertEqual([r["id"] for r in req["reqs"]], ["v_lab", "v_rack"])

    def test_token_only_goes_to_gh(self):
        self.draw(REQS[:1])
        calls = self.gh_calls()
        self.assertTrue(calls)
        for c in calls:
            self.assertLessEqual(set(c["env"]) - {"PATH", "HOME", "LANG", "GH_TOKEN", "GH_PROMPT_DISABLED", "PWD", "SHLVL", "_",
                                                  "__CF_USER_TEXT_ENCODING", "LC_CTYPE"}, set(), c["env"])
            self.assertNotIn("MIMO_API_KEY", c["env"])
            self.assertNotIn("FD_REMOTE_IMAGES_TOKEN", c["env"])

    def test_quota_failure_noted(self):
        res, out = self.draw([REQS[0], {"id": "v_fail", "placement": "tile", "brief_en": "x"}])
        self.assertTrue(res["v_lab"]["ok"])
        self.assertFalse(res["v_fail"]["ok"])
        self.assertIn("额度用完", res["v_fail"]["note"])
        self.assertFalse((self.d / "v_fail.png").exists())
        self.assertIn("画回来 1/2 张", out)

    def test_max_one_in_test_runs(self):
        os.environ["FD_REMOTE_IMAGES_MAX"] = "1"
        res, _ = self.draw(REQS)
        self.assertTrue(res["v_lab"]["ok"])
        self.assertFalse(res["v_rack"]["ok"])
        self.assertIn("最多远程画 1 张", res["v_rack"]["note"])
        req = json.loads(next((self.store / "run-123").glob("director-req-*.json")).read_text(encoding="utf-8"))
        self.assertEqual(len(req["reqs"]), 1)

    def test_not_configured_calls_nothing(self):
        os.environ["FD_REMOTE_IMAGES_TOKEN"] = ""
        res, out = self.draw(REQS)
        self.assertFalse(any(x["ok"] for x in res.values()))
        self.assertIn("没配好", out)
        self.assertEqual(self.gh_calls(), [])

    def test_timeout_falls_back(self):
        (self.store / "NOSERVE").write_text("")
        os.environ["FD_REMOTE_IMAGES_WAIT"] = "0"
        res, out = self.draw(REQS[:1])
        self.assertFalse(res["v_lab"]["ok"])
        self.assertIn("没画回来", res["v_lab"]["note"])
        self.assertFalse((self.d / "v_lab.png").exists())

    def test_creates_release_if_missing(self):
        os.rmdir(self.store / "run-123")
        res, _ = self.draw(REQS[:1])
        self.assertTrue(res["v_lab"]["ok"])


class EnsureTest(Base):
    def test_backends(self):
        for raw, want in (("remote", ["remote"]), ("remote,codex", ["remote"]), ("codex", ["codex"]), ("agy,codex", ["agy", "codex"])):
            with mock.patch.dict(os.environ, {"FD_IMAGE_BACKENDS": raw}):
                self.assertEqual(V.image_backends(), want)
        with mock.patch.dict(os.environ):
            os.environ.pop("FD_IMAGE_BACKENDS", None)
            self.assertEqual(V.image_backends(), ["agy", "codex"])

    def test_ensure_uses_remote_in_one_batch(self):
        with mock.patch.dict(os.environ, {"FD_IMAGE_BACKENDS": "remote"}), redirect_stdout(io.StringIO()):
            meta = V.ensure(self.issue, REQS, "blue", gen=True)
        self.assertEqual(meta["v_lab"]["kind"], "generated")
        self.assertEqual(meta["v_lab"]["backend"], "codex")
        self.assertEqual(len([c for c in self.gh_calls() if c["argv"][:2] == ["workflow", "run"]]), 1)
        rec = (self.d / "提示词记录.md").read_text(encoding="utf-8")
        self.assertIn("`v_lab.png`", rec)
        self.assertIn("Codex，用量", rec)
        # 第二次：图都在了，不再叫私有仓库
        with mock.patch.dict(os.environ, {"FD_IMAGE_BACKENDS": "remote"}), redirect_stdout(io.StringIO()):
            V.ensure(self.issue, REQS, "blue", gen=True)
        self.assertEqual(len([c for c in self.gh_calls() if c["argv"][:2] == ["workflow", "run"]]), 1)


class DirectorEnvTest(unittest.TestCase):
    def test_claude_env_has_no_other_keys(self):
        import video3_director as VD
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            dump = t / "env.json"
            fake = t / "claude"
            make_exec(fake, "#!%s\nimport json, os, sys\njson.dump(sorted(os.environ), open(%r, 'w'))\nprint('{}')\n" % (sys.executable, str(dump)))
            keys = {"MIMO_API_KEY": "m", "MIMO_BASE_URL": "u", "GCP_ACCESS_TOKEN": "g", "FD_REMOTE_IMAGES_TOKEN": "r",
                    "GH_TOKEN": "h", "GITHUB_TOKEN": "t", "ANTHROPIC_API_KEY": "a", "CLAUDE_CODE_OAUTH_TOKEN": "c"}
            with mock.patch.dict(os.environ, keys), mock.patch.object(VD.shutil, "which", return_value=str(fake)), \
                    redirect_stdout(io.StringIO()):
                try:
                    VD.run_claude(t, "hi", 120, "测试")
                except Exception:  # noqa: BLE001  这里只看传给 claude 的环境
                    pass
            env = set(json.loads(dump.read_text()))
        self.assertIn("CLAUDE_CODE_OAUTH_TOKEN", env)
        for k in keys:
            if k != "CLAUDE_CODE_OAUTH_TOKEN":
                self.assertNotIn(k, env)


if __name__ == "__main__":
    unittest.main()
