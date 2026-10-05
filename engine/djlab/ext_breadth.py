"""Breadth-producer toolkit: extra drums, instruments, FX, textures and a grid-locked mono bass-line
layer used by the psytrance, trance, dnb, dubstep, ukg, breaks and lofi recipes.

Pure additions on top of the core engine (no core module is modified). Everything is synthesised
from scratch; all randomness comes from the ``rng`` passed in, or from generators seeded by note
pitch / bar index, so renders stay bit-identical for the same plan entry.

Contents
--------
* drums: :func:`psy_kick`, :func:`layered_snare`, :func:`break_kit`, :func:`break_bus`, :func:`dusty`
* instruments (``inst(freq, dur, vel)`` factories): :func:`psy_bass`, :func:`fm_seq`, :func:`anthem_lead`,
  :func:`rhodes`, :func:`m1_organ`, :func:`dread_bass`, :func:`soft_bass`, :func:`flute`
* one-shot FX: :func:`zap`, :func:`laser_up`, :func:`pitch_dive`, :func:`scratch`, :func:`siren`
* textures: :func:`speechy` (spoken-word-like vowel gibberish), :func:`bar_texture` + :func:`rain_bar`,
  :func:`crackle_bar` (rendered per bar, deterministic for any render window)
* :func:`tape_wobble` (wow & flutter insert), :func:`gate_fx`
* :class:`SynthLine` layer + voices :class:`Wobble`, :class:`Growl`, :class:`Reese`, :class:`SubLine`
  (tempo-synced LFO from absolute grid time; note flag ``w<N>`` = LFO at N cycles per bar)
"""
from __future__ import annotations

import math
import re

import numpy as np
from numba import njit
from scipy import signal

from . import SR, drums
from . import fx as _fx
from .arrangement import Notes
from .dsp import (F32, as_mono, as_stereo, bp, fade, hp, ladder, lp, mix_into, mod_delay, normalize, saw, sine,
                  square, svf, triangle)
from .mixer import Bus
from .synth import adsr, chorus, fm, pink, supersaw, unison, white

TAU = 2.0 * math.pi


# ============================================================================ helpers
def midi_hz(m) -> float:
    return 440.0 * 2.0 ** ((float(m) - 69.0) / 12.0)


def _n(dur, release, sr=SR):
    gate = max(16, int(dur * sr))
    return gate, gate + int(release * sr)


def _finish(x, vel, rel_fade=64):
    x = fade(np.asarray(x, dtype=F32), 16, rel_fade)
    return normalize(x, 0.8 * float(vel))


def note_in_range(pc: int, lo_hz: float, hi_hz: float | None = None) -> int:
    """MIDI note with pitch class ``pc`` whose frequency is the lowest ≥ ``lo_hz``."""
    m = int(pc) % 12 + 12
    while midi_hz(m) < lo_hz:
        m += 12
    return m


def kick_tune(key, lo=44.0, hi=62.0) -> float:
    """Kick body frequency: the key root if it falls in [lo, hi), else the fifth, else the root ≥ lo."""
    for pc in (key.root_pc, (key.root_pc + 7) % 12):
        m = note_in_range(pc, lo)
        if midi_hz(m) < hi:
            return midi_hz(m)
    return midi_hz(note_in_range(key.root_pc, lo))


def ramp_points(song, kind, bars, lo, hi):
    """Automation points ramping from ``lo`` to ``hi`` over the ``bars`` before every section of ``kind``."""
    pts = []
    for s in song.sections:
        if s.kind == kind or s.name == kind:
            pts += [(s.start_bar - bars, lo), (s.start_bar - 1e-3, hi), (s.start_bar, lo)]
    return pts or [(0, lo)]


# ============================================================================ drums
def psy_kick(tune_hz=48.0, length=0.1, click=0.6, drive=2.4, knock=1.0, rng=None, sr=SR):
    """Short, punchy psytrance kick that is (almost) silent before the next 16th, so the rolling bass
    never overlaps it. ``length`` ≈ one 16th note."""
    rng = rng if rng is not None else np.random.default_rng(0)
    n = int(length * sr)
    t = np.arange(n) / sr
    f = tune_hz + (1000.0 - tune_hz) * np.exp(-t / 0.0032) + 85.0 * knock * np.exp(-t / 0.02)
    ph = TAU * np.cumsum(f) / sr
    body = np.sin(ph - ph[0])
    u = t / length
    amp = (1.0 - u ** 3) ** 2 * (0.7 + 0.3 * np.exp(-t / 0.025))
    nc = int(0.005 * sr)
    tc = np.arange(nc) / sr
    ck = np.zeros(n)
    ck[:nc] = (bp(white(nc, rng), 1800.0, 7000.0) * 0.8 + np.sin(TAU * 2600.0 * tc)) * np.exp(-tc / 0.0018)
    x = body * amp + click * 0.35 * ck
    x = np.tanh(x * drive) / math.tanh(drive)
    x = hp(x.astype(F32), 22.0, 2)
    x = lp(x, 9000.0, 2)
    return normalize(fade(x, int(0.0004 * sr), int(0.003 * sr)))


def layered_snare(rng, tone_hz=200.0, snappy=0.8, decay=0.18, clap_amt=0.5, body=1.0, crack_hz=1800.0, sr=SR):
    """Snare + clap layer (DnB / dubstep / breaks backbeat)."""
    s = drums.snare(tone_hz=tone_hz, snappy=snappy, decay=decay, rng=rng)
    c = drums.clap(tone_hz=crack_hz * 0.7, tail=decay * 1.1, rng=rng)
    n = max(s.shape[0], c.shape[0])
    x = np.zeros(n, dtype=F32)
    x[: s.shape[0]] += s * body
    x[: c.shape[0]] += c * clap_amt
    x = np.tanh(x * 1.3) / math.tanh(1.3)
    return normalize(fade(x.astype(F32), 0, int(0.01 * sr)))


