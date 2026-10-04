#!/usr/bin/env python3
"""DJ Lab audio QA: verify rendered MP3s + sidecars.

Usage:
    python tools/verify_audio.py music/tracks                 # all MP3s below a folder
    python tools/verify_audio.py music/tracks/techno/*.mp3    # specific files
    python tools/verify_audio.py --fast music/tracks          # skip the (slow) BPM estimate

Checks per file: duration vs sidecar & bars, leading silence (< 5 ms), BPM (librosa; half/double
allowed), integrated loudness within target ±1.5 LU, true peak ≤ -0.8 dBTP, ID3v2.4 tags present
and consistent with the sidecar, sidecar schema fields, cues on bar boundaries and sorted A–H,
sections on the 8-bar grid. Prints a table; exits 1 if anything fails.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "engine"))

from djlab.analysis import TARGET_LUFS, bpm_ok, estimate_bpm, leading_silence_ms, load_audio  # noqa: E402
from djlab.dsp import lin2db, oversampled_peak  # noqa: E402
from djlab.master import lufs  # noqa: E402

SIDECAR_FIELDS = ["id", "title", "title_he", "artist", "genre", "genre_slug", "family", "bpm", "key", "key_short",
                  "camelot", "energy", "role", "duration_sec", "bars", "beats_per_bar", "first_downbeat_sec",
                  "sections", "cues", "memory_cues", "lufs", "true_peak_dbtp", "file", "cover", "description_he",
                  "mix_tips_he", "instruments", "seed", "license", "engine_version"]
CUE_COLORS = {"A": "#28E214", "B": "#10B1E6", "C": "#E0641B", "D": "#E62828", "E": "#B4BE04", "F": "#DE44CF",
              "G": "#305AFF", "H": "#8A2BE2"}
SR = 44100


def check_tags(mp3: Path, meta: dict, errs: list):
    from mutagen.id3 import ID3

    try:
        t = ID3(str(mp3))
    except Exception as e:  # noqa: BLE001
        errs.append(f"ID3 missing ({e})")
        return
    if t.version[1] != 4:
        errs.append(f"ID3 v2.{t.version[1]} (need 2.4)")
    want = {
        "TIT2": meta.get("title"), "TPE1": "DJ Lab Originals", "TCON": meta.get("genre"),
        "TBPM": str(int(round(float(meta.get("bpm", 0))))), "TKEY": meta.get("key_short"),
        "TDRC": "2026", "TCOP": "CC0 1.0", "TALB": f"DJ Lab — {meta.get('family')} Vol. 1",
    }
    for fid, val in want.items():
        got = t.get(fid)
        got = str(got.text[0]) if got is not None and got.text else None
        if got != val:
            errs.append(f"{fid}={got!r} (want {val!r})")
    comm = [f for k, f in t.items() if k.startswith("COMM")]
    exp_comm = f"Camelot {meta.get('camelot')} · Energy {meta.get('energy')} · CC0"
    if not comm or str(comm[0].text[0]) != exp_comm:
        errs.append("COMM mismatch")
    if not [k for k in t.keys() if k.startswith("APIC")]:
        errs.append("APIC cover missing")


def check_meta(meta: dict, errs: list):
    for f in SIDECAR_FIELDS:
        if f not in meta:
            errs.append(f"sidecar missing {f}")
    if meta.get("first_downbeat_sec") != 0.0:
        errs.append("first_downbeat_sec != 0")
    bpm = float(meta.get("bpm", 0) or 0)
    if not bpm:
        return
    bar_sec = 240.0 / bpm
    secs = meta.get("sections") or []
    pos = 0
    for s in secs:
        if s.get("start_bar") != pos:
            errs.append(f"section {s.get('name')} starts at {s.get('start_bar')} (expected {pos})")
        if s.get("start_bar", 0) % 8 or s.get("bars", 0) % 8:
            if meta.get("genre_slug") not in ("hip_hop", "lofi", "reggaeton", "afrobeats"):
                errs.append(f"section {s.get('name')} not on 8-bar grid")
        pos = s.get("start_bar", 0) + s.get("bars", 0)
    if secs and pos != meta.get("bars"):
        errs.append(f"sections sum {pos} != bars {meta.get('bars')}")
    slots = [c.get("slot") for c in meta.get("cues", [])]
    if slots != sorted(slots) or len(set(slots)) != len(slots):
        errs.append(f"cue slots not unique/sorted: {slots}")
    for c in meta.get("cues", []) + meta.get("memory_cues", []):
        b = c.get("bar")
        if b is None or abs(c.get("sec", -1) - b * bar_sec) > 0.002:
            errs.append(f"cue {c.get('slot', c.get('name'))} sec {c.get('sec')} not on bar {b}")
        if b is not None and not (0 <= b <= meta.get("bars", 0)):
            errs.append(f"cue {c.get('name')} bar {b} out of range")
        if "slot" in c and CUE_COLORS.get(c["slot"]) != c.get("color"):
            errs.append(f"cue {c['slot']} color {c.get('color')}")
    if slots and slots[0] != "A":
        errs.append("hot cue A missing")


def verify(mp3: Path, fast: bool = False) -> dict:
    errs, warns = [], []
    side = mp3.with_suffix(".json")
    meta = {}
    if not side.exists():
        errs.append("sidecar .json missing")
    else:
        try:
            meta = json.loads(side.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            errs.append(f"sidecar invalid JSON: {e}")
    if meta:
        check_meta(meta, errs)
        check_tags(mp3, meta, errs)
        cover = REPO / meta.get("cover", "")
        if not cover.exists():
            errs.append("cover jpg missing")
        elif cover.stat().st_size > 200 * 1024:
            errs.append(f"cover {cover.stat().st_size // 1024} KB > 200 KB")
    x = load_audio(mp3)
    dur = x.shape[0] / SR
    row = {"file": mp3.name, "dur": dur}
    lead = leading_silence_ms(x, SR)
    row["lead_ms"] = lead
    if lead >= 5.0:
        errs.append(f"leading silence {lead:.1f} ms")
    L = lufs(x, SR)
    tp = float(lin2db(oversampled_peak(x).max()))
    row["lufs"], row["tp"] = L, tp
    slug = meta.get("genre_slug", "")
    target = TARGET_LUFS.get(slug, -9.0)
    if abs(L - target) > 1.5:
        errs.append(f"LUFS {L:.2f} outside {target}±1.5")
    if tp > -0.8:
        errs.append(f"true peak {tp:.2f} dBTP > -0.8")
    if meta:
        if abs(meta.get("duration_sec", 0) - dur) > 0.05:
            errs.append(f"duration {dur:.3f} != sidecar {meta.get('duration_sec')}")
        bpm = float(meta.get("bpm", 0))
        if bpm:
            exp = meta.get("bars", 0) * 240.0 / bpm
            if abs(exp - dur) > 0.06:
                errs.append(f"duration {dur:.3f} != bars×bar_len {exp:.3f}")
            if abs(meta.get("lufs", 0) - L) > 0.3:
                warns.append(f"sidecar lufs {meta.get('lufs')} vs measured {L:.2f}")
            if not fast:
                est = estimate_bpm(x, SR, bpm)
                row["bpm_est"] = est
                if not bpm_ok(est, bpm):
                    errs.append(f"BPM estimate {est:.1f} vs {bpm}")
    row["errors"], row["warnings"] = errs, warns
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--fast", action="store_true", help="skip BPM estimation")
    args = ap.parse_args(argv)
    files = []
    for p in args.paths:
        p = Path(p)
        if p.is_dir():
            files += sorted(p.rglob("*.mp3"))
        elif p.suffix.lower() == ".mp3":
            files.append(p)
    files = [f for f in files if not f.name.endswith(".preview.mp3")]
    if not files:
        print("no MP3 files found")
        return 1
    print(f"{'file':<44} {'dur':>7} {'lead':>6} {'LUFS':>6} {'TP':>6} {'BPM~':>6}  status")
    bad = 0
    for f in files:
        try:
            r = verify(f, args.fast)
        except Exception as e:  # noqa: BLE001
            r = {"file": f.name, "errors": [f"{type(e).__name__}: {e}"], "warnings": []}
        ok = not r["errors"]
        bad += 0 if ok else 1
        bpm = f"{r['bpm_est']:.1f}" if "bpm_est" in r else "-"
        if "dur" in r:
            print(f"{r['file'][:44]:<44} {r['dur']:7.1f} {r['lead_ms']:6.1f} {r['lufs']:6.2f} {r['tp']:6.2f} {bpm:>6}  "
                  f"{'OK' if ok else 'FAIL'}")
        else:
            print(f"{r['file'][:44]:<44} {'':>34}  FAIL")
        for e in r["errors"]:
            print(f"    ✗ {e}")
        for w in r["warnings"]:
            print(f"    ! {w}")
    print(f"\n{len(files) - bad}/{len(files)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
