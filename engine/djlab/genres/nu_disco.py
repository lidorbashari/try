"""Nu-Disco recipe (112–122 BPM).

Disco groove reworked for the club: a tight round kick, open hat on every off-beat, 16th closed
hats, clap + tight snare on 2 & 4, 16th tambourine and shaker, congas; a funky octave bass that
follows the chords (root on the beat, octave on the "and", 16th pick-ups); Karplus-Strong muted
rhythm guitar ("chicken scratch" 16ths, strummed chord tones); a string machine with ensemble
chorus for pads and off-beat stabs; positive major-key 7th progressions; and the filter-house
"chorus": the music bus breathes through a slowly opening and closing low-pass with pumping
sidechain.

Flavors (``STYLE_BY_ID`` or ``plan["style"]``):
* ``mirrorball`` — French-touch filter house: strings + guitar loop under a sweeping filter,
                   formant "vocoder" vowel hook, a 16-bar filtered breakdown.
* ``funk``       — funkier: envelope-wah guitar, Rhodes comping, synth-brass stabs, busier
                   syncopated bass, a short 8-bar breakdown.

DJ rules: 32-bar drums-only intro (bass at bar 33 = Hot Cue B), 32-bar outro whose last 16 bars
are drums only, sections on 8-bar phrases, crashes/fills on phrase boundaries.
"""
from __future__ import annotations

import numpy as np

from .. import drums, ext_house as eh, fx, instruments as inst
from ..arrangement import Song, clip
from ..dsp import eq_peak
from ..theory import Key, voice_lead
from . import register

STYLE_BY_ID = {"house-12": "mirrorball", "house-13": "funk"}
STYLES = ("mirrorball", "funk")

TEMPLATES = {
    "mirrorball": [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 16, 5, 2), ("Breakdown", "breakdown", 16, 4, 0),
                   ("Chorus", "drop", 32, 7, 3), ("Outro", "outro", 32, 4, 0)],
    "funk": [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 24, 5, 2), ("Breakdown", "breakdown", 8, 4, 0),
             ("Chorus", "drop", 32, 7, 3), ("Outro", "outro", 32, 4, 0)],
}

PROGRESSIONS = [  # major key, one chord per bar
    [3, 4, 2, 5],     # IV  V  iii vi   (the "royal road")
    [0, 5, 1, 4],     # I   vi ii  V
    [1, 4, 0, 5],     # ii  V  I   vi
    [0, 3, 1, 4],     # I   IV ii  V
]
# bass (1 bar): (step, len, scale-steps from chord degree, vel)
OCTAVE_BASS = [
    [(0, 1.5, 0, 1.0), (2, 1.5, 7, 0.8), (4, 1.5, 0, 0.95), (6, 1.5, 7, 0.8), (8, 1.5, 0, 1.0), (10, 1.5, 7, 0.8),
     (12, 1.5, 0, 0.95), (14, 1, 7, 0.8), (15, 1, 6, 0.7)],
    [(0, 1.5, 0, 1.0), (2, 1, 7, 0.8), (3, 1, 7, 0.6), (4, 1.5, 0, 0.95), (6, 1.5, 7, 0.8), (8, 1.5, 0, 1.0),
     (10, 1, 7, 0.8), (11, 1, 4, 0.7), (12, 1.5, 0, 0.95), (14, 1.5, 7, 0.8)],
]
FUNK_BASS = [
    [(0, 1, 0, 1.0), (2, 1, 7, 0.85), (3, 1, 0, 0.6), (6, 1, 7, 0.9), (7, 1, 0, 0.7), (8, 1, 0, 1.0),
     (10, 1, 6, 0.8), (11, 1, 7, 0.9), (13, 1, 4, 0.75), (14, 1, 2, 0.8), (15, 1, 1, 0.7)],
    [(0, 1.5, 0, 1.0), (3, 1, 0, 0.7), (4, 1, 7, 0.9), (6, 1, 0, 0.7), (8, 1, 0, 1.0), (9, 1, 0, 0.6),
     (10, 1, 7, 0.9), (12, 1, 4, 0.8), (14, 1, 7, 0.85), (15, 1, 6, 0.7)],
]
GUITAR = ["x.xxx.xxx.xxx.xx", "..x...x.x.x...x.", "x.x.xxx.x.x.xx.x"]
GUITAR_VEL = "oXgxoXgxoXgxoXgx"
STRING_STABS = [[(6, 1, 0.85), (14, 1.5, 0.8)], [(3, 1, 0.8), (10, 1, 0.8), (14, 1.5, 0.85)]]
BRASS = [[(14, 1.5, 0.9)], [(6, 1, 0.8), (14, 1.5, 0.9)]]
# vocoder-ish hook (4 bars = 64 steps): (step, len, scale degree, vel)
HOOKS = [
    [(0, 2, 4, 0.9), (3, 1, 4, 0.7), (4, 3, 5, 0.9), (8, 2, 4, 0.8), (12, 4, 2, 0.85),
     (32, 2, 4, 0.9), (35, 1, 4, 0.7), (36, 3, 7, 0.9), (40, 2, 6, 0.8), (44, 6, 4, 0.85)],
    [(2, 2, 7, 0.9), (6, 2, 6, 0.8), (8, 4, 4, 0.9), (18, 2, 5, 0.8), (20, 6, 4, 0.85),
     (34, 2, 7, 0.9), (38, 2, 9, 0.85), (40, 4, 7, 0.9), (50, 2, 6, 0.8), (52, 6, 4, 0.85)],
]


