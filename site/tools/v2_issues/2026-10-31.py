# -*- coding: utf-8 -*-
"""2026-10-31 这一期的 v2 网页配置（由 site/tools/build_v2.py 读取）。

这里只放“编辑决定”：用哪份稿、哪张图配哪条、今日数字挑哪几个、画哪些图、预告看板列哪些事、国内外对照怎么配。
所有数字和事实都用 ref=(事件号, 条目, 核对片段) 指回 03_事件卡/cards_写稿用.json：
    "F3" = 该事件卡 facts 的第 3 条（从 0 数），"N2" = numbers 的第 2 条；
    核对片段必须原样出现在那一条里（text_zh / text_en / quote / value / meaning / compare 任一字段），否则组装直接报错停下。
出处编号由组装脚本按那一条的 source_id 自动换成全站编号，这里不手写来源。
以后这份配置应由流水线生成，组装脚本不变。
"""

WEEKDAY = ("星期六", "Saturday")

WEB = "04_文稿/claude_网页.json"              # 图文与日卡：只用 Claude 稿
CARDS = "03_事件卡/cards_写稿用.json"         # 已核对的事件卡：图表、今日数字、预告看板只从这里取
CANDIDATES = "02_选题/candidates.json"         # 报道光谱：各条有几家中文、英文媒体在报
VIDEO_SCRIPT = "04_文稿/claude_视频_定时.json"
VIDEO_AUDIO = "05_配音/视频旁白_claude稿/episode.mp3"
PODCAST_DIR = "05_配音/Claude稿_Gemini配音"   # v2 播客做好后改成 05_配音/v2_…，或运行时加 --podcast

CREDIT = {"credit_zh": "AI 生成配图", "credit_en": "AI-generated image"}
# 06_配图 下的文件 → 用在哪里；文件不存在时页面自动用占位样式，图片补上后重新组装即可
IMAGES = {
    "card": dict(file="card.png", alt_zh="日卡配图：浅滩上由发光球形节点搭成的高塔，远处是厂房和落日",
                 alt_en="Day card art: a glowing tower of spherical nodes on tidal flats, with plants and a setting sun beyond"),
    "E001": dict(file="e001.png", alt_zh="配图：几股深青色的流体向右收束，汇入一个由节点和连线组成的大脑",
                 alt_en="Illustration: teal streams narrowing as they flow into a brain made of connected nodes"),
    "E002": dict(file="e002.png", alt_zh="配图：内存条从一台家用电脑飞出，排成弧线落向远处成排的数据中心机柜",
                 alt_en="Illustration: memory sticks flying out of a home PC in an arc toward rows of data-centre racks"),
    "E003": dict(file="e003.png", alt_zh="配图：架子上一排拼图形状的插件，其中一块被掀开，一根细线连向外面",
                 alt_en="Illustration: a shelf of puzzle-piece plug-ins, one pried open with a thin wire trailing out"),
    "E005": dict(file="e005.png", alt_zh="配图：层层叠叠的深青色方块像书页一样翻开，四周伸来的手各取走一页",
                 alt_en="Illustration: a stack of teal layers opening like a book while hands reach in to take pages"),
    "E007": dict(file="e007.png", alt_zh="配图：山坡上的人举着手机，一道弧线从手机越过海湾连向对岸的城市",
                 alt_en="Illustration: a person on a hillside holding a phone, an arc running from it across the bay to a city"),
    "term": dict(file="term.png", alt_zh="插画：由节点和连线织成的挂锁已经打开，钥匙插在锁孔里",
                 alt_en="Illustration: an open padlock woven from nodes and links, with a key in the lock"),
}

