/* Mashup Lab · word-play timing: WHERE a "מעבר מילים" cuts, computed from measured data only.
   Pure functions, no DOM, no audio (unit-tested in node: wordplay/test/t_timing.js).

   WordTiming.plan(link, info, opts) → plan
     link   a word-play link: { type, technique, word: "A word → B word", mix: { keyA, keyB, bpmA, bpmB } }
     info   { gA, gB: beat grids {bpm, b0, db} of the two previews (seconds), durA, durB }
     opts   { wt: wordtimes entry {a: [[start, end, p, n]...], b: [...]}, anA, anB: analysis records, drop: bool }
   plan = {
     ok, synced, q, r          tempo: B plays r× faster (WSOLA, pitch kept) so its beats continue A's (q = B beats per A beat)
     ride                      tempos 10–30 % apart: B still enters at A's tempo (r), holds it a few bars, then glides back
                               to its own tempo (DJs ride the pitch fader): { r0, i1, i2 } = rate r0 until B's time i1, a
                               linear glide to 1 by i2 (s, B's preview time); null when B keeps r for the whole tail
     semis, rel, keyA, keyB    B shifted by `semis` semitones so the keys fit (rel: same | rel | adj | null = clash)
     style                     cut | echo | blend | drop
     aStart                    A starts here (s, A's preview time), a bar line some bars before A's word
     cut                       the handoff, s in A's preview time, on A's beat grid
     bPos                      B's position at the cut (s, B's preview time, before the stretch)
     pre                       seconds of B under A before the cut (blend / drop), 0 = a clean entry
     tail                      seconds B plays after the cut
     wA, wB                    the words used: [start, end] in each preview; foundA / foundB (from Whisper or not)
     gap                       seconds between the end of A's word and the start of B's word, as heard
     onBeat                    "1" (bar line) | "3" | "beat" | "off" where the cut lands in A's bar
     trimA, trimB, echo, notes (Hebrew)
   }
   The rule (how DJs do word play): A's word ends, and on the next beat of the SAME grid B comes in, positioned so
   its own word lands right after, B's bar lines on A's bar lines (same tempo after the stretch). */
