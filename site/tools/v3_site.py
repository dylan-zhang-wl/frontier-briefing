# -*- coding: utf-8 -*-
"""网页 v3 的全站设置（每一期都一样的东西）。由 site/tools/build_v3.py 读取。

改这里的任何一行，重新组装一次，整站就跟着变；不用动网页代码。
"""

# ---------------------------------------------------------------- 刊名
NAME_ZH = "每日AI科技前沿简报"
# 英文全名和简称（10-31 已定）；以后要改，只改这两行
NAME_EN = "Daily AI & Tech Frontier Briefing"
NAME_EN_SHORT = "Frontier Briefing"

# ---------------------------------------------------------------- 正文字体（只一个开关，页面上不放切换按钮）
# "kai"  霞鹜文楷·屏幕阅读版（默认）：组装时按这一期用到的字截成小字体包
# "song" 思源宋体（Noto Serif SC 常规体）：同样截成小字体包
# "hei"  系统黑体（苹方等）：不下载任何正文字体
BODY_FONT = "kai"

# ---------------------------------------------------------------- 每天的主题色（每期配置里的 THEME 从这里挑一个）
# 只是一小撮颜色，避开绿色和青色；具体色值写在 site/v3/style.css 里（浅色、深色两套，都按 WCAG AA 核过对比度）。
# 用在当前页签、链接、图表重点、背景色团，以及 v3.1 起背景那层点和细线（10-31 用户确认：主题色仍按当天主线变，不固定成海蓝）。
ACCENTS = {
    "blue": "海蓝",     # 新模型、新产品为主的一天
    "amber": "琥珀",    # 资本、钱、市场为主的一天
    "coral": "珊瑚",    # 安全、风险、争议为主的一天
    "violet": "紫",     # 研究、学术、长线趋势为主的一天
}
ACCENTS_EN = {"blue": "ocean blue", "amber": "amber", "coral": "coral", "violet": "violet"}   # 英文页脚里的颜色名

# ---------------------------------------------------------------- 页脚（v3.2：一行话，只在这里改）
# {accent} 换成当天主题色的名字；{past} 换成“往期”按钮（点开日历）。中文页面用 FOOT_ZH，英文页面用 FOOT_EN。
FOOT_ZH = "本期由 AI 自动化工作流生成 · 主题色：{accent} · {past} · 每日AI科技前沿简报"
FOOT_EN = "Produced by an automated AI workflow · Colour: {accent} · {past} · Daily AI & Tech Frontier Briefing"
FOOT_PAST = ("往期", "Past issues")      # {past} 那个按钮上的字

# 配乐署名（v3.2）：CC BY 4.0 不管商用与否都要求署名，但允许放在合理的位置：11-01 用户定放进折叠的“参考来源”末尾。
# Lyria 生成的乐句不需要署名。11-03 起 build_v3.py 按这一期播客实际用的声音包自动写（播客 qc.json → usage.json → 默认 包.json；
# 中英文措辞取 video3_music.CREDITS），下面这一行只在哪儿都查不到声音包时兜底，换声音包不用改这里。
MUSIC_CREDIT = ("配乐：Scott Buckley《Castles in the Sky》（CC BY 4.0，经剪辑）",
                "Music: ‘Castles in the Sky’ by Scott Buckley, CC BY 4.0 (edited)")
# 配图由 AI 生成的说明（v3.2）：页面上的图不再挂“AI 生成配图”小标签，改在折叠的“参考来源”末尾、和配乐署名放在一起写一次
IMAGE_CREDIT = ("配图由 AI 生成", "Images are AI-generated")
IMAGE_CREDIT_WITH_VIDEO = ("配图由 AI 生成（视频里的场景图也是）", "Images are AI-generated, including the scenes in the video")
# 视频画面里用了公司标志、但视频数据没给现成说明时，用这一句（不逐个列标志和许可证）
LOGO_CREDIT = ("画面中的公司标志取自 Simple Icons（CC0）与 Wikimedia Commons（公有领域字标），仅作单色处理；商标归各自所有者，仅用于指称。",
               "Company logos come from Simple Icons (CC0) and Wikimedia Commons (public-domain wordmarks), shown in one colour; trademarks belong to their owners and are used only to identify them.")

# ---------------------------------------------------------------- 头条、要闻的配图版式（v3.2）
# 每条按“日期＋条目号”的哈希从下面挑一种（重新组装结果不变），相邻两条不重复；手机上一律“图在上、字在下”。
# 不喜欢哪一种，从名单里删掉那一行即可（至少留两种，才能做到相邻不重复）。
LAYOUTS = [
    "split-l",   # 图在左（宽），文字在右
    "split-r",   # 文字在左（宽），图在右，图裁成 4:3
    "glass",     # 图铺满整块做底，标题和导语放在一块毛玻璃上
    "wide",      # 宽幅图在上（约 21:8），下面左文右栏
    "inset",     # 图放进带边框的小画框，图注错开压在画框一角，文字在右
]