# ---------------------------------------------------------------- 今日数字（3–5 个；点击跳到 story）
NUMBERS = [
    dict(story="E001", ref=("E001", "N0", "~$20B"), dir="down",
         zh=dict(to=200, pre="约 ", suf=" 亿美元"), en=dict(to=20, pre="~$", suf="B"),
         label_zh="OpenAI 本轮现寻求的融资额", label_en="What OpenAI now seeks in this round",
         sub_zh="最初目标 300 亿美元", sub_en="The target was $30B", sub_ref=("E001", "N1", "$30B")),
    dict(story="E004", ref=("E004", "N0", "28.58"), dir="down",
         zh=dict(to=28.58, dec=2, pre="−", suf="%"), en=dict(to=28.58, dec=2, pre="−", suf="%"),
         label_zh="英特尔股价 · 10 月 30 日单日", label_en="Intel shares, Oct 30",
         sub_zh="有记录以来第二大单日跌幅", sub_en="Second-worst day on record", sub_ref=("E004", "F0", "第二大单日跌幅")),
    dict(story="E017", ref=("E017", "N5", "29.22%"), dir="down",
         zh=dict(to=29.22, dec=2, pre="−", suf="%"), en=dict(to=29.22, dec=2, pre="−", suf="%"),
         label_zh="Reddit 股价 · 同一天", label_en="Reddit shares, same day",
         sub_zh="2024 年上市以来最大跌幅", sub_en="Worst day since its 2024 IPO", sub_ref=("E017", "F2", "上市以来最差")),
    dict(story="E003", ref=("E003", "N0", "5,000"), dir=None,
         zh=dict(to=5000, comma=True, pre="", suf=" 名"), en=dict(to=5000, comma=True, pre="", suf=""),
         label_zh="篡改插件可能波及的开发者（上限）", label_en="Developers the tampered extension could reach, at most",
         sub_zh="在 Cursor 商城分发约 11 小时", sub_en="Live in Cursor's store for about 11 hours", sub_ref=("E003", "F4", "约 11 小时")),
    dict(story="E007", ref=("E007", "N3", "around 18"), dir="up",
         zh=dict(to=18, pre="约 ", suf=" 项"), en=dict(to=18, pre="~", suf=""),
         label_zh="国行 Apple 智能首批功能", label_en="Features in Apple Intelligence's first China batch",
         sub_zh="12 月随 iOS 27.3 推出", sub_en="Arrives with iOS 27.3 in December", sub_ref=("E007", "N1", "12 月")),
]

