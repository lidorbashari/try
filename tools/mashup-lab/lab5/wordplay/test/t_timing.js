/* node test/t_timing.js — unit tests of the word-play timing (no audio) */
"use strict";
const T = require("../timing.js");
const fs = require("fs"), path = require("path");
let ok = 0, bad = 0;
function chk(name, c, extra) { if (c) ok++; else bad++; console.log((c ? "OK   " : "FAIL ") + name + (extra ? "  " + extra : "")); }
const near = (a, b, e) => Math.abs(a - b) <= (e || 1e-6);

// keys
chk("+1 semitone = +7 on the wheel (8A → 3A)", T.camShift("8A", 1) === "3A");
chk("-1 semitone (8A → 1A)", T.camShift("8A", -1) === "1A");
chk("relations", T.camRel("8A", "8B") === "rel" && T.camRel("8A", "9A") === "adj" && T.camRel("8A", "8A") === "same" && T.camRel("8A", "10A") === null);
const kf = T.keyFit("8A", "3A", 1);
chk("clash 8A vs 3A fixed by shifting B -1 semitone", kf.semis === -1 && kf.rel === "same", JSON.stringify(kf));
chk("compatible keys are not shifted", T.keyFit("8A", "9A", 2).semis === 0);
chk("no fit within ±1 → semis 0, rel null", (() => { const f = T.keyFit("8A", "11B", 1); return f.semis === 0 && f.rel === null; })());

// the worked example
const gA = { bpm: 120, b0: .1, db: 0 }, gB = { bpm: 125, b0: .3, db: 1 };
const link = { type: "answer", technique: "echo", word: "X → Y", mix: { keyA: "8A", keyB: "8A" } };
let p = T.plan(link, { gA, gB, durA: 30, durB: 30 }, { wt: { a: [[10.25, 10.82, .9, 1]], b: [[8.0, 8.6, .9, 1]] } });
chk("plan ok + synced (B slowed to 120)", p.ok && p.synced && near(p.r, .96, 1e-3), JSON.stringify({ ok: p.ok, r: p.r }));
chk("on the one: the cut is A's first bar line after the word (12.10 s)", near(p.cut, 12.1, 1e-3) && p.onBeat === "1", "cut " + p.cut + " " + p.onBeat);
chk("on the one: B enters from its own bar line (6.54 s), its word 1.52 s after its 1", near(p.bPos, 6.54, 1e-3) && near((p.wB[0] - p.bPos) / p.r, 1.52, .01) && near(((T.xOf(gB, p.bPos) % 4) + 4) % 4, 0, 1e-6), "bPos " + p.bPos);
chk("gap between the words 2.8 s (both waits on the grid)", near(p.gap, 2.8, .01), "gap " + p.gap);
chk("A doesn't sing after its word here (unknown, wait < 2 beats? no: 2.6 beats) → it echoes out right after the word", p.aOut < p.cut && p.style === "echo" && p.echo, JSON.stringify({ aOut: p.aOut, st: p.style }));
chk("A starts on a bar line 4 bars before its word's bar", near(p.aStart, T.tOf(gA, 20 - 16), 1e-3), "aStart " + p.aStart);
chk("B's bar lines on A's bar lines after the cut", (() => { const xB = T.xOf(gB, p.bPos), xA = T.xOf(gA, p.cut); return near(((xB - xA) % 4 + 4) % 4, 0, 1e-6); })());
chk("summary in Hebrew", p.summary.length >= 3 && /B/.test(p.summary[0]), p.summary.join(" | "));

// a bar line right after the word wins
p = T.plan(link, { gA, gB: { bpm: 120, b0: .1, db: 0 }, durA: 30, durB: 30 }, { wt: { a: [[9.4, 10.05, .9, 1]], b: [[6.25, 6.7, .9, 1]] } });
chk("cut lands on the 1 when it is within a beat after the word", p.ok && p.onBeat === "1" && near(p.cut, 10.1, 1e-3), p.cut + " " + p.onBeat);
chk("then B's word (on its beat 1.5 of the bar) follows 0.15 s later", near((p.wB[0] - p.bPos) / p.r, .15, .01), String((p.wB[0] - p.bPos) / p.r));

