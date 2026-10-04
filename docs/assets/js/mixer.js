/* DJ Lab — Mix Trainer: two Web Audio decks, 3-band EQ + filter, faders, crossfader, VU meters,
   zoomed beat-grid waveforms and a beat-phase meter (B vs A) for learning to beatmatch by ear.
   AudioBufferSourceNode.playbackRate is used for tempo, so pitch follows tempo ("no Master Tempo"). */
(function () {
  'use strict';
  var DJ = window.DJ, I = DJ.icon, esc = DJ.esc;
  var ctx = null, masterGain = null, anL = null, anR = null;
  var decks = [], bufCache = new Map();
  var opts = { showBpm: true, showPhase: true, quantize: false, curve: DJ.store.get('mx-curve', 'blend'), zoom: DJ.store.get('mx-zoom', 6) };
  var xf = 0, xfFader = null;
  var SLOTS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];

  /* ------------------------------------------------------------------ audio context */
  function ensureCtx() {
    if (ctx) { if (ctx.state === 'suspended') ctx.resume(); return ctx; }
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) { DJ.toast('הדפדפן הזה לא תומך ב-Web Audio.'); return null; }
    ctx = new AC({ latencyHint: 'interactive' });
    masterGain = ctx.createGain(); masterGain.gain.value = 0.8;
    var lim = ctx.createDynamicsCompressor();
    lim.threshold.value = -3; lim.knee.value = 0; lim.ratio.value = 20; lim.attack.value = 0.002; lim.release.value = 0.15;
    masterGain.connect(lim); lim.connect(ctx.destination);
    var sp = ctx.createChannelSplitter(2); lim.connect(sp);
    anL = ctx.createAnalyser(); anR = ctx.createAnalyser(); anL.fftSize = anR.fftSize = 1024;
    sp.connect(anL, 0); sp.connect(anR, 1);
    decks.forEach(function (d) { d.buildGraph(); });
    applyXfader();
    return ctx;
  }

  /* ------------------------------------------------------------------ loading */
  function fetchProgress(url, cb) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      var total = +r.headers.get('content-length') || 0;
      if (!r.body || !total || !r.body.getReader) return r.arrayBuffer();
      var reader = r.body.getReader(), chunks = [], got = 0;
      function pump() {
        return reader.read().then(function (res) {
          if (res.done) { var out = new Uint8Array(got), o = 0; chunks.forEach(function (c) { out.set(c, o); o += c.length; }); return out.buffer; }
          chunks.push(res.value); got += res.value.length; if (cb) cb(got / total);
          return pump();
        });
      }
      return pump();
    });
  }
  function decodeBuf(ab) {
    var OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    var off = new OAC(2, 1, 44100);
    return new Promise(function (res, rej) { var p = off.decodeAudioData(ab, res, rej); if (p && p.then) p.then(res, rej); });
  }
  function envelope(buf) {
    var sr = buf.sampleRate, hop = Math.round(sr / 200), n = Math.ceil(buf.length / hop);
    var L = buf.getChannelData(0), R = buf.numberOfChannels > 1 ? buf.getChannelData(1) : L;
    var amp = new Float32Array(n), low = new Float32Array(n), a = 1 - Math.exp(-2 * Math.PI * 160 / sr), y = 0, mx = 1e-6;
    for (var i = 0, k = 0; k < n; k++) {
      var m = 0, ml = 0, end = Math.min(buf.length, i + hop);
      for (; i < end; i++) {
        var s = (L[i] + R[i]) * 0.5; y += a * (s - y);
        var as = s < 0 ? -s : s, al = y < 0 ? -y : y;
        if (as > m) m = as; if (al > ml) ml = al;
      }
      amp[k] = m; low[k] = ml; if (m > mx) mx = m;
    }
    for (var j = 0; j < n; j++) { amp[j] /= mx; low[j] = Math.min(1, low[j] / mx * 1.6); }
    return { amp: amp, low: low, rate: sr / hop, n: n };
  }
  function load(file, onProgress) {
    if (bufCache.has(file)) return bufCache.get(file);
    var p = fetchProgress(DJ.media(file), onProgress).then(decodeBuf).then(function (buffer) { return { buffer: buffer, env: envelope(buffer) }; });
    bufCache.set(file, p);
    p.catch(function () { bufCache.delete(file); });
    return p;
  }

  /* ------------------------------------------------------------------ deck */
  function Deck(id, host) {
    this.id = id; this.host = host; this.item = null; this.buffer = null; this.env = null;
    this.playing = false; this.pos = 0; this.lastT = 0; this.src = null; this.rateApplied = 1;
    this.tempo = 0; this.range = 8; this.bend = 1; this.jog = 1; this.cue = 0; this.loadToken = 0;
    this.eq = { low: 0, mid: 0, high: 0 }; this.filter = 0; this.trimDb = 0; this.fader = 1;
    this.build();
  }
  Deck.prototype.duration = function () { return this.buffer ? this.buffer.duration : (this.item && this.item.duration_sec) || 0; };
  Deck.prototype.rate = function () { return (1 + this.tempo / 100) * this.bend * this.jog; };
  Deck.prototype.position = function () {
    if (!this.playing || !ctx) return this.pos;
    return Math.min(this.pos + (ctx.currentTime - this.lastT) * this.rateApplied, this.duration());
  };
  Deck.prototype.commit = function () { this.pos = this.position(); this.lastT = ctx ? ctx.currentTime : 0; };
  Deck.prototype.applyRate = function () {
    if (this.playing) this.commit();
    this.rateApplied = this.rate();
    if (this.src && ctx) this.src.playbackRate.setValueAtTime(this.rateApplied, ctx.currentTime);
  };
  Deck.prototype.buildGraph = function () {
    if (!ctx || this.nodes) return;
    var n = this.nodes = {};
    n.trim = ctx.createGain();
    n.low = ctx.createBiquadFilter(); n.low.type = 'lowshelf'; n.low.frequency.value = 70;
    n.mid = ctx.createBiquadFilter(); n.mid.type = 'peaking'; n.mid.frequency.value = 1000; n.mid.Q.value = 0.7;
    n.high = ctx.createBiquadFilter(); n.high.type = 'highshelf'; n.high.frequency.value = 13000;
    n.hp = ctx.createBiquadFilter(); n.hp.type = 'highpass'; n.hp.frequency.value = 10; n.hp.Q.value = 0.9;
    n.lp = ctx.createBiquadFilter(); n.lp.type = 'lowpass'; n.lp.frequency.value = 22000; n.lp.Q.value = 0.9;
    n.fader = ctx.createGain(); n.xf = ctx.createGain();
    n.an = ctx.createAnalyser(); n.an.fftSize = 1024;
    n.trim.connect(n.low); n.low.connect(n.mid); n.mid.connect(n.high); n.high.connect(n.hp); n.hp.connect(n.lp);
    n.lp.connect(n.fader); n.fader.connect(n.xf); n.xf.connect(masterGain); n.fader.connect(n.an);
    this.applyMix();
  };
  Deck.prototype.applyMix = function () {
    var n = this.nodes; if (!n) return;
    var t = ctx.currentTime;
    n.trim.gain.setTargetAtTime(Math.pow(10, this.trimDb / 20), t, 0.01);
    ['low', 'mid', 'high'].forEach(function (b) { var db = this.eq[b] <= -25.9 ? -40 : this.eq[b]; n[b].gain.setTargetAtTime(db, t, 0.008); }, this);
    var f = this.filter, lpF = 22000, hpF = 10;
    if (f < -0.02) lpF = Math.exp(Math.log(20000) + (Math.log(70) - Math.log(20000)) * Math.pow(-f, 0.85));
    if (f > 0.02) hpF = Math.exp(Math.log(20) + (Math.log(9000) - Math.log(20)) * Math.pow(f, 0.85));
    n.lp.frequency.setTargetAtTime(lpF, t, 0.015); n.hp.frequency.setTargetAtTime(hpF, t, 0.015);
    n.lp.Q.value = f < -0.02 ? 1.3 : 0.7; n.hp.Q.value = f > 0.02 ? 1.3 : 0.7;
    var fg = this.fader; n.fader.gain.setTargetAtTime(fg * fg, t, 0.01);
  };
  Deck.prototype.startSrc = function () {
    var self = this;
    var s = ctx.createBufferSource(); s.buffer = this.buffer;
    this.rateApplied = this.rate();
    s.playbackRate.value = this.rateApplied;
    s.connect(this.nodes.trim);
    s.onended = function () { if (self.src === s && self.playing && self.position() >= self.duration() - 0.05) { self.playing = false; self.pos = self.duration(); self.src = null; self.syncUI(); } };
    s.start(0, Math.min(this.pos, Math.max(0, this.duration() - 0.01)));
    this.lastT = ctx.currentTime; this.src = s;
  };
  Deck.prototype.stopSrc = function () {
    if (!this.src) return;
    this.src.onended = null;
    try { this.src.stop(); } catch (e) { /* already stopped */ }
    try { this.src.disconnect(); } catch (e) { /* */ }
    this.src = null;
  };
  Deck.prototype.play = function () {
    if (!this.buffer) { DJ.toast('טענו קודם טראק לדק ' + this.id); return; }
    if (!ensureCtx()) return;
    if (this.playing) return;
    if (this.pos >= this.duration() - 0.05) this.pos = 0;
    this.startSrc(); this.playing = true; this.syncUI();
  };
  Deck.prototype.pause = function () { if (!this.playing) return; this.commit(); this.stopSrc(); this.playing = false; this.syncUI(); };
  Deck.prototype.toggle = function () { if (this.playing) this.pause(); else this.play(); };
  Deck.prototype.seek = function (t) {
    t = DJ.clamp(t, 0, Math.max(0, this.duration() - 0.01));
    if (this.playing) { this.stopSrc(); this.pos = t; this.startSrc(); } else this.pos = t;
    this.dirty = true;
  };
  Deck.prototype.beatLen = function () { return this.item && this.item.bpm ? 60 / this.item.bpm : 0.5; };
  Deck.prototype.firstBeat = function () { return (this.item && this.item.first_downbeat_sec) || 0; };
  Deck.prototype.quantizeTime = function (t) { var bl = this.beatLen(), fd = this.firstBeat(); return fd + Math.round((t - fd) / bl) * bl; };
  Deck.prototype.beatInfo = function () {
    if (!this.item || !this.item.bpm) return null;
    var bpb = this.item.beats_per_bar || 4;
    var beats = (this.position() - this.firstBeat()) / this.beatLen();
    var b = Math.floor(beats + 1e-6);
    return { beats: beats, phase: beats - Math.floor(beats), barBeat: ((b % bpb) + bpb) % bpb, bar: Math.floor(b / bpb), bpb: bpb };
  };
  Deck.prototype.effBpm = function () { return this.item && this.item.bpm ? this.item.bpm * this.rate() : 0; };
  Deck.prototype.setTempo = function (v) { this.tempo = v; this.applyRate(); this.paintTempo(); };

  /* ---------- deck UI ---------- */
  Deck.prototype.build = function () {
    var self = this, id = this.id, h = this.host;
    h.innerHTML =
      '<div class="deck-head"><span class="deck-id">' + id + '</span>' +
      '<label class="select-field select-field--sm deck-load"><span class="sr-only">טעינת טראק לדק ' + id + '</span><select data-load></select></label></div>' +
      '<div class="deck-screen">' +
      '<div class="ds-top"><div class="ds-title" data-title>בחרו טראק לדק ' + id + '</div><div class="ds-sub" data-sub dir="rtl"></div></div>' +
      '<div class="ds-readouts">' +
      '<div class="ro ro-bpm"><span class="k">BPM</span><span class="v" data-bpm>--</span><span class="ro-orig" data-orig></span></div>' +
      '<div class="ro"><span class="k">TEMPO</span><span class="v" data-tempo>0.00%</span><span class="ro-orig" data-range>±8%</span></div>' +
      '<div class="ro"><span class="k">KEY</span><span class="v" data-key>--</span></div>' +
      '<div class="ro ro-time"><span class="k">REMAIN</span><span class="v" data-time>-0:00</span><span class="ro-orig" data-elapsed>0:00</span></div></div>' +
      '<div class="ds-overview"><canvas data-overview aria-label="Waveform של דק ' + id + ' - לחצו כדי לקפוץ"></canvas><div class="ds-load" data-loadbar hidden><span></span><em>טוען…</em></div></div>' +
      '<div class="ds-beats" aria-hidden="true"><span class="beat"></span><span class="beat"></span><span class="beat"></span><span class="beat"></span><span class="ds-bar" data-bar>Bar —</span></div>' +
      '</div>' +
      '<div class="deck-body">' +
      '<div class="jog-col"><div class="jog" data-jog role="slider" tabindex="0" aria-label="Jog דק ' + id + ': גררו סיבובית כדי לדחוף או לגרור, או השתמשו בחצים" aria-valuetext="Jog"><div class="jog-plate" data-plate><span class="jog-mark"></span></div><div class="jog-center"><span>' + id + '</span></div></div>' +
      '<div class="bend-row"><button type="button" class="pad-btn" data-bend="-1" aria-label="Pitch bend - האטה זמנית">' + I('chev-left') + '<span>האטה</span></button><button type="button" class="pad-btn" data-bend="1" aria-label="Pitch bend - האצה זמנית"><span>האצה</span>' + I('chev-right') + '</button></div></div>' +
      '<div class="tempo-col"><div class="tempo-top"><button type="button" class="mini-btn" data-range-btn aria-label="טווח Tempo">±8</button></div><div data-tempo-fader class="tempo-wrap"><span class="t-lab t-minus">−</span><span class="t-lab t-plus">+</span></div>' +
      '<button type="button" class="mini-btn" data-tempo-reset aria-label="איפוס Tempo">0%</button><button type="button" class="mini-btn mini-btn--sync" data-sync title="רמאות קטנה: מכוון טמפו ומיישר ביט. נסו קודם באוזן!">SYNC</button></div>' +
      '</div>' +
      '<div class="pads" data-pads></div>' +
      '<div class="transport"><button type="button" class="tb tb-cue" data-cue aria-label="CUE דק ' + id + '">CUE</button><button type="button" class="tb tb-play" data-play aria-label="Play דק ' + id + '">' + I('play') + '</button></div>';
    var $ = function (s) { return h.querySelector(s); };
    this.ui = {
      load: $('[data-load]'), title: $('[data-title]'), sub: $('[data-sub]'), bpm: $('[data-bpm]'), orig: $('[data-orig]'), tempo: $('[data-tempo]'),
      rangeLab: $('[data-range]'), key: $('[data-key]'), time: $('[data-time]'), elapsed: $('[data-elapsed]'), overview: $('[data-overview]'), loadbar: $('[data-loadbar]'),
      beats: h.querySelectorAll('.beat'), bar: $('[data-bar]'), jog: $('[data-jog]'), plate: $('[data-plate]'), pads: $('[data-pads]'),
      cue: $('[data-cue]'), play: $('[data-play]'), rangeBtn: $('[data-range-btn]')
    };
    this.wave = new DJ.Wave(this.ui.overview, { peaks: null, barW: 2, gap: 0.4, seed: id === 'A' ? 3 : 9, onSeek: function (f) { if (self.buffer) self.seek(f * self.duration()); } });
    this.tempoFader = new DJ.Fader({
      orient: 'v', min: -8, max: 8, step: 0.01, fine: 0.02, def: 0, invert: true, name: 'Tempo fader דק ' + id + ' (למטה = מהר יותר)', cls: 'fader--tempo',
      format: function (v) { return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(2) + '%'; },
      onInput: function (v) { self.setTempo(v); }
    });
    $('[data-tempo-fader]').appendChild(this.tempoFader.el);
    $('[data-tempo-reset]').addEventListener('click', function () { self.tempoFader.set(0, true); });
    this.ui.rangeBtn.addEventListener('click', function () {
      var r = self.range === 8 ? 16 : self.range === 16 ? 6 : 8;
      if (Math.abs(self.tempo) > r) self.tempoFader.set(DJ.clamp(self.tempo, -r, r), true);
      self.range = r; self.tempoFader.setRange(-r, r); self.ui.rangeBtn.textContent = '±' + r; self.ui.rangeLab.textContent = '±' + r + '%';
    });
    $('[data-sync]').addEventListener('click', function () { syncDeck(self); });
    this.ui.load.addEventListener('change', function () { var v = self.ui.load.value; if (v) self.loadItem(DJ.byId.get(v)); });
    this.ui.play.addEventListener('click', function () { ensureCtx(); self.toggle(); });
    // CUE: CDJ behaviour
    var cueHeld = false;
    var cueDown = function () {
      if (!self.buffer) return;
      ensureCtx();
      if (self.playing) { self.pause(); self.seek(self.cue); return; }
      var p = self.position();
      if (Math.abs(p - self.cue) > 0.02) { self.cue = opts.quantize ? self.quantizeTime(p) : p; self.seek(self.cue); self.paintCueMark(); }
      cueHeld = true; self.play(); self.ui.cue.classList.add('is-held');
    };
    var cueUp = function () { if (!cueHeld) return; cueHeld = false; self.ui.cue.classList.remove('is-held'); self.pause(); self.seek(self.cue); self.syncUI(); };
    this.cueDown = cueDown; this.cueUp = cueUp;
    this.ui.cue.addEventListener('pointerdown', function (e) { e.preventDefault(); cueDown(); });
    this.ui.cue.addEventListener('pointerup', cueUp); this.ui.cue.addEventListener('pointerleave', cueUp);
    this.ui.cue.addEventListener('keydown', function (e) { if ((e.key === 'Enter' || e.key === ' ') && !e.repeat) { e.preventDefault(); cueDown(); } });
    this.ui.cue.addEventListener('keyup', function (e) { if (e.key === 'Enter' || e.key === ' ') cueUp(); });
    // bend buttons
    h.querySelectorAll('[data-bend]').forEach(function (b) {
      var dir = +b.getAttribute('data-bend');
      var on = function (e) { if (e) e.preventDefault(); self.setBend(dir); b.classList.add('is-held'); };
      var off = function () { self.setBend(0); b.classList.remove('is-held'); };
      b.addEventListener('pointerdown', on); b.addEventListener('pointerup', off); b.addEventListener('pointerleave', off); b.addEventListener('pointercancel', off);
      b.addEventListener('keydown', function (e) { if ((e.key === 'Enter' || e.key === ' ') && !e.repeat) on(e); });
      b.addEventListener('keyup', off);
    });
    this.buildJog();
    this.renderPads();
    this.syncUI();
  };
  Deck.prototype.setBend = function (dir) { this.bend = dir ? 1 + dir * 0.04 : 1; this.applyRate(); this.ui.jog.classList.toggle('is-bend', !!dir); };
  Deck.prototype.buildJog = function () {
    var self = this, jog = this.ui.jog, last = null, lastT = 0, rel = null;
    function ang(e) { var r = jog.getBoundingClientRect(); return Math.atan2(e.clientY - (r.top + r.height / 2), e.clientX - (r.left + r.width / 2)); }
    jog.addEventListener('pointerdown', function (e) { if (!self.buffer) return; ensureCtx(); last = ang(e); lastT = performance.now(); try { jog.setPointerCapture(e.pointerId); } catch (x) { /* */ } jog.classList.add('is-touch'); e.preventDefault(); });
    jog.addEventListener('pointermove', function (e) {
      if (last === null) return;
      var a = ang(e), d = a - last; if (d > Math.PI) d -= 2 * Math.PI; if (d < -Math.PI) d += 2 * Math.PI;
      var now = performance.now(), dt = Math.max(8, now - lastT);
      last = a; lastT = now;
      if (self.playing) {
        var vel = d / (dt / 1000); // rad/s
        self.jog = DJ.clamp(1 + vel * 0.06, 0.7, 1.3); self.applyRate();
        clearTimeout(rel); rel = setTimeout(function () { self.jog = 1; self.applyRate(); }, 90);
      } else {
        self.seek(self.pos + d / (2 * Math.PI) * 1.8);
      }
    });
    var up = function () { last = null; jog.classList.remove('is-touch'); clearTimeout(rel); if (self.jog !== 1) { self.jog = 1; self.applyRate(); } };
    jog.addEventListener('pointerup', up); jog.addEventListener('pointercancel', up);
    jog.addEventListener('wheel', function (e) {
      if (!self.buffer) return; e.preventDefault();
      var dir = e.deltaY > 0 ? 1 : -1;
      if (self.playing) { self.jog = 1 + dir * 0.06; self.applyRate(); clearTimeout(rel); rel = setTimeout(function () { self.jog = 1; self.applyRate(); }, 120); }
      else self.seek(self.pos + dir * 0.015);
    }, { passive: false });
    jog.addEventListener('keydown', function (e) {
      if (!self.buffer) return;
      var dir = e.key === 'ArrowRight' || e.key === 'ArrowUp' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowDown' ? -1 : 0;
      if (!dir) return;
      e.preventDefault();
      if (self.playing) { self.jog = 1 + dir * 0.05; self.applyRate(); clearTimeout(rel); rel = setTimeout(function () { self.jog = 1; self.applyRate(); }, 150); }
      else self.seek(self.pos + dir * 0.01);
    });
  };
  Deck.prototype.renderPads = function () {
    var self = this, cues = {}, it = this.item;
    ((it && it.cues) || []).forEach(function (c) { cues[c.slot] = c; });
    this.ui.pads.innerHTML = SLOTS.map(function (s) {
      var c = cues[s];
      return '<button type="button" class="hc' + (c ? '' : ' is-empty') + '" data-slot="' + s + '" style="--c:' + (c ? esc(c.color || DJ.CUE_COLORS[s]) : 'transparent') + '" ' + (c ? 'title="' + esc(c.name) + ' · Bar ' + ((c.bar || 0) + 1) + '" aria-label="Hot Cue ' + s + ': ' + esc(c.name) + '"' : 'disabled aria-label="Hot Cue ' + s + ' ריק"') + '><b>' + s + '</b><span>' + (c ? esc(c.name) : '') + '</span></button>';
    }).join('');
    this.ui.pads.querySelectorAll('[data-slot]').forEach(function (b) {
      b.addEventListener('click', function () { self.hotCue(b.getAttribute('data-slot')); });
    });
  };
  Deck.prototype.hotCue = function (slot) {
    var c = ((this.item && this.item.cues) || []).filter(function (x) { return x.slot === slot; })[0];
    if (!c || !this.buffer) return;
    ensureCtx();
    this.seek(c.sec); this.cue = c.sec; this.paintCueMark();
    if (!this.playing) this.play();
    var b = this.ui.pads.querySelector('[data-slot="' + slot + '"]');
    if (b) { b.classList.add('is-hit'); setTimeout(function () { b.classList.remove('is-hit'); }, 160); }
  };
  Deck.prototype.paintCueMark = function () {
    var d = this.duration(), marks = [];
    ((this.item && this.item.cues) || []).forEach(function (c) { if (d) marks.push({ f: c.sec / d, color: c.color || DJ.CUE_COLORS[c.slot] }); });
    if (d) marks.push({ f: this.cue / d, color: '#ffb020' });
    this.wave.o.marks = marks; this.wave.draw();
  };
  Deck.prototype.paintTempo = function () {
    var t = this.tempo;
    this.ui.tempo.textContent = (t > 0 ? '+' : t < 0 ? '−' : '') + Math.abs(t).toFixed(2) + '%';
    this.ui.tempo.parentNode.classList.toggle('is-zero', Math.abs(t) < 0.005);
  };
  Deck.prototype.syncUI = function () {
    var it = this.item;
    this.ui.play.innerHTML = I(this.playing ? 'pause' : 'play');
    this.ui.play.classList.toggle('is-on', this.playing);
    this.ui.play.setAttribute('aria-label', (this.playing ? 'Pause' : 'Play') + ' דק ' + this.id);
    this.host.classList.toggle('is-playing', this.playing);
    this.ui.cue.classList.toggle('is-blink', !!this.buffer && !this.playing);
    if (!it) return;
    this.ui.title.textContent = it.title || it.id;
    this.ui.sub.innerHTML = esc(it.title_he || '') + (it.genre ? ' · ' + esc(it.genre) : '');
    var cam = DJ.camOf(it);
    this.ui.key.innerHTML = cam ? DJ.camBadge(cam) + ' <small>' + esc(it.key_short || DJ.cam.keys[cam] || '') + '</small>' : '--';
    this.paintTempo();
  };
  Deck.prototype.frame = function () {
    var it = this.item, p = this.position(), d = this.duration();
    if (!it) return;
    this.wave.set(d ? p / d : 0);
    if (this.playing && p >= d - 0.02) { this.playing = false; this.pos = d; this.stopSrc(); this.syncUI(); }
    var bpm = this.effBpm();
    this.ui.bpm.textContent = opts.showBpm ? (bpm ? bpm.toFixed(2) : '--') : '•••';
    this.ui.orig.textContent = opts.showBpm && it.bpm ? 'ORIG ' + DJ.fmtBpm(it.bpm) : '';
    this.ui.time.textContent = '-' + DJ.fmtTime(Math.max(0, d - p));
    this.ui.elapsed.textContent = DJ.fmtTime(p);
    var bi = this.beatInfo();
    if (bi) {
      for (var i = 0; i < 4; i++) this.ui.beats[i].classList.toggle('on', i === bi.barBeat % 4 && bi.beats >= 0);
      var phrase = Math.floor(bi.bar / 8) + 1, inPhrase = ((bi.bar % 8) + 8) % 8 + 1;
      this.ui.bar.textContent = 'Bar ' + (bi.bar + 1) + ' · Phrase ' + phrase + ' (' + inPhrase + '/8)';
      this.host.style.setProperty('--beat-glow', bi.phase < 0.15 && this.playing ? '1' : '0');
    }
    this.ui.plate.style.transform = 'rotate(' + ((p * 200) % 360).toFixed(1) + 'deg)';
  };
  Deck.prototype.setLoading = function (f) {
    var lb = this.ui.loadbar;
    if (f === null) { lb.hidden = true; return; }
    lb.hidden = false; lb.querySelector('span').style.width = Math.round(f * 100) + '%';
  };
  Deck.prototype.loadItem = function (item) {
    var self = this;
    if (!item || !DJ.playable(item)) { DJ.toast('הקובץ הזה עדיין לא זמין'); return Promise.resolve(); }
    if (DJ.isFile) { DJ.toast('המאמן צריך שרת מקומי: הריצו python -m http.server מתיקיית הריפו.'); return Promise.resolve(); }
    var token = ++this.loadToken;
    if (this.playing) this.pause();
    this.ui.load.value = item.id;
    this.setLoading(0);
    this.ui.title.textContent = 'טוען: ' + (item.title || item.id) + '…';
    return load(item.file, function (f) { if (token === self.loadToken) self.setLoading(f * 0.9); }).then(function (r) {
      if (token !== self.loadToken) return;
      self.stopSrc(); self.playing = false;
      self.item = item; self.buffer = r.buffer; self.env = r.env; self.pos = self.firstBeat(); self.cue = self.pos;
      self.jog = 1; self.bend = 1;
      self.wave.setPeaks(DJ.peaks(item.file) || peaksFromEnv(r.env));
      self.paintCueMark(); self.renderPads(); self.setLoading(null); self.syncUI(); self.frame();
      self.dirty = true;
      updateUrl();
    }).catch(function (e) {
      console.warn(e);
      if (token !== self.loadToken) return;
      self.setLoading(null); self.ui.title.textContent = 'הטעינה נכשלה';
      DJ.toast('לא הצלחנו לטעון את הקובץ. אם אתם עובדים מקומית - הריצו שרת מתיקיית הריפו.');
    });
  };
  function peaksFromEnv(env) {
    var n = 600, out = new Uint8Array(n * 3);
    for (var i = 0; i < n; i++) {
      var a = Math.floor(i * env.n / n), b = Math.max(a + 1, Math.floor((i + 1) * env.n / n)), m = 0, l = 0;
      for (var k = a; k < b; k++) { if (env.amp[k] > m) m = env.amp[k]; if (env.low[k] > l) l = env.low[k]; }
      out[i * 3] = Math.round(l * 255); out[i * 3 + 1] = Math.round(m * 0.75 * 255); out[i * 3 + 2] = Math.round(m * 0.45 * 255);
    }
    return out;
  }

  /* ------------------------------------------------------------------ sync (the "cheat") */
  function syncDeck(d) {
    var other = decks[d.id === 'A' ? 1 : 0];
    if (!d.item || !other.item || !d.item.bpm || !other.item.bpm) { DJ.toast('צריך טראק בשני הדקים'); return; }
    var target = other.effBpm(), pct = (target / d.item.bpm - 1) * 100;
    if (Math.abs(pct) > d.range) {
      if (Math.abs(pct) <= 16) { d.range = 16; d.tempoFader.setRange(-16, 16); d.ui.rangeBtn.textContent = '±16'; d.ui.rangeLab.textContent = '±16%'; }
      else { DJ.toast('הפרש הטמפו גדול מ-16% - נסו טראק קרוב יותר ב-BPM'); return; }
    }
    d.tempoFader.set(pct, true);
    if (d.playing && other.playing) {
      var a = other.beatInfo(), b = d.beatInfo();
      var diff = b.phase - a.phase; if (diff > 0.5) diff -= 1; if (diff < -0.5) diff += 1;
      d.seek(d.position() - diff * d.beatLen());
    }
    DJ.toast('SYNC: הטמפו והביט יושרו. עכשיו נסו לבד - בלי SYNC.');
  }

  /* ------------------------------------------------------------------ mixer UI */
  function dbFmt(v) { return v <= -25.9 ? 'KILL' : (v > 0 ? '+' : '') + v.toFixed(1) + ' dB'; }
  function eqMap(t) { return t >= 0 ? t * 6 : t * 26; } // knob -1..1 -> -26..+6 dB
  function buildMixer(host) {
    host.innerHTML = '<div class="mx-strips"><div class="mx-strip" data-strip="A"></div><div class="mx-master" data-master></div><div class="mx-strip" data-strip="B"></div></div>' +
      '<div class="mx-xf"><span class="xf-lab">A</span><div data-xf class="xf-wrap"></div><span class="xf-lab">B</span></div>' +
      '<div class="mx-curve"><span class="small">Crossfader</span><div class="seg seg--xs" role="group" aria-label="עקומת Crossfader"><button type="button" data-curve="blend" aria-pressed="' + (opts.curve === 'blend') + '">חלק</button><button type="button" data-curve="cut" aria-pressed="' + (opts.curve === 'cut') + '">חד</button></div></div>' +
      '<p class="mx-note" dir="rtl">אין כאן יציאת אוזניות נפרדת - כל מה שתשמעו הוא ה-Master. כדי "להציץ" לטראק לפני שהוא נכנס, הורידו את ה-Channel fader שלו ונסו להקשיב לקיק מתחת לטראק השני.</p>';
    decks.forEach(function (d) {
      var s = host.querySelector('[data-strip="' + d.id + '"]');
      s.innerHTML = '<div class="strip-id">' + d.id + '</div>';
      var mk = function (o) { var k = new DJ.Knob(o); s.appendChild(k.el); return k; };
      d.knobs = {
        trim: mk({ label: 'TRIM', name: 'Trim דק ' + d.id, min: -1, max: 1, def: 0, color: '#c9c8d8', format: function (v) { return (v * 12 > 0 ? '+' : '') + (v * 12).toFixed(1) + ' dB'; }, onInput: function (v) { d.trimDb = v * 12; d.applyMix(); } }),
        high: mk({ label: 'HI', name: 'EQ High דק ' + d.id, min: -1, max: 1, def: 0, color: '#ffffff', format: function (v) { return dbFmt(eqMap(v)); }, onInput: function (v) { d.eq.high = eqMap(v); d.applyMix(); } }),
        mid: mk({ label: 'MID', name: 'EQ Mid דק ' + d.id, min: -1, max: 1, def: 0, color: '#ffa63d', format: function (v) { return dbFmt(eqMap(v)); }, onInput: function (v) { d.eq.mid = eqMap(v); d.applyMix(); } }),
        low: mk({ label: 'LOW', name: 'EQ Low דק ' + d.id, min: -1, max: 1, def: 0, color: '#2f7bff', format: function (v) { return dbFmt(eqMap(v)); }, onInput: function (v) { d.eq.low = eqMap(v); d.applyMix(); } }),
        filter: mk({ label: 'FILTER', name: 'Filter דק ' + d.id + ' (שמאלה LPF, ימינה HPF)', min: -1, max: 1, def: 0, color: '#ff2bd6', format: function (v) { return Math.abs(v) < 0.03 ? 'OFF' : (v < 0 ? 'LPF ' : 'HPF ') + Math.round(Math.abs(v) * 100) + '%'; }, onInput: function (v) { d.filter = v; d.applyMix(); } })
      };
      d.knobs.filter.el.classList.add('knob--filter');
      var row = DJ.h('<div class="strip-fader"><div class="vu" data-vu="' + d.id + '" aria-hidden="true"><i></i><b></b></div></div>');
      d.chFader = new DJ.Fader({ orient: 'v', min: 0, max: 1, step: 0.005, def: 1, value: 1, name: 'Channel fader ' + d.id, cls: 'fader--ch', format: function (v) { return Math.round(v * 100) + '%'; }, onInput: function (v) { d.fader = v; d.applyMix(); } });
      row.appendChild(d.chFader.el);
      s.appendChild(row);
      d.vu = row.querySelector('.vu');
    });
    var m = host.querySelector('[data-master]');
    m.innerHTML = '<div class="strip-id">MASTER</div>';
    var mk2 = new DJ.Knob({ label: 'MASTER', name: 'Master volume', min: 0, max: 1, def: 0.8, value: 0.8, color: '#b6ff3b', format: function (v) { return Math.round(v * 100) + '%'; }, onInput: function (v) { if (masterGain) masterGain.gain.setTargetAtTime(v, ctx.currentTime, 0.01); } });
    m.appendChild(mk2.el);
    m.appendChild(DJ.h('<div class="master-vu" aria-hidden="true"><div class="vu vu--m" data-vu="L"><i></i><b></b></div><div class="vu vu--m" data-vu="R"><i></i><b></b></div><span>L</span><span>R</span></div>'));
    xfFader = new DJ.Fader({ orient: 'h', min: -1, max: 1, step: 0.01, def: 0, value: 0, name: 'Crossfader (שמאלה A, ימינה B)', cls: 'fader--xf', format: function (v) { return v < -0.02 ? 'A ' + Math.round(-v * 100) + '%' : v > 0.02 ? 'B ' + Math.round(v * 100) + '%' : 'מרכז'; }, onInput: function (v) { xf = v; applyXfader(); } });
    host.querySelector('[data-xf]').appendChild(xfFader.el);
    host.querySelectorAll('[data-curve]').forEach(function (b) {
      b.addEventListener('click', function () {
        opts.curve = b.getAttribute('data-curve'); DJ.store.set('mx-curve', opts.curve);
        host.querySelectorAll('[data-curve]').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
        applyXfader();
      });
    });
  }
  function applyXfader() {
    if (!ctx) return;
    var ga, gb, x = xf;
    if (opts.curve === 'cut') { ga = DJ.clamp((1 - x) / 0.1, 0, 1); gb = DJ.clamp((1 + x) / 0.1, 0, 1); }
    else { var t = (x + 1) / 2; ga = Math.cos(t * Math.PI / 2); gb = Math.sin(t * Math.PI / 2); ga = Math.min(1, ga * 1.414); gb = Math.min(1, gb * 1.414); }
    if (decks[0].nodes) decks[0].nodes.xf.gain.setTargetAtTime(ga, ctx.currentTime, 0.01);
    if (decks[1].nodes) decks[1].nodes.xf.gain.setTargetAtTime(gb, ctx.currentTime, 0.01);
  }

  /* ------------------------------------------------------------------ zoom waveforms + phase meter */
  var zoomEls = {}, phaseEl = null, vuBuf = new Float32Array(1024), vuPeaks = {};
  function buildZoom(host) {
    host.innerHTML =
      '<div class="zrow" data-zrow="A"><span class="ztag">A</span><canvas data-zoom="A" aria-hidden="true"></canvas></div>' +
      '<div class="phase" data-phase role="group" aria-label="מד פאזה: כמה הביטים של B רחוקים מהביטים של A">' +
      '<div class="ph-meter"><span class="ph-side">B מאחר</span><div class="ph-track"><span class="ph-zone"></span><span class="ph-tick" style="left:25%"></span><span class="ph-tick" style="left:75%"></span><span class="ph-center"></span><span class="ph-needle" data-needle></span></div><span class="ph-side">B מקדים</span></div>' +
      '<div class="ph-info"><span class="ph-text" data-phtext>הפעילו את שני הדקים כדי לראות את הפאזה</span><span class="ph-tempo" data-phtempo></span><span class="ph-bar" data-phbar></span></div></div>' +
      '<div class="zrow" data-zrow="B"><span class="ztag">B</span><canvas data-zoom="B" aria-hidden="true"></canvas></div>';
    var zslot = DJ.$('[data-zoom-slot]');
    if (zslot) zslot.innerHTML = '<span class="small muted">זום</span><div class="zoom-ctl" dir="ltr"><button type="button" class="mini-btn" data-zoom-btn="out" aria-label="הרחקה (יותר שניות)">−</button><span data-zoom-lab>' + opts.zoom + 's</span><button type="button" class="mini-btn" data-zoom-btn="in" aria-label="קירוב (פחות שניות)">+</button></div>';
    zoomEls.A = host.querySelector('[data-zoom="A"]'); zoomEls.B = host.querySelector('[data-zoom="B"]');
    phaseEl = { root: host.querySelector('[data-phase]'), needle: host.querySelector('[data-needle]'), text: host.querySelector('[data-phtext]'), tempo: host.querySelector('[data-phtempo]'), bar: host.querySelector('[data-phbar]') };
    var Z = [2, 4, 6, 10, 16];
    document.querySelectorAll('[data-zoom-btn]').forEach(function (b) {
      b.addEventListener('click', function () {
        var i = Z.indexOf(opts.zoom); if (i < 0) i = 2;
        i = DJ.clamp(i + (b.getAttribute('data-zoom-btn') === 'in' ? -1 : 1), 0, Z.length - 1);
        opts.zoom = Z[i]; DJ.store.set('mx-zoom', opts.zoom); DJ.$('[data-zoom-lab]').textContent = opts.zoom + 's';
      });
    });
    // click/drag on zoomed waveform = scratch-free nudge (move position)
    ['A', 'B'].forEach(function (id, i) {
      var cv = zoomEls[id], startX = null, startPos = 0;
      cv.addEventListener('pointerdown', function (e) { var d = decks[i]; if (!d.buffer) return; startX = e.clientX; startPos = d.position(); try { cv.setPointerCapture(e.pointerId); } catch (x) { /* */ } });
      cv.addEventListener('pointermove', function (e) { if (startX === null) return; var d = decks[i], w = cv.clientWidth; d.seek(startPos - (e.clientX - startX) / w * opts.zoom); });
      var up = function () { startX = null; };
      cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
    });
  }
  function drawZoom(d, cv, col) {
    var w = cv.clientWidth, h = cv.clientHeight; if (!w || !h) return;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    var g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
    var mid = h / 2;
    if (!d.env) {
      g.fillStyle = 'rgba(255,255,255,.08)'; g.fillRect(0, mid, w, 1);
      g.fillStyle = 'rgba(255,255,255,.35)'; g.font = '12px Heebo, sans-serif'; g.textAlign = 'center'; g.fillText('דק ' + d.id + ' ריק', w / 2, mid - 6);
      return;
    }
    var p = d.position(), span = opts.zoom, t0 = p - span / 2, env = d.env, pxPerSec = w / span;
    // beat grid
    if (d.item && d.item.bpm) {
      var bl = d.beatLen(), fd = d.firstBeat(), bpb = d.item.beats_per_bar || 4;
      var k0 = Math.ceil((t0 - fd) / bl), k1 = Math.floor((t0 + span - fd) / bl);
      for (var k = Math.max(k0, 0); k <= k1; k++) {
        var x = (fd + k * bl - t0) * pxPerSec;
        var down = ((k % bpb) + bpb) % bpb === 0, phrase = ((k % (bpb * 8)) + bpb * 8) % (bpb * 8) === 0;
        g.fillStyle = phrase ? 'rgba(255,43,214,.9)' : down ? 'rgba(255,255,255,.55)' : 'rgba(255,255,255,.18)';
        g.fillRect(Math.round(x), 0, phrase ? 2 : 1, h);
        if (down && pxPerSec * bl * bpb > 60) { g.fillStyle = 'rgba(255,255,255,.55)'; g.font = '10px Rubik, sans-serif'; g.textAlign = 'left'; g.fillText(String(Math.floor(k / bpb) + 1), Math.round(x) + 3, 11); }
      }
    }
    // waveform
    var step = 2;
    for (var px = 0; px < w; px += step) {
      var t = t0 + px / pxPerSec;
      if (t < 0 || t > d.duration()) continue;
      var i0 = Math.floor(t * env.rate), i1 = Math.max(i0 + 1, Math.floor((t + step / pxPerSec) * env.rate)), a = 0, l = 0;
      for (var i = i0; i < i1 && i < env.n; i++) { if (env.amp[i] > a) a = env.amp[i]; if (env.low[i] > l) l = env.low[i]; }
      var ah = a * (mid - 3), lh = l * (mid - 3);
      g.globalAlpha = px < w / 2 ? 0.95 : 0.8;
      g.fillStyle = col.mid; g.fillRect(px, mid - ah, step - 0.5, ah * 2);
      g.fillStyle = col.low; g.fillRect(px, mid - lh, step - 0.5, lh * 2);
    }
    g.globalAlpha = 1;
    // cue points
    ((d.item && d.item.cues) || []).forEach(function (c) {
      var x = (c.sec - t0) * pxPerSec; if (x < -10 || x > w + 10) return;
      g.fillStyle = c.color || DJ.CUE_COLORS[c.slot]; g.fillRect(x - 1, 0, 2, h);
      g.beginPath(); g.moveTo(x - 6, 0); g.lineTo(x + 6, 0); g.lineTo(x, 8); g.closePath(); g.fill();
    });
    var cx = (d.cue - t0) * pxPerSec;
    if (cx > -10 && cx < w + 10) { g.fillStyle = '#ffb020'; g.beginPath(); g.moveTo(cx - 6, h); g.lineTo(cx + 6, h); g.lineTo(cx, h - 8); g.closePath(); g.fill(); }
    // playhead
    g.fillStyle = '#fff'; g.shadowColor = '#fff'; g.shadowBlur = 8; g.fillRect(Math.round(w / 2) - 1, 0, 2, h); g.shadowBlur = 0;
  }
  function paintPhase() {
    var A = decks[0], B = decks[1];
    phaseEl.root.classList.toggle('is-hidden', !opts.showPhase);
    var ok = A.item && B.item && A.item.bpm && B.item.bpm;
    var tempoTxt = '';
    if (ok && opts.showBpm) {
      var diff = (B.effBpm() / A.effBpm() - 1) * 100;
      tempoTxt = Math.abs(diff) < 0.02 ? 'טמפו: זהה ✓' : 'טמפו: B ' + (diff > 0 ? 'מהיר' : 'איטי') + ' ב-' + Math.abs(diff).toFixed(2) + '%';
    } else if (ok) {
      var diff2 = (B.effBpm() / A.effBpm() - 1) * 100;
      tempoTxt = Math.abs(diff2) < 0.05 ? 'הטמפו כמעט זהה' : 'B ' + (diff2 > 0 ? 'בורח קדימה' : 'נגרר אחורה');
    }
    phaseEl.tempo.textContent = tempoTxt;
    if (!ok || !A.playing || !B.playing || !opts.showPhase) {
      phaseEl.needle.style.left = '50%'; phaseEl.root.dataset.state = 'idle';
      phaseEl.text.textContent = !ok ? 'טענו טראק לשני הדקים' : (!A.playing || !B.playing) ? 'הפעילו את שני הדקים כדי לראות את הפאזה' : '';
      phaseEl.bar.textContent = '';
      return;
    }
    var a = A.beatInfo(), b = B.beatInfo();
    var dph = b.phase - a.phase; if (dph > 0.5) dph -= 1; if (dph < -0.5) dph += 1;
    var ms = dph * 60 / A.effBpm() * 1000;
    phaseEl.needle.style.left = (50 + dph * 100).toFixed(2) + '%';
    var am = Math.abs(ms), state = am < 12 ? 'lock' : am < 35 ? 'close' : 'off';
    phaseEl.root.dataset.state = state;
    phaseEl.text.textContent = state === 'lock' ? 'מסונכרן! (' + Math.round(am) + 'ms)' : 'B ' + (ms > 0 ? 'מקדים' : 'מאחר') + ' ב-' + Math.round(am) + 'ms';
    // bar alignment (beat 1 of A vs beat 1 of B)
    var beatOffset = Math.round(b.beats - a.beats - dph);
    var barOff = ((beatOffset % 4) + 4) % 4;
    phaseEl.bar.textContent = state === 'off' ? '' : barOff === 0 ? 'ה-1 של התיבה מיושר ✓' : 'הביטים מיושרים, אבל ה-1 של B זז ב-' + barOff + ' ביטים';
  }
  function paintVu(el, an) {
    if (!el) return;
    var lvl = 0;
    if (an) {
      an.getFloatTimeDomainData(vuBuf);
      var pk = 0; for (var i = 0; i < vuBuf.length; i++) { var v = vuBuf[i] < 0 ? -vuBuf[i] : vuBuf[i]; if (v > pk) pk = v; }
      var db = 20 * Math.log10(pk + 1e-9);
      lvl = DJ.clamp((db + 48) / 48, 0, 1);
    }
    var key = el.getAttribute('data-vu'), hold = vuPeaks[key] || { v: 0, t: 0 }, now = performance.now();
    if (lvl >= hold.v || now - hold.t > 900) { hold = { v: lvl, t: now }; vuPeaks[key] = hold; }
    el.style.setProperty('--lvl', lvl.toFixed(3));
    el.style.setProperty('--hold', hold.v.toFixed(3));
  }

  /* ------------------------------------------------------------------ main loop */
  var colors = { mid: '#ffa63d', low: '#2f7bff' };
  function loop() {
    decks.forEach(function (d) { d.frame(); });
    var vis = !document.hidden;
    if (vis) {
      drawZoom(decks[0], zoomEls.A, colors);
      drawZoom(decks[1], zoomEls.B, colors);
      paintPhase();
      decks.forEach(function (d) { paintVu(d.vu, d.nodes && d.nodes.an); });
      paintVu(DJ.$('[data-vu="L"]'), anL); paintVu(DJ.$('[data-vu="R"]'), anR);
    }
    requestAnimationFrame(loop);
  }

  /* ------------------------------------------------------------------ track select + presets */
  function optionsHTML() {
    var groups = [];
    DJ.FAMILY_ORDER.forEach(function (f) {
      var ts = DJ.catalog.tracks.filter(function (t) { return t.family === f && DJ.playable(t); });
      if (ts.length) groups.push(['טראקים · ' + DJ.FAMILIES[f], ts]);
    });
    var other = DJ.catalog.tracks.filter(function (t) { return DJ.FAMILY_ORDER.indexOf(t.family) < 0 && DJ.playable(t); });
    if (other.length) groups.push(['טראקים', other]);
    var pr = DJ.catalog.practice.filter(DJ.playable); if (pr.length) groups.push(['תרגילים', pr]);
    var tr = DJ.catalog.transitions.filter(DJ.playable); if (tr.length) groups.push(['מעברים לדוגמה', tr]);
    if (!groups.length) return '<option value="">אין עדיין קבצי אודיו (ברינדור)</option>';
    return '<option value="">טענו טראק…</option>' + groups.map(function (g) {
      return '<optgroup label="' + esc(g[0]) + '">' + g[1].map(function (t) {
        var meta = [t.genre || '', opts.showBpm && t.bpm ? DJ.fmtBpm(t.bpm) + ' BPM' : '', DJ.camOf(t) || ''].filter(Boolean).join(' · ');
        return '<option value="' + esc(t.id) + '">' + esc(t.title || t.id) + (meta ? ' — ' + esc(meta) : '') + '</option>';
      }).join('') + '</optgroup>';
    }).join('');
  }
  function refreshSelects() { decks.forEach(function (d) { var v = d.item ? d.item.id : ''; d.ui.load.innerHTML = optionsHTML(); d.ui.load.value = v; }); }
  var PRESETS = [
    ['ביטמאצ\'ינג בסיסי: תופים 124 מול 128', 'practice-03', 'practice-04', { bpm: false }],
    ['טמפו עקום: 125.5 מול 124', 'practice-06', 'practice-03', { bpm: false }],
    ['ספירת פרייזים 124 + תופים', 'practice-01', 'practice-03', {}],
    ['Bass Swap: באס A מול באס B', 'practice-08', 'practice-09', {}],
    ['הרמוני: 8A מול 9A (תואם)', 'practice-10', 'practice-12', {}],
    ['התנגשות: 8A מול 3A (מזייף)', 'practice-10', 'practice-11', {}],
    ['טק האוס: Groove Machine ← Bassline Bandit', 'house-05', 'house-06', {}],
    ['דיפ האוס: בלנד ארוך', 'house-01', 'house-02', {}],
    ['מלודיק טכנו: Energy Boost +2', 'techno-08', 'techno-05', {}],
    ['טכנו: Concrete Pulse ← Industrial Heart', 'techno-01', 'techno-02', {}]
  ];
  function buildPresets() {
    var sel = DJ.$('[data-preset]');
    PRESETS.forEach(function (p, i) {
      var a = DJ.byId.get(p[1]), b = DJ.byId.get(p[2]);
      var ok = DJ.playable(a) && DJ.playable(b);
      sel.appendChild(DJ.h('<option value="' + i + '"' + (ok ? '' : ' disabled') + '>' + esc(p[0]) + (ok ? '' : ' (בקרוב)') + '</option>'));
    });
    sel.addEventListener('change', function () {
      var p = PRESETS[+sel.value]; if (!p) return;
      if (p[3].bpm === false) { var cb = DJ.$('[data-opt-bpm]'); cb.checked = false; cb.dispatchEvent(new Event('change')); }
      decks[0].loadItem(DJ.byId.get(p[1])); decks[1].loadItem(DJ.byId.get(p[2]));
      decks[1].tempoFader.set(0, true);
      sel.value = '';
      DJ.toast('נטען: ' + p[0] + '. התחילו את A, ואז הכניסו את B על ה-1.');
    });
  }
  function updateUrl() {
    try {
      var u = new URL(location.href);
      ['a', 'b'].forEach(function (k, i) { if (decks[i].item) u.searchParams.set(k, decks[i].item.id); });
      history.replaceState(null, '', u);
    } catch (e) { /* ignore */ }
  }

  /* ------------------------------------------------------------------ keyboard */
  var KEYMAP = {
    KeyQ: ['A', 'play'], KeyA: ['A', 'cue'], KeyW: ['A', 'bend-'], KeyE: ['A', 'bend+'], KeyS: ['A', 'tempo-'], KeyD: ['A', 'tempo+'],
    Digit1: ['A', 'hc', 'A'], Digit2: ['A', 'hc', 'B'], Digit3: ['A', 'hc', 'C'], Digit4: ['A', 'hc', 'D'],
    KeyP: ['B', 'play'], Semicolon: ['B', 'cue'], KeyI: ['B', 'bend-'], KeyO: ['B', 'bend+'], KeyK: ['B', 'tempo-'], KeyL: ['B', 'tempo+'],
    Digit7: ['B', 'hc', 'A'], Digit8: ['B', 'hc', 'B'], Digit9: ['B', 'hc', 'C'], Digit0: ['B', 'hc', 'D'],
    KeyZ: ['X', 'left'], KeyX: ['X', 'center'], KeyC: ['X', 'right']
  };
  function keys() {
    document.addEventListener('keydown', function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var t = e.target, tag = t && t.tagName;
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
      var m = KEYMAP[e.code]; if (!m) return;
      if (m[0] === 'X') {
        e.preventDefault();
        var v = m[1] === 'center' ? 0 : xf + (m[1] === 'left' ? -0.1 : 0.1);
        xfFader.set(v, true); return;
      }
      var d = decks[m[0] === 'A' ? 0 : 1];
      e.preventDefault();
      if (m[1] === 'play' && !e.repeat) { ensureCtx(); d.toggle(); }
      else if (m[1] === 'cue' && !e.repeat) d.cueDown();
      else if (m[1] === 'bend-' && !e.repeat) d.setBend(-1);
      else if (m[1] === 'bend+' && !e.repeat) d.setBend(1);
      else if (m[1] === 'tempo-') d.tempoFader.set(d.tempo - 0.05, true);
      else if (m[1] === 'tempo+') d.tempoFader.set(d.tempo + 0.05, true);
      else if (m[1] === 'hc' && !e.repeat) d.hotCue(m[2]);
    });
    document.addEventListener('keyup', function (e) {
      var m = KEYMAP[e.code]; if (!m || m[0] === 'X') return;
      var d = decks[m[0] === 'A' ? 0 : 1];
      if (m[1] === 'cue') d.cueUp();
      if (m[1] === 'bend-' || m[1] === 'bend+') d.setBend(0);
    });
  }
  function helpHTML() {
    var row = function (k, a) { return '<tr><td>' + a + '</td><td>' + k + '</td></tr>'; };
    return '<div class="help-grid"><div><h3>קיצורי מקלדת</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>פעולה</th><th>דק A</th><th>דק B</th></tr></thead><tbody>' +
      '<tr><td>Play / Pause</td><td><kbd>Q</kbd></td><td><kbd>P</kbd></td></tr>' +
      '<tr><td>CUE (החזקה = האזנה מקדימה)</td><td><kbd>A</kbd></td><td><kbd>;</kbd></td></tr>' +
      '<tr><td>Pitch bend האטה / האצה (החזקה)</td><td><kbd>W</kbd> <kbd>E</kbd></td><td><kbd>I</kbd> <kbd>O</kbd></td></tr>' +
      '<tr><td>Tempo −0.05% / +0.05%</td><td><kbd>S</kbd> <kbd>D</kbd></td><td><kbd>K</kbd> <kbd>L</kbd></td></tr>' +
      '<tr><td>Hot Cues A–D</td><td><kbd>1</kbd>–<kbd>4</kbd></td><td><kbd>7</kbd>–<kbd>0</kbd></td></tr>' +
      '<tr><td>Crossfader שמאלה / מרכז / ימינה</td><td colspan="2"><kbd>Z</kbd> <kbd>X</kbd> <kbd>C</kbd></td></tr>' +
      '</tbody></table></div><p class="muted small">הקיצורים עובדים בכל פריסת מקלדת (גם בעברית). על Knob או Fader: חצים לכיוונון, <kbd>Shift</kbd> לכיוונון עדין, <kbd>0</kbd> או דאבל-קליק לאיפוס.</p></div>' +
      '<div><h3>איך עובד מד הפאזה?</h3><p>המאמן יודע בדיוק איפה כל ביט נמצא בכל טראק (BPM + הביט הראשון ב-0.0 שניות). המחוג מראה בכמה מילישניות הקיק של B מקדים או מאחר ביחס ל-A. ירוק = פחות מ-12ms (נשמע כמו קיק אחד), צהוב = קרוב, אדום = "סוסים דוהרים".</p>' +
      '<p>אם המחוג זז כל הזמן לכיוון אחד - הטמפו לא תואם: תקנו עם ה-Tempo fader. אם הוא עומד במקום אבל לא באמצע - הטמפו נכון והפאזה לא: דחפו עם ה-Jog או כפתורי ההאטה/ההאצה.</p>' +
      '<p>בשורה התחתונה תראו גם אם ה-"1" של התיבה מיושר - ככה מכניסים טראק על תחילת פרייז.</p></div></div>';
  }

  /* ------------------------------------------------------------------ init */
  DJ.ready(function () {
    var app = DJ.$('[data-mixer]');
    if (!app) return;
    DJ.noGlobalSpace = true;
    var consoleEl = DJ.$('[data-console]');
    var zoomHost = DJ.h('<div class="zoom-panel" data-zoom-panel></div>');
    consoleEl.insertBefore(zoomHost, consoleEl.firstChild);
    decks = [new Deck('A', DJ.$('[data-deck="A"]')), new Deck('B', DJ.$('[data-deck="B"]'))];
    buildZoom(zoomHost);
    buildMixer(DJ.$('[data-mixer-center]'));
    refreshSelects();
    buildPresets();
    keys();
    DJ.$('[data-help]').innerHTML = helpHTML();
    var ht = DJ.$('[data-help-toggle]');
    ht.addEventListener('click', function () { var hp = DJ.$('[data-help]'); hp.hidden = !hp.hidden; ht.setAttribute('aria-expanded', String(!hp.hidden)); });
    var cbB = DJ.$('[data-opt-bpm]'), cbP = DJ.$('[data-opt-phase]'), cbQ = DJ.$('[data-opt-quantize]');
    cbB.addEventListener('change', function () { opts.showBpm = cbB.checked; refreshSelects(); app.classList.toggle('hide-bpm', !opts.showBpm); });
    cbP.addEventListener('change', function () { opts.showPhase = cbP.checked; });
    cbQ.addEventListener('change', function () { opts.quantize = cbQ.checked; });
    // unlock audio on first interaction anywhere in the console
    consoleEl.addEventListener('pointerdown', function () { ensureCtx(); }, { once: true });
    if (!DJ.all.some(DJ.playable)) {
      app.insertBefore(DJ.h('<div class="callout callout--warn" role="note"><div class="callout-head">' + I('alert') + '<span>עוד אין קבצי אודיו</span></div><div class="callout-body"><p>הטראקים ברינדור ממש עכשיו. ברגע שיתווספו לריפו ויריצו <code>python tools/build_site.py</code> - הם יופיעו כאן.</p></div></div>'), consoleEl);
    }
    if (DJ.isFile) {
      app.insertBefore(DJ.h('<div class="callout callout--warn" role="note"><div class="callout-head">' + I('alert') + '<span>צריך שרת מקומי</span></div><div class="callout-body"><p>הדפדפן לא מאפשר לטעון אודיו מ-<code>file://</code>. מתיקיית הריפו הריצו <code>python -m http.server 8000</code> ופתחו <code>http://localhost:8000/docs/</code>.</p></div></div>'), consoleEl);
    }
    var a = DJ.params.get('a'), b = DJ.params.get('b');
    var fallbackA = DJ.byId.get('practice-03'), fallbackB = DJ.byId.get('practice-04');
    var ia = a ? DJ.byId.get(a) : null, ib = b ? DJ.byId.get(b) : null;
    if (!ia && !ib) {
      var ready = DJ.tracksReady();
      ia = DJ.playable(fallbackA) ? fallbackA : ready[0]; ib = DJ.playable(fallbackB) ? fallbackB : ready[1];
    }
    if (ia && DJ.playable(ia)) decks[0].loadItem(ia);
    if (ib && DJ.playable(ib)) decks[1].loadItem(ib);
    requestAnimationFrame(loop);
    window.DJMixer = { decks: decks, ensureCtx: ensureCtx, get ctx() { return ctx; } };
  });
})();
