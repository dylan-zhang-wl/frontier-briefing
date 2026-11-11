#!/usr/bin/env python3
"""第 2 步 粗筛：用关键词＋实体表做便宜的相关性判断（不调用大模型），中英文都认。宁宽勿严。

规则（按顺序）：
  1. 来源本身专讲 AI（sources_test.yaml 里 ai_focused: true，以及 AINews 拆出的社交信号）→ 一律保留。
  2. 标题像导购促销（价格＋"到手／券后／国补"等词）且 AI 词不多 → 剔除。
  3. 综合来源：标题里有 AI 强词或 AI 公司／模型／芯片实体（或 2 个弱词），或者摘要里有 2 个以上不同的强词／实体 → 保留；
     或者"科技公司＋商业／安全／政策词"（标题里有科技公司，或标题里有商业／安全词而摘要里有科技公司）→ 保留为科技商业；
     或者标题有弱词（芯片、机器人……）＋商业／政策词 → 宽松保留；其余剔除。
     只看标题为主，是因为综合媒体的长摘要常顺带提一句 AI 或某家大公司，只看摘要会放进很多数码导购和社会新闻。
  每条都写下保留或剔除的理由，以及命中的词、实体、主题标签和"主体属于中国还是国际"。

  相关度 relevance：ai（命中 AI 词或实体）、lang_edu（AI × 语言／翻译／教育）、tech_business（只命中科技商业）、
  other（因来源专注 AI 而保留、但没命中词表）。归并打热度时按相关度打折（见 cluster.py）。

运行：~/.venvs/frontier-daily/bin/python pipeline/prefilter.py --day 2026-10-31
输入：测试版/<day>/01_获取/raw.jsonl
输出：测试版/<day>/01_获取/prefilter.jsonl（全部条目，多一个 pf 字段）、粗筛统计.md
"""

import argparse
import copy
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from fd_common import LAYER_LABELS, md_escape, read_jsonl, run_dir, write_jsonl


def _ascii_pat(term: str, case: bool) -> str:
    body = re.escape(term).replace(r"\ ", r"[\s\-]?")
    return rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])" if case else rf"(?i:(?<![A-Za-z0-9]){body}(?![A-Za-z0-9]))"


def compile_terms(terms):
    """terms 里每项是字符串或 (字符串, 是否区分大小写)。纯 ASCII 词按词边界匹配；含汉字的按子串匹配。"""
    out = []
    for t in terms:
        term, case = (t, False) if isinstance(t, str) else t
        if term.startswith("re:"):
            out.append((term[3:], re.compile(term[3:])))
        elif re.search(r"[^\x00-\x7f]", term):
            out.append((term, re.compile(re.escape(term))))
        else:
            out.append((term, re.compile(_ascii_pat(term, case))))
    return out


# ───────────────────────── 词表 ─────────────────────────
# 区分大小写的短缩写写成 (词, True)

AI_STRONG = compile_terms([
    ("AI", True), ("A.I.", True), ("AGI", True), ("LLM", True), ("LLMs", True), ("GPU", True), ("GPUs", True),
    ("TPU", True), ("NPU", True), ("HBM", True), ("RAG", True), ("MCP", True), ("AIGC", True), ("GenAI", True),
    "artificial intelligence", "machine learning", "deep learning", "neural network", "neural networks",
    "large language model", "language model", "language models", "foundation model", "frontier model",
    "frontier models", "generative", "chatbot", "chatbots", "AI agent", "AI agents", "agentic", "coding agent",
    "coding agents", "superintelligence", "super intelligence", "multimodal", "open-weight", "open weights",
    "reasoning model", "world model", "diffusion model", "text-to-image", "text-to-video", "text-to-speech",
    "data center", "data centers", "datacenter", "datacenters", "hyperscaler", "hyperscalers", "humanoid",
    "robotaxi", "robotaxis", "self-driving", "autonomous driving", "deepfake", "deepfakes", "RLHF", "fine-tuning",
    "fine-tuned", "pretraining", "post-training", "inference", "vibe coding", "prompt injection", "jailbreak",
    "hallucination", "hallucinations", "embodied", "speech recognition", "machine translation", "computer vision",
    "transformer model", "token pricing", "context window", "AI chip", "AI chips", "accelerator chips",
    ("TPUs", True), ("LoRA", True), ("vLLM", True), "open model", "open models", "AI-powered", "AI-generated",
    "image generation", "video generation", "3D generation", "computer-use", "computer use", "model weights",
    "distillation", "reinforcement learning", "GPU cluster", "AI lab", "AI labs", "AI startup", "AI startups",
    "人工智能", "大模型", "大语言模型", "语言模型", "生成式", "智能体", "多模态", "通用人工智能", "超级智能", "算力", "智算",
    "具身智能", "具身", "人形机器人", "自动驾驶", "智驾", "无人驾驶", "数据中心", "深度学习", "机器学习", "神经网络",
    "世界模型", "文生图", "文生视频", "视频生成", "图像生成", "数字人", "提示词", "开源模型", "推理模型", "机器翻译",
    "语音识别", "语音合成", "AI 编程", "AI编程", ("Agent", True), "端侧模型", "预训练", "后训练", "微调",
])