# ---------------------------------------------------------------- 图表（数字一律带 ref）
CHARTS = {
    "openai-raise": dict(
        type="dumbbell", title_zh="OpenAI 本轮：目标与现状", title_en="OpenAI's round: target vs. now",
        rows=[
            dict(label_zh="融资额", label_en="Raise", unit_zh="亿美元", unit_en="$B", max=320,
                 points=[
                     dict(role="from", label_zh="最初目标", label_en="Original target", v=300, v_en=30, ref=("E001", "N1", "$30B")),
                     dict(role="to", label_zh="现寻求（约）", label_en="Now sought (approx.)", v=200, v_en=20, ref=("E001", "N0", "~$20B")),
                     dict(role="mark", label_zh="已获承诺（约）", label_en="Committed (approx.)", v=110, v_en=11, ref=("E001", "N2", "~$11B")),
                 ]),
            dict(label_zh="估值", label_en="Valuation", unit_zh="万亿美元", unit_en="$T", max=1.6,
                 points=[
                     dict(role="from", label_zh="原目标估值", label_en="Target valuation", v=1.4, v_en=1.4, ref=("E001", "N4", "$1.4T")),
                     dict(role="to", label_zh="本轮估值", label_en="This round", v=1.25, v_en=1.25, ref=("E001", "N3", "$1.25T")),
                 ]),
        ],
        note_zh="均为媒体援引的匿名消息源，OpenAI 未确认；“现寻求”和“已获承诺”是两种口径。",
        note_en="All from anonymous sources cited by the press; OpenAI has not confirmed. 'Sought' and 'committed' are different measures."),
    "apple-timeline": dict(
        type="timeline", title_zh="国行 Apple 智能：从亮相到推送", title_en="Apple Intelligence in China, step by step",
        items=[
            dict(when_zh="2024 年 6 月", when_en="Jun 2024", text_zh="WWDC 上首次亮相", text_en="Debuts at WWDC", ref=("E007", "F2", "2024 年 6 月")),
            dict(when_zh="2024 年 10 月起", when_en="From Oct 2024", text_zh="海外 iPhone 陆续用上", text_en="Rolls out on iPhones elsewhere", ref=("E007", "N2", "2024 年 10 月")),
            dict(when_zh="7 月 15 日", when_en="Jul 15", text_zh="网信办备案公告，「Apple 智能」在列", text_en="Listed in a CAC filing notice", ref=("E007", "N4", "7 月 15 日")),
            dict(when_zh="9 月 29 日", when_en="Sep 29", text_zh="进网许可新增 3 个大模型备案编号", text_en="Network licence adds three model filings", ref=("E007", "N5", "9 月 29 日")),
            dict(when_zh="10 月 15 日", when_en="Oct 15", text_zh="库克称测试版“本月晚些时候”", text_en="Cook signals a beta 'later this month'", ref=("E007", "N0", "10 月 15 日")),
            dict(when_zh="10 月 31 日", when_en="Oct 31", text_zh="苹果中国官网发布新闻稿定档", text_en="Apple China's newsroom sets the date", ref=("E007", "F0", "10 月 31 日"), today=True),
            dict(when_zh="11 月 4 日", when_en="Nov 4", text_zh="开发者测试开始", text_en="Developer beta begins", ref=("E007", "N0", "11 月 4 日"), future=True),
            dict(when_zh="12 月", when_en="December", text_zh="随 iOS 27.3 面向中国用户推出", text_en="Ships in China with iOS 27.3", ref=("E007", "N1", "12 月"), future=True),
        ]),
    "apple-graph": dict(
        type="graph", title_zh="谁和谁有关：国行 Apple 智能的分工", title_en="Who does what in Apple Intelligence for China",
        nodes=[
            dict(id="ai", zh="国行 Apple 智能", en="Apple Intelligence (China)", x=46, y=44, kind="core"),
            dict(id="apple", zh="苹果自建生成式模型", en="Apple's own models", x=10, y=12, kind="apple"),
            dict(id="qwen", zh="千问 Qwen", en="Qwen", x=78, y=44, kind="ali"),
            dict(id="ali", zh="阿里巴巴 · 阿里云", en="Alibaba / Alibaba Cloud", x=78, y=6, kind="ali"),
            dict(id="qwen4", zh="Qwen4（传闻）", en="Qwen4 (rumored)", x=100, y=22, kind="ghost"),
            dict(id="siri", zh="Siri", en="Siri", x=56, y=88, kind="feat"),
            dict(id="write", zh="写作工具", en="Writing Tools", x=80, y=94, kind="feat"),
            dict(id="vis", zh="视觉智能", en="Visual Intelligence", x=100, y=78, kind="feat"),
            dict(id="baidu", zh="百度", en="Baidu", x=12, y=82, kind="ghost"),
        ],
        links=[
            dict(s="apple", t="ai", zh="底层驱动", en="runs underneath", ref=("E007", "F5", "Apple 构建的生成式模型")),
            dict(s="qwen", t="ai", zh="可选接入的扩展", en="optional add-on", ref=("E007", "F5", "可选择接入的扩展")),
            dict(s="ali", t="qwen", zh="阿里的通义千问", en="Alibaba's model", ref=("E007", "N5", "阿里的通义万相和通义千问")),
            dict(s="qwen", t="siri", zh="接 Siri 答不了的问题", en="takes what Siri can't answer", ref=("E007", "F4", "Siri 答不了的问题可转给千问")),
            dict(s="qwen", t="write", zh="新增「创作」", en="adds 'Compose'", ref=("E007", "F4", "写作工具新增「创作」")),
            dict(s="qwen", t="vis", zh="接入", en="built in", ref=("E007", "F4", "视觉智能三处")),
            dict(s="baidu", t="ai", zh="7 月曾传接入，这次未出现", en="rumored in July, absent now", ref=("E007", "F9", "未出现百度"), dashed=True),
            dict(s="ali", t="qwen4", zh="预告，传下周发布", en="teased for 'next week'", ref=("E019", "F1", "next week"), dashed=True),
        ]),
    "drops-1030": dict(
        type="bars", title_zh="10 月 30 日 · 单日跌幅", title_en="One-day drops, Oct 30", unit="%", tone="down", sign="−",
        items=[
            dict(label_zh="Reddit", label_en="Reddit", v=29.22, hl=True, story="E017", ref=("E017", "N5", "29.22%"),
                 extra_zh="上市以来最大；前纪录 20.99%（7 月 31 日）", extra_en="Worst since IPO; prior record 20.99% (Jul 31)", extra_ref=("E017", "F2", "20.99%")),
            dict(label_zh="英特尔", label_en="Intel", v=28.58, hl=True, story="E004", ref=("E004", "N0", "28.58"),
                 extra_zh="仅次于 1974 年 7 月 5 日的 29.9%", extra_en="Second only to 29.9% on Jul 5, 1974", extra_ref=("E004", "F0", "29.9%")),
            dict(label_zh="高通", label_en="Qualcomm", v=11.12, ref=("E004", "F9", "11.12")),
            dict(label_zh="AMD", label_en="AMD", v=10.88, ref=("E004", "F9", "10.88")),
            dict(label_zh="Arm", label_en="Arm", v=9.97, ref=("E004", "F9", "9.97")),
            dict(label_zh="费城半导体指数", label_en="PHLX Semiconductor", v=7.20, ref=("E004", "F9", "7.20")),
            dict(label_zh="台积电", label_en="TSMC", v=5.95, ref=("E004", "F9", "5.95")),
            dict(label_zh="博通", label_en="Broadcom", v=5.48, ref=("E004", "F9", "5.48")),
        ],
        note_zh="费城半导体指数 30 只成份股中 29 只下跌。", note_en="29 of the index's 30 members fell.", note_ref=("E004", "F9", "29只下跌")),
    "sse-weights": dict(
        type="bars", title_zh="上证综指前三大权重股", title_en="Top three weights in the SSE Composite", unit="%", compact=True,
        items=[
            dict(label_zh="长鑫科技", label_en="CXMT", v=4.67, hl=True, ref=("E038", "N7", "4.67")),
            dict(label_zh="农业银行", label_en="ABC", v=3.83, ref=("E038", "N7", "3.83")),
            dict(label_zh="工商银行", label_en="ICBC", v=3.77, ref=("E038", "N7", "3.77")),
        ]),
    "cheepseek": dict(
        type="steps", title_zh="10 美元订阅里的 DeepSeek 额度", title_en="DeepSeek credit inside a $10 plan", unit_zh="美元", unit_en="$",
        items=[
            dict(label_zh="第一阶段", label_en="Phase 1", v=30, ref=("E027", "N2", "30/60/80/100")),
            dict(label_zh="第二阶段", label_en="Phase 2", v=60, ref=("E027", "N2", "30/60/80/100")),
            dict(label_zh="第三阶段", label_en="Phase 3", v=80, ref=("E027", "N2", "30/60/80/100")),
            dict(label_zh="第四阶段", label_en="Phase 4", v=100, ref=("E027", "N2", "30/60/80/100")),
        ],
        base=dict(label_zh="订阅价 10 美元/月", label_en="Plan price $10/mo", v=10, ref=("E027", "N0", "OpenCode Go")),
        note_zh="额度不等于现金余额，按模型调用计费折算。", note_en="Credit is not cash; it is metered by model usage.", note_ref=("E027", "F6", "不等于现金余额")),
}

