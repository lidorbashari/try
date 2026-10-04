"""Hip-Hop recipe: boom bap (85–98 BPM) and trap (130–150 BPM, half-time feel).

The plan's ``genre`` field picks the variant: anything containing "trap" → trap, else boom bap.
A boom-bap plan whose title/mood mentions night / dark / cypher / midnight gets the darker palette.

Boom bap brief
--------------
* MPC-style swung 16ths (swing 58–62): dusty knocking kick ("a-of-2 / and-of-3" patterns), crisp
  snare + tight clap on 2 and 4 with ghost rims, swung hats with ghost 16ths, tambourine in hooks,
  vinyl crackle + hiss bed, everything through a 12-bit "sampler" (bit-reduction, low-pass, tape).
* Music: a synthesized "sampled" chord loop — FM Rhodes with tape wow playing jazzy 9th/maj7
  voicings (i9–bVImaj7–iv9–V7 and friends, or Phrygian-dark i9–bIImaj7 for the night variant);
  deep round bass locked to the kick; a short hook motif (breathy jazz flute + vibes, or dark FM
  bells + muted horn); turntable scratches into the hooks.
* Arrangement (80 bars ≈ 3.4 min): Intro 16 (drums only) · Verse 16 · Hook 8 · Verse 2 · Break 8 ·
  Hook 2 · Outro 16 (8 bars beat+loop, 8 bars drums only). −11 LUFS.

Trap brief
----------
* 140 BPM with a half-time feel: short punchy kick, clap+snare on beat 3, hi-hats on 8ths with
  1/16, 1/16-triplet, 1/32 and 1/32-triplet rolls (96-step grid), open hats, rim/snap percs.
* Long tuned 808 with glides (octave / fifth slides) following the kick, dark FM bells hook,
  "ooh" formant choir pad, risers, reverse cymbals, impacts, triplet snare roll in the build.
* Arrangement (112 bars ≈ 3.2 min): Intro 16 (drums only) · Verse 16 · Build 8 · Drop 16 ·
  Verse 2 16 · Breakdown 8 · Drop 2 16 · Outro 16. −10.5 LUFS.
"""
from __future__ import annotations

import numpy as np

from .. import drums, ext_mainstream as xm, fx, instruments as inst
from ..arrangement import Song, clip
from ..theory import chord as mkchord, voice_lead
from . import register

# ============================================================================ boom bap material
BB_KICKS = [  # 2-bar kick patterns (16ths, swung)
    ["x.........x.....", "x......x..x....."],
    ["x......x..x.....", "x.x.......x....x"],
    ["x.........x..x..", "x.......x.x....."],
    ["x..x......x.....", "x......x..x..x.."],
]
BB_SNARE = ["....x.......x...", "....x.......x..g", "....x..g....x..."]
BB_HATS = ["x.x.x.x.x.x.x.x.", "x.xgx.x.x.xgx.x.", "X.o.x.o.X.o.x.og", "x.x.xgx.x.x.xgxg"]
BB_RIM = ["..g....g..g....g", ".......g......g.", "..g.......g..g.."]
JAZZY = [  # (semitones from key root, chord quality) per bar
    [(0, "min9"), (8, "maj7"), (5, "min9"), (7, "7")],
    [(0, "min9"), (5, "min9"), (10, "7"), (3, "maj7")],
    [(0, "min9"), (3, "maj7"), (8, "maj7"), (7, "7")],
]
DARK = [
    [(0, "min9"), (1, "maj7"), (0, "min7"), (8, "maj7")],
    [(0, "min9"), (8, "maj7"), (1, "maj7"), (7, "7")],
    [(0, "min7"), (0, "min9"), (8, "maj7"), (1, "maj7")],
]
CHORD_RHYTHMS = [
    [(0, 7, 0.85), (7, 3, 0.7), (10, 6, 0.8)],
    [(0, 3, 0.85), (3, 4, 0.7), (8, 3, 0.8), (11, 5, 0.72)],
    [(0, 10, 0.82), (10, 2, 0.6), (12, 4, 0.75)],
]
MOTIF_RHYTHMS = [  # 2 bars
    [(0, 3, .9), (3, 1, .7), (4, 2, .8), (6, 6, .9), (16, 2, .85), (18, 2, .75), (20, 2, .8), (22, 8, .9)],
    [(2, 2, .85), (4, 2, .8), (7, 5, .9), (14, 2, .7), (18, 2, .85), (20, 2, .8), (23, 7, .9)],
    [(0, 4, .9), (6, 2, .75), (8, 4, .85), (12, 2, .7), (16, 6, .9), (24, 2, .75), (26, 4, .85)],
]
TPL_BB = [("Intro", "intro", 16, 3, 0), ("Verse", "verse", 16, 5, 2), ("Hook", "drop", 8, 7, 1),
          ("Verse 2", "verse", 8, 5, 1), ("Break", "breakdown", 8, 4, 0), ("Hook 2", "drop", 8, 7, 1),
          ("Outro", "outro", 16, 4, 0)]
