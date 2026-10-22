/* calibrate MashMatch on the real measured data: node calib.js <docs/mashup-lab dir> <data.json> */
const fs = require("fs"), path = require("path");
require(path.resolve(__dirname, "../match.js"));
const M = globalThis.MashMatch, D = process.argv[2], DATA = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const J = f => JSON.parse(fs.readFileSync(path.join(D, f), "utf8"));
const an = J("analysis.json").map, li = J("listen.json").map, beats = J("beats.json").map, pv = J("previews.json").map;
function fnv(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return ("0000000" + (h >>> 0).toString(16)).slice(-8); }
M.seed({ an, li, beats, previews: pv, hash: fnv });
const meas = DATA.filter(t => M.track(t));
console.log("tracks", DATA.length, "measured", meas.length);
const byG = {}; meas.forEach(t => (byG[t.g] = byG[t.g] || []).push(t));
console.log(Object.entries(byG).map(([g, a]) => g + ":" + a.length).join(" "));
function camRel(a, b) { const na = parseInt(a), la = a.slice(-1), nb = parseInt(b), lb = b.slice(-1); if (a === b) return "same"; if (la === lb && (Math.abs(na - nb) === 1 || Math.abs(na - nb) === 11)) return "adj"; if (na === nb) return "rel"; return null; }
let res = [], t0 = Date.now(), n = 0;
const V = ["mizr", "ilpop", "pop", "rnb", "hiphop", "latin", "regg", "afro", "dancehall"], B = ["house", "techhouse", "afrohouse", "techno", "edm", "amapiano", "ukg"];
for (const gv of V) for (const gb of B) for (const v of byG[gv] || []) for (const b of byG[gb] || []) {
  n++; const m = M.pair(v, b, { maxDiff: .06 }); if (!m || !m.ok) continue;
  res.push({ v, b, m, cat: camRel(v.k, b.k), mk: m.keyV && m.keyB ? camRel(m.keyV, m.keyB) : null });
}
console.log("pairs evaluated", n, "ok", res.length, "ms", Date.now() - t0, "per pair us", Math.round((Date.now() - t0) * 1000 / n));
const q = (a, p) => { const s = a.slice().sort((x, y) => x - y); return s[Math.floor(p * (s.length - 1))]; };
const sc = res.map(r => r.m.score), hn = res.map(r => r.m.Hn), O = res.map(r => r.m.O);
console.log("score q10/50/90", q(sc, .1), q(sc, .5), q(sc, .9), "Hn q10/50/90", q(hn, .1).toFixed(2), q(hn, .5).toFixed(2), q(hn, .9).toFixed(2), "O q50/90", q(O, .5).toFixed(2), q(O, .9).toFixed(2));
for (const k of ["same", "adj", "rel", null]) { const a = res.filter(r => r.mk === k && r.m.s === 0); if (a.length) console.log("measured-key rel", k, "(no shift) n", a.length, "Hn median", q(a.map(r => r.m.Hn), .5).toFixed(3), "score median", q(a.map(r => r.m.score), .5)); }
for (const s of [-2, -1, 0, 1, 2]) { const a = res.filter(r => r.m.s === s); console.log("shift", s, "n", a.length, "Hn med", a.length ? q(a.map(r => r.m.Hn), .5).toFixed(3) : "-"); }
console.log(">=70:", res.filter(r => r.m.score >= 70).length, ">=80:", res.filter(r => r.m.score >= 80).length, ">=90:", res.filter(r => r.m.score >= 90).length);
const show = r => `${r.m.score} Hn${r.m.Hn.toFixed(2)} s${r.m.s} c${r.m.cents} O${r.m.O.toFixed(2)} d${(r.m.d * 100).toFixed(1)} | ${r.v.t} (${r.v.k}/${r.m.keyV}) × ${r.b.t} (${r.b.k}/${r.m.keyB}) a${r.m.aBar} b${r.m.bBar} cleanB ${r.m.plan.cleanB}`;
res.sort((x, y) => y.m.score - x.m.score);
console.log("TOP"); res.slice(0, 12).forEach(r => console.log(" ", show(r)));
console.log("BOTTOM"); res.slice(-8).forEach(r => console.log(" ", show(r)));
const mizrHouse = res.filter(r => r.v.g === "mizr" && r.b.g === "house");
console.log("mizr×house ok", mizrHouse.length, ">=70", mizrHouse.filter(r => r.m.score >= 70).length);
mizrHouse.slice(0, 8).forEach(r => console.log(" ", show(r)));
