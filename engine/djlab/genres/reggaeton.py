"""Reggaeton recipe (88–98 BPM, dembow).

Genre brief
-----------
* Feel: the **dembow** — kick on 1 and 3 in verses (four-on-the-floor in the hooks), snare + rim on
  the "a-of-1 / and-of-2" cell (16th steps 3, 6, 11, 14), 8th hats with off-beat accents, 16th
  shaker, timbale fills at every 8-bar phrase end, congas and güiro for the Latin colour.
* Low end: tuned 808 sub that follows the kick (roots on 1 and 3 + dembow pickups); in the
  "Perreo" drop a second, driven 808 with octave/fifth glides takes over.
* Harmony: minor loops — i–VI–III–VII (bright, "fuego") or i–VI–iv–V with the harmonic-minor V
  (dark, "nocturno"). Nylon-guitar Karplus-Strong arpeggios in tresillo rhythm, warm pad, a square
  pluck hook generated per seed (chord-aware call/response), formant "oh/eh" chops in the dark
  variant, siren / riser / reverse cymbal into the drops.
* Arrangement (80 bars @ 92–95 BPM ≈ 3.4 min): Intro 16 (drums only) · Verso · Coro (drop) ·
  Puente (breakdown + build) · Perreo (drop 2) · Outro 16 (8 bars drums+bass, 8 bars drums only).
* Loudness −10 LUFS (punchy, not squashed), true peak ≤ −1 dBTP.
"""
from __future__ import annotations

import numpy as np

from .. import drums, ext_mainstream as xm, fx
from ..arrangement import Song, clip
from . import register

DEMBOW = "...x..x....x..x."
DEMBOW_VARS = ["...x..x....x..x.", "...x..x...xx..x.", "...x..x....x.x.x", "..xx..x....x..x."]
DEMBOW_FILL = ["...x..x.x.xxx.xx", "...x..x.xxxx.xxx", "...x..xx..xxxxxx"]
KICK_VERSE = ["X...o...X...o...", "X...o...X...o...", "X...o...X...o...", "X...o...X...o.x."]
KICK_DROP = "X...x...X...x..."
HATS = ["o.x.o.x.o.x.o.x.", "g.x.g.x.g.x.o.x.", "o.x.o.xgo.x.o.xg"]
SHAKER = ["xgogxgogxgogxgog", "xgoxxgoxxgoxxgox", "ogxgogxgogxgogxg"]
CONGA = ["......x...x..x..", "..x...x...x..xx.", "......xx..x...x.", "...x..x.......x."]
GUIRO = "x...x.x.x...x.x."
TIMB_FILLS = [("........x.x..x.x", "..........x.x..."), ("..........x.xxxx", "........x.x....."),
              ("......x.x.x.x.xx", "........x...x..."), ("........xxx.x.x.", "...........x.x..")]

# nylon arpeggios: (step, len, chord index (0=root,1=third,2=fifth,3=octave,4=tenth)) per bar
ARPS = [
    [(0, 2, 0), (3, 2, 2), (6, 2, 3), (8, 2, 1), (11, 2, 2), (14, 2, 3)],
    [(0, 2, 0), (2, 1.5, 2), (4, 1.5, 1), (6, 2, 2), (8, 2, 3), (10, 1.5, 2), (12, 1.5, 4), (14, 2, 2)],
    [(0, 3, 0), (3, 3, 3), (6, 2, 1), (8, 3, 2), (11, 3, 4), (14, 2, 3)],
]
# hook rhythms over 2 bars (step, len, vel) — dembow-friendly syncopation
HOOK_RHYTHMS = [
    [(0, 2, .95), (3, 1, .8), (6, 2, .9), (8, 2, .85), (11, 1, .75), (14, 2, .9),
     (16, 2, .95), (19, 1, .8), (22, 2, .9), (24, 4, .9)],
    [(0, 1, .9), (2, 1, .7), (3, 2, .95), (6, 2, .85), (10, 1, .75), (11, 2, .9), (14, 2, .8),
     (16, 1, .9), (18, 1, .7), (19, 2, .95), (22, 2, .85), (24, 6, .9)],
    [(3, 1, .85), (6, 2, .95), (8, 1, .7), (11, 1, .85), (14, 2, .95), (16, 2, .9), (19, 1, .8),
     (22, 2, .9), (24, 2, .85), (27, 3, .9)],
]
# 808 patterns (step, len, semis from chord root, vel, flags) per bar
BASS_VERSE = [(0, 7, 0, 1.0, ""), (8, 5, 0, 0.92, ""), (14, 2, 0, 0.8, "")]
BASS_CORO = [(0, 3, 0, 1.0, ""), (3, 3, 0, 0.85, ""), (8, 3, 0, 1.0, ""), (11, 3, 0, 0.85, ""), (14, 2, 12, 0.75, "")]
BASS_PERREO = [
    [(0, 3, 0, 1.0, "s"), (3, 3, 12, 0.9, ""), (8, 3, 0, 1.0, ""), (11, 2, 0, 0.85, "s"), (14, 2, 7, 0.85, "")],
    [(0, 3, 0, 1.0, ""), (3, 3, 0, 0.9, "s"), (6, 2, 12, 0.8, ""), (8, 3, 0, 1.0, "s"), (11, 3, -2, 0.9, ""),
     (14, 2, 0, 0.8, "")],
]

