"""Decoded-buffer playback: time-stretch quality + sample-accurate beat sync, measured on the AUDIO of each deck.

Each deck's signal (after the stretch, before the vocal clean-up) is recorded inside the page with a
ScriptProcessor tap; the kick-band onset envelopes of the two decks are cross-correlated, so "the kicks fall
together" is measured, not inferred from engine state.

usage: python3 t_buf.py [scenario-filter]          prints PASS/FAIL lines + BUF_OK / BUF_FAIL
"""
import base64, functools, http.server, json, os, sys, threading, time
import numpy as np
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
from rangehttp import RangeHandler

ENGINE = open(os.path.join(HERE, "..", "..", "lab5", "engine.js"), encoding="utf-8").read()
TR = json.load(open(os.path.join(HERE, "truth.json")))
PORT, NPORT = 8874, 8875           # with CORS, and a server without CORS (fallback path)
FILT = sys.argv[1] if len(sys.argv) > 1 else ""
RES = []


class H(RangeHandler):
    cors = True
    def end_headers(self):
        if self.cors: self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store"); super().end_headers()
    def log_message(self, *a): pass
class HN(H): cors = False


def check(name, ok, info=""):
    RES.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  " + str(info)[:600]))


SETUP = """
window.E = MashEngine.create({ net: true, root: document.body });
window.T = {};
for (const [k, bpm, g, f] of [["x",124,"house"],["y",126,"house"],["z",92,"hiphop"],["w",125,"house"],["h",62,"hiphop"],["x2",123,"house","x"]]) T[k] = {i: k.charCodeAt(0) + k.length, t: k.toUpperCase(), a: "Test", g, bpm, k: "8A", y: 2020, f: f || k};
window.BASE = location.origin;
window.seedAll = (base) => { const m = {}; for (const k of Object.keys(T)) m[T[k].t + " | Test"] = {p: base + "/" + T[k].f + ".wav"}; MashEngine.seed(m); };
seedAll(BASE); E.hintCors(true);
window.REC = null;
window.record = (secs) => {               /* tap both decks' raw signal (stretched audio, before clean-up/EQ) */
  const c = E._ctx(), out = {A: [], B: []}, sps = [];
  for (const s of ["A", "B"]) {
    const sp = c.createScriptProcessor(4096, 2, 1), g = c.createGain(); g.gain.value = 0;
    sp.onaudioprocess = e => { const x = e.inputBuffer.getChannelData(0), y = e.inputBuffer.numberOfChannels > 1 ? e.inputBuffer.getChannelData(1) : x, m = new Float32Array(x.length);
      for (let i = 0; i < x.length; i++) m[i] = .5 * (x[i] + y[i]); out[s].push([e.playbackTime, m]); };
    E._nodes(s).inp.connect(sp); sp.connect(g); g.connect(c.destination); sps.push([s, sp]);
  }
  window.REC = {out, sps, sr: c.sampleRate};
  return new Promise(res => setTimeout(() => {
    for (const [s, sp] of sps) { try { E._nodes(s).inp.disconnect(sp); } catch (e) {} sp.disconnect(); }
    const pack = s => { const ch = out[s]; if (!ch.length) return null; const n = ch.reduce((a, b) => a + b[1].length, 0), all = new Int16Array(n); let o = 0;
      for (const [, m] of ch) { for (let i = 0; i < m.length; i++) all[o + i] = Math.max(-32767, Math.min(32767, Math.round(m[i] * 32767))); o += m.length; }
      let bin = ""; const u8 = new Uint8Array(all.buffer); for (let i = 0; i < u8.length; i += 8192) bin += String.fromCharCode.apply(null, u8.subarray(i, i + 8192));
      return {t0: ch[0][0], b64: btoa(bin)}; };
    res({sr: c.sampleRate, A: pack("A"), B: pack("B")});
  }, secs * 1000));
};
const b = document.createElement("button"); b.id = "act"; b.textContent = "act"; document.body.appendChild(b);
b.onclick = () => { E.gesture(); (window.__act || (() => {}))(); };
"""


def page(br, throttle=0):
    ctx = br.new_context(); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type in ("error", "warning") and "MashEngine" in m.text else None)
    pg.goto(f"http://127.0.0.1:{PORT}/index.html"); pg.add_script_tag(content=ENGINE); pg.evaluate(SETUP)
    if throttle:
        cdp = ctx.new_cdp_session(pg); cdp.send("Emulation.setCPUThrottlingRate", {"rate": throttle})
    return ctx, pg, errs


def act(pg, js):
    pg.evaluate("js => { window.__act = new Function(js); }", js); pg.click("#act")


def decode_rec(r):
    sr = r["sr"]; out = {}
    for s in "AB":
        if not r[s]: out[s] = None; continue
        x = np.frombuffer(base64.b64decode(r[s]["b64"]), dtype="<i2").astype(np.float32) / 32767
        out[s] = (r[s]["t0"], x)
    return sr, out


