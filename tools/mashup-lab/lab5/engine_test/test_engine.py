"""Engine-level Playwright tests for SP/lab5/engine.js (SPEC §3, §3.1, §6 items 1-3).

Run: python3 test_engine.py [name-filter]
Real page.click gestures on engine_test/test.html; itunes.apple.com is mocked with page.route;
previews are local WAVs served with (port 8822) and without (port 8823) Access-Control-Allow-Origin.
"""
import functools, http.server, json, os, subprocess, sys, threading, time, traceback, urllib.parse
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(LAB), "lead_check", "common"))
from rangehttp import RangeHandler  # byte ranges like Apple's CDN
PP, CP, NP = 8821, 8822, 8823
PAGE = f"http://127.0.0.1:{PP}/engine_test/test.html"
CORS = f"http://127.0.0.1:{CP}/"
PLAIN = f"http://127.0.0.1:{NP}/"
ART = f"http://127.0.0.1:{PP}/engine_test/art/100x100bb.png"
NET_ERR = ("Failed to load resource", "net::ERR", "blocked by CORS policy", "CORS")


class H(RangeHandler):
    cors = False

    def end_headers(self):
        if self.cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


class HC(H):
    cors = True


def serve(port, cls, d):
    s = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(cls, directory=d))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


WAVS = {"Alpha Vocal": "a.wav", "Bravo Beat": "b.wav", "Charlie Groove": "c.wav", "Short Alpha": "sa.wav",
        "Short Bravo": "sb.wav", "שיר בדיקה": "a.wav", "Silent Song": "silent.wav"}
ARTISTS = {"Alpha Vocal": "Singer One", "Bravo Beat": "Producer Two", "Charlie Groove": "Producer Three",
           "Short Alpha": "Singer One", "Short Bravo": "Producer Two", "שיר בדיקה": "זמר ישראלי", "Silent Song": "Quiet"}


def results_for(term, country, base):
    out = []
    for title, wav in WAVS.items():
        if title in term:
            if title == "שיר בדיקה" and country != "il":
                continue
            out.append({"trackName": title + " (Karaoke Version)", "artistName": "Karaoke Stars", "collectionName": "Karaoke Hits",
                        "previewUrl": base + "sa.wav", "artworkUrl100": ART})
            out.append({"trackName": title, "artistName": ARTISTS[title], "collectionName": title + " - Single",
                        "previewUrl": base + wav, "artworkUrl100": ART})
    return out


class Mock:
    """page.route handler for https://itunes.apple.com/search"""

    def __init__(self, mode="ok", base=CORS):
        self.mode, self.base, self.calls, self.pending = mode, base, [], []

    def body(self, request):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(request.url).query)
        term, country, cb = q.get("term", [""])[0], q.get("country", [""])[0], q.get("callback", [None])[0]
        res = results_for(term, country, self.base)
        return term, country, cb, json.dumps({"resultCount": len(res), "results": res})

    def fulfill(self, route, request):
        term, country, cb, body = self.body(request)
        if cb:
            route.fulfill(status=200, content_type="text/javascript", body=f"{cb}({body});")
        elif self.mode == "nocors-json":
            route.fulfill(status=200, content_type="application/json", body=body)
        else:
            route.fulfill(status=200, content_type="application/json", headers={"Access-Control-Allow-Origin": "*"}, body=body)

    def __call__(self, route, request):
        term, country, cb, _ = self.body(request)
        self.calls.append({"t": time.time(), "term": term, "country": country, "jsonp": bool(cb)})
        if self.mode == "abort" or (self.mode == "nojson" and not cb):
            return route.abort()
        if self.mode == "hold":
            self.pending.append((route, request))
            return
        self.fulfill(route, request)


# ---------------------------------------------------------------- harness
RESULTS = []


