# 视频 v3「今日地图」：怎么出一期、怎么加一个画面模板

## 出一期

```bash
PY=~/.venvs/frontier-daily/bin/python
$PY site/tools/video3_build.py --day 2026-11-01            # 读分镜 → 核对 → 配音（只配改过的章）→ 配乐、对齐 → 写 11_视频v3/
node site/tools/video3_record.mjs 测试版/2026-11-01         # 预览.mp4 ＋ 关键帧总览.jpg（--dark 出深色版）
```

- 每期只要一份分镜：`测试版/<日期>/04_文稿/视频v3_分镜.json`。写法、格式、模板目录都在 `pipeline/prompts/写稿_视频v3.md`；10-31 那份是范例（冻结作参照）。
- 组装脚本先核对再花钱：事实（`facts` 的 check 要逐字在事件卡里）、画面上的每个数字、每个触发词、章的结构，有一样不对就停，不配音。数据不够画的模板只去掉并提醒。
- 配音用的 `04_文稿/视频旁白_v3.md` 由分镜生成；旁白改了会自动重配，没改的章直接用配音缓存。声音从 `pipeline/voice_profile.json` 读（庚A）。
- 网页那边只读 `11_视频v3/video3_media.json`（章、热点、配图、音频、配乐署名），格式不变；v3.3 起多了 `logos`（嵌好的标志）和 `credits`（`credits.lines` 是要在折叠的"参考来源"里显示的几行：配乐署名、"视频配图由 AI 生成（资料图除外：…）"、标志来源）。

## 画面里的真东西（v3.3）

- **标志小签**：库在 `site/assets/logos/`（`来源.json` 记每个标志的来源、许可、取得日期）。缺哪个用 `site/tools/video3_logos.py` 加：先 `si-search` 查 Simple Icons，有就 `add-si`；没有再到 Wikimedia Commons 找公有领域字标（PD-textlogo）或 CC 许可的，`add-commons`；都没有就 `add-text` 登记成文字小签。加完 `preview 输出.html` 出一页对照，看单色化以后标志有没有糊成一块（比如 7-Eleven 的彩色叠层标志单色后中间的字会被填实，所以登记成了文字小签）。Simple Icons 里有同名 slug 的，分镜里直接写也会自动取来。标志只按字色／主题色整块上色（CSS 遮罩），只裁四周空白，不改形状。
- **配图**：分镜顶层写 `image_requests`，缺的图构建时生成到 `06_配图/视频/`（本机先 agy、没成再 Codex；云端不装 agy，只用 Codex；`FD_IMAGE_BACKENDS=codex` 只用 Codex）（也可以先单独跑 `$PY site/tools/video3_images.py --day 日期`，`--redo <id>` 重画一张）；`commons` 写法取资料图。生成失败的那块不带图，版式和时间不变。`--no-gen` 不生成。
- **帖子／节目卡** `post_card`：平台、日期、原话都对事件卡；平台核不上只标"原话"，英文不是逐字原话就按转述显示（不加引号）。
- 画面里不挂"AI 生成配图""资料图"小标。画面检查见下一节（11-06 改准，原来是"只有字卡或标题超过约 6 秒"）。英文名以 `pipeline/prompts/英文名表.yaml` 为准（有就读：标志小签的英文名按它，分镜英文字和它对不上会提醒）。

## 11-06 版式修理（画面检查、四个模板、计数模板）

- **画面检查**（`video3_storyboard.py` 的 `screen_model` / `check_screen` / `check_gaps`，都只提醒）：按"画面上真有东西"算——配图、标志、计数模板的美国轮廓从出现到模板下场都算；关系模板的动效只算每个触发词后 `SCREEN_HOLD`（4 秒）；只剩线和点的时间轴、空玻璃柱、白卡上的字不算；"这一刻镜头在哪个模板"按最近一个说到的触发词算，所以认得"时间轴 → 对比卡 → 再回到时间轴"这种穿插。单段空档超过 `SCREEN_GAP`（4 秒）、章首 `OPENER_SEC`（3 秒）内没有主角、时间轴被打断都提醒；另查旁白里的数字和等级有没有上画面（`check_spoken_facts`）、一期配图张数（`check_image_budget`；配图不设固定张数，张数上限已去掉，只查时间轴一条最多 3 张小图）。
  - 第 7 步：总调度只调 `check_relations`，所以 `check_screen` 挂在它后面，时间用 `estimate_timing` 按字数估（和 `video3_preview.py` 同一套）；
  - 第 14 步、无声样片：`check_gaps` 按实际对齐的时间再查一遍；`compile_chapters` 把空档写进 `video3_media.json` 每章的 `blank`，`video3_record.mjs --sheet` 据此在关键帧总览里多截几格（标红"空档"）。
