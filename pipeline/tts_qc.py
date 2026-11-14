#!/usr/bin/env python3
"""对稿：本机 Whisper 把配好的音频转写回来，和原稿逐字比对。

只抓两类大问题——多念（转写里冒出原稿没有的一大段）和漏念（原稿有一大段没念）；
专名、同音字写错只算进字错率，不触发重录（Whisper 自己也常把英文专名拼错）。

比对前先把两边"拉到同一种写法"，避免把写法差异算成读错：
    · 繁体转简体（Whisper 偶尔输出繁体），全角转半角，英文转小写，去掉标点和空格；
    · 中文数字转阿拉伯数字："百分之六十五点二"→"65.2%"、"三百亿"→"300亿"、"二零二六"→"2026"。
      两边用同一套规则，所以"第一条""统一"之类被一起转成"第1条""统1"也不影响比对。
计数单位：一个汉字、一个英文单词、一个数字位各算一个。
另报一个"拼音错误率"：按拼音比、不计声调，同音字和多音字的另一读音都算对，
剩下的才是"听起来就不一样"的地方（多半是英文专名，或真的读错、漏读）。只作参考，不触发重录。

专名读音（2026-11-09 加）：pipeline/prompts/专名读音.yaml 列了几个名字的已知误读（Claude→cloud、Gurman→German、
黄仁勋→黄仁荀、拼音 Yao Shunyu→姚书怀……）。原稿这一块有这个名字、转写里多出了它的已知误读，就算"要重录"
（原因写"专名读音：……"），和多念、漏念一样自动重录一次；重录后还在，调用方在 qc.json 里写"专名读音（请你耳听）"。
清单读不了就不查这一项，照常对稿。转写模型自己也会把念对的名字写错，所以命中只说明"要人耳听"，不等于念错了。
清单里标了"只提醒: true"的名字（Claude，11-09 定）命中时不重录，只在结果的"专名读音"里记一笔（带"只提醒"），
调用方照样在 qc.json 那一块写"专名读音（请你耳听）"：转写模型几乎总把 Claude 写成 cloud，重录多半白花钱。

数字单位（2026-11-09 晚加，unit_losses）：11-09 视频"Anthropic 签下 34 亿美元的协议"转写成"34亿元"，少的正好是"美"，
美元变成了人民币；整块字错率只有 2.75%、最长少 1 个字，原来的线拦不住。现在原稿里紧跟在数字后面的单位或量级
（美元、欧元、英镑、日元、港元、人民币、元、美金……；万亿、亿、千万、万、千……；百分之或 %、个百分点、倍）
在转写里少了或换了，这一块就算"要重录"，原因写"数字单位少字：美（原稿 34亿美元，转写 34亿元）"，和多念、漏念同一套
自动重录一次；重录后还在，调用方在 qc.json 那一块写"数字单位（请你耳听）"。怎么判（只认单位字真的丢了或换了）：
    · 两边先照上面的归一化拉成同一种写法、逐字对齐，再看原稿每个"数字＋单位"对上的那段转写；
    · 同义的算对：美元＝美金、日元＝日圆、港元＝港币、人民币＝元＝元人民币、个百分点＝百分点、百分之＝%；
    · 量级写法不同但数值相同的算对："3.4万"转写成"34000"、"1.25万亿"转写成"12500亿"；
    · 单位字换成同音同调的字算对（"倍"写成"被"）：转写模型挑错字，不是没念出来；
    · 转写多出单位（原稿"34亿"、转写"34亿元"）不算，这条只管丢了、换了；数字本身念错（34 变 35）不归这条管。
吉瓦、年、月这类不在单位表里的不查（"吉瓦"常被转写成"级瓦"，查了只会误报）。

英文名漏念（2026-11-10 加，name_drops）：11-10 视频"发布了 Claude Fable 5.2"，Fable 整个没念（用户耳听确认），转写是"Cloud 5.2"；
少一个英文词只算一两个错字，专名读音清单也只认"念成了什么"，认不出"没念"。现在原稿里读音表（pipeline/prompts/读音表.yaml）
收录的英文名（写法、之后、也可写），同时满足这两条，这一块就算"要重录"，原因写"英文名漏念：……"，和多念、漏念同一套
自动重录一次；重录后还在，调用方在 qc.json 那一块写"英文名漏念（请你耳听）"：
    · 这一条转写里一次都没出现（压扁了比：只看字母数字、不分大小写、0 当 o，LingBot-Touch＝Lingbot Touch，GR00T＝GROOT），
      也没出现专名读音清单里它的已知误读（Claude 转写成 cloud 算念到了，念得对不对归专名读音那一项管）；
    · 逐字对齐里，有一处对上的转写英文字母不到原稿的一半、又没有汉字（整个词被吞了；转写成别的拼法如 Anthrobic、
      Sherly，或写成汉字音译如"奥特曼"，都不算）。
只照最初的说法（"一次都没出现"一条）会误报一大片：拿往期 qc.json（mini 试运行 10-31 至 11-09 各期，加云端 11-09、
11-10；不含带音效的）279 块、397 条转写试过，76 块（27%）命中，几乎都是转写拼错（Anthropic→Anthrobic、Shirley→Sherly、
Slator→Slayter……）；加上第二条以后只命中 11-10 视频 Fable 那一块（测试 test_tts_qc_drops.py）。
读音表读不了就不查这一项。
数字本身不同（11-10 播客"Claude Opus 5.5"念成"5.2"）没有并进来：11-10 评估过"原稿里的数字，转写里成了别的数"，
往期 279 块命中 12 块；能找回音频的三处（iOS 27.3→17.3、V4.1→4.0、432.1→432.01）两个转写模型都一致，单切也一样，
分不出是念错还是转写模型的偏好（iOS 17.3 是它认得的旧版本号），云端又只有一个转写模型，所以只记在报告里。

Whisper 设置（用户定）：mlx-community/whisper-large-v3-turbo，language=zh，
condition_on_previous_text=False（不拿上一句当提示，避免它自己陷入复读、把正常音频误判成多念）。
用 digital-human 的环境跑命令行，HF_HUB_OFFLINE=1 只用本机已下载的模型。
"""
import json
import os
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import sys
sys.dont_write_bytecode = True

try:
    from opencc import OpenCC
    _T2S = OpenCC("t2s")
except Exception:          # 没装也能跑，只是繁体输出会被算成错字
    _T2S = None
try:                       # 拼音错误率用；没装就只报字错率
    from pypinyin import Style, pinyin as _pinyin
except Exception:
    _pinyin = None

# ============================ 可改区 ============================

WHISPER_BIN = Path(os.environ.get("FD_WHISPER_BIN") or Path.home() / ".venvs/digital-human/bin/mlx_whisper")   # FD_WHISPER_BIN：别的机器上转写命令的位置；没设时和原来一样
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"

