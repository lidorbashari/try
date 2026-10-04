/* DJ Lab — home page: featured tracks, animated hero waveform, learning-path progress. */
(function () {
  'use strict';
  var DJ = window.DJ;

  function pickFeatured() {
    var ready = DJ.tracksReady();
    var src = ready.length ? ready : (DJ.catalog.plan.tracks || []).map(function (p) { return DJ.byId.get(p.id) || Object.assign({ has_audio: false }, p); });
    var out = [], used = new Set(), byFam = {};
    src.forEach(function (t) { (byFam[t.family] = byFam[t.family] || []).push(t); });
    // round-robin across families, preferring peak / high-energy tracks first
    Object.keys(byFam).forEach(function (f) { byFam[f].sort(function (a, b) { return (b.energy || 0) - (a.energy || 0); }); });
    var fams = DJ.FAMILY_ORDER.filter(function (f) { return byFam[f]; });
    var i = 0;
    while (out.length < 8 && fams.some(function (f) { return byFam[f].length; })) {
      var f = fams[i % fams.length]; i++;
      var list = byFam[f];
      if (!list.length) continue;
      var pickIdx = (i < fams.length + 1) ? 0 : Math.floor(list.length / 2);
      var t = list.splice(Math.min(pickIdx, list.length - 1), 1)[0];
      if (!used.has(t.genre) || out.length >= fams.length * 1.5) { out.push(t); used.add(t.genre); }
    }
    out = out.slice(0, 8);
    if (ready.length && out.length < 8) {
      // fill with planned tracks that are still rendering, one per genre
      var seen = new Set(out.map(function (t) { return t.genre; }));
      (DJ.catalog.plan.tracks || []).forEach(function (p) {
        if (out.length >= 8 || DJ.byId.has(p.id) || seen.has(p.genre)) return;
        seen.add(p.genre); out.push(Object.assign({ has_audio: false }, p));
      });
    }
    return out;
  }

  function heroWave() {
    var cv = DJ.$('[data-hero-wave]');
    if (!cv) return;
    var feat = DJ.tracksReady().filter(function (t) { return DJ.peaks(t.file); })[0];
    var peaks = feat ? DJ.peaks(feat.file) : null;
    var n = peaks ? peaks.length / 3 : 600;
    var bpmEl = DJ.$('[data-hero-bpm]'), timeEl = DJ.$('[data-hero-time]');
    if (feat && bpmEl) bpmEl.textContent = DJ.fmtBpm(feat.bpm, 2);
    var camEl = DJ.$('.hero-readout .cam-badge');
    if (feat && camEl) { var c = DJ.camOf(feat); camEl.textContent = c; camEl.style.setProperty('--cam', DJ.cam.color(c)); }
    var dur = feat ? feat.duration_sec : 240;
    var ctx = cv.getContext('2d');
    var cols = ['#2f7bff', '#ffa63d', '#ffffff'];
    function synth(i, b) { var x = i / n; var env = x < 0.12 ? 0.35 : x > 0.88 ? 0.35 : (x > 0.45 && x < 0.55 ? 0.25 : 0.9); var beat = (i % 4 === 0) ? 1 : 0.55; return Math.min(1, env * beat * [1, 0.7, 0.45][b] * (0.75 + 0.25 * Math.sin(i * 1.7 + b))); }
    var t0 = performance.now(), startPos = 0.22;
    function draw(now) {
      var w = cv.clientWidth, h = cv.clientHeight; if (!w || !h) { requestAnimationFrame(draw); return; }
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
      var elapsed = DJ.reducedMotion ? 0 : (now - t0) / 1000;
      var pos = (startPos + elapsed / dur) % 1;
      var visible = 90; // points across the view (zoomed)
      var center = pos * n, step = w / visible;
      for (var b = 0; b < 3; b++) {
        ctx.fillStyle = cols[b];
        for (var k = -visible / 2; k <= visible / 2; k++) {
          var idx = Math.floor(center + k * 0.5);
          if (idx < 0 || idx >= n) continue;
          var v = peaks ? peaks[idx * 3 + b] / 255 : synth(idx, b);
          var hh = v * (h / 2 - 2);
          var x = w / 2 + k * step - (center * 2 % 1) * step;
          ctx.globalAlpha = x < w / 2 ? 1 : 0.55;
          ctx.fillRect(x, h / 2 - hh, step * 0.7, hh * 2);
        }
      }
      ctx.globalAlpha = 1;
      if (timeEl) { var s = pos * dur; timeEl.textContent = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(Math.floor(s % 60)).padStart(2, '0'); }
      if (!DJ.reducedMotion) requestAnimationFrame(draw);
    }
    requestAnimationFrame(draw);
  }

  DJ.ready(function () {
    var host = DJ.$('[data-featured]');
    if (host) {
      var list = pickFeatured();
      var q = function () { return list.filter(DJ.playable); };
      if (!list.length) host.innerHTML = '<div class="empty card" style="grid-column:1/-1"><h2>המוזיקה ברינדור</h2><p>הטראקים יופיעו כאן ממש בקרוב.</p></div>';
      list.forEach(function (t) { var c = DJ.trackCard(t, { queue: q }); c._sync(); host.appendChild(c); });
    }
    var read = DJ.store.get('guide-read', []) || [];
    DJ.$$('.path-step[data-chapter]').forEach(function (li) { if (read.indexOf(li.getAttribute('data-chapter')) >= 0) li.classList.add('is-read'); });
    heroWave();
  });
})();
