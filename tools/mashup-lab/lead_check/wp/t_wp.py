"""Word-play transitions (E.wordplay + WordTiming.plan), measured on the AUDIO of the transition.

Synthetic previews (mkwav.py) have drums on a known grid and sung "words" (harmonic tone bursts) at known times.
The word-play bus is recorded in the page (ScriptProcessor tap, ctx clock), then:
  * B's drum hits after the cut must continue A's beat grid (the same beat, not just the same tempo)
  * B's word must start where the plan says (right after A's word), A's word must be heard whole before the cut
  * a key shift must move B's pitch by the planned semitones; tempos too far apart keep B native, on its own beat
  * stop / deck play interrupt the word play cleanly
usage: python3 t_wp.py [filter]      → PASS/FAIL lines + WP_OK / WP_FAIL
"""
import base64, functools, http.server, json, os, sys, threading, time
import numpy as np
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
sys.path.insert(0, os.path.join(HERE, "..", "beat"))
from rangehttp import RangeHandler
from t_buf import hf_env, hits          # same onset measurement as the sync tests

ENGINE = open(os.path.join(SP, "lab5", "engine.js"), encoding="utf-8").read()
TIMING = open(os.path.join(SP, "lab5", "wordplay", "timing.js"), encoding="utf-8").read()
TR = json.load(open(os.path.join(HERE, "truth.json")))
PORT = 8884
FILT = sys.argv[1] if len(sys.argv) > 1 else ""
RES = []


class H(RangeHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Cache-Control", "no-store"); super().end_headers()
    def log_message(self, *a): pass


def check(name, ok, info=""):
    RES.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  " + str(info)[:700]))


SETUP = """
window.E = MashEngine.create({ net: true, root: document.body });
window.T = {};
for (const k of ["wa", "wb", "wc"]) T[k] = {i: k.charCodeAt(1), t: k.toUpperCase(), a: "Test", g: "house", bpm: TRUTH[k].bpm, k: "8A", y: 2020};
const m = {}, bm = {};
for (const k of Object.keys(T)) { const u = location.origin + "/" + k + ".wav"; m[T[k].t + " | Test"] = {p: u}; const t = TRUTH[k]; bm[T[k].t + " | Test"] = [t.bpm, t.b0, t.d, 0.95, MashEngine._hash(u)]; }
MashEngine.seed(m); MashEngine.seedBeats(bm); E.hintCors(true);
window.REC = null;
window.tapWP = () => {            /* record the word-play output (bus), stamped with the AudioContext clock */
  const c = E._ctx(), n = E._wpNodes(); if (!n) return false;
  const sp = c.createScriptProcessor(4096, 2, 1), g = c.createGain(), out = []; g.gain.value = 0;
  sp.onaudioprocess = e => { const x = e.inputBuffer.getChannelData(0), y = e.inputBuffer.numberOfChannels > 1 ? e.inputBuffer.getChannelData(1) : x, mm = new Float32Array(x.length);
    for (let i = 0; i < x.length; i++) mm[i] = .5 * (x[i] + y[i]); out.push([e.playbackTime, mm]); };
  n.bus.connect(sp); sp.connect(g); g.connect(c.destination);
  window.REC = {out, sp, n};
  return true;
};
window.pack = () => {
  const r = window.REC; if (!r) return null; try { r.n.bus.disconnect(r.sp); } catch (e) {} r.sp.disconnect();
  const ch = r.out; if (!ch.length) return null; const n = ch.reduce((a, b) => a + b[1].length, 0), all = new Int16Array(n); let o = 0;
  for (const [, mm] of ch) { for (let i = 0; i < mm.length; i++) all[o + i] = Math.max(-32767, Math.min(32767, Math.round(mm[i] * 32767))); o += mm.length; }
  let bin = ""; const u8 = new Uint8Array(all.buffer); for (let i = 0; i < u8.length; i += 8192) bin += String.fromCharCode.apply(null, u8.subarray(i, i + 8192));
  return {t0: ch[0][0], sr: E._ctx().sampleRate, b64: btoa(bin), nodes: {t0: r.n.t0, tc: r.n.tc, te: r.n.te}};
};
window.go = (a, b, link, opts) => {
  window.PLAN = null; window.WPERR = null;
  return E.wordplay({a: T[a], b: T[b], plan: info => (window.PLAN = WordTiming.plan(link, info, opts))}).then(p => { tapWP(); return p; }, e => { window.WPERR = String(e && e.message || e); });
};
const bt = document.createElement("button"); bt.id = "act"; bt.textContent = "act"; document.body.appendChild(bt);
bt.onclick = () => { E.gesture(); (window.__act || (() => {}))(); };
"""


def page(br):
    ctx = br.new_context(); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type in ("error", "warning") and "MashEngine" in m.text else None)
    pg.goto(f"http://127.0.0.1:{PORT}/index.html")
    pg.add_script_tag(content=ENGINE); pg.add_script_tag(content=TIMING)
    pg.evaluate("t => { window.TRUTH = t; }", TR); pg.evaluate(SETUP)
    return ctx, pg, errs


