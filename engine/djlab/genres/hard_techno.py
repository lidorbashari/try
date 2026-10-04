"""Hard Techno recipe (145–155 BPM).

Distorted punchy kick with a saturated, heavily side-chained rumble (the 'bounce' between kicks),
hard stereo clap into a plate, fast 16th hats, offbeat open hats and an 8th ride, metal hits and tom
rolls, accelerating pitched snare rolls, pitched noise risers and impacts. Relentless but clean:
the distortion lives on the sources (post low-passed), the master stays at ≈ -9 LUFS.

Flavors (per plan id; unknown ids draw one from ``rng``):

* ``rave``      – 90s rave energy: hoover riff (pitch scoops & dives) and rave chord stabs (techno-11)
* ``overdrive`` – aggressive: screeching resonant lead + distorted acid line, industrial clangs (techno-12)
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from .. import ext_techno as xt
from ..arrangement import Song, clip, euclid
from ..dsp import normalize
from ..theory import voice_lead
from . import register

TEMPLATES = {
    "rave": [("Intro", "intro", 32, 5, 0), ("Groove", "groove", 24, 7, 2), ("Breakdown", "breakdown", 16, 5, 0),
             ("Drop", "drop", 32, 10, 3), ("Outro", "outro", 32, 6, 0)],
    "overdrive": [("Intro", "intro", 32, 5, 0), ("Groove", "groove", 16, 7, 2), ("Breakdown", "breakdown", 8, 5, 0),
                  ("Drop", "drop", 32, 10, 3), ("Breakdown 2", "breakdown", 8, 6, 0), ("Drop 2", "drop", 24, 10, 1),
                  ("Outro", "outro", 32, 6, 0)],
}
FLAVORS = {"techno-11": "rave", "techno-12": "overdrive"}

# hoover riff (2 bars): (step, length, semitone offset, vel)
HOOVER_RIFFS = [
    [(0, 3, 0, 1.0), (3, 3, 0, 0.85), (6, 2, 12, 0.9), (8, 3, 0, 1.0), (11, 3, 3, 0.85), (14, 2, 0, 0.8),
     (16, 3, 0, 1.0), (19, 3, 0, 0.85), (22, 2, 12, 0.9), (24, 6, 7, 1.0), (30, 2, 5, 0.8)],
    [(0, 6, 0, 1.0), (6, 2, -2, 0.85), (8, 6, 0, 1.0), (14, 2, 3, 0.85), (16, 6, 0, 1.0), (22, 2, 5, 0.85),
     (24, 4, 3, 1.0), (28, 4, -2, 0.85)],
]
SCREECH_RIFFS = [
    [(0, 1, 12, 0.9, "a"), (2, 1, 12, 0.7, ""), (3, 1, 15, 0.9, "s"), (4, 1, 12, 0.8, "a"), (6, 1, 24, 0.9, "a"),
     (8, 1, 12, 0.7, ""), (10, 1, 10, 0.9, "s"), (11, 1, 12, 0.8, "a"), (12, 2, 12, 0.9, "a"), (14, 1, 7, 0.8, "s"),
     (15, 1, 12, 0.9, "a")],
    [(0, 2, 12, 0.9, "a"), (3, 1, 13, 0.8, "s"), (4, 1, 12, 0.9, "a"), (7, 1, 24, 0.8, "a"), (8, 2, 12, 0.9, "a"),
     (11, 1, 15, 0.8, "s"), (12, 1, 12, 0.9, "a"), (14, 1, 10, 0.8, "a"), (15, 1, 12, 0.7, "")],
]


@register("hard_techno")
def build(plan: dict, rng: np.random.Generator) -> Song:
    flavor = FLAVORS.get(plan["id"]) or xt.pick(rng, ["rave", "overdrive"])
    rave = flavor == "rave"
    song = Song(plan, rng, swing=50.0)
    key = song.key
    song.arrange(TEMPLATES[flavor], song.target_bars())
    groove = song.bar("groove")
    song.mix_in_bar = groove
    outro = song.find("outro")
    bass_off = outro.start_bar + outro.bars - 16
    d1 = song.bar("drop")
    bar = song.grid.bar_sec
    xt.setup_space(song, hall_decay=2.8, plate_width=1.5)
    root = key.root(1)
    while root < 31:
        root += 12

    # ================================================================ kick + rumble
    kick = drums.kick("hard", tune_hz=xt.kick_tune(key, 45.0, 60.0), decay=float(rng.uniform(0.3, 0.36)),
                      click=0.85, drive=float(rng.uniform(5.5, 7.0)), rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown":
            if c.section.bars >= 16 and 8 <= c.i < c.section.bars - 1:  # kick returns as a build
                return "x...x...x...x..." if c.bars_left > 4 else ("x.x.x.x.x.x.x.x." if c.bars_left > 2 else "xxxxxxxxxxxxxxxx")
            return None
        if c.before("drop", 1):
            return None
        if c.before("breakdown", 1):
            return "x...x...x...x.x."
        return "x...x...x...x..."

    song.hits("kick", kick, kick_pat, gain_db=-3.0, sc_source=True, humanize=0.0)

    def rumble_pat(c):
        if c.kind in ("intro", "breakdown") or c.bar >= bass_off or c.before("drop", 1):
            return None
        return "x...x...x...x..."

    rum = song.hits("rumble", kick, rumble_pat, bus="bass", gain_db=-6.0, humanize=0.0, hp=38.0,
                    fx=[lambda x: fx.rumble(x, song.bpm, cutoff=float(rng.uniform(190, 230)), decay=1.6,
                                            drive=float(rng.uniform(7.0, 9.0)))],
                    sidechain=1.0, sc_release_ms=60000 / song.bpm * 0.7)
    rum.automate("lp", [(groove, 150), (groove + 8, 450), (outro.start_bar, 450), (bass_off, 160)])

    # ================================================================ tops
    hats = xt.stereo_variants(drums.hat, 4, rng, jitter={"decay": 0.2}, corr=0.45, decay=0.03, tone=1.25)
    hat_v = xt.pick(rng, ["oxXxoxXxoxXxoxXx", "xoXoxoXoxoXoxoXo"])
    song.hits("hats", hats, lambda c: hat_v if not (c.kind == "breakdown" and c.bars_left > 4) and not (c.kind == "intro" and c.i < 4)
              else None, gain_db=-13.0, pan=0.2, humanize=0.1)
    ohat = xt.stereo_hit(drums.hat, rng, corr=0.5, open_=True, decay=0.18, tone=1.2)
    song.hits("open_hat", ohat, lambda c: "..x...x...x...x." if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 8)
              or (c.kind == "outro" and c.bars_left > 8) else None, gain_db=-10.5, pan=-0.2, sends={"room": 0.1})
    ride = xt.stereo_hit(drums.ride, rng, corr=0.55, decay=1.1)
    song.hits("ride", ride, lambda c: "x.x.x.x.x.x.x.x." if c.kind == "drop" else None, gain_db=-15.0, pan=0.3)
    clap = [xt.distorted(c_, 2.0, 9000.0) for c_ in
            xt.stereo_variants(drums.clap, 3, rng, corr=0.7, tone_hz=float(rng.uniform(1200, 1500)), tail=0.14, tightness=0.8)]
    song.hits("clap", clap, lambda c: ("....x.......x..." if not c.phrase_end else "....x.......x.xx")
              if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 16) or (c.kind == "outro" and c.bars_left > 8)
              else None, gain_db=-2.5, sends={"reverb": 0.3, "hall": 0.08})
    metal = [drums.metal_hit(float(rng.uniform(300, 450)), 0.25, rng=rng), drums.metal_hit(float(rng.uniform(600, 800)), 0.18, rng=rng)]
    met_p = xt.pick(rng, ["...x......x.....", ".......x.....x..", "...x...x...x...x"])
    song.hits("metal", metal, lambda c: met_p if c.kind in ("groove", "drop") and (c.i % 2 or not rave) else None,
              gain_db=-12.0 if rave else -10.0, pan=-0.45, sends={"hall": 0.25, "delay": 0.12},
              fx=[lambda x: fx.bitcrush(x, 9, 2)])
    perc = xt.ms_spread(drums.perc_blip(float(rng.uniform(700, 1000)), 0.04, fm_index=3.0, ratio=1.5, rng=rng), 11.0, 0.5, 300.0)
    perc_p = euclid(int(rng.integers(5, 8)), 16, int(rng.integers(1, 4)))
    song.hits("perc", perc, lambda c: perc_p if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 16) else None,
              gain_db=-14.0, pan=0.5, sends={"delay8": 0.15})
    tom = drums.tom(float(rng.uniform(100, 130)), 0.3, rng=rng)
    song.hits("tom_roll", [tom, xt.pitch_shift(tom, 4), xt.pitch_shift(tom, 7)],
              lambda c: "........x.x.xxxx" if c.every(8) and c.kind in ("groove", "drop", "intro") else None,
              gain_db=-12.0, pan=-0.2, sends={"reverb": 0.15})

    # ================================================================ lead material
    chords = [voice_lead(None, key.chord(0, 3, 3), center=key.root(4) - 3)]
    chords.append(voice_lead(chords[0], key.chord(5, 3, 3), center=key.root(4) - 3))
    chords.append(voice_lead(chords[1], key.chord(6, 3, 3), center=key.root(4) - 3))
    chords.append(voice_lead(chords[2], key.chord(4, 3, 3), center=key.root(4) - 3))

    if rave:
        hoov = xt.hoover(detune_cents=22.0, scoop=7.0, dive=12.0, pw_rate=3.0, cutoff=4200.0, drive=2.0, release=0.22)
        riff = xt.pick(rng, HOOVER_RIFFS)
        hroot = key.root(2)
        hclip = clip([(s, l - 0.2, hroot + o, v) for s, l, o, v in riff], 2)

        def hoover_notes(c):
            if c.kind == "drop" or (c.kind == "groove" and c.i >= c.section.bars - 8):
                return hclip(c)
            if c.kind == "breakdown" and c.i < 8 and c.i % 4 == 0:  # long hoover chord swells in the break
                return [(0, 60, ch_, 0.8) for ch_ in chords[(c.i // 4) % 2]]
            return []

        hv = song.notes("hoover", hoov, hoover_notes, gain_db=-8.0, sidechain=0.5, humanize=0.03,
                        sends={"reverb": 0.12, "delay8": 0.1})
        hv.automate("lp", [(groove + 16, 1200), (d1 - 0.01, 3000), (d1, 9000)])
        stab = xt.rave_stab(cutoff=900.0, env_amt=7000.0, decay=0.08, drive=2.5)
        st_p = xt.pick(rng, [[(2, 1, 0.9), (6, 1, 0.8), (10, 1, 0.9), (13, 1, 0.7)], [(3, 1, 0.9), (6, 1, 0.8), (11, 1, 0.9)]])

        def stab_notes(c):
            if c.kind == "groove" and c.i >= 8 or c.kind == "drop" and c.i % 8 >= 4 or (c.kind == "breakdown" and c.i >= 8):
                ch_ = chords[(c.i // 2) % len(chords)]
                return [(s, l, ch_, v) for s, l, v in st_p]
            return []

        stb = song.notes("rave_stab", stab, stab_notes, gain_db=-9.0, sidechain=0.55, humanize=0.04,
                         sends={"reverb": 0.2, "delay": 0.15})
        for s in song.sections:
            if s.kind == "breakdown":
                stb.automate("lp", [(s.start_bar + 8, 800), (s.end_bar, 9000)])
    else:
        # screech lead: resonant, driven MonoSynth with slides – the hard-techno 'scream'
        sc = inst.MonoSynth(**xt.screech())
        riff = xt.pick(rng, SCREECH_RIFFS)
        sroot = root + 24
        sclip = clip([(s, l, sroot + o, v, f) for s, l, o, v, f in riff], 1)

        def screech_notes(c):
            if c.kind == "drop" and (c.i % 8 < 6 or c.name == "Drop 2"):
                return sclip(c)
            if c.kind == "breakdown" and c.bars_left <= 4:
                return sclip(c)
            return []

        scr = song.line("screech", sc, screech_notes, bus="music", gain_db=-9.0, sidechain=0.45,
                        sends={"reverb": 0.12, "delay8": 0.12}, hp=250.0,
                        fx=[lambda x: xt.ms_spread(xt.distorted(x, 2.5, 7500.0), 8.0, 0.35, 500.0)])
        pts = []
        for s in song.sections:
            if s.kind == "drop":
                pts += [(s.start_bar, 1400), (s.start_bar + s.bars - 0.01, 4200)]
            if s.kind == "breakdown":
                pts += [(s.end_bar - 4, 500), (s.end_bar - 0.01, 2500)]
        scr.automate("cutoff", pts)
        # aggressive acid in the groove and under the drops
        acid_ev = []
        for st in range(32):
            if st % 2 == 0 or rng.random() < 0.55:
                o = int(rng.choice([0, 0, 0, 12, 3, 10, 7, -2]))
                fl = ("a" if (st % 4 == 0 or rng.random() < 0.3) else "") + ("s" if rng.random() < 0.2 else "")
                acid_ev.append((st, 0.6 if "s" not in fl else 1.0, root + 12 + o, 0.9, fl))
        acid = song.line("acid", inst.MonoSynth(wave="saw", cutoff=300.0, res=0.85, env_mod=3.0, decay=0.12, glide_ms=40.0,
                                                drive=3.5, dist=0.6), lambda c: clip(acid_ev, 2)(c)
                         if c.kind in ("groove", "drop") or (c.kind == "outro" and c.i < 8) else [],
                         bus="music", gain_db=-8.5, sidechain=0.55, sends={"delay": 0.15}, hp=110.0,
                         fx=[lambda x: xt.ms_spread(x, 10.0, 0.3, 400.0)])
        apts = []
        for s in song.sections:
            if s.kind == "groove":
                apts += [(s.start_bar, 250), (s.end_bar, 1800)]
            elif s.kind == "drop":
                apts += [(s.start_bar, 900), (s.start_bar + s.bars // 2, 2600), (s.end_bar, 1200)]
            elif s.kind == "outro":
                apts += [(s.start_bar, 1000), (s.start_bar + 8, 250)]
        acid.automate("cutoff", apts)
        # industrial distorted noise bursts on the offbeat 16ths
        nz = [xt.distorted(drums.noise_hit(0.04, float(rng.uniform(3000, 5000)), rng=rng), 4.0, 10000.0) for _ in range(3)]
        song.hits("noise_16", nz, lambda c: "..x...x...x..xx." if c.kind == "drop" else None,
                  gain_db=-16.0, pan=0.6, humanize=0.2)

    # dark pad for the breakdowns (both flavors)
    pad = song.notes("pad", xt.warm_pad(attack=1.0, release=1.8, cutoff=1500.0, detune=0.3, warmth=0.5),
                     lambda c: [(0, 8 * 16 - 2, chords[0 if c.i == 0 else 1], 0.75)]
                     if c.kind == "breakdown" and c.i % 8 == 0 else [], gain_db=-13.0, humanize=0.0,
                     sends={"hall": 0.35})
    for s in song.sections:
        if s.kind == "breakdown":
            pad.automate("lp", [(s.start_bar, 600), (s.end_bar, 5000)])

    # ================================================================ fx
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.12})
    crash = xt.stereo_hit(drums.crash, rng, corr=0.4, decay=2.0)
    snr = xt.distorted(drums.snare(tone_hz=float(rng.uniform(200, 240)), snappy=0.9, decay=0.11, rng=rng), 2.5, 9000.0)
    for s in song.sections:
        if s.kind in ("groove", "drop", "outro"):
            fxl.add(crash, s.start_bar, gain_db=-9.0)
        if s.kind == "drop":
            fxl.add(fx.impact(2.5, rng=rng), s.start_bar, gain_db=-6.0)
            for b in range(s.start_bar + 8, s.end_bar, 8):
                fxl.add(crash, b, gain_db=-14.0 if (b - s.start_bar) % 16 else -11.0)
        if s.kind == "breakdown":
            nb = 8 if s.bars >= 8 else s.bars
            fxl.add(xt.pitched_riser(bar * nb, f_from=float(110 * 2 ** ((key.root_pc - 9) / 12)), f_to=1760.0, rng=rng),
                    s.end_bar, align="end", gain_db=-9.0)
            fxl.add(fx.riser(bar * nb, "noise", f_lo=300, f_hi=12000, rng=rng), s.end_bar, align="end", gain_db=-12.0)
            fxl.add(fx.downlifter(bar * 2, rng=rng), s.start_bar, gain_db=-11.0)
            fxl.add(xt.roll_buffer(song, min(8, s.bars), snr, vel_from=0.25, vel_to=1.0, pitch_up=7.0), s.end_bar,
                    align="end", gain_db=-9.0)
    fxl.add(fx.noise_sweep(bar * 8, up=True, rng=rng), groove, align="end", gain_db=-15.0)

    song.buses["drums"].eq = [("peak", 2800.0, 1.5, 0.8)]
    song.buses["music"].eq = [("peak", 400.0, -2.0, 0.9)]
    song.master.lufs = -9.0
    common = ["distorted hard kick", "saturated side-chained rumble", "hard stereo clap", "fast 16th hats",
              "open hats & ride", "metal hits & tom rolls", "pitched noise risers & snare rolls"]
    if rave:
        song.instruments = common + ["hoover riff", "rave chord stabs"]
        desc = "אנרגיית רייב של שנות ה-90: ריף הובר עם גלישות פיץ' וסטאבים של אקורדי רייב"
    else:
        song.instruments = common + ["screech lead", "distorted acid line", "industrial noise bursts"]
        desc = "אגרסיבי ותעשייתי: ליד צורח עם רזוננס, קו אסיד מעוות ופרצי רעש מתכתיים"
    song.description_he = (f"הארד טכנו ב-{int(song.bpm)} BPM בסולם {plan['key']}: קיק מעוות ופאנצ'י עם ראמבל רווי, "
                           f"קלאפ קשה והיי-האטים מהירים; {desc}. בלתי מתפשר — לשיא של הסט.")
    song.mix_tips_he = (song.auto_mix_tips_he() +
                        " ב-148–150 BPM המעבר מטכנו רגיל דורש קפיצת טמפו: עדיף להיכנס מטראק הארד אחר או לעשות Cut חד על "
                        "תחילת פרייז.")
    return song
