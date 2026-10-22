#!/usr/bin/env python3
"""Beat grids for Mashup Lab (docs/mashup-lab): tempo, first beat and bar start of every Apple preview.

Runs on GitHub Actions (.github/workflows/mashup-beats.yml), which can reach Apple's preview CDN.
Each 30-second preview is downloaded to a temporary file, decoded in memory and analysed with the
"Beat This!" beat/downbeat tracker (Foscarin, Schlüter & Widmer, ISMIR 2024). Only the numbers are
kept; no audio is stored anywhere. The app schedules both decks on one audio clock from these grids.

    python tools/mashup_lab_beats.py analyze --shard 0 --shards 8 --out beats-0.json
    python tools/mashup_lab_beats.py merge --parts parts --out docs/mashup-lab/beats.json
    python tools/mashup_lab_beats.py selftest

beats.json: {"meta": {...}, "map": {"<title> | <artist>": [bpm, b0, db, conf, urlhash]}}
  bpm   tempo of the preview (3 decimals; a constant-tempo fit over all detected beats)
  b0    time (s) of the first fitted beat, 0 <= b0 < one beat
  db    which beat of the grid is a bar start: downbeats at b0 + (db + 4k) * 60 / bpm
  conf  0..1, how well the beats fit one steady grid (the app ignores grids below 0.5)
  h     FNV-1a 32-bit hash (hex) of the preview URL the grid belongs to (a changed link is re-analysed)
"""
import argparse
import datetime
import glob
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAB = os.path.join(ROOT, "docs", "mashup-lab")
TRACKS = os.path.join(LAB, "tracks.json")
PREVIEWS = os.path.join(LAB, "previews.json")
BEATS = os.path.join(LAB, "beats.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
SR = 22050


def fnv32(s):
    """FNV-1a 32-bit over UTF-16 code units, identical to hash() in the app's engine.js"""
    h = 2166136261
    b = s.encode("utf-16-le")
    for i in range(0, len(b), 2):
        h ^= b[i] | (b[i + 1] << 8)
        h = (h * 16777619) & 0xFFFFFFFF
    return format(h, "08x")


def key(t):
    return f'{t["t"]} | {t["a"]}'


# ---------------------------------------------------------------- grid fit (pure numpy, unit-tested)
def fit_grid(beats, downbeats, dur=30.0):
    """Constant-tempo grid through detected beat times (robust to missed / extra beats).
    Returns dict(bpm, b0, db, conf, rms, n, bar) or None."""
    b = np.asarray(sorted(float(x) for x in beats if 0 <= x <= dur + 1), float)
    if len(b) < 8:
        return None
    ibi = np.diff(b)
    P = float(np.median(ibi))
    if not (0.25 <= P <= 1.6):  # 37.5 .. 240 BPM
        return None
    # integer beat index per detection (handles gaps), then iterative robust least squares
    k = np.round((b - b[0]) / P).astype(int)
    keep = np.ones(len(b), bool)
    for _ in range(4):
        A = np.vstack([k[keep], np.ones(keep.sum())]).T
        (P, c), *_ = np.linalg.lstsq(A, b[keep], rcond=None)
        res = b - (c + k * P)
        k = np.round((b - c) / P).astype(int)
        res = b - (c + k * P)
        keep = np.abs(res) < max(0.035, 2.5 * np.std(res[keep]) if keep.sum() > 4 else 0.035)
        if keep.sum() < 8:
            return None
    res = b - (c + k * P)
    rms = float(np.sqrt(np.mean(res[keep] ** 2)))
    # fraction of grid beats inside the analysed span that have a detection within 40 ms
    first, last = b[keep][0], b[keep][-1]
    grid_n = int(round((last - first) / P)) + 1
    hit = len(set(k[keep & (np.abs(res) < 0.04)].tolist()))
    cover = hit / max(1, grid_n)
    # b0 = first grid beat at or after t = 0 (the engine's convention), index shift s
    s = int(np.ceil((0 - c) / P - 1e-9))
    b0 = c + s * P
    # downbeats → which grid index mod 4 starts a bar
    db, dbc, bar = 0, 0.0, 4
    d = np.asarray([float(x) for x in downbeats if 0 <= x <= dur + 1], float)
    if len(d) >= 2:
        kd = np.round((d - b0) / P).astype(int)
        near = np.abs(d - (b0 + kd * P)) < 0.06
        kd = kd[near]
        if len(kd) >= 2:
            sp = np.diff(kd)
            bar = int(np.median(sp)) if len(sp) else 4
            m4 = np.bincount(kd % 4, minlength=4)
            db = int(np.argmax(m4))
            dbc = float(m4[db] / max(1, m4.sum()))
    conf = float(np.clip(cover, 0, 1) * np.clip(1 - (rms - 0.008) / 0.03, 0, 1) * (0.6 + 0.4 * dbc) * (1.0 if bar == 4 else 0.7))
    return {"bpm": round(60.0 / P, 3), "b0": round(float(b0), 4), "db": db, "conf": round(conf, 3), "rms": round(rms, 4),
            "n": int(keep.sum()), "cover": round(cover, 3), "dbc": round(dbc, 3), "bar": bar}


def selftest():
    rng = np.random.default_rng(7)
    ok = True
    for bpm, b0, db, jit, miss, extra in [(124, 0.41, 0, 0.004, 0.05, 0.02), (92, 0.62, 1, 0.006, 0.1, 0.05),
                                          (174, 0.05, 3, 0.003, 0.0, 0.0), (100.37, 0.3, 2, 0.008, 0.15, 0.08)]:
        P = 60 / bpm
        n = int(30 / P)
        beats = b0 + np.arange(n) * P + rng.normal(0, jit, n)
        keepm = rng.random(n) > miss
        bt = list(beats[keepm]) + list(rng.uniform(0, 30, int(extra * n)))
        downs = [x for i, x in enumerate(beats) if (i - db) % 4 == 0 and keepm[i]]
        g = fit_grid(bt, downs)
        good = g and abs(g["bpm"] - bpm) < 0.05 and abs(g["b0"] - b0) < 0.006 and g["db"] == db and g["conf"] > 0.5
        print("selftest", bpm, b0, db, "→", g, "OK" if good else "FAIL")
        ok &= bool(good)
    # a drifting performance must get a low confidence
    t = np.cumsum(60 / np.linspace(96, 104, 50))
    g = fit_grid(t, t[::4])
    print("selftest drift →", g, "OK" if g and g["conf"] < 0.5 else "FAIL")
    ok &= bool(g and g["conf"] < 0.5)
    print("SELFTEST_OK" if ok else "SELFTEST_FAIL")
    return 0 if ok else 1


# ---------------------------------------------------------------- audio + model (CI only)
def fetch(url, path):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
                f.write(r.read())
            return True
        except Exception:
            time.sleep(3 * (attempt + 1))
    return False


def decode(path):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                       capture_output=True, timeout=60)
    if p.returncode != 0:
        return None
    x = np.frombuffer(p.stdout, dtype="<f4").astype(np.float32)
    return x if len(x) > SR * 5 else None


