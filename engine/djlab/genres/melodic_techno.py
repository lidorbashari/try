"""Melodic Techno recipe (122–124 BPM) — Afterlife / Anyma / Tale Of Us / Massano territory.

Long-form arrangement in 32-bar sections: drums-only intro → build (rolling arpeggiated bass + wide
arp, filter opening) → cinematic breakdown (side-chain-free pads, formant choir, the hook introduced,
pitched snare roll + riser) → drop (anthem lead hook, full arp, side-chained pads and choir) →
mirrored outro (bass out for the last 16 bars).

Harmony: emotional minor progressions, one chord per 2 bars (8-bar cycle = one DJ phrase). The lead
hook is built from a motif cell restated over every chord (voice-led on chord tones), so it is
original, singable and always consonant with the pads. Each plan id gets its own *flavor*
(progression, arp shape, lead voice, bass roll, percussion); unknown ids draw one from ``rng``.
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from .. import ext_techno as xt
from ..arrangement import Song, clip, euclid
from . import register

TEMPLATE = [
    ("Intro", "intro", 32, 4, 0),
    ("Build", "groove", 32, 6, 2),
    ("Breakdown", "breakdown", 32, 3, 0),
    ("Drop", "drop", 32, 9, 3),
    ("Outro", "outro", 32, 4, 0),
]

FLAVORS = {
    # Neon Cathedral: choir-heavy, organ-tinted pads, glassy 3-against-4 arp, slow cathedral hook
    "techno-05": dict(prog=[0, 5, 2, 6], arp="three", arp_rate=1, arp_voice="glass", lead="glass",
                      hook="cathedral", bass="roll3", organ=0.35, choir_db=-9.0, perc="tribal",
                      kick_decay=0.36, swing=50.0, hall=4.5, vowel=("a", "o"), arp_gain=-9.5,
                      desc="קתדרלה של צלילים: מקהלה סינתטית ופדים עם גוון של עוגב, ארפג'יו זכוכיתי בשלוש-נגד-ארבע "
                           "ומלודיה איטית ורחבה בדרופ"),
    # Afterglow Protocol: bright Anyma-style supersaw arp + big anthem lead
    "techno-06": dict(prog=[0, 6, 5, 6], arp="updown", arp_rate=1, arp_voice="supersaw", lead="anthem",
                      hook="anthem", bass="roll3", organ=0.0, choir_db=-12.0, perc="tight",
                      kick_decay=0.32, swing=50.0, hall=3.8, vowel=("e", "a"), arp_gain=-10.0,
                      desc="ארפג'יו סופר-סו רחב ובוהק בסגנון Anyma, ליד המנוני גדול בדרופ ופדים בסיידצ'יין"),
    # Event Horizon: darker Massano drive, galloping bass, pedal arp, rhythmic pulse hook
    "techno-07": dict(prog=[0, 3, 5, 6], arp="pedal", arp_rate=1, arp_voice="supersaw_dark", lead="anthem_dark",
                      hook="pulse", bass="gallop", organ=0.0, choir_db=-13.0, perc="driving",
                      kick_decay=0.3, swing=50.0, hall=3.5, vowel=("o", "a"), arp_gain=-9.0,
                      desc="מלודיק טכנו כהה ודוהר בסגנון Massano: באס דוהר, ארפג'יו פדאל אפל וליד ריתמי וחד בדרופ"),
    # Silent Orbit: spacey Tale-Of-Us mood, 8th-note glass arp, soft breathy lead, long delays
    "techno-08": dict(prog=[0, 5, 3, 4], arp="converge", arp_rate=2, arp_voice="glass", lead="soft",
                      hook="descend", bass="roll2", organ=0.15, choir_db=-10.0, perc="tribal",
                      kick_decay=0.34, swing=51.0, hall=5.0, vowel=("u", "a"), arp_gain=-8.5,
                      desc="מסע חללי ושקט בסגנון Tale Of Us: ארפג'יו זכוכית בשמיניות עם דיליי ארוך, ליד רך ונושם "
                           "ופדים רחבים"),
}


def _flavor(plan, rng):
    fl = FLAVORS.get(plan["id"])
    if fl is None:
        fl = dict(FLAVORS[xt.pick(rng, sorted(FLAVORS))])
        fl["prog"] = xt.pick(rng, [[0, 5, 2, 6], [0, 6, 5, 6], [0, 3, 5, 6], [0, 5, 3, 4], [0, 2, 6, 5]])
        fl["hook"] = xt.pick(rng, sorted(xt.HOOK_CELLS))
    return fl


@register("melodic_techno")
def build(plan: dict, rng: np.random.Generator) -> Song:
    fl = _flavor(plan, rng)
    song = Song(plan, rng, swing=fl["swing"])
    key = song.key
    song.arrange(TEMPLATE, song.target_bars(32))
    intro, grv, bd, drop, outro = (song.find(k) for k in ("intro", "groove", "breakdown", "drop", "outro"))
    song.mix_in_bar = grv.start_bar
    bass_off = outro.start_bar + outro.bars - 16
    sp = song.section_points
    xt.setup_space(song, hall_decay=fl["hall"], long_reverb=7.0, quarter_delay=True)

    root = key.root(1)
    while root < 30:
        root += 12
    while root > 41:
        root -= 12
    kick_hz = xt.kick_tune(key)

    prog = fl["prog"]
    arp_chords = xt.chords_for(key, prog, octave=3, size=4, center=key.root(3) + 9)
    pad_chords = xt.chords_for(key, prog, octave=3, size=3, center=key.root(4) - 3, add9=True)
    choir_chords = [sorted(c)[-3:] for c in xt.chords_for(key, prog, octave=4, size=3, center=key.root(5) - 2)]

    def chord_i(c):
        return (c.i // 2) % len(prog)

    def bass_root(d):
        n = root + key.scale[d % 7]
        return n - 12 if n > root + 7 else n

    # ================================================================ drums
    kick = drums.kick("techno", tune_hz=float(kick_hz), decay=fl["kick_decay"], click=0.45, drive=1.7, rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown":
            return None
        if c.before("breakdown", 1):
            return "x...x...x......."
        return "x...x...x...x..."

    song.hits("kick", kick, kick_pat, gain_db=-1.5, sc_source=True, humanize=0.0)

    clap = xt.stereo_variants(drums.clap, 3, rng, jitter={"tone_hz": 0.05}, corr=0.75,
                              tone_hz=float(rng.uniform(1050, 1300)), tail=float(rng.uniform(0.18, 0.24)))

    def clap_pat(c):
        if c.kind == "breakdown" or (c.kind == "intro" and c.i < 8) or (c.kind == "outro" and c.bars_left <= 8):
            return None
        return "....x.......x..." if not (c.phrase_end and c.kind in ("groove", "drop")) else "....x.......x..x"

    song.hits("clap", clap, clap_pat, gain_db=-2.5, sends={"reverb": 0.28, "hall": 0.06}, timing_ms=1.0)
    snr = drums.snare(tone_hz=float(rng.uniform(180, 210)), snappy=0.8, decay=0.14, kind="tight", rng=rng)
    song.hits("snare", snr, lambda c: "....x.......x..." if c.kind == "drop" else None, gain_db=-13.0,
              sends={"reverb": 0.2})

    hats = xt.stereo_variants(drums.hat, 4, rng, jitter={"decay": 0.15}, corr=0.5,
                              decay=float(rng.uniform(0.03, 0.045)), tone=float(rng.uniform(1.0, 1.2)))
    hat_p = {"tribal": "gogxgogxgogxgogx", "tight": "xgoxxgoxxgoxxgox", "driving": "oxoxoxoxoxoxoxox"}[fl["perc"]]

    def hat_pat(c):
        if c.kind == "breakdown" and c.bars_left > 8:
            return None
        if c.kind == "breakdown":
            return "..x...x...x...x."
        return hat_p

    song.hits("hats", hats, hat_pat, gain_db=-11.0, pan=0.15, humanize=0.1)

    ohat = xt.stereo_hit(drums.hat, rng, corr=0.5, open_=True, decay=float(rng.uniform(0.18, 0.26)), tone=1.05)
    song.hits("open_hat", ohat, lambda c: "..x...x...x...x." if (c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 16)
                                                                 or (c.kind == "outro" and c.bars_left > 8)) else None,
              gain_db=-10.5, pan=-0.12, sends={"room": 0.1})
    shk = xt.stereo_variants(drums.shaker, 3, rng, corr=0.3, length=float(rng.uniform(0.07, 0.09)))
    song.hits("shaker", shk, lambda c: "xgogxgogxgogxgog" if c.kind != "breakdown" and not (c.kind == "intro" and c.i < 8)
              and not (c.kind == "outro" and c.bars_left <= 8) else None,
              gain_db=-16.0, pan=-0.35, humanize=0.15, timing_ms=1.5)
    ride = xt.stereo_hit(drums.ride, rng, corr=0.55, decay=1.3)
    song.hits("ride", ride, lambda c: "..x...x...x...x." if c.kind == "drop" or (c.kind == "groove" and c.i >= 16) else None,
              gain_db=-14.5, pan=0.25, sends={"room": 0.1})

    # tribal / tom percussion – the Afterlife groove
    if fl["perc"] == "tribal":
        p1 = [drums.conga(float(rng.uniform(150, 180)), "open", rng=rng), drums.tom(float(rng.uniform(95, 115)), 0.35, rng=rng)]
        p2 = [drums.conga(float(rng.uniform(230, 270)), "mute", rng=rng), drums.bongo(float(rng.uniform(380, 450)), "open", rng=rng)]
        pa, pb = "...x..x....x..x.", "..x.....x.x...x."
    elif fl["perc"] == "driving":
        p1 = [drums.tom(float(rng.uniform(110, 130)), 0.25, rng=rng)]
        p2 = [drums.perc_blip(float(rng.uniform(600, 800)), 0.05, fm_index=2.0, rng=rng)]
        pa, pb = euclid(5, 16, 3), euclid(3, 16, 2)
    else:
        p1 = [drums.rimshot(float(rng.uniform(1500, 1800)), rng=rng)]
        p2 = [drums.perc_blip(float(rng.uniform(900, 1200)), 0.04, rng=rng)]
        pa, pb = "...x......x..x..", euclid(3, 8, 1) * 2

    def perc_on(c):
        return (c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 16)
                or (c.kind == "outro" and c.bars_left > 8))

    song.hits("perc_l", p1, lambda c: pa if perc_on(c) else None, gain_db=-14.0, pan=-0.6,
              sends={"room": 0.15, "delay": 0.08}, humanize=0.12)
    song.hits("perc_r", p2, lambda c: pb if perc_on(c) and c.i % 4 >= 2 else None, gain_db=-16.0, pan=0.6,
              sends={"delay8": 0.15, "room": 0.1}, humanize=0.12)
    tom = drums.tom(float(rng.uniform(80, 100)), 0.5, rng=rng)
    song.hits("tom_fill", [tom, xt.pitch_shift(tom, 5), xt.pitch_shift(tom, 7)],
              lambda c: "..........x..xx." if c.every(16) and c.kind in ("intro", "groove", "drop", "outro") else None,
              gain_db=-12.0, pan=0.2, sends={"hall": 0.15})

    # ================================================================ bass (rolling, arpeggiated on the chord roots)
    bass_i = inst.bass_pluck(cutoff=float(rng.uniform(170, 230)), env_amt=float(rng.uniform(1100, 1600)),
                             decay=float(rng.uniform(0.06, 0.085)), res=0.3, sub=0.8, drive=1.5, grit=0.22,
                             sustain=0.25, wave="saw")

    def bass_notes(c):
        if c.kind in ("intro", "breakdown") or c.bar >= bass_off:
            return []
        ev = xt.bass_roll(bass_root(prog[chord_i(c)]), fl["bass"], c.rng)
        if c.before("breakdown", 1):
            ev = [e for e in ev if e[0] < 8]
        return ev

    bass = song.notes("bass", bass_i, bass_notes, bus="bass", gain_db=-4.5, sidechain=0.75,
                      sc_release_ms=60000 / song.bpm * 0.35, humanize=0.03)
    bass.automate("lp", [(grv.start_bar, 260), (grv.start_bar + 16, 700), (grv.end_bar, 1400), (bd.start_bar, 1400),
                         (drop.start_bar, 2600), (outro.start_bar, 2600), (bass_off, 400)])
    # quiet sub under the breakdown keeps weight on club systems
    song.notes("bd_sub", inst.sub_bass(harmonics=0.08), lambda c: [(0, 31.0, bass_root(prog[chord_i(c)]), 0.7)]
               if c.kind == "breakdown" and c.i % 2 == 0 and c.i < c.section.bars - 2 else [],
               bus="bass", gain_db=-15.0, humanize=0.0)

    # ================================================================ arp
    av = fl["arp_voice"]
    if av == "glass":
        arp_inst = xt.glass_pluck(ratio=2.0, index=float(rng.uniform(1.6, 2.4)), decay=0.32, release=0.35)
    elif av == "supersaw_dark":
        arp_inst = xt.supersaw_pluck(cutoff=320.0, env_amt=2600.0, decay=0.11, sustain=0.1, release=0.15, detune=0.18)
    else:
        arp_inst = xt.supersaw_pluck(cutoff=450.0, env_amt=5200.0, decay=0.14, sustain=0.14, release=0.2, detune=0.26)
    arp_seqs = [xt.arp_seq(ch, fl["arp"], 2) for ch in arp_chords]
    rate = fl["arp_rate"]

    def arp_notes(c):
        on = (c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 24)
              or (c.kind == "breakdown" and (c.i < 8 or c.i >= 16)) or (c.kind == "outro" and c.i < 16))
        if not on:
            return []
        return xt.arp_bar(arp_seqs[chord_i(c)], c.i * 16, rate=rate, gate=0.7)

    arp = song.notes("arp", arp_inst, arp_notes, gain_db=fl["arp_gain"], sidechain=0.45, humanize=0.02, hp=180.0,
                     sends={"delay": 0.22, "hall": 0.14, "space": 0.06})
    i0, g0, b0, d0, o0 = intro.start_bar, grv.start_bar, bd.start_bar, drop.start_bar, outro.start_bar
    arp.automate("lp", [(i0 + 24, 700), (g0, 800), (g0 + 24, 3500), (g0 + 32, 5000), (b0, 1400), (b0 + 16, 900),
                        (d0 - 0.01, 9000), (d0, 7000), (o0, 6000), (o0 + 16, 500)])
    arp.automate("hp", [(i0 + 24, 1200), (g0 - 0.01, 600), (g0, 150)])
    arp.automate("gain_db", [(i0 + 24, -8.0), (g0, -3.0), (g0 + 8, 0.0), (b0, -2.0), (d0, 0.0), (o0 + 8, 0.0), (o0 + 16, -10.0)])

    # ================================================================ pads + choir
    pad = song.notes("pad", xt.warm_pad(attack=1.4, release=2.2, cutoff=2400.0, detune=0.3, organ=fl["organ"]),
                     lambda c: [(0, 31.5, pad_chords[chord_i(c)], 0.8)]
                     if c.i % 2 == 0 and (c.kind in ("breakdown", "drop") or (c.kind == "groove" and c.i >= 16)
                                          or (c.kind == "outro" and c.i < 8)) else [],
                     gain_db=-12.5, sidechain=0.55, humanize=0.0, hp=150.0,
                     sends={"hall": 0.25, "space": 0.2})
    pad.automate("gain_db", sp({"groove": -7.0, "breakdown": 0.0, "drop": -3.5, "outro": -6.0}, -6.0, ramp_bars=2))
    pad.automate("lp", [(g0 + 16, 900), (g0 + 32, 2500), (b0, 1200), (b0 + 24, 5000), (d0, 3500), (o0 + 8, 900)])

    choir_i = xt.choir(vowel=fl["vowel"][0], vowel_to=fl["vowel"][1], shift=float(rng.uniform(1.0, 1.1)),
                       attack=0.9, release=1.6)
    ch = song.notes("choir", choir_i, lambda c: [(0, 31.0, choir_chords[chord_i(c)], 0.8)]
                    if c.i % 2 == 0 and ((c.kind == "breakdown" and c.i >= 4 and c.bars_left > 2) or (c.kind == "drop" and c.i >= 16))
                    else [], bus="vox", gain_db=fl["choir_db"], sidechain=0.3, humanize=0.0,
                    sends={"space": 0.35, "hall": 0.15})
    ch.automate("gain_db", sp({"breakdown": 0.0, "drop": -4.0}, -4.0, ramp_bars=1))

    # ================================================================ lead hook
    hook = xt.hook_events(key, prog, fl["hook"], octave=4)
    hclip = clip(hook, 8)
    lv = fl["lead"]
    if lv == "glass":
        lead_inst = xt.glass_pluck(ratio=3.0, index=1.6, decay=0.9, release=0.8, shimmer=0.15)
        lead_db = -6.0
    elif lv == "soft":
        lead_inst = xt.soft_lead(vib=0.2, release=0.6, bright=0.45)
        lead_db = -7.0
    elif lv == "anthem_dark":
        lead_inst = xt.anthem_lead(detune=0.14, bright=0.55, vib=0.1, octave_up=0.1, sub=0.3, release=0.3)
        lead_db = -8.0
    else:
        lead_inst = xt.anthem_lead(detune=0.22, bright=0.85, vib=0.15, octave_up=0.22, sub=0.22)
        lead_db = -8.0

    def lead_notes(c):
        if c.kind == "drop" or (c.kind == "breakdown" and 8 <= c.i < c.section.bars - 1):
            return hclip(c)
        return []

    lead = song.notes("lead", lead_inst, lead_notes, gain_db=lead_db - 3.0, sidechain=0.3, humanize=0.03,
                      sends={"delay4": 0.18, "delay": 0.12, "hall": 0.2, "space": 0.12})
    lead.automate("gain_db", [(b0 + 8, -7.0), (b0 + 24, -3.0), (d0 - 0.01, -1.0), (d0, 0.0)])
    lead.automate("lp", [(b0 + 8, 1500), (b0 + 24, 3000), (d0 - 0.01, 9000), (d0, 14000)])
    # octave-up glass double on the second half of the drop (lift without new material)
    dbl = xt.glass_pluck(ratio=2.0, index=1.2, decay=0.6, release=0.5, shimmer=0.1)
    song.notes("lead_hi", dbl, lambda c: hclip(c) if c.kind == "drop" and c.i >= 16 else [], transpose=12,
               gain_db=-16.0, sidechain=0.3, humanize=0.0, sends={"delay": 0.25, "space": 0.15})

    # ================================================================ fx / transitions
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.12})
    crash = xt.stereo_hit(drums.crash, rng, corr=0.4, decay=2.6)
    bar = song.grid.bar_sec
    for s in song.sections:
        if s.kind in ("groove", "drop", "outro"):
            fxl.add(crash, s.start_bar, gain_db=-10.0)
        if s.kind == "drop":
            fxl.add(fx.impact(3.5, rng=rng), s.start_bar, gain_db=-8.0)
            for b in range(s.start_bar + 16, s.end_bar, 16):
                fxl.add(crash, b, gain_db=-13.0)
                fxl.add(fx.noise_sweep(bar * 2, up=True, rng=rng), b, align="end", gain_db=-20.0)
        if s.kind == "breakdown":
            fxl.add(fx.downlifter(bar * 4, rng=rng), s.start_bar, gain_db=-12.0)
            fxl.add(fx.riser(bar * 8, "noise", f_lo=250, f_hi=11000, rng=rng), s.end_bar, align="end", gain_db=-10.0)
            fxl.add(fx.reverse_cymbal(bar * 1, rng=rng), s.end_bar, align="end", gain_db=-11.0)
            roll = xt.roll_buffer(song, 8, drums.snare(tone_hz=210.0, snappy=0.85, decay=0.12, rng=rng),
                                  vel_from=0.15, vel_to=0.9, pitch_up=7.0)
            fxl.add(roll, s.end_bar, align="end", gain_db=-12.0)
    fxl.add(fx.noise_sweep(bar * 8, up=True, rng=rng), g0, align="end", gain_db=-18.0)
    fxl.add(fx.reverse_cymbal(bar * 2, rng=rng), g0, align="end", gain_db=-13.0)
    fxl.add(fx.downlifter(bar * 4, rng=rng), o0, gain_db=-14.0)

    # ================================================================ mix
    song.buses["drums"].eq = [("peak", 3200.0, 1.0, 0.8), ("peak", 350.0, -1.5, 1.0)]
    song.buses["music"].eq = [("peak", 380.0, -2.5, 0.8)]
    song.buses["vox"].hp = 250.0
    song.master.lufs = -9.0
    song.instruments = ["tight tuned techno kick", "rolling arpeggiated bass", "wide arpeggio", "anthem lead hook",
                        "side-chained pads", "formant choir", "clap & plate snare", "stereo hats, shaker & ride",
                        "tribal toms & percussion", "riser, pitched snare roll & impact"]
    nm = plan["key"]
    song.description_he = (f"מלודיק טכנו ב-{int(song.bpm)} BPM בסולם {nm}: {fl['desc']}. "
                           f"מבנה ארוך של 32 תיבות לכל חלק — ברייקדאון קולנועי עם מקהלה ומתח שנבנה לדרופ גדול.")
    song.mix_tips_he = (song.auto_mix_tips_he() +
                        f" הארפג'יו מתחיל לרמוז כבר בתיבה {i0 + 25} (מסונן) — אפשר להתחיל להכניס אז את ה-Mid. "
                        f"הבאס יוצא בתיבה {bass_off + 1}, כך ש-16 התיבות האחרונות הן תופים בלבד — חלון מושלם ל-Bass Swap.")
    return song
