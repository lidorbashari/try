"""Tech House reference recipe (124–128 BPM).

Rolling, shuffled groove: punchy tuned kick, rumbly off-beat bass with filter movement, swung
16th hats + shaker, off-beat open hat, clap with plate reverb, vocal-like formant chops, chord
stabs through a dotted-8th delay, conga/bongo/blip percussion fills, 32-bar DJ intro/outro,
breakdown with pad + riser + snare roll, drop with impact and crash.

Everything that can vary is drawn from ``rng`` (pattern pools, sound-design params, arrangement
variant), so each plan entry (seed/key/BPM) gives a genuinely different track.
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from ..arrangement import Song, clip
from ..synth import white  # noqa: F401
from ..theory import Key
from . import register

# ---- pattern pools (16 steps per bar; X accent, x normal, o soft, g ghost, . rest)
KICK = "x...x...x...x..."
CLAP = ["....x.......x...", "....x.......x..g", "....x.......x.g."]
HATS_16 = ["gogxgogxgogxgogx", "g.gx.ogxg.gx.ogx", "ggoxggoxggoxgoox"]
OPEN_HAT = "..x...x...x...x."
SHAKER = ["gxgogxgogxgogxgo", "oxgxoxgxoxgxoxgx", ".xgo.xgo.xgo.xgo"]
PERC_POOL = [
    "...x......x..x..", "..x....x..x.....", "......x...x..x.x", "...x..x.......x.", ".x.....x...x..x.",
]
FILL_PERC = ["......x.x.xxx.xx", "........x.x.x.xx", "..........xxxxxx"]

# bass riffs: (step, length_steps, semitone offset from root, velocity); 2 bars = 32 steps
BASS_RIFFS = [
    [(2, 1.5, 0, 1.0), (3, 1, 0, 0.7), (6, 1.5, 0, 0.95), (10, 1.5, 0, 1.0), (11, 1, 12, 0.6), (14, 1.5, 0, 0.9),
     (18, 1.5, 0, 1.0), (19, 1, 0, 0.7), (22, 1.5, 0, 0.95), (26, 1.5, 3, 1.0), (27, 1, 0, 0.6), (30, 1.5, -2, 0.9)],
    [(2, 2, 0, 1.0), (6, 1, 0, 0.8), (7, 1, 12, 0.6), (10, 2, 0, 1.0), (14, 1, 7, 0.7), (15, 1, 0, 0.6),
     (18, 2, 0, 1.0), (22, 1, 0, 0.8), (23, 1, 12, 0.6), (26, 2, 0, 1.0), (29, 1, -2, 0.8), (30, 1, -5, 0.7)],
    [(2, 1, 0, 1.0), (3, 1, 0, 0.6), (5, 1, 0, 0.7), (6, 1.5, 0, 0.9), (10, 1, 0, 1.0), (11, 1, 0, 0.6),
     (13, 1, 12, 0.7), (14, 1.5, 0, 0.9), (18, 1, 0, 1.0), (19, 1, 0, 0.6), (21, 1, 0, 0.7), (22, 1.5, 3, 0.9),
     (26, 1, 0, 1.0), (27, 1, 0, 0.6), (29, 1, -2, 0.7), (30, 1.5, 0, 0.9)],
]

# vocal chop phrases (2 bars): (step, length, scale-degree, vel, vowel pair)
VOX_PHRASES = [
    [(3, 1.5, 4, 0.9), (6, 1, 4, 0.7), (10, 2, 2, 0.9), (19, 1.5, 4, 0.9), (22, 1, 5, 0.7), (26, 3, 4, 0.9)],
    [(0, 1, 7, 0.8), (3, 1, 7, 0.9), (6, 2, 6, 0.9), (14, 1, 4, 0.7), (16, 1, 7, 0.8), (19, 1, 7, 0.9), (22, 4, 9, 0.9)],
    [(2, 1, 4, 0.9), (4, 1, 4, 0.6), (7, 2, 2, 0.9), (11, 1, 0, 0.8), (18, 1, 4, 0.9), (20, 1, 4, 0.6), (23, 3, 5, 0.9)],
]
STAB_RHYTHMS = [
    [(3, 1, 0.9), (6, 1, 0.7), (11, 1.5, 0.9)],
    [(2, 1, 0.9), (10, 1, 0.9), (13, 1, 0.6)],
    [(0, 1, 0.9), (3, 1, 0.7), (7, 1, 0.8), (14, 1, 0.6)],
]

TEMPLATES = [
    [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 24, 6, 2), ("Breakdown", "breakdown", 16, 3, 0),
     ("Drop", "drop", 32, 8, 3), ("Outro", "outro", 32, 4, 0)],
    [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 16, 6, 2), ("Breakdown", "breakdown", 8, 3, 0),
     ("Drop", "drop", 24, 8, 3), ("Breakdown 2", "breakdown", 8, 4, 0), ("Drop 2", "drop", 16, 8, 1),
     ("Outro", "outro", 32, 4, 0)],
]


@register("tech_house")
def build(plan: dict, rng: np.random.Generator) -> Song:
    song = Song(plan, rng, swing=float(rng.choice([54.0, 56.0, 57.0, 58.0])))
    key: Key = song.key
    total = song.target_bars()
    tpl = TEMPLATES[1] if total >= 136 and rng.random() < 0.45 else TEMPLATES[0]
    song.arrange(tpl, total)
    groove_bar = song.bar("groove")
    song.mix_in_bar = groove_bar
    outro = song.find("outro")
    bass_off_bar = outro.start_bar + outro.bars - 16  # last 16 bars: drums only

    root = key.root(1)  # e.g. A1 = 33
    while root < 31:
        root += 12
    root_hz = 440 * 2 ** ((root - 69) / 12)

    # ---------------------------------------------------------------- drums
    kick_s = drums.kick("tech_house", tune_hz=float(np.clip(root_hz, 46, 58)),
                        decay=float(rng.uniform(0.26, 0.34)), click=float(rng.uniform(0.45, 0.65)), rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown":
            return None
        if c.before("drop", 1) or c.before("breakdown", 1) and c.rng.random() < 0.5:
            return "x...x...x......." if c.before("breakdown", 1) else None
        return KICK

    song.hits("kick", kick_s, kick_pat, bus="drums", gain_db=0.0, sc_source=True, humanize=0.0)

    clap_s = drums.variants(drums.clap, 3, rng, jitter={"tone_hz": 0.05}, tone_hz=float(rng.uniform(1100, 1400)),
                            tail=float(rng.uniform(0.14, 0.2)))
    clap_p = CLAP[int(rng.integers(len(CLAP)))]

    def clap_pat(c):
        if c.kind == "breakdown":
            return "....x.......x..." if c.bars_left <= 4 and c.section.bars > 8 else None
        if c.kind == "intro" and c.i < 8:
            return None
        return clap_p if not c.phrase_end else "....x.......x.xx"

    song.hits("clap", clap_s, clap_pat, gain_db=-5.5, sends={"reverb": 0.22, "room": 0.15}, timing_ms=1.5)

    hats_c = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.15}, decay=float(rng.uniform(0.03, 0.05)),
                            tone=float(rng.uniform(0.9, 1.15)))
    hat_p = HATS_16[int(rng.integers(len(HATS_16)))]

    def hat_pat(c):
        if c.kind == "breakdown" and c.bars_left > 4:
            return None
        if c.kind == "intro" and c.i < 4:
            return None
        return hat_p

    song.hits("hats", hats_c, hat_pat, gain_db=-14.0, pan=0.12, humanize=0.12)

    ohat = drums.hat(open_=True, decay=float(rng.uniform(0.16, 0.24)), tone=float(rng.uniform(0.95, 1.1)), rng=rng)
    song.hits("open_hat", ohat, lambda c: OPEN_HAT if (c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 16)
                                                         or (c.kind == "outro" and c.bars_left > 8)) else None,
              gain_db=-11.0, pan=-0.08, sends={"room": 0.1})

    shk = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=float(rng.uniform(0.07, 0.1)))
    sh_p = SHAKER[int(rng.integers(len(SHAKER)))]
    song.hits("shaker", shk, lambda c: sh_p if not (c.kind == "breakdown") and not (c.kind == "intro" and c.i < 8) else None,
              gain_db=-17.0, pan=-0.35, humanize=0.15, timing_ms=2.0)

    # percussion: conga/bongo/rim/blip
    perc_kit = [drums.conga(float(rng.uniform(190, 240)), "open", rng=rng),
                drums.conga(float(rng.uniform(280, 330)), "slap", rng=rng),
                drums.bongo(float(rng.uniform(450, 560)), "open", rng=rng),
                drums.perc_blip(float(rng.uniform(700, 1100)), 0.04, rng=rng)]
    p1 = PERC_POOL[int(rng.integers(len(PERC_POOL)))]
    p2 = PERC_POOL[int(rng.integers(len(PERC_POOL)))]
    fill = FILL_PERC[int(rng.integers(len(FILL_PERC)))]

    def perc_a(c):
        if c.kind == "intro" and c.i < 16:
            return None
        if c.phrase_end and c.kind != "breakdown":
            return fill
        return p1 if c.kind != "breakdown" else None

    song.hits("perc_conga", [perc_kit[0], perc_kit[1]], perc_a, gain_db=-12.0, pan=-0.45,
              sends={"room": 0.2, "delay": 0.06})
    song.hits("perc_bongo", [perc_kit[2], perc_kit[3]],
              lambda c: p2 if c.kind in ("groove", "drop") and c.phrase < 4 else None,
              gain_db=-15.0, pan=0.5, sends={"delay": 0.12, "room": 0.15})

    rim = drums.rimshot(float(rng.uniform(1500, 1900)), rng=rng)
    song.hits("rim", rim, lambda c: "..x..x....x..x.." if c.kind == "drop" and c.i % 4 >= 2 else None,
              gain_db=-17.0, pan=0.3, sends={"delay8": 0.15})

    ride = drums.ride(decay=1.1, rng=rng)
    song.hits("ride", ride, lambda c: "x...x...x...x..." if c.kind == "drop" else None, gain_db=-21.0, pan=0.2)

    # snare roll into the drop (last 4 bars of each breakdown)
    snr = drums.snare(tone_hz=float(rng.uniform(180, 220)), snappy=0.8, decay=0.12, rng=rng)

    def roll(c):
        if c.kind != "breakdown" or c.bars_left > 4:
            return None
        return ["x...x...x...x...", "x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx", "xxxxxxxxxxxxxxxx"][4 - c.bars_left]

    song.hits("snare_roll", snr, roll, gain_db=-14.0, sends={"reverb": 0.25}, vel_curve=1.0) \
        .automate("gain_db", _ramp_into(song, "drop", 4, -12.0, 0.0))

    # ---------------------------------------------------------------- bass
    riff = BASS_RIFFS[int(rng.integers(len(BASS_RIFFS)))]
    bass_inst = inst.bass_pluck(cutoff=float(rng.uniform(260, 380)), env_amt=float(rng.uniform(1500, 2600)),
                                decay=float(rng.uniform(0.08, 0.14)), res=float(rng.uniform(0.25, 0.45)),
                                sub=0.75, drive=float(rng.uniform(1.4, 2.2)),
                                wave=str(rng.choice(["saw", "square"])))
    bass_ev = [(s, l, root + o, v) for s, l, o, v in riff]
    bass_clip = clip(bass_ev, 2)

    def bass_notes(c):
        if c.kind in ("intro", "breakdown") or c.bar >= bass_off_bar:
            return []
        ev = bass_clip(c)
        if c.before("drop", 1) or c.before("breakdown", 1):
            ev = [e for e in ev if e[0] < 8]  # cut the bass for half a bar before transitions
        return ev

    bass = song.notes("bass", bass_inst, bass_notes, bus="bass", gain_db=-2.0, sidechain=0.55,
                      sc_release_ms=150.0, swing=song.swing, humanize=0.04)
    g0, d0 = groove_bar, song.bar("drop")
    bass.automate("lp", [(g0, 350), (g0 + 8, 900), (d0 - 1, 1600), (d0, 5000), (outro.start_bar, 5000),
                         (bass_off_bar, 500)])

    # ---------------------------------------------------------------- music
    deg = key.degree
    # vocal chops (formant) in the upper-middle register
    vphr = VOX_PHRASES[int(rng.integers(len(VOX_PHRASES)))]
    vowels = [("a", "e"), ("o", "a"), ("e", "i"), ("a", "o")]
    va, vb = vowels[int(rng.integers(len(vowels)))]
    vox_inst = inst.vocal_chop(vowel=va, vowel_to=vb, shift=float(rng.uniform(1.05, 1.2)),
                               scoop=float(rng.uniform(-1.5, -0.5)))
    vox_ev = [(s, l, deg(d, 4), v) for s, l, d, v in vphr]
    vclip = clip(vox_ev, 2)

    def vox_notes(c):
        if c.kind == "groove":
            return vclip(c) if (c.i // 4) % 2 == 1 else []
        if c.kind == "drop":
            return vclip(c)
        if c.kind == "breakdown":
            return vclip(c) if c.i < c.section.bars - 4 and c.i % 4 < 2 else []
        if c.kind == "outro" and c.i < 8:
            return vclip(c) if c.i % 4 < 2 else []
        return []

    song.notes("vox_chop", vox_inst, vox_notes, bus="vox", gain_db=-9.0, sidechain=0.35,
               sends={"delay": 0.22, "reverb": 0.18}, pan=0.0)

    # chord stabs (minor 7th voicings, voice-led)
    prog_degs = [[0, 0, 5, 6], [0, 3, 0, 4], [0, 5, 3, 4], [0, 0, 3, 3]][int(rng.integers(4))]
    from ..theory import voice_lead
    chords, prev = [], None
    for dg in prog_degs:
        ch = voice_lead(prev, key.chord(dg, 3, 4), center=key.root(4) - 2)
        chords.append(ch)
        prev = ch
    stab_r = STAB_RHYTHMS[int(rng.integers(len(STAB_RHYTHMS)))]
    stab_inst = inst.stab(wave=str(rng.choice(["saw", "square"])), cutoff=float(rng.uniform(600, 1000)),
                          env_amt=float(rng.uniform(2500, 4500)), decay=float(rng.uniform(0.1, 0.2)))

    def stab_notes(c):
        if c.kind == "drop" or (c.kind == "groove" and c.i >= c.section.bars - 8):
            ch = chords[(c.i // 2) % len(chords)]
            return [(s, l, ch, v) for s, l, v in stab_r]
        return []

    song.notes("stabs", stab_inst, stab_notes, gain_db=-11.0, sidechain=0.5,
               sends={"delay": 0.25, "reverb": 0.15}, width=1.3)

    # breakdown pad
    pad_inst = inst.pad(attack=float(rng.uniform(0.6, 1.2)), cutoff=float(rng.uniform(1400, 2400)))

    def pad_notes(c):
        if c.kind == "breakdown" and c.i % 2 == 0:
            ch = chords[(c.i // 2) % len(chords)]
            return [(0, 31.5, ch, 0.8)]
        return []

    pad = song.notes("pad", pad_inst, pad_notes, gain_db=-11.0, sends={"hall": 0.3}, width=1.4)
    for bd in [s for s in song.sections if s.kind == "breakdown"]:
        pad.automate("lp", [(bd.start_bar, 600), (bd.end_bar, 6000)])

    # sub drone in breakdown keeps weight (root note, very low level)
    song.notes("bd_sub", inst.sub_bass(), lambda c: [(0, 63.5, root, 0.6)] if c.kind == "breakdown" and c.i % 4 == 0
               and c.bars_left > 4 else [], bus="bass", gain_db=-14.0)

    # ---------------------------------------------------------------- fx
    fxl = song.audio("fx", bus="fx")
    crash = drums.crash(decay=float(rng.uniform(1.8, 2.6)), rng=rng)
    for s in song.sections:
        if s.kind in ("groove", "drop", "outro"):
            fxl.add(crash, s.start_bar, gain_db=-8.0)
        if s.kind == "drop":
            for b in range(s.start_bar + 16, s.end_bar, 16):
                fxl.add(crash, b, gain_db=-12.0)
            fxl.add(fx.impact(2.5, rng=rng), s.start_bar, gain_db=-9.0)
    for s in song.sections:
        if s.kind == "breakdown":
            nb = min(8, s.bars)
            fxl.add(fx.riser(song.grid.bar_sec * nb, "both" if rng.random() < 0.6 else "noise", rng=rng),
                    s.end_bar, align="end", gain_db=-9.0)
            fxl.add(fx.downlifter(song.grid.bar_sec * 2, rng=rng), s.start_bar, gain_db=-12.0)
    fxl.add(fx.reverse_cymbal(song.grid.bar_sec, rng=rng), groove_bar, align="end", gain_db=-10.0)
    fxl.sends = {"hall": 0.12}

    song.master.lufs = -9.0
    song.instruments = ["punchy tuned tech-house kick", "rolling off-beat bass", "swung 16th hats", "open hat",
                        "shaker", "clap + plate reverb", "congas & bongos", "formant vocal chops",
                        "minor-7th chord stabs", "breakdown pad", "riser & impact"]
    song.description_he = (f"טק-האוס מתגלגל ב-{int(song.bpm)} BPM בסולם {plan['key']}: קיק חזק ומכוון, באס אופביט "
                           f"מגרגר עם פילטר שנפתח, היי-האטים בשאפל, קלאפ עם ריוורב וצ'ופים ווקאליים סינתטיים. "
                           f"בנוי לרגעי השיא של הערב.")
    tips = song.auto_mix_tips_he()
    song.mix_tips_he = tips + " הקיק נעלם לתיבה אחת לפני הדרופ — רגע מצוין לחתוך את הבאס בטראק השני."
    return song


def _ramp_into(song, kind, bars, lo, hi):
    pts = []
    for s in song.sections:
        if s.kind == kind:
            pts += [(s.start_bar - bars, lo), (s.start_bar, hi)]
    return pts or [(0, 0.0)]