def kick_check(x, g):
    """independent sanity check: low-band onset energy on the grid's beats vs halfway between them
    (> 1 means the grid sits on the kicks, not on the off-beats)"""
    hop = 256
    n = len(x) // hop
    if n < 50:
        return None
    lo = np.convolve(x, np.ones(16) / 16, mode="same")  # crude low-pass
    e = np.log1p(1e3 * np.add.reduceat(lo[: n * hop] ** 2, np.arange(0, n * hop, hop)))
    on = np.maximum(0, np.diff(e, prepend=e[0]))
    fps, P = SR / hop, 60 / g["bpm"]
    def at(t):
        i = int(round(t * fps))
        return on[max(0, i - 1): i + 2].max() if 0 <= i < n else 0.0
    beats = [g["b0"] + i * P for i in range(int(30 / P) + 1)]
    on_b = np.mean([at(t) for t in beats])
    off_b = np.mean([at(t + P / 2) for t in beats])
    return round(float(on_b / (off_b + 1e-9)), 2)


def analyze(args):
    tracks = json.load(open(args.tracks, encoding="utf-8"))
    pmap = json.load(open(args.previews, encoding="utf-8")).get("map", {})
    old = {}
    if os.path.exists(args.existing) and not args.force:
        try:
            old = json.load(open(args.existing, encoding="utf-8")).get("map", {})
        except Exception:
            old = {}
    todo = []
    for t in tracks:
        v = pmap.get(key(t)) or {}
        if not v.get("p"):
            continue
        h = fnv32(v["p"])
        o = old.get(key(t))
        if o and len(o) >= 5 and o[4] == h:
            continue
        todo.append((t, v["p"], h))
    mine = todo[args.shard::args.shards]
    if args.limit:
        mine = mine[: args.limit]
    print(f"shard {args.shard}: {len(mine)} of {len(todo)} previews to analyse", flush=True)
    from beat_this.inference import Audio2Beats  # heavy import only in CI
    a2b = Audio2Beats(checkpoint_path=args.model, device="cpu", dbn=False)
    out, n_ok, t0 = {}, 0, time.time()
    with tempfile.TemporaryDirectory() as tmp:
        for i, (t, url, h) in enumerate(mine, 1):
            path = os.path.join(tmp, "p.m4a")
            rec = {"h": h, "cat": t.get("bpm"), "g": t.get("g")}
            try:
                if not fetch(url, path):
                    rec["err"] = "download"
                else:
                    x = decode(path)
                    if x is None:
                        rec["err"] = "decode"
                    else:
                        beats, downs = a2b(x, SR)
                        g = fit_grid(beats, downs, dur=len(x) / SR)
                        if not g:
                            rec["err"] = "nogrid"
                        else:
                            rec.update(g)
                            rec["kick"] = kick_check(x, g)
                            n_ok += 1
            except Exception as e:  # never stop the shard on one bad file
                rec["err"] = "exc:" + str(e)[:80]
            finally:
                try:
                    os.remove(path)  # no audio is kept
                except OSError:
                    pass
            out[key(t)] = rec
            if i % 10 == 0:
                print(f"shard {args.shard}: {i}/{len(mine)} ok={n_ok} ({time.time() - t0:.0f}s)", flush=True)
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"shard {args.shard} done: {len(mine)} analysed, {n_ok} grids")
    return 0


