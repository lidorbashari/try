"""Tech House flavors used by ``tech_house.py`` (the ``classic`` flavor lives there).

* ``talking``   — Bassline Bandit style: the bass IS the hook (talking / wah formant bass with
                  call-and-response riffs), lean drums, a vowel "shout", a bass tease in the breakdown.
* ``warehouse`` — darker, straighter and more percussive: driven kick + low rumble, rolling 16th
                  mono bass, toms, metallic perc, 16th rims, dub chord stab into delay, dark vox,
                  two breakdowns/drops.
* ``shuffle``   — heavy MPC swing (61–63 %), bouncy octave bass, triplet bongos (3-against-4),
                  percussive organ stabs through a rotary chorus, call-and-response vocal chops.

Same DJ rules as the classic recipe: 32-bar drums-only intro (bass at bar 33 = Hot Cue B), 32-bar
outro whose last 16 bars are drums only, sections on 8-bar phrases, crash/fill phrase markers,
kick out for one bar before each drop, riser + snare roll + impact into drops.
"""
from __future__ import annotations

import numpy as np

from .. import drums, ext_house as eh, fx, instruments as inst
from ..arrangement import Song, clip, euclid
from ..dsp import eq_peak
from ..theory import Key

TEMPLATES = {
    "talking": [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 24, 6, 2), ("Breakdown", "breakdown", 16, 3, 0),
                ("Drop", "drop", 32, 8, 3), ("Outro", "outro", 32, 4, 0)],
    "warehouse": [("Intro", "intro", 32, 5, 0), ("Groove", "groove", 16, 7, 2), ("Breakdown", "breakdown", 8, 4, 0),
                  ("Drop", "drop", 24, 9, 3), ("Breakdown 2", "breakdown", 8, 5, 0), ("Drop 2", "drop", 16, 9, 1),
                  ("Outro", "outro", 32, 5, 0)],
    "shuffle": [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 32, 6, 2), ("Breakdown", "breakdown", 16, 4, 0),
                ("Drop", "drop", 24, 8, 3), ("Outro", "outro", 32, 4, 0)],
}

KICK = "x...x...x...x..."

# talking-bass riffs: 2 bars (32 steps) of (step, len, semitones from root, vel). Velocity = how far
# the formant "mouth" opens, so accents literally talk.
TALK_RIFFS = [
    [(2, 2, 0, 1.0), (6, 1, 0, 0.6), (7, 2, 12, 0.95), (10, 2, 0, 1.0), (13, 1, 10, 0.75), (14, 2, 7, 0.9),
     (18, 2, 0, 1.0), (22, 1, 0, 0.6), (23, 2, 3, 0.95), (26, 1.5, 0, 1.0), (28, 1, -2, 0.8), (30, 2, 0, 0.9)],
    [(2, 3, 0, 1.0), (6, 1, 0, 0.55), (7, 1, 0, 0.8), (10, 3, 0, 1.0), (14, 1, 12, 0.9), (15, 1, 10, 0.7),
     (18, 3, 0, 1.0), (22, 1, 0, 0.55), (23, 1, 0, 0.8), (26, 2, 5, 1.0), (29, 1, 3, 0.8), (30, 2, -2, 0.95)],
    [(2, 1.5, 0, 0.9), (3, 2, 0, 1.0), (7, 1, 0, 0.6), (10, 1.5, 0, 0.9), (11, 2, 12, 1.0), (14, 1, 10, 0.7),
     (18, 1.5, 0, 0.9), (19, 2, 0, 1.0), (23, 1, 3, 0.7), (26, 1.5, 7, 1.0), (28, 1, 5, 0.8), (30, 2, 3, 1.0)],
]

# rolling warehouse bass: steps around the kick, accents on the off-beat 8ths
ROLL_STEPS = [(2, 1.0), (3, 0.7), (6, 1.0), (7, 0.7), (10, 1.0), (11, 0.7), (14, 1.0), (15, 0.75)]
ROLL_VARIATIONS = [{15: 12}, {7: 3, 15: -2}, {11: 12, 15: 7}, {3: 0, 15: 10}]

