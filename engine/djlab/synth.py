"""Synthesis building blocks: oscillators, unison/supersaw, FM, noise, wavetable morphing,
envelopes, LFOs, glide, filters (re-exported from :mod:`djlab.dsp`).

All functions return float32 numpy arrays. Mono = ``(n,)``, stereo = ``(n, 2)``.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import signal

from . import SR
from .dsp import (F32, as_mono, as_stereo, bp, dc_block, eq_highshelf, eq_lowshelf, eq_peak, fade, hp,  # noqa: F401
                  karplus, ladder, lp, normalize, onepole_hp, onepole_lp, pan, param_array, saw, sine, square,
                  svf, svf24, triangle)


def midi_hz(m):
    return 440.0 * 2.0 ** ((np.asarray(m, dtype=np.float64) - 69.0) / 12.0)


# ----------------------------------------------------------------------------- noise
def white(n, rng=None):
    rng = rng or np.random.default_rng(0)
    return rng.uniform(-1.0, 1.0, n).astype(F32)


def pink(n, rng=None):
    """Pink noise (Paul Kellet economy filter on white noise), normalised to peak 1."""
    w = white(n, rng)
    b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
    a = [1, -2.494956002, 2.017265875, -0.522189400]
    return normalize(signal.lfilter(b, a, w).astype(F32))


def brown(n, rng=None):
    w = white(n, rng)
    y = signal.lfilter([1.0], [1.0, -0.995], w)
    return normalize(dc_block(y.astype(F32)))


# ----------------------------------------------------------------------------- envelopes
def ad(n, attack=0.002, decay=0.3, curve=4.0, sr=SR):
    """Attack/decay envelope of length n. ``decay`` is the time to reach ~-60 dB when curve≈7,
    lower curve = slower falloff. Exponential decay ``exp(-curve * t / decay)``."""
    t = np.arange(n) / sr
    a = max(attack, 1e-5)
    env = np.where(t < a, t / a, np.exp(-curve * (t - a) / max(decay, 1e-5)))
    return env.astype(F32)


def adsr(n_total, gate, attack=0.005, decay=0.1, sustain=0.7, release=0.1, sr=SR, curve=5.0):
    """Sample-accurate ADSR. ``gate`` = number of samples the key is held; release starts exactly
    at ``gate`` from the level reached at that moment. Output length ``n_total``."""
    n_total = int(n_total)
    gate = int(min(gate, n_total))
    t = np.arange(n_total) / sr
    a = max(attack, 1e-5)
    d = max(decay, 1e-5)
    env = np.where(t < a, t / a, sustain + (1 - sustain) * np.exp(-curve * (t - a) / d))
    if gate < n_total:
        level = env[gate - 1] if gate > 0 else 0.0
        tr = t[gate:] - t[gate]
        env[gate:] = level * np.exp(-curve * tr / max(release, 1e-5))
    return env.astype(F32)


def note_env(n, gate, attack=0.003, decay=0.2, sustain=0.6, release=0.03, sr=SR):
    """ADSR + 1 ms anti-click fades at both ends."""
    e = adsr(n, gate, attack, decay, sustain, release, sr)
    return fade(e, 0, min(64, n))


def lfo(n, rate_hz, shape="sine", phase=0.0, sr=SR):
    """Bipolar LFO in [-1, 1]. Shapes: sine, tri, saw, square, ramp."""
    t = np.arange(n) / sr
    ph = (rate_hz * t + phase) % 1.0
    if shape == "sine":
        y = np.sin(2 * np.pi * ph)
    elif shape == "tri":
        y = 1 - 4 * np.abs(ph - 0.5)
    elif shape == "saw":
        y = 2 * ph - 1
    elif shape == "ramp":
        y = 1 - 2 * ph
    elif shape == "square":
        y = np.where(ph < 0.5, 1.0, -1.0)
    else:
        raise ValueError(shape)
    return y.astype(F32)


def lfo_sync(n, bpm, beats=1.0, shape="sine", phase=0.0, sr=SR):
    """Tempo-synced LFO, one cycle per ``beats`` beats."""
    return lfo(n, bpm / 60.0 / beats, shape, phase, sr)


def glide(freqs_per_sample_target, glide_ms, sr=SR):
    """Portamento: one-pole smoothing (in log-frequency) of a stepwise per-sample target."""
    tgt = np.log(np.maximum(np.asarray(freqs_per_sample_target, dtype=np.float64), 1.0))
    if glide_ms <= 0:
        return np.exp(tgt)
    a = math.exp(-1.0 / (glide_ms * 1e-3 * sr))
    y = signal.lfilter([1 - a], [1, -a], tgt - tgt[0]) + tgt[0]
    return np.exp(y)


def pitch_env(n, start_ratio=2.0, time=0.03, sr=SR):
    """Multiplicative pitch envelope decaying exponentially from ``start_ratio`` to 1."""
    t = np.arange(n) / sr
    return (1.0 + (start_ratio - 1.0) * np.exp(-t / max(time, 1e-5))).astype(np.float64)


# ----------------------------------------------------------------------------- composite oscillators
def unison(osc_fn, freq, n, voices=3, detune_cents=12.0, spread=0.8, rng=None, sr=SR):
    """Unison of ``voices`` detuned copies of ``osc_fn(freq, n, phase)``, stereo spread."""
    rng = rng or np.random.default_rng(1)
    out = np.zeros((n, 2), dtype=F32)
    if voices == 1:
        return as_stereo(osc_fn(freq, n, rng.random()))
    for v in range(voices):
        pos = (v / (voices - 1)) * 2 - 1  # -1..1
        cents = pos * detune_cents
        f = np.asarray(freq) * 2 ** (cents / 1200.0)
        x = osc_fn(f, n, rng.random())
        out += pan(x, pos * spread)
    return (out / math.sqrt(voices)).astype(F32)


_SUPERSAW_OFFS = np.array([-0.11002313, -0.06288439, -0.01952356, 0.0, 0.01991221, 0.06216538, 0.10745242])


def supersaw(freq, n, detune=0.35, mix=0.75, spread=1.0, rng=None, sr=SR):
    """JP-8000 style supersaw: 7 saws, detune 0..1, ``mix`` = side voices level, stereo spread.
    ``freq`` scalar or per-sample array."""
    rng = rng or np.random.default_rng(7)
    out = np.zeros((n, 2), dtype=F32)
    d = detune ** 1.6
    pans = [-1.0, 0.66, -0.33, 0.0, 0.33, -0.66, 1.0]
    for i, off in enumerate(_SUPERSAW_OFFS):
        f = np.asarray(freq) * (1.0 + off * d)
        g = 1.0 - 0.6 * mix if off == 0.0 else mix * 0.55
        out += pan(saw(f, n, rng.random()) * g, pans[i] * spread)
    out = hp(out, float(np.min(freq)) * 0.8 if np.isscalar(freq) else 30.0, 1)
    return out.astype(F32)


def fm(freq, n, ratio=1.0, index=2.0, index_env=None, feedback=0.0, sr=SR):
    """Two-operator FM (phase modulation): carrier at ``freq``, modulator at ``freq*ratio``,
    modulation index scalar or envelope array."""
    f = param_array(freq, n)
    ph_m = 2 * np.pi * np.cumsum(f * ratio) / sr
    idx = param_array(index, n) if index_env is None else index * np.asarray(index_env, dtype=np.float64)[:n]
    mod = np.sin(ph_m)
    if feedback:
        mod = np.sin(ph_m + feedback * mod)
    ph_c = 2 * np.pi * np.cumsum(f) / sr
    return np.sin(ph_c + idx * mod).astype(F32)


def wavetable(freq, n, morph=0.0, sr=SR):
    """'Wavetable-ish' morph through sine → triangle → saw → square. ``morph`` 0..3, scalar or array."""
    m = param_array(morph, n)
    tables = [sine(freq, n), triangle(freq, n), saw(freq, n), square(freq, n)]
    out = np.zeros(n, dtype=np.float64)
    for i, tb in enumerate(tables):
        w = np.clip(1.0 - np.abs(m - i), 0.0, 1.0)
        out += w * tb
    return out.astype(F32)


def chorus(x, rate_hz=0.6, depth_ms=3.0, base_ms=12.0, mix=0.5, sr=SR):
    """Stereo chorus (two modulated delay taps in quadrature)."""
    from .dsp import mod_delay

    xs = as_stereo(x)
    n = xs.shape[0]
    mono = xs.mean(axis=1)
    l_mod = base_ms + depth_ms * lfo(n, rate_hz, "sine", 0.0, sr)
    r_mod = base_ms + depth_ms * lfo(n, rate_hz, "sine", 0.25, sr)
    wet = np.stack([mod_delay(mono, l_mod, sr), mod_delay(mono, r_mod, sr)], axis=1)
    return ((1 - mix) * xs + mix * wet).astype(F32)


def formant_filter(x, vowel="a", vowel_to=None, shift=1.0, sr=SR):
    """Parallel band-pass formant bank (vocal-like). Vowels: a e i o u. Optional morph to
    ``vowel_to`` over the length of the signal. ``shift`` scales formants (1.15 ≈ female)."""
    F = {
        "a": [(800, 1.0, 9), (1150, 0.5, 10), (2900, 0.25, 14), (3900, 0.12, 16)],
        "e": [(400, 1.0, 8), (1700, 0.45, 12), (2600, 0.3, 14), (3400, 0.1, 16)],
        "i": [(300, 1.0, 7), (2200, 0.35, 12), (3000, 0.25, 14), (3700, 0.1, 16)],
        "o": [(450, 1.0, 8), (800, 0.6, 9), (2830, 0.12, 14), (3500, 0.08, 16)],
        "u": [(325, 1.0, 7), (700, 0.35, 9), (2530, 0.07, 14), (3500, 0.04, 16)],
    }
    x = as_mono(x)
    n = x.shape[0]
    a = F[vowel]
    b = F[vowel_to] if vowel_to else a
    ramp = np.linspace(0, 1, n) if vowel_to else 0.0
    out = np.zeros(n, dtype=np.float64)
    for (f1, g1, q1), (f2, g2, q2) in zip(a, b):
        fc = (f1 + (f2 - f1) * ramp) * shift
        gain = g1 + (g2 - g1) * ramp
        out += svf(x, fc, q1, "bp", sr) * gain
    return out.astype(F32)
