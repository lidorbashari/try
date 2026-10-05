"""House-family sound design shared by the house producer's recipes.

Deep house, house, tech house, afro house, nu-disco and amapiano need a few instruments the core
does not have (or needs in a more detailed form): a Rhodes-style FM electric piano, a multi-string
additive house piano, a percussive drawbar organ, a string machine with ensemble chorus, a muted
"chicken-scratch" guitar (Karplus-Strong), chant/choir formant voices, a talking/wah bass, an
amapiano log drum that can slide between notes, and organic hand percussion (clave, woodblock,
djembe, talking drum, shekere, the amapiano "pha").

Conventions follow the core (see ``instruments.py`` / ``drums.py``):

* instrument factories return ``inst(freq_hz, dur_sec, vel)`` → mono ``(n,)`` or stereo ``(n, 2)``
  float32 with peak ≈ ``0.8 * vel``; the note tail (release) is included;
* drum one-shots are mono float32, peak 1.0, transient at sample 0;
* layer effects (``fx=[...]`` on a layer) take and return a stereo buffer. They only process the
  non-silent span of the buffer, so a layer that plays 30 s of a 4-minute track stays cheap.

All randomness uses fixed per-note seeds or the recipe ``rng`` → renders stay deterministic.
"""
from __future__ import annotations

import math

import numpy as np

from . import SR, drums, fx
from .arrangement import Notes
from .dsp import (F32, as_stereo, fade, hp, ladder, lp, mix_into, mod_delay, normalize, pan, saw, sine, square,
                  svf, karplus)
from .synth import adsr, fm, formant_filter, white
from .theory import Key, hz_to_midi, midi_to_hz, voice_lead

TAU = 2 * math.pi


def _n(dur, release, sr=SR):
    gate = max(16, int(dur * sr))
    return gate, gate + int(release * sr)


def _finish(x, vel, rel_fade=64):
    x = fade(np.asarray(x, dtype=F32), 16, rel_fade)
    return normalize(x, 0.8 * float(vel))


def _seed(freq, salt=0):
    return (int(freq * 1000) * 2654435761 + salt) % (2 ** 32)


# ============================================================================ helpers (keys / tuning)
def bass_root(key: Key, lo: int = 31) -> int:
    """MIDI root for bass lines: the key root in octave 1, raised into [lo, lo+11] (A1, B1, C2 … F#2)."""
    r = key.root(1)
    while r < lo:
        r += 12
    while r >= lo + 12:
        r -= 12
    return r


def sub_root(key: Key) -> int:
    """MIDI root for a sine sub layer: D1 (36.7 Hz) … C#2 (69 Hz)."""
    r = key.root(1)
    while r < 26:
        r += 12
    while r > 37:
        r -= 12
    return r


def sub_events(events, root: int, sub: int, vel: float = 0.9):
    """Sine-sub notes that follow a bass line: every note below the octave pop is copied into the
    sub register (``sub`` = :func:`sub_root`), octave pops are skipped."""
    shift = sub - root
    return [(e[0], e[1], e[2] + shift, e[3] * vel) for e in events if e[2] - root < 12]


def key_hz(key: Key, lo: float, hi: float, rng=None, degrees=(0, 4, 2, 3, 6)) -> float:
    """A frequency in [lo, hi] Hz that is a scale tone of ``key`` (root/5th/3rd/4th/7th preferred) —
    for tuning congas, bongos, toms and blips so hand percussion sits in the key instead of adding
    random pitches. With ``rng`` a random candidate is chosen (deterministic)."""
    cands = []
    for d in degrees:
        pc = (key.root_pc + key.scale[d % len(key.scale)]) % 12
        for octv in range(0, 9):
            f = float(midi_to_hz(12 * (octv + 1) + pc))
            if lo <= f <= hi:
                cands.append(f)
    if not cands:
        return float(np.sqrt(lo * hi))
    if rng is None:
        return cands[0]
    return float(cands[int(rng.integers(len(cands)))])


def kick_tune(key: Key, lo: float = 44.0, hi: float = 60.0) -> float:
    """Kick body pitch that is a chord tone of the key (root, fifth, fourth) inside [lo, hi] Hz."""
    for semis in (0, 7, 5, 3):
        pc = (key.root_pc + semis) % 12
        for octv in (0, 1, 2):
            f = float(midi_to_hz(12 * (octv + 1) + pc))
            if lo <= f <= hi:
                return f
    return float(np.clip(midi_to_hz(key.root(1)), lo, hi))


def chord_voicing(key: Key, deg: int, size: int = 5, rootless: bool = True, octave: int = 3) -> list[int]:
    """Diatonic chord on ``deg`` stacked in thirds (size 4 = 7th, 5 = 9th); rootless = drop the root
    (the bass plays it) like a keyboard player's left-hand voicing."""
    ch = key.chord(deg, octave, size)
    return ch[1:] if rootless and len(ch) > 3 else ch


