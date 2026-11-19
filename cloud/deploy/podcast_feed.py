#!/usr/bin/env python3
"""私有播客订阅源（2026-11-19 加，第一阶段）：从做好的上线包里的各期，生成 <上线包>/frontier/_podcast/。

由 cloud/deploy/assemble.py 在开关打开时调用（环境变量 FD_PODCAST_FEED=on，或命令行 --podcast），默认不做。
只读上线包里已经拼好的 issues/<日期>/（issue.js、summary.json、audio/podcast.mp3、头图），所以订阅源只收网站上有的期。

做出来的文件（Worker 只认带钥匙的网址 /frontier/podcast/<钥匙>/…，直接要 /frontier/_podcast/… 一律 404，见 src/index.js）：
    _podcast/feed.xml                订阅源模板（RSS 2.0 + iTunes 标签 + podcast:chapters），地址处写占位 __FD_FEED_BASE__，
                                     不含钥匙；Worker 回应时换成 https://wenlongzhang.com/frontier/podcast/<钥匙>
    _podcast/cover.jpg               节目封面：原样拷贝本目录 podcast/cover-3000.jpg（固定文件，podcast/make_cover.py 画的）
    _podcast/<日期>.jpg              单集封面 1400×1400：从这一期网页头图（summary.json 的 card.src）做；要 Pillow，没有就不出，
                                     播客 App 改用节目封面
    _podcast/<日期>.chapters.json    章节（podcast:chapters 格式），时间取 issue.js 的 media.podcast.chapters（带音效那一版）
mp3 不另放、一个字节都不改：订阅源里的地址由 Worker 指到 issues/<日期>/audio/podcast.mp3，length 写它原来的大小。
（第一阶段不改 mp3 里的 ID3 章节标签：等真机看过再说。）

出错不连累网站：全部先做在上线包以外的临时目录里，自检通过才整个挪进上线包；任何一步出错就整个不放，
只返回一行原因。一期出问题（读不出、没有播客）只跳过这一期，别的期照收。不调用模型、不联网。

节目名、简介、封面做法、单集封面裁法、收几期，都写在下面“可以改的”那几行，用户定了以后只改这里。
"""
import html
import json
import re
import shutil
import struct
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- 可以改的（用户定了以后只改这几行）
SHOW_NAME = "每日AI科技前沿简报"
SHOW_DESC = (                                         # 节目简介：一段一个字符串（设计稿第五节草稿原文，待用户改）
    "每日AI科技前沿简报，讲全球 AI 和科技商业的新消息，以 AI 为主、科技商业为辅，除周六外每天一期。周一到周五是工作日版：一位主播，十到十五分钟，先讲两三条热点的来龙去脉，再过几条要闻和快讯，最后是“今日一词”，一个中英对照的术语；有时还有一条值得留意、但还没得到证实的预告。周日是深谈版：两位主播用十五分钟上下，聊这一周持续发酵的一件事，也带上周五、周六的新消息。",
    "新一期通常在格林尼治时间早上六点到七点之间更新，也就是北京时间下午两三点。",
    "节目由 AI 自动化工作流制作。程序每天从几十个中英文新闻源和社区抓取、归并新闻；AI 选题、写稿，稿子里的事实、数字和原话只取自从新闻原文逐字摘出、经程序核对过的摘录；另一个独立的 AI 审读稿子，成片后再按清单检查一遍，各项都过了才自动发布。主播 Shirley 和周日的 Dylan 都是 AI 合成的声音，配图、片头片尾和转场音乐也由 AI 生成。",
    "AI 难免出错，请以原文为准：每期的网页版附有每条新闻的出处链接，页面底部可以直接反馈错误。",
    "底乐：Kevin MacLeod《Dreamer》（incompetech.com），CC BY 4.0 授权，经剪辑。",
)
SHOW_COVER = HERE / "podcast" / "cover-3000.jpg"     # 节目封面做法 (a)：程序画的占位封面，待用户定（换文件即可）
EPISODE_COVER = "A"                                   # 单集封面：A＝居中裁成正方形再放大到 1400；B＝整图不裁、上下用同图虚化填满；none＝不出
LIMIT = 60                                            # 收最近多少期（FD_PODCAST_LIMIT 可以临时改）
CATEGORIES = (("Technology", None), ("News", "Tech News"))
COPYRIGHT = "节目文字与声音由 AI 自动化工作流生成；新闻原文版权归各原发媒体"
# 章节名“热点一”后面要不要接上那条热点的标题（如“热点一 · 某某上市”）：只对这一天及以后的期接，空字符串＝都不接。
# 旧期的 listen 可能和播客里的先后对调过（11-12 实证，fix/listen-jump-video-cards 修），那个分支合进 main、
# 用新程序出了第一期以后，再把那一天填在这里。
HOT_TITLE_FROM = ""

