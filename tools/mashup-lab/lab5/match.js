/* MashMatch: hears a pair the way the song analysis heard each preview (listen.json + analysis.json + beats.json).
   For a vocal track V over a beat track B it chooses which bars of V to sing over which bars of B and how far to move
   the vocal (−2…+2 semitones, plus a tuning correction in cents), so the sung notes sit on B's chords
   (AutoMashUpper-style bar-aligned pitch-class match, normalised by how well V's vocal sits on its own song), with B's
   own vocal out of the way, the tempo close and the grooves alike. Pure functions; the app ranks pairs by `score` and
   hands the engine the plan (entry points, key shift, whether B needs its vocal cleaned out).
   Data needed per track: analysis.json (t0, voc, key, tc, vp, rp, hc, vc, vdb, vs, sec), listen.json (vb, hb, vr per
   bar / beat) and the beat grid (beats.json), all measured on the same preview (hash h of its URL). */
(function (root) {
  "use strict";
  var AN = {}, LI = {}, BT = {}, PV = {}, HASH = null, TR = new Map(), CACHE = new Map();
  var NOTE_HE = ["דו", "דו#", "רה", "רה#", "מי", "פה", "פה#", "סול", "סול#", "לה", "לה#", "סי"];

  function seed(o) {
    o = o || {};
    if (o.an) AN = o.an; if (o.li) LI = o.li; if (o.beats) BT = o.beats; if (o.previews) PV = o.previews; if (o.hash) HASH = o.hash;
    TR.clear(); CACHE.clear();
    return ready();
  }
  function ready() { for (var k in LI) return true; return false; }
  function keyOf(t) { return String(t.t) + " | " + String(t.a); }
  function unit(v) { var s = 0, i; for (i = 0; i < 12; i++) s += v[i] * v[i]; s = Math.sqrt(s); if (!(s > 0)) return null; var o = new Float32Array(12); for (i = 0; i < 12; i++) o[i] = v[i] / s; return o; }
  function bars(hex) {
    var n = Math.floor((hex || "").length / 12), out = [];
    for (var b = 0; b < n; b++) { var v = new Float32Array(12), any = 0; for (var i = 0; i < 12; i++) { v[i] = parseInt(hex.charAt(12 * b + i), 16) || 0; any += v[i]; } out.push(any ? unit(v) : null); }
    return out;
  }
  function digs(s) { var o = []; s = s || ""; for (var i = 0; i < s.length; i++) o.push(+s.charAt(i) || 0); return o; }
  function pc(s) { if (!s || s.length !== 12) return null; var v = new Float32Array(12); for (var i = 0; i < 12; i++) v[i] = +s.charAt(i) || 0; return unit(v); }
  function barLevels(d, nb) { var o = []; for (var b = 0; b < nb; b++) { var s = 0, n = 0; for (var k = 0; k < 4; k++) { var x = d[4 * b + k]; if (x != null) { s += x; n++; } } o.push(n ? s / n : 0); } return o; }

  /* one track as measured on its current preview, or null */
  function track(t) {
    if (!t) return null;
    var k = keyOf(t); if (TR.has(k)) return TR.get(k);
    var a = AN[k], l = LI[k], g = BT[k], p = PV[k], r = null;
    var u = p && p.p, h = u && HASH ? HASH(u) : null;
    var same = function (x) { return !h || !x || x === h; };
    if (a && !a.err && l && l.hb && g && g[3] >= .5 && a.t0 != null && same(a.h) && same(l.h) && (!h || g[4] === h)) {
      var hb = bars(l.hb), vb = bars(l.vb || ""), nb = Math.min(hb.length, vb.length || hb.length);
      var vr = digs(l.vr), voc = digs(a.voc);
      r = { k: k, bpm: g[0], p: 60 / g[0], t0: a.t0, nb: nb, hb: hb, vb: vb, vr: vr, voc: voc, vlev: barLevels(vr, nb), act: barLevels(voc, nb),
        key: a.ks >= .45 ? a.key : null, tc: a.tc || 0, vp: a.vp || null, rp: a.rp ? digs(a.rp) : null, hc: pc(a.hc), vc: pc(a.vc),
        vdb: a.vdb, vs: a.vs, sec: a.sec || [0], lufs: a.lufs };
    }
    TR.set(k, r);
    return r;
  }
  function cosRot(v, w, s) {                  /* cosine of v transposed up by s semitones against w (both unit) */
    var c = 0; for (var i = 0; i < 12; i++) c += v[i] * w[(i + s + 120) % 12]; return c;
  }
  function cos(a, b) { if (!a || !b || a.length !== b.length) return null; var s = 0, x = 0, y = 0; for (var i = 0; i < a.length; i++) { s += a[i] * b[i]; x += a[i] * a[i]; y += b[i] * b[i]; } return x && y ? s / Math.sqrt(x * y) : null; }

  /* where V's singing can start: the bar a phrase begins (with its pickup), the densest 8 bars */
  function vocalStarts(V) {
    var out = [], L = V.vlev, n = V.nb;
    for (var b = 0; b < n - 2; b++) {
      var sing = 0; for (var k = b; k < Math.min(n, b + 4); k++) if (L[k] >= 3.5) sing++;
      if (L[b] >= 3.5 && sing >= 3 && (b === 0 || L[b - 1] < 3)) out.push(b > 0 && V.vr[4 * b - 1] >= 4 ? b - 1 : b);   /* a pickup: from the bar before */
    }
    var best = -1, bs = -1;
    for (b = 0; b + 4 <= n; b++) { var s = 0; for (k = b; k < Math.min(n, b + 8); k++) s += L[k]; if (s > bs) { bs = s; best = b; } }
    if (best >= 0 && out.indexOf(best) < 0) out.push(best);
    return out.slice(0, 3);
  }
  /* where B's bars can start under the vocal: any bar line (a preview starts anywhere in the song, so its bar numbers
     say nothing about phrases); section starts get a small bonus below */
  function beatStarts(B, need) {
    var out = []; for (var b = 0; b + Math.min(need, 4) <= B.nb; b++) out.push(b);
    return out;
  }
  function camN(k) { var m = /^(1[0-2]|[1-9])([AB])$/.exec(String(k || "")); return m ? { n: +m[1], l: m[2] } : null; }

  /* the full measured match of vocal track v over beat track b; null when either preview is not measured */
  function pair(v, b, o) {
    o = o || {};
    var V = track(v), B = track(b); if (!V || !B) return null;
    var ck = V.k + " >> " + B.k + " | " + (o.maxDiff || 0.06);
    if (CACHE.has(ck)) return CACHE.get(ck);
    var res = compute(V, B, o);
    CACHE.set(ck, res);
    return res;
  }
  function compute(V, B, o) {
    var maxD = o.maxDiff == null ? .06 : o.maxDiff;
    var q = [.5, 1, 2].reduce(function (x, y) { return Math.abs(V.bpm - B.bpm * y) < Math.abs(V.bpm - B.bpm * x) ? y : x; }, 1);
    var r = B.bpm * q / V.bpm, d = Math.abs(r - 1);
    if (d > Math.max(.1, maxD) + 1e-9) return { ok: false, why: "tempo", d: d };
    /* key shift candidates from the whole-preview profiles, then bar by bar */
    var shifts = [0];
    if (V.vc && B.hc) {
      var g = [-2, -1, 0, 1, 2].map(function (s) { return [s, cosRot(V.vc, B.hc, s)]; }).sort(function (x, y) { return y[1] - x[1]; });
      g.slice(0, 2).forEach(function (x) { if (shifts.indexOf(x[0]) < 0 && x[1] >= g[0][1] - .1) shifts.push(x[0]); });
    }
    var hcB = B.hc, sm = function (w) { if (!w) return hcB; if (!hcB) return w; var x = new Float32Array(12); for (var i = 0; i < 12; i++) x[i] = .78 * w[i] + .22 * hcB[i]; return unit(x); };
    var HB = B.hb.map(sm);
    var starts = vocalStarts(V); if (!starts.length) return { ok: false, why: "vocal" };
    var W = 8, best = null;
    for (var ai = 0; ai < starts.length; ai++) {
      var a = starts[ai], w = Math.min(W, V.nb - a); if (w < 3) continue;
      var bS = beatStarts(B, Math.ceil(w / q));
      /* how well this vocal sits on its own song (the reference for "fits") */
      var own = 0, ow = 0;
      for (var i = 0; i < w; i++) { var vi = V.vb[a + i], wi = V.vlev[a + i] >= 3 ? V.vlev[a + i] : 0, hi = V.hb[a + i]; if (vi && wi && hi) { own += wi * cosRot(vi, hi, 0); ow += wi; } }
      var Hown = ow ? own / ow : .7;
      for (var si = 0; si < shifts.length; si++) {
        var s = shifts[si];
        for (var bi = 0; bi < bS.length; bi++) {
          var b0 = bS[bi], hs = 0, hw = 0, clash = 0, bv = 0, bn = 0;
          for (i = 0; i < w; i++) {
            var j = q === 2 ? b0 + Math.floor(i / 2) : q === .5 ? b0 + 2 * i : b0 + i; if (j >= B.nb) break;
            var hb = q === .5 && j + 1 < B.nb && HB[j] && HB[j + 1] ? unit(HB[j].map(function (x, k) { return x + HB[j + 1][k]; })) : HB[j];
            var vb = V.vb[a + i], wl = V.vlev[a + i] >= 3 ? V.vlev[a + i] : 0;
            bv += B.vlev[j]; bn++;
            if (!vb || !wl || !hb) continue;
            hs += wl * cosRot(vb, hb, s); hw += wl;
            if (B.vlev[j] >= 5) clash += wl;
          }
          if (!hw) continue;
          var H = hs / hw, Hn = Math.min(1.1, H / Math.max(.3, Hown)), O = clash / hw;
          var phrase = (B.sec || []).indexOf(b0) >= 0 ? 2 : 0;
          var penS = [0, 4, 10][Math.abs(s)] + (s > 0 && V.vp >= 65 ? 5 : 0) + (s < 0 && V.vp && V.vp <= 50 ? 5 : 0);
          var sc = 100 - 70 * Math.max(0, .97 - Hn) - penS - 22 * O + phrase;
          if (!best || sc > best.sc) best = { sc: sc, a: a, b: b0, s: s, w: w, H: H, Hn: Hn, Hown: Hown, O: O, bvoc: bn ? bv / bn : 0 };
        }
      }
    }
    if (!best) return { ok: false, why: "bars" };
    var R = V.rp && B.rp ? cos(V.rp, B.rp) : null;
    var penT = 500 * d, penQ = (V.vdb < -12 ? 6 : V.vdb < -9 ? 3 : 0) + (V.vs < .15 ? 6 : 0), bonR = R == null ? 0 : Math.max(-5, Math.min(3, 8 * (R - .6)));
    var score = Math.max(0, Math.min(100, Math.round(best.sc - penT - penQ + bonR)));
    var cents = Math.round((B.tc || 0) - (V.tc || 0)); if (Math.abs(cents) < 15) cents = 0;
    var semis = best.s + cents / 100;
    var lead = Math.min(2, best.b);                                  /* B plays up to 2 bars before the vocal comes in */
    var plan = { v: V.k, b: B.k, semis: Math.round(semis * 100) / 100, aAt: V.t0 + 4 * best.a * V.p, bAt: B.t0 + 4 * best.b * B.p, leadBars: lead, lead: lead * 4 * B.p,
      cleanB: best.bvoc >= 2.5, q: q, r: Math.round(r * 1e4) / 1e4 };
    return { ok: true, score: score, plan: plan, s: best.s, cents: cents, H: best.H, Hn: best.Hn, Hown: best.Hown, O: best.O, R: R, d: d, q: q,
      aBar: best.a, bBar: best.b, bars: best.w, keyV: V.key, keyB: B.key, why: whyOf(V, B, best, cents, d, R) };
  }
  function whyOf(V, B, x, cents, d, R) {
    var w = [];
    var fit = Math.round(Math.min(1, x.Hn) * 100);
    w.push(fit >= 92 ? "השירה יושבת על האקורדים של הביט כמו על השיר שלה" : fit >= 80 ? "התווים של השירה מתאימים לאקורדים של הביט (" + fit + "%)" : "יש מעט תווים שמתחככים באקורדים (" + fit + "%)");
    if (x.s) w.push("השירה מוזזת " + (x.s > 0 ? "למעלה" : "למטה") + " " + (Math.abs(x.s) === 1 ? "חצי טון" : "טון") + " כדי לשבת בסולם");
    if (cents) w.push("וגם מכוונת " + Math.abs(cents) + " סנט, כי הביט מכוון " + (cents > 0 ? "גבוה" : "נמוך") + " יותר");
    w.push(x.bvoc < 2.5 ? "בקטע הזה של הביט כמעט אין שירה, אז הוא מתנגן מלא" : x.O > .3 ? "גם בביט שרים בקטע הזה, ולכן הניקוי מוריד את השירה שלו" : "השירה של הביט מנוקה מתחת לשירה");
    if (d >= .03) w.push("השירה נמתחת " + Math.round(d * 1000) / 10 + "% לקצב של הביט");
    if (R != null && R >= .8) w.push("הגרוב של שני השירים דומה");
    return w;
  }
  function noteName(semis) { return NOTE_HE[((semis % 12) + 12) % 12]; }
  root.MashMatch = { seed: seed, ready: ready, track: track, pair: pair, _keyOf: keyOf, _bars: bars, _cosRot: cosRot, _note: noteName };
})(typeof window !== "undefined" ? window : globalThis);
