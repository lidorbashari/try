#!/usr/bin/env python3
"""Real-music check of Mashup Lab's beat sync. Runs on GitHub Actions (.github/workflows/mashup-verify.yml):
Google Chrome plays real Apple previews through the app's own engine, both decks are recorded separately from the
audio graph, and the "Beat This!" tracker listens to each recording on its own. If the decks are in sync, every
beat of the vocal deck lands on a beat of the beat deck, and bar lines meet bar lines.

    python tools/mashup_lab_verify.py --page tools/verify/mashup-lab-next.html --pairs 40 --checkpoint final0.ckpt

Writes a JSON report and a short text summary (numbers only; recordings live in memory and are discarded).
"""
import argparse
import base64
import functools
import http.server
import json
import os
import random
import shutil
import sys
import tempfile
import threading
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAB = os.path.join(ROOT, "docs", "mashup-lab")
VOC = {"mizr", "ilpop", "pop", "rnb", "hiphop", "latin", "regg", "afro", "dancehall"}
BEAT = {"house", "techhouse", "afrohouse", "amapiano", "techno", "edm", "ukg"}

RECORD_JS = """async (secs) => {
  const E = MashApp.E, c = E._ctx(), out = {A: [], B: []}, sps = [];
  for (const s of ["A", "B"]) {
    const sp = c.createScriptProcessor(4096, 2, 1), g = c.createGain(); g.gain.value = 0;
    sp.onaudioprocess = e => { const x = e.inputBuffer.getChannelData(0), y = e.inputBuffer.numberOfChannels > 1 ? e.inputBuffer.getChannelData(1) : x, m = new Float32Array(x.length);
      for (let i = 0; i < x.length; i++) m[i] = .5 * (x[i] + y[i]); out[s].push([e.playbackTime, m]); };
    E._nodes(s).inp.connect(sp); sp.connect(g); g.connect(c.destination); sps.push([s, sp]);
  }
  await new Promise(r => setTimeout(r, secs * 1000));
  for (const [s, sp] of sps) { try { E._nodes(s).inp.disconnect(sp); } catch (e) {} sp.disconnect(); }
  const pack = s => { const ch = out[s]; if (!ch.length) return null; const n = ch.reduce((a, b) => a + b[1].length, 0), all = new Int16Array(n); let o = 0;
    for (const [, m] of ch) { for (let i = 0; i < m.length; i++) all[o + i] = Math.max(-32767, Math.min(32767, Math.round(m[i] * 32767))); o += m.length; }
    let bin = ""; const u8 = new Uint8Array(all.buffer); for (let i = 0; i < u8.length; i += 8192) bin += String.fromCharCode.apply(null, u8.subarray(i, i + 8192));
    return {t0: ch[0][0], b64: btoa(bin)}; };
  return {sr: c.sampleRate, A: pack("A"), B: pack("B")};
}"""

PLAY_JS = """([ka, kb]) => {
  const D = MashApp.DATA, key = t => t.t + " | " + t.a, A = D.find(t => key(t) === ka), B = D.find(t => key(t) === kb);
  if (!A || !B) return "missing";
  const E = MashApp.E; E.stopAll();
  /* the app's own path: the measured matcher's plan (entry bars, key shift, clean-up, vocal gate) goes to the engine */
  const p = MashApp.pairAny(A, B); MashApp.play(p, "both"); window.__t0 = performance.now();
  const m = p.mm; window.__plan = m && m.ok ? { score: m.score, s: m.s, cents: m.cents, Hn: Math.round(m.Hn * 1000) / 1000, O: Math.round(m.O * 100) / 100, aBar: m.aBar, bBar: m.bBar, cleanB: m.plan.cleanB, lead: m.plan.leadBars } : null;
  return "ok";
}"""


def key(t):
    return f'{t["t"]} | {t["a"]}'