AI_WEAK = compile_terms([
    "model", "models", "robot", "robots", "robotics", "chip", "chips", "chipmaker", "chipmakers", "semiconductor",
    "semiconductors", "training", "open source", "open-source", "algorithm", "algorithms", "automation",
    "benchmark", "benchmarks", "coding", "copilot", "assistant", "speech", "voice", "translation", "memory chips",
    "DRAM", "foundry", "wafer", "cloud computing", "compute", "agent", "agents", "transformer", "transformers",
    "parameters", ("RL", True), "checkpoint", "prompt", "prompts", "neuron", "neurons", "simulation",
    "模型", "机器人", "芯片", "半导体", "推理", "训练", "开源", "算法", "自动化", "智能", "语音", "内存", "存储芯片",
    "服务器", "编程", "代码", "晶圆", "光刻", "制程", "云计算", "助手", "翻译",
])

# 实体：标签 → (匹配写法, 地区, 类别)。类别 ai = AI 公司／产品／芯片（算 1 分）；tech = 一般科技公司（0.5 分，可配商业词）
ENTITIES = {
    # —— 国际 AI ——
    "OpenAI": (["OpenAI", "ChatGPT", "re:GPT[-‑ ]?\\d", "Sora", ("Codex", True), "Altman", "奥特曼", "奥尔特曼"], "intl", "ai"),
    "Anthropic": (["Anthropic", ("Claude", True), ("Opus", True), ("Sonnet", True), ("Haiku", True), "Amodei"], "intl", "ai"),
    "Google AI": (["DeepMind", ("Gemini", True), ("Gemma", True), ("Veo", True), "re:\\bGenie \\d|Project Genie",
                   "Hassabis", "AI Mode", "NotebookLM"], "intl", "ai"),
    "Microsoft AI": (["Copilot", "Azure AI", "MAI-", "Microsoft AI"], "intl", "ai"),
    "Meta AI": (["Meta AI", ("Llama", True), "Superintelligence Labs", "MSL"], "intl", "ai"),
    "xAI": ([("xAI", True), ("Grok", True), "SpaceXAI"], "intl", "ai"),
    "Mistral": ([("Mistral", True), "Mixtral", "Le Chat"], "intl", "ai"),
    "Apple Intelligence": (["Apple Intelligence", "Apple 智能", "Apple智能", ("Siri", True)], "intl", "ai"),
    "Amazon AI": (["Bedrock", "Trainium", "Alexa+", "Nova Act"], "intl", "ai"),
    "NVIDIA": (["Nvidia", "NVIDIA", "英伟达", "Jensen Huang", "黄仁勋", "Blackwell", ("CUDA", True)], "intl", "ai"),
    "AI 初创": (["Perplexity", "Hugging Face", "HuggingFace", "Midjourney", "ElevenLabs", "Scale AI", "Databricks",
               "CoreWeave", "Nscale", "Baseten", "Cerebras", ("Groq", True), "SambaNova", ("Cursor", True), "Anysphere",
               ("Replit", True), "Windsurf", ("Lovable", True), "Character.AI", "Thinking Machines", "Sutskever",
               ("Cohere", True), "Figure AI", ("Waymo", True), "Higgsfield", "ComfyUI", "Stability AI", "Runway ML",
               "Together AI", "OpenRouter", "LMArena", "Artificial Analysis"], "intl", "ai"),
    "芯片（国际）": (["TSMC", "台积电", "ASML", "阿斯麦", "SK Hynix", "SK海力士", "海力士", "Micron", "美光", ("AMD", True),
                  "Intel", "英特尔", "Qualcomm", "高通", "Broadcom", "博通", ("Arm", True), "Supermicro", "Foxconn",
                  "富士康", "Stargate", "星际之门", "Samsung Electronics", "三星电子"], "intl", "ai"),
    # —— 中国 AI ——
    "DeepSeek": (["DeepSeek", "深度求索", "梁文锋"], "cn", "ai"),
    "阿里通义": (["Qwen", "千问", "通义", "Tongyi", "阿里云", "Alibaba Cloud", "夸克"], "cn", "ai"),
    "月之暗面": (["Kimi", "月之暗面", "Moonshot AI", "杨植麟"], "cn", "ai"),
    "智谱": (["智谱", "Zhipu", ("Z.ai", True), ("GLM", True), "ZCode"], "cn", "ai"),
    "MiniMax": (["MiniMax", "稀宇", "海螺"], "cn", "ai"),
    "阶跃星辰": (["阶跃星辰", "StepFun", "阶跃"], "cn", "ai"),
    "字节 AI": (["豆包", "Doubao", "火山引擎", "Volcano Engine", "ByteDance Seed", "字节Seed", "字节 Seed", "Seedance",
               "Seedream", "即梦", "扣子", "Coze"], "cn", "ai"),
    "腾讯 AI": (["混元", "Hunyuan", "元宝", "Yuanbao", "WorkBuddy", "腾讯云"], "cn", "ai"),
    "百度 AI": (["文心", ("ERNIE", True), "文小言", "百度智能云", "萝卜快跑", "Apollo Go"], "cn", "ai"),
    "华为 AI": (["昇腾", "Ascend", "盘古", "华为云", "ADS 5", "乾崑"], "cn", "ai"),
    "小米 AI": (["MiMo", "小米大模型", "小爱"], "cn", "ai"),
    "蚂蚁 AI": (["inclusionAI", "百灵", "灵光", "蚂蚁数科"], "cn", "ai"),
    "其他中国 AI": (["商汤", "SenseTime", "科大讯飞", "讯飞", "iFlytek", "百川智能", "Baichuan", "零一万物", "面壁",
                 "MiniCPM", "LongCat", "可灵", ("Kling", True), "昆仑万维", "Skywork", "天工", "生数科技", "Vidu",
                 "智元", "AgiBot", "宇树", "Unitree", "王兴兴", "优必选", "UBTech", "银河通用", "地平线", "Horizon Robotics",
                 "智源", "BAAI", "上海人工智能实验室", "书生", "InternLM", "OpenCode", "Cheepseek"], "cn", "ai"),
    "中国芯片": (["寒武纪", "Cambricon", "摩尔线程", "Moore Threads", "壁仞", "沐曦", "海光", "燧原", "中芯国际", ("SMIC", True),
              "长鑫", "CXMT", "长江存储", "YMTC", "华虹", "龙芯"], "cn", "ai"),
    # —— 一般科技公司（国际）——
    "谷歌": (["Google", "谷歌", "Alphabet", "YouTube", "Pichai", "Waymo"], "intl", "tech"),
    "微软": (["Microsoft", "微软", "Nadella", "OneDrive", "Windows", "Azure", "GitHub"], "intl", "tech"),
    "Meta": ([("Meta", True), "Facebook", "Instagram", "WhatsApp", "Zuckerberg", "扎克伯格"], "intl", "tech"),
    "苹果": ([("Apple", True), "苹果", "iPhone", "iPad", "Tim Cook", "库克"], "intl", "tech"),
    "亚马逊": (["Amazon", "亚马逊", ("AWS", True)], "intl", "tech"),
    "马斯克系": (["Tesla", "特斯拉", "Musk", "马斯克", "SpaceX", "Optimus", "Starlink", "星链"], "intl", "tech"),
    "其他国际科技": (["Oracle", "甲骨文", ("IBM", True), "Salesforce", "ServiceNow", "Palantir", "SoftBank", "软银",
                  "Samsung", "三星", "Netflix", "Spotify", ("Reddit", True), ("Uber", True), "Shopify", ("Stripe", True),
                  "TikTok", "Okta", "Snowflake", ("Adobe", True), ("Figma", True), "Dell", "戴尔", "Binance", "币安",
                  "Polymarket", "Coinbase", "Electronic Arts", "Sony", "索尼", "Nasdaq", "纳斯达克", "Telegram",
                  "Booking", "Airbnb", "PayPal", "Robinhood", "Cisco", "思科", "Qualtrics", "Workday", "SAP",
                  "DoorDash", "Instacart", "Marvell", "Lumentum", "Kalshi", "Northflank", "Linode", "Akamai",
                  "Cloudflare"], "intl", "tech"),
    # —— 一般科技公司（中国）——
    "百度": (["百度", "Baidu", "李彦宏"], "cn", "tech"),
    "阿里": (["阿里巴巴", "阿里", "Alibaba", "淘宝", "天猫", "吴泳铭", "蔡崇信"], "cn", "tech"),
    "腾讯": (["腾讯", "Tencent", "微信", "WeChat", "马化腾"], "cn", "tech"),
    "字节": (["字节跳动", "字节", "ByteDance", "抖音", "Douyin"], "cn", "tech"),
    "华为": (["华为", "Huawei", "鸿蒙", "HarmonyOS", "余承东"], "cn", "tech"),
    "小米": (["小米", "Xiaomi", "雷军"], "cn", "tech"),
    "其他中国科技": (["美团", "Meituan", "快手", "Kuaishou", "京东", ("JD", True), "拼多多", ("PDD", True), "Temu", "蚂蚁集团",
                  "Ant Group", "网易", "NetEase", "联想", "Lenovo", "荣耀", ("OPPO", True), ("vivo", True), "理想汽车",
                  "小鹏", "XPeng", "蔚来", ("NIO", True), "比亚迪", ("BYD", True), "宁德时代", ("CATL", True), "大疆", ("DJI", True),
                  "滴滴", "携程", "赛力斯", "Shein", "希音", "中兴", "ZTE", "立讯", "工业富联"], "cn", "tech"),
}

