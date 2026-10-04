#!/usr/bin/env python3
"""Suggest what to play next - from DJ Lab originals, crates and your analyzed library.

Usage:
  python .claude/skills/harmonic-next-track/scripts/next_track.py "Groove Machine"
  python .claude/skills/harmonic-next-track/scripts/next_track.py house-05 --energy up --top 8
  python .claude/skills/harmonic-next-track/scripts/next_track.py "8A 124"          # key + BPM
  python .claude/skills/harmonic-next-track/scripts/next_track.py "Am 95" --genres reggaeton,mediterranean
Options: --energy up|down|keep, --no-crates, --library PATH (default library/my_library.csv if present),
         --genres a,b, --max-bpm-change 6
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))
import camelot  # noqa: E402
import set_planner as sp  # noqa: E402


def find_seed(query: str, pool: list[sp.Track]) -> sp.Track | None:
    m = re.fullmatch(r"\s*(\S+(?:\s*(?:minor|major|min|maj))?)\s+(\d{2,3}(?:\.\d+)?)\s*", query, re.I)
    if m and camelot.parse_key(m.group(1)):
        k = camelot.parse_key(m.group(1))
        return sp.Track(title=f"{k.short} @ {m.group(2)} BPM", artist="", source="query", genre_slug="", genre="",
                        bpm=float(m.group(2)), camelot=k.camelot, energy=6, duration_sec=300)
    q = sp.norm(query)
    best, best_score = None, 0.0
    for t in pool:
        hay = [sp.norm(t.title), sp.norm(t.ref), sp.norm(f"{t.artist} {t.title}")]
        for h in hay:
            if not h:
                continue
            if q == h or q == sp.norm(Path(t.ref).stem):
                return t
            if q in h:
                score = len(q) / len(h)
                if score > best_score:
                    best, best_score = t, score
    return best


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", help='track title / id / file stem, or "<key> <bpm>" like "8A 124"')
    ap.add_argument("--energy", choices=["up", "down", "keep"], default="keep")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--genres", default="all")
    ap.add_argument("--no-crates", action="store_true")
    ap.add_argument("--library", default=None)
    ap.add_argument("--max-bpm-change", type=float, default=6.0, help="hide candidates beyond this %% (after half/double)")
    args = ap.parse_args(argv)

    pool, _ = sp.load_djlab()
    if not args.no_crates:
        pool += sp.load_crates()
    lib = Path(args.library) if args.library else ROOT / "library" / "my_library.csv"
    if lib.exists():
        pool += sp.load_library(lib)
    elif args.library:
        print(f"!! library CSV not found: {lib}", file=sys.stderr)

    seed = find_seed(args.query, pool)
    if not seed:
        print(f"לא מצאתי טראק בשם \"{args.query}\". נסו מזהה (house-05), חלק מהשם, או \"8A 124\".", file=sys.stderr)
        return 1
    cands = sp.genre_filter([t for t in pool if t is not seed], [g for g in args.genres.split(",") if g])
    want = {"up": 1.0, "down": -1.0, "keep": 0.0}[args.energy]
    scored = []
    for c in cands:
        h = camelot.harmonic_compat(seed.camelot, c.camelot)
        t = camelot.bpm_compat(seed.bpm, c.bpm)
        if abs(t.pct) > args.max_bpm_change:
            continue
        de = c.energy - seed.energy
        e_fit = 1.0 - min(1.0, abs(de - want) / 3.0)
        bonus = 0.1 if c.genre_slug == seed.genre_slug else 0.0
        score = 0.45 * h.score + 0.35 * t.score + 0.2 * e_fit + bonus
        scored.append((score, c, h, t))
    scored.sort(key=lambda x: -x[0])
    print(f"🎧 אחרי: {seed.label}  ({seed.bpm:g} BPM · {seed.camelot or '?'} · אנרגיה {seed.energy:g})"
          f"  [{sp.src_label(seed) if seed.source != 'query' else 'שאילתה'}]")
    print(f"   כיוון אנרגיה: {args.energy} · מועמדים: {len(scored)} מתוך {len(cands)}")
    print()
    for i, (s, c, h, t) in enumerate(scored[: args.top], 1):
        tr = camelot.suggest_transition(seed.as_mix(), c.as_mix())
        verified = "" if not c.source.startswith("crate") or c.verified == "yes" else f" (verified={c.verified})"
        print(f"{i:>2}. {c.label}  —  {c.bpm:g} BPM · {c.camelot or '?'} · E{c.energy:g} · {sp.src_label(c)}{verified}")
        print(f"     {h.label_he} · BPM {t.pct:+.1f}%{' (' + t.mode + ')' if t.mode not in ('direct', 'unknown') else ''}"
              f" · מעבר מומלץ: {tr['technique_he']}  [score {s:.2f}]")
    if not scored:
        print("אין מועמדים בטווח ה-BPM. נסו --max-bpm-change 10 או --genres all.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
