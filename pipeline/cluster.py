#!/usr/bin/env python3
"""第 3 步 归并：把同一件事的多篇报道（含中英文）合成一个"事件"，打热度，找相关事件和中外对照。

做法
  1. 向量：用本机缓存的多语种句向量模型 sentence-transformers/LaBSE（离线加载）给"标题＋摘要前 300 字"编码。
     LaBSE 把不同语言、意思相近的句子映射到相近的向量，所以中文稿和英文稿可以直接比。
  2. 专名：从标题里抽"专名"——公司、产品、人名（中英文写法归一，如 英伟达→nvidia、奥尔特曼→altman）、
     带数字的型号（GPT-6、Qwen4）、金额（$6.3B 与"63 亿美元"都记成 $6.3b）、百分比。
  3. 合并：凝聚式聚类（每次合并最像的两组，直到最像的一对也不够像）。两组之间的"调整后相似度"
       = 两组质心的余弦相似度 ＋ 专名加分 − 专名减分
       专名加分：共有 ≥2 个少见专名（或 1 少见＋1 枢纽专名）+0.20；共有 1 个少见专名 +0.16；
                只共有"枢纽"专名（天天出现的大公司、大产品，如 openai、claude、google，名单见 COMMON）：2 个 +0.14，1 个 +0.08；
                金额、百分比单独重合按枢纽专名算，和别的专名一起重合才算少见；
       专名减分：两组都有专名、却一个也不重合 −0.05；
     调整后相似度 ≥ 0.78 才合并。等价于：
       没有专名可比时，余弦要 ≥ 0.78；只共有 1 个枢纽专名，余弦 ≥ 0.70；共有 2 个枢纽专名，余弦 ≥ 0.64；
       共有 1 个少见专名，余弦 ≥ 0.62；共有 2 个以上，余弦 ≥ 0.58；专名完全对不上，余弦要 ≥ 0.83。
     GitHub 新星榜是快照、不是新闻，只按余弦合并，不吃专名加分。
     为什么是这些数：10-31 这批 549 条的实测（见 README_获取.md）——LaBSE 对同一事件的中英文稿余弦多在 0.60–0.82，
     而同一天、同一领域但不同事件的稿子也常落在 0.60–0.80（如"茅台三季报"对"摩尔线程三季报点评" 0.77，
     "摩尔线程三季报"对"长鑫签长期供货协议" 0.80），
     单看余弦分不开；加上"有没有共同专名"后，误并明显减少，跨语种的真同一事件（Apple 智能入华 0.70、
     Cursor 插件被投毒 0.69–0.71、英特尔暴跌 0.69）都能并上。阈值是凭这批样本定的，需要人工标注再校准。
  4. 汇总稿（TLDR 每期、WSJ Market Talk 等）不参与合并，只在质心余弦 ≥ 0.62 时记为该事件的"提及"。
  5. 相关事件：未合并的两个事件，质心余弦 ≥ 0.55，记为"相关"。
     中外对照：一边主体是中国公司、另一边是国际公司，标题里有共同的具体主题（模型发布、价格套餐、融资上市、算力芯片、
     政策监管、机器人驾驶、安全风险、财报股市），两边都是像样的 AI 事件且至少一边有 ≥2 个独立来源，质心余弦 ≥ 0.35，
     标为"可能的中外对照"。主体按标题里出现的公司判断（标题里没有公司时才看摘要）。

热度公式（写在 heat() 里）
  heat = R × ( Σ_独立来源 w(层级) × 0.5^(距今小时 / 36)  ＋  E )
  - 独立来源：同一运营方只算一次（如 NVIDIA 博客和 NVIDIA 新闻稿算一个；同一媒体多篇算一个）；
    网址相同被并掉的来源也算（如 HN 帖子和 TechCrunch 原文是同一个链接）。取该来源最近一次出现的时间和最高层级。
  - w(层级)：国际一手／中国一手 1.5，国际媒体／中文媒体／语言教育媒体 1.0，社区信号 0.8，二手整合 0.6，
    社交信号 0.4（社交信号最多计 4 个，免得 X 上的热议压过正式报道）。
  - 时效衰减：半衰期 36 小时（窗口约 45 小时，用 24 小时会把前天下午的大事压得太低）。
  - E（互动加分，各项取事件内最大值，合计封顶 1.2，约等于多 1 个媒体来源）：
    0.4·log2(1+HN 分数/100) ＋ 0.3·log2(1+HF 论文点赞/100) ＋ 0.3·log2(1+GitHub 星数/1000) ＋ 0.3·log2(1+Reddit Activity/1000)。
  - R（相关度折扣）：事件以 AI 或 AI×语言教育为主 1.0；只是科技商业 0.6。落实"以 AI 为主，科技商业为辅"。

运行：~/.venvs/frontier-daily/bin/python pipeline/cluster.py --day 2026-10-31
输入：测试版/<day>/01_获取/prefilter.jsonl
输出：测试版/<day>/02_选题/candidates.json（热度前 60 个事件，字段齐全）、candidates.md（给人看的表格）
"""

import argparse
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np

from fd_common import LAYER_LABELS, LAYER_PRIORITY, iso, md_escape, parse_iso, read_jsonl, run_dir, truncate

MODEL_NAME = "sentence-transformers/LaBSE"