RUN_LIMIT = 8          # 一处连续多出（或少掉）这么多个字/词，就算"大段"多念（漏念）
RUN_GAP = 2            # 两处差异之间只隔 ≤2 个对得上的字，合并成一处（防止被零星巧合切碎）
CER_LIMIT = 0.20       # 整块字错率超过两成，说明整体对不上
DURATION_RANGE = (0.5, 2.0)   # 实际时长 / 估计时长 超出这个范围也重录
OVERLONG_RATIO = 2.0          # 实际时长超过按字数估计的这么多倍，
OVERLONG_MIN_EXTRA_S = 30     # 而且至少多出这么多秒：当废条丢掉重录，不转写（11-14 加，见 overlong()）
NAMES = Path(__file__).resolve().parent / "prompts" / "专名读音.yaml"   # 专名读音清单（11-09 加）

# ==============================================================

CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}
_NUM_CHARS = "零〇一二两三四五六七八九十百千"


def transcribe(wav_path, work_dir=None):
    """返回转写文本。work_dir 放 Whisper 的 json 输出（放缓存目录，别放 iCloud）。"""
    wav_path = Path(wav_path)
    work = Path(work_dir or tempfile.mkdtemp(prefix="fd_whisper_"))
    work.mkdir(parents=True, exist_ok=True)
    name = wav_path.stem + "_whisper"
    env = dict(os.environ, HF_HUB_OFFLINE="1")
    for k in ("MIMO_API_KEY", "GCP_ACCESS_TOKEN"):    # 子进程用不着密钥
        env.pop(k, None)
    cmd = [str(WHISPER_BIN), str(wav_path), "--model", WHISPER_MODEL, "--language", "zh",
           "--condition-on-previous-text", "False", "--output-format", "json",
           "--output-dir", str(work), "--output-name", name, "--verbose", "False"]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    out = work / f"{name}.json"
    if r.returncode or not out.exists():
        raise RuntimeError(f"Whisper 失败：{(r.stderr or r.stdout)[-400:]}")
    d = json.loads(out.read_text(encoding="utf-8"))
    return (d.get("text") or "").strip()


# 一次进程里逐条跑 mlx_whisper 自己的命令行入口（参数和 transcribe 完全一样），模型只载入一次。
# 不直接给命令行传多个文件：它的 cli.py 有个小毛病，多个文件时输出名一直沿用第一个文件的名字，会互相覆盖。
_MANY = """
import json, sys
from mlx_whisper import cli
jobs = json.loads(sys.stdin.read())
for wav, out_dir, name, model in jobs:
    sys.argv = ["mlx_whisper", wav, "--model", model, "--language", "zh",
                "--condition-on-previous-text", "False", "--output-format", "json",
                "--output-dir", out_dir, "--output-name", name, "--verbose", "False"]
    cli.main()
"""


def transcribe_many(items):
    """items：[(音频路径, 输出目录), …]。和逐条调 transcribe 结果一样（输出也叫 <音频名>_whisper.json），
    只是一次进程做完（对谈稿一集几十句，逐条调每句都要重新载入模型）。返回 {音频路径字符串: 转写文本}。"""
    items = [(Path(w), Path(d)) for w, d in items]
    if not items:
        return {}
    jobs = []
    for w, d in items:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{w.stem}_whisper.json").unlink(missing_ok=True)     # 免得把上次的旧结果当成这次的
        jobs.append([str(w), str(d), w.stem + "_whisper", WHISPER_MODEL])
    env = dict(os.environ, HF_HUB_OFFLINE="1")
    for k in ("MIMO_API_KEY", "GCP_ACCESS_TOKEN", "GEMINI_API_KEY"):    # 子进程用不着密钥
        env.pop(k, None)
    py = WHISPER_BIN.parent / "python"
    r = subprocess.run([str(py), "-c", _MANY], input=json.dumps(jobs), capture_output=True, text=True, env=env)
    out = {}
    for w, d in items:
        f = d / f"{w.stem}_whisper.json"
        if not f.exists():
            raise RuntimeError(f"Whisper 没转出 {w.name}：{(r.stderr or r.stdout)[-400:]}")
        out[str(w)] = (json.loads(f.read_text(encoding="utf-8")).get("text") or "").strip()
    return out


# ---------------------------------------------------------------- 归一化


def _cn_int(s):
    """不含万、亿的中文整数 → 阿拉伯数字串。只有数字字的（二零二六）逐位转；只有单位的不转。"""
    if all(c in CN_DIGITS for c in s):
        return "".join(str(CN_DIGITS[c]) for c in s)
    if not any(c in CN_DIGITS for c in s) and s != "十":
        return None
    total, num = 0, 0
    for c in s:
        if c in CN_DIGITS:
            num = CN_DIGITS[c]
        else:
            total += (num if num else 1) * CN_UNITS[c]
            num = 0
    return str(total + num)


def _convert_run(run):
    """一段连续的中文数字（可含"点"）→ 阿拉伯数字；转不了就原样返回。"""
    if "点" in run:
        a, b = run.split("点", 1)
        ia = _cn_int(a) if a else None
        if ia is not None and b and all(c in CN_DIGITS for c in b):
            return ia + "." + "".join(str(CN_DIGITS[c]) for c in b)
        return run
    v = _cn_int(run)
    return v if v is not None else run


_RUN_RE = re.compile(rf"[{_NUM_CHARS}]+(?:点[零〇一二两三四五六七八九]+)?")


def cn_numbers_to_arabic(s):
    s = re.sub(r"百分之([0-9]+(?:\.[0-9]+)?)", r"\1%", s)           # 百分之65.2
    s = re.sub(rf"百分之({_RUN_RE.pattern})", lambda m: _convert_run(m.group(1)) + "%", s)
    return _RUN_RE.sub(lambda m: _convert_run(m.group(0)), s)


def normalize(text):
    s = unicodedata.normalize("NFKC", text)
    if _T2S:
        s = _T2S.convert(s)
    s = s.lower()
    s = re.sub(r"<[^>]*>", " ", s)                  # 行内标记（<short pause> 等）不算台词
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)   # 1,000 → 1000
    s = cn_numbers_to_arabic(s)
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)      # 只保留数字中间的小数点
    return s


def tokens(text):
    return re.findall(r"[a-z]+|\d|[%.]|[\u3400-\u9fff]", normalize(text))


# ---------------------------------------------------------------- 比对