- **原话卡头像**（`post_card` 的 `who.logo`）：方形的图形标放进圆里，横长的字标改成胶囊、宽度跟着标志走，头像一律裁边；规则在 `video3.js` 的 `AV`/`avatarFit` 和 `video3_logos.py` 的 `AVATAR`/`avatar_fit`（同一组数，测试逐个标志核不溢出）。
- **要点卡**（`quote_card`）：出处和标志合成卡片顶上一行（出处里已有公司名时标志只放图形）；短句自动放大、卡片压矮、镜头退远；可带 `image`（左图右字）。`video3_build.prep_photos` 不认得这个图位，由 `compile_chapters` 里的 `ensure_photo` 补上（同一张图已备过就共用），写进同一个 `images`，网页那边照样会拷。
- **时间轴**（`timeline`）：每个日子可挂 `logos` 和一张小图 `image`（一条轴最多 3 张）；日子按"下一个别的模板什么时候开始"分段（`tlSegments`），标签留到这一段结束，被打断后再说到下一个日子时前面的标签重新出来、镜头飞回整条轴（修掉了"周四"标签从 28 秒挂到片尾）。
- **柱状图**（`column_compare`）：玻璃 1.62 贴着实心柱 1.3（原来 2.2 对 1.3），只描正面的框（`W.outlineFront`），玻璃和芯一起在说到这个数时长出来；标题旁的 `head_logos` 画出来了；滚动的数字保留 %（`emph` 里只滚内层那个数）。
- **计数模板**（`tally`，新）：美国本土轮廓＋大字"N 个州"＋M 格方阵，说到"除了几项"时 M−k 格亮、k 格灰；只点亮分镜点了名、又和计数出自同一条事件卡原文的州（`check_tally`，核不上和数字一样停）；颜色中性（字色和灰，不用红蓝）。没有州界数据时退成大字＋方阵。

### 11-06 白天、晚上补的字段和行为（都只在分镜用到时才起作用，往期分镜不受影响）

- **刻度尺 `scale` 的 `open_top: true`**（白天）：材料没说最上面那档就是顶格时写。播放器不画玻璃体的顶面、描边不画顶面四条棱，四条竖棱往上接三小段虚线；`head` 或 `status` 同时写明是谁的框架。另：`from.at`/`to.at` 是档位序号（0 是最上面那档），往上升（如 High 第 1 档 → Critical 第 0 档）也画得对了（`video3.js` 的 `scAt`）；`video3_storyboard.strip_labels` 编数据时留着数字 `at`，只删触发词那种 `at`。
- **时间轴小图停留**（白天，`video3.js` 的 `tlImageHold`，常数 `TL_IMG_HOLD` = 1.8、`TL_IMG_ZOOM` = 1.7）：时间轴日子上的小图 `ticks[].image` 弹出后，镜头至少在时间轴上停 1.8 秒，下一个模板那一镜往后顺延（不越过再后面一镜）；小图弹出时先放大到 1.7 倍（从下沿往上长，不挤别的字），镜头起飞时缩回原大。11-06 选票章"本周中期选举"那张投票站图原来一闪就飞走。
- **国内外 `split` 小卡带题图**（晚上）：`left_items[]`/`right_items[]` 每项可写 `image`（网页图文件名或 `image_requests` 的 id）。`compile_chapters` 用 `ensure_photo` 备图（键 `<块 id>.left_items0` 这样，宽 800），播放器把图放在小卡上半截、字在下半截、慢推；带图的小卡从锚点往下长（锚点是卡片上沿，y 4.6，`align: 't'`），不压两边标题下面的标志；竖屏时带图小卡收窄到 17u、图压扁到 16:7。检查一侧：`IMAGE_SLOTS["split"]`、`structure` 找不到图只去掉图、`photo_moments` 算"清楚露脸"、`screen_model` 从说到这一项起算"有画面"。两边标题的 `left.logos`/`right.logos` 原来就能挂；标题按 `left`/`right` 触发词出现，想让它随地图对折出来（开口 3 秒内有主角），触发词写 `{"say": "国内外", "offset": 1.5}`、`{…, "offset": 1.9}`（偏移别小于 1.4，镜头到位前出来会贴顶）。
- **"接下来" `next` 每一项挂标志**（晚上）：`items[].logos`，放在字的上面一行，说到这一项时弹出（`LOGO_SLOTS["next"]`；公司名要在这一项的字或 `ref` 指的事件卡原文里，否则不挂）。
- **要点卡压在路尽头的配图上 `over_photo: true`**（晚上，`quote_card`）：紧跟在 `fork` 后面、这一章有立在路尽头的 `image_card` 时，卡片不站在路的一头，改立在那张配图正前方 0.9 处，卡片稍宽（8.4×2.7）、字小一号（`.v3qc.over`），镜头正对配图装下整张图（`W.buildChapter` 末尾、`TPL.quote_card.build`）。没有立在路尽头的配图时照旧。检查一侧：`fork_photo(c)` 成立时算"有图"（`_moments` 的 `over_ok`）。11-06 开放权重章"研发成本 3200 万美元"就是这样压在 v_code 上。
- **新提醒（第 7 步，只提醒、不拦）**：
  - `check_voice_openings`：旁白每章单独配一次音，章首开口是英文名、后面只隔三个以内的汉字又接英文（11-06"Ricursive Intelligence，发布了""GPT-6 Cyber 在 OpenAI"）→ 提醒改中文起句；判断在 `pipeline/lexicon_check.py` 的 `opening_problem`（第 8 项后半，播客块、对谈轮用同一个函数；阿拉伯数字一位算一个汉字；只夹一个"的"的、后面中文够长的算弱，不报）。挂在 `check_relations` 的提醒最前面，免得被第 7 步只摘的前 8 条挤掉。
  - `check_text_cards`：要点卡只有字（没有 `image`、没挂真标志——文字小签不算——也不是有效的 `over_photo`）。挂在 `check_screen` 里。