PARAMS = {
    "merge": 0.78,         # 调整后相似度合并线
    "bonus_rare2": 0.20,   # 共有 ≥2 个少见专名，或 1 个少见＋1 个枢纽专名 → 余弦 ≥ 0.58 即可合并
    "bonus_rare1": 0.16,   # 共有 1 个少见专名 → 余弦 ≥ 0.62
    "bonus_common2": 0.14, # 只共有 ≥2 个"枢纽"专名（如 三星＋OpenAI 同时出现）→ 余弦 ≥ 0.64
    "bonus_common1": 0.08, # 只共有 1 个"枢纽"专名 → 余弦 ≥ 0.70
    "penalty": 0.05,       # 都有专名但完全不重合
    "core_share": 0.25,    # 一组的"核心专名"= 至少出现在 25% 成员标题里的专名
    "related_low": 0.55,   # 相关事件下限（质心余弦）
    "contrast_low": 0.35,  # 中外对照下限（质心余弦）：主体不同的两件事本来就不会太像，主要靠"同一主题"配对
    "mention": 0.62,       # 汇总稿记为"提及"的下限（质心余弦）
    "half_life_h": 36.0,
    "social_cap": 4,
    "engagement_cap": 1.2, # 互动加分封顶，约等于 1 个媒体来源
    "top_n": 60,
}

LAYER_WEIGHT = {"primary_intl": 1.5, "primary_cn": 1.5, "media_intl": 1.0, "media_cn": 1.0, "lang_edu": 1.0,
                "community": 0.8, "aggregator": 0.6, "social": 0.4}
REPORT_LAYERS = {"primary_intl", "primary_cn", "media_intl", "media_cn", "aggregator", "lang_edu"}  # "报道"层，不含社区和社交
RELEVANCE_FACTOR = {"ai": 1.0, "lang_edu": 1.0, "tech_business": 0.6, "other": 0.5}


# ───────────────────────── 专名抽取 ─────────────────────────

CANON_GROUPS = [
    ("openai", ["OpenAI"]), ("chatgpt", ["ChatGPT"]), ("altman", ["Altman", "奥特曼", "奥尔特曼"]),
    ("anthropic", ["Anthropic"]), ("claude", ["Claude"]), ("claude-code", ["Claude Code"]),
    ("google", ["Google", "谷歌", "Alphabet"]), ("gemini", ["Gemini"]), ("deepmind", ["DeepMind"]),
    ("microsoft", ["Microsoft", "微软"]), ("meta", ["Meta"]), ("zuckerberg", ["Zuckerberg", "扎克伯格"]),
    ("apple", ["Apple", "苹果"]), ("apple-intelligence", ["Apple Intelligence", "Apple 智能", "Apple智能"]),
    ("amazon", ["Amazon", "亚马逊", "AWS"]), ("nvidia", ["Nvidia", "NVIDIA", "英伟达"]),
    ("jensen-huang", ["Jensen Huang", "黄仁勋"]), ("intel", ["Intel", "英特尔"]), ("amd", ["AMD"]),
    ("tsmc", ["TSMC", "台积电"]), ("samsung", ["Samsung", "三星"]), ("sk-hynix", ["SK Hynix", "海力士"]),
    ("micron", ["Micron", "美光"]), ("asml", ["ASML", "阿斯麦"]), ("qualcomm", ["Qualcomm", "高通"]),
    ("broadcom", ["Broadcom", "博通"]), ("arm", ["Arm"]), ("softbank", ["SoftBank", "软银"]),
    ("oracle", ["Oracle", "甲骨文"]), ("musk", ["Musk", "马斯克"]), ("tesla", ["Tesla", "特斯拉"]),
    ("spacex", ["SpaceX"]), ("xai", ["xAI", "SpaceXAI"]), ("grok", ["Grok"]), ("binance", ["Binance", "币安"]),
    ("polymarket", ["Polymarket"]), ("cursor", ["Cursor"]), ("mistral", ["Mistral"]), ("perplexity", ["Perplexity"]),
    ("hugging-face", ["Hugging Face", "HuggingFace"]), ("reddit", ["Reddit"]), ("north-korea", ["North Korea", "朝鲜"]),
    ("trump", ["Trump", "特朗普"]), ("deepseek", ["DeepSeek", "深度求索"]), ("qwen", ["Qwen", "千问", "通义"]),
    ("alibaba", ["Alibaba", "阿里巴巴", "阿里"]), ("tencent", ["Tencent", "腾讯"]), ("bytedance", ["ByteDance", "字节跳动", "字节"]),
    ("doubao", ["Doubao", "豆包"]), ("baidu", ["Baidu", "百度"]), ("huawei", ["Huawei", "华为"]), ("xiaomi", ["Xiaomi", "小米"]),
    ("kimi", ["Kimi", "月之暗面", "Moonshot"]), ("zhipu", ["Zhipu", "智谱", "GLM"]), ("minimax", ["MiniMax", "稀宇"]),
    ("stepfun", ["StepFun", "阶跃"]), ("hunyuan", ["Hunyuan", "混元"]), ("cambricon", ["Cambricon", "寒武纪"]),
    ("moore-threads", ["Moore Threads", "摩尔线程"]), ("smic", ["SMIC", "中芯国际"]), ("unitree", ["Unitree", "宇树"]),
    ("meituan", ["Meituan", "美团"]), ("kuaishou", ["Kuaishou", "快手"]), ("kling", ["Kling", "可灵"]),
    ("iphone", ["iPhone"]), ("ipad", ["iPad"]), ("dram", ["DRAM"]), ("hbm", ["HBM"]), ("codex", ["Codex"]),
    ("copilot", ["Copilot"]), ("workbuddy", ["WorkBuddy"]), ("yuanbao", ["元宝"]), ("chery", ["奇瑞", "Chery"]),
    ("samsung", ["三星电子"]), ("instacart", ["Instacart"]), ("doordash", ["DoorDash"]), ("nscale", ["Nscale"]),
    # 中国科技公司补充：标题里有这些名字，才能触发"专名对不上就减分"，免得同领域不同公司的中文稿被并在一起
    ("cxmt", ["长鑫", "CXMT"]), ("ymtc", ["长江存储", "YMTC"]), ("hygon", ["海光"]), ("biren", ["壁仞"]), ("metax", ["沐曦"]),
    ("enflame", ["燧原"]), ("loongson", ["龙芯"]), ("hua-hong", ["华虹"]), ("agibot", ["智元", "AgiBot"]), ("ubtech", ["优必选", "UBTech"]),
    ("li-auto", ["理想汽车", "Li Auto"]), ("xpeng", ["小鹏", "XPeng"]), ("nio", ["蔚来"]), ("byd", ["比亚迪", "BYD"]),
    ("catl", ["宁德时代", "CATL"]), ("jd", ["京东"]), ("pdd", ["拼多多", "Temu"]), ("netease", ["网易", "NetEase"]),
    ("lenovo", ["联想", "Lenovo"]), ("honor", ["荣耀"]), ("oppo", ["OPPO"]), ("vivo", ["vivo"]), ("dji", ["大疆", "DJI"]),
    ("sensetime", ["商汤", "SenseTime"]), ("iflytek", ["讯飞", "iFlytek"]), ("baichuan", ["百川"]), ("01ai", ["零一万物"]),
    ("modelbest", ["面壁"]), ("baai", ["智源", "BAAI"]), ("ant-group", ["蚂蚁"]), ("seres", ["赛力斯"]), ("harmonyos", ["鸿蒙"]),
    ("lingguang", ["灵光"]), ("trae", ["TRAE", "Trae"]), ("kling", ["可灵"]),
]
ALIAS = {}
ZH_ALIASES = []
for key, names in CANON_GROUPS:
    for name in names:
        ALIAS[name.lower()] = key
        if re.search(r"[^\x00-\x7f]", name):
            ZH_ALIASES.append((name, key))
