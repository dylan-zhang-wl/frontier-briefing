#!/usr/bin/env python3
"""frontier-daily 播客混音：每章人声 + 声音包装（片头曲、底乐、转场音、片尾曲）→ 整集 MP3。

用法（在项目根运行）：
    PY=~/.venvs/frontier-daily/bin/python
    # 1) 先配音，加 --chapter-wavs 另存每章人声（缓存里已有的块不重复花钱）
    $PY pipeline/tts.py 稿.md --engine gemini --voice voice_… --style-map 稿_语气.json \
        --chapter-wavs --out 产出/人声
    # 2) 再混音：读人声目录 qc.json 里记的每章 WAV，配上 pipeline/assets/music/ 的素材
    $PY pipeline/podcast_mix.py 产出/人声 --out 产出/带音效 --title "每日AI科技前沿简报 · 2026年10月31日"
    #   --reviewed：稿子已人工审过，音频文件信息里的 AI 声明写"经人工审核"
    #   --music 目录：换一套声音包装（目录里要有 intro / bed / stinger / outro 四个 .flac 或 .wav）
    # 3) v3 起用声音包（不加 --package 就还是下面写的 v2 做法，产出和以前一模一样）：
    $PY pipeline/podcast_mix.py 产出/人声 --out 产出/带音效 --package v3            # 读 assets/music/v3/包.json
    #   --package v3/A、v3/B：指定方向；--intro 6s|10s：片头版本；--bed-db -29：说话时底乐比人声低多少 dB；
    #   --excerpt 0:120：只出前 2 分钟试听（也能写 要闻-25:要闻+20、片尾-30:末）。
    #   声音包怎么摆见文件后半"v3 起：声音包"一节和 assets/music/v3/README.md。
    #   第十一轮（11-02）加了"自动避让"的两个包：--package v3/D_原曲避让、v3/E_新底乐避让。11-02 晚起 包.json 基于 E（《Dreamer》底乐＋避让），
#   不加 /方向 的 --package v3 就是 E；以前的默认 B2 用 --package v3/B2 复现；
    #   --stems 目录：另存人声、底乐、其余音乐三轨，测量用。

结构（v2 做法）：
    片头曲 → 开场（片头曲淡出时人声进来，底乐垫着）→ 转场音 → 热点一 → 转场音 → 热点二 → … →
    今日一词（垫一层很轻的底乐）→ … → 结尾（最后一秒多人声下面淡入片尾曲）→ 片尾曲。
    "说话时底乐自动压低"用 ffmpeg 的 sidechaincompress（侧链压缩）：拿人声当控制信号，人声一响，
    音乐轨就按比例降下来，停顿时再慢慢回来。片头曲尾巴、两段底乐、片尾曲都走这条"会被压低"的轨；
    转场音放在人声的空档里，单走一条不压低的轨，免得它被上一句话的余量压瘪。
    各段音量按"相对人声整体响度多少 dB"来定（见 LEVEL_DB），换一期、换一个声音都不用重调。
    最后整集用 loudnorm 两遍法统一到 −16 LUFS（真峰值 ≤ −1 dBTP），编码成 96 kbps 立体声 MP3（44.1 kHz）；
    和 tts.py 一样，编码后再量一次，差 0.15 LU 以上就补一次增益重编。
章节表：开始时间算上了片头曲和转场音——开场从 0 秒开始，其余每章从它前面那声转场音开始。
    同样的章节也写进 MP3 的 ID3 章节帧（CHAP），播放器能直接跳。
AI 声明：不进口播，只写进 MP3 的音频文件信息（comment），节目说明和网页另写。

产出（--out 目录）：
    episode.mp3     整集，立体声 96 kbps
    chapters.json   每章开始秒数（Podcasting 2.0 章节格式）
    qc.json         时间线（每段从第几秒到第几秒）、各段音量、压低参数、整集响度、人声对稿摘要
    usage.json      配音用量（照搬人声目录的 usage.json 合计）+ 音乐素材的一次性花费
中间文件放 ~/.cache/frontier-daily/mix/（iCloud 之外），做完就删。
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
PIPE = Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

import tts                   # noqa: E402  （复用响度测量、ffmpeg 调用）

# ============================ 可改区 ============================

MUSIC = PIPE / "assets" / "music"
CACHE = Path.home() / ".cache/frontier-daily/mix"
SR = 44100
TARGET_LUFS = -16.0
TRUE_PEAK = -1.5            # loudnorm 的真峰值目标
FINAL_PEAK = -1.0           # 编码后补增益时真峰值的上限
BITRATE_KBPS = 96

# 各段音量：相对人声整体响度的 dB（人声 = 0）。底乐是"没被压低时"的音量，说话时还会再降约 10 dB。
LEVEL_DB = {"intro": -1.0, "outro": -2.0, "stinger": -4.0, "bed": -13.0, "bed_light": -18.0}
BED_FOR = {"开场": "bed", "今日一词": "bed_light"}     # 哪几章垫底乐、用哪一档
NO_STINGER_BEFORE = set()                              # 不想在某章前放转场音就把章名放进来

# 时间（秒）
VOICE_INTO_INTRO = 1.2      # 开场人声在片头曲最后这么多秒（淡出段）里进来
BED_LEAD = 0.6              # 底乐比人声早这么多秒进来
BED_FADE_IN = 1.5
BED_TAIL = 1.2              # 这一章说完后底乐再留多久
BED_FADE_OUT = 1.5
GAP_BEFORE_STINGER = 0.45   # 上一章说完到转场音开始
VOICE_INTO_STINGER = 0.35   # 下一章人声在转场音尾巴的最后这么多秒里进来
OUTRO_UNDER_VOICE = 1.6     # 片尾曲在结尾最后这么多秒人声下面淡入
END_PAD = 0.3

# 侧链压缩（ffmpeg sidechaincompress）：threshold 是人声电平的门槛（线性，0.03 ≈ −30 dBFS），ratio 是压缩比。
# 2026-10-31 用开场人声实测：0.02/4 说话段压低 16–20 dB（底乐几乎听不见），0.03/2 压低约 9.4 dB 且起伏最小，
# 取 0.03/2.5（约 10 dB）。release 长一点，句子之间的短停顿里音乐不会忽大忽小
DUCK = "threshold=0.03:ratio=2.5:attack=25:release=900:knee=3:link=average:detection=rms"

# ==============================================================


def _ffmpeg(args):
    return tts._ffmpeg(args)


def load(path, channels):
    """解码成 44.1 kHz float32，形状 (n,) 或 (n, 2)。"""
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-f", "f32le",
                        "-ac", str(channels), "-ar", str(SR), "-"], capture_output=True)
    if r.returncode:
        raise RuntimeError(f"读不了 {path}：{r.stderr.decode()[-300:]}")
    x = np.frombuffer(r.stdout, dtype=np.float32).copy()
    return x if channels == 1 else x.reshape(-1, 2)


def write_raw(x, path):
    path.write_bytes(np.ascontiguousarray(x, dtype=np.float32).tobytes())


def raw_input(path, channels):
    return ["-f", "f32le", "-ar", str(SR), "-ac", str(channels), "-i", str(path)]


def loud_of(x, tmp):
    """量一段数组的整体响度（LUFS）和真峰值。"""
    ch = 1 if x.ndim == 1 else 2
    write_raw(x, tmp)
    _ffmpeg(raw_input(tmp, ch) + ["-c:a", "pcm_f32le", str(tmp.with_suffix(".wav"))])
    m = tts.measure_loudness(tmp.with_suffix(".wav"))
    tmp.with_suffix(".wav").unlink(missing_ok=True)
    tmp.unlink(missing_ok=True)
    return m


def _kweight(sr=SR):
    """BS.1770 的 K 计权（两级双二阶滤波：高频搁架 + 高通），系数按采样率现算，和 pyloudnorm 的做法一样。"""
    G, Q, fc = 3.99984385397, 0.7071752369554193, 1681.9744509555319
    A, w0 = 10 ** (G / 40), 2 * np.pi * fc / sr
    al, c = np.sin(w0) / (2 * Q), np.cos(w0)
    shelf = ([A * ((A + 1) + (A - 1) * c + 2 * np.sqrt(A) * al), -2 * A * ((A - 1) + (A + 1) * c),
              A * ((A + 1) + (A - 1) * c - 2 * np.sqrt(A) * al)],
             [(A + 1) - (A - 1) * c + 2 * np.sqrt(A) * al, 2 * ((A - 1) - (A + 1) * c),
              (A + 1) - (A - 1) * c - 2 * np.sqrt(A) * al])
    Q2, fc2 = 0.5003270373253953, 38.13547087613982
    w0 = 2 * np.pi * fc2 / sr
    al, c = np.sin(w0) / (2 * Q2), np.cos(w0)
    hp = ([(1 + c) / 2, -(1 + c), (1 + c) / 2], [1 + al, -2 * c, 1 - al])
    return shelf, hp


def lufs(x, sr=SR, momentary_max=False):
    """在内存里量响度（LUFS，按广播标准 BS.1770：K 计权、400 毫秒一块、绝对门限 −70、相对门限 −10）。
    短素材、只取一部分（比如"只量说话时的底乐"）都能量，不用写文件；和 ffmpeg ebur128 对过，差 0.2 LU 以内。
    momentary_max=True 时返回"最响的 400 毫秒"有多响，用来摆翻页、杯碟这类很短的声音。"""
    from scipy.signal import lfilter
    x = np.asarray(x, dtype=np.float64)
    x = x[:, None] if x.ndim == 1 else x
    if len(x) == 0:
        return -70.0
    (b1, a1), (b2, a2) = _kweight(sr)
    y = lfilter(b2, a2, lfilter(b1, a1, x, axis=0), axis=0)
    n, hop = int(0.4 * sr), int((0.01 if momentary_max else 0.1) * sr)
    if len(y) < n:
        return -0.691 + 10 * np.log10((y ** 2).mean(axis=0).sum() + 1e-20)
    cs = np.concatenate([np.zeros((1, y.shape[1])), np.cumsum(y ** 2, axis=0)])
    st = np.arange(0, len(y) - n + 1, hop)
    z = ((cs[st + n] - cs[st]) / n).sum(axis=1)
    blk = -0.691 + 10 * np.log10(z + 1e-20)
    if momentary_max:
        return float(blk.max())
    z = z[blk > -70]
    if not len(z):
        return -70.0
    rel = -0.691 + 10 * np.log10(z.mean()) - 10
    return float(-0.691 + 10 * np.log10(z[-0.691 + 10 * np.log10(z) > rel].mean()))


def true_peak(x):
    """真峰值（dBTP）：先 4 倍过采样再取最大值，能抓到采样点之间的峰。"""
    from scipy.signal import resample_poly
    y = resample_poly(np.asarray(x, dtype=np.float64), 4, 1, axis=0)
    return float(20 * np.log10(np.abs(y).max() + 1e-12))


def find_asset(music, name):
    for ext in (".flac", ".wav"):
        p = Path(music) / f"{name}{ext}"
        if p.exists():
            return p
    raise FileNotFoundError(f"{music} 里没有 {name}.flac / {name}.wav")


def fades(x, fade_in=0.0, fade_out=0.0):
    x = x.copy()
    if fade_in:
        n = min(len(x), int(fade_in * SR))
        x[:n] *= (np.sin(np.linspace(0, np.pi / 2, n)) ** 2)[:, None]
    if fade_out:
        n = min(len(x), int(fade_out * SR))
        x[len(x) - n:] *= (np.cos(np.linspace(0, np.pi / 2, n)) ** 2)[:, None]
    return x


def looped(bed, seconds):
    n = int(seconds * SR)
    reps = int(np.ceil(n / len(bed)))
    return np.concatenate([bed] * reps)[:n]


class Track:
    """一条轨：把片段按秒数摆上去。"""

    def __init__(self, channels):
        self.channels, self.parts = channels, []

    def put(self, start, x, gain_db=0.0):
        self.parts.append((int(round(start * SR)), x * (10 ** (gain_db / 20))))

    def render(self, n):
        y = np.zeros((n,) if self.channels == 1 else (n, 2), dtype=np.float32)
        for s, x in self.parts:
            e = min(n, s + len(x))
            y[s:e] += x[:e - s]
        return y


def _master(mixed, work, out_dir, title, disclosure, chapters_out, total, bitrate, lra=11):
    """混好的 WAV → 成品 MP3（v2、v3 共用）：统一响度（loudnorm 两遍法，能线性就线性）→ 写音频文件信息和章节 →
    编码 → 再量一次，差 0.15 LU 以上补增益重编。返回 (MP3 路径, 成品响度, loudnorm 第二遍的报告, 编码后补的增益 dB)。
    lra：响度范围上限。素材起伏超过它，loudnorm 会改成动态压缩；只截一小段试听时（片尾曲的长余音占比大）放宽到 20。"""
    base = f"I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA={lra}"
    m = tts._last_json(_ffmpeg(["-i", str(mixed), "-af", f"loudnorm={base}:print_format=json", "-f", "null", "-"]))
    norm = work / "norm.wav"
    r = tts._last_json(_ffmpeg(["-i", str(mixed), "-af",
                                f"loudnorm={base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                                f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
                                f"offset={m['target_offset']}:linear=true:print_format=json",
                                "-ar", str(SR), "-c:a", "pcm_f32le", str(norm)]))
    ffmeta = work / "meta.txt"
    lines = [";FFMETADATA1", f"title={title}", "artist=每日AI科技前沿简报", "album=每日AI科技前沿简报（Daily AI & Tech Frontier Briefing）",
             f"date={datetime.now().strftime('%Y')}", f"comment={disclosure}"]
    for i, c in enumerate(chapters_out):
        end = chapters_out[i + 1]["startTime"] if i + 1 < len(chapters_out) else total
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(c['startTime'] * 1000)}",
                  f"END={int(end * 1000)}", f"title={c['title']}"]
    ffmeta.write_text("\n".join(x.replace("\n", " ") for x in lines) + "\n", encoding="utf-8")
    mp3 = out_dir / "episode.mp3"
    gain_db = 0.0
    for attempt in range(3):
        af = ["-af", f"volume={gain_db:.2f}dB"] if gain_db else []
        _ffmpeg(["-i", str(norm), "-i", str(ffmeta), "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1"]
                + af + ["-ac", "2", "-ar", str(SR), "-c:a", "libmp3lame", "-b:a", f"{bitrate}k", str(mp3)])
        loud = tts.measure_loudness(mp3)
        extra = TARGET_LUFS - loud["I"]
        if extra > 0:
            extra = min(extra, FINAL_PEAK - loud["TP"])
        if abs(extra) < 0.15 or attempt == 2:
            break
        gain_db = round(gain_db + extra, 2)
    return mp3, loud, r, gain_db


def mix(speech_dir, out_dir, music=MUSIC, title=None, reviewed=False, bitrate=BITRATE_KBPS, log=print):
    speech_dir, out_dir = Path(speech_dir), Path(out_dir)
    sq = json.loads((speech_dir / "qc.json").read_text(encoding="utf-8"))
    chaps = sq.get("章节人声")
    if not chaps:
        raise ValueError(f"{speech_dir}/qc.json 里没有\"章节人声\"：配音时要加 --chapter-wavs")
    missing = [c["文件"] for c in chaps if not Path(c["文件"]).exists()]
    if missing:
        raise FileNotFoundError("每章人声 WAV 找不到了（缓存可能已清）。重跑一遍 tts.py（加 --chapter-wavs；"
                                f"块有缓存，不花钱）。缺：{missing[:2]}")
    out_dir.mkdir(parents=True, exist_ok=True)
    work = CACHE / (tts._safe_name(out_dir.name) + datetime.now().strftime("_%H%M%S"))
    work.mkdir(parents=True, exist_ok=True)

    # 读素材、量响度
    assets, alevel = {}, {}
    for name in ("intro", "bed", "stinger", "outro"):
        p = find_asset(music, name)
        assets[name] = load(p, 2)
        alevel[name] = tts.measure_loudness(p)["I"]
    voices = [(c["章"], load(c["文件"], 1)) for c in chaps]
    # 人声整体响度（立体声两路相同，比单声道文件量出来高约 3 dB），音乐按它来摆
    vl = loud_of(np.concatenate([np.stack([v, v], axis=1) for _, v in voices]), work / "vl.f32")["I"]

    def gain(asset, level_key):
        return vl + LEVEL_DB[level_key] - alevel[asset]

    voice, duck, free = Track(1), Track(2), Track(2)
    timeline, chapters_out = [], []
    beat = 0.6                                           # 素材都是 100 BPM（见 assets/music/素材.json）
    meta_p = Path(music) / "素材.json"
    if meta_p.exists():
        bpm = [v.get("节拍BPM") for v in json.loads(meta_p.read_text(encoding="utf-8"))["成品"].values()]
        bpm = [b for b in bpm if b]
        if bpm:
            beat = 60 / float(np.median(bpm))

    intro = assets["intro"]
    t_intro = len(intro) / SR
    duck.put(0.0, intro, gain("intro", "intro"))
    timeline.append({"段": "片头曲", "开始秒": 0.0, "秒数": round(t_intro, 2)})
    t = 0.0                                              # 上一章人声结束的时刻
    for i, (name, v) in enumerate(voices):
        secs = len(v) / SR
        if i == 0:
            chap_start = 0.0
            vstart = t_intro - VOICE_INTO_INTRO
        elif name in NO_STINGER_BEFORE:
            chap_start = t + GAP_BEFORE_STINGER
            vstart = chap_start
        else:
            st = assets["stinger"]
            chap_start = t + GAP_BEFORE_STINGER
            free.put(chap_start, st, gain("stinger", "stinger"))
            timeline.append({"段": f"转场音（{name}前）", "开始秒": round(chap_start, 2),
                             "秒数": round(len(st) / SR, 2)})
            vstart = chap_start + len(st) / SR - VOICE_INTO_STINGER
        level = BED_FOR.get(name)
        if level:
            if i == 0:   # 开场：底乐对齐片头曲的拍子进来
                bstart = round((vstart - BED_LEAD) / beat) * beat
            else:
                bstart = vstart - BED_LEAD
            bend = vstart + secs + BED_TAIL
            bed = fades(looped(assets["bed"], bend - bstart), BED_FADE_IN, BED_FADE_OUT)
            duck.put(bstart, bed, gain("bed", level))
            timeline.append({"段": f"底乐（{name}，{'很轻' if level == 'bed_light' else '常规'}）",
                             "开始秒": round(bstart, 2), "秒数": round(bend - bstart, 2)})
        voice.put(vstart, v)
        timeline.append({"段": f"人声·{name}", "开始秒": round(vstart, 2), "秒数": round(secs, 2)})
        chapters_out.append({"startTime": round(chap_start, 2), "title": name})
        t = vstart + secs
    outro = assets["outro"]
    ostart = t - OUTRO_UNDER_VOICE
    duck.put(ostart, outro, gain("outro", "outro"))
    timeline.append({"段": "片尾曲", "开始秒": round(ostart, 2), "秒数": round(len(outro) / SR, 2)})
    total = max(t, ostart + len(outro) / SR) + END_PAD
    n = int(round(total * SR))
    timeline.sort(key=lambda r: r["开始秒"])

    # 三条轨写成原始浮点文件，交给 ffmpeg：人声复制成左右两路，音乐轨按人声压低，三路相加
    vp, dp, fp = work / "voice.f32", work / "duck.f32", work / "free.f32"
    write_raw(voice.render(n), vp)
    write_raw(duck.render(n), dp)
    write_raw(free.render(n), fp)
    mixed = work / "mix.wav"
    graph = ("[0:a]pan=stereo|c0=c0|c1=c0,asplit=2[v][sc];"
             f"[1:a][sc]sidechaincompress={DUCK}[ducked];"
             "[v][ducked][2:a]amix=inputs=3:normalize=0:duration=longest[out]")
    _ffmpeg(raw_input(vp, 1) + raw_input(dp, 2) + raw_input(fp, 2) +
            ["-filter_complex", graph, "-map", "[out]", "-c:a", "pcm_f32le", str(mixed)])

    disclosure = ("本节目由 AI 辅助生成，" + ("经人工审核，" if reviewed else "") +
                  "使用 AI 合成语音；片头曲、转场音、底乐和片尾曲由 Google Lyria 生成（带 AI 生成水印）。")
    mp3, loud, r, gain_db = _master(mixed, work, out_dir, title or out_dir.name, disclosure, chapters_out,
                                    total, bitrate)

    (out_dir / "chapters.json").write_text(json.dumps(
        {"version": "1.2.0", "chapters": chapters_out}, ensure_ascii=False, indent=1), encoding="utf-8")
    music_meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    speech_total = sum(len(v) for _, v in voices) / SR
    (out_dir / "qc.json").write_text(json.dumps({
        "生成于": stamp, "人声来源": str(speech_dir), "配音配置": sq.get("配置"),
        "人声对稿": sq.get("整集"),
        "整集": {"秒数": round(total, 1), "其中人声秒数": round(speech_total, 1),
                 "响度LUFS": round(loud["I"], 1), "真峰值dBTP": round(loud["TP"], 1),
                 "loudnorm方式": r.get("normalization_type"), "编码后补的增益dB": gain_db,
                 "格式": f"MP3 立体声 {bitrate} kbps {SR} Hz", "音频文件信息里的声明": disclosure},
        "混音": {"音量（相对人声dB）": LEVEL_DB, "人声整体响度LUFS（混音前）": round(vl, 1),
                 "垫底乐的章": BED_FOR, "压低（sidechaincompress）": DUCK,
                 "时间参数秒": {"人声进入片头曲尾巴": VOICE_INTO_INTRO, "底乐提前": BED_LEAD,
                             "底乐淡入": BED_FADE_IN, "底乐收尾": BED_TAIL, "底乐淡出": BED_FADE_OUT,
                             "转场音前空": GAP_BEFORE_STINGER, "人声进入转场音尾巴": VOICE_INTO_STINGER,
                             "片尾曲压在人声下": OUTRO_UNDER_VOICE},
                 "音乐素材目录": str(music), "音乐素材": music_meta.get("成品")},
        "时间线": timeline}, ensure_ascii=False, indent=1), encoding="utf-8")

    su = json.loads((speech_dir / "usage.json").read_text(encoding="utf-8")) if (speech_dir / "usage.json").exists() else {}
    gen_log = Path(music) / "lyria_raw" / "生成记录.json"
    gens = json.loads(gen_log.read_text(encoding="utf-8")) if gen_log.exists() else []
    (out_dir / "usage.json").write_text(json.dumps({
        "生成于": stamp,
        "配音": {"引擎": su.get("引擎"), "模型": su.get("模型"), "合计": su.get("合计"), "说明": su.get("说明")},
        "音乐素材（一次性，各期复用，不算进每期）": {
            "模型": sorted({g.get("模型") for g in gens}), "生成段数": len(gens),
            "估计费用美元": round(sum(g.get("估计费用美元") or 0 for g in gens), 2),
            "说明": "单价按第三方转引的 Gemini API 价目（lyria-3-clip $0.04/段），Vertex 价目页没抓到原文。"},
        "混音": "本机 ffmpeg，不花钱"}, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    log(f"  ✓ {mp3}  {total / 60:.1f} 分钟（人声 {speech_total / 60:.1f} 分钟），{loud['I']:.1f} LUFS，"
        f"峰 {loud['TP']:.1f} dBTP，{len(chapters_out)} 章")
    return {"mp3": str(mp3), "秒数": total, "chapters": chapters_out, "响度": loud}


# ============================ v3 起：声音包（--package） ============================
# 声音包 = 一个 JSON 配置（如 assets/music/v3/A.json）+ 它指向的几件素材 + 素材目录里的 素材.json。
# 和上面 v2 的做法比，改了这几处（依据见 文档/方案/改版计划_v3.md 第二节第 4 条，只在私有仓库）：
#   · 片头：先是约 2 秒生活声，再进一小句音乐（比人声低约 3 dB），人声在乐句淡下去时进来；6 秒、10 秒两版；
#   · 转场只放在配置"转场位置"写的几章前面（开场之后一处、两条热点讲完转到要闻时一处稍长的"桥段"）；
#     周末版（章名是"深度·…""深谈·…"）按配置"转场按章名开头"：第一个这样开头的章之前放一次桥段，全集只这一处（transition_places），
#     其余章之间只留一个自然停顿；
#   · 底乐从开场人声进来一直垫到片尾曲前：说话时约比人声低 29 dB，长一点的空隙里浮到约 −20 dB；
#     压低不用侧链压缩（压多少要看人声多响，不好控），改成按人声算一条音量曲线：10 毫秒一帧判断在不在说话，
#     说话前 0.3 秒开始压，停顿不到 1 秒不回升，再平滑——所以"说话时 −29 dB"是定死的数，换一期也一样；
#   · 片尾曲照旧：结尾最后 1.6 秒人声下面进来，人声没说完时再压 10 dB；
#   · 音量、时间都写在配置里，素材的参考响度和片头"人声几秒进来"记在 素材.json 里，换素材不用改代码。
# 2026-11-02 第十一轮加"避让"（配置里写了 "避让": {...} 才用，见 v3/D_原曲避让.json、E_新底乐避让.json 和 README 第十节）：
#   底乐用不滤波的原曲；说话时降到"底乐·说话时"，停顿够长就升到"底乐·空隙里"。和上面的压低比：
#   · 不靠平滑去"追"人声，而是按已知的人声起止画曲线：开口前提前降、开口那一刻已经降好；说完稍等再慢慢升；
#   · 停顿短于"最短停顿秒"整段不升；停顿不够长时只升一部分（升、降两段曲线取较低的），不会忽大忽小；
#   · 片头、转场、桥段的乐句响着时（一直到乐句结束），底乐压到"底乐·转场乐句下"，让乐句单独出来，结束后再升回。
#   不写"避让"的包（v3/A、B、B2）走原来的压低，结果逐采样不变。

FRAME = 0.01                # 压低曲线 10 毫秒一帧


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        if k != "基于":
            out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_package(name):
    """读声音包配置。可以给 JSON 路径，也可以给名字：v3 → assets/music/v3/包.json，v3/B → assets/music/v3/B.json。
    配置里写了"基于"，就先读那一份，再拿这一份逐项覆盖（嵌套的也逐项）。"""
    cands = [Path(name), MUSIC / f"{name}.json", MUSIC / name / "包.json"]
    path = next((c for c in cands if c.suffix == ".json" and c.is_file()), None)
    if path is None:
        raise FileNotFoundError(f"找不到声音包 {name}（试过 {'、'.join(str(c) for c in cands)}）")
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("基于"):
        spec = _merge(load_package(str(path.parent / spec["基于"])), spec)
    spec["_目录"], spec["_文件"] = str(path.parent), str(path)
    return spec


def _music_note(spec):
    """usage.json 里"音乐素材"那一段，按这一期实际用的声音包写（11-03 补：原来写死"Castles in the Sky"，
    11-02 起 包.json 指向 E（Kevin MacLeod《Dreamer》底乐）后就过时了）。配置链照"基于"一层层往下列。"""
    chain, p = [], Path(spec["_文件"])
    while p is not None and p.is_file() and len(chain) < 8:
        chain.append(p.name)
        nxt = json.loads(p.read_text(encoding="utf-8")).get("基于")
        p = p.parent / nxt if nxt else None
    out = {"声音包": spec.get("名称"), "配置": " → ".join(chain), "底乐文件": (spec.get("素材") or {}).get("底乐"),
           "说明": (spec.get("音乐说明") or "").rstrip("。") + "。都是现成素材剪的，这一期没有新生成，不花钱；"
                 "v2 那批 Lyria 5 段约 $0.20，当时已计。"}
    if spec.get("署名"):
        out["署名"] = spec["署名"]
    return out


def _pkg_meta(spec):
    """声音包目录里 素材.json 的"成品"记录；配置写了"另读素材记录"（第十一轮加，如 ["素材_避让.json"]）就一并读进来。"""
    meta = {}
    for name in ["素材.json"] + list(spec.get("另读素材记录") or []):
        p = Path(spec["_目录"]) / name
        if p.exists():
            meta.update(json.loads(p.read_text(encoding="utf-8"))["成品"])
    return meta


def _pkg_asset(spec, rel, meta):
    """读声音包里的一件素材和 素材.json 里它的记录；没记参考响度的（比如沿用的 v2 片尾曲）整件量，和 v2 摆法一样。"""
    p = (Path(spec["_目录"]) / rel).resolve()
    info = dict(meta.get(rel) or {})
    if info.get("参考响度LUFS") is None:
        info["参考响度LUFS"] = tts.measure_loudness(p)["I"]
    info["文件"] = str(p)
    return load(p, 2), info


def _looped_from(bed, seconds, offset):
    """把可循环的底乐接成 seconds 秒，从循环里第 offset 秒开始（offset 取循环末尾，开头就是"强拍前那一小段"）。"""
    n, o = int(round(seconds * SR)), int(round(offset * SR)) % len(bed)
    return np.concatenate([bed] * int(np.ceil((n + o) / len(bed))))[o:o + n]


def _fade_edges(x, fade_in, fade_out):
    """原地淡入淡出（和 fades 一样的曲线，不复制整条，省内存）。"""
    for secs, rising in ((fade_in, True), (fade_out, False)):
        k = min(len(x), int(secs * SR))
        if k:
            c = np.linspace(0, np.pi / 2, k)
            w = (np.sin(c) ** 2 if rising else np.cos(c) ** 2).astype(x.dtype)
            sl = slice(0, k) if rising else slice(len(x) - k, len(x))
            x[sl] *= w[:, None] if x.ndim == 2 else w
    return x


def _dilate(mask, back, fwd):
    """为真的帧往前扩 back 帧、往后扩 fwd 帧（"说话前先压""停顿短就不回升"）。"""
    d = np.zeros(len(mask) + 1, dtype=np.int64)
    idx = np.flatnonzero(mask)
    np.add.at(d, np.clip(idx - back, 0, len(mask)), 1)
    np.add.at(d, np.clip(idx + fwd + 1, 0, len(mask)), -1)
    return np.cumsum(d[:-1]) > 0


def _smooth_db(target, down, up):
    """每帧的目标音量（dB）→ 平滑曲线：往下走的时间常数 down 秒，往上走 up 秒。"""
    kd, ku = 1 - np.exp(-FRAME / max(down, 1e-3)), 1 - np.exp(-FRAME / max(up, 1e-3))
    out, g = np.empty(len(target)), float(target[0])
    for i, v in enumerate(target):
        g += (v - g) * (kd if v < g else ku)
        out[i] = g
    return out


def _runs(code):
    """整数数组里连续相同、且不为 0 的段：[(开始帧, 结束帧（不含）, 值)]。"""
    cut = np.flatnonzero(np.diff(code)) + 1
    starts, ends = np.r_[0, cut], np.r_[cut, len(code)]
    return [(int(a), int(b), int(code[a])) for a, b in zip(starts, ends) if code[a]]


def _avoid_curve(talk, holds, A, lv):
    """第十一轮"避让"：按人声起止画底乐的音量曲线（dB，每 10 毫秒一帧）。
    talk：每帧在不在说话；holds：[(开始帧, 结束帧)] 片头、转场、桥段乐句响着的时候；A：配置里的"避让"；lv：音量dB。
    返回 (曲线, 每帧属于哪一档：0 空隙、1 说话（含没升起来的短停顿）、2 乐句下)。
    做法：①停顿短于"最短停顿秒"的整段算说话；②每段说话给一个上限：段内是"说话时"那一档，段前"降下秒"内从空隙档平滑降下
    （降好的时刻比开口早"降好提前秒"），段后等"回升等待秒"再用"回升秒"平滑升回空隙档；所有上限取最低——停顿不够长时
    升、降两段曲线在半路相遇，只升一部分；③乐句下：从当时的音量用"降下秒"降到"转场乐句下"那一档（降好也比乐句早
    "降好提前秒"），乐句结束后等"回升等待秒"再用"回升秒"往空隙档升，和②取最低；④轻轻抹平拐角（"平滑秒"）。
    曲线都是"升余弦"（起止两头都是平的），按 dB 走，听起来是匀速的推子。"""
    nf = len(talk)
    sp, gp, hp = lv["底乐·说话时"], lv["底乐·空隙里"], lv.get("底乐·转场乐句下", lv["底乐·说话时"])
    fall, rise = (max(1, int(round(A[k] / FRAME))) for k in ("降下秒", "回升秒"))
    lead, wait = int(round(A["降好提前秒"] / FRAME)), int(round(A["回升等待秒"] / FRAME))

    def rc(x):
        return (1 - np.cos(np.pi * np.clip(x, 0, 1))) / 2

    code = talk.astype(np.int8)
    for a, b in holds:
        code[max(0, a):min(nf, b)] = 2
    gap_min = int(round(A["最短停顿秒"] / FRAME))
    busy = _runs((code > 0).astype(np.int8))
    for (_, e0, _), (s1, _, _) in zip(busy[:-1], busy[1:]):
        if s1 - e0 < gap_min:
            code[e0:s1] = 1                                  # 短停顿：不升，按说话那一档
    runs = _runs(code)
    cap = np.full(nf, float(gp))
    for a, b, c in runs:                                 # ② 说话
        if c != 1:
            continue
        cap[a:b] = np.minimum(cap[a:b], sp)
        i0 = max(0, a - lead - fall)
        cap[i0:a] = np.minimum(cap[i0:a], sp + (gp - sp) * rc((a - lead - np.arange(i0, a)) / fall))
        i1 = min(nf, b + wait + rise)
        cap[b:i1] = np.minimum(cap[b:i1], sp + (gp - sp) * rc((np.arange(b, i1) - b - wait) / rise))
    for a, b, c in runs:                                 # ③ 乐句下（按时间先后，从当时的音量降）
        if c != 2:
            continue
        i0 = max(0, a - lead - fall)
        if a > i0:
            c0 = cap[i0]
            span = max(1, a - lead - i0)
            cap[i0:a] = np.minimum(cap[i0:a], c0 + (hp - c0) * rc((np.arange(i0, a) - i0) / span))
        cap[a:b] = np.minimum(cap[a:b], hp)
        i1 = min(nf, b + wait + rise)
        cap[b:i1] = np.minimum(cap[b:i1], hp + (gp - hp) * rc((np.arange(b, i1) - b - wait) / rise))
    k = int(round(A.get("平滑秒", 0.0) / FRAME)) | 1          # 取奇数，抹平时不错位
    if k >= 3:
        w = np.hanning(k + 2)[1:-1]
        cap = np.convolve(np.r_[np.full(k, cap[0]), cap, np.full(k, cap[-1])], w / w.sum(), "same")[k:-k]
    return cap, code


def _apply_db(x, start, curve_db, offset_db):
    """原地把 x（从第 start 秒开始）乘上按帧给的 dB 曲线（线性插值到每个采样点）再加 offset_db。分块算，省内存。"""
    s0, tf, step = int(round(start * SR)), np.arange(len(curve_db)) * FRAME, 1 << 20
    for a in range(0, len(x), step):
        b = min(len(x), a + step)
        g = (10 ** ((np.interp((s0 + np.arange(a, b)) / SR, tf, curve_db) + offset_db) / 20)).astype(x.dtype)
        x[a:b] *= g[:, None] if x.ndim == 2 else g
    return x


def _kframes(x):
    """K 计权后每 10 毫秒的均方能量（声道相加），分块滤波、带着滤波器状态往下接。量"只在说话时"这类不连续的部分用。"""
    from scipy.signal import lfilter
    (b1, a1), (b2, a2) = _kweight()
    x = x[:, None] if x.ndim == 1 else x
    hop = int(FRAME * SR)
    z1, z2, out = np.zeros((2, x.shape[1])), np.zeros((2, x.shape[1])), []
    for a in range(0, len(x), hop * 4096):
        y, z1 = lfilter(b1, a1, x[a:a + hop * 4096].astype(np.float64), axis=0, zi=z1)
        y, z2 = lfilter(b2, a2, y, axis=0, zi=z2)
        m = len(y) // hop
        out.append((y[:m * hop] ** 2).reshape(m, hop, -1).mean(axis=1).sum(axis=1))
    return np.concatenate(out)


def _lu(e, gated=True):
    """每 10 毫秒能量 → 响度（LUFS）。gated=True 按标准 400 毫秒一块、门限去掉静音；False 直接平均（量选出来的帧）。"""
    if not len(e):
        return None
    if not gated:
        return round(float(-0.691 + 10 * np.log10(e.mean() + 1e-20)), 1)
    cs = np.concatenate([[0.0], np.cumsum(e)])
    st = np.arange(0, max(1, len(e) - 40 + 1), 10)
    z = (cs[np.minimum(st + 40, len(e))] - cs[st]) / np.minimum(40, len(e) - st)
    z = z[-0.691 + 10 * np.log10(z + 1e-20) > -70]
    if not len(z):
        return None
    z = z[-0.691 + 10 * np.log10(z + 1e-20) > -0.691 + 10 * np.log10(z.mean()) - 10]
    return round(float(-0.691 + 10 * np.log10(z.mean())), 1)


def _excerpt_range(text, marks, total):
    """"0:120"、"要闻-25:要闻+20"、"片尾-30:末" → (开始秒, 结束秒)。章名、片尾（片尾曲开始处）、末 都能当锚点。"""
    import re

    def one(s, default):
        s = s.strip()
        if not s:
            return default
        try:
            return float(s)
        except ValueError:
            pass
        m = re.fullmatch(r"(.+?)([+-]\d+(?:\.\d+)?)?", s)
        key, off = m.group(1), float(m.group(2) or 0)
        if key == "末":
            return total + off
        if key not in marks:
            raise ValueError(f"--excerpt 里的「{key}」不是章名，也不是 片尾/末（能用：{'、'.join(marks)}、末）")
        return marks[key] + off

    a, b = (text.split(":", 1) + [""])[:2]
    a, b = max(0.0, one(a, 0.0)), min(total, one(b, total))
    if b - a < 1:
        raise ValueError(f"--excerpt {text} 太短（{a:.1f}–{b:.1f} 秒）")
    return a, b


def _speech(speech_dir):
    sq = json.loads((speech_dir / "qc.json").read_text(encoding="utf-8"))
    chaps = sq.get("章节人声")
    if not chaps:
        raise ValueError(f"{speech_dir}/qc.json 里没有\"章节人声\"：配音时要加 --chapter-wavs")
    missing = [c["文件"] for c in chaps if not Path(c["文件"]).exists()]
    if missing:
        raise FileNotFoundError("每章人声 WAV 找不到了（缓存可能已清）。重跑一遍 tts.py（加 --chapter-wavs；"
                                f"块有缓存，不花钱）。缺：{missing[:2]}")
    return sq, chaps


def transition_places(spec, names):
    """这期哪几章前面放转场：返回 ({章名: "转场"/"桥段"}, 按章名开头的规则用上了没有)。
    ①配置"转场位置"按章名写死的（工作日：热点一前转场、要闻前桥段）；②配置"转场按章名开头"（周末版，2026-11-01 晚加）：
    第一个以"深度""深谈"开头的章之前放一次；"只放这一处"为真时，用上了这条就不再按①放。开场那一章前面从来不放。"""
    where = {ch: kind for ch, kind in spec.get("转场位置", {}).items() if ch in names[1:]}
    rule = spec.get("转场按章名开头") or {}
    first = next((n for n in names[1:] if any(n.startswith(p_) for p_ in rule.get("开头") or [])), None)
    if not first:
        return where, False
    kind = rule.get("放") or "桥段"
    return ({first: kind} if rule.get("只放这一处") else dict(where, **{first: kind})), True


def package_seconds(chapters, package="v3", intro=None, overrides=None):
    """不混音、只算时间（2026-11-01 晚加，第十轮"按日子把关时长"用）：chapters＝[(章名, 人声秒数)]，按声音包配置排一遍时间线，
    返回整集秒数。排法和 mix_package 第 1 步一模一样（片头人声进入点、转场对拍子、章间停顿、片尾曲压在最后 1.6 秒下面、末尾留白），
    素材长度取 素材.json 的"秒数"，没记的用 ffprobe 量。只读配置和素材，不改任何东西。"""
    spec = load_package(package)
    if overrides:
        spec = _merge(spec, overrides)
    T, A = spec["时间秒"], spec["素材"]
    iv = intro or spec.get("片头默认", "6s")
    meta = _pkg_meta(spec)

    def info(rel):
        i = dict(meta.get(rel) or {})
        if i.get("秒数") is None:
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str((Path(spec["_目录"]) / rel).resolve())], capture_output=True, text=True)
            i["秒数"] = float(r.stdout.strip())
        return i
    intro_i, bed_i, outro_i = info(A["片头"][iv]), info(A["底乐"]), info(A["片尾"])
    names = [n for n, _ in chapters]
    where, _ = transition_places(spec, names)
    trans = {kind: info(A[kind]) for kind in set(where.values())}
    t_v0 = intro_i.get("人声进入秒", intro_i["秒数"] - 1.4)
    t_bed = intro_i.get("底乐进入秒", t_v0)
    beat = intro_i.get("每拍秒") or bed_i.get("每拍秒") or 0.6
    t = 0.0
    for i, (name, secs) in enumerate(chapters):
        kind = where.get(name) if i else None
        if i == 0:
            vstart = t_v0
        elif kind:
            ti = trans[kind]
            land = ti.get("落拍秒", 0.0)
            k = np.ceil((t + T["转场前停顿"] + land - t_bed) / beat - 1e-6)
            fig_end = t_bed + k * beat - land + ti.get("乐句结束秒", ti["秒数"])
            vstart = (fig_end - T["人声在转场最后这么多秒进来"] if kind == "转场" else fig_end + T["桥段后底乐单独浮起"])
        else:
            vstart = t + T["章间停顿"]
        t = vstart + secs
    ostart = t - T["片尾在最后这么多秒人声下面进来"]
    return max(t, ostart + outro_i["秒数"]) + T["末尾留白"]


def mix_package(speech_dir, out_dir, package="v3", intro=None, bed_db=None, excerpt=None, title=None,
                reviewed=False, bitrate=BITRATE_KBPS, log=print, overrides=None, stems=None):
    """v3 起的混音：按声音包配置摆片头、一两处转场、全程底乐和片尾（见上面"声音包"一节）。
    intro："6s" / "10s"，不给用配置里的"片头默认"；bed_db：说话时底乐比人声低多少 dB（如 −29），不给用配置里的；
    excerpt：只出一段试听（写法见 _excerpt_range），整集照样排，只是最后只截这一段去统一响度、编码。
    overrides：在声音包配置上再逐项覆盖（写法和配置文件一样，如 {"时间秒": {"章间停顿": 1.6}}），不给就和以前完全一样。
    周日对谈用它（dialog_tts.py 从 voice_profile.json"周日搭档"的"声音包调整"读）：对谈里换人的空白都不到 1 秒，
    底乐整章都压着；章与章之间留长一点，并在"压低"里写 "章与章之间不保持": true——上一章说完 0.15 秒就让底乐浮起来
    （平时要等 1 秒），下一章开口前 0.3 秒再压下去，段落之间音乐能透口气。
    stems：给一个目录，就把这一段（整集或 excerpt 那段，统一响度之前、没加首尾淡入淡出）分三轨另存成 32 位浮点 WAV：
    人声.wav、底乐.wav（带避让起伏）、其余音乐.wav（片头、转场、桥段、片尾），量"底乐比人声低多少"、做"只有底乐"的试听用。
    不给就和以前完全一样。"""
    spec = load_package(package)
    if overrides:
        spec = dict(_merge(spec, overrides), _调整=overrides)
    lv = dict(spec["音量dB"])
    if bed_db is not None:
        lv["底乐·说话时"] = float(bed_db)
    T, D, A = spec["时间秒"], spec["压低"], spec["素材"]
    iv = intro or spec.get("片头默认", "6s")
    if iv not in A["片头"]:
        raise ValueError(f"声音包「{spec.get('名称')}」没有 {iv} 版片头（有：{'、'.join(A['片头'])}）")
    speech_dir, out_dir = Path(speech_dir), Path(out_dir)
    sq, chaps = _speech(speech_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = CACHE / (tts._safe_name(out_dir.name) + datetime.now().strftime("_%H%M%S"))
    work.mkdir(parents=True, exist_ok=True)

    meta = _pkg_meta(spec)
    intro_x, intro_i = _pkg_asset(spec, A["片头"][iv], meta)
    bed_x, bed_i = _pkg_asset(spec, A["底乐"], meta)
    outro_x, outro_i = _pkg_asset(spec, A["片尾"], meta)
    voices = [(c["章"], load(c["文件"], 1)) for c in chaps]
    vl = loud_of(np.concatenate([np.stack([v, v], axis=1) for _, v in voices]), work / "vl.f32")["I"]

    def gain(info, key):
        return vl + lv[key] - info["参考响度LUFS"]

    names = [nm for nm, _ in voices]
    where, by_prefix = transition_places(spec, names)
    if by_prefix:
        log(f"  转场：按章名开头放在「{next(iter(where))}」前（{next(iter(where.values()))}），全集这一处")
    else:
        for ch, kind in spec.get("转场位置", {}).items():
            if ch not in names[1:]:
                log(f"  注意：声音包要在「{ch}」前放{kind}，这期没有这一章（或它是第一章），这处不放")
    trans = {kind: _pkg_asset(spec, A[kind], meta) for kind in sorted(set(where.values()))}

    # —— 1) 排时间线 ——
    t_v0 = intro_i.get("人声进入秒", len(intro_x) / SR - 1.4)
    t_bed = intro_i.get("底乐进入秒", t_v0)              # 底乐的拍子从这里数（片头乐句结束的那一拍）
    beat = intro_i.get("每拍秒") or bed_i.get("每拍秒") or 0.6
    free, windows, spans, timeline, chapters_out = [], [], [], [], []
    holds = [(0.0, len(intro_x) / SR)]                   # "避让"用：片头、转场、桥段乐句响着的时候（到乐句结束）
    free.append((0.0, intro_x, gain(intro_i, "片头乐句"), "片头"))
    timeline.append({"段": f"片头（{iv}版，人声 {t_v0:.2f} 秒进来）", "开始秒": 0.0, "秒数": round(len(intro_x) / SR, 2)})
    t = 0.0                                              # 上一章人声结束的时刻
    for i, (name, v) in enumerate(voices):
        secs = len(v) / SR
        kind = where.get(name) if i else None
        if i == 0:
            vstart, chap_start = t_v0, 0.0
        elif kind:
            x, info = trans[kind]
            land = info.get("落拍秒", 0.0)
            k = np.ceil((t + T["转场前停顿"] + land - t_bed) / beat - 1e-6)
            tstart = t_bed + k * beat - land                 # 乐句的强拍落在底乐的拍子上
            fig_end = tstart + info.get("乐句结束秒", len(x) / SR)
            free.append((tstart, x, gain(info, kind), kind))
            windows.append((tstart, tstart + info.get("淡出开始秒", len(x) / SR), kind, tstart + land))
            holds.append((tstart, fig_end))
            vstart = (fig_end - T["人声在转场最后这么多秒进来"] if kind == "转场"
                      else fig_end + T["桥段后底乐单独浮起"])
            chap_start = tstart
            timeline.append({"段": f"{kind}（{name}前）", "开始秒": round(tstart, 2), "秒数": round(len(x) / SR, 2)})
        else:
            vstart = chap_start = t + T["章间停顿"]
        spans.append((vstart, vstart + secs))
        timeline.append({"段": f"人声·{name}", "开始秒": round(vstart, 2), "秒数": round(secs, 2)})
        chapters_out.append({"startTime": round(chap_start, 2), "title": name})
        t = vstart + secs
    ostart = t - T["片尾在最后这么多秒人声下面进来"]
    b0, b1 = t_bed - T["底乐提前进"], ostart              # 底乐：开场人声前一点进来，片尾曲进来时淡完
    timeline.append({"段": "底乐（全程，说话时压低）", "开始秒": round(b0, 2), "秒数": round(b1 - b0, 2)})
    timeline.append({"段": "片尾曲", "开始秒": round(ostart, 2), "秒数": round(len(outro_x) / SR, 2)})
    total = max(t, ostart + len(outro_x) / SR) + T["末尾留白"]
    n = int(round(total * SR))
    timeline.sort(key=lambda r: r["开始秒"])

    # —— 2) 人声轨；10 毫秒一帧判断在不在说话，算出底乐和片尾曲的音量曲线 ——
    voice = np.zeros(n, dtype=np.float32)
    for (s, _), (_, v) in zip(spans, voices):
        a = int(round(s * SR))
        voice[a:a + len(v)] += v[:n - a]
    hop = int(FRAME * SR)
    nf = int(np.ceil(n / hop))
    vp = np.zeros(nf * hop, dtype=np.float64)
    vp[:n] = voice
    AV = spec.get("避让")                                 # 第十一轮"避让"；不写就走下面原来的压低
    talk = 10 * np.log10((vp.reshape(nf, hop) ** 2).mean(axis=1) + 1e-12) > vl - (AV or D)["门限dB"]
    del vp
    if AV:
        bed_curve, av_code = _avoid_curve(talk, [(int(round(a / FRAME)), int(round(b / FRAME))) for a, b in holds],
                                          AV, lv)
        duck_on = av_code > 0
    else:
        duck_on = _dilate(talk, int(round(D["提前"] / FRAME)), int(round(D["保持"] / FRAME)))
        if D.get("章与章之间不保持"):                     # 章与章之间：说完稍等一下就浮起来，不等"保持"那 1 秒
            hold = float(D.get("章末保持", 0.15))
            for (_, e0), (s1, _) in zip(spans[:-1], spans[1:]):
                a, b = int(round((e0 + hold) / FRAME)), int(round((s1 - D["提前"]) / FRAME))
                if b > a:
                    duck_on[a:b] = talk[a:b]
        for a, b, _, _ in windows:                       # 转场、桥段的乐句响着时，底乐也压着
            duck_on[int(a / FRAME):int(b / FRAME) + 1] = True
        target = np.where(duck_on, lv["底乐·说话时"], lv["底乐·空隙里"]).astype(np.float64)
        extra = spec.get("开场那一章底乐另加dB") or 0
        if extra:
            a, b = int(spans[0][0] / FRAME), int(spans[0][1] / FRAME)
            target[a:b] += np.where(duck_on[a:b], extra, 0)
        bed_curve = _smooth_db(target, D["压下"], D["回升"])
    outro_curve = _smooth_db(np.where(talk, lv["片尾·人声没说完时再压"], 0.0), 0.05, 0.9)

    # —— 3) 各轨相加（人声复制成左右两路） ——
    mixed_arr = np.repeat(voice[:, None], 2, axis=1)
    bed = _looped_from(bed_x, b1 - b0, len(bed_x) / SR - T["底乐提前进"])
    _apply_db(_fade_edges(bed, T["底乐淡入"], T["底乐在片尾前淡出"]), b0, bed_curve, vl - bed_i["参考响度LUFS"])
    s0 = int(round(b0 * SR))
    mixed_arr[s0:s0 + len(bed)] += bed[:n - s0]
    outro = _apply_db(outro_x.copy(), ostart, outro_curve, gain(outro_i, "片尾"))
    o0 = int(round(ostart * SR))
    mixed_arr[o0:o0 + len(outro)] += outro[:n - o0]
    for st, x, gdb, _ in free:
        a = int(round(st * SR))
        e = min(n, a + len(x))
        mixed_arr[a:e] += x[:e - a] * np.float32(10 ** (gdb / 20))

    # —— 4) 只出一段（试听小样）就截出来；量各段比人声低多少 ——
    marks = {c["title"]: c["startTime"] for c in chapters_out}
    marks["片尾"] = ostart
    ra, rb = _excerpt_range(excerpt, marks, total) if excerpt else (0.0, total)
    fa, fb = int(ra / FRAME), int(rb / FRAME)
    ve = _kframes(voice) * 2                             # 立体声两路一样，能量×2
    vlu = _lu(ve[fa:fb])
    be = np.zeros(nf)
    bk = _kframes(bed)
    be[s0 // hop:s0 // hop + len(bk)] = bk[:nf - s0 // hop]
    in_bed = np.zeros(nf, dtype=bool)
    in_bed[int((b0 + T["底乐淡入"]) / FRAME):int((b1 - T["底乐在片尾前淡出"]) / FRAME)] = True
    in_voice = np.zeros(nf, dtype=bool)
    for s, e in spans:
        in_voice[int(s / FRAME):int(e / FRAME)] = True
    rng = np.zeros(nf, dtype=bool)
    rng[fa:fb] = True
    speak = in_bed & in_voice & duck_on & rng
    for a, b, _, _ in windows:
        speak[int(a / FRAME):int(b / FRAME) + 1] = False
    if AV:                                               # 避让：只量已降到"说话时"那一档的帧（转场后回升途中的不算）
        speak &= np.abs(bed_curve - lv["底乐·说话时"]) < 0.3
    gap = in_bed & rng & (bed_curve > lv["底乐·空隙里"] - 1)

    def rel(v):
        return None if v is None or vlu is None else round(v - vlu, 1)

    measured = {"人声整体响度LUFS（混音后、统一响度前）": vlu,
                "底乐·说话时": rel(_lu(be[speak], gated=False)), "其中说话秒数": round(speak.sum() * FRAME, 1),
                "底乐·空隙里（已浮到位的时候）": rel(_lu(be[gap], gated=False)), "其中空隙秒数": round(gap.sum() * FRAME, 1)}
    if AV:
        pk = [float(bed_curve[a:b].max()) for a, b, c in _runs(np.where(av_code == 0, 3, av_code).astype(np.int8))
              if c == 3 and rng[a:b].any() and in_bed[a:b].any()]
        measured["避让：本段升起来的停顿数"] = len(pk)
        measured["避让：这些停顿里底乐最高升到（配置dB，最低/中位/最高）"] = (
            [round(min(pk), 1), round(float(np.median(pk)), 1), round(max(pk), 1)] if pk else None)
    if stems:
        sd = Path(stems)
        sd.mkdir(parents=True, exist_ok=True)
        import soundfile as sf
        A0, B0 = int(round(ra * SR)), int(round(rb * SR))
        bseg = np.zeros((B0 - A0, 2), dtype=np.float32)
        lo_, hi_ = max(A0, s0), min(B0, s0 + len(bed))
        if hi_ > lo_:
            bseg[lo_ - A0:hi_ - A0] = bed[lo_ - s0:hi_ - s0]
        vseg = np.repeat(voice[A0:B0, None], 2, axis=1)
        sf.write(sd / "人声.wav", vseg, SR, subtype="FLOAT")
        sf.write(sd / "底乐.wav", bseg, SR, subtype="FLOAT")
        sf.write(sd / "其余音乐.wav", mixed_arr[A0:B0] - vseg - bseg, SR, subtype="FLOAT")
        np.save(sd / "底乐曲线dB.npy", bed_curve[fa:fb])
        del bseg, vseg
    del be, bk, bed
    for st, x, gdb, what in free:
        info = intro_i if what == "片头" else trans[what][1]
        if what == "片头":
            a0, a1 = info.get("乐句起拍秒", 0.0), info.get("人声进入秒", len(x) / SR) - 0.3
        else:
            a0, a1 = info.get("落拍秒", 0.0), info.get("淡出开始秒", len(x) / SR)
        if ra <= st + a0 and st + a1 <= rb:
            seg = x[int(a0 * SR):int(a1 * SR)] * 10 ** (gdb / 20)
            measured[f"{what}乐句（{st:.1f} 秒处）"] = rel(lufs(seg))
    if ra <= t and rb >= t + 2:
        k = int((t - ostart) * SR)
        measured["片尾曲（人声说完后）"] = rel(lufs(outro[k:k + int(min(rb - t, 8) * SR)]))

    seg = mixed_arr[int(round(ra * SR)):int(round(rb * SR))]
    del mixed_arr, voice
    if excerpt:
        _fade_edges(seg, 0.3 if ra > 0 else 0.0, 1.5 if rb < total else 0.0)
    raw = work / "mix.f32"
    write_raw(seg, raw)
    mixed = work / "mix.wav"
    _ffmpeg(raw_input(raw, 2) + ["-c:a", "pcm_f32le", str(mixed)])
    raw.unlink(missing_ok=True)
    chapters_x = [{"startTime": round(max(0.0, c["startTime"] - ra), 2), "title": c["title"]}
                  for c in chapters_out if ra - 0.5 <= c["startTime"] < rb]

    # —— 5) 统一响度、写音频文件信息、编码（和 v2 同一套） ——
    disclosure = ("本节目由 AI 辅助生成，" + ("经人工审核，" if reviewed else "") + "使用 AI 合成语音；" +
                  spec.get("音乐说明", "") + (f" 音乐署名：{spec['署名']}" if spec.get("署名") else ""))
    mp3, loud, r, gain_db = _master(mixed, work, out_dir, title or out_dir.name, disclosure, chapters_x,
                                    rb - ra, bitrate, lra=20 if excerpt else 11)
    (out_dir / "chapters.json").write_text(json.dumps(
        {"version": "1.2.0", "chapters": chapters_x}, ensure_ascii=False, indent=1), encoding="utf-8")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    speech_total = sum(len(v) for _, v in voices) / SR
    files = {"片头": intro_i, "底乐": bed_i, "片尾": outro_i, **{k: v[1] for k, v in trans.items()}}
    (out_dir / "qc.json").write_text(json.dumps({
        "生成于": stamp, "人声来源": str(speech_dir), "配音配置": sq.get("配置"), "人声对稿": sq.get("整集"),
        "声音包": {"名称": spec.get("名称"), "配置": spec["_文件"], "片头版本": iv, "署名": spec.get("署名"),
                   **({"本期调整": spec["_调整"]} if spec.get("_调整") else {})},
        "整集" if not excerpt else "片段": {
            "范围秒": [round(ra, 2), round(rb, 2)], "整集秒数": round(total, 1), "其中人声秒数": round(speech_total, 1),
            "响度LUFS": round(loud["I"], 1), "真峰值dBTP": round(loud["TP"], 1),
            "loudnorm方式": r.get("normalization_type"), "编码后补的增益dB": gain_db,
            "格式": f"MP3 立体声 {bitrate} kbps {SR} Hz", "音频文件信息里的声明": disclosure},
        "混音": {"音量（相对人声dB，配置）": lv, "人声整体响度LUFS（混音前）": round(vl, 1), "转场位置": where,
                 "时间参数秒": T, **({"避让（第十一轮，代替压低）": AV} if AV else {"压低": D}),
                 "素材": {k: {kk: vv for kk, vv in v.items() if kk in ("文件", "参考响度LUFS", "人声进入秒", "落拍秒",
                                                                    "乐句结束秒", "循环秒", "用途")}
                        for k, v in files.items()}},
        "实测（相对人声整体响度，dB；只量本文件这一段）": measured,
        "时间线": timeline}, ensure_ascii=False, indent=1), encoding="utf-8")
    su = json.loads((speech_dir / "usage.json").read_text(encoding="utf-8")) if (speech_dir / "usage.json").exists() else {}
    (out_dir / "usage.json").write_text(json.dumps({
        "生成于": stamp,
        "配音": {"引擎": su.get("引擎"), "模型": su.get("模型"), "合计": su.get("合计"), "说明": su.get("说明")},
        "音乐素材（一次性，各期复用，不算进每期）": _music_note(spec),
        "混音": "本机 ffmpeg + numpy，不花钱"}, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    what = f"片段 {ra:.0f}–{rb:.0f} 秒" if excerpt else f"{total / 60:.1f} 分钟（人声 {speech_total / 60:.1f} 分钟）"
    log(f"  ✓ {mp3}  {what}，{loud['I']:.1f} LUFS，峰 {loud['TP']:.1f} dBTP；底乐说话时 {measured['底乐·说话时']} dB、"
        f"空隙里 {measured['底乐·空隙里（已浮到位的时候）']} dB（相对人声）")
    return {"mp3": str(mp3), "秒数": rb - ra, "chapters": chapters_x, "响度": loud, "实测": measured,
            "qc": str(out_dir / "qc.json")}


def main(argv=None):
    ap = argparse.ArgumentParser(description="播客混音（用法见文件开头）")
    ap.add_argument("speech_dir", help="tts.py 的产出目录（配音时加了 --chapter-wavs）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--music", default=str(MUSIC), help="v2 做法用的素材目录（用 --package 时不看它）")
    ap.add_argument("--title")
    ap.add_argument("--reviewed", action="store_true", help="稿子已人工审核")
    ap.add_argument("--bitrate", type=int, default=BITRATE_KBPS)
    ap.add_argument("--package", help="v3 起：声音包，写名字（v3、v3/A、v3/B）或 JSON 路径；不给就是 v2 的老做法")
    ap.add_argument("--intro", help="片头版本，如 6s、10s（配 --package）")
    ap.add_argument("--bed-db", type=float, help="说话时底乐比人声低多少 dB，如 -29（配 --package）")
    ap.add_argument("--excerpt", help="只出一段试听，如 0:120、要闻-25:要闻+20、片尾-30:末（配 --package）")
    ap.add_argument("--stems", help="另存人声、底乐、其余音乐三轨（统一响度前）到这个目录，测量用（配 --package）")
    a = ap.parse_args(argv)
    try:
        if a.package:
            mix_package(a.speech_dir, a.out, package=a.package, intro=a.intro, bed_db=a.bed_db, excerpt=a.excerpt,
                        title=a.title, reviewed=a.reviewed, bitrate=a.bitrate, stems=a.stems)
        elif a.intro or a.bed_db is not None or a.excerpt or a.stems:
            ap.error("--intro、--bed-db、--excerpt、--stems 要和 --package 一起用")
        else:
            mix(a.speech_dir, a.out, music=a.music, title=a.title, reviewed=a.reviewed, bitrate=a.bitrate)
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"✗ {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
