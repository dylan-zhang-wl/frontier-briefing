#!/usr/bin/env python3
"""视频 v3 配乐：按配乐的拍子排章节空隙，再把旁白和配乐混成一条音轨（−16 LUFS、真峰值 ≤ −1 dBTP）。

由 site/tools/video3_build.py 调用，不单独运行。和播客 v3/B2 是同一套声音：
  · 片头一小句、片尾收束：播客片尾曲那次 Google Lyria 生成的同一段音乐（4/4 拍，每分钟 100 拍，升 F 大调）。
    片头取它开头 6 拍——和播客 B 方向片头的乐句是同一句；片尾取它最后慢慢收住的那几小节。
  · 底乐：播客 B2 的亮底乐 pipeline/assets/music/v3/bed_bright.flac（Scott Buckley《Castles in the Sky》中段循环，
    3/4 拍，每分钟 100 拍，降 e 小调——和 Lyria 那段是关系大小调，同一组音），说话时垫在下面；
  · 空隙里浮起来的那一层：同一段 Castles 不挖人声频段的原样（和底乐同一个循环、同一个位置，叠在一起不打架）。

节拍怎么用（"跟着拍子剪"）：
  1. 片头乐句的第一个强拍落在第 0.3 秒，片头字跟着这个强拍上推；6 拍后（3.9 秒）底乐的第一个强拍进来，旁白同时开口。
  2. 之后底乐每 3 拍一小节（1.8 秒），小节线排成一张网格。每章说完，下一章不按固定秒数接，而是等到下一条小节线
     （离最后一个字至少 0.45 秒）：这条小节线就是两章的分界——镜头在这个强拍上起飞，空隙里的音乐也在这里涨到最满。
  3. 下一章在小节线后 2 拍开口（如果前面已经等了 1 秒以上，就 1 拍后开口），音乐在开口前 0.45 秒压下去。
  4. 进收尾那条小节线上，片尾那段 Lyria 的强拍接进来（底乐在前一拍淡出），收尾的旁白骑在它上面；
     片尾从哪个强拍起，按"最后的收束和弦正好落在最后一个字之后"倒推着选，所以音乐和旁白一起收住。
  5. 每个拍点、每条小节线的秒数都写进视频数据（music.beats、music.downbeats），画面那边用它把镜头落点对到拍子上。

响度：先按"相对人声多少 dB"摆好每一层，混好后整体线性加减到 −16 LUFS（不压缩），编码成 MP3 后再量一次真峰值，
     超过 −1 dBTP 就整体再降一点重编。

2026-11-02 晚改（第十一轮）：默认配乐改成和播客一样的"避让"（STYLE = "avoid"）。用户在视频里也听到 B2 亮底乐那种
一直响的"铃声余音"。现在：
  · 底乐、音量、避让参数都从播客的默认声音包读（PACKAGE = "v3"，即 assets/music/v3/包.json；11-02 起指向
    E_新底乐避让.json：Kevin MacLeod《Dreamer》第 4–80 小节，100 拍／分钟、四拍子，不滤波）。用户换包，视频跟着换；
  · 避让和播客同一个函数（podcast_mix._avoid_curve）：按人声起止画曲线，说话时比人声低 23 dB，停顿够长时升到低 15 dB，
    短于 0.6 秒的停顿不升；片头乐句响着时（到人声进来后 1.4 秒）和片尾那段 Lyria 进来以后，底乐压到低 30 dB；
  · 不再叠"空隙里浮起"那一层：底乐自己在停顿里浮上来；
  · 章与章的分界仍按底乐的小节线排，只是小节换成四拍（2.4 秒）；片头 Lyria 6 拍、片尾按收束拍倒推，和原来一样；
  · 响度标准不变（−16 LUFS、真峰值 ≤ −1 dBTP、128 kbps），整体增益的算法也不变。
旧的混法（B2 亮底乐＋空隙层、三拍子小节线）用 STYLE = "b2" 原样复现（video3_build.py --music-style b2）：
已核对，用 11-02 的人声重混，和 测试版/2026-11-02/05_配音/视频旁白_v3/video3.mp3 解码后逐采样一致。
"""
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PIPE = ROOT / "pipeline"
MUSIC = PIPE / "assets/music"
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

import podcast_mix as M  # noqa: E402  （只读调用：读音频、淡入淡出、响度和真峰值）

SR = M.SR

# ============================ 可改区 ============================

# 两段音乐的节拍（2026-10-31 用 pipeline/assets/music/make_music.py 的 beat_grid 测，见 v3/素材.json）
LYRIA = {"文件": MUSIC / "lyria_raw/outro_lyria-3-clip.mp3", "第一拍秒": 0.511, "每拍秒": 0.60007, "每小节拍数": 4,
         "第一个强拍": 1,             # 第 1 拍（1.111 秒）起是强拍
         "参考段拍": (1, 25),          # 开头 24 拍音量很平，拿来定这段音乐的参考响度
         "收束拍": 37,                 # 最后一个强拍（22.7 秒）：之后只剩余音
         "余音到秒": 26.0}