def voice_progression(key: Key, degs, sizes=None, center: int = 62, rootless: bool = True) -> list[list[int]]:
    """Voice-led chords for a list of scale degrees."""
    out, prev = [], None
    sizes = sizes or [5] * len(degs)
    for d, s in zip(degs, sizes):
        ch = voice_lead(prev, chord_voicing(key, d, s, rootless), center=center)
        out.append(ch)
        prev = ch
    return out


def chord_bass(key: Key, chord_deg: int, step: int, lo: int) -> int:
    """Bass note ``step`` scale steps above the chord root, with the chord root folded once into
    the octave [lo, lo+12) — so octave pops and passing tones keep their real interval."""
    base = key.degree(chord_deg, 1)
    while base < lo:
        base += 12
    while base >= lo + 12:
        base -= 12
    return base + key.degree(chord_deg + step, 1) - key.degree(chord_deg, 1)


def degree_root(key: Key, deg: int, base: int) -> int:
    """MIDI of scale degree ``deg`` placed in the octave starting at ``base`` (a bass root)."""
    pc = (key.root_pc + key.scale[deg % len(key.scale)]) % 12
    m = base - (base % 12) + pc
    while m < base:
        m += 12
    while m >= base + 12:
        m -= 12
    return m


# ============================================================================ layer effects
def _span(x, pad_sec=0.5, sr=SR):
    nz = np.flatnonzero(np.abs(x).max(axis=1) > 1e-7)
    if nz.size == 0:
        return None
    return int(nz[0]), min(x.shape[0], int(nz[-1]) + int(pad_sec * sr))


def autopan(bpm: float, beats: float = 0.5, depth: float = 0.3, sr=SR):
    """Tempo-synced stereo tremolo (Rhodes suitcase style). Phase is locked to sample 0 = bar 1."""
    def f(x):
        x = as_stereo(x).copy()
        sp = _span(x, 0.0, sr)
        if sp is None:
            return x
        a, b = sp
        ph = TAU * (np.arange(a, b, dtype=np.float64) / sr * bpm / 60.0 / beats)
        m = np.sin(ph)
        x[a:b, 0] *= (1.0 - depth * (0.5 + 0.5 * m)).astype(F32)
        x[a:b, 1] *= (1.0 - depth * (0.5 - 0.5 * m)).astype(F32)
        return x
    return f


def ensemble(depth_ms: float = 2.0, rate: float = 0.6, fast_rate: float = 6.2, fast_ms: float = 0.22,
             mix: float = 0.75, sr=SR):
    """Three-phase string-machine ensemble chorus (Solina style). Stereo out, mono-safe."""
    def f(x):
        xs = as_stereo(x)
        sp = _span(xs, 0.1, sr)
        if sp is None:
            return xs
        a, b = sp
        m = xs[a:b].mean(axis=1).astype(np.float64)
        t = np.arange(b - a, dtype=np.float64) / sr + a / sr
        taps = []
        for ph in (0.0, 1 / 3, 2 / 3):
            d = 8.0 + depth_ms * np.sin(TAU * (rate * t + ph)) + fast_ms * np.sin(TAU * (fast_rate * t + ph))
            taps.append(mod_delay(m, d, sr))
        wet = np.stack([taps[0] + 0.5 * taps[1], taps[2] + 0.5 * taps[1]], axis=1) / 1.5
        out = xs.copy()
        out[a:b] = ((1 - mix) * xs[a:b] + mix * wet).astype(F32)
        return out
    return f


def leslie(rate: float = 5.8, depth_ms: float = 0.6, am: float = 0.18, mix: float = 0.6, sr=SR):
    """Rotary-speaker-ish chorus + amplitude wobble for organs."""
    def f(x):
        xs = as_stereo(x)
        sp = _span(xs, 0.1, sr)
        if sp is None:
            return xs
        a, b = sp
        m = xs[a:b].mean(axis=1).astype(np.float64)
        t = np.arange(b - a, dtype=np.float64) / sr + a / sr
        l = mod_delay(m, 3.0 + depth_ms * np.sin(TAU * rate * t), sr)
        r = mod_delay(m, 3.0 + depth_ms * np.sin(TAU * rate * t + 1.9), sr)
        l = l * (1 - am * (0.5 + 0.5 * np.sin(TAU * rate * t)))
        r = r * (1 - am * (0.5 + 0.5 * np.sin(TAU * rate * t + 1.9)))
        out = xs.copy()
        out[a:b] = ((1 - mix) * xs[a:b] + mix * np.stack([l, r], axis=1)).astype(F32)
        return out
    return f


def saturate_fx(drive=1.6, mix=1.0):
    return lambda x: fx.saturate(x, drive, mix)


def tape_fx(drive=1.3, warmth=0.4):
    return lambda x: fx.tape(x, drive, warmth)


