"""Lo-fi hip-hop recipe (70–90 BPM): "beats to study to".

Brief
-----
* Dusty, lazily swung drums: soft round kick, a snare/rim that sits a few ms *behind* the beat
  (laid-back feel), 12-bit low-passed hats with heavy MPC swing (62–66) and timing jitter.
* Texture: vinyl crackle + hiss through the whole track and synthetic rain (louder in the intro,
  break and outro); everything tonal passes through a tape insert (wow & flutter + saturation).
* Music: jazzy FM Rhodes playing rootless maj9 / m9 / 9 voicings, rolled like a real player
  (a few ms between notes), mellow round bass locked to the kick with passing notes, a gentle
  breathy flute melody in the themes and a soft vibraphone answer in the break.
* Arrangement (64 bars ≈ 3 min at 84 BPM): Intro 8 (drums + crackle + rain only, no bass / no
  tonal content) · Verse 16 (Rhodes + bass in) · Theme 16 (melody) · Break 8 (kick out, filtered
  Rhodes, vibes) · Theme 2 8 · Outro 8 (drums + crackle only, mirrors the intro). −12 LUFS.
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from .. import ext_breadth as xb
from .. import ext_mainstream as xm
from ..arrangement import Song, clip
from ..dsp import F32
from ..theory import voice_lead
from . import register

TPL = [("Intro", "intro", 8, 2, 0), ("Verse", "verse", 16, 3, 0), ("Theme", "drop", 16, 4, 0),
       ("Break", "breakdown", 8, 2, 0), ("Theme 2", "drop", 8, 4, 0), ("Outro", "outro", 8, 2, 0)]

# chord qualities as intervals above the root (rootless voicings drop the 0 when ≥ 5 notes)
Q = {"maj9": [0, 4, 7, 11, 14], "m7": [0, 3, 7, 10], "m9": [0, 3, 7, 10, 14], "9": [0, 4, 7, 10, 14],
     "maj7": [0, 4, 7, 11], "6/9": [0, 4, 7, 9, 14]}
# progressions in a major key: (semitones above the tonic, quality), one chord per bar
PROGS = [
    [(0, "maj9"), (4, "m7"), (5, "maj9"), (7, "9")],      # Imaj9 – iii7 – IVmaj9 – V9
    [(5, "maj9"), (4, "m7"), (2, "m9"), (0, "maj9")],     # IVmaj9 – iii7 – ii9 – Imaj9 (lazy descent)
    [(0, "maj9"), (9, "m9"), (2, "m9"), (7, "9")],        # Imaj9 – vi9 – ii9 – V9
]
KICKS = [["x.........x.....", "x......x..x....."], ["x.........x..x..", "x.x.......x....."],
         ["x.......x.x.....", "x.........x....x"]]
HATS = ["x.g.x.gox.g.x.go", "x.gox.g.x.gox.g.", "x.o.x.gox.o.x.g."]
RIMS = ["..........g.....", "......g.......g.", "...g..........g."]
KEY_RHYTHMS = [[(0, 7, 0.8), (7, 3, 0.5), (10, 6, 0.65)], [(0, 12, 0.82), (12, 4, 0.5)],
               [(0, 3, 0.78), (3, 9, 0.6), (14, 2, 0.48)]]
MEL_RHYTHM = [(0.5, 3, 0.8), (4, 1.5, 0.6), (6, 4, 0.75), (11, 1.5, 0.55), (12.5, 3, 0.7),
              (20, 2, 0.65), (22, 2, 0.6), (24, 6, 0.75)]


NOTE_HE = {"C": "דו", "C#": "דו דיאז", "Db": "רה במול", "D": "רה", "D#": "רה דיאז", "Eb": "מי במול", "E": "מי",
           "F": "פה", "F#": "פה דיאז", "Gb": "סול במול", "G": "סול", "G#": "סול דיאז", "Ab": "לה במול", "A": "לה",
           "A#": "לה דיאז", "Bb": "סי במול", "B": "סי"}


def key_he(key_name: str) -> str:
    """'F major' → 'פה מז'ור'."""
    note, q = key_name.split()[0], key_name.split()[-1].lower()
    return f"{NOTE_HE.get(note, note)} {'מינור' if q == 'minor' else 'מז׳ור'}"


