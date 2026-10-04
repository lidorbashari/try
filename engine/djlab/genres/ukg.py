"""UK Garage recipe (128–136 BPM): 2-step with a speed-garage twist.

Shuffled, skippy 2-step drums (swing ≈ 60: kick on 1 + syncopated second kick, clap/rim snare on 2 and
4, skippy 16th hats, shaker, rim & bongo ghosts), 90s 'M1-style' organ chord stabs, chopped formant
vocal chops (vowel-like, no words) with delay, a bouncy sub bass with octave jumps, and a
speed-garage 'dread' bassline (detuned saws with a downward pitch scoop) in the drop, whose second
half switches to a 4/4 speed-garage kick for a lift.

DJ rules: 32-bar intro (drums only for 16 bars, sub enters on bar 17), short 8-bar breakdown,
32-bar outro (last 16 drums only), all sections on the 8-bar grid.
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from .. import ext_breadth as xb
from ..arrangement import Song, clip, euclid
from ..theory import voice_lead
from . import register

TPL = [("Intro", "intro", 32, 5, 0), ("Groove", "groove", 24, 7, 1), ("Breakdown", "breakdown", 8, 5, 0),
       ("Drop", "drop", 32, 8, 2), ("Outro", "outro", 32, 5, 0)]

KICK_2STEP = [["x.........x.....", "x......x..x....."], ["x.........x.....", "x.........x..x.."],
              ["x.........x.....", "x.......x.x....."]]
HATS = ["x.xxx.x.x.xxx.xx", "x.x.xxx.x.x.xx.x", "xx.x.xx.xx.x.xx."]
SHAKER = "gogxgogxgogxgogx"
RIM = ["...x..x.....x...", "......x..x....x.", "..x.....x..x...."]
SUB_RIFFS = [  # 2 bars: (step, len, semitone offset)
    [(0, 3, 0), (3, 1, 12), (6, 2, 0), (10, 3, 0), (14, 2, 12), (16, 3, 0), (19, 1, 12), (22, 2, 0),
     (26, 2, 10), (28, 2, 7), (30, 2, 5)],
    [(0, 2, 0), (2, 1, 12), (4, 2, 0), (10, 2, 0), (12, 1, 12), (13, 2, 0), (16, 2, 0), (18, 1, 12),
     (20, 2, 3), (26, 2, 5), (29, 3, 7)],
]
DREAD_RIFF = [(0, 6, 0), (7, 3, 0), (10, 5, 0), (16, 6, 0), (23, 2, 3), (26, 3, 5), (29, 3, -2)]
VOX_PHRASES = [  # 2 bars: (step, len, degree, vowel pair)
    [(2, 1, 4, "a", "e"), (3, 1, 4, "a", "e"), (6, 2, 6, "o", "a"), (10, 1, 4, "e", "i"), (11, 3, 3, "a", "o"),
     (18, 1, 4, "a", "e"), (19, 1, 4, "a", "e"), (22, 2, 7, "o", "a"), (27, 4, 6, "a", "e")],
    [(0, 2, 7, "o", "a"), (3, 1, 6, "a", "e"), (4, 2, 4, "e", "a"), (8, 1, 4, "a", "e"), (10, 3, 3, "o", "u"),
     (16, 2, 7, "o", "a"), (19, 1, 6, "a", "e"), (20, 3, 9, "a", "i"), (26, 4, 7, "o", "a")],
]
ORGAN_RHYTHMS = [[(0, 1.5, 0.9), (3, 1, 0.7), (6, 1.5, 0.85), (11, 1, 0.7), (14, 1.5, 0.8)],
                 [(2, 1, 0.85), (6, 1, 0.75), (10, 2, 0.9), (13, 1, 0.65)],
                 [(0, 1, 0.8), (3, 1, 0.9), (7, 1, 0.7), (10, 1, 0.9), (12, 1, 0.6)]]


@register("ukg")
def build(plan: dict, rng: np.random.Generator) -> Song:
    song = Song(plan, rng, swing=float(rng.choice([58.0, 60.0, 62.0])))
    key = song.key
    song.arrange(TPL, song.target_bars())
    secs = song.sections
    intro, outro = song.find("intro"), song.find("outro")
    groove, bd, drop = song.find("groove"), song.find("breakdown"), song.find("drop")
    bass_in = 16
    song.mix_in_bar = bass_in
    bass_off = outro.start_bar + outro.bars - 16
    bar_sec = song.grid.bar_sec

    def speed(c):  # 4/4 speed-garage lift in the second half of the drop
        return c.kind == "drop" and c.i >= 16

    # ---------------------------------------------------------------- drums
    k_hz = xb.kick_tune(key, 45.0, 62.0)
    kick = drums.kick("house", tune_hz=k_hz, decay=float(rng.uniform(0.28, 0.34)), click=0.55, drive=1.6, rng=rng)
    kpat = KICK_2STEP[int(rng.integers(len(KICK_2STEP)))]

    def kick_pat(c):
        if c.kind == "breakdown":
            return None
        if c.before("drop", 1) or c.before("breakdown", 1):
            return "x..............."
        if speed(c):
            return "x...x...x...x..."
        return kpat[c.i % 2]

    song.hits("kick", kick, kick_pat, gain_db=-2.0, sc_source=True, humanize=0.0)
    clap = drums.variants(drums.clap, 3, rng, jitter={"tone_hz": 0.05}, tone_hz=float(rng.uniform(1300, 1600)),
                          tail=0.12)
    rim = drums.rimshot(float(rng.uniform(1600, 2000)), rng=rng)
    snr = drums.snare(tone_hz=float(rng.uniform(200, 240)), snappy=0.7, decay=0.1, kind="tight", rng=rng)

    def bb(c):  # backbeat 2 & 4 (+ skippy ghost)
        if c.kind == "breakdown" or (c.kind == "intro" and c.i < 4):
            return None
        return "....x.......x..." if not c.phrase_end else "....x.......x.xx"

    song.hits("clap", clap, bb, gain_db=-5.0, sends={"reverb": 0.15, "room": 0.12})
    song.hits("snare", snr, lambda c: ("....x.......x..g" if c.i % 2 else "....x.......x...") if bb(c) else None,
              gain_db=-9.0, sends={"room": 0.1})
    hats = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.2}, decay=float(rng.uniform(0.03, 0.045)),
                          tone=float(rng.uniform(1.05, 1.25)))
    hpat = HATS[int(rng.integers(len(HATS)))]
    song.hits("hats", hats, lambda c: hpat if not (c.kind == "breakdown" and c.bars_left > 2) else None,
              gain_db=-13.0, pan=0.3, humanize=0.18, timing_ms=1.5)
    oh = drums.hat(open_=True, decay=0.18, tone=1.1, rng=rng)
    song.hits("open_hat", oh, lambda c: "..x...x...x...x." if speed(c) or (c.kind == "groove" and c.i >= 16)
              or (c.kind == "intro" and c.i >= 24) else None, gain_db=-12.0, pan=-0.25, sends={"room": 0.1})
    shk = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=0.07)
    song.hits("shaker", shk, lambda c: SHAKER if c.kind != "breakdown" and not (c.kind == "intro" and c.i < 8) else None,
              gain_db=-17.0, pan=-0.5, humanize=0.2)
    rpat = RIM[int(rng.integers(len(RIM)))]
    song.hits("rim", rim, lambda c: rpat if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 8) else None,
              gain_db=-16.0, pan=0.45, sends={"delay8": 0.15})
    bongo = [drums.bongo(float(rng.uniform(450, 520)), "open", rng=rng), drums.bongo(float(rng.uniform(600, 680)), "mute", rng=rng)]
    bpat = euclid(int(rng.integers(4, 7)), 16, int(rng.integers(1, 4)))
    song.hits("bongo", bongo, lambda c: bpat if c.kind in ("groove", "drop") and c.i % 4 >= 2 else None,
              gain_db=-17.0, pan=-0.45, sends={"room": 0.15})

    # ---------------------------------------------------------------- harmony
    degs = [[0, 5, 3, 4], [0, 3, 5, 4], [0, 6, 5, 4]][int(rng.integers(3))]
    chords, prev = [], None
    for d in degs:
        ch = voice_lead(prev, key.chord(d, 3, 4), center=key.root(4) - 2)
        chords.append(ch)
        prev = ch

    def chord_i(c):
        return (c.i // 2) % 4

    # ---------------------------------------------------------------- bass
    root = xb.note_in_range(key.root_pc, 41.0)   # G1 49 Hz
    sriff = SUB_RIFFS[int(rng.integers(len(SUB_RIFFS)))]
    sub_ev = [(s, l, o) for s, l, o in sriff]

    def bass_on(c):
        if c.kind == "intro":
            return c.i >= bass_in
        if c.kind == "outro":
            return c.bar < bass_off
        return c.kind in ("groove", "drop")

    def chord_root_off(c):
        return (key.degree(degs[chord_i(c)], 1) - key.root(1)) % 12 if c.kind != "intro" else 0

    def sub_notes(c):
        if not bass_on(c) or c.kind == "drop":   # the dread bass takes over in the drop
            return []
        off = (c.i % 2) * 16
        ro = chord_root_off(c)
        if ro > 6:
            ro -= 12
        out = [(s - off, l * 0.9, root + o + ro, 0.95 if o == 0 else 0.75) for s, l, o in sub_ev if off <= s < off + 16]
        if c.before("breakdown", 1) or c.before("drop", 1):
            out = [e for e in out if e[0] < 8]
        return out

    sub = song.notes("sub", inst.sub_bass(harmonics=0.18, drive=1.4, release=0.05), sub_notes, bus="bass",
                     gain_db=-4.0, sidechain=0.45, sc_release_ms=90.0, humanize=0.03)
    sub.automate("gain_db", [(bass_in, -6.0), (intro.end_bar, 0.0)])
    dread_i = xb.dread_bass(detune_cents=float(rng.uniform(12, 18)), cutoff=float(rng.uniform(250, 330)),
                            env_amt=float(rng.uniform(1200, 1700)), bend=float(rng.choice([5.0, 7.0, 12.0])),
                            bend_ms=float(rng.uniform(50, 90)), drive=2.4, sub=0.6)

    def dread_notes(c):
        if c.kind != "drop":
            return []
        off = (c.i % 2) * 16
        ro = chord_root_off(c)
        if ro > 6:
            ro -= 12
        return [(s - off, l * 0.92, root + o + ro, 0.95) for s, l, o in DREAD_RIFF if off <= s < off + 16]

    song.notes("dread_bass", dread_i, dread_notes, bus="bass", gain_db=-3.5, sidechain=0.5, sc_release_ms=100.0,
               humanize=0.02)

    # ---------------------------------------------------------------- organ stabs (M1-style)
    org = xb.m1_organ(bright=float(rng.uniform(0.5, 0.75)), decay=float(rng.uniform(0.22, 0.32)))
    orh = ORGAN_RHYTHMS[int(rng.integers(len(ORGAN_RHYTHMS)))]

    def organ_notes(c):
        if c.kind == "breakdown":
            return [(0, 30, chords[chord_i(c)], 0.7)] if c.i % 2 == 0 else []
        on = c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 24) or (c.kind == "outro" and c.i < 8)
        if not on:
            return []
        ch = chords[chord_i(c)]
        return [(s, l, ch, v) for s, l, v in orh]

    organ = song.notes("organ", org, organ_notes, gain_db=-10.0, sidechain=0.35, sends={"reverb": 0.15, "delay8": 0.1},
                       width=1.4)
    organ.automate("lp", [(intro.start_bar + 24, 1200.0), (intro.end_bar, 8000.0)])

    # ---------------------------------------------------------------- vocal chops
    vph = VOX_PHRASES[int(rng.integers(len(VOX_PHRASES)))]
    vinst = {}
    for _, _, _, va, vb in vph:
        if (va, vb) not in vinst:
            vinst[(va, vb)] = inst.vocal_chop(vowel=va, vowel_to=vb, shift=float(rng.uniform(1.1, 1.22)),
                                              scoop=float(rng.uniform(-1.5, -0.6)), vibrato=0.2, breath=0.1)
    vlayers = {}
    for (va, vb), vi in vinst.items():
        def mk(va=va, vb=vb):
            def notes(c):
                on = (c.kind == "drop" or (c.kind == "groove" and c.i >= 8 and (c.i // 4) % 2 == 1)
                      or (c.kind == "breakdown"))
                if not on:
                    return []
                off = (c.i % 2) * 16
                return [(s - off, l * 0.85, key.degree(d, 4), 0.85) for s, l, d, a, b in vph
                        if off <= s < off + 16 and a == va and b == vb]
            return notes
        vlayers[(va, vb)] = song.notes(f"vox_{va}{vb}", vi, mk(), bus="vox", gain_db=-6.5, sidechain=0.3,
                                       sends={"delay": 0.25, "reverb": 0.2}, pan=0.05)

    # breakdown pad under the organ
    pad_i = inst.pad(attack=0.8, cutoff=1800.0, detune=0.25, warmth=0.6)
    song.notes("pad", pad_i, lambda c: [(0, 31.5, chords[chord_i(c)], 0.6)] if c.kind == "breakdown" and c.i % 2 == 0
               else [], gain_db=-14.0, sends={"hall": 0.35}, width=1.6)

    # ---------------------------------------------------------------- FX
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.12})
    crash = drums.crash(decay=2.0, rng=rng)
    for s in secs:
        if s.kind in ("groove", "drop", "outro"):
            fxl.add(crash, s.start_bar, gain_db=-10.0)
        if s.kind == "drop":
            fxl.add(fx.impact(2.0, rng=rng), s.start_bar, gain_db=-10.0)
            fxl.add(crash, s.start_bar + 16, gain_db=-9.0)
            fxl.add(fx.noise_sweep(bar_sec * 4, up=True, rng=rng), s.start_bar + 16, align="end", gain_db=-16.0)
        if s.kind == "breakdown":
            fxl.add(fx.riser(bar_sec * s.bars, "noise", f_lo=300, f_hi=9000, rng=rng), s.end_bar, align="end", gain_db=-11.0)
            fxl.add(fx.reverse_cymbal(bar_sec, rng=rng), s.end_bar, align="end", gain_db=-10.0)
    fxl.add(fx.reverse_cymbal(bar_sec, rng=rng), bass_in, align="end", gain_db=-13.0)

    # ---------------------------------------------------------------- mix
    song.buses["drums"].eq = [("peak", 5000.0, 1.5, 0.8)]
    song.buses["drums"].width = 1.25
    song.buses["music"].width = 1.3
    song.buses["music"].eq = [("peak", 1600.0, 2.5, 0.7)]
    song.buses["vox"].eq = [("peak", 2000.0, 2.0, 0.8)]
    song.master.lufs = -9.0
    song.description_he = (
        f"יו-קיי גראז' ב-{int(song.bpm)} BPM בסולם {plan['key']}: תופי טו-סטפ קופצניים עם סווינג של כ-{int(song.swing)}%, "
        f"סטאבים של אורגן בסגנון M1 משנות ה-90, צ'ופים ווקאליים מקוטעים (סינתטיים, בלי מילים), סאב קופצני "
        f"עם קפיצות אוקטבה — ובדרופ באסליין 'דרד' בסגנון ספיד גראז' וחצי שני עם קיק ישר ב-4/4.")
    song.instruments = ["2-step shuffled drums", "clap + rim + tight snare", "skippy hats & shaker", "M1-style organ stabs",
                        "formant vocal chops", "bouncy sub bass", "speed-garage dread bass", "breakdown pad"]
    from ..theory import compatible_keys
    cam = plan["camelot"]
    song.mix_tips_he = (
        f"טיפ ערבוב: 16 תיבות ראשונות תופים בלבד (טו-סטפ — הקיק לא על כל פעמה, אז הקשיבו לסנר ב-2 וב-4 כדי לסנכרן). "
        f"הסאב נכנס בתיבה {bass_in + 1} (Hot Cue B), ברייקדאון קצר בתיבה {bd.start_bar + 1} ודרופ בתיבה "
        f"{drop.start_bar + 1}; מהתיבה {drop.start_bar + 17} הקיק עובר ל-4/4 — נקודה נוחה למעבר לטראק האוס. "
        f"האאוטרו מתיבה {outro.start_bar + 1}, ו-16 התיבות האחרונות תופים בלבד. שכנים ב-Camelot: {cam} ↔ "
        f"{', '.join(compatible_keys(cam)[1:4])}.")
    return song
