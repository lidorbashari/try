"""QA lead: app-level E2E on the RELEASE file SP/mashup-lab.html with the REAL engine (SPEC §6 items 1-4).
iTunes search is mocked with page.route; previews are local WAVs served WITH (8841) and WITHOUT (8842) CORS.
usage: python3 qa/e2e_audio.py [flow-filter]     prints FAIL lines + summary; exit 1 on failure."""
import functools, http.server, json, math, os, sys, threading, time, urllib.parse
from playwright.sync_api import sync_playwright

QA = os.path.dirname(os.path.abspath(__file__)); LAB = os.path.dirname(QA); SP = os.path.dirname(LAB)
sys.path.insert(0, os.path.join(SP, "lead_check", "common"))
from rangehttp import RangeHandler  # byte ranges like Apple's CDN (Safari needs them; seeking relies on them)
PP, CP, NP = 8840, 8841, 8842
PAGE = f"http://127.0.0.1:{PP}/mashup-lab.html"
CORS, PLAIN = f"http://127.0.0.1:{CP}/wav/", f"http://127.0.0.1:{NP}/wav/"
ART = f"http://127.0.0.1:{CP}/art/100x100bb.png"
DATA = json.load(open(os.path.join(LAB, "data.json"), encoding="utf-8"))
VOC = {"mizr", "ilpop", "pop", "rnb", "hiphop", "latin", "regg", "afro", "dancehall"}
RESULTS, FILT = [], (sys.argv[1] if len(sys.argv) > 1 else "")


def check(name, ok, info=""):
    RESULTS.append((name, bool(ok)))
    if not ok: print("FAIL " + name + ("  " + str(info)[:400] if info != "" else ""))


class H(RangeHandler):
    cors = False
    def end_headers(self):
        if self.cors: self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store"); super().end_headers()
    def log_message(self, *a): pass
class HC(H): cors = True


def serve(port, cls, d):
    s = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(cls, directory=d))
    threading.Thread(target=s.serve_forever, daemon=True).start(); return s


class Mock:
    """itunes.apple.com/search → one result per DATA track whose title is in the term (pick() needs title+artist)."""
    def __init__(self, base=CORS, mode="ok"):
        self.base, self.mode, self.calls, self.wav = base, mode, [], {}
    def __call__(self, route, request):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(request.url).query)
        term, cb = q.get("term", [""])[0].lower(), q.get("callback", [None])[0]
        self.calls.append(term)
        if self.mode == "abort": return route.abort()
        res = []
        for r in DATA:
            main = r["t"].split(" (")[0].split(" - ")[0].lower()
            if main and main in term and r["a"].split(",")[0].split(" feat")[0].lower()[:5] in term:
                w = self.wav.get(r["t"], "a.wav" if r["g"] in VOC else "b.wav")
                res.append({"trackName": r["t"], "artistName": r["a"], "collectionName": r["t"] + " - Single",
                            "previewUrl": self.base + w, "artworkUrl100": ART})
        body = json.dumps({"resultCount": len(res), "results": res[:5]})
        if cb: return route.fulfill(status=200, content_type="text/javascript", body=f"{cb}({body});")
        route.fulfill(status=200, content_type="application/json", headers={"Access-Control-Allow-Origin": "*"}, body=body)


MOCK_CLAUDE = open(os.path.join(QA, "mock_claude.js"), encoding="utf-8").read()