def act(pg, js):
    pg.evaluate("js => { window.__act = new Function(js); }", js); pg.click("#act")


def run(pg, a, b, link, opts, secs_after_cut=4.0):
    act(pg, f"go({json.dumps(a)}, {json.dumps(b)}, {json.dumps(link)}, {json.dumps(opts)});")
    t0 = time.time()
    while time.time() - t0 < 8:
        if pg.evaluate("!!(window.REC || window.WPERR)"): break
        pg.wait_for_timeout(30)
    pl = pg.evaluate("window.PLAN"); err = pg.evaluate("window.WPERR")
    if err or not pl: return pl, None, err
    wait = (pl["cut"] - pl["aStart"]) + secs_after_cut + .3
    pg.wait_for_timeout(int(wait * 1000))
    rec = pg.evaluate("pack()")
    sr = rec["sr"]; x = np.frombuffer(base64.b64decode(rec["b64"]), dtype="<i2").astype(np.float32) / 32767
    # a ScriptProcessor's input reaches it a couple of buffers after it played: calibrate on A's start, which is
    # scheduled at exactly nodes.t0 (the bus is silent before it)
    nz = np.flatnonzero(np.abs(x) > 1e-4)
    corr = (rec["t0"] + nz[0] / sr) - rec["nodes"]["t0"] if len(nz) else 0
    print(f"   recording latency {corr * 1000:.1f} ms (calibrated on A's scheduled start)")
    return pl, (rec["t0"] - corr, sr, x, rec["nodes"]), None


def seg(R, t1, t2):
    t0, sr, x, _ = R
    i1, i2 = int(round((t1 - t0) * sr)), int(round((t2 - t0) * sr))
    return x[max(0, i1):max(0, i2)]


def tone_env(R, f, t1, t2, hop=0.005):
    """energy of a narrow band around f (Goertzel-like, 20 ms windows every 5 ms) → (times, env)"""
    t0, sr, x, _ = R
    win = int(.02 * sr); out = []; ts = []
    w = np.hanning(win); ph = np.exp(-2j * np.pi * f * np.arange(win) / sr)
    t = t1
    while t < t2:
        s = seg(R, t, t + .02)
        if len(s) == win: out.append(abs(np.sum(s * w * ph)) / win); ts.append(t + .01)
        t += hop
    return np.array(ts), np.array(out)


def onset_of(R, f, t1, t2):
    ts, e = tone_env(R, f, t1, t2)
    if not len(e) or e.max() < 1e-4: return None
    th = .3 * e.max(); i = int(np.argmax(e > th))
    return float(ts[i])


def offset_of(R, f, t1, t2):
    ts, e = tone_env(R, f, t1, t2)
    if not len(e) or e.max() < 1e-4: return None
    th = .3 * e.max(); idx = np.flatnonzero(e > th)
    return float(ts[idx[-1]]) if len(idx) else None


def pitch_of(R, t1, t2, lo=450, hi=1200):
    s = seg(R, t1, t2); n = len(s)
    if n < 1024: return None
    S = np.abs(np.fft.rfft(s * np.hanning(n), 8 * n)); f = np.fft.rfftfreq(8 * n, 1 / R[1])
    sel = (f >= lo) & (f <= hi)
    return float(f[sel][np.argmax(S[sel])])


def grid_ctx(g, t_start, t_ctx0, rate, lag, t_from, t_to):
    """beat times of a track (its own time) mapped to the ctx clock: track time t_start plays at ctx t_ctx0, speed rate"""
    p = 60 / g["bpm"]; out = []
    k = int(np.floor((t_start - g["b0"]) / p)) - 2
    while True:
        tt = g["b0"] + k * p
        c = t_ctx0 + (tt - t_start) / rate - lag
        if c > t_to: break
        if c >= t_from: out.append(c)
        k += 1
    return np.array(out)