# 头条舞台里每条配哪几张图（多张时舞台里出现小标签切换）；快讯旁边的数据面板
STORY_CHARTS = {"E001": ["openai-raise"], "E007": ["apple-timeline", "apple-graph"]}
FLASH_CHART = "drops-1030"

# ---------------------------------------------------------------- 预告看板（只放事件卡里有出处的“将要发生的事”）
# status: rumor 传闻 / teaser 预告（当事方自己说的）/ scheduled 已排期（有明确日期）/ reported 报道称（媒体转述）
WATCH = [
    dict(status="rumor", when_zh="下周（传）", when_en="Next week?", story="E019",
         text_zh="阿里云 Qwen4 系列：Max、Flash、Plus、27B", text_en="Alibaba Cloud's Qwen4 family: Max, Flash, Plus, 27B",
         refs=[("E019", "F1", "next week"), ("E019", "F2", "Qwen4-27B")]),
    dict(status="scheduled", when_zh="11 月 4 日", when_en="Nov 4", story="E007",
         text_zh="国行 Apple 智能首批功能开放开发者测试", text_en="Apple Intelligence's first China features reach developer beta",
         refs=[("E007", "N0", "11 月 4 日")]),
    dict(status="reported", when_zh="未来几周", when_en="Coming weeks", story="E001",
         text_zh="OpenAI 本轮预计继续募资（已获约 110 亿美元承诺）", text_en="OpenAI expects to keep raising (about $11B committed)",
         refs=[("E001", "F2", "未来几周")]),
    dict(status="scheduled", when_zh="12 月", when_en="December", story="E007",
         text_zh="随 iOS 27.3 面向中国用户推出，首批约 18 项功能", text_en="Ships in China with iOS 27.3, about 18 features at first",
         refs=[("E007", "N1", "12 月"), ("E007", "F11", "18")]),
    dict(status="teaser", when_zh="第四季度", when_en="Q4", story="E017",
         text_zh="Reddit 先在美国以外部分市场测试强制登录", text_en="Reddit tests required log-ins in some markets outside the US",
         refs=[("E017", "F5", "第四季度")]),
    dict(status="rumor", when_zh="随 Qwen4", when_en="With Qwen4", story="E019",
         text_zh="Qwen4 支持 100 万 token 上下文", text_en="A 1M-token context window for Qwen4",
         refs=[("E019", "F3", "100 万")]),
    dict(status="teaser", when_zh="未来两个季度", when_en="Next two quarters", story="E004",
         text_zh="英特尔：准备好宣布几家代工客户", text_en="Intel says it will be ready to name some foundry customers",
         refs=[("E004", "F11", "未来两个季度")]),
    dict(status="teaser", when_zh="未来数月", when_en="Coming months", story="E005",
         text_zh="Mistral 持续调整 Large 4 的网安护栏", text_en="Mistral keeps adjusting Large 4's cyber guardrails",
         refs=[("E005", "F10", "未来数月")]),
    dict(status="teaser", when_zh="获批之后", when_en="After approval", story="E007",
         text_zh="iPad、Mac 等平台的国行 Apple 智能", text_en="Apple Intelligence on iPad, Mac and more in China",
         refs=[("E007", "F12", "获得必要审批后")]),
    dict(status="reported", when_zh="未来两年", when_en="Next two years", story="E008",
         text_zh="标普可能下调 Meta 信用评级（彭博）", text_en="S&P may cut Meta's credit rating (Bloomberg)",
         refs=[("E008", "F6", "未来两年")]),
    dict(status="reported", when_zh="至 2028 年", when_en="Through 2028", story="E002",
         text_zh="三星：存储芯片供应紧张可能一直持续", text_en="Samsung: the memory-chip squeeze could last",
         refs=[("E002", "F7", "2028")]),
]