### 计数模板的地图数据

- 文件：`site/v3/us_states.json`（约 39 KB）。组装时只把用得到的几何编进那一块的 `geo`（本土外轮廓约 7 KB、州界细线约 6 KB，加上点亮的州），播放时不向外网要东西。
- 来源：us-atlas 3.0.1 的 `states-albers-10m.json`（https://cdn.jsdelivr.net/npm/us-atlas@3.0.1/states-albers-10m.json ，sha256 写在文件的 `source` 里，2026-11-06 取）。us-atlas 是 Mike Bostock 把美国人口普查局 2017 年 cartographic boundary（州界）文件转成的 TopoJSON，已按 `d3.geoAlbersUsa().scale(1300).translate([487.5, 305])` 投影到 975×610。许可：us-atlas 是 ISC（许可原文抄在文件的 `license_text` 里）；底下的人口普查局数据是美国政府作品，属公有领域。
- 怎么转的：下载的文件当不可信数据，只用 `json.load` 读、逐项校验类型，只取弧段坐标、变换参数和州的 FIPS 编号；弧段按 Douglas–Peucker 简化（容差 1.2 像素），面积小于 8 平方像素的小岛去掉，坐标留一位小数，拼成 SVG 路径。本土外轮廓取 nation 里不在阿拉斯加、夏威夷插图框里的几块；州界细线取被两个本土州共用的弧段；每个州另存一条路径和中文名、英文名、别名（核州名用）。转换脚本 `make_us_states.py` 和下载的原件、许可、README 留了一份在 `~/.cache/frontier-daily/验证/视频版式_工具/`（仓库外）：`python3 -I make_us_states.py states-albers-10m.json site/v3/us_states.json 1.2 8`。

## 三处代码各管什么

| 文件 | 管什么 |
|---|---|
| `site/tools/video3_storyboard.py` | 分镜的格式：`TEMPLATES` 表（每种模板要哪些字段、触发词、最少几项、能放在哪种章）、事实和数字核对、触发词清单、编成播放器数据 |
| `site/tools/video3_build.py` | 一条命令跑完：核对、配音、配乐排拍（`video3_music.py`）、逐字对齐、写演示页 |
| `site/v3/video3.js` | 播放器。`TPL` 是模板库：每种模板一段，按数据搭三维场景、排动画、给镜头；`logoChip`/`floatChip` 画标志小签 |
| `site/tools/video3_zhwrap.py` | 中文整词换行（11-09 晚加）：组装最后算"原文 → 带换行点的显示文字"对照表，写进数据的 `zhwrap`；播放器那一半是 `video3.js` 的 `wbWalk` |
| `site/tools/video3_logos.py` | 品牌标志库（`site/assets/logos/`）：取标志、记来源、量四周空白、构建时嵌进数据 |
| `site/tools/video3_images.py` | 视频配图：缺图时生成（本机先 agy 再 Codex，云端只用 Codex）或取资料图（Commons）、记来源、写署名 |
| `site/v3/us_states.json` | 计数模板的美国州界（us-atlas，来源和许可见上一节） |
| `pipeline/lexicon_check.py` 第 8 项后半 | 配音单位开头（视频一章、播客一块、对谈一轮）的英文夹心判断，`video3_storyboard.check_voice_openings` 借用它 |

## 中文整词换行（11-09 晚加，开关"视频中文整词换行"）

全站规矩：中文一个词不拆到两行，只在词与词之间、标点和空格处换行（经验库 9.3）。网页早就做到了，视频以前没接上（11-09 燃气轮机那张卡"稀缺设｜备"）。