BUSINESS = compile_terms([
    "funding", "raises", "raised", "raising", "valuation", "valued at", ("IPO", True), "prospectus", "S-1",
    "acquisition", "acquire", "acquires", "acquired", "merger", "earnings", "revenue", "profit", "guidance",
    "shares", "stock", "stocks", "market value", "market cap", "selloff", "sell-off", "investors", "capex",
    "capital expenditure", "layoffs", "job cuts", "startup", "start-up", "unicorn", "Series A", "Series B", "Series C",
    "debt", "bond", "credit rating", "buyback", "antitrust", "lawsuit", "deal", "plunge", "plunges", "tanks",
    "tumble", "tumbles", "slump", "slumps", "slides", "sinks", "soars", "surges", "jumps", "rally", "rout",
    "worst day", "record high", "outlook", "forecast", "spending", "investment",
    "融资", "估值", "re:(港股|美股|A股|科创板|创业板|纳斯达克|纽交所|挂牌|递表|赴港|冲刺|IPO).{0,4}上市|上市(首日|申请|计划|进程|公司)",
    "招股", "收购", "并购", "财报", "营收", "净利", "利润", "股价", "市值", "暴跌", "大涨", "裁员",
    "投资", "资本开支", "回购", "季报", "三季报", "初创", "独角兽", "A轮", "B轮", "C轮", "IPO", "破产", "亏损", "出货量",
    "跌超", "大跌", "重挫", "蒸发", "暴涨", "涨停", "跌停", "市场份额",
])

