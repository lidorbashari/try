#!/usr/bin/env python3
"""Build a Rekordbox XML library (beatgrids + hot cues + memory cues + playlists) from music/catalog.json.

Rekordbox needs absolute file paths, so the XML is tied to where the DJ Lab folder lives on your computer.

  python tools/build_rekordbox_xml.py                         # the two ready-made presets (see below)
  python tools/build_rekordbox_xml.py --root "D:/Music/DJ-Lab" # your own location (folder that contains music/)

Presets written to music/rekordbox/:
  rekordbox-windows.xml  -> repo extracted to  C:\\DJ-Lab
  rekordbox-mac.xml      -> repo extracted to  /Users/Shared/DJ-Lab

Import: Rekordbox > Preferences > Advanced > Database > "rekordbox xml" > Imported Library > Browse,
then enable the "rekordbox xml" node in the tree view, right-click a playlist > Import Playlist.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import quoteattr

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "music" / "catalog.json"
OUT_DIR = ROOT / "music" / "rekordbox"

PRESETS = {
    "rekordbox-windows.xml": "C:/DJ-Lab",
    "rekordbox-mac.xml": "/Users/Shared/DJ-Lab",
}

FAMILY_NAMES = {"house": "House Family", "techno": "Techno Family",
                "mainstream": "Mainstream & Mediterranean", "breadth": "More Genres"}


def location(root: str, rel: str) -> str:
    root = root.replace("\\", "/").rstrip("/")
    path = f"{root}/{rel}"
    if not path.startswith("/"):
        path = "/" + path  # Windows drive letter: file://localhost/C:/...
    return "file://localhost" + quote(path, safe="/:")


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def attrs(**kw) -> str:
    return " ".join(f"{k}={quoteattr(str(v))}" for k, v in kw.items())


def track_xml(tid: int, item: dict, root: str) -> str:
    bpm = float(item.get("bpm", 0) or 0)
    a = attrs(
        TrackID=tid, Name=item.get("title", item["id"]), Artist=item.get("artist", "DJ Lab Originals"),
        Composer="", Album=item.get("album", f"DJ Lab — {item.get('family', item.get('kind', 'extras')).title()} Vol. 1"),
        Grouping=item.get("family", item.get("kind", "")), Genre=item.get("genre", item.get("kind", "Practice").title()),
        Kind="MP3 File", Size=item.get("size_bytes", 0), TotalTime=int(round(item.get("duration_sec", 0))),
        DiscNumber=0, TrackNumber=0, Year=2026, AverageBpm=f"{bpm:.2f}", DateAdded="2026-10-04",
        BitRate=320, SampleRate=44100,
        Comments=f"Camelot {item.get('camelot', '-')} · Energy {item.get('energy', '-')} · CC0 DJ Lab",
        PlayCount=0, Rating=0, Location=location(root, item["file"]), Remixer="",
        Tonality=item.get("key_short", ""), Label="DJ Lab", Mix="Original Mix",
    )
    lines = [f'    <TRACK {a}>']
    if bpm:
        inizio = float(item.get("first_downbeat_sec", 0.0))
        # Demos that switch decks mid-way carry a tempo_map ([{bar, bpm}, ...]): one TEMPO per segment.
        segments = sorted(item.get("tempo_map") or [{"bar": 0, "bpm": bpm}], key=lambda s: s["bar"])
        prev_bar, prev_bpm = 0, None
        for seg in segments:
            if prev_bpm is not None:
                inizio += (seg["bar"] - prev_bar) * 240.0 / prev_bpm
            prev_bar, prev_bpm = seg["bar"], float(seg["bpm"])
            tempo = attrs(Inizio=f"{inizio:.3f}", Bpm=f"{prev_bpm:.2f}", Metro="4/4", Battito=1)
            lines.append(f"      <TEMPO {tempo}/>")
    for cue in item.get("cues", []):
        slot = cue.get("slot", "A")
        num = "ABCDEFGH".index(slot) if slot in "ABCDEFGH" else 0
        r, g, b = rgb(cue.get("color", "#28E214"))
        start = f"{cue['sec']:.3f}"
        mark = attrs(Name=cue.get("name", slot), Type=0, Start=start, Num=num, Red=r, Green=g, Blue=b)
        lines.append(f"      <POSITION_MARK {mark}/>")
    for cue in item.get("memory_cues", []):
        start = f"{cue['sec']:.3f}"
        lines.append(f"      <POSITION_MARK {attrs(Name=cue.get('name', ''), Type=0, Start=start, Num=-1)}/>")
    lines.append("    </TRACK>")
    return "\n".join(lines)


def playlist(name: str, keys: list[int], indent: str) -> str:
    inner = "".join(f'\n{indent}  <TRACK Key="{k}"/>' for k in keys)
    return f'{indent}<NODE {attrs(Name=name, Type=1, KeyType=0, Entries=len(keys))}>{inner}\n{indent}</NODE>'


def folder(name: str, children: list[str], indent: str) -> str:
    body = "\n".join(children)
    return f'{indent}<NODE {attrs(Type=0, Name=name, Count=len(children))}>\n{body}\n{indent}</NODE>'


def build(catalog: dict, root: str) -> str:
    items = catalog["tracks"] + catalog.get("practice", []) + catalog.get("transitions", [])
    ids = {item["id"]: i + 1 for i, item in enumerate(items)}
    collection = "\n".join(track_xml(ids[item["id"]], item, root) for item in items)

    ind = "        "
    fams = []
    for fam, label in FAMILY_NAMES.items():
        fam_tracks = [t for t in catalog["tracks"] if t.get("family") == fam]
        if not fam_tracks:
            continue
        genres = []
        for g in dict.fromkeys(t["genre_slug"] for t in fam_tracks):
            gt = [t for t in fam_tracks if t["genre_slug"] == g]
            genres.append(playlist(gt[0]["genre"].split(" / ")[0] if len({x['genre'] for x in gt}) == 1 else g.replace("_", " ").title(),
                                   [ids[t["id"]] for t in gt], ind + "  "))
        genres.insert(0, playlist(f"All {label}", [ids[t["id"]] for t in fam_tracks], ind + "  "))
        fams.append(folder(label, genres, ind))
    by_energy = sorted(catalog["tracks"], key=lambda t: (t.get("energy", 0), t.get("bpm", 0)))
    smart = [
        playlist("Warm-up (energy 1-5)", [ids[t["id"]] for t in by_energy if t.get("energy", 0) <= 5], ind + "  "),
        playlist("Build (energy 6-7)", [ids[t["id"]] for t in by_energy if 6 <= t.get("energy", 0) <= 7], ind + "  "),
        playlist("Peak (energy 8-10)", [ids[t["id"]] for t in by_energy if t.get("energy", 0) >= 8], ind + "  "),
    ]
    fams.append(folder("By Energy", smart, ind))
    if catalog.get("practice"):
        fams.append(playlist("Practice Drills", [ids[t["id"]] for t in catalog["practice"]], ind))
    if catalog.get("transitions"):
        fams.append(playlist("Transition Demos", [ids[t["id"]] for t in catalog["transitions"]], ind))
    fams.insert(0, playlist("All DJ Lab Tracks", [ids[t["id"]] for t in catalog["tracks"]], ind))

    dj_lab = folder("DJ Lab", fams, "      ")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<DJ_PLAYLISTS Version="1.0.0">\n'
        '  <PRODUCT Name="rekordbox" Version="7.0.0" Company="AlphaTheta"/>\n'
        f'  <COLLECTION Entries="{len(items)}">\n{collection}\n  </COLLECTION>\n'
        '  <PLAYLISTS>\n'
        f'    <NODE Type="0" Name="ROOT" Count="1">\n{dj_lab}\n    </NODE>\n'
        '  </PLAYLISTS>\n'
        '</DJ_PLAYLISTS>\n'
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="absolute path of the DJ-Lab folder (the one that contains music/) on your computer")
    ap.add_argument("--out", help="output file (default: music/rekordbox/rekordbox-custom.xml)")
    args = ap.parse_args()
    if not CATALOG.exists():
        print("music/catalog.json missing — run tools/build_catalog.py first", file=sys.stderr)
        return 1
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = {args.out or str(OUT_DIR / "rekordbox-custom.xml"): args.root} if args.root else \
        {str(OUT_DIR / name): root for name, root in PRESETS.items()}
    import xml.dom.minidom
    for out, root in targets.items():
        xml_text = build(catalog, root)
        xml.dom.minidom.parseString(xml_text.encode("utf-8"))  # well-formedness check
        Path(out).write_text(xml_text, encoding="utf-8")
        print(f"wrote {Path(out).relative_to(ROOT) if Path(out).is_relative_to(ROOT) else out} "
              f"({len(catalog['tracks'])} tracks, root={root})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
