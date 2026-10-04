"""House recipe — classic piano house, Chicago / New York feel (120–126 BPM).

Strong 909 kick, offbeat open hat (the house "tss"), 16th closed hats, 909 claps on 2 & 4, shaker,
tambourine and ride in the drop; a bouncy octave bassline (M1-style organ bass or a plucky saw
bass) following the chords; driving piano chord stabs (multi-string additive piano with hammer
noise and an FM 'bell' attack) on a hands-in-the-air minor progression, percussive drawbar organ
stabs through a rotary chorus, a string machine with ensemble chorus for the big breakdown,
"oh / ah" vowel chops, a riser + snare roll and a euphoric drop (impact + crash).

Flavors (``STYLE_BY_ID`` or ``plan["style"]``):
* ``hands`` — organ + piano anthem, vocal "oh" chops, a short second breakdown before drop 2.
* ``piano`` — the piano riff is the star from the groove on, strings + organ bass, one long
              breakdown with a solo piano that opens up.

DJ rules: 32-bar drums-only intro (bass at bar 33 = Hot Cue B), 32-bar outro whose last 16 bars
are drums only, sections on 8-bar phrases, crash + fill phrase markers.
"""
from __future__ import annotations

import numpy as np

from .. import drums, ext_house as eh, fx, instruments as inst
from ..arrangement import Song, clip
from ..dsp import eq_peak
from ..theory import Key, voice_lead
from . import register

STYLE_BY_ID = {"house-03": "hands", "house-04": "piano"}
STYLES = ("hands", "piano")

TEMPLATES = {
    "hands": [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 16, 6, 2), ("Breakdown", "breakdown", 16, 4, 0),
              ("Drop", "drop", 24, 8, 3), ("Breakdown 2", "breakdown", 8, 5, 0), ("Drop 2", "drop", 8, 9, 1),
              ("Outro", "outro", 32, 5, 0)],
    "piano": [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 24, 6, 2), ("Breakdown", "breakdown", 16, 4, 0),
              ("Drop", "drop", 32, 8, 3), ("Outro", "outro", 32, 5, 0)],
}

PROGRESSIONS = [[0, 5, 2, 6], [5, 6, 0, 0], [0, 3, 6, 2], [0, 5, 3, 6]]   # one chord per bar

# piano riffs: 1 bar of (step, len, vel); accents carry the groove
PIANO_RIFFS = [
    [(0, 1.5, 1.0), (3, 1.5, 0.85), (6, 1.5, 0.9), (10, 1.5, 0.85), (14, 2, 0.9)],
    [(0, 2, 1.0), (3, 1, 0.8), (6, 2, 0.9), (8, 1, 0.7), (11, 2, 0.9), (14, 1, 0.7)],
    [(2, 1, 0.9), (4, 1, 0.6), (6, 1, 0.9), (10, 1, 0.9), (12, 1, 0.6), (14, 1.5, 0.95)],
]
ORGAN_RHYTHM = [[(2, 1, 0.9), (6, 1, 0.75), (10, 1, 0.9), (14, 1, 0.75)],
                [(3, 1, 0.9), (6, 1, 0.7), (11, 1.5, 0.9)]]
# bass (2 bars): (step, len, scale-steps from the chord degree, vel)
BASS_RIFFS = [
    [(2, 1.5, 0, 1.0), (6, 1, 7, 0.8), (10, 1.5, 0, 1.0), (14, 1, 7, 0.8),
     (18, 1.5, 0, 1.0), (22, 1, 7, 0.8), (26, 1.5, 0, 1.0), (29, 1, 4, 0.7), (30, 1.5, 7, 0.8)],
    [(2, 1, 0, 1.0), (3, 1, 0, 0.6), (6, 1.5, 7, 0.9), (10, 1, 0, 1.0), (11, 1, 0, 0.6), (14, 1.5, 4, 0.9),
     (18, 1, 0, 1.0), (19, 1, 0, 0.6), (22, 1.5, 7, 0.9), (26, 1, 0, 1.0), (28, 1, 2, 0.7), (30, 1.5, 4, 0.9)],
    [(0, 1, 0, 0.7), (2, 2, 0, 1.0), (6, 1, 0, 0.7), (7, 1, 7, 0.8), (10, 2, 0, 1.0), (14, 1, 7, 0.8),
     (16, 1, 0, 0.7), (18, 2, 0, 1.0), (22, 1, 0, 0.7), (23, 1, 7, 0.8), (26, 2, 4, 1.0), (30, 1, 6, 0.8)],
]
VOX = [[(0, 3, 4, 0.95), (6, 1, 4, 0.7), (8, 4, 2, 0.85)], [(0, 2, 7, 0.95), (3, 2, 6, 0.8), (6, 6, 4, 0.9)]]


