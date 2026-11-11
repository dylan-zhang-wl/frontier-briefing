#!/usr/bin/env python3
"""第 1 步 获取：按 sources_test.yaml 抓取各来源，统一字段，只留时间窗口内的条目，去掉网址重复。

运行（任意目录都行）：
  ~/.venvs/frontier-daily/bin/python pipeline/fetch.py --day 2026-10-31 --since 2026-10-29T12:00:00Z
  只跑几个来源调试：加 --only openai,qbitai

输出（测试版/<day>/01_获取/）：
  raw.jsonl      每行一条，字段 {id, source_id, source_name, layer, lang, title, url, published, summary, engagement, extra}
  每源统计.md     每个来源抓到几条、窗口内几条、去重后几条、失败原因
  每源统计.json   同上，给程序读

礼貌抓取：同一网站同时最多 2 个请求（HN、Hugging Face 接口另设），单个请求 20 秒超时，
超时／网络错误／429／5xx 最多重试一次；4xx 不重试。不登录，不碰 X、Reddit 和公众号。
"""

import argparse
import asyncio
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import feedparser
import httpx
import yaml
from bs4 import BeautifulSoup

from ainews_parse import parse_ainews
from fd_common import (LAYER_LABELS, LAYER_PRIORITY, PIPELINE_DIR, clean_summary, clean_title,
                       detect_lang, html_to_text, iso, md_escape, parse_iso, run_dir, truncate, write_jsonl)
from horizon_borrowed import dedup_url_key, entry_content, entry_published

UTC = timezone.utc
HOST_LIMITS = {"hacker-news.firebaseio.com": 8, "huggingface.co": 3}


# ───────────────────────── HTTP：礼貌并发＋重试一次 ─────────────────────────

class RetryableStatus(Exception):
    pass


class Http:
    def __init__(self, cfg: dict):
        self.retries = int(cfg["retries"])
        self.wait = float(cfg["retry_wait_s"])
        self.per_host = int(cfg["per_host_concurrency"])
        self.global_sem = asyncio.Semaphore(int(cfg["global_concurrency"]))
        self.host_sems = {}
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(float(cfg["timeout_s"])),
            headers={"User-Agent": cfg["user_agent"], "Accept": "*/*", "Accept-Language": "en,zh-CN;q=0.8"},
            follow_redirects=True,
        )

    def _sem(self, host: str) -> asyncio.Semaphore:
        if host not in self.host_sems:
            self.host_sems[host] = asyncio.Semaphore(HOST_LIMITS.get(host, self.per_host))
        return self.host_sems[host]

    async def get(self, url: str, stat: dict, **kw) -> httpx.Response:
        host = urlsplit(url).hostname or ""
        last = None
        for attempt in range(self.retries + 1):
            async with self._sem(host), self.global_sem:  # 先排同站的队，再占全局名额
                stat["requests"] += 1
                try:
                    r = await self.client.get(url, **kw)
                    if r.status_code == 429 or r.status_code >= 500:
                        raise RetryableStatus(f"HTTP {r.status_code}")
                    r.raise_for_status()  # 其余 4xx 直接失败，不重试
                    stat["http"] = r.status_code
                    return r
                except (httpx.TimeoutException, httpx.TransportError, RetryableStatus) as e:
                    last = e
            if attempt < self.retries:
                stat["retries"] += 1
                await asyncio.sleep(self.wait)
        raise last

    async def close(self):
        await self.client.aclose()


# ───────────────────────── 条目统一格式 ─────────────────────────

class Ctx:
    def __init__(self, since: datetime, now: datetime, day: str, cfg: dict):
        self.since, self.now, self.day, self.cfg = since, now, day, cfg
        self.limit = int(cfg["summary_max_chars"])