# bouncy octave bass for the shuffle flavor
BOUNCE_RIFFS = [
    [(2, 1, 0, 1.0), (3, 1, 12, 0.65), (6, 1, 0, 0.9), (7, 1, 12, 0.6), (10, 1, 0, 1.0), (11, 1, 12, 0.65),
     (14, 1, 7, 0.85), (15, 1, 10, 0.6), (18, 1, 0, 1.0), (19, 1, 12, 0.65), (22, 1, 0, 0.9), (23, 1, 12, 0.6),
     (26, 1, 3, 1.0), (27, 1, 15, 0.65), (30, 1, 5, 0.85), (31, 1, 7, 0.7)],
    [(2, 1.5, 0, 1.0), (5, 1, 12, 0.7), (6, 1, 0, 0.85), (10, 1.5, 0, 1.0), (13, 1, 12, 0.7), (14, 1, 10, 0.8),
     (18, 1.5, 0, 1.0), (21, 1, 12, 0.7), (22, 1, 0, 0.85), (26, 1.5, -2, 1.0), (29, 1, 10, 0.7), (30, 1, 0, 0.85)],
]

VOX_SHUFFLE = [
    [(3, 1, 4, 0.9), (6, 1, 4, 0.7), (8, 2, 2, 0.9), (14, 1, 0, 0.7), (19, 1, 4, 0.9), (22, 1, 5, 0.8),
     (24, 3, 4, 0.9)],
    [(2, 1, 7, 0.9), (4, 1, 7, 0.6), (6, 2, 6, 0.9), (11, 1, 4, 0.8), (18, 1, 7, 0.9), (20, 1, 7, 0.6),
     (22, 4, 9, 0.9)],
]

ORGAN_RHYTHMS = [
    [(3, 1, 0.9), (10, 1, 0.8), (14, 1, 0.6)],
    [(2, 1, 0.9), (6, 1, 0.6), (11, 1.5, 0.9)],
    [(0, 1, 0.8), (3, 1, 0.9), (8, 1, 0.6), (11, 1, 0.8)],
]


