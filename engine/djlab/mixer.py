"""Mixer: renders every layer, applies per-layer automation/filters/sidechain/sends, processes the
buses (glue compression, saturation, mono-izing low end) and the send returns (reverbs, delay).

Bus names: ``drums``, ``bass``, ``music``, ``fx``, ``vox`` (+ any custom name: unknown buses get a
neutral default). Returns: ``reverb`` (plate), ``hall``, ``room``, ``delay`` (dotted 8th), ``delay8``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .dsp import F32, as_stereo, compressor, db2lin, eq_highshelf, eq_lowshelf, eq_peak, hp as _hp, lp as _lp, svf
from . import fx as _fx


@dataclass
class Bus:
    name: str
    gain_db: float = 0.0
    hp: float | None = None
    lp: float | None = None
    comp: dict | None = None
    sat: float = 0.0  # tanh drive amount 0..1
    mono_below: float | None = None
    width: float = 1.0
    sidechain: float = 0.0
    sc_release_ms: float | None = None
    eq: list = field(default_factory=list)  # [("peak"|"lowshelf"|"highshelf", f, gain_db, q)]


@dataclass
class Return:
    name: str
    kind: str = "reverb"  # reverb | delay
    preset: str = "plate"
    decay: float | None = None
    predelay_ms: float | None = None
    beats: float = 0.75
    feedback: float = 0.38
    hp: float = 300.0
    lp: float = 9000.0
    gain_db: float = 0.0
    sidechain: float = 0.5
    sc_release_ms: float | None = None
    width: float = 1.0


def default_buses() -> dict[str, Bus]:
    return {
        "drums": Bus("drums", comp=dict(threshold_db=-10.0, ratio=2.5, attack_ms=15.0, release_ms=90.0, makeup_db=1.0),
                     sat=0.15, mono_below=110.0),
        "bass": Bus("bass", hp=28.0, mono_below=180.0, sat=0.1,
                    comp=dict(threshold_db=-12.0, ratio=3.0, attack_ms=6.0, release_ms=70.0)),
        "music": Bus("music", hp=120.0, mono_below=160.0),
        "fx": Bus("fx", hp=140.0, mono_below=200.0),
        "vox": Bus("vox", hp=160.0, mono_below=200.0,
                   comp=dict(threshold_db=-14.0, ratio=3.0, attack_ms=5.0, release_ms=80.0, makeup_db=2.0)),
    }


def default_returns(bpm: float) -> dict[str, Return]:
    return {
        "reverb": Return("reverb", "reverb", "plate", width=1.2),
        "hall": Return("hall", "reverb", "hall", hp=350.0, lp=8000.0, sidechain=0.6, width=1.3),
        "room": Return("room", "reverb", "room", hp=200.0, lp=10000.0, sidechain=0.3),
        "delay": Return("delay", "delay", beats=0.75, feedback=0.38, hp=350.0, lp=5000.0, sidechain=0.5),
        "delay8": Return("delay8", "delay", beats=0.5, feedback=0.3, hp=400.0, lp=6000.0, sidechain=0.5),
    }


def _apply_width(x, width, mono_below):
    if (width == 1.0 or width is None) and not mono_below:
        return x
    return _fx.widen(x, width if width is not None else 1.0, mono_below)


def _times(verbose, label, t0):
    if verbose:
        print(f"    {label:<18s}{time.time() - t0:6.2f}s")


def mix(song, a: int, b: int, verbose: bool = False):
    """Render & mix the song for samples [a, b). Returns float32 stereo pre-master mix."""
    n = b - a
    sr = song.sr
    # ---------------------------------------------------------------- sidechain triggers
    trig, vels = [], []
    for l in song.layers:
        if getattr(l, "sc_source", False) and not l.mute:
            for pos, vel, _ in l.events(song, a, b):
                trig.append(pos - a)
                vels.append(min(1.0, vel / 0.82))
    sc_cache: dict = {}

    def sc_env(release_ms):
        release_ms = release_ms or (60000.0 / song.bpm) * 0.45
        key = round(release_ms, 1)
        if key not in sc_cache:
            sc_cache[key] = _fx.sidechain_env(trig, n, release_ms, velocities=vels, sr=sr)
        return sc_cache[key]

    buses = {name: np.zeros((n, 2), dtype=F32) for name in song.buses}
    sends = {name: None for name in song.returns}
    for l in song.layers:
        if l.mute:
            continue
        t0 = time.time()
        x = l.render_dry(song, a, b)
        if x is None:
            continue
        x = as_stereo(x)
        for f in l.fx:
            x = as_stereo(f(x))
        if l.hp:
            x = _hp(x, l.hp, 2, sr)
        if l.lp:
            x = _lp(x, l.lp, 2, sr)
        c = l.curve(song, "hp", a, b)
        if c is not None:
            x = svf(x, c, l.res, "hp", sr)
        c = l.curve(song, "lp", a, b)
        if c is not None:
            x = svf(x, c, l.res, "lp", sr)
        if l.width is not None:
            x = _fx.widen(x, l.width, 150.0)
        p = l.curve(song, "pan", a, b, l.pan)
        if np.isscalar(p):
            if p:
                x = _pan_stereo(x, float(p))
        else:
            x = _pan_stereo_curve(x, p)
        gdb = l.curve(song, "gain_db", a, b, None)
        g = db2lin(l.gain_db) if gdb is None else db2lin(gdb + l.gain_db).astype(F32)[:, None]
        x = (x * g).astype(F32)
        if l.sidechain and trig:
            x = _fx.apply_sidechain(x, sc_env(l.sc_release_ms), l.sidechain)
        if l.bus not in buses:
            song.buses[l.bus] = Bus(l.bus)
            buses[l.bus] = np.zeros((n, 2), dtype=F32)
        buses[l.bus] += x
        # sends (post-fader)
        for rname in song.returns:
            lvl = l.curve(song, "send:" + rname, a, b, l.sends.get(rname, 0.0))
            if np.isscalar(lvl) and lvl <= 0:
                continue
            s = x * (F32(lvl) if np.isscalar(lvl) else lvl.astype(F32)[:, None])
            sends[rname] = s if sends[rname] is None else sends[rname] + s
        _times(verbose, l.name, t0)

    out = np.zeros((n, 2), dtype=F32)
    for name, buf in buses.items():
        out += process_bus(buf, song.buses[name], sc_env if trig else None, sr)
    for rname, s in sends.items():
        if s is None:
            continue
        t0 = time.time()
        r = song.returns[rname]
        if r.kind == "reverb":
            w = _fx.reverb(s, r.preset, r.decay, r.predelay_ms, hp_hz=r.hp, lp_hz=r.lp, sr=sr)
        else:
            w = _fx.tempo_delay(s, song.bpm, r.beats, r.feedback, r.lp, r.hp, True, sr)
        if r.width != 1.0:
            w = _fx.widen(w, r.width, 200.0)
        if r.sidechain and trig:
            w = _fx.apply_sidechain(w, sc_env(r.sc_release_ms), r.sidechain)
        out += w * F32(db2lin(r.gain_db))
        _times(verbose, "return:" + rname, t0)
    return out


def _pan_stereo(x, p):
    return _pan_stereo_curve(x, np.float64(p))


def _pan_stereo_curve(x, p):
    a = (np.clip(p, -1, 1) + 1.0) * np.pi / 4.0
    gl = np.minimum(np.cos(a) * np.sqrt(2), 1.0)
    gr = np.minimum(np.sin(a) * np.sqrt(2), 1.0)
    return np.stack([x[:, 0] * gl, x[:, 1] * gr], axis=1).astype(F32)


def process_bus(x, bus: Bus, sc_env=None, sr=44100):
    if not np.any(x):
        return x
    if bus.hp:
        x = _hp(x, bus.hp, 2, sr)
    if bus.lp:
        x = _lp(x, bus.lp, 2, sr)
    for kind, f, gdb, q in bus.eq:
        x = {"peak": eq_peak, "lowshelf": eq_lowshelf, "highshelf": eq_highshelf}[kind](x, f, gdb, q, sr)
    if bus.comp:
        # threshold is relative to the bus's own peak level so behaviour is level independent
        pk = float(np.abs(x).max()) + 1e-9
        c = dict(bus.comp)
        c["threshold_db"] = c.get("threshold_db", -12.0) + 20 * np.log10(pk)
        x = compressor(x, sr=sr, **c)
    if bus.sat:
        pk = float(np.abs(x).max()) + 1e-9
        d = 1.0 + 3.0 * bus.sat
        x = (np.tanh(x / pk * d) / np.tanh(d) * pk).astype(F32)
    if bus.mono_below or bus.width != 1.0:
        x = _fx.widen(x, bus.width, bus.mono_below)
    if bus.sidechain and sc_env is not None:
        x = _fx.apply_sidechain(x, sc_env(bus.sc_release_ms), bus.sidechain)
    return (x * F32(db2lin(bus.gain_db))).astype(F32)