SECURITY = compile_terms([
    "hack", "hacked", "hackers", "heist", "breach", "breached", "stolen", "outage", "vulnerability", "exploit",
    "黑客", "被盗", "盗窃", "漏洞", "宕机", "攻击",
])

PROMO_RE = re.compile(r"(TechCrunch (Founder Summit|Disrupt|Sessions)|Save up to|Register now|last chance to|days left|"
                      r"早鸟票|报名开启|限时报名)", re.I)

LANG_EDU = compile_terms([
    "translation", "translator", "translators", "translate", "machine translation", "interpreting", "interpreter",
    "interpreters", "localization", "localisation", "multilingual", "language learning", "language learners",
    "Duolingo", "DeepL", "dubbing", "subtitles", "subtitling", "linguistic", "linguistics", "linguist",
    "education", "edtech", "students", "student", "teachers", "teacher", "school", "schools", "university",
    "universities", "college", "colleges", "classroom", "classrooms", "tutor", "tutoring", "homework", "exam",
    "exams", "academic", "academia", "plagiarism", "cheating", "literacy", "curriculum", "higher ed", "faculty",
    "learners", "pedagogy", "degree", "degrees", "accreditation", "researchers",
    "翻译", "机器翻译", "译者", "口译", "同传", "同声传译", "本地化", "多语言", "多语种", "语言学习", "外语", "英语学习",
    "多邻国", "配音", "字幕", "语言学", "教育", "教学", "教师", "老师", "学生", "课堂", "高校", "大学", "学校", "作业",
    "考试", "高考", "论文", "学术", "留学", "教培", "在线教育", "学而思", "好未来", "有道", "作业帮", "猿辅导", "新东方",
    "学习机", "院校", "职教", "科研",
])

