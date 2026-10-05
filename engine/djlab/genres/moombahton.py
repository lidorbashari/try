"""Moombahton recipe (105–112 BPM): Dutch house slowed into a dembow swing.

Genre brief
-----------
* Drums: four-on-the-floor house kick at 108 under a **dembow** snare/rim cell (16th steps 3, 6,
  11, 14), claps on 2 and 4 in the drops, 8th hats + 16th shaker, a rolling **tom groove**
  (tribal low/high toms) plus tom fills on every 8-bar phrase end, timbale accents.
* Bass: in the groove a round sub that follows the dembow; in the drops a **heavy wobble bass**
  (detuned saw+square through a resonant ladder, tempo-synced LFO: 8th wobbles, 16th/triplet
  wobbles on turnaround bars) with a sine sub underneath, ducked by the kick.
* Lead: **Dutch-house style squeaky lead** — narrow-pulse square, resonant filter envelope, a fast
  upward pitch "bwip" into every note and legato slides, playing a bouncy 16th riff built from
  chord tones (generated per seed). An octave-up copy joins in drop 2.
* Harmony: minor loops (i–VI–III–VII / i–iv–VI–V …), one chord per bar; square plucks on the dembow
  rhythm in the groove, brass stabs and a pad in the breakdown, crowd "YA!" chants, siren.
* Builds: 8 bars — snare roll that accelerates and rises in pitch, tom roll, riser + noise sweep,
  kick 8ths, one bar of silence-ish tension, impact + crash on the drop.
* Arrangement (96 bars ≈ 3.6 min): Intro 16 (drums only) · Groove 8 · Build 8 · Drop 16 ·
  Breakdown 8 · Build 2 8 · Drop 2 16 · Outro 16 (8 bars drums+bass, last 8 drums only).
"""
from __future__ import annotations

import numpy as np

from .. import drums, ext_mainstream as xm, fx, instruments as inst
from ..arrangement import Song
from ..theory import voice_lead
from . import register

TPL = [("Intro", "intro", 16, 4, 0), ("Groove", "groove", 8, 6, 1), ("Build", "build", 8, 7, 0),
       ("Drop", "drop", 16, 8, 2), ("Breakdown", "breakdown", 8, 4, 0), ("Build 2", "build", 8, 7, 0),
       ("Drop 2", "drop", 16, 9, 3), ("Outro", "outro", 16, 5, 0)]

PROGS = [[0, 5, 2, 6], [0, 3, 0, 6], [0, 5, 3, 6], [0, 0, 5, 6]]

FOUR = "x...x...x...x..."
DEMBOW = "...o..x....o..x."
DEMBOW_VARS = ["...o..x....o..x.", "...o..x...oo..x.", "...o..x....o.xx.", "..oo..x....o..x."]
DEMBOW_FILL = ["...o..x.x.xxx.xx", "...o..xxxxxxxxxx", "...o..x.xxxx.xxx"]
HATS = ["x.o.x.o.x.o.x.o.", "x.x.o.x.x.x.o.x.", "o.x.o.x.o.x.o.xg"]
SHAKER = ["xgogxgogxgogxgog", "xgoxxgoxxgoxxgox"]
TOM_GROOVES = [("..x....x..x.....", "......x.....x.x."), ("......x...x..x..", "..x.......x....."),
               ("..x..x....x.....", ".......x.....x..")]
TOM_FILLS = [("........x.x.x...", "..............xx"), ("..........x.x.x.", "..............x."),
             ("........xx.x....", "............x.xx")]

# Dutch lead riffs: (step, len, chord-tone index, flags) per bar ("s" = slide into the next note)
RIFFS = [
    [(0, 1, 0, ""), (2, 1, 2, ""), (3, 1, 3, "s"), (5, 1, 2, ""), (6, 2, 0, ""), (8, 1, 3, ""), (10, 1, 2, "s"),
     (11, 1, 4, ""), (13, 1, 3, ""), (14, 2, 2, "")],
    [(0, 2, 3, ""), (3, 1, 2, ""), (4, 1, 3, "s"), (6, 1, 4, ""), (8, 2, 2, ""), (11, 1, 1, ""), (12, 1, 2, "s"),
     (14, 2, 3, "")],
    [(0, 1, 2, ""), (1, 1, 3, "s"), (3, 2, 2, ""), (6, 1, 0, ""), (7, 1, 2, ""), (8, 1, 3, "s"), (10, 2, 4, ""),
     (13, 1, 3, ""), (14, 1, 2, "s"), (15, 1, 0, "")],
]
GROOVE_BASS = [(0, 3, 0, 1.0), (3, 2, 0, 0.8), (6, 2, 0, 0.9), (8, 3, 0, 1.0), (11, 2, 0, 0.8), (14, 2, 7, 0.85)]