TPL_BB_DARK = [("Intro", "intro", 16, 3, 0), ("Verse", "verse", 16, 5, 2), ("Hook", "drop", 8, 6, 1),
               ("Break", "breakdown", 8, 4, 0), ("Verse 2", "verse", 8, 5, 1), ("Hook 2", "drop", 8, 7, 1),
               ("Outro", "outro", 16, 4, 0)]

# ============================================================================ trap material
TRAP_KICK_808 = [
    # (2-bar kick, 2-bar 808 events (step, len, semis, vel, flags))
    (["x.....x...x.....", "x.........x..x.."],
     [(0, 6, 0, 1.0, ""), (6, 4, 0, 0.9, "s"), (10, 6, 12, 0.9, ""), (16, 10, 0, 1.0, ""), (26, 3, 0, 0.85, "s"),
      (29, 3, 7, 0.85, "")]),
    (["x.......x.x.....", "x..x......x....."],
     [(0, 8, 0, 1.0, ""), (10, 4, 0, 0.9, "s"), (14, 2, 12, 0.85, ""), (16, 3, 0, 1.0, ""), (19, 7, 0, 0.9, ""),
      (26, 3, 0, 0.85, "s"), (29, 3, -2, 0.85, "")]),
    (["x.....x.....x...", "x.........x....."],
     [(0, 6, 0, 1.0, "s"), (6, 6, 12, 0.9, ""), (12, 4, 0, 0.9, ""), (16, 10, 0, 1.0, "s"), (26, 6, 5, 0.9, "")]),
]
TRAP_BELL_RHYTHMS = [
    [(0, 2, .9), (3, 2, .8), (6, 2, .85), (8, 4, .9), (14, 2, .75), (16, 2, .9), (19, 2, .8), (22, 2, .85),
     (24, 8, .9)],
    [(0, 3, .9), (3, 3, .8), (6, 2, .85), (10, 2, .8), (12, 4, .9), (16, 3, .9), (19, 3, .8), (22, 2, .85),
     (26, 6, .9)],
]
TPL_TRAP = [("Intro", "intro", 16, 3, 0), ("Verse", "verse", 16, 5, 1), ("Build", "build", 8, 6, 0),
            ("Drop", "drop", 16, 8, 2), ("Verse 2", "verse", 16, 6, 1), ("Breakdown", "breakdown", 8, 4, 0),
            ("Drop 2", "drop", 16, 8, 2), ("Outro", "outro", 16, 4, 0)]


def _bass_range(m, lo=28, hi=40):
    while m > hi:
        m -= 12
    while m < lo:
        m += 12
    return m


@register("hip_hop")
def build(plan: dict, rng: np.random.Generator) -> Song:
    if "trap" in str(plan.get("genre", "")).lower():
        return _trap(plan, rng)
    return _boom_bap(plan, rng)