# ---------------------------------------------------------------- 国内外对照的关系词表（v3.2）
# 每一对在每期配置 PAIRS 里写 relation="竞争"（或网页稿 related 里写 relation），页面中间画对应的小动画，
# 下面配“我们的理解”那一句。没写或写了词表外的词，按“呼应”。键是规范写法，alias 里的写法也认。
# key 是动画的名字（app.js / style.css 里用），label_zh / en 是页面上的小字。
RELATIONS = {
    "呼应": dict(key="echo", label_zh="呼应", en="Echo", alias=("相互呼应",),
               def_zh="两边各自发生、方向一致，彼此印证；没有谁带动谁。"),
    "竞争（良性）": dict(key="race", label_zh="良性竞争", en="Rivalry", alias=("竞争", "良性竞争", "competition"),
                   def_zh="同一条赛道上各拼各的长处，比的是谁做得更好，不是谁压倒谁。"),
    "对抗": dict(key="clash", label_zh="对抗", en="Clash", alias=("冲突", "confrontation"),
               def_zh="立场或利益正面冲突，一方的得就是另一方的失（如制裁与反制、诉讼）。"),
    "合作": dict(key="link", label_zh="合作", en="Partnership", alias=("cooperation",),
               def_zh="双方直接联手：合资、授权、接入、供货等有明确协议的关系。"),
    "拉锯": dict(key="tug", label_zh="拉锯", en="Tug-of-war", alias=("tug",),
               def_zh="来回较劲、互有进退，短期内分不出胜负（如谈判、监管与企业之间）。"),
    "互补": dict(key="fit", label_zh="互补", en="Complement", alias=("complement",),
               def_zh="一边缺的正是另一边有的，合起来才是完整的图景（如供给一侧与需求一侧）。"),
    "跟进": dict(key="follow", label_zh="跟进", en="Follow", alias=("follow",),
               def_zh="一方已经走出一步，另一方随后走上同一条路；只按先后说，不断言因果。"),
    "分化": dict(key="split", label_zh="分化", en="Divergence", alias=("divergence",),
               def_zh="起点相近、走向分开：同一个问题，两边给出不同的答案或路线。"),
}

# ---------------------------------------------------------------- 周末两版的版面（11-01 晚定，见 文档/方案/周末版与声音规范.md）
# 网页稿 sections 里有 kind 为 "deep" 的一条（深度／深谈那一题）时，周六按 "sat"、周日按 "sun" 排版；工作日不受影响。
# 从上到下：
#   周六：今日深度卡（深度题标题、一句话、"听深度"、下面两三条快讯标题）→ 今日数字 → 看与听 → 快讯 → 深度（层、名词解释）
#         → 预告看板 → 参考来源
#   周日：本周深谈卡（大标题、核心问题、一句话结论、"听深谈"）→ 看与听 → 本周深谈（五层、时间线、关键数字、名词解释）
#         → 本周快讯 → 接下来看什么 → 参考来源。不单列今日数字：关键数字放进深谈各层
# 两天都没有"今日一词"：改成深度／深谈版块里折叠的"名词解释"（周六播客没有今日一词这一章）。
WEEKEND = {
    "sat": {"numbers_max": 4,        # 今日数字最多几格（从快讯和深度里取）
            "card_flash_max": 3},    # 今日深度卡下面列几条快讯标题
    "sun": {"numbers_max": 0},       # 0 = 不单列今日数字
}
LAYER_NUMBERS_MAX = 3                # 深度／深谈每一层下面最多几个关键数字
GLOSSARY_RANGE = (3, 5)              # 名词解释收几个词（少于、多于都只提醒，页面照常）

# ---------------------------------------------------------------- 其他
SITE_HOST = "frontier.wenlongzhang.com"
FONT_CACHE = "~/.cache/frontier-daily/fonts"   # 原字体只下载一次，放在 iCloud 之外
FONT_FILES = {                                  # 都是 SIL OFL 开源许可，可截取后随网页分发
    "title_700": "NotoSerifSC-Bold.otf",        # 标题（粗）：思源宋体，notofonts/noto-cjk 官方仓库
    "title_900": "NotoSerifSC-Black.otf",       # 刊名、版块大标题（特粗）
    "song_400": "NotoSerifSC-Regular.otf",      # 只有 BODY_FONT = "song" 时才用
    "kai_400": "LXGWWenKaiScreen.ttf",          # 正文楷体：lxgw/LxgwWenKai-Screen 官方发布 v1.530
    "display_400": "InstrumentSerif-Regular.ttf",   # 英文刊名、大数字：google/fonts 官方仓库
    "display_400i": "InstrumentSerif-Italic.ttf",
    "latin_400": "Tinos-Regular.ttf",           # 本机没有 Times New Roman 时的同尺寸替代（安卓等）
    "latin_700": "Tinos-Bold.ttf",
    "latin_400i": "Tinos-Italic.ttf",
}
