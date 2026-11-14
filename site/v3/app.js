/* 每日AI科技前沿简报 · v3 · app.js（“发布会玻璃”）
 * 读 issues/index.js（往期日期和全站设置）→ 按 ?date= 加载 issues/日期/issue.js → 渲染整页。
 * 双击 index.html（file://）也能用：数据都是 <script> 挂到 window 上，不用 fetch。
 * 凡是“原地切换”的版块（头条、要闻、预告看板、国内外对照）都用同一个编号页签 Pager：1 2 3、“1/3”、进度条、
 *   自动轮播（鼠标停上去或键盘焦点进来就暂停；滚出视野暂停；手动点过就不再自动）、左右方向键、手机左右滑。
 * 视频播放器（GSAP＋video2.js）和图表库（ECharts）都等滚到附近才加载，首屏不下载。
 * 正文里的 [^s07] 渲染成上标引用，页面渲染完后按出现顺序统一编号 [1][2]…；上标用 CSS 里的“连字符”和前一个字粘在一起，不会单独换行。
 * v3.1：页签鼠标停约 150 毫秒就换过去；背景加一层 Canvas 画的点和细线（Field，颜色取当天主题色）；正文里有组装时插入的换行点 U+200B（复制时去掉）。
 * v3.2：头条、要闻每条按 st.layout 用五种配图版式之一（组装时按日期＋条目号挑，相邻不重复）；缺图时画一张主题色的抽象封面；
 *   版块标题旁不再放操作说明；预告看板改成一条时间轴（节点＋同一块里的详情，仍用 Pager 的轮播逻辑）；
 *   国内外对照中间画关系小动画（词表见 site/tools/v3_site.py 的 RELATIONS）；页脚一行话取自 v3_site.py；没有播客或视频时相应按钮和面板都不出现。
 * 周末两版（11-01 晚定，ISSUE.edition 为 sat / sun）：首屏换成“今日深度”／“本周深谈”卡；今日一词改成深度那一块里折叠的“名词解释”；
 *   周日不单列今日数字（关键数字放进深谈各层），快讯叫“本周快讯”、预告看板叫“接下来看什么”，深谈排在看与听后面。工作日不变。
 * 网址参数：?date=YYYY-MM-DD  ?theme=light|dark  ?static=1（截图用）  ?accent=blue|amber|coral|violet（只预览别的主题色） */