CASTLES = {"文件": Path.home() / ".cache/frontier-daily/music-candidates/SB_CastlesInTheSky.mp3",
           "第一拍秒": 0.511, "每拍秒": 0.59993, "每小节拍数": 3, "从第几拍": 60, "拍数": 72, "接缝秒": 1.2}
BED = MUSIC / "v3/bed_bright.flac"     # 播客 B2 的亮底乐：与上面 Castles 同一段循环（第 60 拍起 72 拍）

INTRO = {"从第几拍": 1, "拍数": 6, "强拍前淡入秒": 0.3, "强拍在第几秒": 0.3}

# 音量：相对人声整体响度的 dB（人声 = 0）
LEVEL = {"片头乐句": -3.0,                # 和播客片头乐句一样
         "底乐·说话时": -23.0,         # 播客 B2 是 −26；视频画面在动，音乐可以略显一点
         "空隙里浮起": -13.0,          # 章与章之间、镜头飞的时候（加上底乐，实测约比说话低 9–10 dB）
         "片尾·镜头飞时": -10.0,
         "片尾·说话时": -20.0,
         "片尾·收束": -3.0}             # 这段 Lyria 本身在收，比参考段低 4–5 dB，实际听着约低 7–8 dB
# 人声左右两个声道一样（单声道摆在正中），所以"人声响度"按立体声算：比单声道量出来的高 3 dB。
# 这样音乐（立体声）和人声比的才是耳朵里听到的差。

TIME = {"末字到小节线至少": 0.45,       # 章末到分界小节线至少隔多久（配音文件末尾自带约 0.15 秒静音）
        "开口在小节线后几拍": 2,
        "已等够秒": 1.0, "已等够时几拍开口": 1,
        "压下提前": 0.45, "压下到": 0.05,  # 下一句开口前 0.45 秒开始压，开口前 0.05 秒压完
        "浮起前沿": 0.3,                # 章末后多久浮到"差 12 dB"，再慢慢涨到强拍上最满
        "收束拍在末字后至少": 0.4,
        "最后至少留": 2.2}

TARGET_LUFS = -16.0
PEAK_DBTP = -1.0
BITRATE = "128k"

# 2026-11-02 起：配乐的做法。"avoid"＝和播客默认声音包一样的底乐＋避让（默认）；"b2"＝11-02 以前的混法（原样复现用）
STYLE = "avoid"
STYLES = ("avoid", "b2")
PACKAGE = "v3"                       # avoid 用哪个声音包（和播客 --package 写法一样）；"v3" 就是 assets/music/v3/包.json 指的那个
AVOID = {"底乐提前进": 0.6,           # 底乐在第一句人声前这么多秒淡入（同 b2）
         "片头乐句响到人声后": 1.4}     # 片头乐句在人声进来后这么多秒淡完（见下面片头的音量曲线）；这之前底乐压在"转场乐句下"那一档
# 各条底乐的署名（网页 music.credit 用；attribution 一行写进 MP3 的音频文件信息）
CREDITS = {
    "bed_dreamer.flac": {
        "zh": "配乐：Kevin MacLeod《Dreamer》（CC BY 4.0，经剪辑）。",
        "en": "Music: \"Dreamer\" by Kevin MacLeod (incompetech.com), licensed under CC BY 4.0 (edited).",
        "url": "https://incompetech.com", "曲名": "Kevin MacLeod《Dreamer》"},
    "bed_castles_long.flac": {
        "zh": "配乐：Scott Buckley《Castles in the Sky》（CC BY 4.0，经剪辑）。",
        "en": "Music: 'Castles in the Sky' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au (edited).",
        "url": "https://www.scottbuckley.com.au", "曲名": "Scott Buckley《Castles in the Sky》"},
}

CREDIT = {
    "zh": "配乐：Scott Buckley《Castles in the Sky》（CC BY 4.0，经剪辑）。",
    "en": "Music: 'Castles in the Sky' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au (edited).",
    "attribution": "'Castles in the Sky' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au (edited)",
    "url": "https://www.scottbuckley.com.au",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "note_zh": "片头、片尾乐句出自播客片尾曲那次 Lyria 3 生成的同一段音乐（带 AI 生成水印）；Lyria 输出的许可还没核，"
               "公开发布前要核（见 pipeline/assets/music/README.md）。底乐与播客 v3/B2 相同。",
}

# ==============================================================


def t_lyria(i):
    return LYRIA["第一拍秒"] + i * LYRIA["每拍秒"]


def lyria_downbeats():
    s, n = LYRIA["第一个强拍"], LYRIA["每小节拍数"]
    return list(range(s, LYRIA["收束拍"] + 1, n))


