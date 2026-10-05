"""Amapiano recipe (110–116 BPM).

The signature **log drum** carries the low end and the melody: a pitched, woody, saturated
percussive bass tuned to the key, playing syncopated 2-bar phrases with exponential slides between
notes (``ext_house.SlideNotes``). Around it: swung 16th shakers (two layers, panned), a sparse,
soft kick (beats 1 and 3, syncopated pushes in the drop — not four-on-the-floor), "pha" hits (a
mid-heavy snare/clap hybrid in a roomy reverb), 3-3-2 rim ticks, a woodblock, hi-hat triplet rolls,
soft jazzy piano chords (minor 9ths / major 7ths, multi-string piano with a little Rhodes), a warm
pad, airy vowel voices and a plucked melody. Long, hypnotic build: the log drum enters filtered at
the groove and opens over 32 bars while keys, pad and voices are layered in; a short breakdown
drops the log drum, then it returns for the main section.

DJ rules: 32-bar percussion intro with no bass/tonal content (log drum enters at bar 33 = Hot
Cue B), 32-bar outro whose last 16 bars are percussion only, sections on 8-bar phrases.
"""
from __future__ import annotations

import numpy as np

from .. import drums, ext_house as eh, fx, instruments as inst
from ..arrangement import Song, clip
from ..dsp import eq_peak
from ..theory import Key, voice_lead
from . import register

TEMPLATE = [("Intro", "intro", 32, 3, 0), ("Build", "groove", 32, 5, 2), ("Breakdown", "breakdown", 8, 4, 0),
            ("Main", "drop", 24, 7, 3), ("Outro", "outro", 32, 4, 0)]

PROGRESSIONS = [  # (degree, size): 2 bars each
    [(0, 5), (3, 5), (6, 4), (2, 4)],     # i9  iv9  VII7  IIImaj7
    [(0, 5), (5, 4), (3, 5), (4, 4)],     # i9  VImaj7 iv9 v7
    [(0, 5), (3, 5), (0, 5), (5, 4)],     # i9  iv9  i9  VImaj7
]
# log drum phrases (2 bars): (step, len, scale degree [0 = root in the low octave], vel, flags);
# "s" = slide in from the previous note
LOG_PHRASES = [
    [(2, 2, 0, 1.0, ""), (5, 1.5, 0, 0.75, ""), (7, 2, 7, 0.9, "s"), (10, 2, 4, 0.85, ""), (13, 3, 0, 1.0, "s"),
     (18, 2, 0, 1.0, ""), (21, 1, 2, 0.7, ""), (23, 2, 3, 0.9, ""), (26, 2, 4, 0.9, "s"), (29, 3, 7, 1.0, "s")],
    [(3, 2, 0, 1.0, ""), (6, 2, 0, 0.8, ""), (9, 2, 4, 0.9, "s"), (12, 2, 3, 0.85, ""), (14, 2, 2, 0.8, "s"),
     (19, 2, 0, 1.0, ""), (22, 2, 0, 0.8, ""), (24, 1.5, 6, 0.85, ""), (26, 2, 7, 0.95, "s"), (29, 3, 4, 0.9, "s")],
    [(0, 1.5, 0, 0.9, ""), (3, 2, 0, 1.0, ""), (6, 1.5, 2, 0.8, ""), (8, 2, 4, 0.95, "s"), (11, 2, 3, 0.8, ""),
     (14, 2, 0, 0.9, "s"), (19, 2, 0, 1.0, ""), (22, 1.5, 4, 0.85, ""), (24, 2, 6, 0.9, "s"), (27, 2, 7, 1.0, ""),
     (30, 2, 4, 0.85, "s")],
]
PIANO_COMP = [  # 2 bars of (step, len, vel): laid-back, syncopated
    [(0, 3, 0.75), (3, 3, 0.65), (10, 4, 0.7), (16, 3, 0.75), (22, 2, 0.6), (26, 5, 0.7)],
    [(2, 4, 0.75), (8, 2, 0.6), (11, 4, 0.7), (18, 4, 0.75), (24, 2, 0.6), (27, 4, 0.7)],
]
MELODY = [  # 4 bars: soft plucked answer phrases, scale degrees in octave 5
    [(0, 2, 4, 0.85), (3, 1, 6, 0.7), (4, 2, 7, 0.85), (8, 4, 4, 0.75), (32, 2, 2, 0.8), (35, 1, 4, 0.7),
     (36, 3, 3, 0.8), (40, 6, 2, 0.75)],
    [(2, 2, 7, 0.85), (6, 2, 6, 0.75), (10, 4, 4, 0.8), (34, 2, 4, 0.8), (38, 2, 3, 0.7), (40, 6, 2, 0.8)],
]
VOICES = [(0, 8, 4, 0.8), (16, 6, 2, 0.7), (32, 8, 6, 0.8), (48, 6, 4, 0.7)]

