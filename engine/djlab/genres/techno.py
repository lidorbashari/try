"""Peak-time / Driving Techno reference recipe (128–135 BPM).

Driving tuned kick + sidechained reverb rumble, closed/open hats, ride, clap/snare into a plate,
industrial metal hits, noise sweeps, accelerating pitched snare rolls, risers and big drops (kick
drop-out → impact + crash). Tops, claps and percussion are decorrelated stereo one-shots
(:mod:`djlab.ext_techno`) so the mix has real width while kick, rumble and bass stay mono.

Each plan id gets a *flavor* that changes the sound design and the lead element:

* ``classic``    – hypnotic 16th sequence, acid line in the drops, dub chord stabs (techno-01)
* ``industrial`` – distorted kick and rumble, clangs, machine noise, growl stabs, dark drone (techno-02)
* ``acid``       – a 303-style acid line is the protagonist from the groove on + strobe stabs (techno-03)
* ``rolling``    – rolling 16th bassline, polymetric sequence, dub stabs, long drop (techno-04)

Unknown ids draw a flavor from ``rng``.
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from ..dsp import eq_lowshelf, normalize
from .. import ext_techno as xt
from ..arrangement import Song, clip, euclid
from ..theory import voice_lead
from . import register

HATS = ["x.x.x.x.x.x.x.x.", "gxgxgxgxgxgxgxgx", "xgxgxgxgxgxgxgxg", "x.xxx.xxx.xxx.xx"]
HAT_VEL = ["oxooXxooXxooxoXo", "gogxgogxgogxgogx", "ooXoooXoooXoooXo"]
OPEN_HAT = "..x...x...x...x."
RIDE = ["x.x.x.x.x.x.x.x.", "..x...x...x...x.", "x.xxx.xxx.xxx.xx"]
CLAP = ["....x.......x...", "....x.......x...", "....x..g....x..."]
METAL = ["...x.......x....", ".......x......x.", "...x......x....."]
TEMPLATES = {
    "long_break": [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 32, 6, 2), ("Breakdown", "breakdown", 16, 4, 0),
                   ("Drop", "drop", 32, 9, 3), ("Outro", "outro", 32, 5, 0)],
    "two_drops": [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 24, 6, 2), ("Breakdown", "breakdown", 8, 4, 0),
                  ("Drop", "drop", 24, 9, 3), ("Breakdown 2", "breakdown", 8, 5, 0), ("Drop 2", "drop", 16, 9, 1),
                  ("Outro", "outro", 32, 5, 0)],
    "rolling": [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 40, 7, 2), ("Breakdown", "breakdown", 8, 5, 0),
                ("Drop", "drop", 32, 9, 3), ("Outro", "outro", 32, 5, 0)],
}
FLAVORS = {
    "techno-01": "classic",
    "techno-02": "industrial",
    "techno-03": "acid",
    "techno-04": "rolling",
}
FLAVOR_TEMPLATE = {"classic": "two_drops", "industrial": "long_break", "acid": "two_drops", "rolling": "rolling"}


def acid_pattern(rng, key, root, steps=32, density=None):
    """Random but musical 2-bar acid sequence: (step, len, midi, vel, flags)."""
    pool = [0, 0, 0, 12, 3, 7, 10, -2, 5, 15]
    ev = []
    density = density if density is not None else rng.uniform(0.55, 0.8)
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
    flavor = FLAVORS.get(plan["id"]) or xt.pick(rng, ["classic", "industrial", "acid", "rolling"])
    song = Song(plan, rng, swing=float(rng.choice([50.0, 50.0, 52.0])))
    key = song.key
    song.arrange(TEMPLATES[FLAVOR_TEMPLATE[flavor]], song.target_bars())
    groove = song.bar("groove")
    song.mix_in_bar = groove
    outro = song.find("outro")
    bass_off = outro.start_bar + outro.bars - 16
    d1 = song.bar("drop")
    root = key.root(1)
    while root < 31:
        root += 12
    kick_hz = xt.kick_tune(key, 43.0, 57.0)
    ind, acid_fl, rolling = flavor == "industrial", flavor == "acid", flavor == "rolling"
    xt.setup_space(song, hall_decay=3.6 if ind else None)
    bar = song.grid.bar_sec

    # ---------------------------------------------------------------- kick + rumble
    kick_s = drums.kick("techno", tune_hz=kick_hz, decay=float(rng.uniform(0.34, 0.42)) if not rolling else 0.3,
                        click=0.7 if ind else 0.6, drive=float(rng.uniform(3.8, 4.6)) if ind else float(rng.uniform(2.0, 3.0)),
                        rng=rng)
    if ind:  # extra drive on the body, transient kept → hard, distorted but still punchy; sub tamed
        kick_s = normalize(eq_lowshelf(xt.distorted(kick_s, 2.2, 9000.0), 70.0, -3.5, 0.7))

    def kick_pat(c):
        if c.kind == "breakdown":
            return "x...x...x...x..." if (ind and c.bars_left <= 4 and c.bars_left > 1) else None
        if c.before("drop", 1):
            return "x...x...x...x.x." if c.rng.random() < 0.3 else None
        return "x...x...x...x..."

    song.hits("kick", kick_s, kick_pat, gain_db=-3.5, sc_source=True, humanize=0.0)

    # rumble = kick → dark reverb → LP → drive, heavily sidechained (classic techno low end)
    def rumble_pat(c):
        if c.kind in ("intro", "breakdown") or c.bar >= bass_off or c.before("drop", 1):
            return None
        return "x...x...x...x..."

    r_cut = {"industrial": 210.0, "rolling": 120.0}.get(flavor, float(rng.uniform(130, 190)))
    r_drive = {"industrial": 8.0}.get(flavor, float(rng.uniform(3, 6)))
    rum = song.hits("rumble", kick_s, rumble_pat, bus="bass", humanize=0.0,
                    gain_db={"industrial": -8.5, "rolling": -10.0}.get(flavor, -6.5), hp=40.0 if ind else None,
                    fx=[lambda x: fx.rumble(x, song.bpm, cutoff=r_cut, decay=float(rng.uniform(1.8, 2.8)), drive=r_drive)],
                    sidechain=1.0, sc_release_ms=60000 / song.bpm * 0.85)
    rum.automate("lp", [(groove, 120), (groove + 16, 400), (outro.start_bar, 400), (bass_off, 150)])

    # ---------------------------------------------------------------- tops
    hat_p, hat_v = HATS[int(rng.integers(len(HATS)))], HAT_VEL[int(rng.integers(len(HAT_VEL)))]
    if rolling:
        hat_p = "xxxxxxxxxxxxxxxx"
    hat_pattern = "".join(v if h != "." else "." for h, v in zip(hat_p, hat_v))
    hats = xt.stereo_variants(drums.hat, 4, rng, jitter={"decay": 0.2}, corr=0.45,
                              decay=float(rng.uniform(0.03, 0.06)), tone=float(rng.uniform(1.0, 1.3)))
    song.hits("hats", hats, lambda c: hat_pattern if not (c.kind == "breakdown" and c.bars_left > 2) else None,
              gain_db=-14.5 if rolling else -11.5, pan=0.2, humanize=0.1)
    ohat = xt.stereo_hit(drums.hat, rng, corr=0.5, open_=True, decay=float(rng.uniform(0.2, 0.3)),
                         tone=float(rng.uniform(1.0, 1.2)))
    song.hits("open_hat", ohat, lambda c: OPEN_HAT if (c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 8)
                                                         or (c.kind == "outro" and c.bars_left > 8)) else None,
              gain_db=-10.5, pan=-0.2, sends={"room": 0.12})
    ride_p = RIDE[int(rng.integers(len(RIDE)))]
    ride = xt.stereo_hit(drums.ride, rng, corr=0.55, decay=float(rng.uniform(1.0, 1.6)))
    song.hits("ride", ride, lambda c: ride_p if c.kind == "drop" or (c.kind == "groove" and c.i >= 16) else None,
              gain_db=-13.5, pan=0.3, sends={"room": 0.12})
    clap = xt.stereo_variants(drums.clap, 3, rng, jitter={"tone_hz": 0.05}, corr=0.7,
                              tone_hz=float(rng.uniform(1000, 1300)), tail=float(rng.uniform(0.16, 0.25)))
    if ind:
        clap = [xt.distorted(c_, 3.0, 8000.0) for c_ in clap]
    clap_p = CLAP[int(rng.integers(len(CLAP)))]
    song.hits("clap", clap, lambda c: clap_p if c.kind in ("groove", "drop", "outro") or (c.kind == "intro" and c.i >= 16)
              else None, gain_db=-4.0 if ind else -3.0, sends={"reverb": 0.35, "hall": 0.16 if ind else 0.1})
    snr = drums.snare(tone_hz=float(rng.uniform(170, 210)), snappy=0.75, decay=0.16, rng=rng)
    if ind:
        snr = xt.distorted(snr, 4.0, 7000.0)

    def snare_pat(c):
        if c.kind == "drop":
            return "....x.......x..." if not c.phrase_end else "....x.......x.xx"
        return None

    song.hits("snare", snr, snare_pat, gain_db=-8.0, sends={"reverb": 0.22})

    # ---------------------------------------------------------------- industrial textures / percussion
    metal = [drums.metal_hit(float(rng.uniform(250, 420)), 0.3, rng=rng), drums.metal_hit(float(rng.uniform(500, 700)), 0.2, rng=rng)]
    metal_p = METAL[int(rng.integers(len(METAL)))]
    song.hits("metal", metal, lambda c: metal_p if (c.kind in ("groove", "drop") and (c.i % 2 == 1 or ind))
              or (ind and c.kind == "breakdown" and c.i % 2 == 1) else None,
              gain_db=-9.0 if ind else -11.0, pan=-0.5, sends={"hall": 0.3 if ind else 0.22, "delay": 0.15},
              fx=[lambda x: fx.bitcrush(x, 8 if ind else 10, 3 if ind else 2)])
    perc = xt.ms_spread(drums.perc_blip(float(rng.uniform(500, 900)), 0.06, fm_index=2.5, ratio=1.41, rng=rng),
                        13.0, 0.5, 300.0)
    perc_p = euclid(int(rng.integers(3, 6)), 16, int(rng.integers(1, 5)))
    song.hits("perc", perc, lambda c: perc_p if c.kind != "breakdown" and not (c.kind == "intro" and c.i < 8) else None,
              gain_db=-13.0, pan=0.55, sends={"delay8": 0.2})
    if ind:
        # machine noise: band-passed noise ticks alternating L/R (factory floor)
        nz = [xt.distorted(drums.noise_hit(0.05, float(rng.uniform(2500, 4500)), rng=rng), 3.0, 9000.0) for _ in range(3)]
        song.hits("machine_l", nz, lambda c: "x.g.x.g.x.g.x.gx" if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 16)
                  else None, gain_db=-17.0, pan=-0.75, humanize=0.2)
        song.hits("machine_r", nz, lambda c: ".g.x.g.xxg.x.g.x" if c.kind in ("groove", "drop") else None,
                  gain_db=-18.0, pan=0.75, humanize=0.2)
    if rolling:
        shk = xt.stereo_variants(drums.shaker, 3, rng, corr=0.3, length=0.08)
        song.hits("shaker", shk, lambda c: "gxgogxgogxgogxgo" if c.kind != "breakdown" and not (c.kind == "intro" and c.i < 8)
                  else None, gain_db=-18.5, pan=-0.4, humanize=0.15)
        toms = [drums.tom(float(rng.uniform(95, 120)), 0.3, rng=rng), drums.tom(float(rng.uniform(140, 170)), 0.25, rng=rng)]
        song.hits("toms_roll", toms, lambda c: xt.steps_to_pattern(xt.poly_hits(c, 3, 2)) if c.kind in ("groove", "drop")
                  and c.i >= 8 else None, gain_db=-16.0, pan=0.35, sends={"room": 0.2, "delay8": 0.1}, humanize=0.2)
    tom = drums.tom(float(rng.uniform(90, 130)), 0.4, rng=rng)
    song.hits("tom_fill", [tom, xt.pitch_shift(tom, 3), xt.pitch_shift(tom, 7)],
              lambda c: "..........x.x.xx" if c.phrase_end and c.i % 16 == 15 and c.kind != "breakdown"
              else None, gain_db=-13.0, pan=-0.15, sends={"reverb": 0.2})

    # ---------------------------------------------------------------- rolling bass (rolling flavor)
    if rolling:
        rb_inst = inst.bass_pluck(cutoff=float(rng.uniform(160, 220)), env_amt=float(rng.uniform(900, 1400)),
                                  decay=0.07, res=0.3, sub=0.85, drive=1.8, grit=0.3, sustain=0.2)

        def rbass(c):
            if c.kind in ("intro", "breakdown") or c.bar >= bass_off:
                return []
            r = root + (key.scale[3] if c.kind == "drop" and c.i % 8 in (6, 7) else 0)
            ev = xt.bass_roll(r, "roll3", c.rng, shape=[0, 0, 12] if c.kind == "drop" else None)
            return [e for e in ev if e[0] < 8] if c.before("drop", 1) or c.before("breakdown", 1) else ev

        rbl = song.notes("rolling_bass", rb_inst, rbass, bus="bass", gain_db=-5.0, sidechain=0.7,
                         sc_release_ms=60000 / song.bpm * 0.3, humanize=0.04)
        rbl.automate("lp", [(groove, 300), (groove + 24, 1500), (d1, 2500), (outro.start_bar, 2500), (bass_off, 400)])

    # ---------------------------------------------------------------- tonal
    chords, prev = [], None
    degs = {"industrial": [0, 0, 1, 0], "rolling": [0, 0, 3, 5]}.get(flavor) or [[0, 0, 5, 3], [0, 6, 5, 6], [0, 0, 3, 4]][int(rng.integers(3))]
    for dg in degs:
        ch = key.chord(dg, 3, 4) if not (ind and dg == 1) else [key.root(3) + 1, key.root(3) + 5, key.root(3) + 8]
        ch = voice_lead(prev, ch, center=key.root(3) + 7)
        chords.append(ch)
        prev = ch

    if flavor in ("classic", "rolling"):
        if rolling:  # polymetric 3-step sequence (root / fifth / octave) – hypnotic 3-against-4
            cell = [key.root(4), key.degree(4, 4), key.root(5), key.degree(2, 4), key.degree(4, 4)]
            seq_fn = lambda c: [(s, 0.6, cell[((c.i * 16 + s) // 3) % len(cell)], 0.9 if s % 4 == 0 else 0.7)  # noqa: E731
                                for s in xt.poly_hits(c, 3)]
        else:
            seq = seq_pattern(rng, key)
            seq_fn = lambda c: seq  # noqa: E731
        seq_inst = xt.stereo_detune(inst.seq_blip(wave=str(rng.choice(["square", "saw"])), cutoff=float(rng.uniform(900, 1600)),
                                                  decay=float(rng.uniform(0.04, 0.08)), res=float(rng.uniform(0.4, 0.6))), 8.0, 0.3)
        seq_l = song.notes("sequence", seq_inst,
                           lambda c: seq_fn(c) if (c.kind in ("groove", "drop", "breakdown") or (c.kind == "outro" and c.i < 8)) else [],
                           gain_db=-3.0 if rolling else -7.0, sidechain=0.45, sends={"delay": 0.22, "hall": 0.08}, pan=0.15)
        seq_l.automate("lp", [(groove, 700), (groove + 24, 3500), (d1, 2500), (d1 + 16, 9000), (outro.start_bar + 8, 1200)])
    elif ind:  # metallic FM sequence, bit-crushed, low in the mix
        fm_seq = [(s, 0.5, key.root(4) + (12 if s in (6, 14) else 0), 0.9 if s % 4 == 2 else 0.6)
                  for s in (2, 3, 6, 10, 11, 14)]
        seq_l = song.notes("sequence", inst.fm_stab(ratio=3.5, index=5.0, decay=0.06),
                           lambda c: fm_seq if c.kind in ("groove", "drop") and c.i >= 8 else [],
                           gain_db=-8.0, sidechain=0.4, sends={"delay": 0.2, "hall": 0.15}, pan=0.3,
                           fx=[lambda x: fx.bitcrush(x, 9, 2)])
        seq_l.automate("lp", [(groove + 8, 1500), (d1, 6000), (outro.start_bar, 2500)])

    # acid line (303-style MonoSynth with slides/accents)
    if flavor in ("classic", "acid"):
        acid_a = acid_pattern(rng, key, root + 24, density=0.7 if acid_fl else None)
        acid_b = acid_pattern(rng, key, root + 24, density=0.8) if acid_fl else acid_a
        synth = inst.MonoSynth(wave=str(rng.choice(["saw", "square"])) if not acid_fl else "saw", cutoff=300.0,
                               res=float(rng.uniform(0.72, 0.86)) if not acid_fl else 0.86,
                               env_mod=float(rng.uniform(2.0, 3.0)), decay=float(rng.uniform(0.12, 0.22)),
                               glide_ms=60.0, drive=2.5, dist=0.35 if not acid_fl else 0.5)
        ca, cb = clip(acid_a, 2), clip(acid_b, 2)

        def acid_notes(c):
            if acid_fl:
                if c.kind == "groove" or c.kind == "breakdown":
                    return ca(c)
                if c.kind == "drop":
                    return cb(c) if c.name == "Drop 2" or c.i >= 8 else ca(c)
                if c.kind == "outro" and c.i < 8:
                    return ca(c)
                return []
            if c.kind == "drop" or (c.kind == "breakdown" and c.i >= 4) or (c.kind == "groove" and c.i >= c.section.bars - 8):
                return ca(c)
            return []

        acid = song.line("acid", synth, acid_notes, bus="music", gain_db=-5.0 if not acid_fl else -4.0, sidechain=0.4,
                         sends={"delay": 0.2 if not acid_fl else 0.25, "reverb": 0.08},
                         fx=[lambda x: xt.ms_spread(x, 9.0, 0.3, 400.0)])
        pts = []
        for s in song.sections:
            if s.kind == "groove":
                pts += [(s.start_bar, 260), (s.end_bar, 900 if acid_fl else 700)]
            elif s.kind == "breakdown":
                pts += [(s.start_bar, 400), (s.end_bar - 0.01, 2500)]
            elif s.kind == "drop":
                pts += [(s.start_bar, 800), (s.start_bar + s.bars * 0.75, 3800 if acid_fl else 3500), (s.end_bar, 1200)]
            elif s.kind == "outro" and acid_fl:
                pts += [(s.start_bar, 900), (s.start_bar + 8, 250)]
        acid.automate("cutoff", pts)
        if acid_fl:
            acid.automate("env_mod", [(groove, 1.6), (d1, 2.6), (d1 + 16, 3.4), (outro.start_bar, 2.0)])

    # stabs
    if flavor in ("classic", "rolling"):
        stab_r = [[(0, 1, 0.9), (6, 1, 0.6)], [(3, 1, 0.9), (10, 1, 0.7)], [(2, 1, 0.9)]][int(rng.integers(3))]
        dub = xt.dub_chord_st(cutoff=float(rng.uniform(500, 800)), env_amt=float(rng.uniform(900, 1600)))
        song.notes("dub_stab", dub,
                   lambda c: [(s, l, chords[(c.i // 4) % len(chords)], v) for s, l, v in stab_r]
                   if c.kind in ("breakdown", "drop") or (rolling and c.kind == "groove" and c.i >= 16) else [],
                   gain_db=-6.0 if rolling else -8.0, sidechain=0.5, sends={"delay": 0.35, "hall": 0.25})
    elif acid_fl:  # strobe: 16th-gated chord stab in the second half of each drop
        strobe = "x.xx.xx.x.xx.xx."
        stb = xt.rave_stab(cutoff=500.0, env_amt=3500.0, decay=0.05, drive=1.8, amp_decay=0.09)
        song.notes("strobe", stb, lambda c: [(i, 0.5, chords[(c.i // 4) % len(chords)], 0.9 if i % 4 == 0 else 0.65)
                                             for i, ch_ in enumerate(strobe) if ch_ == "x"]
                   if c.kind == "drop" and (c.i >= c.section.bars // 2) else [],
                   gain_db=-10.0, sidechain=0.6, sends={"delay8": 0.2, "hall": 0.12})
    elif ind:  # growl: distorted low-mid FM stab on the offbeats of the drop
        growl = inst.fm_stab(ratio=1.0, index=3.5, decay=0.12)
        gr = song.notes("growl", growl, lambda c: [(s, 1.5, key.root(2), 0.9 if c.kind == "drop" else 0.7) for s in (2, 6, 10, 14)]
                   if (c.kind == "drop" and c.i % 8 < 6) or (c.kind == "groove" and c.i >= 16)
                   or (c.kind == "breakdown" and c.i >= 8 and c.bars_left > 1) else [],
                   gain_db=-7.5, sidechain=0.7, hp=140.0, fx=[lambda x: xt.distorted(x, 5.0, 4000.0)],
                   sends={"reverb": 0.1})
        gr.automate("lp", [(groove + 16, 500), (d1 - 8, 600), (d1 - 0.01, 3000), (d1, 8000)])

    # breakdown pad / drone
    pad_inst = xt.warm_pad(attack=1.2, cutoff=900.0, detune=0.25, warmth=0.7)
    pad = song.notes("pad", pad_inst, lambda c: [(0, 63.5, chords[(c.i // 4) % len(chords)], 0.7)]
                     if c.kind == "breakdown" and c.i % 4 == 0 else [], gain_db=-12.0 if not ind else -7.0,
                     sends={"hall": 0.35}, humanize=0.0)
    for s in song.sections:
        if s.kind == "breakdown":
            pad.automate("lp", [(s.start_bar, 500), (s.end_bar, 4000)])
    if ind:
        song.notes("drone", xt.noise_drone(q=12.0, harmonics=(1, 2, 3), attack=3.0),
                   lambda c: [(0, c.section.bars * 16 - 4, key.root(2), 0.8)] if c.kind == "breakdown" and c.i == 0 else [],
                   gain_db=-1.0, sends={"hall": 0.3}, humanize=0.0)

    # ---------------------------------------------------------------- fx / transitions
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.15})
    crash = xt.stereo_hit(drums.crash, rng, corr=0.4, decay=2.4)
    roll_snr = drums.snare(tone_hz=float(rng.uniform(190, 230)), snappy=0.85, decay=0.12, rng=rng)
    if ind:
        roll_snr = xt.distorted(roll_snr, 3.0, 8000.0)
    for s in song.sections:
        if s.kind in ("groove", "drop", "outro"):
            fxl.add(crash, s.start_bar, gain_db=-9.0)
        if s.kind == "drop":
            fxl.add(fx.impact(3.0, rng=rng), s.start_bar, gain_db=-7.0)
            for b in range(s.start_bar + 16, s.end_bar, 16):
                fxl.add(crash, b, gain_db=-13.0)
                fxl.add(fx.noise_sweep(bar * 4, up=True, rng=rng), b, align="end", gain_db=-18.0)
        if s.kind == "breakdown":
            nb = min(8, s.bars)
            fxl.add(fx.riser(bar * nb, "both", f_lo=200, f_hi=10000, rng=rng), s.end_bar, align="end", gain_db=-8.0)
            fxl.add(fx.downlifter(bar * 2, rng=rng), s.start_bar, gain_db=-11.0)
            fxl.add(fx.reverse_cymbal(bar, rng=rng), s.end_bar, align="end", gain_db=-11.0)
            rb = min(8, s.bars) if s.bars >= 16 else 4
            fxl.add(xt.roll_buffer(song, rb, roll_snr, vel_from=0.2, vel_to=1.0, pitch_up=5.0), s.end_bar,
                    align="end", gain_db=-9.0)
    fxl.add(fx.noise_sweep(bar * 8, up=True, rng=rng), groove, align="end", gain_db=-16.0)

    song.buses["drums"].eq = [("peak", 3000.0, 1.5, 0.8)]
    mud, pres = {"classic": (-2.0, 1.5), "industrial": (0.0, 1.5), "acid": (-2.5, 3.0), "rolling": (0.0, 2.5)}[flavor]
    song.buses["music"].eq = [("peak", 420.0, mud, 0.9), ("peak", 1600.0, pres, 0.8)]
    song.master.lufs = -9.0
    if kick_hz > 50.0 and not rolling:  # kick body near the 60 Hz edge → gentle sub tilt in the master
        song.master.low_shelf_db, song.master.low_shelf_hz = 2.0, 55.0
    common = ["driving techno kick", "sidechained reverb rumble", "stereo closed & open hats", "ride",
              "clap & snare (plate)", "industrial metal hits", "pitched snare rolls, risers & noise sweeps"]
    extra = {
        "classic": ["hypnotic 16th sequence", "acid line", "dub chord stabs"],
        "industrial": ["distorted kick & rumble", "machine noise", "bit-crushed FM sequence", "growl stabs", "dark drone"],
        "acid": ["303-style acid lead", "strobe chord stabs"],
        "rolling": ["rolling 16th bassline", "polymetric 3/16 sequence", "rolling toms & shaker", "dub chord stabs"],
    }[flavor]
    song.instruments = common + extra
    kname = plan["key"]
    desc = {
        "classic": "קיק דוחף עם ראמבל עמוק, סיקוונס היפנוטי, קו אסיד שנפתח לאורך הטראק וסטאבים דאביים עם דיליי",
        "industrial": "הצד התעשייתי, הכהה והמעוות — קיק וראמבל עם דיסטורשן, צלצולי מתכת, רעש מכונות בסטריאו, "
                      "סטאבים גרוליים ודרון אפל בברייקדאון",
        "acid": "קו אסיד בסגנון 303 שמוביל את הטראק מהגרוב ועד הדרופ — הפילטר נפתח לאט, וסטאבים מהבהבים "
                "(סטרובו) בחצי השני של כל דרופ",
        "rolling": "גרוב מתגלגל ודוהר — באסליין מתגלגל בשש-עשריות, היי-האטים רצים, סיקוונס פולימטרי של 3 נגד 4, "
                   "טומים מתגלגלים, סטאבים דאביים עם דיליי ודרופ ארוך",
    }[flavor]
    gname = "טכנו דוהר (Driving)" if "Driving" in plan.get("genre", "") else "טכנו פיק-טיים"
    slot = {"peak": "לרגעי השיא של הסט", "build": "לבניית אנרגיה באמצע הסט"}.get(plan.get("role"), "לאמצע-סוף הסט")
    song.description_he = f"{gname} ב-{int(song.bpm)} BPM בסולם {kname}: {desc}. {slot}."
    song.mix_tips_he = (song.auto_mix_tips_he() + " הראמבל יושב על הסאב — בזמן מעבר הורידו את ה-Low בטראק היוצא. "
                        + xt.neighbours_he(plan))
    return song