TPL_FUEGO = [("Intro", "intro", 16, 3, 0), ("Verso", "groove", 8, 5, 1), ("Coro", "drop", 16, 7, 2),
             ("Puente", "breakdown", 8, 4, 0), ("Perreo", "drop", 16, 8, 3), ("Outro", "outro", 16, 4, 0)]
TPL_NOCHE = [("Intro", "intro", 16, 3, 0), ("Verso", "groove", 16, 5, 3), ("Coro", "drop", 16, 6, 1),
             ("Puente", "breakdown", 8, 4, 0), ("Perreo", "drop", 8, 7, 2), ("Outro", "outro", 16, 4, 0)]


def _bass_midi(m):
    while m > 39:
        m -= 12
    while m < 28:
        m += 12
    return m


@register("reggaeton")
def build(plan: dict, rng: np.random.Generator) -> Song:
    dark = int(plan.get("energy", 6)) < 7
    song = Song(plan, rng, swing=float(rng.choice([50.0, 51.0, 52.0])), scale="harmonic_minor" if dark else None)
    key = song.key
    total = song.target_bars()
    song.arrange(TPL_NOCHE if dark else TPL_FUEGO, total)
    verso, coro, puente, perreo, outro = (song.find("Verso"), song.find("Coro"), song.find("Puente"),
                                          song.find("Perreo"), song.find("outro"))
    song.mix_in_bar = verso.start_bar
    drums_only_from = outro.start_bar + outro.bars - 8
    sr = song.sr

    root = key.root(1)
    while root < 31:
        root += 12
    root_hz = 440 * 2 ** ((root - 69) / 12)
    if root_hz > 60:
        root_hz *= 2 ** (-5 / 12) if root_hz * 2 ** (-5 / 12) >= 45 else 0.5  # tune to the fifth below
    kick_hz = float(np.clip(root_hz, 45, 60))

    # ---------------------------------------------------------------- harmony
    if dark:
        degs = [[0, 5, 3, 4], [0, 3, 5, 4], [0, 0, 5, 4]][int(rng.integers(3))]   # i–VI–iv–V (harm. minor)
    else:
        degs = [[0, 5, 2, 6], [0, 0, 5, 6], [0, 6, 5, 6], [0, 5, 6, 6]][int(rng.integers(4))]  # i–VI–III–VII etc.
    from ..theory import Key
    nat = Key(plan["key"])  # natural minor for everything except the V chord in the dark variant
    chords = []
    prev = None
    from ..theory import voice_lead
    for d in degs:
        kk = key if (dark and d == 4) else nat
        ch = voice_lead(prev, kk.chord(d, 3, 3), center=key.root(3) + 3)
        chords.append(ch)
        prev = ch
    roots = [_bass_midi(nat.degree(d, 1) if not (dark and d == 4) else key.degree(d, 1)) for d in degs]

    def chord_at(c):
        return chords[c.i % 4] if c.kind != "intro" else chords[0]

    def root_at(c):
        return roots[c.i % 4]

    # ---------------------------------------------------------------- drums
    kick = drums.kick("house", tune_hz=kick_hz, decay=float(rng.uniform(0.24, 0.3)), click=float(rng.uniform(0.45, 0.65)),
                      drive=1.5, rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown":
            return "x..............." if c.i == 0 else None
        if c.before("drop", 1):
            return "X...x...X......." if c.rng.random() < 0.5 else "X...x...X...x..."
        if c.kind == "drop":
            return KICK_DROP
        if c.kind == "intro" and c.i < 4:
            return "x.......x......."  # bare 1-and-3 dembow kick to open
        return KICK_VERSE[c.i % 4]

    song.hits("kick", kick, kick_pat, gain_db=-1.5, sc_source=True, humanize=0.0)

    snr = drums.snare(tone_hz=float(rng.uniform(210, 250)), snappy=0.85, decay=0.11, kind="tight", rng=rng)
    rim = drums.rimshot(float(rng.uniform(1600, 2000)), rng=rng)
    dembow_s = []
    for k in range(3):
        n = max(snr.shape[0], rim.shape[0])
        x = np.zeros(n, dtype=np.float32)
        x[:snr.shape[0]] += snr * (0.85 + 0.05 * k)
        x[:rim.shape[0]] += rim * (0.55 - 0.05 * k)
        dembow_s.append(xm.normalize(x))
    dv = DEMBOW_VARS[int(rng.integers(len(DEMBOW_VARS)))]
    dfill = DEMBOW_FILL[int(rng.integers(len(DEMBOW_FILL)))]

    def dembow_pat(c):
        if c.kind == "breakdown":
            if c.bars_left == 2:
                return "x...x...x...x..."
            if c.bars_left == 1:
                return "x.x.x.x.xxxxxxxx"
            return None
        if c.kind == "intro" and c.i < 4:
            return None
        if c.before("drop", 1):
            return "...x..x.x.x.xxxx"
        if c.phrase_end:
            return dfill
        return DEMBOW if c.i % 4 != 3 else dv

    song.hits("dembow", dembow_s, dembow_pat, gain_db=-2.5, sends={"room": 0.12, "reverb": 0.05}, humanize=0.08,
              timing_ms=1.0)
    pb0 = song.bar("Perreo")
    song.layer("dembow").automate("gain_db", [(0, 0.0), (pb0 - 2.01, 0.0), (pb0 - 2, -9.0), (pb0 - 0.01, -1.0),
                                              (pb0, 0.0)])

    clap = drums.clap(tightness=0.8, tone_hz=float(rng.uniform(1200, 1500)), tail=0.12, rng=rng)
    song.hits("clap", clap, lambda c: "......x.......x." if c.kind == "drop" else None, gain_db=-6.5,
              sends={"reverb": 0.15}, pan=0.05)

    hat = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.15}, decay=float(rng.uniform(0.03, 0.045)),
                         tone=float(rng.uniform(0.95, 1.15)))
    hp_ = HATS[int(rng.integers(len(HATS)))]
    song.hits("hats", hat, lambda c: hp_ if (c.kind != "breakdown" and not (c.kind == "outro" and c.bars_left <= 2))
              else None, gain_db=-12.0, pan=0.25, humanize=0.1)
    ohat = drums.hat(open_=True, decay=0.18, tone=1.05, rng=rng)
    song.hits("open_hat", ohat, lambda c: "..............x." if c.kind == "drop" and c.i % 2 == 1 else None,
              gain_db=-14.0, pan=-0.2, sends={"room": 0.1})
    shk = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=float(rng.uniform(0.06, 0.09)))
    sp = SHAKER[int(rng.integers(len(SHAKER)))]
    song.hits("shaker", shk, lambda c: sp if not (c.kind == "intro" and c.i < 2) else None, gain_db=-15.0, pan=-0.45,
              humanize=0.15, timing_ms=2.0)

    t_hi = xm.timbale(float(rng.uniform(560, 680)), ring=0.55, rng=rng)
    t_lo = xm.timbale(float(rng.uniform(360, 440)), ring=0.45, rng=rng)
    tf = TIMB_FILLS[int(rng.integers(len(TIMB_FILLS)))]

    def timb(which):
        def f(c):
            if c.kind == "breakdown" and c.bars_left > 1:
                return None
            if c.phrase_end or (c.kind == "intro" and c.i in (3, 11)):
                return tf[which]
            if c.kind == "drop" and c.i % 4 == 1 and which == 0:
                return "..............x."
            return None
        return f

    song.hits("timbal_hi", t_hi, timb(0), gain_db=-10.5, pan=0.35, sends={"room": 0.18})
    song.hits("timbal_lo", t_lo, timb(1), gain_db=-10.5, pan=-0.3, sends={"room": 0.18})
    congas = [drums.conga(float(rng.uniform(200, 240)), "open", rng=rng),
              drums.conga(float(rng.uniform(290, 330)), "slap", rng=rng),
              drums.conga(float(rng.uniform(200, 240)), "mute", rng=rng)]
    cp = CONGA[int(rng.integers(len(CONGA)))]
    song.hits("congas", congas, lambda c: cp if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 8)
              or (c.kind == "outro" and c.bars_left > 4) else None, gain_db=-13.0, pan=-0.55,
              sends={"room": 0.15}, humanize=0.12)
    gu = [xm.guiro(0.22, 16, rng=rng), xm.guiro(0.1, 8, rng=rng)]
    song.hits("guiro", gu, lambda c: GUIRO if (c.kind == "drop" and not dark) or (c.kind == "intro" and c.i >= 8
                                                                                   and not dark) else None,
              gain_db=-19.0, pan=0.6, humanize=0.1)
    if dark:
        cow = drums.perc_blip(float(rng.uniform(800, 1000)), 0.05, fm_index=2.0, ratio=1.48, rng=rng)
        song.hits("perc", cow, lambda c: "......x.......x." if c.kind == "drop" or (c.kind == "intro" and c.i >= 8)
                  else None, gain_db=-17.0, pan=0.55, sends={"delay8": 0.18})

    # ---------------------------------------------------------------- 808s
    def bass_notes(c):
        if c.kind in ("intro", "breakdown") or c.bar >= drums_only_from or c.name == "Perreo":
            return []
        r = root_at(c)
        pat = BASS_CORO if c.kind == "drop" else BASS_VERSE
        ev = [(s, l, r + o, v, f) for s, l, o, v, f in pat]
        if c.before("drop", 1) or c.before("breakdown", 1):
            ev = [e for e in ev if e[0] < 8]
        return ev

    b808 = xm.synth_808(decay=float(rng.uniform(0.9, 1.3)), drive=float(rng.uniform(1.3, 1.6)), punch=5.0,
                        glide_ms=70.0, seed=song.seed)
    song.line("bass", b808, bass_notes, bus="bass", gain_db=-3.0, sidechain=0.3, sc_release_ms=90.0)

    pb = BASS_PERREO[int(rng.integers(len(BASS_PERREO)))]

    def perreo_notes(c):
        if c.name != "Perreo":
            return []
        r = root_at(c)
        ev = [(s, l, r + o, v, f) for s, l, o, v, f in pb]
        if c.last:
            ev = [e for e in ev if e[0] < 12]
        return ev

    p808 = xm.synth_808(decay=1.6, drive=3.6, punch=8.0, glide_ms=85.0, tone=1.8, seed=song.seed + 1)
    song.line("bass_perreo", p808, perreo_notes, bus="bass", gain_db=-4.0, sidechain=0.3, sc_release_ms=90.0)

    # quiet sub under the Puente so the breakdown keeps weight on a club system
    song.notes("bd_sub", xm.deep_bass(cutoff=200.0, harm=0.1, drive=1.1, attack=0.3, decay=2.0, sustain=0.9,
                                      release=0.6),
               lambda c: [(0, 15.0, root_at(c), 0.7)] if c.kind == "breakdown" and c.bars_left > 2 else [],
               bus="bass", gain_db=-9.0)

    # ---------------------------------------------------------------- music
    arp = ARPS[int(rng.integers(len(ARPS)))]
    guitar = xm.nylon(bright=float(rng.uniform(0.35, 0.5)), body_hz=float(rng.uniform(180, 240)))

    def gtr_notes(c):
        if c.kind == "intro" or c.bar >= drums_only_from:
            return []
        ch = chord_at(c)
        tones = [ch[0], ch[1], ch[2], ch[0] + 12, ch[1] + 12]
        ev = [(s, l, tones[k], 0.75 + 0.2 * (s % 8 == 0)) for s, l, k in arp]
        if c.kind == "outro":
            return ev if c.i % 2 == 0 else ev[:3]
        return ev

    gl = song.notes("guitar", guitar, gtr_notes, gain_db=-6.5, pan=-0.25, sends={"reverb": 0.18, "delay8": 0.1},
                    sidechain=0.2, humanize=0.1)
    gl.automate("lp", [(verso.start_bar, 2500), (verso.start_bar + 4, 9000), (outro.start_bar, 9000),
                       (drums_only_from, 900)])

    pad = song.notes("pad", xm.soft_pad(attack=0.5, cutoff=float(rng.uniform(1300, 1900))),
                     lambda c: [(0, 15.5, chord_at(c), 0.7)] if c.kind in ("groove", "breakdown", "drop") else [],
                     gain_db=-12.5 if not dark else -11.0, sends={"hall": 0.25}, width=1.5, sidechain=0.35)
    pad.automate("gain_db", song.section_points({"Puente": 3.0, "Perreo": -3.0}, 0.0, ramp_bars=1))

    # hook (square pluck) — chord-aware call/response, generated per seed
    rhythm = HOOK_RHYTHMS[int(rng.integers(len(HOOK_RHYTHMS)))]
    lo, hi = key.root(4) - 5, key.root(5) + 2
    hook = xm.make_melody(rng, nat, chords, rhythm, lo, hi)
    hook_clip = clip(hook, 4)
    lead_inst = xm.square_pluck(pw=float(rng.uniform(0.3, 0.45)), cutoff=float(rng.uniform(800, 1200)),
                                env_amt=float(rng.uniform(3500, 6000)), decay=float(rng.uniform(0.08, 0.13)))

    def hook_notes(c):
        if c.kind == "drop":
            return hook_clip(c)
        if c.kind == "breakdown" and c.bars_left > 2:
            return hook_clip(c) if c.i % 4 < 2 else []
        if c.kind == "groove" and c.bars_left <= 2:
            return [e for e in hook_clip(c)][:3]
        return []

    hl = song.notes("hook", lead_inst, hook_notes, gain_db=-6.0, sends={"delay": 0.22, "reverb": 0.15}, width=1.3,
                    sidechain=0.3)
    hl.automate("lp", [(puente.start_bar, 1400), (puente.end_bar - 2, 4000), (puente.end_bar, 16000)])
    if not dark:
        song.notes("hook_bell", xm.rhodes(bright=0.9, bark=0.2, trem=0.0, wow_cents=0.0),
                   lambda c: [(s, l, m + 12, v * 0.8) for s, l, m, v in hook_clip(c)] if c.name == "Perreo" else [],
                   gain_db=-14.0, sends={"delay": 0.25, "hall": 0.1}, pan=0.2)
    else:
        vox = xm.chant(vowel="o", vowel_to="a", voices=3, shift=1.15, fall=-1.5, breath=0.15, spread=0.5)
        cell = [(3, 2, 0, 0.9), (6, 3, 2, 0.85), (11, 2, 0, 0.8), (14, 2, 4, 0.85)]

        def vox_notes(c):
            if c.name == "Perreo" or (c.name == "Coro" and c.i >= 8):
                ch = chord_at(c)
                return [(s, l, sorted(ch)[k % 3] + 12, v) for s, l, k, v in cell]
            return []

        song.notes("vox_chop", vox, vox_notes, bus="vox", gain_db=-9.0, sends={"delay": 0.2, "reverb": 0.2},
                   sidechain=0.25)

    # ---------------------------------------------------------------- fx
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.12})
    crash = drums.crash(decay=2.2, rng=rng)
    bar = song.grid.bar_sec
    for s in song.sections:
        if s.kind in ("drop",):
            fxl.add(crash, s.start_bar, gain_db=-9.0)
            fxl.add(fx.reverse_cymbal(bar * 1.0, rng=rng), s.start_bar, align="end", gain_db=-11.0)
        if s.kind == "groove":
            fxl.add(crash, s.start_bar, gain_db=-12.0)
            fxl.add(fx.noise_sweep(bar * 4, up=True, rng=rng), s.start_bar, align="end", gain_db=-20.0)
        if s.kind == "breakdown":
            fxl.add(fx.downlifter(bar * 2, rng=rng), s.start_bar, gain_db=-12.0)
            fxl.add(fx.riser(bar * 4, "noise", rng=rng), s.end_bar, align="end", gain_db=-12.0)
    if not dark:
        fxl.add(xm.siren(bar * 2, rng=rng), perreo.start_bar - 2, gain_db=-17.0)
    fxl.add(fx.impact(2.5, rng=rng), perreo.start_bar, gain_db=-11.0)
    fxl.add(crash, outro.start_bar, gain_db=-12.0)

    # ---------------------------------------------------------------- mix
    song.buses["drums"].eq = [("peak", 3200.0, 1.5, 0.8), ("peak", 170.0, -2.0, 0.9)]
    song.buses["bass"].eq = [("lowshelf", 55.0, 2.5, 0.7), ("peak", 150.0, -3.0, 0.9)]
    song.buses["music"].eq = [("peak", 2200.0, 1.0, 0.7)]
    song.buses["drums"].width = 1.1
    song.master.lufs = -10.0
    song.instruments = ["dembow snare + rim", "tuned reggaeton kick", "808 sub (with perreo glides)", "timbales",
                        "congas", "shaker & hats", "nylon-guitar arpeggio (Karplus-Strong)", "square pluck hook",
                        "warm pad"] + (["güiro", "siren FX"] if not dark else ["formant vocal chops", "FM perc"])
    if dark:
        song.description_he = (f"רגאטון לילי ואפל ב-{int(song.bpm)} BPM בסולם {plan['key']}: דמבו קלאסי עם תופי "
                               f"טימבלס, 808 עמוק, ארפג'ו של גיטרה ניילון במינור הרמוני (אקורד V מז'ורי שנותן צבע "
                               f"לטיני-דרמטי), פלאק מלודי וצ'ופים ווקאליים סינתטיים. בדרופ ה-Perreo נכנס 808 "
                               f"מעוות עם גלישות — אנרגיה שעולה בהדרגה, מתאים לבניית הסט.")
    else:
        song.description_he = (f"רגאטון חם ומקפיץ ב-{int(song.bpm)} BPM בסולם {plan['key']}: ריתם דמבו קלאסי "
                               f"(קיק עם הדגשה על 1 ו-3 וסנר-רים על ה\"בום-צ'יק\"), טימבלס, קונגות וגוויירו, 808 "
                               f"שעוקב אחרי הקיק, ארפג'ו גיטרה ניילון ופלאק עם הוק קליט. דרופ Perreo כבד עם 808 "
                               f"גולש וסירנה — לרגעי השיא ברחבה.")
    cam = plan.get("camelot", "")
    song.mix_tips_he = (f"טיפ ערבוב: אינטרו של 16 תיבות תופים בלבד (בלי באס ובלי מלודיה). ה-808 והגיטרה "
                        f"נכנסים בתיבה {verso.start_bar + 1} (Hot Cue B), הפזמון בתיבה {coro.start_bar + 1}, "
                        f"הברייק בתיבה {puente.start_bar + 1} ודרופ ה-Perreo בתיבה {perreo.start_bar + 1}. "
                        f"האאוטרו מתחיל בתיבה {outro.start_bar + 1} ו-8 התיבות האחרונות הן תופים בלבד. "
                        f"{xm.wheel_he(cam)} "
                        + (xm.partners_he(plan) + ". " if xm.partners_he(plan) else "")
                        + f"ב-{int(song.bpm)} BPM אפשר לעבור להיפ-הופ (92–95) כמעט בלי לגעת ב-Pitch.")
    return song