def _package():
    """avoid 用的声音包：(配置, 底乐文件, 底乐在 素材*.json 里的记录)。和播客读的是同一份（podcast_mix.load_package）。"""
    spec = M.load_package(PACKAGE)
    rel = spec["素材"]["底乐"]
    info = dict(M._pkg_meta(spec).get(rel) or {})
    if not info.get("每拍秒") or not info.get("每小节拍数"):
        raise SystemExit("声音包 %s 的底乐 %s 没记节拍（每拍秒、每小节拍数），视频没法按小节线排" % (spec.get("名称"), rel))
    return spec, (Path(spec["_目录"]) / rel).resolve(), info


def plan(voice_lens, style=None):
    """各章人声的秒数 → 时间表：每章几秒开口、几秒说完、章与章的分界（小节线）、片尾从哪拍起、总长、拍点。
    style：不给用 STYLE。avoid 的小节线按声音包底乐的拍子（Dreamer 四拍一小节），b2 按 Castles（三拍一小节）。"""
    style = style or STYLE
    if style not in STYLES:
        raise ValueError("配乐做法只有 %s，没有 %s" % ("、".join(STYLES), style))
    if style == "b2":
        return _plan_grid(voice_lens, CASTLES["每拍秒"], CASTLES["每小节拍数"], "底乐（Castles in the Sky）")
    spec, bed, info = _package()
    pl = _plan_grid(voice_lens, info["每拍秒"], info["每小节拍数"], "底乐（%s）" % (CREDITS.get(bed.name) or {}).get("曲名", bed.name))
    pl.update({"style": "avoid", "package": spec.get("名称"), "bed": bed.name})
    return pl


def _plan_grid(voice_lens, bC, per_bar, bed_what):
    bL = LYRIA["每拍秒"]
    p0 = INTRO["强拍在第几秒"]
    v0 = p0 + INTRO["拍数"] * bL
    bar = per_bar * bC
    n = len(voice_lens)
    vs, ve, bounds, waits = [v0], [], [], []
    for i in range(n):
        e = vs[i] + voice_lens[i]
        ve.append(e)
        if i == n - 1:
            break
        m = math.ceil((e + TIME["末字到小节线至少"] - v0) / bar - 1e-9)
        b = v0 + m * bar
        bounds.append(b)
        if i == n - 2:                    # 进收尾：开口按片尾那段的拍子
            k, beat = TIME["开口在小节线后几拍"], bL
        else:
            k = TIME["已等够时几拍开口"] if b - e >= TIME["已等够秒"] else TIME["开口在小节线后几拍"]
            beat = bC
        waits.append({"末字到小节线": round(b - e, 3), "开口在第几拍后": k})
        vs.append(b + k * beat)
    # 片尾：从哪个强拍起，让最后的收束拍落在最后一个字之后
    b_out, e_last = bounds[-1], ve[-1]
    limit = t_lyria(LYRIA["收束拍"]) + b_out - (e_last + TIME["收束拍在末字后至少"])
    cands = [s for s in lyria_downbeats() if t_lyria(s) <= limit + 1e-9]
    s_out = max(cands) if cands else LYRIA["第一个强拍"]
    dur = max(b_out + LYRIA["余音到秒"] - t_lyria(s_out), e_last + TIME["最后至少留"])
    beats, downs = [], []
    for k in range(INTRO["拍数"]):
        beats.append(p0 + k * bL)
        if k % LYRIA["每小节拍数"] == 0:
            downs.append(p0 + k * bL)
    k = 0
    while v0 + k * bC < b_out - 1e-6:
        beats.append(v0 + k * bC)
        if k % per_bar == 0:
            downs.append(v0 + k * bC)
        k += 1
    k = 0
    while b_out + k * bL < dur - 0.3:
        beats.append(b_out + k * bL)
        if k % LYRIA["每小节拍数"] == 0:
            downs.append(b_out + k * bL)
        k += 1
    r3 = lambda xs: [round(x, 3) for x in xs]   # noqa: E731
    return {"intro_down": round(p0, 3), "voice_starts": r3(vs), "voice_ends": r3(ve), "bounds": r3(bounds), "waits": waits,
            "outro_from_beat": s_out, "outro_src_sec": round(t_lyria(s_out), 3), "resolve_at": round(b_out + t_lyria(LYRIA["收束拍"]) - t_lyria(s_out), 3),
            "duration": round(dur, 3), "beats": r3(beats), "downbeats": r3(downs), "bpm": 100,
            "meters": [{"from": round(p0, 3), "beats_per_bar": 4, "what": "片头乐句（Lyria）"},
                       {"from": round(v0, 3), "beats_per_bar": per_bar, "what": bed_what},
                       {"from": round(b_out, 3), "beats_per_bar": 4, "what": "片尾（Lyria）"}]}