def build_flavor(plan: dict, rng: np.random.Generator, flavor: str) -> Song:
    sw = {"talking": (55.0, 57.0), "warehouse": (52.0, 53.0), "shuffle": (61.0, 63.0)}[flavor]
    song = Song(plan, rng, swing=float(rng.uniform(*sw)))
    key: Key = song.key
    song.arrange(TEMPLATES[flavor], song.target_bars())
    groove = song.bar("groove")
    song.mix_in_bar = groove
    outro = song.find("outro")
    bass_off = outro.start_bar + outro.bars - 16
    root = eh.bass_root(key)
    drop1 = song.bar("drop")

    # ================================================================ drums (shared core, flavored)
    kd = {"talking": dict(decay=rng.uniform(0.27, 0.31), click=rng.uniform(0.5, 0.62), drive=1.7),
          "warehouse": dict(decay=rng.uniform(0.3, 0.34), click=rng.uniform(0.6, 0.72), drive=2.3),
          "shuffle": dict(decay=rng.uniform(0.26, 0.3), click=rng.uniform(0.45, 0.58), drive=1.5)}[flavor]
    kick_s = drums.kick("tech_house", tune_hz=eh.kick_tune(key, 46, 58), rng=rng, **{k: float(v) for k, v in kd.items()})

    def kick_pat(c):
        if c.kind == "breakdown":
            return None
        if c.before("drop", 1):
            return None
        if c.before("breakdown", 1):
            return "x...x...x......."
        return KICK

    song.hits("kick", kick_s, kick_pat, gain_db=-1.5, sc_source=True, humanize=0.0)

    clap_s = drums.variants(drums.clap, 3, rng, jitter={"tone_hz": 0.05},
                            tone_hz=float(rng.uniform(1050, 1350)), tail=float(rng.uniform(0.15, 0.22)))
    clap_p = {"talking": "....x.......x...", "warehouse": "....x.......x...", "shuffle": "....x.......x..g"}[flavor]

    def clap_pat(c):
        if c.kind == "breakdown":
            return "....x.......x..." if c.bars_left <= 4 and c.section.bars > 8 else None
        if c.kind == "intro" and c.i < 8:
            return None
        return clap_p if not c.phrase_end else "....x.......x.xx"

    song.hits("clap", clap_s, clap_pat, gain_db=-3.0, sends={"reverb": 0.2 if flavor != "warehouse" else 0.32,
                                                             "room": 0.15}, timing_ms=1.5)
    if flavor == "warehouse":  # snap layered on the clap: harder, more industrial transient
        song.hits("snap", drums.snap(rng=rng), lambda c: clap_pat(c) if c.kind in ("groove", "drop") else None,
                  gain_db=-11.0, sends={"reverb": 0.2})

    hat_p = {"talking": "gogxgogxgogxgogx", "warehouse": "xgxoxgxoxgxoxgxX"[:16], "shuffle": "x.xgx.xgx.xgx.xg"}[flavor]
    hats_c = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.15}, decay=float(rng.uniform(0.03, 0.05)),
                            tone=float(rng.uniform(0.95, 1.2) if flavor != "warehouse" else rng.uniform(1.1, 1.3)))

    def hat_pat(c):
        if c.kind == "breakdown" and c.bars_left > 4:
            return None
        if c.kind == "intro" and c.i < 4:
            return None
        return hat_p

    song.hits("hats", hats_c, hat_pat, gain_db=-14.0 if flavor != "warehouse" else -13.0, pan=0.3, humanize=0.12)

    ohat = drums.hat(open_=True, decay=float(rng.uniform(0.16, 0.24)), tone=float(rng.uniform(0.95, 1.1)), rng=rng)
    oh_p = "..x...x...x...x." if flavor != "shuffle" else "..x...x...x...xg"
    song.hits("open_hat", ohat, lambda c: oh_p if (c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 16)
                                                   or (c.kind == "outro" and c.bars_left > 8)) else None,
              gain_db=-11.5, pan=-0.15, sends={"room": 0.12})

    shk = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=float(rng.uniform(0.07, 0.1)))
    sh_p = {"talking": "gxgogxgogxgogxgo", "warehouse": "oxgxoxgxoxgxoxgx", "shuffle": ".xgo.xgo.xgo.xgo"}[flavor]
    song.hits("shaker", shk, lambda c: sh_p if c.kind != "breakdown" and not (c.kind == "intro" and c.i < 8) else None,
              gain_db=-17.0, pan=-0.5, humanize=0.15, timing_ms=2.0)

    ride = drums.ride(decay=1.1, rng=rng)
    song.hits("ride", ride, lambda c: ("x.x.x.x.x.x.x.x." if flavor == "warehouse" else "x...x...x...x...")
              if c.kind == "drop" else None, gain_db=-19.0, pan=0.25)

    snr = drums.snare(tone_hz=float(rng.uniform(180, 220)), snappy=0.8, decay=0.12, rng=rng)
    song.hits("snare_roll", snr, eh.snare_roll, gain_db=-14.0, sends={"reverb": 0.25}) \
        .automate("gain_db", eh.ramp_into(song, "drop", 4, -12.0, 0.0))

    # ---- flavor percussion
    if flavor == "talking":
        congas = [drums.conga(eh.key_hz(key, 180, 240, rng), "open", rng=rng),
                  drums.conga(eh.key_hz(key, 280, 340, rng), "slap", rng=rng)]
        cp = ["...x......x..x..", "..x....x..x....."][int(rng.integers(2))]
        song.hits("perc_conga", congas, lambda c: ("......x.x.xxx.xx" if c.phrase_end else cp)
                  if c.kind in ("groove", "drop", "outro") or (c.kind == "intro" and c.i >= 16) else None,
                  gain_db=-12.0, pan=-0.55, sends={"room": 0.2})
        rim = drums.rimshot(float(rng.uniform(1500, 1900)), rng=rng)
        song.hits("rim", rim, lambda c: "..x..x....x..x.." if c.kind == "drop" and c.i % 4 >= 2 else None,
                  gain_db=-17.0, pan=0.3, sends={"delay8": 0.15})
    elif flavor == "warehouse":
        toms = [drums.tom(eh.key_hz(key, 90, 115, rng), 0.35, rng=rng), drums.tom(eh.key_hz(key, 125, 155, rng), 0.3, rng=rng),
                drums.tom(eh.key_hz(key, 170, 210, rng), 0.25, rng=rng)]
        tom_p = ["......x..x....x.", "...x......x...x.", "......x...x..x.."][int(rng.integers(3))]
        song.hits("toms", toms, lambda c: ("..........x.x.xx" if c.phrase_end else tom_p)
                  if c.kind in ("drop",) or (c.kind == "groove" and c.i >= 8) or (c.kind == "intro" and c.i >= 24)
                  else None, gain_db=-12.0, pan=-0.35, sends={"room": 0.25, "reverb": 0.08})
        rim = drums.rimshot(float(rng.uniform(1700, 2100)), rng=rng)
        song.hits("rim16", drums.variants(lambda rng=None: drums.rimshot(float(1800), rng=rng), 3, rng) + [rim],
                  lambda c: "gogxgogogogxgogo" if c.kind == "drop" or (c.kind == "groove" and c.i >= 8) else
                  ("g.g.g.g.g.g.g.g." if c.kind in ("intro", "outro") and c.i >= 16 and not (c.kind == "outro" and c.bars_left <= 8) else None),
                  gain_db=-20.0, pan=0.45, humanize=0.2)
        metal = drums.perc_blip(eh.key_hz(key, 580, 900, rng), 0.05, fm_index=3.0, ratio=1.41, rng=rng)
        mp = euclid(int(rng.integers(3, 6)), 16, int(rng.integers(1, 5)))
        song.hits("metal_perc", metal, lambda c: mp if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 16)
                  else None, gain_db=-15.0, pan=0.55, sends={"delay8": 0.18, "room": 0.1},
                  fx=[lambda x: fx.bitcrush(x, 10, 2)])
    else:  # shuffle
        bongos = [drums.bongo(eh.key_hz(key, 440, 530, rng), "open", rng=rng),
                  drums.bongo(eh.key_hz(key, 590, 700, rng), "slap", rng=rng),
                  drums.bongo(eh.key_hz(key, 520, 620, rng), "mute", rng=rng)]
        trip = ["x..x..x.xx..", "x.xx..x..x.x", ".x.x.xx..x.x"][int(rng.integers(3))]  # 12 steps = 8th triplets
        song.hits("bongo_trip", bongos, lambda c: trip if (c.kind in ("groove", "drop") and c.i % 4 >= 2)
                  or (c.kind == "intro" and c.i >= 24) else None, gain_db=-14.0, pan=0.55, humanize=0.15,
                  sends={"room": 0.18})
        congas = [drums.conga(eh.key_hz(key, 180, 240, rng), "open", rng=rng),
                  drums.conga(eh.key_hz(key, 260, 320, rng), "mute", rng=rng)]
        song.hits("perc_conga", congas, lambda c: ("...x..x.......x." if not c.phrase_end else "......x.x.xxx.xx")
                  if c.kind in ("groove", "drop", "outro") or (c.kind == "intro" and c.i >= 16) else None,
                  gain_db=-13.0, pan=-0.5, sends={"room": 0.2})
        tamb = drums.tambourine(0.18, rng=rng)
        song.hits("tamb", tamb, lambda c: "..x...x...x...x." if c.kind == "drop" else None, gain_db=-18.0, pan=0.35)

    # ================================================================ bass
    def bass_ok(c):
        return c.kind not in ("intro", "breakdown") and c.bar < bass_off

    if flavor == "talking":
        riff = TALK_RIFFS[int(rng.integers(len(TALK_RIFFS)))]
        tb = eh.talking_bass(cutoff=float(rng.uniform(220, 300)), wah_time=float(rng.uniform(0.11, 0.16)),
                             f1=(220.0, float(rng.uniform(800, 1000))), f2=(650.0, float(rng.uniform(1900, 2400))),
                             drive=float(rng.uniform(1.8, 2.4)), sub_oct=root >= 38)
        bclip = clip([(s, l, root + o, v) for s, l, o, v in riff], 2)
        bd = song.find("breakdown")

        def bass_notes(c):
            if c.kind == "breakdown":  # bass tease: last 8 bars of the breakdown, filtered (see automation)
                return bclip(c) if c.bars_left <= 8 and not c.last else []
            if not bass_ok(c):
                return []
            ev = bclip(c)
            if c.before("drop", 1) or c.before("breakdown", 1):
                ev = [e for e in ev if e[0] < 8]
            return ev

        bass = song.notes("bass", tb, bass_notes, bus="bass", gain_db=-3.5, sidechain=0.5, sc_release_ms=140.0,
                          swing=song.swing, humanize=0.03)
        bass.automate("lp", [(groove, 600), (groove + 8, 2500), (drop1 - 16, 2500), (bd.end_bar - 8, 300),
                             (drop1 - 0.01, 1200), (drop1, 9000), (outro.start_bar, 9000), (bass_off, 700)])
        bass.automate("gain_db", [(bd.end_bar - 8.01, 0.0), (bd.end_bar - 8, -6.0), (drop1 - 0.01, -1.5), (drop1, 0.0)])
    elif flavor == "warehouse":
        var = ROLL_VARIATIONS[int(rng.integers(len(ROLL_VARIATIONS)))]

        def roll_bar(c):
            if not bass_ok(c):
                return []
            ev = []
            for st, v in ROLL_STEPS:
                off = var.get(st, 0) if c.i % 2 == 1 else 0
                fl = "a" if v >= 1.0 else ""
                ev.append((st, 0.8, root + off, v, fl))
            if c.before("drop", 1) or c.before("breakdown", 1):
                ev = [e for e in ev if e[0] < 8]
            return ev

        ms = inst.MonoSynth(wave=str(rng.choice(["saw", "square"])), cutoff=200.0, res=float(rng.uniform(0.3, 0.45)),
                            env_mod=float(rng.uniform(1.6, 2.2)), decay=float(rng.uniform(0.07, 0.1)), accent=0.5,
                            glide_ms=25.0, drive=2.2, sustain=0.6, dist=0.15)
        bass = song.line("bass", ms, roll_bar, bus="bass", gain_db=-4.0, sidechain=0.6, sc_release_ms=120.0)
        cut = []
        for s in song.sections:
            if s.kind == "groove":
                cut += [(s.start_bar, 180), (s.end_bar, 420)]
            elif s.kind == "drop":
                cut += [(s.start_bar, 380), (s.start_bar + s.bars * 0.75, 700), (s.end_bar, 450)]
            elif s.kind == "outro":
                cut += [(s.start_bar, 400), (bass_off, 160)]
        bass.automate("cutoff", cut)
        rum = song.hits("rumble", kick_s, lambda c: KICK if c.kind == "drop" and not c.before("drop", 1)
                        and not c.before("breakdown", 1) else None, bus="bass", gain_db=-12.0, humanize=0.0,
                        fx=[lambda x: fx.rumble(x, song.bpm, cutoff=float(rng.uniform(120, 160)), decay=2.0, drive=4.0)],
                        sidechain=1.0, sc_release_ms=60000 / song.bpm * 0.8)
        rum.automate("lp", [(drop1, 110), (drop1 + 8, 260)])
    else:  # shuffle
        riff = BOUNCE_RIFFS[int(rng.integers(len(BOUNCE_RIFFS)))]
        bp = inst.bass_pluck(cutoff=float(rng.uniform(300, 420)), env_amt=float(rng.uniform(1800, 2600)),
                             decay=float(rng.uniform(0.07, 0.1)), res=0.3, sub=0.8, drive=1.6, wave="saw",
                             sustain=0.25, grit=0.4)
        bclip = clip([(s, l, root + o, v) for s, l, o, v in riff], 2)

        def bass_notes(c):
            if not bass_ok(c):
                return []
            ev = bclip(c)
            if c.before("drop", 1) or c.before("breakdown", 1):
                ev = [e for e in ev if e[0] < 8]
            return ev

        bass = song.notes("bass", bp, bass_notes, bus="bass", gain_db=-4.0, sidechain=0.55, sc_release_ms=130.0,
                          swing=song.swing, humanize=0.04)
        bass.automate("lp", [(groove, 500), (groove + 16, 2000), (drop1 - 1, 2400), (drop1, 7000),
                             (outro.start_bar, 7000), (bass_off, 600)])
        if root >= 38:  # E2/D2 roots: add a clean sine sub an octave down so the sub band is not empty
            sr_ = eh.sub_root(key)
            song.notes("sub", inst.sub_bass(harmonics=0.05), lambda c: eh.sub_events(bass_notes(c), root, sr_),
                       bus="bass", gain_db=-5.5, sidechain=0.6, sc_release_ms=130.0, swing=song.swing, humanize=0.0)

    # ================================================================ music / hooks
    deg = key.degree
    if flavor == "talking":
        shout = inst.vocal_chop(vowel="a", vowel_to="e", shift=float(rng.uniform(1.0, 1.1)), scoop=-2.5, breath=0.12)
        song.notes("vox_shout", shout, lambda c: [(14, 1.5, deg(4, 4), 0.95)] if (c.kind == "drop" and c.i % 4 == 3)
                   or (c.kind == "groove" and c.i % 8 == 7) else [], bus="vox", gain_db=-6.0,
                   sends={"delay": 0.3, "reverb": 0.2}, sidechain=0.3)
        chords = eh.voice_progression(key, [0, 5], [4, 4], center=60, rootless=False)
        pad = song.notes("pad", inst.pad(attack=1.0, cutoff=2000.0), lambda c: [(0, 63.5, chords[(c.i // 4) % 2], 0.75)]
                         if c.kind == "breakdown" and c.i % 4 == 0 else [], gain_db=-10.0, sends={"hall": 0.3}, width=1.6)
        for s in song.sections:
            if s.kind == "breakdown":
                pad.automate("lp", [(s.start_bar, 500), (s.end_bar, 5000)])
        stab = inst.stab(wave="square", cutoff=700.0, env_amt=2500.0, decay=0.12)
        song.notes("stab", stab, lambda c: [(3, 1, chords[0], 0.8), (11, 1, chords[0], 0.6)]
                   if c.kind == "drop" and c.phrase >= 2 else [], gain_db=-10.0, sidechain=0.5,
                   sends={"delay": 0.3, "reverb": 0.12}, width=1.6)
    elif flavor == "warehouse":
        ch = eh.voice_progression(key, [0, 5, 0, 6], [4, 4, 4, 4], center=57, rootless=False)
        stab_r = [[(0, 1, 0.9), (6, 1, 0.55)], [(3, 1, 0.9), (10, 1, 0.65)], [(2, 1, 0.9)]][int(rng.integers(3))]
        dub = inst.dub_chord(cutoff=float(rng.uniform(700, 950)), env_amt=float(rng.uniform(1200, 1800)))
        song.notes("dub_stab", dub, lambda c: [(s, l, ch[(c.i // 4) % len(ch)], v) for s, l, v in stab_r]
                   if c.kind in ("drop", "breakdown") or (c.kind == "groove" and c.i >= 8) else [],
                   gain_db=-7.0, sidechain=0.5, sends={"delay": 0.38, "hall": 0.2}, width=1.6)
        dpad = song.notes("pad", inst.pad(attack=1.0, cutoff=1100.0, detune=0.25, warmth=0.7),
                          lambda c: [(0, 63.5, ch[(c.i // 4) % len(ch)], 0.75)] if c.kind == "breakdown" and c.i % 4 == 0
                          else [], gain_db=-9.0, sends={"hall": 0.35}, width=1.5)
        for s in song.sections:
            if s.kind == "breakdown":
                dpad.automate("lp", [(s.start_bar, 600), (s.end_bar, 4500)])
        dark = inst.vocal_chop(vowel="o", vowel_to="u", shift=0.85, scoop=-1.0, breath=0.1)
        song.notes("vox_dark", dark, lambda c: [(2, 2, deg(0, 4), 0.9), (6, 1, deg(2, 4), 0.7), (10, 3, deg(0, 4), 0.85)]
                   if (c.kind == "drop" and c.i % 4 == 1) or (c.kind == "breakdown" and c.i % 2 == 0) else [],
                   bus="vox", gain_db=-6.5, sends={"delay": 0.32, "hall": 0.2}, sidechain=0.35)
        seq = [(0, 0.6, deg(0, 4), 0.9), (3, 0.6, deg(0, 5), 0.7), (6, 0.6, deg(2, 4), 0.8), (10, 0.6, deg(6, 3), 0.8),
               (13, 0.6, deg(0, 4), 0.7)]
        blip = inst.seq_blip(wave="square", cutoff=float(rng.uniform(1200, 1700)), decay=0.05, res=0.5)
        sq = song.notes("blip_seq", blip, lambda c: seq if c.kind == "drop" else [], gain_db=-13.0, sidechain=0.45,
                        sends={"delay": 0.25}, pan=0.25, width=1.4)
        sq.automate("lp", [(drop1, 900), (drop1 + 16, 5000)])
        bed = fx.noise_sweep(song.grid.bar_sec * 8, up=True, q=0.7, rng=rng)
        song.hits("noise_bed", bed * 0.5, lambda c: "x..............." if c.kind in ("groove", "drop", "breakdown")
                  and c.i % 8 == 0 else None, bus="fx", gain_db=-22.0, sends={"hall": 0.2}, humanize=0.0)
    else:  # shuffle
        ch = eh.voice_progression(key, [0, 3, 0, 5], [5, 5, 5, 4], center=64)
        rhy = ORGAN_RHYTHMS[int(rng.integers(len(ORGAN_RHYTHMS)))]
        organ = eh.house_organ(decay=float(rng.uniform(0.18, 0.26)), sustain=0.25, click=0.3, perc=0.5)

        def organ_notes(c):
            if c.kind == "drop" or (c.kind == "groove" and c.i >= 16) or (c.kind == "outro" and c.i < 8):
                return [(s, l, ch[(c.i // 2) % len(ch)], v) for s, l, v in rhy]
            return []

        org = song.notes("organ", organ, organ_notes, gain_db=-10.5, sidechain=0.45, swing=song.swing, hp=220.0,
                         sends={"delay": 0.18, "reverb": 0.15}, width=1.2, fx=[eh.leslie(rate=5.5, mix=0.3)])
        org.automate("lp", [(groove + 16, 1200), (drop1 - 1, 3000), (drop1, 9000)])
        vphr = VOX_SHUFFLE[int(rng.integers(len(VOX_SHUFFLE)))]
        vox = inst.vocal_chop(vowel="e", vowel_to="a", shift=float(rng.uniform(1.1, 1.2)), scoop=-1.2)
        vclip = clip([(s, l, deg(d, 4), v) for s, l, d, v in vphr], 2)
        song.notes("vox_chop", vox, lambda c: vclip(c) if c.kind == "drop" or (c.kind == "groove" and c.i % 8 >= 4)
                   or (c.kind == "breakdown" and c.i < c.section.bars - 4 and c.i % 4 < 2) else [],
                   bus="vox", gain_db=-7.0, hp=350.0, sidechain=0.35, sends={"delay": 0.22, "reverb": 0.18},
                   swing=song.swing, fx=[lambda x: eq_peak(x, 470.0, -5.0, 0.9)])
        pad = song.notes("pad", eh.soft_pad(attack=0.8, cutoff=1800.0), lambda c: [(0, 31.5, ch[(c.i // 2) % len(ch)], 0.8)]
                         if c.kind == "breakdown" and c.i % 2 == 0 else [], gain_db=-10.0, sends={"hall": 0.3},
                         width=1.2, hp=200.0)
        for s in song.sections:
            if s.kind == "breakdown":
                pad.automate("lp", [(s.start_bar, 700), (s.end_bar, 5000)])

    # breakdown sub drone keeps weight (very low)
    song.notes("bd_sub", inst.sub_bass(), lambda c: [(0, 63.5, root, 0.6)] if c.kind == "breakdown" and c.i % 4 == 0
               and c.bars_left > 4 and flavor != "talking" else [], bus="bass", gain_db=-15.0)

    # ================================================================ fx
    eh.transitions(song, rng, crash_db=-8.5, impact_db=-9.0, riser_db=-9.0,
                   riser_kind="both" if flavor != "warehouse" else "noise")

    song.buses["drums"].eq = [("peak", 2600.0, 2.0, 0.8)] if flavor != "warehouse" else \
        [("peak", 1300.0, 1.5, 0.8), ("peak", 2800.0, 2.0, 0.8)]
    song.buses["music"].eq = [("peak", 1800.0, 1.5, 0.7)]
    song.buses["drums"].width = 1.15 if flavor != "warehouse" else 1.25
    if flavor == "warehouse":
        song.returns["hall"].decay = 4.0
    song.master.lufs = -9.0

    # ================================================================ metadata
    k = plan["key"]
    if flavor == "talking":
        song.instruments = ["tuned tech-house kick", "talking / wah formant bass", "swung 16th hats", "open hat",
                            "shaker", "clap + plate", "congas", "rim", "vowel shout", "minor stab", "breakdown pad",
                            "riser & impact"]
        song.description_he = (f"טק-האוס ב-{int(song.bpm)} BPM בסולם {k} שבו הבאס הוא הכוכב: באסליין \"מדבר\" עם "
                                f"פילטר פורמנטים שנפתח ונסגר בכל תו, בשיטת שאלה-תשובה. תופים רזים ומדויקים, "
                                f"וטיזר של הבאס בסוף הברייקדאון לפני הדרופ.")
        extra = " בסוף הברייקדאון הבאס חוזר מפולטר לשמונה תיבות — אל תערבבו שם באס של טראק אחר."
    elif flavor == "warehouse":
        song.instruments = ["driven tech-house kick", "low rumble", "rolling 16th mono bass", "toms", "16th rims",
                            "metallic perc", "clap + snap", "ride", "dub chord stab", "dark vocal chop",
                            "hypnotic blip sequence", "noise sweeps"]
        song.description_he = (f"טק-האוס אפל ומחסני ב-{int(song.bpm)} BPM בסולם {k}: קיק דוחף עם ראמבל נמוך, באס "
                                f"מתגלגל בשש-עשריות, טומים ופרקשן מתכתי, וסטאב דאבי שנבלע בדיליי. שני דרופים — "
                                f"לשעת השיא של הלילה.")
        extra = " יש שני ברייקדאונים קצרים של 8 תיבות — מקום טוב לטריקים של אקו/פילטר."
    else:
        song.instruments = ["tech-house kick", "heavy-swing 16th hats", "triplet bongos", "congas", "tambourine",
                            "bouncy octave bass", "rotary organ stabs", "vocal chops", "pad", "riser & impact"]
        song.description_he = (f"טק-האוס עם שאפל כבד ב-{int(song.bpm)} BPM בסולם {k}: היי-האטים מתנדנדים, בונגוס "
                                f"בטריולות שיוצרים תחושת 3 נגד 4, באס קופצני באוקטבות וסטאבים של אורגן עם צ'ופים "
                                f"ווקאליים. גרוב שמכין את הרחבה לשיא.")
        extra = " השאפל כבד — בזמן ביטמאצ'ינג הקשיבו להיי-האטים ולא רק לקיק."
    song.mix_tips_he = song.auto_mix_tips_he() + extra
    return song