def make_item(src: dict, ctx: Ctx, *, title: str, url: str, published: datetime, summary: str = "",
              engagement: dict = None, extra: dict = None, layer: str = None, source_id: str = None,
              source_name: str = None, lang: str = None) -> dict:
    title = clean_title(title)
    summary = clean_summary(summary, ctx.limit)
    if summary == title:
        summary = ""
    sid = source_id or src["id"]
    native = (url or "") + "|" + title
    ex = {"region": src["region"], "operator": src["operator"], "ai_focused": bool(src.get("ai_focused")),
          "paywall": bool(src.get("paywall")), "roundup": bool(src.get("roundup"))}
    ex.update(extra or {})
    return {
        "id": f"{sid}:{hashlib.sha1(native.encode('utf-8')).hexdigest()[:12]}",
        "source_id": sid,
        "source_name": source_name or src["name"],
        "layer": layer or src["layer"],
        "lang": lang or detect_lang(title + " " + summary[:200], src["lang"]),
        "title": title,
        "url": url,
        "published": iso(published),
        "summary": summary,
        "engagement": {k: v for k, v in (engagement or {}).items() if v is not None},
        "extra": ex,
    }


def fix_time(pub: datetime, src: dict, ctx: Ctx, stat: dict):
    """处理晚于当前时刻的时间：中文源多是把北京时间误标成 UTC，减 8 小时；其余按当前时刻计。"""
    if pub <= ctx.now + timedelta(minutes=10):
        return pub
    if src["region"] == "cn" and pub - timedelta(hours=8) <= ctx.now + timedelta(minutes=10):
        stat["notes"]["时间晚于当前、按北京时间误标处理（减 8 小时）"] += 1
        return pub - timedelta(hours=8)
    stat["notes"]["时间晚于当前、按当前时刻计"] += 1
    return ctx.now


def in_window(pub: datetime, src: dict, ctx: Ctx) -> bool:
    return bool(src.get("window_exempt")) or pub >= ctx.since


# ───────────────────────── 各类来源 ─────────────────────────

TECHMEME_VIA = re.compile(r"\s*\(([^()]{2,80})\)\s*$")


async def fetch_rss(http: Http, src: dict, ctx: Ctx, stat: dict) -> list:
    r = await http.get(src["url"], stat)
    feed = feedparser.parse(r.content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"订阅源解析失败：{type(feed.bozo_exception).__name__}")
    stat["fetched"] = len(feed.entries)
    rows = []
    for e in feed.entries:
        pub = entry_published(e)
        if pub is None:
            stat["notes"]["没有发布时间、丢弃"] += 1
            continue
        rows.append((fix_time(pub, src, ctx, stat), e))
    rows.sort(key=lambda x: x[0], reverse=True)
    if rows:
        stat["newest"] = iso(rows[0][0])
    excl = re.compile(src["exclude_title"]) if src.get("exclude_title") else None
    items = []
    for pub, e in rows:
        if not in_window(pub, src, ctx):
            continue
        stat["in_window"] += 1
        title = e.get("title", "") or ""
        if excl and excl.search(title):
            stat["notes"]["标题命中 exclude_title、丢弃"] += 1
            continue
        if len(items) >= int(src.get("max_items", ctx.cfg["max_items"])):
            stat["notes"]["超过 max_items、丢弃"] += 1
            continue
        link = e.get("link") or ""
        summary = entry_content(e)
        extra = {"author": e.get("author", "") or "",
                 "tags": [t.get("term") for t in e.get("tags", []) if t.get("term")][:8]}
        if src["id"] == "techmeme":
            title, link, summary, extra = _techmeme(title, link, summary, extra)
        if src.get("paywall"):
            extra["note"] = "付费墙：只有标题和订阅源摘要"
        if not link:
            stat["notes"]["没有链接、丢弃"] += 1
            continue
        if src.get("title_prefix"):
            title = f"{src['title_prefix']} {clean_title(title)}"
        items.append(make_item(src, ctx, title=title, url=link, published=pub, summary=summary, extra=extra))
    return items


