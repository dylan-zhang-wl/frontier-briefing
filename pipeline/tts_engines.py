#!/usr/bin/env python3
"""配音引擎：Gemini 3.8 TTS（Vertex，或 Gemini API）与小米 MiMo-V2.5-TTS。tts.py 调这里，单独也能用。

Gemini API（engine=gemini-api，10-31 晚起配音走这条：主账号的 AI Studio 项目 frontier-daily，主账号订阅额度）
    · 密钥只从 macOS 钥匙串（服务名 frontier-daily-gemini）现取进内存，放在 x-goog-api-key 请求头里，
      不进网址、不打印、不落盘；GitHub Actions 上改给环境变量 GEMINI_API_KEY。
    · 造声音：POST v1beta/voices，voice 里要写 model（这条和 Vertex 相反）、type=prompted、store=true；
      合成：POST v1beta/interactions，声音放 generation_config.speech_config[0].voice，
      风格放文本的 speech_metadata 注解（style）。按 https://ai.google.dev/gemini-api/docs/voice-design、
      /speech-generation（2026-10-31 读）。两条路的模型名都用下面的 GEMINI_FLASH / GEMINI_LITE，改一处就行。
    · 声音绑定项目：Vertex 那个项目里造的 F1、M1 在这里用不了，反之亦然。

Gemini（Vertex，2026-10-31 按 Vertex 文档核过；当时的项目是另一个不许用的项目，10-31 晚起配音不再用）
    · 合成：POST v1/projects/P/locations/global/publishers/google/models/<模型>:generateContent
      风格放 parts[0].speechMetadata.style；声音放 generationConfig.speechConfig.voiceConfig.voice，
      可以是自造声音 ID（voice_…）、预置声音名（如 charon）或扩展音色库 ID。
    · 造声音：POST v1beta1/projects/P/locations/global/voices（Voices API，Preview，只有 global）。
      type=VOICE_TYPE_PROMPTED、store=true，不能设 voice.model。按 Flash TTS 单价计费（约 1 美分）。
    · 列声音不计费。令牌每次由 gcloud 现取，只放内存、5 分钟内复用，不落盘、不打印。
    · 两个模型（flash / flash-lite）请求格式完全相同，都能用自造声音。

MiMo（https://mimo.mi.com/static/docs/api/audio/tts.md）
    · OpenAI 兼容的 chat/completions：assistant 消息放要念的文本，user 消息放风格说明
      （声音设计模型里 user 消息就是音色描述，必填）。
    · mimo-v2.5-tts 用 audio.voice 选内置音色（冰糖、茉莉为中文女声）；
      mimo-v2.5-tts-voicedesign 不接受 voice；mimo-v2.5-tts-voiceclone 的 voice 是
      data:audio/wav;base64,… 形式的参考音频（≤10MB）。
    · 地址取 MIMO_BASE_URL（Token Plan 的 tp- 密钥要配 Token Plan 地址），密钥见 keys.py。
    · 声音设计的 optimize_text_preview 会"润色"原文，这里明确关掉，保证一字不改。

用法（单独调试）：
    python pipeline/tts_engines.py gemini-api-voices        # 列主账号项目里自造的声音（Gemini API，不计费）
    python pipeline/tts_engines.py gemini-voices            # 列 Vertex 项目里自造的声音（不计费）
    python pipeline/tts_engines.py gemini-prebuilt charon   # 在预置/音色库里按名字或描述搜
"""
import base64
import io
import json
import os
import subprocess
import sys
import time
import wave

import requests

sys.dont_write_bytecode = True
import keys  # noqa: E402

# ============================ 可改区 ============================