# ============================================================================ keys
def rhodes(bright: float = 0.55, bark: float = 0.5, decay: float | None = None, release: float = 0.3,
           drive: float = 0.25, detune_cents: float = 3.0, lp_hz: float = 7000.0, sr=SR):
    """Rhodes-style FM electric piano (DX 'E.Piano' topology): two slightly detuned 1:1 FM body
    stacks whose index rises with velocity (the 'bark'), a 14:1 tine transient, pitch-dependent
    decay, soft tube-ish drive and a velocity-dependent low-pass. Stereo (pitch-dependent pan);
    add :func:`autopan` on the layer for the suitcase tremolo."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        td = decay or 2.4 * (220.0 / freq) ** 0.4
        v2 = vel * vel
        idx_env = (0.2 + bark * 1.8 * v2) * np.exp(-t / 0.22) + 0.12 + 0.1 * bright
        body = fm(freq, n, 1.0, 1.0, idx_env)
        body2 = fm(freq * 2 ** (detune_cents / 1200), n, 1.0, 1.0, idx_env * 0.85)
        tine = fm(freq, n, 14.0, 0.8 + 1.6 * vel, np.exp(-t / 0.010)) * np.exp(-t / 0.3)
        x = 0.72 * body + 0.45 * body2 + (0.25 + 0.4 * bright) * vel * tine
        d = 1.0 + 3.0 * drive
        x = np.tanh(x * d) / math.tanh(d)
        env = np.exp(-t / td) * adsr(n, gate, 0.0015, 10.0, 1.0, release, sr)
        x = svf((x * env).astype(F32), lp_hz * (0.55 + 0.45 * vel), 0.6, "lp")
        midi = float(hz_to_midi(freq))
        return _finish(pan(x, float(np.clip((midi - 64) / 36, -0.35, 0.35))), vel, rel_fade=256)
    return inst


def house_piano(bright: float = 0.7, strings: int = 3, detune_cents: float = 1.6, hammer: float = 0.6,
                decay: float = 1.0, release: float = 0.22, bell: float = 0.15, stereo: float = 0.6, sr=SR):
    """Additive 'house piano': up to 20 inharmonic partials per string, 2–3 slightly detuned strings
    panned across the stereo field (natural chorus/beating), two-stage decay (prompt + aftersound),
    hammer-position comb, felt/hammer noise, an FM 'bell' attack for the bright M1-ish house tone
    and a velocity-dependent low-pass. Stereo."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        n = min(n, int(7 * sr))
        t = np.arange(n) / sr
        midi = float(hz_to_midi(freq))
        B = 1.2e-4 * 2 ** ((midi - 48) / 18)
        T = float(np.clip(decay * 4.0 * (130.0 / freq) ** 0.55, 0.5, 8.0))
        tilt = 1.3 - 0.6 * bright * vel
        K = int(max(3, min(20, 13000 / freq)))
        rng = np.random.default_rng(_seed(freq, 11))
        L = np.zeros(n)
        R = np.zeros(n)
        S = max(1, strings)
        for k in range(1, K + 1):
            fk = freq * k * math.sqrt(1 + B * k * k)
            if fk > 15000:
                break
            ak = k ** -tilt * (0.35 + 0.65 * abs(math.sin(math.pi * k * 0.137)))
            env = 0.62 * np.exp(-t / (T * 0.09 / (1 + 0.07 * k))) + 0.38 * np.exp(-t / (T / (1 + 0.2 * k)))
            for s in range(S):
                c = (s - (S - 1) / 2) * detune_cents
                sig = np.sin(TAU * fk * 2 ** (c / 1200) * t + rng.random() * TAU) * (ak / S) * env
                w = 0.5 if S == 1 else 0.5 + 0.5 * stereo * ((s / (S - 1)) * 2 - 1)
                L += sig * (1 - w) * 2
                R += sig * w * 2
        mono_extra = np.zeros(n)
        if bell:
            mono_extra += bell * vel * fm(freq, n, 4.0, 1.4, np.exp(-t / 0.05)) * np.exp(-t / 0.35)
        if hammer:
            nh = min(n, int(0.04 * sr))
            th = t[:nh]
            hn = svf(white(nh, rng), float(np.clip(freq * 4, 900, 4500)), 0.9, "bp") * np.exp(-th / 0.006)
            thump = np.sin(TAU * freq * th) * np.exp(-th / 0.012)
            mono_extra[:nh] += hammer * vel * (0.5 * hn + 0.25 * thump)
        x = np.stack([L + mono_extra, R + mono_extra], axis=1)
        env = adsr(n, gate, 0.0012, 20.0, 1.0, release, sr)
        x = x * env[:, None]
        x = svf(x.astype(F32), 2200 + 9000 * vel * bright, 0.6, "lp")
        p = float(np.clip((midi - 60) / 40, -0.3, 0.3))
        x = pan(x, p) if p else x
        return _finish(x, vel, rel_fade=256)
    return inst