ZH_ALIASES.sort(key=lambda x: -len(x[0]))
MULTIWORD = sorted([n for _, ns in CANON_GROUPS for n in ns if " " in n and not re.search(r"[^\x00-\x7f]", n)], key=len, reverse=True)

GENERIC = {
    "ai", "a.i.", "ceo", "cfo", "cto", "us", "u.s.", "u.s", "uk", "eu", "china", "chinese", "american", "america",
    "ipo", "llm", "llms", "gpu", "gpus", "api", "app", "apps", "pc", "tv", "inc", "ltd", "co", "new", "the", "q1", "q2",
    "q3", "q4", "ok", "faq", "ama", "hn", "show", "ask", "tell", "via", "news", "it", "id", "ui", "ux", "vr", "ar", "xr",
    "os", "sdk", "json", "html", "agi", "gen", "pro", "max", "mini", "plus", "ultra", "lite", "beta", "v1", "v2",
    "github", "repo", "opinion", "exclusive", "sources", "report", "update", "week", "daily", "today", "now",
    "s&p", "sp", "nasdaq", "dow", "wall", "street", "big", "tech", "market", "markets", "stock", "stocks",
    "intelligence", "vs", "one", "two", "three", "first", "how", "why", "what", "when", "who", "this", "that", "here",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "january", "february", "march",
    "april", "may", "june", "july", "august", "september", "october", "november", "december", "halloween",
    "ft", "wsj", "nyt", "cnbc", "bloomberg", "reuters", "axios", "says", "reportedly",   # 媒体名多是"据某某报道"的出处
    "rl", "lora", "fp8", "fp4", "nvfp4", "mxfp4", "gguf", "day-0", "day0", "moe", "sft", "dpo", "sota", "code", "index",
    "cli", "ide", "mcp", "rag", "tpu", "npu", "hbm", "ram", "cpu", "soc", "oss",                       # 技术通用词
}
_TITLECASE_WORD = re.compile(r"\b[A-Z][a-z]+\b")
_WORD = re.compile(r"\b[A-Za-z][A-Za-z']+\b")
_ASCII_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[.\-][A-Za-z0-9]+)*")
_MONEY_EN = re.compile(r"\$\s?(\d+(?:\.\d+)?)\s?(trillion|tn|t|billion|bn|b|million|mn|m)\b", re.I)
_MONEY_ZH = re.compile(r"(\d+(?:\.\d+)?)\s?(万亿|亿)\s?(美元|元|人民币)?")
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s?%")


def _fmt(x: float) -> str:
    return f"{x:.3g}"