class Ctx:
    def __init__(self, browser, net=True, mock=None, cache=None, allow_net_errors=False, init=None, buf=False):
        self.ctx = browser.new_context()
        self.page = self.ctx.new_page()
        self.errors, self.requests, self.allow = [], [], allow_net_errors
        self.page.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        self.page.on("pageerror", lambda e: self.errors.append("PAGEERROR " + str(e)))
        self.page.on("request", lambda r: self.requests.append(r.url))
        self.mock = mock
        if mock is not None:
            self.page.route("https://itunes.apple.com/**", mock)
        if cache:
            self.page.add_init_script("localStorage.setItem('mashlab.it', %s)" % json.dumps(json.dumps(cache)))
        if init:
            self.page.add_init_script(init)
        self.page.goto(PAGE + ("" if net else "?net=0"))
        # these tests cover the <audio> streaming path, which stays the fallback whenever a preview cannot be
        # downloaded and decoded; decoded-buffer playback has its own tests (buffer_* below, lead_check/beat/t_buf.py)
        if not buf:
            self.page.evaluate("E.setBufMode && E.setBufMode(false)")

    def ev(self, js, arg=None):
        return self.page.evaluate(js, arg) if arg is not None else self.page.evaluate(js)

    def act(self, js):
        self.page.evaluate("() => { window.__act = function () { %s }; }" % js)
        self.page.click("#go")
        err = self.ev("window.__err || null")
        assert not err, err

    def st(self):
        return self.ev("E.state()")

    def dbg(self):
        return self.ev("E._dbg()")

    def wait(self, js, timeout=8.0, msg=None):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.ev(js):
                return time.time() - t0
            time.sleep(0.05)
        raise AssertionError(msg or ("timeout waiting for: " + js) + " | state=" + json.dumps(self.short()))

    def level(self, side, ms=700):
        return self.ev("""async ([s, ms]) => { let m = 0; const t0 = performance.now();
            while (performance.now() - t0 < ms) { m = Math.max(m, E.level(s)); await new Promise(r => requestAnimationFrame(r)); } return m; }""", [side, ms])

    def short(self):
        s = self.st()
        return {k: ({x: s[k][x] for x in ("kind", "busy", "playing", "pos", "eqActive")} if isinstance(s.get(k), dict) else s.get(k)) for k in ("mode", "A", "B")}

    def close(self):
        errs = [e for e in self.errors if not (self.allow and any(x in e for x in NET_ERR))]
        self.ctx.close()
        assert not errs, "console errors: %s" % errs


def cache_for(*keys, base=CORS):
    tracks = {"a": ("Alpha Vocal", "Singer One", "a.wav"), "b": ("Bravo Beat (Extended Mix)", "Producer Two feat. Guest", "b.wav"),
              "c": ("Charlie Groove", "Producer Three", "c.wav"), "sa": ("Short Alpha", "Singer One", "sa.wav"),
              "sb": ("Short Bravo", "Producer Two", "sb.wav"), "silent": ("Silent Song", "Quiet", "silent.wav")}
    return {f"{tracks[k][0]} | {tracks[k][1]}": {"p": base + tracks[k][2], "a": ART.replace("100x100", "600x600")} for k in keys}


def test(fn):
    RESULTS.append(fn)
    return fn


def approx(a, b, tol=0.03):
    return abs(a - b) <= tol