- **断点只加在显示那一层**：`video3_build.build` 最后（英文名表也改完以后）调 `video3_zhwrap.table`，把要显示的中文（章和模板里的字、片头片尾、热点卡、字幕、文字稿、原句摘录画面上那一段）逐条过 `zh_breaks.phrase_breaks`（和网页同一套：BudouX 切词组、jieba 把关、数字和单位不断），只多写一个键 `zhwrap`：`{原文: 带换行点的显示文字}`。分镜、旁白、触发词、配图挂哪一句、字幕的 `text` 和逐字时间 `t`、文字稿都还是原文，所以触发词对旁白、字幕逐字高亮都不受影响。一个点都不用加的短词组也进表（显示文字就是原文），好让它整个不断。
- **播放器**（`video3.js` 的 `wbWalk`）：`W.label` 建好每张卡片、开场速览、时间轴弹出框、片头片尾、文字稿、热点说明的 HTML 以后，按元素里的字去表里找；对上了才把换行点（U+200B）、连接符（U+2060）插进那几个文本节点，元素加 `v3wb`（`video3.css`：`word-break: keep-all; overflow-wrap: anywhere`，和网页同一对）；对不上的（播放器自己拼的字）原样不动。滚动数字一开始显示 0，按"数字一段对一段"也认得出。荧光笔的时长按字数算，`wbLen` 不算插进去的点。
- **字幕**：仍是一个字一个 `<i>`（逐字变亮按 `<i>` 的序号对 `cues[].t`），换行点插在 `<i>` 和 `<i>` 之间、不进 `<i>`；数字那一组（`.nw`）后面的点放在 `</span>` 外面。
- **新模板、新版式（长字幕等）**：HTML 经 `self.label(...)` 建、字直接用数据里的原文（`esc(S2(...))`、`emph`、`noOrphan` 都行），就自动走这一套，不用另写；自己拼字（几段字连成一句、加前后缀）的那一段对不上表，就按原来的办法换行——要整词换行，就让组装时把拼好的那句也放进 `video3_zhwrap.strings`。
- **开关**：`fd_开关.json` 的"视频中文整词换行"（默认"开"；只管一次在命令前写 `FD_VIDEO_ZH_WRAP=off` 或 `on`）。关着时数据里不写 `zhwrap`，播放器什么都不做，视频和加开关以前逐像素一样（11-09 晚回归：10-31、11-06 浅色、手机竖屏、深色共 166 帧逐字节相同）。fd 第 14 步的输入指纹带着它（开着是空字符串，往期不重做；一换开关第 14 步自动重做），`./fd doctor` 会显示它开没开。断行工具（budoux、jieba）没装或出错只提醒，视频照常出（等于这一期没开）。
- **测试**：`$PY site/tools/test_video3_zhwrap.py`（开关、对照表不改原文、摘录截法和播放器一致；浏览器一组查各种宽度下"设备""供应商"不拆、不插时会拆、滚动数字和标题扫光副本、字幕 `<i>` 个数和逐字高亮不变、没有 `zhwrap` 时字幕 HTML 和改之前一模一样）；`test_video3_motion.py` 浏览器那几项比画面文字之前先去掉换行点（`plain`），演示页带不带 `zhwrap` 都能过。
- 残留：`zh_breaks` 本身偶尔在复合词中间切（经验库 9.3 记的"桌面｜电脑"），视频和网页一样；事件卡术语会整词保留。

## 加一个画面模板（例：`stat_card`，一个大数字）

1. **`video3_storyboard.py` 的 `TEMPLATES`** 加一行：

   ```python
   "stat_card": {"required": ["value"], "cues": ["show"], "kinds": ["story"], "panel": True,
                 "about": "一个大数字加一句说明"},
   ```
   `required` 缺了、`min` 不够，这个模板会被去掉；`list_cues` 写列表字段里每项的触发词（如 `{"items": "cue"}`），程序据此生成 `items0`、`items1`… 的时刻。字里的数字会自动按 `ref` 核对，不用另写。

2. **`video3.js` 的 `TPL`** 加一段（照着 `quote_card` 抄最省事）：

   ```js
   TPL.stat_card = {
     ext: [5, 5], panel: true,                                   // 在一行里占多宽；panel 表示能站在分岔路尽头
     build: function (b) {                                       // b：这一块的数据；b._.g 是它的三维组（局部坐标里搭）
       panelBuild(this, b, '<div class="kpi"><span class="n v3n">' + numUnit(S2(b.value, this.P.L)) + '</span></div>');
     },
     tl: function (b, a) {                                       // 按触发词排动画：b.t.show 是旁白说到那几个字的秒数
       var show = bt(b, 'show', b._.c.vs + 0.6); panelTl(b, a, show); b._.o.show = show;
     },
     cams: function (b) { return [{ t: b._.o.show + 0.4, s: b._.shS, dur: 1.4, ease: 'io', arc: 6 }]; },   // 这一段的镜头
     settle: function (b) { return b._.o.show + 2.5; },          // 这一段"看完"的时刻（暂停跳章、减少动态效果用）
     explore: function (b) { return [1, b._.shS]; }              // 自由看图时用哪一镜（数字越大越优先）
   };
   ```
   要每帧更新的（粒子、图表、抖动）再写 `frame: function (b, t) {…}`。镜头用 `this.bshot(b, [x, y, z], 偏航, 俯仰, 宽, 高)`，坐标在模板局部，朝向跟着模板转。
   放在哪里：普通模板在这一章里从左到右排一行（行居中在这一片上）；特殊的贴法写在 `W.buildChapter`（手机贴时间轴尽头、点阵贴传播链、卡片站在分岔路尽头、配图做背景）。

3. **`pipeline/prompts/写稿_视频v3.md` 的模板目录**加一行，写稿模型才知道有它。