def align(ref, hyp, keys_ref=None, keys_hyp=None):
    """编辑距离对齐，返回操作序列 [(op, 原稿字, 转写字)]，op ∈ E S D I。
    keys_ref/keys_hyp 给了的话按它们比"是否相同"（集合有交集就算相同，用于拼音比对）。"""
    n, m = len(ref), len(hyp)
    kr, kh = keys_ref, keys_hyp
    prev = list(range(m + 1))
    back = [bytearray(b"I" * (m + 1))]
    back[0][0] = ord("E")
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        row = bytearray(m + 1)
        row[0] = ord("D")
        ri = ref[i - 1]
        for j in range(1, m + 1):
            if (kr[i - 1] & kh[j - 1]) if kr is not None else ri == hyp[j - 1]:
                best, op = prev[j - 1], "E"
            else:
                best, op = prev[j - 1] + 1, "S"
            if prev[j] + 1 < best:
                best, op = prev[j] + 1, "D"
            if cur[j - 1] + 1 < best:
                best, op = cur[j - 1] + 1, "I"
            cur[j] = best
            row[j] = ord(op)
        back.append(row)
        prev = cur
    ops, i, j = [], n, m
    while i > 0 or j > 0:
        op = chr(back[i][j]) if i > 0 and j > 0 else ("D" if i > 0 else "I")
        if op in "ES":
            ops.append((op, ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif op == "D":
            ops.append(("D", ref[i - 1], ""))
            i -= 1
        else:
            ops.append(("I", "", hyp[j - 1]))
            j -= 1
    return ops[::-1]


def _join(toks):
    out = ""
    for t in toks:
        if out and re.match(r"[a-z]", t) and re.search(r"[a-z0-9]$", out):
            out += " "
        out += t
    return out


def diff_runs(ops, gap=RUN_GAP):
    """把差异归成一处一处：每处统计多出(I)、少掉(D)、替换(S)，附原稿和转写片段。"""
    runs, cur, eq = [], None, 0
    for op, r, h in ops:
        if op == "E":
            if cur is not None:
                eq += 1
                cur["_tail"].append((r, h))
                if eq > gap:
                    cur["_tail"] = cur["_tail"][:-eq]
                    runs.append(cur)
                    cur, eq = None, 0
            continue
        if cur is None:
            cur = {"I": 0, "D": 0, "S": 0, "ref": [], "hyp": [], "_tail": []}
        else:
            for tr, th in cur["_tail"]:
                cur["ref"].append(tr)
                cur["hyp"].append(th)
        cur["_tail"], eq = [], 0
        cur[op] += 1
        if r:
            cur["ref"].append(r)
        if h:
            cur["hyp"].append(h)
    if cur is not None:
        runs.append(cur)
    return [{"多出": x["I"], "少掉": x["D"], "替换": x["S"],
             "原稿": _join(x["ref"]), "转写": _join(x["hyp"])} for x in runs]


def _pinyin_sets(toks):
    """每个汉字 → 它所有读音的无调拼音集合；其他记号原样。"""
    out = []
    for t in toks:
        if _pinyin and re.match(r"[\u3400-\u9fff]", t):
            out.append(frozenset(_pinyin(t, style=Style.NORMAL, heteronym=True)[0]))
        else:
            out.append(frozenset([t]))
    return out


def pinyin_error_rate(ref, hyp):
    """按拼音比、不计声调：同音字、多音字的另一种读音都算对。剩下的才是"听起来就不一样"的地方。"""
    if not _pinyin:
        return None
    ops = align(ref, hyp, _pinyin_sets(ref), _pinyin_sets(hyp))
    return sum(1 for o in ops if o[0] != "E") / max(1, len(ref))


_NAMES_CACHE = {}


def _name_pattern(form):
    """英文按整词、不分大小写（前后紧挨字母的不算，Cloudflare 里的 cloud 不算）；中文按字面。"""
    body = r"\s*".join(re.escape(x) for x in form.split())
    if re.search(r"[A-Za-z]", form):
        return re.compile(r"(?<![A-Za-z])" + body + r"(?![A-Za-z])", re.I)
    return re.compile(body)


def load_names(path=None):
    """专名读音清单 → [{"写法": [正则…], "名字": 写法原样, "误读": [(写法, 正则)…], "说明", "只提醒"}]。读不了返回 []（不查这一项）。"""
    p = Path(path) if path else NAMES
    try:
        mt = p.stat().st_mtime_ns
    except OSError:
        return []
    hit = _NAMES_CACHE.get(str(p))
    if hit and hit[0] == mt:
        return hit[1]
    rows = []
    try:
        import yaml
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for e in d.get("名字") or []:
            if not isinstance(e, dict) or not e.get("写法") or not e.get("已知误读"):
                continue
            forms = e["写法"] if isinstance(e["写法"], list) else [e["写法"]]
            bad = e["已知误读"] if isinstance(e["已知误读"], list) else [e["已知误读"]]
            rows.append({"名字": str(forms[0]), "写法": [_name_pattern(str(f)) for f in forms],
                         "误读": [(str(b), _name_pattern(str(b))) for b in bad], "说明": str(e.get("说明") or ""),
                         "只提醒": e.get("只提醒") is True})
    except Exception:  # noqa: BLE001  清单坏了不能让配音停下
        rows = []
    _NAMES_CACHE[str(p)] = (mt, rows)
    return rows


def _norm_hyp(text):
    s = unicodedata.normalize("NFKC", text or "")
    return _T2S.convert(s) if _T2S else s


def name_misreads(ref_text, hyp_text, names=None):
    """原稿有清单里的名字、转写里多出了它的已知误读 → [{"名字", "转写成", "处数", "说明"}]，清单标了只提醒的另带 "只提醒": True。
    "多出"按次数算：原稿里本来就有的同一个词（原稿写了 Google Cloud）先抵掉，免得误报。"""
    names = load_names() if names is None else names
    ref, hyp = _norm_hyp(ref_text), _norm_hyp(hyp_text)
    out = []
    for e in names:
        if not any(p.search(ref) for p in e["写法"]):
            continue
        for word, pat in e["误读"]:
            n = len(pat.findall(hyp)) - len(pat.findall(ref))
            if n > 0:
                out.append({"名字": e["名字"], "转写成": word, "处数": n, "说明": e["说明"],
                            **({"只提醒": True} if e.get("只提醒") else {})})
    return out


# ---------------------------------------------------------------- 数字单位（2026-11-09 晚加）
# 原稿里紧跟在数字后面的量级和单位。同一组（第二个值）的算同义；量级给出倍数，用来认"3.4万"＝"34000"。
UNIT_MAGS = {"万亿": 1e12, "千亿": 1e11, "百亿": 1e10, "千万": 1e7, "百万": 1e6, "亿": 1e8, "万": 1e4, "千": 1e3, "百": 1e2}
UNIT_KINDS = {
    "美元": "美元", "美金": "美元", "欧元": "欧元", "英镑": "英镑", "日元": "日元", "日圆": "日元",
    "港元": "港元", "港币": "港元", "澳元": "澳元", "加元": "加元", "韩元": "韩元", "新台币": "新台币", "台币": "新台币",
    "卢布": "卢布", "卢比": "卢比", "新加坡元": "新加坡元", "元人民币": "人民币", "人民币": "人民币", "元": "人民币",
    "个百分点": "百分点", "百分点": "百分点", "百分之": "%", "%": "%", "倍": "倍",
}
_APPROX = "多余几来"      # "三十多万""十几亿"：数字和单位中间的约数字，跳过


def _match_unit(toks, p, table):
    """从第 p 个记号起，按表找最长的一个单位（表里都是单字记号拼成的）：返回 (单位, 新位置) 或 ("", p)。"""
    for u in sorted(table, key=len, reverse=True):
        if u == "百" and "".join(toks[p:p + 2]) == "百分":     # "百分点""百分之"不是量级"百"
            continue
        if "".join(toks[p:p + len(u)]) == u and all(len(t) == 1 for t in toks[p:p + len(u)]):
            return u, p + len(u)
    return "", p


def _digits_at(toks, q):
    """从 q 起的一串数字（中间可带小数点）的结束位置。"""
    while q < len(toks) and (toks[q].isdigit() or (toks[q] == "." and q + 1 < len(toks) and toks[q + 1].isdigit())):
        q += 1
    return q


def _skip_approx(toks, q):
    while q < len(toks) and toks[q] in _APPROX:
        q += 1
    return q


def _num_unit(toks, p):
    """从 p 起读"数字 [约数] [量级] ([数字 [量级]]…) [约数] [单位]"：返回 {"数字", "量级", "单位", "值", "数字止", "止"}。
    "1万7500"（一万七千五百）、"3亿2000万"这种带量级的复合数一起读，值按整个数算，免得和转写里的"17500"对不上。
    "数字"是第一段数字，"量级"是各段量级连起来（"万""亿万"），"值"是整个数的数值（读不了是 None）。"""
    q = _digits_at(toks, p)
    first, nend = "".join(toks[p:q]), q
    mags, value, cur_num = "", 0.0, first
    while True:
        r = _skip_approx(toks, q)
        mag, r2 = _match_unit(toks, r, UNIT_MAGS)
        try:
            v = float(cur_num) if cur_num else None
        except ValueError:
            v = None
        if not mag:
            value = value + v if (v is not None and value is not None) else None
            break
        mags += mag
        value = value + v * UNIT_MAGS[mag] if (v is not None and value is not None) else None
        q = r2
        nxt = _digits_at(toks, q)                     # 量级后面紧跟的数字：小于这一级的才算同一个数（1万7500）
        if nxt == q:
            break
        try:
            small = float("".join(toks[q:nxt])) * UNIT_MAGS.get(_match_unit(toks, _skip_approx(toks, nxt), UNIT_MAGS)[0], 1) \
                < UNIT_MAGS[mag]
        except ValueError:
            small = False
        if not small:
            break
        cur_num, q = "".join(toks[q:nxt]), nxt
    r = _skip_approx(toks, q)
    unit, r = _match_unit(toks, r, UNIT_KINDS)
    return {"数字": first, "量级": mags, "单位": unit, "值": value if first else None, "数字止": nend, "止": r if unit else q}


def _number_mentions(toks):
    """原稿里每个"数字＋量级/单位"：[(起, 止, _num_unit 的结果)]（记号下标，止不含）。"""
    out, k = [], 0
    while k < len(toks):
        if not toks[k].isdigit():
            k += 1
            continue
        m = _num_unit(toks, k)
        if m["量级"] or m["单位"]:
            out.append((k, m["止"], m))
        k = max(m["止"], m["数字止"])
    return out


def _parse_hyp_unit(toks):
    """对上原稿那一段的转写记号 → (_num_unit 的结果, 这一段里出现的所有单位)。从第一个数字读起；没有数字时只在里面找。
    "所有单位"用来认"32万亿日元"转写成"32万元日元"这种：亿丢了，日元其实还在。"""
    m = {"数字": "", "量级": "", "单位": "", "值": None}
    for k, t in enumerate(toks):
        if t.isdigit():
            m = _num_unit(toks, k)
            break
    found, k = [], 0
    while k < len(toks):                      # 不重叠地找（"日元"里的"元"不再单算一次）
        if not m["数字"] and not m["量级"]:
            m["量级"] = _match_unit(toks, k, UNIT_MAGS)[0]
        u, k2 = _match_unit(toks, k, UNIT_KINDS)
        if u:
            found.append(u)
        k = max(k2, k + 1)
    if not m["单位"] and found:
        m["单位"] = found[0]
    return m, found


def _tone_sets(ch):
    if not (_pinyin and re.match(r"[㐀-鿿]$", ch)):
        return frozenset([ch])
    return frozenset(_pinyin(ch, style=Style.TONE3, heteronym=True)[0])


def _missing(a, b):
    """a 里有、b 里没有的字（按次数）。"""
    rest = list(b)
    out = []
    for c in a:
        if c in rest:
            rest.remove(c)
        else:
            out.append(c)
    return "".join(out)


def _shown(u):
    return "百分之" if u == "%" else u


def unit_losses(ref_text, hyp_text, ref=None, hyp=None, ops=None):
    """原稿里数字后面的单位、量级，转写里少了或换了 → [{"原稿", "转写", "说明"}]（规则见文件头"数字单位"）。
    ref/hyp/ops 可以传 check() 已经算好的记号和对齐，省得再算一遍。"""
    ref = tokens(ref_text) if ref is None else ref
    hyp = tokens(hyp_text) if hyp is None else hyp
    mentions = _number_mentions(ref)
    if not mentions:
        return []
    ops = align(ref, hyp) if ops is None else ops
    pos, i, j = [], 0, 0                     # 每一步对齐：(op, 原稿下标, 转写下标)
    for op, r, h in ops:
        if op in "ES":
            pos.append((op, i, j))
            i, j = i + 1, j + 1
        elif op == "D":
            pos.append((op, i, None))
            i += 1
        else:
            pos.append((op, None, j))
            j += 1
    out = []
    for a, end, m in mentions:
        ks = [k for k, (_, ri, _) in enumerate(pos) if ri is not None and a <= ri < end]
        span = []
        for op, ri, hj in pos[ks[0]:ks[-1] + 1]:
            if hj is None:
                continue
            h = hyp[hj]
            # 单位字换成同音同调的字（倍→被）：当作对上了
            if op == "S" and ri is not None and ref[ri] not in _APPROX and _tone_sets(ref[ri]) & _tone_sets(h) \
                    and re.match(r"[㐀-鿿]$", ref[ri]):
                h = ref[ri]
            span.append(h)
        hm, hall = _parse_hyp_unit(span)
        unit, mag = m["单位"], m["量级"]
        lost, swapped = [], []
        if unit and UNIT_KINDS[unit] not in {UNIT_KINDS[u] for u in hall}:
            if hm["单位"] and _missing(hm["单位"], unit):
                swapped.append(f"{_shown(unit)}→{_shown(hm['单位'])}")
            else:
                lost.append(_shown(_missing(unit, hm["单位"]) or unit))
        if mag and hm["量级"] != mag:
            # 量级写法不同、数值一样的算对（3.4万＝34000，1万7500＝17500，1.25万亿＝12500亿）
            same = m["值"] is not None and hm["值"] is not None and abs(m["值"] - hm["值"]) <= 1e-9 * abs(m["值"])
            if not same:
                if hm["量级"] and _missing(hm["量级"], mag):
                    swapped.append(f"{mag}→{hm['量级']}")
                else:
                    lost.append(_missing(mag, hm["量级"]) or mag)
        if lost or swapped:
            why = "；".join(([f"少字：{'、'.join(lost)}"] if lost else []) + ([f"换字：{'、'.join(swapped)}"] if swapped else []))
            out.append({"原稿": _join(ref[a:end]), "转写": _join(span), "说明": why})
    return out


# ---------------------------------------------------------------- 英文名漏念（2026-11-10 加）
LEXICON = Path(__file__).resolve().parent / "prompts" / "读音表.yaml"
_LEX_CACHE = {}
_TOKEN_RE = re.compile(r"[a-z]+|\d|[%.]|[\u3400-\u9fff]")      # 和 tokens() 同一个正则


def _ref_positions(ops):
    """对齐结果 → 每一步的 (op, 原稿下标, 转写下标)（没有的是 None）。"""
    pos, i, j = [], 0, 0
    for op, r, h in ops:
        if op in "ES":
            pos.append((op, i, j))
            i, j = i + 1, j + 1
        elif op == "D":
            pos.append((op, i, None))
            i += 1
        else:
            pos.append((op, None, j))
            j += 1
    return pos


def _squash(s):
    """只留字母和数字、小写，数字 0 当字母 o（LingBot-Touch → lingbottouch，GR00T → groot），用来认转写里有没有
    这个名字：连写、拆开、带不带连字符，GR00T 写成 GROOT，都算出现了。"""
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", s or "").lower()).replace("0", "o")


def load_lexicon_names(path=None):
    """读音表里写法带英文字母的条目 → [{"名字", "写法": [原样…], "正则": [正则…], "认": [压扁的写法…]}]
    （写法、之后、也可写里带英文字母的都算）。读不了返回 []（不查这一项）。"""
    p = Path(path) if path else LEXICON
    try:
        mt = p.stat().st_mtime_ns
    except OSError:
        return []
    hit = _LEX_CACHE.get(str(p))
    if hit and hit[0] == mt:
        return hit[1]
    rows = []
    try:
        import yaml
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for cat in ("人名", "公司", "产品", "媒体", "其他"):
            for e in d.get(cat) or []:
                if not isinstance(e, dict) or not re.search(r"[A-Za-z]", str(e.get("写法") or "")):
                    continue
                also = e.get("也可写") or []
                forms = [str(e["写法"])] + ([str(e["之后"])] if e.get("之后") else []) + \
                    [str(x) for x in (also if isinstance(also, list) else [also])]
                forms = list(dict.fromkeys(f for f in forms if re.search(r"[A-Za-z]", f)))
                rows.append({"名字": str(e["写法"]), "写法": forms, "正则": [_name_pattern(f) for f in forms],
                             "认": sorted({_squash(f) for f in forms if _squash(f)}, key=len)})
    except Exception:  # noqa: BLE001  表坏了不能让配音停下
        rows = []
    _LEX_CACHE[str(p)] = (mt, rows)
    return rows


def _misread_seen(e, names, hyp):
    """这一条的某个写法正好是专名读音清单里的名字，转写里又出现了它的已知误读：算念到了（念得对不对归 name_misreads 管）。"""
    for x in names:
        if any(p.fullmatch(f) for p in x["写法"] for f in e["写法"]) and any(pat.search(hyp) for _, pat in x["误读"]):
            return True
    return False


def name_drops(ref_text, hyp_text, lexicon=None, names=None):
    """英文名漏念：原稿里读音表收录的英文名，转写里一次都没出现（压扁了比，也没有它的已知误读），而且逐字对齐里
    有一处对上的转写，英文字母不到原稿的一半、又没有汉字（整个词被吞了，不是转写写成了别的拼法、音译）
    → [{"名字", "原稿", "转写"}]（规则和误报统计见文件头"英文名漏念"）。"""
    lexicon = load_lexicon_names() if lexicon is None else lexicon
    names = load_names() if names is None else names
    hyp_raw = _norm_hyp(hyp_text)
    sq = _squash(hyp_raw)
    ref_n = normalize(ref_text)
    R, H = None, None
    pos = None
    out = []
    for e in lexicon:
        found = [m for p in e["正则"] for m in p.finditer(ref_n)]
        if not found:
            continue
        if any(f in sq for f in e["认"]) or _misread_seen(e, names, hyp_raw):
            continue
        if pos is None:
            R, H = tokens(ref_text), tokens(hyp_text)
            pos = _ref_positions(align(R, H))
            spans = [(m.start(), m.end()) for m in _TOKEN_RE.finditer(ref_n)]
            hyp_n = normalize(hyp_text)
            spans_h = [(m.start(), m.end()) for m in _TOKEN_RE.finditer(hyp_n)]
        occ = set()
        for m in found:
            ks = tuple(k for k, (a, b) in enumerate(spans) if a >= m.start() and b <= m.end())
            if any(re.match(r"[a-z]", R[k]) for k in ks):
                occ.add(ks)
        for ks in sorted(x for x in occ if not any(set(x) < set(y) for y in occ)):   # 同一处取最长的写法
            steps = [s for s, (_, ri, _) in enumerate(pos) if ri is not None and ri in ks]
            a, b = steps[0], steps[-1]
            while a > 0 and pos[a - 1][0] == "I":      # 紧挨着多出来的字也算这一处的（DeepSeek 转写成 Deep Seek）
                a -= 1
            while b + 1 < len(pos) and pos[b + 1][0] == "I":
                b += 1
            hj = [h for _, _, h in pos[a:b + 1] if h is not None]
            got = [H[h] for h in hj]
            letters_r = sum(len(R[k]) for k in ks if re.match(r"[a-z]", R[k]))
            letters_h = sum(len(t) for t in got if re.match(r"[a-z]", t))
            if letters_h <= 0.5 * letters_r and not any(re.match(r"[\u3400-\u9fff]", t) for t in got):
                out.append({"名字": e["名字"], "原稿": ref_n[spans[ks[0]][0]:spans[ks[-1]][1]],
                            "转写": hyp_n[spans_h[hj[0]][0]:spans_h[hj[-1]][1]] if hj else ""})
                break
    return out


def check(ref_text, hyp_text, seconds=None, est_seconds=None):
    """返回对稿结果字典；"需重录" 为 True 表示有多念、漏念、整体对不上，或专名转写成了已知误读（11-09 加；
    清单标了"只提醒"的名字不算，只记进"专名读音"），或数字后面的单位字少了、换了（11-09 晚加，记进"数字单位"），
    或读音表里的英文名整个没念出来（11-10 加，记进"英文名漏念"）。"""
    ref, hyp = tokens(ref_text), tokens(hyp_text)
    ops = align(ref, hyp)
    cnt = {k: sum(1 for o in ops if o[0] == k) for k in "SDI"}
    cer = (cnt["S"] + cnt["D"] + cnt["I"]) / max(1, len(ref))
    per = pinyin_error_rate(ref, hyp)
    runs = diff_runs(ops)
    max_ins = max([r["多出"] for r in runs] or [0])
    max_del = max([r["少掉"] for r in runs] or [0])
    reasons = []
    if max_ins >= RUN_LIMIT:
        reasons.append(f"多念：一处多出 {max_ins} 个字/词")
    if max_del >= RUN_LIMIT:
        reasons.append(f"漏念：一处少了 {max_del} 个字/词")
    if cer >= CER_LIMIT:
        reasons.append(f"字错率 {cer:.1%} 过高")
    ratio = None
    if seconds and est_seconds:
        ratio = seconds / est_seconds
        if not DURATION_RANGE[0] <= ratio <= DURATION_RANGE[1]:
            reasons.append(f"时长异常：实际 {seconds:.0f} 秒，估计 {est_seconds:.0f} 秒")
    names = name_misreads(ref_text, hyp_text)
    for x in names:
        if not x.get("只提醒"):
            reasons.append(f"专名读音：{x['名字']} 转写成了 {x['转写成']}（{x['处数']} 处），重录一次；还在就请你耳听")
    units = unit_losses(ref_text, hyp_text, ref, hyp, ops)
    for x in units:
        reasons.append(f"数字单位{x['说明']}（原稿 {x['原稿']}，转写 {x['转写'] or '（没有）'}），重录一次；还在就请你耳听")
    drops = name_drops(ref_text, hyp_text)
    for x in drops:
        reasons.append(f"英文名漏念：{x['名字']}（原稿 {x['原稿']}，转写 {x['转写'] or '（没有）'}），重录一次；还在就请你耳听")
    return {"字错率": round(cer, 4),
            "拼音错误率": round(per, 4) if per is not None else None,
            "原稿字数": len(ref), "转写字数": len(hyp),
            "替换": cnt["S"], "少掉": cnt["D"], "多出": cnt["I"],
            "最长多出": max_ins, "最长少掉": max_del,
            "时长比": round(ratio, 2) if ratio else None,
            "需重录": bool(reasons), "原因": reasons,
            **({"专名读音": names} if names else {}),
            **({"数字单位": units} if units else {}),
            **({"英文名漏念": drops} if drops else {}),
            "差异": runs, "转写": hyp_text}


def badness(result):
    """两条都不完美时挑哪条：先看是否需重录，再看最大的一处多念/漏念，最后看字错率（没转写的废条字错率记作最差）。"""
    cer = result.get("字错率")
    return (result["需重录"], max(result["最长多出"], result["最长少掉"]), cer if cer is not None else float("inf"))


def overlong(seconds, est_seconds):
    """这一条明显跑飞了（11-14 加，经验库第 71 件①）：实际时长超过按字数估计的 OVERLONG_RATIO（2）倍、而且至少多出
    OVERLONG_MIN_EXTRA_S（30）秒，返回一句说明；不是就返回 None。
    为什么：11-11 播客块 1 为音高重录的第 2 条，Gemini 多念了 612 个字，181 秒（估计 55 秒）；照旧整条转写，云端转写
    约 1 秒音频 1 秒，白花 3 分钟才判出"多念""时长异常"。这种不用听也知道不能用，配完量了时长就丢，直接重录。
    只多一点（短块 2 倍出头、多不到 30 秒）的照旧转写，由 check() 的"时长异常"判。"""
    if not seconds or not est_seconds:
        return None
    if seconds > OVERLONG_RATIO * est_seconds and seconds - est_seconds >= OVERLONG_MIN_EXTRA_S:
        return (f"时长异常：实际 {seconds:.0f} 秒，估计 {est_seconds:.0f} 秒（超过 {OVERLONG_RATIO:g} 倍、多 "
                f"{seconds - est_seconds:.0f} 秒），当废条丢掉重录，没转写")
    return None


def discarded(seconds, est_seconds, why):
    """废条（overlong）的对稿结果：字段和 check() 一样，需重录，没转写；挑条时排在转写过的各条后面（tts.pick_take 看"废条"）。"""
    return {"字错率": None, "拼音错误率": None, "原稿字数": 0, "转写字数": 0, "替换": 0, "少掉": 0, "多出": 0,
            "最长多出": 0, "最长少掉": 0, "时长比": round(seconds / est_seconds, 2) if est_seconds else None,
            "需重录": True, "原因": [why], "废条": True, "没转写": True, "差异": [], "转写": ""}


# ---------------------------------------------------------------- 音高、语速把关（2026-11-01 加）
# 同一个声音每次合成的音高会漂（11-01 实测：同一句两次能差几十赫兹，视频各章从 160 到 229 Hz）。
# 把关的做法：每块（对谈里是每轮）配完量一次"音高中位数"，和这个声音的参考音高比；差太多就重录，挑最接近的一条。
# 参考音高、参考语速写在 pipeline/voice_profile.json（各声音的"参考"一节，从定稿样音实测），阈值在它的"音高把关"一节。

SR = 24000
PITCH_TOL_ST = 1.5          # 和参考音高差超过这么多个半音就重录（profile"音高把关"可改）
PITCH_RETAKES = 2           # 为音高最多再录几次
PITCH_MIN_VOICED_S = 1.2    # 有声部分不到这么多秒的（"对。"这类短句）音高量不准，不判
RATE_TOL = 0.10             # 语速和参考值差超过一成，在 qc 里标出来（只标，不重录）
PROFILE = Path(__file__).resolve().parent / "voice_profile.json"


def read_audio(path, sr=SR):
    """任意音频 → 单声道 float64（ffmpeg 解码）。"""
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-f", "f64le", "-ac", "1",
                        "-ar", str(sr), "-"], capture_output=True)
    if r.returncode:
        raise RuntimeError(f"读不了 {path}：{r.stderr.decode(errors='replace')[-300:]}")
    import numpy as np
    return np.frombuffer(r.stdout, dtype=np.float64)


