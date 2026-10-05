"""Pop Dance recipe (120–126 BPM): radio dance / tropical pop.

Genre brief
-----------
* Harmony: uplifting four-chord pop loops, one chord per bar — I–V–vi–IV family in major keys,
  vi–IV–I–V (= i–VI–III–VII) in minor keys.
* Topline: a catchy, chord-aware synth melody (no real vocals) generated per seed from pop rhythms
  (call/response over 2+2 bars, strong beats on chord tones, resolves to the tonic).
* Two flavours chosen from the key (deterministic):
  - **tropical** (major keys): pan-flute style topline (sine/triangle + breath, vibrato, legato
    glides), marimba arpeggios, synthetic formant vocal chops answering the topline, snaps, shaker,
    tambourine, a dotted, round bass.
  - **radio** (minor keys): "sung" detuned-saw topline with scoops and vibrato, bright saw plucks,
    piano chords in the verse, pumping supersaw chord stabs in the chorus, a syncopated octave
    house bass.
* Verses: chords and plucks low-pass filtered, the topline only teases. Choruses ("drops"): filters
  wide open, full topline, crash + soft impact, clap roll and riser into every chorus.
* DJ rules: drums-only first 16 bars, bass in at bar 17, outro mirrors the intro (last 16 bars
  drums only), every section on the 8-bar grid, fills/crashes every 8 bars.
"""
from __future__ import annotations

import numpy as np

from .. import drums, ext_mainstream as xm, fx, instruments as inst
from ..arrangement import Song, clip
from ..theory import voice_lead
from . import register

# 112 bars ≈ 3.6 min at 122–124 BPM
TPL_TROPICAL = [("Intro", "intro", 16, 4, 0), ("Verse", "groove", 16, 5, 1), ("Pre-Chorus", "build", 8, 6, 0),
                ("Chorus", "drop", 16, 8, 2), ("Breakdown", "breakdown", 16, 4, 0), ("Chorus 2", "drop", 16, 8, 3),
                ("Outro", "outro", 24, 4, 0)]
TPL_RADIO = [("Intro", "intro", 32, 4, 0), ("Verse", "groove", 8, 5, 1), ("Chorus", "drop", 16, 8, 2),
             ("Breakdown", "breakdown", 16, 4, 0), ("Chorus 2", "drop", 16, 8, 3), ("Outro", "outro", 24, 4, 0)]

PROGS_MAJOR = [[0, 4, 5, 3], [5, 3, 0, 4], [0, 5, 3, 4], [3, 0, 4, 5]]
PROGS_MINOR = [[0, 5, 2, 6], [5, 2, 6, 0], [0, 5, 6, 2]]

# topline rhythms over 2 bars: (step, len, vel)
TOPLINE_RHYTHMS = [
    [(0, 2, .9), (3, 2, .8), (6, 3, .95), (10, 2, .8), (12, 2, .85), (14, 4, .9), (19, 2, .8), (22, 2, .85),
     (24, 6, .95)],
    [(2, 2, .85), (4, 2, .8), (6, 2, .9), (8, 4, .95), (14, 2, .8), (16, 2, .85), (18, 2, .8), (20, 3, .9),
     (24, 7, .95)],
    [(0, 3, .95), (3, 3, .85), (6, 2, .8), (8, 2, .85), (10, 2, .8), (12, 4, .9), (16, 3, .95), (19, 3, .85),
     (22, 2, .8), (24, 4, .9), (28, 3, .85)],
    [(1, 2, .85), (3, 2, .9), (6, 2, .85), (8, 3, .95), (11, 3, .85), (16, 2, .9), (19, 2, .85), (22, 2, .9),
     (24, 6, .95)],
]
# arps (step, len, chord-tone index) per bar
ARPS = [
    [(0, 2, 0), (2, 2, 1), (4, 2, 2), (6, 2, 3), (8, 2, 2), (10, 2, 1), (12, 2, 2), (14, 2, 3)],
    [(0, 2, 0), (3, 2, 2), (6, 2, 1), (8, 2, 3), (11, 2, 2), (14, 2, 4)],
    [(0, 1, 2), (2, 1, 1), (3, 2, 3), (6, 1, 2), (8, 1, 0), (10, 1, 1), (11, 2, 2), (14, 2, 3)],
]
BASS_TROP = [(0, 3, 0, 0.95), (3, 2, 0, 0.8), (6, 2, 12, 0.8), (8, 3, 0, 0.95), (11, 2, 0, 0.8), (14, 2, 7, 0.85)]
BASS_RADIO = [(2, 2, 0, 1.0), (6, 1, 0, 0.8), (7, 1, 12, 0.85), (10, 2, 0, 1.0), (14, 1, 12, 0.85), (15, 1, 0, 0.7)]

