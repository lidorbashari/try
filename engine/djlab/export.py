"""Export: float WAV (temp) → MP3 320 kbps CBR via ffmpeg/libmp3lame, ID3v2.4 tags (mutagen),
sidecar JSON (SCHEMA §2) with loudness / true peak measured on the *decoded MP3*.

Gapless / first-downbeat note: LAME prepends an encoder delay (576 + 529 samples) and pads the end.
ffmpeg writes a Xing/LAME info header with the exact delay/padding, and decoders that honour it
(ffmpeg, Rekordbox, Traktor, Serato, foobar, browsers) trim it, so sample 0 of the decoded MP3 is
exactly beat 1. Very old players that ignore the header start ~25 ms late.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from mutagen.id3 import APIC, COMM, ID3, TALB, TBPM, TCON, TCOP, TDRC, TIT2, TKEY, TPE1, TSSE

from . import ARTIST, ENGINE_VERSION, REPO_ROOT, SR, scratch_dir
from .dsp import lin2db, oversampled_peak


def encode_mp3(audio: np.ndarray, path: Path, sr: int = SR, bitrate: str = "320k") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".wav", dir=scratch_dir(), delete=False) as tf:
        tmp = Path(tf.name)
    try:
        sf.write(tmp, np.asarray(audio, dtype=np.float32), sr, subtype="FLOAT")
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(tmp), "-map_metadata", "-1", "-c:a", "libmp3lame",
               "-b:a", bitrate, "-ar", str(sr), "-ac", "2", "-id3v2_version", "0", "-write_id3v1", "0",
               "-write_xing", "1", str(path)]
        subprocess.run(cmd, check=True)
    finally:
        tmp.unlink(missing_ok=True)


def decode(path, sr: int = SR) -> np.ndarray:
    """Decode any audio file to float32 stereo with ffmpeg (honours the LAME gapless header)."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(sr), "pipe:1"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()


def measure(audio: np.ndarray, sr: int = SR) -> tuple[float, float]:
    from .master import lufs

    return round(lufs(audio, sr), 2), round(float(lin2db(oversampled_peak(audio).max())), 2)


def write_tags(path, plan: dict, cover_jpg: bytes | None = None) -> None:
    fam = plan.get("family", "")
    tags = ID3()
    tags.add(TIT2(encoding=3, text=plan["title"]))
    tags.add(TPE1(encoding=3, text=ARTIST))
    tags.add(TALB(encoding=3, text=f"DJ Lab — {fam} Vol. 1"))
    tags.add(TCON(encoding=3, text=plan["genre"]))
    tags.add(TBPM(encoding=3, text=str(int(round(float(plan["bpm"]))))))
    tags.add(TKEY(encoding=3, text=plan.get("key_short", "")))
    tags.add(COMM(encoding=3, lang="eng", desc="",
                  text=f"Camelot {plan.get('camelot', '')} · Energy {plan.get('energy', '')} · CC0"))
    tags.add(TDRC(encoding=3, text="2026"))
    tags.add(TCOP(encoding=3, text="CC0 1.0"))
    tags.add(TSSE(encoding=3, text=f"djlab {ENGINE_VERSION}"))
    if cover_jpg:
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_jpg))
    tags.save(str(path), v2_version=4)


def export_mp3_safe(audio, path, sr=SR, max_tp=-1.0, verbose=False):
    """Encode, decode, verify true peak ≤ ``max_tp``; if not, trim gain and re-encode."""
    gain = 1.0
    for it in range(4):
        encode_mp3(audio * gain, path, sr)
        dec = decode(path, sr)
        L, tp = measure(dec, sr)
        if verbose:
            print(f"    mp3 it{it}: {L:.2f} LUFS, TP {tp:.2f} dBTP")
        if tp <= max_tp - 0.05:
            return dec, L, tp
        gain *= 10 ** ((max_tp - 0.15 - tp) / 20.0)
    return dec, L, tp


def rel(p: Path) -> str:
    try:
        return Path(p).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(p)


def sidecar(song, plan: dict, mp3_path: Path, cover_path: Path, lufs_v: float, tp: float, duration: float) -> dict:
    return {
        "id": plan["id"], "title": plan["title"], "title_he": plan.get("title_he", ""),
        "artist": ARTIST, "genre": plan["genre"], "genre_slug": plan["genre_slug"], "family": plan["family"],
        "bpm": float(plan["bpm"]), "key": plan["key"], "key_short": plan["key_short"], "camelot": plan["camelot"],
        "energy": int(plan["energy"]), "role": plan["role"],
        "duration_sec": round(duration, 3), "bars": song.total_bars, "beats_per_bar": 4,
        "first_downbeat_sec": 0.0,
        "sections": song.sections_meta(),
        "cues": song.cues(),
        "memory_cues": song.memory_cues(),
        "lufs": lufs_v, "true_peak_dbtp": tp,
        "file": rel(mp3_path), "cover": rel(cover_path),
        "description_he": song.description_he,
        "mix_tips_he": song.mix_tips_he or song.auto_mix_tips_he(),
        "instruments": list(song.instruments),
        "seed": int(plan["seed"]), "license": "CC0-1.0", "engine_version": ENGINE_VERSION,
    }


def write_json(path: Path, data: dict) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
