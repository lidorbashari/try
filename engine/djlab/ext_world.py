"""World-music extensions for DJ Lab recipes: Middle-Eastern & West-African percussion, plucked
strings, flutes, strings and the Israeli "Mizrahi" keyboard lead.

Everything is synthesised from scratch (modal synthesis, variable-pitch Karplus-Strong, filtered
noise, band-limited oscillators) — no samples. Used by ``genres/mediterranean.py`` and
``genres/afrobeats.py``; any recipe may import it.

Darbuka notation
----------------
``"D.Tk.kT.D.kkT.kk"`` — one character per step (16 = 16ths, 24 = 16th-triplets, 32 = 32nds):
``D``/``d`` doum (low centre stroke), ``T``/``t`` tek (sharp rim), ``K``/``k`` ka (other-hand rim),
``S``/``s`` slap (pa), ``.`` rest. Upper case = accent, lower case = soft. :func:`add_darbuka` turns a
notation pattern (string, list, dict or callable — like any ``Hits`` pattern) into one ``Hits`` layer
per stroke so every stroke gets its own level, pan and sends. Classic rhythms: :data:`RHYTHMS`.

Melodic mini-notation
---------------------
``mel("7:2 8:1/g+2 7:1 r:2 5:4/v,f-1")`` → note tuples ``(step, len, semitone, vel, ornaments)``.
Token = ``[!|~]pitch:len[/orn,orn]`` (``!`` accent, ``~`` soft, ``r`` = rest). Ornaments:
``s`` slide/legato into the next note · ``g±x`` grace note from x semitones · ``m±x`` mordent ·
``t±x`` trill with the note x semitones away · ``b±x`` bend/scoop in from x semitones (quarter tones:
``b-0.5``) · ``f±x`` fall at the end · ``q±x`` micro-tuning of the note itself · ``v`` deeper
vibrato · ``n`` no vibrato · ``r`` tremolo picking (plucked strings).

:class:`PhraseLayer` renders whole phrases with continuous pitch (portamento, slides, ornaments,
vibrato) using phrase instruments: :func:`oud`, :func:`qanun`, :func:`guitar` (variable-pitch
Karplus-Strong with double courses and body resonances), :func:`ney` (breathy flute),
:func:`mizrahi_lead` (the Israeli party keyboard lead) and :func:`strings_unison` (Arabic string
section playing the melody in unison). :func:`strings_pad` is a regular ``Notes`` instrument.
"""
from __future__ import annotations

import math

import numpy as np
from numba import njit
from scipy.signal import lfilter

from . import SR, drums
from .arrangement import Ctx, Hits, Layer, hash_name
from .dsp import F32, as_stereo, bp, eq_peak, fade, hp, lp, mix_into, normalize, saw, sine, square, svf
from .synth import chorus, white

TAU = 2.0 * math.pi


def _rng(rng):
    return rng if rng is not None else np.random.default_rng(0)


def _seed(*parts) -> int:
    return hash_name(repr(parts))


def _t(n, sr=SR):
    return np.arange(n) / sr


def _smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


# ============================================================================ rhythms
#: Classic Middle-Eastern rhythms in darbuka notation (16 steps = one 4/4 bar unless noted).
RHYTHMS = {
    # maqsum: D T - T D - T -
    "maqsum": ["D.T...T.D...T...", "D.Tk.kT.D.kkT.kk", "D.TkkkT.D.k.TkTk", "D.T.kkTkD.kkT.k."],
    # baladi: D D - T D - T -
    "baladi": ["D.D...T.D...T...", "D.D.k.TkD.kkT.kk", "D.DkkkT.D.k.TkTk"],
    # saidi: D T - D D - T -
    "saidi": ["D.T...D.D...T...", "D.Tk.kD.D.kkT.kk", "D.TkkkD.D.k.TkTk"],
    # malfuf (3-3-2 drive)
    "malfuf": ["D..T..T.D..T..T.", "D.kT.kT.D.kT.kTk", "D..TkkT.D..TkkTk"],
    # ayoub (2/4 trance rhythm)
    "ayoub": ["D..kD.T.D..kD.T.", "D.kkD.T.D.kkD.Tk"],
    # chiftetelli (8 beats over two bars): D tk T tk | D D T tk
    "chiftetelli": [["D...t.k.T...t.k.", "D...D...T...t.k."], ["D...TkkkT...t.k.", "D...D...T.k.TkTk"]],
    # house-friendly darbuka (leaves the kick's downbeats to the kick)
    "house": ["..T.k.Tk..T.k.Tk", "..TkK.T...TkK.Tk", "k.T.kkT.k.T.kkTk", "..T..kT...T..kTk"],
}
#: one-bar fills / rolls (32 = 32nd notes, 24 = 16th triplets)
FILLS = {
    "fill": ["D.TkTkTkD.TkTkTk", "D.T.TkTkTkTkTkTk", "D.kkT.kkTkTkTkTk", "TkTkD.TkTkTkD.TT"],
    "roll32": ["TkTkTkTkTkTkTkTkTkTkTkTkTkTkTkTk"],
    "roll24": ["TkkTkkTkkTkkTkkTkkTkkTkk"],
    "build": ["D.T.D.T.D.T.D.T.", "D.TkD.TkD.TkD.Tk", "DkTkDkTkDkTkDkTk", "TkTkTkTkTkTkTkTkTkTkTkTkTkTkTkTk"],
}
_STROKE_VEL = {"D": "X", "d": "o", "T": "X", "t": "o", "K": "x", "k": "g", "S": "X", "s": "o"}


def stroke_split(pattern: str | None, stroke: str) -> str | None:
    """Engine step string for one stroke type ('D', 'T', 'K', 'S') of a darbuka pattern."""
    if not pattern:
        return None
    up, lo = stroke.upper(), stroke.lower()
    out = []
    for ch in pattern.replace(" ", "").replace("|", ""):
        out.append(_STROKE_VEL[ch] if ch in (up, lo) else ".")
    s = "".join(out)
    return s if s.strip(".") else None


def _resolve(pattern, ctx):
    p = pattern(ctx) if callable(pattern) else pattern
    if isinstance(p, dict):
        p = p.get(ctx.section.name, p.get(ctx.section.kind, p.get("*")))
    if isinstance(p, (list, tuple)) and p and isinstance(p[0], str):
        p = p[ctx.i % len(p)]
    return p