FOUR = "x...x...x...x..."
CLAP = "....x.......x..."
OPEN_HAT = "..x...x...x...x."
SHAKER = ["xgoxxgoxxgoxxgox", "ogxgogxgogxgogxg", "x.oxx.oxx.oxx.ox"]
TAMB = "....x.......x..."


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


@register("pop_dance")
def build(plan: dict, rng: np.random.Generator) -> Song:
    song = Song(plan, rng, swing=float(rng.choice([50.0, 52.0, 54.0])))
    key = song.key
    tropical = key.quality == "major"
    song.arrange(TPL_TROPICAL if tropical else TPL_RADIO, song.target_bars())
    intro, outro = song.find("intro"), song.find("outro")
    verse, bd = song.find("groove"), song.find("breakdown")
    drops = [s for s in song.sections if s.kind == "drop"]
    song.mix_in_bar = 16
    bass_off = outro.end_bar - 16
    bar_sec = song.grid.bar_sec

    windows = []   # roll + riser into every chorus
    for d in drops:
        prev = song.section_before(d)
        rb = 8 if prev.kind == "build" else 4
        windows.append((d.start_bar - rb, d.start_bar))

    def to_drop(bar):
        for a, b in windows:
            if a <= bar < b:
                return b - bar
        return None

    # ---------------------------------------------------------------- harmony
    degs = (PROGS_MAJOR if tropical else PROGS_MINOR)[int(rng.integers(4 if tropical else 3))]
    t0 = min((key.root(o) for o in (3, 4, 5)), key=lambda m: abs(m - 64))   # tonic nearest E4
    chords, prev = [], None
    for d in degs:
        ch = voice_lead(prev, key.chord(d, 3, 3), center=t0 + (4 if tropical else -3))
        chords.append(ch)
        prev = ch
    roots = [in_range(key.degree(d, 1), 33, 44) if tropical else in_range(key.degree(d, 1), 28, 40) for d in degs]

    def chord_at(c):
        return chords[c.i % 4]

    def root_at(c):
        return roots[c.i % 4]

    # topline (generated per seed, chord-aware) as a MonoLine with legato glides
    rhythm = TOPLINE_RHYTHMS[int(rng.integers(len(TOPLINE_RHYTHMS)))]
    lo, hi = (t0 + 16, t0 + 29) if tropical else (t0 - 3, t0 + 12)
    mel = xm.make_melody(rng, key, chords, rhythm, lo, hi)
    top = []
    for j, (s, ln, m, v) in enumerate(mel):
        nxt = mel[j + 1] if j + 1 < len(mel) else None
        fl = ""
        if nxt is not None and abs(nxt[0] - (s + ln)) < 0.01 and abs(nxt[2] - m) <= 4 and rng.random() < 0.6:
            fl = "s"
        top.append((s, ln, m, v, fl))
    top_clip = clip(top, 4)

    # ---------------------------------------------------------------- drums
    kick_hz = float(np.clip(440 * 2 ** ((in_range(key.root(1), 28, 39) - 69) / 12), 45, 60))
    if kick_hz > 58:
        kick_hz *= 2 ** (-5 / 12)
    kick = drums.kick("house", tune_hz=kick_hz, decay=float(rng.uniform(0.3, 0.38)) * (1.0 if tropical else 1.25), click=float(rng.uniform(0.5, 0.7)),
                      drive=1.6, rng=rng)

    def kick_pat(c):
        tb = to_drop(c.bar)
        if tb == 1:
            return "x...x...x......."
        if c.kind == "breakdown" and tb is None:
            return "x..............." if c.first else None
        return FOUR

    song.hits("kick", kick, kick_pat, gain_db=-1.5, sc_source=True, humanize=0.0)

    clap = drums.clap(tightness=1.0, tone_hz=float(rng.uniform(1300, 1600)), tail=0.12, bursts=3, rng=rng)
    snap = drums.snap(rng=rng)
    n = max(clap.shape[0], snap.shape[0])
    cs = np.zeros(n, dtype=np.float32)
    cs[:clap.shape[0]] += clap
    cs[:snap.shape[0]] += snap * (0.7 if tropical else 0.4)
    cs = xm.normalize(cs)

    def clap_pat(c):
        tb = to_drop(c.bar)
        if (c.kind == "breakdown" and tb is None) or (tb is not None and tb <= 2):
            return None
        if c.kind == "intro" and c.i < 4:
            return None
        if c.kind == "outro" and c.bars_left <= 4:
            return None
        if c.phrase_end and c.kind in ("drop", "groove"):
            return "....x.......x.x."
        return CLAP

    song.hits("clap", cs, clap_pat, gain_db=-4.0, sends={"reverb": 0.14}, humanize=0.04)
    hat = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.2}, decay=0.03, tone=1.15)
    ohat = drums.hat(open_=True, decay=0.16, tone=1.1, rng=rng)

    def oh_pat(c):
        if c.kind == "breakdown" or (c.kind == "intro" and c.i < 8) or (c.kind == "outro" and c.bars_left <= 8):
            return None
        return OPEN_HAT

    song.hits("open_hat", ohat, oh_pat, gain_db=-13.5, pan=-0.15, sends={"room": 0.08})
    song.hits("hats", hat, lambda c: None if c.kind == "breakdown" and to_drop(c.bar) is None else
              ("x.x.x.x.x.x.x.x." if c.kind != "drop" else "x.xgx.xgx.xgx.xx"), gain_db=-11.0 if tropical else -12.5, pan=0.25, humanize=0.1)
    shk = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=0.08)
    sp = SHAKER[int(rng.integers(len(SHAKER)))]
    song.hits("shaker", shk, lambda c: sp if not (c.kind == "intro" and c.i < 2) else None, gain_db=-13.0 if tropical else -14.5,
              pan=-0.45, humanize=0.15, timing_ms=1.5)
    if tropical:
        tam = drums.tambourine(rng=rng)
        song.hits("tamb", tam, lambda c: TAMB if c.kind == "drop" or (c.kind == "intro" and c.i >= 8) else None,
                  gain_db=-13.5, pan=0.45)
        bongos = [drums.bongo(float(rng.uniform(420, 480)), "open", rng=rng),
                  drums.bongo(float(rng.uniform(600, 680)), "open", rng=rng)]
        song.hits("bongo", bongos, lambda c: "...x..x....x.x.." if c.kind in ("groove", "drop", "outro") or
                  (c.kind == "intro" and c.i >= 8) else None, gain_db=-15.5, pan=0.55, sends={"room": 0.12},
                  humanize=0.12)
    else:
        rim = drums.rimshot(float(rng.uniform(1600, 1900)), rng=rng)
        song.hits("rim", rim, lambda c: "......x.......x." if c.kind in ("groove", "drop") or
                  (c.kind == "intro" and c.i >= 8 and c.bars_left > 0) else None, gain_db=-16.0, pan=0.4,
                  sends={"delay8": 0.12})

    roll = song.audio("roll", bus="drums", sends={"reverb": 0.15})
    for a, b in windows:
        roll.add(xm.build_roll(song, cs, a, b - a, semis=(0.0, 7.0), vel=(0.3, 0.9), last_beat_rest=True), a,
                 gain_db=-8.0)

    # ---------------------------------------------------------------- bass
    if tropical:
        bass_inst = inst.bass_pluck(cutoff=380.0, env_amt=1500.0, decay=0.16, res=0.2, sub=0.8, drive=1.4,
                                    sustain=0.55, grit=0.25)
        pat = BASS_TROP
    else:
        bass_inst = inst.bass_pluck(cutoff=520.0, env_amt=2400.0, decay=0.1, res=0.3, sub=0.65, drive=1.7,
                                    sustain=0.4, grit=0.4)
        pat = BASS_RADIO

    def bass_notes(c):
        if c.bar < 16 or c.bar >= bass_off or (c.kind == "breakdown"):
            return []
        tb = to_drop(c.bar)
        r = root_at(c) if c.kind != "intro" else roots[0]
        if tb is not None and tb <= 2:
            return [(s, 1.5, r, 0.85) for s in (0, 2, 4, 6, 8, 10)] if tb == 2 else [(0, 2, r, 0.9)]
        return [(s, ln, r + o, v) for s, ln, o, v in pat]

    bl = song.notes("bass", bass_inst, bass_notes, bus="bass", gain_db=-6.0 if tropical else -5.0, sidechain=0.55, sc_release_ms=140.0)
    bl.automate("lp", [(16, 300), (intro.end_bar - 0.01, 1500 if tropical else 2500), (intro.end_bar, 8000)])

    # ---------------------------------------------------------------- chords / plucks
    arp = ARPS[int(rng.integers(len(ARPS)))]

    def arp_notes(c):
        if c.kind == "breakdown" and to_drop(c.bar) is None:
            return []
        if c.bar >= bass_off or (c.kind == "intro" and c.i < (24 if not tropical else 99)):
            return []
        ts = tones(chord_at(c), t0 + (9 if tropical else -5))
        return [(s, ln, ts[k], 0.85 if s % 4 == 0 else 0.7) for s, ln, k in arp]

    if tropical:
        arp_inst = inst.mallet("marimba", release=0.2)
        al = song.notes("marimba", arp_inst, arp_notes, gain_db=-6.5, pan=-0.35, sends={"delay8": 0.25, "reverb": 0.12},
                        sidechain=0.3, humanize=0.08)
    else:
        arp_inst = inst.pluck(wave="saw", cutoff=900.0, env_amt=6000.0, decay=0.1, release=0.1, width=0.7)
        al = song.notes("pluck", arp_inst, arp_notes, gain_db=-9.0, width=1.5, sends={"delay": 0.18, "reverb": 0.1},
                        sidechain=0.4, humanize=0.06)

    # filtered in the verse / intro, wide open in the choruses
    lp_pts = [(0, 900.0)]
    for s in song.sections:
        if s.kind == "drop":
            lp_pts += [(s.start_bar - 0.01, lp_pts[-1][1]), (s.start_bar, 14000.0), (s.end_bar - 0.01, 14000.0)]
        elif s.kind == "build":
            lp_pts += [(s.start_bar, 1200.0), (s.end_bar - 0.01, 6000.0)]
        elif s.kind in ("groove", "intro"):
            lp_pts += [(s.start_bar, 1100.0), (s.end_bar - 0.01, 1800.0 if s.kind == "groove" else 1100.0)]
        elif s.kind == "breakdown":
            lp_pts += [(s.start_bar, 3000.0), (s.end_bar - 4.01, 3000.0), (s.end_bar - 0.01, 8000.0)]
        else:
            lp_pts += [(s.start_bar, 3000.0), (bass_off, 600.0)]
    al.automate("lp", lp_pts)

    # offbeat chords: piano (verse/breakdown) + pumping stabs (chorus)
    def chord_notes(c):
        ch = chord_at(c)
        if c.kind == "drop":
            return [(s, 1.5, ch, 0.85) for s in (2, 6, 10, 14)] if tropical else \
                [(s, 1.8, ch + [ch[0] + 12], 0.9) for s in (2, 6, 10, 14)]
        return []

    stab = (inst.stab(wave="square", cutoff=1200.0, env_amt=4000.0, decay=0.14, amp_decay=0.25) if tropical else
            xm.supersaw_stab(detune=0.35, cutoff=1800.0, env_amt=6000.0, f_decay=0.1, decay=0.3, sustain=0.0,
                             release=0.1, drive=1.3))
    song.notes("chords", stab, chord_notes, gain_db=-7.0 if tropical else -9.0, width=1.6, sidechain=0.6,
               sc_release_ms=160.0, sends={"reverb": 0.12})
    piano = inst.piano(bright=0.6, release=0.35)

    def piano_notes(c):
        ch = chord_at(c)
        if c.kind == "groove" or (c.kind == "build" and (to_drop(c.bar) or 9) > 2):
            return [(0, 3, ch, 0.75), (6, 2, ch, 0.65), (10, 3, ch, 0.7)]
        if c.kind == "breakdown" and to_drop(c.bar) is None:
            return [(0, 14, ch, 0.7), (0, 14, [ch[0] - 12], 0.6)]
        return []

    song.notes("piano", piano, piano_notes, gain_db=-9.5, width=1.3, sidechain=0.35, sends={"hall": 0.2})
    pad = song.notes("pad", xm.soft_pad(attack=0.5, cutoff=1800.0), lambda c: [(0, 16, chord_at(c), 0.7)]
                     if c.kind in ("breakdown", "drop", "build") else [], gain_db=-13.0, width=1.6, sidechain=0.55,
                     sends={"hall": 0.25})
    pad.automate("gain_db", song.section_points({"breakdown": 0.0, "build": -2.0, "drop": -4.0}, -60.0))

    # ---------------------------------------------------------------- topline
    if tropical:
        lead = xm.GlideSynth(osc="flute", cutoff=7000.0, attack=0.025, decay=0.4, sustain=0.85, release=0.12,
                             glide_ms=70.0, vib_cents=22.0, vib_hz=5.2, vib_delay=0.18, scoop=-0.6, breath=0.35, drive=1.8,
                             chiff=0.25, gain=0.75, seed=song.seed)
    else:
        lead = xm.GlideSynth(osc="saw", voices=3, detune_cents=12.0, spread=0.5, cutoff=2600.0, res=0.15,
                             env_amt=1.3, env_decay=0.12, attack=0.006, decay=0.3, sustain=0.75, release=0.1,
                             glide_ms=55.0, vib_cents=18.0, vib_hz=5.6, vib_delay=0.22, scoop=-1.0, drive=1.3,
                             gain=0.7, seed=song.seed)

    def top_notes(c):
        tb = to_drop(c.bar)
        if c.kind == "drop":
            return top_clip(c)
        if c.kind == "breakdown" and tb is None and c.i >= 4:
            return top_clip(c)
        if c.kind == "groove" and c.i % 4 < 2:        # verse tease: first phrase only
            return top_clip(c)
        return []

    tl = song.line("topline", lead, top_notes, bus="music", gain_db=-6.0 if tropical else -5.5, width=1.2, sidechain=0.25,
                   sends={"delay": 0.2, "reverb": 0.15})
    tl.automate("gain_db", song.section_points({"groove": -5.0, "breakdown": -3.0, "drop": 0.0}, 0.0))
    if tropical:
        chop = inst.vocal_chop(vowel="a", vowel_to="o", shift=1.15, scoop=-1.5)

        def chop_notes(c):
            if c.kind != "drop":
                return []
            ts = tones(chord_at(c), t0 + 9)
            return [(4, 1, ts[2], 0.85), (7, 1, ts[1], 0.75), (10, 2, ts[2], 0.9)] if c.i % 2 == 1 else []

        song.notes("vox_chop", chop, chop_notes, bus="vox", gain_db=-6.5, pan=0.3, sends={"delay8": 0.2, "reverb": 0.2},
                   sidechain=0.3)
    else:
        bell = inst.bell(ratio=3.5, index=2.2, decay=0.6)
        song.notes("topline_bell", bell, lambda c: [(s, ln, m + 12, v * 0.8) for s, ln, m, v, *_ in top_clip(c)]
                   if c.name == "Chorus 2" else [], gain_db=-15.0, sends={"delay": 0.25, "hall": 0.1}, pan=0.15)

    # ---------------------------------------------------------------- fx
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.1})
    crash = drums.crash(decay=2.0, rng=rng)
    for d in drops:
        for k in range(0, d.bars, 8):
            fxl.add(crash, d.start_bar + k, gain_db=-10.0 if k == 0 else -13.0)
        fxl.add(fx.impact(2.0, rng=rng), d.start_bar, gain_db=-14.0)
    for a, b in windows:
        fxl.add(fx.riser((b - a) * bar_sec, "noise", rng=rng), b, align="end", gain_db=-13.0)
        fxl.add(fx.reverse_cymbal(bar_sec, rng=rng), b, align="end", gain_db=-12.0)
    for s in song.sections:
        if s.kind in ("groove", "outro", "breakdown"):
            fxl.add(crash, s.start_bar, gain_db=-13.0)
        if s.kind == "breakdown":
            fxl.add(fx.downlifter(bar_sec * 2, rng=rng), s.start_bar, gain_db=-14.0)
    fxl.add(crash, 16, gain_db=-14.0)
    fxl.add(fx.noise_sweep(bar_sec * 4, up=True, rng=rng), 16, align="end", gain_db=-21.0)
    fxl.add(crash, bass_off, gain_db=-14.0)

    # ---------------------------------------------------------------- mix
    song.buses["drums"].eq = [("peak", 5000.0, 3.0 if tropical else 1.5, 0.7), ("peak", 300.0, -1.5, 1.0)]
    song.buses["bass"].eq = [("lowshelf", 60.0, 1.5 if tropical else 2.0, 0.7), ("peak", 140.0, -3.0, 0.8)]
    song.buses["music"].eq = [("peak", 2500.0, 3.0 if tropical else 1.5, 0.7), ("peak", 450.0, -3.0 if tropical else -1.5, 0.9)]
    if tropical:
        song.buses["music"].eq.append(("peak", 5500.0, 2.0, 0.8))
    song.master.lufs = -9.0
    song.master.high_shelf_db = 2.5 if tropical else 1.5

    names = ["I", "ii", "iii", "IV", "V", "vi", "vii°"] if tropical else ["i", "ii°", "III", "iv", "v", "VI", "VII"]
    progname = "–".join(names[d] for d in degs)
    ch1, ch2 = drops[0], drops[1]
    if tropical:
        song.instruments = ["house kick", "clap + snap", "shaker", "tambourine", "bongos", "round dotted bass",
                            "marimba arpeggios", "pan-flute synth topline", "formant vocal chops", "piano",
                            "square chord stabs", "warm pad", "clap-roll build", "riser"]
        song.description_he = (f"פופ דאנס טרופי ושמשי ב-{int(song.bpm)} BPM בסולם {plan['key']}: לופ אקורדים "
                               f"אופטימי {progname}, ארפג'ו של מרימבה, ליין מלודי של \"חליל פאן\" סינתטי עם גלישות "
                               f"וויברטו, וצ'ופים ווקאליים סינתטיים שעונים לו (בלי שירה אמיתית). בבית האקורדים "
                               f"מסוננים, ובפזמון הכול נפתח — טראק שמח לשקיעה על החוף או לחימום הרחבה.")
    else:
        song.instruments = ["house kick", "snappy clap", "rimshot", "shaker", "syncopated octave bass",
                            "bright saw plucks", "supersaw chord stabs", "detuned-saw 'sung' topline", "piano",
                            "FM bell", "warm pad", "clap-roll build", "riser"]
        song.description_he = (f"פופ דאנס רדיופוני ב-{int(song.bpm)} BPM בסולם {plan['key']}: התקדמות {progname} "
                               f"מרוממת, פלאקים בהירים, פסנתר בבית ואקורדי סופרסאו פועמים בפזמון, באס אוקטבות "
                               f"מסונכפ וליין מלודי סינתטי \"שר\" עם גלישות וויברטו (בלי שירה אמיתית). ברייקדאון עם "
                               f"פסנתר ופד, רול של קלאפים ופזמון שני עם פעמון — מושלם לבניית אנרגיה בסט.")
    cam = plan.get("camelot", "")
    partners = xm.partners_he(plan)
    song.mix_tips_he = (
        f"טיפ ערבוב: אינטרו של {intro.bars} תיבות — 16 התיבות הראשונות תופים בלבד, הבאס נכנס בתיבה 17 "
        f"(Hot Cue B). הבית מתחיל בתיבה {verse.start_bar + 1}, הפזמון הראשון (Hot Cue D) בתיבה "
        f"{ch1.start_bar + 1}, הברייקדאון בתיבה {bd.start_bar + 1} והפזמון השני בתיבה {ch2.start_bar + 1}. "
        f"באאוטרו הבאס יוצא בתיבה {bass_off + 1} ו-16 התיבות האחרונות הן תופים בלבד. "
        f"{xm.wheel_he(cam)} " + (partners + ". " if partners else "")
        + "כשנכנסים מטראק האוס, עשו Bass Swap בדיוק בתיבה 17 — הקיק כבר מסונכרן והמלודיה עוד לא התחילה.")
    return song