def specific_tokens(title: str) -> set:
    """标题里的"专名"集合（小写、归一）。"""
    t = re.sub(r"\s*\(via @[^)]*\)\s*$", "", title or "")
    toks = set()
    for name, key in ZH_ALIASES:
        if name in t:
            toks.add(key)
    for name in MULTIWORD:
        if re.search(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", t):
            toks.add(ALIAS[name.lower()])
    # 金额与百分比
    for m in _MONEY_EN.finditer(t):
        x, unit = float(m.group(1)), m.group(2).lower()
        if unit in ("trillion", "tn", "t"):
            toks.add("$" + _fmt(x) + "t")
        elif unit in ("billion", "bn", "b"):
            toks.add("$" + _fmt(x) + "b")
    for m in _MONEY_ZH.finditer(t):
        x, unit, cur = float(m.group(1)), m.group(2), m.group(3) or ""
        sym = "$" if cur == "美元" else "¥"
        toks.add(sym + (_fmt(x) + "t" if unit == "万亿" else _fmt(x / 10) + "b"))
    for m in _PCT.finditer(t):
        toks.add(f"{int(float(m.group(1)))}%")
    for m in re.finditer(r"(?<![A-Za-z])([A-Z][A-Za-z]{1,15})[\s\-]?(\d{1,2}(?:\.\d)?)(?![\d%])", t):
        if m.group(1).lower() not in GENERIC:
            toks.add(m.group(1).lower() + m.group(2))                # Gemini 4 → gemini4，Qwen4 → qwen4
    # 英文专名：带数字的型号、内部大写（OpenAI、iPhone）、全大写缩写；句子式标题里句中大写词也算
    words = _WORD.findall(t)
    long_words = [w for w in words if len(w) > 3]
    title_case = bool(long_words) and sum(w[0].isupper() for w in long_words) / len(long_words) >= 0.6
    for m in _ASCII_TOKEN.finditer(t):
        w = m.group(0)
        lw = w.lower().strip(".-")
        before = t[: m.start()].rstrip(" \"'“‘(（")
        is_first = (not before) or before[-1] in ":：—–-.!?。！？|｜"     # 句首词不算专名
        if lw in GENERIC or len(lw) < 2:
            continue
        if re.fullmatch(r"(19|20)\d\d", lw):
            continue
        keep = False
        if any(c.isdigit() for c in w) and any(c.isalpha() for c in w):
            keep = True                                            # GPT-6、Qwen4、B200
        elif re.search(r"[a-z][A-Z]", w) or re.fullmatch(r"[A-Z]{2,6}s?", w):
            keep = True                                            # OpenAI、iPhone、DRAM
        elif lw in ALIAS:
            keep = True
        elif w[0].isupper() and not title_case and not is_first and len(w) > 2:
            keep = True                                            # 句子式标题里的句中大写词：Binance、Cursor
        if keep:
            toks.add(ALIAS.get(lw, lw))
    return {x for x in toks if x not in GENERIC}


# ───────────────────────── 编码 ─────────────────────────

_BOILER_ZH = [
    re.compile(r"^本文来自微信公众号[:：][^，,。]{0,30}[，,]?\s*(作者[:：][^，,。\s]{0,20}[，,。]?)?\s*"),
    re.compile(r"^IT之家\s*\d+\s*月\s*\d+\s*日消息[，,]\s*"),
    re.compile(r"^(36氪获悉|据\S{2,8}报道)[，,]\s*"),
]


def embed_text(it: dict) -> str:
    title = re.sub(r"\s*\(via @[^)]*\)\s*$", "", it["title"] or "")
    s = it.get("summary") or ""
    for pat in _BOILER_ZH:
        s = pat.sub("", s)
    return (title + " " + s[:300]).strip()


def encode(texts: list) -> np.ndarray:
    from sentence_transformers import SentenceTransformer

    import torch

    device = "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu"
    model = SentenceTransformer(MODEL_NAME, device=device)
    return model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False).astype(np.float32)


# ───────────────────────── 聚类 ─────────────────────────

def core_tokens(counter: Counter, size: int) -> set:
    need = max(1, math.ceil(PARAMS["core_share"] * size))
    return {t for t, c in counter.items() if c >= need}


# "枢纽"专名：几乎每天都出现在许多互不相干的新闻里的大公司、大产品、大人物。两条稿子只共有这些名字，
# 不足以说明是同一件事，所以加分少。没列进来的专名（如 binance、intel、cursor、$6.3b、gemini4）算"少见"，加分多。
# 不用"出现次数"自动判断：大事件本身会被很多家报道，按次数算会把真正的大事件压低。
COMMON = {
    "openai", "chatgpt", "altman", "anthropic", "claude", "claude-code", "google", "gemini", "deepmind", "microsoft",
    "copilot", "meta", "zuckerberg", "apple", "iphone", "amazon", "nvidia", "musk", "tesla", "xai", "trump", "samsung",
    "alibaba", "qwen", "tencent", "bytedance", "doubao", "baidu", "huawei", "xiaomi", "deepseek", "codex", "vllm",
    "sglang", "hugging-face",
}
_NUMERIC = re.compile(r"^[$¥]|%$")


def token_adjust(a: set, b: set) -> float:
    """专名加减分：少见专名（如 $6.3b、apple-intelligence、cursor）比常见专名（openai、claude）更能说明是同一件事。"""
    if not a or not b:
        return 0.0
    shared = a & b
    if not shared:
        return -PARAMS["penalty"]
    words = {t for t in shared if not _NUMERIC.match(t)}
    nums = shared - words
    rare = len(words - COMMON)
    common = len(words & COMMON)
    # 金额、百分比单独出现时可能只是巧合（如 OpenAI 的 $30B 目标和 Baseten 的 $30B 估值），按枢纽专名算；
    # 和别的专名一起出现时（如 google＋$500b）才算少见专名
    if nums:
        if words:
            rare += len(nums)
        else:
            common += len(nums)
    if rare >= 2 or (rare == 1 and common >= 1):
        return PARAMS["bonus_rare2"]
    if rare == 1:
        return PARAMS["bonus_rare1"]
    return PARAMS["bonus_common2"] if common >= 2 else PARAMS["bonus_common1"]


def agglomerate(E: np.ndarray, toks: list) -> list:
    """质心凝聚聚类。返回成员下标列表的列表。"""
    n = len(E)
    sums = E.copy()
    sizes = np.ones(n)
    tok_counts = [Counter(t) for t in toks]
    cores = [set(t) for t in toks]
    members = [[i] for i in range(n)]
    active = np.ones(n, dtype=bool)

    cent = E.copy()
    S = cent @ cent.T
    for i in range(n):
        for j in range(i + 1, n):
            adj = token_adjust(cores[i], cores[j])
            if adj:
                S[i, j] += adj
                S[j, i] += adj
    np.fill_diagonal(S, -9)
    thr = PARAMS["merge"]
    while True:
        k = int(np.argmax(S))
        i, j = divmod(k, n)
        if S[i, j] < thr:
            break
        # 把 j 并进 i
        sums[i] += sums[j]
        sizes[i] += sizes[j]
        members[i].extend(members[j])
        tok_counts[i].update(tok_counts[j])
        cores[i] = core_tokens(tok_counts[i], int(sizes[i]))
        active[j] = False
        S[j, :] = -9
        S[:, j] = -9
        c = sums[i] / np.linalg.norm(sums[i])
        cent[i] = c
        row = cent @ c
        for m in np.where(active)[0]:
            if m == i:
                continue
            row[m] += token_adjust(cores[i], cores[m])
        row[~active] = -9
        row[i] = -9
        S[i, :] = row
        S[:, i] = row
    return [members[i] for i in np.where(active)[0]]