POLICY = compile_terms([
    "regulation", "regulations", "regulator", "regulators", "regulatory", "AI Act", "executive order", "export control",
    "export controls", "entity list", "antitrust", "lawsuit", "sued", "sues", "court", "judge", "copyright",
    "privacy", ("FTC", True), ("DOJ", True), ("SEC", True), ("EU", True), "European Commission", "Congress", "Senate",
    "White House", "Trump", "legislation", "bill", "ban", "bans", "tariff", "tariffs", "sanction", "sanctions",
    "national security", "AISI", "safety institute", "midterms", "lawmakers", "policy", "governance",
    "监管", "法案", "立法", "行政令", "出口管制", "实体清单", "反垄断", "诉讼", "起诉", "法院", "版权", "隐私", "欧盟", "国会",
    "白宫", "特朗普", "网信办", "工信部", "发改委", "国务院", "备案", "禁令", "关税", "制裁", "国家安全", "政策", "标准",
    "市场监管", "治理",
])

TOPICS = {
    "模型发布": compile_terms(["release", "releases", "released", "launch", "launches", "launched", "unveil", "unveils",
                           "introduces", "introducing", "debut", "debuts", "rolls out", "open-sources", "open sources",
                           "now available", "new model", "arrives", "preview", "previews", "teases", "coming soon",
                           "next week", "open weight", "open-weight", "tops", "预告", "发布", "推出", "上线", "开源", "亮相",
                           "首发", "官宣", "上新", "登顶", "即将"]),
    "价格套餐": compile_terms(["price", "prices", "pricing", "cheaper", "discount", "subscription", "subscriptions",
                           "tier", "tiers", "per million tokens", "rate limit", "usage limits", "price cut",
                           "降价", "价格", "免费", "订阅", "套餐", "额度", "会员", "定价", "限额", "涨价"]),
    "融资上市": compile_terms(["funding", "raises", "raised", "valuation", ("IPO", True), "prospectus", "S-1", "round",
                           "investors", "融资", "估值", "re:(港股|美股|A股|科创板|挂牌|递表|赴港|IPO).{0,4}上市", "招股", "IPO", "轮"]),
    "财报股市": compile_terms(["earnings", "revenue", "profit", "stock", "stocks", "shares", "market value", "selloff",
                           "sell-off", "capex", "Nasdaq", "财报", "营收", "净利", "股价", "市值", "暴跌", "资本开支", "美股", "季报"]),
    "算力芯片": compile_terms([("GPU", True), ("GPUs", True), ("TPU", True), ("HBM", True), "chip", "chips", "semiconductor",
                           "data center", "data centers", "datacenter", "DRAM", "memory", "foundry", "compute",
                           "芯片", "半导体", "算力", "数据中心", "内存", "存储", "晶圆", "光刻", "服务器", "智算"]),
    "政策监管": POLICY,
    "编程智能体": compile_terms(["agent", "agents", "agentic", "coding", "code", "developer", "developers", "Copilot",
                            "Cursor", "Claude Code", "Codex", "智能体", "Agent", "编程", "代码", "开发者"]),
    "机器人驾驶": compile_terms(["robot", "robots", "robotics", "humanoid", "robotaxi", "self-driving", "autonomous",
                            "机器人", "人形", "具身", "自动驾驶", "智驾", "无人驾驶"]),
    "研究论文": compile_terms(["paper", "papers", "arXiv", "study", "researchers", "research", "benchmark", "benchmarks",
                           "论文", "研究", "基准", "评测", "科研"]),
    "安全风险": compile_terms(["safety", "alignment", "jailbreak", "misuse", "hack", "hacked", "hackers", "security",
                           "vulnerability", "malicious", "breach", "安全", "对齐", "越狱", "漏洞", "黑客", "恶意", "攻击"]),
    "语言教育": LANG_EDU,
}

MODEL_WORDS = compile_terms([
    "model", "models", ("LLM", True), "weights", "open-weight", "open weights", "checkpoint", "模型", "大模型", "权重",
    "re:GPT[-‑ ]?\\d", ("Gemini", True), ("Claude", True), ("Qwen", True), ("DeepSeek", True), ("Kimi", True), ("GLM", True),
    ("MiniMax", True), ("Llama", True), ("Mistral", True), ("Grok", True), ("Gemma", True), ("MiMo", True), "混元", "文心", "豆包",
])

DEAL_PRICE = re.compile(r"(\d+(?:\.\d+)?\s*(?:万元|元|块)|¥\s*\d+|\d+\s*→\s*\d+)")
DEAL_WORDS = re.compile(r"(到手|券后|直降|新低|国补|限时|特惠|免息|开售|发售|上架|预售|立减|秒杀|低至|包邮|补贴价|首发价|权益价|"
                        r"闭眼囤|再降价|京东|天猫|拼多多百亿|起售|售价|交付)")
ROUNDUP_RE = re.compile(r"(\d+点\d+氪|早报|晚报|日报|周报|晨报|夜报|快报|早知道|速览|一周|盘点|汇总|Roundup|Round-up|Recap|Digest|"
                        r"This Week in|Market Talk|The Download)", re.I)


