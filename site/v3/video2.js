/* frontier-daily · video2.js — 视频 v2 播放器（v3 网页用的副本；site/v2/video2.js 不动）
 * v3 只改了三处：① 画面下方的分章换成和网页其他版块一样的编号页签（1 2 3…，当前这一章里有进度在走，左右方向键切换）；
 *   ② 关掉背景的粒子连线（“发布会玻璃”不要网格和霓虹）；③ 故障抖动的颜色改读 CSS 变量，跟着主题色和深浅色走。
 * 原说明：
 *
 * 数据：issue.media.video（v: 2），由 site/tools/build_v2.py 组装：
 *   beats[]  一屏一个节拍：{tpl 模板名, start, end, ev 事件, label/kicker, 各模板的内容；每个元素带 t＝旁白说到对应词的秒数}
 *   cues[]   字幕：{start, end, text, t: [每个字的起始秒]}，按 Whisper 逐字对齐得来，用于“卡拉 OK”逐字变亮
 * 动画：GSAP（vendor/gsap.min.js）。所有动画放进一条暂停的时间轴，每一帧只做 tl.time(当前秒)，
 *   所以画面完全由时间决定：有音频时跟着音频走，拖动、暂停、跳场景都不会错位；以后逐帧导出 MP4 也只是逐个时刻截图。
 * 系统开了“减少动态效果”：所有元素只做淡入淡出，数字直接显示终值，没有推拉、故障、粒子。
 * 没加载到 GSAP 时：退成“到点直接显示”的静态版本，照样能看能听。
 * 用法：FDVideo2.mount(容器, issue.media.video, ctx)；ctx 由 app.js 提供（lang、t、asset、store、go）。 */
