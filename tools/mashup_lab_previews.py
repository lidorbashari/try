#!/usr/bin/env python3
"""Resolve Apple Music 30-second preview links for Mashup Lab (docs/mashup-lab).

Runs on GitHub Actions (.github/workflows/mashup-previews.yml), which can reach the iTunes Search API.
Phones then never call the Search API: the page loads docs/mashup-lab/previews.json, which holds
links only (no audio is downloaded or stored) and starts the original preview right inside the tap.

    python tools/mashup_lab_previews.py resolve --shard 0 --shards 8 --out previews-0.json
    python tools/mashup_lab_previews.py merge --parts parts --out docs/mashup-lab/previews.json

The matching mirrors engine.js (pick): normalised title exact = 6, prefix = 4, contains = 2,
artist match +3, karaoke/instrumental/tribute -3, accept >= 6. Hebrew tracks try the IL store first.
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKS = os.path.join(ROOT, "docs", "mashup-lab", "tracks.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
SITE_ORIGIN = "https://lidorbashari.github.io"
GAP = 3.2          # seconds between Search API calls per runner (Apple allows ~20 calls / minute)
BAD = re.compile(r"karaoke|instrumental|tribute|made famous|in the style of", re.I)


def clean_title(s):
    s = re.sub(r"\s*[\(\[](?:extended|original|radio|club)(?:\s+(?:mix|edit|version))?[\)\]]", "", s or "", flags=re.I)
    return re.sub(r"\s+-\s+(?:extended|original|radio|club)\s+(?:mix|edit)\s*$", "", s, flags=re.I).strip()


def first_artist(s):
    return re.split(r"\s*(?:,|\bfeat\.?\s|\bft\.?\s|\bfeaturing\s|\swith\s|\sx\s|\s×\s|\svs\.?\s)\s*", s or "", flags=re.I)[0].strip()


def norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = re.sub(r"[̀-֑ͯ-ׇ]", "", s)
    s = re.sub(r"[\(\[][^\)\]]*(?:feat|ft\.|with |extended|original|radio|club|edit|version|remaster)[^\)\]]*[\)\]]", " ", s)
    return re.sub(r"[\W_]+", " ", s).strip()


def pick(results, t):
    nt, na, own = norm(clean_title(t["t"])), norm(first_artist(t["a"])), (t["t"] + " " + t["a"]).lower()
    best, bs = None, -1
    for r in results or []:
        if not r or not r.get("previewUrl") or not r.get("trackName"):
            continue
        rt, ra, s = norm(r["trackName"]), norm(r.get("artistName", "")), 0
        if not rt or not nt:
            continue
        if rt == nt:
            s = 6
        elif rt.startswith(nt) or nt.startswith(rt):
            s = 4
        elif nt in rt or rt in nt:
            s = 2
        if na and ra and (na in ra or ra in na):
            s += 3
        m = BAD.search(r["trackName"] + " " + (r.get("collectionName") or "") + " " + (r.get("artistName") or ""))
        if m and m.group(0).lower() not in own:
            s -= 3
        if s > bs:
            bs, best = s, r
    if bs < 6:
        return None
    art = best.get("artworkUrl100")
    return {"p": best["previewUrl"], "a": art.replace("100x100bb", "600x600bb") if art else None}


def key(t):
    return f'{t["t"]} | {t["a"]}'


def hebrew(t):
    return bool(re.search(r"[֐-׿]", t["t"] + " " + t["a"]))


_last = [0.0]


def search(term, country):
    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
        {"term": term, "media": "music", "entity": "song", "limit": 10, "country": country})
    for attempt in range(5):
        wait = _last[0] + GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8", "replace")).get("results", [])
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 500, 502, 503, 504):
                time.sleep(30 * (attempt + 1))  # rate limited or transient: back off
                continue
            return None
        except Exception:
            time.sleep(5 * (attempt + 1))
    return None


def resolve(args):
    tracks = json.load(open(args.tracks, encoding="utf-8"))
    mine = [t for i, t in enumerate(tracks) if i % args.shards == args.shard]
    out, found, missing, errors = {}, 0, 0, 0
    for n, t in enumerate(mine, 1):
        term = (first_artist(t["a"]) + " " + clean_title(t["t"])).strip()
        countries = ["il", "us"] if hebrew(t) else ["us", "il"]
        hit, reached = None, False
        for c in countries:
            res = search(term, c)
            if res is None:
                continue
            reached = True
            hit = pick(res, t)
            if hit:
                break
        if hit:
            out[key(t)] = hit
            found += 1
        elif reached:
            out[key(t)] = {"miss": 1}
            missing += 1
        else:
            errors += 1  # not cached: the app may still try at runtime
        if n % 20 == 0:
            print(f"shard {args.shard}: {n}/{len(mine)} found={found} miss={missing} err={errors}", flush=True)
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"shard {args.shard} done: {len(mine)} tracks, found={found} miss={missing} err={errors}")


def audio_cors(url):
    """Does the preview CDN send CORS headers? Decides whether the app routes previews through Web Audio (EQ, crossfader on iPhone)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Origin": SITE_ORIGIN, "Range": "bytes=0-1"})
        with urllib.request.urlopen(req, timeout=20) as r:
            v = r.headers.get("Access-Control-Allow-Origin")
            return v in ("*", SITE_ORIGIN)
    except Exception:
        return None


def merge(args):
    merged = {}
    for f in sorted(glob.glob(os.path.join(args.parts, "**", "*.json"), recursive=True)):
        try:
            merged.update(json.load(open(f, encoding="utf-8")))
        except Exception as e:
            print("skip", f, e)
    tracks = json.load(open(args.tracks, encoding="utf-8"))
    keys = {key(t) for t in tracks}
    merged = {k: v for k, v in merged.items() if k in keys}
    found = sum(1 for v in merged.values() if v.get("p"))
    sample = next((v["p"] for v in merged.values() if v.get("p")), None)
    meta = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "tracks": len(tracks), "resolved": len(merged), "found": found,
            "audioCors": audio_cors(sample) if sample else None,
            "note": "Apple Music preview links (streamed, courtesy of iTunes). Links only; no audio is stored."}
    if found < min(50, len(tracks) // 4):  # guard: a blocked run must not wipe working links
        print("too few previews found; keeping the existing file", meta)
        return 1
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    tmp = args.out + ".tmp"
    json.dump({"meta": meta, "map": merged}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, args.out)
    print("merged", meta)
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve")
    r.add_argument("--shard", type=int, default=0)
    r.add_argument("--shards", type=int, default=1)
    r.add_argument("--tracks", default=TRACKS)
    r.add_argument("--out", required=True)
    m = sub.add_parser("merge")
    m.add_argument("--parts", required=True)
    m.add_argument("--tracks", default=TRACKS)
    m.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "resolve":
        resolve(a)
        return 0
    return merge(a)


if __name__ == "__main__":
    sys.exit(main())