# ---------------------------------------------------------------- tests
@test
def cors_both_play_and_gains(br):
    m = Mock()
    c = Ctx(br, mock=m)
    c.ev("E.setBeatSync && E.setBeatSync(false)")  # mechanics only; beat sync has its own test (lead_check/beat/t_align.py)
    c.act("E.loadPair(T.a, T.b, {A: 1, B: 1}); E.playBoth();")
    s = c.st()
    assert s["mode"] == "both" and (s["A"]["busy"] or s["A"]["playing"]) and (s["B"]["busy"] or s["B"]["playing"]), c.short()  # Play lookups are parallel now and may already have finished
    c.wait("E.state().A.kind === 'apple' && E.state().A.playing && E.state().B.kind === 'apple' && E.state().B.playing", 9)
    d = c.dbg()
    assert d["A"]["active"] == "C" and d["B"]["active"] == "C", d
    assert not d["A"]["C"]["paused"] and not d["B"]["C"]["paused"], d
    t1 = c.ev("[E._dbg().A.C.t, E._dbg().B.C.t]"); time.sleep(0.5); t2 = c.ev("[E._dbg().A.C.t, E._dbg().B.C.t]")
    assert t2[0] > t1[0] + 0.3 and t2[1] > t1[1] + 0.3, (t1, t2)
    la, lb = c.level("A"), c.level("B")
    assert la > 0.05 and lb > 0.05, (la, lb)
    s = c.st()
    assert s["A"]["eqActive"] and s["B"]["eqActive"] and d["cors"] in (True, None), (s, d)
    c.wait("E._dbg().cors === true", 3)
    assert s["A"]["art"] and "600x600bb" in s["A"]["art"], s["A"]["art"]
    assert c.ev("E.art(T.b)").endswith("600x600bb.png")
    assert "art:Alpha Vocal" in c.ev("__log"), c.ev("__log")
    # the karaoke decoy (listed first) must not win
    assert c.dbg()["A"]["url"].endswith("/a.wav"), c.dbg()["A"]["url"]
    # crossfader / volume / EQ move the real node gains
    c.ev("E.setCrossfader(0)"); time.sleep(0.3); g = c.dbg()
    assert approx(g["A"]["g"]["xf"], 1) and approx(g["B"]["g"]["xf"], 0), g
    c.ev("E.setCrossfader(1)"); time.sleep(0.3); g = c.dbg()
    assert approx(g["A"]["g"]["xf"], 0) and approx(g["B"]["g"]["xf"], 1), g
    c.ev("E.setCrossfader(0.5)"); time.sleep(0.3); g = c.dbg()
    assert approx(g["A"]["g"]["xf"], 0.7071) and approx(g["B"]["g"]["xf"], 0.7071), g
    c.ev("E.setVolume('A', 0.3); E.setEq('B', 'low', -24); E.setEq('B', 'high', 20); E.setEq('A', 'mid', -6)"); time.sleep(0.35); g = c.dbg()
    assert approx(g["A"]["g"]["vol"], 0.3) and approx(g["B"]["g"]["low"], -24, .2) and approx(g["B"]["g"]["high"], 6, .1) and approx(g["A"]["g"]["mid"], -6, .1), g
    s = c.st()
    assert s["A"]["vol"] == 0.3 and s["B"]["eq"]["low"] == -24 and s["B"]["eq"]["high"] == 6 and s["xf"] == 0.5, s
    # pause all / resume continues the last mode
    c.act("E.pauseAll();")
    s = c.st(); d = c.dbg()
    assert not s["A"]["playing"] and not s["B"]["playing"] and d["A"]["C"]["paused"] and d["B"]["C"]["paused"] and s["mode"] == "both", c.short()
    c.act("E.resume();")
    c.wait("E.state().A.playing && E.state().B.playing", 3)
    assert c.ev("__plays.filter(p => p.src.indexOf('a.wav') >= 0).pop().inClick"), "resume must call el.play() inside the click"
    c.act("E.playOnly('B');")
    c.wait("!E.state().A.playing && E.state().B.playing && E.state().mode === 'B'", 3)
    assert c.ev("__changes") > 3
    c.close()


@test
def cached_url_plays_synchronously_in_gesture(br):
    c = Ctx(br, mock=Mock(), cache=cache_for("a", "b"))
    c.act("E.loadPair(T.a, T.b, {A: 1, B: 1}); E.playBoth();")
    plays = c.ev("__plays")
    assert any("a.wav" in p["src"] and p["inClick"] for p in plays) and any("b.wav" in p["src"] and p["inClick"] for p in plays), plays
    c.wait("E.state().A.playing && E.state().B.playing", 3)
    assert not c.mock.calls, c.mock.calls  # cached → no lookups
    c.close()