def house_organ(drawbars=(0.7, 1.0, 0.0, 0.75, 0.4, 0.55, 0.0, 0.25, 0.35), click: float = 0.35,
                perc: float = 0.4, sustain: float = 0.55, decay: float = 0.28, drive: float = 1.4,
                release: float = 0.06, sr=SR):
    """Percussive drawbar organ for house stabs (16' 8' 5⅓' 4' 2⅔' 2' 1⅗' 1⅓' 1'), key click,
    2nd-harmonic percussion and gentle overdrive. Pair with :func:`leslie` on the layer."""
    ratios = (0.5, 1, 1.5, 2, 3, 4, 5, 6, 8)

    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        x = np.zeros(n)
        for r, a in zip(ratios, drawbars):
            if a and freq * r < 15000:
                x += a * np.sin(TAU * freq * r * t + r)
        x += perc * vel * np.sin(TAU * freq * 2 * t) * np.exp(-t / 0.09)
        if click:
            nc = min(n, int(0.005 * sr))
            x[:nc] += click * hp(white(nc, np.random.default_rng(_seed(freq, 3))), 1800.0) * np.exp(-t[:nc] / 0.0012)
        x = x / sum(drawbars)
        x = np.tanh(x * drive) / math.tanh(drive)
        env = adsr(n, gate, 0.002, decay, sustain, release, sr)
        return _finish(x * env, vel)
    return inst


def string_machine(attack: float = 0.3, release: float = 0.9, cutoff: float = 4800.0, octave: float = 0.55,
                   sr=SR):
    """String machine voice (divide-down saws, 8' + 4'), soft attack. Put :func:`ensemble` on the
    layer for the classic lush chorus."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        x = saw(freq, n) * 0.7 + saw(freq * 2.0, n, 0.3) * octave * 0.5
        x = svf(x, cutoff * (0.7 + 0.3 * vel), 0.6, "lp")
        x = hp(x, 140.0)
        env = adsr(n, gate, attack, 0.6, 0.85, release, sr, curve=3.5)
        return _finish(x * env, vel, rel_fade=512)
    return inst


def soft_pad(attack: float = 1.2, release: float = 2.0, cutoff: float = 1600.0, detune_cents: float = 7.0,
             air: float = 0.25, sr=SR):
    """Warm, slow pad (detuned saw/triangle pairs + breathy air) for filtered house/afro pads."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        rng = np.random.default_rng(_seed(freq, 5))
        a = saw(freq * 2 ** (detune_cents / 1200), n, rng.random())
        b = saw(freq * 2 ** (-detune_cents / 1200), n, rng.random())
        tri = np.sin(TAU * freq * t) * 0.4
        cut = cutoff * (1 + 0.25 * np.sin(TAU * 0.11 * t + freq))
        L = svf(a * 0.6 + tri, cut, 0.7, "lp")
        R = svf(b * 0.6 + tri, cut * 1.03, 0.7, "lp")
        nz = svf(white(n, rng), float(min(9000, freq * 8)), 1.5, "bp") * air
        x = np.stack([L + nz, R + nz * 0.8], axis=1)
        env = adsr(n, gate, attack, 1.0, 0.9, release, sr, curve=3.0)
        return _finish(x * env[:, None], vel, rel_fade=1024)
    return inst


# ============================================================================ plucked / mallets
def muted_guitar(mute: float = 0.11, bright: float = 0.62, decay: float = 0.994, pick: float = 0.5,
                 body_hz: float = 1900.0, wah: float = 0.0, sr=SR):
    """Disco/funk rhythm guitar: Karplus-Strong string, palm-mute envelope, pick noise, body
    resonance, optional envelope 'wah' (0..1). Mono."""
    def inst(freq, dur, vel):
        ln = int(max(dur + mute * 2.5, 0.12) * sr)
        t = np.arange(ln) / sr
        rng = np.random.default_rng(_seed(freq, 31))
        x = karplus(freq, ln, decay, bright * (0.55 + 0.45 * vel), rng)
        gate_t = max(dur, 0.03)
        env = np.exp(-t / (mute * (0.6 + 0.7 * vel)))
        env = np.where(t < gate_t, env, env * np.exp(-(t - gate_t) / 0.025))
        x = x * env
        nk = min(ln, int(0.006 * sr))
        x[:nk] += pick * vel * hp(white(nk, rng), 2500.0) * np.exp(-t[:nk] / 0.0015)
        x = x + 0.45 * svf(x, body_hz, 1.4, "bp")
        if wah:
            fc = 500 + 2200 * wah * vel * np.exp(-t / 0.07) * (1 - np.exp(-t / 0.006))
            x = (1 - 0.7 * wah) * x + 0.7 * wah * svf(x.astype(F32), fc, 3.5, "bp") * 2.0
        x = hp(x.astype(F32), 170.0)
        return _finish(x, vel, rel_fade=128)
    return inst


def kalimba(bright: float = 0.5, decay: float = 0.9, sr=SR):
    """Kalimba / mbira tine: fundamental + inharmonic tine modes (≈5.9, 13.4), thumb-noise attack
    and a small resonator box. Mono."""
    def inst(freq, dur, vel):
        n = int(max(dur, decay * 2.2) * sr)
        t = np.arange(n) / sr
        rng = np.random.default_rng(_seed(freq, 7))
        x = np.sin(TAU * freq * t) * np.exp(-t / (decay * (300.0 / freq) ** 0.25))
        x += 0.22 * bright * np.sin(TAU * freq * 5.93 * t + 0.4) * np.exp(-t / 0.06)
        x += 0.08 * bright * np.sin(TAU * freq * 13.4 * t) * np.exp(-t / 0.02)
        x += 0.12 * np.sin(TAU * freq * 2.0 * t) * np.exp(-t / 0.25)
        nk = min(n, int(0.01 * sr))
        x[:nk] += 0.25 * vel * svf(white(nk, rng), 3000.0, 1.0, "bp") * np.exp(-t[:nk] / 0.0025)
        x = x + 0.2 * svf(x.astype(F32), 420.0, 2.0, "bp")
        return _finish(x, vel, rel_fade=512)
    return inst


