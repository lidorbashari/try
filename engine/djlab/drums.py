"""Drum & percussion synthesis (one-shots).

Every function returns a **mono float32 one-shot normalised to peak 1.0** (unless noted), starting
with its transient at sample 0 (so a hit placed on the grid is sample-exact). Velocity is applied
by the arrangement layer; use :func:`variants` to pre-render a few humanised round-robin copies.

Kick flavours: ``kick("tech_house"|"909"|"808"|"techno"|"hard"|"house"|"deep")``.
"""
from __future__ import annotations

import math

import numpy as np

from . import SR
from .dsp import F32, bp, fade, hp, lp, normalize, square, svf
from .synth import pink, white

TAU = 2 * math.pi


def _t(n, sr=SR):
    return np.arange(n) / sr


def _sat(x, drive):
    if drive <= 0:
        return x
    return (np.tanh(x * drive) / math.tanh(drive)).astype(F32)


def _rng(rng):
    return rng if rng is not None else np.random.default_rng(0)


# ============================================================================ kicks
KICK_PRESETS = {
    #            f_start f_end  pitch_t  decay  click  drive  noise  len
    "tech_house": (260.0, 50.0, 0.030, 0.30, 0.55, 1.6, 0.15, 0.55),
    "house":      (230.0, 52.0, 0.035, 0.38, 0.45, 1.3, 0.12, 0.65),
    "909":        (210.0, 51.0, 0.040, 0.45, 0.65, 1.2, 0.25, 0.70),
    "deep":       (180.0, 47.0, 0.045, 0.42, 0.25, 1.0, 0.05, 0.70),
    "techno":     (240.0, 47.0, 0.028, 0.40, 0.60, 2.4, 0.18, 0.65),
    "hard":       (320.0, 52.0, 0.022, 0.32, 0.80, 6.0, 0.25, 0.50),
    "808":        (95.0, 46.0, 0.060, 1.30, 0.20, 1.1, 0.0, 1.60),
    "trap":       (110.0, 44.0, 0.050, 1.10, 0.35, 1.8, 0.0, 1.40),
    "dnb":        (280.0, 55.0, 0.022, 0.22, 0.70, 1.8, 0.20, 0.40),
    "big_room":   (300.0, 50.0, 0.028, 0.36, 0.75, 2.2, 0.25, 0.60),
}


def kick(kind="tech_house", tune_hz=None, decay=None, click=None, drive=None, length=None, rng=None, sr=SR):
    """Synth kick drum. ``tune_hz`` sets the final body pitch (e.g. key root around 45–60 Hz)."""
    rng = _rng(rng)
    f0, f1, pt, dec, clk, drv, nz, ln = KICK_PRESETS[kind]
    f1 = tune_hz or f1
    dec = decay or dec
    clk = clk if click is None else click
    drv = drv if drive is None else drive
    ln = length or ln
    n = int(ln * sr)
    t = _t(n, sr)
    # pitch envelope: fast exponential drop plus a slower tail glide (gives "thump")
    f = f1 + (f0 - f1) * np.exp(-t / pt) + f1 * 0.12 * np.exp(-t / (pt * 6))
    ph = TAU * np.cumsum(f) / sr
    ph -= ph[0]
    body = np.sin(ph)
    # amplitude: tiny attack, short hold, exponential decay with soft knee
    hold = 0.012 if kind not in ("808", "trap") else 0.03
    amp = np.where(t < hold, 1.0, np.exp(-(t - hold) / (dec / 4.2)))
    amp *= np.clip(t / 0.0006, 0, 1) * 0.15 + 0.85 if kind != "808" else 1.0
    body = body * amp
    # click / beater transient
    nc = int(0.012 * sr)
    tc = _t(nc, sr)
    ck = np.sin(TAU * (1800 + 1400 * np.exp(-tc / 0.002)) * tc) * np.exp(-tc / 0.0025)
    noise = hp(white(nc, rng), 2500.0) * np.exp(-tc / 0.004) * nz * 2.0
    trans = np.zeros(n)
    trans[:nc] = (ck + noise) * clk * 0.5
    x = body + trans
    x = _sat(x.astype(F32), drv)
    if kind == "hard":
        x = lp(x, 7000.0)
        x = _sat(x * 1.4, 1.5)
    x = hp(x, 20.0, 2)
    x = fade(x, 0, int(0.01 * sr))
    return normalize(x)