@test
def direct_mode_without_cors(br):
    c = Ctx(br, mock=Mock(base=PLAIN), allow_net_errors=True)
    c.act("E.loadPair(T.a, T.b, {A: 1, B: 1}); E.playBoth();")
    c.wait("E.state().A.kind === 'apple' && E.state().A.playing && E.state().B.kind === 'apple' && E.state().B.playing", 9)
    s, d = c.st(), c.dbg()
    assert d["cors"] is False and d["A"]["active"] == "D" and d["B"]["active"] == "D", d
    assert not s["A"]["eqActive"] and not s["B"]["eqActive"], s
    assert not d["A"]["D"]["paused"] and not d["B"]["D"]["paused"], d
    t1 = c.ev("E._dbg().A.D.t"); time.sleep(0.5)
    assert c.ev("E._dbg().A.D.t") > t1 + 0.3
    assert c.level("A") > 0.05 and c.level("B") > 0.05
    c.ev("E.setCrossfader(0)"); d = c.dbg()
    assert d["B"]["D"]["muted"] and approx(d["A"]["D"]["vol"], 0.85, .01), d
    c.ev("E.setCrossfader(0.5); E.setVolume('B', 0.5)"); d = c.dbg()
    assert approx(d["A"]["D"]["vol"], 0.85 * 0.7071, .01) and approx(d["B"]["D"]["vol"], 0.5 * 0.7071, .01) and not d["B"]["D"]["muted"], d
    c.close()


@test
def silence_watchdog_switches_to_direct(br):
    c = Ctx(br, mock=Mock(), cache=cache_for("silent"), allow_net_errors=True)
    c.act("E.loadDeck('A', {i: 20, t: 'Silent Song', a: 'Quiet', g: 'pop', bpm: 120, k: '5A'}, {A: 1, B: 1}); E.play('A');")
    c.wait("E._dbg().A.active === 'C' && E.state().A.playing", 3)
    dt = c.wait("E._dbg().A.active === 'D' && E.state().A.playing", 6)
    c.wait("E.state().A.pos > 0.8", 3)  # resumed at the same position on elD
    d, s = c.dbg(), c.st()
    assert d["cors"] is False and not s["A"]["eqActive"] and not d["A"]["D"]["paused"], (d, s)
    c.close()


@test
def jsonp_fallback(br):
    m = Mock(mode="nojson")  # fetch fails (Playwright adds CORS to fulfilled responses) → JSONP
    c = Ctx(br, mock=m, allow_net_errors=True)
    c.act("E.loadDeck('A', T.a, {A: 1, B: 1}); E.play('A');")
    c.wait("E.state().A.kind === 'apple' && E.state().A.playing", 6)
    assert [x["jsonp"] for x in m.calls][:2] == [False, True], m.calls
    assert c.ev("Object.keys(window).filter(k => k.indexOf('__mlIT') === 0).every(k => typeof window[k] === 'function')")
    c.close()


@test
def sequence_and_loop_short_wavs(br):
    c = Ctx(br, mock=Mock(), cache=cache_for("sa", "sb"))
    c.act("E.loadPair(T.sa, T.sb, {A: 1, B: 1}); E.loop(true); E.sequence(true);")
    c.wait("E.state().A.playing", 3)
    s = c.st()
    assert s["mode"] == "seq" and s["seq"] and s["loop"] and not s["B"]["playing"], c.short()
    c.wait("E.state().B.playing && !E.state().A.playing", 4)
    c.wait("E.state().A.playing && !E.state().B.playing", 4)
    log = [x for x in c.ev("__log") if x.startswith("ended")]
    assert log[:2] == ["ended:A", "ended:B"], log
    c.act("E.loop(false);")
    c.wait("E.state().B.playing", 4)
    c.wait("!E.state().A.playing && !E.state().B.playing", 4)
    time.sleep(0.5)
    assert not c.st()["A"]["playing"], "loop off: must stop after B"
    c.act("E.sequence(false);")
    assert c.st()["seq"] is False
    c.close()