def break_kit(rng, tune=1.0, sr=SR):
    """'Vintage funk break' kit: round kick, cracky snare with shell ring, ghost snare, trashy hats,
    open hat, ride. Use on a ``break`` bus (:func:`break_bus`) for the sampled-break character."""
    k = drums.kick("house", tune_hz=60.0 * tune, decay=0.26, click=0.4, drive=1.6, rng=rng)
    k = lp(k, 5000.0)
    s = drums.snare(tone_hz=205.0 * tune, snappy=0.85, decay=0.2, rng=rng)
    n = s.shape[0]
    t = np.arange(n) / sr
    ring = (np.sin(TAU * 330.0 * tune * t) * 0.25 + np.sin(TAU * 910.0 * tune * t) * 0.12) * np.exp(-t / 0.07)
    s = lp(s + ring.astype(F32), 9000.0)
    g = drums.snare(tone_hz=235.0 * tune, snappy=0.6, decay=0.09, kind="tight", rng=rng)
    h = drums.hat(decay=0.05, tone=0.82, noise_mix=0.55, rng=rng)
    oh = drums.hat(open_=True, decay=0.2, tone=0.82, noise_mix=0.5, rng=rng)
    r = drums.ride(decay=1.0, bell=0.7, rng=rng)
    return {"kick": normalize(k), "snare": normalize(s), "ghost": normalize(lp(g, 8000.0)),
            "hat": normalize(lp(h, 11000.0)), "ohat": normalize(lp(oh, 11000.0)), "ride": normalize(lp(r, 12000.0))}


def break_bus(hp_hz=110.0, lp_hz=10000.0, sat=0.45, gain_db=0.0) -> Bus:
    """Bus for synthesised breakbeat layers: band-limited, squashed and saturated (sampled feel)."""
    return Bus("break", gain_db=gain_db, hp=hp_hz, lp=lp_hz, sat=sat, mono_below=150.0, width=1.1,
               comp=dict(threshold_db=-16.0, ratio=4.0, attack_ms=4.0, release_ms=70.0, makeup_db=2.0),
               eq=[("peak", 1900.0, 2.5, 0.9), ("peak", 350.0, -2.0, 1.0)])


def dusty(lp_hz=7000.0, bits=12, drive=1.4):
    """Layer insert: low-pass + gentle bit reduction + tape saturation (lo-fi drums)."""
    def f(x):
        y = lp(as_stereo(x), lp_hz, 2)
        y = _fx.bitcrush(y, bits, 1)
        return _fx.tape(y, drive, 0.4)
    return f


# ============================================================================ instruments
def psy_bass(cutoff=170.0, env_amt=2600.0, decay=0.05, res=0.35, drive=2.2, sub=0.45, sustain=0.5,
             release=0.006, pulse=0.25, sr=SR):
    """Rolling psytrance bass voice: saw (+ a little pulse) through a 24 dB ladder with a fast
    filter envelope ('plonk'), sine sub, very short release so each 16th is tight."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        osc = saw(freq, n) + pulse * square(freq, n, 0.25, 0.3)
        cut = cutoff + env_amt * vel * np.exp(-t / decay)
        x = ladder(osc * 0.8, cut, res, drive)
        x = x + sub * sine(freq, n)
        env = adsr(n, gate, 0.0008, decay * 2.5, sustain, release, sr, curve=4.0)
        return _finish(x * env, vel, rel_fade=48)
    return inst


def fm_seq(ratio=2.0, index=5.0, idx_decay=0.06, decay=0.12, feedback=0.35, cutoff=7000.0, sustain=0.08,
           release=0.02, pitch_drop=0.0, sr=SR):
    """Two-op FM 'psy' voice: bright index envelope → squelchy/metallic 16th sequences and zaps."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        f = freq * (1.0 + pitch_drop * np.exp(-t / 0.012))
        x = fm(f, n, ratio, index * (0.5 + 0.5 * vel), np.exp(-t / idx_decay), feedback)
        x = svf(x, cutoff, 0.9, "lp")
        env = adsr(n, gate, 0.0008, decay, sustain, release, sr)
        return _finish(x * env, vel)
    return inst


def anthem_lead(detune=0.32, cutoff=5200.0, res=0.15, attack=0.006, release=0.32, vibrato=0.14,
                octave_mix=0.35, sr=SR):
    """Big trance supersaw lead: 7-voice supersaw + quieter octave supersaw, delayed vibrato,
    gentle resonant low-pass. Stereo."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        vib = vibrato * np.sin(TAU * 5.4 * t) * np.clip((t - 0.18) / 0.25, 0.0, 1.0)
        f = freq * 2.0 ** (vib / 12.0)
        rng = np.random.default_rng(int(freq * 3) % 9973)
        x = supersaw(f, n, detune=detune, mix=0.75, rng=rng)
        if octave_mix:
            x = x + octave_mix * supersaw(f * 2.0, n, detune=detune * 0.8, mix=0.6, rng=rng)
        cut = cutoff * (0.65 + 0.35 * vel) * (1.0 + 0.6 * np.exp(-t / 0.08))
        x = svf(x, cut, 0.7 + res * 3, "lp")
        env = adsr(n, gate, attack, 0.35, 0.82, release, sr, curve=4.0)
        return _finish(x * env[:, None], vel, rel_fade=256)
    return inst


def rhodes(bright=0.55, tremolo=0.22, trem_rate=4.2, bark=0.35, release=0.35, drift_cents=4.0, sr=SR):
    """Electric piano (Rhodes-like): FM body + tine transient, velocity 'bark', stereo tremolo,
    slight per-note detune drift. Long natural decay. Stereo."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        rng = np.random.default_rng(int(freq * 11) % 99991)
        dr = drift_cents * (rng.random() - 0.5) * 2
        f = freq * 2 ** (dr / 1200.0)
        idx = (0.6 + 2.0 * vel * bright) * np.exp(-t / 0.35) + 0.15
        body = fm(f, n, 1.0, 1.0, idx)
        tine = fm(f, n, 14.0, 1.0 + vel, np.exp(-t / 0.012)) * (0.18 + 0.25 * bright) * vel
        bell = np.sin(TAU * f * 3.0 * t) * np.exp(-t / 0.15) * 0.08 * bright
        x = body + tine + bell
        if bark:
            d = 1.0 + bark * 3.0 * vel
            x = np.tanh(x * d) / math.tanh(d)
        dec = 1.4 + 260.0 / max(freq, 60.0)
        env = np.exp(-t / dec) * adsr(n, gate, 0.0015, 1.0, 1.0, release, sr)
        x = (x * env).astype(F32)
        tr = tremolo * np.sin(TAU * trem_rate * t + rng.random() * TAU)
        st = np.stack([x * (1.0 + tr), x * (1.0 - tr)], axis=1)
        return _finish(st, vel, rel_fade=256)
    return inst


