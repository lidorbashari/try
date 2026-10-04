#!/usr/bin/env python3
"""Plan helper for new DJ Lab tracks.

  python .claude/skills/produce-track/scripts/plan_helper.py status [--genre afro_house]
  python .claude/skills/produce-track/scripts/plan_helper.py next --genre afro_house [--count 5]

`status` shows per genre: planned/rendered counts, BPM range, Camelot keys used, recipe present.
`next` proposes the next free ids, unique seeds and Camelot keys that fill gaps next to the genre's existing
keys (so new tracks mix harmonically with old ones). It prints JSON stubs - you still choose titles,
energy/role and write them into music/tracklist.plan.json yourself.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))
import camelot  # noqa: E402

PLAN = ROOT / "music" / "tracklist.plan.json"
GENRES = ROOT / "engine" / "djlab" / "genres"


def load_plan() -> list[dict]:
    return json.loads(PLAN.read_text(encoding="utf-8")) if PLAN.exists() else []


def rendered(t: dict) -> bool:
    return (ROOT / "music" / "tracks" / t["genre_slug"] / f"{t['file_stem']}.mp3").exists()


def cmd_status(args, plan) -> int:
    by = defaultdict(list)
    for t in plan:
        by[t["genre_slug"]].append(t)
    print(f"{'genre':<18}{'family':<12}{'plan':>5}{'mp3':>5}  {'BPM':<9} recipe  keys")
    for g in sorted(by):
        if args.genre and g != args.genre:
            continue
        ts = by[g]
        bpms = [t["bpm"] for t in ts]
        rec = "yes" if (GENRES / f"{g}.py").exists() else "NO"
        keys = " ".join(sorted({t["camelot"] for t in ts}, key=lambda c: (int(c[:-1]), c[-1])))
        print(f"{g:<18}{ts[0]['family']:<12}{len(ts):>5}{sum(rendered(t) for t in ts):>5}  "
              f"{min(bpms):g}-{max(bpms):g}{'':<3} {rec:<7} {keys}")
    seeds = [t["seed"] for t in plan]
    dup = {s for s in seeds if seeds.count(s) > 1}
    ids = [t["id"] for t in plan]
    dupi = {i for i in ids if ids.count(i) > 1}
    bad = [t["id"] for t in plan if camelot.to_camelot(t.get("key_short")) != t.get("camelot")]
    print(f"\n{len(plan)} tracks · duplicate seeds: {sorted(dup) or 'none'} · duplicate ids: {sorted(dupi) or 'none'}"
          f" · key/camelot mismatches: {bad or 'none'}")
    return 1 if dup or dupi or bad else 0


def cmd_next(args, plan) -> int:
    same = [t for t in plan if t["genre_slug"] == args.genre]
    family = args.family or (same[0]["family"] if same else None)
    if not family:
        print("unknown genre - pass --family house|techno|mainstream|breadth", file=sys.stderr)
        return 2
    nums = [int(m.group(1)) for t in plan if (m := re.fullmatch(rf"{family}-(\d+)", t["id"]))]
    nxt = max(nums, default=0) + 1
    used_seeds = {t["seed"] for t in plan}
    seed = max(used_seeds, default=1000) + 17
    keys_have = [t["camelot"] for t in same] or ["8A"]
    # candidate keys: wheel neighbours of existing keys, most-connected first, unused first
    score = defaultdict(float)
    for k in keys_have:
        for c, h in camelot.compatible_keys(k):
            if h.score >= 0.85:
                score[c] += h.score
    minor_bias = sum(k.endswith("A") for k in keys_have) >= len(keys_have) / 2
    cands = sorted(score, key=lambda c: (c in keys_have, -(score[c] + (0.3 if c.endswith("A") == minor_bias else 0))))
    bpms = sorted(t["bpm"] for t in same) or [124]
    stubs = []
    for i in range(args.count):
        while seed in used_seeds:
            seed += 1
        cam = cands[i % len(cands)] if cands else "8A"
        k = camelot.from_camelot(cam)
        stubs.append({
            "id": f"{family}-{nxt + i:02d}", "file_stem": f"{family}-{nxt + i:02d}-<kebab-title>",
            "family": family, "genre_slug": args.genre, "genre": same[0]["genre"] if same else "<Display Genre>",
            "bpm": bpms[len(bpms) // 2], "key": k.long, "key_short": k.short, "camelot": cam,
            "energy": "<1-10>", "role": "<warmup|build|peak|closing>", "title": "<English title>",
            "title_he": "<שם בעברית>", "target_minutes": same[0]["target_minutes"] if same else 4.5,
            "seed": seed, "producer": same[0].get("producer", family) if same else family,
        })
        used_seeds.add(seed)
        seed += 17
    print(json.dumps(stubs, ensure_ascii=False, indent=1))
    if not (GENRES / f"{args.genre}.py").exists():
        print(f"\n⚠ no recipe engine/djlab/genres/{args.genre}.py yet - run the new-genre skill first.", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("status")
    p.add_argument("--genre")
    p = sub.add_parser("next")
    p.add_argument("--genre", required=True)
    p.add_argument("--family")
    p.add_argument("--count", type=int, default=1)
    args = ap.parse_args(argv)
    plan = load_plan()
    return cmd_status(args, plan) if args.cmd == "status" else cmd_next(args, plan)


if __name__ == "__main__":
    sys.exit(main())
