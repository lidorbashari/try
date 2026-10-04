"""Mastering chain: DC/sub cleanup → mono bass → tone EQ → glue compressor → (gain → 2x-oversampled
soft clipper → look-ahead true-peak limiter) iterated until the integrated loudness hits the
target LUFS, with true peak ≤ ceiling.
"""
from __future__ import annotations

import numpy as np
import pyloudnorm as pyln
from scipy import signal
from scipy.ndimage import minimum_filter1d, uniform_filter1d

from . import SR
from .dsp import (F32, _release_smooth, compressor, eq_highshelf, eq_lowshelf, eq_peak, hp, lin2db,
                  oversampled_peak)
from .fx import soft_clip, widen


def lufs(x, sr=SR) -> float:
    x = np.asarray(x, dtype=np.float64)
    if x.shape[0] < sr * 0.5:
        x = np.concatenate([x, np.zeros((int(sr * 0.5), x.shape[1]))])
    v = pyln.Meter(sr).integrated_loudness(x)
    return float(v) if np.isfinite(v) else -70.0


def limiter(x, ceiling_db=-1.3, lookahead_ms=5.0, release_ms=90.0, sr=SR):
    """Look-ahead brickwall limiter on 4x-oversampled (true) peaks."""
    x = np.asarray(x, dtype=F32)
    c = 10 ** (ceiling_db / 20.0)
    peak = oversampled_peak(x)
    g = np.minimum(1.0, c / np.maximum(peak, 1e-9)).astype(np.float64)
    L = int(lookahead_ms * 1e-3 * sr) // 2 * 2
    gmin = minimum_filter1d(g, size=L + 1, mode="nearest", origin=-(L // 2))
    rel = np.exp(-1.0 / (release_ms * 1e-3 * sr))
    g2 = _release_smooth(gmin, rel)
    g3 = uniform_filter1d(g2, size=L + 1, mode="nearest", origin=L // 2)
    g3 = np.minimum(g3, g)  # numerical safety
    y = x * g3.astype(F32)[:, None]
    return y.astype(F32), float(lin2db(g3.min()))


def clip2x(x, threshold=0.72):
    """Soft clip at 2x oversampling (less aliasing)."""
    up = signal.resample_poly(x, 2, 1, axis=0)
    up = soft_clip(up, threshold)
    return signal.resample_poly(up, 1, 2, axis=0)[: x.shape[0]].astype(F32)


def prepare(mix, s, sr=SR):
    """Static part of the chain (EQ, mono-bass, glue). Output normalised to ≈ -16 LUFS."""
    x = np.nan_to_num(np.asarray(mix, dtype=F32))
    x = hp(x, 20.0, 2, sr)
    x = widen(x, s.width, s.mono_below, sr)
    if s.low_shelf_db:
        x = eq_lowshelf(x, s.low_shelf_hz, s.low_shelf_db, 0.707, sr)
    if s.mud_cut_db:
        x = eq_peak(x, 300.0, -abs(s.mud_cut_db), 0.9, sr)
    if s.high_shelf_db:
        x = eq_highshelf(x, s.high_shelf_hz, s.high_shelf_db, 0.707, sr)
    l0 = lufs(x, sr)
    x = (x * 10 ** ((-16.0 - l0) / 20.0)).astype(F32)
    if s.glue_ratio > 1.0 and s.glue_gr_db > 0:
        # threshold placed relative to the loud parts so the glue does ≈ glue_gr_db on peaks
        env = np.abs(x).max(axis=1)
        p95 = float(np.percentile(env[env > 1e-4], 99.0)) if np.any(env > 1e-4) else 0.1
        thr = 20 * np.log10(p95 + 1e-9) - s.glue_gr_db / (1 - 1 / s.glue_ratio)
        x = compressor(x, thr, s.glue_ratio, attack_ms=30.0, release_ms=180.0, knee_db=8.0, sr=sr)
        l1 = lufs(x, sr)
        x = (x * 10 ** ((-16.0 - l1) / 20.0)).astype(F32)
    return x


def finalize(x, s, sr=SR, verbose=False):
    """Loudness loop: find input gain so that gain→clip→limit lands on ``s.lufs``."""
    target = s.lufs
    gain_db = target + 16.0 + 1.0  # first guess (prepared signal sits at -16 LUFS)
    y, best = None, None
    for it in range(5):
        z = (x * 10 ** (gain_db / 20.0)).astype(F32)
        z = clip2x(z, s.clip_threshold)
        z, gr = limiter(z, s.ceiling_dbtp, 5.0, s.limiter_release_ms, sr)
        L = lufs(z, sr)
        if verbose:
            print(f"    master it{it}: gain {gain_db:+.2f} dB → {L:.2f} LUFS (lim {gr:.1f} dB)")
        y = z
        best = L
        err = target - L
        if abs(err) < 0.25:
            break
        gain_db += err * (1.25 if err > 0 else 1.0)
    # remove DC, short fade at the very end only (sample 0 must stay the downbeat)
    y = y - y.mean(axis=0, keepdims=True)
    k = min(int(0.02 * sr), y.shape[0])
    y[-k:] *= np.linspace(1, 0, k, dtype=F32)[:, None]
    y = np.clip(y, -1.0, 1.0)
    return y.astype(F32), best


def master(mix, settings, sr=SR, verbose=False):
    x = prepare(mix, settings, sr)
    return finalize(x, settings, sr, verbose)