def _techmeme(title, link, summary_html, extra):
    """Techmeme 标题末尾的 "(作者/媒体)" 拆到 extra.via；网址换成原文链接，Techmeme 自己的链接留在 extra。"""
    clean = clean_title(title)
    m = TECHMEME_VIA.search(clean)
    if m:
        extra["via"] = m.group(1)
        clean = clean[: m.start()].strip()
    orig = ""
    soup = BeautifulSoup(summary_html or "", "lxml")
    # 原文链接是加粗标题上的那个链接；没有再退回第一个非 Techmeme 链接（前面几个可能是作者主页、媒体首页）
    for a in [b.find("a", href=True) for b in soup.find_all("b")] + soup.find_all("a", href=True):
        h = a["href"] if a is not None else ""
        if h.startswith("http") and "techmeme.com" not in h:
            orig = h
            break
    extra["techmeme_url"] = link
    text = html_to_text(summary_html)
    # 摘要里先是 "作者 / 媒体: 标题 — 导语"，只留导语
    parts = re.split(r"\s+—\s+", text, maxsplit=1)
    summary = parts[1] if len(parts) == 2 else text
    return clean, (orig or link), summary, extra


async def fetch_hn(http: Http, src: dict, ctx: Ctx, stat: dict) -> list:
    base = "https://hacker-news.firebaseio.com/v0"
    which = defaultdict(list)
    for lst in src.get("lists", ["topstories"]):
        r = await http.get(f"{base}/{lst}.json", stat)
        for rank, sid in enumerate(r.json()[: int(src.get("per_list", 100))], 1):
            which[sid].append(f"{lst.replace('stories', '')}#{rank}")

    async def one(sid):
        rr = await http.get(f"{base}/item/{sid}.json", stat)
        return rr.json()

    stories = await asyncio.gather(*(one(s) for s in which), return_exceptions=True)
    stat["fetched"] = len(which)
    items, newest = [], None
    min_score = int(src.get("min_score", 0))
    for st in stories:
        if isinstance(st, Exception) or not isinstance(st, dict):
            stat["notes"]["单条请求失败"] += 1
            continue
        if st.get("type") != "story" or st.get("dead") or st.get("deleted"):
            continue
        pub = datetime.fromtimestamp(int(st["time"]), tz=UTC)
        newest = max(newest, pub) if newest else pub
        if pub < ctx.since:
            continue
        stat["in_window"] += 1
        if int(st.get("score", 0)) < min_score:
            stat["notes"][f"分数低于 {min_score}、丢弃"] += 1
            continue
        hn_url = f"https://news.ycombinator.com/item?id={st['id']}"
        items.append(make_item(
            src, ctx, title=st.get("title", ""), url=st.get("url") or hn_url, published=pub,
            summary=html_to_text(st.get("text", "")),
            engagement={"hn_score": int(st.get("score", 0)), "hn_comments": int(st.get("descendants", 0) or 0)},
            extra={"hn_url": hn_url, "hn_lists": which[st["id"]], "author": st.get("by", "")}))
    if newest:
        stat["newest"] = iso(newest)
    return items


# Hugging Face：同一系列的量化版、不同尺寸、指令版合并成一条
_HF_SUFFIX = re.compile(
    r"[-_.](gguf|gptq|awq|fp8|fp4|nvfp4|mxfp4|bf16|fp16|int4|int8|w4a16|w8a8|mlx|onnx|diffusers|hf|"
    r"\d+bit|instruct|base|chat|thinking|preview|exp|\d{4}|a\d+(\.\d+)?b|\d+(\.\d+)?[bmt])$", re.I)


def hf_family(name: str) -> str:
    prev = None
    while prev != name:
        prev = name
        name = _HF_SUFFIX.sub("", name)
    return name or prev


def _card_text(md: str) -> str:
    md = re.sub(r"^---\n.*?\n---\n", "", md or "", flags=re.S)  # 去掉 YAML 头
    md = re.sub(r"<[^>]+>", " ", md)
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)                  # 图片
    md = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md)              # 链接留文字
    md = re.sub(r"```.*?```", " ", md, flags=re.S)                # 代码块
    lines = [ln.strip("#>*-| \t") for ln in md.splitlines()]
    lines = [ln for ln in lines if len(ln) > 25 and not ln.startswith(("http", "!", ":--", "---"))]
    return " ".join(lines)


