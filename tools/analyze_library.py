#!/usr/bin/env python3
"""Analyze YOUR OWN music folder (legally bought tracks) for DJ prep.

For every audio file (mp3 / wav / aiff / flac / m4a / aac / ogg / opus) it measures:
  * BPM  - onset envelope + autocorrelation, refined by phase-folding to ~0.05 BPM, with half/double
           correction into a sensible 70-180 range (alt octave reported in `bpm_alt`)
  * key  - harmonic CQT chroma (HPSS) correlated with an ensemble of key profiles
           (Krumhansl-Kessler, Temperley, Albrecht-Shanahan); major/minor, Camelot, confidence 0..1
  * LUFS - integrated loudness (ITU-R BS.1770 via pyloudnorm) + sample peak
  * duration, a rough energy estimate (1-10), and the BPM/key already written in the file tags
    (Rekordbox / Mixed In Key / Beatport) with a mismatch flag.

Audio never leaves your computer and nothing is copied into the repo - only a CSV of numbers is written.

Usage:
  python tools/analyze_library.py ~/Music/MyDJ                       # -> library/my_library.csv
  python tools/analyze_library.py ~/Music/MyDJ --jobs 4 --sample 60   # faster: 60 s from the middle
  python tools/analyze_library.py a.mp3 b.flac --out /tmp/x.csv --force
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import camelot  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "library" / "my_library.csv"
AUDIO_EXT = {".mp3", ".wav", ".aif", ".aiff", ".flac", ".m4a", ".mp4", ".aac", ".ogg", ".opus", ".alac"}
SR = 44100          # decode rate (loudness)
SR_A = 22050        # analysis rate (tempo / key)
BPM_MIN, BPM_MAX = 70.0, 180.0

COLUMNS = [
    "path", "artist", "title", "genre_tag", "duration_sec", "bpm", "bpm_alt", "bpm_confidence",
    "key", "key_short", "camelot", "key_confidence", "key_alt_camelot", "lufs", "peak_dbfs",
    "energy_est", "tag_bpm", "tag_key", "tag_camelot", "bpm_check", "key_check",
    "analyzed_sec", "size_bytes", "mtime", "error",
]

# ---------------------------------------------------------------- key profiles (C = index 0)
_PROFILES = {
    "krumhansl": (
        [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
        [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    ),
    "temperley": (
        [0.748, 0.060, 0.488, 0.082, 0.670, 0.460, 0.096, 0.715, 0.104, 0.366, 0.057, 0.400],
        [0.712, 0.084, 0.474, 0.618, 0.049, 0.460, 0.105, 0.747, 0.404, 0.067, 0.133, 0.330],
    ),
    "albrecht_shanahan": (
        [0.238, 0.006, 0.111, 0.006, 0.137, 0.094, 0.016, 0.214, 0.009, 0.080, 0.008, 0.081],
        [0.220, 0.006, 0.104, 0.123, 0.019, 0.103, 0.012, 0.214, 0.062, 0.022, 0.061, 0.052],
    ),
}


def _z(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    s = v.std()
    return (v - v.mean()) / (s if s > 1e-12 else 1.0)


_KEY_TEMPLATES = []  # (pc, minor, zscored template) for 24 keys x N profiles
for _maj, _min in _PROFILES.values():
    for _pc in range(12):
        _KEY_TEMPLATES.append((_pc, False, _z(np.roll(_maj, _pc))))
        _KEY_TEMPLATES.append((_pc, True, _z(np.roll(_min, _pc))))


# ---------------------------------------------------------------- decoding / tags
def probe_duration(path: Path) -> float | None:
    try:
        import mutagen
        mf = mutagen.File(str(path))
        if mf is not None and getattr(mf, "info", None) and getattr(mf.info, "length", 0):
            return float(mf.info.length)
    except Exception:
        pass
    if shutil.which("ffprobe"):
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                capture_output=True, text=True, timeout=60,
            )
            return float(json.loads(r.stdout)["format"]["duration"])
        except Exception:
            return None
    return None


def decode(path: Path, offset: float = 0.0, duration: float | None = None) -> np.ndarray:
    """Return float32 stereo (n, 2) at 44.1 kHz. Uses ffmpeg when available, else librosa."""
    if shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-nostdin", "-v", "error"]
        if offset > 0:
            cmd += ["-ss", f"{offset:.3f}"]
        if duration:
            cmd += ["-t", f"{duration:.3f}"]
        cmd += ["-i", str(path), "-vn", "-map", "0:a:0", "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"]
        r = subprocess.run(cmd, capture_output=True, timeout=600)
        if r.returncode != 0 or not r.stdout:
            raise RuntimeError(f"ffmpeg failed: {r.stderr.decode(errors='ignore').strip()[:200]}")
        return np.frombuffer(r.stdout, dtype=np.float32).reshape(-1, 2)
    import librosa
    y, _ = librosa.load(str(path), sr=SR, mono=False, offset=offset, duration=duration)
    y = np.atleast_2d(y)
    if y.shape[0] == 1:
        y = np.vstack([y, y])
    return y.T.astype(np.float32)


def _first(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        v = v[0] if v else ""
    if isinstance(v, bytes):
        v = v.decode("utf-8", errors="ignore")
    if hasattr(v, "text"):
        return _first(v.text)
    return str(v).strip()


def read_tags(path: Path) -> dict:
    out = {"artist": "", "title": "", "genre_tag": "", "tag_bpm": "", "tag_key": ""}
    try:
        import mutagen
        mf = mutagen.File(str(path))
    except Exception:
        return out
    if mf is None or mf.tags is None:
        return out
    tags = mf.tags
    try:
        if hasattr(tags, "getall"):  # ID3 (mp3 / aiff / wav)
            def g(fid: str) -> str:
                frames = tags.getall(fid)
                return _first(frames[0]) if frames else ""
            out.update(artist=g("TPE1"), title=g("TIT2"), genre_tag=g("TCON"), tag_bpm=g("TBPM"), tag_key=g("TKEY"))
            if not out["tag_key"]:
                for fr in tags.getall("TXXX"):
                    if str(getattr(fr, "desc", "")).lower() in {"initialkey", "initial key", "key"}:
                        out["tag_key"] = _first(fr)
                        break
        elif type(tags).__name__ == "MP4Tags":
            out.update(artist=_first(tags.get("\xa9ART")), title=_first(tags.get("\xa9nam")),
                       genre_tag=_first(tags.get("\xa9gen")), tag_bpm=_first(tags.get("tmpo")))
            for k in tags.keys():
                if k.lower().endswith(":initialkey") or k.lower().endswith(":key"):
                    out["tag_key"] = _first(tags[k])
                    break
        else:  # Vorbis comments (flac / ogg / opus) and others
            low = {str(k).lower(): v for k, v in tags.items()}
            out.update(artist=_first(low.get("artist")), title=_first(low.get("title")),
                       genre_tag=_first(low.get("genre")),
                       tag_bpm=_first(low.get("bpm") or low.get("tbpm")),
                       tag_key=_first(low.get("initialkey") or low.get("key") or low.get("tkey")))
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- tempo
def _fold_strength(env: np.ndarray, period: float) -> tuple[float, np.ndarray]:
    nb = max(16, int(round(period)))
    phase = (np.arange(len(env)) / period) % 1.0
    idx = np.minimum((phase * nb).astype(int), nb - 1)
    cnt = np.bincount(idx, minlength=nb)
    prof = np.bincount(idx, weights=env, minlength=nb) / np.maximum(cnt, 1)
    return float(prof.max() / (prof.mean() + 1e-9)), prof


def estimate_bpm(y: np.ndarray, sr: int) -> dict:
    import librosa
    hop = 256
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    env = np.maximum(env - np.median(env), 0)
    if env.max() <= 0 or len(env) < 200:
        return {"bpm": None, "bpm_alt": None, "bpm_confidence": 0.0, "onset_rate": 0.0}
    fps = sr / hop
    # coarse: librosa tempogram estimate with a log-normal prior around 120 BPM
    try:
        coarse = float(librosa.feature.tempo(onset_envelope=env, sr=sr, hop_length=hop)[0])
    except AttributeError:  # librosa < 0.10
        coarse = float(librosa.beat.tempo(onset_envelope=env, sr=sr, hop_length=hop)[0])
    # also take the strongest autocorrelation peak in 60-200 BPM as a second opinion
    ac = librosa.autocorrelate(env, max_size=int(fps * 60 / 55))
    lags = np.arange(len(ac))
    valid = (lags >= fps * 60 / 200) & (lags <= fps * 60 / 60)
    ac_bpm = 60 * fps / lags[valid][np.argmax(ac[valid])] if valid.any() else coarse

    def refine(b0: float, width: float = 0.025, step: float = 0.01) -> tuple[float, float]:
        grid = np.arange(b0 * (1 - width), b0 * (1 + width), step)
        scores = np.array([_fold_strength(env, 60 * fps / b)[0] for b in grid])
        i = int(np.argmax(scores))
        return float(grid[i]), float(scores[i])

    cands: dict[float, float] = {}
    for b in {round(coarse, 2), round(float(ac_bpm), 2)}:
        while b < BPM_MIN:
            b *= 2
        while b > BPM_MAX:
            b /= 2
        rb, rs = refine(b)
        cands[rb] = rs
    bpm = max(cands, key=cands.get)
    strength = cands[bpm]
    # octave ambiguity inside the 70-180 window (e.g. 87 vs 174, 70 vs 140, 85 vs 170)
    alt = None
    slow, fast = (bpm, bpm * 2) if bpm * 2 <= BPM_MAX else ((bpm / 2, bpm) if bpm / 2 >= BPM_MIN else (None, None))
    if slow:
        _, prof = _fold_strength(env, 60 * fps / slow)
        nb = len(prof)
        main = int(np.argmax(prof))
        half_val = float(max(prof[(main + nb // 2 + d) % nb] for d in (-1, 0, 1)))
        ratio = (half_val - prof.mean()) / (prof[main] - prof.mean() + 1e-9)
        if fast >= 160:
            # DnB (170-176) vs hip-hop/reggaeton (85-90): look at the snare/clap band. In DnB the snare
            # lands on every *slow* beat, so a fold over two slow beats shows two equal peaks.
            mid = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop, fmin=150.0, fmax=2000.0, n_mels=48)
            mid = np.maximum(mid - np.median(mid), 0)
            _, mp = _fold_strength(mid, 2 * 60 * fps / slow)
            n2, m2 = len(mp), int(np.argmax(mp))
            other = float(max(mp[(m2 + n2 // 2 + d) % n2] for d in (-1, 0, 1)))
            sym = (other - mp.mean()) / (mp[m2] - mp.mean() + 1e-9)
            chosen = fast if sym >= 0.6 else slow
        else:
            chosen = fast if ratio >= 0.55 else slow
        alt = slow if chosen == fast else fast
        if abs(chosen - bpm) > 1e-6:
            bpm, strength = refine(chosen, width=0.01)
    # snap to integer when within 0.06 BPM (most club tracks are produced at integer tempos)
    if abs(bpm - round(bpm)) < 0.06:
        bpm = float(round(bpm))
    conf = float(np.clip((strength - 1.3) / 2.2, 0.0, 1.0))
    onsets = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=hop, units="frames")
    return {"bpm": round(bpm, 2), "bpm_alt": round(alt, 2) if alt else None,
            "bpm_confidence": round(conf, 2), "onset_rate": len(onsets) / (len(env) / fps)}


# ---------------------------------------------------------------- key
def estimate_key(y: np.ndarray, sr: int) -> dict:
    import librosa
    hop = 2048
    try:
        tuning = float(librosa.estimate_tuning(y=y, sr=sr))
    except Exception:
        tuning = 0.0
    fmin = librosa.note_to_hz("C1")
    C = np.abs(librosa.cqt(y, sr=sr, hop_length=hop, fmin=fmin, n_bins=7 * 36, bins_per_octave=36, tuning=tuning))
    H, P = librosa.decompose.hpss(C, kernel_size=(17, 17))
    perc_ratio = float(P.sum() / (H.sum() + P.sum() + 1e-9))
    # suppress overtone ghosts (3rd harmonic = +19 semitones, 5th = +28): the 5th harmonic of a minor
    # chord's root is a *major* third and otherwise drags minor keys towards their parallel major
    H = H.copy()
    for semis, amount in ((28, 0.2), (19, 0.25)):
        sh = semis * 3
        H[sh:] = np.maximum(H[sh:] - amount * H[:-sh], 0.0)
    chroma = librosa.feature.chroma_cqt(C=H, sr=sr, hop_length=hop, fmin=fmin, bins_per_octave=36, norm=None)
    bass = librosa.feature.chroma_cqt(C=H[: 3 * 36], sr=sr, hop_length=hop, fmin=fmin, bins_per_octave=36,
                                      n_octaves=3, norm=None)
    vec = np.zeros(12)
    for ch, w in ((chroma, 1.0), (bass, 0.6)):
        ch = ch / (ch.max() + 1e-9)
        ch = np.log1p(10.0 * ch)
        v = ch.sum(axis=1)
        vec += w * v / (v.sum() + 1e-9)
    if not np.isfinite(vec).all() or vec.std() < 1e-9:
        return {"key": None, "key_confidence": 0.0, "key_alt": None, "perc_ratio": perc_ratio}
    zv = _z(vec)
    scores = np.zeros((24,))
    for pc, minor, tmpl in _KEY_TEMPLATES:
        scores[pc * 2 + int(minor)] += float(np.dot(zv, tmpl) / 12.0) / len(_PROFILES)
    # parallel major/minor (same tonic) are often within a hair: let the 3rd and 6th decide
    top = int(np.argmax(scores))
    tonic = top // 2
    par = tonic * 2 + (1 - top % 2)
    if scores[top] - scores[par] < 0.04:
        minor_ev = vec[(tonic + 3) % 12] + vec[(tonic + 8) % 12]
        major_ev = vec[(tonic + 4) % 12] + vec[(tonic + 9) % 12]
        win, lose = (tonic * 2 + 1, tonic * 2) if minor_ev > major_ev else (tonic * 2, tonic * 2 + 1)
        if scores[win] < scores[lose]:
            scores[win], scores[lose] = scores[lose] + 1e-3, scores[win]
    order = np.argsort(-scores)
    best, second = int(order[0]), int(order[1])
    if scores[best] < 0.38:  # no clear tonality (drum tools, noise, spoken word): don't guess
        return {"key": None, "key_confidence": 0.0, "key_alt": None, "perc_ratio": perc_ratio}
    p = np.exp((scores - scores.max()) / 0.04)
    p /= p.sum()
    # a relative major/minor runner-up is harmless for mixing (same Camelot number): count it as agreement
    kb = camelot.key_from_pc(best // 2, bool(best % 2))
    ks = camelot.key_from_pc(second // 2, bool(second % 2))
    conf = float(p[best])
    if kb.camelot[:-1] == ks.camelot[:-1]:
        conf = min(1.0, conf + 0.5 * float(p[second]))
    conf *= float(np.clip((scores[best] - 0.35) / 0.35, 0.0, 1.0))  # weak correlation = low confidence
    return {"key": kb, "key_confidence": round(conf, 2), "key_alt": ks, "perc_ratio": perc_ratio}


# ---------------------------------------------------------------- one file
def _check_bpm(tag: str, bpm: float | None) -> str:
    try:
        t = float(str(tag).replace(",", "."))
    except ValueError:
        return ""
    if not bpm or t <= 0:
        return ""
    if abs(t - bpm) / bpm <= 0.015:
        return "ok"
    if abs(t * 2 - bpm) / bpm <= 0.015 or abs(t / 2 - bpm) / bpm <= 0.015:
        return "half_double"
    return "mismatch"


def _check_key(tag_cam: str, cam: str) -> str:
    if not tag_cam or not cam:
        return ""
    if tag_cam == cam:
        return "ok"
    if tag_cam[:-1] == cam[:-1]:
        return "relative"
    h = camelot.harmonic_compat(tag_cam, cam)
    return "neighbor" if h.relation in ("+1", "-1") else "mismatch"


def analyze_file(path_str: str, sample: float | None) -> dict:
    path = Path(path_str)
    row: dict = {c: "" for c in COLUMNS}
    row["path"] = path_str
    try:
        st = path.stat()
        row["size_bytes"], row["mtime"] = st.st_size, int(st.st_mtime)
        row.update(read_tags(path))
        dur = probe_duration(path)
        offset, length = 0.0, None
        if sample and dur and dur > sample + 10:
            offset = max(0.0, dur * 0.5 - sample / 2)  # middle of the track: past the drums-only intro
            length = sample
        y = decode(path, offset, length)
        if len(y) < SR * 3:
            raise RuntimeError("audio shorter than 3 s")
        if not dur:
            dur = len(y) / SR
        row["duration_sec"] = round(dur, 1)
        row["analyzed_sec"] = round(len(y) / SR, 1)
        peak = float(np.max(np.abs(y)))
        row["peak_dbfs"] = round(20 * math.log10(peak), 1) if peak > 0 else -120.0
        try:
            import pyloudnorm as pyln
            lufs = pyln.Meter(SR).integrated_loudness(y.astype(np.float64))
            row["lufs"] = round(float(lufs), 1) if np.isfinite(lufs) else ""
        except Exception:
            row["lufs"] = ""
        from scipy.signal import resample_poly
        mono = resample_poly(y.mean(axis=1).astype(np.float64), 1, 2)
        t = estimate_bpm(mono, SR_A)
        k = estimate_key(mono, SR_A)
        row["bpm"] = t["bpm"] if t["bpm"] else ""
        row["bpm_alt"] = t["bpm_alt"] or ""
        row["bpm_confidence"] = t["bpm_confidence"]
        if k["key"]:
            row["key"], row["key_short"], row["camelot"] = k["key"].long, k["key"].short, k["key"].camelot
            row["key_alt_camelot"] = k["key_alt"].camelot if k["key_alt"] else ""
        row["key_confidence"] = k["key_confidence"]
        # rough energy 1..10: loudness + onset density + percussiveness + tempo
        lufs_v = row["lufs"] if row["lufs"] != "" else -14.0
        e = (0.35 * np.clip((lufs_v + 16) / 10, 0, 1)
             + 0.25 * np.clip((t["onset_rate"] - 1.0) / 7.0, 0, 1)
             + 0.20 * np.clip((k["perc_ratio"] - 0.2) / 0.5, 0, 1)
             + 0.20 * np.clip(((t["bpm"] or 110) - 85) / 60, 0, 1))
        row["energy_est"] = int(np.clip(round(1 + 9 * e), 1, 10))
        row["tag_camelot"] = camelot.to_camelot(row["tag_key"])
        row["bpm_check"] = _check_bpm(row["tag_bpm"], t["bpm"])
        row["key_check"] = _check_key(row["tag_camelot"], row["camelot"])
    except Exception as exc:  # keep going: one broken file must not stop a 2,000-track library
        row["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return row


# ---------------------------------------------------------------- summary (Hebrew)
def _num(v) -> float | None:
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def hebrew_summary(rows: list[dict], out_path: Path, elapsed: float) -> str:
    ok = [r for r in rows if not r.get("error") and _num(r.get("bpm"))]
    bad = [r for r in rows if r.get("error")]
    L = []
    L.append("")
    L.append("🎧 סיכום ניתוח הספרייה שלך")
    L.append("=" * 40)
    L.append(f"נותחו {len(ok)} קבצים ({len(bad)} שגיאות) תוך {elapsed:.0f} שניות.")
    L.append(f"קובץ התוצאות: {out_path}")
    if not ok:
        return "\n".join(L)
    bands = [(0, 100, "היפ-הופ / רגאטון / ים-תיכוני איטי"), (100, 115, "אפרוביטס / מומבהטון / ים-תיכוני"),
             (115, 124, "דיפ / אפרו / מלודי"), (124, 130, "האוס / טק-האוס / טכנו"),
             (130, 140, "טכנו / טראנס / UKG"), (140, 200, "פסיי / האַרד טכנו / DnB / דאבסטפ")]
    L.append("")
    L.append("התפלגות BPM:")
    for lo, hi, name in bands:
        n = sum(1 for r in ok if lo <= float(r["bpm"]) < hi)
        if n:
            L.append(f"  {lo:>3}–{hi:<3} | {'█' * min(30, n)} {n}  ({name})")
    cams: dict[str, int] = {}
    for r in ok:
        if r.get("camelot"):
            cams[r["camelot"]] = cams.get(r["camelot"], 0) + 1
    if cams:
        top = sorted(cams.items(), key=lambda x: -x[1])[:6]
        L.append("")
        L.append("הסולמות הנפוצים אצלך (Camelot): " + ", ".join(f"`{c}`×{n}" for c, n in top))
        missing = [f"{n}{l}" for n in range(1, 13) for l in "AB" if f"{n}{l}" not in cams]
        if missing:
            L.append(f"  אין לך אף טראק ב: {', '.join(missing[:12])}{' …' if len(missing) > 12 else ''}")
    lufs = [float(r["lufs"]) for r in ok if _num(r.get("lufs")) is not None]
    if lufs:
        med = float(np.median(lufs))
        quiet = [r for r in ok if _num(r.get("lufs")) is not None and float(r["lufs"]) < med - 3]
        loud = [r for r in ok if _num(r.get("lufs")) is not None and float(r["lufs"]) > med + 3]
        L.append("")
        L.append(f"עוצמה: חציון {med:.1f} LUFS. {len(quiet)} טראקים שקטים משמעותית, {len(loud)} רועשים משמעותית.")
        if quiet or loud:
            L.append("  טיפ: הדליקו `Auto Gain` ב-Rekordbox או כוונו `Trim` — אחרת המעברים יקפצו בווליום.")
            for r in (quiet + loud)[:5]:
                L.append(f"   · {Path(r['path']).name} → {r['lufs']} LUFS")
    mism_b = [r for r in ok if r.get("bpm_check") == "mismatch"]
    hd = [r for r in ok if r.get("bpm_check") == "half_double"]
    mism_k = [r for r in ok if r.get("key_check") == "mismatch"]
    if mism_b or hd or mism_k:
        L.append("")
        L.append("בדיקת התגיות הקיימות בקבצים:")
        if hd:
            L.append(f"  {len(hd)} טראקים עם BPM כפול/חצי בתגית — לא באג, רק לבחור תצוגה עקבית.")
        for r in mism_b[:8]:
            L.append(f"  ⚠ BPM: {Path(r['path']).name}: בתגית {r['tag_bpm']}, נמדד {r['bpm']} — בדקו את ה-Beatgrid.")
        for r in mism_k[:8]:
            L.append(f"  ⚠ Key: {Path(r['path']).name}: בתגית {r['tag_key']} ({r['tag_camelot']}), "
                     f"נמדד {r['key_short']} ({r['camelot']}) — הקשיבו באוזן / השוו ל-Beatport.")
    low = [r for r in ok if (_num(r.get("key_confidence")) or 0) < 0.35]
    if low:
        L.append("")
        L.append(f"{len(low)} טראקים עם ביטחון נמוך בזיהוי הסולם (למשל טראקים של תופים בלבד) — "
                 f"עמודת `key_alt_camelot` נותנת את האפשרות השנייה.")
    pairs = []
    for i, a in enumerate(ok):
        for b in ok[i + 1:]:
            h = camelot.harmonic_compat(a.get("camelot"), b.get("camelot"))
            tt = camelot.bpm_compat(_num(a["bpm"]), _num(b["bpm"]))
            if h.score >= 0.88 and tt.mode == "direct" and abs(tt.pct) <= 3:
                pairs.append((h.score + tt.score, a, b, h))
    if pairs:
        pairs.sort(key=lambda x: -x[0])
        L.append("")
        L.append("זוגות שכדאי לנסות במיקס (הרמוני + BPM קרוב):")
        for _, a, b, h in pairs[:5]:
            L.append(f"  ♫ {Path(a['path']).stem}  ({a['bpm']} · {a['camelot']})  ↔  "
                     f"{Path(b['path']).stem}  ({b['bpm']} · {b['camelot']})  — {h.label_he}")
    L.append("")
    L.append("מה הלאה?")
    L.append("  · ב-Rekordbox: Preferences → View → Key display format → Alphanumeric כדי לראות Camelot.")
    L.append("  · תכנון סט מהספרייה: `python tools/set_planner.py --minutes 60 --library "
             f"{out_path}` (או בקשו מ-Claude: \"תכין לי סט\").")
    L.append("  · מה מתאים אחרי טראק? בקשו: \"מה לנגן אחרי <שם טראק>?\" (סקיל harmonic-next-track).")
    L.append("  · ה-BPM/Key כאן הם הערכה אלגוריתמית — הבדיקה הסופית היא תמיד באוזניות.")
    if bad:
        L.append("")
        L.append("קבצים שנכשלו:")
        for r in bad[:10]:
            L.append(f"  ✗ {Path(r['path']).name}: {r['error']}")
    return "\n".join(L)


# ---------------------------------------------------------------- main
def find_audio(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for s in inputs:
        p = Path(os.path.expanduser(s))
        if p.is_file() and p.suffix.lower() in AUDIO_EXT:
            files.append(p)
        elif p.is_dir():
            files += sorted(q for q in p.rglob("*") if q.is_file() and q.suffix.lower() in AUDIO_EXT
                            and not q.name.startswith("._"))
        else:
            print(f"!! not found / not audio: {s}", file=sys.stderr)
    seen, uniq = set(), []
    for f in files:
        k = str(f.resolve())
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq


def _covers(old: dict, sample: float | None) -> bool:
    """Was the cached row analyzed with at least as much audio as requested now?"""
    got, dur = _num(old.get("analyzed_sec")) or 0.0, _num(old.get("duration_sec")) or 0.0
    full = abs(got - dur) < 1.5
    return full or (sample is not None and got >= sample - 0.5)


def load_existing(out: Path) -> dict[str, dict]:
    if not out.exists():
        return {}
    with out.open(encoding="utf-8-sig", newline="") as fh:
        return {r["path"]: r for r in csv.DictReader(fh)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="folder(s) and/or audio files")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help=f"CSV output (default: {DEFAULT_OUT.relative_to(ROOT)})")
    ap.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1), help="parallel workers")
    ap.add_argument("--sample", type=float, default=None,
                    help="analyze only N seconds from the middle of each file (e.g. 60) - much faster")
    ap.add_argument("--force", action="store_true", help="re-analyze files already in the CSV")
    ap.add_argument("--limit", type=int, default=0, help="analyze at most N files (testing)")
    ap.add_argument("--quiet", action="store_true", help="no per-file progress lines")
    args = ap.parse_args(argv)

    files = find_audio(args.inputs)
    if args.limit:
        files = files[: args.limit]
    if not files:
        print("לא נמצאו קבצי אודיו (mp3/wav/aiff/flac/m4a).", file=sys.stderr)
        return 1
    out = Path(os.path.expanduser(args.out))
    out.parent.mkdir(parents=True, exist_ok=True)
    existing = {} if args.force else load_existing(out)
    sample_tag = round(args.sample, 1) if args.sample else None

    rows: dict[str, dict] = {}
    todo: list[str] = []
    for f in files:
        key = str(f)
        old = existing.get(key)
        st = f.stat()
        if old and not old.get("error") and str(old.get("size_bytes")) == str(st.st_size) \
                and str(old.get("mtime")) == str(int(st.st_mtime)) and _covers(old, sample_tag):
            rows[key] = old
        else:
            todo.append(key)
    t0 = time.time()
    if not args.quiet and len(rows):
        print(f"· {len(rows)} קבצים כבר נותחו (מהקובץ הקיים) — מדלגים. --force כדי לנתח מחדש.", file=sys.stderr)
    done = 0

    def report(r: dict) -> None:
        nonlocal done
        done += 1
        if not args.quiet:
            msg = r["error"] or f"{r['bpm']} BPM · {r['key_short']} ({r['camelot']}) · {r['lufs']} LUFS"
            print(f"[{done}/{len(todo)}] {Path(r['path']).name}: {msg}", file=sys.stderr, flush=True)

    if args.jobs > 1 and len(todo) > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            futs = {ex.submit(analyze_file, p, args.sample): p for p in todo}
            for fu in as_completed(futs):
                r = fu.result()
                rows[r["path"]] = r
                report(r)
    else:
        for p in todo:
            r = analyze_file(p, args.sample)
            rows[p] = r
            report(r)

    ordered = [rows[str(f)] for f in files if str(f) in rows]
    # keep rows for files analyzed earlier that were not part of this run
    for k, r in existing.items():
        if k not in rows:
            ordered.append(r)
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in ordered:
            w.writerow(r)
    this_run = [rows[str(f)] for f in files if str(f) in rows]
    print(hebrew_summary(this_run, out, time.time() - t0))
    return 0 if any(not r.get("error") for r in this_run) else 2


if __name__ == "__main__":
    sys.exit(main())