def f0_track(x, sr=SR, fmin=70, fmax=420, frame=0.04, hop=0.02, thresh=0.15):
    """音高（Hz，每 hop 秒一个，不发声的帧是 nan）。YIN 算法（de Cheveigné & Kawahara 2002），
    和 配音测试/第四轮 的 yin_f0、dialog_tts.f0_track 同样的做法和参数；差分函数用 FFT 一次算整批帧。"""
    import numpy as np
    W, H = int(frame * sr), int(hop * sr)
    tmin, tmax = int(sr / fmax), int(sr / fmin)
    n = (len(x) - W - tmax) // H
    if n <= 0:
        return np.array([])
    out = np.full(n, np.nan)
    starts = np.arange(n) * H
    rms_all = np.sqrt(np.array([(x[s:s + W] ** 2).mean() for s in starts]))
    gate = rms_all.max() * 10 ** (-35 / 20)
    L = 1 << int(np.ceil(np.log2(2 * W + tmax)))
    lag = np.arange(1, tmax + 1)
    for a0 in range(0, n, 1024):
        idx = np.arange(a0, min(n, a0 + 1024))
        idx = idx[rms_all[idx] > gate]
        if not len(idx):
            continue
        seg = x[starts[idx][:, None] + np.arange(W + tmax)]
        a = seg[:, :W]
        corr = np.fft.irfft(np.fft.rfft(a[:, ::-1], L) * np.fft.rfft(seg, L), L)[:, W - 1:W + tmax]
        cs = np.concatenate([np.zeros((len(idx), 1)), np.cumsum(seg ** 2, axis=1)], axis=1)
        d = (a ** 2).sum(axis=1)[:, None] + (cs[:, W:W + tmax + 1] - cs[:, :tmax + 1]) - 2 * corr
        d = np.maximum(d, 0)
        cm = np.ones_like(d)
        cm[:, 1:] = d[:, 1:] * lag / np.maximum(np.cumsum(d[:, 1:], axis=1), 1e-12)
        below = cm[:, tmin:] < thresh
        has = below.any(axis=1)
        t = np.where(has, below.argmax(axis=1) + tmin, 0)
        for _ in range(40):                            # 顺着往下走到这个谷的底
            nxt = np.minimum(t + 1, tmax)
            go = has & (t + 1 <= tmax) & (cm[np.arange(len(t)), nxt] < cm[np.arange(len(t)), t])
            if not go.any():
                break
            t = np.where(go, t + 1, t)
        ok = has & (t >= 1) & (t < tmax)
        r = np.arange(len(t))[ok]
        tt = t[ok]
        c0, c1, c2 = cm[r, tt - 1], cm[r, tt], cm[r, tt + 1]
        den = c0 - 2 * c1 + c2
        tf = tt + np.where(den != 0, 0.5 * (c0 - c2) / np.where(den != 0, den, 1), 0)
        out[idx[ok]] = sr / tf
    return out