def hit_lag(R, t1, t2, grid, show=False):
    """recorded drum-hit onsets in [t1, t2] (ctx time) against an expected beat grid → (median ms, p90 |ms|, n)"""
    t0, sr, x, _ = R
    s = seg(R, t1, t2); e = hf_env(s, sr); h = hits(e) / 1000.0 + t1
    first = {}                                   # the attack of each hit = its earliest onset near a grid beat
    for t in h:
        j = int(np.argmin(np.abs(grid - t)))
        if abs(grid[j] - t) <= .04 and (j not in first or t < first[j]): first[j] = t
    o = [(first[j] - grid[j]) * 1000 for j in sorted(first)]
    if show: print("   hit attacks vs grid (ms):", [round(float(v), 1) for v in o])
    if len(o) < 4: return None
    o = np.array(o)
    return round(float(np.median(o)), 2), round(float(np.percentile(np.abs(o), 90)), 2), len(o)


WAV = {}
def wav(k):
    if k not in WAV:
        import wave
        with wave.open(os.path.join(HERE, "media", k + ".wav")) as w:
            x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32).reshape(-1, 2).mean(1) / 32767
        WAV[k] = x
    return WAV[k]


def env_lag(R, t1, t2, k, pos0, tau0, rate):
    """timing error (ms, + = late) of the recording in [t1, t2] (ctx time) against track k's ORIGINAL audio placed where
    the plan puts it (track time pos0 at ctx time tau0, speed rate): cross-correlation of 1 ms onset envelopes, ±40 ms"""
    t0, sr, x, _ = R
    er = hf_env(seg(R, t1, t2), sr)
    src = wav(k); a = pos0 + (t1 - .05 - tau0) * rate; b = pos0 + (t2 + .05 - tau0) * rate
    eb = hf_env(src[int(max(0, a) * 44100):int(b * 44100)], 44100)          # 1 ms per value, track time
    tb = max(0, a) + np.arange(len(eb)) / 1000.0                           # track time of each value
    tc = tau0 + (tb - pos0) / rate                                          # → ctx time
    grid = t1 + np.arange(len(er)) / 1000.0
    em = np.interp(grid, tc, eb, left=0, right=0)
    best, bk = -1, 0
    for kk in range(-40, 41):
        if kk >= 0: v = float(np.dot(er[kk:], em[:len(em) - kk]))
        else: v = float(np.dot(er[:kk], em[-kk:]))
        if v > best: best, bk = v, kk
    return bk


def gA_of(k):
    t = TR[k]; return {"bpm": t["bpm"], "b0": t["b0"] + t["d"] * t["p"] - 4 * t["p"] * int((t["b0"] + t["d"] * t["p"]) / (4 * t["p"])), "db": 0}