def m1_organ(bright=0.6, decay=0.28, sustain=0.18, release=0.07, click=0.25, sr=SR):
    """90s 'M1-style' house/garage organ stab: additive organ partials with faster decay on the
    upper ones, key click, light chorus. Stereo."""
    partials = [(1.0, 1.0, 1.0), (2.0, 0.75, 0.8), (3.0, 0.5 * bright, 0.6), (4.0, 0.42 * bright, 0.45),
                (6.0, 0.2 * bright, 0.35), (8.0, 0.12 * bright, 0.25)]

    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        x = np.zeros(n)
        for r, a, dk in partials:
            if freq * r < 15000:
                x += a * np.sin(TAU * freq * r * t + r) * (sustain + (1 - sustain) * np.exp(-t / (decay * dk)))
        nc = min(n, int(0.006 * sr))
        ck = np.zeros(n)
        ck[:nc] = bp(white(nc, np.random.default_rng(int(freq))), 1500.0, 6000.0) * np.exp(-np.arange(nc) / sr / 0.0015)
        x = x + click * ck * 3.0
        env = adsr(n, gate, 0.002, 0.2, 1.0, release, sr)
        y = chorus((x * env).astype(F32), 0.8, 1.2, 7.0, 0.35)
        return _finish(y, vel)
    return inst


def dread_bass(detune_cents=14.0, cutoff=280.0, env_amt=1400.0, decay=0.11, bend=7.0, bend_ms=70.0,
               res=0.3, drive=2.4, sub=0.7, release=0.04, sr=SR):
    """Speed-garage 'dread' bass: two detuned saws + sine sub, pitch scooping down ``bend``
    semitones into the note ('bwomp'), filter envelope, driven ladder."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        f = freq * 2.0 ** (bend * np.exp(-t / (bend_ms * 1e-3)) / 12.0)
        a = saw(f * 2 ** (detune_cents / 1200), n)
        b = saw(f * 2 ** (-detune_cents / 1200), n, 0.4)
        cut = cutoff + env_amt * vel * np.exp(-t / decay)
        x = ladder((a + b) * 0.45, cut, res, drive) + sub * sine(f, n)
        env = adsr(n, gate, 0.003, 0.25, 0.8, release, sr)
        return _finish(x * env, vel, rel_fade=128)
    return inst


def soft_bass(tone=0.35, attack=0.012, release=0.12, sr=SR):
    """Mellow round bass (lo-fi / liquid): sine + soft triangle, low-passed, gentle attack."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        x = sine(freq, n) + tone * triangle(freq, n) * 0.6 + 0.1 * sine(2 * freq, n)
        x = lp(x, 900.0, 2)
        x = np.tanh(x * 1.3) / math.tanh(1.3)
        env = adsr(n, gate, attack, 0.6, 0.75, release, sr, curve=3.0)
        return _finish(x * env, vel, rel_fade=256)
    return inst