@test
def swap_one_deck_while_other_plays(br):
    c = Ctx(br, mock=Mock(), cache=cache_for("a", "b", "c"))
    c.ev("E.setBeatSync && E.setBeatSync(false)")  # mechanics only; beat sync has its own test (lead_check/beat/t_align.py)
    c.act("E.loadPair(T.a, T.b, {A: 1, B: 1}); E.playBoth();")
    c.wait("E.state().A.playing && E.state().B.playing", 3)
    t1 = c.ev("E._dbg().A.C.t")
    c.act("E.loadDeck('B', T.c, {A: 1.016, B: 0.984});")
    c.wait("E.state().B.playing && E._dbg().B.url.indexOf('c.wav') > 0", 3)
    time.sleep(0.4)
    s, d = c.st(), c.dbg()
    assert s["A"]["playing"] and not d["A"]["C"]["paused"] and d["A"]["C"]["t"] > t1 + 0.3, (s["A"], d["A"])
    # the deck that keeps playing is never re-timed (a tempo change of an audible track glitches on iPhone);
    # the new track follows its tempo instead: 124 BPM (A at rate 1) → C (126 BPM) at 124/126
    assert s["B"]["track"]["t"] == "Charlie Groove" and approx(s["A"]["rate"], 1, .001) and approx(d["A"]["C"]["rate"], 1, .001), (s, d)
    assert approx(s["B"]["rate"], 124 / 126, .001) and approx(d["B"]["C"]["rate"], 124 / 126, .001), (s["B"], d["B"])
    assert d["A"]["C"]["pp"] is True
    c.act("E.setSync('A', false);")
    assert c.dbg()["A"]["C"]["rate"] == 1 and c.st()["A"]["rate"] == 1
    c.close()


@test
def network_blocked_studio_on_both(br):
    m = Mock(mode="abort")
    c = Ctx(br, mock=m, allow_net_errors=True)
    c.act("E.loadPair(T.a, T.b, {A: 1, B: 1}); E.playBoth();")
    c.wait("E.state().A.kind === 'studio' && E.state().A.playing && E.state().B.kind === 'studio' && E.state().B.playing", 3)
    la, lb = c.level("A", 900), c.level("B", 900)
    assert la > 0.05 and lb > 0.05, (la, lb)
    d = c.dbg()
    assert d["backoff"] and d["A"]["groove"]["pat"] == "lead" and d["B"]["groove"]["pat"] == "house", d
    ga, gb = d["A"]["groove"], d["B"]["groove"]
    bars = (gb["t0"] - ga["t0"]) / (16 * ga["dt"])
    assert abs(bars - round(bars)) < 1e-3, (ga, gb)  # downbeats aligned
    n = len(m.calls)
    c.act("E.stopAll(); E.loadPair(T.c, T.a, {A: 1, B: 1}); window.__t0 = Date.now();")
    c.wait("Date.now() - window.__t0 > 600", 3)
    assert len(m.calls) == n, "back-off: background lookups pause after a network failure"
    c.act("E.playBoth();")  # a Play still tries Apple (fast, parallel), then falls back with a reason
    c.wait("E.state().A.kind === 'studio' && E.state().B.kind === 'studio' && E.state().A.playing && E.state().B.playing", 8)
    assert c.st()["A"]["why"] == "net" and c.st()["B"]["why"] == "net", c.short()
    s = c.st()
    assert s["A"]["eqActive"] and s["B"]["eqActive"]
    c.close()