def add_darbuka(song, pattern, kit=None, prefix="darbuka", gain_db=-6.0, pan=0.0, rng=None,
                levels=None, pans=None, sends=None, bus="drums", **kw):
    """Add one Hits layer per darbuka stroke following a notation ``pattern``.

    ``levels``: per-stroke offsets in dB (default doum 0, tek -1, ka -5, slap -3);
    ``pans``: per-stroke pan offsets. Returns the dict of layers."""
    kit = kit or darbuka_kit(rng)
    lv = {"D": 0.0, "T": -1.0, "K": -5.0, "S": -3.0}
    lv.update(levels or {})
    pn = {"D": 0.0, "T": 0.08, "K": -0.12, "S": 0.05}
    pn.update(pans or {})
    names = {"D": "doum", "T": "tek", "K": "ka", "S": "slap"}
    layers = {}
    for st, nm in names.items():
        def pat(c, st=st):
            return stroke_split(_resolve(pattern, c), st)
        layers[st] = song.hits(f"{prefix}_{nm}", kit[st], pat, bus=bus, gain_db=gain_db + lv[st],
                               pan=float(np.clip(pan + pn[st], -1, 1)), sends=dict(sends or {}), **kw)
    return layers


# ============================================================================ percussion one-shots
# circular membrane mode ratios (Bessel zeros relative to (0,1))
_MEMBRANE = [1.0, 1.594, 2.136, 2.296, 2.653, 2.918, 3.156, 3.501, 3.600, 3.652]


def _modes(n, f0, ratios_amps_decays, sr=SR, pitch_drop=0.0, drop_t=0.012, rng=None):
    t = _t(n, sr)
    bend = 1.0 + pitch_drop * np.exp(-t / drop_t)
    x = np.zeros(n)
    rng = _rng(rng)
    for r, a, d in ratios_amps_decays:
        f = f0 * r * bend
        if f0 * r > 16000:
            continue
        ph = TAU * np.cumsum(f) / sr + rng.random() * 0.3
        x += a * np.sin(ph) * np.exp(-t / d)
    return x


def darbuka_stroke(stroke="D", pitch_hz=None, metal=0.5, rng=None, sr=SR):
    """One darbuka (goblet drum) stroke by modal synthesis. ``metal`` (0..1) adds the bright ring of
    an aluminium Egyptian darbuka."""
    rng = _rng(rng)
    st = stroke.upper()
    if st == "D":
        p = pitch_hz or 96.0
        n = int(0.55 * sr)
        t = _t(n, sr)
        x = _modes(n, p, [(1.0, 1.0, 0.16), (2.296, 0.32, 0.05), (3.6, 0.12, 0.03), (1.594, 0.1, 0.04)],
                   sr, pitch_drop=0.22, drop_t=0.014, rng=rng)
        # goblet air "boom" just below the membrane pitch
        x += 0.45 * np.sin(TAU * p * 0.62 * t) * np.exp(-t / 0.09) * (1 - np.exp(-t / 0.004))
        slapn = svf(white(n, rng), 900.0, 0.9, "bp") * np.exp(-t / 0.006) * 0.5
        ring = _modes(n, p * 9.3, [(1.0, 1.0, 0.12), (1.47, 0.5, 0.08)], sr, rng=rng) * 0.04 * metal
        x = x + slapn + ring
        return normalize(fade(hp(x.astype(F32), 35.0), int(0.0006 * sr), int(0.03 * sr)))
    n = int(0.3 * sr)
    t = _t(n, sr)
    if st == "T":
        p = pitch_hz or 520.0
        body = _modes(n, p, [(1.0, 0.7, 0.03), (1.594, 0.6, 0.025), (2.136, 0.5, 0.02), (2.653, 0.35, 0.018),
                             (3.156, 0.25, 0.015)], sr, pitch_drop=0.06, drop_t=0.004, rng=rng)
        crack = hp(white(n, rng), 2800.0) * np.exp(-t / 0.0035) * 1.6
        ring = _modes(n, 3900.0 * (pitch_hz or 520.0) / 520.0, [(1.0, 1.0, 0.09), (1.33, 0.6, 0.07), (1.71, 0.4, 0.05)],
                      sr, rng=rng) * 0.22 * metal
        x = body + crack + ring
        return normalize(fade(hp(x.astype(F32), 300.0), int(0.0003 * sr), int(0.02 * sr)))
    if st == "K":
        p = pitch_hz or 470.0
        body = _modes(n, p, [(1.0, 0.8, 0.022), (1.594, 0.5, 0.018), (2.136, 0.35, 0.014), (2.653, 0.2, 0.012)],
                      sr, pitch_drop=0.05, drop_t=0.004, rng=rng)
        crack = hp(white(n, rng), 2200.0) * np.exp(-t / 0.0028) * 0.9
        ring = _modes(n, 3600.0 * p / 470.0, [(1.0, 1.0, 0.06), (1.41, 0.5, 0.04)], sr, rng=rng) * 0.12 * metal
        x = lp(body + crack + ring, 9000.0)
        return normalize(fade(hp(x.astype(F32), 300.0), int(0.0003 * sr), int(0.02 * sr)))
    # slap / pa: open slap – lots of mid noise + low membrane
    p = pitch_hz or 300.0
    body = _modes(n, p, [(1.0, 0.8, 0.04), (1.594, 0.5, 0.03), (2.296, 0.3, 0.02)], sr, pitch_drop=0.1, rng=rng)
    nz = svf(white(n, rng), 1600.0, 0.8, "bp") * np.exp(-t / 0.018) * 1.4
    x = body + nz + hp(white(n, rng), 4000.0) * np.exp(-t / 0.004)
    return normalize(fade(hp(x.astype(F32), 200.0), int(0.0003 * sr), int(0.02 * sr)))


def darbuka_kit(rng=None, pitch=1.0, metal=0.5, n=3):
    """Round-robin darbuka kit: {'D','T','K','S'} → list of ``n`` humanised one-shots."""
    rng = _rng(rng)
    kit = {}
    base = {"D": 96.0, "T": 520.0, "K": 470.0, "S": 300.0}
    for st, f in base.items():
        kit[st] = [darbuka_stroke(st, f * pitch * (1 + 0.012 * rng.uniform(-1, 1)), metal,
                                  np.random.default_rng(int(rng.integers(1 << 31)))) for _ in range(n)]
    return kit


