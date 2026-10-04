"""Practice drills: render ``music/extras.plan.json`` → ``music/practice/<id>-<slug>.{mp3,json,jpg}``.

    python -m djlab.practice --list
    python -m djlab.practice --id practice-03 [--preview]
    python -m djlab.practice --all [--jobs 1]

Each drill is a small, purpose-built arrangement made with the normal engine building blocks
(``Song``, drums, instruments, mixer, master, MP3 export) and engineered for one skill of the
Hebrew course: counting phrases, beatmatching (integer and odd tempos), bass swaps, harmonic
mixing, Hot Cue hunting, EQ ear training and a 100 → 124 tempo bridge.

Practice files differ from catalogue tracks (SCHEMA §3): artist ``DJ Lab Practice``, genre
``Practice``, album ``DJ Lab — Practice``, ``kind: "practice"`` sidecar with ``exercise_he`` and
(optional) ``answer_key``; loudness target −10 LUFS; sidecar ``bpm`` is exact (125.5 / 122.7)
while ID3 ``TBPM`` holds the rounded integer. Everything else (sample-exact grid, first downbeat at
0.0 s, 8-bar sections, Hot Cue slot colours, true peak ≤ −1 dBTP on the decoded MP3) follows the
track contract. Determinism: all randomness comes from the per-drill seed.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import ENGINE_VERSION, REPO_ROOT, SR, scratch_dir
from . import drums, fx, instruments as inst
from .arrangement import Song
from .dsp import F32, fade
from .theory import camelot as camelot_of, parse_key, voice_lead

EXTRAS_PATH = REPO_ROOT / "music" / "extras.plan.json"
PRACTICE_DIR = REPO_ROOT / "music" / "practice"
ARTIST = "DJ Lab Practice"
ALBUM = "DJ Lab — Practice"
GENRE = "Practice"
TARGET_LUFS = -10.0
SLOT_COLORS = {"A": "#28E214", "B": "#10B1E6", "C": "#E0641B", "D": "#E62828", "E": "#B4BE04",
               "F": "#DE44CF", "G": "#305AFF", "H": "#8A2BE2"}
LRM = "\u200e"

# Per-drill production settings (seed, key for tonal drills, builder). practice-10/11/12 share one
# seed on purpose: the very same loop, only transposed, so the key comparison is fair.
SPECS: dict[str, dict] = {
    "practice-01": dict(seed=7101, key="A minor", builder="phrase_counter", category="count"),
    "practice-02": dict(seed=7102, builder="drums", kit="deep", category="beat"),
    "practice-03": dict(seed=7103, builder="drums", kit="tech", category="beat"),
    "practice-04": dict(seed=7104, builder="drums", kit="909", category="beat"),
    "practice-05": dict(seed=7105, builder="drums", kit="techno", category="beat"),
    "practice-06": dict(seed=7106, builder="drums", kit="house", category="odd"),
    "practice-07": dict(seed=7107, builder="drums", kit="deep_tech", category="odd"),
    "practice-08": dict(seed=7108, key="A minor", builder="bass_swap_a", category="bass"),
    "practice-09": dict(seed=7109, key="E minor", builder="bass_swap_b", category="bass"),
    "practice-10": dict(seed=7110, key="A minor", builder="key_loop", category="key"),
    "practice-11": dict(seed=7110, key="Bb minor", builder="key_loop", category="key"),
    "practice-12": dict(seed=7110, key="E minor", builder="key_loop", category="key"),
    "practice-13": dict(seed=7113, key="G minor", builder="cue_hunt", category="cue"),
    "practice-14": dict(seed=7114, key="C minor", builder="eq_ear", category="eq"),
    "practice-15": dict(seed=7115, key="D minor", builder="tempo_bridge", category="tempo"),
}
CATEGORY_ACCENT = {"count": "#FACC15", "beat": "#FB923C", "odd": "#F472B6", "bass": "#C084FC",
                   "key": "#22D3EE", "cue": "#F87171", "eq": "#4ADE80", "tempo": "#A78BFA"}

# ---- shared step patterns
FOUR = "x...x...x...x..."
OFF_HAT = "..x...x...x...x."
CLAP = "....x.......x..."
CLAP_END = "....x.......x..g"
HATS16 = ["gogxgogxgogxgogx", "g.gx.ogxg.gx.ogx", "ggoxggoxggoxgoox", "g.g.gog.g.g.gogo"]
SHAKERS = ["gxgogxgogxgogxgo", "oxgxoxgxoxgxoxgx", ".xgo.xgo.xgo.xgo"]
PERCS = ["...x......x..x..", "..x....x..x.....", "......x...x..x.x", "...x..x.......x.", ".x.....x...x..x."]
FILL_SMALL = "............o.xx"
FILL_BLOCK = "........o.o.xxxX"
FILL_KICKLESS = "....4...5.5.6789"


# ============================================================================ helpers
def load_extras(path: Path = EXTRAS_PATH) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["practice"]


def entry_for(pid: str, extras: list[dict] | None = None) -> dict:
    for e in extras or load_extras():
        if e["id"] == pid:
            return e
    raise KeyError(f"unknown practice id {pid!r}")


def file_stem(entry: dict) -> str:
    return f"{entry['id']}-{entry['slug']}"


def key_short(key: str) -> str:
    name = key.split()[0]
    _, q = parse_key(key)
    return name + ("m" if q == "minor" else "")


def bpm_str(bpm: float) -> str:
    b = float(bpm)
    return str(int(b)) if b.is_integer() else f"{b:g}"


def pct(target: float, source: float) -> str:
    """Tempo-fader change for a deck playing at ``source`` BPM to reach ``target`` (LTR-safe)."""
    v = (target / source - 1.0) * 100.0
    sign = "+" if v >= 0 else "−"
    return f"{LRM}{sign}{abs(v):.1f}%{LRM}"


def soft_onset(x, ms: float = 0.6):
    """Sub-millisecond raised-cosine fade-in on a one-shot: the onset stays on sample 0 (grid-exact) but the
    beater transient no longer starts with a step, which on drum-only material reads as a click."""
    return fade(x, int(ms * 1e-3 * SR), 0)


def pick(rng, pool):
    return pool[int(rng.integers(len(pool)))]


def root_at_least(midi: int, low: int = 31) -> int:
    while midi < low:
        midi += 12
    return midi


@dataclass
class Drill:
    """Practice metadata attached to a Song by a builder."""
    category: str
    description_he: str = ""
    exercise: list[str] = field(default_factory=list)
    cues: list[tuple] = field(default_factory=list)          # (slot, name, bar)
    memory: list[tuple] | None = None                        # (name, bar); None → section starts
    pair_with: list[str] = field(default_factory=list)
    instruments: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)                # answer_key, events, ...
    post: Callable | None = None                             # post(song, mix, a0_sample) -> mix
    preview: tuple[int, int] = (16, 32)
    tonal: bool = True
    marks: dict | None = None                                # cover grid highlights {(row, col): level}


def new_song(entry: dict, spec: dict, rng, swing: float = 50.0) -> Song:
    plan = {"id": entry["id"], "title": entry["title"], "bpm": float(entry["bpm"]), "seed": spec["seed"],
            "key": spec.get("key") or entry.get("key") or "A minor", "lufs": TARGET_LUFS}
    song = Song(plan, rng, swing=swing)
    song.master.lufs = TARGET_LUFS
    return song


# ============================================================================ drum kits
KITS = {
    "deep": dict(kick="deep", tune=49.0, decay=0.42, click=0.30, clap_tone=1050.0, clap_tail=0.22, hat_tone=0.92,
                 hat_dec=0.036, oh_dec=0.16, swing=54.0, perc="rim", extra="tamb", style_he="דיפ-האוס רך"),
    "tech": dict(kick="tech_house", tune=52.0, decay=0.30, click=0.55, clap_tone=1300.0, clap_tail=0.16, hat_tone=1.0,
                 hat_dec=0.04, oh_dec=0.18, swing=56.0, perc="rim", extra="ride", style_he="טק-האוס"),
    "909": dict(kick="909", tune=50.0, decay=0.42, click=0.62, clap_tone=1250.0, clap_tail=0.18, hat_tone=1.1,
                hat_dec=0.045, oh_dec=0.24, swing=50.0, perc="rim", extra="ride", style_he="האוס קלאסי בסאונד 909"),
    "techno": dict(kick="techno", tune=48.0, decay=0.36, click=0.6, clap_tone=1450.0, clap_tail=0.14, hat_tone=1.15,
                   hat_dec=0.03, oh_dec=0.2, swing=50.0, perc="rim", extra="ride", style_he="טכנו מהודק"),
    "house": dict(kick="house", tune=53.0, decay=0.36, click=0.45, clap_tone=1200.0, clap_tail=0.18, hat_tone=1.05,
                  hat_dec=0.042, oh_dec=0.2, swing=53.0, perc="snap", extra="tamb", style_he="האוס גרובי"),
    "deep_tech": dict(kick="deep", tune=51.0, decay=0.36, click=0.42, clap_tone=1150.0, clap_tail=0.2, hat_tone=0.97,
                      hat_dec=0.038, oh_dec=0.17, swing=55.0, perc="snap", extra="tamb", style_he="דיפ-טק"),
}


def make_kit(rng, name: str, tune: float | None = None) -> dict:
    k = KITS[name]
    kit = {"cfg": k}
    kit["kick"] = soft_onset(drums.kick(k["kick"], tune_hz=tune or k["tune"], decay=k["decay"], click=k["click"],
                                        rng=rng))
    kit["clap"] = drums.variants(drums.clap, 3, rng, jitter={"tone_hz": 0.04}, tone_hz=k["clap_tone"],
                                 tail=k["clap_tail"])
    kit["hat"] = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.12}, decay=k["hat_dec"], tone=k["hat_tone"])
    kit["ohat"] = drums.variants(drums.hat, 2, rng, jitter={"decay": 0.08}, open_=True, decay=k["oh_dec"],
                                 tone=k["hat_tone"])
    kit["shaker"] = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=0.085)
    kit["rim"] = drums.variants(drums.rimshot, 2, rng, jitter={"tone_hz": 0.03}, tone_hz=1700.0)
    kit["snap"] = drums.variants(drums.snap, 2, rng)
    kit["tamb"] = drums.variants(drums.tambourine, 2, rng, jitter={"length": 0.1}, length=0.2)
    kit["ride"] = drums.ride(decay=1.2, rng=rng)
    kit["snare"] = drums.variants(drums.snare, 3, rng, jitter={"tone_hz": 0.03}, tone_hz=200.0, snappy=0.75,
                                  decay=0.13)
    kit["crash"] = drums.crash(decay=2.2, rng=rng)
    return kit


def house_drums(song: Song, kit: dict, rng, *, clap_from=8, hats_from=16, shaker_from=16, perc_from=32,
                full_until=96, kickless=(), phrase_fills=True, crash_every=16, crash_from=16, perc_pan=0.55):
    """Steady DJ-tool house drums: kick always (except ``kickless`` bars), offbeat hat, clap, 16th hats,
    shaker, percussion; intro/outro mirror each other (kick + hat at both ends)."""
    total = song.total_bars
    end_min = total - 8  # last 8 bars: kick + offbeat hat only
    kickless = set(kickless)
    perc_p = pick(rng, PERCS)
    hat_p = pick(rng, HATS16)
    sh_p = pick(rng, SHAKERS)

    song.hits("kick", kit["kick"], lambda c: None if c.bar in kickless else FOUR, gain_db=-1.5, sc_source=True,
              humanize=0.0)
    song.hits("offhat", kit["ohat"], OFF_HAT, gain_db=-11.0, pan=-0.2, humanize=0.05, sends={"room": 0.1})

    def clap(c):
        if c.bar < clap_from or c.bar >= end_min:
            return None
        return CLAP_END if (phrase_fills and c.bar % 8 == 7) else CLAP

    song.hits("clap", kit["clap"], clap, gain_db=-4.0, sends={"reverb": 0.1, "room": 0.12})
    song.hits("hats", kit["hat"], lambda c: hat_p if hats_from <= c.bar < full_until else None, gain_db=-15.0,
              pan=0.4, humanize=0.12)
    song.hits("shaker", kit["shaker"], lambda c: sh_p if shaker_from <= c.bar < end_min else None, gain_db=-17.0,
              pan=-0.55, humanize=0.15)
    perc = kit[kit["cfg"]["perc"]]
    song.hits("perc", perc, lambda c: perc_p if perc_from <= c.bar < full_until else None, gain_db=-16.0,
              pan=perc_pan, sends={"delay8": 0.1, "room": 0.1})
    fxl = song.audio("crash", bus="fx")
    for b in range(crash_from, total, crash_every):
        fxl.add(kit["crash"], b, gain_db=-10.0 if b % 32 == 0 else -14.0)
    song.buses["drums"].eq = [("peak", 2600.0, 1.5, 0.8)]
    song.buses["drums"].width = 1.3
    return fxl


# ============================================================================ 01 phrase counter
def build_phrase_counter(entry, spec, rng):
    kit = make_kit(rng, "house", tune=55.0)
    song = new_song(entry, spec, rng, swing=54.0)
    song.arrange([("Block 1 · Intro", "intro", 16, 3, 0), ("Block 1 · Bass In", "groove", 16, 5, 0),
                  ("Block 2", "groove", 32, 6, 0), ("Block 3", "groove", 32, 6, 0), ("Block 4", "groove", 16, 6, 0),
                  ("Block 4 · Outro", "outro", 16, 3, 0)], 128)
    key = song.key
    song.hits("kick", kit["kick"], FOUR, gain_db=-1.5, sc_source=True, humanize=0.0)
    song.hits("offhat", kit["ohat"], OFF_HAT, gain_db=-11.0, pan=-0.1, sends={"room": 0.06})
    song.hits("clap", kit["clap"], lambda c: CLAP if c.bar >= 8 else None, gain_db=-4.5,
              sends={"reverb": 0.1, "room": 0.12})
    hat_p = pick(rng, HATS16[:3])
    song.hits("hats", kit["hat"], lambda c: hat_p if 16 <= c.bar < 112 else None, gain_db=-15.5, pan=0.3,
              humanize=0.12)
    sh_p = pick(rng, SHAKERS)
    song.hits("shaker", kit["shaker"], lambda c: sh_p if c.bar >= 8 else None, gain_db=-17.5, pan=-0.45,
              humanize=0.15)
    congas = [drums.conga(210.0, "open", rng=rng), drums.conga(300.0, "mute", rng=rng)]
    cp = pick(rng, PERCS)
    song.hits("conga", congas, lambda c: cp if 32 <= c.bar < 112 else None, gain_db=-16.0, pan=0.5,
              sends={"room": 0.15})

    # the drill: small fill in bar 8 of every phrase, bigger one in the last bar of each 32-bar block
    def fill(c):
        if c.bar % 32 == 31:
            return FILL_BLOCK
        return FILL_SMALL if c.bar % 8 == 7 else None

    song.hits("fill", kit["snare"], fill, gain_db=-7.0, sends={"reverb": 0.12}, humanize=0.03)
    marks = song.audio("phrase_crash", bus="fx")
    for b in range(0, song.total_bars, 8):
        marks.add(kit["crash"], b, gain_db=-6.0 if b % 32 == 0 else -8.5)
    bell = inst.bell(ratio=3.5, index=2.2, decay=2.6, release=0.6)
    root5 = key.root(5)  # A5
    song.notes("bell", bell, lambda c: [(0, 8, [root5, root5 + 7], 0.85)] if c.bar % 32 == 0 else [],
               gain_db=-5.0, sends={"hall": 0.35, "delay": 0.12}, width=1.3)

    # light bass: i - VI - VII - v, 2 bars each → the progression itself repeats every 8-bar phrase
    roots = [root_at_least(key.degree(d, 1), 28) for d in (0, 5, 6, 4)]
    roots[3] = key.degree(4, 2)  # lift to the 5th an octave up before the phrase restarts

    def bass(c):
        if not (16 <= c.bar < 112):
            return []
        r = roots[(c.bar % 8) // 2]
        ev = [(2, 1.5, r, 0.95), (6, 1.5, r, 0.85), (10, 1.5, r, 0.95), (14, 1, r, 0.8)]
        if c.bar % 2 == 1:
            ev.append((15, 1, r + 12, 0.55))
        return ev

    b = song.notes("bass", inst.bass_pluck(cutoff=300.0, env_amt=1500.0, decay=0.1, res=0.3, sub=0.8, drive=1.5),
                   bass, bus="bass", gain_db=-6.0, sidechain=0.55, sc_release_ms=140.0)
    b.automate("lp", [(16, 500), (32, 1400), (112, 1400)])
    chords, prev = [], None
    for d in (0, 5, 6, 4):
        ch = voice_lead(prev, key.chord(d, 3, 4), center=key.root(4) - 2)
        chords.append(ch)
        prev = ch
    song.notes("chords", inst.dub_chord(cutoff=700.0, env_amt=1400.0, decay=0.2),
               lambda c: [(6, 1, chords[(c.bar % 8) // 2], 0.75), (14, 1, chords[(c.bar % 8) // 2], 0.6)]
               if 32 <= c.bar < 112 else [], gain_db=-15.0, sidechain=0.45, sends={"delay": 0.2, "reverb": 0.1},
               width=1.5)

    k1 = key_short(spec["key"])
    d = Drill(category="count", preview=(28, 36), tonal=True)
    d.description_he = (
        "גרוב האוס רגוע ב-124 BPM שנבנה כדי ללמוד לספור תיבות ופרייזים: מצילת קראש על התיבה הראשונה של כל פרייז "
        "(כל 8 תיבות), צליל פעמון רך על התיבה הראשונה של כל בלוק של 32 תיבות (תיבות 1, 33, 65, 97) ומילוי תופים "
        "קטן בתיבה 8 של כל פרייז (מילוי גדול יותר בסוף כל בלוק). הבאס נכנס בתיבה 17 ויוצא בתיבה 113, ומהלך "
        f"האקורדים שלו חוזר בדיוק כל 8 תיבות. סולם {k1} (8A).")
    d.exercise = [
        "נגנו את הקובץ וספרו בקול \"1-2-3-4\" על כל תיבה; הקישו על השולחן בכל \"1\".",
        "ספרו תיבות על האצבעות: המילוי הקטן מגיע בתיבה 8, והקראש נוחת בדיוק על ה-1 של הפרייז הבא. אם הקראש "
        "מפתיע אתכם — איבדתם את הספירה.",
        "ספרו פרייזים: אחרי ארבעה קראשים (32 תיבות) מגיע הפעמון. אמרו \"בלוק!\" רגע לפני שהוא מצלצל.",
        "שלב ב': טענו לדק 2 את `music/practice/practice-03-drums-124.mp3`, הפעילו Sync, והתחילו אותו בדיוק "
        "על הפעמון של תיבה 33 — המילויים והקראשים של שני הדקים צריכים ליפול יחד.",
        "יעד: 3 בלוקים של 32 תיבות ברצף בלי לאבד את הספירה — בסוף גם בעיניים עצומות.",
    ]
    d.cues = [("A", "Bar 1 · Bell", 0), ("B", "Bass In · Bar 17", 16), ("C", "Bell · Bar 33", 32),
              ("D", "Bell · Bar 65", 64), ("E", "Bell · Bar 97", 96), ("G", "Outro · Bar 113", 112)]
    d.pair_with = ["practice-03", "house-04"]
    d.instruments = ["house kick", "phrase crash every 8 bars", "bell every 32 bars", "snare fills (bar 8)",
                     "clap", "hats & shaker", "congas", "light pluck bass", "dub chords"]
    d.marks = {**{(r, 0): 0.85 for r in range(4)}, **{(r, 7): 0.5 for r in range(4)}, (0, 0): 1.0}
    return song, d


# ============================================================================ 02–07 beatmatch drums
def build_drums(entry, spec, rng):
    kit = make_kit(rng, spec["kit"])
    cfg = kit["cfg"]
    song = new_song(entry, spec, rng, swing=cfg["swing"])
    song.arrange([("Intro", "intro", 16, 3, 0), ("Build", "groove", 16, 5, 0), ("Groove A", "groove", 32, 6, 0),
                  ("Groove B", "groove", 32, 6, 0), ("Outro", "outro", 16, 3, 0)], 112)
    fills = {31, 63, 95}
    hv = [pick(rng, HATS16) for _ in range(3)]
    sv = [pick(rng, SHAKERS) for _ in range(2)]
    pv = [pick(rng, PERCS) for _ in range(3)]
    # phrase (8 bars) → element variant; gentle change every 8 bars, never touching the kick
    hats_v = {3: 0, 4: 0, 5: 1, 7: 0, 9: 2, 10: 2, 11: 0}
    shaker_v = {2: 0, 3: 0, 4: 0, 5: 0, 6: 1, 7: 0, 9: 0, 10: 1, 11: 0, 12: 0}
    perc_v = {4: 0, 5: 1, 6: 0, 7: 1, 8: 2, 10: 2, 11: 1}
    extra_on = {5, 6, 7, 10, 11}

    song.hits("kick", kit["kick"], lambda c: "x..............." if c.bar in fills else FOUR, gain_db=-1.5,
              sc_source=True, humanize=0.0)
    song.hits("offhat", kit["ohat"], OFF_HAT, gain_db=-11.0, pan=-0.2, humanize=0.05, sends={"room": 0.1})

    def clap(c):
        p = c.bar // 8
        if not (1 <= p <= 12) or c.bar in fills:
            return None
        return CLAP_END if c.bar % 8 == 7 else CLAP

    song.hits("clap", kit["clap"], clap, gain_db=-4.0, sends={"reverb": 0.1, "room": 0.12})
    song.hits("fill", kit["snare"], lambda c: FILL_KICKLESS if c.bar in fills else None, gain_db=-7.0,
              sends={"reverb": 0.15}, humanize=0.0)
    song.hits("hats", kit["hat"], lambda c: hv[hats_v[c.bar // 8]] if c.bar // 8 in hats_v and c.bar not in fills
              else None, gain_db=-15.0, pan=0.4, humanize=0.1)
    song.hits("shaker", kit["shaker"], lambda c: sv[shaker_v[c.bar // 8]] if c.bar // 8 in shaker_v else None,
              gain_db=-17.0, pan=-0.55, humanize=0.12)
    song.hits("perc", kit[cfg["perc"]], lambda c: pv[perc_v[c.bar // 8]] if c.bar // 8 in perc_v
              and c.bar not in fills else None, gain_db=-16.0, pan=0.55, sends={"delay8": 0.1, "room": 0.12})
    if cfg["extra"] == "ride":
        song.hits("ride", kit["ride"], lambda c: "x...x...x...x..." if c.bar // 8 in extra_on else None,
                  gain_db=-20.0, pan=0.3)
    else:
        song.hits("tamb", kit["tamb"], lambda c: "....x..g....x..g" if c.bar // 8 in extra_on else None,
                  gain_db=-18.0, pan=0.6, humanize=0.1)
    fxl = song.audio("crash", bus="fx")
    for b in range(16, song.total_bars, 16):
        fxl.add(kit["crash"], b, gain_db=-10.0 if b % 32 == 0 else -14.5)
    song.buses["drums"].eq = [("peak", 2600.0, 1.5, 0.8)]
    song.buses["drums"].width = 1.3

    bpm = float(entry["bpm"])
    bs = bpm_str(bpm)
    d = Drill(category=spec["category"], preview=(28, 36), tonal=False)
    desc = (f"לופ תופים נקי ב-{bs} BPM בסגנון {cfg['style_he']} — קיק, קלאפ, היי-האט באופביט ושייקר, בלי באס ובלי "
            "שום צליל טונאלי, כך שהביטמאצ'ינג נעשה רק לפי הקצב. כל 8 תיבות משהו קטן משתנה בתופים, וקראש עדין מסמן "
            "כל 16 תיבות. הקיק לא נעלם אף פעם — חוץ מתיבת מילוי אחת בסוף כל 32 תיבות (תיבות 32, 64 ו-96: קיק רק על "
            "ה-1 ומילוי סנר). 16 התיבות הראשונות והאחרונות מינימליות (קיק והיי-האט).")
    if not bpm.is_integer():
        desc += (f" הטמפו 'עקום' בכוונה: {bs} BPM בדיוק. תגית ה-BPM בקובץ (ID3) חייבת להיות מספר שלם ולכן מציגה "
                 f"{int(round(bpm))}, אבל ה-Beatgrid וקובץ ה-JSON מציינים {bs} — אי אפשר 'לכוון למספר', חייבים להקשיב.")
    d.description_he = desc
    d.exercise = DRUM_EXERCISES[entry["id"]]()
    d.pair_with = DRUM_PAIRS[entry["id"]]
    d.cues = [("A", "Start · Kick + Hat", 0), ("B", "Groove A · Bar 33", 32), ("C", "Groove B · Bar 65", 64),
              ("G", "Outro · Bar 97", 96)]
    d.memory = [(s.name, s.start_bar) for s in song.sections] + [(f"Fill · Bar {b + 1}", b) for b in sorted(fills)]
    d.memory.sort(key=lambda m: m[1])
    d.instruments = [f"{cfg['kick']} kick", "clap", "offbeat open hat", "16th hats", "shaker",
                     "rimshot" if cfg["perc"] == "rim" else "finger snap",
                     "ride" if cfg["extra"] == "ride" else "tambourine", "snare fill every 32 bars",
                     "crash every 16 bars"]
    d.marks = {**{(r, c): 0.28 for r in range(4) for c in range(8)}, **{(r, 0): 0.6 for r in range(4)},
               (3, 7): 1.0}
    return song, d


DRUM_PAIRS = {
    "practice-02": ["practice-03", "practice-05"], "practice-03": ["practice-04", "practice-03"],
    "practice-04": ["practice-03", "practice-05"], "practice-05": ["practice-04", "practice-02"],
    "practice-06": ["practice-03", "practice-07"], "practice-07": ["practice-03", "practice-06"],
}
P02, P03, P04, P05 = (f"music/practice/{x}" for x in ("practice-02-drums-120.mp3", "practice-03-drums-124.mp3",
                                                         "practice-04-drums-128.mp3", "practice-05-drums-132.mp3"))
P06, P07 = "music/practice/practice-06-odd-tempo-125_5.mp3", "music/practice/practice-07-odd-tempo-122_7.mp3"
COVER_BPM = "כסו את תצוגת ה-BPM של דק 2 (פתק דביק עובד מצוין)."
DRUM_EXERCISES: dict[str, Callable[[], list[str]]] = {
    "practice-02": lambda: [
        f"טענו את `practice-02` (120) לדק 1 ואת `{P03}` (124) לדק 2. Sync כבוי. {COVER_BPM}",
        "נגנו את דק 1 ברמקולים. בדק 2 לחצו Play על ה-1 של פרייז (הקראש בדק 1 הוא סימן טוב) והאזינו לו באוזניות.",
        f"הורידו את ה-Tempo Fader של דק 2 עד שהקיקים מפסיקים 'לדהור' — היעד בערך {pct(120, 124)}. תקנו מיקום עם ה-Jog.",
        "החזיקו 32 תיבות יציבות. תיבת המילוי (בלי קיק) בסוף כל 32 תיבות היא מבחן: אם אחריה הקיקים עדיין יחד — הצלחתם.",
        f"שלב ב': אותו תרגיל מול `{P05}` (132) — פער של 10% ({pct(120, 132)}); צריך טווח Tempo של ±16%.",
    ],
    "practice-03": lambda: [
        "תרגיל מיקום: טענו את `practice-03` לשני הדקים. הפעילו את דק 2 בכוונה לא בזמן, ויישרו את הקיקים רק עם "
        "ה-Jog. 20 חזרות.",
        f"תרגיל מהירות: דק 1 — `practice-03` (124), דק 2 — `{P04}` (128). Sync כבוי. {COVER_BPM}",
        f"כוונו את ה-Tempo Fader של דק 2 עד שהקיקים יושבים יחד — בערך {pct(124, 128)} — ותקנו עם ה-Jog.",
        "החזיקו 32 תיבות בלי סטייה של יותר מחצי ביט, ובדקו את עצמכם על תיבת המילוי (תיבה 32).",
        f"שלב ב': החליפו תפקידים — `{P04}` בדק 1 ו-`practice-03` בדק 2 (הפעם צריך להאיץ, {pct(128, 124)}).",
    ],
    "practice-04": lambda: [
        f"טענו את `practice-04` (128) לדק 1 ואת `{P03}` (124) לדק 2. Sync כבוי. {COVER_BPM}",
        "הפעילו את דק 2 על ה-1 של פרייז והאזינו באוזניות: דק 2 איטי יותר, הקיקים שלו 'נגררים אחורה'.",
        f"העלו את ה-Tempo Fader של דק 2 בערך {pct(128, 124)} ויישרו עם ה-Jog.",
        "כשזה יציב העלו את הפיידר של דק 2 והאזינו לשני הלופים יחד ברמקולים 32 תיבות — בלי 'דהירה'.",
        f"שלב ב': `{P05}` (132) בדק 2 מול `practice-04` — פער קטן יותר ({pct(128, 132)}), ולכן קשה יותר לשמוע.",
    ],
    "practice-05": lambda: [
        f"טענו את `practice-05` (132) לדק 1 ואת `{P04}` (128) לדק 2. Sync כבוי. {COVER_BPM}",
        f"כוונו את דק 2 ל-132 באוזן בלבד (בערך {pct(132, 128)}) ויישרו עם ה-Jog.",
        "החזיקו 32 תיבות יציבות; בדקו את עצמכם על תיבת המילוי בסוף כל 32 תיבות.",
        f"שלב ב': פער גדול — `{P02}` (120) בדק 2 מול `practice-05`: {pct(132, 120)}. צריך טווח Tempo של ±16%.",
    ],
    "practice-06": lambda: [
        f"טענו את `{P03}` (124) לדק 1 ואת `practice-06` (125.5) לדק 2. Sync כבוי. {COVER_BPM}",
        f"כוונו את דק 2 באוזן — היעד בערך {pct(124, 125.5)}: שינוי קטן ועדין של ה-Tempo Fader.",
        "החזיקו 32 תיבות. כשהפער קטן הסטייה מצטברת לאט — 'הבהוב' או 'פלאם' בהיי-האטים הוא סימן מוקדם שצריך לתקן.",
        f"שלב ב': `practice-06` (125.5) בדק 1 מול `{P07}` (122.7) בדק 2 — {pct(125.5, 122.7)}.",
        "בסוף הציצו ב-BPM שהגעתם אליו: כמה קרוב ל-124 (או ל-125.5) הייתם?",
    ],
    "practice-07": lambda: [
        f"טענו את `{P03}` (124) לדק 1 ואת `practice-07` (122.7) לדק 2. Sync כבוי. {COVER_BPM}",
        f"הפער זעיר ({pct(124, 122.7)}): הזיזו את ה-Tempo Fader במילימטרים, ותנו לאוזן כמה תיבות לשמוע לאיזה "
        "כיוון זה בורח.",
        "תקנו בנגיעות קטנות ב-Jog, לא בדחיפות גדולות. החזיקו 32 תיבות יציבות.",
        f"שלב ב': `{P06}` (125.5) בדק 1 ו-`practice-07` בדק 2 ({pct(125.5, 122.7)}).",
    ],
}


# ============================================================================ 08/09 bass swap
def _bass_swap_frame(entry, spec, rng, kit_name, swing):
    kit = make_kit(rng, kit_name)
    song = new_song(entry, spec, rng, swing=swing)
    song.arrange([("Intro", "intro", 16, 3, 0), ("Bass In", "groove", 16, 5, 0), ("Full Loop", "drop", 32, 7, 0),
                  ("Full Loop 2", "drop", 32, 7, 0), ("Outro", "outro", 16, 3, 0)], 112)
    house_drums(song, kit, rng, clap_from=8, hats_from=16, shaker_from=16, perc_from=32, full_until=96)
    return song, kit


def _bass_swap_meta(song, d: Drill, other_id, other_path, other_desc_he):
    d.cues = [("A", "Intro (drums)", 0), ("B", "Bass In · Bar 17", 16), ("D", "Full Loop · Bar 33", 32),
              ("G", "Outro (drums) · Bar 97", 96)]
    d.pair_with = [other_id, "transition-02"]
    d.exercise = [
        f"טענו את הקובץ הזה לדק 1 ואת `{other_path}` לדק 2 (שניהם 124 — מותר Sync).",
        "נגנו את דק 1 מ-Hot Cue D (תיבה 33). בדק 2 סגרו לגמרי את ידית ה-Low, והפעילו אותו מ-Hot Cue A על ה-1 של פרייז "
        "בדק 1.",
        "העלו את הפיידר של דק 2. אחרי 16 תיבות נכנס הבאס שלו (Hot Cue B) — עדיין לא שומעים אותו, כי ה-Low סגור.",
        f"על ה-1 של הפרייז הבא: בתנועה אחת פתחו את ה-Low של דק 2 וסגרו את ה-Low של דק 1. הבאס צריך להתחלף בבירור "
        f"ל{other_desc_he}.",
        "חזרו הלוך-חזור 20 פעמים, תמיד על ה-1. יעד: אף רגע של 'שני באסים' (בוץ) ואף רגע של 'אין באס' (חור).",
    ]
    d.preview = (28, 40)
    d.marks = {**{(r, c): 0.25 for r in range(2) for c in range(8)},
               **{(r, c): 0.8 for r in range(2, 4) for c in range(8)}, (2, 0): 1.0}


def build_bass_swap_a(entry, spec, rng):
    song, kit = _bass_swap_frame(entry, spec, rng, "tech", 55.0)
    key = song.key
    R = root_at_least(key.root(1))  # A1
    bar_a = [(2, 1, 0, 1.0), (3, 1, 12, 0.55), (6, 1, 0, 0.95), (7, 1, 0, 0.6), (10, 1, 0, 1.0), (11, 1, 12, 0.55),
             (14, 1, 0, 0.95)]
    riff = ([(s, l, o, v) for s, l, o, v in bar_a] + [(15, 1, 7, 0.65)]
            + [(16 + s, l, o, v) for s, l, o, v in bar_a] + [(31, 1, 10, 0.65)]
            + [(32 + s, l, o, v) for s, l, o, v in bar_a[:-1]] + [(46, 1, 3, 0.95), (47, 1, 5, 0.7)]
            + [(48 + s, l, o - 2, v) for s, l, o, v in bar_a[:-1]] + [(62, 1, 0, 0.95), (63, 1, 12, 0.7)])

    def bass(c):
        if not (16 <= c.bar < 96):
            return []
        off = (c.i % 4) * 16
        return [(s - off, l, R + o, v) for s, l, o, v in riff if off <= s < off + 16]

    b = song.notes("bass", inst.bass_pluck(cutoff=320.0, env_amt=2400.0, decay=0.11, res=0.4, sub=0.75, drive=2.0,
                                           wave="saw"),
                   bass, bus="bass", gain_db=-3.5, sidechain=0.6, sc_release_ms=130.0, humanize=0.03)
    b.automate("lp", [(16, 700), (31.9, 1300), (32, 3800), (96, 3800)])
    # light melodic element: kalimba motif in A minor pentatonic (2-bar loop) + delay
    m = key.degree
    motif = [(0, 2, m(4, 4), 0.8), (3, 1, m(3, 4), 0.55), (4, 2, m(2, 4), 0.7), (7, 1, m(0, 4), 0.55),
             (10, 2, m(2, 4), 0.7), (12, 2, m(3, 4), 0.6),
             (16, 3, m(4, 4), 0.8), (20, 1, m(6, 4), 0.55), (22, 2, m(4, 4), 0.7), (26, 2, m(3, 4), 0.6),
             (30, 2, m(2, 4), 0.5)]

    def mel(c):
        if not (32 <= c.bar < 96):
            return []
        off = (c.i % 2) * 16
        return [(s - off, l, p, v) for s, l, p, v in motif if off <= s < off + 16]

    song.notes("kalimba", inst.mallet("kalimba"), mel, gain_db=-10.0, sidechain=0.3, pan=0.15,
               sends={"delay": 0.25, "reverb": 0.12}, width=1.3)
    d = Drill(category="bass", tonal=True)
    d.description_he = (
        "לופ האוס ב-124 BPM בלה מינור (8A) עם באס 'מתגלגל' דומיננטי: זוגות של שש-עשריות באופביט, בדיוק בין הקיקים, "
        "עם קפיצות אוקטבה ופילטר שנפתח בתיבה 33 — ומעליו מוטיב קלימבה עדין עם דיליי. 16 תיבות תופים בלבד, הבאס "
        "נכנס בתיבה 17, הקלימבה בתיבה 33, ומתיבה 97 חוזרים לתופים בלבד. בנוי לתרגול Bass Swap מול `practice-09` "
        "(באס סינקופטי וגומי במי מינור, 9A — שכן הרמוני).")
    _bass_swap_meta(song, d, "practice-09", "music/practice/practice-09-bass-swap-b-124.mp3",
                    "באס הגומי הסינקופטי של practice-09")
    d.instruments = ["tech-house kick", "rolling offbeat pluck bass", "kalimba motif", "clap", "hats", "shaker",
                     "rimshot", "crash every 16 bars"]
    return song, d


def build_bass_swap_b(entry, spec, rng):
    song, kit = _bass_swap_frame(entry, spec, rng, "house", 52.0)
    key = song.key
    R = key.root(1)  # E1 (41 Hz) — rubbery octave jumps around it
    riff = [(0, 1, 0, 1.0, "a"), (3, 1.5, 12, 0.85, "s"), (5, 1, 10, 0.8, ""), (8, 1, 0, 0.9, ""),
            (10, 1, 12, 0.8, "s"), (11, 1.5, 15, 0.85, ""), (14, 1.5, 12, 0.8, ""),
            (16, 1, 0, 1.0, "a"), (19, 1.5, 12, 0.85, "s"), (21, 1, 10, 0.8, ""), (24, 1, 3, 0.9, "s"),
            (26, 1, 5, 0.85, ""), (28, 1, 7, 0.9, "a"), (30, 1.5, 10, 0.8, "")]

    def bass(c):
        if not (16 <= c.bar < 96):
            return []
        off = (c.i % 2) * 16
        return [(s - off, l, R + o, v, f) for s, l, o, v, f in riff if off <= s < off + 16]

    synth = inst.MonoSynth(wave="square", cutoff=260.0, res=0.62, env_mod=2.6, decay=0.13, accent=0.7, glide_ms=70.0,
                           drive=2.2, sub=0.55, sustain=0.7)
    b = song.line("bass", synth, bass, gain_db=-3.0, sidechain=0.45, sc_release_ms=110.0, humanize=0.0)
    b.automate("cutoff", [(16, 200), (31.9, 300), (32, 380), (96, 380)])
    # light melodic element: syncopated e-piano chords Em9 / Cmaj9 / D6/9
    voicings = [[key.degree(d, 3) for d in (2, 4, 6, 8)],    # Em9 (rootless: G B D F#)
                [key.degree(d, 3) for d in (5, 7, 9, 11)],   # Cmaj7
                [key.degree(d, 3) for d in (6, 7, 8, 10)]]   # Dadd9
    voicings = [voice_lead(None, v, center=64) for v in voicings]
    seq = [0, 0, 1, 2]

    def keys(c):
        if not (32 <= c.bar < 96):
            return []
        ch = voicings[seq[c.i % 4]]
        return [(3, 1.5, ch, 0.7), (10, 2.5, ch, 0.6)] if c.i % 2 == 0 else [(6, 1.5, ch, 0.6), (14, 1.5, ch, 0.5)]

    song.notes("epiano", inst.epiano(bright=0.55), keys, gain_db=-11.0, sidechain=0.35, pan=-0.1,
               sends={"delay": 0.18, "reverb": 0.15}, width=1.4)
    d = Drill(category="bass", tonal=True)
    d.description_he = (
        "לופ האוס ב-124 BPM במי מינור (9A) עם באס סינקופטי ו'גומי': תווים מחוץ לפעמה, קפיצות אוקטבה וגלישות "
        "(Glide) בין התווים, בצליל מרובע עם רזוננס — ומעליו אקורדי אלקטרי-פיאנו עדינים. 16 תיבות תופים בלבד, הבאס "
        "נכנס בתיבה 17, הפיאנו בתיבה 33, ומתיבה 97 חוזרים לתופים בלבד. בנוי לתרגול Bass Swap מול `practice-08` "
        "(באס מתגלגל בלה מינור, 8A — שכן הרמוני).")
    _bass_swap_meta(song, d, "practice-08", "music/practice/practice-08-bass-swap-a-124.mp3",
                    "באס המתגלגל באופביט של practice-08")
    d.instruments = ["house kick", "syncopated rubbery square bass with glides", "electric piano chords", "clap",
                     "hats", "shaker", "finger snaps", "crash every 16 bars"]
    return song, d


# ============================================================================ 10/11/12 key loops
def build_key_loop(entry, spec, rng):
    kit = make_kit(rng, "deep", tune=50.0)
    song = new_song(entry, spec, rng, swing=52.0)
    song.arrange([("Intro", "intro", 16, 3, 0), ("Chords", "groove", 16, 4, 0), ("Full Loop", "drop", 32, 6, 0),
                  ("Full Loop 2", "drop", 32, 6, 0), ("Outro", "outro", 16, 3, 0)], 112)
    key = song.key
    song.hits("kick", kit["kick"], FOUR, gain_db=-2.0, sc_source=True, humanize=0.0)
    song.hits("offhat", kit["ohat"], OFF_HAT, gain_db=-12.0, pan=-0.1, sends={"room": 0.06})
    hp_ = pick(rng, HATS16[:3])
    song.hits("hats", kit["hat"], lambda c: hp_ if 8 <= c.bar < 104 else None, gain_db=-17.0, pan=0.3,
              humanize=0.12)
    fxl = song.audio("crash", bus="fx")
    for b in (16, 32, 64, 96):
        fxl.add(kit["crash"], b, gain_db=-15.0)
    # i - VI - VII - i, two bars each: tonic-heavy so the key is unmistakable
    degs = [0, 5, 6, 0]
    triads, prev = [], None
    for dg in degs:
        ch = voice_lead(prev, key.chord(dg, 3, 3), center=62)
        triads.append(ch)
        prev = ch

    def chord_at(c):
        return triads[(c.i // 2) % 4]

    def pad(c):
        if not (16 <= c.bar < 96) or c.i % 2:
            return []
        ch = chord_at(c)
        return [(0, 31.5, ch + [ch[0] - 12], 0.8)]

    p = song.notes("pad", inst.pad(attack=0.35, release=1.2, cutoff=2400.0, detune=0.25, warmth=0.6), pad,
                   gain_db=-8.0, sidechain=0.35, sends={"hall": 0.25}, width=1.5)
    p.automate("lp", [(16, 1200), (32, 5000), (96, 5000)])

    def arp(c):
        if not (32 <= c.bar < 96):
            return []
        ch = [n + 12 for n in chord_at(c)]
        seqn = [ch[0], ch[1], ch[2], ch[0] + 12, ch[2], ch[1], ch[0], ch[1]]
        return [(i * 2, 1.5, n, 0.8 if i % 4 == 0 else 0.62) for i, n in enumerate(seqn)]

    song.notes("pluck", inst.pluck(cutoff=900.0, env_amt=3800.0, decay=0.14, release=0.15), arp, gain_db=-11.0,
               sidechain=0.3, pan=0.1, sends={"delay8": 0.18, "reverb": 0.1}, width=1.3)

    def bass(c):
        if not (32 <= c.bar < 96):
            return []
        r = root_at_least(key.degree(degs[(c.i // 2) % 4], 1))
        return [(2, 1.75, r, 0.9), (6, 1.75, r, 0.85), (10, 1.75, r, 0.9), (14, 1.75, r, 0.85)]

    song.notes("bass", inst.sub_bass(harmonics=0.22, drive=1.4), bass, bus="bass", gain_db=-6.0, sidechain=0.5,
               sc_release_ms=120.0)

    ks, cam = key_short(spec["key"]), camelot_of(spec["key"])
    names = [key_short(n) for n in _degree_names(spec["key"], degs)]
    prog = "–".join(names)
    d = Drill(category="key", tonal=True, preview=(28, 40))
    base = (f"לופ אקורדים ב-124 BPM ב-{ks} ({cam}): פד חם מנגן {prog} (2 תיבות לכל אקורד), ארפג'יו פלאק ובאס רך "
            "נכנסים בתיבה 33. התופים מינימליים — קיק והיי-האט בלבד — כדי שההרמוניה תישמע ברורה. 16 תיבות תופים "
            "בהתחלה ובסוף. ")
    if entry["id"] == "practice-10":
        d.description_he = base + ("זו נקודת הייחוס לתרגילי המיקס ההרמוני: `practice-12` (9A) תואם לו, ו-`practice-11` "
                                   "(3A) מתנגש בו בכוונה. שלושת הקבצים הם אותו לופ בדיוק — רק הסולם שונה.")
        d.exercise = [
            "טענו את `practice-10` לדק 1 ואת `music/practice/practice-12-key-friend-9A-124.mp3` לדק 2. שניהם 124 — "
            "הפעילו Sync.",
            "הפעילו את שני הדקים יחד מ-Hot Cue A על ה-1, כך שהאקורדים נכנסים יחד בתיבה 17. העלו את שני הפיידרים — "
            "זה נשמע כמו שיר אחד.",
            "החליפו את דק 2 ל-`music/practice/practice-11-key-clash-3A-124.mp3` (3A) וחזרו על אותו דבר. זה הצליל של "
            "התנגשות סולמות.",
            "עכשיו בעיניים עצומות: בקשו ממישהו לטעון 11 או 12 לדק 2, ונחשו 'תואם' או 'מתנגש'. יעד: 5 מתוך 5.",
        ]
        d.pair_with = ["practice-12", "practice-11"]
    elif entry["id"] == "practice-11":
        d.description_he = base + ("זה בדיוק אותו לופ כמו `practice-10`, אבל חצי טון מעליו. לבד הוא נשמע נהדר; יחד "
                                   "עם `practice-10` (8A) הוא מזייף בכוונה — כדי שתלמדו לזהות התנגשות סולמות באוזן.")
        d.exercise = [
            "נגנו את `practice-11` לבד — שימו לב שאין בו שום בעיה.",
            "טענו את `music/practice/practice-10-key-home-8A-124.mp3` לדק השני, Sync, הפעילו יחד על ה-1 והעלו את "
            "שני הפיידרים. הקשיבו לחיכוך בתיבה 17, כשהאקורדים נכנסים.",
            "נסו 'להציל' את המיקס: הורידו את ה-Mid וה-Low של אחד הדקים — ההתנגשות נחלשת, אבל לא נעלמת.",
            "לחצו Key Sync (או Key Shift של חצי טון למטה) בדק של `practice-11` — ההתנגשות נעלמת, כי הוא הפך ל-8A.",
            "המסקנה: מ-8A ל-3A עוברים רק בקאט, ב-Echo Out או בברייקדאון — לא בבלנד ארוך.",
        ]
        d.pair_with = ["practice-10", "practice-08"]
    else:
        d.description_he = base + ("זה אותו לופ כמו `practice-10`, בסולם שכן בגלגל ה-Camelot (\u200e+1\u200e מ-8A). יחד עם "
                                   "`practice-10` הוא נשמע כמו חלק מאותו שיר — מושלם לבלנד ארוך.")
        d.exercise = [
            "טענו את `music/practice/practice-10-key-home-8A-124.mp3` לדק 1 ואת `practice-12` לדק 2, Sync.",
            "בלנד ארוך: הכניסו את דק 2 מ-Hot Cue A על ה-1 של פרייז, עם Low סגור, והעלו את הפיידר לאורך 16 תיבות.",
            "בתיבה 33 של דק 2 (Hot Cue D) עשו Bass Swap והוציאו את דק 1 לאט — אין אף רגע מזייף.",
            "השוו: עשו את אותו בלנד עם `music/practice/practice-11-key-clash-3A-124.mp3` במקום, ורשמו ביומן את ההבדל "
            "במילים שלכם.",
        ]
        d.pair_with = ["practice-10", "practice-08", "practice-09"]
    d.cues = [("A", "Intro (drums)", 0), ("B", "Chords In · Bar 17", 16), ("D", "Full Loop · Bar 33", 32),
              ("G", "Outro (drums) · Bar 97", 96)]
    d.instruments = ["deep house kick", "offbeat hat", "16th hats", "warm supersaw pad", "pluck arpeggio",
                     "soft sub bass"]
    d.extra = {"progression": names}
    d.marks = {(r, c): (0.85 if (c // 2) % 2 == 0 else 0.5) for r in range(4) for c in range(8)}
    return song, d


def _degree_names(key_name: str, degs) -> list[str]:
    """Chord names (diatonic triads) of scale degrees in a natural-minor key, flats preferred."""
    from .theory import Key
    flats = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
    sharps = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    k = Key(key_name)
    use_flats = "b" in key_name.split()[0] or k.root_pc in (0, 2, 5, 7)  # C D F G minor → flat keys
    names = []
    for dg in degs:
        ch = k.chord(dg, 3, 3)
        third = (ch[1] - ch[0]) % 12
        nm = (flats if use_flats else sharps)[ch[0] % 12]
        names.append(f"{nm} {'minor' if third == 3 else 'major'}")
    return names


# ============================================================================ 13 cue hunt
def build_cue_hunt(entry, spec, rng):
    kit = make_kit(rng, "tech", tune=49.0)
    song = new_song(entry, spec, rng, swing=56.0)
    song.arrange([("Part 1", "intro", 16, 4, 0), ("Part 2", "groove", 16, 6, 0), ("Part 3", "groove", 16, 6, 0),
                  ("Part 4", "groove", 16, 7, 0), ("Part 5", "drop", 16, 8, 0), ("Outro", "outro", 16, 4, 0)], 96)
    key = song.key
    events = [0, 16, 32, 48, 64]
    hat_p, sh_p, perc_p = pick(rng, HATS16[:3]), pick(rng, SHAKERS), pick(rng, PERCS)
    song.hits("kick", kit["kick"], lambda c: None if c.bar in (31, 63) else FOUR, gain_db=-1.5, sc_source=True,
              humanize=0.0)
    song.hits("offhat", kit["ohat"], OFF_HAT, gain_db=-11.0, pan=-0.1, sends={"room": 0.06})
    song.hits("clap", kit["clap"], lambda c: None if c.bar in (31, 63) else CLAP, gain_db=-4.0,
              sends={"reverb": 0.1, "room": 0.12})
    song.hits("hats", kit["hat"], lambda c: hat_p if c.bar < 88 else None, gain_db=-15.0, pan=0.3, humanize=0.12)
    song.hits("shaker", kit["shaker"], lambda c: sh_p if 16 <= c.bar < 88 else None, gain_db=-17.0, pan=-0.45,
              humanize=0.15)
    song.hits("rim", kit["rim"], lambda c: perc_p if 48 <= c.bar < 88 else None, gain_db=-16.0, pan=0.45,
              sends={"delay8": 0.12})
    rolls = {14: "x...x...x...x...", 15: "x.x.x.x.xxxxxxxx", 62: "x...x...x...x...", 63: "x.x.x.x.xxxxxxxx"}
    song.hits("snare_roll", kit["snare"], lambda c: rolls.get(c.bar), gain_db=-9.0, sends={"reverb": 0.2},
              humanize=0.0).automate("gain_db", [(14, -8.0), (16, 0.0), (62, -8.0), (64, 0.0)])

    R = root_at_least(key.root(1))  # G1
    riff = [(2, 1.5, 0, 1.0), (3, 1, 0, 0.6), (6, 1.5, 0, 0.95), (10, 1.5, 0, 1.0), (11, 1, 12, 0.6),
            (14, 1.5, 0, 0.9), (18, 1.5, 0, 1.0), (19, 1, 0, 0.6), (22, 1.5, 0, 0.95), (26, 1.5, 3, 1.0),
            (27, 1, 0, 0.6), (30, 1.5, -2, 0.9)]

    def bass(c):
        if not (16 <= c.bar < 88):
            return []
        off = (c.i % 2) * 16
        return [(s - off, l, R + o, v) for s, l, o, v in riff if off <= s < off + 16]

    song.notes("bass", inst.bass_pluck(cutoff=340.0, env_amt=2200.0, decay=0.12, res=0.4, sub=0.75, drive=1.9),
               bass, bus="bass", gain_db=-4.0, sidechain=0.55, sc_release_ms=140.0)
    chords, prev = [], None
    for dg in (0, 5, 3, 4):
        ch = voice_lead(prev, key.chord(dg, 3, 4), center=key.root(4) - 2)
        chords.append(ch)
        prev = ch

    def stabs(c):
        if not (32 <= c.bar < 88):
            return []
        ch = chords[(c.i // 2) % 4]
        return [(3, 1, ch, 0.85), (6, 1, ch, 0.65), (11, 1.5, ch, 0.85)]

    song.notes("stabs", inst.stab(cutoff=800.0, env_amt=3500.0, decay=0.15), stabs, gain_db=-9.0, sidechain=0.5,
               sends={"delay": 0.2, "reverb": 0.12}, width=1.5)
    lead_ev = [(0, 3, 4, 0.85), (4, 1, 3, 0.6), (6, 2, 2, 0.75), (10, 2, 0, 0.7), (14, 2, 2, 0.6),
               (16, 3, 4, 0.85), (20, 1, 5, 0.6), (22, 2, 4, 0.75), (26, 4, 7, 0.8)]

    def lead(c):
        if not (64 <= c.bar < 80):
            return []
        off = (c.i % 2) * 16
        return [(s - off, l, key.degree(dg, 4), v) for s, l, dg, v in lead_ev if off <= s < off + 16]

    song.notes("lead", inst.pluck(cutoff=1200.0, env_amt=4500.0, decay=0.18), lead, gain_db=-10.0, sidechain=0.35,
               sends={"delay": 0.25, "reverb": 0.15}, width=1.4)
    # ---- the five events
    hey = inst.vocal_chop(vowel="e", vowel_to="i", shift=1.15, scoop=-4.0, vibrato=0.0, breath=0.12)
    ho = inst.vocal_chop(vowel="o", vowel_to="u", shift=1.05, scoop=-3.0, vibrato=0.0, breath=0.12)
    song.notes("shout_hey", hey, lambda c: [(0, 2.5, key.degree(4, 4), 1.0)] if c.bar in (0, 64) else [], bus="vox",
               gain_db=-4.0, sends={"delay": 0.3, "reverb": 0.2})
    song.notes("shout_ho", ho, lambda c: [(0, 3, key.degree(0, 4), 1.0)] if c.bar == 48 else [], bus="vox",
               gain_db=-4.0, sends={"delay": 0.3, "reverb": 0.2})
    big = voice_lead(None, key.chord(0, 3, 4) + [key.root(5)], center=62)
    song.notes("big_stab", inst.brass(cutoff=3200.0, release=0.4), lambda c: [(0, 6, big, 1.0)] if c.bar == 32 else [],
               gain_db=-6.0, sends={"reverb": 0.35, "delay": 0.2}, width=1.6)
    ev = song.audio("events", bus="fx")
    bar_s = song.grid.bar_sec
    for b in events:
        ev.add(kit["crash"], b, gain_db=-5.0)
    for b in (0, 16, 64):
        ev.add(fx.impact(2.5, rng=rng), b, gain_db=-7.0)
    ev.add(fx.riser(bar_s * 4, "both", rng=rng), 16, align="end", gain_db=-9.0)
    ev.add(fx.riser(bar_s * 4, "noise", rng=rng), 64, align="end", gain_db=-9.0)
    ev.add(fx.reverse_cymbal(bar_s, rng=rng), 32, align="end", gain_db=-8.0)
    ev.add(fx.reverse_cymbal(bar_s * 0.5, rng=rng), 48, align="end", gain_db=-10.0)
    ev.add(drums.metal_hit(float(440.0 * 2 ** ((key.degree(0, 3) - 69) / 12)), 0.5, rng=rng), 48, gain_db=-12.0)

    d = Drill(category="cue", tonal=True, preview=(12, 20))
    d.description_he = (
        "גרוב טק-האוס ב-126 BPM עם חמישה 'אירועים' שאי אפשר לפספס, כל אחד בדיוק על תחילת תיבה: תיבה 1 — אימפקט, "
        "קראש וקריאת \"Hey!\"; תיבה 17 — רייזר שנגמר בדרופ והבאס נכנס; תיבה 33 — אחרי תיבה שלמה בלי קיק, סטאב "
        "אקורד גדול; תיבה 49 — קריאת \"Ho!\" עם קראש; תיבה 65 — סנר רול, אימפקט והדרופ הגדול עם מלודיה. בין האירועים "
        "הגרוב יציב. ה-Hot Cues לא מסומנים מראש (רק A בהתחלה) — התשובות נמצאות ב-`answer_key`.")
    d.exercise = [
        "טענו את `practice-13` לדק 1. ודאו ש-Quantize דולק ושה-Beatgrid מתחיל בתיבה 1.",
        "נגנו בלי להסתכל על הווייבפורם. בכל פעם שאתם שומעים אירוע — לחצו על הכפתור הפנוי הבא (A, B, C, D, E) "
        "כדי לשמור Hot Cue.",
        "בדקו את עצמכם: הגדילו את הזום וודאו שכל Cue יושב על קו של תחילת תיבה — 1, 17, 33, 49, 65 (ראו "
        "`answer_key` בקובץ ה-JSON).",
        "קפצו בין ה-Cues תוך כדי נגינה (A→C→B…) בתזמון של ה-1 — כך משתמשים ב-Hot Cues בהופעה.",
        "שלב ב': כבו Quantize ונסו שוב. יעד: 5 מתוך 5 במקום. בונוס: טענו את "
        "`music/practice/practice-03-drums-124.mp3` לדק 2 והכניסו אותו בדיוק על Hot Cue C.",
    ]
    d.cues = [("A", "Start · Bar 1", 0)]
    d.memory = []
    d.pair_with = ["practice-03"]
    names = [("start", "Impact + \"Hey!\" shout + crash", "אימפקט, קריאת Hey וקראש — תחילת הגרוב"),
             ("drop", "Riser ends → drop, bass enters", "הרייזר נגמר, דרופ והבאס נכנס"),
             ("stab", "1 bar without kick → big chord stab", "תיבה בלי קיק ואז סטאב אקורד גדול"),
             ("shout", "\"Ho!\" shout + crash, percussion enters", "קריאת Ho, קראש ופרקשן חדש"),
             ("big_drop", "Snare roll → impact, big drop + lead", "סנר רול, אימפקט והדרופ הגדול עם מלודיה")]
    d.extra = {"answer_key": [
        {"slot": "ABCDE"[i], "bar": b + 1, "start_bar": b, "sec": round(song.grid.bar_time(b), 3), "event": n[0],
         "event_en": n[1], "event_he": n[2]} for i, (b, n) in enumerate(zip(events, names))]}
    d.instruments = ["tech-house kick", "clap", "hats", "shaker", "rimshot", "rolling bass", "chord stabs",
                     "pluck lead", "formant vocal shouts", "brass stab", "impacts, risers, crashes"]
    d.marks = {**{(r, c): 0.25 for r in range(4) for c in range(8)}, (0, 0): 1.0, (2, 0): 1.0}
    return song, d


# ============================================================================ 14 EQ ear training
BANDS_HE = {"low": "Low — באס וקיק בלבד", "mid": "Mid — אקורדים, ווקאל וקלאפ", "high": "High — היי-האטים ושייקר",
            "full": "Full — המיקס המלא"}
EQ_SPLIT = (250.0, 3000.0)


def _eq_rounds(rng, n_blocks=3) -> list[str]:
    bands = ["low", "mid", "high", "full"]
    out: list[str] = []
    for _ in range(n_blocks):
        for _try in range(100):
            perm = [bands[i] for i in rng.permutation(4)]
            prev = out[-1] if out else "full"  # the reference before round 1 is the full mix
            if perm[0] != prev:
                break
        out += perm
    return out


def _split3(x, sr=SR):
    from scipy import signal
    lo = signal.sosfiltfilt(signal.butter(4, EQ_SPLIT[0], "lowpass", fs=sr, output="sos"), x, axis=0)
    hi = signal.sosfiltfilt(signal.butter(4, EQ_SPLIT[1], "highpass", fs=sr, output="sos"), x, axis=0)
    mid = x - lo - hi
    return lo.astype(F32), mid.astype(F32), hi.astype(F32)


def build_eq_ear(entry, spec, rng):
    kit = make_kit(rng, "tech", tune=52.0)
    song = new_song(entry, spec, rng, swing=55.0)
    rounds = _eq_rounds(rng)
    tpl = [("Reference", "intro", 8, 6, 0)] + [(f"Round {i + 1}", "groove", 8, 6, 0) for i in range(len(rounds))] \
        + [("Final (Full)", "outro", 8, 6, 0)]
    song.arrange(tpl, 8 * (len(rounds) + 2))
    key = song.key
    hat_p, sh_p, perc_p = pick(rng, HATS16[:3]), pick(rng, SHAKERS), pick(rng, PERCS)
    song.hits("kick", kit["kick"], FOUR, gain_db=-1.5, sc_source=True, humanize=0.0)
    song.hits("offhat", kit["ohat"], OFF_HAT, gain_db=-10.5, pan=-0.1, sends={"room": 0.06})
    song.hits("clap", kit["clap"], CLAP, gain_db=-4.0, sends={"reverb": 0.12, "room": 0.12})
    song.hits("hats", kit["hat"], hat_p, gain_db=-13.5, pan=0.3, humanize=0.12)
    song.hits("shaker", kit["shaker"], sh_p, gain_db=-15.0, pan=-0.45, humanize=0.15)
    song.hits("ride", kit["ride"], "x...x...x...x...", gain_db=-18.0, pan=0.2)
    song.hits("rim", kit["rim"], perc_p, gain_db=-15.0, pan=0.45, sends={"delay8": 0.1})
    R = root_at_least(key.root(1))  # C2
    riff = [(2, 1.5, 0, 1.0), (3, 1, 0, 0.6), (6, 1.5, 0, 0.95), (10, 1.5, 0, 1.0), (11, 1, 12, 0.6),
            (14, 1.5, 0, 0.9), (18, 1.5, -4, 1.0), (19, 1, -4, 0.6), (22, 1.5, -4, 0.95), (26, 1.5, -2, 1.0),
            (27, 1, 10, 0.6), (30, 1.5, -2, 0.9)]
    song.notes("bass", inst.bass_pluck(cutoff=380.0, env_amt=2000.0, decay=0.12, res=0.35, sub=0.8, drive=1.8),
               lambda c: [(s - (c.i % 2) * 16, l, R + o, v) for s, l, o, v in riff
                          if (c.i % 2) * 16 <= s < (c.i % 2) * 16 + 16],
               bus="bass", gain_db=-4.0, sidechain=0.55, sc_release_ms=140.0)
    chords, prev = [], None
    for dg in (0, 5, 0, 6):
        ch = voice_lead(prev, key.chord(dg, 3, 4), center=key.root(4) - 2)
        chords.append(ch)
        prev = ch
    song.notes("stabs", inst.stab(cutoff=900.0, env_amt=3000.0, decay=0.16),
               lambda c: [(3, 1, chords[(c.bar // 2) % 4], 0.85),
                          (10, 1.5, chords[(c.bar // 2) % 4], 0.75)],
               gain_db=-8.0, sidechain=0.5, sends={"delay": 0.2, "reverb": 0.12}, width=1.5)
    vox = inst.vocal_chop(vowel="a", vowel_to="e", shift=1.1, scoop=-1.0)
    vph = [(4, 1.5, 4, 0.9), (7, 1, 4, 0.7), (12, 2, 2, 0.85), (20, 1.5, 4, 0.9), (23, 1, 5, 0.7), (28, 3, 4, 0.85)]
    song.notes("vox", vox, lambda c: [(s - (c.bar % 2) * 16, l, key.degree(dg, 4), v) for s, l, dg, v in vph
                                      if (c.bar % 2) * 16 <= s < (c.bar % 2) * 16 + 16],
               bus="vox", gain_db=-7.0, sidechain=0.3, sends={"delay": 0.2, "reverb": 0.15})
    song.buses["drums"].eq = [("peak", 2600.0, 1.5, 0.8)]
    crash = drums.crash(decay=1.6, rng=rng)
    starts = [s.start_bar for s in song.sections[1:]]
    plan_gain = ["full"] + rounds + ["full"]

    def post(song_, m, a0):
        n = m.shape[0]
        lo, mid, hi = _split3(m)
        from .master import lufs
        L_full = lufs(m)
        makeup = {}
        for name, band in (("low", lo), ("mid", mid), ("high", hi)):
            Lb = lufs(band)
            makeup[name] = float(np.clip((L_full - 4.0) - Lb, 0.0, 12.0))
        resid = 10 ** (-30 / 20)
        g = {b: np.ones(n, dtype=np.float64) for b in ("low", "mid", "high")}
        ramp = int(0.012 * SR)
        for si, sec in enumerate(song_.sections):
            band = plan_gain[si]
            s0 = song_.grid.bar_sample(sec.start_bar) - a0
            s1 = song_.grid.bar_sample(sec.end_bar) - a0
            if s1 <= 0 or s0 >= n:
                continue
            for b in ("low", "mid", "high"):
                if band == "full":
                    val = 1.0
                elif band == b:
                    val = 10 ** (makeup[b] / 20)
                else:
                    val = resid
                g[b][max(0, s0):max(0, min(n, s1))] = val
        win = np.hanning(2 * ramp + 1)
        win /= win.sum()
        out = np.zeros_like(m)
        for b, band in (("low", lo), ("mid", mid), ("high", hi)):
            # smooth band switches over ~12 ms ending exactly on the downbeat (causal-left shift)
            sm = np.convolve(np.pad(g[b], (ramp, ramp), mode="edge"), win, mode="valid")
            sm = np.concatenate([sm[ramp:], np.full(ramp, sm[-1])])
            out += band * sm.astype(F32)[:, None]
        for b in starts:  # round marker: a short soft crash on the 1 (not EQ'd)
            pos = song_.grid.bar_sample(b) - a0
            if 0 <= pos < n:
                k = min(crash.shape[0], n - pos)
                out[pos:pos + k] += crash[:k] * F32(0.2)
        return out

    d = Drill(category="eq", tonal=True, post=post, preview=(0, 24))
    d.description_he = (
        "לופ האוס מלא ב-124 BPM (קיק, באס, אקורדים, ווקאל צ'ופ, קלאפ, היי-האטים, שייקר ורייד) — וכל 8 תיבות נשאר "
        "רק תחום תדרים אחד: Low (עד 250Hz — קיק ובאס), Mid (\u200f250Hz–3kHz — אקורדים, ווקאל וקלאפ) או High (מעל 3kHz — "
        "היי-האטים ושייקר), או שחוזר המיקס המלא (Full). זה בדיוק מה ששומעים כשסוגרים ידיות EQ במיקסר. 8 התיבות "
        "הראשונות הן מיקס מלא לייחוס, אחריהן 12 סבבים בסדר אקראי (כל תחום 3 פעמים), ו-8 תיבות מלאות בסוף. קראש "
        "קטן מסמן כל סבב חדש. מפתח התשובות ב-`answer_key`.")
    d.exercise = [
        "הכינו דף עם המספרים 1–12. נגנו את הקובץ מההתחלה, ושננו את צליל המיקס המלא ב-8 התיבות הראשונות.",
        "בכל סבב (קראש קטן כל 8 תיבות, החל מתיבה 9) כתבו Low, Mid, High או Full — לפני שהקראש הבא מגיע.",
        "בדקו מול `answer_key` בקובץ ה-JSON. יעד: 10 מתוך 12, ואז 12 מתוך 12.",
        "שלב ב': טענו את `music/practice/practice-03-drums-124.mp3` לדק השני ונסו לחקות כל צבע עם ידיות ה-EQ "
        "(סגירה מלאה) או עם ה-Filter: סיבוב שמאלה (LPF) משאיר Low, סיבוב ימינה (HPF) משאיר High.",
    ]
    d.cues = [("A", "Reference · Full", 0)]
    d.memory = [(s.name, s.start_bar) for s in song.sections]
    d.pair_with = ["practice-03"]
    d.extra = {
        "eq_split_hz": list(EQ_SPLIT),
        "answer_key": [{"round": i + 1, "bar": starts[i] + 1, "start_bar": starts[i],
                        "sec": round(song.grid.bar_time(starts[i]), 3), "band": band, "band_he": BANDS_HE[band]}
                       for i, band in enumerate(rounds)],
    }
    d.instruments = ["tech-house kick", "rolling bass", "chord stabs", "formant vocal chops", "clap", "hats",
                     "open hat", "shaker", "ride", "rimshot", "3-band isolator (250 Hz / 3 kHz)"]
    shade = {"low": 0.95, "mid": 0.7, "high": 0.45, "full": 0.25}
    d.marks = {(r, c): shade[(["full"] + rounds)[r]] for r in range(4) for c in range(8)}
    return song, d


# ============================================================================ 15 tempo bridge 100 → 124
def build_tempo_bridge(entry, spec, rng):
    song = new_song(entry, spec, rng, swing=52.0)
    song.arrange([("Intro", "intro", 16, 4, 0), ("Verse", "verse", 16, 6, 0), ("Hook", "chorus", 16, 8, 0),
                  ("Break", "breakdown", 8, 4, 0), ("Hook 2", "chorus", 24, 8, 0),
                  ("Outro · Vox + Drums", "outro", 8, 5, 0), ("Outro · Drums Only", "outro", 8, 4, 0)], 96)
    key = song.key
    last = song.total_bars - 1
    brk = range(48, 56)
    kick = soft_onset(drums.kick("house", tune_hz=49.0, decay=0.4, click=0.4, rng=rng))
    snr = drums.variants(drums.snare, 3, rng, jitter={"tone_hz": 0.03}, tone_hz=230.0, snappy=0.6, decay=0.1,
                         kind="tight")
    clp = drums.variants(drums.clap, 2, rng, tone_hz=1350.0, tail=0.12)
    hat = drums.variants(drums.hat, 3, rng, jitter={"decay": 0.1}, decay=0.035, tone=1.05)
    doum = soft_onset(drums.darbuka("doum", 115.0, rng=rng))
    tek = drums.variants(drums.darbuka, 3, rng, stroke="tek", pitch_hz=720.0)
    ka = drums.variants(drums.darbuka, 3, rng, stroke="ka", pitch_hz=650.0)
    riq = drums.variants(drums.tambourine, 2, rng, length=0.18)
    shk = drums.variants(drums.shaker, 3, rng, length=0.08)

    def k_pat(c):
        if c.bar in brk:
            return "x..............." if c.bar == 48 else None
        return FOUR

    song.hits("kick", kick, k_pat, gain_db=-2.0, sc_source=True, humanize=0.0)
    dembow = "...x..x....x..x."

    def snare(c):
        if c.bar < 8 or c.bar == last or c.bar in brk:
            return None
        return dembow

    song.hits("dembow_snare", snr, snare, gain_db=-6.0, sends={"room": 0.15}, humanize=0.05)
    song.hits("dembow_clap", clp, lambda c: dembow if 32 <= c.bar < 80 and c.bar not in brk else None, gain_db=-9.0,
              pan=0.1, sends={"reverb": 0.12})
    song.hits("hats", hat, lambda c: "x.o.x.o.x.o.x.o." if 16 <= c.bar < last and c.bar not in brk else None,
              gain_db=-15.0, pan=0.3, humanize=0.12)
    # darbuka maqsum: DOUM tek . tek DOUM . tek .  (+ ka ghosts, fills every 8 bars)
    song.hits("darbuka_doum", doum, lambda c: "x...x...x...x..." if c.bar == last else "x.......x.......",
              gain_db=-6.0, pan=-0.15, sends={"room": 0.15})

    def tek_p(c):
        if c.bar == last:
            return None
        if c.bar % 8 == 7:
            return "..x...x.....x.xx" if c.bar % 16 != 15 else "..x...x.xxxxrrrr"
        return "..x...x.....x..."

    song.hits("darbuka_tek", tek, tek_p, gain_db=-8.0, pan=-0.3, sends={"room": 0.18}, humanize=0.1)
    song.hits("darbuka_ka", ka, lambda c: None if c.bar == last else "....g.g...g..g.g", gain_db=-13.0, pan=-0.4,
              humanize=0.2)
    song.hits("riq", riq, lambda c: "..o...o...o...o." if 32 <= c.bar < 88 and c.bar not in brk else None,
              gain_db=-17.0, pan=0.5)
    song.hits("shaker", shk, lambda c: "gxgogxgogxgogxgo" if c.bar < last else None, gain_db=-18.0, pan=-0.5,
              humanize=0.15)
    # ---- harmony: Dm – Bb – C – A (harmonic-minor V gives the Mediterranean colour)
    prog = [0, 5, 6, 4]
    qual = ["min", "maj", "maj", "maj"]
    from .theory import chord as mkchord
    roots2 = [key.degree(dg, 2) for dg in prog]
    triads = [mkchord(r + 12, q) for r, q in zip(roots2, qual)]  # around octave 3
    triads = [voice_lead(None, t, center=62) for t in triads]

    def bass(c):
        if not (16 <= c.bar < 80) or c.bar in brk:
            return []
        r = root_at_least(roots2[c.i % 4] - 12, 31)
        return [(0, 2.5, r, 1.0), (3, 2.5, r, 0.85), (8, 2.5, r, 0.95), (11, 1.5, r, 0.85), (14, 1.5, r + 7, 0.75)]

    song.notes("bass", inst.sub_bass(harmonics=0.3, drive=1.8, release=0.05), bass, bus="bass", gain_db=-5.0,
               sidechain=0.35, sc_release_ms=110.0)
    D4 = key.root(3) + 12  # D4 = 62
    oud_riff = [  # 4 bars over Dm | Bb | C | A, D harmonic minor (C# on the A chord)
        (0, 1, 0, .9), (2, 1, 3, .8), (3, 1, 2, .7), (4, 2, 0, .85), (7, 1, -5, .7), (8, 1, 0, .8), (10, 1, 2, .75),
        (11, 1, 3, .8), (12, 2, 5, .85), (14, 2, 3, .75),
        (16, 1, 3, .9), (18, 1, 0, .75), (19, 1, 3, .75), (20, 2, 8, .9), (23, 1, 7, .75), (24, 2, 5, .8),
        (26, 1, 3, .75), (27, 1, 5, .7), (28, 4, 3, .8),
        (32, 1, 2, .9), (34, 1, 5, .8), (35, 1, 3, .7), (36, 2, 2, .85), (39, 1, -2, .7), (40, 1, 2, .8),
        (42, 1, 3, .75), (43, 1, 5, .8), (44, 2, 7, .85), (46, 2, 5, .75),
        (48, 1, 7, .9), (50, 1, 5, .7), (51, 1, 3, .75), (52, 2, 2, .85), (54, 1, 3, .7), (55, 1, 2, .7),
        (56, 2, -1, .9), (58, 2, 2, .8), (60, 4, -5, .85)]

    def is_hook(c):
        return 32 <= c.bar < 48 or 56 <= c.bar < 80

    def oud(c):  # verse + break: full riff; hooks: answers the vocal (bars 3-4 of every 4)
        if not (16 <= c.bar < 80) or (is_hook(c) and c.i % 4 < 2):
            return []
        off = (c.i % 4) * 16
        return [(s - off, l, D4 + o, v) for s, l, o, v in oud_riff if off <= s < off + 16]

    song.notes("oud", inst.string_pluck(decay=0.996, bright=0.55, body_hz=280.0), oud, gain_db=-8.0, pan=-0.2,
               sidechain=0.2, sends={"reverb": 0.15, "delay8": 0.12})
    vox_riff = [  # 4 bars, chop phrase answering the oud
        (0, 1.5, 12, .9), (3, 1, 15, .75), (4, 2, 14, .85), (8, 1, 12, .75), (10, 4, 7, .9),
        (16, 1.5, 12, .9), (19, 1, 15, .75), (20, 1, 17, .8), (22, 2, 15, .85), (26, 4, 12, .85),
        (32, 1.5, 14, .9), (35, 1, 17, .75), (36, 2, 15, .85), (40, 1, 14, .75), (42, 4, 10, .9),
        (48, 1.5, 14, .9), (51, 1, 15, .75), (52, 1, 14, .8), (54, 2, 11, .85), (58, 4, 7, .9)]
    vox = inst.vocal_chop(vowel="a", vowel_to="e", shift=1.12, scoop=-1.5, vibrato=0.4)

    def vox_n(c):  # hooks: call (bars 1-2 of every 4); outro bars 81-88: the whole phrase, a-cappella style
        if not ((is_hook(c) and c.i % 4 < 2) or 80 <= c.bar < 88):
            return []
        off = (c.i % 4) * 16
        return [(s - off, l, D4 + o, v) for s, l, o, v in vox_riff if off <= s < off + 16]

    song.notes("vox_chops", vox, vox_n, bus="vox", gain_db=-6.5, sidechain=0.25,
               sends={"delay": 0.22, "reverb": 0.2})
    song.notes("strings", inst.pad(attack=0.5, release=1.0, cutoff=2600.0, detune=0.2, warmth=0.7),
               lambda c: [(0, 15.5, triads[c.i % 4], 0.75)] if ((32 <= c.bar < 48) or (56 <= c.bar < 80)
                                                                 or c.bar in brk) else [],
               gain_db=-11.0, sidechain=0.3, sends={"hall": 0.3}, width=1.6)
    fxl = song.audio("fx", bus="fx")
    crash = drums.crash(decay=2.0, rng=rng)
    for b in (16, 32, 56):
        fxl.add(crash, b, gain_db=-9.0)
    fxl.add(fx.downlifter(song.grid.bar_sec * 2, rng=rng), 48, gain_db=-12.0)
    fxl.add(fx.riser(song.grid.bar_sec * 4, "noise", rng=rng), 56, align="end", gain_db=-11.0)

    d = Drill(category="tempo", tonal=True, preview=(76, 96))
    d.description_he = (
        "גרוב ים-תיכוני/רגאטון ב-100 BPM ברה מינור (7A): דרבוקה במקצב מקסום, קיק ישר עם סנר דמבו, סאב-באס, "
        "עוּד סינתטי בסולם רה מינור הרמוני (עם צבע חיג'אז על אקורד ה-A) וצ'ופים ווקאליים בפזמון. 16 התיבות "
        "האחרונות מתרוקנות בהדרגה: תיבות 81–88 — תופים וצ'ופים ווקאליים בלבד (בסגנון אקפלה), תיבות 89–96 — תופים "
        "בלבד, והתיבה האחרונה (96) נקייה לגמרי: רק ארבעה רבעים של קיק ודרבוקה — מושלם ל-Echo Out ולכניסה "
        "'בבום' לטראק האוס ב-124. אותו סולם (7A) כמו `mainstream-15` ו-`house-03`.")
    d.exercise = [
        "טענו את `practice-15` לדק 1, ולדק 2 טראק ב-124: `mainstream-15` או `house-03` (שניהם 7A), או לתרגול יבש "
        "`music/practice/practice-03-drums-124.mp3`. Sync כבוי — במעבר הזה אין ביטמאצ'ינג.",
        "שימו את דק 2 על Hot Cue A. בדק 1 בחרו Echo עם 1 Beat (או 1/2 Beat).",
        "נגנו את דק 1 וספרו פרייזים. מתיבה 81 (Hot Cue G) נשארים תופים וווקאל, ומתיבה 89 (Hot Cue H) רק תופים.",
        "בתחילת התיבה האחרונה (96) הדליקו את ה-Echo. על ה-1 שאחריה — הורידו את הפיידר של דק 1, ובאותו רגע "
        "הפעילו את דק 2: 'בום' בטמפו החדש, וההד של ה-100 נמס מתחתיו.",
        "חזרו 10 פעמים, עד שה-1 של הטראק החדש נוחת בדיוק כשההד מתחיל לדעוך. שלב ב': אותה נקודה בקאט נקי, בלי Echo.",
    ]
    d.cues = [("A", "Intro · Darbuka + Dembow", 0), ("B", "Verse · Bass In · Bar 17", 16),
              ("C", "Break · Bar 49", 48), ("D", "Hook · Bar 33", 32), ("F", "Hook 2 · Bar 57", 56),
              ("G", "Outro · Vox + Drums · Bar 81", 80), ("H", "Drums Only · Bar 89", 88)]
    d.pair_with = ["mainstream-15", "house-03", "practice-03", "transition-08"]
    d.instruments = ["darbuka (doum / tek / ka, maqsum)", "reggaeton kick + dembow snare & clap", "riq", "shaker",
                     "sub bass", "synth oud (Karplus-Strong)", "formant vocal chops", "string pad", "riser & downlifter"]
    d.extra = {"echo_out_bar": last + 1, "next_bpm": 124}
    d.marks = {**{(r, c): 0.3 for r in range(4) for c in range(8)}, **{(3, c): 0.8 for c in range(8)}, (3, 7): 1.0}
    return song, d


BUILDERS = {
    "phrase_counter": build_phrase_counter, "drums": build_drums, "bass_swap_a": build_bass_swap_a,
    "bass_swap_b": build_bass_swap_b, "key_loop": build_key_loop, "cue_hunt": build_cue_hunt,
    "eq_ear": build_eq_ear, "tempo_bridge": build_tempo_bridge,
}


# ============================================================================ build / metadata
def _haas(ms: float, left: bool = False):
    def f(x):
        y = fx.haas(x, ms)
        return y[:, ::-1].copy() if left else y
    return f


def stereo_polish(song: Song) -> None:
    """Same top-end image for every drill: tops panned wide + a few ms of Haas on hats (right) and shaker (left),
    a wider room return. Lows are untouched (drum bus stays mono below 110 Hz)."""
    song.returns["room"].width = 1.5
    for l in song.layers:
        if l.name == "hats":
            l.pan = 0.55
            l.fx.append(_haas(7.0))
            l.sends.setdefault("room", 0.1)
        elif l.name == "shaker":
            l.pan = -0.7
            l.fx.append(_haas(11.0, left=True))
            l.sends.setdefault("room", 0.1)
        elif l.name == "offhat":
            l.pan = -0.3
        elif l.name in ("perc", "rim", "conga", "tamb", "riq"):
            l.pan = 0.7 if l.pan >= 0 else -0.7


def build_drill(entry: dict) -> tuple[Song, Drill, dict]:
    spec = SPECS[entry["id"]]
    if entry.get("key") and spec.get("key") and entry["key"] != spec["key"]:
        raise ValueError(f"{entry['id']}: key mismatch plan={entry['key']} spec={spec['key']}")
    rng = np.random.default_rng(int(spec["seed"]))
    song, drill = BUILDERS[spec["builder"]](entry, spec, rng)
    stereo_polish(song)
    for s in song.sections:
        if s.start_bar % 8 or s.bars % 8:
            raise ValueError(f"{entry['id']}: section {s.name} off the 8-bar grid")
    return song, drill, spec


def make_cues(song: Song, items) -> list[dict]:
    out = []
    for slot, name, bar in sorted(items, key=lambda x: x[0]):
        out.append({"slot": slot, "name": name, "bar": int(bar), "sec": round(song.grid.bar_time(bar), 3),
                    "color": SLOT_COLORS[slot], "type": "hot"})
    return out


def sidecar(entry, spec, song: Song, drill: Drill, mp3: Path, jpg: Path, L: float, tp: float, dur: float) -> dict:
    from .export import rel

    meta = {"id": entry["id"], "kind": "practice", "title": entry["title"], "title_he": entry["title_he"],
            "artist": ARTIST, "album": ALBUM, "genre": GENRE, "bpm": float(entry["bpm"])}
    if drill.tonal:
        k = spec.get("key") or entry["key"]
        meta.update({"key": k, "key_short": key_short(k), "camelot": camelot_of(k)})
    memory = drill.memory if drill.memory is not None else [(s.name, s.start_bar) for s in song.sections]
    meta.update({
        "duration_sec": round(dur, 3), "bars": song.total_bars, "beats_per_bar": 4, "first_downbeat_sec": 0.0,
        "sections": song.sections_meta(),
        "cues": make_cues(song, drill.cues),
        "memory_cues": [{"name": n, "bar": int(b), "sec": round(song.grid.bar_time(b), 3)} for n, b in memory],
        "lufs": L, "true_peak_dbtp": tp,
        "file": rel(mp3), "cover": rel(jpg),
        "purpose_he": entry.get("purpose_he", ""),
        "description_he": drill.description_he,
        "exercise_he": "\n".join(f"{i + 1}. {s}" for i, s in enumerate(drill.exercise)),
        "pair_with": list(drill.pair_with),
    })
    meta.update(drill.extra)
    meta.update({"instruments": list(drill.instruments), "seed": int(spec["seed"]), "license": "CC0-1.0",
                 "engine_version": ENGINE_VERSION})
    return meta


def comment(meta: dict) -> str:
    parts = [f"Camelot {meta['camelot']}"] if meta.get("camelot") else []
    parts += [f"BPM {bpm_str(meta['bpm'])}", "Practice drill", "CC0"]
    return " · ".join(parts)


def write_tags(path: Path, meta: dict, cover_jpg: bytes | None) -> None:
    from mutagen.id3 import APIC, COMM, ID3, TALB, TBPM, TCON, TCOP, TDRC, TIT2, TKEY, TPE1, TSSE

    tags = ID3()
    tags.add(TIT2(encoding=3, text=meta["title"]))
    tags.add(TPE1(encoding=3, text=ARTIST))
    tags.add(TALB(encoding=3, text=ALBUM))
    tags.add(TCON(encoding=3, text=GENRE))
    tags.add(TBPM(encoding=3, text=str(int(round(float(meta["bpm"]))))))
    if meta.get("key_short"):
        tags.add(TKEY(encoding=3, text=meta["key_short"]))
    tags.add(COMM(encoding=3, lang="eng", desc="", text=comment(meta)))
    tags.add(TDRC(encoding=3, text="2026"))
    tags.add(TCOP(encoding=3, text="CC0 1.0"))
    tags.add(TSSE(encoding=3, text=f"djlab {ENGINE_VERSION}"))
    if cover_jpg:
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_jpg))
    tags.save(str(path), v2_version=4)


# ============================================================================ cover (PRACTICE theme)
def practice_cover(meta: dict, category: str, envelope=None, marks=None, size: int = 800) -> bytes:
    """800×800 JPEG ≤ 200 KB: slate 'practice' palette from cover.py + a per-skill accent, drill number,
    a 32-bar grid (4 phrases × 8 bars) highlighting what the drill trains, the real audio envelope,
    English + Hebrew title and an exact-BPM badge."""
    from PIL import Image, ImageDraw, ImageFilter

    from .cover import FONT_BOLD, FONT_REG, PALETTES, _fit_font, _font, _hex

    c1, c2, gold = [_hex(c) for c in PALETTES["practice"][0]]
    acc = _hex(CATEGORY_ACCENT.get(category, "#FACC15"))
    S = size
    yy, xx = np.mgrid[0:S, 0:S] / S
    t = np.clip(yy * 0.85 + xx * 0.15, 0, 1)[..., None]
    arr = np.array(c1)[None, None, :] * (1 - t) + np.array(c2)[None, None, :] * t
    glow = np.exp(-(((xx - 0.82) ** 2 + (yy - 0.18) ** 2) / 0.06))[..., None]
    arr = arr * (1 - 0.3 * glow) + np.array(acc)[None, None, :] * 0.3 * glow
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    over = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    pad = 48
    white = (255, 255, 255, 255)
    # subtle background bar lines
    for i in range(0, S, 25):
        d.line([i, 0, i, S], fill=(255, 255, 255, 10 if i % 100 else 18), width=1)
    # header
    d.text((pad, pad), "D J   L A B", font=_font(FONT_BOLD, 26), fill=white)
    d.line([pad, pad + 38, pad + 90, pad + 38], fill=acc + (255,), width=4)
    tag = "PRACTICE DRILL"
    tf = _font(FONT_REG, 24)
    d.text((S - pad - d.textlength(tag, font=tf), pad + 2), tag, font=tf, fill=(255, 255, 255, 220))
    # big drill number
    num = meta["id"].split("-")[-1]
    d.text((pad - 6, 96), num, font=_font(FONT_BOLD, 190), fill=acc + (255,))
    # 32-bar grid: 4 rows (phrases) × 8 bars
    marks = marks or {}
    gx0, gy0, cell, gap = 330, 118, 44, 9
    for r in range(4):
        for cidx in range(8):
            lvl = float(marks.get((r, cidx), 0.18))
            x0 = gx0 + cidx * (cell + gap)
            y0 = gy0 + r * (cell + gap)
            col = tuple(int(c2[i] * (1 - lvl) + acc[i] * lvl) for i in range(3))
            d.rounded_rectangle([x0, y0, x0 + cell, y0 + cell], radius=8, fill=col + (235,),
                                outline=(255, 255, 255, 40), width=1)
    img = Image.alpha_composite(img, over)
    # waveform strip from the real envelope
    env = np.asarray(envelope if envelope is not None and len(envelope) > 8 else np.ones(120) * 0.5, dtype=float)
    nb = 96
    env = np.interp(np.linspace(0, len(env) - 1, nb), np.arange(len(env)), env)
    env = env / (env.max() + 1e-9)
    wl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wl)
    cy, h = 420, 70
    bw = (S - 2 * pad) / nb
    for i, e in enumerate(env):
        x = pad + i * bw + bw / 2
        hh = 4 + h * float(e)
        wd.line([x, cy - hh, x, cy + hh], fill=acc + (230,), width=max(2, int(bw * 0.6)))
    glow_l = wl.filter(ImageFilter.GaussianBlur(6))
    img = Image.alpha_composite(img, glow_l)
    img = Image.alpha_composite(img, wl)
    # text block
    d = ImageDraw.Draw(img)
    title = meta["title"]
    tf = _fit_font(d, title, FONT_BOLD, S - 2 * pad, 66)
    d.text((pad, S - 262), title, font=tf, fill=white)
    title_he = meta.get("title_he", "")
    hf = _fit_font(d, title_he, FONT_BOLD, S - 2 * pad, 50, direction="rtl")
    hw = d.textlength(title_he, font=hf, direction="rtl")
    d.text((S - pad - hw, S - 178), title_he, font=hf, fill=acc + (255,), direction="rtl")
    badge = f"{bpm_str(meta['bpm'])} BPM"
    badge += f"  ·  {meta['camelot']}  ·  {meta['key_short']}" if meta.get("camelot") else "  ·  NO KEY · DRUMS"
    bf = _font(FONT_BOLD, 26)
    bwid = d.textlength(badge, font=bf)
    bx, by = pad, S - 82
    d.rounded_rectangle([bx - 2, by - 8, bx + bwid + 28, by + 36], radius=20, fill=acc + (255,))
    d.text((bx + 13, by - 1), badge, font=bf, fill=(17, 24, 39, 255))
    lic = "CC0"
    lf = _font(FONT_REG, 22)
    d.text((S - pad - d.textlength(lic, font=lf), by + 2), lic, font=lf, fill=gold + (230,))
    rgb = img.convert("RGB")
    for q in (90, 85, 80, 72, 64, 55):
        buf = io.BytesIO()
        rgb.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() <= 200 * 1024:
            break
    return buf.getvalue()


# ============================================================================ render
def render_practice(entry: dict, preview: bool = False, out_dir: Path | None = None, verbose: bool = True) -> dict:
    from .cover import envelope_from_audio
    from .export import decode, encode_mp3, export_mp3_safe, measure, write_json
    from .master import master
    from .mixer import mix

    t0 = time.time()
    song, drill, spec = build_drill(entry)
    sr = song.sr
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    log(f"[{entry['id']}] {entry['title']} — {bpm_str(entry['bpm'])} BPM · {song.total_bars} bars · "
        f"{len(song.layers)} layers")
    stem = file_stem(entry)
    if preview:
        s, e = drill.preview
        a, b = song.grid.bar_sample(s), song.grid.bar_sample(e)
        m = mix(song, a, b, verbose=False)
        if drill.post:
            m = drill.post(song, m, a)
        y, _ = master(m, song.master, sr)
        out_dir = Path(out_dir or scratch_dir())
        path = out_dir / f"{stem}.preview.mp3"
        encode_mp3(y, path, sr)
        L, tp = measure(decode(path, sr), sr)
        dt = time.time() - t0
        log(f"[{entry['id']}] preview bars {s}-{e} → {path}  ({L} LUFS, TP {tp} dBTP, {dt:.1f}s)")
        return {"id": entry["id"], "path": str(path), "lufs": L, "true_peak": tp, "seconds": dt, "preview": True}

    m = mix(song, 0, song.grid.total_samples(song.total_bars), verbose=False)
    if drill.post:
        m = drill.post(song, m, 0)
    y, _ = master(m, song.master, sr, verbose=verbose)
    out_dir = Path(out_dir or PRACTICE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    mp3, jpg = out_dir / f"{stem}.mp3", out_dir / f"{stem}.jpg"
    dec, L, tp = export_mp3_safe(y, mp3, sr, max_tp=-1.0, verbose=verbose)
    meta = sidecar(entry, spec, song, drill, mp3, jpg, L, tp, dec.shape[0] / sr)
    cover = practice_cover(meta, drill.category, envelope_from_audio(y), drill.marks)
    jpg.write_bytes(cover)
    write_tags(mp3, meta, cover)
    write_json(out_dir / f"{stem}.json", meta)
    dt = time.time() - t0
    log(f"[{entry['id']}] → {mp3}  ({L} LUFS, TP {tp} dBTP, {meta['duration_sec']:.1f}s, {dt:.1f}s)")
    return {"id": entry["id"], "path": str(mp3), "lufs": L, "true_peak": tp, "seconds": round(dt, 1),
            "duration": meta["duration_sec"], "preview": False}


def _worker(args):
    entry, preview, out = args
    try:
        return render_practice(entry, preview=preview, out_dir=out)
    except Exception as e:  # report and continue
        import traceback

        traceback.print_exc()
        return {"id": entry["id"], "error": f"{type(e).__name__}: {e}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m djlab.practice", description="Render DJ Lab practice drills")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", nargs="+", help="practice id(s), e.g. practice-03")
    g.add_argument("--all", action="store_true", help="render all drills in music/extras.plan.json")
    g.add_argument("--list", action="store_true", help="list drills")
    ap.add_argument("--preview", action="store_true", help="short preview to $DJLAB_SCRATCH")
    ap.add_argument("--jobs", type=int, default=1, help="parallel processes (default 1)")
    ap.add_argument("--out", help="output directory override (e.g. a scratch dir for determinism checks)")
    args = ap.parse_args(argv)
    extras = load_extras()
    if args.list:
        for e in extras:
            sp = SPECS.get(e["id"], {})
            k = sp.get("key") or e.get("key") or "-"
            print(f"{e['id']:<12} {bpm_str(e['bpm']):>6} BPM  {k:<9} {sp.get('builder', '?'):<15} {file_stem(e)}")
        return 0
    sel = extras if args.all else [e for e in extras if e["id"] in set(args.id)]
    if not args.all:
        missing = set(args.id) - {e["id"] for e in sel}
        if missing:
            print(f"unknown id(s): {sorted(missing)}", file=sys.stderr)
            return 2
    out = Path(args.out) if args.out else None
    t0 = time.time()
    jobs = [(e, args.preview, out) for e in sel]
    if args.jobs <= 1 or len(jobs) == 1:
        res = [_worker(j) for j in jobs]
    else:
        import multiprocessing as mp

        with mp.get_context("fork").Pool(args.jobs, maxtasksperchild=1) as pool:
            res = pool.map(_worker, jobs, chunksize=1)
    bad = [r for r in res if "error" in r]
    print(f"\nrendered {len(res) - len(bad)}/{len(res)} in {time.time() - t0:.1f}s")
    for r in bad:
        print(f"  FAILED {r['id']}: {r['error']}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