@test
def net_false_studio_immediately_zero_requests(br):
    c = Ctx(br, net=False, mock=Mock())
    c.requests.clear()
    c.act("E.loadPair(T.a, T.b, {A: 1, B: 1}); E.playBoth();")
    s = c.st()
    assert s["A"]["kind"] == "studio" and s["A"]["playing"] and s["B"]["kind"] == "studio" and s["B"]["playing"], c.short()
    d = c.dbg()
    assert d["A"]["groove"]["tStart"] == d["B"]["groove"]["tStart"], d  # playBoth: same AudioContext time
    assert c.level("A") > 0.05 and c.level("B") > 0.05
    assert c.ev("E.art(T.a)") is None and c.ev("E.prefetch(T.a)") is None
    c.act("E.pause('B');"); time.sleep(0.3)
    c.act("E.play('B');")
    d = c.dbg(); ga, gb = d["A"]["groove"], d["B"]["groove"]
    bars = (gb["t0"] - ga["t0"]) / (16 * ga["dt"])
    assert abs(bars - round(bars)) < 1e-3 and gb["tStart"] > ga["tStart"], (ga, gb)  # quantized onto A's grid
    c.ev("E.setRates({A: 1.05, B: 1})"); time.sleep(0.1)
    assert approx(c.dbg()["A"]["tempo"], 124 * 1.05, 1e-6)
    c.act("E.loadPair(T.hh, T.dnb, {A: 1, B: 1}); E.playBoth();")
    d = c.dbg()
    assert d["B"]["tempo"] == 174 and d["B"]["groove"]["div"] == 2 and d["A"]["groove"]["div"] == 1 and d["A"]["tempo"] == 87, d
    assert d["A"]["C"] is None and c.ev("document.querySelectorAll('audio').length") == 0  # no media elements at all
    time.sleep(0.5)
    assert c.requests == [], c.requests
    c.close()


@test
def slow_lookup_studio_after_4s_late_result_next_play(br):
    m = Mock(mode="hold")
    c = Ctx(br, mock=m, allow_net_errors=True)
    c.act("E.loadDeck('A', T.a, {A: 1, B: 1}); E.play('A');")
    time.sleep(1)
    s = c.st()
    assert s["A"]["busy"] and s["A"]["kind"] == "idle", c.short()
    c.wait("E.state().A.kind === 'studio' && E.state().A.playing", 7)
    # deliver the (JSONP retry) result late
    c.wait("true", 0.1)
    t0 = time.time()
    while not any("callback=" in req.url for _, req in m.pending) and time.time() - t0 < 4:
        time.sleep(0.05)
    for route, req in m.pending:
        if "callback=" in req.url:
            m.fulfill(route, req)
    c.wait("E.art(T.a) !== null", 3)
    c.wait("E.state().A.kind === 'apple' && E.state().A.playing", 4)  # late result upgrades the Studio Groove fallback mid-play
    for route, req in m.pending:
        try:
            route.abort()
        except Exception:
            pass
    c.close()


@test
def not_allowed_and_midplay_error_fall_back_to_studio(br):
    init = """(function(){ var op = HTMLMediaElement.prototype.play; HTMLMediaElement.prototype.play = function () {
        if (window.__deny && String(this.getAttribute('src')||'').indexOf('data:') !== 0) return Promise.reject(new DOMException('denied', 'NotAllowedError'));
        return op.apply(this, arguments); }; })();"""
    c = Ctx(br, mock=Mock(), cache=cache_for("a", "b"), init=init)
    c.ev("window.__deny = true")
    c.act("E.loadPair(T.a, T.b, {A: 1, B: 1}); E.playBoth();")
    c.wait("E.state().A.kind === 'studio' && E.state().A.playing && E.state().B.kind === 'studio' && E.state().B.playing", 2)
    assert c.dbg()["cors"] is None, "NotAllowedError must not flip CORS"
    c.ev("window.__deny = false")
    c.act("E.stopAll(); E.playBoth();")
    c.wait("E.state().A.kind === 'apple' && E.state().A.playing", 3)
    c.ev("document.querySelectorAll('audio')[0].dispatchEvent(new Event('error'))")  # A's elC
    c.wait("E.state().A.kind === 'studio' && E.state().A.playing", 2)
    # external pause (iOS interruption) is reflected in the state
    c.wait("E.state().B.playing", 2)
    c.ev("document.querySelectorAll('audio')[2].pause()")  # B's elC
    c.wait("!E.state().B.playing", 2)
    c.close()