def _jingles(n, count=6, spread_ms=10.0, bright=1.0, rng=None, sr=SR):
    """Brass jingle cluster (riq / tambourine zils): inharmonic partials, staggered clashes."""
    rng = _rng(rng)
    t = _t(n, sr)
    x = np.zeros(n)
    for _ in range(count):
        off = int(rng.uniform(0, spread_ms) * 1e-3 * sr)
        tt = t[: n - off]
        j = np.zeros(n - off)
        f0 = rng.uniform(4200, 6800) * bright
        for r, a in ((1.0, 1.0), (1.37, 0.7), (1.91, 0.5), (2.43, 0.35)):
            j += a * np.sin(TAU * f0 * r * tt + rng.random() * TAU) * np.exp(-tt / rng.uniform(0.03, 0.09))
        j += 0.6 * white(n - off, rng) * np.exp(-tt / 0.004)
        x[off:] += j * rng.uniform(0.5, 1.0)
    return x


def riq(stroke="tak", rng=None, sr=SR):
    """Riq (Arabic tambourine). ``stroke``: 'dum' (low skin + light jingles), 'tak' (edge + jingles),
    'jingle' (jingles only, the shake 'tsh')."""
    rng = _rng(rng)
    n = int(0.35 * sr)
    t = _t(n, sr)
    if stroke == "jingle":
        x = _jingles(n, 7, 14.0, 1.0, rng, sr)
        x = hp(x, 3500.0)
        return normalize(fade(x.astype(F32), int(0.0005 * sr), int(0.03 * sr)))
    if stroke == "dum":
        skin = _modes(n, 190.0, [(1.0, 1.0, 0.07), (1.594, 0.4, 0.04), (2.296, 0.2, 0.03)], sr, 0.15, rng=rng)
        x = skin + 0.35 * hp(_jingles(n, 4, 8.0, 1.0, rng, sr), 3500.0)
        return normalize(fade(hp(x.astype(F32), 80.0), 0, int(0.03 * sr)))
    skin = _modes(n, 560.0, [(1.0, 1.0, 0.025), (1.594, 0.6, 0.02), (2.136, 0.4, 0.015)], sr, 0.08, rng=rng)
    x = skin * 0.8 + hp(_jingles(n, 6, 10.0, 1.0, rng, sr), 3200.0) + hp(white(n, rng), 3000) * np.exp(-t / 0.003)
    return normalize(fade(hp(x.astype(F32), 250.0), 0, int(0.03 * sr)))


def zills(pitch_hz=None, decay=1.4, rng=None, sr=SR):
    """Finger cymbals (sagat / zills): two small brass cymbals struck together — bright inharmonic
    ring with slow beating. Returns stereo."""
    rng = _rng(rng)
    f0 = pitch_hz or rng.uniform(2550, 2900)
    n = int(decay * 1.4 * sr)
    t = _t(n, sr)
    outs = []
    for ch in range(2):
        x = np.zeros(n)
        for r, a, d in ((1.0, 1.0, 1.0), (1.48, 0.55, 0.7), (2.09, 0.4, 0.5), (2.57, 0.3, 0.38), (2.99, 0.2, 0.3),
                        (3.61, 0.12, 0.2)):
            beat = 1.0 + 0.0016 * (ch * 2 - 1) * r
            x += a * np.sin(TAU * f0 * r * beat * t + rng.random() * TAU) * np.exp(-t / (decay * d / 3.0))
        x += 0.5 * hp(white(n, rng), 5000.0) * np.exp(-t / 0.003)
        outs.append(fade(hp(x, 1800.0), int(0.0003 * sr), int(0.05 * sr)))
    st = np.stack(outs, axis=1)
    return (st / np.abs(st).max()).astype(F32)


def crowd_clap(people=5, spread_ms=9.0, rng=None, sr=SR):
    """Group hand-clap (party crowd clapping): several claps with human timing/tone spread."""
    rng = _rng(rng)
    n = int(0.45 * sr)
    x = np.zeros(n, dtype=np.float64)
    for i in range(people):
        c = drums.clap(tightness=rng.uniform(0.8, 1.3), tone_hz=rng.uniform(900, 1700), tail=rng.uniform(0.12, 0.2),
                       bursts=int(rng.integers(3, 5)), rng=np.random.default_rng(int(rng.integers(1 << 31))))
        off = 0 if i == 0 else int(abs(rng.normal(0, spread_ms / 2)) * 1e-3 * sr)
        m = min(n - off, len(c))
        x[off:off + m] += c[:m] * rng.uniform(0.6, 1.0)
    return normalize(fade(x.astype(F32), 0, int(0.04 * sr)))


def finger_snap(rng=None, sr=SR):
    return drums.snap(rng=rng, sr=sr)


def talking_drum(f0=150.0, bend=5.0, bend_time=0.1, decay=0.35, rng=None, sr=SR):
    """West-African talking drum (dùndún): membrane whose pitch is bent by squeezing the cords.
    ``bend`` semitones (+ up, - down) reached after ``bend_time`` s."""
    rng = _rng(rng)
    n = int(decay * 2.2 * sr)
    t = _t(n, sr)
    semis = bend * _smooth(t / max(bend_time, 1e-3))
    f = f0 * 2 ** (semis / 12.0) * (1 + 0.08 * np.exp(-t / 0.006))
    ph = TAU * np.cumsum(f) / sr
    x = np.sin(ph) * np.exp(-t / (decay / 3.0))
    x += 0.35 * np.sin(1.594 * ph) * np.exp(-t / (decay / 6.0))
    x += 0.15 * np.sin(2.136 * ph) * np.exp(-t / (decay / 8.0))
    x += 0.5 * svf(white(n, rng), 2600.0, 1.2, "bp") * np.exp(-t / 0.004)
    return normalize(fade(hp(x.astype(F32), 60.0), 0, int(0.02 * sr)))


def log_perc(freq_hz=420.0, decay=0.09, rng=None, sr=SR):
    """Wooden log / slit-drum knock (afro percussion)."""
    rng = _rng(rng)
    n = int(decay * 4 * sr)
    t = _t(n, sr)
    x = _modes(n, freq_hz, [(1.0, 1.0, decay), (2.57, 0.35, decay * 0.4), (4.9, 0.12, decay * 0.25)], sr, 0.04, 0.003,
               rng=rng)
    x += 0.4 * svf(white(n, rng), freq_hz * 4, 1.5, "bp") * np.exp(-t / 0.003)
    return normalize(fade(hp(x.astype(F32), 120.0), 0, int(0.01 * sr)))