GCP_PROJECT = "gen-lang-client-0975170599"      # 主账号的 frontier-daily 项目（Vertex，结算账号 1，主账号订阅的每月赠金先抵扣）
# 本机用 gcloud 取令牌时用哪个 Google 账号（主账号）：地址不进仓库，写在环境变量 FD_GCP_ACCOUNT 里；没设就用 gcloud 当前的默认账号。
# 云端不用 gcloud：配音用 GitHub 身份换来的一小时令牌（环境变量 GCP_ACCESS_TOKEN），用不到这个账号。fd doctor 读这两行。
GCP_ACCOUNT = ""
GCP_ACCOUNT = os.environ.get("FD_GCP_ACCOUNT") or GCP_ACCOUNT
# 配音绝不能用的 Google 项目（2026-11-01 加，全项目只这一份）：另一个账号的项目，另有用途，配音、文字模型、生图都不用。
# Gemini（Vertex）、GeminiAPI 建客户端时都查（check_project），tts.py 单人、视频旁白、dialog_tts 对谈都经过这里。
FORBIDDEN_PROJECTS = ("gen-lang-client-0665640995",)
GCLOUD = "~/google-cloud-sdk/bin/gcloud"
GCLOUD = os.path.expanduser(os.environ.get("FD_GCLOUD") or GCLOUD)   # FD_GCLOUD：别的机器上 gcloud 的位置；没设时用家目录下的 google-cloud-sdk（fd doctor 读上一行，自己展开 ~）
VERTEX = "https://aiplatform.googleapis.com"

GEMINI_FLASH = "gemini-3.8-flash-tts"          # 两条路共用；换模型只改这里
GEMINI_LITE = "gemini-3.8-flash-lite-tts"

# Gemini API（主账号 AI Pro 额度）。项目和账号只用来记录：Gemini API 按密钥所属的项目计费
GEMINI_API = "https://generativelanguage.googleapis.com"
GEMINI_API_KEYCHAIN = "frontier-daily-gemini"     # macOS 钥匙串里的服务名
GEMINI_API_PROJECT = "gen-lang-client-0975170599" # AI Studio 项目 frontier-daily
GEMINI_API_ACCOUNT = GCP_ACCOUNT               # 同一个主账号（只用来记录）

# Gemini API 价目页（2026-10-30 核）：美元 / 百万 token。2027-01-01 起翻倍。
# Vertex 价目页是脚本渲染、没抓到原文，第三方显示的数字相同，所以这里只算"估计"。
PRICES = {
    GEMINI_FLASH: {"2026": (0.50, 9.00), "2027": (1.00, 18.00)},
    GEMINI_LITE: {"2026": (0.50, 6.00), "2027": (1.00, 12.00)},
}
AUDIO_TOKENS_PER_SEC = 25

MIMO_BUILTIN = "mimo-v2.5-tts"
MIMO_DESIGN = "mimo-v2.5-tts-voicedesign"
MIMO_CLONE = "mimo-v2.5-tts-voiceclone"

# ==============================================================


def price_per_million(model, when=None):
    """返回 (输入单价, 音频输出单价)，美元 / 百万 token。"""
    when = when or time.strftime("%Y-%m-%d")
    table = PRICES.get(model, PRICES[GEMINI_FLASH])
    return table["2027"] if when >= "2027-01-01" else table["2026"]


def gemini_cost(model, prompt_tokens, audio_tokens, when=None):
    pin, pout = price_per_million(model, when)
    return (prompt_tokens or 0) * pin / 1e6 + (audio_tokens or 0) * pout / 1e6


def as_wav(data, rate=24000):
    """接口一般给完整 WAV；万一是裸 PCM（16 位单声道），按给定采样率包一层文件头。"""
    if data[:4] == b"RIFF":
        return data
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data)
    return buf.getvalue()


def wav_seconds(data):
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / float(w.getframerate())


def _get(d, *names):
    """接口有时用驼峰、有时用下划线，两种都认。"""
    for n in names:
        if isinstance(d, dict) and n in d:
            return d[n]
    return None


class TTSError(RuntimeError):
    pass


class ForbiddenProject(ValueError):
    """要用的 Google 项目在 FORBIDDEN_PROJECTS 里。故意不是 TTSError：这是配置错，不该被"Gemini 出错就换备用声音"悄悄接住。"""


def check_project(project):
    """项目在 FORBIDDEN_PROJECTS 里就停（建 Vertex / Gemini API 客户端时、每次发请求前都查）。"""
    if str(project or "").strip() in FORBIDDEN_PROJECTS:
        raise ForbiddenProject(f"Google 项目 {project} 是留给大论文的赠金项目，配音不能用"
                               "（改 pipeline/tts_engines.py 的 GCP_PROJECT / GEMINI_API_PROJECT）")
    return project


