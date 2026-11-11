/* frontier-daily · app.js
 * 读入 window.ISSUE（由 issue.js 提供），渲染整页：日卡、视频（交给 video.js）、播客播放器、图文各栏、来源、AI 生成说明。
 * 中英切换与主题选择记在 localStorage 里；读写都包在 try/catch 里，浏览器禁用存储时照常工作，只是不记住。
 * 不用 fetch、不连外网，双击 index.html（file://）即可打开。
 */
(function () {
  'use strict';

  /* ===================== basics ===================== */
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var pad2 = function (n) { return String(n).padStart(2, '0'); };
  var isCJK = function (ch) { return /[㐀-鿿豈-﫿]/.test(ch); };
  var fmtTime = function (sec) {
    sec = Math.max(0, Math.floor((sec || 0) + 1e-6));
    return Math.floor(sec / 60) + ':' + pad2(sec % 60);
  };

  var store = {
    get: function (key, fallback) {
      try { var v = window.localStorage.getItem(key); return v === null ? fallback : v; } catch (e) { return fallback; }
    },
    set: function (key, value) {
      try { window.localStorage.setItem(key, value); } catch (e) { /* storage blocked: just don't remember */ }
    }
  };

  /* ===================== UI strings ===================== */
  var I18N = {
    zh: {
      brand: '每日前沿简报', brand_alt: 'Frontier Daily', skip: '跳到正文', toc: '本页目录',
      edition: '稿件版本', note_tag: '说明', ci_full: '全文见', p_transcript: '读文字稿', chart_show: '看图表', fig_credit: '配图',
      lang_group: '语言', theme: '主题', theme_auto: '主题：跟随系统', theme_light: '主题：浅色', theme_dark: '主题：深色',
      nav_card: '日卡', nav_video: '视频', nav_podcast: '播客', nav_headline: '头条', nav_brief: '要闻', nav_flash: '快讯',
      nav_term: '一词', nav_cn_intl: '对照', nav_teaser: '预告', nav_sources: '来源', nav_about: '说明',
      sec_video: '视频', sec_podcast: '播客', sec_headline: '头条', sec_brief: '要闻', sec_flash: '快讯', sec_term: '今日一词',
      sec_cn_intl: '中外对照', sec_teaser: '预告观察', sec_sources: '完整来源', sec_about: 'AI 生成说明',
      kick_video: '视频', kick_podcast: '播客', kick_headline: '头条', kick_brief: '要闻', kick_flash: '快讯', kick_term: '今日一词',
      kick_cn_intl: '中外对照', kick_teaser: '预告观察', kick_sources: '来源', kick_about: '说明',
      title_podcast: '今日播客',
      deck_video: '{d}，只讲今天最重要的一两件事：画面为主，字少，多用对比。播客和图文在下面。',
      deck_podcast: '{d} · 单人主播 · {n} 个版本可切换，点章节跳到对应位置。',
      deck_headline: '发生了什么、关键数字、谁怎么说、为什么重要；事实和解读分开写。',
      deck_brief: '每条一段话，附一手来源。',
      deck_flash: '工作日才有：一两句话，加原文链接。',
      deck_term: '英文原词、常见译法、大白话解释，以及它在今天新闻里的用法。',
      deck_cn_intl: '把相关的国内事件和国际事件放在一起看。',
      deck_teaser: 'AI 公司负责人在社交媒体上的预告或暗示。',
      deck_sources: '本期引用的全部来源，按类型分组。正文里的 [数字] 对应这里的编号。',
      deck_about: '这一期是怎么做出来的。',
      dur_fmt: '约 {m} 分 {s} 秒',
      date_fmt: '{y} 年 {m} 月 {d} 日 · {w}', ym_fmt: '{y} 年 {m} 月',
      three: '今日三件事', three_alt: 'THREE THINGS', term: '今日一词', term_alt: 'WORD OF THE DAY',
      dc_foot: 'AI 辅助生成 · 经人工审核', save: '保存为图片', saving: '正在生成…',
      save_hint: '生成一张 1080 像素宽的 PNG，可以单独发给别人。',
      share_title: '保存日卡', share_download: '下载 PNG', share_share: '分享…', share_close: '关闭',
      share_note: '手机上可以长按图片存到相册；电脑上点"下载 PNG"。',
      share_taint: '浏览器不允许把这张配图写进导出的图片（跨源限制，常见于本地双击打开、或配图放在别的网站），已用纹样代替。配图和网页放在同一网站、或写成 data URI，就会正常带图。',
      save_fail: '生成图片失败：{e}',
      st_confirmed: '已确认', st_reported: '媒体报道', st_teaser: '未经证实',
      st_tip_confirmed: '有一手来源（官方、论文、当事人发布）', st_tip_reported: '只有媒体报道，尚无一手来源', st_tip_teaser: '社交媒体上的预告或暗示，未经证实',
      stype_official: '官方', stype_media: '媒体', stype_social: '社交媒体', stype_paper: '论文', stype_community: '社区',
      sgroup_official: '官方与一手来源', sgroup_paper: '论文', sgroup_media: '媒体报道', sgroup_community: '社区讨论', sgroup_social: '社交媒体',
      region_cn: '国内', region_intl: '国际',
      numbers: '关键数字', why: '为什么重要', why_tag: '解读', srccard: '来源卡', related: '相关', chart_src: '来源',
      unit: '单位', evidence: '原文片段', quote_tr: '中文意思',
      k_headline: '头条',
      term_alias: '常见译法', term_plain: '大白话', term_today: '今天的用法', term_example: '例句', term_note: '译法说明', term_ask: '想一想',
      ci_cn: '国内', ci_intl: '国际', ci_vs: '对照', ci_why: '对照看点',
      tz_flag: '未经证实', tz_banner: '以下是社交媒体上的预告或暗示，还没有官方发布或可靠媒体证实。只作观察，不当作事实引用；以后兑现或落空，都会回来交代。',
      tz_readings: '几种可能的解读', tz_read: '我们的观察', tz_verify: '怎样才算证实', tz_posted: '发布于',
      cited_in: '引用于', open_link: '打开原文', mock_tag: '样例',
      about_generated: '生成时间', about_how: '生成方式', about_contact: '更正与下架', about_file: '数据文件',
      foot_top: '回到顶部', fatal_title: '没有找到本期数据',
      fatal_body: '页面需要一份 issue.js（内容是 window.ISSUE = {…}）。默认依次找 {list}；也可以在地址后面加 ?issue=路径/issue.js。',
      flash_weekend: '今天是周末，快讯暂停。',
      p_variant: '配音版本', p_ai: 'AI 合成语音', p_play: '播放', p_pause: '暂停', p_back: '后退 15 秒', p_fwd: '前进 15 秒',
      p_rate: '倍速', p_now: '正在播放', p_chapters: '章节', p_seek: '播客进度',
      p_missing: '这个版本的音频暂缺（文件没找到），可以先切换到另一个版本。章节列表照常显示。',
      p_loading: '正在载入音频…',
      v_play: '播放', v_pause: '暂停', v_replay: '重播', v_prev: '上一场景', v_next: '下一场景', v_cc: '字幕',
      v_silent: '无声预览', v_silent_forced: '没有旁白音频，只能无声预览', v_full: '全屏', v_seek: '视频进度',
      v_region: '视频播放器：空格播放或暂停，左右方向键快退快进，Shift 加方向键切换场景',
      v_scenes: '场景列表', v_scene: '场景', v_src: '来源：', v_chip_ai: 'AI 合成', v_chip_silent: '无声预览',
      v_play_silent: '无声预览',
      v_no_audio: '没有找到旁白音频，已切换为无声预览：画面和字幕按时间轴播放，可以拖动进度条，或点下面的场景逐个查看。',
      v_audio_error: '旁白音频播放出错，已切换为无声预览。',
      v_silent_on: '无声预览中：旁白已关，画面和字幕照常按时间轴播放。',
      v_estimated: '这一版还没有对齐过的时间轴，场景和字幕的时间是按旁白字数估算的。'
    },
    en: {
      brand: 'Frontier Daily', brand_alt: '每日前沿简报', skip: 'Skip to content', toc: 'On this page',
      edition: 'Draft', note_tag: 'Note', ci_full: 'Full story', p_transcript: 'Read the script', chart_show: 'Show chart', fig_credit: 'Image',
      lang_group: 'Language', theme: 'Theme', theme_auto: 'Theme: system', theme_light: 'Theme: light', theme_dark: 'Theme: dark',
      nav_card: 'Card', nav_video: 'Video', nav_podcast: 'Podcast', nav_headline: 'Top', nav_brief: 'Briefs', nav_flash: 'Flash',
      nav_term: 'Term', nav_cn_intl: 'China × World', nav_teaser: 'Teasers', nav_sources: 'Sources', nav_about: 'About',
      sec_video: 'Video', sec_podcast: 'Podcast', sec_headline: 'Top stories', sec_brief: 'Briefs', sec_flash: 'Flash',
      sec_term: 'Word of the day', sec_cn_intl: 'China × World', sec_teaser: 'Teasers to watch', sec_sources: 'All sources', sec_about: 'How this was made',
      kick_video: 'Video', kick_podcast: 'Podcast', kick_headline: 'Top stories', kick_brief: 'Briefs', kick_flash: 'Flash', kick_term: 'Word of the day',
      kick_cn_intl: 'China × World', kick_teaser: 'Teasers', kick_sources: 'Sources', kick_about: 'About',
      title_podcast: "Today's podcast",
      deck_video: '{d}. One or two stories that matter most, told in pictures: few words, more comparisons. The podcast and full text follow.',
      deck_podcast: '{d} · single host · {n} versions to choose from; tap a chapter to jump to it.',
      deck_headline: 'What happened, key numbers, who said what, and why it matters — facts kept apart from interpretation.',
      deck_brief: 'One paragraph each, with primary sources.',
      deck_flash: 'Weekdays only: a line or two with a link.',
      deck_term: 'The English term, common Chinese renderings, a plain-language gloss and how it shows up in today\'s news.',
      deck_cn_intl: 'Related stories from China and elsewhere, side by side.',
      deck_teaser: 'Hints and teasers posted by AI company leaders.',
      deck_sources: 'Every source cited in this issue, grouped by type. Bracketed numbers in the text point here.',
      deck_about: 'How this issue was produced.',
      dur_fmt: 'About {m} min {s} s',
      date_fmt: '{w}, {mon} {d}, {y}', ym_fmt: '{mon} {y}',
      three: 'Three things today', three_alt: '今日三件事', term: 'Word of the day', term_alt: '今日一词',
      dc_foot: 'AI-assisted · human-reviewed', save: 'Save as image', saving: 'Rendering…',
      save_hint: 'Renders a 1080-px-wide PNG you can share on its own.',
      share_title: 'Save the day card', share_download: 'Download PNG', share_share: 'Share…', share_close: 'Close',
      share_note: 'On a phone, long-press the image to save it; on a computer, use Download PNG.',
      share_taint: 'The browser won\'t let this illustration be written into the export (a cross-origin rule, typical when the page is opened from a local file or the image sits on another site), so a pattern stands in. Serving the image from the same site, or as a data URI, fixes it.',
      save_fail: 'Could not render the image: {e}',
      st_confirmed: 'Confirmed', st_reported: 'Reported', st_teaser: 'Unverified',
      st_tip_confirmed: 'Has a primary source (official post, paper, first-hand release)', st_tip_reported: 'Media reports only, no primary source yet', st_tip_teaser: 'A social-media hint or teaser, not verified',
      stype_official: 'Official', stype_media: 'Media', stype_social: 'Social', stype_paper: 'Paper', stype_community: 'Community',
      sgroup_official: 'Official & primary', sgroup_paper: 'Papers', sgroup_media: 'Media reports', sgroup_community: 'Community', sgroup_social: 'Social media',
      region_cn: 'China', region_intl: 'World',
      numbers: 'Key numbers', why: 'Why it matters', why_tag: 'Interpretation', srccard: 'Sources', related: 'Related', chart_src: 'Source',
      unit: 'Unit', evidence: 'Original wording', quote_tr: 'In Chinese',
      k_headline: 'Top story',
      term_alias: 'Chinese renderings', term_plain: 'In plain words', term_today: 'In today\'s news', term_example: 'Example', term_note: 'Translation note', term_ask: 'Your take',
      ci_cn: 'China', ci_intl: 'World', ci_vs: 'vs', ci_why: 'What the pairing shows',
      tz_flag: 'Unverified', tz_banner: 'These are hints and teasers from social media. Nothing here has been confirmed by an official release or reliable reporting. We note them to watch, not as facts, and will report back whether they pan out.',
      tz_readings: 'Possible readings', tz_read: 'Our read', tz_verify: 'What would confirm it', tz_posted: 'Posted',
      cited_in: 'Cited in', open_link: 'Open original', mock_tag: 'Sample',
      about_generated: 'Generated', about_how: 'How', about_contact: 'Corrections', about_file: 'Data file',
      foot_top: 'Back to top', fatal_title: 'No issue data found',
      fatal_body: 'The page needs an issue.js file (window.ISSUE = {…}). It looks for {list} in turn; you can also add ?issue=path/issue.js to the address.',
      flash_weekend: 'Weekend: no flash items today.',
      p_variant: 'Voice', p_ai: 'Synthetic voice', p_play: 'Play', p_pause: 'Pause', p_back: 'Back 15 s', p_fwd: 'Forward 15 s',
      p_rate: 'Speed', p_now: 'Now playing', p_chapters: 'Chapters', p_seek: 'Podcast position',
      p_missing: 'Audio for this version is missing (file not found). Try the other version; the chapter list still works as an outline.',
      p_loading: 'Loading audio…',
      v_play: 'Play', v_pause: 'Pause', v_replay: 'Replay', v_prev: 'Previous scene', v_next: 'Next scene', v_cc: 'Subtitles',
      v_silent: 'Silent preview', v_silent_forced: 'No narration audio: silent preview only', v_full: 'Full screen', v_seek: 'Video position',
      v_region: 'Video player: Space to play or pause, arrow keys to seek, Shift+arrows to change scene',
      v_scenes: 'Scenes', v_scene: 'Scene', v_src: 'Source: ', v_chip_ai: 'AI-generated', v_chip_silent: 'Silent preview',
      v_play_silent: 'Silent preview',
      v_no_audio: 'Narration audio not found, so this is a silent preview: pictures and subtitles follow the timeline. Drag the bar or tap a scene below to step through.',
      v_audio_error: 'The narration failed to play, so this switched to a silent preview.',
      v_silent_on: 'Silent preview: narration off; pictures and subtitles keep to the timeline.',
      v_estimated: 'This cut has no aligned timeline yet; scene and subtitle timings are estimated from the narration length.'
    }
  };
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

  var lang = store.get('fd.lang', 'zh') === 'en' ? 'en' : 'zh';
  var t = function (key, vars) {
    var s = (I18N[lang] && I18N[lang][key] != null) ? I18N[lang][key] : (I18N.zh[key] != null ? I18N.zh[key] : key);
    if (vars) s = s.replace(/\{(\w+)\}/g, function (m, k) { return vars[k] != null ? vars[k] : m; });
    return s;
  };
  var tOther = function (key) { var o = lang === 'zh' ? 'en' : 'zh'; return I18N[o][key] != null ? I18N[o][key] : ''; };

  /* pick(obj, 'title') → obj.title_en / obj.title_zh / obj.title, by current language with Chinese fallback */
  var pick = function (obj, key) {
    if (!obj) return '';
    var v = obj[key + '_' + lang];
    if (v != null && v !== '') return v;
    v = obj[key + '_zh'];
    if (v != null && v !== '') return v;
    v = obj[key];
    return v == null ? '' : v;
  };
  var pickL = function (obj) { return obj ? (obj[lang] || obj.zh || obj.en || '') : ''; };
  var pickArr = function (obj, key) {
    var v = obj && obj[key + '_' + lang];
    if (Array.isArray(v) && v.length) return v;
    v = obj && obj[key + '_zh'];
    return Array.isArray(v) ? v : [];
  };

  /* ===================== state ===================== */
  var RAW = null;        // the issue as loaded; may carry several editions (稿件版本)
  var ISSUE = null;      // what the page shows: RAW merged with the current edition
  var EDITION = null;    // current edition id, or null when the issue has no editions
  var BASE = '';
  var SRC = {};          // id → source
  var SRC_N = {};        // id → display number
  var SRC_ORDER = [];
  var ITEM = {};         // id → {item, kind, n}
  var CITED = {};        // source id → [{id, label}]
  var CHARTS = {};
  var players = { video: null, podcast: null };
  var issueSrc = '';

  /* editions: RAW.editions = [{id, label_zh, label_en, daily_card, video, sections, sources, ...}]
     an edition replaces the base fields it carries; daily_card and meta are merged key by key */
  function editions() { return (RAW && Array.isArray(RAW.editions)) ? RAW.editions : []; }
  function mergeEdition(base, ed) {
    var out = {};
    Object.keys(base).forEach(function (k) { if (k !== 'editions' && k !== 'default_edition') out[k] = base[k]; });
    if (!ed) return out;
    Object.keys(ed).forEach(function (k) {
      if (k === 'id' || /^label_/.test(k)) return;
      var bv = out[k], ev = ed[k];
      var plain = function (o) { return o && typeof o === 'object' && !Array.isArray(o); };
      out[k] = ((k === 'daily_card' || k === 'meta') && plain(bv) && plain(ev)) ? Object.assign({}, bv, ev) : ev;
    });
    return out;
  }
  function applyEdition() {
    var eds = editions();
    if (!eds.length) { ISSUE = RAW; EDITION = null; return; }
    var ids = eds.map(function (e) { return e.id; });
    if (ids.indexOf(EDITION) < 0) {
      var saved = store.get('fd.edition', '');
      EDITION = ids.indexOf(saved) >= 0 ? saved : (ids.indexOf(RAW.default_edition) >= 0 ? RAW.default_edition : ids[0]);
    }
    ISSUE = mergeEdition(RAW, eds[ids.indexOf(EDITION)]);
  }
  function editionLabel() {
    var ed = editions().filter(function (e) { return e.id === EDITION; })[0];
    return ed ? pick(ed, 'label') : '';
  }

  var asset = function (p) {
    if (!p) return p;
    if (/^(data:|blob:|https?:|file:|\/)/i.test(p)) return p;
    return BASE + p;
  };
  var normImage = function (img) {
    if (!img) return null;
    if (typeof img === 'string') return { src: img };
    return img.src ? img : null;
  };
  var host = function (url) {
    try { return new URL(url).hostname.replace(/^www\./, ''); } catch (e) { return ''; }
  };

  /* ===================== text helpers ===================== */
  function cite(id) {
    var n = SRC_N[id];
    if (!n) return '';
    var s = SRC[id] || {};
    return '<sup class="cite"><a href="#src-' + esc(id) + '" title="' + esc(srcName(s) + (s.date ? ' · ' + s.date : '')) + '">' + n + '</a></sup>';
  }
  /* inline markup: **bold**, [^s1] citations, and "中文（English）" glosses get a quieter Latin style */
  function rich(text) {
    var s = esc(text);
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/（([A-Za-z][^（）<>]*?)）/g, '<span class="gloss">（$1）</span>');
    // U+2060 (word joiner) keeps a citation mark on the same line as the word before it
    s = s.replace(/\[\^([\w-]+)\]/g, function (m, id) { var c = cite(id); return c ? '⁠' + c : ''; });
    return s;
  }
  function paras(x) {
    if (Array.isArray(x)) return x.filter(Boolean);
    return String(x || '').split(/\n+/).map(function (p) { return p.trim(); }).filter(Boolean);
  }
  function numHTML(text) {
    return esc(text).replace(/[^\d.,\-\s]+/g, function (u, off) {
      return '<span class="u' + (off === 0 ? ' pre' : '') + '">' + u + '</span>';
    });
  }
  function joinUnit(value, unit) {
    if (unit == null || unit === '') return String(value);
    return String(value) + (isCJK(String(unit).charAt(0)) ? ' ' : '') + unit;
  }
  function numVal(n) { return (lang === 'en' && n.value_en != null) ? n.value_en : n.value; }
  function srcName(s) { return (lang === 'en' && s.name_en) ? s.name_en : (s.name || ''); }
  function badge(status) {
    if (!status) return '';
    return '<span class="badge badge--' + esc(status) + '" title="' + esc(t('st_tip_' + status)) + '">' + esc(t('st_' + status)) + '</span>';
  }
  function regionTag(r) { return r ? '<span class="region">' + esc(t('region_' + r)) + '</span>' : ''; }
  function durText(sec) {
    sec = Math.round(sec || 0);
    return t('dur_fmt', { m: Math.floor(sec / 60), s: sec % 60 });
  }

  /* ===================== data index ===================== */
  function srcIdsOf(item) {
    var ids = [];
    var push = function (id) { if (id && ids.indexOf(id) < 0) ids.push(id); };
    (item.sources || []).forEach(function (s) { push(typeof s === 'string' ? s : s.id); });
    (item.numbers || []).forEach(function (n) { push(n.source_id); });
    if (item.chart) push(item.chart.source_id);
    if (item.quote) push(item.quote.source_id);
    ['body_zh', 'body_en', 'summary_zh', 'summary_en', 'why_zh', 'why_en'].forEach(function (k) {
      String(item[k] || '').replace(/\[\^([\w-]+)\]/g, function (m, id) { push(id); return m; });
    });
    ['cn', 'intl'].forEach(function (side) { if (item[side]) srcIdsOf(item[side]).forEach(push); });
    return ids;
  }
  function buildIndex() {
    SRC = {}; SRC_N = {}; SRC_ORDER = []; ITEM = {}; CITED = {};
    var addSrc = function (s) {
      if (!s || !s.id) return;
      if (!SRC[s.id]) { SRC[s.id] = Object.assign({}, s); SRC_ORDER.push(s.id); }
      else { Object.keys(s).forEach(function (k) { if (SRC[s.id][k] == null || SRC[s.id][k] === '') SRC[s.id][k] = s[k]; }); }
    };
    (ISSUE.sources || []).forEach(addSrc);
    var walk = function (it) {
      (it.sources || []).forEach(function (s) { if (typeof s === 'object' && s.name) addSrc(s); });
      ['cn', 'intl'].forEach(function (side) { if (it[side]) walk(it[side]); });
    };
    (ISSUE.sections || []).forEach(function (sec) { (sec.items || []).forEach(walk); });
    // numbering follows reading order: the first source cited on the page is [1]; uncited ones go last
    var order = [];
    var kinds = [];
    (ISSUE.sections || []).forEach(function (sec) { if (sec && sec.kind && kinds.indexOf(sec.kind) < 0) kinds.push(sec.kind); });
    kinds.forEach(function (kind) {
      (ISSUE.sections || []).forEach(function (sec) {
        if (!sec || sec.kind !== kind) return;
        (sec.items || []).forEach(function (it) {
          srcIdsOf(it).forEach(function (id) { if (SRC[id] && order.indexOf(id) < 0) order.push(id); });
        });
      });
    });
    SRC_ORDER.forEach(function (id) { if (order.indexOf(id) < 0) order.push(id); });
    order.forEach(function (id, i) { SRC_N[id] = i + 1; });
    SRC_ORDER = order;
    var count = {};
    (ISSUE.sections || []).forEach(function (sec) {
      (sec.items || []).forEach(function (it) {
        var n = count[sec.kind] = (count[sec.kind] || 0) + 1;
        if (it.id) ITEM[it.id] = { item: it, kind: sec.kind, n: n };
        srcIdsOf(it).forEach(function (sid) {
          (CITED[sid] = CITED[sid] || []).push({ id: it.id, kind: sec.kind, n: n });
        });
      });
    });
  }

  /* ===================== loader ===================== */
  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.async = false;
      s.onload = function () { resolve(src); };
      s.onerror = function () { s.remove(); reject(new Error('cannot load ' + src)); };
      document.head.appendChild(s);
    });
  }
  /* ?issue= accepts a relative path ending in .js (no scheme, no //), so a crafted link cannot pull in a script from another site */
  function safeIssuePath(p) { return /^[^:?#]+\.js$/i.test(p) && p.indexOf('//') !== 0 && p.indexOf('\\') < 0; }
  function candidates() {
    var meta = $('meta[name="fd-issue"]');
    var list = ((meta && meta.content) || 'issue.js mock/issue.js').split(/\s+/).filter(Boolean);
    var q = null;
    try { q = new URLSearchParams(window.location.search).get('issue'); } catch (e) { q = null; }
    if (q) {
      if (safeIssuePath(q)) list = [q];
      else console.warn('[frontier-daily] ignored ?issue=' + q + ' (only relative .js paths are allowed)');
    }
    return list;
  }
  function loadIssue() {
    var list = candidates();
    var i = 0;
    var next = function () {
      if (i >= list.length) return Promise.resolve(null);
      var src = list[i++];
      window.ISSUE = undefined;
      return loadScript(src).then(function () {
        return window.ISSUE ? { issue: window.ISSUE, src: src } : next();
      }, next);
    };
    return next().then(function (r) { if (!r) r = { issue: null, list: list }; return r; });
  }

  /* ===================== render: static parts ===================== */
  function fmtDate(full) {
    var p = String(ISSUE.date || '').split('-');
    var y = p[0], m = +p[1], d = +p[2];
    var w = lang === 'en' ? (ISSUE.weekday_en || '') : (ISSUE.weekday_zh || '');
    if (!full) return t('ym_fmt', { y: y, m: m, mon: MONTHS[m - 1] || '' });
    return t('date_fmt', { y: y, m: m, d: d, w: w, mon: MONTHS[m - 1] || '' });
  }
  function isWeekend() {
    var d = new Date(ISSUE.date + 'T12:00:00');
    var wd = isNaN(d) ? -1 : d.getDay();
    return wd === 0 || wd === 6;
  }

  function renderChrome() {
    var meta = ISSUE.meta || {};
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    document.title = t('brand') + ' · ' + ISSUE.date;
    $('.skip').textContent = t('skip');
    $('.brand-zh').textContent = t('brand');
    $('.brand-en').textContent = t('brand_alt');
    $('#topdate').textContent = [fmtDate(true), pick(meta, 'edition'), editionLabel()].filter(Boolean).join(' · ');
    $('#secnav').setAttribute('aria-label', t('toc'));
    $('.lang').setAttribute('aria-label', t('lang_group'));
    $$('.lang button').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.lang === lang ? 'true' : 'false'); });
    syncThemeBtn();
    // strip under the header: edition switch (when the issue has editions) + a short notice
    var eds = editions();
    var notice = pick(meta, 'notice');
    var tag = pick(meta, 'notice_tag') || (meta.mock ? t('mock_tag') : t('note_tag'));
    var sw = eds.length > 1 ? '<div class="edswitch"><span class="eb-label">' + esc(t('edition')) + '</span><div class="seg" role="group" aria-label="' + esc(t('edition')) + '">' +
      eds.map(function (e) { return '<button type="button" data-edition="' + esc(e.id) + '" aria-pressed="' + (e.id === EDITION ? 'true' : 'false') + '">' + esc(pick(e, 'label') || e.id) + '</button>'; }).join('') +
      '</div></div>' : '';
    var mb = $('#mockbar');
    if (sw || notice) {
      mb.innerHTML = '<div class="' + (meta.mock ? 'mockbar' : 'notebar') + '"><div class="wrap notebar-in">' + sw +
        (notice ? '<p><b>' + esc(tag) + '</b><span>' + esc(notice) + '</span></p>' : '') + '</div></div>';
      $$('[data-edition]', mb).forEach(function (b) { b.addEventListener('click', function () { setEdition(b.dataset.edition); }); });
    } else mb.innerHTML = '';
  }
  function cardFoot() { return pick(ISSUE.meta || {}, 'card_foot') || t('dc_foot'); }

  function renderCard() {
    var dc = ISSUE.daily_card || {};
    var meta = ISSUE.meta || {};
    var p = String(ISSUE.date || '').split('-');
    var heads = (dc.headlines || []).slice(0, 3);
    var term = dc.term || {};
    var img = normImage(dc.image);
    var wd = lang === 'en' ? ISSUE.weekday_en : ISSUE.weekday_zh;
    var wd2 = lang === 'en' ? ISSUE.weekday_zh : ISSUE.weekday_en;
    var ed = [pick(meta, 'edition'), meta.issue_no ? 'No.<span class="num">' + esc(meta.issue_no) + '</span>' : ''].filter(Boolean).join(' · ');
    var termRef = term.ref || (ITEM['term-' + term.en] ? 'term-' + term.en : '');
    var html =
      '<article class="daycard" id="daycard" aria-label="' + esc(t('three') + ' · ' + fmtDate(true)) + '">' +
        '<header class="dc-top"><span class="dc-brand"><i class="mark" aria-hidden="true"></i>' + esc(t('brand')) + ' <small>' + esc(t('brand_alt')) + '</small></span>' +
        '<span class="dc-ed">' + ed + '</span></header>' +
        '<div class="dc-body"><div class="dc-left">' +
          '<div class="dc-date"><div class="dc-day num" aria-hidden="true">' + esc(pad2(+p[2] || 0)) + '</div>' +
          '<div class="dc-dmeta"><div class="dc-ym">' + esc(fmtDate(false)) + '</div><div class="dc-wd">' + esc(wd || '') + '</div><div class="dc-wd2">' + esc(wd2 || '') + '</div></div></div>' +
          (img ? '<figure class="dc-fig" style="margin-bottom:0"><img src="' + esc(asset(img.src)) + '" alt="' + esc(pick(img, 'alt')) + '"></figure>' : '') +
        '</div><div class="dc-right">' +
          '<div class="perf" aria-hidden="true"></div>' +
          '<section class="dc-sec dc-three"><h2 class="dc-label">' + esc(t('three')) + ' <small>' + esc(t('three_alt')) + '</small></h2><ol>' +
            heads.map(function (h, i) {
              var txt = esc(pickL(h));
              return '<li><span class="dc-i num">' + pad2(i + 1) + '</span>' + (h.ref ? '<a href="#item-' + esc(h.ref) + '">' + txt + '</a>' : '<a>' + txt + '</a>') + '</li>';
            }).join('') +
          '</ol></section>' +
          '<div class="perf" aria-hidden="true"></div>' +
          '<section class="dc-sec dc-term"><h2 class="dc-label">' + esc(t('term')) + ' <small>' + esc(t('term_alt')) + '</small></h2>' +
            '<div class="dc-term-w"><span class="zh">' + (termRef ? '<a href="#item-' + esc(termRef) + '" style="text-decoration:none">' + esc(term.zh || '') + '</a>' : esc(term.zh || '')) + '</span><span class="en">' + esc(term.en || '') + '</span></div>' +
            '<p>' + esc(pick(term, 'explain')) + '</p></section>' +
        '</div></div>' +
        '<footer class="dc-foot"><span>' + esc(cardFoot()) + '</span><span class="site">' + esc(meta.site || '') + '</span></footer>' +
      '</article>';
    $('#card-root').innerHTML = html;
    var btn = $('#dc-save');
    btn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v10.5m0 0-4.2-4.2M12 14.5l4.2-4.2M5 19.5h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><span>' + esc(t('save')) + '</span>';
    $('#card-hint').textContent = t('save_hint');
  }

  function blockHead(n, kind, title, deck) {
    return '<div class="block-head"><div class="block-kick"><span class="num">' + pad2(n) + '</span><span>' + esc(tOther('kick_' + kind)) + '</span></div>' +
      '<h2 class="block-title">' + esc(title || t('sec_' + kind)) + '</h2>' + (deck ? '<p class="block-deck">' + esc(deck) + '</p>' : '') + '</div>';
  }

  /* ---------- items ---------- */
  function numbersHTML(nums, withHead) {
    if (!nums || !nums.length) return '';
    return '<div class="numbers">' + (withHead ? '<div class="numbers-h">' + esc(t('numbers')) + '</div>' : '') +
      nums.map(function (n) {
        var ctx = pick(n, 'context');
        return '<div class="numcell"><div class="nv num' + (String(numVal(n)).length > 7 ? ' long' : '') + '">' + numHTML(numVal(n)) + '</div>' +
          '<div class="nmeta"><div class="nl">' + esc(pick(n, 'label')) + (n.source_id ? cite(n.source_id) : '') + '</div>' +
          (ctx ? '<div class="nc">' + esc(ctx) + '</div>' : '') + '</div>' +
          (n.quote ? '<details class="nq"><summary>' + esc(t('evidence')) + '</summary><q>' + esc(n.quote) + '</q></details>' : '') +
          '</div>';
      }).join('') + '</div>';
  }
  function srcLink(s) {
    var full = SRC[s.id] || s;
    return full.url ? '<a href="' + esc(full.url) + '" target="_blank" rel="noopener noreferrer">' + esc(srcName(full)) + '</a>' : esc(srcName(full));
  }
  function itemSources(it) {
    return (it.sources || []).map(function (s) { return typeof s === 'string' ? { id: s } : s; }).filter(function (s) { return s && (s.id || s.name); });
  }
  function sourceCardHTML(it) {
    var list = itemSources(it);
    if (!list.length) return '';
    return '<div class="srccard"><h4>' + esc(t('srccard')) + '</h4><ol>' + list.map(function (s0) {
      var s = SRC[s0.id] || s0;
      var ti = pick(s, 'title');
      return '<li><a class="src-n" href="#src-' + esc(s.id) + '">' + (SRC_N[s.id] || '·') + '</a><div>' +
        (s.url ? '<a class="src-name" href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer">' + esc(srcName(s)) + '</a>' : '<span class="src-name">' + esc(srcName(s)) + '</span>') +
        '<span class="stype stype--' + esc(s.type || 'media') + '">' + esc(t('stype_' + (s.type || 'media'))) + '</span>' +
        (ti ? '<div class="src-t">' + esc(ti) + '</div>' : '') +
        '<div class="src-m">' + esc([s.date, host(s.url)].filter(Boolean).join(' · ')) + '</div></div></li>';
    }).join('') + '</ol></div>';
  }
  function relLabel(r) {
    var note = pick(r, 'note');
    if (note) return note;
    var tgt = ITEM[r.id];
    return tgt ? pick(tgt.item, 'title') : (r.id || '');
  }
  function relHref(r) { return r.url ? r.url : '#item-' + r.id; }
  function relatedHTML(rel) {
    if (!rel || !rel.length) return '';
    return '<div class="related"><h4>' + esc(t('related')) + '</h4><ul>' + rel.map(function (r) {
      return '<li><a href="' + esc(relHref(r)) + '">' + esc(relLabel(r)) + '</a></li>';
    }).join('') + '</ul></div>';
  }
  function relInline(rel) {
    if (!rel || !rel.length) return '';
    return '<p class="rel-inline">' + esc(t('related')) + '：' + rel.map(function (r) {
      return '<a href="' + esc(relHref(r)) + '">' + esc(relLabel(r)) + '</a>';
    }).join(' · ') + '</p>';
  }
  function figureHTML(img) {
    var cap = pick(img, 'caption'), credit = pick(img, 'credit');
    return '<figure class="fig"><div class="fig-frame"><img src="' + esc(asset(img.src)) + '" alt="' + esc(pick(img, 'alt')) + '" loading="lazy"></div>' +
      ((cap || credit) ? '<figcaption><span>' + esc(cap) + '</span>' + (credit ? '<span class="credit">' + esc(credit) + '</span>' : '') + '</figcaption>' : '') + '</figure>';
  }
  function chartHTML(chart, id) {
    if (!chart || !chart.series || !chart.series.length) return '';
    CHARTS[id] = chart;
    var unit = pick(chart, 'unit_note') || ((lang === 'en' && chart.unit_en != null) ? chart.unit_en : chart.unit);
    var note = [unit ? t('unit') + '：' + unit : '', pick(chart, 'note')].filter(Boolean).join(' · ');
    return '<figure class="chart"><figcaption class="chart-t">' + esc(pick(chart, 'title')) + '</figcaption>' +
      '<div class="chart-svg" data-chart="' + esc(id) + '"></div>' +
      '<p class="chart-note">' + esc(note) + (chart.source_id ? ' · ' + esc(t('chart_src')) + cite(chart.source_id) : '') + '</p></figure>';
  }
  function pullHTML(q) {
    if (!q || !q.text) return '';
    var tr = lang === 'en' ? '' : (q.text_zh || '');
    var who = (lang === 'en' && q.who_en) ? q.who_en : q.who;
    return '<blockquote class="pull"><p class="o">“' + esc(q.text) + '”</p>' + (tr ? '<p class="tr">' + esc(tr) + '</p>' : '') +
      '<cite>— ' + esc(who || '') + (q.source_id ? cite(q.source_id) : '') + '</cite></blockquote>';
  }
  function whyHTML(it) {
    var w = pick(it, 'why');
    if (!w) return '';
    return '<aside class="why"><h4>' + esc(t('why')) + ' <span>' + esc(t('why_tag')) + '</span></h4><p>' + rich(w) + '</p></aside>';
  }

  function renderHeadline(it, i) {
    var img = normImage(it.image);
    var kick = t('k_headline') + ' ' + pad2(i + 1) + (pick(it, 'kicker') ? ' · ' + pick(it, 'kicker') : '');
    return '<article class="story" id="item-' + esc(it.id) + '">' +
      '<header class="story-head"><div class="story-kick"><span class="kick">' + esc(kick) + '</span>' + badge(it.status) + regionTag(it.region) + '</div>' +
      '<h3 class="story-title">' + rich(pick(it, 'title')) + '</h3>' +
      (pick(it, 'summary') ? '<p class="lead">' + rich(pick(it, 'summary')) + '</p>' : '') + '</header>' +
      '<div class="story-grid"><div class="story-main">' +
        (img ? figureHTML(img) : '') +
        '<div class="prose">' + paras(pick(it, 'body')).map(function (p) { return '<p>' + rich(p) + '</p>'; }).join('') + '</div>' +
        pullHTML(it.quote) +
        chartHTML(it.chart, 'c-' + it.id) +
        whyHTML(it) +
      '</div><div class="story-side">' +
        numbersHTML(it.numbers, true) +
        sourceCardHTML(it) +
        relatedHTML(it.related) +
      '</div></div></article>';
  }

  function miniNumbers(nums, max) {
    nums = (nums || []).slice(0, max || 2);
    if (!nums.length) return '';
    return '<div class="brief-nums">' + nums.map(function (n) {
      return '<div class="brief-num"><span class="nv num">' + numHTML(numVal(n)) + '</span><span class="nl">' + esc(pick(n, 'label')) + (n.source_id ? cite(n.source_id) : '') + '</span></div>';
    }).join('') + '</div>';
  }
  function whyInline(it) {
    var w = pick(it, 'why');
    return w ? '<p class="why-inline"><b>' + esc(t('why_tag')) + '</b>' + rich(w) + '</p>' : '';
  }
  function renderBrief(it, i) {
    var srcs = itemSources(it);
    var body = pick(it, 'body');
    var img = normImage(it.image);
    return '<article class="brief" id="item-' + esc(it.id) + '">' +
      (img ? figureHTML(img) : '') +
      '<div class="brief-top"><span class="i">' + pad2(i + 1) + '</span>' + regionTag(it.region) + badge(it.status) + '</div>' +
      '<h3 class="brief-title">' + rich(pick(it, 'title')) + '</h3>' +
      (pick(it, 'summary') ? '<p class="brief-sum brief-lead">' + rich(pick(it, 'summary')) + '</p>' : '') +
      (body ? paras(body).map(function (p) { return '<p class="brief-sum">' + rich(p) + '</p>'; }).join('') : '') +
      miniNumbers(it.numbers, 2) +
      chartHTML(it.chart, 'c-' + it.id) +
      whyInline(it) +
      relInline(it.related) +
      (srcs.length ? '<div class="brief-src">' + srcs.map(function (s) { return '<span>' + srcLink(s) + (SRC_N[s.id] ? cite(s.id) : '') + '</span>'; }).join('') + '</div>' : '') +
      '</article>';
  }

  function renderFlash(it, i) {
    var srcs = itemSources(it);
    var chart = chartHTML(it.chart, 'c-' + it.id);
    return '<li id="item-' + esc(it.id) + '"><span class="fi num">' + pad2(i + 1) + '</span><div>' +
      '<h3 class="flash-t">' + rich(pick(it, 'title')) + (it.status && it.status !== 'confirmed' ? badge(it.status) : '') + '</h3>' +
      (pick(it, 'summary') ? '<p>' + rich(pick(it, 'summary')) + '</p>' : '') +
      (chart ? '<details class="flash-chart"><summary>' + esc(t('chart_show')) + '</summary>' + chart + '</details>' : '') +
      (srcs.length ? '<div class="flash-src">' + srcs.map(function (s) { return srcLink(s) + (SRC_N[s.id] ? cite(s.id) : ''); }).join(' · ') + '</div>' : '') +
      '</div></li>';
  }

  function renderTerm(it) {
    // the writing prompt may prefix titles with "今日一词：" / "Word of the day:"; the card shows the bare term
    var zh = String(it.title_zh || '').replace(/^今日一词[：:]\s*/, '');
    var en = String(it.title_en || '').replace(/^word of the day\s*[:：]\s*/i, '');
    var aliases = it.aliases_zh || [];
    var ex = it.example || null;
    var exEn = ex && ex.en ? esc(ex.en).replace(new RegExp('\\b(' + en.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')\\b', 'i'), '<span class="hit">$1</span>') : '';
    var blocks = [];
    if (pick(it, 'summary')) blocks.push('<div class="term-block"><h4>' + esc(t('term_plain')) + '</h4><p>' + rich(pick(it, 'summary')) + '</p></div>');
    if (pick(it, 'body')) blocks.push('<div class="term-block"><h4>' + esc(t('term_today')) + '</h4>' + paras(pick(it, 'body')).map(function (p) { return '<p>' + rich(p) + '</p>'; }).join('') + '</div>');
    if (ex) blocks.push('<div class="term-block"><h4>' + esc(t('term_example')) + '</h4><p class="ex-en">' + exEn + '</p>' + (lang === 'zh' && ex.zh ? '<p class="ex-zh">' + esc(ex.zh) + '</p>' : '') + '</div>');
    if (pick(it, 'note')) blocks.push('<div class="term-block"><h4>' + esc(t('term_note')) + '</h4><p>' + rich(pick(it, 'note')) + '</p></div>');
    if (pick(it, 'why')) blocks.push('<div class="term-block"><h4>' + esc(t('why')) + ' <span class="tag">' + esc(t('why_tag')) + '</span></h4><p>' + rich(pick(it, 'why')) + '</p></div>');
    if (pick(it, 'ask')) blocks.push('<p class="term-ask">' + esc(t('term_ask')) + '：' + esc(pick(it, 'ask')) + '</p>');
    if (it.related && it.related.length) blocks.push(relInline(it.related));
    var tsrc = itemSources(it);
    if (tsrc.length) blocks.push('<div class="brief-src">' + tsrc.map(function (s) { return '<span>' + srcLink(s) + (SRC_N[s.id] ? cite(s.id) : '') + '</span>'; }).join('') + '</div>');
    return '<article class="term" id="item-' + esc(it.id) + '">' +
      '<div class="term-word"><div class="term-zh">' + esc(zh) + '</div><div class="term-en">' + esc(en) + '</div>' +
      (aliases.length ? '<div class="term-alias"><span>' + esc(t('term_alias')) + '</span>' + aliases.map(function (a, k) { return '<b class="' + (k === 0 ? 'main' : '') + '">' + esc(a) + '</b>'; }).join('') + '</div>' : '') +
      '</div><div class="term-body">' + blocks.join('') + '</div></article>';
  }

  function pairSide(side, kind) {
    if (!side) return '<div class="pair-side"></div>';
    var n = (side.numbers || [])[0];
    var srcs = itemSources(side);
    return '<div class="pair-side pair-side--' + kind + '">' +
      '<div class="pair-tag"><span>' + esc(t('ci_' + kind)) + '</span>' + badge(side.status) + '</div>' +
      '<h4>' + rich(pick(side, 'title')) + '</h4>' +
      (pick(side, 'summary') ? '<p>' + rich(pick(side, 'summary')) + '</p>' : '') +
      (pick(side, 'body') ? paras(pick(side, 'body')).map(function (p) { return '<p>' + rich(p) + '</p>'; }).join('') : '') +
      (n ? '<div class="pn"><span class="nv num">' + numHTML(numVal(n)) + '</span><span class="nl">' + esc(pick(n, 'label')) + (n.source_id ? cite(n.source_id) : '') + '</span></div>' : '') +
      (srcs.length ? '<div class="psrc">' + srcs.map(function (s) { return srcLink(s) + (SRC_N[s.id] ? cite(s.id) : ''); }).join(' · ') + '</div>' : '') +
      '</div>';
  }
  /* cn_intl, three accepted shapes:
     1. one item with `cn` and `intl` sub-items (template format);
     2. one item (usually the Chinese event) whose related[0] points at its counterpart elsewhere on the page
        (what the writing prompt produces): shown as a linked pair, the item's own details below;
     3. plain items without a counterpart: paired in order (region "cn" goes left). */
  function pairShell(p, head, grid, extra) {
    return '<article class="pair" id="item-' + esc(p.id) + '">' + head +
      '<div class="pair-grid">' + grid[0] + '<div class="pair-mid" aria-hidden="true">' + esc(t('ci_vs')) + '</div>' + grid[1] + '</div>' + (extra || '') + '</article>';
  }
  function pairHead(n, title) {
    return title ? '<div class="pair-h"><span class="kick">' + esc(t('sec_cn_intl')) + (n ? ' ' + pad2(n) : '') + '</span><h3>' + rich(title) + '</h3></div>' : '';
  }
  function pairBrief(side, kind, isSelf) {
    if (!side) return '<div class="pair-side"></div>';
    var n = (side.numbers || [])[0];
    var ref = ITEM[side.id];
    return '<div class="pair-side pair-side--' + kind + '">' +
      '<div class="pair-tag"><span>' + esc(t('ci_' + kind)) + '</span>' + badge(side.status) + '</div>' +
      '<h4>' + rich(pick(side, 'title')) + '</h4>' +
      (pick(side, 'summary') ? '<p>' + rich(pick(side, 'summary')) + '</p>' : '') +
      (n ? '<div class="pn"><span class="nv num">' + numHTML(numVal(n)) + '</span><span class="nl">' + esc(pick(n, 'label')) + (n.source_id ? cite(n.source_id) : '') + '</span></div>' : '') +
      (!isSelf && ref ? '<a class="pair-more" href="#item-' + esc(side.id) + '">' + esc(t('ci_full')) + '：' + esc(t('nav_' + ref.kind) + ' ' + ref.n) + ' →</a>' : '') +
      '</div>';
  }
  function renderCnIntl(items) {
    var out = [];
    var loose = [];
    items.forEach(function (it) {
      var rel = (it.related || [])[0];
      var other = rel && ITEM[rel.id] && ITEM[rel.id].item !== it ? ITEM[rel.id].item : null;
      if (it.cn || it.intl) {
        out.push(pairShell(it, pairHead(0, pick(it, 'title')), [pairSide(it.cn, 'cn'), pairSide(it.intl, 'intl')],
          pick(it, 'why') ? '<div class="pair-why"><h4>' + esc(t('ci_why')) + '</h4><p>' + rich(pick(it, 'why')) + '</p>' + relInline(it.related) + '</div>' : ''));
      } else if (other) {
        var selfIntl = it.region === 'intl';
        var note = String(pick(rel, 'note') || '').replace(/^(中外对照|China\s*[–—-]\s*international pair)\s*[：:]\s*/i, '');
        var detail = '<div class="pair-detail"><div class="pair-detail-h"><span class="kick">' + esc(t('ci_' + (selfIntl ? 'intl' : 'cn'))) + '</span><h4>' + rich(pick(it, 'title')) + '</h4></div>' +
          '<div class="prose">' + paras(pick(it, 'body')).map(function (p) { return '<p>' + rich(p) + '</p>'; }).join('') + '</div>' +
          numbersHTML(it.numbers, true) + chartHTML(it.chart, 'c-' + it.id) + sourceCardHTML(it) + '</div>';
        var why = pick(it, 'why') ? '<div class="pair-why"><h4>' + esc(t('why')) + ' <span class="tag">' + esc(t('why_tag')) + '</span></h4><p>' + rich(pick(it, 'why')) + '</p>' + relInline((it.related || []).slice(1)) + '</div>' : '';
        out.push(pairShell(it, pairHead(out.length + 1, note || pick(it, 'title')),
          selfIntl ? [pairBrief(other, 'cn', false), pairBrief(it, 'intl', true)] : [pairBrief(it, 'cn', true), pairBrief(other, 'intl', false)],
          detail + why));
      } else loose.push(it);
    });
    for (var k = 0; k < loose.length; k += 2) {
      var a = loose[k], b = loose[k + 1];
      if (b && a.region === 'intl' && b.region !== 'intl') { var tmp = a; a = b; b = tmp; }
      var why2 = pick(a, 'why') || (b ? pick(b, 'why') : '');
      out.push(pairShell(a, '', [pairSide(a, 'cn'), pairSide(b, 'intl')],
        why2 ? '<div class="pair-why"><h4>' + esc(t('ci_why')) + '</h4><p>' + rich(why2) + '</p>' + relInline((a.related || []).concat(b ? b.related || [] : [])) + '</div>' : ''));
    }
    return out.join('');
  }

  var WARN_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 22 20H2z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M12 10v4.5M12 17.2v.3" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>';
  function renderTeaser(it) {
    var post = it.post || null;
    var readings = pickArr(it, 'readings');
    var who = post ? ((lang === 'en' && post.who_en) ? post.who_en : post.who) : '';
    var platform = post ? ((lang === 'en' && post.platform_en) ? post.platform_en : post.platform) : '';
    var text = post ? ((lang === 'en' && post.text_en) ? post.text_en : post.text) : '';
    var tr = post && lang === 'zh' && post.text_zh && post.text_zh !== post.text ? post.text_zh : '';
    return '<article class="teaser" id="item-' + esc(it.id) + '">' +
      '<span class="teaser-flag">' + WARN_SVG + esc(t('tz_flag')) + '</span>' +
      '<h3>' + rich(pick(it, 'title')) + '</h3>' +
      (post ? '<div class="post"><div class="post-who"><span class="avatar" aria-hidden="true">' + esc((who || '?').trim().slice(-1)) + '</span><div><b>' + esc(who) + '</b><span>' +
        esc([pick(post, 'role'), platform, post.handle].filter(Boolean).join(' · ')) + '</span></div></div>' +
        (text ? '<p class="post-text">' + esc(text) + '</p>' : '') + (tr ? '<p class="post-tr">' + esc(t('quote_tr')) + '：' + esc(tr) + '</p>' : '') +
        (post.posted_at ? '<p class="post-meta">' + esc(t('tz_posted')) + ' ' + esc(post.posted_at) + '</p>' : '') + '</div>' : '') +
      (pick(it, 'summary') ? '<p class="teaser-sum">' + rich(pick(it, 'summary')) + '</p>' : '') +
      paras(pick(it, 'body')).map(function (p) { return '<p>' + rich(p) + '</p>'; }).join('') +
      miniNumbers(it.numbers, 2) +
      (readings.length ? '<div><span class="lbl">' + esc(t('tz_readings')) + '</span><div class="readings">' + readings.map(function (r) { return '<span>' + esc(r) + '</span>'; }).join('') + '</div></div>' : '') +
      (pick(it, 'why') ? '<div><span class="lbl">' + esc(t('tz_read')) + '</span><p>' + rich(pick(it, 'why')) + '</p></div>' : '') +
      (pick(it, 'verify') ? '<p class="verify"><b>' + esc(t('tz_verify')) + '：</b>' + esc(pick(it, 'verify')) + '</p>' : '') +
      (itemSources(it).length ? '<div class="flash-src">' + itemSources(it).map(function (s) { return srcLink(s) + (SRC_N[s.id] ? cite(s.id) : ''); }).join(' · ') + '</div>' : '') +
      relInline(it.related) +
      '</article>';
  }

  function renderSection(sec, n) {
    var kind = sec.kind;
    var items = sec.items || [];
    var deck = pick(sec, 'intro') || t('deck_' + kind);
    var title = pick(sec, 'title') || t('sec_' + kind);
    var body = '';
    if (kind === 'headline') body = items.map(renderHeadline).join('');
    else if (kind === 'brief') body = '<div class="briefs">' + items.map(renderBrief).join('') + '</div>';
    else if (kind === 'flash') body = items.length ? '<ol class="flash">' + items.map(renderFlash).join('') + '</ol>' : '<p class="weekday-note">' + esc(t('flash_weekend')) + '</p>';
    else if (kind === 'term') body = items.map(renderTerm).join('');
    else if (kind === 'cn_intl') body = renderCnIntl(items);
    else if (kind === 'teaser') body = '<div class="unverified" role="note"><span class="stamp">' + WARN_SVG + esc(t('tz_flag')) + '</span><p>' + esc(t('tz_banner')) + '</p></div><div class="teasers">' + items.map(renderTeaser).join('') + '</div>';
    else body = '<div class="briefs">' + items.map(renderBrief).join('') + '</div>';
    return '<section class="block" id="sec-' + esc(kind) + '" data-nav="' + esc(kind) + '"><div class="wrap">' + blockHead(n, kind, title, deck) + body + '</div></section>';
  }

  function renderStories() {
    CHARTS = {};
    // one block per kind (keeps anchors unique): sections of the same kind are merged in order
    var merged = [], byKind = {};
    (ISSUE.sections || []).forEach(function (sec) {
      if (!sec || !sec.kind) return;
      if (byKind[sec.kind]) { byKind[sec.kind].items = byKind[sec.kind].items.concat(sec.items || []); return; }
      byKind[sec.kind] = Object.assign({}, sec, { items: (sec.items || []).slice() });
      merged.push(byKind[sec.kind]);
    });
    var n = 3;
    var html = merged.filter(function (sec) {
      return !(sec.kind === 'flash' && !sec.items.length && !isWeekend());
    }).map(function (sec) { n += 1; return renderSection(sec, n); }).join('');
    $('#stories').innerHTML = html;
    return n;
  }

  function renderSources(n) {
    var groups = ['official', 'paper', 'media', 'community', 'social'];
    var by = {};
    SRC_ORDER.forEach(function (id) { var ty = SRC[id].type || 'media'; if (groups.indexOf(ty) < 0) ty = 'media'; (by[ty] = by[ty] || []).push(SRC[id]); });
    var html = blockHead(n, 'sources', t('sec_sources'), t('deck_sources')) + '<div class="srcgroups">' +
      groups.filter(function (g) { return by[g]; }).map(function (g) {
        return '<div class="srcgroup"><h3><span>' + esc(t('sgroup_' + g)) + '</span><span class="num">' + by[g].length + '</span></h3><ol class="srclist">' +
          by[g].map(function (s) {
            var ti = pick(s, 'title');
            var back = (CITED[s.id] || []).map(function (c) {
              return '<a href="#item-' + esc(c.id) + '">' + esc(t('nav_' + c.kind) + ' ' + c.n) + '</a>';
            }).join('、');
            return '<li id="src-' + esc(s.id) + '"><span class="src-n">' + SRC_N[s.id] + '</span><div>' +
              (s.url ? '<a class="src-name" href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer">' + esc(srcName(s)) + '</a>' : '<span class="src-name">' + esc(srcName(s)) + '</span>') +
              (ti ? '<div class="src-t">' + esc(ti) + '</div>' : '') +
              '<div class="src-m">' + esc([s.date, host(s.url)].filter(Boolean).join(' · ')) +
              (back ? ' · ' + esc(t('cited_in')) + ' ' + back : '') + '</div>' +
              '</div></li>';
          }).join('') + '</ol></div>';
      }).join('') + '</div>';
    $('#sources-root').innerHTML = html;
  }

  function renderAbout(n) {
    var meta = ISSUE.meta || {};
    var gen = '';
    if (meta.generated_at) {
      var m = String(meta.generated_at).match(/^(\d{4}-\d\d-\d\d)T(\d\d:\d\d)(?::\d\d(?:\.\d+)?)?(Z|[+-]\d\d:?\d\d)?$/);
      gen = m ? m[1] + ' ' + m[2] + (m[3] ? ' (UTC' + (m[3] === 'Z' ? '' : m[3]) + ')' : '') : String(meta.generated_at);
    }
    var rows = [
      [t('about_generated'), gen],
      [t('about_how'), pick(meta, 'how')],
      [t('about_file'), issueSrc],
      [t('about_contact'), pick(meta, 'contact')]
    ].filter(function (r) { return r[1]; });
    $('#about-root').innerHTML = blockHead(n, 'about', t('sec_about'), '') +
      '<div class="about"><div class="about-main"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 10.6v6M12 7.4v.4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>' +
      '<p>' + rich(pick(ISSUE, 'disclosure')) + '</p></div>' +
      (rows.length ? '<dl>' + rows.map(function (r) { return '<dt>' + esc(r[0]) + '</dt><dd>' + esc(r[1]) + '</dd>'; }).join('') + '</dl>' : '') + '</div>';
    $('#foot').innerHTML = '<div class="wrap"><span>' + esc(t('brand')) + ' · ' + esc(ISSUE.date) + (meta.issue_no ? ' · No.' + esc(meta.issue_no) : '') + ' · ' + esc(cardFoot()) + '</span><a href="#top">' + esc(t('foot_top')) + ' ↑</a></div>';
  }

  function renderMediaHeads() {
    var v = ISSUE.video, p = ISSUE.podcast;
    var vs = $('#sec-video'), ps = $('#sec-podcast');
    if (v && v.scenes && v.scenes.length) {
      var norm = window.FDVideo ? window.FDVideo.normalize(v) : v;
      $('#head-video').innerHTML = blockHead(2, 'video', pick(v, 'title') || t('sec_video'), t('deck_video', { d: durText(norm.duration) }));
      vs.hidden = false;
    } else vs.hidden = true;
    if (p && p.variants && p.variants.length) {
      var cur = players.podcast ? players.podcast.variant() : p.variants[0];
      $('#head-podcast').innerHTML = blockHead(3, 'podcast', t('title_podcast'), t('deck_podcast', { d: durText(cur.duration || p.duration || 0), n: p.variants.length }));
      ps.hidden = false;
    } else ps.hidden = true;
  }

  function renderNav() {
    var items = [['card', 'sec-card']];
    if (!$('#sec-video').hidden) items.push(['video', 'sec-video']);
    if (!$('#sec-podcast').hidden) items.push(['podcast', 'sec-podcast']);
    $$('#stories > section').forEach(function (s) { items.push([s.dataset.nav, s.id]); });
    items.push(['sources', 'sec-sources'], ['about', 'sec-about']);
    $('#secnav').innerHTML = items.map(function (x) { return '<a href="#' + x[1] + '" data-target="' + x[1] + '">' + esc(t('nav_' + x[0])) + '</a>'; }).join('');
    setupSpy();
  }

  /* ---------- charts (hand-written SVG, laid out in real pixels so text never scales) ---------- */
  function drawCharts() {
    $$('.chart-svg[data-chart]').forEach(function (box) {
      var chart = CHARTS[box.dataset.chart];
      if (!chart) return;
      var draw = function () {
        var W = Math.max(220, Math.floor(box.clientWidth));
        if (box._w === W && box._lang === lang) return;
        box._w = W; box._lang = lang;
        box.innerHTML = barSVG(chart, W);
      };
      draw();
      if (window.ResizeObserver && !box._ro) { box._ro = new ResizeObserver(function () { draw(); }); box._ro.observe(box); }
    });
  }
  function barSVG(chart, W) {
    var series = chart.series || [];
    var vals = series.map(function (s) { return Math.abs(+s.value || 0); });
    var vmax = Math.max.apply(null, vals.concat([0])) || 1;
    var max = +chart.max || vmax;
    var hlName = chart.highlight;
    var unit = (lang === 'en' && chart.unit_en != null) ? chart.unit_en : (chart.unit || '');
    var rowH = 62, barH = 18, labelY = 16, top = 2;
    var H = top + series.length * rowH - 10;
    var out = [];
    var aria = [];
    series.forEach(function (s, i) {
      var y = top + i * rowH;
      var label = (lang === 'en' && s.label_en) ? s.label_en : (s.label_zh || s.label || '');
      var dv = (lang === 'en' && s.value_en != null) ? s.value_en : s.value;
      var vt = joinUnit(dv, unit);
      var hl = hlName ? (s.label === hlName || s.label_en === hlName) : (vals[i] === vmax);
      var bw = Math.max(3, W * Math.min(1, vals[i] / max));
      aria.push(label + ' ' + vt);
      if (chart.max) out.push('<rect class="ct" x="0" y="' + (y + 26) + '" width="' + W + '" height="' + barH + '" rx="2"/>');
      out.push('<rect class="cb' + (hl ? ' hl' : '') + '" x="0" y="' + (y + 26) + '" width="' + bw.toFixed(1) + '" height="' + barH + '" rx="2"/>');
      out.push('<text class="cl" x="0" y="' + (y + labelY) + '">' + esc(label) + '</text>');
      out.push('<text class="cv' + (hl ? ' hl' : '') + '" x="' + W + '" y="' + (y + labelY + 1) + '" text-anchor="end">' + esc(vt) + '</text>');
    });
    out.push('<line class="cax" x1="0.5" y1="' + (top + 20) + '" x2="0.5" y2="' + (H + 2) + '"/>');
    return '<svg viewBox="0 0 ' + W + ' ' + (H + 4) + '" width="' + W + '" height="' + (H + 4) + '" role="img" aria-label="' + esc(pick(chart, 'title') + '：' + aria.join('，')) + '">' + out.join('') + '</svg>';
  }

  /* ===================== podcast player ===================== */
  var PICON = {
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M8 5.2v13.6L18.6 12z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M7 5h3.6v14H7zM13.4 5H17v14h-3.6z"/></svg>',
    back: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12a7 7 0 1 0 2.1-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M6.5 3.5v4h4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><text x="12.2" y="15.4" font-size="7" font-weight="700" text-anchor="middle" fill="currentColor" font-family="Arial">15</text></svg>',
    fwd: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 12a7 7 0 1 1-2.1-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M17.5 3.5v4h-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><text x="11.8" y="15.4" font-size="7" font-weight="700" text-anchor="middle" fill="currentColor" font-family="Arial">15</text></svg>'
  };
  var RATES = [1, 1.25, 1.5, 2, 0.8];

  function Podcast(root, pod) {
    this.root = root;
    this.pod = pod;
    this.variants = pod.variants || [];
    var saved = store.get('fd.podcast.variant', '');
    this.vi = Math.max(0, this.variants.map(function (v) { return v.id; }).indexOf(saved));
    this.rate = parseFloat(store.get('fd.podcast.rate', '1')) || 1;
    if (RATES.indexOf(this.rate) < 0) this.rate = 1;
    this.audio = new Audio();
    this.audio.preload = 'metadata';
    this.state = 'idle';
    this.build();
    this.bind();
    this.load(false, null);
  }
  var PP = Podcast.prototype;
  PP.variant = function () { return this.variants[this.vi] || {}; };
  PP.chapters = function () { var v = this.variant(); return (v.chapters && v.chapters.length ? v.chapters : this.pod.chapters) || []; };
  PP.duration = function () { var d = this.audio.duration; return (this.state === 'ok' && isFinite(d) && d > 0) ? d : (this.variant().duration || this.pod.duration || 0); };
  PP.chapterAt = function (tm) { var ch = this.chapters(), i = 0; for (var k = 0; k < ch.length; k++) if (ch[k].start <= tm + 0.05) i = k; return i; };
  PP.build = function () {
    this.root.innerHTML =
      '<div class="pod">' +
        '<div class="pod-head"><span class="pod-vlabel"></span><span class="pod-ai"></span></div>' +
        '<div class="pod-vars" role="group"></div>' +
        '<p class="pod-note"><span class="pod-note-t"></span> <a class="pod-transcript" target="_blank" rel="noopener"></a></p>' +
        '<div class="pod-main"><button class="pod-play" type="button"></button>' +
          '<div class="pod-track"><div class="pod-now"><span class="pod-now-l"></span><b></b></div>' +
          '<div class="pod-scrub"><input class="range" type="range" min="0" step="0.1" value="0"><div class="pod-ticks" aria-hidden="true"></div></div>' +
          '<div class="pod-times"><span class="cur">0:00</span><span class="dur">0:00</span></div></div></div>' +
        '<div class="pod-tools"><button class="ibtn" type="button" data-act="back">' + PICON.back + '</button><button class="ibtn" type="button" data-act="fwd">' + PICON.fwd + '</button><button class="pod-rate" type="button"></button></div>' +
        '<div class="pod-msg" hidden></div>' +
        '<div class="pod-chwrap"><h4 class="pod-ch-h"></h4><ol class="pod-chapters"></ol></div>' +
      '</div>';
    var q = this.root.querySelector.bind(this.root);
    this.el = {
      seg: q('.pod-vars'), vlabel: q('.pod-vlabel'), ai: q('.pod-ai'), note: q('.pod-note'), noteT: q('.pod-note-t'), tr: q('.pod-transcript'), play: q('.pod-play'),
      nowL: q('.pod-now-l'), nowT: q('.pod-now b'), range: q('.range'), ticks: q('.pod-ticks'), cur: q('.cur'), dur: q('.dur'),
      back: q('[data-act="back"]'), fwd: q('[data-act="fwd"]'), rate: q('.pod-rate'), msg: q('.pod-msg'), chH: q('.pod-ch-h'), list: q('.pod-chapters')
    };
    this.renderStatic();
  };
  PP.renderStatic = function () {
    var self = this, e = this.el, v = this.variant();
    e.vlabel.textContent = t('p_variant');
    e.seg.setAttribute('aria-label', t('p_variant'));
    e.seg.innerHTML = this.variants.map(function (x, i) {
      return '<button type="button" class="pod-var" data-i="' + i + '" aria-pressed="' + (i === self.vi ? 'true' : 'false') + '">' + esc(pick(x, 'label') || x.id) + (x.duration ? ' <span class="num">' + fmtTime(x.duration) + '</span>' : '') + '</button>';
    }).join('');
    e.ai.textContent = t('p_ai');
    e.noteT.textContent = pick(v, 'note');
    var tr = v.transcript || null;
    e.tr.hidden = !tr;
    if (tr) { e.tr.href = asset(tr.href); e.tr.textContent = (pick(tr, 'label') || t('p_transcript')) + ' ↗'; }
    e.note.hidden = !pick(v, 'note') && !tr;
    e.nowL.textContent = t('p_now');
    e.back.setAttribute('aria-label', t('p_back')); e.back.title = t('p_back');
    e.fwd.setAttribute('aria-label', t('p_fwd')); e.fwd.title = t('p_fwd');
    e.rate.setAttribute('aria-label', t('p_rate'));
    e.rate.textContent = this.rate + '×';
    e.range.setAttribute('aria-label', t('p_seek'));
    e.chH.textContent = t('p_chapters');
    var dur = this.duration() || 1;
    e.list.innerHTML = this.chapters().map(function (c, i) {
      return '<li data-i="' + i + '"><button type="button"><span class="i">' + pad2(i + 1) + '</span><span class="ti">' + esc(pick(c, 'title')) + '</span><span class="tm">' + fmtTime(c.start) + '</span></button></li>';
    }).join('');
    e.ticks.innerHTML = this.chapters().slice(1).map(function (c) { return '<i style="left:' + (c.start / dur * 100).toFixed(3) + '%"></i>'; }).join('');
    this.sync();
  };
  PP.sync = function () {
    var e = this.el, a = this.audio;
    var tm = a.currentTime || 0, dur = this.duration() || 0;
    var playing = !a.paused && !a.ended;
    e.play.innerHTML = playing ? PICON.pause : PICON.play;
    e.play.setAttribute('aria-label', playing ? t('p_pause') : t('p_play'));
    e.play.disabled = this.state === 'error';
    e.range.disabled = this.state === 'error';
    e.range.max = String(dur || 1);
    if (!this.scrubbing) e.range.value = String(tm);
    e.range.style.setProperty('--pct', (dur ? tm / dur * 100 : 0).toFixed(3) + '%');
    e.range.setAttribute('aria-valuetext', fmtTime(tm) + ' / ' + fmtTime(dur));
    e.cur.textContent = fmtTime(tm);
    e.dur.textContent = fmtTime(dur);
    var ci = this.chapterAt(tm);
    var ch = this.chapters()[ci];
    e.nowT.textContent = ch ? pick(ch, 'title') : '';
    $$('li', e.list).forEach(function (li) { li.classList.toggle('on', +li.dataset.i === ci); });
    if (this.state === 'error') { e.msg.hidden = false; e.msg.textContent = t('p_missing'); }
    else e.msg.hidden = true;
  };
  PP.load = function (autoplay, seekTo) {
    var v = this.variant();
    this.state = v.file ? 'loading' : 'error';
    this.pendingSeek = seekTo;
    this.wantPlay = autoplay;
    try { this.audio.pause(); } catch (e) { /* ignore */ }
    if (v.file) { this.audio.src = asset(v.file); this.audio.load(); }
    else this.audio.removeAttribute('src');
    this.sync();
  };
  PP.play = function () {
    var self = this;
    if (this.state === 'error') { this.sync(); return; }
    this.audio.playbackRate = this.rate;
    var pr = this.audio.play();
    if (pr && pr.catch) pr.catch(function () { self.sync(); });
    document.dispatchEvent(new CustomEvent('fd:play', { detail: { id: 'podcast' } }));
    this.media();
  };
  PP.seekTo = function (tm, andPlay) {
    if (this.state === 'error') { this.sync(); return; }
    if (this.state !== 'ok') { this.pendingSeek = tm; this.wantPlay = !!andPlay; return; }
    this.audio.currentTime = Math.max(0, Math.min(tm, this.duration()));
    if (andPlay) this.play();
    this.sync();
  };
  PP.switchTo = function (i) {
    if (i === this.vi || !this.variants[i]) return;
    var a = this.audio;
    var playing = !a.paused && !a.ended;
    var ci = this.chapterAt(a.currentTime || 0);
    var progressed = (a.currentTime || 0) > 0.5;
    this.vi = i;
    store.set('fd.podcast.variant', this.variants[i].id);
    var ch = this.chapters()[ci];
    this.load(playing, progressed && ch ? ch.start : null);
    this.renderStatic();
    renderMediaHeads();
  };
  PP.media = function () {
    if (!('mediaSession' in navigator)) return;
    var self = this;
    try {
      navigator.mediaSession.metadata = new window.MediaMetadata({ title: t('brand') + ' · ' + ISSUE.date, artist: pick(this.variant(), 'label'), album: t('brand') });
      navigator.mediaSession.setActionHandler('play', function () { self.play(); });
      navigator.mediaSession.setActionHandler('pause', function () { self.audio.pause(); });
      navigator.mediaSession.setActionHandler('seekbackward', function () { self.seekTo(self.audio.currentTime - 15); });
      navigator.mediaSession.setActionHandler('seekforward', function () { self.seekTo(self.audio.currentTime + 15); });
      navigator.mediaSession.setActionHandler('previoustrack', function () { var c = self.chapterAt(self.audio.currentTime); var ch = self.chapters()[Math.max(0, c - 1)]; if (ch) self.seekTo(ch.start, true); });
      navigator.mediaSession.setActionHandler('nexttrack', function () { var c = self.chapterAt(self.audio.currentTime); var ch = self.chapters()[c + 1]; if (ch) self.seekTo(ch.start, true); });
    } catch (e) { /* optional */ }
  };
  PP.bind = function () {
    var self = this, e = this.el, a = this.audio;
    a.addEventListener('loadedmetadata', function () {
      self.state = 'ok';
      a.playbackRate = self.rate;
      if (self.pendingSeek != null) {
        var target = self.pendingSeek;
        self.pendingSeek = null;
        try { a.currentTime = target; } catch (err) { /* ignore */ }
        // some servers can't seek before the file is buffered and playback restarts at 0: try once more when it can play through
        var retry = function () {
          a.removeEventListener('canplaythrough', retry);
          if ((a.currentTime || 0) < Math.min(3, target - 1)) { try { a.currentTime = target; } catch (err) { /* ignore */ } }
        };
        a.addEventListener('canplaythrough', retry);
      }
      if (self.wantPlay) { self.wantPlay = false; self.play(); }
      self.renderStatic();
      renderMediaHeads();
    });
    a.addEventListener('error', function () { if (!a.getAttribute('src')) return; self.state = 'error'; self.sync(); });
    ['timeupdate', 'play', 'pause', 'ended', 'seeked'].forEach(function (ev) { a.addEventListener(ev, function () { self.sync(); }); });
    e.play.addEventListener('click', function () { if (a.paused || a.ended) self.play(); else a.pause(); });
    e.back.addEventListener('click', function () { self.seekTo((a.currentTime || 0) - 15); });
    e.fwd.addEventListener('click', function () { self.seekTo((a.currentTime || 0) + 15); });
    e.rate.addEventListener('click', function () {
      self.rate = RATES[(RATES.indexOf(self.rate) + 1) % RATES.length];
      a.playbackRate = self.rate;
      store.set('fd.podcast.rate', String(self.rate));
      e.rate.textContent = self.rate + '×';
    });
    e.seg.addEventListener('click', function (ev) { var b = ev.target.closest('button'); if (b) self.switchTo(+b.dataset.i); });
    e.list.addEventListener('click', function (ev) {
      var li = ev.target.closest('li');
      if (!li) return;
      var ch = self.chapters()[+li.dataset.i];
      if (ch) self.seekTo(ch.start, true);
    });
    e.range.addEventListener('pointerdown', function () { self.scrubbing = true; });
    e.range.addEventListener('pointerup', function () { self.scrubbing = false; });
    e.range.addEventListener('input', function () { if (self.state === 'ok') { a.currentTime = parseFloat(e.range.value) || 0; self.sync(); } });
    e.range.addEventListener('change', function () { self.scrubbing = false; });
    document.addEventListener('fd:play', function (ev) { if (ev.detail && ev.detail.id !== 'podcast' && !a.paused) a.pause(); });
  };
  PP.setLang = function () { this.renderStatic(); };

  /* ===================== day card → PNG (Canvas 2D; no libraries) ===================== */
  function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function loadImage(src) {
    return new Promise(function (resolve, reject) {
      var im = new Image();
      im.decoding = 'async';
      im.onload = function () { resolve(im); };
      im.onerror = function () { reject(new Error('image')); };
      im.src = src;
    });
  }
  var OPEN_PUNCT = '（《「『“‘([{';
  var CLOSE_PUNCT = '，。、；：？！）》」』”’…—,.;:?!)]}%';
  function wrapLines(ctx, text, maxW, maxLines) {
    var tokens = String(text || '').match(/[㐀-鿿豈-﫿　-〿＀-￯“”‘’…—]|[^\s㐀-鿿豈-﫿　-〿＀-￯“”‘’…—]+\s*|\s+/g) || [];
    var lines = [], line = '';
    for (var i = 0; i < tokens.length; i++) {
      var tok = tokens[i];
      if (!line && /^\s+$/.test(tok)) continue;
      var test = line + tok;
      if (ctx.measureText(test.replace(/\s+$/, '')).width <= maxW || !line) { line = test; continue; }
      if (CLOSE_PUNCT.indexOf(tok.charAt(0)) >= 0) { line = test; continue; } // 避头：标点不放行首
      var carry = '';
      if (OPEN_PUNCT.indexOf(line.slice(-1)) >= 0) { carry = line.slice(-1); line = line.slice(0, -1); } // 避尾：开括号不留行尾
      lines.push(line.replace(/\s+$/, ''));
      line = carry + tok.replace(/^\s+/, '');
    }
    if (line.trim()) lines.push(line.replace(/\s+$/, ''));
    // no one-character last line in Chinese: pull a character or two down from the line above
    if (lines.length >= 2) {
      var n = lines.length, last = lines[n - 1], prev = lines[n - 2];
      var core = last.replace(/[\s，。、；：？！）》」』”’…—,.;:?!)]/g, '');
      if (core.length < 2 && /[㐀-鿿]$/.test(prev)) {
        var take = (core.length === 0 && /[㐀-鿿]{2}$/.test(prev)) ? 2 : 1;
        lines[n - 2] = prev.slice(0, -take).replace(/\s+$/, '');
        lines[n - 1] = prev.slice(-take) + last;
      }
    }
    if (maxLines && lines.length > maxLines) {
      lines = lines.slice(0, maxLines);
      var last = lines[maxLines - 1];
      while (last.length && ctx.measureText(last + '…').width > maxW) last = last.slice(0, -1);
      lines[maxLines - 1] = last + '…';
    }
    return lines;
  }
  function spaced(ctx, text, x, y, sp, align) {
    var chars = String(text).split('');
    var w = chars.reduce(function (a, c) { return a + ctx.measureText(c).width + sp; }, -sp);
    var cx = align === 'right' ? x - w : x;
    var keep = ctx.textAlign;
    ctx.textAlign = 'left';
    chars.forEach(function (c) { ctx.fillText(c, cx, y); cx += ctx.measureText(c).width + sp; });
    ctx.textAlign = keep;
    return w;
  }
  function rr(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  function patternArt(ctx, x, y, w, h, col) {
    ctx.fillStyle = col.plate; ctx.fillRect(x, y, w, h);
    var cx = x + w * 0.65, hy = y + h * 0.66;
    ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, hy - y); ctx.clip();
    ctx.strokeStyle = '#F4EFE4';
    [0.12, 0.2, 0.29, 0.39, 0.5].forEach(function (r, i) { ctx.globalAlpha = 1 - i * 0.18; ctx.lineWidth = 3 - i * 0.4; ctx.beginPath(); ctx.arc(cx, hy, w * r, 0, Math.PI * 2); ctx.stroke(); });
    ctx.restore(); ctx.globalAlpha = 1;
    ctx.fillStyle = '#F4EFE4'; ctx.beginPath(); ctx.arc(cx, hy, w * 0.07, Math.PI, 0); ctx.fill();
    ctx.fillRect(x, hy - 1.5, w, 3);
  }
  function drawCard(withImage) {
    var dc = ISSUE.daily_card || {}, meta = ISSUE.meta || {};
    var col = { card: cssVar('--paper-2'), page: cssVar('--paper'), ink: cssVar('--ink'), ink2: cssVar('--ink-2'), ink3: cssVar('--ink-3'), rule: cssVar('--rule'), rule2: cssVar('--rule-2'), accent: cssVar('--accent'), plate: cssVar('--plate') || '#1C2E95' };
    var F = { sans: cssVar('--font-sans'), serif: cssVar('--font-serif'), latin: cssVar('--font-latin-serif'), num: cssVar('--font-num') };
    var im = normImage(dc.image);
    var imgP = (withImage && im && im.src) ? loadImage(asset(im.src)).catch(function () { return null; }) : Promise.resolve(null);
    return imgP.then(function (img) {
      var W = 1080, P = 84, CW = W - P * 2;
      var p = String(ISSUE.date || '').split('-');
      var day = pad2(+p[2] || 0);
      var heads = (dc.headlines || []).slice(0, 3).map(pickL);
      var term = dc.term || {};
      var wd = lang === 'en' ? ISSUE.weekday_en : ISSUE.weekday_zh;
      var wd2 = lang === 'en' ? ISSUE.weekday_zh : String(ISSUE.weekday_en || '').toUpperCase();
      var ed = [pick(meta, 'edition'), meta.issue_no ? 'No.' + meta.issue_no : ''].filter(Boolean).join(' · ');
      var plan = function (ctx, draw) {
        var font = function (w, s, f, st) { ctx.font = (st || 'normal') + ' ' + w + ' ' + s + 'px ' + f; };
        var hline = function (x1, x2, y, c, lw) { ctx.fillStyle = c; ctx.fillRect(x1, y - lw / 2, x2 - x1, lw); };
        var perf = function (y) {
          ctx.fillStyle = col.rule2;
          for (var x = P - 30; x < W - P + 30; x += 12) ctx.fillRect(x, y - 1.5, 4, 3);
          ctx.fillStyle = col.page;
          [0, W].forEach(function (cx) { ctx.beginPath(); ctx.arc(cx, y, 22, 0, Math.PI * 2); ctx.fill(); });
        };
        var label = function (a, b, y) {
          font(700, 26, F.sans); ctx.fillStyle = col.accent;
          var w = spaced(ctx, a, P, y, 3);
          font(700, 18, F.sans); ctx.fillStyle = col.ink3;
          spaced(ctx, b, P + w + 18, y, 4);
        };
        ctx.textBaseline = 'alphabetic';
        ctx.textAlign = 'left';
        if (draw) { ctx.fillStyle = col.card; ctx.fillRect(0, 0, W, ctx.canvas.height); }
        // top band
        var y = 72;
        if (draw) {
          ctx.fillStyle = col.accent; rr(ctx, P, y - 26, 26, 26, 4); ctx.fill();
          ctx.fillStyle = col.card; ctx.fillRect(P + 6, y - 9, 14, 3.5);
          font(700, 34, F.serif); ctx.fillStyle = col.ink; ctx.fillText(t('brand'), P + 42, y);
          font(600, 22, F.sans); ctx.fillStyle = col.ink3; spaced(ctx, ed, W - P, y, 2, 'right');
        }
        y = 112;
        if (draw) hline(0, W, y, col.rule, 2);
        // date
        font(700, 300, F.num);
        var dw = ctx.measureText(day).width;
        var base = y + 50 + 216;
        if (draw) { ctx.fillStyle = col.accent; ctx.fillText(day, P - 10, base); }
        var x2 = P + dw + 30;
        if (draw) {
          font(600, 34, F.sans); ctx.fillStyle = col.ink2; ctx.fillText(fmtDate(false), x2, base - 150);
          font(700, 80, F.serif); ctx.fillStyle = col.ink; ctx.fillText(wd || '', x2, base - 56);
          font(700, 24, F.sans); ctx.fillStyle = col.ink3; spaced(ctx, wd2 || '', x2, base, 6);
        }
        y = base + 46;
        // illustration
        var ih = Math.round(CW * 0.5);
        if (draw) {
          ctx.save(); rr(ctx, P, y, CW, ih, 16); ctx.clip();
          if (img) {
            var iw = img.naturalWidth || img.width || 1600, iH = img.naturalHeight || img.height || 900;
            var sc = Math.max(CW / iw, ih / iH), sw = CW / sc, sh = ih / sc;
            ctx.drawImage(img, (iw - sw) / 2, (iH - sh) / 2, sw, sh, P, y, CW, ih);
          } else patternArt(ctx, P, y, CW, ih, col);
          ctx.restore();
        }
        y += ih + 52;
        if (draw) perf(y);
        y += 62;
        if (draw) label(t('three'), t('three_alt'), y);
        y += 26;
        heads.forEach(function (h, i) {
          font(700, 40, F.serif);
          var lines = wrapLines(ctx, h, CW - 90, 2);
          y += 54;
          if (draw) {
            font(700, 44, F.num); ctx.fillStyle = col.accent; ctx.fillText(pad2(i + 1), P, y);
            font(700, 40, F.serif); ctx.fillStyle = col.ink;
            lines.forEach(function (ln, k) { ctx.fillText(ln, P + 90, y + k * 56); });
          }
          y += (lines.length - 1) * 56 + 26;
          if (draw && i < heads.length - 1) hline(P + 90, W - P, y, col.rule, 1.5);
        });
        y += 30;
        if (draw) perf(y);
        y += 62;
        if (draw) label(t('term'), t('term_alt'), y);
        y += 96;
        font(700, 76, F.serif);
        var zw = ctx.measureText(term.zh || '').width;
        if (draw) {
          ctx.fillStyle = col.ink; ctx.fillText(term.zh || '', P, y);
          font(400, 50, F.latin, 'italic'); ctx.fillStyle = col.accent; ctx.fillText(term.en || '', P + zw + 26, y);
        }
        font(400, 31, F.sans);
        var ex = wrapLines(ctx, pick(term, 'explain'), CW, 3);
        y += 30;
        ex.forEach(function (ln, k) { if (draw) { ctx.fillStyle = col.ink2; ctx.fillText(ln, P, y + 32 + k * 48); } });
        y += 32 + (ex.length - 1) * 48 + 50;
        if (draw) hline(0, W, y, col.rule, 2);
        y += 52;
        if (draw) {
          font(500, 23, F.sans); ctx.fillStyle = col.ink3; ctx.fillText(cardFoot(), P, y);
          ctx.textAlign = 'right'; font(700, 24, F.num); ctx.fillText(meta.site || '', W - P, y); ctx.textAlign = 'left';
        }
        return y + 44;
      };
      var probe = document.createElement('canvas').getContext('2d');
      var H = Math.ceil(plan(probe, false));
      var canvas = document.createElement('canvas');
      canvas.width = W;
      canvas.height = Math.max(1350, H);
      plan(canvas.getContext('2d'), true);
      return canvas;
    });
  }
  function toBlob(canvas) {
    return new Promise(function (resolve, reject) {
      try { canvas.toBlob(function (b) { if (b) resolve(b); else reject(new Error('empty')); }, 'image/png'); } catch (e) { reject(e); }
    });
  }
  function exportCard() {
    var btn = $('#dc-save');
    var label = btn.querySelector('span');
    btn.disabled = true;
    label.textContent = t('saving');
    var fellBack = false;
    return drawCard(true).then(toBlob).catch(function (err) {
      if (err && (err.name === 'SecurityError' || /taint|insecure/i.test(err.message || ''))) {
        fellBack = true;
        return drawCard(false).then(toBlob);
      }
      throw err;
    }).then(function (blob) {
      showShare(blob, fellBack);
    }).catch(function (err) {
      console.error(err);
      window.alert(t('save_fail', { e: (err && err.message) || err }));
    }).then(function () {
      btn.disabled = false;
      label.textContent = t('save');
    });
  }
  var shareURL = null;
  function showShare(blob, fellBack) {
    var dlg = $('#shareDlg');
    if (shareURL) URL.revokeObjectURL(shareURL);
    shareURL = URL.createObjectURL(blob);
    var name = 'frontier-daily-' + ISSUE.date + (lang === 'en' ? '-en' : '') + '.png';
    var file = null;
    try { file = new File([blob], name, { type: 'image/png' }); } catch (e) { file = null; }
    var canShare = !!(file && navigator.canShare && navigator.share && navigator.canShare({ files: [file] }));
    dlg.innerHTML =
      '<div class="share-h"><span>' + esc(t('share_title')) + '</span><button class="ibtn" type="button" data-close aria-label="' + esc(t('share_close')) + '"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button></div>' +
      '<div class="share-body"><div class="share-img"><img alt="" src="' + shareURL + '"></div>' +
      '<p class="share-note' + (fellBack ? ' warn' : '') + '">' + esc(fellBack ? t('share_taint') : t('share_note')) + '</p></div>' +
      '<div class="share-actions"><a class="btn btn-primary" href="' + shareURL + '" download="' + esc(name) + '">' + esc(t('share_download')) + '</a>' +
      (canShare ? '<button class="btn" type="button" data-share>' + esc(t('share_share')) + '</button>' : '') +
      '<button class="btn" type="button" data-close>' + esc(t('share_close')) + '</button></div>';
    $$('[data-close]', dlg).forEach(function (b) { b.addEventListener('click', function () { dlg.close(); }); });
    var sb = $('[data-share]', dlg);
    if (sb) sb.addEventListener('click', function () { navigator.share({ files: [file], title: t('brand') + ' · ' + ISSUE.date }).catch(function () { /* cancelled */ }); });
    if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
  }

  /* ===================== theme & language ===================== */
  var THEME_ICON = {
    auto: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/></svg>',
    light: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 2.8v2.4M12 18.8v2.4M2.8 12h2.4M18.8 12h2.4M5.5 5.5l1.7 1.7M16.8 16.8l1.7 1.7M5.5 18.5l1.7-1.7M16.8 7.2l1.7-1.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    dark: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19.5 14.6A8 8 0 0 1 9.4 4.5a8 8 0 1 0 10.1 10.1z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>'
  };
  var theme = store.get('fd.theme', 'auto');
  if (['auto', 'light', 'dark'].indexOf(theme) < 0) theme = 'auto';
  function applyTheme() {
    if (theme === 'auto') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', theme);
  }
  function syncThemeBtn() {
    var b = $('#themeBtn');
    if (!b) return;
    b.innerHTML = THEME_ICON[theme];
    b.setAttribute('aria-label', t('theme_' + theme));
    b.title = t('theme_' + theme);
  }
  // keep the reader's place across a re-render: remember the first visible block and its offset
  function rememberPlace() {
    var head = $('.topbar').getBoundingClientRect().bottom;
    var blocks = $$('#main [id^="sec-"], #main [id^="item-"]');
    for (var i = 0; i < blocks.length; i++) {
      var r = blocks[i].getBoundingClientRect();
      if (r.bottom > head + 8) return { id: blocks[i].id, offset: r.top };
    }
    return null;
  }
  function restorePlace(place) {
    if (!place) return;
    var el = document.getElementById(place.id);
    if (el) window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - place.offset);
  }
  function setLang(next) {
    if (next === lang) return;
    var place = rememberPlace();
    lang = next;
    store.set('fd.lang', lang);
    renderStatic();
    if (players.video) players.video.setLang();
    if (players.podcast) players.podcast.setLang();
    restorePlace(place);
  }
  /* 稿件版本: day card, video and text switch together; the podcast keeps playing whatever version was chosen */
  function setEdition(id) {
    if (id === EDITION) return;
    var place = rememberPlace();
    EDITION = id;
    store.set('fd.edition', id);
    applyEdition();
    renderStatic();
    mountVideo();
    if (players.podcast) renderMediaHeads();
    restorePlace(place);
  }
  function mountVideo() {
    if (players.video && players.video.destroy) players.video.destroy();
    players.video = null;
    if (ISSUE.video && ISSUE.video.scenes && ISSUE.video.scenes.length && window.FDVideo) {
      players.video = window.FDVideo.mount($('#video-root'), ISSUE.video, videoCtx());
    } else $('#video-root').innerHTML = '';
  }

  /* ===================== scroll spy ===================== */
  // the highlighted chip is the last section whose top has passed just below the sticky header
  var spyTick = 0;
  function setupSpy() {
    var run = function () {
      spyTick = 0;
      var links = $$('#secnav a');
      if (!links.length) return;
      var line = (parseInt(cssVar('--sticky'), 10) || 92) + 24;
      var cur = links[0];
      links.forEach(function (a) {
        var el = document.getElementById(a.dataset.target);
        if (el && el.getBoundingClientRect().top <= line) cur = a;
      });
      if (cur.classList.contains('on')) return;
      links.forEach(function (a) { a.classList.toggle('on', a === cur); });
      var nav = $('#secnav');
      if (nav.scrollWidth > nav.clientWidth) {
        var left = cur.offsetLeft - nav.clientWidth / 2 + cur.offsetWidth / 2;
        try { nav.scrollTo({ left: left, behavior: 'smooth' }); } catch (e) { nav.scrollLeft = left; }
      }
    };
    if (!setupSpy.bound) {
      setupSpy.bound = true;
      window.addEventListener('scroll', function () { if (!spyTick) spyTick = requestAnimationFrame(run); }, { passive: true });
      window.addEventListener('resize', function () { if (!spyTick) spyTick = requestAnimationFrame(run); });
    }
    run();
  }

  /* ===================== boot ===================== */
  function renderStatic() {
    buildIndex();
    renderChrome();
    renderCard();
    renderMediaHeads();
    var n = renderStories();
    renderSources(n + 1);
    renderAbout(n + 2);
    renderNav();
    drawCharts();
  }
  function videoCtx() {
    return {
      lang: function () { return lang; },
      t: t,
      pick: pick,
      asset: asset,
      normImage: normImage,
      host: host,
      store: store
    };
  }
  function renderFatal(list) {
    $('#main').innerHTML = '<div class="fatal"><h1>' + esc(t('fatal_title')) + '</h1><p>' +
      esc(t('fatal_body', { list: list.join('、') })) + '</p></div>';
  }
  function boot() {
    applyTheme();
    $$('.lang button').forEach(function (b) { b.addEventListener('click', function () { setLang(b.dataset.lang); }); });
    $('#themeBtn').addEventListener('click', function () {
      theme = theme === 'auto' ? 'light' : theme === 'light' ? 'dark' : 'auto';
      store.set('fd.theme', theme);
      applyTheme();
      syncThemeBtn();
    });
    $('#dc-save').addEventListener('click', exportCard);
    $('#shareDlg').addEventListener('click', function (e) { if (e.target === e.currentTarget) e.currentTarget.close(); });
    syncThemeBtn();
    loadIssue().then(function (r) {
      if (!r.issue) { renderChrome0(); renderFatal(r.list || []); return; }
      RAW = r.issue;
      issueSrc = r.src;
      BASE = RAW.asset_base != null ? RAW.asset_base : (r.src.indexOf('/') >= 0 ? r.src.slice(0, r.src.lastIndexOf('/') + 1) : '');
      applyEdition();
      renderStatic();
      mountVideo();
      if (ISSUE.podcast && ISSUE.podcast.variants && ISSUE.podcast.variants.length) {
        players.podcast = new Podcast($('#podcast-root'), ISSUE.podcast);
        renderMediaHeads();
      }
      if (window.location.hash) {
        var tgt = document.getElementById(window.location.hash.slice(1));
        if (tgt) tgt.scrollIntoView();
      }
    });
  }
  function renderChrome0() {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    $('.brand-zh').textContent = t('brand');
    $('.brand-en').textContent = t('brand_alt');
    $$('.lang button').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.lang === lang ? 'true' : 'false'); });
  }

  window.FD = { players: players, store: store, version: '0.2', setEdition: function (id) { setEdition(id); }, edition: function () { return EDITION; } };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