def agogo(freq_hz=820.0, decay=0.22, rng=None, sr=SR):
    """Agogo / gankogui bell (inharmonic metal)."""
    rng = _rng(rng)
    n = int(decay * 2.5 * sr)
    t = _t(n, sr)
    x = _modes(n, freq_hz, [(1.0, 1.0, decay), (2.32, 0.45, decay * 0.6), (3.86, 0.25, decay * 0.4),
                            (5.2, 0.1, decay * 0.3)], sr, rng=rng)
    x += 0.3 * hp(white(n, rng), 3000.0) * np.exp(-t / 0.002)
    return normalize(fade(hp(x.astype(F32), 300.0), 0, int(0.02 * sr)))


# ============================================================================ melodic notation
def mel(s: str, vel: float = 0.88, offset: float = 0.0) -> list:
    """Parse the melodic mini-notation into note tuples ``(step, len, semitone, vel, orn)``.

    Tokens are played back to back; ``r:len`` is a rest; ``@step`` jumps to an absolute step."""
    out, pos = [], float(offset)
    for tok in s.split():
        if tok.startswith("@"):
            pos = float(tok[1:]) + offset
            continue
        v = vel
        if tok[0] == "!":
            v, tok = min(1.0, vel * 1.15), tok[1:]
        elif tok[0] == "~":
            v, tok = vel * 0.7, tok[1:]
        orn = ""
        if "/" in tok:
            tok, orn = tok.split("/", 1)
        p, ln = tok.split(":")
        ln = float(ln)
        if p != "r":
            out.append((pos, ln, float(p), round(v, 3), orn))
        pos += ln
    return out


def transpose(notes, base: float) -> tuple:
    """Semitone note tuples → absolute MIDI tuples (hashable)."""
    return tuple((st, ln, base + p, v, o) for st, ln, p, v, o in notes)


def shift(notes, steps: float) -> list:
    return [(n[0] + steps,) + tuple(n[1:]) for n in notes]


def stretch(notes, k: float) -> tuple:
    """Time-stretch a note tuple sequence by ``k`` (e.g. 2.0 = half tempo)."""
    return tuple((n[0] * k, n[1] * k) + tuple(n[2:]) for n in notes)


def parse_orn(orn: str) -> dict:
    d = {}
    if not orn:
        return d
    for tok in orn.split(","):
        tok = tok.strip()
        if not tok:
            continue
        k, v = tok[0], tok[1:]
        d[k] = float(v) if v else True
    return d


# ============================================================================ pitch / envelope builders
def pitch_track(notes, n, sr=SR, glide=0.045, legato_all=False, vib_rate=5.6, vib_depth=0.0, vib_delay=0.16,
                vib_attack=0.3, trill_hz=13.0, seed=0, vib_flag_only=False):
    """Per-sample MIDI pitch (float) for a monophonic phrase with portamento, ornaments, vibrato.

    ``notes``: sorted ``(t0_sec, dur_sec, midi, vel, orn)``. ``legato_all``: portamento between all
    touching notes (keyboard-lead style); otherwise only after notes flagged ``s``."""
    rng = np.random.default_rng(seed)
    curve = np.zeros(n)
    starts = [min(n, int(round(nt[0] * sr))) for nt in notes]
    if not notes:
        return curve
    for i, (t0, dur, m, vel, orn) in enumerate(notes):
        o = parse_orn(orn)
        s = starts[i]
        e = starts[i + 1] if i + 1 < len(notes) else n
        if s >= n or e <= s:
            continue
        seg = e - s
        tt = np.arange(seg) / sr
        base = m + o.get("q", 0.0)
        c = np.full(seg, base)
        if i > 0:
            pt0, pdur, pm, _, porn = notes[i - 1]
            po = parse_orn(porn)
            pm = pm + po.get("q", 0.0) + (po.get("f", 0.0) if "f" in po else 0.0)
            leg = "s" in po or (legato_all and pt0 + pdur >= t0 - 0.03)
            if leg:
                gl = min(glide * (1.6 if "s" in po else 1.0), max(dur * 0.5, 0.01))
                k = tt < gl
                c[k] = pm + (base - pm) * _smooth(tt[k] / gl)
        if "b" in o:
            bl = min(0.13, dur * 0.5)
            k = tt < bl
            c[k] += o["b"] * (1.0 - _smooth(tt[k] / bl))
        if "g" in o:
            gl2 = min(0.06, dur * 0.35)
            k = tt < gl2
            c[k] = base + o["g"] * (1.0 - _smooth((tt[k] - gl2 * 0.7) / (gl2 * 0.3)))
        if "m" in o:
            a0, a1 = min(0.025, dur * 0.15), min(0.075, dur * 0.4)
            k = (tt >= a0) & (tt < a1)
            w = np.sin(np.pi * (tt[k] - a0) / (a1 - a0))
            c[k] += o["m"] * np.clip(w * 1.6, 0, 1)
        if "t" in o:
            tl = dur * 0.82
            k = tt < tl
            sq = 0.5 * (1 + np.tanh(5.0 * np.sin(TAU * trill_hz * tt[k] - np.pi / 2)))
            c[k] += o["t"] * sq
        if "f" in o:
            fl = min(0.2, dur * 0.4)
            k = tt > dur - fl
            c[k] += o["f"] * _smooth((tt[k] - (dur - fl)) / fl)
        depth = vib_depth * (1.7 if "v" in o else (0.0 if vib_flag_only else 1.0)) * (0.0 if "n" in o or "t" in o else 1.0)
        if depth > 0 and dur > 0.18:
            ramp = _smooth((tt - vib_delay) / vib_attack) * (tt < dur + 0.05)
            rate = vib_rate * (1 + 0.04 * rng.uniform(-1, 1))
            c += depth * ramp * np.sin(TAU * rate * tt + rng.random() * TAU)
        curve[s:e] = c
    curve[: starts[0]] = notes[0][2] + parse_orn(notes[0][4]).get("q", 0.0)
    return curve


@njit(cache=True, fastmath=True)
def _follow(target, att, rel):
    n = target.shape[0]
    y = np.empty(n)
    v = 0.0
    for i in range(n):
        tg = target[i]
        if tg > v:
            v += (tg - v) * att
        else:
            v += (tg - v) * rel
        y[i] = v
    return y


