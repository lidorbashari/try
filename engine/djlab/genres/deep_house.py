"""Deep House recipe (118–123 BPM).

Warm, round tuned kick; soft swung 16th hats with a rolled-off top, shaker, dusty rim and a roomy
clap/snap on 2 & 4; a deep, smoothly moving bass (classic organ bass or a gliding sine/saw mono
bass); lush minor 9th / 11th chords — a Rhodes-style FM electric piano with stereo tremolo, or
filtered dub chords over a slow pad — plus an airy, breathy vowel "vocal" atmosphere drenched in
long reverb and dotted-8th delay. Gentle energy curve: the breakdown is a soft lift (kick out,
chords and voices bloom, quiet noise riser), never a big EDM build — perfect for long blends.

Flavors (``STYLE_BY_ID`` or ``plan["style"]``):
* ``rhodes`` — Rhodes comping with suitcase tremolo, M1-style organ bass, conga ghost notes.
* ``velvet`` — filtered dub-chord stabs into delay over a velvet pad, gliding mono bass, more
               minimal late-night drums.

DJ rules: 32-bar drums-only intro (bass + chords at bar 33 = Hot Cue B), 32-bar outro whose last
16 bars are drums only, sections on 8-bar phrases, subtle phrase markers (crash/rim fills).
"""
from __future__ import annotations

import numpy as np

from .. import drums, ext_house as eh, fx, instruments as inst
from ..arrangement import Song, clip
from ..dsp import eq_peak
from ..theory import Key
from . import register

STYLE_BY_ID = {"house-01": "rhodes", "house-02": "velvet"}
STYLES = ("rhodes", "velvet")

TEMPLATE = [("Intro", "intro", 32, 3, 0), ("Groove", "groove", 32, 5, 2), ("Breakdown", "breakdown", 16, 4, 0),
            ("Main", "drop", 32, 6, 3), ("Outro", "outro", 32, 3, 0)]

# progressions: (degree, chord size) — size 5 = 9th, 6 = 11th; one chord per 2 bars
PROGRESSIONS = [
    [(0, 5), (3, 5), (0, 5), (3, 5)],          # i9 – iv9 vamp (the deep house classic)
    [(0, 5), (5, 5), (3, 5), (4, 4)],          # i9 – VImaj9 – iv9 – v7
    [(0, 6), (6, 5), (5, 5), (3, 5)],          # i11 – VII9 – VImaj9 – iv9
    [(0, 5), (2, 5), (5, 5), (3, 5)],          # i9 – IIImaj9 – VImaj9 – iv9
]

# comping rhythms: 2 bars of (step, len, vel)
COMP = [
    [(0, 5, 0.85), (6, 2, 0.6), (10, 5, 0.8), (18, 3, 0.7), (22, 6, 0.85), (30, 2, 0.6)],
    [(3, 2, 0.8), (6, 1.5, 0.6), (10, 2, 0.8), (14, 1.5, 0.6), (18, 2, 0.8), (22, 3, 0.75), (27, 2, 0.7)],
    [(0, 10, 0.85), (14, 2, 0.7), (22, 2, 0.7), (26, 6, 0.8)],
]
DUB_RHYTHMS = [[(3, 1, 0.85), (11, 1, 0.65)], [(2, 1, 0.85), (7, 1, 0.6), (10, 1, 0.75)], [(3, 1, 0.8), (14, 1, 0.7)]]

