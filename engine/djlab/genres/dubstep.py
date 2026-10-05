"""Dubstep recipe (138–142 BPM, half-time feel).

Half-time drums (kick on 1 + syncopated kicks, huge snare on beat 3, 8th hats with triplet rolls and
tom/rim fills), a big build (pads, sub teaser, siren, accelerating snare roll, riser, quarter-note
kicks, one-beat silence) into the drop. Drops: **wobble bass** whose ladder filter + vowel formant
follow a tempo-synced LFO (1/8, 1/16, 1/8-triplet, 1/4 per note), answered by an FM **growl** bass
(index + 'o→a→e' formant on the LFO), all over a clean mono sine sub. Breakdown with dark pads and a
bell melody, second drop with more growl.

DJ rules: 16-bar drums-only intro, 16-bar build (sub/pad enter on bar 17 = Hot Cue B), drop on bar 33,
24-bar outro whose last 16 bars are drums only; sections on the 8-bar grid.
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from .. import ext_breadth as xb
from ..arrangement import Song
from ..theory import voice_lead
from . import register

TPL = [("Intro", "intro", 16, 4, 0), ("Build", "build", 16, 6, 0), ("Drop", "drop", 32, 10, 2),
       ("Breakdown", "breakdown", 16, 5, 0), ("Drop 2", "drop", 24, 10, 1), ("Outro", "outro", 24, 4, 0)]

KICKS = [["x.........x.....", "x.....x...x....."], ["x.........x.....", "x.........x..x.."],
         ["x.......x.......", "x.....x...x....."]]
SNARE = "........X......."
HATS = ["x.x.x.x.x.x.x.x.", "x.xxx.x.x.xxx.x.", "x...x.x.x...x.xx"]
TRIP_HATS = "x.xx.xx.xx.xx.xxxxxxxxxx"  # 24 steps = 16th triplets on the last half

# 4-bar riffs (64 steps): (step, len, semitone offset, voice 'w' wobble / 'g' growl, LFO flag)
RIFFS = [
    [(0, 8, 0, "w", "w8"), (8, 4, 0, "w", "w16"), (12, 4, 3, "w", "w12"),
     (16, 6, 0, "w", "w8"), (22, 2, 12, "w", "w16"), (24, 8, -2, "w", "w4"),
     (32, 4, 0, "g", "w8"), (36, 4, 0, "g", "w16"), (40, 8, 5, "g", "w4"), (48, 4, 3, "w", "w16"),
     (52, 4, 0, "w", "w12"), (56, 8, -4, "g", "w8")],
    [(0, 6, 0, "w", "w8"), (6, 2, 0, "w", "w16"), (8, 8, 7, "w", "w8"),
     (16, 4, 0, "g", "w8"), (20, 4, 3, "g", "w16"), (24, 8, 0, "w", "w4"),
     (32, 8, 0, "w", "w8"), (40, 4, -2, "w", "w16"), (44, 4, -4, "w", "w12"), (48, 4, 0, "g", "w16"),
     (52, 4, 0, "g", "w8"), (56, 4, 3, "w", "w16"), (60, 4, 5, "g", "w4")],
]
RIFF2_SWAP = {"w": "g", "g": "w"}


@register("dubstep")
def build(plan: dict, rng: np.random.Generator) -> Song:
    song = Song(plan, rng, swing=50.0)
    key = song.key
    song.arrange(TPL, song.target_bars())
    secs = song.sections
    intro, buildsec, drop1 = song.find("intro"), song.find("build"), song.find("drop")
    bd, drop2, outro = song.find("breakdown"), song.find("drop", 1), song.find("outro")
    song.mix_in_bar = buildsec.start_bar
    bass_off = outro.start_bar + outro.bars - 16
    bar_sec = song.grid.bar_sec

    root = xb.note_in_range(key.root_pc, 41.0)   # F1 = 43.7 Hz

    # ---------------------------------------------------------------- drums
    kick = drums.kick("hard", tune_hz=xb.kick_tune(key, 44.0, 62.0), decay=float(rng.uniform(0.3, 0.38)),
                      click=0.7, drive=float(rng.uniform(2.5, 4.0)), rng=rng)
    kp = KICKS[int(rng.integers(len(KICKS)))]

    def kick_pat(c):
        if c.kind == "breakdown":
            return None if c.bars_left > 4 else ("x.........x....." if c.bars_left > 1 else None)
        if c.kind == "build":
            if c.bars_left == 1:
                return None
            if c.bars_left <= 4:
                return "x...x...x...x..." if c.bars_left > 2 else "x.x.x.x.x.x.x.x."
            return kp[c.i % 2] if c.i >= 8 else "x..............."
        return kp[c.i % 2]

    song.hits("kick", kick, kick_pat, gain_db=-2.0, sc_source=True, humanize=0.0)
    snr = xb.layered_snare(rng, tone_hz=float(rng.uniform(180, 210)), snappy=0.9, decay=0.24, clap_amt=0.8,
                           crack_hz=float(rng.uniform(1600, 2000)))

    def snare_pat(c):
        if c.kind == "build":
            if c.bars_left == 1:
                return None
            if c.bars_left <= 8:
                return ["........X.......", "....X.......X...", "X...X...X...X...", "X...X...X...X...",
                        "X.X.X.X.X.X.X.X.", "XXXXXXXXXXXXXXXX", "rrrrrrrrrrrrrrrr", None][8 - c.bars_left]
            return SNARE
        if c.kind == "breakdown":
            if c.bars_left <= 4:
                return ["X...X...X...X...", "X.X.X.X.X.X.X.X.", "XXXXXXXXXXXXXXXX", None][4 - c.bars_left]
            return SNARE if c.i >= 4 else None
        if c.kind == "intro" and c.i < 4:
            return None
        return SNARE if not c.phrase_end else "........X.....XX"

    sn = song.hits("snare", snr, snare_pat, gain_db=-2.5, sc_source=True, sends={"reverb": 0.3, "room": 0.15})
    sn.automate("gain_db", [(0, 0.0), (buildsec.end_bar - 8 - 1e-3, 0.0), (buildsec.end_bar - 8, -10.0),
                            (buildsec.end_bar - 1, 0.0)])
    hats = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.2}, decay=float(rng.uniform(0.03, 0.045)),
                          tone=float(rng.uniform(1.0, 1.25)))
    hp_ = HATS[int(rng.integers(len(HATS)))]

    def hat_pat(c):
        if c.kind == "breakdown" and c.bars_left > 4:
            return "x...x...x...x..." if c.i >= 4 else None
        if c.phrase_end and c.kind in ("drop", "outro"):
            return TRIP_HATS
        return hp_

    song.hits("hats", hats, hat_pat, gain_db=-12.5, pan=0.35, humanize=0.15)
    oh = drums.hat(open_=True, decay=0.25, tone=1.05, rng=rng)
    song.hits("open_hat", oh, lambda c: "......x.......x." if c.kind == "drop" and c.i % 2 == 1 else None,
              gain_db=-13.0, pan=-0.3)
    rim = drums.rimshot(float(rng.uniform(1500, 1800)), rng=rng)
    song.hits("rim", rim, lambda c: "...x......x..x.." if c.kind == "drop" and c.i % 4 == 3 else None,
              gain_db=-15.0, pan=0.4, sends={"delay": 0.2})
    toms = [drums.tom(float(rng.uniform(90, 110)), 0.4, rng=rng), drums.tom(float(rng.uniform(130, 160)), 0.35, rng=rng)]
    song.hits("toms", toms, lambda c: "..........x.x.xx" if c.kind == "drop" and c.i % 8 == 7 else None,
              gain_db=-12.0, sends={"reverb": 0.2})

    # ---------------------------------------------------------------- harmony
    degs = [[0, 5, 3, 4], [0, 5, 6, 4], [0, 3, 5, 6]][int(rng.integers(3))]
    chords, prev = [], None
    for d in degs:
        ch = voice_lead(prev, key.chord(d, 3, 3), center=key.root(4) - 3)
        chords.append(ch)
        prev = ch

    def chord_i(c):
        return (c.i // 4) % 4

    # ---------------------------------------------------------------- wobble / growl / sub
    riff = RIFFS[int(rng.integers(len(RIFFS)))]

    def riff_events(c, voice=None, swap=False):
        if c.kind not in ("drop",) and not (c.kind == "outro" and c.bar < bass_off):
            return []
        off = (c.i % 4) * 16
        out = []
        for s, l, o, v, flag in riff:
            vv = RIFF2_SWAP[v] if swap else v
            if off <= s < off + 16 and (voice is None or vv == voice):
                out.append((s - off, l - 0.2, root + o, 0.95, flag))
        if c.before("breakdown", 1) or c.before("outro", 1) and False:
            out = [e for e in out if e[0] < 8]
        return out

    def wob_notes(c):
        if c.kind == "outro":
            return [(0, 15.8, root, 0.8, "w4")] if c.bar < bass_off and c.i % 2 == 0 else []
        return riff_events(c, "w", swap=(c.name == "Drop 2" and c.i % 8 >= 4))

    def growl_notes(c):
        if c.kind == "outro":
            return []
        return riff_events(c, "g", swap=(c.name == "Drop 2" and c.i % 8 >= 4))

    def sub_notes(c):
        if c.kind == "build":
            return [(0, 31.5, root + (0 if (c.i // 2) % 2 == 0 else -4), 0.6, "")] if c.i % 2 == 0 and c.bars_left > 1 else []
        if c.kind == "breakdown":
            return []
        if c.kind == "outro":
            return [(0, 15.8, root, 0.8, "")] if c.bar < bass_off else []
        return [(s, l, m, v, "") for s, l, m, v, _ in riff_events(c)]

    wob = song.add(xb.SynthLine("wobble", xb.Wobble(cut_lo=float(rng.uniform(100, 140)),
                                                    cut_hi=float(rng.uniform(2600, 3600)), res=0.5, drive=2.6,
                                                    dist=0.6, fm_amt=1.6, vowel=0.45, hp_hz=95.0, chorus_mix=0.3),
                                wob_notes, bus="bass", gain_db=0.0, sidechain=0.55, sc_release_ms=120.0))
    growl = song.add(xb.SynthLine("growl", xb.Growl(ratio=float(rng.choice([1.0, 2.0])), index=float(rng.uniform(3.5, 5.5)),
                                                    feedback=0.7, dist=0.55, hp_hz=110.0),
                                  growl_notes, bus="bass", gain_db=-3.0, sidechain=0.55, sc_release_ms=120.0))
    sub = song.add(xb.SynthLine("sub", xb.SubLine(harm=0.1, drive=1.3, glide_ms=40.0), sub_notes, bus="bass",
                                gain_db=-7.0, sidechain=0.5, sc_release_ms=150.0))
    sub.automate("gain_db", [(buildsec.start_bar, -12.0), (buildsec.end_bar - 1, -6.0), (buildsec.end_bar, 0.0)])
    wob.automate("cutoff", [(0, 1.0), (outro.start_bar, 1.0), (bass_off, 0.3)])

    # ---------------------------------------------------------------- music: pads, bells, siren, vocal
    pad_i = inst.pad(attack=1.5, release=2.0, cutoff=1400.0, detune=0.3, warmth=0.6)

    def pad_notes(c):
        if c.i % 4:
            return []
        if c.kind in ("build", "breakdown"):
            return [(0, 63.5, chords[chord_i(c)], 0.75)]
        return []

    pad = song.notes("pad", pad_i, pad_notes, gain_db=-11.0, sends={"hall": 0.4}, width=1.7, hp=150.0)
    pad.automate("lp", [(buildsec.start_bar, 500.0), (buildsec.end_bar, 5000.0), (bd.start_bar, 700.0),
                        (bd.end_bar, 5000.0)])
    bell = inst.bell(ratio=3.5, index=2.5, decay=0.9)
    mel = [(0, 3, 4), (3, 3, 3), (6, 2, 2), (8, 6, 0), (16, 3, 4), (19, 3, 5), (22, 2, 4), (24, 8, 2),
           (32, 3, 4), (35, 3, 3), (38, 2, 2), (40, 6, 0), (48, 4, 2), (52, 4, 1), (56, 8, -1)]

    def bell_notes(c):
        if not (c.kind == "breakdown" or (c.kind == "build" and c.i >= 8)):
            return []
        off = (c.i % 4) * 16
        return [(s - off, l, key.degree(d, 5), 0.8) for s, l, d in mel if off <= s < off + 16]

    song.notes("bells", bell, bell_notes, gain_db=-13.0, sends={"delay": 0.35, "hall": 0.3}, pan=0.15, width=1.4)
    vox_i = inst.vocal_chop(vowel="o", vowel_to="a", shift=1.0, scoop=-2.0, vibrato=0.3, release=0.3)
    song.notes("vox", vox_i, lambda c: [(0, 6, key.degree(4, 4), 0.85), (8, 6, key.degree(2, 4), 0.8)]
               if (c.kind == "build" and c.bars_left == 2) or (c.kind == "breakdown" and c.i in (0, 8)) else [],
               bus="vox", gain_db=-8.0, sends={"delay": 0.35, "hall": 0.3})

    # ---------------------------------------------------------------- FX
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.12})
    crash = drums.crash(decay=2.4, rng=rng)
    for s in secs:
        if s.kind == "drop":
            fxl.add(crash, s.start_bar, gain_db=-8.0)
            fxl.add(fx.impact(3.0, rng=rng), s.start_bar, gain_db=-6.0)
            for b in range(s.start_bar + 8, s.end_bar, 8):
                fxl.add(crash, b, gain_db=-12.0)
        if s.kind in ("build", "breakdown"):
            fxl.add(fx.riser(bar_sec * 8, "both", f_lo=200, f_hi=12000, pitch_from=45, pitch_to=84, rng=rng),
                    s.end_bar - 1, align="end", gain_db=-8.0)
            fxl.add(xb.siren(bar_sec * 2, float(rng.uniform(500, 700)), 0.6, 4.0), s.end_bar - 3, gain_db=-17.0)
            fxl.add(fx.reverse_cymbal(bar_sec, rng=rng), s.end_bar, align="end", gain_db=-9.0)
        if s.kind == "breakdown":
            fxl.add(fx.downlifter(bar_sec * 4, rng=rng), s.start_bar, gain_db=-9.0)
            fxl.add(xb.pitch_dive(bar_sec * 2, 1500.0, 40.0, rng=rng), s.start_bar, gain_db=-12.0)
    fxl.add(crash, buildsec.start_bar, gain_db=-11.0)
    fxl.add(crash, outro.start_bar, gain_db=-10.0)
    fxl.add(fx.noise_sweep(bar_sec * 4, up=True, rng=rng), buildsec.start_bar, align="end", gain_db=-17.0)

    # ---------------------------------------------------------------- mix
    song.buses["drums"].eq = [("peak", 3500.0, 1.0, 0.8), ("peak", 200.0, 1.5, 1.0)]
    song.buses["drums"].width = 1.2
    song.buses["bass"].comp = dict(threshold_db=-10.0, ratio=3.0, attack_ms=5.0, release_ms=60.0)
    song.buses["bass"].sat = 0.2
    song.buses["music"].width = 1.3
    song.master.lufs = -9.0
    song.description_he = (
        f"דאבסטפ ב-{int(song.bpm)} BPM (תחושת חצי טמפו) בסולם {plan['key']}: תופים בחצי טמפו עם סנר ענק בפעמה 3, "
        f"בילד גדול עם סנר-רול, סירנה ורייזר, ודרופ של באס וובל שהפילטר שלו מסונכרן לטמפו (1/8, 1/16 וטריולות) "
        f"שעונה לו באס גראול ב-FM — הכול מעל סאב מונו נקי וכבד. ברייקדאון עם פדים כהים ופעמונים.")
    song.instruments = ["half-time drums", "huge layered snare", "tempo-synced wobble bass", "FM growl bass",
                        "clean mono sub", "dark pads", "FM bell melody", "siren, riser, impact"]
    from ..theory import compatible_keys
    cam = plan["camelot"]
    song.mix_tips_he = (
        f"טיפ ערבוב: 16 תיבות ראשונות תופים בלבד, בתיבה {buildsec.start_bar + 1} (Hot Cue B) נכנסים סאב ופדים "
        f"והבילד מתחיל; הדרופ בתיבה {drop1.start_bar + 1} (Hot Cue D). ברייקדאון בתיבה {bd.start_bar + 1}, "
        f"דרופ 2 בתיבה {drop2.start_bar + 1}, אאוטרו מתיבה {outro.start_bar + 1} (16 התיבות האחרונות תופים בלבד). "
        f"Rekordbox עשוי להציג 70 BPM (חצי טמפו) — הגריד זהה, אפשר להכפיל. מעבר קלאסי: "
        f"לחתוך את הטראק היוצא על הסנר של הפעמה 3 ממש לפני הדרופ. שכנים ב-Camelot: {cam} ↔ "
        f"{', '.join(compatible_keys(cam)[1:4])}.")
    return song
