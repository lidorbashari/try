"""Command line: ``python -m djlab {list,render,analyze}``."""
from __future__ import annotations

import argparse
import sys
import time


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="djlab", description="DJ Lab synthesis engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list tracks in the plan and whether a recipe exists")

    r = sub.add_parser("render", help="render tracks from music/tracklist.plan.json")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", nargs="+", help="track id(s), e.g. house-05")
    g.add_argument("--genre", help="genre_slug, e.g. tech_house")
    g.add_argument("--family", help="family: house|techno|mainstream|breadth")
    g.add_argument("--all", action="store_true")
    r.add_argument("--preview", action="store_true", help="render ~16 bars around the first drop to scratch")
    r.add_argument("--jobs", type=int, default=1, help="parallel processes")
    r.add_argument("--out", help="output directory override")

    a = sub.add_parser("analyze", help="objective audio report for an MP3/WAV")
    a.add_argument("files", nargs="+")
    a.add_argument("--genre", help="genre_slug for the reference curve (default: from sidecar)")
    a.add_argument("--bpm", type=float)
    a.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if args.cmd == "list":
        from .genres import available
        from .render import load_plan

        have = set(available())
        for e in load_plan():
            mark = "✓" if e["genre_slug"] in have else "·"
            print(f"{mark} {e['id']:<14} {e['genre_slug']:<16} {e['bpm']:>6} {e['key_short']:<4} {e['camelot']:<4} "
                  f"{e['target_minutes']:>4}m  {e['title']}")
        return 0

    if args.cmd == "render":
        from .render import load_plan, render_many

        plan = load_plan()
        if args.id:
            sel = [e for e in plan if e["id"] in set(args.id)]
            missing = set(args.id) - {e["id"] for e in sel}
            if missing:
                print(f"unknown id(s): {sorted(missing)}", file=sys.stderr)
                return 2
        elif args.genre:
            sel = [e for e in plan if e["genre_slug"] == args.genre]
        elif args.family:
            sel = [e for e in plan if e["family"] == args.family]
        else:
            sel = plan
        if not sel:
            print("nothing selected", file=sys.stderr)
            return 2
        t0 = time.time()
        if args.out:
            from pathlib import Path

            from .render import render_track
            res = [render_track(p, preview=args.preview, out_dir=Path(args.out)) for p in sel]
        else:
            res = render_many(sel, preview=args.preview, jobs=args.jobs)
        bad = [x for x in res if "error" in x]
        print(f"\nrendered {len(res) - len(bad)}/{len(res)} in {time.time() - t0:.1f}s")
        for x in bad:
            print(f"  FAILED {x['id']}: {x['error']}", file=sys.stderr)
        return 1 if bad else 0

    if args.cmd == "analyze":
        from .analysis import analyze_file, format_report
        import json

        rc = 0
        for f in args.files:
            rep = analyze_file(f, genre=args.genre, bpm=args.bpm)
            print(json.dumps(rep, indent=1, ensure_ascii=False) if args.json else format_report(rep))
            rc |= 0 if rep.get("ok", True) else 1
        return rc
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