# ============================================================================ boom bap
def _boom_bap(plan, rng):
    words = (str(plan.get("title", "")) + " " + str(plan.get("mood", ""))).lower()
    dark = any(w in words for w in ("night", "dark", "cypher", "midnight", "shadow"))
    song = Song(plan, rng, swing=float(rng.choice([58.0, 60.0, 61.0, 62.0])))
    key = song.key
    total = song.target_bars()
    song.arrange(TPL_BB_DARK if dark else TPL_BB, total)
    verse, hook, brk, outro = song.find("Verse"), song.find("Hook"), song.find("Break"), song.find("outro")
    song.mix_in_bar = verse.start_bar
    beat_only_from = outro.start_bar + outro.bars - 8
    bar = song.grid.bar_sec

    # ---------------------------------------------------------------- harmony (jazzy loop)
    prog = (DARK if dark else JAZZY)[int(rng.integers(3))]
    chords, prev = [], None
    for semi, q in prog:
        ch = mkchord(key.root(3) + semi, q)
        ch = voice_lead(prev, ch, center=key.root(4) + 3)
        chords.append(ch)
        prev = ch
    roots = [_bass_range(key.root(1) + semi) for semi, _ in prog]

    # ---------------------------------------------------------------- drums
    kick = xm.boom_kick(float(np.clip(440 * 2 ** ((_bass_range(key.root(1), 31, 42) - 69) / 12), 48, 62)), rng=rng)
    kp = BB_KICKS[int(rng.integers(len(BB_KICKS)))]

    def kick_pat(c):
        if c.kind == "breakdown":
            return "x..............." if c.i == 0 else (kp[c.i % 2] if c.bars_left <= 1 else None)
        if c.kind == "intro" and c.i < 2:
            return "x..............." if c.i == 0 else kp[1]
        if c.before("drop", 1):
            return kp[c.i % 2][:8] + "........"  # beat drops out for the last half bar before the hook
        return kp[c.i % 2]

    song.hits("kick", kick, kick_pat, gain_db=-1.0, sc_source=True, humanize=0.05)
    snare = drums.variants(xm.boom_snare, 3, rng, jitter={"tone_hz": 0.03}, tone_hz=float(rng.uniform(180, 215)),
                           snappy=float(rng.uniform(0.55, 0.7)), room=float(rng.uniform(0.12, 0.22)))
    sp = BB_SNARE[int(rng.integers(len(BB_SNARE)))]

    def snare_pat(c):
        if c.kind == "breakdown":
            return "....x.......x..." if c.bars_left <= 2 else None
        if c.kind == "intro" and c.i < 2:
            return "............x..." if c.i == 1 else None
        if c.before("drop", 1):
            return "....x..........."
        if c.phrase_end and c.kind != "outro":
            return "....x.......x.gx"
        return sp

    song.hits("snare", snare, snare_pat, gain_db=-2.5, sends={"room": 0.2, "reverb": 0.06}, humanize=0.05, timing_ms=3.0)
    rim = xm.dusty(drums.rimshot(float(rng.uniform(1500, 1900)), rng=rng), bits=11, lp_hz=8000.0)
    rp = BB_RIM[int(rng.integers(len(BB_RIM)))]
    song.hits("rim", rim, lambda c: rp if c.kind in ("verse", "drop") or (c.kind == "intro" and c.i >= 8) else None,
              gain_db=-15.0, pan=0.4, humanize=0.15, timing_ms=3.0)
    hat_c = [xm.dusty(h, bits=11, lp_hz=10500.0) for h in
             drums.variants(drums.hat, 4, rng, jitter={"decay": 0.2}, decay=float(rng.uniform(0.035, 0.05)),
                            tone=float(rng.uniform(0.85, 1.0)))]
    hp_ = BB_HATS[int(rng.integers(len(BB_HATS)))]

    def hat_pat(c):
        if c.kind == "breakdown":
            return "x.x.x.x.x.x.x.x." if c.i >= 2 else None
        if c.kind == "intro" and c.i < 2:
            return "x.x.x.x.x.x.x.x." if c.i == 1 else None
        return hp_

    hats = song.hits("hats", hat_c, hat_pat, gain_db=-11.0, pan=0.32, humanize=0.18, timing_ms=4.0)
    hats.automate("lp", [(0, 2500), (4, 2500), (8, 16000)])
    ohat = xm.dusty(drums.hat(open_=True, decay=0.22, tone=0.9, rng=rng), bits=11, lp_hz=9500.0)
    song.hits("open_hat", ohat, lambda c: "..............x." if c.kind == "drop" and c.i % 2 == 1
              or (c.kind == "verse" and c.i % 4 == 3) else None, gain_db=-15.0, pan=-0.25)
    tamb = drums.tambourine(0.2, rng=rng)
    song.hits("tambourine", tamb, lambda c: "....x.......x..." if c.kind == "drop" else None, gain_db=-14.0, pan=-0.4,
              sends={"room": 0.15})
    shk = drums.variants(drums.shaker, 3, rng, length=0.08)
    song.hits("shaker", shk, lambda c: "..x...x...x...x." if c.kind == "drop" or (c.kind == "intro" and c.i >= 8)
              else None, gain_db=-18.0, pan=0.5, humanize=0.2, timing_ms=4.0)
    song.custom("vinyl", xm.vinyl_crackle(song.seed, level=1.0), bus="fx", gain_db=-9.0) \
        .automate("gain_db", song.section_points({"intro": 2.0, "breakdown": 3.0, "outro": 1.0}, -1.0))
    song.buses["fx"].hp = 300.0

    # ---------------------------------------------------------------- bass
    cr = CHORD_RHYTHMS[int(rng.integers(len(CHORD_RHYTHMS)))]

    def bass_notes(c):
        if c.kind in ("intro",) or c.bar >= beat_only_from:
            return []
        r = roots[c.i % 4]
        if c.kind == "breakdown":
            return [(0, 12, r, 0.75)] if c.i % 2 == 0 and c.bars_left > 2 else []
        steps = [i for i, ch in enumerate(kp[c.i % 2]) if ch != "."]
        ev = []
        for j, st in enumerate(steps):
            nxt = steps[j + 1] if j + 1 < len(steps) else 16
            ev.append((st, max(1.5, nxt - st - 0.5), r, 0.95 if st == 0 else 0.8))
        if c.kind == "drop" and c.i % 2 == 1:
            ev.append((14, 2, r + 12 if c.rng.random() < 0.5 else r + 7, 0.7))
        if c.before("drop", 1):
            ev = [e for e in ev if e[0] < 8]
        return ev

    bass = song.notes("bass", xm.deep_bass(cutoff=float(rng.uniform(380, 520)), harm=0.3, drive=1.5,
                                           decay=0.4, sustain=0.65),
                      bass_notes, bus="bass", gain_db=-3.0, sidechain=0.25, sc_release_ms=110.0, humanize=0.05)
    bass.automate("gain_db", [(0, 0.0), (beat_only_from - 4, 0.0), (beat_only_from, -6.0)])

    # ---------------------------------------------------------------- the "sampled" Rhodes loop
    rh = xm.rhodes(bright=float(rng.uniform(0.7, 0.9)), bark=float(rng.uniform(0.7, 0.95)),
                   trem=float(rng.uniform(0.28, 0.4)), wow_cents=float(rng.uniform(6, 11)))

    def keys_notes(c):
        if c.kind == "intro" or c.bar >= beat_only_from:
            return []
        ch = chords[c.i % 4]
        return [(s, l, ch, v) for s, l, v in cr]

    keys = song.notes("keys", rh, keys_notes, gain_db=-5.0, sends={"room": 0.18, "reverb": 0.1}, width=1.7,
                      sidechain=0.15, humanize=0.06,
                      fx=[lambda x: fx.tape(x * 0.3, 1.4, 0.55), lambda x: fx.bitcrush(x, 12, 1)])
    keys.automate("lp", [(verse.start_bar, 1800), (verse.start_bar + 4, 7000), (outro.start_bar, 7000),
                         (beat_only_from, 1200)])

    # ---------------------------------------------------------------- hook motif
    mr = MOTIF_RHYTHMS[int(rng.integers(len(MOTIF_RHYTHMS)))]
    tones = [[n for n in ch] for ch in chords]
    lo, hi = key.root(5) - 3, key.root(6) + 2
    motif = xm.make_melody(rng, key, tones, mr, lo, hi)
    mclip = clip(motif, 4)

    def motif_notes(c):
        if c.kind == "drop":
            return mclip(c)
        if c.kind == "breakdown" and c.bars_left > 2:
            return mclip(c) if c.i % 4 < 2 else []
        if c.kind == "verse" and c.name == "Verse 2" and c.i >= c.section.bars - 4:
            return mclip(c) if c.i % 2 == 0 else []
        return []

    if dark:
        song.notes("bells", inst.bell(ratio=3.5, index=2.2, decay=1.4), motif_notes, gain_db=-11.0,
                   sends={"reverb": 0.25, "delay": 0.18}, pan=0.2, width=1.3)
        horn = xm.GlideSynth(osc="square", voices=2, detune_cents=8, spread=0.4, cutoff=900.0, res=0.1, env_amt=1.2,
                             env_decay=0.25, attack=0.04, decay=0.6, sustain=0.6, release=0.2, vib_cents=12,
                             vib_delay=0.3, glide_ms=50, gain=0.6, seed=song.seed)
        song.line("horn", horn, lambda c: [(s, l, m - 12, v * 0.9) for s, l, m, v in mclip(c)]
                  if c.kind == "drop" else [], bus="music", gain_db=-10.0, sends={"hall": 0.2, "room": 0.1},
                  pan=-0.2)
        pad = song.notes("pad", xm.soft_pad(attack=1.0, cutoff=900.0, detune=0.18),
                         lambda c: [(0, 31.5, chords[c.i % 4], 0.6)] if c.kind in ("verse", "drop", "breakdown")
                         and c.i % 2 == 0 else [], gain_db=-16.0, sends={"hall": 0.3}, width=1.6)
        pad.automate("gain_db", song.section_points({"breakdown": 4.0}, 0.0, ramp_bars=1))
    else:
        flute = xm.GlideSynth(osc="flute", cutoff=4200.0, attack=0.05, decay=0.4, sustain=0.8, release=0.15,
                              glide_ms=45, vib_cents=18, vib_hz=5.2, vib_delay=0.18, scoop=-0.7, scoop_ms=45,
                              breath=0.35, chiff=0.25, gain=0.7, seed=song.seed)
        song.line("flute", flute, lambda c: [(s, l, m, v) for s, l, m, v in motif_notes(c)], bus="music",
                  gain_db=-8.0, sends={"reverb": 0.22, "delay": 0.15}, pan=0.15,
                  fx=[lambda x: fx.tape(x, 1.2, 0.4)])
        song.notes("vibes", inst.mallet("vibes"),
                   lambda c: [(s, l, m - 12, v * 0.7) for s, l, m, v in mclip(c)][::2] if c.kind == "drop" else [],
                   gain_db=-14.0, sends={"reverb": 0.2}, pan=-0.3)

    # ---------------------------------------------------------------- scratches + fx
    src = xm.chant(vowel="a", vowel_to="o", voices=1, fall=0.0, breath=0.3)(330.0, 0.4, 1.0)
    scr1 = xm.scratch(src, song.bpm, beats=1.0, moves=(1, -1, 1, -1))
    scr2 = xm.scratch(src, song.bpm, beats=0.5, moves=(1, -1))
    vx = song.audio("scratch", bus="vox", sends={"room": 0.1})
    for s in song.sections:
        if s.kind == "drop":
            vx.add(scr1, s.start_bar - 1, beat=2.0, gain_db=-6.0)
            vx.add(scr2, s.start_bar - 1, beat=3.0, gain_db=-7.0)
            vx.add(scr1, s.start_bar + 3, beat=2.0, gain_db=-8.0)
            if s.bars >= 8:
                vx.add(scr2, s.start_bar + 7, beat=3.0, gain_db=-8.0)
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.1})
    for s in song.sections:
        if s.kind == "drop":
            fxl.add(fx.reverse_cymbal(bar * 0.5, rng=rng), s.start_bar, align="end", gain_db=-14.0)
        if s.kind == "breakdown":
            fxl.add(fx.downlifter(bar * 1.5, rng=rng), s.start_bar, gain_db=-16.0)

    # ---------------------------------------------------------------- mix
    song.buses["drums"].comp = dict(threshold_db=-12.0, ratio=3.0, attack_ms=10.0, release_ms=80.0, makeup_db=1.0)
    song.buses["drums"].sat = 0.25
    song.buses["drums"].eq = [("peak", 2800.0, 1.5, 0.8), ("peak", 220.0, -1.5, 1.0)]
    song.buses["music"].eq = [("peak", 420.0, -3.0, 0.8), ("peak", 1500.0, 2.5, 0.7)]
    song.buses["bass"].eq = [("lowshelf", 60.0, 1.5, 0.7)]
    song.returns["room"].width = 1.4
    song.master.lufs = -11.0
    song.master.high_shelf_db = -1.0
    song.instruments = (["dusty swung boom-bap drums (12-bit)", "vinyl crackle", "FM Rhodes chord loop (tape wow)",
                         "deep round bass", "turntable scratches"]
                        + (["dark FM bells", "muted square horn", "dark pad"] if dark
                           else ["breathy jazz flute", "vibraphone"]))
    sw = int(song.swing)
    if dark:
        song.description_he = (f"היפ-הופ בום-באפ אפל ולילי ב-{int(song.bpm)} BPM בסולם {plan['key']}: תופים "
                               f"מאובקים בסווינג MPC של {sw}%, לופ רודס ג'אזי עם אקורדים פריגיים כהים, באס עמוק, "
                               f"פעמונים וקרן עמומה בהוק, קראקל של ויניל וסקרצ'ים לפני כל פזמון. אווירת סייפר "
                               f"של שתיים בלילה.")
    else:
        song.description_he = (f"היפ-הופ בום-באפ קלאסי ב-{int(song.bpm)} BPM בסולם {plan['key']}: קיק מאובק ונוקש, "
                               f"סנר פריך, היי-האטים בסווינג MPC של {sw}%, לופ רודס ג'אזי (אקורדי 9 ו-maj7) עם "
                               f"\"ווא\" של טייפ, באס עמוק, מוטיב חליל ווייבים בהוק, קראקל של ויניל וסקרצ'ים.")
    song.mix_tips_he = (f"טיפ ערבוב: אינטרו של 16 תיבות ביט בלבד (בלי באס ובלי אקורדים) — הכי נוח למיקס בסווינג. "
                        f"הלופ והבאס נכנסים בתיבה {verse.start_bar + 1} (Hot Cue B), ההוק בתיבה "
                        f"{hook.start_bar + 1}, הברייק בתיבה {brk.start_bar + 1}. לפני כל הוק הביט נעצר לחצי "
                        f"תיבה — רגע מושלם לסקרץ' או לקאט. האאוטרו מתחיל בתיבה {outro.start_bar + 1} ו-8 "
                        f"התיבות האחרונות הן תופים בלבד. {xm.wheel_he(plan['camelot'])} "
                        + (xm.partners_he(plan) + "." if xm.partners_he(plan) else ""))
    return song