# ------------------------------------------------------------------ Gemini


class Gemini:
    def __init__(self, project=None, account=GCP_ACCOUNT, location="global"):
        # project 不给就用模块里的 GCP_PROJECT（运行时读，不是定义时读），并查一遍禁用名单
        self.project = check_project(project or GCP_PROJECT)
        self.account, self.location = account, location
        self._tok, self._tok_t = None, 0.0

    def _token(self):
        """gcloud 给的令牌可能是它早先缓存的，剩余有效期未知，只复用 5 分钟。
        以后上 GitHub Actions 时可以直接给环境变量 GCP_ACCESS_TOKEN。"""
        env = os.environ.get("GCP_ACCESS_TOKEN")
        if env:
            return env
        if self._tok and time.time() - self._tok_t < 300:
            return self._tok
        acct = [f"--account={self.account}"] if self.account else []      # 没设 FD_GCP_ACCOUNT：用 gcloud 当前的默认账号
        r = subprocess.run([GCLOUD, "auth", "print-access-token"] + acct,
                           capture_output=True, text=True)
        tok = r.stdout.strip()
        if r.returncode or not tok:
            raise TTSError(f"取不到 {self.account or 'gcloud 默认账号'} 的令牌，可能要重新 gcloud auth login")
        self._tok, self._tok_t = tok, time.time()
        return tok

    def _hide(self, text):
        s = str(text)
        if self._tok:
            s = s.replace(self._tok, "<已隐藏>")
        return keys.hide(s)

    def _request(self, method, path, body=None, params=None, retries=6, timeout=300):
        """401 换令牌；429、5xx、项目初始化中，等一会儿再试。报错里抹掉令牌。"""
        check_project(self.project)                # 万一建好之后 project 被改过
        last = ""
        for i in range(retries):
            headers = {"Authorization": f"Bearer {self._token()}",
                       "x-goog-user-project": self.project,
                       "Content-Type": "application/json"}
            try:
                r = requests.request(method, VERTEX + path, headers=headers, json=body,
                                     params=params, timeout=timeout)
            except requests.RequestException as e:
                last = self._hide(f"{type(e).__name__}: {str(e)[:200]}")
                if i < retries - 1:
                    time.sleep(10 * (i + 1))
                    continue
                raise TTSError(last) from None
            if r.status_code == 401 and i < retries - 1:
                self._tok = None
                continue
            busy = r.status_code == 400 and "setup is in progress" in r.text
            if (r.status_code in (429, 500, 502, 503, 504) or busy) and i < retries - 1:
                wait = 20 * (i + 1)
                print(f"      Gemini 忙（HTTP {r.status_code}），{wait} 秒后重试", flush=True)
                time.sleep(wait)
                continue
            if r.status_code != 200:
                raise TTSError(self._hide(f"Gemini HTTP {r.status_code}：{r.text[:500]}"))
            return r.json()
        raise TTSError(last or "Gemini 请求失败")

    # 造声音 --------------------------------------------------------
    def create_voice(self, description, display_name, gender, language_code):
        """返回 {"voice_id", "sample_wav", "usage", "raw_keys"}。每次结果都不一样，约 1 美分。"""
        body = {"store": True,
                "voice": {"type": "VOICE_TYPE_PROMPTED", "displayName": display_name,
                          "gender": gender, "languageCode": language_code,
                          "prompted": {"input": description}}}
        d = self._request("POST", f"/v1beta1/projects/{self.project}/locations/global/voices",
                          body, timeout=120)
        v = d.get("voice", d)
        vid = _get(v, "id") or _get(d, "id") or _get(v, "name")
        sample = _get(d, "sample_audio", "sampleAudio") or _get(v, "sample_audio", "sampleAudio") or {}
        wav = None
        if sample.get("data"):
            wav = as_wav(base64.b64decode(sample["data"]))
        usage = _get(d, "usage", "usageMetadata") or {}
        raw = json.loads(json.dumps(d))           # 原始返回（音频去掉），和 GeminiAPI.create_voice 同样的键，方便调用方换路线
        for x in _walk(raw):
            if "data" in x and isinstance(x["data"], str) and len(x["data"]) > 200:
                x["data"] = f"<音频 {len(x['data'])} 个 base64 字符，已另存>"
        return {"voice_id": str(vid).split("/")[-1] if vid else None, "sample_wav": wav, "usage": usage,
                "sample_mime": _get(sample, "mime_type", "mimeType"), "tokens": _tokens(d), "raw": raw}

    def list_voices(self, types=None, search=None, max_pages=60):
        """types 例如 ["prompted", "replicated"]（项目里自造的）或 ["prebuilt"]。不计费。"""
        out, page = [], None
        for _ in range(max_pages):
            params = [("pageSize", "50")]
            for t in types or []:
                params.append(("type", t))
            if search:
                params.append(("search", search))
            if page:
                params.append(("pageToken", page))
            d = self._request("GET", f"/v1beta1/projects/{self.project}/locations/global/voices",
                              params=params, timeout=60)
            out += d.get("voices", [])
            page = d.get("nextPageToken") or d.get("next_page_token")
            if not page:
                break
        return out

    # 合成 ----------------------------------------------------------
    def synthesize(self, text, voice, style=None, model=GEMINI_FLASH, language_code=None):
        """返回 (WAV 字节, 用量字典)。用量里有接口报的 token 数和按价目估的费用。"""
        part = {"text": text}
        if style:
            part["speechMetadata"] = {"style": style}
        speech = {"voiceConfig": {"voice": voice}}
        if language_code:
            speech["languageCode"] = language_code
        body = {"contents": [{"role": "user", "parts": [part]}],
                "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": speech}}
        t0 = time.time()
        d = self._request("POST", f"/v1/projects/{self.project}/locations/{self.location}/"
                                  f"publishers/google/models/{model}:generateContent", body)
        cand = (d.get("candidates") or [{}])[0]
        finish = cand.get("finishReason") or cand.get("finish_reason")
        wav = None
        for p in (cand.get("content") or {}).get("parts", []):
            inline = _get(p, "inlineData", "inline_data")
            if inline and inline.get("data"):
                wav = as_wav(base64.b64decode(inline["data"]))
                break
        if wav is None:
            raise TTSError(f"Gemini 返回里没有音频（finishReason={finish}）")
        secs = wav_seconds(wav)
        um = d.get("usageMetadata") or {}
        prompt_tokens = um.get("promptTokenCount")
        audio_tokens = um.get("candidatesTokenCount")
        est_audio = round(secs * AUDIO_TOKENS_PER_SEC)
        usage = {"engine": "gemini", "model": model, "seconds_audio": round(secs, 2),
                 "seconds_wall": round(time.time() - t0, 1), "finish_reason": finish,
                 "prompt_tokens": prompt_tokens, "audio_tokens_reported": audio_tokens,
                 "audio_tokens_estimated": est_audio,
                 "cost_usd": round(gemini_cost(model, prompt_tokens or len(text),
                                               audio_tokens or est_audio), 5)}
        return wav, usage


