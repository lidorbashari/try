"""Low-level DSP primitives (numba-accelerated kernels + numpy helpers).

Conventions used across the engine:
* mono audio = 1-D float32 array ``(n,)``; stereo = ``(n, 2)`` float32.
* cutoff / gain parameters accept a scalar or a per-sample array (sample-accurate modulation).
"""
from __future__ import annotations

import math

import numpy as np
from numba import njit
from scipy import signal

from . import SR

F32 = np.float32


# ----------------------------------------------------------------------------- basic helpers
def db2lin(db):
    return np.power(10.0, np.asarray(db, dtype=np.float64) / 20.0)


def lin2db(x, floor=1e-12):
    return 20.0 * np.log10(np.maximum(np.abs(x), floor))


def secs(n_or_sec, sr=SR) -> int:
    return int(round(n_or_sec * sr))


def as_stereo(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=F32)
    if x.ndim == 1:
        return np.stack([x, x], axis=1)
    return x


def as_mono(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=F32)
    if x.ndim == 2:
        return x.mean(axis=1).astype(F32)
    return x


def pan(x: np.ndarray, p: float = 0.0) -> np.ndarray:
    """Constant-power pan of a mono (or stereo) signal; p in [-1, 1]."""
    if x.ndim == 2:
        if p == 0.0:
            return x.astype(F32)
        a = (p + 1.0) * math.pi / 4.0
        gl, gr = math.cos(a) * math.sqrt(2), math.sin(a) * math.sqrt(2)
        return np.stack([x[:, 0] * min(gl, 1.0), x[:, 1] * min(gr, 1.0)], axis=1).astype(F32)
    a = (p + 1.0) * math.pi / 4.0
    return np.stack([x * math.cos(a), x * math.sin(a)], axis=1).astype(F32) * F32(math.sqrt(2))


def normalize(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    m = float(np.max(np.abs(x))) if x.size else 0.0
    if m < 1e-12:
        return x.astype(F32)
    return (x * (peak / m)).astype(F32)


def fade(x: np.ndarray, fade_in: int = 0, fade_out: int = 0) -> np.ndarray:
    """Raised-cosine fades (in samples), in place-safe copy."""
    x = np.array(x, dtype=F32, copy=True)
    n = x.shape[0]
    if fade_in > 0:
        k = min(fade_in, n)
        w = (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, k))).astype(F32)
        x[:k] *= w if x.ndim == 1 else w[:, None]
    if fade_out > 0:
        k = min(fade_out, n)
        w = (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, k))).astype(F32)
        x[n - k:] *= w if x.ndim == 1 else w[:, None]
    return x


def mix_into(buf: np.ndarray, x: np.ndarray, pos: int, gain: float = 1.0) -> None:
    """Add ``x`` into ``buf`` at sample ``pos`` (clipped to the buffer)."""
    n = buf.shape[0]
    if pos >= n or x.shape[0] == 0:
        return
    s0 = max(0, pos)
    off = s0 - pos
    if off >= x.shape[0]:
        return
    e = min(n, pos + x.shape[0])
    seg = x[off:off + (e - s0)]
    if buf.ndim == 2 and seg.ndim == 1:
        buf[s0:e] += (seg * gain)[:, None]
    else:
        buf[s0:e] += seg * gain


def param_array(v, n: int) -> np.ndarray:
    if np.isscalar(v):
        return np.full(n, float(v), dtype=np.float64)
    a = np.asarray(v, dtype=np.float64)
    if a.shape[0] < n:
        a = np.concatenate([a, np.full(n - a.shape[0], a[-1] if a.size else 0.0)])
    return a[:n]


def _g_from_cutoff(cutoff, n, sr):
    fc = np.clip(param_array(cutoff, n), 10.0, sr * 0.45)
    return np.tan(np.pi * fc / sr)


