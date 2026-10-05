"""Breakbeat / nu-skool breaks recipe (126–136 BPM).

Funky syncopated breakbeat: punchy kick on 1 + syncopated kicks, tight snare on 2 and 4 with ghost
notes, accented 16th hats with open-hat lifts, plus a synthesised funk-break layer (vintage kit on a
squashed ``break`` bus). Nu-skool bassline: rubbery distorted saw/square bass whose resonant filter
moves on a tempo-synced LFO (1/4 – 1/2 bar) with slides, over a clean sub; brass/synth chord stabs,
turntable **scratch** FX made from a synthesised vocal 'ahh' (no samples), rising filter sweeps.

DJ rules: 32-bar intro (drums only for 16 bars, bass enters on bar 17), 16-bar breakdown, 32-bar
outro (last 16 drums only), sections on the 8-bar grid.
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from .. import ext_breadth as xb
from ..arrangement import Song
from ..theory import voice_lead
from . import register

TPL = [("Intro", "intro", 32, 5, 0), ("Groove", "groove", 24, 7, 1), ("Breakdown", "breakdown", 16, 4, 0),
       ("Drop", "drop", 24, 8, 2), ("Outro", "outro", 32, 5, 0)]

KICKS = [["x.....x...x.....", "x.x.......x..x.."], ["x......x..x.....", "x.x....x..x....."],
         ["x.....x.x.......", "x.....x...x..x.."]]
SNARE = "....x.......x..."
GHOSTS = ["......g..g....g.", ".g.....g.g......", "..g....g......gg"]
HATS = ["xgxoxgxoxgxoxgxo", "xgxgxoxgxgxgxoxg", "x.xox.xox.xox.xo"]
OPEN = ["......x.......x.", "..............x.", "......x........."]
FUNK_A = ("x.x.......x.....", "....x..g.g..x...", ".......g.g.....g", "x.x.x.x.x.x.x.x.")
FUNK_B = ("x.........xx....", "....x..g....x.g.", "...g...g......g.", "x.x.x.x.x.x.x.x.")
FUNK_FILL = ("x.x.......x.....", "....x..x.x.xx.xx", "......g.g.g.....", "x.x.x.x.x.x.....")

# bass riffs (2 bars): (step, len, semitone offset, LFO flag, slide)
BASS_RIFFS = [
    [(0, 3, 0, "w4", ""), (3, 1, 0, "w8", ""), (6, 2, 12, "w8", "s"), (8, 2, 10, "w8", ""), (10, 4, 0, "w4", ""),
     (14, 2, 3, "w8", "s"), (16, 3, 5, "w4", ""), (19, 1, 5, "w8", ""), (22, 2, 3, "w8", ""), (24, 6, 0, "w2", ""),
     (30, 2, -2, "w8", "s")],
    [(0, 2, 0, "w8", ""), (2, 2, 0, "w8", ""), (6, 4, 7, "w4", "s"), (10, 2, 5, "w8", ""), (12, 4, 3, "w4", ""),
     (16, 2, 0, "w8", ""), (18, 2, 12, "w8", "s"), (20, 2, 10, "w8", ""), (22, 4, 7, "w4", ""), (26, 6, 0, "w2", "")],
]
STAB_RHYTHMS = [[(0, 1, 0.9), (3, 1, 0.75), (10, 1.5, 0.85)], [(2, 1, 0.85), (7, 1, 0.7), (14, 1, 0.8)],
                [(0, 2, 0.9), (6, 1, 0.7), (11, 1, 0.8)]]


def _funk(c):
    if c.phrase_end:
        return FUNK_FILL
    return FUNK_A if c.i % 2 == 0 else FUNK_B


@register("breaks")
def build(plan: dict, rng: np.random.Generator) -> Song:
    song = Song(plan, rng, swing=float(rng.choice([52.0, 54.0, 55.0])))
    key = song.key
    song.arrange(TPL, song.target_bars())
    secs = song.sections
    intro, outro = song.find("intro"), song.find("outro")
    groove, bd, drop = song.find("groove"), song.find("breakdown"), song.find("drop")
    bass_in = 16
    song.mix_in_bar = bass_in
    bass_off = outro.start_bar + outro.bars - 16
    bar_sec = song.grid.bar_sec
    beat_sec = song.grid.beat_sec

    # ---------------------------------------------------------------- drums
    kick = drums.kick("909", tune_hz=xb.kick_tune(key, 46.0, 62.0), decay=float(rng.uniform(0.3, 0.38)),
                      click=0.65, drive=1.8, rng=rng)
    kp = KICKS[int(rng.integers(len(KICKS)))]

    def kick_pat(c):
        if c.kind == "breakdown":
            return None if c.bars_left > 4 else ("x.....x...x....." if c.bars_left > 1 else None)
        if c.before("drop", 1):
            return "x..............."
        return kp[c.i % 2]

    song.hits("kick", kick, kick_pat, gain_db=-2.0, sc_source=True, humanize=0.0)
    snr = xb.layered_snare(rng, tone_hz=float(rng.uniform(200, 235)), snappy=0.8, decay=0.15, clap_amt=0.45,
                           crack_hz=float(rng.uniform(1800, 2300)))

    def snare_pat(c):
        if c.kind == "breakdown":
            if c.bars_left <= 4:
                return ["x...x...x...x...", "x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx", "rrrrrrrrrrrrrrrr"][4 - c.bars_left]
            return None
        if c.kind == "intro" and c.i < 4:
            return None
        return SNARE if not c.phrase_end else "....x.......x.xx"

    sn = song.hits("snare", snr, snare_pat, gain_db=-4.0, sc_source=True, sends={"room": 0.15, "reverb": 0.08})
    sn.automate("gain_db", [(0, 0.0), (bd.end_bar - 4 - 1e-3, 0.0), (bd.end_bar - 4, -12.0), (bd.end_bar - 0.01, 0.0)])
    ghost = drums.snare(tone_hz=240.0, snappy=0.6, decay=0.07, kind="tight", rng=rng)
    gp = GHOSTS[int(rng.integers(len(GHOSTS)))]
    song.hits("ghost", ghost, lambda c: gp if c.kind not in ("breakdown",) and not (c.kind == "intro" and c.i < 8) else None,
              gain_db=-15.0, humanize=0.25, timing_ms=2.0, pan=-0.1)
    hats = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.2}, decay=float(rng.uniform(0.03, 0.045)),
                          tone=float(rng.uniform(0.95, 1.2)))
    hpat = HATS[int(rng.integers(len(HATS)))]
    song.hits("hats", hats, lambda c: hpat if not (c.kind == "breakdown" and c.bars_left > 8) else
              ("x.x.x.x.x.x.x.x." if c.i >= 4 else None), gain_db=-14.0, pan=0.3, humanize=0.15)
    oh = drums.hat(open_=True, decay=float(rng.uniform(0.18, 0.26)), tone=1.05, rng=rng)
    opat = OPEN[int(rng.integers(len(OPEN)))]
    song.hits("open_hat", oh, lambda c: opat if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 8)
              or (c.kind == "outro" and c.bars_left > 8) else None, gain_db=-12.0, pan=-0.3, sends={"room": 0.1})
    shk = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=0.06)
    song.hits("shaker", shk, lambda c: "gxgogxgogxgogxgo" if c.kind in ("groove", "drop") else None,
              gain_db=-19.0, pan=0.55, humanize=0.2)
    cow = drums.cowbell(rng=rng)
    song.hits("cowbell", cow, lambda c: "..x.......x..x.." if c.kind == "drop" and c.i % 4 == 2 else None,
              gain_db=-20.0, pan=-0.5, sends={"delay": 0.2})

    kit = xb.break_kit(rng, tune=float(rng.uniform(0.95, 1.05)))
    song.buses["break"] = xb.break_bus(hp_hz=120.0, sat=0.5)

    def brk(idx):
        def p(c):
            if c.kind == "breakdown" and c.bars_left > 4:
                return None
            if c.kind == "intro" and c.i < 8:
                return None
            if c.kind == "outro" and c.bars_left <= 4:
                return None
            return _funk(c)[idx]
        return p

    song.hits("brk_kick", kit["kick"], brk(0), bus="break", gain_db=-10.0, humanize=0.08)
    song.hits("brk_snare", kit["snare"], brk(1), bus="break", gain_db=-7.0, humanize=0.1, sends={"room": 0.2})
    song.hits("brk_ghost", kit["ghost"], brk(2), bus="break", gain_db=-13.0, humanize=0.2)
    song.hits("brk_hat", [kit["hat"], kit["ohat"]], brk(3), bus="break", gain_db=-14.0, humanize=0.15, pan=0.2)

    # ---------------------------------------------------------------- harmony
    degs = [[0, 0, 5, 6], [0, 3, 0, 4], [0, 6, 5, 6]][int(rng.integers(3))]
    chords, prev = [], None
    for d in degs:
        ch = voice_lead(prev, key.chord(d, 3, 3), center=key.root(4))
        chords.append(ch)
        prev = ch

    def chord_i(c):
        return (c.i // 2) % 4

    # ---------------------------------------------------------------- nu-skool bass
    root = xb.note_in_range(key.root_pc, 41.0)
    riff = BASS_RIFFS[int(rng.integers(len(BASS_RIFFS)))]

    def bass_on(c):
        if c.kind == "intro":
            return c.i >= bass_in
        if c.kind == "outro":
            return c.bar < bass_off
        if c.kind == "breakdown":
            return 4 < c.bars_left <= 8
        return True

    def bass_notes(c):
        if not bass_on(c):
            return []
        off = (c.i % 2) * 16
        shift = (key.degree(degs[chord_i(c)], 1) - key.root(1)) % 12 if c.kind in ("groove", "drop") else 0
        if shift > 6:
            shift -= 12
        out = [(s - off, l - 0.15, root + o + shift, 0.95, fl + sl) for s, l, o, fl, sl in riff if off <= s < off + 16]
        if c.before("breakdown", 1) or c.before("drop", 1):
            out = [e for e in out if e[0] < 12]
        return out

    bass = song.add(xb.SynthLine("bass", xb.Wobble(cut_lo=float(rng.uniform(280, 360)), cut_hi=float(rng.uniform(2200, 3000)),
                                                   res=0.62, drive=3.0, dist=0.45, fm_amt=0.5, vowel=0.25, hp_hz=70.0,
                                                   chorus_mix=0.2, shape="sine"),
                                 bass_notes, bus="bass", gain_db=-1.5, sidechain=0.5, sc_release_ms=110.0))
    bass.automate("cutoff", [(bass_in, 0.35), (intro.end_bar - 0.01, 0.9), (intro.end_bar, 1.0),
                             (bd.end_bar - 8, 0.4), (bd.end_bar - 4, 0.8), (outro.start_bar, 1.0), (bass_off, 0.35)])
    sub = song.add(xb.SynthLine("sub", xb.SubLine(harm=0.15, drive=1.4, glide_ms=35.0),
                                lambda c: [(s, l, m - 12 if m - 12 >= 26 else m, v, fl) for s, l, m, v, fl in bass_notes(c)],
                                bus="bass", gain_db=-8.0, sidechain=0.5, sc_release_ms=110.0))
    sub.automate("gain_db", [(bass_in, -6.0), (intro.end_bar, 0.0)])

    # ---------------------------------------------------------------- stabs
    sr_ = STAB_RHYTHMS[int(rng.integers(len(STAB_RHYTHMS)))]
    brass = inst.brass(cutoff=float(rng.uniform(2500, 3500)))
    stab = inst.stab(wave="square", cutoff=900.0, env_amt=3800.0, decay=0.14)

    def stab_notes(c):
        on = c.kind in ("groove", "drop") or (c.kind == "outro" and c.i < 8) or (c.kind == "intro" and c.i >= 24)
        if not on:
            return []
        ch = chords[chord_i(c)]
        if c.kind == "drop" or (c.kind == "groove" and c.i >= 8):
            return [(s, l, ch, v) for s, l, v in sr_]
        return [(s, l, ch, v) for s, l, v in sr_[:1]]

    song.notes("stabs", stab, stab_notes, gain_db=-8.5, sidechain=0.35, sends={"delay": 0.2, "reverb": 0.12},
               width=1.5).automate("lp", [(intro.start_bar + 24, 1200.0), (intro.end_bar, 9000.0)])
    song.notes("brass", brass, lambda c: [(0, 3, chords[chord_i(c)], 0.85), (6, 2, chords[chord_i(c)], 0.7)]
               if (c.kind == "drop" and c.i % 4 == 3) or (c.kind == "breakdown" and c.i % 2 == 0 and c.bars_left > 4) else [],
               gain_db=-8.0, sends={"reverb": 0.2, "hall": 0.1}, width=1.4)
    pad_i = inst.pad(attack=1.0, cutoff=1600.0, detune=0.3, warmth=0.6)
    song.notes("pad", pad_i, lambda c: [(0, 31.5, chords[chord_i(c)], 0.7)] if c.kind == "breakdown" and c.i % 2 == 0
               else [], gain_db=-11.0, sends={"hall": 0.4}, width=1.6, hp=150.0)

    # ---------------------------------------------------------------- scratch FX (synth 'ahh' on a turntable)
    ahh = inst.vocal_chop(vowel="a", vowel_to="o", shift=1.15, scoop=-0.5, vibrato=0.1)(xb.midi_hz(key.degree(4, 4)), 0.5, 1.0)
    fresh = inst.vocal_chop(vowel="e", vowel_to="a", shift=1.2, scoop=-2.0)(xb.midi_hz(key.degree(2, 4)), 0.35, 1.0)
    scr = song.audio("scratch", bus="fx", sends={"room": 0.1})
    scr.gain_db = -9.0
    kinds = ["baby", "chirp", "transformer", "scribble"]
    for s in secs:
        if s.kind not in ("groove", "drop") and not (s.kind == "intro" and s.bars > 16):
            continue
        start = s.start_bar if s.kind != "intro" else s.start_bar + 16
        for b in range(start + 7, s.end_bar, 8):
            rr = np.random.default_rng(song.seed * 13 + b)
            k = kinds[int(rr.integers(len(kinds)))]
            src = ahh if rr.random() < 0.6 else fresh
            scr.add(xb.scratch(src, song.bpm, k, 2.0, rng=rr), b, 2.0, gain_db=0.0)
        if s.kind == "drop":
            for b in range(s.start_bar + 3, s.end_bar, 8):
                rr = np.random.default_rng(song.seed * 17 + b)
                scr.add(xb.scratch(ahh, song.bpm, "chirp", 1.0, rng=rr), b, 3.0, gain_db=-3.0)

    # ---------------------------------------------------------------- FX
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.12})
    crash = drums.crash(decay=2.2, rng=rng)
    for s in secs:
        if s.kind in ("groove", "drop", "outro"):
            fxl.add(crash, s.start_bar, gain_db=-9.0)
        if s.kind == "drop":
            fxl.add(fx.impact(2.5, rng=rng), s.start_bar, gain_db=-8.0)
            fxl.add(crash, s.start_bar + 16, gain_db=-11.0)
        if s.kind == "breakdown":
            fxl.add(fx.riser(bar_sec * 8, "both", f_lo=250, f_hi=11000, rng=rng), s.end_bar, align="end", gain_db=-9.0)
            fxl.add(fx.downlifter(bar_sec * 2, rng=rng), s.start_bar, gain_db=-11.0)
            fxl.add(fx.reverse_cymbal(bar_sec, rng=rng), s.end_bar, align="end", gain_db=-10.0)
        if s.kind in ("groove", "drop"):
            for b in range(s.start_bar + 8, s.end_bar, 8):
                fxl.add(fx.noise_sweep(bar_sec * 2, up=True, rng=rng), b, align="end", gain_db=-19.0)
    fxl.add(fx.reverse_cymbal(bar_sec, rng=rng), bass_in, align="end", gain_db=-12.0)

    # ---------------------------------------------------------------- mix
    song.buses["drums"].eq = [("peak", 3000.0, 1.5, 0.8), ("peak", 100.0, 1.0, 1.0)]
    song.buses["drums"].width = 1.2
    song.buses["music"].width = 1.3
    song.buses["music"].eq = [("peak", 1500.0, 2.5, 0.7), ("peak", 600.0, 1.5, 0.8)]
    song.master.lufs = -9.0
    song.description_he = (
        f"ברייקביט ב-{int(song.bpm)} BPM בסולם {plan['key']}: תופי ברייק פאנקיים וסינקופטיים (קיק ב-1 וקיקים מוזזים, "
        f"סנר ב-2 וב-4 עם גוסט-נוטס) מעל שכבת ברייק סינתטית בסגנון וינטג', באסליין נו-סקול גומי ומלוכלך עם פילטר "
        f"שזז בסנכרון לטמפו, סטאבים של סינת וברס, ושריטות (Scratch) שנוצרו מ'אהה' סינתטי — בלי סמפלים.")
    song.instruments = ["funky breakbeat drums", "synthesised funk-break layer", "nu-skool filter bass", "clean sub",
                        "synth & brass stabs", "turntable scratch FX", "breakdown pad", "risers & sweeps"]
    from ..theory import compatible_keys
    cam = plan["camelot"]
    song.mix_tips_he = (
        f"טיפ ערבוב: 16 תיבות ראשונות תופים בלבד; הבאס נכנס בתיבה {bass_in + 1} (Hot Cue B). ברייקביט לא בנוי על "
        f"קיק בכל פעמה — כדי לסנכרן הקשיבו לסנר ב-2 וב-4. ברייקדאון בתיבה {bd.start_bar + 1}, דרופ בתיבה "
        f"{drop.start_bar + 1}, ושריטות בסוף כל פרייז של 8 תיבות מסמנות את המעבר. האאוטרו מתיבה {outro.start_bar + 1} "
        f"(16 התיבות האחרונות תופים בלבד). שכנים ב-Camelot: {cam} ↔ {', '.join(compatible_keys(cam)[1:4])}.")
    return song
