"""Psytrance recipe (136–148 BPM): full-on (default) and progressive psy (plan ``genre`` contains
"Progressive").

* Short punchy kick that ends before the next 16th + rolling **KBBB** bassline (three 16th bass notes
  after every kick), gated by its own short envelope and side-chained to the kick.
* Squelchy acid (TB-style MonoSynth with slides/accents), filter-swept 1/16 FM sequences, FM lead
  phrases, twisted FX (zaps, pitch dives, laser ups), a synthesised spoken-word-like vowel texture
  (gibberish syllables, no real words), dark pads.
* Full-on: tension build every 16 bars (acid cutoff ramp, noise riser, snare 8ths, bass/kick cut on
  the last beat, crash on the next "one"). Progressive: deeper/darker, organic hypnotic percussion
  (congas, bongos, shaker, toms), FM bell sequence, longer filter journeys.
* Arrangement in 16-bar phrases; 32-bar DJ intro (drums only for 16 bars, bass enters on bar 17) and a
  mirrored 32-bar outro (last 16 bars drums only).
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from .. import ext_breadth as xb
from ..arrangement import Song, clip, euclid
from ..theory import voice_lead
from . import register

FULLON = [("Intro", "intro", 32, 6, 0), ("Groove", "groove", 16, 8, 1), ("Breakdown", "breakdown", 16, 6, 0),
          ("Drop", "drop", 32, 9, 2), ("Breakdown 2", "breakdown", 16, 7, 0), ("Drop 2", "drop", 16, 10, 1),
          ("Outro", "outro", 32, 6, 0)]
PROG = [("Intro", "intro", 32, 5, 0), ("Groove", "groove", 32, 7, 1), ("Breakdown", "breakdown", 16, 5, 0),
        ("Drop", "drop", 48, 8, 2), ("Outro", "outro", 32, 5, 0)]

FOUR = "x...x...x...x..."
# turnaround cells: the 3 sixteenths after a kick, semitone offsets from the bass root (None = rest)
CELLS_FULLON = [[0, 0, 12], [0, 12, 0], [0, 0, -2], [3, 3, 3], [7, 7, 7], [0, 12, 10], [10, 10, 10],
                [5, 5, 3], [12, 12, 7], [0, 3, 0]]
CELLS_PROG = [[0, None, 0], [0, 0, 12], [None, 0, 0], [3, 3, 0], [-2, -2, 0], [7, 7, 5], [0, 12, 0]]


def make_riff(rng, prog: bool):
    """4-bar riff = 16 beats × 3 sixteenths (offsets from the root)."""
    base = [0, 0, 0]
    riff = [list(base) for _ in range(16)]
    cells = CELLS_PROG if prog else CELLS_FULLON
    pick = lambda: list(cells[int(rng.integers(len(cells)))])  # noqa: E731
    if prog:
        gallop = [0, None, 0] if rng.random() < 0.5 else [None, 0, 0]
        for b in (3, 7, 11):
            if rng.random() < 0.5:
                riff[b] = list(gallop)
        riff[14], riff[15] = pick(), pick()
    else:
        riff[7] = pick()
        riff[14], riff[15] = pick(), pick()
        if rng.random() < 0.5:
            riff[11] = [0, 0, 12]
    return riff


def acid_seq(rng, root, steps=32, prog=False):
    pool = [0, 0, 0, 12, 3, 7, 10, 12, 15, -2] if not prog else [0, 0, 0, 12, 3, 7, -2, 5]
    ev = []
    dens = rng.uniform(0.55, 0.75) if not prog else rng.uniform(0.4, 0.55)
    for s in range(steps):
        if s % 4 == 0 or rng.random() < dens:
            o = int(rng.choice(pool))
            fl = ""
            if rng.random() < 0.25:
                fl += "s"
            if s % 8 == 0 or rng.random() < 0.3:
                fl += "a"
            ev.append((s, 0.55 if "s" not in fl else 1.0, root + o, 0.9, fl))
    return ev


def fm_pattern(rng, key, octave=4, prog=False):
    k = int(rng.integers(9, 13)) if not prog else int(rng.integers(5, 8))
    rhythm = euclid(k, 16, int(rng.integers(0, 4)))
    degs = [0, 0, 2, 4, 6, 7, 3, 4] if not prog else [0, 0, 4, 2, 7, 6]
    out = []
    for s, ch in enumerate(rhythm):
        if ch != ".":
            d = int(rng.choice(degs))
            out.append((s, 0.6, key.degree(d, octave), 0.7 + 0.3 * (s % 4 == 0)))
    return out


LEAD_PHRASES = [  # 4 bars (64 steps): (step, len, degree) — Goa-style 16th runs ending on chord tones
    [(0, 2, 7), (2, 1, 6), (3, 1, 4), (4, 2, 6), (6, 2, 4), (8, 1, 2), (9, 1, 4), (10, 2, 3), (12, 4, 2),
     (16, 2, 4), (18, 1, 3), (19, 1, 2), (20, 2, 3), (22, 2, 1), (24, 2, 0), (26, 2, 2), (28, 4, 4),
     (32, 2, 7), (34, 1, 6), (35, 1, 4), (36, 2, 6), (38, 2, 7), (40, 2, 9), (42, 2, 7), (44, 4, 6),
     (48, 2, 4), (50, 2, 3), (52, 2, 2), (54, 2, 1), (56, 4, 0), (60, 4, -1)],
    [(0, 3, 4), (3, 1, 2), (4, 2, 4), (6, 2, 5), (8, 3, 4), (11, 1, 2), (12, 4, 0), (16, 3, 4), (19, 1, 2),
     (20, 2, 4), (22, 2, 7), (24, 4, 6), (28, 4, 4), (32, 3, 4), (35, 1, 2), (36, 2, 4), (38, 2, 5),
     (40, 3, 7), (43, 1, 5), (44, 4, 4), (48, 2, 2), (50, 2, 4), (52, 2, 2), (54, 2, 0), (56, 8, -1)],
]


@register("psytrance")
def build(plan: dict, rng: np.random.Generator) -> Song:
    prog = "progressive" in str(plan.get("genre", "")).lower()
    song = Song(plan, rng, swing=50.0)
    key = song.key
    total = song.target_bars(16)
    song.arrange(PROG if prog else FULLON, total)
    intro, outro = song.find("intro"), song.find("outro")
    bass_in = 16
    song.mix_in_bar = bass_in
    bass_off = outro.start_bar + outro.bars - 16
    step = song.grid.step_sec
    secs = song.sections

    root = xb.note_in_range(key.root_pc, 41.0)          # F#1 46 Hz, D2 73 Hz …
    k_hz = xb.kick_tune(key, 44.0, 62.0)

    # ---------------------------------------------------------------- tension structure (16-bar blocks)
    def block_end(c):
        """Last bar of a 16-bar block inside groove/drop (full-on tension moment)."""
        return c.kind in ("groove", "drop") and c.i % 16 == 15

    # ---------------------------------------------------------------- kick
    kick = xb.psy_kick(k_hz, length=step * (0.98 if prog else 0.94), click=float(rng.uniform(0.5, 0.75)),
                       drive=float(rng.uniform(2.0, 2.8)) if not prog else 1.8,
                       knock=float(rng.uniform(0.8, 1.2)), rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown":
            if not prog and c.name == "Breakdown 2" and 8 <= c.i and c.bars_left > 1:
                return FOUR
            return None
        if block_end(c) and not prog:
            return "x...x...x......."  # tension: kick out on the last beat of every 16-bar block
        return FOUR

    song.hits("kick", kick, kick_pat, gain_db=-1.5, sc_source=True, humanize=0.0)

    # ---------------------------------------------------------------- rolling bass (KBBB)
    riff = make_riff(rng, prog)
    gate = 0.9 if prog else 0.74
    vels = (0.84, 0.9, 1.0) if not prog else (0.8, 0.88, 0.96)
    bass_i = xb.psy_bass(cutoff=float(rng.uniform(150, 200)) if not prog else float(rng.uniform(110, 140)),
                         env_amt=float(rng.uniform(2200, 3000)) if not prog else float(rng.uniform(1100, 1500)),
                         decay=float(rng.uniform(0.04, 0.055)) if not prog else float(rng.uniform(0.06, 0.08)),
                         res=float(rng.uniform(0.3, 0.42)), drive=2.2 if not prog else 1.7,
                         sub=0.45 if not prog else 0.6, sustain=0.45 if not prog else 0.6,
                         pulse=0.25 if not prog else 0.1)

    def bass_on(c):
        if c.kind == "intro":
            return c.i >= bass_in
        if c.kind == "outro":
            return c.bar < bass_off
        if c.kind == "breakdown":
            return not prog and c.name == "Breakdown 2" and 8 <= c.i and c.bars_left > 1
        return True

    def bass_notes(c):
        if not bass_on(c):
            return []
        bar4 = c.i % 4
        out = []
        for beat in range(4):
            cell = riff[bar4 * 4 + beat]
            for j in range(3):
                if cell[j] is None:
                    continue
                out.append((beat * 4 + 1 + j, gate, root + cell[j], vels[j]))
        if (block_end(c) and not prog) or c.before("breakdown", 1) or c.before("drop", 1):
            out = [e for e in out if e[0] < 12]
        return out

    bass = song.notes("bass", bass_i, bass_notes, bus="bass", gain_db=-3.5, sidechain=0.9,
                      sc_release_ms=step * 1000 * 0.7, humanize=0.03)
    pts = [(bass_in, 260.0), (bass_in + 8, 900.0), (intro.end_bar - 0.01, 3000.0), (intro.end_bar, 9000.0)]
    for s in secs:
        if s.kind == "breakdown" and s.name == "Breakdown 2":
            pts += [(s.start_bar + 8, 400.0), (s.end_bar - 0.01, 3500.0), (s.end_bar, 9000.0)]
    pts += [(outro.start_bar, 9000.0), (outro.start_bar + 8, 2500.0), (bass_off, 350.0)]
    bass.automate("lp", pts)

    # ---------------------------------------------------------------- hats & percussion
    ch = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.15}, decay=float(rng.uniform(0.025, 0.04)),
                        tone=float(rng.uniform(1.1, 1.35)))
    ch_p = ["gxgxgxgxgxgxgxgx", "x.xgx.xgx.xgx.xg", "gxxggxxggxxggxxg"][int(rng.integers(3))]

    def ch_pat(c):
        if c.kind == "breakdown" and not (c.name == "Breakdown 2" and c.i >= 8):
            return None if c.bars_left > 2 else "gxgxgxgxgxgxgxgx"
        return ch_p

    song.hits("hats", ch, ch_pat, gain_db=-12.5, pan=0.4, humanize=0.12, sends={"delay8": 0.05})
    oh = drums.hat(open_=True, decay=float(rng.uniform(0.09, 0.13)), tone=float(rng.uniform(1.0, 1.2)), rng=rng)

    def oh_pat(c):
        if c.kind == "breakdown":
            return None
        if c.kind == "intro" and c.i < 8:
            return None
        if c.kind == "outro" and c.bars_left <= 8:
            return None
        return "..x...x...x...x."

    song.hits("open_hat", oh, oh_pat, gain_db=-10.5, pan=-0.25, sends={"room": 0.12})
    clap = drums.variants(drums.clap, 3, rng, jitter={"tone_hz": 0.05}, tone_hz=float(rng.uniform(1300, 1700)),
                          tail=float(rng.uniform(0.1, 0.15)))

    def clap_pat(c):
        if c.kind == "breakdown" or (c.kind == "intro" and c.i < (16 if not prog else 8)):
            return None
        if c.kind == "outro" and c.bars_left <= 8:
            return None
        return "....x.......x..." if not (block_end(c) and not prog) else "....x.......x.x."

    song.hits("clap", clap, clap_pat, gain_db=-9.0 if not prog else -10.5, sends={"reverb": 0.18, "room": 0.1})
    ride = drums.ride(decay=0.8, rng=rng)
    song.hits("ride", ride, lambda c: "..x...x...x...x." if c.kind == "drop" else None, gain_db=-17.0, pan=0.3)

    snr = drums.snare(tone_hz=float(rng.uniform(190, 230)), snappy=0.85, decay=0.11, rng=rng)

    def snare_build(c):
        if c.kind == "breakdown" and c.bars_left <= 4 and c.section.bars >= 8 and c.next and c.next.kind == "drop":
            return ["x.x.x.x.x.x.x.x.", "x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx",
                    "rrrrrrrrrrrrrrrr"][4 - c.bars_left]
        if block_end(c) and not prog:
            return "........x.x.xxxx"
        if c.kind in ("groove", "drop") and c.i % 16 == 14 and not prog:
            return "..............x."
        return None

    sb_pts = [(0, -4.0)]
    for s in song.sections:
        if s.kind == "drop":
            sb_pts += [(s.start_bar - 4, -10.0), (s.start_bar - 1e-3, 0.0), (s.start_bar, -4.0)]
    song.hits("snare_build", snr, snare_build, gain_db=-13.0, sends={"reverb": 0.25}).automate("gain_db", sb_pts)

    if prog:
        # organic, hypnotic percussion
        cong = [drums.conga(float(rng.uniform(180, 220)), "open", rng=rng),
                drums.conga(float(rng.uniform(260, 300)), "mute", rng=rng),
                drums.conga(float(rng.uniform(300, 340)), "slap", rng=rng)]
        cp = ["..x..x....x.x...", ".x...x..x.....x.", "...x..x...x..x.."][int(rng.integers(3))]
        song.hits("congas", cong, lambda c: cp if c.kind != "breakdown" and not (c.kind == "intro" and c.i < 8)
                  and not (c.kind == "outro" and c.bars_left <= 8) else None,
                  gain_db=-15.0, pan=-0.45, humanize=0.15, timing_ms=3.0, sends={"room": 0.2})
        bong = [drums.bongo(float(rng.uniform(480, 560)), "open", rng=rng),
                drums.bongo(float(rng.uniform(620, 700)), "slap", rng=rng)]
        bp_ = euclid(int(rng.integers(5, 8)), 16, int(rng.integers(1, 4)))
        song.hits("bongos", bong, lambda c: bp_ if c.kind in ("groove", "drop") else None,
                  gain_db=-17.0, pan=0.5, humanize=0.2, timing_ms=3.0, sends={"delay": 0.12})
        shk = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=0.07)
        song.hits("shaker", shk, lambda c: "gogxgogxgogxgogx" if c.kind != "breakdown" and not (c.kind == "intro" and c.i < 4)
                  else None, gain_db=-18.0, pan=0.55, humanize=0.2, timing_ms=2.0)
        tom = [drums.tom(float(rng.uniform(85, 105)), 0.35, rng=rng), drums.tom(float(rng.uniform(120, 150)), 0.3, rng=rng)]
        song.hits("toms", tom, lambda c: "..........x..x.x" if c.phrase_end and c.kind in ("groove", "drop", "intro")
                  and c.i % 16 == 15 else None, gain_db=-12.0, sends={"reverb": 0.2})
    else:
        blips = [drums.perc_blip(float(rng.uniform(900, 1400)), 0.03, fm_index=3.0, ratio=1.41, rng=rng),
                 drums.perc_blip(float(rng.uniform(1600, 2200)), 0.02, fm_index=2.0, ratio=2.3, rng=rng)]
        pp = euclid(int(rng.integers(4, 7)), 16, int(rng.integers(1, 5)))
        song.hits("perc", blips, lambda c: pp if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 8)
                  else None, gain_db=-16.0, pan=0.5, sends={"delay8": 0.18})
        shk = drums.variants(drums.shaker, 3, rng, jitter={"length": 0.2}, length=0.05)
        song.hits("shaker", shk, lambda c: "..x...x...x...x." if c.kind in ("drop",) else None,
                  gain_db=-19.0, pan=-0.5)

    # ---------------------------------------------------------------- acid (squelch)
    acid_ev = acid_seq(rng, key.root(3) if not prog else key.root(2) + 12, 32, prog)
    acid_syn = inst.MonoSynth(wave="saw" if not prog else "square", cutoff=400.0,
                              res=float(rng.uniform(0.78, 0.88)) if not prog else 0.7,
                              env_mod=float(rng.uniform(2.2, 3.0)) if not prog else 1.6,
                              decay=float(rng.uniform(0.1, 0.16)), glide_ms=55.0, drive=2.4, dist=0.3 if not prog else 0.15)
    acid_clip = clip(acid_ev, 2)

    def acid_notes(c):
        if c.kind == "groove" and c.i >= (0 if not prog else 16):
            return acid_clip(c)
        if c.kind == "breakdown" and c.i >= c.section.bars // 2:
            return acid_clip(c)
        if c.kind == "drop":
            return acid_clip(c)
        if c.kind == "intro" and c.i >= 24 and not prog:
            return acid_clip(c)
        return []

    acid = song.line("acid", acid_syn, acid_notes, bus="music", gain_db=-8.0 if not prog else -10.0,
                     sidechain=0.45, sends={"delay": 0.24, "reverb": 0.1}, hp=200.0, pan=-0.15, width=1.3)
    apts = []
    for s in secs:
        if s.kind in ("groove", "drop"):
            for b in range(s.start_bar, s.end_bar, 16):
                hi = 3800.0 if not prog else 1800.0
                apts += [(b, 650.0 if not prog else 350.0), (b + 12, 1400.0 if not prog else 800.0),
                         (min(b + 16, s.end_bar) - 0.01, hi)]
        elif s.kind == "breakdown":
            apts += [(s.start_bar + s.bars // 2, 300.0), (s.end_bar - 0.01, 3500.0 if not prog else 2000.0)]
        elif s.kind == "intro":
            apts += [(24, 250.0), (s.end_bar - 0.01, 700.0)]
    acid.automate("cutoff", apts)

    # ---------------------------------------------------------------- filter-swept 1/16 FM sequence
    fm_ev = fm_pattern(rng, key, 4, prog)
    fm_i = xb.fm_seq(ratio=float(rng.choice([2.0, 3.0, 1.5])) if not prog else 1.0,
                     index=float(rng.uniform(4.0, 6.5)) if not prog else 2.0,
                     idx_decay=float(rng.uniform(0.04, 0.07)), decay=0.1 if not prog else 0.25,
                     feedback=0.4 if not prog else 0.1, cutoff=7000.0 if not prog else 4000.0)

    def fm_notes(c):
        if c.kind == "drop" or (c.kind == "groove" and c.i >= c.section.bars - 8):
            return fm_ev
        if c.kind == "intro" and c.i >= 16 and prog:
            return fm_ev
        if c.kind == "outro" and c.i < 16:
            return fm_ev
        return []

    fm_l = song.notes("fm_seq", fm_i, fm_notes, gain_db=-9.5 if not prog else -12.0, sidechain=0.4,
                      sends={"delay": 0.22 if not prog else 0.3, "hall": 0.06}, pan=0.25, width=1.6)
    fpts = []
    for s in secs:
        if s.kind in ("groove", "drop"):
            for b in range(s.start_bar, s.end_bar, 16):
                fpts += [(b, 500.0), (min(b + 16, s.end_bar) - 0.01, 9000.0 if not prog else 5000.0)]
        elif s.kind == "intro":
            fpts += [(16, 300.0), (s.end_bar - 0.01, 2500.0)]
        elif s.kind == "outro":
            fpts += [(s.start_bar, 5000.0), (s.start_bar + 16, 400.0)]
    fm_l.automate("lp", fpts)

    # ---------------------------------------------------------------- leads
    if not prog:
        phrase = LEAD_PHRASES[int(rng.integers(len(LEAD_PHRASES)))]
        lead_ev = [(s, l * 0.9, key.degree(d, 5), 0.9, "a" if s % 8 == 0 else ("s" if l <= 1 else ""))
                   for s, l, d in phrase]
        lead_syn = inst.MonoSynth(wave="square", cutoff=900.0, res=0.6, env_mod=2.0, decay=0.14, glide_ms=35.0,
                                  drive=1.8, dist=0.2)
        lclip = clip(lead_ev, 4)
        lead = song.line("lead", lead_syn, lambda c: lclip(c) if (c.kind == "drop" and (c.name == "Drop 2" or c.i >= 16))
                         else [], bus="music", gain_db=-15.0, sidechain=0.4,
                         sends={"delay": 0.3, "reverb": 0.15}, hp=300.0, pan=0.12, width=1.3)
        lead.automate("cutoff", [(0, 1200.0)] + [(s.start_bar, 900.0) for s in secs if s.kind == "drop"]
                      + [(s.end_bar - 0.01, 3000.0) for s in secs if s.kind == "drop"])
    else:
        # hypnotic FM bell sequence (dotted delays)
        bell_ev = []
        degs = [0, 4, 7, 2, 4, 0, 6, 4]
        r = euclid(5, 16, int(rng.integers(0, 3)))
        j = 0
        for s, chh in enumerate(r):
            if chh != ".":
                bell_ev.append((s, 1, key.degree(degs[j % len(degs)], 5), 0.8))
                j += 1
        bell = inst.bell(ratio=3.5, index=2.0, decay=0.6)
        song.notes("bells", bell, lambda c: bell_ev if c.kind in ("breakdown", "drop") or (c.kind == "groove" and c.i >= 16)
                   else [], gain_db=-15.0, sidechain=0.3, sends={"delay": 0.4, "hall": 0.25}, pan=-0.2, width=1.5)

    # ---------------------------------------------------------------- pads (breakdowns, prog drops)
    prog_degs = [[0, 5, 6, 0], [0, 3, 5, 4], [0, 5, 3, 6]][int(rng.integers(3))]
    chords, prev = [], None
    for dg in prog_degs:
        chh = voice_lead(prev, key.chord(dg, 3, 3), center=key.root(4) - 3)
        chords.append(chh)
        prev = chh
    pad_i = inst.pad(attack=1.0, cutoff=1300.0 if not prog else 900.0, detune=0.3, warmth=0.6)

    def pad_notes(c):
        if c.kind == "breakdown" and c.i % 4 == 0:
            return [(0, 63.5, chords[(c.i // 4) % 4], 0.75)]
        if c.kind == "drop" and c.i >= (16 if prog else 0) and c.i % 4 == 0:
            return [(0, 63.5, chords[(c.i // 4) % 4], 0.5)]
        return []

    pad = song.notes("pad", pad_i, pad_notes, gain_db=-12.0, sends={"hall": 0.35}, width=1.8, sidechain=0.6,
                     hp=250.0)
    for s in secs:
        if s.kind == "breakdown":
            pad.automate("lp", [(s.start_bar, 500.0), (s.end_bar, 4000.0)])

    # ---------------------------------------------------------------- spoken-word-like vowel texture
    vox = song.audio("speech", bus="vox", sends={"delay": 0.3, "reverb": 0.25})
    bar_sec = song.grid.bar_sec
    vf0 = 98.0 if not prog else 82.0
    vshift = 1.0 if not prog else 0.9
    for s in secs:
        if s.kind == "breakdown":
            vox.add(xb.speechy(bar_sec * 7.5, rng, f0=vf0, shift=vshift, rate=1.0), s.start_bar + 0.5, gain_db=-1.0)
        if s.kind == "drop" and s.bars >= 32:
            vox.add(xb.speechy(bar_sec * 3.5, rng, f0=vf0, shift=vshift, density=0.6), s.start_bar + 24, gain_db=-4.0)
    vox.add(xb.speechy(bar_sec * 3.5, rng, f0=vf0, shift=vshift, density=0.7), 24, gain_db=-3.0)
    vox.gain_db = -9.0
    vox.automate("lp", [(0, 5000.0)])

    # ---------------------------------------------------------------- FX: zaps, dives, lasers, risers
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.12, "delay": 0.1})
    crash = drums.crash(decay=2.2, rng=rng)
    impact = fx.impact(2.5, rng=rng)
    zaps = [xb.zap(float(rng.uniform(0.12, 0.25)), float(rng.uniform(3000, 7000)), float(rng.uniform(50, 120)),
                   float(rng.uniform(1.5, 4.0))) for _ in range(4)]
    for s in secs:
        if s.kind in ("groove", "drop", "outro") or (s.kind == "breakdown" and s.name == "Breakdown 2"):
            fxl.add(crash, s.start_bar, gain_db=-9.0)
        if s.kind == "drop":
            fxl.add(impact, s.start_bar, gain_db=-8.0)
        if s.kind in ("groove", "drop"):
            for b in range(s.start_bar + 16, s.end_bar, 16):
                fxl.add(crash, b, gain_db=-11.0)
            for b in range(s.start_bar, s.end_bar, 16):
                end = min(b + 16, s.end_bar)
                if not prog:
                    fxl.add(fx.riser(bar_sec * 4, "noise", f_lo=400, f_hi=9000, rng=rng), end, align="end", gain_db=-14.0)
                    fxl.add(xb.laser_up(bar_sec / 4 * 3, 300.0, float(rng.uniform(5000, 8000))), end, align="end", gain_db=-15.0)
                else:
                    fxl.add(fx.noise_sweep(bar_sec * 8, up=True, rng=rng), end, align="end", gain_db=-19.0)
            # zaps on off-beats (twisted FX)
            for b in range(s.start_bar, s.end_bar):
                rr = np.random.default_rng(song.seed * 31 + b)
                if rr.random() < (0.45 if not prog else 0.2):
                    beat = float(rr.choice([1.5, 2.75, 3.5, 3.75]))
                    fxl.add(zaps[int(rr.integers(len(zaps)))], b, beat, gain_db=-15.0 if not prog else -18.0)
        if s.kind == "breakdown":
            fxl.add(xb.pitch_dive(bar_sec * 2, float(rng.uniform(1500, 2500)), 40.0, rng=rng), s.start_bar,
                    gain_db=-11.0)
            fxl.add(fx.downlifter(bar_sec * 2, rng=rng), s.start_bar, gain_db=-13.0)
            nb = min(8, s.bars)
            fxl.add(fx.riser(bar_sec * nb, "both", f_lo=300, f_hi=11000, rng=rng), s.end_bar, align="end", gain_db=-9.0)
            fxl.add(fx.reverse_cymbal(bar_sec, rng=rng), s.end_bar, align="end", gain_db=-11.0)
            if not prog:
                fxl.add(xb.laser_up(bar_sec, 150.0, 9000.0), s.end_bar, align="end", gain_db=-12.0)
    fxl.add(fx.noise_sweep(bar_sec * 8, up=True, rng=rng), bass_in, align="end", gain_db=-17.0)
    fxl.add(fx.reverse_cymbal(bar_sec, rng=rng), intro.end_bar, align="end", gain_db=-11.0)
    # pitch dives into each tension block end (full-on)
    if not prog:
        for s in secs:
            if s.kind in ("groove", "drop"):
                for b in range(s.start_bar + 15, s.end_bar, 16):
                    fxl.add(xb.pitch_dive(bar_sec * 0.25, 2500.0, 80.0, rng=rng), b, 3.0, gain_db=-14.0)

    # ---------------------------------------------------------------- mix
    song.buses["drums"].eq = [("peak", 3200.0, 1.5, 0.8), ("peak", 120.0, 1.0, 1.0)]
    song.buses["drums"].width = 1.3
    song.buses["music"].width = 1.4
    song.buses["music"].eq = [("peak", 2200.0, 2.0, 0.7)]
    song.returns["delay"].beats = 0.75
    song.returns["reverb"].width = 1.5
    song.returns["delay"].width = 1.5
    song.returns["hall"].width = 1.5
    song.master.lufs = -9.0

    style = "פרוגרסיב פסיי" if prog else "פסיטרנס פול-און"
    if prog:
        song.description_he = (
            f"{style} ב-{int(song.bpm)} BPM בסולם {plan['key']}: עמוק, כהה והיפנוטי. קיק קצר ומדויק, בס מתגלגל "
            f"(שלוש 16-יות אחרי כל קיק) עם גלופ קטן, כלי הקשה אורגניים (קונגות, בונגו, שייקר וטומים), סיקוונס "
            f"פעמונים ב-FM עם דיליי, אסיד מעוגל ופילטרים שנפתחים לאט — ומרקם קולי שנשמע כמו קטע דיבור "
            f"(סינתטי לגמרי, בלי מילים אמיתיות). מעולה לבניית מתח לפני הפיק.")
    else:
        song.description_he = (
            f"{style} ב-{int(song.bpm)} BPM בסולם {plan['key']}: קיק קצר ופאנצ'י בלי חפיפה, בס מתגלגל של שלוש "
            f"16-יות אחרי כל קיק, אסיד סקוואלשי, סיקוונסים של FM עם פילטר שנפתח, זאפים, צלילות פיץ' ולייזרים — "
            f"ומרקם קולי שנשמע כמו קטע דיבור (סינתטי לגמרי, בלי מילים). המתח נבנה מחדש כל 16 תיבות. טראק פיק.")
    song.instruments = (["short punchy psy kick", "rolling KBBB bass", "squelchy acid", "filter-swept FM 1/16 sequence",
                         "FM bell sequence" if prog else "Goa-style square lead", "spoken-word-like vowel texture",
                         "dark pad", "zaps & pitch dives", "open hats & ride"]
                        + (["congas, bongos, shaker, toms"] if prog else ["FM percussion"]))
    song.mix_tips_he = _tips(song, plan, prog)
    return song


def _tips(song, plan, prog):
    from ..theory import compatible_keys
    cam = plan["camelot"]
    neigh = [k for k in compatible_keys(cam)[1:4]]
    bd = song.find("breakdown")
    dr = song.find("drop")
    out = song.find("outro")
    parts = [f"טיפ ערבוב: 16 התיבות הראשונות הן קיק והיי-האטים בלבד, והבאס המתגלגל נכנס בתיבה {song.mix_in_bar + 1} "
             f"(Hot Cue B) — זה הרגע להחליף באסים: בפסיטרנס אסור ששני באסים יתנגשו, אז חתכו את ה-Low בטראק הנכנס עד הסוויץ'"]
    parts.append(f"ברייקדאון בתיבה {bd.start_bar + 1} ודרופ בתיבה {dr.start_bar + 1}")
    bd2 = song.find("breakdown", 1)
    if bd2:
        parts.append(f"ברייקדאון שני בתיבה {bd2.start_bar + 1}")
    parts.append(f"האאוטרו מתחיל בתיבה {out.start_bar + 1} והבאס יוצא בתיבה {out.start_bar + out.bars - 16 + 1} "
                 f"(16 תיבות תופים בלבד)")
    if not prog:
        parts.append("כל 16 תיבות יש בילד קצר עם חיתוך של הפעמה האחרונה — סמנו אותו כנקודת מעבר טבעית")
    parts.append(f"שכנים הרמוניים ב-Camelot: {cam} ↔ {', '.join(neigh)}")
    return ". ".join(parts) + "."
