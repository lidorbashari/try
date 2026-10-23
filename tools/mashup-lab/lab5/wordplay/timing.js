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
  /* one candidate (A word end eA, B word start sB) → timing, or null */
  function place(eA, sB, gA, gB, tr, durB) {
    var pA = 60 / gA.bpm, xe = xOf(gA, eA), cands = [], c, q = tr.q;
    if (tr.synced) {
      var per = (q === .5 ? 8 : 4) * q, xs = xOf(gB, sB), gapX = .04 / pA, opts = [];
      var k = Math.floor((xs - q * (xe + gapX)) / per);
      opts.push({ c: per * k, half: false });
      /* the other half of the period: still bar on bar when q ≠ 1; for q = 1 it puts B's bar line on A's beat 3 */
      opts.push({ c: per * Math.floor((xs - q * (xe + gapX) - per / 2) / per) + per / 2, half: q === 1 });
      opts.forEach(function (o) {
        var xw = (xs - o.c) / q;                                   /* B's word start in A beats */
        var lo1 = xe - .06 / pA, lo = xe + .03 / pA, hi = xw - .05 / pA, pts = [];
        for (var x = Math.ceil(lo1); x <= hi; x++) {
          var bar = mod(x, 4) === 0;
          if (x < lo && !bar) continue;
          pts.push({ x: x, on: bar ? "1" : mod(x, 4) === 2 ? "3" : "beat" });
        }
        for (x = Math.ceil(lo * 2) / 2; x <= hi && pts.length < 1; x += .5) pts.push({ x: x, on: "off" });
        if (!pts.length && hi >= lo1) pts.push({ x: hi, on: "off" });     /* words back to back: just before B's word */
        /* the first grid point after the word; a bar line wins when it is within ~1 beat */
        pts.sort(function (a, b) { return a.x - b.x; });
        var pick = null;
        for (var i = 0; i < pts.length; i++) {
          var pt = pts[i], bPos = tOf(gB, q * pt.x + o.c);
          if (bPos < .05) continue;
          if (!pick) pick = pt;
          if (pt.on === "1" && pt.x - xe <= 1.25 && pick.on !== "1") { pick = pt; break; }
          if (pick.on === "1") break;
        }
        if (!pick) return;
        var bP = tOf(gB, q * pick.x + o.c);
        cands.push({ cut: tOf(gA, pick.x), bPos: bP, on: pick.on, half: o.half, gap: (xw - xe) * pA, wait: (xw - pick.x) * pA });
      });
      if (!cands.length) return null;
      cands.sort(function (a, b) { return a.gap + (a.half ? .8 : 0) - (b.gap + (b.half ? .8 : 0)); });
      c = cands[0];
      return c.gap > 4 ? null : c;
    }
    /* tempos too far apart: B keeps its own tempo; the cut on A's beat, B starts on its own beat before its word */
    var pB = 60 / gB.bpm, x2 = Math.ceil(xe + .03 / pA), xbar = Math.ceil((xe - .06 / pA) / 4) * 4;
    var xc = xbar - xe <= 1.25 ? xbar : x2, cut = tOf(gA, xc);
    var xs2 = xOf(gB, sB), xb = Math.floor(xs2 - .05 / pB), xbb = Math.floor((xs2 - .05 / pB) / 4) * 4;
    if (xs2 - xbb <= 1.5) xb = xbb;                                 /* enter on B's bar line when the word sits near it */
    var bPos = tOf(gB, xb);
    if (bPos < .05) { xb += Math.ceil((.05 - bPos) / pB); bPos = tOf(gB, xb); if (bPos > sB - .02) return null; }
    return { cut: cut, bPos: bPos, on: mod(xc, 4) === 0 ? "1" : mod(xc, 4) === 2 ? "3" : "beat", half: false, gap: (cut - eA) + (sB - bPos), wait: sB - bPos };
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
        var leadIn = a.s - 0, rB = tr.synced ? tr.r : 1, tail = (durB - .4 - pl.bPos) / rB;
        var sc = 2 * (a.p + b.p) + (a.n > 1 ? .6 : 0) + (b.n > 1 ? .6 : 0) - 1.2 * Math.max(0, pl.gap) - (pl.gap > 2.2 ? 3 : 0);
        if (leadIn < 4) sc -= (4 - leadIn) * 1.2;
        if (tail < 9) sc -= (9 - tail) * 1.5;
        if (pl.half) sc -= .8;
        if (pl.on === "off") sc -= 1.5;
        var vb = vocalMax(anB, gB, b.s - 2 * 60 / gB.bpm, b.s - .05), va = vocalMax(anA, gA, a.e + .05, a.e + 2 * 60 / gA.bpm);
        if (vb >= 0 && vb <= 2) sc += .8;                          /* B's word starts a line */
        if (va >= 0 && va <= 2) sc += .5;                          /* A's word ends a line */
        if (!best || sc > best.sc) best = { sc: sc, a: a, b: b, pl: pl, tail: tail };
      });
    });
    if (!best) return { ok: false, why: "place" };
    var pl = best.pl, a = best.a, b = best.b, pA = 60 / gA.bpm, rB = tr.synced ? tr.r : 1;
    /* A's lead-in: from a bar line 4 bars (2 when slow) before the bar of its word */
    var nb = 16 * pA <= 9.5 ? 4 : 2, xw = Math.floor(xOf(gA, a.s) / 4) * 4, xs = xw - 4 * nb;
    while (tOf(gA, xs) < 0 && xs < xw) xs += 4;
    var aStart = tOf(gA, xs);
    if (aStart < 0 || xs >= xw || a.s - aStart < 2.5) aStart = 0;
    /* key */
    var kA = keyOf(anA, link.mix && link.mix.keyA), kB = keyOf(anB, link.mix && link.mix.keyB);
    var tech = String(link.technique || (link.mix && link.mix.technique) || ""), want = drop ? "drop" : /^(double|blend|callresp)$/.test(tech) ? "blend" : tech === "cut" ? "cut" : "echo";
    var fit = kA && kB ? keyFit(kA.k, kB.k, want === "blend" || want === "drop" ? 2 : 1) : { semis: 0, rel: undefined, keyB: kB && kB.k };
    if (!tr.synced) fit = { semis: 0, rel: kA && kB ? camRel(camParse(kA.k), camParse(kB.k)) : undefined, keyB: kB && kB.k };
    var style = want;
    if (!tr.synced && style !== "cut") style = "echo";                  /* a tempo change: cut with an echo on A's word */
    if (fit.rel === null && style === "blend") style = "echo";          /* clashing keys: no overlap */
    /* B under A before the cut: blend 1 bar of B's instrumental, drop the 2-bar build-up */
    var pre = 0, barB = 4 * 60 / gB.bpm;
    if (style === "blend") {
      pre = 4 * pA;
      if (pl.bPos - pre * rB < .05 || vocalMax(anB, gB, pl.bPos - pre * rB, pl.bPos - .05) >= 5) { pre = 0; style = "echo"; }
    } else if (style === "drop") {
      pre = pl.bPos - 2 * barB >= .05 ? 8 * pA : pl.bPos - barB >= .05 ? 4 * pA : 0;
    }
    var ride = null;
    if (tr.ride) {                                   /* hold A's tempo for a few of B's bars after its word, then glide home */
      var bB = 4 * 60 / gB.bpm, room = durB - .5 - pl.bPos, hold = room / rB >= 14 ? 4 : 2;
      var i1 = Math.max(pl.bPos + hold * bB, b.e + 60 / gB.bpm), i2 = Math.min(durB - .3, i1 + 8 * bB);
      if (i2 - i1 >= 2 * bB) ride = { r0: r3(rB), i1: r3(i1), i2: r3(i2), hold: hold, bars: Math.round((i2 - i1) / bB) };
    }
    var tailRaw = ride ? rideOut(ride, durB - .4) - rideOut(ride, pl.bPos) : best.tail;
    var tail = clamp(tailRaw, 3, 16);
    function trim(an) { return an && isFinite(an.lufs) ? r3(clamp(Math.pow(10, (-11 - an.lufs) / 20), .45, 1.6)) : 1; }
    var echo = style === "echo" || style === "drop" ? { d: r3(.75 * pA <= .6 ? .75 * pA : .5 * pA), fb: .42, wet: .5 } : null;
    var out = {
      ok: true, synced: tr.synced, q: tr.q, r: r3(rB), ride: ride, semis: fit.semis || 0, rel: fit.rel, keyA: kA ? kA.k : null, keyB: kB ? kB.k : null, keyB2: fit.keyB || null,
      keySrc: kA && kB ? (kA.src === "measured" && kB.src === "measured" ? "measured" : "catalog") : null,
      style: style, aStart: r3(aStart), cut: r3(pl.cut), bPos: r3(pl.bPos), pre: r3(pre), tail: r3(tail),
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
    if (p.semis) s.push("B מוזז " + (Math.abs(p.semis) === 1 ? "חצי טון" : "טון שלם") + " " + (p.semis > 0 ? "למעלה" : "למטה") + " (" + p.keyB + " → " + p.keyB2 + ") כדי להתאים לסולם של A (" + p.keyA + ").");
    else if (p.rel) s.push("הסולמות מתאימים (" + p.keyA + " ו־" + p.keyB + ").");
    else if (p.rel === null) s.push("הסולמות מתנגשים (" + p.keyA + " מול " + p.keyB + "), אז אין חפיפה: חיתוך נקי" + (p.echo ? " עם אקו." : "."));
    var where = p.onBeat === "1" ? "על ה־1 של התיבה" : p.onBeat === "3" ? "על הפעמה השלישית בתיבה" : p.onBeat === "beat" ? "על פעמה" : "רגע לפני המילה של B";
    if (p.drop) s.push("החיתוך " + where + ": הדרופ של B נוחת מיד אחרי המילים של A.");
    else s.push("החיתוך " + where + ", מיד אחרי המילה של A, והמילה של B נכנסת " + (p.gap < .35 ? "מיד אחריה" : "אחרי " + (Math.round(p.gap * 10) / 10) + " שניות") + ".");
    if (p.style === "echo") s.push("אקו מסונכרן לקצב ממשיך את המילה של A לתוך B.");
    else if (p.style === "blend") s.push("B מתנגן תיבה אחת מתחת ל־A בלי הבס, ובחיתוך מחליפים את הבס (Bass Swap).");
    else if (p.style === "drop") s.push("ה־Build-up של B עולה מתחת ל־A עם פילטר שנפתח.");
    return s;
  }

  var api = { plan: plan, summary: summary, keyFit: keyFit, camRel: function (a, b) { return camRel(camParse(a), camParse(b)); }, camShift: function (k, s) { return camStr(camShift(camParse(k), s)); },
    tempoRel: tempoRel, rideOut: rideOut, place: place, dropAt: dropAt, phraseEnds: phraseEnds, phraseStarts: phraseStarts, xOf: xOf, tOf: tOf, wordsOf: wordsOf };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.WordTiming = api;
})(typeof window !== "undefined" ? window : this);
