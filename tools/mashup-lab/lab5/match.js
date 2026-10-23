/* MashMatch: hears a pair the way the song analysis heard each preview (listen.json + analysis.json + beats.json).
   For a vocal track V over a beat track B it chooses which bars of V to sing over which bars of B and how far to move
   the vocal (−2…+2 semitones, plus a tuning correction in cents), so the sung notes sit on B's chords
   (v2.1, calibrated on the 1,129 measured previews: Pearson correlation of pitch-class profiles, i.e. mean-centred, which
   separates a vocal's own song from a random song with AUC 0.83 where raw cosine reached 0.72. The key fit is measured
   on the whole previews (one decision per shift, so trying many bar offsets can't inflate it); the bar-by-bar fit only
   places the vocal on the right chords. Rap and other barely-pitched vocals depend less on harmony.), with B's own
   vocal out of the way, the tempo close and the grooves alike. Pure functions; the app ranks pairs by `score` and
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
      r = { k: k, u: u || null, bpm: g[0], p: 60 / g[0], t0: a.t0, nb: nb, hb: hb, vb: vb, vr: vr, voc: voc, vlev: barLevels(vr, nb), act: barLevels(voc, nb),
        key: a.ks >= .45 ? a.key : null, tc: a.tc || 0, vp: a.vp || null, rp: a.rp ? digs(a.rp) : null, hc: pc(a.hc), vc: pc(a.vc),
        vdb: a.vdb, vs: a.vs, sec: a.sec || [0], lufs: a.lufs };
      /* whole-preview profiles: the notes sung (weighted by how loud the singing is) and the harmony under them */
      var VP = new Float32Array(12), HP = new Float32Array(12), b, i;
      for (b = 0; b < nb; b++) {
        if (vb[b] && r.vlev[b] >= 3) for (i = 0; i < 12; i++) VP[i] += r.vlev[b] * vb[b][i];
        if (hb[b]) for (i = 0; i < 12; i++) HP[i] += hb[b][i];
      }
      r.VPc = cu(VP); r.HPc = cu(HP);
      var hpu = unit(HP);
      r.vbc = vb.map(function (x) { return x ? cu(x) : null; });
      r.hbc = hb.map(function (x) { if (!x) return hpu ? cu(hpu) : null; if (!hpu) return cu(x); var y = new Float32Array(12); for (var j = 0; j < 12; j++) y[j] = .75 * x[j] + .25 * hpu[j]; return cu(y); });
      r.Fown = r.VPc && r.HPc ? cosRot(r.VPc, r.HPc, 0) : 0;      /* how tonal the vocal is: its fit on its own song */
    }
    TR.set(k, r);
    return r;
  }
  function cosRot(v, w, s) {                  /* cosine of v transposed up by s semitones against w (both unit) */
    var c = 0; for (var i = 0; i < 12; i++) c += v[i] * w[(i + s + 120) % 12]; return c;
  }
  function cu(v) {                             /* mean-centred unit vector (Pearson correlation = dot of two of these) */
    if (!v) return null; var m = 0, i; for (i = 0; i < 12; i++) m += v[i]; m /= 12;
    var o = new Float32Array(12), s = 0; for (i = 0; i < 12; i++) { o[i] = v[i] - m; s += o[i] * o[i]; }
    s = Math.sqrt(s); if (!(s > 1e-6)) return null; for (i = 0; i < 12; i++) o[i] /= s; return o;
  }
  function clamp(x, a, b) { return x < a ? a : x > b ? b : x; }
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
  /* o.maxDiff: tempo reach (anything up to 10 % gives the same answer, so it shares one cache entry);
     o.min: the caller only needs pairs scoring at least this much. When even the best case (perfect bars, no clash)
     stays below it, the bar-by-bar search is skipped and a "lite" answer (ok, score = that upper bound, no plan) is
     returned: lists and presets stay fast on a phone. Callers without o.min always get the full plan. */
  function pair(v, b, o) {
    o = o || {};
    var V = track(v), B = track(b); if (!V || !B) return null;
    var md = Math.max(.1, +o.maxDiff || 0), ck = V.k + " >> " + B.k + " | " + md.toFixed(3), c = CACHE.get(ck);
    if (c && (!c.lite || (o.min != null && c.score < o.min))) return c;
    var res = compute(V, B, { maxDiff: md, min: o.min });
    CACHE.set(ck, res);
    return res;
  }
  function compute(V, B, o) {
    var maxD = o.maxDiff == null ? .06 : o.maxDiff;
    var q = [.5, 1, 2].reduce(function (x, y) { return Math.abs(V.bpm - B.bpm * y) < Math.abs(V.bpm - B.bpm * x) ? y : x; }, 1);
    var r = B.bpm * q / V.bpm, d = Math.abs(r - 1);
    if (d > Math.max(.1, maxD) + 1e-9) return { ok: false, why: "tempo", d: d };
    if (V.u && B.u && V.u === B.u) return { ok: false, why: "same" };   /* two catalog entries found on one preview */
    /* the key fit, on the whole previews: Pearson correlation of V's sung notes (moved by s semitones) with B's harmony */
    var p = clamp((V.Fown + .05) / .45, .25, 1);                  /* rap / spoken vocals: harmony matters less */
    var fk = {}, cand = [];
    [-2, -1, 0, 1, 2].forEach(function (s) {
      var f = V.VPc && B.HPc ? cosRot(V.VPc, B.HPc, s) : 0;
      var pen = [0, .03, .08][Math.abs(s)] + (s > 0 && V.vp >= 65 ? .04 : 0) + (s < 0 && V.vp && V.vp <= 50 ? .04 : 0);
      fk[s] = f; cand.push([s, f - pen]);
    });
    cand.sort(function (x, y) { return y[1] - x[1]; });
    var shifts = [cand[0][0]]; if (cand[1][1] >= cand[0][1] - .05) shifts.push(cand[1][0]);
    var R0 = V.rp && B.rp ? cos(V.rp, B.rp) : null;
    var penT0 = d <= .02 ? 150 * d : 3 + 400 * (d - .02), penQ0 = (V.vdb < -12 ? 6 : V.vdb < -9 ? 3 : 0) + (V.vs < .15 ? 6 : 0);
    if (o.min != null) {                                     /* the best this pair can reach: perfect bars, no clash */
      var ub = -1e9;
      shifts.forEach(function (s) { ub = Math.max(ub, 100 - 55 * p * clamp((.65 - fk[s]) / .55, 0, 1.3) - ([0, 3, 8][Math.abs(s)] + (s > 0 && V.vp >= 65 ? 4 : 0) + (s < 0 && V.vp && V.vp <= 50 ? 4 : 0))); });
      ub += 1.5 - penT0 - penQ0 + (R0 == null ? 0 : Math.max(-5, Math.min(3, 8 * (R0 - .6))));
      if (ub < o.min) return { ok: true, lite: true, score: Math.max(0, Math.round(ub)), s: shifts[0], d: d, q: q };
    }
    var starts = vocalStarts(V); if (!starts.length) return { ok: false, why: "vocal" };
    var W = 8, best = null;
    for (var ai = 0; ai < starts.length; ai++) {
      var a = starts[ai], w = Math.min(W, V.nb - a); if (w < 3) continue;
      var bS = beatStarts(B, Math.ceil(w / q));
      for (var si = 0; si < shifts.length; si++) {
        var s = shifts[si];
        var Pkey = 55 * p * clamp((.65 - fk[s]) / .55, 0, 1.3);           /* the key fit (whole previews) */
        var penS = [0, 3, 8][Math.abs(s)] + (s > 0 && V.vp >= 65 ? 4 : 0) + (s < 0 && V.vp && V.vp <= 50 ? 4 : 0);
        for (var bi = 0; bi < bS.length; bi++) {
          var b0 = bS[bi], hs = 0, hw = 0, clash = 0, bv = 0, bn = 0, cov = 0;
          for (var i = 0; i < w; i++) {
            var j = q === 2 ? b0 + Math.floor(i / 2) : q === .5 ? b0 + 2 * i : b0 + i; if (j >= B.nb) break;
            cov++;
            var hb = q === .5 && j + 1 < B.nb && B.hbc[j] && B.hbc[j + 1] ? cu(B.hbc[j].map(function (x, k) { return x + B.hbc[j + 1][k]; })) : B.hbc[j];
            var vb = V.vbc[a + i], wl = V.vlev[a + i] >= 3 ? V.vlev[a + i] : 0;
            bv += B.vlev[j]; bn++;
            if (!vb || !wl || !hb) continue;
            hs += wl * cosRot(vb, hb, s); hw += wl;
            if (B.vlev[j] >= 5) clash += wl;
          }
          if (!hw) continue;
          var Hb = hs / hw, O = clash / hw;
          var Pbar = 24 * p * clamp((.55 - Hb) / .7, 0, 1);             /* the vocal on the right chords (bar by bar) */
          var phrase = (B.sec || []).indexOf(b0) >= 0 ? 1.5 : 0;
          var sc = 100 - Pkey - Pbar - penS - 22 * O + phrase - 20 * (1 - cov / w);   /* the beat must last under the vocal */
          if (!best || sc > best.sc) best = { sc: sc, a: a, b: b0, s: s, w: w, H: fk[s], Hb: Hb, O: O, bvoc: bn ? bv / bn : 0 };
        }
      }
    }
    if (!best) return { ok: false, why: "bars" };
    var R = V.rp && B.rp ? cos(V.rp, B.rp) : null;
    var penT = d <= .02 ? 150 * d : 3 + 400 * (d - .02),           /* up to 2 % is inaudible with WSOLA; 6 % costs 19 */ penQ = (V.vdb < -12 ? 6 : V.vdb < -9 ? 3 : 0) + (V.vs < .15 ? 6 : 0), bonR = R == null ? 0 : Math.max(-5, Math.min(3, 8 * (R - .6)));
    var score = Math.max(0, Math.min(100, Math.round(best.sc - penT - penQ + bonR)));
    var cents = Math.round((B.tc || 0) - (V.tc || 0)); if (Math.abs(cents) < 15) cents = 0;
    var semis = best.s + cents / 100;
    var lead = Math.min(2, best.b);                                  /* B plays up to 2 bars before the vocal comes in */
    var plan = { v: V.k, b: B.k, semis: Math.round(semis * 100) / 100, aAt: V.t0 + 4 * best.a * V.p, bAt: B.t0 + 4 * best.b * B.p, leadBars: lead, lead: lead * 4 * B.p,
      cleanB: best.bvoc >= 2.5, q: q, r: Math.round(r * 1e4) / 1e4 };
    best.p = p; best.Hn = clamp(.7 * clamp((best.H + .1) / .75, 0, 1) + .3 * clamp((best.Hb + .15) / .7, 0, 1), 0, 1);
    return { ok: true, score: score, plan: plan, s: best.s, cents: cents, H: best.H, Hb: best.Hb, Hn: best.Hn, Hown: V.Fown, tonal: p, O: best.O, R: R, d: d, q: q,
      aBar: best.a, bBar: best.b, bars: best.w, keyV: V.key, keyB: B.key, why: whyOf(V, B, best, cents, d, R) };
  }
  function whyOf(V, B, x, cents, d, R) {
    var w = [];
    var fit = Math.round(Math.min(1, x.Hn) * 100);
    if (x.p < .6) w.push(fit >= 70 ? "שירה קצבית (ראפ) שגם יושבת טוב על האקורדים של הביט" : "שירה קצבית (ראפ): הקצב קובע כאן יותר מהאקורדים");
    else w.push(fit >= 90 ? "השירה יושבת על האקורדים של הביט כמו על השיר שלה" : fit >= 75 ? "התווים של השירה מתאימים לאקורדים של הביט (" + fit + "%)" : "יש תווים שמתחככים באקורדים (" + fit + "%)");
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