SHAKER_A = "xgoxxgoxxgoxxgox"
SHAKER_B = "gxgogxgogxgogxgo"
PHA = ["....x.......x...", "....x..x....x.x."]
RIM_332 = "x..x..x.x..x..x."
HAT_TRIP = "...........x.x.x"     # pickup into the next bar


@register("amapiano")
def build(plan: dict, rng: np.random.Generator) -> Song:
    song = Song(plan, rng, swing=float(rng.uniform(56.0, 59.0)))
    key: Key = song.key
    song.arrange(TEMPLATE, song.target_bars())
    build_bar = song.bar("groove")
    song.mix_in_bar = build_bar
    outro = song.find("outro")
    bd = song.find("breakdown")
    main = song.bar("drop")
    bass_off = outro.start_bar + outro.bars - 16

    # ================================================================ drums & percussion
    kick_s = drums.kick("deep", tune_hz=eh.kick_tune(key, 45, 60), decay=float(rng.uniform(0.32, 0.38)),
                        click=0.2, drive=1.1, rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown" or c.before("drop", 1):
            return None
        if c.kind == "drop":
            return ["x.....x.x.......", "x.......x.....x."][c.i % 2]
        return "x.......x......."

    song.hits("kick", kick_s, kick_pat, gain_db=-3.0, sc_source=True, humanize=0.0)

    shk = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=float(rng.uniform(0.07, 0.09)),
                         tone=float(rng.uniform(6000, 7000)))
    song.hits("shaker", shk, lambda c: SHAKER_A if not (c.kind == "outro" and c.bars_left <= 2) else None,
              gain_db=-12.0, pan=-0.4, humanize=0.18, timing_ms=2.0)
    shk2 = drums.variants(eh.shekere, 3, rng, jitter={"length": 0.15}, length=0.1)
    song.hits("shaker2", shk2, lambda c: SHAKER_B if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 8)
              or (c.kind == "outro" and c.bars_left > 8) else None, gain_db=-15.0, pan=0.45, humanize=0.18,
              timing_ms=3.0)
    pha_s = drums.variants(eh.pha, 3, rng, jitter={"tone": 0.05}, tone=float(rng.uniform(850, 1050)),
                           body=eh.key_hz(key, 190, 260, rng))
    song.hits("pha", pha_s, lambda c: PHA[c.i % 2] if c.kind in ("groove", "drop", "outro") or
              (c.kind == "intro" and c.i >= 16) or (c.kind == "breakdown" and c.bars_left <= 2) else None,
              gain_db=-6.0, sends={"room": 0.3, "reverb": 0.18}, timing_ms=2.0)
    rim = drums.rimshot(eh.key_hz(key, 1400, 1900, rng), rng=rng)
    song.hits("rim", rim, lambda c: RIM_332 if c.kind == "drop" or (c.kind == "groove" and c.i >= 16)
              or (c.kind == "intro" and c.i >= 24) else None, gain_db=-17.0, pan=0.3, sends={"delay8": 0.15})
    wb = eh.woodblock(eh.key_hz(key, 700, 1000, rng), 0.03, rng=rng)
    song.hits("woodblock", wb, lambda c: "......x.......x." if c.kind in ("drop",) or (c.kind == "groove" and c.i % 4 >= 2)
              else None, gain_db=-17.0, pan=-0.55, sends={"room": 0.15})
    hats = drums.variants(drums.hat, 3, rng, jitter={"decay": 0.2}, decay=0.03, tone=1.05)

    def hat_pat(c):
        if c.kind == "intro" and c.i < 4:
            return None
        if c.every(4) and c.kind in ("groove", "drop"):
            return "..x...x...xxxxxx"
        return "..x...x...x...x."

    song.hits("hats", hats, hat_pat, gain_db=-16.0, pan=0.2, humanize=0.12)
    trip = drums.variants(drums.hat, 3, rng, jitter={"decay": 0.2}, decay=0.025, tone=1.2)
    song.hits("hat_trip", trip, lambda c: "..........xxx..." if c.kind in ("drop",) and c.i % 2 == 1 else None,
              gain_db=-19.0, pan=-0.2, swing=50.0)
    clap = drums.variants(eh.soft_clap, 2, rng, tone_hz=1100.0, tail=0.3)
    song.hits("clap", clap, lambda c: "............x..." if c.kind == "drop" and c.i % 4 == 3 else None,
              gain_db=-9.0, sends={"reverb": 0.35})
    congas = [drums.conga(eh.key_hz(key, 180, 240, rng), "open", rng=rng),
              drums.conga(eh.key_hz(key, 260, 330, rng), "mute", rng=rng)]
    song.hits("congas", congas, lambda c: "...x......x...x." if c.kind == "drop" or (c.kind == "intro" and c.i >= 24 and c.i % 2)
              else None, gain_db=-16.0, pan=-0.3, humanize=0.15, sends={"room": 0.2})

    # ================================================================ log drum (hero)
    phrase = LOG_PHRASES[int(rng.integers(len(LOG_PHRASES)))]
    lo = eh.bass_root(key, 28)                          # F1 for F minor
    prog = PROGRESSIONS[int(rng.integers(len(PROGRESSIONS)))]

    def log_note(d):
        return lo + key.degree(d, 1) - key.degree(0, 1)

    ld_ev = [(s, l, log_note(d), v, fl) for s, l, d, v, fl in phrase]
    ld_clip = clip(ld_ev, 2)

    def log_notes(c):
        if c.kind in ("intro", "breakdown") or c.bar >= bass_off:
            return []
        ev = ld_clip(c)
        if c.kind == "groove" and c.i < 8:
            ev = [e for e in ev if e[3] >= 0.95]          # sparse at first: only the strongest hits
        if c.before("breakdown", 1) or c.before("drop", 1):
            ev = [e for e in ev if e[0] < 8]
        if c.kind == "drop" and c.every(8):              # phrase-end roll
            ev = [e for e in ev if e[0] < 12] + [(12, 1, log_note(4), 0.8, ""), (13, 1, log_note(4), 0.85, ""),
                                                  (14, 1, log_note(6), 0.9, "s"), (15, 1, log_note(7), 0.95, "s")]
        return ev

    ld_inst = eh.log_drum(decay=float(rng.uniform(0.42, 0.52)), knock=float(rng.uniform(0.45, 0.6)),
                          bend=float(rng.uniform(3.5, 5.0)), drive=float(rng.uniform(1.8, 2.4)), body=0.5,
                          slide_ms=float(rng.uniform(60, 90)), tone_hz=float(rng.uniform(900, 1300)))
    log = song.add(eh.SlideNotes("log_drum", ld_inst, log_notes, bus="bass", gain_db=-2.5, sidechain=0.15,
                                 sc_release_ms=120.0, humanize=0.03, swing=song.swing))
    log.automate("lp", [(build_bar, 280), (build_bar + 24, 2500), (bd.start_bar, 3000), (main, 6000),
                        (outro.start_bar, 6000), (bass_off, 400)])
    song.buses["bass"].sat = 0.2

    # ================================================================ keys, pad, voices
    chords = eh.voice_progression(key, [d for d, _ in prog], [s for _, s in prog], center=63)

    def chord_i(c):
        return (c.i // 2) % len(prog)

    comp = PIANO_COMP[int(rng.integers(len(PIANO_COMP)))]
    piano = eh.house_piano(bright=0.45, hammer=0.35, bell=0.05, decay=1.3, release=0.35, detune_cents=2.0)

    def piano_notes(c):
        on = (c.kind == "groove" and c.i >= 8) or c.kind in ("breakdown", "drop") or (c.kind == "outro" and c.i < 8)
        if not on:
            return []
        ch = chords[chord_i(c)]
        off = (c.i % 2) * 16
        return [(s - off, l, ch, v) for s, l, v in comp if off <= s < off + 16]

    pl = song.notes("piano", piano, piano_notes, gain_db=-10.0, sidechain=0.2, hp=170.0, humanize=0.08,
                    timing_ms=6.0, sends={"hall": 0.25, "delay": 0.12},
                    fx=[lambda x: eq_peak(eq_peak(x, 320.0, -3.0, 0.8), 2500.0, 2.0, 0.8)])
    pl.automate("lp", [(build_bar + 8, 1800), (build_bar + 24, 7000), (outro.start_bar, 7000),
                       (outro.start_bar + 8, 1500)])
    rh = eh.rhodes(bright=0.55, bark=0.4, drive=0.25)
    song.notes("rhodes", rh, lambda c: [(0, 30, chords[chord_i(c)], 0.55)] if (c.kind in ("drop", "breakdown"))
               and c.i % 2 == 0 else [], gain_db=-17.0, sidechain=0.2, hp=200.0, sends={"hall": 0.3},
               fx=[eh.autopan(song.bpm, 1.0, 0.4)])

    pad = song.notes("pad", eh.soft_pad(attack=2.0, release=3.0, cutoff=1500.0, air=0.35),
                     lambda c: [(0, 31.0, chords[chord_i(c)], 0.75)] if c.i % 2 == 0 and
                     ((c.kind == "groove" and c.i >= 16) or c.kind in ("breakdown", "drop")) else [],
                     gain_db=-18.0, sends={"hall": 0.4}, width=0.9, hp=220.0, sidechain=0.15)
    pad.automate("gain_db", song.section_points({"breakdown": 3.0, "drop": 0.0}, 0.0, ramp_bars=2))

    deg = key.degree
    vclip = clip([(s, l, deg(d, 4), v) for s, l, d, v in VOICES], 4)
    voice = eh.chant(vowel="o", vowel_to="a", shift=1.12, voices=3, vibrato=0.3, breath=0.25, attack=0.15,
                     release=0.6, scoop=-1.0)
    song.notes("voices", voice, lambda c: vclip(c) if c.kind == "breakdown" or (c.kind == "groove" and c.i >= 24)
               or (c.kind == "drop" and c.phrase % 2 == 1) else [], bus="vox", gain_db=-11.0, sidechain=0.15,
               sends={"hall": 0.5, "delay": 0.3}, hp=300.0, width=1.2)

    mel = MELODY[int(rng.integers(len(MELODY)))]
    mclip = clip([(s, l, deg(d, 5), v) for s, l, d, v in mel], 4)
    song.notes("pluck", eh.pluck_lead(bright=0.6, decay=0.995, body=0.3),
               lambda c: mclip(c) if c.kind == "drop" else [], gain_db=-6.5, pan=0.2, sidechain=0.15,
               sends={"delay": 0.3, "hall": 0.2})

    # ================================================================ fx & mix
    eh.transitions(song, rng, crash_db=-11.0, impact=True, impact_db=-13.0, riser_db=-12.0, riser_kind="noise",
                   downlifter=True, reverse=True, drop_crash_every=8)
    song.returns["hall"].decay = 3.8
    song.returns["room"].decay = 0.9
    song.buses["drums"].eq = [("peak", 3000.0, 1.0, 0.8)]
    song.buses["music"].eq = [("peak", 350.0, -1.5, 0.8)]
    song.master.lufs = -9.0

    song.description_he = (f"אמאפיאנו היפנוטי ב-{int(song.bpm)} BPM בסולם {plan['key']}: הלוג-דראם המפורסם מנגן מלודיית "
                           f"באס עם גלישות בין התווים, שייקרים בשש-עשריות עם סווינג, קיק דליל ולא ארבע-על-הרצפה, "
                           f"מכות \"פה\" עם ריוורב, פסנתר ג'אזי רך ופדים — בבילד ארוך שנפתח לאט.")
    song.instruments = ["sliding log drum (tuned to key)", "soft sparse kick", "swung 16th shakers", "shekere",
                        "pha hits", "3-3-2 rim", "woodblock", "hat rolls", "congas", "jazzy piano (min9 / maj7)",
                        "Rhodes-style e-piano", "warm pad", "airy vowel voices", "plucked melody"]
    song.mix_tips_he = (song.auto_mix_tips_he() + " הקיק באמאפיאנו דליל — כשמערבבים מטראק האוס, הורידו את הקיק "
                        "של הטראק היוצא בהדרגה ותנו לשייקרים להחזיק את הגריד.")
    return song