def marimba(decay: float = 0.45, sr=SR):
    """Wooden marimba: fundamental + 4th/10th modes with fast decay, mallet knock. Mono."""
    def inst(freq, dur, vel):
        n = int(max(dur, decay * 2.5) * sr)
        t = np.arange(n) / sr
        rng = np.random.default_rng(_seed(freq, 9))
        td = decay * (400.0 / freq) ** 0.3
        x = np.sin(TAU * freq * t) * np.exp(-t / td)
        x += 0.3 * vel * np.sin(TAU * freq * 3.99 * t) * np.exp(-t / (td * 0.25))
        x += 0.08 * vel * np.sin(TAU * freq * 9.9 * t) * np.exp(-t / (td * 0.08))
        nk = min(n, int(0.008 * sr))
        x[:nk] += 0.3 * vel * svf(white(nk, rng), 1800.0, 1.0, "bp") * np.exp(-t[:nk] / 0.002)
        return _finish(x, vel, rel_fade=512)
    return inst


def pluck_lead(bright: float = 0.7, decay: float = 0.996, body: float = 0.3, sr=SR):
    """Karplus-Strong plucked melody voice (harp / kora / guitar-like) with a little body. Mono."""
    def inst(freq, dur, vel):
        n = int(max(dur + 0.4, 1.0) * sr)
        rng = np.random.default_rng(_seed(freq, 13))
        x = karplus(freq, n, decay, bright * (0.6 + 0.4 * vel), rng)
        x = x + body * svf(x, float(min(freq * 3, 3000)), 1.2, "bp")
        t = np.arange(n) / sr
        g = max(dur, 0.1)
        x = np.where(t < g + 0.25, x, x * np.exp(-(t - g - 0.25) / 0.15))
        return _finish(hp(x.astype(F32), 120.0), vel, rel_fade=512)
    return inst


def synth_lead(detune_cents: float = 12.0, cutoff: float = 3200.0, res: float = 0.25, attack: float = 0.01,
               release: float = 0.25, vibrato: float = 0.15, sr=SR):
    """Big but round peak-time lead: 3 detuned saws + square sub-octave, ladder low-pass with a
    small envelope, delayed vibrato. Stereo."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        vib = 2 ** (vibrato * np.sin(TAU * 5.4 * t) * np.clip((t - 0.25) / 0.3, 0, 1) / 12)
        f = freq * vib
        rng = np.random.default_rng(_seed(freq, 17))
        voices = []
        for c in (-detune_cents, 0.0, detune_cents):
            voices.append(saw(f * 2 ** (c / 1200), n, rng.random()))
        sub = square(f * 0.5, n, 0.0, 0.5) * 0.3
        L = voices[0] * 0.8 + voices[1] * 0.6 + sub
        R = voices[2] * 0.8 + voices[1] * 0.6 + sub
        cut = cutoff * (0.6 + 0.4 * vel) * (1 + 1.2 * np.exp(-t / 0.08))
        L = ladder(L, cut, res, 1.4)
        R = ladder(R, cut * 1.02, res, 1.4)
        env = adsr(n, gate, attack, 0.3, 0.8, release, sr)
        return _finish(np.stack([L, R], axis=1) * env[:, None], vel, rel_fade=256)
    return inst


# ============================================================================ voices
def chant(vowel: str = "o", vowel_to: str | None = "a", shift: float = 1.0, voices: int = 2,
          detune_cents: float = 9.0, vibrato: float = 0.35, breath: float = 0.1, attack: float = 0.03,
          release: float = 0.2, scoop: float = -1.5, sr=SR):
    """Chant-like vowel voice (glottal saw + breath through a morphing formant bank), doubled
    with slightly detuned/panned copies for an ensemble feel. Stereo. Not words — vowels only."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        rng = np.random.default_rng(_seed(freq, 23))
        vib = vibrato * np.sin(TAU * 5.1 * t + rng.random() * TAU) * (1 - np.exp(-t / 0.3))
        out = np.zeros((n, 2), dtype=F32)
        for v in range(voices):
            pos = 0.0 if voices == 1 else (v / (voices - 1)) * 2 - 1
            c = pos * detune_cents / 100.0
            f = freq * 2 ** ((scoop * np.exp(-t / 0.05) + vib + c) / 12)
            src = saw(f, n, rng.random()) * 0.85 + breath * white(n, rng)
            y = formant_filter(src, vowel, vowel_to, shift * (1 + 0.02 * pos), sr)
            out += pan(y, pos * 0.6)
        out = hp(out, 180.0)
        env = adsr(n, gate, attack, 0.3, 0.85, release, sr, curve=3.0)
        return _finish(out * env[:, None], vel, rel_fade=512)
    return inst