# ------------------------------------------------------------------ Gemini API（AI Studio 密钥）


def _walk(d):
    """把嵌套的 dict / list 一层层摊开（找接口返回里的音频、用量，字段位置文档没写全）。"""
    if isinstance(d, dict):
        yield d
        for v in d.values():
            yield from _walk(v)
    elif isinstance(d, list):
        for v in d:
            yield from _walk(v)


def _tokens(d):
    """从返回里找输入、输出、"思考" token 数（Vertex Voices 用 total_input_tokens / total_output_tokens，generateContent 用
    promptTokenCount / candidatesTokenCount；Gemini API 的 voices 另报 total_thought_tokens，且不算在 total_tokens 里）。
    找不到的返回 None。"""
    names_in = ("total_input_tokens", "totalInputTokens", "input_tokens", "inputTokens", "prompt_token_count",
                "promptTokenCount")
    names_out = ("total_output_tokens", "totalOutputTokens", "output_tokens", "outputTokens",
                 "candidates_token_count", "candidatesTokenCount")
    names_th = ("total_thought_tokens", "totalThoughtTokens", "thoughts_token_count", "thoughtsTokenCount")
    tin = tout = th = None
    for x in _walk(d):
        for n in names_in:
            if tin is None and isinstance(x.get(n), (int, float)):
                tin = x[n]
        for n in names_out:
            if tout is None and isinstance(x.get(n), (int, float)):
                tout = x[n]
        for n in names_th:
            if th is None and isinstance(x.get(n), (int, float)):
                th = x[n]
    return tin, tout, th


