#!/usr/bin/env python3
"""Real-music check of Mashup Lab's word-play transitions ("מעברי מילים"). Runs on GitHub Actions
(.github/workflows/mashup-verify-wordplay.yml): Google Chrome plays each curated link through the app's own word-play
player (E.wordplay + the same plan the card uses), the transition is recorded from the audio graph, and then:

  * placement: A before the cut and B after it are cross-correlated (1 ms onset envelopes) with the original
    previews placed where the plan says → how many ms each one is off
  * the same beat: the "Beat This!" tracker listens to the recording; A's beats before the cut are fitted to one
    grid and B's beats after the cut must continue it (median / 90th percentile offset in ms)
  * the words: the plan's gap between the end of A's word and the start of B's word, and whether Whisper found both

    python tools/mashup_lab_verify_wordplay.py --page tools/verify/mashup-lab-next.html --links 40 --checkpoint final0.ckpt

Writes a JSON report and a short text summary (numbers only; recordings and previews stay in memory / temp files).
"""
import argparse
import base64
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAB = os.path.join(ROOT, "docs", "mashup-lab")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

RUN_JS = """async ([lk]) => {
  const W = window.WordplayUI, E = MashApp.E, l = W.links.find(x => W.key(x) === lk);
  if (!l) return {err: "missing"};
  E.gesture(); E.stopAll();
  window.__plan = null;
  let pl = null;
  try { pl = await E.wordplay({a: MashApp.DATA[l.ai], b: MashApp.DATA[l.bi], plan: info => (window.__plan = W.planFor(l, info))}); }
  catch (e) { return {err: "wordplay: " + (e && e.message || e), plan: window.__plan}; }
  const n = E._wpNodes(); if (!n || !pl) return {err: "not started"};
  const c = E._ctx(), sp = c.createScriptProcessor(4096, 2, 1), g = c.createGain(), out = []; g.gain.value = 0;
  sp.onaudioprocess = e => { const x = e.inputBuffer.getChannelData(0), y = e.inputBuffer.numberOfChannels > 1 ? e.inputBuffer.getChannelData(1) : x, m = new Float32Array(x.length);
    for (let i = 0; i < x.length; i++) m[i] = .5 * (x[i] + y[i]); out.push([e.playbackTime, m]); };
  n.bus.connect(sp); sp.connect(g); g.connect(c.destination);
  const st = E.wpState();
  await new Promise(r => setTimeout(r, Math.max(1000, (n.te - c.currentTime) * 1000 + 400)));
  try { n.bus.disconnect(sp); } catch (e) {} sp.disconnect();
  if (!out.length) return {err: "no recording", plan: pl};
  const N = out.reduce((a, b) => a + b[1].length, 0), all = new Int16Array(N); let o = 0;
  for (const [, m] of out) { for (let i = 0; i < m.length; i++) all[o + i] = Math.max(-32767, Math.min(32767, Math.round(m[i] * 32767))); o += m.length; }
  let bin = ""; const u8 = new Uint8Array(all.buffer); for (let i = 0; i < u8.length; i += 8192) bin += String.fromCharCode.apply(null, u8.subarray(i, i + 8192));
  return {plan: pl, lag: st.lag || 0, nodes: {t0: n.t0, tc: n.tc, te: n.te}, rec: {t0: out[0][0], sr: c.sampleRate, b64: bin && btoa(bin)},
          a: MashApp.DATA[l.ai].t + " | " + MashApp.DATA[l.ai].a, b: MashApp.DATA[l.bi].t + " | " + MashApp.DATA[l.bi].a};
}"""


def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def preview_audio(url, sr, cache):
    if url in cache:
        return cache[url]
    x = None
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "p.m4a")
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r, open(p, "wb") as f:
                    f.write(r.read())
                break
            except Exception:
                time.sleep(3)
        if os.path.exists(p):
            q = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", p, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, timeout=90)
            if q.returncode == 0:
                x = np.frombuffer(q.stdout, dtype="<f4").astype(np.float32)
    cache[url] = x
    return x


