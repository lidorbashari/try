"""Peak-time Techno reference recipe (128–135 BPM).

Driving tuned kick + sidechained reverb rumble, hypnotic 16th sequence, acid line (TB-style
MonoSynth with slides/accents and a cutoff that climbs through the track), dub chord stabs into a
dotted-8th delay, closed/open hats, ride, clap/snare, industrial metal hits, noise sweeps, tension
risers and big drops (kick drop-out → impact + crash).
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from ..arrangement import Song, clip, euclid
from ..theory import voice_lead
from . import register

HATS = ["x.x.x.x.x.x.x.x.", "gxgxgxgxgxgxgxgx", "xgxgxgxgxgxgxgxg", "x.xxx.xxx.xxx.xx"]
HAT_VEL = ["oxooXxooXxooxoXo", "gogxgogxgogxgogx", "ooXoooXoooXoooXo"]
OPEN_HAT = "..x...x...x...x."
RIDE = ["x.x.x.x.x.x.x.x.", "..x...x...x...x.", "x.xxx.xxx.xxx.xx"]
CLAP = ["....x.......x...", "....x.......x...", "....x..g....x..."]
METAL = ["...x.......x....", ".......x......x.", "...x......x....."]
TEMPLATES = [
    [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 32, 6, 2), ("Breakdown", "breakdown", 16, 4, 0),
     ("Drop", "drop", 32, 9, 3), ("Outro", "outro", 32, 5, 0)],
    [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 24, 6, 2), ("Breakdown", "breakdown", 8, 4, 0),
     ("Drop", "drop", 24, 9, 3), ("Breakdown 2", "breakdown", 8, 5, 0), ("Drop 2", "drop", 16, 9, 1),
     ("Outro", "outro", 32, 5, 0)],
]


def acid_pattern(rng, key, root, steps=32):
    """Random but musical 2-bar acid sequence: (step, len, midi, vel, flags)."""
    pool = [0, 0, 0, 12, 3, 7, 10, -2, 5, 15]
    ev = []
    density = rng.uniform(0.55, 0.8)
    for s in range(steps):
        if s % 4 == 0 or rng.random() < density:
            o = int(rng.choice(pool))
            fl = ""
            if rng.random() < 0.22:
                fl += "s"
            if rng.random() < 0.28 or s % 8 == 0:
                fl += "a"
            ev.append((s, 0.6 if "s" not in fl else 1.0, root + o, 0.9, fl))
    return ev


def seq_pattern(rng, key, steps=16):
    degs = rng.choice([0, 0, 2, 4, 7, 6, 3], size=steps)
    octs = rng.choice([0, 0, 0, 1], size=steps)
    rhythm = euclid(int(rng.integers(9, 14)), 16, int(rng.integers(0, 4)))
    out = []
    for s, ch in enumerate(rhythm):
        if ch != ".":
            out.append((s, 0.7, key.degree(int(degs[s]), 4 + int(octs[s])), 0.75 + 0.25 * (s % 4 == 2)))
    return out


@register("techno")
def build(plan: dict, rng: np.random.Generator) -> Song:
    song = Song(plan, rng, swing=float(rng.choice([50.0, 50.0, 52.0])))
    key = song.key
    total = song.target_bars()
    tpl = TEMPLATES[1] if rng.random() < 0.4 else TEMPLATES[0]
    song.arrange(tpl, total)
    groove = song.bar("groove")
    song.mix_in_bar = groove
    outro = song.find("outro")
    bass_off = outro.start_bar + outro.bars - 16
    root = key.root(1)
    while root < 31:
        root += 12
    root_hz = 440 * 2 ** ((root - 69) / 12)

    # ---------------------------------------------------------------- drums
    kick_s = drums.kick("techno", tune_hz=float(np.clip(root_hz, 44, 56)), decay=float(rng.uniform(0.34, 0.44)),
                        drive=float(rng.uniform(2.0, 3.2)), rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown":
            return "xxxxxxxxxxxxxxxx" if c.bars_left == 1 and c.rng.random() < 0.5 else None
        if c.before("drop", 1):
            return "x...x...x...x.x." if c.rng.random() < 0.3 else None
        return "x...x...x...x..."

    song.hits("kick", kick_s, kick_pat, gain_db=-3.5, sc_source=True, humanize=0.0)

    # rumble = kick → dark reverb → LP → drive, heavily sidechained (classic techno low end)
    def rumble_pat(c):
        if c.kind in ("intro", "breakdown") or c.bar >= bass_off or c.before("drop", 1):
            return None
        return "x...x...x...x..."

    rum = song.hits("rumble", kick_s, rumble_pat, bus="bass", gain_db=-6.5, humanize=0.0,
                    fx=[lambda x: fx.rumble(x, song.bpm, cutoff=float(rng.uniform(130, 190)),
                                            decay=float(rng.uniform(1.8, 2.8)), drive=float(rng.uniform(3, 6)))],
                    sidechain=1.0, sc_release_ms=60000 / song.bpm * 0.85)
    rum.automate("lp", [(groove, 120), (groove + 16, 400), (outro.start_bar, 400), (bass_off, 150)])

    hat_p, hat_v = HATS[int(rng.integers(len(HATS)))], HAT_VEL[int(rng.integers(len(HAT_VEL)))]
    hat_pattern = "".join(v if h != "." else "." for h, v in zip(hat_p, hat_v))
    hats = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.2}, decay=float(rng.uniform(0.03, 0.06)),
                          tone=float(rng.uniform(1.0, 1.3)))
    song.hits("hats", hats, lambda c: hat_pattern if not (c.kind == "breakdown" and c.bars_left > 2) else None,
              gain_db=-12.5, pan=0.35, humanize=0.1)
    ohat = drums.hat(open_=True, decay=float(rng.uniform(0.2, 0.3)), tone=float(rng.uniform(1.0, 1.2)), rng=rng)
    song.hits("open_hat", ohat, lambda c: OPEN_HAT if (c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 8)
                                                         or (c.kind == "outro" and c.bars_left > 8)) else None,
              gain_db=-11.0, pan=-0.3, sends={"room": 0.12})
    ride_p = RIDE[int(rng.integers(len(RIDE)))]
    ride = drums.ride(decay=float(rng.uniform(1.0, 1.6)), rng=rng)
    song.hits("ride", ride, lambda c: ride_p if c.kind == "drop" or (c.kind == "groove" and c.i >= 16) else None,
              gain_db=-14.0, pan=0.4, sends={"room": 0.12})
    clap = drums.variants(drums.clap, 3, rng, jitter={"tone_hz": 0.05}, tone_hz=float(rng.uniform(1000, 1300)),
                          tail=float(rng.uniform(0.16, 0.25)))
    clap_p = CLAP[int(rng.integers(len(CLAP)))]
    song.hits("clap", clap, lambda c: clap_p if c.kind in ("groove", "drop", "outro") or (c.kind == "intro" and c.i >= 16)
              else None, gain_db=-4.0, sends={"reverb": 0.35, "hall": 0.12})
    snr = drums.snare(tone_hz=float(rng.uniform(170, 210)), snappy=0.75, decay=0.16, rng=rng)

    def snare_pat(c):
        if c.kind == "drop":
            return "....x.......x..." if not c.phrase_end else "....x.......x.xx"
        if c.kind == "breakdown" and c.bars_left <= 4:
            return ["x...x...x...x...", "x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx", "rrrrrrrrrrrrrrrr"][4 - c.bars_left]
        return None

    song.hits("snare", snr, snare_pat, gain_db=-8.0, sends={"reverb": 0.2})

    metal = [drums.metal_hit(float(rng.uniform(250, 420)), 0.3, rng=rng), drums.metal_hit(float(rng.uniform(500, 700)), 0.2, rng=rng)]
    metal_p = METAL[int(rng.integers(len(METAL)))]
    song.hits("metal", metal, lambda c: metal_p if c.kind in ("groove", "drop") and c.i % 2 == 1 else None,
              gain_db=-11.0, pan=-0.5, sends={"hall": 0.25, "delay": 0.15},
              fx=[lambda x: fx.bitcrush(x, 10, 2)])
    perc = drums.perc_blip(float(rng.uniform(500, 900)), 0.06, fm_index=2.5, ratio=1.41, rng=rng)
    perc_p = euclid(int(rng.integers(3, 6)), 16, int(rng.integers(1, 5)))
    song.hits("perc", perc, lambda c: perc_p if c.kind != "breakdown" and not (c.kind == "intro" and c.i < 8) else None,
              gain_db=-13.0, pan=0.55, sends={"delay8": 0.2})
    tom = drums.tom(float(rng.uniform(90, 130)), 0.4, rng=rng)
    song.hits("tom_fill", tom, lambda c: "..........x.x.xx" if c.phrase_end and c.i % 16 == 15 and c.kind != "breakdown"
              else None, gain_db=-13.0, sends={"reverb": 0.2})

    # ---------------------------------------------------------------- tonal
    seq = seq_pattern(rng, key)
    seq_inst = inst.seq_blip(wave=str(rng.choice(["square", "saw"])), cutoff=float(rng.uniform(900, 1600)),
                             decay=float(rng.uniform(0.04, 0.08)), res=float(rng.uniform(0.4, 0.6)))
    seq_l = song.notes("sequence", seq_inst,
                       lambda c: seq if (c.kind in ("groove", "drop", "breakdown") or (c.kind == "outro" and c.i < 8)) else [],
                       gain_db=-7.0, sidechain=0.45, sends={"delay": 0.22, "hall": 0.08}, pan=0.2, width=1.4)
    seq_l.automate("lp", [(groove, 700), (groove + 24, 3500), (song.bar("drop"), 2500),
                          (song.bar("drop") + 16, 9000), (outro.start_bar + 8, 1200)])

    acid_ev = acid_pattern(rng, key, root + 24)
    synth = inst.MonoSynth(wave=str(rng.choice(["saw", "square"])), cutoff=300.0, res=float(rng.uniform(0.72, 0.86)),
                           env_mod=float(rng.uniform(2.0, 3.0)), decay=float(rng.uniform(0.12, 0.22)),
                           glide_ms=60.0, drive=2.5, dist=0.35)
    acid_clip = clip(acid_ev, 2)

    def acid_notes(c):
        if c.kind == "drop" or (c.kind == "breakdown" and c.i >= 4) or (c.kind == "groove" and c.i >= c.section.bars - 8):
            return acid_clip(c)
        return []

    acid = song.line("acid", synth, acid_notes, bus="music", gain_db=-5.0, sidechain=0.4,
                     sends={"delay": 0.2, "reverb": 0.08})
    d1 = song.bar("drop")
    pts = []
    for s in song.sections:
        if s.kind == "groove":
            pts += [(s.start_bar, 300), (s.end_bar, 700)]
        elif s.kind == "breakdown":
            pts += [(s.start_bar, 400), (s.end_bar - 0.01, 2500)]
        elif s.kind == "drop":
            pts += [(s.start_bar, 800), (s.start_bar + s.bars * 0.75, 3500), (s.end_bar, 1200)]
    acid.automate("cutoff", pts)

    # dub chord stabs
    chords, prev = [], None
    for dg in [[0, 0, 5, 3], [0, 6, 5, 6], [0, 0, 3, 4]][int(rng.integers(3))]:
        ch = voice_lead(prev, key.chord(dg, 3, 4), center=key.root(3) + 7)
        chords.append(ch)
        prev = ch
    stab_r = [[(0, 1, 0.9), (6, 1, 0.6)], [(3, 1, 0.9), (10, 1, 0.7)], [(2, 1, 0.9)]][int(rng.integers(3))]
    dub = inst.dub_chord(cutoff=float(rng.uniform(500, 800)), env_amt=float(rng.uniform(900, 1600)))
    song.notes("dub_stab", dub,
               lambda c: [(s, l, chords[(c.i // 4) % len(chords)], v) for s, l, v in stab_r]
               if c.kind in ("breakdown", "drop") else [],
               gain_db=-8.0, sidechain=0.5, sends={"delay": 0.35, "hall": 0.25}, width=1.7)

    # dark pad in breakdowns
    pad_inst = inst.pad(attack=1.2, cutoff=900.0, detune=0.25, warmth=0.7)
    pad = song.notes("pad", pad_inst, lambda c: [(0, 63.5, chords[(c.i // 4) % len(chords)], 0.7)]
                     if c.kind == "breakdown" and c.i % 4 == 0 else [], gain_db=-12.0, sends={"hall": 0.35}, width=1.6)
    for s in song.sections:
        if s.kind == "breakdown":
            pad.automate("lp", [(s.start_bar, 500), (s.end_bar, 4000)])

    # ---------------------------------------------------------------- fx / transitions
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.15})
    crash = drums.crash(decay=2.4, rng=rng)
    for s in song.sections:
        if s.kind in ("groove", "drop", "outro"):
            fxl.add(crash, s.start_bar, gain_db=-9.0)
        if s.kind == "drop":
            fxl.add(fx.impact(3.0, rng=rng), s.start_bar, gain_db=-7.0)
            for b in range(s.start_bar + 16, s.end_bar, 16):
                fxl.add(crash, b, gain_db=-13.0)
                fxl.add(fx.noise_sweep(song.grid.bar_sec * 4, up=True, rng=rng), b, align="end", gain_db=-18.0)
        if s.kind == "breakdown":
            nb = min(8, s.bars)
            fxl.add(fx.riser(song.grid.bar_sec * nb, "both", f_lo=200, f_hi=10000, rng=rng), s.end_bar,
                    align="end", gain_db=-8.0)
            fxl.add(fx.downlifter(song.grid.bar_sec * 2, rng=rng), s.start_bar, gain_db=-11.0)
            fxl.add(fx.reverse_cymbal(song.grid.bar_sec, rng=rng), s.end_bar, align="end", gain_db=-11.0)
    fxl.add(fx.noise_sweep(song.grid.bar_sec * 8, up=True, rng=rng), groove, align="end", gain_db=-16.0)

    song.buses["drums"].eq = [("peak", 3000.0, 1.5, 0.8)]
    song.buses["drums"].width = 1.3
    song.buses["music"].width = 1.3
    song.returns["reverb"].width = 1.4
    song.master.lufs = -9.0
    song.instruments = ["driving techno kick", "sidechained reverb rumble", "hypnotic 16th sequence", "acid line",
                        "dub chord stabs", "closed & open hats", "ride", "clap & snare", "industrial metal hits",
                        "risers & noise sweeps"]
    song.description_he = (f"טכנו פיק-טיים ב-{int(song.bpm)} BPM בסולם {plan['key']}: קיק דוחף עם ראמבל עמוק, "
                           f"סיקוונס היפנוטי, קו אסיד שנפתח לאורך הטראק וסטאבים דאביים עם דיליי. אנרגיה גבוהה לאמצע-סוף הסט.")
    song.mix_tips_he = song.auto_mix_tips_he() + " הראמבל יושב על הסאב — בזמן מעבר הורידו את ה-Low בטראק היוצא."
    return song