@test
def unload_stops_everything_and_suspends(br):
    c = Ctx(br, mock=Mock(), cache=cache_for("a"), allow_net_errors=False)
    c.act("E.loadPair(T.a, T.c, {A: 1, B: 1}); E.playBoth();")  # A apple (cached), B waits for lookup → apple later
    c.wait("E.state().A.playing", 3)
    c.act("E.unload();")
    time.sleep(0.4)
    s, d = c.st(), c.dbg()
    assert s["A"]["track"] is None and s["B"]["track"] is None and s["mode"] is None and not s["A"]["playing"] and not s["B"]["playing"], c.short()
    assert d["ctx"] == "suspended", d["ctx"]
    assert all(x["paused"] and (x["src"] == "" or x["src"].startswith("data:")) for k in ("A", "B") for x in (d[k]["C"], d[k]["D"])), d  # data: = silent iOS unlock
    time.sleep(3)  # a late lookup result must not restart anything
    assert not c.st()["B"]["playing"] and c.dbg()["B"]["C"]["src"] == ""
    c.act("E.loadPair(T.a, T.b, {A: 1, B: 1}); E.playOnly('A');")
    c.wait("E.state().A.playing && E._dbg().ctx === 'running'", 3)
    c.close()


@test
def buffer_both_play_gains_levels_unload(br):
    """decoded-buffer decks (the main path): both play from memory, node gains / EQ / crossfader act on them,
    levels are measured from the real signal, pause / resume / play-only / unload behave like the streaming path"""
    c = Ctx(br, mock=Mock(), cache=cache_for("a", "b"), buf=True)
    c.act("E.loadPair(T.a, T.b, {A: 1, B: 1}); E.playBoth();")
    c.wait("E.state().A.playing && E.state().B.playing", 4)
    s, d = c.st(), c.dbg()
    assert s["A"]["bm"] and s["B"]["bm"] and s["A"]["kind"] == "apple" and s["A"]["eqActive"], (s["A"], d["A"]["buf"])
    assert d["A"]["C"] is None or d["A"]["C"]["paused"], d["A"]["C"]          # no <audio> element plays
    p1 = c.ev("[E.state().A.pos, E.state().B.pos]"); time.sleep(0.5); p2 = c.ev("[E.state().A.pos, E.state().B.pos]")
    assert p2[0] > p1[0] + 0.3 and p2[1] > p1[1] + 0.3, (p1, p2)
    la, lb = c.level("A"), c.level("B")
    assert la > 0.05 and lb > 0.05, (la, lb)
    c.ev("E.setCrossfader(0)"); time.sleep(0.3); g = c.dbg()
    assert approx(g["A"]["g"]["xf"], 1) and approx(g["B"]["g"]["xf"], 0), g
    c.ev("E.setCrossfader(0.5); E.setVolume('A', 0.3); E.setEq('B', 'low', -24)"); time.sleep(0.35); g = c.dbg()
    assert approx(g["A"]["g"]["vol"], 0.3) and approx(g["B"]["g"]["low"], -24, .2), g
    c.act("E.pauseAll();")
    s = c.st(); q = c.ev("[E.state().A.pos, E.state().B.pos]"); time.sleep(0.4); q2 = c.ev("[E.state().A.pos, E.state().B.pos]")
    assert not s["A"]["playing"] and not s["B"]["playing"] and s["mode"] == "both" and q == q2, (s["mode"], q, q2)
    c.act("E.resume();")
    c.wait("E.state().A.playing && E.state().B.playing", 3)
    r = c.ev("[E.state().A.pos, E.state().B.pos]")
    assert abs(r[0] - q[0]) < 0.6 and abs(r[1] - q[1]) < 0.6, (q, r)          # resumed where it paused
    c.act("E.playOnly('B');")
    c.wait("!E.state().A.playing && E.state().B.playing && E.state().mode === 'B'", 3)
    c.act("E.unload();"); time.sleep(0.3)
    s, d = c.st(), c.dbg()
    assert s["A"]["track"] is None and not s["B"]["playing"] and d["ctx"] == "suspended" and not d["B"]["buf"]["bm"], (s["B"], d["ctx"])
    c.close()