def plan_fixed(voice_lens, lead, gaps, tail):
    """不配乐（--no-music）：开头、章间、结尾按固定秒数留空，分界在上一章说完后 0.05 秒。"""
    vs, ve, bounds, pos = [], [], [], lead
    for i, n in enumerate(voice_lens):
        vs.append(pos)
        ve.append(pos + n)
        if i < len(voice_lens) - 1:
            bounds.append(pos + n + 0.05)
            pos += n + gaps[i]
    r3 = lambda xs: [round(x, 3) for x in xs]   # noqa: E731
    return {"intro_down": None, "voice_starts": r3(vs), "voice_ends": r3(ve), "bounds": r3(bounds),
            "duration": round(ve[-1] + tail, 3), "beats": [], "downbeats": [], "music": False}


# ---------------------------------------------------------------- 渲染
def _take(x, t0, t1):
    a, b = int(round(t0 * SR)), int(round(t1 * SR))
    out = np.zeros((b - a, 2), dtype=np.float32)
    lo, hi = max(a, 0), min(b, len(x))
    if hi > lo:
        out[lo - a:hi - a] = x[lo:hi]
    return out


def _put(buf, x, at, base_db, points=None):
    """把 x 放到第 at 秒，乘上 base_db 和一条按 (秒, dB) 折线的音量曲线（秒是成片里的时间）。"""
    s = int(round(at * SR))
    a, b = max(0, s), min(len(buf), s + len(x))
    if b <= a:
        return
    seg = x[a - s:b - s].astype(np.float32)
    if points:
        ts, ds = zip(*points)
        tt = np.arange(a, b) / SR
        g = 10 ** ((base_db + np.interp(tt, ts, ds)) / 20)
    else:
        g = np.full(b - a, 10 ** (base_db / 20))
    buf[a:b] += seg * g.astype(np.float32)[:, None]


def _castles_full():
    """不挖人声频段的 Castles 循环（和 bed_bright 同一段、同一个接缝做法）。原曲不在缓存里就返回 None。"""
    c = CASTLES
    if not Path(c["文件"]).exists():
        return None
    x = M.load(c["文件"], 2)
    bt = c["每拍秒"]
    t0 = c["第一拍秒"] + c["从第几拍"] * bt
    loop = c["拍数"] * bt
    core = _take(x, t0, t0 + loop).astype(np.float64)
    pre = _take(x, t0 - c["接缝秒"], t0).astype(np.float64)
    n = len(pre)
    ang = np.linspace(0, np.pi / 2, n)[:, None]
    core[-n:] = core[-n:] * np.cos(ang) + pre * np.sin(ang)
    return core.astype(np.float32)


def _mp3(x, path, title, channels, gain_db=0.0, comment=""):
    tmp = Path(str(path) + ".f32")
    M.write_raw(np.asarray(x, dtype=np.float32) * (10 ** (gain_db / 20)), tmp)
    args = M.raw_input(tmp, channels) + ["-c:a", "libmp3lame", "-b:a", BITRATE if channels == 2 else "96k",
                                         "-metadata", "title=" + title]
    if comment:
        args += ["-metadata", "comment=" + comment]
    M._ffmpeg(args + [str(path)])
    tmp.unlink(missing_ok=True)


