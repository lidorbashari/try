#!/usr/bin/env python3
"""Plan a DJ set: order tracks along an energy curve with harmonic (Camelot) and BPM-friendly transitions.

Sources (combined):
  * DJ Lab originals  - music/catalog.json, else rendered sidecars, else music/tracklist.plan.json
  * crates/*.csv      - real commercial tracks (metadata only)   [--include-crates]
  * your library CSV  - output of tools/analyze_library.py       [--library library/my_library.csv]

Search: beam search (greedy = --beam 1) over a cost made of energy-curve distance, Camelot compatibility,
BPM change (half/double aware), energy jumps, genre switches and repeated artists.

Examples:
  python tools/set_planner.py --minutes 60 --start-energy 4 --peak-energy 9 --genres house,tech_house,afro_house
  python tools/set_planner.py --minutes 90 --genres techno,melodic_techno --include-crates --out sets/techno-90.md
  python tools/set_planner.py --minutes 45 --genres all --library library/my_library.csv --curve flat --json x.json
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import camelot  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SHORT_FORM = {"hip_hop", "reggaeton", "afrobeats", "pop_dance", "mediterranean", "lofi", "moombahton"}
ALIASES = {
    "hiphop": "hip_hop", "hip-hop": "hip_hop", "rap": "hip_hop", "afro": "afro_house", "melodic": "melodic_techno",
    "tech": "tech_house", "techhouse": "tech_house", "deep": "deep_house", "drum_and_bass": "dnb",
    "drum_n_bass": "dnb", "dnb": "dnb", "mizrahit": "mediterranean", "mizrahi": "mediterranean",
    "ים_תיכוני": "mediterranean", "מזרחית": "mediterranean", "psy": "psytrance", "garage": "ukg",
    "uk_garage": "ukg", "disco": "nu_disco", "nudisco": "nu_disco", "lo_fi": "lofi", "edm": "big_room",
    "pop": "pop_dance", "hard": "hard_techno", "hypnotic": "hypnotic_techno",
}


def norm(s: object) -> str:
    s = str(s or "").strip().lower().replace("&", " ")
    s = re.sub(r"[^0-9a-z֐-׿]+", "_", s).strip("_")
    return ALIASES.get(s, s)


@dataclass
class Track:
    title: str
    artist: str
    source: str               # "djlab" | "crate:<slug>" | "library"
    genre_slug: str
    genre: str
    bpm: float
    camelot: str
    energy: float
    duration_sec: float
    role: str = ""
    ref: str = ""             # id / file / path
    verified: str = "yes"
    match_keys: set = field(default_factory=set)
    tag_words: set = field(default_factory=set)

    @property
    def label(self) -> str:
        return f"{self.title} — {self.artist}" if self.artist else self.title

    @property
    def play_sec(self) -> float:
        """Time this track occupies in the set (full length minus the overlap with the next track)."""
        overlap_bars = 8 if self.genre_slug in SHORT_FORM else 32
        overlap = overlap_bars * 4 * 60.0 / max(self.bpm, 60.0)
        return max(75.0, min(self.duration_sec - overlap, self.duration_sec * 0.8))

    def as_mix(self) -> dict:
        return {"bpm": self.bpm, "camelot": self.camelot, "energy": self.energy, "genre_slug": self.genre_slug}


def _f(v, default=None):
    try:
        x = float(str(v).replace(",", "."))
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ loaders
def load_djlab() -> tuple[list[Track], str]:
    cat = ROOT / "music" / "catalog.json"
    items, origin = [], ""
    if cat.exists():
        try:
            items = json.loads(cat.read_text(encoding="utf-8")).get("tracks", [])
            origin = "music/catalog.json"
        except json.JSONDecodeError:
            items = []
    if not items:
        for js in sorted((ROOT / "music" / "tracks").glob("*/*.json")):
            try:
                items.append(json.loads(js.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass
        origin = "music/tracks/*/*.json" if items else ""
    if not items:
        plan = ROOT / "music" / "tracklist.plan.json"
        if plan.exists():
            items = json.loads(plan.read_text(encoding="utf-8"))
            for it in items:
                it.setdefault("duration_sec", float(it.get("target_minutes", 4.5)) * 60)
            origin = "music/tracklist.plan.json (not rendered yet)"
    out = []
    for it in items:
        bpm = _f(it.get("bpm"))
        if not bpm:
            continue
        slug = it.get("genre_slug", "")
        out.append(Track(
            title=it.get("title", it.get("id", "?")), artist=it.get("artist", "DJ Lab Originals"), source="djlab",
            genre_slug=slug, genre=it.get("genre", slug), bpm=bpm,
            camelot=it.get("camelot") or camelot.to_camelot(it.get("key_short") or it.get("key")),
            energy=_f(it.get("energy"), 5.0), duration_sec=_f(it.get("duration_sec"), 270.0),
            role=it.get("role", ""), ref=it.get("file") or it.get("id", ""),
            match_keys={norm(slug), norm(it.get("genre")), "family:" + norm(it.get("family"))},
        ))
    return out, origin


def load_crates() -> list[Track]:
    cdir = ROOT / "crates"
    index = {}
    idx_file = cdir / "index.json"
    if idx_file.exists():
        try:
            for c in json.loads(idx_file.read_text(encoding="utf-8")):
                index[c.get("slug")] = c
        except json.JSONDecodeError:
            pass
    out = []
    for csv_path in sorted(cdir.glob("*.csv")):
        slug = csv_path.stem
        meta = index.get(slug, {})
        genres = [norm(g) for g in meta.get("genres", [])] or [norm(slug)]
        with csv_path.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                bpm = _f(r.get("bpm"))
                if not bpm:
                    continue
                cam = r.get("camelot") or camelot.to_camelot(r.get("key"))
                cam = camelot.to_camelot(cam) or ""
                bpm_f = bpm
                club = bpm_f >= 115 and genres[0] not in SHORT_FORM
                title = r.get("title", "?")
                if r.get("mix") and r["mix"].lower() not in {"original mix", ""}:
                    title = f"{title} ({r['mix']})"
                out.append(Track(
                    title=title, artist=r.get("artist", ""), source=f"crate:{slug}", genre_slug=genres[0],
                    genre=meta.get("title") or slug.replace("-", " ").replace("_", " ").title(), bpm=bpm_f, camelot=cam, energy=_f(r.get("energy"), 5.0),
                    duration_sec=390.0 if club else 210.0, role=r.get("role", ""), ref=r.get("label", ""),
                    verified=(r.get("verified") or "no").strip().lower(),
                    match_keys=set(genres) | {norm(slug)},
                ))
    return out


def load_library(path: Path) -> list[Track]:
    out = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("error"):
                continue
            bpm = _f(r.get("bpm"))
            if not bpm:
                continue
            g = r.get("genre_tag", "")
            title = r.get("title") or Path(r.get("path", "?")).stem
            out.append(Track(
                title=title, artist=r.get("artist", ""), source="library", genre_slug=norm(g), genre=g or "?",
                bpm=bpm, camelot=r.get("camelot", ""), energy=_f(r.get("energy_est"), 5.0),
                duration_sec=_f(r.get("duration_sec"), 300.0), ref=r.get("path", ""),
                match_keys={norm(g)} if g else set(), tag_words=set(norm(g).split("_")) if g else set(),
            ))
    return out


def genre_filter(tracks: list[Track], tokens: list[str]) -> list[Track]:
    if not tokens or tokens == ["all"]:
        return tracks
    toks = [t if t.startswith("family:") else norm(t) for t in tokens]
    sel_bpms = [t.bpm for t in tracks if t.match_keys & set(toks)]
    lo, hi = (min(sel_bpms) - 3, max(sel_bpms) + 3) if sel_bpms else (0, 999)
    out = []
    for t in tracks:
        if t.match_keys & set(toks):
            out.append(t)
        elif t.source == "library":
            if t.tag_words and any(set(tok.split("_")) <= t.tag_words for tok in toks if ":" not in tok):
                out.append(t)
            elif not t.tag_words and lo <= t.bpm <= hi:
                out.append(t)  # untagged library track inside the selected genres' BPM range
    return out


# ------------------------------------------------------------------ energy curves
def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def target_energy(p: float, start: float, peak: float, end: float, curve: str) -> float:
    if curve == "ramp":
        return start + (peak - start) * _smooth(p / 0.9)
    if curve == "flat":
        return start + (peak - start) * _smooth(p / 0.2)
    if curve == "wave":
        pts = [(0, start), (0.38, peak - 1), (0.55, (start + peak) / 2 + 0.5), (0.85, peak), (1.0, end)]
    else:  # arc
        pts = [(0, start), (0.72, peak), (1.0, end)]
    for (p0, e0), (p1, e1) in zip(pts, pts[1:]):
        if p <= p1:
            return e0 + (e1 - e0) * _smooth((p - p0) / (p1 - p0))
    return pts[-1][1]


# ------------------------------------------------------------------ search
@dataclass
class Weights:
    energy: float = 1.0
    jump: float = 0.8
    key: float = 3.0
    bpm: float = 3.5
    bpm_drop: float = 0.12
    genre: float = 0.35
    artist: float = 1.5
    unverified: float = 0.4
    prefer: float = 0.4


def step_cost(prev: Track | None, c: Track, target: float, w: Weights, prefer: str, falling: bool) -> float:
    cost = w.energy * abs(c.energy - target)
    if c.source.startswith("crate") and c.verified == "no":
        cost += w.unverified
    elif c.source.startswith("crate") and c.verified == "partial":
        cost += w.unverified / 2
    if prefer and c.source.startswith(prefer):
        cost -= w.prefer
    if prev is None:
        return cost + 0.01 * c.bpm
    h = camelot.harmonic_compat(prev.camelot, c.camelot)
    t = camelot.bpm_compat(prev.bpm, c.bpm)
    cost += w.key * (1 - h.score) + w.bpm * (1 - t.score)
    if t.pct < 0 and not falling:
        cost += w.bpm_drop * min(10.0, -t.pct)
    cost += w.jump * max(0.0, abs(c.energy - prev.energy) - 2)
    if c.genre_slug != prev.genre_slug:
        cost += w.genre
    if c.artist and prev.artist and c.artist == prev.artist and c.source != "djlab":
        cost += w.artist
    return cost


def plan_set(pool: list[Track], minutes: float, start: float, peak: float, end: float, curve: str,
             beam: int = 16, branch: int = 10, prefer: str = "", w: Weights | None = None) -> list[Track]:
    w = w or Weights()
    total = minutes * 60.0
    States = list[tuple[float, list[int], float]]
    states: States = [(0.0, [], 0.0)]
    finished: States = []
    while states:
        nxt: States = []
        for cost, seq, used in states:
            if used >= total - 30:
                finished.append((cost, seq, used))
                continue
            prev = pool[seq[-1]] if seq else None
            cands = []
            for i, c in enumerate(pool):
                if i in seq:
                    continue
                p = min(1.0, (used + c.play_sec / 2) / total)
                tgt = target_energy(p, start, peak, end, curve)
                falling = target_energy(min(1.0, p + 0.05), start, peak, end, curve) < tgt - 0.05
                cands.append((step_cost(prev, c, tgt, w, prefer, falling), i))
            if not cands:
                finished.append((cost, seq, used))
                continue
            cands.sort()
            for sc, i in cands[:branch]:
                nxt.append((cost + sc, seq + [i], used + pool[i].play_sec))
        nxt.sort(key=lambda s: (s[0] / max(1, len(s[1])), s[1]))
        states = nxt[:beam]
    if not finished:
        return []

    def final_score(s):
        cost, seq, used = s
        short = max(0.0, total - used) / 60.0
        over = max(0.0, used - total - 120) / 60.0
        return cost / max(1, len(seq)) + 1.5 * short + 0.5 * over

    best = min(finished, key=final_score)
    return [pool[i] for i in best[1]]


# ------------------------------------------------------------------ output
SRC_HE = {"djlab": "DJ Lab", "library": "הספרייה שלך"}


def src_label(t: Track) -> str:
    if t.source.startswith("crate:"):
        return "crate " + t.source.split(":", 1)[1]
    return SRC_HE.get(t.source, t.source)


def mmss(sec: float) -> str:
    return f"{int(sec // 60):02d}:{int(sec % 60):02d}"


def build_rows(seq: list[Track], minutes: float, start: float, peak: float, end: float, curve: str) -> list[dict]:
    rows, t0 = [], 0.0
    total = minutes * 60
    for i, t in enumerate(seq):
        p = min(1.0, (t0 + t.play_sec / 2) / total)
        row = {"n": i + 1, "start": mmss(t0), "track": t, "target": round(target_energy(p, start, peak, end, curve), 1)}
        if i + 1 < len(seq):
            nx = seq[i + 1]
            tr = camelot.suggest_transition(t.as_mix(), nx.as_mix())
            row["transition"] = tr
        rows.append(row)
        t0 += t.play_sec
    return rows


def print_table(rows: list[dict]) -> None:
    hdr = f"{'#':>2}  {'start':5}  {'BPM':>6}  {'key':>4}  {'E':>2}/{'tgt':<4} {'source':<16} track  →  transition"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        t: Track = r["track"]
        tr = r.get("transition")
        nxt = ""
        if tr:
            nxt = (f"  →  {tr['technique_he']} | {tr['harmony'].label_he} | "
                   f"BPM {tr['tempo'].pct:+.1f}%" + (f" ({tr['tempo'].mode})" if tr["tempo"].mode not in ("direct", "unknown") else ""))
        print(f"{r['n']:>2}  {r['start']:5}  {t.bpm:6.1f}  {t.camelot or '?':>4}  {int(t.energy):>2}/{r['target']:<4} "
              f"{src_label(t)[:16]:<16} {t.label}{nxt}")


def energy_chart(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        t: Track = r["track"]
        e2, tgt = int(round(t.energy * 2)), int(round(r["target"] * 2))
        cells = ["█" if j < e2 else " " for j in range(20)]
        if 1 <= tgt <= 20:
            cells[tgt - 1] = "|"
        lines.append(f"{r['n']:>2} {r['start']} {''.join(cells)} {int(t.energy)}")
    return "\n".join(lines)


def to_markdown(rows: list[dict], args, origin: str, title: str) -> str:
    now = dt.datetime.now().strftime("%Y-%m-%d")
    total = sum(r["track"].play_sec for r in rows) / 60
    genres = [g for g in (args.genres or "all").split(",") if g]
    L = ["---",
         f'title: "{title}"',
         f"minutes: {args.minutes:g}",
         f"genres: {json.dumps(genres, ensure_ascii=False)}",
         f"curve: {args.curve}",
         f"start_energy: {args.start_energy:g}",
         f"peak_energy: {args.peak_energy:g}",
         f"tracks: {len(rows)}",
         f"generated_by: tools/set_planner.py",
         f"generated_at: {now}",
         "---", "",
         f"# {title}", "",
         f"סט של כ-{total:.0f} דקות ({len(rows)} טראקים), עקומת אנרגיה `{args.curve}` מ-{args.start_energy:g} עד "
         f"{args.peak_energy:g}. סדר הטראקים נבחר כך שכל מעבר יהיה הרמוני (Camelot) ובטווח BPM נוח.", "",
         "> 💡 הזמנים הם הערכה: כל טראק \"תופס\" את האורך שלו פחות החפיפה עם הבא (32 תיבות בהאוס/טכנו, "
         "8 תיבות בהיפ-הופ/רגאטון).", "",
         "## רשימת הטראקים", "",
         "| # | זמן | טראק | מקור | ז'אנר | BPM | Key | אנרגיה (יעד) | מעבר לטראק הבא |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        t: Track = r["track"]
        tr = r.get("transition")
        nxt = f"{tr['technique_he']} · {tr['harmony'].label_he} · BPM {tr['tempo'].pct:+.1f}%" if tr else "סוף הסט 🎉"
        name = t.label.replace("|", "/")
        L.append(f"| {r['n']} | {r['start']} | {name} | {src_label(t)} | {t.genre} | {t.bpm:g} | "
                 f"`{t.camelot or '?'}` | {int(t.energy)} ({r['target']}) | {nxt} |")
    L += ["", "## עקומת האנרגיה", "", "```", energy_chart(rows), "```", "",
          "(`█` = אנרגיית הטראק, `|` = היעד בעקומה)", "", "## איך לבצע כל מעבר", ""]
    for i, r in enumerate(rows[:-1]):
        t, nx, tr = r["track"], rows[i + 1]["track"], r["transition"]
        L.append(f"**{r['n']} → {r['n'] + 1}: {t.title} → {nx.title}** — {tr['technique_he']} "
                 f"(`{t.camelot or '?'}`→`{nx.camelot or '?'}`, {t.bpm:g}→{nx.bpm:g} BPM)")
        L.append(f"- {tr['tip_he']}")
        if tr["tempo"].mode in ("half", "double"):
            L.append("- שימו לב: מעבר בין טמפו כפול/חצי — הביט מסתנכרן, אבל התחושה משתנה. עדיף קאט נקי על ה-1.")
        if abs(tr["tempo"].pct) > 6:
            L.append("- הפרש BPM גדול: אל תמתחו את הטמפו יותר מ-~6% — עדיף Echo Out ולהתחיל את הבא בטמפו שלו.")
        L.append("")
    srcs = {r["track"].source for r in rows}
    L += ["## מקורות ורישוי", ""]
    if "djlab" in srcs:
        L.append(f"- טראקים של **DJ Lab Originals** הם מקוריים ברישיון CC0 — נמצאים בתיקייה `music/tracks/` "
                 f"(מקור הנתונים: `{origin}`).")
    if any(s.startswith("crate:") for s in srcs):
        L.append("- טראקים מה-`crates/` הם שירים מסחריים אמיתיים — **לא נמצאים ברפו**. קנו אותם באופן חוקי "
                 "(Beatport, Bandcamp, Traxsource, iTunes) או נגנו דרך שירות סטרימינג שמחובר ל-Rekordbox. "
                 "בדקו BPM/Key ב-Rekordbox לפני ההופעה (במיוחד שורות עם `verified` שאינו `yes`).")
    if "library" in srcs:
        L.append("- טראקים מ**הספרייה שלך** נותחו ע\"י `tools/analyze_library.py` — הערכים הם הערכה; ודאו Beatgrid ו-Key "
                 "ב-Rekordbox.")
    L += ["", f"_נוצר אוטומטית ע\"י `tools/set_planner.py` ({now}). פקודה:_ `{' '.join(['python', 'tools/set_planner.py'] + sys.argv[1:])}`", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minutes", type=float, default=60)
    ap.add_argument("--start-energy", type=float, default=4)
    ap.add_argument("--peak-energy", type=float, default=8)
    ap.add_argument("--end-energy", type=float, default=None, help="default: peak-2 (arc/wave) or peak (ramp/flat)")
    ap.add_argument("--curve", choices=["arc", "ramp", "wave", "flat"], default="arc",
                    help="arc=warm-up→peak at ~70%%→cool-down, ramp=build to the end, wave=two peaks, flat=plateau")
    ap.add_argument("--genres", default="all", help="comma list of genre slugs (tech_house,afro_house), "
                                                    "family:<house|techno|mainstream|breadth>, or all")
    ap.add_argument("--include-crates", action="store_true", help="add real tracks from crates/*.csv")
    ap.add_argument("--library", help="CSV from tools/analyze_library.py (your own tracks)")
    ap.add_argument("--no-catalog", action="store_true", help="exclude DJ Lab originals")
    ap.add_argument("--prefer", choices=["djlab", "crate", "library"], default="", help="small bonus for a source")
    ap.add_argument("--bpm-range", help="hard BPM window, e.g. 118-128")
    ap.add_argument("--beam", type=int, default=16, help="beam width (1 = greedy)")
    ap.add_argument("--title", help="set title (Hebrew welcome)")
    ap.add_argument("--out", help="write Markdown here (e.g. sets/wedding-60.md)")
    ap.add_argument("--json", help="also write machine-readable JSON here")
    args = ap.parse_args(argv)

    end = args.end_energy
    if end is None:
        end = args.peak_energy if args.curve in ("ramp", "flat") else max(args.start_energy, args.peak_energy - 2)

    pool: list[Track] = []
    origin = ""
    if not args.no_catalog:
        dj, origin = load_djlab()
        pool += dj
    if args.include_crates:
        pool += load_crates()
    if args.library:
        lp = Path(args.library)
        if not lp.exists():
            print(f"!! library CSV not found: {lp}  (run: python tools/analyze_library.py <folder>)", file=sys.stderr)
            return 2
        pool += load_library(lp)
    tokens = [g.strip() for g in (args.genres or "all").split(",") if g.strip()]
    pool = genre_filter(pool, tokens)
    if args.bpm_range:
        lo, hi = (float(x) for x in args.bpm_range.split("-"))
        pool = [t for t in pool if lo <= t.bpm <= hi]
    # dedupe (same artist+title from two sources)
    seen, uniq = set(), []
    for t in pool:
        k = (norm(t.artist), norm(t.title))
        if k not in seen:
            seen.add(k)
            uniq.append(t)
    pool = uniq
    if not pool:
        print("לא נמצאו טראקים שמתאימים לז'אנרים/מקורות שנבחרו. נסו --genres all או --include-crates.", file=sys.stderr)
        return 1

    seq = plan_set(pool, args.minutes, args.start_energy, args.peak_energy, end, args.curve, beam=max(1, args.beam),
                   prefer=args.prefer)
    rows = build_rows(seq, args.minutes, args.start_energy, args.peak_energy, end, args.curve)
    got = sum(t.play_sec for t in seq) / 60
    title = args.title or f"סט {args.minutes:g} דקות — {', '.join(tokens)}"
    print(f"# {title}")
    print(f"pool: {len(pool)} tracks · picked {len(seq)} · ≈{got:.0f} min · curve {args.curve} "
          f"{args.start_energy:g}→{args.peak_energy:g}→{end:g}" + (f" · DJ Lab source: {origin}" if origin else ""))
    print()
    print_table(rows)
    print()
    print(energy_chart(rows))
    if got < args.minutes - 3:
        print(f"\n⚠ יש מספיק טראקים רק לכ-{got:.0f} דקות מתוך {args.minutes:g}. הוסיפו --include-crates, "
              f"--library או ז'אנרים נוספים.", file=sys.stderr)
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = Path.cwd() / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(to_markdown(rows, args, origin, title), encoding="utf-8")
        print(f"\n✓ wrote {out}")
    if args.json:
        data = {"title": title, "minutes": args.minutes, "curve": args.curve, "genres": tokens, "tracks": []}
        for r in rows:
            t: Track = r["track"]
            item = {"n": r["n"], "start": r["start"], "title": t.title, "artist": t.artist, "source": t.source,
                    "genre": t.genre, "genre_slug": t.genre_slug, "bpm": t.bpm, "camelot": t.camelot,
                    "energy": t.energy, "target_energy": r["target"], "ref": t.ref}
            tr = r.get("transition")
            if tr:
                item["transition"] = {"technique": tr["technique"], "technique_he": tr["technique_he"],
                                      "harmony": tr["harmony"].relation, "bpm_change_pct": round(tr["tempo"].pct, 2)}
            data["tracks"].append(item)
        Path(args.json).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