// tempos 10–30 % apart: B enters at A's tempo, then rides back to its own
const gR = { bpm: 126, b0: .1, db: 0 };
p = T.plan(link, { gA: { bpm: 95, b0: .2, db: 0 }, gB: gR, durA: 30, durB: 30 }, { wt: { a: [[12.0, 12.6, .9, 1]], b: [[9.6, 10.1, .9, 1]] } });
chk("95 vs 126: B enters at A's tempo (r = 95/126) and rides back (Tempo Ride)", p.ok && p.synced && near(p.r, 95 / 126, 1e-3) && p.ride && near(p.ride.r0, p.r, 1e-9), JSON.stringify({ s: p.synced, r: p.r, ride: p.ride }));
chk("ride: B's bar lines on A's bar lines at the cut", (() => { const xB = T.xOf(gR, p.bPos), xA = T.xOf({ bpm: 95, b0: .2, db: 0 }, p.cut), m = ((xB - xA) % 4 + 4) % 4; return Math.min(m, 4 - m) < .01; })(), "bPos " + p.bPos + " cut " + p.cut);
chk("ride: the glide starts after B's word and holds A's tempo at least 2 bars", p.ride.i1 >= p.wB[1] && p.ride.i1 - p.bPos >= 2 * 4 * 60 / 126 - 1e-6 && p.ride.i2 > p.ride.i1, JSON.stringify(p.ride));
chk("ride: heard time is continuous and monotonic (rate r0 → 1)", (() => { const rd = p.ride; let prev = -1, ok2 = true; for (let i = 0; i <= 30; i += .05) { const o = T.rideOut(rd, i); if (!(o > prev)) ok2 = false; prev = o; }
  const d1 = T.rideOut(rd, rd.i1) - T.rideOut(rd, rd.i1 - .01), d2 = T.rideOut(rd, rd.i2 + .01) - T.rideOut(rd, rd.i2); return ok2 && near(d1, .01 / rd.r0, 1e-4) && near(d2, .01, 1e-4); })());
chk("ride: summary says so", p.summary.some(x => /Tempo Ride/.test(x)), p.summary[0]);
p = T.plan(link, { gA: { bpm: 100, b0: .2, db: 0 }, gB: { bpm: 136, b0: .1, db: 0 }, durA: 30, durB: 30 }, { wt: { a: [[12.0, 12.6, .9, 1]], b: [[9.6, 10.1, .9, 1]] } });
chk("100 vs 136 (beyond a natural stretch): echo style, B native", p.ok && !p.synced && p.r === 1 && !p.ride && p.style === "echo", JSON.stringify({ s: p.synced, r: p.r, st: p.style }));
chk("B enters on its own beat before its word", (() => { const x = T.xOf({ bpm: 136, b0: .1, db: 0 }, p.bPos); return near(x, Math.round(x), 1e-2) && p.bPos < 9.6; })(), "bPos " + p.bPos);

// half / double time
p = T.plan(link, { gA: { bpm: 70, b0: .2, db: 0 }, gB: { bpm: 140, b0: .1, db: 2 }, durA: 30, durB: 30 }, { wt: { a: [[14.0, 14.5, .9, 1]], b: [[12.1, 12.5, .9, 1]] } });
chk("70 vs 140: synced with q = 2, no stretch", p.ok && p.synced && p.q === 2 && near(p.r, 1, 1e-3), JSON.stringify({ q: p.q, r: p.r }));

// key shift chosen
p = T.plan(Object.assign({}, link, { technique: "double" }), { gA, gB, durA: 30, durB: 30 }, { wt: { a: [[10.25, 10.82, .9, 1]], b: [[8.0, 8.6, .9, 1]] },
  anA: { key: "8A", ks: .8, km: "e" }, anB: { key: "10A", ks: .8, km: "e" } });
chk("blend asks for a key fit: 10A → 8A is -2 semitones", p.ok && p.semis === -2 && p.rel === "same", JSON.stringify({ s: p.semis, rel: p.rel, k: p.keyB2 }));

// the key decision by ear (analysis v2 profiles): C major chords + singing vs the same a whole tone up
const rot = (str, k) => str.split("").map((_, i) => str[((i - k) % 12 + 12) % 12]).join("");   /* pitch classes moved up by k */
const Cmaj = "905090590509", Cvoc = "703080480306";
let e = T.earFit({ hc: Cmaj, vc: Cvoc }, { hc: Cmaj, vc: Cvoc }, 2);
chk("ear: the same harmony needs no shift and fits", e && e.semis === 0 && e.rel === "ear" && e.fit > .9, JSON.stringify(e));
e = T.earFit({ hc: Cmaj, vc: Cvoc }, { hc: rot(Cmaj, 2), vc: rot(Cvoc, 2) }, 2);
chk("ear: B a whole tone up → B moved down 2 semitones", e && e.semis === -2 && e.rel === "ear", JSON.stringify(e));
e = T.earFit({ hc: Cmaj, vc: Cvoc }, { hc: "909090909090", vc: "505050505050" }, 2);
chk("ear: whole-tone harmony fits no shift → clash (no overlap)", e && e.rel === null, JSON.stringify(e));
p = T.plan(Object.assign({}, link, { technique: "double" }), { gA, gB, durA: 30, durB: 30 }, { wt: { a: [[10.25, 10.82, .9, 1]], b: [[8.0, 8.6, .9, 1]] },
  anA: { key: "8B", ks: .8, km: "e", hc: Cmaj, vc: Cvoc }, anB: { key: "10B", ks: .8, km: "e", hc: rot(Cmaj, 2), vc: rot(Cvoc, 2) } });