(function (root) {
  "use strict";
  function xOf(g, t) { return (t - g.b0) / (60 / g.bpm) - g.db; }          /* beats since a bar line (bar lines at x ≡ 0 mod 4) */
  function tOf(g, x) { return g.b0 + (g.db + x) * (60 / g.bpm); }
  function mod(a, n) { return ((a % n) + n) % n; }
  function clamp(x, a, b) { return Math.min(b, Math.max(a, x)); }
  function r3(x) { return Math.round(x * 1000) / 1000; }

  /* ---------- keys (Camelot) ---------- */
  function camParse(k) { var m = /^(1[0-2]|[1-9])\s*([AB])$/i.exec(String(k || "").trim()); return m ? { n: +m[1], l: m[2].toUpperCase() } : null; }
  function camStr(c) { return c ? c.n + c.l : null; }
  function camShift(c, s) { return c ? { n: mod(c.n - 1 + 7 * s, 12) + 1, l: c.l } : null; }   /* +1 semitone = +7 on the wheel */
  function camRel(a, b) {
    if (!a || !b) return null;
    if (a.n === b.n) return a.l === b.l ? "same" : "rel";
    if (a.l === b.l && (mod(a.n - b.n, 12) === 1 || mod(b.n - a.n, 12) === 1)) return "adj";
    return null;
  }
  /* the smallest shift of B (±maxShift semitones) that makes the two keys mix */
  function keyFit(kA, kB, maxShift) {
    var A = camParse(kA), B = camParse(kB), best = null;
    if (!A || !B) return { semis: 0, rel: undefined, keyB: kB || null };
    [0, 1, -1, 2, -2].forEach(function (s) {
      if (Math.abs(s) > maxShift) return;
      var b = camShift(B, s), rel = camRel(A, b);
      if (!rel) return;
      var cost = Math.abs(s) + (rel === "same" ? 0 : rel === "rel" ? .3 : .5);
      if (!best || cost < best.cost) best = { semis: s, rel: rel, cost: cost, keyB: camStr(b) };
    });
    return best || { semis: 0, rel: null, keyB: camStr(B) };
  }
  /* the key decision by ear (analysis v2 profiles of the two previews, 12 pitch classes each: hc = harmony, vc = singing):
     B moved by s semitones fits A when A's chords and B's chords agree, A's last word (and its echo) sits on B's chords,
     and B's first word sits on A's key. Pearson correlation (mean-centred), so any two songs score about 0 by chance. */
  function prof(sv) { if (!sv || String(sv).length !== 12) return null; var v = [], m = 0, i, n = 0; for (i = 0; i < 12; i++) { v.push(+String(sv).charAt(i) || 0); m += v[i]; } m /= 12;
    for (i = 0; i < 12; i++) { v[i] -= m; n += v[i] * v[i]; } n = Math.sqrt(n); if (!(n > 1e-6)) return null; for (i = 0; i < 12; i++) v[i] /= n; return v; }
  function corrRot(a, b, s) { var c = 0; for (var i = 0; i < 12; i++) c += a[i] * b[mod(i + s, 12)]; return c; }   /* a vs b moved by s */
  function earFit(anA, anB, maxShift) {
    var hA = prof(anA && anA.hc), hB = prof(anB && anB.hc), vA = prof(anA && anA.vc), vB = prof(anB && anB.vc);
    if (!hA || !hB) return null;
    var best = null;
    [0, 1, -1, 2, -2].forEach(function (s) {
      if (Math.abs(s) > maxShift) return;
      /* B's profile moved up by s: bin i of A meets bin i − s of B */
      var f = .5 * corrRot(hA, hB, -s), w = .5;
      if (vA) { f += .25 * corrRot(vA, hB, -s); w += .25; }
      if (vB) { f += .25 * corrRot(hA, vB, -s); w += .25; }
      f /= w;
      var sc = f - .05 * Math.abs(s);
      if (!best || sc > best.sc + 1e-9) best = { semis: s, fit: f, sc: sc };
    });
    return { semis: best.semis, fit: Math.round(best.fit * 100) / 100, rel: best.fit >= .45 ? "ear" : best.fit >= .25 ? "ear-ok" : null };
  }
  function keyOf(an, fallback) {        /* the key measured on the preview when it is clear, else the catalog key */
    if (an && an.key && (an.ks >= (an.km === "e" ? .45 : .62))) return { k: an.key, src: "measured" };
    return fallback ? { k: fallback, src: "catalog" } : null;
  }

  /* ---------- analysis helpers (per-beat digit strings) ---------- */
  function digitAt(an, g, field, t) {
    if (!an || !an[field] || an.t0 == null || !g) return -1;
    var i = Math.floor((t - an.t0) / (60 / g.bpm) + 1e-6), s = an[field];
    return i >= 0 && i < s.length ? +s.charAt(i) : -1;
  }
  function vocalMax(an, g, t1, t2) {
    var p = 60 / g.bpm, m = -1;
    for (var t = t1; t < t2 - 1e-6; t += p / 2) m = Math.max(m, digitAt(an, g, "voc", t));
    return m;
  }
  /* sung-phrase boundaries: a line ends (vocal → silence) / starts (silence → vocal), on beats */
  function phraseEnds(an, g, dur) {
    var out = [], s = an && an.voc; if (!s || an.t0 == null) return out;
    var p = 60 / g.bpm;
    for (var i = 1; i + 2 < s.length; i++) if (+s[i] >= 4 && +s[i + 1] <= 2 && +s[i + 2] <= 2) out.push(r3(an.t0 + (i + 1) * p));
    return out.filter(function (t) { return t > 4 && t < dur - 6; });
  }
  function phraseStarts(an, g, dur) {
    var out = [], s = an && an.voc; if (!s || an.t0 == null) return out;
    var p = 60 / g.bpm;
    for (var i = 2; i < s.length; i++) if (+s[i] >= 4 && +s[i - 1] <= 2 && +s[i - 2] <= 2) out.push(r3(an.t0 + i * p));
    return out.filter(function (t) { return t > 1 && t < dur - 8; });
  }
  /* B's drop: the bar line with the biggest jump in instrumental energy */
  function dropAt(an, g, dur) {
    var s = an && an.nrg; if (!s || an.t0 == null) return null;
    var p = 60 / g.bpm, bars = Math.floor(s.length / 4), E = [], best = null;
    for (var b = 0; b < bars; b++) { var v = 0; for (var k = 0; k < 4; k++) v += +s[4 * b + k]; E.push(v / 4); }
    for (b = 2; b + 1 < bars; b++) {
      var t = an.t0 + 4 * b * p; if (t > dur - 8) break;
      var rise = (E[b] + E[b + 1]) / 2 - (E[b - 1] + E[b - 2]) / 2;
      if (!best || rise > best.rise) best = { t: t, rise: rise };
    }
    return best && best.rise >= 1.5 ? r3(best.t) : null;
  }

  /* ---------- where to cut ---------- */
  var RIDE_LO = .75, RIDE_HI = 1.3;                 /* beyond this a stretch of the whole mix sounds wrong: cut + echo instead */
  function tempoRel(gA, gB) {
    var best = null;
    [1, .5, 2].forEach(function (q) {               /* the beat ratio that needs the smallest stretch of B */
      var r = gA.bpm * q / gB.bpm, cost = Math.abs(Math.log(r));
      if (!best || cost < best.cost - 1e-9) best = { q: q, r: r, cost: cost };
    });
    var q = best.q, r = best.r, near = r >= .9 && r <= 1.1, ride = !near && r >= RIDE_LO && r <= RIDE_HI;
    return { q: q, r: r, synced: near || ride, ride: ride };
  }
  /* the ride mapping (B's time ↔ the time B is heard): rate r0 until i1, a glide (linear in heard time) to 1 by i2, then 1 */
  function rideOut(rd, i) {                         /* heard seconds from B's 0 to B's time i */
    var o1 = rd.i1 / rd.r0; if (i <= rd.i1) return i / rd.r0;
    var T2 = 2 * (rd.i2 - rd.i1) / (rd.r0 + 1);
    if (i >= rd.i2) return o1 + T2 + (i - rd.i2);
    var a = (1 - rd.r0) / (2 * T2), b = rd.r0, c = -(i - rd.i1);
    return o1 + (Math.abs(a) < 1e-9 ? -c / b : (-b + Math.sqrt(Math.max(0, b * b - 4 * a * c))) / (2 * a));
  }
  /* one candidate (A word end eA, B word start sB) → timing ON THE ONE, or null. The cut is A's first bar line after its
     word (A's "1"); at that moment B comes in from its own bar line (B's "1"), the last one before its word, so the two
     bars line up (B stretched to A's tempo when synced, its bar lines on A's). A word may end ≤ 50 ms after a bar line
     (its tail fades under the cut); B's word may start ≤ 30 ms before its bar line. */
  function place(eA, sB, gA, gB, tr, durB) {
    var pA = 60 / gA.bpm, pB = 60 / gB.bpm, rB = tr.synced ? tr.r : 1;
    var xe = xOf(gA, eA), xc = Math.ceil((xe - .05 / pA) / 4 - 1e-9) * 4;
    var xs = xOf(gB, sB), xb = Math.floor((xs + .03 / pB) / 4 + 1e-9) * 4;
    var bPos = tOf(gB, xb), cut = tOf(gA, xc);
    if (bPos < .05 || bPos > durB - 3) return null;                  /* B's word sits before its first full bar in the clip */
    var gapA = Math.max(0, cut - eA), gapB = Math.max(0, sB - bPos) / rB;
    return { cut: cut, bPos: bPos, on: "1", half: false, gap: gapA + gapB, gapA: gapA, gapB: gapB, wait: gapB };
  }

  function wordsOf(link) {
    var p = String(link.word || "").split(/\s*(?:→|->|=|↔)\s*/).filter(Boolean);
    return { a: (p[0] || "").replace(/[?!.,"']+$/, ""), b: (p[1] || p[0] || "").replace(/[?!.,"']+$/, ""), drop: /דרופ|\bdrop\b/i.test(p[1] || "") };
  }

  function plan(link, info, opts) {
    opts = opts || {};
    var gA = info.gA, gB = info.gB, durA = info.durA || 30, durB = info.durB || 30, wt = opts.wt || {}, anA = opts.anA, anB = opts.anB;
    var notes = [], w = wordsOf(link), drop = opts.drop != null ? opts.drop : w.drop;
    if (!gA || !gB || !(gA.bpm > 30) || !(gB.bpm > 30)) return { ok: false, why: "grid" };
    var tr = tempoRel(gA, gB);
    /* candidate words: Whisper's timestamps, else sung-phrase boundaries, else bar lines */
    var occA = (wt.a || []).filter(function (o) { return o[1] > 1.5 && o[1] < durA - 4; }).map(function (o) { return { s: o[0], e: o[1], p: o[2] || .5, n: o[3] || 1, found: true }; });
    var occB = [];
    if (drop) { var dt = dropAt(anB, gB, durB); if (dt != null) occB.push({ s: dt, e: dt + .5, p: .8, n: 1, found: true, drop: true }); }
    else occB = (wt.b || []).filter(function (o) { return o[0] > .2 && o[0] < durB - 6; }).map(function (o) { return { s: o[0], e: o[1], p: o[2] || .5, n: o[3] || 1, found: true }; });
    var foundA = occA.length > 0, foundB = occB.length > 0;
    if (!foundA) {
      phraseEnds(anA, gA, durA).forEach(function (t) { occA.push({ s: t - .5, e: t, p: .3, n: 0, found: false }); });
      if (!occA.length) { var xe0 = Math.round(xOf(gA, Math.min(14, durA * .45)) / 4) * 4; occA.push({ s: tOf(gA, xe0) - .5, e: tOf(gA, xe0) - .05, p: .1, n: 0, found: false }); }
      notes.push("המילה של A לא נשמעת בקטע של 30 השניות, אז החיתוך נעשה בסוף משפט שירה של A.");
    }
    if (!foundB) {
      phraseStarts(anB, gB, durB).forEach(function (t) { occB.push({ s: t, e: t + .5, p: .3, n: 0, found: false }); });
      if (!occB.length) { var xb0 = Math.max(4, Math.round(xOf(gB, Math.min(8, durB * .3)) / 4) * 4); occB.push({ s: tOf(gB, xb0), e: tOf(gB, xb0) + .5, p: .1, n: 0, found: false }); }
      notes.push(drop ? "לא נמצא דרופ ברור בקטע של B, אז B נכנס בתחילת תיבה." : "המילה של B לא נשמעת בקטע של 30 השניות, אז B נכנס בתחילת משפט שירה.");
    }
    var best = null;
    occA.forEach(function (a) {
      occB.forEach(function (b) {
        var pl = place(a.e, b.s, gA, gB, tr, durB);
        if (!pl) return;
        var leadIn = a.s - 0, rB = tr.synced ? tr.r : 1, tail = (durB - .4 - pl.bPos) / rB, pA0 = 60 / gA.bpm, pB0 = 60 / gB.bpm;
        var bA = pl.gapA / pA0, bB = pl.gapB * rB / pB0;            /* the waits in beats: A's word → its 1, B's 1 → its word */
        var sc = 2 * (a.p + b.p) + (a.n > 1 ? .6 : 0) + (b.n > 1 ? .6 : 0) - .7 * Math.max(0, bA - 1) - .6 * Math.max(0, bB - 1) - .4 * Math.max(0, pl.gap - 2.5);
        if (leadIn < 4) sc -= (4 - leadIn) * 1.2;
        if (tail < 9) sc -= (9 - tail) * 1.5;
        var vb = vocalMax(anB, gB, b.s - 2 * pB0, b.s - .05), va = vocalMax(anA, gA, a.e + .05, a.e + 2 * pA0);
        if (vb >= 0 && vb <= 2) sc += .8;                          /* B's word starts a line */
        if (va >= 0 && va <= 2) sc += .5;                          /* A's word ends a line */
        if (vocalMax(anB, gB, pl.bPos, b.s - .05) >= 5) sc -= 1;    /* B would sing other words between its 1 and its word */
        if (vocalMax(anA, gA, a.e + .06, pl.cut - .03) >= 5) sc -= .4;   /* A sings on before its 1: it has to echo out early */
        if (!best || sc > best.sc) best = { sc: sc, a: a, b: b, pl: pl, tail: tail };
      });
    });
    if (!best) {                     /* no cut fits the words found: retry on sung phrases, then on plain bar lines */
      if (!opts._retry) return plan(link, info, Object.assign({}, opts, { wt: {}, _retry: 1 }));
      if (opts._retry === 1) return plan(link, info, Object.assign({}, opts, { wt: {}, anA: null, anB: null, _retry: 2 }));
      return { ok: false, why: "place" };
    }
    var pl = best.pl, a = best.a, b = best.b, pA = 60 / gA.bpm, rB = tr.synced ? tr.r : 1;
    /* A's lead-in: from a bar line 4 bars (2 when slow) before the bar of its word */
    var nb = 16 * pA <= 9.5 ? 4 : 2, xw = Math.floor(xOf(gA, a.s) / 4) * 4, xs = xw - 4 * nb;
    while (tOf(gA, xs) < 0 && xs < xw) xs += 4;
    var aStart = tOf(gA, xs);
    if (aStart < 0 || xs >= xw || a.s - aStart < 2.5) aStart = 0;
    /* key */
    var kA = keyOf(anA, link.mix && link.mix.keyA), kB = keyOf(anB, link.mix && link.mix.keyB);
    var tech = String(link.technique || (link.mix && link.mix.technique) || ""), want = drop ? "drop" : /^(double|blend|callresp)$/.test(tech) ? "blend" : tech === "cut" ? "cut" : "echo";
    var maxS = want === "blend" || want === "drop" ? 2 : 1, ear = earFit(anA, anB, maxS);
    var fit = kA && kB ? keyFit(kA.k, kB.k, maxS) : { semis: 0, rel: undefined, keyB: kB && kB.k };
    if (ear) fit = { semis: ear.semis, rel: ear.rel, keyB: kB ? camStr(camShift(camParse(kB.k), ear.semis)) || kB.k : null, ear: ear.fit };   /* the ear decides */
    if (!tr.synced) fit = { semis: 0, rel: ear ? (earFit(anA, anB, 0) || {}).rel : kA && kB ? camRel(camParse(kA.k), camParse(kB.k)) : undefined, keyB: kB && kB.k, ear: ear ? (earFit(anA, anB, 0) || {}).fit : undefined };
    var style = want;
    if (!tr.synced && style !== "cut") style = "echo";                  /* a tempo change: cut with an echo on A's word */
    if (fit.rel === null && style === "blend") style = "echo";          /* clashing keys: no overlap */
    /* B under A before the cut: blend 1 bar of B's instrumental, drop the 2-bar build-up */
    var pre = 0, barB = 4 * 60 / gB.bpm, barA = 4 * pA * Math.max(1, 1 / tr.q);   /* whole bars of both songs (q: B beats per A beat) */
    if (style === "blend") {
      pre = barA;
      if (pl.bPos - pre * rB < .05 || vocalMax(anB, gB, pl.bPos - pre * rB, pl.bPos - .05) >= 5) { pre = 0; style = "echo"; }
    } else if (style === "drop") {
      pre = pl.bPos - 2 * barA * rB >= .05 ? 2 * barA : pl.bPos - barA * rB >= .05 ? barA : 0;
    }
    /* A between its word and its 1: when it goes on singing (or we can't tell and the wait is long), its fader closes
       right after the word and a tempo-synced echo of the word carries the beat to the 1, where B comes in */
    var aSings = vocalMax(anA, gA, a.e + .06, pl.cut - .03), early = pl.gapA > .3 * pA && (aSings >= 4 || (aSings < 0 && pl.gapA > 1.6 * pA));
    var aOut = early ? Math.min(pl.cut, a.e + Math.min(.12, .25 * pA)) : pl.cut;
    if (early && style !== "drop") { style = "echo"; pre = 0; }
    var ride = null;
    if (tr.ride) {                                   /* hold A's tempo for a few of B's bars after its word, then glide home */
      var bB = 4 * 60 / gB.bpm, room = durB - .5 - pl.bPos, hold = room / rB >= 14 ? 4 : 2;
      var i1 = Math.max(pl.bPos + hold * bB, b.e + 60 / gB.bpm), i2;
      i1 = pl.bPos + Math.ceil((i1 - pl.bPos) / bB - 1e-9) * bB;    /* the glide starts on one of B's bar lines too */
      i2 = Math.min(durB - .3, i1 + 8 * bB);
      if (i2 - i1 >= 2 * bB) ride = { r0: r3(rB), i1: r3(i1), i2: r3(i2), hold: hold, bars: Math.round((i2 - i1) / bB) };
    }
    var tailRaw = ride ? rideOut(ride, durB - .4) - rideOut(ride, pl.bPos) : best.tail;
    var tail = clamp(tailRaw, 3, 16);
    function trim(an) { return an && isFinite(an.lufs) ? r3(clamp(Math.pow(10, (-11 - an.lufs) / 20), .45, 1.6)) : 1; }
    var echo = style === "echo" || style === "drop" ? { d: r3(.75 * pA <= .6 ? .75 * pA : .5 * pA), fb: pl.cut - aOut > 2 * pA ? .55 : .42, wet: .5 } : null;
    var out = {
      ok: true, fallback: opts._retry || 0, synced: tr.synced, q: tr.q, r: r3(rB), ride: ride, semis: fit.semis || 0, rel: fit.rel, ear: fit.ear == null ? null : fit.ear, keyA: kA ? kA.k : null, keyB: kB ? kB.k : null, keyB2: fit.keyB || null,
      keySrc: kA && kB ? (kA.src === "measured" && kB.src === "measured" ? "measured" : "catalog") : null,
      style: style, aStart: r3(aStart), cut: r3(pl.cut), aOut: r3(aOut), bPos: r3(pl.bPos), pre: r3(pre), tail: r3(tail),
      bFade: r3(Math.max(.012, (pl.bPos - b.s) / rB + .012)),        /* B fades in over its word's anticipation (≤ 30 ms before its 1) */
      wA: [r3(a.s), r3(a.e)], wB: [r3(b.s), r3(b.e)], foundA: a.found, foundB: b.found, drop: !!b.drop,
      gap: r3(pl.gap), half: pl.half, onBeat: pl.on, bpmA: Math.round(gA.bpm * 10) / 10, bpmB: Math.round(gB.bpm * 10) / 10,
      trimA: trim(anA), trimB: trim(anB), echo: echo, notes: notes, words: w
    };
    out.summary = summary(out);
    return out;
  }

  /* what happens, in Hebrew, for the card (DJ terms stay in English) */
  function summary(p) {
    var s = [], pct = Math.round((p.r - 1) * 1000) / 10;
    if (p.synced) {
      if (p.ride) s.push("הקצבים רחוקים (" + p.bpmA + " מול " + p.bpmB + " BPM), ובכל זאת B נכנס בדיוק בקצב של A (" + (pct > 0 ? "מואץ" : "מואט") + " " + Math.abs(pct) + "%) כדי שהביט ימשיך בלי קפיצה. אחרי " + p.ride.hold + " תיבות הוא חוזר בהדרגה לקצב שלו במשך " + p.ride.bars + " תיבות, כמו דיג'יי שרוכב על ה־Pitch (Tempo Ride).");
      else if (Math.abs(pct) >= .3) s.push("B " + (pct > 0 ? "מואץ" : "מואט") + " מ־" + p.bpmB + " ל־" + Math.round(p.bpmB * p.r * 10) / 10 + " BPM (" + (pct > 0 ? "+" : "") + pct + "%), כדי שהביט שלו ימשיך בדיוק את הביט של A.");
      else s.push("שני השירים כמעט באותו קצב, אז B נכנס כמו שהוא והביט ממשיך בלי קפיצה.");
      if (p.q !== 1) s.push("יחס קצב " + (p.q === 2 ? "1:2" : "2:1") + ": פעמה של שיר אחד היא שתי פעמות של השני.");
    } else s.push("הקצבים רחוקים מדי למתיחה (" + p.bpmA + " מול " + p.bpmB + " BPM), אז B נכנס בקצב שלו בדיוק על פעמה, ואקו על המילה של A מחליק את המעבר.");
    var ks = p.keyA && p.keyB ? " (" + p.keyA + " ו־" + p.keyB + ")" : "";
    if (p.semis) s.push("B מוזז " + (Math.abs(p.semis) === 1 ? "חצי טון" : "טון שלם") + " " + (p.semis > 0 ? "למעלה" : "למטה") + (p.keyB && p.keyB2 ? " (" + p.keyB + " → " + p.keyB2 + ")" : "") + (p.ear != null ? ": ככה, לפי ההאזנה לשני הקטעים, האקורדים והמילים של שניהם יושבים הכי טוב אחד על השני." : " כדי להתאים לסולם של A (" + p.keyA + ")."));
    else if (p.rel) s.push(p.ear != null ? "לפי ההאזנה לשני הקטעים, האקורדים והמילים של שניהם יושבים טוב אחד על השני" + ks + "." : "הסולמות מתאימים" + ks + ".");
    else if (p.rel === null) s.push((p.ear != null ? "לפי ההאזנה, ההרמוניות של שני הקטעים לא מסתדרות" : "הסולמות מתנגשים" + (p.keyA && p.keyB ? " (" + p.keyA + " מול " + p.keyB + ")" : "")) + ", אז אין חפיפה: חיתוך נקי" + (p.echo ? " עם אקו." : "."));
    var early = p.aOut != null && p.aOut < p.cut - .05;
    if (p.drop) s.push("על ה־1 שאחרי המילה של A הדרופ של B נוחת, מה־1 של התיבה שלו (On The One).");
    else s.push("B נכנס בדיוק על ה־1: ה־1 של התיבה של A שאחרי המילה, ומה־1 של התיבה של B" + (p.gap < .35 ? ", והמילה שלו מיד שם." : ", והמילה שלו אחרי " + (Math.round(p.gap * 10) / 10) + " שניות."));
    if (early) s.push("A ממשיך לשיר אחרי המילה, אז הפיידר שלו נסגר מיד אחריה, והאקו של המילה ממשיך את הביט עד ה־1.");
    if (p.style === "echo") s.push("אקו מסונכרן לקצב ממשיך את המילה של A לתוך B.");
    else if (p.style === "blend") s.push("B מתנגן תיבה אחת מתחת ל־A בלי הבס, ובחיתוך מחליפים את הבס (Bass Swap).");
    else if (p.style === "drop") s.push("ה־Build-up של B עולה מתחת ל־A עם פילטר שנפתח.");
    return s;
  }

  var api = { plan: plan, summary: summary, keyFit: keyFit, camRel: function (a, b) { return camRel(camParse(a), camParse(b)); }, camShift: function (k, s) { return camStr(camShift(camParse(k), s)); },
    tempoRel: tempoRel, rideOut: rideOut, earFit: earFit, place: place, dropAt: dropAt, phraseEnds: phraseEnds, phraseStarts: phraseStarts, xOf: xOf, tOf: tOf, wordsOf: wordsOf };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.WordTiming = api;
})(typeof window !== "undefined" ? window : this);