ENTITY_RX = {label: (compile_terms(pats), region, kind) for label, (pats, region, kind) in ENTITIES.items()}


def hits(rx_list, text):
    return [term for term, rx in rx_list if rx.search(text)]


def analyze(item: dict) -> dict:
    title = item["title"] or ""
    summary = item["summary"] or ""
    extra_txt = " ".join(item.get("extra", {}).get("topics") or []) + " " + " ".join(item.get("extra", {}).get("ai_keywords") or [])
    text = f"{title} \n {summary} {extra_txt}"

    strong = hits(AI_STRONG, text)
    weak = [w for w in hits(AI_WEAK, text) if w not in strong]
    title_strong = hits(AI_STRONG, title)
    title_weak = [w for w in hits(AI_WEAK, title) if w not in title_strong]
    ents = {"cn": [], "intl": []}
    ai_ents, tech_ents, title_ai_ents, title_tech_ents = [], [], [], []
    region_score = Counter()
    region_title = Counter()
    for label, (rx, region, kind) in ENTITY_RX.items():
        t_hit = any(r.search(title) for _, r in rx)
        s_hit = t_hit or any(r.search(text) for _, r in rx)
        if not s_hit:
            continue
        ents[region].append(label)
        (ai_ents if kind == "ai" else tech_ents).append(label)
        if t_hit:
            (title_ai_ents if kind == "ai" else title_tech_ents).append(label)
        region_score[region] += (2 if t_hit else 1) * (1.0 if kind == "ai" else 0.7)
        if t_hit:
            region_title[region] += 1.0 if kind == "ai" else 0.7
    ai_score = round(min(len(strong), 3) * 1.0 + min(len(weak), 3) * 0.4 + min(len(ai_ents), 3) * 1.0
                     + min(len(tech_ents), 2) * 0.3, 2)
    biz = hits(BUSINESS, text)
    sec = hits(SECURITY, title + " " + summary[:300])
    biz_title = hits(BUSINESS, title)
    sec_title = hits(SECURITY, title)
    pol_title = hits(POLICY, title)
    policy = hits(POLICY, text)
    # 科技商业：标题里有科技公司，或者摘要里有科技公司、标题里有商业／安全词（如 "$6.3bn heist"）
    tech_biz = bool(title_tech_ents and (biz or sec or policy)) or bool(tech_ents and (biz_title or sec_title))
    langedu = hits(LANG_EDU, text)
    langedu_title = hits(LANG_EDU, title)
    head = title + " " + summary[:300]
    topics = [name for name, rx in TOPICS.items() if hits(rx, head)]
    # "模型发布"要求同时提到模型（模型、权重、型号名等），否则"发布""上线"太宽
    if "模型发布" in topics and not (hits(MODEL_WORDS, head) or title_ai_ents):
        topics.remove("模型发布")
    # 只看标题的主题标签（中外对照用；摘要里顺带提到的不算）
    topics_title = [name for name, rx in TOPICS.items() if hits(rx, title)]
    if "模型发布" in topics_title and not (hits(MODEL_WORDS, title) or title_ai_ents):
        topics_title.remove("模型发布")

    if region_score:
        top = region_score.most_common()
        subject = top[0][0] if len(top) == 1 or top[0][1] > top[1][1] else "mixed"
    else:
        subject = "none"
    # 只按标题里的公司判断的主体（更可靠，中外对照用这个）
    if region_title:
        tt = region_title.most_common()
        subject_title = tt[0][0] if len(tt) == 1 or tt[0][1] > tt[1][1] else "mixed"
    else:
        subject_title = "none"
    # 是否 AI 相关：标题里有 AI 词或 AI 实体（或 2 个弱词）；只在摘要里出现时，要有 2 个以上不同的强词／实体。
    # 综合媒体的长摘要常顺带提一句 AI（如"支持 AI 人形侦测"的门铃），只看摘要会放进很多数码稿。
    is_ai = (bool(title_strong or title_ai_ents) or len(title_weak) >= 2
             or len(set(strong) | set(ai_ents)) >= 2)
    # 语言教育题：标题里有核心词，或摘要里有 3 个以上不同的核心词（摘要里零星出现的"翻译""学术"不算）
    langedu_core = _langedu_core(langedu_title) or len(set(h for h in langedu if h in LANGEDU_CORE)) >= 3
    src_focus = bool(item["extra"].get("ai_focused")) or item["layer"] == "social"
    if (is_ai or src_focus) and (langedu_core or item["layer"] == "lang_edu"):
        relevance = "lang_edu"
    elif is_ai:
        relevance = "ai"
    elif tech_biz:
        relevance = "tech_business"
    elif src_focus:
        relevance = "ai"          # 来源专讲 AI（如每日论文、AINews），没命中词表也按 AI 算
    else:
        relevance = "tech_business" if (title_weak and (biz or policy)) else "other"
    topics = [t for t in topics if t != "语言教育"]
    if relevance == "lang_edu":
        topics.append("语言教育")
    # 汇总稿：来源标了 roundup，或标题像早报／周报，或标题用分号串了三件以上的事
    editorial = item["layer"] in ("media_cn", "media_intl", "aggregator", "lang_edu")
    roundup = (bool(item["extra"].get("roundup"))
               or (editorial and (bool(ROUNDUP_RE.search(title)) or len(re.findall(r"[；;]", title)) >= 2)))
    return {"is_ai": is_ai, "title_ai": bool(title_strong or title_ai_ents), "tech_biz": tech_biz,
            "title_strong": title_strong, "title_ai_entities": title_ai_ents,
            "title_weak": title_weak, "policy_title": pol_title,
            "strong": strong, "weak": weak, "ai_entities": ai_ents, "tech_entities": tech_ents, "entities": ents,
            "business": biz, "security": sec, "lang_edu": langedu, "policy": policy, "topics": topics, "ai_score": ai_score,
            "subject_region": subject, "subject_region_title": subject_title, "topics_title": topics_title, "relevance": relevance, "roundup": roundup}