def _late(x, ms: float, sr: int = 44100):
    """Shift a one-shot later by ``ms`` (leading zeros): the 'lazy', behind-the-beat snare."""
    x = np.asarray(x, dtype=F32)
    pad = np.zeros((int(ms * 1e-3 * sr),) + x.shape[1:], dtype=F32)
    return np.concatenate([pad, x])


def _bass_range(m: int, lo: int = 29, hi: int = 40) -> int:
    while m < lo:
        m += 12
    while m > hi:
        m -= 12
    return m


@register("lofi")
def build(plan: dict, rng: np.random.Generator) -> Song:
    song = Song(plan, rng, swing=float(rng.choice([62.0, 64.0, 66.0])))
    key = song.key
    song.arrange(TPL, 64)
    verse, theme, brk, theme2, outro = (song.find("Verse"), song.find("Theme"), song.find("Break"),
                                        song.find("Theme 2"), song.find("Outro"))
    song.mix_in_bar = verse.start_bar

    def tonal(c):  # bass / keys / melody live between the intro and the outro
        return verse.start_bar <= c.bar < outro.start_bar

    # ---------------------------------------------------------------- drums (dusty, lazy)
    kick = xm.dusty(xm.boom_kick(float(rng.uniform(50.0, 55.0)), rng=rng), bits=12, lp_hz=5200.0)
    kp = KICKS[int(rng.integers(len(KICKS)))]

    def kick_pat(c):
        if c.kind == "breakdown":
            return "x..............." if c.i == 0 else None
        if c.next is not None and c.next.kind == "breakdown" and c.bars_left == 1:
            return kp[c.i % 2][:8] + "........"
        return kp[c.i % 2]

    song.hits("kick", kick, kick_pat, gain_db=-2.0, sc_source=True, humanize=0.04)
    lazy_ms = float(rng.uniform(16.0, 24.0))
    snare = [_late(xm.dusty(s, bits=11, lp_hz=9000.0), lazy_ms) for s in
             drums.variants(xm.boom_snare, 3, rng, jitter={"tone_hz": 0.03}, tone_hz=float(rng.uniform(185, 205)),
                            snappy=0.45, body=0.7, room=0.25)]

    def snare_pat(c):
        if c.kind == "breakdown":
            return "............x.gx" if c.bars_left == 1 else None
        if c.phrase_end and c.kind not in ("outro",):
            return "....x.......x.gx"
        return "....x.......x..."

    song.hits("snare", snare, snare_pat, gain_db=-3.0, sends={"room": 0.22, "reverb": 0.08}, humanize=0.08,
              timing_ms=4.0)
    rim = _late(xm.dusty(drums.rimshot(float(rng.uniform(1500, 1800)), rng=rng), bits=11, lp_hz=7000.0), lazy_ms)
    rp = RIMS[int(rng.integers(len(RIMS)))]
    song.hits("rim", rim, lambda c: "....x.......x..." if c.kind == "breakdown" else rp, gain_db=-14.0, pan=0.35,
              humanize=0.2, timing_ms=5.0, sends={"room": 0.2})
    hats = [xm.dusty(h, bits=11, lp_hz=11000.0) for h in
            drums.variants(drums.hat, 4, rng, jitter={"decay": 0.25}, decay=float(rng.uniform(0.03, 0.045)),
                           tone=float(rng.uniform(0.8, 0.95)))]
    hp_ = HATS[int(rng.integers(len(HATS)))]
    hl = song.hits("hats", hats, lambda c: "x.x.x.x.x.x.x.x." if c.kind == "breakdown" else hp_, gain_db=-10.0,
                   pan=0.3, humanize=0.22, timing_ms=6.0)
    hl.automate("lp", [(0, 2500), (4, 2500), (8, 16000)])  # "through the wall" opening over the intro
    shk = drums.variants(drums.shaker, 3, rng, length=0.09)
    song.hits("shaker", shk, lambda c: "..o...o...o...o." if c.kind == "drop" else None, gain_db=-20.0, pan=-0.5,
              humanize=0.25, timing_ms=6.0)
    song.custom("vinyl", xm.vinyl_crackle(song.seed, level=1.0, rate=18.0, pops=0.4), bus="fx", gain_db=-8.5) \
        .automate("gain_db", song.section_points({"intro": 1.5, "breakdown": 2.0, "outro": 1.5}, -1.0, ramp_bars=1))
    rain = song.custom("rain", xb.bar_texture(lambda b, n, r: xb.rain_bar(n, r, density=11.0, bed=0.12, drops=0.8),
                                              song.seed + 7), bus="fx", gain_db=-21.0, width=1.4)
    rain.automate("gain_db", song.section_points({"intro": 0.0, "verse": -4.0, "drop": -6.0, "breakdown": 1.0,
                                                  "outro": 0.0}, -4.0, ramp_bars=2))
    song.buses["fx"].hp = 300.0

    # ---------------------------------------------------------------- harmony
    prog = PROGS[int(rng.integers(len(PROGS)))]
    voicings, prev = [], None
    for semi, q in prog:
        ints = Q[q]
        ints = [i for i in ints if i] if len(ints) >= 5 else ints
        v = voice_lead(prev, [key.root(3) + semi + i for i in ints], center=key.root(4) - 1)
        voicings.append(v)
        prev = v
    roots = [_bass_range(key.root(1) + semi) for semi, _ in prog]
    tape = [xb.tape_wobble(depth_ms=1.1, rate=0.5, flutter_ms=0.06, flutter_rate=6.5),
            lambda x: fx.tape(x, 1.3, 0.5)]

    # ---------------------------------------------------------------- Rhodes (rolled 7th/9th chords)
    kr = KEY_RHYTHMS[int(rng.integers(len(KEY_RHYTHMS)))]
    roll = float(rng.uniform(0.07, 0.11))  # steps between rolled notes (~12–20 ms)

    def keys_notes(c):
        if not tonal(c):
            return []
        ch = voicings[c.i % 4]
        out = []
        for s, l, v in kr:
            for j, m in enumerate(sorted(ch)):
                out.append((s + j * roll, l - j * roll, m, round(v * (0.92 + 0.05 * (j % 2)), 2)))
        return out

    keys = song.notes("rhodes", xb.rhodes(bright=float(rng.uniform(0.55, 0.7)), tremolo=0.28, trem_rate=3.6,
                                           bark=0.3, release=0.5),
                      keys_notes, gain_db=-6.0, sends={"room": 0.2, "reverb": 0.14}, width=1.5, sidechain=0.1,
                      humanize=0.05, fx=list(tape))
    keys.automate("lp", [(verse.start_bar, 1400), (verse.start_bar + 4, 9000), (brk.start_bar - 0.01, 9000),
                         (brk.start_bar, 1500), (theme2.start_bar - 2, 1500), (theme2.start_bar, 9000)])

    # ---------------------------------------------------------------- mellow bass
    def bass_notes(c):
        if not tonal(c):
            return []
        r = roots[c.i % 4]
        if c.kind == "breakdown":
            return [(0, 30, r, 0.7)] if c.i % 2 == 0 else []
        steps = [i for i, ch in enumerate(kp[c.i % 2]) if ch != "."]
        ev = []
        for j, st in enumerate(steps):
            nxt = steps[j + 1] if j + 1 < len(steps) else 16
            ev.append((st, max(1.5, nxt - st - 0.6), r, 0.95 if st == 0 else 0.78))
        nr = roots[(c.i + 1) % 4]
        if c.i % 2 == 1 and nr != r and c.bars_left > 1:  # stepwise approach into the next chord
            app = key.quantize(nr + (2 if nr < r else -2))
            ev = [e for e in ev if e[0] < 13] + [(14, 1.6, _bass_range(app), 0.62)]
        return ev

    song.notes("bass", xb.soft_bass(tone=0.4, attack=0.01, release=0.14), bass_notes, bus="bass", gain_db=-4.5,
               sidechain=0.2, sc_release_ms=120.0, humanize=0.05, fx=[lambda x: fx.tape(x, 1.2, 0.4)])

    # ---------------------------------------------------------------- gentle melody
    chords8 = voicings + voicings
    lo, hi = key.root(5) - 3, key.root(6)
    motif = xm.make_melody(rng, key, chords8, MEL_RHYTHM, lo, hi, phrase_bars=2)
    # breathe: the 2nd and 4th phrase keep only their first half (call → space)
    motif = [e for e in motif if not (int(e[0] // 32) % 2 == 1 and e[0] % 32 >= 16)]
    mclip = clip(motif, 8)
    song.notes("flute", xb.flute(breath=0.2, vibrato=0.16), lambda c: mclip(c) if c.kind == "drop" else [],
               gain_db=-7.5, pan=0.15, sends={"reverb": 0.25, "delay": 0.14}, fx=list(tape))
    song.notes("vibes", inst.mallet("vibes"),
               lambda c: [(s, l, m - 12, v * 0.75) for s, l, m, v in mclip(c)] if c.kind == "breakdown" and c.i < 6
               else [], gain_db=-12.0, pan=-0.25, sends={"reverb": 0.3, "delay": 0.2}, fx=list(tape))

    # ---------------------------------------------------------------- small fx
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.15})
    bar = song.grid.bar_sec
    fxl.add(fx.reverse_cymbal(bar * 0.5, rng=rng), theme.start_bar, align="end", gain_db=-18.0)
    fxl.add(fx.reverse_cymbal(bar * 0.5, rng=rng), theme2.start_bar, align="end", gain_db=-18.0)

    # ---------------------------------------------------------------- mix
    song.buses["drums"].comp = dict(threshold_db=-14.0, ratio=2.5, attack_ms=12.0, release_ms=110.0, makeup_db=1.0)
    song.buses["drums"].sat = 0.3
    song.buses["drums"].eq = [("peak", 120.0, 1.0, 1.0)]
    song.buses["music"].eq = [("peak", 380.0, -3.0, 0.8), ("peak", 2000.0, 3.0, 0.6)]
    song.buses["bass"].eq = [("lowshelf", 70.0, 1.0, 0.7)]
    song.returns["room"].width = 1.4
    song.master.lufs = -12.0
    song.master.high_shelf_db = 0.0

    flats = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
    prog_txt = " – ".join(flats[(key.root_pc + s) % 12] + q for s, q in prog)
    sw = int(song.swing)
    bpm = int(round(song.bpm))
    song.instruments = ["dusty swung drums (12-bit, laid-back snare)", "vinyl crackle", "rain", "FM Rhodes (rolled 9th "
                        "chords, tape wow & flutter)", "mellow round bass", "breathy flute melody", "vibraphone"]
    song.description_he = (
        f"לו-פיי היפ-הופ רגוע ב-{bpm} BPM ב{key_he(plan['key'])} ({plan['camelot']}) — אחר צהריים גשום באולפן. "
        f"תופים מאובקים בסווינג עצל של {sw}%, עם סנר שיושב קצת מאחורי הביט, קראקל של ויניל וגשם ברקע. "
        f"פסנתר רודס מנגן אקורדים ג'אזיים ({prog_txt}) בפריטה רכה, עם 'רעידת' טייפ (Wow & Flutter) עדינה, "
        f"באס עגול ורך ומלודיית חליל נושמת. בברייק הקיק יוצא, הרודס מתעמעם וויברפון רך עונה למלודיה.")
    song.mix_tips_he = (
        f"טיפ ערבוב: אינטרו של {verse.start_bar} תיבות תופים, קראקל וגשם בלבד — בלי באס ובלי אקורדים. הרודס והבאס "
        f"נכנסים בתיבה {verse.start_bar + 1} (Hot Cue B), המלודיה בתיבה {theme.start_bar + 1} (Hot Cue D), "
        f"הברייק בלי קיק בתיבה {brk.start_bar + 1} (Hot Cue C), והאאוטרו מתיבה {outro.start_bar + 1} (Hot Cue G) "
        f"חוזר לתופים בלבד — 8 תיבות נקיות למיקס החוצה. בגלל הסווינג הכבד, עשו Beatmatching לפי הקיק והסנר ולא "
        f"לפי ההיי-האטים. {xm.wheel_he(plan['camelot'])} "
        + (xm.partners_he(plan) + "." if xm.partners_he(plan) else
           "טראק מושלם לפתיחת ערב או לרגע נשימה, ולמעבר להיפ-הופ ב-85–95 BPM."))
    return song