4. 用 10-31 的分镜复制一份、加上这个模板试一遍（只看画面不想配音时：用 `video3_storyboard` 的 `structure`、`cue_list`、`compile_chapters` 配上按字数估的假时间，写一份 `data.js` 放进演示页目录打开），看三种画幅（16:9、网页里约 680 像素的一栏、手机竖屏）都不出画、不互压，控制台无报错。

## 动效尝试版（11-06 晚加：原文截图＋荧光笔、数字递进、开场今日速览、数字滚动；深夜补结合式：原话卡、时间轴日子带原文截图）

学《小互 AI 日报》"看得见出处"的动效（分析见 `文档/调研/参考作品拆解.md` 第六节），外观仍是我们的浅色"今日地图"。

**11-07 起并入正式流程**（用户看过 11-07"配图＋动效结合版"后定，从 11-08 起每期照做）：
- 写法在正式写稿提示词 `pipeline/prompts/写稿_视频v3.md`"看得见出处：原文截图和动效"一节和"画面要有真东西"末尾"11-07 补"，周末另看 `写稿_视频v3_周末.md` 第五节；写稿模型直接在正式分镜里写这些块和字段。
- 截图：`fd` 第 14 步组装视频之前调 `pipeline/orchestrator/helpers.py shots`（内部用下面的 `video3_trial.shot_items`、`run_shots` 和 `source_shots.mjs`），截到期目录的 `06_配图/原文截图/`，结果写 `本期截图.json`；总时长最多 150 秒，fd 另有 240 秒硬上限；截不到、超时、出错都只记提醒，那一处退回原句摘录，照常组装。
- 总开关：项目根 `fd_开关.json` 的"新动效和原文截图"写"关"（只管一次就在命令前写 `FD_MOTION=off`），`video3_build.prepare` 组装前调 `video3_storyboard.strip_motion` 去掉新块和新字段，fd 第 14 步不截图，视频退回 11-06 以前的画法；尝试版命令自己按"开"（命令前写 `FD_MOTION=off` 才关）。
- 不写这些模板和字段的分镜，渲染结果和改之前逐像素相同（11-06 晚、11-07 回归过 10-31、11-03、11-06、11-07 和周末彩排两版）。
- "尝试版"照旧能用：把某一期复制到缓存，在副本的分镜里加块，用现成配音重渲（$0）。

### 一条命令

```bash
PY=~/.venvs/frontier-daily/bin/python
$PY site/tools/video3_trial.py --day 2026-11-07 --spec <加块说明.json> --check-only    # 先只过分镜检查（几秒）
$PY site/tools/video3_trial.py --day 2026-11-07 --spec <加块说明.json>                 # 全套：复制 → 加块 → 截图 → 重渲 → 录预览（约 4 分钟）
$PY site/tools/video3_trial.py --day 2026-11-07 --spec <加块说明.json> --reuse-shots --compare 6,21.5,47 \
    --compare-out ~/.cache/frontier-daily/验证/动效尝试_1107_对比图                       # 改了加块说明再跑：截过的图不重截；出修前修后对比图
```

**命令做了什么**：
1. 复制：`测试版/<日期>/` → `~/.cache/frontier-daily/动效尝试/<日期>/`。
   - 原来有副本就整个移到废纸篓，不永久删；`--out` 可改位置，但不能放进 `测试版/`。
   - 原期的 `11_视频v3/` 另存一份 `修前_11_视频v3/`，做对比图用。
2. 按加块说明改副本的分镜 `04_文稿/视频v3_分镜.json`。
   - 加块说明改了旁白就停：尝试版只用现成配音。
3. 截图：每个 `source_shot`、原话卡的 `shot`、时间轴日子的 `shot` 按它的 `fact` 到事件卡找原句和来源网址，连同图位（`slot`）交给 `source_shots.mjs`。
   - 图存到副本的 `06_配图/原文截图/`；
   - `--no-shots` 不截，全部退回摘录。
4. 重渲：调 `video3_build.py --no-gen`。配音函数被换成"停"，旁白和现有配音对不上就停，绝不重配、不生图。
5. 录像：`video3_record.mjs` 出 `预览.mp4`、`关键帧总览.jpg`，另拷一份到副本根目录。
   - `--no-record` 不录；`--sheet-only` 只出总览。
6. 对比图（`--compare 时刻,时刻`）：`video3_frames.mjs` 在同一时刻渲修前、修后两帧，左右并排存成 `对比_<秒>.jpg`，外加一张 `对比总览.jpg`。

### 加块说明（JSON）

```json
{"date": "2026-11-07", "说明": "一句话说这次试了什么",
 "facts": {"e009.aa_fact": {"event": "E009", "field": "facts", "index": 4, "check": "得分最高的开源权重模型"}},
 "ops": [
  {"chapter": "open", "add": {"type": "headline_open", "id": "glance", "items": [...]}},
  {"chapter": "vote", "replace": "ballot", "with": {"type": "num_chain", ...}},
  {"chapter": "vote", "after": "vote_chain", "add": {"type": "source_shot", ...}},
  {"chapter": "code", "set": "cost", "fields": {"count": true}},
  {"chapter": "contrast", "remove": "aa"}]}
```