# ───────────────────────── 事件属性 ─────────────────────────

def participants(ev_items: list) -> dict:
    """独立来源：运营方 → {layer, time, region, source_names}。网址相同被并掉的来源也算。"""
    parts = {}

    def add(op, layer, published, region, name):
        p = parts.get(op)
        t = parse_iso(published)
        if p is None:
            parts[op] = {"layer": layer, "time": t, "region": region, "names": {name}}
        else:
            if LAYER_WEIGHT.get(layer, 0) > LAYER_WEIGHT.get(p["layer"], 0):
                p["layer"] = layer
            p["time"] = max(p["time"], t)
            p["names"].add(name)

    for it in ev_items:
        ex = it["extra"]
        add(ex.get("operator") or it["source_id"], it["layer"], it["published"], ex.get("region"), it["source_name"])
        for d in ex.get("dup_sources") or []:
            add(d.get("operator") or d["source_id"], d["layer"], d["published"], d.get("region"), d["source_name"])
    return parts


def heat(ev_items: list, parts: dict, relevance: str, ref: datetime) -> tuple:
    """heat = R × ( Σ_独立来源 w(层级)·0.5^(距今小时/36) ＋ E )，见文件头说明。"""
    hl = PARAMS["half_life_h"]
    s_term = 0.0
    social = sorted((p for p in parts.values() if p["layer"] == "social"), key=lambda p: p["time"], reverse=True)
    counted = [p for p in parts.values() if p["layer"] != "social"] + social[: PARAMS["social_cap"]]
    for p in counted:
        age_h = max(0.0, (ref - p["time"]).total_seconds() / 3600)
        s_term += LAYER_WEIGHT.get(p["layer"], 0.5) * 0.5 ** (age_h / hl)

    def mx(key):
        vals = [it["engagement"].get(key) or 0 for it in ev_items]
        vals += [(d.get("engagement") or {}).get(key) or 0 for it in ev_items for d in it["extra"].get("dup_sources") or []]
        return max([0] + [v for v in vals if isinstance(v, (int, float))])

    eng = {"hn_score": mx("hn_score"), "hf_upvotes": mx("hf_upvotes"), "gh_stars": mx("gh_stars"),
           "reddit_activity": mx("reddit_activity")}
    e_term = min(PARAMS["engagement_cap"],
                 0.4 * math.log2(1 + eng["hn_score"] / 100) + 0.3 * math.log2(1 + eng["hf_upvotes"] / 100)
                 + 0.3 * math.log2(1 + eng["gh_stars"] / 1000) + 0.3 * math.log2(1 + eng["reddit_activity"] / 1000))
    r = RELEVANCE_FACTOR.get(relevance, 0.5)
    return round(r * (s_term + e_term), 3), {"sources_term": round(s_term, 3), "engagement_term": round(e_term, 3),
                                            "relevance_factor": r}, {k: v for k, v in eng.items() if v}


TITLE_PRIORITY = {"media_intl": 0, "media_cn": 0, "lang_edu": 0, "primary_intl": 1, "primary_cn": 1,
                  "aggregator": 2, "community": 3, "social": 4}


def pick_title(ev_items: list, sims, lang: str) -> str:
    """代表标题：媒体标题通常最能说清"发生了什么"，其次官方标题；同一层里取最贴近事件质心的一条。"""
    cands = [(it, float(s)) for it, s in zip(ev_items, sims) if it["lang"] == lang]
    if not cands:
        return ""

    def key(x):
        it, s = x
        bad_len = 0 if 8 <= len(it["title"]) <= (80 if lang == "zh" else 160) else 1
        return (TITLE_PRIORITY.get(it["layer"], 9), bad_len, -s)

    return sorted(cands, key=key)[0][0]["title"]


def event_profile(ev_items: list) -> dict:
    rel = Counter(it["pf"]["relevance"] for it in ev_items)
    relevance = "ai" if (rel["ai"] + rel["lang_edu"]) >= rel["tech_business"] else "tech_business"
    if rel["lang_edu"] and rel["lang_edu"] >= 0.3 * len(ev_items):
        relevance = "lang_edu"
    topics = Counter(t for it in ev_items for t in it["pf"]["topics"])
    need = max(1, math.ceil(0.3 * len(ev_items)))
    top_topics = [t for t, c in topics.most_common() if c >= need][:4]
    t_topics = Counter(t for it in ev_items for t in it["pf"].get("topics_title", []))
    title_topics = [t for t, c in t_topics.most_common() if c >= max(1, math.ceil(0.2 * len(ev_items)))][:4]
    reg = Counter()
    titled = [it for it in ev_items if it["pf"].get("subject_region_title", "none") != "none"]
    use_title = bool(titled)
    for it in (titled or ev_items):
        sr = it["pf"]["subject_region_title"] if use_title else it["pf"]["subject_region"]
        if sr in ("cn", "intl"):
            reg[sr] += 1
        elif sr == "mixed":
            reg["cn"] += 0.5
            reg["intl"] += 0.5
    total = reg["cn"] + reg["intl"]
    if total == 0:
        subject = "none"
    elif reg["cn"] >= 0.65 * total:
        subject = "cn"
    elif reg["intl"] >= 0.65 * total:
        subject = "intl"
    else:
        subject = "mixed"
    return {"relevance": relevance, "topics": top_topics, "title_topics": title_topics, "subject_region": subject}