async def fetch_hf_models(http: Http, src: dict, ctx: Ctx, stat: dict) -> list:
    author = src["author"]
    url = f"https://huggingface.co/api/models?author={quote(author)}&sort=createdAt&direction=-1&limit={int(src.get('limit', 20))}"
    r = await http.get(url, stat)
    models = r.json()
    stat["fetched"] = len(models)
    if models:
        stat["newest"] = iso(parse_iso(models[0]["createdAt"]))
    fams = defaultdict(list)
    for m in models:
        pub = parse_iso(m["createdAt"])
        if not in_window(pub, src, ctx):
            continue
        stat["in_window"] += 1
        fams[hf_family(m["id"].split("/", 1)[1])].append((pub, m))
    items = []
    for fam, ms in fams.items():
        ms.sort(key=lambda x: (-(x[1].get("likes") or 0), len(x[1]["id"])))
        pub0 = min(p for p, _ in ms)
        main = ms[0][1]
        names = [m["id"].split("/", 1)[1] for _, m in ms]
        tags = [t for t in (main.get("tags") or []) if ":" not in t][:8]
        card = ""
        try:
            rr = await http.get(f"https://huggingface.co/{main['id']}/raw/main/README.md", stat)
            card = _card_text(rr.text)
        except Exception:
            stat["notes"]["模型卡读取失败（不影响条目）"] += 1
        more = f" (+{len(ms) - 1} variants)" if len(ms) > 1 else ""
        title = f"{author} releases {fam} on Hugging Face{more}"
        meta = f"New model repos from {author}: {', '.join(names[:6])}. Task: {main.get('pipeline_tag') or 'n/a'}. Tags: {', '.join(tags)}."
        items.append(make_item(
            src, ctx, title=title, url=f"https://huggingface.co/{main['id']}", published=pub0,
            summary=meta + (" Model card: " + card if card else ""),
            engagement={"hf_likes": sum(m.get("likes") or 0 for _, m in ms),
                        "hf_downloads": sum(m.get("downloads") or 0 for _, m in ms)},
            extra={"hf_repos": [m["id"] for _, m in ms], "pipeline_tag": main.get("pipeline_tag"), "family": fam}))
    if stat["in_window"] > len(items):
        stat["notes"][f"同系列合并：{stat['in_window']} 个仓库并成 {len(items)} 条"] += 0
    return items


async def fetch_hf_papers(http: Http, src: dict, ctx: Ctx, stat: dict) -> list:
    d = ctx.since.date()
    end = datetime.strptime(ctx.day, "%Y-%m-%d").date()
    items, newest = [], None
    while d <= end:
        try:
            r = await http.get(f"https://huggingface.co/api/daily_papers?date={d.isoformat()}&limit=100", stat)
        except httpx.HTTPStatusError as e:
            # 接口只收到“最新上榜日”为止，再往后的日期回 400："date" must be less than or equal to …
            # （11-01 实测：周日 00:06 跑时请求当天 11-01 被拒，最新上榜日是周五 10-30，周六 10-31 回空列表）。
            # 这不是来源坏了：已取到的前几天照常保留，后面的日期跳过。
            if e.response.status_code == 400 and "less than or equal" in e.response.text:
                stat["notes"][f"{d.isoformat()} 起还没有上榜论文（接口只收到最新上榜日为止）"] += 0
                break
            raise
        rows = r.json() if r.content else []
        stat["fetched"] += len(rows)
        day_items = []
        for x in rows:
            p = x.get("paper") or {}
            when = p.get("submittedOnDailyAt") or x.get("publishedAt")
            if not when:
                continue
            pub = parse_iso(when)
            newest = max(newest, pub) if newest else pub
            if not in_window(pub, src, ctx):
                continue
            stat["in_window"] += 1
            try:
                up = int(p.get("upvotes") or 0)
            except ValueError:
                up = 0
            org = p.get("organization") or x.get("organization") or {}
            day_items.append((up, make_item(
                src, ctx, title=p.get("title") or x.get("title", ""), url=f"https://huggingface.co/papers/{p.get('id')}",
                published=pub, summary=p.get("ai_summary") or p.get("summary") or "",
                engagement={"hf_upvotes": up, "hf_comments": x.get("numComments")},
                extra={"arxiv_id": p.get("id"), "github": p.get("githubRepo"),
                       "org": org.get("fullname") or org.get("name") if isinstance(org, dict) else None,
                       "ai_keywords": (p.get("ai_keywords") or [])[:8]})))
        day_items.sort(key=lambda x: -x[0])
        keep = int(src.get("per_day", 30))
        if len(day_items) > keep:
            stat["notes"][f"每天只留点赞最高的 {keep} 篇"] += len(day_items) - keep
        items.extend(it for _, it in day_items[:keep])
        d += timedelta(days=1)
    if newest:
        stat["newest"] = iso(newest)
    return items


