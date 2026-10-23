/* Mashup Lab v5 — audio engine. Plain browser JS, no dependencies. Defines window.MashEngine.
 *
 * const E = MashEngine.create({ net: true|false, root: document.body })
 *   net:false → never touches the network (inside Claude: CSP) → Studio Groove immediately.
 * E.gesture()                      call synchronously first in EVERY click handler that can start audio
 * E.loadPair(v, b, rates)          v→A (vocal), b→B (beat); rates {A,B}; halts both, prefetches lookups, keeps vol/EQ/xf
 * E.loadDeck(side, track, rates)   swap one deck (it keeps playing, new track from 0, if it was playing); other deck untouched
 * E.unload()                       stop all, clear tracks, suspend the AudioContext
 * E.play(s) E.pause(s) E.toggle(s) E.stop(s) E.seek(s, sec)
 * E.playBoth() E.playOnly(s) E.pauseAll() E.stopAll() E.resume()      resume = continue the last mode
 * E.sequence(on) E.loop(on)        sequence: A plays, when A ends B starts; loop: after B, A again
 *                                  (loop outside a sequence: a deck that ends restarts)
 * E.setVolume(s, 0..1) E.setEq(s, "low"|"mid"|"high", dB −24..+6) E.setSync(s, on) E.setRates({A,B})
 * E.setCrossfader(0..1)            0 = only A, 1 = only B, equal power (cos/sin), 0.5 → both ≈ .707
 * E.state() → { mode:null|"both"|"A"|"B"|"seq", seq, loop, xf, A: DeckState, B: DeckState }
 *   DeckState = { track, kind:"idle"|"apple"|"studio", busy, buffering, playing, pos, dur, vol,
 *                 eq:{low,mid,high}, syncOn, rate, eqActive, art }
 * E.level(s) → 0..1 smoothed loudness (analyser; BPM pulse when not measurable)   E.bands(s) → {low,mid,high} 0..1
 * E.on("change"|"ended"|"art", fn) / E.off(ev, fn)   change is rAF-throttled; ended(side); art(track)
 * E.art(track) → cached artwork URL | null      E.prefetch(track) → Promise (lookup only, ≤1 request / 2.5 s)
 * Track = { i, t, a, g, bpm, k, y } (k = Camelot, e.g. "8A").
 * Test hooks: E._dbg() (graph/element snapshot), MashEngine._render(opts) (offline Studio Groove render → AudioBuffer),
 *             MashEngine._pick(results, track) (iTunes match picker).
 * Design (SPEC §3.1): one AudioContext; master Gain → Compressor(−10 dB, 4:1) → out. Per deck: inp → lowshelf 220 →
 * peaking 1.1k → highshelf 4.2k → vol → xf → master, analyser on inp. Two <audio> per deck: elC (crossorigin, via
 * MediaElementSource, EQ works) and elD (direct, el.volume = vol×xf, eqActive=false). Previews are streamed, never stored.
 */