# ----------------------------------------------------------------------------- SVF (TPT / Simper)
@njit(cache=True, fastmath=True)
def _svf_kernel(x, g, k, mode):
    n = x.shape[0]
    y = np.empty(n, dtype=np.float32)
    ic1 = 0.0
    ic2 = 0.0
    for i in range(n):
        gi = g[i]
        a1 = 1.0 / (1.0 + gi * (gi + k))
        a2 = gi * a1
        a3 = gi * a2
        v0 = x[i]
        v3 = v0 - ic2
        v1 = a1 * ic1 + a2 * v3
        v2 = ic2 + a2 * ic1 + a3 * v3
        ic1 = 2.0 * v1 - ic1
        ic2 = 2.0 * v2 - ic2
        if mode == 0:
            y[i] = v2
        elif mode == 1:
            y[i] = v0 - k * v1 - v2
        elif mode == 2:
            y[i] = v1 * k  # constant peak-gain bandpass
        else:
            y[i] = v0 - k * v1  # notch
    return y


_SVF_MODES = {"lp": 0, "hp": 1, "bp": 2, "notch": 3}


def svf(x: np.ndarray, cutoff, q: float = 0.707, mode: str = "lp", sr: int = SR) -> np.ndarray:
    """Resonant 12 dB/oct state-variable filter with per-sample cutoff (scalar or array)."""
    x = np.asarray(x, dtype=F32)
    n = x.shape[0]
    g = _g_from_cutoff(cutoff, n, sr)
    k = 1.0 / max(q, 0.05)
    m = _SVF_MODES[mode]
    if x.ndim == 2:
        return np.stack([_svf_kernel(x[:, c].astype(np.float64), g, k, m) for c in range(x.shape[1])], axis=1)
    return _svf_kernel(x.astype(np.float64), g, k, m)


def svf24(x, cutoff, q=0.707, mode="lp", sr=SR):
    """24 dB/oct (two cascaded SVFs; resonance only on the second)."""
    return svf(svf(x, cutoff, 0.707, mode, sr), cutoff, q, mode, sr)


# ----------------------------------------------------------------------------- ladder (TPT, tanh)
@njit(cache=True, fastmath=True)
def _ladder_kernel(x, g, k, drive):
    n = x.shape[0]
    y = np.empty(n, dtype=np.float32)
    s1 = 0.0
    s2 = 0.0
    s3 = 0.0
    s4 = 0.0
    comp = 1.0 + 0.5 * k
    for i in range(n):
        gi = g[i]
        G = gi / (1.0 + gi)
        inv = 1.0 / (1.0 + gi)
        e1 = s1 * inv
        e2 = s2 * inv
        e3 = s3 * inv
        e4 = s4 * inv
        S = G * G * G * e1 + G * G * e2 + G * e3 + e4
        G4 = G * G * G * G
        u = (x[i] * comp - k * S) / (1.0 + k * G4)
        u = math.tanh(u * drive) / drive
        v = (u - s1) * G
        y1 = v + s1
        s1 = y1 + v
        v = (y1 - s2) * G
        y2 = v + s2
        s2 = y2 + v
        v = (y2 - s3) * G
        y3 = v + s3
        s3 = y3 + v
        v = (y3 - s4) * G
        y4 = v + s4
        s4 = y4 + v
        y[i] = y4
    return y


def ladder(x: np.ndarray, cutoff, res: float = 0.3, drive: float = 1.0, sr: int = SR) -> np.ndarray:
    """Moog-style 24 dB/oct lowpass with tanh input stage. ``res`` 0..1 (≈1 self-oscillates)."""
    x = np.asarray(x, dtype=F32)
    n = x.shape[0]
    g = _g_from_cutoff(cutoff, n, sr)
    k = 3.98 * float(np.clip(res, 0.0, 1.0))
    d = max(float(drive), 0.05)
    if x.ndim == 2:
        return np.stack([_ladder_kernel(x[:, c].astype(np.float64), g, k, d) for c in range(2)], axis=1)
    return _ladder_kernel(x.astype(np.float64), g, k, d)


# ----------------------------------------------------------------------------- biquad EQ (RBJ)
def _rbj(kind, f0, gain_db=0.0, q=0.707, sr=SR):
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * min(f0, sr * 0.49) / sr
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2 * q)
    if kind == "peak":
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind == "lowshelf":
        sa = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) - (A - 1) * cw + sa), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sa)]
        a = [(A + 1) + (A - 1) * cw + sa, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sa]
    elif kind == "highshelf":
        sa = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) + (A - 1) * cw + sa), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sa)]
        a = [(A + 1) - (A - 1) * cw + sa, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sa]
    else:
        raise ValueError(kind)
    b = np.array(b) / a[0]
    a = np.array(a) / a[0]
    return np.concatenate([b, a])[None, :]


