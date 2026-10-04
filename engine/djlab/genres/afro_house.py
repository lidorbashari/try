"""Afro House recipe (118–124 BPM).

Organic percussion first: a deep round kick, 16th shakers + shekere, three congas (tumba / conga /
quinto slaps) in interlocking 2-bar patterns, martillo bongos, the West-African 12/8 bell pattern
on a woodblock (8th-note triplets against straight 16ths = the 3-against-4 pull), 3-2 clave, djembe
bass/tone/slap, tribal toms and (desert flavor) a talking drum. On top: a deep rolling diatonic bass
that follows the chords, kalimba / marimba / Karplus-Strong plucked ostinatos (one in dotted 8ths
for a hemiola), haunting filtered pads, chant-like vowel voices and — in the peak flavor — a big
saw lead. The breakdown is "spiritual": kick and bass out, pads + chants + hand drums, a tom roll
and riser back into the drop.

Flavors (``STYLE_BY_ID``, or ``plan["style"]``):
* ``desert``  — harmonic-minor colour (raised 7th), heavy toms + talking drum, kora-like pluck +
                marimba, low chant.
* ``kalimba`` — softer warm-up: lighter hand drums, kalimba lead, dreamy i–VII–VI–VII pads,
                airy "ooh" voices, gentle riser.
* ``spirit``  — peak time: full percussion, djembe, toms, marimba ostinato and a big detuned saw lead
                in the drop, call-and-response chants.

DJ rules: 32-bar intro of drums/percussion only (bass + tonal parts enter at bar 33 = Hot Cue B),
32-bar outro whose last 16 bars are percussion only, every section on 8-bar phrases, fills/crashes
on phrase boundaries.
"""
from __future__ import annotations

import numpy as np

from .. import drums, ext_house as eh, fx, instruments as inst
from ..arrangement import Song, clip
from ..theory import Key
from . import register

STYLE_BY_ID = {"house-09": "desert", "house-10": "kalimba", "house-11": "spirit"}
STYLES = ("desert", "kalimba", "spirit")

TEMPLATE = [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 32, 6, 2), ("Breakdown", "breakdown", 16, 3, 0),
            ("Drop", "drop", 32, 8, 3), ("Outro", "outro", 32, 4, 0)]

PROGRESSIONS = {  # scale degrees, one chord per 2 bars
    "desert": [[0, 3, 0, 4], [0, 5, 3, 4], [0, 0, 5, 4]],
    "kalimba": [[0, 6, 5, 6], [0, 5, 6, 0], [0, 3, 6, 5]],
    "spirit": [[0, 5, 6, 0], [0, 5, 2, 6], [0, 6, 5, 4]],
}

# --- percussion (16 steps unless noted). Interlocking 2-bar conga parts.
CONGA_LO = [["......x.......x.", "......x...x...x."], ["...x......x.....", "...x......x...x."]]
CONGA_MID = [["..xx......xx....", "..xx....x.xx...."], [".x...x.x.x...x..", ".x...x.x.x..xx.."]]
CONGA_HI = [["....x.......x...", "....x.......x.x."], ["x.....x.....x...", "x.....x...x.x..."]]
BONGO = ["x.xxx.xxx.xxx.xx", "xgxoxgxoxgxoxgxo", "x.xgx.xgx.xgx.xx"]
BELL_12 = "x.x.xx.x.x.x"            # 12/8 standard bell over a 4/4 bar (8th triplets)
CLAVE_32 = ["x..x..x.........", "....x...x......."]   # 3-2 son clave
SHAKER = ["gxgogxgogxgogxgo", "oxgxoxgxoxgxoxgx"]
SHEKERE = "..x...x...x...x."
DJEMBE = [("x.........x.....", "......x.......x.", "...x......x..x.."),   # (bass, tone, slap)
          ("x.....x.........", "...x......x.x...", ".......x......x.")]
TOMS = ["......x..x....x.", "...x......x...x.", "..........x.x.x."]
TOM_FILL = "........x.x.xxxx"
TALKING = ["...........x..x.", "......x.......x.", "...x..........x."]