def flute(breath=0.18, vibrato=0.18, attack=0.06, release=0.15, sr=SR):
    """Soft breathy flute-like lead (lo-fi melody): sine + 2nd/3rd harmonics + band-passed breath."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        vib = vibrato * np.sin(TAU * 5.0 * t) * np.clip((t - 0.15) / 0.3, 0, 1)
        f = freq * 2 ** (vib / 12)
        x = sine(f, n) + 0.22 * sine(2 * f, n) + 0.07 * sine(3 * f, n)
        nz = svf(white(n, np.random.default_rng(int(freq))), freq * 2.0, 2.0, "bp") * breath * 3
        env = adsr(n, gate, attack, 0.3, 0.85, release, sr, curve=3.0)
        return _finish((x + nz) * env, vel, rel_fade=256)
    return inst


# ============================================================================ one-shot FX
def zap(dur=0.2, f_hi=5000.0, f_lo=70.0, index=3.0, sr=SR):
    """Fast exponential FM down-sweep ('psy zap')."""
    n = int(dur * sr)
    t = np.arange(n) / sr
    f = f_lo * (f_hi / f_lo) ** np.exp(-t / (dur * 0.2))
    ph = TAU * np.cumsum(f) / sr
    x = np.sin(ph + index * np.sin(ph * 1.5) * np.exp(-t / (dur * 0.3))) * np.exp(-t / (dur * 0.35))
    return normalize(fade(x.astype(F32), 8, int(0.004 * sr)))


def laser_up(dur=0.5, f_lo=200.0, f_hi=6000.0, index=2.0, sr=SR):
    """Rising FM sweep (laser / tension zap)."""
    n = int(dur * sr)
    t = np.linspace(0, 1, n)
    f = f_lo * (f_hi / f_lo) ** (t ** 2)
    ph = TAU * np.cumsum(f) / sr
    x = np.sin(ph + index * np.sin(ph * 0.5)) * (t ** 1.5)
    return normalize(fade(x.astype(F32), int(0.005 * sr), int(0.01 * sr)))


def pitch_dive(dur=2.0, f0=1800.0, f1=45.0, res_q=4.0, rng=None, sr=SR):
    """Long twisted pitch dive: FM'd saw falling from ``f0`` to ``f1`` through a resonant filter
    that follows it, plus a noise tail. Stereo."""
    rng = rng if rng is not None else np.random.default_rng(9)
    n = int(dur * sr)
    t = np.linspace(0, 1, n)
    f = f1 * (f0 / f1) ** ((1 - t) ** 1.8)
    x = saw(f, n) * 0.6 + fm(f, n, 1.5, 2.5 * (1 - t))
    x = svf(x, np.clip(f * 3.0, 60, 12000), res_q, "lp")
    nz = svf(white(n, rng), np.clip(f * 6, 100, 15000), 1.5, "bp") * 0.4
    y = (x + nz) * (1 - t) ** 0.6
    st = np.stack([y, np.roll(y, int(0.007 * sr))], axis=1)
    return normalize(fade(st.astype(F32), int(0.004 * sr), int(0.05 * sr)))


def siren(dur=1.0, f0=600.0, depth=0.5, rate=4.0, sr=SR):
    """Classic rave siren / pitch-wobble tone (dubstep / breaks builds)."""
    n = int(dur * sr)
    t = np.arange(n) / sr
    f = f0 * 2 ** (depth * np.sin(TAU * rate * t))
    x = square(f, n, 0.0, 0.5) * 0.5 + saw(f * 1.005, n) * 0.5
    x = svf(x, 3000.0, 0.8, "lp")
    return normalize(fade(x.astype(F32), int(0.01 * sr), int(0.05 * sr)))


def scratch(src, bpm, kind="baby", beats=1.0, rng=None, sr=SR):
    """Turntable scratch of a (synthesised) source sound.

    The 'record' position follows hand strokes (eased back-and-forth moves); playback speed is the
    derivative, so pitch and level follow the hand like real vinyl. ``kind``: ``baby`` (forward +
    back), ``chirp`` (fader cuts the back-stroke), ``transformer`` (fader chops), ``scribble``.
    Returns stereo of length ``beats`` beats."""
    rng = rng if rng is not None else np.random.default_rng(12)
    src = as_mono(src).astype(np.float64)
    L = src.shape[0]
    n = int(beats * 60.0 / bpm * sr)
    t = np.arange(n) / sr
    beat = 60.0 / bpm
    if kind == "scribble":
        stroke = beat / 8
    elif kind == "transformer":
        stroke = beat / 2
    else:
        stroke = beat / 4
    span = min(L - 2, int(0.18 * sr * (stroke / (beat / 4))))
    ph = (t / stroke) % 2.0
    pos = np.where(ph < 1.0, 0.5 - 0.5 * np.cos(np.pi * ph), 0.5 + 0.5 * np.cos(np.pi * (ph - 1.0)))
    if kind == "scribble":
        pos = 0.5 + 0.12 * np.sin(TAU * t / stroke) + 0.38 * (t / t[-1])
    p = pos * span + 0.01 * sr
    y = np.interp(p, np.arange(L), src)
    speed = np.abs(np.gradient(p)) + 1e-3
    y = y * np.clip(speed, 0, 2.0) ** 0.6
    if kind == "chirp":
        y = y * np.where(ph < 1.0, 1.0, np.clip((ph - 1.0) * 8, 0, 1) * 0.0)
    elif kind == "transformer":
        gate = (np.floor(t / (beat / 8)) % 2 == 0).astype(np.float64)
        gate = signal.lfilter([0.15], [1, -0.85], gate)
        y = y * gate
    y = svf(y.astype(F32), np.clip(1500 + 5000 * np.clip(speed, 0, 1.5), 500, 12000), 0.8, "lp")
    y = hp(y, 180.0, 2)
    y = np.tanh(y * 2.0)
    st = np.stack([y, np.roll(y, int(0.004 * sr))], axis=1)
    return normalize(fade(st.astype(F32), int(0.002 * sr), int(0.01 * sr)))


# ============================================================================ speech-like texture
_VOWELS = {
    "a": (730, 1090, 2440, 3400), "e": (530, 1840, 2480, 3500), "i": (300, 2250, 3000, 3700),
    "o": (570, 840, 2410, 3400), "u": (320, 870, 2240, 3300), "ae": (660, 1720, 2410, 3400),
    "uh": (520, 1190, 2390, 3400), "er": (490, 1350, 1690, 3300),
}
_VGAIN = (1.0, 0.55, 0.28, 0.12)
_VQ = (6.0, 9.0, 12.0, 14.0)


def speechy(dur_sec, rng, f0=105.0, shift=1.0, rate=1.0, breath=0.12, radio=True, density=1.0, sr=SR):
    """Spoken-word-like *gibberish*: syllables with vowel glides, consonant noise, falling phrase
    intonation and pauses — the texture of a psytrance 'spoken sample', but no real words.
    ``density`` < 1 → longer pauses. Mono, peak 1."""
    n = int(dur_sec * sr)
    names = list(_VOWELS)
    syl = []
    t = float(rng.uniform(0.0, 0.2))
    while t < dur_sec - 0.5:
        p_start = t
        items = []
        for _ in range(int(rng.integers(3, 7))):
            for _ in range(int(rng.integers(1, 4))):
                L = float(rng.uniform(0.09, 0.2)) / rate
                if t + L > dur_sec - 0.1:
                    break
                cons = str(rng.choice(["", "", "s", "t", "k", "sh", "f", "p"]))
                items.append([t, L, names[int(rng.integers(len(names)))], names[int(rng.integers(len(names)))],
                              bool(rng.random() < 0.3), cons])
                t += L
            t += float(rng.uniform(0.04, 0.14)) / rate
        p_end = max(t, p_start + 0.1)
        base = f0 * float(rng.uniform(0.92, 1.12))
        for it in items:
            it.append((it[0] - p_start) / (p_end - p_start))
            it.append(base)
        syl += items
        t += float(rng.uniform(0.35, 0.9)) / max(density, 0.2)
    amp = np.zeros(n)
    form = [np.full(n, float(v)) for v in _VOWELS["uh"]]
    pitch = np.full(n, f0)
    cons_buf = np.zeros(n)
    for t0, L, v1, v2, stress, cons, prog, base in syl:
        i0, i1 = int(t0 * sr), min(n, int((t0 + L) * sr))
        m = i1 - i0
        if m <= 8:
            continue
        k = np.arange(m)
        att, rel = int(0.014 * sr), int(0.035 * sr)
        env = np.minimum(1.0, k / att) * np.minimum(1.0, (m - k) / rel) * (1.25 if stress else 1.0)
        amp[i0:i1] = np.maximum(amp[i0:i1], env)
        r = k / m
        for j in range(4):
            form[j][i0:i1] = _VOWELS[v1][j] + (_VOWELS[v2][j] - _VOWELS[v1][j]) * r
        p = base * (1.14 - 0.3 * prog) * (1.07 if stress else 1.0) * (1 + 0.04 * np.sin(np.pi * r))
        pitch[i0:i1] = p
        if cons:
            cl = int((0.07 if cons in ("s", "sh", "f") else 0.018) * sr)
            c0 = max(0, i0 - cl // 2)
            c1 = min(n, c0 + cl)
            kk = np.arange(c1 - c0) / sr
            nz = white(c1 - c0, rng).astype(np.float64)
            fc = {"s": 6500.0, "sh": 3000.0, "f": 5000.0, "t": 4000.0, "k": 2200.0, "p": 900.0}[cons]
            nz = np.asarray(svf(nz, fc, 1.2 if cons in ("s", "sh", "f") else 0.8, "bp"), dtype=np.float64)
            shape = np.exp(-kk / (0.02 if cons in ("s", "sh", "f") else 0.006))
            cons_buf[c0:c1] += nz * shape * (0.5 if cons in ("s", "sh", "f") else 0.9)
    # smooth formant / pitch trajectories (articulators don't jump)
    a1 = math.exp(-1.0 / (0.018 * sr))
    form = [signal.lfilter([1 - a1], [1, -a1], f - f[0]) + f[0] for f in form]
    pitch = signal.lfilter([1 - a1], [1, -a1], pitch - pitch[0]) + pitch[0]
    jit = signal.lfilter([0.002], [1, -0.998], np.asarray(white(n, rng), dtype=np.float64))
    pitch = pitch * (1.0 + 0.6 * jit)
    amp = signal.lfilter([1 - math.exp(-1 / (0.004 * sr))], [1, -math.exp(-1 / (0.004 * sr))], amp)
    src = saw(pitch, n) * 0.85 + breath * white(n, rng)
    src = lp(src, 4200.0, 2)
    voiced = np.zeros(n)
    for j in range(4):
        voiced += np.asarray(svf(src, np.clip(form[j] * shift, 80, 9000), _VQ[j], "bp"), dtype=np.float64) * _VGAIN[j]
    y = voiced * amp + cons_buf * 0.6 * (np.max(np.abs(voiced)) + 1e-6)
    y = y.astype(F32)
    if radio:
        y = bp(y, 260.0, 3900.0, 2)
        y = np.tanh(normalize(y) * 1.8).astype(F32)
    return normalize(fade(y, int(0.005 * sr), int(0.05 * sr)))


# ============================================================================ per-bar textures
def bar_texture(gen, seed: int, when=None, tail_bars: int = 1):
    """Custom-layer function rendering a texture bar by bar: ``gen(bar, n_bar_samples, rng)`` returns
    mono/stereo audio (may be longer than the bar = tail). Each bar's rng is derived from ``seed`` and
    the bar index, so any render window gives identical samples. ``when(ctx)`` gates bars."""
    def fn(song, a, b):
        g = song.grid
        bar_n = g.bar_sec * g.sr
        b0 = max(0, int(a // bar_n) - tail_bars)
        b1 = min(song.total_bars, int(math.ceil(b / bar_n)) + 1)
        out = np.zeros((b - a, 2), dtype=F32)
        hit = False
        for bar in range(b0, b1):
            if when is not None and not when(song.ctx(bar)):
                continue
            s = g.bar_sample(bar)
            nb = g.bar_sample(bar + 1) - s
            y = gen(bar, nb, np.random.default_rng((int(seed) * 1_000_003 + bar * 7919 + 17) % (2 ** 32)))
            if y is None:
                continue
            y = as_stereo(y)
            if s - a >= out.shape[0] or s - a + y.shape[0] <= 0:
                continue
            mix_into(out, y, s - a)
            hit = True
        return out if hit else None
    return fn


def rain_bar(n, rng, density=14.0, bed=0.1, drops=1.0, sr=SR):
    """One bar of synthetic rain: filtered noise bed + random bubble-like droplets. Stereo."""
    m = n + int(0.12 * sr)
    out = np.zeros((m, 2), dtype=np.float64)
    if bed:
        for c in range(2):
            nz = pink(m, rng).astype(np.float64)
            out[:, c] += np.asarray(bp(nz, 500.0, 7000.0, 2), dtype=np.float64) * bed
    k = int(rng.poisson(density * n / sr))
    for _ in range(k):
        pos = int(rng.integers(0, n))
        f0 = float(rng.uniform(1300, 4800))
        d = float(rng.uniform(0.006, 0.025))
        L = min(m - pos, int(d * 5 * sr))
        if L < 16:
            continue
        tt = np.arange(L) / sr
        f = f0 * (1.0 + 0.8 * tt / (d * 5))
        y = np.sin(TAU * np.cumsum(f) / sr) * np.exp(-tt / d) * float(rng.uniform(0.15, 1.0)) * drops
        p = float(rng.uniform(-0.9, 0.9))
        out[pos:pos + L, 0] += y * math.cos((p + 1) * math.pi / 4) * 1.41
        out[pos:pos + L, 1] += y * math.sin((p + 1) * math.pi / 4) * 1.41
    return out.astype(F32)


def crackle_bar(n, rng, density=9.0, pops=0.35, hiss=0.05, sr=SR):
    """One bar of vinyl surface noise: sparse soft clicks (stereo-scattered), occasional low pops and
    a faint band-passed hiss. Stereo, roughly peak 1 for loud clicks."""
    m = n + 512
    imp = np.zeros((m, 2))
    k = int(rng.poisson(density * n / sr))
    if k:
        pos = rng.integers(0, n, k)
        amp = np.minimum(1.0, 0.06 + rng.pareto(3.0, k) * 0.1) * rng.choice([-1.0, 1.0], k)
        side = rng.random(k)
        imp[pos, 0] += amp * (side < 0.75)
        imp[pos, 1] += amp * (side > 0.25)
    kern = np.array([1.0, -0.55, 0.25, -0.1, 0.03])
    y = np.stack([np.convolve(imp[:, c], kern)[:m] for c in range(2)], axis=1)
    y = np.asarray(lp(hp(y.astype(F32), 500.0, 2), 7500.0, 2), dtype=np.float64)
    kp = int(rng.poisson(pops * n / sr))
    for _ in range(kp):
        p0 = int(rng.integers(0, n))
        L = min(m - p0, int(0.004 * sr))
        tt = np.arange(L) / sr
        y[p0:p0 + L] += (np.sin(TAU * 900 * tt) * np.exp(-tt / 0.0008) * float(rng.uniform(0.3, 0.8)))[:, None]
    if hiss:
        h = np.stack([np.asarray(bp(pink(m, rng), 1500.0, 9000.0, 2), dtype=np.float64) for _ in range(2)], axis=1)
        y += h * hiss
    return y.astype(F32)


# ============================================================================ inserts
def tape_wobble(depth_ms=0.8, rate=0.55, flutter_ms=0.05, flutter_rate=7.0, base_ms=4.0, sr=SR):
    """Layer insert: wow (slow, two incommensurate LFOs) + flutter pitch wobble via a modulated delay."""
    def f(x):
        xs = as_stereo(x)
        n = xs.shape[0]
        t = np.arange(n) / sr
        d = (base_ms + depth_ms * np.sin(TAU * rate * t) + 0.4 * depth_ms * np.sin(TAU * rate * 0.37 * t + 1.3)
             + flutter_ms * np.sin(TAU * flutter_rate * t))
        return np.stack([np.asarray(mod_delay(xs[:, c], d, sr), dtype=F32) for c in range(2)], axis=1)
    return f


# ============================================================================ grid-locked mono line layer
_W = re.compile(r"w(\d+(?:\.\d+)?)")


def _div(flags: str) -> float:
    m = _W.search(flags or "")
    return float(m.group(1)) if m else 0.0


class SynthLine(Notes):
    """Monophonic bass-line layer whose voice gets **absolute** sample positions, so tempo-synced
    LFOs (wobbles) and slow movement stay locked to the song grid in previews and full renders.

    Notes: ``(step, length, midi, vel[, flags])``; flags: ``s`` slide into the next note, ``a`` accent,
    ``w<N>`` LFO at N cycles per bar (``w8`` = 1/8 notes, ``w16`` = 1/16, ``w12`` = 1/8 triplets,
    ``w6`` = 1/4 triplets, ``w4`` = quarters, ``w2`` = halves). Automatable: ``cutoff`` (multiplier on
    the voice's filter), ``drive``."""

    def __init__(self, name, synth, notes, bus="bass", **kw):
        super().__init__(name, instrument=None, notes=notes, bus=bus, **kw)
        self.synth = synth

    def render_dry(self, song, a, b):
        evs = sorted(self.note_events(song, a, b, lookback=2), key=lambda e: e[0])
        if not evs:
            return None

        def curve(param, s, e):
            if param not in self.auto:
                return None
            return self.curve(song, param, s, e)

        return self.synth.render(song, evs, a, b, curve)


class LineVoice:
    """Base voice for :class:`SynthLine`: splits notes into runs, builds per-sample pitch/gate/LFO
    arrays and calls :meth:`voice`."""

    glide_ms = 45.0
    release_ms = 12.0
    attack_ms = 2.0
    tail_ms = 40.0
    legato_glide = True
    lfo_shape = "sine"

    def render(self, song, evs, a, b, curve):
        sr = song.sr
        n = b - a
        out = np.zeros((n, 2), dtype=F32)
        tail = int((self.release_ms + self.tail_ms) * 1e-3 * sr)
        runs, cur, last_end = [], [], 0
        for ev in evs:
            pos, length = int(ev[0]), int(ev[1])
            if cur and pos - last_end > int(0.1 * sr):
                runs.append(cur)
                cur = []
            last_end = pos + length if not cur else max(last_end, pos + length)
            cur.append(ev)
        if cur:
            runs.append(cur)
        hit = False
        for run in runs:
            s0 = int(run[0][0])
            e0 = max(int(p) + int(l) for p, l, *_ in run) + tail
            lo, hi = max(s0, a), min(e0, b)
            if hi <= lo:
                continue
            arr = self._arrays(song, run, s0, e0)
            y = as_stereo(self.voice(song, arr, s0, e0, curve))
            mix_into(out, y[lo - s0:hi - s0], lo - a)
            hit = True
        return out if hit else None

    def _arrays(self, song, run, s0, e0):
        sr = song.sr
        m = e0 - s0
        f = np.zeros(m)
        gate = np.zeros(m)
        age = np.zeros(m)
        vel = np.zeros(m)
        div = np.zeros(m)
        acc = np.zeros(m)
        gl = max(1, int(self.glide_ms * 1e-3 * sr))
        prev_hz, prev_slide, prev_end = None, False, -1
        for i, ev in enumerate(run):
            pos, length, midi, v = int(ev[0]), int(ev[1]), ev[2], ev[3]
            flags = ev[4] if len(ev) > 4 else ""
            s = pos - s0
            e = (int(run[i + 1][0]) - s0) if i + 1 < len(run) else m
            seg = e - s
            if seg <= 0:
                continue
            hzv = midi_hz(midi)
            k = np.arange(seg)
            legato = prev_hz is not None and (prev_slide or (self.legato_glide and s < prev_end))
            if legato:
                g = min(gl, seg)
                lf = np.full(seg, math.log(hzv))
                lf[:g] = math.log(prev_hz) + (math.log(hzv) - math.log(prev_hz)) * (k[:g] / g)
                f[s:e] = np.exp(lf)
                base = age[s - 1] if s > 0 else 0.0
                age[s:e] = base + (k + 1) / sr
            else:
                f[s:e] = hzv
                age[s:e] = k / sr
            slide = "s" in flags
            g_end = e if slide else min(e, s + length)
            gate[s:g_end] = 1.0
            vel[s:e] = v
            div[s:e] = _div(flags)
            acc[s:e] = 1.0 if "a" in flags else 0.0
            prev_hz, prev_slide, prev_end = hzv, slide, s + length
        f[f <= 0] = 40.0
        att = math.exp(-1.0 / max(1.0, self.attack_ms * 1e-3 * sr))
        rel = math.exp(-1.0 / max(1.0, self.release_ms * 1e-3 * sr / 3.0))
        gs = _gate_smooth(gate, att, rel)
        bar_n = song.grid.bar_sec * sr
        idx = s0 + np.arange(m)
        phase = (idx / bar_n * div) % 1.0
        if self.lfo_shape == "saw":
            lfo = 1.0 - phase
        elif self.lfo_shape == "tri":
            lfo = 1.0 - np.abs(2.0 * phase - 1.0)
        else:
            lfo = 0.5 - 0.5 * np.cos(TAU * phase)
        lfo = np.where(div > 0, lfo, np.exp(-age / 0.18))
        return {"f": f, "gate": gs, "age": age, "vel": vel, "div": div, "acc": acc, "lfo": lfo, "m": m,
                "t_abs": idx / sr, "bar_n": bar_n}

    def voice(self, song, A, s0, e0, curve):  # pragma: no cover - abstract
        raise NotImplementedError


@njit(cache=True)
def _asym_smooth(g, att, rel):
    y = np.empty_like(g)
    cur = 0.0
    for i in range(g.shape[0]):
        target = g[i]
        c = att if target > cur else rel
        cur = target + (cur - target) * c
        y[i] = cur
    return y


def _gate_smooth(g, att, rel):
    """One-pole gate smoothing with separate attack / release coefficients (no clicks)."""
    return _asym_smooth(np.ascontiguousarray(g, dtype=np.float64), float(att), float(rel))


def _curve_or(curve, name, s0, e0, default):
    c = curve(name, s0, e0)
    return default if c is None else c


class Wobble(LineVoice):
    """Dubstep wobble: saw + square + FM through a driven ladder whose cutoff follows a tempo-synced
    LFO (rate from note flag ``w<N>``), vowel-formant blend ('wow/yoi'), distortion, HP (the sub is a
    separate :class:`SubLine`)."""

    def __init__(self, cut_lo=110.0, cut_hi=3200.0, res=0.5, drive=2.5, dist=0.55, fm_amt=1.6, vowel=0.45,
                 hp_hz=95.0, chorus_mix=0.3, shape="sine"):
        self.cut_lo, self.cut_hi, self.res, self.drive = cut_lo, cut_hi, res, drive
        self.dist, self.fm_amt, self.vowel, self.hp_hz, self.chorus_mix = dist, fm_amt, vowel, hp_hz, chorus_mix
        self.lfo_shape = shape
        self.glide_ms = 30.0

    def voice(self, song, A, s0, e0, curve):
        m, f, l = A["m"], A["f"], A["lfo"]
        osc = 0.55 * saw(f, m) + 0.4 * square(f * 1.004, m, 0.3, 0.5) + 0.25 * saw(f * 2.0, m, 0.6)
        osc = osc + 0.6 * fm(f, m, 1.0, 1.0, self.fm_amt * l + 0.1)
        mult = _curve_or(curve, "cutoff", s0, e0, 1.0)
        cut = np.clip(self.cut_lo * (self.cut_hi / self.cut_lo) ** (l ** 1.2) * mult, 40, 15000)
        y = np.asarray(ladder((osc * 0.55).astype(F32), cut, self.res, self.drive), dtype=np.float64)
        if self.vowel:
            f1 = 380 + 450 * l
            f2 = 750 + 1100 * l
            vf = np.asarray(svf(y, f1, 5.0, "bp"), dtype=np.float64) + 0.7 * np.asarray(svf(y, f2, 7.0, "bp"), dtype=np.float64)
            y = (1 - self.vowel) * y + self.vowel * vf * 2.2
        d = 1.0 + self.dist * 5.0
        y = np.tanh(y * d) / math.tanh(d)
        y = y * A["gate"] * A["vel"] * (1 + 0.25 * A["acc"])
        y = hp(y.astype(F32), self.hp_hz, 2)
        y = lp(y, 9000.0, 2)
        if self.chorus_mix:
            return chorus(y, 0.7, 1.6, 8.0, self.chorus_mix)
        return y


class Growl(LineVoice):
    """Growl / talking FM bass: feedback FM whose index and a 3-formant vowel filter ('o'→'a'→'e')
    follow the synced LFO, heavy saturation, HP. Stereo via short chorus."""

    def __init__(self, ratio=1.0, index=4.5, feedback=0.7, shift=1.0, dist=0.7, hp_hz=110.0, vowels=("o", "a", "e"),
                 chorus_mix=0.25, lp_hz=6000.0):
        self.ratio, self.index, self.feedback, self.shift, self.lp_hz = ratio, index, feedback, shift, lp_hz
        self.dist, self.hp_hz, self.vowels, self.chorus_mix = dist, hp_hz, vowels, chorus_mix
        self.glide_ms = 25.0
        self.lfo_shape = "tri"

    def voice(self, song, A, s0, e0, curve):
        m, f, l = A["m"], A["f"], A["lfo"]
        x = fm(f, m, self.ratio, 1.0, 0.6 + self.index * l, self.feedback)
        x = x + 0.35 * saw(f, m)
        x = np.tanh(x * 2.5)
        v0, v1, v2 = (_VOWELS[v] for v in self.vowels)
        y = np.zeros(m)
        for j in range(3):
            fa = np.where(l < 0.5, v0[j] + (v1[j] - v0[j]) * (l * 2), v1[j] + (v2[j] - v1[j]) * (l * 2 - 1))
            y += np.asarray(svf(x, np.clip(fa * self.shift, 80, 9000), _VQ[j] * 0.8, "bp"), dtype=np.float64) * _VGAIN[j]
        y = y * 2.5 + 0.25 * x
        d = 1.0 + self.dist * 5.0
        y = np.tanh(y * d) / math.tanh(d)
        y = y * A["gate"] * A["vel"]
        y = hp(y.astype(F32), self.hp_hz, 2)
        y = lp(y, self.lp_hz, 2)
        return chorus(y, 0.9, 1.2, 6.0, self.chorus_mix) if self.chorus_mix else y


class Reese(LineVoice):
    """Reese bass with movement: 3 detuned saws with drifting detune (phasing), ladder LP that
    breathes with a slow LFO (``move_bars`` per cycle) + note envelope, soft drive, stereo chorus.
    HP'd at ``hp_hz`` (pair it with a :class:`SubLine`)."""

    def __init__(self, detune=17.0, cutoff=650.0, res=0.25, drive=2.0, move=0.55, move_bars=2.0, env=1.2,
                 chorus_mix=0.35, hp_hz=75.0, dist=0.3):
        self.detune, self.cutoff, self.res, self.drive = detune, cutoff, res, drive
        self.move, self.move_bars, self.env, self.chorus_mix = move, move_bars, env, chorus_mix
        self.hp_hz, self.dist = hp_hz, dist
        self.glide_ms = 70.0
        self.release_ms = 25.0

    def voice(self, song, A, s0, e0, curve):
        m, f, tabs = A["m"], A["f"], A["t_abs"]
        d = self.detune * (1.0 + 0.35 * np.sin(TAU * 0.11 * tabs))
        x = (saw(f * 2 ** (d / 1200), m) + saw(f * 2 ** (-d / 1200), m, 0.37)
             + 0.6 * saw(f * 2 ** (0.45 * d / 1200), m, 0.71) + 0.3 * saw(f * 2.0 * 2 ** (-0.3 * d / 1200), m, 0.2))
        mv = 0.5 - 0.5 * np.cos(TAU * (s0 + np.arange(m)) / (A["bar_n"] * self.move_bars))
        base = _curve_or(curve, "cutoff", s0, e0, self.cutoff)
        cut = np.clip(base * 2 ** (self.move * 2.0 * (mv - 0.5)) * (1.0 + self.env * np.exp(-A["age"] / 0.12)), 40, 14000)
        y = np.asarray(ladder((x * 0.4).astype(F32), cut, self.res, self.drive), dtype=np.float64)
        if self.dist:
            dd = 1.0 + self.dist * 4
            y = np.tanh(y * dd) / math.tanh(dd)
        y = y * A["gate"] * A["vel"]
        y = hp(y.astype(F32), self.hp_hz, 2)
        return chorus(y, 0.35, 2.5, 9.0, self.chorus_mix) if self.chorus_mix else y


class SubLine(LineVoice):
    """Clean sine sub that follows the same notes (glides included), slight 2nd harmonic + soft drive."""

    def __init__(self, harm=0.12, drive=1.3, glide_ms=60.0, release_ms=18.0):
        self.harm, self.drive = harm, drive
        self.glide_ms, self.release_ms = glide_ms, release_ms

    def voice(self, song, A, s0, e0, curve):
        m, f = A["m"], A["f"]
        y = np.asarray(sine(f, m), dtype=np.float64) + self.harm * np.asarray(sine(f * 2.0, m), dtype=np.float64)
        y = np.tanh(y * self.drive) / math.tanh(self.drive)
        y = y * A["gate"] * A["vel"]
        return y.astype(F32)


def gate_fx(pattern: str, bpm: float, depth=1.0, smooth_ms=4.0, sr=SR):
    """Layer insert: 16-step trance gate. Assumes the buffer starts on a bar line (true for full
    renders; previews start on a bar too)."""
    steps = [ch != "." for ch in pattern]
    step_n = 60.0 / bpm / 4 * sr

    def f(x):
        xs = as_stereo(x)
        n = xs.shape[0]
        idx = (np.arange(n) / step_n).astype(np.int64) % len(steps)
        g = np.array(steps, dtype=np.float64)[idx]
        a = math.exp(-1.0 / (smooth_ms * 1e-3 * sr))
        g = signal.lfilter([1 - a], [1, -a], g)
        g = 1.0 - depth * (1.0 - g)
        return (xs * g[:, None]).astype(F32)
    return f


__all__ = [k for k in dir() if not k.startswith("_")]
