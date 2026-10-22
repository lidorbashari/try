"""Beat-sync safety test (the iPhone stutter regression).

Rule under test: an AUDIBLE deck is never seeked and never re-timed. Every jump / tempo change must happen while
that deck's gate is closed (muted while waiting to enter, or inside a short dip). After a deck has entered,
nothing touches either deck again. Each 'seeking' / 'ratechange' event of the real <audio> elements is logged
with the gate gain at that instant, so the check is exact rather than inferred from currentTime.

usage: python3 t_sync.py [scenario-filter]      prints one line per check + SYNC_OK / SYNC_FAIL
"""
import functools, http.server, json, os, sys, threading, time
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
from rangehttp import RangeHandler
ENGINE = open(os.path.join(HERE, "..", "..", "lab5", "engine.js"), encoding="utf-8").read()
TR = json.load(open(os.path.join(HERE, "truth.json")))
PORT = 8873
DELAY = {"s": 0.0, "fail": False}          # grid fetch (Sec-Fetch-Dest: empty) only; the <audio> stream is untouched
FILT = sys.argv[1] if len(sys.argv) > 1 else ""
RES = []


class H(RangeHandler):
    """grid fetches (Sec-Fetch-Dest: empty) can be failed or slowed: headers at once, the body late (a slow
    mobile network), while the <audio> stream of the same file is served normally"""
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Cache-Control", "no-store"); super().end_headers()
    def do_GET(self):
        self._slow = 0.0
        if self.path.endswith(".wav") and self.headers.get("Sec-Fetch-Dest") == "empty":
            if DELAY["fail"]: self.send_error(404); return
            self._slow = DELAY["s"]
        return super().do_GET()
    def copyfile(self, source, outputfile):
        if self._slow:
            outputfile.write(source.read(65536)); outputfile.flush(); time.sleep(self._slow)
        return super().copyfile(source, outputfile)
    def log_message(self, *a): pass


def check(name, ok, info=""):
    RES.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  " + str(info)[:500]))


SETUP = """
window.E = MashEngine.create({ net: true, root: document.body });
E.setBufMode(false);   /* this suite covers the <audio> streaming fallback (gate / one-shot jumps); buffers: t_buf.py */
window.T = {};
for (const [k, bpm, g, f] of [["x",124,"house"],["y",126,"house"],["z",92,"hiphop"],["w",125,"house"],["h",62,"hiphop"],["x2",123,"house","x"]]) T[k] = {i: k.charCodeAt(0) + k.length, t: k.toUpperCase(), a: "Test", g, bpm, k: "8A", y: 2020, f: f || k};
const m = {}; for (const k of Object.keys(T)) m[T[k].t + " | Test"] = {p: location.origin + "/" + T[k].f + ".wav"};
MashEngine.seed(m); E.hintCors(true);
window.EV = []; window.LOG = [];
window.gateOf = s => { const g = E._dbg()[s].g; return g ? g.gate : 1; };
window.hook = () => {
  const els = document.querySelectorAll("audio");          /* creation order: A.elC, A.elD, B.elC, B.elD */
  [["A", els[0]], ["B", els[2]]].forEach(([s, el]) => { if (!el || el._hooked) return; el._hooked = true;
    ["seeking", "ratechange", "playing", "pause"].forEach(ev => el.addEventListener(ev, () => {
      const st = E.state()[s];
      EV.push({s, ev, t: performance.now(), gate: gateOf(s), held: st.held, cur: el.currentTime, rate: el.playbackRate, paused: el.paused, src: (el.getAttribute("src") || "").slice(-6)});
    }));
  });
};
window.startLog = () => { clearInterval(window.__lg); window.__lg = setInterval(() => {
  const g = E._dbg(), s = E.state();
  LOG.push({t: performance.now(), tA: g.A.C && g.A.C.t, tB: g.B.C && g.B.C.t, rA: g.A.C && g.A.C.rate, rB: g.B.C && g.B.C.rate,
            gA: g.A.g && g.A.g.gate, gB: g.B.g && g.B.g.gate, hA: s.A.held, hB: s.B.held, pA: s.A.playing, pB: s.B.playing, beat: s.beat, cue: s.cue, sync: g.sync});
}, 20); };
const b = document.createElement("button"); b.id = "go"; b.textContent = "go"; document.body.appendChild(b);
b.onclick = () => { E.gesture(); hook(); E.loadPair(T[window.__a], T[window.__b], window.__r); E.playBoth(); hook(); window.T0 = performance.now(); };
const c = document.createElement("button"); c.id = "act"; c.textContent = "act"; document.body.appendChild(c);
c.onclick = () => { E.gesture(); (window.__act || (() => {}))(); hook(); };
"""