async def fetch_github_search(http: Http, src: dict, ctx: Ctx, stat: dict) -> list:
    day = datetime.strptime(ctx.day, "%Y-%m-%d").date()
    since_d = (day - timedelta(days=int(src.get("days", 7)))).isoformat()
    q = f"created:>={since_d} stars:>={int(src.get('min_stars', 50))}"
    url = f"https://api.github.com/search/repositories?q={quote(q)}&sort=stars&order=desc&per_page={int(src.get('per_page', 50))}"
    r = await http.get(url, stat, headers={"Accept": "application/vnd.github+json"})
    repos = r.json().get("items", [])
    stat["fetched"] = len(repos)
    items, newest = [], None
    for repo in repos:
        pub = parse_iso(repo["created_at"])
        newest = max(newest, pub) if newest else pub
        stat["in_window"] += 1
        desc = repo.get("description") or ""
        topics = repo.get("topics") or []
        items.append(make_item(
            src, ctx, title=f"{repo['full_name']}: {desc}" if desc else repo["full_name"], url=repo["html_url"],
            published=pub, summary=f"{desc} Topics: {', '.join(topics)}. Language: {repo.get('language') or 'n/a'}.",
            engagement={"gh_stars": repo.get("stargazers_count"), "gh_forks": repo.get("forks_count")},
            extra={"topics": topics, "language": repo.get("language"), "window_exempt": True,
                   "owner": repo["owner"]["login"]}, lang="en"))
    if newest:
        stat["newest"] = iso(newest)
    stat["notes"]["快照型来源，不受时间窗口限制"] += 0
    return items


async def fetch_github_org_repos(http: Http, src: dict, ctx: Ctx, stat: dict) -> list:
    items, newest = [], None
    for org, operator in (src.get("orgs") or {}).items():
        try:
            r = await http.get(f"https://api.github.com/orgs/{org}/repos?sort=created&direction=desc&per_page=10",
                               stat, headers={"Accept": "application/vnd.github+json"})
        except Exception as e:
            stat["notes"][f"{org} 失败：{type(e).__name__}"] += 1
            continue
        repos = r.json()
        stat["fetched"] += len(repos)
        for repo in repos:
            pub = parse_iso(repo["created_at"])
            newest = max(newest, pub) if newest else pub
            if repo.get("fork") or not in_window(pub, src, ctx):
                continue
            stat["in_window"] += 1
            desc = repo.get("description") or ""
            items.append(make_item(
                src, ctx, title=f"New GitHub repo from {org}: {repo['name']}" + (f" — {desc}" if desc else ""),
                url=repo["html_url"], published=pub, summary=f"{desc} Topics: {', '.join(repo.get('topics') or [])}.",
                engagement={"gh_stars": repo.get("stargazers_count")},
                extra={"operator": operator, "org": org}, lang="en"))
    if newest:
        stat["newest"] = iso(newest)
    return items