def amp_track(notes, n, sr=SR, attack=0.005, release=0.08, legato_gap=0.03, reartic=0.25, reartic_t=0.03):
    """Amplitude envelope for a monophonic phrase (legato notes are not re-attacked; non-slide
    legato notes get a small re-articulation dip)."""
    target = np.zeros(n)
    for i, (t0, dur, m, vel, orn) in enumerate(notes):
        s = int(round(t0 * sr))
        e = int(round((t0 + dur) * sr))
        if i + 1 < len(notes):
            nt0 = notes[i + 1][0]
            if nt0 <= t0 + dur + legato_gap:
                e = max(e, int(round(nt0 * sr)))
        target[max(0, s):min(n, e)] = vel
    att = 1.0 - math.exp(-1.0 / (attack * sr))
    rel = 1.0 - math.exp(-1.0 / (release * sr))
    env = _follow(target, att, rel)
    if reartic > 0:
        for i in range(1, len(notes)):
            t0, dur, m, vel, orn = notes[i]
            pt0, pdur, _, _, porn = notes[i - 1]
            if "s" in parse_orn(porn) or t0 > pt0 + pdur + legato_gap:
                continue
            s = int(round(t0 * sr))
            k = min(n - s, int(reartic_t * 6 * sr))
            if k > 0:
                tt = np.arange(k) / sr
                env[s:s + k] *= 1.0 - reartic * np.sin(np.pi * np.clip(tt / (reartic_t * 2), 0, 1)) * (tt < reartic_t * 2)
    return env


def _hz(midi_curve):
    return 440.0 * 2.0 ** ((midi_curve - 69.0) / 12.0)


def _phrase_len(notes, tail, sr=SR):
    end = max(t0 + d for t0, d, *_ in notes)
    return int((end + tail) * sr)


# ============================================================================ variable-pitch Karplus-Strong
@njit(cache=True, fastmath=True)
def _ks_var(exc, delay, gain, bright):
    n = exc.shape[0]
    size = 8192
    buf = np.zeros(size)
    y = np.zeros(n, dtype=np.float32)
    w = 0
    prev = 0.0
    for i in range(n):
        d = delay[i]
        if d < 3.0:
            d = 3.0
        rp = w - d
        ip = math.floor(rp)
        f = rp - ip
        i0 = int(ip)
        im1 = (i0 - 1) % size
        i0m = i0 % size
        i1 = (i0 + 1) % size
        i2 = (i0 + 2) % size
        cm1 = -f * (f - 1.0) * (f - 2.0) / 6.0
        c0 = (f + 1.0) * (f - 1.0) * (f - 2.0) / 2.0
        c1 = -(f + 1.0) * f * (f - 2.0) / 2.0
        c2 = (f + 1.0) * f * (f - 1.0) / 6.0
        v = cm1 * buf[im1] + c0 * buf[i0m] + c1 * buf[i1] + c2 * buf[i2]
        lpv = bright * v + (1.0 - bright) * 0.5 * (v + prev)
        prev = v
        nv = gain[i] * lpv + exc[i]
        buf[w] = nv
        y[i] = nv
        w += 1
        if w >= size:
            w = 0
    return y


def _burst(period, vel, hardness, pos, rng):
    """Pluck excitation: one period of noise, low-passed by pick hardness, pick-position comb."""
    L = max(6, int(period))
    nz = rng.uniform(-1.0, 1.0, L)
    a = float(np.clip(1.0 - hardness, 0.0, 0.97))
    nz = lfilter([1.0 - a], [1.0, -a], nz)
    k = max(1, int(pos * L))
    nz2 = nz.copy()
    nz2[k:] -= nz[:-k]
    nz2 -= nz2.mean()
    nz2 *= np.hanning(L + 2)[1:-1] ** 0.3
    return nz2 * vel / (np.abs(nz2).max() + 1e-9)


def _ks_group(group, n0, sr, bright, t60, t60_rel, hardness, pos, detune_cents, seed, trem_hz, ref_hz=220.0):
    """Render one legato group (notes joined by slides/hammer-ons) on one string."""
    t_start = group[0][0]
    notes = [(t0 - t_start, d, m, v, o) for t0, d, m, v, o in group]
    end = max(t0 + d for t0, d, *_ in notes)
    n = int((end + t60_rel * 1.3 + 0.02) * sr)
    # left-hand vibrato only on notes flagged "v"
    curve = pitch_track(notes, n, sr, glide=0.07, legato_all=False, vib_depth=0.09, vib_rate=5.2, vib_delay=0.12,
                        seed=seed, vib_flag_only=True)
    curve = curve + detune_cents / 100.0
    hz = _hz(curve)
    delay = sr / hz - 0.5 * (1.0 - bright)
    # decay: higher notes shorter (∝ sqrt), released after the gate
    t60c = t60 * np.sqrt(ref_hz / np.maximum(hz, 30.0))
    gate_end = int(end * sr)
    t60c[gate_end:] = np.minimum(t60c[gate_end:], t60_rel)
    gain = 0.001 ** ((1.0 / hz) / np.maximum(t60c, 0.01))
    exc = np.zeros(n)
    rng = np.random.default_rng(seed)
    for j, (t0, d, m, v, o) in enumerate(notes):
        oo = parse_orn(o)
        s = int(round(t0 * sr))
        if s >= n:
            continue
        if j == 0 or "h" not in parse_orn(notes[j - 1][4]) and "s" not in parse_orn(notes[j - 1][4]):
            per = delay[min(s, n - 1)]
            b = _burst(per, v, hardness * (0.75 + 0.25 * v), pos, rng)
            e = min(n, s + b.shape[0])
            exc[s:e] += b[: e - s]
        else:  # hammer-on / slide: tiny re-excitation keeps it alive
            per = delay[min(s, n - 1)]
            b = _burst(per, v * 0.12, hardness * 0.5, pos, rng)
            e = min(n, s + b.shape[0])
            exc[s:e] += b[: e - s]
        if "r" in oo:  # tremolo picking (risha)
            step = 1.0 / trem_hz
            tt = t0 + step
            k = 0
            while tt < t0 + d - step * 0.5:
                ss = int(round(tt * sr))
                per = delay[min(ss, n - 1)]
                b = _burst(per, v * (0.55 + 0.2 * (k % 2)), hardness * 0.8, pos, rng)
                e = min(n, ss + b.shape[0])
                exc[ss:e] += b[: e - ss] * 0.6
                tt += step
                k += 1
        if "t" in oo or "g" in oo or "m" in oo:  # left-hand ornaments: small excitations
            per = delay[min(s + int(0.05 * sr), n - 1)]
            b = _burst(per, v * 0.15, hardness * 0.6, pos, rng)
            ss = min(n - 1, s + int(0.05 * sr))
            e = min(n, ss + b.shape[0])
            exc[ss:e] += b[: e - ss]
    y = _ks_var(exc, delay, gain, float(bright)).astype(np.float64)
    # damp the very end smoothly
    y = fade(y.astype(F32), 0, int(0.01 * sr))
    return int(round(t_start * sr)), y