def _langedu_core(langedu_hits) -> bool:
    """"学生""大学"这类词太宽，单独出现不算语言教育题；翻译、语言学习、教育、课堂等核心词出现才算。"""
    return any(h in LANGEDU_CORE for h in langedu_hits)


LANGEDU_CORE = {"translation", "translator", "translators", "translate", "machine translation", "interpreting",
            "interpreter", "interpreters", "localization", "localisation", "multilingual", "language learning",
            "language learners", "Duolingo", "DeepL", "dubbing", "subtitles", "subtitling", "linguistic",
            "linguistics", "linguist", "education", "edtech", "teachers", "teacher", "classroom", "classrooms",
            "tutor", "tutoring", "homework", "plagiarism", "cheating", "literacy", "curriculum", "higher ed",
            "pedagogy", "accreditation", "翻译", "机器翻译", "译者", "口译", "同传", "同声传译", "本地化", "多语言", "多语种",
            "语言学习", "外语", "英语学习", "多邻国", "配音", "字幕", "语言学", "教育", "教学", "教师", "课堂", "高考",
            "学术", "教培", "在线教育", "学而思", "好未来", "有道", "作业帮", "猿辅导", "新东方", "学习机", "职教"}


def decide(item: dict, a: dict) -> tuple:
    """返回 (是否保留, 理由类别, 细节)。理由写成 "保留｜类别｜细节"。"""
    src_focus = bool(item["extra"].get("ai_focused")) or item["layer"] == "social"
    title = item["title"] or ""
    found = []
    if a["strong"]:
        found.append("AI 词 " + "、".join(a["strong"][:4]))
    if a["ai_entities"]:
        found.append("AI 实体 " + "、".join(a["ai_entities"][:4]))
    if a["weak"]:
        found.append("弱词 " + "、".join(a["weak"][:3]))
    if a["tech_entities"]:
        found.append("科技公司 " + "、".join(a["tech_entities"][:3]))
    if a["business"]:
        found.append("商业词 " + "、".join(a["business"][:2]))
    if a["security"] or a["policy"]:
        found.append("安全／政策词 " + "、".join((a["security"] + a["policy"])[:2]))
    found_s = "；".join(found) if found else "未命中词表"

    if PROMO_RE.search(title):
        return False, "活动广告", "会议报名、门票促销"
    if src_focus:
        return True, ("AINews 社交信号，默认保留" if item["layer"] == "social" else "来源专注 AI，默认保留"), found_s
    if DEAL_PRICE.search(title) and DEAL_WORDS.search(title) and len(a["title_strong"]) + len(a["title_ai_entities"]) < 2:
        return False, "导购促销", "标题有价格和促销词；" + found_s
    if a["is_ai"]:
        return True, "AI 相关", ("标题命中；" if a["title_ai"] else "摘要多处命中；") + found_s
    if a["tech_biz"]:
        return True, ("科技商业" if a["business"] else "科技商业（安全／政策）"), found_s
    if a["title_weak"] and (a["business"] or a["policy"]) and item["layer"] in ("media_intl", "media_cn"):
        return True, "宽松：标题弱词＋商业／政策词", found_s
    return False, "未命中 AI／科技商业词表", ("只在摘要里零星提到 AI；" if (a["strong"] or a["ai_entities"]) else "") + found_s