def _sosfilt(sos, x):
    x = np.asarray(x, dtype=F32)
    return signal.sosfilt(sos, x, axis=0).astype(F32)


def eq_peak(x, f0, gain_db, q=1.0, sr=SR):
    return _sosfilt(_rbj("peak", f0, gain_db, q, sr), x)


def eq_lowshelf(x, f0, gain_db, q=0.707, sr=SR):
    return _sosfilt(_rbj("lowshelf", f0, gain_db, q, sr), x)


def eq_highshelf(x, f0, gain_db, q=0.707, sr=SR):
    return _sosfilt(_rbj("highshelf", f0, gain_db, q, sr), x)


def hp(x, f0, order=2, sr=SR):
    """Butterworth highpass (static)."""
    return _sosfilt(signal.butter(order, f0, "highpass", fs=sr, output="sos"), x)


def lp(x, f0, order=2, sr=SR):
    """Butterworth lowpass (static)."""
    return _sosfilt(signal.butter(order, min(f0, sr * 0.49), "lowpass", fs=sr, output="sos"), x)


def bp(x, lo, hi, order=2, sr=SR):
    return _sosfilt(signal.butter(order, [lo, min(hi, sr * 0.49)], "bandpass", fs=sr, output="sos"), x)


def onepole_lp(x, f0, sr=SR):
    a = math.exp(-2 * math.pi * f0 / sr)
    return signal.lfilter([1 - a], [1, -a], np.asarray(x, dtype=F32), axis=0).astype(F32)


def onepole_hp(x, f0, sr=SR):
    return (np.asarray(x, dtype=F32) - onepole_lp(x, f0, sr)).astype(F32)


def dc_block(x, sr=SR):
    return hp(x, 12.0, 1, sr)


# ----------------------------------------------------------------------------- oscillators
@njit(cache=True, fastmath=True)
def _polyblep(t, dt):
    if t < dt:
        t = t / dt
        return t + t - t * t - 1.0
    elif t > 1.0 - dt:
        t = (t - 1.0) / dt
        return t * t + t + t + 1.0
    return 0.0


@njit(cache=True, fastmath=True)
def _osc_kernel(freq, sr, phase0, shape, pw):
    """shape: 0 saw, 1 square/pulse (pw array), 2 triangle (leaky-integrated square), 3 sine."""
    n = freq.shape[0]
    y = np.empty(n, dtype=np.float32)
    ph = phase0
    tri = 0.0
    for i in range(n):
        dt = freq[i] / sr
        if dt > 0.49:
            dt = 0.49
        if shape == 0:
            v = 2.0 * ph - 1.0
            v -= _polyblep(ph, dt)
        elif shape == 3:
            v = math.sin(2.0 * math.pi * ph)
        else:
            p = pw[i]
            v = 1.0 if ph < p else -1.0
            v += _polyblep(ph, dt)
            t2 = ph - p
            if t2 < 0.0:
                t2 += 1.0
            v -= _polyblep(t2, dt)
            if shape == 2:
                tri = dt * 4.0 * v + (1.0 - dt * 0.05) * tri
                v = tri
        y[i] = v
        ph += dt
        if ph >= 1.0:
            ph -= 1.0
    return y


def _osc(freq, n, shape, phase=0.0, pw=0.5, sr=SR):
    f = param_array(freq, n)
    p = param_array(pw, n)
    return _osc_kernel(f, float(sr), float(phase % 1.0), shape, p)


def saw(freq, n, phase=0.0, sr=SR):
    return _osc(freq, n, 0, phase, 0.5, sr)


def square(freq, n, phase=0.0, pw=0.5, sr=SR):
    return _osc(freq, n, 1, phase, pw, sr)


