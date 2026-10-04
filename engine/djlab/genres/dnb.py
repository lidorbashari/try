"""Drum & Bass recipe (170–176 BPM): energetic reese DnB (default) and liquid DnB (plan ``genre``
contains "Liquid").

Drums: two-step pattern (kick on 1 and the "and" of 3, snare on 2 and 4), ghost snares, shuffled 16th
hats, plus a synthesised **amen-like break layer** (vintage kit through a squashed, saturated
``break`` bus) that is re-sequenced per bar with fills and edits.
Bass: reese with movement (3 detuned drifting saws → breathing ladder LP → chorus) over a separate
clean sine sub (energetic); warm round sub with glides (liquid).
Music: minor stabs + vocal chops + atmos pad (energetic); lush jazzy pads (min9 / maj7), Rhodes
comping, a gentle Rhodes melody and a synthetic rain texture (liquid).

DJ rules: 32-bar intro (drums only for 16 bars; sub/reese + atmosphere from bar 17), drop on bar 33,
32-bar breakdown, second drop, 32-bar outro whose last 16 bars are drums only.
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from .. import ext_breadth as xb
from ..arrangement import Song
from ..theory import chord as mkchord, voice_lead
from . import register

TPL = [("Intro", "intro", 32, 5, 0), ("Drop", "drop", 48, 9, 2), ("Breakdown", "breakdown", 32, 5, 0),
       ("Drop 2", "drop", 32, 9, 1), ("Outro", "outro", 32, 5, 0)]

KICKS = ["x.........x.....", "x.........x.....", "x.x.......x.....", "x.........xx...."]
SNARE = "....X.......X..."
GHOSTS = ["......g..g....g.", ".......g.g.....g", "...g...g......g.", "......g...g..g.."]
HATS = ["xgxgxgxgxgxgxgxg", "x.xgx.xgx.xgx.xg", "xgxxxgxxxgxxxgxx"]
# amen-like break (own patterns): per bar kick / snare / ghost / hat
BREAK_A = ("x.x.......xx....", "....x.......x...", ".......g.g.....g", "x.x.x.x.x.x.x.x.")
BREAK_B = ("x.x.......x.....", "....x.......x...", ".......g.g..g.g.", "x.x.x.x.x.x.x.x.")
BREAK_FILL = ("x.x.......x.....", "....x..x.x.xx.xx", "......g.g.g.....", "x.x.x.x.x.x.....")
BREAK_EDIT = ("x...x.....x.....", "..x.x..x....x.x.", "g.....g.........", "x.xxx.x.x.xxx.x.")

# reese riffs (4 bars = 64 steps): (step, len, scale degree, octave offset)
REESE_RIFFS = [
    [(0, 10, 0, 0), (10, 6, 0, 0), (16, 6, 0, 0), (22, 4, 2, 0), (26, 6, 0, 0),
     (32, 10, 5, -1), (42, 6, 5, -1), (48, 8, 6, -1), (56, 4, 4, -1), (60, 4, 6, -1)],
    [(0, 6, 0, 0), (6, 4, 0, 1), (10, 6, 0, 0), (16, 10, 0, 0), (26, 6, 6, -1),
     (32, 6, 5, -1), (38, 4, 5, 0), (42, 6, 5, -1), (48, 10, 3, -1), (58, 6, 4, -1)],
]


def _bar_break(c):
    if c.phrase_end:
        return BREAK_FILL
    if c.i % 8 == 3:
        return BREAK_EDIT
    return BREAK_A if c.i % 2 == 0 else BREAK_B


@register("dnb")
def build(plan: dict, rng: np.random.Generator) -> Song:
    liquid = "liquid" in str(plan.get("genre", "")).lower()
    song = Song(plan, rng, swing=float(rng.choice([52.0, 54.0])) if liquid else 51.0)
    key = song.key
    song.arrange(TPL, song.target_bars())
    secs = song.sections
    intro, outro = song.find("intro"), song.find("outro")
    drop1, bd, drop2 = song.find("drop"), song.find("breakdown"), song.find("drop", 1)
    bass_in = 16
    song.mix_in_bar = bass_in
    bass_off = outro.start_bar + outro.bars - 16
    bar_sec = song.grid.bar_sec
    step = song.grid.step_sec

    def full(c):
        return c.kind == "drop"

    # ---------------------------------------------------------------- main drums (two-step)
    k_hz = xb.kick_tune(key, 43.0, 62.0)
    kick = drums.kick("dnb", tune_hz=k_hz, decay=float(rng.uniform(0.2, 0.26)) if not liquid else 0.28,
                      click=float(rng.uniform(0.6, 0.8)) if not liquid else 0.45, drive=1.8 if not liquid else 1.3, rng=rng)
    kpat = [KICKS[int(rng.integers(len(KICKS)))], KICKS[0]]

    def kick_pat(c):
        if c.kind == "breakdown":
            return None if c.bars_left > 8 or liquid else ("x.........x....." if c.i % 2 == 0 else None)
        if c.before("drop", 1):
            return "x..............."
        if c.kind == "intro" and c.i < 8:
            return None
        return kpat[c.i % 2]

    song.hits("kick", kick, kick_pat, gain_db=-2.0, sc_source=True, humanize=0.0)
    snr = xb.layered_snare(rng, tone_hz=float(rng.uniform(185, 215)), snappy=0.85, decay=0.16 if not liquid else 0.2,
                           clap_amt=0.6 if not liquid else 0.4, crack_hz=float(rng.uniform(1700, 2100)))
    ghost = drums.snare(tone_hz=230.0, snappy=0.6, decay=0.08, kind="tight", rng=rng)
    gpat = GHOSTS[int(rng.integers(len(GHOSTS)))]

    def snare_pat(c):
        if c.kind == "breakdown" and c.bars_left > 8:
            return None if not liquid or c.i < 8 else "............X..."
        if c.kind == "breakdown":
            k = c.bars_left
            return ["....X.......X...", "....X.......X...", "..X...X...X...X.", "..X...X...X...X.",
                    "X.X.X.X.X.X.X.X.", "X.X.X.X.X.X.X.X.", "XXXXXXXXXXXXXXXX", "rrrrrrrrrrrrrrrr"][8 - k]
        if c.kind == "intro" and c.i < 4:
            return None
        if c.before("drop", 1):
            return "....X.......XXXX"
        return SNARE if not c.phrase_end else "....X.......X.XX"

    song.hits("snare", snr, snare_pat, gain_db=-5.0, sends={"room": 0.15, "reverb": 0.08 if not liquid else 0.18})
    song.hits("ghost", ghost, lambda c: gpat if c.kind in ("drop", "outro") or (c.kind == "intro" and c.i >= 8) else None,
              gain_db=-15.0, pan=0.1, humanize=0.2, timing_ms=1.5)
    hats = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.2}, decay=float(rng.uniform(0.025, 0.04)),
                          tone=float(rng.uniform(1.05, 1.3)))
    hpat = HATS[int(rng.integers(len(HATS)))]

    def hat_pat(c):
        if c.kind == "breakdown" and c.bars_left > 8:
            return None if not liquid else "x.x.x.x.x.x.x.x."
        return hpat

    song.hits("hats", hats, hat_pat, gain_db=-16.0, pan=0.4, humanize=0.15, swing=56.0)
    oh = drums.hat(open_=True, decay=0.12, tone=1.1, rng=rng)
    song.hits("open_hat", oh, lambda c: "......x.......x." if full(c) and c.i % 2 == 1 else None,
              gain_db=-13.0, pan=-0.3)
    ride = drums.ride(decay=1.1, bell=0.6, rng=rng)
    song.hits("ride", ride, lambda c: "x...x...x...x..." if full(c) and c.i >= 16 else None, gain_db=-18.0, pan=0.4)
    shk = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=0.05)
    song.hits("shaker", shk, lambda c: "gxgogxgogxgogxgo" if c.kind != "breakdown" or liquid else None,
              gain_db=-19.0 if not liquid else -17.0, pan=-0.5, humanize=0.2, swing=56.0)

    # ---------------------------------------------------------------- amen-like synthesised break layer
    kit = xb.break_kit(rng, tune=float(rng.uniform(0.95, 1.08)))
    song.buses["break"] = xb.break_bus(hp_hz=140.0 if not liquid else 180.0, sat=0.5 if not liquid else 0.35)

    def brk(idx):
        def p(c):
            if c.kind == "breakdown" and c.bars_left > 8:
                return None
            if c.kind == "outro" and c.bars_left <= 4:
                return None
            return _bar_break(c)[idx]
        return p

    bgain = -6.0 if not liquid else -9.0
    song.hits("brk_kick", kit["kick"], brk(0), bus="break", gain_db=bgain - 4, humanize=0.08)
    song.hits("brk_snare", kit["snare"], brk(1), bus="break", gain_db=bgain, humanize=0.1, sends={"room": 0.2})
    song.hits("brk_ghost", kit["ghost"], brk(2), bus="break", gain_db=bgain - 6, humanize=0.2)
    song.hits("brk_hat", [kit["hat"], kit["ohat"]], brk(3), bus="break", gain_db=bgain - 8, humanize=0.15, pan=0.2)

    # ---------------------------------------------------------------- harmony
    if liquid:
        r = key.root(3)
        opts = [[("min9", 0), ("maj7", 8), ("min9", 5), ("min7", 7)],
                [("maj7", 8), ("min7", 7), ("min9", 0), ("min9", 0)],
                [("min9", 0), ("maj7", 3), ("maj7", 8), ("min7", 7)]]
        spec = opts[int(rng.integers(len(opts)))]
        chords, prev = [], None
        for q, off in spec:
            ch = voice_lead(prev, mkchord(r + off, q)[:5], center=key.root(4) - 3)
            chords.append(ch)
            prev = ch
        roots = [xb.note_in_range((key.root_pc + off) % 12, 41.0) for _, off in spec]
    else:
        degs = [[0, 5, 6, 4], [0, 0, 5, 6], [0, 3, 5, 6]][int(rng.integers(3))]
        chords, prev = [], None
        for d in degs:
            ch = voice_lead(prev, key.chord(d, 3, 3), center=key.root(4))
            chords.append(ch)
            prev = ch
        roots = [xb.note_in_range(key.degree(d, 1) % 12, 41.0) for d in degs]

    def chord_i(c):
        return (c.i // 2) % 4

    def bass_on(c):
        if c.kind == "intro":
            return c.i >= bass_in
        if c.kind == "outro":
            return c.bar < bass_off
        if c.kind == "breakdown":
            return c.i >= 16 and c.bars_left > 1
        return True

    # ---------------------------------------------------------------- bass
    if not liquid:
        riff = REESE_RIFFS[int(rng.integers(len(REESE_RIFFS)))]
        broot = xb.note_in_range(key.root_pc, 41.0)
        rnotes = []
        for s, l, d, o in riff:
            m = broot + (key.degree(d, 0) - key.root(0)) + 12 * o
            while m < 26:          # fold into D1..C#2 (37–69 Hz): the sub carries the fundamental
                m += 12
            while m >= 38:
                m -= 12
            rnotes.append((s, l, m))

        def reese_notes(c):
            if not bass_on(c):
                return []
            off = (c.i % 4) * 16
            out = []
            for s, l, m in rnotes:
                if off <= s < off + 16:
                    fl = "s" if (s + l) % 16 != 0 and l >= 6 else ""
                    out.append((s - off, l - 0.25, m, 0.95, fl))
            if c.before("drop", 1) or c.before("breakdown", 1):
                out = [e for e in out if e[0] < 8]
                out = [(s, min(l, 8 - s), m, v, "") for s, l, m, v, _ in out]
            return out

        reese = song.add(xb.SynthLine("reese", xb.Reese(detune=float(rng.uniform(15, 20)),
                                                         cutoff=float(rng.uniform(550, 750)), res=0.28, drive=2.2,
                                                         move=0.6, move_bars=2.0, env=1.0, chorus_mix=0.35,
                                                         hp_hz=85.0, dist=0.4),
                                      reese_notes, bus="bass", gain_db=-3.0, sidechain=0.5, sc_release_ms=120.0))
        rp = [(bass_in, 0.25), (intro.end_bar - 0.01, 0.8), (intro.end_bar, 1.0)]
        rp += [(bd.start_bar + 16, 0.3), (bd.end_bar - 0.01, 0.9), (bd.end_bar, 1.0)]
        rp += [(outro.start_bar, 1.0), (bass_off, 0.3)]
        reese.automate("cutoff", [(b, v * 950.0) for b, v in rp])
        sub = song.add(xb.SynthLine("sub", xb.SubLine(harm=0.08, drive=1.2, glide_ms=60.0), reese_notes, bus="bass",
                                    gain_db=-4.0, sidechain=0.55, sc_release_ms=110.0))
        sub.automate("gain_db", [(bass_in, -8.0), (intro.end_bar - 0.01, -3.0), (intro.end_bar, 0.0)])
    else:
        def sub_notes(c):
            if not bass_on(c):
                return []
            k = chord_i(c)
            r0 = roots[k]
            if c.i % 2 == 0:
                return [(0, 10, r0, 0.95, ""), (10, 6, r0, 0.85, "")]
            nxt = roots[(k + 1) % 4]
            return [(0, 6, r0, 0.9, ""), (6, 4, r0 + 12 if r0 < 48 else r0, 0.7, ""), (10, 6, r0, 0.85, "s"),
                    (15.5, 0.5, nxt, 0.8, "")][:3 if nxt == r0 else 4]

        sub = song.add(xb.SynthLine("sub", xb.SubLine(harm=0.22, drive=1.6, glide_ms=80.0, release_ms=40.0), sub_notes,
                                    bus="bass", gain_db=-3.0, sidechain=0.45, sc_release_ms=140.0))
        sub.automate("gain_db", [(bass_in, -10.0), (intro.end_bar - 0.01, -3.0), (intro.end_bar, 0.0)])

    # ---------------------------------------------------------------- music
    if liquid:
        pad_i = inst.pad(attack=1.4, release=2.0, cutoff=2400.0, detune=0.22, warmth=0.75, lfo_rate=0.1)
        song.notes("pad", pad_i, lambda c: [(0, 31.5, chords[chord_i(c)], 0.75)]
                   if c.i % 2 == 0 and (c.kind in ("drop", "breakdown") or (c.kind == "intro" and c.i >= 16)
                                        or (c.kind == "outro" and c.i < 16)) else [],
                   gain_db=-12.0, sends={"hall": 0.4}, width=1.6, sidechain=0.35, hp=180.0)
        rh = xb.rhodes(bright=0.5, tremolo=0.25, trem_rate=float(rng.uniform(3.5, 5.0)), bark=0.3)
        comp = [[(0, 5, 0.75), (6, 3, 0.55), (10, 5, 0.65)], [(0, 3, 0.7), (3, 3, 0.5), (8, 6, 0.65), (14, 2, 0.45)],
                [(2, 4, 0.65), (10, 4, 0.6)]][int(rng.integers(3))]

        def rhodes_notes(c):
            on = c.kind in ("drop", "breakdown") or (c.kind == "intro" and c.i >= 16) or (c.kind == "outro" and c.i < 16)
            if not on:
                return []
            ch = chords[chord_i(c)]
            return [(s, l, ch[1:] if len(ch) > 4 else ch, v) for s, l, v in comp]

        song.notes("rhodes", rh, rhodes_notes, gain_db=-8.5, sends={"reverb": 0.2, "delay": 0.12}, width=1.3,
                   sidechain=0.3)
        # gentle melody (Rhodes, higher register) — chord tones of the bar
        mel_r = [[(0, 6, 2), (6, 2, 1), (8, 8, 0)], [(0, 4, 3), (4, 4, 2), (8, 4, 1), (12, 4, 2)],
                 [(2, 6, 4), (8, 2, 3), (10, 6, 2)], [(0, 12, 1), (12, 4, 0)]]
        mel_i = xb.rhodes(bright=0.7, tremolo=0.15, bark=0.2)

        def mel_notes(c):
            if not (c.kind == "breakdown" and c.i >= 8 or (c.kind == "drop" and c.name == "Drop 2")
                    or (c.kind == "drop" and c.i >= 16)):
                return []
            ch = sorted(chords[chord_i(c)])
            tones = [n + 12 for n in ch]
            cell = mel_r[(c.i // 2 + c.i % 2) % 4]
            return [(s, l, tones[min(t, len(tones) - 1)], 0.65) for s, l, t in cell]

        song.notes("melody", mel_i, mel_notes, gain_db=-11.0, sends={"delay": 0.3, "hall": 0.25}, pan=0.15, width=1.2)
        # vocal 'ooh' pad (formant) in breakdown + drop 2
        ooh = inst.vocal_chop(vowel="o", vowel_to="u", shift=1.1, vibrato=0.4, breath=0.15, scoop=-0.5, release=0.4)
        song.notes("ooh", ooh, lambda c: [(0, 30, sorted(chords[chord_i(c)])[-1] + 12, 0.6)]
                   if c.i % 2 == 0 and (c.kind == "breakdown" or (c.name == "Drop 2" and c.i >= 16)) else [],
                   bus="vox", gain_db=-14.0, sends={"hall": 0.5, "delay": 0.2})
        rain = xb.bar_texture(lambda bar, n, r: xb.rain_bar(n, r, density=10.0, bed=0.12,
                                                            drops=0.0 if bar < 16 else 1.0),
                              song.seed + 7)
        song.custom("rain", rain, bus="fx", gain_db=-24.0, width=1.5)
    else:
        stab_i = inst.stab(wave="saw", cutoff=float(rng.uniform(700, 1000)), env_amt=3500.0, decay=0.12)
        stab_r = [[(3, 1, 0.9), (6, 1, 0.7)], [(2, 1, 0.9), (10, 1, 0.8), (13, 1, 0.6)], [(6, 1, 0.9), (14, 1, 0.7)]]
        sr_ = stab_r[int(rng.integers(len(stab_r)))]
        song.notes("stabs", stab_i, lambda c: [(s, l, chords[chord_i(c)], v) for s, l, v in sr_]
                   if c.kind == "drop" and c.i % 4 in (1, 3) else [],
                   gain_db=-9.5, sidechain=0.4, sends={"delay": 0.3, "reverb": 0.15}, width=1.7)
        pad_i = inst.pad(attack=1.2, cutoff=1500.0, detune=0.3, warmth=0.6)
        song.notes("pad", pad_i, lambda c: [(0, 31.5, chords[chord_i(c)], 0.7)]
                   if c.i % 2 == 0 and (c.kind == "breakdown" or (c.kind == "intro" and c.i >= 16)) else [],
                   gain_db=-12.0, sends={"hall": 0.4}, width=1.6, hp=160.0)
        vox_i = inst.vocal_chop(vowel="a", vowel_to="e", shift=1.15, scoop=-1.2)
        vph = [(0, 2, 4), (3, 1, 4), (6, 2, 6), (10, 3, 4), (14, 2, 2)]

        def vox_notes(c):
            if not ((c.kind == "breakdown" and 8 <= c.i < 24) or (c.kind == "drop" and c.i >= 16 and c.i % 4 < 2)):
                return []
            return [(s, l, key.degree(d, 4), 0.85) for s, l, d in vph] if c.i % 2 == 0 else []

        song.notes("vox", vox_i, vox_notes, bus="vox", gain_db=-9.0, sends={"delay": 0.3, "reverb": 0.25})

    # ---------------------------------------------------------------- FX
    fxl = song.audio("fx_hits", bus="fx", sends={"hall": 0.12})
    crash = drums.crash(decay=2.4, rng=rng)
    for s in secs:
        if s.kind in ("drop", "outro"):
            fxl.add(crash, s.start_bar, gain_db=-8.0)
        if s.kind == "drop":
            fxl.add(fx.impact(2.5, rng=rng), s.start_bar, gain_db=-7.0)
            for b in range(s.start_bar + 16, s.end_bar, 16):
                fxl.add(crash, b, gain_db=-11.0)
        if s.kind == "breakdown":
            fxl.add(fx.downlifter(bar_sec * 4, rng=rng), s.start_bar, gain_db=-11.0)
            fxl.add(fx.riser(bar_sec * 8, "both" if not liquid else "noise", f_lo=250, f_hi=11000, rng=rng),
                    s.end_bar, align="end", gain_db=-9.0)
            fxl.add(fx.reverse_cymbal(bar_sec, rng=rng), s.end_bar, align="end", gain_db=-10.0)
    fxl.add(fx.riser(bar_sec * 8, "noise", f_lo=300, f_hi=10000, rng=rng), drop1.start_bar, align="end", gain_db=-10.0)
    fxl.add(fx.reverse_cymbal(bar_sec * 2, rng=rng), drop1.start_bar, align="end", gain_db=-10.0)
    fxl.add(crash, bass_in, gain_db=-12.0)

    # ---------------------------------------------------------------- mix
    song.buses["drums"].eq = [("peak", 4000.0, 2.0, 0.8), ("peak", 200.0, 1.0, 1.0)]
    song.buses["drums"].width = 1.2
    song.buses["music"].width = 1.3
    song.returns["room"].decay = 0.6
    song.returns["delay"].beats = 0.75
    song.master.lufs = -9.0
    if liquid:
        song.description_he = (
            f"ליקוויד דראם אנד בייס ב-{int(song.bpm)} BPM בסולם {plan['key']}: סאב חם ועגול עם גלישות, פדים ג'אזיים "
            f"עשירים (אקורדי min9 ו-maj7), רודס שמנגן קומפינג ומנגינה עדינה, מרקם של גשם ברקע ותופי ברייקביט "
            f"מתגלגלים (קיק ב-1, סנר ב-2 וב-4, גוסטים וברייק סינתטי בסגנון אמן). אווירה של לילה רטוב בעיר.")
        song.instruments = ["two-step DnB drums", "synthesised amen-like break", "warm sine sub with glides",
                            "jazzy min9/maj7 pads", "Rhodes comping & melody", "vocal 'ooh' pad", "rain texture"]
    else:
        song.description_he = (
            f"דראם אנד בייס אנרגטי ב-{int(song.bpm)} BPM בסולם {plan['key']}: תופי טו-סטפ חדים (קיק ב-1, סנר ב-2 וב-4) "
            f"עם גוסט-נוטס והיי-האטים בשאפל, שכבת ברייק סינתטית בסגנון אמן, ובס ריס (Reese) שזז ונושם — סאוטות "
            f"מנוגדות, פילטר וכורוס — מעל סאב נקי. ווקאל צ'ופים וסטאבים מינוריים. טראק פיק.")
        song.instruments = ["two-step DnB drums", "synthesised amen-like break", "moving reese bass", "clean sine sub",
                            "minor stabs", "atmos pad", "formant vocal chops", "risers & impacts"]
    from ..theory import compatible_keys
    cam = plan["camelot"]
    song.mix_tips_he = (
        f"טיפ ערבוב: 16 תיבות ראשונות תופים בלבד; הסאב{' והריס' if not liquid else ' והפדים'} נכנסים בתיבה "
        f"{bass_in + 1} (Hot Cue B) והדרופ בתיבה {drop1.start_bar + 1} (Hot Cue D). בדראם אנד בייס מקובל לעשות "
        f"Double Drop: מסנכרנים את הדרופ של הטראק הנכנס עם הדרופ או האאוטרו של היוצא, והורדת Low בטראק אחד חובה. "
        f"ברייקדאון בתיבה {bd.start_bar + 1}, דרופ 2 בתיבה {drop2.start_bar + 1}, האאוטרו מתחיל בתיבה "
        f"{outro.start_bar + 1} ו-16 התיבות האחרונות תופים בלבד. Rekordbox עלול לזהות {int(song.bpm) // 2} BPM "
        f"(חצי טמפו) — אם כך, תקנו ל-{int(song.bpm)}. שכנים ב-Camelot: {cam} ↔ {', '.join(compatible_keys(cam)[1:4])}.")
    return song