def sc_echo(br):
    ctx, pg, errs = page(br)
    link = {"type": "answer", "technique": "echo", "word": "X → Y", "mix": {"keyA": "8A", "keyB": "8A"}}
    wt = {"a": [[w[0], w[1], .9, 1] for w in TR["wa"]["words"]], "b": [[w[0], w[1], .9, 1] for w in TR["wb"]["words"]]}
    pl, R, err = run(pg, "wa", "wb", link, {"wt": wt}, secs_after_cut=8.0)
    check("echo: word play starts from decoded buffers", R is not None and pl and pl["ok"], err or pl)
    if not R: ctx.close(); return
    nd = R[3]; T0, Tc = nd["t0"], nd["tc"]
    st = pg.evaluate("E.wpState()")
    lag = st.get("lag", 0) if st else 0
    print("   plan:", {k: pl[k] for k in ("synced", "r", "semis", "style", "aStart", "cut", "bPos", "gap", "onBeat", "pre")}, "fine lag ms", round(lag * 1000, 1))
    check("echo: synced, B stretched to A's tempo (124/126)", pl["synced"] and abs(pl["r"] - 124 / 126) < 2e-3, pl["r"])
    check("echo: the clock mapping matches the plan (cut − aStart)", abs((Tc - T0) - (pl["cut"] - pl["aStart"])) < 1e-3, [Tc - T0, pl["cut"] - pl["aStart"]])
    # A's word is heard whole before the cut
    wA = TR["wa"]["words"][0]
    endA = offset_of(R, 600, T0 + (wA[0] - pl["aStart"]) - .2, Tc - .002)
    check("echo: A's word heard to its end before the cut", endA is not None and endA >= T0 + (wA[1] - pl["aStart"]) - .03, [endA, T0 + (wA[1] - pl["aStart"])])
    # B's word lands where the plan says
    wB = TR["wb"]["words"][0]
    expB = Tc + (wB[0] - pl["bPos"]) / pl["r"] - lag
    onB = onset_of(R, 900, Tc - .05, Tc + 3)
    check("echo: B's word starts where planned (±15 ms)", onB is not None and abs(onB - expB) <= .015, [onB, expB])
    check("echo: B's word comes right after A's (gap ≤ 1.2 s, no overlap)", onB is not None and endA is not None and 0 < onB - endA <= 1.2, [onB and endA and onB - endA])
    # the same beat: B's hits after the cut continue A's grid
    gA = {"bpm": TR["wa"]["bpm"], "b0": TR["wa"]["b0"]}
    eA = env_lag(R, T0 + .3, Tc - .1, "wa", pl["aStart"], T0, 1.0)
    check("echo: before the cut A plays exactly as scheduled (measurement check, ±2 ms)", abs(eA) <= 2, eA)
    eB = env_lag(R, Tc + 3.9, Tc + 7.8, "wb", pl["bPos"] + lag * pl["r"], Tc, pl["r"])   # after the echo died away
    check("echo: after the cut B plays where planned (±8 ms: the stretch splices within ±8 ms)", abs(eB) <= 8, eB)
    xA = (pl["cut"] - gA["b0"]) / (60 / gA["bpm"]); xB = (pl["bPos"] + lag * pl["r"] - TR["wb"]["b0"]) / TR["wb"]["p"] - TR["wb"]["d"]
    ph = ((xB - xA) % 4 + 4) % 4; ph = ph - 4 if ph > 2 else ph
    check("echo: B's bar lines continue A's (bar phase error ≤ 5 ms)", abs(ph * 60 / 124) <= .005, round(ph * 60 / 124 * 1000, 2))
    # the echo: A's word rings on after the cut
    ts, e = tone_env(R, 600, Tc + .02, Tc + 1.5)
    check("echo: A's word echoes after the cut (600 Hz still present, decaying)", len(e) and e.max() > 1e-3, [round(float(e.max()), 5) if len(e) else None])
    # clean splice
    s = seg(R, Tc - .03, Tc + .03); jump = float(np.max(np.abs(np.diff(s)))) if len(s) > 2 else 1
    check("echo: no click at the cut (sample jump < 0.25)", jump < .25, round(jump, 3))
    pg.wait_for_timeout(int((pl["tail"] + 1) * 1000 - 4000))
    st = pg.evaluate("E.wpState()")
    check("echo: ends by itself after B's tail", st["phase"] in ("idle", "done"), st["phase"])
    check("echo: no engine errors", not errs, errs[:3]); ctx.close()


def sc_key(br):
    ctx, pg, errs = page(br)
    link = {"type": "answer", "technique": "double", "word": "X → Y", "mix": {"keyA": "8A", "keyB": "10A"}}
    wt = {"a": [[w[0], w[1], .9, 1] for w in TR["wa"]["words"]], "b": [[w[0], w[1], .9, 1] for w in TR["wb"]["words"]]}
    opts = {"wt": wt, "anA": {"key": "8A", "ks": .8, "km": "e"}, "anB": {"key": "10A", "ks": .8, "km": "e"}}
    pl, R, err = run(pg, "wa", "wb", link, opts)
    check("key: plan shifts B -2 semitones (10A → 8A) and blends", R is not None and pl["semis"] == -2 and pl["style"] in ("blend", "echo"), err or (pl and [pl["semis"], pl["style"], pl["pre"]]))
    if not R: ctx.close(); return
    nd = R[3]; Tc = nd["tc"]; lag = pg.evaluate("E.wpState().lag || 0")
    wB = TR["wb"]["words"][0]; on = Tc + (wB[0] - pl["bPos"]) / pl["r"] - lag
    f = pitch_of(R, on + .08, on + .5)
    want = 900 * 2 ** (-2 / 12)
    check(f"key: B's word sounds {want:.1f} Hz (was 900)", f is not None and abs(f - want) < 6, f)
    gA = {"bpm": TR["wa"]["bpm"], "b0": TR["wa"]["b0"]}
    gridA = grid_ctx(gA, pl["aStart"], nd["t0"], 1.0, 0, Tc + .25, Tc + 3.8)
    eB = env_lag(R, Tc + .3, Tc + 3.8, "wb", pl["bPos"] + lag * pl["r"], Tc, pl["r"])
    check("key: shifted B plays where planned (±8 ms)", abs(eB) <= 8, eB)
    if pl["style"] == "blend":
        pre = seg(R, Tc - pl["pre"] + .1, Tc - .05)
        check("blend: B is already under A for the last bar (bass cut)", len(pre) and np.sqrt(np.mean(pre ** 2)) > .01, pl["pre"])
    check("key: no engine errors", not errs, errs[:3]); ctx.close()