def render(pl, chapter_wavs, out_mix, out_voice, title, log=print):
    """按 plan() 的时间表把各章人声和配乐摆好、混好，写出 out_mix（立体声 MP3）和 out_voice（只有人声，对齐用）。返回测量结果。
    pl 来自 plan_fixed()（不配乐）时只摆人声，out_mix 就是人声（单声道）。pl 是 avoid 做法排的，就走 _render_avoid。"""
    if pl.get("style") == "avoid":
        return _render_avoid(pl, chapter_wavs, out_mix, out_voice, title, log)
    dur = pl["duration"]
    if pl.get("music") is False:
        n = int(round(dur * SR))
        voice = np.zeros(n, dtype=np.float32)
        for w, v in zip(chapter_wavs, pl["voice_starts"]):
            x = M.load(w, 1)
            s = int(round(v * SR))
            e = min(n, s + len(x))
            voice[s:e] += x[:e - s]
        gain = TARGET_LUFS - M.lufs(voice)
        gain = min(gain, PEAK_DBTP - 0.4 - M.true_peak(voice))
        _mp3(voice, out_mix, title, 1, gain)
        y = M.load(out_mix, 1)
        fix = min(TARGET_LUFS - M.lufs(y), PEAK_DBTP - M.true_peak(y))   # 补上 MP3 编码损失的响度，真峰值不超上限
        if fix > 0.1:
            gain += fix
            _mp3(voice, out_mix, title, 1, gain)
            y = M.load(out_mix, 1)
        shutil.copy2(out_mix, out_voice)
        meas = {"整体响度LUFS": round(M.lufs(y), 2), "真峰值dBTP": round(M.true_peak(y), 2), "整体增益dB": round(gain, 2), "配乐": "无"}
        log("  只有人声：%s LUFS、真峰值 %s dBTP" % (meas["整体响度LUFS"], meas["真峰值dBTP"]))
        return meas
    n = int(round(dur * SR))
    voice = np.zeros(n, dtype=np.float32)
    for w, v in zip(chapter_wavs, pl["voice_starts"]):
        x = M.load(w, 1)
        s = int(round(v * SR))
        e = min(n, s + len(x))
        voice[s:e] += x[:e - s]
    ref_v = M.lufs(voice) + 10 * np.log10(2)      # 人声放在两个声道里的响度（见上面 LEVEL 的说明）
    music = np.zeros((n, 2), dtype=np.float32)
    bL = LYRIA["每拍秒"]
    p0, v0 = pl["intro_down"], pl["voice_starts"][0]
    b_out, v_last, e_last = pl["bounds"][-1], pl["voice_starts"][-1], pl["voice_ends"][-1]

    # 1. 片头乐句（Lyria 开头 6 拍）
    ly = M.load(LYRIA["文件"], 2)
    a, b = LYRIA["参考段拍"]
    ref_l = M.lufs(_take(ly, t_lyria(a), t_lyria(b)))
    pick = INTRO["强拍前淡入秒"]
    t_dn = t_lyria(INTRO["从第几拍"])
    seg = M.fades(_take(ly, t_dn - pick, t_dn + (v0 - p0) + 1.6), pick, 0.05)
    _put(music, seg, p0 - pick, ref_v + LEVEL["片头乐句"] - ref_l,
         [(0, 0), (v0 - 0.3, 0), (v0 + 0.5, -15), (v0 + 1.4, -50), (v0 + 1.7, -80)])

    # 2. 底乐（说话时垫在下面）
    bed = M.load(BED, 2)
    ref_b = M.lufs(bed)
    pre = 0.6
    span = b_out + 0.6 - (v0 - pre)
    under = M._looped_from(bed, span, len(bed) / SR - pre)
    _put(music, under, v0 - pre, ref_v + LEVEL["底乐·说话时"] - ref_b,
         [(v0 - pre, -60), (v0 - 0.3, -30), (v0 + 0.4, 0), (b_out - bL, 0), (b_out + 0.3, -60)])

    # 3. 空隙里浮起来的一层（同一段 Castles 不挖人声频段）；没有原曲时用底乐本身
    full = _castles_full()
    if full is None:
        log("  注意：缓存里没有 Castles in the Sky 原曲，空隙里改用底乐本身浮起")
        full = bed
    ref_f = M.lufs(full)
    swell = M._looped_from(full, span, len(full) / SR - pre)
    pts = [(v0 - pre, -80)]
    for i, bd in enumerate(pl["bounds"]):
        e, v = pl["voice_ends"][i], pl["voice_starts"][i + 1]
        if i < len(pl["bounds"]) - 1:
            up = min(e + TIME["浮起前沿"], bd - 0.1)
            near = max(up + 0.05, bd - CASTLES["每拍秒"])       # 强拍前一拍已涨到只差 3 dB
            pts += [(e - 0.1, -80), (e - 0.05, -40), (up, -12), (near, -3), (bd, 0), (v - TIME["压下提前"], 0),
                    (v - TIME["压下到"], -40), (v, -80)]
        else:                              # 最后一个空隙：涨到片尾强拍前一拍，再交给片尾
            pk = max(e + 0.3, bd - bL)
            pts += [(e - 0.1, -80), (e - 0.05, -40), (min(e + TIME["浮起前沿"], pk - 0.05), -12), (pk, 0), (bd + 0.25, -60), (bd + 0.3, -80)]
    _put(music, swell, v0 - pre, ref_v + LEVEL["空隙里浮起"] - ref_f, pts)

    # 4. 片尾（Lyria 收束）：强拍对准进收尾的那条小节线
    t_s = pl["outro_src_sec"]
    seg = M.fades(_take(ly, t_s - bL, LYRIA["余音到秒"] + 0.4), bL, 0.8)
    fly, talk, end = LEVEL["片尾·镜头飞时"], LEVEL["片尾·说话时"], LEVEL["片尾·收束"]
    _put(music, seg, b_out - bL, ref_v - ref_l,
         [(b_out - bL, fly), (v_last - TIME["压下提前"], fly), (v_last - TIME["压下到"], talk), (e_last - 0.1, talk),
          (e_last + 0.5, end), (dur + 1, end)])

    # 5. 混音、统一响度
    mix = music + voice[:, None]
    lu = M.lufs(mix)
    gain = TARGET_LUFS - lu
    tp = M.true_peak(mix) + gain
    if tp > PEAK_DBTP - 0.4:               # 给 MP3 编码留 0.4 dB
        gain -= tp - (PEAK_DBTP - 0.4)
    comment = CREDIT["attribution"] + " | Opening/closing phrases: Google Lyria (AI-generated, watermarked)."
    # MP3 编码本身会让响度低 0.3–0.5 LU（实测），所以编完解码再量，按差值补一次增益；真峰值始终不超过上限
    for attempt in range(4):
        _mp3(mix, out_mix, title, 2, gain, comment)
        y = M.load(out_mix, 2)
        tp_out, lu_out = M.true_peak(y), M.lufs(y)
        if tp_out > PEAK_DBTP:
            gain -= tp_out - PEAK_DBTP + 0.05
        elif abs(lu_out - TARGET_LUFS) > 0.1 and tp_out + (TARGET_LUFS - lu_out) <= PEAK_DBTP:
            gain += TARGET_LUFS - lu_out
        else:
            break
    _mp3(voice, out_voice, title + "（只有人声，对齐用）", 1, gain)

    # 6. 量：说话时 / 空隙里音乐比人声低多少
    g = 10 ** (gain / 20)
    ev, em = M._kframes(voice * g) * 2, M._kframes(music * g)      # 人声按两个声道算
    fr = M.FRAME
    talk_mask = np.zeros(len(ev), bool)
    for v, e in zip(pl["voice_starts"], pl["voice_ends"]):
        talk_mask[int((v + 0.3) / fr):int((e - 0.3) / fr)] = True
    vt = M._lu(ev[talk_mask], gated=False)
    mt = M._lu(em[talk_mask], gated=False)
    gap_mask = np.zeros(len(ev), bool)
    for i, bd in enumerate(pl["bounds"][:-1]):
        gap_mask[int(bd / fr):int((pl["voice_starts"][i + 1] - TIME["压下提前"]) / fr)] = True
    mg = M._lu(em[gap_mask], gated=False) if gap_mask.any() else None
    meas = {"整体响度LUFS": round(lu_out, 2), "真峰值dBTP": round(tp_out, 2), "整体增益dB": round(gain, 2),
            "人声说话时LUFS": vt, "音乐·说话时（比人声）dB": round(mt - vt, 1) if mt is not None and vt else None,
            "音乐·空隙里浮到（比人声说话时）dB": round(mg - vt, 1) if mg is not None and vt else None,
            "参考响度": {"人声": round(ref_v, 2), "Lyria": round(ref_l, 2), "底乐": round(ref_b, 2), "空隙层": round(ref_f, 2)}}
    log("  混音：%s LUFS、真峰值 %s dBTP；音乐说话时比人声低 %s dB，空隙里浮到 %s dB" % (
        meas["整体响度LUFS"], meas["真峰值dBTP"], meas["音乐·说话时（比人声）dB"], meas["音乐·空隙里浮到（比人声说话时）dB"]))
    return meas


