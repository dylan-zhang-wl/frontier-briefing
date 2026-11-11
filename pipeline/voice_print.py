#!/usr/bin/env python3
"""音色把关：配完一段，查一查"还是不是那个人"。

为什么要有：Gemini 设计的声音每次合成都会在这个人附近"飘"一下，偶尔一轮飘得像另一个人（11-01 对谈第 52 轮），
而音高把关抓不到这种不像——音高正常、音色远了。详见 配音测试/音色一致性_1101/README.md。

怎么查：
    · "音色指纹"＝说话人识别模型 SpeechBrain ECAPA-TDNN（speechbrain/spkrec-ecapa-voxceleb）把一段人声变成 192 个数；
      两段越像同一个人，两串数的余弦相似度越高（最高 1）。绝对数没有意义，门槛是拿"同一个人"和"不同的人"的录音实测定的。
    · 每个声音建一份"档案指纹"：pipeline/assets/voices/音色指纹/<叫法>.npy（每块参考人声一行），旁边的 .json 写明来源、
      内容指纹（sha1）、模型版本、生成时间。参考人声本身存在 pipeline/assets/voices/参考人声/（16 kHz 单声道 flac），
      换电脑、换模型时用 build-refs 从它重建。
    · 一段新配音的"相似度"＝和档案里每一块分别比、取平均（和 11-01 测量时的算法一样，门槛才对得上）。
    · 只用说话的部分：先去掉停顿；说话不到 5 秒的段量不准，不判（和音高把关"有声不足不判"一个意思）。
    · 变速过的声音（乙稍快、男声06 等）和音高把关一样，量变速之前的原声。

三层判定（门槛默认值来自 11-01 测量；voice_profile.json 有"音色把关"一节就读那一节）：
    段（每块／每轮，说话≥5 秒）：低于 0.60 重录，低于 0.65 提醒；
    章（这个人一章里的各轮拼起来，说话≥20 秒）：低于 0.75 提醒；
        —— 不到 20 秒的章不判：单独一块 10–20 秒的录音，同一个人也有约四分之一低于 0.75，判了全是误报；
    整期（各章指纹按说话时长加权平均，对档案）：低于 0.85 提醒——"声音可能变了，比如模型升级，或者档案该重建了"。
11-01 用现有合格素材试算：说话≥5 秒的 84 段里重录 0、提醒 1；对谈各章 0 章提醒；MiMo 的几个女声全部抓到；
抓不到的是和庚A 很像的几个 Gemini 设计女声（戊、己、F1）——这道把关管"明显换了个人"，不管"变成一个相近的人"。

模型装不上、加载不了（比如云端没装 speechbrain）时，所有判定返回 {"判定": "未判", "说明": 原因}，程序照常往下走，不报错。
FD_VOICEPRINT_OFF=1 直接关掉。

接线（tts.py、dialog_tts.py、video3_build.py）：
    import voice_print
    chk = voice_print.Checker("庚A")                  # 或 Checker.for_cfg(cfg)：按声音 ID／参考音认出是谁，认不出返回 None
    r = chk.segment(原始音频)                          # 每块／每轮的每一条配完 → 小字典，写进 qc 的这一条
    r = chk.chapter([本章这个人选用的各条原始音频])     # 每章配完（工作日、视频一章一块就传 [那一块]）
    s = chk.episode()                                 # 整期收尾：用前面 chapter() 记下的指纹
音频可以是路径，也可以是数组（再给 sr）。返回的都是能直接 json.dumps 的小字典。

命令行：
    python pipeline/voice_print.py build-refs [--only 庚A 男声03] [--from-cache]   建档（已有参考人声就从它重建）
    python pipeline/voice_print.py check 音频.wav [更多…] --voice 庚A [--chapter]  查一段（--chapter：几段拼成一章查）
    python pipeline/voice_print.py status                                          模型能不能用、有哪些档案

装哪些包（云端要用时）：speechbrain（会带上 torchaudio、hyperpyyaml、sentencepiece 等）、torch、numpy、scipy；外加 ffmpeg 命令。
模型约 85 MB，第一次用时从 Hugging Face 下载（免费），放 ~/.cache/frontier-daily/models/（FD_VOICEPRINT_MODELS 可改）。
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

import numpy as np

# ============================ 可改区 ============================

MODEL_SRC = "speechbrain/spkrec-ecapa-voxceleb"
MODEL_ROOT = Path(os.environ.get("FD_VOICEPRINT_MODELS") or Path.home() / ".cache/frontier-daily/models")
MODEL_DIR = MODEL_ROOT / "spkrec-ecapa-voxceleb"
VEC_CACHE = Path(os.environ.get("FD_VOICEPRINT_CACHE") or Path.home() / ".cache/frontier-daily/voice_print")
THREADS = int(os.environ.get("FD_VOICEPRINT_THREADS") or 4)

HERE = Path(__file__).resolve().parent
VOICES = HERE / "assets/voices"
PRINT_DIR = VOICES / "音色指纹"          # <叫法>.npy ＋ <叫法>.json
REF_DIR = VOICES / "参考人声"            # <叫法>_<序号>_<块名>.flac
PROFILE = HERE / "voice_profile.json"

SR = 16000                               # 模型要 16 kHz 单声道

# 门槛默认值（2026-11-01 测量定的；profile"音色把关"一节同名的键会覆盖）
DEFAULTS = {
    "段重录线": 0.60,
    "段提醒线": 0.65,
    "章提醒线": 0.75,
    "整期提醒线": 0.85,
    "段说话不足秒不判": 5.0,
    "章说话不足秒不判": 20.0,
    "整期说话不足秒不判": 30.0,
}

# 建档用的参考人声（只在第一次建档、项目里还没有 参考人声/*.flac 时用到；之后以项目里的 flac 为准）。
# 都是配音缓存里的原始合成：不带音乐、没变速、没混响。四个声音都念的是第四、五轮同一段样稿（10-31 工作日稿开场＋热点一）。
_C = Path.home() / ".cache/frontier-daily/tts/chunks"
REF_SOURCES = {
    "庚A": {"声音ID": "voice_7c77bbe9-d6aa-4919-8353-3aae65f71cb7",
           "说明": "庚A 定稿样音的人声版（第五轮 人声_庚A，带抬高那句），11-01 测量的锚点",
           "块": [("开场", _C / "3195a0bf80da7944fb01.wav"), ("热点一", _C / "bde8e8e7f69315cc910f.wav")]},
    "乙稍快": {"参考音": VOICES / "乙_MiMo参考音.wav",
            "说明": "乙稍快 备用样音的人声版，加快之前的原声（第五轮 人声_乙稍快）",
            "块": [("开场", _C / "061581897a25c980d8a1.wav"), ("热点一", _C / "a162ef4e8855d8830bde.wav")]},
    "男声03": {"声音ID": "voice_75b4b332-ee1b-472e-a864-0e71fdb5d3cc",
            "说明": "第七轮 03 Gemini·沉稳带笑（GM-C1）单人版人声，变速之前的原声",
            "块": [("开场", _C / "9137c2338ef77efc099d.wav"), ("热点一", _C / "39fe8047c17b8d76f361.wav")]},
    "男声06": {"参考音": VOICES / "男声06_MiMo参考音.wav",
            "说明": "第七轮 06 MiMo·温和知性（MM-A）单人版人声，变速之前的原声",
            "块": [("开场", _C / "ac499804d931261d853d.wav"), ("热点一", _C / "aaf1e2737beed2a5be30.wav")]},
}

# ==============================================================


def settings(profile=None):
    """门槛：默认值，被 voice_profile.json 的"音色把关"一节覆盖（只认上面 DEFAULTS 里的键名）。"""
    out = dict(DEFAULTS)
    try:
        prof = profile if isinstance(profile, dict) else json.loads(Path(profile or PROFILE).read_text(encoding="utf-8"))
        for k, v in (prof.get("音色把关") or {}).items():
            if k in out and isinstance(v, (int, float)):
                out[k] = float(v)
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return out


# ---------------------------------------------------------------- 模型（懒加载）

_MODEL = None
_MODEL_ERR = None
_MODEL_INFO = None


def _sha1_file(p, chunk=1 << 20):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _load():
    """第一次用到时才加载；失败就记下原因，以后都返回 None（不再重试，不报错）。"""
    global _MODEL, _MODEL_ERR, _MODEL_INFO
    if _MODEL is not None or _MODEL_ERR is not None:
        return _MODEL
    if os.environ.get("FD_VOICEPRINT_OFF"):
        _MODEL_ERR = "FD_VOICEPRINT_OFF 关掉了音色把关"
        return None
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import torch
            from speechbrain.inference.speaker import EncoderClassifier
            from speechbrain.utils.fetching import FetchConfig
            torch.set_num_threads(THREADS)
            have = (MODEL_DIR / "embedding_model.ckpt").exists()
            # 已经下载过就完全不联网；没有才从 Hugging Face 下一次（下载缓存也放 MODEL_ROOT/hf，不碰全局 HF_HOME）
            m = EncoderClassifier.from_hparams(
                source=MODEL_SRC, savedir=str(MODEL_DIR), run_opts={"device": "cpu"},
                fetch_config=FetchConfig(allow_network=not have, huggingface_cache_dir=str(MODEL_ROOT / "hf")))
            m.eval()
        import importlib.metadata as md
        _MODEL_INFO = {"名字": MODEL_SRC, "speechbrain": md.version("speechbrain"), "torch": torch.__version__,
                       "权重sha1": _sha1_file((MODEL_DIR / "embedding_model.ckpt").resolve())}
        _MODEL = m
    except Exception as e:                       # 没装、下载失败、文件坏了……一律记下原因
        _MODEL_ERR = f"音色指纹模型用不了：{type(e).__name__}: {str(e)[:200]}"
    return _MODEL


def status():
    """{"能用": bool, "说明": 原因, "模型": 名字和版本, "档案": [有哪些声音]}"""
    m = _load()
    return {"能用": m is not None, "说明": _MODEL_ERR or "", "模型": _MODEL_INFO,
            "档案": sorted(p.stem for p in PRINT_DIR.glob("*.npy"))}


# ---------------------------------------------------------------- 读音频、只留说话部分


def read_audio(src, sr=None):
    """路径（ffmpeg 解码）或数组（要给 sr）→ 16 kHz 单声道 float64。"""
    if isinstance(src, (str, Path)):
        r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(src), "-f", "f64le", "-ac", "1",
                            "-ar", str(SR), "-"], capture_output=True)
        if r.returncode:
            raise RuntimeError(f"读不了 {src}：{r.stderr.decode(errors='replace')[-300:]}")
        return np.frombuffer(r.stdout, dtype=np.float64).copy()
    if sr is None:
        raise ValueError("传数组时要给 sr（采样率）")
    x = np.asarray(src, dtype=np.float64)
    if x.ndim == 2:                              # 多声道：哪一维短，哪一维就是声道
        x = x.mean(axis=1 if x.shape[1] <= x.shape[0] else 0)
    if int(sr) != SR:
        from fractions import Fraction
        from scipy.signal import resample_poly
        f = Fraction(SR, int(sr)).limit_denominator(1000)
        x = resample_poly(x, f.numerator, f.denominator)
    return x


def _frames_db(x, h):
    n = len(x) // h
    rms = np.sqrt((x[:n * h].reshape(n, h) ** 2).mean(axis=1) + 1e-20)
    return n, 20 * np.log10(rms)


def trim(x, sr=SR, floor_db=40.0, pad=0.1):
    """去掉首尾静音（20 毫秒一帧，比最响一帧低 40 dB 以下算静音，两头各留 0.1 秒）。"""
    h = int(0.02 * sr)
    if len(x) < 3 * h:
        return x
    n, db = _frames_db(x, h)
    on = np.where(db > db.max() - floor_db)[0]
    return x[max(0, on[0] * h - int(pad * sr)):min(len(x), (on[-1] + 1) * h + int(pad * sr))]


def speech_only(x, sr=SR, floor_db=40.0, hang=0.1):
    """只留说话的部分：比最响一帧低 40 dB 以内算"有声音"，前后各多留 0.1 秒，长停顿去掉。
    这样原始合成（停顿长）和成品（停顿缩短过）比的是同样的东西。"""
    h = int(0.02 * sr)
    if len(x) < 3 * h:
        return x
    n, db = _frames_db(x, h)
    on = db > db.max() - floor_db
    k = int(round(hang / 0.02))
    on = np.convolve(on.astype(int), np.ones(2 * k + 1, dtype=int), mode="same") > 0
    return x[:n * h][np.repeat(on, h)]


def _speech(src, sr=None):
    return speech_only(trim(read_audio(src, sr)))


# ---------------------------------------------------------------- 指纹


def _embed_speech(x):
    """只含说话部分的 16 kHz 音频 → 单位长度的 192 维向量；模型用不了返回 None。按内容缓存。"""
    m = _load()
    if m is None:
        return None
    x32 = np.ascontiguousarray(x, dtype=np.float32)
    key = hashlib.sha1(x32.tobytes() + _MODEL_INFO["权重sha1"].encode()).hexdigest()[:24]
    f = VEC_CACHE / f"{key}.npy"
    if f.exists():
        try:
            return np.load(f)
        except Exception:
            pass
    import torch
    with torch.no_grad():
        e = m.encode_batch(torch.from_numpy(x32[None])).squeeze().numpy().astype(np.float64)
    e = e / np.linalg.norm(e)
    try:
        VEC_CACHE.mkdir(parents=True, exist_ok=True)
        np.save(f, e)
    except OSError:
        pass
    return e


def embed(src, sr=None, min_speech=None):
    """一段音频（路径，或数组＋sr）→ 音色指纹（192 维单位向量）。
    说话部分不足 min_speech 秒（默认 5 秒）或模型用不了，返回 None。"""
    x = _speech(src, sr)
    lim = settings()["段说话不足秒不判"] if min_speech is None else min_speech
    if len(x) / SR < lim:
        return None
    return _embed_speech(x)


def load_print(voice):
    """读档案指纹：(每块一行的矩阵, 说明 json)；没有就 (None, None)。"""
    p = PRINT_DIR / f"{voice}.npy"
    if not p.exists():
        return None, None
    meta = {}
    try:
        meta = json.loads(p.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    B = np.atleast_2d(np.load(p)).astype(np.float64)
    return B / np.linalg.norm(B, axis=1, keepdims=True), meta


def similarity(v, B):
    """和档案每一块分别算余弦相似度，取平均（11-01 测量时的算法）。"""
    return float(np.mean(B @ v))


def _center(V, w=None):
    c = np.average(np.asarray(V), axis=0, weights=w)
    return c / np.linalg.norm(c)


# Shirley、Dylan 自己的 MiMo 复刻（2026-11-01 晚第十轮换成备用）：要查的正是"听着还是不是 Shirley、Dylan"，
# 所以直接用庚A、男声03 的档案判，不另建档（第十轮实测复刻对档案 0.868、0.875）。按参考音文件名认。
CLONE_OF = {"Shirley_MiMo参考音.wav": "庚A", "Dylan_MiMo参考音.wav": "男声03"}


def voice_for(cfg, profile=None):
    """按配音配置认出是哪个声音（档案的叫法）：Gemini 看声音 ID，MiMo 看参考音（文件名或内容指纹）。认不出返回 None。
    cfg 可以是 tts.py 的配置对象，也可以是 {"voice": …, "clone_ref": …} 这样的字典。
    Shirley、Dylan 的 MiMo 复刻参考音（CLONE_OF）认成本人的档案（庚A、男声03）。"""
    get = (lambda k: cfg.get(k)) if isinstance(cfg, dict) else (lambda k: getattr(cfg, k, None))
    voice, clone = get("voice"), get("clone_ref")
    if clone and Path(str(clone)).name in CLONE_OF and (PRINT_DIR / f"{CLONE_OF[Path(str(clone)).name]}.npy").exists():
        return CLONE_OF[Path(str(clone)).name]
    clone_sha = None
    for j in sorted(PRINT_DIR.glob("*.json")):
        try:
            meta = json.loads(j.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if voice and meta.get("声音ID") == voice:
            return j.stem
        if clone and meta.get("参考音"):
            if Path(str(clone)).name == Path(meta["参考音"]).name:
                return j.stem
            if clone_sha is None and Path(str(clone)).exists():
                clone_sha = _sha1_file(clone)
            if clone_sha and clone_sha == meta.get("参考音sha1"):
                return j.stem
    return None


# ---------------------------------------------------------------- 判定


def _r3(x):
    return round(float(x), 3)


class Checker:
    """一期里一个声音的音色把关。segment() 判每一条，chapter() 判每章并记下这一章的指纹，episode() 汇总整期。"""

    def __init__(self, voice, profile=None):
        self.voice = voice
        self.gate = settings(profile)
        self.B, self.meta = load_print(voice)
        self._chapters = []               # [(指纹, 说话秒数)]

    @classmethod
    def for_cfg(cls, cfg, profile=None):
        """按配音配置找声音；没有这个声音的档案就返回 None（调用方跳过音色把关即可）。"""
        name = voice_for(cfg, profile)
        return cls(name, profile) if name else None

    def _unready(self):
        """不能判的原因；能判返回 None。"""
        if self.B is None:
            return f"没有 {self.voice} 的档案指纹（先跑 python pipeline/voice_print.py build-refs）"
        if _load() is None:
            return _MODEL_ERR
        want = ((self.meta or {}).get("模型") or {}).get("权重sha1")
        if want and want != _MODEL_INFO["权重sha1"]:
            return "档案指纹是用另一版模型建的，和现在的模型比没有意义；先跑 build-refs 重建"
        return None

    def _skip(self, why, **extra):
        return {"判定": "未判", "声音": self.voice, **extra, "说明": why}

    def segment(self, src, sr=None):
        """一块／一轮（的一条）：说话≥5 秒才判。低于重录线→"重录"，低于提醒线→"提醒"，否则"通过"。
        返回 {"判定", "相似度", "说话秒数", "声音", "门槛": [重录线, 提醒线], "说明"(不通过时)}。"""
        why = self._unready()
        if why:
            return self._skip(why)
        try:
            x = _speech(src, sr)
        except Exception as e:
            return self._skip(f"读不了音频：{str(e)[:200]}")
        secs = round(len(x) / SR, 2)
        lim = self.gate["段说话不足秒不判"]
        if secs < lim:
            return self._skip(f"说话 {secs} 秒，不到 {lim:g} 秒，量不准，不判", 说话秒数=secs)
        v = _embed_speech(x)
        if v is None:
            return self._skip(_MODEL_ERR or "算不出指纹")
        s = similarity(v, self.B)
        redo, warn = self.gate["段重录线"], self.gate["段提醒线"]
        out = {"判定": "重录" if s < redo else "提醒" if s < warn else "通过", "相似度": _r3(s), "说话秒数": secs,
               "声音": self.voice, "门槛": [redo, warn]}
        if out["判定"] == "重录":
            out["说明"] = f"音色和 {self.voice} 档案只有 {s:.2f}（低于 {redo}），像换了个人，重录"
        elif out["判定"] == "提醒":
            out["说明"] = f"音色和 {self.voice} 档案 {s:.2f}（低于 {warn}），偏远，建议人工听"
        return out

    def chapter(self, srcs, sr=None):
        """一章：把这个人这一章选用的各条（只留说话部分）拼起来算一个指纹。说话≥20 秒才判，低于章提醒线→"提醒"。
        说话≥5 秒的章会记下指纹给 episode() 用（不到 20 秒的章只是不判，指纹照记）。
        返回 {"判定", "相似度", "说话秒数", "段数", "声音", "门槛", "说明"(不通过时)}。"""
        if isinstance(srcs, (str, Path)) or (isinstance(srcs, np.ndarray) and srcs.ndim == 1):
            srcs = [srcs]
        why = self._unready()
        if why:
            return self._skip(why, 段数=len(srcs))
        try:
            parts = [_speech(s, sr) for s in srcs]
        except Exception as e:
            return self._skip(f"读不了音频：{str(e)[:200]}", 段数=len(srcs))
        x = np.concatenate(parts) if parts else np.zeros(0)
        secs = round(len(x) / SR, 2)
        if secs < self.gate["段说话不足秒不判"]:
            return self._skip(f"这一章说话 {secs} 秒，太短，不判", 说话秒数=secs, 段数=len(srcs))
        v = _embed_speech(x)
        if v is None:
            return self._skip(_MODEL_ERR or "算不出指纹", 段数=len(srcs))
        self._chapters.append((v, secs))
        s = similarity(v, self.B)
        lim, warn = self.gate["章说话不足秒不判"], self.gate["章提醒线"]
        if secs < lim:
            return self._skip(f"这一章说话 {secs} 秒，不到 {lim:g} 秒，章这一层不判（各条已按段判过）",
                              相似度=_r3(s), 说话秒数=secs, 段数=len(srcs))
        out = {"判定": "提醒" if s < warn else "通过", "相似度": _r3(s), "说话秒数": secs, "段数": len(srcs),
               "声音": self.voice, "门槛": warn}
        if out["判定"] == "提醒":
            out["说明"] = f"这一章整体音色和 {self.voice} 档案只有 {s:.2f}（低于 {warn}），建议人工听"
        return out

    def episode(self):
        """整期：前面 chapter() 记下的各章指纹，按说话时长加权平均，和档案的平均指纹比。低于整期提醒线→"提醒"。
        返回 {"判定", "整期对档案", "章数", "说话秒数", "声音", "门槛", "模型", "说明"(不通过时)}。"""
        why = self._unready()
        if why:
            return self._skip(why)
        secs = round(sum(t for _, t in self._chapters), 1)
        if not self._chapters or secs < self.gate["整期说话不足秒不判"]:
            return self._skip(f"整期只量到 {secs} 秒说话，太少，不判", 章数=len(self._chapters), 说话秒数=secs)
        c = _center([v for v, _ in self._chapters], [t for _, t in self._chapters])
        s = float(c @ _center(self.B))
        warn = self.gate["整期提醒线"]
        out = {"判定": "提醒" if s < warn else "通过", "整期对档案": _r3(s), "章数": len(self._chapters),
               "说话秒数": secs, "声音": self.voice, "门槛": warn, "模型": (_MODEL_INFO or {}).get("名字")}
        if out["判定"] == "提醒":
            out["说明"] = (f"整期平均音色和 {self.voice} 档案只有 {s:.2f}（低于 {warn}）：声音可能变了（比如模型升级），"
                         "或者档案指纹该重建了，建议人工听")
        return out


def check_segment(src, voice, sr=None, profile=None):
    """不想建 Checker 时的快捷写法：判一段。"""
    return Checker(voice, profile).segment(src, sr)


def check_chapter(srcs, voice, sr=None, profile=None):
    """快捷写法：判一章（几段拼起来）。"""
    return Checker(voice, profile).chapter(srcs, sr)


# ---------------------------------------------------------------- 建档


def _write_flac(x, path):
    """16 kHz 单声道 16 位 flac（ffmpeg 写，不依赖 soundfile）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "f64le", "-ar", str(SR), "-ac", "1", "-i", "-",
                        "-c:a", "flac", "-sample_fmt", "s16", str(path)],
                       input=np.ascontiguousarray(x, dtype=np.float64).tobytes(), capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace")[-300:])