- `ops` 有四种：
  - `add`：加块，可带 `after`、`before`，不带就加在这一章最后；
  - `replace`：换块；
  - `set`：改字段，字段写 `null` 表示去掉；加 `"tick": 第几个日子（从 0 数）` 就改时间轴那一天的字段（结合式的 `shot` 用）；
  - `remove`：删块。
- 块 id 找不到就停，并列出这一章现有的块。
- `facts` 补进分镜的 facts；同名键要一模一样。
- 11-06 的完整范例：第二版 `site/tools/fixtures/动效尝试_加块说明_1106_v2.json`（按草案第五节，能结合的先结合，明早照它写）；第一版 `动效尝试_加块说明_1106.json` 留着对照。
- 每种块怎么写、什么时候用：11-07 起以正式提示词 `pipeline/prompts/写稿_视频v3.md`"看得见出处"一节为准（草案 `文档/历史/写稿_视频v3_动效草案.md` 留作来历，11-09 晚从 pipeline/prompts/ 移去，尝试版的加块说明写法还在那里）。

### 四种新块（播放器在 `video3.js` 的"动效尝试"一段，检查在 `video3_storyboard.py`）

| 块 | 放在哪 | 画面 | 必填 | 触发词 |
|---|---|---|---|---|
| `source_shot` | story、contrast 章 | 原文截图放在纸感卡片里缓慢推近（1 → 1.08 倍，推向原句）；`mark` 时荧光笔按行从左往右扫，每行时间按行宽分，合计 1.2–2.4 秒；左上角出处签"媒体 · 日期"；可选 `zh` 一行中文 | **fact**、**quote**；可选 `zh`、`source`、`shot`（截图 id，默认等于块 id） | show、mark |
| `source_excerpt` | 同上 | 没有截图时（或截图失败自动退回）：事件卡那条原文排成"报纸摘录"，原句包在荧光笔里扫过；卡片约占画面六成宽 | 同上 | show、mark |
| `num_chain` | story、contrast 章 | A → B → C 跟旁白一个个出，箭头画出来，最后一个强调色；`count: true` 时数字从 0 滚到终值 | **items**（2–4 项，每项 `label`、`cue`，可带 `sub`）；可选 `head`、`note`、`count` | head、items[].cue |
| `headline_open` | open 章 | 整屏配图＋左下大字标题＋关键数字小签，三屏依次出；右上角"日期 今日速览"；放完淡出，地图露出来再俯冲 | **items**（每项 `ch`、`text`，可带 `image`、`sub`、`cue`；`cue` 不写用那一章的 `map_cue`） | items[].cue |

`count: true` 写在 `quote_card` 或 `num_chain` 上：
- 第一个数字说到时从 0 滚到终值（0.8 秒）；
- 滚完显示的字和标签一字不差：3200、80.52、94.49%、1,200（`W.counter` 的 `fin`）；
- `column_compare`、`tally` 原来就会滚，不受影响。

### 结合式（11-06 深夜加：原话卡、时间轴日子带原文截图）

给已有的块加 `shot` 字段，不写就和原来逐像素相同（回归过 10-31、11-03、周末彩排两版和 11-06 原分镜）。`shot` 的字段同 `source_shot`：**fact**、**quote**，可选 `zh`、`source`、`id`、`cues.mark`。

| 写在哪 | 画面 | 截图 id 默认 | mark 触发词的键 | 截图宽高比 |
|---|---|---|---|---|
| `post_card` / `quote_card` 的 `shot` | 截图放进这张卡的图位、替代 `image`；卡片上图下字，人名、身份、原话、平台照旧；截图左上角出处签；mark 时荧光笔按行扫 | 块 id | `<章>.<块>.shot_mark` | 2.8–4.2（扁） |
| `timeline` 的 `ticks[i].shot` | 截图当这一天的小图；说到这一天后 0.2 秒弹出、放大到画面正中（70u 宽），mark 时扫，扫完停 1.1 秒缩回小图；镜头停在时间轴（`tlImageHold`），时间轴不打断 | `<块>_t<i>` | `<章>.<块>.ticks<i>_mark` | 1.9–3.4 |

- 加块说明的写法：`{"chapter": "code", "set": "ripple", "fields": {"shot": {…}}}`；时间轴 `{"chapter": "vote", "set": "nda", "tick": 2, "fields": {"shot": {…}}}`。
- 截图不能用就在**同一个图位**退回原句摘录，原因写在提醒里：没有截图记录、截图没成功、截的不是这一句、裁不干净、原句比字幕小。
- 播放器：`video3.js` 的"结合式"一段（`sbxHtml`、`sbxSweep`、`sbxCardBuild`、`tickShot`、`W.tlPopFrame`）；弹出框每一帧在 `updateLabels` 之后按小图的位置和画面中间插值（分镜没写 `ticks[].shot` 时不走这一步）。样式在 `video3.css` 末尾"结合式"一段。
- 被替代的 `image` 记进 `_image_replaced`，不备图、不算配图张数、不进"视频配图由 AI 生成"那一行；截图另写一行出处。
- 正式稿写法同理（直接在卡片或日子上写 `"shot": {…}`）；11-07 起写进了正式写稿提示词。