def rumble_tail(kick_sample, length_sec=0.9, cutoff=180.0, drive=3.0, rng=None, sr=SR):
    """Pseudo 'reverb rumble' for one kick (dark, saturated, low-passed decay) – useful for a
    one-shot rumble; for continuous rumble use :func:`djlab.fx.rumble` on a kick layer."""
    rng = _rng(rng)
    n = int(length_sec * sr)
    t = _t(n, sr)
    nz = lp(white(n, rng), cutoff * 1.5, 4) * np.exp(-t / (length_sec / 3))
    tone = np.zeros(n, dtype=F32)
    k = kick_sample[: n]
    tone[: len(k)] = k
    x = svf(tone * 0.5 + nz * 3.0, cutoff, 2.0, "lp")
    return normalize(_sat(x, drive))


# ============================================================================ snares / claps
def clap(tightness=1.0, tone_hz=1250.0, tail=0.16, bursts=4, rng=None, sr=SR):
    """Analog-style hand clap: several noise bursts ~9 ms apart + filtered tail."""
    rng = _rng(rng)
    n = int((tail * 2.5 + 0.05) * sr)
    t = _t(n, sr)
    nz = white(n, rng)
    env = np.zeros(n)
    spacing = 0.0095 * tightness
    for b in range(bursts):
        st = b * spacing * (1 + 0.15 * rng.uniform(-1, 1)) if b else 0.0
        i0 = int(st * sr)
        tt = t[i0:] - st
        if b < bursts - 1:
            env[i0:] += np.exp(-tt / 0.0035) * (0.85 if b else 1.0)
        else:
            env[i0:] += np.exp(-tt / (tail / 3.0)) * 0.9
    x = svf(nz * env, tone_hz, 1.4, "bp") * 1.6 + svf(nz * env, tone_hz * 2.2, 1.0, "bp") * 0.6
    x = x + hp(nz * env, 5000.0) * 0.1
    x = hp(x, 450.0)
    return normalize(fade(x, 0, int(0.02 * sr)))


def snare(tone_hz=185.0, snappy=0.7, decay=0.18, rng=None, kind="909", sr=SR):
    """Tonal body (two pitched modes) + snappy noise. ``kind`` 909|808|tight|trap."""
    rng = _rng(rng)
    if kind == "tight":
        decay *= 0.6
    n = int((decay * 2.2 + 0.03) * sr)
    t = _t(n, sr)
    pe = 1 + 0.5 * np.exp(-t / 0.008)
    body = (np.sin(TAU * np.cumsum(tone_hz * pe) / sr) * np.exp(-t / 0.06)
            + 0.6 * np.sin(TAU * np.cumsum(tone_hz * 1.78 * pe) / sr) * np.exp(-t / 0.035))
    nz = white(n, rng)
    nz = bp(nz, 1800.0, 9000.0) * np.exp(-t / (decay / 3.2))
    x = body * (1 - snappy * 0.5) + nz * snappy * 2.2
    if kind == "808":
        x = lp(x, 7000.0)
    if kind == "trap":
        x = _sat(x * 1.5, 1.5)
    return normalize(fade(hp(x, 120.0), 0, int(0.01 * sr)))


def rimshot(tone_hz=1700.0, rng=None, sr=SR):
    rng = _rng(rng)
    n = int(0.08 * sr)
    t = _t(n, sr)
    x = (np.sin(TAU * tone_hz * t) * np.exp(-t / 0.008) + 0.8 * np.sin(TAU * tone_hz * 0.29 * t) * np.exp(-t / 0.012)
         + 0.6 * hp(white(n, rng), 3000.0) * np.exp(-t / 0.003))
    x = bp(x, 400.0, 9000.0)
    return normalize(_sat(x.astype(F32), 1.5))


def snap(rng=None, sr=SR):
    """Finger snap."""
    rng = _rng(rng)
    n = int(0.12 * sr)
    t = _t(n, sr)
    x = svf(white(n, rng), 2400.0, 2.5, "bp") * (np.exp(-t / 0.02) + 0.5 * np.exp(-t / 0.002))
    return normalize(hp(x, 900.0))