def sc_far(br):
    ctx, pg, errs = page(br)
    link = {"type": "answer", "technique": "double", "word": "X → Y", "mix": {"keyA": "8A", "keyB": "8A"}}
    wt = {"a": [[w[0], w[1], .9, 1] for w in TR["wa"]["words"]], "b": [[w[0], w[1], .9, 1] for w in TR["wc"]["words"]]}
    pl, R, err = run(pg, "wa", "wc", link, {"wt": wt})
    check("far tempos (124 → 92): no stretch, echo cut", R is not None and not pl["synced"] and pl["r"] == 1 and pl["style"] == "echo", err or (pl and [pl["synced"], pl["r"], pl["style"]]))
    if not R: ctx.close(); return
    nd = R[3]; Tc = nd["tc"]
    w = TR["wc"]["words"][0]; exp = Tc + (w[0] - pl["bPos"])
    on = onset_of(R, 750, Tc - .05, Tc + 3)
    check("far: B's word starts where planned (±15 ms)", on is not None and abs(on - exp) <= .015, [on, exp])
    gC = {"bpm": TR["wc"]["bpm"], "b0": TR["wc"]["b0"]}
    grid = grid_ctx(gC, pl["bPos"], Tc, 1.0, 0, Tc + .25, Tc + 3.8)
    eB = env_lag(R, Tc + 2.5, Tc + 3.8, "wc", pl["bPos"], Tc, 1.0)
    check("far: B plays from its own beat where planned (±3 ms)", abs(eB) <= 3, eB)
    xb = (pl["bPos"] - TR["wc"]["b0"]) / TR["wc"]["p"]
    check("far: B's entry point is on one of its beats", abs(xb - round(xb)) * TR["wc"]["p"] <= .002, xb)
    check("far: no engine errors", not errs, errs[:3]); ctx.close()


def sc_stop(br):
    ctx, pg, errs = page(br)
    link = {"type": "answer", "technique": "cut", "word": "X → Y", "mix": {}}
    wt = {"a": [[w[0], w[1], .9, 1] for w in TR["wa"]["words"]], "b": [[w[0], w[1], .9, 1] for w in TR["wb"]["words"]]}
    act(pg, f"go('wa', 'wb', {json.dumps(link)}, {json.dumps({'wt': wt})});")
    pg.wait_for_timeout(2500)
    st = pg.evaluate("E.wpState()")
    check("stop: word play running (phase a)", st["phase"] == "a", st)
    act(pg, "E.wpStop();")
    pg.wait_for_timeout(300)
    st = pg.evaluate("E.wpState()")
    check("stop: E.wpStop() ends it", st["phase"] == "idle", st)
    act(pg, f"go('wa', 'wb', {json.dumps(link)}, {json.dumps({'wt': wt})});")
    pg.wait_for_timeout(2000)
    act(pg, "E.loadPair(T.wa, T.wb, {A: 1, B: 1}); E.playOnly('A');")
    pg.wait_for_timeout(1500)
    st = pg.evaluate("[E.wpState().phase, E.state().A.playing]")
    check("stop: playing a deck stops the word play", st == ["idle", True], st)
    act(pg, "E.pauseAll();")
    check("stop: no engine errors", not errs, errs[:3]); ctx.close()


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(H, directory=os.path.join(HERE, "media")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        br = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        for name, fn in [("echo", sc_echo), ("key", sc_key), ("far", sc_far), ("stop", sc_stop)]:
            if FILT and FILT not in name: continue
            try: fn(br)
            except Exception as e: check(name + " crashed", False, repr(e)[:500])
        br.close()
    srv.shutdown()
    bad = [n for n, ok in RES if not ok]
    print(f"{len(RES) - len(bad)}/{len(RES)} passed", "WP_OK" if not bad else "WP_FAIL")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