def triangle(freq, n, phase=0.0, sr=SR):
    y = _osc(freq, n, 2, phase, 0.5, sr)
    return normalize(dc_block(y)) if n > 64 else y


def sine(freq, n, phase=0.0, sr=SR):
    if np.isscalar(freq):
        t = np.arange(n) / sr
        return np.sin(2 * np.pi * (freq * t + phase)).astype(F32)
    ph = 2 * np.pi * (np.cumsum(param_array(freq, n)) / sr + phase)
    ph -= ph[0] - 2 * np.pi * phase
    return np.sin(ph).astype(F32)


# ----------------------------------------------------------------------------- envelope follower / compressor
@njit(cache=True, fastmath=True)
def _comp_gain(det, thr_db, ratio, knee_db, att, rel):
    n = det.shape[0]
    g = np.empty(n, dtype=np.float32)
    env = 0.0
    for i in range(n):
        lvl = 20.0 * math.log10(det[i] + 1e-9)
        over = lvl - thr_db
        if over <= -knee_db / 2.0:
            gr = 0.0
        elif over >= knee_db / 2.0:
            gr = over * (1.0 - 1.0 / ratio)
        else:
            t = over + knee_db / 2.0
            gr = (1.0 - 1.0 / ratio) * t * t / (2.0 * knee_db)
        if gr > env:
            env = att * env + (1.0 - att) * gr
        else:
            env = rel * env + (1.0 - rel) * gr
        g[i] = env
    return g


def compressor(x, threshold_db=-18.0, ratio=3.0, attack_ms=10.0, release_ms=120.0, knee_db=6.0,
               makeup_db=0.0, mix=1.0, sidechain=None, sr=SR, return_gr=False):
    """Stereo-linked feed-forward compressor (peak-ish detector smoothed by attack/release on the
    gain-reduction curve). ``mix`` < 1 gives parallel ("New York") compression."""
    x = np.asarray(x, dtype=F32)
    src = x if sidechain is None else np.asarray(sidechain, dtype=F32)
    det = np.abs(src).max(axis=1) if src.ndim == 2 else np.abs(src)
    # light RMS-ish smoothing of the detector (2 ms)
    det = onepole_lp(det, 1000.0 / (2 * np.pi * 2.0), sr)
    att = math.exp(-1.0 / (attack_ms * 1e-3 * sr))
    rel = math.exp(-1.0 / (release_ms * 1e-3 * sr))
    gr_db = _comp_gain(det.astype(np.float64), float(threshold_db), float(ratio), float(knee_db), att, rel)
    gain = np.power(10.0, (-gr_db + makeup_db) / 20.0).astype(F32)
    y = x * (gain[:, None] if x.ndim == 2 else gain)
    if mix < 1.0:
        y = mix * y + (1.0 - mix) * x
    if return_gr:
        return y.astype(F32), gr_db
    return y.astype(F32)


# ----------------------------------------------------------------------------- delay lines
@njit(cache=True, fastmath=True)
def _pingpong_kernel(xl, xr, d, fb, lp_a, hp_a, pingpong):
    n = xl.shape[0]
    size = d + 1
    bl = np.zeros(size)
    br = np.zeros(size)
    yl = np.empty(n, dtype=np.float32)
    yr = np.empty(n, dtype=np.float32)
    w = 0
    lpl = 0.0
    lpr = 0.0
    hpl = 0.0
    hpr = 0.0
    for i in range(n):
        r = w - d
        if r < 0:
            r += size
        ol = bl[r]
        orr = br[r]
        # filter in the feedback path
        lpl = lp_a * lpl + (1.0 - lp_a) * ol
        lpr = lp_a * lpr + (1.0 - lp_a) * orr
        hpl = hp_a * hpl + (1.0 - hp_a) * lpl
        hpr = hp_a * hpr + (1.0 - hp_a) * lpr
        fl = lpl - hpl
        fr = lpr - hpr
        yl[i] = fl
        yr[i] = fr
        if pingpong:
            bl[w] = 0.5 * (xl[i] + xr[i]) + fb * fr
            br[w] = fb * fl
        else:
            bl[w] = xl[i] + fb * fl
            br[w] = xr[i] + fb * fr
        w += 1
        if w >= size:
            w = 0
    return yl, yr


