"""fd doctor：体检。只查不改，每项给"好了／缺了／怎么补"；不显示任何密钥内容（只看有没有）。"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .common import (ROOT, PIPE, PY, VENV, CACHE, PLAYWRIGHT, PROFILE, TESTDIR, DEFAULT_LEDGER, SWITCH_FILE, tts_constants, read_json, rel,
                     motion_switch, director_switch, zh_wrap_switch)
from .ledger import Ledger

OK, BAD, WARN = "✓ 好了", "✗ 缺了", "! 提醒"

PACKAGES = [  # (import 名, 给人看的名字, 哪一步用)
    ("feedparser", "feedparser", "抓取"), ("httpx", "httpx", "抓取"), ("bs4", "beautifulsoup4", "抓取"), ("lxml", "lxml", "抓取"),
    ("yaml", "pyyaml", "多处"), ("numpy", "numpy", "多处"), ("scipy", "scipy", "配音、混音"),
    ("sentence_transformers", "sentence-transformers", "归并"), ("torch", "torch", "归并、音色把关"),
    ("trafilatura", "trafilatura", "事件卡取正文"), ("requests", "requests", "配音"), ("certifi", "certifi", "联网"),
    ("pypinyin", "pypinyin", "对稿"), ("opencc", "opencc", "对稿"),
    ("speechbrain", "speechbrain", "音色把关"), ("torchaudio", "torchaudio", "音色把关"),
    ("PIL", "Pillow", "网页、视频"), ("fontTools", "fonttools", "字体子集"), ("brotli", "brotli", "字体子集"),
    ("budoux", "budoux", "中文断行"), ("jieba", "jieba", "中文断行"),
]


def _run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return 127, "", "找不到"
    except subprocess.TimeoutExpired:
        return 124, "", "超时"
    except OSError as e:
        return 1, "", str(e)


class Doctor:
    def __init__(self):
        self.rows = []

    def add(self, mark, what, detail="", fix=""):
        self.rows.append((mark, what, detail, fix))
        line = "%s｜%s%s" % (mark, what, "：" + detail if detail else "")
        print(line)
        if fix and mark != OK:
            print("        怎么补：" + fix)

    # ------------------------------------------------------------ 各项
    def python(self):
        if not PY.exists():
            self.add(BAD, "Python 环境", "没有 %s" % rel(PY), "uv venv ~/.venvs/frontier-daily --python 3.12，再按 README 装依赖")
            return
        rc, out, err = _run([str(PY), "--version"])
        self.add(OK, "Python 环境", "%s（%s）" % ((out or err).strip(), rel(VENV)))
        code = ("import importlib.util as u, importlib.metadata as m, json\n"
                "out={}\n"
                "for imp, dist in %r:\n"
                "  s=u.find_spec(imp)\n"
                "  v=None\n"
                "  if s:\n"
                "    try: v=m.version(dist)\n"
                "    except Exception: v='在'\n"
                "  out[imp]=v\n"
                "print(json.dumps(out))") % ([(i, d) for i, d, _ in PACKAGES],)
        rc, out, err = _run([str(PY), "-c", code], timeout=60)
        try:
            got = json.loads(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            self.add(BAD, "关键包", "查不了：%s" % (err or out)[-120:])
            return
        miss = [(d, w) for i, d, w in PACKAGES if not got.get(i)]
        have = ["%s %s" % (d, got[i]) for i, d, _ in PACKAGES if got.get(i) and i in ("speechbrain", "torch", "sentence_transformers", "budoux", "jieba")]
        if miss:
            self.add(BAD, "关键包", "缺 " + "、".join("%s（%s）" % m for m in miss),
                     "uv pip install --python %s %s" % (rel(PY), " ".join(d for d, _ in miss)))
        else:
            self.add(OK, "关键包", "%d 个都在（%s）" % (len(PACKAGES), "、".join(have)))

    def tools(self):
        for name, fix in (("ffmpeg", "brew install ffmpeg"), ("ffprobe", "brew install ffmpeg"), ("node", "装 Node.js 22（nodejs.org）")):
            p = shutil.which(name)
            if not p:
                self.add(BAD, name, "找不到", fix)
                continue
            rc, out, err = _run([p, "-version" if name.startswith("ff") else "--version"])
            first = (out or err).splitlines()[0] if (out or err) else ""
            m = re.search(r"version (\S+)", first)
            ver = m.group(1) if m else first[:40]
            self.add(OK, name, "%s（%s）" % (ver, p))
        # 苹果电脑上是 /Applications 里的 Chrome；云端（Linux）装的是 google-chrome（11-09 晚改：原来只认苹果的位置，云端每次误报）
        mac_chrome = Path("/Applications/Google Chrome.app")
        chrome = str(mac_chrome) if mac_chrome.exists() else next(
            (shutil.which(n) for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser") if shutil.which(n)), None)
        self.add(OK if chrome else BAD, "Chrome", chrome or "没装",
                 "装 Google Chrome（验收截图、录视频预览用本机 Chrome）")
        self.add(OK if PLAYWRIGHT.exists() else BAD, "Playwright（截图、验收用）", rel(PLAYWRIGHT) if PLAYWRIGHT.exists() else "npx 缓存里没有",
                 "npx -y playwright@1 --version 让它装进 npx 缓存，再改 pipeline/orchestrator/common.py 的 PLAYWRIGHT 路径")
        wb = Path.home() / ".venvs/digital-human/bin/mlx_whisper"
        wm = Path.home() / ".cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo"
        env_bin = os.environ.get("FD_WHISPER_BIN")      # 别的机器（云端是 Linux 替身，内部 faster-whisper）用它指转写命令，同 pipeline/tts_qc.py
        if env_bin:
            ok = Path(env_bin).exists()
            self.add(OK if ok else BAD, "Whisper（对稿、对齐）", "FD_WHISPER_BIN 指的 %s%s" % (env_bin, "" if ok else "：不在"),
                     "检查环境变量 FD_WHISPER_BIN（云端见 cloud/whisper_standin/）")
        elif wb.exists() and wm.exists():
            self.add(OK, "Whisper（对稿、对齐）", "mlx_whisper＋whisper-large-v3-turbo（本机）")
        else:
            self.add(BAD, "Whisper（对稿、对齐）", "缺 %s" % ("程序" if not wb.exists() else "模型"),
                     "见 pipeline/tts_qc.py 开头：mlx_whisper 装在 ~/.venvs/digital-human，模型 mlx-community/whisper-large-v3-turbo")
        lb = Path.home() / ".cache/huggingface/hub/models--sentence-transformers--LaBSE"
        self.add(OK if lb.exists() else BAD, "LaBSE（归并用的句向量模型）", "已缓存" if lb.exists() else "没缓存",
                 "联网时运行一次 pipeline/cluster.py 会自动下载（约 1.8 GB）")

    def gcloud(self):
        k = tts_constants()
        g = os.path.expanduser(k.get("GCLOUD") or shutil.which("gcloud") or "gcloud")
        # 配音账号不进仓库：本机写在环境变量 FD_GCP_ACCOUNT 里（tts_engines.py 同样读它），没设就按 gcloud 当前的默认账号
        want, proj, forbidden = os.environ.get("FD_GCP_ACCOUNT") or k.get("GCP_ACCOUNT"), k.get("GCP_PROJECT"), tuple(k.get("FORBIDDEN_PROJECTS") or ())
        if proj in forbidden:
            self.add(BAD, "配音用的 Google 项目", "%s 在禁用名单里（留给大论文）" % proj, "改 pipeline/tts_engines.py 的 GCP_PROJECT")
        else:
            self.add(OK, "配音用的 Google 项目", "%s（不是禁用的 %s）" % (proj, "、".join(forbidden)))
        if os.environ.get("GITHUB_ACTIONS") == "true" and not shutil.which(g):
            # 云端不装 gcloud：配音时用 GitHub 给的身份换一小时的临时令牌（环境变量 GCP_ACCESS_TOKEN，只给配音那几步），不靠 gcloud 登录
            self.add(OK, "gcloud 登录", "云端不用 gcloud：配音用临时令牌（GCP_ACCESS_TOKEN，只在配音那几步有）")
            return
        rc, out, err = _run([g, "auth", "list", "--format=json"], timeout=30)
        if rc != 0:
            self.add(BAD, "gcloud 登录", "gcloud 跑不了（%s）" % (err.strip()[-80:] or rc), "装 Google Cloud SDK 并 gcloud auth login %s" % want)
            return
        try:
            accts = json.loads(out or "[]")
        except ValueError:
            accts = []
        names = [a.get("account") for a in accts]
        active = [a.get("account") for a in accts if a.get("status") == "ACTIVE"]
        if not want:
            self.add(WARN if not active else OK, "gcloud 登录", "没设 FD_GCP_ACCOUNT：配音按 gcloud 当前的默认账号取令牌（%s）" % ("、".join(active) or "没有默认账号"),
                     "要指定账号：export FD_GCP_ACCOUNT=<主账号>")
        elif want in names:
            self.add(OK, "gcloud 登录", "配音账号 %s 已登录%s" % (want, "" if want in active else "（当前默认账号是 %s；配音程序按账号取令牌，不受影响）" % "、".join(active)))
        else:
            self.add(BAD, "gcloud 登录", "配音账号 %s 没登录（已登录：%s）" % (want, "、".join(names) or "无"), "gcloud auth login %s" % want)
        rc, out, err = _run([g, "config", "get-value", "project"], timeout=30)
        cur = (out or "").strip()
        if cur in forbidden:
            self.add(WARN, "gcloud 默认项目", "%s 是禁用的那个；配音程序自己指定项目、每次请求前都查，不会用它，但手动敲 gcloud 命令时要小心" % cur,
                     "gcloud config set project %s" % proj)
        else:
            self.add(OK, "gcloud 默认项目", cur or "（没设）")

    def keychain(self):
        k = tts_constants()
        name = k.get("GEMINI_API_KEYCHAIN") or "frontier-daily-gemini"
        if sys.platform != "darwin":                # 钥匙串只有苹果电脑有；云端（Linux）没有，现行配音也不靠它
            self.add(OK, "钥匙串 %s" % name, "不是苹果电脑，没有钥匙串，跳过（现行配音走 Vertex，不靠它）")
            return
        # 不加 -w／-g：只查这一项在不在，不读密码本身；输出全部丢掉
        try:
            rc = subprocess.run(["security", "find-generic-password", "-s", name], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=15).returncode
        except (OSError, subprocess.TimeoutExpired):
            rc = 1
        if rc == 0:
            self.add(OK, "钥匙串 %s" % name, "在（Gemini API 那条路的密钥；只查了有没有）")
        else:
            self.add(WARN, "钥匙串 %s" % name, "没找到；现行配音走 Vertex（gcloud 令牌），不靠它，只有改用 --engine gemini-api 时才要",
                     "security add-generic-password -s %s -a <账号> -w（在终端里自己输，别贴进对话）" % name)

    def mimo(self):
        rc, out, err = _run([str(PY), str(PIPE / "keys.py")], timeout=30)
        txt = out + err
        ok = re.search(r"变量就位：\s*\{.*'MIMO_API_KEY': True.*'MIMO_BASE_URL': True", txt)
        kind = re.search(r"密钥类型：\s*(.+)", txt)
        host = re.search(r"地址主机：\s*(.+)", txt)
        if ok:
            self.add(OK, "MiMo 密钥", "在（%s，地址 %s；keys.py 自检，不显示值）" % (kind.group(1).strip() if kind else "?", host.group(1).strip() if host else "?"))
        else:
            self.add(BAD, "MiMo 密钥", "没读到（%s）" % ((txt.strip().splitlines() or ["?"])[-1][:80]),
                     "在知识库 .env 里写 MIMO_API_KEY、MIMO_BASE_URL（见 pipeline/keys.py 开头）")

    def agents(self):
        for name, use in (("claude", "主笔（以后 claude -p 自动写稿）"), ("codex", "配图后备（agy 不能用或画得不合格时）")):
            p = shutil.which(name)
            if not p:
                self.add(BAD, "%s 命令" % name, "找不到（%s）" % use, "npm i -g %s" % ("@anthropic-ai/claude-code" if name == "claude" else "@openai/codex"))
                continue
            rc, out, err = _run([p, "--version"], timeout=20)
            self.add(OK, "%s 命令" % name, "%s（%s）" % ((out or err).strip().splitlines()[0][:40] if (out or err).strip() else "在", use))
        self.agy()

    def agy(self):
        """配图先用的 agy（Google AI Pro 订阅）：装了没有、登录了没有、额度还有没有。只提醒、不算"缺了"——不能用时配图自动走 Codex。"""
        tool = ROOT / "site/tools/agy_image.py"
        rc, out, err = _run([str(PY), str(tool), "--check"], timeout=150)
        txt = (out + err).strip()
        line = next((x.strip() for x in txt.splitlines() if x.strip()[:1] in ("✓", "✗")), txt[-120:]).lstrip("✓✗ ").strip()
        if rc == 0:
            gem = re.findall(r"Gemini Models (weekly|5h) 剩 ([\d.]+%)", line)
            self.add(OK, "agy（配图先用它）", "已登录；Gemini 额度 %s" % ("，".join("%s 剩 %s" % (w, v) for w, v in gem) or line[:80]))
            return
        why = {3: "额度用完", 4: "没登录或登录过期", 7: "没装", 124: "检查超时"}.get(rc, "检查出错（退出码 %s）" % rc)
        fix = {3: "等额度刷新（5 小时或每周），这期间配图自动走 Codex", 4: "用户本人在终端运行一次 agy 重新登录",
               7: "装 Antigravity CLI（agy），或者就只用 Codex"}.get(rc, "看 site/tools/agy_image.py --check 的输出")
        self.add(WARN, "agy（配图先用它）", "%s：%s；配图会改走 Codex，不挡出刊" % (why, line[:100]), fix)

    def voices(self):
        prof = read_json(PROFILE, None)
        if not prof:
            self.add(BAD, "声音档案", "pipeline/voice_profile.json 读不出来", "从备份恢复")
            return
        ov = prof.get("声音一览") or {}
        refs, miss = [], []
        for who in ("Shirley", "Dylan"):
            for tier in ("备用", "再备用"):
                ref = ((ov.get(who) or {}).get(tier) or {}).get("参考音")
                if ref:
                    (refs if (ROOT / ref).exists() else miss).append(ref)
        fp_dir = PIPE / "assets/voices/音色指纹"
        fps = sorted({p.stem for p in fp_dir.glob("*.npy")}) if fp_dir.is_dir() else []
        model = CACHE / "models/spkrec-ecapa-voxceleb"
        pk = PIPE / "assets/music/v3/包.json"
        if miss:
            self.add(BAD, "声音档案", "参考音缺 %s" % "、".join(miss), "从 配音测试/ 或备份里放回")
        else:
            self.add(OK, "声音档案", "Shirley 主用 %s、Dylan 主用 %s；MiMo 复刻参考音 %d 条都在" % (
                ((ov.get("Shirley") or {}).get("主用") or {}).get("声音ID", "?")[:14] + "…",
                ((ov.get("Dylan") or {}).get("主用") or {}).get("声音ID", "?")[:14] + "…", len(refs)))
        self.add(OK if fps else BAD, "音色指纹档案", "%d 个声音（%s）" % (len(fps), "、".join(fps)) if fps else "没有",
                 "$PY pipeline/voice_print.py build-refs")
        self.add(OK if model.exists() else WARN, "音色模型（SpeechBrain ECAPA）", rel(model) if model.exists() else "没缓存",
                 "联网时配一次音会自动下载；没有它照常配音，只是音色把关记'未判'")
        self.add(OK if pk.exists() else BAD, "声音包 v3", rel(pk) if pk.exists() else "没有", "从备份恢复 pipeline/assets/music/v3/")

    def switch(self):
        """新动效总开关（11-07 加）：只报现在是开是关、从哪来的；fd_开关.json 写坏了提醒。"""
        on, why = motion_switch()
        raw = None
        if SWITCH_FILE.exists():
            try:
                raw = json.loads(SWITCH_FILE.read_text(encoding="utf-8"))
            except ValueError:
                raw = False
        if raw is False:
            self.add(WARN, "新动效和原文截图（开关）", "fd_开关.json 不是合法的 JSON，按“开”", "照 文档/方案/每日自动运行.md'出错怎么办'里的写法改好")
            return
        self.add(OK, "新动效和原文截图（开关）", "%s（%s）%s" % ("开" if on else "关", why,
                                                  "" if on else "：视频按 11-06 以前的画法出、第 14 步不截图"))
        don, dwhy = director_switch()          # 11-08 晚加：视频导演开关；开着时看一眼 claude 命令在不在（只查有没有，不调用）
        has = bool(shutil.which("claude"))
        self.add(OK if (not don or has) else WARN, "视频导演（开关）", "%s（%s）%s" % (
            "开" if don else "关", dwhy, ("；claude 命令在" if has else "；找不到 claude 命令，第 14 步会退回老路") if don else ""),
            "" if (not don or has) else "装 Claude Code 并登录订阅，或把 fd_开关.json 的“视频导演”改成“关”")
        zon, zwhy = zh_wrap_switch()           # 11-09 晚加：视频中文整词换行开关（断行工具 budoux、jieba 在上面的软件检查里）
        self.add(OK, "视频中文整词换行（开关）", "%s（%s）%s" % ("开" if zon else "关", zwhy, "" if zon else "：视频文字按加开关以前的办法换行"))

    def disk(self):
        u = shutil.disk_usage(str(Path.home()))
        free = u.free / 1e9
        mark = OK if free >= 10 else WARN if free >= 5 else BAD
        self.add(mark, "磁盘剩余", "%.1f GB" % free, "清缓存：~/.cache/frontier-daily/ 里的试验中间文件（配音分块缓存别删，重跑靠它不花钱）")

    def ledger(self):
        lg = Ledger(DEFAULT_LEDGER, TESTDIR / "_doctor", "doctor", dry_run=True)
        st = lg.status()
        if not lg.month_file.exists():
            self.add(OK, "本月 Gemini 花费", "账本还没有（fd 第一次配音时自动建在 %s）；上限 $%.2f" % (rel(lg.month_file), st["上限美元"]))
        else:
            mark = WARN if st["到90%"] else OK
            self.add(mark, "本月 Gemini 花费", "已记 $%.2f / 上限 $%.2f（%.0f%%）%s" % (
                st["Gemini已记美元"], st["上限美元"], 100 * st["比例"], "，到 90% 了：配音会走 MiMo 备用" if st["到90%"] else ""))
        print("        （只算经 fd 跑的；fd 上线前手动跑的没记进来）")

    def run(self):
        print("fd doctor：只查不改，不显示密钥\n")
        for part in (self.python, self.tools, self.gcloud, self.keychain, self.mimo, self.agents, self.voices, self.switch, self.disk, self.ledger):
            try:
                part()
            except Exception as e:      # noqa: BLE001  一项查不了不影响别的
                self.add(BAD, part.__name__, "体检程序出错：%s" % e)
        bad = sum(1 for r in self.rows if r[0] == BAD)
        warn = sum(1 for r in self.rows if r[0] == WARN)
        print("\n共 %d 项：好了 %d，缺了 %d，提醒 %d" % (len(self.rows), len(self.rows) - bad - warn, bad, warn))
        return 1 if bad else 0


def main():
    return Doctor().run()