# --- bass: (step, len, scale-steps from the chord degree, vel) over 2 bars
BASS_RIFFS = [
    [(2, 2, 0, 1.0), (6, 1, 0, 0.7), (7, 2, 0, 0.9), (10, 2, 0, 1.0), (14, 1, 4, 0.8), (15, 1, 0, 0.7),
     (18, 2, 0, 1.0), (22, 1, 0, 0.7), (23, 2, 0, 0.9), (26, 2, 7, 0.9), (29, 1, 4, 0.8), (30, 2, 6, 0.8)],
    [(0, 3, 0, 1.0), (3, 3, 0, 0.8), (6, 2, 4, 0.9), (10, 2, 0, 1.0), (13, 3, 2, 0.8),
     (16, 3, 0, 1.0), (19, 3, 0, 0.8), (22, 2, 4, 0.9), (26, 2, 7, 0.9), (29, 3, 6, 0.8)],   # tresillo roll
    [(2, 1.5, 0, 1.0), (4, 1, 0, 0.6), (6, 2, 0, 0.9), (10, 1.5, 0, 1.0), (11, 1, 7, 0.7), (14, 2, 4, 0.9),
     (18, 1.5, 0, 1.0), (20, 1, 0, 0.6), (22, 2, 0, 0.9), (26, 1.5, 2, 1.0), (28, 1, 4, 0.8), (30, 2, -1, 0.8)],
]

# --- melodic motifs (2 bars): (step, len, scale degree, vel); degrees ≥7 = next octave
MOTIFS = [
    [(0, 2, 7, 0.9), (3, 1, 4, 0.7), (6, 2, 6, 0.8), (8, 1, 4, 0.7), (10, 2, 2, 0.8), (14, 2, 4, 0.7),
     (16, 2, 7, 0.9), (19, 1, 4, 0.7), (22, 2, 6, 0.8), (24, 1, 9, 0.8), (26, 2, 7, 0.8), (30, 2, 4, 0.7)],
    [(0, 1, 4, 0.9), (2, 1, 7, 0.7), (4, 1, 6, 0.8), (6, 1, 4, 0.7), (9, 1, 2, 0.8), (11, 1, 4, 0.7), (14, 2, 0, 0.8),
     (16, 1, 4, 0.9), (18, 1, 7, 0.7), (20, 1, 9, 0.8), (22, 1, 7, 0.7), (25, 1, 6, 0.8), (27, 1, 4, 0.7),
     (30, 2, 2, 0.8)],
    # dotted-8th hemiola (3 against 4) across two bars
    [(0, 2, 7, 0.95), (3, 2, 4, 0.75), (6, 2, 6, 0.8), (9, 2, 4, 0.75), (12, 2, 9, 0.85), (15, 2, 7, 0.75),
     (18, 2, 4, 0.8), (21, 2, 6, 0.75), (24, 2, 7, 0.9), (27, 2, 4, 0.75), (30, 2, 2, 0.8)],
]
COUNTER = [  # sparser second voice (marimba / pluck), answers the motif
    [(4, 2, 2, 0.8), (7, 1, 4, 0.7), (12, 3, 0, 0.8), (20, 2, 4, 0.8), (23, 1, 6, 0.7), (28, 3, 4, 0.8)],
    [(2, 1, 4, 0.8), (5, 1, 2, 0.7), (8, 2, 0, 0.8), (18, 1, 4, 0.8), (21, 1, 6, 0.7), (24, 4, 4, 0.8)],
]
LEAD = [  # 4 bars (64 steps), big peak-time hook
    [(0, 3, 9, 1.0), (3, 3, 7, 0.85), (6, 2, 6, 0.8), (8, 6, 7, 0.95), (16, 3, 4, 0.9), (19, 3, 6, 0.85),
     (22, 2, 4, 0.8), (24, 7, 2, 0.9), (32, 3, 9, 1.0), (35, 3, 7, 0.85), (38, 2, 6, 0.8), (40, 6, 7, 0.95),
     (46, 2, 9, 0.85), (48, 3, 10, 0.95), (51, 3, 9, 0.85), (54, 2, 7, 0.8), (56, 7, 6, 0.9)],
    [(0, 6, 7, 1.0), (6, 2, 9, 0.85), (8, 4, 10, 0.9), (12, 4, 9, 0.8), (16, 8, 7, 0.95), (26, 2, 6, 0.8),
     (28, 4, 4, 0.85), (32, 6, 7, 1.0), (38, 2, 9, 0.85), (40, 4, 11, 0.95), (44, 4, 10, 0.85),
     (48, 6, 9, 0.9), (54, 2, 7, 0.8), (56, 7, 6, 0.9)],
]
CHANTS = [  # 4 bars: call (low voice) — degrees in octave 3
    [(0, 6, 4, 0.9), (8, 3, 6, 0.8), (12, 4, 7, 0.9), (32, 6, 4, 0.9), (40, 8, 2, 0.85)],
    [(2, 4, 7, 0.9), (8, 2, 6, 0.8), (10, 6, 4, 0.85), (34, 4, 7, 0.9), (40, 3, 9, 0.85), (44, 8, 7, 0.85)],
]
RESPONSE = [(18, 3, 9, 0.8), (22, 6, 7, 0.75), (50, 3, 9, 0.8), (54, 8, 11, 0.75)]


