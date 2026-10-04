/* DJ Lab — core helpers shared by every page (classic script, works over file:// too). */
(function () {
  'use strict';
  var DJ = (window.DJ = window.DJ || {});
  var doc = document;

  function meta(n) { var m = doc.querySelector('meta[name="' + n + '"]'); return m ? m.getAttribute('content') : ''; }
  DJ.ROOT = meta('djlab-root') || './';
  DJ.BASE = meta('djlab-base') || './';
  DJ.isFile = location.protocol === 'file:';
  DJ.media = function (p) {
    if (!p) return '';
    if (/^(https?:|data:|blob:)/.test(p)) return p;
    return DJ.ROOT + String(p).split('/').map(encodeURIComponent).join('/');
  };
  DJ.page = function (p) { return DJ.BASE + p; };

  /* ---------- storage (always guarded) ---------- */
  DJ.store = {
    get: function (k, d) {
      try { var v = localStorage.getItem('djlab:' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; }
    },
    set: function (k, v) { try { localStorage.setItem('djlab:' + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
    del: function (k) { try { localStorage.removeItem('djlab:' + k); } catch (e) { /* ignore */ } }
  };

  /* ---------- dom helpers ---------- */
  DJ.$ = function (s, r) { return (r || doc).querySelector(s); };
  DJ.$$ = function (s, r) { return Array.prototype.slice.call((r || doc).querySelectorAll(s)); };
  DJ.esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  DJ.h = function (html) { var t = doc.createElement('template'); t.innerHTML = String(html).trim(); return t.content.firstElementChild; };
  DJ.frag = function (html) { var t = doc.createElement('template'); t.innerHTML = String(html).trim(); return t.content; };
  var ICONS = window.DJ_ICONS || {};
  DJ.icon = function (name, cls) {
    return '<svg class="icon ' + (cls || '') + '" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + (ICONS[name] || '') + '</svg>';
  };
  DJ.ready = function (fn) { if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', fn); else fn(); };
  DJ.debounce = function (fn, ms) { var t; return function () { var a = arguments, s = this; clearTimeout(t); t = setTimeout(function () { fn.apply(s, a); }, ms); }; };
  DJ.clamp = function (v, a, b) { return Math.max(a, Math.min(b, v)); };
  DJ.params = new URLSearchParams(location.search);
  DJ.reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- formatting ---------- */
  DJ.fmtTime = function (s) {
    if (!isFinite(s) || s < 0) s = 0;
    var m = Math.floor(s / 60), ss = Math.floor(s % 60);
    return m + ':' + (ss < 10 ? '0' : '') + ss;
  };
  DJ.fmtDur = function (s) {
    if (!isFinite(s) || s <= 0) return '—';
    var h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
    if (h) return h + ':' + (m < 10 ? '0' : '') + m + ' ש\'';
    return m + ' דק\'';
  };
  DJ.fmtBpm = function (b, dec) {
    if (b == null || b === '' || isNaN(b)) return '—';
    b = Number(b);
    if (dec != null) return b.toFixed(dec);
    return Math.abs(b - Math.round(b)) < 0.005 ? String(Math.round(b)) : b.toFixed(1);
  };
  DJ.fmtPct = function (p, dec) { var s = (p >= 0 ? '+' : '−') + Math.abs(p).toFixed(dec == null ? 1 : dec) + '%'; return s; };
  DJ.fmtSize = function (b) { if (!b) return ''; return (b / 1048576).toFixed(1) + ' MB'; };

  /* ---------- vocab ---------- */
  DJ.ROLES = { warmup: 'חימום', build: 'בנייה', peak: 'שיא', closing: 'סגירה' };
  DJ.FAMILIES = { house: 'האוס', techno: 'טכנו', mainstream: 'מיינסטרים', breadth: "עוד ז'אנרים" };
  DJ.FAMILY_ORDER = ['house', 'techno', 'mainstream', 'breadth'];
  DJ.CUE_COLORS = { A: '#28E214', B: '#10B1E6', C: '#E0641B', D: '#E62828', E: '#B4BE04', F: '#DE44CF', G: '#305AFF', H: '#8A2BE2' };

  /* ---------- catalog ---------- */
  var C = window.DJLAB_CATALOG || {};
  var plan = C.plan || { tracks: [], practice: [], transitions: [] };
  DJ.catalog = { tracks: C.tracks || [], practice: C.practice || [], transitions: C.transitions || [], plan: plan };
  DJ.all = DJ.catalog.tracks.concat(DJ.catalog.practice, DJ.catalog.transitions);
  DJ.byId = new Map(); DJ.byFile = new Map(); DJ.planById = new Map();
  DJ.all.forEach(function (t) { DJ.byId.set(t.id, t); if (t.file) DJ.byFile.set(t.file, t); });
  [].concat(plan.tracks || [], plan.practice || [], plan.transitions || []).forEach(function (t) { DJ.planById.set(t.id, t); });
  DJ.playable = function (t) { return !!(t && t.file && t.has_audio !== false); };
  DJ.tracksReady = function () { return DJ.catalog.tracks.filter(DJ.playable); };
  DJ.lookup = function (id) { return DJ.byId.get(id) || DJ.planById.get(id) || null; };

  /* ---------- Camelot ---------- */
  var CAM_KEYS = { '1A': 'Abm', '1B': 'B', '2A': 'Ebm', '2B': 'F#', '3A': 'Bbm', '3B': 'Db', '4A': 'Fm', '4B': 'Ab', '5A': 'Cm', '5B': 'Eb', '6A': 'Gm', '6B': 'Bb', '7A': 'Dm', '7B': 'F', '8A': 'Am', '8B': 'C', '9A': 'Em', '9B': 'G', '10A': 'Bm', '10B': 'D', '11A': 'F#m', '11B': 'A', '12A': 'C#m', '12B': 'E' };
  var CAM_NAMES = { '1A': 'A♭ minor', '1B': 'B major', '2A': 'E♭ minor', '2B': 'F♯ major', '3A': 'B♭ minor', '3B': 'D♭ major', '4A': 'F minor', '4B': 'A♭ major', '5A': 'C minor', '5B': 'E♭ major', '6A': 'G minor', '6B': 'B♭ major', '7A': 'D minor', '7B': 'F major', '8A': 'A minor', '8B': 'C major', '9A': 'E minor', '9B': 'G major', '10A': 'B minor', '10B': 'D major', '11A': 'F♯ minor', '11B': 'A major', '12A': 'C♯ minor', '12B': 'E major' };
  var ENHARM = { 'G#m': '1A', 'Abm': '1A', 'B': '1B', 'Cb': '1B', 'D#m': '2A', 'Ebm': '2A', 'F#': '2B', 'Gb': '2B', 'A#m': '3A', 'Bbm': '3A', 'C#': '3B', 'Db': '3B', 'Fm': '4A', 'G#': '4B', 'Ab': '4B', 'Cm': '5A', 'D#': '5B', 'Eb': '5B', 'Gm': '6A', 'A#': '6B', 'Bb': '6B', 'Dm': '7A', 'F': '7B', 'Am': '8A', 'C': '8B', 'Em': '9A', 'G': '9B', 'Bm': '10A', 'D': '10B', 'F#m': '11A', 'Gbm': '11A', 'A': '11B', 'C#m': '12A', 'Dbm': '12A', 'E': '12B' };
  DJ.cam = {
    keys: CAM_KEYS,
    names: CAM_NAMES,
    all: (function () { var a = []; for (var n = 1; n <= 12; n++) { a.push(n + 'A'); a.push(n + 'B'); } return a; })(),
    parse: function (code) { var m = /^\s*(\d{1,2})\s*([AB])\s*$/i.exec(String(code || '')); if (!m) return null; var n = +m[1]; if (n < 1 || n > 12) return null; return { n: n, l: m[2].toUpperCase() }; },
    norm: function (code) { var p = DJ.cam.parse(code); return p ? p.n + p.l : null; },
    code: function (n, l) { n = ((n - 1) % 12 + 12) % 12 + 1; return n + l; },
    color: function (code) { var p = DJ.cam.parse(code); return p ? 'var(--cam-' + p.n + p.l.toLowerCase() + ')' : 'var(--surface-3)'; },
    hue: function (n) { return ((165 - (n - 1) * 30) % 360 + 360) % 360; },
    fromKey: function (k) {
      if (!k) return null;
      var c = DJ.cam.norm(k); if (c) return c;
      var s = String(k).trim().replace('♯', '#').replace('♭', 'b');
      var m = /^([A-Ga-g])([#b]?)\s*(m|min|minor|maj|major)?$/i.exec(s);
      if (!m) return null;
      var root = m[1].toUpperCase() + (m[2] || '');
      var minor = m[3] && /^m(in(or)?)?$/i.test(m[3]) && m[3] !== 'M';
      if (m[3] && /^maj/i.test(m[3])) minor = false;
      return ENHARM[root + (minor ? 'm' : '')] || null;
    },
    relation: function (a, b) {
      var A = DJ.cam.parse(a), B = DJ.cam.parse(b);
      if (!A || !B) return { type: 'unknown', label: '?', score: 0 };
      var d = ((B.n - A.n) % 12 + 12) % 12;
      if (A.l === B.l) {
        if (d === 0) return { type: 'perfect', label: 'אותו סולם', score: 5 };
        if (d === 1) return { type: 'adjacent', label: '+1 שכן', score: 4 };
        if (d === 11) return { type: 'adjacent', label: '−1 שכן', score: 4 };
        if (d === 2) return { type: 'boost', label: 'Energy +2', score: 3 };
        if (d === 7) return { type: 'boost', label: '+7 חצי טון', score: 2 };
      } else {
        if (d === 0) return { type: 'relative', label: 'יחסי ' + A.l + '↔' + B.l, score: 4 };
        if ((A.l === 'A' && d === 1) || (A.l === 'B' && d === 11)) return { type: 'diagonal', label: 'אלכסון', score: 1 };
      }
      return { type: 'clash', label: 'התנגשות', score: 0 };
    },
    compatible: function (code) {
      var p = DJ.cam.parse(code); if (!p) return [];
      var o = p.l === 'A' ? 'B' : 'A', c = DJ.cam.code;
      return [
        { code: c(p.n, p.l), type: 'perfect', label: 'אותו סולם' },
        { code: c(p.n + 1, p.l), type: 'adjacent', label: '+1' },
        { code: c(p.n - 1, p.l), type: 'adjacent', label: '−1' },
        { code: c(p.n, o), type: 'relative', label: 'יחסי' },
        { code: c(p.n + 2, p.l), type: 'boost', label: '+2 Energy' },
        { code: c(p.n + 7, p.l), type: 'boost', label: '+7' }
      ];
    }
  };
  DJ.camOf = function (t) { return t ? (DJ.cam.norm(t.camelot) || DJ.cam.fromKey(t.key_short) || DJ.cam.fromKey(t.key)) : null; };
  DJ.camBadge = function (code, cls) {
    if (!code) return '';
    return '<span class="cam-badge ' + (cls || '') + '" style="--cam:' + DJ.cam.color(code) + '" title="Camelot ' + code + ' · ' + (CAM_NAMES[code] || '') + '">' + code + '</span>';
  };

  /* ---------- BPM ---------- */
  DJ.bpmDelta = function (from, to) { return (to / from - 1) * 100; };
  DJ.bpmRelation = function (a, b, tol) {
    tol = tol || 6;
    if (!a || !b) return null;
    var d = DJ.bpmDelta(a, b);
    if (Math.abs(d) <= tol) return { type: 'ok', delta: d, label: DJ.fmtPct(d) };
    var h = DJ.bpmDelta(a, b * 2), dd = DJ.bpmDelta(a, b / 2);
    if (Math.abs(h) <= tol) return { type: 'half', delta: h, label: '×2 ' + DJ.fmtPct(h) };
    if (Math.abs(dd) <= tol) return { type: 'double', delta: dd, label: '×½ ' + DJ.fmtPct(dd) };
    return { type: 'far', delta: d, label: DJ.fmtPct(d) };
  };
  DJ.compatibleTracks = function (t, opts) {
    opts = opts || {};
    var pool = opts.pool || DJ.tracksReady();
    var cam = DJ.camOf(t), tol = opts.tol || 6, out = [];
    pool.forEach(function (o) {
      if (o.id === t.id) return;
      var rel = DJ.cam.relation(cam, DJ.camOf(o));
      if (rel.score < 2) return;
      var br = DJ.bpmRelation(t.bpm, o.bpm, tol);
      if (!br || br.type === 'far') return;
      var score = rel.score * 10 - Math.abs(br.delta) - (br.type === 'ok' ? 0 : 6) - Math.abs((o.energy || 5) - (t.energy || 5)) * 0.6;
      out.push({ track: o, rel: rel, bpm: br, score: score });
    });
    out.sort(function (a, b) { return b.score - a.score; });
    return opts.limit ? out.slice(0, opts.limit) : out;
  };

  /* ---------- visuals ---------- */
  DJ.energyHTML = function (e) {
    e = Math.round(Number(e) || 0);
    var lvl = e >= 8 ? 'high' : e >= 5 ? 'mid' : 'low', s = '';
    for (var i = 1; i <= 10; i++) s += '<i style="--h:' + i + '"' + (i <= e ? ' class="on"' : '') + '></i>';
    return '<span class="energy" data-level="' + lvl + '" role="img" aria-label="אנרגיה ' + e + ' מתוך 10" title="אנרגיה ' + e + '/10">' + s + '</span>';
  };
  DJ.roleHTML = function (r) { return r ? '<span class="role role--' + DJ.esc(r) + '">' + DJ.esc(DJ.ROLES[r] || r) + '</span>' : ''; };
  DJ.coverHTML = function (t, opts) {
    opts = opts || {};
    var cam = DJ.camOf(t);
    var label = DJ.esc((t && (t.genre || t.title)) || 'DJ Lab');
    var fb = '<span class="cover-fallback" style="--cam:' + DJ.cam.color(cam) + '"><span>' + label + '</span></span>';
    if (t && t.cover) {
      return '<img src="' + DJ.esc(DJ.media(t.cover)) + '" alt="' + (opts.alt ? DJ.esc(opts.alt) : '') + '" loading="lazy" decoding="async" onerror="this.replaceWith(document.createRange().createContextualFragment(this.dataset.fb||\'\'))" data-fb="' + DJ.esc(fb) + '">';
    }
    return fb;
  };

  /* ---------- peaks & waveform ---------- */
  var P = window.DJLAB_PEAKS || { files: {} };
  var peakCache = new Map();
  DJ.peaks = function (file) {
    if (!file) return null;
    if (peakCache.has(file)) return peakCache.get(file);
    var b64 = P.files && P.files[file], arr = null;
    if (b64) {
      try { var bin = atob(b64); arr = new Uint8Array(bin.length); for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i); } catch (e) { arr = null; }
    }
    peakCache.set(file, arr);
    return arr;
  };
  function cssVar(n, fb) { var v = getComputedStyle(doc.documentElement).getPropertyValue(n).trim(); return v || fb; }
  DJ.cssVar = cssVar;

  /** Render 3-band peaks into a canvas (used as an offscreen image). */
  DJ.renderPeaks = function (peaks, w, h, opts) {
    opts = opts || {};
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var cv = doc.createElement('canvas');
    cv.width = Math.max(1, Math.round(w * dpr)); cv.height = Math.max(1, Math.round(h * dpr));
    var ctx = cv.getContext('2d');
    ctx.scale(dpr, dpr);
    var cols = [cssVar('--wave-low', '#2f7bff'), cssVar('--wave-mid', '#ffa63d'), cssVar('--wave-high', '#fff')];
    var mid = opts.bottom ? h : h / 2, amp = opts.bottom ? h : h / 2 - 1;
    var n = peaks ? Math.floor(peaks.length / 3) : 0;
    if (!n) {
      // placeholder: gentle pseudo-wave so the UI never looks broken
      ctx.fillStyle = cols[0]; ctx.globalAlpha = 0.5;
      var seed = opts.seed || 7;
      for (var x = 0; x < w; x += 3) {
        var v = 0.25 + 0.2 * Math.abs(Math.sin(x * 0.05 + seed) * Math.cos(x * 0.013 + seed * 2));
        ctx.fillRect(x, mid - v * amp, 2, v * amp * (opts.bottom ? 1 : 2));
      }
      return cv;
    }
    var step = opts.barW || 1, gap = opts.gap || 0;
    var colsN = Math.max(1, Math.floor(w / step));
    var bands = [0, 1, 2], scale = [1, 1, 1];
    for (var bi = 0; bi < 3; bi++) {
      ctx.fillStyle = cols[bi];
      for (var c = 0; c < colsN; c++) {
        var i0 = Math.floor(c * n / colsN), i1 = Math.max(i0 + 1, Math.floor((c + 1) * n / colsN)), m = 0;
        for (var i = i0; i < i1 && i < n; i++) { var val = peaks[i * 3 + bands[bi]]; if (val > m) m = val; }
        var hh = (m / 255) * amp * scale[bi];
        if (hh < 0.5) continue;
        if (opts.bottom) ctx.fillRect(c * step, mid - hh, step - gap, hh);
        else ctx.fillRect(c * step, mid - hh, step - gap, hh * 2);
      }
    }
    return cv;
  };

  /** Interactive waveform: progress overlay, seeking by click/drag/keyboard, optional cue/section marks. */
  DJ.Wave = function (canvas, opts) {
    this.c = canvas; this.o = opts || {}; this.p = 0; this.img = null; this.w = 0; this.h = 0;
    var self = this;
    this.resize = function () {
      var r = canvas.getBoundingClientRect(); var w = Math.round(r.width), h = Math.round(r.height);
      if (!w || !h) return;
      if (w === self.w && h === self.h && self.img) { self.draw(); return; }
      self.w = w; self.h = h;
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      self.img = DJ.renderPeaks(self.o.peaks, w, h, { barW: self.o.barW || (w > 500 ? 2 : 1), gap: self.o.gap != null ? self.o.gap : (w > 500 ? 0.6 : 0), seed: self.o.seed });
      self.draw();
    };
    if (window.ResizeObserver) { this.ro = new ResizeObserver(function () { self.resize(); }); this.ro.observe(canvas); }
    else window.addEventListener('resize', this.resize);
    this.resize();
    var dragging = false;
    function frac(ev) { var r = canvas.getBoundingClientRect(); return DJ.clamp((ev.clientX - r.left) / r.width, 0, 1); }
    canvas.addEventListener('pointerdown', function (ev) {
      if (!self.o.onSeek) return;
      dragging = true; try { canvas.setPointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
      self.o.onSeek(frac(ev), 'down');
    });
    canvas.addEventListener('pointermove', function (ev) { if (dragging && self.o.onSeek) self.o.onSeek(frac(ev), 'move'); });
    canvas.addEventListener('pointerup', function () { dragging = false; });
    canvas.addEventListener('pointercancel', function () { dragging = false; });
    canvas.addEventListener('keydown', function (ev) {
      if (!self.o.onKey) return;
      if (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft' || ev.key === 'Home' || ev.key === 'End') { ev.preventDefault(); self.o.onKey(ev.key); }
    });
  };
  DJ.Wave.prototype.setPeaks = function (peaks) { this.o.peaks = peaks; this.w = 0; this.resize(); };
  DJ.Wave.prototype.set = function (p) { p = DJ.clamp(p || 0, 0, 1); if (Math.abs(p - this.p) < 0.0004 && this.img) return; this.p = p; this.draw(); };
  DJ.Wave.prototype.draw = function () {
    var c = this.c, ctx = c.getContext('2d'), w = this.w, h = this.h;
    if (!w || !this.img) return;
    var dpr = c.width / w;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, c.width, c.height);
    var dim = parseFloat(cssVar('--wave-dim', '.38')) || 0.38;
    ctx.globalAlpha = dim; ctx.drawImage(this.img, 0, 0);
    ctx.globalAlpha = 1;
    var px = Math.round(this.p * c.width);
    if (px > 0) { ctx.save(); ctx.beginPath(); ctx.rect(0, 0, px, c.height); ctx.clip(); ctx.drawImage(this.img, 0, 0); ctx.restore(); }
    if (this.o.marks) {
      var marks = this.o.marks;
      for (var i = 0; i < marks.length; i++) {
        ctx.fillStyle = marks[i].color; ctx.globalAlpha = 0.85;
        ctx.fillRect(Math.round(marks[i].f * c.width) - Math.round(dpr / 2), 0, Math.max(1, Math.round(dpr)), c.height);
      }
      ctx.globalAlpha = 1;
    }
    if (this.p > 0 || this.o.showHead) {
      ctx.fillStyle = cssVar('--text', '#fff');
      ctx.fillRect(Math.max(0, px - dpr), 0, Math.round(2 * dpr), c.height);
    }
  };

  /* ---------- toast ---------- */
  var toastWrap;
  DJ.toast = function (msg, ms) {
    if (!toastWrap) { toastWrap = DJ.h('<div class="toast-wrap" role="status" aria-live="polite"></div>'); doc.body.appendChild(toastWrap); }
    var t = DJ.h('<div class="toast"></div>'); t.textContent = msg;
    toastWrap.innerHTML = ''; toastWrap.appendChild(t);
    clearTimeout(DJ._toastT); DJ._toastT = setTimeout(function () { t.remove(); }, ms || 3200);
  };

  /* ---------- downloads ---------- */
  DJ.downloadText = function (name, text, type) {
    var blob = new Blob([text], { type: type || 'text/plain;charset=utf-8' });
    var a = doc.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name;
    doc.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
  };
  DJ.copy = function (text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (res, rej) {
      var ta = doc.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      doc.body.appendChild(ta); ta.select();
      try { doc.execCommand('copy'); res(); } catch (e) { rej(e); } finally { ta.remove(); }
    });
  };
  DJ.loadScript = function (src) {
    return new Promise(function (res, rej) { var s = doc.createElement('script'); s.src = src; s.onload = res; s.onerror = rej; doc.head.appendChild(s); });
  };

  /* ---------- theme & nav ---------- */
  function currentTheme() {
    var t = doc.documentElement.getAttribute('data-theme');
    return t || 'dark';
  }
  DJ.ready(function () {
    DJ.$$('[data-theme-toggle]').forEach(function (b) {
      b.addEventListener('click', function () {
        var next = currentTheme() === 'dark' ? 'light' : 'dark';
        doc.documentElement.setAttribute('data-theme', next);
        try { localStorage.setItem('djlab:theme', next); } catch (e) { /* ignore */ }
        doc.dispatchEvent(new CustomEvent('djlab:theme', { detail: next }));
      });
    });
    var nav = DJ.$('#site-nav'), tog = DJ.$('[data-nav-toggle]');
    if (nav && tog) {
      var close = function () { nav.classList.remove('is-open'); tog.setAttribute('aria-expanded', 'false'); tog.innerHTML = DJ.icon('menu'); tog.setAttribute('aria-label', 'פתיחת תפריט'); };
      tog.addEventListener('click', function () {
        var open = !nav.classList.contains('is-open');
        nav.classList.toggle('is-open', open);
        tog.setAttribute('aria-expanded', String(open));
        tog.setAttribute('aria-label', open ? 'סגירת תפריט' : 'פתיחת תפריט');
        tog.innerHTML = DJ.icon(open ? 'close' : 'menu');
        if (open) { var a = nav.querySelector('a'); if (a) a.focus(); }
      });
      doc.addEventListener('keydown', function (e) { if (e.key === 'Escape' && nav.classList.contains('is-open')) { close(); tog.focus(); } });
      doc.addEventListener('click', function (e) { if (nav.classList.contains('is-open') && !nav.contains(e.target) && !tog.contains(e.target)) close(); });
    }
  });
})();
