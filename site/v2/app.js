/* 每日AI科技前沿简报 · v2 · app.js
 * 读 issues/index.js（往期日期）→ 按 ?date= 加载 issues/日期/issue.js → 渲染整页。
 * 双击 index.html（file://）也能用：数据都是 <script> 挂到 window 上，不用 fetch。
 * 视频：issue.media.video 带 v: 2 时用 video2.js（GSAP 动画、逐字对齐、12 种场景模板），否则用第一版 video.js；两者都按同一个 ctx 约定。
 * 图表用 vendor/echarts.min.js，滚到附近才加载。
 * 正文里的 [^s07] 渲染成上标引用，页面渲染完后按出现顺序统一编号 [1][2]…，参考来源列表据此生成。 */
(function () {
  'use strict';

  /* ===================== utils ===================== */
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var store = {
    get: function (k, f) { try { var v = localStorage.getItem(k); return v == null ? f : v; } catch (e) { return f; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage blocked: just don't remember */ } }
  };
  var RM = function () { return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); };
  var HOVER = function () { return !!(window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches); };
  var pad2 = function (n) { return String(n).padStart(2, '0'); };
  var fmtTime = function (s) { s = Math.max(0, Math.floor(s || 0)); return Math.floor(s / 60) + ':' + pad2(s % 60); };
  var fmtN = function (v, dec, comma) {
    var s = (+v).toFixed(dec || 0);
    if (comma) s = s.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return s;
  };
  var fmtNum = function (v) { return String(+(+v).toFixed(2)); };

  var ICON = {
    chevL: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    chevR: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    chevD: '<svg class="chev" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 9l7 7 7-7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M8 5.2v13.6L18.6 12z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M7 5h3.6v14H7zM13.4 5H17v14h-3.6z"/></svg>',
    headph: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 15v-3a8 8 0 0 1 16 0v3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><rect x="3" y="14" width="5" height="7" rx="2" fill="currentColor"/><rect x="16" y="14" width="5" height="7" rx="2" fill="currentColor"/></svg>',
    film: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M10 9.2v5.6l4.8-2.8z" fill="currentColor"/></svg>',
    plus: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>',
    flip: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 0 1 13.7-5.6M20 12a8 8 0 0 1-13.7 5.6M18 3v4h-4M6 21v-4h4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    close: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
    go: '<svg class="go" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h13M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    down: '<svg class="ar" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20L3 6h18z" fill="currentColor"/></svg>',
    up: '<svg class="ar" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4l9 14H3z" fill="currentColor"/></svg>',
    th_auto: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/></svg>',
    th_light: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2" fill="currentColor"/><path d="M12 2.5v2.4M12 19.1v2.4M2.5 12h2.4M19.1 12h2.4M5.3 5.3l1.7 1.7M17 17l1.7 1.7M5.3 18.7L7 17M17 7l1.7-1.7" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    th_dark: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" fill="currentColor"/></svg>'
  };
  var LOGO = '<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="#0D636D"/><path d="M6 18h5l3-8 4 13 3-7h5" fill="none" stroke="#F6F2E9" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  /* ===================== i18n ===================== */
  var I18N = {
    zh: {
      brand: '每日AI科技前沿简报', brand_alt: 'Daily AI & Tech Frontier', test: '测试版',
      prev_day: '前一期', next_day: '后一期', pick_date: '选择日期', no_more: '没有了',
      cal_count: '共 {n} 期 · 最新 {d}', cal_prev: '上个月', cal_next: '下个月',
      theme_auto: '深浅色：跟随系统', theme_light: '深浅色：浅色', theme_dark: '深浅色：深色', lang_label: '语言',
      wd: ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'], wd_s: ['日', '一', '二', '三', '四', '五', '六'],
      over: '每日AI科技前沿简报 · Daily AI & Tech Frontier', three: '今日三件事', term_k: '今日一词',
      listen_n: '听 {n} 分钟', watch_n: '看 {n} 秒', ai_img: 'AI 生成配图',
      k_numbers: '01 · Today in numbers', k_media: '02 · Watch & listen', k_headline: '03 · Top stories', k_brief: '04 · Briefs',
      k_flash: '05 · In brief', k_watch: '06 · On the radar', k_pairs: '07 · China × World', k_term: '08 · Word of the day',
      sec_numbers: '今日数字', sec_media: '看与听', sec_headline: '头条', sec_brief: '要闻', sec_flash: '快讯',
      sec_watch: '预告看板', sec_pairs: '国内外对照', sec_term: '今日一词',
      numbers_ph: '关键数字', numbers_hint: '点一下跳到那条新闻',
      media_aside: '视频 {v} 秒 · 播客 {p} 分钟 · AI 合成语音', m_watch: '看 · 视频', m_listen: '听 · 播客',
      hover_hint: '划过或点击标签切换', swipe_hint: '点标签或左右滑动切换',
      read_more: '读全文', read_less: '收起全文', why: '为什么重要',
      listen_seg: '听这一段', watch_seg: '看这一段', watch_none: '视频未涉及', sources_of: '来源 ',
      brief_hint: '点开卡片看解读，一次只展开一张', open: '展开解读', close: '收起',
      watch_hint: '只列事件卡里有出处的“将要发生的事”', watch_ph: '接下来 · 何时见分晓',
      w_rumor: '传闻', w_teaser: '预告', w_scheduled: '已排期', w_reported: '报道称', w_go: '看原条', w_more: '详情', w_less: '收起',
      page: '第 {p} / {n} 页', prev_page: '上一页', next_page: '下一页',
      pair_intl: '国外', pair_cn: '国内', pair_rel: '两边的关系', to_brief: '去看要闻',
      flip: '翻面：英文和用法', flip_back: '翻回来', term_k2: 'English · 用法', term_usage: '今天新闻里的用法', term_note: '为什么值得分清',
      src_title: '参考来源', src_sum: '共 {n} 条 · 先列被引用最多的 5 条', src_sum_all: '共 {n} 条 · 按正文首次出现排序',
      src_all: '展开全部（{n}）', src_top: '只看前 5 条', cite_go: '查看来源 →', cite_label: '来源 {n}',
      chart_src: '出处', chart_err: '图表库没有加载出来。', c_timeline: '时间线', c_graph: '关系图',
      foot_ai: '本页由 AI 辅助生成', foot_past: '往期',
      pod_ai: 'AI 合成语音', pod_ch: '章节', pod_speed: '倍速', pod_back: '后退 15 秒', pod_fwd: '前进 15 秒',
      pod_play: '播放播客', pod_pause: '暂停播客', pod_seek: '播客进度', pod_err: '播客音频没有加载出来。', mini_close: '停止播放',
      kind_headline: '头条', kind_brief: '要闻', kind_flash: '快讯', kind_teaser: '预告', kind_cn_intl: '对照', kind_term: '一词',
      status_confirmed: '已确认', status_reported: '媒体报道', status_teaser: '未经证实', region_cn: '国内', region_intl: '国际',
      spec_n: '中 {zh} · 英 {en}', spec_s: ' · 社 {so}', spec_tip: '当天归并到这一条的报道', spec_zh: '中文', spec_en: '英文', spec_so: '社区/社交',
      notice_no_issue: '没有 {date} 这一期，已显示最新一期。',
      fatal_title: '这一期没能载入', fatal_body: '找不到 {f}。请确认文件夹完整，或从往期里另选一天。', fatal_index: '找不到往期目录 issues/index.js。',
      v_play: '播放', v_pause: '暂停', v_replay: '重播', v_prev: '上一场景', v_next: '下一场景', v_cc: '字幕',
      v_silent: '无声预览', v_silent_forced: '没有旁白音频，只能无声预览', v_full: '全屏', v_seek: '视频进度',
      v_region: '视频播放器：空格播放或暂停，左右方向键快退快进，Shift 加方向键切换场景',
      v_scenes: '场景列表', v_scene: '场景', v_src: '来源：', v_orig: '原文', v_chip_ai: 'AI 合成', v_chip_silent: '无声预览', v_play_silent: '无声预览',
      v_no_audio: '没有找到旁白音频，已切换为无声预览：画面和字幕按时间轴播放，可以拖动进度条，或点下面的场景逐个查看。',
      v_audio_error: '旁白音频播放出错，已切换为无声预览。',
      v_silent_on: '无声预览中：旁白已关，画面和字幕照常按时间轴播放。',
      v_estimated: '这一版还没有对齐过的时间轴，场景和字幕的时间是按旁白字数估算的。'
    },
    en: {
      brand: 'Daily AI & Tech Frontier', brand_alt: '每日AI科技前沿简报', test: 'Test build',
      prev_day: 'Previous issue', next_day: 'Next issue', pick_date: 'Pick a date', no_more: 'None',
      cal_count: '{n} issue(s) · latest {d}', cal_prev: 'Previous month', cal_next: 'Next month',
      theme_auto: 'Theme: follow system', theme_light: 'Theme: light', theme_dark: 'Theme: dark', lang_label: 'Language',
      wd: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'], wd_s: ['S', 'M', 'T', 'W', 'T', 'F', 'S'],
      over: 'Daily AI & Tech Frontier · 每日AI科技前沿简报', three: 'Three things today', term_k: 'Word of the day',
      listen_n: 'Listen · {n} min', watch_n: 'Watch · {n} s', ai_img: 'AI-generated',
      k_numbers: '01', k_media: '02', k_headline: '03', k_brief: '04', k_flash: '05', k_watch: '06', k_pairs: '07', k_term: '08',
      sec_numbers: 'Today in numbers', sec_media: 'Watch & listen', sec_headline: 'Top stories', sec_brief: 'Briefs', sec_flash: 'In brief',
      sec_watch: 'On the radar', sec_pairs: 'China × World', sec_term: 'Word of the day',
      numbers_ph: 'Key figures', numbers_hint: 'Tap one to jump to its story',
      media_aside: 'Video {v} s · podcast {p} min · synthetic voices', m_watch: 'Watch', m_listen: 'Listen',
      hover_hint: 'Hover or click a tab to switch', swipe_hint: 'Tap a tab or swipe to switch',
      read_more: 'Read in full', read_less: 'Show less', why: 'Why it matters',
      listen_seg: 'Listen', watch_seg: 'Watch', watch_none: 'Not in the video', sources_of: 'Sources ',
      brief_hint: 'Open a card for the full story; one at a time', open: 'Open', close: 'Close',
      watch_hint: 'Only upcoming events the event cards source', watch_ph: 'Coming up · when we will know',
      w_rumor: 'Rumor', w_teaser: 'Announced', w_scheduled: 'Scheduled', w_reported: 'Reported', w_go: 'Story', w_more: 'Details', w_less: 'Hide',
      page: 'Page {p} of {n}', prev_page: 'Previous page', next_page: 'Next page',
      pair_intl: 'ELSEWHERE', pair_cn: 'CHINA', pair_rel: 'How they connect', to_brief: 'Go to the brief',
      flip: 'Flip: Chinese and usage', flip_back: 'Flip back', term_k2: '中文 · usage', term_usage: 'In today’s news', term_note: 'Why the distinction matters',
      src_title: 'References', src_sum: '{n} sources · the 5 cited most first', src_sum_all: '{n} sources · in order of first citation',
      src_all: 'Show all {n}', src_top: 'Top 5 only', cite_go: 'Go to the source →', cite_label: 'Source {n}',
      chart_src: 'Sources', chart_err: 'The chart library did not load.', c_timeline: 'Timeline', c_graph: 'Who’s who',
      foot_ai: 'This page was produced with AI assistance', foot_past: 'Past issues',
      pod_ai: 'Synthetic voice', pod_ch: 'Chapters', pod_speed: 'Speed', pod_back: 'Back 15 s', pod_fwd: 'Forward 15 s',
      pod_play: 'Play podcast', pod_pause: 'Pause podcast', pod_seek: 'Podcast position', pod_err: 'The podcast audio did not load.', mini_close: 'Stop',
      kind_headline: 'Top story', kind_brief: 'Brief', kind_flash: 'In brief', kind_teaser: 'Radar', kind_cn_intl: 'China × World', kind_term: 'Word',
      status_confirmed: 'Confirmed', status_reported: 'Reported', status_teaser: 'Unverified', region_cn: 'China', region_intl: 'World',
      spec_n: 'zh {zh} · en {en}', spec_s: ' · social {so}', spec_tip: 'Coverage merged into this story that day', spec_zh: 'Chinese', spec_en: 'English', spec_so: 'Community / social',
      notice_no_issue: 'There is no issue for {date}; showing the latest one.',
      fatal_title: 'This issue could not be loaded', fatal_body: 'Missing {f}. Check that the folder is complete, or pick another day.', fatal_index: 'The issue list issues/index.js is missing.',
      v_play: 'Play', v_pause: 'Pause', v_replay: 'Replay', v_prev: 'Previous scene', v_next: 'Next scene', v_cc: 'Subtitles',
      v_silent: 'Silent preview', v_silent_forced: 'No narration audio: silent preview only', v_full: 'Full screen', v_seek: 'Video position',
      v_region: 'Video player: Space to play or pause, arrow keys to seek, Shift+arrows to change scene',
      v_scenes: 'Scenes', v_scene: 'Scene', v_src: 'Source: ', v_orig: 'Original', v_chip_ai: 'AI-generated', v_chip_silent: 'Silent preview', v_play_silent: 'Silent preview',
      v_no_audio: 'Narration audio not found, so this is a silent preview: pictures and subtitles follow the timeline.',
      v_audio_error: 'The narration failed to play, so this switched to a silent preview.',
      v_silent_on: 'Silent preview: narration off; pictures and subtitles keep to the timeline.',
      v_estimated: 'This cut has no aligned timeline yet; timings are estimated from the narration length.'
    }
  };
  var lang = store.get('fd.lang', 'zh') === 'en' ? 'en' : 'zh';
  var theme = store.get('fd.theme', 'auto');
  if (['auto', 'light', 'dark'].indexOf(theme) < 0) theme = 'auto';
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

  /* ===================== state ===================== */
  var INDEX = window.FD_INDEX || null;
  var DATE = null, ISSUE = null, BASE = '';
  var players = { video: null, podcast: null };
  var CHARTS = [];
  var CITE = { order: {}, count: {}, list: [] };
  var UI = { hl: 0, brief: null, flash: null, pair: 0, page: 0, flip: false, srcOpen: false, srcAll: false, media: 'watch', ctab: {}, more: {}, pexp: {}, wdet: {} };
  var lastPointer = 'mouse';
  var io = null;

  var asset = function (p) { if (!p) return p; return /^(data:|blob:|https?:|file:|\/)/i.test(p) ? p : BASE + p; };
  var normImage = function (img) { if (!img) return null; if (typeof img === 'string') return { src: img }; return img.src ? img : null; };
  var host = function (url) { try { return new URL(url).hostname.replace(/^www\./, ''); } catch (e) { return ''; } };
  var S = function (id) { return (ISSUE && ISSUE.stories[id]) || null; };
  var CH = function (id) { return (ISSUE && ISSUE.charts[id]) || null; };
  var srcById = function (id) { for (var i = 0; i < ISSUE.sources.length; i++) if (ISSUE.sources[i].id === id) return ISSUE.sources[i]; return null; };

  /* ===================== boot ===================== */
  function loadScript(src, cb) {
    var s = document.createElement('script');
    s.src = src;
    s.onload = function () { cb(true); };
    s.onerror = function () { cb(false); };
    document.body.appendChild(s);
  }
  function dates() { return ((INDEX && INDEX.issues) || []).map(function (x) { return x.date; }).sort(); }
  function boot() {
    document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';
    applyTheme();
    if (!INDEX) { fatal(t('fatal_index')); return; }
    var ds = dates();
    var q = (location.search.match(/[?&]date=(\d{4}-\d{2}-\d{2})/) || [])[1];
    DATE = q && ds.indexOf(q) >= 0 ? q : (INDEX.latest || ds[ds.length - 1]);
    if (q && ds.indexOf(q) < 0) {
      var n = $('#notice'); n.hidden = false; n.innerHTML = '<p>' + esc(t('notice_no_issue', { date: q })) + '</p>';
    }
    BASE = 'issues/' + DATE + '/';
    renderTop();
    loadScript(BASE + 'issue.js', function (ok) {
      ISSUE = window.FD_ISSUES && window.FD_ISSUES[DATE];
      if (!ok || !ISSUE) { fatal(t('fatal_body', { f: BASE + 'issue.js' })); return; }
      document.title = t('brand') + ' · ' + DATE;
      $('#main').innerHTML = '<div id="c-main"></div>';
      setupIO();
      renderContent();
      mountMedia();
      bindGlobal();
    });
  }
  function fatal(msg) {
    $('#main').innerHTML = '<div class="fatal"><h1>' + esc(t('fatal_title')) + '</h1><p>' + esc(msg) + '</p></div>';
  }
  function go(date) {
    if (!date || date === DATE) { closeCal(); return; }
    location.search = '?date=' + date;
  }

  /* ===================== top bar & calendar ===================== */
  function dateLabel(d) {
    var dt = new Date(d + 'T12:00:00');
    return { d: d, wd: t('wd')[dt.getDay()] };
  }
  function renderTop() {
    var ds = dates(), i = ds.indexOf(DATE);
    var prev = i > 0 ? ds[i - 1] : '', next = i >= 0 && i < ds.length - 1 ? ds[i + 1] : '';
    var dl = DATE ? dateLabel(DATE) : { d: '', wd: '' };
    $('#top').innerHTML = '<div class="top-in">' +
      '<a class="brand" href="?date=' + esc((INDEX && INDEX.latest) || '') + '" aria-label="' + esc(t('brand')) + '">' + LOGO +
      '<span class="nm">' + esc(t('brand')) + '<small>' + esc(t('brand_alt')) + '</small></span></a>' +
      '<span class="tbadge">' + esc(t('test')) + '</span>' +
      '<div class="tools">' +
      '<div class="datebar" id="datebar">' +
      '<button class="ibtn" type="button" data-act="day" data-date="' + prev + '"' + (prev ? '' : ' disabled') + ' aria-label="' + esc(t('prev_day')) + '" title="' + esc(t('prev_day') + (prev ? ' · ' + prev : ' · ' + t('no_more'))) + '">' + ICON.chevL + '</button>' +
      '<button class="dbtn" type="button" data-act="cal" aria-haspopup="dialog" aria-expanded="false" aria-controls="cal" title="' + esc(t('pick_date')) + '"><span class="y">' + esc(dl.d.slice(0, 5)) + '</span>' + esc(dl.d.slice(5)) + ' <span class="wd">' + esc(dl.wd) + '</span>' + ICON.chevD + '</button>' +
      '<button class="ibtn" type="button" data-act="day" data-date="' + next + '"' + (next ? '' : ' disabled') + ' aria-label="' + esc(t('next_day')) + '" title="' + esc(t('next_day') + (next ? ' · ' + next : ' · ' + t('no_more'))) + '">' + ICON.chevR + '</button>' +
      '<div class="cal" id="cal" role="dialog" aria-label="' + esc(t('pick_date')) + '" hidden></div></div>' +
      '<div class="seg" role="group" aria-label="' + esc(t('lang_label')) + '">' +
      '<button type="button" data-act="lang" data-l="zh" aria-pressed="' + (lang === 'zh') + '">中</button>' +
      '<button type="button" data-act="lang" data-l="en" aria-pressed="' + (lang === 'en') + '">EN</button></div>' +
      '<button class="ibtn" type="button" data-act="theme" aria-label="' + esc(t('theme_' + theme)) + '" title="' + esc(t('theme_' + theme)) + '">' + ICON['th_' + theme] + '</button>' +
      '</div></div>';
    $('#foot').innerHTML = '<span>' + esc(t('foot_ai')) + '</span><button type="button" data-act="cal">' + esc(t('foot_past')) + '</button>';
  }
  var calMonth = null;
  function renderCal() {
    var ds = dates();
    if (!calMonth) calMonth = (DATE || ds[ds.length - 1] || '').slice(0, 7);
    var y = +calMonth.slice(0, 4), m = +calMonth.slice(5, 7);
    var first = new Date(y, m - 1, 1), days = new Date(y, m, 0).getDate();
    var lead = (first.getDay() + 6) % 7;   // week starts on Monday
    var minM = (ds[0] || calMonth).slice(0, 7), maxM = (ds[ds.length - 1] || calMonth).slice(0, 7);
    var title = lang === 'en' ? first.toLocaleString('en', { month: 'long', year: 'numeric' }) : y + ' 年 ' + m + ' 月';
    var wds = t('wd_s'), h = '';
    for (var k = 1; k <= 7; k++) h += '<span class="dw">' + wds[k % 7] + '</span>';
    for (var b = 0; b < lead; b++) h += '<span></span>';
    for (var d = 1; d <= days; d++) {
      var iso = y + '-' + pad2(m) + '-' + pad2(d);
      if (ds.indexOf(iso) >= 0) {
        h += '<button type="button" data-act="pickdate" data-date="' + iso + '"' + (iso === DATE ? ' aria-current="date"' : '') + ' aria-label="' + iso + '">' + d + '</button>';
      } else {
        h += '<span class="d" aria-hidden="true">' + d + '</span>';
      }
    }
    $('#cal').innerHTML = '<div class="cal-h"><button class="ibtn" type="button" data-act="calm" data-d="-1"' + (calMonth <= minM ? ' disabled' : '') + ' aria-label="' + esc(t('cal_prev')) + '">' + ICON.chevL + '</button>' +
      '<span>' + esc(title) + '</span><button class="ibtn" type="button" data-act="calm" data-d="1"' + (calMonth >= maxM ? ' disabled' : '') + ' aria-label="' + esc(t('cal_next')) + '">' + ICON.chevR + '</button></div>' +
      '<div class="cal-g">' + h + '</div><p class="cal-f">' + esc(t('cal_count', { n: ds.length, d: ds[ds.length - 1] || '' })) + '</p>';
  }
  function openCal() {
    var c = $('#cal'); if (!c) return;
    calMonth = null; renderCal(); c.hidden = false;
    $('.dbtn').setAttribute('aria-expanded', 'true');
    var cur = $('[aria-current="date"]', c) || $('button[data-act="pickdate"]', c);
    if (cur) cur.focus();
  }
  function closeCal() {
    var c = $('#cal'); if (!c || c.hidden) return;
    c.hidden = true; $('.dbtn').setAttribute('aria-expanded', 'false');
  }

  /* ===================== text helpers ===================== */
  function citeTag(id) { return id ? '<sup class="cite" data-s="' + esc(id) + '"><a href="#src-' + esc(id) + '">[?]</a></sup>' : ''; }
  function cites(ids) { return (ids || []).filter(Boolean).map(citeTag).join(''); }
  function rich(s) {
    var h = esc(s);
    h = h.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
    if (lang === 'zh') h = h.replace(/（([A-Za-z][^（）]{0,60})）/g, '<span class="gloss">（$1）</span>');
    return h.replace(/\[\^(s\d+)\]/g, function (m, id) { return citeTag(id); });
  }
  function paras(arr) { return (arr || []).map(function (p) { return '<p>' + rich(p) + '</p>'; }).join(''); }
  function kindLabel(k) { return t('kind_' + k); }
  function badges(st) {
    var s = st.status || 'reported';
    return '<span class="badge ' + esc(s) + '">' + esc(t('status_' + s)) + '</span><span class="badge reg">' + esc(t('region_' + (st.region === 'cn' ? 'cn' : 'intl'))) + '</span>';
  }
  function spectrum(cov, inBtn) {
    if (!cov) return '';
    var z = cov.zh.length, e = cov.en.length, so = cov.social.length;
    if (!z && !e && !so) return '';
    var lines = [t('spec_tip'), t('spec_zh') + '：' + (cov.zh.join('、') || '—'), t('spec_en') + '：' + (cov.en.join('、') || '—')];
    if (so) lines.push(t('spec_so') + '：' + cov.social.join('、'));
    return '<span class="spec"' + (inBtn ? '' : ' tabindex="0"') + ' data-tip="' + esc(lines.join('\n')) + '">' +
      '<span class="spec-bar" aria-hidden="true">' + (z ? '<i class="zh" style="flex:' + z + '"></i>' : '') + (e ? '<i class="en" style="flex:' + e + '"></i>' : '') + (so ? '<i class="so" style="flex:' + so + '"></i>' : '') + '</span>' +
      '<span>' + esc(t('spec_n', { zh: z, en: e }) + (so ? t('spec_s', { so: so }) : '')) + '</span></span>';
  }
  function pic(im, st) {
    if (!im) return '<div class="pic ph-only" aria-hidden="true"><span>' + esc(kindLabel(st.kind)) + ' · ' + esc(String(pick(st, 'title')).slice(0, 16)) + '</span></div>';
    return '<div class="pic"><img src="' + esc(asset(im.src)) + '" alt="' + esc(pick(im, 'alt')) + '" loading="lazy" decoding="async" width="' + (im.w || 1400) + '" height="' + (im.h || 788) + '"></div>';
  }
  function head(key, aside) {
    return '<div class="sec-h"><span class="k">' + esc(t('k_' + key)) + '</span><h2>' + esc(t('sec_' + key)) + '</h2>' + (aside ? '<span class="aside">' + esc(aside) + '</span>' : '') + '</div>';
  }
  function whyBox(st) { var w = st['why_' + lang] || st.why_zh; return w && w.length ? '<div class="why"><span class="k">' + esc(t('why')) + '</span>' + paras(w) + '</div>' : ''; }
  function actions(st, extra) {
    var a = '';
    if (st.listen != null) a += '<button class="btn sm" type="button" data-act="listen" data-t="' + st.listen + '">' + ICON.headph + esc(t('listen_seg')) + '<span class="t">' + fmtTime(st.listen) + '</span></button>';
    if (st.watch) a += '<button class="btn sm" type="button" data-act="watch" data-scene="' + st.watch.scene + '">' + ICON.film + esc(t('watch_seg')) + '<span class="t">' + fmtTime(st.watch.t) + '</span></button>';
    else if (st.kind === 'headline') a += '<span class="btn sm" aria-disabled="true" style="opacity:.5;cursor:default">' + ICON.film + esc(t('watch_seg')) + '<span class="t">' + esc(t('watch_none')) + '</span></span>';
    return a || extra ? '<div class="acts">' + a + (extra || '') + '</div>' : '';
  }
  function numbersGrid(nums) {
    if (!nums || !nums.length) return '';
    return '<div class="kn">' + nums.map(function (n) {
      var v = lang === 'en' && n.value_en ? n.value_en : n.value;
      return '<div><b>' + esc(v) + '</b><span>' + esc(pick(n, 'label')) + citeTag(n.cite) + '</span></div>';
    }).join('') + '</div>';
  }

  /* ===================== sections ===================== */
  function secCard() {
    var c = ISSUE.card, d = ISSUE.date, term = c.term || {};
    var pod = ISSUE.media.podcast, vid = ISSUE.media.video;
    var mins = Math.round((pod && pod.duration || 0) / 60), secs = Math.round(vid && vid.duration || 0);
    var im = c.image;
    return '<section class="sec" id="sec-card"><div class="hero rv">' +
      '<div class="hero-txt"><p class="hero-over">' + esc(t('over')) + '</p>' +
      '<div class="hero-date"><span class="d">' + esc(d.slice(5).replace('-', '.')) + '</span><span class="w"><b>' + esc(pick(ISSUE, 'weekday')) + '</b>' + esc(d.slice(0, 4)) + '</span></div>' +
      '<p class="three-h">' + esc(t('three')) + '</p><ol class="three">' + c.headlines.map(function (h, i) {
        return '<li><button type="button" data-act="go" data-id="' + esc(h.ref) + '"><span class="n">0' + (i + 1) + '</span><span class="tx">' + esc(h[lang] || h.zh) + '</span></button></li>';
      }).join('') + '</ol>' +
      '<button class="termchip" type="button" data-act="go" data-id="term"><span class="k">' + esc(t('term_k')) + '</span><b>' + esc(lang === 'en' ? term.en : term.zh) + '</b><i>' + esc(lang === 'en' ? term.zh : term.en) + '</i></button>' +
      '<div class="hero-acts"><button class="btn pri" type="button" data-act="listen" data-t="">' + ICON.headph + esc(t('listen_n', { n: mins })) + '</button>' +
      '<button class="btn" type="button" data-act="watch" data-scene="0">' + ICON.film + esc(t('watch_n', { n: secs })) + '</button></div></div>' +
      '<figure class="hero-fig">' + (im ? '<img src="' + esc(asset(im.src)) + '" alt="' + esc(pick(im, 'alt')) + '" width="' + im.w + '" height="' + im.h + '" fetchpriority="high">' : '') +
      '<div class="hud"><i></i><i></i><i></i><i></i></div>' + (im ? '<figcaption class="figcap">' + esc(t('ai_img')) + '</figcaption>' : '') + '</figure>' +
      '</div></section>';
  }
  function secNumbers() {
    var N = ISSUE.numbers || [];
    if (!N.length) return '';
    return '<section class="sec" id="sec-numbers">' + head('numbers') +
      '<div class="console nums-wrap rv"><div class="ph"><span class="dot"></span>' + esc(t('numbers_ph')) + '<span class="r">' + esc(t('numbers_hint')) + '</span></div>' +
      '<div class="nums" style="--n:' + N.length + '">' + N.map(function (n, i) {
        var L = n[lang] || n.zh, st = S(n.story) || {};
        var sym = function (s, cls) { return s ? '<span class="' + (/[㐀-鿿]/.test(s) || cls === 'suf' ? cls : 'sym') + '">' + esc(s) + '</span>' : ''; };
        return '<div class="numt rv ' + (n.dir || '') + '" style="--d:' + (i * 0.08).toFixed(2) + 's">' +
          '<button class="cover" type="button" data-act="go" data-id="' + esc(n.story) + '" aria-label="' + esc(pick(n, 'label')) + '"></button>' +
          '<span class="tg">' + esc(kindLabel(st.kind) + ' · ' + t('status_' + (st.status || 'reported'))) + '</span>' +
          '<span class="v">' + (n.dir ? ICON[n.dir] : '') + '<span class="vg">' + sym(L.pre, 'pre') + '<span class="cnt" data-to="' + L.to + '" data-dec="' + (L.dec || 0) + '" data-comma="' + (L.comma ? 1 : 0) + '">' + fmtN(L.to, L.dec, L.comma) + '</span>' + sym(L.suf, 'suf') + '</span></span>' +
          '<span class="l">' + esc(pick(n, 'label')) + cites(n.cite) + '</span><span class="s">' + esc(pick(n, 'sub')) + '</span>' + ICON.go + '</div>';
      }).join('') + '</div></div></section>';
  }
  function secMedia() {
    var pod = ISSUE.media.podcast, vid = ISSUE.media.video;
    var mins = Math.round((pod && pod.duration || 0) / 60), secs = Math.round(vid && vid.duration || 0);
    return '<section class="sec" id="sec-media"><div id="media-head">' + head('media', t('media_aside', { v: secs, p: mins })) + '</div>' +
      '<div class="console media-wrap rv" data-tab="' + UI.media + '">' +
      '<div class="mtabs" role="tablist" id="mtabs">' + mtabs(secs, mins) + '</div>' +
      '<div class="media"><div class="pane pane-watch"><div id="video-root"></div></div><div class="pane pane-listen"><div id="pod-root"></div></div></div></div></section>';
  }
  function mtabs(secs, mins) {
    return '<button role="tab" type="button" data-act="mtab" data-tab="watch" aria-selected="' + (UI.media === 'watch') + '">' + esc(t('m_watch')) + '<span class="t">' + secs + 's</span></button>' +
      '<button role="tab" type="button" data-act="mtab" data-tab="listen" aria-selected="' + (UI.media === 'listen') + '">' + esc(t('m_listen')) + '<span class="t">' + mins + ' min</span></button>';
  }
  function chartBody(cid) {
    var c = CH(cid); if (!c) return '';
    var inner;
    if (c.type === 'timeline') {
      inner = '<div class="tl" data-tl><div class="tl-line"><i></i></div><ol>' + c.items.map(function (x, k) {
        var cls = x.future ? 'future' : (x.today ? 'today' : 'past');
        return '<li class="' + cls + '" style="--k:' + k + '"><span class="dt"></span><span class="w">' + esc(pick(x, 'when')) + '</span><span class="x">' + esc(pick(x, 'text')) + citeTag(x.cite) + '</span></li>';
      }).join('') + '</ol></div>';
    } else {
      inner = '<div class="chart" data-chart="' + esc(cid) + '" style="height:' + chartH(c) + 'px" role="img" aria-label="' + esc(pick(c, 'title')) + '"></div>';
    }
    var note = pick(c, 'note');
    return inner + '<p class="cnote">' + (note ? esc(note) + (c.note_cite ? citeTag(c.note_cite) : '') + ' ' : '') + '<b>' + esc(t('chart_src')) + '</b> ' + cites(c.cites) + '</p>';
  }
  function chartH(c) {
    var narrow = window.innerWidth < 640;
    if (c.type === 'dumbbell') return 270;
    if (c.type === 'graph') return narrow ? 300 : 330;
    if (c.type === 'steps') return 180;
    if (c.type === 'bars') return c.compact ? 140 : Math.max(200, c.items.length * 34 + 20);
    return 280;
  }
  function chartPanel(st) {
    var ids = (st.charts || []).filter(CH);
    if (!ids.length) return '';
    var k0 = UI.ctab[st.id] || 0;
    var tabs = ids.length > 1 ? '<div class="ctabs" role="tablist">' + ids.map(function (c, k) {
      var cc = CH(c), lbl = cc.type === 'timeline' ? t('c_timeline') : cc.type === 'graph' ? t('c_graph') : pick(cc, 'title');
      return '<button role="tab" type="button" aria-selected="' + (k === k0) + '" data-act="ctab" data-story="' + esc(st.id) + '" data-k="' + k + '">' + esc(lbl) + '</button>';
    }).join('') + '</div>' : '';
    return '<div class="console cpanel" id="cp-' + esc(st.id) + '"><div class="ph"><span class="dot"></span><b class="ct">' + esc(pick(CH(ids[k0]), 'title')) + '</b>' + tabs + '</div>' +
      ids.map(function (c, k) { return '<div class="cbody" data-k="' + k + '"' + (k === k0 ? '' : ' hidden') + '>' + chartBody(c) + '</div>'; }).join('') + '</div>';
  }
  function secHeadlines() {
    var ids = (ISSUE.order.headline || []).filter(S);
    if (!ids.length) return '';
    if (UI.hl >= ids.length) UI.hl = 0;
    return '<section class="sec" id="sec-headline">' + head('headline') + '<div class="stage-wrap rv">' +
      '<div class="htabs" role="tablist" aria-label="' + esc(t('sec_headline')) + '" aria-orientation="vertical">' + ids.map(function (id, i) {
        var st = S(id), on = i === UI.hl;
        return '<button class="htab" role="tab" type="button" id="ht-' + i + '" aria-controls="sp-' + i + '" aria-selected="' + on + '" tabindex="' + (on ? 0 : -1) + '" data-act="htab" data-i="' + i + '">' +
          '<span class="i">0' + (i + 1) + ' · ' + esc(t('status_' + st.status)) + '</span><span class="t">' + esc(pick(st, 'title')) + '</span>' + spectrum(st.coverage, true) + '<span class="bar"></span></button>';
      }).join('') + '<p class="hint">' + esc(t(HOVER() ? 'hover_hint' : 'swipe_hint')) + '</p></div>' +
      '<div class="stage" id="stage">' + ids.map(function (id, i) {
        var st = S(id), more = !!UI.more[id];
        return '<div class="spanel" role="tabpanel" id="sp-' + i + '" aria-labelledby="ht-' + i + '"' + (i === UI.hl ? '' : ' hidden') + '>' +
          '<div class="scol">' + pic(st.image, st) + '<div class="meta-row">' + badges(st) + spectrum(st.coverage) + '</div>' +
          '<h3 class="stitle">' + esc(pick(st, 'title')) + '</h3>' +
          '<ol class="lead">' + (st['lead_' + lang] || st.lead_zh).map(function (s) { return '<li>' + rich(s) + '</li>'; }).join('') + '</ol>' +
          '<button class="linkbtn" type="button" data-act="more" data-id="' + esc(id) + '" aria-expanded="' + more + '" aria-controls="body-' + esc(id) + '">' + esc(t(more ? 'read_less' : 'read_more')) + '</button>' +
          '<div class="body" id="body-' + esc(id) + '"' + (more ? '' : ' hidden') + '>' + paras(st['body_' + lang]) + '</div></div>' +
          '<div class="scol">' + chartPanel(st) + whyBox(st) + actions(st) + '<p class="srcline">' + esc(t('sources_of')) + cites(st.sources) + '</p></div></div>';
      }).join('') + '</div></div></section>';
  }
  function secBriefs() {
    var ids = (ISSUE.order.brief || []).filter(S);
    if (!ids.length) return '';
    return '<section class="sec" id="sec-brief">' + head('brief', t('brief_hint')) +
      '<div class="briefs rv' + (UI.brief ? ' has-open' : '') + '" id="briefs">' + ids.map(function (id, i) {
        var st = S(id), on = UI.brief === id;
        return '<article class="bcard' + (on ? ' open' : '') + '" id="b-' + esc(id) + '" style="--d:' + (i * 0.08) + 's">' +
          '<button class="bhead" type="button" data-act="bopen" data-id="' + esc(id) + '" aria-expanded="' + on + '" aria-controls="bb-' + esc(id) + '">' + pic(st.image, st) +
          '<span class="bmeta meta-row">' + badges(st) + spectrum(st.coverage, true) + '</span>' +
          '<h3>' + esc(pick(st, 'title')) + '</h3><span class="bsum">' + esc(pick(st, 'summary')) + '</span>' +
          '<span class="bmore">' + ICON.plus + '<span class="lb">' + esc(t(on ? 'close' : 'open')) + '</span></span></button>' +
          '<div class="bbody" id="bb-' + esc(id) + '"><div class="body">' + paras(st['body_' + lang]) + '</div>' + numbersGrid(st.numbers) + whyBox(st) + actions(st) +
          '<p class="srcline" style="margin-top:10px">' + esc(t('sources_of')) + cites(st.sources) + '</p></div></article>';
      }).join('') + '</div></section>';
  }
  function secFlash() {
    var ids = (ISSUE.order.flash || []).filter(S);
    if (!ids.length) return '';
    var fc = ISSUE.flash_chart && CH(ISSUE.flash_chart);
    return '<section class="sec" id="sec-flash">' + head('flash') + '<div class="flash-wrap rv"><ol class="flist">' + ids.map(function (id, i) {
      var st = S(id), on = UI.flash === id;
      return '<li class="frow' + (on ? ' open' : '') + '" id="f-' + esc(id) + '"><button type="button" data-act="fopen" data-id="' + esc(id) + '" aria-expanded="' + on + '">' +
        '<span class="i">0' + (i + 1) + '</span><span class="ft">' + esc(pick(st, 'title')) + '</span>' + spectrum(st.coverage, true) + ICON.chevD + '</button>' +
        '<div class="fx"><div class="meta-row" style="margin-bottom:8px">' + badges(st) + '</div>' + (st['lead_' + lang] || []).slice(0, 2).map(function (s) { return '<p>' + rich(s) + '</p>'; }).join('') + actions(st) + '</div></li>';
    }).join('') + '</ol>' +
      (fc ? '<div class="console"><div class="ph"><span class="dot"></span><b>' + esc(pick(fc, 'title')) + '</b></div>' + chartBody(ISSUE.flash_chart) + '</div>' : '') + '</div></section>';
  }
  var PER = 6;
  function secWatch() {
    var W = ISSUE.watch || [];
    if (!W.length) return '';
    return '<section class="sec" id="sec-watch">' + head('watch', t('watch_hint')) + '<div class="console board rv"><div class="ph"><span class="dot"></span>' + esc(t('watch_ph')) +
      '<span class="legend">' + ['rumor', 'teaser', 'scheduled', 'reported'].map(function (s) { return '<span class="st ' + s + '">' + esc(t('w_' + s)) + '</span>'; }).join('') + '</span></div>' +
      '<div class="brows" id="brows">' + boardHTML() + '</div>' + (W.length > PER ? '<div class="bpg" id="bpg"></div>' : '') + '</div></section>';
  }
  function boardHTML() {
    return (ISSUE.watch || []).map(function (w, k) {
      var st = S(w.story), det = st && st.kind === 'teaser', open = !!UI.wdet[k], pg = Math.floor(k / PER);
      var btn = det ? '<button class="rf" type="button" data-act="wdet" data-k="' + k + '" aria-expanded="' + open + '" aria-controls="wd-' + k + '">' + esc(t(open ? 'w_less' : 'w_more')) + '</button>'
        : (st ? '<button class="rf" type="button" data-act="go" data-id="' + esc(w.story) + '">' + esc(kindLabel(st.kind)) + ' →</button>' : '');
      return '<div class="brow" data-pg="' + pg + '" data-story="' + esc(w.story) + '" style="--k:' + (k % PER) + '"><span class="st ' + esc(w.status) + '">' + esc(t('w_' + w.status)) + '</span>' +
        '<span class="wn">' + esc(pick(w, 'when')) + '</span><span class="tx">' + esc(pick(w, 'text')) + cites(w.cite) + '</span>' + btn + '</div>' +
        (det ? '<div class="bdet" id="wd-' + k + '" data-pg="' + pg + '" data-k="' + k + '">' + paras(st['body_' + lang]) + whyBox(st) + actions(st) + '</div>' : '');
    }).join('');
  }
  function renderBoard(anim) {
    var W = ISSUE.watch || [], el = $('#brows');
    if (!el) return;
    var pages = Math.ceil(W.length / PER);
    if (UI.page >= pages) UI.page = 0;
    $$('.brow', el).forEach(function (r) { r.hidden = +r.getAttribute('data-pg') !== UI.page; });
    $$('.bdet', el).forEach(function (d) {
      var k = +d.getAttribute('data-k');
      d.hidden = +d.getAttribute('data-pg') !== UI.page || !UI.wdet[k];
      var b = $('[data-act="wdet"][data-k="' + k + '"]', el);
      if (b) { b.setAttribute('aria-expanded', !!UI.wdet[k]); b.textContent = t(UI.wdet[k] ? 'w_less' : 'w_more'); }
    });
    if (anim && !RM()) { el.classList.remove('enter'); void el.offsetWidth; el.classList.add('enter'); }
    var pg = $('#bpg');
    if (pg) {
      var h = '<span style="margin-right:auto">' + esc(t('page', { p: UI.page + 1, n: pages })) + '</span>' +
        '<button type="button" data-act="wpage" data-p="' + (UI.page - 1) + '"' + (UI.page ? '' : ' disabled') + ' aria-label="' + esc(t('prev_page')) + '">‹</button>';
      for (var p = 0; p < pages; p++) h += '<button type="button" data-act="wpage" data-p="' + p + '"' + (p === UI.page ? ' aria-current="page"' : '') + '>' + (p + 1) + '</button>';
      h += '<button type="button" data-act="wpage" data-p="' + (UI.page + 1) + '"' + (UI.page < pages - 1 ? '' : ' disabled') + ' aria-label="' + esc(t('next_page')) + '">›</button>';
      pg.innerHTML = h;
    }
  }
  function secPairs() {
    var P = ISSUE.pairs || [];
    if (!P.length) return '';
    if (UI.pair >= P.length) UI.pair = 0;
    var conn = '<svg class="cx-h" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path class="flow" d="M0 44 C 30 44, 70 44, 100 44" vector-effect="non-scaling-stroke"/><path class="flow back" d="M0 56 C 30 56, 70 56, 100 56" vector-effect="non-scaling-stroke"/></svg>' +
      '<svg class="cx-v" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path class="flow" d="M46 0 L46 100" vector-effect="non-scaling-stroke"/><path class="flow back" d="M54 0 L54 100" vector-effect="non-scaling-stroke"/></svg>';
    var side = function (st, r, p) {
      var chart = r === 'cn' && p.chart_cn && CH(p.chart_cn) ? '<div class="console"><div class="ph"><span class="dot"></span><b>' + esc(pick(CH(p.chart_cn), 'title')) + '</b></div>' + chartBody(p.chart_cn) + '</div>' : '';
      var isBrief = st.kind === 'brief', open = !!UI.pexp[st.id];
      var lead = (st['lead_' + lang] || [])[0] || pick(st, 'summary');
      var btn = isBrief ? '<button class="btn sm" type="button" data-act="go" data-id="' + esc(st.id) + '">' + esc(t('to_brief')) + ' →</button>'
        : '<button class="btn sm" type="button" data-act="pexp" data-id="' + esc(st.id) + '" aria-expanded="' + open + '">' + esc(t(open ? 'read_less' : 'read_more')) + '</button>';
      return '<div class="side ' + r + '"><span class="rg">' + esc(t(r === 'cn' ? 'pair_cn' : 'pair_intl')) + '</span><h3>' + esc(pick(st, 'title')) + '</h3>' +
        '<p class="sm">' + rich(lead) + '</p>' + numbersGrid((st.numbers || []).slice(0, 2)) + chart +
        (isBrief ? '' : '<div class="xbody" id="x-' + esc(st.id) + '"' + (open ? '' : ' hidden') + '><div class="body">' + paras((st['body_' + lang] || []).slice(0)) + '</div><div style="margin-top:12px">' + whyBox(st) + '</div>' + actions(st) + '</div>') +
        '<div class="acts">' + btn + '</div></div>';
    };
    return '<section class="sec" id="sec-pairs">' + head('pairs') + '<div class="rv"><div class="ptabs" role="tablist">' + P.map(function (p, i) {
      return '<button role="tab" type="button" aria-selected="' + (i === UI.pair) + '" aria-controls="pair-' + i + '" data-act="ptab" data-i="' + i + '">' + esc(pick(p, 'label')) + '</button>';
    }).join('') + '</div>' + P.map(function (p, i) {
      var a = S(p.intl), b = S(p.cn);
      if (!a || !b) return '';
      return '<div class="pair" id="pair-' + i + '" role="tabpanel"' + (i === UI.pair ? '' : ' hidden') + '>' + side(a, 'intl', p) +
        '<div class="mid">' + conn + '<div class="rel"><span class="k">' + esc(t('pair_rel')) + '</span>' + rich(pick(p, 'note')) + '</div></div>' + side(b, 'cn', p) + '</div>';
    }).join('') + '</div></section>';
  }
  function secTerm() {
    var st = S('term'), c = ISSUE.card.term;
    if (!st || !c) return '';
    var zh = lang === 'zh';
    var front = zh ? { w: c.zh, lat: false, ex: c.explain_zh } : { w: c.en, lat: true, ex: c.explain_en };
    var back = zh ? { w: c.en, lat: true } : { w: c.zh, lat: false };
    var art = st.image ? pic(st.image, st) : '<div class="pic ph-only" aria-hidden="true"><span>' + esc(c.zh + ' · ' + c.en) + '</span></div>';
    return '<section class="sec" id="sec-term">' + head('term') + '<div class="flip rv' + (UI.flip ? ' on' : '') + '" id="flip"><div class="flip-in">' +
      '<div class="face front"' + (UI.flip ? ' inert' : '') + '><div class="art">' + art + '</div><div class="tx"><span class="k">' + esc(t('term_k')) + '</span>' +
      '<span class="w' + (front.lat ? ' lat' : '') + '">' + esc(front.w) + '</span><p class="ex">' + esc(front.ex) + '</p>' +
      '<button class="btn" type="button" data-act="flip" aria-pressed="' + UI.flip + '">' + ICON.flip + esc(t('flip')) + '</button></div></div>' +
      '<div class="face back"' + (UI.flip ? '' : ' inert') + '><div class="tx"><span class="k">' + esc(t('term_k2')) + '</span>' +
      '<span class="w' + (back.lat ? ' lat' : '') + '">' + esc(back.w) + '</span><h4>' + esc(t('term_usage')) + '</h4>' + paras(st['body_' + lang]) +
      '<h4>' + esc(t('term_note')) + '</h4>' + paras(st['why_' + lang]) +
      actions(st, '<button class="btn sm" type="button" data-act="flip" aria-pressed="' + UI.flip + '">' + ICON.flip + esc(t('flip_back')) + '</button>') + '</div></div>' +
      '</div></div></section>';
  }
  function secSources() {
    return '<section class="sec" id="sec-sources"><div class="srcbox rv' + (UI.srcOpen ? ' open' : '') + '" id="srcbox">' +
      '<button class="srct" type="button" data-act="srctoggle" aria-expanded="' + UI.srcOpen + '" aria-controls="srcin"><b>' + esc(t('src_title')) + '</b><span id="srcsum"></span>' + ICON.chevD + '</button>' +
      '<div class="srcin" id="srcin"><ol class="srcl" id="srcl"></ol><button class="btn sm srcall" type="button" data-act="srcall" id="srcall"></button></div></div></section>';
  }

  /* ===================== citations: number by first appearance, count uses ===================== */
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
    ISSUE.sources.forEach(function (s) { if (!order[s.id]) order[s.id] = ++n; });   // never cited in text: listed after the cited ones
    var list = ISSUE.sources.slice().sort(function (a, b) { return order[a.id] - order[b.id]; });
    CITE = { order: order, count: count, list: list };
  }
  function topIds() {
    return CITE.list.slice().sort(function (a, b) { return (CITE.count[b.id] || 0) - (CITE.count[a.id] || 0) || CITE.order[a.id] - CITE.order[b.id]; })
      .slice(0, 5).map(function (s) { return s.id; });
  }
  function renderSources() {
    var ul = $('#srcl'); if (!ul) return;
    var all = CITE.list, show = UI.srcAll ? all : topIds().map(srcById);
    ul.innerHTML = show.map(function (s) {
      return '<li id="src-' + esc(s.id) + '"><span class="n">[' + CITE.order[s.id] + ']</span><span><span class="m">' + esc(s.name) + '</span> · ' +
        '<a href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer">' + esc(s.title || host(s.url) || s.url) + '</a> <span class="d">' + esc(s.date) + '</span></span></li>';
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
    scrollToEl(li, 90);
    li.classList.remove('hit'); void li.offsetWidth; li.classList.add('hit');
  }
  function setSrcOpen(on) {
    UI.srcOpen = on;
    var box = $('#srcbox'); if (!box) return;
    box.classList.toggle('open', on);
    $('.srct', box).setAttribute('aria-expanded', on);
  }

  /* ===================== charts (ECharts, loaded on demand) ===================== */
  var C = { ink: '#E2EFEC', ink2: '#AFC7C3', ink3: '#8AA6A2', line: 'rgba(120,214,204,.34)', grid: 'rgba(120,214,204,.09)', accent: '#5FD3C7', warm: '#F2A65A', blue: '#A9C0FF', muted: '#46655F', bg: '#0B1618', pale: '#D9E4E2' };
  var MONO = 'ui-monospace, "SF Mono", Menlo, Consolas, monospace';
  var SANS = '-apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif';
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
  function srcLine(id) {
    var s = id && srcById(id);
    return s ? esc(t('chart_src')) + ' [' + (CITE.order[id] || '?') + '] ' + esc(s.name) : '';
  }
  function base(o) {
    o.animation = !RM();
    o.backgroundColor = 'transparent';
    o.textStyle = { fontFamily: SANS, color: C.ink };
    o.tooltip = Object.assign({ backgroundColor: '#0F1E21', borderColor: C.line, borderWidth: 1, padding: [7, 10], textStyle: { color: C.ink, fontSize: 12, fontFamily: SANS }, extraCssText: 'border-radius:8px;box-shadow:0 12px 30px rgba(0,0,0,.45);max-width:280px;white-space:normal;' }, o.tooltip || {});
    return o;
  }
  function unitFmt(v, unit, en, full) {
    var n = fmtNum(v);
    if (en) return unit === '$B' ? '$' + n + 'B' : unit === '$T' ? '$' + n + 'T' : n + unit;
    return full ? n + ' ' + unit : n;
  }
  function optDumbbell(c, el) {
    var en = lang === 'en', H = 92, top = 22, gap = 22, narrow = el.offsetWidth < 420;
    var grid = [], xAxis = [], yAxis = [], series = [];
    c.rows.forEach(function (r, i) {
      var unit = en ? r.unit_en : r.unit_zh, k = r.points[0].v ? r.points[0].v_en / r.points[0].v : 1;
      var cat = pick(r, 'label'), V = function (p) { return en ? p.v_en : p.v; };
      var from = r.points.filter(function (p) { return p.role === 'from'; })[0], to = r.points.filter(function (p) { return p.role === 'to'; })[0];
      grid.push({ left: narrow ? 58 : 76, right: 26, top: top + i * (H + gap), height: H });
      var mx = +(r.max * (en ? k : 1)).toFixed(4), raw = mx / 3.2, mag = Math.pow(10, Math.floor(Math.log10(raw))), nr = raw / mag;
      xAxis.push({ gridIndex: i, type: 'value', min: 0, max: mx, interval: (nr < 1.5 ? 1 : nr < 3.5 ? 2.5 : nr < 7.5 ? 5 : 10) * mag,
        axisLabel: { color: C.ink3, fontFamily: MONO, fontSize: 10, showMaxLabel: false, formatter: function (v) { return unitFmt(v, unit, en, false); } },
        splitLine: { lineStyle: { color: C.grid } }, axisLine: { show: false }, axisTick: { show: false } });
      yAxis.push({ gridIndex: i, type: 'category', data: [cat], axisLabel: { color: C.ink, fontSize: 12.5, fontWeight: 600 }, axisLine: { lineStyle: { color: C.line } }, axisTick: { show: false } });
      var lo = V(from) < V(to) ? C.warm : C.accent, hi = V(from) < V(to) ? C.accent : C.warm;
      series.push({ type: 'line', xAxisIndex: i, yAxisIndex: i, silent: true, symbol: 'none', z: 1, data: [[V(from), cat], [V(to), cat]],
        lineStyle: { width: 7, cap: 'round', color: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: lo }, { offset: 1, color: hi }] } },
        animationDuration: 1100, animationEasing: 'cubicOut' });
      series.push({ type: 'scatter', xAxisIndex: i, yAxisIndex: i, z: 3, animationDelay: function (idx) { return 450 + idx * 220; },
        data: r.points.map(function (p) {
          var mark = p.role === 'mark', col = mark ? C.ink2 : (p.role === 'from' ? C.warm : C.accent);
          return { value: [V(p), cat], name: pick(p, 'label'), cite: p.cite, unit: unit, symbolSize: mark ? 12 : 18,
            itemStyle: { color: mark ? C.bg : col, borderColor: mark ? C.ink2 : C.bg, borderWidth: mark ? 1.5 : 2.5, borderType: mark ? 'dashed' : 'solid' },
            label: { show: true, position: p.role === 'from' ? 'top' : 'bottom', distance: 7, color: mark ? C.ink2 : C.ink, fontSize: 11, lineHeight: 15, align: 'center',
              formatter: pick(p, 'label') + '\n{v|' + unitFmt(V(p), unit, en, true) + '}', rich: { v: { fontFamily: MONO, fontWeight: 700, fontSize: 12, color: col } } } };
        }) });
    });
    return base({ grid: grid, xAxis: xAxis, yAxis: yAxis, series: series,
      tooltip: { trigger: 'item', formatter: function (p) { var d = p.data || {}; return '<b>' + esc(d.name) + '</b> ' + esc(unitFmt(d.value[0], d.unit, lang === 'en', true)) + '<br><span style="opacity:.8">' + srcLine(d.cite) + '</span>'; } } });
  }
  function optBars(c) {
    var items = c.items.slice().reverse(), max = Math.max.apply(null, c.items.map(function (x) { return x.v; }));
    var down = c.tone === 'down', hl = down ? C.warm : C.accent;
    return base({
      grid: { left: 6, right: 58, top: 4, bottom: 4, containLabel: true },
      xAxis: { type: 'value', max: max * 1.12, show: false },
      yAxis: { type: 'category', data: items.map(function (x) { return pick(x, 'label'); }), axisLabel: { color: C.ink, fontSize: 12 }, axisTick: { show: false }, axisLine: { lineStyle: { color: C.line } } },
      series: [{ type: 'bar', barWidth: '60%', cursor: 'pointer',
        data: items.map(function (x) { return { value: x.v, story: x.story, item: x, itemStyle: { color: x.hl ? hl : C.muted, borderRadius: [0, 3, 3, 0] } }; }),
        label: { show: true, position: 'right', fontFamily: MONO, fontSize: 11.5, fontWeight: 700, color: C.ink, formatter: function (p) { return (c.sign || '') + fmtNum(p.value) + c.unit; } },
        animationDuration: 1000, animationDelay: function (i) { return (items.length - i) * 70; } }],
      tooltip: { trigger: 'item', formatter: function (p) {
        var x = p.data.item, ex = pick(x, 'extra');
        return '<b>' + esc(pick(x, 'label')) + '</b> ' + (c.sign || '') + fmtNum(x.v) + c.unit + (ex ? '<br>' + esc(ex) + (x.extra_cite ? ' [' + (CITE.order[x.extra_cite] || '?') + ']' : '') : '') + '<br><span style="opacity:.8">' + srcLine(x.cite) + '</span>';
      } }
    });
  }
  function optSteps(c) {
    var en = lang === 'en', money = function (v) { return en ? '$' + v : v + ' ' + c.unit_zh; };
    var s = { type: 'line', step: 'middle', data: c.items.map(function (x) { return x.v; }), symbol: 'circle', symbolSize: 8,
      lineStyle: { color: C.accent, width: 2.5 }, itemStyle: { color: C.accent, borderColor: C.bg, borderWidth: 2 },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(95,211,199,.30)' }, { offset: 1, color: 'rgba(95,211,199,0)' }] } },
      label: { show: true, position: 'top', color: C.ink, fontFamily: MONO, fontWeight: 700, fontSize: 11, formatter: function (p) { return money(p.value); } },
      animationDuration: 1300 };
    if (c.base) s.markLine = { silent: true, symbol: 'none', data: [{ yAxis: c.base.v, label: { formatter: pick(c.base, 'label'), position: 'insideStartTop', color: C.warm, fontSize: 10.5 }, lineStyle: { color: C.warm, type: 'dashed', width: 1.4 } }] };
    return base({
      grid: { left: 6, right: 14, top: 26, bottom: 4, containLabel: true },
      xAxis: { type: 'category', data: c.items.map(function (x) { return pick(x, 'label'); }), axisLabel: { color: C.ink2, fontSize: 11 }, axisTick: { show: false }, axisLine: { lineStyle: { color: C.line } } },
      yAxis: { type: 'value', min: 0, max: 120, interval: 40, axisLabel: { color: C.ink3, fontFamily: MONO, fontSize: 10, formatter: function (v) { return en ? '$' + v : v; } }, splitLine: { lineStyle: { color: C.grid } } },
      series: [s],
      tooltip: { trigger: 'axis', formatter: function (ps) { var p = ps[0]; return '<b>' + esc(p.name) + '</b> ' + money(p.value) + '<br><span style="opacity:.8">' + srcLine(c.items[p.dataIndex].cite) + '</span>'; } }
    });
  }
  function optGraph(c, el) {
    var narrow = el.offsetWidth < 520;
    var col = { core: C.accent, apple: C.pale, ali: C.warm, feat: C.blue, ghost: C.bg };
    return base({
      tooltip: { trigger: 'item', formatter: function (p) {
        if (p.dataType === 'edge') return esc(p.data.lbl) + '<br><span style="opacity:.8">' + srcLine(p.data.cite) + '</span>';
        return '<b>' + esc(p.data.lbl) + '</b>';
      } },
      series: [{ type: 'graph', layout: 'none', roam: false, left: narrow ? 50 : 76, right: narrow ? 50 : 76, top: 30, bottom: 34,
        edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 6,
        data: c.nodes.map(function (n) {
          var lb = n[lang] || n.zh, ghost = n.kind === 'ghost', core = n.kind === 'core';
          return { name: n.id, x: n.x, y: n.y, lbl: lb, symbolSize: core ? (narrow ? 38 : 48) : (narrow ? 16 : 21),
            itemStyle: { color: col[n.kind], borderColor: ghost ? C.ink3 : C.bg, borderWidth: ghost ? 1.5 : 2, borderType: ghost ? 'dashed' : 'solid', shadowBlur: core ? 22 : 0, shadowColor: 'rgba(95,211,199,.7)' },
            label: { show: true, formatter: lb, position: n.y < 30 ? 'top' : 'bottom', color: ghost ? C.ink3 : C.ink, fontSize: narrow ? 10.5 : 12, fontWeight: core ? 700 : 500 } };
        }),
        links: c.links.map(function (l) {
          return { source: l.s, target: l.t, lbl: l[lang] || l.zh, cite: l.cite,
            lineStyle: { type: l.dashed ? 'dashed' : 'solid', color: l.dashed ? C.ink3 : C.accent, opacity: l.dashed ? 0.7 : 0.55, width: 1.4, curveness: 0.1 } };
        }),
        edgeLabel: { show: !narrow, formatter: function (p) { return p.data.lbl; }, fontSize: 10, color: C.ink2 },
        emphasis: { focus: 'adjacency', lineStyle: { width: 2.6, opacity: 1 }, edgeLabel: { show: true } },
        animationDuration: 1200, animationEasing: 'cubicOut' }]
    });
  }
  function buildOption(c, el) {
    if (c.type === 'dumbbell') return optDumbbell(c, el);
    if (c.type === 'bars') return optBars(c);
    if (c.type === 'steps') return optSteps(c);
    if (c.type === 'graph') return optGraph(c, el);
    return null;
  }
  function initChart(el) {
    if (el._ec || !el.offsetWidth) return;
    withEC(function (echarts) {
      if (el._ec || !el.offsetWidth) return;
      var c = CH(el.getAttribute('data-chart'));
      var opt = c && buildOption(c, el);
      if (!opt) return;
      var inst = echarts.init(el, null, { renderer: 'canvas' });
      inst.setOption(opt);
      inst.on('click', function (p) { if (p.data && p.data.story) goStory(p.data.story); });
      el._ec = inst;
      CHARTS.push(inst);
    });
  }
  function disposeCharts() { CHARTS.forEach(function (c) { try { c.dispose(); } catch (e) { /* ignore */ } }); CHARTS = []; }

  /* ===================== podcast ===================== */
  function Pod(root, p) {
    var self = this;
    this.root = root; this.p = p; this.dur = p.duration || 0;
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
      new IntersectionObserver(function (es) { self.inView = es[0].isIntersecting; self.mini(); }).observe(root);
    }
  }
  Pod.prototype.build = function () {
    var self = this, p = this.p, D = this.dur || 1;
    var bars = (p.peaks || []).map(function (v) { return '<i style="height:' + Math.max(6, Math.round(v * 100)) + '%"></i>'; }).join('');
    var ticks = (p.chapters || []).slice(1).map(function (c) { return '<span class="tk" style="left:' + (c.start / D * 100).toFixed(2) + '%"></span>'; }).join('');
    this.root.innerHTML = '<div class="pod">' +
      '<div class="pod-top"><button class="pod-play" type="button" data-pod="toggle"></button><div class="pod-tt"><b>' + esc(pick(p, 'title')) + '</b><span class="pod-now"></span></div><span class="pod-ai">' + esc(t('pod_ai')) + '</span></div>' +
      '<div class="wave" role="slider" tabindex="0" aria-label="' + esc(t('pod_seek')) + '" aria-valuemin="0" aria-valuemax="' + Math.round(D) + '"><div class="bars">' + bars + '</div><div class="bars on">' + bars + '</div>' + ticks + '<span class="hd"></span></div>' +
      '<div class="pod-row"><span class="tm"></span><button type="button" data-pod="back" aria-label="' + esc(t('pod_back')) + '">−15</button><button type="button" data-pod="fwd" aria-label="' + esc(t('pod_fwd')) + '">+15</button><button type="button" data-pod="rate" aria-label="' + esc(t('pod_speed')) + '"></button></div>' +
      '<ol class="pod-ch" aria-label="' + esc(t('pod_ch')) + '">' + (p.chapters || []).map(function (c, i) {
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
  Pod.prototype.seek = function (s, keepPaused) {
    s = Math.max(0, Math.min(this.dur - 0.2, s || 0));
    if (this.a.readyState < 1) { this.pend = s; if (!keepPaused) { /* nothing loaded yet */ } this.sync(); try { this.a.currentTime = s; } catch (e) { /* set after metadata */ } return; }
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
      m.innerHTML = '<button class="pod-play" type="button" data-act="mini-toggle"></button><button class="mt" type="button" data-act="mini-go"></button><button class="ibtn" type="button" data-act="mini-close" aria-label="' + esc(t('mini_close')) + '">' + ICON.close + '</button>';
    }
    m.hidden = false;
    var ch = (this.p.chapters || [])[this.chapter()];
    var pb = $('.pod-play', m); pb.innerHTML = a.paused ? ICON.play : ICON.pause; pb.setAttribute('aria-label', t(a.paused ? 'pod_play' : 'pod_pause'));
    $('.mt', m).innerHTML = esc(ch ? pick(ch, 'title') : pick(this.p, 'title')) + '<span>' + fmtTime(this.cur()) + ' / ' + fmtTime(this.dur) + '</span>';
  };
  Pod.prototype.setLang = function () { this.build(); };

  /* ===================== media ===================== */
  function videoCtx() { return { lang: function () { return lang; }, t: t, pick: pick, asset: asset, normImage: normImage, host: host, store: store, go: function (id) { goStory(id); } }; }
  function mountMedia() {
    var v = ISSUE.media.video, p = ISSUE.media.podcast;
    if (v && v.v === 2 && window.FDVideo2) players.video = window.FDVideo2.mount($('#video-root'), v, videoCtx());
    else if (v && v.v !== 2 && window.FDVideo) players.video = window.FDVideo.mount($('#video-root'), v, videoCtx());
    if (p) players.podcast = new Pod($('#pod-root'), p);
    window.FD.players = players;
  }
  function setMediaTab(tab) {
    UI.media = tab;
    var w = $('.media-wrap'); if (!w) return;
    w.setAttribute('data-tab', tab);
    $$('#mtabs button').forEach(function (b) { b.setAttribute('aria-selected', b.getAttribute('data-tab') === tab); });
    if (tab === 'listen' && players.video && players.video.playing && window.innerWidth < 760) players.video.pause();
  }
  function watchScene(i) {
    var v = players.video; if (!v) return;
    setMediaTab('watch');
    scrollToEl($('#sec-media'));
    var sc = v.scenes[i] || v.scenes[0];
    v.seek(sc.start + 0.01);
    v.play();
  }
  function listen(tm) {
    var p = players.podcast; if (!p) return;
    if (tm === '' || tm == null) { p.toggle(); return; }
    p.playAt(+tm);
  }

  /* ===================== navigation inside the page ===================== */
  function scrollToEl(el, extra) {
    if (!el) return;
    var top = $('#top').offsetHeight;
    var y = el.getBoundingClientRect().top + window.pageYOffset - top - (extra == null ? 14 : extra);
    window.scrollTo({ top: Math.max(0, y), behavior: RM() ? 'auto' : 'smooth' });
  }
  function selectHeadline(i, focus) {
    var tabs = $$('.htab'), panels = $$('.spanel');
    if (!tabs[i]) return;
    var changed = UI.hl !== i;
    UI.hl = i;
    tabs.forEach(function (b, k) { b.setAttribute('aria-selected', k === i); b.tabIndex = k === i ? 0 : -1; });
    panels.forEach(function (p, k) {
      p.hidden = k !== i;
      if (k === i && changed && !RM()) { p.classList.remove('enter'); void p.offsetWidth; p.classList.add('enter'); }
    });
    if (focus) tabs[i].focus();
    observeNew();
  }
  function openBrief(id, force) {
    var card = document.getElementById('b-' + id); if (!card) return;
    var open = force ? true : !card.classList.contains('open');
    UI.brief = open ? id : null;
    $$('.bcard').forEach(function (c) {
      var on = c === card && open;
      c.classList.toggle('open', on);
      $('.bhead', c).setAttribute('aria-expanded', on);
      $('.lb', c).textContent = t(on ? 'close' : 'open');
    });
    $('#briefs').classList.toggle('has-open', open);
    if (open && window.innerWidth < 1024) {
      var strip = $('#briefs');
      strip.scrollTo({ left: card.offsetLeft - strip.offsetLeft - 16, behavior: RM() ? 'auto' : 'smooth' });
    }
  }
  function openFlash(id, force) {
    var row = document.getElementById('f-' + id); if (!row) return;
    var open = force ? true : !row.classList.contains('open');
    UI.flash = open ? id : null;
    $$('.frow').forEach(function (r) { var on = r === row && open; r.classList.toggle('open', on); $('button', r).setAttribute('aria-expanded', on); });
  }
  function selectPair(i) {
    UI.pair = i;
    $$('.ptabs button').forEach(function (b, k) { b.setAttribute('aria-selected', k === i); });
    $$('.pair').forEach(function (p, k) {
      p.hidden = k !== i;
      if (k === i && !RM()) { p.classList.remove('enter'); void p.offsetWidth; p.classList.add('enter'); }
    });
    observeNew();
  }
  function goStory(id) {
    var st = S(id); if (!st) return;
    hideTip();
    var k = st.kind;
    if (k === 'headline') { selectHeadline(ISSUE.order.headline.indexOf(id)); scrollToEl($('#sec-headline')); }
    else if (k === 'brief') { openBrief(id, true); scrollToEl($('#b-' + id)); }
    else if (k === 'flash') { openFlash(id, true); scrollToEl($('#f-' + id), 60); }
    else if (k === 'cn_intl') {
      var pi = (ISSUE.pairs || []).map(function (p) { return p.cn === id || p.intl === id; }).indexOf(true);
      if (pi >= 0) selectPair(pi);
      scrollToEl($('#sec-pairs'));
    } else if (k === 'teaser') {
      var W = ISSUE.watch || [], wi = W.map(function (w) { return w.story; }).indexOf(id);
      if (wi >= 0) { UI.page = Math.floor(wi / PER); UI.wdet[wi] = true; renderBoard(true); }
      scrollToEl($('#sec-watch'));
      $$('#brows .brow[data-story="' + id + '"]').forEach(function (r) { r.classList.add('hl'); setTimeout(function () { r.classList.remove('hl'); }, 2600); });
    } else if (k === 'term') { scrollToEl($('#sec-term')); }
  }

  /* ===================== tooltip (citations, coverage) ===================== */
  var tip = null, tipFor = null;
  function showTip(el) {
    var html;
    if (el.matches('sup.cite')) {
      var s = srcById(el.getAttribute('data-s')); if (!s) return;
      html = '<b>' + esc(s.name) + '</b> · ' + esc(s.title || host(s.url)) + (s.date ? ' <span style="opacity:.7">' + esc(s.date) + '</span>' : '') +
        (lastPointer === 'touch' ? '<br><button class="go" type="button" data-act="srcgo" data-s="' + esc(s.id) + '">' + esc(t('cite_go')) + '</button>' : '');
    } else {
      html = esc(el.getAttribute('data-tip')).replace(/\n/g, '<br>');
    }
    tip.innerHTML = html; tip.hidden = false; tipFor = el;
    var r = el.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight, vw = window.innerWidth;
    var left = Math.min(vw - w - 10, Math.max(10, r.left + r.width / 2 - w / 2));
    var top = r.bottom + 8;
    if (top + h > window.innerHeight - 8) top = r.top - h - 8;
    tip.style.left = left + 'px'; tip.style.top = Math.max(8, top) + 'px';
    $$('sup.cite a.on').forEach(function (a) { a.classList.remove('on'); });
    if (el.matches('sup.cite')) el.firstChild.classList.add('on');
  }
  function hideTip() {
    if (!tip || tip.hidden) return;
    tip.hidden = true; tipFor = null;
    $$('sup.cite a.on').forEach(function (a) { a.classList.remove('on'); });
  }

  /* ===================== reveal, count-up, lazy charts ===================== */
  function countUp(el) {
    var to = +el.getAttribute('data-to'), dec = +el.getAttribute('data-dec') || 0, comma = el.getAttribute('data-comma') === '1';
    if (RM()) { el.textContent = fmtN(to, dec, comma); return; }
    var t0 = performance.now(), D = 1500;
    var step = function (now) {
      var k = Math.min(1, (now - t0) / D), e = 1 - Math.pow(1 - k, 3);
      el.textContent = fmtN(to * e, dec, comma);
      if (k < 1) requestAnimationFrame(step);
    };
    el.textContent = fmtN(0, dec, comma);
    requestAnimationFrame(step);
  }
  function onSeen(el) {
    if (el.classList.contains('rv') && !el.classList.contains('in')) {
      el.classList.add('in');
      if (el.classList.contains('numt')) $$('.cnt', el).forEach(countUp);
    }
    if (el.hasAttribute('data-tl') && !el.classList.contains('go')) { void el.offsetWidth; el.classList.add('go'); }
    if (el.classList.contains('chart')) initChart(el);
  }
  function observeNew() {
    var els = $$('#c-main .rv:not(.in), #c-main [data-tl]:not(.go), #c-main .chart');
    if (!io) { els.forEach(onSeen); return; }
    els.forEach(function (el) { if (!el._obs) { el._obs = true; io.observe(el); } });
    // elements that were hidden (other tab) are observed already; when shown, the observer reports them
    $$('#c-main .chart').forEach(function (el) { if (!el._ec && el.offsetWidth && inViewport(el)) initChart(el); });
    $$('#c-main [data-tl]').forEach(function (el) { if (el.offsetWidth && inViewport(el) && !el.classList.contains('go')) onSeen(el); });
  }
  function inViewport(el) { var r = el.getBoundingClientRect(); return r.bottom > 0 && r.top < window.innerHeight; }

  /* ===================== render ===================== */
  function renderContent() {
    disposeCharts();
    if (io) setupIO();
    var keep = null;
    $$('#c-main > .sec').some(function (s) { var r = s.getBoundingClientRect(); if (r.bottom > 80) { keep = { id: s.id, y: r.top }; return true; } return false; });
    var html = secCard() + secNumbers() + (ISSUE.media ? '<div id="media-slot"></div>' : '') + secHeadlines() + secBriefs() + secFlash() + secWatch() + secPairs() + secTerm() + secSources();
    var cm = $('#c-main');
    var media = $('#sec-media');
    if (media) media.parentNode.removeChild(media);
    cm.innerHTML = html;
    var slot = $('#media-slot');
    if (slot) {
      if (media) {
        slot.parentNode.replaceChild(media, slot);
        $('#media-head').innerHTML = head('media', t('media_aside', { v: Math.round(ISSUE.media.video.duration), p: Math.round(ISSUE.media.podcast.duration / 60) }));
        $('#mtabs').innerHTML = mtabs(Math.round(ISSUE.media.video.duration), Math.round(ISSUE.media.podcast.duration / 60));
      } else {
        var tmp = document.createElement('div'); tmp.innerHTML = secMedia();
        slot.parentNode.replaceChild(tmp.firstChild, slot);
      }
    }
    renderBoard(false);
    numberCites();
    renderSources();
    if (keep) { var s = document.getElementById(keep.id); if (s) window.scrollTo(0, s.getBoundingClientRect().top + window.pageYOffset - keep.y); }
    // sections already on screen (e.g. after a language switch) show at once
    $$('#c-main .rv').forEach(function (el) { if (inViewport(el) && keep) el.classList.add('in'); });
    observeNew();
  }
  function setLang(l) {
    if (l === lang) return;
    lang = l; store.set('fd.lang', l);
    document.documentElement.lang = l === 'en' ? 'en' : 'zh-CN';
    document.title = t('brand') + ' · ' + DATE;
    renderTop();
    if (!ISSUE) return;
    renderContent();
    if (players.video) players.video.setLang();
    if (players.podcast) players.podcast.setLang();
    $('#mini').innerHTML = '';
    if (players.podcast) players.podcast.sync();
  }
  function applyTheme() {
    var d = document.documentElement;
    if (theme === 'auto') d.removeAttribute('data-theme'); else d.setAttribute('data-theme', theme);
  }

  /* ===================== events ===================== */
  var hoverT = 0, touchX = null, touchY = null;
  function setupIO() {
    if (!('IntersectionObserver' in window)) { document.documentElement.classList.add('no-io'); return; }
    if (io) io.disconnect();
    io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target;
        onSeen(el);
        if (el.classList.contains('rv') && !el.classList.contains('chart') && !el.hasAttribute('data-tl')) io.unobserve(el);
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });
  }
  function bindGlobal() {
    tip = $('#tip');
    document.addEventListener('pointerdown', function (e) { lastPointer = e.pointerType || 'mouse'; }, true);
    document.addEventListener('click', onClick);
    document.addEventListener('keydown', onKey);
    document.addEventListener('mouseover', function (e) {
      if (lastPointer === 'touch') return;
      var c = e.target.closest && e.target.closest('sup.cite, [data-tip]');
      if (c && c !== tipFor) showTip(c);
      var h = e.target.closest && e.target.closest('.htab');
      if (h && HOVER()) { clearTimeout(hoverT); hoverT = setTimeout(function () { selectHeadline(+h.getAttribute('data-i')); }, 140); }
    });
    document.addEventListener('mouseout', function (e) {
      var c = e.target.closest && e.target.closest('sup.cite, [data-tip]');
      if (c && !(e.relatedTarget && (c.contains(e.relatedTarget) || tip.contains(e.relatedTarget)))) hideTip();
      var h = e.target.closest && e.target.closest('.htab');
      if (h && !(e.relatedTarget && h.contains(e.relatedTarget))) clearTimeout(hoverT);
    });
    tip.addEventListener('mouseleave', function () { if (lastPointer !== 'touch') hideTip(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Tab') lastPointer = 'key'; }, true);
    document.addEventListener('focusin', function (e) {
      if (lastPointer === 'touch') return;   // a tap focuses the link too; the click handler decides what a tap does
      var c = e.target.closest && e.target.closest('sup.cite, [data-tip]');
      if (c) showTip(c);
    });
    document.addEventListener('focusout', function (e) {
      var c = e.target.closest && e.target.closest('sup.cite, [data-tip]');
      if (c && !(e.relatedTarget && tip.contains(e.relatedTarget))) hideTip();
    });
    window.addEventListener('scroll', function () { if (tipFor) hideTip(); }, { passive: true });
    var rt = 0;
    window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { CHARTS.forEach(function (c) { c.resize(); }); }, 150); });
    var stage = $('#stage');
    document.addEventListener('touchstart', function (e) {
      if (!e.target.closest('#stage')) return;
      touchX = e.touches[0].clientX; touchY = e.touches[0].clientY;
    }, { passive: true });
    document.addEventListener('touchend', function (e) {
      if (touchX == null || !e.target.closest('#stage')) { touchX = null; return; }
      var dx = e.changedTouches[0].clientX - touchX, dy = e.changedTouches[0].clientY - touchY;
      touchX = null;
      if (e.target.closest('.chart')) return;
      if (Math.abs(dx) > 60 && Math.abs(dy) < 50) {
        var n = $$('.htab').length;
        selectHeadline((UI.hl + (dx < 0 ? 1 : -1) + n) % n);
      }
    }, { passive: true });
    void stage;
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
    if (spec && lastPointer === 'touch' && !e.target.closest('[data-act]')) { if (tipFor === spec) hideTip(); else showTip(spec); return; }
    if (spec && lastPointer === 'touch') { showTip(spec); }
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
      case 'htab': clearTimeout(hoverT); selectHeadline(+el.getAttribute('data-i')); break;
      case 'more': {
        var b = document.getElementById('body-' + id), on = b.hidden;
        b.hidden = !on; UI.more[id] = on;
        el.setAttribute('aria-expanded', on); el.textContent = t(on ? 'read_less' : 'read_more');
        break;
      }
      case 'ctab': {
        var sid = el.getAttribute('data-story'), k = +el.getAttribute('data-k'), panel = document.getElementById('cp-' + sid);
        UI.ctab[sid] = k;
        $$('.ctabs button', panel).forEach(function (x, j) { x.setAttribute('aria-selected', j === k); });
        $$('.cbody', panel).forEach(function (x, j) { x.hidden = j !== k; });
        $('.ct', panel).textContent = pick(CH(S(sid).charts[k]), 'title');
        $$('[data-tl]', panel).forEach(function (x) { x.classList.remove('go'); });
        observeNew();
        break;
      }
      case 'bopen': openBrief(id); break;
      case 'fopen': openFlash(id); break;
      case 'wpage': UI.page = +el.getAttribute('data-p'); renderBoard(true); break;
      case 'wdet': { var key = +el.getAttribute('data-k'); UI.wdet[key] = !UI.wdet[key]; renderBoard(false); break; }
      case 'ptab': selectPair(+el.getAttribute('data-i')); break;
      case 'pexp': {
        var x = document.getElementById('x-' + id), op = x.hidden;
        x.hidden = !op; UI.pexp[id] = op;
        el.setAttribute('aria-expanded', op); el.textContent = t(op ? 'read_less' : 'read_more');
        observeNew();
        break;
      }
      case 'flip': {
        UI.flip = !UI.flip;
        var f = $('#flip');
        f.classList.toggle('on', UI.flip);
        $('.face.front', f).inert = UI.flip; $('.face.back', f).inert = !UI.flip;
        $$('[data-act="flip"]', f).forEach(function (x) { x.setAttribute('aria-pressed', UI.flip); });
        var target = $(UI.flip ? '.face.back [data-act="flip"]' : '.face.front [data-act="flip"]', f);
        if (target) setTimeout(function () { target.focus({ preventScroll: true }); }, RM() ? 0 : 420);
        break;
      }
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
        if (c && !c.hidden) closeCal(); else { if (el.closest('#foot')) window.scrollTo({ top: 0, behavior: RM() ? 'auto' : 'smooth' }); openCal(); }
        break;
      }
      case 'calm': {
        var ym = calMonth.split('-'), dt = new Date(+ym[0], +ym[1] - 1 + (+el.getAttribute('data-d')), 1);
        calMonth = dt.getFullYear() + '-' + pad2(dt.getMonth() + 1);
        renderCal();
        break;
      }
      case 'lang': setLang(el.getAttribute('data-l')); break;
      case 'theme': {
        var order = ['auto', 'light', 'dark'];
        theme = order[(order.indexOf(theme) + 1) % 3];
        store.set('fd.theme', theme);
        applyTheme();
        renderTop();
        $('[data-act="theme"]').focus();
        break;
      }
    }
  }
  function onKey(e) {
    if (e.key === 'Escape') { closeCal(); hideTip(); return; }
    var tab = e.target.closest && e.target.closest('.htab');
    if (tab) {
      var n = $$('.htab').length, i = +tab.getAttribute('data-i'), j = null;
      if (e.key === 'ArrowDown' || e.key === 'ArrowRight') j = (i + 1) % n;
      else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') j = (i - 1 + n) % n;
      else if (e.key === 'Home') j = 0; else if (e.key === 'End') j = n - 1;
      if (j != null) { e.preventDefault(); selectHeadline(j, true); }
    }
  }

  window.FD = { players: players, setLang: function (l) { setLang(l); }, goStory: function (id) { goStory(id); }, jumpSource: function (s) { jumpSource(s); }, issue: function () { return ISSUE; }, ui: UI, version: '2.0' };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