async def fetch_ainews(http: Http, src: dict, ctx: Ctx, stat: dict) -> list:
    r = await http.get(src["url"], stat)
    feed = feedparser.parse(r.content)
    stat["fetched"] = len(feed.entries)
    items, newest = [], None
    n_x = n_r = 0
    for e in feed.entries:
        pub = entry_published(e)
        if pub is None:
            continue
        newest = max(newest, pub) if newest else pub
        if pub < ctx.since:
            continue
        stat["in_window"] += 1
        html_body = entry_content(e)
        text = html_to_text(html_body)
        lead = text.split("AI Twitter Recap")[0]
        title = re.sub(r"^\[AINews\]\s*", "", e.get("title", ""))
        items.append(make_item(src, ctx, title=title, url=e.get("link", ""), published=pub, summary=lead,
                               extra={"issue": e.get("link", "")}))
        for s in parse_ainews(html_body):
            if s["kind"] == "x":
                n_x += 1
                t = s.get("tweet_time")
                # 帖子时间可信就用帖子时间（应在该期之前 7 天内），否则用该期时间
                spub = t if t and pub - timedelta(days=7) <= t <= pub + timedelta(hours=1) else pub
                if spub < ctx.since:
                    stat["notes"]["X 信号早于窗口、丢弃"] += 1
                    continue
                items.append(make_item(
                    src, ctx, title=s["title"], url=s["url"], published=spub, summary=s["summary"],
                    layer="social", source_id="ainews-x", source_name="AINews · X 回顾",
                    extra={"operator": "x:@" + s["x_authors"][0].lower(), "x_authors": s["x_authors"],
                           "tweet_urls": s["tweet_urls"], "topic": s["topic"], "issue": e.get("link", ""),
                           "via": "AINews AI Twitter Recap"}, lang="en"))
            else:
                n_r += 1
                items.append(make_item(
                    src, ctx, title=s["title"], url=s["url"], published=pub, summary=s["summary"],
                    layer="social", source_id="ainews-reddit", source_name="AINews · Reddit 回顾",
                    engagement={"reddit_activity": s.get("activity")},
                    extra={"operator": "reddit:" + s["url"].rstrip("/").split("/comments/")[-1].split("/")[0],
                           "subreddit": s["subreddit"], "topic": s["topic"], "group": s["group"],
                           "issue": e.get("link", ""), "via": "AINews AI Reddit Recap"}, lang="en"))
    if newest:
        stat["newest"] = iso(newest)
    stat["derived"] = {"ainews-x": n_x, "ainews-reddit": n_r}
    return items


FETCHERS = {
    "rss": fetch_rss,
    "hn": fetch_hn,
    "hf_models": fetch_hf_models,
    "hf_papers": fetch_hf_papers,
    "github_search": fetch_github_search,
    "github_org_repos": fetch_github_org_repos,
    "ainews": fetch_ainews,
}


async def run_source(http: Http, src: dict, ctx: Ctx) -> tuple:
    stat = {"id": src["id"], "name": src["name"], "type": src["type"], "layer": src["layer"],
            "status": "ok", "http": None, "requests": 0, "retries": 0, "fetched": 0, "in_window": 0,
            "items": 0, "newest": None, "error": "", "notes": Counter(), "seconds": 0.0}
    t0 = time.monotonic()
    budget = 150 if src["type"] in ("hn", "github_org_repos", "hf_papers", "hf_models") else 60
    try:
        items = await asyncio.wait_for(FETCHERS[src["type"]](http, src, ctx, stat), timeout=budget)
    except Exception as e:
        items = []
        stat["status"] = "fail"
        msg = str(e).split("\n")[0][:160]
        if isinstance(e, httpx.HTTPStatusError):
            msg = f"HTTP {e.response.status_code}"
        elif isinstance(e, asyncio.TimeoutError):
            msg = f"整体超时（{budget} 秒）"
        stat["error"] = f"{type(e).__name__}: {msg}" if msg else type(e).__name__
    stat["seconds"] = round(time.monotonic() - t0, 1)
    stat["items"] = len(items)
    if stat["status"] == "ok" and not items:
        stat["status"] = "empty"
    return items, stat


# ───────────────────────── 去重 ─────────────────────────

def dedupe(items: list) -> tuple:
    """同一网址只留一条：层级优先（一手 > 媒体 > 二手 > 社区 > 社交），同层留摘要长的。
    被并掉的条目记进保留条目的 extra.dup_sources，分数等互动数据取最大值并入；归并时它们仍算独立来源。"""
    groups = defaultdict(list)
    for it in items:
        groups[dedup_url_key(it["url"])].append(it)
    out, removed = [], Counter()
    for group in groups.values():
        group.sort(key=lambda x: (LAYER_PRIORITY.get(x["layer"], 9), -len(x["summary"]), x["published"]))
        keep = group[0]
        dups = []
        for other in group[1:]:
            removed[other["source_id"]] += 1
            for k, v in other["engagement"].items():
                if isinstance(v, (int, float)) and v > (keep["engagement"].get(k) or 0):
                    keep["engagement"][k] = v
            if other["source_id"] == keep["source_id"]:
                continue          # 同一来源重复发的（如两条 X 信号引同一帖）只合并互动数据，不另记来源
            dups.append({"source_id": other["source_id"], "source_name": other["source_name"],
                         "layer": other["layer"], "lang": other["lang"], "title": other["title"],
                         "published": other["published"], "operator": other["extra"].get("operator"),
                         "region": other["extra"].get("region"), "engagement": other["engagement"]})
        if dups:
            keep["extra"]["dup_sources"] = dups
        out.append(keep)
    out.sort(key=lambda x: x["published"], reverse=True)
    return out, removed


