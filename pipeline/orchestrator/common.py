"""总调度的共用部分：路径、版别、每期状态、锁、内容指纹、跑子程序。只用标准库。"""
import ast
import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------- 路径
ROOT = Path(__file__).resolve().parents[2]            # 项目根 frontier-daily/
PIPE = ROOT / "pipeline"
TOOLS = ROOT / "site" / "tools"
PROMPTS = PIPE / "prompts"
TESTDIR = ROOT / "测试版"
DEFAULT_DB = TESTDIR / "往期事件库"
DEFAULT_LEDGER = TESTDIR / "月度账本"
VENV = Path.home() / ".venvs" / "frontier-daily"
PY = VENV / "bin" / "python"
CACHE = Path.home() / ".cache" / "frontier-daily"
LOCKS = CACHE / "locks"                                # 锁放在本机缓存里，不进 iCloud
# FD_PLAYWRIGHT：playwright 包目录（云端等别的机器用；没设时和原来一样，用本机 npx 缓存）
PLAYWRIGHT = Path(os.environ.get("FD_PLAYWRIGHT") or Path.home() / ".npm/_npx/9833c18b2d85bc59/node_modules/playwright")
PROFILE = PIPE / "voice_profile.json"
HELPERS = PIPE / "orchestrator" / "helpers.py"
UTC = timezone.utc

# ---------------------------------------------------------------- 状态的叫法（给人看的）
DONE, FAILED, SKIPPED, WAITING, TODO, RUNNING = "做完", "失败", "跳过", "等人", "没做", "在跑"


def now_utc():
    return datetime.now(UTC)


def stamp(dt=None):
    """给人看的本机时间（读系统时钟）。"""
    return (dt or datetime.now().astimezone()).strftime("%Y-%m-%d %H:%M:%S %Z")