def kick_env(x, sr, hop):
    """kick-band onset strength: one-pole low-pass ~120 Hz energy per hop, positive log-difference"""
    a = np.exp(-2 * np.pi * 120 / sr); y = np.empty_like(x); acc = 0.0
    # vectorised one-pole via lfilter-like recursion (scipy-free): process in python is slow, so use cumulative trick
    b = 1 - a
    y = np.zeros_like(x)
    for i0 in range(0, len(x), 65536):  # chunked recursion
        seg = x[i0:i0 + 65536]
        out = np.empty_like(seg)
        for i, v in enumerate(seg):
            acc = a * acc + b * v; out[i] = acc
        y[i0:i0 + 65536] = out
    n = len(y) // hop
    e = np.log1p(1e4 * np.add.reduceat(y[: n * hop] ** 2, np.arange(0, n * hop, hop)))
    return np.maximum(0, np.diff(e, prepend=e[0]))


def hf_env(x, sr):
    """onsets of claps / snares / hats: high-passed (first difference) energy per 1 ms, positive log-difference"""
    d = np.diff(x, prepend=x[0]); hop = max(1, sr // 1000); n = len(d) // hop
    e = np.log1p(1e5 * np.add.reduceat(d[: n * hop] ** 2, np.arange(0, n * hop, hop)))
    return np.maximum(0, np.diff(e, prepend=e[0]))


def hits(e, frac=.25):
    """onset times (ms) where the hit envelope peaks above a share of its loud peaks"""
    th = np.percentile(e, 99) * frac
    pk = [j for j in range(1, len(e) - 1) if e[j] > th and e[j] >= e[j - 1] and e[j] > e[j + 1]]
    out = []
    for j in pk:
        if not out or j - out[-1] > 25: out.append(j)
    return np.array(out, float)


def kick_lag_ms(rec, beat_s):
    """per-hit timing of deck A against deck B from the recorded audio (same clock): every clap / snare / hat onset of
    A is paired with B's nearest one (within 40 ms). Returns (median ms, 90th percentile of |offset| ms, pairs).
    The low band is not used: a stretched bass smears its envelope, and the vocal deck's bass is filtered out anyway."""
    sr, d = decode_rec(rec)
    if not d["A"] or not d["B"]: return None
    (tA, xA), (tB, xB) = d["A"], d["B"]
    off = int(round((tA - tB) * sr))      # >0: A's recording starts later
    if off > 0: xB = xB[off:]
    elif off < 0: xA = xA[-off:]
    n = min(len(xA), len(xB)); xA, xB = xA[:n], xB[:n]
    nzA = np.argmax(np.abs(xA) > 1e-3); nzB = np.argmax(np.abs(xB) > 1e-3); s0 = max(nzA, nzB) + int(.3 * sr)
    xA, xB = xA[s0:], xB[s0:]
    if len(xA) < sr * 2: return None
    hA, hB = hits(hf_env(xA, sr)), hits(hf_env(xB, sr))
    if len(hA) < 4 or len(hB) < 4: return None
    o = []
    for t in hA:
        j = int(np.argmin(np.abs(hB - t)))
        if abs(hB[j] - t) <= 40: o.append(t - hB[j])
    if len(o) < 4: return None
    o = np.array(o)
    return (float(np.median(o)), float(np.percentile(np.abs(o), 90)), len(o))


def lag_ok(m, med=6, p90=16):   # p90 noise floor of this measurement is ~13 ms even with no stretch at all
    return m is not None and abs(m[0]) <= med and m[1] <= p90


def gaps_ms(rec, side, after_s=0.4):
    """longest run of digital silence inside a deck's recording after it started (a dropout would show here)"""
    sr, d = decode_rec(rec)
    if not d[side]: return None
    _, x = d[side]
    nz = np.flatnonzero(np.abs(x) > 1e-4)
    if not len(nz): return 9999
    x = x[nz[0] + int(after_s * sr): nz[-1]]
    z = np.abs(x) < 1e-5
    best = cur = 0
    for v in z:
        cur = cur + 1 if v else 0
        if cur > best: best = cur
    return round(best / sr * 1000, 1)


def sc_wsola(br):
    ctx, pg, errs = page(br)
    r = pg.evaluate("""() => {
      const sr = 44100, N = sr * 10, x = new Float32Array(N);
      for (let i = 0; i < N; i++) x[i] = .3 * Math.sin(2 * Math.PI * 220 * i / sr) + .2 * Math.sin(2 * Math.PI * 1000 * i / sr);
      for (let c = 0; c < 20; c++) { const k = Math.round((.25 + c * .5) * sr); for (let j = 0; j < 200; j++) x[k + j] += .8 * Math.exp(-j / 30) * (j % 2 ? 1 : -1); }
      const res = {};
      for (const r of [.9, .94, .97, 1.03, 1.06, 1.1]) {
        const t0 = performance.now(), y = MashEngine._wsola([x], r, sr)[0], ms = performance.now() - t0;
        /* pitch: zero crossings of the 220 Hz component region (low-passed by averaging) over 1-9 s */
        const lp = new Float32Array(y.length); let a = 0; for (let i = 0; i < y.length; i++) { a = a * .97 + y[i] * .03; lp[i] = a; }
        let zc = 0; const i0 = Math.round(1 * sr), i1 = Math.round(Math.min(9, y.length / sr - .5) * sr);
        for (let i = i0 + 1; i < i1; i++) if ((lp[i - 1] < 0) !== (lp[i] < 0)) zc++;
        const f = zc / 2 / ((i1 - i0) / sr);
        /* click onsets: where |y| jumps above .5 */
        const on = []; for (let i = 1; i < y.length; i++) if (Math.abs(y[i]) > .55 && Math.abs(y[i - 1]) <= .55 && (!on.length || i - on[on.length - 1] > sr * .2)) on.push(i);
        const err = on.map((i, c) => Math.abs(i / sr - (.25 + c * .5) / r) * 1000);
        /* clicks / discontinuities between the clicks: largest sample step away from transients */
        let step = 0; for (let i = 1; i < y.length; i++) { const near = on.some(o => i >= o - 50 && i < o + 400); if (!near) step = Math.max(step, Math.abs(y[i] - y[i - 1])); }
        res[r] = {len: y.length, want: Math.round(N / r), f, clicks: on.length, maxOnsetErr: Math.max(...err), step, ms};
      }
      const big = new Float32Array(48000 * 30); for (let i = 0; i < big.length; i++) big[i] = Math.sin(i * .05) * .3;
      const t0 = performance.now(); MashEngine._wsola([big, big], 1.03, 48000); res.perf30s = performance.now() - t0;
      return res;
    }""")
    for k, v in r.items():
        if k == "perf30s": continue
        rate = float(k)
        check(f"stretch ×{rate}: length = N / rate", abs(v["len"] - v["want"]) <= 2, v)
        check(f"stretch ×{rate}: pitch kept (220 Hz ± 1.5 %)", abs(v["f"] - 220) / 220 < .015, v)
        check(f"stretch ×{rate}: every transient kept, on time (≤ 12 ms)", v["clicks"] == 20 and v["maxOnsetErr"] <= 12, v)
        check(f"stretch ×{rate}: no clicks between transients", v["step"] < .08, v)
    check("stretch: 30 s stereo @ 48 kHz in < 400 ms (desktop; ≈ 2× on a phone)", r["perf30s"] < 400, r["perf30s"])
    print("   wsola:", {k: (v if k == "perf30s" else {kk: round(vv, 3) if isinstance(vv, float) else vv for kk, vv in v.items()}) for k, v in r.items()})
    check("stretch: no engine errors", not errs, errs[:3]); ctx.close()


def sc_ride(br):
    """word play, tempos 10-30 % apart: B is stretched to A's tempo, holds it, then glides back to its own (tempo ride)"""
    ctx, pg, errs = page(br)
    r = pg.evaluate("""() => {
      const sr = 44100, N = sr * 20, x = new Float32Array(N);
      for (let i = 0; i < N; i++) x[i] = .3 * Math.sin(2 * Math.PI * 220 * i / sr);
      /* clicks: a decaying 2.5 kHz burst (a pure Nyquist buzz would not survive the key-shift resampler) */
      const clicks = []; for (let c = 0; c < 39; c++) { const t = .25 + c * .5, k = Math.round(t * sr); clicks.push(t); for (let j = 0; j < 300; j++) x[k + j] += .9 * Math.exp(-j / 40) * Math.sin(2 * Math.PI * 2500 * j / sr + Math.PI / 2); }
      const out = (rd, i) => { const o1 = rd.i1 / rd.r0; if (i <= rd.i1) return i / rd.r0; const T2 = 2 * (rd.i2 - rd.i1) / (rd.r0 + 1); if (i >= rd.i2) return o1 + T2 + (i - rd.i2);
        const a = (1 - rd.r0) / (2 * T2), b = rd.r0, c = -(i - rd.i1); return o1 + (-b + Math.sqrt(b * b - 4 * a * c)) / (2 * a); };
      const res = {};
      for (const [r0, semis] of [[.8, 0], [1.25, 0], [.8, 1]]) {
        const rd = { r0, i1: 6, i2: 14 }, t0 = performance.now(), y = MashEngine._shift([x], r0, semis, sr, { i1: rd.i1, i2: rd.i2 })[0], ms = performance.now() - t0;
        const onI = []; for (let i = 1; i < y.length; i++) if (Math.abs(y[i]) > .55 && Math.abs(y[i - 1]) <= .55 && (!onI.length || i - onI[onI.length - 1] > sr * .2)) onI.push(i);
        const on = onI.map(i => i / sr), want = clicks.map(t => out(rd, t)).filter(t => t < y.length / sr - .05);
        const sg = want.map(w => { let b = 1e9; for (const o of on) if (Math.abs(o - w) < Math.abs(b)) b = o - w; return b * 1000; });
        const med = a => a.slice().sort((p, q) => p - q)[a.length >> 1], o1 = rd.i1 / r0, o2 = out(rd, rd.i2);
        const H = sg.filter((e, i) => want[i] < o1 - .1), P = sg.filter((e, i) => want[i] > o2 + .1), G = sg.filter((e, i) => want[i] >= o1 - .1 && want[i] <= o2 + .1);
        const offH = med(H), offP = med(P), jH = Math.max(...H.map(e => Math.abs(e - offH))), jP = Math.max(...P.map(e => Math.abs(e - offP)));
        const lo = Math.min(offH, offP) - 5, hi = Math.max(offH, offP) + 5, gOut = G.filter(e => e < lo || e > hi).length;
        const off = offH, err = sg.map(e => Math.abs(e - offH));
        const worst = sg.map((e, i) => [Math.round(e * 10) / 10, Math.round(want[i] * 100) / 100]).sort((p, q) => Math.abs(q[0]) - Math.abs(p[0])).slice(0, 4);
        /* pitch over the last 3 s (rate 1 there): 220 Hz × 2^(semis/12) */
        const lp = new Float32Array(y.length); let a = 0; for (let i = 0; i < y.length; i++) { a = a * .97 + y[i] * .03; lp[i] = a; }
        let zc = 0; const i0 = Math.round((y.length / sr - 3.2) * sr), i1 = Math.round((y.length / sr - .2) * sr);
        for (let i = i0 + 1; i < i1; i++) if ((lp[i - 1] < 0) !== (lp[i] < 0)) zc++;
        res[r0 + "/" + semis] = { len: y.length / sr, wantLen: out(rd, 20), clicks: on.length, want: want.length, maxErr: Math.max(...err), off, offP, jH, jP, gOut, nH: H.length, nP: P.length, nG: G.length, worst, f: zc / 2 / ((i1 - i0) / sr), fWant: 220 * Math.pow(2, semis / 12), ms };
      }
      return res;
    }""")
    for k, v in r.items():
        check(f"ride {k}: length follows the ride map (± 5 ms)", abs(v["len"] - v["wantLen"]) <= .005, v)
        # WSOLA copies 60 ms segments at rate 1, so at a 20-25 % stretch every hit sits ~(1 - r) x 50 ms early: a constant
        # offset that the word play's fineLag removes at the cut (it lines B's hits up with A's); what must hold is the beat
        # spacing, i.e. every hit within a few ms of the map once that constant is removed
        # (the offset is ~(1 - r) x 50 ms, so it fades to 0 along the glide: inaudible, B plays alone by then)
        lim = 4 if k.endswith("/0") else 7
        check(f"ride {k}: steady beats while B holds A's tempo (offset ≤ 15 ms, each beat ≤ {lim} ms from it)", v["clicks"] >= v["want"] and v["nH"] >= 6 and abs(v["off"]) <= 15 and v["jH"] <= lim, v)
        check(f"ride {k}: on time after the glide (offset ≤ 4 ms, each beat ≤ {lim} ms)", v["nP"] >= 6 and abs(v["offP"]) <= 4 and v["jP"] <= lim, v)
        check(f"ride {k}: during the glide every beat stays between the two (± 5 ms)", v["nG"] >= 10 and v["gOut"] == 0, v)
        check(f"ride {k}: pitch kept after the glide", abs(v["f"] - v["fWant"]) / v["fWant"] < .015, v)
    print("   ride:", {k: {kk: round(vv, 3) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in r.items()})
    check("ride: no engine errors", not errs, errs[:3]); ctx.close()


def seed_truth(pg, keys, err=None):
    """beats.json the way GitHub Actions writes it, from the ground truth (exact grids); err = {key: b0 error in s}"""
    m = {}
    for k in keys:
        t = TR[k.rstrip("2")]
        m[k.upper() + " | Test"] = [t["bpm"], round(t["b0"] + (err or {}).get(k, 0), 4), t["d"], 0.95, None]
    pg.evaluate("""m => { for (const k of Object.keys(m)) { const t = Object.values(T).find(x => x.t + " | Test" === k); m[k][4] = MashEngine._hash(BASE + "/" + t.f + ".wav"); } MashEngine.seedBeats(m); }""", m)


def truth_phase_ms(st, a, b, q=1):
    """bar-phase error from the engine's clock mapping + ground truth (A follower vs B)"""
    A, B = st["A"]["buf"], st["B"]["buf"]
    T = max(A["now"], A["t0"], B["t0"]) + 0.5
    pa = (A["o0"] + max(0, T - A["t0"])) * A["sr"]; pb = (B["o0"] + max(0, T - B["t0"])) * B["sr"]
    ta, tb = TR[a.rstrip("2")], TR[b.rstrip("2")]; M = 8 if q == .5 else 4
    xa = ((pa - ta["b0"]) / ta["p"] - ta["d"]) / q; xb = (pb - tb["b0"]) / tb["p"] - tb["d"]
    e = (xa - xb) % M
    if e >= M / 2: e -= M
    return e * tb["p"] / B["sr"] * 1000


def sc_pair(br, tag, a, b, rates, server, q=1, throttle=0, err=None):
    ctx, pg, errs = page(br, throttle)
    if server: seed_truth(pg, [a, b], err)
    t0 = time.time()
    act(pg, f"E.loadPair(T.{a}, T.{b}, {json.dumps(rates)}); E.playBoth();")
    ok = False
    while time.time() - t0 < 6:
        st = pg.evaluate("E.state()")
        if st["A"]["playing"] and st["B"]["playing"]: ok = True; break
        pg.wait_for_timeout(50)
    lat = time.time() - t0
    st = pg.evaluate("E.state()"); dbg = pg.evaluate("E._dbg()")
    check(f"{tag}: both decks play from decoded buffers", ok and st["A"]["bm"] and st["B"]["bm"], [st["A"].get("bm"), st["B"].get("bm"), st["A"]["kind"], dbg["A"]["buf"]])
    check(f"{tag}: sound within 1.5 s of the tap (local files)", lat < 1.5, round(lat, 2))
    pg.wait_for_timeout(300)
    st = pg.evaluate("E.state()"); dbg = pg.evaluate("E._dbg()")
    check(f"{tag}: beat grid source = {'server' if server else 'measured in the page'}", st["A"]["grid"] and st["A"]["grid"]["src"] == ("server" if server else "local") and st["B"]["grid"]["src"] == ("server" if server else "local"), [st["A"]["grid"], st["B"]["grid"]])
    check(f"{tag}: synced + locked", st["A"]["sync"] and st["B"]["sync"] and st["beat"] == "locked", [st["A"]["sync"], st["B"]["sync"], st["beat"]])
    ph = truth_phase_ms(dbg, a, b, q)
    check(f"{tag}: bar lines aligned (|error| ≤ 10 ms vs ground truth; the audio check below is the stricter one)", abs(ph) <= 10, [round(ph, 2), "fine shift ms", round(dbg["A"]["buf"].get("fine", 0) * 1000, 1)])
    rec = pg.evaluate("record(6)")
    lag = kick_lag_ms(rec, TR[b.rstrip("2")]["p"])
    check(f"{tag}: recorded hits of both decks coincide (median ≤ 6 ms, 90 % within 16 ms)", lag_ok(lag), lag)
    g = [gaps_ms(rec, "A"), gaps_ms(rec, "B")]
    check(f"{tag}: no dropouts in either deck's audio", all(x is not None and x < 5 for x in g), g)
    check(f"{tag}: no engine errors", not errs, errs[:3])
    print(f"   {tag}: start {lat:.2f} s, rates A {dbg['A']['buf']['sr']} B {dbg['B']['buf']['sr']}, phase {ph:.2f} ms (fine shift {dbg['A']['buf'].get('fine', 0) * 1000:.0f} ms), hit lag {lag} ms, gaps {g}")
    return ctx, pg, errs


def sc_both(br, server=True, throttle=0):
    tag = ("server grids" if server else "page-measured grids") + (f", CPU ×{throttle}" if throttle else "")
    ctx, pg, errs = sc_pair(br, tag, "x", "y", {"A": 125 / 124, "B": 125 / 126}, server, throttle=throttle)
    ctx.close()


def sc_ops(br):
    """swap, seek, pause/resume, loop restart — the sync must survive all of them, the other deck untouched"""
    ctx, pg, errs = sc_pair(br, "ops base", "x", "y", {"A": 125 / 124, "B": 125 / 126}, True)
    seed_truth(pg, ["w"])
    a0 = pg.evaluate("E._dbg().A.buf")
    pg.evaluate("window.__swapRec = record(4)")
    act(pg, "E.loadDeck('B', T.w, {A: 124.5/124, B: 124.5/125});")
    pg.wait_for_timeout(2500)
    st, dbg = pg.evaluate("E.state()"), pg.evaluate("E._dbg()")
    rec0 = pg.evaluate("window.__swapRec")
    gA = gaps_ms(rec0, "A", after_s=0.1)
    check("swap: the vocal kept playing without a gap (one seamless tempo change at the entry)", st["A"]["playing"] and gA is not None and gA < 5, [st["A"]["playing"], gA, a0["sr"], dbg["A"]["buf"]["sr"]])
    check("swap: the new beat plays at its own tempo (drums and bass never stretched)", dbg["B"]["buf"]["sr"] == 1, dbg["B"]["buf"])
    check("swap: the new beat joined synced", st["B"]["playing"] and st["B"]["sync"] and st["beat"] == "locked", [st["B"]["playing"], st["B"]["sync"], st["beat"]])
    ph = truth_phase_ms(dbg, "x", "w")
    check("swap: bar lines aligned (≤ 8 ms)", abs(ph) <= 8, round(ph, 2))
    rec = pg.evaluate("record(4)"); lag = kick_lag_ms(rec, TR["w"]["p"])
    check("swap: recorded hits coincide (median ≤ 6 ms, 90 % within 16 ms)", lag_ok(lag), lag)
    # seek the vocal deck while synced → quantised, still aligned
    act(pg, "E.seek('A', 9.3);"); pg.wait_for_timeout(600)
    dbg = pg.evaluate("E._dbg()"); ph = truth_phase_ms(dbg, "x", "w")
    check("seek while synced: lands near the asked point, bar phase kept (≤ 8 ms)", abs(ph) <= 8 and abs(dbg["A"]["buf"]["pos"] - 9.9) < 2.5, [round(ph, 2), dbg["A"]["buf"]["pos"]])
    # pause both, resume both
    act(pg, "E.pauseAll();"); pg.wait_for_timeout(500); act(pg, "E.playBoth();"); pg.wait_for_timeout(900)
    st, dbg = pg.evaluate("E.state()"), pg.evaluate("E._dbg()"); ph = truth_phase_ms(dbg, "x", "w")
    check("pause + resume: both run synced again (≤ 8 ms)", st["A"]["playing"] and st["B"]["playing"] and st["beat"] == "locked" and abs(ph) <= 8, [st["beat"], round(ph, 2)])
    # SYNC off on the vocal: plays on at its own tempo, seamless; on again → re-joins on the beat
    act(pg, "E.setSync('A', false);"); pg.wait_for_timeout(400)
    st = pg.evaluate("E.state()")
    check("SYNC off: the vocal keeps playing, not synced", st["A"]["playing"] and not st["A"]["sync"] and st["beat"] != "locked", [st["A"]["playing"], st["A"]["sync"], st["beat"]])
    act(pg, "E.setSync('A', true);"); pg.wait_for_timeout(1600)
    st, dbg = pg.evaluate("E.state()"), pg.evaluate("E._dbg()"); ph = truth_phase_ms(dbg, "x", "w")
    check("SYNC on again: re-joined on the beat (≤ 8 ms)", st["A"]["sync"] and st["beat"] == "locked" and abs(ph) <= 8, [st["A"]["sync"], st["beat"], round(ph, 2)])
    check("ops: no engine errors", not errs, errs[:3]); ctx.close()


def sc_loop(br):
    ctx, pg, errs = page(br); seed_truth(pg, ["x", "y"])
    act(pg, "E.loop(true); E.loadPair(T.x, T.y, {A: 125/124, B: 125/126}); E.playBoth();")
    pg.wait_for_timeout(1000)
    act(pg, "E.seek('A', E.state().A.dur - 1.2);")      # A reaches its end soon (a synced seek may land a bar earlier) and restarts
    t0 = time.time()
    while time.time() - t0 < 9:
        pg.wait_for_timeout(250)
        st = pg.evaluate("E.state()")
        if st["A"]["playing"] and st["A"]["sync"] and st["A"]["pos"] < 8: break
    pg.wait_for_timeout(600)
    st, dbg = pg.evaluate("E.state()"), pg.evaluate("E._dbg()"); ph = truth_phase_ms(dbg, "x", "y")
    check("loop: the vocal restarted after its end and re-entered on the beat (≤ 10 ms)", st["A"]["playing"] and st["A"]["sync"] and dbg["A"]["buf"]["pos"] < 9 and abs(ph) <= 10, [st["A"]["playing"], st["A"]["sync"], dbg["A"]["buf"]["pos"], round(ph, 2)])
    check("loop: no engine errors", not errs, errs[:3]); ctx.close()


def sc_wordplay(br):
    ctx, pg, errs = page(br); seed_truth(pg, ["x", "y"])
    act(pg, "E.loadPair(T.x, T.y, {A: 125/124, B: 125/126}); E.setCrossfader(0); E.playOnly('A');")
    pg.wait_for_timeout(2500)
    t = pg.evaluate("() => { E.holdClean(12000); const t0 = performance.now(); E.play('B'); return new Promise(r => { const iv = setInterval(() => { if (E.state().B.playing) { clearInterval(iv); r(performance.now() - t0); } }, 5); setTimeout(() => r(9999), 3000); }); }")
    st = pg.evaluate("E.state()")
    check("word-play handoff: B starts at once (≤ 150 ms, pre-stretched)", t <= 150, round(t))
    check("word-play handoff: no sync during the handoff, A keeps playing", st["A"]["playing"] and not st["B"]["sync"], [st["A"]["playing"], st["B"]["sync"]])
    check("word-play: no engine errors", not errs, errs[:3]); ctx.close()


def sc_nocors(br):
    ctx, pg, errs = page(br)
    pg.evaluate(f"seedAll('http://127.0.0.1:{NPORT}')")
    act(pg, "E.loadPair(T.x, T.y, {A: 1, B: 1}); E.playBoth();")
    pg.wait_for_timeout(4000)
    st = pg.evaluate("E.state()")
    check("no CORS: falls back to streaming, both still play", st["A"]["playing"] and st["B"]["playing"] and not st["A"]["bm"] and st["A"]["kind"] == "apple", [st["A"]["playing"], st["B"]["playing"], st["A"]["bm"], st["A"]["kind"]])
    bad = [e for e in errs if "MashEngine" in e]
    check("no CORS: no engine errors", not bad, bad[:3]); ctx.close()


def sc_analysis(br):
    """song analysis (analysis.json): the vocal enters on its first sung phrase, the beat on its full bar, the vocal deck
    is shifted 1 semitone when the measured keys clash, both decks are trimmed to the same loudness, and stay in sync"""
    ctx, pg, errs = page(br); seed_truth(pg, ["x", "y"])
    tx, ty = TR["x"], TR["y"]
    dx = tx["down"]; dy = ty["down"]
    an = {"X | Test": {"key": "8A", "ks": .8, "km": "e", "lufs": -6.0, "t0": round(dx, 4), "voc": "0000" * 4 + "1666" + "6666" * 7, "nrg": "9999" * 12},
          "Y | Test": {"key": "3A", "ks": .8, "km": "e", "lufs": -14.0, "t0": round(dy, 4), "voc": "0000" * 12, "nrg": "2222" * 2 + "9999" * 10}}
    pg.evaluate("""an => { for (const k of Object.keys(an)) { const t = Object.values(T).find(x => x.t + " | Test" === k); an[k].h = MashEngine._hash(BASE + "/" + t.f + ".wav"); } MashEngine.seedAnalysis(an); }""", an)
    act(pg, "E.loadPair(T.x, T.y, {A: 126/124, B: 1}); E.playBoth();")
    ok = False; t0 = time.time()
    while time.time() - t0 < 6:
        st = pg.evaluate("E.state()")
        if st["A"]["playing"] and st["B"]["playing"]: ok = True; break
        pg.wait_for_timeout(50)
    pg.wait_for_timeout(300)
    st = pg.evaluate("E.state()"); dbg = pg.evaluate("E._dbg()")
    check("analysis: both decks play, synced", ok and st["A"]["sync"] and st["B"]["sync"], [st["A"]["sync"], st["B"]["sync"]])
    check("analysis: keys 8A vs 3A clash → the vocal deck is shifted +1 semitone (→ 3A)", st["A"]["semis"] == 1 and st["B"]["semis"] == 0, [st["A"]["semis"], st["B"]["semis"]])
    check("analysis: loudness trims from LUFS (A −6 → 0.56, B −14 → 1.41)", abs(st["A"]["trim"] - 10 ** (-5 / 20)) < .01 and abs(st["B"]["trim"] - min(1.5, 10 ** (3 / 20))) < .01, [st["A"]["trim"], st["B"]["trim"]])
    A, B = dbg["A"]["buf"], dbg["B"]["buf"]
    startA = A["o0"] * A["sr"]; startB = B["o0"] * B["sr"]
    wantA = dx + 16 * tx["p"]; wantB = dy + 8 * ty["p"]
    check("analysis: the vocal starts at the bar of its first sung phrase (beat 16)", abs(startA - (wantA + A.get("fine", 0) * A["sr"])) < .06, [round(startA, 3), round(wantA, 3)])
    check("analysis: the beat starts at its first full bar (bar 2, after the thin intro)", abs(startB - (wantB + B.get("fine", 0))) < .06, [round(startB, 3), round(wantB, 3)])
    rec = pg.evaluate("record(6)")
    lag = kick_lag_ms(rec, ty["p"])
    check("analysis: the shifted vocal deck stays on the beat (median ≤ 6 ms, 90 % ≤ 16 ms)", lag_ok(lag), lag)
    act(pg, "E.setKeyMatch(false);"); pg.wait_for_timeout(400)
    st = pg.evaluate("E.state()")
    check("analysis: key match off → the vocal back to its own key, still synced", st["A"]["semis"] == 0 and st["A"]["sync"] and st["A"]["playing"], [st["A"]["semis"], st["A"]["sync"]])
    check("analysis: no engine errors", not errs, errs[:3]); ctx.close()


def sc_plan(br):
    """the matcher's plan (match.js → E.loadPair(v, b, r, plan)): the beat starts 2 bars before the bar chosen for it,
    the vocal comes in exactly on that bar, the vocal deck takes the plan's fractional key shift, the beat plays full
    when the plan says it doesn't sing there, and the vocal gate (listen.json vr) turns the vocal deck down between
    sung beats and opens it on time"""
    ctx, pg, errs = page(br); seed_truth(pg, ["x", "y"])
    tx, ty = TR["x"], TR["y"]; dx, dy = tx["down"], ty["down"]
    vr = "0000" * 6 + "7777" * 8 + "0000" * 8
    an = {"X | Test": {"key": "8A", "ks": .8, "km": "e", "lufs": -9.0, "t0": round(dx, 4), "voc": vr.replace("7", "8"), "nrg": "9999" * 20},
          "Y | Test": {"key": "8A", "ks": .8, "km": "e", "lufs": -9.0, "t0": round(dy, 4), "voc": "0000" * 20, "nrg": "9999" * 20}}
    li = {"X | Test": {"vr": vr}}
    pg.evaluate("""([an, li]) => { for (const k of Object.keys(an)) { const t = Object.values(T).find(x => x.t + " | Test" === k); an[k].h = MashEngine._hash(BASE + "/" + t.f + ".wav"); if (li[k]) li[k].h = an[k].h; } MashEngine.seedAnalysis(an); MashEngine.seedListen(li); }""", [an, li])
    aAt, bAt = dx + 24 * tx["p"], dy + 16 * ty["p"]                 # vocal bar 6 (its singing starts there), beat bar 4
    plan = {"v": "X | Test", "b": "Y | Test", "semis": 1.3, "aAt": aAt, "bAt": bAt, "leadBars": 2, "cleanB": False, "q": 1}
    act(pg, f"E.loadPair(T.x, T.y, {{A: 126/124, B: 1}}, {json.dumps(plan)}); E.playBoth();")
    ok = False; t0 = time.time()
    while time.time() - t0 < 6:
        st = pg.evaluate("E.state()")
        if st["A"]["playing"] and st["B"]["playing"]: ok = True; break
        pg.wait_for_timeout(50)
    pg.wait_for_timeout(250)
    st = pg.evaluate("E.state()"); dbg = pg.evaluate("E._dbg()")
    A, B = dbg["A"]["buf"], dbg["B"]["buf"]
    startA, startB = A["o0"] * A["sr"], B["o0"] * B["sr"]
    check("plan: both play, synced", ok and st["A"]["sync"] and st["B"]["sync"], [st["A"]["sync"], st["B"]["sync"]])
    check("plan: the beat starts 2 bars before its chosen bar", abs(startB - (bAt - 8 * ty["p"] + B.get("fine", 0))) < .06, [round(startB, 3), round(bAt - 8 * ty["p"], 3)])
    check("plan: the vocal starts 2 of its bars before its phrase, so the phrase lands on the chosen bar", abs(startA - (aAt - 8 * tx["p"] + A.get("fine", 0) * A["sr"])) < .06, [round(startA, 3), round(aAt - 8 * tx["p"], 3)])
    check("plan: fractional key shift on the vocal deck (+1.3 semitones), none on the beat", abs(st["A"]["semis"] - 1.3) < 1e-6 and st["B"]["semis"] == 0, [st["A"]["semis"], st["B"]["semis"]])
    check("plan: the beat plays full (it does not sing there), the vocal deck is cleaned", st["B"]["vox"] == "off" and st["A"]["vox"] == "vocal", [st["A"]["vox"], st["B"]["vox"]])
    # the vocal gate: closed during the 2-bar lead-in (no singing), open once the phrase is on
    g = pg.evaluate("E._nodes('A').vg.gain.value")
    check("plan: vocal gate down while A has no singing (lead-in)", g < .3, g)
    t_open = (8 * tx["p"]) / A["sr"] + .25                            # real seconds from A's start to its phrase (+ margin)
    pg.wait_for_timeout(int(max(0, t_open - .25 + .4) * 1000))
    g2 = pg.evaluate("E._nodes('A').vg.gain.value")
    check("plan: vocal gate open once A sings", g2 > .8, g2)
    rec = pg.evaluate("record(5)")
    lag = kick_lag_ms(rec, ty["p"])
    check("plan: the shifted vocal stays on the beat (median ≤ 6 ms, 90 % ≤ 16 ms)", lag_ok(lag), lag)
    act(pg, "E.setPlan(null); E.setClean(false);"); pg.wait_for_timeout(300)
    g3 = pg.evaluate("E._nodes('A').vg.gain.value")
    check("plan: clean-up off → the vocal gate opens", g3 > .8, g3)
    check("plan: no engine errors", not errs, errs[:3]); ctx.close()


def main():
    srv = [http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(H, directory=os.path.join(HERE, "media"))),
           http.server.ThreadingHTTPServer(("127.0.0.1", NPORT), functools.partial(HN, directory=os.path.join(HERE, "media")))]
    for s in srv: threading.Thread(target=s.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        br = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        for name, fn in [("wsola", lambda: sc_wsola(br)), ("server", lambda: sc_both(br, True)), ("local", lambda: sc_both(br, False)),
                         ("slowcpu", lambda: sc_both(br, True, throttle=4)),
                         ("tempo", lambda: sc_pair(br, "catalog BPM off by 1", "x2", "y", {"A": 124.5 / 123, "B": 124.5 / 126}, True)[0].close()),
                         ("half", lambda: sc_pair(br, "half-time vocal (62 over 124)", "h", "x", {"A": 1, "B": 1}, True, q=.5)[0].close()),
                         ("griderr", lambda: sc_pair(br, "vocal grid 25 ms early → fixed on the audio", "x", "y", {"A": 125 / 124, "B": 125 / 126}, True, err={"x": -0.025})[0].close()),
                         ("griderr2", lambda: sc_pair(br, "beat grid 30 ms late → fixed on the audio", "x", "y", {"A": 125 / 124, "B": 125 / 126}, True, err={"y": 0.03})[0].close()),
                         ("ops", lambda: sc_ops(br)), ("loop", lambda: sc_loop(br)), ("wordplay", lambda: sc_wordplay(br)), ("ride", lambda: sc_ride(br)), ("nocors", lambda: sc_nocors(br)),
                         ("analysis", lambda: sc_analysis(br)), ("plan", lambda: sc_plan(br))]:
            if FILT and FILT not in name: continue
            try: fn()
            except Exception as e: check(name + " crashed", False, repr(e)[:500])
        br.close()
    for s in srv: s.shutdown()
    bad = [n for n, ok in RES if not ok]
    print(f"{len(RES) - len(bad)}/{len(RES)} passed", "BUF_OK" if not bad else "BUF_FAIL")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