class P:
    def __init__(self, b, mock=None, init=None, scheme="light", allow=()):
        self.ctx = b.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme, has_touch=True, is_mobile=True)
        self.pg = pg = self.ctx.new_page(); self.errs, self.allow = [], allow
        pg.on("console", lambda m: self.errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: self.errs.append("pageerror: " + str(e)))
        pg.route("**/fonts.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
        pg.route("**/fonts.gstatic.com/**", lambda r: r.abort())
        self.mock = mock or Mock()
        pg.route("**/itunes.apple.com/**", self.mock)
        if init: pg.add_init_script(init)
        pg.goto(PAGE); pg.wait_for_timeout(600)
    def ev(self, js, arg=None): return self.pg.evaluate(js, arg)
    def st(self): return self.ev("(() => { const s = MashApp.E.state(); return {mode: s.mode, A: s.A && {k: s.A.kind, p: s.A.playing, b: s.A.busy, eq: s.A.eqActive, t: s.A.track && s.A.track.t}, B: s.B && {k: s.B.kind, p: s.B.playing, b: s.B.busy, eq: s.B.eqActive, t: s.B.track && s.B.track.t}}; })()")
    def dbg(self): return self.ev("MashApp.E._dbg()")
    def wait(self, js, ms=9000):
        t0 = time.time()
        while time.time() - t0 < ms / 1000:
            if self.ev(js): return True
            self.pg.wait_for_timeout(120)
        return False
    def levels(self, n=12):
        mx = {"A": 0, "B": 0}
        for _ in range(n):
            l = self.ev("[MashApp.E.level('A'), MashApp.E.level('B')]"); mx["A"] = max(mx["A"], l[0]); mx["B"] = max(mx["B"], l[1])
            self.pg.wait_for_timeout(80)
        return mx
    def errors(self): return [e for e in self.errs if not any(a in e for a in self.allow)]
    def close(self): self.ctx.close()


BOTH = "(() => { const s = MashApp.E.state(); return s.A.playing && s.B.playing; })()"
def card(p, i=0): return p.pg.locator("#list .card").nth(i)
def el_of(d, s):
    """the playing source of a deck: its decoded buffer (main path) or its active <audio> element (fallback)"""
    x = d[s]
    if x.get("buf") and x["buf"]["bm"]: return {"paused": not x["buf"]["sr"] or False, "t": x["buf"]["pos"], "buf": True}
    return x["C"] if x["active"] == "C" else x["D"]
def advancing(p):
    for _ in range(3):
        d1 = p.dbg(); p.pg.wait_for_timeout(700); d2 = p.dbg()
        if (d1["sync"]["seeks"], d1["sync"]["dips"]) != (d2["sync"]["seeks"], d2["sync"]["dips"]): continue  # a beat-sync jump (made while muted) fell inside the window: measure again
        return all(el_of(d2, s) and not el_of(d2, s)["paused"] and el_of(d2, s)["t"] > el_of(d1, s)["t"] + 0.3 for s in "AB"), [el_of(d1, "A"), el_of(d2, "A")]
    return False, ["sync kept jumping", d2["sync"]]
def set_input(p, sel, v):
    p.ev("([s, v]) => { const x = document.querySelector(s); x.value = v; x.dispatchEvent(new Event('input', {bubbles:true})); x.dispatchEvent(new Event('change', {bubbles:true})); }", [sel, str(v)])


def flow_cors(b):
    p = P(b)
    card(p).locator('[data-act="both"]').click()
    check("cors: card 'נגן מאש־אפ יחד' → both decks playing", p.wait(BOTH), p.st())
    s = p.st(); check("cors: both decks are Apple previews with EQ active", s["A"]["k"] == s["B"]["k"] == "apple" and s["A"]["eq"] and s["B"]["eq"], s)
    bm = p.ev("(() => { const s = MashApp.E.state(); return [s.A.bm, s.B.bm]; })()")
    check("cors: both decks play from decoded buffers (one clock, sample-accurate sync)", bm == [True, True], bm)
    ok, info = advancing(p); check("cors: both <audio> not paused, currentTime advancing", ok, info)
    lv = p.levels(); check("cors: levels > 0 on both decks", lv["A"] > 0.01 and lv["B"] > 0.01, lv)
    p.pg.click('#mini [data-act="open-mixer"]'); p.pg.wait_for_timeout(700)
    bad = p.ev("['A','B'].map(s => document.querySelector('#dk-' + s).textContent.includes('באדיבות iTunes'))")
    check("cors: deck badges show 'תצוגה מקדימה באדיבות iTunes' (§4.9b)", all(bad), bad)
    set_input(p, '#mixer [data-act=xf]', 20); set_input(p, '#dk-A [data-band=low]', -12); set_input(p, '#dk-B [data-act=vol]', 40)
    p.pg.wait_for_timeout(400); g = p.dbg()
    exA, exB = math.cos(0.2 * math.pi / 2), math.sin(0.2 * math.pi / 2)
    check("cors: crossfader 0.2 → xf gains cos/sin", abs(g["A"]["g"]["xf"] - exA) < .03 and abs(g["B"]["g"]["xf"] - exB) < .03, [g["A"]["g"], g["B"]["g"]])
    check("cors: EQ LOW A −12 dB → lowshelf gain", abs(g["A"]["g"]["low"] + 12) < .6, g["A"]["g"])
    check("cors: volume B 40 → vol gain 0.4", abs(g["B"]["g"]["vol"] - .4) < .03, g["B"]["g"])
    # swap B while A plays
    p.pg.click('#mixer [data-act="tp-both"]'); p.wait(BOTH, 4000)
    opt = p.ev("(() => { const s = document.querySelector('#dk-B [data-act=swap]'); const o = Array.from(s.options).find(o => !o.selected && o.value); return o ? o.value : null; })()")
    tb0 = p.st()["B"]["t"]; p.pg.select_option('#dk-B [data-act="swap"]', opt)
    a_ok = True
    for _ in range(12):
        p.pg.wait_for_timeout(150); a_ok = a_ok and p.st()["A"]["p"]
    ok = p.wait("(() => { const s = MashApp.E.state(); return s.B.playing && s.A.playing; })()", 8000)
    s = p.st(); check("cors: swap B while A plays → A never stops, B plays the new track", a_ok and ok and s["B"]["t"] != tb0, [a_ok, s, tb0])
    p.pg.click('#mixer [data-act="sheet-close"]'); p.pg.wait_for_timeout(800)
    ok, _ = advancing(p); check("cors: closing the mixer keeps both decks playing", ok and p.ev("document.querySelector('#mixer').hidden"))
    # card single-deck buttons on the loaded card
    lc = p.pg.locator("#list .card").nth(1)
    if True:
        lc.locator('[data-act="vocal"]').click()
        ok = p.wait("(() => { const s = MashApp.E.state(); return s.A.playing && !s.B.playing; })()", 6000)
        check("cors: 'שירה בלבד' → only deck A plays", ok, p.st())
        lc.locator('[data-act="beat"]').click()
        ok = p.wait("(() => { const s = MashApp.E.state(); return s.B.playing && !s.A.playing; })()", 6000)
        check("cors: 'ביט בלבד' → only deck B plays", ok, p.st())
    p.pg.click('#mini [data-act="unload"]'); p.pg.wait_for_timeout(900)
    d = p.dbg(); s = p.ev("MashApp.E.state()")
    paused = all((d[x]["C"] is None or d[x]["C"]["paused"]) and (d[x]["D"] is None or d[x]["D"]["paused"]) for x in "AB")
    check("cors: mini ✕ unloads (all paused, no tracks, ctx suspended, mini hidden)",
          paused and not s["A"]["track"] and not s["B"]["track"] and d["ctx"] in ("suspended", "closed") and p.ev("document.querySelector('#mini').classList.contains('off')"), [paused, d["ctx"]])
    check("cors: zero console errors", not p.errors(), p.errors()[:4]); p.close()


def flow_seq(b):
    m = Mock()
    # the app prefetches the top pairs right after render, so map every track to a short WAV before the page loads
    m.wav = {r["t"]: ("sa.wav" if r["g"] in VOC else "sb.wav") for r in DATA}
    p = P(b, mock=m)
    pk = card(p).get_attribute("data-pk"); a, bb = map(int, pk.split(":"))
    m.wav[DATA[a]["t"]] = "sa.wav"; m.wav[DATA[bb]["t"]] = "sb.wav"
    card(p).locator('[data-act="mixer"]').click(); p.pg.wait_for_timeout(3500)   # lookups (≤1 / 2.5 s)
    p.pg.click('#mixer [data-act="tp-loop"]'); p.pg.wait_for_timeout(150)
    p.pg.click('#mixer [data-act="tp-seq"]')
    tl, t0 = [], time.time()
    while time.time() - t0 < 9:
        s = p.st(); c = ("A" if s["A"]["p"] else "") + ("B" if s["B"]["p"] else "")
        if c and (not tl or tl[-1] != c): tl.append(c)
        p.pg.wait_for_timeout(80)
    s = p.st()
    check("seq: short WAVs are Apple previews", s["A"]["k"] == "apple" and s["B"]["k"] == "apple", s)
    seqd = "".join(x + "," for x in tl)
    check("seq: רצף plays A then B (never together)", "A,B," in seqd and "AB" not in tl, tl)
    check("seq: לופ restarts A after B", "A,B,A," in seqd, tl)
    p.pg.click('#mixer [data-act="tp-stop"]') if p.ev("!!document.querySelector('#mixer [data-act=tp-stop]')") else None
    check("seq: zero console errors", not p.errors(), p.errors()[:4]); p.close()


def flow_nocors(b):
    p = P(b, mock=Mock(base=PLAIN), allow=("CORS", "net::ERR", "Failed to load resource"))
    card(p).locator('[data-act="both"]').click()
    check("nocors: both decks play (direct mode)", p.wait(BOTH, 12000), p.st())
    s = p.st(); d = p.dbg()
    check("nocors: Apple kind, eqActive=false, direct element active", s["A"]["k"] == s["B"]["k"] == "apple" and s["A"]["eq"] is False and s["B"]["eq"] is False and d["A"]["active"] == d["B"]["active"] == "D", [s, d["A"]["active"], d["B"]["active"]])
    ok, info = advancing(p); check("nocors: currentTime advancing on both", ok, info)
    p.pg.click('#mini [data-act="open-mixer"]'); p.pg.wait_for_timeout(700)
    dis = p.ev("['A','B'].map(s => { const e = document.querySelector('#dk-' + s + ' [data-band=low]'); return !!(e && (e.disabled || e.closest('[aria-disabled=true], .eq-off, .off, .is-off'))); })")
    check("nocors: EQ shows the disabled look", all(dis), dis)
    check("nocors: zero app console errors (browser CORS notices allowed)", not p.errors(), p.errors()[:4]); p.close()


def flow_blocked(b):
    p = P(b, mock=Mock(mode="abort"), allow=("net::ERR", "Failed to load resource"))
    card(p).locator('[data-act="both"]').click()
    check("blocked: both decks play", p.wait(BOTH, 12000), p.st())
    s = p.st(); check("blocked: Studio Groove on both decks", s["A"]["k"] == s["B"]["k"] == "studio", s)
    lv = p.levels(); check("blocked: levels > 0 on both", lv["A"] > 0.01 and lv["B"] > 0.01, lv)
    check("blocked: zero app console errors", not p.errors(), p.errors()[:4]); p.close()


def flow_claude(b):
    m = Mock(); p = P(b, mock=m, init=MOCK_CLAUDE)
    check("claude: engine net:false", p.dbg()["net"] is False, p.dbg()["net"])
    card(p).locator('[data-act="both"]').click()
    check("claude: card plays both decks", p.wait(BOTH, 6000), p.st())
    s = p.st(); check("claude: Studio Groove on both decks", s["A"]["k"] == s["B"]["k"] == "studio", s)
    lv = p.levels(); check("claude: levels > 0 on both", lv["A"] > 0.01 and lv["B"] > 0.01, lv)
    p.pg.wait_for_timeout(500); check("claude: zero iTunes requests", not m.calls, m.calls[:3])
    ext = p.ev("Array.from(document.querySelectorAll('a[target=_blank], a[href^=http]')).length")
    check("claude: at most one external link element in DOM (the Safari link)", ext <= 1, ext)
    check("claude: zero console errors", not p.errors(), p.errors()[:4]); p.close()


def main():
    srv = [serve(PP, H, SP), serve(CP, HC, os.path.join(QA, "media")), serve(NP, H, os.path.join(QA, "media"))]
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        for f in (flow_cors, flow_seq, flow_nocors, flow_blocked, flow_claude):
            if FILT and FILT not in f.__name__: continue
            try: f(b)
            except Exception as e: check(f.__name__ + " crashed", False, repr(e)[:400])
        b.close()
    for s in srv: s.shutdown()
    bad = [n for n, ok in RESULTS if not ok]
    print(f"e2e_audio: {len(RESULTS) - len(bad)}/{len(RESULTS)} passed" + (f"; FAILED: {bad}" if bad else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