(function () {
  'use strict';

  /* ===================== 小工具 ===================== */
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var store = {
    get: function (k, f) { try { var v = localStorage.getItem(k); return v == null ? f : v; } catch (e) { return f; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 浏览器不让存就不记了 */ } }
  };
  var root = document.documentElement;
  var STATIC = root.classList.contains('static');
  var mm = function (q) { return window.matchMedia ? window.matchMedia(q) : null; };
  var mqRM = mm('(prefers-reduced-motion: reduce)'), mqDark = mm('(prefers-color-scheme: dark)'), mqHover = mm('(hover: hover) and (pointer: fine)');
  var RM = function () { return !!(mqRM && mqRM.matches); };
  var animOK = function () { return !STATIC && !RM(); };
  var HOVER = function () { return !!(mqHover && mqHover.matches); };
  var pad2 = function (n) { return String(n).padStart(2, '0'); };
  var fmtTime = function (s) { s = Math.max(0, Math.floor(s || 0)); return Math.floor(s / 60) + ':' + pad2(s % 60); };
  var fmtN = function (v, dec, comma) {
    var s = (+v).toFixed(dec || 0);
    if (comma) s = s.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return s;
  };
  var fmtNum = function (v) { return String(+(+v).toFixed(2)); };
  var hasCJK = function (s) { return /[㐀-鿿]/.test(s); };

  var ICON = {
    chevL: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.5 5.5 8 12l6.5 6.5"/></svg>',
    chevR: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.5 5.5 16 12l-6.5 6.5"/></svg>',
    chevD: '<svg class="chev" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9.5l6 6 6-6"/></svg>',
    play: '<svg class="i-play" viewBox="0 0 24 24" aria-hidden="true"><path class="f" d="M8 5.6v12.8c0 .8.9 1.3 1.6.9l10-6.4c.6-.4.6-1.4 0-1.8l-10-6.4C8.9 4.3 8 4.8 8 5.6Z"/></svg>',
    pause: '<svg class="i-pause" viewBox="0 0 24 24" aria-hidden="true"><rect class="f" x="6.5" y="5" width="3.6" height="14" rx="1.2"/><rect class="f" x="13.9" y="5" width="3.6" height="14" rx="1.2"/></svg>',
    headph: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.5 15v-3a7.5 7.5 0 0 1 15 0v3"/><rect class="f" x="3.5" y="13.5" width="5" height="7" rx="2"/><rect class="f" x="15.5" y="13.5" width="5" height="7" rx="2"/></svg>',
    film: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="3.5"/><path class="f" d="M10 9.2v5.6l4.8-2.8z"/></svg>',
    flip: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 0 1 13.7-5.6L20 8.7M20 4v4.7h-4.7M20 12a8 8 0 0 1-13.7 5.6L4 15.3M4 20v-4.7h4.7"/></svg>',
    close: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></svg>',
    go: '<svg class="go" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h13M13 6.5l5.5 5.5-5.5 5.5"/></svg>',
    ar_down: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4.5v15M5.5 13l6.5 6.5 6.5-6.5"/></svg>',
    ar_up: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19.5v-15M5.5 11 12 4.5l6.5 6.5"/></svg>',
    plus: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
    sun: '<svg class="i-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6"/></svg>',
    moon: '<svg class="i-moon" viewBox="0 0 24 24" aria-hidden="true"><path class="f" d="M20 14.6A8.2 8.2 0 0 1 9.4 4a8.2 8.2 0 1 0 10.6 10.6Z"/></svg>'
  };

  /* ===================== 文字（中文段落在两个标记之间：组装脚本按它挑出界面要用的字，做字体子集） ===================== */
  var I18N = {
    /* I18N-ZH-START */
    zh: {
      test: '测试版', prev_day: '前一期', next_day: '后一期', pick_date: '选择日期', no_more: '没有了',
      cal_count: '共 {n} 期 · 最新 {d}', cal_prev: '上个月', cal_next: '下个月',
      to_dark: '切换到深色', to_light: '切换到浅色', lang_label: '语言',
      wd: ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'], wd_s: ['日', '一', '二', '三', '四', '五', '六'],
      three: '今日三件事', term_k: '今日一词', listen_n: '听 {n} 分钟', watch_n: '看 {n} 秒', ai_img: 'AI 生成配图',
      sec_numbers: '今日数字', sec_media: '看与听', sec_headline: '头条', sec_brief: '要闻', sec_flash: '快讯',
      sec_watch: '预告看板', sec_pairs: '国内外对照', sec_term: '今日一词', sec_sources: '参考来源',
      media_v: '视频 {v} 秒', media_p: '播客 {p} 分钟', media_ai: 'AI 合成语音', m_watch: '看 · 视频', m_listen: '听 · 播客',
      v_ph: '视频 · {s} 秒', v_loading: '正在载入视频…',
      carousel: '轮播', timeline: '时间轴', pg_play: '开始自动轮播', pg_pause: '暂停自动轮播',
      go_headline: '看头条', go_brief: '看要闻', go_flash: '看快讯', go_story: '看原条', go_pair: '看对照', our_read: '我们的理解', skip: '跳到正文',
      spec_zh_n: '中 {n}', spec_en_n: '英 {n}', spec_so_n: '社 {n}',
      read_more: '读全文', read_less: '收起全文', why: '为什么重要',
      listen_seg: '听这一段', watch_seg: '看这一段', watch_none: '视频未涉及', sources_of: '来源',
      w_rumor: '传闻', w_teaser: '预告', w_scheduled: '已排期', w_reported: '报道称', w_more: '详情', w_less: '收起',
      pair_intl: '国外', pair_cn: '国内', rel_aria: '两边的关系：{r}', to_brief: '去看要闻', to_headline: '去看头条', to_flash: '去看快讯',
      flip: '翻面：白话解释和今天的用法', flip_back: '翻回来', term_explain: '白话解释', term_usage: '今天新闻里的用法',
      term_note: '为什么值得分清', term_front: '正面', term_back: '背面（点“翻面”后卡片转过来）',
      src_sum: '共 {n} 条', src_sum_all: '共 {n} 条',
      src_all: '展开全部（{n}）', src_top: '只看前 5 条', cite_go: '查看来源 →', cite_label: '来源 {n}',
      chart_src: '出处', chart_err: '图表库没有加载出来。', c_timeline: '时间线', c_graph: '关系图',
      foot_line: '本期由 AI 自动化工作流生成 · 主题色：{accent} · {past} · 每日AI科技前沿简报', foot_past: '往期',
      fb_link: '反馈', fb_title: '反馈', fb_issue: '{d} 这一期', fb_intro: '哪里写错了、念错了、链接打不开，都可以告诉我们。',
      fb_text: '哪里不对', fb_text_ph: '比如：头条第 2 条的金额和原文对不上', fb_need: '先写一下哪里不对。', fb_count: '{n}/{max}',
      fb_name: '称呼', fb_where: '大概位置', fb_opt: '选填', fb_where_ph: '比如：要闻第 3 条、播客 7:33',
      fb_send: '提交', fb_cancel: '取消', fb_close: '关闭', fb_sending: '正在提交…', fb_more: '再写一条',
      fb_ok: '收到了，谢谢', fb_ok_more: '我们核对以后会改正。', fb_err: '暂时没能提交，请稍后再试。你写的内容还在。',
      fb_err_rate: '提交得有点频繁，请过几分钟再试。', fb_err_setup: '反馈功能还没设置好，请稍后再试。',
      fb_local: '只能在网站上提交：这是本机打开的页面，提交不会发出去。', fb_pod: '播客 {t}', fb_vid: '视频 {s} 秒',
      pod_ai: 'AI 合成语音', pod_ch: '章节', pod_speed: '倍速', pod_back: '后退 15 秒', pod_fwd: '前进 15 秒',
      pod_play: '播放播客', pod_pause: '暂停播客', pod_seek: '播客进度', pod_err: '播客音频没有加载出来。', mini_close: '停止播放',
      kind_headline: '头条', kind_brief: '要闻', kind_flash: '快讯', kind_teaser: '预告', kind_cn_intl: '对照', kind_term: '一词',
      kind_deep: '深度', kind_talk: '深谈', sec_deep: '深度', sec_talk: '本周深谈', go_deep: '看深度', go_talk: '看深谈',
      dl_nav: '这一题的几层', dl_n: '{n} 层', dl_listen: '听这一层', dl_pod: '播客里约 {m} 分钟',
      sec_card_sat: '今日深度', sec_card_sun: '本周深谈', sec_flash_week: '本周快讯', sec_next: '接下来看什么', sec_glossary: '名词解释',
      listen_deep: '听深度', listen_talk: '听深谈', listen_min: '约 {n} 分钟', card_flash: '快讯', core_q: '核心问题', one_line: '一句话结论',
      gl_n: '{n} 个词', gl_layer: '出自第 {n} 层 · {l}',
      status_confirmed: '已确认', status_reported: '媒体报道', status_teaser: '未经证实', region_cn: '国内', region_intl: '国际',
      spec_n: '中 {zh} · 英 {en}', spec_s: ' · 社 {so}', spec_tip: '当天归并到这一条的报道', spec_zh: '中文', spec_en: '英文', spec_so: '社区/社交',
      notice_no_issue: '没有 {date} 这一期，已显示最新一期。',
      fatal_title: '这一期没能载入', fatal_body: '找不到 {f}。请确认文件夹完整，或从往期里另选一天。', fatal_index: '找不到往期目录 issues/index.js。',
      v_play: '播放', v_pause: '暂停', v_replay: '重播', v_prev: '上一场景', v_next: '下一场景', v_cc: '字幕',
      v_silent: '无声预览', v_silent_forced: '没有旁白音频，只能无声预览', v_full: '全屏', v_seek: '视频进度',
      v_region: '视频播放器：空格播放或暂停，左右方向键快退快进，Shift 加方向键切换场景',
      v_scenes: '视频分章', v_scene: '场景', v_src: '来源：', v_orig: '原文', v_chip_ai: 'AI 合成', v_chip_silent: '无声预览', v_play_silent: '无声预览',
      v_no_audio: '没有找到旁白音频，已切换为无声预览：画面和字幕按时间轴播放，可以拖动进度条，或点下面的分章逐个查看。',
      v_audio_error: '旁白音频播放出错，已切换为无声预览。',
      v_silent_on: '无声预览中：旁白已关，画面和字幕照常按时间轴播放。',
      v_estimated: '这一版还没有对齐过的时间轴，场景和字幕的时间是按旁白字数估算的。'
    },
    /* I18N-ZH-END */
    en: {
      test: 'Test build', prev_day: 'Previous issue', next_day: 'Next issue', pick_date: 'Pick a date', no_more: 'None',
      cal_count: '{n} issue(s) · latest {d}', cal_prev: 'Previous month', cal_next: 'Next month',
      to_dark: 'Switch to dark', to_light: 'Switch to light', lang_label: 'Language',
      wd: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'], wd_s: ['S', 'M', 'T', 'W', 'T', 'F', 'S'],
      three: 'Three things today', term_k: 'Word of the day', listen_n: 'Listen · {n} min · in Mandarin', watch_n: 'Watch · {n} s · in Mandarin', ai_img: 'AI-generated',
      sec_numbers: 'Today in numbers', sec_media: 'Watch & listen', sec_headline: 'Top stories', sec_brief: 'Key stories', sec_flash: 'In brief',
      sec_watch: 'On the radar', sec_pairs: 'China × World', sec_term: 'Word of the day', sec_sources: 'Sources',
      media_v: 'Video {v} s', media_p: 'podcast {p} min · both in Mandarin', media_ai: 'synthetic voices', m_watch: 'Watch', m_listen: 'Listen',
      v_ph: 'Video · {s} s', v_loading: 'Loading the video…',
      carousel: 'carousel', timeline: 'timeline', pg_play: 'Start auto-play', pg_pause: 'Pause auto-play',
      go_headline: 'Top story', go_brief: 'Key story', go_flash: 'In brief', go_story: 'Story', go_pair: 'China × World', our_read: 'Our read', skip: 'Skip to content',
      spec_zh_n: 'zh {n}', spec_en_n: 'en {n}', spec_so_n: 'social {n}',
      read_more: 'Read in full', read_less: 'Show less', why: 'Why it matters',
      listen_seg: 'Listen', watch_seg: 'Watch', watch_none: 'Not in the video', sources_of: 'Sources',
      w_rumor: 'Rumor', w_teaser: 'Announced', w_scheduled: 'Scheduled', w_reported: 'Reported', w_more: 'Details', w_less: 'Hide',
      pair_intl: 'World', pair_cn: 'China', rel_aria: 'How the two sides relate: {r}', to_brief: 'Go to the key story', to_headline: 'Go to the top story', to_flash: 'Go to the news in brief',
      flip: 'Flip: plain words and today’s usage', flip_back: 'Flip back', term_explain: 'In plain words', term_usage: 'In today’s news',
      term_note: 'Why the distinction matters', term_front: 'Front', term_back: 'Back (shown after “Flip”)',
      src_sum: '{n} sources', src_sum_all: '{n} sources',
      src_all: 'Show all {n}', src_top: 'Top 5 only', cite_go: 'Go to the source →', cite_label: 'Source {n}',
      chart_src: 'Sources', chart_err: 'The chart library did not load.', c_timeline: 'Timeline', c_graph: 'Who’s who',
      foot_line: 'Produced by an automated AI workflow · Colour: {accent} · {past} · Daily AI & Tech Frontier Briefing', foot_past: 'Past issues',
      fb_link: 'Feedback', fb_title: 'Feedback', fb_issue: 'Issue of {d}', fb_intro: 'Spotted a mistake, a mispronunciation or a broken link? Tell us.',
      fb_text: 'What’s wrong', fb_text_ph: 'e.g. the amount in top story 2 doesn’t match the source', fb_need: 'Please say what’s wrong first.', fb_count: '{n}/{max}',
      fb_name: 'Your name', fb_where: 'Where, roughly', fb_opt: 'optional', fb_where_ph: 'e.g. key story 3, podcast 7:33',
      fb_send: 'Send', fb_cancel: 'Cancel', fb_close: 'Close', fb_sending: 'Sending…', fb_more: 'Write another',
      fb_ok: 'Got it, thank you', fb_ok_more: 'We’ll check it and correct what needs correcting.', fb_err: 'Couldn’t send just now. Please try again later; your text is still here.',
      fb_err_rate: 'That’s several in a row. Please wait a few minutes and try again.', fb_err_setup: 'Feedback isn’t set up yet. Please try again later.',
      fb_local: 'Feedback can only be sent from the website; this local copy won’t send anything.', fb_pod: 'Podcast {t}', fb_vid: 'Video {s} s',
      pod_ai: 'Synthetic voice', pod_ch: 'Chapters', pod_speed: 'Speed', pod_back: 'Back 15 s', pod_fwd: 'Forward 15 s',
      pod_play: 'Play podcast', pod_pause: 'Pause podcast', pod_seek: 'Podcast position', pod_err: 'The podcast audio did not load.', mini_close: 'Stop',
      kind_headline: 'Top story', kind_brief: 'Key story', kind_flash: 'In brief', kind_teaser: 'Radar', kind_cn_intl: 'China × World', kind_term: 'Word',
      kind_deep: 'Deep dive', kind_talk: 'Deep talk', sec_deep: 'Deep dive', sec_talk: 'The week, in depth', go_deep: 'Go to the deep dive', go_talk: 'Go to the deep talk',
      dl_nav: 'Layers of this story', dl_n: '{n} layers', dl_listen: 'Listen to this layer', dl_pod: 'about {m} min in the podcast',
      sec_card_sat: 'Today’s deep dive', sec_card_sun: 'The week, in depth', sec_flash_week: 'This week in brief', sec_next: 'What to watch next', sec_glossary: 'Glossary',
      listen_deep: 'Listen to the deep dive', listen_talk: 'Listen to the deep talk', listen_min: 'about {n} min · in Mandarin', card_flash: 'In brief', core_q: 'The question', one_line: 'In one line',
      gl_n: '{n} terms', gl_layer: 'From layer {n} · {l}',
      status_confirmed: 'Confirmed', status_reported: 'Reported', status_teaser: 'Unverified', region_cn: 'China', region_intl: 'World',
      spec_n: 'zh {zh} · en {en}', spec_s: ' · social {so}', spec_tip: 'Coverage merged into this story that day', spec_zh: 'Chinese', spec_en: 'English', spec_so: 'Community / social',
      notice_no_issue: 'There is no issue for {date}; showing the latest one.',
      fatal_title: 'This issue could not be loaded', fatal_body: 'Missing {f}. Check that the folder is complete, or pick another day.', fatal_index: 'The issue list issues/index.js is missing.',
      v_play: 'Play', v_pause: 'Pause', v_replay: 'Replay', v_prev: 'Previous scene', v_next: 'Next scene', v_cc: 'Subtitles',
      v_silent: 'Silent preview', v_silent_forced: 'No narration audio: silent preview only', v_full: 'Full screen', v_seek: 'Video position',
      v_region: 'Video player: Space to play or pause, arrow keys to seek, Shift+arrows to change scene',
      v_scenes: 'Video chapters', v_scene: 'Scene', v_src: 'Source: ', v_orig: 'Original', v_chip_ai: 'AI-generated', v_chip_silent: 'Silent preview', v_play_silent: 'Silent preview',
      v_no_audio: 'Narration audio not found, so this is a silent preview: pictures and subtitles follow the timeline.',
      v_audio_error: 'The narration failed to play, so this switched to a silent preview.',
      v_silent_on: 'Silent preview: narration off; pictures and subtitles keep to the timeline.',
      v_estimated: 'This cut has no aligned timeline yet; timings are estimated from the narration length.'
    }
  };
  var ACCENT_NAME = { blue: ['海蓝', 'ocean blue'], amber: ['琥珀', 'amber'], coral: ['珊瑚', 'coral'], violet: ['紫', 'violet'] };
  var lang = store.get('fd.lang', 'zh') === 'en' ? 'en' : 'zh';
  var t = function (k, vars) {
    var s = I18N[lang][k] != null ? I18N[lang][k] : (I18N.zh[k] != null ? I18N.zh[k] : k);
    if (vars && typeof s === 'string') s = s.replace(/\{(\w+)\}/g, function (m, x) { return vars[x] != null ? vars[x] : m; });
    return s;
  };
  var pick = function (o, k) {
    if (!o) return '';
    var v = o[k + '_' + lang];
    if (v != null && v !== '') return v;
    v = o[k + '_zh'];
    if (v != null && v !== '') return v;
    v = o[k];
    return v == null ? '' : v;
  };

  /* ===================== 状态 ===================== */
  var INDEX = window.FD_INDEX || null;
  var SITE = (INDEX && INDEX.site) || { name_zh: '每日AI科技前沿简报', name_en: 'Daily AI & Tech Frontier Briefing', name_en_short: 'Frontier Briefing' };
  var DATE = null, ISSUE = null, BASE = '';
  var players = { video: null, podcast: null };
  var CHARTS = [];
  var PAGERS = {};
  var CITE = { order: {}, count: {}, list: [] };
  var UI = { pg: {}, more: {}, flash: null, flip: false, srcOpen: false, srcAll: false, media: 'watch', ctab: {}, pexp: {}, wdet: {}, gloss: false };
  var lastPointer = 'mouse';
  var io = null, SECN = 0;

  var asset = function (p) { if (!p) return p; return /^(data:|blob:|https?:|file:|\/)/i.test(p) ? p : BASE + p; };
  var normImage = function (img) { if (!img) return null; if (typeof img === 'string') return { src: img }; return img.src ? img : null; };
  var host = function (url) { try { return new URL(url).hostname.replace(/^www\./, ''); } catch (e) { return ''; } };
  var S = function (id) { return (ISSUE && ISSUE.stories[id]) || null; };
  var CH = function (id) { return (ISSUE && ISSUE.charts[id]) || null; };
  var srcById = function (id) { for (var i = 0; i < ISSUE.sources.length; i++) if (ISSUE.sources[i].id === id) return ISSUE.sources[i]; return null; };

  /* ===================== 启动 ===================== */
  function loadScript(src, cb) {
    var s = document.createElement('script');
    s.src = src;
    s.onload = function () { cb(true); };
    s.onerror = function () { cb(false); };
    document.body.appendChild(s);
  }
  function loadCSS(href, cb) {
    if ($('link[data-href="' + href + '"]')) { if (cb) cb(); return; }
    var l = document.createElement('link');
    l.rel = 'stylesheet'; l.href = href; l.setAttribute('data-href', href);
    l.onload = l.onerror = function () { if (cb) cb(); };
    document.head.appendChild(l);
  }
  function dates() { return ((INDEX && INDEX.issues) || []).map(function (x) { return x.date; }).sort(); }
  function boot() {
    root.lang = lang === 'en' ? 'en' : 'zh-CN';
    initField();   // 背景数字层不等数据，先画起来
    if (!INDEX) { fatal(t('fatal_index')); return; }
    var ds = dates();
    var q = (location.search.match(/[?&]date=(\d{4}-\d{2}-\d{2})/) || [])[1];
    DATE = q && ds.indexOf(q) >= 0 ? q : (INDEX.latest || ds[ds.length - 1]);
    if (q && ds.indexOf(q) < 0) {
      var n = $('#notice'); n.hidden = false; n.innerHTML = '<p class="glass">' + esc(t('notice_no_issue', { date: q })) + '</p>';
    }
    BASE = 'issues/' + DATE + '/';
    loadScript(BASE + 'issue.js', function (ok) {
      ISSUE = window.FD_ISSUES && window.FD_ISSUES[DATE];
      if (!ok || !ISSUE) { renderTop(); fatal(t('fatal_body', { f: BASE + 'issue.js' })); return; }
      applyIssueLook();
      document.title = (lang === 'en' ? SITE.name_en_short : SITE.name_zh) + ' · ' + DATE;
      renderTop();
      $('#main').innerHTML = '<div id="c-main"></div>';
      setupIO();
      renderContent();
      mountMedia();
      bindGlobal();
      if (STATIC) staticPage();
    });
  }
  // 这一期的主题色和字体：index.html 里已经按最新一期写好；看往期时换成那一期的
  function applyIssueLook() {
    var a = ISSUE.theme && ISSUE.theme.accent;
    if (a && !root.hasAttribute('data-accent-lock')) root.setAttribute('data-accent', a);
    if (FIELD) FIELD.refresh();
    var st = $('#fd-fonts');
    if (st && ISSUE.fonts_css && st.textContent.trim() !== ISSUE.fonts_css.trim()) st.textContent = ISSUE.fonts_css;
  }
  function fatal(msg) {
    $('#main').innerHTML = '<div class="fatal glass"><h1>' + esc(t('fatal_title')) + '</h1><p>' + esc(msg) + '</p></div>';
  }
  function go(date) {
    if (!date || date === DATE) { closeCal(); return; }
    location.search = '?date=' + date;
  }

  /* ===================== 刊头：品牌、日期（前一期/日历/后一期）、中/EN、深浅色 ===================== */
  function amp(s) { return esc(s).replace(/&amp;/g, '<i>&amp;</i>'); }
  function dateText(d) {   // 年份单独包一层，手机上窄时可以省掉
    var dt = new Date(d + 'T12:00:00');
    if (lang === 'en') return { y: ' ' + d.slice(0, 4), md: dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }), wd: t('wd')[dt.getDay()].slice(0, 3), yFirst: false };
    return { y: +d.slice(0, 4) + ' 年 ', md: (+d.slice(5, 7)) + ' 月 ' + (+d.slice(8, 10)) + ' 日', wd: t('wd')[dt.getDay()], yFirst: true };   // 和正文一样，数字和年月日之间留空格
  }
  function effTheme() { return root.getAttribute('data-theme') || (mqDark && mqDark.matches ? 'dark' : 'light'); }
  function renderTop() {
    var sk = $('.skip'); if (sk) sk.textContent = t('skip');
    var ds = dates(), i = ds.indexOf(DATE);
    var prev = i > 0 ? ds[i - 1] : '', next = i >= 0 && i < ds.length - 1 ? ds[i + 1] : '';
    var dl = DATE ? dateText(DATE) : { y: '', md: '', wd: '' }, en = lang === 'en';
    var dhtml = dl.yFirst ? '<span class="y">' + esc(dl.y) + '</span>' + esc(dl.md) : esc(dl.md) + '<span class="y">' + esc(dl.y) + '</span>';
    var test = ISSUE && ISSUE.meta && ISSUE.meta.test;
    $('#top').innerHTML =
      '<div class="mast-top rv">' +
        '<a class="mark" href="?date=' + esc((INDEX && INDEX.latest) || '') + '"><span class="orb" aria-hidden="true"></span><span class="mark-en" lang="en">' + esc(SITE.name_en_short) + '</span></a>' +
        (test ? '<span class="tag">' + esc(t('test')) + '</span>' : '') +
        '<div class="mast-ctl">' +
          '<div class="datebar" id="datebar">' +
            '<button class="db-step" type="button" data-act="day" data-date="' + prev + '"' + (prev ? '' : ' disabled') + ' aria-label="' + esc(t('prev_day')) + '" title="' + esc(t('prev_day') + ' · ' + (prev || t('no_more'))) + '">' + ICON.chevL + '</button>' +
            '<button class="db-date" type="button" data-act="cal" aria-haspopup="dialog" aria-expanded="false" aria-controls="cal" title="' + esc(t('pick_date')) + '"><time datetime="' + esc(DATE || '') + '">' + dhtml + '</time><span class="wd">' + esc(dl.wd) + '</span>' + ICON.chevD + '</button>' +
            '<button class="db-step" type="button" data-act="day" data-date="' + next + '"' + (next ? '' : ' disabled') + ' aria-label="' + esc(t('next_day')) + '" title="' + esc(t('next_day') + ' · ' + (next || t('no_more'))) + '">' + ICON.chevR + '</button>' +
            '<div class="cal glass" id="cal" role="dialog" aria-label="' + esc(t('pick_date')) + '" hidden></div>' +
          '</div>' +
          '<div class="seg" role="group" aria-label="' + esc(t('lang_label')) + '">' +
            '<button type="button" data-act="lang" data-l="zh" aria-pressed="' + (lang === 'zh') + '">中</button>' +
            '<button type="button" data-act="lang" data-l="en" aria-pressed="' + (lang === 'en') + '" lang="en">EN</button></div>' +
          '<button class="icon-btn" type="button" data-act="theme" aria-label="' + esc(t(effTheme() === 'dark' ? 'to_light' : 'to_dark')) + '">' + ICON.sun + ICON.moon + '</button>' +
        '</div>' +
      '</div>' +
      '<h1 class="mast-title rv' + (en ? ' lat' : '') + '"' + (en ? ' lang="en"' : '') + '>' + amp(en ? SITE.name_en : SITE.name_zh) + '</h1>' +
      '<p class="mast-sub rv' + (en ? ' cjk' : '') + '"' + (en ? ' lang="zh-CN"' : ' lang="en"') + '>' + amp(en ? SITE.name_zh : SITE.name_en) + '</p>';
    // 页脚一行话：文字在 site/tools/v3_site.py 的 FOOT_ZH / FOOT_EN（{accent} 换成主题色名，{past} 换成“往期”按钮）
    var acc = ISSUE && ISSUE.theme && ISSUE.theme.accent, akey = root.getAttribute('data-accent') || acc, an = ACCENT_NAME[akey];
    var aname = an ? an[en ? 1 : 0] : ((ISSUE && ISSUE.theme && (en ? ISSUE.theme.name_en : ISSUE.theme.name_zh)) || '');
    if (!root.hasAttribute('data-accent-lock') && ISSUE && ISSUE.theme) aname = (en ? ISSUE.theme.name_en : ISSUE.theme.name_zh) || aname;
    var past = '<button type="button" data-act="cal">' + esc((SITE.foot_past || [])[en ? 1 : 0] || t('foot_past')) + '</button>';
    var line = SITE['foot_' + (en ? 'en' : 'zh')] || t('foot_line');
    if (!aname) line = line.replace(/\s*·?\s*[^·]*\{accent\}[^·]*/, '');
    // 11-10 加：“往期”后面紧跟一段“反馈”（点开左下角的反馈框，见下面“读者反馈”一节）；页脚文字本身仍取自 v3_site.py
    var fbBtn = '<button type="button" data-act="fb" aria-haspopup="dialog" aria-expanded="' + fbIsOpen() + '" aria-controls="fb">' + esc(t('fb_link')) + '</button>';
    var segs = [];
    line.split(' · ').forEach(function (s) { segs.push(s); if (s.indexOf('{past}') >= 0) segs.push('{fb}'); });
    if (segs.indexOf('{fb}') < 0) segs.push('{fb}');
    // 按“ · ”分段，每段内部不换行（窄屏只在分隔点处折行，刊名不会被拆开）
    $('#foot').innerHTML = '<p>' + segs.map(function (s) {
      return '<span class="ft-seg">' + esc(s).replace('{accent}', esc(aname)).replace('{past}', past).replace('{fb}', fbBtn) + '</span>';
    }).join(' · ') + '</p>';
    if (!animOK()) $$('#top .rv').forEach(function (el) { el.classList.add('in'); });
    else requestAnimationFrame(function () { $$('#top .rv').forEach(function (el) { el.classList.add('in'); }); });
  }
  var calMonth = null;
  function renderCal() {
    var ds = dates();
    if (!calMonth) calMonth = (DATE || ds[ds.length - 1] || '').slice(0, 7);
    var y = +calMonth.slice(0, 4), m = +calMonth.slice(5, 7);
    var first = new Date(y, m - 1, 1), days = new Date(y, m, 0).getDate();
    var lead = (first.getDay() + 6) % 7;   // 周一开头
    var minM = (ds[0] || calMonth).slice(0, 7), maxM = (ds[ds.length - 1] || calMonth).slice(0, 7);
    var title = lang === 'en' ? first.toLocaleString('en', { month: 'long', year: 'numeric' }) : y + ' 年 ' + m + ' 月';
    var wds = t('wd_s'), h = '';
    for (var k = 1; k <= 7; k++) h += '<span class="dw">' + wds[k % 7] + '</span>';
    for (var b = 0; b < lead; b++) h += '<span></span>';
    for (var d = 1; d <= days; d++) {
      var iso = y + '-' + pad2(m) + '-' + pad2(d);
      if (ds.indexOf(iso) >= 0) h += '<button type="button" data-act="pickdate" data-date="' + iso + '"' + (iso === DATE ? ' aria-current="date"' : '') + ' aria-label="' + iso + '">' + d + '</button>';
      else h += '<span class="d" aria-hidden="true">' + d + '</span>';
    }
    $('#cal').innerHTML = '<div class="cal-h"><button class="icon-btn sm" type="button" data-act="calm" data-d="-1"' + (calMonth <= minM ? ' disabled' : '') + ' aria-label="' + esc(t('cal_prev')) + '">' + ICON.chevL + '</button>' +
      '<span>' + esc(title) + '</span><button class="icon-btn sm" type="button" data-act="calm" data-d="1"' + (calMonth >= maxM ? ' disabled' : '') + ' aria-label="' + esc(t('cal_next')) + '">' + ICON.chevR + '</button></div>' +
      '<div class="cal-g">' + h + '</div><p class="cal-f">' + esc(t('cal_count', { n: ds.length, d: ds[ds.length - 1] || '' })) + '</p>';
  }
  function openCal() {
    var c = $('#cal'); if (!c) return;
    calMonth = null; renderCal(); c.hidden = false;
    $('.db-date').setAttribute('aria-expanded', 'true');
    var cur = $('[aria-current="date"]', c) || $('button[data-act="pickdate"]', c);
    if (cur) cur.focus();
  }
  function closeCal() {
    var c = $('#cal'); if (!c || c.hidden) return;
    c.hidden = true; $('.db-date').setAttribute('aria-expanded', 'false');
  }

  /* ===================== 文字小工具 ===================== */
  // 上标：CSS 在 [n] 前面加了一个看不见的“连字符”（U+2060），上标永远和前一个字在同一行
  function citeTag(id) { return id ? '<sup class="cite" data-s="' + esc(id) + '"><a href="#src-' + esc(id) + '">[?]</a></sup>' : ''; }
  function cites(ids) { return (ids || []).filter(Boolean).map(citeTag).join(''); }
  function rich(s) {
    var h = esc(s);
    h = h.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
    if (lang === 'zh') h = h.replace(/（([A-Za-z][^（）]{0,60})）/g, '<span class="gloss">（$1）</span>');
    return h.replace(/\[\^(s\d+)\]/g, function (m, id) { return citeTag(id); });
  }
  function paras(arr) { return (arr || []).map(function (p) { return '<p>' + rich(p) + '</p>'; }).join(''); }
  function isSunday() { return !!ISSUE && ISSUE.weekday_zh === '星期日'; }
  // 周末两版（11-01 晚定）：有深度／深谈那一条时，周六 'sat'、周日 'sun'；工作日 ''（组装脚本写在 ISSUE.edition，旧数据按星期几推）
  function edition() {
    if (!ISSUE) return '';
    if (ISSUE.edition) return ISSUE.edition;
    return ((ISSUE.order || {}).deep || []).length ? (isSunday() ? 'sun' : 'sat') : '';
  }
  // 周末版面的几个上限（site/tools/v3_site.py 的 WEEKEND、LAYER_NUMBERS_MAX）
  function WK(k, d) { var w = (ISSUE && ISSUE.weekend) || {}; return w[k] != null ? w[k] : d; }
  function deepStory() { return S((((ISSUE && ISSUE.order) || {}).deep || []).filter(S)[0]); }
  function kindLabel(k) { return t('kind_' + (k === 'deep' && isSunday() ? 'talk' : k)); }
  function kick(st, extra) {
    var s = st.status || 'reported';
    return '<span class="k-kind">' + esc(kindLabel(st.kind)) + '</span><span class="k-dot" aria-hidden="true">·</span>' +
      '<span class="k-st ' + esc(s) + '">' + esc(t('status_' + s)) + '</span><span class="k-dot" aria-hidden="true">·</span>' +
      '<span class="k-reg">' + esc(t('region_' + (st.region === 'cn' ? 'cn' : 'intl'))) + '</span>' + (extra || '');
  }
  function spectrum(cov) {
    if (!cov) return '';
    var z = cov.zh.length, e = cov.en.length, so = cov.social.length;
    if (!z && !e && !so) return '';
    var nm = function (a) { return a.map(function (x) { return lang === 'en' && cov.names_en && cov.names_en[x] ? cov.names_en[x] : x; }).join(lang === 'en' ? ', ' : '、'); };
    var lines = [t('spec_tip')];
    if (z) lines.push(t('spec_zh') + (lang === 'en' ? ': ' : '：') + nm(cov.zh));
    if (e) lines.push(t('spec_en') + (lang === 'en' ? ': ' : '：') + nm(cov.en));
    if (so) lines.push(t('spec_so') + (lang === 'en' ? ': ' : '：') + nm(cov.social));
    var cnt = [z ? t('spec_zh_n', { n: z }) : '', e ? t('spec_en_n', { n: e }) : '', so ? t('spec_so_n', { n: so }) : ''].filter(Boolean).join(' · ');   // 0 家的不显示
    return '<span class="spec" tabindex="0" data-tip="' + esc(lines.join('\n')) + '">' +
      '<span class="spec-bar" aria-hidden="true">' + (z ? '<i class="zh" style="flex:' + z + '"></i>' : '') + (e ? '<i class="en" style="flex:' + e + '"></i>' : '') + (so ? '<i class="so" style="flex:' + so + '"></i>' : '') + '</span>' +
      '<span>' + esc(cnt) + '</span></span>';
  }
  function imgTag(im, eager, sizes) {
    im = normImage(im); if (!im) return '';
    var set = im.src_sm ? ' srcset="' + esc(asset(im.src_sm)) + ' ' + im.w_sm + 'w, ' + esc(asset(im.src)) + ' ' + im.w + 'w" sizes="' + (sizes || '(max-width: 900px) 100vw, 600px') + '"' : '';
    return '<img src="' + esc(asset(im.src)) + '"' + set + ' width="' + (im.w || 1400) + '" height="' + (im.h || 788) + '" alt="' + esc(pick(im, 'alt')) + '"' +
      (eager ? ' fetchpriority="high"' : (STATIC ? '' : ' loading="lazy"')) + ' decoding="async">';
  }
  function figure(im, cls, eager, sizes, seed) {
    if (!normImage(im)) return seed ? '<figure class="' + cls + ' cover" aria-hidden="true">' + coverSVG(seed) + '</figure>' : '';
    return '<figure class="' + cls + '">' + imgTag(im, eager, sizes) + '</figure>';   // v3.2：不再挂“AI 生成配图”，说明统一放在参考来源末尾
  }
  /* 缺图时的抽象封面（v3.2）：程序画的 SVG，颜色全取当天主题色（--accent-rgb），深浅色自动跟着变；
   * 图案按条目号定（同一条每次都一样）：一团柔光、一组同心弧、一片渐隐的点阵、几条带节点的“数据线”。不是 AI 生成的图，所以不挂“AI 生成配图”。 */
  function hashStr(s) { var h = 2166136261; s = String(s || ''); for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function coverSVG(seed) {
    var R = rng(hashStr(seed)), W = 1600, H = 900, f = function (n) { return Math.round(n); };
    var A = function (o) { return 'rgb(var(--accent-rgb) / ' + o + ')'; };
    var gx = f(W * (0.2 + R() * 0.6)), gy = f(H * (0.25 + R() * 0.5)), side = R() < 0.5 ? -1 : 1;
    var cx = f(gx + side * W * (0.18 + R() * 0.12)), cy = f(gy + (R() - 0.5) * H * 0.4), id = 'cv' + hashStr(seed).toString(36);
    var h = '<svg class="cover-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">' +
      '<defs><radialGradient id="' + id + 'g" cx="' + (gx / W) + '" cy="' + (gy / H) + '" r=".62"><stop offset="0" style="stop-color:rgb(var(--accent-rgb));stop-opacity:.6"/>' +
      '<stop offset=".45" style="stop-color:rgb(var(--accent-rgb));stop-opacity:.22"/><stop offset="1" style="stop-color:rgb(var(--accent-rgb));stop-opacity:0"/></radialGradient>' +
      '<linearGradient id="' + id + 'l" x1="0" y1="0" x2="1" y2="1"><stop offset="0" style="stop-color:rgb(var(--accent-rgb));stop-opacity:.14"/><stop offset="1" style="stop-color:rgb(var(--accent-rgb));stop-opacity:.03"/></linearGradient></defs>' +
      '<rect width="' + W + '" height="' + H + '" style="fill:var(--glass-solid)"/><rect width="' + W + '" height="' + H + '" fill="url(#' + id + 'l)"/>' +
      '<rect width="' + W + '" height="' + H + '" fill="url(#' + id + 'g)"/>';
    for (var k = 0; k < 7; k++) h += '<circle cx="' + cx + '" cy="' + cy + '" r="' + (110 + k * 92) + '" fill="none" style="stroke:' + A((0.5 - k * 0.055).toFixed(2)) + '" stroke-width="' + (k ? 1.4 : 2.4) + '"' + (k % 3 === 2 ? ' stroke-dasharray="3 9"' : '') + '/>';
    for (var y = 40; y < H; y += 44) for (var x = 40; x < W; x += 44) {   // 点阵：离柔光越近越浓，远处不画
      var d = Math.sqrt((x - gx) * (x - gx) + (y - gy) * (y - gy)) / (W * 0.42);
      if (d < 1 && R() > d * 0.55) h += '<circle cx="' + x + '" cy="' + y + '" r="2.2" style="fill:' + A((0.5 * (1 - d)).toFixed(2)) + '"/>';
    }
    for (var j = 0; j < 3; j++) {                                          // 数据线：几段折线，节点上一个小圆
      var yy = f(H * (0.22 + j * 0.27 + (R() - 0.5) * 0.08)), xx = f(-40 + R() * 200), pts = [[xx, yy]];
      while (xx < W + 40) { xx += f(120 + R() * 220); yy += f((R() - 0.5) * 120); pts.push([xx, yy]); }
      h += '<polyline points="' + pts.map(function (p) { return p.join(','); }).join(' ') + '" fill="none" style="stroke:' + A(j === 1 ? 0.55 : 0.28) + '" stroke-width="' + (j === 1 ? 2.2 : 1.4) + '" stroke-linejoin="round"/>';
      pts.slice(1, -1).forEach(function (p, i) { if (i % 2 === j % 2) h += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="' + (j === 1 ? 7 : 5) + '" style="fill:var(--glass-solid);stroke:' + A(j === 1 ? 0.8 : 0.4) + '" stroke-width="2"/>'; });
    }
    return h + '</svg>';
  }
  // 版块标题：小编号＋中文大标题＋另一种语言的小标题＋右侧说明
  function head(key, note) {
    SECN++;
    var zh = lang === 'zh', alt = (zh ? I18N.en : I18N.zh)['sec_' + key];
    return '<div class="sec-h rv"><span class="sec-n" aria-hidden="true">' + pad2(SECN) + '</span>' +
      '<h2 id="h-' + key + '">' + esc(t('sec_' + key)) + '</h2>' +
      '<span class="sec-alt' + (zh ? '' : ' cjk') + '" lang="' + (zh ? 'en' : 'zh-CN') + '">' + esc(alt) + '</span>' +
      (note ? '<p class="sec-note">' + note + '</p>' : '') + '</div>';
  }
  // “为什么重要”：先是转述的判断（带出处），再是我们自己的理解（v3.2：用一个小标签隔开，句子里不再反复写“我们的理解是”）
  function whyBox(st) {
    var w = st['why_' + lang] || st.why_zh || [], r = st['read_' + lang] || st.read_zh || [];
    if (!w.length && !r.length) return '';
    return '<div class="why"><p class="why-k">' + esc(t('why')) + '</p>' + paras(w) +
      (r.length ? '<div class="our-read"><p class="our-k">' + esc(t('our_read')) + '</p>' + paras(r) + '</div>' : '') + '</div>';
  }
  function hasPod() { return !!(ISSUE && ISSUE.media && ISSUE.media.podcast); }
  function hasVid() { return !!(ISSUE && ISSUE.media && ISSUE.media.video); }
  function actions(st, extra) {
    var a = '';
    if (st.listen != null && hasPod()) a += '<button class="btn sm" type="button" data-act="listen" data-t="' + st.listen + '">' + ICON.headph + esc(t('listen_seg')) + '<span class="t">' + fmtTime(st.listen) + '</span></button>';
    if (st.watch) a += '<button class="btn sm" type="button" data-act="watch" data-scene="' + st.watch.scene + '">' + ICON.film + esc(t('watch_seg')) + '<span class="t">' + fmtTime(st.watch.t) + '</span></button>';
    else if (st.kind === 'headline' && hasVid()) a += '<span class="btn sm off" aria-disabled="true">' + ICON.film + esc(t('watch_seg')) + '<span class="t">' + esc(t('watch_none')) + '</span></span>';
    return a || extra ? '<div class="acts">' + a + (extra || '') + '</div>' : '';
  }
  function numbersGrid(nums) {
    if (!nums || !nums.length) return '';
    return '<div class="kn">' + nums.map(function (n) {
      var v = lang === 'en' && n.value_en ? n.value_en : n.value;
      return '<div class="kn-i"><b>' + esc(v) + '</b><span>' + esc(pick(n, 'label')) + citeTag(n.cite) + '</span></div>';
    }).join('') + '</div>';
  }
  function srcLine(st) { return st.sources && st.sources.length ? '<p class="srcline">' + esc(t('sources_of')) + ' ' + cites(st.sources) + '</p>' : ''; }

  /* ===================== 编号页签（Pager）：HTML ===================== */
  function pagerHTML(key, label, items, slides, dur) {
    var N = items.length, cur = Math.min(UI.pg[key] || 0, N - 1);
    if (N === 1) return '<div class="stage glass rv single"><div class="slides"><article class="slide on">' + slides[0] + '</article></div></div>';
    var tabs = items.map(function (it, i) {
      var on = i === cur;
      return '<button class="pg' + (on ? ' on' : '') + '" type="button" role="tab" id="pg-' + key + '-' + i + '" aria-controls="sl-' + key + '-' + i + '" aria-selected="' + on + '" tabindex="' + (on ? 0 : -1) + '" title="' + esc(it) + '">' +
        '<span class="pg-fill" aria-hidden="true"></span><span class="pg-n">' + (i + 1) + '</span><span class="pg-t">' + esc(it) + '</span></button>';
    }).join('');
    var body = slides.map(function (h, i) {
      var on = i === cur;
      return '<article class="slide' + (on ? ' on' : '') + '" role="tabpanel" id="sl-' + key + '-' + i + '" aria-labelledby="pg-' + key + '-' + i + '"' + (on ? '' : ' aria-hidden="true" inert') + '>' + h + '</article>';
    }).join('');
    return '<div class="stage glass rv' + (N >= 4 ? ' many' : '') + '" data-pager="' + key + '" role="region" aria-roledescription="' + esc(t('carousel')) + '" aria-label="' + esc(label) + '" style="--pg-dur:' + (dur || 8000) + 'ms">' +
      '<div class="stage-bar"><div class="pager" role="tablist" aria-label="' + esc(label) + '">' + tabs + '</div>' +
      '<div class="stage-ctl"><span class="count" aria-hidden="true"><b>' + (cur + 1) + '</b><span class="sl">/</span>' + N + '</span>' +
      '<button class="icon-btn sm pg-play" type="button" aria-label="' + esc(t('pg_pause')) + '">' + ICON.pause + ICON.play + '</button></div></div>' +
      '<div class="slides">' + body + '</div></div>';
  }

  /* ===================== 编号页签（Pager）：交互 ===================== */
  // 两种外观共用这套轮播逻辑：编号页签（头条、要闻、对照）和预告时间轴（v3.2）；SEL 是各自的类名
  var PG_SEL = { tab: '.pg', slide: '.slide', count: '.count b', btn: '.pg-play', box: '.slides', bar: '.stage-bar', list: '.pager', anim: 'pgfill', fill: '.pg.on .pg-fill' };
  var WTL_SEL = { tab: '.wn', slide: '.wp', count: null, btn: '.wtl-play', box: '.wtl-panels', bar: '.wtl-axis', list: '.wtl-axis', anim: 'wring', fill: '.wn.on .wn-ring circle' };
  function Pager(el, onShow, sel) {
    var self = this;
    sel = this.sel = sel || PG_SEL;
    this.el = el; this.key = el.getAttribute('data-pager'); this.onShow = onShow;
    this.tabs = $$(sel.tab, el); this.slides = $$(sel.slide, el); this.N = this.tabs.length; this.cur = 0;
    for (var i = 0; i < this.N; i++) if (this.tabs[i].classList.contains('on')) this.cur = i;
    this.countEl = sel.count ? $(sel.count, el) : null; this.btn = $(sel.btn, el); this.box = $(sel.box, el); this.bar = $(sel.bar, el);
    this.hover = false; this.kbd = false; this.touch = false; this.inView = false; this.auto = false;
    // 点页签：换到那一张并停止自动轮播（点的就是当前这一张也停，因为鼠标停上去时它往往已经换过来了）
    // v3.1 鼠标停在页签上约 150 毫秒就换过去，不用点；中途移开就取消。手指、键盘不受影响。悬停换页不关自动轮播，鼠标离开这一块后接着轮播
    var hv = 0;
    this.tabs.forEach(function (tb, k) {
      tb.addEventListener('click', function () { if (k === self.cur) self.setAuto(false); else self.show(k, 0, true); });
      tb.addEventListener('pointerenter', function (e) {
        if (e.pointerType !== 'mouse' || !HOVER()) return;
        clearTimeout(hv);
        hv = setTimeout(function () { hv = 0; self.show(k, 0, false); }, 150);
      });
      tb.addEventListener('pointerleave', function () { clearTimeout(hv); hv = 0; });
    });
    $(sel.list, el).addEventListener('keydown', function (e) {
      var k = e.key, j = null, d = 0;
      if (k === 'ArrowRight' || k === 'ArrowDown') { j = self.cur + 1; d = 1; }
      else if (k === 'ArrowLeft' || k === 'ArrowUp') { j = self.cur - 1; d = -1; }
      else if (k === 'Home') j = 0;
      else if (k === 'End') j = self.N - 1;
      if (j === null) return;
      e.preventDefault();
      self.show(j, d, true);
      self.tabs[self.cur].focus();
    });
    el.addEventListener('mouseenter', function () { if (HOVER()) { self.hover = true; self.hold(); } });
    el.addEventListener('mouseleave', function () { self.hover = false; self.hold(); });
    el.addEventListener('focusin', function (e) {   // 键盘焦点进来时暂停（鼠标点一下不算，免得一直停着）
      var fv = false;
      try { fv = e.target.matches(':focus-visible'); } catch (x) { fv = true; }
      self.kbd = fv; self.hold();
    });
    el.addEventListener('focusout', function (e) { if (!el.contains(e.relatedTarget)) { self.kbd = false; self.hold(); } });
    // 读者在这一张里点了按钮（读全文、听这一段、详情…）：说明在看，停止自动轮播
    this.box.addEventListener('click', function (e) { if (e.target.closest('button, a, [data-act]')) self.setAuto(false); });
    // 手机：手指按着时暂停；左右滑动换一张
    var box = this.box, sx = null, sy = 0;
    box.addEventListener('pointerdown', function (e) { if (e.pointerType === 'mouse') return; sx = e.clientX; sy = e.clientY; self.touch = true; self.hold(); });
    box.addEventListener('pointerup', function (e) {
      self.touch = false; self.hold();
      if (sx === null) return;
      var dx = e.clientX - sx, dy = e.clientY - sy;
      sx = null;
      if (Math.abs(dx) > 44 && Math.abs(dx) > Math.abs(dy) * 1.3) self.show(self.cur + (dx < 0 ? 1 : -1), dx < 0 ? 1 : -1, true);
    });
    box.addEventListener('pointercancel', function () { sx = null; self.touch = false; self.hold(); });
    this.btn.addEventListener('click', function () { self.setAuto(!self.auto); });
    el.addEventListener('animationend', function (e) { if (e.animationName === sel.anim && self.auto) self.show(self.cur + 1, 1, false); });
    // 只在“编号页签那一行在屏幕上、而且这一块至少露出一半（或占满屏幕）”时自动翻页；读者往下读到长内容里时就停着
    if ('IntersectionObserver' in window) {
      var ratio = 0, barIn = false, upd = function () {
        var vh = window.innerHeight || 800, h = el.offsetHeight || 1;
        self.inView = barIn && (ratio >= 0.5 || ratio * h >= vh * 0.6); self.hold();
      };
      new IntersectionObserver(function (es) { ratio = es[0].intersectionRatio; upd(); }, { threshold: [0, 0.25, 0.5, 0.75, 1] }).observe(el);
      new IntersectionObserver(function (es) { barIn = es[0].isIntersecting; upd(); }, { threshold: 1 }).observe(this.bar);
    } else this.inView = true;
    this.setAuto(animOK());          // 减少动态效果、截图模式：不自动轮播（读者可以点播放键打开）
    if (STATIC) el.classList.add('auto');   // 截图里画成“正在轮播”的样子（进度停在中途），不会真的翻页
    this.hold();
  }
  Pager.prototype.hold = function () {
    this.el.classList.toggle('hold', this.hover || this.kbd || this.touch || !this.inView || document.hidden);
  };
  Pager.prototype.restartFill = function () {
    var f = $(this.sel.fill, this.el);
    if (!f) return;
    f.style.animation = 'none'; void f.getBoundingClientRect(); f.style.animation = '';
  };
  Pager.prototype.setAuto = function (on) {
    this.auto = on;
    this.el.classList.toggle('auto', on);
    this.btn.setAttribute('aria-label', t(on ? 'pg_pause' : 'pg_play'));
    if (on) this.restartFill();
  };
  Pager.prototype.show = function (i, dir, user) {
    i = (i + this.N) % this.N;
    if (i === this.cur) return;
    if (user) this.setAuto(false);
    var d = dir || (i > this.cur ? 1 : -1), a = this.slides[this.cur], b = this.slides[i], box = this.box, h0 = box.getBoundingClientRect().height;
    if (animOK()) {   // 新的一张从行进方向那一侧进来，旧的一张往反方向退出
      b.style.transition = 'none'; b.style.setProperty('--x', (32 * d) + 'px'); void b.offsetWidth; b.style.transition = '';
      a.style.setProperty('--x', (-32 * d) + 'px');
    }
    a.classList.remove('on'); a.setAttribute('aria-hidden', 'true'); a.inert = true;
    b.classList.add('on'); b.removeAttribute('aria-hidden'); b.inert = false;
    var ta = this.tabs[this.cur], tb = this.tabs[i];
    ta.classList.remove('on'); ta.setAttribute('aria-selected', 'false'); ta.tabIndex = -1;
    tb.classList.add('on'); tb.setAttribute('aria-selected', 'true'); tb.tabIndex = 0;
    this.tabs.forEach(function (x, k) { x.classList.toggle('done', k < i); });   // 时间轴：走过的线段染成主题色
    this.el.style.setProperty('--cur', i);
    this.cur = i; UI.pg[this.key] = i;
    if (this.countEl) this.countEl.textContent = String(i + 1);
    // 版块高度跟着新的一张平滑变化。先放开上一次动画留下的固定高度，量出新一张的真实高度（连续快速换页时也对）
    clearTimeout(this._ht);
    box.style.transition = 'none'; box.style.height = '';
    var h1 = box.offsetHeight;
    if (animOK() && Math.abs(h1 - h0) > 2) {
      box.style.height = h0 + 'px'; void box.offsetHeight;
      box.style.transition = 'height .62s cubic-bezier(.22,.61,.36,1)'; box.style.height = h1 + 'px';
      this._ht = setTimeout(function () { box.style.height = ''; box.style.transition = ''; }, 680);
    } else box.style.transition = '';
    if (this.auto) this.restartFill();
    if (this.onShow) this.onShow(i);
  };
  function mountPagers() {
    PAGERS = {};
    $$('#c-main [data-pager]').forEach(function (el) {
      PAGERS[el.getAttribute('data-pager')] = new Pager(el, function () { observeNew(); }, el.classList.contains('wtl') ? WTL_SEL : PG_SEL);
    });
  }
  document.addEventListener('visibilitychange', function () { Object.keys(PAGERS).forEach(function (k) { PAGERS[k].hold(); }); });

  /* ===================== 各版块 ===================== */
  function secCard() {
    var ed = edition();
    if (ed && deepStory()) return secCardWeekend(ed);
    var c = ISSUE.card || {}, d = ISSUE.date, term = c.term || {}, heads = c.headlines || [];
    var pod = ISSUE.media && ISSUE.media.podcast, vid = ISSUE.media && ISSUE.media.video;
    var mins = Math.round((pod && pod.duration || 0) / 60), secs = Math.round(vid && vid.duration || 0);
    var wd = pick(ISSUE, 'weekday');
    var acts = (pod ? '<button class="btn pri" type="button" data-act="listen" data-t="">' + ICON.headph + esc(t('listen_n', { n: mins })) + '</button>' : '') +
      (vid ? '<button class="btn' + (pod ? '' : ' pri') + '" type="button" data-act="watch" data-scene="0">' + ICON.film + esc(t('watch_n', { n: secs })) + '</button>' : '');
    return '<section class="sec hero-sec" id="sec-card" aria-label="' + esc(t('three')) + '"><div class="hero glass rv">' +
      '<div class="hero-tx">' +
        '<p class="hero-date"><span class="d" lang="en">' + esc(d.slice(5).replace('-', '.')) + '</span><span class="w"><b>' + esc(wd) + '</b>' + esc(d.slice(0, 4)) + '</span></p>' +
        '<h2 class="hero-k">' + esc(t('three')) + '</h2>' +
        (heads.length ? '<ol class="three">' + heads.map(function (h, i) {
          var tx = '<span class="n" aria-hidden="true">' + (i + 1) + '</span><span class="tx">' + esc(h[lang] || h.zh) + '</span>';
          return '<li>' + (h.ref && S(h.ref) ? '<button type="button" data-act="go" data-id="' + esc(h.ref) + '">' + tx + ICON.go + '</button>' : '<span class="row">' + tx + '</span>') + '</li>';
        }).join('') + '</ol>' : '') +
        (term.zh || term.en ? '<button class="termchip" type="button" data-act="go" data-id="term"><span class="k">' + esc(t('term_k')) + '</span><b>' + esc(lang === 'en' ? (term.en || term.zh) : term.zh) + '</b>' +
          ((lang === 'en' ? term.zh : term.en) ? '<i' + (lang === 'en' ? ' class="cjk" lang="zh-CN"' : ' lang="en"') + '>' + esc(lang === 'en' ? term.zh : term.en) + '</i>' : '') + ICON.go + '</button>' : '') +
        (acts ? '<div class="hero-acts">' + acts + '</div>' : '') +
      '</div>' + figure(c.image, 'hero-fig', true, '(max-width: 900px) 100vw, 640px', 'card-' + d) +
      '</div></section>';
  }
  /* 周末的首屏卡（11-01 晚定，代替"今日三件事"）：
   *   周六"今日深度"：深度题的大标题、一句话（摘要）、"听深度"，下面列两三条快讯标题（点了跳到那条快讯）；
   *   周日"本周深谈"：大标题、核心问题、一句话结论、"听深谈"。
   * "听深度／听深谈"从第一层那一章开头放，旁边写这一题在播客里大约几分钟；有视频时另有"看 N 秒"（视频只讲这一题）。 */
  function secCardWeekend(ed) {
    var c = ISSUE.card || {}, d = ISSUE.date, st = deepStory(), sun = ed === 'sun';
    var vid = ISSUE.media && ISSUE.media.video, secs = Math.round(vid && vid.duration || 0), sp = deepSpan(st);
    var wd = pick(ISSUE, 'weekday'), label = t(sun ? 'sec_card_sun' : 'sec_card_sat');
    var acts = (hasPod() && sp.at != null ? '<button class="btn pri" type="button" data-act="listen" data-t="' + sp.at + '">' + ICON.headph + esc(t(sun ? 'listen_talk' : 'listen_deep')) +
        (sp.mins ? '<span class="t">' + esc(t('listen_min', { n: sp.mins })) + '</span>' : '') + '</button>' : '') +
      (vid ? '<button class="btn' + (hasPod() ? '' : ' pri') + '" type="button" data-act="watch" data-scene="0">' + ICON.film + esc(t('watch_n', { n: secs })) + '</button>' : '');
    var body;
    if (sun) {
      var q = pick(st, 'question') || pick(st, 'summary'), cc = pick(st, 'conclusion');
      body = (q ? '<div class="wk-line"><p class="wk-lk">' + esc(t('core_q')) + '</p><p class="wk-q">' + rich(q) + '</p></div>' : '') +
        (cc ? '<div class="wk-line wk-concl"><p class="wk-lk">' + esc(t('one_line')) + '</p><p class="wk-c">' + rich(cc) + '</p></div>' : '');
    } else {
      // 快讯标题：日卡 headlines 里指向快讯的几行（写稿时挑的短标题）；不够两条就按快讯顺序补
      var fl = ((ISSUE.order || {}).flash || []).filter(S), rows = [], seen = {};
      (c.headlines || []).forEach(function (h) { var s = h.ref && S(h.ref); if (s && s.kind === 'flash' && !seen[h.ref]) { seen[h.ref] = 1; rows.push({ id: h.ref, tx: h[lang] || h.zh }); } });
      if (rows.length < 2) fl.forEach(function (id) { if (!seen[id] && rows.length < 2) { seen[id] = 1; rows.push({ id: id, tx: pick(S(id), 'title') }); } });
      rows = rows.slice(0, WK('card_flash_max', 3));
      body = (pick(st, 'summary') ? '<p class="wk-dek">' + rich(pick(st, 'summary')) + '</p>' : '');
      var list = rows.length ? '<div class="wk-flash"><p class="wk-lk">' + esc(t('card_flash')) + '</p><ol class="three sm">' + rows.map(function (r, i) {
        return '<li><button type="button" data-act="go" data-id="' + esc(r.id) + '"><span class="n" aria-hidden="true">' + (i + 1) + '</span><span class="tx">' + esc(r.tx) + '</span>' + ICON.go + '</button></li>';
      }).join('') + '</ol></div>' : '';
    }
    return '<section class="sec hero-sec" id="sec-card" aria-label="' + esc(label) + '"><div class="hero wk wk-' + ed + ' glass rv">' +
      '<div class="hero-tx">' +
        '<p class="hero-date"><span class="d" lang="en">' + esc(d.slice(5).replace('-', '.')) + '</span><span class="w"><b>' + esc(wd) + '</b>' + esc(d.slice(0, 4)) + '</span></p>' +
        '<p class="wk-k">' + esc(label) + '</p>' +
        '<h2 class="wk-title"><button type="button" data-act="go" data-id="' + esc(st.id) + '">' + esc(pick(st, 'title')) + '</button></h2>' +
        body + (acts ? '<div class="hero-acts">' + acts + '</div>' : '') + (sun ? '' : list) +
      '</div>' + figure(c.image || st.image, 'hero-fig', true, '(max-width: 900px) 100vw, 640px', 'card-' + d) +
      '</div></section>';
  }
  function numPart(s, cls) {
    s = String(s || '').trim();
    if (!s) return '';
    if (s === '约') return '<span class="approx ' + cls + '">' + esc(s) + '</span>';   // “约”排成小字
    return '<span class="' + (hasCJK(s) ? 'u' : 'sym') + ' ' + cls + '">' + esc(s) + '</span>';
  }
  function secNumbers() {
    var N = ISSUE.numbers || [], ed = edition();
    if (ed) N = N.slice(0, WK('numbers_max', ed === 'sun' ? 0 : 4));   // 周六最多 4 格；周日不单列（关键数字在深谈各层里）
    if (!N.length) return '';
    var tiles = N.map(function (n, i) {
      var st = S(n.story) || {}, L = n[lang] || n.zh;
      var full = ((L.pre || '') + fmtN(L.to, L.dec, L.comma) + (L.suf ? (hasCJK(L.suf) ? ' ' : '') + L.suf : '')).trim();
      var arrow = n.dir && n.change ? '<span class="arr">' + ICON['ar_' + n.dir] + '</span>' : '';   // 只有真实的涨跌或前后变化才有箭头
      var goKey = 'go_' + (st.kind === 'headline' || st.kind === 'brief' || st.kind === 'flash' ? st.kind : st.kind === 'cn_intl' ? 'pair' :
        st.kind === 'deep' ? (isSunday() ? 'talk' : 'deep') : 'story');
      return '<div class="numt glass rv" style="--d:' + (i * 70) + 'ms" data-story="' + esc(n.story) + '">' +
        '<button class="cover" type="button" data-act="go" data-id="' + esc(n.story) + '" aria-label="' + esc(pick(n, 'label') + '：' + full + '。' + t(goKey)) + '"></button>' +
        '<p class="num-k">' + kick(st) + '</p>' +
        '<p class="num-v"><span class="sr">' + esc(full) + '</span><span class="num-vv" aria-hidden="true">' + arrow + numPart(L.pre, 'pre') +
        '<span class="cnt" data-to="' + L.to + '" data-from="' + (L.from != null ? L.from : 0) + '" data-dec="' + (L.dec || 0) + '" data-comma="' + (L.comma ? 1 : 0) + '">' + fmtN(L.to, L.dec, L.comma) + '</span>' +
        numPart(L.suf, 'suf') + '</span></p>' +
        '<p class="num-l">' + esc(pick(n, 'label')) + cites(n.cite) + '</p>' +
        '<p class="num-s">' + esc(pick(n, 'sub')) + '</p>' +
        '<span class="num-go" aria-hidden="true">' + esc(t(goKey)) + ' →</span></div>';
    }).join('');
    return '<section class="sec" id="sec-numbers">' + head('numbers') + '<div class="nums n' + N.length + '">' + tiles + '</div></section>';
  }
  function secMedia() {
    var pod = ISSUE.media && ISSUE.media.podcast, vid = ISSUE.media && ISSUE.media.video;
    if (!pod && !vid) return '';
    var mins = Math.round((pod && pod.duration || 0) / 60), secs = Math.round(vid && vid.duration || 0);
    var im = normImage(ISSUE.card && ISSUE.card.image), both = !!(pod && vid);
    if (!both) UI.media = vid ? 'watch' : 'listen';
    var note = [vid ? t('media_v', { v: secs }) : '', pod ? t('media_p', { p: mins }) : ''].filter(Boolean).join(' · ');   // 11-01 用户定：不单独标“AI 合成语音”（页脚已说明整期由 AI 工作流生成）
    return '<section class="sec" id="sec-media">' + head('media', esc(note)) +
      '<div class="media glass rv' + (both ? '' : ' one') + '" data-tab="' + UI.media + '">' +
      (both ? '<div class="mtabs seg" role="tablist" id="mtabs">' +
        '<button role="tab" type="button" data-act="mtab" data-tab="watch" aria-selected="' + (UI.media === 'watch') + '">' + esc(t('m_watch')) + '<span class="t">' + secs + 's</span></button>' +
        '<button role="tab" type="button" data-act="mtab" data-tab="listen" aria-selected="' + (UI.media === 'listen') + '">' + esc(t('m_listen')) + '<span class="t">' + mins + ' min</span></button></div>' : '') +
      '<div class="media-in">' + (vid ? '<div class="pane pane-watch"><div id="video-root">' +
        '<button class="v-ph" type="button" data-act="watch" data-scene="0">' + (im ? imgTag(im, false, '(max-width: 900px) 100vw, 680px') : '<span class="cover">' + coverSVG('video-' + ISSUE.date) + '</span>') +
        '<span class="v-ph-in"><span class="v-ph-btn">' + ICON.play + '</span><span class="v-ph-t">' + esc(t('v_ph', { s: secs })) + '</span></span></button>' +
      '</div></div>' : '') + (pod ? '<div class="pane pane-listen"><div id="pod-root"></div></div>' : '') + '</div></div></section>';
  }

  /* —— 图表面板（头条里、对照里、快讯旁） —— */
  function chartBody(cid) {
    var c = CH(cid); if (!c) return '';
    var inner;
    if (c.type === 'timeline') {
      inner = '<div class="tl" data-tl><div class="tl-line"><i></i></div><ol>' + c.items.map(function (x, k) {
        var cls = x.future ? 'future' : (x.today ? 'today' : 'past');
        return '<li class="' + cls + '" style="--k:' + k + '"><span class="dt" aria-hidden="true"></span><span class="w">' + esc(pick(x, 'when')) + '</span><span class="x">' + esc(pick(x, 'text')) + citeTag(x.cite) + '</span></li>';
      }).join('') + '</ol></div>';
    } else {
      inner = '<div class="chart" data-chart="' + esc(cid) + '" style="height:' + chartH(c) + 'px" role="img" aria-label="' + esc(pick(c, 'title')) + '"></div>';
    }
    var note = pick(c, 'note');
    var rest = (c.cites || []).filter(function (x) { return !(note && x === c.note_cite); });   // 注释已挂的出处，不在“出处”里再写一遍
    return inner + '<p class="cnote">' + (note ? esc(note) + (c.note_cite ? citeTag(c.note_cite) : '') + ' ' : '') + (rest.length ? '<span class="cn-src"><b>' + esc(t('chart_src')) + '</b>\u00a0' + cites(rest) + '</span>' : '') + '</p>';
  }
  function chartH(c) {
    var narrow = window.innerWidth < 640;
    if (c.type === 'dumbbell') return 270;
    if (c.type === 'graph') return narrow ? 300 : 330;
    if (c.type === 'steps') return 190;
    if (c.type === 'bars') return c.compact ? 140 : Math.max(200, c.items.length * 34 + 20);
    return 280;
  }
  function chartPanel(st) {
    var ids = (st.charts || []).filter(CH);
    if (!ids.length) return '';
    var k0 = UI.ctab[st.id] || 0;
    var tabs = ids.length > 1 ? '<div class="ctabs seg" role="tablist">' + ids.map(function (c, k) {
      var cc = CH(c), lbl = cc.type === 'timeline' ? t('c_timeline') : cc.type === 'graph' ? t('c_graph') : pick(cc, 'title');
      return '<button role="tab" type="button" id="ct-' + esc(st.id) + '-' + k + '" aria-controls="cb-' + esc(st.id) + '-' + k + '" aria-selected="' + (k === k0) + '" tabindex="' + (k === k0 ? 0 : -1) + '" data-act="ctab" data-story="' + esc(st.id) + '" data-k="' + k + '">' + esc(lbl) + '</button>';
    }).join('') + '</div>' : '';
    return '<div class="cpanel" id="cp-' + esc(st.id) + '"><div class="cp-h"><b class="ct">' + esc(pick(CH(ids[k0]), 'title')) + '</b>' + tabs + '</div>' +
      ids.map(function (c, k) { return '<div class="cbody" id="cb-' + esc(st.id) + '-' + k + '"' + (ids.length > 1 ? ' role="tabpanel" aria-labelledby="ct-' + esc(st.id) + '-' + k + '"' : '') + (k === k0 ? '' : ' hidden') + '>' + chartBody(c) + '</div>'; }).join('') + '</div>';
  }

  /* —— 头条、要闻：同一种“故事页”，五种配图版式（v3.2） ——
   * st.layout 由组装脚本按“日期＋条目号”挑（site/tools/v3_site.py 的 LAYOUTS），相邻两条不重复：
   *   split-l 图在左、字在右 · split-r 字在左、图在右（4:3）· glass 图铺满做底、标题导语在毛玻璃上 ·
   *   wide 宽幅图在上、下面左文右栏 · inset 带边框的小画框＋错开的图注
   * 每块内容都有固定的类名（sl-fig 图、sl-head 标题和正文、cpanel/kn 图表和数字、why、acts、srcline），
   * 窄屏（≤1080px）时外层容器一律 display: contents，按 order 排成“图 → 正文 → 图表 → 为什么重要 → 听/看 → 来源”。 */
  var LAY_SIZES = { 'split-l': '(max-width: 1080px) 100vw, 560px', 'split-r': '(max-width: 1080px) 100vw, 470px', glass: '(max-width: 1080px) 100vw, 1130px',
    wide: '(max-width: 1080px) 100vw, 1130px', inset: '(max-width: 1080px) 100vw, 430px' };
  function storyFig(st, lay) {
    var im = normImage(st.image);
    if (!im) return '<figure class="sl-fig cover" aria-hidden="true">' + coverSVG(st.id) + '</figure>';
    var fig = '<figure class="sl-fig">' + imgTag(im, false, LAY_SIZES[lay]) + '</figure>';
    if (lay !== 'inset') return fig;
    var cap = pick(im, 'cap');   // 图注只用稿件写的 caption（这张图对这条新闻意味着什么）；没有就不放图注，绝不拿替代文字当图注
    return '<div class="sl-frame"><span class="sl-mat" aria-hidden="true"></span>' + fig + (cap ? '<p class="sl-cap" aria-hidden="true"><span>' + esc(cap) + '</span></p>' : '') + '</div>';
  }
  // 页签上的字：稿件给了短标题（tab_zh / tab_en）就用它，没有就用标题（v3.2）
  function tabLabel(id) { var st = S(id); return pick(st, 'tab') || pick(st, 'title'); }
  function storySlide(st, o) {
    var more = !!UI.more[st.id], lay = st.layout || 'split-l';
    var lead = st['lead_' + lang] || st.lead_zh || [];
    var fig = storyFig(st, lay);
    var extra = (o.charts ? chartPanel(st) : '') + (o.nums ? numbersGrid(st.numbers) : '');
    var headHTML = '<div class="sl-head">' +
      '<p class="kick">' + kick(st) + spectrum(st.coverage) + '</p>' +
      '<h3 class="sl-title">' + esc(pick(st, 'title')) + '</h3>' +
      (o.summary ? '<p class="dek">' + rich(pick(st, 'summary')) + '</p>' : '') +
      (o.lead && lead.length ? '<ol class="lead" id="lead-' + esc(st.id) + '"' + (more ? ' hidden' : '') + '>' + lead.map(function (s) { return '<li>' + rich(s) + '</li>'; }).join('') + '</ol>' : '') +
      '<div class="body" id="body-' + esc(st.id) + '"' + (more ? '' : ' hidden') + '>' + paras(st['body_' + lang]) + '</div>' +
      '<button class="linkbtn" type="button" data-act="more" data-id="' + esc(st.id) + '" aria-expanded="' + more + '" aria-controls="body-' + esc(st.id) + '">' + esc(t(more ? 'read_less' : 'read_more')) + '</button></div>';
    var foot = whyBox(st) + actions(st) + srcLine(st);
    var col = function (h, cls) { return h ? '<div class="sl-col' + (cls ? ' ' + cls : '') + '">' + h + '</div>' : ''; };
    var inner;
    if (lay === 'glass') {
      var below = col(extra) + col(foot);
      inner = '<div class="sl-hero">' + fig + '<div class="sl-glass">' + headHTML + '</div></div>' +
        (below ? '<div class="sl-below' + (extra && foot ? '' : ' one') + '">' + below + '</div>' : '');
    } else if (lay === 'wide') {
      inner = fig + '<div class="sl-below' + (extra || foot ? '' : ' one') + '">' + col(headHTML) + col(extra + foot) + '</div>';
    } else if (lay === 'split-r') {
      inner = col(headHTML + foot, 'sl-a') + col(fig + extra, 'sl-b');
    } else {   // split-l、inset
      inner = col(fig + extra, 'sl-a') + col(headHTML + foot, 'sl-b');
    }
    return '<div class="story lay-' + esc(lay) + '">' + inner + '</div>';
  }
  function secHeadlines() {
    var ids = ((ISSUE.order || {}).headline || []).filter(S);
    if (!ids.length) return '';
    return '<section class="sec" id="sec-headline">' + head('headline') +
      pagerHTML('headline', t('sec_headline'), ids.map(tabLabel),
        ids.map(function (id) { return storySlide(S(id), { charts: true, lead: true }); }), 9000) + '</section>';
  }
  function secBriefs() {
    var ids = ((ISSUE.order || {}).brief || []).filter(S);
    if (!ids.length) return '';
    return '<section class="sec" id="sec-brief">' + head('brief') +
      pagerHTML('brief', t('sec_brief'), ids.map(tabLabel),
        ids.map(function (id) { return storySlide(S(id), { summary: true, nums: true }); }), 8000) + '</section>';
  }
  function secFlash() {
    var ids = ((ISSUE.order || {}).flash || []).filter(S);
    if (!ids.length) return '';
    var fc = ISSUE.flash_chart && CH(ISSUE.flash_chart);
    return '<section class="sec" id="sec-flash">' + head(edition() === 'sun' ? 'flash_week' : 'flash') + '<div class="flash-wrap rv' + (fc ? '' : ' solo') + '"><ol class="flist glass">' + ids.map(function (id, i) {
      var st = S(id), on = UI.flash === id;
      return '<li class="frow' + (on ? ' open' : '') + '" id="f-' + esc(id) + '"><button type="button" data-act="fopen" data-id="' + esc(id) + '" aria-expanded="' + on + '" aria-controls="fx-' + esc(id) + '">' +
        '<span class="i" aria-hidden="true">' + (i + 1) + '</span><span class="ft">' + esc(pick(st, 'title')) + '</span>' + ICON.chevD + '</button>' +
        '<div class="fx" id="fx-' + esc(id) + '"><p class="kick">' + kick(st) + spectrum(st.coverage) + '</p>' +
        // v3.2：快讯没有正文，展开后显示摘要（有正文时显示前两句）、数字、为什么重要和来源，限定说法和出处读者都看得到
        ((st['lead_' + lang] || []).length ? (st['lead_' + lang] || []).slice(0, 2).map(function (s) { return '<p>' + rich(s) + '</p>'; }).join('') : (pick(st, 'summary') ? '<p>' + rich(pick(st, 'summary')) + '</p>' : '')) +
        numbersGrid(st.numbers) + whyBox(st) + actions(st) + srcLine(st) + '</div></li>';
    }).join('') + '</ol>' +
      (fc ? '<div class="cpanel glass"><div class="cp-h"><b class="ct">' + esc(pick(fc, 'title')) + '</b></div>' + chartBody(ISSUE.flash_chart) + '</div>' : '') + '</div></section>';
  }

  /* —— 周末：周六"深度"、周日"本周深谈"（11-01 彩排加） ——
   * 网页稿把那一题写成 sections 里 kind 为 "deep" 的一条（id 是专题卡编号，如 D1）。正文按"层"写：每层以一整段
   * "【层名】这一层的结论" 开头（写法见 pipeline/prompts/写稿_网页_周末.md），这里拆成一层层的卡片：
   *   上面一块是这一题的标题、反差、关键数字（有配图放配图，没有就是主题色封面）；
   *   下面左边（窄屏在上面）是 1 2 3 编号的层目录，点了滚到那一层；右边一层一张卡：编号、层名、结论、正文，
   *   "听这一层"跳到播客里同名的那一章（章名是"深度·层名"或"深谈·层名"）。
   * 图表：配置里没被头条、对照、快讯用掉的图表都归这一块；图表写了 layer（中文层名）就放在那一层下面，否则放在最后。
   * 英文正文的层和中文一一对应（按顺序），层名照英文写。 */
  var LAYER_RE = /^[\s​⁠]*【([^】]{1,30})】[\s​⁠]*/;
  function zw(s) { return String(s || '').replace(/[​⁠]/g, ''); }
  function deepLayers(arr) {
    var out = [], cur = null;
    (arr || []).forEach(function (p) {
      var m = LAYER_RE.exec(p);
      if (m) { cur = { key: zw(m[1]).trim(), take: p.slice(m[0].length), paras: [] }; out.push(cur); }
      else { if (!cur) { cur = { key: '', take: '', paras: [] }; out.push(cur); } cur.paras.push(p); }
    });
    return out;
  }
  function deepCharts() {
    var used = {};
    Object.keys(ISSUE.stories || {}).forEach(function (k) { (ISSUE.stories[k].charts || []).forEach(function (c) { used[c] = 1; }); });
    (ISSUE.pairs || []).forEach(function (p) { if (p.chart_cn) used[p.chart_cn] = 1; });
    if (ISSUE.flash_chart) used[ISSUE.flash_chart] = 1;
    return Object.keys(ISSUE.charts || {}).filter(function (c) { return !used[c] && CH(c); });
  }
  function layerChapter(key) {
    var pod = ISSUE.media && ISSUE.media.podcast;
    if (!pod || !key) return null;
    var hit = (pod.chapters || []).filter(function (c) { var tz = zw(c.title_zh || c.title || ''); return tz.slice(-key.length - 1) === '·' + key; })[0];
    return hit ? hit.start : null;
  }
  function deepChartBox(cid) {
    var c = CH(cid);
    return '<div class="cpanel dl-chart"><div class="cp-h"><b class="ct">' + esc(pick(c, 'title')) + '</b></div>' + chartBody(cid) + '</div>';
  }
  // 这一题在播客里从哪一秒开始（第一层那一章；没有就用组装脚本算的“听这一段”）、到结尾大约几分钟
  function deepSpan(st) {
    var LZ = deepLayers(st.body_zh), pod = ISSUE.media && ISSUE.media.podcast, chs = (pod && pod.chapters) || [];
    var first = LZ.length ? layerChapter(LZ[0].key) : null;
    if (first == null && st.listen != null && pod) first = st.listen;
    var last = chs.filter(function (c) { return /^(结尾|Outro)/.test(zw(c.title_zh || '')); })[0];
    return { at: first, mins: first != null && last ? Math.max(1, Math.round((last.start - first) / 60)) : 0 };
  }
  /* 名词解释（11-01 晚定，代替周末的“今日一词”）：深度／深谈那一块最后一个折叠框，收这一期出现的 3–5 个术语。
   * 平时收着，标题行列出收了哪几个词；点开是“词 · 英文／中文 · 解释”，写了 layer 的注明出自第几层（点了跳过去）。截图模式下展开。 */
  function glossaryBox(st, L, LZ) {
    var G = (st.glossary || []).filter(function (g) { return g && g.zh && g.explain_zh; });
    if (!G.length) return '';
    var zh = lang === 'zh', open = STATIC || !!UI.gloss, keys = LZ.map(function (x) { return x.key; });
    var name = function (g) { return zh ? g.zh : (g.en || g.zh); };
    var items = G.map(function (g) {
      var alt = zh ? g.en : g.zh, li = g.layer ? keys.indexOf(zw(g.layer)) : -1;
      var at = li >= 0 ? '<button class="gl-at" type="button" data-act="dl" data-k="' + li + '">' + esc(t('gl_layer', { n: li + 1, l: zw((L[li] || LZ[li]).key) })) + ICON.go + '</button>' : '';
      return '<div class="gl-i"><dt><b>' + esc(name(g)) + '</b>' + (alt ? '<i' + (zh ? ' lang="en"' : ' class="cjk" lang="zh-CN"') + '>' + esc(alt) + '</i>' : '') + '</dt>' +
        '<dd><p>' + esc(zh ? g.explain_zh : (g.explain_en || g.explain_zh)) + citeTag(g.cite) + '</p>' + at + '</dd></div>';
    }).join('');
    return '<div class="glbox glass rv' + (open ? ' open' : '') + '" id="glbox">' +
      '<button class="glt" type="button" data-act="gloss" aria-expanded="' + open + '" aria-controls="glin"><b>' + esc(t('sec_glossary')) + '</b>' +
      '<span class="gl-sum">' + esc(t('gl_n', { n: G.length })) + ' · ' + esc(G.map(name).join(zh ? '、' : ', ')) + '</span>' + ICON.chevD + '</button>' +
      '<dl class="glin" id="glin">' + items + '</dl></div>';
  }
  function setGloss(on) {
    UI.gloss = on;
    var box = $('#glbox'); if (!box) return;
    box.classList.toggle('open', on);
    $('.glt', box).setAttribute('aria-expanded', on);
  }
  // 这一题的来源一行：周末专题卡的来源常有十几条，上标之间留换行点（U+200B），手机上可以在上标之间折行；"来源"和第一个上标用不换行空格粘住
  function deepSrcLine(st) {
    var ids = (st.sources || []).filter(Boolean);
    return ids.length ? '<p class="srcline dl-src">' + esc(t('sources_of')) + '\u00a0' + ids.map(citeTag).join('\u200b') + '</p>' : '';
  }
  /* 周六“深度”：上面一块（图、标题、反差、关键数字、听／看）＋层目录＋层卡＋为什么重要＋名词解释。
   * 周日“本周深谈”（11-01 晚定）：标题、核心问题、一句话结论已经在首屏的本周深谈卡上，这里不再放上面那一块，
   *   直接是层目录和五层；关键数字放进各层（每个数写 layer，每层最多 3 个，没写 layer 的放进“数字怎么读”），时间线等图表照旧按 layer 放。
   * 关键数字写了 layer 的，周六也放进那一层；没写的留在上面那一块。 */
  function secDeep() {
    var st = deepStory();
    if (!st) return '';
    var sun = edition() === 'sun', key = sun ? 'talk' : 'deep';
    var LZ = deepLayers(st.body_zh), L = deepLayers(st['body_' + lang] || st.body_zh);
    if (L.length !== LZ.length) L = LZ;                     // 英文层数对不上时用中文的层，免得"听这一层"错位
    var charts = deepCharts(), placed = {};
    var sp = deepSpan(st);
    var note = esc(t('dl_n', { n: LZ.length })) + (sp.mins ? ' · ' + esc(t('dl_pod', { m: sp.mins })) : '');
    // 关键数字分到各层：-1 = 不进层（留在上面那一块）
    var keys = LZ.map(function (x) { return x.key; }), nums = st.numbers || [], lnMax = WK('layer_numbers_max', 3);
    var fallback = keys.indexOf('数字怎么读') >= 0 ? keys.indexOf('数字怎么读') : 0;
    var target = nums.map(function (n) {
      var i = n.layer ? keys.indexOf(zw(n.layer)) : -1;
      return i < 0 && sun && keys.length ? fallback : i;
    });
    var heroNums = nums.filter(function (n, j) { return target[j] < 0; });
    var gl = glossaryBox(st, L, LZ);
    var nav = '<nav class="dl-nav glass" aria-label="' + esc(t('dl_nav')) + '"><ol>' + L.map(function (x, i) {
      return '<li><button type="button" data-act="dl" data-k="' + i + '"><span class="n" aria-hidden="true">' + (i + 1) + '</span>' +
        '<span class="k">' + esc(zw(x.key) || '—') + '</span></button></li>';
    }).join('') + (gl ? '<li class="gl-nav"><button type="button" data-act="glgo" aria-controls="glin"><span class="n" aria-hidden="true">' + ICON.plus + '</span><span class="k">' + esc(t('sec_glossary')) + '</span></button></li>' : '') +
      '</ol></nav>';
    var layers = L.map(function (x, i) {
      var zkey = (LZ[i] || {}).key, at = layerChapter(zkey);
      var cs = charts.filter(function (c) { return !placed[c] && zw(CH(c).layer) === zkey; });
      cs.forEach(function (c) { placed[c] = 1; });
      var ln = nums.filter(function (n, j) { return target[j] === i; }).slice(0, lnMax);
      var listenBtn = at != null ? '<div class="acts"><button class="btn sm" type="button" data-act="listen" data-t="' + at + '">' + ICON.headph +
        esc(t('dl_listen')) + '<span class="t">' + fmtTime(at) + '</span></button></div>' : '';
      return '<article class="dl glass rv" id="dl-' + i + '" style="--d:' + (i * 60) + 'ms"><p class="dl-k"><span class="n" aria-hidden="true">' + (i + 1) + '</span>' + esc(zw(x.key)) + '</p>' +
        (x.take ? '<h4 class="dl-take">' + rich(x.take.replace(/\[\^s\d+\]/g, '')) + '</h4>' : '') + '<div class="body">' + paras(x.paras) + '</div>' +   // 层结论是小标题，不挂上标（出处在正文里）
        numbersGrid(ln) + cs.map(deepChartBox).join('') + listenBtn + '</article>';
    }).join('');
    var rest = charts.filter(function (c) { return !placed[c]; }).map(deepChartBox).join('');
    var hero = sun ? '' : '<div class="dl-hero glass rv">' + figure(st.image, 'dl-fig', false, '(max-width: 900px) 100vw, 560px', 'deep-' + st.id) +
      '<div class="dl-hd"><p class="kick">' + kick(st) + spectrum(st.coverage) + '</p><h3 class="sl-title">' + esc(pick(st, 'title')) + '</h3>' +
      (pick(st, 'summary') ? '<p class="dek">' + rich(pick(st, 'summary')) + '</p>' : '') + numbersGrid(heroNums) +
      actions(st) + '</div></div>';   // "听这一段"由组装脚本定在第一层那一章开头（build_v3.py 的 listen_at）
    return '<section class="sec" id="sec-deep">' + head(key, note) + hero +
      '<div class="dl-main' + (sun ? ' no-hero' : '') + '">' + nav + '<div class="dl-list">' + layers + rest +
      '<div class="dl-foot">' + whyBox(st) + deepSrcLine(st) + '</div>' + gl + '</div></div></section>';
  }

  /* —— 预告看板：一条时间轴（v3.2） ——
   * 节点按配置顺序（＝发生先后）排在一条轴上，当前节点的详情显示在轴下面同一块里；电脑上横排，手机上竖排。
   * 线段一段段画出来、节点依次出现；当前节点外面一圈细环走完就换下一个（复用 Pager：悬停约 0.15 秒换、点了就停、方向键、滑动、滚出视野暂停）。
   * 状态只用很淡的方式区分：传闻＝虚线圈（连向它的那段线也是虚线），已排期＝实心点，当事方预告＝实线圈，报道称＝灰色实线圈。 */
  function watchPanel(w, k) {
    var st = S(w.story), det = st && st.kind === 'teaser', open = !!UI.wdet[k];
    var btns = (det ? '<button class="btn sm" type="button" data-act="wdet" data-k="' + k + '" aria-expanded="' + open + '" aria-controls="wd-' + k + '">' + esc(t(open ? 'w_less' : 'w_more')) + '</button>' : '') +
      (st && !det ? '<button class="btn sm" type="button" data-act="go" data-id="' + esc(w.story) + '">' + esc(t('go_story')) + ' · ' + esc(kindLabel(st.kind)) + ICON.go + '</button>' : '');
    return '<p class="wp-meta"><span class="st ' + esc(w.status) + '">' + esc(t('w_' + w.status)) + '</span><span class="wp-when">' + esc(pick(w, 'when')) + '</span></p>' +
      '<p class="w-text">' + esc(pick(w, 'text')) + cites(w.cite) + '</p>' +
      (btns ? '<div class="acts">' + btns + '</div>' : '') +
      (det ? '<div class="w-det" id="wd-' + k + '"' + (open ? '' : ' hidden') + '>' + paras(st['body_' + lang]) + whyBox(st) + actions(st) + '</div>' : '');
  }
  function secWatch() {
    var W = (ISSUE.watch || []).slice(0, 5);   // 最多 5 条
    if (!W.length) return '';
    var hk = edition() === 'sun' ? 'next' : 'watch';   // 周日叫"接下来看什么"（11-01 晚定）
    var N = W.length, multi = N > 1, cur = multi ? Math.min(UI.pg.watch || 0, N - 1) : 0, label = t('sec_' + hk);
    var nodes = W.map(function (w, k) {
      var on = k === cur, cls = 'wn st-' + esc(w.status) + (on ? ' on' : '') + (k < cur ? ' done' : '') + (k < N - 1 && W[k + 1].status === 'rumor' ? ' to-rumor' : '');
      var inner = (k < N - 1 ? '<i class="wn-seg" aria-hidden="true"></i>' : '') +
        '<span class="wn-dot" aria-hidden="true">' + (multi ? '<svg class="wn-ring" viewBox="0 0 36 36"><circle cx="18" cy="18" r="16"/></svg>' : '') + '</span>' +
        '<span class="wn-when">' + esc(pick(w, 'when')) + '</span><span class="wn-st">' + esc(t('w_' + w.status)) + '</span>';
      return multi ? '<button class="' + cls + '" type="button" role="tab" id="wn-' + k + '" aria-controls="wp-' + k + '" aria-selected="' + on + '" tabindex="' + (on ? 0 : -1) + '" style="--k:' + k + '">' + inner + '</button>'
        : '<div class="' + cls + '" style="--k:0">' + inner + '</div>';
    }).join('');
    var panels = W.map(function (w, k) {
      var on = k === cur;
      return '<div class="wp' + (on ? ' on' : '') + '"' + (multi ? ' role="tabpanel" id="wp-' + k + '" aria-labelledby="wn-' + k + '"' : '') + (on ? '' : ' aria-hidden="true" inert') + '>' + watchPanel(w, k) + '</div>';
    }).join('');
    return '<section class="sec" id="sec-watch">' + head(hk) +
      '<div class="wtl glass rv' + (multi ? '' : ' single') + '"' + (multi ? ' data-pager="watch" role="region" aria-roledescription="' + esc(t('timeline')) + '" aria-label="' + esc(label) + '"' : '') +
        ' style="--n:' + N + ';--cur:' + cur + ';--pg-dur:6500ms">' +
        '<div class="wtl-top"><div class="wtl-axis"' + (multi ? ' role="tablist" aria-label="' + esc(label) + '"' : '') + '>' + nodes + '</div>' +
        (multi ? '<button class="icon-btn sm wtl-play" type="button" aria-label="' + esc(t('pg_pause')) + '">' + ICON.pause + ICON.play + '</button>' : '') + '</div>' +
        '<div class="wtl-panels">' + panels + '</div></div></section>';
  }

  /* —— 国内外对照：中间画两边的关系（v3.2） ——
   * 关系从固定词表里选（site/tools/v3_site.py 的 RELATIONS），每种一个小动画，颜色都是当天主题色：
   *   echo 呼应＝两边同步发出的脉冲 · race 良性竞争＝两条并行跑道上你追我赶 · clash 对抗＝两块楔形相向顶住 ·
   *   link 合作＝两个环扣到一起 · tug 拉锯＝绳上的标记左右来回 · fit 互补＝两块拼图合上 ·
   *   follow 跟进＝一个先走、一个随后 · split 分化＝一条线分成两条岔路
   * 横排时左边是国外、右边是国内；手机上上下排，图形转 90 度（上国外、下国内）。 */
  var REL_SVG = {
    echo: '<line class="rail" x1="20" y1="26" x2="112" y2="26" stroke-dasharray="1.5 6"/>' +
      '<circle class="pl" cx="20" cy="26" r="17"/><circle class="pl d2" cx="20" cy="26" r="17"/><circle class="pl" cx="112" cy="26" r="17"/><circle class="pl d2" cx="112" cy="26" r="17"/>' +
      '<circle class="af" cx="20" cy="26" r="4.5"/><circle class="af" cx="112" cy="26" r="4.5"/>',
    race: '<line class="rail" x1="8" y1="17" x2="124" y2="17"/><line class="rail" x1="8" y1="35" x2="124" y2="35"/><line class="fin" x1="124" y1="9" x2="124" y2="43"/>' +
      '<g class="rn r1"><line class="tr" x1="-22" y1="17" x2="0" y2="17"/><circle class="af" cx="0" cy="17" r="4.5"/></g>' +
      '<g class="rn r2"><line class="tr" x1="-22" y1="35" x2="0" y2="35"/><circle class="af soft" cx="0" cy="35" r="4.5"/></g>',
    clash: '<line class="rail" x1="66" y1="8" x2="66" y2="44" stroke-dasharray="2 4"/>' +
      '<path class="wg wl" d="M26 12 L58 26 L26 40 Z"/><path class="wg wr" d="M106 12 L74 26 L106 40 Z"/>' +
      '<line class="spark" x1="66" y1="15" x2="66" y2="37"/>',
    link: '<path class="lens" d="M66 17 A15 15 0 0 1 66 35 A15 15 0 0 1 66 17 Z"/><circle class="lk l1" cx="54" cy="26" r="15"/><circle class="lk l2" cx="78" cy="26" r="15"/>',
    tug: '<line class="rope" x1="10" y1="26" x2="122" y2="26"/><line class="rail" x1="66" y1="13" x2="66" y2="39" stroke-dasharray="2 4"/>' +
      '<circle class="af" cx="10" cy="26" r="4"/><circle class="af" cx="122" cy="26" r="4"/><path class="knot" d="M66 18 L72 26 L66 34 L60 26 Z"/>',
    fit: '<path class="pz pa" d="M24 12 H64 V21 A5 5 0 0 1 64 31 V40 H24 Z"/><path class="pz pb" d="M64 12 H108 V40 H64 V31 A5 5 0 0 0 64 21 Z"/>',
    follow: '<line class="rail" x1="8" y1="26" x2="124" y2="26"/><g class="fo f2"><circle class="ring" cx="0" cy="26" r="5"/></g><g class="fo f1"><circle class="af" cx="0" cy="26" r="5.5"/></g>',
    split: '<path class="rail" d="M8 26 H54 C70 26 80 11 124 9"/><path class="rail" d="M8 26 H54 C70 26 80 41 124 43"/>' +
      '<path class="br" pathLength="100" d="M8 26 H54 C70 26 80 11 124 9"/><path class="br" pathLength="100" d="M8 26 H54 C70 26 80 41 124 43"/>' +
      '<circle class="af tip t1" cx="124" cy="9" r="4"/><circle class="af tip t2" cx="124" cy="43" r="4"/><circle class="af" cx="54" cy="26" r="3.5"/>'
  };
  function relGlyph(r) {
    r = r || { k: 'echo', label_zh: '呼应', label_en: 'Echo' };
    var k = REL_SVG[r.k] ? r.k : 'echo', name = lang === 'en' ? (r.label_en || r.label_zh) : (r.label_zh || r.label_en);
    return '<div class="rg-box" role="img" aria-label="' + esc(t('rel_aria', { r: name })) + '"><svg class="rg rg-' + k + (r.lead === 'cn' ? ' flip' : '') + '" viewBox="0 0 132 52" aria-hidden="true" focusable="false">' + REL_SVG[k] + '</svg></div>' +
      '<p class="rel-name" aria-hidden="true">' + esc(name) + '</p>';
  }
  function pairOK(p) { return !!(p && S(p.intl) && S(p.cn)); }
  function pairSlide(p) {
    var a = S(p.intl), b = S(p.cn);
    if (!a || !b) return '';
    var side = function (st, r) {
      var chart = r === 'cn' && p.chart_cn && CH(p.chart_cn) ? '<div class="cpanel"><div class="cp-h"><b class="ct">' + esc(pick(CH(p.chart_cn), 'title')) + '</b></div>' + chartBody(p.chart_cn) + '</div>' : '';
      // 对照的一边如果本身是头条、要闻或快讯，就给“去看头条/要闻/快讯”（快讯没有正文可展开）；只在对照里出现的条目才原地“读全文”
      var goKey = { headline: 'to_headline', brief: 'to_brief', flash: 'to_flash' }[st.kind], isBrief = !!goKey, open = !!UI.pexp[st.id];
      var lead = p[r + '_' + lang] || p[r + '_zh'] || pick(st, 'summary') || (st['lead_' + lang] || [])[0];   // 对照专用的一句 > 摘要
      var btn = isBrief ? '<button class="btn sm" type="button" data-act="go" data-id="' + esc(st.id) + '">' + esc(t(goKey)) + ICON.go + '</button>'
        : '<button class="btn sm" type="button" data-act="pexp" data-id="' + esc(st.id) + '" aria-expanded="' + open + '" aria-controls="x-' + esc(st.id) + '">' + esc(t(open ? 'read_less' : 'read_more')) + '</button>';
      return '<div class="side ' + r + '"><p class="rg-side">' + esc(t(r === 'cn' ? 'pair_cn' : 'pair_intl')) + '</p><h3>' + esc(pick(st, 'title')) + '</h3>' +
        '<p class="sm">' + rich(lead) + '</p>' + numbersGrid((st.numbers || []).slice(0, 2)) + chart +
        (isBrief ? '' : '<div class="xbody" id="x-' + esc(st.id) + '"' + (open ? '' : ' hidden') + '>' + paras(st['body_' + lang]) + whyBox(st) + actions(st) + '</div>') +
        '<div class="acts">' + btn + '</div></div>';
    };
    var note = pick(p, 'note');
    return '<div class="pair">' + side(a, 'intl') +
      '<div class="mid"><div class="rel">' + relGlyph(p.relation) + (note ? '<p class="rel-tx">' + rich(note) + '</p>' : '') + '</div></div>' + side(b, 'cn') + '</div>';
  }
  function secPairs() {
    var P = (ISSUE.pairs || []).filter(pairOK);
    if (!P.length) return '';
    return '<section class="sec" id="sec-pairs">' + head('pairs') +
      pagerHTML('pairs', t('sec_pairs'), P.map(function (p) { return pick(p, 'label') || pick(S(p.cn), 'title'); }), P.map(pairSlide), 9000) + '</section>';
  }
  function secTerm() {
    if (edition()) return '';   // 周末没有今日一词：改成深度／深谈里折叠的"名词解释"（11-01 晚定）
    var st = S('term'), c = ISSUE.card && ISSUE.card.term;
    if (!st || !c || !(c.zh || c.en)) return '';
    var zh = lang === 'zh', like = zh ? c.like_zh : c.like_en;
    var front = '<div class="face front">' + figure(st.image, 'term-fig', false, '(max-width: 640px) 100vw, 300px', 'term-' + ISSUE.date) +
      '<div class="front-tx"><p class="kick">' + esc(t('term_k')) + '</p>' +
      '<p class="term-w' + (zh ? '' : ' lat') + '">' + esc(zh ? c.zh : c.en) + '</p><p class="term-alt' + (zh ? '' : ' cjk') + '"' + (zh ? ' lang="en"' : '') + '>' + esc(zh ? c.en : c.zh) + '</p>' +
      (like ? '<p class="term-like">' + esc(like) + '</p>' : '') +
      '<button class="btn" type="button" data-act="flip" aria-pressed="false">' + ICON.flip + esc(t('flip')) + '</button></div></div>';
    var back = '<div class="face back"><p class="kick">' + esc(zh ? c.zh : c.en) + ' · <span' + (zh ? ' lang="en"' : '') + '>' + esc(zh ? c.en : c.zh) + '</span></p>' +
      '<div class="back-cols"><div><h3 class="bh">' + esc(t('term_explain')) + '</h3><p class="body-s">' + esc(zh ? c.explain_zh : c.explain_en) + '</p>' +
      (st['why_' + lang] && st['why_' + lang].length ? '<h3 class="bh">' + esc(t('term_note')) + '</h3><div class="body-s">' + paras(st['why_' + lang]) + '</div>' : '') + '</div>' +
      '<div><h3 class="bh">' + esc(t('term_usage')) + '</h3><div class="body-s">' + paras(st['body_' + lang]) + '</div></div></div>' +
      actions(st, '<button class="btn sm" type="button" data-act="flip" aria-pressed="true">' + ICON.flip + esc(t('flip_back')) + '</button>') + '</div>';
    var body;
    if (STATIC) {   // 截图模式：正反两面摆在一起
      body = '<div class="term-both"><div><p class="face-tag">' + esc(t('term_front')) + '</p><div class="term-card glass rv"><div class="term-in">' + front + '</div></div></div>' +
        '<div><p class="face-tag">' + esc(t('term_back')) + '</p><div class="term-card glass rv flipped"><div class="term-in">' + back + '</div></div></div></div>';
    } else {
      body = '<div class="term-card glass rv' + (UI.flip ? ' flipped' : '') + '" id="termCard"><div class="term-in">' + front + back + '</div></div>';
    }
    return '<section class="sec" id="sec-term">' + head('term') + body + '</section>';
  }
  function secSources() {
    // 配乐署名（CC BY 4.0 要求署名，放在折叠的参考来源末尾，平时看不见；文字在 v3_site.py 的 MUSIC_CREDIT）
    // v3.2：署名都在这里——配乐、配图由 AI 生成、视频带来的署名（组装时去过重，见 build_v3.py 的 credits）
    var cr = (ISSUE && ISSUE.credits) || [];
    if (!cr.length && SITE && SITE.music_credit) cr = [{ zh: SITE.music_credit[0], en: SITE.music_credit[1] }];
    var credit = cr.map(function (c) { return esc(lang === 'en' ? (c.en || c.zh) : (c.zh || c.en)); }).join('<br>');
    return '<section class="sec" id="sec-sources"><div class="srcbox glass rv' + (UI.srcOpen ? ' open' : '') + '" id="srcbox">' +
      '<button class="srct" type="button" data-act="srctoggle" aria-expanded="' + UI.srcOpen + '" aria-controls="srcin"><b>' + esc(t('sec_sources')) + '</b><span id="srcsum"></span>' + ICON.chevD + '</button>' +
      '<div class="srcin" id="srcin"><ol class="refs" id="srcl"></ol><button class="btn sm srcall" type="button" data-act="srcall" id="srcall"></button>' +
      (credit ? '<p class="src-credit">' + credit + '</p>' : '') + '</div></div></section>';
  }

  /* ===================== 引用：按正文首次出现编号，统计引用次数 ===================== */
  function numberCites() {
    var order = {}, count = {}, n = 0;
    $$('#c-main sup.cite[data-s]').forEach(function (el) {
      var s = el.getAttribute('data-s');
      if (!order[s]) order[s] = ++n;
      count[s] = (count[s] || 0) + 1;
      var a = el.firstChild;
      a.textContent = '[' + order[s] + ']';
      a.setAttribute('aria-label', t('cite_label', { n: order[s] }));
    });
    ISSUE.sources.forEach(function (s) { if (!order[s.id]) order[s.id] = ++n; });
    var list = ISSUE.sources.slice().sort(function (a, b) { return order[a.id] - order[b.id]; });
    CITE = { order: order, count: count, list: list };
  }
  /* 上标和前面那个词粘成一块（11-14 加）：CSS 的 U+2060 只管正常换行；一块（如手机上“CloudRobo-WM1.2[19]”）比一整行还宽时，
   * overflow-wrap: anywhere 会随处断开，偏偏断在上标前面，上标单独掉到下一行（11-13 测试期第 16 步）。
   * 这里把上标前面最后一段连同紧跟的几个上标包进不换行的 <fd-nobr>：西文、数字连成的一串（最多 12 个字，到空格、连字符、U+2060、中文为止），
   * 前面是中文、标点时不包（11-14 回归：单包最后一个字会让这个字的抗锯齿差一两个像素，而中文词组有 keep-all 管着）。这一段里本来就没有换行点，放得下时排版和原来一样；放不下时只会在这一段前面断开
   * （“CloudRobo-”留上一行，“WM1.2[19]”一起到下一行）。用自定义标签不用 span，免得 .kn-i span 之类的样式套上来。
   * 周末来源行（.dl-src）的上标之间本来就允许折行，前面也没有正文，不处理。 */
  function glueCites() {
    $$('#c-main sup.cite').forEach(function (s) {
      var prev = s.previousSibling;
      if (!prev || prev.nodeType !== 3 || s.parentNode.nodeName === 'FD-NOBR' || s.closest('.dl-src')) return;
      var m = /[A-Za-z0-9\u00c0-\u024f.,%_'\u2019+#&]{1,12}$/.exec(prev.data);
      if (!m) return;
      var tail = prev.splitText(m.index);
      var g = document.createElement('fd-nobr');
      s.parentNode.insertBefore(g, tail);
      g.appendChild(tail);
      var n = s, nx;
      while (n && n.nodeType === 1 && n.matches('sup.cite')) { nx = n.nextSibling; g.appendChild(n); n = nx; }
    });
  }
  function topIds() {
    return CITE.list.slice().sort(function (a, b) { return (CITE.count[b.id] || 0) - (CITE.count[a.id] || 0) || CITE.order[a.id] - CITE.order[b.id]; })
      .slice(0, 5).map(function (s) { return s.id; });
  }
  function renderSources() {
    var ul = $('#srcl'); if (!ul) return;
    var all = CITE.list, show = UI.srcAll ? all : topIds().map(srcById);
    if (!UI.srcAll) show.sort(function (a, b) { return CITE.order[a.id] - CITE.order[b.id]; });
    ul.innerHTML = show.map(function (s) {
      return '<li class="ref" id="src-' + esc(s.id) + '" tabindex="-1"><span class="ref-n">[' + CITE.order[s.id] + ']</span><div class="ref-b">' +
        '<span class="ref-name">' + esc(lang === 'en' && s.name_en ? s.name_en : s.name) + '</span>' +
        '<a class="ref-t" href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer">' + esc((lang === 'en' && s.title_en) || s.title || host(s.url) || s.url) + '</a>' +
        '<span class="ref-d">' + esc(s.date) + '</span></div></li>';
    }).join('');
    $('#srcsum').textContent = t(UI.srcAll ? 'src_sum_all' : 'src_sum', { n: all.length });
    var b = $('#srcall');
    b.textContent = UI.srcAll ? t('src_top') : t('src_all', { n: all.length });
    b.hidden = all.length <= 5;
  }
  function jumpSource(sid) {
    hideTip();
    if (!UI.srcOpen) setSrcOpen(true);
    if (!UI.srcAll && topIds().indexOf(sid) < 0) { UI.srcAll = true; renderSources(); }
    var li = document.getElementById('src-' + sid);
    if (!li) return;
    li.scrollIntoView({ behavior: animOK() ? 'smooth' : 'auto', block: 'center' });
    li.classList.remove('flash'); void li.offsetWidth; li.classList.add('flash');
    try { li.focus({ preventScroll: true }); } catch (e) { /* 老浏览器 */ }
  }
  function setSrcOpen(on) {
    UI.srcOpen = on;
    var box = $('#srcbox'); if (!box) return;
    box.classList.toggle('open', on);
    $('.srct', box).setAttribute('aria-expanded', on);
  }

  /* ===================== 图表（ECharts，滚到附近才加载）：颜色读当前主题的 CSS 变量，切换深浅色时重画 ===================== */
  var ecWait = [];
  function withEC(cb) {
    if (window.echarts) { cb(window.echarts); return; }
    ecWait.push(cb);
    if (ecWait.length > 1) return;
    var s = document.createElement('script');
    s.src = 'vendor/echarts.min.js';
    s.onload = function () { var l = ecWait; ecWait = []; l.forEach(function (f) { f(window.echarts); }); };
    s.onerror = function () { ecWait = []; $$('.chart').forEach(function (el) { if (!el._ec) el.innerHTML = '<p class="chart-err">' + esc(t('chart_err')) + '</p>'; }); };
    document.head.appendChild(s);
  }
  function pal() {
    var cs = getComputedStyle(root), v = function (k) { return cs.getPropertyValue(k).trim(); };
    return { ink: v('--ink'), ink2: v('--ink-2'), ink3: v('--ink-3'), line: v('--chart-line'), grid: v('--chart-grid'),
      acc: v('--accent-hi'), accSoft: v('--chart-acc-soft'), accLine: v('--chart-acc-line'), muted: v('--chart-muted'), bg: v('--chart-bg'), tip: v('--tip-solid'), hair: v('--hair-2') };
  }
  // 图表文字：数字用 Times New Roman（FD Num，只管数字和几个数字符号），其余用系统黑体
  var SANS = '"FD Num", -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif';
  function srcNote(id) {
    var s = id && srcById(id);
    return s ? esc(t('chart_src')) + ' [' + (CITE.order[id] || '?') + '] ' + esc(s.name) : '';
  }
  function base(o, P) {
    o.animation = animOK();
    o.backgroundColor = 'transparent';
    o.textStyle = { fontFamily: SANS, color: P.ink };
    o.tooltip = Object.assign({ backgroundColor: P.tip, borderColor: P.hair, borderWidth: 1, padding: [8, 11], textStyle: { color: P.ink, fontSize: 12.5, fontFamily: SANS },
      extraCssText: 'border-radius:12px;box-shadow:0 12px 30px rgba(0,0,0,.16);max-width:280px;white-space:normal;backdrop-filter:blur(16px);' }, o.tooltip || {});
    return o;
  }
  function unitFmt(v, unit, en, full) {
    var n = fmtNum(v);
    if (en) return unit === '$B' ? '$' + n + 'bn' : unit === '$T' ? '$' + n + 'tn' : n + unit;   // v3.2：英文数字统一 bn / tn
    return full ? n + ' ' + unit : n;
  }
  function optDumbbell(c, el, P) {
    var en = lang === 'en', H = 92, top = 24, gap = 24, narrow = el.offsetWidth < 420;
    var grid = [], xAxis = [], yAxis = [], series = [];
    c.rows.forEach(function (r, i) {
      var unit = en ? r.unit_en : r.unit_zh, k = r.points[0].v ? r.points[0].v_en / r.points[0].v : 1;
      var cat = pick(r, 'label'), V = function (p) { return en ? p.v_en : p.v; };
      var from = r.points.filter(function (p) { return p.role === 'from'; })[0], to = r.points.filter(function (p) { return p.role === 'to'; })[0];
      grid.push({ left: narrow ? 58 : 72, right: 26, top: top + i * (H + gap), height: H });
      var mx = +(r.max * (en ? k : 1)).toFixed(4), raw = mx / 3.2, mag = Math.pow(10, Math.floor(Math.log10(raw))), nr = raw / mag;
      xAxis.push({ gridIndex: i, type: 'value', min: 0, max: mx, interval: (nr < 1.5 ? 1 : nr < 3.5 ? 2.5 : nr < 7.5 ? 5 : 10) * mag,
        axisLabel: { color: P.ink3, fontSize: 11, showMaxLabel: false, formatter: function (v) { return unitFmt(v, unit, en, false); } },
        splitLine: { lineStyle: { color: P.grid } }, axisLine: { show: false }, axisTick: { show: false } });
      yAxis.push({ gridIndex: i, type: 'category', data: [cat], axisLabel: { color: P.ink, fontSize: 13, fontWeight: 600 }, axisLine: { lineStyle: { color: P.line } }, axisTick: { show: false } });
      series.push({ type: 'line', xAxisIndex: i, yAxisIndex: i, silent: true, symbol: 'none', z: 1, data: [[V(from), cat], [V(to), cat]],
        lineStyle: { width: 6, cap: 'round', color: P.accLine },   // 纯色：SVG 里水平线配渐变会整条消失
        animationDuration: 1100, animationEasing: 'cubicOut' });
      series.push({ type: 'scatter', xAxisIndex: i, yAxisIndex: i, z: 3, animationDelay: function (idx) { return 450 + idx * 220; },
        data: r.points.map(function (p) {
          var mark = p.role === 'mark', col = mark ? P.ink3 : (p.role === 'from' ? P.muted : P.acc);
          return { value: [V(p), cat], name: pick(p, 'label'), cite: p.cite, unit: unit, symbolSize: mark ? 12 : 17,
            itemStyle: { color: mark ? P.bg : col, borderColor: mark ? P.ink3 : P.bg, borderWidth: mark ? 1.5 : 2.5, borderType: mark ? 'dashed' : 'solid' },
            label: { show: true, position: p.role === 'to' ? 'bottom' : 'top', distance: 7, color: mark ? P.ink3 : P.ink2, fontSize: 11.5, lineHeight: 15, align: 'center',
              formatter: pick(p, 'label') + '\n{v|' + unitFmt(V(p), unit, en, true) + '}', rich: { v: { fontWeight: 700, fontSize: 12.5, color: p.role === 'to' ? P.acc : P.ink } } } };
        }) });
    });
    return base({ grid: grid, xAxis: xAxis, yAxis: yAxis, series: series,
      tooltip: { trigger: 'item', formatter: function (p) { var d = p.data || {}; return '<b>' + esc(d.name) + '</b> ' + esc(unitFmt(d.value[0], d.unit, lang === 'en', true)) + '<br><span style="opacity:.75">' + srcNote(d.cite) + '</span>'; } } }, P);
  }
  // v3.2：横条图可以中英两种口径（unit_zh / pre_en + unit_en / 每条的 v_en），比如“420 亿美元”在英文页显示“$42B”；只写 unit 的老图表照旧
  function optBars(c, el, P) {
    var en = lang === 'en' && c.unit_en != null;
    var V = function (x) { return en && x.v_en != null ? x.v_en : x.v; };
    var F = function (v) { var u = en ? c.unit_en : (c.unit_zh != null ? c.unit_zh : (c.unit || '')); return (c.sign || '') + (en ? (c.pre_en || '') : '') + fmtNum(v) + (hasCJK(u) ? ' ' : '') + u; };
    var items = c.items.slice().reverse(), max = Math.max.apply(null, c.items.map(V));
    return base({
      grid: { left: 6, right: 64, top: 4, bottom: 4, containLabel: true },
      xAxis: { type: 'value', max: max * 1.12, show: false },
      yAxis: { type: 'category', data: items.map(function (x) { return pick(x, 'label'); }), axisLabel: { color: P.ink2, fontSize: 12.5 }, axisTick: { show: false }, axisLine: { lineStyle: { color: P.line } } },
      series: [{ type: 'bar', barWidth: '58%', cursor: 'pointer',
        data: items.map(function (x) { return { value: V(x), story: x.story, item: x, itemStyle: { color: x.hl ? P.acc : P.muted, borderRadius: [0, 6, 6, 0] } }; }),
        label: { show: true, position: 'right', fontSize: 12, fontWeight: 600, color: P.ink, formatter: function (p) { return F(p.value); } },
        animationDuration: 1000, animationDelay: function (i) { return (items.length - i) * 70; } }],
      tooltip: { trigger: 'item', formatter: function (p) {
        var x = p.data.item, ex = pick(x, 'extra');
        return '<b>' + esc(pick(x, 'label')) + '</b> ' + esc(F(V(x))) + (ex ? '<br>' + esc(ex) + (x.extra_cite ? ' [' + (CITE.order[x.extra_cite] || '?') + ']' : '') : '') + '<br><span style="opacity:.75">' + srcNote(x.cite) + '</span>';
      } }
    }, P);
  }
  function optSteps(c, el, P) {
    var en = lang === 'en', money = function (v) { return en ? '$' + v : v + ' ' + c.unit_zh; };
    var s = { type: 'line', step: 'middle', data: c.items.map(function (x) { return x.v; }), symbol: 'circle', symbolSize: 9,
      lineStyle: { color: P.acc, width: 2.5 }, itemStyle: { color: P.acc, borderColor: P.bg, borderWidth: 2 },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: P.accSoft }, { offset: 1, color: 'rgba(0,0,0,0)' }] } },
      label: { show: true, position: 'top', color: P.ink, fontWeight: 600, fontSize: 11.5, formatter: function (p) { return money(p.value); } },
      animationDuration: 1300 };
    if (c.base) s.markLine = { silent: true, symbol: 'none', data: [{ yAxis: c.base.v, label: { formatter: pick(c.base, 'label'), position: 'insideStartTop', color: P.ink2, fontSize: 11 }, lineStyle: { color: P.ink3, type: 'dashed', width: 1.4 } }] };
    return base({
      grid: { left: 6, right: 14, top: 28, bottom: 4, containLabel: true },
      xAxis: { type: 'category', data: c.items.map(function (x) { return pick(x, 'label'); }), axisLabel: { color: P.ink2, fontSize: 11.5 }, axisTick: { show: false }, axisLine: { lineStyle: { color: P.line } } },
      yAxis: { type: 'value', min: 0, max: 120, interval: 40, axisLabel: { color: P.ink3, fontSize: 11, formatter: function (v) { return en ? '$' + v : v; } }, splitLine: { lineStyle: { color: P.grid } } },
      series: [s],
      tooltip: { trigger: 'axis', formatter: function (ps) { var p = ps[0]; return '<b>' + esc(p.name) + '</b> ' + money(p.value) + '<br><span style="opacity:.75">' + srcNote(c.items[p.dataIndex].cite) + '</span>'; } }
    }, P);
  }
  function optGraph(c, el, P) {
    var narrow = el.offsetWidth < 520;
    var col = { core: P.acc, apple: P.ink2, ali: P.ink2, feat: P.muted, ghost: P.bg };
    return base({
      tooltip: { trigger: 'item', formatter: function (p) {
        if (p.dataType === 'edge') return esc(p.data.lbl) + '<br><span style="opacity:.75">' + srcNote(p.data.cite) + '</span>';
        return '<b>' + esc(p.data.lbl) + '</b>';
      } },
      series: [{ type: 'graph', layout: 'none', roam: false, left: narrow ? 50 : 76, right: narrow ? 50 : 76, top: 30, bottom: 34,
        edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 6,
        data: c.nodes.map(function (n) {
          var lb = n[lang] || n.zh, ghost = n.kind === 'ghost', core = n.kind === 'core';
          return { name: n.id, x: n.x, y: n.y, lbl: lb, symbolSize: core ? (narrow ? 34 : 44) : (narrow ? 14 : 18),
            itemStyle: { color: col[n.kind], borderColor: ghost ? P.ink3 : P.bg, borderWidth: ghost ? 1.5 : 2, borderType: ghost ? 'dashed' : 'solid', shadowBlur: core ? 18 : 0, shadowColor: P.accSoft },
            label: { show: true, formatter: lb, position: n.y < 30 ? 'top' : 'bottom', color: ghost ? P.ink3 : P.ink, fontSize: narrow ? 10.5 : 12, fontWeight: core ? 700 : 500 } };
        }),
        links: c.links.map(function (l) {
          return { source: l.s, target: l.t, lbl: l[lang] || l.zh, cite: l.cite,
            lineStyle: { type: l.dashed ? 'dashed' : 'solid', color: l.dashed ? P.ink3 : P.acc, opacity: l.dashed ? 0.7 : 0.6, width: 1.4, curveness: 0.1 } };
        }),
        edgeLabel: { show: !narrow, formatter: function (p) { return p.data.lbl; }, fontSize: 10.5, color: P.ink2 },
        emphasis: { focus: 'adjacency', lineStyle: { width: 2.6, opacity: 1 }, edgeLabel: { show: true } },
        animationDuration: 1200, animationEasing: 'cubicOut' }]
    }, P);
  }
  function buildOption(c, el) {
    var P = pal();
    if (c.type === 'dumbbell') return optDumbbell(c, el, P);
    if (c.type === 'bars') return optBars(c, el, P);
    if (c.type === 'steps') return optSteps(c, el, P);
    if (c.type === 'graph') return optGraph(c, el, P);
    return null;
  }
  function initChart(el) {
    if (el._ec || !el.offsetWidth) return;
    withEC(function (echarts) {
      if (el._ec || !el.offsetWidth) return;
      var c = CH(el.getAttribute('data-chart'));
      var opt = c && buildOption(c, el);
      if (!opt) return;
      var inst = echarts.init(el, null, { renderer: 'svg' });
      inst.setOption(opt);
      inst.on('click', function (p) { if (p.data && p.data.story) goStory(p.data.story); });
      el._ec = inst; inst._el = el;
      CHARTS.push(inst);
    });
  }
  function rethemeCharts() {
    CHARTS.forEach(function (inst) {
      var el = inst._el, c = el && CH(el.getAttribute('data-chart'));
      if (c) { var o = buildOption(c, el); o.animation = false; inst.setOption(o, true); }
    });
  }
  function disposeCharts() { CHARTS.forEach(function (c) { try { c.dispose(); } catch (e) { /* ignore */ } }); CHARTS = []; }

  /* ===================== 播客 ===================== */
  function Pod(rootEl, p) {
    var self = this;
    this.root = rootEl; this.p = p; this.dur = p.duration || 0;
    this.rate = parseFloat(store.get('fd.pod.rate', '1')) || 1;
    var a = this.a = new Audio();
    a.preload = 'none';
    a.src = asset(p.file);
    a.addEventListener('timeupdate', function () { self.sync(); });
    a.addEventListener('loadedmetadata', function () { if (isFinite(a.duration)) self.dur = a.duration; if (self.pend != null) { try { a.currentTime = self.pend; } catch (e) { /* ignore */ } self.pend = null; } a.playbackRate = self.rate; self.sync(); });
    a.addEventListener('play', function () { a.playbackRate = self.rate; document.dispatchEvent(new CustomEvent('fd:play', { detail: { id: 'podcast' } })); self.sync(); });
    a.addEventListener('pause', function () { self.sync(); });
    a.addEventListener('ended', function () { self.sync(); });
    a.addEventListener('error', function () { self.err = true; self.sync(); });
    document.addEventListener('fd:play', function (e) { if (e.detail && e.detail.id !== 'podcast' && !a.paused) a.pause(); });
    this.build();
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (es) { self.inView = es[0].isIntersecting; self.mini(); }).observe(rootEl);
    }
  }
  Pod.prototype.build = function () {
    var self = this, p = this.p, D = this.dur || 1;
    var bars = (p.peaks || []).map(function (v) { return '<i style="height:' + Math.max(8, Math.round(v * 100)) + '%"></i>'; }).join('');
    var ticks = (p.chapters || []).slice(1).map(function (c) { return '<span class="tk" style="left:' + (c.start / D * 100).toFixed(2) + '%"></span>'; }).join('');
    this.root.innerHTML = '<div class="pod">' +
      '<div class="pod-top"><button class="pod-play" type="button" data-pod="toggle"></button><div class="pod-tt"><b>' + esc(pick(p, 'title')) + '</b><span class="pod-now"></span></div></div>' +
      '<div class="wave" role="slider" tabindex="0" aria-label="' + esc(t('pod_seek')) + '" aria-valuemin="0" aria-valuemax="' + Math.round(D) + '"><div class="bars">' + bars + '</div><div class="bars on">' + bars + '</div>' + ticks + '<span class="hd"></span></div>' +
      '<div class="pod-row"><span class="tm"></span><button type="button" data-pod="back" aria-label="' + esc(t('pod_back')) + '">−15</button><button type="button" data-pod="fwd" aria-label="' + esc(t('pod_fwd')) + '">+15</button><button type="button" data-pod="rate" aria-label="' + esc(t('pod_speed')) + '"></button></div>' +
      '<p class="pod-chk">' + esc(t('pod_ch')) + '</p><ol class="pod-ch" aria-label="' + esc(t('pod_ch')) + '">' + (p.chapters || []).map(function (c, i) {
        return '<li><button type="button" data-pod="ch" data-i="' + i + '"><span class="t">' + fmtTime(c.start) + '</span><span>' + esc(pick(c, 'title')) + '</span></button></li>';
      }).join('') + '</ol></div>';
    this.wave = $('.wave', this.root);
    this.root.onclick = function (e) {
      var b = e.target.closest('[data-pod]'); if (!b) return;
      var k = b.getAttribute('data-pod');
      if (k === 'toggle') self.toggle();
      else if (k === 'back') self.seek(self.a.currentTime - 15);
      else if (k === 'fwd') self.seek(self.a.currentTime + 15);
      else if (k === 'rate') { var R = [1, 1.25, 1.5, 0.8]; self.rate = R[(R.indexOf(self.rate) + 1) % R.length] || 1; self.a.playbackRate = self.rate; store.set('fd.pod.rate', String(self.rate)); self.sync(); }
      else if (k === 'ch') self.playAt(p.chapters[+b.getAttribute('data-i')].start);
    };
    var frac = function (e) { var r = self.wave.getBoundingClientRect(); return Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)); };
    this.wave.onpointerdown = function (e) {
      self.drag = true; try { self.wave.setPointerCapture(e.pointerId); } catch (x) { /* ignore */ }
      self.seek(frac(e) * self.dur, true);
    };
    this.wave.onpointermove = function (e) { if (self.drag) self.seek(frac(e) * self.dur, true); };
    this.wave.onpointerup = this.wave.onpointercancel = function () { self.drag = false; };
    this.wave.onkeydown = function (e) {
      var k = e.key, c = self.a.currentTime;
      if (k === 'ArrowRight') self.seek(c + 5); else if (k === 'ArrowLeft') self.seek(c - 5);
      else if (k === 'Home') self.seek(0); else if (k === 'End') self.seek(self.dur - 1);
      else if (k === ' ' || k === 'Enter') self.toggle(); else return;
      e.preventDefault();
    };
    this.sync();
  };
  Pod.prototype.cur = function () { return this.pend != null ? this.pend : (this.a.currentTime || 0); };
  Pod.prototype.seek = function (s) {
    s = Math.max(0, Math.min(this.dur - 0.2, s || 0));
    if (this.a.readyState < 1) { this.pend = s; this.sync(); try { this.a.currentTime = s; } catch (e) { /* 等元数据到了再设 */ } return; }
    this.a.currentTime = s; this.sync();
  };
  Pod.prototype.playAt = function (s) { this.seek(s); this.play(); };
  Pod.prototype.play = function () {
    var self = this;
    this.err = false;
    var pr = this.a.play();
    if (pr && pr.catch) pr.catch(function (e) { if (e && e.name !== 'AbortError' && e.name !== 'NotAllowedError') { self.err = true; self.sync(); } });
  };
  Pod.prototype.toggle = function () { if (this.a.paused) this.play(); else this.a.pause(); };
  Pod.prototype.chapter = function () {
    var ch = this.p.chapters || [], s = this.cur(), i = 0;
    for (var k = 0; k < ch.length; k++) if (ch[k].start <= s + 0.3) i = k;
    return i;
  };
  Pod.prototype.sync = function () {
    var a = this.a, s = this.cur(), D = this.dur || 1, playing = !a.paused && !a.ended;
    var pct = Math.min(100, s / D * 100).toFixed(2) + '%';
    var b = $('.pod-play', this.root);
    if (b) { b.innerHTML = playing ? ICON.pause : ICON.play; b.setAttribute('aria-label', t(playing ? 'pod_pause' : 'pod_play')); }
    $('.pod', this.root).classList.toggle('playing', playing);
    if (this.wave) { this.wave.style.setProperty('--p', pct); this.wave.setAttribute('aria-valuenow', Math.round(s)); this.wave.setAttribute('aria-valuetext', fmtTime(s)); }
    var tm = $('.tm', this.root); if (tm) tm.textContent = fmtTime(s) + ' / ' + fmtTime(D);
    var rb = $('[data-pod="rate"]', this.root); if (rb) rb.textContent = this.rate + '×';
    var ci = this.chapter(), ch = (this.p.chapters || [])[ci];
    $$('[data-pod="ch"]', this.root).forEach(function (x, k) { x.classList.toggle('on', k === ci && (s > 0 || playing)); });
    var now = $('.pod-now', this.root);
    if (now) now.textContent = this.err ? t('pod_err') : ((s > 0 || playing) && ch ? pick(ch, 'title') + ' · ' + fmtTime(s) : fmtTime(D));
    this.mini();
  };
  Pod.prototype.mini = function () {
    var m = $('#mini'), a = this.a;
    if (!a.paused) { this.started = true; this.closed = false; }
    if (!(this.inView === false && this.started && !this.closed)) { m.hidden = true; return; }
    if (!m.firstChild) {
      m.innerHTML = '<button class="pod-play" type="button" data-act="mini-toggle"></button><button class="mt" type="button" data-act="mini-go"></button><button class="icon-btn sm" type="button" data-act="mini-close" aria-label="' + esc(t('mini_close')) + '">' + ICON.close + '</button>';
    }
    m.hidden = false;
    var ch = (this.p.chapters || [])[this.chapter()];
    var pb = $('.pod-play', m); pb.innerHTML = a.paused ? ICON.play : ICON.pause; pb.setAttribute('aria-label', t(a.paused ? 'pod_play' : 'pod_pause'));
    $('.mt', m).innerHTML = esc(ch ? pick(ch, 'title') : pick(this.p, 'title')) + '<span>' + fmtTime(this.cur()) + ' / ' + fmtTime(this.dur) + '</span>';
  };
  Pod.prototype.setLang = function () { this.build(); };

  /* ===================== 看与听：视频滚到附近才加载（GSAP＋video2.js＋样式），播客马上可用 ===================== */
  var vid = { state: 0, wait: [] };
  function videoCtx() { return { lang: function () { return lang; }, t: t, pick: pick, asset: function (p) { return (window.FD_VIDEO3_ASSETS && window.FD_VIDEO3_ASSETS[p]) || asset(p); }, normImage: normImage, host: host, store: store, go: function (id) { goStory(id); }, jumpSource: function (sid) { jumpSource(sid); } }; }
  function ensureVideo(cb) {
    if (players.video) { if (cb) cb(players.video); return; }
    var v = ISSUE.media && ISSUE.media.video, rootEl = $('#video-root');
    if (!v || !rootEl) return;
    if (cb) vid.wait.push(cb);
    if (vid.state) return;
    vid.state = 1;
    rootEl.classList.add('loading');
    var left = 2;
    var done = function () {
      if (--left) return;
      var P = null;
      try {
        if (v.v === 3 && window.FDVideo3) P = window.FDVideo3.mount(rootEl, v, videoCtx());
        else if (v.v === 2 && window.FDVideo2) P = window.FDVideo2.mount(rootEl, v, videoCtx());
        else if (v.v !== 2 && v.v !== 3 && window.FDVideo) P = window.FDVideo.mount(rootEl, v, videoCtx());
      } catch (e) { console.warn('[video]', e); }
      rootEl.classList.remove('loading');
      players.video = P; vid.state = 2;
      if (window.FD) window.FD.players = players;
      var w = vid.wait; vid.wait = [];
      if (P) w.forEach(function (f) { f(P); });
    };
    if (v.v === 3) {                     // v3：三维今日地图，同样滚到附近才加载（three.js 打包文件压缩后约 230 KB）
      loadCSS('video3.css', done);
      var chain = function () { loadScript('vendor/three/three-bundle.min.js', function () { loadScript('vendor/gsap.min.js', function () { loadScript('video3.js', done); }); }); };
      if (location.protocol === 'file:') loadScript(asset('video3_assets.js'), chain);   // 双击打开时三维画面只能用 data: 地址的配图
      else chain();
      return;
    }
    loadCSS('video.css', function () { loadCSS('video2.css', done); });
    if (v.v === 2) loadScript('vendor/gsap.min.js', function () { loadScript('video2.js', done); });
    else loadScript('video.js', done);
  }
  function mountMedia() {
    var p = ISSUE.media && ISSUE.media.podcast;
    if (p && $('#pod-root')) players.podcast = new Pod($('#pod-root'), p);
    window.FD.players = players;
    var sec = $('#sec-media');
    if (!sec || !(ISSUE.media && ISSUE.media.video)) return;
    if (STATIC || !('IntersectionObserver' in window)) { ensureVideo(); return; }
    var ob = new IntersectionObserver(function (es) {
      if (es[0].isIntersecting) { ob.disconnect(); ensureVideo(); }
    }, { rootMargin: (ISSUE.media.video && ISSUE.media.video.v === 3) ? '0px 0px 120px 0px' : '500px 0px 500px 0px' });   // 三维视频较大：快露出来时才加载，不占首屏
    ob.observe(sec);
  }
  function setMediaTab(tab) {
    UI.media = tab;
    var w = $('.media'); if (!w) return;
    w.setAttribute('data-tab', tab);
    $$('#mtabs button').forEach(function (b) { b.setAttribute('aria-selected', b.getAttribute('data-tab') === tab); });
    if (tab === 'listen' && players.video && players.video.playing && window.innerWidth < 760) players.video.pause();
  }
  function watchScene(i) {
    setMediaTab('watch');
    scrollToEl($('#sec-media'));
    ensureVideo(function (v) {
      var sc = v.scenes[i] || v.scenes[0];
      v.seek(sc.start + 0.01);
      v.play();
    });
  }
  function listen(tm) {
    var p = players.podcast; if (!p) return;
    if (window.innerWidth < 760) setMediaTab('listen');
    if (tm === '' || tm == null) { p.toggle(); return; }
    p.playAt(+tm);
  }

  /* ===================== 页内跳转 ===================== */
  function scrollToEl(el, extra) {
    if (!el) return;
    var y = el.getBoundingClientRect().top + window.pageYOffset - (extra == null ? 20 : extra);
    window.scrollTo({ top: Math.max(0, y), behavior: animOK() ? 'smooth' : 'auto' });
  }
  function openFlash(id, force) {
    var row = document.getElementById('f-' + id); if (!row) return;
    var open = force ? true : !row.classList.contains('open');
    UI.flash = open ? id : null;
    $$('.frow').forEach(function (r) { var on = r === row && open; r.classList.toggle('open', on); $('button', r).setAttribute('aria-expanded', on); });
  }
  function selectSlide(key, i) {
    var P = PAGERS[key];
    if (P) P.show(i, 0, true);
    else UI.pg[key] = i;
  }
  function goStory(id) {
    var st = S(id); if (!st) return;
    hideTip();
    var k = st.kind;
    if (k === 'headline') { selectSlide('headline', ((ISSUE.order.headline || []).filter(S)).indexOf(id)); scrollToEl($('#sec-headline')); }
    else if (k === 'brief') { selectSlide('brief', ((ISSUE.order.brief || []).filter(S)).indexOf(id)); scrollToEl($('#sec-brief')); }
    else if (k === 'flash') { openFlash(id, true); scrollToEl($('#f-' + id), 80); }
    else if (k === 'cn_intl') {
      var pi = (ISSUE.pairs || []).filter(pairOK).map(function (p) { return p.cn === id || p.intl === id; }).indexOf(true);
      if (pi >= 0) selectSlide('pairs', pi);
      scrollToEl($('#sec-pairs'));
    } else if (k === 'teaser') {
      var W = (ISSUE.watch || []).slice(0, 5), wi = W.map(function (w) { return w.story; }).indexOf(id);
      if (wi >= 0) { selectSlide('watch', wi); setWdet(wi, true); }
      scrollToEl($('#sec-watch'));
    } else if (k === 'term') { scrollToEl($('#sec-term')); }
    else if (k === 'deep') { scrollToEl($('#sec-deep')); }
  }
  function setWdet(k, on) {
    UI.wdet[k] = on;
    var d = document.getElementById('wd-' + k), b = $('[data-act="wdet"][data-k="' + k + '"]');
    if (d) d.hidden = !on;
    if (b) { b.setAttribute('aria-expanded', on); b.textContent = t(on ? 'w_less' : 'w_more'); }
  }

  /* ===================== 提示框（上标引用、报道光谱） ===================== */
  var tip = null, tipFor = null, tipT = 0;
  function showTip(el) {
    var html;
    if (el.matches('sup.cite')) {
      var s = srcById(el.getAttribute('data-s')); if (!s) return;
      html = '<b>[' + (CITE.order[s.id] || '?') + '] ' + esc(s.name) + '</b>' + esc(s.title || host(s.url)) + '<i>' + esc(s.date) +
        (lastPointer === 'touch' ? '</i><button class="go" type="button" data-act="srcgo" data-s="' + esc(s.id) + '">' + esc(t('cite_go')) + '</button>' : ' · ' + esc(t('cite_go')).replace(' →', '') + '</i>');
    } else {
      html = esc(el.getAttribute('data-tip')).replace(/\n/g, '<br>');
    }
    clearTimeout(tipT);
    tip.innerHTML = html; tip.hidden = false; tipFor = el;
    var r = el.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight, vw = window.innerWidth, m = 12;
    var left = Math.min(vw - w - m, Math.max(m, r.left + r.width / 2 - w / 2));
    var top = r.top - h - 10;
    if (top < m) top = r.bottom + 10;
    tip.style.left = Math.round(left) + 'px'; tip.style.top = Math.round(top) + 'px';
    $$('sup.cite a.on').forEach(function (a) { a.classList.remove('on'); });
    if (el.matches('sup.cite')) el.firstChild.classList.add('on');
    requestAnimationFrame(function () { tip.classList.add('on'); });
  }
  function hideTip() {
    if (!tip || tip.hidden) return;
    tip.classList.remove('on'); tipFor = null;
    $$('sup.cite a.on').forEach(function (a) { a.classList.remove('on'); });
    tipT = setTimeout(function () { if (!tipFor) tip.hidden = true; }, animOK() ? 220 : 0);
  }

  /* ===================== 出场、数字滚动、图表懒加载 ===================== */
  function countUp(el) {
    var to = +el.getAttribute('data-to'), from = +el.getAttribute('data-from') || 0;
    var dec = +el.getAttribute('data-dec') || 0, comma = el.getAttribute('data-comma') === '1';
    if (!animOK()) { el.textContent = fmtN(to, dec, comma); return; }
    var t0 = 0, D = 1500;
    var step = function (now) {
      if (!t0) t0 = now;
      var k = Math.min(1, (now - t0) / D), e = 1 - Math.pow(1 - k, 4);
      el.textContent = fmtN(from + (to - from) * e, dec, comma);
      if (k < 1) requestAnimationFrame(step);
    };
    el.textContent = fmtN(from, dec, comma);
    requestAnimationFrame(step);
  }
  function onSeen(el) {
    if (el.classList.contains('rv') && !el.classList.contains('in')) {
      el.classList.add('in');
      if (el.classList.contains('numt')) {
        var c = $('.cnt', el), dl = parseInt(el.style.getPropertyValue('--d'), 10) || 0;
        if (c) { if (animOK()) c.textContent = fmtN(+c.getAttribute('data-from') || 0, +c.getAttribute('data-dec') || 0, c.getAttribute('data-comma') === '1'); setTimeout(function () { countUp(c); }, dl); }
      }
    }
    if (el.hasAttribute('data-tl') && !el.classList.contains('go')) { void el.offsetWidth; el.classList.add('go'); }
    if (el.classList.contains('chart')) initChart(el);
  }
  function inViewport(el) { var r = el.getBoundingClientRect(); return r.bottom > 0 && r.top < window.innerHeight && r.width > 0; }
  function observeNew() {
    var els = $$('#c-main .rv:not(.in), #c-main [data-tl]:not(.go), #c-main .chart');
    if (!io || !animOK()) { els.forEach(function (el) { if (el.classList.contains('rv') || el.offsetWidth) onSeen(el); }); if (!io) return; }
    els.forEach(function (el) { if (!el._obs) { el._obs = true; io.observe(el); } });
    $$('#c-main .chart').forEach(function (el) { if (!el._ec && el.offsetWidth && inViewport(el)) initChart(el); });
    $$('#c-main [data-tl]').forEach(function (el) { if (el.offsetWidth && inViewport(el) && !el.classList.contains('go')) onSeen(el); });
  }
  function setupIO() {
    if (!('IntersectionObserver' in window)) { root.classList.add('no-io'); return; }
    if (io) io.disconnect();
    io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target;
        if (el.classList.contains('chart') && !el.offsetWidth) return;
        onSeen(el);
        if (el.classList.contains('rv') && !el.classList.contains('chart') && !el.hasAttribute('data-tl')) io.unobserve(el);
      });
    }, { rootMargin: '0px 0px -6% 0px', threshold: 0.06 });
  }

  /* ===================== 渲染 ===================== */
  function renderContent() {
    disposeCharts();
    if (io) setupIO();
    SECN = 0;
    var keep = null;
    $$('#c-main > .sec').some(function (s) { var r = s.getBoundingClientRect(); if (r.bottom > 80) { keep = { id: s.id, y: r.top }; return true; } return false; });
    ISSUE.order = ISSUE.order || {};   // 按页面上的先后顺序生成，小编号才对
    var sun = edition() === 'sun';
    // 周日（11-01 晚定）：本周深谈卡 → 看与听 → 本周深谈 → 本周快讯 → 接下来看什么 → 参考来源（不单列今日数字）
    var pre = secCard() + (sun ? '' : secNumbers()), mediaHTML = ISSUE.media ? secMedia() : '';
    var slot = mediaHTML ? '<div id="media-slot"></div>' : '';
    var html = sun ? pre + slot + secDeep() + secFlash() + secWatch() + secPairs() + secSources()
      : pre + slot + secHeadlines() + secBriefs() + secFlash() + secDeep() + secWatch() + secPairs() + secTerm() + secSources();
    var cm = $('#c-main');
    var media = $('#sec-media');
    if (media) media.parentNode.removeChild(media);
    cm.innerHTML = html;
    var slot = $('#media-slot');
    if (slot) {
      var tmp = document.createElement('div'); tmp.innerHTML = mediaHTML;
      var fresh = tmp.firstChild;
      if (media) {   // 换语言时保留正在播放的播放器，只换标题
        $('.sec-h', media).outerHTML = $('.sec-h', fresh).outerHTML;
        if ($('#mtabs', media) && $('#mtabs', fresh)) $('#mtabs', media).innerHTML = $('#mtabs', fresh).innerHTML;
        slot.parentNode.replaceChild(media, slot);
      } else slot.parentNode.replaceChild(fresh, slot);
    }
    numberCites();
    glueCites();
    renderSources();
    mountPagers();
    bindTermCard();
    if (keep) { var s = document.getElementById(keep.id); if (s) window.scrollTo(0, s.getBoundingClientRect().top + window.pageYOffset - keep.y); }
    if (keep || !animOK()) $$('#c-main .rv').forEach(function (el) { if (!animOK() || inViewport(el)) onSeen(el); });
    observeNew();
  }
  function setLang(l) {
    if (l === lang) return;
    lang = l; store.set('fd.lang', l);
    root.lang = l === 'en' ? 'en' : 'zh-CN';
    document.title = (lang === 'en' ? SITE.name_en_short : SITE.name_zh) + ' · ' + DATE;
    renderTop();
    fbTexts();
    if (!ISSUE) return;
    renderContent();
    if (players.video) players.video.setLang();
    if (players.podcast) players.podcast.setLang();
    $('#mini').innerHTML = '';
    if (players.podcast) players.podcast.sync();
  }
  function soft(fn) {   // 换深浅色时整页柔和地交叉淡入（浏览器支持 View Transitions 时）
    if (animOK() && document.startViewTransition) document.startViewTransition(fn); else fn();
  }
  function toggleTheme() {
    var next = effTheme() === 'dark' ? 'light' : 'dark';
    soft(function () { root.setAttribute('data-theme', next); });
    store.set('fd3.theme', next);
    var b = $('[data-act="theme"]'); if (b) b.setAttribute('aria-label', t(next === 'dark' ? 'to_light' : 'to_dark'));
    setTimeout(function () { rethemeCharts(); if (FIELD) FIELD.refresh(); }, 30);
  }

  /* ===================== 今日一词：整张卡转过来 ===================== */
  function bindTermCard() {
    var card = $('#termCard');
    if (!card) return;
    var on = card.classList.contains('flipped');
    $('.front', card).inert = on; $('.back', card).inert = !on;
    $(on ? '.front' : '.back', card).setAttribute('aria-hidden', 'true');
  }
  function flip(card) {
    if (!card || card._busy || STATIC || !card.id) return;
    var on = !card.classList.contains('flipped');
    var front = $('.front', card), back = $('.back', card);
    var swap = function () {
      card.classList.toggle('flipped', on); UI.flip = on;
      front.inert = on; back.inert = !on;
      if (on) { front.setAttribute('aria-hidden', 'true'); back.removeAttribute('aria-hidden'); }
      else { back.setAttribute('aria-hidden', 'true'); front.removeAttribute('aria-hidden'); }
      var b = $((on ? '.back' : '.front') + ' [data-act="flip"]', card);
      if (b) { try { b.focus({ preventScroll: true }); } catch (e) { b.focus(); } }
    };
    if (!animOK() || !card.animate) { swap(); return; }
    card._busy = true;
    var P = 'perspective(1600px) ';
    var a1 = card.animate([{ transform: P + 'rotateY(0deg)' }, { transform: P + 'rotateY(' + (on ? 90 : -90) + 'deg) scale(.96)' }],
      { duration: 260, easing: 'cubic-bezier(.55,.06,.68,.19)', fill: 'forwards' });
    a1.onfinish = function () {
      swap();
      var a2 = card.animate([{ transform: P + 'rotateY(' + (on ? -90 : 90) + 'deg) scale(.96)' }, { transform: P + 'rotateY(0deg)' }],
        { duration: 520, easing: 'cubic-bezier(.22,.61,.36,1)', fill: 'forwards' });
      a2.onfinish = function () { a1.cancel(); a2.cancel(); card._busy = false; };
    };
  }

  /* ===================== 事件 ===================== */
  function bindGlobal() {
    tip = $('#tip');
    document.addEventListener('pointerdown', function (e) { lastPointer = e.pointerType || 'mouse'; }, true);
    document.addEventListener('click', onClick);
    document.addEventListener('keydown', onKey);
    document.addEventListener('mouseover', function (e) {
      if (lastPointer === 'touch' || !HOVER()) return;
      var c = e.target.closest && e.target.closest('sup.cite, [data-tip]');
      if (c && c !== tipFor) showTip(c);
    });
    document.addEventListener('mouseout', function (e) {
      var c = e.target.closest && e.target.closest('sup.cite, [data-tip]');
      if (c && !(e.relatedTarget && (c.contains(e.relatedTarget) || tip.contains(e.relatedTarget)))) hideTip();
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Tab') lastPointer = 'key'; }, true);
    document.addEventListener('focusin', function (e) {
      if (lastPointer === 'touch') return;
      var c = e.target.closest && e.target.closest('sup.cite, [data-tip]');
      if (c) showTip(c);
    });
    document.addEventListener('focusout', function (e) {
      var c = e.target.closest && e.target.closest('sup.cite, [data-tip]');
      if (c && !(e.relatedTarget && tip.contains(e.relatedTarget))) hideTip();
    });
    window.addEventListener('scroll', function () { if (tipFor) hideTip(); }, { passive: true });
    // 复制正文时去掉组装时插入的看不见的换行点（U+200B），粘贴到别处不会多出怪字符
    document.addEventListener('copy', function (e) {
      var sel = window.getSelection ? String(window.getSelection()) : '';
      if (!sel || sel.indexOf('\u200b') < 0 || !e.clipboardData) return;
      e.clipboardData.setData('text/plain', sel.replace(/\u200b/g, ''));
      e.preventDefault();
    });
    var rt = 0;
    window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { CHARTS.forEach(function (c) { c.resize(); }); }, 150); });
    var onScheme = function () { if (!root.getAttribute('data-theme')) setTimeout(function () { rethemeCharts(); if (FIELD) FIELD.refresh(); }, 30); var b = $('[data-act="theme"]'); if (b) b.setAttribute('aria-label', t(effTheme() === 'dark' ? 'to_light' : 'to_dark')); };
    if (mqDark) { if (mqDark.addEventListener) mqDark.addEventListener('change', onScheme); else if (mqDark.addListener) mqDark.addListener(onScheme); }
  }
  function onClick(e) {
    var cite = e.target.closest('sup.cite');
    if (cite) {
      e.preventDefault();
      if (lastPointer === 'touch' && tipFor !== cite) { showTip(cite); return; }
      jumpSource(cite.getAttribute('data-s'));
      return;
    }
    var spec = e.target.closest('.spec[data-tip]');
    if (spec && lastPointer === 'touch') { if (tipFor === spec) hideTip(); else showTip(spec); return; }
    var el = e.target.closest('[data-act]');
    if (!el) {
      if (!e.target.closest('#tip')) hideTip();
      if (!e.target.closest('#datebar')) closeCal();
      return;
    }
    if (!e.target.closest('#datebar') && el.getAttribute('data-act') !== 'cal') closeCal();
    var act = el.getAttribute('data-act'), id = el.getAttribute('data-id');
    switch (act) {
      case 'go': goStory(id); break;
      case 'listen': listen(el.getAttribute('data-t')); break;
      case 'watch': watchScene(+el.getAttribute('data-scene') || 0); break;
      case 'more': {
        var b = document.getElementById('body-' + id), lead = document.getElementById('lead-' + id), on = b.hidden;
        b.hidden = !on; if (lead) lead.hidden = on; UI.more[id] = on;
        el.setAttribute('aria-expanded', on); el.textContent = t(on ? 'read_less' : 'read_more');
        if (!on) { var sl = el.closest('.slide'); if (sl && sl.getBoundingClientRect().top < 0) scrollToEl(sl, 30); }
        break;
      }
      case 'ctab': {
        var sid = el.getAttribute('data-story'), k = +el.getAttribute('data-k'), panel = document.getElementById('cp-' + sid);
        UI.ctab[sid] = k;
        $$('.ctabs button', panel).forEach(function (x, j) { x.setAttribute('aria-selected', j === k); x.tabIndex = j === k ? 0 : -1; });
        $$('.cbody', panel).forEach(function (x, j) { x.hidden = j !== k; });
        $('.ct', panel).textContent = pick(CH(S(sid).charts[k]), 'title');
        $$('[data-tl]', panel).forEach(function (x) { x.classList.remove('go'); });
        observeNew();
        break;
      }
      case 'fopen': openFlash(id); break;
      case 'dl': scrollToEl(document.getElementById('dl-' + el.getAttribute('data-k')), 24); break;
      case 'gloss': setGloss(!UI.gloss); break;
      case 'glgo': setGloss(true); scrollToEl($('#glbox'), 24); break;
      case 'wdet': { var key = +el.getAttribute('data-k'); setWdet(key, !UI.wdet[key]); break; }
      case 'pexp': {
        var x = document.getElementById('x-' + id), op = x.hidden;
        x.hidden = !op; UI.pexp[id] = op;
        el.setAttribute('aria-expanded', op); el.textContent = t(op ? 'read_less' : 'read_more');
        observeNew();
        break;
      }
      case 'flip': flip(el.closest('.term-card')); break;
      case 'srctoggle': setSrcOpen(!UI.srcOpen); break;
      case 'srcall': UI.srcAll = !UI.srcAll; renderSources(); break;
      case 'srcgo': jumpSource(el.getAttribute('data-s')); break;
      case 'mtab': setMediaTab(el.getAttribute('data-tab')); break;
      case 'mini-toggle': if (players.podcast) players.podcast.toggle(); break;
      case 'mini-go': setMediaTab('listen'); scrollToEl($('#sec-media')); break;
      case 'mini-close': if (players.podcast) { players.podcast.a.pause(); players.podcast.closed = true; players.podcast.mini(); } break;
      case 'day': go(el.getAttribute('data-date')); break;
      case 'pickdate': go(el.getAttribute('data-date')); break;
      case 'cal': {
        var c = $('#cal');
        if (c && !c.hidden) closeCal(); else { if (el.closest('#foot')) window.scrollTo({ top: 0, behavior: animOK() ? 'smooth' : 'auto' }); openCal(); }
        break;
      }
      case 'calm': {
        var ym = calMonth.split('-'), dt = new Date(+ym[0], +ym[1] - 1 + (+el.getAttribute('data-d')), 1);
        calMonth = dt.getFullYear() + '-' + pad2(dt.getMonth() + 1);
        renderCal();
        break;
      }
      case 'lang': setLang(el.getAttribute('data-l')); break;
      case 'theme': toggleTheme(); break;
      case 'fb': if (fbIsOpen()) fbClose(); else fbOpen(el); break;
    }
  }
  function onKey(e) {
    if (e.key === 'Escape' && fbIsOpen()) { e.preventDefault(); fbClose(); return; }   // 先关反馈框，别的不动
    if (e.key === 'Escape') { closeCal(); hideTip(); return; }
    var tab = e.target.closest && e.target.closest('.ctabs [role="tab"]');
    if (tab && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) {
      var all = $$('[role="tab"]', tab.parentNode), i = all.indexOf(tab), j = (i + (e.key === 'ArrowRight' ? 1 : -1) + all.length) % all.length;
      e.preventDefault(); all[j].click(); all[j].focus();
    }
  }

  /* ===================== 背景的“数字层”（v3.1）：稀疏的点和短细线，Canvas 2D，不用任何库 =====================
   * 颜色取当天主题色（--accent-rgb），浓淡取 --dots-a / --dots-l（深浅色各一套），在毛玻璃后面只隐约透出一点。
   * 每个点绕着自己的位置慢慢漂；鼠标靠近时周围的点轻轻让开、连线稍亮（只在有鼠标的设备上）；滚动时这一层比页面慢，有一点视差。
   * 省电：像素比最多 1.5；手机上点更少；平时每秒约 30 帧，鼠标在动或正在滚动时才满帧；标签页不在前台时完全停画。
   * “减少动态效果”：只画一张静止的。截图模式（?static=1）：铺满整页画一张静止的，和背景色团一样。 */
  var FIELD = null;
  function rng(seed) {   // 固定种子的随机数：每次打开点的位置都一样，截图也稳定
    return function () {
      seed = (seed + 0x6D2B79F5) | 0;
      var x = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
      return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
    };
  }
  function Field(cv) {
    var self = this;
    this.cv = cv; this.ctx = cv.getContext('2d');
    this.raf = 0; this.last = 0; this.t0 = 0; this.busyAt = 0; this.page = false;
    this.mouse = { x: -9999, y: -9999, on: false };
    this.colors(); this.size();
    var rt = 0;
    window.addEventListener('resize', function () {
      clearTimeout(rt);
      rt = setTimeout(function () { if (!self.page) { self.size(); self.kick(); } }, 200);
    });
    window.addEventListener('pointermove', function (e) {
      if (e.pointerType !== 'mouse') return;
      self.mouse.x = e.clientX; self.mouse.y = e.clientY; self.mouse.on = true; self.busyAt = performance.now();
    }, { passive: true });
    document.addEventListener('mouseout', function (e) { if (!e.relatedTarget) self.mouse.on = false; });
    window.addEventListener('scroll', function () { self.busyAt = performance.now(); }, { passive: true });
    document.addEventListener('visibilitychange', function () { self.kick(); });
    if (mqRM) { var f = function () { self.kick(); }; if (mqRM.addEventListener) mqRM.addEventListener('change', f); else if (mqRM.addListener) mqRM.addListener(f); }
    this.kick();
  }
  Field.prototype.colors = function () {
    var cs = getComputedStyle(root);
    this.rgb = (cs.getPropertyValue('--accent-rgb') || '').trim().split(/\s+/).join(',') || '232,140,20';
    this.aDot = parseFloat(cs.getPropertyValue('--dots-a')) || 0.42;
    this.aLine = parseFloat(cs.getPropertyValue('--dots-l')) || 0.15;
  };
  Field.prototype.size = function (pageH) {
    var W = document.documentElement.clientWidth || window.innerWidth, H = pageH || window.innerHeight;
    var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    if (pageH && W * H * dpr * dpr > 12e6) dpr = 1;   // 截图模式整页很长，画布别太大
    this.W = W; this.H = H; this.dpr = dpr; this.small = W < 640;
    this.cv.width = Math.round(W * dpr); this.cv.height = Math.round(H * dpr);
    this.cv.style.width = W + 'px'; this.cv.style.height = H + 'px';
    var cell = this.small ? 116 : 96, M = this.M = 90, R = rng(20261031), pts = [];
    this.FH = H + 2 * M;                      // 上下各多出一截：点从一头漂出去，从另一头补回来，看不出跳动
    for (var y = 0; y < this.FH; y += cell) {
      for (var x = -cell / 2; x < W + cell / 2; x += cell) {
        if (R() < 0.24) continue;             // 留些空格子，免得看起来像网格
        pts.push({ bx: x + R() * cell, by: y + R() * cell, ph: R() * 6.283, sp: 0.07 + R() * 0.12,
          ax: 7 + R() * 14, ay: 7 + R() * 14, r: 0.7 + R() * 1.1, dx: 0, dy: 0 });
      }
    }
    this.pts = pts; this.xs = new Float32Array(pts.length); this.ys = new Float32Array(pts.length);
    this.link = this.small ? 110 : 126;
  };
  Field.prototype.draw = function (t, still) {
    var c = this.ctx, W = this.W, H = this.H, M = this.M, FH = this.FH, pts = this.pts, n = pts.length, xs = this.xs, ys = this.ys;
    var sy = still || this.page ? 0 : (window.pageYOffset || 0) * 0.12;   // 视差：滚 100 像素，这一层只挪 12 像素
    var mx = this.mouse.x, my = this.mouse.y, mon = this.mouse.on && !still && HOVER(), R = 150, R2 = R * R;
    var i, j, p, x, y;
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    for (i = 0; i < n; i++) {
      p = pts[i];
      x = p.bx + Math.sin(t * p.sp + p.ph) * p.ax;
      y = p.by + Math.cos(t * p.sp * 0.8 + p.ph * 1.3) * p.ay - sy;
      y = ((y % FH) + FH) % FH - M;
      var tx = 0, ty = 0;
      if (mon) {   // 鼠标附近的点轻轻让开，离开后慢慢回到原处
        var ex = x - mx, ey = y - my, e2 = ex * ex + ey * ey;
        if (e2 < R2 && e2 > 0.01) { var e = Math.sqrt(e2), k = 1 - e / R; k = k * k * 28; tx = ex / e * k; ty = ey / e * k; }
      }
      p.dx += (tx - p.dx) * (still ? 1 : 0.08); p.dy += (ty - p.dy) * (still ? 1 : 0.08);
      xs[i] = x + p.dx; ys[i] = y + p.dy;
    }
    var L = this.link, L2 = L * L;
    c.lineWidth = 1;
    for (i = 0; i < n; i++) {
      if (ys[i] < -L || ys[i] > H + L) continue;
      for (j = i + 1; j < n; j++) {
        var dx = xs[i] - xs[j], dy = ys[i] - ys[j], dd = dx * dx + dy * dy;
        if (dd > L2) continue;
        var a = (1 - Math.sqrt(dd) / L) * this.aLine;
        if (mon) { var qx = (xs[i] + xs[j]) / 2 - mx, qy = (ys[i] + ys[j]) / 2 - my, q2 = qx * qx + qy * qy; if (q2 < R2) a *= 1 + 1.5 * (1 - Math.sqrt(q2) / R); }
        if (a < 0.008) continue;
        c.strokeStyle = 'rgba(' + this.rgb + ',' + a.toFixed(3) + ')';
        c.beginPath(); c.moveTo(xs[i], ys[i]); c.lineTo(xs[j], ys[j]); c.stroke();
      }
    }
    for (i = 0; i < n; i++) {
      if (ys[i] < -4 || ys[i] > H + 4) continue;
      var ad = this.aDot;
      if (mon) { var fx = xs[i] - mx, fy = ys[i] - my, f2 = fx * fx + fy * fy; if (f2 < R2) ad = Math.min(0.9, ad * (1 + 0.8 * (1 - Math.sqrt(f2) / R))); }
      c.fillStyle = 'rgba(' + this.rgb + ',' + ad.toFixed(3) + ')';
      c.beginPath(); c.arc(xs[i], ys[i], pts[i].r, 0, 6.283); c.fill();
    }
  };
  Field.prototype.kick = function () {
    var self = this;
    cancelAnimationFrame(this.raf); this.raf = 0;
    if (this.page) return;
    if (!animOK()) { this.draw(0, true); return; }   // 减少动态效果：一张静止的
    if (document.hidden) return;                     // 标签页在后台：停画
    var tick = function (now) {
      self.raf = requestAnimationFrame(tick);
      var busy = now - self.busyAt < 900;
      if (now - self.last < (busy && !self.small ? 0 : 31)) return;
      self.last = now;
      if (!self.t0) self.t0 = now;
      self.draw((now - self.t0) / 1000, false);
    };
    this.raf = requestAnimationFrame(tick);
  };
  Field.prototype.refresh = function () { this.colors(); if (this.page || !animOK()) this.draw(0, true); };
  Field.prototype.toPage = function (h) {   // 截图模式：画布铺满整页，画一张静止的
    this.page = true; cancelAnimationFrame(this.raf); this.raf = 0;
    this.size(h); this.colors(); this.draw(0, true);
  };
  function initField() {
    var cv = $('#dots');
    if (!cv || FIELD || !cv.getContext) return;
    try { FIELD = new Field(cv); } catch (e) { FIELD = null; }
  }

  /* ===================== 截图模式：背景色团铺满整页 ===================== */
  function staticPage() {
    var field = function () {
      var bg = $('#bg'); if (!bg) return;
      var band = Math.max(window.innerHeight, 640), h = document.documentElement.scrollHeight, out = '';
      for (var y = 0; y < h; y += band) {
        out += '<i class="blob f1" style="top:' + Math.round(y - 0.22 * band) + 'px"></i>' +
          '<i class="blob f2" style="top:' + Math.round(y + 0.26 * band) + 'px"></i>' +
          '<i class="blob f3" style="top:' + Math.round(y + 0.64 * band) + 'px"></i>';
      }
      var cv = $('#dots');
      bg.innerHTML = out; bg.classList.add('page');
      if (cv) { bg.appendChild(cv); if (FIELD) FIELD.toPage(h); }   // 数字层也铺满整页
    };
    field();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(field);
    window.addEventListener('load', field);
    setTimeout(field, 1500);
  }

  /* ===================== 读者反馈（11-10 加） =====================
   * 页脚“往期”旁边的“反馈”点开：电脑上在页面左侧的空白处浮出一个毛玻璃小框，手机上（640 像素宽以下）从底部升起一张卡。
   * 栏目：哪里不对（必填，最多 1000 字）；称呼（选填）；大概位置（选填：正在放或放到一半的播客、视频自动填上“播客 7:33”“视频 57 秒”，可以改）。
   *   期号自动带上。另有一个看不见的“网站”栏（蜜罐：人看不到也点不到，机器人会填；Worker 见到有值就当机器人，不转交）。
   * 提交：POST 到同一目录的 feedback（网站上就是 /frontier/feedback，由 cloud/deploy/src/index.js 收），只发 JSON。
   *   成功显示“收到了，谢谢”；失败说清楚可以稍后再试，写的字留着不清。
   * 只有在网站上（https://wenlongzhang.com）才真的提交。双击打开（file://）或本机预览时框照样能打开，但只说明“只能在网站上提交”，不发请求。
   *   本机看样子可以加 ?fbmock=ok|fail|rate|setup 模拟服务器的几种回应（只在不是网站时认）。
   * 键盘和读屏：Esc 关闭并回到“反馈”按钮；Tab 在框里依次走；框有名字和说明，提交结果由一个 role=status 的区域读出。 */
  var FB = { el: null, trigger: null, autoWhere: '', busy: false };
  var FB_MAX = 1000;
  var FB_ONLINE = location.protocol === 'https:' && location.hostname === 'wenlongzhang.com';
  function fbMock() {
    if (FB_ONLINE) return '';
    return (location.search.match(/[?&]fbmock=(ok|fail|rate|setup)\b/) || [])[1] || '';
  }
  function fbIsOpen() { return !!(FB.el && !FB.el.hidden); }
  function fbBuild() {
    if (FB.el) return FB.el;
    var scrim = document.createElement('div');
    scrim.className = 'fb-scrim'; scrim.id = 'fb-scrim'; scrim.hidden = true;
    scrim.addEventListener('click', function () { fbClose(); });
    var box = document.createElement('section');
    box.className = 'fb'; box.id = 'fb'; box.hidden = true;
    box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'false');
    box.setAttribute('aria-labelledby', 'fb-h'); box.setAttribute('aria-describedby', 'fb-intro');
    box.innerHTML =
      '<div class="fb-head"><h2 id="fb-h" data-fbt="fb_title"></h2><span class="fb-issue" id="fb-issue"></span>' +
        '<button class="icon-btn sm fb-x" type="button" data-fb="close" data-fbl="fb_close">' + ICON.close + '</button></div>' +
      '<p class="fb-intro" id="fb-intro" data-fbt="fb_intro"></p>' +
      '<form class="fb-form" id="fb-form" novalidate>' +
        '<div class="fb-f"><label class="fb-l" for="fb-text" data-fbt="fb_text"></label>' +
          '<textarea id="fb-text" name="text" rows="4" maxlength="' + FB_MAX + '" required aria-required="true" aria-describedby="fb-count" data-fbph="fb_text_ph"></textarea>' +
          '<span class="fb-count" id="fb-count"></span></div>' +
        '<div class="fb-f"><label class="fb-l" for="fb-name"><span data-fbt="fb_name"></span><i data-fbt="fb_opt"></i></label>' +
          '<input id="fb-name" name="name" type="text" maxlength="40" autocomplete="nickname"></div>' +
        '<div class="fb-f"><label class="fb-l" for="fb-where"><span data-fbt="fb_where"></span><i data-fbt="fb_opt"></i></label>' +
          '<input id="fb-where" name="where" type="text" maxlength="80" autocomplete="off" data-fbph="fb_where_ph"></div>' +
        '<div class="sr" aria-hidden="true"><label>Website <input name="website" type="text" tabindex="-1" autocomplete="off"></label></div>' +
        '<p class="fb-msg" id="fb-msg"></p>' +
        '<div class="fb-acts"><button class="btn sm" type="button" data-fb="close" data-fbt="fb_cancel"></button>' +
          '<button class="btn sm pri" type="submit" id="fb-send" data-fbt="fb_send"></button></div>' +
      '</form>' +
      '<div class="fb-done" id="fb-done" hidden><p class="fb-ok" data-fbt="fb_ok"></p><p class="fb-ok2" data-fbt="fb_ok_more"></p>' +
        '<div class="fb-acts"><button class="btn sm" type="button" data-fb="again" data-fbt="fb_more"></button>' +
          '<button class="btn sm pri" type="button" data-fb="close" id="fb-done-close" data-fbt="fb_close"></button></div></div>' +
      '<p class="sr" id="fb-live" role="status" aria-live="polite"></p>';
    document.body.appendChild(scrim);
    document.body.appendChild(box);
    FB.el = box;
    box.addEventListener('click', function (e) {
      var b = e.target.closest('[data-fb]'); if (!b) return;
      if (b.getAttribute('data-fb') === 'close') fbClose(); else fbAgain();
    });
    $('#fb-form').addEventListener('submit', function (e) { e.preventDefault(); fbSend(); });
    $('#fb-text').addEventListener('input', function () {
      fbCount();
      if (this.hasAttribute('aria-invalid')) { this.removeAttribute('aria-invalid'); fbMsg('', ''); }   // 开始写了，“先写一下”的提示就去掉
    });
    $('#fb-where').addEventListener('input', function () { FB.autoWhere = ''; });   // 改过就不再自动覆盖
    fbTexts();
    return box;
  }
  function fbTexts() {
    if (!FB.el) return;
    $$('[data-fbt]', FB.el).forEach(function (x) { x.textContent = t(x.getAttribute('data-fbt')); });
    $$('[data-fbph]', FB.el).forEach(function (x) { x.setAttribute('placeholder', t(x.getAttribute('data-fbph'))); });
    $$('[data-fbl]', FB.el).forEach(function (x) { x.setAttribute('aria-label', t(x.getAttribute('data-fbl'))); });
    $('#fb-issue').textContent = DATE ? t('fb_issue', { d: DATE }) : '';
    fbCount();
  }
  function fbCount() {
    var ta = $('#fb-text'), c = $('#fb-count'); if (!ta || !c) return;
    c.textContent = t('fb_count', { n: ta.value.length, max: FB_MAX });
    c.classList.toggle('near', ta.value.length > FB_MAX * 0.9);
  }
  // 大概位置：正在放的优先；都没在放时，取放到一半停下的（播客没关掉、视频没放完）
  function fbWhere() {
    var p = players.podcast, v = players.video;
    var pod = function () { return t('fb_pod', { t: fmtTime(p.cur()) }); };
    var vt = function () { return Math.round(v.now ? v.now() : (v.t || 0)); };
    try {
      if (p && p.a && !p.a.paused && !p.a.ended) return pod();
      if (v && v.playing) return t('fb_vid', { s: vt() });
      if (p && p.started && !p.closed && p.cur() > 0) return pod();
      if (v && v.started && !v.ended && vt() > 0) return t('fb_vid', { s: vt() });
    } catch (e) { /* 播放器还没好，不填 */ }
    return '';
  }
  function fbExpanded(on) { $$('[data-act="fb"]').forEach(function (b) { b.setAttribute('aria-expanded', on ? 'true' : 'false'); }); }
  function fbMsg(text, kind) {
    var m = $('#fb-msg');
    if (m) { m.textContent = text || ''; m.className = 'fb-msg' + (kind ? ' ' + kind : ''); }
    var l = $('#fb-live'); if (l) l.textContent = text || '';
  }
  function fbFocus(el) { if (!el) return; try { el.focus({ preventScroll: true }); } catch (e) { el.focus(); } }
  function fbOpen(trigger) {
    var box = fbBuild();
    FB.trigger = trigger || null;
    fbTexts();
    if (!FB.busy) { $('#fb-done').hidden = true; $('#fb-form').hidden = false; }
    var w = $('#fb-where'), auto = fbWhere();
    if (auto && (!w.value || w.value === FB.autoWhere)) { w.value = auto; FB.autoWhere = auto; }
    if (!FB.busy) fbMsg(!FB_ONLINE && !fbMock() ? t('fb_local') : '', 'info');
    hideTip(); closeCal();
    box.hidden = false; $('#fb-scrim').hidden = false;
    fbExpanded(true);
    fbFocus($('#fb-text'));
  }
  function fbClose() {
    if (!fbIsOpen()) return;
    var inside = FB.el.contains(document.activeElement);
    FB.el.hidden = true; $('#fb-scrim').hidden = true;
    fbExpanded(false);
    var back = FB.trigger && document.body.contains(FB.trigger) ? FB.trigger : $('#foot [data-act="fb"]');
    if (inside || document.activeElement === document.body) fbFocus(back);
  }
  function fbAgain() {
    $('#fb-done').hidden = true; $('#fb-form').hidden = false;
    fbMsg('', ''); fbCount();
    fbFocus($('#fb-text'));
  }
  function fbBusy(on) {
    FB.busy = on;
    var b = $('#fb-send'); if (b) b.disabled = on;
    $('#fb-form').setAttribute('aria-busy', on ? 'true' : 'false');
  }
  function fbSend() {
    if (FB.busy) return;
    var ta = $('#fb-text'), text = ta.value.trim();
    if (!text) { ta.setAttribute('aria-invalid', 'true'); fbMsg(t('fb_need'), 'err'); fbFocus(ta); return; }
    var mock = fbMock();
    if (!FB_ONLINE && !mock) { fbMsg(t('fb_local'), 'info'); return; }
    var hp = $('input[name="website"]', FB.el);
    var data = { date: DATE || '', text: text.slice(0, FB_MAX), name: $('#fb-name').value.trim().slice(0, 40),
      where: $('#fb-where').value.trim().slice(0, 80), lang: lang, website: hp ? hp.value : '' };
    fbBusy(true); fbMsg(t('fb_sending'), '');
    var finish = function (status, body) {
      fbBusy(false);
      if ((status === 200 || status === 202) && !(body && body.ok === false)) {
        ta.value = ''; $('#fb-where').value = ''; FB.autoWhere = '';   // 称呼留着，家里人连写几条不用重填
        $('#fb-form').hidden = true; $('#fb-done').hidden = false;
        fbMsg('', ''); var l = $('#fb-live'); if (l) l.textContent = t('fb_ok') + (lang === 'en' ? '. ' : '。') + t('fb_ok_more');
        fbFocus($('#fb-done-close'));
        return;
      }
      var msg = status === 429 ? t('fb_err_rate') : status === 503 ? t('fb_err_setup') : t('fb_err');
      if (status === 400 && body && (lang === 'en' ? body.error_en : body.error)) msg = lang === 'en' ? body.error_en : body.error;
      fbMsg(msg, 'err');
    };
    if (mock) { setTimeout(function () { finish({ ok: 202, fail: 502, rate: 429, setup: 503 }[mock], { ok: mock === 'ok' }); }, 600); return; }
    if (!window.fetch) { finish(0, null); return; }
    var ctl = window.AbortController ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 15000);
    fetch('feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
      credentials: 'same-origin', cache: 'no-store', signal: ctl ? ctl.signal : undefined })
      .then(function (r) {
        return r.json().catch(function () { return null; }).then(function (b) { clearTimeout(timer); finish(r.status, b); });
      })
      .catch(function () { clearTimeout(timer); finish(0, null); });
  }

  window.FD = { players: players, pagers: function () { return PAGERS; }, setLang: function (l) { setLang(l); }, goStory: function (id) { goStory(id); },
    jumpSource: function (s) { jumpSource(s); }, issue: function () { return ISSUE; }, ui: UI, field: function () { return FIELD; }, version: '3.2' };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
