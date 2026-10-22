"""Studio Groove calibration: offline-render deck A solo, deck B solo and both (through the master compressor)
for many genre pairs; report RMS (dBFS) and peak. Pass: |RMS A − RMS B| ≤ 3 dB and peak < 1.0.
Run: python3 test_levels.py"""
import functools, http.server, os, sys, threading
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PAIRS = [  # (vocal genre, bpm, key) , (beat genre, bpm, key)
    (("mizr", 124, "8A"), ("house", 124, "8A")), (("afro", 106, "5A"), ("afrohouse", 122, "5A")),
    (("hiphop", 87, "8A"), ("dnb", 87, "9A")), (("ilpop", 128, "11A"), ("techno", 130, "11A")),
    (("rnb", 98, "4A"), ("amapiano", 112, "4A")), (("regg", 95, "7A"), ("dancehall", 96, "7B")),
    (("pop", 128, "1A"), ("ukg", 132, "2A")), (("latin", 100, "10A"), ("edm", 126, "10A")),
    (("mizr", 96, "3A"), ("regg", 96, "3A")), (("pop", 120, "6B"), ("hiphop", 140, "6A")),
    (("afro", 104, "9A"), ("afro", 104, "9A")), (("rnb", 90, "12A"), ("hiphop", 90, "12A")),
    (("mizr", 128, "8A"), ("techhouse", 126, "8A")), (("ilpop", 100, "2A"), ("pop", 100, "2A")),
    (("mizr", 92, "5A"), ("mizr", 92, "5A")),
]
JS = """async (p) => {
  const st = b => { let q = 0, pk = 0, n = 0, dmax = 0; for (let c = 0; c < b.numberOfChannels; c++) { const d = b.getChannelData(c);
      for (let i = 0; i < d.length; i++) { const v = d[i]; q += v * v; const a = v < 0 ? -v : v; if (a > pk) pk = a; } n += d.length; }
    return { rms: 10 * Math.log10(q / n + 1e-12), peak: pk }; };
  const mk = (x, i) => ({ i, t: "T" + i + x[0], a: "Art" + i, g: x[0], bpm: x[1], k: x[2] });
  const A = mk(p[0], 1), B = mk(p[1], 2), o = { A, B, secs: 16 };
  const a = st(await MashEngine._render(Object.assign({ solo: "A" }, o)));
  const b = st(await MashEngine._render(Object.assign({ solo: "B" }, o)));
  const ab = st(await MashEngine._render(o));
  return { a, b, ab };
}"""


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 8831), functools.partial(H, directory=os.path.dirname(HERE)))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    bad, da = 0, []
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page()
        errs = []
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
        pg.goto("http://127.0.0.1:8831/engine_test/test.html?net=0")
        print(f"{'vocal':>14} {'beat':>16} | {'RMS A':>6} {'RMS B':>6} {'Δ':>5} | {'pk A':>5} {'pk B':>5} {'pk AB':>5}")
        for pr in PAIRS:
            r = pg.evaluate(JS, [list(pr[0]), list(pr[1])])
            d = r["a"]["rms"] - r["b"]["rms"]
            da.append(d)
            ok = abs(d) <= 3 and max(r["a"]["peak"], r["b"]["peak"], r["ab"]["peak"]) < 1
            bad += not ok
            print(f"{pr[0][0] + ' ' + str(pr[0][1]):>14} {pr[1][0] + ' ' + str(pr[1][1]):>16} | {r['a']['rms']:6.1f} {r['b']['rms']:6.1f} {d:5.1f} |"
                  f" {r['a']['peak']:5.2f} {r['b']['peak']:5.2f} {r['ab']['peak']:5.2f} {'' if ok else '  <-- FAIL'}", flush=True)
        br.close()
    s.shutdown()
    print(f"mean ΔRMS (A−B) {sum(da) / len(da):+.2f} dB, max |Δ| {max(abs(x) for x in da):.2f} dB; console errors: {errs}")
    print(f"{len(PAIRS) - bad} passed, {bad} failed")
    sys.exit(1 if bad or errs else 0)


if __name__ == "__main__":
    main()