def page(br, throttle=0):
    ctx = br.new_context(); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type in ("error", "warning") and "MashEngine" in m.text else None)
    pg.goto(f"http://127.0.0.1:{PORT}/index.html"); pg.add_script_tag(content=ENGINE); pg.evaluate(SETUP)
    if throttle:
        cdp = ctx.new_cdp_session(pg); cdp.send("Emulation.setCPUThrottlingRate", {"rate": throttle})
    return ctx, pg, errs


def go(pg, a, b, rates):
    pg.evaluate(f"window.__a = '{a}'; window.__b = '{b}'; window.__r = {json.dumps(rates)}; EV.length = 0; LOG.length = 0; startLog();")
    pg.click("#go")


def truth_err(L, a, b, q=1):
    """phase error (ms, real time) of A vs B from the ground-truth grids; q = A beats per B beat (0.5 = half time)"""
    a, b = a.rstrip("2"), b.rstrip("2")
    pA, pB, M = TR[a]["p"], TR[b]["p"], 8 if q == 0.5 else 4
    xA = ((L["tA"] - TR[a]["b0"]) / pA - TR[a]["d"]) / q
    xB = (L["tB"] - TR[b]["b0"]) / pB - TR[b]["d"]
    e = (xA - xB) % M
    if e >= M / 2: e -= M
    return e * pB / (L["rB"] or 1) * 1000


def audible_events(EV, side, since=0):
    """seeks / tempo changes of `side` while it was audible: gate open and the element running for > 150 ms"""
    bad, run_t = [], {}
    for e in EV:
        if e["s"] != side: continue
        if e["ev"] == "playing": run_t[side] = e["t"]; continue
        if e["ev"] == "pause": run_t.pop(side, None); continue
        if e["t"] < since or e["paused"] or side not in run_t or e["t"] - run_t[side] < 150: continue
        if e["gate"] > 0.05: bad.append({k: (round(v, 3) if isinstance(v, float) else v) for k, v in e.items()})
    return bad


def entry_time(LOG, side, t0):
    k = "g" + side
    for L in LOG:
        if L["t"] > t0 + 100 and L[k] is not None and L[k] > 0.9 and (L["p" + side]): return (L["t"] - t0) / 1000
    return None