def _groups(notes):
    groups, cur = [], []
    for nt in notes:
        if cur and ("s" in parse_orn(cur[-1][4]) or "h" in parse_orn(cur[-1][4])):
            cur.append(nt)
        else:
            if cur:
                groups.append(cur)
            cur = [nt]
    if cur:
        groups.append(cur)
    return groups


def plucked_string(bright=0.5, t60=1.8, t60_rel=0.12, hardness=0.85, pos=0.18, courses=2, course_cents=3.0,
                   course_ms=1.2, body=(), attack_click=0.08, tail=1.2, octave_double=0.0, lp_hz=None, hp_hz=None,
                   width=0.35, trem_hz=14.0, sr=SR):
    """Phrase instrument factory: variable-pitch Karplus-Strong string(s) with double courses,
    plectrum attack click and body resonances (``body`` = [(hz, gain_db, q), ...])."""
    def inst(notes):
        n = _phrase_len(notes, tail, sr)
        out = np.zeros((n, 2))
        seed0 = _seed("ks", notes)
        for gi, grp in enumerate(_groups(notes)):
            for c in range(courses):
                cents = 0.0 if courses == 1 else course_cents * (2 * c / (courses - 1) - 1)
                s, y = _ks_group(grp, n, sr, bright, t60, t60_rel, hardness, pos, cents, seed0 + gi * 31 + c * 7, trem_hz)
                off = s + int(c * course_ms * 1e-3 * sr)
                pan = (2 * c / max(1, courses - 1) - 1) * width if courses > 1 else 0.0
                gl, gr = math.cos((pan + 1) * math.pi / 4) * math.sqrt(2), math.sin((pan + 1) * math.pi / 4) * math.sqrt(2)
                m = min(n - off, y.shape[0])
                if m > 0:
                    out[off:off + m, 0] += y[:m] * gl
                    out[off:off + m, 1] += y[:m] * gr
                if octave_double:
                    grp2 = [(t0, d, mm + 12, v * octave_double, o) for t0, d, mm, v, o in grp]
                    s2, y2 = _ks_group(grp2, n, sr, bright, t60 * 0.8, t60_rel, hardness, pos, cents,
                                       seed0 + gi * 31 + c * 7 + 3, trem_hz)
                    m2 = min(n - off, y2.shape[0])
                    if m2 > 0:
                        out[off:off + m2, 0] += y2[:m2] * gr
                        out[off:off + m2, 1] += y2[:m2] * gl
            if attack_click:
                rng = np.random.default_rng(seed0 + gi)
                s = int(round(grp[0][0] * sr))
                k = int(0.004 * sr)
                if s + k < n:
                    ck = hp(white(k, rng), 3500.0) * np.exp(-np.arange(k) / (0.0008 * sr)) * attack_click * grp[0][3]
                    out[s:s + k] += ck[:, None]
        x = out.astype(F32)
        for f, g, q in body:
            x = eq_peak(x, f, g, q, sr)
        if hp_hz:
            x = hp(x, hp_hz, 2, sr)
        if lp_hz:
            x = lp(x, lp_hz, 2, sr)
        peak = max(nt[3] for nt in notes)
        return normalize(fade(x, 0, int(0.02 * sr)), 0.8 * peak)
    return inst


def oud(bright=0.3, t60=1.5, hardness=0.72, pos=0.17, sr=SR, **kw):
    """Fretless Arabic lute: warm double courses, bright plectrum (risha) attack, deep wooden body.
    Supports slides (``s``), hammer-ons (``h``), tremolo picking (``r``), grace notes, trills."""
    kw.setdefault("body", [(110.0, 3.5, 1.3), (230.0, 3.5, 1.5), (480.0, -1.5, 1.2), (1900.0, 2.0, 1.6),
                           (5000.0, -6.0, 0.7)])
    kw.setdefault("lp_hz", 7500.0)
    kw.setdefault("hp_hz", 70.0)
    return plucked_string(bright=bright, t60=t60, hardness=hardness, pos=pos, courses=2, course_cents=3.5,
                          course_ms=1.4, attack_click=0.16, sr=sr, **kw)


def qanun(bright=0.72, t60=2.2, hardness=0.97, pos=0.11, sr=SR, **kw):
    """Arabic zither: bright triple-course strings plucked with metal picks, light skin-bridge body."""
    kw.setdefault("body", [(330.0, 2.5, 1.5), (1200.0, -1.5, 1.0), (3100.0, 3.5, 1.3), (7000.0, 1.5, 1.0)])
    kw.setdefault("hp_hz", 150.0)
    kw.setdefault("lp_hz", 13000.0)
    kw.setdefault("tail", 1.6)
    return plucked_string(bright=bright, t60=t60, hardness=hardness, pos=pos, courses=3, course_cents=2.5,
                          course_ms=0.7, attack_click=0.1, width=0.5, sr=sr, **kw)


def guitar(bright=0.55, t60=1.3, hardness=0.8, pos=0.24, muted=False, sr=SR, **kw):
    """Clean highlife guitar (single course). ``muted`` = palm-muted (short, darker)."""
    kw.setdefault("body", [(110.0, 2.0, 1.2), (220.0, 2.5, 1.5), (2600.0, 2.0, 1.2), (6000.0, -3.0, 0.8)])
    kw.setdefault("hp_hz", 90.0)
    kw.setdefault("lp_hz", 8500.0 if not muted else 4200.0)
    kw.setdefault("tail", 0.8)
    return plucked_string(bright=bright if not muted else bright * 0.6, t60=t60 if not muted else 0.35,
                          t60_rel=0.08 if not muted else 0.04, hardness=hardness, pos=pos, courses=2,
                          course_cents=1.5, course_ms=6.0, attack_click=0.05, width=0.6, sr=sr, **kw)