def tones(chord, lo, count=8):
    pcs = sorted({n % 12 for n in chord})
    out, m = [], lo
    while len(out) < count:
        if m % 12 in pcs:
            out.append(m)
        m += 1
    return out


def in_range(m, lo, hi):
    while m > hi:
        m -= 12
    while m < lo:
        m += 12
    return m


@register("moombahton")
def build(plan: dict, rng: np.random.Generator) -> Song:
    song = Song(plan, rng, swing=float(rng.choice([50.0, 52.0])))
    key = song.key
    song.arrange(TPL, song.target_bars())
    intro, outro = song.find("intro"), song.find("outro")
    groove, bd = song.find("groove"), song.find("breakdown")
    drops = [s for s in song.sections if s.kind == "drop"]
    song.mix_in_bar = groove.start_bar
    drums_only_from = outro.end_bar - 8
    bar_sec = song.grid.bar_sec
    windows = [(song.section_before(d).start_bar, d.start_bar) for d in drops]   # the Build sections

    def to_drop(bar):
        for a, b in windows:
            if a <= bar < b:
                return b - bar
        return None

    # ---------------------------------------------------------------- harmony
    degs = PROGS[int(rng.integers(len(PROGS)))]
    chords, prev = [], None
    for d in degs:
        ch = voice_lead(prev, key.chord(d, 3, 3), center=key.root(4) - 2)
        chords.append(ch)
        prev = ch
    roots = [in_range(key.degree(d, 1), 28, 39) for d in degs]
    lead_lo = in_range(key.root(5), 72, 83) - 2

    def chord_at(c):
        return chords[c.i % 4]

    def root_at(c):
        return roots[c.i % 4]

    # kick tuned to the scale note nearest 52 Hz (root/fifth preferred)
    cands = []
    for deg, pref in ((0, 0.0), (4, 1.0), (2, 2.0), (3, 2.5)):
        for o in (0, 1, 2):
            hz = 440 * 2 ** ((key.degree(deg, o) - 69) / 12)
            if 40 <= hz <= 62:
                cands.append((pref + abs(hz - 52) / 10, hz))
    kick_hz = float(min(cands)[1]) if cands else 52.0

    # ---------------------------------------------------------------- drums
    kick = drums.kick("house", tune_hz=kick_hz, decay=float(rng.uniform(0.32, 0.4)), click=float(rng.uniform(0.55, 0.75)),
                      drive=1.8, rng=rng)

    def kick_pat(c):
        tb = to_drop(c.bar)
        if c.kind == "breakdown":
            return "X..............." if c.first else None
        if tb is not None:
            if tb == 1:
                return None
            if tb == 2:
                return "x.x.x.x.x.x.x.x."
            return FOUR
        return FOUR

    song.hits("kick", kick, kick_pat, gain_db=-1.5, sc_source=True, humanize=0.0)

    snr = drums.snare(tone_hz=float(rng.uniform(200, 240)), snappy=0.85, decay=0.14, kind="tight", rng=rng)
    rim = drums.rimshot(float(rng.uniform(1500, 1900)), rng=rng)
    n = max(snr.shape[0], rim.shape[0])
    dem = np.zeros(n, dtype=np.float32)
    dem[:snr.shape[0]] += snr * 0.85
    dem[:rim.shape[0]] += rim * 0.45
    dem = xm.normalize(dem)
    dv = DEMBOW_VARS[int(rng.integers(len(DEMBOW_VARS)))]
    dfill = DEMBOW_FILL[int(rng.integers(len(DEMBOW_FILL)))]

    def dembow_pat(c):
        tb = to_drop(c.bar)
        if c.kind == "breakdown":
            return None
        if tb is not None and tb <= 3:
            return None          # the snare roll takes over
        if c.kind == "intro" and c.i < 4:
            return None
        if c.kind == "outro" and c.bars_left <= 2:
            return None
        if c.phrase_end and c.kind in ("drop", "groove", "intro"):
            return dfill
        return DEMBOW if c.i % 4 != 3 else dv

    song.hits("dembow", dem, dembow_pat, gain_db=-3.5, sends={"room": 0.12, "reverb": 0.05}, humanize=0.08,
              timing_ms=1.0)
    clap = drums.clap(tightness=0.85, tone_hz=float(rng.uniform(1150, 1400)), tail=0.18, rng=rng)
    song.hits("clap", clap, lambda c: "....x.......x..." if c.kind == "drop" else None, gain_db=-6.0,
              sends={"reverb": 0.18})

    hat = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.15}, decay=0.035, tone=1.1)
    hp_ = HATS[int(rng.integers(len(HATS)))]
    song.hits("hats", hat, lambda c: None if (c.kind == "breakdown" or (to_drop(c.bar) or 9) <= 1) else hp_,
              gain_db=-12.5, pan=0.25, humanize=0.1)
    ohat = drums.hat(open_=True, decay=0.18, tone=1.05, rng=rng)
    song.hits("open_hat", ohat, lambda c: "..x...x...x...x." if c.kind == "drop" else None, gain_db=-15.0, pan=-0.2)
    shk = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=0.08)
    sp = SHAKER[int(rng.integers(len(SHAKER)))]
    song.hits("shaker", shk, lambda c: sp if not (c.kind == "intro" and c.i < 2) and c.kind != "breakdown" else None,
              gain_db=-15.5, pan=-0.45, humanize=0.15, timing_ms=1.5)

    tg = TOM_GROOVES[int(rng.integers(len(TOM_GROOVES)))]
    tf = TOM_FILLS[int(rng.integers(len(TOM_FILLS)))]
    # toms / timbale tuned to the key (tonic + fifth) so the drums-only intro already "speaks" the key
    tom_hi_m = in_range(key.root(3), 50, 57)
    rng.uniform(170, 200)
    tom_hi = drums.tom(440 * 2 ** ((tom_hi_m - 69) / 12), decay=0.3, rng=rng)
    rng.uniform(105, 125)
    tom_lo = drums.tom(440 * 2 ** ((tom_hi_m - 5 - 69) / 12), decay=0.4, rng=rng)

    def tom_pat(which):
        def f(c):
            tb = to_drop(c.bar)
            if c.kind == "breakdown":
                return None
            if tb is not None and tb <= 2:
                return ("xxxxxxxxxxxxxxxx" if which == 0 else "x.x.x.x.x.x.x.x.") if tb == 2 else \
                    ("x.x.x.x.x.x....." if which == 0 else "....x...x.......")
            if c.phrase_end or (c.kind == "intro" and c.i in (3, 11)):
                return tf[which]
            if c.kind in ("drop",) or (c.kind == "intro" and c.i >= 8) or (c.kind == "outro" and c.bars_left > 8):
                return tg[which]
            return None
        return f

    song.hits("tom_hi", tom_hi, tom_pat(0), gain_db=-10.0, pan=0.3, sends={"room": 0.2}, humanize=0.1)
    song.hits("tom_lo", tom_lo, tom_pat(1), gain_db=-9.0, pan=-0.3, sends={"room": 0.2}, humanize=0.1)
    rng.uniform(560, 660)
    timb = xm.timbale(440 * 2 ** ((in_range(key.root(5), 74, 81) - 69) / 12), ring=0.5, rng=rng)
    song.hits("timbale", timb, lambda c: "..............x." if c.kind == "drop" and c.i % 4 == 1 else None,
              gain_db=-11.0, pan=0.4, sends={"room": 0.15})

    roll = song.audio("roll", bus="drums", sends={"reverb": 0.15})
    for a, b in windows:
        roll.add(xm.build_roll(song, dem, a, b - a, semis=(0.0, 12.0), vel=(0.3, 1.0), last_beat_rest=True), a,
                 gain_db=-8.0)

    # ---------------------------------------------------------------- bass
    sub = xm.deep_bass(cutoff=320.0, harm=0.25, drive=1.5, attack=0.004, decay=0.3, sustain=0.65, release=0.06)

    def sub_notes(c):
        tb = to_drop(c.bar)
        if c.kind in ("groove", "build") or (c.kind == "outro" and c.bar < drums_only_from):
            if tb is not None and tb <= 2:
                return [(0, 2, root_at(c), 0.9)] if tb == 2 else []
            r = root_at(c) if c.kind != "outro" else roots[0]
            return [(s, ln, r + o, v) for s, ln, o, v in GROOVE_BASS]
        return []

    song.notes("sub", sub, sub_notes, bus="bass", gain_db=-4.0, sidechain=0.5, sc_release_ms=120.0)

    bpm = song.bpm
    wob8 = xm.wobble_bass(bpm, beats=0.5, lo=float(rng.uniform(140, 200)), hi=float(rng.uniform(2200, 3000)) * 0.6,
                          res=0.4, detune=14.0, drive=2.6, sub=0.85)
    wob16 = xm.wobble_bass(bpm, beats=0.25, lo=180.0, hi=1800.0, res=0.45, detune=16.0, drive=2.8, sub=0.85,
                           shape="square")
    wob3 = xm.wobble_bass(bpm, beats=1.0 / 3.0, lo=160.0, hi=1600.0, res=0.4, detune=12.0, drive=2.6, sub=0.85,
                          shape="saw")

    def wob_notes(which):
        def f(c):
            if c.kind != "drop":
                return []
            r = root_at(c)
            turn = c.i % 4 == 3
            if which == 8 and not turn:
                return [(0, 6, r, 1.0), (6, 2, r, 0.85), (8, 8, r, 1.0)] if c.i % 2 == 0 else \
                    [(0, 3, r, 1.0), (3, 3, r, 0.9), (6, 2, r + 12, 0.85), (8, 6, r, 1.0), (14, 2, r, 0.85)]
            if turn and which == (16 if c.i % 8 == 3 else 3):
                return [(0, 4, r, 1.0), (4, 4, r + 7, 0.95), (8, 4, r + 12, 0.95), (12, 4, r + 7, 0.9)] \
                    if which == 16 else [(0, 8, r, 1.0), (8, 4, r + 12, 0.9), (12, 4, r + 7, 0.9)]
            return []
        return f

    for nm, ins, w in (("wobble", wob8, 8), ("wobble16", wob16, 16), ("wobble3", wob3, 3)):
        song.notes(nm, ins, wob_notes(w), bus="bass", gain_db=-6.5, sidechain=0.6, sc_release_ms=130.0)
    # growl layer: the same wobbles an octave up without sub, high-passed (reads on small speakers)
    wtop8 = xm.wobble_bass(bpm, beats=0.5, lo=300.0, hi=2200.0, res=0.45, detune=18.0, drive=3.2, sub=0.0)
    wtop16 = xm.wobble_bass(bpm, beats=0.25, lo=320.0, hi=2400.0, res=0.45, detune=18.0, drive=3.2, sub=0.0,
                            shape="square")
    wtop3 = xm.wobble_bass(bpm, beats=1.0 / 3.0, lo=300.0, hi=2000.0, res=0.4, detune=16.0, drive=3.0, sub=0.0,
                           shape="saw")

    def top_of(f):
        return lambda c: [(s, ln, m + 12, v) for s, ln, m, v in f(c)]

    for nm, ins, w in (("growl", wtop8, 8), ("growl16", wtop16, 16), ("growl3", wtop3, 3)):
        song.notes(nm, ins, top_of(wob_notes(w)), bus="music", gain_db=-6.0, hp=220.0, width=1.3, sidechain=0.6,
                   sc_release_ms=130.0)

    # ---------------------------------------------------------------- lead (Dutch squeak)
    riff = RIFFS[int(rng.integers(len(RIFFS)))]
    riff2 = RIFFS[(RIFFS.index(riff) + 1) % len(RIFFS)]
    lead = xm.GlideSynth(osc="square", voices=2, detune_cents=9.0, spread=0.5, pw=0.2, cutoff=1800.0, res=0.5,
                         env_amt=2.4, env_decay=0.07, attack=0.002, decay=0.12, sustain=0.45, release=0.05,
                         glide_ms=35.0, scoop=-float(rng.uniform(4.0, 7.0)), scoop_ms=22.0, drive=2.2, gain=0.7,
                         seed=song.seed)

    def riff_notes(c, oct_=0):
        ts = tones(chord_at(c), lead_lo)
        pat = riff if c.i % 4 != 3 else riff2
        return [(s, ln, ts[k] + oct_, 1.0 if s % 4 == 0 else 0.85, fl) for s, ln, k, fl in pat]

    def lead_notes(c):
        tb = to_drop(c.bar)
        if c.kind == "drop":
            return riff_notes(c)
        if tb is not None:
            ev = riff_notes(c)
            return [e for e in ev if e[0] < 12] if tb == 1 else ev
        if c.kind == "groove" and c.i >= 4:
            return riff_notes(c)
        return []

    ll = song.line("lead", lead, lead_notes, bus="music", gain_db=-7.0, width=1.3, sidechain=0.45, sc_release_ms=130.0,
                   sends={"delay8": 0.12, "reverb": 0.1})
    pts = [(0, 700.0), (groove.start_bar + 4, 700.0), (groove.end_bar - 0.01, 1500.0)]
    for a, b in windows:
        pts += [(a, 500.0), (b - 0.02, 6000.0), (b, 16000.0)]
        d = song.section_at(b)
        pts += [(d.end_bar - 0.01, 16000.0)]
    ll.automate("lp", pts)
    lead_hi = xm.GlideSynth(osc="saw", voices=3, detune_cents=14.0, spread=0.8, cutoff=4500.0, res=0.3, env_amt=1.5,
                            env_decay=0.06, attack=0.002, decay=0.1, sustain=0.35, release=0.05, glide_ms=35.0,
                            scoop=-5.0, scoop_ms=20.0, drive=1.6, gain=0.6, seed=song.seed + 7)
    song.line("lead_hi", lead_hi, lambda c: riff_notes(c, 12) if c.name == "Drop 2" else [], bus="music",
              gain_db=-14.0, width=1.6, sidechain=0.45, sends={"delay": 0.15})

    # plucks on the dembow (groove / breakdown / outro), brass stabs, pad
    pl = xm.square_pluck(pw=0.35, cutoff=900.0, env_amt=4500.0, decay=0.1)

    def pluck_notes(c):
        if c.kind in ("groove", "breakdown", "drop") or (c.kind == "outro" and c.bar < drums_only_from):
            ch = chord_at(c)
            v = 0.9
            return [(3, 2, ch, v - 0.1), (6, 2, ch, v), (11, 2, ch, v - 0.1), (14, 2, ch, v)]
        return []

    song.notes("pluck", pl, pluck_notes, gain_db=-9.5, width=1.5, sidechain=0.4, sends={"delay8": 0.15})
    brass = inst.brass(cutoff=2200.0, release=0.12)

    def brass_notes(c):
        ch = chord_at(c)
        if c.kind == "breakdown":
            return [(0, 6, ch, 0.85), (8, 2, ch, 0.75), (11, 4, ch, 0.8)]
        if c.name == "Drop 2" and c.i % 2 == 0:
            return [(0, 2, ch, 0.8)]
        return []

    song.notes("brass", brass, brass_notes, gain_db=-11.0, width=1.4, sidechain=0.4, sends={"hall": 0.15})
    pad = song.notes("pad", xm.soft_pad(attack=0.5, cutoff=1500.0),
                     lambda c: [(0, 16, chord_at(c), 0.7)] if c.kind in ("breakdown", "build", "drop") else [],
                     gain_db=-13.0, width=1.6, sidechain=0.5, sends={"hall": 0.25})
    pad.automate("gain_db", song.section_points({"breakdown": 0.0, "build": -4.0, "drop": -3.0}, -60.0))

    shout = xm.chant(vowel="a", vowel_to="e", voices=5, shift=1.1, fall=-2.0, breath=0.25, spread=0.8)
    sp_pitch = in_range(key.root(3), 50, 61)
    song.notes("chant", shout, lambda c: [(12, 3, sp_pitch, 1.0)] if to_drop(c.bar) == 1 else
               ([(14, 2, sp_pitch, 0.9)] if c.kind == "drop" and c.i % 4 == 3 else []),
               bus="vox", gain_db=-8.0, sends={"reverb": 0.25, "delay8": 0.15}, sidechain=0.3)

    # ---------------------------------------------------------------- fx
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.1})
    crash = drums.crash(decay=2.4, rng=rng)
    for d in drops:
        for k in range(0, d.bars, 8):
            fxl.add(crash, d.start_bar + k, gain_db=-9.0 if k == 0 else -12.0)
        fxl.add(fx.impact(2.5, rng=rng), d.start_bar, gain_db=-10.0)
    for a, b in windows:
        fxl.add(fx.riser((b - a) * bar_sec, "noise", rng=rng), b, align="end", gain_db=-13.0)
        fxl.add(fx.reverse_cymbal(bar_sec, rng=rng), b, align="end", gain_db=-11.0)
        fxl.add(xm.siren(bar_sec * 2, f_lo=600.0, f_hi=1500.0, rate=2.0 * bpm / 120.0, rng=rng), b - 2, gain_db=-19.0)
    fxl.add(fx.downlifter(bar_sec * 2, rng=rng), bd.start_bar, gain_db=-12.0)
    for b in (groove.start_bar, outro.start_bar, drums_only_from):
        fxl.add(crash, b, gain_db=-12.0)
    fxl.add(fx.noise_sweep(bar_sec * 4, up=True, rng=rng), groove.start_bar, align="end", gain_db=-20.0)

    # ---------------------------------------------------------------- mix
    song.buses["drums"].eq = [("peak", 3800.0, 1.5, 0.8), ("peak", 220.0, -1.5, 1.0)]
    song.buses["bass"].eq = [("lowshelf", 50.0, 1.5, 0.7), ("peak", 300.0, -2.0, 0.9)]
    song.buses["music"].eq = [("peak", 2600.0, 1.5, 0.7)]
    song.master.lufs = -9.0

    names = ["i", "ii°", "III", "iv", "v", "VI", "VII"]
    progname = "–".join(names[d] for d in degs)
    song.instruments = ["house kick", "dembow snare + rim", "claps", "tribal toms", "timbale", "shaker & hats",
                        "groove sub bass", "wobble bass (8th / 16th / triplet)", "Dutch-house squeaky lead",
                        "supersaw octave lead", "square plucks", "synth brass", "warm pad", "crowd chant",
                        "siren", "snare-roll build", "riser"]
    song.description_he = (f"מומבהטון חם ב-{int(song.bpm)} BPM בסולם {plan['key']}: קיק האוס ישר מתחת לריתם "
                            f"דמבו, גרוב טומים שבטי, ליד \"מצפצף\" בסגנון הדאץ' האוס עם גלישות וקפיצות אוקטבה, "
                            f"ובאס וובל כבד שמשנה קצב (שמיניות, שש-עשריות וטריולות) על לופ {progname}. שני בילדים "
                            f"עם רול סנר מאיץ, טומים וסירנה, ודרופים מלאי אנרגיה — לרגע שבו רוצים להאט את הסט "
                            f"בלי להוריד את האנרגיה.")
    cam = plan.get("camelot", "")
    partners = xm.partners_he(plan)
    song.mix_tips_he = (
        f"טיפ ערבוב: אינטרו של 16 תיבות תופים וטומים בלבד; הבאס והפלאקים נכנסים בתיבה {groove.start_bar + 1} "
        f"(Hot Cue B). הבילד הראשון בתיבה {windows[0][0] + 1}, הדרופ בתיבה {drops[0].start_bar + 1} (Hot Cue D), "
        f"ברייקדאון בתיבה {bd.start_bar + 1} ודרופ שני בתיבה {drops[1].start_bar + 1}. באאוטרו (תיבה "
        f"{outro.start_bar + 1}) הבאס נשאר 8 תיבות ו-8 התיבות האחרונות הן תופים בלבד. {xm.wheel_he(cam)} "
        + (partners + ". " if partners else "")
        + "מעבר מומלץ: מטראק האוס ב-124–128 עושים Echo Out בסוף פרייז ונכנסים לאינטרו ב-108; גם מרגאטון "
          "(90–100 BPM) עדיף לעבור ב-Echo Out או Cut נקי בתחילת פרייז ולא בבלנד ארוך.")
    return song
