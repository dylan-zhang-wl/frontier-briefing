"""获取＋归并测试流水线共用的小工具：路径、层级、文本清洗、语言判断、时间格式。"""

import html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PIPELINE_DIR.parent


def run_dir(day: str) -> Path:
    """某一天测试版的根目录，如 测试版/2026-10-31。"""
    return PROJECT_DIR / "测试版" / day


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# 层级：代码里用英文键，给人看时用中文名
LAYER_LABELS = {
    "primary_intl": "国际一手",
    "primary_cn": "中国一手",
    "media_intl": "国际媒体",
    "media_cn": "中文媒体",
    "community": "社区信号",
    "aggregator": "二手整合",
    "lang_edu": "语言翻译教育",
    "social": "社交信号",
}

# 选代表稿、排成员顺序时的层级优先次序（数字小的优先）
LAYER_PRIORITY = {
    "primary_intl": 0,
    "primary_cn": 0,
    "media_intl": 1,
    "media_cn": 1,
    "lang_edu": 1,
    "aggregator": 2,
    "community": 3,
    "social": 4,
}


# ---------- 时间 ----------

def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------- 文本 ----------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_BOILERPLATE = [
    re.compile(r"The post .{0,300}? appeared first on .{0,120}?\.?$", re.I | re.S),
    re.compile(r"(Continue reading|Read more|Read the full story|阅读全文|查看全文|点击查看原文)[\s\S]{0,80}$", re.I),
    re.compile(r"\[(…|\.\.\.)\]\s*$"),
    re.compile(r"\s*Discussion\s*\|\s*Link\s*$"),          # Product Hunt
    re.compile(r"\s*(Comments|评论)\s*$"),
]
CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
LATIN_RE = re.compile(r"[A-Za-z]")


def html_to_text(s: str) -> str:
    """把订阅源里的 HTML 片段转成纯文本（不依赖网页结构，够用就行）。"""
    if not s:
        return ""
    if "<" in s and ">" in s:
        try:
            from bs4 import BeautifulSoup

            s = BeautifulSoup(s, "lxml").get_text(" ")
        except Exception:
            s = _TAG_RE.sub(" ", s)
    s = html.unescape(s)
    s = s.replace(" ", " ").replace("﻿", "").replace("​", "")
    return _WS_RE.sub(" ", s).strip()


def clean_summary(s: str, limit: int = 600) -> str:
    s = html_to_text(s)
    for pat in _BOILERPLATE:
        s = pat.sub("", s).strip()
    return truncate(s, limit)


def clean_title(s: str) -> str:
    return _WS_RE.sub(" ", html.unescape(html_to_text(s or ""))).strip()


def truncate(s: str, limit: int) -> str:
    s = s or ""
    if len(s) <= limit:
        return s
    cut = s[: limit - 1]
    # 尽量在句末或空格处截断
    for sep in ("。", "！", "？", ". ", "; ", "，", ", ", " "):
        pos = cut.rfind(sep)
        if pos >= limit * 0.6:
            return cut[: pos + len(sep)].rstrip() + "…"
    return cut + "…"


def detect_lang(text: str, fallback: str = "en") -> str:
    """按汉字和拉丁字母的比例粗判 zh / en。"""
    if not text:
        return fallback
    cjk = len(CJK_RE.findall(text))
    latin = len(LATIN_RE.findall(text))
    if cjk == 0 and latin == 0:
        return fallback
    # 中文稿里常夹英文专名（OpenAI、GPT-6），所以汉字只要达到字母数的 1/8 就算中文
    return "zh" if cjk >= 2 and cjk * 8 >= latin else "en"


# ---------- 读写 ----------

def read_jsonl(path: Path) -> list:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def md_escape(s: str) -> str:
    """表格里用：去掉竖线和换行。"""
    return (s or "").replace("|", "／").replace("\n", " ").strip()
