"""从 Horizon 复制并改写的采集小零件（网址规范化、订阅源日期解析、订阅源正文选取）。

出处
  项目：Thysrael/Horizon  https://github.com/Thysrael/Horizon
  版本：cdd95f8e881673057e3e201717836da4b8e2e0e7（2026-10-30）
  文件：src/orchestrator.py 第 43-84 行（_TRACKING_QUERY_PARAMETERS、_deduplication_url_key）
        src/scrapers/rss.py 第 136-200 行（_parse_date、_extract_content）
  改动：去掉类和 pydantic 依赖，改成普通函数；网址键另忽略 http/https 与 www. 的差别、去掉锚点（#…），
        以便跨来源去重；日期统一转成 UTC。

许可：MIT。按许可要求，原版权声明和许可全文附在下面。

MIT License

Copyright (c) 2026 Thysrael

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import calendar
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import unquote_plus, urlsplit

# —— 来自 Horizon src/orchestrator.py:43-56：网址里的追踪参数，去重时忽略 ——
_TRACKING_QUERY_PARAMETERS = {
    "_ga",
    "dclid",
    "fbclid",
    "gclid",
    "igshid",
    "li_fat_id",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ttclid",
    "twclid",
    "vero_id",
    # 以下为本项目补充
    "ref",
    "ref_src",
    "source",
    "sref",
    "smid",
    "cmpid",
    "view_token",
    "guccounter",
    "rss",
}


def dedup_url_key(url: str) -> tuple:
    """改自 Horizon src/orchestrator.py:59-84 的 _deduplication_url_key。

    返回一个保守的"网址身份"，用于跨来源去重：主机名小写、去掉 www.、去掉默认端口、
    路径去掉结尾斜杠、去掉 utm_* 等追踪参数和锚点。协议（http/https）不参与比较。
    """
    parsed = urlsplit((url or "").strip())
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parsed.port
    if port in (80, 443):
        port = None

    path = parsed.path.rstrip("/") or "/"
    query_parts = []
    for part in parsed.query.split("&") if parsed.query else []:
        name = unquote_plus(part.partition("=")[0]).lower()
        if name.startswith("utm_") or name in _TRACKING_QUERY_PARAMETERS:
            continue
        query_parts.append(part)

    return (host, port, path, "&".join(sorted(query_parts)))


def entry_published(entry: dict) -> Optional[datetime]:
    """改自 Horizon src/scrapers/rss.py:136-165 的 _parse_date：依次试 published / updated / created。"""
    for field in ("published", "updated", "created"):
        if field in entry:
            try:
                parsed = entry.get(f"{field}_parsed")
                if parsed:
                    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
                parsed_date = parsedate_to_datetime(entry[field])
                if parsed_date.tzinfo is None:
                    parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                return parsed_date.astimezone(timezone.utc)
            except Exception:
                continue
    return None


def entry_content(entry: dict) -> str:
    """改自 Horizon src/scrapers/rss.py:167-200 的 _extract_content：在 content / summary / description 里取最长的文本。"""
    content = entry.get("content", [])
    if not isinstance(content, (list, tuple)):
        content = []
    candidates = []
    for part in content:
        if not isinstance(part, dict):
            continue
        media_type = part.get("type", "")
        if not isinstance(media_type, str):
            continue
        media_type = media_type.split(";", 1)[0].strip().lower()
        if media_type and not (
            media_type.startswith("text/")
            or media_type in ("html", "xhtml", "application/xhtml+xml")
        ):
            continue
        candidates.append(part.get("value"))
    candidates.extend([entry.get("summary"), entry.get("description")])
    return max(
        (value for value in candidates if isinstance(value, str) and value.strip()),
        key=len,
        default="",
    )