# ============================================================================ metallic (hats, cymbals)
_METAL = np.array([205.3, 304.4, 369.6, 522.7, 540.0, 800.0])


def _metal_cluster(n, scale=1.0, rng=None, sr=SR):
    rng = _rng(rng)
    x = np.zeros(n, dtype=F32)
    for f in _METAL * scale:
        x += square(f * (1 + 0.003 * rng.uniform(-1, 1)), n, rng.random())
    return x / len(_METAL)


def hat(open_=False, decay=None, tone=1.0, noise_mix=0.35, rng=None, sr=SR):
    """808/909-style hi-hat: 6 detuned square oscillators + noise, band-passed. ``tone`` scales
    the metallic cluster (1.0 = classic). Closed decay ≈ 45 ms, open ≈ 320 ms."""
    rng = _rng(rng)
    dec = decay or (0.32 if open_ else 0.045)
    n = int((dec * 3 + 0.01) * sr)
    t = _t(n, sr)
    m = _metal_cluster(n, 1.45 * tone, rng, sr)
    m = bp(m, 4800.0 * tone ** 0.5, 12500.0, 2)
    nz = svf(white(n, rng), 7500.0 * tone ** 0.5, 0.9, "bp")
    x = (1 - noise_mix) * m * 3.0 + noise_mix * nz * 1.5
    env = np.exp(-t / (dec / 2.6)) * (0.8 + 0.2 * np.exp(-t / 0.004))
    x = hp(x * env, 4200.0, 2)
    x = lp(x, 14000.0, 2)
    x = fade(x, 0, int(0.004 * sr))
    return normalize(x)


def ride(decay=1.4, bell=0.5, rng=None, sr=SR):
    """Ride cymbal: metallic cluster + inharmonic bell partials + shimmer noise."""
    rng = _rng(rng)
    n = int(decay * 1.6 * sr)
    t = _t(n, sr)
    m = bp(_metal_cluster(n, 2.6, rng, sr), 3500.0, 16000.0)
    partials = [(2950, 1.0), (4170, 0.6), (5340, 0.45), (6890, 0.3), (8410, 0.2)]
    b = sum(a * np.sin(TAU * f * t + rng.random() * TAU) for f, a in partials) * np.exp(-t / (decay / 5.0))
    nz = hp(white(n, rng), 6000.0) * np.exp(-t / (decay / 6.0)) * 0.4
    env = np.exp(-t / (decay / 4.5))
    x = m * 2.0 * env + bell * b * 0.4 + nz
    x = x * (0.75 + 0.25 * np.exp(-t / 0.01))
    return normalize(fade(hp(x, 2500.0), 0, int(0.05 * sr)))


def crash(decay=2.2, rng=None, sr=SR):
    """Crash cymbal (stereo, decorrelated). Returns (n, 2)."""
    rng = _rng(rng)
    n = int(decay * 1.3 * sr)
    t = _t(n, sr)
    outs = []
    for _ in range(2):
        m = bp(_metal_cluster(n, 3.1, rng, sr), 3000.0, 17000.0)
        nz = hp(white(n, rng), 4000.0)
        env = np.exp(-t / (decay / 4.0)) * (0.6 + 0.4 * np.exp(-t / 0.05))
        sweep = svf(nz, 5000 + 6000 * np.exp(-t / 0.4), 0.8, "lp")
        x = (m * 1.5 + sweep * 0.9 + nz * 0.3) * env
        outs.append(fade(hp(x, 1500.0), int(0.0005 * sr), int(0.1 * sr)))
    st = np.stack(outs, axis=1)
    return (st / np.abs(st).max()).astype(F32)


def shaker(length=0.09, tone=6200.0, rng=None, sr=SR):
    """Shaker: band-passed noise with a soft, grainy attack."""
    rng = _rng(rng)
    n = int(length * 1.6 * sr)
    t = _t(n, sr)
    a = length * 0.25
    env = np.where(t < a, (t / a) ** 1.5, np.exp(-(t - a) / (length * 0.35)))
    grains = 0.7 + 0.3 * np.abs(svf(white(n, rng), 400.0, 0.7, "lp")) * 6
    x = svf(white(n, rng), tone, 1.2, "bp") * env * np.clip(grains, 0, 1.5)
    return normalize(lp(hp(x, 3000.0), 13000.0))