def choose_pairs(n, seed, lab):
    tracks = json.load(open(os.path.join(lab, "tracks.json"), encoding="utf-8"))
    pmap = json.load(open(os.path.join(lab, "previews.json"), encoding="utf-8"))["map"]
    bmap = json.load(open(os.path.join(lab, "beats.json"), encoding="utf-8"))["map"] if os.path.exists(os.path.join(lab, "beats.json")) else {}
    ok = [t for t in tracks if t.get("bpm") and not t.get("pending") and (pmap.get(key(t)) or {}).get("p") and key(t) in bmap and bmap[key(t)][3] >= 0.5]
    vs = [t for t in ok if t["g"] in VOC]
    bs = [t for t in ok if t["g"] in BEAT]
    rng = random.Random(seed)
    pairs, seen = [], set()
    by_genre = {}
    for v in vs:
        by_genre.setdefault(v["g"], []).append(v)
    genres = sorted(by_genre)
    tries = 0
    while len(pairs) < n and tries < 20000:
        tries += 1
        v = rng.choice(by_genre[genres[len(pairs) % len(genres)]])
        gv = bmap[key(v)][0]
        cand = [b for b in bs if 0.94 <= bmap[key(b)][0] / gv <= 1.06]
        if not cand:
            continue
        b = rng.choice(cand)
        if (key(v), key(b)) in seen:
            continue
        seen.add((key(v), key(b)))
        pairs.append((v, b))
    return pairs, bmap


def decode(rec, s):
    r = rec.get(s)
    if not r:
        return None
    x = np.frombuffer(base64.b64decode(r["b64"]), dtype="<i2").astype(np.float32) / 32767
    return r["t0"], x


def stats(a, b, tol):
    """for every time in a, the offset to the nearest time in b (within tol)"""
    if len(a) == 0 or len(b) == 0:
        return None
    o = np.array([t - b[np.argmin(np.abs(b - t))] for t in a])
    near = o[np.abs(o) <= tol]
    return {"n": int(len(o)), "matched": round(float(len(near) / len(o)), 3),
            "median_ms": round(float(np.median(near)) * 1000, 1) if len(near) else None,
            "p90_abs_ms": round(float(np.percentile(np.abs(near), 90)) * 1000, 1) if len(near) else None}


def stats_beats(bA, bB, tol):
    """beat offsets measured from the sparser list: a vocal heard at double density (every eighth note) is not a miss"""
    if len(bA) > 1.4 * len(bB) and len(bB):
        r = stats(bB, bA, tol)
        if r and r["median_ms"] is not None:
            r["median_ms"] = -r["median_ms"]
        if r: r["from"] = "beat deck"
        return r
    return stats(bA, bB, tol)


