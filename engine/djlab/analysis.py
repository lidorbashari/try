"""Objective 'ears' for agents that cannot listen.

``python -m djlab analyze <file.mp3> [--genre slug] [--json]`` prints: loudness (LUFS, true peak,
crest, PLR), band balance vs a genre reference curve, stereo correlation per band (sub must be
mono), BPM check, clipping, silence gaps, click detection, and per-phrase loudness (arrangement
dynamics) when the sidecar is present.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import signal

from . import SR

BANDS = [("sub", 20, 60), ("low", 60, 250), ("low_mid", 250, 800), ("mid", 800, 3000),
         ("high_mid", 3000, 8000), ("air", 8000, 20000)]

# Reference band balance (dB relative to total power) for well-mixed modern masters per style.
# Derived from typical spectra of commercial club/urban masters; tolerance ±3 dB is "fine".
REFERENCE = {
    "four_on_floor": {"sub": -6.5, "low": -3.8, "low_mid": -9.5, "mid": -11.5, "high_mid": -15.5, "air": -21.0},
    "techno":        {"sub": -6.0, "low": -3.6, "low_mid": -10.0, "mid": -12.0, "high_mid": -15.5, "air": -21.0},
    "melodic":       {"sub": -6.5, "low": -4.0, "low_mid": -9.0, "mid": -11.0, "high_mid": -15.0, "air": -20.5},
    "bass_heavy":    {"sub": -4.0, "low": -4.5, "low_mid": -10.5, "mid": -12.5, "high_mid": -16.0, "air": -21.5},
    "bright":        {"sub": -7.5, "low": -4.5, "low_mid": -9.0, "mid": -10.0, "high_mid": -13.5, "air": -18.5},
    "lofi":          {"sub": -7.0, "low": -3.5, "low_mid": -8.0, "mid": -11.0, "high_mid": -17.0, "air": -24.0},
}
GENRE_CURVE = {
    "deep_house": "four_on_floor", "house": "four_on_floor", "tech_house": "four_on_floor",
    "afro_house": "four_on_floor", "nu_disco": "bright", "amapiano": "bass_heavy",
    "techno": "techno", "melodic_techno": "melodic", "hypnotic_techno": "techno", "hard_techno": "techno",
    "big_room": "bright", "pop_dance": "bright", "hip_hop": "bass_heavy", "reggaeton": "bass_heavy",
    "moombahton": "bass_heavy", "afrobeats": "four_on_floor", "mediterranean": "four_on_floor",
    "psytrance": "techno", "trance": "bright", "dnb": "bass_heavy", "dubstep": "bass_heavy",
    "ukg": "bass_heavy", "breaks": "four_on_floor", "lofi": "lofi",
}
TARGET_LUFS = {"hip_hop": -11.0, "lofi": -12.0}


def load_audio(path, sr=SR) -> np.ndarray:
    p = Path(path)
    if p.suffix.lower() == ".wav":
        import soundfile as sf

        x, fs = sf.read(str(p), dtype="float32", always_2d=True)
        if x.shape[1] == 1:
            x = np.repeat(x, 2, axis=1)
        return x[:, :2]
    from .export import decode

    return decode(p, sr)


def band_energies(x, sr=SR) -> dict:
    m = x.mean(axis=1)
    f, p = signal.welch(m, sr, nperseg=16384, noverlap=8192)
    tot = p[(f >= 20) & (f <= 20000)].sum() + 1e-20
    return {name: round(float(10 * np.log10(p[(f >= lo) & (f < hi)].sum() / tot + 1e-20)), 2)
            for name, lo, hi in BANDS}


def band_correlation(x, sr=SR) -> dict:
    out = {}
    for name, lo, hi in BANDS:
        sos = signal.butter(4, [lo, min(hi, sr / 2 - 100)], "bandpass", fs=sr, output="sos")
        y = signal.sosfilt(sos, x[:: 1], axis=0)
        l, r = y[:, 0], y[:, 1]
        den = np.sqrt((l * l).sum() * (r * r).sum()) + 1e-20
        out[name] = round(float((l * r).sum() / den), 3)
    return out


def detect_clicks(x, sr=SR, max_report=10):
    """Very short broadband spikes relative to the local high-frequency energy (not drum hits)."""
    m = x.mean(axis=1)
    d2 = np.abs(np.diff(m, 2))
    win = int(0.02 * sr)
    k = np.ones(win) / win
    local = np.sqrt(signal.fftconvolve(d2 ** 2, k, mode="same")) + 1e-6
    ratio = d2 / local
    idx = np.where((ratio > 14.0) & (d2 > 0.05))[0]
    events, last = [], -sr
    for i in idx:
        if i - last > sr * 0.05:
            events.append(round(i / sr, 3))
        last = i
    return events[:max_report], len(events)


def silence_gaps(x, sr=SR, thr_db=-60.0, min_sec=0.5):
    hop = int(0.05 * sr)
    m = np.abs(x).max(axis=1)
    nwin = m.shape[0] // hop
    frames = m[: nwin * hop].reshape(nwin, hop).max(axis=1)
    quiet = 20 * np.log10(frames + 1e-12) < thr_db
    gaps, start = [], None
    for i, q in enumerate(quiet):
        if q and start is None:
            start = i
        if (not q or i == len(quiet) - 1) and start is not None:
            dur = (i - start) * hop / sr
            if dur >= min_sec:
                gaps.append((round(start * hop / sr, 2), round(dur, 2)))
            start = None
    return gaps


def leading_silence_ms(x, sr=SR, thr_db=-50.0) -> float:
    m = np.abs(x).max(axis=1)
    idx = np.where(m > 10 ** (thr_db / 20))[0]
    return float(idx[0] / sr * 1000) if idx.size else float("inf")


def estimate_bpm(x, sr=SR, expected=None) -> float:
    import librosa

    m = x.mean(axis=1)
    y = librosa.resample(m[: sr * 120], orig_sr=sr, target_sr=22050) if m.shape[0] > 0 else m
    env = librosa.onset.onset_strength(y=y, sr=22050, hop_length=256)
    kw = {"start_bpm": expected} if expected else {}
    tempo = librosa.feature.tempo(onset_envelope=env, sr=22050, hop_length=256, aggregate=np.median, **kw)
    return float(np.atleast_1d(tempo)[0])


def bpm_ok(est, expected, tol=0.03) -> bool:
    for mult in (1.0, 0.5, 2.0, 2 / 3, 1.5):
        if abs(est - expected * mult) <= expected * mult * tol:
            return True
    return False


def phrase_loudness(x, bpm, sr=SR, bars=8):
    """Short-term loudness per 8-bar phrase (dB RMS of K-ish weighted mono)."""
    spb = int(round(bars * 4 * 60 / bpm * sr))
    m = signal.sosfilt(signal.butter(2, 60, "highpass", fs=sr, output="sos"), x.mean(axis=1))
    out = []
    for i in range(0, m.shape[0] - spb // 2, spb):
        seg = m[i:i + spb]
        out.append(round(float(10 * np.log10((seg ** 2).mean() + 1e-12)), 1))
    return out


def analyze(x, sr=SR, genre=None, bpm=None, target_lufs=None) -> dict:
    from .master import lufs
    from .dsp import oversampled_peak

    rep: dict = {}
    L = lufs(x, sr)
    tp = float(20 * np.log10(oversampled_peak(x).max() + 1e-12))
    rms = float(np.sqrt((x ** 2).mean()) + 1e-12)
    rep["duration_sec"] = round(x.shape[0] / sr, 3)
    rep["lufs"] = round(L, 2)
    rep["true_peak_dbtp"] = round(tp, 2)
    rep["crest_db"] = round(float(20 * np.log10(np.abs(x).max() / rms)), 2)
    rep["plr_db"] = round(tp - L, 2)
    rep["leading_silence_ms"] = round(leading_silence_ms(x, sr), 2)
    rep["dc_offset"] = [round(float(v), 5) for v in x.mean(axis=0)]
    rep["clipped_samples"] = int((np.abs(x) >= 0.9999).sum())
    rep["bands_db"] = band_energies(x, sr)
    curve_name = GENRE_CURVE.get(genre or "", "four_on_floor")
    ref = REFERENCE[curve_name]
    rep["reference_curve"] = curve_name
    rep["bands_delta_db"] = {k: round(rep["bands_db"][k] - ref[k], 2) for k in ref}
    rep["band_correlation"] = band_correlation(x, sr)
    side = (x[:, 0] - x[:, 1]) * 0.5
    mid = (x[:, 0] + x[:, 1]) * 0.5
    rep["side_to_mid_db"] = round(float(10 * np.log10((side ** 2).mean() / ((mid ** 2).mean() + 1e-20) + 1e-20)), 2)
    clicks, nclicks = detect_clicks(x, sr)
    rep["clicks"] = {"count": nclicks, "first_at_sec": clicks}
    rep["silence_gaps"] = silence_gaps(x[: max(0, x.shape[0] - sr)], sr)
    if bpm:
        est = estimate_bpm(x, sr, bpm)
        rep["bpm_expected"] = bpm
        rep["bpm_estimated"] = round(est, 2)
        rep["bpm_ok"] = bpm_ok(est, bpm)
        rep["phrase_loudness_db"] = phrase_loudness(x, bpm, sr)
    # ---- advice
    adv = []
    tl = target_lufs if target_lufs is not None else TARGET_LUFS.get(genre or "", -9.0)
    rep["target_lufs"] = tl
    if abs(L - tl) > 1.5:
        adv.append(f"loudness {L:.1f} LUFS is off target {tl} (±1.5)")
    if tp > -1.0:
        adv.append(f"true peak {tp:.2f} dBTP > -1.0")
    for k, dv in rep["bands_delta_db"].items():
        if dv > 3.0:
            adv.append(f"{k} is {dv:+.1f} dB above the {curve_name} reference → reduce/EQ elements living there")
        elif dv < -3.0:
            adv.append(f"{k} is {dv:+.1f} dB below the {curve_name} reference → add/brighten elements there")
    if rep["band_correlation"]["sub"] < 0.95:
        adv.append("sub band is not mono (corr < 0.95) → mono the bass/kick below ~120 Hz")
    if rep["band_correlation"]["low"] < 0.8:
        adv.append("low band is wide/phasey (corr < 0.8)")
    if rep["side_to_mid_db"] < -20:
        adv.append("mix is almost mono → pan percussion / widen pads, add stereo reverb")
    if rep["side_to_mid_db"] > -4:
        adv.append("very wide mix (side ≈ mid) → check mono compatibility")
    if rep["crest_db"] < 7:
        adv.append("crest factor < 7 dB → over-compressed / squashed")
    if rep["clipped_samples"] > 0:
        adv.append(f"{rep['clipped_samples']} samples at full scale (clipping)")
    if nclicks:
        adv.append(f"{nclicks} possible clicks (first at {clicks[:3]} s) → add fades to note/sample ends")
    if rep["silence_gaps"]:
        adv.append(f"silence gaps: {rep['silence_gaps'][:3]}")
    if rep["leading_silence_ms"] > 5:
        adv.append(f"leading silence {rep['leading_silence_ms']} ms (must start on the downbeat)")
    if bpm and not rep.get("bpm_ok", True):
        adv.append(f"BPM estimate {rep['bpm_estimated']} does not match {bpm}")
    rep["advice"] = adv
    rep["ok"] = not any(("true peak" in a) or ("leading silence" in a) or ("clipping" in a) for a in adv)
    return rep


def analyze_file(path, genre=None, bpm=None) -> dict:
    p = Path(path)
    side = p.with_suffix(".json")
    meta = {}
    if side.exists():
        try:
            meta = json.loads(side.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    genre = genre or meta.get("genre_slug")
    bpm = bpm or meta.get("bpm")
    x = load_audio(p)
    rep = analyze(x, SR, genre, bpm)
    rep["file"] = str(p)
    return rep


def format_report(rep: dict) -> str:
    L = []
    L.append(f"== {rep.get('file', '')}")
    L.append(f"  duration {rep['duration_sec']} s · {rep['lufs']} LUFS (target {rep['target_lufs']}) · "
             f"TP {rep['true_peak_dbtp']} dBTP · crest {rep['crest_db']} dB · PLR {rep['plr_db']} dB")
    if "bpm_expected" in rep:
        L.append(f"  BPM expected {rep['bpm_expected']} · estimated {rep['bpm_estimated']} · "
                 f"{'OK' if rep['bpm_ok'] else 'MISMATCH'}")
    L.append(f"  leading silence {rep['leading_silence_ms']} ms · clipped samples {rep['clipped_samples']} · "
             f"clicks {rep['clicks']['count']} · side/mid {rep['side_to_mid_db']} dB")
    L.append(f"  band       level   Δref   corr   (reference: {rep['reference_curve']})")
    for name, _, _ in BANDS:
        d = rep["bands_delta_db"][name]
        bar = ("+" * int(min(10, max(0, d))) if d > 0 else "-" * int(min(10, max(0, -d))))
        L.append(f"  {name:<9}{rep['bands_db'][name]:7.1f} {d:+6.1f} {rep['band_correlation'][name]:6.2f}   {bar}")
    if rep.get("phrase_loudness_db"):
        L.append("  8-bar phrase loudness (dB): " + " ".join(f"{v:.0f}" for v in rep["phrase_loudness_db"]))
    if rep["advice"]:
        L.append("  advice:")
        L += [f"   - {a}" for a in rep["advice"]]
    else:
        L.append("  advice: none — within reference")
    return "\n".join(L)