chk("plan: the ear decides the shift and says so (Hebrew)", p.ok && p.semis === -2 && p.ear > .9 && p.summary.some(x => /לפי ההאזנה/.test(x)), JSON.stringify({ s: p.semis, ear: p.ear, k: p.keyB2 }));

// word not in the preview → phrase boundary from the vocal per beat
const anA = { t0: .1, voc: "0000" + "5555" + "5550" + "0000" + "6666" + "6600" + "0000" + "0000" + "7777" + "7777" + "0000" + "0000" + "0000" + "0000" + "0000", key: "8A", ks: .3 };
const anB = { t0: .78, voc: "0000" + "0000" + "0006" + "6666" + "0000" + "0000" + "0000" + "0000" + "0000" + "0000" + "0000" + "0000" + "0000" + "0000" };
p = T.plan(link, { gA, gB, durA: 30, durB: 30 }, { wt: {}, anA, anB });
chk("no words: plan from sung-phrase boundaries + Hebrew notes", p.ok && !p.foundA && !p.foundB && p.notes.length === 2, JSON.stringify({ ok: p.ok, cut: p.cut, notes: p.notes.length }));

// the drop
const anD = { t0: .78, nrg: "3333" + "3333" + "3333" + "4444" + "9999" + "9999" + "9999" + "9999" + "8888" + "8888" + "8888" + "8888" + "8888" + "8888" };
p = T.plan({ type: "answer", technique: "echo", word: "הנה זה בא → הדרופ", mix: {} }, { gA, gB, durA: 30, durB: 30 }, { wt: { a: [[10.25, 10.82, .9, 3]] }, anB: anD });
chk("drop: B's drop bar found and lands right after A's words", p.ok && p.drop && p.style === "drop" && near(p.wB[0], .78 + 16 * .48, 1e-3), JSON.stringify({ wB: p.wB, st: p.style, pre: p.pre }));

// all curated links with the real beat grids and synthetic words: never throws, sane output
const LAB = path.join(__dirname, "..", "..", "..", "..", "..", "..", "..", "home", "claude", "try", "docs", "mashup-lab");
const lab = fs.existsSync("/home/claude/try/docs/mashup-lab") ? "/home/claude/try/docs/mashup-lab" : LAB;
const links = JSON.parse(fs.readFileSync(lab + "/wordplay-links.json", "utf8")), beats = JSON.parse(fs.readFileSync(lab + "/beats.json", "utf8")).map;
let n = 0, okc = 0, synced = 0, ons = {}, gaps = [];
for (const l of links) {
  const a = beats[l.a], b = beats[l.b]; if (!a || !b) continue;
  const g1 = { bpm: a[0], b0: a[1], db: a[2] }, g2 = { bpm: b[0], b0: b[1], db: b[2] };
  for (const sA of [6, 13.3, 21.7]) for (const sB of [2.2, 9.1, 15.5]) {
    n++;
    const q = T.plan(l, { gA: g1, gB: g2, durA: 30, durB: 30 }, { wt: { a: [[sA, sA + .55, .8, 1]], b: [[sB, sB + .5, .8, 1]] } });
    if (!q.ok) continue;
    okc++; if (q.synced) synced++; ons[q.onBeat] = (ons[q.onBeat] || 0) + 1; gaps.push(q.gap);
    if (!(q.cut >= sA + .55 - .061) || !(q.cut <= sA + .55 + 4.1) || !(q.bPos >= .05) || !(q.aStart >= 0 && q.aStart < sA)) { bad++; console.log("FAIL sanity", l.a, "||", l.b, JSON.stringify(q).slice(0, 300)); }
    if (q.foundB) { const heard = (q.wB[0] - q.bPos) / q.r; if (!(heard >= -.031) || !(q.bFade >= -heard)) { bad++; console.log("FAIL B word before its entry", heard, q.bFade); } }
    { const xa = ((T.xOf(g1, q.cut) % 4) + 4) % 4, xb = ((T.xOf(g2, q.bPos) % 4) + 4) % 4;   /* on the one, both sides */
      if (Math.min(xa, 4 - xa) > .01 || Math.min(xb, 4 - xb) > .01 || q.onBeat !== "1") { bad++; console.log("FAIL not on the one", xa, xb, q.onBeat); } }
    if (!(q.aOut <= q.cut + 1e-9) || !(q.aOut >= sA + .55 - .061)) { bad++; console.log("FAIL A out", q.aOut, q.cut); }
  }
}
gaps.sort((x, y) => x - y);
chk(`all curated links plan (${okc}/${n}), synced ${synced}, cut on ${JSON.stringify(ons)}, median gap ${gaps[gaps.length >> 1]} s`, okc >= n * .9);
console.log(bad ? "TIMING_FAIL " + bad : "TIMING_OK " + ok);
process.exit(bad ? 1 : 0);
