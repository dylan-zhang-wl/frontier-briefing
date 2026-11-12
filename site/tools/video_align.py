#!/usr/bin/env python3
"""视频旁白逐字对齐：Whisper 逐词时间 ＋ 视频稿原文 → 每个字、每句、每个关键词在音频里的时刻。

为什么要对齐而不是直接用转写：转写有错字、数字写成阿拉伯数字（“300亿”），画面要按稿子上的字出现；
所以把转写里的数字换成汉字读法（300 → 三百、28.58% → 百分之二十八点五八），再和稿子逐字比对（difflib），
比上的字用转写的时间，没比上的字按前后已知时间线性插值。

精度自检：用 ffmpeg 的静音检测找出每次停顿后“重新开口”的时刻，和对齐结果里停顿后第一个字的时间比；
若整体偏早或偏晚，就把所有时间平移这个中位数（最多 0.3 秒），报告平移后的误差。

单独运行（看对齐结果，不写任何文件）：
    python site/tools/video_align.py 测试版/2026-10-31
组装脚本 build_v2.py 会调用 load_words() 和 align()。
"""
import difflib
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys

WHISPER_BIN = os.environ.get("FD_WHISPER_BIN") or os.path.expanduser("~/.venvs/digital-human/bin/mlx_whisper")   # FD_WHISPER_BIN：同 pipeline/tts_qc.py；没设时和原来一样
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
CJK = re.compile(r"[㐀-鿿豈-﫿]")
DIG = "零一二三四五六七八九"
SENT_END = "。！？；!?;"
CLAUSE_END = "，、：,:" + SENT_END


def is_unit(ch):
    """参与比对的字：汉字、字母、数字（标点和空格不参与）。"""
    return bool(CJK.match(ch)) or (ch.isascii() and ch.isalnum())


# ---------------------------------------------------------------- 数字 → 汉字读法
def _below_10k(n):
    s, zero = "", False
    for val, u in ((1000, "千"), (100, "百"), (10, "十"), (1, "")):
        d, n = divmod(n, val)
        if d:
            if zero:
                s += "零"
            s += DIG[d] + u
            zero = False
        elif s:
            zero = True
    return s


def int_zh(n):
    if n == 0:
        return "零"
    if n >= 10 ** 8:
        hi, lo = divmod(n, 10 ** 8)
        return int_zh(hi) + "亿" + (("零" if lo < 10 ** 7 else "") + int_zh(lo) if lo else "")
    if n >= 10 ** 4:
        hi, lo = divmod(n, 10 ** 4)
        s = _below_10k(hi) + "万"
        return s + (("零" if lo < 1000 else "") + _below_10k(lo) if lo else "")
    s = _below_10k(n)
    if s.startswith("一十"):
        s = s[1:]
    if n >= 100 and s.startswith("二"):
        s = "两" + s[1:]          # 200 读“两百”，和稿子的写法一致
    return s


def num_zh(tok):
    """'28.58%' → '百分之二十八点五八'；'1.25' → '一点二五'；'300' → '三百'"""
    pct = tok.endswith("%")
    tok = tok.rstrip("%")
    whole, _, frac = tok.partition(".")
    s = int_zh(int(whole or 0)) + ("点" + "".join(DIG[int(c)] for c in frac) if frac else "")
    return ("百分之" if pct else "") + s


# ---------------------------------------------------------------- Whisper
def file_sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load_words(audio, cache, prompt=""):
    """逐词时间 [{w, s, e}]。优先用配音目录里流水线留下的 words.json；其次用缓存（音频指纹一致才用）；
    都没有就在本机跑 Whisper（mlx_whisper，离线），结果写进缓存。跑不了时返回 None。"""
    sha = file_sha1(audio)
    side = os.path.join(os.path.dirname(audio), "words.json")
    for p in (side, cache):
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            if d.get("audio_sha1") in (None, sha) and d.get("words"):
                return d
    if not os.path.exists(WHISPER_BIN):
        return None
    tmp = os.path.join(os.path.dirname(cache), "_whisper")
    os.makedirs(tmp, exist_ok=True)
    cmd = [WHISPER_BIN, audio, "--model", WHISPER_MODEL, "--word-timestamps", "True", "--language", "zh",
           "--output-format", "json", "--output-dir", tmp, "--condition-on-previous-text", "False", "--verbose", "False"]
    if prompt:
        cmd += ["--initial-prompt", prompt]
    subprocess.run(cmd, check=True, capture_output=True, env=dict(os.environ, HF_HUB_OFFLINE="1"))
    raw = json.load(open(os.path.join(tmp, os.path.splitext(os.path.basename(audio))[0] + ".json"), encoding="utf-8"))
    d = whisper_to_words(raw, sha)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
    for x in os.listdir(tmp):
        os.remove(os.path.join(tmp, x))
    os.rmdir(tmp)
    return d


