"""Trance recipe (128–140 BPM): uplifting (default) and progressive (plan ``genre`` contains
"Progressive").

Uplifting: punchy kick, rolling off-beat bass that follows the chords, plucked 16th arpeggios, a big
supersaw anthem lead (written from chord tones, original hooks), a long emotional breakdown with
pads and piano chords + piano melody, snare-roll build with riser, euphoric drop (impact, crash, lead
+ arp + pads). Progressive: rolling arp-driven groove, subtle pluck/bell lead, trance-gated pad,
longer filter journeys, smaller breakdown.

DJ rules: 32-bar intro (drums only for 16 bars, bass enters on bar 17), 32-bar outro (bass out for
the last 16), every section on the 8-bar grid, crash every 8 bars in drops.
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from .. import ext_breadth as xb
from ..arrangement import Song
from ..theory import voice_lead
from . import register

UPLIFT = [("Intro", "intro", 32, 5, 0), ("Groove", "groove", 32, 7, 1), ("Breakdown", "breakdown", 32, 4, 0),
          ("Drop", "drop", 32, 9, 2), ("Outro", "outro", 32, 5, 0)]
PROG = [("Intro", "intro", 32, 5, 0), ("Groove", "groove", 32, 7, 1), ("Breakdown", "breakdown", 24, 5, 0),
        ("Drop", "drop", 32, 8, 2), ("Outro", "outro", 32, 5, 0)]

PROGRESSIONS_UP = [[0, 5, 2, 6], [5, 6, 0, 0], [0, 5, 3, 6], [5, 2, 6, 0]]
PROGRESSIONS_PROG = [[0, 5, 2, 6], [0, 3, 5, 4], [0, 0, 5, 6], [0, 6, 5, 6]]

# Original hooks over a 2-bar chord: (step, len, chord-tone index in the lead register)
HOOKS = [
    [[(0, 3, 2), (3, 3, 1), (6, 2, 0), (8, 3, 1), (11, 3, 2), (14, 2, 3), (16, 3, 2), (19, 3, 1), (22, 2, 0),
      (24, 4, 1), (28, 4, 0)],
     [(0, 3, 2), (3, 3, 1), (6, 2, 0), (8, 3, 1), (11, 3, 2), (14, 2, 3), (16, 3, 4), (19, 3, 3), (22, 2, 2),
      (24, 8, 3)]],
    [[(0, 2, 0), (2, 2, 1), (4, 2, 2), (6, 4, 3), (10, 2, 2), (12, 4, 1), (16, 2, 0), (18, 2, 1), (20, 4, 2),
      (24, 2, 1), (26, 6, 0)],
     [(0, 2, 0), (2, 2, 1), (4, 2, 2), (6, 4, 3), (10, 2, 4), (12, 4, 3), (16, 4, 2), (20, 4, 3), (24, 8, 4)]],
    [[(0, 4, 3), (4, 2, 2), (6, 2, 1), (8, 4, 2), (12, 4, 0), (16, 3, 1), (19, 3, 2), (22, 2, 3), (24, 6, 2),
      (30, 2, 1)],
     [(0, 4, 3), (4, 2, 2), (6, 2, 1), (8, 4, 2), (12, 4, 4), (16, 3, 5), (19, 3, 4), (22, 2, 3), (24, 8, 4)]],
]
ARPS = [[0, 1, 2, 3, 2, 1, 2, 3], [0, 2, 1, 3, 2, 4, 3, 1], [0, 1, 2, 1, 3, 2, 4, 2], [3, 2, 1, 0, 1, 2, 3, 4]]


def tones_in_range(chord, lo, count=7):
    """Chord pitch classes stacked upward from MIDI ``lo``: [t0, t1, ...] (lead register)."""
    pcs = sorted({n % 12 for n in chord})
    out, m = [], lo
    while len(out) < count:
        if m % 12 in pcs:
            out.append(m)
        m += 1
    return out


@register("trance")
def build(plan: dict, rng: np.random.Generator) -> Song:
    prog = "progressive" in str(plan.get("genre", "")).lower()
    song = Song(plan, rng, swing=50.0)
    key = song.key
    song.arrange(PROG if prog else UPLIFT, song.target_bars())
    secs = song.sections
    intro, outro = song.find("intro"), song.find("outro")
    groove, bd, drop = song.find("groove"), song.find("breakdown"), song.find("drop")
    bass_in = 16
    song.mix_in_bar = bass_in
    bass_off = outro.start_bar + outro.bars - 16
    bar_sec = song.grid.bar_sec
    step = song.grid.step_sec

    # ---------------------------------------------------------------- harmony
    degs = (PROGRESSIONS_PROG if prog else PROGRESSIONS_UP)[int(rng.integers(4))]
    chords, prev = [], None
    for d in degs:
        ch = voice_lead(prev, key.chord(d, 3, 4 if prog else 3), center=key.root(4) - 2)
        chords.append(ch)
        prev = ch
    roots = [xb.note_in_range(key.degree(d, 1) % 12, 41.0) for d in degs]

    def chord_at(c):
        return (c.i // 2) % 4

    # ---------------------------------------------------------------- drums
    k_hz = xb.kick_tune(key, 46.0, 60.0)
    kick = drums.kick("big_room" if not prog else "techno", tune_hz=k_hz, decay=float(rng.uniform(0.3, 0.36)),
                      click=float(rng.uniform(0.55, 0.75)), drive=float(rng.uniform(1.8, 2.4)), rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown":
            return None
        if c.before("breakdown", 1):
            return "x...x...x......."
        return "x...x...x...x..."

    song.hits("kick", kick, kick_pat, gain_db=-2.0, sc_source=True, humanize=0.0)
    clap = drums.variants(drums.clap, 3, rng, jitter={"tone_hz": 0.05}, tone_hz=float(rng.uniform(1150, 1450)),
                          tail=float(rng.uniform(0.16, 0.22)))
    song.hits("clap", clap, lambda c: ("....x.......x..." if not c.phrase_end else "....x.......x.xx")
              if not (c.kind == "breakdown" or (c.kind == "intro" and c.i < 8) or (c.kind == "outro" and c.bars_left <= 8))
              else None, gain_db=-5.5, sends={"reverb": 0.25, "hall": 0.08})
    ch = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.15}, decay=float(rng.uniform(0.03, 0.045)),
                        tone=float(rng.uniform(1.05, 1.25)))
    song.hits("hats", ch, lambda c: ("gxgxgxgxgxgxgxgx" if c.kind != "intro" or c.i >= 8 else "..x...x...x...x.")
              if c.kind != "breakdown" else None, gain_db=-14.0, pan=0.35, humanize=0.12)
    oh = drums.hat(open_=True, decay=float(rng.uniform(0.16, 0.22)), tone=float(rng.uniform(1.0, 1.15)), rng=rng)
    song.hits("open_hat", oh, lambda c: "..x...x...x...x." if (c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 8)
                                                            or (c.kind == "outro" and c.bars_left > 8)) else None,
              gain_db=-10.5, pan=-0.25, sends={"room": 0.12})
    ride = drums.ride(decay=1.2, rng=rng)
    song.hits("ride", ride, lambda c: "x.x.x.x.x.x.x.x." if c.kind == "drop" or (c.kind == "groove" and c.i >= 16) else None,
              gain_db=-17.0, pan=0.35, sends={"room": 0.1})
    shk = drums.variants(drums.shaker, 3, rng, jitter={"length": 0.2}, length=0.06)
    song.hits("shaker", shk, lambda c: "gogxgogxgogxgogx" if c.kind in ("groove", "drop") else None,
              gain_db=-19.0, pan=-0.55, humanize=0.2)

    snr = drums.snare(tone_hz=float(rng.uniform(190, 230)), snappy=0.85, decay=0.13, rng=rng)

    def roll(c):
        if c.kind != "breakdown":
            if c.kind in ("groove",) and c.bars_left <= 2:
                return ["x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx"][2 - c.bars_left]
            if c.kind == "drop" and c.phrase_end and c.i % 16 == 15:
                return "............xxxx"
            return None
        nb = 8 if c.section.bars >= 16 else 4
        if c.bars_left > nb:
            return None
        k = c.bars_left
        if k > 6:
            return "x...x...x...x..."
        if k > 4:
            return "x.x.x.x.x.x.x.x."
        if k > 1:
            return "xxxxxxxxxxxxxxxx"
        return "rrrrrrrrrrrrrrrr"

    sr_pts = [(0, -8.0)]
    for s in secs:
        if s.kind == "breakdown":
            nb = 8 if s.bars >= 16 else 4
            sr_pts += [(s.end_bar - nb, -20.0), (s.end_bar - 1e-3, 0.0), (s.end_bar, -8.0)]
    sn = song.hits("snare_roll", snr, roll, gain_db=-9.0, sends={"reverb": 0.3}, vel_curve=1.0)
    sn.automate("gain_db", sr_pts)

    # ---------------------------------------------------------------- bass (rolling off-beat, follows chords)
    bass_i = xb.psy_bass(cutoff=float(rng.uniform(220, 300)), env_amt=float(rng.uniform(1500, 2200)),
                         decay=float(rng.uniform(0.06, 0.08)), res=0.3, drive=1.8, sub=0.6, sustain=0.55, pulse=0.15)
    bvel = (0.5, 1.0, 0.75) if not prog else (0.75, 0.95, 0.85)

    def bass_on(c):
        if c.kind == "intro":
            return c.i >= bass_in
        if c.kind == "outro":
            return c.bar < bass_off
        return c.kind in ("groove", "drop")

    def bass_notes(c):
        if not bass_on(c):
            return []
        r = roots[chord_at(c)]
        out = []
        for beat in range(4):
            for j in range(3):
                out.append((beat * 4 + 1 + j, 0.8, r, bvel[j]))
        if c.before("breakdown", 1):
            out = [e for e in out if e[0] < 8]
        return out

    bass = song.notes("bass", bass_i, bass_notes, bus="bass", gain_db=-5.0, sidechain=0.85,
                      sc_release_ms=step * 1000 * 1.1, humanize=0.03)
    bass.automate("lp", [(bass_in, 250.0), (intro.end_bar - 0.01, 2500.0), (intro.end_bar, 8000.0),
                         (outro.start_bar, 8000.0), (bass_off, 300.0)])

    # ---------------------------------------------------------------- plucked arpeggio
    arp_shape = ARPS[int(rng.integers(len(ARPS)))]
    arp_i = inst.pluck(wave="saw", cutoff=float(rng.uniform(500, 800)), env_amt=float(rng.uniform(3500, 5500)),
                       decay=float(rng.uniform(0.09, 0.14)), release=0.1, width=0.6)

    def arp_notes(c):
        on = (c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 24)
              or (c.kind == "breakdown" and (prog or c.i >= 16)) or (c.kind == "outro" and c.i < 16))
        if not on:
            return []
        tones = tones_in_range(chords[chord_at(c)], key.root(4) - 3, 6)
        vel = [0.95, 0.65, 0.8, 0.65]
        return [(s, 0.9, tones[arp_shape[s % 8] % len(tones)], vel[s % 4]) for s in range(16)]

    arp = song.notes("arp", arp_i, arp_notes, gain_db=-11.0 if not prog else -8.5, sidechain=0.45,
                     sends={"delay": 0.25, "reverb": 0.12}, pan=0.15, width=1.5)
    apts = [(intro.start_bar + 24, 500.0), (intro.end_bar, 1800.0), (groove.start_bar + 16, 3000.0),
            (groove.end_bar, 5000.0), (bd.start_bar, 1200.0), (bd.end_bar - 0.01, 7000.0), (drop.start_bar, 9000.0),
            (outro.start_bar, 6000.0), (outro.start_bar + 16, 600.0)]
    arp.automate("lp", apts)

    # ---------------------------------------------------------------- pads
    pad_i = inst.pad(attack=float(rng.uniform(0.5, 0.9)), cutoff=float(rng.uniform(2200, 3200)), detune=0.32, warmth=0.5)

    def pad_notes(c):
        if c.i % 2:
            return []
        on = c.kind in ("breakdown", "drop") or (c.kind == "groove" and c.i >= 16)
        if not on:
            return []
        return [(0, 31.5, chords[chord_at(c)], 0.8 if c.kind == "breakdown" else 0.6)]

    pad = song.notes("pad", pad_i, pad_notes, gain_db=-11.0, sends={"hall": 0.35}, width=1.4, sidechain=0.55,
                     sc_release_ms=step * 1000 * 2.2)
    pad.automate("gain_db", song.section_points({"breakdown": 0.0, "drop": -3.0, "groove": -6.0}, -6.0, ramp_bars=1))

    if prog:
        # trance-gated pad (16th gate) in the drop
        gate = ["x.xxx.xx.xx.x.xx", "xx.xx.xx.xx.xx.x", "x.x.xxx.x.x.xxx."][int(rng.integers(3))]
        gpad = inst.pad(attack=0.01, release=0.2, cutoff=4000.0, detune=0.25, warmth=0.3)
        song.notes("gate_pad", gpad, lambda c: [(0, 31.5, chords[chord_at(c)], 0.7)] if c.kind == "drop" and c.i % 2 == 0
                   else [], gain_db=-15.0, fx=[xb.gate_fx(gate, song.bpm, 0.9)], sends={"delay8": 0.15},
                   width=1.7, sidechain=0.5, hp=300.0)

    # ---------------------------------------------------------------- lead (anthem / subtle)
    hook = HOOKS[int(rng.integers(len(HOOKS)))]
    lead_lo = key.root(5) - 5 if not prog else key.root(4) + 2

    def hook_notes(c, octave_shift=0):
        k = chord_at(c)
        tones = tones_in_range(chords[k], lead_lo + octave_shift, 7)
        cell = hook[1] if k == 3 else hook[0]
        off = (c.i % 2) * 16
        out = []
        for s, l, ti in cell:
            if off <= s < off + 16:
                out.append((s - off, l * 0.92, tones[min(ti, len(tones) - 1)], 0.9 if s % 8 == 0 else 0.8))
        return out

    if not prog:
        lead_i = xb.anthem_lead(detune=float(rng.uniform(0.28, 0.38)), cutoff=float(rng.uniform(4500, 6500)))

        def lead_notes(c):
            if c.kind == "drop" or (c.kind == "breakdown" and c.i >= 16):
                return hook_notes(c)
            if c.kind == "groove" and c.i >= 16:
                return hook_notes(c)
            return []

        lead = song.notes("lead", lead_i, lead_notes, gain_db=-7.0, sidechain=0.45,
                          sends={"delay": 0.22, "reverb": 0.2, "hall": 0.12}, width=1.25)
        lpts = [(groove.start_bar + 16, 700.0), (groove.end_bar, 1800.0), (bd.start_bar + 16, 900.0),
                (bd.end_bar - 0.01, 9000.0), (drop.start_bar, 14000.0)]
        lead.automate("lp", lpts)
        lead.automate("gain_db", song.section_points({"groove": -5.0, "breakdown": -1.0, "drop": 0.0}, 0.0))
        # piano: chords + melody in the first half of the breakdown
        pno = inst.piano(bright=0.55)

        def piano_notes(c):
            if c.kind != "breakdown" or c.i >= 24:
                return []
            k = chord_at(c)
            ch = chords[k]
            out = [(0, 15.5, ch, 0.7)] if c.i % 2 == 0 else [(0, 7.5, ch, 0.55), (8, 7.5, ch, 0.5)]
            if c.i < 16:
                out += hook_notes(c, -12)
            return out

        song.notes("piano", pno, piano_notes, gain_db=-8.5, sends={"hall": 0.3, "reverb": 0.15}, width=1.3)
    else:
        bell_i = inst.pluck(wave="square", cutoff=900.0, env_amt=4000.0, decay=0.2, release=0.3, width=0.7)

        def motif(c):
            if c.kind == "drop" or (c.kind == "breakdown" and c.i >= 8):
                return [(s, l, n, v) for s, l, n, v in hook_notes(c)]
            return []

        song.notes("lead", bell_i, motif, gain_db=-12.0, sidechain=0.4, sends={"delay": 0.35, "hall": 0.2}, width=1.5,
                   pan=-0.1)

    # sub weight in the breakdown (very low)
    song.notes("bd_sub", inst.sub_bass(), lambda c: [(0, 31.5, roots[chord_at(c)], 0.6)]
               if c.kind == "breakdown" and c.i % 2 == 0 and c.bars_left > 2 else [], bus="bass", gain_db=-16.0)

    # ---------------------------------------------------------------- FX / transitions
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.15})
    crash = drums.crash(decay=2.6, rng=rng)
    for s in secs:
        if s.kind in ("groove", "drop", "outro"):
            fxl.add(crash, s.start_bar, gain_db=-8.0)
        if s.kind == "drop":
            fxl.add(fx.impact(3.0, rng=rng), s.start_bar, gain_db=-7.0)
            for b in range(s.start_bar + 8, s.end_bar, 8):
                fxl.add(crash, b, gain_db=-12.0 if (b - s.start_bar) % 16 else -10.0)
        if s.kind == "groove":
            for b in range(s.start_bar + 16, s.end_bar, 16):
                fxl.add(crash, b, gain_db=-12.0)
        if s.kind == "breakdown":
            nb = 8 if s.bars >= 16 else 4
            fxl.add(fx.riser(bar_sec * nb, "both", f_lo=250, f_hi=12000, pitch_from=52, pitch_to=88, rng=rng),
                    s.end_bar, align="end", gain_db=-8.0)
            fxl.add(fx.downlifter(bar_sec * 4, rng=rng), s.start_bar, gain_db=-11.0)
            fxl.add(fx.reverse_cymbal(bar_sec, rng=rng), s.end_bar, align="end", gain_db=-9.0)
            fxl.add(crash, s.start_bar, gain_db=-10.0)
    fxl.add(fx.noise_sweep(bar_sec * 8, up=True, rng=rng), groove.start_bar, align="end", gain_db=-16.0)
    fxl.add(fx.reverse_cymbal(bar_sec, rng=rng), bass_in, align="end", gain_db=-13.0)

    # ---------------------------------------------------------------- mix
    song.buses["drums"].eq = [("peak", 3500.0, 1.5, 0.8)]
    song.buses["drums"].width = 1.25
    song.buses["music"].width = 1.15
    song.buses["music"].eq = [("peak", 3000.0, 1.5, 0.7), ("peak", 350.0, -1.5, 1.0)]
    song.returns["hall"].decay = 4.0
    song.returns["reverb"].width = 1.5
    song.returns["delay"].width = 1.4
    song.master.lufs = -9.0

    if prog:
        song.description_he = (
            f"פרוגרסיב טראנס ב-{int(song.bpm)} BPM בסולם {plan['key']}: גרוב מתגלגל שנבנה סביב ארפג'ו פלאקי עם דיליי, "
            f"באס אופביט שעוקב אחרי האקורדים, פד עם טראנס-גייט, מוטיב עדין ופילטרים שנפתחים לאט. "
            f"פחות סופר-סו, יותר מסע — מושלם לבניית אנרגיה לפני הפיק.")
        song.instruments = ["trance kick", "rolling off-beat bass", "plucked 16th arpeggio", "trance-gated pad",
                            "pluck lead motif", "pads", "clap, hats, ride", "snare roll & riser"]
    else:
        song.description_he = (
            f"טראנס אפליפטינג ב-{int(song.bpm)} BPM בסולם {plan['key']}: באס אופביט מתגלגל, ארפג'יו פלאקים, ליד "
            f"סופר-סו ענק עם מנגינה מקורית, ברייקדאון רגשי ארוך עם פדים ואקורדי פסנתר, בילד של סנר-רול ורייזר — "
            f"ודרופ אופורי. רגע הידיים-למעלה של הסט.")
        song.instruments = ["trance kick", "rolling off-beat bass", "plucked arpeggio", "supersaw anthem lead",
                            "piano chords & melody", "lush pads", "clap, hats, ride", "snare roll, riser, impact"]
    song.mix_tips_he = _tips(song, plan, prog)
    return song


def _tips(song, plan, prog):
    from ..theory import compatible_keys
    cam = plan["camelot"]
    bd, dr, out = song.find("breakdown"), song.find("drop"), song.find("outro")
    return (f"טיפ ערבוב: 16 תיבות תופים בלבד בהתחלה, הבאס המתגלגל נכנס בתיבה {song.mix_in_bar + 1} (Hot Cue B). "
            f"הברייקדאון ב-{bd.start_bar + 1} נמשך {bd.bars} תיבות"
            + (" עם פסנתר ופדים" if not prog else "")
            + f", הסנר-רול מוביל לדרופ בתיבה {dr.start_bar + 1} (Hot Cue D). "
            f"האאוטרו מתחיל בתיבה {out.start_bar + 1} והבאס יוצא בתיבה {out.start_bar + out.bars - 16 + 1}. "
            f"אל תמקסו בזמן הברייקדאון — חכו לדרופ או לאאוטרו. שכנים ב-Camelot: {cam} ↔ "
            f"{', '.join(compatible_keys(cam)[1:4])}.")
