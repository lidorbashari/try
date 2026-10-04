#!/usr/bin/env python3
"""Validate crate CSVs against music/SCHEMA.md section 5.

Usage: python .claude/skills/crate-research/scripts/validate_crate.py crates/*.csv
Exit code 1 when any ERROR is found (warnings don't fail).
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))
import camelot  # noqa: E402

HEADER = ["artist", "title", "mix", "label", "year", "bpm", "key", "camelot", "energy", "role", "verified", "notes_he"]
ROLES = {"warmup", "build", "peak", "closing"}
VERIFIED = {"yes", "partial", "no"}
HEBREW = re.compile(r"[֐-׿]")


def check(path: Path) -> tuple[int, int, int]:
    errors = warnings = rows = 0

    def err(line: int, msg: str) -> None:
        nonlocal errors
        errors += 1
        print(f"ERROR {path}:{line}: {msg}")

    def warn(line: int, msg: str) -> None:
        nonlocal warnings
        warnings += 1
        print(f"warn  {path}:{line}: {msg}")

    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        warn(1, "file starts with a UTF-8 BOM (allowed, but plain UTF-8 is preferred)")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            err(1, "empty file")
            return errors, warnings, 0
        if header != HEADER:
            err(1, f"header must be exactly: {','.join(HEADER)}  (got: {','.join(header)})")
            return errors, warnings, 0
        seen = {}
        for i, cols in enumerate(reader, start=2):
            if not any(c.strip() for c in cols):
                continue
            rows += 1
            if len(cols) != len(HEADER):
                err(i, f"{len(cols)} columns, expected {len(HEADER)} (quote fields that contain commas)")
                continue
            r = dict(zip(HEADER, (c.strip() for c in cols)))
            for f in ("artist", "title", "bpm", "key", "camelot", "energy", "role", "verified"):
                if not r[f]:
                    err(i, f"empty `{f}`")
            try:
                bpm = float(r["bpm"])
                if not 60 <= bpm <= 200:
                    err(i, f"bpm {bpm} outside 60-200")
            except ValueError:
                err(i, f"bpm not a number: {r['bpm']!r}")
            k = camelot.parse_key(r["key"])
            if r["key"] and not k:
                err(i, f"unrecognised key {r['key']!r} (use Am, F#m, Db ...)")
            cam = camelot.from_camelot(r["camelot"]) if r["camelot"] else None
            if r["camelot"] and not cam:
                err(i, f"bad camelot {r['camelot']!r} (1A..12B)")
            if k and cam and k.camelot != cam.camelot:
                err(i, f"key {r['key']} is {k.camelot}, but camelot column says {r['camelot']}")
            if k and r["key"] != k.short and r["key"] not in (k.short.replace("m", " minor"),):
                warn(i, f"key {r['key']!r} - SCHEMA short form would be {k.short!r}")
            try:
                e = int(r["energy"])
                if not 1 <= e <= 10:
                    err(i, f"energy {e} outside 1-10")
            except ValueError:
                err(i, f"energy not an integer: {r['energy']!r}")
            if r["role"] and r["role"] not in ROLES:
                err(i, f"role {r['role']!r} not in {sorted(ROLES)}")
            if r["verified"] and r["verified"] not in VERIFIED:
                err(i, f"verified {r['verified']!r} not in {sorted(VERIFIED)}")
            if r["year"] and not re.fullmatch(r"(19[5-9]\d|20[0-4]\d)", r["year"]):
                warn(i, f"odd year {r['year']!r}")
            if not r["notes_he"]:
                warn(i, "empty notes_he")
            elif not HEBREW.search(r["notes_he"]):
                warn(i, "notes_he has no Hebrew text")
            dup = (r["artist"].lower(), r["title"].lower(), r["mix"].lower())
            if dup in seen:
                err(i, f"duplicate of line {seen[dup]}")
            seen[dup] = i
    md = path.with_suffix(".md")
    if not md.exists():
        warn(0, f"missing companion {md.name}")
    return errors, warnings, rows


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv] or sorted((ROOT / "crates").glob("*.csv"))
    total_e = total_w = total_r = 0
    for f in files:
        e, w, r = check(f)
        total_e, total_w, total_r = total_e + e, total_w + w, total_r + r
        print(f"{'OK   ' if not e else 'FAIL '} {f}: {r} rows, {e} errors, {w} warnings")
    # no audio may live in crates/
    audio = [p for p in (ROOT / "crates").rglob("*") if p.suffix.lower() in {".mp3", ".wav", ".flac", ".aiff", ".m4a", ".ogg"}]
    for a in audio:
        print(f"ERROR {a}: audio files are not allowed in crates/ (metadata only)")
    total_e += len(audio)
    print(f"== {len(files)} file(s), {total_r} rows, {total_e} errors, {total_w} warnings")
    return 1 if total_e else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