def _usage_part(d):
    """返回里和用量有关的那一块（原样记下，不含音频）。"""
    for k in ("usage", "usage_metadata", "usageMetadata"):
        if isinstance(d.get(k), dict):
            return d[k]
    return None


class GeminiAPI:
    """Gemini API（generativelanguage.googleapis.com，AI Studio 密钥）。请求和返回的格式按官方文档
    voice-design、speech-generation 两页（2026-10-31 读）；返回里音频、用量的位置文档没写全，这里几种写法都认。"""

    def __init__(self, keychain=GEMINI_API_KEYCHAIN):
        check_project(GEMINI_API_PROJECT)          # 密钥属于哪个项目只能靠这里记的名字查
        self.keychain, self._key = keychain, None

    def _api_key(self):
        """GEMINI_API_KEY 环境变量优先（GitHub Actions），否则从 macOS 钥匙串现取。只放内存。"""
        if not self._key:
            k = os.environ.get("GEMINI_API_KEY", "")
            if not k:
                try:
                    r = subprocess.run(["security", "find-generic-password", "-s", self.keychain, "-w"],
                                       capture_output=True, text=True, timeout=120)
                except subprocess.TimeoutExpired:
                    raise TTSError(f"读钥匙串 {self.keychain} 超时（可能在等你点'允许'）") from None
                k = r.stdout.strip()
                if r.returncode or not k:
                    raise TTSError(f"钥匙串里读不到 {self.keychain}（security 返回 {r.returncode}）")
            self._key = k
        return self._key

    def _hide(self, text):
        s = str(text)
        if self._key:
            s = s.replace(self._key, "<已隐藏>")
        return keys.hide(s)

    def _request(self, method, path, body=None, params=None, retries=6, timeout=300):
        """429、5xx 等一会儿再试；报错里抹掉密钥。密钥只在请求头里。"""
        last = ""
        for i in range(retries):
            headers = {"x-goog-api-key": self._api_key(), "Content-Type": "application/json"}
            try:
                r = requests.request(method, GEMINI_API + path, headers=headers, json=body, params=params,
                                     timeout=timeout)
            except requests.RequestException as e:
                last = self._hide(f"{type(e).__name__}: {str(e)[:200]}")
                if i < retries - 1:
                    time.sleep(10 * (i + 1))
                    continue
                raise TTSError(last) from None
            if r.status_code in (429, 500, 502, 503, 504) and i < retries - 1:
                wait = 20 * (i + 1)
                print(f"      Gemini API 忙（HTTP {r.status_code}），{wait} 秒后重试", flush=True)
                time.sleep(wait)
                continue
            if r.status_code != 200:
                raise TTSError(self._hide(f"Gemini API HTTP {r.status_code}：{r.text[:500]}"))
            return r.json()
        raise TTSError(last or "Gemini API 请求失败")

    # 造声音 --------------------------------------------------------
    def create_voice(self, description, display_name, gender, language_code, model=GEMINI_FLASH):
        """返回 {"voice_id", "sample_wav", "usage", "sample_mime", "raw"}；raw 是去掉音频后的原始返回（记录用）。
        每次结果都不一样。language_code 被拒（400）时，不带它再试一次。"""
        voice = {"model": model, "type": "prompted", "display_name": display_name, "gender": gender,
                 "prompted": {"input": description}}
        if language_code:
            voice["language_code"] = language_code
        try:
            d = self._request("POST", "/v1beta/voices", {"store": True, "voice": voice}, timeout=180)
        except TTSError as e:
            if not language_code or "HTTP 400" not in str(e):
                raise
            print(f"      语言代码 {language_code} 被拒，不带它再试：{str(e)[:160]}", flush=True)
            voice.pop("language_code")
            d = self._request("POST", "/v1beta/voices", {"store": True, "voice": voice}, timeout=180)
        v = d.get("voice", d)
        vid = _get(v, "id") or _get(d, "id") or _get(v, "name") or _get(d, "name")
        vid = str(vid).split("/")[-1] if vid else None
        sample = _get(d, "sample_audio", "sampleAudio") or _get(v, "sample_audio", "sampleAudio") or {}
        wav = as_wav(base64.b64decode(sample["data"])) if sample.get("data") else None
        raw = json.loads(json.dumps(d))
        for x in _walk(raw):
            if "data" in x and isinstance(x["data"], str) and len(x["data"]) > 200:
                x["data"] = f"<音频 {len(x['data'])} 个 base64 字符，已另存>"
        tin, tout, th = _tokens(d)
        return {"voice_id": vid, "sample_wav": wav, "sample_mime": _get(sample, "mime_type", "mimeType"),
                "usage": _usage_part(d) or {"input_tokens": tin, "output_tokens": tout, "thought_tokens": th},
                "raw": raw, "tokens": (tin, tout, th)}

    def list_voices(self, types=None, max_pages=20):
        out, page = [], None
        for _ in range(max_pages):
            params = [("pageSize", "50")] + [("type", t) for t in types or []]
            if page:
                params.append(("pageToken", page))
            d = self._request("GET", "/v1beta/voices", params=params, timeout=60)
            out += d.get("voices", [])
            page = d.get("nextPageToken") or d.get("next_page_token")
            if not page:
                break
        return out

    # 合成 ----------------------------------------------------------
    def synthesize(self, text, voice, style=None, model=GEMINI_FLASH, language_code=None):
        """返回 (WAV 字节, 用量字典)，字段和 Gemini.synthesize 一样。language_code 这条路不用（文档说自动识别语言）。"""
        part = {"type": "text", "text": text}
        if style:
            part["annotations"] = [{"type": "speech_metadata", "style": style}]
        body = {"model": model, "input": [{"type": "user_input", "content": [part]}],
                "response_format": {"type": "audio"},
                "generation_config": {"speech_config": [{"voice": voice}]}}
        t0 = time.time()
        d = self._request("POST", "/v1beta/interactions", body)
        audio = [x for x in _walk(d.get("steps") or d.get("outputs") or d) if x.get("type") == "audio" and x.get("data")]
        if not audio:
            keys_seen = sorted({k for x in _walk(d) for k in x})[:40]
            raise TTSError(f"Gemini API 返回里没有音频（出现过的字段：{keys_seen}）")
        a = audio[-1]
        raw = base64.b64decode(a["data"])
        rate = a.get("sample_rate") or a.get("sampleRate") or 24000
        wav = as_wav(raw, int(rate))
        secs = wav_seconds(wav)
        tin, tout, th = _tokens(d)
        est_audio = round(secs * AUDIO_TOKENS_PER_SEC)
        # "思考" token 计不计费、按什么价，文档没写；稳妥起见按音频输出的单价算进去
        usage = {"engine": "gemini-api", "model": model, "seconds_audio": round(secs, 2),
                 "seconds_wall": round(time.time() - t0, 1), "finish_reason": d.get("status") or d.get("state"),
                 "prompt_tokens": tin, "audio_tokens_reported": tout, "audio_tokens_estimated": est_audio,
                 "thought_tokens": th, "usage_raw": _usage_part(d), "audio_mime": a.get("mime_type") or a.get("mimeType"),
                 "cost_usd": round(gemini_cost(model, tin or len(text), (tout or est_audio) + (th or 0)), 5)}
        return wav, usage