def whisper_to_words(raw, sha=None):
    words = [{"w": w["word"].strip(), "s": round(w["start"], 3), "e": round(w["end"], 3)}
             for seg in raw.get("segments", []) for w in seg.get("words", []) if w["word"].strip()]
    return {"engine": "mlx-whisper " + WHISPER_MODEL.split("/")[-1], "word_timestamps": True, "language": "zh",
            "audio_sha1": sha, "text": raw.get("text", ""), "words": words}


# ---------------------------------------------------------------- 对齐
def transcript_units(words):
    """转写 → [(字, 起, 止)]：词内按字数均分时间；数字串换成汉字读法后再均分。"""
    chars = []
    for w in words:
        cs = [c for c in w["w"] if is_unit(c) or c in ".%"]
        n = len(cs)
        for k, c in enumerate(cs):
            chars.append((c.lower(), w["s"] + (w["e"] - w["s"]) * k / n, w["s"] + (w["e"] - w["s"]) * (k + 1) / n))
    s = "".join(c for c, _, _ in chars)
    out, i = [], 0
    for m in re.finditer(r"\d+(?:\.\d+)?%?|[.%]", s):
        out += chars[i:m.start()]
        i = m.end()
        if not m.group()[0].isdigit():
            continue
        reading = num_zh(m.group())
        t0, t1 = chars[m.start()][1], chars[m.end() - 1][2]
        n = len(reading)
        out += [(c, t0 + (t1 - t0) * k / n, t0 + (t1 - t0) * (k + 1) / n) for k, c in enumerate(reading)]
    out += chars[i:]
    return out


