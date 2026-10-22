/* MashMatch unit test on synthetic analysis: node test/t_match.js */
require("../match.js");
const M = globalThis.MashMatch;
let ok = 0, n = 0;
function chk(name, c, info) { n++; if (c) ok++; console.log((c ? "OK   " : "FAIL ") + name + (info !== undefined ? "  " + JSON.stringify(info) : "")); }
const HEX = "0123456789abcdef";
function hexBar(pcs, strong) { let s = ""; for (let i = 0; i < 12; i++) s += pcs.includes(i) ? (i === pcs[0] && strong ? "f" : "c") : "1"; return s; }
function track(o) {               /* o: { bars: [[pcs]...] harmony, vbars: [[pcs]] vocal notes, vlev: digit per bar, bpm, t0 } */
  const nb = o.bars.length, hb = o.bars.map(p => hexBar(p, true)).join(""), vb = (o.vbars || o.bars).map((p, i) => (o.vlev[i] ? hexBar(p, false) : "000000000000")).join("");
  const vr = o.vlev.map(x => String(x).repeat(4)).join(""), voc = o.vlev.map(x => String(Math.min(9, x + 2)).repeat(4)).join("");
  const hcv = new Array(12).fill(0); o.bars.forEach(p => p.forEach(i => hcv[i]++)); const mx = Math.max(...hcv);
  const vcv = new Array(12).fill(0); (o.vbars || o.bars).forEach((p, i) => o.vlev[i] && p.forEach(k => vcv[k]++)); const mv = Math.max(...vcv) || 1;
  return { an: { h: "x", key: o.key || "8A", ks: .8, t0: o.t0 || .5, voc, hc: hcv.map(x => Math.round(9 * x / mx)).join(""), vc: vcv.map(x => Math.round(9 * x / mv)).join(""), vdb: -6, vs: .6, sec: [0, 4], tc: o.tc || 0, vp: o.vp || 60, rp: "900000500000900000900000" },
    li: { h: "x", hb, vb, vr }, beat: [o.bpm || 124, o.t0 || .5, 0, .9, "x"] };
}
const Am = [9, 0, 4], F = [5, 9, 0], C = [0, 4, 7], G = [7, 11, 2], Bm = [11, 2, 6], G2 = [7, 11, 2], D = [2, 6, 9], A = [9, 1, 4], CSm = [1, 4, 8], Fs = [6, 10, 1];
const prog = [Am, F, C, G, Am, F, C, G, Am, F, C, G];
const lev = [0, 0, 6, 7, 7, 6, 7, 7, 6, 7, 0, 0];
const T = {
  V: track({ bars: prog, vlev: lev, vp: 58 }),
  Bsame: track({ bars: prog, vlev: new Array(12).fill(0) }),
  Btone: track({ bars: [Bm, G2, D, A, Bm, G2, D, A, Bm, G2, D, A], vlev: new Array(12).fill(0), key: "10A" }),
  Bfar: track({ bars: [CSm, A, [4, 8, 11], [11, 3, 6], CSm, A, [4, 8, 11], [11, 3, 6], CSm, A, [4, 8, 11], [11, 3, 6]], vlev: new Array(12).fill(0), key: "12A" }),
  Bsing: track({ bars: prog, vlev: new Array(12).fill(8) }),
  Bfast: track({ bars: prog, vlev: new Array(12).fill(0), bpm: 150 }),
  Btuned: track({ bars: prog, vlev: new Array(12).fill(0), tc: -30 }),
};
const an = {}, li = {}, beats = {}, previews = {};
for (const k in T) { const key = k + " | x"; an[key] = T[k].an; li[key] = T[k].li; beats[key] = T[k].beat; previews[key] = { p: "u" }; }
M.seed({ an, li, beats, previews, hash: () => "x" });
const t = k => ({ t: k, a: "x" });
const same = M.pair(t("V"), t("Bsame")), tone = M.pair(t("V"), t("Btone")), far = M.pair(t("V"), t("Bfar")), sing = M.pair(t("V"), t("Bsing")), fast = M.pair(t("V"), t("Bfast")), tuned = M.pair(t("V"), t("Btuned"));
chk("same chords: no shift, high score", same.ok && same.s === 0 && same.score >= 95, [same.score, same.s, same.Hn]);
chk("same chords: the vocal starts where it starts singing (bar 2), over the same chords of B (bar 2)", same.aBar === 2 && same.bBar === 2, [same.aBar, same.bBar]);
chk("B a whole tone up: vocal shifted +2", tone.ok && tone.s === 2, [tone.score, tone.s, tone.Hn]);
chk("shifted pair scores below the unshifted one", tone.score < same.score, [tone.score, same.score]);
chk("B a major third away (out of ±2): low score", far.ok && far.score < tone.score - 8, [far.score, far.s, far.Hn]);
chk("B sings in the same bars: clash lowers the score, B gets cleaned", sing.ok && sing.score <= same.score - 15 && sing.plan.cleanB === true && same.plan.cleanB === false, [sing.score, sing.O]);
chk("tempo 124 vs 150: not a pair", fast && fast.ok === false && fast.why === "tempo", fast);
chk("B tuned 30 cents low: the vocal follows (−0.3 semitone)", tuned.ok && tuned.cents === -30 && Math.abs(tuned.plan.semis + .3) < 1e-9, [tuned.cents, tuned.plan.semis]);
chk("plan times: entry at the bar lines (t0 + 4 beats per bar)", Math.abs(same.plan.aAt - (.5 + 4 * 2 * 60 / 124)) < 1e-9 && same.plan.lead >= 0, same.plan);
chk("Hebrew reasons", Array.isArray(same.why) && same.why.length >= 2 && /[א-ת]/.test(same.why[0]), same.why);
const t0 = Date.now(); for (let i = 0; i < 2000; i++) { M.seed({ an, li, beats, previews, hash: () => "x" }); M.pair(t("V"), t("Btone")); } const ms = (Date.now() - t0) / 2000;
chk("fast enough (< 0.4 ms per pair here)", ms < .4, ms);
console.log(ok + "/" + n + (ok === n ? " MATCH_OK" : " MATCH_FAIL"));
process.exit(ok === n ? 0 : 1);