### 配图＋动效结合（11-07 加，都只在写了才起作用；不写的分镜逐像素相同）

- **尝试版里新画图**：加块说明顶层写 `image_requests`（写法同正式分镜，`id` 不能和分镜里已有的重名），命令加 `--gen-images` 才画（`video3_images.ensure`：本机先 agy、没成再 Codex，云端只用 Codex，存副本的 `06_配图/视频/`）；`--reuse-images` 把同一个副本目录里上次画的图留下（先暂存、复制完放回，原期同名文件以原期为准），不重画。重组仍是 `--no-gen`。
- **压在配图上 `photo`**（`tile_row`、`compare_panel`）：块后面立一张清楚的配图（不做视差、轻微柔化），卡片站在图前，镜头正对配图装下整张图；配图在 `cues.photo` 说到时溶解出现（不写就是这一块第一个触发词前 0.3 秒），这一块收场时收起；这一块在一行里占得宽些（`TPL.*.extPhoto`），左右的模板不进画面。小卡一排压在图上时卡片放大、抬高（不压字幕），解读字大一号；对比卡收小、站在图的右半边（竖屏时镜头改对着卡片，卡片放宽也不出画）。检查一侧：`PHOTO_BLOCKS`，算"真东西"、算清楚露脸、算配图张数，图找不到只去掉 `photo`；编成 `photo_img`（`ensure_photo`，键 `<块 id>.photo`）。
- **对比卡的出处签 `src_tag`、条尾的数 `bars[].val`**（`compare_panel`）：顶上一枚出处签（和原文截图的出处签同一个样子）；每根对比条末尾写数（如"1""约 3"），`val` 带数字要写 `ref`，照常核。
- **时间轴日子截图截不成**：退回摘录时这一天原来的 `image` 留着当小图（`tick_shots`、`video3.js` 的 `tickShot`），弹出框里照样是摘录；原来会变成只写媒体名的白卡。截成时照旧替代。
- 范例：`site/tools/fixtures/动效尝试_加块说明_1107_v2.json`（11-07 配图＋动效结合版，报告 `~/.cache/frontier-daily/验证/配图动效_1107_报告.md`）。

### 分镜检查（`video3_storyboard.py`，核不上就停）

- `check_sources`（在 `check_labels` 里一起跑；`shot_owners` 列出每一处：`source_shot`／`source_excerpt` 本身、原话卡的 `shot`、时间轴日子的 `shot`）：
  - 原句要逐字是事件卡那条 `quote` 里连续的一段，弯撇号、括号都不能改；
  - `zh` 只能取同一条的 `text_zh`（`who_said` 取 `said_zh`），写 `true` 就整句用；
  - `source` 的媒体名要在事件卡来源名或网址里；
  - 出处签日期按事件卡来源的日期写。截图记录里网页自己写的日期（`page_date`）和它不是同一天时，签上不写日期，并提醒。
- 数字：`num_chain`、`headline_open` 的字按 `ref` 核，和别的模板一样。
- 触发词：都要在这一章的旁白里（`check_cues`）。
- 原句在成片里有多大（`shot_font_u`）：截图记录里原句的字号 `font_px` ÷ 截图宽 `clip.w` × 截图框在成片里的宽（`shot_slot_u`，按图位算：整屏卡、原话卡、弹出框，16:9 横屏），小于字幕 `SUB_U`＝1.85（舞台宽度的百分之几）就退回摘录。`shot_slot_u` 和 `video3.js` 的版式常数（`SBX_*`、`.v3tpop` 宽、`SRC_*`）要一起改；浏览器测试核过估的不比实际宽。
- 只提醒、不拦：
  - 截图没成功、没截、截的不是这一句、裁不干净、字比字幕小，自动退回 `source_excerpt`（`structure` 里的 `shot_fallback`；结合式是 `card_shot`、`tick_shots`，在同一个图位换成摘录）；
  - 一期超过 3 处截图／摘录，结合式也算（`shot_budget`）；
  - `count` 写错地方、写成别的值、字里没数字（`count_problems`）。
- 画面检查也认得它们：
  - 截图算"真东西"（img），从出现到下场都算；
  - 摘录只算荧光笔扫的那 4 秒；
  - 数字递进每出一项算 4 秒；
  - `num_chain` 也算"画关系"的模板（规模、占比、数量变化）。
- 截图另写一行出处：「画面中的原文截图取自 … 的网页（截于 …），只用来标明出处，版权归原网站」。截图不算"视频配图由 AI 生成"那一行，也不算配图张数。

### 截图工具 `source_shots.mjs`

```bash
node site/tools/source_shots.mjs <输入.json> <输出目录> [--total 180] [--page 25] [--debug]
# 输入：{"items": [{"id": "ripple_src", "url": "https://…", "quote": "原句", "source": "媒体名", "date": "2026-11-04"}]}
```