def _rel(p):
    p = Path(p)
    try:
        return str(p.resolve().relative_to(HERE.parent))
    except ValueError:
        return str(p).replace(str(Path.home()), "~")


def build_refs(only=None, from_cache=False, log=print):
    """建档：①项目里还没有参考人声（或 from_cache）→ 从配音缓存的原始合成剪掉首尾静音，存成 16 kHz flac；
    ②用 参考人声/ 里的 flac 算档案指纹，存 .npy ＋ .json。已有 flac 时只做②（换电脑、换模型就这样重建）。"""
    if _load() is None:
        log(f"✗ {_MODEL_ERR}")
        return False
    ok = True
    for voice, src in REF_SOURCES.items():
        if only and voice not in only:
            continue
        flacs = sorted(REF_DIR.glob(f"{voice}_*.flac"))
        old = {}
        try:
            old = json.loads((PRINT_DIR / f"{voice}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        origin = {b.get("文件"): b for b in old.get("块", [])}
        if not flacs or from_cache:
            missing = [str(p) for _, p in src["块"] if not p.exists()]
            if missing:
                log(f"✗ {voice}：项目里没有参考人声，缓存里的原始合成也找不到：{missing}")
                ok = False
                continue
            for f in flacs:
                f.unlink()
            flacs = []
            for i, (name, p) in enumerate(src["块"], 1):
                f = REF_DIR / f"{voice}_{i}_{name}.flac"
                _write_flac(trim(read_audio(p)), f)
                flacs.append(f)
                origin[_rel(f)] = {"来源": _rel(p), "来源sha1": _sha1_file(p)}
        rows, blocks = [], []
        for f in flacs:
            x = _speech(f)
            v = _embed_speech(x)
            rows.append(v)
            o = origin.get(_rel(f), {})
            blocks.append({"文件": _rel(f), "sha1": _sha1_file(f), "说话秒数": round(len(x) / SR, 2),
                           "来源": o.get("来源"), "来源sha1": o.get("来源sha1")})
        B = np.array(rows, dtype=np.float32)
        PRINT_DIR.mkdir(parents=True, exist_ok=True)
        np.save(PRINT_DIR / f"{voice}.npy", B)
        meta = {"叫法": voice, "说明": src["说明"]}
        if src.get("声音ID"):
            meta["声音ID"] = src["声音ID"]
        if src.get("参考音"):
            meta["参考音"] = _rel(src["参考音"])
            meta["参考音sha1"] = _sha1_file(src["参考音"]) if Path(src["参考音"]).exists() else None
        meta.update({"块": blocks, "块之间相似度": _r3(float(B[0] @ B[1])) if len(B) > 1 else None,
                     "模型": _MODEL_INFO, "生成于": time.strftime("%Y-%m-%d %H:%M"),
                     "怎么比": "新配音的相似度＝和这里每一块分别算余弦相似度再平均；整期比的是各块平均后的方向"})
        (PRINT_DIR / f"{voice}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"✓ {voice}：{len(B)} 块，说话共 {sum(b['说话秒数'] for b in blocks):.1f} 秒，块之间 {meta['块之间相似度']}")
    return ok


# ---------------------------------------------------------------- 命令行


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="音色把关：建档、查一段")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-refs", help="建档（已有参考人声就从它重建档案指纹）")
    b.add_argument("--only", nargs="*", help="只建这几个声音（叫法）")
    b.add_argument("--from-cache", action="store_true", help="不管项目里有没有，从配音缓存重新剪参考人声")
    c = sub.add_parser("check", help="查一段（或几段拼成一章）")
    c.add_argument("audio", nargs="+")
    c.add_argument("--voice", required=True, help="档案的叫法，如 庚A、乙稍快、男声03、男声06")
    c.add_argument("--chapter", action="store_true", help="把几段拼成一章来判")
    sub.add_parser("status", help="模型能不能用、有哪些档案")
    a = ap.parse_args(argv)
    if a.cmd == "build-refs":
        return 0 if build_refs(a.only, a.from_cache) else 1
    if a.cmd == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=1))
        return 0
    chk = Checker(a.voice)
    if a.chapter:
        print(json.dumps(chk.chapter(a.audio), ensure_ascii=False, indent=1))
    else:
        for p in a.audio:
            print(json.dumps({"音频": p, **chk.segment(p)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
