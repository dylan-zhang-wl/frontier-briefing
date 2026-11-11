"""把 AINews 每期的 "AI Twitter Recap"、"AI Reddit Recap" 两栏拆成一条条社交信号。

只解析 AINews 订阅源里已有的 HTML，不访问 X 和 Reddit。
- X 信号：每个列表项（含嵌套项）只要自己那段文字里带 x.com/…/status/… 链接，就算一条；
  记下发帖人、要点、帖子链接。发帖时间从帖子编号里解出（X 的编号前 41 位是毫秒时间戳）。
- Reddit 信号：每个顶层列表项是一篇帖子，记下标题、版块、Activity 数和 AINews 的概述。
"""

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from fd_common import truncate

X_STATUS_RE = re.compile(r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,20})/status/(\d+)")
REDDIT_RE = re.compile(r"^https?://(?:www\.|old\.)?reddit\.com/r/([A-Za-z0-9_]+)/comments/")
_TWITTER_EPOCH_MS = 1288834974657
_WS = re.compile(r"\s+")


def tweet_time(status_id: str):
    """X 帖子编号（snowflake）→ 发帖时间（UTC）。"""
    try:
        ms = (int(status_id) >> 22) + _TWITTER_EPOCH_MS
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except Exception:
        return None


def _text(el) -> str:
    if el is None:
        return ""
    t = _WS.sub(" ", el.get_text(" ", strip=True)).strip()
    return re.sub(r"\s+([,.;:!?)])", r"\1", t).replace("( ", "(")


def _own_p(li):
    return li.find("p", recursive=False)


def _x_links(p):
    if p is None:
        return []
    return [a["href"] for a in p.find_all("a", href=True) if X_STATUS_RE.match(a["href"])]


def _strip_link_noise(p) -> str:
    """去掉 "(@a, @b)" "(announcement)" 这类只由链接文字组成的括注，保留正文。"""
    p = BeautifulSoup(str(p), "lxml").find("p")
    for a in p.find_all("a", href=True):
        if X_STATUS_RE.match(a["href"]):
            a.decompose()
    t = _text(p)
    t = re.sub(r"\(\s*(?:[,;、]|\band\b|\s)*\)", "", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    return _WS.sub(" ", t).strip()


def _first_sentence(s: str, limit: int = 150) -> str:
    m = re.search(r"^(.{20,}?[.!?])(\s|$)", s)
    out = m.group(1) if m else s
    return truncate(out, limit)


def _x_signals(li, topic: str, parent_lead: str = ""):
    sigs = []
    p = _own_p(li)
    links = _x_links(p)
    lead = ""
    if p is not None and p.find("b") is not None:
        lead = _text(p.find("b")).rstrip(":： ").strip()
    body = _strip_link_noise(p) if p is not None else ""
    if lead and body.startswith(lead):
        body = body[len(lead):].lstrip(":： ").strip()

    context = []
    for sub_ul in li.find_all("ul", recursive=False):
        for sub in sub_ul.find_all("li", recursive=False):
            if _x_links(_own_p(sub)):
                sigs.extend(_x_signals(sub, topic, lead or parent_lead))
            else:
                context.append(_text(sub))

    if links:
        handles = []
        for link in links:
            h = X_STATUS_RE.match(link).group(1)
            if h not in handles:
                handles.append(h)
        status_id = X_STATUS_RE.match(links[0]).group(2)
        head = f"{parent_lead} — {lead}" if parent_lead and lead else (lead or parent_lead)
        sentence = _first_sentence(body) if body else ""
        title = f"{head}: {sentence}" if head and sentence else (head or sentence)
        by = ", ".join("@" + h for h in handles[:3]) + (" 等" if len(handles) > 3 else "")
        sigs.insert(0, {
            "kind": "x",
            "title": truncate(f"{title} (via {by})", 220),
            "url": links[0],
            "summary": " ".join([body] + context),
            "topic": topic,
            "x_authors": handles,
            "tweet_urls": list(dict.fromkeys(links)),
            "tweet_time": tweet_time(status_id),
        })
    return sigs


def _reddit_signal(li, topic: str, group: str):
    p = _own_p(li)
    if p is None:
        return None
    a = next((a for a in p.find_all("a", href=True) if REDDIT_RE.match(a["href"])), None)
    if a is None:
        return None
    text = _text(p)
    m = re.search(r"\(Activity:\s*([\d,]+)\)\s*:?", text)
    activity = int(m.group(1).replace(",", "")) if m else None
    body = text[m.end():].strip() if m else text
    return {
        "kind": "reddit",
        "title": _text(a),
        "url": a["href"],
        "summary": body,
        "topic": topic,
        "subreddit": REDDIT_RE.match(a["href"]).group(1),
        "group": group,
        "activity": activity,
    }


def parse_ainews(html_text: str) -> list:
    """返回信号列表（dict）。结构变了解析不出时返回空列表，不报错。"""
    soup = BeautifulSoup(html_text or "", "lxml")
    section, topic, group = None, "", ""
    out = []
    for el in soup.find_all(["h1", "h2", "h3", "p", "ul"]):
        name = el.name
        if name == "h1":
            t = _text(el).lower()
            section = "x" if "twitter" in t else ("reddit" if "reddit" in t else None)
            topic, group = "", ""
        elif section is None:
            continue
        elif name == "h2":
            group, topic = _text(el), ""
        elif name == "h3":
            topic = re.sub(r"^\d+\.\s*", "", _text(el))
        elif name == "p":
            # X 回顾里的小标题是只有加粗文字的段落（不在列表项里）
            if el.find_parent("li") is None and section == "x":
                b = el.find("b")
                if b is not None and _text(b) == _text(el):
                    topic = _text(el)
        elif name == "ul" and el.find_parent("li") is None:
            for li in el.find_all("li", recursive=False):
                if section == "x":
                    out.extend(_x_signals(li, topic))
                else:
                    s = _reddit_signal(li, topic, group)
                    if s:
                        out.append(s)
    return out


if __name__ == "__main__":
    import sys

    sigs = parse_ainews(open(sys.argv[1], encoding="utf-8").read())
    print(len(sigs), "signals;", sum(s["kind"] == "x" for s in sigs), "x,", sum(s["kind"] == "reddit" for s in sigs), "reddit")
    for s in sigs[:12] + sigs[-6:]:
        print("-", s["kind"], "|", s["title"][:150], "|", s["url"][:70], "|", s.get("tweet_time") or s.get("activity"))
        print("    ", s["summary"][:160])