def hits(x, sr):
    """claps / snares / hats onsets (s): high-passed energy per 1 ms, positive log-difference, local peaks"""
    d = np.diff(x, prepend=x[0]); hop = max(1, sr // 1000); n = len(d) // hop
    e = np.log1p(1e5 * np.add.reduceat(d[: n * hop] ** 2, np.arange(0, n * hop, hop)))
    o = np.maximum(0, np.diff(e, prepend=e[0]))
    th = np.percentile(o, 99) * .25
    out = []
    for j in range(1, len(o) - 1):
        if o[j] > th and o[j] >= o[j - 1] and o[j] > o[j + 1] and (not out or j - out[-1] > 25):
            out.append(j)
    return np.array(out, float) / 1000.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", default=os.path.join(ROOT, "tools", "verify", "mashup-lab-next.html"))
    ap.add_argument("--pairs", type=int, default=40)
    ap.add_argument("--secs", type=float, default=10)
    ap.add_argument("--seed", type=int, default=int(os.environ.get("VERIFY_SEED", "7")))
    ap.add_argument("--checkpoint", default="final0")
    ap.add_argument("--out", default=os.path.join(ROOT, "tools", "reports", "mashup-verify-report.json"))
    ap.add_argument("--summary", default=os.path.join(ROOT, "tools", "reports", "mashup-verify.txt"))
    ap.add_argument("--lab", default=LAB, help="folder with tracks.json, previews.json, beats.json")
    ap.add_argument("--browser", default="chrome", help="chrome (has AAC for Apple previews) or chromium (local dry runs)")
    ap.add_argument("--port", type=int, default=8890)
    ap.add_argument("--reuse", default=os.environ.get("VERIFY_REUSE", ""), help="a previous report: test exactly its pairs (before/after)")
    args = ap.parse_args()

    from beat_this.inference import Audio2Beats
    from playwright.sync_api import sync_playwright
    a2b = Audio2Beats(checkpoint_path=args.checkpoint, device="cpu", dbn=False)

    pairs, bmap = choose_pairs(args.pairs, args.seed, args.lab)
    if args.reuse and os.path.exists(args.reuse):
        tracks = {key(t): t for t in json.load(open(os.path.join(args.lab, "tracks.json"), encoding="utf-8"))}
        prev = json.load(open(args.reuse, encoding="utf-8"))["rows"]
        pairs = [(tracks[r["vocal"]], tracks[r["beat"]]) for r in prev if r.get("vocal") in tracks and r.get("beat") in tracks and r["vocal"] in bmap and r["beat"] in bmap]
    print(f"{len(pairs)} pairs chosen", flush=True)
    site = tempfile.mkdtemp()
    shutil.copy(args.page, os.path.join(site, "index.html"))
    for f in os.listdir(args.lab):   # tracks.json, previews.json, beats.json (+ local audio for dry runs)
        if f.endswith((".json", ".wav")):
            shutil.copy(os.path.join(args.lab, f), os.path.join(site, f))
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), functools.partial(Quiet, directory=site))
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    rows = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(channel=None if args.browser == "chromium" else args.browser, headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        pg = br.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{args.port}/index.html")
        pg.wait_for_function("window.MashApp && window.__previews && window.__beats", timeout=30000)
        try:
            pg.wait_for_function("window.__measured === true", timeout=20000)    # listen.json in: the matcher plans every pair
        except Exception:
            print("no measured matcher on this page (listen.json missing?)", flush=True)
        meta = pg.evaluate("({previews: window.__previews.n, beats: window.__beats.n, engine: MashEngine.version, measured: !!window.__measured})")
        print("page ready", meta, flush=True)
        for i, (v, b) in enumerate(pairs, 1):
            row = {"vocal": key(v), "beat": key(b), "gv": v["g"], "gb": b["g"], "grid_v": bmap[key(v)][:4], "grid_b": bmap[key(b)][:4]}
            try:
                if pg.evaluate(PLAY_JS, [key(v), key(b)]) != "ok":
                    row["err"] = "missing"; rows.append(row); continue
                t0 = time.time()
                pg.wait_for_function("MashApp.E.state().A.playing && MashApp.E.state().B.playing", timeout=25000)
                row["start_s"] = round(time.time() - t0, 2)
                pg.wait_for_timeout(1200)
                st = pg.evaluate("MashApp.E.state()")
                row["plan"] = pg.evaluate("window.__plan")
                row["semis"] = [st["A"].get("semis"), st["B"].get("semis")]
                row["vox"] = [st["A"].get("vox"), st["B"].get("vox")]
                row.update({"bm": [st["A"].get("bm"), st["B"].get("bm")], "sync": [st["A"].get("sync"), st["B"].get("sync")], "lock": st.get("beat"),
                            "src": [(st["A"].get("grid") or {}).get("src"), (st["B"].get("grid") or {}).get("src")],
                            "rate": [round(st["A"]["rate"], 5), round(st["B"]["rate"], 5)]})
                rec = pg.evaluate(RECORD_JS, args.secs)
                pg.evaluate("MashApp.E.pauseAll()")
                sr = rec["sr"]
                A, B = decode(rec, "A"), decode(rec, "B")
                if not A or not B:
                    row["err"] = "no recording"; rows.append(row); continue
                (tA, xA), (tB, xB) = A, B
                bA, dA = a2b(xA, sr); bB, dB = a2b(xB, sr)
                bA, dA, bB, dB = (np.asarray(z) for z in (bA, dA, bB, dB))
                bA, dA = bA + tA, dA + tA   # one clock for both recordings
                bB, dB = bB + tB, dB + tB
                lo, hi = max(tA, tB) + 0.5, min(tA + len(xA) / sr, tB + len(xB) / sr) - 0.5
                sel = lambda z: z[(z >= lo) & (z <= hi)]
                bA, dA, bB, dB = sel(bA), sel(dA), sel(bB), sel(dB)
                ibi = float(np.median(np.diff(bB))) if len(bB) > 2 else 0.5
                row["beats"] = stats_beats(bA, bB, min(0.12, ibi / 3))
                hA, hB = hits(xA, sr) + tA, hits(xB, sr) + tB
                row["hits"] = stats(sel(hA), sel(hB), 0.03)          # second opinion at 1 ms resolution
                row["bars"] = stats(dA, dB, 0.08)
                row["ibi_ms"] = [round(float(np.median(np.diff(bA))) * 1000, 1) if len(bA) > 2 else None, round(ibi * 1000, 1)]
            except Exception as e:
                row["err"] = type(e).__name__ + ": " + str(e)[:160]
            rows.append(row)
            bt = row.get("beats") or {}
            print(f'{i:2d}/{len(pairs)} {row.get("gv")}→{row.get("gb")} start {row.get("start_s")} s  hits median {(row.get("hits") or {}).get("median_ms")} ms  beats: median {bt.get("median_ms")} ms, '
                  f'p90 {bt.get("p90_abs_ms")} ms, matched {bt.get("matched")}  bars matched {(row.get("bars") or {}).get("matched")}  {row.get("src")} {row.get("err", "")}', flush=True)
        br.close()
    srv.shutdown()

    good = [r for r in rows if r.get("beats") and r["beats"]["median_ms"] is not None]
    on_beat = [r for r in good if abs(r["beats"]["median_ms"]) <= 20 and r["beats"]["matched"] >= 0.7]
    med = [abs(r["beats"]["median_ms"]) for r in good]
    summary = {
        "pairs": len(rows), "measured": len(good), "on_beat": len(on_beat),
        "share_on_beat": round(len(on_beat) / max(1, len(good)), 3),
        "median_abs_offset_ms": round(float(np.median(med)), 1) if med else None,
        "p90_abs_offset_ms": round(float(np.percentile(med, 90)), 1) if med else None,
        "median_start_s": round(float(np.median([r["start_s"] for r in rows if r.get("start_s")])), 2) if any(r.get("start_s") for r in rows) else None,
        "bars_matched_median": round(float(np.median([r["bars"]["matched"] for r in good if r.get("bars")])), 3) if any(r.get("bars") for r in good) else None,
        "page": meta, "page_errors": errs[:5],
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump({"summary": summary, "rows": rows}, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    hm = [abs(r["hits"]["median_ms"]) for r in rows if r.get("hits") and r["hits"]["median_ms"] is not None]
    summary["hits_median_abs_ms"] = round(float(np.median(hm)), 1) if hm else None
    summary["hits_within_10ms"] = round(float(np.mean(np.array(hm) <= 10)), 3) if hm else None
    lines = ["Mashup Lab real-music beat-sync check",
             "columns: beat offset median ms | beats matched | bars matched | hit offset median ms | start s | genres | pair | measured plan",
             json.dumps(summary, ensure_ascii=False)] + [
        f'{(r.get("beats") or {}).get("median_ms")}\t{(r.get("beats") or {}).get("matched")}\t{(r.get("bars") or {}).get("matched")}\t{(r.get("hits") or {}).get("median_ms")}\t{r.get("start_s")}\t{r.get("gv")}→{r.get("gb")}\t{r["vocal"]}  ×  {r["beat"]}\t{json.dumps(r.get("plan"), ensure_ascii=False) if r.get("plan") else "-"}\t{r.get("err", "")}'
        for r in rows]
    open(args.summary, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