@register("house")
def build(plan: dict, rng: np.random.Generator) -> Song:
    style = plan.get("style") or STYLE_BY_ID.get(plan.get("id", ""))
    if style not in STYLES:
        style = str(np.random.default_rng(int(plan.get("seed", 0)) + 307).choice(list(STYLES)))
    song = Song(plan, rng, swing=float(rng.uniform(51.0, 54.0)))
    key: Key = song.key
    song.arrange(TEMPLATES[style], song.target_bars())
    groove = song.bar("groove")
    song.mix_in_bar = groove
    outro = song.find("outro")
    bd1 = song.find("breakdown")
    drop1 = song.bar("drop")
    bass_off = outro.start_bar + outro.bars - 16
    hands = style == "hands"

    # ================================================================ drums
    kick_s = drums.kick("909", tune_hz=eh.kick_tune(key, 46, 58), decay=float(rng.uniform(0.38, 0.45)),
                        click=float(rng.uniform(0.6, 0.75)), rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown" or c.before("drop", 1):
            return None
        if c.before("breakdown", 1):
            return "x...x...x......."
        return "x...x...x...x..."

    song.hits("kick", kick_s, kick_pat, gain_db=-1.5, sc_source=True, humanize=0.0)

    clap = drums.variants(drums.clap, 3, rng, jitter={"tone_hz": 0.05}, tone_hz=float(rng.uniform(1150, 1400)),
                          tail=float(rng.uniform(0.16, 0.22)))

    def clap_pat(c):
        if c.kind == "breakdown":
            return "....x.......x..." if c.bars_left <= 4 and c.section.bars > 8 else None
        if c.kind == "intro" and c.i < 8:
            return None
        return "....x.......x..." if not c.phrase_end else "....x.......x.xx"

    song.hits("clap", clap, clap_pat, gain_db=-3.0, sends={"reverb": 0.25, "room": 0.12}, timing_ms=1.0)

    hats = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.12}, decay=float(rng.uniform(0.035, 0.05)),
                          tone=float(rng.uniform(0.95, 1.1)))
    song.hits("hats", hats, lambda c: ("xoxoxoxoxoxoxoxo" if c.kind == "drop" else "x.x.x.x.x.x.x.x.")
              if not (c.kind == "breakdown" and c.bars_left > 4) and not (c.kind == "intro" and c.i < 4) else None,
              gain_db=-14.5, pan=0.25, humanize=0.1)
    ohat = drums.hat(open_=True, decay=float(rng.uniform(0.2, 0.28)), tone=float(rng.uniform(1.0, 1.1)), rng=rng)
    song.hits("open_hat", ohat, lambda c: "..x...x...x...x." if c.kind in ("groove", "drop") or
              (c.kind == "intro" and c.i >= 8) or (c.kind == "outro" and c.bars_left > 8) else None,
              gain_db=-10.5, pan=-0.12, sends={"room": 0.1})
    shk = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=float(rng.uniform(0.07, 0.09)))
    song.hits("shaker", shk, lambda c: "gxgogxgogxgogxgo" if c.kind in ("groove", "drop") or
              (c.kind == "intro" and c.i >= 16) or (c.kind == "outro" and c.bars_left > 4) else None,
              gain_db=-16.0, pan=-0.45, humanize=0.15, timing_ms=2.0)
    tamb = drums.tambourine(float(rng.uniform(0.16, 0.22)), rng=rng)
    song.hits("tamb", tamb, lambda c: ("..x...x...x...x." if c.i % 2 == 0 else "..x...x...x.x.x.")
              if c.kind == "drop" or (c.kind == "intro" and c.i >= 24) else None, gain_db=-17.0, pan=0.45)
    ride = drums.ride(decay=1.3, rng=rng)
    song.hits("ride", ride, lambda c: "x.x.x.x.x.x.x.x." if c.kind == "drop" and c.i >= 8 else None,
              gain_db=-21.0, pan=0.3)
    perc = [drums.conga(eh.key_hz(key, 210, 270, rng), "open", rng=rng), drums.bongo(eh.key_hz(key, 460, 560, rng), "slap", rng=rng)]
    song.hits("perc", perc, lambda c: ("...x......x..x.." if not c.phrase_end else "......x.x.xxx.xx")
              if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 24) else None,
              gain_db=-15.0, pan=-0.55, sends={"room": 0.15})
    snr = drums.snare(tone_hz=float(rng.uniform(190, 220)), snappy=0.8, decay=0.14, rng=rng)
    song.hits("snare_roll", snr, eh.snare_roll, gain_db=-12.0, sends={"reverb": 0.25}) \
        .automate("gain_db", eh.ramp_into(song, "drop", 4, -12.0, 0.0))

    # ================================================================ harmony
    prog = PROGRESSIONS[int(rng.integers(len(PROGRESSIONS)))]
    chords, prev = [], None
    for d in prog:
        tri = key.chord(d, 4, 3)
        ch = voice_lead(prev, tri, center=66)
        ch = sorted(ch) + [sorted(ch)[0] + 12]      # octave-doubled top: the classic piano-house voicing
        chords.append(ch)
        prev = ch[:3]
    root = eh.bass_root(key)

    def chord_of(c):
        return c.i % len(prog)

    def bass_note(deg_):
        n = key.degree(deg_, 1)
        while n < root - 2:
            n += 12
        while n > root + 14:
            n -= 12
        return n

    # ================================================================ bass
    riff = BASS_RIFFS[int(rng.integers(len(BASS_RIFFS)))]

    def bass_notes(c):
        if c.kind in ("intro", "breakdown") or c.bar >= bass_off:
            return []
        off = (c.i % 2) * 16  # riff is 2 bars; the chord changes every bar
        cd = prog[chord_of(c)]
        ev = [(s - off, l, bass_note(cd + st), v) for s, l, st, v in riff if off <= s < off + 16]
        if c.before("drop", 1) or c.before("breakdown", 1):
            ev = [e for e in ev if e[0] < 8]
        return ev

    if hands:
        b_inst = inst.bass_pluck(cutoff=float(rng.uniform(320, 420)), env_amt=float(rng.uniform(1600, 2400)),
                                 decay=float(rng.uniform(0.09, 0.13)), res=0.3, sub=0.8, drive=1.5, grit=0.35)
    else:
        b_inst = inst.organ_bass(drawbars=(1.0, 0.55, 0.25, 0.1))
    bass = song.notes("bass", b_inst, bass_notes, bus="bass", gain_db=-4.0, sidechain=0.5, sc_release_ms=140.0,
                      humanize=0.04)
    bass.automate("lp", [(groove, 600), (groove + 8, 2500), (drop1 - 1, 2500), (drop1, 8000),
                         (outro.start_bar, 8000), (bass_off, 600)])
    if root >= 38:
        sr_ = eh.sub_root(key)
        song.notes("sub", inst.sub_bass(harmonics=0.05), lambda c: eh.sub_events(bass_notes(c), root, sr_),
                   bus="bass", gain_db=-6.0, sidechain=0.55, sc_release_ms=140.0, humanize=0.0)
    song.notes("bd_sub", inst.sub_bass(), lambda c: [(0, 63.5, bass_note(prog[0]), 0.55)]
               if c.kind == "breakdown" and c.i % 4 == 0 and c.bars_left > 4 else [], bus="bass", gain_db=-15.0)

    # ================================================================ piano (the hook)
    p_riff = PIANO_RIFFS[int(rng.integers(len(PIANO_RIFFS)))]
    piano = eh.house_piano(bright=float(rng.uniform(0.7, 0.85)), hammer=0.6, bell=0.18, decay=0.9)

    def piano_notes(c):
        on = (c.kind == "drop" or c.kind == "breakdown"
              or (c.kind == "groove" and (not hands or c.i >= 8))
              or (c.kind == "outro" and c.i < 8))
        if not on:
            return []
        ch = chords[chord_of(c)]
        if c.kind == "breakdown" and c.i < 8 and c.section.bars >= 16:
            return [(0, 14, ch, 0.8)] if c.i % 2 == 0 else [(0, 6, ch, 0.7), (8, 6, ch, 0.75)]
        return [(s, l, ch, v) for s, l, v in p_riff]

    pl = song.notes("piano", piano, piano_notes, gain_db=-7.0, sidechain=0.35, sc_release_ms=150.0,
                    sends={"reverb": 0.18, "delay": 0.08}, humanize=0.05, hp=150.0,
                    fx=[lambda x: eq_peak(x, 3000.0, 2.0, 0.8)])
    pts = [(groove, 1500), (groove + 8, 6000)]
    for s in song.sections:
        if s.kind == "breakdown":
            pts += [(s.start_bar, 1200 if s.bars >= 16 else 3000), (s.end_bar - 0.01, 12000)]
        if s.kind == "drop":
            pts += [(s.start_bar, 12000)]
    pts += [(outro.start_bar, 9000), (outro.start_bar + 8, 1500)]
    pl.automate("lp", sorted(pts))

    # organ stabs
    org_r = ORGAN_RHYTHM[int(rng.integers(len(ORGAN_RHYTHM)))]
    organ = eh.house_organ(decay=0.22, sustain=0.3, click=0.35, perc=0.45)
    org_ch = [voice_lead(None, key.chord(d, 3, 4), center=62) for d in prog]
    song.notes("organ", organ, lambda c: [(s, l, org_ch[chord_of(c)], v) for s, l, v in org_r]
               if (c.kind == "drop" and (hands or c.i >= 16)) or (hands and c.kind == "groove" and c.i < 8) else [],
               gain_db=-11.0 if hands else -13.0, sidechain=0.45, hp=220.0, sends={"delay8": 0.12, "reverb": 0.12},
               fx=[eh.leslie(rate=6.0, mix=0.35)])

    # strings
    strings = eh.string_machine(attack=float(rng.uniform(0.3, 0.6)), release=1.2, cutoff=4200.0)
    st_ch = [voice_lead(None, key.chord(d, 4, 3), center=70) for d in prog]
    stl = song.notes("strings", strings, lambda c: [(0, 15.5, st_ch[chord_of(c)], 0.8)]
                     if c.kind in ("breakdown",) or (c.kind == "drop" and c.i >= (8 if hands else 16)) else [],
                     gain_db=-11.0, sidechain=0.3, sends={"hall": 0.3}, fx=[eh.ensemble(mix=0.7)], hp=250.0)
    for s in song.sections:
        if s.kind == "breakdown":
            stl.automate("gain_db", [(s.start_bar, -8.0), (s.end_bar - 0.01, 2.0), (s.end_bar, 0.0)])

    # vocal "oh / ah" chops
    deg = key.degree
    vph = VOX[int(rng.integers(len(VOX)))]
    vox = inst.vocal_chop(vowel="o", vowel_to="a", shift=float(rng.uniform(1.1, 1.2)), scoop=-2.0, breath=0.1)
    vcl = [(s, l, deg(d, 4), v) for s, l, d, v in vph]
    song.notes("vox", vox, lambda c: vcl if (c.kind == "drop" and c.i % 4 == 0 and (hands or c.i % 8 == 0))
               or (c.kind == "breakdown" and c.i % 8 == 4) else [], bus="vox", gain_db=-6.5 if hands else -8.0,
               sidechain=0.3, sends={"reverb": 0.25, "delay": 0.25}, hp=300.0)

    # ================================================================ fx & mix
    eh.transitions(song, rng, crash_db=-8.0, impact_db=-8.5, riser_db=-8.5, riser_kind="both")
    song.buses["drums"].eq = [("peak", 2800.0, 1.5, 0.8)]
    song.buses["music"].eq = [("peak", 350.0, -2.0, 0.8)]
    song.buses["drums"].width = 1.15
    song.master.lufs = -9.0

    k = plan["key"]
    if hands:
        song.description_he = (f"האוס קלאסי בסגנון שיקגו/ניו-יורק ב-{int(song.bpm)} BPM בסולם {k}: קיק 909 חזק, "
                               f"אופן-האט על האופביט וקלאפים על 2 ו-4, באס קופצני, סטאבים של פסנתר ואורגן ומהלך "
                               f"אקורדים של ידיים למעלה — עם ברייקדאון גדול ודרופ אופוריה.")
    else:
        song.description_he = (f"פסנתר-האוס שמח ב-{int(song.bpm)} BPM בסולם {k}: ריף פסנתר מתנגן על קיק 909, באס "
                               f"אורגן בסגנון M1, סטרינגס רחבים וברייקדאון ארוך שבו הפסנתר נפתח לאט עד לדרופ.")
    song.instruments = ["909 kick", "909 clap", "16th hats", "offbeat open hat", "shaker", "tambourine", "ride",
                        "conga/bongo", "bouncy octave bass" if hands else "M1-style organ bass",
                        "house piano stabs", "drawbar organ stabs (rotary)", "string machine", "vowel chops",
                        "riser, snare roll & impact"]
    song.mix_tips_he = (song.auto_mix_tips_he() + " הקיק נעלם לתיבה אחת לפני הדרופ — חתכו שם את הבאס של הטראק "
                        "היוצא ותנו לפסנתר להיכנס נקי.")
    return song
