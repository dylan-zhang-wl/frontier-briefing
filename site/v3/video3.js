/* frontier-daily · video3.js — 视频 v3「一镜到底的今日地图」
 *
 * 一台镜头连续飞过一张三维的“今日地图”：开场俯瞰全图 → 每条故事线一片（1–4 片）→（可选）国内外对照与接下来 → 回到全图。
 * 每一期画什么全由数据决定（site/tools/video3_build.py 从那一期的分镜 JSON 编出来）：每章 1–3 个模板，模板库见下面的 TPL
 * （柱子缩水、价位块下坠、时间轨、2.5D 配图、手机、传播链、点阵数字、分岔路、对比卡、额度柱、原话卡、国内外对折、接下来）；
 * 怎么加一个模板见 site/tools/README_video3.md。
 * 每一片用最合适的手法，但都摆在同一个三维世界里，镜头从不硬切：
 *   · 三维（three.js r186.1）：玻璃柱、下坠的价位块、时间轨、粒子、分岔的路；后期用 postprocessing 做景深、泛光、暗角；
 *   · 2.5D 视差：本期配图＋深度图（Depth Anything V2 Small 估的），贴在世界里的“窗”上，镜头一动近处就动得多；
 *   · SVG 动态图形：安全一章的等轴测“供应链机器”（投影公式借自 anatomy，MIT），线条描出、光扫、包裹沿传送带走；
 *   · 动态图表：开放模型一章的额度阶梯用 ECharts（网页已自带），按时间逐帧算，不靠它自己的动画；
 *   · 着色器转场：配图用噪声溶解（带亮边）出现和消失；地图“对折”时屏幕沿中缝撕开、色散；镜头飞得快时整屏方向模糊。
 *   · 动态文字：片头遮罩上推（参考 awesome-ai-motion 的 R11 开场钩子，MIT）、字形光扫、数字滚动、翻牌日期。
 * 所有中文都是 HTML（清楚、可选中、可读屏），按三维坐标投影到画面上，不做三维文字模型。
 *
 * 时间：画面完全是时间的函数。一条暂停的 GSAP 时间轴＋按时间算的镜头路径，每一帧只做“跳到第 t 秒”；
 *   有音频时以音频为准，拖动、暂停、跳章都不会错位；逐帧截图也只是逐个时刻渲染（render(t)）。
 * 触发词：每个动作在哪一秒出现，来自 site/tools/video3_build.py 的逐字对齐（data.T）。
 * 用法：FDVideo3.mount(容器, 场景数据, ctx)；ctx 可给 lang()、asset(路径)、store、jumpSource(来源id)、go(事件id)。
 *   返回的播放器有 scenes[]、play()、pause()、seek(秒)、playing、setLang()、destroy()，与 video2 相同，接进主页面时 app.js 不必改别处。
 * 性能：滚到附近才建三维场景；像素比最高 1.5；看不见（切到别的标签页、滚出画面）就暂停；手机上关景深和方向模糊。
 * 系统开了“减少动态效果”：镜头不飞，每章停在一张关键画面，下方展开文字稿；音频照常。 */
(function () {
  'use strict';

  var THREE = null, PP = null;
  // 11-08 渲染修复（K42 封面、K44 对比卡长数值、K45 卡片及时收起和柱子、K46 时间轴小图与小字、对比卡压图不出画、滚动数字千位逗号）：
  // 只在组装数据写了 fix1108（新动效开关和视频导演开关都开着）时起作用；任一个关着，这些地方和 11-08 以前逐像素一样。
  var FX = false;
  var clamp = function (v, a, b) { return Math.min(b, Math.max(a, v)); };
  var sat = function (u) { return clamp(u, 0, 1); };
  var lerp = function (a, b, u) { return a + (b - a) * u; };
  var smooth = function (u) { u = sat(u); return u * u * (3 - 2 * u); };
  var inOut = function (u) { u = sat(u); return u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2; };
  var out3 = function (u) { u = sat(u); return 1 - Math.pow(1 - u, 3); };
  var out4 = function (u) { u = sat(u); return 1 - Math.pow(1 - u, 4); };
  var sine = function (u) { u = sat(u); return -(Math.cos(Math.PI * u) - 1) / 2; };
  var EASE = { io: inOut, o3: out3, o4: out4, sine: sine, lin: sat };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var pad2 = function (n) { return String(n).padStart(2, '0'); };
  var fmt = function (sec) { sec = Math.max(0, Math.floor((sec || 0) + 1e-6)); return Math.floor(sec / 60) + ':' + pad2(sec % 60); };
  function rnd(n) { var x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); }
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  var MQ = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  var MQD = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  var DEG = Math.PI / 180;

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
    map: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5 3.5 7v12L9 17l6 2 5.5-2V5L15 7z M9 5v12 M15 7v12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>'
  };

  /* 界面文字（组装脚本按这一段截取字体用到的字） */
  /* I18N-ZH-START */
  var I18N = {
    zh: {
      play: '播放', pause: '暂停', replay: '重播', prev: '上一章', next: '下一章', cc: '字幕', silent: '静音', full: '全屏',
      seek: '进度', region: '视频：今日地图', chapters: '分章', ai: 'AI 合成语音', music: '配乐',
      explore: '自由看图', back: '回到全图', sources: '出处', close: '关闭', no_audio: '旁白音频没有加载成功，画面照常播放。',
      no_gl: '这台设备画不了三维画面，下面是每一章的要点和文字稿。', transcript: '文字稿', loading: '正在准备三维画面…',
      play_meta: '播放', replay_meta: '重播', ch: '第 {n} 章', stage: ['一', '二', '三', '四'],
      reduced: '已按系统设置减少动态效果：每章停在一张关键画面，下面是文字稿。', note_lbl: '这一片', jump: '跳到'
    },
    en: {
      play: 'Play', pause: 'Pause', replay: 'Replay', prev: 'Previous chapter', next: 'Next chapter', cc: 'Captions', silent: 'Mute', full: 'Full screen',
      seek: 'Seek', region: 'Video: today\'s map', chapters: 'Chapters', ai: 'AI voice', music: 'Music',
      explore: 'Explore', back: 'Back to the map', sources: 'Sources', close: 'Close', no_audio: 'The narration failed to load; the visuals still play.',
      no_gl: 'This device cannot draw the 3D scene; here are the key points and the transcript.', transcript: 'Transcript', loading: 'Preparing the 3D scene…',
      play_meta: 'Play', replay_meta: 'Replay', ch: 'Chapter {n}', stage: ['1', '2', '3', '4'],
      reduced: 'Reduced motion: one key frame per chapter, with the transcript below.', note_lbl: 'This area', jump: 'Go to'
    }
  };
  /* I18N-ZH-END */

  function V3(x, y, z) { return new THREE.Vector3(x, y, z); }
  function tx(o, L) { if (!o) return ''; if (typeof o === 'string') return o; return o[L] != null ? o[L] : (o.zh != null ? o.zh : ''); }
  // 一行字里的数字放大（Times New Roman），counter 时第一个数字换成从 0 滚上去的计数
  // 11-06：滚动的只是里面那个数（span[data-c]），单位（%）留在外面不被换掉——原来 94.49% 滚完只剩 94.49
  function emph(s, counter, cls) {
    var first = true;
    return esc(s).replace(/[−\-]?\d[\d,]*(?:\.\d+)?%?/g, function (m, off, all) {
      // 型号、名字里的数字（GPT-6、K3.1、Qwen4、Q2）不当数字强调（11-06 白天补：刻度尺"GPT-6 Cyber"原来被拆成"GPT"＋放大的红色"-6"）
      if (/[A-Za-z]/.test(all.charAt(off - 1))) return m;
      var c = cls || '';
      if (counter && first) {
        first = false;
        var u = /%$/.test(m) ? '%' : '';
        // 11-08：data-f 记下原样的数（1,318），滚完照它显示、滚动中也带千位逗号（原来滚完显示成 1318）
        return '<span class="v3n em ' + c + '"><span data-c="' + m.replace(/[^\d.\-−]/g, '').replace('−', '-') + '"' + (FX && m.indexOf(',') >= 0 ? ' data-f="' + m.replace(/^[−\-]/, '').replace(/%$/, '') + '"' : '') + '>0</span>' + u + '</span>';
      }
      first = false; return '<span class="v3n em ' + c + '">' + m + '</span>';
    });
  }

  /* ---- 中文整词换行（2026-11-09 加；组装时开关"视频中文整词换行"开着，数据里才有 zhwrap） ----
   * zhwrap 是"原文 → 带换行点的显示文字"的对照表（site/tools/video3_zhwrap.py 用 zh_breaks.py 算好，和网页同一套）。
   * 卡片、标题等的 HTML 建好以后，wbWalk 按元素里的文字去表里找：找到了才把换行点 U+200B、连接符 U+2060 插进那几个文本节点
   * （数字和单位之间的空格换成不换行空格），元素加 v3wb（keep-all：只在换行点、空格、标点处换行）；找不到的原样不动。
   * 只动画面上的文本节点：数据里的字（触发词、字幕和逐字时间、文字稿）一个字不改。没有 zhwrap 时这些函数什么都不做。 */
  var WB_CJK = /[\u3400-\u9fff]/, WB_MK = /[\u200b\u2060]/, WB_DIG = /[\d,.]/, WB_HAS = Object.prototype.hasOwnProperty;
  function wbNum(s) { return s.replace(/\d[\d,.]*/g, '#'); }          // 数字一段收成 #：滚动数字一开始显示 0，也认得出来
  function wbIndex(map) {
    if (!map || typeof map !== 'object') return null;
    var ix = { m: map, n: {} };
    for (var k in map) if (WB_HAS.call(map, k)) { var nk = wbNum(k); if (!WB_HAS.call(ix.n, nk)) ix.n[nk] = map[k]; }
    return ix;
  }
  function wbLook(ix, s) {
    var t = String(s || '').trim();
    if (!t || !WB_CJK.test(t)) return null;
    if (WB_HAS.call(ix.m, t)) return ix.m[t];
    t = wbNum(t);
    return WB_HAS.call(ix.n, t) ? ix.n[t] : null;
  }
  // 把显示文字 d 对到几段原文 parts 上（parts 连起来就是元素里的字）：换行点跟在前一个字后面；返回插好的几段，对不上返回 null
  function wbAlign(parts, d) {
    var j = 0, n = d.length, out = [], k, i, t, o, c;
    var marks = function () { var m = ''; while (j < n && WB_MK.test(d.charAt(j))) m += d.charAt(j++); return m; };
    marks();
    for (k = 0; k < parts.length; k++) {
      t = parts[k]; o = '';
      for (i = 0; i < t.length; i++) {
        c = t.charAt(i);
        if (j < n && c === d.charAt(j)) { o += c; j++; }
        else if (c === ' ' && d.charAt(j) === '\u00a0') { o += '\u00a0'; j++; }
        else if (/\d/.test(c) && /\d/.test(d.charAt(j))) {      // 滚动数字：画面上先是 0，原文是终值，整段数字对整段数字
          while (i < t.length && WB_DIG.test(t.charAt(i))) o += t.charAt(i++);
          i--;
          while (j < n && WB_DIG.test(d.charAt(j))) j++;
        } else if (/\s/.test(c)) { o += c; continue; }           // 播放器拼字时多出的空白，原样留着
        else return null;
        o += marks();
      }
      out.push(o);
    }
    return j >= n ? out : null;
  }
  function wbNodes(e, deep) {
    var a = [], x;
    if (deep) { var w = document.createTreeWalker(e, 4 /* NodeFilter.SHOW_TEXT */, null); for (x = w.nextNode(); x; x = w.nextNode()) a.push(x); }
    else for (x = e.firstChild; x; x = x.nextSibling) if (x.nodeType === 3) a.push(x);
    return a;
  }
  function wbSet(nodes, d) {
    if (!nodes.length) return false;
    var r = wbAlign(nodes.map(function (x) { return x.data; }), d);
    if (!r) return false;
    nodes.forEach(function (x, i) { if (x.data !== r[i]) x.data = r[i]; });
    return true;
  }
  // 从 e 往下找：整个元素的字对上了就整块插、加 v3wb；对不上再看它自己直接带的字（如标题里另有一层扫光的副本），再往下找。
  // kept：上一层已是 keep-all；这一层的字没对上时加 v3wbn 恢复普通换行，免得没有换行点的中文整段连在一起
  function wbWalk(ix, e, kept) {
    if (!ix || !e || e.nodeType !== 1 || e.namespaceURI !== 'http://www.w3.org/1999/xhtml') return;
    var full = e.textContent || '';
    if (!WB_CJK.test(full)) return;
    var d = wbLook(ix, full);
    if (d != null && wbSet(wbNodes(e, true), d)) { e.classList.add('v3wb'); return; }
    var own = wbNodes(e, false), s = own.map(function (x) { return x.data; }).join('');
    var mine = WB_CJK.test(s) && (d = wbLook(ix, s)) != null && wbSet(own, d);
    if (mine) e.classList.add('v3wb'); else if (kept) e.classList.add('v3wbn');
    for (var c = e.firstElementChild; c; c = c.nextElementSibling) wbWalk(ix, c, mine);
  }
  function wbLen(s) { return String(s || '').replace(/[\u200b\u2060]/g, '').length; }   // 字数（不算插进去的换行点）

  /* =================================================================== 着色器 */
  var NOISE = [
    'float h21(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }',
    'float vnoise(vec2 p){ vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);',
    '  return mix(mix(h21(i), h21(i + vec2(1.0, 0.0)), u.x), mix(h21(i + vec2(0.0, 1.0)), h21(i + vec2(1.0, 1.0)), u.x), u.y); }',
    'float fbm(vec2 p){ float a = 0.5, s = 0.0; for (int i = 0; i < 4; i++) { s += a * vnoise(p); p *= 2.03; a *= 0.5; } return s; }'
  ].join('\n');

  // 玻璃板：平面上用圆角矩形距离场画出圆角、亮边和斜向光泽（不用复杂几何）
  var PANEL_V = [
    'varying vec2 vUv; varying vec3 vN; varying vec3 vV;',
    '#include <fog_pars_vertex>',
    'void main(){ vUv = uv; vec4 mvPosition = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = -mvPosition.xyz;',
    '  gl_Position = projectionMatrix * mvPosition;', '#include <fog_vertex>', '}'
  ].join('\n');
  var PANEL_F = [
    'uniform vec3 uTint; uniform vec3 uTop; uniform vec3 uEdge; uniform vec3 uInk; uniform float uInkK; uniform float uAlpha; uniform float uFade; uniform vec2 uSize; uniform float uRadius; uniform float uSheen; uniform float uEdgeGlow;',
    'varying vec2 vUv; varying vec3 vN; varying vec3 vV;',
    '#include <fog_pars_fragment>',
    'float sdR(vec2 p, vec2 b, float r){ vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }',
    'void main(){',
    '  vec2 p = (vUv - 0.5) * uSize; float d = sdR(p, uSize * 0.5, uRadius); float aa = max(fwidth(d) * 1.2, 1e-4);',
    '  float mask = 1.0 - smoothstep(-aa, aa, d); if (mask < 0.003) discard;',
    '  float edge = 1.0 - smoothstep(0.0, 0.09, -d); float inner = 1.0 - smoothstep(0.0, 0.9, -d);',
    '  float fres = pow(clamp(1.0 - abs(dot(normalize(vN), normalize(vV))), 0.0, 1.0), 2.0);',
    '  vec3 col = mix(uTint, uTop, smoothstep(0.0, 1.0, vUv.y));',
    '  float sk = (vUv.x * 0.8 + vUv.y * 0.45 - uSheen) * 6.0; float sh = exp(-sk * sk);',
    '  float hair = 1.0 - smoothstep(0.0, 0.03, -d);',
    '  col += uEdge * (edge * uEdgeGlow + inner * 0.06) + vec3(1.0) * sh * 0.22; col = mix(col, uInk, hair * uInkK);',
    '  float a = uAlpha * (0.8 + 0.3 * fres) + edge * 0.5 + sh * 0.12 + hair * 0.3;',
    '  gl_FragColor = vec4(col, clamp(a, 0.0, 1.0) * mask * uFade);',
    '#include <fog_fragment>', '}'
  ].join('\n');
  // 玻璃体（柱、块）：菲涅耳亮边＋一点高光
  var BOX_V = PANEL_V;
  var BOX_F = [
    'uniform vec3 uTint; uniform vec3 uRim; uniform vec3 uInk; uniform float uInkK; uniform float uAlpha; uniform float uFade; uniform float uRimK;',
    'varying vec2 vUv; varying vec3 vN; varying vec3 vV;',
    '#include <fog_pars_fragment>',
    'void main(){ vec3 N = normalize(vN), V = normalize(vV); float fres = pow(clamp(1.0 - abs(dot(N, V)), 0.0, 1.0), 2.2);',
    '  vec3 L = normalize(vec3(0.4, 0.8, 0.5)); float spec = pow(clamp(dot(reflect(-L, N), V), 0.0, 1.0), 40.0);',
    '  float top = smoothstep(0.6, 0.95, N.y); float side = 1.0 - abs(N.x) * 0.25;',
    '  vec3 col = uTint * side; col = mix(col, uInk, pow(fres, 2.6) * uInkK);',
    '  col += uRim * pow(fres, 1.5) * uRimK + vec3(1.0) * (spec * 0.8 + top * 0.1);',
    '  float a = uAlpha + fres * 0.5 + spec * 0.35 + top * 0.06;',
    '  gl_FragColor = vec4(col, clamp(a, 0.0, 1.0) * uFade);',
    '#include <fog_fragment>', '}'
  ].join('\n');
  // 发光的线（航线、时间轨、桥、分岔路）：沿长度“画出来”，带流动的虚线和亮头
  var FLOW_V = ['varying vec2 vUv;', '#include <fog_pars_vertex>',
    'void main(){ vUv = uv; vec4 mvPosition = modelViewMatrix * vec4(position, 1.0); gl_Position = projectionMatrix * mvPosition;', '#include <fog_vertex>', '}'].join('\n');
  var FLOW_F = [
    'uniform vec3 uCol; uniform float uReveal; uniform float uFrom; uniform float uFade; uniform float uDash; uniform float uFlow; uniform float uGlow; uniform float uHead;',
    'varying vec2 vUv;', '#include <fog_pars_fragment>',
    'void main(){ if (vUv.x > uReveal || vUv.x < uFrom) discard;',
    '  float head = (1.0 - smoothstep(0.0, 0.035, uReveal - vUv.x)) * step(uReveal, 0.998) * uHead;',
    '  float dash = uDash > 0.0 ? 0.5 + 0.5 * smoothstep(0.35, 0.5, fract(vUv.x * uDash - uFlow)) : 1.0;',
    '  vec3 c = uCol * (uGlow * dash + head * 2.4);',
    '  gl_FragColor = vec4(c, uFade * (0.82 + 0.18 * dash));', '#include <fog_fragment>', '}'
  ].join('\n');
  // 地面：点阵地图、每片下面的光斑；左右两半各一块（地图对折时分开）
  var GROUND_V = ['varying vec3 vW; varying vec3 vL;', '#include <fog_pars_vertex>',
    'void main(){ vL = position; vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; vec4 mvPosition = viewMatrix * w; gl_Position = projectionMatrix * mvPosition;', '#include <fog_vertex>', '}'].join('\n');
  var GROUND_F = [
    'uniform vec3 uBg; uniform vec3 uDot; uniform float uDotA; uniform vec3 uGlow; uniform vec3 uRing; uniform vec4 uPads[6]; uniform float uFade; uniform vec2 uCenter; uniform float uSeamX; uniform float uSeam;',
    'varying vec3 vW; varying vec3 vL;', NOISE, '#include <fog_pars_fragment>',
    'void main(){',
    '  vec2 g = vL.xy; vec2 cell = fract(g) - 0.5; float r = length(cell); float aa = max(fwidth(r), 1e-4);',
    '  float dotm = 1.0 - smoothstep(0.055 - aa, 0.055 + aa, r);',
    '  vec2 g10 = abs(fract(g / 8.0) - 0.5); float line = 1.0 - smoothstep(0.0, max(fwidth(g.x / 8.0) * 1.5, 1e-4), min(g10.x, g10.y));',
    '  float far = length(vW.xz - uCenter) / 62.0; float fade = 1.0 - smoothstep(0.55, 1.0, far);',
    '  float h = fbm(g * 0.045 + 7.3) * 7.0; float iso = abs(fract(h) - 0.5); float cont = 1.0 - smoothstep(0.0, max(fwidth(h) * 1.4, 1e-4), iso);',
    '  vec3 col = uBg * (1.0 - 0.07 * smoothstep(0.3, 1.0, far)); col = mix(col, uDot, (dotm * uDotA + line * uDotA * 0.25 + cont * uDotA * 0.32) * fade);',
    '  float glow = 0.0, ring = 0.0; for (int i = 0; i < 6; i++) { vec2 d = vW.xz - uPads[i].xy; float rr = length(d); float R = uPads[i].z;',
    '    glow += uPads[i].w * exp(-rr * rr / (R * R));',
    '    ring += uPads[i].w * ((1.0 - smoothstep(0.0, 0.07 + fwidth(rr), abs(rr - R * 1.12))) + 0.55 * (1.0 - smoothstep(0.0, 0.05 + fwidth(rr), abs(rr - R * 1.55)))); }',
    '  col += uGlow * glow * fade; col = mix(col, uRing, clamp(ring, 0.0, 1.0) * 0.75 * fade);',
    '  float sd = abs(vW.x - uSeamX); col += uGlow * uSeam * 2.2 * exp(-sd * 3.0) * fade;',
    '  gl_FragColor = vec4(col, 1.0);', '#include <fog_fragment>', '}'
  ].join('\n');
  // 2.5D 视差的配图：按深度图偏移取样（近处动得多），出现和消失用带亮边的噪声溶解（着色器转场）
  var PHOTO_V = ['varying vec2 vUv;', '#include <fog_pars_vertex>',
    'void main(){ vUv = uv; vec4 mvPosition = modelViewMatrix * vec4(position, 1.0); gl_Position = projectionMatrix * mvPosition;', '#include <fog_vertex>', '}'].join('\n');
  var PHOTO_F = [
    'uniform sampler2D uImg; uniform sampler2D uDep; uniform float uHasDep; uniform float uReveal; uniform float uFade; uniform vec2 uShift; uniform float uZoom; uniform float uFocus; uniform vec3 uEdge; uniform float uReady; uniform vec2 uSize; uniform float uBias;',
    'varying vec2 vUv;', NOISE, '#include <fog_pars_fragment>',
    'float sdR(vec2 p, vec2 b, float r){ vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }',
    'void main(){',
    '  vec2 c = vec2(0.5); vec2 uv = c + (vUv - c) / uZoom; vec2 p = uv;',
    '  if (uHasDep > 0.5) { for (int i = 0; i < 6; i++) { float d = texture2D(uDep, p).r - uFocus; p = uv - uShift * d; } }',
    '  vec3 col = texture2D(uImg, clamp(p, vec2(0.002), vec2(0.998)), uBias).rgb;',
    '  float n = fbm(vUv * vec2(3.2, 1.8) + 3.1) * 0.85 + vUv.x * 0.15;',
    '  float vis = 1.0 - smoothstep(uReveal - 0.025, uReveal + 0.025, n);',
    '  float rim = (1.0 - smoothstep(0.0, 0.05, abs(n - uReveal))) * step(0.002, uReveal) * step(uReveal, 0.998);',
    '  vec2 q = (vUv - 0.5) * uSize; float dd = sdR(q, uSize * 0.5, 0.45); float aa = max(fwidth(dd) * 1.2, 1e-4); float mask = 1.0 - smoothstep(-aa, aa, dd);',
    '  col = mix(col, vec3(1.0), rim * 0.55) + uEdge * rim * 0.9;',
    '  float a = clamp(vis + rim, 0.0, 1.0) * mask * uFade * uReady;',
    '  if (a < 0.003) discard;',
    '  gl_FragColor = vec4(col, a);', '#include <fog_fragment>', '}'
  ].join('\n');
  // 粒子（空气里的尘、下坠时溅起的碎屑、五千个点）
  var DUST_V = [
    'attribute vec3 aR; uniform float uTime; uniform float uSize; uniform float uPR;',
    'varying float vA;',
    'void main(){ vec3 p = position + vec3(sin(uTime * 0.11 + aR.x * 6.283) * 0.9, sin(uTime * 0.17 + aR.y * 6.283) * 0.45, cos(uTime * 0.13 + aR.z * 6.283) * 0.9);',
    '  vec4 mv = modelViewMatrix * vec4(p, 1.0); gl_Position = projectionMatrix * mv;',
    '  gl_PointSize = clamp(uSize * (0.6 + aR.x) * uPR * (60.0 / -mv.z), 1.0, 6.0); vA = smoothstep(260.0, 60.0, -mv.z) * smoothstep(5.0, 16.0, -mv.z) * (0.45 + 0.55 * aR.y); }'
  ].join('\n');
  var DOT_F = ['uniform vec3 uCol; uniform float uFade; varying float vA;',
    'void main(){ vec2 c = gl_PointCoord - 0.5; float r = length(c); float a = smoothstep(0.5, 0.15, r); if (a < 0.01) discard; gl_FragColor = vec4(uCol, a * vA * uFade); }'].join('\n');
  var STREAK_V = [
    'attribute vec3 aR; attribute float aEnd; uniform float uTime; uniform vec3 uVel;',
    'varying float vA;',
    'void main(){ vec3 p = position + vec3(sin(uTime * 0.11 + aR.x * 6.283) * 0.9, sin(uTime * 0.17 + aR.y * 6.283) * 0.45, cos(uTime * 0.13 + aR.z * 6.283) * 0.9);',
    '  p -= uVel * aEnd * (0.05 + 0.05 * aR.z); vec4 mv = modelViewMatrix * vec4(p, 1.0); gl_Position = projectionMatrix * mv; vA = (1.0 - aEnd * 0.9) * smoothstep(200.0, 30.0, -mv.z) * smoothstep(5.0, 14.0, -mv.z); }'
  ].join('\n');
  var STREAK_F = ['uniform vec3 uCol; uniform float uFade; varying float vA; void main(){ gl_FragColor = vec4(uCol, vA * uFade); }'].join('\n');
  var BURST_V = [
    'attribute vec3 aDir; attribute float aR; uniform float uT; uniform float uSize; uniform float uPR; uniform float uGrav;',
    'varying float vA;',
    'void main(){ float t = clamp(uT, 0.0, 1.0); vec3 p = position + aDir * (1.0 - pow(1.0 - t, 2.2)) * (0.6 + aR) + vec3(0.0, -uGrav * t * t, 0.0);',
    '  vec4 mv = modelViewMatrix * vec4(p, 1.0); gl_Position = projectionMatrix * mv; gl_PointSize = clamp(uSize * uPR * (40.0 / -mv.z) * (0.5 + aR), 1.0, 10.0);',
    '  vA = (1.0 - smoothstep(0.55, 1.0, t)) * step(0.001, t); }'
  ].join('\n');
  var SWARM_V = [
    'attribute vec3 aA; attribute vec3 aB; attribute vec4 aC; attribute float aR;',
    'uniform float uM1; uniform float uM2; uniform float uFlow; uniform float uSize; uniform float uPR; uniform vec3 uP[7]; uniform vec3 uC1; uniform vec3 uC2; uniform vec3 uC3; uniform float uLit;',
    'varying vec3 vC; varying float vA;',
    'vec3 bez(vec3 a, vec3 b, vec3 c, float u){ float v = 1.0 - u; return v * v * a + 2.0 * v * u * b + u * u * c; }',
    'void main(){',
    '  float d1 = smoothstep(0.0, 1.0, clamp(uM1 * 1.7 - aR * 0.7, 0.0, 1.0));',
    '  vec3 p = mix(aA, aB, d1) + vec3(sin(aR * 41.0 + uM1 * 5.0), cos(aR * 29.0 + uM1 * 4.0), sin(aR * 17.0 + uM1 * 3.0)) * sin(d1 * 3.14159) * 0.9;',
    '  vec3 col = mix(uC3, uC1, d1);',
    '  if (uM2 > 0.0) {',
    '    float s = fract(aC.y + uFlow); vec3 q;',
    '    if (s < 0.42) q = bez(uP[0], uP[1], uP[2], s / 0.42);',
    '    else { float u = (s - 0.42) / 0.58; q = aC.x < 0.5 ? bez(uP[2], uP[3], uP[4], u) : bez(uP[2], uP[5], uP[6], u); }',
    '    q += vec3(0.0, aC.w * 0.45 + 0.25, aC.z * 0.7);',
    '    float d2 = smoothstep(0.0, 1.0, clamp(uM2 * 1.6 - aR * 0.6, 0.0, 1.0));',
    '    p = mix(p, q, d2); col = mix(col, aC.x < 0.5 ? uC1 : uC2, d2);',
    '  }',
    '  vec4 mv = modelViewMatrix * vec4(p, 1.0); gl_Position = projectionMatrix * mv;',
    '  gl_PointSize = clamp(uSize * uPR * (30.0 / -mv.z) * (0.7 + aR * 0.6), 1.0, 9.0); vC = col * (1.0 + uLit * 0.6); vA = 1.0; }'
  ].join('\n');
  var SWARM_F = ['uniform float uFade; varying vec3 vC; varying float vA;',
    'void main(){ vec2 c = gl_PointCoord - 0.5; float r = length(c); float a = smoothstep(0.5, 0.2, r); if (a < 0.02) discard; gl_FragColor = vec4(vC, a * vA * uFade); }'].join('\n');

  /* =================================================================== 等轴测“供应链机器”（SVG）
   * 投影：屏幕 x = ox + (x − y)·cos30°，屏幕 y = oy + (x + y)·sin30° − z（等轴测，思路与 anatomy 的 iso-kit 相同，MIT）。
   * 可见三个面：顶面、朝 +y 的左前面、朝 +x 的右前面；按 x+y 由远到近画（画家算法）。 */
  // 等轴测"传播链"机器（SVG）：2–5 站沿 x 轴排开，传送带连起来；一件包裹按旁白一站站走（可被标红）。
  //   每站的 kind：source（发布者：顶上终端＋徽章）、store（商城：顶上摆货）、loop（循环箭头）、devices（一排排小电脑）、box（普通一站）
  var ST_KIND = { source: { w: 150, h: 70 }, store: { w: 190, h: 112 }, loop: { w: 150, h: 86 }, devices: { w: 250, h: 22 }, box: { w: 160, h: 90 } };
  function Machine(L, blk) {
    var ns = 'http://www.w3.org/2000/svg', C30 = Math.cos(30 * DEG), S30 = 0.5, OX = 300, OY = 250;
    var P = function (x, y, z) { return [OX + (x - y) * C30, OY + (x + y) * S30 - z]; };
    var pts = function (a) { return a.map(function (q) { var p = P(q[0], q[1], q[2]); return p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join(' '); };
    var mk = function (tag, attrs, parent) { var e = document.createElementNS(ns, tag); for (var k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
    var svg = mk('svg', { viewBox: '0 0 1600 900', 'aria-hidden': 'true' });
    var root = mk('g', {}, svg);
    var lines = [], faces = [];
    function box(g, x, y, z, w, d, h, cls) {
      var gg = mk('g', { 'class': cls || '' }, g);
      var top = [[x, y, z + h], [x + w, y, z + h], [x + w, y + d, z + h], [x, y + d, z + h]];
      var lf = [[x, y + d, z], [x + w, y + d, z], [x + w, y + d, z + h], [x, y + d, z + h]];
      var rt = [[x + w, y, z], [x + w, y + d, z], [x + w, y + d, z + h], [x + w, y, z + h]];
      faces.push(mk('polygon', { points: pts(lf), 'class': 'lf' }, gg));
      faces.push(mk('polygon', { points: pts(rt), 'class': 'rt' }, gg));
      faces.push(mk('polygon', { points: pts(top), 'class': 'top' }, gg));
      var o = [[x, y + d, z], [x + w, y + d, z], [x + w, y, z], [x + w, y, z + h], [x, y, z + h], [x, y + d, z + h], [x, y + d, z]];
      var e = [[x, y + d, z + h], [x + w, y + d, z + h], [x + w, y, z + h]];
      var e2 = [[x + w, y + d, z + h], [x + w, y + d, z]];
      [o, e, e2].forEach(function (a) { var pl = mk('polyline', { points: pts(a), 'class': 'ln', pathLength: '1' }, gg); lines.push(pl); });
      return gg;
    }
    function text(x, y, z, str, cls, dy) { var p = P(x, y, z); var t = mk('text', { x: p[0].toFixed(1), y: (p[1] + (dy || 0)).toFixed(1), 'class': cls, 'text-anchor': 'middle' }, root); t.textContent = str; return t; }
    // 布局（等轴测单位≈像素）：各站沿 x 轴排开，总长约 1200
    var src = (blk.stations || []).slice(0, 5), n = Math.max(2, src.length);
    var dims = src.map(function (s) { return ST_KIND[s.kind] || ST_KIND.box; });
    var sumW = dims.reduce(function (a, d) { return a + d.w; }, 0), gap = Math.max(80, (1200 - sumW) / Math.max(1, src.length - 1));
    var ST = [], cx = 0;
    src.forEach(function (s, i) { ST.push({ x: cx, w: dims[i].w, h: dims[i].h, kind: ST_KIND[s.kind] ? s.kind : 'box', name: tx(s.name, L), cap: tx(s.cap, L) }); cx += dims[i].w + gap; });
    var gBase = mk('g', {}, root);
    var belts = [];
    for (var i = 0; i < ST.length - 1; i++) {
      var x0 = ST[i].x + ST[i].w, x1 = ST[i + 1].x;
      var bg = box(gBase, x0, 50, 0, x1 - x0, 50, 12, 'belt-g');
      bg.querySelectorAll('polygon').forEach(function (p) { p.setAttribute('class', p.getAttribute('class') + ' belt'); });
      belts.push(mk('polyline', { points: pts([[x0, 75, 13], [x1, 75, 13]]), 'class': 'flow' }, gBase));
    }
    var stations = ST.map(function (s) {
      var g = mk('g', { 'class': 'st' }, root);
      if (s.kind !== 'devices') box(g, s.x, 0, 0, s.w, 150, s.h);
      return g;
    });
    var badge = null, arrows = [], screens = [], devBox = null, scrPos = [];
    ST.forEach(function (s, k) {
      var g = stations[k];
      if (s.kind === 'source') {                       // 顶上的终端和徽章
        box(g, s.x + 40, 40, s.h, 70, 70, 46, 'term');
        if (blk.badge) {
          var bp = P(s.x + 110, 75, s.h + 25);
          badge = mk('g', { 'class': 'badge' }, g);
          mk('rect', { x: (bp[0] + 6).toFixed(1), y: (bp[1] - 15).toFixed(1), width: 68, height: 30, rx: 15 }, badge);
          var bt = mk('text', { x: (bp[0] + 40).toFixed(1), y: (bp[1] + 6).toFixed(1), 'text-anchor': 'middle' }, badge); bt.textContent = tx(blk.badge, L);
        }
      } else if (s.kind === 'store') {                 // 顶上摆着几件货
        for (var j = 0; j < 3; j++) box(g, s.x + 20 + j * 55, 20, s.h, 34, 34, 22, 'goods');
      } else if (s.kind === 'loop') {                  // 顶面上一圈循环箭头
        var c3 = P(s.x + s.w / 2, 75, s.h);
        var arrow = mk('ellipse', { cx: c3[0].toFixed(1), cy: c3[1].toFixed(1), rx: 62, ry: 36, 'class': 'arrow' }, g);
        var head = mk('path', { d: 'M' + (c3[0] + 62) + ' ' + (c3[1] - 8) + ' l 9 14 l -17 1 z', fill: 'currentColor', 'class': 'ahead' }, g);
        head.style.color = 'var(--v3-acc)';
        arrows.push({ el: arrow, head: head, k: k });
      } else if (s.kind === 'devices') {               // 4 列 × 3 行小电脑，屏幕会被"点亮"
        var devs = mk('g', {}, g);
        for (var r = 0; r < 3; r++) {
          for (var c = 0; c < 4; c++) {
            var dx = s.x + c * 62, dy = 5 + r * 50;
            box(devs, dx, dy, 0, 44, 34, 6, 'lap');
            var scr = mk('polygon', { points: pts([[dx + 4, dy + 2, 6], [dx + 40, dy + 2, 6], [dx + 40, dy + 2, 34], [dx + 4, dy + 2, 34]]), 'class': 'scr' }, devs);
            lines.push(mk('polyline', { points: pts([[dx + 4, dy + 2, 6], [dx + 4, dy + 2, 34], [dx + 40, dy + 2, 34], [dx + 40, dy + 2, 6]]), 'class': 'ln', pathLength: '1' }, devs));
            screens.push(scr); scrPos.push(P(dx + 22, dy + 2, 22));
          }
        }
        var p1 = P(s.x, 5, 0), p2 = P(s.x + 3 * 62 + 44, 5 + 2 * 50 + 34, 0), p3 = P(s.x + 3 * 62 + 44, 5, 34), p4 = P(s.x, 5 + 2 * 50 + 34, 34);
        devBox = { x0: Math.min(p1[0], p2[0], p3[0], p4[0]), x1: Math.max(p1[0], p2[0], p3[0], p4[0]), y0: Math.min(p1[1], p2[1], p3[1], p4[1]), y1: Math.max(p1[1], p2[1], p3[1], p4[1]) };
      }
    });
    // 站名和说明
    var labs = ST.map(function (s) {
      var cx2 = s.x + s.w / 2, top = s.kind === 'source' ? s.h + 46 : (s.kind === 'devices' ? 40 : s.h);
      var g = mk('g', {}, root);
      g.appendChild(text(cx2, 0, top + 60, s.name, 'lab')); g.appendChild(text(cx2, 0, top + 60, s.cap, 'cap', 30));
      return g;
    });
    // 包裹走的路：每站顶上 → 传送带中点 → 下一站顶上
    var tops = ST.map(function (s) {
      if (s.kind === 'source') return [s.x + 75, 75, s.h + 47];
      if (s.kind === 'devices') return [s.x + 110, 75, 26];
      return [s.x + (s.kind === 'loop' ? 75 : s.w / 2), 75, s.h + 2];
    });
    var mids = []; for (var m2 = 0; m2 < ST.length - 1; m2++) mids.push([(ST[m2].x + ST[m2].w + ST[m2 + 1].x) / 2, 75, 14]);
    function at(p) {    // p：0 … 站数−1（第几站，可以是小数）
      var last = ST.length - 1; p = clamp(p, 0, last);
      var j = Math.min(Math.floor(p), last - 1), f = p - j;
      if (last < 1) return tops[0];
      var a = tops[j], b = mids[j], c = tops[j + 1];
      var l1 = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]), l2 = Math.hypot(c[0] - b[0], c[1] - b[1], c[2] - b[2]), s = f * (l1 + l2);
      if (s <= l1) { var u = s / Math.max(1e-6, l1); return [lerp(a[0], b[0], u), lerp(a[1], b[1], u), lerp(a[2], b[2], u)]; }
      var v = (s - l1) / Math.max(1e-6, l2); return [lerp(b[0], c[0], v), lerp(b[1], c[1], v), lerp(b[2], c[2], v)];
    }
    function pkg(cls) { var g = mk('g', { 'class': 'pkg ' + (cls || '') }, root); box(g, -14, -14, 0, 28, 28, 24); return g; }
    var flow = [pkg(), pkg(), pkg()];
    var bad = pkg('main');
    var tag = mk('text', { 'class': 'tagbad', 'text-anchor': 'end' }, root); tag.textContent = tx(blk.tag, L);
    var sparks = [];
    if (devBox) for (var q = 0; q < 12; q++) sparks.push(mk('circle', { r: 4.5, fill: 'var(--v3-warn)' }, root));
    this.svg = svg; this.lines = lines; this.faces = faces; this.labs = labs; this.belts = belts; this.arrows = arrows;
    this.screens = screens; this.scrPos = scrPos; this.flow = flow; this.bad = bad; this.tag = tag; this.sparks = sparks; this.badge = badge; this.P = P; this.at = at;
    this.stations = stations; this.n = ST.length;
    // 最后一站在 SVG 里的范围（给三维的点当起点）；不是电脑那种站，就用最后一站的顶面
    var lt = tops[ST.length - 1], lp = P(lt[0], lt[1], lt[2]);
    this.devBox = devBox || { x0: lp[0] - 60, x1: lp[0] + 60, y0: lp[1] - 30, y1: lp[1] + 20 };
    this.pub = P(tops[0][0], tops[0][1], tops[0][2]);
  }
  // 按时间摆好机器（k：draw、start、mark、hops[第 1…n−1 站到达]）
  Machine.prototype.update = function (t, k, rm) {
    var i, ln = this.lines, draw = sat((t - k.draw) / 1.8), n = this.n, hops = k.hops || [];
    for (i = 0; i < ln.length; i++) { var u = sat(draw * 1.6 - i / ln.length * 0.6); ln[i].style.strokeDasharray = '1'; ln[i].style.strokeDashoffset = (1 - u).toFixed(3); }
    var fa = sat((t - k.draw - 0.5) / 1.2);
    for (i = 0; i < this.faces.length; i++) this.faces[i].style.opacity = fa.toFixed(3);
    for (i = 0; i < this.labs.length; i++) this.labs[i].style.opacity = sat((t - k.draw - 0.6 - i * 0.25) / 0.5).toFixed(3);
    var fl = rm ? 0 : t * 1.8;
    for (i = 0; i < this.belts.length; i++) { this.belts[i].style.strokeDashoffset = (-fl * 10).toFixed(1); this.belts[i].style.opacity = fa.toFixed(3); }
    for (i = 0; i < this.arrows.length; i++) {
      var ar = this.arrows[i], ht = hops[ar.k - 1] != null ? hops[ar.k - 1] : Infinity;
      ar.el.style.strokeDashoffset = (t > ht && !rm ? -(t - ht) * 60 : 0).toFixed(1);
      ar.el.style.opacity = ar.head.style.opacity = fa.toFixed(3);
    }
    var o0 = this.P(0, 0, 0);
    // 普通包裹：循环走
    for (i = 0; i < this.flow.length; i++) {
      var on = t > k.start + 0.6 ? 1 : 0, u2 = ((t - k.start) * 0.11 + i / 3) % 1, p = this.at(u2 * (n - 1)), sp = this.P(p[0], p[1], p[2]);
      this.flow[i].setAttribute('transform', 'translate(' + (sp[0] - o0[0]).toFixed(1) + ' ' + (sp[1] - o0[1]).toFixed(1) + ')');
      this.flow[i].style.opacity = (on * fa * (u2 > 0.96 ? 0 : 1) * 0.85).toFixed(3);
    }
    // 被盯上的那一件：第 j 站到达时刻前后走过去（第一段 1.6 秒，中间 1.2 秒提前 0.3，最后 1.0 秒提前 0.1）
    var pb = 0, lastHop = hops.length ? hops[hops.length - 1] : k.start + 3;
    for (var j = 1; j <= hops.length; j++) {
      var h = hops[j - 1], st = j === 1 ? h : (j === hops.length ? h - 0.1 : h - 0.3), du = j === 1 ? 1.6 : (j === hops.length ? 1.0 : 1.2);
      if (t > st) pb = Math.max(pb, (j - 1) + out3((t - st) / du));
    }
    var pbp = this.at(pb), sb = this.P(pbp[0], pbp[1], pbp[2]);
    var shake = (k.mark != null && t > k.mark && t < k.mark + 0.6 && !rm) ? Math.sin(t * 90) * 4 * (1 - (t - k.mark) / 0.6) : 0;
    this.bad.setAttribute('transform', 'translate(' + (sb[0] - o0[0] + shake).toFixed(1) + ' ' + (sb[1] - o0[1]).toFixed(1) + ')');
    var arrived = t > lastHop + 0.9;
    this.bad.style.opacity = (t > k.start ? (arrived ? 1 - sat((t - lastHop - 0.9) / 0.4) : 1) : 0).toFixed(3);
    var marked = k.mark != null && t > k.mark;
    this.bad.classList.toggle('bad', marked);
    this.tag.setAttribute('x', (sb[0] - 34 + shake).toFixed(1)); this.tag.setAttribute('y', (sb[1] - 4).toFixed(1));
    this.tag.style.opacity = (marked ? sat((t - k.mark) / 0.4) * (arrived ? 1 - sat((t - lastHop - 0.9) / 0.4) : 1) : 0).toFixed(3);
    // 徽章光扫（离开第一站时）
    if (this.badge) {
      var h0 = hops[0], bs = h0 != null && t > h0 && t < h0 + 1.4 ? Math.sin((t - h0) / 1.4 * Math.PI) : 0;
      this.badge.style.filter = bs > 0.01 ? 'drop-shadow(0 0 ' + (10 * bs).toFixed(1) + 'px rgb(var(--v3-acc-rgb)))' : '';
    }
    // 到了最后一站（电脑）：火花散开，屏幕依次变红
    if (this.sparks.length) {
      var sp0 = this.at(n - 1), base = this.P(sp0[0], sp0[1], sp0[2]);
      for (i = 0; i < this.sparks.length; i++) {
        var tt = sat((t - lastHop - 0.8) / 0.9), tgt = this.scrPos[i % this.scrPos.length];
        this.sparks[i].setAttribute('cx', lerp(base[0], tgt[0], out3(tt)).toFixed(1));
        this.sparks[i].setAttribute('cy', (lerp(base[1], tgt[1], out3(tt)) - Math.sin(tt * Math.PI) * 40).toFixed(1));
        this.sparks[i].style.opacity = (tt > 0 && tt < 1 && marked ? 1 : 0).toFixed(2);
      }
      for (i = 0; i < this.screens.length; i++) this.screens[i].classList.toggle('hit', marked && t > lastHop + 1.4 + i * 0.06);
    }
  };

  /* =================================================================== 三维世界 */
  // 地图上的位置（世界坐标，y 朝上，地面 y=0）：故事线按顺序放进 SLOTS（前两片在左半边、后两片在右半边），对照放在中间偏前；SEAM 是对折的中缝
  var SLOTS = [[-26, 0, 6], [-6, 0, -12], [14, 0, 4], [32, 0, -10]], CPOS = [3, 0, 12];
  var SEAM = 3, MAPC = [3, 0, -2];
  function slotsFor(n) { return n >= 4 ? [0, 1, 2, 3] : (n === 3 ? [0, 1, 2] : (n === 2 ? [1, 2] : [1])); }

  function World(P) {
    this.P = P; this.v = P.v; this.L = []; this.upd = [];
    THREE = window.THREE; PP = window.POSTPROCESSING;
    this.tmp = new THREE.Vector3(); this.tmp2 = new THREE.Vector3();
    // 配乐的拍点（video3_build.py 按配乐写进 music.beats）：镜头落点对到拍子上；没有配乐时原样返回
    var mu = P.v.music || {};
    this.beats = (mu.beats || []).slice().sort(function (a, b) { return a - b; });
    this.beat = mu.bpm ? 60 / mu.bpm : 0.6;
  }
  var W = World.prototype;
  // 离 t 最近的拍点（最多挪半拍）；没有拍点就是 t 本身
  W.Q = function (t) {
    var bs = this.beats, best = t, dmin = this.beat / 2 + 1e-6;
    for (var i = 0; i < bs.length; i++) { var dd = Math.abs(bs[i] - t); if (dd < dmin) { dmin = dd; best = bs[i]; } }
    return best;
  };

  W.palette = function (dark) {
    var acc = this.P.accRGB;
    var c = new THREE.Color('rgb(' + acc.join(',') + ')');
    var pal = {
      dark: dark, acc: c, accHex: '#' + c.getHexString(),
      bg: dark ? '#0d0b09' : '#f3efe8', dot: dark ? '#f3e9db' : '#5b4630', dotA: dark ? 0.14 : 0.3,
      glass: new THREE.Color(dark ? '#2a241e' : '#ffffff'), glassTop: new THREE.Color(dark ? '#3d342b' : '#fff9f0'),
      boxTint: new THREE.Color(dark ? '#3a3129' : '#f6efe4'),
      glassA: dark ? 0.32 : 0.36, warn: new THREE.Color(dark ? '#ff8a72' : '#d04a35'), alt: new THREE.Color(dark ? '#ffa080' : '#e2683a'),
      ink: new THREE.Color(dark ? '#f5efe6' : '#3a2f22'), shadow: dark ? 0.55 : 0.2
    };
    pal.glow = c.clone().multiplyScalar(dark ? 0.9 : 0.42);
    return pal;
  };

  W.makeGlow = function () {
    var cv = document.createElement('canvas'); cv.width = cv.height = 128;
    var g = cv.getContext('2d'), gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.25, 'rgba(255,255,255,.55)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
    var t = new THREE.CanvasTexture(cv); return t;
  };

  /* ---------- 材质 ---------- */
  W.fogU = function (u) { return THREE.UniformsUtils.merge([THREE.UniformsLib.fog, u]); };
  W.panelMat = function (w, h, o) {
    o = o || {}; var p = this.pal;
    return new THREE.ShaderMaterial({
      uniforms: this.fogU({ uTint: { value: p.glass.clone() }, uTop: { value: p.glassTop.clone() }, uEdge: { value: p.acc.clone().multiplyScalar(o.edge || 1.3) },
        uInk: { value: p.ink.clone() }, uInkK: { value: p.dark ? 0.0 : 0.35 },
        uAlpha: { value: o.alpha != null ? o.alpha : p.glassA }, uFade: { value: o.fade != null ? o.fade : 1 }, uSize: { value: new THREE.Vector2(w, h) },
        uRadius: { value: o.radius || 0.45 }, uSheen: { value: -1 }, uEdgeGlow: { value: o.edgeGlow != null ? o.edgeGlow : 0.9 } }),
      vertexShader: PANEL_V, fragmentShader: PANEL_F, transparent: true, depthWrite: false, side: THREE.DoubleSide, fog: true
    });
  };
  W.boxMat = function (o) {
    o = o || {}; var p = this.pal;
    return new THREE.ShaderMaterial({
      uniforms: this.fogU({ uTint: { value: (o.tint || p.boxTint).clone() }, uRim: { value: (o.rim || p.acc).clone() }, uInk: { value: p.ink.clone() }, uInkK: { value: p.dark ? 0.0 : 0.42 },
        uAlpha: { value: o.alpha != null ? o.alpha : 0.2 }, uFade: { value: o.fade != null ? o.fade : 1 }, uRimK: { value: o.rimK != null ? o.rimK : (p.dark ? 1.1 : 0.55) } }),
      vertexShader: BOX_V, fragmentShader: BOX_F, transparent: true, depthWrite: false, side: THREE.DoubleSide, fog: true
    });
  };
  W.flowMat = function (col, o) {
    o = o || {};
    return new THREE.ShaderMaterial({
      uniforms: this.fogU({ uCol: { value: col.clone() }, uReveal: { value: o.reveal != null ? o.reveal : 0 }, uFrom: { value: 0 }, uFade: { value: 1 }, uDash: { value: o.dash || 0 },
        uFlow: { value: 0 }, uGlow: { value: o.glow || 1.6 }, uHead: { value: o.head != null ? o.head : 1 } }),
      vertexShader: FLOW_V, fragmentShader: FLOW_F, transparent: true, depthWrite: false, fog: true
    });
  };
  W.coreMat = function (col, k) {
    return new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: k != null ? k * (this.pal.dark ? 0.75 : 1) : (this.pal.dark ? 0.85 : 0.22), roughness: 0.32, metalness: 0.0, transparent: true, opacity: 1 });
  };
  W.tube = function (pts, r, mat, seg) {
    var curve = pts.length === 2 ? new THREE.LineCurve3(pts[0], pts[1]) : new THREE.CatmullRomCurve3(pts, false, 'centripetal');
    var m = new THREE.Mesh(new THREE.TubeGeometry(curve, seg || 240, r, 8, false), mat);
    m.userData.curve = curve; m.renderOrder = 2;
    return m;
  };
  W.glow = function (size, col, op) {
    var m = new THREE.SpriteMaterial({ map: this.glowTex, color: col || this.pal.acc, transparent: true, opacity: op != null ? op : (this.pal.dark ? 0.8 : 0.45), depthWrite: false,
      blending: this.pal.dark ? THREE.AdditiveBlending : THREE.NormalBlending });
    var s = new THREE.Sprite(m); s.scale.set(size, size, 1); s.renderOrder = 3; return s;
  };
  W.gk = function (v) { return v * (this.pal.dark ? 1 : 0.6); };
  // 接触阴影：物体脚下一块柔和的暗斑，让东西“站”在地图上
  W.shadow = function (w, d, parent, x, z, k) {
    if (!this.shadowTex) {
      var cv = document.createElement('canvas'); cv.width = cv.height = 128; var g = cv.getContext('2d'), gr = g.createRadialGradient(64, 64, 4, 64, 64, 64);
      gr.addColorStop(0, 'rgba(0,0,0,1)'); gr.addColorStop(0.45, 'rgba(0,0,0,.45)'); gr.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
      this.shadowTex = new THREE.CanvasTexture(cv);
    }
    var m = new THREE.Mesh(new THREE.PlaneGeometry(w, d), new THREE.MeshBasicMaterial({ map: this.shadowTex, color: this.pal.dark ? 0x000000 : 0x3a2a14, transparent: true, opacity: this.pal.shadow * (k || 1), depthWrite: false }));
    m.rotation.x = -Math.PI / 2; m.position.set(x || 0, 0.03, z || 0); m.renderOrder = 1; parent.add(m); return m;
  };
  // 细描边：玻璃体外面一圈很淡的线（和安全一章的等轴测线稿同一种笔触）
  W.outline = function (w, h, d, parent, y, a) {
    var m = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(w, h, d)), new THREE.LineBasicMaterial({ color: this.pal.ink, transparent: true, opacity: a != null ? a : (this.pal.dark ? 0.35 : 0.42), depthWrite: false }));
    m.position.y = y; parent.add(m); return m;
  };
  // 只描正面那一个框（11-06，柱状图用）：透明玻璃把前后 12 条棱全画出来，镜头带一点俯角、偏角时前后两个框错开，像套印没对准
  W.outlineFront = function (w, h, d, parent, y, a) {
    var x = w / 2, yy = h / 2, z = d / 2 + 0.002, v = [-x, -yy, z, x, -yy, z, x, -yy, z, x, yy, z, x, yy, z, -x, yy, z, -x, yy, z, -x, -yy, z];
    var g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(v), 3));
    var m = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: this.pal.ink, transparent: true, opacity: a != null ? a : (this.pal.dark ? 0.35 : 0.42), depthWrite: false }));
    m.position.y = y; parent.add(m); return m;
  };
  // 上沿不封口的描边（11-06 白天补，刻度尺 open_top 用）：不画顶面四条棱，四条竖棱往上接三小段虚线——
  // 材料没说最上面那一档就是顶格时（11-06 只说 GPT-6 Cyber 从 High 升到 Critical），刻度尺不画成封顶的盒子
  W.outlineOpenTop = function (w, h, d, parent, y, a) {
    var x = w / 2, t = h / 2, z = d / 2, v = [], seg = function (p, q) { v.push(p[0], p[1], p[2], q[0], q[1], q[2]); };
    [[-x, -z], [x, -z], [x, z], [-x, z]].forEach(function (c, i, all) {
      var n = all[(i + 1) % 4];
      seg([c[0], -t, c[1]], [n[0], -t, n[1]]);                 // 底面
      seg([c[0], -t, c[1]], [c[0], t, c[1]]);                  // 竖棱
      [[0.16, 0.36], [0.5, 0.62], [0.74, 0.8]].forEach(function (u) { seg([c[0], t + u[0], c[1]], [c[0], t + u[1], c[1]]); });
    });
    var g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(v), 3));
    var m = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: this.pal.ink, transparent: true, opacity: a != null ? a : (this.pal.dark ? 0.35 : 0.42), depthWrite: false }));
    m.position.y = y; parent.add(m); return m;
  };
  W.burst = function (n, origin, spread, o) {
    o = o || {};
    var g = new THREE.BufferGeometry(), pos = new Float32Array(n * 3), dir = new Float32Array(n * 3), r = new Float32Array(n);
    for (var i = 0; i < n; i++) {
      pos[i * 3] = origin.x + (rnd(i * 3 + 1) - 0.5) * spread.x; pos[i * 3 + 1] = origin.y + (rnd(i * 3 + 2) - 0.5) * spread.y; pos[i * 3 + 2] = origin.z + (rnd(i * 3 + 3) - 0.5) * spread.z;
      var a = rnd(i * 7 + 5) * Math.PI * 2, e = (rnd(i * 7 + 6) - 0.2) * 1.4;
      dir[i * 3] = Math.cos(a) * (o.out || 1.6); dir[i * 3 + 1] = e * (o.up || 1.2); dir[i * 3 + 2] = Math.sin(a) * (o.out || 1.6); r[i] = rnd(i * 11 + 9);
    }
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('aDir', new THREE.BufferAttribute(dir, 3)); g.setAttribute('aR', new THREE.BufferAttribute(r, 1));
    var m = new THREE.ShaderMaterial({ uniforms: { uT: { value: 0 }, uSize: { value: o.size || 3.2 }, uPR: { value: this.pr }, uGrav: { value: o.grav != null ? o.grav : 2.2 }, uCol: { value: (o.col || this.pal.acc).clone() }, uFade: { value: 1 } },
      vertexShader: BURST_V, fragmentShader: DOT_F, transparent: true, depthWrite: false, blending: this.pal.dark ? THREE.AdditiveBlending : THREE.NormalBlending });
    var pts = new THREE.Points(g, m); pts.frustumCulled = false; pts.renderOrder = 4; return pts;
  };

  /* ---------- 标签（HTML 投影到三维） ---------- */
  W.label = function (html, o) {
    var e = el('div', 'v3l ' + (o.align ? 'al-' + o.align : '') + (o.cls ? ' ' + o.cls : ''), '<div class="in">' + html + '</div>');
    if (this.P.wb) wbWalk(this.P.wb, e, false);     // 11-09：中文整词换行（量尺寸、排版之前插好换行点）
    this.P.worldEl.appendChild(e);
    var lb = { el: e, inEl: e.firstChild, obj: o.obj || null, at: o.at ? o.at.clone() : new THREE.Vector3(), a: o.a || 0, shot: o.shot || null, ref: o.ref || 0,
      min: o.min != null ? o.min : 0.5, max: o.max != null ? o.max : 1.25, fixed: !!o.fixed, edge: o.edge !== false, _s: '', _o: -1, fitW: o.fitW || 0, fitH: o.fitH || 0, keep: !!o.keep, fit: !!o.fit, tight: !!o.tight,
      sideX: /^(r|tr)$/.test(o.align || '') ? -1 : (/^(l|bl|tl)$/.test(o.align || '') ? 1 : 0),
      sideY: o.align === 'b' ? 1 : 0,     // 只给"卡片在锚点上方"的（热点卡）做互相让开
      topY: /^(t|tl|tr)$/.test(o.align || '') };   // 卡片在锚点下方（keep 的卡片上下挪回画面时用）
    this.L.push(lb);
    return lb;
  };
  // 飘在三维里的标志小签（柱子两边、小卡上沿、刻度尺的标记上）：每一帧轻轻上下浮动
  W.floatChip = function (html, o) {
    if (!html) return null;
    var lb = this.label('<div class="v3lrow">' + html + '</div>', { obj: o.obj, at: o.at, shot: o.shot, align: o.align || '' });
    var fl = this.floaters || (this.floaters = []);
    lb.bob = { y: o.at.y, ph: fl.length * 1.37 + 0.4, amp: o.amp != null ? o.amp : 0.06 };
    fl.push(lb);
    return lb;
  };
  // 飘着的小签出场：整张淡入，里面每个标志按自己的时刻弹出
  W.showChips = function (a, lb, list, t0, hideAt) {
    if (!lb) return;
    a.show(lb, t0, 0.4);
    popLogos(a, lb.inEl, list, t0 - 0.1, 0.16);
    if (hideAt != null) a.hide(lb, hideAt, 0.35);
  };
  W.labelWorld = function (lb, out) {
    out.copy(lb.at);
    if (lb.obj) lb.obj.localToWorld(out);
    return out;
  };
  W.updateLabels = function () {
    var cam = this.camera, w = this.P.sw, h = this.P.sh, v = this.tmp, kept = [];
    for (var i = 0; i < this.L.length; i++) {
      var lb = this.L[i];
      if (lb.a <= 0.003) { if (lb._o !== 0) { lb.el.style.opacity = '0'; lb.el.style.visibility = 'hidden'; lb._o = 0; } continue; }
      this.labelWorld(lb, v);
      var dist = v.distanceTo(cam.position);
      v.project(cam);
      if (v.z > 1 || v.z < -1) { if (lb._o !== 0) { lb.el.style.opacity = '0'; lb.el.style.visibility = 'hidden'; lb._o = 0; } continue; }
      var x = (v.x * 0.5 + 0.5) * w, y = (-v.y * 0.5 + 0.5) * h;
      var s = lb.fixed || !lb.ref ? 1 : clamp(lb.ref / dist, lb.min, lb.max);
      if (lb.keep || lb.fit) { // 热点卡、国内外两边的标题、时间轨的日子（fit）：整张卡留在画面里（竖屏时地图两端的卡不被切掉）
        var bw = (lb._bw || (lb._bw = lb.inEl.offsetWidth || 0)) * s, bh = (lb._bh || (lb._bh = lb.inEl.offsetHeight || 0)) * s, mg = 6;
        var sx = lb.sideX;   // 卡片在锚点哪一边：−1 左边（align r），0 居中，1 右边（align l）
        if (bw && bw < w - 2 * mg && x >= 0 && x <= w) x = clamp(x, mg + (sx < 0 ? bw : sx > 0 ? 0 : bw / 2), w - mg - (sx > 0 ? bw : sx < 0 ? 0 : bw / 2));
        // 上下也一样（11-05 补）：锚点在画面里、卡片却伸出上沿或下沿时，挪回画面里（11-04 国内外章"初创公司融资"贴着上沿、切掉一半）
        var vy = lb.sideY > 0 ? -1 : (lb.topY ? 1 : 0);   // 卡片在锚点哪一边：−1 上边（align b），1 下边（align t），0 居中
        if (bh && bh < h - 2 * mg && y >= 0 && y <= h) y = clamp(y, mg + (vy < 0 ? bh : vy > 0 ? 0 : bh / 2), h - mg - (vy > 0 ? bh : vy < 0 ? 0 : bh / 2));
        if (lb.keep && lb.sideY > 0) kept.push({ lb: lb, x: x, y: y, s: s, bw: bw, bh: bh });
      }
      lb._x = x; lb._y = y; lb._sc = s;
      var ef = 1;
      if (lb.edge) { var mx = Math.min(x, w - x) / (w * 0.06), my = Math.min(y, h - y) / (h * 0.06); ef = sat(Math.min(mx, my) + 0.15); }
      var o = lb.a * ef;
      var tr = 'translate3d(' + x.toFixed(1) + 'px,' + y.toFixed(1) + 'px,0) scale(' + s.toFixed(3) + ')';
      if (tr !== lb._s) { lb.el.style.transform = tr; lb._s = tr; }
      var os = o < 0.004 ? 0 : Math.round(o * 1000) / 1000;
      if (os !== lb._o) { lb.el.style.opacity = String(os); lb.el.style.visibility = os ? 'visible' : 'hidden'; lb._o = os; }
    }
    // 时间轨的日子标签（11-05 补）：同一侧相邻两张在画面上叠住时（竖屏的标签相对画面宽一倍），后一张错开一行——
    // 轨道上方的往上、下方的往下；按从左到右排，每张放进第一个不和它叠住的行
    (this.tlRows || []).forEach(function (grp) {
      var rows = [];
      grp.lbs.forEach(function (lb) {
        if (!lb._o) return;
        var bw = (lb._bw || (lb._bw = lb.inEl.offsetWidth || 0)) * lb._sc, bh = (lb._bh || (lb._bh = lb.inEl.offsetHeight || 0)) * lb._sc;
        var x0 = lb._x - bw / 2, r = 0;
        while (r < rows.length && rows[r] > x0 - 6) r++;
        rows[r] = lb._x + bw / 2;
        if (!r) return;
        var t2 = 'translate3d(' + lb._x.toFixed(1) + 'px,' + (lb._y + grp.dir * r * (bh + 4)).toFixed(1) + 'px,0) scale(' + lb._sc.toFixed(3) + ')';
        if (t2 !== lb._s) { lb.el.style.transform = t2; lb._s = t2; }
      });
    });
    // 热点卡互相压住时（竖屏的全图里，安全和"对照与接下来"挨得很近），把靠下的那张往下让开
    if (kept.length > 1) {
      kept.sort(function (a, b) { return a.y - b.y; });
      for (var m = 1; m < kept.length; m++) {
        var k = kept[m], moved = false;
        for (var n = 0; n < m; n++) {
          var j = kept[n];
          if (j.lb._o === 0 || k.lb._o === 0) continue;
          var ox = Math.min(j.x + j.bw / 2, k.x + k.bw / 2) - Math.max(j.x - j.bw / 2, k.x - k.bw / 2);
          var oy = j.y - (k.y - k.bh);
          if (ox > 0 && oy > 0) { k.y = Math.min(h - 4, k.y + oy + 4); moved = true; }
        }
        if (moved) { var t2 = 'translate3d(' + k.x.toFixed(1) + 'px,' + k.y.toFixed(1) + 'px,0) scale(' + k.s.toFixed(3) + ')'; if (t2 !== k.lb._s) { k.lb.el.style.transform = t2; k.lb._s = t2; } }
      }
    }
  };
  // 标签的“参考距离”：镜头在它那一镜（按当前画幅算出的位置）时，标签缩放正好是 1
  W.refLabels = function () {
    var v = this.tmp, sh = this.P.sh || 540;
    for (var i = 0; i < this.L.length; i++) {
      var lb = this.L[i]; lb._bw = 0; lb._bh = 0; if (!lb.shot) continue;
      this.labelWorld(lb, v); var dist = v.distanceTo(this.shotPos(lb.shot)); lb.ref = dist;
      if (lb.fitW) { // HTML 卡片按三维玻璃板在那一镜里的大小定宽（字号仍按舞台宽度走）；竖屏时卡片放宽到接近舞台宽度
        var ppu = sh / (2 * dist * Math.tan(lb.shot.fov * DEG / 2)), ch = lb.inEl.firstElementChild, sw = this.P.sw || 960;
        var portrait = sw < sh, wpx = lb.fitW * ppu, hpx = lb.fitH * ppu;
        if (portrait && !lb.tight) { var k = Math.max(1, sw * (lb.fitH ? 0.9 : 0.86) / wpx); wpx *= k; hpx = lb.fitH ? 0 : 0; if (ch && ch.classList.contains('v3machine-box')) hpx = wpx * 900 / 1600; }
        if (ch) { ch.style.width = wpx.toFixed(1) + 'px'; ch.style.height = hpx ? hpx.toFixed(1) + 'px' : ''; }
      }
    }
  };

  /* ---------- 镜头：每一镜＝看向哪里、从哪个方向、要装下多大；位置按当前画幅现算 ---------- */
  W.shot = function (c, yaw, pitch, fw, fh, o) {
    o = o || {};
    return { c: V3(c[0], c[1], c[2]), yaw: yaw * DEG, pitch: pitch * DEG, fw: fw, fh: fh, fov: o.fov || 34, pad: o.pad || 1.0,
      pk: o.pk || 0.74, pc: o.pc ? V3(o.pc[0], o.pc[1], o.pc[2]) : null };   // pk：竖屏时横向装下几成；pc：竖屏时改看哪里
  };
  W.shotC = function (s) { return (this.P.sw < this.P.sh && s.pc) ? s.pc : s.c; };
  W.shotPos = function (s) {
    var asp = this.P.sw / Math.max(1, this.P.sh), vf = s.fov * DEG, hf = 2 * Math.atan(Math.tan(vf / 2) * asp);
    var fw = asp < 1 ? s.fw * s.pk : s.fw;   // 竖屏：镜头靠近一些，两边裁掉一点，主体不至于太小（全图、对照不裁，标签才不出画）
    var c = this.shotC(s);
    var d = Math.max(s.fh / 2 / Math.tan(vf / 2), fw / 2 / Math.tan(hf / 2)) * s.pad;
    var cp = Math.cos(s.pitch);
    return V3(c.x + Math.sin(s.yaw) * cp * d, c.y + Math.sin(s.pitch) * d, c.z + Math.cos(s.yaw) * cp * d);
  };
  W.camKeys = function (keys) { // keys：[{t, s(镜), ease, arc}]，相邻两镜之间飞过去；到点后停住
    this.ck = keys.map(function (k) { return { t: k.t, s: k.s, ease: k.ease || 'io', arc: k.arc || 0, dur: k.dur || null }; });
    this.ck.sort(function (a, b) { return a.t - b.t; });
    this.layoutCams();
  };
  W.layoutCams = function () {
    var self = this;
    this.ck.forEach(function (k) { k.pos = self.shotPos(k.s); k.tgt = self.shotC(k.s).clone(); });
    this.refLabels();
  };
  // 第 t 秒的镜头：落在两镜之间就按缓动和弧线插值。每一镜的 dur 是“飞过去”用的时间，其余时间停在上一镜并缓缓推近
  W.camAt = function (t, pos, tgt) {
    var ck = this.ck, i = 0;
    for (var k = 0; k < ck.length; k++) if (ck[k].t <= t) i = k;
    var A = ck[i], B = ck[i + 1];
    if (!B || t < A.t) { pos.copy(A.pos); tgt.copy(A.tgt); return A.s.fov; }
    var span = B.t - A.t, dur = B.dur ? Math.min(B.dur, span) : span, t0 = B.t - dur;
    if (t < t0) { // 停留：慢慢推近一点（不让画面死掉）
      var hold = sat((t - A.t) / Math.max(0.01, t0 - A.t)), push = sine(hold) * 0.035;
      pos.copy(A.pos).lerp(A.tgt, push); tgt.copy(A.tgt);
      return A.s.fov;
    }
    var u = (EASE[B.ease] || inOut)((t - t0) / Math.max(0.01, dur));
    var a = this.tmp2.copy(A.pos).lerp(A.tgt, 0.035);
    var p0 = a, p3 = B.pos, lift = B.arc;
    var p1 = this._p1 || (this._p1 = new THREE.Vector3()), p2 = this._p2 || (this._p2 = new THREE.Vector3());
    p1.copy(p0).lerp(p3, 1 / 3); p1.y += lift; p2.copy(p0).lerp(p3, 2 / 3); p2.y += lift;
    var v = 1 - u;
    pos.set(0, 0, 0).addScaledVector(p0, v * v * v).addScaledVector(p1, 3 * v * v * u).addScaledVector(p2, 3 * v * u * u).addScaledVector(p3, u * u * u);
    var ut = (EASE[B.ease] || inOut)(sat((t - t0) / Math.max(0.01, dur) * 1.08));
    tgt.copy(A.tgt).lerp(B.tgt, ut);
    return lerp(A.s.fov, B.s.fov, u);
  };

  /* ---------- 后期：景深、泛光、暗角、方向模糊/中缝撕开（一个自定义效果） ---------- */
  W.post = function () {
    var r = this.renderer, cam = this.camera, pal = this.pal;
    var comp = this.comp = new PP.EffectComposer(r, { frameBufferType: THREE.HalfFloatType, multisampling: this.low ? 0 : Math.min(4, r.capabilities.maxSamples || 4) });
    comp.addPass(new PP.RenderPass(this.scene, cam));
    this.focus = new THREE.Vector3();
    if (!this.low) {
      this.dof = new PP.DepthOfFieldEffect(cam, { worldFocusDistance: 30, worldFocusRange: 22, bokehScale: 2.6, height: 540 });
      this.dof.target = this.focus;
      comp.addPass(new PP.EffectPass(cam, this.dof));
    }
    this.bloom = new PP.BloomEffect({ luminanceThreshold: pal.dark ? 0.62 : 0.96, luminanceSmoothing: 0.25, intensity: pal.dark ? 1.25 : 0.85, mipmapBlur: true, radius: 0.72 });
    this.vig = new PP.VignetteEffect({ offset: 0.32, darkness: pal.dark ? 0.55 : 0.24 });
    comp.addPass(new PP.EffectPass(cam, this.bloom, this.vig));
    var frag = [
      'uniform vec2 uBlur; uniform float uSeam; uniform float uTear; uniform float uFlash; uniform vec3 uFlashCol;',
      'void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor) {',
      '  vec2 st = uv; float side = st.x < uSeam ? 1.0 : -1.0; float dS = abs(st.x - uSeam);',
      '  st.x += side * uTear * 0.045 * exp(-dS * 7.0);',
      '  vec4 c = texture2D(inputBuffer, st);',
      '  if (length(uBlur) > 0.0006) { vec4 acc = vec4(0.0); float ws = 0.0;',
      '    for (int i = -6; i <= 6; i++) { float k = float(i) / 6.0; float w = 1.0 - abs(k) * 0.55; acc += texture2D(inputBuffer, st + uBlur * k) * w; ws += w; } c = acc / ws; }',
      '  if (uTear > 0.002) { float ca = uTear * 0.006 * exp(-dS * 4.0); c.r = texture2D(inputBuffer, st + vec2(ca, 0.0)).r; c.b = texture2D(inputBuffer, st - vec2(ca, 0.0)).b;',
      '    c.rgb += uFlashCol * uTear * 1.4 * exp(-dS * 140.0); }',
      '  c.rgb = mix(c.rgb, uFlashCol, uFlash); c = max(c, vec4(0.0));',
      '  outputColor = c; }'
    ].join('\n');
    if (!this.low) {
      this.fx = new PP.Effect('FDFX', frag, { attributes: PP.EffectAttribute.CONVOLUTION,
        uniforms: new Map([['uBlur', new THREE.Uniform(new THREE.Vector2())], ['uSeam', new THREE.Uniform(0.5)], ['uTear', new THREE.Uniform(0)],
          ['uFlash', new THREE.Uniform(0)], ['uFlashCol', new THREE.Uniform(pal.acc.clone())]]) });
      comp.addPass(new PP.EffectPass(cam, this.fx));
    }
  };

  /* =================================================================== 搭场景 */
  W.build = function () {
    var self = this, P = this.P, pal = this.pal, L = P.L, S = function (k) { return tx((P.v.S || {})[k], L); };
    this.S = S;
    var sc = this.scene;
    var left = this.left = new THREE.Group(), right = this.right = new THREE.Group();
    sc.add(left); sc.add(right);
    // ---- 地面（两半）
    var gU = { uBg: { value: new THREE.Color(pal.bg) }, uDot: { value: new THREE.Color(pal.dot) }, uDotA: { value: pal.dotA }, uGlow: { value: pal.glow.clone() }, uRing: { value: pal.acc.clone() },
      uPads: { value: [0, 0, 0, 0, 0, 0].map(function () { return new THREE.Vector4(0, 0, 4, 0); }) }, uFade: { value: 1 }, uCenter: { value: new THREE.Vector2(MAPC[0], MAPC[2]) },
      uSeamX: { value: SEAM }, uSeam: { value: 0 } };
    this.gU = gU;
    var gL = new THREE.ShaderMaterial({ uniforms: this.fogU(gU), vertexShader: GROUND_V, fragmentShader: GROUND_F, fog: true });
    var gR = gL.clone(); gR.uniforms = gL.uniforms; // 两半共用一套参数
    var planeL = new THREE.Mesh(new THREE.PlaneGeometry(90, 110, 1, 1), gL); planeL.rotation.x = -Math.PI / 2;
    var planeR = new THREE.Mesh(new THREE.PlaneGeometry(90, 110, 1, 1), gR); planeR.rotation.x = -Math.PI / 2;
    // 让两半的点阵对齐：把几何体平移，使局部坐标＝世界坐标
    planeL.geometry.translate(SEAM - 45, -MAPC[2], 0); planeL.position.set(0, 0, 0);
    planeR.geometry.translate(SEAM + 45, -MAPC[2], 0); planeR.position.set(0, 0, 0);
    left.add(planeL); right.add(planeR);
    this.gUL = gL.uniforms; this.gUR = gR.uniforms;
    // ---- 航线（分成两半，对折时跟着各自那一半走）
    var routeL = [V3(-40, 0.05, 16), V3(-26, 0.05, 6.5), V3(-15, 0.05, -5), V3(-6, 0.05, -12.5), V3(SEAM, 0.05, -6)];
    var routeR = [V3(SEAM, 0.05, -6), V3(14, 0.05, 3.5), V3(23, 0.05, -2), V3(32, 0.05, -10.5), V3(44, 0.05, -18)];
    this.routeL = this.tube(routeL, 0.06, this.flowMat(pal.acc, { dash: 60, glow: 1.25 }), 300);
    this.routeR = this.tube(routeR, 0.06, this.flowMat(pal.acc, { dash: 60, glow: 1.25 }), 300);
    left.add(this.routeL); right.add(this.routeR);
    this.flowMeshes = [this.routeL, this.routeR]; this.glass = []; this.photos = []; this.blocks = []; this.cubes = []; this.charts = []; this.exploreShots = {};
    // ---- 各章在地图上的一片：故事线按顺序占 SLOTS，对照在中间
    var chs = P.v.chapters || [], stories = chs.filter(function (c) { return c.kind === 'story'; }), sl = slotsFor(stories.length);
    var A = this.areas = {};
    stories.forEach(function (c, i) {
      var k = sl[i], p = SLOTS[k], g = new THREE.Group(); g.position.set(p[0], p[1], p[2]);
      (k < 2 ? left : right).add(g); A[c.id] = { pos: p, side: k < 2 ? -1 : 1, g: g, ch: c, half: k < 2 ? left : right };
    });
    chs.forEach(function (c) {
      if (c.kind !== 'contrast') return;
      var g = new THREE.Group(); g.position.set(CPOS[0], CPOS[1], CPOS[2]); sc.add(g); A[c.id] = { pos: CPOS, side: 0, g: g, ch: c, half: sc };
    });
    // ---- 空气里的尘（带运动拖影）
    this.dust();
    chs.forEach(function (c) { if (A[c.id]) self.buildChapter(c); });
    this.buildHandoffs();
    this.buildChips();
    // 动效尝试（11-06 晚）：开场"今日速览"（open 章写了 headline_open 才有）
    this.heads = [];
    chs.forEach(function (c) {
      if (c.kind !== 'open') return;
      (c.blocks || []).forEach(function (b) { if (b.type === 'headline_open') { b._ = { c: c, o: {} }; TPL.headline_open.build.call(self, b); self.heads.push(b); } });
    });
  };

  // 一章里的几个模板：按顺序排成一行（行居中在这一片上）；有的模板贴在前一个上面（手机贴时间轴尽头、点阵贴传播链、卡片站在分岔路尽头）；配图做背景
  W.buildChapter = function (c) {
    var self = this, Ar = this.areas[c.id], list = (c.blocks || []).filter(function (b) { return TPL[b.type]; });
    var row = [], prev = null, fork = null, branch = 0, cursor = 0, images = [], real = [];
    list.forEach(function (b) {
      var tp = TPL[b.type], o = b._ = { c: c, A: Ar, prev: null, next: null, o: {} };
      if (b.type === 'image_card') { images.push(b); return; }
      if (fork && branch < 2 && tp.panel) { o.branch = branch++; o.fork = fork; o.rel = [fork._.x + 10.5, 0, o.branch ? 7.2 : -7.2]; o.rot = -Math.PI / 2; }
      else if (prev && prev.type === 'timeline' && b.type === 'phone_list') { o.attach = prev; o.dx = 12.2; }
      else if (prev && prev.type === 'chain' && b.type === 'particle_counter') { o.attach = prev; o.dx = 0; }
      else { var e = (b.photo_img && tp.extPhoto) || tp.ext || [4, 4]; o.x = cursor + e[0]; cursor = o.x + e[1] + 3.3; row.push(b); if (b.type === 'fork') { fork = b; branch = 0; } }   // extPhoto：压在配图上（11-07）时占得宽
      o.prev = prev; if (prev) prev._.next = b; prev = b; real.push(b);
    });
    var shift = row.length ? -(row[0]._.x + row[row.length - 1]._.x) / 2 : 0;
    row.forEach(function (b) { b._.x += shift; b._.rel = [b._.x, 0, 0]; });
    real.forEach(function (b) {
      var o = b._;
      if (o.attach) { o.x = o.attach._.x + o.dx; o.rel = [o.x, 0, 0]; }
      if (o.fork) o.x = o.rel[0];
    });
    // 配图：有分岔路就立在两条路之间的尽头，否则挂在这一章右后方
    var maxR = 0; real.forEach(function (b) { maxR = Math.max(maxR, (b._.rel ? b._.rel[0] : 0) + ((TPL[b.type].ext || [4, 4])[1])); });
    images.forEach(function (b, i) {
      var o = b._;
      if (fork && i === 0) { o.mode = 'fork'; o.rel = [fork._.x + 7, 0, 0]; o.rot = -Math.PI / 2; }
      else {
        // 挂在它出现时画面上那一段的右后方；那一段之后另起一段（不是贴在它上面的），配图就收起
        var tin = bt(b, 'in', null), host = null;
        real.forEach(function (rb) { var st0 = startT(rb); if (!host || (tin != null && st0 != null && st0 <= tin + 0.01)) host = rb; });
        var root = host && host._.attach ? host._.attach : host;
        o.mode = 'backdrop'; o.host = host;
        // bdx：模板右边还挂着一列字（刻度尺的档名）时，配图再往右让开，不压字
        o.rel = root ? [root._.x + (TPL[root.type].ext || [4, 4])[1] + (TPL[root.type].bdx != null ? TPL[root.type].bdx : 2.5), 0, -15] : [Math.max(6, maxR - 0.45) + i * 24, 0, -15];
        var nx = host ? host._.next : null; while (nx && nx._.attach) nx = nx._.next;
        o.hideAt = nx ? startT(nx) - 0.3 : null;
      }
      o.prev = real.length ? real[real.length - 1] : null;
    });
    // 11-06 晚补：分岔路尽头的要点卡写了 over_photo，就不站在路的一头，而是立在路尽头那张配图的正前方（卡片压在配图上，配图当背景）；
    //   没有立在路尽头的配图时照旧
    var fph = images.filter(function (b) { return b._.mode === 'fork'; })[0];
    real.forEach(function (b) {
      if (b.over_photo && b.type === 'quote_card' && b._.fork && fph) { b._.over = fph; b._.rel = [fph._.rel[0] - 0.9, 0, 0]; b._.x = b._.rel[0]; }
    });
    // 每个模板一个组（局部坐标里搭）
    list.forEach(function (b) {
      var o = b._, g = o.g = new THREE.Group();
      g.position.set(o.rel ? o.rel[0] : 0, 0, o.rel ? o.rel[2] : 0); if (o.rot) g.rotation.y = o.rot;
      Ar.g.add(g);
    });
    this.scene.updateMatrixWorld(true);
    real.forEach(function (b, i) { b._.first = i === 0; });
    // 下一个模板的开头（前一个模板据此收场）
    real.forEach(function (b) { var nx = b._.next; b._.nextT = nx ? startT(nx) : null; });
    real.concat(images).forEach(function (b) { TPL[b.type].build.call(self, b); self.blocks.push(b); });
    c._real = real; c._images = images;
  };
  // 模板局部坐标 → 世界坐标；镜头（看哪里在模板局部坐标里给，偏航角跟着模板的朝向转）
  W.wp = function (b, x, y, z) { return b._.g.localToWorld(V3(x, y, z)); };
  W.bshot = function (b, c, yaw, pitch, fw, fh, o) {
    o = o || {};
    var rot = (b._.g.rotation.y || 0) / DEG, w = this.wp(b, c[0], c[1], c[2]), pc = o.pc ? this.wp(b, o.pc[0], o.pc[1], o.pc[2]) : null;
    return this.shot([w.x, w.y, w.z], yaw + rot, pitch, fw, fh, { pk: o.pk, pc: pc ? [pc.x, pc.y, pc.z] : null, fov: o.fov });
  };
  function bt(b, k, d) { var v = b.t && b.t[k]; return typeof v === 'number' ? v : d; }
  function firstT(b) { var m = Infinity, t = b.t || {}; for (var k in t) if (typeof t[k] === 'number') m = Math.min(m, t[k]); return m === Infinity ? null : m; }
  function startT(b) { var tp = TPL[b.type]; return tp.startT ? tp.startT(b) : firstT(b); }
  // 列表里的时刻：有触发词的用触发词，没有的在前后已知时刻之间均分（再没有就从 t0 起每 gap 秒一个）
  function fillTimes(ts, t0, gap) {
    var out = ts.slice(), n = out.length, i, j;
    for (i = 0; i < n; i++) {
      if (typeof out[i] === 'number') continue;
      j = i; while (j < n && typeof out[j] !== 'number') j++;
      var a = i > 0 ? out[i - 1] : t0 - gap, b = j < n ? out[j] : a + (j - i + 1) * gap;
      for (var k = i; k < j; k++) out[k] = a + (b - a) * (k - i + 1) / (j - i + 1);
      i = j - 1;
    }
    return out;
  }
  function listT(b, field, n, t0, gap) { var a = []; for (var i = 0; i < n; i++) a.push(bt(b, field + i, null)); return fillTimes(a, t0, gap); }
  function S2(o, L) { return tx(o, L); }
  // 字里的数字＋单位：48% → 48<span class="v3u">%</span>
  // 11-08（K44）：区间（1–1.25、1 至 2）整段算数字放大，不再只放大前一半
  function numUnit(s) { var m = String(s || '').match(FX ? /^([−\-]?[\d.,]+(?:\s*[–—~～\-至到]\s*[\d.,]+)?)(.*)$/ : /^([−\-]?[\d.,]+)(.*)$/); return m ? esc(m[1]) + (m[2] ? '<span class="v3u">' + esc(m[2]) + '</span>' : '') : esc(s); }
  // 11-08（K44、K46）：括号整段、末两个字不单独掉行（开关关着时就是 esc）
  function noOrphan(s) {
    if (!FX) return esc(s);
    var parts = String(s == null ? '' : s).split(/(（[^（）]{1,10}）|\([^()]{1,12}\))/), out = parts.map(function (x, i) { return i % 2 ? '<span class="v3nw">' + esc(x) + '</span>' : esc(x); });
    var last = parts[parts.length - 1];
    if (last.length >= 3 && /[\u3400-\u9fff。，；！？]$/.test(last)) out[out.length - 1] = esc(last.slice(0, -2)) + '<span class="v3nw">' + esc(last.slice(-2)) + '</span>';
    return out.join('');
  }
  // 标志小签：data.logos 里是构建时嵌进来的标志（data: 地址，CSS 遮罩单色上色，形状不动）；没有标志的是文字小签
  function logoChip(P, key, o) {
    o = o || {};
    var lg = (P.v.logos || {})[key]; if (!lg) return '';
    var nm = tx(lg.n, P.L), named = !lg.m || lg.f === 'symbol';
    return '<span class="v3logo' + (lg.m ? '' : ' txt') + (o.hi ? ' hi' : '') + (o.sm ? ' sm' : '') + (lg.m && lg.f !== 'symbol' && lg.ar < 2.2 ? ' tall' : '') + '" data-logo="' + esc(key) + '"' +
      (o.i != null ? ' data-li="' + o.i + '"' : '') + ' role="img" aria-label="' + esc(nm) + '">' +
      (lg.m ? '<i class="mk" style="aspect-ratio:' + (+lg.ar || 1) + '"></i>' : '') + (named ? '<b>' + esc(nm) + '</b>' : '') + '</span>';
  }
  function logoList(P, list, o) { return (list || []).map(function (r, i) { return logoChip(P, r && r.k ? r.k : r, Object.assign({ i: i }, o || {})); }).join(''); }
  // 卡片里的标志：各按自己的触发词弹出（说到这家公司时）；没有触发词的跟在 t0 后面依次出来；不早于 t0
  function popLogos(a, root, list, t0, gap) {
    var els = root ? root.querySelectorAll('.v3logo[data-li]') : [], n = els.length;
    var ts = fillTimes((list || []).slice(0, n).map(function (r) { return r && typeof r.t === 'number' ? r.t : null; }), t0 + (gap || 0.18), gap || 0.18);
    for (var i = 0; i < n; i++) {
      var at = Math.max(ts[i] != null ? ts[i] : t0, t0 + 0.15 + i * 0.12);
      a.ST(els[i], { autoAlpha: 0, scale: 0.6 });
      a.tl.fromTo(els[i], { autoAlpha: 0, scale: 0.6 }, { autoAlpha: 1, scale: 1, duration: 0.45, ease: 'back.out(2.4)' }, at);
    }
  }
  // 卡片里题图的慢推（11-06 晚补，给国内外小卡用）：说到时从 1.1 倍慢慢缩回原大，收场前一直在动
  function kenBurns(a, root, t0, t1) {
    var ph = root ? root.querySelector('.ph i') : null; if (!ph) return;
    a.ST(ph, { scale: 1.1 }); a.tl.fromTo(ph, { scale: 1.1 }, { scale: 1, duration: Math.max(2, t1 - t0 + 0.5), ease: 'none' }, t0 - 0.3);
  }
  function mono(name) {
    var s = String(name || '').trim(); if (!s) return '·';
    if (/^[A-Za-z]/.test(s)) { var w = s.split(/\s+/).filter(function (x) { return /^[A-Za-z]/.test(x); }); return (w[0][0] + (w.length > 1 ? w[w.length - 1][0] : '')).toUpperCase(); }
    return s[0];
  }
  function imgUrl(P, key) { var info = (P.v.images || {})[key]; return info ? P.asset(info.src) : null; }
  // 帖子卡头像里的标志怎么放（11-06）：单位是 cqw 里的 --u。圆的直径 D；圆里能放的标志最宽 IN（再宽四角就出圆）；
  // 放不进圆的（横长字标）用胶囊：标志高 PH，最宽 PW。site/tools/video3_logos.py 的 AVATAR 用同一组数，测试逐个标志核不溢出。
  var AV = { D: 3.2, MH: 1.7, IN: 2.5, PH: 1.2, PW: 7.0 };
  function avatarFit(lg) {
    var ar = +lg.ar || 1;
    if (lg.f === 'symbol' || ar <= AV.IN / AV.MH * 1.2) {
      var h = Math.min(AV.MH, AV.IN / ar);
      if (h >= AV.MH * 0.7) return { pill: false, h: h };          // 圆里放得下（最多缩到七成）
    }
    return { pill: true, h: Math.min(AV.PH, AV.PW / ar) };
  }

  /* =================================================================== 模板库
   * 每种模板：ext（在一行里占多宽：[左, 右]）、build（搭场景、建镜头和字）、tl（按触发词排动画）、cams（这一段的镜头）、
   * settle（这一段"看完"的时刻）、frame（每一帧要算的东西，可选）、startT（这一段从哪个时刻算开始，可选）。
   * 数据字段见 site/tools/video3_storyboard.py 的 TEMPLATES，写稿说明见 pipeline/prompts/写稿_视频v3.md。 */
  var TPL = {};

  /* ---- 一根柱子从原值缩到新值（断开、碎掉）；可选：已完成量的芯、原值一半的虚线 ---- */
  TPL.bar_shrink = {
    ext: [3, 6.5],
    build: function (b) {
      var g = b._.g, pal = this.pal, L = this.P.L, M = b._.o;
      var vF = Math.abs(+((b.from || {}).value)) || 1, vT = Math.abs(+((b.to || {}).value)) || 0, vD = b.done ? Math.abs(+b.done.value) || 0 : 0;
      var U = 9 / vF, BW = 2.4, hF = 9, hT = Math.max(0.2, Math.min(hF - 0.3, vT * U)), hD = Math.min(hF, vD * U), hH = hF / 2;
      M.hT = hT; M.vD = vD; M.dec = String(b.done && b.done.value || '').split('.')[1] ? String(b.done.value).split('.')[1].length : 0;
      var lowG = new THREE.RoundedBoxGeometry(BW, hT, BW, 4, 0.14); lowG.translate(0, hT / 2, 0);
      var upG = new THREE.RoundedBoxGeometry(BW, hF - hT - 0.06, BW, 4, 0.14); upG.translate(0, (hF - hT - 0.06) / 2, 0);
      M.low = new THREE.Mesh(lowG, this.boxMat({ alpha: 0.22 })); g.add(M.low);
      M.up = new THREE.Mesh(upG, this.boxMat({ alpha: 0.22 })); M.up.position.y = hT + 0.06; g.add(M.up);
      this.outline(BW, hT, BW, M.low, hT / 2);
      this.outline(BW, hF - hT - 0.06, BW, M.up, (hF - hT - 0.06) / 2);
      this.shadow(BW * 2.6, BW * 2.6, g, 0, 0, 1.1);
      if (vD) {
        var coreG = new THREE.RoundedBoxGeometry(BW * 0.58, Math.max(0.05, hD), BW * 0.58, 3, 0.1); coreG.translate(0, Math.max(0.05, hD) / 2, 0);
        M.core = new THREE.Mesh(coreG, this.coreMat(pal.acc)); M.core.scale.y = 0.001; g.add(M.core);
        M.coreGlow = this.glow(5.5, pal.acc, 0); M.coreGlow.position.set(0, hD, 0); g.add(M.coreGlow);
      }
      var hw = BW / 2 + 0.32;
      if (b.half) {
        var sq = [V3(-hw, 0, -hw), V3(hw, 0, -hw), V3(hw, 0, hw), V3(-hw, 0, hw), V3(-hw, 0, -hw)];
        M.half = new THREE.Line(new THREE.BufferGeometry().setFromPoints(sq), new THREE.LineDashedMaterial({ color: pal.dark ? 0xf5efe6 : 0x3a2f22, dashSize: 0.22, gapSize: 0.16, transparent: true, opacity: 0 }));
        M.half.computeLineDistances(); M.half.position.y = hH; g.add(M.half);
      }
      M.shards = this.burst(140, V3(0, hT + 1.5, 0), V3(BW, 3, BW), { out: 1.4, up: 1.6, grav: 3, size: 3 }); g.add(M.shards);
      var sh = b._.shA = this.bshot(b, [-1.0, 5.2, 0], -10, 9, 13.5, 12.6, { pk: 0.95 });
      b._.shA2 = this.bshot(b, [-0.6, 5.1, 0], -4, 8, 12.6, 11.8, { pk: 0.95 });
      M.lHead = this.label('<div class="v3head v3glass"><div class="h">' + esc(S2(b.head, L)) + '</div>' + (b.status ? '<div class="s">' + esc(S2(b.status, L)) + '</div>' : '') + '</div>', { obj: g, at: V3(-BW / 2 - 0.5, hF - 0.2, 0), shot: sh, align: 'r', keep: true });
      M.l300 = this.label('<div class="v3line">' + emph(S2(b.from.label, L)) + '</div>', { obj: g, at: V3(BW / 2 + 0.55, hF - 0.35, 0), shot: sh, align: 'l' });
      M.l200 = this.label('<div class="v3line">' + emph(S2(b.to.label, L), false, 'v3acc') + '</div>', { obj: g, at: V3(BW / 2 + 0.55, hT - 0.35, 0), shot: sh, align: 'l' });
      if (b.cut) M.lCut = this.label('<span class="v3tag warn v3n">' + esc(S2(b.cut, L)) + '</span>', { obj: g, at: V3(-BW / 2 - 0.35, hT + 0.75, 0), shot: sh, align: 'r' });
      if (vD) M.l110 = this.label('<div class="v3line">' + emph(S2(b.done.label, L), true, 'v3acc') + '</div>', { obj: g, at: V3(BW / 2 + 0.55, Math.max(0.6, hD * 0.6), 0), shot: sh, align: 'l' });
      if (b.half) M.lHalf = this.label('<span class="v3plain">' + esc(S2(b.half, L)) + '</span>', { obj: g, at: V3(-hw - 0.25, hH, 0), shot: sh, align: 'r' });
      if (b.note) M.lVal = this.label('<span class="v3tag v3glass">' + esc(S2(b.note, L)) + '</span>', { obj: g, at: V3(0, -0.55, 1.9), shot: sh, align: 't' });
      b._.headAt = V3(0, 10.6, 0); b._.enterAt = V3(-1.5, 1, 0); b._.exitAt = V3(BW / 2 + 0.5, 1, 0);
    },
    tl: function (b, a) {
      var M = b._.o, c = b._.c, self = this, b0 = bt(b, 'head', c.vs + 0.3), cs = b._.first ? c.start : b0 - 1.5;
      [M.low, M.up].forEach(function (m) { a.ST(m.scale, { y: 0.001 }); });
      a.tl.fromTo(M.low.scale, { y: 0.001 }, { y: 1, duration: 1.1, ease: 'power3.out' }, cs + 0.7);
      a.tl.fromTo(M.up.scale, { y: 0.001 }, { y: 1, duration: 0.9, ease: 'power3.out' }, cs + 1.25);
      a.show(M.lHead, b0 - 0.1); a.show(M.l300, bt(b, 'from', b0 + 1.2) - 0.15);
      a.ST(M.up.position, { x: 0, y: M.hT + 0.06, z: 0 }); a.ST(M.up.rotation, { x: 0, z: 0 }); a.ST(M.up.material.uniforms.uFade, { value: 1 });
      var c200 = bt(b, 'to', bt(b, 'from', b0 + 1.2) + 1.4);
      a.tl.fromTo(M.up.position, { x: 0, y: M.hT + 0.06, z: 0 }, { x: -1.4, y: M.hT + 2.4, z: -0.6, duration: 1.4, ease: 'power2.out' }, c200);
      a.tl.fromTo(M.up.rotation, { x: 0, z: 0 }, { x: -0.22, z: 0.32, duration: 1.4, ease: 'power2.out' }, c200);
      a.U(M.up.material.uniforms.uFade, 1, 0, c200 + 0.55, 1.1, 'power1.in');
      a.U(M.shards.material.uniforms.uT, 0, 1, c200 + 0.5, 1.8, 'none');
      if (M.lCut) { a.show(M.lCut, c200 + 0.1); a.hide(M.lCut, c200 + 1.6, 0.4); }
      a.show(M.l200, c200 + 0.3); a.hide(M.l300, c200 + 0.25, 0.4);
      if (M.lVal) a.show(M.lVal, c200 + 1.0);
      var c110 = bt(b, 'done', c200 + 1.4);
      if (M.core) {
        a.ST(M.core.scale, { y: 0.001 }); a.tl.fromTo(M.core.scale, { y: 0.001 }, { y: 1, duration: 1.3, ease: 'power3.out' }, c110 - 0.05);
        a.ST(M.coreGlow.material, { opacity: 0 }); a.tl.fromTo(M.coreGlow.material, { opacity: 0 }, { opacity: self.gk(0.85), duration: 0.8 }, c110 + 0.3);
        a.show(M.l110, c110); this.counter(M.l110, 'span[data-c]', 0, M.vD, c110, 1.3, M.dec);
      }
      if (M.half) {
        var ch = bt(b, 'half', c110 + 1.5);
        a.ST(M.half.material, { opacity: 0 }); a.tl.fromTo(M.half.material, { opacity: 0 }, { opacity: 0.85, duration: 0.5 }, ch - 0.2);
        a.show(M.lHalf, ch - 0.1);
      }
      var endT = b._.nextT != null ? b._.nextT - 0.2 : c.end + 0.3;
      [M.lHead, M.l200, M.l110, M.lHalf, M.lVal].forEach(function (lb) { if (lb) a.hide(lb, endT, 0.4); });
      M.settle = Math.max(c200, M.core ? c110 : 0, M.half ? bt(b, 'half', 0) : 0) + 1.4;
    },
    cams: function (b) {
      var c = b._.c, b0 = bt(b, 'head', c.vs + 0.3), end = b._.nextT != null ? b._.nextT : c.end;
      return [{ t: b0 - 0.15, s: b._.shA, dur: 1.3, ease: 'io', arc: 10 }, { t: end - 0.4, s: b._.shA2, dur: 3.0, ease: 'sine' }];
    },
    settle: function (b) { return b._.o.settle; },
    explore: function (b) { return [1, b._.shA2]; }
  };

  /* ---- 1–3 个价位块从同一高度按跌幅掉下来 ---- */
  TPL.twin_drop = {
    ext: [1.6, 6.8],
    build: function (b) {
      var g = b._.g, pal = this.pal, L = this.P.L, M = b._.o, self = this;
      var items = (b.items || []).slice(0, 3), N = items.length, TOP = 10;
      var drops = items.map(function (it) { return clamp(Math.abs(+it.value || 0) / 100, 0.02, 0.9); });
      M.rails = []; M.slabs = []; M.ghosts = []; M.lines = []; M.dust2 = []; M.items = items; M.drops = drops; M.TOP = TOP;
      for (var i = 0; i < N; i++) {
        var x = i * 3.5, alt = i % 2 ? pal.alt : pal.acc;
        var rail = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, TOP + 1.2, 10), this.boxMat({ alpha: 0.25, rimK: 0.6 })); rail.position.set(x, (TOP + 1.2) / 2, 0); g.add(rail); M.rails.push(rail);
        var sg = new THREE.RoundedBoxGeometry(2.3, 0.46, 2.3, 3, 0.1);
        var ghost = new THREE.Mesh(sg, this.boxMat({ alpha: 0.05, rimK: 0.6 })); ghost.position.set(x, TOP, 0); g.add(ghost); M.ghosts.push(ghost);
        this.outline(2.34, 0.5, 2.34, ghost, 0, this.pal.dark ? 0.25 : 0.3);
        this.shadow(3.4, 3.4, g, x, 0, 0.8);
        var slab = new THREE.Mesh(sg, this.coreMat(alt, pal.dark ? 1.1 : 0.8)); slab.position.set(x, TOP, 0); g.add(slab); M.slabs.push(slab);
        var ln = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.022, 1, 6), this.flowMat(alt, { reveal: 1, glow: 0.95, head: 0 }));
        ln.material.uniforms.uDash.value = 18; ln.position.set(x + 1.35, TOP, 0); g.add(ln); M.lines.push(ln);
        var bu = this.burst(90, V3(x, TOP * (1 - drops[i]) - 0.2, 0), V3(2.2, 0.2, 2.2), { out: 2.2, up: 1.1, grav: 2.6, size: 2.6, col: alt }); g.add(bu); M.dust2.push(bu);
      }
      var lastX = (N - 1) * 3.5, cx = lastX / 2, avg = drops.reduce(function (s, v) { return s + v; }, 0) / Math.max(1, N);
      var yb = TOP * (1 - avg) - 0.23;
      if (N > 1) { M.floor = this.tube([V3(-1.6, yb, 0), V3(lastX + 1.6, yb, 0)], 0.055, this.flowMat(pal.acc, { glow: 1.9 }), 40); g.add(M.floor); }
      var shF = b._.shB = this.bshot(b, [cx, 7.3, 0], 12, 8, 11 + Math.max(0, N - 2) * 3.5, 9.8, { pk: 0.95, pc: [cx, 7.9, 0] });
      b._.shC = this.bshot(b, [cx + 0.85, 6.5, 0], 8, 12, 15 + Math.max(0, N - 2) * 3.5, 10.5);
      if (b.head) M.lFalls = this.label('<div class="v3head v3glass"><div class="h">' + esc(S2(b.head, L)) + '</div></div>', { obj: g, at: V3(cx, TOP + 1.9, 0), shot: shF, align: 'b' });
      if (b.before) M.lBefore = this.label('<span class="v3plain">' + esc(S2(b.before, L)) + '</span>', { obj: g, at: V3(-1.5, TOP, 0), shot: shF, align: 'r' });
      M.lItems = items.map(function (it, i) {
        var v = +it.value || 0, dec = (String(it.value).split('.')[1] || '').length, unit = it.unit != null ? it.unit : '%';
        return self.label('<div class="v3val"><div class="c v3t">' + esc(S2(it.name, L)) + '</div><div class="n v3n v3acc"><span data-c="' + v + '">0</span><span class="v3u">' + esc(unit) + '</span></div>' +
          (it.sub ? '<div class="c">' + esc(S2(it.sub, L)) + '</div>' : '') + '</div>', { obj: g, at: V3(i * 3.5, TOP * (1 - drops[i]) - 1.6, 1.2), shot: shF, align: 't' });
      });
      M.decs = items.map(function (it) { return (String(it.value).split('.')[1] || '').length; });
      if (b.same && N > 1) M.lSame = this.label('<span class="v3plain strong">' + esc(S2(b.same, L)) + '</span>', { obj: g, at: V3(lastX + 2.1, yb + 0.1, 0), shot: shF, align: 'l' });
      if (b.note) M.lNote = this.label('<span class="v3tag v3glass">' + esc(S2(b.note, L)) + '</span>', { obj: g, at: V3(lastX + 2.1, yb - 1.25, 0), shot: shF, align: 'l' });
      b._.enterAt = V3(-1.6, TOP, 0); b._.exitAt = V3(lastX + 1.6, yb, 0); b._.headAt = V3(cx, TOP + 2.4, 0);
    },
    tl: function (b, a) {
      var M = b._.o, c = b._.c, self = this, N = M.items.length;
      var it0 = bt(b, 'items0', null), cf = bt(b, 'head', it0 != null ? it0 - 1.6 : c.vs + 0.4);
      var its = listT(b, 'items', N, cf + 1.7, 2.4);
      M.slabs.forEach(function (s) { a.ST(s.position, { y: M.TOP }); a.ST(s.scale, { x: 0.001, y: 0.001, z: 0.001 }); });
      M.ghosts.forEach(function (s) { a.ST(s.material.uniforms.uFade, { value: 0 }); a.U(s.material.uniforms.uFade, 0, 1, cf - 0.6, 0.6); });
      M.rails.forEach(function (s) { a.ST(s.scale, { y: 0.001 }); a.tl.fromTo(s.scale, { y: 0.001 }, { y: 1, duration: 0.9, ease: 'power3.out' }, cf - 0.9); });
      M.slabs.forEach(function (s, i) { a.tl.fromTo(s.scale, { x: 0.001, y: 0.001, z: 0.001 }, { x: 1, y: 1, z: 1, duration: 0.6, ease: 'back.out(1.6)' }, cf - 0.3 + i * 0.15); });
      if (M.lFalls) a.show(M.lFalls, cf - 0.3); if (M.lBefore) a.show(M.lBefore, cf + 0.2);
      its.forEach(function (at, i) {
        var s = M.slabs[i], to = M.TOP * (1 - M.drops[i]);
        a.tl.fromTo(s.position, { y: M.TOP }, { y: to - 0.12, duration: 0.42, ease: 'power3.in' }, at - 0.25);
        a.tl.fromTo(s.position, { y: to - 0.12 }, { y: to, duration: 0.5, ease: 'back.out(3)' }, at + 0.17);
        a.U(M.dust2[i].material.uniforms.uT, 0, 1, at + 0.15, 1.4, 'none');
        a.show(M.lItems[i], at - 0.2); self.counter(M.lItems[i], 'span[data-c]', 0, +M.items[i].value || 0, at - 0.2, 0.7, M.decs[i]);
      });
      var same = bt(b, 'same', its[N - 1] + 1.5);
      if (M.floor) { a.ST(M.floor.material.uniforms.uReveal, { value: 0 }); a.U(M.floor.material.uniforms.uReveal, 0, 1, same - 0.3, 0.8, 'power2.inOut'); }
      if (M.lSame) a.show(M.lSame, same + 0.1);
      if (M.lNote) a.show(M.lNote, bt(b, 'note', same + 1.5) - 0.2);
      if (M.lFalls) a.hide(M.lFalls, same - 0.3, 0.4);
      var endT = b._.nextT != null ? b._.nextT - 0.2 : c.end + 0.3;
      [M.lBefore, M.lSame, M.lNote].concat(M.lItems).forEach(function (lb) { if (lb) a.hide(lb, endT, 0.4); });
      M.cf = cf; M.same = same; M.hasSame = !!M.lSame;
    },
    cams: function (b) {
      var M = b._.o, k = [{ t: M.cf + 0.9, s: b._.shB, dur: 1.3, ease: 'io', arc: 6 }];
      if (M.hasSame) k.push({ t: M.same + 0.4, s: b._.shC, dur: 1.0, ease: 'io' });
      return k;
    },
    settle: function (b) { return b._.o.same + 1.4; },
    explore: function (b) { return [2, b._.o.hasSame ? b._.shC : b._.shB]; },
    frame: function (b) {
      var M = b._.o;
      for (var i = 0; i < M.slabs.length; i++) {
        var s = M.slabs[i], ln = M.lines[i], h = Math.max(0.001, M.TOP - s.position.y);
        ln.scale.y = h; ln.position.y = s.position.y + h / 2; ln.material.uniforms.uFade.value = h > 0.05 ? 0.9 : 0;
      }
    }
  };

  // 时间轨上相邻两个日子最少隔开整条轨的几分之几（11-05 按渲染实测定：标签宽约画面的 13%，整条轨约占画面的 75%，
  // 0.2 时两张同侧标签之间还空约 2% 画面宽；7 个日子装不下 0.2 时就等分）。分镜检查 video3_storyboard.TIMELINE_GAP 用同一个数提醒。
  var TL_GAP = 0.2;
  // pos（0–1，只表示先后）→ 0–1 上的位置：先按原顺序排成不倒退，再把整段拉满 0–1；太近的间隔补到 gap，补出来的从宽的间隔里按比例匀出来
  function tlSpread(p, gap) {
    var n = p.length, i, it;
    if (n < 2) return n ? [0] : [];
    var q = p.slice(); for (i = 1; i < n; i++) q[i] = Math.max(q[i], q[i - 1]);
    var tot = q[n - 1] - q[0], g = [], fix = [];
    for (i = 0; i < n - 1; i++) { g.push(tot > 1e-6 ? (q[i + 1] - q[i]) / tot : 1 / (n - 1)); fix.push(false); }
    var m = Math.min(gap, 1 / (n - 1));
    for (it = 0; it < n; it++) {
      var nf = 0, free = 0, again = false;
      for (i = 0; i < n - 1; i++) { if (fix[i]) nf++; else free += g[i]; }
      var room = 1 - nf * m;
      for (i = 0; i < n - 1; i++) {
        if (fix[i]) { g[i] = m; continue; }
        g[i] = free > 1e-9 ? g[i] * room / free : room / (n - 1 - nf);
        if (g[i] < m - 1e-9) { fix[i] = true; again = true; }
      }
      if (!again) break;
    }
    var out = [0]; for (i = 0; i < n - 1; i++) out.push(out[i] + (fix[i] ? m : g[i]));
    return out;
  }
  // 时间轨的日子分段（11-06）：tt 是每个日子说到的秒数；同一章别的模板开始的时刻把日子切开（贴在时间轨尽头的手机也算：
  // 镜头推到手机时，标签照旧在手机出现前收起——10-31 入口那一章）。
  // 返回 [{i0, i1, t0, end}]：第 i0–i1 个日子一段，t0 是这一段第一个日子的时刻，end 是这一段之后第一个别的模板开始的时刻（没有就是章末）
  function tlSegments(b, tt) {
    var c = b._.c, others = (c._real || []).filter(function (x) { return x !== b; })
      .map(startT).filter(function (v) { return typeof v === 'number'; }).sort(function (x, y) { return x - y; });
    var after = function (t) { for (var i = 0; i < others.length; i++) if (others[i] > t + 0.05) return others[i]; return null; };
    var segs = [], cur = null;
    tt.forEach(function (t, i) {
      var nx = after(t);
      if (!cur || cur.nx !== nx) { cur = { i0: i, i1: i, t0: t, nx: nx }; segs.push(cur); } else cur.i1 = i;
    });
    segs.forEach(function (sg) { sg.end = sg.nx != null ? sg.nx : c.end - 0.1; });
    return segs;
  }
  // 时间轨日子上的小图要真的露脸（11-06 白天补）：小图在说到那个日子时才弹出，可下一个模板那一镜的"起飞"在它触发词前 1 秒多
  // （落点在触发词后，飞 1.3–1.5 秒）——11-06 选票那一章"本周中期选举"后 0.7 秒就说"10 个州"，镜头在投票会堂那张小图弹出前
  // 就飞去计数卡了，21 秒那一刻画面几乎是空的。规矩：带小图的日子弹出后，镜头至少在时间轨上停 TL_IMG_HOLD 秒；别的模板飞过来的
  // 那一镜往后顺延（不越过再后面的一镜）。这几个日子的标签也至少留到镜头起飞后 0.5 秒（时间轨的 tl 里按同一个数算）。
  // 日子没挂小图时什么都不变（11-06 以前的各期都没有小图）。
  var TL_IMG_HOLD = 1.8, TL_IMG_ZOOM = 1.7;
  function tlImagePops(b) {
    var E = b._ && b._.o;
    if (b.type !== 'timeline' || !E || !E.ticks || !E.tt) return [];
    var out = []; E.ticks.forEach(function (k, i) {
      if (k.img) out.push({ t: E.tt[i] + 0.15, hold: TL_IMG_HOLD });
      else if (k.shot) out.push({ t: E.tt[i] + 0.15, hold: k.shot.t1 + 0.2 - (E.tt[i] + 0.15) });   // 结合式：截图弹出、扫完、缩回小图以后才起飞
    });
    return out;
  }
  function tlImageHold(real, ks) {
    real.forEach(function (b) {
      tlImagePops(b).forEach(function (pp) {
        var pop = pp.t, hold = pop + pp.hold;
        ks.forEach(function (k, j) {
          if (k.b === b || !k.dur || k.t <= pop || k.t - k.dur >= hold) return;
          var nt = hold + k.dur, nx = ks[j + 1];
          if (nx && nx.dur && nx.t - nx.dur < nt + 0.3) nt = Math.max(k.t, nx.t - nx.dur - 0.3);
          k.t = nt;
        });
      });
    });
    ks.sort(function (x, y) { return x.t - y.t; });
  }

  /* ---- 时间轨：日子依次立起，hot 的是重点日子（更大、发亮，最后镜头轻轻偏向它那一头）；可选一道拱线标"等了多久"
   * 11-05 改（11-04 国行 AI 那一章：前两个日子一直没露脸，"11 月 4 日"和"12 月"两张标签叠成"11 月 4 日 月"）：
   *   · pos 只排先后，不按真实时间比例：相邻两个日子至少隔开整条轨的 TL_GAP（tlSpread），标签才不叠；
   *   · 镜头先装下整条轨（shA），每个日子立起时都在画面里；最后一个日子立起后，才慢慢转到 shB2（仍装下整条轨，偏向重点日子）；
   *     原来 shA 只装下左半截、在第一个重点日子前 1.2 秒就飞去右头，中间和左头的日子落在画面外；
   *   · 轨道跟着日子一段段画：说到哪个日子，光头正好走到那个点（原来是一口气匀速画完，和日子对不上）。
   * 11-06 改（11-06 选票那一章：时间轨说到一半插进一张对比卡，"周四"在对比卡之后才说到）：
   *   · 日子按"下一个别的模板什么时候开始"分成几段；每个日子的标签留到它那一段结束（不早于弹出后 1.4 秒）——原来重点日子
   *     按"下一个模板开始后 0.2 秒"收，比它弹出还早，于是再也收不掉，从 28 秒一直挂到片尾；
   *   · 被打断后再回来时，前面已收起的日子标签跟着重新出来，镜头也飞回整条轨（不再等最后一个日子后 2.2 秒）；
   *   · 每个日子可挂 logos（标志）和一张小图 image（标签上方；带图的重点日子标签也放在轨道上方）。 */
  TPL.timeline = {
    ext: [11, 11],
    build: function (b) {
      var g = b._.g, pal = this.pal, L = this.P.L, E = b._.o, self = this;
      var railY = 1.0, X0 = -11, X1 = 11, ticks = (b.ticks || []).slice(0, 7), n = ticks.length;
      var raw = ticks.map(function (q, i) { return q.pos != null && isFinite(+q.pos) ? clamp(+q.pos, 0, 1) : (n > 1 ? i / (n - 1) : 0); });
      var xs = tlSpread(raw, TL_GAP).map(function (u) { return -10 + u * 18.6; });
      var hotI = []; ticks.forEach(function (q, i) { if (q.hot) hotI.push(i); });
      E.xs = xs; E.hotI = hotI; E.n = n; E.railY = railY; E.X0 = X0; E.X1 = X1;
      E.rail = this.tube([V3(X0, railY, 0), V3(X1, railY, 0)], 0.075, this.flowMat(pal.acc, { dash: 70, glow: 1.6 }), 200); g.add(E.rail); this.flowMeshes.push(E.rail);
      // 两镜都装下整条轨：两头各留一张标签的宽度（标签宽约画面的 13%，见 .v3tick .c）；shB2 换个角度、偏向重点日子那一头
      var x0 = xs[0], x1 = xs[n - 1], span = Math.max(6, x1 - x0), mid = (x0 + x1) / 2, fwA = span + 6.4;
      var hx = hotI.length ? (xs[hotI[0]] + xs[hotI[hotI.length - 1]]) / 2 : x1, lean = (hx >= mid ? 1 : -1) * span * 0.02;
      // 这一段后面挂着背景配图（10-31 入口那一章）：配图立在右后方、底边抬高，平视时正好压在轨道上方那排标签上；
      // 镜头俯得低一些，远处的配图就落到标签上面去
      var bd = (b._.c.blocks || []).some(function (x) { return x.type === 'image_card' && x._ && x._.mode === 'backdrop' && x._.host === b; });
      var pA = bd ? 17 : 5;   // 11-05 实测：10-31 俯 11 度仍压字，15 度刚好贴着配图下沿，17 度留出一点空
      b._.shA = this.bshot(b, [mid - lean, 1.6, 0], -10, pA, fwA, 9, { pk: 1 });
      b._.shB2 = this.bshot(b, [mid + lean, 1.7, 0.3], -7, pA + 2, fwA, 9, { pk: 1 });
      var P = this.P;
      E.ticks = ticks.map(function (q, i) {
        var sk = q.shot ? tickShot(self, q) : null;                                     // 结合式：这一天带原文截图（小图＋弹出框）
        var hot = !!q.hot, src = !sk && q.img ? imgUrl(P, q.img) : null, up = !hot || !!src || !!sk;   // up：标签在轨道上方
        // 普通日子的圆点（11-05 调深）：原来是 35% 的主题色、浅色底上几乎看不见
        var disc = new THREE.Mesh(new THREE.CylinderGeometry(hot ? 0.42 : 0.3, hot ? 0.42 : 0.3, 0.16, 28), self.coreMat(hot ? pal.acc : pal.glass.clone().lerp(pal.acc, 0.62), hot ? 1.2 : 0.5));
        disc.position.set(xs[i], railY, 0); disc.rotation.x = Math.PI / 2; disc.scale.setScalar(0.001); g.add(disc);
        var gl = self.glow(hot ? 3.2 : 1.8, pal.acc, 0); gl.position.set(xs[i], railY, 0.2); g.add(gl);
        var post = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 1.2, 6), self.boxMat({ alpha: 0.5, rimK: 0.4 })); post.position.set(xs[i], railY + 0.75, 0); post.scale.y = 0.001; g.add(post);
        var lgs = q.logos && q.logos.length ? '<div class="lg v3logos">' + logoList(P, q.logos) + '</div>' : '';
        var ph = sk ? sk.th : (src ? '<div class="ph"><i style="background-image:url(&quot;' + src + '&quot;)"></i></div>' : '');
        var lb = self.label('<div class="v3tick' + (hot ? ' hot' : '') + (src || sk ? ' wimg' : '') + (sk ? ' wshot' : '') + '">' + ph + '<div class="d">' + esc(S2(q.date, L)) + '</div>' + lgs + (q.cap ? '<div class="c">' + noOrphan(S2(q.cap, L)) + '</div>' : '') + '</div>',
          up ? { obj: g, at: V3(xs[i], railY + 1.55, 0), shot: b._.shA, align: 'b', max: 1.15, fit: true } : { obj: g, at: V3(xs[i], railY - 0.55, 0.6), shot: b._.shA, align: 't', max: 1.15, fit: true });
        var tk = { disc: disc, glow: gl, post: post, lb: lb, x: xs[i], hot: hot, up: up, logos: q.logos, img: !!src };
        if (sk) { tk.shot = sk; (self.tlPops || (self.tlPops = [])).push(tk); }
        return tk;
      });
      // 同一侧叠住时错开一行（updateLabels）：轨道上方的往上错，下方的（不带图的重点日子）往下错
      var rowsOf = function (up) { return E.ticks.filter(function (k) { return k.up === up; }).map(function (k) { return k.lb; }); };
      (this.tlRows || (this.tlRows = [])).push({ dir: -1, lbs: rowsOf(true) }, { dir: 1, lbs: rowsOf(false) });
      var w = b.wait;
      if (w && w.label) {
        var i0 = clamp(w.from || 0, 0, n - 1), i1 = clamp(w.to != null ? w.to : n - 1, 0, n - 1), xa = xs[i0], xb = xs[i1];
        var arcPts = []; for (var k = 0; k <= 24; k++) { var u = k / 24; arcPts.push(V3(lerp(xa, xb, u), railY + 0.35 + Math.sin(u * Math.PI) * 2.6, -0.2)); }
        E.arc = this.tube(arcPts, 0.03, this.flowMat(pal.ink, { glow: 0.7, dash: 40, head: 0 }), 120); g.add(E.arc);
        E.lWait = this.label('<span class="v3tag v3glass">' + esc(S2(w.label, L)) + '</span>', { obj: g, at: V3((xa + xb) / 2, railY + 3.25, -0.2), shot: b._.shA, align: 'b' });
      }
      b._.enterAt = V3(X0, railY, 0); b._.exitAt = V3(X1, railY, 0); b._.headAt = V3(-6, 4, 0);
    },
    tl: function (b, a) {
      var E = b._.o, c = b._.c, self = this, st = bt(b, 'start', c.vs + 0.3);
      var tt = E.tt = listT(b, 'ticks', E.n, st, 0.9);
      var last = tt[E.n - 1];
      // 轨道一段段画：每段从上一个日子画到下一个日子，说到那个日子时光头正好到那一点；最后画完剩下的一截
      var rv = E.rail.material.uniforms.uReveal, t0 = st - 0.1, v0 = 0;
      a.ST(rv, { value: 0 });
      E.xs.forEach(function (x, i) {
        var t1 = Math.max(tt[i], t0 + 0.3), v1 = (x - E.X0) / (E.X1 - E.X0);
        a.U(rv, v0, v1, t0, t1 - t0, 'power1.inOut'); t0 = t1; v0 = v1;
      });
      a.U(rv, v0, 1, t0, 0.8, 'power1.out');
      E.ticks.forEach(function (k, i) {
        a.ST(k.disc.scale, { x: 0.001, y: 0.001, z: 0.001 }); a.ST(k.post.scale, { y: 0.001 }); a.ST(k.glow.material, { opacity: 0 });
        a.tl.fromTo(k.disc.scale, { x: 0.001, y: 0.001, z: 0.001 }, { x: 1, y: 1, z: 1, duration: 0.5, ease: 'back.out(2)' }, tt[i]);
        a.tl.fromTo(k.post.scale, { y: 0.001 }, { y: 1, duration: 0.45, ease: 'power2.out' }, tt[i] + 0.1);
        a.tl.fromTo(k.glow.material, { opacity: 0 }, { opacity: self.gk(k.hot ? 0.9 : 0.5), duration: 0.5 }, tt[i]);
        if (k.logos) popLogos(a, k.lb.el, k.logos, tt[i] + 0.15);
        var ph = k.img ? k.lb.el.querySelector('.ph i') : null;     // 小图慢慢推近一点（按时间轴）
        if (ph) { a.ST(ph, { scale: 1.12 }); a.tl.fromTo(ph, { scale: 1.12 }, { scale: 1, duration: Math.max(2, c.end - tt[i]), ease: 'none' }, tt[i]); }
        // 11-06 白天补：说到这个日子时小图先放大（从下沿往上长，不挤别的字），镜头停在时间轨的那 TL_IMG_HOLD 秒里一直大着，
        // 镜头起飞时再缩回原大；被打断后回来重新出现时就是原大（只在第一次说到时强调一下）
        var box = k.img ? k.lb.el.querySelector('.ph') : null;
        if (box) {
          a.ST(box, { scale: 1, transformOrigin: '50% 100%' });
          a.tl.fromTo(box, { scale: 1 }, { scale: TL_IMG_ZOOM, duration: 0.5, ease: 'back.out(1.4)' }, tt[i] + 0.15);
          a.tl.fromTo(box, { scale: TL_IMG_ZOOM }, { scale: 1, duration: 0.6, ease: 'power2.inOut' }, tt[i] + 0.15 + TL_IMG_HOLD);
        }
        if (k.shot) {          // 结合式：小图出来后 0.2 秒弹出、放大到画面中间；说到 mark 时荧光扫那句，扫完再停 TL_SHOT_TAIL 秒，缩回小图
          var S = k.shot, t0 = tt[i] + 0.35, mk = Math.max(bt(b, 'ticks' + i + '_mark', t0 + 0.8), t0 + 0.6);
          var root = S.el.querySelector('.v3sbx'), dur = sbxSweep(a, root, S.sx.lines, mk), back = mk + dur + TL_SHOT_TAIL;
          a.ST(S.pop, { v: 0 });
          a.tl.fromTo(S.pop, { v: 0 }, { v: 1, duration: 0.6, ease: 'none' }, t0);
          a.tl.fromTo(S.pop, { v: 1 }, { v: 0, duration: 0.55, ease: 'none' }, back);
          sbxTl(a, root, t0, back, mk, dur);
          S.t0 = t0; S.mk = mk; S.t1 = back + 0.55;
        }
      });
      // 分段：相邻的日子之间没有别的模板开始，就在同一段；段尾＝这一段之后第一个别的模板开始的时刻（没有就是章末）
      var segs = tlSegments(b, tt);
      segs.forEach(function (sg, si) {
        var imgPop = 0, shotEnd = 0;                       // 这一段新说到的带小图的日子：标签留到镜头起飞后 0.5 秒（见 tlImageHold）
        for (var j = sg.i0; j <= sg.i1; j++) { if (E.ticks[j].img) imgPop = Math.max(imgPop, tt[j] + 0.15); if (E.ticks[j].shot) shotEnd = Math.max(shotEnd, E.ticks[j].shot.t1 + 0.2); }
        for (var i = 0; i <= sg.i1; i++) {
          var k = E.ticks[i], own = i >= sg.i0;            // own：这一段新说到的日子；前面段的日子跟着重新出来
          var on = own ? tt[i] + 0.15 : sg.t0 + 0.15;
          var off = Math.max(sg.end + (k.hot ? 0.2 : -0.2), on + 1.4, imgPop ? imgPop + TL_IMG_HOLD + 0.5 : 0);
          if (shotEnd) off = Math.max(off, shotEnd + 0.5);
          a.show(k.lb, on, own ? 0.5 : 0.4); a.hide(k.lb, off, 0.4);
        }
        if (E.lWait && si === segs.length - 1) a.hide(E.lWait, Math.max(sg.end - 0.2, sg.t0 + 1.4), 0.4);
      });
      if (E.arc) {
        var wt = bt(b, 'wait', tt[clamp((b.wait || {}).from || 0, 0, E.n - 1)] + 1.0);
        a.ST(E.arc.material.uniforms.uReveal, { value: 0 }); a.U(E.arc.material.uniforms.uReveal, 0, 1, wt, 1.1, 'power2.inOut'); a.show(E.lWait, wt + 0.7);
      }
      E.ticks.forEach(function (k) { a.tl.fromTo(k.glow.material, { opacity: self.gk(k.hot ? 0.9 : 0.5) }, { opacity: 0, duration: 0.8 }, c.end); });
      a.U(E.rail.material.uniforms.uFade, 1, 0.35, c.end + 0.2, 1);
      E.st = st; E.last = last; E.segs = segs;
    },
    cams: function (b) {
      // 先装下整条轨，日子一个个在画面里立起；被别的模板打断后，再说到下一个日子时镜头飞回整条轨；
      // 最后一个立起后再慢慢转向重点日子那一头（仍装下整条轨；这一段太短就不转）
      var E = b._.o, k = [{ t: E.st + 0.5, s: b._.shA, dur: 1.3, ease: 'io', arc: 9 }], segs = E.segs || [];
      segs.forEach(function (sg, si) { if (si) k.push({ t: sg.t0 + 0.9, s: b._.shA, dur: 1.2, ease: 'io', arc: 4 }); });
      var lastEnd = segs.length ? segs[segs.length - 1].end : Infinity, lastT = E.last + 2.2;
      E.ticks.forEach(function (tk) { if (tk.shot) lastT = Math.max(lastT, tk.shot.t1 + 0.2 + 2.2); });   // 结合式：截图缩回以后才慢慢转
      if (lastT < lastEnd - 0.4) k.push({ t: lastT, s: b._.shB2, dur: 2.2, ease: 'sine' });
      return k;
    },
    settle: function (b) { return b._.o.last + 1.2; },
    explore: function (b) { return [2, b._.shB2]; }
  };

  /* ---- 2.5D 配图（不能单独成章：挂在这一章背景里，或立在分岔路的尽头） ---- */
  TPL.image_card = {
    build: function (b) {
      var fork = b._.mode === 'fork', w = fork ? 15 : 22, h = fork ? 8.44 : 12.4;
      var m = b._.o.m = this.photo(b.img || b.id, w, h, fork ? 1.3 : 2.0); m.position.set(0, fork ? 5.4 : 7.0, 0); b._.g.add(m); this.photos.push(m);
    },
    tl: function (b, a) {
      var m = b._.o.m, c = b._.c, pu = m.material.uniforms, fork = b._.mode === 'fork', t0 = bt(b, 'in', c.vs + 1.5);
      a.ST(pu.uReveal, { value: 0 }); a.U(pu.uReveal, 0, 1.02, t0 - 0.6, fork ? 1.8 : 1.6, 'power1.inOut');
      var off = fork ? c.end + 0.2 : (b._.hideAt != null ? b._.hideAt : c.end - 0.6);
      a.U(pu.uReveal, 1.02, 0, off, 1.2, 'power1.inOut');
      if (m.userData.cap) {
        var panel = (c._real || []).filter(function (x) { return TPL[x.type].panel && x._.fork; })[0];
        a.show(m.userData.cap, t0 + (fork ? 0.7 : 0.6));
        a.hide(m.userData.cap, fork && panel ? startT(panel) - 0.2 : off - 0.1, 0.3);
      }
    },
    cams: function () { return []; }
  };

  /* ---- 玻璃手机：屏幕上 1–5 行功能，每行挂一个小标；底部一行说明 ---- */
  TPL.phone_list = {
    ext: [1.8, 1.8],
    startT: function (b) { return bt(b, 'show', firstT(b)); },
    build: function (b) {
      var g = b._.g, pal = this.pal, L = this.P.L, E = b._.o;
      var PW = 3.5, PH = 6.6;
      E.phone = new THREE.Mesh(new THREE.PlaneGeometry(PW, PH), this.panelMat(PW, PH, { radius: 0.55, alpha: pal.dark ? 0.5 : 0.62, edgeGlow: 1.2 }));
      E.phone.position.set(0, 4.6, 1.2); E.phone.material.uniforms.uFade.value = 0; g.add(E.phone); this.glass.push(E.phone);
      E.phoneGlow = this.glow(9, pal.acc, 0); E.phoneGlow.position.set(0, 4.6, 0.6); g.add(E.phoneGlow);
      b._.shC = this.bshot(b, [-1.6, 4.3, 1.2], -14, 5, 10.5, 8.8, { pc: [0, 4.5, 1.2] });
      var rows = (b.rows || []).slice(0, 5);
      var row = function (r, i) {
        return '<div class="row" data-r="' + i + '"><span><b>' + esc(S2(r.name, L)) + '</b>' + (r.sub ? '<small>' + esc(S2(r.sub, L)) + '</small>' : '') + '</span>' +
          (r.pill ? '<span class="v3pill" data-p="' + i + '">' + esc(S2(r.pill, L)) + '</span>' : '') + '</div>';
      };
      var ft = b.foot ? '<div class="ft"><span>' + esc(S2(b.foot.text, L)) + '</span>' + (b.foot.pill ? '<span><span class="v3pill ext" data-p="f">' + esc(S2(b.foot.pill, L)) + '</span></span>' : '') + '</div>' : '';
      E.lPhone = this.label('<div class="v3phone v3glass">' + (b.head ? '<div class="ph">' + esc(S2(b.head, L)) + '</div>' : '') + rows.map(row).join('') + ft + '</div>',
        { obj: E.phone, at: V3(0, 0, 0.05), shot: b._.shC, fitW: PW * 0.88, fitH: PH * 0.9 });
      this.shadow(5, 3, g, 0, 1.2, 0.9);
      E.n = rows.length;
      b._.exitAt = V3(0, 2.4, 1.4); b._.enterAt = V3(0, 2.4, 1.4); b._.headAt = V3(0, 8.5, 1.2);
    },
    tl: function (b, a) {
      var E = b._.o, c = b._.c, self = this, show = bt(b, 'show', bt(b, 'rows0', c.vs + 1.5) - 0.6), rise = bt(b, 'rise', show - 1.3);
      a.ST(E.phone.material.uniforms.uFade, { value: 0 }); a.ST(E.phone.position, { y: 2.2 });
      a.U(E.phone.material.uniforms.uFade, 0, 1, rise - 0.2, 0.8);
      a.tl.fromTo(E.phone.position, { y: 2.2 }, { y: 4.6, duration: 1.2, ease: 'power3.out' }, rise - 0.2);
      a.ST(E.phoneGlow.material, { opacity: 0 }); a.tl.fromTo(E.phoneGlow.material, { opacity: 0 }, { opacity: self.gk(0.55), duration: 0.8 }, rise);
      a.show(E.lPhone, show - 0.5, 0.5);
      var rt = listT(b, 'rows', E.n, show + 0.4, 0.6);
      var footT = b.t && typeof b.t.foot === 'number' ? b.t.foot : (rt.length ? rt[rt.length - 1] + 1.2 : show + 1.5);
      var pills = E.lPhone.el.querySelectorAll('[data-p]'), rows = E.lPhone.el.querySelectorAll('[data-r]');
      Array.prototype.forEach.call(pills, function (p) {
        var k = p.getAttribute('data-p'), at = k === 'f' ? footT : rt[+k];
        a.ST(p, { autoAlpha: 0, x: 18, scale: 0.8 });
        a.tl.fromTo(p, { autoAlpha: 0, x: 18, scale: 0.8 }, { autoAlpha: 1, x: 0, scale: 1, duration: 0.5, ease: 'back.out(2)' }, at - 0.1);
      });
      Array.prototype.forEach.call(rows, function (r) {
        var at = rt[+r.getAttribute('data-r')];
        a.ST(r, { autoAlpha: 0.35 }); a.tl.fromTo(r, { autoAlpha: 0.35 }, { autoAlpha: 1, duration: 0.3 }, at - 0.15);
      });
      a.hide(E.lPhone, c.end + 0.4, 0.5);
      a.U(E.phone.material.uniforms.uFade, 1, 0, c.end + 0.5, 0.8, 'power1.in');
      a.tl.fromTo(E.phoneGlow.material, { opacity: self.gk(0.55) }, { opacity: 0, duration: 0.6 }, c.end + 0.4);
      E.show = show; E.footT = footT;
    },
    cams: function (b) { return [{ t: b._.o.show + 0.1, s: b._.shC, dur: 1.3, ease: 'io', arc: 6 }]; },
    settle: function (b) { return b._.o.footT + 0.6; },
    explore: function (b) { return [1, b._.shC]; }
  };

  /* ---- 等轴测传播链（SVG 画在一块大玻璃板上） ---- */
  TPL.chain = {
    ext: [9, 9],
    build: function (b) {
      var g = b._.g, pal = this.pal, L = this.P.L, Z = b._.o;
      var PW = 17, PH = 9.56;
      Z.panel = new THREE.Mesh(new THREE.PlaneGeometry(PW, PH), this.panelMat(PW, PH, { radius: 0.6, alpha: pal.dark ? 0.42 : 0.55, edgeGlow: 0.9 }));
      Z.panel.position.set(0, 5.6, 0); Z.panel.material.uniforms.uFade.value = 0; g.add(Z.panel); this.glass.push(Z.panel);
      b._.shA = this.bshot(b, [0, 5.6, 0], 0, 4, 19.8, 11.6);
      b._.shA2 = this.bshot(b, [0.8, 5.5, 0], 5, 4, 18.8, 11);
      Z.m = new Machine(L, b);
      var box = el('div', 'v3machine'); box.appendChild(Z.m.svg);
      Z.lMachine = this.label('<div class="v3machine-box"></div>', { obj: Z.panel, at: V3(0, 0, 0.05), shot: b._.shA, min: 0.3, max: 1.6, fitW: PW * 0.96, fitH: PH * 0.96 });
      Z.lMachine.inEl.firstChild.appendChild(box);
      if (b.head) Z.lHead = this.label('<div class="v3head v3glass"><div class="h">' + esc(S2(b.head, L)) + '</div>' + (b.head_sub ? '<div class="s">' + esc(S2(b.head_sub, L)) + '</div>' : '') + '</div>', { obj: Z.panel, at: V3(PW / 2 - 0.55, PH / 2 - 0.55, 0.05), shot: b._.shA, align: 'tr' });
      this.shadow(PW * 1.1, 4, g, 0, 0.6, 0.9);
      if (b.window) Z.lWin = this.label('<span class="v3tag v3glass">' + esc(S2(b.window, L)) + '</span>', { obj: Z.panel, at: V3(-PW / 2 + 0.6, -PH / 2 + 0.6, 0.05), shot: b._.shA, align: 'bl' });
      Z.svgW = function (sx, sy, out) { out = out || V3(0, 0, 0); out.set((sx / 1600 - 0.5) * PW, (0.5 - sy / 900) * PH, 0.08); return Z.panel.localToWorld(out); };
      b._.enterWorld = function (out) { return Z.svgW(Z.m.pub[0], Z.m.pub[1], out); };
      b._.enterAt = V3(-PW / 2, 1, 0); b._.exitAt = V3(PW / 2 - 2, 1, 0); b._.headAt = V3(0, 10.8, 0);
    },
    tl: function (b, a) {
      var Z = b._.o, c = b._.c, s0 = bt(b, 'draw', c.vs + 0.1), st = bt(b, 'start', s0 + 2.0);
      var nh = Math.max(1, Z.m.n - 1), hops = listT(b, 'hops', nh, st + 0.4, 2.2);
      a.ST(Z.panel.material.uniforms.uFade, { value: 0 }); a.U(Z.panel.material.uniforms.uFade, 0, 1, s0 - 0.6, 0.9);
      a.show(Z.lMachine, s0 - 0.4, 0.6); if (Z.lHead) a.show(Z.lHead, st + 0.2); if (Z.lWin) a.show(Z.lWin, bt(b, 'window', hops[Math.min(1, hops.length - 1)]) + 0.2);
      Z.k = { draw: s0 - 0.3, start: st, mark: bt(b, 'mark', null), hops: hops };
      var nx = b._.next && b._.next.type === 'particle_counter' && b._.next._.attach === b ? b._.next : null;
      if (nx) {
        var c5 = bt(nx, 'count', hops[hops.length - 1] + 2);
        a.tl.fromTo(Z.lMachine, { a: 1 }, { a: 0.14, duration: 0.6, ease: 'power1.inOut' }, c5 - 0.8);
        a.U(Z.panel.material.uniforms.uFade, 1, 0.45, c5 - 0.8, 0.6);
        if (Z.lHead) a.hide(Z.lHead, c5 - 0.6, 0.4); if (Z.lWin) a.hide(Z.lWin, c5 - 0.6, 0.4);
        a.tl.fromTo(Z.lMachine, { a: 0.14 }, { a: 0, duration: 0.5 }, c.end - 0.2); a.U(Z.panel.material.uniforms.uFade, 0.45, 0, c.end - 0.2, 0.9);
      } else {
        a.tl.fromTo(Z.lMachine, { a: 1 }, { a: 0, duration: 0.5 }, c.end - 0.2); a.U(Z.panel.material.uniforms.uFade, 1, 0, c.end - 0.2, 0.9);
        if (Z.lHead) a.hide(Z.lHead, c.end - 0.3, 0.4); if (Z.lWin) a.hide(Z.lWin, c.end - 0.3, 0.4);
      }
      Z.st = st; Z.lastHop = hops[hops.length - 1];
    },
    cams: function (b) { var Z = b._.o; return [{ t: Z.st - 0.2, s: b._.shA, dur: 1.3, ease: 'io', arc: 3 }, { t: Z.lastHop, s: b._.shA2, dur: 4.5, ease: 'sine' }]; },
    settle: function (b) { return b._.o.lastHop + 1.4; },
    explore: function (b) { return [1, b._.shA2]; },
    frame: function (b, t) { var Z = b._.o; if (Z.k && Z.lMachine.a > 0.003) Z.m.update(t, Z.k, this.P.rm); }
  };

  /* ---- 几千个点聚成一个数字（放在 chain 后面时从最后一站升起） ---- */
  TPL.particle_counter = {
    ext: [5.5, 5.5],
    build: function (b) {
      var g = b._.g, pal = this.pal, L = this.P.L, Z = b._.o, ch = b._.attach;
      var N = this.low ? 2500 : 5000;
      var geo = new THREE.BufferGeometry(), aA = new Float32Array(N * 3), aB = new Float32Array(N * 3), aC = new Float32Array(N * 4), aR = new Float32Array(N);
      var digits = this.textPoints(S2(b.value, L) || '0', N);
      var dW = 10.5, dH = 3.6, dC = ch ? V3(0.6, 6.4, 4.2) : V3(0, 6.4, 2.5);
      var pw = V3(0, 0, 0), db = ch ? ch._.o.m.devBox : null;
      g.updateMatrixWorld(true);
      for (var i = 0; i < N; i++) {
        if (ch) { var sx = lerp(db.x0, db.x1, rnd(i * 2 + 7)), sy = lerp(db.y0, db.y1, rnd(i * 2 + 8)); ch._.o.svgW(sx, sy, pw); g.worldToLocal(pw); }
        else { var r = Math.sqrt(rnd(i * 2 + 7)) * 4.5, th = rnd(i * 2 + 8) * Math.PI * 2; pw.set(Math.cos(th) * r, 0.1, Math.sin(th) * r * 0.6 + dC.z); }
        aA[i * 3] = pw.x; aA[i * 3 + 1] = pw.y; aA[i * 3 + 2] = pw.z + rnd(i + 3) * 0.2;
        var d = digits[i];
        aB[i * 3] = dC.x + (d[0] - 0.5) * dW; aB[i * 3 + 1] = dC.y + (0.5 - d[1]) * dH; aB[i * 3 + 2] = dC.z + (rnd(i * 5 + 1) - 0.5) * 0.5;
        aC[i * 4] = rnd(i * 13 + 2) < 0.5 ? 0 : 1; aC[i * 4 + 1] = rnd(i * 17 + 3); aC[i * 4 + 2] = (rnd(i * 19 + 4) - 0.5) * 2; aC[i * 4 + 3] = (rnd(i * 23 + 5) - 0.5) * 2;
        aR[i] = rnd(i * 29 + 6);
      }
      geo.setAttribute('position', new THREE.BufferAttribute(aA.slice(), 3));
      geo.setAttribute('aA', new THREE.BufferAttribute(aA, 3)); geo.setAttribute('aB', new THREE.BufferAttribute(aB, 3));
      geo.setAttribute('aC', new THREE.BufferAttribute(aC, 4)); geo.setAttribute('aR', new THREE.BufferAttribute(aR, 1));
      var P7 = []; for (var k = 0; k < 7; k++) P7.push(dC.clone());
      Z.swarmU = { uM1: { value: 0 }, uM2: { value: 0 }, uFlow: { value: 0 }, uSize: { value: this.low ? 3.4 : 2.6 }, uPR: { value: this.pr }, uP: { value: P7 },
        uC1: { value: pal.acc.clone().multiplyScalar(pal.dark ? 1.4 : 1.0) }, uC2: { value: pal.alt.clone().multiplyScalar(pal.dark ? 1.4 : 1.0) }, uC3: { value: pal.warn.clone() },
        uFade: { value: 0 }, uLit: { value: 0 } };
      Z.swarm = new THREE.Points(geo, new THREE.ShaderMaterial({ uniforms: Z.swarmU, vertexShader: SWARM_V, fragmentShader: SWARM_F, transparent: true, depthWrite: false,
        blending: pal.dark ? THREE.AdditiveBlending : THREE.NormalBlending }));
      Z.swarm.frustumCulled = false; Z.swarm.renderOrder = 5; g.add(Z.swarm);
      b._.shB = this.bshot(b, [dC.x, dC.y - 0.6, dC.z], -18, 7, 14, 8.8);
      Z.lNum = this.label('<div class="v3cap">' + (b.cap ? '<div class="a">' + esc(S2(b.cap, L)) + '</div>' : '') + (b.sub ? '<div class="b">' + esc(S2(b.sub, L)) + '</div>' : '') + '</div>',
        { obj: g, at: V3(dC.x, dC.y - dH / 2 - 0.5, dC.z), shot: b._.shB, align: 't' });
      Z.dC = dC;
      b._.exitAt = dC.clone(); b._.enterAt = V3(0, 1, 0); b._.headAt = V3(dC.x, dC.y + 3, dC.z);
    },
    tl: function (b, a) {
      var Z = b._.o, c = b._.c, c5 = bt(b, 'count', c.vs + 1.0);
      a.U(Z.swarmU.uFade, 0, 1, c5 - 0.9, 0.5);
      a.U(Z.swarmU.uM1, 0, 1, c5 - 0.6, 2.2, 'power2.inOut');
      a.show(Z.lNum, c5 + 1.0);
      a.hide(Z.lNum, c.end - 0.3, 0.4);
      if (!Z.handoff) a.U(Z.swarmU.uFade, 1, 0, c.end - 0.2, 0.8);
      Z.c5 = c5;
    },
    cams: function (b) { return [{ t: b._.o.c5 + 0.3, s: b._.shB, dur: 1.4, ease: 'io', arc: 6 }]; },
    settle: function (b) { return b._.o.c5 + 1.8; },
    explore: function (b) { return [2, b._.shB]; },
    frame: function (b, t) {
      var Z = b._.o, ch = b._.attach, from = ch && ch._.o.lastHop != null ? ch._.o.lastHop : Z.c5 || 0;
      Z.swarmU.uFlow.value = this.P.rm ? 0.2 : Math.max(0, t - from) * 0.06; Z.swarmU.uLit.value = 0;
    }
  };

  /* ---- 一条路分成两条；后面紧跟的两个卡片模板站在两条路的尽头 ---- */
  TPL.fork = {
    ext: [21, 12],
    build: function (b) {
      var g = b._.g, pal = this.pal, L = this.P.L, Md = b._.o;
      var J = V3(-8, 0.15, 0), A = V3(8, 0.15, -7.2), B = V3(8, 0.15, 7.2), cA = V3(0, 0.15, -5.2), cB = V3(0, 0.15, 5.2);
      var bezPts = function (a, bb, cc) { var r = []; for (var i = 0; i <= 30; i++) { var u = i / 30, v = 1 - u; r.push(V3(v * v * a.x + 2 * v * u * bb.x + u * u * cc.x, 0.15, v * v * a.z + 2 * v * u * bb.z + u * u * cc.z)); } return r; };
      Md.trunk = this.tube([V3(-21, 0.15, 0), V3(-14, 0.15, 0), J], 0.09, this.flowMat(pal.acc, { dash: 26, glow: 1.6 }), 80); g.add(Md.trunk);
      Md.pa = this.tube(bezPts(J, cA, A), 0.09, this.flowMat(pal.acc, { dash: 30, glow: 1.8 }), 120); g.add(Md.pa);
      Md.pb = this.tube(bezPts(J, cB, B), 0.09, this.flowMat(pal.alt, { dash: 30, glow: 1.8 }), 120); g.add(Md.pb);
      this.flowMeshes.push(Md.trunk, Md.pa, Md.pb);
      Md.jGlow = this.glow(4.5, pal.acc, 0); Md.jGlow.position.copy(J); g.add(Md.jGlow);
      Md.J = J; Md.A = A; Md.B = B; Md.cA = cA; Md.cB = cB;
      b._.shA = this.bshot(b, [2, 2.4, 0], -90, 21, 30, 16);
      Md.lEff = this.label('<span class="v3fork v3glass">' + esc(S2(b.a, L)) + '</span>', { obj: g, at: V3(1.5, 1.8, -5.4), shot: b._.shA, align: 'b' });
      Md.lPrice = this.label('<span class="v3fork v3glass">' + esc(S2(b.b, L)) + '</span>', { obj: g, at: V3(1.5, 1.8, 5.4), shot: b._.shA, align: 'b' });
      b._.enterAt = V3(-21, 0.15, 0); b._.exitAt = V3(8, 0.15, 0); b._.headAt = V3(0, 6, 0);
    },
    tl: function (b, a) {
      var Md = b._.o, c = b._.c, self = this, f0 = bt(b, 'fork', c.vs + 0.6);
      [Md.trunk, Md.pa, Md.pb].forEach(function (m, i) { a.ST(m.material.uniforms.uReveal, { value: 0 }); a.U(m.material.uniforms.uReveal, 0, 1, i ? f0 + 0.3 : (b._.first ? c.start : f0 - 1.2), i ? 1.4 : 1.2, 'power2.inOut'); });
      a.ST(Md.jGlow.material, { opacity: 0 }); a.tl.fromTo(Md.jGlow.material, { opacity: 0 }, { opacity: self.gk(0.9), duration: 0.6 }, f0);
      a.show(Md.lEff, bt(b, 'a', f0 + 1.0) - 0.1); a.show(Md.lPrice, bt(b, 'b', f0 + 3.0) - 0.1);
      [Md.lEff, Md.lPrice].forEach(function (lb) { a.hide(lb, c.end + 0.3, 0.5); });
      Md.f0 = f0;
    },
    cams: function (b) { return [{ t: b._.o.f0 + 0.6, s: b._.shA, dur: 1.3, ease: 'io', arc: 4 }]; },
    settle: function (b) { return bt(b, 'b', b._.o.f0 + 3) + 1.2; },
    explore: function (b) { return [3, b._.shA]; }
  };

  // 卡片类模板共用：一块玻璃板＋一张 HTML 卡片；站在分岔路尽头时面朝来路，否则面朝前
  function panelBuild(self, b, inner, size, cls) {
    var g = b._.g, pal = self.pal, w = size ? size[0] : 9.6, h = size ? size[1] : 6.6;
    var p = new THREE.Mesh(new THREE.PlaneGeometry(w, h), self.panelMat(w, h, { radius: 0.5, alpha: pal.dark ? 0.4 : 0.5, edgeGlow: 1.0 }));
    p.position.set(0, 3.9, 0); p.material.uniforms.uFade.value = 0; if (b._.branch) p.material.uniforms.uEdge.value.copy(pal.alt).multiplyScalar(1.3); g.add(p);
    self.shadow(w * 1.05, 3.5, g, 0, 0, 0.8); self.glass.push(p);
    b._.shS = self.bshot(b, [0, 3.9, 0], b._.fork ? (b._.branch ? 14 : -14) : 0, 3, w * 1.19, h * 1.18);
    var lb = self.label('<div class="v3card v3glass' + (cls ? ' ' + cls : '') + '">' + inner + '</div>', { obj: p, at: V3(0, 0, 0.05), shot: b._.shS, fitW: w * 0.9, fitH: h * 0.86 });
    b._.o.pan = p; b._.o.lb = lb;
    b._.enterAt = V3(0, 1, 0); b._.exitAt = V3(0, 1, 0); b._.headAt = V3(0, 7.6, 0);
    return lb;
  }
  // 11-08（K45）：同章下一块开始前 0.4 秒收起卡片和压图（站在分岔路尽头的照旧到章末）；开关关着时照旧到章末
  function panelEnd(b, show) { var c = b._.c; return (FX && b._.nextT != null && !b._.fork) ? Math.max(show + 2, b._.nextT - 0.4) : c.end + 0.3; }
  function panelTl(b, a, show) {
    var o = b._.o, c = b._.c, end = panelEnd(b, show);
    a.ST(o.pan.material.uniforms.uFade, { value: 0 }); a.U(o.pan.material.uniforms.uFade, 0, 1, show - 0.3, 0.8); a.show(o.lb, show, 0.6);
    a.hide(o.lb, end, 0.5); a.U(o.pan.material.uniforms.uFade, 1, 0, end, 0.8, 'power1.in');
  }

  /* ---- 压在配图上（2026-11-07 加；只在分镜写了 photo 字段时起作用，动效尝试版用）：tile_row、compare_panel 后面立一张清楚的配图
   *   （不做视差、轻微柔化），卡片站在图前，镜头正对配图装下整张图；配图在 photo 触发词（没写就是这一块第一个触发词前 0.3 秒）溶解出现，
   *   这一块收场时溶解消失；这一块在一行里占得宽一些（extPhoto），左右的模板不进画面。分镜没写 photo 的不走这一段，画面和原来逐像素相同。 */
  var OVP_Z = -1.6, OVP_BLUR = 0.5;
  function ovpOn(P, b) { return !!(b.photo_img && (P.v.images || {})[b.photo_img]); }
  function ovpBuild(self, b, cx, w, pk) {      // pk：竖屏时横向装下几成，同时改看这一块的中心（卡片在竖屏会放宽，偏在图的一边就出画）
    var h = w * 9 / 16, cy = h / 2 + 0.1, m = self.photo(b.photo_img, w, h, OVP_BLUR);
    m.position.set(cx, cy, OVP_Z); b._.g.add(m); self.photos.push(m);
    b._.o.ovp = m;
    return self.bshot(b, [cx, cy, OVP_Z], 0, 2, w * 1.02, h * 1.02, pk ? { pk: pk, pc: [0, cy, OVP_Z] } : { pk: 1 });
  }
  function ovpTl(b, a, t0, off) {
    var pu = b._.o.ovp.material.uniforms;
    a.ST(pu.uReveal, { value: 0 }); a.U(pu.uReveal, 0, 1.02, t0 - 0.6, 1.5, 'power1.inOut');
    a.U(pu.uReveal, 1.02, 0, off, 1.0, 'power1.inOut');
    b._.o.ovpT = t0;
  }

  /* ---- 玻璃卡片：标题、一个大数字、1–4 根对比条（条长只是示意） ----
   * 11-07 补（都只在写了才有）：photo 压在配图上（卡片收小、站在图的右半边）；src_tag 卡片顶上的出处签；bars[].val 对比条末尾的数（如"1""约 3"）。 */
  TPL.compare_panel = {
    ext: [5, 5], panel: true, extPhoto: [13.8, 5.0],
    startT: function (b) { return bt(b, 'show', firstT(b)); },
    build: function (b) {
      var L = this.P.L, k = b.kpi || {}, bars = (b.bars || []).slice(0, 4), ovp = ovpOn(this.P, b);
      var hasV = bars.some(function (x) { return x.val; });
      var longV = FX && hasV && bars.some(function (x) { return String(S2(x.val, L) || '').replace(/\s/g, '').length > 6; });
      // 11-09：不到 7 个字、但比数值列宽的数（"约 18 小时""16% 以上"）原来出卡片右边 27–40 像素。开关开着时各行共用一套列（.bars.sg，
      //   CSS 子网格）：数值列按最长的那个数放宽（最多 11u，再长就在列里换行），条子跟着缩短，几根条子仍一样长、一样起点
      panelBuild(this, b, (b.src_tag ? '<div class="stag"><b>' + esc(S2(b.src_tag, L)) + '</b></div>' : '') + '<div class="hd">' + esc(S2(b.head, L)) + '</div>' + (b.sub ? '<div class="sb">' + esc(S2(b.sub, L)) + '</div>' : '') +
        (k.value ? '<div class="kpi"><span class="n v3n">' + numUnit(S2(k.value, L)) + '</span>' + (k.text ? '<span class="sb">' + noOrphan(S2(k.text, L)) + '</span>' : '') + '</div>' : '') +
        (bars.length ? '<div class="bars' + (FX && hasV && !longV ? ' sg' : '') + '">' + bars.map(function (bar, i) { return '<div class="bar' + (bar.me ? ' me' : '') + (hasV ? ' wv' : '') + (longV ? ' lv' : '') + '"><span>' + esc(S2(bar.label, L)) + '</span><i data-bar="' + i + '"></i>' + (hasV ? '<b class="v">' + esc(S2(bar.val, L) || '') + '</b>' : '') + '</div>'; }).join('') + '</div>' : '') +
        (b.foot ? '<div class="ft v3acc" style="font-weight:600">' + esc(S2(b.foot, L)) + '</div>' : ''), ovp ? [7.4, 6.0] : undefined, ovp ? 'v3cp ovp' : undefined);
      b._.o.bars = bars;
      // 卡片站在配图右半边，镜头对着整张图；11-08：配图中心从 −4.4 挪到 −3.9（卡片在画面里左移约 40 像素），原来卡片外框出右边
      if (ovp) { b._.shS = ovpBuild(this, b, FX ? -3.9 : -4.4, 18, 0.5); b._.o.lb.shot = b._.shS; }
    },
    tl: function (b, a) {
      var o = b._.o, show = bt(b, 'show', b._.c.vs + 1);
      panelTl(b, a, show);
      if (o.ovp) ovpTl(b, a, bt(b, 'photo', show - 0.3), panelEnd(b, show));
      var els = o.lb.el.querySelectorAll('[data-bar]'), bt2 = listT(b, 'bars', o.bars.length, show + 1.2, 1.5);
      a.ST(els, { scaleX: 0 });
      Array.prototype.forEach.call(els, function (e, i) { a.tl.fromTo(e, { scaleX: 0 }, { scaleX: clamp(+o.bars[i].value || 0, 0.02, 1), duration: 0.9, ease: 'power2.out' }, bt2[i] - 0.1); });
      o.show = show; o.last = bt2.length ? bt2[bt2.length - 1] : show + 1;
    },
    cams: function (b) { return [{ t: b._.o.show + 0.9, s: b._.shS, dur: 1.5, ease: 'io', arc: 6 }]; },
    settle: function (b) { return b._.o.last + 1.0; },
    explore: function (b) { return [1, b._.shS]; }
  };

  /* ---- 玻璃卡片：从 A 到 B 两个大字，加 2–6 根逐根长出的柱子 ---- */
  TPL.quota_bars = {
    ext: [5, 5], panel: true,
    startT: function (b) { return bt(b, 'show', firstT(b)); },
    build: function (b) {
      var L = this.P.L;
      panelBuild(this, b, '<div class="hd">' + esc(S2(b.head, L)) + '</div>' + (b.sub ? '<div class="sb">' + esc(S2(b.sub, L)) + '</div>' : '') +
        ((b.from || b.to) ? '<div class="kpi">' + (b.from ? '<span class="n v3n" data-k="from">' + esc(S2(b.from, L)) + '</span>' : '') + (b.from && b.to ? '<span class="ar">→</span>' : '') +
          (b.to ? '<span class="n v3n v3acc" data-k="to">' + esc(S2(b.to, L)) + '</span>' : '') + '</div>' : '') +
        (b.title ? '<div class="sb">' + esc(S2(b.title, L)) + '</div>' : '') + '<div class="chart" data-chart="1"></div>' + (b.foot ? '<div class="ft">' + esc(S2(b.foot, L)) + '</div>' : ''));
      b._.o.stages = (b.stages || []).slice(0, 6);
    },
    tl: function (b, a) {
      var o = b._.o, show = bt(b, 'show', b._.c.vs + 1), f = bt(b, 'from', show + 1.5), to = bt(b, 'to', f + 1.5);
      panelTl(b, a, show);
      var k1 = o.lb.el.querySelector('[data-k="from"]'), k2 = o.lb.el.querySelector('[data-k="to"]');
      if (k1) { a.ST(k1, { autoAlpha: 0, y: 12 }); a.tl.fromTo(k1, { autoAlpha: 0, y: 12 }, { autoAlpha: 1, y: 0, duration: 0.5, ease: 'power3.out' }, f - 0.1); }
      if (k2) { a.ST(k2, { autoAlpha: 0, y: 12 }); a.tl.fromTo(k2, { autoAlpha: 0, y: 12 }, { autoAlpha: 1, y: 0, duration: 0.5, ease: 'power3.out' }, to - 0.1); }
      o.chartK = { t0: f - 0.3, last: to - 0.15 }; o.show = show; o.to = to;
    },
    cams: function (b) { return [{ t: b._.o.show + 0.5, s: b._.shS, dur: 1.4, ease: 'io', arc: 6 }]; },
    settle: function (b) { return b._.o.to + 1.6; },
    explore: function (b) { return [1, b._.shS]; },
    frame: function (b, t) {
      var o = b._.o, host = o.lb.el.querySelector('[data-chart]'); if (!host) return;
      var st = o.stages, k = o.chartK || { t0: 0 }, n = st.length, max = Math.max.apply(null, st.map(function (s) { return +s.value || 0; }).concat([1]));
      var vals = st.map(function (s, i) { var t0 = i === n - 1 && k.last ? k.last : k.t0 + i * 0.38; var u = sat((t - t0) / 0.7); return Math.round((+s.value || 0) * out3(u) * 10) / 10; });
      var key = vals.join(',');
      if (key === o._key) return;
      o._key = key;
      var L = this.P.L, labels = st.map(function (s, i) { return S2(s.label, L) || String(i + 1); }), pal = this.pal, accHex = pal.accHex, soft = 'rgba(' + this.P.accRGB.join(',') + ',0.38)';
      var ink = pal.dark ? 'rgba(245,239,230,.75)' : 'rgba(58,47,34,.75)';
      if (window.echarts && !this.P.noCharts) {
        if (!o.chart) {
          try {
            o.chart = window.echarts.init(host, null, { renderer: 'svg' }); this.charts.push(o.chart);
            o.chart.setOption({ animation: false, grid: { left: 4, right: 4, top: 22, bottom: 22 },
              xAxis: { type: 'category', data: labels, axisTick: { show: false }, axisLine: { lineStyle: { color: ink } }, axisLabel: { color: ink, fontSize: 12, fontFamily: '"FD Kai", "Kaiti SC", serif' } },
              yAxis: { type: 'value', max: max, show: false },
              series: [{ type: 'bar', data: vals, barWidth: '56%', itemStyle: { borderRadius: [5, 5, 0, 0], color: function (p) { return p.dataIndex === n - 1 ? accHex : soft; } },
                label: { show: true, position: 'top', color: ink, fontSize: 13, fontFamily: '"FD Latin", "Times New Roman", serif', formatter: function (p) { return p.value > max * 0.005 ? Math.round(p.value) : ''; } } }] });
          } catch (e) { o.chart = null; this.P.noCharts = true; }
        }
        if (o.chart) { o.chart.setOption({ series: [{ data: vals }] }); return; }
      }
      // 没有 ECharts：用几根 CSS 柱子
      if (!host.firstChild) host.innerHTML = '<div class="chart-css">' + labels.map(function (lab, i) { return '<div><span data-v="' + i + '"></span><b data-b="' + i + '"></b><span>' + esc(lab) + '</span></div>'; }).join('') + '</div>';
      vals.forEach(function (v, i) {
        var bb = host.querySelector('[data-b="' + i + '"]'), s = host.querySelector('[data-v="' + i + '"]');
        if (bb) bb.style.height = (v / max * 7).toFixed(2) + 'cqw'; if (s) s.textContent = v > max * 0.005 ? Math.round(v) : '';
      });
    }
  };

  /* ---- 玻璃卡片上的一句原话或要点
   * 11-06 改：出处和标志合成卡片顶上一行（[标志] Anthropic 的说法 · 据 The Verge），出处里已经有公司名的，标志只放图形、不再重复名字
   *   （原来标志胶囊挂在出处行末尾，"Anthropic"出现两遍）；短句（中文 12 字、英文 34 个字母以内）字放大、卡片压矮，不再留大片空白；
   *   可带一张题图 image（左图右字）。 */
  function srcBadge(P, list, who) {
    var L = P.L, w = String(who || ''), low = w.toLowerCase(), marks = (list || []).map(function (r, i) {
      var k = r && r.k ? r.k : r, lg = (P.v.logos || {})[k]; if (!lg) return '';
      var nm = tx(lg.n, L), named = [lg.n && lg.n.zh, lg.n && lg.n.en, nm].some(function (x) { return x && low.indexOf(String(x).toLowerCase()) >= 0; });
      if (named && !lg.m) return '';                                  // 文字小签、出处里已有名字：不放
      var chip = logoChip(P, k, { sm: true, i: i });
      return named ? chip.replace(/<b>[^<]*<\/b>/, '') : chip;      // 出处里已有名字：只放图形
    }).join('');
    if (!marks && !w) return '';
    return '<div class="src">' + (marks ? '<span class="v3logos">' + marks + '</span>' : '') + (w ? '<span class="w">' + esc(w) + '</span>' : '') + '</div>';
  }
  function shortText(s, L) { s = String(s || ''); return L === 'en' ? s.length <= 34 : s.replace(/\s/g, '').length <= 12; }
  TPL.quote_card = {
    ext: [5, 5], panel: true,
    build: function (b) {
      var P = this.P, L = P.L, q = S2(b.text, L), src = b.img ? imgUrl(P, b.img) : null, sh = shortText(q, L);
      var cq = b.count === true ? countHtml(q) : null;        // 动效尝试：count: true 时第一个数字从 0 滚到终值
      b._.o.cq = cq && cq.v != null ? cq : null;
      var body = srcBadge(P, b.logos, S2(b.who, L)) + '<div class="hd v3quote">' + (b._.o.cq ? cq.html : esc(q)) + '</div>';
      if (b.shot) {                    // 结合式：原文截图放在图位（替代 image），卡片改成上图下字
        var sx = sbxHtml(P, b.shot);
        sbxCardBuild(this, b, 'quote_card', sx.html + '<div class="qt">' + body + '</div>', sx);
        return;
      }
      var inner = src ? '<div class="ph"><i style="background-image:url(&quot;' + src + '&quot;)"></i></div><div class="qt">' + body + '</div>' : body;
      var ov = !!b._.over && !src;        // 压在路尽头的配图上（11-06 晚补）：卡片稍宽、字小一号，四周露出配图
      var size = src ? [9.4, 4.2] : (ov ? [8.4, 2.7] : (sh ? [6.2, 2.1] : [7.0, 3.6]));
      panelBuild(this, b, inner, size, 'v3qc' + (sh ? ' short' : '') + (src ? ' img' : '') + (ov ? ' over' : ''));
      if (ov) {          // 压在路尽头的配图上（11-06 晚补）：镜头正对配图、装下整张图，卡片在图的下半截
        b._.shS = this.bshot(b, [0, 5.1, -0.9], 0, 4, 16.4, 9.4);
        b._.o.lb.shot = b._.shS;
      } else if (sh && !src) {        // 短句：卡片压矮、镜头退远一点，卡片不再撑满整个画面，四周露出地图
        b._.shS = this.bshot(b, [0, 3.9, 0], b._.fork ? (b._.branch ? 14 : -14) : 0, 3, size[0] * 1.45, size[1] * 1.6);
        b._.o.lb.shot = b._.shS;
      }
    },
    tl: function (b, a) {
      var o = b._.o, show = bt(b, 'show', b._.c.vs + 0.6); panelTl(b, a, show); o.show = show;
      if (b.logos) popLogos(a, o.lb.el, b.logos, show + 0.2);
      if (o.cq) this.counter(o.lb, 'span[data-c]', 0, o.cq.v, show + 0.15, CNT_DUR, o.cq.dec, o.cq.fin);
      var ph = o.lb.el.querySelector('.ph i');
      if (ph) { a.ST(ph, { scale: 1.12 }); a.tl.fromTo(ph, { scale: 1.12 }, { scale: 1, duration: Math.max(2, b._.c.end - show + 0.5), ease: 'none' }, show - 0.3); }
      if (o.sx) sbxCardTl(this, b, a, show);
    },
    cams: function (b) { return [{ t: b._.o.show + 0.4, s: b._.shS, dur: 1.4, ease: 'io', arc: 6 }]; },
    settle: function (b) { var o = b._.o; return o.done != null ? Math.max(o.show + 2.5, o.done + 1.0) : o.show + 2.5; },
    explore: function (b) { return [1, b._.shS]; }
  };

  /* ---- 帖子／节目卡：平台小标（图标＋名字）、日期、原话、署名（头像只用首字母或机构标志），可带一张题图 ----
   * 平台和日期由 video3_storyboard.check_posts 对过事件卡；核不上时 platform 是 {kind: 'quote'}（只标“原话”）、不写日期。
   * en_para：英文那句不是逐字原话（比如从中文转述），英文页面不加引号。 */
  var PF_ICON = {
    podcast: '<path d="M12 2.5a3.2 3.2 0 0 0-3.2 3.2v6.1a3.2 3.2 0 0 0 6.4 0V5.7A3.2 3.2 0 0 0 12 2.5zM5.6 11.4h1.9a4.5 4.5 0 0 0 9 0h1.9a6.4 6.4 0 0 1-5.45 6.33V20.5h3.1v1.9h-8.1v-1.9h3.1v-2.77A6.4 6.4 0 0 1 5.6 11.4z"/>',
    statement: '<path d="M4 9.2v5.6h3.2l6.3 4.2V5L7.2 9.2H4zm12.2-1.5 1.3-1.3A7.8 7.8 0 0 1 20 12a7.8 7.8 0 0 1-2.5 5.6l-1.3-1.3A6 6 0 0 0 18.1 12a6 6 0 0 0-1.9-4.3z"/>',
    document: '<path d="M6 2.5h8.2L19 7.3v14.2H6V2.5zm7.4 1.9v3.8h3.8M8.6 11h7.8v1.6H8.6zm0 3.4h7.8V16H8.6zm0 3.4h5.2v1.6H8.6z"/>',
    post: '<path d="M4 4.5h16v11.2H9.4L5.6 19.5v-3.8H4V4.5zm3.4 3.6v1.6h9.2V8.1H7.4zm0 3.2v1.6h6.2v-1.6H7.4z"/>',
    video: '<path d="M3 6.2h18v11.6H3V6.2zm7.2 2.9v5.8l5-2.9-5-2.9z"/>',
    quote: '<path d="M5 6h6v6.2c0 3.3-1.7 5.2-5 5.8v-2c1.6-.4 2.4-1.4 2.6-3H5V6zm8 0h6v6.2c0 3.3-1.7 5.2-5 5.8v-2c1.6-.4 2.4-1.4 2.6-3H13V6z"/>'
  };
  var PF_NAME = { podcast: { zh: '播客', en: 'Podcast' }, x: { zh: 'X', en: 'X' }, threads: { zh: 'Threads', en: 'Threads' }, youtube: { zh: 'YouTube', en: 'YouTube' },
    statement: { zh: '官方声明', en: 'Statement' }, document: { zh: '文件', en: 'Document' }, post: { zh: '帖子', en: 'Post' }, quote: { zh: '原话', en: 'Quote' } };
  TPL.post_card = {
    ext: [5.5, 5.5], panel: true,
    build: function (b) {
      var P = this.P, L = P.L, pf = b.platform || { kind: 'quote' }, kind = PF_NAME[pf.kind] ? pf.kind : 'quote';
      var logoPf = (kind === 'x' || kind === 'threads' || kind === 'youtube') && (P.v.logos || {})[kind];
      var ic = logoPf ? logoChip(P, kind, { sm: true }).replace('<b>', '<b hidden>') :
        '<i class="pi"><svg viewBox="0 0 24 24" aria-hidden="true">' + PF_ICON[kind === 'youtube' ? 'video' : (kind === 'x' || kind === 'threads' ? 'post' : kind)] + '</svg></i>';
      var pname = pf.name ? S2(pf.name, L) : tx(PF_NAME[kind], L);
      var who = b.who || {}, name = S2(who.name, L) || '', role = S2(who.role, L) || '';
      // 头像（11-06 改）：方形的图形标放进圆里；横长的字标（OpenAI、亚马逊……）改成横向胶囊，宽度跟着标志走，名字永远不被盖住
      //   （原来字标塞进 3.2 宽的圆，OpenAI 宽约 5.7，左右各溢出一截压住名字）；文字小签（没有图形）把名字放进胶囊
      var lgw = who.logo && (P.v.logos || {})[who.logo], fit = lgw ? avatarFit(lgw) : null;
      var av = !lgw ? '<span class="av">' + esc(who.mono || mono(name)) + '</span>'
        : (!lgw.m ? '<span class="av pill txt">' + esc(tx(lgw.n, L)) + '</span>'
          : '<span class="av lg' + (fit.pill ? ' pill' : '') + '" style="--mh:' + fit.h.toFixed(3) + '">' + logoChip(P, who.logo, { sm: true }).replace(/<b>[^<]*<\/b>/, '') + '</span>');
      var para = L === 'en' && b.en_para, q = S2(b.text, L);
      var sx = b.shot ? sbxHtml(P, b.shot) : null;                      // 结合式：原文截图放在图位（替代 image）
      var src = !sx && b.img ? imgUrl(P, b.img) : null;
      var inner = (sx ? sx.html : '') + (src ? '<div class="ph"><i style="background-image:url(&quot;' + src + '&quot;)"></i></div>' : '') +
        '<div class="pt"><span class="pf' + (kind === 'quote' ? ' n' : '') + '">' + ic + '<span>' + esc(pname) + '</span></span>' + (b.date ? '<span class="dt">' + esc(S2(b.date, L)) + '</span>' : '') + '</div>' +
        '<div class="q' + (para ? ' para' : '') + '">' + (para ? esc(q) : '“' + esc(q) + '”') + '</div>' +
        '<div class="by">' + av + '<span class="nm"><b>' + esc(name) + '</b>' + (role ? '<small>' + esc(role) + '</small>' : '') + '</span></div>';
      if (sx) sbxCardBuild(this, b, 'post_card', inner, sx);
      else panelBuild(this, b, inner, src ? [7.6, 6.0] : [7.6, 3.5], 'v3post' + (src ? ' img' : ''));
    },
    tl: function (b, a) {
      var o = b._.o, c = b._.c, show = bt(b, 'show', c.vs + 0.6), el = o.lb.el;
      panelTl(b, a, show); o.show = show;
      ['.pt', '.q', '.by'].forEach(function (sel, i) {
        var e = el.querySelector(sel); if (!e) return;
        a.ST(e, { autoAlpha: 0, y: 10 }); a.tl.fromTo(e, { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.5, ease: 'power2.out' }, show + 0.2 + i * 0.22);
      });
      var ph = el.querySelector('.ph i');
      if (ph) { a.ST(ph, { scale: 1.12 }); a.tl.fromTo(ph, { scale: 1.12 }, { scale: 1, duration: Math.max(2, c.end - show + 0.5), ease: 'none' }, show - 0.3); }
      if (o.sx) sbxCardTl(this, b, a, show);
    },
    cams: function (b) { return [{ t: b._.o.show + 0.4, s: b._.shS, dur: 1.4, ease: 'io', arc: 6 }]; },
    settle: function (b) { var o = b._.o; return o.done != null ? Math.max(o.show + 2.8, o.done + 1.0) : o.show + 2.8; },
    explore: function (b) { return [1, b._.shS]; }
  };

  /* ---- 刻度尺：几档（信用评级、等级），一条门槛线，一个标记从原来的档落到新的档 ---- */
  // 档位序号（11-06 白天补）：原来写成 (b.to || {}).at || 1，第 0 档（最上面那一档）被当成没写、退回第 1 档——
  // 只会往下落的评级（11-01 投资级 → BB）没露馅，往上升的（11-06 High → Critical）标记就原地不动
  function scAt(x, d) { return x && x.at != null && isFinite(+x.at) ? +x.at : d; }
  TPL.scale = {
    ext: [3.5, 8.5], bdx: 12,
    build: function (b) {
      var g = b._.g, pal = this.pal, L = this.P.L, o = b._.o, self = this;
      var bands = (b.bands || []).slice(0, 6), n = bands.length, H = 8.4, top = 9.4, bh = H / n, W = 2.6;
      var yAt = function (at) { return top - (clamp(+at || 0, 0, n - 1) + 0.5) * bh; };
      o.n = n; o.yAt = yAt; o.top = top;
      // open_top（11-06 白天补）：玻璃体不要顶面（方盒六个面里 +y 那面不画）、描边不画顶面四条棱，看着是一根没封顶的尺
      var bodyG = b.open_top ? new THREE.BoxGeometry(W, H, 0.9) : new THREE.RoundedBoxGeometry(W, H, 0.9, 4, 0.12); bodyG.translate(0, H / 2, 0);
      var bm = this.boxMat({ alpha: 0.18 });
      o.body = new THREE.Mesh(bodyG, b.open_top ? [bm, bm, new THREE.MeshBasicMaterial({ visible: false }), bm, bm, bm] : bm); o.body.position.y = top - H; g.add(o.body);
      if (b.open_top) this.outlineOpenTop(W, H, 0.9, o.body, H / 2); else this.outline(W, H, 0.9, o.body, H / 2);
      this.shadow(W * 2.4, 2.6, g, 0, 0, 1.0);
      var sh = b._.shA = this.bshot(b, [1.4, 5.9, 0], -6, 6, 15, 13.2, { pk: 0.95 });
      o.lines = [];
      for (var i = 1; i < n; i++) {
        var y = top - i * bh, isT = b.threshold != null && i === +b.threshold;
        var ln = this.tube([V3(-W / 2 - (isT ? 1.0 : 0.12), y, 0.5), V3(W / 2 + (isT ? 1.0 : 0.12), y, 0.5)], isT ? 0.07 : 0.02, this.flowMat(isT ? pal.acc : pal.ink, { glow: isT ? 1.9 : 0.6, head: 0 }), 20);
        g.add(ln); o.lines.push(ln); if (isT) o.thr = ln;
      }
      o.lBands = bands.map(function (bd, i) {
        return self.label('<div class="v3band"><div class="d">' + esc(S2(bd.label, L)) + '</div>' + (bd.sub ? '<div class="c">' + esc(S2(bd.sub, L)) + '</div>' : '') + '</div>',
          { obj: g, at: V3(W / 2 + 0.55, top - (i + 0.5) * bh, 0.45), shot: sh, align: 'l' });
      });
      if (b.threshold != null && b.threshold_label) o.lThr = this.label('<span class="v3tag acc">' + esc(S2(b.threshold_label, L)) + '</span>', { obj: g, at: V3(-W / 2 - 1.1, top - (+b.threshold) * bh, 0.5), shot: sh, align: 'r' });
      // 标记：一块发光的板，从原来的档落到新的档；原来的位置留一圈虚框
      var mg = new THREE.RoundedBoxGeometry(W + 0.5, 0.34, 1.3, 3, 0.1);
      o.mark = new THREE.Mesh(mg, this.coreMat(pal.acc, pal.dark ? 1.2 : 0.85)); o.mark.position.set(0, yAt(scAt(b.from, 0)), 0.1); g.add(o.mark);
      o.ghost = new THREE.Mesh(mg, this.boxMat({ alpha: 0.05, rimK: 0.6 })); o.ghost.position.copy(o.mark.position); g.add(o.ghost);
      this.outline(W + 0.54, 0.38, 1.34, o.ghost, 0, pal.dark ? 0.3 : 0.35);
      o.dust = this.burst(80, V3(0, yAt(scAt(b.to, 1)) - 0.2, 0.1), V3(W, 0.2, 1.2), { out: 1.8, up: 1.0, grav: 2.6, size: 2.6 }); g.add(o.dust);
      if (b.from && b.from.label) o.lFrom = this.label('<span class="v3plain">' + esc(S2(b.from.label, L)) + '</span>', { obj: g, at: V3(-W / 2 - 0.45, yAt(scAt(b.from, 0)), 0.5), shot: sh, align: 'r' });
      if (b.to && b.to.label) o.lTo = this.label('<div class="v3line">' + emph(S2(b.to.label, L), false, 'v3acc') + '</div>', { obj: g, at: V3(-W / 2 - 0.45, yAt(scAt(b.to, 1)), 0.5), shot: sh, align: 'r' });
      if (b.head) o.lHead = this.label('<div class="v3head v3glass"><div class="h">' + esc(S2(b.head, L)) + (b.head_logos ? '<span class="v3logos">' + logoList(this.P, b.head_logos, { sm: true }) + '</span>' : '') + '</div>' + (b.status ? '<div class="s">' + esc(S2(b.status, L)) + '</div>' : '') + '</div>', { obj: g, at: V3(1.6, top + 1.0, 0), shot: sh, align: 'b', keep: true });
      if (b.note) o.lNote = this.label('<span class="v3tag v3glass">' + esc(S2(b.note, L)) + '</span>', { obj: g, at: V3(W / 2 + 0.55, 1.2, 0.6), shot: sh, align: 'l', keep: true });
      // 被评级的那家公司的标志：贴在标记上，跟着它落下去
      if (b.logos) o.lMark = this.floatChip(logoList(this.P, b.logos), { obj: o.mark, at: V3(0, 0, 0.85), shot: sh, amp: 0.03 });
      b._.headAt = V3(1.6, top + 1.4, 0); b._.enterAt = V3(-W / 2, 1, 0); b._.exitAt = V3(W / 2 + 4, 1, 0);
    },
    tl: function (b, a) {
      var o = b._.o, c = b._.c, self = this, hd = bt(b, 'head', c.vs + 0.3), fr = bt(b, 'from', hd + 1.2), to = bt(b, 'to', fr + 2.0);
      var cs = b._.first ? c.start + 0.4 : hd - 1.0;
      a.ST(o.body.scale, { y: 0.001 }); a.tl.fromTo(o.body.scale, { y: 0.001 }, { y: 1, duration: 1.1, ease: 'power3.out' }, cs);
      o.lines.forEach(function (m, i) { a.ST(m.material.uniforms.uReveal, { value: 0 }); a.U(m.material.uniforms.uReveal, 0, 1, cs + 0.6 + i * 0.12, 0.6); });
      if (o.lHead) a.show(o.lHead, hd - 0.1);
      o.lBands.forEach(function (lb, i) { a.show(lb, hd + 0.2 + i * 0.25); });
      if (o.lThr) a.show(o.lThr, hd + 0.6);
      var y0 = o.yAt(scAt(b.from, 0)), y1 = o.yAt(scAt(b.to, 1));
      a.ST(o.mark.scale, { x: 0.001, y: 0.001, z: 0.001 }); a.ST(o.mark.position, { y: y0 });
      a.tl.fromTo(o.mark.scale, { x: 0.001, y: 0.001, z: 0.001 }, { x: 1, y: 1, z: 1, duration: 0.6, ease: 'back.out(1.6)' }, fr - 0.3);
      a.ST(o.ghost.material.uniforms.uFade, { value: 0 });
      if (o.lFrom) a.show(o.lFrom, fr - 0.1);
      a.tl.fromTo(o.mark.position, { y: y0 }, { y: y1 - 0.12, duration: 0.5, ease: 'power3.in' }, to - 0.3);
      a.tl.fromTo(o.mark.position, { y: y1 - 0.12 }, { y: y1, duration: 0.5, ease: 'back.out(3)' }, to + 0.2);
      a.U(o.ghost.material.uniforms.uFade, 0, 1, to - 0.25, 0.4);
      a.U(o.dust.material.uniforms.uT, 0, 1, to + 0.15, 1.4, 'none');
      if (o.lFrom) a.tl.fromTo(o.lFrom, { a: 1 }, { a: 0.45, duration: 0.4 }, to - 0.2);
      if (o.lTo) a.show(o.lTo, to + 0.2);
      if (o.thr) { a.tl.fromTo(o.thr.material.uniforms.uFade, { value: 1 }, { value: 1.8, duration: 0.3 }, to - 0.1); a.tl.fromTo(o.thr.material.uniforms.uFade, { value: 1.8 }, { value: 1, duration: 0.8 }, to + 0.3); }
      var nt = bt(b, 'note', null); if (o.lNote) a.show(o.lNote, (nt != null ? nt : to + 1.5) - 0.2);
      var endT = b._.nextT != null ? b._.nextT - 0.2 : c.end + 0.3;
      [o.lHead, o.lFrom, o.lTo, o.lThr, o.lNote].concat(o.lBands).forEach(function (lb) { if (lb) a.hide(lb, endT, 0.4); });
      if (o.lHead && b.head_logos) popLogos(a, o.lHead.el, b.head_logos, hd);
      if (o.lMark) this.showChips(a, o.lMark, b.logos, fr + 0.1, endT);
      // 章末收起（不挡后面几章的镜头）
      [o.body, o.mark, o.ghost].forEach(function (m) { a.tl.fromTo(m.scale, { y: 1 }, { y: 0.001, duration: 0.8, ease: 'power2.in' }, c.end + 0.4); });
      o.lines.forEach(function (m) { a.U(m.material.uniforms.uFade, 1, 0, c.end + 0.3, 0.6); });
      o.hd = hd; o.to = to; o.settle = Math.max(to, nt || 0) + 1.2;
    },
    cams: function (b) { return [{ t: b._.o.hd - 0.15, s: b._.shA, dur: 1.3, ease: 'io', arc: 8 }]; },
    settle: function (b) { return b._.o.settle; },
    explore: function (b) { return [2, b._.shA]; }
  };

  /* ---- 2–4 根玻璃柱按数值长高（谁比谁多）；重点那根带发光的芯
   * 11-06 改：玻璃收窄、贴着实心柱（原来 2.2 对 1.3，斜着看前后两个框错开）；描边只描正面；玻璃和芯一起在说到这个数时长出来
   * （原来标题一出就先立起到最终高度的空框，等于先露了答案）；标题旁的 head_logos 补画（原来检查算它"有标志"，画面上没有）。 */
  var COL_GLASS = 1.62, COL_CORE = 1.3;
  TPL.column_compare = {
    ext: [5, 7],
    build: function (b) {
      var g = b._.g, pal = this.pal, L = this.P.L, o = b._.o, self = this;
      var items = (b.items || []).slice(0, 4), n = items.length, sp = 3.6, H = 7.6;
      var max = Math.max.apply(null, items.map(function (it) { return Math.abs(+it.value || 0); }).concat([1e-6]));
      o.items = items; o.cols = [];
      var xs = items.map(function (it, i) { return (i - (n - 1) / 2) * sp; });
      // 标志小签：第一根柱子的在左边、最后一根的在右边竖着排；中间的柱子（3–4 根时）放进柱顶那张字里
      var sideOf = function (i) { return i === 0 ? -1 : (i === n - 1 ? 1 : 0); };
      var hasL = !!(items[0] && items[0].logos && items[0].logos.length), hasR = n > 1 && !!(items[n - 1].logos && items[n - 1].logos.length);
      var cw = 4.2, cx = ((hasR ? cw : 0) - (hasL ? cw : 0)) / 2;
      var sh = b._.shA = this.bshot(b, [cx, 5.8, 0], -4, 8, (n - 1) * sp + 9 + (hasL ? cw : 0) + (hasR ? cw : 0), 15, { pk: 0.95 });
      o.chips = [];
      items.forEach(function (it, i) {
        var h = Math.max(0.2, Math.abs(+it.value || 0) / max * H), x = xs[i], hi = !!it.hi;
        var cg = new THREE.RoundedBoxGeometry(COL_GLASS, h, COL_GLASS, 4, 0.12); cg.translate(0, h / 2, 0);
        var col = new THREE.Mesh(cg, self.boxMat({ alpha: hi ? 0.16 : 0.22 })); col.position.set(x, 0, 0); g.add(col);
        self.outlineFront(COL_GLASS, h, COL_GLASS, col, h / 2);
        var core = null;
        if (hi) { var kg = new THREE.RoundedBoxGeometry(COL_CORE, h, COL_CORE, 3, 0.1); kg.translate(0, h / 2, 0); core = new THREE.Mesh(kg, self.coreMat(pal.acc)); core.position.set(x, 0, 0); g.add(core); }
        else { var kg2 = new THREE.RoundedBoxGeometry(COL_CORE, h, COL_CORE, 3, 0.1); kg2.translate(0, h / 2, 0); core = new THREE.Mesh(kg2, self.coreMat(pal.glass.clone().lerp(pal.ink, 0.25), 0.3)); core.position.set(x, 0, 0); g.add(core); }
        var shd = self.shadow(2.7, 2.7, g, x, 0, 0.9);
        var dec = (String(it.value).split('.')[1] || '').length;
        // 柱顶一张字：名字、数值（滚动）、小字说明；不放在柱脚（会被字幕压住）
        var side = sideOf(i), lgs = it.logos || [];
        var ln = self.label('<div class="v3val v3colv"><div class="c v3t">' + esc(S2(it.name, L)) + '</div>' + (it.label ? '<div class="v3line">' + emph(S2(it.label, L), true, hi ? 'v3acc' : '') + '</div>' : '') +
          (it.sub ? '<div class="c">' + esc(S2(it.sub, L)) + '</div>' : '') + (lgs.length && !side ? '<div class="v3logos">' + logoList(self.P, lgs, { sm: true }) + '</div>' : '') + '</div>', { obj: g, at: V3(x, h + 0.35, 0), shot: sh, align: 'b' });
        if (lgs.length && side) {
          var stp = Math.min(0.82, (h - 0.7) / lgs.length);
          lgs.forEach(function (r, j) {
            o.chips.push({ i: i, j: j, r: r, lb: self.floatChip(logoChip(self.P, r.k, { sm: true, hi: hi, i: 0 }), { obj: g, at: V3(x + side * 1.5, h - 0.5 - j * stp, 0.4), shot: sh, align: side < 0 ? 'r' : 'l', amp: 0.05 }) });
          });
        }
        var lv = it.label ? ln : null;
        o.cols.push({ col: col, core: core, shd: shd, h: h, lv: lv, ln: ln, v: +it.value || 0, dec: dec });
      });
      if (b.head) o.lHead = this.label('<div class="v3head v3glass"><div class="h">' + esc(S2(b.head, L)) + (b.head_logos ? '<span class="v3logos">' + logoList(this.P, b.head_logos, { sm: true }) + '</span>' : '') + '</div>' + (b.status ? '<div class="s">' + esc(S2(b.status, L)) + '</div>' : '') + '</div>', { obj: g, at: V3(0, H + 3.4, 0), shot: sh, align: 'b', keep: true });
      if (b.note) o.lNote = this.label('<span class="v3tag acc big">' + esc(S2(b.note, L)) + '</span>', hasR ? { obj: g, at: V3(xs[n - 1] + 1.7, o.cols[n - 1].h + 0.75, 0.6), shot: sh, align: 'l' } : { obj: g, at: V3(xs[n - 1] + 1.4, H * 0.55, 0.6), shot: sh, align: 'l' });
      b._.headAt = V3(0, H + 3.8, 0); b._.enterAt = V3(xs[0] - 1.1, 1, 0); b._.exitAt = V3(xs[n - 1] + 1.1, 1, 0);
    },
    tl: function (b, a) {
      var o = b._.o, c = b._.c, self = this, hd = bt(b, 'head', c.vs + 0.3), n = o.cols.length;
      var ts = listT(b, 'items', n, hd + 1.0, 1.5);
      if (o.lHead) a.show(o.lHead, hd - 0.1);
      o.cols.forEach(function (q, i) {
        // 玻璃和芯一起在旁白说到这个数时长满（11-06：不再在标题一出就先立起空玻璃框）；数字滚动和柱子长出同样 1.2 秒
        if (FX) {     // 11-08（K45）：柱子长出来之前 x、z 也是 0（不留白底座），影子跟着长
          a.ST(q.col.scale, { x: 0.001, y: 0.001, z: 0.001 }); a.tl.set(q.col.scale, { x: 1, z: 1 }, ts[i] - 0.2); a.tl.fromTo(q.col.scale, { y: 0.001 }, { y: 1, duration: 1.2, ease: 'power3.out' }, ts[i] - 0.2);
          if (q.core) { a.ST(q.core.scale, { x: 0.001, y: 0.001, z: 0.001 }); a.tl.set(q.core.scale, { x: 1, z: 1 }, ts[i] - 0.2); a.tl.fromTo(q.core.scale, { y: 0.001 }, { y: 1, duration: 1.2, ease: 'power3.out' }, ts[i] - 0.2); }
        } else {
          a.ST(q.col.scale, { y: 0.001 }); a.tl.fromTo(q.col.scale, { y: 0.001 }, { y: 1, duration: 1.2, ease: 'power3.out' }, ts[i] - 0.2);
          if (q.core) { a.ST(q.core.scale, { y: 0.001 }); a.tl.fromTo(q.core.scale, { y: 0.001 }, { y: 1, duration: 1.2, ease: 'power3.out' }, ts[i] - 0.2); }
        }
        if (FX && q.shd) { a.ST(q.shd.scale, { x: 0.001, y: 0.001 }); a.tl.fromTo(q.shd.scale, { x: 0.001, y: 0.001 }, { x: 1, y: 1, duration: 1.0, ease: 'power2.out' }, ts[i] - 0.2); }
        a.show(q.ln, ts[i] - 0.1);
        if (q.lv) self.counter(q.lv, 'span[data-c]', 0, Math.abs(q.v), ts[i] - 0.1, 1.2, q.dec);
      });
      var nt = bt(b, 'note', ts[n - 1] + 1.4);
      if (o.lNote) a.show(o.lNote, nt - 0.2);
      var endT = b._.nextT != null ? b._.nextT - 0.2 : c.end + 0.3;
      [o.lHead, o.lNote].concat(o.cols.map(function (q) { return q.ln; })).forEach(function (lb) { if (lb) a.hide(lb, endT, 0.4); });
      o.cols.forEach(function (q, i) { var it = o.items[i]; if (it.logos && q.ln) popLogos(a, q.ln.el, it.logos, ts[i] + 0.2); });
      if (o.lHead && b.head_logos) popLogos(a, o.lHead.el, b.head_logos, hd);
      // 柱子旁的标志：说到这家公司时（有触发词）或柱子长满时依次弹出
      o.chips.forEach(function (ch) {
        var at = typeof ch.r.t === 'number' ? Math.max(ch.r.t, ts[ch.i] - 0.2) : ts[ch.i] + 0.3 + ch.j * 0.16;
        a.show(ch.lb, at, 0.35);
        var e = ch.lb.inEl.querySelector('.v3logo'); if (e) { a.ST(e, { scale: 0.6 }); a.tl.fromTo(e, { scale: 0.6 }, { scale: 1, duration: 0.45, ease: 'back.out(2.4)' }, at); }
        a.hide(ch.lb, endT, 0.35);
      });
      o.cols.forEach(function (q) { [q.col, q.core].forEach(function (m) { if (m) { a.tl.fromTo(m.scale, { y: 1 }, { y: 0.001, duration: 0.8, ease: 'power2.in' }, c.end + 0.4); if (FX) a.tl.set(m.scale, { x: 0.001, z: 0.001 }, c.end + 1.25); } }); });
      o.hd = hd; o.settle = Math.max(ts[n - 1], o.lNote ? nt : 0) + 1.4;
    },
    cams: function (b) { return [{ t: b._.o.hd - 0.15, s: b._.shA, dur: 1.3, ease: 'io', arc: 8 }]; },
    settle: function (b) { return b._.o.settle; },
    explore: function (b) { return [2, b._.shA]; }
  };

  /* ---- 计数（11-06 加）：美国本土轮廓＋大字"N 个州"＋M 格方阵；说到"除了几项"时 M−k 格亮、k 格灰
   * 轮廓、州界来自 site/v3/us_states.json（us-atlas，Albers USA 投影），组装时只把用得到的几何编进这一块的 geo。
   * 只点亮分镜点了名、又在事件卡原文里逐字找到的州（video3_storyboard.check_tally 核）；没点名就只画轮廓，不落到任何一个州。
   * 颜色中性：点亮用字色，例外用灰，不用红蓝（不带党派色）。没有 geo（数据读不到）时退成大字＋方阵。 */
  TPL.tally = {
    ext: [9, 9],
    startT: function (b) { return bt(b, 'head', bt(b, 'show', firstT(b))); },
    build: function (b) {
      var g = b._.g, pal = this.pal, L = this.P.L, Z = b._.o, geo = b.geo || null;
      var PW = 17, PH = 9.4, M = Math.max(1, Math.min(120, Math.round(+(b.count || {}).value || 1))), K = Math.max(0, Math.min(M - 1, Math.round(+(b.except || {}).value || 0)));
      Z.M = M; Z.K = K;
      Z.panel = new THREE.Mesh(new THREE.PlaneGeometry(PW, PH), this.panelMat(PW, PH, { radius: 0.6, alpha: pal.dark ? 0.42 : 0.55, edgeGlow: 0.9 }));
      Z.panel.position.set(0, 5.4, 0); Z.panel.material.uniforms.uFade.value = 0; g.add(Z.panel); this.glass.push(Z.panel);
      b._.shA = this.bshot(b, [0, 5.4, 0], 0, 4, PW * 1.16, PH * 1.2, { pk: 1 });   // 竖屏也装下整张卡（不裁两边）
      var cols = M <= 10 ? M : (M <= 24 ? 6 : (M <= 49 ? 7 : (M <= 80 ? 10 : 12)));
      var cells = ''; for (var i = 0; i < M; i++) cells += '<i data-k="' + i + '"></i>';
      var map = '';
      if (geo && geo.outline) {
        var vb = (geo.vb || [0, 0, 975, 610]).join(' ');
        map = '<div class="map"><svg viewBox="' + esc(vb) + '" aria-hidden="true" preserveAspectRatio="xMidYMid meet">' +
          '<path class="fill" d="' + esc(geo.outline) + '"/>' + (geo.borders ? '<path class="bd" d="' + esc(geo.borders) + '"/>' : '') +
          (geo.lit || []).map(function (s0, i) { return '<path class="lit" data-s="' + i + '" d="' + esc(s0.d) + '"/>'; }).join('') +
          '<path class="ln" pathLength="1" d="' + esc(geo.outline) + '"/></svg></div>';
      }
      var lit = (geo && geo.lit) || [], rg = S2(b.region, L) || '';
      // 点亮的州名写在轮廓下面一行；大字里已经写了这几个州就不重复
      var sn = lit.map(function (s0) { return tx(s0.n, L); }).filter(function (x) { return x && rg.indexOf(x) < 0; }).join(L === 'en' ? ', ' : '、');
      var html = '<div class="v3tally' + (map ? '' : ' nomap') + '">' + (b.head ? '<div class="hd">' + esc(S2(b.head, L)) + '</div>' : '') +
        '<div class="bd2"><div class="mp">' + map + (rg ? '<div class="rg' + (rg.replace(/\s/g, '').length > (L === 'en' ? 14 : 7) ? ' long' : '') + '" data-p="rg">' + emph(rg) + '</div>' : '') +
        (sn ? '<div class="sn" data-p="sn">' + esc(sn) + '</div>' : '') + '</div>' +
        '<div class="gw"><div class="cl" data-p="cl">' + emph(S2((b.count || {}).label, L), true) + '</div>' +
        '<div class="grid" style="--cols:' + cols + '">' + cells + '</div>' +
        '<div class="lgd">' + (b.lit ? '<span data-p="lo"><i class="k on"></i>' + esc(S2(b.lit, L)) + '</span>' : '') +
        (K && (b.except || {}).label ? '<span data-p="lx"><i class="k ex"></i>' + esc(S2(b.except.label, L)) + '</span>' : '') + '</div></div></div>' +
        (b.note ? '<div class="ft">' + esc(S2(b.note, L)) + '</div>' : '') + '</div>';
      Z.lb = this.label(html, { obj: Z.panel, at: V3(0, 0, 0.05), shot: b._.shA, min: 0.3, max: 1.6, fitW: PW * 0.94, fitH: PH * 0.92 });
      var root = Z.lb.el;
      Z.cells = root.querySelectorAll('.grid i'); Z.ln = root.querySelector('path.ln'); Z.fill = root.querySelector('path.fill');
      Z.bd = root.querySelector('path.bd'); Z.lits = root.querySelectorAll('path.lit');
      this.shadow(PW * 1.1, 4, g, 0, 0.6, 0.9);
      b._.enterAt = V3(-PW / 2, 1, 0); b._.exitAt = V3(PW / 2 - 2, 1, 0); b._.headAt = V3(0, 10.4, 0);
    },
    tl: function (b, a) {
      var Z = b._.o, c = b._.c, hd = bt(b, 'head', null), show = bt(b, 'show', hd != null ? hd + 0.6 : c.vs + 0.6);
      var cnt = bt(b, 'count', show + 1.2), ex = Z.K ? bt(b, 'except', cnt + 1.6) : cnt + 0.9, st = bt(b, 'states', show + 0.9);
      var t0 = Math.min(show, hd != null ? hd : show);
      a.ST(Z.panel.material.uniforms.uFade, { value: 0 }); a.U(Z.panel.material.uniforms.uFade, 0, 1, t0 - 0.5, 0.8);
      a.show(Z.lb, t0 - 0.3, 0.5);
      var el = Z.lb.el, pop = function (sel, at) { var e = el.querySelector(sel); if (!e) return; a.ST(e, { autoAlpha: 0, y: 8 }); a.tl.fromTo(e, { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.5, ease: 'power3.out' }, at); };
      pop('[data-p="rg"]', show + 0.3); pop('[data-p="cl"]', cnt - 0.1); pop('[data-p="lo"]', ex + 0.2); pop('[data-p="lx"]', ex + 0.35); pop('[data-p="sn"]', st + 0.4);
      this.counter(Z.lb, 'span[data-c]', 0, Z.M, cnt - 0.1, 1.0, 0);
      var endT = b._.nextT != null ? b._.nextT - 0.2 : c.end + 0.3;
      a.hide(Z.lb, endT, 0.5); a.U(Z.panel.material.uniforms.uFade, 1, 0, endT, 0.8, 'power1.in');
      Z.k = { show: show, cnt: cnt, ex: ex, st: st };
      Z.t0 = t0; Z.settle = Math.max(ex, cnt, (Z.lits.length ? st : 0)) + 1.4;
    },
    cams: function (b) { return [{ t: b._.o.t0 + 0.2, s: b._.shA, dur: 1.3, ease: 'io', arc: 4 }]; },
    settle: function (b) { return b._.o.settle; },
    explore: function (b) { return [2, b._.shA]; },
    frame: function (b, t) {
      var Z = b._.o, k = Z.k; if (!k || Z.lb.a <= 0.003) return;
      var draw = sat((t - k.show + 0.2) / 1.4), key = [Math.round(draw * 100), t >= k.cnt - 0.2, t >= k.ex, t >= k.st].join(',');
      // 只在画面状态变了的时候写 DOM（格子一格一格冒出来那一秒按时间算）
      var grow = t >= k.cnt - 0.2 && t < k.cnt + 1.4;
      if (key === Z._key && !grow) return;
      Z._key = key;
      if (Z.ln) { Z.ln.style.strokeDashoffset = (1 - out3(draw)).toFixed(3); }
      if (Z.fill) Z.fill.style.opacity = (sat((t - k.show - 0.3) / 0.9) * 1).toFixed(3);
      if (Z.bd) Z.bd.style.opacity = (sat((t - k.show - 0.6) / 0.9) * 1).toFixed(3);
      for (var j = 0; j < Z.lits.length; j++) Z.lits[j].style.opacity = sat((t - k.st - j * 0.12) / 0.5).toFixed(3);
      var M = Z.M, K = Z.K;
      for (var i = 0; i < Z.cells.length; i++) {
        var u = sat((t - k.cnt + 0.2 - i * (1.0 / Math.max(1, M))) / 0.35), cl = '';
        if (t >= k.ex) cl = i < M - K ? 'on' : 'ex';
        var e = Z.cells[i], tr = 'scale(' + (0.4 + 0.6 * out3(u)).toFixed(3) + ')', op = u.toFixed(2);
        if (e._tr !== tr) { e.style.transform = tr; e._tr = tr; }
        if (e._op !== op) { e.style.opacity = op; e._op = op; }      // 透明度单独记：缩放先到 1，透明度还差一点时也要写进去
        if (e._cl !== cl) { e.className = cl; e._cl = cl; }
      }
    }
  };

  /* ---- 一排 2–5 块玻璃小卡（几个例子、几种说法），按旁白一块块立起来；竖屏时两列排 ---- */
  TPL.tile_row = {
    ext: [6, 6], extPhoto: [11, 11],
    build: function (b) {
      var g = b._.g, pal = this.pal, L = this.P.L, o = b._.o, self = this;
      var items = (b.items || []).slice(0, 5), n = items.length, P = this.P;
      // 有配图的小卡：上半截是图（写实场景），下半截是字，卡片高一些
      var hasImg = items.some(function (it) { return it.img && imgUrl(P, it.img); });
      var ovp = ovpOn(P, b);              // 11-07：压在配图上（分镜写了 photo）：小卡大一些，后面立一张配图
      var TW = ovp ? 4.6 : 4.0, TH = hasImg ? 3.9 : (ovp ? 3.1 : 2.7), sp = ovp ? 5.2 : 4.6, rg = TH + 0.5, y0 = TH / 2 + (ovp ? 1.55 : 0.65);   // 压在配图上：小卡抬高，不压字幕
      var portrait = this.P.sw < this.P.sh, cols = portrait && n > 2 ? 2 : n, rows = Math.ceil(n / cols);
      var pos = items.map(function (it, i) {
        var r = Math.floor(i / cols), k = i % cols, m = Math.min(cols, n - r * cols);
        var x = (k - (m - 1) / 2) * sp, z = cols === n ? -0.45 * Math.pow(k - (m - 1) / 2, 2) : 0;
        return V3(x, y0 + (rows - 1 - r) * rg, z);
      });
      var topY = y0 + (rows - 1) * rg + TH / 2, fw = (cols - 1) * sp + TW + 1.6, fh = (topY + 1.5) - 0.4 + 0.8;
      var sh = b._.shA = this.bshot(b, [0, (topY + 1.5 + 0.4) / 2, 0], 0, 6, fw, fh, { pk: 1 });
      if (ovp) sh = b._.shA = ovpBuild(this, b, 0, fw + 4.2);
      o.tiles = items.map(function (it, i) {
        var p = new THREE.Mesh(new THREE.PlaneGeometry(TW, TH), self.panelMat(TW, TH, { radius: 0.36, alpha: pal.dark ? 0.42 : 0.55, edgeGlow: 0.9 }));
        p.position.copy(pos[i]); p.rotation.y = cols === n ? -pos[i].x * 0.035 : 0; p.material.uniforms.uFade.value = 0; g.add(p); self.glass.push(p);
        var live = it.kind !== 'proto', src = it.img ? imgUrl(P, it.img) : null;
        var txt = '<div class="hd">' + esc(S2(it.title, L)) + '</div>' + (it.sub ? '<div class="sb">' + esc(S2(it.sub, L)) + '</div>' : '') +
          (it.tag ? '<span class="v3tag ' + (it.kind === 'plain' ? 'v3glass' : (live ? 'acc' : 'warn')) + '" data-tag="1">' + esc(S2(it.tag, L)) + '</span>' : '');
        var lb = self.label('<div class="v3card v3glass v3tc' + (hasImg ? ' img' : '') + (ovp ? ' ovp' : '') + '">' + (hasImg ? '<div class="ph">' + (src ? '<i style="background-image:url(&quot;' + src + '&quot;)"></i>' : '') + '</div><div class="tx">' + txt + '</div>' : txt) + '</div>',
          { obj: p, at: V3(0, 0, 0.05), shot: sh, fitW: TW * 0.94, fitH: TH * 0.9, tight: true });
        // 这块卡上的标志：一排小签骑在卡片左上沿
        var chips = it.logos && it.logos.length ? self.floatChip(logoList(P, it.logos, { sm: true }), { obj: p, at: V3(-TW * 0.47 + 0.15, TH * 0.45 - 0.05, 0.35), shot: sh, align: 'bl', amp: 0.04 }) : null;
        return { p: p, lb: lb, y: pos[i].y, chips: chips, logos: it.logos };
      });
      if (b.head) o.lHead = this.label('<div class="v3head v3glass"><div class="h">' + esc(S2(b.head, L)) + (b.head_logos ? '<span class="v3logos">' + logoList(P, b.head_logos, { sm: true }) + '</span>' : '') + '</div>' + (b.status ? '<div class="s">' + esc(S2(b.status, L)) + '</div>' : '') + '</div>', { obj: g, at: V3(0, topY + 0.3, 0), shot: sh, align: 'b', keep: true });
      this.shadow(fw, 3, g, 0, 0, 0.7);
      b._.headAt = V3(0, topY + 0.8, 0); b._.enterAt = V3(-fw / 2, 1, 0); b._.exitAt = V3(fw / 2, 1, 0);
    },
    tl: function (b, a) {
      var o = b._.o, c = b._.c, n = o.tiles.length, it0 = bt(b, 'items0', null), hd = bt(b, 'head', it0 != null ? it0 - 0.8 : c.vs + 0.3);
      var ts = listT(b, 'items', n, hd + 0.8, 1.6);
      if (o.lHead) a.show(o.lHead, hd - 0.1);
      o.tiles.forEach(function (q, i) {
        a.ST(q.p.material.uniforms.uFade, { value: 0 }); a.ST(q.p.position, { y: q.y - 0.9 });
        a.U(q.p.material.uniforms.uFade, 0, 1, ts[i] - 0.35, 0.6);
        a.tl.fromTo(q.p.position, { y: q.y - 0.9 }, { y: q.y, duration: 0.7, ease: 'power3.out' }, ts[i] - 0.35);
        a.show(q.lb, ts[i] - 0.1, 0.5);
        var tag = q.lb.el.querySelector('[data-tag]');
        if (tag) { a.ST(tag, { autoAlpha: 0, scale: 0.7 }); a.tl.fromTo(tag, { autoAlpha: 0, scale: 0.7 }, { autoAlpha: 1, scale: 1, duration: 0.45, ease: 'back.out(2.2)' }, ts[i] + 0.35); }
      });
      var endT = b._.nextT != null ? b._.nextT - 0.2 : c.end + 0.3, self = this;
      o.tiles.forEach(function (q) { a.hide(q.lb, endT, 0.4); a.U(q.p.material.uniforms.uFade, 1, 0, endT, 0.6, 'power1.in'); });
      if (o.lHead) a.hide(o.lHead, endT, 0.4);
      if (o.lHead && b.head_logos) popLogos(a, o.lHead.el, b.head_logos, hd);
      o.tiles.forEach(function (q, i) {
        var ph = q.lb.el.querySelector('.ph i');      // 配图慢慢推近一点（按时间轴，不按墙钟）
        if (ph) { a.ST(ph, { scale: 1.12 }); a.tl.fromTo(ph, { scale: 1.12 }, { scale: 1, duration: Math.max(2, endT - ts[i] + 0.8), ease: 'none' }, ts[i] - 0.4); }
        if (q.chips) self.showChips(a, q.chips, q.logos, ts[i] + 0.25, endT);
      });
      if (o.ovp) ovpTl(b, a, bt(b, 'photo', Math.min(hd, ts[0]) - 0.3), endT);
      o.hd = hd; o.first = ts[0]; o.settle = ts[n - 1] + 1.4;
    },
    cams: function (b) { var o = b._.o, t = Math.min(o.hd, o.first - 0.4) - 0.15; if (o.ovpT != null) t = Math.min(t, o.ovpT + 0.4); return [{ t: t, s: b._.shA, dur: 1.3, ease: 'io', arc: 6 }]; },
    settle: function (b) { return b._.o.settle; },
    explore: function (b) { return [2, b._.shA]; }
  };

  /* ---- 国内外：地图沿中缝对折，卡片从各自那一片飞到两边 ----
   * 11-06 晚补：两边的小卡可带一张题图 image（卡片上半截，和时间轴小图同样从网页图或视频图里备；没写就和原来一样只有字）；
   *   两边标题的 logos 原来就能挂（标题在 left/right 触发词出现）。 */
  TPL.split = {
    build: function (b) {
      var self = this, L = this.P.L, C = b._.o, sh = this.shots.conA, A = this.areas;
      var src = function (id) { var a = A[id]; return a ? V3(a.pos[0], 3, a.pos[2]) : V3(CPOS[0], 3, CPOS[2]); };
      var lt = (b.left || {}), rt = (b.right || {});
      var P = this.P, sideLg = function (x) { return x.logos ? '<span class="v3logos">' + logoList(P, x.logos, { sm: true }) + '</span>' : ''; };
      C.hIntl = this.label('<div class="v3side">' + esc(S2(lt.head, L) || (L === 'en' ? 'World' : '国外')) + (lt.tag ? '<small>' + esc(S2(lt.tag, L)) + '</small>' : '') + sideLg(lt) + '</div>', { obj: this.left, at: V3(-15, 7, -16), shot: sh, align: 'b', keep: true });
      C.hCn = this.label('<div class="v3side">' + esc(S2(rt.head, L) || (L === 'en' ? 'China' : '国内')) + (rt.tag ? '<small>' + esc(S2(rt.tag, L)) + '</small>' : '') + sideLg(rt) + '</div>', { obj: this.right, at: V3(22, 7, -16), shot: sh, align: 'b', keep: true });
      var li = (b.left_items || []).slice(0, 4), ri = (b.right_items || []).slice(0, 4);
      var gapL = li.length >= 4 ? 6.2 : 7.4, gapR = ri.length >= 4 ? 6.2 : 7.4;
      var tile = function (it) {        // 小卡：可带题图（11-06 晚补），图在上、字在下
        var ph = it.img ? imgUrl(P, it.img) : null;
        return '<div class="v3tile v3glass' + (ph ? ' img' : '') + '">' + (ph ? '<div class="ph"><i style="background-image:url(&quot;' + ph + '&quot;)"></i></div>' : '') +
          sideLg(it) + esc(S2(it.text, L)) + (it.sub ? '<small>' + esc(S2(it.sub, L)) + '</small>' : '') + '</div>';
      };
      // 带图的小卡高一截：改成从锚点往下长（锚点是卡片上沿），上沿不压两边标题下面的标志；横屏、竖屏都一样
      //   （只有一两张卡时；卡多了间距本来就紧，不挪；video3.css 里竖屏的带图小卡也收窄、图压扁一点）
      var imgL = li.length <= 2 && li.some(function (it) { return it.img; }), imgR = ri.length <= 2 && ri.some(function (it) { return it.img; });
      var yL = imgL ? 4.6 : 4, yR = imgR ? 4.6 : 4;
      C.tl = li.map(function (it, i) {
        return { lb: self.label(tile(it), { at: V3(-15, yL, -9.5 + i * gapL), shot: sh, align: imgL ? 't' : '' }),
          to: V3(-15, yL, -9.5 + i * gapL), from: src(it.from), side: -1, logos: it.logos };
      });
      C.tr = ri.map(function (it, i) {
        return { lb: self.label(tile(it), { at: V3(22, yR, -9.5 + i * gapR), shot: sh, align: imgR ? 't' : '' }),
          to: V3(22, yR, -9.5 + i * gapR), from: src(it.from), side: 1, logos: it.logos };
      });
      C.seamGlow = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 84), new THREE.MeshBasicMaterial({ map: this.glowTex, color: this.pal.acc.clone().multiplyScalar(this.pal.dark ? 2.2 : 0.85), transparent: true, opacity: 0, depthWrite: false,
        blending: this.pal.dark ? THREE.AdditiveBlending : THREE.NormalBlending }));
      C.seamGlow.rotation.x = -Math.PI / 2; C.seamGlow.position.set(SEAM, 0.05, MAPC[2]); C.seamGlow.renderOrder = 2; this.scene.add(C.seamGlow);
      b._.shA = sh; b._.enterAt = V3(0, 1, 0); b._.exitAt = V3(0, 1, 0); b._.headAt = V3(0, 6, 0);
    },
    tl: function (b, a) {
      var C = b._.o, c = b._.c, self = this, c0 = bt(b, 'split', c.vs + 0.1), lf = bt(b, 'left', c0 + 1.2), rg = bt(b, 'right', lf + 2.0);
      // 两边的标题不早于地图对折：触发词落在对折之前（11-04"国内"对到了开头的"国内外"，65.2 秒；11-03 开头就说"国外和国内"），
      // 标题会在镜头还在飞的时候出来，11-04 那次贴在画面最上沿、切掉一半。这时跟着对折出来：对折开始 0.6 秒后，国外先、国内隔 0.4 秒
      if (lf < c0) lf = c0 + 0.6;
      if (rg < c0) rg = Math.max(c0 + 0.6, lf + 0.4);
      this.split = this.split || { v: 0 }; a.ST(this.split, { v: 0 });
      a.tl.fromTo(this.split, { v: 0 }, { v: 1, duration: 1.6, ease: 'power3.inOut' }, c0 + 0.2);
      this.tear = this.tear || { v: 0 }; a.ST(this.tear, { v: 0 });
      a.tl.fromTo(this.tear, { v: 0 }, { v: 1, duration: 0.35, ease: 'power2.out' }, c0 + 0.25);
      a.tl.fromTo(this.tear, { v: 1 }, { v: 0, duration: 1.1, ease: 'power2.in' }, c0 + 0.6);
      a.ST(C.seamGlow.material, { opacity: 0 }); a.tl.fromTo(C.seamGlow.material, { opacity: 0 }, { opacity: self.gk(0.6), duration: 0.6 }, c0 + 0.3);
      a.show(C.hIntl, lf - 0.1); a.show(C.hCn, rg - 0.1);
      if ((b.left || {}).logos) popLogos(a, C.hIntl.el, b.left.logos, lf + 0.2);
      if ((b.right || {}).logos) popLogos(a, C.hCn.el, b.right.logos, rg + 0.2);
      var fly = function (q, at, back) {
        var aa = back ? q.to : q.from, bb = back ? q.from : q.to, top = Math.max(aa.y, bb.y) + 5;
        a.tl.fromTo(q.lb.at, { x: aa.x, z: aa.z }, { x: bb.x, z: bb.z, duration: 1.1, ease: 'power3.inOut' }, at);
        a.tl.fromTo(q.lb.at, { y: aa.y }, { y: top, duration: 0.55, ease: 'power2.out' }, at);
        a.tl.fromTo(q.lb.at, { y: top }, { y: bb.y, duration: 0.55, ease: 'power2.in' }, at + 0.55);
      };
      var lAt = listT(b, 'left_items', C.tl.length, lf, 0.18);   // 左边的卡：有自己的触发词就按它，没有就跟着 left 依次飞
      C.tl.forEach(function (q, i) { a.ST(q.lb.at, { x: q.from.x, y: q.from.y, z: q.from.z }); fly(q, lAt[i]); a.show(q.lb, lAt[i], 0.45); if (q.logos) popLogos(a, q.lb.el, q.logos, lAt[i] + 0.6); });
      var rAt = listT(b, 'right_items', C.tr.length, rg + 0.2, 0.9);
      C.tr.forEach(function (q, i) { a.ST(q.lb.at, { x: q.from.x, y: q.from.y, z: q.from.z }); fly(q, rAt[i]); a.show(q.lb, rAt[i], 0.45); if (q.logos) popLogos(a, q.lb.el, q.logos, rAt[i] + 0.6); });
      var hideT = b._.nextT != null ? b._.nextT - 0.3 : c.end - 0.3;
      C.tl.forEach(function (q, i) { kenBurns(a, q.lb.el, lAt[i], hideT); });       // 小卡题图：慢慢推近（和要点卡、帖子卡一样）
      C.tr.forEach(function (q, i) { kenBurns(a, q.lb.el, rAt[i], hideT); });
      [C.hIntl, C.hCn].forEach(function (lb) { a.hide(lb, hideT, 0.4); });
      C.tl.concat(C.tr).forEach(function (q) { a.hide(q.lb, hideT, 0.4); });
      // 章末：卡片飞回各自那一片，两半在强拍上合拢
      C.tl.concat(C.tr).forEach(function (q, i) {
        a.tl.fromTo(q.lb, { a: 0 }, { a: 0.9, duration: 0.3 }, c.end - 0.05 + i * 0.05);
        fly(q, c.end + i * 0.05, true);
        a.tl.fromTo(q.lb, { a: 0.9 }, { a: 0, duration: 0.35 }, c.end + 0.75 + i * 0.05);
      });
      a.tl.fromTo(this.split, { v: 1 }, { v: 0, duration: 1.4, ease: 'power3.inOut' }, c.end);
      a.tl.fromTo(C.seamGlow.material, { opacity: self.gk(0.6) }, { opacity: 0, duration: 0.6 }, c.end + 0.4);
      C.c0 = c0; C.last = Math.max(lAt.length ? lAt[lAt.length - 1] : lf, rAt.length ? rAt[rAt.length - 1] : rg);
      this.splitT = c0;
    },
    cams: function (b) { return [{ t: b._.o.c0 + 1.4, s: b._.shA, dur: 1.3, ease: 'io', arc: 6 }]; },
    settle: function (b) { return b._.o.last + 1.5; },
    explore: function (b) { return [3, b._.shA]; }
  };

  /* ---- "接下来"：已排期的日期翻牌，传闻的标"尚未证实"并抖一下 ---- */
  TPL.next = {
    build: function (b) {
      var self = this, L = this.P.L, C = b._.o, sh2 = this.shots.conB;
      if (b.head) C.head = this.label('<span class="v3tag acc">' + esc(S2(b.head, L)) + '</span>', { at: V3(SEAM, 7.4, 3.5), shot: sh2, align: 'b' });
      C.items = (b.items || []).slice(0, 3).map(function (it, i) {
        var sched = it.kind !== 'rumor';
        // 11-06 晚补：每一项可挂 logos（谁的计划），放在字的上面一行，说到这一项时弹出
        var lg = it.logos && it.logos.length ? '<span class="lg v3logos">' + logoList(self.P, it.logos, { sm: true }) + '</span>' : '';
        var html = sched
          ? '<div class="v3next v3glass' + (lg ? ' haslg' : '') + '"><span class="w v3n"><span class="v3flap" data-flap="1"><span>' + esc(S2(it.when, L)) + '</span></span></span>' + lg + '<span class="x">' + esc(S2(it.text, L)) + '</span>' + (it.status ? '<span class="st v3tag acc">' + esc(S2(it.status, L)) + '</span>' : '') + '</div>'
          : '<div class="v3next v3glass' + (lg ? ' haslg' : '') + '"><span class="w cn">' + esc(S2(it.when, L)) + '</span>' + lg + '<span class="x">' + esc(S2(it.text, L)) + '</span>' + (it.status ? '<span class="st v3tag warn" data-glitch="1">' + esc(S2(it.status, L)) + '</span>' : '') + '</div>';
        return { lb: self.label(html, { at: V3(SEAM, 5.6 - i * 3.0, 4 + i * 1.5), shot: sh2 }), sched: sched, logos: it.logos };
      });
      b._.shA = sh2; b._.enterAt = V3(0, 1, 0); b._.exitAt = V3(0, 1, 0); b._.headAt = V3(0, 6, 0);
    },
    tl: function (b, a) {
      var C = b._.o, c = b._.c, cn = bt(b, 'head', c.vs + 0.2), its = listT(b, 'items', C.items.length, cn + 1.2, 2.5);
      if (C.head) a.show(C.head, cn - 0.1);
      C.items.forEach(function (q, i) {
        a.show(q.lb, its[i] - (q.sched ? 0.3 : 0.5));
        var flap = q.lb.el.querySelector('[data-flap] > span');
        if (flap) { a.ST(flap, { yPercent: 100 }); a.tl.fromTo(flap, { yPercent: 100 }, { yPercent: 0, duration: 0.45, ease: 'back.out(2.2)' }, its[i] - 0.15); }
        if (q.logos) popLogos(a, q.lb.el, q.logos, its[i] + 0.1);
      });
      var g = null; C.items.forEach(function (q) { g = g || q.lb.el.querySelector('[data-glitch]'); });
      C.glitchEl = g; C.glitchT = bt(b, 'flag', (its[its.length - 1] || cn) + 0.6);
      [C.head].concat(C.items.map(function (q) { return q.lb; })).forEach(function (lb) { if (lb) a.hide(lb, c.end + 0.1, 0.5); });
      C.cn = cn; C.last = Math.max(C.glitchT, its[its.length - 1] || cn);
    },
    cams: function (b) { return [{ t: b._.o.cn + 0.5, s: b._.shA, dur: 1.5, ease: 'io', arc: 6 }]; },
    settle: function (b) { return b._.o.last + 0.8; },
    explore: function (b) { return [1, b._.shA]; },
    frame: function (b, t) {
      var C = b._.o; if (!C.glitchEl) return;
      var gd = t - C.glitchT, gx = (!this.P.rm && gd > 0 && gd < 0.9) ? Math.sin(t * 70) * 3 * (1 - gd / 0.9) : 0;
      var gs2 = gx ? 'translateX(' + gx.toFixed(1) + 'px)' : '';
      if (gs2 !== C._gs) { C.glitchEl.style.transform = gs2; C._gs = gs2; }
    }
  };

  /* =================================================================== 动效尝试（2026-11-06 晚加；只在分镜写了这些模板、字段时才起作用）
   * source_shot：原文网页截图（site/tools/source_shots.mjs 截的）放在纸感卡片里缓慢推近，旁白说到 mark 时荧光笔按行从左往右扫过原句；
   *   左上角出处签（媒体 · 日期，按事件卡来源写），可选一行中文 zh（只取同一条 fact 的 text_zh，分镜检查核过）。
   * source_excerpt：截图没成功时（或分镜直接写它），用事件卡那条原文自己排成"报纸摘录"，原句那一段同样按行扫过。
   * num_chain：数字递进 A → B → C，跟着旁白一个个出，最后一个用强调色；count: true 时数字从 0 滚到终值（终值照原标签一字不差）。
   * headline_open：开场"今日速览"（放在 open 章），每章一句大字标题压在该章配图上，依次出；角标写日期和"今日速览"。
   * quote_card 的 count: true：要点卡里第一个数字从 0 滚到终值（W.counter 的 fin：滚完显示原样的字）。 */
  var SRC_W = 11.6, HL_DUR = 1.5, CNT_DUR = 0.8, SRC_FW = 1.08, SRC_FW_EX = 1.55;   // 摘录卡镜头退远些：卡片约占画面六成宽，像一张剪报
  // 一行字里第一个数字包成可滚动的 span（终值写法 fin 原样保留：3200、80.52、94.49%、1,200）；返回 {html, v, dec, fin}
  function countHtml(s) {
    var str = String(s || ''), m = str.match(/[−\-]?\d[\d,]*(?:\.\d+)?/), out = { html: esc(str), v: null };
    if (!m) return out;
    var raw = m[0], i = m.index, num = +raw.replace(/,/g, '').replace('−', '-'), dec = (raw.split('.')[1] || '').length;
    if (!isFinite(num)) return out;
    var w = raw.replace(/[^\d]/g, '').length + (dec ? 0.4 : 0) + (raw.indexOf(',') >= 0 ? 0.4 * (raw.split(',').length - 1) : 0);
    out.html = esc(str.slice(0, i)) + '<span class="v3cnt" style="min-width:' + w.toFixed(1) + 'ch" data-c="' + esc(raw) + '">0</span>' + esc(str.slice(i + raw.length));
    out.v = num; out.dec = dec; out.fin = raw;
    return out;
  }
  function srcTag(P, b) {
    var s = b.src || {}, L = P.L, nm = tx(s.name, L), dt = tx(s.date, L);
    return '<div class="tag"><b>' + esc(nm) + '</b>' + (dt ? '<i>·</i><span>' + esc(dt) + '</span>' : '') + '</div>';
  }
  // 摘录：原句放在原文里（前后各留一点上下文，太长就省略），原句包成 <mark>，荧光笔沿着它一行行扫
  function excerptParts(b) {
    var full = String(b.full || b.quote || ''), q = String(b.quote || ''), i = full.indexOf(q);
    if (i < 0) { full = q; i = 0; }
    var pre = full.slice(0, i), post = full.slice(i + q.length), room = Math.max(40, 260 - q.length);
    if (pre.length > room * 0.55) { pre = pre.slice(pre.length - Math.round(room * 0.55)); pre = '…' + pre.slice(pre.indexOf(' ') + 1); }
    if (post.length > room * 0.45) { post = post.slice(0, Math.round(room * 0.45)); post = post.slice(0, post.lastIndexOf(' ')) + '…'; }
    return [pre, q, post];
  }
  function excerptLen(b) { return excerptParts(b).join('').length; }
  function excerptHtml(b) {
    var x = excerptParts(b), n = x.join('').length;
    return '<div class="ex' + (n > 240 ? ' long' : (n > 150 ? ' mid' : '')) + '"><p>' + esc(x[0]) + '<mark class="hl">' + esc(x[1]) + '</mark>' + esc(x[2]) + '</p></div>';
  }
  function srcBuild(self, b) {
    var P = self.P, L = P.L, g = b._.g, pal = self.pal, sh = b.shot && b.type === 'source_shot' ? b.shot : null, src = sh ? imgUrl(P, sh.img) : null;
    // 卡片高度按 HTML 的排法估（字号用舞台宽度的百分之一 u；这一镜装下 w×SRC_FW，所以 1u ≈ w×SRC_FW/100 个世界单位）
    var ar = sh && sh.w && sh.h ? sh.w / sh.h : 16 / 9, w = SRC_W, fw = src ? SRC_FW : SRC_FW_EX, uw = w * fw / 100, bodyU = 15;
    if (!src) {             // 摘录：按字数估几行（Times 每个字母约 0.46 个字号宽），和 CSS 里 .ex 的字号一致
      var exn = excerptLen(b), fs = exn > 240 ? 1.9 : (exn > 150 ? 2.2 : 2.5), cpl = Math.max(20, (w / uw - 4.4) / (0.46 * fs));
      bodyU = Math.ceil(exn / cpl) * fs * 1.55 + 2.8;
    }
    var h = (src ? (w - 1.5 * uw) / ar : bodyU * uw) + (1.5 + 2.2 + 0.6) * uw + (b.zh ? (0.6 + 2.1) * uw : 0);
    var p = new THREE.Mesh(new THREE.PlaneGeometry(w * 0.96, h * 0.94), self.panelMat(w, h, { radius: 0.35, alpha: pal.dark ? 0.4 : 0.5, edgeGlow: 0.7 }));
    p.position.set(0, h / 2 + 0.5, 0); p.material.uniforms.uFade.value = 0; g.add(p);
    self.shadow(w * 1.05, 3.5, g, 0, 0, 0.8); self.glass.push(p);
    // 镜头对准卡片中心稍下一点：卡片在画面里略偏上，下沿不压字幕
    b._.shS = self.bshot(b, [0, h / 2 + 0.5 - h * 0.06, 0], 0, 3, w * fw, h * (src ? 1.24 : 1.6), { pk: 1 });
    var body;
    if (src) {
      var cx = 0.5, cy = 0.5, ls = sh.lines || [];
      if (ls.length) {          // 推近的中心对准原句（不出图）
        var x0 = Math.min.apply(null, ls.map(function (l) { return l[0]; })), x1 = Math.max.apply(null, ls.map(function (l) { return l[0] + l[2]; }));
        var y0 = Math.min.apply(null, ls.map(function (l) { return l[1]; })), y1 = Math.max.apply(null, ls.map(function (l) { return l[1] + l[3]; }));
        cx = clamp((x0 + x1) / 2, 0.2, 0.8); cy = clamp((y0 + y1) / 2, 0.2, 0.8);
      }
      body = '<div class="shot" style="aspect-ratio:' + ar.toFixed(4) + '"><div class="zoom" style="transform-origin:' + (cx * 100).toFixed(1) + '% ' + (cy * 100).toFixed(1) + '%">' +
        '<img alt="" draggable="false" src="' + esc(src) + '">' +
        ls.map(function (l, i) {
          var px = 0.004, py = l[3] * 0.1;
          return '<i class="hl" data-l="' + i + '" style="left:' + ((l[0] - px) * 100).toFixed(2) + '%;top:' + ((l[1] - py) * 100).toFixed(2) + '%;width:' + ((l[2] + 2 * px) * 100).toFixed(2) + '%;height:' + ((l[3] + 2 * py) * 100).toFixed(2) + '%"></i>';
        }).join('') + '</div></div>';
    } else body = excerptHtml(b);
    var html = '<div class="v3card v3src' + (src ? ' shotc' : ' exc') + '">' + srcTag(P, b) + body + (b.zh ? '<div class="zh">' + esc(b.zh) + '</div>' : '') + '</div>';
    var lb = self.label(html, { obj: p, at: V3(0, 0, 0.05), shot: b._.shS, fitW: w, fitH: 0, min: 0.4, max: 1.4 });
    b._.o.pan = p; b._.o.lb = lb; b._.o.lines = src ? (sh.lines || []) : null;
    b._.enterAt = V3(-w / 2 + 0.5, 1, 0); b._.exitAt = V3(w / 2 - 0.5, 1, 0); b._.headAt = V3(0, h + 1.4, 0);
  }
  function srcTl(b, a) {
    var o = b._.o, c = b._.c, show = bt(b, 'show', c.vs + 0.6), mk = bt(b, 'mark', show + 1.2), el = o.lb.el;
    var endT = b._.nextT != null ? Math.max(show + 2, b._.nextT + 0.2) : c.end + 0.3;
    a.ST(o.pan.material.uniforms.uFade, { value: 0 }); a.U(o.pan.material.uniforms.uFade, 0, 1, show - 0.3, 0.8); a.show(o.lb, show - 0.1, 0.6);
    a.hide(o.lb, endT, 0.5); a.U(o.pan.material.uniforms.uFade, 1, 0, endT, 0.8, 'power1.in');
    var tag = el.querySelector('.tag');
    if (tag) { a.ST(tag, { autoAlpha: 0, x: -10 }); a.tl.fromTo(tag, { autoAlpha: 0, x: -10 }, { autoAlpha: 1, x: 0, duration: 0.5, ease: 'power3.out' }, show + 0.25); }
    var zm = el.querySelector('.zoom');      // 截图缓慢推近（到下场前一直在动）
    if (zm) { a.ST(zm, { scale: 1 }); a.tl.fromTo(zm, { scale: 1 }, { scale: 1.08, duration: Math.max(2, endT - show + 0.4), ease: 'none' }, show - 0.2); }
    var zh = el.querySelector('.zh');
    var dur = HL_DUR;
    if (o.lines) {            // 截图：一行一行扫，每行的时间按行宽分
      var hls = el.querySelectorAll('i.hl'), tot = 0;
      o.lines.forEach(function (l) { tot += Math.max(0.05, l[2]); });
      dur = clamp(0.8 + 0.42 * hls.length, 1.2, 2.4);
      var at = mk;
      Array.prototype.forEach.call(hls, function (e, i) {
        var d = dur * Math.max(0.05, o.lines[i][2]) / tot;
        a.ST(e, { scaleX: 0 }); a.tl.fromTo(e, { scaleX: 0 }, { scaleX: 1, duration: d, ease: 'none' }, at); at += d;
      });
    } else {                  // 摘录：<mark> 的底色按整段文字的长度从左往右长（跨行时一行接一行）
      var m = el.querySelector('mark.hl');
      if (m) {
        var n = wbLen(m.textContent); dur = clamp(0.9 + n / 120, 1.2, 2.4);
        a.ST(m, { backgroundSize: '0% 100%' }); a.tl.fromTo(m, { backgroundSize: '0% 100%' }, { backgroundSize: '100% 100%', duration: dur, ease: 'none' }, mk);
      }
      var ex = el.querySelector('.ex');
      if (ex) { a.ST(ex, { scale: 1 }); a.tl.fromTo(ex, { scale: 1 }, { scale: 1.04, duration: Math.max(2, endT - show + 0.4), ease: 'none' }, show - 0.2); }
    }
    if (zh) { a.ST(zh, { autoAlpha: 0, y: 8 }); a.tl.fromTo(zh, { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.5, ease: 'power2.out' }, mk + Math.min(dur, 1.2)); }
    o.show = show; o.mk = mk; o.done = mk + dur;
  }
  TPL.source_shot = {
    ext: [6.6, 6.6],
    build: function (b) { srcBuild(this, b); },
    tl: function (b, a) { srcTl(b, a); },
    cams: function (b) { return [{ t: b._.o.show + 0.4, s: b._.shS, dur: 1.4, ease: 'io', arc: 6 }]; },
    settle: function (b) { return b._.o.done + 1.0; },
    explore: function (b) { return [2, b._.shS]; }
  };
  TPL.source_excerpt = {
    ext: [6.6, 6.6],
    build: function (b) { srcBuild(this, b); },
    tl: function (b, a) { srcTl(b, a); },
    cams: function (b) { return TPL.source_shot.cams.call(this, b); },
    settle: function (b) { return b._.o.done + 1.0; },
    explore: function (b) { return [2, b._.shS]; }
  };

  /* ---- 数字递进：A → B → C 跟着旁白一个个出，最后一个用强调色 ---- */
  function chainNum(s, cnt) {
    var str = String(s || ''), m = str.match(/^(\D*?)([−\-]?\d[\d,]*(?:\.\d+)?%?)(.*)$/);
    if (!m) return { html: '<span class="w">' + esc(str) + '</span>', c: null };
    var c = cnt ? countHtml(m[2]) : null;
    return { html: (m[1] ? '<span class="u">' + esc(m[1]) + '</span>' : '') + '<span class="n v3n">' + (c && c.v != null ? c.html : esc(m[2])) + '</span>' + (m[3] ? '<span class="u">' + esc(m[3].trim()) + '</span>' : ''), c: c && c.v != null ? c : null };
  }
  TPL.num_chain = {
    ext: [7.5, 7.5],
    startT: function (b) { return bt(b, 'head', firstT(b)); },
    build: function (b) {
      var L = this.P.L, items = (b.items || []).slice(0, 4), n = items.length, cnt = b.count === true;
      var cs = [];
      var row = items.map(function (it, i) {
        var q = chainNum(S2(it.label, L), cnt); cs.push(q.c);
        return (i ? '<i class="ar" data-a="' + i + '" aria-hidden="true"></i>' : '') + '<div class="it' + (i === n - 1 ? ' last' : '') + '" data-i="' + i + '"><div class="nn">' + q.html + '</div>' +
          (it.sub ? '<div class="s">' + esc(S2(it.sub, L)) + '</div>' : '') + '</div>';
      }).join('');
      var w = Math.min(18, 4.3 * n + 1.4), h = (b.head ? 0.9 : 0) + (b.note ? 0.6 : 0) + 2.9;
      panelBuild(this, b, (b.head ? '<div class="hd">' + esc(S2(b.head, L)) + '</div>' : '') + '<div class="row">' + row + '</div>' +
        (b.note ? '<div class="ft">' + esc(S2(b.note, L)) + '</div>' : ''), [w, h], 'v3chain');
      b._.shS = this.bshot(b, [0, 3.9, 0], 0, 3, w * 1.19, h * 1.18, { pk: 1 });     // 竖屏也装下整张卡（不裁两边）
      b._.o.lb.shot = b._.shS;
      b._.o.n = n; b._.o.cs = cs;
    },
    tl: function (b, a) {
      var o = b._.o, c = b._.c, self = this, el = o.lb.el, ts = listT(b, 'items', o.n, bt(b, 'head', c.vs + 0.6) + 0.6, 1.4);
      var show = Math.min(bt(b, 'head', ts[0] - 0.5), ts[0] - 0.5);
      panelTl(b, a, show);
      var hd = el.querySelector('.hd');
      if (hd) { a.ST(hd, { autoAlpha: 0, y: 8 }); a.tl.fromTo(hd, { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.5, ease: 'power2.out' }, show + 0.1); }
      for (var i = 0; i < o.n; i++) {
        var it = el.querySelector('[data-i="' + i + '"]'), ar = el.querySelector('[data-a="' + i + '"]'), at = ts[i] - 0.12, last = i === o.n - 1;
        if (ar) { a.ST(ar, { scaleX: 0, autoAlpha: 0 }); a.tl.fromTo(ar, { scaleX: 0, autoAlpha: 0 }, { scaleX: 1, autoAlpha: 1, duration: 0.35, ease: 'power2.out' }, at - 0.3); }
        if (it) {
          a.ST(it, { autoAlpha: 0, y: 14, scale: last ? 0.86 : 0.94 });
          a.tl.fromTo(it, { autoAlpha: 0, y: 14, scale: last ? 0.86 : 0.94 }, { autoAlpha: 1, y: 0, scale: 1, duration: last ? 0.6 : 0.5, ease: last ? 'back.out(2.2)' : 'power3.out' }, at);
        }
        var cc = o.cs[i];
        if (cc && it) self.counter({ el: it }, 'span[data-c]', 0, cc.v, at + 0.05, CNT_DUR, cc.dec, cc.fin);
      }
      var ft = el.querySelector('.ft');
      if (ft) { a.ST(ft, { autoAlpha: 0 }); a.tl.fromTo(ft, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.5 }, ts[o.n - 1] + 0.6); }
      o.show = show; o.last = ts[o.n - 1];
    },
    cams: function (b) { return [{ t: b._.o.show + 0.4, s: b._.shS, dur: 1.3, ease: 'io', arc: 6 }]; },
    settle: function (b) { return b._.o.last + 1.4; },
    explore: function (b) { return [2, b._.shS]; }
  };

  /* ---- 开场"今日速览"：每章一句大字标题压在该章配图上（HUD 一层，盖在地图上），依次出；放完淡出，地图露出来再俯冲 ---- */
  TPL.headline_open = {
    build: function (b) {
      var P = this.P, L = P.L, items = (b.items || []).filter(function (x) { return x && x.text; });
      var date = tx((P.v.S || {})['title.date'], L), tag = tx(b.tag, L) || (L === 'en' ? 'Today at a glance' : '今日速览');
      var html = '<div class="tg"><b class="v3n">' + esc(date) + '</b><span>' + esc(tag) + '</span></div>' + items.map(function (it, i) {
        var src = it.img ? imgUrl(P, it.img) : null;
        return '<div class="it" data-i="' + i + '"><div class="ph' + (src ? '' : ' none') + '">' + (src ? '<i style="background-image:url(&quot;' + src + '&quot;)"></i>' : '') + '</div><div class="sc"></div>' +
          '<div class="tx"><div class="lb"><b class="v3n">' + pad2(i + 1) + '</b><span>' + esc(tx(it.label, L)) + '</span></div><div class="h"><span>' + esc(tx(it.text, L)) + '</span></div>' +
          (it.sub ? '<div class="s">' + esc(tx(it.sub, L)) + '</div>' : '') + '</div></div>';
      }).join('');
      var root = el('div', 'v3hl', html); root.setAttribute('aria-hidden', 'true');
      if (P.wb) wbWalk(P.wb, root, false);
      P.hudEl.insertBefore(root, P.hudEl.firstChild);
      b._.o.root = root; b._.o.n = items.length;
    },
    tl: function (b, a) {
      var o = b._.o, c = b._.c, root = o.root, n = o.n; if (!n) return;
      var ts = listT(b, 'items', n, c.vs + 1.0, 2.4), go = a.T('open.go', c.end);
      var tf = this.Q(a.T('open.map', c.vs + 0.1) + 0.9);             // 片头大字淡出的时刻（W.timeline 里同一个算法）
      var t0 = Math.max(ts[0] - 0.35, tf + 0.25), tEnd = Math.max(ts[n - 1] + 1.4, Math.min(go - 0.6, ts[n - 1] + 2.4));
      a.ST(root, { autoAlpha: 0 });
      a.tl.fromTo(root, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.45, ease: 'power2.out' }, t0);
      a.tl.fromTo(root, { autoAlpha: 1 }, { autoAlpha: 0, duration: 0.6, ease: 'power1.in' }, tEnd);
      var tg = root.querySelector('.tg');
      if (tg) { a.ST(tg, { autoAlpha: 0, y: -8 }); a.tl.fromTo(tg, { autoAlpha: 0, y: -8 }, { autoAlpha: 1, y: 0, duration: 0.5, ease: 'power3.out' }, t0 + 0.15); }
      for (var i = 0; i < n; i++) {
        var e = root.querySelector('.it[data-i="' + i + '"]'), at = Math.max(t0, ts[i] - 0.15), nx = i < n - 1 ? Math.max(t0 + 0.4, ts[i + 1] - 0.15) : tEnd + 0.6;
        a.ST(e, { autoAlpha: 0 });
        a.tl.fromTo(e, { autoAlpha: 0 }, { autoAlpha: 1, duration: i ? 0.5 : 0.05, ease: 'power1.out' }, at);
        if (i < n - 1) a.tl.fromTo(e, { autoAlpha: 1 }, { autoAlpha: 0, duration: 0.05 }, nx + 0.55);   // 下一屏淡入盖住以后再藏
        var ph = e.querySelector('.ph i');
        if (ph) { a.ST(ph, { scale: 1.1 }); a.tl.fromTo(ph, { scale: 1.1 }, { scale: 1, duration: Math.max(1.5, nx - at + 0.8), ease: 'none' }, at - 0.1); }
        var h = e.querySelector('.h > span'), lb = e.querySelector('.lb'), sb = e.querySelector('.s');
        if (h) { a.ST(h, { yPercent: 112 }); a.tl.fromTo(h, { yPercent: 112 }, { yPercent: 0, duration: 0.6, ease: 'power3.out' }, at + 0.05); }
        [lb, sb].forEach(function (x, k) { if (!x) return; a.ST(x, { autoAlpha: 0, y: 8 }); a.tl.fromTo(x, { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.45, ease: 'power2.out' }, at + 0.15 + k * 0.2); });
      }
    }
  };

  /* =================================================================== 结合式（2026-11-06 深夜加；只在分镜写了 shot 字段时起作用）
   * 原话卡带原文截图：post_card / quote_card 写了 shot，截图放进这张卡的图位（替代 image），荧光笔扫那句；人名、身份、中文、出处签照旧。
   * 时间轴日子带原文截图：timeline 的 ticks[i].shot，截图当这一天的小图；说到这一天时从小图弹出、放大到画面中间、停住，荧光笔扫那句，
   *   再缩回小图（tlPopFrame），时间轴不打断；镜头停留沿用 tlImageHold。
   * shot 编进播放器的字段（video3_storyboard.shot_data）：{src: {name, date}, quote, full, zh, img?, lines?, w?, h?}：有 img 是截图，
   *   没有（截图没成功、裁不干净、字比字幕小）就是摘录，放在同一个图位。
   * 卡片和弹出框的尺寸都按舞台宽度的百分之一（u）算，video3_storyboard.shot_slot_u 照同一套数估"原句在成片里有多大"，两边要一起改。 */
  var SBX_CARD_U = 84.9, SBX_PAD_U = 2.8, SBX_HMAX_U = 46, SBX_W = 10.4;   // 卡片最宽占舞台 84.9%（左右内边距共 2.8u），整张卡最高 46u
  var TL_SHOT_TAIL = 1.1;                                                  // 弹出框宽见 .v3tpop（横屏 70u、竖屏 48u）；荧光扫完再停 1.1 秒
  function sbxRatio(s) { return s && s.w && s.h ? s.w / s.h : 16 / 9; }
  function sbxLines(ls) {     // 荧光笔的每一行（和 source_shot 同一个画法）
    return (ls || []).map(function (l, i) {
      var px = 0.004, py = l[3] * 0.1;
      return '<i class="hl" data-l="' + i + '" style="left:' + ((l[0] - px) * 100).toFixed(2) + '%;top:' + ((l[1] - py) * 100).toFixed(2) + '%;width:' + ((l[2] + 2 * px) * 100).toFixed(2) + '%;height:' + ((l[3] + 2 * py) * 100).toFixed(2) + '%"></i>';
    }).join('');
  }
  function sbxCenter(ls) {
    if (!ls || !ls.length) return [0.5, 0.5];
    var x0 = Math.min.apply(null, ls.map(function (l) { return l[0]; })), x1 = Math.max.apply(null, ls.map(function (l) { return l[0] + l[2]; }));
    var y0 = Math.min.apply(null, ls.map(function (l) { return l[1]; })), y1 = Math.max.apply(null, ls.map(function (l) { return l[1] + l[3]; }));
    return [clamp((x0 + x1) / 2, 0.2, 0.8), clamp((y0 + y1) / 2, 0.2, 0.8)];
  }
  // 截图框（或摘录）的 HTML：出处签＋截图（荧光笔每一行）＋可选中文行。返回 {html, img, lines}
  function sbxHtml(P, s) {
    var src = s.img ? imgUrl(P, s.img) : null, ls = src ? (s.lines || []) : null, zh = s.zh ? '<div class="zh">' + esc(s.zh) + '</div>' : '';
    if (!src) return { html: '<div class="v3sbx v3src exc">' + srcTag(P, s) + excerptHtml(s) + zh + '</div>', img: null, lines: null };
    var c = sbxCenter(ls);
    return { html: '<div class="v3sbx v3src shotc">' + srcTag(P, s) + '<div class="shot" style="aspect-ratio:' + sbxRatio(s).toFixed(4) + '"><div class="zoom" style="transform-origin:' +
      (c[0] * 100).toFixed(1) + '% ' + (c[1] * 100).toFixed(1) + '%"><img alt="" draggable="false" src="' + esc(src) + '">' + sbxLines(ls) + '</div></div>' + zh + '</div>', img: src, lines: ls };
  }
  // 荧光笔：截图按行扫（每行时间按行宽分），摘录按整段文字长度扫；返回扫的秒数（和 srcTl 同一个算法）
  function sbxSweep(a, root, ls, mk) {
    var dur = HL_DUR;
    if (ls) {
      var hls = root.querySelectorAll('i.hl'), tot = 0, at = mk;
      ls.forEach(function (l) { tot += Math.max(0.05, l[2]); });
      dur = clamp(0.8 + 0.42 * hls.length, 1.2, 2.4);
      Array.prototype.forEach.call(hls, function (e, i) {
        var d = dur * Math.max(0.05, ls[i][2]) / tot;
        a.ST(e, { scaleX: 0 }); a.tl.fromTo(e, { scaleX: 0 }, { scaleX: 1, duration: d, ease: 'none' }, at); at += d;
      });
    } else {
      var m = root.querySelector('mark.hl');
      if (m) {
        var n = wbLen(m.textContent); dur = clamp(0.9 + n / 120, 1.2, 2.4);
        a.ST(m, { backgroundSize: '0% 100%' }); a.tl.fromTo(m, { backgroundSize: '0% 100%' }, { backgroundSize: '100% 100%', duration: dur, ease: 'none' }, mk);
      }
    }
    return dur;
  }
  // 截图框出场：出处签滑进来、截图（或摘录）慢慢推近、中文行在荧光扫到一半后出来
  function sbxTl(a, root, t0, t1, mk, dur) {
    var tag = root.querySelector('.tag'), zm = root.querySelector('.zoom') || root.querySelector('.ex'), zh = root.querySelector('.zh');
    if (tag) { a.ST(tag, { autoAlpha: 0, x: -10 }); a.tl.fromTo(tag, { autoAlpha: 0, x: -10 }, { autoAlpha: 1, x: 0, duration: 0.5, ease: 'power3.out' }, t0 + 0.25); }
    if (zm) { a.ST(zm, { scale: 1 }); a.tl.fromTo(zm, { scale: 1 }, { scale: zm.classList.contains('ex') ? 1.03 : 1.06, duration: Math.max(2, t1 - t0), ease: 'none' }, t0 - 0.2); }
    if (zh) { a.ST(zh, { autoAlpha: 0, y: 8 }); a.tl.fromTo(zh, { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 0.5, ease: 'power2.out' }, mk + Math.min(dur, 1.2)); }
  }
  // 结合式卡片的版式（舞台宽度的百分之几）：截图框按它自己的比例排在卡片上半截，下面是这张卡原来的字；
  // 卡片最宽 SBX_CARD_U，整张卡高过 SBX_HMAX_U 就把卡片收窄（截图跟着变小）。extraU：截图以外的部分有多高
  function sbxCardU(ar, extraU) { return Math.max(40, Math.min(SBX_CARD_U, (SBX_HMAX_U - extraU) * ar + SBX_PAD_U)); }
  function zhLines(s, perLine) { var n = String(s || '').replace(/\s/g, '').length; return Math.max(1, Math.ceil(n / Math.max(6, perLine))); }
  function sbxExtra(P, b, kind, cardU, sx) {       // 卡片里截图框以外的高度（u）；和 CSS 里 .v3sbxc 那几条的字号、行高一致
    var L = P.L, s = b.shot || {}, w = cardU - SBX_PAD_U, u = 1.1 + 1.3;                              // 上下内边距
    u += 2.2 + 0.6;                                                                                   // 截图框里的出处签和间距
    if (s.zh) u += 0.6 + 1.4 * 1.45 * zhLines(s.zh, (w - 1.1) / 1.4);
    if (kind === 'post_card') {
      var q = S2(b.text, L), role = S2((b.who || {}).role, L);
      u += 0.9 + 1.6 + 0.9 + 2.1 * 1.45 * zhLines(q, w / 2.1) + 0.9 + (role ? 3.4 : 2.6);              // 平台行、原话、署名
    } else {
      u += 0.9 + 1.3 * 1.25 + 0.9 + 3.0 * 1.2 * zhLines(S2(b.text, L), w / 3.0);                       // 署名行、要点
    }
    return u;
  }
  function sbxBodyU(s, w, ar) {            // 截图框本身的高度（u）：截图按比例；摘录按字数估（Times 每个字母约 0.46 个字号宽）
    if (s.img) return w / ar;
    var n = excerptLen(s), fs = n > 240 ? 1.9 : (n > 150 ? 2.2 : 2.5), cpl = Math.max(20, (w - 2.8) / (0.46 * fs));
    return Math.ceil(n / cpl) * fs * 1.55 + 2.8;
  }
  function sbxCardBuild(self, b, kind, inner, sx) {
    var P = self.P, ar = sbxRatio(b.shot), cardU = SBX_CARD_U, ex = 0, body = 0;
    for (var it = 0; it < 3; it++) {      // 卡片宽影响字的行数，算两三遍就稳了
      ex = sbxExtra(P, b, kind, cardU, sx); body = sbxBodyU(b.shot, cardU - SBX_PAD_U, ar);
      cardU = sx.img ? sbxCardU(ar, ex) : SBX_CARD_U;
    }
    var w = SBX_W, kw = 0.9 * w / cardU, hU = ex + body, h = hU * kw + 0.1 * w;   // kw：1u 是多少个世界单位（这张卡占 cardU 宽时）
    panelBuild(self, b, inner, [w, h], (kind === 'post_card' ? 'v3post img' : 'v3qc') + ' v3sbxc' + (sx.img ? '' : ' exc'));
    b._.o.lb.fitH = 0;                     // 高度跟着内容走（估的高只用来定玻璃板和镜头）
    b._.shS = self.bshot(b, [0, 3.9, 0], b._.fork ? (b._.branch ? 14 : -14) : 0, 3, 100 * kw, hU * kw * 1.06, { pk: 1 });
    b._.o.lb.shot = b._.shS;
    b._.o.sx = sx; b._.o.cardU = cardU;
  }
  function sbxCardTl(self, b, a, show) {
    var o = b._.o, c = b._.c, el = o.lb.el, sx = o.sx;
    var mk = Math.max(bt(b, 'shot_mark', show + 1.2), show + 0.5), root = el.querySelector('.v3sbx');
    var dur = sbxSweep(a, root, sx.lines, mk);
    sbxTl(a, root, show, c.end + 0.3, mk, dur);
    o.mk = mk; o.done = mk + dur;
  }
  // 时间轴日子带截图：小图（截图按原句那一块裁满）＋弹出框；弹出框每一帧在 updateLabels 之后摆（tlPopFrame）
  function tickShot(self, q) {
    var P = self.P, s = q.shot, sx = sbxHtml(P, s), c = sbxCenter(sx.lines);
    var keep, th;
    if (FX) {       // 11-08（K46）：有配图就一直用配图当小图（截图成功时也是），截图只在弹出框里；没有配图就是"媒体名＋日期"出处签
      keep = q.img ? imgUrl(P, q.img) : null;
      th = keep ? '<div class="ph sbth"><i style="background-image:url(&quot;' + keep + '&quot;)"></i></div>'
        : '<div class="ph sbth stg"><span><b>' + esc(tx((s.src || {}).name, P.L)) + '</b>' + ((s.src || {}).date ? '<small>' + esc(tx(s.src.date, P.L)) + '</small>' : '') + '</span></div>';
    } else {
      keep = !sx.img && q.img ? imgUrl(P, q.img) : null;     // 11-07 补：截图没成功退回摘录时，这一天原来的小图留着（弹出框里仍是摘录）
      th = sx.img ? '<div class="ph sbth"><i style="background-image:url(&quot;' + sx.img + '&quot;);background-position:' + (c[0] * 100).toFixed(1) + '% ' + (c[1] * 100).toFixed(1) + '%"></i></div>'
        : keep ? '<div class="ph sbth"><i style="background-image:url(&quot;' + keep + '&quot;)"></i></div>'
        : '<div class="ph sbth exc"><span>' + esc(tx((s.src || {}).name, P.L)) + '</span></div>';
    }
    var pop = el('div', 'v3tpop', sx.html.replace('class="v3sbx v3src', 'class="v3card v3src v3sbx'));
    if (P.wb) wbWalk(P.wb, pop, false);
    pop.setAttribute('aria-hidden', 'true');
    P.worldEl.appendChild(pop);
    return { sx: sx, th: th, el: pop, pop: { v: 0 }, t1: 0 };
  }
  W.tlPopFrame = function () {
    var P = this.P, sw = P.sw || 960, sh = P.sh || 540, wr = null, portrait = sw < sh;
    (this.tlPops || []).forEach(function (k) {
      var s = k.shot, v = s.pop.v, e = s.el;
      if (v <= 0.001) { if (s._on) { e.style.visibility = 'hidden'; e.style.opacity = '0'; if (s.thEl) s.thEl.style.opacity = ''; s._on = false; } return; }
      wr = wr || P.worldEl.getBoundingClientRect();
      var kx = wr.width ? sw / wr.width : 1, thEl = s.thEl || (s.thEl = k.lb.el.querySelector('.ph'));
      if (s._sw !== sw) { s._sw = sw; s._w = e.offsetWidth; s._h = e.offsetHeight; }
      var W0 = s._w || 1, H0 = s._h || 1, r = thEl ? thEl.getBoundingClientRect() : null;
      var tcx = r ? (r.left + r.width / 2 - wr.left) * kx : sw * 0.8, tcy = r ? (r.top + r.height / 2 - wr.top) * kx : sh * 0.4, tw = r && r.width ? r.width * kx : W0 * 0.2;
      var gcx = sw / 2, gcy = clamp(sh * (portrait ? 0.42 : 0.455), H0 / 2 + sh * 0.03, sh * 0.87 - H0 / 2);   // 停在画面正中略偏上，下沿不压字幕
      var u = out3(v), sc = lerp(tw / W0, 1, u), cx = lerp(tcx, gcx, u), cy = lerp(tcy, gcy, u);
      e.style.transform = 'translate3d(' + (cx - W0 * sc / 2).toFixed(1) + 'px,' + (cy - H0 * sc / 2).toFixed(1) + 'px,0) scale(' + sc.toFixed(4) + ')';
      e.style.opacity = String(Math.round(clamp(v * 4, 0, 1) * 1000) / 1000); e.style.visibility = 'visible';
      if (thEl) thEl.style.opacity = String(Math.round((1 - clamp(v * 4, 0, 1)) * 1000) / 1000);
      s._on = true;
    });
  };

  /* ---------- 章与章之间的"神奇移动"：光线（trail）、小方块（cube）、点阵流过去（swarm） ---------- */
  W.buildHandoffs = function () {
    var self = this, chs = this.P.v.chapters || [], pal = this.pal, prev = null;
    this.handoffs = [];
    chs.forEach(function (c) {
      if (!self.areas[c.id] || !(c._real || []).length) return;
      if (!prev) { prev = c; return; }
      var pl = prev._real[prev._real.length - 1], nf = c._real[0];
      var kind = c.handoff || (pl.type === 'particle_counter' ? 'swarm' : (nf.type === 'chain' ? 'cube' : (c.kind === 'contrast' ? 'none' : 'trail')));
      var h = { kind: kind, c: c, from: pl, to: nf };
      if (kind === 'trail') {
        var a = self.wp(pl, pl._.exitAt.x, pl._.exitAt.y, pl._.exitAt.z), b = nf._.enterWorld ? nf._.enterWorld(V3(0, 0, 0)) : self.wp(nf, nf._.enterAt.x, nf._.enterAt.y, nf._.enterAt.z);
        var g = self.areas[c.id].g, toL = function (w) { return w.clone().sub(g.position); };
        var m1 = a.clone().add(V3(4, 0.6, -2)), m2 = b.clone().add(V3(-3, 2.2, 3.5));
        h.tube = self.tube([toL(a), toL(m1), toL(m2), toL(b)], 0.04, self.flowMat(pal.acc, { glow: 1.9 }), 260); g.add(h.tube);
      } else if (kind === 'cube') {
        h.cube = new THREE.Mesh(new THREE.RoundedBoxGeometry(0.55, 0.55, 0.55, 3, 0.1), self.coreMat(pal.acc, pal.dark ? 1.8 : 1.3));
        h.cube.visible = false; self.scene.add(h.cube);
        h.glow = self.glow(3, pal.acc, 0); self.scene.add(h.glow);
        self.cubes.push(h);
      } else if (kind === 'swarm' && pl.type === 'particle_counter') {
        // 点阵的路线（在点阵那一组的局部坐标里；两半一起移动，相对位置不变）
        var pg = pl._.g, P7 = pl._.o.swarmU.uP.value, loc = function (w) { return pg.worldToLocal(w.clone()); };
        if (nf.type === 'fork') {
          var M = nf._.o, w = function (v) { return self.wp(nf, v.x, v.y, v.z); };
          var j = w(M.J), A1 = w(M.A).add(V3(1.5, 0, 0)), B1 = w(M.B).add(V3(1.5, 0, 0));
          P7[1].copy(loc(j.clone().add(V3(-13, 3.05, 0)))); P7[2].copy(loc(j));
          P7[3].copy(loc(w(M.cA))); P7[4].copy(loc(A1)); P7[5].copy(loc(w(M.cB))); P7[6].copy(loc(B1));
        } else {
          var tgt = nf._.enterWorld ? nf._.enterWorld(V3(0, 0, 0)) : self.wp(nf, nf._.enterAt.x, nf._.enterAt.y, nf._.enterAt.z), lt = loc(tgt), st = P7[0].clone();
          P7[1].copy(st.clone().lerp(lt, 0.5).add(V3(0, 3, 0))); for (var k = 2; k < 7; k++) P7[k].copy(lt);
        }
        pl._.o.handoff = h;
      } else h.kind = 'none';
      self.handoffs.push(h);
      prev = c;
    });
  };

  /* ---------- 地图上的热点（开场和结尾、自由看图） ---------- */
  W.buildChips = function () {
    var self = this, P = this.P, L = P.L, cl = P.v.clusters || [], pal = this.pal;
    this.chips = {};
    // 每一片一根细光柱＋一圈向外扩的波纹
    this.beacons = {};
    var beamMat = function () {
      return new THREE.ShaderMaterial({ uniforms: { uCol: { value: pal.acc.clone().multiplyScalar(pal.dark ? 2.2 : 1.6) }, uFade: { value: 0 } },
        vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
        fragmentShader: 'uniform vec3 uCol; uniform float uFade; varying vec2 vUv; void main(){ float a = pow(clamp(1.0 - vUv.y, 0.0, 1.0), 1.6) * uFade; gl_FragColor = vec4(uCol, a * 0.9); }',
        transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: pal.dark ? THREE.AdditiveBlending : THREE.NormalBlending });
    };
    Object.keys(this.areas).forEach(function (k) {
      var ar = self.areas[k]; if (ar.side === 0) return;
      var p = ar.pos, g = ar.half;
      var beam = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 9, 10, 1, true), beamMat()); beam.position.set(p[0], 4.5, p[2]); beam.renderOrder = 3; g.add(beam);
      var ring = new THREE.Mesh(new THREE.RingGeometry(4.4, 4.62, 96), new THREE.MeshBasicMaterial({ color: pal.acc, transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide }));
      ring.rotation.x = -Math.PI / 2; ring.position.set(p[0], 0.06, p[2]); ring.renderOrder = 2; g.add(ring);
      var dot = self.glow(3.2, pal.acc, 0); dot.position.set(p[0], 0.4, p[2]); g.add(dot);
      self.beacons[k] = { beam: beam, ring: ring, dot: dot };
    });
    cl.forEach(function (c) {
      var ar = self.areas[c.ch || c.id]; if (!ar) return;
      var p = ar.pos;
      var lb = self.label('<button type="button" class="v3chip v3glass" data-cl="' + esc(c.id) + '" tabindex="-1"><span class="nm">' + esc(tx(c.name, L)) + '</span><span class="ky v3n">' + esc(tx(c.key, L)) + '</span><span class="sb">' + esc(tx(c.sub, L)) + '</span></button>',
        { obj: ar.half, at: V3(p[0], 3.6, p[2]), shot: self.shots.over, align: 'b', min: 0.62, max: 1.3, keep: true });
      lb.btn = lb.inEl.firstChild; lb.home = lb.at.clone(); lb.side = ar.side;
      self.chips[c.id] = lb;
    });
  };

  /* =================================================================== 镜头脚本（全图的几镜；各模板的镜头在模板里） */
  W.defineShots = function () {
    var S = this.shot.bind(this);
    this.shots = {
      start: S([-6, 1, 4], -16, 36, 54, 30),
      over: S(MAPC, -4, 58, 84, 44, { pk: 0.84 }),
      over2: S(MAPC, 7, 54, 80, 42, { pk: 0.84 }),
      conA: S([MAPC[0], 0, MAPC[2] + 1], 0, 63, 98, 52, { pk: 1 }),
      conB: S([SEAM, 4.4, 4.4], 0, 22, 30, 15),
      close: S(MAPC, 4, 57, 84, 44, { pk: 0.84 })
    };
    for (var k in this.shots) this.shots[k].name = k;
  };

  /* =================================================================== 时间轴（全部按旁白的触发词排） */
  W.timeline = function () {
    var P = this.P, d = P.v, self = this, gs = window.gsap;
    var T = function (k, dflt) { var v = (d.T || {})[k]; return typeof v === 'number' ? v : (dflt != null ? dflt : 0); };
    var chs = d.chapters || [], ch = {}; chs.forEach(function (c) { ch[c.id] = c; });
    var open = chs.filter(function (c) { return c.kind === 'open'; })[0] || { start: 0, end: 12, vs: 3, ve: 10 };
    var close = chs.filter(function (c) { return c.kind === 'close'; })[0] || { start: d.duration - 8, end: d.duration, vs: d.duration - 7, ve: d.duration - 2 };
    var stories = chs.filter(function (c) { return c.kind === 'story'; });
    var tl = gs.timeline({ paused: true, defaults: { immediateRender: false, overwrite: false, lazy: false } });
    this.tl = tl;
    var ST = function (target, vars, at) { tl.set(target, Object.assign({ immediateRender: true }, vars), at || 0); };
    var show = function (lb, at, dur) { tl.fromTo(lb, { a: 0 }, { a: 1, duration: dur || 0.5, ease: 'power2.out' }, at); };
    var hide = function (lb, at, dur) { tl.fromTo(lb, { a: 1 }, { a: 0, duration: dur || 0.35, ease: 'power1.in' }, at); };
    var U = function (u, from, to, at, dur, ease) { tl.fromTo(u, { value: from }, { value: to, duration: dur || 0.6, ease: ease || 'power2.out' }, at); };
    var api = { tl: tl, T: T, ST: ST, show: show, hide: hide, U: U };
    var chips = this.chips;
    this.L.forEach(function (lb) { ST(lb, { a: 0 }); });
    this.split = { v: 0 }; this.tear = { v: 0 }; this.splitT = null;

    /* ---- 开场：片头字上推、光扫；地图亮起，各片随旁白依次点亮 ---- */
    var hud = P.hud, go = T('open.go', open.end);
    ST(hud.title, { autoAlpha: 1, y: 0 });
    ST(hud.lines, { yPercent: 112 }); ST(hud.rule, { scaleX: 0 }); ST(hud.sweeps, { '--sx': '150%' });
    // 片头字跟着配乐：片头乐句第一个强拍上推，两拍后描下划线，再一拍光扫（没有配乐时按原来的 0.15 秒起）
    var m0 = T('mus.in', 0.15), bt0 = this.beat;
    tl.fromTo(hud.lines, { yPercent: 112 }, { yPercent: 0, duration: 0.75, ease: 'power3.out', stagger: 0.2 }, m0);
    tl.fromTo(hud.rule, { scaleX: 0 }, { scaleX: 1, duration: 0.7, ease: 'power2.inOut' }, m0 + Math.max(0.8, bt0 * 2));
    tl.fromTo(hud.sweeps, { '--sx': '150%' }, { '--sx': '-60%', duration: 1.5, ease: 'power1.inOut', stagger: 0.12 }, m0 + Math.max(1.1, bt0 * 3));
    var omap = T('open.map', open.vs + 0.1);
    tl.fromTo(hud.title, { autoAlpha: 1, y: 0 }, { autoAlpha: 0, y: -40, duration: 0.7, ease: 'power2.in' }, this.Q(omap + 0.9));
    if (hud.cover) {
      var ci = hud.cover.querySelector('.im');
      ST(hud.cover, { autoAlpha: 1 }); tl.fromTo(hud.cover, { autoAlpha: 1 }, { autoAlpha: 0, duration: 0.9, ease: 'power2.in' }, this.Q(omap + 0.9));
      ST(ci, { scale: 1.07 }); tl.fromTo(ci, { scale: 1.07 }, { scale: 1, duration: Math.max(1, omap + 1.8), ease: 'none' }, 0);
    }
    ST(hud.kick, { autoAlpha: 0 }); tl.fromTo(hud.kick, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.5 }, omap + 1.4);
    U(this.routeL.material.uniforms.uReveal, 0, 1, 0.6, 3.6, 'power1.inOut');
    U(this.routeR.material.uniforms.uReveal, 0, 1, 3.0, 2.6, 'power1.inOut');
    this.pads = Object.keys(this.areas).map(function (k) { var ar = self.areas[k]; return { k: k, x: ar.pos[0], z: ar.pos[2], r: ar.side === 0 ? 6 : 5.2, w: 0, side: ar.side }; });
    var padAt = {}, ov = fillTimes(stories.map(function (c) { return T(c.id + '.map', null); }).map(function (v) { return v === null || v === 0 ? null : v; }), open.vs + 1.2, 1.2);
    stories.forEach(function (c, i) { padAt[c.id] = ov[i]; });
    this.pads.forEach(function (pd) {
      ST(pd, { w: 0 });
      if (padAt[pd.k] != null) tl.fromTo(pd, { w: 0 }, { w: 1, duration: 0.6, ease: 'power2.out' }, padAt[pd.k] - 0.1);
    });
    var first = stories[0];
    stories.forEach(function (c) { var k = c.id; if (chips[k]) { show(chips[k], padAt[k] - 0.05, 0.5); hide(chips[k], k === (first && first.id) ? go + 0.9 : go + 0.4, 0.4); } });
    var z0 = T('close.map', close.vs + 0.1);
    Object.keys(this.beacons).forEach(function (k) {
      var bc = self.beacons[k], at = padAt[k] != null ? padAt[k] : omap + 1;
      ST(bc.beam.material.uniforms.uFade, { value: 0 }); ST(bc.ring.scale, { x: 1, y: 1, z: 1 }); ST(bc.ring.material, { opacity: 0 }); ST(bc.dot.material, { opacity: 0 });
      U(bc.beam.material.uniforms.uFade, 0, 1, at - 0.1, 0.7);
      tl.fromTo(bc.ring.scale, { x: 0.6, y: 0.6, z: 0.6 }, { x: 1.9, y: 1.9, z: 1.9, duration: 1.6, ease: 'power2.out' }, at - 0.1);
      tl.fromTo(bc.ring.material, { opacity: 0.9 }, { opacity: 0, duration: 1.6, ease: 'power1.in' }, at - 0.1);
      tl.fromTo(bc.dot.material, { opacity: 0 }, { opacity: self.gk(0.9), duration: 0.5 }, at - 0.1);
      U(bc.beam.material.uniforms.uFade, 1, 0, go + 0.8, 0.8);
      tl.fromTo(bc.dot.material, { opacity: self.gk(0.9) }, { opacity: 0, duration: 0.8 }, go + 0.8);
      U(bc.beam.material.uniforms.uFade, 0, 1, z0 + 0.3, 0.9);
      tl.fromTo(bc.dot.material, { opacity: 0 }, { opacity: self.gk(0.9), duration: 0.8 }, z0 + 0.3);
      tl.fromTo(bc.ring.scale, { x: 0.6, y: 0.6, z: 0.6 }, { x: 1.9, y: 1.9, z: 1.9, duration: 1.6, ease: 'power2.out' }, z0 + 0.4);
      tl.fromTo(bc.ring.material, { opacity: 0.9 }, { opacity: 0, duration: 1.6, ease: 'power1.in' }, z0 + 0.4);
    });

    /* ---- 各章的模板 ---- */
    chs.forEach(function (c) { (c._real || []).concat(c._images || []).forEach(function (b) { TPL[b.type].tl.call(self, b, api); }); });
    (this.heads || []).forEach(function (b) { TPL.headline_open.tl.call(self, b, api); });

    /* ---- 章与章之间的神奇移动 ---- */
    (this.handoffs || []).forEach(function (h) {
      var c = h.c, nf = h.to;
      if (h.kind === 'trail') {
        ST(h.tube.material.uniforms.uReveal, { value: 0 });
        U(h.tube.material.uniforms.uReveal, 0, 1, c.start, 1.7, 'power1.inOut');   // 分界的强拍上，光线伸向下一片
        U(h.tube.material.uniforms.uFade, 1, 0, c.vs + 2.6, 1.0);
      } else if (h.kind === 'cube') {
        h.t0 = c.start; h.t1 = Math.max(c.start + 0.8, startT(nf) - 0.25);         // 强拍上起飞
      } else if (h.kind === 'swarm') {
        var Z = h.from._.o;
        U(Z.swarmU.uM2, 0, 1, c.start, 2.6, 'power1.inOut');
        U(Z.swarmU.uFade, 1, 0, c.end + 0.6, 1.0);
      }
    });
    // 神奇移动：第一片的热点卡在俯冲时一路飘到这一片的标题处，再交棒
    var fb = first && (first._real || [])[0];
    if (fb && chips[first.id]) {
      var cm = chips[first.id], ha = this.wp(fb, fb._.headAt.x, fb._.headAt.y, fb._.headAt.z);
      ST(cm.at, { x: cm.home.x, y: cm.home.y, z: cm.home.z });
      tl.fromTo(cm.at, { x: cm.home.x, y: cm.home.y, z: cm.home.z }, { x: ha.x, y: ha.y, z: ha.z, duration: 1.6, ease: 'power2.inOut' }, go);
      tl.fromTo(cm.at, { x: ha.x, y: ha.y, z: ha.z }, { x: cm.home.x, y: cm.home.y, z: cm.home.z, duration: 0.01 }, z0 - 0.5);
    }
    // 航线：俯瞰时亮，进到各片里时变淡（不抢戏），对折和结尾时再亮
    var rb = this.splitT != null ? this.splitT - 0.2 : z0 - 1.0;
    [this.routeL, this.routeR].forEach(function (m) { U(m.material.uniforms.uFade, 1, 0.4, go + 1.0, 1.0); U(m.material.uniforms.uFade, 0.4, 1, rb, 1.0); });

    /* ---- 回到全图 ---- */
    Object.keys(chips).forEach(function (k, i) { show(chips[k], z0 + 0.2 + (k === (first && first.id) ? 0 : i * 0.12), 0.5); });
    this.pads.forEach(function (pd) { if (pd.side === 0) tl.fromTo(pd, { w: 0 }, { w: 0.8, duration: 0.8 }, z0 + 0.6); });
    ST(hud.end, { autoAlpha: 0, y: 16 });
    tl.fromTo(hud.end, { autoAlpha: 0, y: 16 }, { autoAlpha: 1, y: 0, duration: 0.8, ease: 'power3.out' }, z0);
    // 结尾那句总括：几个短语一行一个，旁白说到哪一句就出哪一行（close.l1…；没有就从 close.map 起每半秒一行）
    ST(hud.endHint, { autoAlpha: 1 });
    Array.prototype.forEach.call(hud.endLines, function (ln, i) {
      ST(ln, { autoAlpha: 0, y: 10 });
      tl.fromTo(ln, { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.5, ease: 'power3.out' }, T('close.l' + (i + 1), z0 + 1.0 + i * 0.5) - 0.1);
    });
    tl.fromTo(hud.kick, { autoAlpha: 1 }, { autoAlpha: 0, duration: 0.4 }, z0 - 0.2);
    tl.set({}, {}, d.duration + 0.5);

    /* ---- 镜头 ---- */
    var sh = this.shots, Q = this.Q.bind(this);
    // 章与章之间的飞行：在分界那条小节线（强拍）上起飞，落点对到最近的拍子上（不早于触发词前 0.25 秒）
    var fly = function (land, from, s, arc) {
      var t = Math.max(Q(land), land - 0.25);
      return { t: t, s: s, dur: Math.max(1.0, t - from), ease: 'io', arc: arc };
    };
    var keys = [{ t: 0, s: sh.start }, { t: omap + 0.4, s: sh.over, dur: 3.6, ease: 'io', arc: 6 }, { t: go, s: sh.over2, dur: 4.5, ease: 'sine' }];
    var settle = {};
    settle[open.id] = (ov.length ? ov[ov.length - 1] : omap) + 1.0;
    chs.forEach(function (c) {
      var real = c._real || []; if (!real.length) return;
      var ks = [], best = null, st = c.vs + 1;
      real.forEach(function (b, i) {
        var tp = TPL[b.type], bk = tp.cams.call(self, b) || [];
        if (i === 0 && bk.length) { var k0 = bk[0]; bk[0] = fly(k0.t, c.start, k0.s, k0.arc || 6); }
        bk.forEach(function (k) { k.b = b; });
        ks = ks.concat(bk);
        if (tp.settle) st = Math.max(st, tp.settle.call(self, b) || 0);
        var ex = tp.explore ? tp.explore.call(self, b) : null;
        if (ex && ex[1] && (!best || ex[0] >= best[0])) best = ex;
      });
      ks.sort(function (x, y) { return x.t - y.t; });
      tlImageHold(real, ks);
      keys = keys.concat(ks);
      settle[c.id] = st;
      self.exploreShots[c.id] = best ? best[1] : (ks.length ? ks[ks.length - 1].s : sh.close);
    });
    keys.push(fly(z0 + 1.0, close.start, sh.close, 4));
    keys.push({ t: d.duration + 1, s: sh.close, dur: 0.1 });
    this.camKeys(keys);
    // 每章"看完"的时刻（暂停时跳到那一章停在哪里；减少动态效果时的关键画面）
    settle[close.id] = d.duration - 0.05;
    chs.forEach(function (c) { c.settle = clamp(settle[c.id] != null ? settle[c.id] : c.end - 0.5, c.start + 0.2, c.end - 0.05); });
  };

  W.dust = function () {
    var n = this.low ? 360 : 720, g = new THREE.BufferGeometry(), pos = new Float32Array(n * 3), r = new Float32Array(n * 3);
    for (var i = 0; i < n; i++) {
      pos[i * 3] = (rnd(i + 1) - 0.5) * 120 + MAPC[0]; pos[i * 3 + 1] = 0.8 + Math.pow(rnd(i + 301), 1.6) * 30; pos[i * 3 + 2] = (rnd(i + 601) - 0.5) * 90 + MAPC[2];
      r[i * 3] = rnd(i + 901); r[i * 3 + 1] = rnd(i + 1201); r[i * 3 + 2] = rnd(i + 1501);
    }
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('aR', new THREE.BufferAttribute(r, 3));
    var col = this.pal.dark ? new THREE.Color('#ffe2b0') : this.pal.acc.clone().multiplyScalar(0.85);
    var m = new THREE.ShaderMaterial({ uniforms: { uTime: { value: 0 }, uSize: { value: this.pal.dark ? 2.4 : 1.7 }, uPR: { value: this.pr }, uCol: { value: col }, uFade: { value: this.pal.dark ? 0.9 : 0.22 } },
      vertexShader: DUST_V, fragmentShader: DOT_F, transparent: true, depthWrite: false, blending: this.pal.dark ? THREE.AdditiveBlending : THREE.NormalBlending });
    this.dustPts = new THREE.Points(g, m); this.dustPts.frustumCulled = false; this.scene.add(this.dustPts);
    this.dustPts.visible = this.pal.dark;   // 浅色背景上，景深一虚就像灰点：只在深色里放尘
    // 拖影：每粒尘一条短线，镜头飞得越快线越长
    var g2 = new THREE.BufferGeometry(), p2 = new Float32Array(n * 6), r2 = new Float32Array(n * 6), e2 = new Float32Array(n * 2);
    for (var j = 0; j < n; j++) for (var s = 0; s < 2; s++) { for (var c = 0; c < 3; c++) { p2[(j * 2 + s) * 3 + c] = pos[j * 3 + c]; r2[(j * 2 + s) * 3 + c] = r[j * 3 + c]; } e2[j * 2 + s] = s; }
    g2.setAttribute('position', new THREE.BufferAttribute(p2, 3)); g2.setAttribute('aR', new THREE.BufferAttribute(r2, 3)); g2.setAttribute('aEnd', new THREE.BufferAttribute(e2, 1));
    var m2 = new THREE.ShaderMaterial({ uniforms: { uTime: { value: 0 }, uVel: { value: new THREE.Vector3() }, uCol: { value: col.clone() }, uFade: { value: 0 } },
      vertexShader: STREAK_V, fragmentShader: STREAK_F, transparent: true, depthWrite: false, blending: this.pal.dark ? THREE.AdditiveBlending : THREE.NormalBlending });
    this.streaks = new THREE.LineSegments(g2, m2); this.streaks.frustumCulled = false; this.scene.add(this.streaks);
  };

  // 2.5D 视差配图（贴在世界里的一扇“窗”）
  W.photo = function (key, w, h, blur) {
    var info = (this.P.v.images || {})[key], pal = this.pal, self = this;
    var mat = new THREE.ShaderMaterial({
      uniforms: this.fogU({ uImg: { value: null }, uDep: { value: null }, uHasDep: { value: 0 }, uReveal: { value: 0 }, uFade: { value: 1 }, uShift: { value: new THREE.Vector2() },
        uZoom: { value: 1.06 }, uFocus: { value: 0.35 }, uEdge: { value: pal.acc.clone() }, uReady: { value: 0 }, uSize: { value: new THREE.Vector2(w, h) }, uBias: { value: blur || 0 } }),
      vertexShader: PHOTO_V, fragmentShader: PHOTO_F, transparent: true, depthWrite: false, fog: true
    });
    var m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), mat); m.renderOrder = 0; m.userData = { w: w, h: h, key: key };
    if (info) {
      var load = function (src, cb) { var im = new Image(); im.decoding = 'async'; im.onload = function () { cb(im); }; im.onerror = function () { cb(null); }; im.src = self.P.asset(src); };
      load(info.src, function (im) {
        if (!im) return;
        var t = new THREE.Texture(im); t.colorSpace = THREE.SRGBColorSpace; t.minFilter = THREE.LinearMipmapLinearFilter; t.generateMipmaps = true; t.needsUpdate = true;
        mat.uniforms.uImg.value = t; mat.uniforms.uReady.value = 1; self.P.dirty = true;
      });
      if (info.depth) load(info.depth, function (im) {
        if (!im) return;
        var t = new THREE.Texture(im); t.minFilter = THREE.LinearFilter; t.generateMipmaps = false; t.needsUpdate = true;
        mat.uniforms.uDep.value = t; mat.uniforms.uHasDep.value = 1; self.P.dirty = true;
      });
      // 画面里不挂“AI 生成配图”之类的小标：说明和署名统一写在文字稿面板的出处里（data.credits）
    }
    return m;
  };

  // 用画布把一串字画出来，取 n 个点（确定性的抽样）
  W.textPoints = function (str, n) {
    var cv = document.createElement('canvas'), w = 600, h = 200; cv.width = w; cv.height = h;
    var g = cv.getContext('2d'); g.fillStyle = '#000'; g.fillRect(0, 0, w, h); g.fillStyle = '#fff';
    g.font = '700 170px "FD Latin", "Times New Roman", Times, serif'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(str, w / 2, h / 2 + 8);
    var d = g.getImageData(0, 0, w, h).data, on = [];
    for (var y = 0; y < h; y += 2) for (var x = 0; x < w; x += 2) if (d[(y * w + x) * 4] > 128) on.push([x / w, y / h]);
    var out = [];
    for (var i = 0; i < n; i++) { var q = on.length ? on[Math.floor(rnd(i * 3.7 + 1.3) * on.length) % on.length] : [rnd(i), rnd(i + 9)]; out.push([q[0] + (rnd(i + 77) - 0.5) * 0.004, q[1] + (rnd(i + 99) - 0.5) * 0.01]); }
    return out;
  };

  // 数字滚动：标签里 span 的数从 a 滚到 b（按时间算，不是 setInterval）
  W.counter = function (lb, sel, a, b, at, dur, dec, fin) {
    var span = lb.el.querySelector(sel); if (!span) return;
    var c = { el: span, a: a, b: b, at: at, dur: dur, dec: dec, _s: '' };
    if (fin != null) { c.fin = String(fin); c.comma = c.fin.indexOf(',') >= 0; }    // 动效尝试：滚完显示原样的字（3200、1,200、80.52）
    else if (FX && span.getAttribute('data-f')) { c.fin = span.getAttribute('data-f'); c.comma = true; }     // 11-08：emph 记下的原样数字（带千位逗号）
    (this.counters || (this.counters = [])).push(c);
  };

  /* =================================================================== 每一帧 */
  W.update = function (t, wallT, opt) {
    var cam = this.camera, P = this.P, pal = this.pal;
    opt = opt || {};
    // 镜头
    var pos = this._pos || (this._pos = new THREE.Vector3()), tgt = this._tgt || (this._tgt = new THREE.Vector3());
    var fov = this.camAt(t, pos, tgt);
    if (P.exploreCam) { pos.copy(P.exploreCam.pos); tgt.copy(P.exploreCam.tgt); fov = P.exploreCam.fov || fov; }
    if (P.orbit && (P.orbit.yaw || P.orbit.pitch)) { // 暂停时拖动：绕目标转一点
      var off = pos.clone().sub(tgt), r = off.length(), yaw = Math.atan2(off.x, off.z) + P.orbit.yaw, pit = Math.asin(clamp(off.y / r, -1, 1)) + P.orbit.pitch;
      pit = clamp(pit, 0.05, 1.45);
      pos.set(tgt.x + Math.sin(yaw) * Math.cos(pit) * r, tgt.y + Math.sin(pit) * r, tgt.z + Math.cos(yaw) * Math.cos(pit) * r);
    }
    var prev = this._prevPos || (this._prevPos = pos.clone()), prevT = this._prevTgt || (this._prevTgt = tgt.clone());
    cam.position.copy(pos); cam.fov = fov; cam.updateProjectionMatrix(); cam.lookAt(tgt);
    cam.updateMatrixWorld();
    // 镜头速度 → 尘的拖影、整屏方向模糊（“动态模糊感”）
    var dtS = opt.dt != null ? opt.dt : 1 / 60, vel = this._vel || (this._vel = new THREE.Vector3());
    if (opt.jump || dtS <= 0) vel.set(0, 0, 0); else vel.copy(pos).sub(prev).divideScalar(Math.max(1 / 120, dtS));
    var speed = vel.length();
    if (this.streaks) { this.streaks.material.uniforms.uVel.value.copy(vel); this.streaks.material.uniforms.uFade.value = P.rm ? 0 : clamp((speed - 6) / 40, 0, 0.55); }
    if (this.fx) {
      var bl = this.fx.uniforms.get('uBlur').value;
      if (P.rm || opt.jump || speed < 8) bl.set(0, 0);
      else {
        // 目标点在屏幕上的移动方向（近似整屏的平移）
        var a = this.tmp.copy(prevT).project(cam), b2 = this.tmp2.copy(tgt);
        var c = b2.project(cam); var dx = (c.x - a.x) * 0.5, dy = (c.y - a.y) * 0.5;
        var k = clamp((speed - 8) / 60, 0, 1) * 0.6;
        var len = Math.hypot(dx, dy) + 1e-6, cap = 0.012 * k / Math.max(0.15, k);
        bl.set(clamp(dx * k, -cap, cap), clamp(dy * k, -cap, cap));
        if (len < 0.0004) bl.multiplyScalar(0);
      }
    }
    prev.copy(pos); prevT.copy(tgt);
    // 景深：对准镜头看的地方；开场先对在近处（地图是虚的），再拉焦到地图
    if (this.dof) {
      var rack = sat((t - 1.6) / 1.6);
      var near = this.tmp.copy(tgt).sub(pos).normalize().multiplyScalar(12).add(pos);
      this.focus.copy(near).lerp(tgt, P.exploreCam ? 1 : smooth(rack));
      var fd = pos.distanceTo(tgt);
      try { this.dof.cocMaterial.worldFocusRange = Math.max(3, fd * 0.42); } catch (e) { /* 旧版本没有这个属性 */ }
    }
    // 动的东西
    var wt = P.rm ? 0 : (wallT != null ? wallT : t), self = this;
    this.dustPts.material.uniforms.uTime.value = wt; this.streaks.material.uniforms.uTime.value = wt;
    var flow = P.rm ? 0 : t * 0.35;
    this.flowMeshes.forEach(function (m) { m.material.uniforms.uFlow.value = flow; });
    var sp = this.split ? this.split.v : 0;
    this.left.position.x = -sp * 7; this.right.position.x = sp * 7;
    this.gU.uSeam.value = sp * 0.6;
    this.gUL.uSeam.value = this.gUR.uSeam.value = sp * 0.6;
    this.gUL.uSeamX.value = this.gUR.uSeamX.value = SEAM;
    var pads = this.gUL.uPads.value;
    (this.pads || []).forEach(function (pd, i) { if (i < pads.length) pads[i].set(pd.x + pd.side * sp * 7, pd.z, pd.r, pd.w * (pal.dark ? 1.0 : 0.85)); });
    this.gUR.uPads.value = pads;
    if (this.fx) {
      this.fx.uniforms.get('uTear').value = P.rm ? 0 : (this.tear ? this.tear.v : 0);
      var sv = this.tmp.set(SEAM, 0, MAPC[2]).project(cam); this.fx.uniforms.get('uSeam').value = sv.x * 0.5 + 0.5;
    }
    // 玻璃的光泽扫过（按时间）
    var sheen = ((t * 0.16) % 1.6) - 0.3;
    this.glass.forEach(function (m) { m.material.uniforms.uSheen.value = sheen; });
    // 2.5D：镜头相对“窗”的位置 → 视差偏移
    this.photos.forEach(function (m) {
      var u = m.material.uniforms; if (!u.uReady.value) return;
      if (u.uReveal.value > 0.001) { var wp = m.getWorldPosition(self.tmp2); m.parent.updateMatrixWorld(); m.rotation.set(0, Math.atan2(cam.position.x - wp.x, cam.position.z - wp.z) - (m.parent.rotation ? m.parent.rotation.y : 0), 0); m.updateMatrixWorld(); }
      var lp = m.worldToLocal(self.tmp.copy(cam.position));
      var dz = Math.max(4, lp.z);
      u.uShift.value.set(clamp(lp.x / dz, -1.2, 1.2) * 0.05, clamp(-lp.y / dz, -1.2, 1.2) * 0.04);
      u.uZoom.value = 1.06 + clamp(12 / dz, 0, 1) * 0.04;
    });
    // 各模板每一帧要算的东西（价位块的虚线、传播链、点阵、图表、抖动）
    this.blocks.forEach(function (b) { var f = TPL[b.type].frame; if (f) f.call(self, b, t); });
    // 章与章之间飞过去的小方块
    this.cubes.forEach(function (h) {
      if (h.t0 != null && t > h.t0 && t < h.t1 + 0.5) {
        var u2 = sat((t - h.t0) / Math.max(0.1, h.t1 - h.t0)), e = inOut(u2), ea = h.from._.exitAt, eb = h.to._.enterAt;
        var from = h.from._.g.localToWorld(self.tmp.set(ea.x, ea.y, ea.z));
        var to = h.to._.enterWorld ? h.to._.enterWorld(self.tmp2) : h.to._.g.localToWorld(self.tmp2.set(eb.x, eb.y, eb.z));
        var mid = from.clone().lerp(to, 0.5); mid.y += 7;
        var q = new THREE.Vector3().copy(from).multiplyScalar((1 - e) * (1 - e)).addScaledVector(mid, 2 * (1 - e) * e).addScaledVector(to, e * e);
        h.cube.position.copy(q); h.cube.rotation.set(t * 2.1, t * 1.7, 0); h.cube.visible = u2 < 1;
        h.cube.scale.setScalar(u2 < 1 ? 1 - sat((u2 - 0.85) / 0.15) * 0.7 : 0.001);
        h.glow.position.copy(q); h.glow.material.opacity = u2 < 1 ? 0.8 : sat(1 - (t - h.t1) / 0.5) * 0.8;
      } else { h.cube.visible = false; h.glow.material.opacity = 0; }
    });
    // 数字滚动
    (this.counters || []).forEach(function (c) {
      var u3 = sat((t - c.at) / c.dur), v = lerp(c.a, c.b, out3(u3)), str;
      if (c.dec) str = (v < 0 ? '−' : '') + Math.abs(v).toFixed(c.dec); else str = String(Math.round(v));
      if (c.comma) str = str.replace(/^(\D*)(\d+)/, function (m0, s0, d0) { return s0 + d0.replace(/\B(?=(\d{3})+(?!\d))/g, ','); });
      if (u3 >= 1) str = c.fin != null ? c.fin : (c.dec ? (c.b < 0 ? '−' : '') + Math.abs(c.b).toFixed(c.dec) : String(Math.round(c.b)));
      if (str !== c._s) { c.el.textContent = str; c._s = str; }
    });
    // 标志小签轻轻浮动（按时间算；减少动态效果时不动）
    (this.floaters || []).forEach(function (lb) { if (lb.a > 0.003) lb.at.y = lb.bob.y + (P.rm ? 0 : Math.sin(t * 1.15 + lb.bob.ph) * lb.bob.amp); });
    this.updateLabels();
    if (this.tlPops) this.tlPopFrame();          // 结合式：时间轴日子上弹出的截图（分镜没写 ticks[].shot 时没有这一步）
  };

  W.draw = function (dt) { this.comp.render(dt || 1 / 60); };

  W.resize = function (w, h) {
    this.renderer.setSize(w, h, false);
    this.comp.setSize(w, h);
    this.camera.aspect = w / Math.max(1, h); this.camera.updateProjectionMatrix();
    if (this.ck) this.layoutCams();
    (this.charts || []).forEach(function (c) { try { c.resize(); } catch (e) { /* ignore */ } });
  };

  W.setTheme = function (dark) {
    var old = this.pal; this.pal = this.palette(dark); var pal = this.pal;
    this.scene.background.set(pal.bg); this.scene.fog.color.set(pal.bg);
    this.gUL.uBg.value.set(pal.bg); this.gUL.uDot.value.set(pal.dot); this.gUL.uDotA.value = pal.dotA; this.gUL.uGlow.value.copy(pal.glow);
    if (this.bloom) { this.bloom.luminanceMaterial.threshold = dark ? 0.62 : 0.96; this.bloom.intensity = dark ? 1.25 : 0.85; }
    if (this.vig) this.vig.darkness = dark ? 0.55 : 0.24;
    this.scene.traverse(function (o) {
      var u = o.material && o.material.uniforms; if (!u) return;
      if (u.uTint && u.uTop) { u.uTint.value.copy(pal.glass); u.uTop.value.copy(pal.glassTop); }
      else if (u.uTint && u.uRim) { u.uTint.value.copy(pal.glass); }
    });
    (this.blocks || []).forEach(function (b) { var o = b._ && b._.o; if (o && o.chart) { try { o.chart.dispose(); } catch (e) { /* ignore */ } o.chart = null; o._key = null; } }); this.charts = [];
    return old;
  };

  W.dispose = function () {
    (this.charts || []).forEach(function (c) { try { c.dispose(); } catch (e) { /* ignore */ } });
    this.scene.traverse(function (o) { if (o.geometry) o.geometry.dispose(); if (o.material) { if (o.material.map) o.material.map.dispose(); o.material.dispose(); } });
    try { this.comp.dispose(); } catch (e) { /* ignore */ }
    this.renderer.dispose();
    if (this.tl) this.tl.kill();
  };

  /* =================================================================== 播放器 */
  function Player(root, video, ctx) {
    this.root = root; this.v = video || {}; this.ctx = ctx || {};
    FX = !!this.v.fix1108;
    this.wb = wbIndex(this.v.zhwrap);     // 11-09 中文整词换行的对照表；数据里没有就是 null，什么都不做
    this.L = this.ctx.lang ? (this.ctx.lang() === 'en' ? 'en' : 'zh') : 'zh';
    this.T = I18N[this.L] || I18N.zh;
    this.chapters = (this.v.chapters || []).map(function (c) { return c; });
    this.scenes = this.chapters.map(function (c) { return { start: c.start, end: c.end }; }); // app.js 的“看这一段”按它跳
    this.cues = this.v.cues || [];
    this.duration = +this.v.duration || 1;
    this.t = 0; this.base = 0; this.at = 0; this.playing = false; this.started = false; this.ended = false;
    this.cc = this.store('fd.video.cc', '1') !== '0';
    this.rm = !!(MQ && MQ.matches);
    this.dark = this.isDark();
    this.accRGB = this.readAccent();
    this.low = this.isLow();
    this.orbit = { yaw: 0, pitch: 0 };
    this.build();
    this.initAudio();
    this.bind();
    this.syncUI();
    this.renderUI(0);
    if (this.ctx.eager || this.ctx.static) this.ensureWorld(); else this.lazy();
  }
  var P = Player.prototype;
  P.store = function (k, d) { try { return this.ctx.store ? this.ctx.store.get(k, d) : d; } catch (e) { return d; } };
  P.asset = function (p) { return this.ctx.asset ? this.ctx.asset(p) : p; };
  P.isDark = function () {
    var dt = document.documentElement.getAttribute('data-theme');
    return dt === 'dark' || (dt !== 'light' && !!(MQD && MQD.matches));
  };
  P.readAccent = function () {
    var s = '';
    try { s = getComputedStyle(this.root).getPropertyValue('--accent-rgb').trim(); } catch (e) { /* ignore */ }
    var m = s.match(/(\d+)[ ,]+(\d+)[ ,]+(\d+)/);
    if (m) return [+m[1], +m[2], +m[3]];
    return { blue: [0, 113, 227], amber: [232, 140, 20], coral: [232, 92, 68], violet: [125, 79, 224] }[this.v.accent || 'amber'] || [232, 140, 20];
  };
  P.isLow = function () {
    var w = window.innerWidth || 1280, mem = navigator.deviceMemory || 8, cores = navigator.hardwareConcurrency || 8;
    return w < 700 || mem <= 3 || cores <= 4;
  };
  P.useAudio = function () { return !!this.audio && this.audioState !== 'error' && !this.userSilent; };
  P.now = function () {
    if (this.useAudio() && this.playing) return this.audio.currentTime || 0;
    if (!this.playing) return this.t;
    return this.base + (performance.now() - this.at) / 1000;
  };

  P.build = function () {
    var T = this.T, self = this, d = this.v, L = this.L;
    this.root.innerHTML =
      '<div class="v3p' + (L === 'en' ? ' en' : '') + '" tabindex="0" role="region">' +
        '<div class="v3stage">' +
          '<canvas class="v3gl" aria-hidden="true"></canvas>' +
          '<div class="v3poster" aria-hidden="true"></div>' +
          '<div class="v3world" aria-hidden="true"></div>' +
          '<div class="v3hud" aria-hidden="true">' +
            (FX ? '<div class="v3cover"><i class="im"></i><i class="gr"></i></div>' : '') +
            '<div class="v3kick"><b></b><span></span></div>' +
            '<div class="v3title"></div>' +
            '<div class="v3end"><div class="t"></div><div class="h"></div></div>' +
          '</div>' +
          '<div class="v3sub" aria-live="off"></div>' +
          '<div class="v3note v3glass" role="dialog" hidden></div>' +
          '<div class="v3over"><div class="v3over-in"><button class="v3big" type="button"></button><span class="v3over-meta"></span></div></div>' +
        '</div>' +
        '<div class="v3ctl">' +
          '<div class="v3scrub"><input type="range" min="0" step="0.05" value="0"><div class="v3ticks" aria-hidden="true"></div></div>' +
          '<div class="v3row">' +
            '<button class="v3btn" type="button" data-act="play"></button>' +
            '<button class="v3btn" type="button" data-act="prev">' + ICON.prev + '</button>' +
            '<button class="v3btn" type="button" data-act="next">' + ICON.next + '</button>' +
            '<span class="v3time"></span><span class="v3sp"></span>' +
            '<button class="v3txtbtn" type="button" data-act="explore"></button>' +
            '<button class="v3txtbtn" type="button" data-act="tr"></button>' +
            '<button class="v3btn" type="button" data-act="cc">' + ICON.cc + '</button>' +
            '<button class="v3btn" type="button" data-act="silent"></button>' +
            '<button class="v3btn" type="button" data-act="full">' + ICON.full + '</button>' +
          '</div>' +
        '</div>' +
        '<div class="v3pgr"><div class="v3pager" role="tablist"></div><span class="count" aria-hidden="true"><b>1</b><span class="sl">/</span><span class="vn"></span></span></div>' +
        '<div class="v3tr" hidden></div>' +
      '</div>';
    var q = this.root.querySelector.bind(this.root);
    this.wrap = q('.v3p'); this.stage = q('.v3stage'); this.canvas = q('.v3gl'); this.worldEl = q('.v3world'); this.hudEl = q('.v3hud');
    this.subEl = q('.v3sub'); this.noteEl = q('.v3note'); this.over = q('.v3over'); this.big = q('.v3big'); this.overMeta = q('.v3over-meta');
    this.range = q('.v3scrub input'); this.ticksEl = q('.v3ticks'); this.timeEl = q('.v3time'); this.pagerEl = q('.v3pager'); this.countEl = q('.v3pgr .count b');
    this.trEl = q('.v3tr');
    // 标志的遮罩图：每个标志一条样式（data: 地址，构建时嵌进来，不向外网要东西）
    var lgs = d.logos || {}, css = Object.keys(lgs).filter(function (k) { return lgs[k].m && /^[a-z0-9_-]+$/.test(k); }).map(function (k) {
      return '.v3logo[data-logo="' + k + '"] .mk{-webkit-mask-image:url("' + lgs[k].m + '");mask-image:url("' + lgs[k].m + '")}';
    }).join('\n');
    if (css) { var st = document.createElement('style'); st.textContent = css; this.wrap.appendChild(st); }
    q('.v3pgr .vn').textContent = String(this.chapters.length);
    this.wrap.classList.toggle('dark', this.dark);
    this.wrap.classList.toggle('reduced', this.rm);
    this.wrap.classList.toggle('lowfx', this.low);
    this.btn = {};
    this.root.querySelectorAll('[data-act]').forEach(function (b) { self.btn[b.dataset.act] = b; });
    this.range.max = String(this.duration);
    this.stage.id = 'v3stage-' + Math.random().toString(36).slice(2, 8);
    // 片头大字、结尾字
    var S = function (k) { return tx((d.S || {})[k], L); };
    var sweep = function (s) { return esc(s) + '<i class="v3sweep" aria-hidden="true">' + esc(s) + '</i>'; };
    q('.v3title').innerHTML = '<span class="ln"><span class="d v3n">' + sweep(S('title.date')) + '</span></span>' +
      '<span class="ln"><span class="m">' + sweep(S('title.main')) + '</span></span><span class="ln"><span class="s">' + esc(S('title.line')) + '</span></span><i class="rule"></i>';
    q('.v3end .t').textContent = S('close.title');
    q('.v3end .h').innerHTML = S('close.hint').split(/\s*·\s*/).filter(Boolean).map(function (x) { return '<span class="ln">' + esc(x) + '</span>'; }).join('');
    if (this.wb) { wbWalk(this.wb, q('.v3title'), false); wbWalk(this.wb, q('.v3end'), false); }     // 11-09：中文整词换行
    var cov = q('.v3cover'), covInfo = FX && d.cover ? (d.images || {})[d.cover] : null;     // 11-08（K42）：封面图，标题压在左侧渐变上
    if (cov && covInfo) cov.querySelector('.im').style.backgroundImage = 'url("' + this.asset(covInfo.src) + '")'; else if (cov) { cov.parentNode.removeChild(cov); cov = null; }
    if (FX) this.wrap.classList.add('fx1108');
    this.hud = { cover: cov, title: q('.v3title'), lines: q('.v3title').querySelectorAll('.ln > span'), rule: q('.v3title .rule'), sweeps: q('.v3title').querySelectorAll('.v3sweep'),
      kick: q('.v3kick'), end: q('.v3end'), endHint: q('.v3end .h'), endLines: q('.v3end .h').querySelectorAll('.ln') };
    // 画面上不放标注、不放操作提示（11-01 用户定去掉“AI 合成语音”角标；暂停时鼠标变成“手”，拖动可转视角）
    // 分章页签
    this.chips = this.chapters.map(function (c, i) {
      var lab = tx(c.label, L);
      var b = el('button', 'pg', '<span class="pg-fill" aria-hidden="true"></span><span class="pg-n">' + (i + 1) + '</span><span class="pg-t">' + esc(lab) + '</span>');
      b.type = 'button'; b.setAttribute('role', 'tab'); b.setAttribute('aria-selected', 'false'); b.tabIndex = i ? -1 : 0; b.setAttribute('aria-controls', self.stage.id);
      b.title = lab + ' · ' + fmt(c.start);
      b.addEventListener('click', function () { self.gotoChapter(i); });
      b.addEventListener('keydown', function (e) {
        var k = e.key, j = null;
        if (k === 'ArrowRight' || k === 'ArrowDown') j = i + 1; else if (k === 'ArrowLeft' || k === 'ArrowUp') j = i - 1; else if (k === 'Home') j = 0; else if (k === 'End') j = self.chips.length - 1;
        if (j === null) return;
        e.preventDefault(); e.stopPropagation(); j = clamp(j, 0, self.chips.length - 1); self.gotoChapter(j); self.chips[j].focus();
      });
      self.pagerEl.appendChild(b);
      if (i) { var tk = el('i'); tk.style.left = (c.start / self.duration * 100) + '%'; self.ticksEl.appendChild(tk); }
      return b;
    });
    // 文字稿
    var trH = '<h4>' + esc(T.transcript) + '</h4>' + (this.rm ? '<p class="note">' + esc(T.reduced) + '</p>' : '') + '<ol>' +
      (d.transcript || []).map(function (s, i) { return '<li data-i="' + i + '" data-t="' + s.start + '"><b>' + fmt(s.start) + '</b><span>' + esc(s.text) + '</span></li>'; }).join('') + '</ol>' +
      // 出处与署名：配乐、视频配图（AI 生成／资料图的署名）、标志来源；构建时写好在 data.credits.lines（旧数据只有 music.credit）
      ((d.credits && d.credits.lines) ? d.credits.lines.map(function (ln) { return '<p class="credit">' + esc(tx(ln, L)) + '</p>'; }).join('') :
        (d.music && d.music.credit ? '<p class="credit">' + esc(tx(d.music.credit, L)) + '</p>' : ''));
    this.trEl.innerHTML = trH;
    if (this.wb) wbWalk(this.wb, this.trEl, false);
    this.trItems = this.trEl.querySelectorAll('li');
    if (this.rm) this.trEl.hidden = false;
    this.layout();
  };

  P.layout = function () {
    var w = this.stage.clientWidth || 960;
    var portrait = (window.innerWidth || w) < 640;
    this.wrap.classList.toggle('portrait', portrait);
    this.sw = this.stage.clientWidth || 960; this.sh = this.stage.clientHeight || 540;
  };

  P.lazy = function () {
    var self = this;
    if (!('IntersectionObserver' in window)) { this.ensureWorld(); return; }
    this.io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (e.isIntersecting) self.ensureWorld();
      });
    }, { rootMargin: '300px 0px 300px 0px' });
    this.io.observe(this.stage);
  };

  P.ensureWorld = function () {
    if (this.world || this.noGL) return !!this.world;
    if (!window.THREE || !window.POSTPROCESSING || !window.gsap) { this.failGL(); return false; }
    try {
      this.world = new World(this);
      this.world.initAll();
      this.world.timeline();
    } catch (e) {
      console.warn('[video3] 三维场景建不起来，改用文字版', e);
      try { if (this.world) this.world.dispose(); } catch (e2) { /* ignore */ }
      this.world = null; this.worldEl.innerHTML = ''; this.failGL(); return false;
    }
    this.wrap.classList.add('ready');
    this.onResize();
    this.watchVisible();
    this.syncUI();
    this.render(true);
    return true;
  };
  // 按正确顺序初始化：渲染器 → 镜头定义 → 搭场景 → 后期
  W.initAll = function () {
    var P = this.P;
    var r = this.renderer = new THREE.WebGLRenderer({ canvas: P.canvas, antialias: false, alpha: false, powerPreference: 'high-performance', stencil: false });
    this.pr = Math.min(1.5, window.devicePixelRatio || 1);
    r.setPixelRatio(this.pr); r.outputColorSpace = THREE.SRGBColorSpace; r.toneMapping = THREE.NoToneMapping;
    this.low = P.low;
    var sc = this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(34, (P.sw || 16) / (P.sh || 9), 0.2, 520);
    this.pal = this.palette(P.dark);
    sc.background = new THREE.Color(this.pal.bg);
    sc.fog = new THREE.Fog(this.pal.bg, 150, 330);
    sc.add(new THREE.HemisphereLight(0xffffff, this.pal.dark ? 0x221a12 : 0xd9ccb8, this.pal.dark ? 0.7 : 0.5));
    var dl = new THREE.DirectionalLight(0xffffff, this.pal.dark ? 1.1 : 0.75); dl.position.set(-20, 40, 30); sc.add(dl);
    try { var pm = new THREE.PMREMGenerator(r); sc.environment = pm.fromScene(new THREE.RoomEnvironment(), 0.04).texture; sc.environmentIntensity = this.pal.dark ? 0.9 : 0.45; pm.dispose(); } catch (e) { /* 可有可无 */ }
    this.glowTex = this.makeGlow();
    this.defineShots();
    this.build();
    this.post();
  };

  P.failGL = function () {
    this.noGL = true;
    this.wrap.classList.add('nogl');
    var T = this.T, d = this.v, L = this.L;
    var poster = this.stage.querySelector('.v3poster');
    poster.innerHTML = '<div style="position:absolute;inset:0;display:grid;place-items:center;padding:6cqw;text-align:center;font:400 clamp(13px,1.6cqw,18px)/1.6 var(--v3-body);color:var(--v3-ink2)">' + esc(T.no_gl) + '</div>';
    this.trEl.hidden = false;
    var keys = '<h4>' + esc(T.chapters) + '</h4><ol>' + (d.clusters || []).map(function (c) {
      return '<li><b>' + esc(tx(c.name, L)) + '</b><span>' + (c.note || []).map(function (n) { return esc(tx(n, L)); }).join(' ') + '</span></li>';
    }).join('') + '</ol>';
    var k = el('div', '', keys); this.trEl.insertBefore(k, this.trEl.firstChild);
  };

  P.watchVisible = function () {
    var self = this;
    if ('IntersectionObserver' in window) {
      this.vio = new IntersectionObserver(function (es) {
        es.forEach(function (e) { self.visible = e.isIntersecting; if (!e.isIntersecting && self.playing) self.pause(); });
      }, { threshold: 0.12 });
      this.vio.observe(this.stage);
    }
    if (!this._onVis) {
      this._onVis = function () { if (document.hidden && self.playing) self.pause(); };
      document.addEventListener('visibilitychange', this._onVis);
    }
  };

  /* ---------- 音频 ---------- */
  P.initAudio = function () {
    var self = this, src = this.v.audio ? this.asset(this.v.audio) : '';
    if (!src) { this.audioState = 'error'; return; }
    var a = this.audio = new Audio(); a.preload = 'metadata'; this.audioState = 'loading';
    a.addEventListener('loadedmetadata', function () { self.audioState = 'ok'; self.syncUI(); });
    a.addEventListener('error', function () { self.fallbackSilent(); });
    a.addEventListener('ended', function () { if (self.useAudio() && self.playing) self.finish(); });
    a.addEventListener('pause', function () { if (self.playing && self.useAudio() && !a.ended && !self._seeking) { self.t = a.currentTime; self.playing = false; self.syncUI(); self.render(); } });
    a.src = src;
  };
  P.fallbackSilent = function () {
    this.audioState = 'error'; this.base = this.t; this.at = performance.now();
    if (this.audio) { try { this.audio.pause(); } catch (e) { /* ignore */ } }
    if (this.playing) this.kick();
    this.syncUI();
  };

  /* ---------- 播放控制 ---------- */
  P.play = function () {
    var self = this;
    if (!this.world && !this.noGL) this.ensureWorld();
    this.exitExplore(true);
    if (this.ended || this.t >= this.duration - 0.05) { this.t = 0; this.ended = false; }
    this.started = true; this.playing = true; this.orbitBack();
    if (this.useAudio()) {
      try { this.audio.currentTime = this.t; } catch (e) { /* not ready */ }
      var pr = this.audio.play();
      if (pr && pr.catch) pr.catch(function (err) {
        if (!self.playing) return;
        if (err && err.name === 'NotAllowedError') { self.playing = false; self.syncUI(); return; }
        if (err && err.name === 'AbortError') return;
        self.fallbackSilent();
      });
    }
    this.base = this.t; this.at = performance.now();
    document.dispatchEvent(new CustomEvent('fd:play', { detail: { id: 'video' } }));
    this.kick(); this.syncUI();
  };
  P.pause = function () {
    if (!this.playing) return;
    this.t = clamp(this.now(), 0, this.duration); this.playing = false;
    if (this.audio && !this.audio.paused) this.audio.pause();
    this.syncUI(); this.render();
  };
  P.toggle = function () { if (this.playing) this.pause(); else this.play(); };
  P.seek = function (t) {
    this.t = clamp(t, 0, this.duration); this.ended = false; this.started = true;
    if (this.useAudio()) { try { this._seeking = true; this.audio.currentTime = this.t; } catch (e) { /* ignore */ } this._seeking = false; }
    this.base = this.t; this.at = performance.now(); this._jump = true;
    this.render(); this.syncUI();
  };
  P.kick = function () {
    var self = this; if (this.raf) return;
    var step = function () {
      self.raf = 0;
      if (!self.playing && !self.animating) return;
      if (self.playing) {
        var t = self.now();
        if (t >= self.duration) { self.t = self.duration; self.finish(); return; }
        self.t = t;
      }
      self.render();
      self.raf = requestAnimationFrame(step);
    };
    this.raf = requestAnimationFrame(step);
  };
  P.finish = function () { this.playing = false; this.ended = true; if (this.audio && !this.audio.paused) this.audio.pause(); this.render(); this.syncUI(); this.enterExplore(); };
  P.chapterAt = function (t) { var i = 0; for (var k = 0; k < this.chapters.length; k++) if (this.chapters[k].start <= t + 1e-6) i = k; return i; };
  P.sceneAt = P.chapterAt;
  P.gotoChapter = function (i) {
    i = clamp(i, 0, this.chapters.length - 1); var c = this.chapters[i];
    this.exitExplore(true);
    this.seek(this.playing ? c.start + 0.01 : (c.settle || c.start + 0.5));
  };
  P.gotoScene = P.gotoChapter;
  P.step = function (dir) {
    var t = this.started ? this.t : 0, cur = this.chapterAt(t);
    if (dir < 0 && this.playing && t - this.chapters[cur].start > 1.5) { this.gotoChapter(cur); return; }
    this.gotoChapter(cur + dir);
  };
  P.toggleSilent = function () {
    if (!this.audio || this.audioState === 'error') return;
    var was = this.playing, t = was ? this.now() : this.t;
    if (was) { this.playing = false; if (!this.audio.paused) this.audio.pause(); }
    this.userSilent = !this.userSilent; this.t = t;
    if (was) this.play(); else { this.render(); this.syncUI(); }
  };
  P.toggleCC = function () { this.cc = !this.cc; try { if (this.ctx.store) this.ctx.store.set('fd.video.cc', this.cc ? '1' : '0'); } catch (e) { /* ignore */ } this._cue = undefined; this.syncUI(); this.render(); };
  P.toggleTr = function () { this.trEl.hidden = !this.trEl.hidden; this.syncUI(); };
  P.toggleFull = function () {
    var d = document;
    if (d.fullscreenElement || d.webkitFullscreenElement) { (d.exitFullscreen || d.webkitExitFullscreen).call(d); return; }
    var w = this.wrap, req = w.requestFullscreen || w.webkitRequestFullscreen;
    if (req && (d.fullscreenEnabled || d.webkitFullscreenEnabled)) { try { var r = req.call(w); if (r && r.catch) r.catch(function () { w.classList.toggle('zoom'); }); } catch (e) { w.classList.toggle('zoom'); } }
    else w.classList.toggle('zoom');
  };

  /* ---------- 自由看图：点一片，镜头飞过去，右边出出处卡 ---------- */
  P.enterExplore = function () {
    if (!this.world) return;
    this.exploring = true; this.wrap.classList.add('exploring');
    var self = this, chips = this.world.chips;
    Object.keys(chips).forEach(function (k) {
      var lb = chips[k]; lb.a = 1; lb.btn.classList.add('btn'); lb.btn.tabIndex = 0; lb.el.style.pointerEvents = 'auto';
      if (!lb._bound) { lb._bound = true; lb.btn.addEventListener('click', function (e) { e.stopPropagation(); self.explore(k); }); }
    });
    this.render(); this.syncUI();
  };
  // 自由看图时，热点卡一直在原位、可以点（时间轴在别的时刻会把它们藏起来，这里盖过去）
  P.applyExplore = function () {
    var chips = this.world.chips, sel = this.exploreSel;
    Object.keys(chips).forEach(function (k) { var lb = chips[k]; lb.at.copy(lb.home); lb.a = sel ? 0 : 1; lb.el.style.pointerEvents = sel ? 'none' : 'auto'; });
  };
  P.exitExplore = function (silent) {
    if (!this.exploring && !this.exploreCam) return;
    this.exploring = false; this.exploreCam = null; this.exploreT = null; this.exploreSel = null; this.wrap.classList.remove('exploring');
    this.noteEl.hidden = true;
    var chips = this.world ? this.world.chips : {};
    Object.keys(chips).forEach(function (k) { var lb = chips[k]; lb.btn.classList.remove('btn', 'on'); lb.btn.tabIndex = -1; lb.el.style.pointerEvents = ''; });
    if (!silent) this.render();
  };
  P.explore = function (id) {
    var W0 = this.world, self = this; if (!W0) return;
    var c = (this.v.clusters || []).filter(function (x) { return x.id === id; })[0]; if (!c) return;
    var chI = this.chapters.map(function (x) { return x.id; }).indexOf(c.ch);
    var ch = this.chapters[chI];
    var s = (W0.exploreShots || {})[c.ch || c.id] || W0.shots.close;   // 每章“看全”的那一镜（模板里定）
    var to = { pos: W0.shotPos(s), tgt: W0.shotC(s).clone(), fov: s.fov };
    var from = { pos: W0.camera.position.clone(), tgt: W0._tgt ? W0._tgt.clone() : W0.shotC(s).clone(), fov: W0.camera.fov };
    this.exploreT = ch ? ch.settle : this.duration;
    this.exploreCam = { pos: from.pos.clone(), tgt: from.tgt.clone(), fov: from.fov };
    this.exploreSel = id;
    Object.keys(W0.chips).forEach(function (k) { W0.chips[k].btn.classList.toggle('on', k === id); });
    var o = { u: 0 };
    this.animating = true; this.kick();
    window.gsap.to(o, { u: 1, duration: this.rm ? 0.01 : 1.3, ease: 'power3.inOut', onUpdate: function () {
      self.exploreCam.pos.copy(from.pos).lerp(to.pos, o.u); self.exploreCam.tgt.copy(from.tgt).lerp(to.tgt, o.u);
    }, onComplete: function () { self.animating = false; self.render(); } });
    this.showNote(c);
  };
  P.showNote = function (c) {
    var self = this, T = this.T, L = this.L, src = this.v.sources || {};
    var cite = function (sid) {
      var s = src[sid]; if (!s) return '';
      var n = self.citeNo(sid, s);
      return '<button type="button" data-src="' + esc(sid) + '" title="' + esc(s.name + (s.title ? ' · ' + s.title : '')) + '">[' + n + ']</button>';
    };
    this.noteEl.innerHTML = '<button type="button" class="x" aria-label="' + esc(T.close) + '">✕</button><span class="lbl">' + esc(T.note_lbl) + '</span><h3>' + esc(tx(c.name, L)) + '</h3>' +
      (c.note || []).map(function (n) { return '<p>' + esc(tx(n, L)) + ' ' + '<span class="srcl" style="display:inline-flex">' + (n.src || []).map(cite).join('') + '</span></p>'; }).join('') +
      '<div><span class="lbl">' + esc(T.sources) + '</span><div class="srcl" style="margin-top:.4em">' + (c.src || []).map(cite).join('') + '</div></div>' +
      '<button type="button" class="bk">' + esc(T.back) + '</button>';
    if (this.wb) wbWalk(this.wb, this.noteEl, false);
    this.noteEl.hidden = false;
    this.noteEl.querySelector('.x').addEventListener('click', function (e) { e.stopPropagation(); self.backToMap(); });
    this.noteEl.querySelector('.bk').addEventListener('click', function (e) { e.stopPropagation(); self.backToMap(); });
    this.noteEl.querySelectorAll('[data-src]').forEach(function (b) {
      b.addEventListener('click', function (e) { e.stopPropagation(); self.jumpSource(b.getAttribute('data-src')); });
    });
    this.noteEl.addEventListener('click', function (e) { e.stopPropagation(); });
  };
  // 来源编号：主页面里沿用网页正文的 [n]（读页面上第一处引用）；单独的演示页用场景数据里的编号
  P.citeNo = function (sid, s) {
    try {
      var a = document.querySelector('sup.cite[data-s="' + sid + '"] a');
      var m = a && a.textContent.match(/\d+/); if (m) return m[0];
    } catch (e) { /* ignore */ }
    return s && s.n ? s.n : '?';
  };
  P.jumpSource = function (sid) {
    if (this.ctx.jumpSource) { this.ctx.jumpSource(sid); return; }
    if (window.FD && window.FD.jumpSource) { window.FD.jumpSource(sid); return; }
    var li = document.getElementById('src-' + sid); if (li) li.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };
  P.backToMap = function () {
    var W0 = this.world, self = this; if (!W0) return;
    this.noteEl.hidden = true;
    var s = W0.shots.close, to = { pos: W0.shotPos(s), tgt: W0.shotC(s).clone() };
    var from = this.exploreCam ? { pos: this.exploreCam.pos.clone(), tgt: this.exploreCam.tgt.clone() } : { pos: W0.camera.position.clone(), tgt: W0.shotC(s).clone() };
    this.exploreSel = null;
    Object.keys(W0.chips).forEach(function (k) { W0.chips[k].btn.classList.remove('on'); });
    var o = { u: 0 }; this.animating = true; this.kick();
    window.gsap.to(o, { u: 1, duration: this.rm ? 0.01 : 1.2, ease: 'power3.inOut', onUpdate: function () {
      if (!self.exploreCam) return; self.exploreCam.pos.copy(from.pos).lerp(to.pos, o.u); self.exploreCam.tgt.copy(from.tgt).lerp(to.tgt, o.u);
    }, onComplete: function () { self.animating = false; self.exploreT = self.duration; self.render(); } });
    this.exploreT = this.duration;
  };

  /* ---------- 暂停时拖动转视角 ---------- */
  P.orbitBack = function () {
    var o = this.orbit, self = this; if (!o.yaw && !o.pitch) return;
    if (window.gsap) window.gsap.to(o, { yaw: 0, pitch: 0, duration: 0.6, ease: 'power2.out', onUpdate: function () { if (!self.playing) self.render(); } });
    else { o.yaw = 0; o.pitch = 0; }
  };

  /* ---------- 每一帧：画面＋字幕＋进度 ---------- */
  P.posterT = function () { var T0 = (this.v.T || {})['open.map']; return typeof T0 === 'number' ? T0 + 0.3 : 4; };
  P.shownT = function () { return this.started ? this.t : this.posterT(); };
  P.render = function (first) {
    var t = this.shownT();
    var wt = t;
    if (this.exploreT != null && !this.playing) wt = this.exploreT;
    if (this.rm && this.chapters.length) { var c = this.chapters[this.chapterAt(t)]; wt = this.exploreT != null && !this.playing ? wt : (c.settle || c.start); }
    var W0 = this.world;
    if (W0 && !this.noGL) {
      var now = performance.now(), dt = this._lastWall ? (now - this._lastWall) / 1000 : 1 / 60; this._lastWall = now;
      if (W0.tl) W0.tl.time(Math.min(wt, this.duration + 0.4));
      if (this.exploring) this.applyExplore();
      var jump = !!(first || this._jump || this.rm || !this.playing);
      this._jump = false;
      var simDt = this.playing ? (wt - (this._lastT == null ? wt : this._lastT)) : 0;
      this._lastT = wt;
      W0.update(wt, this.rm ? 0 : (this.playing ? wt : wt), { dt: simDt > 0 && simDt < 0.25 ? simDt : 0, jump: jump });
      W0.draw(dt);
    }
    this.renderUI(t);
  };
  P.renderUI = function (t) {
    var shown = this.started ? t : 0, ci = this.chapterAt(shown), T = this.T, L = this.L;
    if (ci !== this._ci) {
      var self = this;
      this.chips.forEach(function (b, k) { var on = k === ci; b.classList.toggle('on', on); b.setAttribute('aria-selected', on ? 'true' : 'false'); b.tabIndex = on ? 0 : -1; if (!on) b.style.removeProperty('--f'); });
      if (this.countEl) this.countEl.textContent = String(ci + 1);
      var c = this.chapters[ci];
      if (c && this.hud) { this.hud.kick.querySelector('b').textContent = pad2(ci + 1) + ' / ' + pad2(this.chapters.length); this.hud.kick.querySelector('span').textContent = tx(c.label, L); }
      var chip = this.chips[ci], ps = this.pagerEl;
      if (chip && ps.scrollWidth > ps.clientWidth) { var left = chip.offsetLeft - ps.clientWidth / 2 + chip.offsetWidth / 2; try { ps.scrollTo({ left: left, behavior: self.playing ? 'smooth' : 'auto' }); } catch (e) { ps.scrollLeft = left; } }
      this._ci = ci;
    }
    var cc = this.chapters[ci];
    if (cc) { var f = clamp((shown - cc.start) / Math.max(0.01, cc.end - cc.start), 0, 1); var ch = this.chips[ci]; if (ch && ch._f !== f) { ch.style.setProperty('--f', (this.started ? f : 0).toFixed(4)); ch._f = f; } }
    this.renderSub(t);
    if (this.trItems && !this.trEl.hidden) {
      var ti = -1, tr = this.v.transcript || [];
      for (var k = 0; k < tr.length; k++) if (tr[k].start <= shown + 0.05) ti = k;
      if (ti !== this._ti) { for (var j = 0; j < this.trItems.length; j++) this.trItems[j].classList.toggle('on', j === ti); this._ti = ti; }
    }
    if (!this.scrubbing) this.range.value = String(shown);
    this.range.style.setProperty('--pct', (shown / this.duration * 100).toFixed(3) + '%');
    var tt = fmt(shown) + ' / ' + fmt(this.duration);
    if (tt !== this._tt) { this.timeEl.textContent = tt; this.range.setAttribute('aria-valuetext', tt); this._tt = tt; }
  };
  P.renderSub = function (t) {
    var show = this.cc && this.started && !this.exploring, cue = null, k;
    if (this.L === 'en') { if (this._cue !== '') { this.subEl.innerHTML = ''; this._cue = ''; } return; }
    if (show) for (k = 0; k < this.cues.length; k++) { var c = this.cues[k]; if (c.start - 0.05 <= t && t < c.end) { cue = c; break; } }
    if (cue !== this._cue) {
      this._cue = cue; this._n = -1;
      // 每个字一个 <i>（逐字变亮）；数字和紧跟的单位（11 月、28.58%、200 亿、5,000 名）包在一起，换行时不被拆开
      // 11-09 中文整词换行（数据里有 zhwrap 时）：换行点插在 <i> 和 <i> 之间、不进 <i>，<i> 的个数和顺序不变，逐字时间照旧对得上；
      // 数字那一组后面的换行点放在 </span> 外面。没有 zhwrap 时 wa 是 null，和以前一模一样
      var txt = cue ? cue.text : '', wd = cue && this.wb ? wbLook(this.wb, txt) : null, wa = wd != null ? wbAlign(txt.split(''), wd) : null;
      var ch1 = function (k, ch) { var w = wa && wa[k]; return '<i>' + esc(w ? w.charAt(0) : ch) + '</i>'; };
      var mk = function (k) { var w = wa && wa[k]; return w ? w.slice(1) : ''; };
      var chars = function (x, at, tail) { return x.split('').map(function (ch, k) { return ch1(at + k, ch) + (tail || k < x.length - 1 ? mk(at + k) : ''); }).join(''); };
      var html = '', re = /\d[\d,.]*%?(?: ?(?:美元|[月日年亿万名项个倍]))?/g, last = 0, mm;
      while (cue && (mm = re.exec(txt))) { html += chars(txt.slice(last, mm.index), last, true) + '<span class="nw">' + chars(mm[0], mm.index, false) + '</span>' + mk(mm.index + mm[0].length - 1); last = mm.index + mm[0].length; }
      this.subEl.innerHTML = cue ? '<p' + (wa ? ' class="v3wb"' : '') + '>' + html + chars(txt.slice(last), last, true) + '</p>' : '';
      this._subEls = cue ? this.subEl.querySelectorAll('i') : [];
    }
    if (!cue) return;
    var n = 0;
    for (k = 0; k < cue.t.length; k++) if (cue.t[k] != null && cue.t[k] <= t + 0.03) n = k + 1;
    if (n !== this._n) { for (k = 0; k < this._subEls.length; k++) this._subEls[k].className = k < n - 1 ? 'on' : (k === n - 1 ? 'on cur' : ''); this._n = n; }
  };

  P.syncUI = function () {
    var T = this.T, b = this.btn, silent = !this.useAudio(), forced = !this.audio || this.audioState === 'error';
    b.play.innerHTML = this.playing ? ICON.pause : ICON.play;
    b.play.setAttribute('aria-label', this.playing ? T.pause : T.play); b.play.title = b.play.getAttribute('aria-label') + ' (Space)';
    b.prev.setAttribute('aria-label', T.prev); b.prev.title = T.prev + ' (Shift+←)';
    b.next.setAttribute('aria-label', T.next); b.next.title = T.next + ' (Shift+→)';
    b.cc.setAttribute('aria-label', T.cc); b.cc.title = T.cc + ' (C)'; b.cc.setAttribute('aria-pressed', this.cc ? 'true' : 'false');
    b.silent.innerHTML = silent ? ICON.mute : ICON.sound; b.silent.setAttribute('aria-label', T.silent); b.silent.setAttribute('aria-pressed', silent ? 'true' : 'false'); b.silent.disabled = forced;
    b.full.setAttribute('aria-label', T.full); b.full.title = T.full + ' (F)';
    b.explore.textContent = T.explore; b.explore.setAttribute('aria-pressed', this.exploring ? 'true' : 'false'); b.explore.disabled = !this.world;
    b.tr.textContent = T.transcript; b.tr.setAttribute('aria-pressed', this.trEl.hidden ? 'false' : 'true');
    this.range.setAttribute('aria-label', T.seek); this.wrap.setAttribute('aria-label', T.region); this.pagerEl.setAttribute('aria-label', T.chapters);
    this.wrap.classList.toggle('paused', !this.playing && this.started);
    this.wrap.classList.toggle('ended', this.ended);
    var showOver = !this.playing && (!this.started || this.ended) && !this.exploring;
    this.over.hidden = !showOver;
    if (showOver) {
      this.big.innerHTML = this.ended ? ICON.replay : ICON.play;
      this.big.setAttribute('aria-label', this.ended ? T.replay : T.play);
      this.overMeta.textContent = (this.ended ? T.replay_meta : T.play_meta) + ' · ' + fmt(this.duration);
    }
  };

  /* ---------- 事件 ---------- */
  P.bind = function () {
    var self = this, b = this.btn;
    b.play.addEventListener('click', function () { self.toggle(); });
    b.prev.addEventListener('click', function () { self.step(-1); });
    b.next.addEventListener('click', function () { self.step(1); });
    b.cc.addEventListener('click', function () { self.toggleCC(); });
    b.silent.addEventListener('click', function () { self.toggleSilent(); });
    b.full.addEventListener('click', function () { self.toggleFull(); });
    b.tr.addEventListener('click', function () { self.toggleTr(); });
    b.explore.addEventListener('click', function () { if (self.exploring) { self.exitExplore(); self.syncUI(); } else { if (self.playing) self.pause(); if (!self.started) { self.started = true; self.t = self.duration; self.ended = true; } self.exploreT = self.duration; self.enterExplore(); } });
    this.big.addEventListener('click', function (e) { e.stopPropagation(); self.play(); });
    this.trEl.addEventListener('click', function (e) { var li = e.target.closest && e.target.closest('li[data-t]'); if (li) self.seek(parseFloat(li.getAttribute('data-t')) + 0.01); });
    // 舞台：点一下播放/暂停；暂停时按住拖动＝转视角
    var down = null;
    this.stage.addEventListener('pointerdown', function (e) {
      if (e.button !== 0 || e.target.closest('button, a, .v3note')) return;
      down = { x: e.clientX, y: e.clientY, yaw: self.orbit.yaw, pitch: self.orbit.pitch, moved: false, id: e.pointerId };
    });
    this.stage.addEventListener('pointermove', function (e) {
      if (!down || down.id !== e.pointerId) return;
      var dx = e.clientX - down.x, dy = e.clientY - down.y;
      if (!down.moved && Math.hypot(dx, dy) < 6) return;
      if (self.playing || self.rm || !self.world) return;
      if (!down.moved) { down.moved = true; try { self.stage.setPointerCapture(e.pointerId); } catch (er) { /* ignore */ } self.wrap.classList.add('orbiting'); }
      self.orbit.yaw = clamp(down.yaw - dx / self.sw * 1.4, -0.7, 0.7);
      self.orbit.pitch = clamp(down.pitch + dy / self.sh * 0.8, -0.35, 0.35);
      self.render();
    });
    var up = function (e) {
      if (!down) return;
      var moved = down.moved; down = null; self.wrap.classList.remove('orbiting');
      if (!moved && !e.target.closest('button, a, .v3note')) { if (self.exploring) return; self.toggle(); }
    };
    this.stage.addEventListener('pointerup', up);
    this.stage.addEventListener('pointercancel', function () { down = null; self.wrap.classList.remove('orbiting'); });
    var startScrub = function () { self.scrubbing = true; }, endScrub = function () { self.scrubbing = false; };
    this.range.addEventListener('pointerdown', startScrub);
    this.range.addEventListener('pointerup', endScrub);
    this.range.addEventListener('input', function () { self.exitExplore(true); self.seek(parseFloat(self.range.value) || 0); });
    this.range.addEventListener('change', function () { self.scrubbing = false; self.seek(parseFloat(self.range.value) || 0); });
    this.wrap.addEventListener('keydown', function (e) {
      if (e.target === self.range && (e.key === 'ArrowLeft' || e.key === 'ArrowRight') && !e.shiftKey) return;
      if (e.target.closest && e.target.closest('.pg, .v3note, .v3chip') && (e.key === ' ' || e.key === 'Enter')) return;
      var k = e.key;
      if (k === ' ' || k === 'k' || k === 'K') { e.preventDefault(); self.toggle(); }
      else if (k === 'ArrowRight' && e.shiftKey) { e.preventDefault(); self.step(1); }
      else if (k === 'ArrowLeft' && e.shiftKey) { e.preventDefault(); self.step(-1); }
      else if (k === 'ArrowRight') { e.preventDefault(); self.seek((self.started ? self.t : 0) + 5); }
      else if (k === 'ArrowLeft') { e.preventDefault(); self.seek((self.started ? self.t : 0) - 5); }
      else if (k === 'c' || k === 'C') self.toggleCC();
      else if (k === 'm' || k === 'M') self.toggleSilent();
      else if (k === 'f' || k === 'F') self.toggleFull();
      else if (k === 'Escape') { if (self.exploring) { self.backToMap(); } if (self.wrap.classList.contains('zoom')) self.wrap.classList.remove('zoom'); }
    });
    this._onPlay = function (e) { if (e.detail && e.detail.id !== 'video') self.pause(); };
    document.addEventListener('fd:play', this._onPlay);
    // 画幅变化
    this.onResize = function () {
      self.layout();
      if (self.world) { self.world.resize(self.sw, self.sh); self.render(); }
    };
    if (window.ResizeObserver) { this.ro = new ResizeObserver(function () { self.onResize(); }); this.ro.observe(this.stage); }
    else window.addEventListener('resize', this.onResize);
    // 深浅色、减少动态效果
    this._onTheme = function () {
      var dk = self.isDark(); if (dk === self.dark) return;
      self.dark = dk; self.wrap.classList.toggle('dark', dk);
      if (self.world) { // 换深浅色：整个场景按新配色重建一次（约 0.2 秒），时间位置不变
        var was = self.playing; if (was) self.pause();
        try { if (self.vio) self.vio.disconnect(); self.world.dispose(); } catch (e) { /* ignore */ }
        self.world = null; self.worldEl.innerHTML = '';
        self.ensureWorld(); if (was) self.play();
      }
    };
    if (MQD) { if (MQD.addEventListener) MQD.addEventListener('change', this._onTheme); else if (MQD.addListener) MQD.addListener(this._onTheme); }
    if (window.MutationObserver) { this.mo = new MutationObserver(this._onTheme); this.mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] }); }
    this._onRM = function () { self.rm = !!(MQ && MQ.matches); self.wrap.classList.toggle('reduced', self.rm); if (self.rm) self.trEl.hidden = false; self.render(); };
    if (MQ) { if (MQ.addEventListener) MQ.addEventListener('change', this._onRM); else if (MQ.addListener) MQ.addListener(this._onRM); }
  };

  P.setLang = function () {
    var t = this.t, was = this.playing;
    if (was) this.pause();
    this.L = this.ctx.lang ? (this.ctx.lang() === 'en' ? 'en' : 'zh') : 'zh'; this.T = I18N[this.L] || I18N.zh;
    var hadWorld = !!this.world;
    if (this.world) { this.world.dispose(); this.world = null; }
    this.build(); this.bind(); this.initAudio();
    if (hadWorld) this.ensureWorld();
    this.t = t; this.syncUI(); this.render();
  };
  P.destroy = function () {
    this.playing = false;
    if (this.raf) { cancelAnimationFrame(this.raf); this.raf = 0; }
    if (this.world) this.world.dispose();
    if (this.io) this.io.disconnect(); if (this.vio) this.vio.disconnect(); if (this.ro) this.ro.disconnect(); if (this.mo) this.mo.disconnect();
    if (this.audio) { try { this.audio.pause(); this.audio.removeAttribute('src'); this.audio.load(); } catch (e) { /* ignore */ } }
    if (this._onPlay) document.removeEventListener('fd:play', this._onPlay);
    if (this._onVis) document.removeEventListener('visibilitychange', this._onVis);
    if (MQD && this._onTheme) { if (MQD.removeEventListener) MQD.removeEventListener('change', this._onTheme); }
    if (MQ && this._onRM) { if (MQ.removeEventListener) MQ.removeEventListener('change', this._onRM); }
    this.root.innerHTML = '';
  };
  // 逐帧截图用：渲染第 t 秒（不放声音）
  P.renderAt = function (t) {
    if (!this.world) this.ensureWorld();
    this.wrap.classList.add('capture');
    this.started = true; this.playing = false; this.t = clamp(t, 0, this.duration);
    this.render(false);
    this.syncUI();
    return this.t;
  };

  window.FDVideo3 = { mount: function (root, video, ctx) { return new Player(root, video, ctx); }, version: '3.3' };
})();