# ------------------------------------------------------------------ MiMo


class MiMo:
    def __init__(self):
        state = keys.load_local_env()            # 读被拒绝时抛 keys.KeyReadDenied
        if not all(state.values()):
            raise TTSError(f"MiMo 变量不全：{state}")
        self.url = keys.mimo_chat_url()

    def synthesize(self, text, model=MIMO_BUILTIN, voice=None, style=None, design=None,
                   clone_ref=None, timeout=300, retries=3):
        """返回 (WAV 字节, 用量字典)。
        内置音色：voice=冰糖 等，style 放 user 消息；
        声音设计：design=音色描述（user 消息），不传 voice；
        声音复刻：clone_ref=参考音频路径（wav/mp3），style 可选。"""
        messages = []
        audio = {"format": "wav"}
        if model == MIMO_DESIGN:
            if not design:
                raise TTSError("声音设计模型必须给音色描述（design）")
            messages.append({"role": "user", "content": design})
            audio["optimize_text_preview"] = False
        elif model == MIMO_CLONE:
            if not clone_ref:
                raise TTSError("声音复刻模型必须给参考音频（clone_ref）")
            raw = open(clone_ref, "rb").read()
            mime = "audio/mpeg" if str(clone_ref).lower().endswith(".mp3") else "audio/wav"
            audio["voice"] = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
            messages.append({"role": "user", "content": style or ""})
        else:
            if style:
                messages.append({"role": "user", "content": style})
            if voice:
                audio["voice"] = voice
        messages.append({"role": "assistant", "content": text})
        body = {"model": model, "messages": messages, "audio": audio}
        key = os.environ.get("MIMO_API_KEY", "")
        last = ""
        for i in range(retries):
            t0 = time.time()
            try:
                r = requests.post(self.url, json=body, timeout=timeout,
                                  headers={"Authorization": f"Bearer {key}",
                                           "Content-Type": "application/json"})
            except requests.RequestException as e:
                last = keys.hide(f"{type(e).__name__}: {str(e)[:200]}")
                if i < retries - 1:
                    time.sleep(15 * (i + 1))
                    continue
                raise TTSError(last) from None
            if r.status_code in (429, 500, 502, 503, 504) and i < retries - 1:
                last = keys.hide(f"MiMo HTTP {r.status_code}：{r.text[:300]}")
                print(f"      MiMo 忙（HTTP {r.status_code}），{20 * (i + 1)} 秒后重试", flush=True)
                time.sleep(20 * (i + 1))
                continue
            if r.status_code != 200:
                raise TTSError(keys.hide(f"MiMo HTTP {r.status_code}：{r.text[:500]}"))
            d = r.json()
            ch = (d.get("choices") or [{}])[0]
            finish = ch.get("finish_reason")
            data = ((ch.get("message") or {}).get("audio") or {}).get("data")
            if not data:
                raise TTSError(keys.hide(f"MiMo 返回里没有音频（finish_reason={finish}）"))
            wav = as_wav(base64.b64decode(data))
            u = d.get("usage") or {}
            return wav, {"engine": "mimo", "model": model, "seconds_audio": round(wav_seconds(wav), 2),
                         "seconds_wall": round(time.time() - t0, 1), "finish_reason": finish,
                         "prompt_tokens": u.get("prompt_tokens"),
                         "completion_tokens": u.get("completion_tokens"), "cost_usd": 0.0}
        raise TTSError(last or "MiMo 请求失败")


def main(argv=None):
    keys.install_excepthook()
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] not in ("gemini-voices", "gemini-prebuilt", "gemini-api-voices"):
        print(__doc__)
        return 1
    if argv[0] == "gemini-api-voices":          # 主账号项目里自造的声音（不计费）
        for v in GeminiAPI().list_voices(types=["prompted"]):
            print(_get(v, "id", "name"), "|", _get(v, "display_name", "displayName"), "|",
                  _get(v, "language_code", "languageCode"), "|", _get(v, "gender"), "|", _get(v, "model"))
        return 0
    g = Gemini()
    if argv[0] == "gemini-voices":
        for v in g.list_voices(types=["prompted", "replicated"]):
            print(_get(v, "id"), "|", _get(v, "display_name", "displayName"), "|",
                  _get(v, "language_code", "languageCode"), "|", _get(v, "gender"))
    else:
        q = argv[1] if len(argv) > 1 else None
        for v in g.list_voices(types=["prebuilt"], search=q):
            print(json.dumps({k: v.get(k) for k in ("id", "gender", "language_code", "persona",
                                                    "description")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
