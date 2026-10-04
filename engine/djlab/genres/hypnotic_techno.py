"""Hypnotic / Minimal Techno recipe (125–130 BPM).

Repetition with micro-variation: a short loop set (kick, sub, dub chord, percussion) that evolves
bar by bar through deterministic per-bar randomness (ghost notes appear/disappear, chord rhythms
rotate), **polymetric** percussion and sequences (3/16 and 5/16 cycles against the 4/4 kick) and one
long **filter journey** — every tonal layer follows the same low-pass curve from dark (groove) to
open (middle of the drop) and back (outro). Few drops: a single 8-bar kick-out breakdown.

Flavors (per plan id, unknown ids draw one from ``rng``):

* ``tunnel``  – deep and tunnel-like: round kick + long rumble, offbeat sub, dub chords into long
  feedback delays, pitched noise drone, swirling sweeps (techno-09 Infinite Loop)
* ``micro``   – sparse and clicky minimal: tight kick, short sub blips, clicks/ticks in 3/16, 5/16 and
  7/16, rim + snap, a lone dub stab, blip sequence (techno-10 Micro Groove)
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from .. import ext_techno as xt
from ..arrangement import Song, euclid
from . import register

TEMPLATE = [
    ("Intro", "intro", 32, 4, 0),
    ("Groove", "groove", 40, 6, 2),
    ("Breakdown", "breakdown", 8, 4, 0),
    ("Drop", "drop", 32, 7, 3),
    ("Outro", "outro", 32, 4, 0),
]
FLAVORS = {"techno-09": "tunnel", "techno-10": "micro"}

# 1-bar dub-chord rhythms (step, length, vel); the loop rotates between them every 4 bars
CHORD_RHYTHMS = [
    [(3, 1.0, 0.9), (10, 1.0, 0.7)],
    [(2, 1.0, 0.85), (7, 1.0, 0.6), (13, 1.0, 0.7)],
    [(3, 1.0, 0.9), (6, 0.5, 0.5), (14, 1.0, 0.75)],
    [(0, 1.0, 0.8), (6, 1.0, 0.7), (11, 1.0, 0.6)],
]


@register("hypnotic_techno")
def build(plan: dict, rng: np.random.Generator) -> Song:
    flavor = FLAVORS.get(plan["id"]) or xt.pick(rng, ["tunnel", "micro"])
    tunnel = flavor == "tunnel"
    song = Song(plan, rng, swing=52.0 if tunnel else 55.0)
    key = song.key
    song.arrange(TEMPLATE, song.target_bars())
    intro, grv, bd, drop, outro = (song.find(k) for k in ("intro", "groove", "breakdown", "drop", "outro"))
    g0, b0, d0, o0 = grv.start_bar, bd.start_bar, drop.start_bar, outro.start_bar
    song.mix_in_bar = g0
    bass_off = o0 + outro.bars - 16
    bar = song.grid.bar_sec
    xt.setup_space(song, hall_decay=4.5 if tunnel else 2.5, long_reverb=6.0 if tunnel else None,
                   quarter_delay=True, delay_fb=0.55 if tunnel else 0.42)
    root = key.root(1)
    while root < 28:
        root += 12
    while root > 39:
        root -= 12

    # the filter journey shared by every tonal layer: dark → open at the middle of the drop → dark
    peak = d0 + drop.bars // 2

    def journey(lo, hi):
        return [(g0, lo), (b0, lo + (hi - lo) * 0.45), (b0 + bd.bars - 0.01, lo * 1.4), (d0, lo + (hi - lo) * 0.5),
                (peak, hi), (o0, lo + (hi - lo) * 0.4), (o0 + 16, lo)]

    def groove_on(c, from_intro=16):
        return (c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= from_intro)
                or (c.kind == "outro" and c.bars_left > 8))

    # ================================================================ drums
    if tunnel:
        kick = drums.kick("deep", tune_hz=xt.kick_tune(key), decay=0.42, click=0.35, drive=1.6, rng=rng)
    else:
        kick = drums.kick("tech_house", tune_hz=xt.kick_tune(key, 46.0, 60.0), decay=0.27, click=0.55, drive=1.5, rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown":
            return None
        return "x...x...x...x..."

    song.hits("kick", kick, kick_pat, gain_db=-2.0, sc_source=True, humanize=0.0)

    if tunnel:
        def rumble_pat(c):
            return None if c.kind in ("intro", "breakdown") or c.bar >= bass_off else "x...x...x...x..."

        rum = song.hits("rumble", kick, rumble_pat, bus="bass", gain_db=-9.0, humanize=0.0,
                        fx=[lambda x: fx.rumble(x, song.bpm, cutoff=140.0, decay=3.0, drive=3.0)],
                        sidechain=1.0, sc_release_ms=60000 / song.bpm * 0.9)
        rum.automate("lp", [(g0, 110), (g0 + 24, 300), (o0, 300), (bass_off, 120)])

    hats = xt.stereo_variants(drums.hat, 4, rng, jitter={"decay": 0.2}, corr=0.45,
                              decay=0.04 if tunnel else 0.022, tone=float(rng.uniform(1.0, 1.25)))

    def hat_pat(c):
        if c.kind == "breakdown" and c.bars_left > 2:
            return None
        if c.kind == "intro" and c.i < 4:
            return None
        base = list("gogxgogxgogxgogx" if tunnel else "..x...x...x...x.")
        # micro-variation: every bar a ghost note may appear or vanish
        for _ in range(2):
            s = int(c.rng.integers(16))
            if s % 4 != 0:
                base[s] = "g" if base[s] == "." else "."
        return "".join(base)

    song.hits("hats", hats, hat_pat, gain_db=-11.5 if tunnel else -9.5, pan=0.2, humanize=0.12)
    ohat = xt.stereo_hit(drums.hat, rng, corr=0.5, open_=True, decay=0.22 if tunnel else 0.12, tone=1.1)
    song.hits("open_hat", ohat, lambda c: "..x...x...x...x." if groove_on(c, 8) and (tunnel or c.kind == "drop") else None,
              gain_db=-12.0, pan=-0.2, sends={"room": 0.12})
    clap = xt.stereo_variants(drums.clap, 3, rng, corr=0.7, tone_hz=float(rng.uniform(1000, 1250)),
                              tail=0.25 if tunnel else 0.12)
    clap_p = "............x..." if tunnel else "....x.......x..."
    song.hits("clap", clap, lambda c: clap_p if groove_on(c) else None, gain_db=-4.5 if tunnel else -6.5,
              sends={"hall": 0.25 if tunnel else 0.05, "reverb": 0.15})
    if not tunnel:
        snap = xt.stereo_hit(drums.snap, rng, corr=0.6)
        song.hits("snap", snap, lambda c: "....x.......x..." if groove_on(c, 8) else None, gain_db=-8.0,
                  sends={"room": 0.15}, timing_ms=1.0)

    # polymetric percussion: 3/16 rim + 5/16 tick against the 4/4 kick
    rim = drums.rimshot(float(rng.uniform(1500, 1900)), rng=rng)
    song.hits("poly3", rim, lambda c: xt.steps_to_pattern(xt.poly_hits(c, 3, 1, reset_bars=8),
                                                          vel_fn=lambda k, s: "x" if k % 2 == 0 else "o")
              if groove_on(c) else None, gain_db=-12.0 if tunnel else -10.5, pan=0.45,
              sends={"delay8": 0.18, "room": 0.1}, humanize=0.1)
    tick = drums.perc_blip(float(rng.uniform(1200, 1700)), 0.03, fm_index=3.0, ratio=1.7, rng=rng)
    song.hits("poly5", xt.ms_spread(tick, 9.0, 0.6, 600.0),
              lambda c: xt.steps_to_pattern(xt.poly_hits(c, 5, 2, reset_bars=16)) if (c.kind in ("groove", "drop")) else None,
              gain_db=-13.0, pan=-0.5, sends={"delay": 0.15}, humanize=0.15)
    if not tunnel:
        # clicks: tiny ticks in 7/16 and an evolving euclid, panned wide – the 'micro' texture
        clicks = [xt.click(float(rng.uniform(3000, 6000)), 0.008, rng=rng) for _ in range(3)]
        song.hits("click7", clicks, lambda c: xt.steps_to_pattern(xt.poly_hits(c, 7, 3, reset_bars=8))
                  if groove_on(c, 8) else None, gain_db=-8.5, pan=0.7, humanize=0.2)
        eu = [euclid(k, 16, r) for k, r in ((5, 1), (7, 2), (3, 3), (6, 1))]
        song.hits("click_eu", clicks, lambda c: eu[(c.i // 4) % 4] if c.kind in ("groove", "drop") else None,
                  gain_db=-10.5, pan=-0.7, humanize=0.2, sends={"delay8": 0.1})
        shk = xt.stereo_variants(drums.shaker, 3, rng, corr=0.3, length=0.05)
        song.hits("shaker", shk, lambda c: "g.gxg.gxg.gxg.gx" if c.kind == "drop" else None, gain_db=-19.0, pan=0.3)
    else:
        shk = xt.stereo_variants(drums.shaker, 3, rng, corr=0.3, length=0.09)
        song.hits("shaker", shk, lambda c: "xgogxgogxgogxgog" if groove_on(c, 16) else None, gain_db=-18.0, pan=-0.35,
                  humanize=0.15)
        ride = xt.stereo_hit(drums.ride, rng, corr=0.55, decay=1.6)
        song.hits("ride", ride, lambda c: "..x...x...x...x." if c.kind == "drop" else None, gain_db=-16.0, pan=0.3,
                  sends={"hall": 0.1})
        tom = drums.tom(float(rng.uniform(85, 105)), 0.5, rng=rng)
        song.hits("toms", [tom, xt.pitch_shift(tom, 3)], lambda c: xt.steps_to_pattern(xt.poly_hits(c, 3, 2, reset_bars=4))
                  if c.kind == "drop" and c.i % 8 >= 4 else None, gain_db=-17.0, pan=-0.3,
                  sends={"hall": 0.2, "delay": 0.1}, humanize=0.2)

    # ================================================================ bass
    if tunnel:
        sub_i = inst.bass_pluck(cutoff=140.0, env_amt=500.0, decay=0.12, res=0.2, sub=1.0, drive=1.2, grit=0.1,
                                sustain=0.5, wave="square")

        def bass_notes(c):
            if c.kind in ("intro", "breakdown") or c.bar >= bass_off:
                return []
            ev = xt.bass_roll(root, "offbeat", c.rng, octave_jump=False, fifth=0)
            if c.i % 8 == 7:
                ev[-1] = (14, 1.6, root + key.scale[6] - 12, 0.85)  # flat-7 pickup at the phrase end
            return ev

        song.notes("sub", sub_i, bass_notes, bus="bass", gain_db=-6.0, sidechain=0.6, humanize=0.03)
    else:
        sub_i = inst.sub_bass(harmonics=0.2, drive=1.4, release=0.03, attack=0.003)
        base_b = [(2, 1.2, 0, 0.9), (7, 0.8, 0, 0.6), (10, 1.2, 0, 0.9), (13, 0.8, 7, 0.55)]

        def bass_notes(c):
            if c.kind in ("intro", "breakdown") or c.bar >= bass_off:
                return []
            ev = [(s, l, root + o, v) for s, l, o, v in base_b]
            if c.rng.random() < 0.35:  # micro-variation: one note moves by a 16th or drops out
                k = int(c.rng.integers(len(ev)))
                s, l, p, v = ev[k]
                ev[k] = (s + (1 if s < 14 else -1), l, p, v * 0.8) if c.rng.random() < 0.6 else (s, l, p, 0.0)
                ev = [e for e in ev if e[3] > 0]
            return ev

        song.notes("sub", sub_i, bass_notes, bus="bass", gain_db=-6.5, sidechain=0.45, humanize=0.05)

    # ================================================================ dub chords (the loop)
    chord = key.chord(0, 3, 4) + ([key.degree(8, 3)] if tunnel else [])
    alt = key.chord(5, 3, 4) if tunnel else key.chord(3, 3, 3)
    from ..theory import voice_lead
    ch_a = voice_lead(None, chord, center=key.root(4) - 2)
    ch_b = voice_lead(ch_a, alt, center=key.root(4) - 2)
    dub_i = xt.dub_chord_st(cutoff=500.0 if tunnel else 900.0, env_amt=1200.0 if tunnel else 2500.0,
                            decay=0.25 if tunnel else 0.08, amp_decay=0.35 if tunnel else 0.12)

    def dub_notes(c):
        on = c.kind in ("groove", "drop", "breakdown") or (c.kind == "outro" and c.i < 16)
        if not on:
            return []
        if not tunnel:  # a lone stab every 2 bars, position drifting
            if c.i % 2:
                return []
            st = [3, 6, 10, 11][(c.i // 2) % 4]
            return [(st, 1.0, ch_a, 0.9)]
        rh = CHORD_RHYTHMS[(c.i // 4 + int(c.rng.integers(2)) * (c.i % 4 == 3)) % len(CHORD_RHYTHMS)]
        ch_ = ch_b if (c.i % 16) >= 12 else ch_a
        return [(s, l, ch_, v) for s, l, v in rh]

    dub = song.notes("dub_chord", dub_i, dub_notes, gain_db=-6.0 if tunnel else -3.0, sidechain=0.55,
                     humanize=0.05, sends={"delay": 0.4 if tunnel else 0.3, "hall": 0.25 if tunnel else 0.1,
                                          "delay4": 0.15 if tunnel else 0.0})
    dub.automate("lp", journey(450, 4500) if tunnel else journey(700, 7000))

    # hypnotic sequence: 5-note cell on a 3-step grid (polymeter); micro: high blips
    cell = ([key.root(4), key.degree(2, 4), key.degree(4, 4), key.root(5), key.degree(4, 4)] if tunnel
            else [key.root(5), key.degree(6, 4), key.root(5), key.degree(4, 4), key.degree(2, 5)])
    period = 3 if tunnel else 5
    seq_i = xt.stereo_detune(inst.seq_blip(wave="square" if tunnel else "saw", cutoff=900.0 if tunnel else 1800.0,
                                           decay=0.06 if tunnel else 0.03, res=0.5), 9.0, 0.35)
    seq = song.notes("sequence", seq_i, lambda c: [(s, 0.6, cell[((c.i % 8) * 16 + s) // period % len(cell)],
                                                     0.9 if s % 4 == 0 else 0.65)
                                                    for s in xt.poly_hits(c, period, 0, reset_bars=8)]
                     if (c.kind == "drop" or (c.kind == "groove" and c.i >= 16) or (c.kind == "outro" and c.i < 8)) else [],
                     gain_db=-4.5 if tunnel else -5.0, sidechain=0.4, pan=0.15,
                     sends={"delay": 0.3, "hall": 0.15, "space": 0.1 if tunnel else 0.0})
    seq.automate("lp", journey(500, 5000) if tunnel else journey(900, 9000))

    if tunnel:
        # the tunnel: pitched noise drone on the root + fifth, slowly opening; long space reverb
        def drone_notes(c):
            if c.kind in ("groove", "drop") and c.i % 16 == 0:
                ln = min(16, c.bars_left) * 16 - 2
                return [(0, ln, key.root(3), 0.8), (0, ln, key.degree(4, 3), 0.6)]
            if c.kind == "breakdown" and c.i == 0:
                return [(0, c.section.bars * 16 - 2, key.root(3), 0.8)]
            return []

        drn = song.notes("tunnel", xt.noise_drone(q=14.0, harmonics=(1, 2, 3, 4), drift=0.15, attack=4.0, air=0.05),
                         drone_notes, gain_db=-12.0, sidechain=0.35, humanize=0.0, hp=150.0, sends={"space": 0.35})
        drn.automate("lp", journey(600, 3500))
        pad = song.notes("pad", xt.warm_pad(attack=2.0, release=2.5, cutoff=1200.0, detune=0.2, warmth=0.8),
                         lambda c: [(0, bd.bars * 16 - 2, ch_a, 0.7)] if c.kind == "breakdown" and c.i == 0 else [],
                         gain_db=-12.0, humanize=0.0, sends={"space": 0.4})
        pad.automate("lp", [(b0, 500), (b0 + bd.bars, 3000)])
    else:
        # micro: a dry, filtered 'bleep' answer every 4 bars (call & response with the stab)
        bleep = xt.glass_pluck(ratio=3.0, index=1.0, decay=0.15, release=0.2, shimmer=0.0, side=0.25)
        song.notes("bleep", bleep, lambda c: [(9, 1.0, key.degree(4, 5), 0.8), (11, 1.0, key.degree(2, 5), 0.6)]
                   if c.kind in ("groove", "drop") and c.i % 4 == 3 else [],
                   gain_db=-7.0, sends={"delay": 0.35, "reverb": 0.1})

    # ================================================================ fx
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.2})
    crash = xt.stereo_hit(drums.crash, rng, corr=0.4, decay=2.8 if tunnel else 1.6)
    for s in song.sections:
        if s.kind in ("groove", "drop", "outro"):
            fxl.add(crash, s.start_bar, gain_db=-12.0 if tunnel else -15.0)
        if s.kind == "breakdown":
            fxl.add(fx.riser(bar * s.bars, "noise", f_lo=300, f_hi=9000, rng=rng), s.end_bar, align="end",
                    gain_db=-12.0)
            fxl.add(fx.downlifter(bar * 2, rng=rng), s.start_bar, gain_db=-14.0)
            fxl.add(xt.roll_buffer(song, 4, drums.snare(tone_hz=220.0, snappy=0.9, decay=0.1, rng=rng),
                                   vel_from=0.1, vel_to=0.7, pitch_up=3.0), s.end_bar, align="end", gain_db=-14.0)
        if s.kind in ("groove", "drop"):
            for b in range(s.start_bar + 16, s.end_bar, 16):  # slow swirl every 16 bars marks the phrase
                fxl.add(fx.noise_sweep(bar * 4, up=True, q=2.0, rng=rng), b, align="end",
                        gain_db=-19.0 if tunnel else -22.0)
    fxl.add(fx.noise_sweep(bar * 8, up=True, rng=rng), g0, align="end", gain_db=-18.0)

    song.buses["drums"].eq = [("peak", 2400.0, 2.5, 0.7)]
    song.buses["music"].eq = [("peak", 380.0, -2.5, 0.9), ("peak", 1500.0, 3.0, 0.7)]
    song.master.lufs = -9.0
    if tunnel:
        song.instruments = ["deep round kick", "long sidechained rumble", "offbeat sub", "dub chords into long delays",
                            "3/16 polymetric sequence", "3/16 rim & 5/16 tick", "pitched noise tunnel drone",
                            "stereo hats, shaker & ride", "noise swirls"]
        desc = ("טכנו היפנוטי עמוק כמו מנהרה: קיק עגול עם ראמבל ארוך, סאב אופביט, אקורדי דאב שנמתחים לדיליי ארוך, "
                "סיקוונס פולימטרי של 3 נגד 4 ודרון רעש שנפתח לאט — מסע פילטר אחד ארוך מהחושך אל האור וחזרה")
    else:
        song.instruments = ["tight minimal kick", "short sub blips", "clicks in 7/16 & euclid", "3/16 rim & 5/16 tick",
                            "snap & dry clap", "lone dub stab", "blip sequence (5/16)", "bleep answers"]
        desc = ("מינימל טכנו חסכוני ו'קליקי': קיק הדוק, בליפים קצרים של סאב, קליקים פולימטריים (3, 5 ו-7 צעדים נגד ה-4/4), "
                "סטאב דאב בודד ומיקרו-וריאציות בכל תיבה — הגרוב משתנה בלי שתשימו לב")
    song.description_he = f"{desc}. {int(song.bpm)} BPM בסולם {plan['key']}, דרופ אחד בלבד אחרי ברייקדאון קצר."
    song.mix_tips_he = (song.auto_mix_tips_he() +
                        " טראק לופי שמושלם לבלנד ארוך: אפשר להחזיק את שני הטראקים יחד 32 תיבות ולשחק רק עם ה-EQ. "
                        + xt.neighbours_he(plan))
    return song