def pitch_stats(src, sr=SR):
    """一段人声（文件路径，或 sr 采样率的数组）的音高：中位数、10%–90% 范围、有声秒数。量不到就是 None。"""
    import numpy as np
    x = read_audio(src, sr) if isinstance(src, (str, Path)) else np.asarray(src, dtype=np.float64)
    f = f0_track(x, sr)
    v = f[~np.isnan(f)] if len(f) else f
    if not len(v):
        return {"音高中位数Hz": None, "音高10%–90%Hz": None, "有声秒数": 0.0}
    return {"音高中位数Hz": round(float(np.median(v)), 1),
            "音高10%–90%Hz": [round(float(np.percentile(v, 10)), 1), round(float(np.percentile(v, 90)), 1)],
            "有声秒数": round(len(v) * 0.02, 2)}


def semitones(hz, ref_hz):
    import math
    return 12 * math.log2(hz / ref_hz)


def speech_rate(text, seconds):
    """语速：字／秒（一个汉字、一个英文词、一个数字位各算一个，和对稿同一种数法；秒数是去掉首尾静音后的整段）。"""
    return len(tokens(text)) / seconds if seconds else None


def gate_settings(profile=None):
    """profile"音高把关"一节的阈值（没写的用本文件的默认值）。"""
    d = _load_profile(profile).get("音高把关") or {}
    return {"允许偏差半音": float(d.get("允许偏差半音", PITCH_TOL_ST)),
            "最多再录": int(d.get("最多再录", PITCH_RETAKES)),
            "有声不足秒不判": float(d.get("有声不足秒不判", PITCH_MIN_VOICED_S)),
            "语速允许偏差": float(d.get("语速允许偏差", RATE_TOL))}