(function () {
  "use strict";
  var W = window, AC = W.AudioContext || W.webkitAudioContext, SIDES = ["A", "B"], LSK = "mashlab.it", DAY = 864e5;
  /* levels, calibrated with engine_test/test_levels.py (A ≈ B RMS, peak < 1 after the compressor) */
  var MASTER = 0.8, OUT = { A: 1.85, B: 0.75 }, LEAD = 0.5, PAD = 0.05, DRUM = 0.8, BASS = 0.42;

  function clamp(x, a, b) { x = Number(x); return isFinite(x) ? Math.min(b, Math.max(a, x)) : a; }
  function noop() {}
  function other(s) { return s === "A" ? "B" : "A"; }
  function hash(s) { var h = 2166136261; s = String(s); for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function rng(seed) { var a = seed >>> 0; return function () { a = a + 0x6D2B79F5 | 0; var t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
  function mtof(m) { return 440 * Math.pow(2, (m - 69) / 12); }
  var SILENT = (function () {
    function u(v, n) { var s = ""; for (var i = 0; i < n; i++) s += String.fromCharCode(v >> 8 * i & 255); return s; }
    var n = 400, b = "RIFF" + u(36 + n, 4) + "WAVEfmt " + u(16, 4) + u(1, 2) + u(1, 2) + u(8000, 4) + u(8000, 4) + u(1, 2) + u(8, 2) + "data" + u(n, 4);
    for (var i = 0; i < n; i++) b += "\x80";
    return "data:audio/wav;base64," + btoa(b);
  })();

  /* ---------------- music theory ---------------- */
  var NAT = [0, 2, 3, 5, 7, 8, 10], HARM = [0, 2, 3, 5, 7, 8, 11], PROG = [0, 5, 2, 6]; /* i–VI–III–VII */
  function camelot(k) { var m = /^(1[0-2]|[1-9])\s*[AB]$/i.exec(String(k || "").trim()); var n = m ? +m[1] : 8; return (8 + 7 * (n - 1)) % 12; }
  function degSemi(d, sc) { var o = Math.floor(d / 7); return o * 12 + sc[d - o * 7]; }
  function pattTempo(t) { var b = clamp(t && t.bpm, 50, 220) || 120; return t && t.g === "dnb" && b < 110 ? b * 2 : b; }
  function grooveBars(tempo) { return Math.max(8, Math.round(30 / (240 / tempo) / 4) * 4); }
  function divOf(myTempo, otherTempo) { if (!otherTempo) return 1; var r = myTempo / otherTempo; return r > 1.6 && r < 2.5 ? 2 : 1; }

  /* ---------------- Studio Groove ---------------- */
  /* lanes: k kick, c clap, s snare, h hat, oh open hat, sh shaker, rim, pc conga, dm dum, tk tek; b bass. x=1 X=1.25 o=.55 */
  var GP = {
    house: { k: "x...x...x...x...", c: "....x.......x...", oh: "..x...x...x...x.", h: ".o.o.o.o.o.o.o.o", b: "..x...x...x...x.", bt: "fat", bl: 1.6, duck: 1 },
    techhouse: { k: "x...x...x...x...", c: "....x.......x...", oh: "..x...x...x...x.", h: "xoxoxoxoxoxoxoxo", rim: "......x.......x.", b: "..x...x...x...x.", bt: "fat", bl: 1.4, duck: 1 },
    afrohouse: { k: "x...x...x...x...", c: "....o.......o...", oh: "..x...x...x...x.", sh: "xoxoxoxoxoxoxoxo", pc: "x..x..x...x..x..", b: "..x...x...x...x.", bt: "fat", bl: 1.8, duck: 1 },
    techno: { k: "x...x...x...x...", c: "....o.......o...", h: "xxXxxxXxxxXxxxXx", b: ".xx..xx..xx..xx.", bt: "fat", bl: .9, duck: 1, kf: [160, 45, .11, .42] },
    edm: { k: "x...x...x...x...", c: "....x.......x...", s: "....o.......o...", oh: "..x...x...x...x.", b: "x.x.x.x.x.x.x.x.", bt: "fat", bl: 1.7, duck: 1 },
    ukg: { k: "x.........x.....", s: "....x.......x...", h: "o.x.o.x.o.x.o.xo", rim: ".......o......o.", b: "x.........x..x..", bt: "fat", bl: 2.5, sw: .24 },
    dembow: { k: "x...x...x...x...", s: "...x..x....x..x.", h: "o.o.o.o.o.o.o.o.", b: "x..x....x..x....", bt: "fat", bl: 2.6 },
    dancehall: { k: "x..x....x..x....", rim: "....x..x....x..x", h: "o.o.o.o.o.o.o.o.", b: "x..x....x..x....", bt: "fat", bl: 2.6 },
    afro: { k: "x..x....x..x....", c: "....o.......o...", sh: "xoxoxoxoxoxoxoxo", rim: "...x..x...x..x..", pc: "......x.......x.", b: "x..x....x..x..x.", bt: "fat", bl: 2.2 },
    amapiano: { k: "o...o...o...o...", sh: "xoxoxoxoxoxoxoxo", rim: "....x.......x...", oh: "..o...o...o...o.", b: "x..x..x...x..x..", bt: "log", bl: 2.5, duck: 1, v: 1.75 },
    trap: { k: "x......x..x.....", s: "........x.......", h: "x.x.x.x.x.x.x.x.", b: "x......x..x.....", bt: "808", bl: 0, roll: 1, kf: [180, 55, .05, .2], v: 1.3 },
    boombap: { k: "x.......x.x.....", s: "....x.......x...", h: "x.o.x.o.x.o.x.o.", b: "x.......x.x.....", bt: "fat", bl: 3, sw: .2, kf: [150, 55, .08, .38] },
    rnb: { k: "x......xx.......", s: "....o.......o...", rim: "....x.......x...", h: "x.o.x.o.x.o.x.o.", b: "x......xx.......", bt: "fat", bl: 3, sw: .18, kf: [150, 55, .08, .36] },
    dnb: { k: "x.........x.....", s: "....x.......x...", h: "x.x.x.x.x.x.x.x.", rim: ".......o.......o", b: "x.........x.....", bt: "fat", bl: 0, kf: [200, 55, .04, .2] },
    mizr: { dm: "x.......x.......", tk: "..x...x.....x...", k: "o...o...o...o...", sh: "o.o.o.o.o.o.o.o.", b: "x.......x.....x.", bt: "fat", bl: 3.2 },
    pop: { k: "x.......x.x.....", s: "....x.......x...", h: "x.x.x.x.x.x.x.x.", b: "x.......x.x.....", bt: "fat", bl: 3 }
  };
  var GMAP = { house: "house", techhouse: "techhouse", afrohouse: "afrohouse", techno: "techno", edm: "edm", ukg: "ukg", regg: "dembow", latin: "dembow",
    dancehall: "dancehall", afro: "afro", amapiano: "amapiano", rnb: "rnb", dnb: "dnb", mizr: "mizr", pop: "pop", ilpop: "pop" };
  var LANES = [["k", "kick", .95], ["c", "clap", .5], ["s", "snare", .55], ["h", "hat", .12], ["oh", "ohat", .14], ["sh", "shaker", .35],
    ["rim", "rim", .4], ["pc", "conga", .45], ["dm", "dum", .6], ["tk", "tek", .4]];
  /* lead rhythms (x onset, - hold, . rest); *B = breathing bar 4 of each phrase; SLOW* for tempos ≥ 140 */
  var MOT = ["x-x-x---x-x-x---", "x---x-x-x---x-x-", "..x-x-x-x---x---", "x-x-x-x-x-------", "x--x--x-x-x-x---", "..x-x-x-x-x-x---", "x-xxx---x-xxx---", "....x-x-x-x-x---"],
    MOTB = ["x-x-x-------....", "x---x-------....", "x-x---x-----....", "x-----x-----...."],
    SLOW = ["x---x---x-------", "x-------x---x---", "x---x---x---x---", "..x---x-x-------"], SLOWB = ["x-----------....", "x---x-------...."];
  var VOW = [[800, 1150], [500, 850], [430, 1750], [650, 1080], [380, 900]]; /* a o e ah u: formants F1 F2 */
  var CURVE = (function () { var n = 1024, a = new Float32Array(n), d = Math.tanh(2); for (var i = 0; i < n; i++) a[i] = Math.tanh(2 * (i / (n - 1) * 2 - 1)) / d; return a; })();

  function gainN(c, v) { var g = c.createGain(); g.gain.value = v; return g; }
  function biq(c, type, f, q) { var b = c.createBiquadFilter(); b.type = type; b.frequency.value = f; b.Q.value = q; return b; }
  /* Vocal clean-up for mashups (plain Web Audio, works on full stereo mixes, no AI):
     "vocal" (deck A) keeps the centre of the mix, where the lead vocal sits, and removes kick/bass and stereo
     instruments; "inst" (deck B) keeps the low end (kick, bass) plus the stereo sides and cancels the centre,
     so B's own lead vocal drops out of the way. Three parallel paths, switched with short gain ramps. */
  function buildProc(c) {
    var input = c.createGain(), output = c.createGain(), g = { off: c.createGain(), vocal: c.createGain(), inst: c.createGain() };
    g.vocal.gain.value = 0; g.inst.gain.value = 0;
    input.connect(g.off); g.off.connect(output);
    var sp1 = c.createChannelSplitter(2), mid = c.createGain(); mid.gain.value = .5;      /* mid = (L + R) / 2 */
    input.connect(sp1); sp1.connect(mid, 0); sp1.connect(mid, 1);
    var h1 = biq(c, "highpass", 230, .7), h2 = biq(c, "highpass", 230, .7), lp = biq(c, "lowpass", 9500, .7), pr = biq(c, "peaking", 3000, .9);
    pr.gain.value = 2.5;
    mid.connect(h1); h1.connect(h2); h2.connect(lp); lp.connect(pr); pr.connect(g.vocal); g.vocal.connect(output);
    var l1 = biq(c, "lowpass", 160, .7), l2 = biq(c, "lowpass", 160, .7), k1 = biq(c, "highpass", 160, .7), k2 = biq(c, "highpass", 160, .7);
    input.connect(l1); l1.connect(l2); l2.connect(g.inst);                                  /* low band kept */
    input.connect(k1); k1.connect(k2);
    var sp2 = c.createChannelSplitter(2), sl = c.createGain(), sr = c.createGain(), side = c.createGain(), inv = c.createGain(), mg = c.createChannelMerger(2), mk = c.createGain();
    sl.gain.value = .5; sr.gain.value = -.5; inv.gain.value = -1; mk.gain.value = 1.7;     /* side = (L − R) / 2, make-up gain */
    k2.connect(sp2); sp2.connect(sl, 0); sp2.connect(sr, 1); sl.connect(side); sr.connect(side);
    side.connect(mg, 0, 0); side.connect(inv); inv.connect(mg, 0, 1); mg.connect(mk); mk.connect(g.inst);
    g.inst.connect(output);
    return { input: input, output: output, mode: "off", set: function (m, t) {
      if (m === this.mode) return; this.mode = m; var T = t || c.currentTime;
      ["off", "vocal", "inst"].forEach(function (k) { g[k].gain.setTargetAtTime(k === m ? 1 : 0, T, .04); });
    } };
  }
  function panBus(c, p, v, dest) { var g = gainN(c, v); if (c.createStereoPanner) { var s = c.createStereoPanner(); s.pan.value = p; g.connect(s); s.connect(dest); } else g.connect(dest); return g; }
  function noiseBuf(c) {
    if (c.__mlNoise) return c.__mlNoise;
    var n = Math.floor(c.sampleRate * 2), b = c.createBuffer(1, n, c.sampleRate), d = b.getChannelData(0), r = rng(12345);
    for (var i = 0; i < n; i++) d[i] = r() * 2 - 1;
    return (c.__mlNoise = b);
  }

  function Groove(c, dest, tr, role, tempo, div) {
    var g = this; g.ctx = c; g.role = role; g.tr = tr; g.tempo = tempo; g.dt = 15 / tempo; g.div = div || 1; g.cOff = 0;
    g.bars = grooveBars(tempo); g.kEnd = g.bars * 16; g.pc = camelot(tr.k);
    g.seed = hash((tr.i != null ? tr.i : "") + "|" + tr.t + "|" + tr.a); g.R = rng(g.seed); g.nb = noiseBuf(c); g.sw = 0; g.next = 0; g.lastT = -1;
    g.out = gainN(c, OUT[role]); g.out.connect(dest);
    if (role === "A") g.initA(); else g.initB();
  }
  var G = Groove.prototype;
  G.chord = function (bar) { return PROG[((Math.floor(bar / this.div) + this.cOff) % 4 + 4) % 4]; };
  G.time = function (k) { return this.t0 + (k + (k & 1 ? this.sw : 0)) * this.dt; };
  G.pos = function (now) { return clamp(Math.max(now, this.tStart) - this.t0, 0, this.kEnd * this.dt); };
  G.dur = function () { return this.kEnd * this.dt; };
  G.start = function (at, k0, cOff) {
    var g = this; g.cOff = cOff || 0; g.k0 = k0; g.t0 = at - k0 * g.dt; g.tStart = at; g.next = k0; g.tEnd = g.t0 + g.kEnd * g.dt;
    if (g.role === "A") { g.mel = melody(g); g.L.osc.start(at); g.L.lfo.start(at); }
  };
  G.schedule = function (until, now) {
    while (this.next < this.kEnd) {
      var k = this.next, t = this.time(k);
      if (t >= until) break;
      this.next++; this.lastT = t;
      if (t < now - .03) continue; /* too late (throttled timer): skip instead of piling up */
      if (this.role === "A") this.stepA(k, t); else this.stepB(k, t);
    }
  };
  G.retempo = function (tempo, now) {
    var g = this, k = (now - g.t0) / g.dt, dt = 15 / tempo, lt = Math.max(now, g.lastT);
    g.tempo = tempo; g.dt = dt; g.t0 = now - k * dt; g.tEnd = g.t0 + g.kEnd * dt;
    g.next = Math.max(g.next, Math.floor((lt - g.t0) / dt) + 1);
    if (g.L) g.L.dly.delayTime.setTargetAtTime(Math.min(1.4, 3 * dt), now, .1);
  };
  G.stop = function (t, fade) {
    var g = this, c = g.ctx; if (g.dead) return; g.dead = 1; fade = fade || .04;
    try { g.out.gain.cancelScheduledValues(t); g.out.gain.setTargetAtTime(0, t, fade / 3); } catch (e) {}
    if (g.L) { try { g.L.osc.stop(t + fade + .1); g.L.lfo.stop(t + fade + .1); } catch (e) {} }
    setTimeout(function () { try { g.out.disconnect(); } catch (e) {} }, Math.max(0, t - c.currentTime + fade + .25) * 1000);
  };
  /* ---- deck A: pad + vocal-like lead ---- */
  G.initA = function () {
    var g = this, c = g.ctx, L = g.L = { off: -9 }, m = 60 + g.pc;
    if (m > 66) m -= 12;
    g.mBase = m; g.pBase = 48 + g.pc; g.mizr = g.tr.g === "mizr";
    L.osc = c.createOscillator(); L.osc.type = "sawtooth"; L.osc.frequency.value = mtof(m + 7);
    L.lfo = c.createOscillator(); L.lfo.frequency.value = 5.5; L.vib = gainN(c, 0); L.lfo.connect(L.vib); L.vib.connect(L.osc.detune);
    L.env = gainN(c, 0); L.bus = gainN(c, LEAD);
    L.f1 = biq(c, "bandpass", 800, 6); L.f2 = biq(c, "bandpass", 1150, 8);
    [[L.f1, 1], [L.f2, .6], [biq(c, "lowpass", 950, .7), .28]].forEach(function (f) { var gg = gainN(c, f[1]); L.osc.connect(f[0]); f[0].connect(gg); gg.connect(L.env); });
    L.env.connect(L.bus); L.bus.connect(g.out);
    L.dly = c.createDelay(1.5); L.dly.delayTime.value = Math.min(1.4, 3 * g.dt); L.fb = gainN(c, .3); L.dlp = biq(c, "lowpass", 2400, .5); L.wet = gainN(c, .22);
    L.bus.connect(L.dly); L.dly.connect(L.dlp); L.dlp.connect(L.fb); L.fb.connect(L.dly); L.dlp.connect(L.wet); L.wet.connect(g.out);
    g.padBus = [panBus(c, -.45, PAD, g.out), panBus(c, .45, PAD, g.out)];
    g.vow = []; for (var i = 0; i < 8; i++) g.vow.push(Math.floor(g.R() * VOW.length));
  };
  G.midi = function (d, cd) { return this.mBase + degSemi(d, this.mizr && (cd === 0 || cd === 5) ? HARM : NAT); };
  G.stepA = function (k, t) {
    var s = k & 15, bar = k >> 4, span = 16 * this.div;
    if (s === 0 || k === this.k0) this.vowel(t, bar);
    if (k % span === 0 || k === this.k0) this.pad(t, (span - k % span) * this.dt, this.chord(bar));
    var n = this.mel[bar] && this.mel[bar][s];
    if (n) this.note(t, n);
  };
  G.vowel = function (t, bar) { var v = VOW[this.vow[bar % 8]]; this.L.f1.frequency.setTargetAtTime(v[0], t, .05); this.L.f2.frequency.setTargetAtTime(v[1], t, .05); };
  G.note = function (t, n) {
    var L = this.L, f = mtof(n.m), fq = L.osc.frequency, e = L.env.gain, dur = n.len * this.dt * .9, leg = t - L.off < this.dt * 1.1;
    if (n.orn) { fq.setTargetAtTime(mtof(n.orn), t, .006); fq.setTargetAtTime(f, t + .06, .012); }
    else if (leg) fq.setTargetAtTime(f, t, .015); /* 45 ms scoop from the previous note */
    else { fq.setValueAtTime(f * .944, t); fq.setTargetAtTime(f, t + .001, .015); }
    if (leg) e.setTargetAtTime(n.acc * .5, t - .02, .008);
    e.setTargetAtTime(n.acc, t, .012); e.setTargetAtTime(n.acc * .75, t + .09, .18); e.setTargetAtTime(0, t + dur, .035);
    L.vib.gain.setTargetAtTime(0, t, .02);
    if (dur > .28) L.vib.gain.setTargetAtTime(22, t + .16, .1); /* vibrato after the onset (cents) */
    L.off = t + dur;
  };
  G.pad = function (t, dur, cd) {
    var g = this, c = g.ctx, end = t + dur, tones = [[cd, 1], [cd + 2, 1], [cd + 4, .9], [cd + 6, .45]];
    [0, 1].forEach(function (j) {
      var fl = biq(c, "lowpass", 650, .7), env = c.createGain();
      fl.frequency.setTargetAtTime(1700, t, dur * .35);
      env.gain.setValueAtTime(0, t); env.gain.setTargetAtTime(1, t, .12); env.gain.setTargetAtTime(0, end - .04, .2);
      fl.connect(env); env.connect(g.padBus[j]);
      tones.forEach(function (tn) {
        var m = g.pBase + degSemi(tn[0], NAT); while (m < 55) m += 12; while (m >= 67) m -= 12;
        var o = c.createOscillator(), og = gainN(c, tn[1]);
        o.type = "sawtooth"; o.frequency.value = mtof(m); o.detune.value = (j ? 1 : -1) * (6 + 4 * g.R());
        o.connect(og); og.connect(fl); o.start(t); o.stop(end + 1.3);
      });
    });
  };
  function melody(g) {
    var R = rng(g.seed ^ 0x5bd1e995), fast = g.tempo >= 140, mo = fast ? SLOW : MOT, br = fast ? SLOWB : MOTB;
    function pk(a) { return a[Math.floor(R() * a.length)]; }
    function nat(d) { return g.mBase + degSemi(d, NAT); }
    function ok(d) { var m = nat(d); return m >= 62 && m <= 74; } /* ~D4–D5 */
    function ct(d, cd) { var r = ((d - cd) % 7 + 7) % 7; return r === 0 || r === 2 || r === 4; }
    var a0 = pk(mo), ph = [[a0, pk(mo), a0, pk(br)], [a0, pk(mo), pk(mo), pk(br)]], cur = 0, best = 99, d, out = [], dir = R() < .5 ? 1 : -1;
    for (d = -7; d < 21; d++) if (ok(d) && ct(d, g.chord(0)) && Math.abs(nat(d) - 67) < best) { best = Math.abs(nat(d) - 67); cur = d; }
    for (var bar = 0; bar < g.bars; bar++) {
      var rh = ph[(bar >> 2) & 1][bar & 3], cd = g.chord(bar), notes = {}, ons = [], s, i;
      for (s = 0; s < 16; s++) if (rh.charAt(s) === "x") ons.push(s);
      for (i = 0; i < ons.length; i++) {
        s = ons[i];
        var len = 1; while (s + len < 16 && rh.charAt(s + len) === "-") len++;
        var strong = (s & 3) === 0, end = (bar & 3) === 3 && i === ons.length - 1, nd = cur;
        if (strong || end) { /* chord tones on strong 16ths, nearest first, gentle bias to keep moving */
          var cs = [];
          for (d = cur - 5; d <= cur + 5; d++) if (ok(d) && ct(d, cd) && (!end || ((d - cd) % 7 + 7) % 7 !== 4)) cs.push(d);
          var sc = function (x) { return Math.abs(x - cur) + (x === cur ? .8 : 0) + ((x - cur) * dir < 0 ? .5 : 0); };
          cs.sort(function (x, y) { return sc(x) - sc(y); });
          if (cs.length) nd = cs[cs.length > 1 && R() < .3 ? 1 : 0];
        } else { if (R() < .22) dir = -dir; nd = cur + dir * (R() < .8 ? 1 : 2); } /* scale steps elsewhere */
        if (!ok(nd)) { dir = -dir; nd = cur + dir; if (!ok(nd)) nd = cur; }
        if (nd !== cur) dir = nd > cur ? 1 : -1;
        cur = nd;
        notes[s] = { len: len, m: g.midi(nd, cd), orn: g.mizr && len >= 2 && R() < .35 ? g.midi(nd + 1, cd) : 0, acc: strong ? 1 : .8 };
      }
      out.push(notes);
    }
    return out;
  }
  /* ---- deck B: drums + bass ---- */
  G.initB = function () {
    var g = this, c = g.ctx, key = GMAP[g.tr.g] || "pop", s;
    if (g.tr.g === "hiphop") key = g.tempo >= 115 ? "trap" : "boombap";
    var P = g.P = GP[key]; g.sw = P.sw || 0; g.out.gain.value = OUT.B * (P.v || 1);
    g.drum = gainN(c, DRUM); g.drum.connect(g.out);
    g.hp = panBus(c, .22, 1, g.drum); g.sp = panBus(c, -.25, 1, g.drum); g.pp = panBus(c, -.12, 1, g.drum);
    g.bin = gainN(c, 1); g.shp = c.createWaveShaper(); g.shp.curve = CURVE; g.duck = gainN(c, 1); g.bout = gainN(c, BASS);
    g.bin.connect(g.shp); g.shp.connect(g.duck); g.duck.connect(g.bout); g.bout.connect(g.out);
    var hits = []; for (s = 0; s < 16; s++) if (P.b.charAt(s) !== ".") hits.push(s);
    g.blen = {}; g.bLast = hits[hits.length - 1];
    hits.forEach(function (s, i) { var gap = (i + 1 < hits.length ? hits[i + 1] : hits[0] + 16) - s; g.blen[s] = P.bl ? Math.min(P.bl, gap) : gap - .3; });
  };
  G.stepB = function (k, t) {
    var g = this, P = g.P, s = k & 15, bar = k >> 4, fill = (bar & 7) === 7 && s >= 12, i, ch;
    for (i = 0; i < LANES.length; i++) {
      var ln = LANES[i], p = P[ln[0]];
      if (!p || (ch = p.charAt(s)) === ".") continue;
      if (fill && i === 0 && P.duck && s === 12) continue; /* drop the kick before the phrase downbeat */
      g[ln[1]](t, ln[2] * (ch === "X" ? 1.25 : ch === "o" ? .55 : 1) * (i ? .9 + .2 * g.R() : 1) * (s ? 1 : 1.04), s);
    }
    if (fill && s > 12) { var f = P.s ? "snare" : P.c ? "clap" : "rim"; g[f](t, .18 + .1 * (s - 12), s); }
    if (P.roll && (bar & 1) && s >= 12) g.hat(t + g.dt / 2, .1);
    if (!(bar & 7) && bar && !s) g.cym(t, .12);
    if ((ch = P.b.charAt(s)) !== ".") {
      var m = 33 + ((g.pc + NAT[g.chord(bar)] - 9) % 12 + 12) % 12; /* chord root in A1–G#2 */
      if ((bar & 1) && s === g.bLast) m += 7; /* fifth on the last hit of odd bars */
      g.bassNote(t, .55 * (ch === "o" ? .6 : 1), m, g.blen[s] * g.dt);
    }
  };
  G.osc = function (type, f, t) { var o = this.ctx.createOscillator(); o.type = type; o.frequency.setValueAtTime(f, t); return o; };
  G.env = function (t, v, att, dec, dest) { var g = this.ctx.createGain(); g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(v, t + att); g.gain.setTargetAtTime(0, t + att, dec / 4); g.connect(dest || this.drum); return g; };
  G.tone = function (type, f0, f1, pd, t, v, dec, dest) { var o = this.osc(type, f0, t); if (f1) o.frequency.exponentialRampToValueAtTime(f1, t + pd); o.connect(this.env(t, v, .002, dec, dest)); o.start(t); o.stop(t + dec * 1.7 + .02); };
  G.noise = function (t, v, ft, f, q, att, dec, dest) { var c = this.ctx, s = c.createBufferSource(); s.buffer = this.nb; var fl = biq(c, ft, f, q); s.connect(fl); fl.connect(this.env(t, v, att, dec, dest)); s.start(t, this.R() * 1.4); s.stop(t + att + dec * 1.7 + .01); };
  G.kick = function (t, v) {
    var K = this.P.kf || [165, 50, .09, .32];
    this.tone("sine", K[0], K[1], K[2], t, v, K[3]); this.noise(t, v * .2, "highpass", 3000, .7, .001, .012);
    if (this.P.duck) { var d = this.duck.gain; d.setTargetAtTime(.38, t, .006); d.setTargetAtTime(1, t + .05, .07); } /* sidechain pump */
  };
  G.clap = function (t, v) {
    var c = this.ctx, s = c.createBufferSource(), fl = biq(c, "bandpass", 1350, .9), g = c.createGain(), p = g.gain;
    s.buffer = this.nb; p.setValueAtTime(0, t);
    [[.001, 1], [.009, .25], [.0105, .9], [.019, .25], [.0205, 1]].forEach(function (x) { p.linearRampToValueAtTime(v * x[1], t + x[0]); });
    p.setTargetAtTime(0, t + .021, .045); s.connect(fl); fl.connect(g); g.connect(this.drum); s.start(t, this.R()); s.stop(t + .32);
  };
  G.snare = function (t, v) { this.noise(t, v, "highpass", 1400, .6, .001, .17); this.tone("triangle", 200, 150, .06, t, v * .55, .08); };
  G.hat = function (t, v) { this.noise(t, v, "highpass", 7800, .8, .001, .035, this.hp); };
  G.ohat = function (t, v) { this.noise(t, v, "highpass", 7400, .8, .002, .2, this.hp); };
  G.cym = function (t, v) { this.noise(t, v, "highpass", 6500, .5, .002, 1.1, this.hp); };
  G.shaker = function (t, v) { this.noise(t, v, "bandpass", 6200, 1.3, .007, .055, this.sp); };
  G.rim = function (t, v) { this.tone("triangle", 1750, 0, 0, t, v * .7, .03); this.noise(t, v * .5, "bandpass", 2600, 2, .001, .02); };
  G.conga = function (t, v, s) { var f = s % 3 === 2 ? 340 : 230; this.tone("sine", f * 1.3, f, .025, t, v, .16, this.pp); };
  G.dum = function (t, v) { this.tone("sine", 150, 92, .07, t, v, .28); this.noise(t, v * .3, "lowpass", 500, .7, .001, .04); };
  G.tek = function (t, v) { this.noise(t, v, "bandpass", 3600, 1.4, .001, .05, this.pp); this.tone("sine", 620, 0, 0, t, v * .35, .03, this.pp); };
  G.bassNote = function (t, v, m, len) {
    var g = this, c = g.ctx, f = mtof(m), type = g.P.bt, a = c.createGain(), p = a.gain, end = t + len, o, o2;
    p.setValueAtTime(0, t); a.connect(g.bin);
    if (type === "808") {
      o = g.osc("sine", f * 1.6, t); o.frequency.exponentialRampToValueAtTime(f, t + .055);
      p.linearRampToValueAtTime(v * 1.3, t + .004); p.setTargetAtTime(0, t + .02, Math.min(len, 1.2) / 2.2); p.setTargetAtTime(0, end, .03);
      o.connect(a); o.start(t); o.stop(end + .2);
    } else if (type === "log") {
      o = g.osc("sine", f * 1.8, t); o.frequency.exponentialRampToValueAtTime(f, t + .035); o2 = g.osc("triangle", f * 2, t);
      p.linearRampToValueAtTime(v * 1.3, t + .003); p.setTargetAtTime(0, t + .015, .12); p.setTargetAtTime(0, end, .03);
      var a2 = c.createGain(); a2.gain.setValueAtTime(0, t); a2.gain.linearRampToValueAtTime(v * .35, t + .002); a2.gain.setTargetAtTime(0, t + .002, .012);
      o.connect(a); o2.connect(a2); a2.connect(g.bin); o.start(t); o2.start(t); o.stop(end + .2); o2.stop(t + .1);
    } else { /* fat: 2 detuned saws + sine, filter envelope */
      var fl = biq(c, "lowpass", Math.min(4000, f * 18), 5), sub = gainN(c, .9);
      fl.frequency.setTargetAtTime(f * 3.2, t + .005, .07);
      p.linearRampToValueAtTime(v, t + .005); p.setTargetAtTime(v * .8, t + .03, .1); p.setTargetAtTime(0, end, .025);
      [-9, 9, 0].forEach(function (dt, j) { var x = g.osc(j < 2 ? "sawtooth" : "sine", f, t); x.detune.value = dt; x.connect(j < 2 ? fl : sub); x.start(t); x.stop(end + .15); });
      fl.connect(a); sub.connect(a);
    }
  };

  /* ---------------- iTunes lookup (cached; ≤1 request / 2.5 s; fetch → JSONP) ---------------- */
  var cache = {}, cacheT = 0, Q = [], qRun = false, qLast = -1e9, qTimer = 0, pend = {}, backoff = 0, jpN = 0, artFns = [];
  var diag = { ok: 0, miss: 0, fail: 0, last: "", via: "", fetchErr: "" };
  try { cache = JSON.parse(W.localStorage.getItem(LSK) || "{}") || {}; } catch (e) { cache = {}; }
  function ckey(t) { return String(t.t) + " | " + String(t.a); }
  function cget(t) {
    if (!t) return null;
    var k = ckey(t), c = cache[k];
    if (!c) return null;
    if (c.miss) { if (Date.now() - c.miss > 7 * DAY) { delete cache[k]; return null; } return c; }
    return c.p ? c : null;
  }
  function cset(t, v) { cache[ckey(t)] = v; clearTimeout(cacheT); cacheT = setTimeout(function () { try { W.localStorage.setItem(LSK, JSON.stringify(cache)); } catch (e) {} }, 300); }
  function cleanTitle(s) { return String(s || "").replace(/\s*[\(\[](?:extended|original|radio|club)(?:\s+(?:mix|edit|version))?[\)\]]/gi, "").replace(/\s+-\s+(?:extended|original|radio|club)\s+(?:mix|edit)\s*$/i, "").trim(); }
  function firstArtist(s) { return String(s || "").split(/\s*(?:,|\bfeat\.?\s|\bft\.?\s|\bfeaturing\s|\swith\s|\sx\s|\s×\s|\svs\.?\s)\s*/i)[0].trim(); }
  function norm(s) {
    return String(s || "").toLowerCase().normalize("NFD").replace(/[̀-֑ͯ-ׇ]/g, "")
      .replace(/[\(\[][^\)\]]*(?:feat|ft\.|with |extended|original|radio|club|edit|version|remaster)[^\)\]]*[\)\]]/g, " ")
      .replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  }
  var BAD = /karaoke|instrumental|tribute|made famous|in the style of/i;
  function pick(res, t) {
    var nt = norm(cleanTitle(t.t)), na = norm(firstArtist(t.a)), best = null, bs = -1, own = t.t + " " + t.a;
    (res || []).forEach(function (r) {
      if (!r || !r.previewUrl || !r.trackName) return;
      var rt = norm(r.trackName), ra = norm(r.artistName), s = 0;
      if (!rt || !nt) return;
      if (rt === nt) s = 6; else if (rt.indexOf(nt) === 0 || nt.indexOf(rt) === 0) s = 4; else if (rt.indexOf(nt) >= 0 || nt.indexOf(rt) >= 0) s = 2;
      if (na && ra && (ra.indexOf(na) >= 0 || na.indexOf(ra) >= 0)) s += 3;
      var m = BAD.exec(r.trackName + " " + (r.collectionName || "") + " " + (r.artistName || ""));
      if (m && own.toLowerCase().indexOf(m[0].toLowerCase()) < 0) s -= 3;
      if (s > bs) { bs = s; best = r; }
    });
    return bs >= 6 ? { p: String(best.previewUrl), a: best.artworkUrl100 ? String(best.artworkUrl100).replace("100x100bb", "600x600bb") : null } : null;
  }
  function fetchJSON(url) {
    return new Promise(function (res, rej) {
      if (!W.fetch) return rej(new Error("nofetch"));
      var ac = W.AbortController ? new AbortController() : null, done = false;
      var to = setTimeout(function () { done = true; if (ac) ac.abort(); rej(new Error("timeout")); }, 3500);
      W.fetch(url, ac ? { signal: ac.signal } : undefined).then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
        .then(function (j) { if (!done) { done = true; clearTimeout(to); res(j); } }, function (e) { if (!done) { done = true; clearTimeout(to); rej(e); } });
    });
  }
  function jsonp(url) {
    return new Promise(function (res, rej) {
      var cb = "__mlIT" + (++jpN) + "_" + (Date.now() % 1e6), s = document.createElement("script"), done = false;
      function fin(ok, v) { if (done) return; done = true; clearTimeout(to); W[cb] = noop; if (s.parentNode) s.parentNode.removeChild(s); if (ok) res(v); else rej(v); }
      var to = setTimeout(function () { fin(false, new Error("timeout")); }, 3500);
      W[cb] = function (j) { fin(true, j); };
      s.onerror = function () { fin(false, new Error("jsonp")); };
      s.async = true; s.src = url + "&callback=" + cb;
      (document.head || document.documentElement).appendChild(s);
    });
  }
  function hebrew(t) { return /[֐-׿]/.test(t.t + " " + t.a); }
  function urlFor(t, c) { return "https://itunes.apple.com/search?term=" + encodeURIComponent(firstArtist(t.a) + " " + cleanTitle(t.t)) + "&media=music&entity=song&limit=10&country=" + c; }
  function req(url) {
    return fetchJSON(url).then(function (j) { diag.via = "fetch"; return j; },
      function (e) { diag.fetchErr = String(e && e.message || e).slice(0, 60); return jsonp(url).then(function (j) { diag.via = "jsonp"; return j; }); });
  }
  function runFast(j) { /* a Play is waiting: ask both storefronts in parallel, outside the background queue */
    var i = Q.indexOf(j); if (i >= 0) Q.splice(i, 1);
    j.run = true; var anyOk = false;
    Promise.all(j.cs.map(function (c) { return req(urlFor(j.t, c)).then(function (json) { anyOk = true; return (json && json.results) || []; }, function () { return null; }); }))
      .then(function (arrs) {
        if (!anyOk) { diag.fail++; diag.last = "net"; backoff = Date.now() + 20000; fin(j, null); return; }
        var all = []; arrs.forEach(function (a) { if (a) all = all.concat(a); });
        var r = pick(all, j.t);
        if (r) { diag.ok++; diag.last = "ok"; cset(j.t, r); fin(j, r); artFns.forEach(function (f) { f(j.t, r); }); }
        else { diag.miss++; diag.last = "miss"; cset(j.t, { miss: Date.now() }); fin(j, null); }
      });
  }
  function lookup(t, prio) {
    if (!t) return Promise.resolve(null);
    var c = cget(t);
    if (c) return Promise.resolve(c.p ? c : null);
    if (!prio && Date.now() < backoff) return Promise.resolve(null);
    var k = ckey(t), j = pend[k];
    if (!j) { j = pend[k] = { t: t, k: k, ci: 0, cs: hebrew(t) ? ["il", "us"] : ["us", "il"] }; j.pr = new Promise(function (r) { j.res = r; }); Q.push(j); }
    if (prio && !j.run) { runFast(j); return j.pr; }
    pump();
    return j.pr;
  }
  function fin(j, v) { var i = Q.indexOf(j); if (i >= 0) Q.splice(i, 1); delete pend[j.k]; j.res(v); }
  function pump() {
    if (qRun || !Q.length || qTimer) return;
    var w = qLast + 2500 - Date.now();
    if (w > 0) { qTimer = setTimeout(function () { qTimer = 0; pump(); }, w); return; }
    var j = Q[0], url = "https://itunes.apple.com/search?term=" + encodeURIComponent(firstArtist(j.t.a) + " " + cleanTitle(j.t.t)) +
      "&media=music&entity=song&limit=10&country=" + j.cs[j.ci];
    qRun = true; qLast = Date.now(); j.run = true;
    req(url).then(function (json) {
      qRun = false; j.run = false;
      if (!pend[j.k]) { pump(); return; } /* already answered by a fast (Play) lookup */
      var r = pick(json && json.results, j.t);
      if (r) { diag.ok++; diag.last = "ok"; cset(j.t, r); fin(j, r); artFns.forEach(function (f) { f(j.t, r); }); }
      else if (++j.ci >= j.cs.length) { diag.miss++; diag.last = "miss"; cset(j.t, { miss: Date.now() }); fin(j, null); }
      pump();
    }, function () { /* network failure: not cached, 20 s back-off for background lookups; Plays still try */
      qRun = false; j.run = false; backoff = Date.now() + 20000; diag.fail++; diag.last = "net";
      Q.slice().forEach(function (x) { if (!x.run) fin(x, null); }); Q = Q.filter(function (x) { return x.run; });
    });
  }

  /* ---------------- engine ---------------- */
  function create(opts) {
    opts = opts || {};
    var net = opts.net !== false, root = opts.root || null, api = {}, ctx = null, master = null, comp = null, cors = null, unlocked = false, tickId = 0;
    var L = { change: [], ended: [], art: [], wp: [] }, raf = 0, rafTO = 0, msTitle = "", msInit = false;
    var S = { mode: null, seq: false, loop: false, xf: .5, cur: "A", clean: true, hold: 0, beat: "off", cue: "", bsync: true, pb: false, useBuf: true, keyMatch: true, loud: true, plan: null, vgate: true }, rates = { A: 1, B: 1 }, D = {};
    SIDES.forEach(function (s) {
      D[s] = { side: s, track: null, kind: "idle", busy: false, buffering: false, playing: false, pos: 0, dur: 0, vol: .85, eq: { low: 0, mid: 0, high: 0 },
        syncOn: true, rate: 1, eqActive: true, art: null, tok: 0, lv: 0, n: null, elC: null, elD: null, el: null, src: null, groove: null, url: null, sil: 0, why: "",
        gate: 1, dip: 0, holdT: 0, playT: 0, moveT: 0, seekN: 0, grid: null, gridFor: null, gridDone: false,
        bmode: false, buf: null, sb: null, sr: 1, bs: null, t0: 0, o0: 0, ready: false, waitT: 0, noBuf: null, bsync: false, semis: 0, trim: 1 };
    });
    function guard(fn) { return function () { try { return fn.apply(null, arguments); } catch (e) { try { console.warn("[MashEngine]", e); } catch (x) {} } }; }
    function fire(ev, arg) { L[ev].slice().forEach(function (f) { try { f(arg); } catch (e) { setTimeout(function () { throw e; }); } }); }
    function procMode(d) { /* clean-up only while both decks play a mashup together, on Apple previews routed through Web Audio */
      if (!S.clean || S.mode !== "both" || performance.now() < S.hold) return "off";
      if (!bp(D.A) || !bp(D.B) || d.kind !== "apple" || !(d.bmode || d.el === d.elC)) return "off";
      if (d.side === "B") { var P = planFor(d); if (P && P.cleanB === false) return "off"; }
      return d.side === "A" ? "vocal" : "inst";
    }
    function applyProc() { SIDES.forEach(function (s) { var d = D[s]; if (d.n && d.n.proc) { var m = procMode(d), was = d.n.proc.mode; d.n.proc.set(m); if (m !== was && d.side === "A") voxGate(d); } }); }
    function flush() { if (!raf) return; try { cancelAnimationFrame(raf); } catch (e) {} clearTimeout(rafTO); raf = 0; try { applyProc(); } catch (e) {} media(); fire("change"); }
    function emit() { if (raf) return; raf = W.requestAnimationFrame ? requestAnimationFrame(flush) : -1; rafTO = setTimeout(flush, 250); }
    function bp(d) { return !!(d.playing || d.busy); }
    function xfg(s) { return s === "A" ? Math.cos(S.xf * Math.PI / 2) : Math.sin(S.xf * Math.PI / 2); }
    function effRate(d) { return d.syncOn ? rates[d.side] : 1; }
    function tempoOf(d) { return d.track ? pattTempo(d.track) * effRate(d) : 120; }
    function now() { return ctx ? ctx.currentTime : 0; }

    /* ---- audio graph ---- */
    function deckGraph(c, dest) {
      var n = { inp: c.createGain(), lo: biq(c, "lowshelf", 220, .7), mid: biq(c, "peaking", 1100, .8), hi: biq(c, "highshelf", 4200, .7), vol: c.createGain(), gate: c.createGain(), xf: c.createGain(), an: c.createAnalyser() };
      n.an.fftSize = 1024; n.an.smoothingTimeConstant = .6; n.an.minDecibels = -90; n.an.maxDecibels = -12;
      /* gate: mutes a deck that waits to enter on the beat (beat sync); vol / xf stay the user's */
      n.vg = c.createGain(); n.proc = buildProc(c); n.inp.connect(n.proc.input); n.proc.output.connect(n.vg); n.vg.connect(n.lo); n.lo.connect(n.mid); n.mid.connect(n.hi); n.hi.connect(n.vol); n.vol.connect(n.gate); n.gate.connect(n.xf); n.xf.connect(dest); n.inp.connect(n.an);
      n.buf = new Float32Array(n.an.fftSize); n.fb = new Uint8Array(n.an.frequencyBinCount);
      return n;
    }
    function ensureCtx() {
      if (ctx || !AC) return ctx;
      try { ctx = new AC({ latencyHint: "playback" }); } catch (e) { try { ctx = new AC(); } catch (e2) { return null; } }
      master = gainN(ctx, MASTER); comp = ctx.createDynamicsCompressor(); comp.threshold.value = -10; comp.ratio.value = 4;
      master.connect(comp); comp.connect(ctx.destination);
      SIDES.forEach(function (s) { D[s].n = deckGraph(ctx, master); applyGains(D[s], true); hookC(D[s]); });
      noiseBuf(ctx);
      return ctx;
    }
    function resumeCtx() { if (ctx && ctx.state !== "running" && ctx.state !== "closed") { try { var p = ctx.resume(); if (p && p.catch) p.catch(noop); } catch (e) {} } }
    function hookC(d) {
      if (!ctx || !d.elC || d.src) return;
      try { d.src = ctx.createMediaElementSource(d.elC); d.src.connect(d.n.inp); } catch (e) { d.src = null; }
    }
    function setP(p, v, instant) { if (!ctx) return; try { if (instant) { p.cancelScheduledValues(0); p.value = v; } else { p.cancelScheduledValues(ctx.currentTime); p.setTargetAtTime(v, ctx.currentTime, .03); } } catch (e) { p.value = v; } }
    function applyGains(d, instant) {
      var n = d.n;
      if (n) { setP(n.vol.gain, d.vol * (d.trim || 1), instant); setP(n.xf.gain, xfg(d.side), instant); setP(n.lo.gain, d.eq.low, instant); setP(n.mid.gain, d.eq.mid, instant); setP(n.hi.gain, d.eq.high, instant); }
      if (d.elD) { var v = clamp(d.vol * xfg(d.side), 0, 1); d.elD.volume = v; d.elD.muted = v < .02; }
    }

    /* ---- media elements ---- */
    function isData(el) { return String(el.currentSrc || el.getAttribute("src") || "").indexOf("data:") === 0; }
    function pitch(el, r) { el.playbackRate = r; el.defaultPlaybackRate = r; el.preservesPitch = true; el.webkitPreservesPitch = true; el.mozPreservesPitch = true; }
    function mkEl(d, withCors) {
      var el = document.createElement("audio");
      el.setAttribute("playsinline", ""); el.setAttribute("webkit-playsinline", ""); el.preload = "auto"; el.style.display = "none";
      if (withCors) el.crossOrigin = "anonymous";
      pitch(el, 1);
      ["playing", "waiting", "pause", "ended", "error", "loadedmetadata", "durationchange"].forEach(function (ev) { el.addEventListener(ev, guard(function () { elEvent(d, el, ev); })); });
      try { (root || document.body || document.documentElement).appendChild(el); } catch (e) {}
      return el;
    }
    function ensureEls() { SIDES.forEach(function (s) { var d = D[s]; if (!d.elC) { d.elC = mkEl(d, true); d.elD = mkEl(d, false); applyGains(d, true); } hookC(d); }); }
    function clearSrc(el) { if (!el || !el._u) return; el._u = null; try { el.pause(); el.removeAttribute("src"); el.load(); } catch (e) {} }
    function elEvent(d, el, ev) {
      if (el !== d.el || d.kind !== "apple" || isData(el)) return;
      if (ev === "waiting") { d.buffering = true; emit(); }
      else if (ev === "playing") { d.buffering = false; emit(); }
      else if (ev === "loadedmetadata" || ev === "durationchange") {
        if (el._seek) { var sk = el._seek; el._seek = 0; if (Math.abs((el.currentTime || 0) - sk) > .5) try { el.currentTime = sk; } catch (e) {} } /* #t= not honoured */
        if (isFinite(el.duration) && el.duration > 0) { d.dur = el.duration; emit(); }
      }
      else if (ev === "pause") { if (d.playing && !el.ended) { d.playing = false; d.pos = el.currentTime || d.pos; emit(); } } /* external pause (iOS interruption) */
      else if (ev === "ended") { if (d.playing) ended(d, 0); }
      else if (ev === "error") {
        if (d.busy) appleFail(d, d.tok, "MediaError", el === d.elD);
        else if (d.playing) { d.pos = el.currentTime || d.pos; d.why = "media"; startStudio(d); } /* error mid-play → Studio Groove */
      }
    }
    function stopApple(d, drop) {
      [d.elC, d.elD].forEach(function (el) { if (!el || !el._u) return; if (drop || el !== d.el) clearSrc(el); else try { el.pause(); } catch (e) {} });
      if (drop) d.el = null;
    }
    function startApple(d, url, direct) {
      bufStop(d); d.bmode = false; d.ready = false; d.waitT = 0; d.bsync = false;
      ensureEls();
      if (!direct && cors !== false) { ensureCtx(); hookC(d); }
      direct = direct || cors === false || !d.src;
      stopGroove(d);
      var el = direct ? d.elD : d.elC, alt = direct ? d.elC : d.elD, tok = ++d.tok, pos = d.pos > .25 && (!d.dur || d.pos < d.dur - .5) ? d.pos : 0;
      clearSrc(alt);
      d.kind = "apple"; d.url = url; d.el = el; d.eqActive = !direct; d.busy = true; d.playing = false; d.buffering = false; d.sil = 0; d.playT = 0; d.moveT = performance.now();
      if (holdFor(d)) gateClose(d); else gateOpen(d, 0, .03);   /* joining a playing mashup: start muted, enter on the beat */
      if (el._u !== url) { el._u = url; el._seek = pos; el.src = pos ? url + "#t=" + pos.toFixed(2) : url; }
      else if (Math.abs((el.currentTime || 0) - pos) > .3) { try { el.currentTime = pos; } catch (e) {} }
      pitch(el, d.rate = effRate(d)); applyGains(d);
      var p; try { p = el.play(); } catch (e) { p = Promise.reject(e); }
      if (!p || !p.then) p = Promise.resolve();
      p.then(function () { if (tok !== d.tok) return; d.busy = false; d.playing = true; d.playT = performance.now(); d.why = ""; d.retry = false; ensureTick(); emit(); },
        function (e) { appleFail(d, tok, e && e.name, direct); });
      ensureTick(); emit();
    }
    function appleFail(d, tok, name, direct) {
      if (tok !== d.tok || d.kind !== "apple") return;
      if (name === "AbortError" && d.el && !d.el.paused) return;
      if (name === "NotAllowedError") { d.why = "blocked"; startStudio(d); return; } /* iOS refused: a second tap plays the (now cached) original */
      if (!d.retry) { /* one retry on the same element first: a flaky (mobile) network must not be mistaken for missing CORS */
        d.retry = true; var rt = d.tok;
        setTimeout(guard(function () { if (rt === d.tok && d.kind === "apple" && d.busy) { clearSrc(direct ? d.elD : d.elC); startApple(d, d.url, direct); } }), 500);
        return;
      }
      if (!direct) { /* failed twice through Web Audio: unknown CORS → assume none; known CORS → just this deck goes direct */
        if (cors !== true) cors = false;
        d.retry = false; startApple(d, d.url, true); return;
      }
      d.why = "media";
      startStudio(d); /* never silent: Studio Groove */
    }
    function switchDirect(d) { var pos = d.el ? d.el.currentTime : d.pos; cors = false; d.pos = pos; startApple(d, d.url, true); }

    /* ---- Studio Groove decks ---- */
    function stopGroove(d, fade) { if (d.groove) { d.groove.stop(now(), fade); d.groove = null; } }
    function alignStart(N, O, ref, k0) { /* quantize to O's next beat; match bar phase + chord when spans agree */
      var beat = 4 * O.dt, kb = Math.ceil((Math.max(ref, O.tStart) - O.t0) / beat - 1e-6), tb = O.t0 + kb * beat;
      var SO = 16 * O.div, SN = 16 * N.div;
      if (Math.abs(SO * O.dt / (SN * N.dt) - 1) > .03) return { at: tb, k0: k0 - k0 % 4, cOff: 0 };
      var kO = kb * 4, idx = Math.floor(k0 / SN), kN = idx * SN + Math.round((kO % SO) / SO * SN), cO = (Math.floor(kO / SO) + O.cOff) % 4;
      if (kN >= N.kEnd - 4) { kN = Math.round((kO % SO) / SO * SN); idx = 0; }
      return { at: tb, k0: kN, cOff: ((cO - idx) % 4 + 4) % 4 };
    }
    function startStudio(d, o) {
      o = o || {};
      stopApple(d, false); stopGroove(d); bufStop(d); d.bmode = false; d.ready = false; d.waitT = 0; d.bsync = false;
      d.tok++; d.kind = "studio"; d.eqActive = true; d.busy = false; d.buffering = false; d.playing = false; d.rate = effRate(d);
      if (!ensureCtx()) { emit(); return; }
      resumeCtx(); gateOpen(d, 0, .02); /* Studio Groove schedules its own beat grid: never muted */
      var O = D[other(d.side)], my = tempoOf(d), g = new Groove(ctx, d.n.inp, d.track, d.side, my, divOf(my, O.track ? tempoOf(O) : 0));
      var k0 = Math.round(clamp(d.pos, 0, 1e4) / g.dt), at = Math.max(ctx.currentTime + .04, o.at || 0), cOff = 0;
      if (k0 >= g.kEnd - 4) k0 = 0;
      k0 -= k0 % 4;
      if (O.groove && !O.groove.dead) { var r = alignStart(g, O.groove, at, k0); at = r.at; k0 = r.k0; cOff = r.cOff; }
      g.start(at, k0, cOff); d.groove = g; d.playing = true; d.dur = g.dur();
      g.schedule(ctx.currentTime + lookahead(), ctx.currentTime);
      ensureTick(); emit();
    }
    function lookahead() { return document.hidden ? 1.2 : .16; }
    function ensureTick() { if (!tickId) tickId = setInterval(guard(tick), 25); }
    function tick() {
      var t = now(), act = false;
      SIDES.forEach(function (s) {
        var d = D[s], g = d.groove;
        if (g && d.playing) { act = true; g.schedule(t + lookahead(), t); if (t >= g.tEnd - .03) ended(d, g.tEnd); }
        if (d.kind === "apple" && d.playing && d.el && d.el === d.elC && cors !== true && d.n) watchdog(d);
        if (d.kind === "apple" && d.url && S.mode === "both" && !d.bmode) wantGrid(d);
        if (bp(d)) act = true;
      });
      try { bufTick(); } catch (e) {}
      try { alignTick(); } catch (e) {}
      if (!act) { clearInterval(tickId); tickId = 0; }
    }
    function peakOf(d) { var n = d.n, b = n.buf, m = 0; try { n.an.getFloatTimeDomainData(b); } catch (e) { return 1; } for (var i = 0; i < b.length; i++) { var v = b[i] < 0 ? -b[i] : b[i]; if (v > m) m = v; } return m; }
    function watchdog(d) { /* elC playing silence (no CORS data) for 1.8 s → direct element */
      if (peakOf(d) > 1e-4) { cors = true; d.sil = 0; return; }
      if (d.el.currentTime <= .8 || d.el.paused) { d.sil = 0; return; }
      var pn = performance.now();
      if (!d.sil) d.sil = pn; else if (pn - d.sil > 3000) switchDirect(d); /* 3 s of pure digital silence → CORS-blocked data */
    }

    /* ---- beat sync (one-shot and silent: safe on iPhone Safari, which glitches on every tempo change or jump
       of an AUDIBLE track) ----
       The deck that joins a playing mashup (the vocal, when both start together) is the follower. It starts muted
       by its gate, gets ONE tempo setting (pitch preserved) and at most 3 beat-accurate jumps while muted, then fades
       in on the leader's next beat 1 or 3. After that nothing touches the playback. If the follower is already
       audible (its beat grid came late, the user moved it), the fix happens inside a short dip instead of a jump.
       Safety: the audio thread itself re-opens a gate after HOLD_MAX, so a deck can never stay muted. */
    var HOLD_GRID = 4500, HOLD_ALIGN = 3500, HOLD_MAX = 9000, HOLD_LEAD = 1500;
    function wantGrid(d) {
      if (!net || !d.track) return;
      var c = cget(d.track), url = d.url || (c && c.p) || null;
      if (!url || d.gridFor === url) return;
      d.gridFor = url; d.grid = null; d.gridDone = false;
      grid(url, d.track.bpm).then(guard(function (g) { if (d.gridFor !== url) return; d.grid = g && g.conf >= 2 ? g : null; d.gridDone = true; ensureTick(); emit(); }));
    }
    function downbeat(g) { var p = 60 / g.bpm, t = g.b0 + g.db * p; while (t < .3) t += 4 * p; return t; }
    function gateNow(d) { /* the gate gain right now; known values first (older Safari may report a stale AudioParam.value) */
      var t = ctx.currentTime;
      if (d.gate === 0 && !d.dip && t > (d.gEnd || 0) && t < (d.gFall || 0)) return 0;
      if (d.gate === 1 && !d.dip && t > (d.gEnd || 0)) return 1;
      return d.n.gate.gain.value;
    }
    function gateRamp(d, v, at, dur) { /* gate gain → v, from ctx time `at` (default now), over dur seconds */
      var from = d.n && ctx ? gateNow(d) : v;
      d.gate = v;
      if (!d.n || !ctx) return;
      var p = d.n.gate.gain, t0 = ctx.currentTime, t = Math.max(t0, at || 0);
      d.gEnd = t + (dur || .03); d.gFall = 0;
      try { p.cancelScheduledValues(t0); p.setValueAtTime(from, t0); if (t > t0) p.setValueAtTime(from, t); p.linearRampToValueAtTime(v, d.gEnd); }
      catch (e) { try { p.value = v; } catch (x) {} }
    }
    function gateClose(d) { /* muted now; the audio thread re-opens it after HOLD_MAX even if timers stall (locked screen) */
      gateRamp(d, 0, 0, .006); d.holdT = performance.now(); d.dip = 0;
      if (d.n && ctx) try { var p = d.n.gate.gain, T = ctx.currentTime + HOLD_MAX / 1000; p.setValueAtTime(0, T); p.linearRampToValueAtTime(1, T + .4); d.gFall = T; } catch (e) {}
    }
    function gateOpen(d, at, dur) { if (d.gate !== 1 || d.dip) gateRamp(d, 1, at, dur || .08); d.gate = 1; d.holdT = 0; d.dip = 0; }
    function blocked() { return performance.now() < S.hold || document.hidden; } /* a word-play handoff runs its own timing; background timers are coarse */
    function gridFail(d) { return !!(d.gridDone && !d.grid); }
    function holdFor(d) { /* should deck d start muted, to enter in sync? */
      var O = D[other(d.side)];
      if (!net || !S.bsync || S.mode !== "both" || blocked() || !d.syncOn || !O.syncOn || !O.track || !d.track) return false;
      if (d.el !== d.elC || !d.n || cors === false || O.kind === "studio" || gridFail(d) || gridFail(O)) return false;
      if (O.playing && O.gate === 1) return true;               /* the other deck is already sounding: I join it */
      return !!S.pb && d.side === "A" && !O.playing;            /* both start together: the vocal waits for the beat */
    }
    function holdOk(d, O) { /* may a muted follower keep waiting? */
      return S.bsync && S.mode === "both" && !blocked() && d.syncOn && O.syncOn && d.kind === "apple" && d.el === d.elC && !!O.track &&
        O.kind !== "studio" && (O.playing || O.busy) && !gridFail(d) && !gridFail(O);
    }
    var al = { key: "", F: "A", done: true, ok: false, next: 0, samples: [], fixes: 0, q: 1, rF: 1, t0: 0, seeks: 0, rateSets: 0, dips: 0, lag: .02, err: null, opened: "" }; /* lag: typical seek latency, learnt per device */
    function superviseGates(pn) {
      SIDES.forEach(function (s) {
        var d = D[s], O = D[other(s)];
        if (d.gate === 1 || !d.playing) return;                                         /* still loading: no sound anyway */
        var t = pn - (d.playT || pn), both = O.playing && O.playT ? pn - Math.max(d.playT, O.playT) : -1, why = "";
        if (!holdOk(d, O)) why = "nosync";
        else if (!O.playing && t > HOLD_LEAD) why = "lead";                             /* the other deck is still loading */
        else if (t > HOLD_MAX) why = "max";
        else if (both > HOLD_GRID && (!d.grid || !O.grid)) why = "grid";                /* beat grid late: play, fix later in a dip */
        else if (al.key && al.F === s && !al.done && pn - al.t0 > HOLD_ALIGN) why = "align";
        if (why) { gateOpen(d, 0, why === "nosync" ? .12 : .35); al.opened = why; emit(); }  /* waiting no longer makes sense → now; a timeout → soft fade */
      });
    }
    function phaseErr(F, L) { /* real seconds, positive = follower ahead; e in leader beats, wrapped to the common bar */
      var gF = F.grid, gL = L.grid, q = al.q, pF = 60 / gF.bpm, pL = 60 / gL.bpm, rL = L.el.playbackRate || 1, M = q === .5 ? 8 : 4;
      var xF = ((F.el.currentTime - gF.b0) / pF - gF.db) / q, xL = (L.el.currentTime - gL.b0) / pL - gL.db, e = (xF - xL) % M;
      if (e >= M / 2) e -= M; if (e < -M / 2) e += M;
      return { s: e * pL / rL, beats: e };
    }
    function median(a) { var b = a.slice().sort(function (x, y) { return x.s - y.s; }); return b[b.length >> 1]; }
    function jump(F, m) { /* beat-accurate jump of the follower, relative to where it is now (+ learnt seek latency) */
      var el = F.el, pF = 60 / F.grid.bpm, per = (al.q === .5 ? 8 : 4) * al.q * pF, nt = el.currentTime - m.beats * al.q * pF + Math.max(0, Math.min(.12, al.lag)) * (el.playbackRate || 1);
      if (nt < .05) nt += per;
      if (el.duration && nt > el.duration - 1) nt -= per;
      try { el.currentTime = Math.max(0, nt); } catch (x) {}
      al.seeks++;
    }
    function dipDo(d, fn) { /* audible follower: fade out 40 ms → fn() → fade back in after 'seeked' (by 0.76 s at the latest) */
      if (!d.n || !ctx || d.el !== d.elC) return false;
      var p = d.n.gate.gain, t0 = ctx.currentTime, el = d.el, tok = d.tok, t1 = performance.now(), from = gateNow(d);
      try { p.cancelScheduledValues(t0); p.setValueAtTime(from, t0); p.linearRampToValueAtTime(0, t0 + .04); p.setValueAtTime(0, t0 + .6); p.linearRampToValueAtTime(1, t0 + .76); } catch (e) { return false; }
      d.dip = t1; d.gEnd = t0 + .76; al.dips++;
      setTimeout(guard(function () {
        if (tok !== d.tok || el !== d.el || performance.now() - t1 > 450) { d.dip = 0; return; } /* timer came too late: skip */
        fn();
        var up = guard(function () {
          if (!d.dip || d.dip !== t1 || !ctx) return;
          var q = d.n.gate.gain, t = ctx.currentTime, v0 = t < t0 + .6 ? 0 : q.value; d.dip = 0; d.gEnd = t + .16;
          try { q.cancelScheduledValues(t); q.setValueAtTime(v0, t); q.linearRampToValueAtTime(1, t + .16); } catch (e) {}
        });
        if (el.seeking) { var h = function () { el.removeEventListener("seeked", h); setTimeout(up, 60); }; el.addEventListener("seeked", h); setTimeout(up, 500); }
        else setTimeout(up, 120);
      }), 50);
      return true;
    }
    function nextEntry(L) { /* ctx time just before the leader's next beat 1 or 3 (≥ 0.12 s ahead) */
      var g = L.grid, r = L.el.playbackRate || 1, p = 60 / g.bpm, x = (L.el.currentTime - g.b0) / p - g.db, lead = .12 * r / p, k = Math.ceil((x + lead) / 2) * 2;
      return ctx.currentTime + Math.max(0, (k - x) * p / r - .05);
    }
    function finish(F, L, m) {
      al.done = true; al.ok = !!(m && Math.abs(m.s) <= .04);
      if (F.gate !== 1) gateOpen(F, al.ok ? nextEntry(L) : 0, al.ok ? .07 : .3);
    }
    function syncUi() {
      var cue, b;
      if (D.A.bmode || D.B.bmode) { /* decoded decks: "aligning" while one waits to enter on the beat, "locked" once both run synced */
        var t = ctx ? ctx.currentTime : 0;
        cue = SIDES.filter(function (s) { var d = D[s], O = D[other(s)]; return d.bmode && O.playing && S.mode === "both" && (d.busy || (d.playing && d.t0 > t + .01)); })[0] || "";
        b = cue ? "aligning" : D.A.bsync && D.B.bsync && D.A.playing && D.B.playing ? "locked" : "off";
      } else {
        cue = D.A.gate !== 1 && bp(D.A) ? "A" : D.B.gate !== 1 && bp(D.B) ? "B" : "";
        b = cue || (al.key && !al.done) ? "aligning" : al.key && al.done && al.ok ? "locked" : "off";
      }
      if (b !== S.beat || cue !== S.cue) { S.beat = b; S.cue = cue; emit(); }
    }
    function alignTick() {
      var pn = performance.now(), A = D.A, B = D.B;
      superviseGates(pn);
      var on = S.bsync && S.mode === "both" && !blocked() && A.kind === "apple" && B.kind === "apple" && A.playing && B.playing && A.el && B.el &&
        A.grid && B.grid && A.syncOn && B.syncOn && !A.el.paused && !B.el.paused;
      if (!on) { al.key = ""; syncUi(); return; }
      var key = [A.url, B.url, A.tok, B.tok, A.seekN, B.seekN].join("|");  /* a new play / track / user seek → align once more */
      if (key !== al.key) {
        var fs = A.gate !== 1 ? "A" : B.gate !== 1 ? "B" : B.moveT > A.moveT ? "B" : "A", F = D[fs], L = D[other(fs)];
        var effL = L.grid.bpm * (L.el.playbackRate || 1), q = [.5, 1, 2].reduce(function (x, y) { return Math.abs(F.grid.bpm - effL * y) < Math.abs(F.grid.bpm - effL * x) ? y : x; }, 1);
        al = { key: key, F: fs, q: q, rF: effL * q / F.grid.bpm, done: false, ok: false, t0: pn, next: pn + 350, samples: [], fixes: 0, lastF: -1, lastL: -1,
          seeks: al.seeks, rateSets: al.rateSets, dips: al.dips, lag: al.lag, err: null, opened: "", needRate: false };
        if (al.rF < .9 || al.rF > 1.1 || F.el !== F.elC) { finish(F, L, null); syncUi(); return; }
        if (Math.abs((F.el.playbackRate || 1) - al.rF) > .0008) {
          if (F.gate !== 1) { pitch(F.el, al.rF); al.rateSets++; } else al.needRate = true;   /* the only tempo change */
        }
        F.rate = al.rF; syncUi(); return;
      }
      if (al.done) return;
      var F = D[al.F], L = D[other(al.F)];
      SIDES.forEach(function (s) { if (D[s].dip && pn - D[s].dip > 1500) D[s].dip = 0; }); /* a dip whose timers never ran (background) */
      if (pn < al.next || F.el.seeking || L.el.seeking || F.buffering || L.buffering || F.dip || L.dip) return;
      var tf = F.el.currentTime, tl = L.el.currentTime;
      if (tf === al.lastF || tl === al.lastL) { al.lastF = tf; al.lastL = tl; al.samples = []; al.next = pn + 60; return; } /* a clock is not running yet */
      al.lastF = tf; al.lastL = tl;
      al.samples.push(phaseErr(F, L));
      if (al.samples.length < 6) { al.next = pn + 40; return; }
      var m = median(al.samples); al.samples = []; al.err = m.s;
      if (al.fixes > 0 && Math.abs(m.s) < .09) al.lag = clamp(al.lag - m.s, -.05, .15); /* learn how late a jump lands (seek latency) */
      var muted = F.gate !== 1, tol = muted ? .012 : .02;
      if ((Math.abs(m.s) <= tol && !al.needRate) || al.fixes >= (muted ? 3 : 2)) { finish(F, L, m); syncUi(); return; }
      if (muted) { jump(F, m); al.fixes++; al.next = pn + 300; return; }
      var big = Math.abs(m.s) > tol, k = al.key;
      if (!dipDo(F, function () { if (al.key !== k) return; if (al.needRate) { pitch(F.el, al.rF); al.rateSets++; al.needRate = false; } if (big) jump(F, m); })) { finish(F, L, m); syncUi(); return; }
      al.fixes++; al.next = pn + 950;
    }

    /* ---- decoded-buffer decks: the main way to play Apple previews ----
       The preview is fetched once (CORS), decoded into memory and played by an AudioBufferSourceNode, so both decks
       run on the AudioContext clock and a synced start is exact to the sample: no seeking, no tempo nudging and no
       media-element path (Safari feeds <audio> into Web Audio through an adaptive buffer that shifts each deck by
       tens of ms and sometimes speeds it up). The follower is time-stretched once (pitch kept) to the leader's tempo
       and started on the leader's next beat 1 or 3 with the same bar phase. Audio stays in memory for this page only. */
    var BUF = {}, RAW = {};
    function bufOk(d, url) { return net && !!AC && !!W.fetch && cors !== false && S.useBuf && !(d && url && d.noBuf === url) && !!ensureCtx(); }
    function fetchBytes(url) {
      return new Promise(function (res, rej) {
        var ac = W.AbortController ? new AbortController() : null, done = false, o = { mode: "cors", credentials: "omit" };
        if (ac) o.signal = ac.signal;
        var to = setTimeout(function () { if (done) return; done = true; try { if (ac) ac.abort(); } catch (e) {} rej(new Error("timeout")); }, 9000);
        W.fetch(url, o).then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.arrayBuffer(); })
          .then(function (ab) { if (!done) { done = true; clearTimeout(to); res(ab); } }, function (e) { if (!done) { done = true; clearTimeout(to); rej(e); } });
      });
    }
    function prefetchBytes(url) { if (!url || RAW[url] || BUF[url]) return; var p = RAW[url] = fetchBytes(url); p.catch(function () { if (RAW[url] === p) delete RAW[url]; }); }
    function loadBuf(url) {
      var e = BUF[url];
      if (e) { e.t = Date.now(); return e.p; }
      e = BUF[url] = { t: Date.now(), p: null, buf: null, st: null };
      var raw = RAW[url] || fetchBytes(url); delete RAW[url];
      e.p = raw.then(function (ab) { return decodeOn(ctx, ab); }).then(function (b) { e.buf = b; trimBuf(); return b; },
        function () { if (BUF[url] === e) delete BUF[url]; return null; });
      return e.p;
    }
    function trimBuf() { /* the two loaded tracks (and a running word play) + two more stay decoded */
      var used = [D.A.buf, D.B.buf, WP && WP.A && WP.A.buf, WP && WP.B && WP.B.buf], ks = Object.keys(BUF).filter(function (k) { return BUF[k].buf && used.indexOf(BUF[k].buf) < 0; });
      ks.sort(function (a, b) { return BUF[a].t - BUF[b].t; });
      while (ks.length > 2) delete BUF[ks.shift()];
    }
    function serverGrid(d) {
      var v = d.track && BG[ckey(d.track)];
      if (!v || !d.url || v[4] !== hex8(hash(d.url)) || !(v[3] >= .5)) return null;
      return { bpm: v[0], b0: v[1], db: v[2], conf: v[3], src: "server" };
    }
    function gridOf(d) { /* server grid (Beat This! on the preview) → cached analysis → analyse the decoded audio here */
      var g = serverGrid(d);
      if (g) { d.grid = g; d.gridDone = true; return Promise.resolve(g); }
      var k = d.url + "|" + Math.round(d.track.bpm || 0), b = d.buf;
      if (BEATS[k]) { d.grid = BEATS[k].conf >= 2 ? BEATS[k] : null; d.gridDone = true; return Promise.resolve(d.grid); }
      return bands(b).then(function (r) { return new Promise(function (res) { setTimeout(function () { res(gridFrom(r, d.track.bpm)); }, 0); }); }).then(function (x) {
        if (x) { x.src = "local"; BEATS[k] = x; saveBeats(); }
        if (d.buf === b) { d.grid = x && x.conf >= 2 ? x : null; d.gridDone = true; }
        return d.grid;
      }, function () { if (d.buf === b) { d.grid = null; d.gridDone = true; } return null; });
    }
    function stretchBuffer(b, r) {
      var n = Math.min(2, b.numberOfChannels), chs = [], c;
      for (c = 0; c < n; c++) chs.push(b.getChannelData(c));
      var out = wsola(chs, r, b.sampleRate), ob = ctx.createBuffer(n, out[0].length, b.sampleRate);
      for (c = 0; c < n; c++) { if (ob.copyToChannel) ob.copyToChannel(out[c], c); else ob.getChannelData(c).set(out[c]); }
      return ob;
    }
    function setSB(d, r, semis) { /* what deck d plays: the decoded original, or a copy stretched once to speed r
         (and shifted by `semis` semitones when the keys need it: the vocal of a mashup, never the beat) */
      r = Math.round(clamp(r, .5, 2) * 1e5) / 1e5; semis = Math.round((semis || 0) * 100) / 100;
      if (Math.abs(r - 1) < 5e-4 && !semis) { d.sb = d.buf; d.sr = 1; d.semis = 0; return; }
      var e = BUF[d.url];
      if (e && e.st && e.st.r === r && (e.st.s || 0) === semis && e.st.src === d.buf) { d.sb = e.st.b; d.sr = r; d.semis = semis; return; }
      var b = semis ? shiftBuffer(d.buf, r, semis) : stretchBuffer(d.buf, r);
      if (e) e.st = { r: r, s: semis, b: b, src: d.buf };
      d.sb = b; d.sr = r; d.semis = semis;
    }
    function shiftBuffer(b, r, semis) {
      var n = Math.min(2, b.numberOfChannels), chs = [], c;
      for (c = 0; c < n; c++) chs.push(b.getChannelData(c));
      var out = shiftStretch(chs, r, semis, b.sampleRate), ob = ctx.createBuffer(n, out[0].length, b.sampleRate);
      for (c = 0; c < n; c++) { if (ob.copyToChannel) ob.copyToChannel(out[c], c); else ob.getChannelData(c).set(out[c]); }
      return ob;
    }
    /* song analysis (analysis.json, measured on GitHub from the same preview): where the singing starts, where the
       beat is full, the key of the harmony and the loudness. Only used when it was measured on this exact preview. */
    function an2Of(d) { var v = d.track && AN2[ckey(d.track)]; return v && d.url && (!v.h || v.h === hex8(hash(d.url))) ? v : null; }
    function anOf(d) { var v = d.track && AN[ckey(d.track)]; return v && !v.err && d.url && (!v.h || v.h === hex8(hash(d.url))) ? v : null; }
    function trimOf(d) { var a = S.loud && anOf(d); return a && isFinite(a.lufs) ? clamp(Math.pow(10, (-11 - a.lufs) / 20), .5, 1.5) : 1; }
    function setTrim(d) { var t = trimOf(d); if (Math.abs(t - (d.trim || 1)) > 1e-3) { d.trim = t; applyGains(d); } }
    function digitsAt(a, field, i) { var s = a && a[field]; return s && i >= 0 && i < s.length ? +s.charAt(i) : -1; }
    function vocalEntry(d) { /* the bar line where the first full sung phrase starts (with its pickup) */
      var a = anOf(d), g = d.grid; if (!a || !a.voc || a.t0 == null || !g) return null;
      var p = 60 / g.bpm, s = a.voc, lim = (d.dur || 30) - 12;
      for (var i = 1; i + 3 < s.length; i++) {
        var on = 0; for (var k = 0; k < 4; k++) on += +s.charAt(i + k) >= 4 ? 1 : 0;
        if (+s.charAt(i) >= 5 && +s.charAt(i - 1) <= 3 && on >= 3) {
          var t = a.t0 + Math.floor(i / 4) * 4 * p;           /* the bar the phrase (or its pickup) starts in */
          return t <= lim && t >= .05 ? t : null;
        }
      }
      return null;
    }
    function beatEntry(d) { /* the first bar where the beat is full (drums + bass), not a thin intro */
      var a = anOf(d), g = d.grid; if (!a || !a.nrg || a.t0 == null || !g) return null;
      var p = 60 / g.bpm, s = a.nrg, bars = Math.floor(s.length / 4), E = [], mx = 0, b, k;
      for (b = 0; b < bars; b++) { var v = 0; for (k = 0; k < 4; k++) v += +s.charAt(4 * b + k); E.push(v / 4); if (v / 4 > mx) mx = v / 4; }
      for (b = 0; b + 1 < bars; b++) {
        var t = a.t0 + 4 * b * p;
        if (t > (d.dur || 30) - 16) break;
        if ((E[b] + E[b + 1]) / 2 >= .75 * mx) return t >= .05 ? t : null;
      }
      return null;
    }
    function entryOf(d) {
      var P = planFor(d), O = D[other(d.side)];
      if (P && d.grid) {                                                /* the bars the matcher chose by ear, B leading by up to 2 bars */
        var at = d.side === "A" ? P.aAt : P.bAt, lb = Math.max(0, Math.round(P.leadBars || 0)), q = P.q || 1;
        var preOf = function (L, x) { return x.side === "A" ? 4 * L * q * 60 / x.grid.bpm : 4 * L * 60 / x.grid.bpm; };
        var A = D.A, B = D.B;
        while (lb > 0 && A.grid && B.grid && (P.aAt - preOf(lb, A) < .05 || P.bAt - preOf(lb, B) < .05)) lb--;
        var t = at - (lb ? preOf(lb, d) : 0);
        if (isFinite(t) && t >= .02 && t < (d.dur || 30) - 4) return t;
      }
      var t2 = d.side === "A" ? vocalEntry(d) : beatEntry(d); return t2 != null ? t2 : downbeat(d.grid);
    }
    function planFor(d) { var P = S.plan; if (!P || !d || !d.track) return null; return ckey(d.track) === (d.side === "A" ? P.v : P.b) ? P : null; }
    /* key match: shift the vocal deck ±1–2 semitones when the measured keys clash and a small shift fixes it */
    function camN(k) { var m = /^(1[0-2]|[1-9])\s*([AB])$/i.exec(String(k || "").trim()); return m ? { n: +m[1], l: m[2].toUpperCase() } : null; }
    function camOk(a, b) { return !!(a && b && (a.n === b.n || (a.l === b.l && (((a.n - b.n) % 12 + 12) % 12 === 1 || ((b.n - a.n) % 12 + 12) % 12 === 1)))); }
    function keyOfDeck(d) { var a = anOf(d); if (a && a.key && a.ks >= (a.km === "e" ? .45 : .62)) return a.key; return null; }
    function semisFor(V, B) {
      if (!S.keyMatch) return 0;
      var P = planFor(V); if (P && planFor(B) && isFinite(P.semis)) return Math.round(clamp(P.semis, -3, 3) * 100) / 100;
      var kv = camN(keyOfDeck(V)), kb = camN(keyOfDeck(B));
      if (!kv || !kb || camOk(kv, kb)) return 0;
      var order = [1, -1, 2, -2];
      for (var i = 0; i < order.length; i++) { var s2 = order[i], sh = { n: ((kv.n - 1 + 7 * s2) % 12 + 12) % 12 + 1, l: kv.l }; if (camOk(sh, kb)) return s2; }
      return 0;
    }
    function warm(d, r) { /* stretch ahead of time (a word-play handoff must start at once) */
      var u = d.url || (d.track && cget(d.track) && cget(d.track).p), trk = d.track;
      if (!u || Math.abs(r - 1) < 5e-4 || !bufOk(d, u)) return;
      loadBuf(u).then(function (b) { setTimeout(guard(function () {
        var e = BUF[u]; r = Math.round(clamp(r, .5, 2) * 1e5) / 1e5;
        if (!b || !e || d.track !== trk || (e.st && e.st.r === r && e.st.src === b)) return;
        e.st = { r: r, b: stretchBuffer(b, r), src: b };
      }), 30); });
    }
    function posAt(d, T) { return (d.o0 + Math.max(0, T - d.t0)) * d.sr; }
    function xOf(g, t) { return (t - g.b0) / (60 / g.bpm) - g.db; }      /* beats since a bar line */
    function tOf(g, x) { return g.b0 + (g.db + x) * (60 / g.bpm); }
    function qOf(gF, effL) { return [.5, 1, 2].reduce(function (x, y) { return Math.abs(gF.bpm - effL * y) < Math.abs(gF.bpm - effL * x) ? y : x; }, 1); }
    function phasePos(F, xL, q, want) { /* follower position (s) near `want` with the leader's bar phase xL */
      var g = F.grid, M = q === .5 ? 8 : 4, per = q * M, x0 = q * xL, x = x0 + Math.round((xOf(g, want) - x0) / per) * per, p = tOf(g, x), lim = (F.dur || 30) - 2;
      while (p < .05) { x += per; p = tOf(g, x); }
      if (p > lim && tOf(g, x - per) >= .05) p = tOf(g, x - per);
      return p;
    }
    function phaseLead(L, xF, q, want) { /* leader position (s) near `want` whose bar phase matches follower phase xF */
      var g = L.grid, M = q === .5 ? 8 : 4, x0 = xF / q, x = x0 + Math.round((xOf(g, want) - x0) / M) * M, p = tOf(g, x), lim = (L.dur || 30) - 2;
      while (p < .05) { x += M; p = tOf(g, x); }
      if (p > lim && tOf(g, x - M) >= .05) p = tOf(g, x - M);
      return p;
    }
    /* fine alignment on the real audio: a beat grid can be off by a frame or two (and a stretch has a few ms of bias),
       so right before a synced start the follower's drum hits are matched against the leader's, ±40 ms, on 1 ms
       onset envelopes of the decoded audio (low band = kicks, high band = claps / hats). The shift is used only when
       the match has a clear peak inside the window. */
    function onsetEnv(buf, off, secs) {
      var sr = buf.sampleRate, n = Math.floor(secs * 1000), B = Math.max(1, Math.round(sr / 1000)), i0 = Math.round(off * sr);
      var L = buf.getChannelData(0), R = buf.numberOfChannels > 1 ? buf.getChannelData(1) : L, lo = new Float32Array(n), hi = new Float32Array(n);
      var a = Math.exp(-2 * Math.PI * 150 / sr), y = 0, prev = 0, j, k;
      for (j = 0; j < n; j++) {
        var el = 0, eh = 0;
        for (k = 0; k < B; k++) { var t = i0 + j * B + k, x = t >= 0 && t < L.length ? .5 * (L[t] + R[t]) : 0; y = a * y + (1 - a) * x; el += y * y; var dx = x - prev; eh += dx * dx; prev = x; }
        lo[j] = Math.log(1e-7 + el); hi[j] = Math.log(1e-9 + eh);
      }
      var e = new Float32Array(n);
      for (j = 1; j < n; j++) { var dl = lo[j] - lo[j - 1], dh = hi[j] - hi[j - 1]; e[j] = .35 * (dl > 0 ? dl : 0) + (dh > 0 ? dh : 0); }
      return e;
    }
    function fineLag(F, oF, L, oL) { /* seconds the follower's content is late against the leader (offsets in their playing buffers) */
      try {
        var W = Math.min(8, (F.sb.duration - oF) - .1, (L.sb.duration - oL) - .1), K = 40;
        if (!(W > 3)) return 0;
        var eL = onsetEnv(L.sb, oL, W), eF = onsetEnv(F.sb, oF - K / 1000, W + 2 * K / 1000), n = eL.length - 2 * K, c = [], best = -1, bk = 0, sum = 0, i, k;
        for (k = -K; k <= K; k++) { var v = 0; for (i = K; i < K + n; i++) v += eL[i] * eF[i + k + K]; c.push(v); sum += v; if (v > best) { best = v; bk = k; } }
        var mean = sum / c.length;
        if (bk <= -K + 2 || bk >= K - 2 || !(best > 1.12 * mean)) return 0;   /* no clear peak inside ±40 ms: trust the grids */
        return bk / 1000;
      } catch (e) { return 0; }
    }
    function bufStop(d) { var s = d.bs; d.bs = null; if (!s) return; s.onended = null; try { s.stop(); } catch (e) {} try { s.disconnect(); } catch (e) {} }
    function gateBlip(d, T) { /* 16 ms dip around a seamless handover, so the splice never clicks */
      try { var p = d.n.gate.gain; p.cancelScheduledValues(ctx.currentTime); p.setValueAtTime(1, Math.max(ctx.currentTime, T - .016)); p.linearRampToValueAtTime(0, T); p.linearRampToValueAtTime(1, T + .016); } catch (e) {}
    }
    function startSrc(d, when, pos, seamless) {
      var old = d.bs, t = ctx.currentTime, s = ctx.createBufferSource();
      when = Math.max(when, t + .005);
      s.buffer = d.sb; s.connect(d.n.inp);
      var off = clamp(pos / d.sr, 0, Math.max(0, d.sb.duration - .05));
      s.onended = guard(function () { if (s === d.bs && d.playing && d.bmode) ended(d, 0); });
      s.start(when, off);
      if (old) {
        old.onended = null; try { old.stop(seamless ? when : 0); } catch (e) {}
        if (seamless) gateBlip(d, when);
        setTimeout(function () { try { old.disconnect(); } catch (e) {} }, Math.max(0, (when - t) * 1000) + 300);
      }
      d.bs = s; d.t0 = when; d.o0 = off; d.pos = off * d.sr; d.busy = false; d.playing = true; d.ready = false; d.waitT = 0; d.playT = performance.now(); d.rate = d.sr;
      if (d.side === "A") voxGate(d);
      ensureTick(); emit();
    }
    /* vocal gate: while the vocal deck plays the clean-up ("vocal" mode), the beats where the analysis heard no singing are
       turned down (−20 dB): what leaks through the clean-up between phrases (A's own drums and synths) drops out, the
       singing comes in a beat early so no pickup is lost, and it rings out for half a beat after. */
    function vgOpen(d) { var g = d && d.n && d.n.vg; if (!g || !ctx) return; try { g.gain.cancelScheduledValues(0); g.gain.setTargetAtTime(1, ctx.currentTime, .015); } catch (e) {} d.vgOn = false; }
    function voxGate(d) {
      var g = d.n && d.n.vg; if (!g || !ctx) return;
      var a = anOf(d), mode = d.n.proc && d.n.proc.mode;
      if (!S.vgate || mode !== "vocal" || !d.bmode || !d.bs || !a || a.t0 == null || !d.grid) { if (d.vgOn) vgOpen(d); return; }
      var l2 = an2Of(d), lev = l2 && l2.vr || a.voc, thr = l2 && l2.vr ? 3 : 4;
      if (!lev) { if (d.vgOn) vgOpen(d); return; }
      var p = 60 / d.grid.bpm, now = ctx.currentTime, T = function (tau) { return d.t0 + (tau / d.sr - d.o0); };
      var on = function (i) { var x = +lev.charAt(i), nx = +lev.charAt(i + 1), pv = i > 0 ? +lev.charAt(i - 1) : 0; return x >= thr || nx >= thr + 1 || pv >= thr + 1; };
      try {
        g.gain.cancelScheduledValues(now);
        var first = Math.max(0, Math.floor((d.o0 * d.sr - a.t0) / p)), cur = -1;
        for (var i = first; i < lev.length; i++) {
          var o = on(i) ? 1 : .1, at = T(a.t0 + i * p) - .03;
          if (o === cur) continue;
          if (at <= now) g.gain.setTargetAtTime(o, now, .012); else g.gain.setTargetAtTime(o, at, o > .5 ? .012 : .05);
          cur = o;
        }
        if (cur !== 1) g.gain.setTargetAtTime(1, T(a.t0 + lev.length * p), .05);
        d.vgOn = true;
      } catch (e) {}
    }
    function syncable(d, O) { /* buffer starts are exact whenever they run (even with the screen locked); only a word-play handoff opts out */
      return S.bsync && S.mode === "both" && performance.now() >= S.hold && d.syncOn && O.syncOn && !!d.grid && !!O.track;
    }
    function solo(d, seamless) { /* start (or re-time a playing deck) at its own tempo, from where it is */
      d.waitT = 0; d.bsync = false;
      var o0 = d.o0, t0 = d.t0, r0 = d.sr, live = !!d.bs;
      setSB(d, effRate(d), 0);
      var T = ctx.currentTime + .03;
      startSrc(d, T, live ? Math.min(d.dur || 1e9, (o0 + Math.max(0, T - t0)) * r0) : d.pos, seamless);
    }
    function join(d, L, seamless) { /* d enters ON THE ONE: the leader's next bar line, at the leader's tempo, same bar phase */
      var gL = L.grid, effL = gL.bpm * L.sr, q = qOf(d.grid, effL), r = effL * q / d.grid.bpm, want = curPos(d);
      if (r < .9 || r > 1.1) { solo(d, seamless); return; }
      setSB(d, r, d.side === "A" ? semisFor(d, L) : 0);                        /* stretch first: the timing below must be fresh */
      var tref = Math.max(ctx.currentTime, L.t0), perL = 60 / gL.bpm / L.sr, xL = xOf(gL, posAt(L, tref));
      var k = Math.ceil((xL + .2 / perL) / 4) * 4, T = tref + (k - xL) * perL;    /* the next 1, ≥ 0.2 s ahead */
      var pF = phasePos(d, k, q, want > .05 ? want : entryOf(d)), lag = fineLag(d, pF / d.sr, L, posAt(L, T) / L.sr);
      d.fine = lag; startSrc(d, T, pF + lag * d.sr, seamless);
      d.bsync = L.bsync = true;
    }
    function beatJoin(B, A, seamless) { /* the beat joins a playing vocal: the beat keeps its own tempo (drums and bass are
         never stretched); at the entry point the vocal switches once, seamlessly, to the beat's tempo */
      var gB = B.grid, gA = A.grid, q = qOf(gA, gB.bpm), r = gB.bpm * q / gA.bpm, want = curPos(B);
      if (r < .9 || r > 1.1) { solo(B, seamless); return; }
      var o0 = A.o0, t0 = A.t0, r0 = A.sr, sm = semisFor(A, B), same = Math.abs(r - r0) < 1e-4 && sm === (A.semis || 0);   /* the vocal's clock mapping right now */
      setSB(B, 1); if (!same) setSB(A, r, sm);                                   /* stretching first: the timing below must be fresh */
      var tref = Math.max(ctx.currentTime, t0), perA = 60 / gA.bpm / r0, xA = xOf(gA, (o0 + (tref - t0)) * r0);
      var k = Math.ceil((xA + .2 / perA) / 4) * 4, T = tref + (k - xA) * perA;    /* the vocal's next 1, ≥ 0.2 s ahead */
      var pB = phaseLead(B, k, q, want > .05 ? want : entryOf(B)), pA = (o0 + (T - t0)) * r0;
      var lagB = fineLag(B, pB, A, pA / A.sr);                                   /* B is never stretched: offset = position */
      B.fine = lagB; startSrc(B, T, pB + lagB, seamless);
      if (!same) startSrc(A, T, pA, true);                                       /* same place in the song, new tempo, from T */
      A.bsync = B.bsync = true;
    }
    function together() { /* both decks loaded: start them on the same clock tick, bar lines aligned */
      var A = D.A, B = D.B; A.waitT = B.waitT = 0;
      if (!(A.ready && B.ready && A.busy && B.busy)) return;
      var ok = !!(A.grid && B.grid && syncable(A, B) && syncable(B, A)), q = 1, r = 1;
      if (ok) { q = qOf(A.grid, B.grid.bpm); r = B.grid.bpm * q / A.grid.bpm; ok = r >= .9 && r <= 1.1; }
      if (!ok) { setSB(A, effRate(A)); setSB(B, effRate(B)); var T0 = ctx.currentTime + .08; startSrc(B, T0, B.pos); startSrc(A, T0, A.pos); return; }
      setSB(B, 1); setSB(A, r, semisFor(A, B));                                 /* the beat keeps its own tempo (and key); the vocal follows it */
      var pB = B.pos > .05 ? B.pos : entryOf(B), xB = xOf(B.grid, pB), pA = phasePos(A, xB, q, A.pos > .05 ? A.pos : entryOf(A));
      var lag = fineLag(A, pA / A.sr, B, pB);                                    /* the vocal's hits against the beat's, ±40 ms */
      A.fine = lag;
      var T = ctx.currentTime + .08;
      startSrc(B, T, pB); startSrc(A, T, pA + lag * A.sr);
      A.bsync = B.bsync = true;
    }
    function place(d) { /* decoded + grid known: start now, join the playing deck, or wait for the other one */
      var O = D[other(d.side)];
      if (!d.ready || !d.busy || !d.bmode) return;
      if (syncable(d, O) && O.bmode) {
        if (O.playing && O.grid && O.bs) { if (d.side === "B") beatJoin(d, O); else join(d, O); return; }
        if (O.busy) { if (O.ready) together(); else { d.waitT = performance.now(); ensureTick(); } return; }
      }
      solo(d);
    }
    function startBuf(d, url) {
      stopGroove(d); stopApple(d, false); bufStop(d);
      var tok = ++d.tok;
      d.kind = "apple"; d.bmode = true; d.url = url; d.el = null; d.busy = true; d.playing = false; d.buffering = false; d.why = ""; d.eqActive = true;
      d.moveT = performance.now(); d.ready = false; d.waitT = 0; d.bsync = false; d.retry = false;
      gateOpen(d, 0, .02);
      var to = setTimeout(guard(function () { if (tok === d.tok && d.busy && !d.ready) { d.noBuf = url; startApple(d, url, false); } }), 8000); /* slow network: stream it */
      loadBuf(url).then(guard(function (b) {
        if (tok !== d.tok) return;
        if (!b) { clearTimeout(to); d.noBuf = url; startApple(d, url, false); return; }   /* no CORS / decode error: stream it */
        if (d.buf !== b) { d.buf = b; d.sb = null; d.sr = 1; d.semis = 0; }
        d.dur = b.duration; setTrim(d);
        gridOf(d).then(guard(function () { if (tok !== d.tok) return; clearTimeout(to); d.ready = true; place(d); }));
      }));
      ensureTick(); emit();
    }
    function preload(d) { var c = d.track && cget(d.track); if (c && c.p && bufOk(d, c.p)) loadBuf(c.p); }
    function bufTick() {
      SIDES.forEach(function (s) {
        var d = D[s], O = D[other(s)];
        if (d.bmode && d.busy && d.ready && d.waitT) {
          if (O.bmode && O.busy && O.ready) together();
          else if (!(O.bmode && O.busy) || performance.now() - d.waitT > 2500) solo(d);   /* the other deck is late: start, it joins on the beat */
        }
      });
    }

    /* ---- word play ("מעברי מילים"): A, then B on the words, on one audio clock ----
       Both previews are decoded. B is time-stretched (pitch kept) to A's tempo and, when that makes the keys fit,
       shifted 1–2 semitones (stretch + resample). A starts a few bars before its word; on A's beat right after the
       word B takes over, positioned so its own word lands right after A's and its bar lines continue A's (the plan
       comes from WordTiming.plan with the measured word times). Styles: cut; echo (a tempo-synced echo carries A's
       word into B); blend (one bar of B without its bass under A, then a bass swap on the cut); drop (B's build-up
       rises under A through an opening high-pass, the drop lands right after A's words). */
    var WP = null, wpN = 0;
    function wpGrid(t, url, b) {
      var v = BG[ckey(t)];
      if (v && v[4] === hex8(hash(url)) && v[3] >= .5) return Promise.resolve({ bpm: v[0], b0: v[1], db: v[2], conf: v[3], src: "server" });
      var k = url + "|" + Math.round(t.bpm || 0);
      if (BEATS[k]) return Promise.resolve(BEATS[k].conf >= 2 ? BEATS[k] : null);
      return bands(b).then(function (r) { return gridFrom(r, t.bpm); }).then(function (x) {
        if (x) { x.src = "local"; BEATS[k] = x; saveBeats(); }
        return x && x.conf >= 2 ? x : null;
      }, function () { return null; });
    }
    function wpTrack(t) {
      var c = t && cget(t), p = c && c.p ? Promise.resolve(c.p) : net && t ? lookup(t, true).then(function (r) { return r && r.p; }) : Promise.resolve(null);
      return p.then(function (url) {
        if (!url || !bufOk(null, url)) throw new Error("preview");
        return loadBuf(url).then(function (b) {
          if (!b) throw new Error("decode");
          return wpGrid(t, url, b).then(function (g) { if (!g) throw new Error("grid"); return { t: t, url: url, buf: b, grid: g }; });
        });
      });
    }
    function procBuf(url, b, r, semis, ride) { /* B as the word play needs it: stretched to A's tempo (maybe riding back
                                                  to its own), maybe shifted in key */
      r = Math.round(clamp(r, .5, 2) * 1e4) / 1e4; semis = Math.round(clamp(semis || 0, -3, 3));
      var rd = ride && ride.i2 > ride.i1 && Math.abs(r - 1) >= 5e-4 ? { i1: +ride.i1, i2: +ride.i2 } : null, rk = rd ? rd.i1 + "-" + rd.i2 : "";
      if (Math.abs(r - 1) < 5e-4 && !semis) return b;
      var e = BUF[url];
      if (e && e.wp && e.wp.r === r && e.wp.s === semis && e.wp.rk === rk && e.wp.src === b) return e.wp.b;
      var n = Math.min(2, b.numberOfChannels), chs = [], c;
      for (c = 0; c < n; c++) chs.push(b.getChannelData(c));
      var out = shiftStretch(chs, r, semis, b.sampleRate, rd), ob = ctx.createBuffer(n, out[0].length, b.sampleRate);
      for (c = 0; c < n; c++) { if (ob.copyToChannel) ob.copyToChannel(out[c], c); else ob.getChannelData(c).set(out[c]); }
      if (e) e.wp = { r: r, s: semis, rk: rk, b: ob, src: b };
      return ob;
    }
    function wpVoice(buf, dest) {
      var v = { src: ctx.createBufferSource(), hp: biq(ctx, "highpass", 12, .7), ls: biq(ctx, "lowshelf", 220, .7), g: gainN(ctx, 0) };
      v.src.buffer = buf; v.src.connect(v.hp); v.hp.connect(v.ls); v.ls.connect(v.g); v.g.connect(dest);
      return v;
    }
    function wpStop(why) {
      var r = WP; if (!r) return; WP = null;
      clearTimeout(r.to);
      if (r.bus && ctx) { try { var t = ctx.currentTime, gp = r.bus.gain; gp.cancelScheduledValues(t); gp.setValueAtTime(gp.value, t); gp.linearRampToValueAtTime(0, t + .06); } catch (e) {} }
      setTimeout(function () {
        r.nodes.forEach(function (n) { try { if (n.stop) n.stop(); } catch (e) {} try { n.disconnect(); } catch (e) {} });
        try { if (r.bus) r.bus.disconnect(); } catch (e) {}
      }, 140);
      r.phase = "done";
      fire("wp", { phase: "done", why: why || "stop", id: r.id });
      emit();
    }
    function wpSchedule(r, A, B, bb, pl) {
      var c = ctx, bus = r.bus = gainN(c, 1), now0 = c.currentTime;
      bus.connect(master);
      var vA = wpVoice(A.buf, bus), vB = wpVoice(bb, bus), pA = 60 / A.grid.bpm, x = .012;
      r.nodes.push(vA.src, vB.src, vA.hp, vA.ls, vA.g, vB.hp, vB.ls, vB.g);
      var T0 = now0 + .15, Tc = T0 + Math.max(.2, pl.cut - pl.aStart);
      var offB = pl.bPos / pl.r, lag = pl.synced ? fineLag({ sb: bb }, offB, { sb: A.buf }, pl.cut) : 0;  /* B's hits on A's, ±40 ms */
      offB = Math.max(0, offB + lag); r.lag = lag;
      var gA = .85 * (pl.trimA || 1), gB = .85 * (pl.trimB || 1), st = pl.style;
      /* on the one: B comes in on the cut (A's 1) from its own 1; A's fader may close earlier, right after its word, when
         it sings on (its echo carries the beat to the 1). xb: B's fade-in, longer when its word starts a hair early. */
      var Ta = Math.min(Tc, T0 + Math.max(.2, (pl.aOut != null ? pl.aOut : pl.cut) - pl.aStart)), xb = clamp(pl.bFade || x, x, .06);
      var pre = Math.max(0, Math.min(pl.pre || 0, offB - xb - .01, Tc - T0 - xb)), Tb = Tc - pre - xb;
      vA.g.gain.setValueAtTime(gA, T0);
      vA.src.start(T0, clamp(pl.aStart, 0, A.buf.duration - .1));
      vB.src.start(Tb, Math.max(0, offB - pre - xb));
      if (st === "blend" && pre > 0) {                                 /* one bar of B without bass, bass swap on the cut */
        vB.ls.gain.setValueAtTime(-26, Tb); vB.ls.gain.setValueAtTime(-26, Tc - .02); vB.ls.gain.linearRampToValueAtTime(0, Tc + .02);
        vB.g.gain.setValueAtTime(0, Tb); vB.g.gain.linearRampToValueAtTime(.7 * gB, Tc - .02); vB.g.gain.linearRampToValueAtTime(gB, Tc + .02);
        vA.ls.gain.setValueAtTime(0, Tc - .02); vA.ls.gain.linearRampToValueAtTime(-26, Tc + .02);
        vA.g.gain.setValueAtTime(gA, Tc); vA.g.gain.linearRampToValueAtTime(0, Tc + pA);
        vA.src.stop(Tc + pA + .05);
      } else if (st === "drop" && pre > 0) {                           /* B's build-up opens under A; the drop after the words */
        vB.hp.frequency.setValueAtTime(1400, Tb); vB.hp.frequency.exponentialRampToValueAtTime(14, Tc);
        vB.g.gain.setValueAtTime(.3 * gB, Tb); vB.g.gain.linearRampToValueAtTime(.85 * gB, Tc - .01); vB.g.gain.linearRampToValueAtTime(gB, Tc);
        vA.hp.frequency.setValueAtTime(12, Tb); vA.hp.frequency.exponentialRampToValueAtTime(420, Math.max(Tb + .05, Ta));
        vA.g.gain.setValueAtTime(gA, Ta - x); vA.g.gain.linearRampToValueAtTime(0, Ta);
        vA.src.stop(Ta + .05);
      } else {                                                         /* clean entry on the one (A out at Ta ≤ Tc, B in at Tc) */
        vB.g.gain.setValueAtTime(0, Tb); vB.g.gain.linearRampToValueAtTime(gB, Tc);
        vA.g.gain.setValueAtTime(gA, Ta - x); vA.g.gain.linearRampToValueAtTime(0, Ta);
        vA.src.stop(Ta + .05);
      }
      if (pl.echo) {                                                   /* A's last beat (its word) rings on, in time */
        var e = { send: gainN(c, 0), dl: c.createDelay(2), fb: gainN(c, pl.echo.fb), hp: biq(c, "highpass", 280, .6), lp: biq(c, "lowpass", 5200, .6), wet: gainN(c, pl.echo.wet) };
        e.dl.delayTime.value = clamp(pl.echo.d, .05, 1.9);
        vA.ls.connect(e.send); e.send.connect(e.dl); e.dl.connect(e.hp); e.hp.connect(e.lp); e.lp.connect(e.fb); e.fb.connect(e.dl); e.lp.connect(e.wet); e.wet.connect(bus);
        r.nodes.push(e.send, e.dl, e.fb, e.hp, e.lp, e.wet);
        var s0 = Math.max(T0 + .01, Ta - pA);                           /* the echo hears A's last beat: its word */
        e.send.gain.setValueAtTime(0, s0); e.send.gain.linearRampToValueAtTime(gA, s0 + .01); e.send.gain.setValueAtTime(gA, Ta - .006); e.send.gain.linearRampToValueAtTime(0, Ta + .004);
        e.fb.gain.setValueAtTime(pl.echo.fb, Tc + 2 * pA); e.fb.gain.linearRampToValueAtTime(0, Tc + 5 * pA);
        e.wet.gain.setValueAtTime(pl.echo.wet, Tc); e.wet.gain.linearRampToValueAtTime(pl.echo.wet * .45, Tc + 2 * pA);   /* B on its 1 takes over */
      }
      var Te = Tc + Math.max(2, pl.tail || 10);
      vB.g.gain.setValueAtTime(gB, Te - 1.6); vB.g.gain.linearRampToValueAtTime(0, Te);
      vB.src.stop(Te + .05);
      r.t0 = T0; r.tc = Tc; r.te = Te; r.phase = "play";
      r.to = setTimeout(guard(function () { if (WP === r) wpStop("end"); }), Math.max(0, (Te - c.currentTime) * 1000 + 300));
      fire("wp", { phase: "play", id: r.id, plan: pl });
      emit();
    }
    api.wordplay = function (o) {
      try {
        wpStop("new");
        if (!o || !o.a || !o.b || typeof o.plan !== "function" || !ensureCtx()) return Promise.reject(new Error("args"));
        resumeCtx();
        SIDES.forEach(function (s) { if (bp(D[s])) halt(D[s]); }); S.mode = null; S.seq = false;
        var r = WP = { id: ++wpN, phase: "load", plan: null, nodes: [], t0: 0, tc: 0, te: 0 };
        fire("wp", { phase: "load", id: r.id }); emit();
        return Promise.all([wpTrack(o.a), wpTrack(o.b)]).then(function (x) {
          if (WP !== r) return null;
          var A = x[0], B = x[1], pl = o.plan({ gA: A.grid, gB: B.grid, durA: A.buf.duration, durB: B.buf.duration, hA: hex8(hash(A.url)), hB: hex8(hash(B.url)) });
          if (!pl || !pl.ok) throw new Error("plan:" + (pl && pl.why));
          r.plan = pl; r.A = A; r.B = B;
          return new Promise(function (res) { setTimeout(res, 30); }).then(function () {   /* the card paints "preparing" first */
            if (WP !== r) return null;
            if (ctx.state !== "running") resumeCtx();
            wpSchedule(r, A, B, procBuf(B.url, B.buf, pl.r, pl.semis, pl.ride), pl);
            return pl;
          });
        }).catch(function (e) {
          if (WP === r) { WP = null; fire("wp", { phase: "error", id: r.id, err: String(e && e.message || e) }); emit(); }
          throw e;
        });
      } catch (e) { return Promise.reject(e); }
    };
    api.wpStop = guard(function () { wpStop("user"); });
    api.wpState = function () {
      var r = WP; if (!r) return { phase: "idle" };
      if (r.phase === "load" || !ctx) return { phase: "load", id: r.id, plan: r.plan };
      var t = ctx.currentTime;
      return { phase: t < r.t0 ? "load" : t < r.tc ? "a" : t < r.te ? "b" : "done", id: r.id, t: Math.max(0, t - r.t0), cut: r.tc - r.t0, total: r.te - r.t0, plan: r.plan, lag: r.lag || 0 };
    };
    api._wpNodes = function () { return WP && WP.bus ? { bus: WP.bus, t0: WP.t0, tc: WP.tc, te: WP.te } : null; };   /* tests: tap the word-play output */

    /* ---- deck control ---- */
    function curPos(d) {
      if (d.bmode && d.bs && ctx) return Math.min(d.dur || 1e9, posAt(d, ctx.currentTime));
      if (d.kind === "apple" && d.el && d.el._u) return d.el.currentTime || (d.busy ? d.pos : 0);
      if (d.kind === "studio" && d.groove) return d.groove.pos(now());
      return d.pos;
    }
    function halt(d) {
      d.pos = curPos(d); d.tok++; d.busy = false; d.buffering = false; d.playing = false; d.playT = 0; d.ready = false; d.waitT = 0;
      stopGroove(d); bufStop(d); if (d.el) try { d.el.pause(); } catch (e) {}
      vgOpen(d);
    }
    function startDeck(d, o) {
      if (!d.track || bp(d)) return;
      d.rate = effRate(d);
      if (d.dur && d.pos >= d.dur - .25) d.pos = 0;
      if (!net) { d.why = "claude"; startStudio(d, o); return; }
      var c = cget(d.track);
      if (c && c.p) { if (bufOk(d, c.p)) startBuf(d, c.p); else startApple(d, c.p, false); return; } /* decoded buffer; or el.play() inside the gesture */
      if (c) { d.why = "miss"; startStudio(d, o); return; } /* known: Apple has no preview for this song */
      var tok = ++d.tok, trk = d.track; d.busy = true;
      var to = setTimeout(guard(function () { if (tok === d.tok && d.busy) { d.why = "slow"; startStudio(d, o); } }), 6000); /* wait ≤ 6 s */
      lookup(d.track, true).then(guard(function (r) {
        clearTimeout(to);
        if (tok === d.tok && d.busy) { if (r && r.p) { if (bufOk(d, r.p)) startBuf(d, r.p); else startApple(d, r.p, false); } else { d.why = diag.last === "net" ? "net" : "miss"; startStudio(d, o); } return; }
        /* late result: this deck fell back to Studio Groove for the same track and is still playing → switch to the original now */
        if (r && r.p && d.track === trk && d.kind === "studio" && d.playing && S.mode !== "seq") { d.pos = 0; if (bufOk(d, r.p)) startBuf(d, r.p); else startApple(d, r.p, false); }
      }));
      ensureTick(); emit();
    }
    function ended(d, at) {
      halt(d); d.pos = d.dur;
      fire("ended", d.side);
      var s = d.side, o = { at: at || 0 };
      if (S.mode === "seq") {
        if (s === "A" && D.B.track) { S.cur = "B"; D.B.pos = 0; startDeck(D.B, o); }
        else if (s === "B" && S.loop && D.A.track) { S.cur = "A"; D.A.pos = 0; startDeck(D.A, o); }
      } else if (S.loop && (S.mode === s || S.mode === "both")) { d.pos = 0; startDeck(d, o); }
      emit();
    }
    function setTrack(d, t) {
      halt(d); stopApple(d, true);
      d.track = t || null; d.kind = "idle"; d.pos = 0; d.url = null; d.lv = 0; d.retry = false; d.why = ""; d.grid = null; d.gridFor = null; d.gridDone = false;
      bufStop(d); d.bmode = false; d.buf = null; d.sb = null; d.sr = 1; d.bsync = false; d.ready = false; d.waitT = 0; d.noBuf = null; d.semis = 0;
      if (d.trim !== 1) { d.trim = 1; applyGains(d); }
      d.art = t ? api.art(t) : null; d.eqActive = !(net && cors === false); d.rate = effRate(d);
      d.dur = t ? grooveBars(tempoOf(d)) * 240 / tempoOf(d) : 0;
    }
    function setRatesInt(r) {
      if (r && typeof r === "object") SIDES.forEach(function (s) { var v = Number(r[s]); if (v > 0 && isFinite(v)) rates[s] = clamp(v, .5, 2); });
      SIDES.forEach(applyRate);
    }
    function applyRate(s) {
      var d = D[s], r = effRate(d);
      if (d.bmode) { if (d.playing && d.buf && !d.bsync && Math.abs(r - d.sr) > 5e-4) solo(d, true); return; }
      if (r === d.rate && !(d.groove && Math.abs(d.groove.tempo - tempoOf(d)) > 1e-6)) return;
      d.rate = r;
      [d.elC, d.elD].forEach(function (el) { if (el) pitch(el, r); });
      if (d.groove) d.groove.retempo(tempoOf(d), now());
    }
    function side(s) { return s === "B" || s === "b" ? "B" : s === "A" || s === "a" ? "A" : null; }
    function playIn(s, o) { /* starts deck s, keeps the mode consistent */
      var d = D[s]; if (!d.track) return;
      wpStop("deck");
      ensureCtx(); resumeCtx();
      if (S.mode === "seq") S.cur = s; else S.mode = bp(D[other(s)]) ? "both" : s;
      startDeck(d, o);
    }
    function media() {
      var ms = navigator.mediaSession; if (!ms) return;
      try {
        var a = D.A.track, b = D.B.track, art = net ? (D.A.art || D.B.art) : null, title = a && b ? a.t + " × " + b.t : (a || b || {}).t || "";
        if (W.MediaMetadata && title + art !== msTitle) {
          msTitle = title + art;
          ms.metadata = new MediaMetadata({ title: title, artist: [a && a.a, b && b.a].filter(Boolean).join(" · "), album: "מעבדת המשאפים", artwork: art ? [{ src: art, sizes: "600x600", type: "image/jpeg" }] : [] });
        }
        ms.playbackState = bp(D.A) || bp(D.B) ? "playing" : "paused";
        if (!msInit) { msInit = true; ms.setActionHandler("play", function () { api.resume(); }); ms.setActionHandler("pause", function () { api.pauseAll(); }); try { ms.setActionHandler("stop", function () { api.stopAll(); }); } catch (e) {} }
      } catch (e) {}
    }
    artFns.push(function (t, r) {
      if (!net) return;
      SIDES.forEach(function (s) { var d = D[s]; if (d.track && ckey(d.track) === ckey(t) && d.art !== r.a) { d.art = r.a; emit(); } });
      if (r.a) fire("art", t);
    });

    /* ---- public API (never throws) ---- */
    api.gesture = guard(function () {
      if (!ensureCtx()) return;
      resumeCtx();
      if (!unlocked) { unlocked = true; try { var b = ctx.createBuffer(1, 1, 22050), s = ctx.createBufferSource(); s.buffer = b; s.connect(ctx.destination); s.start(0); } catch (e) {} }
      try { if (navigator.audioSession && navigator.audioSession.type !== "playback") navigator.audioSession.type = "playback"; } catch (e) {}
      if (!net) return;
      ensureEls();
      SIDES.forEach(function (s) {
        [D[s].elC, D[s].elD].forEach(function (el) { /* iOS: unlock each element inside the gesture */
          if (el._unl || el._u || el.getAttribute("src")) return;
          el._unl = true; el.src = SILENT;
          try { var p = el.play(); if (p && p.then) p.then(function () { if (isData(el)) el.pause(); }, noop); } catch (e) {}
        });
      });
    });
    api.loadPair = guard(function (v, b, r, plan) {
      wpStop("load");
      S.plan = plan && plan.v && plan.b ? plan : null;
      SIDES.forEach(function (s) { halt(D[s]); }); setRatesInt(r); setTrack(D.A, v); setTrack(D.B, b); S.mode = null; S.seq = false; S.cur = "A";
      SIDES.forEach(function (s) { var d = D[s], c = d.track && cget(d.track); if (c && c.p && bufOk(d, c.p)) preload(d); else wantGrid(d); });
      if (net) { if (v) lookup(v).catch(noop); if (b) lookup(b).catch(noop); }
      emit();
    });
    api.loadDeck = guard(function (s, t, r) {
      s = side(s); if (!s) return;
      var d = D[s], O = D[other(s)], was = bp(d), v = r && Number(r[s]), w = r && Number(r[O.side]);
      setTrack(d, t);
      if (t && O.track && O.playing && O.syncOn && v > 0 && w > 0) { /* the other deck keeps playing: never retime it (an audible jump on iPhone); the new track follows its tempo */
        var q = v * pattTempo(t) / (w * pattTempo(O.track)); q = q > 1.5 ? 2 : q < .75 ? .5 : 1;
        rates[s] = clamp(pattTempo(O.track) * (O.rate || 1) * q / pattTempo(t), .5, 2); applyRate(s);
      } else setRatesInt(r);
      d.dur = t ? grooveBars(tempoOf(d)) * 240 / tempoOf(d) : 0;
      if (net && t) lookup(t, was).catch(noop);
      preload(d);
      if (was && t) playIn(s);
      emit();
    });
    api.unload = guard(function () {
      wpStop("unload");
      SIDES.forEach(function (s) { setTrack(D[s], null); }); S.mode = null; S.seq = false; S.cur = "A";
      if (ctx && ctx.state !== "closed") { try { var p = ctx.suspend(); if (p && p.catch) p.catch(noop); } catch (e) {} }
      emit();
    });
    api.play = guard(function (s) { s = side(s); if (s) { playIn(s); emit(); } });
    api.pause = guard(function (s) {
      s = side(s); if (!s) return;
      halt(D[s]);
      if (S.mode === "both") S.mode = bp(D[other(s)]) ? other(s) : "both";
      emit();
    });
    api.toggle = guard(function (s) { s = side(s); if (!s) return; if (bp(D[s])) api.pause(s); else api.play(s); });
    api.stop = guard(function (s) { s = side(s); if (!s) return; var d = D[s]; halt(d); d.pos = 0; if (d.el && d.el._u) try { d.el.currentTime = 0; } catch (e) {} emit(); });
    api.seek = guard(function (s, sec) {
      s = side(s); if (!s) return;
      var d = D[s]; sec = clamp(sec, 0, d.dur || 30); d.seekN++; d.moveT = performance.now(); /* the moved deck re-syncs to the other one */
      if (d.bmode) {
        d.pos = sec;
        if (d.playing && d.sb && ctx) {
          var O = D[other(s)], T = ctx.currentTime + .04;
          if (d.bsync && O.bmode && O.playing && O.bs && O.grid && d.grid) startSrc(d, T, phasePos(d, xOf(O.grid, posAt(O, T)), qOf(d.grid, O.grid.bpm * O.sr), sec), true);
          else startSrc(d, T, sec, true);
        }
        emit(); return;
      }
      if (d.kind === "apple" && d.el && d.el._u) { try { d.el.currentTime = sec; } catch (e) {} d.pos = sec; }
      else if (d.kind === "studio" && d.groove && d.playing) { d.pos = sec; startStudio(d); }
      else d.pos = sec;
      emit();
    });
    api.playBoth = guard(function () {
      wpStop("deck"); ensureCtx(); resumeCtx();
      S.mode = "both"; S.seq = false;
      SIDES.forEach(function (s) { var d = D[s]; if (d.grid && d.pos < .05 && !bp(d)) d.pos = downbeat(d.grid); });
      var at = ctx ? ctx.currentTime + .06 : 0; /* same AudioContext time → aligned downbeats */
      S.pb = true; /* starting together: the vocal (A) waits muted and enters on the beat (see holdFor) */
      var both = !bp(D.A) && !bp(D.B);
      try { SIDES.forEach(function (s) { startDeck(D[s], { at: at }); }); } finally { S.pb = false; }
      if (both && bp(D.A) && bp(D.B)) D.A.moveT = Math.max(D.A.moveT, D.B.moveT) + 1; /* …and stays the follower if its gate had to open early */
      emit();
    });
    api.playOnly = guard(function (s) { s = side(s); if (!s) return; halt(D[other(s)]); S.seq = false; S.mode = s; playIn(s); warm(D[other(s)], effRate(D[other(s)])); emit(); });
    api.pauseAll = guard(function () { wpStop("pause"); SIDES.forEach(function (s) { halt(D[s]); }); emit(); });
    api.stopAll = guard(function () { wpStop("stop"); SIDES.forEach(function (s) { var d = D[s]; halt(d); d.pos = 0; if (d.el && d.el._u) try { d.el.currentTime = 0; } catch (e) {} }); emit(); });
    api.resume = guard(function () {
      var m = S.mode || (D.A.track && D.B.track ? "both" : D.A.track ? "A" : D.B.track ? "B" : null);
      if (m === "both") api.playBoth(); else if (m === "seq") { playIn(S.cur || "A"); emit(); } else if (m) { playIn(m); emit(); }
    });
    api.sequence = guard(function (on) {
      if (on) { wpStop("deck"); SIDES.forEach(function (s) { halt(D[s]); D[s].pos = 0; }); S.seq = true; S.mode = "seq"; S.cur = "A"; ensureCtx(); resumeCtx(); startDeck(D.A); }
      else { S.seq = false; if (S.mode === "seq") S.mode = bp(D.A) && bp(D.B) ? "both" : bp(D.A) ? "A" : bp(D.B) ? "B" : null; }
      emit();
    });
    api.loop = guard(function (on) { S.loop = !!on; emit(); });
    api.setVolume = guard(function (s, v) { s = side(s); if (!s) return; D[s].vol = clamp(v, 0, 1); applyGains(D[s]); emit(); });
    api.setEq = guard(function (s, band, db) { s = side(s); if (!s || !(band in D[s].eq)) return; D[s].eq[band] = clamp(db, -24, 6); applyGains(D[s]); emit(); });
    api.setSync = guard(function (s, on) {
      s = side(s); if (!s) return; var d = D[s]; d.syncOn = !!on; d.moveT = performance.now();
      var O = D[other(s)];
      if (d.bmode && d.playing && d.buf && ctx) {
        if (on && syncable(d, O) && O.bmode && O.playing && O.bs && O.grid) { if (s === "B") beatJoin(d, O, true); else join(d, O, true); } else solo(d, true);
        emit(); return;
      }
      applyRate(s);
      if (on && d.groove && O.groove && d.playing && O.playing) { d.pos = curPos(d); startStudio(d); } /* re-lock the beat grid */
      emit();
    });
    api.setRates = guard(function (r) { setRatesInt(r); emit(); });
    api.setCrossfader = guard(function (x) { S.xf = clamp(x, 0, 1); SIDES.forEach(function (s) { applyGains(D[s]); }); emit(); });
    api.state = function () {
      function cp(d) {
        var dur = d.kind === "apple" && d.el && isFinite(d.el.duration) && d.el.duration > 0 ? d.el.duration : d.dur;
        return { track: d.track, kind: d.kind, busy: d.busy, buffering: d.buffering, playing: d.playing, pos: Math.min(curPos(d), dur || 1e9), dur: dur, vol: d.vol,
          eq: { low: d.eq.low, mid: d.eq.mid, high: d.eq.high }, syncOn: d.syncOn, rate: d.rate, eqActive: d.kind === "studio" ? true : d.eqActive, art: d.art, why: d.kind === "studio" ? (d.why || "") : "", vox: d.n && d.n.proc ? d.n.proc.mode : "off", grid: d.grid ? { bpm: d.grid.bpm, conf: d.grid.conf, src: d.grid.src || "" } : null, held: d.gate !== 1, bm: !!d.bmode, sync: !!d.bsync, semis: d.semis || 0, trim: Math.round((d.trim || 1) * 1000) / 1000, an: !!anOf(d) };
      }
      try { return { mode: S.mode, seq: S.seq, loop: S.loop, xf: S.xf, clean: S.clean, beat: S.beat, cue: S.cue, keyMatch: S.keyMatch, A: cp(D.A), B: cp(D.B) }; } catch (e) { return { mode: null, seq: false, loop: false, xf: .5, A: null, B: null }; }
    };
    function pulse(d) {
      var ph = performance.now() / 1000 * tempoOf(d) / 60;
      return d.side === "A" ? .42 + .22 * Math.sin(ph * Math.PI * .5) + .14 * Math.sin(ph * Math.PI * 2 + 1) : .22 + .7 * Math.pow(Math.max(0, Math.cos(ph * Math.PI * 2)), 6);
    }
    function measurable(d) { return d.n && ctx && ctx.state === "running" && (d.kind === "studio" || (d.kind === "apple" && (d.bmode || (d.el === d.elC && cors !== false)))); }
    api.level = function (s) {
      try {
        var d = D[side(s)], raw = 0;
        if (!d || !d.playing) raw = 0;
        else if (measurable(d)) { var n = d.n, b = n.buf, q = 0; n.an.getFloatTimeDomainData(b); for (var i = 0; i < b.length; i++) q += b[i] * b[i]; raw = Math.min(1, Math.pow(Math.sqrt(q / b.length) * 3.2, .8)); }
        else raw = clamp(pulse(d), 0, 1);
        raw *= .25 + .75 * d.vol;
        d.lv += (raw - d.lv) * (raw > d.lv ? .5 : .15);
        return clamp(d.lv, 0, 1);
      } catch (e) { return 0; }
    };
    api.bands = function (s) {
      try {
        var d = D[side(s)]; if (!d || !d.playing) return { low: 0, mid: 0, high: 0 };
        if (!measurable(d)) { var p = clamp(pulse(d), 0, 1); return { low: p, mid: p * .7, high: p * .45 }; }
        var n = d.n, f = n.fb, hz = ctx.sampleRate / 2 / f.length;
        n.an.getByteFrequencyData(f);
        var r = [[20, 250], [250, 2500], [2500, 10000]].map(function (x) {
          var a = Math.max(1, Math.floor(x[0] / hz)), b = Math.min(f.length - 1, Math.ceil(x[1] / hz)), q = 0; for (var i = a; i <= b; i++) q += f[i]; return clamp(q / (b - a + 1) / 255, 0, 1);
        });
        return { low: r[0], mid: r[1], high: r[2] };
      } catch (e) { return { low: 0, mid: 0, high: 0 }; }
    };
    api.on = function (ev, fn) { if (L[ev] && typeof fn === "function") L[ev].push(fn); return api; };
    api.off = function (ev, fn) { if (L[ev]) L[ev] = L[ev].filter(function (f) { return f !== fn; }); return api; };
    api.art = function (t) { try { var c = net && t ? cget(t) : null; return c && c.a || null; } catch (e) { return null; } };
    api.prefetch = function (t) { try { return net && t ? lookup(t).catch(function () { return null; }) : Promise.resolve(null); } catch (e) { return Promise.resolve(null); } };
    api.hintCors = function (v) { if (cors === null && typeof v === "boolean") cors = v; };
    api.setClean = guard(function (on) { S.clean = !!on; emit(); });
    api.setBeatSync = guard(function (on) { S.bsync = !!on; emit(); });
    api.setBufMode = guard(function (on) { S.useBuf = !!on; });
    api.setKeyMatch = guard(function (on) { /* auto key match for the vocal deck; a playing synced pair re-times seamlessly */
      S.keyMatch = !!on;
      var A = D.A, B = D.B;
      if (A.bmode && B.bmode && A.playing && B.playing && A.bsync && B.bsync && A.grid && B.grid && ctx) {
        var sm = semisFor(A, B);
        if (sm !== (A.semis || 0)) { var T = ctx.currentTime + .05, pos = posAt(A, T); setSB(A, A.sr, sm); startSrc(A, T, pos, true); A.bsync = true; }
      }
      emit();
    });
    api.setLoudMatch = guard(function (on) { S.loud = !!on; SIDES.forEach(setTrim); emit(); });
    /* the matcher's plan for the loaded pair: { v, b (track keys), semis, aAt, bAt, leadBars, cleanB, q } (null: own choice) */
    api.setPlan = guard(function (P) { S.plan = P && P.v && P.b ? P : null; emit(); });
    api.setVocalGate = guard(function (on) { S.vgate = !!on; voxGate(D.A); });
    api.prefetchAudio = guard(function (t) { var c = net && t ? cget(t) : null; if (c && c.p && bufOk(null, c.p)) prefetchBytes(c.p); });
    api._nodes = function (s) { var d = D[side(s)]; return d ? d.n : null; };   /* tests: tap a deck's signal */
    api._ctx = function () { return ctx; };
    api.holdClean = guard(function (ms) { S.hold = performance.now() + Math.max(0, Number(ms) || 0); setTimeout(guard(emit), (Number(ms) || 0) + 30); emit(); });
    api.diag = function () { return { net: net, cors: cors, backoff: Math.max(0, backoff - Date.now()), ok: diag.ok, miss: diag.miss, fail: diag.fail, last: diag.last, via: diag.via, fetchErr: diag.fetchErr }; };
    api.probe = function () { /* connection test for the audio-source sheet: one fresh search (cache bypassed) */
      if (!net) return Promise.resolve({ ok: false, err: "net-off", ms: 0 });
      var t0 = Date.now(), u = "https://itunes.apple.com/search?term=" + encodeURIComponent("Rema Calm Down") + "&media=music&entity=song&limit=3&country=us", via = "fetch", fe = "";
      return fetchJSON(u).catch(function (e) { via = "jsonp"; fe = String(e && e.message || e).slice(0, 60); return jsonp(u); })
        .then(function (j) { var r = j && j.results && j.results.filter(function (x) { return x && x.previewUrl; })[0]; return { ok: !!r, via: via, fetchErr: fe, ms: Date.now() - t0 }; },
              function (e) { return { ok: false, via: via, fetchErr: fe, err: String(e && e.message || e).slice(0, 60), ms: Date.now() - t0 }; });
    };
    api._dbg = function () {
      function el(e) { return e ? { paused: e.paused, t: e.currentTime, src: e.getAttribute("src") || "", vol: e.volume, muted: e.muted, rate: e.playbackRate, pp: e.preservesPitch } : null; }
      var o = { cors: cors, ctx: ctx ? ctx.state : null, backoff: Date.now() < backoff, queue: Q.length, mode: S.mode, net: net, sync: { seeks: al.seeks, rateSets: al.rateSets, dips: al.dips, done: al.done, ok: al.ok, F: al.F, err: al.err, lag: al.lag, opened: al.opened, fixes: al.fixes, beat: S.beat, cue: S.cue } };
      SIDES.forEach(function (s) {
        var d = D[s], n = d.n, g = d.groove;
        o[s] = { C: el(d.elC), D: el(d.elD), active: d.el ? (d.el === d.elC ? "C" : "D") : null, url: d.url, tempo: g ? g.tempo : null,
          groove: g ? { t0: g.t0, tStart: g.tStart, dt: g.dt, div: g.div, cOff: g.cOff, k0: g.k0, bars: g.bars, pat: g.P ? Object.keys(GP).filter(function (k) { return GP[k] === g.P; })[0] : "lead" } : null,
          g: n ? { vol: n.vol.gain.value, gate: n.gate.gain.value, xf: n.xf.gain.value, low: n.lo.gain.value, mid: n.mid.gain.value, high: n.hi.gain.value } : null, held: d.gate !== 1,
          buf: { bm: !!d.bmode, sr: d.sr, t0: d.t0, o0: d.o0, pos: curPos(d), dur: d.dur, sync: !!d.bsync, ready: !!d.ready, fine: d.fine || 0, grid: d.grid ? [d.grid.bpm, d.grid.b0, d.grid.db, d.grid.src || ""] : null, now: ctx ? ctx.currentTime : 0, noBuf: d.noBuf } };
      });
      return o;
    };
    W.addEventListener("pagehide", guard(function () { api.stopAll(); }));
    return api;
  }

  /* offline render for tests/calibration: opts {A, B, rates:{A,B}, secs, solo:"A"|"B", sr, xf} → Promise<AudioBuffer> */
  function render(o) {
    var sr = o.sr || 44100, secs = o.secs || 16, oc = new (W.OfflineAudioContext || W.webkitOfflineAudioContext)(2, Math.ceil(sr * secs), sr);
    var m = gainN(oc, MASTER), cp = oc.createDynamicsCompressor(), xf = o.xf == null ? .5 : o.xf, tempo = {};
    cp.threshold.value = -10; cp.ratio.value = 4; m.connect(cp); cp.connect(oc.destination);
    SIDES.forEach(function (s) { if (o[s]) tempo[s] = pattTempo(o[s]) * ((o.rates && o.rates[s]) || 1); });
    SIDES.forEach(function (s) {
      if (!o[s] || (o.solo && o.solo !== s)) return;
      var v = gainN(oc, o.vol == null ? .85 : o.vol), x = gainN(oc, s === "A" ? Math.cos(xf * Math.PI / 2) : Math.sin(xf * Math.PI / 2));
      v.connect(x); x.connect(m);
      var g = new Groove(oc, v, o[s], s, tempo[s], divOf(tempo[s], tempo[other(s)]));
      g.start(.05, 0, 0); g.schedule(secs + 1, -1);
    });
    return oc.startRendering();
  }
  /* ---------------- beat grid of a preview (analysed in memory; only the timing numbers are kept) ----------------
     Band energies (low < 160 Hz, mid ~1.8 kHz, high > 6 kHz) → onset strength → comb search around the catalog
     BPM (±8 %, 0.01 BPM steps after a coarse pass) for tempo + phase → downbeat from claps/snares on 2 and 4. */
  var BEATS = {}, beatPend = {};
  try { BEATS = JSON.parse(W.localStorage.getItem("mashlab.beats") || "{}") || {}; } catch (e) { BEATS = {}; }
  function saveBeats() { try { var ks = Object.keys(BEATS); if (ks.length > 800) ks.slice(0, ks.length - 800).forEach(function (k) { delete BEATS[k]; }); W.localStorage.setItem("mashlab.beats", JSON.stringify(BEATS)); } catch (e) {} }
  function offline(ch, n, sr) { var O = W.OfflineAudioContext || W.webkitOfflineAudioContext; return new O(ch, n, sr); }
  function decodeAudio(ab) {
    return new Promise(function (res, rej) {
      var oc; try { oc = offline(1, 22050, 22050); } catch (e) { try { oc = offline(1, 44100, 44100); } catch (e2) { rej(e2); return; } }
      try { var p = oc.decodeAudioData(ab, res, rej); if (p && p.then) p.then(res, rej); } catch (e) { rej(e); }
    });
  }
  function renderOff(oc) { return new Promise(function (res, rej) { try { var p = oc.startRendering(); if (p && p.then) p.then(res, rej); else oc.oncomplete = function (e) { res(e.renderedBuffer); }; } catch (e) { rej(e); } }); }
  function bands(buf) {
    var sr = buf.sampleRate, n = Math.min(buf.length, Math.floor(sr * 32)), oc = offline(4, n, sr), src = oc.createBufferSource(); src.buffer = buf;
    var lo = biq(oc, "lowpass", 160, .7), mi = biq(oc, "bandpass", 1800, .6), hi = biq(oc, "highpass", 6000, .7), hm = biq(oc, "bandpass", 260, .8), mg = oc.createChannelMerger(4);
    src.connect(lo); src.connect(mi); src.connect(hi); src.connect(hm); lo.connect(mg, 0, 0); mi.connect(mg, 0, 1); hi.connect(mg, 0, 2); hm.connect(mg, 0, 3); mg.connect(oc.destination);
    src.start(0); return renderOff(oc);
  }
  function gridFrom(r, hint) {
    var sr = r.sampleRate, hop = Math.max(64, Math.round(sr * .0116)), win = hop * 4, N = Math.floor((r.length - win) / hop), i, j, b, k;
    if (N < 300) return null;
    var E = [];
    for (b = 0; b < 4; b++) { var x = r.getChannelData(b), e = new Float32Array(N); for (i = 0; i < N; i++) { var sm = 0, o = i * hop; for (j = 0; j < win; j += 2) { var v = x[o + j]; sm += v * v; } e[i] = Math.log(1e-9 + sm); } E.push(e); }
    var Lo = new Float32Array(N), Mi = new Float32Array(N), On = new Float32Array(N);
    for (i = 1; i < N; i++) {
      var d0 = E[0][i] - E[0][i - 1], d1 = E[1][i] - E[1][i - 1], d2 = E[2][i] - E[2][i - 1];
      Lo[i] = d0 > 0 ? d0 : 0; Mi[i] = d1 > 0 ? d1 : 0; On[i] = Lo[i] + .6 * Mi[i] + .4 * (d2 > 0 ? d2 : 0);
    }
    var Pf = new Float64Array(N + 1), Oc = new Float32Array(N), w = 12, tot = 0;
    for (i = 0; i < N; i++) Pf[i + 1] = Pf[i] + On[i];
    for (i = 0; i < N; i++) { var a = Math.max(0, i - w), z = Math.min(N, i + w + 1), m = (Pf[z] - Pf[a]) / (z - a), y = On[i] - m; Oc[i] = y > 0 ? y : 0; tot += Oc[i]; }
    var mean = tot / N || 1e-9, fps = sr / hop;
    function at(arr, xx) { var q = xx | 0, f = xx - q; return q + 1 < N ? arr[q] * (1 - f) + arr[q + 1] * f : 0; }
    function comb(bpm, ph) { var P = 60 * fps / bpm, sm = 0, c = 0; for (var xx = ph; xx < N - 1; xx += P) { sm += at(Oc, xx); c++; } return c ? sm / c : 0; }
    var c0 = hint > 0 ? hint : 120, best = { s: -1 };
    for (var bpm = c0 * .92; bpm <= c0 * 1.08; bpm += .05) { var P = 60 * fps / bpm; for (var ph = 0; ph < P; ph += 1) { var sc = comb(bpm, ph); if (sc > best.s) best = { s: sc, bpm: bpm, ph: ph }; } }
    var b2 = best;
    for (var bb = best.bpm - .06; bb <= best.bpm + .06; bb += .01) for (var pp = best.ph - 1.5; pp <= best.ph + 1.5; pp += .1) { if (pp < 0) continue; var s2 = comb(bb, pp); if (s2 > b2.s) b2 = { s: s2, bpm: bb, ph: pp }; }
    /* downbeat: claps/snares on 2 and 4 pick between {1,3} and {2,4}; bass/chord changes (new bar) break the 1-vs-3 tie */
    var Pb = 60 * fps / b2.bpm, Mj = [0, 0, 0, 0], Lj = [0, 0, 0, 0], Nj = [0, 0, 0, 0], cn = [0, 0, 0, 0], dl = Math.max(2, Math.round(Pb * .35));
    for (k = 0; b2.ph + k * Pb < N - 1; k++) {
      var q4 = k % 4, fi = Math.round(b2.ph + k * Pb);
      Mj[q4] += at(Mi, b2.ph + k * Pb); Lj[q4] += at(Lo, b2.ph + k * Pb);
      if (fi - dl >= 0 && fi + dl < N) Nj[q4] += Math.abs(E[3][fi + dl] - E[3][fi - dl]) + .5 * Math.abs(E[0][fi + dl] - E[0][fi - dl]);
      cn[q4]++;
    }
    for (k = 0; k < 4; k++) { Mj[k] /= cn[k] || 1; Lj[k] /= cn[k] || 1; Nj[k] /= cn[k] || 1; }
    var lm = (Lj[0] + Lj[1] + Lj[2] + Lj[3]) / 4, nm = (Nj[0] + Nj[1] + Nj[2] + Nj[3]) / 4, db = 0, dbs = -1e9;
    for (k = 0; k < 4; k++) { var sd = (Mj[(k + 1) % 4] + Mj[(k + 3) % 4]) - (Mj[k] + Mj[(k + 2) % 4]) + .3 * (Lj[k] - lm) + (Nj[k] - nm); if (sd > dbs) { dbs = sd; db = k; } }
    var r3 = function (v) { return Math.round(v * 1000) / 1000; };
    return { bpm: r3(b2.bpm), b0: r3((b2.ph * hop + win * .5) / sr + .013), db: db, conf: Math.round(b2.s / mean * 100) / 100 };
  }
  function grid(url, hint) {
    var key = url + "|" + Math.round(hint || 0);
    if (BEATS[key]) return Promise.resolve(BEATS[key]);
    if (beatPend[key]) return beatPend[key];
    if (!W.fetch || !(W.OfflineAudioContext || W.webkitOfflineAudioContext)) return Promise.resolve(null);
    return (beatPend[key] = W.fetch(url, { mode: "cors", credentials: "omit" })
      .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.arrayBuffer(); })
      .then(decodeAudio).then(bands).then(function (r) { return new Promise(function (res) { setTimeout(function () { res(gridFrom(r, hint)); }, 30); }); })
      .then(function (g) { delete beatPend[key]; if (g) { BEATS[key] = g; saveBeats(); } return g; }, function () { delete beatPend[key]; return null; }));
  }
  /* ---------------- time-stretch with the pitch kept: WSOLA (as in SoundTouch's TDStretch) ----------------
     rate > 1 plays faster. 60 ms segments joined by 12 ms raised-cosine crossfades; each splice point is searched
     ±8 ms for the best waveform match (coarse on a 4× decimated mono mix, then sample-exact). Transient-aware:
     a splice never crossfades through a drum hit or a consonant, and never skips or repeats one. Output position
     t always takes input from t × rate (± the 8 ms search), so beat times map linearly. ~50 ms per 30 s preview. */
  function wsola(chs, rate, sr, map) {          /* map (optional): { inAt(outSample) → inSample, outN } for a varying rate */
    var nC = chs.length, N = chs[0].length, c, i, j;
    if (!map && (!(rate > 0) || Math.abs(rate - 1) < 1e-6 || N < sr)) return chs.map(function (x) { return new Float32Array(x); });
    var seq = Math.round(sr * .06), ov = Math.round(sr * .012), sw = Math.round(sr * .008), hop = seq - ov;
    var outN = Math.max(1, map ? Math.round(map.outN) : Math.round(N / rate)), out = [];
    for (c = 0; c < nC; c++) out.push(new Float32Array(outN + seq + Math.round(sr * .03)));
    var mono = new Float32Array(N), md = new Float32Array((N >> 2) + 1);
    for (c = 0; c < nC; c++) { var xc = chs[c]; for (i = 0; i < N; i++) mono[i] += xc[i]; }
    for (i = 0; i + 3 < N; i += 4) md[i >> 2] = mono[i] + mono[i + 1] + mono[i + 2] + mono[i + 3];
    /* transients (drum hits, consonants): 1 ms blocks whose high-frequency energy jumps 6× above the last 20 ms */
    var B = Math.max(1, Math.round(sr / 1000)), nb = Math.ceil(N / B) + 1, en = new Float64Array(nb), pre = new Int32Array(nb + 1), run = 0, peak = 0;
    for (i = 1; i < N; i++) { var dd = mono[i] - mono[i - 1]; en[(i / B) | 0] += dd * dd; }
    for (j = 0; j < nb; j++) if (en[j] > peak) peak = en[j];
    for (j = 0; j < nb; j++) {
      var mean = j >= 20 ? run / 20 : j ? run / j : en[0];
      pre[j + 1] = pre[j] + (en[j] > 6 * mean && en[j] > peak * 1e-4 ? 1 : 0);
      run += en[j]; if (j >= 20) run -= en[j - 20];
    }
    function hasTr(a, b2) { var ja = Math.max(0, Math.floor(a / B)), jb = Math.min(nb, Math.ceil(b2 / B)); return jb > ja && pre[jb] > pre[ja]; }
    function firstTr(a, b2) {                       /* input sample of the first transient block in [a, b2), or −1 */
      var ja = Math.max(0, Math.floor(a / B)), jb = Math.min(nb, Math.ceil(b2 / B));
      if (jb <= ja || pre[jb] === pre[ja]) return -1;
      for (var k = ja; k < jb; k++) if (pre[k + 1] > pre[k]) return k * B;
      return -1;
    }
    var outAt = map ? map.outAt : function (x) { return x / rate; };
    var w = new Float32Array(ov); for (i = 0; i < ov; i++) w[i] = .5 - .5 * Math.cos(Math.PI * (i + .5) / ov);
    /* best splice: normalised waveform correlation with the natural continuation, minus a heavy penalty when the
       material that would be skipped or repeated (between ref and s) holds a transient */
    function best(a, D2, ra, lo, hi, len, ref, ideal) {
      var bs = lo, bv = -1e30, k, s2, nrm = 0, rn = 0, cr, v;
      for (k = 0; k < len; k++) { nrm += a[lo + k] * a[lo + k]; rn += a[ra + k] * a[ra + k]; }
      for (s2 = lo; s2 <= hi; s2++) {
        if (s2 > lo) { var o1 = a[s2 - 1], n1 = a[s2 + len - 1]; nrm += n1 * n1 - o1 * o1; }
        cr = 0; for (k = 0; k < len; k++) cr += a[ra + k] * a[s2 + k];
        v = cr / Math.sqrt(Math.max(1e-12, nrm * rn));                                   /* −1 … 1 */
        var sx = s2 * D2; if (hasTr(Math.min(sx, ref) - B, Math.max(sx, ref) + ov + B)) v -= 3;
        v -= .35 * Math.abs(sx - ideal) / sw;                                             /* stay close to the ideal timing */
        if (v > bv) { bv = v; bs = s2; }
      }
      return bs;
    }
    var prev = 0, segOut = 0, filled = Math.min(seq, N);
    for (c = 0; c < nC; c++) out[c].set(chs[c].subarray(0, filled), 0);
    var maxExt = Math.round(sr * .025), pad = 2 * B, dev = 0, ideal = 0; /* dev: running mean of (chosen − ideal) input position */
    while (true) {
      /* move the splice later (≤ 25 ms) while it would crossfade through a hit, or while every candidate in the
         search window would skip (speeding up) or repeat (slowing down) one */
      var ext = 0, op, ref, tg, lo, hi;
      for (;;) {
        op = segOut + hop + ext; ref = prev + hop + ext; ideal = map ? map.inAt(op) : op * rate; tg = Math.round(ideal - .8 * dev); lo = Math.max(0, tg - sw); hi = Math.min(N - seq, tg + sw);
        var bad = hasTr(ref - pad, ref + ov + pad) || (ref < lo && hasTr(ref, lo + ov + pad)) || (ref > hi && hasTr(hi - pad, ref + ov));
        if (!bad || ext >= maxExt) break;
        ext += B;
      }
      /* hit lock: the next hit not yet heard gets a splice of its own, placed so that it sounds at its own time (output =
         map⁻¹ of its input time) instead of (1 − rate) × its depth in a 60 ms segment early or late. The segment start
         may move against the regular hop, as long as the hit sits in the body (never in a crossfade), the previous
         segment's run-on stops before the hit, and nothing else is skipped or repeated. */
      if (outAt) {
        var trI = firstTr(prev + seq + B, Math.min(N - seq, prev + seq + hop + maxExt + seq));
        if (trI >= 0) {
          var oT = outAt(trI), L1 = Math.max(oT - seq + 3 * B, segOut + ov + 2 * B), H1 = Math.min(oT - ov - 3 * B, segOut + hop + maxExt, segOut + (trI - prev) - ov - 2 * B);
          if (L1 <= H1) {
            var opL = Math.round(clamp(segOut + hop, L1, H1)), spL = Math.round(trI - (oT - opL)), refL = prev + (opL - segOut);
            if (spL >= 0 && spL + seq <= N && opL < outN && !hasTr(Math.min(spL, refL) - B, Math.max(spL, refL) + ov + B)) {
              op = opL; ref = refL; ideal = spL; tg = spL; lo = Math.max(0, spL - 2 * B); hi = Math.min(N - seq, spL + 2 * B);
            }
          }
        }
      }
      if (op >= outN || ref + ov > N || hi < lo) break;
      var need = op + ov - segOut;
      if (need > filled) { for (c = 0; c < nC; c++) out[c].set(chs[c].subarray(prev + filled, prev + need), segOut + filled); filled = need; }
      var cs = best(md, 4, ref >> 2, lo >> 2, hi >> 2, ov >> 2, ref, ideal) << 2;
      var sp = best(mono, 1, ref, Math.max(lo, cs - 4), Math.min(hi, cs + 4), ov, ref, ideal);
      dev += .15 * ((sp - ideal) - dev);       /* feedback: content timing has no lasting bias in either direction */
      for (c = 0; c < nC; c++) {
        var o = out[c], x = chs[c];
        for (i = 0; i < ov; i++) o[op + i] = o[op + i] * (1 - w[i]) + x[sp + i] * w[i];
        o.set(x.subarray(sp + ov, sp + seq), op + ov);
      }
      prev = sp; segOut = op; filled = seq;
    }
    var have = segOut + filled, left = Math.min(outN - have, N - (prev + filled)); /* the last few ms: plain continuation */
    if (left > 0) for (c = 0; c < nC; c++) out[c].set(chs[c].subarray(prev + filled, prev + filled + left), have);
    return out.map(function (o2) { return o2.subarray(0, outN); });
  }
  /* key shift with the tempo kept: WSOLA to rate / p, then resample by p = 2^(semitones / 12) (Catmull-Rom).
     Beat times map exactly like a plain stretch to `rate`; ±1–2 semitones keep the voice natural. */
  function resampleTo(x, p, outN) {
    var y = new Float32Array(outN), L = x.length;
    for (var i = 0; i < outN; i++) {
      var t = i * p, k = t | 0, f = t - k;
      if (k + 2 >= L) { y[i] = k < L ? x[k] : 0; continue; }
      var a = k > 0 ? x[k - 1] : x[0], b = x[k], c = x[k + 1], d = x[k + 2];
      y[i] = b + .5 * f * (c - a + f * (2 * a - 5 * b + 4 * c - d + f * (3 * (b - c) + d - a)));
    }
    return y;
  }
  /* a tempo ride (word play, tempos 10–30 % apart): rate r0 until input sample i1, then the rate glides linearly in
     output time to 1 by input sample i2, then 1. B keeps A's beat at the cut and comes home to its own tempo. */
  function rideMap(N, r0, i1, i2) {
    i1 = Math.max(0, Math.min(N, i1)); i2 = Math.max(i1, Math.min(N, i2));
    var o1 = i1 / r0, T2 = i2 > i1 ? 2 * (i2 - i1) / (r0 + 1) : 0, o2 = o1 + T2;
    return { outN: Math.max(1, Math.round(o2 + (N - i2))), inAt: function (o) {
      if (o <= o1) return o * r0;
      if (o <= o2) { var u = o - o1; return i1 + r0 * u + (1 - r0) * u * u / (2 * T2); }
      return i2 + (o - o2);
    }, outAt: function (i) {
      if (i <= i1) return i / r0;
      if (i >= i2) return o2 + (i - i2);
      var a = (1 - r0) / (2 * T2), c = -(i - i1);
      return o1 + (Math.abs(a) < 1e-12 ? -c / r0 : (-r0 + Math.sqrt(Math.max(0, r0 * r0 - 4 * a * c))) / (2 * a));
    } };
  }
  function shiftStretch(chs, rate, semis, sr, ride) {
    var map = ride && ride.i2 > ride.i1 ? rideMap(chs[0].length, rate, ride.i1 * sr, ride.i2 * sr) : null;
    if (!semis) return wsola(chs, rate, sr, map);
    var p = Math.pow(2, semis / 12), outN = map ? map.outN : Math.max(1, Math.round(chs[0].length / rate));
    var st = wsola(chs, rate / p, sr, map ? { outN: map.outN * p, inAt: function (o) { return map.inAt(o / p); }, outAt: function (i) { return map.outAt(i) * p; } } : null);
    return st.map(function (x) { return resampleTo(x, p, outN); });
  }
  /* beat grids measured on GitHub Actions from the previews (beats.json): key → [bpm, b0, db, conf, urlhash] */
  var BG = {}, AN = {}, AN2 = {};
  function seedAnalysis(map) {
    var n = 0; if (!map || typeof map !== "object") return 0;
    Object.keys(map).forEach(function (k) { var v = map[k]; if (v && typeof v === "object" && !v.err) { AN[k] = v; n++; } });
    return n;
  }
  function seedListen(map) {             /* listen.json: per-bar notes / chords and the vocal level per beat (vr) */
    var n = 0; if (!map || typeof map !== "object") return 0;
    Object.keys(map).forEach(function (k) { var v = map[k]; if (v && typeof v === "object") { AN2[k] = v; n++; } });
    return n;
  }
  function hex8(h) { return ("0000000" + (h >>> 0).toString(16)).slice(-8); }
  function seedBeats(map) {
    var n = 0; if (!map || typeof map !== "object") return 0;
    Object.keys(map).forEach(function (k) { var v = map[k]; if (v && v.length >= 5 && v[0] > 30 && v[0] < 260) { BG[k] = v; n++; } });
    return n;
  }
  function decodeOn(c, ab) {
    return new Promise(function (res, rej) { try { var p = c.decodeAudioData(ab, res, rej); if (p && p.then) p.then(res, rej); } catch (e) { rej(e); } });
  }
  /* seed(map): preview links resolved ahead of time (previews.json, built on GitHub Actions), so a tap
     starts the original synchronously and the phone never has to call the Search API */
  function seed(map) {
    var n = 0; if (!map || typeof map !== "object") return 0;
    Object.keys(map).forEach(function (k) { var v = map[k]; if (!v || typeof v !== "object") return; if (v.p) { cache[k] = { p: String(v.p), a: v.a ? String(v.a) : null }; n++; } else if (v.miss && !(cache[k] && cache[k].p)) { cache[k] = { miss: Date.now() }; } });
    return n;
  }
  W.MashEngine = { create: create, version: "6.4", seed: seed, seedBeats: seedBeats, seedAnalysis: seedAnalysis, seedListen: seedListen, _render: render, _pick: pick, _proc: buildProc, _grid: grid, _wsola: wsola, _shift: shiftStretch, _rideMap: rideMap, _hash: function (u) { return hex8(hash(u)); } };
})();