@register("afro_house")
def build(plan: dict, rng: np.random.Generator) -> Song:
    style = plan.get("style") or STYLE_BY_ID.get(plan.get("id", ""))
    if style not in STYLES:
        style = str(np.random.default_rng(int(plan.get("seed", 0)) + 101).choice(list(STYLES)))
    sw = {"desert": (53.0, 55.0), "kalimba": (52.0, 54.0), "spirit": (54.0, 56.0)}[style]
    song = Song(plan, rng, swing=float(rng.uniform(*sw)),
                scale="harmonic_minor" if style == "desert" and "minor" in plan["key"] else None)
    key: Key = song.key
    song.arrange(TEMPLATE, song.target_bars())
    groove = song.bar("groove")
    song.mix_in_bar = groove
    outro = song.find("outro")
    bd = song.find("breakdown")
    drop = song.bar("drop")
    bass_off = outro.start_bar + outro.bars - 16
    soft = style == "kalimba"

    def music_on(c):
        return c.kind not in ("intro",) and c.bar < bass_off

    # ================================================================ drums & hand percussion
    kick_s = drums.kick("deep" if soft else "house", tune_hz=eh.kick_tune(key, 46, 60),
                        decay=float(rng.uniform(0.36, 0.42)), click=float(rng.uniform(0.25, 0.4)),
                        drive=float(rng.uniform(1.1, 1.4)), rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown" or c.before("drop", 1):
            return None
        if c.before("breakdown", 1):
            return "x...x...x......."
        return "x...x...x...x..."

    song.hits("kick", kick_s, kick_pat, gain_db=-2.0, sc_source=True, humanize=0.0)

    clap = drums.variants(eh.soft_clap, 3, rng, jitter={"tone_hz": 0.06}, tone_hz=float(rng.uniform(1000, 1250)),
                          tail=float(rng.uniform(0.18, 0.26)))
    song.hits("clap", clap, lambda c: ("....x.......x..." if not c.phrase_end else "....x.......x.x.")
              if (c.kind in ("groove", "drop", "outro") or (c.kind == "intro" and c.i >= 8))
              and not (c.kind == "outro" and c.bars_left <= 4) else None,
              gain_db=-6.5 if not soft else -8.0, sends={"reverb": 0.25, "room": 0.15}, timing_ms=2.0)

    shk = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=float(rng.uniform(0.07, 0.1)),
                         tone=float(rng.uniform(5800, 6800)))
    sh_p = SHAKER[int(rng.integers(len(SHAKER)))]
    song.hits("shaker", shk, lambda c: sh_p if not (c.kind == "breakdown" and c.i < 4) else None,
              gain_db=-13.0, pan=-0.45, humanize=0.15, timing_ms=2.5)
    shek = drums.variants(eh.shekere, 3, rng, jitter={"length": 0.15}, length=float(rng.uniform(0.1, 0.14)))
    song.hits("shekere", shek, lambda c: SHEKERE if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 16)
              or (c.kind == "outro" and c.bars_left > 8) else None, gain_db=-16.0, pan=0.5, humanize=0.15,
              timing_ms=3.0)

    hats = drums.variants(drums.hat, 3, rng, jitter={"decay": 0.2}, decay=float(rng.uniform(0.025, 0.04)),
                          tone=float(rng.uniform(0.9, 1.05)))
    def hat_pat(c):
        if not (c.kind in ("groove", "drop", "outro") or (c.kind == "intro" and c.i >= 4)):
            return None
        return "..x...x...x...x." if c.i % 2 == 0 else "..x...x...x.x.x."

    song.hits("hats", hats, hat_pat, gain_db=-14.0, pan=0.25)
    ohat = drums.hat(open_=True, decay=float(rng.uniform(0.18, 0.26)), tone=0.95, rng=rng)
    song.hits("open_hat", ohat, lambda c: "..x...x...x...x." if c.kind == "drop" or (c.kind == "groove" and c.i >= 8)
              or (c.kind == "intro" and c.i >= 24) else None, gain_db=-12.5 if not soft else -14.5, pan=-0.2,
              sends={"room": 0.1})

    # three congas, interlocking 2-bar parts
    ci = int(rng.integers(len(CONGA_LO)))
    p_lo, p_mid, p_hi = CONGA_LO[ci], CONGA_MID[int(rng.integers(len(CONGA_MID)))], CONGA_HI[ci]
    base = float(rng.uniform(170, 195))
    c_lo = [drums.conga(base, "open", rng=rng), drums.conga(base * 1.01, "open", rng=rng)]
    c_mid = [drums.conga(base * 1.32, "open", rng=rng), drums.conga(base * 1.33, "mute", rng=rng)]
    c_hi = [drums.conga(base * 1.75, "slap", rng=rng), drums.conga(base * 1.76, "slap", rng=rng)]
    conga_gain = -11.0 if not soft else -13.0

    def conga_when(c, start=8):
        if c.kind == "intro":
            return c.i >= start
        if c.kind == "outro":
            return c.bars_left > 4
        return True

    song.hits("conga_lo", c_lo, lambda c: p_lo if conga_when(c, 8) else None, gain_db=conga_gain, pan=-0.35,
              humanize=0.1, timing_ms=3.0, sends={"room": 0.15})
    song.hits("conga_mid", c_mid, lambda c: p_mid if conga_when(c, 12) else None, gain_db=conga_gain - 1, pan=-0.15,
              humanize=0.12, timing_ms=3.0, sends={"room": 0.15})
    song.hits("conga_hi", c_hi, lambda c: p_hi if conga_when(c, 16) and c.kind != "breakdown" else None,
              gain_db=conga_gain - 2, pan=0.3, humanize=0.12, timing_ms=2.5, sends={"room": 0.15})

    bongo_p = BONGO[int(rng.integers(len(BONGO)))]
    bongos = [drums.bongo(float(rng.uniform(470, 520)), "open", rng=rng),
              drums.bongo(float(rng.uniform(620, 680)), "mute", rng=rng)]
    song.hits("bongo", bongos, lambda c: bongo_p if (c.kind == "drop" or (c.kind == "groove" and c.i % 8 >= 4)
                                                      or (c.kind == "intro" and c.i >= 20)) else None,
              gain_db=-16.5 if not soft else -18.5, pan=0.55, humanize=0.18, timing_ms=2.5, sends={"room": 0.12})

    bell = eh.woodblock(float(rng.uniform(780, 900)), 0.035, rng=rng)
    song.hits("bell_12_8", bell, lambda c: BELL_12 if (c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 16)
                                                      or (c.kind == "outro" and c.bars_left > 8)) else None,
              gain_db=-17.0 if not soft else -19.0, pan=-0.6, humanize=0.1, sends={"delay8": 0.08, "room": 0.1})
    clv = eh.clave(float(rng.uniform(2300, 2700)), rng=rng)
    song.hits("clave", clv, lambda c: CLAVE_32 if c.kind in ("drop", "breakdown") or (c.kind == "groove" and c.i >= 16)
              else None, gain_db=-19.0, pan=0.45, sends={"reverb": 0.12})

    if style != "kalimba":
        dj = DJEMBE[int(rng.integers(len(DJEMBE)))]
        dj_s = {"bass": eh.djembe("bass", float(rng.uniform(72, 84)), rng=rng),
                "tone": eh.djembe("tone", float(rng.uniform(310, 350)), rng=rng),
                "slap": eh.djembe("slap", float(rng.uniform(400, 440)), rng=rng)}
        def dj_pat(p, stroke):
            def f(c):
                if c.kind == "drop" or (c.kind == "groove" and c.i >= 16) or (c.kind == "breakdown" and stroke != "bass"):
                    return p
                return None
            return f

        for nm, pat in zip(("bass", "tone", "slap"), dj):
            song.hits(f"djembe_{nm}", dj_s[nm], dj_pat(pat, nm),
                      gain_db=-13.0 if nm != "bass" else -11.0, pan=-0.1 if nm == "bass" else 0.15,
                      humanize=0.12, timing_ms=3.0, sends={"room": 0.15})

    tom_kit = [drums.tom(float(rng.uniform(85, 100)), 0.45, rng=rng), drums.tom(float(rng.uniform(120, 140)), 0.4, rng=rng),
               drums.tom(float(rng.uniform(160, 185)), 0.35, rng=rng)]
    tom_p = TOMS[int(rng.integers(len(TOMS)))]

    def tom_pat(c):
        if c.kind == "breakdown" and c.bars_left <= 2:
            return ["x.x.x.x.x.x.x.x.", "xxxxxxxxrrrrrrrr"][2 - c.bars_left]
        if c.phrase_end and c.kind in ("groove", "drop") or (c.kind == "intro" and c.last):
            return TOM_FILL
        if style != "kalimba" and (c.kind == "drop" or (c.kind == "intro" and c.i >= 24 and c.i % 2 == 1)):
            return tom_p
        return None

    song.hits("toms", tom_kit, tom_pat, gain_db=-11.5 if not soft else -14.0, pan=0.1, humanize=0.1,
              sends={"reverb": 0.12, "room": 0.15})
    if style == "desert":
        td = [eh.talking_drum(float(rng.uniform(150, 175)), float(rng.uniform(4, 6)), rng=rng),
              eh.talking_drum(float(rng.uniform(200, 230)), float(rng.uniform(3, 5)), rng=rng)]
        tk = TALKING[int(rng.integers(len(TALKING)))]
        song.hits("talking_drum", td, lambda c: tk if c.kind in ("groove", "drop", "breakdown") and c.i % 2 == 1
                  else None, gain_db=-12.0, pan=-0.4, sends={"room": 0.2, "delay8": 0.1}, humanize=0.1)

    # ================================================================ harmony & bass
    prog = PROGRESSIONS[style][int(rng.integers(len(PROGRESSIONS[style])))]
    root = eh.bass_root(key, 28)

    def chord_deg(c):
        return prog[(c.i // 2) % len(prog)]

    def bass_note(deg_):
        n = key.degree(deg_, 1)
        while n < root - 2:
            n += 12
        while n > root + 14:
            n -= 12
        return n

    riff = BASS_RIFFS[int(rng.integers(len(BASS_RIFFS)))]

    def bass_notes(c):
        if c.kind in ("intro", "breakdown") or c.bar >= bass_off:
            return []
        cd = chord_deg(c)
        off = (c.i % 2) * 16
        ev = [(s - off, l, bass_note(cd + st), v) for s, l, st, v in riff if off <= s < off + 16]
        if c.before("drop", 1) or c.before("breakdown", 1):
            ev = [e for e in ev if e[0] < 8]
        return ev

    bass_inst = eh.deep_bass(cutoff=float(rng.uniform(220, 300)), sub=0.9, drive=float(rng.uniform(1.2, 1.6)),
                             decay=0.3, sustain=0.75)
    bass = song.notes("bass", bass_inst, bass_notes, bus="bass", gain_db=-4.0, sidechain=0.5, sc_release_ms=150.0,
                      humanize=0.03)
    bass.automate("lp", [(groove, 400), (groove + 8, 1500), (drop, 3000), (outro.start_bar, 3000), (bass_off, 400)])
    song.notes("bd_sub", inst.sub_bass(), lambda c: [(0, 63.5, bass_note(chord_deg(c)), 0.6)]
               if c.kind == "breakdown" and c.i % 4 == 0 and c.bars_left > 4 else [], bus="bass", gain_db=-14.0)

    chords = {d: eh.voice_progression(key, [d], [4], center=60, rootless=False)[0] for d in set(prog)}
    pad_inst = eh.soft_pad(attack=float(rng.uniform(1.2, 2.0)), release=2.5, cutoff=float(rng.uniform(1300, 1900)),
                           air=0.3)

    def pad_notes(c):
        if not music_on(c) and c.kind != "breakdown":
            return []
        if c.i % 2 == 0:
            return [(0, 31.0, chords[chord_deg(c)], 0.8)]
        return []

    pad = song.notes("pad", pad_inst, pad_notes, gain_db=-12.0, sends={"hall": 0.35}, width=0.85, sidechain=0.35,
                     hp=180.0)
    pad.automate("gain_db", song.section_points({"groove": -4.0, "breakdown": 2.0, "drop": -2.0, "outro": -5.0}, -60.0,
                                                ramp_bars=2))
    pad.automate("lp", [(groove, 700), (bd.start_bar, 1200), (bd.end_bar - 0.01, 6000), (drop, 3000),
                        (outro.start_bar, 2500), (bass_off, 600)])

    # ================================================================ melodies
    deg = key.degree
    motif = MOTIFS[int(rng.integers(len(MOTIFS)))] if style != "kalimba" else MOTIFS[int(rng.integers(2))]
    motif_oct = 4 if style != "kalimba" else 5
    mclip = clip([(s, l, deg(d, motif_oct), v) for s, l, d, v in motif], 2)
    if style == "kalimba":
        lead_inst, lead_name, lead_gain = eh.kalimba(bright=0.6, decay=1.0), "kalimba", -11.0
    elif style == "desert":
        lead_inst, lead_name, lead_gain = eh.pluck_lead(bright=0.75, decay=0.996, body=0.35), "kora_pluck", -10.0
    else:
        lead_inst, lead_name, lead_gain = eh.marimba(decay=0.5), "marimba", -10.0

    def motif_notes(c):
        if c.kind == "groove":
            return mclip(c) if c.i >= 8 else []
        if c.kind == "breakdown":
            return mclip(c) if (soft or c.i >= 8) else []
        if c.kind == "drop":
            return mclip(c)
        if c.kind == "outro" and c.bar < bass_off:
            return mclip(c) if c.i < 8 else []
        return []

    ml = song.notes(lead_name, lead_inst, motif_notes, gain_db=lead_gain, sidechain=0.3, pan=0.15,
                    sends={"delay": 0.22, "reverb": 0.18}, humanize=0.08)
    ml.automate("lp", [(groove + 8, 1500), (groove + 24, 6000), (outro.start_bar, 6000), (outro.start_bar + 8, 1200)])

    counter = COUNTER[int(rng.integers(len(COUNTER)))]
    cclip = clip([(s, l, deg(d, 4 if style != "spirit" else 5), v) for s, l, d, v in counter], 2)
    sec_inst = {"desert": eh.marimba(decay=0.4), "kalimba": eh.pluck_lead(bright=0.55, body=0.2),
                "spirit": eh.kalimba(bright=0.6)}[style]
    song.notes("counter", sec_inst, lambda c: cclip(c) if c.kind == "drop" or (c.kind == "breakdown" and c.i >= 8)
               else [], gain_db=-11.0, pan=-0.35, sidechain=0.3, sends={"delay8": 0.18, "reverb": 0.2})

    if style == "spirit":
        lead = LEAD[int(rng.integers(len(LEAD)))]
        lclip = clip([(s, l, deg(d, 4), v) for s, l, d, v in lead], 4)
        big = eh.synth_lead(detune_cents=float(rng.uniform(10, 16)), cutoff=float(rng.uniform(2600, 3400)),
                            res=0.2, vibrato=0.15)
        ld = song.notes("lead", big, lambda c: lclip(c) if c.kind == "drop" else [], gain_db=-9.0, sidechain=0.45,
                        sends={"delay": 0.25, "hall": 0.2}, width=0.9)
        ld.automate("lp", [(drop, 2500), (drop + 8, 9000)])

    # chants: call (low ensemble voice) + response (higher voice)
    ch = CHANTS[int(rng.integers(len(CHANTS)))]
    chant_lo = eh.chant(vowel="o", vowel_to="a", shift=0.92 if style != "kalimba" else 1.0, voices=3,
                        vibrato=0.3, breath=0.12, attack=0.06)
    cl = clip([(s, l, deg(d, 3), v) for s, l, d, v in ch], 4)

    def chant_notes(c):
        if c.kind == "breakdown":
            return cl(c)
        if c.kind == "drop":
            return cl(c) if c.phrase % 2 == 0 else []
        if c.kind == "groove":
            return cl(c) if c.i >= c.section.bars - 8 else []
        return []

    song.notes("chant", chant_lo, chant_notes, bus="vox", gain_db=-8.0, sidechain=0.3,
               sends={"hall": 0.4, "delay": 0.18}, width=1.3)
    resp = eh.chant(vowel="u" if soft else "e", vowel_to="a", shift=1.18, voices=2, vibrato=0.4, breath=0.15,
                    attack=0.05)
    rclip = clip([(s, l, deg(d, 4), v) for s, l, d, v in RESPONSE], 4)
    song.notes("chant_resp", resp, lambda c: rclip(c) if c.kind == "breakdown" or (c.kind == "drop" and c.phrase % 2 == 1)
               else [], bus="vox", gain_db=-10.0, sidechain=0.3, sends={"hall": 0.45, "delay": 0.25}, pan=0.2)

    # ================================================================ fx & mix
    eh.transitions(song, rng, crash_db=-10.0, impact_db=-10.0 if not soft else -14.0,
                   riser_db=-10.0 if not soft else -13.0, riser_kind="noise" if soft else "both")
    song.returns["hall"].decay = 3.6
    song.returns["reverb"].decay = 2.2
    song.buses["drums"].eq = [("peak", 2400.0, 1.5, 0.8), ("highshelf", 9000.0, 1.5, 0.7)]
    song.buses["drums"].width = 1.2
    song.buses["music"].eq = [("peak", 380.0, -2.5, 0.8), ("highshelf", 7000.0, 1.5, 0.7)]
    song.master.lufs = -9.0

    # ================================================================ metadata
    k = plan["key"]
    if style == "desert":
        song.description_he = (f"אפרו-האוס מדברי ב-{int(song.bpm)} BPM בסולם {k} (צבע של מינור הרמוני): קונגות, ג'מבה, "
                               f"תופים מדברים וטומים שבטיים מעל באס עמוק ומתגלגל, פריטה דמוית קורה ומרימבה, "
                               f"וקריאות ווקאליות נמוכות בברייקדאון רוחני.")
        song.instruments = ["deep round kick", "congas ×3", "bongos", "12/8 bell (woodblock)", "3-2 clave", "djembe",
                            "tribal toms", "talking drum", "shaker + shekere", "rolling deep bass",
                            "kora-like Karplus-Strong pluck", "marimba", "haunting pad", "chant voices"]
    elif style == "kalimba":
        song.description_he = (f"אפרו-האוס רך ומהפנט ב-{int(song.bpm)} BPM בסולם {k}: קלימבה מנגנת מוטיב חוזר מעל "
                               f"קונגות ושייקרים, פדים חמים ו\"אוו\" ווקאלי אוורירי. מושלם לחימום רחבה בשעות "
                               f"המוקדמות.")
        song.instruments = ["deep kick", "congas ×3", "bongos", "12/8 bell (woodblock)", "3-2 clave", "shaker + shekere",
                            "soft clap", "rolling deep bass", "kalimba", "plucked counter-melody", "warm pad",
                            "airy chant voices"]
    else:
        song.description_he = (f"אפרו-האוס לשעת שיא ב-{int(song.bpm)} BPM בסולם {k}: פרקשן אורגני מלא — קונגות, ג'מבה, "
                               f"בונגוס וטומים — באס מתגלגל, מרימבה בפולי-ריתמוס, ובדרופ ליד סינתי גדול עם צ'אנטים "
                               f"של שאלה-תשובה.")
        song.instruments = ["house kick", "congas ×3", "bongos", "12/8 bell (woodblock)", "3-2 clave", "djembe",
                            "tribal toms", "shaker + shekere", "rolling deep bass", "marimba ostinato", "kalimba",
                            "big detuned saw lead", "pad", "call-and-response chants"]
    song.mix_tips_he = (song.auto_mix_tips_he() + " בברייקדאון נשארים רק כלי הקשה, פדים וצ'אנטים — מקום טבעי "
                        "להכניס את הטראק הבא עם הקונגות שלו.")
    return song
