/* frontier-daily · video.js
 * 网页内嵌的 HTML 动画"视频"：播放旁白音频，画面按时间轴切换场景、逐步出现元素。
 *
 * 画面完全由时间 t 决定（render 读 t，算出每个元素的进度），所以：
 *   - 有音频时，t = 音频的当前时间，画面天然与旁白同步；
 *   - 没有音频或音频加载失败时，自动进入"无声预览"，t 由页面自己的时钟推进；
 *   - 拖动进度条、暂停、逐场景查看都只是改 t；以后要逐帧导出 MP4，也是逐个 t 截图。
 *
 * 用法：FDVideo.mount(容器元素, issue.video, ctx)；ctx 由 app.js 提供（语言、取字段、资源路径等）。
 */
(function () {
  'use strict';

  var clamp = function (v, a, b) { return Math.min(b, Math.max(a, v)); };
  var easeOut = function (x) { return 1 - Math.pow(1 - x, 3); };
  var reduceMotion = function () { return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var pad2 = function (n) { return String(n).padStart(2, '0'); };
  var fmt = function (sec) {
    sec = Math.max(0, Math.floor((sec || 0) + 1e-6));
    return Math.floor(sec / 60) + ':' + pad2(sec % 60);
  };
  var isCJK = function (ch) { return /[㐀-鿿豈-﫿]/.test(ch); };

  var ICON = {
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M8 5.2v13.6L18.6 12z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M7 5h3.6v14H7zM13.4 5H17v14h-3.6z"/></svg>',
    replay: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" d="M4.6 12a7.4 7.4 0 1 0 2.2-5.3M4.6 4.4v3.9h3.9"/></svg>',
    prev: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M6 5h2.2v14H6zM19 5.4v13.2L9.6 12z"/></svg>',
    next: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M15.8 5H18v14h-2.2zM5 5.4v13.2L14.4 12z"/></svg>',
    cc: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5.5" width="18" height="13" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M10.6 10.3a2.1 2.1 0 1 0 0 3.4M16.6 10.3a2.1 2.1 0 1 0 0 3.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    sound: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M4 9.4h3.4L12 5.8v12.4l-4.6-3.6H4z"/><path d="M15.4 9a4.2 4.2 0 0 1 0 6M17.9 6.6a7.6 7.6 0 0 1 0 10.8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    mute: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M4 9.4h3.4L12 5.8v12.4l-4.6-3.6H4z"/><path d="M15.5 9.5l5 5m0-5l-5 5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    full: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    warn: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 22 20H2z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 10v4.5M12 17.2v.3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
  };

  /* ---------- numbers: "65.2%" → count-up from 0 ---------- */
  function parseNum(value) {
    var s = String(value == null ? '' : value).trim();
    var m = s.match(/^([^\d-]*?)(-?\d[\d,]*(?:\.\d+)?)(.*)$/);
    if (!m || /\d/.test(m[3])) return null; // "$2 / $10" 这类含多个数字的不做滚动
    var raw = m[2].replace(/,/g, '');
    return { pre: m[1], num: parseFloat(raw), dec: (raw.split('.')[1] || '').length, suf: m[3], comma: m[2].indexOf(',') >= 0 };
  }
  function fmtNum(p, v) {
    var s = p.comma ? v.toLocaleString('en-US', { minimumFractionDigits: p.dec, maximumFractionDigits: p.dec }) : v.toFixed(p.dec);
    return p.pre + s + p.suf;
  }
  function numHTML(text) {
    var out = esc(text);
    return out.replace(/[^\d.,\-\s]+/g, function (u, off) {
      return '<span class="u' + (off === 0 ? ' pre' : '') + '">' + u + '</span>';
    });
  }
  function joinUnit(value, unit) {
    if (unit == null || unit === '') return String(value);
    return String(value) + (isCJK(String(unit).charAt(0)) ? ' ' : '') + unit;
  }

  /* ---------- timeline helpers (for pipeline output that has no timings yet) ---------- */
  function weightLen(text) {
    var w = 0;
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      if (isCJK(ch)) w += 1;
      else if (/\d/.test(ch)) w += 1.1;
      else if (/[A-Za-z]/.test(ch)) w += 0.3;
      else if (/[，。；：！？,.;:!?]/.test(ch)) w += 0.6;
      else w += 0.15;
    }
    return w;
  }
  function splitClauses(text, maxW) {
    if (!text) return [];
    var parts = [], buf = '';
    String(text).split('').forEach(function (ch) {
      buf += ch;
      if ('，。；：！？,.;:!?'.indexOf(ch) >= 0) { parts.push(buf); buf = ''; }
    });
    if (buf) parts.push(buf);
    var out = [], cur = '';
    parts.forEach(function (p) {
      if (cur && weightLen(cur + p) > (maxW || 24)) { out.push(cur.trim()); cur = p; } else cur += p;
    });
    if (cur.trim()) out.push(cur.trim());
    return out;
  }
  function normalize(video) {
    var v = Object.assign({}, video || {});
    var CPS = 4.6; // 估算语速：约每秒 4.6 个汉字（约 280 字／分钟）
    var cursor = 0, estimated = false;
    v.scenes = (v.scenes || []).map(function (sc0) {
      var sc = Object.assign({}, sc0);
      var est = Math.max(3, weightLen(sc.narration_zh || sc.heading_zh || '') / CPS + 0.8);
      if (typeof sc.start !== 'number') { sc.start = cursor; estimated = true; }
      if (typeof sc.end !== 'number') { sc.end = sc.start + est; estimated = true; }
      cursor = sc.end;
      return sc;
    }).sort(function (a, b) { return a.start - b.start; });
    var last = v.scenes[v.scenes.length - 1];
    v.duration = Math.max(+v.duration || 0, last ? last.end : 0) || 1;
    if (Array.isArray(v.subtitles) && v.subtitles.length) {
      v.subtitles = v.subtitles.slice().sort(function (a, b) { return a.start - b.start; });
    } else {
      v.subtitles = [];
      v.scenes.forEach(function (sc) {
        ['zh', 'en'].forEach(function (L) {
          var chunks = splitClauses(sc['narration_' + L], L === 'en' ? 40 : 22);
          if (!chunks.length) return;
          var total = chunks.reduce(function (a, c) { return a + weightLen(c); }, 0) || 1;
          var t0 = sc.start + 0.2, span = Math.max(0.5, sc.end - sc.start - 0.4), acc = 0;
          chunks.forEach(function (c) {
            var w = weightLen(c);
            var cue = { start: t0 + span * acc / total, end: t0 + span * (acc + w) / total };
            cue[L] = c;
            v.subtitles.push(cue);
            acc += w;
          });
        });
      });
      if (v.subtitles.length) estimated = true;
    }
    v._estimated = estimated;
    return v;
  }

  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }

  /* ======================================================================= */
  function Player(root, video, ctx) {
    this.root = root;
    this.ctx = ctx;
    this.v = normalize(video);
    this.scenes = this.v.scenes;
    this.subs = this.v.subtitles;
    this.duration = this.v.duration;
    this.t = 0;
    this.base = 0;
    this.at = 0;
    this.playing = false;
    this.started = false;
    this.ended = false;
    this.si = -1;
    this.cc = ctx.store.get('fd.video.cc', '1') !== '0';
    this.userSilent = false;
    this.audio = null;
    this.audioState = 'none'; // none | loading | ok | error
    this.noteKey = this.v._estimated ? 'v_estimated' : '';
    this.build();
    this.initAudio();
    this.buildScenes();
    // poster frame: the given poster_time, or the first scene once everything in it has appeared
    var first = this.sceneEls[0];
    this.posterT = typeof this.v.poster_time === 'number' ? this.v.poster_time : (first ? first.settle : 0);
    this.bind();
    this.syncUI();
    this.render();
  }
  var P = Player.prototype;

  P.useAudio = function () { return !!this.audio && this.audioState !== 'error' && !this.userSilent; };
  P.silent = function () { return !this.useAudio(); };
  P.now = function () {
    if (this.useAudio()) return this.audio.currentTime || 0;
    if (!this.playing) return this.t;
    return this.base + (performance.now() - this.at) / 1000;
  };

  /* ---------- DOM ---------- */
  P.build = function () {
    this.root.innerHTML =
      '<div class="vplayer" tabindex="0" role="region">' +
        '<div class="vstage">' +
          '<div class="vbgnum num" aria-hidden="true"></div>' +
          '<div class="vsegs" aria-hidden="true"></div>' +
          '<div class="vtop"><span class="vkick"></span><span class="vchip-ai"></span></div>' +
          '<div class="vbgs" aria-hidden="true"></div>' +
          '<div class="vscenes"></div>' +
          '<div class="vsub"></div>' +
          '<div class="vover"><div class="vover-in"><button class="vbig" type="button"></button><span class="vover-meta"></span></div></div>' +
        '</div>' +
        '<div class="vctl">' +
          '<div class="vscrub"><input class="range" type="range" min="0" step="0.05" value="0"><div class="vticks" aria-hidden="true"></div></div>' +
          '<div class="vrow">' +
            '<button class="ibtn" type="button" data-act="play"></button>' +
            '<button class="ibtn" type="button" data-act="prev">' + ICON.prev + '</button>' +
            '<button class="ibtn" type="button" data-act="next">' + ICON.next + '</button>' +
            '<span class="vtime"></span>' +
            '<span class="vspacer"></span>' +
            '<button class="ibtn" type="button" data-act="cc">' + ICON.cc + '</button>' +
            '<button class="ibtn" type="button" data-act="silent"></button>' +
            '<button class="ibtn" type="button" data-act="full">' + ICON.full + '</button>' +
          '</div>' +
        '</div>' +
        '<div class="vnote" hidden></div>' +
        '<div class="vchips"></div>' +
      '</div>';
    var q = this.root.querySelector.bind(this.root);
    this.wrap = q('.vplayer');
    this.stage = q('.vstage');
    this.bgnum = q('.vbgnum');
    this.segsEl = q('.vsegs');
    this.kickEl = q('.vkick');
    this.aiEl = q('.vchip-ai');
    this.scenesEl = q('.vscenes');
    this.bgsEl = q('.vbgs');
    this.subEl = q('.vsub');
    this.over = q('.vover');
    this.big = q('.vbig');
    this.overMeta = q('.vover-meta');
    this.range = q('.range');
    this.ticks = q('.vticks');
    this.timeEl = q('.vtime');
    this.btn = {};
    var self = this;
    this.root.querySelectorAll('[data-act]').forEach(function (b) { self.btn[b.dataset.act] = b; });
    this.noteEl = q('.vnote');
    this.chipsEl = q('.vchips');
    this.range.max = String(this.duration);
    var fsOK = document.fullscreenEnabled || document.webkitFullscreenEnabled;
    if (!fsOK) this.btn.full.hidden = true;
    // segments + ticks
    this.segs = this.scenes.map(function (sc) {
      var s = el('span', 'vseg', '<i></i>');
      s.style.setProperty('--len', Math.max(0.1, sc.end - sc.start).toFixed(2));
      self.segsEl.appendChild(s);
      return s.firstChild;
    });
    this.scenes.forEach(function (sc, i) {
      if (i === 0) return;
      var tick = el('i');
      tick.style.left = (sc.start / self.duration * 100) + '%';
      self.ticks.appendChild(tick);
    });
  };

  P.buildScenes = function () {
    var self = this;
    var ctx = this.ctx;
    var L = ctx.lang();
    var T = ctx.t;
    var pick = function (o, k) { return ctx.pick(o, k); };
    this.scenesEl.innerHTML = '';
    this.bgsEl.innerHTML = '';
    this.chipsEl.innerHTML = '';
    this.si = -1;
    this.sceneEls = this.scenes.map(function (sc, i) {
      var type = sc.type || 'title';
      var node = el('div', 'vscene vscene--' + type);
      node.dataset.i = i;
      var steps = [];
      var addTo = function (parent, e, key, extra) {
        e.classList.add('vstep');
        parent.appendChild(e);
        var st = Object.assign({ el: e, key: key, kind: 'fade' }, extra || {});
        steps.push(st);
        return st;
      };
      var add = function (e, key, extra) { return addTo(node, e, key, extra); };
      var heading = pick(sc, 'heading');
      var body = pick(sc, 'body');
      var img = null;
      var bg = null, bgImg = null;
      var bgd = ctx.normImage(sc.background);
      if (bgd && bgd.src) {
        bg = el('div', 'vbg' + (bgd.flip ? ' flip' : ''), '<img src="' + esc(ctx.asset(bgd.src)) + '" alt="" draggable="false">');
        self.bgsEl.appendChild(bg);
        bgImg = bg.querySelector('img');
        node.classList.add('vscene--hasbg');
      }

      if (type === 'title') {
        if (heading) add(el('h3', 'vh vh-xl', esc(heading)), 'heading');
        add(el('div', 'vrule'), 'rule', { kind: 'rule' });
        if (body) add(el('p', 'vb', esc(body)), 'body');
      } else if (type === 'list') {
        if (heading) add(el('h3', 'vh', esc(heading)), 'heading');
        var items = [];
        if (Array.isArray(sc.items)) items = sc.items.map(function (it) { return typeof it === 'string' ? it : (it[L] || it.zh || it.en || ''); });
        else items = (L === 'en' && sc.items_en && sc.items_en.length ? sc.items_en : sc.items_zh) || [];
        var list = el('div', 'vlist');
        node.appendChild(list);
        items.forEach(function (it, k) {
          addTo(list, el('div', 'vli', '<span class="num">' + pad2(k + 1) + '</span><span>' + esc(it) + '</span>'), 'items.' + k);
        });
        if (body) add(el('p', 'vb', esc(body)), 'body');
      } else if (type === 'stat') {
        var st = sc.stat || {};
        var val = (L === 'en' && st.value_en != null) ? st.value_en : (st.value != null ? st.value : '');
        if (heading) add(el('h3', 'vh', esc(heading)), 'heading');
        var wrap = el('div', 'vstat');
        node.appendChild(wrap);
        addTo(wrap, el('div', 'vstat-n num', numHTML(val)), 'stat', { kind: 'count', num: parseNum(val), text: String(val) });
        var lab = pick(st, 'label');
        if (lab) addTo(wrap, el('div', 'vstat-l', esc(lab)), 'label');
        if (body) add(el('p', 'vb', esc(body)), 'body');
      } else if (type === 'compare') {
        if (heading) add(el('h3', 'vh', esc(heading)), 'heading');
        var bars = sc.bars || [];
        var vals = bars.map(function (b) { return Math.abs(+b.value || 0); });
        var vmax = Math.max.apply(null, vals.concat([0])) || 1;
        var scale = +sc.scale_max || vmax;
        var fr = vals.map(function (x) { return x / scale; });
        var fmax = Math.max.apply(null, fr.concat([0]));
        if (fmax > 0.8) fr = fr.map(function (f) { return f * 0.8 / fmax; }); // 给数值标签留位置
        var anyHL = bars.some(function (b) { return b.highlight; });
        var box = el('div', 'vbars');
        node.appendChild(box);
        bars.forEach(function (b, k) {
          var hl = b.highlight || (!anyHL && vals[k] === vmax);
          var label = (L === 'en' && b.label_en) ? b.label_en : (b.label_zh || b.label || '');
          var dv = (L === 'en' && b.value_en != null) ? b.value_en : b.value;
          var du = (L === 'en' && b.unit_en != null) ? b.unit_en : (b.unit || '');
          var txt = joinUnit(dv, du);
          var row = el('div', 'vbar' + (hl ? ' hl' : ''),
            '<div class="vbar-l">' + esc(label) + '</div><div class="vbar-track"><div class="vbar-fill"></div><div class="vbar-v num">' + numHTML(txt) + '</div></div>');
          addTo(box, row, 'bars.' + k, { kind: 'bar', frac: clamp(fr[k], 0, 1), num: parseNum(txt), text: txt, vEl: row.querySelector('.vbar-v') });
        });
        if (body) add(el('p', 'vb', esc(body)), 'body');
      } else if (type === 'quote') {
        var qd = sc.quote || {};
        if (heading) add(el('h3', 'vh', esc(heading)), 'heading');
        add(el('blockquote', 'vq', '<div class="vq-mark" aria-hidden="true">“</div><p class="vq-text">' + esc(pick(qd, 'text')) + '</p>'), 'quote');
        var who = (L === 'en' && qd.who_en) ? qd.who_en : qd.who;
        if (who) add(el('p', 'vq-who', esc(who)), 'who');
        if (body) add(el('p', 'vb', esc(body)), 'body');
      } else if (type === 'image') {
        var im = ctx.normImage(sc.image);
        var fig = el('figure', 'vimg', im && im.src ? '<img src="' + esc(ctx.asset(im.src)) + '" alt="' + esc(pick(im, 'alt')) + '" draggable="false">' : '');
        add(fig, 'image', { kind: 'image' });
        img = fig.querySelector('img');
        if (heading) add(el('h3', 'vh', esc(heading)), 'heading');
        if (body) add(el('p', 'vb', esc(body)), 'body');
        var credit = im ? pick(im, 'credit') : '';
        if (credit) add(el('p', 'vimg-cap', esc(credit)), 'credit');
      } else if (type === 'source') {
        if (heading) add(el('h3', 'vh', esc(heading)), 'heading');
        var srcs = (sc.sources && sc.sources.length) ? sc.sources : (sc.source ? [sc.source] : []);
        var grid = el('div', 'vsrcs');
        grid.style.setProperty('--n', Math.max(1, Math.min(3, srcs.length)));
        node.appendChild(grid);
        srcs.forEach(function (s, k) {
          var name = (L === 'en' && s.name_en) ? s.name_en : s.name;
          var title = pick(s, 'title');
          var host = ctx.host(s.url);
          addTo(grid, el('div', 'vsrc',
            '<span class="t">' + esc(T('stype_' + (s.type || 'media'))) + '</span>' +
            '<span class="n">' + esc(name || '') + '</span>' +
            (title ? '<span class="ti">' + esc(title) + '</span>' : '') +
            '<span class="d">' + esc([s.date, host].filter(Boolean).join(' · ')) + '</span>'), 'cards.' + k);
        });
        if (body) add(el('p', 'vb', esc(body)), 'body');
      } else {
        if (heading) add(el('h3', 'vh', esc(heading)), 'heading');
        if (body) add(el('p', 'vb', esc(body)), 'body');
      }
      if (sc.source && type !== 'source') {
        var sname = (L === 'en' && sc.source.name_en) ? sc.source.name_en : sc.source.name;
        add(el('p', 'vsrc-tag', esc(T('v_src')) + '<b>' + esc(sname || '') + '</b>' + (sc.source.date ? ' · ' + esc(sc.source.date) : '')), 'source');
      }
      self.scenesEl.appendChild(node);
      var times = self.stepTimes(sc, steps);
      // "settled" frame for paused previews: everything has appeared, and the scene has not started fading out
      var settle = Math.max(sc.start + 0.05, Math.min(times.length ? Math.max.apply(null, times) + 0.7 : sc.start + 0.5, sc.end - 0.35));
      // chip
      var chip = el('button', 'vchip', '<b>' + pad2(i + 1) + '</b><span>' + esc(pick(sc, 'label') || heading || T('v_scene') + ' ' + (i + 1)) + '</span><em>' + fmt(sc.start) + '</em>');
      chip.type = 'button';
      chip.addEventListener('click', function () { self.gotoScene(i); });
      self.chipsEl.appendChild(chip);
      return { sc: sc, node: node, steps: steps, times: times, img: img, chip: chip, settle: settle, bg: bg, bgImg: bgImg };
    });
  };

  /* step times: named overrides from scene.steps, otherwise evenly spaced over the first half of the scene */
  P.stepTimes = function (sc, steps) {
    var dur = Math.max(0.5, sc.end - sc.start);
    var n = steps.length;
    var lead = Math.min(0.3, dur * 0.08);
    var gap = n > 1 ? clamp((dur * 0.5 - lead) / (n - 1), 0.35, 1.2) : 0;
    var given = sc.steps && typeof sc.steps === 'object' ? sc.steps : {};
    return steps.map(function (st, k) {
      var a = sc.start + lead + k * gap;
      var parts = st.key.split('.');
      var g = given[parts[0]];
      var v = parts.length > 1 ? (Array.isArray(g) ? g[+parts[1]] : undefined) : g;
      if (st.key === 'credit' && typeof v !== 'number' && typeof given.image === 'number') v = given.image + 0.4;
      return typeof v === 'number' ? v : a;
    });
  };

  /* ---------- audio ---------- */
  P.initAudio = function () {
    var self = this;
    var src = this.v.audio ? this.ctx.asset(this.v.audio) : '';
    if (!src) { this.audioState = 'error'; this.noteKey = 'v_no_audio'; return; }
    var a = this.audio = new Audio();
    a.preload = 'metadata';
    this.audioState = 'loading';
    a.addEventListener('loadedmetadata', function () {
      self.audioState = 'ok';
      if (isFinite(a.duration) && Math.abs(a.duration - self.duration) > 1.5) {
        console.warn('[video] audio duration ' + a.duration.toFixed(2) + 's differs from timeline ' + self.duration.toFixed(2) + 's');
      }
      self.syncUI();
    });
    a.addEventListener('error', function () { self.fallbackSilent('v_no_audio'); });
    a.addEventListener('ended', function () { if (self.useAudio() && self.playing) self.finish(); });
    a.addEventListener('pause', function () {
      // paused from outside (media keys, another tab): follow it
      if (self.playing && self.useAudio() && !a.ended) { self.t = a.currentTime; self.playing = false; self.syncUI(); self.render(); }
    });
    a.src = src;
  };
  P.fallbackSilent = function (key) {
    var t = this.t;
    this.audioState = 'error';
    this.noteKey = key;
    this.base = t;
    this.at = performance.now();
    if (this.audio) { try { this.audio.pause(); } catch (e) { /* ignore */ } }
    if (this.playing) this.kick();
    this.syncUI();
  };

  /* ---------- transport ---------- */
  P.play = function () {
    var self = this;
    if (!this.scenes.length) return;
    if (this.ended || this.t >= this.duration - 0.05) { this.t = 0; this.ended = false; }
    this.started = true;
    this.playing = true;
    if (this.useAudio()) {
      try { this.audio.currentTime = this.t; } catch (e) { /* not ready yet */ }
      var pr = this.audio.play();
      if (pr && pr.catch) pr.catch(function (err) {
        if (!self.playing) return;
        if (err && err.name === 'NotAllowedError') { self.playing = false; self.syncUI(); return; }
        if (err && err.name === 'AbortError') return;
        self.fallbackSilent('v_audio_error');
      });
    } else {
      this.base = this.t;
      this.at = performance.now();
    }
    document.dispatchEvent(new CustomEvent('fd:play', { detail: { id: 'video' } }));
    this.kick();
    this.syncUI();
  };
  P.pause = function () {
    if (!this.playing) return;
    this.t = clamp(this.now(), 0, this.duration);
    this.playing = false;
    if (this.audio && !this.audio.paused) this.audio.pause();
    this.syncUI();
    this.render();
  };
  P.toggle = function () { if (this.playing) this.pause(); else this.play(); };
  P.seek = function (t) {
    this.t = clamp(t, 0, this.duration);
    this.ended = false;
    this.started = true;
    if (this.useAudio()) { try { this.audio.currentTime = this.t; } catch (e) { /* ignore */ } }
    this.base = this.t;
    this.at = performance.now();
    this.render();
    this.syncUI();
  };
  P.kick = function () {
    var self = this;
    if (this.raf) return;
    var step = function () {
      self.raf = 0;
      if (!self.playing) return;
      var t = self.now();
      if (t >= self.duration) { self.t = self.duration; self.finish(); return; }
      self.t = t;
      self.render();
      self.raf = requestAnimationFrame(step);
    };
    this.raf = requestAnimationFrame(step);
  };
  P.finish = function () {
    this.playing = false;
    this.ended = true;
    if (this.audio && !this.audio.paused) this.audio.pause();
    this.render();
    this.syncUI();
  };
  P.sceneAt = function (t) {
    var i = 0;
    for (var k = 0; k < this.scenes.length; k++) { if (this.scenes[k].start <= t + 1e-6) i = k; }
    return i;
  };
  /* jump to a scene: while playing, from its start; while paused, to the moment everything has appeared */
  P.gotoScene = function (i) {
    i = clamp(i, 0, this.scenes.length - 1);
    var S = this.sceneEls[i];
    this.seek(this.playing ? S.sc.start + 0.01 : S.settle);
  };
  P.step = function (dir) {
    var t = this.started ? this.t : 0;
    var cur = this.sceneAt(t);
    if (dir < 0 && this.playing && t - this.scenes[cur].start > 1.5) { this.gotoScene(cur); return; }
    this.gotoScene(cur + dir);
  };
  P.toggleSilent = function () {
    if (!this.audio || this.audioState === 'error') return;
    var was = this.playing;
    var t = was ? this.now() : this.t;
    if (was) { this.playing = false; if (!this.audio.paused) this.audio.pause(); }
    this.userSilent = !this.userSilent;
    this.t = t;
    if (was) this.play(); else { this.render(); this.syncUI(); }
  };
  P.toggleCC = function () {
    this.cc = !this.cc;
    this.ctx.store.set('fd.video.cc', this.cc ? '1' : '0');
    this.syncUI();
    this.render();
  };
  P.toggleFull = function () {
    var d = document;
    if (d.fullscreenElement || d.webkitFullscreenElement) { (d.exitFullscreen || d.webkitExitFullscreen).call(d); return; }
    var w = this.wrap;
    var req = w.requestFullscreen || w.webkitRequestFullscreen;
    if (req) { try { var r = req.call(w); if (r && r.catch) r.catch(function () { /* ignore */ }); } catch (e) { /* ignore */ } }
  };

  /* ---------- render at time t ---------- */
  P.render = function () {
    if (!this.scenes.length) return;
    var t = this.started ? this.t : this.posterT;
    var si = this.sceneAt(t);
    if (si !== this.si) {
      var self = this;
      this.sceneEls.forEach(function (S, k) {
        S.node.classList.toggle('on', k === si);
        S.chip.classList.toggle('on', k === si);
        if (S.bg) S.bg.classList.toggle('on', k === si);
      });
      this.stage.classList.toggle('has-bg', !!this.sceneEls[si].bg);
      this.si = si;
      var sc = this.scenes[si];
      this.kickEl.textContent = this.ctx.pick(sc, 'kicker') || '';
      this.bgnum.textContent = pad2(si + 1);
      var chip = this.sceneEls[si].chip;
      var cs = this.chipsEl;
      if (chip && cs.scrollWidth > cs.clientWidth) {
        var left = chip.offsetLeft - cs.clientWidth / 2 + chip.offsetWidth / 2;
        try { cs.scrollTo({ left: left, behavior: self.playing ? 'smooth' : 'auto' }); } catch (e) { cs.scrollLeft = left; }
      }
    }
    var S = this.sceneEls[si];
    this.renderScene(S, t, si === this.scenes.length - 1);
    // story-style segments
    for (var k = 0; k < this.segs.length; k++) {
      var s = this.scenes[k];
      var f = clamp((t - s.start) / Math.max(0.01, s.end - s.start), 0, 1);
      if (this.segs[k]._f !== f) { this.segs[k].style.setProperty('--f', f.toFixed(4)); this.segs[k]._f = f; }
    }
    // subtitle
    var L = this.ctx.lang();
    var cue = null, any = null;
    for (var c = 0; c < this.subs.length; c++) {
      var q = this.subs[c];
      if (q.start <= t && t < q.end) { if (q[L]) { cue = q; break; } if (!any && q.zh) any = q; }
    }
    var txt = cue ? cue[L] : (any ? any.zh : '');
    var show = this.cc && !!txt && this.started;
    if (txt !== this._sub || show !== this._subShow) {
      this.subEl.innerHTML = show ? '<span>' + esc(txt) + '</span>' : '';
      this._sub = txt;
      this._subShow = show;
    }
    // scrubber + time
    if (!this.scrubbing) {
      this.range.value = String(this.started ? t : 0);
    }
    var shown = this.started ? t : 0;
    this.range.style.setProperty('--pct', (shown / this.duration * 100).toFixed(3) + '%');
    this.range.setAttribute('aria-valuetext', fmt(shown) + ' / ' + fmt(this.duration));
    var tt = fmt(shown) + ' / ' + fmt(this.duration);
    if (tt !== this._tt) { this.timeEl.textContent = tt; this._tt = tt; }
  };

  P.renderScene = function (S, t, isLast) {
    var rm = reduceMotion();
    var ENTER = rm ? 0.001 : 0.6;
    var sc = S.sc;
    var fadeOut = isLast ? 1 : clamp((sc.end - t) / 0.25, 0, 1);
    S.node.style.opacity = rm ? '' : fadeOut.toFixed(3);
    for (var k = 0; k < S.steps.length; k++) {
      var st = S.steps[k];
      var at = S.times[k];
      var p = easeOut(clamp((t - at) / ENTER, 0, 1));
      if (st._p !== p) { st.el.style.setProperty('--p', p.toFixed(3)); st._p = p; }
      if (st.kind === 'rule') {
        var w = easeOut(clamp((t - at) / (rm ? 0.001 : 0.9), 0, 1));
        st.el.style.setProperty('--w', w.toFixed(3));
      } else if (st.kind === 'bar') {
        var g = easeOut(clamp((t - at - 0.05) / (rm ? 0.001 : 1.0), 0, 1));
        st.el.style.setProperty('--w', (g * st.frac).toFixed(4));
        var vt = st.num ? fmtNum(st.num, st.num.num * g) : st.text;
        if (vt !== st._vt) { st.vEl.innerHTML = numHTML(vt); st._vt = vt; }
      } else if (st.kind === 'count') {
        var g2 = easeOut(clamp((t - at) / (rm ? 0.001 : 1.1), 0, 1));
        var ct = st.num ? fmtNum(st.num, st.num.num * g2) : st.text;
        if (ct !== st._vt) { st.el.innerHTML = numHTML(ct); st._vt = ct; }
      }
    }
    if (S.img) {
      var kb = rm ? 1 : 1 + 0.07 * clamp((t - sc.start) / Math.max(0.1, sc.end - sc.start), 0, 1);
      S.img.style.setProperty('--k', kb.toFixed(4));
    }
    if (S.bg) {
      var kz = rm ? 1 : 1.02 + 0.06 * clamp((t - sc.start) / Math.max(0.1, sc.end - sc.start), 0, 1);
      S.bgImg.style.setProperty('--k', kz.toFixed(4));
      S.bg.style.opacity = rm ? '' : (Math.min(easeOut(clamp((t - sc.start) / 0.8, 0, 1)), fadeOut)).toFixed(3);
    }
  };

  /* ---------- UI state ---------- */
  P.syncUI = function () {
    var T = this.ctx.t;
    var silent = this.silent();
    var forced = !this.audio || this.audioState === 'error';
    var b = this.btn;
    b.play.innerHTML = this.playing ? ICON.pause : ICON.play;
    b.play.setAttribute('aria-label', this.playing ? T('v_pause') : T('v_play'));
    b.play.title = b.play.getAttribute('aria-label') + ' (Space)';
    b.prev.setAttribute('aria-label', T('v_prev')); b.prev.title = T('v_prev') + ' (Shift+←)';
    b.next.setAttribute('aria-label', T('v_next')); b.next.title = T('v_next') + ' (Shift+→)';
    b.cc.setAttribute('aria-label', T('v_cc')); b.cc.title = T('v_cc') + ' (C)';
    b.cc.setAttribute('aria-pressed', this.cc ? 'true' : 'false');
    b.silent.innerHTML = silent ? ICON.mute : ICON.sound;
    b.silent.setAttribute('aria-label', T('v_silent'));
    b.silent.title = forced ? T('v_silent_forced') : T('v_silent') + ' (M)';
    b.silent.setAttribute('aria-pressed', silent ? 'true' : 'false');
    b.silent.disabled = forced;
    b.full.setAttribute('aria-label', T('v_full')); b.full.title = T('v_full') + ' (F)';
    this.range.setAttribute('aria-label', T('v_seek'));
    this.wrap.setAttribute('aria-label', T('v_region'));
    this.aiEl.textContent = silent ? T('v_chip_silent') : T('v_chip_ai');
    this.aiEl.classList.toggle('silent', silent);
    this.chipsEl.setAttribute('aria-label', T('v_scenes'));
    // overlay: only before the first play and after the end
    var showOver = !this.playing && (!this.started || this.ended);
    this.over.hidden = !showOver;
    if (showOver) {
      this.big.className = 'vbig' + (this.ended ? ' replay' : '');
      this.big.innerHTML = this.ended ? ICON.replay : ICON.play;
      this.big.setAttribute('aria-label', this.ended ? T('v_replay') : T('v_play'));
      this.overMeta.textContent = (this.ended ? T('v_replay') : (silent ? T('v_play_silent') : T('v_play'))) + ' · ' + fmt(this.duration);
    }
    var keys = [];
    if (this.audioState === 'error') keys.push(this.noteKey && this.noteKey !== 'v_estimated' ? this.noteKey : 'v_no_audio');
    else if (this.userSilent) keys.push('v_silent_on');
    if (this.v._estimated) keys.push('v_estimated');
    if (keys.length) {
      this.noteEl.hidden = false;
      this.noteEl.innerHTML = ICON.warn + '<span>' + keys.map(function (k) { return esc(T(k)); }).join(' ') + '</span>';
    } else {
      this.noteEl.hidden = true;
    }
  };

  /* ---------- events ---------- */
  P.bind = function () {
    var self = this;
    this.btn.play.addEventListener('click', function () { self.toggle(); });
    this.btn.prev.addEventListener('click', function () { self.step(-1); });
    this.btn.next.addEventListener('click', function () { self.step(1); });
    this.btn.cc.addEventListener('click', function () { self.toggleCC(); });
    this.btn.silent.addEventListener('click', function () { self.toggleSilent(); });
    this.btn.full.addEventListener('click', function () { self.toggleFull(); });
    this.big.addEventListener('click', function (e) { e.stopPropagation(); self.play(); });
    this.stage.addEventListener('click', function () { self.toggle(); });
    var startScrub = function () { self.scrubbing = true; };
    var endScrub = function () { self.scrubbing = false; };
    this.range.addEventListener('pointerdown', startScrub);
    this.range.addEventListener('pointerup', endScrub);
    this.range.addEventListener('pointercancel', endScrub);
    this.range.addEventListener('input', function () { self.seek(parseFloat(self.range.value) || 0); });
    this.range.addEventListener('change', function () { self.scrubbing = false; self.seek(parseFloat(self.range.value) || 0); });
    this.wrap.addEventListener('keydown', function (e) {
      if (e.target === self.range && (e.key === 'ArrowLeft' || e.key === 'ArrowRight') && !e.shiftKey) return;
      if (e.target.closest && e.target.closest('.vchip') && (e.key === ' ' || e.key === 'Enter')) return;
      var k = e.key;
      if (k === ' ' || k === 'k' || k === 'K') { e.preventDefault(); self.toggle(); }
      else if (k === 'ArrowRight' && e.shiftKey) { e.preventDefault(); self.step(1); }
      else if (k === 'ArrowLeft' && e.shiftKey) { e.preventDefault(); self.step(-1); }
      else if (k === 'ArrowRight') { e.preventDefault(); self.seek((self.started ? self.t : 0) + 5); }
      else if (k === 'ArrowLeft') { e.preventDefault(); self.seek((self.started ? self.t : 0) - 5); }
      else if (k === 'c' || k === 'C') { self.toggleCC(); }
      else if (k === 'm' || k === 'M') { self.toggleSilent(); }
      else if (k === 'f' || k === 'F') { self.toggleFull(); }
    });
    this._onPlay = function (e) { if (e.detail && e.detail.id !== 'video') self.pause(); };
    document.addEventListener('fd:play', this._onPlay);
  };

  /* stop sound and timers, release the audio file, empty the container (used when the page switches 稿件版本) */
  P.destroy = function () {
    this.playing = false;
    if (this.raf) { cancelAnimationFrame(this.raf); this.raf = 0; }
    if (this.audio) { try { this.audio.pause(); this.audio.removeAttribute('src'); this.audio.load(); } catch (e) { /* ignore */ } }
    this.audio = null;
    if (this._onPlay) document.removeEventListener('fd:play', this._onPlay);
    this.root.innerHTML = '';
  };

  P.setLang = function () {
    this.buildScenes();
    this.si = -1;
    this._sub = null;
    this.syncUI();
    this.render();
  };

  window.FDVideo = {
    mount: function (root, video, ctx) { return new Player(root, video, ctx); },
    normalize: normalize
  };
})();
