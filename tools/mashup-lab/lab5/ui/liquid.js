/* Liquid: the motion and glass layer of Mashup Lab.
   Apple's Liquid Glass, made to run in iPhone Safari (no SVG backdrop filters there, so the lens refracts our own
   content instead of sampling the page):
   - springs with response / damping like SwiftUI, one rAF loop, interruptible (velocity carries over)
   - tab bar: a resting platter under the selected tab and a glass lens that lifts on touch, magnifies a live copy of
     the tab row under it (with a faint red / blue split at its edges, like a real lens), stretches with its speed and
     lands with a small wobble. Scrolling down shrinks the bar into a circle (iOS 26) and the mini player docks beside it.
   - segmented controls: the thumb is a small lens with the same physics, and can be dragged
   - sheets: spring presentation and interactive dismiss; the mixer grows out of the mini player and back into it
   Hot paths touch transform / opacity only; prefers-reduced-motion gets short springs without bounce or lift. */
(function () {
  "use strict";
  var W = window, D = document, root = D.documentElement;
  var MQ = W.matchMedia ? W.matchMedia("(prefers-reduced-motion: reduce)") : null;
  var REDUCED = !!(MQ && MQ.matches);
  if (MQ) { var onMq = function (e) { REDUCED = !!e.matches; }; if (MQ.addEventListener) MQ.addEventListener("change", onMq); else if (MQ.addListener) MQ.addListener(onMq); }
  function clamp(x, a, b) { return x < a ? a : x > b ? b : x; }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function r2(v) { return Math.round(v * 100) / 100; }

  /* ---------- springs ---------- */
  function Spring(x, o) { this.x = this.t = x; this.v = 0; this.tune(o); }
  Spring.prototype.tune = function (o) {
    o = o || {};
    var r = o.response || this.r0 || .35, z = o.damping == null ? (this.z0 == null ? .82 : this.z0) : o.damping;
    if (o.response) this.r0 = o.response; if (o.damping != null) this.z0 = o.damping;
    if (REDUCED) { r = Math.min(r, .2); z = 1; }
    this.k = Math.pow(2 * Math.PI / r, 2); this.c = 4 * Math.PI * z / r;
    if (o.eps) this.eps = o.eps; else if (!this.eps) this.eps = .002;
    return this;
  };
  Spring.prototype.to = function (t, o) { this.t = t; if (o) { this.tune(o); if (o.v != null) this.v = o.v; } return this; };
  Spring.prototype.snap = function (x) { this.x = this.t = x; this.v = 0; return this; };
  Spring.prototype.step = function (dt) {
    var n = Math.max(1, Math.ceil(dt / .004)), h = dt / n;
    for (var i = 0; i < n; i++) { var a = -this.k * (this.x - this.t) - this.c * this.v; this.v += a * h; this.x += this.v * h; }
  };
  Spring.prototype.idle = function () { return Math.abs(this.x - this.t) < this.eps && Math.abs(this.v) < this.eps * 25; };

  /* ---------- one animation loop ---------- */
  var jobs = [], raf = 0, last = 0;
  function frame(now) {
    raf = 0;
    var dt = clamp((now - last) / 1000, .001, .034); last = now;
    var list = jobs.slice();
    for (var i = 0; i < list.length; i++) {
      var j = list[i], busy = !!(j.hold && j.hold());
      for (var k = 0; k < j.springs.length; k++) { var s = j.springs[k]; s.step(dt); if (!s.idle()) busy = true; }
      if (!busy) for (k = 0; k < j.springs.length; k++) j.springs[k].snap(j.springs[k].t);
      try { j.render(now); } catch (e) { try { console.warn("[Liquid]", e); } catch (x) {} }
      if (!busy) { var at = jobs.indexOf(j); if (at >= 0) jobs.splice(at, 1); if (j.done) { var d = j.done; j.done = null; try { d(); } catch (e) { setTimeout(function () { throw e; }); } } }
    }
    if (jobs.length) raf = requestAnimationFrame(frame);
  }
  function kick(j) { if (jobs.indexOf(j) < 0) jobs.push(j); if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); } }

  /* ================================================================== tab bar */
  var tabbar = (function () {
    var bar, mat, row, plat, lens, copies = [], onSelect = null, inited = false;
    var G = null;                          /* geometry at full width: { w, h, rw, tabs: [{ b, x, w, c }] } (bar coords) */
    var X = new Spring(0, { response: .34, damping: .72, eps: .05 }), PW = new Spring(80, { response: .34, damping: .86, eps: .05 });
    var LF = new Spring(0, { response: .26, damping: .6, eps: .001 }), MZ = new Spring(0, { response: .44, damping: .86, eps: .001 });
    var touch = null, landAt = 0, mini = false, maskOn = false, selIdx = 0, lastOn = -1;
    var job = { springs: [X, PW, LF, MZ], render: render, hold: function () { return !!touch || (landAt && performance.now() < landAt + 400); } };
    var LH = 22, M = 1.24;                 /* lens: taller than the bar by LH px; magnification M */

    function vis() { return Array.prototype.filter.call(row.querySelectorAll(".tab"), function (b) { return !b.hidden; }); }
    function gut() { var v = parseFloat(getComputedStyle(root).getPropertyValue("--gut")); return isFinite(v) ? v : 16; }
    function measure() {
      if (!bar) return;
      var n = vis().length || 1, vw = root.clientWidth || W.innerWidth, g = gut();
      var w = Math.min(vw - 2 * g, n * 98 + 8), h = bar.offsetHeight || 62;
      row.style.width = (w - 8) + "px";
      copies.forEach(function (c) { c.style.width = (w - 8) + "px"; });
      bar.style.width = w + "px";                                   /* measure at full width */
      var br = row.getBoundingClientRect(), tabs = vis().map(function (b) { var r = b.getBoundingClientRect(); return { b: b, x: r.left - br.left + 4, w: r.width, c: r.left - br.left + 4 + r.width / 2 }; });
      var bb = bar.getBoundingClientRect();                         /* the bar's distance from the bottom (safe area included) */
      G = { w: w, h: h, vw: vw, g: g, tabs: tabs, tb: Math.max(0, (W.innerHeight || bb.bottom) - bb.bottom) };
      lens.style.width = lensW() + "px";
    }
    function lensW() { var t = G && G.tabs[0]; return Math.round((t ? t.w : 80) + 14); }
    function idxOf(btn) { if (!G) return 0; for (var i = 0; i < G.tabs.length; i++) if (G.tabs[i].b === btn) return i; return 0; }
    function nearest(x) { var bi = 0, bd = 1e9; G.tabs.forEach(function (t, i) { var d = Math.abs(t.c - x); if (d < bd) { bd = d; bi = i; } }); return bi; }
    function sync() {                                               /* after the app (re)renders the tab buttons */
      if (!inited) return;
      var html = row.innerHTML.replace(/\s(id|role|aria-[a-z]+|tabindex|aria-controls|data-tab)="[^"]*"/g, "").replace(/class="tab(["\s])/g, 'class="tbc$1');
      copies.forEach(function (c) { c.innerHTML = html; });
      measure();
      var sel = row.querySelector('.tab[aria-selected="true"]') || vis()[0];
      select(sel, false);
    }
    function select(btn, animate) {
      if (!inited || !btn) return;
      if (!G) measure();
      var i = idxOf(btn), t = G.tabs[i]; if (!t) return;
      var changed = i !== selIdx; selIdx = i;
      if (touch) return;                                            /* a finger is on the bar: it leads, up() lands */
      var busy = LF.x > .02 || LF.t > 0 || !X.idle();
      if (REDUCED || (!animate && !busy)) { X.snap(t.c); PW.snap(t.w); LF.snap(0); render(); return; }
      X.to(t.c, { response: .36, damping: .7 }); PW.to(t.w);
      if (changed && LF.t < .5) LF.to(.82, { response: .2, damping: .7 });   /* a quick lift while it travels (a tap on iOS 26) */
      landAt = performance.now();
      kick(job);
    }
    function render(now) {
      if (!G) return;
      now = now || performance.now();
      if (!touch && landAt && LF.t > 0 && Math.abs(X.x - X.t) < 6 && now > landAt + 120) { LF.to(0, { response: .34, damping: .66 }); landAt = 0; }
      var mz = clamp(MZ.x, 0, 1), lf = clamp(LF.x, 0, 1.15), x = X.x, pw = PW.x;
      dock.follow();
      /* bar width and place (minimised: a circle at the inline start, iOS 26) */
      var w = lerp(G.w, G.h, mz), left = lerp((G.vw - G.w) / 2, G.vw - G.g - G.h, mz);
      bar.style.width = r2(w) + "px"; bar.style.transform = "translate3d(" + r2(left) + "px,0,0)";
      var selT = G.tabs[selIdx] || G.tabs[0], shift = mz * (G.h / 2 - selT.c);
      row.style.transform = shift ? "translate3d(" + r2(shift) + "px,0,0)" : "";
      if (mz > .001 || bar.classList.contains("mz")) {
        G.tabs.forEach(function (t, i) {
          var on = i === selIdx, o = on ? 1 : clamp(1 - mz * 2.2, 0, 1);
          t.b.style.opacity = o < 1 ? String(r2(o)) : "";
          var lab = t.b.querySelector("span:not(.badge)"); if (lab) lab.style.opacity = on && mz > 0 ? String(r2(clamp(1 - mz * 2.4, 0, 1))) : "";
          var ic = t.b.querySelector("svg"); if (ic) ic.style.transform = on && mz > 0 ? "translateY(" + r2(7 * mz) + "px) scale(" + r2(1 + .08 * mz) + ")" : "";
        });
        bar.classList.toggle("mz", mz > .001);
      }
      /* platter (resting selection) */
      var v = X.v, st = REDUCED ? 0 : clamp(Math.abs(v) / 2600, 0, .26);
      plat.style.width = r2(pw) + "px";
      plat.style.transform = "translate3d(" + r2(x - pw / 2 + shift) + "px,0,0) scale(" + r2(1 + st * .6) + "," + r2(1 - st * .25) + ")";
      plat.style.opacity = String(r2(clamp(1 - lf * 1.6, 0, 1) * (1 - mz)));
      /* lens */
      var lw = lensW(), L = x - lw / 2;
      if (lf > .004 && mz < .5) {
        var sc = .72 + .28 * Math.min(1, lf), sx = sc * (1 + st), sy = sc * (1 - st * .45);
        lens.style.opacity = String(r2(clamp(lf * 1.5, 0, 1)));
        lens.style.transform = "translate3d(" + r2(L) + "px,0,0) scale(" + r2(sx) + "," + r2(sy) + ")";
        var ox = L + lw / 2 - 4, oy = (G.h - 8) / 2;               /* the row point under the lens centre */
        copies.forEach(function (c, k) {
          var m = M * (k === 1 ? 1.018 : k === 2 ? .982 : 1);       /* 0: the copy, 1 / 2: red / blue fringes */
          c.style.transform = "translate3d(" + r2(4 - L + ox) + "px," + r2(LH / 2 + 4 + oy) + "px,0) scale(" + m + ") translate(" + r2(-ox) + "px," + r2(-oy) + "px)";
        });
        var on = nearest(x);
        if (on !== lastOn) { lastOn = on; copies.forEach(function (c) { Array.prototype.forEach.call(c.querySelectorAll(".tbc:not([hidden])"), function (b, i) { b.classList.toggle("on", i === on); }); }); }
        /* the real row under the lens fades out, so only the magnified copy shows there */
        var a = L - 4, b2 = L + lw - 4, k2 = r2(clamp(1 - lf * 1.4, 0, 1));
        row.style.webkitMaskImage = row.style.maskImage = "linear-gradient(to right,#000 " + r2(a) + "px,rgba(0,0,0," + k2 + ") " + r2(a + 10) + "px,rgba(0,0,0," + k2 + ") " + r2(b2 - 10) + "px,#000 " + r2(b2) + "px)";
        maskOn = true;
        lens.classList.toggle("deep", lf > .55);
      } else {
        if (lens.style.opacity !== "0") { lens.style.opacity = "0"; lens.style.transform = "translate3d(" + r2(L) + "px,0,0) scale(.72)"; }
        if (maskOn) { row.style.webkitMaskImage = row.style.maskImage = ""; maskOn = false; }
        lastOn = -1;
      }
    }
    /* touch: lift, follow, land */
    function localX(e) { return e.clientX - bar.getBoundingClientRect().left; }
    function down(e) {
      if (e.button || !G || touch) return;
      if (MZ.t > .5) { touch = { id: e.pointerId, mini: true }; return; }
      var b = e.target.closest && e.target.closest(".tab"); if (!b && !e.target.closest(".tb-row")) return;
      var lo = Math.min(G.tabs[0].c, G.tabs[G.tabs.length - 1].c), hi = Math.max(G.tabs[0].c, G.tabs[G.tabs.length - 1].c), lx = clamp(localX(e), lo, hi);
      touch = { id: e.pointerId, x0: e.clientX, t0: performance.now(), moved: false, lx: lx, lo: lo, hi: hi, start: b };   /* no capture yet: a tap must reach the button */
      if (!REDUCED) { LF.to(1, { response: .24, damping: .58 }); X.to(lx, { response: .3, damping: .74 }); }
      landAt = 0; kick(job);
    }
    function move(e) {
      if (!touch || e.pointerId !== touch.id || touch.mini) return;
      if (!touch.moved && Math.abs(e.clientX - touch.x0) < 7) return;
      if (!touch.moved) { touch.moved = true; try { bar.setPointerCapture(e.pointerId); } catch (err) {} }
      var lx = localX(e), lo = touch.lo, hi = touch.hi;
      if (lx < lo) lx = lo - Math.sqrt(lo - lx) * 2.2; else if (lx > hi) lx = hi + Math.sqrt(lx - hi) * 2.2;   /* rubber band */
      touch.lx = lx; X.to(lx, { response: .2, damping: .86 }); kick(job);
    }
    function up(e) {
      if (!touch || e.pointerId !== touch.id) return;
      var t = touch; touch = null;
      if (t.mini) { if (e.type === "pointerup") expand(); return; }
      var i = nearest(t.moved ? t.lx : (t.start ? G.tabs[idxOf(t.start)].c : t.lx));
      if (e.type === "pointercancel") i = selIdx;
      var tb = G.tabs[i];
      X.to(tb.c, { response: .36, damping: .7 }); PW.to(tb.w);
      landAt = performance.now();
      if (REDUCED) LF.to(0);
      kick(job);
      if (t.moved && i !== selIdx && onSelect) onSelect(tb.b, true);   /* a tap goes through the button's own click */
    }
    /* minimise on scroll (narrow screens only, like the iOS 26 tab bar) */
    var lastY = 0, acc = 0;
    function onScroll() {
      if (!inited || W.innerWidth >= 700 || root.classList.contains("behind")) return;
      var y = W.scrollY || 0, dy = y - lastY; lastY = y;
      if ((dy > 0) !== (acc > 0)) acc = 0;
      acc += dy;
      if (y < 60) setMini(false);
      else if (acc > 26 && y > 140) setMini(true);
      else if (acc < -20) setMini(false);
    }
    function setMini(on) {
      if (on === mini) return;
      mini = on; MZ.to(on ? 1 : 0, { response: on ? .46 : .4, damping: on ? .9 : .8 });
      root.classList.toggle("tb-min", on);
      if (on) { LF.snap(0); touch = null; }
      kick(job);
    }
    function expand() { setMini(false); }
    function init(o) {
      bar = D.getElementById("tabbar"); row = D.getElementById("tabs"); if (!bar || !row) return;
      plat = bar.querySelector(".tb-plat"); lens = bar.querySelector(".tb-lens"); mat = bar.querySelector(".tb-mat");
      copies = Array.prototype.slice.call(lens.querySelectorAll(".tb-copy")).reverse();   /* [main, red, blue] (DOM: blue, red, main) */
      onSelect = o && o.onSelect || null;
      inited = true; root.classList.add("lq");
      bar.addEventListener("pointerdown", down);
      bar.addEventListener("pointermove", move);
      bar.addEventListener("pointerup", up); bar.addEventListener("pointercancel", up);
      bar.addEventListener("lostpointercapture", function (e) { if (touch && e.pointerId === touch.id) up({ pointerId: e.pointerId, type: "pointercancel", button: 0 }); });
      W.addEventListener("scroll", onScroll, { passive: true });
      W.addEventListener("resize", function () { if (MZ.t < .5) { measure(); var t = G.tabs[selIdx]; if (t) { X.snap(t.c); PW.snap(t.w); } render(); } dock.place(); });
      sync();
    }
    return { init: init, sync: sync, select: select, expand: expand, minimize: setMini, get minimized() { return mini; }, get geo() { return G; },
      render: render, _springs: { X: X, LF: LF, MZ: MZ } };
  })();

  /* ================================================================== mini player dock (follows the tab bar) */
  var dock = (function () {
    var el = null, glow = null, lastMz = -1;
    function place(force) {
      el = el || D.getElementById("mini"); glow = glow || D.getElementById("miniGlow");
      var G = tabbar.geo; if (!el || !G) return;
      var mz = clamp(tabbar._springs.MZ.x, 0, 1);
      if (!force && Math.abs(mz - lastMz) < 1e-4) return;
      lastMz = mz;
      var vw = G.vw, g = G.g, tb = G.tb != null ? G.tb : 14;
      var wf = Math.min(vw - 2 * g, 560), wm = vw - 2 * g - G.h - 10;
      el.style.width = r2(lerp(wf, wm, mz)) + "px"; el.style.left = r2(lerp((vw - wf) / 2, g, mz)) + "px";
      el.style.bottom = r2(lerp(tb + G.h + 10, tb + (G.h - 60) / 2, mz)) + "px";
      if (glow) glow.style.opacity = mz > .05 ? "0" : "";
    }
    return { place: function () { place(true); }, follow: place };
  })();

  /* ================================================================== segmented controls (thumb = small lens) */
  function seg(el) {
    if (!el || el.__lq) return el && el.__lq;
    var th = el.querySelector(".seg-th"); if (!th) return null;
    var SX = new Spring(0, { response: .36, damping: .74, eps: .05 }), SW = new Spring(0, { response: .36, damping: .86, eps: .05 }), LF = new Spring(0, { response: .22, damping: .66, eps: .001 });
    var ready = false, drag = null;
    var job = { springs: [SX, SW, LF], render: render, hold: function () { return !!drag; } };
    function btns() { return Array.prototype.filter.call(el.querySelectorAll("button"), function (b) { return !b.hidden; }); }
    function sel() { var bs = btns(); for (var i = 0; i < bs.length; i++) if (bs[i].getAttribute("aria-checked") === "true" || bs[i].getAttribute("aria-pressed") === "true") return bs[i]; return bs[0]; }
    function box(b) { var r = el.getBoundingClientRect(), q = b.getBoundingClientRect(); return { x: q.left - r.left, w: q.width }; }
    function place(anim) {
      var b = sel(); if (!b) return;
      var g = box(b); if (!g.w) return;
      if (!ready || !anim || REDUCED) { SX.snap(g.x); SW.snap(g.w); ready = true; render(); return; }
      SX.to(g.x); SW.to(g.w); kick(job);
    }
    function render() {
      var st = REDUCED ? 0 : clamp(Math.abs(SX.v) / 2400, 0, .2), l = clamp(LF.x, 0, 1.2);
      th.style.width = r2(SW.x) + "px";
      th.style.transform = "translate3d(" + r2(SX.x) + "px,0,0) scale(" + r2(1 + st + .06 * l) + "," + r2(1 - st * .4 + .1 * l) + ")";
      th.classList.toggle("lift", l > .35);
    }
    el.addEventListener("pointerdown", function (e) {
      var b = e.target.closest("button"); if (!b || e.button || !ready) return;
      drag = { id: e.pointerId, x0: e.clientX, moved: false, b: b };
      if (b === sel()) { LF.to(1); kick(job); }
    });
    el.addEventListener("pointermove", function (e) {
      if (!drag || e.pointerId !== drag.id) return;
      if (!drag.moved) { if (Math.abs(e.clientX - drag.x0) < 7 || drag.b !== sel()) return; drag.moved = true; try { el.setPointerCapture(e.pointerId); } catch (x) {} }
      var r = el.getBoundingClientRect(), w = SW.x, x = e.clientX - r.left - w / 2, lo = 2, hi = r.width - w - 2;
      if (x < lo) x = lo - Math.sqrt(lo - x) * 2; else if (x > hi) x = hi + Math.sqrt(x - hi) * 2;
      SX.to(x, { response: .18, damping: .86 }); kick(job);
    });
    function end(e) {
      if (!drag || e.pointerId !== drag.id) return;
      var d = drag; drag = null; LF.to(0, { response: .3, damping: .62 });
      if (d.moved) {
        var c = SX.x + SW.x / 2, best = null, bd = 1e9, r = el.getBoundingClientRect();
        btns().forEach(function (b) { var q = b.getBoundingClientRect(), dd = Math.abs(q.left - r.left + q.width / 2 - c); if (dd < bd) { bd = dd; best = b; } });
        SX.tune({ response: .36, damping: .74 });
        if (best && best !== sel()) { el.__lqSkip = true; best.click(); setTimeout(function () { el.__lqSkip = false; }, 0); }
        place(true);
      }
      kick(job);
    }
    el.addEventListener("pointerup", end); el.addEventListener("pointercancel", end);
    el.addEventListener("click", function (e) { if (drag && drag.moved) e.stopPropagation(); }, true);
    var mo = new MutationObserver(function () { place(true); });
    mo.observe(el, { subtree: true, attributes: true, attributeFilter: ["aria-checked", "aria-pressed", "hidden"] });
    if (W.ResizeObserver) new ResizeObserver(function () { place(false); }).observe(el);
    root.classList.add("lq");
    el.__lq = { place: place };
    place(false);
    return el.__lq;
  }
  function segAll(scope) { Array.prototype.forEach.call((scope || D).querySelectorAll(".seg"), seg); }

  /* ================================================================== sheets */
  var sheet = (function () {
    var S = null;
    var job = { springs: [], render: render };
    function present(el, o) {
      o = o || {};
      if (S && S.el !== el) finish(S);
      var again = S && S.el === el;
      var p = again ? S.p : new Spring(0, { response: .44, damping: .9, eps: .0006 });
      S = { el: el, p: p, page: D.getElementById("page"), scrim: D.getElementById("scrim"), from: again ? S.from : (o.from || null), inset: o.inset || (again ? S.inset : null), dragged: false, closing: false };
      el.style.transform = ""; el.style.clipPath = ""; el.style.webkitClipPath = "";
      S.rect = el.getBoundingClientRect();
      root.classList.add("lq-sheet");
      if (S.from) el.classList.add("lq-morph");
      p.to(1, S.from ? { response: .52, damping: .84, v: o.v || 0 } : { response: .44, damping: .9, v: o.v || 0 });
      job.springs = [p]; job.done = null;
      render(); kick(job);
    }
    function dismiss(o) {
      o = o || {};
      if (!S) { if (o.done) o.done(); return; }
      var s = S; s.closing = true;
      if (o.instant) { finish(s); if (o.done) o.done(); return; }
      if (o.vy) o.v = -o.vy / (s.rect.height || 600);
      var to = o.to || null;                                       /* a rect to shrink into (the mini player) */
      if (to && !s.dragged) { s.from = to; s.el.classList.add("lq-morph"); } else if (s.from && s.dragged) { s.from = null; s.el.classList.remove("lq-morph"); }
      s.p.to(0, to && !s.dragged ? { response: .42, damping: .9, v: o.v || 0 } : { response: .36, damping: 1, v: o.v || 0 });
      job.springs = [s.p];
      job.done = function () { finish(s); if (o.done) o.done(); };
      kick(job);
    }
    function finish(s) {
      if (!s) return;
      s.el.style.transform = ""; s.el.style.clipPath = ""; s.el.style.webkitClipPath = ""; s.el.style.removeProperty("--lq-in"); s.el.classList.remove("lq-morph");
      if (s.page) { s.page.style.transform = ""; }
      if (s.scrim) s.scrim.style.opacity = "";
      if (S === s) { S = null; root.classList.remove("lq-sheet"); }
    }
    function render() {
      var s = S; if (!s) return;
      var p = s.p.x, q = clamp(p, 0, 1), el = s.el, r = s.rect;
      if (s.from && !s.dragged) {
        var f = s.from, k = q;
        var t = lerp(f.top - r.top, 0, k), l = lerp(f.left - r.left, 0, k), rr = lerp(r.right - f.right, 0, k), b = lerp(r.bottom - f.bottom, 0, k), rad = lerp(f.height / 2, 32, k);
        var cp = "inset(" + r2(Math.max(0, t)) + "px " + r2(Math.max(0, rr)) + "px " + r2(Math.max(0, b)) + "px " + r2(Math.max(0, l)) + "px round " + r2(rad) + "px)";
        el.style.clipPath = cp; el.style.webkitClipPath = cp;
        el.style.transform = p > 1 ? "translate3d(0," + r2((1 - p) * 40) + "px,0)" : "";
        el.style.setProperty("--lq-in", String(r2(clamp((q - .25) / .55, 0, 1))));
      } else {
        el.style.clipPath = ""; el.style.webkitClipPath = "";
        var y = p >= 1 ? (1 - p) * 60 : (1 - p) * (r.height + 30);
        el.style.transform = "translate3d(0," + r2(y) + "px,0)";
        el.style.removeProperty("--lq-in");
      }
      if (s.page) {
        s.page.style.transform = "scale(" + r2(1 - .06 * q) + ")";
        if (s.inset) { var cp2 = "inset(" + s.inset[0] + "px 0 " + s.inset[1] + "px 0 round " + r2(22 * q) + "px)"; s.page.style.clipPath = cp2; s.page.style.webkitClipPath = cp2; }
      }
      if (s.scrim) s.scrim.style.opacity = String(r2(q));
    }
    function drag(el, dy) {
      if (!S || S.el !== el) return;
      S.dragged = true; S.el.classList.remove("lq-morph");
      var H = S.rect.height || 600, p = dy >= 0 ? 1 - dy / H : 1 + Math.sqrt(-dy) * 2.4 / H;
      S.p.snap(p); render();
    }
    function release(el, vy) {                                    /* not dismissed: spring back up (vy: px/s downwards) */
      if (!S || S.el !== el) return;
      S.p.to(1, { response: .4, damping: .82, v: -(vy || 0) / (S.rect.height || 600) }); job.springs = [S.p]; job.done = null; kick(job);
    }
    return { present: present, dismiss: dismiss, drag: drag, release: release, get open() { return !!S && !S.closing; } };
  })();

  /* ================================================================== touch light
     iOS 26 interactive glass lights up where the finger is: a soft bloom follows the touch inside the control and
     fades when the finger lifts. One fixed element, re-fitted to the control's rect every frame, so it follows the
     control's own press scale; its border radius clips the bloom to the control's shape. */
  var light = (function () {
    var SEL = ".hbtn.glass, .btn, .wl-go, .chip, .mini-b", el = null, on = null, last = null, pid = null, fx = .5, fy = .5, rad = "0px";
    var A = new Spring(0, { response: .16, damping: 1, eps: .004 });
    var job = { springs: [A], hold: function () { return !!on; }, render: function () {
      var t = on || last;
      if (!el) return;
      if (!t || !t.isConnected || A.x < .01) { if (el.style.visibility !== "hidden") el.style.visibility = "hidden"; return; }
      var r = t.getBoundingClientRect(), w = Math.max(1, r.width), h = Math.max(1, r.height);
      el.style.visibility = "visible";
      el.style.transform = "translate(" + r2(r.left) + "px," + r2(r.top) + "px)";
      el.style.width = r2(w) + "px"; el.style.height = r2(h) + "px"; el.style.borderRadius = rad;
      el.style.setProperty("--lx", r2(fx * w) + "px"); el.style.setProperty("--ly", r2(fy * h) + "px");
      el.style.setProperty("--lr", r2(Math.max(w, h) * .7 + 26) + "px");
      el.style.opacity = r2(clamp(A.x, 0, 1));
    } };
    function aim(e, t) { var r = t.getBoundingClientRect(); fx = clamp((e.clientX - r.left) / Math.max(1, r.width), 0, 1); fy = clamp((e.clientY - r.top) / Math.max(1, r.height), 0, 1); }
    function down(e) {
      if (REDUCED || (e.pointerType === "mouse" && e.button !== 0)) return;
      var t = e.target && e.target.closest && e.target.closest(SEL);
      if (!t || t.disabled || t.getAttribute("aria-disabled") === "true") return;
      if (!el) { el = D.createElement("i"); el.className = "lq-light"; el.setAttribute("aria-hidden", "true"); D.body.appendChild(el); }
      on = last = t; pid = e.pointerId; aim(e, t);
      try { rad = W.getComputedStyle(t).borderRadius || "0px"; } catch (x) { rad = "0px"; }
      A.to(1, { response: .14, damping: 1 }); kick(job);
    }
    function move(e) { if (on && e.pointerId === pid) aim(e, on); }
    function up(e) { if (!on || (e && e.pointerId != null && e.pointerId !== pid)) return; on = null; A.to(0, { response: .55, damping: 1 }); kick(job); }
    D.addEventListener("pointerdown", down, { capture: true, passive: true });
    D.addEventListener("pointermove", move, { capture: true, passive: true });
    D.addEventListener("pointerup", up, { capture: true, passive: true });
    D.addEventListener("pointercancel", up, { capture: true, passive: true });
    W.addEventListener("scroll", function () { if (on) up(); }, { capture: true, passive: true });
    return { get active() { return !!on; } };
  })();

  /* auto-attach to segmented controls that appear later (search view re-renders its role toggle) */
  var scanQ = 0;
  function scanSoon() { if (scanQ) return; scanQ = requestAnimationFrame(function () { scanQ = 0; segAll(); }); }
  if (W.MutationObserver) new MutationObserver(function (ms) {
    for (var i = 0; i < ms.length; i++) for (var j = 0; j < ms[i].addedNodes.length; j++) { var n = ms[i].addedNodes[j]; if (n.nodeType === 1 && (n.classList.contains("seg") || n.querySelector && n.querySelector(".seg"))) { scanSoon(); return; } }
  }).observe(D.documentElement, { childList: true, subtree: true });

  W.Liquid = { Spring: Spring, kick: kick, tabbar: tabbar, dock: dock, seg: seg, segAll: segAll, sheet: sheet, light: light, get reduced() { return REDUCED; } };
})();