def _load_profile(profile=None):
    if isinstance(profile, dict):
        return profile
    p = Path(profile) if profile else PROFILE
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def reference_for(cfg, profile=None, raised=None):
    """按配音配置在声音档案里找这个声音的参考音高、参考语速：{"音高Hz", "语速", "来自"}；找不到返回 None（不把关）。
    主声音（同一个声音 ID）分两档：语气里带了"抬高"那一句就用"带抬高那句"，没带就用"不带抬高那句"；
    raised 给了 True/False 就按它，不看语气。MiMo 声音复刻按参考音文件名对上备用声音。"""
    prof = _load_profile(profile)
    voice, clone = getattr(cfg, "voice", None), getattr(cfg, "clone_ref", None)
    for name, sec in prof.items():
        if not isinstance(sec, dict) or not isinstance(sec.get("参考"), dict):
            continue
        ref = sec["参考"]
        hit = (voice and sec.get("声音ID") == voice) or \
              (clone and sec.get("参考音") and Path(str(sec["参考音"])).name == Path(str(clone)).name)
        if not hit:
            continue
        if "带抬高那句" in ref:
            suffix = (sec.get("每章语气后面都加这一句") or "").strip()
            up = raised if raised is not None else bool(suffix and suffix in (getattr(cfg, "style", None) or ""))
            r = ref["带抬高那句" if up else "不带抬高那句"]
            return {"音高Hz": r.get("音高Hz"), "语速": r.get("语速字每秒"),
                    "来自": f"{name}（{'带' if up else '不带'}抬高那句）：{r.get('来自', '')}"}
        return {"音高Hz": ref.get("音高Hz"), "语速": ref.get("语速字每秒"), "来自": f"{name}：{ref.get('来自', '')}"}
    return None