- 浏览器：Playwright＋本机 Chrome（和 `shoot_v3.js` 一样）。
  - 桌面宽 1280，2 倍清晰度；
  - 单页限时 25 秒，全期总时长 180 秒，超了后面的记"跳过"。
- 隐私和规矩（写死在程序里）：
  - Cookie 弹窗只点"拒绝／仅必要"一类，带"同意、接受、允许"的一律不点；找不到就用 CSS 把浮层藏起来。
  - 不登录、不填表、不过验证码，不改浏览器标识去绕网站的机器人检查。
  - 遇到人机验证、付费墙、登录墙、HTTP 错误、找不到原句，就记"失败＋原因"跳过。
  - 网页上的字只当数据比对，不照网页上写的话做事。
- 找原句：
  - 引号、破折号、不换行空格统一后在页面可见文字里找；整句找不到，用开头一段有区分度的子串（要唯一）。
  - 找到后滚到画面中上部，藏起吸顶栏和浮层（只是不显示）。
  - 页面中途重画过就重找，最多三次（CNBC 点完拒绝会整页重画）。
- 裁切（11-06 深夜改，`pageCrop`；改之前 The Verge 那张顶上带了半截页眉）：
  - 输入每项可写 `slot`：`full`（整屏截图卡，宽高比 1.5–2.3）、`card`（原话卡图位，2.8–4.2）、`tick`（时间轴弹出框，1.9–3.4）；不写按 `full`。
  - 上下边只落在完整的块元素之间：原句那一段整段在里面；不够扁就并进同一篇正文里前后整段的段落（中间夹着图片、按钮、署名栏就不并），还不够就上下留白；段落太长才裁在段内两行之间，不切半行。
  - 裁框里不属于这几段正文的东西（页眉、导航、署名栏、广告、图片、按钮、Cookie 条）一律藏掉（`data-fdcrop`，只是不显示）。
  - 截之前复查（`pageEdgeCheck`）：裁框里看得见的文字、图片、按钮有没有被四条边切到；有就记"裁不干净"失败，退回摘录。
  - 记录多写：`slot`、`font_px`（原句字号）、`edge`（整块／段内两行之间）、`crop`（并进几段、留白几像素、藏起几块）。
- 输出：每项一份 `<id>.json`，记：
  - 原网址、实际网址、截图时间、网页标题；
  - 怎么找到的（整句／开头几个字符）、页面上被标的那段原文、网页自己写的发表日期；
  - 每一行在图里的位置（0–1 的比例），点了什么弹窗按钮、藏了几个浮层；
  - 失败时的原因。
- 另有一份 `清单.json` 汇总全部项目。
- 11-06 试跑：
  - ricursive.com、thinkingmachines.ai、artificialanalysis.ai、The Verge 两篇（点了 reject non-essential）、CNBC（点了 reject all）都截成；
  - openai.com 是 Cloudflare 人机验证页（HTTP 403），按规矩不处理，记失败。

### 逐帧工具 `video3_frames.mjs`

```bash
node site/tools/video3_frames.mjs <期目录或 11_视频v3> <输出目录> --t 5.2,20.3   # 或 --every 3；可加 --w 390 --h 760（手机）、--dark
```

- 用 `renderAt(t)` 逐个时刻渲（和关键帧总览同一套），存成 `f_<秒>.png`，另写一份 `帧.json`（含页面报错）。
- 对比图和逐像素回归都用它。

### 测试

`$PY site/tools/test_video3_motion.py`（35 项；11-07 加到 44 项：日子截图截不成时小图留着、压在配图上的检查和编译、`val` 数字照核、不写新字段时数据不变、尝试版的 `image_requests` / `--gen-images` / `--reuse-images`，浏览器一组查配图出现又收起、小卡和对比卡在画面里不压字幕区、出处签和条尾的数、截不成那天小图位里是原图）：
- 结合式（11-06 深夜补）：卡片截图替代配图、编进播放器的字段、退回摘录（没记录、字太小）、逐字核对、缺字段时卡片照旧、要点卡不再算"只有字"、时间轴日子截图、mark 触发词、图位尺寸估算、尝试版命令的 `tick` 写法和截图清单；浏览器一组查弹出框 70u 宽、居中、不压字幕、扫完缩回，卡片截图不比估的窄，截不到时图位里是摘录；另用本机起的仿新闻页（只连 127.0.0.1）查裁切：上下边没切到东西、页眉和署名栏不进图、宽高比在图位范围里、长段落裁在段内两行之间。
- 检查一侧：原句逐字、中文行、出处签、数字、触发词、截图退回摘录、网页日期对不上、`count` 提醒、编进播放器的字段。
- 播放器函数：`countHtml`、`chainNum` 的终值写法。
- 浏览器一组：在 11-06 演示页的副本里塞进四种新块，用本机 Chrome 渲几个时刻，查：
  - 速览出现又消失；
  - 数字滚到终值；
  - 荧光笔扫完；
  - 摘录底色长满；
  - 页面无报错。