def _put_db(buf, x, at, base_db, curve_db, points):
    """和 _put 一样，只是音量另外再乘一条每 10 毫秒一格的 dB 曲线（成片里的时间，从 0 秒起；避让用）。"""
    s = int(round(at * SR))
    a, b = max(0, s), min(len(buf), s + len(x))
    if b <= a:
        return
    tf = np.arange(len(curve_db)) * M.FRAME
    ts, ds = zip(*points)
    for c0 in range(a, b, 1 << 20):               # 分块算，省内存
        c1 = min(b, c0 + (1 << 20))
        tt = np.arange(c0, c1) / SR
        g = 10 ** ((base_db + np.interp(tt, tf, curve_db) + np.interp(tt, ts, ds)) / 20)
        buf[c0:c1] += x[c0 - s:c1 - s].astype(np.float32) * g.astype(np.float32)[:, None]


def _credit(bed_name, spec):
    c = dict(CREDITS.get(bed_name) or {"zh": "配乐：%s" % spec.get("音乐说明", ""), "en": spec.get("署名") or "", "url": ""})
    c["attribution"] = spec.get("署名") or c["en"]
    c["license_url"] = "https://creativecommons.org/licenses/by/4.0/"
    c["note_zh"] = ("片头、片尾乐句出自播客片尾曲那次 Lyria 3 生成的同一段音乐（带 AI 生成水印）；Lyria 输出的许可还没核，"
                    "公开发布前要核（见 pipeline/assets/music/README.md）。底乐和避让与播客默认声音包相同（%s）。" % spec.get("名称"))
    return c


