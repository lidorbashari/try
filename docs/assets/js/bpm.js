/* DJ Lab — BPM tapper, metronome, pitch calculator and genre BPM ruler. */
(function () {
  'use strict';
  var DJ = window.DJ, esc = DJ.esc, I = DJ.icon;

  function tapper(calcSetFrom) {
    var pad = DJ.$('[data-tap]'); if (!pad) return;
    var taps = [], bpm = 0;
    var out = DJ.$('[data-tap-bpm]'), hint = DJ.$('[data-tap-hint]'), cnt = DJ.$('[data-tap-count]'), stab = DJ.$('[data-tap-stab]'), alt = DJ.$('[data-tap-alt]');
    function reset() { taps = []; bpm = 0; out.textContent = '--'; cnt.textContent = '0'; stab.textContent = '--'; alt.textContent = '--'; hint.textContent = 'הקישו כאן או על מקש הרווח'; pad.classList.remove('is-stable'); }
    function tap() {
      var now = performance.now();
      if (taps.length && now - taps[taps.length - 1] > 2500) taps = [];
      taps.push(now); if (taps.length > 24) taps.shift();
      cnt.textContent = String(taps.length);
      pad.classList.remove('is-hit'); void pad.offsetWidth; pad.classList.add('is-hit');
      if (taps.length < 2) { hint.textContent = 'עוד...'; return; }
      var iv = []; for (var i = 1; i < taps.length; i++) iv.push(taps[i] - taps[i - 1]);
      var recent = iv.slice(-16), avg = recent.reduce(function (a, b) { return a + b; }, 0) / recent.length;
      var sd = Math.sqrt(recent.reduce(function (a, b) { return a + (b - avg) * (b - avg); }, 0) / recent.length);
      bpm = 60000 / avg;
      out.textContent = bpm.toFixed(taps.length >= 8 ? 1 : 0);
      var cv = sd / avg;
      stab.textContent = taps.length < 6 ? '...' : cv < 0.03 ? 'יציב' : cv < 0.07 ? 'בסדר' : 'לא יציב';
      pad.classList.toggle('is-stable', taps.length >= 8 && cv < 0.03);
      alt.textContent = (bpm / 2).toFixed(1) + ' / ' + (bpm * 2).toFixed(1);
      hint.textContent = taps.length < 8 ? 'המשיכו להקיש…' : 'מצוין! הקישו עוד כדי לדייק';
    }
    pad.addEventListener('pointerdown', function (e) { e.preventDefault(); tap(); });
    pad.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); tap(); } });
    document.addEventListener('keydown', function (e) {
      var tag = e.target && e.target.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if ((e.code === 'Space' || e.code === 'KeyT') && !e.repeat) { e.preventDefault(); tap(); }
    });
    DJ.$('[data-tap-reset]').addEventListener('click', reset);
    DJ.$('[data-tap-use]').addEventListener('click', function () { if (bpm) calcSetFrom(Math.round(bpm * 10) / 10); else DJ.toast('הקישו קודם כמה פעמים'); });
    DJ.noGlobalSpace = true;
    // metronome
    var ctx = null, timer = null, nextT = 0, beat = 0;
    var tog = DJ.$('[data-metro-toggle]'), lab = DJ.$('[data-metro-label]');
    function click(t, acc) {
      var o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = acc ? 1760 : 1100; g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(acc ? 0.5 : 0.3, t + 0.002); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.06);
      o.connect(g); g.connect(ctx.destination); o.start(t); o.stop(t + 0.08);
    }
    function sched() {
      var b = bpm || 124, spb = 60 / b;
      while (nextT < ctx.currentTime + 0.12) { click(nextT, beat % 4 === 0); nextT += spb; beat++; }
      lab.textContent = 'מנגן ב-' + b.toFixed(1) + ' BPM';
    }
    tog.addEventListener('change', function () {
      if (tog.checked) {
        var AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
        ctx = ctx || new AC(); if (ctx.state === 'suspended') ctx.resume();
        nextT = ctx.currentTime + 0.05; beat = 0; timer = setInterval(sched, 25); sched();
      } else { clearInterval(timer); timer = null; lab.textContent = 'ינגן קליק ב-BPM שנמדד (או 124)'; }
    });
  }

  function calc() {
    var box = DJ.$('[data-pitch-calc]'); if (!box) return function () { };
    var from = DJ.$('[data-calc-from]'), to = DJ.$('[data-calc-to]'), res = DJ.$('[data-calc-result]'), ranges = DJ.$('[data-calc-ranges]'), notes = DJ.$('[data-calc-notes]');
    function run() {
      var a = parseFloat(from.value), b = parseFloat(to.value);
      if (!(a > 0) || !(b > 0)) { res.innerHTML = '<p class="muted">הכניסו שני ערכי BPM</p>'; ranges.innerHTML = ''; notes.innerHTML = ''; return; }
      var pct = (b / a - 1) * 100, semis = 12 * Math.log2(b / a);
      res.innerHTML = '<div class="calc-big ' + (pct >= 0 ? 'up' : 'down') + '" dir="ltr">' + DJ.fmtPct(pct, 2) + '</div><p class="muted">כדי שטראק של <b dir="ltr">' + DJ.fmtBpm(a) + '</b> ינגן ב-<b dir="ltr">' + DJ.fmtBpm(b) + '</b> BPM, הזיזו את ה-Tempo fader ' + (pct >= 0 ? 'למטה (מהר יותר)' : 'למעלה (לאט יותר)') + ' ב-' + Math.abs(pct).toFixed(2) + '%.</p>';
      ranges.innerHTML = [6, 8, 10, 16, 50].map(function (r) {
        var fit = Math.abs(pct) <= r, pos = DJ.clamp(pct / r, -1, 1);
        return '<div class="rf' + (fit ? ' is-fit' : '') + '"><span class="rf-name">±' + (r === 50 ? '50 (WIDE)' : r) + '%</span><span class="rf-bar" dir="ltr"><i class="rf-center"></i><i class="rf-dot" style="left:' + (50 + pos * 50) + '%"></i></span><span class="rf-ok">' + (fit ? I('check') + 'נכנס' : 'לא נכנס') + '</span></div>';
      }).join('');
      var tips = [];
      var ratio = b / a;
      if (Math.abs(ratio - 2) / 2 < 0.08) tips.push('היעד הוא כמעט <b>פי 2</b> (Double-time): אפשר לערבב "על חצי" - כל קיק של הטראק האיטי נופל על כל קיק שני של המהיר. הפרש אמיתי: ' + DJ.fmtPct((b / (a * 2) - 1) * 100, 2) + '.');
      if (Math.abs(ratio - 0.5) / 0.5 < 0.08) tips.push('היעד הוא כמעט <b>חצי</b> (Half-time): למשל דאבסטפ 140 מול היפ-הופ 70. הפרש אמיתי: ' + DJ.fmtPct((b * 2 / a - 1) * 100, 2) + '.');
      if (Math.abs(pct) > 16 && !tips.length) tips.push('הפרש גדול מ-16% ישמע לא טבעי. עדיף מעבר "קאט" על דרופ, Echo Out, או לעלות בהדרגה דרך טראק ביניים.');
      if (Math.abs(semis) >= 0.3) {
        var st = Math.round(semis), camShift = ((st * 7) % 12 + 12) % 12;
        tips.push('בלי <b>Master Tempo</b> הצליל ישתנה ב-' + semis.toFixed(2) + ' חצאי טון' + (st ? ' (≈ ' + (camShift ? (camShift > 6 ? '−' + (12 - camShift) : '+' + camShift) + ' צעדים בגלגל קאמלוט' : 'אותו מספר בגלגל') + ')' : '') + '. עם Master Tempo (ב-Rekordbox: כפתור MT) הסולם נשאר אותו דבר.');
      } else tips.push('השינוי קטן מספיק - גם בלי Master Tempo האוזן כמעט לא תשמע שינוי בסולם.');
      notes.innerHTML = tips.map(function (t) { return '<p>' + t + '</p>'; }).join('');
    }
    from.addEventListener('input', run); to.addEventListener('input', run);
    run();
    return function (v) { from.value = v; run(); from.focus(); };
  }

  function ruler() {
    var host = DJ.$('[data-bpm-ruler]'); if (!host) return;
    var src = DJ.catalog.tracks.length ? DJ.catalog.tracks : (DJ.catalog.plan.tracks || []);
    var g = {}, order = [];
    src.forEach(function (t) { if (!t.genre || !t.bpm) return; if (!g[t.genre]) { g[t.genre] = { min: t.bpm, max: t.bpm, fam: t.family }; order.push(t.genre); } g[t.genre].min = Math.min(g[t.genre].min, t.bpm); g[t.genre].max = Math.max(g[t.genre].max, t.bpm); });
    order.sort(function (a, b) { return g[a].min - g[b].min; });
    var lo = 80, hi = 180, pct = function (v) { return (DJ.clamp(v, lo, hi) - lo) / (hi - lo) * 100; };
    var ticks = ''; for (var v = lo; v <= hi; v += 10) ticks += '<span style="left:' + pct(v) + '%">' + v + '</span>';
    host.innerHTML = '<div class="br-axis" dir="ltr">' + ticks + '</div>' + order.map(function (name) {
      var x = g[name], l = pct(x.min - 1), r = pct(x.max + 1);
      return '<div class="br-row" data-family="' + esc(x.fam) + '"><span class="br-name">' + esc(name) + '</span><span class="br-track" dir="ltr"><i style="left:' + l + '%;width:' + Math.max(1.4, r - l) + '%"></i><em style="left:' + r + '%">' + DJ.fmtBpm(x.min) + (x.max !== x.min ? '–' + DJ.fmtBpm(x.max) : '') + '</em></span></div>';
    }).join('');
  }

  DJ.ready(function () { var set = calc(); tapper(set); ruler(); });
})();
