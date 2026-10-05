"""Offline two-deck DJ mixer: renders the transition demos of ``music/extras.plan.json`` →
``music/transitions/<id>-<technique>.{mp3,json}`` (SCHEMA §3).

    python -m djlab.djmix --list
    python -m djlab.djmix --id transition-02 [--out DIR]
    python -m djlab.djmix --all [--jobs 1]

The mixer works on our own rendered MP3s plus their sidecar JSON (exact BPM, cues; beatgrid starts
at 0.0 s), exactly like a DJ on two decks:

* **Tempo matching** — deck B is resampled to A's BPM ("vinyl" pitch, ≤ ~3 %), or time-stretched
  (rubberband via ffmpeg, librosa fallback) for bigger gaps; tempo-change demos play B at its own BPM.
* **Bar-exact alignment** — B's start bar (usually a Hot Cue) lands sample-exactly on A's phrase.
* **Per-deck automation** (piecewise-linear lanes in seconds, written in bars/beats by the recipes):
  channel fader, 3-band isolator EQ (Linkwitz-Riley 200 Hz / 2.5 kHz, kill = −26 dB), one-knob
  LPF/HPF colour filter, beat-synced echo (post-fader send, so its tail keeps ringing after the
  fader closes), slip loop roll (1 → 1/2 → 1/4 → 1/8 beat, crossfaded loop points), hard cuts on
  the downbeat (4 ms ramps).
* **Master** — gentle glue compressor + 4×-oversampled look-ahead limiter, −10 LUFS, true peak
  ≤ −1 dBTP measured on the decoded MP3.

Every move is logged as a timeline event; the "step" events become ``steps_he`` (Hebrew, with exact
demo times) and Hot Cues A–H. ``bar`` fields are 0-based bar indexes of the demo's own grid (SCHEMA
convention, like track cues); the Hebrew text counts bars from 1. Deterministic: no randomness.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path
from typing import Callable

import numpy as np
from scipy import signal
from scipy.ndimage import maximum_filter1d, uniform_filter1d

from . import ENGINE_VERSION, REPO_ROOT, SR, TRACKS_DIR, scratch_dir
from .dsp import F32

EXTRAS_PATH = REPO_ROOT / "music" / "extras.plan.json"
OUT_DIR = REPO_ROOT / "music" / "transitions"
ARTIST = "DJ Lab Transitions"
ALBUM = "DJ Lab — Transitions"
GENRE = "Transition Demo"
TARGET_LUFS = -10.0
KILL_DB = -26.0
EQ_LOW_HZ, EQ_HIGH_HZ = 200.0, 2500.0
DECK_TRIM_DB = -3.0          # channel trim on both decks: headroom for the overlap
RESAMPLE_MAX = 0.031         # ≤ ~3 % → vinyl-style resample, above → time-stretch
DECLICK = 96                 # samples of crossfade at loop-roll jump points
SLOT_COLORS = {"A": "#28E214", "B": "#10B1E6", "C": "#E0641B", "D": "#E62828", "E": "#B4BE04",
               "F": "#DE44CF", "G": "#305AFF", "H": "#8A2BE2"}
TECH_EN = {"blend": "Long Blend", "bass_swap": "Bass Swap", "filter": "Filter Transition",
           "echo_out": "Echo Out", "cut": "Cut / Slam", "loop_roll": "Loop Roll",
           "energy_boost": "Energy Boost +2", "tempo_change_echo": "Tempo Change Echo Out",
           "drop_swap": "Drop Swap", "breakdown_mix": "Breakdown Mix"}


# ============================================================================ helpers
def mmss(t: float) -> str:
    """Player-style time (floor to the second): the event happens during this displayed second."""
    t = max(0.0, t + 1e-6)
    return f"{int(t // 60)}:{int(t % 60):02d}"


def mmss1(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 60)}:{t % 60:04.1f}"


def pct(new: float, old: float) -> str:
    """Signed percentage with a left-to-right mark so the sign stays put inside Hebrew text."""
    return f"\u200e{(new / old - 1) * 100:+.1f}%"


def load_extras(path: Path = EXTRAS_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")).get("transitions", [])


_AUDIO: dict[str, np.ndarray] = {}


class Track:
    """One of our rendered tracks: sidecar metadata + decoded audio (sample 0 = beat 1 of bar 1)."""

    def __init__(self, tid: str):
        hits = sorted(TRACKS_DIR.glob(f"*/{tid}-*.json"))
        if not hits:
            raise FileNotFoundError(f"no sidecar for {tid} in {TRACKS_DIR}")
        self.json_path = hits[0]
        self.meta = json.loads(self.json_path.read_text(encoding="utf-8"))
        self.mp3 = self.json_path.with_suffix(".mp3")
        if not self.mp3.exists():
            raise FileNotFoundError(f"missing audio {self.mp3}")
        self.id = tid
        self.bpm = float(self.meta["bpm"])
        self.downbeat = float(self.meta.get("first_downbeat_sec", 0.0))
        self.cues = {c["slot"]: c for c in self.meta.get("cues", [])}

    @staticmethod
    def exists(tid: str) -> bool:
        return any(p.with_suffix(".mp3").exists() for p in TRACKS_DIR.glob(f"*/{tid}-*.json"))

    def cue(self, slot: str) -> int:
        return int(self.cues[slot]["bar"])

    def bar_sec(self, bar: float) -> float:
        return self.downbeat + bar * 240.0 / self.bpm

    @property
    def audio(self) -> np.ndarray:
        if self.id not in _AUDIO:
            from .export import decode

            _AUDIO[self.id] = decode(self.mp3, SR)
        return _AUDIO[self.id]

    @property
    def file(self) -> str:
        return self.meta.get("file") or self.mp3.relative_to(REPO_ROOT).as_posix()

    @property
    def title(self) -> str:
        return self.meta["title"]

    @property
    def title_he(self) -> str:
        return self.meta.get("title_he", self.title)

    @property
    def camelot(self) -> str:
        return self.meta.get("camelot", "")

    def label(self) -> str:
        """Hebrew-friendly reference: `house-01` „שקיעה ביפו“, 8A, 122 BPM."""
        return f"`{self.id}` „{self.title_he}“, {self.camelot}, {self.bpm:g} BPM"

    def short(self) -> str:
        return f"„{self.title_he}“ (`{self.id}`, {self.camelot})"


class Clock:
    """Demo grid: piecewise-constant tempo. ``pos`` = 0-based bar position (bars + beat/4)."""

    def __init__(self, bpm: float):
        self.segs: list[tuple[float, float, float]] = [(0.0, 0.0, float(bpm))]

    def change(self, pos: float, bpm: float) -> None:
        self.segs.append((pos, self.t_pos(pos), float(bpm)))

    def _seg(self, pos: float):
        s = self.segs[0]
        for g in self.segs:
            if g[0] <= pos + 1e-9:
                s = g
        return s

    def t_pos(self, pos: float) -> float:
        p0, t0, bpm = self._seg(pos)
        return t0 + (pos - p0) * 240.0 / bpm

    def bpm_at(self, pos: float) -> float:
        return self._seg(pos)[2]

    def pos_of(self, t: float) -> float:
        s = self.segs[0]
        for g in self.segs:
            if g[1] <= t + 1e-9:
                s = g
        p0, t0, bpm = s
        return p0 + (t - t0) * bpm / 240.0


class Lane:
    """Automation lane: piecewise-linear (time sec, value). Moves must be written in time order."""

    def __init__(self, v0: float):
        self.pts: list[list[float]] = [[0.0, float(v0)]]

    @property
    def value(self) -> float:
        return self.pts[-1][1]

    def set(self, v: float) -> "Lane":
        """Initial value (before any move)."""
        assert len(self.pts) == 1, "set() only before moves"
        self.pts[0][1] = float(v)
        return self

    def _add(self, t: float, v: float) -> None:
        last = self.pts[-1][0]
        if t <= last:
            t = last + 1e-6
        self.pts.append([t, float(v)])

    def ramp(self, t0: float, t1: float, v: float) -> "Lane":
        if t0 > self.pts[-1][0]:
            self._add(t0, self.value)
        self._add(t1, v)
        return self

    def jump(self, t: float, v: float, ms: float = 4.0) -> "Lane":
        return self.ramp(t - ms * 1e-3, t, v)

    def array(self, t: np.ndarray) -> np.ndarray:
        p = np.asarray(self.pts, dtype=np.float64)
        return np.interp(t, p[:, 0], p[:, 1])

    def active(self) -> bool:
        return any(abs(v) > 1e-9 for _, v in self.pts)


class Deck:
    def __init__(self, mix: "Mix", name: str, track: Track, src_bar: float, start: float,
                 match: str = "auto", stop: float | None = None, trim_db: float = DECK_TRIM_DB):
        self.mix, self.name, self.track = mix, name, track
        self.src_bar, self.t_start, self.t_stop, self.trim_db = float(src_bar), float(start), stop, trim_db
        master = mix.clock.bpm_at(mix.clock.pos_of(start))
        if match == "auto":
            dev = abs(master / track.bpm - 1.0)
            match = "none" if dev < 1e-9 else ("resample" if dev <= RESAMPLE_MAX else "stretch")
        self.match = match
        self.bpm_play = track.bpm if match == "none" else master
        self.fader = Lane(1.0)
        self.low, self.mid, self.high = Lane(0.0), Lane(0.0), Lane(0.0)
        self.filt = Lane(0.0)      # −1 = LPF closed … 0 = off … +1 = HPF closed
        self.send = Lane(0.0)      # echo send (post-fader)
        self.echo_cfg: dict | None = None
        self.rolls: list[tuple[float, float, float]] = []

    def echo(self, t_on: float, beats: float, feedback: float = 0.55, level: float = 0.6,
             lp_hz: float = 7000.0, hp_hz: float = 300.0, t_off: float | None = None) -> None:
        self.echo_cfg = dict(beats=beats, feedback=feedback, level=level, lp=lp_hz, hp=hp_hz,
                             bpm=self.bpm_play)
        self.send.jump(t_on, 1.0, ms=2.0)
        if t_off is not None:
            self.send.jump(t_off, 0.0, ms=2.0)

    def roll(self, t_on: float, t_off: float, beats: float) -> None:
        self.rolls.append((t_on, t_off, beats))

    def tempo_note(self) -> str:
        tb = self.track.bpm
        if self.name == "A":
            return f"master tempo {tb:g} BPM"
        if self.match == "none":
            return f"native {tb:g} BPM (no beatmatch)" if abs(self.bpm_play - tb) < 1e-9 else ""
        how = "resample (vinyl)" if self.match == "resample" else "time-stretch (key lock)"
        return f"{how} {tb:g} → {self.bpm_play:g} BPM ({pct(self.bpm_play, tb)})"


# ============================================================================ DSP
_SOS_LO = signal.butter(4, EQ_LOW_HZ, "low", fs=SR, output="sos")
_SOS_HI = signal.butter(4, EQ_HIGH_HZ, "low", fs=SR, output="sos")


def dj_eq(x: np.ndarray, low_db: np.ndarray, mid_db: np.ndarray, high_db: np.ndarray) -> np.ndarray:
    """3-band isolator with a zero-phase complementary split (low = forward-backward 4th-order
    Butterworth LP, mid/high = the remainder split the same way). The bands sum back to the input
    exactly, so a centred EQ is transparent — no all-pass phase rotation, which would raise the peaks
    of our brick-wall-mastered tracks by several dB."""
    x64 = np.asarray(x, dtype=np.float64)
    lo = signal.sosfiltfilt(_SOS_LO, x64, axis=0)
    rest = x64 - lo
    mid = signal.sosfiltfilt(_SOS_HI, rest, axis=0)
    hi = rest - mid
    g = lambda d: np.power(10.0, np.clip(d, KILL_DB, 6.0) / 20.0)[:, None]
    return (lo * g(low_db) + mid * g(mid_db) + hi * g(high_db)).astype(F32)


def color_filter(x: np.ndarray, v: np.ndarray, sr: int = SR) -> np.ndarray:
    """One-knob filter: v > 0 → HPF 20 Hz…8 kHz, v < 0 → LPF 20 kHz…150 Hz (24 dB/oct, slight
    resonance). Bypassed (dry) where the knob is centred, with 20 ms crossfades."""
    from .dsp import svf24

    act = np.abs(v) > 1e-4
    if not act.any():
        return x
    pad = int(0.05 * sr)
    idx = np.nonzero(act)[0]
    a, b = max(0, idx[0] - pad), min(len(v), idx[-1] + pad)
    seg, vv = x[a:b], v[a:b]
    y = seg
    if (vv > 1e-4).any():
        y = svf24(y, 20.0 * (8000.0 / 20.0) ** np.clip(vv, 0.0, 1.0), q=1.1, mode="hp", sr=sr)
    if (vv < -1e-4).any():
        y = svf24(y, 20000.0 * (150.0 / 20000.0) ** np.clip(-vv, 0.0, 1.0), q=1.1, mode="lp", sr=sr)
    w = maximum_filter1d(act[a:b].astype(np.float64), size=int(0.02 * sr) | 1)
    w = uniform_filter1d(w, size=int(0.02 * sr) | 1)[:, None]
    out = x.copy()
    out[a:b] = (seg * (1.0 - w) + y * w).astype(F32)
    return out


def tempo_process(x: np.ndarray, bpm_src: float, bpm_dst: float, mode: str) -> np.ndarray:
    """Bring a chunk (sample 0 = a downbeat) to ``bpm_dst`` keeping sample 0 aligned."""
    if mode == "none" or abs(bpm_src - bpm_dst) < 1e-9:
        return x
    if mode == "resample":
        fr = Fraction(bpm_src).limit_denominator(2000) / Fraction(bpm_dst).limit_denominator(2000)
        return signal.resample_poly(x, fr.numerator, fr.denominator, axis=0).astype(F32)
    return time_stretch(x, bpm_dst / bpm_src)


def time_stretch(x: np.ndarray, rate: float, sr: int = SR) -> np.ndarray:
    """Tempo change without pitch change (rate > 1 = faster). Rubberband (ffmpeg) when available,
    librosa phase vocoder as fallback. Latency is measured and removed so sample 0 stays on beat 1."""
    import soundfile as sf

    n_out = int(round(x.shape[0] / rate))
    with tempfile.TemporaryDirectory(dir=scratch_dir()) as td:
        src, dst = Path(td) / "in.wav", Path(td) / "out.wav"
        sf.write(src, x, sr, subtype="FLOAT")
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af",
               f"rubberband=tempo={rate:.8f}:transients=crisp:detector=percussive:phase=independent:"
               f"channels=together", "-c:a", "pcm_f32le", str(dst)]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            y, _ = sf.read(dst, dtype="float32", always_2d=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            import librosa

            y = np.stack([librosa.effects.time_stretch(x[:, c], rate=rate) for c in range(2)], axis=1)
    # remove the processing latency: cross-correlate onset envelopes (input warped to output time)
    lag = _onset_lag(x, y, rate)
    if lag > 0:
        y = y[lag:]
    elif lag < 0:
        y = np.concatenate([np.zeros((-lag, 2), F32), y])
    y = y[:n_out]
    if y.shape[0] < n_out:
        y = np.concatenate([y, np.zeros((n_out - y.shape[0], 2), F32)])
    return y.astype(F32)


def _onset_lag(x: np.ndarray, y: np.ndarray, rate: float, hop: int = 8, secs: float = 20.0) -> int:
    """Samples by which ``y`` (stretched) lags the ideal time-scaled ``x`` (positive = late)."""
    def env(z):
        m = np.abs(z[: int(secs * SR)]).mean(axis=1)
        n = m.shape[0] // hop
        e = m[: n * hop].reshape(n, hop).max(axis=1)
        return np.maximum(np.diff(e, prepend=0.0), 0.0)

    ex, ey = env(x), env(y)
    exw = np.interp(np.arange(ey.shape[0]) * rate, np.arange(ex.shape[0]), ex)
    c = signal.correlate(ey - ey.mean(), exw - exw.mean(), "full", method="fft")
    mid = exw.shape[0] - 1
    w = int(0.05 * SR / hop)  # search ±50 ms only
    k = int(np.argmax(c[mid - w: mid + w + 1])) - w
    return k * hop


def _declick(P: np.ndarray, idx: np.ndarray, y: np.ndarray, F: int = DECLICK) -> np.ndarray:
    jumps = np.nonzero(np.diff(idx) != 1)[0] + 1
    w = (0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, F)))[:, None].astype(F32)
    for j in jumps:
        e = min(F, y.shape[0] - j)
        old = P[np.clip(idx[j - 1] + 1 + np.arange(e), 0, P.shape[0] - 1)]
        y[j:j + e] = old * (1.0 - w[:e]) + y[j:j + e] * w[:e]
    return y


def render_deck(d: Deck, n: int, sr: int = SR) -> np.ndarray:
    out = np.zeros((n, 2), F32)
    i0 = int(round(d.t_start * sr))
    i1 = n if d.t_stop is None else min(n, int(round(d.t_stop * sr)))
    if i1 <= i0:
        return out
    L = i1 - i0
    src = d.track.audio
    s0 = int(round(d.track.bar_sec(d.src_bar) * sr))
    rate = d.bpm_play / d.track.bpm
    need = int(math.ceil(L * rate)) + sr
    chunk = src[s0: s0 + need]
    if chunk.shape[0] < need:
        chunk = np.concatenate([chunk, np.zeros((need - chunk.shape[0], 2), F32)])
    P = tempo_process(chunk, d.track.bpm, d.bpm_play, d.match)
    idx = np.arange(L)
    for t_on, t_off, beats in d.rolls:  # slip roll: playback position keeps running underneath
        r0, r1 = int(round(t_on * sr)) - i0, int(round(t_off * sr)) - i0
        ls = max(16, int(round(beats * 60.0 / d.bpm_play * sr)))
        idx[r0:r1] = r0 + (np.arange(r1 - r0) % ls)
    idx = np.clip(idx, 0, P.shape[0] - 1)
    y = P[idx].astype(F32)
    if d.rolls:
        y = _declick(P, idx, y)
    fi, fo = int(0.002 * sr), int(0.004 * sr)
    y[:fi] *= np.linspace(0.0, 1.0, fi, dtype=F32)[:, None]
    if d.t_stop is not None:
        y[-fo:] *= np.linspace(1.0, 0.0, fo, dtype=F32)[:, None]
    t = (i0 + np.arange(L)) / sr
    if d.low.active() or d.mid.active() or d.high.active():
        y = dj_eq(y, d.low.array(t), d.mid.array(t), d.high.array(t))
    if d.filt.active():
        y = color_filter(y, d.filt.array(t), sr)
    p = np.clip(d.fader.array(t), 0.0, 1.0)
    y = y * (p * p * 10 ** (d.trim_db / 20.0)).astype(F32)[:, None]
    out[i0:i1] = y
    if d.echo_cfg:
        from .dsp import delay

        c = d.echo_cfg
        send = np.zeros((n - i0, 2), F32)
        send[:L] = y * d.send.array(t).astype(F32)[:, None]
        wet = delay(send, c["beats"] * 60.0 / c["bpm"], feedback=c["feedback"], lp_hz=c["lp"],
                    hp_hz=c["hp"], pingpong=False, sr=sr)
        out[i0:] += wet * c["level"]
    return out


def master_bus(x: np.ndarray, sr: int = SR, target: float = TARGET_LUFS, verbose: bool = False):
    """Glue compressor → gain → 2×-oversampled soft clip (only the coincident kick transients of an
    overlap reach it) → look-ahead true-peak limiter, iterated to the target LUFS."""
    from .dsp import compressor
    from .master import clip2x, limiter, lufs

    x = compressor(x, threshold_db=-5.0, ratio=2.0, attack_ms=15.0, release_ms=220.0, knee_db=6.0, sr=sr)
    g = 10 ** ((target - lufs(x, sr)) / 20.0)
    y, gr, L = x, 0.0, -70.0
    for _ in range(10):
        y, gr = limiter(clip2x((x * g).astype(F32), 0.85), ceiling_db=-1.6, lookahead_ms=5.0,
                        release_ms=120.0, sr=sr)
        L = lufs(y, sr)
        if verbose:
            print(f"    master: {L:.2f} LUFS, limiter max GR {gr:.2f} dB")
        err = target - L
        if abs(err) <= 0.08:
            break
        g *= 10 ** (err * (1.6 if err > 0 else 1.0) / 20.0)  # clip/limiter eat part of any boost
    return y.astype(F32), L, gr


# ============================================================================ mix context
class Mix:
    def __init__(self, entry: dict, a: Track, b: Track, lead: int, bars: int, bpm: float | None = None):
        self.entry, self.a, self.b, self.lead, self.bars = entry, a, b, lead, bars
        self.clock = Clock(bpm or a.bpm)
        self.decks: list[Deck] = []
        self.events: list[dict] = []
        self.description_he = ""
        self.exercise_he: list[str] = []
        self.notes: dict = {}

    # time helpers (1-based bars/beats, like a DJ counts)
    def t(self, bar: float, beat: float = 1.0) -> float:
        """Demo time of bar ``bar`` (1-based), beat ``beat`` (1-based, fractional allowed)."""
        return self.clock.t_pos(bar - 1 + (beat - 1) / 4.0)

    def m(self, mbar: float, beat: float = 1.0) -> float:
        """Transition bar (1-based, = first bar where B is heard, as in the guide tables)."""
        return self.t(self.lead + mbar, beat)

    def deck(self, name: str, track: Track, src_bar: float, start: float, **kw) -> Deck:
        d = Deck(self, name, track, src_bar, start, **kw)
        self.decks.append(d)
        return d

    def ev(self, t: float, cue: str | None, action: str, he: str | None = None) -> None:
        pos = self.clock.pos_of(t)
        bar = int(math.floor(pos + 1e-6))
        beat = int(round((pos - bar) * 4)) + 1
        if beat > 4:
            bar, beat = bar + 1, 1
        fmt = dict(bar=bar + 1, mbar=bar + 1 - self.lead, beat=beat)
        self.events.append({"t": round(t, 3), "bar": bar, "beat": beat, "action": action,
                            "cue": cue, "he": he.format(**fmt) if he else None})

    @property
    def duration(self) -> float:
        return self.clock.t_pos(self.bars)


def b_entry_note(d: Deck) -> str:
    """Hebrew: where deck B starts inside its track (1-based bar + time in the original track)."""
    bar = int(d.src_bar)
    slots = {v["bar"]: k for k, v in d.track.cues.items()}
    sec = mmss1(d.track.bar_sec(bar))
    if bar in slots:
        return f"Hot Cue {slots[bar]} (תיבה {bar + 1}, {sec})"
    nxt = min((b for b in slots if b > bar), default=None)
    if nxt is not None:
        return f"תיבה {bar + 1} ({sec}) — {nxt - bar} תיבות לפני Hot Cue {slots[nxt]}"
    return f"תיבה {bar + 1} ({sec})"


def common_exercise(mx: Mix, a: Deck, b: Deck, b_prep: str) -> list[str]:
    A, B = mx.a, mx.b
    sync = ("בלי Sync — B נשאר בקצב המקורי שלו" if b.match == "none"
            else f"הפעילו Sync על B (או כוונו את ה-Tempo ל-{b.bpm_play:g} BPM, {pct(b.bpm_play, B.bpm)})")
    return [
        f"טענו לדק 1 את `{A.file}` ולדק 2 את `{B.file}`.",
        f"הכינו את B: {sync}. נקודת הכניסה של B: {b_entry_note(b)}. {b_prep}",
        f"נגנו את A מתיבה {int(a.src_bar) + 1} שלו ({mmss1(A.bar_sec(a.src_bar))}) — שם מתחיל הדמו — וספרו תיבות.",
    ]


# ============================================================================ recipes
def demo_blend(mx: Mix) -> None:
    A, B = mx.a, mx.b
    a = mx.deck("A", A, A.cue("G") - 8, mx.t(1), stop=mx.m(33) + 0.05)
    b = mx.deck("B", B, B.cue("B") - 16, mx.m(1))
    b.low.set(KILL_DB), b.high.set(-6.0), b.fader.set(0.0)
    m = mx.m
    mx.ev(mx.t(1), "A solo", "Deck A plays alone, 8 bars before its Outro (Hot Cue G)",
          f"A ({A.label()}) מנגן לבד את 8 התיבות האחרונות לפני ה-Outro. B ({B.label()}) מוכן באוזניות: "
          f"מותאם ל-{A.bpm:g} BPM, Low למטה לגמרי, High בשעה 10, פיידר למטה.")
    b.fader.ramp(m(1), m(9), 0.75)
    mx.ev(m(1), "B in", "Mix bar 1: A hits Hot Cue G, B starts on the 1 (Low killed, High −6 dB); B fader up to ~75% over 8 bars",
          "תיבה 1 של המעבר (תיבה {bar} בקובץ): A מגיע ל-Hot Cue G (Outro) ו-B מתחיל על ה-1. "
          "הפיידר של B עולה לאט עד כ-75% לאורך 8 תיבות.")
    a.high.ramp(m(9), m(13), -6.0)
    b.fader.ramp(m(9), m(13), 1.0)
    b.high.ramp(m(9), m(13), 0.0)
    mx.ev(m(9), "Highs", "Bars 9-12: A High down to 10 o'clock (−6 dB); B fader to 100%, B High back to centre",
          "תיבות 9–12 של המעבר: ה-High של A יורד לשעה 10, הפיידר של B עולה ל-100% וה-High שלו חוזר לאמצע.")
    a.low.ramp(m(17), m(21), KILL_DB)
    b.low.ramp(m(17), m(21), 0.0)
    mx.ev(m(17), "Bass blend", "Bars 17-20: gradual low swap — A Low down to kill, B Low up to centre (B's bass enters at its Hot Cue B)",
          "תיבות 17–20 של המעבר (מ-{bar} בקובץ): החלפת באסים הדרגתית — ה-Low של A יורד עד הסוף וה-Low של B עולה לאמצע, "
          "בדיוק כשהבאס של B נכנס (Hot Cue B שלו). באמצע הדרך שניהם בערך בשעה 9–10 — אף פעם לא שני Lows מלאים.")
    a.mid.ramp(m(21), m(29), -6.0)
    a.fader.ramp(m(21), m(29), 0.6)
    mx.ev(m(21), "A fades", "Bars 21-28: A Mid slightly down, A fader slowly down",
          "תיבות 21–28 של המעבר: ה-Mid של A יורד מעט והפיידר שלו יורד לאט.")
    a.fader.ramp(m(29), m(33), 0.0)
    mx.ev(m(29), "A out", "Bars 29-32: A fader reaches 0",
          "תיבות 29–32 של המעבר: הפיידר של A מגיע ל-0. ב-B לא נוגעים.")
    mx.ev(m(33), "B solo", "B alone; A EQ reset to centre (fader already down)",
          "תיבה {bar} בקובץ: B לבד. ה-EQ של A חוזר לאמצע (הפיידר שלו כבר למטה) — השיר החדש בבית.")
    mx.description_he = (
        f"בלנד ארוך של 32 תיבות מ-{A.short()} אל {B.short()}, בדיוק לפי הטבלה בפרק 6. B מותאם ל-{A.bpm:g} BPM "
        f"ונכנס על ה-Outro של A; הפיידר שלו עולה לאט, ה-Highs מתחלפים, והבאסים מתחלפים בהדרגה בתיבות 17–20 של "
        f"המעבר — הרחבה כמעט לא מרגישה שהשיר התחלף. ‎{A.camelot}→{B.camelot} — שכנים בגלגל.")
    mx.exercise_he = common_exercise(mx, a, b, "Low למטה לגמרי, High בשעה 10, פיידר למטה.") + [
        "על ה-1 של Hot Cue G של A — הפעילו את B ובצעו את השלבים לפי הזמנים בדמו (פיידר עד 75% בשמונה תיבות, "
        "Highs בתיבות 9–12, Lows בתיבות 17–20, A יוצא עד תיבה 32).",
        "הקליטו והשוו לדמו: האם הבאסים התחלפו בלי רגע של שני באסים מלאים? האם B עלה לאט מספיק?",
    ]


def demo_bass_swap(mx: Mix) -> None:
    A, B = mx.a, mx.b
    a = mx.deck("A", A, A.cue("G") - 8, mx.t(1), stop=mx.m(33) + 0.05)
    b = mx.deck("B", B, B.cue("B") - 16, mx.m(1))
    b.low.set(KILL_DB), b.fader.set(0.0)
    m = mx.m
    mx.ev(mx.t(1), "A solo", "Deck A plays alone, 8 bars before Hot Cue G",
          f"A ({A.label()}) מנגן לבד, 8 תיבות לפני ה-Outro. B ({B.label()}) מוכן: מותאם ל-{A.bpm:g} BPM, "
          "Low למטה לגמרי, פיידר למטה.")
    b.fader.ramp(m(1), m(9), 1.0)
    mx.ev(m(1), "B in", "Mix bar 1: B starts on the 1 with Low killed; fader up to 100% over 8 bars (drums and highs only)",
          "תיבה 1 של המעבר (תיבה {bar} בקובץ): A מגיע ל-Hot Cue G ו-B מתחיל על ה-1. הפיידר של B עולה עד 100% "
          "לאורך 8 תיבות — שומעים רק את התופים והגבוהים שלו, בלי באס.")
    a.high.ramp(m(9), m(11), -5.0)
    mx.ev(m(9), "A hi down", "Bars 9-16: A High slightly down (10-11 o'clock); B full without Low",
          "תיבות 9–16 של המעבר: ה-High של A יורד מעט (שעה 10–11). B מלא, עדיין בלי Low.")
    a.low.jump(m(17), KILL_DB)
    b.low.jump(m(17), 0.0)
    mx.ev(m(17), "Bass swap", "Mix bar 17 on the 1: BASS SWAP — A Low killed, B Low to centre at the same moment",
          "תיבה 17 של המעבר (תיבה {bar} בקובץ), בדיוק על ה-1: Bass Swap — ה-Low של A למטה בבת אחת וה-Low של B לאמצע "
          "בבת אחת. הבאס של B נכנס כאן (Hot Cue B שלו) — באס אחד בכל רגע.")
    a.mid.ramp(m(17), m(25), -10.0)
    a.high.ramp(m(17), m(25), -15.0)
    mx.ev(m(17) + 0.5 * 240 / A.bpm, "A thins", "Bars 17-24: A Mid and High gradually down",
          "תיבות 17–24 של המעבר: ה-Mid וה-High של A יורדים בהדרגה — A הופך לרקע.")
    a.fader.ramp(m(25), m(33), 0.0)
    mx.ev(m(25), "A fader", "Bars 25-32: A fader down to 0",
          "תיבות 25–32 של המעבר: הפיידר של A יורד עד 0.")
    mx.ev(m(33), "B solo", "B alone; A EQ reset",
          "תיבה {bar} בקובץ: B לבד. ה-EQ והפיידר של A מתאפסים — מוכנים לטראק הבא.")
    mx.description_he = (
        f"החלפת באס (Bass Swap) קלאסית ב-32 תיבות מ-{A.short()} אל {B.short()}, לפי פרק 6. B מותאם ל-{A.bpm:g} BPM, "
        "עולה בלי באס, ובתיבה 17 של המעבר — בדיוק על ה-1 — ה-Lows מתחלפים בבת אחת: הבאס של A יוצא והבאס של B נכנס. "
        f"‎{A.camelot}→{B.camelot} — שכנים בגלגל (‎−1).")
    mx.exercise_he = common_exercise(mx, a, b, "Low למטה לגמרי, פיידר למטה.") + [
        "על ה-1 של Hot Cue G של A — הפעילו את B והעלו את הפיידר שלו עד 100% במשך 8 תיבות.",
        "ספרו 16 תיבות. על ה-1 של תיבה 17 של המעבר — יד אחת על ה-Low של A, יד שנייה על ה-Low של B, ושתיהן זזות יחד.",
        "תיבות 17–32: הורידו בהדרגה Mid ו-High של A ואז את הפיידר שלו. הקליטו והשוו לדמו — האם ההחלפה נפלה בדיוק על ה-1?",
    ]


def demo_filter(mx: Mix) -> None:
    A, B = mx.a, mx.b
    a = mx.deck("A", A, A.cue("G") - 8, mx.t(1), stop=mx.m(17) + 0.05)
    b = mx.deck("B", B, B.cue("B"), mx.m(1))
    b.low.set(KILL_DB), b.fader.set(0.0)
    m = mx.m
    mx.ev(mx.t(1), "A solo", "Deck A plays the last 8 bars of its drop",
          f"A ({A.label()}) מנגן את 8 התיבות האחרונות של הדרופ. B ({B.label()}) מוכן על Hot Cue B, Low למטה, פיידר למטה.")
    b.fader.ramp(m(1), m(5), 0.8)
    a.filt.ramp(m(1), m(13), 0.6)
    mx.ev(m(1), "B in + HPF", "Mix bar 1: B starts on the 1 (fader to 80% over 4 bars); A HPF starts rising slowly (12 → 3 o'clock over 12 bars)",
          "תיבה 1 של המעבר (תיבה {bar} בקובץ): A מגיע ל-Outro ו-B מתחיל על ה-1 מ-Hot Cue B; הפיידר שלו עולה ל-80% "
          "ב-4 תיבות. במקביל מתחילים לסובב לאט את הפילטר של A לכיוון HPF.")
    mx.ev(m(7), "HPF halfway", "Bars 7-12: A HPF passes 1-2 o'clock — A's kick and bass get thin",
          "תיבות 7–12 של המעבר: הפילטר של A עובר את שעה 1–2 — הקיק והבאס של A נהיים דקים, ו-B תופס את המקום.")
    b.low.jump(m(13), 0.0)
    a.fader.ramp(m(13), m(17), 0.0)
    a.filt.ramp(m(13), m(17), 0.78)
    b.fader.ramp(m(13), m(17), 1.0)
    mx.ev(m(13), "B low in", "Mix bar 13 on the 1: B Low back to centre; A fader down to 0 over 4 bars (filter stays open)",
          "תיבה 13 של המעבר (תיבה {bar} בקובץ), על ה-1: ה-Low של B חוזר לאמצע — הבאס שלו נכנס. הפיידר של A יורד ל-0 "
          "במשך 4 תיבות, והפילטר שלו נשאר פתוח.")
    a.filt.jump(m(17) + 0.02, 0.0, ms=2.0)
    mx.ev(m(17), "B full", "Mix bar 17: B full; only now A's filter goes back to centre (fader already down)",
          "תיבה 17 של המעבר (תיבה {bar} בקובץ): B מלא. רק עכשיו, כשהפיידר של A כבר למטה, הפילטר שלו חוזר לאמצע.")
    mx.description_he = (
        f"מעבר פילטר של 16 תיבות מ-{A.short()} אל {B.short()}: פילטר HPF על A עולה לאט ו\"מעלים\" את הבאס והגוף שלו, "
        f"בזמן ש-B נכנס מ-Hot Cue B בלי Low. בתיבה 13 הבאס של B חוזר ו-A יוצא. הסולמות ‎{A.camelot} ו-{B.camelot} "
        "רחוקים בשני צעדים — הפילטר מסתיר את החפיפה.")
    mx.exercise_he = common_exercise(mx, a, b, "Low למטה, פיידר למטה.") + [
        "על ה-1 של Hot Cue G של A — הפעילו את B והעלו את הפיידר ל-80% ב-4 תיבות. במקביל סובבו את ה-Color FX של A "
        "(Filter) לאט לכיוון HPF — 12 תיבות משעה 12 לשעה 3.",
        "בתיבה 13: Low של B לאמצע על ה-1, ופיידר A למטה במשך 4 תיבות. רק אחרי שהפיידר למטה — פילטר A לאמצע.",
        "נסו גם את הווריאציה: B נכנס עם LPF כמעט סגור, ופותחים אותו לאט לאורך 16 תיבות.",
    ]


def demo_echo_out(mx: Mix) -> None:
    A, B = mx.a, mx.b
    t = mx.t
    exit_bar = 16
    mx.clock.change(exit_bar, B.bpm)  # bar 17 onward runs at B's native tempo
    a = mx.deck("A", A, A.cue("G") - exit_bar, t(1), stop=t(exit_bar, 3) + 0.01)
    b = mx.deck("B", B, B.cue("A"), t(exit_bar + 1), match="none")
    mx.notes["tempo_map"] = [{"bar": 0, "bpm": A.bpm}, {"bar": exit_bar, "bpm": B.bpm}]
    a_slot = next((k for k, v in A.cues.items() if v["bar"] == int(a.src_bar)), None)
    mx.ev(t(1), "A phrase", "Deck A plays the last phrase of its drop; B waits on Hot Cue A at its own tempo (no beatmatch)",
          f"A ({A.label()}) מנגן את הפרייז האחרון של הדרופ" + (f" (מ-Hot Cue {a_slot})" if a_slot else "") +
          f". B ({B.label()}) מחכה על Hot Cue A בקצב המקורי שלו — בלי ביטמאצ'ינג.")
    mx.ev(t(exit_bar - 3), "Get ready", "Bar 13: 4 bars left in the phrase — Echo 1/2 beat, level ~50%, assigned to A",
          "תיבה {bar}: נשארו 4 תיבות לסוף הפרייז — מכינים Echo של 1/2 פעמה, Level כ-50%, על הערוץ של A.")
    a.echo(t(exit_bar, 1), beats=0.5, feedback=0.6, level=0.7, hp_hz=280.0, t_off=t(exit_bar + 2))
    mx.ev(t(exit_bar, 1), "Echo on", "Last bar of A's phrase, beat 1: Echo ON (1/2 beat)",
          "תיבה {bar}, על ה-1 — התיבה האחרונה של הפרייז: מדליקים את ה-Echo על A.")
    a.fader.jump(t(exit_bar, 3), 0.0)
    mx.ev(t(exit_bar, 3), "A fader cut", "Beat 3: A fader down at once — the echo tail keeps ringing",
          "תיבה {bar}, פעמה 3: הפיידר של A יורד בבת אחת — זנב האקו ממשיך להדהד ולדעוך.")
    mx.ev(t(exit_bar + 1), "B on the 1", f"Next 1: B starts from Hot Cue A at its native {B.bpm:g} BPM, fader up",
          "תיבה {bar}, על ה-1: B מתחיל מ-Hot Cue A והפיידר שלו למעלה — " + f"ב-{B.bpm:g} BPM, בלי לסנכרן.")
    mx.ev(t(exit_bar + 3), "Echo off", "Tail gone: Echo off, A EQ/level reset",
          "תיבה {bar}: הזנב נגמר — מכבים את ה-Echo, מחזירים את ה-Level לאפס ואת ה-EQ של A לאמצע. B ממשיך לבד.")
    mx.description_he = (
        f"‏Echo Out מ-{A.short()} אל {B.short()}: אקו של 1/2 פעמה נדלק על התיבה האחרונה של הפרייז, הפיידר של A יורד "
        f"בפעמה 3, והזנב מגשר עד ש-B נכנס על ה-1 — בקצב המקורי שלו ({B.bpm:g}), בלי ביטמאצ'ינג. "
        "מעבר קצר ונקי שעובד גם בין ז'אנרים וקצבים.")
    mx.exercise_he = common_exercise(mx, a, b, "פיידר למטה, EQ באמצע.") + [
        "ב-Beat FX בחרו Echo, Beat 1/2, Level כ-50%, והקצו אותו לערוץ של A.",
        "על ה-1 של התיבה האחרונה של הפרייז — Echo ON; בפעמה 3 — פיידר A למטה בבת אחת; על ה-1 הבא — Play על B ופיידר למעלה.",
        "נסו גם Beat של 3/4 ושל 1 ובחרו את האהוב עליכם. אל תשכחו לכבות את האקו אחרי שהזנב נגמר.",
    ]


def demo_loop_roll(mx: Mix) -> None:
    A, B = mx.a, mx.b
    t = mx.t
    L = 16
    a = mx.deck("A", A, A.cue("G") - L, t(1), stop=t(L + 1) + 0.005)
    b = mx.deck("B", B, B.cue("D"), t(L + 1))
    mx.ev(t(1), "A drop", "Deck A plays the last 16 bars of its drop; B cued on Hot Cue D, synced",
          f"A ({A.label()}) מנגן את 16 התיבות האחרונות של הדרופ. B ({B.label()}) מוכן על Hot Cue D (הדרופ), "
          f"מסונכרן ל-{A.bpm:g} BPM.")
    a.filt.ramp(t(L - 3), t(L + 1) - 0.01, 0.45)
    mx.ev(t(L - 3), "HPF build", "Bars 13-16: HPF on A rises slowly — tension builds",
          "תיבות {bar}–16: פילטר HPF על A עולה לאט לאורך 4 תיבות — הבאס מתחיל להיעלם והמתח עולה.")
    a.roll(t(L, 1), t(L, 3), 1.0)
    mx.ev(t(L, 1), "Roll 1", "Bar 16 beat 1: Loop Roll 1 beat",
          "תיבה {bar}, על ה-1: Roll של פעמה אחת על A.")
    a.roll(t(L, 3), t(L, 4), 0.5)
    mx.ev(t(L, 3), "Roll 1/2", "Beat 3: Roll 1/2 beat",
          "תיבה {bar}, פעמה 3: מקצרים ל-1/2 פעמה.")
    a.roll(t(L, 4), t(L, 4.5), 0.25)
    a.roll(t(L, 4.5), t(L + 1), 0.125)
    mx.ev(t(L, 4), "Roll 1/4-1/8", "Beat 4: Roll 1/4, then 1/8 on the last half beat",
          "תיבה {bar}, פעמה 4: ‏1/4 פעמה, ובחצי הפעמה האחרונה 1/8 — ה\"טררררר\" מאיץ.")
    a.fader.jump(t(L + 1), 0.0)
    mx.ev(t(L + 1), "B drop", "Bar 17 exactly on the 1: roll off, A fader down, B lands on its drop (Hot Cue D)",
          "תיבה {bar}, בדיוק על ה-1: ה-Roll כבוי, הפיידר של A למטה, ו-B נוחת מ-Hot Cue D עם הדרופ המלא. "
          "רק אחר כך הפילטר של A חוזר לאמצע.")
    mx.ev(t(L + 9), "B groove", "B alone — its drop continues",
          "תיבה {bar}: B ממשיך לבד — הדרופ שלו בשיא, והאנרגיה ברחבה לא ירדה אפילו לרגע.")
    mx.description_he = (
        f"‏Loop Roll לפני דרופ: {A.short()} מסיים את הדרופ שלו עם HPF עולה ו-Roll שמתקצר — 1 → 1/2 → 1/4 → 1/8 פעמה — "
        f"ובדיוק על ה-1 הכל נכבה ו-{B.short()} נוחת על הדרופ שלו (Hot Cue D). בלי חפיפה, ולכן גם הסולמות "
        f"‎{A.camelot} ו-{B.camelot} לא מתנגשים.")
    mx.exercise_he = common_exercise(mx, a, b, "פיידר למטה, מחכה על Hot Cue D; Quantize דולק.") + [
        "בתיבה 13 של A התחילו לסובב את הפילטר לכיוון HPF.",
        "בתיבה 16: Roll של 1 פעמה על ה-1, ‏1/2 בפעמה 3, ‏1/4 בפעמה 4 ו-1/8 בחצי האחרון שלה.",
        "על ה-1 של תיבה 17: Roll כבוי, פיידר A למטה, Hot Cue D של B — באותה תנועה. אחר כך פילטר A לאמצע.",
        "תרגלו גם את הגרסה הארוכה: לופ של 4 תיבות על 16 התיבות האחרונות של A (Hot Cue H) כדי לקנות זמן.",
    ]


def demo_energy_boost(mx: Mix) -> None:
    A, B = mx.a, mx.b
    a = mx.deck("A", A, A.cue("G") - 8, mx.t(1), stop=mx.m(17) + 0.005)
    b = mx.deck("B", B, B.cue("B") - 16, mx.m(1))
    b.low.set(KILL_DB), b.fader.set(0.0)
    m = mx.m
    mx.ev(mx.t(1), "A solo", f"Deck A ({A.camelot}) plays the last 8 bars of its drop",
          f"A ({A.label()}) מנגן את 8 התיבות האחרונות של הדרופ. B ({B.label()}) — שני צעדים עם כיוון השעון בגלגל — "
          "מוכן באוזניות עם Low למטה.")
    b.fader.ramp(m(1), m(9), 1.0)
    mx.ev(m(1), "B drums in", "Mix bar 1: B starts on the 1 — drums and percussion only, no bass/chords, so the keys don't clash",
          "תיבה 1 של המעבר (תיבה {bar} בקובץ): A מגיע ל-Outro ו-B מתחיל על ה-1 — רק תופים וכלי הקשה, בלי באס ובלי "
          "אקורדים, כך ששני הסולמות לא מתנגשים. הפיידר של B עולה עד 100% ב-8 תיבות.")
    a.mid.ramp(m(9), m(17), -12.0)
    a.high.ramp(m(9), m(17), -6.0)
    mx.ev(m(9), "A recedes", f"Bars 9-16: A Mid/High gradually down — the {A.camelot} harmony recedes",
          f"תיבות 9–16 של המעבר: ה-Mid וה-High של A יורדים בהדרגה — ההרמוניה של {A.camelot} נסוגה והתופים של B "
          "תופסים את הבמה.")
    b.low.jump(m(17), 0.0)
    a.fader.jump(m(17), 0.0)
    mx.ev(m(17), "+2 lift", f"Mix bar 17, phrase start, on the 1: A fader cut, B Low in — B's bass and harmony arrive in {B.camelot}",
          "תיבה 17 של המעבר (תיבה {bar} בקובץ) — תחילת פרייז, על ה-1: הפיידר של A למטה בבת אחת וה-Low של B חוזר. "
          f"הבאס וההרמוניה של B נכנסים ב-{B.camelot}: זו ה\"הרמה\" של ‎+2 — טון שלם למעלה.")
    mx.ev(m(25), "B solo", "B alone in the new key",
          "תיבה {bar}: B לבד — שימו לב כמה הגרוב נשמע בהיר ו\"גבוה\" יותר, באותו קצב בדיוק.")
    mx.description_he = (
        f"קפיצת אנרגיה הרמונית ‎+2 בגלגל Camelot: מ-{A.short()} אל {B.short()} — טון שלם למעלה. "
        "כדי שהסולמות לא יתנגשו, B נכנס רק עם התופים שלו, A נסוג, והבאס וההרמוניה של B נוחתים על תחילת פרייז "
        "(תיבה 17 של המעבר) — לא באמצע בלנד ארוך עם שני באסים.")
    mx.exercise_he = common_exercise(mx, a, b, "Low למטה, פיידר למטה.") + [
        "על ה-1 של Hot Cue G של A — הפעילו את B והעלו את הפיידר שלו עד הסוף במשך 8 תיבות.",
        "בתיבות 9–16 הורידו בהדרגה Mid ו-High של A.",
        "על ה-1 של תיבה 17 של המעבר: פיידר A למטה ו-Low של B לאמצע באותו רגע. הקשיבו ל\"הרמה\" — ונסו לעשות את אותו "
        "מעבר בבלנד ארוך כדי לשמוע למה זה פחות עובד ב-‎+2.",
    ]


def demo_breakdown_mix(mx: Mix) -> None:
    A, B = mx.a, mx.b
    a = mx.deck("A", A, A.cue("C"), mx.t(1), stop=mx.m(17) + 0.005)
    b = mx.deck("B", B, B.cue("D") - 16, mx.m(1))
    b.low.set(KILL_DB), b.filt.set(-0.8), b.fader.set(0.0)
    m = mx.m
    mx.ev(mx.t(1), "A breakdown", "Deck A enters its breakdown (Hot Cue C): kick and bass drop out",
          f"A ({A.label()}) נכנס לברייקדאון (Hot Cue C): הקיק והבאס נעלמים, נשארים פדים וארפג'יו. ספרו 16 תיבות.")
    b.fader.ramp(m(1), m(5), 1.0)
    b.filt.ramp(m(1), m(15), -0.25)
    mx.ev(m(1), "B in (LPF)", "Bar 17 (middle of A's breakdown): B starts on the 1, 16 bars before its drop, LPF almost closed, Low killed; fader up over 4 bars",
          "תיבה {bar} — אמצע הברייקדאון של A: B מתחיל על ה-1, 16 תיבות לפני הדרופ שלו (Hot Cue D), עם LPF כמעט סגור "
          "ו-Low למטה. הפיידר שלו עולה ל-100% ב-4 תיבות, והפילטר נפתח לאט — B \"מתקרב\".")
    a.mid.ramp(m(9), m(16), -10.0)
    a.high.ramp(m(9), m(16), -8.0)
    mx.ev(m(9), "A recedes", "Bars 25-32: A Mid/High gradually down while B's LPF keeps opening",
          "תיבות {bar}–" + str(mx.lead + 16) + ": ה-Mid וה-High של A יורדים בהדרגה, וה-LPF של B כמעט פתוח.")
    b.filt.ramp(m(15), m(17) - 0.01, 0.0)
    a.echo(m(16, 3), beats=2.0, feedback=0.5, level=0.6, hp_hz=350.0, t_off=m(18))
    mx.ev(m(16, 3), "Echo 2 beats", "Last bar of A's breakdown, beat 3: Echo 2 beats on A",
          "תיבה {bar}, פעמה 3: Echo של 2 פעמות על A — מברייקדאון לברייקדאון.")
    a.fader.jump(m(17), 0.0)
    b.low.jump(m(17), 0.0)
    mx.ev(m(17), "B drop", "On the 1: A fader down, B Low in — B's drop replaces the drop A was about to play",
          "תיבה {bar}, על ה-1: הפיידר של A למטה וה-Low של B חוזר — הדרופ של B מחליף את הדרופ ש-A היה אמור לתת. "
          "זנב האקו של A דועך מעליו.")
    mx.ev(m(25), "B solo", "B's drop alone; A echo off and EQ reset",
          "תיבה {bar}: B לבד בדרופ שלו. מכבים את האקו ומאפסים את ה-EQ של A.")
    mx.description_he = (
        f"כניסה בברייקדאון במלודיק טכנו: {B.short()} נכנס באמצע הברייקדאון של {A.short()}, עם LPF סגור ובלי Low, "
        "ונפתח לאט. בסוף הברייקדאון A יוצא עם Echo של 2 פעמות, ובדיוק במקום שבו הדרופ של A היה אמור להגיע — "
        "נוחת הדרופ של B. התחלת הדמו היא Hot Cue C של A.")
    mx.exercise_he = common_exercise(mx, a, b, "Low למטה, Color FX על LPF כמעט סגור, פיידר למטה.") + [
        "ספרו 16 תיבות מתחילת הברייקדאון של A, ועל ה-1 הפעילו את B; פיידר עד הסוף ב-4 תיבות.",
        "פתחו את ה-LPF של B לאט לאורך 16 תיבות, והורידו בהדרגה Mid ו-High של A מהתיבה ה-9.",
        "בתיבה האחרונה של הברייקדאון — Echo של 2 פעמות על A בפעמה 3; על ה-1: פיידר A למטה ו-Low של B לאמצע.",
    ]


def demo_cut(mx: Mix) -> None:
    A, B = mx.a, mx.b
    t = mx.t
    drop = mx.lead + 1                       # demo bar where A's drop would land
    a = mx.deck("A", A, A.cue("D") - mx.lead, t(1), stop=t(drop) + 0.005)
    b = mx.deck("B", B, B.cue("D"), t(drop))
    mx.ev(t(1), "A plays", "Deck A plays the end of its intro; B synced and paused on Hot Cue D (its drop)",
          f"A ({A.label()}) מנגן את סוף האינטרו שלו. B ({B.label()}) מסונכרן ועומד על Hot Cue D — הדרופ שלו. "
          "Crossfader בצד של A (או הפיידר של B למטה).")
    mx.ev(t(drop - 16), "A breakdown", "A's breakdown: 16 bars to its drop",
          "תיבה {bar}: הברייקדאון של A (Hot Cue C) — מכאן 16 תיבות עד הדרופ. סופרים.")
    mx.ev(t(drop - 8), "A build", "A's build-up: 8 bars to go, hand on B's Hot Cue D",
          "תיבה {bar}: הבילדאפ של A מתחיל — 8 תיבות. יד אחת על Hot Cue D של B, יד שנייה על ה-Crossfader.")
    mx.ev(t(drop - 1, 4), "Last beat", "Last beat of the build — the crowd expects A's drop",
          "תיבה {bar}, פעמה 4: הפעמה האחרונה של הבילדאפ — הרחבה מחכה לדרופ של A.")
    a.fader.jump(t(drop), 0.0)
    mx.ev(t(drop), "CUT", "On the 1: CUT — B's Hot Cue D and crossfader to B in one motion; B's drop instead of A's",
          "תיבה {bar}, על ה-1: קאט! Hot Cue D של B וה-Crossfader ל-B באותה תנועה — הרחבה מקבלת את הדרופ של B "
          "במקום הדרופ של A.")
    mx.ev(t(drop + 8), "B phrase 2", "B's drop continues — next phrase",
          "תיבה {bar}: B ממשיך — הפרייז השני של הדרופ שלו. A כבר עצור ומוכן לטראק הבא.")
    mx.description_he = (
        f"קאט / סלאם: {A.short()} בונה מתח בבילדאפ שלו, ובדיוק על ה-1 של הדרופ — במקום הדרופ שלו — נוחת הדרופ של "
        f"{B.short()}. ביט אחד, בלי חפיפה, ולכן גם הסולמות ‎{A.camelot} ו-{B.camelot} לא מתנגשים. המעבר הקלאסי של "
        "מיינסטרים, ביג רום ואירועים.")
    mx.exercise_he = common_exercise(mx, a, b, "עצרו אותו על Hot Cue D. עקומת Crossfader חדה, A בצד שמאל ו-B בצד ימין.") + [
        "ספרו את הבילדאפ של A (8 תיבות). על ה-1 של הדרופ — Hot Cue D של B וה-Crossfader ל-B באותה תנועה.",
        "נסו פעם עם Quantize ופעם בלי — ושימו לב להבדל בתזמון.",
        "וריאציה (\"סלאם לבילדאפ\"): קאט מ-A ישר לתחילת הבילדאפ של B (8 תיבות לפני Hot Cue D שלו).",
    ]


def demo_tempo_change_echo(mx: Mix) -> None:
    A, B = mx.a, mx.b
    t = mx.t
    exit_bar = mx.lead
    mx.clock.change(exit_bar, B.bpm)
    a = mx.deck("A", A, A.cue("D"), t(1), stop=t(exit_bar + 1) + 0.005)
    b = mx.deck("B", B, B.cue("D"), t(exit_bar + 1), match="none")
    mx.notes["tempo_map"] = [{"bar": 0, "bpm": A.bpm}, {"bar": exit_bar, "bpm": B.bpm}]
    jump = pct(B.bpm, A.bpm)
    mx.ev(t(1), "A chorus", f"Deck A ({A.bpm:g} BPM) plays its chorus (Hot Cue D); B waits on Hot Cue D at {B.bpm:g} BPM — no beatmatch ({jump})",
          f"A ({A.label()}) מנגן את הפזמון שלו (Hot Cue D). B ({B.label()}) מחכה על Hot Cue D — הדרופ שלו — "
          f"בקצב המקורי. הפער {jump}: אין טעם לנסות ביטמאצ'ינג.")
    mx.ev(t(exit_bar - 7), "Plan exit", "Second half of the chorus: pick the exit (end of the phrase), Echo 1/2 beat ready",
          "תיבה {bar}: החצי השני של הפזמון — בוחרים את רגע היציאה: סוף המשפט בתיבה " + f"{exit_bar}" +
          ". מכינים Echo של 1/2 פעמה, Level כ-50%.")
    a.echo(t(exit_bar, 4), beats=0.5, feedback=0.55, level=0.7, hp_hz=320.0, t_off=t(exit_bar + 2))
    a.low.jump(t(exit_bar, 4), KILL_DB, ms=8.0)
    mx.ev(t(exit_bar, 4), "Echo + Low cut", "Last beat of the phrase: Echo ON (1/2 beat) and A Low cut",
          "תיבה {bar}, פעמה 4 — הפעמה האחרונה של המשפט: Echo ON על A, ובאותו רגע חיתוך ה-Low שלו.")
    a.fader.jump(t(exit_bar + 1), 0.0)
    mx.ev(t(exit_bar + 1), "B drop", f"Next 1: A fader down (echo tail continues); B starts from Hot Cue D at {B.bpm:g} BPM",
          "תיבה {bar}, על ה-1: הפיידר של A למטה וההד ממשיך לבד; על אותו 1 B מתחיל מ-Hot Cue D — " +
          f"ב-{B.bpm:g} BPM, בלי שום ביטמאצ'ינג.")
    mx.ev(t(exit_bar + 3), "Echo off", "Echo off, level back to zero, A EQ reset",
          "תיבה {bar}: מכבים את ה-Echo, Level חזרה לאפס, ה-EQ של A לאמצע. הרחבה כבר בקצב החדש.")
    mx.ev(t(exit_bar + 9), "New tempo", f"B's drop continues at {B.bpm:g} BPM",
          "תיבה {bar}: הדרופ של B ממשיך — " + f"‎{A.bpm:g}→{B.bpm:g} BPM בלי \"בור\" ברחבה.")
    mx.description_he = (
        f"מעבר טמפו עם Echo Out מ-{A.short()} אל {B.short()} — קפיצה של {jump}, בלי ביטמאצ'ינג. A יוצא בסוף "
        "הפזמון: Echo של 1/2 פעמה וחיתוך Low בפעמה האחרונה, הפיידר יורד על ה-1, ועל אותו 1 נוחת הדרופ של B בקצב "
        f"שלו. ‎{A.camelot} ו-{B.camelot} שכנים בגלגל, כך שגם זנב ההד לא מתנגש עם B. הדמו מנוגן ב-{A.bpm:g} BPM עד "
        f"תיבה {exit_bar} וב-{B.bpm:g} BPM מתיבה {exit_bar + 1} (ראו tempo_map).")
    mx.exercise_he = common_exercise(mx, a, b, "עצרו אותו על Hot Cue D (הדרופ), פיידר למטה.") + [
        "בחרו את סוף הפזמון של A. בפעמה האחרונה של המשפט — Echo ON (1/2 פעמה, Level כ-50%) וחיתוך Low.",
        "על ה-1 הבא — פיידר A למטה ו-Play על B מ-Hot Cue D באותו רגע. אחרי שהזנב נגמר — Echo OFF.",
        "נסו Echo של 1/2 ושל פעמה אחת — איזה מגשר טוב יותר בלי \"ללכלך\" את ההתחלה של B?",
    ]


def demo_drop_swap(mx: Mix) -> None:
    A, B = mx.a, mx.b
    t = mx.t
    swap = mx.lead + 9                       # demo bar where B's drop lands
    a = mx.deck("A", A, A.cue("D"), t(1), stop=t(swap) + 0.005)
    b = mx.deck("B", B, B.cue("D") - 8, t(swap - 8))
    b.low.set(KILL_DB), b.fader.set(0.0)
    match = ("Master Tempo / time-stretch" if b.match == "stretch" else "Sync")
    mx.ev(t(1), "A drop", "Deck A plays its drop/hook (Hot Cue D); B synced, waiting 8 bars before its Hot Cue D",
          f"A ({A.label()}) מנגן את הדרופ/הפזמון שלו (Hot Cue D). B ({B.label()}) מותאם ל-{A.bpm:g} BPM "
          f"({match}, {pct(A.bpm, B.bpm)}) ומחכה 8 תיבות לפני Hot Cue D שלו — תחילת הבילד.")
    b.fader.ramp(t(swap - 8), t(swap - 4), 1.0)
    mx.ev(t(swap - 8), "B build in", "B starts on the 1 with its build-up, Low killed; fader up over 4 bars",
          "תיבה {bar}, על ה-1: B מתחיל עם הבילד שלו (גלגולי דרבוקה) מעל החצי השני של הדרופ של A — Low למטה, "
          "הפיידר עולה ב-4 תיבות.")
    a.mid.ramp(t(swap - 4), t(swap), -9.0)
    a.high.ramp(t(swap - 4), t(swap), -9.0)
    mx.ev(t(swap - 4), "A recedes", "Bars 13-16: A Mid/High down gradually while B's build rises",
          "תיבות {bar}–" + f"{swap - 1}" + ": ה-Mid וה-High של A יורדים בהדרגה, והבילד של B עולה.")
    a.fader.jump(t(swap), 0.0)
    b.low.jump(t(swap), 0.0)
    mx.ev(t(swap), "DROP SWAP", "On the 1: A fader down, B Low in — B's drop replaces A's next section",
          "תיבה {bar}, על ה-1: החלפת דרופים — הפיידר של A למטה וה-Low של B לאמצע בבת אחת. במקום הברייקדאון של A "
          "מגיע הדרופ של B.")
    mx.ev(t(swap + 8), "B hook", "B's hook continues — the floor never got a break",
          "תיבה {bar}: B ממשיך בפזמון שלו — הרחבה לא קיבלה אפילו שנייה של ירידה באנרגיה.")
    mx.description_he = (
        f"החלפת דרופים בים-תיכוני: בזמן שהפזמון של {A.short()} מתנגן, הבילד של {B.short()} נכנס מעליו בלי Low, "
        f"ובדיוק במקום שבו A היה יורד לברייקדאון — נוחת הדרופ של B. B מותאם מ-{B.bpm:g} ל-{A.bpm:g} BPM "
        f"(Master Tempo, בלי שינוי בגובה הצליל). ‎{A.camelot}→{B.camelot} — שכנים בגלגל.")
    mx.exercise_he = common_exercise(mx, a, b, "Master Tempo דולק, Low למטה, פיידר למטה.") + [
        "נגנו את A מ-Hot Cue D. אחרי 8 תיבות — על ה-1 — הפעילו את B והעלו את הפיידר שלו ב-4 תיבות.",
        "4 תיבות לפני הסוף של הדרופ של A: הורידו בהדרגה Mid ו-High שלו.",
        "על ה-1 שבו A היה נכנס לברייקדאון: פיידר A למטה ו-Low של B לאמצע — הדרופ של B נוחת.",
    ]


# technique → (recipe, lead bars before mix bar 1, total demo bars)
RECIPES: dict[str, tuple[Callable[[Mix], None], int, int]] = {
    "blend": (demo_blend, 8, 48),
    "bass_swap": (demo_bass_swap, 8, 48),
    "filter": (demo_filter, 8, 40),
    "echo_out": (demo_echo_out, 16, 40),
    "loop_roll": (demo_loop_roll, 16, 40),
    "energy_boost": (demo_energy_boost, 8, 40),
    "breakdown_mix": (demo_breakdown_mix, 16, 48),
    "cut": (demo_cut, 24, 40),
    "tempo_change_echo": (demo_tempo_change_echo, 16, 40),
    "drop_swap": (demo_drop_swap, 8, 32),
}
# closest available pair per demo if a planned source track is still missing
FALLBACKS: dict[str, tuple[str, str]] = {}


# ============================================================================ build / export
def build(entry: dict) -> Mix:
    tech = entry["technique"]
    if tech not in RECIPES:
        raise KeyError(f"no recipe for technique {tech!r}")
    fn, lead, bars = RECIPES[tech]
    fa, fb = entry["from_id"], entry["to_id"]
    note = None
    if not (Track.exists(fa) and Track.exists(fb)):
        alt = FALLBACKS.get(entry["id"])
        if not alt or not (Track.exists(alt[0]) and Track.exists(alt[1])):
            raise FileNotFoundError(f"{entry['id']}: source track(s) {fa}/{fb} not rendered yet")
        note = f"planned pair {fa} → {fb} was not rendered yet; substituted {alt[0]} → {alt[1]}"
        fa, fb = alt
    mx = Mix(entry, Track(fa), Track(fb), lead, bars)
    if note:
        mx.notes["substitution_note"] = note
    fn(mx)
    return mx


def render_audio(mx: Mix, verbose: bool = False) -> np.ndarray:
    n = int(round(mx.duration * SR))
    bus = np.zeros((n, 2), F32)
    for d in mx.decks:
        bus += render_deck(d, n)
    fi = int(0.003 * SR)
    bus[:fi] *= np.linspace(0.0, 1.0, fi, dtype=F32)[:, None]
    fo_start = int(round(mx.clock.t_pos(mx.bars - 2) * SR))
    k = n - fo_start
    bus[fo_start:] *= (0.5 + 0.5 * np.cos(np.linspace(0.0, np.pi, k))).astype(F32)[:, None]
    y, L, gr = master_bus(bus, SR, TARGET_LUFS, verbose)
    mx.notes["limiter_max_gr_db"] = round(gr, 2)
    return y


def title_of(mx: Mix) -> tuple[str, str]:
    e = mx.entry
    en = f"{TECH_EN.get(e['technique'], e['technique'])}: {mx.a.title} → {mx.b.title}"
    he = f"{e['technique_he']} — {mx.a.title_he} ← {mx.b.title_he}"
    return en, he


def sidecar(mx: Mix, mp3: Path, L: float, tp: float, dur: float) -> dict:
    from .export import rel

    e = mx.entry
    en, he = title_of(mx)
    steps = [ev for ev in mx.events if ev["he"]]
    a, b = mx.decks[0], mx.decks[1]
    timeline = []
    for ev in mx.events:
        timeline.append({"t": ev["t"], "bar": ev["bar"], "beat": ev["beat"],
                         "pos": f"{ev['bar'] + 1}.{ev['beat']}", "action": ev["action"]})
    cues = []
    for slot, ev in zip("ABCDEFGH", steps):
        cues.append({"slot": slot, "name": ev["cue"], "bar": ev["bar"], "sec": ev["t"],
                     "color": SLOT_COLORS[slot], "type": "hot"})

    def deck_info(d: Deck) -> dict:
        return {"id": d.track.id, "title": d.track.title, "title_he": d.track.title_he, "bpm": d.track.bpm,
                "camelot": d.track.camelot, "file": d.track.file,
                "play_from_bar": int(d.src_bar), "play_from_sec": round(d.track.bar_sec(d.src_bar), 3),
                "enters_at_sec": round(d.t_start, 3), "tempo": d.tempo_note() or f"{d.track.bpm:g} BPM"}

    meta = {
        "id": e["id"], "kind": "transition", "title": en, "title_he": he,
        "artist": ARTIST, "album": ALBUM, "genre": GENRE,
        "technique": e["technique"], "technique_he": e["technique_he"],
        "from_id": mx.a.id, "to_id": mx.b.id,
        "bpm": float(mx.clock.bpm_at(0.0)),
    }
    if "tempo_map" in mx.notes:
        meta["tempo_map"] = mx.notes["tempo_map"]
    meta.update({
        "duration_sec": round(dur, 3), "bars": mx.bars, "beats_per_bar": 4, "first_downbeat_sec": 0.0,
        "decks": {"A": deck_info(a), "B": deck_info(b)},
        "steps_he": [f"{mmss(ev['t'])} — {ev['he']}" for ev in steps],
        "timeline": timeline,
        "cues": cues,
        "description_he": mx.description_he,
        "exercise_he": "\n".join(f"{i + 1}. {s}" for i, s in enumerate(mx.exercise_he)),
        "lufs": L, "true_peak_dbtp": tp,
        "file": rel(mp3),
    })
    if "substitution_note" in mx.notes:
        meta["planned_pair"] = [e["from_id"], e["to_id"]]
        meta["substitution_note"] = mx.notes["substitution_note"]
    meta.update({"mixer": "djlab.djmix", "license": "CC0-1.0", "engine_version": ENGINE_VERSION})
    return meta


def write_tags(path: Path, meta: dict) -> None:
    from mutagen.id3 import COMM, ID3, TALB, TBPM, TCON, TCOP, TDRC, TIT2, TPE1, TSSE

    a, b = meta["decks"]["A"], meta["decks"]["B"]
    tags = ID3()
    tags.add(TIT2(encoding=3, text=meta["title"]))
    tags.add(TPE1(encoding=3, text=ARTIST))
    tags.add(TALB(encoding=3, text=ALBUM))
    tags.add(TCON(encoding=3, text=GENRE))
    tags.add(TBPM(encoding=3, text=str(int(round(meta["bpm"])))))
    tags.add(COMM(encoding=3, lang="eng", desc="",
                  text=f"{a['id']} {a['camelot']} {a['bpm']:g} → {b['id']} {b['camelot']} {b['bpm']:g} · "
                       f"{TECH_EN.get(meta['technique'], meta['technique'])} · CC0"))
    tags.add(TDRC(encoding=3, text="2026"))
    tags.add(TCOP(encoding=3, text="CC0 1.0"))
    tags.add(TSSE(encoding=3, text=f"djlab {ENGINE_VERSION} djmix"))
    tags.save(str(path), v2_version=4)


def render_transition(entry: dict, out_dir: Path | None = None, verbose: bool = True) -> dict:
    from .export import export_mp3_safe, write_json

    t0 = time.time()
    mx = build(entry)
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    log(f"[{entry['id']}] {entry['technique']}: {mx.a.id} ({mx.a.bpm:g}) → {mx.b.id} ({mx.b.bpm:g}) · "
        f"{mx.bars} bars · {mx.duration:.1f}s")
    y = render_audio(mx, verbose=verbose)
    out_dir = Path(out_dir or OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{entry['id']}-{entry['technique']}"
    mp3 = out_dir / f"{stem}.mp3"
    dec, L, tp = export_mp3_safe(y, mp3, SR, max_tp=-1.0, verbose=verbose)
    meta = sidecar(mx, mp3, L, tp, dec.shape[0] / SR)
    write_tags(mp3, meta)
    write_json(out_dir / f"{stem}.json", meta)
    dt = time.time() - t0
    log(f"[{entry['id']}] → {mp3}  ({L} LUFS, TP {tp} dBTP, {meta['duration_sec']:.1f}s, "
        f"limiter GR {mx.notes.get('limiter_max_gr_db')} dB, {dt:.1f}s)")
    return {"id": entry["id"], "path": str(mp3), "lufs": L, "true_peak": tp, "duration": meta["duration_sec"],
            "seconds": round(dt, 1)}


def _worker(args):
    entry, out = args
    try:
        return render_transition(entry, out_dir=out)
    except Exception as e:  # report and continue
        import traceback

        traceback.print_exc()
        return {"id": entry["id"], "error": f"{type(e).__name__}: {e}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m djlab.djmix", description="Render DJ Lab transition demos")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", nargs="+", help="transition id(s), e.g. transition-02")
    g.add_argument("--all", action="store_true", help="render every transition in music/extras.plan.json")
    g.add_argument("--list", action="store_true", help="list transitions and source availability")
    ap.add_argument("--jobs", type=int, default=1, help="parallel processes (default 1)")
    ap.add_argument("--out", help="output directory override (e.g. scratch, for determinism checks)")
    args = ap.parse_args(argv)
    entries = load_extras()
    if args.list:
        for e in entries:
            ok = Track.exists(e["from_id"]) and Track.exists(e["to_id"])
            rec = "✓" if e["technique"] in RECIPES else "·"
            print(f"{e['id']:<14} {rec} {e['technique']:<18} {e['from_id']:>14} → {e['to_id']:<14} "
                  f"{'ready' if ok else 'waiting for source'}")
        return 0
    sel = entries if args.all else [e for e in entries if e["id"] in set(args.id)]
    if not args.all:
        missing = set(args.id) - {e["id"] for e in sel}
        if missing:
            print(f"unknown id(s): {sorted(missing)}", file=sys.stderr)
            return 2
    out = Path(args.out) if args.out else None
    t0 = time.time()
    jobs = [(e, out) for e in sel]
    if args.jobs <= 1 or len(jobs) == 1:
        res = [_worker(j) for j in jobs]
    else:
        import multiprocessing as mp

        with mp.get_context("fork").Pool(args.jobs, maxtasksperchild=1) as pool:
            res = pool.map(_worker, jobs, chunksize=1)
    bad = [r for r in res if "error" in r]
    print(f"\nrendered {len(res) - len(bad)}/{len(res)} in {time.time() - t0:.1f}s")
    for r in bad:
        print(f"  FAILED {r['id']}: {r['error']}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