def pitch_verdict(stats, ref_hz, tol=PITCH_TOL_ST, min_voiced=PITCH_MIN_VOICED_S):
    """音高把关的判断：{"音高中位数Hz", "参考Hz", "偏差半音", "超出", "说明"}。有声太短或量不到时不判（超出=False）。"""
    hz, vs = stats.get("音高中位数Hz"), stats.get("有声秒数") or 0
    out = {"音高中位数Hz": hz, "参考Hz": ref_hz, "有声秒数": vs, "偏差半音": None, "超出": False}
    if not ref_hz:
        out["说明"] = "没有参考音高，不判"
    elif not hz or vs < min_voiced:
        out["说明"] = f"有声只有 {vs:.1f} 秒，量不准，不判"
    else:
        st = semitones(hz, ref_hz)
        out["偏差半音"] = round(st, 2)
        out["超出"] = abs(st) > tol
        if out["超出"]:
            out["说明"] = f"比参考{'高' if st > 0 else '低'} {abs(st):.1f} 个半音（允许 {tol:g}）"
    return out


def rate_verdict(text, seconds, ref_rate, tol=RATE_TOL):
    """语速：{"字每秒", "参考", "相差", "标出"}；只标出，不重录。"""
    r = speech_rate(text, seconds)
    out = {"字每秒": round(r, 2) if r else None, "参考": ref_rate, "相差": None, "标出": False}
    if r and ref_rate:
        d = r / ref_rate - 1
        out["相差"] = f"{d * 100:+.0f}%"
        out["标出"] = abs(d) > tol
    return out