# ───────────────────────── 统计报告 ─────────────────────────

STATUS_LABEL = {"ok": "成功", "empty": "窗口内无新条目", "fail": "失败"}


def write_stats(out_dir: Path, stats: list, items: list, removed: Counter, ctx: Ctx, started: datetime, seconds: float,
                n_before: int):
    kept_by_source = Counter(it["source_id"] for it in items)
    for s in stats:
        s["kept"] = kept_by_source.get(s["id"], 0)
        s["dup_removed"] = removed.get(s["id"], 0)
        s["notes"] = dict(s["notes"])
    json_rows = stats + [{"id": d, "derived_from": "ainews", "kept": kept_by_source.get(d, 0),
                          "dup_removed": removed.get(d, 0)} for d in ("ainews-x", "ainews-reddit")]
    (out_dir / "每源统计.json").write_text(json.dumps(json_rows, ensure_ascii=False, indent=1), encoding="utf-8")

    n_ok = sum(s["status"] == "ok" for s in stats)
    n_empty = sum(s["status"] == "empty" for s in stats)
    n_fail = sum(s["status"] == "fail" for s in stats)
    by_layer = Counter(it["layer"] for it in items)
    by_lang = Counter(it["lang"] for it in items)
    by_region = Counter(it["extra"]["region"] for it in items)
    L = [f"# 每源统计 · {ctx.day}", "",
         f"- 运行时刻：{iso(started)}（用时 {seconds:.0f} 秒）",
         f"- 时间窗口：{iso(ctx.since)} 之后（GitHub 新星榜是快照型来源，不受窗口限制）",
         f"- 来源 {len(stats)} 个：成功 {n_ok}，窗口内无新条目 {n_empty}，失败 {n_fail}；"
         f"另由 AINews 拆出 X 回顾、Reddit 回顾两类社交信号",
         f"- 条目：各来源窗口内合计 {sum(s['in_window'] for s in stats)} 条，按规则丢弃后留 {n_before - sum(s.get('derived', {}).get('ainews-x', 0) + s.get('derived', {}).get('ainews-reddit', 0) for s in stats)} 条，"
         f"再加 AINews 拆出的社交信号，共 {n_before} 条；去掉网址重复后 **{len(items)}** 条（并掉 {sum(removed.values())} 条）",
         "- 按层级：" + "，".join(f"{LAYER_LABELS.get(k, k)} {v}" for k, v in by_layer.most_common()),
         "- 按语言：" + "，".join(f"{k} {v}" for k, v in by_lang.most_common())
         + "；按地区：" + "，".join(f"{'中国' if k == 'cn' else '国际'} {v}" for k, v in by_region.most_common()),
         "",
         "列说明：抓到 = 订阅源／接口返回的条数；窗口内 = 发布时间在窗口内的条数；保留 = 去掉网址重复后归在这个来源名下的条数；"
         "并掉 = 和别的来源网址相同、被并进别的条目的条数（并进去后仍算独立来源）。",
         "",
         "| 层级 | 来源 | 方式 | 状态 | 抓到 | 窗口内 | 保留 | 并掉 | 最新一条（UTC） | 请求/重试 | 秒 | 失败原因／备注 |",
         "|---|---|---|---|---:|---:|---:|---:|---|---|---:|---|"]
    order = list(LAYER_LABELS)
    for s in sorted(stats, key=lambda x: (order.index(x["layer"]) if x["layer"] in order else 99, x["id"])):
        notes = "；".join(f"{k}{'' if v == 0 else f' {v} 条'}" for k, v in s["notes"].items())
        if s.get("derived"):
            notes = (notes + "；" if notes else "") + f"拆出 X 信号 {s['derived'].get('ainews-x', 0)} 条、Reddit 信号 {s['derived'].get('ainews-reddit', 0)} 条"
        reason = s["error"] or notes
        newest = (s["newest"] or "-").replace("T", " ").replace("Z", "")[:16]
        L.append(f"| {LAYER_LABELS.get(s['layer'], s['layer'])} | {md_escape(s['name'])} | {s['type']} | {STATUS_LABEL[s['status']]} | "
                 f"{s['fetched']} | {s['in_window']} | {s['kept']} | {s['dup_removed']} | {newest} | {s['requests']}/{s['retries']} | "
                 f"{s['seconds']} | {md_escape(reason)} |")
    for d, label in (("ainews-x", "AINews · X 回顾（拆出）"), ("ainews-reddit", "AINews · Reddit 回顾（拆出）")):
        L.append(f"| 社交信号 | {label} | 由 ainews 拆出 | - | - | - | {kept_by_source.get(d, 0)} | {removed.get(d, 0)} | - | - | - | "
                 f"layer=social；同一帖子链接出现多次时合并 |")
    fails = [s for s in stats if s["status"] == "fail"]
    if fails:
        L += ["", "## 失败的来源", ""] + [f"- {s['name']}（{s['id']}）：{s['error']}" for s in fails]
    (out_dir / "每源统计.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# ───────────────────────── 主程序 ─────────────────────────

def load_sources(path: Path) -> tuple:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg = data["defaults"]
    ids = set()
    for s in data["sources"]:
        s["id"] = str(s["id"])
        assert s["id"] not in ids, f"来源编号重复：{s['id']}"
        ids.add(s["id"])
        assert s["type"] in FETCHERS, f"{s['id']} 的 type 不认识：{s['type']}"
        assert s["layer"] in LAYER_LABELS, f"{s['id']} 的 layer 不认识：{s['layer']}"
    return cfg, data["sources"]


async def main_async(args):
    cfg, sources = load_sources(Path(args.sources))
    if args.only:
        wanted = set(args.only.split(","))
        sources = [s for s in sources if s["id"] in wanted]
    started = datetime.now(UTC)
    day = args.day
    if args.since:
        since = parse_iso(args.since)
    else:
        since = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC) - timedelta(hours=float(cfg["since_hours_before_run_day"]))
    ctx = Ctx(since=since, now=started, day=day, cfg=cfg)
    http = Http(cfg)
    t0 = time.monotonic()
    try:
        results = await asyncio.gather(*(run_source(http, s, ctx) for s in sources))
    finally:
        await http.close()
    seconds = time.monotonic() - t0
    all_items, stats = [], []
    for items, stat in results:
        all_items.extend(items)
        stats.append(stat)
    n_before = len(all_items)
    items, removed = dedupe(all_items)
    out_dir = Path(args.out_dir) if args.out_dir else run_dir(day) / "01_获取"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "raw.jsonl", items)
    write_stats(out_dir, stats, items, removed, ctx, started, seconds, n_before)
    n_fail = sum(s["status"] == "fail" for s in stats)
    print(f"来源 {len(stats)} 个（失败 {n_fail}）；窗口内去重后 {len(items)} 条；用时 {seconds:.0f} 秒")
    for s in stats:
        if s["status"] == "fail":
            print(f"  失败 {s['id']}: {s['error']}")
    print(f"写入 {out_dir / 'raw.jsonl'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", default=datetime.now(UTC).strftime("%Y-%m-%d"), help="运行日（决定输出目录），默认今天（UTC）")
    ap.add_argument("--since", help="只留这个时刻之后的条目，ISO 格式，如 2026-10-29T12:00:00Z；默认运行日 00:00 UTC 往前 36 小时")
    ap.add_argument("--sources", default=str(PIPELINE_DIR / "sources_test.yaml"))
    ap.add_argument("--only", help="只跑这些来源（逗号分隔的 id），调试用；建议同时给 --out-dir，免得覆盖正式输出")
    ap.add_argument("--out-dir", help="输出目录，默认 测试版/<day>/01_获取")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