# ============================================================================ basses
def deep_bass(cutoff: float = 260.0, sub: float = 0.85, drive: float = 1.3, attack: float = 0.006,
              release: float = 0.06, sustain: float = 0.8, decay: float = 0.35, sr=SR):
    """Round deep-house bass: sine fundamental + low-passed saw for warmth + soft drive. Mono."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        s = sine(freq, n)
        w = ladder(saw(freq, n), cutoff * (1 + 1.2 * vel * np.exp(-t / 0.06)), 0.15, 1.0)
        x = sub * s + (1 - sub * 0.5) * w
        x = np.tanh(x * drive) / math.tanh(drive)
        env = adsr(n, gate, attack, decay, sustain, release, sr)
        return _finish(x * env, vel)
    return inst


def talking_bass(cutoff: float = 260.0, f1: tuple = (240.0, 900.0), f2: tuple = (700.0, 2100.0),
                 wah_time: float = 0.11, sub: float = 0.8, drive: float = 2.0, release: float = 0.03,
                 sub_oct: bool = False, sr=SR):
    """Talking / wah bass: saw+pulse through two moving formant band-passes that open and close
    per note ('yow'), a low-passed body and a clean sine sub (``sub_oct``: one octave down, for keys
    whose bass root sits above ~70 Hz). Mono."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        osc = saw(freq, n) * 0.7 + square(freq * 1.003, n, 0.2, 0.4) * 0.3
        shape = (1 - np.exp(-t / 0.018)) * np.exp(-t / (wah_time * (0.7 + 0.6 * vel)))
        shape = shape / (shape.max() + 1e-9)
        fa = f1[0] + (f1[1] - f1[0]) * vel * shape
        fb = f2[0] + (f2[1] - f2[0]) * vel * shape
        y = svf(osc, fa, 3.2, "bp") * 1.2 + svf(osc, fb, 4.0, "bp") * 0.7
        y = y + ladder(osc, cutoff, 0.2, 1.0) * 0.5
        y = np.tanh(y * drive) / math.tanh(drive)
        y = y + sub * sine(freq * (0.5 if sub_oct else 1.0), n)
        env = adsr(n, gate, 0.003, 0.25, 0.75, release, sr)
        return _finish(y * env, vel)
    return inst


def log_drum(decay: float = 0.5, knock: float = 0.5, bend: float = 4.0, drive: float = 2.0,
             body: float = 0.45, slide_ms: float = 70.0, tone_hz: float = 1100.0, sr=SR):
    """Amapiano log drum voice for :class:`SlideNotes`: ``inst(freq, dur, vel, from_hz=None)``.

    Sine body with a fast downward pitch 'bend' on the attack, hollow 2nd/3rd harmonics, a woody
    band-passed knock, saturation (so it reads on small speakers) and — when ``from_hz`` is given —
    an exponential slide from the previous note's pitch."""
    def inst(freq, dur, vel, from_hz=None):
        n = int((min(dur, decay * 2.2) + 0.08) * sr)
        t = np.arange(n) / sr
        semis = bend * np.exp(-t / 0.016)
        if from_hz:
            k = math.log(from_hz / freq) / math.log(2) * 12
            semis = semis * 0.25 + k * np.exp(-t / (slide_ms / 1000 / 2.5))
        f = freq * 2 ** (semis / 12)
        ph = TAU * np.cumsum(f) / sr
        x = np.sin(ph) + body * np.sin(2 * ph + 0.4) * np.exp(-t / 0.18) + 0.18 * np.sin(3 * ph) * np.exp(-t / 0.08)
        amp = np.exp(-t / (decay / 2.6)) * np.clip(t / 0.0015, 0, 1)
        g = int(min(dur, decay * 2.2) * sr)
        if g < n:
            amp[g:] *= np.exp(-(t[g:] - t[g]) / 0.02)
        x = x * amp
        nk = min(n, int(0.02 * sr))
        rng = np.random.default_rng(_seed(freq, 41))
        x[:nk] += knock * vel * svf(white(nk, rng), tone_hz, 2.2, "bp") * np.exp(-t[:nk] / 0.004) * 2.5
        x = np.tanh(x * drive) / math.tanh(drive)
        x = lp(hp(x.astype(F32), 28.0), 4000.0)
        return _finish(x, vel, rel_fade=256)
    return inst