# ---------------------------------------------------------------- 整段一次合成后按章切开（2026-11-01 加）


def transcribe_words(wav_path, work_dir, prompt=""):
    """逐词时间：[{"w": 词, "s": 起秒, "e": 止秒}]。设置和 transcribe 一样，另开 --word-timestamps。
    结果按音频文件名存在 work_dir（和 transcribe 的 json 不同名），再调直接读。"""
    wav_path, work = Path(wav_path), Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    name = wav_path.stem + "_words"
    out = work / f"{name}.json"
    if not out.exists():
        env = dict(os.environ, HF_HUB_OFFLINE="1")
        for k in ("MIMO_API_KEY", "GCP_ACCESS_TOKEN", "GEMINI_API_KEY"):
            env.pop(k, None)
        cmd = [str(WHISPER_BIN), str(wav_path), "--model", WHISPER_MODEL, "--language", "zh",
               "--condition-on-previous-text", "False", "--word-timestamps", "True", "--output-format", "json",
               "--output-dir", str(work), "--output-name", name, "--verbose", "False"]
        if prompt:
            cmd += ["--initial-prompt", prompt]
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if r.returncode or not out.exists():
            raise RuntimeError(f"Whisper（逐词）失败：{(r.stderr or r.stdout)[-400:]}")
    d = json.loads(out.read_text(encoding="utf-8"))
    return [{"w": w["word"].strip(), "s": float(w["start"]), "e": float(w["end"])}
            for seg in d.get("segments", []) for w in seg.get("words", []) if w["word"].strip()]


def chapter_cuts(texts, words, x, sr=SR, quiet_db=-45.0, pad=0.35):
    """整段录音按章切开：texts 是各章念的字（念法），words 是 transcribe_words 的结果，x 是整段音频（sr 采样率）。
    做法：两边都拉成同一种写法（tokens），逐字对齐（difflib）；第 i 章最后一个对上的字说完、第 i+1 章第一个对上的字开口，
    在这两个时刻之间（前后各放宽 pad 秒）找最长的一段静音（10 毫秒一窗，低于 quiet_db），切在它正中间。
    返回 [{"秒": 切点, "静音秒": 这段静音多长, "上章末字止": …, "下章首字起": …, "对上": True/False}]，共 len(texts)-1 个。"""
    import difflib
    import numpy as np
    ref, owner = [], []
    for i, t in enumerate(texts):
        tk = tokens(t)
        ref += tk
        owner += [i] * len(tk)
    hyp, times = [], []
    for w in words:
        tk = tokens(w["w"])
        for k, c in enumerate(tk):
            a = w["s"] + (w["e"] - w["s"]) * k / len(tk)
            hyp.append(c)
            times.append((a, w["s"] + (w["e"] - w["s"]) * (k + 1) / len(tk)))
    hit = {}
    for a, b, n in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_matching_blocks():
        for k in range(n):
            hit[a + k] = times[b + k]
    win = int(sr * 0.01)
    m = len(x) // win
    db = 20 * np.log10(np.sqrt((x[:m * win].reshape(m, win) ** 2).mean(axis=1)) + 1e-9)
    total = len(x) / sr
    cuts = []
    for i in range(len(texts) - 1):
        last = [hit[k] for k in range(len(ref)) if owner[k] == i and k in hit]
        first = [hit[k] for k in range(len(ref)) if owner[k] == i + 1 and k in hit]
        e_i = last[-1][1] if last else None
        s_n = first[0][0] if first else None
        lo = (e_i if e_i is not None else (s_n or 0) - 2.0) - pad
        hi = (s_n if s_n is not None else (e_i or total) + 2.0) + pad
        if hi <= lo:
            lo, hi = hi - pad, lo + pad
        a, b = max(0, int(lo / 0.01)), min(m, int(hi / 0.01) + 1)
        best, run_start = (0, None), None
        for j in range(a, b + 1):
            q = j < b and db[j] < quiet_db
            if q and run_start is None:
                run_start = j
            elif not q and run_start is not None:
                if j - run_start > best[0]:
                    best = (j - run_start, run_start)
                run_start = None
        if best[1] is None:                       # 一点静音都没有：切在这一段里最安静的一窗
            j = a + int(np.argmin(db[a:b])) if b > a else int(((e_i or 0) + (s_n or 0)) / 2 / 0.01)
            cut, quiet = j * 0.01 + 0.005, 0.0
        else:
            cut, quiet = (best[1] + best[0] / 2) * 0.01, best[0] * 0.01
        cuts.append({"秒": round(cut, 3), "静音秒": round(quiet, 2),
                     "上章末字止": round(e_i, 2) if e_i is not None else None,
                     "下章首字起": round(s_n, 2) if s_n is not None else None,
                     "对上": e_i is not None and s_n is not None and (e_i - 0.15) <= cut <= (s_n + 0.15)})
    return cuts


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3:
        ref = Path(sys.argv[1]).read_text(encoding="utf-8")
        hyp = transcribe(sys.argv[2])
        print(json.dumps(check(ref, hyp), ensure_ascii=False, indent=1))
    else:
        print("用法：python pipeline/tts_qc.py 原稿.txt 音频.wav")