def tambourine(length=0.22, rng=None, sr=SR):
    rng = _rng(rng)
    n = int(length * 1.5 * sr)
    t = _t(n, sr)
    jingles = np.zeros(n)
    for f in (5200, 6750, 8100, 9600, 11200, 12900):
        jingles += np.sin(TAU * f * (1 + 0.01 * rng.uniform(-1, 1)) * t + rng.random() * TAU)
    am = np.clip(np.abs(svf(white(n, rng), 120.0, 0.7, "lp")) * 8, 0, 1)
    env = np.exp(-t / (length / 4))
    x = (jingles * 0.15 * (0.4 + 0.6 * am) + hp(white(n, rng), 6000.0) * 0.6) * env
    return normalize(fade(hp(x, 4000.0), int(0.001 * sr), int(0.02 * sr)))


def cowbell(rng=None, sr=SR):
    rng = _rng(rng)
    n = int(0.35 * sr)
    t = _t(n, sr)
    x = square(540.0, n) + square(800.0, n)
    x = bp(x, 500.0, 3000.0) * (np.exp(-t / 0.015) * 0.6 + np.exp(-t / 0.09) * 0.4)
    return normalize(x)


# ============================================================================ hand drums / toms
def conga(pitch_hz=220.0, kind="open", rng=None, sr=SR):
    """Conga / bongo. ``kind``: open, mute, slap. Use pitch ~180–350 (conga), 400–650 (bongo)."""
    rng = _rng(rng)
    dec = {"open": 0.22, "mute": 0.06, "slap": 0.08}[kind]
    n = int((dec * 3 + 0.02) * sr)
    t = _t(n, sr)
    f = pitch_hz * (1 + 0.25 * np.exp(-t / 0.012))
    body = np.sin(TAU * np.cumsum(f) / sr) * np.exp(-t / (dec / 2.5))
    over = 0.35 * np.sin(TAU * np.cumsum(f * 1.52) / sr) * np.exp(-t / (dec / 4))
    slap_amt = {"open": 0.15, "mute": 0.25, "slap": 0.9}[kind]
    sl = svf(white(n, rng), pitch_hz * 9, 1.2, "bp") * np.exp(-t / 0.012) * slap_amt * 2
    x = body + over + sl
    return normalize(fade(hp(x, 60.0), 0, int(0.01 * sr)))


def bongo(pitch_hz=480.0, kind="open", rng=None, sr=SR):
    return conga(pitch_hz, kind, rng, sr)


def tom(pitch_hz=110.0, decay=0.45, rng=None, sr=SR):
    rng = _rng(rng)
    n = int(decay * 2 * sr)
    t = _t(n, sr)
    f = pitch_hz * (1 + 0.6 * np.exp(-t / 0.03))
    x = np.sin(TAU * np.cumsum(f) / sr) * np.exp(-t / (decay / 3.5))
    x += 0.3 * hp(white(n, rng), 1500.0) * np.exp(-t / 0.01)
    return normalize(_sat(x.astype(F32), 1.2))


def darbuka(stroke="doum", pitch_hz=None, rng=None, sr=SR):
    """Middle-eastern goblet drum. ``stroke``: doum (deep centre), tek (sharp rim), ka (soft rim),
    slap (pa)."""
    rng = _rng(rng)
    if stroke == "doum":
        p = pitch_hz or 120.0
        n = int(0.6 * sr)
        t = _t(n, sr)
        f = p * (1 + 0.35 * np.exp(-t / 0.015))
        x = np.sin(TAU * np.cumsum(f) / sr) * np.exp(-t / 0.11)
        x += 0.45 * np.sin(TAU * np.cumsum(f * 2.3) / sr) * np.exp(-t / 0.05)
        x += 0.25 * svf(white(n, rng), 900.0, 1.0, "bp") * np.exp(-t / 0.01)
        return normalize(fade(hp(x, 40.0), 0, int(0.02 * sr)))
    n = int(0.25 * sr)
    t = _t(n, sr)
    p = pitch_hz or (720.0 if stroke == "tek" else 640.0)
    ring = np.sin(TAU * p * t) * np.exp(-t / 0.035) + 0.6 * np.sin(TAU * p * 1.59 * t) * np.exp(-t / 0.02)
    crack = hp(white(n, rng), 2500.0) * np.exp(-t / (0.004 if stroke != "slap" else 0.012))
    amt = {"tek": (1.0, 1.0), "ka": (0.55, 0.6), "slap": (0.6, 1.4)}[stroke]
    x = ring * amt[0] + crack * amt[1]
    return normalize(fade(hp(x, 250.0), 0, int(0.01 * sr)))