# ---------------------------------------------------------------- 固定的
SITE = "https://wenlongzhang.com/frontier/"
PLACEHOLDER = "__FD_FEED_BASE__"                      # 和 src/access.js 的 FEED_PLACEHOLDER 一致
OUT_DIR = "_podcast"
EPISODE_PX = 1400
MAX_DESC = 10000                                      # 苹果：单集简介最多 10,000 字
MAX_SHOW_DESC_BYTES = 4000                            # 苹果：节目简介最多 4,000 字节
MAX_FILE_BYTES = 25 * 1024 * 1024                     # 同 assemble.py：Workers 单个文件上限
ALLOWED_TAGS = {"p", "ul", "ol", "li", "a"}           # 苹果允许简介里用的 HTML 标签
MAX_CHAPTER_TITLE = 40
# 底乐署名里的曲名 → 出处网址。照 site/tools/video3_music.py 的 CREDITS（那个文件要 numpy，发布环境没有，所以抄在这里；
# tests/test_deploy.py 有一条测试核对两边一致）。
MUSIC_LINKS = {"Kevin MacLeod《Dreamer》": "https://incompetech.com",
               "Scott Buckley《Castles in the Sky》": "https://www.scottbuckley.com.au"}
CC_BY = "https://creativecommons.org/licenses/by/4.0/"
# 用了 AI 生成的片头、转场、片尾音乐的声音包（按底乐认）：11-19 的 qc.json 写明 Dreamer 那套用了 Google Lyria；
# 10-31 到 11-03 的 Castles 那套没核过，所以只对 Dreamer 写“片头、转场和片尾音乐由 AI 生成”。
AI_MUSIC_BEDS = ("Kevin MacLeod《Dreamer》",)
EDITION_PREFIX = {"sun": "周日深谈", "sat": "周六深度"}
HOT_NUM = {"热点一": 0, "热点二": 1, "热点三": 2}
SECTIONS = (                                          # (order 里的键, 小标题, 带不带摘要)
    ("headline", "今日热点", True), ("deep", None, False), ("brief", "要闻", True),
    ("cn_intl", "中外对照", False), ("flash", "快讯", False), ("teaser", "预告观察", False))

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
INVISIBLE = re.compile("[​⁠­﻿]")   # 网页为了整词换行插的看不见的字符
ODD_SPACE = re.compile("[  ]")
CITE = re.compile(r"\[\^s\d+\]")                      # 正文里的出处上标记号
CTRL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")   # XML 里不许出现的控制字符


class Skip(Exception):
    """这一期不收（原因写在异常里）。"""


def clean(s):
    s = INVISIBLE.sub("", str(s or ""))
    s = ODD_SPACE.sub(" ", s)
    s = CITE.sub("", s)
    s = CTRL.sub("", s)
    return re.sub(r"[ \t]{2,}", " ", s).strip()


def esc(s):
    return html.escape(s, quote=True)


def cut(s, n):
    return s if len(s) <= n else s[:n - 1] + "…"


def hms(sec):
    sec = int(round(float(sec)))
    return "%02d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)


def read_issue_js(path):
    """同 assemble.read_issue_js：window.FD_ISSUES["日期"] = {...}; 取出那个对象。"""
    t = Path(path).read_text(encoding="utf-8")
    m = re.search(r'window\.FD_ISSUES\[(".*?")\]\s*=\s*', t)
    if not m:
        raise ValueError("issue.js 格式不对")
    return json.loads(t[m.end():].rstrip().rstrip(";"))


def _pil():
    """Pillow 在就返回 (Image, ImageFilter)，不在返回 None（不出单集封面，订阅源照出）。测试里会换掉它。"""
    try:
        from PIL import Image, ImageFilter
        return Image, ImageFilter
    except Exception:
        return None