# ============================================================================ trap
def _trap(plan, rng):
    song = Song(plan, rng, swing=50.0)
    key = song.key
    total = song.target_bars()
    song.arrange(TPL_TRAP, total)
    verse, build_s, drop, outro = song.find("Verse"), song.find("Build"), song.find("drop"), song.find("outro")
    bd = song.find("breakdown")
    song.mix_in_bar = verse.start_bar
    beat_only_from = outro.start_bar + outro.bars - 8
    bar = song.grid.bar_sec

    from ..theory import Key
    hm = Key(plan["key"], "harmonic_minor")
    degs = [[0, 5, 3, 4], [0, 5, 6, 5], [0, 3, 5, 4], [0, 0, 5, 6]][int(rng.integers(4))]
    chords, prev = [], None
    for d in degs:
        kk = hm if d == 4 else key
        ch = voice_lead(prev, kk.chord(d, 3, 3), center=key.root(4) - 2)
        chords.append(ch)
        prev = ch
    roots = [_bass_range((hm if d == 4 else key).degree(d, 1), 26, 37) for d in degs]

    def chord_at(c):  # one chord per 2 bars → 8-bar cycle
        return chords[(c.i // 2) % 4]

    def root_at(c):
        return roots[(c.i // 2) % 4]

    # ---------------------------------------------------------------- drums
    kick = xm.trap_kick(float(np.clip(440 * 2 ** ((_bass_range(key.root(1), 31, 42) - 69) / 12), 46, 60)), rng=rng)
    kpat, b808pat = TRAP_KICK_808[int(rng.integers(len(TRAP_KICK_808)))]

    def kick_pat(c):
        if c.kind in ("breakdown", "build"):
            return None
        if c.kind == "intro" and c.i < 4:
            return "x..............." if c.i % 2 == 0 else "x.........x....."
        return kpat[c.i % 2]

    song.hits("kick", kick, kick_pat, gain_db=-2.0, sc_source=True, humanize=0.0)
    clap = drums.clap(tightness=0.85, tone_hz=float(rng.uniform(1100, 1400)), tail=0.18, rng=rng)
    snr = drums.snare(tone_hz=float(rng.uniform(190, 230)), snappy=0.8, decay=0.16, kind="trap", rng=rng)
    n = max(clap.shape[0], snr.shape[0])
    cs = np.zeros(n, dtype=np.float32)
    cs[:clap.shape[0]] += clap * 0.8
    cs[:snr.shape[0]] += snr * 0.7
    cs = xm.normalize(cs)

    def clap_pat(c):
        if c.kind == "breakdown":
            return None
        if c.kind == "build":
            return ["........x.......", "....x.......x...", "x...x...x...x...", "x.x.x.x.x.x.x.x.",
                    "x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx", "xxxxxxxxxxxxxxxx", "rrrrrrrrrrrrrrrr"][min(7, c.i)]
        if c.phrase_end and c.kind in ("drop", "verse"):
            return "........x.....x."
        return "........x......."

    cl = song.hits("clap", cs, clap_pat, gain_db=-3.0, sends={"reverb": 0.18})
    cl.automate("gain_db", [(0, 0.0), (build_s.start_bar - 0.01, 0.0), (build_s.start_bar, -16.0),
                            (build_s.end_bar - 0.01, 0.0), (build_s.end_bar, 0.0)])
    hats = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.1}, decay=float(rng.uniform(0.028, 0.04)),
                          tone=float(rng.uniform(1.05, 1.25)))

    def hat_pat(c):
        if c.kind == "breakdown" and c.bars_left > 4:
            return None
        if c.kind == "intro" and c.i < 2:
            return xm.trap_hats(c.rng, base=2, rolls=0)
        if c.kind == "drop":
            return xm.trap_hats(c.rng, base=4 if c.i % 4 == 3 else 2, rolls=1 + int(c.i % 2 == 1), energy=1.0)
        if c.kind == "build":
            return xm.trap_hats(c.rng, base=4, rolls=int(c.i >= 4) * 2, energy=1.0)
        rolls = 1 if c.i % 2 == 1 else 0
        return xm.trap_hats(c.rng, base=2, rolls=rolls, energy=0.8)

    song.hits("hats", hats, hat_pat, gain_db=-12.0, pan=0.2, humanize=0.08)
    ohat = drums.hat(open_=True, decay=0.25, tone=1.1, rng=rng)
    song.hits("open_hat", ohat, lambda c: "..............x." if c.kind in ("drop",) and c.i % 2 == 0
              or (c.kind == "verse" and c.i % 4 == 3) else None, gain_db=-14.0, pan=-0.3, sends={"room": 0.1})
    rim = drums.rimshot(float(rng.uniform(1700, 2100)), rng=rng)
    snap = drums.snap(rng=rng)
    song.hits("perc", [rim, snap], lambda c: ("...x......x...x." if c.i % 2 else ".......x.....x..")
              if c.kind in ("drop", "verse") or (c.kind == "intro" and c.i >= 8) else None,
              gain_db=-15.0, pan=0.45, sends={"delay8": 0.15, "room": 0.1})

    # ---------------------------------------------------------------- 808
    b808_clip = clip(b808pat, 2)

    def b808_notes(c):
        if c.kind in ("intro", "build") or c.bar >= beat_only_from:
            return []
        if c.kind == "breakdown":
            return [(0, 30, root_at(c), 0.7, "")] if c.i % 4 == 0 and c.bars_left > 4 else []
        r = root_at(c)
        ev = [(s, l, r + o, v, f) for s, l, o, v, f in b808_clip(c)]
        if c.kind == "verse" and c.i % 2 == 0:
            ev = [e for e in ev if e[0] < 10] + [e for e in ev if e[0] >= 10 and "s" not in e[4]][:1]
        return ev

    b808 = xm.synth_808(decay=float(rng.uniform(1.4, 1.9)), drive=float(rng.uniform(2.0, 2.8)), punch=7.0,
                        glide_ms=float(rng.uniform(70, 110)), seed=song.seed)
    song.line("808", b808, b808_notes, bus="bass", gain_db=-1.5, sidechain=0.4, sc_release_ms=70.0)

    # ---------------------------------------------------------------- music
    br = TRAP_BELL_RHYTHMS[int(rng.integers(len(TRAP_BELL_RHYTHMS)))]
    bell_ch = [chords[0], chords[0], chords[1], chords[1], chords[2], chords[2], chords[3], chords[3]]
    mel = xm.make_melody(rng, key, bell_ch, br, key.root(4) + 2, key.root(5) + 7, phrase_bars=2)
    mclip = clip(mel, 8)

    def bell_notes(c):
        if c.kind in ("verse", "drop") or (c.kind == "breakdown") or (c.kind == "build" and c.i < 4):
            return mclip(c)
        if c.kind == "outro" and c.bar < beat_only_from:
            return mclip(c) if c.i % 2 == 0 else []
        return []

    bells = song.notes("bells", inst.bell(ratio=float(rng.choice([3.5, 2.0, 4.0])), index=1.8, decay=1.1),
                       bell_notes, gain_db=-12.5, sends={"reverb": 0.22, "delay": 0.2}, pan=0.15, width=1.4,
                       sidechain=0.25)
    bells.automate("lp", [(verse.start_bar, 2000), (verse.start_bar + 8, 6500), (outro.start_bar, 6500),
                          (beat_only_from, 1500)])
    song.notes("pluck", xm.square_pluck(pw=0.3, cutoff=700.0, env_amt=2500.0, decay=0.12),
               lambda c: [(s, l, m, v * 0.8) for s, l, m, v in mclip(c)] if c.kind == "drop" else [],
               gain_db=-15.0, sends={"delay": 0.15}, pan=-0.25)
    choir = xm.chant(vowel="u", vowel_to="o", voices=4, shift=0.95, fall=0.0, breath=0.1, spread=0.8, release=0.8)

    def choir_notes(c):
        if c.kind in ("verse", "drop", "breakdown", "build") and c.i % 2 == 0:
            return [(0, 31.0, chord_at(c), 0.6)]
        return []

    ch_l = song.notes("choir", choir, choir_notes, bus="vox", gain_db=-17.0, sends={"hall": 0.35}, width=1.6,
                      sidechain=0.3)
    ch_l.automate("lp", [(0, 2500)])
    ch_l.automate("gain_db", song.section_points({"breakdown": 5.0, "build": 3.0, "drop": 0.0}, -2.0, ramp_bars=1))
    pad = song.notes("pad", xm.soft_pad(attack=0.8, cutoff=1100.0, detune=0.2),
                     lambda c: [(0, 31.5, chord_at(c), 0.6)] if c.kind in ("breakdown", "build", "drop")
                     and c.i % 2 == 0 else [], gain_db=-17.0, sends={"hall": 0.25}, width=1.6, sidechain=0.3)
    pad.automate("gain_db", song.section_points({"breakdown": 4.0, "build": 2.0}, 0.0, ramp_bars=1))

    # ---------------------------------------------------------------- fx
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.12})
    crash = drums.crash(decay=2.0, rng=rng)
    for s in song.sections:
        if s.kind == "drop":
            fxl.add(crash, s.start_bar, gain_db=-10.0)
            fxl.add(fx.impact(3.0, rng=rng), s.start_bar, gain_db=-9.0)
            fxl.add(fx.reverse_cymbal(bar, rng=rng), s.start_bar, align="end", gain_db=-12.0)
        if s.kind in ("build", "breakdown"):
            fxl.add(fx.riser(bar * min(8, s.bars), "both", rng=rng), s.end_bar, align="end", gain_db=-11.0)
        if s.kind == "verse":
            fxl.add(crash, s.start_bar, gain_db=-14.0)
    fxl.add(fx.downlifter(bar * 2, rng=rng), bd.start_bar, gain_db=-12.0)

    song.buses["drums"].eq = [("peak", 4500.0, 1.5, 0.8), ("peak", 200.0, -2.0, 1.0)]
    song.buses["bass"].eq = [("lowshelf", 55.0, 1.5, 0.7), ("peak", 160.0, -2.0, 0.9)]
    song.master.lufs = -10.5
    song.instruments = ["long gliding 808 (tuned)", "punchy trap kick", "clap + snare on 3", "hi-hat rolls (1/16, "
                        "1/32, triplets)", "open hats & rim/snap percs", "dark FM bells", "square pluck",
                        "formant 'ooh' choir", "dark pad", "risers / impacts / reverse cymbals"]
    song.description_he = (f"טראפ כהה ב-{int(song.bpm)} BPM בתחושת חצי-טמפו בסולם {plan['key']}: 808 ארוך ומכוון "
                           f"עם גלישות אוקטבה, קלאפ וסנר על הפעמה השלישית, היי-האטים עם רולים של שש-עשריות, "
                           f"שלושים-ושתיים וטריולות, פעמונים אפלים, מקהלת \"אוּ\" סינתטית ובילד עם רול סנר לפני הדרופ.")
    song.mix_tips_he = (f"טיפ ערבוב: אינטרו של 16 תיבות תופים בלבד. ה-808 והפעמונים נכנסים בתיבה "
                        f"{verse.start_bar + 1} (Hot Cue B), בילד בתיבה {build_s.start_bar + 1}, הדרופ בתיבה "
                        f"{drop.start_bar + 1}, ברייקדאון בתיבה {bd.start_bar + 1}. האאוטרו מתחיל בתיבה "
                        f"{outro.start_bar + 1} ו-8 התיבות האחרונות הן תופים בלבד. Rekordbox עשוי לזהות 70 BPM "
                        f"(חצי-טמפו) — זה תקין; ב-140 הוא מתערבב גם עם דאבסטפ, ובחצי (70) עם היפ-הופ איטי. "
                        f"{xm.wheel_he(plan['camelot'])} " + (xm.partners_he(plan) + "." if xm.partners_he(plan) else ""))
    return song