@register("nu_disco")
def build(plan: dict, rng: np.random.Generator) -> Song:
    style = plan.get("style") or STYLE_BY_ID.get(plan.get("id", ""))
    if style not in STYLES:
        style = str(np.random.default_rng(int(plan.get("seed", 0)) + 401).choice(list(STYLES)))
    funk = style == "funk"
    song = Song(plan, rng, swing=float(rng.uniform(52.0, 55.0) if funk else rng.uniform(51.0, 53.0)))
    key: Key = song.key
    song.arrange(TEMPLATES[style], song.target_bars())
    groove = song.bar("groove")
    song.mix_in_bar = groove
    outro = song.find("outro")
    bd = song.find("breakdown")
    chorus = song.bar("drop")
    bass_off = outro.start_bar + outro.bars - 16

    # ================================================================ drums
    kick_s = drums.kick("house", tune_hz=eh.kick_tune(key, 44, 60), decay=float(rng.uniform(0.28, 0.33)),
                        click=float(rng.uniform(0.55, 0.7)), drive=1.4, rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown" or c.before("drop", 1):
            return None
        return "x...x...x...x..."

    song.hits("kick", kick_s, kick_pat, gain_db=-2.0, sc_source=True, humanize=0.0)

    clap = drums.variants(drums.clap, 3, rng, jitter={"tone_hz": 0.05}, tone_hz=float(rng.uniform(1150, 1400)),
                          tail=float(rng.uniform(0.14, 0.2)))
    snr = drums.snare(tone_hz=float(rng.uniform(190, 230)), snappy=0.75, decay=0.12, kind="tight", rng=rng)

    def backbeat(c):
        if c.kind == "breakdown":
            return "....x.......x..." if c.bars_left <= 2 else None
        if c.kind == "intro" and c.i < 8:
            return None
        return "....x.......x..." if not c.phrase_end else "....x.......x.xx"

    song.hits("clap", clap, backbeat, gain_db=-4.0, sends={"reverb": 0.22, "room": 0.12}, timing_ms=1.5)
    song.hits("snare", snr, lambda c: backbeat(c) if c.kind in ("groove", "drop") else None, gain_db=-10.0,
              sends={"room": 0.15})
    hats = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.12}, decay=float(rng.uniform(0.03, 0.045)),
                          tone=float(rng.uniform(1.0, 1.15)))
    song.hits("hats", hats, lambda c: "xgxgxgxgxgxgxgxg" if not (c.kind == "breakdown" and c.bars_left > 4)
              and not (c.kind == "intro" and c.i < 4) else None, gain_db=-15.0, pan=0.3, humanize=0.1)
    ohat = drums.hat(open_=True, decay=float(rng.uniform(0.22, 0.3)), tone=float(rng.uniform(1.0, 1.1)), rng=rng)
    song.hits("open_hat", ohat, lambda c: "..x...x...x...x." if c.kind in ("groove", "drop") or
              (c.kind == "intro" and c.i >= 8) or (c.kind == "outro" and c.bars_left > 8) else None,
              gain_db=-11.0, pan=-0.15, sends={"room": 0.1})
    tamb = drums.variants(drums.tambourine, 3, rng, jitter={"length": 0.15}, length=float(rng.uniform(0.14, 0.2)))
    song.hits("tamb", tamb, lambda c: ("gxoxgxoxgxoxgxox" if c.kind == "drop" else "..x...x...x...x.")
              if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 16) or (c.kind == "outro" and c.bars_left > 4)
              else None, gain_db=-15.5, pan=0.45, humanize=0.15, timing_ms=2.0)
    shk = drums.variants(drums.shaker, 3, rng, jitter={"length": 0.2}, length=0.08)
    song.hits("shaker", shk, lambda c: "gxgogxgogxgogxgo" if c.kind in ("groove", "drop", "breakdown") or
              (c.kind == "intro" and c.i >= 24) else None, gain_db=-18.0, pan=-0.5, humanize=0.15)
    congas = [drums.conga(eh.key_hz(key, 190, 250, rng), "open", rng=rng),
              drums.conga(eh.key_hz(key, 270, 340, rng), "slap", rng=rng)]
    song.hits("congas", congas, lambda c: ("...x..x....x.x.." if not c.phrase_end else "......x.x.xxx.xx")
              if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 24) else None,
              gain_db=-15.0, pan=-0.45, sends={"room": 0.15}, humanize=0.12)
    song.hits("snare_roll", snr, lambda c: eh.snare_roll(c, 4 if bd.bars >= 16 else 2), gain_db=-13.0,
              sends={"reverb": 0.2}).automate("gain_db", eh.ramp_into(song, "drop", 4, -10.0, 0.0))

    # ================================================================ harmony
    prog = PROGRESSIONS[int(rng.integers(len(PROGRESSIONS)))]
    root = eh.bass_root(key, 28)

    def chord_deg(c):
        return prog[c.i % len(prog)]

    def bass_note(deg_):
        n = key.degree(deg_, 1)
        while n < root - 2:
            n += 12
        while n > root + 14:
            n -= 12
        return n

    pad_ch, gtr_ch, stab_ch = {}, {}, {}
    prev = None
    for d in prog:
        ch = voice_lead(prev, key.chord(d, 3, 4), center=62)
        pad_ch[d] = ch
        prev = ch
        g = voice_lead(None, key.chord(d, 4, 3), center=69)
        gtr_ch[d] = g
        stab_ch[d] = voice_lead(None, key.chord(d, 4, 4), center=72)

    def music_on(c, start_groove=0):
        if c.kind == "intro" or c.bar >= bass_off:
            return False
        if c.kind == "groove":
            return c.i >= start_groove
        return True

    # ================================================================ bass
    riffs = FUNK_BASS if funk else OCTAVE_BASS
    riff = riffs[int(rng.integers(len(riffs)))]

    def bass_notes(c):
        if c.kind in ("intro", "breakdown") or c.bar >= bass_off:
            return []
        cd = chord_deg(c)
        ev = [(s, l, bass_note(cd + st), v) for s, l, st, v in riff]
        if c.before("drop", 1) or c.before("breakdown", 1):
            ev = [e for e in ev if e[0] < 8]
        return ev

    b_inst = inst.bass_pluck(cutoff=float(rng.uniform(380, 500)), env_amt=float(rng.uniform(2000, 3000)),
                             decay=float(rng.uniform(0.08, 0.11)), res=0.3, sub=0.7, drive=1.6, sustain=0.4,
                             grit=0.45, wave="square" if funk else "saw")
    bass = song.notes("bass", b_inst, bass_notes, bus="bass", gain_db=-4.0, sidechain=0.4, sc_release_ms=120.0,
                      humanize=0.05, timing_ms=2.0)
    bass.automate("lp", [(groove, 700), (groove + 8, 3500), (outro.start_bar, 3500), (bass_off, 700)])

    # ================================================================ guitar
    g_p = GUITAR[int(rng.integers(len(GUITAR)))]
    g_vel = {"X": 1.0, "x": 0.8, "o": 0.6, "g": 0.4}
    guitar = eh.muted_guitar(mute=float(rng.uniform(0.07, 0.1)), bright=0.62, wah=0.65 if funk else 0.0,
                             body_hz=float(rng.uniform(1700, 2200)))

    def guitar_notes(c):
        if not music_on(c, 8 if funk else 0) or (c.kind == "breakdown" and c.i < c.section.bars - 4):
            return []
        ch = gtr_ch[chord_deg(c)]
        out = []
        for st, (h, vch) in enumerate(zip(g_p, GUITAR_VEL)):
            if h == ".":
                continue
            v = g_vel.get(vch, 0.6)
            for j, m in enumerate(ch):        # strum: 4 ms between strings
                out.append((st + 0.03 * j, 0.6, m, v * (0.85 + 0.15 * (j == len(ch) - 1))))
        return out

    gl = song.notes("guitar", guitar, guitar_notes, gain_db=-11.0, pan=0.35, sidechain=0.35,
                    sends={"room": 0.15, "delay8": 0.08}, humanize=0.08)

    # ================================================================ strings & keys
    strings = eh.string_machine(attack=float(rng.uniform(0.15, 0.3)), release=0.8, cutoff=5200.0, octave=0.6)
    sl = song.notes("strings", strings, lambda c: [(0, 15.5, pad_ch[chord_deg(c)], 0.8)] if music_on(c, 8)
                    else [], gain_db=-12.0, sidechain=0.55, sc_release_ms=200.0, sends={"hall": 0.25},
                    fx=[eh.ensemble(mix=0.75)], hp=220.0)
    stab_r = STRING_STABS[int(rng.integers(len(STRING_STABS)))]
    stab_inst = eh.string_machine(attack=0.01, release=0.25, cutoff=6500.0, octave=0.8)
    song.notes("string_stabs", stab_inst, lambda c: [(s, l, stab_ch[chord_deg(c)], v) for s, l, v in stab_r]
               if c.kind == "drop" else [], gain_db=-11.0, sidechain=0.3, sends={"reverb": 0.2, "delay": 0.15},
               fx=[eh.ensemble(mix=0.6)], hp=300.0)

    if funk:
        rh = eh.rhodes(bright=0.7, bark=0.6, drive=0.35)
        comp = [(2, 1.5, 0.85), (6, 1, 0.65), (10, 1.5, 0.85), (13, 2, 0.75)]
        song.notes("rhodes", rh, lambda c: [(s, l, pad_ch[chord_deg(c)], v) for s, l, v in comp]
                   if music_on(c, 16) and c.kind != "breakdown" else [], gain_db=-12.0, sidechain=0.35, hp=180.0,
                   sends={"reverb": 0.15}, fx=[eh.autopan(song.bpm, 0.5, 0.3)])
        br = BRASS[int(rng.integers(len(BRASS)))]
        brass = inst.brass(cutoff=3200.0, release=0.1)
        song.notes("brass", brass, lambda c: [(s, l, stab_ch[chord_deg(c)], v) for s, l, v in br]
                   if c.kind == "drop" and c.i % 2 == 1 else [], gain_db=-11.0, sidechain=0.3, hp=250.0,
                   sends={"reverb": 0.2, "delay": 0.12}, width=1.3)

    # vocoder-ish vowel hook
    deg = key.degree
    hook = HOOKS[int(rng.integers(len(HOOKS)))]
    hclip = clip([(s, l, deg(d, 4), v) for s, l, d, v in hook], 4)
    voc = eh.chant(vowel="a", vowel_to="e" if funk else "o", shift=1.05, voices=3, detune_cents=7.0, vibrato=0.15,
                   breath=0.05, attack=0.02, release=0.12, scoop=-0.6)
    song.notes("vox_hook", voc, lambda c: hclip(c) if c.kind == "drop" or (c.kind == "breakdown" and c.i >= c.section.bars - 8)
               else [], bus="vox", gain_db=-8.0, sidechain=0.35, sends={"reverb": 0.2, "delay": 0.22}, hp=250.0,
               fx=[lambda x: eq_peak(x, 2500.0, 3.0, 0.8)])

    # ---- the filter-house breath: music layers sweep through a resonant low-pass
    def sweep_points(lo, hi):
        pts = [(groove, lo), (groove + 8, hi * 0.6)]
        pts += [(bd.start_bar, hi * 0.35), (bd.end_bar - 0.01, hi)]
        for b0 in range(chorus, outro.start_bar, 8):
            pts += [(b0, hi), (b0 + 4, hi * 0.3), (b0 + 7.99, hi)]
        pts += [(outro.start_bar, hi), (outro.start_bar + 8, hi * 0.25), (bass_off, lo)]
        return sorted(pts)

    for layer, lo, hi in ((sl, 600, 9000), (gl, 900, 12000)):
        layer.res = 1.1
        layer.automate("lp", sweep_points(lo, hi))

    # ================================================================ fx & mix
    eh.transitions(song, rng, crash_db=-8.5, impact_db=-11.0, riser_db=-10.0, riser_kind="noise",
                   downlifter=True, reverse=True)
    song.buses["drums"].eq = [("peak", 3000.0, 1.5, 0.8), ("highshelf", 9000.0, 1.0, 0.7)]
    song.buses["music"].eq = [("peak", 330.0, -2.0, 0.8), ("highshelf", 6000.0, 1.5, 0.7)]
    song.buses["drums"].width = 1.15
    song.returns["reverb"].decay = 1.6
    song.master.lufs = -9.0

    k = plan["key"]
    if funk:
        song.description_he = (f"נו-דיסקו פאנקי ב-{int(song.bpm)} BPM בסולם {k}: באס באוקטבות עם סינקופות, גיטרה עם "
                               f"וואה בשש-עשריות, רודס, סטאבים של כלי נשיפה סינתטיים וסטרינגס חמים — גרוב חיובי "
                               f"ומחויך לשעות המוקדמות.")
        song.instruments = ["tight house kick", "clap + snare", "16th hats", "off-beat open hat", "tambourine",
                            "shaker", "congas", "funky octave bass", "wah muted guitar (Karplus-Strong)",
                            "string machine + ensemble", "string stabs", "Rhodes-style e-piano", "synth brass",
                            "vocoder-like vowel hook"]
    else:
        song.description_he = (f"נו-דיסקו נוצץ ב-{int(song.bpm)} BPM בסולם {k}: באס דיסקו באוקטבות, גיטרה מושתקת "
                               f"בשש-עשריות, סטרינגס רחבים ופילטר האוס שנושם — נפתח ונסגר — בפזמון. אנרגיה חיובית "
                               f"ושמחה מתחת לכדור המראות.")
        song.instruments = ["tight house kick", "clap + snare", "16th hats", "off-beat open hat", "tambourine",
                            "shaker", "congas", "disco octave bass", "muted rhythm guitar (Karplus-Strong)",
                            "string machine + ensemble", "string stabs", "filter-house sweep", "vocoder-like vowel hook"]
    song.mix_tips_he = (song.auto_mix_tips_he() + " טראק בסולם מז'ור — מתחבר בצורה חלקה לטראקים במינור היחסי "
                        "(אותו מספר Camelot עם A).")
    return song