def jpeg_size(path):
    """只用标准库读 JPEG 的宽高（找 SOF 段）。不是 JPEG 或读不出返回 None。"""
    b = Path(path).read_bytes()
    if b[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(b):
        if b[i] != 0xFF:
            return None
        marker = b[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg = struct.unpack(">H", b[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return w, h
        i += 2 + seg
    return None


# ---------------------------------------------------------------- 每一期的字段
def short_title(iss, sid):
    """日卡（card.headlines）里有这一条就用日卡的短写法，没有就用 title_zh。"""
    for h in (iss.get("card") or {}).get("headlines") or []:
        if h.get("ref") == sid and clean(h.get("zh")):
            return clean(h.get("zh"))
    return clean(((iss.get("stories") or {}).get(sid) or {}).get("title_zh"))


def episode_title(iss, summ):
    ed = iss.get("edition")
    if ed in EDITION_PREFIX:
        deep = (iss.get("order") or {}).get("deep") or []
        t = clean(((iss.get("stories") or {}).get(deep[0]) or {}).get("title_zh")) if deep else ""
        return "%s｜%s" % (EDITION_PREFIX[ed], t or clean(summ.get("lead_zh")) or iss["date"])
    heads = [clean(h.get("zh")) for h in ((iss.get("card") or {}).get("headlines") or [])][:2]
    heads = [h for h in heads if h]
    return "｜".join(heads) or clean(summ.get("lead_zh")) or "%s · %s" % (SHOW_NAME, iss["date"])


def chapters_for(iss):
    """章节：issue.js 的 media.podcast.chapters（带音效那一版的时间，和网页 mp3 一致）。
    “今日一词”后面接上词；“热点 N”只在 HOT_TITLE_FROM 以后的期、且 listen 和章节开始差不到 1 秒的那一条恰好一条时接标题。"""
    pod = (iss.get("media") or {}).get("podcast") or {}
    order = iss.get("order") or {}
    stories = iss.get("stories") or {}
    out = []
    for c in pod.get("chapters") or []:
        t = clean(c.get("title_zh"))
        start = round(float(c.get("start")), 2)
        if not t or start < 0:
            continue
        extra = ""
        if t in HOT_NUM and HOT_TITLE_FROM and iss["date"] >= HOT_TITLE_FROM:
            hit = [i for i in order.get("headline") or []
                   if isinstance((stories.get(i) or {}).get("listen"), (int, float)) and abs(float(stories[i]["listen"]) - start) < 1.0]
            if len(hit) == 1:
                extra = short_title(iss, hit[0])
        elif t == "今日一词":
            extra = clean(((iss.get("card") or {}).get("term") or {}).get("zh"))
        out.append({"start": start, "title": cut(t + (" · " + extra if extra else ""), MAX_CHAPTER_TITLE)})
    out.sort(key=lambda c: c["start"])
    return out


def pubdate(iss):
    """日期用期号；时刻取 meta.generated_at 的时刻，但只在它和期号同一天（UTC）时取，不同天（事后重建的）写 06:00 UTC。"""
    day = iss["date"]
    g = str((iss.get("meta") or {}).get("generated_at") or "").strip()
    dt = None
    try:
        dt = datetime.fromisoformat(g)
        dt = (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)   # 没写时区的按 UTC
    except (ValueError, TypeError):
        pass
    if dt is None or dt.strftime("%Y-%m-%d") != day:
        dt = datetime.fromisoformat(day + "T06:00:00+00:00")
    return dt


def _links(iss, s, srcs):
    out = []
    for x in s.get("sources") or []:
        src = srcs.get(x) or {}
        url = str(src.get("url") or "").strip()
        if not re.match(r"^https?://", url):
            continue
        name = clean(src.get("name")).split(" · ")[0] or url.split("//", 1)[1].split("/", 1)[0]
        out.append('<a href="%s">%s</a>' % (esc(url), esc(name)))
    return out


def _story_li(iss, sid, srcs, with_summary, with_links):
    s = (iss.get("stories") or {}).get(sid)
    if not s:
        return ""
    title = clean(s.get("title_zh"))
    if not title:
        return ""
    summ = clean(s.get("summary_zh")) if with_summary else ""
    links = _links(iss, s, srcs) if with_links else []
    return "<li>%s%s%s</li>" % (esc(title), ("：" + esc(summ)) if summ else "",
                                ("（出处：" + "、".join(links) + "）") if links else "")


def _music(iss):
    """底乐署名（site.music_credit 第一条：播客自己的底乐）→ (那句话的 HTML, 是不是用了 AI 片头片尾那套)。没有就 ("", False)。"""
    mc = (iss.get("site") or {}).get("music_credit") or []
    music = clean(mc[0]).rstrip("。") if mc else ""
    if not music:
        return "", False
    links = ['<a href="%s">%s</a>' % (u, esc(u.split("//", 1)[1])) for n, u in MUSIC_LINKS.items() if n in music]
    if "CC BY 4.0" in music:
        links.append('<a href="%s">CC BY 4.0 许可</a>' % CC_BY)
    return esc(music) + ("（" + "，".join(links) + "）" if links else "") + "。", any(n in music for n in AI_MUSIC_BEDS)


def description(iss, summ, chs, level=0):
    """单集简介（HTML，只用 p ul ol li a）。level 越大越省：1 快讯等去掉出处，2 热点要闻去掉摘要，3 一律只留标题，
    4 快讯、对照、预告整段不列，5 各段新闻都不列（只留导语、今日一词、章节、网页链接和制作说明）。"""
    day = iss["date"]
    srcs = {s.get("id"): s for s in iss.get("sources") or [] if isinstance(s, dict)}
    order = iss.get("order") or {}
    P = []
    hots = list(order.get("headline") or [])
    if hots:
        more = []
        if order.get("brief"):
            more.append("%d 条要闻" % len(order["brief"]))
        if order.get("flash"):
            more.append("%d 条快讯" % len(order["flash"]))
        term0 = clean(((iss.get("card") or {}).get("term") or {}).get("zh"))
        if term0:
            more.append("今日一词“%s”" % term0)
        names = [t for t in (short_title(iss, i) for i in hots) if t]
        lede = ("今天的热点：%s。" % "；".join(names)) if names else ""
        if more:
            lede += "后面还有 " + "、".join(more) + "。"
    else:
        deep = order.get("deep") or []
        lede = clean(((iss.get("stories") or {}).get(deep[0]) or {}).get("summary_zh")) if deep else ""
    if lede:
        P.append("<p>%s</p>" % esc(lede))
    for key, label, full in SECTIONS:
        ids = order.get(key) or []
        if not ids or level >= 5 or (level >= 4 and key in ("cn_intl", "flash", "teaser")):
            continue
        if key == "deep":
            label = "深谈" if iss.get("edition") == "sun" else "深度"
        with_summary = full and level < 2
        with_links = level < 3 and (full or level < 1)
        lis = "".join(_story_li(iss, i, srcs, with_summary, with_links) for i in ids)
        if lis:
            P.append("<p>%s</p><ul>%s</ul>" % (label, lis))
    term = (iss.get("card") or {}).get("term") or {}
    if clean(term.get("zh")):
        en = clean(term.get("en"))
        P.append("<p>今日一词：%s%s。%s</p>" % (esc(clean(term["zh"])), ("（%s）" % esc(en)) if en else "", esc(clean(term.get("explain_zh")))))
    if len(chs) >= 3:
        P.append("<p>章节</p><ul>%s</ul>" % "".join("<li>%s %s</li>" % (hms(c["start"]), esc(c["title"])) for c in chs))
    look = '<a href="%s?date=%s">网页版</a>（图文、出处、数据图）' % (SITE, day)
    video = (iss.get("media") or {}).get("video")
    if video:
        try:
            short = float(video.get("duration") or 0) <= 180
        except (TypeError, ValueError, AttributeError):
            short = False
        look += "；网页里还有一段%s动画视频" % ("三分钟内的" if short else "")
    P.append("<p>%s。发现错误，可在网页底部点“反馈”。</p>" % look)
    credit, ai_music = _music(iss)
    P.append("<p>制作说明：本节目由 AI 自动化工作流制作。选题、写稿由 AI 完成，另一个独立的 AI 审读；事实和数字只取自逐字核对过的新闻原文摘录；"
             "主播声音为 AI 合成，配图由 AI 生成%s。%s新闻原文的版权归各原发媒体。</p>"
             % ("，片头、转场和片尾音乐由 AI 生成" if ai_music else "", credit))
    return "".join(P)


def fit_description(iss, summ, chs):
    for level in range(6):
        d = description(iss, summ, chs, level)
        if len(d) <= MAX_DESC:
            return d
    raise Skip("简介怎么省都超过 %d 字" % MAX_DESC)


# ---------------------------------------------------------------- 文件
def episode_cover(src, dst, pil):
    """头图 → 1400×1400 JPEG（RGB，不带透明）。同一输入两次写出逐字节相同。"""
    Image, ImageFilter = pil
    with Image.open(src) as im0:
        im = im0.convert("RGB")
    w, h = im.size
    if min(w, h) < 200:
        raise ValueError("头图太小（%d×%d）" % (w, h))
    if EPISODE_COVER == "B":
        bg = im.resize((max(EPISODE_PX, int(w * EPISODE_PX / h)), EPISODE_PX), Image.LANCZOS)
        bw = bg.size[0]
        bg = bg.crop(((bw - EPISODE_PX) // 2, 0, (bw - EPISODE_PX) // 2 + EPISODE_PX, EPISODE_PX)).filter(ImageFilter.GaussianBlur(28))
        fg = im.resize((EPISODE_PX, min(EPISODE_PX, int(h * EPISODE_PX / w))), Image.LANCZOS)
        out = bg.copy()
        out.paste(fg, (0, (EPISODE_PX - fg.size[1]) // 2))
    else:
        s = min(w, h)
        out = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((EPISODE_PX, EPISODE_PX), Image.LANCZOS)
    out.save(dst, "JPEG", quality=88, optimize=True, progressive=False)


def build_feed(items, show_desc_html):
    E = esc

    def cdata(s):
        return "<![CDATA[" + s.replace("]]>", "]]]]><![CDATA[>") + "]]>"
    last = format_datetime(max(it["pub"] for it in items))   # 最新一期的发布时间（不用当时的钟点：同样的输入两次做出来逐字节一样）
    x = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" '
         'xmlns:podcast="https://podcastindex.org/namespace/1.0" xmlns:atom="http://www.w3.org/2005/Atom">',
         "<channel>",
         "<title>%s</title>" % E(SHOW_NAME),
         "<link>%s</link>" % SITE,
         '<atom:link href="%s/feed.xml" rel="self" type="application/rss+xml"/>' % PLACEHOLDER,
         "<language>zh-cn</language>",
         "<description>%s</description>" % cdata(show_desc_html),
         '<itunes:image href="%s/cover.jpg"/>' % PLACEHOLDER,
         "<image><url>%s/cover.jpg</url><title>%s</title><link>%s</link></image>" % (PLACEHOLDER, E(SHOW_NAME), SITE),
         "<itunes:author>%s</itunes:author>" % E(SHOW_NAME)]
    for top, sub in CATEGORIES:
        x.append('<itunes:category text="%s">%s</itunes:category>' % (E(top), '<itunes:category text="%s"/>' % E(sub)) if sub
                 else '<itunes:category text="%s"/>' % E(top))
    x += ["<itunes:explicit>false</itunes:explicit>",
          "<itunes:type>episodic</itunes:type>",
          "<itunes:block>Yes</itunes:block>",
          "<podcast:locked>yes</podcast:locked>",
          "<copyright>%s</copyright>" % E(COPYRIGHT),
          "<lastBuildDate>%s</lastBuildDate>" % last]
    for it in items:
        d = it["day"]
        x += ["<item>",
              "<title>%s</title>" % E(it["title"]),
              "<description>%s</description>" % cdata(it["desc"]),
              '<enclosure url="%s/%s.mp3" length="%d" type="audio/mpeg"/>' % (PLACEHOLDER, d, it["size"]),
              '<guid isPermaLink="false">frontier-daily-podcast-%s</guid>' % d,
              "<pubDate>%s</pubDate>" % format_datetime(it["pub"]),
              "<link>%s?date=%s</link>" % (SITE, d),
              "<itunes:duration>%d</itunes:duration>" % it["dur"]]
        if it["cover"]:
            x.append('<itunes:image href="%s/%s.jpg"/>' % (PLACEHOLDER, d))
        x += ["<itunes:episodeType>full</itunes:episodeType>",
              "<itunes:explicit>false</itunes:explicit>"]
        if it["chapters"]:
            x.append('<podcast:chapters url="%s/%s.chapters.json" type="application/json+chapters"/>' % (PLACEHOLDER, d))
        x.append("</item>")
    x += ["</channel>", "</rss>"]
    return "\n".join(x) + "\n"


def show_desc_html():
    return "".join("<p>%s</p>" % esc(clean(p)) for p in SHOW_DESC)


# ---------------------------------------------------------------- 自检
NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd", "podcast": "https://podcastindex.org/namespace/1.0",
      "atom": "http://www.w3.org/2005/Atom"}


def check(pod, issues_root, items):
    """自检做好的 _podcast/ 目录。返回问题列表（空＝通过）。"""
    problems = []
    feed = (pod / "feed.xml").read_text(encoding="utf-8")
    try:
        root = ET.fromstring(feed.encode("utf-8"))
    except ET.ParseError as e:
        return ["feed.xml 不是合法的 XML（%s）" % e]
    ch = root.find("channel")
    if root.tag != "rss" or ch is None:
        return ["feed.xml 没有 rss/channel"]
    for t in ("title", "link", "language", "description", "itunes:image", "itunes:category", "itunes:explicit", "itunes:block", "atom:link"):
        if ch.find(t, NS) is None:
            problems.append("频道缺 %s" % t)
    if PLACEHOLDER not in feed or "/frontier/podcast/" in feed:
        problems.append("地址占位不对（要有 %s，不能有 /frontier/podcast/）" % PLACEHOLDER)
    sd = ch.findtext("description") or ""
    if len(sd.encode("utf-8")) > MAX_SHOW_DESC_BYTES:
        problems.append("节目简介 %d 字节，超过 %d" % (len(sd.encode("utf-8")), MAX_SHOW_DESC_BYTES))
    if set(re.findall(r"</?([a-zA-Z][a-zA-Z0-9]*)", sd)) - ALLOWED_TAGS:
        problems.append("节目简介用了不许用的标签")
    size = jpeg_size(pod / "cover.jpg") if (pod / "cover.jpg").is_file() else None
    if not size or size[0] != size[1] or not 1400 <= size[0] <= 3000:
        problems.append("节目封面不是 1400–3000 见方的 JPEG（%s）" % (size,))
    its = ch.findall("item")
    if len(its) != len(items) or not its:
        problems.append("单集数 %d，应为 %d（至少 1）" % (len(its), len(items)))
    guids = set()
    for el, it in zip(its, items):
        d = it["day"]
        enc = el.find("enclosure")
        guid = el.findtext("guid") or ""
        if not (el.findtext("title") or "").strip() or enc is None or not guid:
            problems.append("%s 缺 title、enclosure 或 guid" % d)
            continue
        if guid != "frontier-daily-podcast-" + d or guid in guids:
            problems.append("%s 的 guid 不对或重复" % d)
        guids.add(guid)
        mp3 = issues_root / d / "audio" / "podcast.mp3"
        if enc.get("url") != "%s/%s.mp3" % (PLACEHOLDER, d) or not mp3.is_file() or enc.get("length") != str(mp3.stat().st_size):
            problems.append("%s 的 enclosure 和上线包里的 mp3 对不上" % d)
        desc = el.findtext("description") or ""
        if len(desc) > MAX_DESC:
            problems.append("%s 的简介 %d 字，超过 %d" % (d, len(desc), MAX_DESC))
        if set(re.findall(r"</?([a-zA-Z][a-zA-Z0-9]*)", desc)) - ALLOWED_TAGS:
            problems.append("%s 的简介用了不许用的标签" % d)
        img = el.find("itunes:image", NS)
        if img is not None:
            sz = jpeg_size(pod / (d + ".jpg")) if (pod / (d + ".jpg")).is_file() else None
            if not sz or sz[0] != sz[1] or not 1400 <= sz[0] <= 3000:
                problems.append("%s 的单集封面不对" % d)
        if el.find("podcast:chapters", NS) is not None:
            try:
                j = json.loads((pod / (d + ".chapters.json")).read_text(encoding="utf-8"))
                assert j["version"] == "1.2.0" and j["chapters"]
            except Exception:
                problems.append("%s 的章节文件不对" % d)
    for f in pod.iterdir():
        if f.stat().st_size > MAX_FILE_BYTES:
            problems.append("%s 超过 25 MiB" % f.name)
    return problems


# ---------------------------------------------------------------- 入口
def build(out, limit=LIMIT, cover=None):
    """在上线包 out（里面是 frontier/…）里做 frontier/_podcast/。不抛异常：
    返回 {"ok": bool, "n": 期数, "line": 给人看的一行, "notes": [跳过了哪几期、为什么], "covers": 单集封面张数}。"""
    out = Path(out)
    root = out / "frontier"
    issues_root = root / "issues"
    notes = []
    try:
        if (root / OUT_DIR).exists():
            raise RuntimeError("上线包里已经有 frontier/%s" % OUT_DIR)
        cover = Path(cover) if cover else SHOW_COVER
        if not cover.is_file():
            raise RuntimeError("找不到节目封面 %s" % cover.name)
        pil = _pil() if EPISODE_COVER in ("A", "B") else None
        days = sorted((d.name for d in issues_root.iterdir() if d.is_dir() and DATE_RE.match(d.name)), reverse=True) if issues_root.is_dir() else []
        with tempfile.TemporaryDirectory(prefix="fd-podcast-") as td:
            pod = Path(td) / OUT_DIR
            pod.mkdir()
            shutil.copyfile(cover, pod / "cover.jpg")
            items = []
            for day in days:
                if len(items) >= limit:
                    break
                d = issues_root / day
                try:
                    iss = read_issue_js(d / "issue.js")
                    summ = json.loads((d / "summary.json").read_text(encoding="utf-8"))
                    if iss.get("date") != day:
                        raise Skip("issue.js 里的日期和目录对不上")
                    podm = (iss.get("media") or {}).get("podcast")
                    mp3 = d / "audio" / "podcast.mp3"
                    if not podm or not mp3.is_file():
                        raise Skip("没有播客")
                    chs = chapters_for(iss)
                    it = {"day": day, "title": episode_title(iss, summ), "desc": fit_description(iss, summ, chs),
                          "size": mp3.stat().st_size, "dur": int(round(float(podm.get("duration") or 0))), "pub": pubdate(iss),
                          "chapters": bool(chs), "cover": False}
                    if it["size"] <= 0:
                        raise Skip("mp3 是空的")
                except Skip as e:
                    notes.append("跳过 %s：%s" % (day, e))
                    continue
                except Exception as e:
                    notes.append("跳过 %s：读不出（%s）" % (day, type(e).__name__))
                    continue
                if chs:
                    (pod / (day + ".chapters.json")).write_text(json.dumps(
                        {"version": "1.2.0", "chapters": [{"startTime": c["start"], "title": c["title"]} for c in chs]},
                        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                if pil:
                    src = str((summ.get("card") or {}).get("src") or "")
                    try:
                        p = (d / src).resolve()
                        if not src or not p.is_file() or d.resolve() not in p.parents:
                            raise ValueError("没有头图")
                        episode_cover(p, pod / (day + ".jpg"), pil)
                        it["cover"] = True
                    except Exception as e:
                        notes.append("%s 没做单集封面（%s）" % (day, type(e).__name__ if not isinstance(e, ValueError) else e))
                        if (pod / (day + ".jpg")).exists():
                            (pod / (day + ".jpg")).replace(Path(td) / ("坏的_" + day + ".jpg"))   # 挪出 _podcast/，不删
                items.append(it)
            if not items:
                raise RuntimeError("一期能收的都没有")
            (pod / "feed.xml").write_text(build_feed(items, show_desc_html()), encoding="utf-8")
            problems = check(pod, issues_root, items)
            if problems:
                raise RuntimeError("自检没过：" + "；".join(problems[:5]))
            dst = root / OUT_DIR
            try:
                shutil.move(str(pod), str(dst))
            except Exception:
                if dst.exists():                      # 挪到一半出错：把挪进去的那部分挪回临时目录，上线包里不留
                    shutil.move(str(dst), str(Path(td) / "挪了一半"))
                raise
        n_cov = sum(1 for it in items if it["cover"])
        line = "播客订阅源：%d 期（%s 到 %s），单集封面 %d 张%s。" % (
            len(items), items[-1]["day"], items[0]["day"], n_cov, "" if pil else "（没有 Pillow，全用节目封面）")
        return {"ok": True, "n": len(items), "covers": n_cov, "line": line, "notes": notes}
    except Exception as e:
        msg = str(e) if isinstance(e, RuntimeError) else "%s：%s" % (type(e).__name__, e)
        return {"ok": False, "n": 0, "covers": 0, "line": "播客订阅源这次没做成：%s（网站照常发布，这次不出订阅源）。" % msg[:300],
                "notes": notes}