# ============================================================================ wind / bowed / keyboard leads
def ney(breath=0.35, vib_depth=0.18, vib_rate=5.0, attack=0.07, release=0.2, tail=1.0, bright=0.5, sr=SR):
    """Ney / kaval: end-blown reed flute — sine + weak harmonics, pitched breath noise tracking the
    fundamental, airy hiss, chiff on attacks, scoops and delayed vibrato. Stereo-ish (slight width)."""
    def inst(notes):
        n = _phrase_len(notes, tail, sr)
        seed = _seed("ney", notes)
        rng = np.random.default_rng(seed)
        mc = pitch_track(notes, n, sr, glide=0.06, legato_all=True, vib_rate=vib_rate, vib_depth=vib_depth,
                         vib_delay=0.22, vib_attack=0.4, seed=seed)
        # slow random pitch drift (breath pressure)
        drift = lfilter([0.0005], [1, -0.9995], rng.normal(0, 1, n)) * 2.0
        hz = _hz(mc + drift * 0.06)
        ph = TAU * np.cumsum(hz) / sr
        tone = np.sin(ph) + 0.18 * np.sin(2 * ph + 0.3) + 0.08 * np.sin(3 * ph + 1.1) + 0.03 * np.sin(4 * ph)
        env = amp_track(notes, n, sr, attack=attack, release=release, reartic=0.18, reartic_t=0.04)
        flutter = 1.0 + 0.06 * lfilter([0.002], [1, -0.998], rng.normal(0, 1, n)) * 10
        wn = white(n, rng).astype(np.float64)
        pitched = svf(wn.astype(F32), hz, 7.0, "bp", sr) * 2.2 + svf(wn.astype(F32), hz * 2, 6.0, "bp", sr) * 0.8
        air = lp(hp(wn.astype(F32), 1800.0), 7000.0) * 0.25
        x = tone * (1 - breath * 0.5) + (pitched + air) * breath
        # chiff on non-legato attacks
        for i, (t0, d, m, v, o) in enumerate(notes):
            if i > 0 and notes[i - 1][0] + notes[i - 1][1] >= t0 - 0.03:
                continue
            s = int(t0 * sr)
            k = min(n - s, int(0.05 * sr))
            if k > 0:
                tt = np.arange(k) / sr
                x[s:s + k] += svf(white(k, rng), 2200.0 * bright + 1200.0, 1.2, "bp") * np.exp(-tt / 0.012) * 0.5 * v
        y = x * env * flutter
        y = hp(y.astype(F32), 160.0)
        st = np.stack([y, np.concatenate([np.zeros(int(0.0007 * sr)), y[: -int(0.0007 * sr)]])], axis=1)
        peak = max(nt[3] for nt in notes)
        return normalize(fade(st.astype(F32), 0, int(0.03 * sr)), 0.8 * peak)
    return inst


def mizrahi_lead(vib_depth=0.32, vib_rate=6.1, glide=0.035, nasal=0.6, cutoff=3800.0, drive=1.6, detune=6.0,
                 attack=0.004, release=0.09, tail=0.8, sr=SR):
    """The Israeli Mizrahi party keyboard lead ("oriental" keyboard): bright double-saw + pulse,
    nasal reed formant, strong delayed vibrato, always-on portamento between touching notes, and
    quarter-tone bends/trills/grace notes from the ornament flags."""
    def inst(notes):
        n = _phrase_len(notes, tail, sr)
        seed = _seed("mizrahi", notes)
        mc = pitch_track(notes, n, sr, glide=glide, legato_all=True, vib_rate=vib_rate, vib_depth=vib_depth,
                         vib_delay=0.13, vib_attack=0.22, trill_hz=14.0, seed=seed)
        hz = _hz(mc)
        d = 2 ** (detune / 1200.0)
        a = saw(hz * d, n, 0.0) * 0.5 + saw(hz / d, n, 0.37) * 0.5
        p = square(hz, n, 0.13, 0.28) * 0.45
        osc = (a + p).astype(F32)
        env = amp_track(notes, n, sr, attack=attack, release=release, reartic=0.3, reartic_t=0.025)
        # brightness follows the envelope a little (keyboard velocity feel)
        cut = cutoff * (0.7 + 0.45 * env / (env.max() + 1e-9))
        body = svf(osc, cut, 0.9, "lp", sr)
        reed = svf(osc, 1350.0, 3.2, "bp", sr) * nasal + svf(osc, 2900.0, 4.0, "bp", sr) * nasal * 0.45
        x = (body + reed).astype(np.float64)
        x = np.tanh(x * drive) / math.tanh(drive)
        y = (x * env).astype(F32)
        y = hp(y, 180.0)
        y = eq_peak(y, 4500.0, -2.5, 1.0, sr)
        st = chorus(y, 0.9, 1.8, 9.0, 0.32, sr)
        peak = max(nt[3] for nt in notes)
        return normalize(fade(st.astype(F32), 0, int(0.02 * sr)), 0.8 * peak)
    return inst


def strings_unison(voices=7, detune_cents=7.0, vib_depth=0.16, vib_rate=5.4, attack=0.06, release=0.28,
                   glide=0.06, cutoff=5200.0, spread=0.9, tail=1.2, sr=SR):
    """Arabic string section (firqa) playing a melody in unison: several detuned bowed voices with
    their own vibrato and timing, legato glissandi, violin body resonances. Stereo."""
    def inst(notes):
        n = _phrase_len(notes, tail, sr)
        seed = _seed("strings_u", notes)
        rng = np.random.default_rng(seed)
        base = pitch_track(notes, n, sr, glide=glide, legato_all=True, vib_depth=0.0, seed=seed)
        env = amp_track(notes, n, sr, attack=attack, release=release, reartic=0.15, reartic_t=0.05)
        out = np.zeros((n, 2))
        t = np.arange(n) / sr
        for v in range(voices):
            off = int(rng.uniform(0, 0.018) * sr)
            cents = (v / max(1, voices - 1) * 2 - 1) * detune_cents + rng.normal(0, 1.5)
            vib = vib_depth * rng.uniform(0.7, 1.2) * np.sin(TAU * vib_rate * rng.uniform(0.9, 1.1) * t + rng.random() * TAU)
            vib *= _smooth((env / (env.max() + 1e-9)) * 1.5)  # vibrato only while sounding
            mc = np.concatenate([np.full(off, base[0]), base[: n - off]]) + cents / 100.0 + vib
            e = np.concatenate([np.zeros(off), env[: n - off]])
            x = saw(_hz(mc), n, rng.random()).astype(np.float64) * e
            pan = (v / max(1, voices - 1) * 2 - 1) * spread
            out[:, 0] += x * math.cos((pan + 1) * math.pi / 4)
            out[:, 1] += x * math.sin((pan + 1) * math.pi / 4)
        x = out.astype(F32)
        x = svf(x, cutoff, 0.7, "lp", sr)
        for f, g, q in ((300.0, 2.5, 1.2), (1000.0, -2.0, 1.0), (2900.0, 3.0, 1.4), (4800.0, -2.0, 1.0)):
            x = eq_peak(x, f, g, q, sr)
        x = hp(x, 190.0)
        peak = max(nt[3] for nt in notes)
        return normalize(fade(x, 0, int(0.03 * sr)), 0.8 * peak)
    return inst


