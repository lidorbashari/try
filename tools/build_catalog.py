#!/usr/bin/env python3
"""Aggregate every rendered sidecar into music/catalog.json and build crates/index.json.

Usage: python tools/build_catalog.py
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUSIC = ROOT / "music"
CRATES = ROOT / "crates"


def load_sidecars(folder: Path, pattern: str) -> list[dict]:
    items = []
    for js in sorted(folder.glob(pattern)):
        try:
            data = json.loads(js.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"!! bad json {js.relative_to(ROOT)}: {exc}", file=sys.stderr)
            continue
        mp3 = js.with_suffix(".mp3")
        if not mp3.exists():
            print(f"!! missing audio for {js.relative_to(ROOT)}", file=sys.stderr)
            continue
        data.setdefault("file", str(mp3.relative_to(ROOT)))
        data["size_bytes"] = mp3.stat().st_size
        cover = js.with_suffix(".jpg")
        if cover.exists():
            data.setdefault("cover", str(cover.relative_to(ROOT)))
        items.append(data)
    return items


def plan_order() -> dict[str, int]:
    plan_file = MUSIC / "tracklist.plan.json"
    if not plan_file.exists():
        return {}
    return {t["id"]: i for i, t in enumerate(json.loads(plan_file.read_text(encoding="utf-8")))}


def front_matter(md: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", md, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        val = val.strip()
        if val.startswith("["):
            try:
                out[key.strip()] = json.loads(val)
                continue
            except json.JSONDecodeError:
                pass
        out[key.strip()] = val.strip('"').strip("'")
    return out


def build_crates_index() -> list[dict]:
    index = []
    for md_path in sorted(CRATES.glob("*.md")):
        if md_path.name.upper() == "README.MD":
            continue
        fm = front_matter(md_path.read_text(encoding="utf-8"))
        slug = fm.get("slug") or md_path.stem
        csv_path = md_path.with_suffix(".csv")
        rows = []
        if csv_path.exists():
            with csv_path.open(encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
        verified = sum(1 for r in rows if (r.get("verified") or "").strip().lower() == "yes")
        bpms = [float(r["bpm"]) for r in rows if (r.get("bpm") or "").replace(".", "", 1).isdigit()]
        index.append({
            "slug": slug,
            "title": fm.get("title", slug),
            "title_he": fm.get("title_he", fm.get("title", slug)),
            "genres": fm.get("genres", []),
            "count": len(rows),
            "verified": verified,
            "bpm_min": min(bpms) if bpms else None,
            "bpm_max": max(bpms) if bpms else None,
            "file_csv": str(csv_path.relative_to(ROOT)) if csv_path.exists() else None,
            "file_md": str(md_path.relative_to(ROOT)),
        })
    return index


def main() -> int:
    order = plan_order()
    tracks = load_sidecars(MUSIC / "tracks", "*/*.json")
    tracks.sort(key=lambda t: order.get(t.get("id"), 10_000))
    practice = load_sidecars(MUSIC / "practice", "*.json")
    transitions = load_sidecars(MUSIC / "transitions", "*.json")
    engine_versions = sorted({t.get("engine_version", "?") for t in tracks})
    catalog = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "engine_version": engine_versions[-1] if engine_versions else None,
        "stats": {
            "tracks": len(tracks),
            "practice": len(practice),
            "transitions": len(transitions),
            "genres": len({t.get("genre_slug") for t in tracks}),
            "minutes": round(sum(t.get("duration_sec", 0) for t in tracks) / 60, 1),
            "bytes": sum(t["size_bytes"] for t in tracks + practice + transitions),
        },
        "tracks": tracks,
        "practice": practice,
        "transitions": transitions,
    }
    (MUSIC / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    crates = build_crates_index()
    if CRATES.exists():
        (CRATES / "index.json").write_text(json.dumps(crates, ensure_ascii=False, indent=1), encoding="utf-8")
    s = catalog["stats"]
    print(f"catalog: {s['tracks']} tracks / {s['genres']} genres / {s['minutes']} min, "
          f"{s['practice']} practice, {s['transitions']} transitions, {s['bytes'] / 1e6:.0f} MB")
    print(f"crates: {len(crates)} crates, {sum(c['count'] for c in crates)} real tracks "
          f"({sum(c['verified'] for c in crates)} verified)")
    missing = [t["id"] for t in json.loads((MUSIC / "tracklist.plan.json").read_text(encoding="utf-8"))
               if t["id"] not in {x.get("id") for x in tracks}]
    if missing:
        print(f"not rendered yet ({len(missing)}): {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
