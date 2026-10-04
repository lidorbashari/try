"""Effects: reverb, delay, saturation, bitcrush, sidechain ducking, risers/downlifters/impacts,
filter-sweep helpers and stereo tools. All return float32; stereo in/out ``(n, 2)`` unless noted.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from scipy import signal

from . import SR
from .dsp import (F32, as_mono, as_stereo, delay as _delay, fade, hp, lp, normalize, svf)
from .synth import chorus, pink, saw, supersaw, white  # noqa: F401  (chorus re-exported)

TAU = 2 * math.pi


# ----------------------------------------------------------------------------- reverb
REVERB_PRESETS = {
    #        decay_s predelay_ms damping(hf decay ratio) size(early spread ms) width
    "room":  (0.7, 8.0, 0.45, 18.0, 0.8),
    "plate": (1.8, 12.0, 0.65, 10.0, 1.0),
    "hall":  (3.2, 25.0, 0.5, 35.0, 1.0),
    "dark":  (2.6, 20.0, 0.25, 30.0, 0.9),
    "short": (0.35, 2.0, 0.5, 6.0, 0.7),
    "huge":  (6.0, 40.0, 0.45, 45.0, 1.0),
}


@lru_cache(maxsize=16)
def reverb_ir(preset="plate", decay=None, predelay_ms=None, damping=None, seed=11, sr=SR):
    """Synthesised stereo impulse response: early reflections + exponentially decaying,
    frequency-dependent (high frequencies die faster) decorrelated noise tail."""
    d0, pd0, dmp0, size, width = REVERB_PRESETS[preset]
    decay = decay or d0
    pd = pd0 if predelay_ms is None else predelay_ms
    dmp = dmp0 if damping is None else damping
    rng = np.random.default_rng(seed)
    n = int((decay * 1.1 + pd / 1000) * sr)
    t = np.arange(n) / sr
    chans = []
    for c in range(2):
        nz = rng.standard_normal(n)
        # split into 4 bands with different decay times
        bands = [(None, 400.0, 1.15), (400.0, 2000.0, 1.0), (2000.0, 6000.0, 0.55 + 0.4 * dmp),
                 (6000.0, None, 0.25 + 0.4 * dmp)]
        tail = np.zeros(n)
        for lo, hi, k in bands:
            if lo is None:
                sos = signal.butter(2, hi, "lowpass", fs=sr, output="sos")
            elif hi is None:
                sos = signal.butter(2, lo, "highpass", fs=sr, output="sos")
            else:
                sos = signal.butter(2, [lo, hi], "bandpass", fs=sr, output="sos")
            tdec = decay * k
            tail += signal.sosfilt(sos, nz) * np.exp(-6.9 * t / tdec)
        # soft fade-in of the diffuse tail (build-up of density)
        tail *= 1 - np.exp(-t / 0.012)
        # early reflections
        er = np.zeros(n)
        for _ in range(14):
            pos = int(rng.uniform(0.002, size / 1000) * sr)
            er[pos] += rng.uniform(-1, 1) * (1 - pos / (size / 1000 * sr + 1)) * 0.9
        ir = tail * 0.5 + er * 0.6
        shift = int(pd / 1000 * sr)
        ir = np.concatenate([np.zeros(shift), ir])[:n]
        chans.append(ir)
    ir = np.stack(chans, axis=1)
    mid = ir.mean(axis=1, keepdims=True)
    ir = mid + (ir - mid) * width
    ir /= np.sqrt((ir ** 2).sum(axis=0).mean())
    return ir.astype(F32)


def reverb(x, preset="plate", decay=None, predelay_ms=None, damping=None, hp_hz=200.0, lp_hz=10000.0,
           seed=11, sr=SR):
    """Convolution reverb with a synthesised IR. Returns the **wet** signal only (stereo)."""
    xs = as_stereo(x)
    ir = reverb_ir(preset, decay, predelay_ms, damping, seed, sr)
    src = hp(xs, hp_hz, 2) if hp_hz else xs
    out = np.empty_like(xs)
    for c in range(2):
        y = signal.oaconvolve(src[:, c], ir[:, c], mode="full")[: xs.shape[0]]
        out[:, c] = y
    if lp_hz:
        out = lp(out, lp_hz, 2)
    return out.astype(F32) * F32(0.35)


def tempo_delay(x, bpm, beats=0.75, feedback=0.4, lp_hz=4500.0, hp_hz=300.0, pingpong=True, sr=SR):
    """Tempo-synced delay (wet only). ``beats``: 0.75 = dotted 8th, 0.5 = 8th, 1/3 = 8th triplet."""
    return _delay(x, beats * 60.0 / bpm, feedback, lp_hz, hp_hz, pingpong, sr)


# ----------------------------------------------------------------------------- saturation / lo-fi
def saturate(x, drive=2.0, mix=1.0):
    """Symmetric tanh saturation, level compensated."""
    x = np.asarray(x, dtype=F32)
    y = np.tanh(x * drive) / math.tanh(drive)
    return (mix * y + (1 - mix) * x).astype(F32)


def soft_clip(x, threshold=0.8):
    """Smooth soft clipper: linear below ``threshold``, tanh knee above (output peak < 1)."""
    x = np.asarray(x, dtype=F32)
    t = float(threshold)
    ax = np.abs(x)
    y = np.where(ax <= t, ax, t + (1 - t) * np.tanh((ax - t) / (1 - t)))
    return (np.sign(x) * y).astype(F32)


def tape(x, drive=1.5, warmth=0.3, sr=SR):
    """Tape-ish: asymmetric saturation + gentle high roll-off + low bump."""
    x = np.asarray(x, dtype=F32)
    y = np.tanh(drive * x + 0.08 * drive * x ** 2) / math.tanh(drive)
    y = y - np.mean(y, axis=0)
    y = lp(y, 16000 - 6000 * warmth, 1)
    return y.astype(F32)


def bitcrush(x, bits=8, downsample=4):
    x = np.asarray(x, dtype=F32)
    q = 2 ** (bits - 1)
    y = np.round(x * q) / q
    if downsample > 1:
        idx = (np.arange(x.shape[0]) // downsample) * downsample
        y = y[idx]
    return y.astype(F32)


def distort(x, drive=6.0, tone_hz=6000.0, sr=SR):
    """Hard-ish distortion with post low-pass (for rumbles, industrial textures)."""
    y = np.clip(np.tanh(np.asarray(x, dtype=F32) * drive) * 1.2, -1, 1)
    return lp(y, tone_hz, 2, sr) if tone_hz else y.astype(F32)


# ----------------------------------------------------------------------------- sidechain
def duck_shape(release_ms=180.0, attack_ms=3.0, hold_ms=8.0, curve=2.2, sr=SR):
    """Ducking envelope 0..1 (1 = fully ducked) for one trigger."""
    na = max(1, int(attack_ms * 1e-3 * sr))
    nh = int(hold_ms * 1e-3 * sr)
    nr = max(1, int(release_ms * 1e-3 * sr))
    a = np.linspace(0, 1, na, endpoint=False)
    r = (1 - (np.linspace(0, 1, nr))) ** curve
    return np.concatenate([a, np.ones(nh), r]).astype(F32)


def sidechain_env(trigger_samples, n, release_ms=180.0, attack_ms=3.0, hold_ms=8.0, curve=2.2,
                  velocities=None, sr=SR):
    """Ducking amount 0..1 per sample built from kick trigger positions (max of overlapping)."""
    env = np.zeros(n, dtype=F32)
    shp = duck_shape(release_ms, attack_ms, hold_ms, curve, sr)
    na = max(1, int(attack_ms * 1e-3 * sr))
    for i, s in enumerate(trigger_samples):
        v = 1.0 if velocities is None else float(velocities[i])
        s0 = int(s) - na  # start ducking slightly before the transient
        a0 = max(0, s0)
        e = min(n, s0 + shp.shape[0])
        if e <= a0:
            continue
        seg = shp[a0 - s0: e - s0] * v
        np.maximum(env[a0:e], seg, out=env[a0:e])
    return env


def apply_sidechain(x, env, depth=0.8):
    g = (1.0 - depth * env).astype(F32)
    x = np.asarray(x, dtype=F32)
    return x * (g[:, None] if x.ndim == 2 else g)


# ----------------------------------------------------------------------------- transitions FX
def riser(dur_sec, kind="noise", f_lo=300.0, f_hi=9000.0, pitch_from=48, pitch_to=84, rng=None, sr=SR):
    """Build-up riser ending at its last sample (place with ``align='end'``). ``kind``: noise,
    pitch, both. Returns stereo, peak 1."""
    rng = rng or np.random.default_rng(3)
    n = int(dur_sec * sr)
    t = np.linspace(0, 1, n)
    out = np.zeros((n, 2), dtype=F32)
    if kind in ("noise", "both"):
        fc = f_lo * (f_hi / f_lo) ** (t ** 1.6)
        for c in range(2):
            nz = white(n, rng)
            out[:, c] += svf(nz, fc, 1.8, "bp") * 1.3 + hp(nz, 6000.0) * 0.12 * t
        amp = t ** 2.2
        out *= amp[:, None]
    if kind in ("pitch", "both"):
        f = 440.0 * 2 ** (((pitch_from + (pitch_to - pitch_from) * t ** 1.4) - 69) / 12)
        ps = supersaw(f, n, detune=0.25, mix=0.6, rng=rng)
        ps = svf(ps, 400 + 9000 * t ** 1.5, 1.0, "lp")
        out += ps * (t ** 1.8)[:, None] * 0.6
    out = fade(out, int(0.01 * sr), int(0.004 * sr))
    return normalize(out)


def downlifter(dur_sec=2.0, rng=None, sr=SR):
    """Falling noise sweep after a drop/impact (stereo)."""
    rng = rng or np.random.default_rng(4)
    n = int(dur_sec * sr)
    t = np.linspace(0, 1, n)
    fc = 9000 * (200 / 9000) ** (t ** 0.7)
    out = np.stack([svf(white(n, rng), fc, 1.5, "bp") for _ in range(2)], axis=1)
    out *= ((1 - t) ** 2.0)[:, None]
    return normalize(fade(out, int(0.003 * sr), int(0.05 * sr)))


def noise_sweep(dur_sec=4.0, up=True, q=1.2, rng=None, sr=SR):
    """White-noise filter sweep (stereo) with constant level; ``up``: low→high."""
    rng = rng or np.random.default_rng(5)
    n = int(dur_sec * sr)
    t = np.linspace(0, 1, n)
    fc = 200 * (12000 / 200) ** (t if up else 1 - t)
    out = np.stack([svf(white(n, rng), fc, q, "bp") for _ in range(2)], axis=1)
    return normalize(fade(out, int(0.05 * sr), int(0.05 * sr)))


def reverse_cymbal(dur_sec=2.0, rng=None, sr=SR):
    from .drums import crash

    c = crash(decay=dur_sec * 1.3, rng=rng, sr=sr)
    n = int(dur_sec * sr)
    c = c[:n][::-1]
    return normalize(fade(c, int(0.01 * sr), int(0.003 * sr)))


def impact(dur_sec=2.5, rng=None, sr=SR):
    """Sub boom + noise burst + tail for drop downbeats (stereo)."""
    rng = rng or np.random.default_rng(6)
    n = int(dur_sec * sr)
    tt = np.arange(n) / sr
    f = 30 + 70 * np.exp(-tt / 0.15)
    boom = np.sin(TAU * np.cumsum(f) / sr) * np.exp(-tt / (dur_sec / 4))
    nz = lp(white(n, rng), 3000.0) * np.exp(-tt / 0.08) * 0.5
    mono = np.tanh(1.5 * (boom + nz))
    wet = reverb(mono, "hall", decay=dur_sec, hp_hz=300)
    out = as_stereo(mono) + wet * 1.5
    return normalize(fade(out, 0, int(0.2 * sr)))


def sweep_curve(n, start_hz, end_hz, shape=1.0):
    """Exponential cutoff sweep curve (Hz per sample), ``shape`` >1 = slow start."""
    t = np.linspace(0, 1, n) ** shape
    return start_hz * (end_hz / start_hz) ** t


def filter_sweep(x, start_hz, end_hz, mode="lp", q=0.9, shape=1.0, sr=SR):
    xs = np.asarray(x, dtype=F32)
    return svf(xs, sweep_curve(xs.shape[0], start_hz, end_hz, shape), q, mode, sr)


def rumble(x, bpm, cutoff=160.0, decay=2.2, drive=4.0, sr=SR):
    """Techno rumble from a kick layer: dark long reverb (wet) → low-pass → saturation → HP.
    Feed the kick layer buffer; sidechain the result to the kick afterwards."""
    wet = reverb(as_mono(x), "dark", decay=decay, predelay_ms=0.25 * 60000 / bpm / 4, hp_hz=30.0, lp_hz=None)
    m = as_mono(wet)
    m = normalize(svf(m, cutoff, 1.2, "lp", sr))
    m = np.tanh(m * drive)
    m = svf(m.astype(F32), cutoff * 1.2, 0.8, "lp", sr)
    m = hp(m, 32.0, 2, sr)
    return as_stereo(normalize(m.astype(F32)))


# ----------------------------------------------------------------------------- stereo tools
def widen(x, width=1.4, mono_below=150.0, sr=SR):
    """Mid/side width with everything below ``mono_below`` Hz forced to mono."""
    xs = as_stereo(x)
    m = (xs[:, 0] + xs[:, 1]) * 0.5
    s = (xs[:, 0] - xs[:, 1]) * 0.5
    s = s * width
    if mono_below:
        s = hp(s, mono_below, 2, sr)
    return np.stack([m + s, m - s], axis=1).astype(F32)


def haas(x, ms=12.0, sr=SR):
    """Mono → stereo by delaying the right channel a few ms (use on highs only)."""
    m = as_mono(x)
    d = int(ms * 1e-3 * sr)
    r = np.concatenate([np.zeros(d, dtype=F32), m[:-d] if d else m])
    return np.stack([m, r], axis=1).astype(F32)


def mono_below(x, freq=120.0, sr=SR):
    return widen(x, 1.0, freq, sr)