def strings_pad(attack=0.45, release=1.2, cutoff=3400.0, voices=5, detune_cents=9.0, vib_depth=0.1, sr=SR):
    """``Notes`` instrument: string-section chord voice (ensemble of detuned bowed saws with
    independent vibrato, slow bow attack, violin/viola body EQ). Stereo."""
    def inst(freq, dur, vel):
        gate = max(16, int(dur * sr))
        n = gate + int(release * sr)
        t = np.arange(n) / sr
        rng = np.random.default_rng(int(freq * 101) % 100003)
        out = np.zeros((n, 2))
        for v in range(voices):
            cents = (v / max(1, voices - 1) * 2 - 1) * detune_cents
            vib = vib_depth * np.sin(TAU * rng.uniform(4.8, 6.0) * t + rng.random() * TAU) * _smooth(t / 0.6)
            f = freq * 2 ** ((cents / 100.0 + vib) / 12.0)
            x = saw(f, n, rng.random()).astype(np.float64)
            pan = (v / max(1, voices - 1) * 2 - 1) * 0.8
            out[:, 0] += x * math.cos((pan + 1) * math.pi / 4)
            out[:, 1] += x * math.sin((pan + 1) * math.pi / 4)
        a = np.clip(t / attack, 0, 1) ** 1.6
        env = a.copy()
        if gate < n:
            env[gate:] = env[gate - 1] * np.exp(-(t[gate:] - t[gate]) * 5.0 / release)
        x = (out * env[:, None]).astype(F32)
        x = svf(x, cutoff, 0.7, "lp", sr)
        x = eq_peak(x, 2900.0, 2.0, 1.2, sr)
        x = hp(x, 150.0)
        return normalize(fade(x, 16, 512), 0.8 * vel)
    return inst


# ============================================================================ phrase layer
class PhraseLayer(Layer):
    """Layer that places whole rendered phrases. ``phrases``: ``callable(ctx) -> [(step, notes,
    gain), ...]`` where ``notes`` is a hashable tuple of ``(step, len_steps, midi, vel, orn)``
    relative to the phrase start (see :func:`mel` / :func:`transpose`). The phrase instrument gets
    ``(t0_sec, dur_sec, midi, vel, orn)`` notes; renders are cached per (notes, gain)."""

    def __init__(self, name, instrument, phrases, bus="music", swing=None, lookback=8, **kw):
        super().__init__(name, bus=bus, **kw)
        self.instrument = instrument
        self.phrases = phrases
        self.swing = swing
        self.lookback = lookback
        self._cache: dict = {}

    def _render(self, song, notes, gain):
        key = (notes, round(float(gain), 3))
        x = self._cache.get(key)
        if x is None:
            g = song.grid
            sw = song.swing if self.swing is None else self.swing
            off = g.swing_offset_steps(1, sw) * g.step_sec
            ev = []
            for st, ln, m, v, o in sorted(notes):
                t0 = st * g.step_sec + (off if float(st).is_integer() and int(st) % 2 == 1 else 0.0)
                ev.append((t0, ln * g.step_sec, float(m), float(v) * gain, o))
            x = as_stereo(self.instrument(tuple(ev)))
            self._cache[key] = x
        return x

    def render_dry(self, song, a, b):
        n = b - a
        buf = np.zeros((n, 2), dtype=F32)
        hit = False
        g = song.grid
        for bar in self.bars_in(song, a, b, lookback=self.lookback):
            ctx = Ctx(song, bar, self)
            if not self.active(ctx):
                continue
            for item in (self.phrases(ctx) or []):
                st, notes, gain = item if len(item) == 3 else (item[0], item[1], 1.0)
                if not notes:
                    continue
                pos = g.step_sample(bar, st, 16, None)
                if pos >= b:
                    continue
                x = self._render(song, tuple(notes), gain)
                if pos + x.shape[0] <= a:
                    continue
                mix_into(buf, x, pos - a)
                hit = True
        return buf if hit else None


def add_phrases(song, name, instrument, phrases, **kw) -> PhraseLayer:
    return song.add(PhraseLayer(name, instrument, phrases, **kw))


# ============================================================================ scale helpers
HARMONIC_MINOR = [0, 2, 3, 5, 7, 8, 11]
HIJAZ = [0, 1, 4, 5, 7, 8, 10]
DOUBLE_HARMONIC = [0, 1, 4, 5, 7, 8, 11]
NATURAL_MINOR = [0, 2, 3, 5, 7, 8, 10]
MAJOR = [0, 2, 4, 5, 7, 9, 11]
MAJOR_PENT = [0, 2, 4, 7, 9]


def scale_note(scale, deg: int, root: float = 0.0) -> float:
    o, d = divmod(int(deg), len(scale))
    return root + 12 * o + scale[d]


def run(scale, from_deg: int, to_deg: int, step_len: float = 0.5, start: float = 0.0, vel: float = 0.8,
        root: float = 0.0, accent_every: int = 4) -> list:
    """Scale run (qanun/oud flourish) from degree ``from_deg`` to ``to_deg`` in ``step_len`` steps."""
    out = []
    d = 1 if to_deg >= from_deg else -1
    pos = start
    for i, deg in enumerate(range(from_deg, to_deg + d, d)):
        v = vel if i % accent_every == 0 else vel * 0.78
        out.append((pos, step_len * 1.6, scale_note(scale, deg, root), round(v, 3), ""))
        pos += step_len
    return out


def kick_tune(key, lo=46.0, hi=60.0) -> float:
    """A kick tuning in [lo, hi] Hz that is a chord tone (root, fifth, third) of the key."""
    cands = []
    third = 3 if key.quality == "minor" else 4
    for semis, pref in ((0, 0.0), (7, 1.0), (third, 2.0)):
        pc = (key.root_pc + semis) % 12
        for octv in range(0, 3):
            f = 440.0 * 2 ** (((12 * (octv + 1) + pc) - 69) / 12.0)
            if lo <= f <= hi:
                cands.append((pref + abs(f - 53.0) / 20.0, f))
    return min(cands)[1] if cands else 52.0