def log_drum(freq_hz=55.0, decay=0.45, knock=0.6, bend=5.0, rng=None, sr=SR):
    """Amapiano log drum: pitched, slightly bent down, woody knock + saturation. Pitched – call per
    note (``freq_hz``) and cache, or use as a Notes instrument via :func:`log_drum_instrument`."""
    rng = _rng(rng)
    n = int(decay * 2.2 * sr)
    t = _t(n, sr)
    f = freq_hz * 2 ** (bend / 12 * np.exp(-t / 0.018))
    ph = TAU * np.cumsum(f) / sr
    body = np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.15 * np.sin(3 * ph + 0.5)
    body *= np.exp(-t / (decay / 3.0))
    nk = int(0.02 * sr)
    k = np.zeros(n)
    k[:nk] = svf(white(nk, rng), 1400.0, 2.0, "bp") * np.exp(-_t(nk) / 0.004)
    x = _sat((body + knock * k * 2).astype(F32), 1.8)
    return normalize(fade(hp(x, 25.0), 0, int(0.02 * sr)))


def perc_blip(freq_hz=900.0, decay=0.05, fm_index=1.5, ratio=1.41, rng=None, sr=SR):
    """Short FM/sine 'tech' percussion blip (tops, rim-ish perc)."""
    n = int((decay * 4 + 0.01) * sr)
    t = _t(n, sr)
    f = freq_hz * (1 + 0.5 * np.exp(-t / 0.006))
    ph = TAU * np.cumsum(f) / sr
    x = np.sin(ph + fm_index * np.exp(-t / (decay / 2)) * np.sin(ph * ratio)) * np.exp(-t / (decay / 2.5))
    return normalize(fade(x.astype(F32), 0, int(0.005 * sr)))


def metal_hit(freq_hz=320.0, decay=0.35, rng=None, sr=SR):
    """Industrial metallic clang (inharmonic FM + noise)."""
    rng = _rng(rng)
    n = int(decay * 2.5 * sr)
    t = _t(n, sr)
    ph = TAU * freq_hz * t
    x = np.sin(ph + 3.0 * np.exp(-t / (decay / 3)) * np.sin(ph * 2.76)) * np.exp(-t / (decay / 3))
    x += 0.5 * np.sin(ph * 4.07 + 2 * np.sin(ph * 1.13)) * np.exp(-t / (decay / 5))
    x += 0.3 * hp(white(n, rng), 2000.0) * np.exp(-t / 0.01)
    return normalize(hp(x, 150.0))


def noise_hit(length=0.12, cutoff=3000.0, rng=None, sr=SR):
    rng = _rng(rng)
    n = int(length * 2 * sr)
    t = _t(n, sr)
    x = svf(pink(n, rng), cutoff, 0.9, "bp") * np.exp(-t / (length / 3))
    return normalize(x)


# ============================================================================ helpers
def variants(fn, n=4, rng=None, jitter=None, **kw):
    """Pre-render ``n`` humanised round-robin variants of a one-shot generator.

    ``jitter``: dict of {param: relative amount}, e.g. ``{"tone_hz": 0.02, "decay": 0.06}``. Each
    variant also gets its own noise seed via ``rng``. Returns a list of arrays.
    """
    rng = _rng(rng)
    jitter = jitter or {}
    out = []
    for i in range(n):
        kk = dict(kw)
        for p, amt in jitter.items():
            if p in kk and kk[p] is not None:
                kk[p] = kk[p] * (1 + amt * rng.uniform(-1, 1))
        child = np.random.default_rng(rng.integers(1 << 31))
        out.append(fn(rng=child, **kk))
    return out