# ───────────────────────── 主程序 ─────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--top", type=int, default=PARAMS["top_n"])
    args = ap.parse_args()
    t0 = time.time()
    base = run_dir(args.day)
    rows = read_jsonl(base / "01_获取" / "prefilter.jsonl")
    kept = [r for r in rows if r["pf"]["keep"]]
    items = [r for r in kept if not r["pf"]["roundup"]]
    roundups = [r for r in kept if r["pf"]["roundup"]]
    print(f"粗筛保留 {len(kept)} 条：参与归并 {len(items)}，汇总稿 {len(roundups)}；编码中……", flush=True)

    E = encode([embed_text(it) for it in items + roundups])
    E_items, E_round = E[: len(items)], E[len(items):]
    toks = [specific_tokens(it["title"]) for it in items]
    # GitHub 新星榜这类快照条目不是新闻事件，只按余弦合并，不吃专名加分
    toks_for_merge = [set() if it["extra"].get("window_exempt") else ts for it, ts in zip(items, toks)]
    groups = agglomerate(E_items, toks_for_merge)
    ref = max(parse_iso(it["published"]) for it in items)
    ref = min(ref, datetime.now(timezone.utc))

    events = []
    for g in groups:
        ev_items = [items[i] for i in g]
        cent = E_items[g].sum(0)
        cent /= np.linalg.norm(cent)
        prof = event_profile(ev_items)
        parts = participants(ev_items)
        h, detail, eng = heat(ev_items, parts, prof["relevance"], ref)
        sims = E_items[g] @ cent  # 各成员与事件质心的余弦
        order = sorted(range(len(g)), key=lambda k: (LAYER_PRIORITY.get(ev_items[k]["layer"], 9), -sims[k]))
        layers = Counter(p["layer"] for p in parts.values())
        langs = sorted({it["lang"] for it in ev_items} | {d["lang"] for it in ev_items for d in it["extra"].get("dup_sources") or []})
        rep_regions = {p["region"] for p in parts.values() if p["layer"] in REPORT_LAYERS}
        any_regions = {p["region"] for p in parts.values()}
        tok_counter = Counter(t for i in g for t in toks[i])
        events.append({
            "_cent": cent, "_g": g,
            "heat": h, "heat_detail": detail,
            "title_zh": pick_title(ev_items, sims, "zh"), "title_en": pick_title(ev_items, sims, "en"),
            "n_items": len(ev_items),
            "n_sources": len({it["source_id"] for it in ev_items} | {d["source_id"] for it in ev_items for d in it["extra"].get("dup_sources") or []}),
            "independent_sources": len(parts),
            "layers": {LAYER_LABELS[k]: v for k, v in layers.most_common()},
            "langs": langs,
            "regions": sorted(any_regions),
            "cn_and_intl": rep_regions >= {"cn", "intl"},
            "cn_and_intl_any": any_regions >= {"cn", "intl"},
            "subject_region": prof["subject_region"],
            "relevance": prof["relevance"],
            "topics": prof["topics"],
            "title_topics": prof["title_topics"],
            "key_terms": [t for t, _ in tok_counter.most_common(6)],
            "first_seen": min(it["published"] for it in ev_items),
            "last_seen": max(it["published"] for it in ev_items),
            "engagement": eng,
            "social_only": all(it["layer"] == "social" for it in ev_items),
            "participants": sorted({n for p in parts.values() for n in p["names"]}),
            "members": [{
                "id": ev_items[k]["id"], "title": ev_items[k]["title"], "url": ev_items[k]["url"],
                "source_id": ev_items[k]["source_id"], "source_name": ev_items[k]["source_name"],
                "layer": ev_items[k]["layer"], "lang": ev_items[k]["lang"], "region": ev_items[k]["extra"].get("region"),
                "published": ev_items[k]["published"], "summary": ev_items[k]["summary"],
                "engagement": ev_items[k]["engagement"], "sim_to_centroid": round(float(sims[k]), 3),
                **({"dup_sources": [{"source_name": d["source_name"], "layer": d["layer"], "title": d["title"]}
                                    for d in ev_items[k]["extra"]["dup_sources"]]} if ev_items[k]["extra"].get("dup_sources") else {}),
                **({"x_authors": ev_items[k]["extra"]["x_authors"]} if ev_items[k]["extra"].get("x_authors") else {}),
            } for k in order],
            "mentions": [],
        })

    # 汇总稿 → 提及
    if events and len(roundups):
        C = np.stack([e["_cent"] for e in events])
        for r, v in zip(roundups, E_round):
            sims = C @ v
            for k in np.where(sims >= PARAMS["mention"])[0]:
                events[k]["mentions"].append({"title": r["title"], "url": r["url"], "source_name": r["source_name"],
                                              "sim": round(float(sims[k]), 3)})

    events.sort(key=lambda e: -e["heat"])
    for rank, e in enumerate(events, 1):
        e["event_id"] = f"E{rank:03d}"
        e["rank"] = rank

    # 相关事件与中外对照
    C = np.stack([e["_cent"] for e in events])
    R = C @ C.T
    np.fill_diagonal(R, -1)

    def contrast_of(e, o):
        """可能的中外对照：主体一边是中国、一边是国际；有共同的具体主题；两边都是像样的 AI 事件。"""
        if {e["subject_region"], o["subject_region"]} != {"cn", "intl"}:
            return []
        if not (substantial(e) and substantial(o)):
            return []
        if max(e["independent_sources"], o["independent_sources"]) < 2:
            return []                       # 至少一边是多家报道的大事
        return sorted((set(e["title_topics"]) & set(o["title_topics"])) & CONTRAST_TOPICS)

    for i, e in enumerate(events):
        rel = []
        for j in np.argsort(-R[i])[:8]:
            s = float(R[i, j])
            if s < PARAMS["related_low"]:
                break
            o = events[j]
            ct = contrast_of(e, o)
            rel.append({"event_id": o["event_id"], "title": o["title_zh"] or o["title_en"], "sim": round(s, 3),
                        "cn_intl_contrast": bool(ct),
                        "shared_topics": sorted(set(e["topics"]) & set(o["topics"]))})
        e["related"] = rel[:4]
    # 中外对照另做一轮全表扫描：主体不同的两件事（如 OpenAI 融资缩水 vs DeepSeek 新一轮融资），句向量余弦往往只有
    # 0.35–0.6，低于"相关事件"线，所以主要靠"同一具体主题"配对，余弦只作下限（0.35）。
    # 排序分 = 0.5 × 余弦 ＋ 0.3 × 两边热度较小者：让两边都有分量的组合排前面；同一主题最多留 4 对，同一事件最多出现 3 次。
    cands = []
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            s = float(R[i, j])
            if s < PARAMS["contrast_low"]:
                continue
            ct = contrast_of(events[i], events[j])
            if ct:
                cands.append((0.5 * s + 0.3 * min(events[i]["heat"], events[j]["heat"]), s, i, j, ct))
    cands.sort(key=lambda x: -x[0])
    pairs, per_topic, per_event = [], Counter(), Counter()
    for score, s, i, j, ct in cands:
        topic = ct[0]
        if per_topic[topic] >= 4 or per_event[i] >= 3 or per_event[j] >= 3:
            continue
        per_topic[topic] += 1
        per_event[i] += 1
        per_event[j] += 1
        pairs.append((s, i, j, ct))

    top = events[: args.top]
    out_dir = base / "02_选题"
    out_dir.mkdir(parents=True, exist_ok=True)
    clean = lambda e: {k: v for k, v in e.items() if not k.startswith("_")}
    langedu = [e for e in events if e["relevance"] == "lang_edu" or "语言教育" in e["topics"]][:12]
    social_only = [e for e in events if e["social_only"]][:12]
    contrast_pairs = [{"sim": round(s, 3), "a": events[i]["event_id"], "a_title": events[i]["title_zh"] or events[i]["title_en"],
                       "a_subject": events[i]["subject_region"], "b": events[j]["event_id"],
                       "b_title": events[j]["title_zh"] or events[j]["title_en"], "b_subject": events[j]["subject_region"],
                       "shared_topics": t} for s, i, j, t in pairs[:20]]
    stats = {
        "day": args.day, "generated_at": iso(datetime.now(timezone.utc)), "ref_time": iso(ref),
        "model": MODEL_NAME, "params": PARAMS, "layer_weight": LAYER_WEIGHT, "relevance_factor": RELEVANCE_FACTOR,
        "heat_formula": "heat = R × ( Σ_独立来源 w(层级)·0.5^(距今小时/36) ＋ min(1.2, 0.4·log2(1+HN分数/100) "
                        "＋ 0.3·log2(1+HF点赞/100) ＋ 0.3·log2(1+GitHub星/1000) ＋ 0.3·log2(1+Reddit Activity/1000)) )",
        "n_kept": len(kept), "n_clustered": len(items), "n_roundups": len(roundups), "n_events": len(events),
        "n_events_multi_source": sum(e["independent_sources"] >= 2 for e in events),
        "n_events_cn_and_intl": sum(e["cn_and_intl"] for e in events),
        "n_events_cn_and_intl_any": sum(e["cn_and_intl_any"] for e in events),
        "n_events_cn_and_intl_top": sum(e["cn_and_intl"] for e in top),
        "n_contrast_pairs": len(pairs), "seconds": round(time.time() - t0, 1),
    }
    data = {"stats": stats, "events": [clean(e) for e in top],
            "lang_edu_column": [clean_brief(e) for e in langedu],
            "social_only": [clean_brief(e) for e in social_only],
            "cn_intl_contrast_pairs": contrast_pairs}
    (out_dir / "candidates.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    write_md(out_dir / "candidates.md", data, events)
    print(f"事件 {len(events)} 个（≥2 个独立来源 {stats['n_events_multi_source']}，中外都有报道 {stats['n_events_cn_and_intl']}）；"
          f"取前 {len(top)}；用时 {stats['seconds']} 秒")
    print(f"写入 {out_dir / 'candidates.json'}")


CONTRAST_TOPICS = {"模型发布", "价格套餐", "融资上市", "算力芯片", "政策监管", "机器人驾驶", "安全风险", "财报股市"}


def substantial(e: dict) -> bool:
    """够格做对照的事件：AI 相关，且（≥2 个独立来源，或有官方一手，或热度 ≥ 0.6 的正式报道）。"""
    if e["relevance"] not in ("ai", "lang_edu"):
        return False
    if e["independent_sources"] >= 2 or any(m["layer"] in ("primary_intl", "primary_cn") for m in e["members"]):
        return True
    return e["heat"] >= 0.6 and any(m["layer"] in REPORT_LAYERS for m in e["members"])


def clean_brief(e: dict) -> dict:
    return {"event_id": e["event_id"], "rank": e["rank"], "heat": e["heat"], "title_zh": e["title_zh"],
            "title_en": e["title_en"], "independent_sources": e["independent_sources"], "topics": e["topics"],
            "members": [{"title": m["title"], "url": m["url"], "source_name": m["source_name"], "published": m["published"]}
                        for m in e["members"][:5]]}


# ───────────────────────── 给人看的表格 ─────────────────────────

def _t(e: dict) -> str:
    zh, en = e["title_zh"], e["title_en"]
    if zh and en:
        return f"{md_escape(truncate(zh, 60))}<br>{md_escape(truncate(en, 110))}"
    return md_escape(truncate(zh or en, 110)) + ("<br>（无中文报道）" if not zh else "<br>（无英文报道）")


def write_md(path, data, all_events):
    st = data["stats"]
    p = st["params"]
    L = [f"# 选题候选 · {st['day']}", "",
         f"生成于 {st['generated_at']}；热度计算的基准时刻 {st['ref_time']}。"
         f"粗筛保留 {st['n_kept']} 条（参与归并 {st['n_clustered']}，汇总稿 {st['n_roundups']} 条只记提及），"
         f"归成 **{st['n_events']}** 个事件，其中 ≥2 个独立来源的 {st['n_events_multi_source']} 个，"
         f"中外都有报道的 {st['n_events_cn_and_intl']} 个（含社交、社区信号算 {st['n_events_cn_and_intl_any']} 个），"
         f"中外对照候选 {st['n_contrast_pairs']} 对。下表按热度取前 {len(data['events'])} 个。", "",
         f"- 向量模型：{st['model']}（离线）；合并线：调整后相似度 ≥ {p['merge']}（共有少见专名 1 个 +{p['bonus_rare1']}、2 个 +{p['bonus_rare2']}；"
         f"只共有常见专名 1 个 +{p['bonus_common1']}、2 个 +{p['bonus_common2']}；都有专名但不重合 −{p['penalty']}）；"
         f"相关事件：质心余弦 ≥ {p['related_low']}；汇总稿提及：≥ {p['mention']}。",
         f"- 热度：{st['heat_formula']}。R：AI／语言教育 1.0，科技商业 0.6。层级权重：一手 1.5，媒体 1.0，社区 0.8，二手 0.6，社交 0.4（最多计 {p['social_cap']} 个）；半衰期 {p['half_life_h']:.0f} 小时。",
         "- 列说明：独立来源 = 去重后的运营方数（同一媒体多篇、同一公司多个渠道只算一次）；中外 = ✓ 表示中国来源和国际来源都有正式报道；"
         "主体 = 按标题里的公司判断事件主角属中国（cn）、国际（intl）还是两边（mixed）。",
         "",
         "| # | 热度 | 代表标题（中／英） | 独立来源 | 层级 | 语言 | 中外 | 主体 | 主题 | 相关事件 |",
         "|---:|---:|---|---:|---|---|:---:|---|---|---|"]
    for e in data["events"]:
        layers = "、".join(f"{k}{v}" for k, v in e["layers"].items())
        rel = "；".join(f"{r['event_id']}{'（中外对照）' if r['cn_intl_contrast'] else ''}" for r in e["related"][:3])
        L.append(f"| {e['rank']} | {e['heat']:.2f} | {_t(e)} | {e['independent_sources']} | {layers} | {'/'.join(e['langs'])} | "
                 f"{'✓' if e['cn_and_intl'] else ''} | {e['subject_region']} | {'、'.join(e['topics'])} | {rel} |")

    L += ["", "## 中外对照候选（相似度中等、主体分属中国和国际、主题相同）", ""]
    if data["cn_intl_contrast_pairs"]:
        L += ["| 相似度 | 事件 A | 事件 B | 共同主题 |", "|---:|---|---|---|"]
        for c in data["cn_intl_contrast_pairs"]:
            L.append(f"| {c['sim']:.2f} | {c['a']}（{c['a_subject']}）{md_escape(truncate(c['a_title'], 50))} | "
                     f"{c['b']}（{c['b_subject']}）{md_escape(truncate(c['b_title'], 50))} | {'、'.join(c['shared_topics'])} |")
    else:
        L.append("（本期没有找到）")

    L += ["", "## AI × 语言／翻译／教育（小栏目候选，不限前 60）", ""]
    for e in data["lang_edu_column"]:
        m = e["members"][0]
        L.append(f"- {e['event_id']}（热度 {e['heat']:.2f}，{e['independent_sources']} 个来源）{md_escape(e['title_zh'] or e['title_en'])} "
                 f"— [{md_escape(m['source_name'])}]({m['url']})")
    if not data["lang_edu_column"]:
        L.append("（本期没有）")

    L += ["", "## 只有社交信号的事件（AINews 转述的 X／Reddit 帖子，多为预告、观点；需回到一手来源核实）", ""]
    for e in data["social_only"]:
        m = e["members"][0]
        L.append(f"- {e['event_id']}（热度 {e['heat']:.2f}）{md_escape(truncate(e['title_en'] or e['title_zh'], 150))} — [{md_escape(m['source_name'])}]({m['url']})")

    L += ["", "## 前 60 个事件的成员条目", ""]
    for e in data["events"]:
        L.append(f"### {e['rank']}. {md_escape(e['title_zh'] or e['title_en'])}")
        if e["title_zh"] and e["title_en"]:
            L.append(f"*{md_escape(e['title_en'])}*")
        L.append("")
        L.append(f"热度 {e['heat']:.2f}（来源项 {e['heat_detail']['sources_term']}，互动项 {e['heat_detail']['engagement_term']}，"
                 f"R={e['heat_detail']['relevance_factor']}）；独立来源 {e['independent_sources']}；{e['first_seen'][5:16].replace('T', ' ')} 起"
                 + (f"；互动 {e['engagement']}" if e["engagement"] else "") + (f"；专名 {', '.join(e['key_terms'])}" if e["key_terms"] else ""))
        L.append("")
        for m in e["members"][:12]:
            dup = f"（同链接另有：{'、'.join(d['source_name'] for d in m['dup_sources'])}）" if m.get("dup_sources") else ""
            L.append(f"- [{LAYER_LABELS[m['layer']]}·{md_escape(m['source_name'])}] [{md_escape(truncate(m['title'], 120))}]({m['url']}) "
                     f"{m['published'][5:16].replace('T', ' ')}{dup}")
        if len(e["members"]) > 12:
            L.append(f"- ……另有 {len(e['members']) - 12} 条")
        for mt in e["mentions"][:3]:
            L.append(f"- 提及：[{md_escape(mt['source_name'])}] {md_escape(truncate(mt['title'], 80))}")
        L.append("")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