class SlideNotes(Notes):
    """Monophonic-ish notes layer whose instrument takes ``from_hz``: a note carrying the flag ``"s"``
    (5th tuple element) slides in from the previous note's pitch (amapiano log drum glides)."""

    def render_dry(self, song, a, b):
        n = b - a
        buf = np.zeros((n, 2), dtype=F32)
        evs = sorted(self.note_events(song, a, b), key=lambda e: e[0])
        prev = None
        hit = False
        for pos, length, midi, vel, flags in evs:
            frm = prev if (prev is not None and "s" in (flags or "")) else None
            prev = midi
            if pos >= b:
                continue
            key = (round(float(midi), 3), int(length // 64), round(vel * 16) / 16,
                   None if frm is None else round(float(frm), 3))
            x = self._cache.get(key)
            if x is None:
                fh = float(midi_to_hz(frm)) if frm is not None else None
                x = as_stereo(self.instrument(float(midi_to_hz(midi)), length / song.sr, key[2], fh))
                self._cache[key] = x
            if pos + x.shape[0] <= a:
                continue
            mix_into(buf, x, pos - a)
            hit = True
        return buf if hit else None


# ============================================================================ percussion one-shots
def clave(freq: float = 2500.0, decay: float = 0.03, rng=None, sr=SR):
    n = int((decay * 5 + 0.01) * sr)
    t = np.arange(n) / sr
    x = np.sin(TAU * freq * t) * np.exp(-t / decay) + 0.25 * np.sin(TAU * freq * 1.6 * t) * np.exp(-t / (decay * 0.4))
    return normalize(fade(hp(x.astype(F32), 600.0), 0, int(0.004 * sr)))


def woodblock(freq: float = 850.0, decay: float = 0.04, rng=None, sr=SR):
    rng = rng if rng is not None else np.random.default_rng(1)
    n = int((decay * 5 + 0.01) * sr)
    t = np.arange(n) / sr
    x = (np.sin(TAU * freq * t) * np.exp(-t / decay) + 0.45 * np.sin(TAU * freq * 2.57 * t) * np.exp(-t / (decay * 0.4))
         + 0.2 * np.sin(TAU * freq * 4.3 * t) * np.exp(-t / (decay * 0.2)))
    nk = int(0.004 * sr)
    x[:nk] += 0.4 * svf(white(nk, rng), freq * 3, 1.0, "bp") * np.exp(-t[:nk] / 0.001)
    return normalize(fade(hp(x.astype(F32), 300.0), 0, int(0.005 * sr)))


def djembe(stroke: str = "tone", pitch: float | None = None, rng=None, sr=SR):
    """Djembe strokes: ``bass`` (deep centre), ``tone`` (open edge), ``slap`` (sharp, bright)."""
    rng = rng if rng is not None else np.random.default_rng(2)
    if stroke == "bass":
        p = pitch or 78.0
        n = int(0.45 * sr)
        t = np.arange(n) / sr
        f = p * (1 + 0.5 * np.exp(-t / 0.02))
        x = np.sin(TAU * np.cumsum(f) / sr) * np.exp(-t / 0.09)
        x += 0.2 * svf(white(n, rng), 500.0, 1.0, "bp") * np.exp(-t / 0.01)
        return normalize(fade(hp(x.astype(F32), 35.0), 0, int(0.02 * sr)))
    p = pitch or (330.0 if stroke == "tone" else 420.0)
    n = int(0.3 * sr)
    t = np.arange(n) / sr
    f = p * (1 + 0.12 * np.exp(-t / 0.01))
    ph = TAU * np.cumsum(f) / sr
    if stroke == "tone":
        x = np.sin(ph) * np.exp(-t / 0.07) + 0.4 * np.sin(1.58 * ph) * np.exp(-t / 0.04) + 0.2 * np.sin(2.3 * ph) * np.exp(-t / 0.025)
        x += 0.3 * svf(white(n, rng), 2500.0, 1.0, "bp") * np.exp(-t / 0.006)
    else:
        x = 0.5 * np.sin(ph) * np.exp(-t / 0.03) + 0.4 * np.sin(2.7 * ph) * np.exp(-t / 0.02)
        x += 1.1 * svf(white(n, rng), 3200.0, 0.8, "bp") * np.exp(-t / 0.012)
    return normalize(fade(hp(x.astype(F32), 120.0), 0, int(0.01 * sr)))


def talking_drum(freq: float = 160.0, bend: float = 5.0, decay: float = 0.28, rng=None, sr=SR):
    """Talking drum: pitched membrane whose pitch rises after the hit (squeezed) and falls back."""
    rng = rng if rng is not None else np.random.default_rng(3)
    n = int((decay * 2.5) * sr)
    t = np.arange(n) / sr
    semis = bend * (1 - np.exp(-t / 0.035)) * np.exp(-t / (decay * 1.5))
    f = freq * 2 ** (semis / 12) * (1 + 0.15 * np.exp(-t / 0.008))
    ph = TAU * np.cumsum(f) / sr
    x = np.sin(ph) * np.exp(-t / (decay / 2.5)) + 0.3 * np.sin(1.5 * ph) * np.exp(-t / (decay / 4))
    x += 0.25 * svf(white(n, rng), 1800.0, 1.0, "bp") * np.exp(-t / 0.006)
    return normalize(fade(hp(x.astype(F32), 60.0), 0, int(0.02 * sr)))


def shekere(length: float = 0.12, tone: float = 4200.0, rng=None, sr=SR):
    """Shekere / caxixi: grainy, lower-pitched shaker with a beaded rattle."""
    rng = rng if rng is not None else np.random.default_rng(4)
    n = int(length * 1.8 * sr)
    t = np.arange(n) / sr
    a = length * 0.2
    env = np.where(t < a, (t / a) ** 1.2, np.exp(-(t - a) / (length * 0.4)))
    beads = (rng.random(n) < 0.05).astype(np.float64) * rng.uniform(0.5, 1.0, n)
    beads = svf(beads.astype(F32), tone * 1.4, 2.0, "bp")
    nz = svf(white(n, rng), tone, 1.0, "bp")
    x = (nz + 0.8 * beads) * env
    return normalize(lp(hp(x.astype(F32), 2200.0), 12000.0))


def pha(tone: float = 950.0, body: float = 230.0, decay: float = 0.09, rng=None, sr=SR):
    """Amapiano 'pha' hit: mid-heavy, short snare/clap hybrid (feed it a room/plate reverb)."""
    rng = rng if rng is not None else np.random.default_rng(5)
    n = int((decay * 4 + 0.02) * sr)
    t = np.arange(n) / sr
    nz = white(n, rng)
    env = np.exp(-t / (decay / 2.2))
    x = svf(nz, tone, 1.1, "bp") * env * 1.4 + 0.5 * svf(nz, tone * 2.6, 1.5, "bp") * np.exp(-t / 0.015)
    x += 0.55 * np.sin(TAU * body * t * (1 + 0.3 * np.exp(-t / 0.01))) * np.exp(-t / 0.03)
    return normalize(fade(hp(x.astype(F32), 180.0), 0, int(0.01 * sr)))


def dusty_rim(tone_hz: float = 1600.0, rng=None, sr=SR):
    """Lo-fi rimshot: core rim + a little bit-reduced grit, rolled-off top (deep house 'dust')."""
    x = drums.rimshot(tone_hz, rng=rng, sr=sr)
    x = lp(fx.bitcrush(x, 12, 2), 6500.0)
    return normalize(fade(x, 0, int(0.004 * sr)))


def soft_clap(tone_hz: float = 1150.0, tail: float = 0.22, rng=None, sr=SR):
    """Softer, roomier clap (rounded top) for deep / afro house."""
    x = drums.clap(1.15, tone_hz, tail, 4, rng=rng, sr=sr)
    return normalize(lp(x, 7500.0))


# ============================================================================ arrangement helpers
def ramp_into(song, kind, bars, lo, hi):
    pts = []
    for s in song.sections:
        if s.kind == kind:
            pts += [(s.start_bar - bars, lo), (s.start_bar, hi)]
    return pts or [(0, 0.0)]


def snare_roll(c, bars=4, rolls=("x...x...x...x...", "x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx", "rrrrrrrrrrrrrrrr")):
    """Classic build roll for the last ``bars`` bars of a breakdown (None elsewhere)."""
    if c.kind != "breakdown" or c.bars_left > bars:
        return None
    seq = list(rolls)[-bars:]
    return seq[bars - c.bars_left]


def transitions(song, rng, crash=None, crash_db=-9.0, impact_db=-9.0, riser_db=-9.5, riser_kind="both",
                impact=True, downlifter=True, reverse=True, sweep_groove=True, drop_crash_every=16,
                riser_bars=8, bus="fx", sends=None):
    """Standard DJ-friendly transition FX: crash on section starts (and every 16 bars in drops),
    riser ending exactly on each drop, downlifter at breakdowns, impact on drop downbeats, reverse
    cymbal + noise sweep into the groove. Returns the Audio layer."""
    fxl = song.audio("fx", bus=bus, sends=sends or {"hall": 0.12})
    crash = crash if crash is not None else drums.crash(decay=float(rng.uniform(1.8, 2.6)), rng=rng)
    bs = song.grid.bar_sec
    groove = song.mix_in_bar
    for s in song.sections:
        if s.kind in ("groove", "drop", "outro"):
            fxl.add(crash, s.start_bar, gain_db=crash_db)
        if s.kind == "drop":
            if drop_crash_every:
                for b in range(s.start_bar + drop_crash_every, s.end_bar, drop_crash_every):
                    fxl.add(crash, b, gain_db=crash_db - 4)
            if impact:
                fxl.add(fx.impact(2.5, rng=rng), s.start_bar, gain_db=impact_db)
        if s.kind == "breakdown":
            nb = min(riser_bars, s.bars)
            if riser_kind:
                fxl.add(fx.riser(bs * nb, riser_kind, rng=rng), s.end_bar, align="end", gain_db=riser_db)
            if downlifter:
                fxl.add(fx.downlifter(bs * 2, rng=rng), s.start_bar, gain_db=riser_db - 3)
            if reverse:
                fxl.add(fx.reverse_cymbal(bs, rng=rng), s.end_bar, align="end", gain_db=riser_db - 1)
    if groove is not None and sweep_groove:
        fxl.add(fx.reverse_cymbal(bs, rng=rng), groove, align="end", gain_db=crash_db - 1)
        fxl.add(fx.noise_sweep(bs * 8, up=True, rng=rng), groove, align="end", gain_db=crash_db - 9)
    return fxl


def phrase_fill(c, fill, every=8, kinds=("groove", "drop", "intro", "outro")):
    """``fill`` on the last bar of each ``every``-bar phrase in the given section kinds, else None."""
    if c.kind in kinds and c.every(every):
        return fill
    return None


__all__ = [n for n in dir() if not n.startswith("_")]