# ---------------------------------------------------------------- 国内外对照（关系说明取自稿件 related 的 note）
PAIRS = [
    dict(intl="E002", cn="E038", label_zh="内存：怎么分 · 怎么卖", label_en="Memory: who gets it, who sells it", chart_cn="sse-weights"),
    dict(intl="E005", cn="E027", label_zh="开放模型：开权重 · 打低价", label_en="Open models: open weights vs. low prices", chart_cn="cheepseek"),
]

# ---------------------------------------------------------------- 视频 v2 的“节拍”（场景计划）
# 每个节拍＝画面上的一屏。这里只写“内容”和“触发词”，不写时间、不写用哪种模板：
#   at    这一屏从旁白的哪几个字开始（忽略标点空格，按顺序往后找）；
#   shape 内容的形状，组装脚本据此自动挑模板（同一模板不连用、优先用本期还没用过的），见 site/tools/video_plan.py；
#   cue   画面元素在旁白说到哪几个字的瞬间出现（逐字对齐后换成秒）；不写 cue 的元素在这一屏开头依次出现；
#   ref   凡是带数字的元素必须写 ref=(事件号, "N0"/"F2"/"Q3", 核对片段)，Q 指事件卡 open_questions_zh 的第几条。
# 来源一行由 ref 指向的出处自动生成。以后这份节拍表由流水线（写视频稿那一步）一起输出，组装脚本不变。
VIDEO_BEATS = [
    dict(at="三百亿美元的融资目标", shape="hook", ev="E001", chip=("开场", "Opening"),
         kicker=("OpenAI · 本轮融资", "OpenAI · this round"),
         sub_en="A $30B fundraising target — how did it shrink to $20B?",
         lines=[
             [dict(cue="三百亿美元", zh="300 亿美元", en="$30B", num=True, strike="缩到了", ref=("E001", "N1", "$30B")),
              dict(cue="的融资目标", zh="的融资目标", en="target")],
             [dict(cue="怎么就缩到了", zh="怎么就缩到了", en="— how did it shrink to")],
             [dict(cue="两百亿", zh="200 亿？", en="$20B?", num=True, accent=True, ref=("E001", "N0", "~$20B"))],
         ]),
    dict(at="据金融时报报道", shape="image", ev="E001", image="E001", chip=("据《金融时报》", "The FT report"),
         kicker=("OpenAI · 本轮融资", "OpenAI · this round"),
         sub_en="According to the Financial Times, as relayed by Techmeme…",
         tags=[dict(cue="金融时报", zh="《金融时报》报道", en="Financial Times report"),
               dict(cue="经Techmeme转述", zh="经 Techmeme 转述", en="via Techmeme")],
         title=dict(cue="OpenAI这一轮", zh="OpenAI 最新一轮融资", en="OpenAI's latest round")),
    dict(at="最初想融", shape="change", ev="E001", chip=("目标缩水", "Target cut"),
         kicker=("OpenAI · 本轮融资", "OpenAI · this round"),
         sub_en="…it first wanted $30B; now it seeks about $20B — a third less.",
         title=dict(zh="本轮融资额", en="Size of the round"), unit=("亿美元", "$B"), max=320, ticks=[0, 100, 200, 300],
         ticks_ref=("E001", "N1", "$30B"),
         frm=dict(cue="三百亿美元", label_zh="最初目标", label_en="Original target", v=300, v_en=30,
                  text_zh="300", text_en="$30B", ref=("E001", "N1", "$30B")),
         to=dict(cue="约两百亿", label_zh="现寻求（约）", label_en="Now sought (approx.)", v=200, v_en=20,
                 text_zh="约 200", text_en="~$20B", ref=("E001", "N0", "~$20B")),
         delta=dict(cue="少了三分之一", zh="下调约 100 亿美元", en="Cut by about $10B", dir="down",
                    ref=("E001", "N0", "下调约 100 亿美元"))),
    dict(at="另据华尔街日报", shape="amounts", ev="E001", chip=("已获承诺", "Committed"),
         kicker=("OpenAI · 本轮融资", "OpenAI · this round"),
         sub_en="The Wall Street Journal says about $11B is committed so far — under half the original target.",
         title=dict(zh="已获出资承诺", en="Committed so far"), unit=("亿美元", "$B"), max=300,
         items=[dict(label_zh="最初目标", label_en="Original target", v=300, v_en=30, ref=("E001", "N1", "$30B")),
                dict(label_zh="现寻求（约）", label_en="Now sought (approx.)", v=200, v_en=20, ref=("E001", "N0", "~$20B")),
                dict(cue="一百一十亿", label_zh="已获承诺（约）", label_en="Committed (approx.)", v=110, v_en=11, hl=True,
                     ref=("E001", "N2", "~$11B"))],
         marker=dict(cue="一半", v=150, zh="最初目标的一半", en="Half the target", ref=("E001", "F2", "目标的一半"))),
    dict(at="估值也从", shape="change", ev="E001", chip=("估值", "Valuation"),
         kicker=("OpenAI · 本轮融资", "OpenAI · this round"),
         sub_en="Its valuation slipped too, from $1.4T to $1.25T.",
         title=dict(zh="估值", en="Valuation"), unit=("万亿美元", "$T"), max=1.6,
         frm=dict(cue="一点四万亿", label_zh="原目标估值", label_en="Target valuation", v=1.4, v_en=1.4, dec=1,
                  text_zh="1.4", text_en="$1.4T", ref=("E001", "N4", "$1.4T")),
         to=dict(cue="一点二五万亿", label_zh="本轮估值", label_en="This round", v=1.25, v_en=1.25, dec=2,
                 text_zh="1.25", text_en="$1.25T", ref=("E001", "N3", "$1.25T")),
         delta=dict(cue="降到了", zh="下调", en="Lower", dir="down")),
    dict(at="报道的说法是", shape="quote", ev="E001", chip=("收敛野心", "Tempered"),
         kicker=("OpenAI · 本轮融资", "OpenAI · this round"),
         sub_en="The report's phrase: OpenAI is “tempering its ambitions.”",
         quote=dict(sync="OpenAI正在收敛野心", zh="OpenAI 正在“收敛野心”", en="OpenAI “tempers its ambitions”",
                    orig="tempers its ambitions", ref=("E001", "F1", "收敛野心")),
         who=("《金融时报》报道 · 经 Techmeme 转述", "Financial Times report, via Techmeme")),
    dict(at="Techmeme则把背景", shape="relation", ev="E001", chip=("背景", "Backdrop"),
         kicker=("OpenAI · 本轮融资", "OpenAI · this round"),
         sub_en="Techmeme's summary: some investors cut their commitments amid the AI stock selloff.",
         title=dict(cue="Techmeme则把背景", zh="背景 · Techmeme 的概括", en="The backdrop, per Techmeme"),
         nodes=[dict(id="oai", zh="OpenAI 本轮融资", en="OpenAI's round", x=80, y=34, kind="core", ref=("E001", "F0", "部分投资者")),
                dict(id="inv", cue="部分投资者", zh="部分投资者", en="Some investors", x=46, y=72),
                dict(id="sell", cue="AI股票抛售", zh="AI 股票抛售", en="AI stock selloff", x=16, y=30, kind="warn")],
         links=[dict(n1="sell", n2="inv", cue="AI股票抛售", zh="抛售之中", en="amid the selloff"),
                dict(n1="inv", n2="oai", cue="削减了承诺", zh="削减了承诺", en="cut commitments", kind="warn", flow=True)]),
    dict(at="同一周的芯片股", shape="number", ev="E004", chip=("英特尔", "Intel"),
         kicker=("芯片股 · 英特尔", "Chips · Intel"),
         sub_en="Chip stocks were rattled the same week: Intel fell 28.58% on Friday —",
         pre=dict(cue="芯片股也不平静", zh="同一周 · 芯片股也不平静", en="Same week · chip stocks rattled"),
         name=dict(cue="英特尔", zh="英特尔 · 10 月 30 日（周五）", en="Intel · Fri, Oct 30", ref=("E004", "F0", "10月30日（周五）")),
         label=dict(cue="单日下跌", zh="单日跌幅", en="One-day drop"),
         value=dict(cue="百分之二十八点五八", to=28.58, dec=2, pre="−", suf="%", dir="down", ref=("E004", "N0", "28.58"))),
    dict(at="是它有记录以来", shape="dates", ev="E004", chip=("历史第二", "2nd worst"),
         kicker=("芯片股 · 英特尔", "Chips · Intel"),
         sub_en="— its second-worst day on record.",
         title=dict(zh="英特尔有记录以来的单日跌幅", en="Intel's worst days on record"),
         span=[1970, 2026], ticks=[1980, 1990, 2000, 2010, 2020], span_ref=("E004", "F0", "1974年7月5日"),
         items=[dict(cue="有记录以来", at=1974.5, when_zh="1974 年 7 月 5 日", when_en="Jul 5, 1974",
                     text_zh="−29.9% · 最大", text_en="−29.9% · worst", ref=("E004", "F0", "1974年7月5日的29.9%")),
                dict(cue="第二大", at=2025.83, when_zh="10 月 30 日", when_en="Oct 30",
                     text_zh="−28.58% · 第二大", text_en="−28.58% · 2nd worst", hl=True, ref=("E004", "F0", "第二大单日跌幅"))]),
    dict(at="标普也把Meta", shape="points", ev="E008", chip=("Meta 展望", "Meta outlook"),
         kicker=("信用评级 · Meta", "Credit · Meta"),
         sub_en="S&P cut Meta's credit outlook to negative, citing weaker AI monetization than peers; the rating itself held.",
         title=dict(zh="标普 · Meta 信用", en="S&P on Meta"),
         items=[dict(cue="从稳定调成负面", zh="展望：稳定 → 负面", en="Outlook: stable → negative", ref=("E008", "F1", "AA- 负面")),
                dict(cue="理由是", zh="理由：AI 投资变现能力比同行更有限", en="Why: AI spending pays off less than at peers",
                     ref=("E008", "F0", "比同行更有限")),
                dict(cue="评级本身没动", zh="评级：仍为 AA-", en="Rating: still AA-", ref=("E008", "N0", "AA-"))]),
    dict(at="要提醒的是", shape="uncertain", ev="E001", chip=("未经证实", "Unconfirmed"),
         kicker=("OpenAI · 本轮融资", "OpenAI · this round"),
         sub_en="A caveat: the OpenAI story rests entirely on anonymous sources and isn't officially confirmed.",
         small=dict(cue="OpenAI这条消息", zh="OpenAI 融资消息", en="The OpenAI funding story"),
         big=dict(cue="全部来自匿名消息源", zh="全部来自匿名消息源", en="Anonymous sources only", ref=("E001", "Q3", "全部依赖匿名消息源")),
         stamp=dict(cue="官方还没有确认", zh="官方尚未确认", en="Not confirmed", ref=("E001", "Q3", "尚未"))),
    dict(at="接下来看两点", shape="points", ev="E001", chip=("接下来", "What's next"), uncertain=True,
         kicker=("OpenAI · 本轮融资", "OpenAI · this round"),
         sub_en="Two things to watch: how much more it raises in the coming weeks, and whether $20B is a ceiling or the total.",
         title=dict(cue="接下来看两点", zh="接下来看两点", en="Two things to watch"),
         items=[dict(cue="未来几周", zh="① 未来几周还能募到多少？", en="1 · How much more in the coming weeks?",
                     ref=("E001", "F2", "未来几周")),
                dict(cue="两百亿究竟", zh="② 200 亿：上限，还是预计总额？", en="2 · Is $20B a ceiling or the total?",
                     ref=("E001", "Q0", "目标上限还是预计总额"))]),
    dict(at="完整来源", shape="recap", chip=("来源", "Sources"), kicker=("回顾 · 来源", "Recap · sources"),
         sub_en="Full sources and links are on the page below.",
         tiles=[dict(ev="E001", k_zh="OpenAI · 融资目标", k_en="OpenAI · raise", v_zh="300 → 约 200 亿美元", v_en="$30B → ~$20B",
                     refs=[("E001", "N1", "$30B"), ("E001", "N0", "~$20B")]),
                dict(ev="E004", k_zh="英特尔 · 10 月 30 日", k_en="Intel · Oct 30", v_zh="−28.58%", v_en="−28.58%",
                     refs=[("E004", "N0", "28.58")]),
                dict(ev="E008", k_zh="Meta · 信用展望", k_en="Meta · outlook", v_zh="稳定 → 负面", v_en="Stable → negative",
                     refs=[("E008", "F1", "AA- 负面")])],
         cta=dict(cue="下方网页", zh="完整来源与原文链接 · 见下方网页", en="Full sources & links · on this page")),
]