def iso(dt=None):
    return (dt or now_utc()).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    s = (s or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def rel(p, base=None):
    """尽量写成相对路径，好读。"""
    p = Path(p)
    for b in ([base] if base else []) + [ROOT, Path.home()]:
        try:
            r = p.resolve().relative_to(Path(b).resolve())
            return ("~/" + str(r)) if Path(b) == Path.home() else str(r)
        except ValueError:
            continue
    return str(p)


def read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return default


def write_json(p, obj):
    """先写临时文件再换名，写到一半断电也不会留下坏文件。"""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=str(p.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def write_text(p, text):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=p.suffix or ".txt", dir=str(p.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, p)


# ---------------------------------------------------------------- 从现有程序里读常量（不 import，免得带进依赖；它们改了这里自动跟着变）
def read_constants(path, names):
    out = {}
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return out
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in names:
                    try:
                        out[t.id] = ast.literal_eval(node.value)
                    except ValueError:
                        pass
    return out


def frozen_editions():
    """已冻结的两期按当时的版别（run_mimo.py 的 FROZEN_EDITION）。"""
    c = read_constants(PIPE / "run_mimo.py", {"FROZEN_EDITION"})
    return c.get("FROZEN_EDITION") or {"2026-10-31": "weekday", "2026-11-01": "sunday_dialog"}


def tts_constants():
    return read_constants(PIPE / "tts_engines.py", {
        "GCP_PROJECT", "GCP_ACCOUNT", "FORBIDDEN_PROJECTS", "GCLOUD", "GEMINI_API_KEYCHAIN", "AUDIO_TOKENS_PER_SEC"})


def gemini_price_out():
    """Gemini 3.8 Flash TTS 音频输出单价（美元 / 百万 token），从 tts_engines.py 的价目表读，只用来估钱。"""
    try:
        tree = ast.parse((PIPE / "tts_engines.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PRICES" for t in node.targets):
                d = node.value
                for v in d.values:                       # 第一项是 Flash
                    table = ast.literal_eval(v)
                    year = "2027" if date.today().isoformat() >= "2027-01-01" else "2026"
                    return float(table[year][1])
    except (OSError, SyntaxError, ValueError, KeyError, IndexError):
        pass
    return 9.0


# ---------------------------------------------------------------- 新动效总开关（2026-11-07 并入正式流程时加）
# 开（默认）：第 14 步组装视频前给分镜里的原文截图截图，分镜里写了的新动效照画。
# 关：不截图，组装时去掉新块和新字段（video3_storyboard.strip_motion），视频退回 11-06 以前的画法。
# 先看环境变量 FD_MOTION（只管这一次，比如 FD_MOTION=off ./fd run …），再看项目根的 fd_开关.json；都没有或读不出来按"开"。
# site/tools/video3_storyboard.py 的 motion_switch 是同一套规则（那边组装时用），两边要一起改。
SWITCH_FILE = ROOT / "fd_开关.json"
SWITCH_KEY = "新动效和原文截图"
_OFF = ("off", "0", "false", "no", "关", "关闭", "关掉")
_ON = ("on", "1", "true", "yes", "开", "打开")


def motion_switch():
    """返回 (开着没有, 从哪来的一句话)。"""
    env = str(os.environ.get("FD_MOTION") or "").strip().lower()
    if env in _OFF:
        return False, "环境变量 FD_MOTION=%s" % env
    if env in _ON:
        return True, "环境变量 FD_MOTION=%s" % env
    try:
        v = str(json.loads(SWITCH_FILE.read_text(encoding="utf-8")).get(SWITCH_KEY) or "").strip().lower()
    except (OSError, ValueError, AttributeError):
        return True, "没有 fd_开关.json（或读不出来），按“开”"
    if v in _OFF:
        return False, "fd_开关.json 写着“关”"
    return True, "fd_开关.json 写着“开”" if v in _ON else "fd_开关.json 里的值认不出（%r），按“开”" % v


# ---------------------------------------------------------------- 视频导演开关（2026-11-08 晚加）
# 开（默认）：第 14 步老路组装完，再跑 site/tools/video3_director.py 让 Claude 重新导演画面，成了就换成导演版；失败或超时退回老路。
# 关：只走老路。先看环境变量 FD_DIRECTOR（只管这一次），再看 fd_开关.json 的"视频导演"；都没有或读不出来按"开"。
DIRECTOR_KEY = "视频导演"


def director_switch():
    """返回 (开着没有, 从哪来的一句话)。"""
    env = str(os.environ.get("FD_DIRECTOR") or "").strip().lower()
    if env in _OFF:
        return False, "环境变量 FD_DIRECTOR=%s" % env
    if env in _ON:
        return True, "环境变量 FD_DIRECTOR=%s" % env
    try:
        v = str(json.loads(SWITCH_FILE.read_text(encoding="utf-8")).get(DIRECTOR_KEY) or "").strip().lower()
    except (OSError, ValueError, AttributeError):
        return True, "没有 fd_开关.json（或读不出来），按“开”"
    if v in _OFF:
        return False, "fd_开关.json 的“视频导演”写着“关”"
    return True, "fd_开关.json 的“视频导演”写着“开”" if v in _ON else "fd_开关.json 的“视频导演”值认不出（%r），按“开”" % v


# ---------------------------------------------------------------- 视频旁白归导演开关（2026-11-09 加，video-narration 分支）
# 开（默认）：导演环节里视频旁白也由导演写（和镜头表、分镜一起），过第 7 步那套检查后只重配视频旁白；
#   检查改两次还不过、配音没成、钱不够，整段退回第 6 步写的现行旁白（导演再按现行旁白只导画面）。
# 关：导演只管画面，旁白用第 6 步写、第 11 步配好的那一份（11-08 晚的做法）。视频导演开关关着时这个开关不起作用。
# 先看环境变量 FD_DIRECTOR_NARRATION（只管这一次），再看 fd_开关.json 的"视频旁白归导演"；都没有或读不出来按"开"。
NARRATION_KEY = "视频旁白归导演"


def narration_switch():
    """返回 (开着没有, 从哪来的一句话)。"""
    env = str(os.environ.get("FD_DIRECTOR_NARRATION") or "").strip().lower()
    if env in _OFF:
        return False, "环境变量 FD_DIRECTOR_NARRATION=%s" % env
    if env in _ON:
        return True, "环境变量 FD_DIRECTOR_NARRATION=%s" % env
    try:
        v = str(json.loads(SWITCH_FILE.read_text(encoding="utf-8")).get(NARRATION_KEY) or "").strip().lower()
    except (OSError, ValueError, AttributeError):
        return True, "没有 fd_开关.json（或读不出来），按“开”"
    if v in _OFF:
        return False, "fd_开关.json 的“视频旁白归导演”写着“关”"
    return True, "fd_开关.json 的“视频旁白归导演”写着“开”" if v in _ON else "fd_开关.json 的“视频旁白归导演”值认不出（%r），按“开”" % v


# ---------------------------------------------------------------- 视频中文整词换行开关（2026-11-09 加，fix-1109-video-breaks 分支）
# 开（默认）：视频里显示的中文按整词换行（组装时在显示那一层加换行点，见 site/tools/video3_zhwrap.py）。
# 关：视频和加这个开关以前逐像素一样。先看环境变量 FD_VIDEO_ZH_WRAP（只管这一次），再看 fd_开关.json 的"视频中文整词换行"；
# 都没有或读不出来按"开"。site/tools/video3_zhwrap.py 的 switch 是同一套规则（组装时用），两边要一起改。
ZH_WRAP_KEY = "视频中文整词换行"


def zh_wrap_switch():
    """返回 (开着没有, 从哪来的一句话)。"""
    env = str(os.environ.get("FD_VIDEO_ZH_WRAP") or "").strip().lower()
    if env in _OFF:
        return False, "环境变量 FD_VIDEO_ZH_WRAP=%s" % env
    if env in _ON:
        return True, "环境变量 FD_VIDEO_ZH_WRAP=%s" % env
    try:
        v = str(json.loads(SWITCH_FILE.read_text(encoding="utf-8")).get(ZH_WRAP_KEY) or "").strip().lower()
    except (OSError, ValueError, AttributeError):
        return True, "没有 fd_开关.json（或读不出来），按“开”"
    if v in _OFF:
        return False, "fd_开关.json 的“视频中文整词换行”写着“关”"
    return True, "fd_开关.json 的“视频中文整词换行”写着“开”" if v in _ON else "fd_开关.json 的“视频中文整词换行”值认不出（%r），按“开”" % v


def monthly_cap():
    prof = read_json(PROFILE, {}) or {}
    v = prof.get("每月 Gemini 配音上限美元（建议）")
    try:
        return float(v)
    except (TypeError, ValueError):
        return 8.0


# ---------------------------------------------------------------- 版别：每一版用哪份写稿指令、稿子叫什么、配音放哪
WEEKDAY_ZH = "一二三四五六日"
EDITIONS = {
    "weekday": {
        "名字": "工作日版", "标题后缀": "",
        "播客稿": "04_文稿/claude_播客_v3.md", "配音方式": "单人", "日子": "日常",
        "人声": "05_配音/播客_v3", "混音": "05_配音/播客_v3_带音效",
        "指令": {"播客": ["写作指南.md", "写稿_播客.md", "读音表.yaml"], "网页": ["写作指南.md", "写稿_网页.md"],
                 "视频": ["写作指南.md", "写稿_视频v3.md"]},
        "周末检查": None, "今日一词": True,
    },
    "saturday_deep": {
        "名字": "周六版（快讯＋单人深度）", "标题后缀": "（周六深度）",
        "播客稿": "04_文稿/claude_播客_周六.md", "配音方式": "单人", "日子": "周六",
        "人声": "05_配音/周六_人声", "混音": "05_配音/周六_带音效",
        "指令": {"播客": ["写作指南.md", "写稿_周六深度.md", "读音表.yaml"],
                 "网页": ["写作指南.md", "写稿_网页.md", "写稿_网页_周末.md"],
                 "视频": ["写作指南.md", "写稿_视频v3.md", "写稿_视频v3_周末.md"]},
        "周末检查": "saturday_deep", "今日一词": False,
    },
    "sunday_deep": {
        "名字": "周日版（Shirley、Dylan 双人深谈）", "标题后缀": "（周日深谈）",
        "播客稿": "04_文稿/claude_播客_周日深谈.md", "配音方式": "对谈", "日子": "周日",
        "人声": "05_配音/周日深谈_人声", "混音": "05_配音/周日深谈_带音效",
        "指令": {"播客": ["写作指南.md", "写稿_周日深谈.md", "读音表.yaml"],
                 "网页": ["写作指南.md", "写稿_网页.md", "写稿_网页_周末.md"],
                 "视频": ["写作指南.md", "写稿_视频v3.md", "写稿_视频v3_周末.md"]},
        "周末检查": "sunday_deep", "今日一词": False,
    },
    "sunday_dialog": {      # 只为复现 11-01 那一期（工作日版面＋两人对谈播客）
        "名字": "旧的周日对谈版（只为复现 11-01）", "标题后缀": "（周日对谈）",
        "播客稿": "04_文稿/claude_对谈_v3.md", "配音方式": "对谈", "日子": "日常",
        "人声": "05_配音/对谈_v3", "混音": "05_配音/对谈_v3_带音效",
        "指令": {"播客": ["写作指南.md", "写稿_周日对谈.md", "读音表.yaml"], "网页": ["写作指南.md", "写稿_网页.md"],
                 "视频": ["写作指南.md", "写稿_视频v3.md"]},
        "周末检查": None, "今日一词": True,
    },
}
WEB_DRAFT = "04_文稿/claude_网页.json"
STORYBOARD = "04_文稿/视频v3_分镜.json"
NARRATION = "04_文稿/视频旁白_v3.md"
VIDEO_VOICE = "05_配音/视频旁白_v3"
CARDS = "03_事件卡/cards_写稿用.json"
LINEUP = "02_选题/最终选题.json"
NO_PODCAST = "05_配音/_本期没有播客"       # 数据版：交给 make_issue_v3 的"播客目录"，不存在 → 页面上不放播客


def pick_edition(day, default_issue, override=None):
    """版别：给了 --edition 用它；默认目录里的冻结期按当时的；其余按星期几（和 run_mimo.py 同一规则）。"""
    if override:
        return override
    if default_issue and day in frozen_editions():
        return frozen_editions()[day]
    wd = date.fromisoformat(day).weekday()
    return "saturday_deep" if wd == 5 else "sunday_deep" if wd == 6 else "weekday"


def episode_title(day, edition):
    d = date.fromisoformat(day)
    return "每日AI科技前沿简报 · %d年%d月%d日%s" % (d.year, d.month, d.day, EDITIONS[edition]["标题后缀"])


# ---------------------------------------------------------------- 内容指纹（判断"上游变没变"）
_FP_CACHE = {}


def fp_file(p):
    p = Path(p)
    try:
        st = p.stat()
    except OSError:
        return None
    if p.is_dir():
        return fp_dir(p)
    key = (str(p), st.st_size, st.st_mtime_ns)
    if key in _FP_CACHE:
        return _FP_CACHE[key]
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    v = h.hexdigest()[:16]
    _FP_CACHE[key] = v
    return v


def fp_dir(p, exts=None):
    """文件夹：里面每个文件的名字和内容指纹（不进子文件夹的 log、隐藏文件）。"""
    p = Path(p)
    if not p.is_dir():
        return None
    h = hashlib.sha1()
    for f in sorted(p.iterdir()):
        if f.name.startswith(".") or not f.is_file():
            continue
        if exts and f.suffix.lower() not in exts:
            continue
        h.update(f.name.encode("utf-8"))
        h.update((fp_file(f) or "").encode())
    return h.hexdigest()[:16]


# ---------------------------------------------------------------- 每期状态 logs/fd_state.json
class State:
    def __init__(self, issue, readonly=False):
        self.path = Path(issue) / "logs" / "fd_state.json"
        self.readonly = readonly
        self.data = read_json(self.path, None) or {"说明": "fd 记的每一步状态（./fd status 读它）；删掉这个文件等于让 fd 从头判断一遍，产出不会丢。",
                                                   "步骤": {}, "运行记录": []}
        self.data.setdefault("步骤", {})
        self.data.setdefault("运行记录", [])

    def step(self, key):
        return self.data["步骤"].get(key)

    def set_step(self, key, rec):
        self.data["步骤"][key] = rec
        self.save()

    def save(self):
        if not self.readonly:
            write_json(self.path, self.data)


# ---------------------------------------------------------------- 锁：同一期同一步只许一个在跑
class Busy(RuntimeError):
    pass


def _proc_cmd(pid):
    try:
        r = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (TypeError, ValueError):
        return False
    return True


class Lock:
    """锁文件里写进程号、开始时间、命令、哪台电脑。那个进程不在了（或进程号被别的程序占了）就当失效、自动清掉。"""

    def __init__(self, issue, name):
        tag = hashlib.sha1(str(Path(issue).resolve()).encode("utf-8")).hexdigest()[:8]
        self.path = LOCKS / ("%s_%s" % (Path(issue).name, tag)) / (name + ".lock")
        self.name = name
        self.held = False
        self.note = ""

    def info(self):
        return read_json(self.path, None)

    def stale_reason(self, info):
        if not info:
            return "锁文件读不出来"
        if info.get("主机") and info["主机"] != socket.gethostname():
            return None                                   # 别的电脑的锁：查不了，当它还在
        pid = info.get("进程号")
        if not pid_alive(pid):
            return "进程 %s 已经不在了" % pid
        cmd = _proc_cmd(pid)
        if cmd and not re.search(r"(^|/)fd(\s|$)", cmd):
            return "进程号 %s 现在是别的程序（%s）" % (pid, cmd[:60])
        return None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(3):
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                info = self.info()
                why = self.stale_reason(info)
                if why is None:
                    raise Busy(info or {})
                try:
                    self.path.unlink()
                    self.note = "清掉了一个失效的锁（%s）" % why
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"进程号": os.getpid(), "开始": stamp(), "命令": " ".join(sys.argv),
                           "主机": socket.gethostname(), "锁的是": self.name}, f, ensure_ascii=False, indent=1)
            self.held = True
            return self
        raise Busy(self.info() or {})

    def release(self):
        if self.held:
            info = self.info() or {}
            if info.get("进程号") == os.getpid():
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
            self.held = False

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()


def running_scripts(patterns):
    """有没有别的进程在跑这些脚本（pgrep -f）：返回 [(进程号, 命令)]，不含自己。"""
    found = []
    for pat in patterns:
        try:
            r = subprocess.run(["pgrep", "-fl", pat], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in r.stdout.splitlines():
            pid, _, cmd = line.strip().partition(" ")
            if pid.isdigit() and int(pid) != os.getpid() and int(pid) != os.getppid():
                found.append((int(pid), cmd))
    return found


# ---------------------------------------------------------------- 子程序的环境
def child_env(offline=False):
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"       # 项目在 iCloud 里，别生成 __pycache__
    env.pop("FD_NO_REEXEC", None)
    if offline:
        dead = "http://127.0.0.1:9"           # 一个没人监听的端口：万一哪段程序想联网，立刻失败，不会花钱
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env[k] = dead
        env["NO_PROXY"] = env["no_proxy"] = ""
        env["FD_ENV_FILE"] = str(CACHE / "离线_没有密钥.env")   # MiMo 读不到密钥（文件不存在）
        for k in ("MIMO_API_KEY", "MIMO_BASE_URL"):
            env.pop(k, None)
        env["GCP_ACCESS_TOKEN"] = "offline-no-network"            # 不去 gcloud 取令牌
        env["HF_HUB_OFFLINE"] = env["TRANSFORMERS_OFFLINE"] = "1"
        env["FD_OFFLINE"] = "1"
    return env


class Proc:
    """跑一条命令：输出全部写进日志文件（python 一律带 -u，边跑边写），屏幕上只显示要紧的几行。"""

    def __init__(self, ctx):
        self.ctx = ctx

    def run(self, argv, log_path, timeout=3600, cwd=None, env=None, label=""):
        argv = [str(a) for a in argv]
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        lines = []
        with open(log_path, "a", encoding="utf-8") as log:
            log.write("\n$ %s\n# 开始 %s（%s）\n" % (" ".join(_q(a) for a in argv), stamp(), label))
            log.flush()
            try:
                p = subprocess.Popen(argv, cwd=str(cwd or ROOT), env=env or self.ctx.env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True,
                                     errors="replace")
            except OSError as e:
                log.write("# 起不来：%s\n" % e)
                return 127, "起不来：%s" % e
            self.ctx.child = p
            verbose = self.ctx.verbose

            def pump():                      # 另开一个线程读输出：子程序长时间不出声也不会卡住超时判断
                for line in p.stdout:
                    log.write(line)
                    log.flush()
                    lines.append(line.rstrip("\n"))
                    if verbose:
                        print("      │ " + line.rstrip("\n"), flush=True)

            th = threading.Thread(target=pump, daemon=True)
            th.start()
            try:
                rc = p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                kill_tree(p)
                rc = 124
                lines.append("✗ 超时（%d 秒），已停掉" % timeout)
                log.write("# 超时 %d 秒，已停掉\n" % timeout)
            except KeyboardInterrupt:
                kill_tree(p)
                log.write("# 被中断（Ctrl-C）\n")
                raise
            finally:
                th.join(timeout=10)
                self.ctx.child = None
            log.write("# 结束 %s，退出码 %s，用时 %.0f 秒\n" % (stamp(), rc, time.time() - t0))
        return rc, "\n".join(lines)


def kill_tree(p):
    try:
        os.killpg(p.pid, signal.SIGTERM)
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _q(a):
    return a if re.fullmatch(r"[\w./:=,+@%-]+", a) else "'" + a.replace("'", "'\\''") + "'"


def tail(text, n=6):
    rows = [x for x in (text or "").splitlines() if x.strip()]
    return rows[-n:]


_KEY = re.compile(r"✗|错误|Error|Exception|Traceback|失败|超出|停|没过|对不上|找不到|注意|提醒|!|⚠")
_NOTICE = re.compile(r"^[-*•·\s]*(提醒|注意|⚠)")      # 只是提醒的行：程序照常往下，不是出错的原因


def key_lines(text, n=8):
    """日志里要紧的几行：报错、没过、提醒。

    11-14 改：先挑真正的报错行（✗、错误、Error、Traceback、找不到……），"提醒：""注意：""⚠" 开头的
    只提醒行跳过；一行报错都没有时才退回老办法（提醒行也算）。11-13 第 14 步视频真正的原因是
    "旁白里找不到这些触发词：close.map（接下来看）"，老办法取最后 3 行要紧的，挑到的是它前面的
    "提醒：读音表里还没有：…"，把真原因埋掉了。"""
    rows = [x.strip() for x in (text or "").splitlines() if _KEY.search(x)]
    hard = [x for x in rows if not _NOTICE.match(x)]
    return (hard or rows)[-n:]


def today_utc():
    return now_utc().date().isoformat()


def hours_ago(h):
    return iso(now_utc() - timedelta(hours=h))
