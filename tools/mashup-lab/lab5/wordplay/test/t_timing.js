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
chk("cut on A's beat 3 right after the word (11.10 s)", near(p.cut, 11.1, 1e-3) && p.onBeat === "3", "cut " + p.cut + " " + p.onBeat);
chk("B enters at 7.50 s (its own beat 3), its word 0.52 s after the cut", near(p.bPos, 7.5, 1e-3) && near((p.wB[0] - p.bPos) / p.r, .52, .01), "bPos " + p.bPos);
chk("gap between the words 0.8 s", near(p.gap, .8, .01), "gap " + p.gap);
chk("A starts on a bar line 4 bars before its word's bar", near(p.aStart, T.tOf(gA, 20 - 16), 1e-3), "aStart " + p.aStart);
chk("B's bar lines on A's bar lines after the cut", (() => { const xB = T.xOf(gB, p.bPos), xA = T.xOf(gA, p.cut); return near(((xB - xA) % 4 + 4) % 4, 0, 1e-6); })());
chk("summary in Hebrew", p.summary.length >= 3 && /B/.test(p.summary[0]), p.summary.join(" | "));

// a bar line right after the word wins
p = T.plan(link, { gA, gB: { bpm: 120, b0: .1, db: 0 }, durA: 30, durB: 30 }, { wt: { a: [[9.4, 10.05, .9, 1]], b: [[6.25, 6.7, .9, 1]] } });
chk("cut lands on the 1 when it is within a beat after the word", p.ok && p.onBeat === "1" && near(p.cut, 10.1, 1e-3), p.cut + " " + p.onBeat);
chk("then B's word (on its beat 1.5 of the bar) follows 0.15 s later", near((p.wB[0] - p.bPos) / p.r, .15, .01), String((p.wB[0] - p.bPos) / p.r));

// tempos too far apart
p = T.plan(link, { gA: { bpm: 95, b0: .2, db: 0 }, gB: { bpm: 126, b0: .1, db: 0 }, durA: 30, durB: 30 }, { wt: { a: [[12.0, 12.6, .9, 1]], b: [[9.6, 10.1, .9, 1]] } });
chk("no stretch when the tempos are far (95 vs 126): echo style, B native", p.ok && !p.synced && p.r === 1 && p.style === "echo", JSON.stringify({ s: p.synced, r: p.r, st: p.style }));
chk("B enters on its own beat before its word", (() => { const x = T.xOf({ bpm: 126, b0: .1, db: 0 }, p.bPos); return near(x, Math.round(x), 1e-2) && p.bPos < 9.6; })(), "bPos " + p.bPos);

// half / double time
p = T.plan(link, { gA: { bpm: 70, b0: .2, db: 0 }, gB: { bpm: 140, b0: .1, db: 2 }, durA: 30, durB: 30 }, { wt: { a: [[14.0, 14.5, .9, 1]], b: [[12.1, 12.5, .9, 1]] } });
chk("70 vs 140: synced with q = 2, no stretch", p.ok && p.synced && p.q === 2 && near(p.r, 1, 1e-3), JSON.stringify({ q: p.q, r: p.r }));

// key shift chosen
p = T.plan(Object.assign({}, link, { technique: "double" }), { gA, gB, durA: 30, durB: 30 }, { wt: { a: [[10.25, 10.82, .9, 1]], b: [[8.0, 8.6, .9, 1]] },
  anA: { key: "8A", ks: .8, km: "e" }, anB: { key: "10A", ks: .8, km: "e" } });
chk("blend asks for a key fit: 10A → 8A is -2 semitones", p.ok && p.semis === -2 && p.rel === "same", JSON.stringify({ s: p.semis, rel: p.rel, k: p.keyB2 }));

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
    if (q.synced && q.foundB) { const heard = (q.wB[0] - q.bPos) / q.r; if (!(heard >= .03)) { bad++; console.log("FAIL B word before the cut", heard); } }
  }
}
gaps.sort((x, y) => x - y);
chk(`all curated links plan (${okc}/${n}), synced ${synced}, cut on ${JSON.stringify(ons)}, median gap ${gaps[gaps.length >> 1]} s`, okc >= n * .9);
console.log(bad ? "TIMING_FAIL " + bad : "TIMING_OK " + ok);
process.exit(bad ? 1 : 0);