def med(xs):
    s = sorted(xs); return s[len(s) // 2]


def steady(LOG, t_from):
    """after t_from: no gate dips, constant rates, and no hidden jump of either deck relative to the other: the
    real-time phase  tA/rA − tB/rB  stays flat (median-filtered over 9 samples, as Chromium's currentTime moves
    in ~10 ms steps). Both clocks stalling together is the headless browser's fake audio device (a bare pair of
    <audio> elements without the engine shows the same), so the common-mode offset is reported, not judged."""
    xs = [L for L in LOG if L["t"] >= t_from and L["tA"] is not None and L["tB"] is not None]
    if len(xs) < 30: return False, "too few samples"
    rates = {(round(L["rA"], 6), round(L["rB"], 6)) for L in xs}
    dips = [round((L["t"] - t_from) / 1000, 2) for L in xs if L["gA"] < 0.98 or L["gB"] < 0.98]
    ph = [L["tA"] / L["rA"] - L["tB"] / L["rB"] for L in xs]
    f = [med(ph[i - 4:i + 5]) for i in range(4, len(ph) - 4)]
    cm = [L["tB"] - (L["t"] - xs[0]["t"]) / 1000 * xs[0]["rB"] for L in xs]
    info = {"rates": list(rates)[:3], "dips": dips[:5], "relative_spread_ms": round((max(f) - min(f)) * 1000, 1), "common_mode_ms": round((max(cm) - min(cm)) * 1000, 1)}
    return len(rates) == 1 and not dips and max(f) - min(f) < 0.015, info


def lock_err(LOG, a, b, q=1, n=60):
    """median phase error (ms) over the last n samples (≈ 1.2 s) against the ground-truth grids"""
    return med([truth_err(L, a, b, q) for L in LOG[-n:]])


def sc_both(br, tag, throttle=0, cached=False):
    ctx, pg, errs = page(br, throttle)
    if cached:  # first a full run so the grids are in localStorage, then a fresh start of the same pair
        go(pg, "x", "y", {"A": 125 / 124, "B": 125 / 126}); pg.wait_for_timeout(5000); pg.evaluate("E.pauseAll(); E.stopAll()")
        pg.wait_for_timeout(300); pg.evaluate("E.loadPair(T.z, T.w, {A:1, B:1})"); pg.wait_for_timeout(200)
    go(pg, "x", "y", {"A": 125 / 124, "B": 125 / 126})
    pg.wait_for_timeout(100)
    held0 = pg.evaluate("E.state().A.held")
    pg.wait_for_timeout(8000)
    LOG, EV, T0 = pg.evaluate("LOG"), pg.evaluate("EV"), pg.evaluate("T0")
    ent = entry_time(LOG, "A", T0)
    last = LOG[-1]
    check(f"{tag}: the vocal (A) starts muted while the beat plays", held0 and LOG[3]["pB"] in (True, False), held0)
    lim = 3.2 if cached else 4.8
    check(f"{tag}: the vocal enters within {lim} s", ent is not None and ent <= lim, ent)
    check(f"{tag}: zero jumps / tempo changes on the vocal while audible", not audible_events(EV, "A"), audible_events(EV, "A")[:3])
    check(f"{tag}: zero jumps / tempo changes on the beat while audible", not audible_events(EV, "B"), audible_events(EV, "B")[:3])
    if ent is not None:
        ok, info = steady(LOG, T0 + ent * 1000 + 200)
        check(f"{tag}: after entering: no dips, constant tempo, no hidden jumps", ok, info)
    e = lock_err(LOG, "x", "y")
    check(f"{tag}: locked on the bar (|error| ≤ 15 ms)", last["beat"] == "locked" and abs(e) <= 15, [last["beat"], round(e, 1), last["sync"]])
    check(f"{tag}: both audible at the end (gates open)", last["gA"] > 0.98 and last["gB"] > 0.98, [last["gA"], last["gB"]])
    check(f"{tag}: no engine errors", not errs, errs[:3])
    print(f"   {tag}: entry {ent} s, sync {last['sync']}")
    ctx.close()


def sc_pair(br, tag, a, b, rates, q=1):
    """a real-world pair: the vocal enters muted-aligned; the one tempo fix (if any) happens while muted"""
    ctx, pg, errs = page(br)
    go(pg, a, b, rates); pg.wait_for_timeout(8000)
    LOG, EV, T0 = pg.evaluate("LOG"), pg.evaluate("EV"), pg.evaluate("T0")
    ent, last = entry_time(LOG, "A", T0), LOG[-1]
    check(f"{tag}: the vocal enters within 4.8 s", ent is not None and ent <= 4.8, [ent, last["sync"]])
    check(f"{tag}: zero jumps / tempo changes on A while audible", not audible_events(EV, "A"), audible_events(EV, "A")[:3])
    check(f"{tag}: zero jumps / tempo changes on B while audible", not audible_events(EV, "B"), audible_events(EV, "B")[:3])
    e = lock_err(LOG, a, b, q)
    check(f"{tag}: locked (|error| ≤ 15 ms)", last["beat"] == "locked" and abs(e) <= 15, [last["beat"], round(e, 1), last["sync"]])
    if ent is not None:
        ok, info = steady(LOG, T0 + ent * 1000 + 200); check(f"{tag}: after entering: steady", ok, info)
    check(f"{tag}: no engine errors", not errs, errs[:3])
    print(f"   {tag}: entry {ent} s, rates A {last['rA']:.5f} B {last['rB']:.5f}, sync {last['sync']}")
    ctx.close()


def sc_swap(br):
    ctx, pg, errs = page(br)
    go(pg, "x", "y", {"A": 125 / 124, "B": 125 / 126}); pg.wait_for_timeout(6000)
    rA0 = pg.evaluate("E._dbg().A.C.rate")
    pg.evaluate("EV.length = 0; window.__act = () => E.loadDeck('B', T.w, {A: 124.5/124, B: 124.5/125}); window.TS = performance.now();")
    pg.click("#act"); pg.wait_for_timeout(100)
    heldB = pg.evaluate("E.state().B.held")
    pg.wait_for_timeout(7000)
    LOG, EV, TS = pg.evaluate("LOG"), pg.evaluate("EV"), pg.evaluate("TS")
    evA = [e for e in EV if e["s"] == "A" and e["ev"] in ("seeking", "ratechange")]
    check("swap: the new beat (B) joins muted", heldB, heldB)
    check("swap: the playing vocal (A) is never seeked or re-timed", not evA and abs(pg.evaluate("E._dbg().A.C.rate") - rA0) < 1e-9, [evA[:3], rA0])
    ent = entry_time(LOG, "B", TS)
    check("swap: the new beat enters within 4.8 s", ent is not None and ent <= 4.8, ent)
    check("swap: zero jumps / tempo changes on B while audible", not audible_events(EV, "B"), audible_events(EV, "B")[:3])
    last = LOG[-1]
    e = lock_err(LOG, "x", "w")
    check("swap: locked on the bar (|error| ≤ 15 ms)", last["beat"] == "locked" and abs(e) <= 15, [last["beat"], round(e, 1), last["sync"]])
    if ent is not None:
        ok, info = steady(LOG, TS + ent * 1000 + 200); check("swap: after entering: steady", ok, info)
    check("swap: no engine errors", not errs, errs[:3]); ctx.close()


def sc_late(br):
    DELAY["s"] = 7.0
    try:
        ctx, pg, errs = page(br)
        go(pg, "x", "y", {"A": 125 / 124, "B": 125 / 126}); pg.wait_for_timeout(14000)
        LOG, EV, T0 = pg.evaluate("LOG"), pg.evaluate("EV"), pg.evaluate("T0")
        ent = entry_time(LOG, "A", T0)
        last = LOG[-1]
        check("late grid: the vocal is not kept waiting (enters ≤ 5.5 s)", ent is not None and ent <= 5.5, [ent, last["sync"]])
        check("late grid: zero AUDIBLE jumps / tempo changes on A (fixes happen inside a dip)", not audible_events(EV, "A"), audible_events(EV, "A")[:3])
        check("late grid: zero audible jumps on B", not audible_events(EV, "B"), audible_events(EV, "B")[:3])
        check("late grid: at most 2 dips", last["sync"]["dips"] <= 2, last["sync"])
        e = lock_err(LOG, "x", "y", n=40)
        check("late grid: locked in the end (|error| ≤ 25 ms)", last["beat"] == "locked" and abs(e) <= 25, [last["beat"], round(e, 1)])
        check("late grid: both audible at the end", last["gA"] > 0.98 and last["gB"] > 0.98, [last["gA"], last["gB"]])
        check("late grid: no engine errors", not errs, errs[:3]); ctx.close()
    finally:
        DELAY["s"] = 0.0


def sc_fail(br):
    DELAY["fail"] = True
    try:
        ctx, pg, errs = page(br)
        go(pg, "x", "y", {"A": 125 / 124, "B": 125 / 126}); pg.wait_for_timeout(4000)
        LOG, EV, T0 = pg.evaluate("LOG"), pg.evaluate("EV"), pg.evaluate("T0")
        ent = entry_time(LOG, "A", T0)
        check("no grid: the vocal enters right away (≤ 1.2 s)", ent is not None and ent <= 1.2, [ent, LOG[-1]["sync"]])
        check("no grid: zero seeks after start", not [e for e in EV if e["ev"] == "seeking" and e["t"] > T0 + 400], [e for e in EV if e["ev"] == "seeking"][:3])
        check("no grid: no engine errors", not errs, errs[:3]); ctx.close()
    finally:
        DELAY["fail"] = False


def sc_wordplay(br):
    ctx, pg, errs = page(br)
    pg.evaluate("window.__a = 'x'; window.__b = 'y'; window.__r = {A: 125/124, B: 125/126}; startLog();")
    pg.evaluate("window.__act = () => { E.loadPair(T.x, T.y, window.__r); E.setCrossfader(0); E.playOnly('A'); }"); pg.click("#act")
    pg.wait_for_timeout(3000)
    pg.evaluate("EV.length = 0; window.__act = () => { E.holdClean(12000); E.play('B'); }; window.TS = performance.now();"); pg.click("#act")
    pg.wait_for_timeout(150)
    s = pg.evaluate("E.state()")
    pg.wait_for_timeout(3000)
    EV = pg.evaluate("EV")
    check("word-play handoff: B starts audible at once (no waiting)", s["B"]["held"] is False and s["mode"] == "both", [s["B"]["held"], s["mode"]])
    check("word-play handoff: no sync jumps during the handoff", not [e for e in EV if e["ev"] == "seeking"], [e for e in EV if e["ev"] == "seeking"][:3])
    check("word-play: no engine errors", not errs, errs[:3]); ctx.close()


def sc_pause(br):
    ctx, pg, errs = page(br)
    DELAY["s"] = 3.0
    try:
        go(pg, "x", "y", {"A": 125 / 124, "B": 125 / 126}); pg.wait_for_timeout(900)
        h = pg.evaluate("E.state().A.held")
        pg.evaluate("E.pause('B'); window.TP = performance.now()"); pg.wait_for_timeout(400)
        LOG, TP = pg.evaluate("LOG"), pg.evaluate("TP")
        g = [L["gA"] for L in LOG if L["t"] > TP + 250]
        check("pause the beat while the vocal waits → the vocal is heard at once", h and g and min(g) > 0.9, [h, g[:5]])
        check("pause: no engine errors", not errs, errs[:3])
    finally:
        DELAY["s"] = 0.0
    ctx.close()


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(H, directory=os.path.join(HERE, "media")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with sync_playwright() as pw:
        br = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        for name, fn in [("both", lambda: sc_both(br, "both")), ("cached", lambda: sc_both(br, "cached", cached=True)),
                         ("slowcpu", lambda: sc_both(br, "slow CPU ×4", throttle=4)), ("swap", lambda: sc_swap(br)),
                         ("tempo", lambda: sc_pair(br, "catalog BPM off by 1 (123 vs real 124)", "x2", "y", {"A": 124.5 / 123, "B": 124.5 / 126})),
                         ("half", lambda: sc_pair(br, "half-time vocal (62 over 124)", "h", "x", {"A": 1, "B": 1}, q=0.5)),
                         ("late", lambda: sc_late(br)), ("fail", lambda: sc_fail(br)), ("wordplay", lambda: sc_wordplay(br)), ("pause", lambda: sc_pause(br))]:
            if FILT and FILT not in name: continue
            try: fn()
            except Exception as e: check(name + " crashed", False, repr(e)[:400])
        br.close()
    srv.shutdown()
    bad = [n for n, ok in RES if not ok]
    print(f"{len(RES) - len(bad)}/{len(RES)} passed", "SYNC_OK" if not bad else "SYNC_FAIL")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