def delay(x, delay_sec, feedback=0.4, lp_hz=5000.0, hp_hz=250.0, pingpong=True, sr=SR):
    """Feedback delay (wet only). Ping-pong mode bounces L/R."""
    x = as_stereo(x)
    d = max(1, int(round(delay_sec * sr)))
    lp_a = math.exp(-2 * math.pi * lp_hz / sr)
    hp_a = math.exp(-2 * math.pi * hp_hz / sr)
    yl, yr = _pingpong_kernel(x[:, 0].astype(np.float64), x[:, 1].astype(np.float64), d, float(feedback),
                              lp_a, hp_a, bool(pingpong))
    return np.stack([yl, yr], axis=1)


@njit(cache=True, fastmath=True)
def _modDelay_kernel(x, dsamp):
    n = x.shape[0]
    size = 8192
    buf = np.zeros(size)
    y = np.empty(n, dtype=np.float32)
    w = 0
    for i in range(n):
        buf[w] = x[i]
        rp = w - dsamp[i]
        while rp < 0:
            rp += size
        i0 = int(rp)
        fr = rp - i0
        i1 = i0 + 1
        if i1 >= size:
            i1 -= size
        y[i] = buf[i0] * (1.0 - fr) + buf[i1] * fr
        w += 1
        if w >= size:
            w = 0
    return y


def mod_delay(x, delay_ms_curve, sr=SR):
    d = np.clip(np.asarray(delay_ms_curve, dtype=np.float64) * 1e-3 * sr, 1.0, 8000.0)
    return _modDelay_kernel(np.asarray(x, dtype=np.float64), d)


# ----------------------------------------------------------------------------- Karplus-Strong
@njit(cache=True, fastmath=True)
def _ks_kernel(exc, n, period, decay, bright):
    y = np.zeros(n, dtype=np.float32)
    p = int(period)
    frac = period - p
    size = p + 2
    buf = np.zeros(size)
    for i in range(min(size, exc.shape[0])):
        buf[i] = exc[i]
    idx = 0
    prev = 0.0
    for i in range(n):
        i1 = idx + 1
        if i1 >= size:
            i1 -= size
        v = buf[idx] * (1.0 - frac) + buf[i1] * frac
        y[i] = v
        nv = decay * (bright * v + (1.0 - bright) * 0.5 * (v + prev))
        prev = v
        buf[idx] = nv
        idx += 1
        if idx >= size:
            idx = 0
    return y


def karplus(freq, n, decay=0.996, bright=0.5, rng=None, sr=SR):
    """Plucked string (Karplus-Strong). ``bright`` 0..1 (higher = brighter/longer highs)."""
    rng = rng or np.random.default_rng(0)
    period = sr / freq
    exc = rng.uniform(-1, 1, int(period) + 2)
    exc = exc - exc.mean()
    return _ks_kernel(exc, int(n), float(period), float(decay), float(bright))


# ----------------------------------------------------------------------------- limiter helpers
@njit(cache=True, fastmath=True)
def _release_smooth(g, rel):
    n = g.shape[0]
    y = np.empty(n, dtype=np.float64)
    cur = 1.0
    for i in range(n):
        target = g[i]
        if target < cur:
            cur = target
        else:
            cur = target + (cur - target) * rel
        y[i] = cur
    return y


def oversampled_peak(x: np.ndarray, factor: int = 4) -> np.ndarray:
    """Per-sample true-peak estimate (max over channels of the 4x-oversampled magnitude)."""
    x = as_stereo(x)
    out = np.zeros(x.shape[0], dtype=np.float32)
    for c in range(x.shape[1]):
        up = signal.resample_poly(x[:, c], factor, 1, window=("kaiser", 8.0)).astype(np.float32)
        m = np.abs(up[: x.shape[0] * factor]).reshape(-1, factor).max(axis=1)
        out = np.maximum(out, m[: x.shape[0]])
    return np.maximum(out, np.abs(x).max(axis=1))


def true_peak_db(x: np.ndarray) -> float:
    return float(lin2db(oversampled_peak(x).max() + 1e-12))