def split_roundup(item: dict) -> list:
    """只拆中文媒体用分号串起来的早报标题；英文汇总稿不拆，归并时只记"提及"。"""
    if item["layer"] != "media_cn":
        return []
    head = re.sub(r"^\d+点\d+氪[丨|｜]\s*", "", item["title"])
    head = re.sub(r"[丨|｜]\s*极客早知道\s*$", "", head)
    parts = [p.strip(" ，,。") for p in re.split(r"[；;]", head)]
    parts = [p for p in parts if len(p) >= 6]
    return parts if len(parts) >= 2 else []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    args = ap.parse_args()
    base = run_dir(args.day) / "01_获取"
    items = read_jsonl(base / "raw.jsonl")
    out = []
    for it in items:
        a = analyze(it)
        parts = split_roundup(it) if a["roundup"] else []
        if parts:
            # 中文早报（如"9点1氪丨A；B；C""A；B；C｜极客早知道"）拆成几条子条目，各自粗筛、各自参与归并
            it["pf"] = {"keep": False, "reason": f"剔除｜汇总稿已拆分｜拆成 {len(parts)} 条子条目分别粗筛",
                        "reason_type": "汇总稿已拆分", **a}
            out.append(it)
            for k, part in enumerate(parts, 1):
                sub = copy.deepcopy(it)
                sub.pop("pf")
                sub["id"] = f"{it['id']}#{k}"
                sub["title"], sub["summary"] = part, ""
                sub["extra"]["split_from"] = it["title"]
                sub["extra"].pop("dup_sources", None)
                sa = analyze(sub)
                sa["roundup"] = False
                keep, cat, detail = decide(sub, sa)
                sub["pf"] = {"keep": keep, "reason": f"{'保留' if keep else '剔除'}｜{cat}｜{detail}（拆自汇总稿）",
                             "reason_type": cat, **sa}
                out.append(sub)
            continue
        keep, cat, detail = decide(it, a)
        it["pf"] = {"keep": keep, "reason": f"{'保留' if keep else '剔除'}｜{cat}｜{detail}", "reason_type": cat, **a}
        out.append(it)
    write_jsonl(base / "prefilter.jsonl", out)
    write_report(base, out, args.day)
    n_keep = sum(it["pf"]["keep"] for it in out)
    print(f"粗筛：{len(out)} 条 → 保留 {n_keep}，剔除 {len(out) - n_keep}")
    print(f"写入 {base / 'prefilter.jsonl'}")


def write_report(base, items, day):
    kept = [i for i in items if i["pf"]["keep"]]
    by_src = defaultdict(lambda: [0, 0, []])
    for it in items:
        row = by_src[(it["layer"], it["source_name"])]
        row[0 if it["pf"]["keep"] else 1] += 1
        if not it["pf"]["keep"]:
            row[2].append(it["title"])
    reasons = Counter(("保留·" if i["pf"]["keep"] else "剔除·") + i["pf"]["reason_type"] for i in items)
    rel = Counter(i["pf"]["relevance"] for i in kept)
    subj = Counter(i["pf"]["subject_region"] for i in kept)
    topics = Counter(t for i in kept for t in i["pf"]["topics"])
    L = [f"# 粗筛统计 · {day}", "",
         f"- 输入 {len(items)} 条，保留 **{len(kept)}** 条，剔除 {len(items) - len(kept)} 条。规则见 pipeline/prefilter.py 文件头。",
         "- 理由分布：" + "；".join(f"{k} {v}" for k, v in reasons.most_common()),
         "- 保留条目的相关度：" + "，".join(f"{k} {v}" for k, v in rel.most_common())
         + "（ai = AI 相关；lang_edu = AI × 语言／翻译／教育；tech_business = 只命中科技商业；other = 来源专注 AI 但没命中词表）",
         "- 保留条目的主体地区（按实体）：" + "，".join(f"{k} {v}" for k, v in subj.most_common()),
         "- 保留条目的主题标签：" + "，".join(f"{k} {v}" for k, v in topics.most_common()),
         "", "## 各来源保留／剔除", "",
         "| 层级 | 来源 | 保留 | 剔除 | 被剔除的标题（前 4 条，供检查是否误杀） |", "|---|---|---:|---:|---|"]
    order = list(LAYER_LABELS)
    for (layer, name), (k, d, dropped) in sorted(by_src.items(), key=lambda x: (order.index(x[0][0]), -x[1][0])):
        L.append(f"| {LAYER_LABELS[layer]} | {md_escape(name)} | {k} | {d} | {md_escape('；'.join(t[:40] for t in dropped[:4]))} |")
    (base / "粗筛统计.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