def silence_ends(audio, noise="-38dB", dur=0.12):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", audio, "-af", f"silencedetect=noise={noise}:d={dur}",
                        "-f", "null", "-"], capture_output=True, text=True)
    return [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", r.stderr)]


def align(narrations, words, audio=None, duration=None, bounds=None):
    """narrations：各场景旁白原文（稿子）；words：load_words() 的结果；
    bounds：各场景音频块的起点（配音目录 chapters.json），场景第一个字不会早于它。
    返回 {units, sentences, cues, scenes, accuracy, ...}；units 是稿子里每个参与比对的字及其起止秒。"""
    A, pos = [], []                       # 稿子的字；它在第几场景、文中第几个字
    for si, text in enumerate(narrations):
        for ci, ch in enumerate(text or ""):
            if is_unit(ch):
                A.append(ch.lower())
                pos.append((si, ci))
    B = transcript_units(words["words"])
    times = [None] * len(A)
    matched = 0
    sm = difflib.SequenceMatcher(None, A, [c for c, _, _ in B], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = [B[j1 + k][1], B[j1 + k][2]]
            matched += i2 - i1
        elif tag == "replace":          # 错字：把这几个稿子字铺在转写那几个字的时间上
            t0, t1, n = B[j1][1], B[j2 - 1][2], i2 - i1
            for k in range(n):
                times[i1 + k] = [t0 + (t1 - t0) * k / n, t0 + (t1 - t0) * (k + 1) / n]
    # 没比上的字：在前后已知时间之间线性插值
    end_all = duration or (B[-1][2] if B else 0)
    i = 0
    while i < len(A):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(A) and times[j] is None:
            j += 1
        t0 = times[i - 1][1] if i > 0 else 0.0
        t1 = times[j][0] if j < len(A) else end_all
        n = j - i
        for k in range(n):
            times[i + k] = [t0 + (t1 - t0) * k / n, t0 + (t1 - t0) * (k + 1) / n]
        i = j

    # 精度自检：停顿后“重新开口”的时刻 vs 停顿后第一个字的对齐时间
    first_after_pause = set()
    for k in range(len(A)):
        si, ci = pos[k]
        prev = narrations[si][:ci].rstrip()
        if k == 0 or pos[k - 1][0] != si or (prev and prev[-1] in CLAUSE_END):
            first_after_pause.add(k)
    sil = [x for x in (silence_ends(audio) if audio else []) if not duration or x <= duration - 0.2]
    diffs = []
    for x in sil:
        cand = [(abs(times[k][0] - x), times[k][0] - x) for k in first_after_pause]
        if cand and min(cand)[0] <= 0.45:
            diffs.append(min(cand)[1])
    offset = 0.0
    if len(diffs) >= 4:
        med = statistics.median(diffs)
        if abs(med) >= 0.03:
            offset = max(-0.3, min(0.3, -med))
    for t in times:
        t[0] = max(0.0, t[0] + offset)
        t[1] = max(0.0, t[1] + offset)
    # 停顿后的第一个字：吸附到实测的开口时刻（±0.6 秒内最近的一次），场景第一个字不早于该场景音频块的起点
    errs, snapped = [], 0
    for k in sorted(first_after_pause):
        si = pos[k][0]
        lo = times[k - 1][0] + 0.05 if k > 0 else 0.0
        if bounds and si < len(bounds) and (k == 0 or pos[k - 1][0] != si):
            lo = max(lo, bounds[si])
        hi = times[k + 1][0] - 0.03 if k + 1 < len(A) else (duration or 1e9)
        near = [x for x in sil if abs(x - times[k][0]) <= 0.6]
        if near:
            errs.append(min(abs(x - times[k][0]) for x in near))
        ok = [x for x in near if lo <= x <= hi]
        if ok:
            x = min(ok, key=lambda x: abs(x - times[k][0]))
            snapped += 1
        elif times[k][0] < lo <= hi:
            x = lo
        else:
            continue
        times[k][0] = x
        times[k][1] = max(times[k][1], x + 0.05)
        if k > 0:
            times[k - 1][1] = min(times[k - 1][1], x)
    # 场景开头不止一个字被 Whisper 放进了分界之前（章间停顿里）：上面只挪得动第一个字，这里把剩下的整串推到分界之后，先后不乱
    if bounds:
        for k in range(len(A)):
            si = pos[k][0]
            if si >= len(bounds) or times[k][0] >= bounds[si] - 1e-6:
                continue
            same = k > 0 and pos[k - 1][0] == si
            lo = max(bounds[si], times[k - 1][0] + 0.05) if same else bounds[si]
            times[k][0] = lo
            times[k][1] = max(times[k][1], lo + 0.05)
            if same:
                times[k - 1][1] = lo
    for t in times:
        t[0], t[1] = round(t[0], 3), round(t[1], 3)
    errs.sort()
    acc = {"matched_ratio": round(matched / max(1, len(A)), 3), "units": len(A), "offset_applied": round(offset, 3),
           "onset_checks": len(errs), "snapped_to_onset": snapped,
           "note": "误差＝停顿后第一个字的 Whisper 时间（已整体平移）与实测开口时刻之差；这些字随后已吸附到实测时刻，句中其他字仍用 Whisper 时间"}
    if errs:
        acc.update(median_abs_err=round(statistics.median(errs), 3), p90_abs_err=round(errs[int(0.9 * (len(errs) - 1))], 3),
                   max_abs_err=round(errs[-1], 3))

    units = [{"c": A[k], "scene": pos[k][0], "i": pos[k][1], "s": times[k][0], "e": times[k][1]} for k in range(len(A))]
    return {"version": 1, "engine": words.get("engine"), "accuracy": acc, "duration": duration,
            "units": units, "narrations": list(narrations),
            "scenes": scene_spans(units, narrations), "sentences": spans(units, narrations, SENT_END),
            "cues": subtitle_cues(units, narrations, duration)}


def char_times(units, narrations):
    """每个场景旁白里每个字（含标点）的起始秒：标点取前一个字的结束。"""
    by = {}
    for u in units:
        by[(u["scene"], u["i"])] = u
    out = []
    for si, text in enumerate(narrations):
        row, last = [], None
        for ci, ch in enumerate(text or ""):
            u = by.get((si, ci))
            if u:
                row.append(u["s"])
                last = u["e"]
            else:
                row.append(last)
        nxt = None                          # 场景开头的标点（如“《”）取后一个字的开始
        for ci in range(len(row) - 1, -1, -1):
            if row[ci] is None:
                row[ci] = nxt
            elif by.get((si, ci)):
                nxt = row[ci]
        out.append(row)
    return out


def spans(units, narrations, enders):
    ct = char_times(units, narrations)
    ends = {(u["scene"], u["i"]): u["e"] for u in units}
    out = []
    for si, text in enumerate(narrations):
        buf, a = "", None
        for ci, ch in enumerate(text or ""):
            if a is None and (si, ci) in ends:
                a = ci
            buf += ch
            if ch in enders or ci == len(text) - 1:
                if a is not None and buf.strip():
                    last = max(k for k in range(a, ci + 1) if (si, k) in ends)
                    out.append({"scene": si, "text": buf.strip(), "start": ct[si][a], "end": ends[(si, last)]})
                buf, a = "", None
    return out


def scene_spans(units, narrations):
    out = []
    for si in range(len(narrations)):
        us = [u for u in units if u["scene"] == si]
        if us:
            out.append({"scene": si, "start": us[0]["s"], "end": us[-1]["e"]})
    return out


def wlen(s):
    return sum(1.0 if CJK.match(c) else 1.1 if c.isdigit() else 0.35 if c.isascii() and c.isalpha() else 0.5 for c in s)


def subtitle_cues(units, narrations, duration, maxw=18.0):
    """字幕：按句切，长句再按逗号切成不超过约 18 字的小段；每段带每个字的起始秒（卡拉 OK 逐字变亮用）。"""
    ct = char_times(units, narrations)
    ends = {(u["scene"], u["i"]): u["e"] for u in units}
    cues = []
    for si, text in enumerate(narrations):
        text = text or ""
        clauses, a = [], 0
        for ci, ch in enumerate(text):
            # 数字里的千分位逗号（5,000）不是停顿，不在这里断开字幕
            if ch == "," and 0 < ci < len(text) - 1 and text[ci - 1].isdigit() and text[ci + 1].isdigit():
                continue
            if ch in CLAUSE_END or ci == len(text) - 1:
                clauses.append((a, ci + 1))
                a = ci + 1
        groups, cur = [], None
        for a, b in clauses:
            seg = text[a:b]
            if cur and wlen(text[cur[0]:cur[1]] + seg) <= maxw and text[cur[1] - 1] not in SENT_END:
                cur = (cur[0], b)
            else:
                if cur:
                    groups.append(cur)
                cur = (a, b)
        if cur:
            groups.append(cur)
        for a, b in groups:
            while a < b and text[a] == " ":
                a += 1
            ks = [k for k in range(a, b) if (si, k) in ends]
            if not ks:
                continue
            seg = text[a:b].rstrip()
            cues.append({"scene": si, "text": seg, "start": ct[si][ks[0]], "end": ends[(si, ks[-1])],
                         "t": [round(ct[si][k], 3) for k in range(a, a + len(seg))]})
    for k, c in enumerate(cues):            # 字幕停留到下一段开始（最多多留 0.8 秒）
        nxt = cues[k + 1]["start"] if k + 1 < len(cues) else (duration or c["end"] + 0.8)
        c["end"] = round(min(max(c["end"] + 0.15, nxt - 0.05), c["end"] + 0.8, nxt), 3)
    return cues


def norm(s):
    return "".join(c.lower() for c in (s or "") if is_unit(c))


def find(al, phrase, after=0.0, scene=None):
    """在稿子里找关键词（忽略标点和空格），返回 (开始秒, 结束秒, 字序号)；after 之前出现的不算。找不到返回 None。"""
    key = norm(phrase)
    if not key:
        return None
    units = al["units"]
    flat = "".join(u["c"] for u in units)
    i = flat.find(key)
    while i >= 0:
        u0, u1 = units[i], units[i + len(key) - 1]
        if u0["s"] >= after - 1e-6 and (scene is None or u0["scene"] == scene):
            return u0["s"], u1["e"], i
        i = flat.find(key, i + 1)
    return None


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    issue = os.path.join(root, sys.argv[1])
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    script = json.load(open(os.path.join(issue, "04_文稿", "claude_视频_定时.json"), encoding="utf-8"))
    audio = os.path.join(issue, "05_配音", "视频旁白_claude稿", "episode.mp3")
    cache = sys.argv[2] if len(sys.argv) > 2 else os.path.join(issue, "08_网页v2", "issues", os.path.basename(issue), "video", "whisper_words.json")
    words = load_words(audio, cache)
    al = align([s["narration_zh"] for s in script["scenes"]], words, audio, script.get("duration"))
    print(json.dumps(al["accuracy"], ensure_ascii=False))
    for c in al["cues"]:
        print("%6.2f–%6.2f  %s" % (c["start"], c["end"], c["text"]))