# bass lines (2 bars): (step, len, scale-steps from chord degree, vel, flags)
ORGAN_BASS = [
    [(0, 3, 0, 1.0), (6, 2, 0, 0.75), (10, 2, 4, 0.85), (14, 2, 7, 0.7), (16, 3, 0, 1.0), (22, 2, 0, 0.75),
     (26, 2, 6, 0.8), (30, 2, 4, 0.7)],
    [(2, 4, 0, 1.0), (7, 1, 0, 0.6), (10, 3, 0, 0.9), (14, 2, 2, 0.7), (18, 4, 0, 1.0), (23, 1, 0, 0.6),
     (26, 3, 4, 0.9), (30, 2, 7, 0.7)],
]
GLIDE_BASS = [
    [(0, 6, 0, 1.0, ""), (6, 2, 0, 0.8, "s"), (8, 4, 4, 0.9, ""), (14, 2, 2, 0.8, "s"), (16, 6, 0, 1.0, ""),
     (22, 2, 7, 0.8, "s"), (24, 4, 6, 0.85, ""), (28, 4, 4, 0.8, "s")],
    [(2, 4, 0, 1.0, ""), (6, 4, 0, 0.8, ""), (10, 2, 4, 0.85, "s"), (12, 4, 2, 0.85, ""), (18, 4, 0, 1.0, ""),
     (22, 4, 0, 0.8, ""), (26, 2, -1, 0.85, "s"), (28, 4, 0, 0.85, "")],
]
# breathy vocal atmosphere (4 bars), scale degrees in octave 4
VOX = [
    [(2, 6, 4, 0.8), (10, 4, 2, 0.7), (34, 8, 6, 0.8), (44, 6, 4, 0.7)],
    [(0, 4, 7, 0.8), (6, 6, 6, 0.7), (32, 4, 4, 0.8), (38, 10, 2, 0.75)],
]

RIM = ["..x...x..x....x.", "...x..x....x..x.", "..x..x....x...x."]
HATS = ["gogxgogxgogxgogx", "g.oxg.oxg.oxg.ox", "ggoxggoxggoxgoox"]