def _render_avoid(pl, chapter_wavs, out_mix, out_voice, title, log=print):
    """avoid 做法：片头乐句、片尾 Lyria 和 b2 一样；底乐换成声音包的底乐，按人声起止避让（和播客同一个函数）；不叠空隙层。"""
    spec, bed_path, info = _package()
    lv, AV = spec["音量dB"], spec["避让"]
    dur = pl["duration"]
    n = int(round(dur * SR))
    voice = np.zeros(n, dtype=np.float32)
    for w, v in zip(chapter_wavs, pl["voice_starts"]):
        x = M.load(w, 1)
        s = int(round(v * SR))
        e = min(n, s + len(x))
        voice[s:e] += x[:e - s]
    ref_v = M.lufs(voice) + 10 * np.log10(2)      # 人声放在两个声道里的响度（同 b2，也和播客 vl 的量法一样）
    music = np.zeros((n, 2), dtype=np.float32)
    bL = LYRIA["每拍秒"]
    p0, v0 = pl["intro_down"], pl["voice_starts"][0]
    b_out, v_last, e_last = pl["bounds"][-1], pl["voice_starts"][-1], pl["voice_ends"][-1]

    # 1. 片头乐句（Lyria 开头 6 拍）：和 b2 一模一样
    ly = M.load(LYRIA["文件"], 2)
    a, b = LYRIA["参考段拍"]
    ref_l = M.lufs(_take(ly, t_lyria(a), t_lyria(b)))
    pick = INTRO["强拍前淡入秒"]
    t_dn = t_lyria(INTRO["从第几拍"])
    seg = M.fades(_take(ly, t_dn - pick, t_dn + (v0 - p0) + 1.6), pick, 0.05)
    _put(music, seg, p0 - pick, ref_v + LEVEL["片头乐句"] - ref_l,
         [(0, 0), (v0 - 0.3, 0), (v0 + 0.5, -15), (v0 + 1.4, -50), (v0 + 1.7, -80)])

    # 2. 底乐＋避让：10 毫秒一帧判断在不在说话（门限同播客），片头乐句和片尾 Lyria 响着时算"乐句下"
    hop = int(M.FRAME * SR)
    nf = int(np.ceil(n / hop))
    vp = np.zeros(nf * hop, dtype=np.float64)
    vp[:n] = voice
    talk = 10 * np.log10((vp.reshape(nf, hop) ** 2).mean(axis=1) + 1e-12) > ref_v - AV["门限dB"]
    del vp
    holds = [(0.0, v0 + AVOID["片头乐句响到人声后"]), (b_out - bL, dur)]
    curve, code = M._avoid_curve(talk, [(int(round(x / M.FRAME)), int(round(y / M.FRAME))) for x, y in holds], AV, lv)
    bed = M.load(bed_path, 2)
    ref_b = info.get("参考响度LUFS") or M.lufs(bed)
    pre = AVOID["底乐提前进"]
    span = b_out + 0.6 - (v0 - pre)
    under = M._looped_from(bed, span, len(bed) / SR - pre)       # 循环起点（强拍）正好落在第一句人声开口处
    _put_db(music, under, v0 - pre, ref_v - ref_b, curve,
            [(v0 - pre, -60), (v0, 0), (b_out - bL, 0), (b_out + 0.3, -60)])

    # 3. 片尾（Lyria 收束）：和 b2 一模一样
    t_s = pl["outro_src_sec"]
    seg = M.fades(_take(ly, t_s - bL, LYRIA["余音到秒"] + 0.4), bL, 0.8)
    fly, talk_db, end = LEVEL["片尾·镜头飞时"], LEVEL["片尾·说话时"], LEVEL["片尾·收束"]
    _put(music, seg, b_out - bL, ref_v - ref_l,
         [(b_out - bL, fly), (v_last - TIME["压下提前"], fly), (v_last - TIME["压下到"], talk_db), (e_last - 0.1, talk_db),
          (e_last + 0.5, end), (dur + 1, end)])

    # 4. 混音、统一响度：和 b2 同一套（−16 LUFS、真峰值 ≤ −1 dBTP、编码后补增益）
    mix = music + voice[:, None]
    lu = M.lufs(mix)
    gain = TARGET_LUFS - lu
    tp = M.true_peak(mix) + gain
    if tp > PEAK_DBTP - 0.4:
        gain -= tp - (PEAK_DBTP - 0.4)
    cr = _credit(bed_path.name, spec)
    comment = cr["attribution"] + " | Opening/closing phrases: Google Lyria (AI-generated, watermarked)."
    for attempt in range(4):
        _mp3(mix, out_mix, title, 2, gain, comment)
        y = M.load(out_mix, 2)
        tp_out, lu_out = M.true_peak(y), M.lufs(y)
        if tp_out > PEAK_DBTP:
            gain -= tp_out - PEAK_DBTP + 0.05
        elif abs(lu_out - TARGET_LUFS) > 0.1 and tp_out + (TARGET_LUFS - lu_out) <= PEAK_DBTP:
            gain += TARGET_LUFS - lu_out
        else:
            break
    _mp3(voice, out_voice, title + "（只有人声，对齐用）", 1, gain)

    # 5. 量：和 b2 同样的两项（说话时、章间空隙），另加"句间停顿里升到多少"
    g = 10 ** (gain / 20)
    ev, em = M._kframes(voice * g) * 2, M._kframes(music * g)
    fr = M.FRAME
    talk_mask = np.zeros(len(ev), bool)
    for v, e in zip(pl["voice_starts"], pl["voice_ends"]):
        talk_mask[int((v + 0.3) / fr):int((e - 0.3) / fr)] = True
    vt = M._lu(ev[talk_mask], gated=False)
    mt = M._lu(em[talk_mask & talk[:len(em)]], gated=False)
    gap_mask = np.zeros(len(ev), bool)
    for i, bd in enumerate(pl["bounds"][:-1]):
        gap_mask[int(bd / fr):int((pl["voice_starts"][i + 1] - TIME["压下提前"]) / fr)] = True
    mg = M._lu(em[gap_mask], gated=False) if gap_mask.any() else None
    pk = [float(curve[a_:b_].max()) for a_, b_, c_ in M._runs(np.where(code == 0, 3, code).astype(np.int8)) if c_ == 3]
    meas = {"整体响度LUFS": round(lu_out, 2), "真峰值dBTP": round(tp_out, 2), "整体增益dB": round(gain, 2),
            "人声说话时LUFS": vt, "音乐·说话时（比人声）dB": round(mt - vt, 1) if mt is not None and vt else None,
            "音乐·空隙里浮到（比人声说话时）dB": round(mg - vt, 1) if mg is not None and vt else None,
            "配乐": "避让（声音包「%s」，底乐 %s）" % (spec.get("名称"), bed_path.name),
            "避让：升起来的停顿数": len(pk),
            "避让：停顿里底乐最高升到（配置dB，最低/中位/最高）": [round(min(pk), 1), round(float(np.median(pk)), 1), round(max(pk), 1)] if pk else None,
            "参考响度": {"人声": round(ref_v, 2), "Lyria": round(ref_l, 2), "底乐": round(ref_b, 2)}}
    log("  混音（避让，底乐 %s）：%s LUFS、真峰值 %s dBTP；音乐说话时比人声低 %s dB，章间空隙里 %s dB" % (
        bed_path.name, meas["整体响度LUFS"], meas["真峰值dBTP"], meas["音乐·说话时（比人声）dB"], meas["音乐·空隙里浮到（比人声说话时）dB"]))
    return meas


