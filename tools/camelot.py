#!/usr/bin/env python3
"""Shared harmonic-mixing helpers for DJ Lab tools (no third-party deps).

- parse any key notation (``A minor``, ``Am``, ``A min``, ``8A``, ``08A``, ``1m`` Open Key, ``C#m``, ``Db``)
- convert key <-> Camelot (table identical to music/SCHEMA.md section 6)
- score harmonic compatibility and BPM compatibility (with half/double-time awareness)
- suggest a transition technique for a pair of tracks (vocabulary shared with music/extras.plan.json)

Used by tools/analyze_library.py, tools/set_planner.py and the harmonic-next-track skill.
Run ``python tools/camelot.py 8A 128`` for a quick "what mixes with this?" printout.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass

NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
_NOTE_TO_PC = {
    "C": 0, "B#": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "FB": 4, "E#": 5, "F": 5,
    "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11, "CB": 11,
}

# Camelot number for each pitch class (index = pitch class, C=0).
_MINOR_CAMELOT = {8: 1, 3: 2, 10: 3, 5: 4, 0: 5, 7: 6, 2: 7, 9: 8, 4: 9, 11: 10, 6: 11, 1: 12}
_MAJOR_CAMELOT = {11: 1, 6: 2, 1: 3, 8: 4, 3: 5, 10: 6, 5: 7, 0: 8, 7: 9, 2: 10, 9: 11, 4: 12}
_CAMELOT_MINOR = {v: k for k, v in _MINOR_CAMELOT.items()}
_CAMELOT_MAJOR = {v: k for k, v in _MAJOR_CAMELOT.items()}

# Display spelling that matches SCHEMA.md section 6 (flats for minor 1A-4A, sharps for F#m/C#m ...).
_MINOR_SPELL = {8: "Ab", 3: "Eb", 10: "Bb", 5: "F", 0: "C", 7: "G", 2: "D", 9: "A", 4: "E", 11: "B", 6: "F#", 1: "C#"}
_MAJOR_SPELL = {11: "B", 6: "F#", 1: "Db", 8: "Ab", 3: "Eb", 10: "Bb", 5: "F", 0: "C", 7: "G", 2: "D", 9: "A", 4: "E"}


@dataclass(frozen=True)
class Key:
    pc: int        # pitch class of the tonic, C=0
    minor: bool

    @property
    def camelot(self) -> str:
        n = (_MINOR_CAMELOT if self.minor else _MAJOR_CAMELOT)[self.pc]
        return f"{n}{'A' if self.minor else 'B'}"

    @property
    def short(self) -> str:
        return (_MINOR_SPELL[self.pc] + "m") if self.minor else _MAJOR_SPELL[self.pc]

    @property
    def long(self) -> str:
        return (_MINOR_SPELL if self.minor else _MAJOR_SPELL)[self.pc] + (" minor" if self.minor else " major")

    def __str__(self) -> str:  # pragma: no cover - convenience
        return f"{self.short} ({self.camelot})"


_CAMELOT_RE = re.compile(r"^\s*0?(1[0-2]|[1-9])\s*([AaBb])\b")
_OPENKEY_RE = re.compile(r"^\s*0?(1[0-2]|[1-9])\s*([mMdD])\b")
_NOTE_RE = re.compile(
    r"^\s*([A-Ga-g])\s*([#♯b♭]?)\s*(m(?:in(?:or)?)?|maj(?:or)?|M|minor|major|-)?\s*$"
)


def parse_key(text: object) -> Key | None:
    """Parse almost any DJ key notation. Returns None when unknown/empty."""
    if text is None:
        return None
    s = str(text).strip()
    if not s or s.lower() in {"nan", "none", "unknown", "-", "?", "o", "off"}:
        return None
    # Mixed In Key style "8A - Am" / "08A" / "8A"
    m = _CAMELOT_RE.match(s)
    if m:
        return from_camelot(f"{int(m.group(1))}{m.group(2).upper()}")
    # Open Key notation: 1d = C major (8B), 1m = A minor (8A)
    m = _OPENKEY_RE.match(s)
    if m and not re.match(r"^\s*\d+\s*m(in|aj)", s, re.I):
        n = int(m.group(1))
        cam = ((n + 6) % 12) + 1
        return from_camelot(f"{cam}{'A' if m.group(2).lower() == 'm' else 'B'}")
    s2 = s.replace("♯", "#").replace("♭", "b")
    s2 = re.sub(r"\s+", " ", s2)
    m = re.match(r"^\s*([A-Ga-g])\s*([#b]?)\s*(.*)$", s2)
    if not m:
        return None
    letter, acc, rest = m.group(1).upper(), m.group(2), m.group(3).strip()
    pc = _NOTE_TO_PC.get(letter + acc.upper())
    if pc is None:
        return None
    rest_l = rest.lower()
    if rest == "" or rest_l in {"maj", "major", "dur", "ionian"} or rest == "M":
        minor = False
    elif rest_l in {"m", "min", "minor", "moll", "aeolian", "-"} or rest_l.startswith("min"):
        minor = True
    elif rest_l.startswith("maj"):
        minor = False
    else:
        return None
    return Key(pc, minor)


def from_camelot(code: str) -> Key | None:
    m = re.match(r"^\s*0?(1[0-2]|[1-9])\s*([AaBb])\s*$", str(code))
    if not m:
        return None
    n, letter = int(m.group(1)), m.group(2).upper()
    return Key(_CAMELOT_MINOR[n], True) if letter == "A" else Key(_CAMELOT_MAJOR[n], False)


def to_camelot(text: object) -> str:
    """Key text -> Camelot code (``""`` when unknown)."""
    k = parse_key(text)
    return k.camelot if k else ""


def key_from_pc(pc: int, minor: bool) -> Key:
    return Key(int(pc) % 12, bool(minor))


def _split(code: str) -> tuple[int, str] | None:
    k = parse_key(code)
    if not k:
        return None
    c = k.camelot
    return int(c[:-1]), c[-1]


def camelot_step(a: str, b: str) -> int | None:
    """Signed shortest step on the wheel from a's number to b's number (-6..+6)."""
    pa, pb = _split(a), _split(b)
    if not pa or not pb:
        return None
    d = (pb[0] - pa[0]) % 12
    return d - 12 if d > 6 else d


@dataclass(frozen=True)
class Harmony:
    score: float     # 0..1, 1 = perfect
    relation: str    # machine label
    label: str       # short English
    label_he: str    # short Hebrew


def harmonic_compat(a: object, b: object) -> Harmony:
    """Score how well key b follows key a on the Camelot wheel."""
    pa, pb = _split(str(a)) if a else None, _split(str(b)) if b else None
    if not pa or not pb:
        return Harmony(0.5, "unknown", "key unknown", "סולם לא ידוע — בדקו באוזן")
    step = camelot_step(str(a), str(b))
    same_letter = pa[1] == pb[1]
    if step == 0 and same_letter:
        return Harmony(1.0, "same", "same key", "אותו סולם")
    if step == 0:
        return Harmony(0.88, "relative", "relative major/minor", "מז'ור/מינור מקביל")
    if same_letter and step in (1, -1):
        return Harmony(0.92 if step == 1 else 0.9, f"{step:+d}", f"{step:+d} on the wheel",
                       f"{step:+d} בגלגל — שכן")
    # diagonal: 8A -> 9B (minor up a fifth to relative major) / 8B -> 7A
    if not same_letter and ((pa[1] == "A" and step == 1) or (pa[1] == "B" and step == -1)):
        return Harmony(0.72, "diagonal", "diagonal mix", "מעבר אלכסוני — עובד ברוב המקרים")
    if same_letter and step in (2, -2):
        return Harmony(0.6 if step == 2 else 0.55, f"{step:+d}", f"{step:+d} (energy shift)",
                       f"{step:+d} — שינוי אנרגיה, קצר ומבוקר")
    if same_letter and step == -5:
        # +7 on the wheel (shows as -5 on the shortest path) == one semitone up ("energy boost")
        return Harmony(0.5, "semitone_up", "+1 semitone boost (+7)",
                       "הרמה בחצי טון (+7) — Energy Boost")
    if same_letter and step == 5:
        return Harmony(0.4, "semitone_down", "-1 semitone (-7)", "ירידה בחצי טון — עדיף בקאט")
    if not same_letter and step in (1, -1):
        return Harmony(0.45, "diagonal_far", "diagonal (less common)", "אלכסוני הפוך — זהירות")
    if same_letter and step in (3, -3):
        return Harmony(0.25, f"{step:+d}", "distant key", "סולם רחוק — מעבר קצר/אפקט")
    return Harmony(0.1, "clash", "key clash", "התנגשות סולמות — רק קאט/Echo Out")


@dataclass(frozen=True)
class Tempo:
    score: float       # 0..1
    pct: float         # signed % change b relative to a after half/double matching
    matched_bpm: float # b's bpm as it would be played against a (may be b*2 or b/2)
    mode: str          # "direct" | "double" | "half"


def bpm_compat(a: float | None, b: float | None) -> Tempo:
    """BPM compatibility of b following a, treating half/double time as equivalent."""
    if not a or not b:
        return Tempo(0.5, 0.0, float(b or 0), "unknown")
    best = None
    for mult, mode in ((1.0, "direct"), (2.0, "double"), (0.5, "half")):
        bb = b * mult
        pct = (bb - a) / a * 100.0
        if best is None or abs(pct) < abs(best[0]):
            best = (pct, bb, mode)
    pct, bb, mode = best
    ap = abs(pct)
    if ap <= 2.0:
        s = 1.0
    elif ap <= 4.0:
        s = 0.85
    elif ap <= 6.0:
        s = 0.6
    elif ap <= 10.0:
        s = 0.3
    elif ap <= 16.0:
        s = 0.12
    else:
        s = 0.03
    if mode != "direct":
        s *= 0.8  # half/double time works, but it changes the feel
    return Tempo(s, pct, bb, mode)


TECHNIQUES_HE = {
    "blend": "בלנד ארוך",
    "bass_swap": "החלפת באס (Bass Swap)",
    "filter": "מעבר פילטר",
    "echo_out": "Echo Out",
    "cut": "קאט / סלאם על הפרייז",
    "loop_roll": "לופ רול",
    "energy_boost": "קפיצת אנרגיה הרמונית",
    "tempo_change_echo": "מעבר טמפו עם Echo",
    "drop_swap": "החלפת דרופים",
    "breakdown_mix": "כניסה בברייקדאון",
}

TIPS_HE = {
    "blend": "מכניסים את הטראק החדש באינטרו (Hot Cue A) על תחילת פרייז, 16–32 תיבות של חפיפה, מורידים בהדרגה את ה-Low של הנכנס.",
    "bass_swap": "חפיפה של 16 תיבות כשה-Low של הנכנס סגור; בתחילת פרייז מחליפים באס בבת אחת (Low פתוח בנכנס, סגור ביוצא).",
    "filter": "סוגרים HPF על היוצא תוך 8–16 תיבות ומכניסים את הנכנס נקי — הפילטר מסתיר התנגשות סולמות.",
    "echo_out": "בסוף פרייז מפעילים Echo (1/2 או 1 Beat) על היוצא, סוגרים פיידר, והנכנס נכנס על ה-1.",
    "cut": "על ה-1 של פרייז חדש — קאט חד בפיידר/Crossfader. בלי חפיפה ארוכה.",
    "loop_roll": "לופ קצר (1 → 1/2 → 1/4 Beat) על היוצא בסוף פרייז, ומשחררים ישר לדרופ של הנכנס.",
    "energy_boost": "מעבר לסולם גבוה יותר מרים אנרגיה — כניסה קצרה (8 תיבות) לפני הדרופ של הנכנס.",
    "tempo_change_echo": "הפרש טמפו גדול: Echo Out על היוצא, ואז מתחילים את הנכנס בטמפו המקורי שלו (או משנים טמפו בהדרגה בברייקדאון).",
    "drop_swap": "מסנכרנים כך שהדרופ של הנכנס (Hot Cue D) נוחת בדיוק כשהיוצא מגיע לסוף הברייקדאון — החלפה על ה-1.",
    "breakdown_mix": "מכניסים את הנכנס כשהיוצא בברייקדאון (Hot Cue C) — הרבה מקום בתדרים, מעבר רך להורדת אנרגיה.",
}


def suggest_transition(a: dict, b: dict) -> dict:
    """Pick a transition technique for a -> b.

    a/b are dicts with optional keys: bpm, camelot (or key), energy, genre_slug.
    Returns {technique, technique_he, tip_he, harmony, tempo}.
    """
    ka = a.get("camelot") or to_camelot(a.get("key"))
    kb = b.get("camelot") or to_camelot(b.get("key"))
    h = harmonic_compat(ka, kb)
    t = bpm_compat(_f(a.get("bpm")), _f(b.get("bpm")))
    ea, eb = _f(a.get("energy")) or 5.0, _f(b.get("energy")) or 5.0
    de = eb - ea
    short_form = {"hip_hop", "reggaeton", "afrobeats", "pop_dance", "mediterranean", "lofi", "moombahton"}
    is_short = a.get("genre_slug") in short_form or b.get("genre_slug") in short_form
    ap = abs(t.pct)
    if ap > 8.0:
        tech = "tempo_change_echo"
    elif h.relation == "semitone_up" or (h.relation == "+2" and de >= 1):
        tech = "energy_boost"
    elif h.score < 0.45:
        tech = "echo_out" if ap > 4 or h.relation == "semitone_down" else "filter"
    elif ap > 4.0:
        tech = "cut" if is_short else "echo_out"
    elif de >= 2 and min(ea, eb) >= 6:
        tech = "drop_swap"
    elif de >= 2:
        tech = "cut" if is_short else "loop_roll"
    elif de <= -2:
        tech = "breakdown_mix"
    elif is_short:
        tech = "cut"
    elif max(ea, eb) >= 7:
        tech = "bass_swap"
    else:
        tech = "blend"
    return {"technique": tech, "technique_he": TECHNIQUES_HE[tech], "tip_he": TIPS_HE[tech],
            "harmony": h, "tempo": t}


def _f(v: object) -> float | None:
    try:
        x = float(v)  # type: ignore[arg-type]
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def compatible_keys(code: str) -> list[tuple[str, Harmony]]:
    """All 24 Camelot codes sorted by compatibility with `code`."""
    out = []
    for n in range(1, 13):
        for letter in "AB":
            c = f"{n}{letter}"
            out.append((c, harmonic_compat(code, c)))
    return sorted(out, key=lambda x: -x[1].score)


def _cli(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 0
    k = parse_key(argv[0])
    if not k:
        print(f"unknown key: {argv[0]}", file=sys.stderr)
        return 2
    bpm = float(argv[1]) if len(argv) > 1 else None
    print(f"{k.long} = {k.short} = Camelot {k.camelot}")
    for c, h in compatible_keys(k.camelot)[:8]:
        kk = from_camelot(c)
        print(f"  {c:>3} {kk.short:<4} {h.score:.2f}  {h.label:<28} {h.label_he}")
    if bpm:
        lo, hi = bpm * 0.96, bpm * 1.04
        print(f"BPM ±4%: {lo:.1f}–{hi:.1f} (half {bpm/2:.1f} / double {bpm*2:.1f})")
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