@register("deep_house")
def build(plan: dict, rng: np.random.Generator) -> Song:
    style = plan.get("style") or STYLE_BY_ID.get(plan.get("id", ""))
    if style not in STYLES:
        style = str(np.random.default_rng(int(plan.get("seed", 0)) + 211).choice(list(STYLES)))
    song = Song(plan, rng, swing=float(rng.uniform(55.0, 58.0)))
    key: Key = song.key
    song.arrange(TEMPLATE, song.target_bars())
    groove = song.bar("groove")
    song.mix_in_bar = groove
    outro = song.find("outro")
    bd = song.find("breakdown")
    main = song.bar("drop")
    bass_off = outro.start_bar + outro.bars - 16
    rhodes_style = style == "rhodes"

    # ================================================================ drums
    kick_s = drums.kick("deep", tune_hz=eh.kick_tune(key, 44, 58), decay=float(rng.uniform(0.4, 0.46)),
                        click=float(rng.uniform(0.18, 0.3)), drive=float(rng.uniform(1.0, 1.2)), rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown" or c.before("drop", 1):
            return None
        return "x...x...x...x..."

    song.hits("kick", kick_s, kick_pat, gain_db=-2.0, sc_source=True, humanize=0.0)

    hat_p = HATS[int(rng.integers(len(HATS)))]
    hats = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.2}, decay=float(rng.uniform(0.025, 0.04)),
                          tone=float(rng.uniform(0.85, 1.0)))
    song.hits("hats", hats, lambda c: hat_p if not (c.kind == "breakdown" and c.i < 8) else
              ("g.g.g.g.g.g.g.g." if c.kind == "breakdown" else None), gain_db=-12.5, pan=0.3, humanize=0.15,
              lp=13000.0)
    ohat = drums.hat(open_=True, decay=float(rng.uniform(0.2, 0.28)), tone=0.9, rng=rng)
    song.hits("open_hat", ohat, lambda c: "..x...x...x...x." if c.kind in ("groove", "drop") or
              (c.kind == "intro" and c.i >= 16) or (c.kind == "outro" and c.bars_left > 8) else None,
              gain_db=-13.5, pan=-0.2, sends={"room": 0.12}, lp=13000.0)
    shk = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=float(rng.uniform(0.08, 0.11)),
                         tone=float(rng.uniform(5200, 6200)))
    song.hits("shaker", shk, lambda c: "gxgogxgogxgogxgo" if not (c.kind == "intro" and c.i < 4) and
              not (c.kind == "outro" and c.bars_left <= 4) else None, gain_db=-14.5, pan=-0.45, humanize=0.18,
              timing_ms=3.0)

    rim = drums.variants(eh.dusty_rim, 3, rng, jitter={"tone_hz": 0.04}, tone_hz=float(rng.uniform(1400, 1800)))
    rim_p = RIM[int(rng.integers(len(RIM)))]
    song.hits("rim", rim, lambda c: (rim_p if not c.phrase_end else "..x...x..x.xx.x.")
              if c.kind != "breakdown" and not (c.kind == "intro" and c.i < 8) else
              (rim_p if c.kind == "breakdown" and c.i >= 8 else None),
              gain_db=-16.0, pan=0.25, sends={"delay": 0.12, "room": 0.15}, timing_ms=2.0)

    clap = drums.variants(eh.soft_clap, 3, rng, jitter={"tone_hz": 0.05}, tone_hz=float(rng.uniform(1000, 1250)),
                          tail=float(rng.uniform(0.2, 0.28)))
    snap = drums.snap(rng=rng)
    song.hits("clap", clap, lambda c: "....x.......x..." if (c.kind in ("groove", "drop", "outro") or
                                                            (c.kind == "intro" and c.i >= 16)) else None,
              gain_db=-7.5, sends={"reverb": 0.35, "hall": 0.08}, timing_ms=2.0)
    song.hits("snap", snap, lambda c: "....x.......x..." if c.kind == "drop" or (c.kind == "breakdown" and c.i >= 8)
              else None, gain_db=-14.0, pan=0.1, sends={"reverb": 0.3})

    if rhodes_style:
        congas = [drums.conga(float(rng.uniform(200, 230)), "open", rng=rng),
                  drums.conga(float(rng.uniform(280, 310)), "mute", rng=rng)]
        cp = ["......x...x..x..", "...x......x.x..."][int(rng.integers(2))]
        song.hits("conga", congas, lambda c: cp if c.kind in ("drop",) or (c.kind == "groove" and c.i >= 16)
                  or (c.kind == "intro" and c.i >= 24) else None, gain_db=-16.0, pan=-0.5, humanize=0.15,
                  timing_ms=3.0, sends={"room": 0.2})
    else:
        ride = drums.ride(decay=1.4, bell=0.3, rng=rng)
        song.hits("ride", ride, lambda c: "..x...x...x...x." if c.kind == "drop" else None, gain_db=-21.0, pan=0.35,
                  lp=12000.0)
        tops = drums.perc_blip(float(rng.uniform(900, 1200)), 0.03, fm_index=1.2, rng=rng)
        song.hits("perc", tops, lambda c: "......x.......x." if c.kind in ("groove", "drop") or
                  (c.kind == "intro" and c.i >= 24) else None, gain_db=-18.0, pan=0.55, sends={"delay": 0.2})

    song.hits("rim_roll", rim[0], lambda c: eh.snare_roll(c, 2, ("x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx")),
              gain_db=-17.0, sends={"reverb": 0.3}).automate("gain_db", eh.ramp_into(song, "drop", 2, -8.0, 0.0))

    # ================================================================ harmony
    prog = PROGRESSIONS[int(rng.integers(len(PROGRESSIONS)))]
    chords = eh.voice_progression(key, [d for d, _ in prog], [s for _, s in prog], center=63 if rhodes_style else 60)
    root = eh.bass_root(key, 28)

    def chord_i(c):
        return (c.i // 2) % len(prog)

    def bass_note(deg_):
        n = key.degree(deg_, 1)
        while n < root - 3:
            n += 12
        while n > root + 12:
            n -= 12
        return n

    def harmony_on(c):
        return c.kind in ("groove", "breakdown", "drop") or (c.kind == "outro" and c.i < 8)

    # ================================================================ bass
    def bass_window(c):
        return c.kind not in ("intro", "breakdown") and c.bar < bass_off

    if rhodes_style:
        riff = ORGAN_BASS[int(rng.integers(len(ORGAN_BASS)))]

        def bass_notes(c):
            if not bass_window(c):
                return []
            cd = prog[chord_i(c)][0]
            off = (c.i % 2) * 16
            ev = [(s - off, l, bass_note(cd + st), v) for s, l, st, v in riff if off <= s < off + 16]
            return [e for e in ev if e[0] < 8] if c.before("drop", 1) else ev

        bass = song.notes("bass", inst.organ_bass(drawbars=(1.0, 0.45, 0.18, 0.06)), bass_notes, bus="bass",
                          gain_db=-3.0, sidechain=0.4, sc_release_ms=160.0, humanize=0.04)
        bass.automate("lp", [(groove, 450), (groove + 8, 1400), (outro.start_bar, 1400), (bass_off, 300)])
    else:
        riff = GLIDE_BASS[int(rng.integers(len(GLIDE_BASS)))]

        def bass_notes(c):
            if not bass_window(c):
                return []
            cd = prog[chord_i(c)][0]
            off = (c.i % 2) * 16
            ev = [(s - off, l, bass_note(cd + st), v, fl) for s, l, st, v, fl in riff if off <= s < off + 16]
            return [e for e in ev if e[0] < 8] if c.before("drop", 1) else ev

        ms = inst.MonoSynth(wave="saw", cutoff=float(rng.uniform(150, 190)), res=0.12, env_mod=1.0, decay=0.3,
                            accent=0.2, glide_ms=float(rng.uniform(80, 110)), drive=1.2, sustain=0.85)
        bass = song.line("bass", ms, bass_notes, gain_db=-4.0, sidechain=0.4, sc_release_ms=160.0)
        bass.automate("cutoff", [(groove, 120), (groove + 16, 190), (outro.start_bar, 190), (bass_off, 110)])
    song.notes("bd_sub", inst.sub_bass(harmonics=0.05),
               lambda c: [(0, 31.5, bass_note(prog[chord_i(c)][0]), 0.55)] if c.kind == "breakdown" and c.i % 2 == 0
               and c.bars_left > 2 else [], bus="bass", gain_db=-13.0)

    # ================================================================ keys / chords
    if rhodes_style:
        comp = COMP[int(rng.integers(len(COMP)))]
        rh = eh.rhodes(bright=float(rng.uniform(0.6, 0.72)), bark=float(rng.uniform(0.45, 0.6)), drive=0.3)

        def keys_notes(c):
            if not harmony_on(c):
                return []
            ch = chords[chord_i(c)]
            off = (c.i % 2) * 16
            return [(s - off, l, ch, v) for s, l, v in comp if off <= s < off + 16]

        keys = song.notes("rhodes", rh, keys_notes, gain_db=-11.5, sidechain=0.3, sc_release_ms=180.0, hp=170.0,
                          sends={"reverb": 0.22, "delay": 0.12}, humanize=0.08,
                          fx=[eh.autopan(song.bpm, 0.5, 0.35), lambda x: eq_peak(eq_peak(x, 300.0, -3.5, 0.8), 1600.0, 2.5, 0.8)],
                          timing_ms=4.0)
        keys.automate("lp", [(groove, 900), (groove + 16, 5000), (bd.start_bar, 2500), (bd.end_bar - 0.01, 7000),
                             (main, 7000), (outro.start_bar, 6000), (outro.start_bar + 8, 800)])
    else:
        dub_r = DUB_RHYTHMS[int(rng.integers(len(DUB_RHYTHMS)))]
        dub = inst.dub_chord(cutoff=float(rng.uniform(600, 850)), env_amt=float(rng.uniform(1300, 2000)), decay=0.25)

        def dub_notes(c):
            if not harmony_on(c):
                return []
            ch = chords[chord_i(c)]
            return [(s, l, ch, v) for s, l, v in dub_r]

        keys = song.notes("dub_chords", dub, dub_notes, gain_db=-7.5, sidechain=0.4,
                          sends={"delay": 0.4, "hall": 0.25}, width=1.4, humanize=0.05)
        keys.automate("lp", [(groove, 700), (groove + 16, 3500), (bd.start_bar, 1800), (bd.end_bar - 0.01, 5000),
                             (main, 5000), (outro.start_bar, 4000), (outro.start_bar + 8, 700)])

    pad_inst = eh.soft_pad(attack=float(rng.uniform(1.5, 2.5)), release=3.0, cutoff=float(rng.uniform(1100, 1500)),
                           air=0.35, detune_cents=6.0)
    pad = song.notes("pad", pad_inst, lambda c: [(0, 31.0, chords[chord_i(c)], 0.8)] if harmony_on(c) and c.i % 2 == 0
                     else [], gain_db=-17.0 if rhodes_style else -11.0, sends={"hall": 0.4}, width=0.9,
                     sidechain=0.3, hp=200.0)
    pad.automate("gain_db", song.section_points({"groove": -3.0, "breakdown": 2.0, "drop": 0.0, "outro": -4.0}, -40.0,
                                                ramp_bars=4))
    pad.automate("lp", [(groove, 600), (bd.start_bar, 1400), (bd.end_bar - 0.01, 4500), (main, 2600),
                        (outro.start_bar, 2000), (outro.start_bar + 8, 600)])

    # ================================================================ airy vocal atmosphere
    deg = key.degree
    vx = VOX[int(rng.integers(len(VOX)))]
    vclip = clip([(s, l, deg(d, 4), v) for s, l, d, v in vx], 4)
    voice = eh.chant(vowel="a", vowel_to="o", shift=float(rng.uniform(1.08, 1.18)), voices=2, vibrato=0.25,
                     breath=0.3, attack=0.12, release=0.5, scoop=-0.8)
    song.notes("vox_air", voice, lambda c: vclip(c) if c.kind == "breakdown" or (c.kind == "drop" and c.phrase % 2 == 1)
               or (c.kind == "groove" and c.i >= c.section.bars - 8) else [], bus="vox", gain_db=-11.0,
               sidechain=0.25, sends={"hall": 0.5, "delay": 0.3}, width=1.3, hp=300.0)
    chop = inst.vocal_chop(vowel="o", vowel_to="a", shift=1.15, scoop=-1.5, breath=0.15)
    song.notes("vox_chop", chop, lambda c: [(14, 1.5, deg(4, 4), 0.85)] if c.kind == "drop" and c.i % 4 == 3 else [],
               bus="vox", gain_db=-10.0,
               sends={"delay": 0.45, "hall": 0.3})

    # ================================================================ fx & mix
    eh.transitions(song, rng, crash_db=-12.0, impact=False, riser_db=-14.0, riser_kind="noise", downlifter=False,
                   reverse=True, drop_crash_every=16, sends={"hall": 0.2})
    song.returns["hall"].decay = 4.5
    song.returns["reverb"].decay = 2.6
    song.returns["delay"].feedback = 0.45
    song.buses["drums"].eq = [("peak", 2500.0, 1.0, 0.8)]
    song.buses["music"].eq = [("peak", 360.0, -2.5, 0.8), ("peak", 2200.0, 1.5, 0.8)]
    song.master.lufs = -9.0

    # ================================================================ metadata
    k = plan["key"]
    if rhodes_style:
        song.description_he = (f"דיפ-האוס חמים ב-{int(song.bpm)} BPM בסולם {k}: אקורדי רודס עם טרמולו סטריאו, באס "
                               f"אורגן עגול וקיק רך, היי-האטים מתנדנדים ואווירה ווקאלית נושמת עם ריוורב ארוך. "
                               f"מוזיקת שקיעה לחימום רגוע.")
        song.instruments = ["warm deep kick", "swung soft hats", "open hat", "shaker", "dusty rim", "roomy clap + snap",
                            "conga ghost notes", "M1-style organ bass", "Rhodes-style FM e-piano (tremolo)",
                            "minor 9th chords", "filtered pad", "breathy vowel atmosphere", "vocal chop"]
    else:
        song.description_he = (f"דיפ-האוס קטיפתי לשעות הלילה ב-{int(song.bpm)} BPM בסולם {k}: אקורדים דאביים מפולטרים "
                               f"שנבלעים בדיליי, פד רך, באס עמוק עם גלישות חלקות ותופים מינימליים. אנרגיה נמוכה "
                               f"ועדינה, מושלם למעברים ארוכים.")
        song.instruments = ["warm deep kick", "swung soft hats", "open hat", "shaker", "dusty rim", "roomy clap + snap",
                            "ride", "tops blip", "gliding mono bass", "filtered dub chords", "velvet pad",
                            "breathy vowel atmosphere", "vocal chop"]
    song.mix_tips_he = (song.auto_mix_tips_he() + " הטראק עדין ואחיד — מתאים למעבר ארוך של 32 תיבות עם החלפת באסים "
                        "(Bass Swap) בתחילת פרייז.")
    return song
