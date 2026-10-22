/* engine_stub.js: a fake MashEngine (SPEC §3) for UI development and tests.
   No audio. Timers move the playheads, level() is a BPM-synced sine pulse, art() returns null.
   Every API call is logged to window.__engineCalls as [method, ...args] (tracks reduced to {i, t}).
   Test knobs (set before acting): window.__stubDur (seconds per track, default 30),
   window.__stubLookupMs (fake lookup delay, default 350), window.__stubNoEq (eqActive=false),
   window.__stubStudio (force kind "studio"). */
(function () {
  "use strict";
  var LOG = window.__engineCalls = window.__engineCalls || [];
  function slim(x) {
    if (x && typeof x === "object" && "t" in x && "bpm" in x) return { i: x.i, t: x.t };
    if (x && typeof x === "object") { try { return JSON.parse(JSON.stringify(x)); } catch (e) { return String(x); } }
    return x;
  }
  function create(opts) {
    opts = opts || {};
    var net = !!opts.net;
    var L = { change: [], ended: [], art: [] };
    function deck() {
      return { track: null, kind: "idle", busy: false, buffering: false, playing: false, pos: 0, dur: 0, vol: 0.85,
        eq: { low: 0, mid: 0, high: 0 }, syncOn: true, rate: 1, eqActive: true, art: null };
    }
    LOG.push(["create", { net: net }]);
    var S = { mode: null, seq: false, loop: false, xf: 0.5, A: deck(), B: deck() };
    var rates = { A: 1, B: 1 }, timer = 0, raf = 0, lookups = { A: 0, B: 0 };
    var api = {};
    function log(name, args) { LOG.push([name].concat(Array.prototype.slice.call(args).map(slim))); }
    function emit() {
      if (raf) return;
      raf = requestAnimationFrame(function () { raf = 0; L.change.slice().forEach(function (f) { try { f(); } catch (e) { setTimeout(function () { throw e; }); } }); });
    }
    function durOf() { return Number(window.__stubDur) || 30; }
    function effRate(sd) { var d = S[sd]; return d.syncOn ? rates[sd] : 1; }
    function ensureTimer() {
      if (timer) return;
      var last = performance.now();
      timer = setInterval(function () {
        var now = performance.now(), dt = (now - last) / 1000; last = now;
        var any = false;
        ["A", "B"].forEach(function (sd) {
          var d = S[sd];
          if (!d.playing) return;
          any = true;
          d.pos = Math.min(d.dur, d.pos + dt * effRate(sd));
          if (d.pos >= d.dur - 1e-6) ended(sd);
        });
        if (!any && !S.A.busy && !S.B.busy) { clearInterval(timer); timer = 0; }
        emit();
      }, 50);
    }
    function ended(sd) {
      var d = S[sd];
      d.playing = false; d.pos = d.dur;
      L.ended.slice().forEach(function (f) { try { f(sd); } catch (e) {} });
      if (S.mode === "seq" || S.seq) {
        if (sd === "A" && S.B.track) { S.B.pos = 0; startDeck("B"); }
        else if (sd === "B" && S.loop && S.A.track) { S.A.pos = 0; startDeck("A"); }
      }
      emit();
    }
    function startDeck(sd) {
      var d = S[sd];
      if (!d.track) return;
      if (d.playing || d.busy) return;
      if (d.pos >= d.dur - 0.05 && d.dur) d.pos = 0;
      d.busy = true; emit();
      var token = ++lookups[sd];
      setTimeout(function () {
        if (token !== lookups[sd] || !d.busy) return;
        d.busy = false;
        d.kind = (net && !window.__stubStudio) ? "apple" : "studio";
        d.eqActive = !window.__stubNoEq;
        d.dur = durOf();
        d.playing = true;
        d.rate = effRate(sd);
        ensureTimer(); emit();
      }, window.__stubLookupMs == null ? 350 : Number(window.__stubLookupMs));
      ensureTimer();
    }
    function haltDeck(sd) { var d = S[sd]; d.playing = false; d.busy = false; lookups[sd]++; }
    function setTrack(sd, t) {
      var d = S[sd]; haltDeck(sd);
      d.track = t || null; d.kind = t ? "idle" : "idle"; d.pos = 0; d.dur = t ? durOf() : 0; d.art = null; d.buffering = false;
    }
    function applyRates(r) {
      if (r && typeof r === "object") { if (r.A > 0) rates.A = r.A; if (r.B > 0) rates.B = r.B; }
      S.A.rate = effRate("A"); S.B.rate = effRate("B");
    }

    api.gesture = function () { log("gesture", arguments); };
    api.loadPair = function (v, b, r) {
      log("loadPair", arguments);
      setTrack("A", v); setTrack("B", b); applyRates(r);
      S.mode = null; S.seq = false; emit();
    };
    api.loadDeck = function (side, t, r) {
      log("loadDeck", arguments);
      setTrack(side, t); applyRates(r); emit();
    };
    api.unload = function () {
      log("unload", arguments);
      setTrack("A", null); setTrack("B", null); S.mode = null; S.seq = false; emit();
    };
    api.play = function (side) { log("play", arguments); if (!S.mode) S.mode = side; startDeck(side); emit(); };
    api.pause = function (side) { log("pause", arguments); haltDeck(side); emit(); };
    api.toggle = function (side) {
      log("toggle", arguments);
      var d = S[side]; if (d.playing || d.busy) haltDeck(side); else { if (!S.mode) S.mode = side; startDeck(side); }
      emit();
    };
    api.stop = function (side) { log("stop", arguments); haltDeck(side); S[side].pos = 0; emit(); };
    api.seek = function (side, sec) { log("seek", arguments); var d = S[side]; d.pos = Math.max(0, Math.min(d.dur || 0, Number(sec) || 0)); emit(); };
    api.playBoth = function () { log("playBoth", arguments); S.mode = "both"; S.seq = false; startDeck("A"); startDeck("B"); emit(); };
    api.playOnly = function (side) {
      log("playOnly", arguments);
      S.mode = side; S.seq = false; haltDeck(side === "A" ? "B" : "A"); startDeck(side); emit();
    };
    api.pauseAll = function () { log("pauseAll", arguments); haltDeck("A"); haltDeck("B"); emit(); };
    api.stopAll = function () { log("stopAll", arguments); haltDeck("A"); haltDeck("B"); S.A.pos = 0; S.B.pos = 0; emit(); };
    api.resume = function () {
      log("resume", arguments);
      var m = S.mode || "both";
      if (m === "both") { startDeck("A"); startDeck("B"); }
      else if (m === "seq") { if (S.B.pos > 0 && S.A.pos >= S.A.dur) startDeck("B"); else startDeck("A"); }
      else startDeck(m);
      emit();
    };
    api.sequence = function (on) {
      log("sequence", arguments);
      S.seq = !!on;
      if (on) { haltDeck("A"); haltDeck("B"); S.A.pos = 0; S.B.pos = 0; S.mode = "seq"; startDeck("A"); }
      else if (S.mode === "seq") S.mode = null;
      emit();
    };
    api.loop = function (on) { log("loop", arguments); S.loop = !!on; emit(); };
    api.setVolume = function (side, v) { log("setVolume", arguments); S[side].vol = Math.max(0, Math.min(1, Number(v))); emit(); };
    api.setEq = function (side, band, db) { log("setEq", arguments); S[side].eq[band] = Math.max(-24, Math.min(6, Number(db))); emit(); };
    api.setSync = function (side, on) { log("setSync", arguments); S[side].syncOn = !!on; S[side].rate = effRate(side); emit(); };
    api.setRates = function (r) { log("setRates", arguments); applyRates(r); emit(); };
    api.setCrossfader = function (x) { log("setCrossfader", arguments); S.xf = Math.max(0, Math.min(1, Number(x))); emit(); };
    api.state = function () {
      function cp(d) {
        return { track: d.track, kind: d.kind, busy: d.busy, buffering: d.buffering, playing: d.playing, pos: d.pos, dur: d.dur,
          vol: d.vol, eq: { low: d.eq.low, mid: d.eq.mid, high: d.eq.high }, syncOn: d.syncOn, rate: d.rate, eqActive: d.eqActive, art: d.art };
      }
      return { mode: S.mode, seq: S.seq, loop: S.loop, xf: S.xf, A: cp(S.A), B: cp(S.B) };
    };
    api.level = function (side) {
      var d = S[side];
      if (!d.playing || !d.track) return 0;
      var bpm = d.track.bpm * effRate(side), ph = (performance.now() / 1000) * bpm / 60;
      var x = side === "A"
        ? 0.42 + 0.22 * Math.sin(ph * Math.PI * 0.5) + 0.14 * Math.sin(ph * Math.PI * 2 + 1)
        : 0.22 + 0.7 * Math.pow(Math.max(0, Math.cos(ph * Math.PI * 2)), 6);
      return Math.max(0, Math.min(1, x * (0.25 + 0.75 * d.vol)));
    };
    api.on = function (ev, fn) { if (L[ev] && typeof fn === "function") L[ev].push(fn); return api; };
    api.off = function (ev, fn) { if (L[ev]) L[ev] = L[ev].filter(function (f) { return f !== fn; }); return api; };
    api.art = function () { return null; };
    api.prefetch = function () { log("prefetch", arguments); return Promise.resolve(null); };
    api.__stub = true;
    return api;
  }
  window.MashEngine = { create: create, stub: true };
})();