def merge(args):
    tracks = json.load(open(args.tracks, encoding="utf-8"))
    keys = {key(t) for t in tracks}
    pmap = json.load(open(args.previews, encoding="utf-8")).get("map", {})
    old = {}
    if os.path.exists(args.out):
        try:
            old = json.load(open(args.out, encoding="utf-8")).get("map", {})
        except Exception:
            old = {}
    new = {}
    for f in sorted(glob.glob(os.path.join(args.parts, "**", "*.json"), recursive=True)):
        try:
            new.update(json.load(open(f, encoding="utf-8")))
        except Exception as e:
            print("skip", f, e)
    m = {}
    stats = {"grids": 0, "low_conf": 0, "errors": 0, "kick_suspect": 0, "kept": 0}
    report = []
    for k in sorted(keys):
        v = pmap.get(k) or {}
        if not v.get("p"):
            continue
        h = fnv32(v["p"])
        r = new.get(k)
        if r and r.get("h") == h:
            if "bpm" in r:
                m[k] = [r["bpm"], r["b0"], r["db"], r["conf"], h]
                stats["grids"] += 1
                stats["low_conf"] += r["conf"] < 0.5
                stats["kick_suspect"] += (r.get("kick") or 9) < 1.0
                report.append((k, r))
            else:
                stats["errors"] += 1
        elif k in old and len(old[k]) >= 5 and old[k][4] == h:
            m[k] = old[k]
            stats["kept"] += 1
    if not m:
        print("no grids; keeping the existing file")
        return 1
    meta = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "model": "beat_this " + args.model, "tracks": len(keys), "grids": len(m), **stats,
            "note": "Beat grids measured from the Apple Music previews (numbers only; no audio is stored)."}
    tmp = args.out + ".tmp"
    json.dump({"meta": meta, "map": m}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, args.out)
    print("merged", meta)
    # a readable report for the run log: the least trustworthy grids first
    report.sort(key=lambda x: x[1]["conf"])
    for k, r in report[:40]:
        print(f'  conf {r["conf"]:.2f} rms {r["rms"]*1000:.0f}ms cover {r["cover"]:.2f} dbc {r["dbc"]:.2f} kick {r.get("kick")} bpm {r["bpm"]} (catalog {r.get("cat")}) {r.get("g")}  {k}')
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--shard", type=int, default=0)
    a.add_argument("--shards", type=int, default=1)
    a.add_argument("--tracks", default=TRACKS)
    a.add_argument("--previews", default=PREVIEWS)
    a.add_argument("--existing", default=BEATS)
    a.add_argument("--model", default="final0")
    a.add_argument("--limit", type=int, default=0)
    a.add_argument("--force", action="store_true")
    a.add_argument("--out", required=True)
    m = sub.add_parser("merge")
    m.add_argument("--parts", required=True)
    m.add_argument("--tracks", default=TRACKS)
    m.add_argument("--previews", default=PREVIEWS)
    m.add_argument("--model", default="final0")
    m.add_argument("--out", default=BEATS)
    sub.add_parser("selftest")
    x = ap.parse_args()
    if x.cmd == "analyze":
        return analyze(x)
    if x.cmd == "merge":
        return merge(x)
    return selftest()


if __name__ == "__main__":
    sys.exit(main())