def hf_env(x, sr):
    """onsets (claps / snares / hats / consonants): first-difference energy per 1 ms, positive log-difference"""
    d = np.diff(x, prepend=x[:1]); hop = max(1, sr // 1000); n = len(d) // hop
    if n < 2:
        return np.zeros(1)
    e = np.log1p(1e5 * np.add.reduceat(d[: n * hop] ** 2, np.arange(0, n * hop, hop)))
    return np.maximum(0, np.diff(e, prepend=e[0]))


def env_lag(rec, sr, t_rec0, t1, t2, src, pos0, tau0, rate):
    """ms the recording in [t1, t2] (ctx time) is late against the original audio `src` placed at track time pos0 = ctx
    time tau0, speed rate. Cross-correlation of onset envelopes over ±40 ms; None when there is no clear peak."""
    i1, i2 = int((t1 - t_rec0) * sr), int((t2 - t_rec0) * sr)
    if i1 < 0 or i2 > len(rec) or i2 - i1 < sr:
        return None
    er = hf_env(rec[i1:i2], sr)
    a, b = pos0 + (t1 - .05 - tau0) * rate, pos0 + (t2 + .05 - tau0) * rate
    if a < 0 or b * sr > len(src):
        return None
    eb = hf_env(src[int(a * sr):int(b * sr)], sr)
    tb = a + np.arange(len(eb)) / 1000.0
    tc = tau0 + (tb - pos0) / rate
    em = np.interp(t1 + np.arange(len(er)) / 1000.0, tc, eb, left=0, right=0)
    cs = []
    for k in range(-40, 41):
        cs.append(float(np.dot(er[k:], em[:len(em) - k])) if k >= 0 else float(np.dot(er[:k], em[-k:])))
    cs = np.array(cs); bk = int(np.argmax(cs))
    if bk in (0, len(cs) - 1) or cs[bk] < 1.15 * float(np.mean(cs)):
        return None
    return bk - 40


def continuity(beats, t0, tc, te):
    """A's tracked beats before the cut define one grid; B's tracked beats after it must continue that grid"""
    bA = beats[(beats > t0 + .8) & (beats < tc - .15)]
    bB = beats[(beats > tc + .3) & (beats < min(te - 1.8, tc + 8))]
    if len(bA) < 6 or len(bB) < 4:
        return None
    k = np.round((bA - bA[0]) / np.median(np.diff(bA)))
    per, ph = np.polyfit(k, bA, 1)
    kb = np.round((bB - ph) / per)
    off = (bB - (ph + kb * per)) * 1000
    # half / double time: B tracked at twice or half of A's beat rate still continues the pulse
    return {"n": int(len(off)), "median_ms": round(float(np.median(off)), 1), "p90_abs_ms": round(float(np.percentile(np.abs(off), 90)), 1),
            "ibi_A_ms": round(float(per) * 1000, 1), "ibi_B_ms": round(float(np.median(np.diff(bB))) * 1000, 1) if len(bB) > 2 else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", default=os.path.join(ROOT, "tools", "verify", "mashup-lab-next.html"))
    ap.add_argument("--links", type=int, default=40)
    ap.add_argument("--disc", type=int, default=15, help="also play the top links found by listening (wordtimes.json disc)")
    ap.add_argument("--checkpoint", default="final0")
    ap.add_argument("--out", default=os.path.join(ROOT, "tools", "reports", "mashup-wordplay-report.json"))
    ap.add_argument("--summary", default=os.path.join(ROOT, "tools", "reports", "mashup-wordplay.txt"))
    ap.add_argument("--lab", default=LAB)
    ap.add_argument("--browser", default="chrome")
    ap.add_argument("--port", type=int, default=8891)
    ap.add_argument("--dry", action="store_true", help="local dry run: no beat tracker (placement checks only)")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright
    a2b = None
    if not args.dry:
        from beat_this.inference import Audio2Beats
        a2b = Audio2Beats(checkpoint_path=args.checkpoint, device="cpu", dbn=False)
    links = json.load(open(os.path.join(args.lab, "wordplay-links.json"), encoding="utf-8"))
    wt, disc = {}, []
    if os.path.exists(os.path.join(args.lab, "wordtimes.json")):
        wj = json.load(open(os.path.join(args.lab, "wordtimes.json"), encoding="utf-8"))
        wt, disc = wj.get("links", {}), wj.get("disc") or []
    pmap = json.load(open(os.path.join(args.lab, "previews.json"), encoding="utf-8"))["map"]
    order = sorted(links, key=lambda l: (-(bool((wt.get(l["a"] + " || " + l["b"]) or {}).get("a")) + bool((wt.get(l["a"] + " || " + l["b"]) or {}).get("b"))), l["a"]))
    order = order[: args.links] + [{"a": c["a"], "b": c["b"], "word": c.get("w"), "type": "heard"} for c in disc[: args.disc]]
    site = tempfile.mkdtemp()
    shutil.copy(args.page, os.path.join(site, "index.html"))
    for f in os.listdir(args.lab):
        if f.endswith((".json", ".wav")):
            shutil.copy(os.path.join(args.lab, f), os.path.join(site, f))

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), functools.partial(Quiet, directory=site))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    rows, cache = [], {}
    with sync_playwright() as pw:
        br = pw.chromium.launch(channel=None if args.browser == "chromium" else args.browser, headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        pg = br.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{args.port}/index.html")
        pg.wait_for_function("window.MashApp && window.WordplayUI && window.__previews && window.__beats", timeout=30000)
        pg.wait_for_timeout(1500)
        if disc:
            try:
                pg.wait_for_function("Array.isArray(window.__wordDisc) && window.WordplayUI.heard > 0", timeout=15000)
            except Exception:
                print("the page did not pick up the links found by listening", flush=True)
        meta = pg.evaluate("({previews: window.__previews.n, beats: window.__beats.n, analysis: window.__analysis ? window.__analysis.n : 0, words: window.__wordtimes ? Object.keys(window.__wordtimes).length : 0, engine: MashEngine.version})")
        print("page ready", meta, flush=True)
        for i, l in enumerate(order, 1):
            lk = l["a"] + " || " + l["b"]
            row = {"link": lk, "word": l.get("word"), "type": l.get("type")}
            try:
                r = pg.evaluate(RUN_JS, [lk])
                if r.get("err"):
                    row["err"] = r["err"]; row["plan"] = r.get("plan"); rows.append(row); print(f"{i:2d} {lk[:60]} {r['err']}", flush=True); continue
                pl, nd = r["plan"], r["nodes"]
                row["plan"] = {k: pl.get(k) for k in ("synced", "q", "r", "semis", "rel", "style", "aStart", "cut", "bPos", "pre", "tail", "gap", "onBeat", "foundA", "foundB", "drop", "keyA", "keyB", "keySrc")}
                sr = r["rec"]["sr"]
                x = np.frombuffer(base64.b64decode(r["rec"]["b64"]), dtype="<i2").astype(np.float32) / 32767
                nz = np.flatnonzero(np.abs(x) > 1e-4)
                lat = (r["rec"]["t0"] + nz[0] / sr) - nd["t0"] if len(nz) else 0   # the tap hears a couple of buffers late
                t_rec0 = r["rec"]["t0"] - lat
                row["latency_ms"] = round(lat * 1000, 1)
                ua, ub = (pmap.get(r["a"]) or {}).get("p"), (pmap.get(r["b"]) or {}).get("p")
                A = preview_audio(ua, sr, cache) if ua else None
                B = preview_audio(ub, sr, cache) if ub else None
                if A is not None:
                    row["placeA_ms"] = env_lag(x, sr, t_rec0, nd["t0"] + .4, nd["tc"] - .1, A, pl["aStart"], nd["t0"], 1.0)
                if B is not None:
                    pA = 60 / max(1, pl.get("bpmA") or 120)
                    s0 = nd["tc"] + (7.5 * pA if pl.get("echo") else .3)                  # after the echo of A's word died away
                    row["placeB_ms"] = env_lag(x, sr, t_rec0, s0, min(nd["te"] - 1.7, s0 + 5), B, pl["bPos"] + r["lag"] * pl["r"], nd["tc"], pl["r"])
                if a2b:
                    bt, _db = a2b(x, sr)
                    bt = np.asarray(bt) + t_rec0
                    row["beat"] = continuity(bt, nd["t0"], nd["tc"], nd["te"])
            except Exception as e:
                row["err"] = type(e).__name__ + ": " + str(e)[:160]
            rows.append(row)
            b = row.get("beat") or {}
            p = row.get("plan") or {}
            print(f'{i:2d}/{len(order)} {p.get("style")} r {p.get("r")} semis {p.get("semis")} on {p.get("onBeat")} gap {p.get("gap")} words {p.get("foundA")}/{p.get("foundB")} '
                  f'placeA {row.get("placeA_ms")} placeB {row.get("placeB_ms")} beat median {b.get("median_ms")} p90 {b.get("p90_abs_ms")} | {lk[:70]} {row.get("err", "")}', flush=True)
        br.close()
    srv.shutdown()

    good = [r for r in rows if r.get("beat")]
    cont = [r for r in good if abs(r["beat"]["median_ms"]) <= 20 and r["beat"]["p90_abs_ms"] <= 45]
    pa = [abs(r["placeA_ms"]) for r in rows if r.get("placeA_ms") is not None]
    pb = [abs(r["placeB_ms"]) for r in rows if r.get("placeB_ms") is not None]
    gaps = [r["plan"]["gap"] for r in rows if r.get("plan") and r["plan"].get("gap") is not None and r["plan"].get("foundA") and r["plan"].get("foundB")]
    summary = {
        "links": len(rows), "played": len([r for r in rows if not r.get("err")]), "beat_measured": len(good), "beat_continues": len(cont),
        "share_beat_continues": round(len(cont) / max(1, len(good)), 3),
        "beat_median_abs_ms": round(float(np.median([abs(r["beat"]["median_ms"]) for r in good])), 1) if good else None,
        "placeA_median_abs_ms": round(float(np.median(pa)), 1) if pa else None, "placeB_median_abs_ms": round(float(np.median(pb)), 1) if pb else None,
        "placeB_within_8ms": round(float(np.mean(np.array(pb) <= 8)), 3) if pb else None,
        "both_words_found": len([r for r in rows if (r.get("plan") or {}).get("foundA") and (r.get("plan") or {}).get("foundB")]),
        "word_gap_median_s": round(float(np.median(gaps)), 2) if gaps else None,
        "styles": {s: len([r for r in rows if (r.get("plan") or {}).get("style") == s]) for s in ("cut", "echo", "blend", "drop")},
        "synced": len([r for r in rows if (r.get("plan") or {}).get("synced")]),
        "key_shifted": len([r for r in rows if (r.get("plan") or {}).get("semis")]),
        "page": meta, "page_errors": errs[:5],
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump({"summary": summary, "rows": rows}, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    lines = ["Mashup Lab real-music word-play check",
             "columns: beat continuity median ms | p90 ms | place A ms | place B ms | style | rate | semis | cut on | word gap s | words found | link",
             json.dumps(summary, ensure_ascii=False)] + [
        f'{(r.get("beat") or {}).get("median_ms")}\t{(r.get("beat") or {}).get("p90_abs_ms")}\t{r.get("placeA_ms")}\t{r.get("placeB_ms")}\t{(r.get("plan") or {}).get("style")}\t'
        f'{(r.get("plan") or {}).get("r")}\t{(r.get("plan") or {}).get("semis")}\t{(r.get("plan") or {}).get("onBeat")}\t{(r.get("plan") or {}).get("gap")}\t'
        f'{(r.get("plan") or {}).get("foundA")}/{(r.get("plan") or {}).get("foundB")}\t{r["link"]}\t{r.get("err", "")}' for r in rows]
    open(args.summary, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