def describe(pl):
    """给视频数据用的配乐说明（网页可以拿 credit 去署名）。"""
    if pl.get("style") == "avoid":
        spec, bed, _info = _package()
        cr = _credit(bed.name, spec)
        return {"credit": {k: cr[k] for k in ("zh", "en")}, "attribution": cr["attribution"], "url": cr["url"],
                "license_url": cr["license_url"], "note": cr["note_zh"],
                "pieces": [
                    {"what": "片头乐句", "from": "Google Lyria 3（播客片尾曲那次生成，lyria_raw/outro_lyria-3-clip.mp3）第 %d 拍起 %d 拍" % (INTRO["从第几拍"], INTRO["拍数"]),
                     "license": "Lyria 输出，许可待核"},
                    {"what": "底乐（说话时退后、停顿时浮上来）", "from": "pipeline/assets/music/v3/%s（声音包「%s」，和播客同一套避让）" % (bed.name, spec.get("名称")),
                     "license": "CC BY 4.0"},
                    {"what": "片尾", "from": "同一段 Lyria 第 %d 拍（%.2f 秒）起到余音落尽" % (pl["outro_from_beat"], pl["outro_src_sec"]),
                     "license": "Lyria 输出，许可待核"}],
                "bpm": pl["bpm"], "meters": pl["meters"], "beats": pl["beats"], "downbeats": pl["downbeats"],
                "intro_down": pl["intro_down"], "resolve_at": pl["resolve_at"]}
    return {"credit": {k: CREDIT[k] for k in ("zh", "en")}, "attribution": CREDIT["attribution"], "url": CREDIT["url"],
            "license_url": CREDIT["license_url"], "note": CREDIT["note_zh"],
            "pieces": [
                {"what": "片头乐句", "from": "Google Lyria 3（播客片尾曲那次生成，lyria_raw/outro_lyria-3-clip.mp3）第 %d 拍起 %d 拍" % (INTRO["从第几拍"], INTRO["拍数"]),
                 "license": "Lyria 输出，许可待核"},
                {"what": "底乐", "from": "pipeline/assets/music/v3/bed_bright.flac（Castles in the Sky 第 %d 拍起 %d 拍的循环，与播客 B2 相同）" % (CASTLES["从第几拍"], CASTLES["拍数"]),
                 "license": "CC BY 4.0"},
                {"what": "空隙里浮起", "from": "Castles in the Sky 同一段循环，不挖人声频段", "license": "CC BY 4.0"},
                {"what": "片尾", "from": "同一段 Lyria 第 %d 拍（%.2f 秒）起到余音落尽" % (pl["outro_from_beat"], pl["outro_src_sec"]),
                 "license": "Lyria 输出，许可待核"}],
            "bpm": pl["bpm"], "meters": pl["meters"], "beats": pl["beats"], "downbeats": pl["downbeats"],
            "intro_down": pl["intro_down"], "resolve_at": pl["resolve_at"]}


if __name__ == "__main__":
    print(json.dumps(plan([7.0, 20.0, 18.0, 18.0, 18.0, 14.0, 6.5], style=(sys.argv[1] if len(sys.argv) > 1 else None)),
                     ensure_ascii=False, indent=1)[:1500])