(function () {
  'use strict';

  var clamp = function (v, a, b) { return Math.min(b, Math.max(a, v)); };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var pad2 = function (n) { return String(n).padStart(2, '0'); };
  var fmt = function (sec) { sec = Math.max(0, Math.floor((sec || 0) + 1e-6)); return Math.floor(sec / 60) + ':' + pad2(sec % 60); };
  var MQ = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  var reduced = function () { return !!(MQ && MQ.matches); };

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
    warn: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 22 20H2z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 10v4.5M12 17.2v.3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    down: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v15M5.5 12.5 12 19l6.5-6.5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    up: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20V5M5.5 11.5 12 5l6.5 6.5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
  };

  /* ---------- text & numbers ---------- */
  var txt = function (o, L) { if (!o) return ''; var v = L === 'en' ? (o.en != null ? o.en : o.zh) : (o.zh != null ? o.zh : o.en); return v == null ? '' : String(v); };
  var pair = function (a, L) { return Array.isArray(a) ? String((L === 'en' ? a[1] : a[0]) || a[0] || '') : String(a || ''); };
  var fld = function (o, k, L) { return o ? String(o[k + '_' + L] != null ? o[k + '_' + L] : (o[k + '_zh'] != null ? o[k + '_zh'] : '')) : ''; };
  function parseNum(s) {
    s = String(s == null ? '' : s).trim();
    var m = s.match(/^([^\d-]*?)(-?\d[\d,]*(?:\.\d+)?)(.*)$/);
    if (!m || /\d/.test(m[3])) return null;
    var raw = m[2].replace(/,/g, '');
    return { pre: m[1], num: parseFloat(raw), dec: (raw.split('.')[1] || '').length, suf: m[3], comma: m[2].indexOf(',') >= 0 };
  }
  function fmtNum(p, v) {
    var s = p.comma ? v.toLocaleString('en-US', { minimumFractionDigits: p.dec, maximumFractionDigits: p.dec }) : v.toFixed(p.dec);
    return (p.pre || '') + s + (p.suf || '');
  }
  function numHTML(text) { // 数字等宽放大，单位和符号缩小
    return esc(text).replace(/[^\d.,\s]+/g, function (u) { return /^[−\-+~$¥]+$/.test(u) ? u : '<span class="u">' + u + '</span>'; });
  }
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function rnd(n) { var x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); }
  function maxT(o) { // 一屏里最晚出现的元素的时刻（暂停时跳到这一屏，就停在全部出齐的那一刻）
    var m = -1;
    (function walk(x) {
      if (Array.isArray(x)) { x.forEach(walk); return; }
      if (!x || typeof x !== 'object') return;
      Object.keys(x).forEach(function (k) {
        if ((k === 't' || k === 'strike_t') && typeof x[k] === 'number') m = Math.max(m, x[k]);
        else if (k === 'ct' && Array.isArray(x[k])) m = Math.max.apply(null, [m].concat(x[k]));
        else if (typeof x[k] === 'object') walk(x[k]);
      });
    })(o);
    return m;
  }

  /* ---------- Anim：往 GSAP 时间轴里加动画；减少动态效果时只淡入淡出 ---------- */
  var NAT = { x: 0, y: 0, xPercent: 0, yPercent: 0, scale: 1, scaleX: 1, scaleY: 1, rotation: 0 };
  function Anim(tl, rm) { this.tl = tl; this.rm = rm; this.list = []; this.counters = []; this.chars = []; this.glitch = []; this.flows = []; this.bounce = []; }
  Anim.prototype.in = function (node, t, from, dur, ease) {
    if (!node) return;
    if (typeof t !== 'number' || isNaN(t)) t = 0; // 没有时刻的元素随这一屏一起出现
    this.list.push([node, t]);
    if (!this.tl) return;
    if (this.rm) { this.tl.fromTo(node, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.35, ease: 'none' }, t); return; }
    var f = Object.assign({ autoAlpha: 0 }, from === undefined ? { yPercent: 30 } : (from || {}));
    var to = { autoAlpha: 1, duration: dur || 0.6, ease: ease || 'power3.out' };
    Object.keys(f).forEach(function (k) { if (k !== 'autoAlpha') to[k] = k in NAT ? NAT[k] : 0; });
    this.tl.fromTo(node, f, to, t);
  };
  /* 出现之后的变化（滑动、生长、变暗）；减少动态效果时到点直接变成终态 */
  Anim.prototype.go = function (node, from, to, t, dur, ease) {
    if (!this.tl || !node) return;
    this.tl.fromTo(node, from, Object.assign({}, to, { duration: this.rm ? 0.001 : (dur || 0.8), ease: ease || 'power2.inOut', immediateRender: false }), t);
  };
  Anim.prototype.set = function (node, vars) { if (window.gsap && node) window.gsap.set(node, vars); };
  Anim.prototype.count = function (span, p, from, to, t, dur, ease) {
    if (!span || !p) return;
    var c = { el: span, p: p, v: from, to: to, t: t, _s: null };
    this.counters.push(c);
    if (this.tl) this.tl.fromTo(c, { v: from }, { v: to, duration: this.rm ? 0.001 : (dur || 1.1), ease: ease || 'power2.out' }, t);
  };

  /* ======================================================================= 模板库（12 种） */
  var TPL = {};
  function head(b, L, extra) {
    var h = el('div', 'v2head', '<span class="v2tag">' + esc(txt(b.title, L)) + '</span>' + (b.unit ? '<span class="v2unit">' + esc(pair(b.unit, L)) + '</span>' : '') + (extra || ''));
    return h;
  }
  function srcLine(node, b, L, ctx) {
    var s = L === 'en' ? b.src_en : b.src_zh;
    if (!s) return null;
    var p = el('p', 'v2src', esc(ctx.t('v_src')) + esc(s));
    node.appendChild(p);
    return p;
  }

  /* 1 动态标题：词按旁白逐个从下方“顶”出来；数字等宽放大；旧数字可被划掉 */
  TPL.kinetic = function (b, L) {
    var node = el('div', 'v2b v2-kin');
    var lines = b.lines;
    if (!lines) { // 其他形状退到这里时：标题 ＋ 每个要点一行
      lines = [];
      if (b.title) lines.push([Object.assign({ kt: true }, b.title)]);
      (b.items || []).forEach(function (it) { lines.push([it]); });
      if (b.value) lines.push([{ zh: (b.value.pre || '') + b.value.to + (b.value.suf || ''), t: b.value.t, num: true, accent: true }]);
      ['name', 'label', 'big', 'stamp', 'cta'].forEach(function (k) { if (b[k]) lines.push([b[k]]); });
      if (b.quote) lines.push([b.quote]);
      node.classList.add('small');
    }
    var words = [];
    var box = el('div', 'kin');
    lines.forEach(function (ln) {
      var row = el('div', 'kl');
      ln.forEach(function (w) {
        var s = txt(w, L); if (!s) return;
        var span = el('span', 'kw' + (w.num ? ' num' : '') + (w.accent ? ' acc' : '') + (w.kt ? ' kt' : ''),
          '<span class="kwi">' + (w.num ? numHTML(s) : esc(s)) + (w.strike_t != null ? '<i class="ks"></i>' : '') + '</span>');
        if (b.uncertain && /[?？]/.test(s)) span.classList.add('glq');
        row.appendChild(span);
        words.push({ w: w, el: span.firstChild, span: span });
      });
      box.appendChild(row);
    });
    node.appendChild(box);
    return { node: node, anim: function (A) {
      words.forEach(function (x) {
        A.in(x.el, x.w.t, { yPercent: 108, rotation: 3 }, 0.55, 'power3.out');
        if (x.span.classList.contains('glq')) A.glitch.push({ el: x.span, t: x.w.t + 0.3, soft: true });
        if (x.w.strike_t != null) {
          var ks = x.el.querySelector('.ks');
          A.set(ks, { scaleX: 0, transformOrigin: 'left center' });
          A.go(ks, { scaleX: 0 }, { scaleX: 1 }, x.w.strike_t, 0.45, 'power2.out');
          A.go(x.el, { opacity: 1 }, { opacity: 0.45 }, x.w.strike_t + 0.3, 0.4, 'none');
        }
      });
    } };
  };

  /* 2 配图缓推：图慢慢推近，前景标签反向平移（视差） */
  TPL.kenburns = function (b, L, ctx) {
    var node = el('div', 'v2b v2-kb full');
    var im = b.image;
    node.innerHTML = '<div class="kb-img">' + (im && im.src ? '<img src="' + esc(ctx.asset(im.src)) + '" alt="' + esc(L === 'en' ? im.alt_en : im.alt_zh) + '" draggable="false">' : '') + '</div>' +
      '<div class="kb-shade"></div><div class="kb-fg"><div class="kb-tags"></div>' + (b.title ? '<h3 class="kb-title">' + esc(txt(b.title, L)) + '</h3>' : '') +
      (im && im.src ? '<span class="kb-cr">' + esc(ctx.t('ai_img')) + '</span>' : '') + '</div>';
    var tagsEl = node.querySelector('.kb-tags');
    var tags = (b.tags || []).map(function (tg) { var e = el('span', 'kb-tag', esc(txt(tg, L))); tagsEl.appendChild(e); return { el: e, t: tg.t }; });
    return { node: node, anim: function (A) {
      var dur = b.end - b.start + 0.4;
      var img = node.querySelector('.kb-img'), fg = node.querySelector('.kb-fg');
      if (A.rm) A.set(img, { scale: 1.06 });
      else {
        A.set(img, { scale: 1.04, xPercent: -1.2, transformOrigin: '62% 50%' });
        A.go(img, { scale: 1.04, xPercent: -1.2 }, { scale: 1.17, xPercent: 1.2 }, b.start - 0.2, dur, 'none');
        A.go(fg, { xPercent: 1.4 }, { xPercent: -1.4 }, b.start - 0.2, dur, 'none');
      }
      tags.forEach(function (x) { A.in(x.el, x.t, { xPercent: -14 }, 0.5); });
      A.in(node.querySelector('.kb-title'), b.title && b.title.t, { yPercent: 40 }, 0.7);
      A.in(node.querySelector('.kb-cr'), b.start + 0.5, null, 0.4);
    } };
  };

  /* 3 哑铃图：之前的点先出现，之后的点从同一位置沿刻度滑过去，中间的差值条跟着拉开 */
  TPL.dumbbell = function (b, L, ctx) {
    var node = el('div', 'v2b v2-db');
    var F = b.frm, To = b.to, D = b.delta || null;
    var max = +b.max || Math.max(F.v, To.v) * 1.1;
    var X = function (v) { return clamp(v / max * 100, 0, 100); };
    var ratio = (L === 'en' && F.v_en != null && F.v) ? F.v_en / F.v : 1;
    var pf = parseNum(fld(F, 'text', L)), pt = parseNum(fld(To, 'text', L));
    node.appendChild(head(b, L));
    var plot = el('div', 'db-plot');
    plot.innerHTML = '<div class="db-axis"><i class="db-line"></i>' + (b.ticks || []).map(function (tk) {
      var v = tk * ratio; return '<span class="db-tk" style="left:' + X(tk) + '%"><b>' + esc(String(+v.toFixed(2))) + '</b></span>';
    }).join('') + '</div>' +
      '<div class="db-seg" style="left:' + X(To.v) + '%;width:' + (X(F.v) - X(To.v)) + '%"></div>' +
      '<div class="db-dot db-from" style="left:' + X(F.v) + '%"><i></i><span class="db-v num"></span><span class="db-l">' + esc(fld(F, 'label', L)) + '</span></div>' +
      '<div class="db-dot db-to" style="left:' + X(F.v) + '%"><i></i><span class="db-v num"></span><span class="db-l">' + esc(fld(To, 'label', L)) + '</span></div>' +
      (D ? '<div class="db-delta" style="left:' + (X(F.v) + X(To.v)) / 2 + '%">' + (D.dir ? ICON[D.dir] : '') + '<span>' + esc(txt(D, L)) + '</span></div>' : '');
    node.appendChild(plot);
    srcLine(node, b, L, ctx);
    var q = function (s) { return plot.querySelector(s); };
    return { node: node, anim: function (A) {
      A.in(node.querySelector('.v2head'), b.start + 0.05, { yPercent: 40 });
      A.set(q('.db-line'), { transformOrigin: 'left center' });
      A.in(q('.db-line'), b.start + 0.1, { scaleX: 0 }, 0.8, 'power2.inOut');
      Array.prototype.forEach.call(plot.querySelectorAll('.db-tk'), function (tk, k) { A.in(tk, b.start + 0.25 + k * 0.07, { yPercent: 60 }, 0.4); });
      var from = q('.db-from'), to = q('.db-to'), seg = q('.db-seg');
      A.in(from, F.t, { scale: 0.2 }, 0.6, 'back.out(2)');
      A.count(from.querySelector('.db-v'), pf, 0, pf ? pf.num : 0, F.t, 1.0);
      var slide = To.t + 0.3;
      A.in(to, To.t, { scale: 0.2 }, 0.35, 'back.out(2)');
      A.go(to, { left: X(F.v) + '%' }, { left: X(To.v) + '%' }, slide, 1.0, 'power2.inOut');
      A.count(to.querySelector('.db-v'), pt, pf ? pf.num : 0, pt ? pt.num : 0, slide, 1.0, 'power2.inOut');
      A.set(seg, { scaleX: 0, transformOrigin: 'right center' });
      A.go(seg, { scaleX: 0 }, { scaleX: 1 }, slide, 1.0, 'power2.inOut');
      if (D) A.in(q('.db-delta'), Math.max(D.t, slide + 0.6), { yPercent: -50 }, 0.5);
      A.in(node.querySelector('.v2src'), b.start + 0.8, null, 0.4);
    } };
  };

  /* 4 条形图生长：各条按旁白生长，数值跟着滚；可加一条参考线（如“一半”） */
  TPL.bars = function (b, L, ctx) {
    var node = el('div', 'v2b v2-bars');
    var items = b.items || [];
    var max = +b.max || Math.max.apply(null, items.map(function (x) { return x.v; }).concat([1]));
    node.appendChild(head(b, L));
    var plot = el('div', 'br-plot');
    var rows = items.map(function (it) {
      var f = clamp(it.v / max, 0, 1);
      var row = el('div', 'br-row' + (it.hl ? ' hl' : ''), '<span class="br-l">' + esc(fld(it, 'label', L)) + '</span><div class="br-tr"><i class="br-f" style="width:' + (f * 100) + '%"></i><span class="br-v num"></span></div>');
      plot.appendChild(row);
      var v = L === 'en' && it.v_en != null ? it.v_en : it.v;
      return { it: it, row: row, f: f, p: { pre: '', num: v, dec: String(v).split('.')[1] ? String(v).split('.')[1].length : 0, suf: '' } };
    });
    var mk = b.marker;
    if (mk) plot.appendChild(el('div', 'br-mk', '<i></i><span>' + esc(txt(mk, L)) + '</span>')).style.left = 'calc(var(--lab) + (100% - var(--lab) - 12cqw) * ' + clamp(mk.v / max, 0, 1).toFixed(4) + ')';
    node.appendChild(plot);
    srcLine(node, b, L, ctx);
    return { node: node, anim: function (A) {
      A.in(node.querySelector('.v2head'), b.start + 0.05, { yPercent: 40 });
      rows.forEach(function (r) {
        var fill = r.row.querySelector('.br-f'), val = r.row.querySelector('.br-v');
        A.in(r.row, r.it.t, { xPercent: -3 }, 0.4);
        A.set(fill, { scaleX: 0, transformOrigin: 'left center' });
        A.go(fill, { scaleX: 0 }, { scaleX: 1 }, r.it.t + 0.05, 0.95, 'power3.out');
        A.go(val, { left: '0%' }, { left: (r.f * 100) + '%' }, r.it.t + 0.05, 0.95, 'power3.out');
        A.count(val, r.p, 0, r.p.num, r.it.t + 0.05, 0.95, 'power3.out');
      });
      if (mk) {
        var m = plot.querySelector('.br-mk');
        A.set(m.firstChild, { transformOrigin: 'top center' });
        A.in(m.firstChild, mk.t, { scaleY: 0 }, 0.5, 'power2.out');
        A.in(m.lastChild, mk.t + 0.15, { yPercent: 60 }, 0.45);
      }
      A.in(node.querySelector('.v2src'), b.start + 0.8, null, 0.4);
    } };
  };

  /* 5 左右分屏：左块先出现，箭头画过去，右块的数从左块的值滚到新值，左块随之变暗 */
  TPL.split = function (b, L, ctx) {
    var node = el('div', 'v2b v2-sp');
    var F = b.frm || b.left, To = b.to || b.right, D = b.delta;
    var max = +b.max || Math.max(F.v || 0, To.v || 0) || 1;
    var panel = function (o, cls) {
      var hasV = typeof o.v === 'number';
      return '<div class="sp-p ' + cls + '"><span class="sp-l">' + esc(fld(o, 'label', L)) + '</span>' +
        '<div class="sp-n ' + (hasV ? 'num' : 'txt') + '">' + (hasV ? '' : esc(fld(o, 'text', L))) + '</div>' +
        (hasV ? '<div class="sp-bar"><i style="width:' + clamp(o.v / max * 100, 0, 100) + '%"></i></div>' : '') + '</div>';
    };
    node.appendChild(head(b, L));
    var grid = el('div', 'sp-grid', panel(F, 'sp-a') +
      '<div class="sp-mid"><svg class="arr" viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true"><path pathLength="1" d="M4 20 H92 M78 8 L94 20 L78 32"/></svg>' +
      (D ? '<span class="sp-dl">' + (D.dir ? ICON[D.dir] : '') + esc(txt(D, L)) + '</span>' : '') + '</div>' + panel(To, 'sp-b'));
    node.appendChild(grid);
    srcLine(node, b, L, ctx);
    var pa = grid.querySelector('.sp-a'), pb = grid.querySelector('.sp-b');
    return { node: node, anim: function (A) {
      A.in(node.querySelector('.v2head'), b.start + 0.05, { yPercent: 40 });
      var pf = parseNum(fld(F, 'text', L)), pt = parseNum(fld(To, 'text', L));
      A.in(pa, F.t, { xPercent: -8 }, 0.6);
      if (pf) A.count(pa.querySelector('.sp-n'), pf, 0, pf.num, F.t, 0.9);
      var ba = pa.querySelector('.sp-bar i'), bb = pb.querySelector('.sp-bar i');
      if (ba) { A.set(ba, { transformOrigin: 'left center' }); A.go(ba, { scaleX: 0 }, { scaleX: 1 }, F.t, 0.9, 'power3.out'); }
      var path = grid.querySelector('.arr path');
      A.set(path, { strokeDasharray: 1, strokeDashoffset: 1 });
      var ta = D && D.t != null ? D.t : (F.t + To.t) / 2;
      A.go(path, { strokeDashoffset: 1 }, { strokeDashoffset: 0 }, ta, 0.6, 'power2.out');
      A.in(grid.querySelector('.sp-dl'), ta + 0.2, { yPercent: 50 }, 0.45);
      A.in(pb, To.t, { xPercent: 8 }, 0.6);
      if (pt) A.count(pb.querySelector('.sp-n'), pt, pf ? pf.num : 0, pt.num, To.t, 1.0, 'power2.inOut');
      if (bb) { A.set(bb, { transformOrigin: 'left center' }); A.go(bb, { scaleX: F.v && To.v ? F.v / To.v : 0 }, { scaleX: 1 }, To.t, 1.0, 'power2.inOut'); }
      A.go(pa, { opacity: 1 }, { opacity: 0.5 }, To.t + 0.6, 0.5, 'none');
      A.in(node.querySelector('.v2src'), b.start + 0.8, null, 0.4);
    } };
  };

  /* 6 引语逐字高亮：引语里的字随旁白逐字变亮，关键词高亮；下附原文措辞和出处 */
  TPL.quote = function (b, L, ctx) {
    var node = el('div', 'v2b v2-q');
    var Q = b.quote || {};
    var text = txt(Q, L);
    var times;
    if (L !== 'en' && Array.isArray(Q.ct) && Q.ct.length === text.length) times = Q.ct;
    else { var a = (Q.t || b.start) + 0.4, z = Math.max(a + 0.6, Q.t_end || a + 1.6); times = text.split('').map(function (_, k) { return a + (z - a) * k / Math.max(1, text.length); }); }
    var key = /“([^”]+)”/.exec(text);
    var k0 = key ? key.index : -1, k1 = key ? key.index + key[0].length : -1;
    node.innerHTML = '<div class="q-mark" aria-hidden="true">“</div><p class="q-text">' + text.split('').map(function (c, k) {
      return '<span' + (k >= k0 && k < k1 ? ' class="k"' : '') + '>' + esc(c) + '</span>'; }).join('') + '</p>' +
      (Q.orig && L !== 'en' ? '<p class="q-orig"><b>' + esc(ctx.t('v_orig') || '原文') + '</b>' + esc(Q.orig) + '</p>' : '') +
      (b.who ? '<p class="q-who">' + esc(pair(b.who, L)) + '</p>' : '');
    srcLine(node, b, L, ctx);
    var spans = node.querySelectorAll('.q-text span');
    return { node: node, anim: function (A) {
      A.in(node.querySelector('.q-mark'), b.start + 0.05, { scale: 0.5, yPercent: 30 }, 0.6, 'back.out(1.8)');
      A.in(node.querySelector('.q-text'), Math.max(b.start + 0.1, (Q.t || b.start) - 0.1), { yPercent: 10 }, 0.5);
      Array.prototype.forEach.call(spans, function (s, k) { A.chars.push({ el: s, t: times[k] }); });
      A.in(node.querySelector('.q-who'), b.start + 0.35, null, 0.5);
      A.in(node.querySelector('.q-orig'), times[times.length - 1] + 0.35, { yPercent: 40 }, 0.5);
      A.in(node.querySelector('.v2src'), b.start + 0.8, null, 0.4);
    } };
  };

  /* 7 关系图生长：节点按旁白出现，连线逐条画出，关键连线上的虚线朝箭头方向流动（连线写 n1 → n2，t 留给出现时刻） */
  TPL.graph = function (b, L, ctx) {
    var node = el('div', 'v2b v2-gr');
    var nodes = b.nodes || [], links = b.links || [];
    var pos = {}; nodes.forEach(function (n) { pos[n.id] = n; });
    if (b.title) node.appendChild(head(b, L));
    var plot = el('div', 'gr-plot');
    var svg = '<svg class="gr-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">' + links.map(function (lk, k) {
      var s = pos[lk.n1], t = pos[lk.n2]; if (!s || !t) return '';
      var d = 'M' + s.x + ' ' + s.y + ' L' + t.x + ' ' + t.y;
      return '<path class="gr-ln' + (lk.kind ? ' ' + lk.kind : '') + '" data-k="' + k + '" pathLength="1" d="' + d + '"/>' +
        (lk.flow ? '<path class="gr-flow" data-f="' + k + '" pathLength="1" d="' + d + '"/>' : '');
    }).join('') + '</svg>';
    plot.innerHTML = svg + nodes.map(function (n) {
      return '<div class="gr-n' + (n.kind ? ' ' + n.kind : '') + '" data-id="' + esc(n.id) + '" style="left:' + n.x + '%;top:' + n.y + '%">' + esc(txt(n, L)) + '</div>';
    }).join('') + links.map(function (lk, k) {
      var s = pos[lk.n1], t = pos[lk.n2]; if (!s || !t) return '';
      return '<span class="gr-lb' + (lk.kind ? ' ' + lk.kind : '') + '" data-l="' + k + '" style="left:' + (s.x + t.x) / 2 + '%;top:' + (s.y + t.y) / 2 + '%">' + esc(txt(lk, L)) + '</span>';
    }).join('');
    node.appendChild(plot);
    srcLine(node, b, L, ctx);
    return { node: node, anim: function (A) {
      if (b.title) A.in(node.querySelector('.v2head'), b.title.t != null ? b.title.t : b.start + 0.05, { yPercent: 40 });
      nodes.forEach(function (n) {
        var e = plot.querySelector('.gr-n[data-id="' + n.id + '"]');
        A.set(e, { xPercent: -50, yPercent: -50 });
        A.in(e, n.t, { scale: 0.4 }, 0.55, 'back.out(2)');
      });
      links.forEach(function (lk, k) {
        var p = plot.querySelector('[data-k="' + k + '"]'), lb = plot.querySelector('[data-l="' + k + '"]'), f = plot.querySelector('[data-f="' + k + '"]');
        if (!p) return;
        A.set(p, { strokeDasharray: 1, strokeDashoffset: 1 });
        A.go(p, { strokeDashoffset: 1 }, { strokeDashoffset: 0 }, lk.t, 0.75, 'power2.inOut');
        A.set(lb, { xPercent: -50, yPercent: -50 });
        A.in(lb, lk.t + 0.3, { scale: 0.6 }, 0.45, 'back.out(1.8)');
        if (f) { A.in(f, lk.t + 0.7, null, 0.3); A.flows.push({ el: f, t: lk.t + 0.7 }); }
      });
      A.in(node.querySelector('.v2src'), b.start + 0.8, null, 0.4);
    } };
  };

  /* 8 关键数字：从 0 滚到实际值，涨跌箭头落下，数字落定时画面闪一下 */
  TPL.counter = function (b, L, ctx) {
    var node = el('div', 'v2b v2-ct');
    var V = b.value || {};
    var dir = V.dir || '';
    node.innerHTML = (b.pre ? '<div class="ct-pre v2tag">' + esc(txt(b.pre, L)) + '</div>' : '') +
      (b.name ? '<div class="ct-name">' + esc(txt(b.name, L)) + '</div>' : '') +
      '<div class="ct-row">' + (dir ? '<span class="ct-ar ' + dir + '">' + ICON[dir] + '</span>' : '') + '<span class="ct-n num ' + dir + '"></span></div>' +
      (b.label ? '<div class="ct-l">' + esc(txt(b.label, L)) + '</div>' : '') + '<div class="ct-flash"></div>';
    srcLine(node, b, L, ctx);
    var p = { pre: (L === 'en' && V.pre_en != null ? V.pre_en : V.pre) || '', num: L === 'en' && V.to_en != null ? V.to_en : V.to,
      dec: V.dec || 0, suf: (L === 'en' && V.suf_en != null ? V.suf_en : V.suf) || '', comma: !!V.comma };
    return { node: node, anim: function (A) {
      var q = function (s) { return node.querySelector(s); };
      A.in(q('.ct-pre'), b.pre && b.pre.t, { xPercent: -6 }, 0.5);
      A.in(q('.ct-name'), b.name && b.name.t, { yPercent: 40 }, 0.6);
      A.in(q('.ct-l'), b.label && b.label.t, { xPercent: -4 }, 0.5);
      A.in(q('.ct-row'), V.t, { yPercent: 18 }, 0.5);
      A.count(q('.ct-n'), p, 0, p.num, V.t, 1.3, 'power2.out');
      A.in(q('.ct-ar'), V.t + 0.1, { yPercent: dir === 'up' ? 60 : -60, rotation: -15 }, 0.7, 'back.out(2.2)');
      if (!A.rm) {
        A.go(q('.ct-flash'), { autoAlpha: 0 }, { autoAlpha: 1 }, V.t + 1.2, 0.12, 'none');
        A.go(q('.ct-flash'), { autoAlpha: 1 }, { autoAlpha: 0 }, V.t + 1.35, 0.7, 'power1.out');
      }
      A.in(q('.v2src'), b.start + 0.8, null, 0.4);
    } };
  };

  /* 9 时间线推进：游标沿年代刻度走到每个日子，事件依次亮出 */
  TPL.timeline = function (b, L, ctx) {
    var node = el('div', 'v2b v2-tl');
    var sp = b.span || [0, 1], items = b.items || [];
    var X = function (y) { return clamp((y - sp[0]) / (sp[1] - sp[0]) * 100, 0, 100); };
    node.appendChild(head(b, L));
    var plot = el('div', 'tl-plot');
    plot.innerHTML = '<div class="tl-axis"><i class="tl-line"></i><i class="tl-fill"></i>' + (b.ticks || []).map(function (y) {
      return '<span class="tl-tk" style="left:' + X(y) + '%">' + y + '</span>'; }).join('') + '</div><i class="tl-cur"></i>' +
      items.map(function (it, k) {
        var x = X(it.at);
        return '<div class="tl-it' + (it.hl ? ' hl' : '') + (x > 60 ? ' r' : '') + '" data-k="' + k + '" style="left:' + x + '%"><i class="tl-dot"></i>' +
          '<div class="tl-card"><span class="tl-when">' + esc(fld(it, 'when', L)) + '</span><b class="num">' + numHTML(fld(it, 'text', L)) + '</b></div></div>';
      }).join('');
    node.appendChild(plot);
    srcLine(node, b, L, ctx);
    return { node: node, anim: function (A) {
      A.in(node.querySelector('.v2head'), b.start + 0.05, { yPercent: 40 });
      var line = plot.querySelector('.tl-line'), fill = plot.querySelector('.tl-fill'), cur = plot.querySelector('.tl-cur');
      A.set(line, { transformOrigin: 'left center' });
      A.in(line, b.start + 0.1, { scaleX: 0 }, 0.7, 'power2.inOut');
      Array.prototype.forEach.call(plot.querySelectorAll('.tl-tk'), function (tk, k) { A.in(tk, b.start + 0.2 + k * 0.06, { yPercent: 50 }, 0.35); });
      A.set(cur, { xPercent: -50 });
      A.in(cur, b.start + 0.25, { scale: 0 }, 0.3);
      var px = 0, pt = b.start + 0.35;
      items.forEach(function (it, k) {
        var x = X(it.at), dur = Math.max(0.35, it.t - pt);
        A.go(cur, { left: px + '%' }, { left: x + '%' }, pt, dur, 'power2.inOut');
        A.go(fill, { width: px + '%' }, { width: x + '%' }, pt, dur, 'power2.inOut');
        var itEl = plot.querySelector('.tl-it[data-k="' + k + '"]');
        A.in(itEl.querySelector('.tl-dot'), pt + dur - 0.05, { scale: 0 }, 0.4, 'back.out(2.5)');
        A.in(itEl.querySelector('.tl-card'), pt + dur, { yPercent: 25 }, 0.5);
        px = x; pt = pt + dur + 0.15;
      });
      A.in(node.querySelector('.v2src'), b.start + 0.8, null, 0.4);
    } };
  };

  /* 10 要点依次落下 */
  TPL.cascade = function (b, L, ctx) {
    var node = el('div', 'v2b v2-cs');
    if (b.title) node.appendChild(el('div', 'v2head', '<span class="v2tag">' + esc(txt(b.title, L)) + '</span>'));
    var list = el('div', 'cs-list');
    var items = b.items || (b.tiles || []).map(function (x) { return { zh: x.k_zh + ' · ' + x.v_zh, en: x.k_en + ' · ' + x.v_en, t: x.t }; });
    var rows = items.map(function (it, k) {
      var s = txt(it, L) || fld(it, 'label', L);
      var r = el('div', 'cs-it', '<span class="cs-i num">' + pad2(k + 1) + '</span><span class="cs-t">' + esc(s) + '</span>');
      if (b.uncertain && /[?？]/.test(s)) r.lastChild.classList.add('glq');
      list.appendChild(r);
      return { it: it, el: r };
    });
    node.appendChild(list);
    srcLine(node, b, L, ctx);
    return { node: node, anim: function (A) {
      A.in(node.querySelector('.v2head'), b.title && b.title.t != null ? b.title.t : b.start + 0.05, { yPercent: 40 });
      rows.forEach(function (r) {
        A.in(r.el, r.it.t, { yPercent: -150, rotation: -2.5 }, 0.7, 'back.out(1.3)');
        var g = r.el.querySelector('.glq'); if (g) A.glitch.push({ el: g, t: r.it.t + 0.4, soft: true });
      });
      A.in(node.querySelector('.v2src'), b.start + 0.8, null, 0.4);
    } };
  };

  /* 11 不确定：轻微故障（错位、色散、扫描线）＋“未确认”印章 */
  TPL.glitch = function (b, L, ctx) {
    var node = el('div', 'v2b v2-gl');
    var big = txt(b.big, L);
    node.innerHTML = '<div class="gl-scan"></div>' + (b.small ? '<span class="gl-small v2tag">' + esc(txt(b.small, L)) + '</span>' : '') +
      '<div class="gl-big" data-text="' + esc(big) + '"><span>' + esc(big) + '</span></div>' +
      (b.stamp ? '<div class="gl-stamp"><span>' + esc(txt(b.stamp, L)) + '</span></div>' : '');
    srcLine(node, b, L, ctx);
    return { node: node, anim: function (A) {
      var g = node.querySelector('.gl-big');
      A.in(node.querySelector('.gl-small'), b.small && b.small.t, { xPercent: -6 }, 0.5);
      if (A.rm) A.in(g, b.big.t, null, 0.3);
      else {
        A.in(g, b.big.t, { x: -6 }, 0.08, 'none');
        A.go(g, { opacity: 1 }, { opacity: 0.25 }, b.big.t + 0.1, 0.04, 'none');
        A.go(g, { opacity: 0.25 }, { opacity: 1 }, b.big.t + 0.18, 0.05, 'none');
      }
      A.glitch.push({ el: g, t: b.big.t });
      A.in(node.querySelector('.gl-stamp'), b.stamp && b.stamp.t, { scale: 1.9, rotation: -10 }, 0.45, 'back.out(1.7)');
      A.in(node.querySelector('.v2src'), b.start + 0.8, null, 0.4);
    } };
  };

  /* 12 结尾回顾宫格＋来源：每条一块（点了跳到网页对应条目），底部提示完整来源在下方 */
  TPL.recap = function (b, L, ctx) {
    var node = el('div', 'v2b v2-rc');
    var tiles = b.tiles || [];
    var grid = el('div', 'rc-grid');
    tiles.forEach(function (x) {
      var t = el('button', 'rc-t', '<span class="rc-k">' + esc(fld(x, 'k', L)) + '</span><span class="rc-v num">' + numHTML(fld(x, 'v', L)) + '</span>' +
        (fld(x, 'src', L) ? '<span class="rc-s">' + esc(ctx.t('v_src')) + esc(fld(x, 'src', L)) + '</span>' : ''));
      t.type = 'button';
      t.addEventListener('click', function (e) { e.stopPropagation(); if (ctx.go && x.ev) ctx.go(x.ev); });
      grid.appendChild(t);
      x._el = t;
    });
    node.appendChild(grid);
    if (b.cta) node.appendChild(el('div', 'rc-cta', '<span>' + esc(txt(b.cta, L)) + '</span><i class="rc-ar">' + ICON.down + '</i>'));
    return { node: node, anim: function (A) {
      tiles.forEach(function (x) { A.in(x._el, x.t, { yPercent: 30, scale: 0.94 }, 0.55, 'back.out(1.5)'); });
      A.in(node.querySelector('.rc-cta'), b.cta && b.cta.t, { yPercent: 60 }, 0.5);
      var ar = node.querySelector('.rc-ar'); if (ar) A.bounce.push({ el: ar, t: b.cta.t });
    } };
  };

  /* ======================================================================= 播放器 */
  function Player(root, video, ctx) {
    this.root = root;
    this.ctx = ctx;
    this.v = video;
    this.beats = video.beats || [];
    this.scenes = this.beats.map(function (b) { return { start: b.start, end: b.end }; }); // app.js 的“看这一段”按它跳
    this.cues = video.cues || [];
    this.duration = +video.duration || (this.beats.length ? this.beats[this.beats.length - 1].end : 1);
    this.t = 0; this.base = 0; this.at = 0;
    this.playing = false; this.started = false; this.ended = false;
    this.bi = -1;
    this.cc = ctx.store.get('fd.video.cc', '1') !== '0';
    this.userSilent = false;
    this.audio = null;
    this.audioState = 'none';
    this.noteKey = '';
    this.build();
    this.initAudio();
    this.buildBeats();
    this.bind();
    this.syncUI();
    this.render(true);
  }
  var P = Player.prototype;

  P.useAudio = function () { return !!this.audio && this.audioState !== 'error' && !this.userSilent; };
  P.silent = function () { return !this.useAudio(); };
  P.now = function () {
    if (this.useAudio()) return this.audio.currentTime || 0;
    if (!this.playing) return this.t;
    return this.base + (performance.now() - this.at) / 1000;
  };

  P.build = function () {
    this.root.innerHTML =
      '<div class="vplayer v2p" tabindex="0" role="region">' +
        '<div class="v2stage">' +
          '<div class="v2grid" aria-hidden="true"></div><canvas class="v2fx" aria-hidden="true"></canvas>' +
          '<div class="v2segs" aria-hidden="true"></div>' +
          '<div class="v2top"><span class="v2kick"></span><span class="v2ai"></span></div>' +
          '<div class="v2beats"></div><i class="v2sweep" aria-hidden="true"></i>' +
          '<div class="v2sub" aria-live="off"></div>' +
          '<div class="vover"><div class="vover-in"><button class="vbig" type="button"></button><span class="vover-meta"></span></div></div>' +
        '</div>' +
        '<div class="vctl">' +
          '<div class="vscrub"><input class="range" type="range" min="0" step="0.05" value="0"><div class="vticks" aria-hidden="true"></div></div>' +
          '<div class="vrow">' +
            '<button class="ibtn" type="button" data-act="play"></button>' +
            '<button class="ibtn" type="button" data-act="prev">' + ICON.prev + '</button>' +
            '<button class="ibtn" type="button" data-act="next">' + ICON.next + '</button>' +
            '<span class="vtime"></span><span class="vspacer"></span>' +
            '<button class="ibtn" type="button" data-act="cc">' + ICON.cc + '</button>' +
            '<button class="ibtn" type="button" data-act="silent"></button>' +
            '<button class="ibtn" type="button" data-act="full">' + ICON.full + '</button>' +
          '</div>' +
        '</div>' +
        '<div class="vnote" hidden></div>' +
        '<div class="vchips vpgr"><div class="vpager" role="tablist"></div><span class="count" aria-hidden="true"><b>1</b><span class="sl">/</span><span class="vn"></span></span></div>' +
      '</div>';
    var q = this.root.querySelector.bind(this.root);
    this.wrap = q('.vplayer'); this.stage = q('.v2stage'); this.fx = q('.v2fx');
    this.segsEl = q('.v2segs'); this.kickEl = q('.v2kick'); this.aiEl = q('.v2ai');
    this.beatsEl = q('.v2beats'); this.sweep = q('.v2sweep'); this.subEl = q('.v2sub');
    this.over = q('.vover'); this.big = q('.vbig'); this.overMeta = q('.vover-meta');
    this.range = q('.range'); this.ticks = q('.vticks'); this.timeEl = q('.vtime');
    this.noteEl = q('.vnote'); this.chipsEl = q('.vpager'); this.countEl = q('.vpgr .count b'); this.fxOff = true;
    this.stage.id = 'v2stage-' + Math.random().toString(36).slice(2, 8); q('.vpgr .vn').textContent = String(this.beats.length);
    var self = this;
    this.btn = {};
    this.root.querySelectorAll('[data-act]').forEach(function (b) { self.btn[b.dataset.act] = b; });
    this.range.max = String(this.duration);
    this.segs = this.beats.map(function (b) {
      var s = el('span', 'v2seg', '<i></i>');
      s.style.setProperty('--len', Math.max(0.1, b.end - b.start).toFixed(2));
      self.segsEl.appendChild(s);
      return s.firstChild;
    });
    this.beats.forEach(function (b, i) {
      if (!i) return;
      var tick = el('i'); tick.style.left = (b.start / self.duration * 100) + '%'; self.ticks.appendChild(tick);
    });
    // 粒子：位置是时间的函数（同一时刻永远画出同一帧）
    this.parts = [];
    for (var k = 0; k < 26; k++) this.parts.push({ x: rnd(k + 1), y: rnd(k + 41), vx: (rnd(k + 81) - 0.5) * 0.012, vy: (rnd(k + 121) - 0.5) * 0.008, r: 0.6 + rnd(k + 161) * 1.3 });
    if (window.ResizeObserver) { this.ro = new ResizeObserver(function () { self._fxW = 0; self.drawFx(self.shownT()); }); this.ro.observe(this.stage); }
  };

  P.buildBeats = function () {
    var self = this, ctx = this.ctx, L = ctx.lang();
    this.beatsEl.innerHTML = '';
    this.chipsEl.innerHTML = '';
    this.bi = -1;
    this.items = this.beats.map(function (b, i) {
      var f = TPL[b.tpl] || TPL.kinetic, r;
      try { r = f(b, L, ctx); } catch (e) { console.warn('[video2] beat ' + (i + 1) + ' (' + b.tpl + ')', e); r = TPL.kinetic({ title: { zh: b.label_zh, en: b.label_en, t: b.start + 0.2 } }, L, ctx); }
      r.node.dataset.i = i;
      self.beatsEl.appendChild(r.node);
      var lab = fld(b, 'label', L) || ctx.t('v_scene') + ' ' + (i + 1);
      var chip = el('button', 'pg vpg', '<span class="pg-fill" aria-hidden="true"></span><span class="pg-n">' + (i + 1) + '</span><span class="pg-t">' + esc(lab) + '</span>');
      chip.type = 'button'; chip.setAttribute('role', 'tab'); chip.setAttribute('aria-selected', 'false'); chip.tabIndex = i ? -1 : 0;
      chip.setAttribute('aria-controls', self.stage.id); chip.title = lab + ' · ' + fmt(b.start);
      chip.addEventListener('keydown', function (e) {
        var k = e.key, j = null;
        if (k === 'ArrowRight' || k === 'ArrowDown') j = i + 1; else if (k === 'ArrowLeft' || k === 'ArrowUp') j = i - 1;
        else if (k === 'Home') j = 0; else if (k === 'End') j = self.items.length - 1;
        if (j === null) return;
        e.preventDefault(); e.stopPropagation();
        j = clamp(j, 0, self.items.length - 1); self.gotoScene(j); self.items[j].chip.focus();
      });
      chip.addEventListener('click', function () { self.gotoScene(i); });
      self.chipsEl.appendChild(chip);
      var last = maxT(b);
      var settle = clamp(Math.max(b.start + 0.6, last + 1.0), b.start + 0.05, b.end - 0.3);
      return { b: b, node: r.node, anim: r.anim, chip: chip, settle: settle };
    });
    this.posterT = typeof this.v.poster_time === 'number' ? this.v.poster_time : (this.items[0] ? this.items[0].settle : 0);
    this.buildTimeline();
  };

  P.buildTimeline = function () {
    var gs = window.gsap, self = this;
    if (this.tl) { this.tl.kill(); this.tl = null; }
    this.rm = reduced();
    this.tl = gs ? gs.timeline({ paused: true, defaults: { lazy: false, overwrite: false } }) : null;
    var A = this.A = new Anim(this.tl, this.rm);
    var n = this.items.length;
    this.items.forEach(function (it, i) {
      var b = it.b;
      // 一屏的进出：淡入（带一点点放大），下一屏开始前淡出
      if (self.tl) {
        self.tl.fromTo(it.node, self.rm ? { autoAlpha: 0 } : { autoAlpha: 0, scale: 1.015 },
          { autoAlpha: 1, scale: 1, duration: self.rm ? 0.3 : 0.38, ease: 'power2.out' }, Math.max(0, b.start - 0.1));
        if (i < n - 1) self.tl.fromTo(it.node, { autoAlpha: 1 }, { autoAlpha: 0, duration: 0.26, ease: 'power1.in', immediateRender: false }, b.end - 0.2);
      }
      it.anim(A);
    });
    if (this.tl) this.tl.set({}, {}, this.duration + 1);
  };

  /* ---------- audio（与第一版相同：音频加载失败自动退成无声预览） ---------- */
  P.initAudio = function () {
    var self = this;
    var src = this.v.audio ? this.ctx.asset(this.v.audio) : '';
    if (!src) { this.audioState = 'error'; this.noteKey = 'v_no_audio'; return; }
    var a = this.audio = new Audio();
    a.preload = 'metadata';
    this.audioState = 'loading';
    a.addEventListener('loadedmetadata', function () { self.audioState = 'ok'; self.syncUI(); });
    a.addEventListener('error', function () { self.fallbackSilent('v_no_audio'); });
    a.addEventListener('ended', function () { if (self.useAudio() && self.playing) self.finish(); });
    a.addEventListener('pause', function () {
      if (self.playing && self.useAudio() && !a.ended) { self.t = a.currentTime; self.playing = false; self.syncUI(); self.render(); }
    });
    a.src = src;
  };
  P.fallbackSilent = function (key) {
    this.audioState = 'error'; this.noteKey = key; this.base = this.t; this.at = performance.now();
    if (this.audio) { try { this.audio.pause(); } catch (e) { /* ignore */ } }
    if (this.playing) this.kick();
    this.syncUI();
  };

  /* ---------- transport ---------- */
  P.play = function () {
    var self = this;
    if (!this.beats.length) return;
    if (this.ended || this.t >= this.duration - 0.05) { this.t = 0; this.ended = false; }
    this.started = true; this.playing = true;
    if (this.useAudio()) {
      try { this.audio.currentTime = this.t; } catch (e) { /* not ready */ }
      var pr = this.audio.play();
      if (pr && pr.catch) pr.catch(function (err) {
        if (!self.playing) return;
        if (err && err.name === 'NotAllowedError') { self.playing = false; self.syncUI(); return; }
        if (err && err.name === 'AbortError') return;
        self.fallbackSilent('v_audio_error');
      });
    } else { this.base = this.t; this.at = performance.now(); }
    document.dispatchEvent(new CustomEvent('fd:play', { detail: { id: 'video' } }));
    this.kick(); this.syncUI();
  };
  P.pause = function () {
    if (!this.playing) return;
    this.t = clamp(this.now(), 0, this.duration);
    this.playing = false;
    if (this.audio && !this.audio.paused) this.audio.pause();
    this.syncUI(); this.render();
  };
  P.toggle = function () { if (this.playing) this.pause(); else this.play(); };
  P.seek = function (t) {
    this.t = clamp(t, 0, this.duration);
    this.ended = false; this.started = true;
    if (this.useAudio()) { try { this.audio.currentTime = this.t; } catch (e) { /* ignore */ } }
    this.base = this.t; this.at = performance.now();
    this.render(); this.syncUI();
  };
  P.kick = function () {
    var self = this;
    if (this.raf) return;
    var step = function () {
      self.raf = 0;
      if (!self.playing) return;
      var t = self.now();
      if (t >= self.duration) { self.t = self.duration; self.finish(); return; }
      self.t = t; self.render();
      self.raf = requestAnimationFrame(step);
    };
    this.raf = requestAnimationFrame(step);
  };
  P.finish = function () { this.playing = false; this.ended = true; if (this.audio && !this.audio.paused) this.audio.pause(); this.render(); this.syncUI(); };
  P.beatAt = function (t) { var i = 0; for (var k = 0; k < this.beats.length; k++) if (this.beats[k].start <= t + 1e-6) i = k; return i; };
  P.sceneAt = P.beatAt;
  P.gotoScene = function (i) { i = clamp(i, 0, this.items.length - 1); var it = this.items[i]; this.seek(this.playing ? it.b.start + 0.01 : it.settle); };
  P.step = function (dir) {
    var t = this.started ? this.t : 0, cur = this.beatAt(t);
    if (dir < 0 && this.playing && t - this.beats[cur].start > 1.5) { this.gotoScene(cur); return; }
    this.gotoScene(cur + dir);
  };
  P.toggleSilent = function () {
    if (!this.audio || this.audioState === 'error') return;
    var was = this.playing, t = was ? this.now() : this.t;
    if (was) { this.playing = false; if (!this.audio.paused) this.audio.pause(); }
    this.userSilent = !this.userSilent; this.t = t;
    if (was) this.play(); else { this.render(); this.syncUI(); }
  };
  P.toggleCC = function () { this.cc = !this.cc; this.ctx.store.set('fd.video.cc', this.cc ? '1' : '0'); this._cue = undefined; this.syncUI(); this.render(); };
  P.toggleFull = function () {
    var d = document;
    if (d.fullscreenElement || d.webkitFullscreenElement) { (d.exitFullscreen || d.webkitExitFullscreen).call(d); return; }
    var w = this.wrap, req = w.requestFullscreen || w.webkitRequestFullscreen;
    if (req && (d.fullscreenEnabled || d.webkitFullscreenEnabled)) { try { var r = req.call(w); if (r && r.catch) r.catch(function () { w.classList.toggle('v2-zoom'); }); } catch (e) { w.classList.toggle('v2-zoom'); } }
    else w.classList.toggle('v2-zoom'); // 没有全屏接口（如 iPhone）：放大铺满窗口，再点一次还原
  };

  /* ---------- render at time t ---------- */
  P.shownT = function () { return this.started ? this.t : this.posterT; };
  P.render = function () {
    if (!this.items || !this.items.length) return;
    var t = this.shownT(), A = this.A, rm = this.rm, k;
    if (this.tl) this.tl.time(Math.min(t, this.duration + 0.5));
    else this.renderStatic(t);
    var bi = this.beatAt(t);
    if (bi !== this.bi) {
      var self = this;
      this.items.forEach(function (it, k2) { var on = k2 === bi; it.chip.classList.toggle('on', on); it.chip.setAttribute('aria-selected', on ? 'true' : 'false'); it.chip.tabIndex = on ? 0 : -1; if (!on) it.chip.style.removeProperty('--f'); });
      if (this.countEl) this.countEl.textContent = String(bi + 1);
      var b = this.beats[bi], L = this.ctx.lang();
      this.kickEl.innerHTML = '<b>' + pad2(bi + 1) + ' / ' + pad2(this.beats.length) + '</b>' + esc(fld(b, 'kicker', L));
      var chip = this.items[bi].chip, cs = this.chipsEl;
      if (chip && cs.scrollWidth > cs.clientWidth) {
        var left = chip.offsetLeft - cs.clientWidth / 2 + chip.offsetWidth / 2;
        try { cs.scrollTo({ left: left, behavior: self.playing ? 'smooth' : 'auto' }); } catch (e) { cs.scrollLeft = left; }
      }
      this.bi = bi;
    }
    // 数字滚动
    for (k = 0; k < A.counters.length; k++) {
      var c = A.counters[k];
      var v = this.tl ? c.v : (t >= c.t ? c.to : 0);
      var s = fmtNum(c.p, v);
      if (s !== c._s) { c.el.innerHTML = numHTML(s); c._s = s; }
    }
    // 引语逐字变亮
    for (k = 0; k < A.chars.length; k++) { var ch = A.chars[k], on = t >= ch.t - 0.02; if (ch._on !== on) { ch.el.classList.toggle('on', on); ch._on = on; } }
    // 故障抖动（按时间算出的伪随机，同一时刻同一帧）
    for (k = 0; k < A.glitch.length; k++) {
      var g = A.glitch[k], dt = t - g.t, amp = 0;
      if (!rm && dt >= 0) {
        var fr = Math.floor(t * 14);
        amp = dt < 0.6 ? 1 - dt / 0.6 : (rnd(fr + k * 7) > 0.9 ? 0.55 : 0);
        if (g.soft) amp *= 0.5;
      }
      var key = amp ? Math.floor(t * 14) : -1;
      if (key !== g._k) {
        g._k = key;
        if (g.soft) g.el.style.setProperty('--gq', amp ? ((rnd(key) - 0.5) * 0.12 * amp).toFixed(3) + 'em 0 0 rgb(var(--v-warm-rgb) / .8), ' + ((rnd(key + 3) - 0.5) * -0.12 * amp).toFixed(3) + 'em 0 0 rgb(var(--v-blue-rgb) / .8)' : 'none');
        else {
          g.el.style.setProperty('--gx', amp ? ((rnd(key) - 0.5) * 0.14 * amp).toFixed(3) + 'em' : '0em');
          g.el.style.setProperty('--gy', amp ? ((rnd(key + 1) - 0.5) * 0.05 * amp).toFixed(3) + 'em' : '0em');
          g.el.style.setProperty('--gc', amp ? Math.round(rnd(key + 2) * 70) + '%' : '0%');
          g.el.style.setProperty('--gd', amp ? Math.round(rnd(key + 4) * 60) + '%' : '100%');
        }
      }
    }
    // 关系图连线流动、回顾页箭头轻跳
    for (k = 0; k < A.flows.length; k++) A.flows[k].el.style.strokeDashoffset = rm ? '0' : (-(t - A.flows[k].t) * 0.35).toFixed(3);
    for (k = 0; k < A.bounce.length; k++) { var bo = A.bounce[k]; bo.el.style.transform = rm || t < bo.t ? '' : 'translateY(' + (Math.abs(Math.sin((t - bo.t) * 3.4)) * -18).toFixed(1) + '%)'; }
    // 换屏时一道细光扫过
    var ds = t - this.beats[bi].start;
    var so = !rm && bi > 0 && ds >= -0.1 && ds < 0.45 ? 1 - Math.max(0, ds) / 0.45 : 0;
    this.sweep.style.opacity = so.toFixed(3);
    if (so) this.sweep.style.top = (Math.max(0, ds + 0.1) / 0.55 * 100).toFixed(2) + '%';
    // 进度条
    for (k = 0; k < this.segs.length; k++) {
      var bb = this.beats[k], f = clamp((t - bb.start) / Math.max(0.01, bb.end - bb.start), 0, 1);
      if (this.segs[k]._f !== f) { this.segs[k].style.setProperty('--f', f.toFixed(4)); this.segs[k]._f = f; }
    }
    var ab = this.beats[bi], af = clamp((t - ab.start) / Math.max(0.01, ab.end - ab.start), 0, 1), ac = this.items[bi].chip;
    if (ac && ac._f !== af) { ac.style.setProperty('--f', (this.started ? af : 0).toFixed(4)); ac._f = af; }
    this.renderSub(t);
    this.drawFx(t);
    if (!this.scrubbing) this.range.value = String(this.started ? t : 0);
    var shown = this.started ? t : 0;
    this.range.style.setProperty('--pct', (shown / this.duration * 100).toFixed(3) + '%');
    this.range.setAttribute('aria-valuetext', fmt(shown) + ' / ' + fmt(this.duration));
    var tt = fmt(shown) + ' / ' + fmt(this.duration);
    if (tt !== this._tt) { this.timeEl.textContent = tt; this._tt = tt; }
  };
  P.renderStatic = function (t) { // 没有 GSAP：到点直接显示
    var bi = this.beatAt(t);
    this.items.forEach(function (it, i) { it.node.style.visibility = i === bi ? 'visible' : 'hidden'; it.node.style.opacity = i === bi ? '1' : '0'; });
    this.A.list.forEach(function (x) { if (x[0] && !x[0].classList.contains('v2b')) x[0].style.opacity = t >= x[1] ? '1' : '0'; });
  };

  /* 字幕：中文按字变亮（卡拉 OK）；英文界面显示这一屏的英文大意 */
  P.renderSub = function (t) {
    var L = this.ctx.lang(), show = this.cc && this.started, cue = null, k;
    if (L === 'en') {
      var b = this.beats[this.beatAt(t)];
      var s = show && b && b.sub_en && t < this.duration - 0.05 ? b.sub_en : '';
      if (s !== this._cue) { this.subEl.innerHTML = s ? '<p class="en">' + esc(s) + '</p>' : ''; this._cue = s; }
      return;
    }
    if (show) for (k = 0; k < this.cues.length; k++) { var c = this.cues[k]; if (c.start - 0.05 <= t && t < c.end) { cue = c; break; } }
    if (cue !== this._cue) {
      this._cue = cue; this._n = -1;
      this.subEl.innerHTML = cue ? '<p>' + cue.text.split('').map(function (ch) { return '<i>' + esc(ch) + '</i>'; }).join('') + '</p>' : '';
      this._subEls = cue ? this.subEl.querySelectorAll('i') : [];
    }
    if (!cue) return;
    var n = 0;
    for (k = 0; k < cue.t.length; k++) if (cue.t[k] != null && cue.t[k] <= t + 0.03) n = k + 1;
    if (n !== this._n) {
      for (k = 0; k < this._subEls.length; k++) { this._subEls[k].className = k < n - 1 ? 'on' : (k === n - 1 ? 'on cur' : ''); }
      this._n = n;
    }
  };

  /* 背景粒子：细点和连线，跟随时间缓慢漂移 */
  P.drawFx = function (t) {
    var cv = this.fx; if (!cv || !cv.getContext || this.fxOff) return;
    var w = cv.clientWidth, h = cv.clientHeight; if (!w || !h) return;
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    if (this._fxW !== w || this._fxH !== h) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); this._fxW = w; this._fxH = h; this._fxT = null; }
    var tt = this.rm ? 0 : t;
    if (this._fxT != null && Math.abs(tt - this._fxT) < 1 / 50) return;
    this._fxT = tt;
    var g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    var pts = this.parts.map(function (p) { var x = (p.x + p.vx * tt) % 1, y = (p.y + p.vy * tt) % 1; return [(x < 0 ? x + 1 : x) * w, (y < 0 ? y + 1 : y) * h, p.r]; });
    var lim = Math.min(w, h) * 0.24;
    g.lineWidth = 1;
    for (var i = 0; i < pts.length; i++) {
      for (var j = i + 1; j < pts.length; j++) {
        var dx = pts[i][0] - pts[j][0], dy = pts[i][1] - pts[j][1], d = Math.sqrt(dx * dx + dy * dy);
        if (d < lim) { g.strokeStyle = 'rgba(95,211,199,' + (0.09 * (1 - d / lim)).toFixed(3) + ')'; g.beginPath(); g.moveTo(pts[i][0], pts[i][1]); g.lineTo(pts[j][0], pts[j][1]); g.stroke(); }
      }
      g.fillStyle = 'rgba(95,211,199,0.38)'; g.beginPath(); g.arc(pts[i][0], pts[i][1], pts[i][2], 0, 6.283); g.fill();
    }
  };

  /* ---------- UI state ---------- */
  P.syncUI = function () {
    var T = this.ctx.t, silent = this.silent(), forced = !this.audio || this.audioState === 'error', b = this.btn;
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
    var showOver = !this.playing && (!this.started || this.ended);
    this.over.hidden = !showOver;
    if (showOver) {
      this.big.className = 'vbig' + (this.ended ? ' replay' : '');
      this.big.innerHTML = this.ended ? ICON.replay : ICON.play;
      this.big.setAttribute('aria-label', this.ended ? T('v_replay') : T('v_play'));
      this.overMeta.textContent = (this.ended ? T('v_replay') : (silent ? T('v_play_silent') : T('v_play'))) + ' · ' + fmt(this.duration);
    }
    var keys = [];
    if (this.audioState === 'error') keys.push(this.noteKey || 'v_no_audio');
    else if (this.userSilent) keys.push('v_silent_on');
    if (keys.length) { this.noteEl.hidden = false; this.noteEl.innerHTML = ICON.warn + '<span>' + keys.map(function (k) { return esc(T(k)); }).join(' ') + '</span>'; }
    else this.noteEl.hidden = true;
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
    var startScrub = function () { self.scrubbing = true; }, endScrub = function () { self.scrubbing = false; };
    this.range.addEventListener('pointerdown', startScrub);
    this.range.addEventListener('pointerup', endScrub);
    this.range.addEventListener('pointercancel', endScrub);
    this.range.addEventListener('input', function () { self.seek(parseFloat(self.range.value) || 0); });
    this.range.addEventListener('change', function () { self.scrubbing = false; self.seek(parseFloat(self.range.value) || 0); });
    this.wrap.addEventListener('keydown', function (e) {
      if (e.target === self.range && (e.key === 'ArrowLeft' || e.key === 'ArrowRight') && !e.shiftKey) return;
      if (e.target.closest && e.target.closest('.vpg, .rc-t') && (e.key === ' ' || e.key === 'Enter')) return;
      var k = e.key;
      if (k === ' ' || k === 'k' || k === 'K') { e.preventDefault(); self.toggle(); }
      else if (k === 'ArrowRight' && e.shiftKey) { e.preventDefault(); self.step(1); }
      else if (k === 'ArrowLeft' && e.shiftKey) { e.preventDefault(); self.step(-1); }
      else if (k === 'ArrowRight') { e.preventDefault(); self.seek((self.started ? self.t : 0) + 5); }
      else if (k === 'ArrowLeft') { e.preventDefault(); self.seek((self.started ? self.t : 0) - 5); }
      else if (k === 'c' || k === 'C') self.toggleCC();
      else if (k === 'm' || k === 'M') self.toggleSilent();
      else if (k === 'f' || k === 'F') self.toggleFull();
      else if (k === 'Escape' && self.wrap.classList.contains('v2-zoom')) self.wrap.classList.remove('v2-zoom');
    });
    this._onPlay = function (e) { if (e.detail && e.detail.id !== 'video') self.pause(); };
    document.addEventListener('fd:play', this._onPlay);
    this._onRM = function () { self.buildBeats(); self.bi = -1; self._cue = undefined; self.render(); };
    if (MQ) { if (MQ.addEventListener) MQ.addEventListener('change', this._onRM); else if (MQ.addListener) MQ.addListener(this._onRM); }
  };

  P.destroy = function () {
    this.playing = false;
    if (this.raf) { cancelAnimationFrame(this.raf); this.raf = 0; }
    if (this.tl) { this.tl.kill(); this.tl = null; }
    if (this.ro) this.ro.disconnect();
    if (this.audio) { try { this.audio.pause(); this.audio.removeAttribute('src'); this.audio.load(); } catch (e) { /* ignore */ } }
    this.audio = null;
    if (this._onPlay) document.removeEventListener('fd:play', this._onPlay);
    if (MQ && this._onRM) { if (MQ.removeEventListener) MQ.removeEventListener('change', this._onRM); else if (MQ.removeListener) MQ.removeListener(this._onRM); }
    this.root.innerHTML = '';
  };
  P.setLang = function () { this.buildBeats(); this.bi = -1; this._cue = undefined; this._fxT = null; this.syncUI(); this.render(); };

  window.FDVideo2 = { mount: function (root, video, ctx) { return new Player(root, video, ctx); }, templates: Object.keys(TPL) };
})();