@test
def lookup_queue_rate_cache_countries_threshold(br):
    m = Mock()
    c = Ctx(br, mock=m)
    c.ev("Promise.all([E.prefetch(T.a), E.prefetch(T.he), E.prefetch(T.miss)])")  # resolves after all lookups
    calls = m.calls
    gaps = [b["t"] - a["t"] for a, b in zip(calls, calls[1:])]
    assert all(g >= 2.4 for g in gaps), gaps
    he = [x for x in calls if "שיר" in x["term"]]
    assert he and he[0]["country"] == "il", calls
    assert [x["country"] for x in calls if "Nothing" in x["term"]] == ["us", "il"], calls
    assert [x["term"] for x in calls][0] == "Singer One Alpha Vocal", calls
    time.sleep(0.5)  # localStorage write is debounced 300 ms
    cache = json.loads(c.ev("localStorage.getItem('mashlab.it')"))
    assert cache["Alpha Vocal | Singer One"]["p"].endswith("a.wav") and "miss" in cache["Nothing Here | Nobody"], cache
    n = len(calls)
    c.page.reload()
    c.ev("Promise.all([E.prefetch(T.a), E.prefetch(T.miss), E.prefetch(T.he)])")
    assert len(m.calls) == n, "cached hits and misses must not hit the network"
    assert c.ev("E.art(T.he)").endswith("600x600bb.png")
    # term cleaning + match threshold
    assert c.ev("MashEngine._pick([{trackName:'Alpha Vocals Remixed', artistName:'Other', previewUrl:'x'}], T.a)") is None  # contains 2 → reject
    assert c.ev("MashEngine._pick([{trackName:'Alpha Vocal', artistName:'Other', previewUrl:'x'}], T.a)")["p"] == "x"  # exact 6 → accept
    assert c.ev("MashEngine._pick([{trackName:'Alpha Vocal (Live)', artistName:'Singer One', previewUrl:'y'}], T.a)")["p"] == "y"  # prefix+artist
    assert c.ev("MashEngine._pick([{trackName:'Alpha Vocal', artistName:'Karaoke Tribute Band', previewUrl:'z'}], T.a)") is None  # 6+0-3
    c.close()


def main():
    subprocess.run([sys.executable, os.path.join(HERE, "make_wavs.py")], check=True, capture_output=True)
    flt = sys.argv[1] if len(sys.argv) > 1 else ""
    srv = [serve(PP, H, LAB), serve(CP, HC, os.path.join(HERE, "wav")), serve(NP, H, os.path.join(HERE, "wav"))]
    passed = failed = 0
    with sync_playwright() as p:
        br = p.chromium.launch()
        for fn in RESULTS:
            if flt and flt not in fn.__name__:
                continue
            t0 = time.time()
            try:
                fn(br)
                passed += 1
                print(f"PASS {fn.__name__} ({time.time() - t0:.1f}s)", flush=True)
            except Exception as e:
                failed += 1
                print(f"FAIL {fn.__name__}: {e}", flush=True)
                traceback.print_exc(limit=2)
        br.close()
    for s in srv:
        s.shutdown()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
