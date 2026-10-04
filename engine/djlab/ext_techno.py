"""Techno-family toolkit shared by the ``techno``, ``melodic_techno``, ``hypnotic_techno`` and
``hard_techno`` recipes.

It only *uses* the frozen engine core (dsp / synth / drums / fx / mixer) and adds:

* **stereo one-shots** - two independently seeded renders of a hat/clap/perc blended to a chosen L/R
  correlation, so tops give the mix real width while kick and sub stay mono;
* **instruments** - supersaw pluck, formant choir, anthem lead, glass lead, hoover, rave stab, stereo
  dub chord, pitched noise drone, click/tick percussion;
* **generators** - chord progressions, arpeggios (incl. 3-against-4), 8-bar hooks built from motif
  cells, rolling basslines, polymetric step helpers;
* **transitions** - accelerating pitched snare rolls, pitched noise risers, wide/long returns.

Everything is deterministic: randomness only comes from the ``rng`` passed in (or from seeds derived
from note frequency, like the core instruments).
"""
from __future__ import annotations

import math

import numpy as np

from . import SR
from .dsp import F32, as_mono, as_stereo, fade, hp, ladder, lp, normalize, saw, sine, square, svf, svf24, triangle
from .mixer import Return
from .synth import adsr, chorus, fm, formant_filter, pink, supersaw, white
from .theory import voice_lead

TAU = 2 * math.pi


# ============================================================================ small helpers
def child(rng) -> np.random.Generator:
    """Independent child generator drawn from ``rng`` (keeps the parent sequence deterministic)."""
    return np.random.default_rng(int(rng.integers(1 << 31)))


def _n(dur, release, sr=SR):
    gate = max(16, int(dur * sr))
    return gate, gate + int(release * sr)


def _finish(x, vel, rel_fade=256):
    x = fade(np.asarray(x, dtype=F32), 16, rel_fade)
    return normalize(x, 0.8 * float(vel))


def _note_rng(freq, salt=0):
    return np.random.default_rng((int(freq * 1000) * 31 + salt) % (2 ** 31))


def kick_tune(key, lo=41.0, hi=58.0):
    """Kick body frequency in ``[lo, hi]`` Hz: the key root if possible, else its fifth, else fourth."""
    for semis in (0, 7, 5):
        for octv in (0, 1, 2):
            f = 440.0 * 2 ** ((key.root(octv) + semis - 69) / 12)
            if lo <= f <= hi:
                return float(f)
    return 50.0


def pick(rng, seq):
    return seq[int(rng.integers(len(seq)))]


# ============================================================================ stereo one-shots
def decorrelate(a, b, corr=0.5):
    """Blend two mono renders into stereo with L/R correlation ≈ ``corr`` (1 = mono)."""
    a, b = as_mono(a), as_mono(b)
    n = max(a.shape[0], b.shape[0])
    a = np.pad(a, (0, n - a.shape[0]))
    b = np.pad(b, (0, n - b.shape[0]))
    th = 0.5 * math.asin(float(np.clip(corr, -1.0, 1.0)))
    c, s = math.cos(th), math.sin(th)
    st = np.stack([c * a + s * b, c * b + s * a], axis=1)
    return normalize(st.astype(F32))


def stereo_hit(fn, rng=None, corr=0.5, **kw):
    """Stereo one-shot from two independently seeded renders of ``fn(rng=..., **kw)``."""
    rng = rng if rng is not None else np.random.default_rng(0)
    return decorrelate(fn(rng=child(rng), **kw), fn(rng=child(rng), **kw), corr)


def stereo_variants(fn, n=4, rng=None, jitter=None, corr=0.5, **kw):
    """Like :func:`djlab.drums.variants` but every round-robin variant is a decorrelated stereo hit."""
    rng = rng if rng is not None else np.random.default_rng(0)
    jitter = jitter or {}
    out = []
    for _ in range(n):
        kk = dict(kw)
        for p, amt in jitter.items():
            if kk.get(p) is not None:
                kk[p] = kk[p] * (1 + amt * rng.uniform(-1, 1))
        out.append(stereo_hit(fn, child(rng), corr, **kk))
    return out


def ms_spread(x, ms=11.0, amount=0.35, hp_hz=250.0, sr=SR):
    """Mono-compatible widening: side = high-passed, delayed copy of the mid. The side cancels
    exactly in a mono sum (no comb filtering), unlike a plain Haas delay."""
    m = as_mono(x)
    d = int(ms * 1e-3 * sr)
    sd = np.concatenate([np.zeros(d, dtype=F32), m[:-d] if d else m])
    sd = hp(sd, hp_hz, 2, sr) * F32(amount)
    return np.stack([m + sd, m - sd], axis=1).astype(F32)


def stereo_detune(inst_fn, cents=7.0, side=0.3):
    """Wrap a mono instrument: mid = the note, side = a slightly detuned copy (mono-compatible)."""
    k = 2 ** (cents / 1200.0)

    def inst(freq, dur, vel):
        m = as_mono(inst_fn(freq, dur, vel))
        d = as_mono(inst_fn(freq * k, dur, vel))
        n = min(m.shape[0], d.shape[0])
        st = np.stack([m[:n] + side * d[:n], m[:n] - side * d[:n]], axis=1)
        return normalize(st.astype(F32), 0.8 * float(vel))
    return inst


def click(freq=4200.0, length=0.012, tone=0.5, rng=None, sr=SR):
    """Tiny 'clicky' minimal-techno tick: band-passed impulse + ringing sine, a few ms long."""
    rng = rng if rng is not None else np.random.default_rng(0)
    n = int((length * 3 + 0.004) * sr)
    t = np.arange(n) / sr
    nz = svf(white(n, rng), freq, 2.5, "bp") * np.exp(-t / (length * 0.35))
    ring = np.sin(TAU * freq * 0.5 * t) * np.exp(-t / (length * 0.6)) * tone
    x = hp(nz * 1.5 + ring, 800.0)
    return normalize(fade(x.astype(F32), 0, int(0.002 * sr)))


def distorted(x, drive=4.0, tone_hz=7000.0, sr=SR):
    """Level-compensated tanh distortion with a post low-pass (keeps fizz/aliasing down)."""
    y = np.tanh(np.asarray(x, dtype=F32) * drive) / math.tanh(drive)
    if tone_hz:
        y = lp(y, tone_hz, 2, sr)
    return normalize(y.astype(F32))


def pitch_shift(x, semis):
    """Repitch a one-shot by resampling (duration follows pitch)."""
    x = np.asarray(x, dtype=F32)
    r = 2 ** (semis / 12.0)
    m = max(16, int(x.shape[0] / r))
    src = np.arange(m) * r
    if x.ndim == 1:
        return np.interp(src, np.arange(x.shape[0]), x).astype(F32)
    return np.stack([np.interp(src, np.arange(x.shape[0]), x[:, c]) for c in range(x.shape[1])], axis=1).astype(F32)


# ============================================================================ instruments
def supersaw_pluck(cutoff=500.0, env_amt=6000.0, decay=0.16, sustain=0.18, release=0.22, detune=0.22,
                   mix=0.55, width=0.55, res=0.25, body=0.15, sr=SR):
    """Wide supersaw pluck for melodic-techno arpeggios (stereo, filter-enveloped)."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        x = supersaw(freq, n, detune=detune, mix=mix, spread=width, rng=_note_rng(freq, 1))
        if body:
            x = x + as_stereo(square(freq, n, 0.13, 0.5)) * body
        cut = np.minimum(cutoff + env_amt * vel * np.exp(-t / decay), 18000.0)
        x = svf(x, cut, 0.75 + res, "lp")
        env = adsr(n, gate, 0.0015, decay * 3.0, sustain, release, sr, curve=4.0)
        return _finish(x * env[:, None], vel)
    return inst


def glass_pluck(ratio=2.0, index=2.2, decay=0.5, release=0.6, shimmer=0.25, side=0.35, sr=SR):
    """Glassy FM/triangle pluck (Tale Of Us / cinematic arps & leads). Mid-dominant stereo: a slightly
    detuned copy is added as the side signal (``side`` ≈ its level), so it stays mono-compatible."""
    def inst(freq, dur, vel):
        gate, n = _n(max(dur, 0.12), release, sr)
        t = np.arange(n) / sr
        ienv = np.exp(-t / (decay * 0.35))
        m = fm(freq, n, ratio, index * vel, ienv) * 0.7 + triangle(freq, n) * 0.4
        d = fm(freq * 1.004, n, ratio, index * vel, ienv) * 0.7 + triangle(freq * 0.996, n, 0.3) * 0.4
        if shimmer:
            m = m + shimmer * sine(freq * 4.0, n) * np.exp(-t / (decay * 0.2))
            d = d + shimmer * sine(freq * 4.01, n, 0.25) * np.exp(-t / (decay * 0.2))
        x = np.stack([m + side * d, m - side * d], axis=1)
        env = np.exp(-t / decay) * 0.75 + 0.25
        env = env * adsr(n, gate, 0.002, 0.1, 1.0, release, sr, curve=4.0)
        return _finish(x * env[:, None], vel, rel_fade=512)
    return inst


def choir(vowel="a", vowel_to="o", shift=1.0, voices=3, vibrato=0.12, breath=0.06, attack=0.5,
          release=1.2, bright=5500.0, corr=0.5, sr=SR):
    """Choir-like vowel pad: per channel ``voices`` detuned glottal saws with independent vibrato through
    a formant bank (slowly morphing ``vowel`` → ``vowel_to``), breath noise, chorus. Stereo."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        rng = _note_rng(freq, 7)
        chans = []
        for _c in range(2):
            src = np.zeros(n, dtype=np.float64)
            for v in range(voices):
                det = (v - (voices - 1) / 2) * 0.09 + rng.uniform(-0.03, 0.03)
                vib = vibrato * np.sin(TAU * rng.uniform(4.4, 5.4) * t + rng.uniform(0, TAU)) * (1 - np.exp(-t / 0.7))
                f = freq * 2 ** ((det + vib) / 12)
                src += saw(f, n, rng.random())
            src = src / voices + breath * white(n, rng)
            chans.append(formant_filter(src.astype(F32), vowel, vowel_to, shift, sr))
        x = decorrelate(chans[0], chans[1], corr)
        x = lp(hp(x, 140.0, 2), bright, 2)
        x = chorus(x, 0.35, 2.5, 14.0, 0.25)
        env = adsr(n, gate, attack, 0.6, 0.9, release, sr, curve=3.0)
        return _finish(x * env[:, None], vel, rel_fade=2048)
    return inst


def anthem_lead(detune=0.2, bright=0.8, vib=0.14, attack=0.006, release=0.4, sustain=0.72, scoop=0.6,
                octave_up=0.2, sub=0.25, spread=0.5, sr=SR):
    """Big melodic-techno lead: supersaw + octave shimmer + square sub-octave, 24 dB LP with a
    pluck-to-sustain envelope, pitch scoop into each note and delayed vibrato. Stereo."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        semis = vib * np.sin(TAU * 5.2 * t) * np.clip((t - 0.2) / 0.3, 0, 1) - scoop * np.exp(-t / 0.022)
        f = freq * 2 ** (semis / 12)
        x = supersaw(f, n, detune=detune, mix=0.5, spread=spread, rng=_note_rng(freq, 3))
        x = hp(x, freq * 0.7, 1)
        if octave_up:
            x = x + as_stereo(saw(f * 2, n, 0.31)) * octave_up
        if sub:
            x = x + as_stereo(square(f * 0.5, n, 0.0, 0.5)) * sub
        cut = (700 + 5200 * bright * vel) * (0.5 + 0.5 * np.exp(-t / 0.3)) + 400
        x = svf24(x, cut, 0.85, "lp")
        env = adsr(n, gate, attack, 0.35, sustain, release, sr, curve=4.0)
        return _finish(x * env[:, None], vel, rel_fade=512)
    return inst


def soft_lead(vib=0.18, release=0.5, bright=0.4, sr=SR):
    """Mellow, breathy triangle/sine lead with a touch of saw (spacey Tale-Of-Us style)."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        semis = vib * np.sin(TAU * 4.8 * t) * np.clip((t - 0.25) / 0.4, 0, 1) - 0.4 * np.exp(-t / 0.03)
        f = freq * 2 ** (semis / 12)
        l = triangle(f, n) + 0.35 * sine(f * 2, n) + bright * 0.3 * saw(f, n, 0.1)
        r = triangle(f * 1.003, n, 0.2) + 0.35 * sine(f * 2.006, n, 0.1) + bright * 0.3 * saw(f * 0.997, n, 0.6)
        x = lp(np.stack([l * 0.8 + r * 0.2, r * 0.8 + l * 0.2], axis=1), 2500 + 3000 * bright, 2)
        x = x + as_stereo(white(n, _note_rng(freq, 9)) * 0.03)
        env = adsr(n, gate, 0.02, 0.4, 0.8, release, sr, curve=3.5)
        return _finish(x * env[:, None], vel, rel_fade=512)
    return inst


def warm_pad(attack=1.2, release=2.0, cutoff=2200.0, detune=0.28, warmth=0.5, organ=0.0, spread=0.65, sr=SR):
    """Lush stereo pad: supersaw + triangle (+ optional organ-like octave sines) with slow filter drift."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        x = supersaw(freq, n, detune=detune, mix=0.6, spread=spread, rng=_note_rng(freq, 5))
        x = x * (1 - warmth * 0.5) + as_stereo(triangle(freq, n)) * warmth * 0.6
        if organ:
            x = x + organ * np.stack([sine(freq * 2, n) + 0.5 * sine(freq * 3, n),
                                      sine(freq * 2.003, n, 0.2) + 0.5 * sine(freq * 3.004, n, 0.4)], axis=1)
        cut = cutoff * (1 + 0.3 * np.sin(TAU * 0.11 * t + freq))
        x = svf(x, cut, 0.8, "lp")
        env = adsr(n, gate, attack, 0.8, 0.85, release, sr, curve=3.0)
        return _finish(x * env[:, None], vel, rel_fade=2048)
    return inst


def dub_chord_st(cutoff=650.0, env_amt=1300.0, decay=0.22, detune_cents=5.0, amp_decay=0.3, side=0.35, sr=SR):
    """Stereo dub-techno chord voice: saw+square through a ladder LP, short; a slightly detuned copy is
    the side signal (mono-compatible width)."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, 0.06, sr)
        t = np.arange(n) / sr
        d = 2 ** (detune_cents / 1200)
        cut = cutoff + env_amt * vel * np.exp(-t / decay)
        sig = []
        for c, k in enumerate((1.0, d)):
            x = saw(freq * k, n, 0.17 * c) * 0.6 + square(freq * k * 1.002, n, 0.3 + 0.2 * c, 0.5) * 0.4
            sig.append(ladder(x, cut, 0.45, 1.2))
        st = np.stack([sig[0] + side * sig[1], sig[0] - side * sig[1]], axis=1)
        env = adsr(n, gate, 0.003, amp_decay, 0.0, 0.06, sr, curve=3.0)
        return _finish(st * env[:, None], vel)
    return inst


def hoover(detune_cents=22.0, scoop=7.0, dive=12.0, pw_rate=3.5, cutoff=3800.0, drive=1.8, release=0.25,
           sub=0.45, sr=SR):
    """'Hoover' rave lead/stab: detuned PWM saws + sub-octave saw, pitch scoop up into the note and a
    pitch dive on release, heavy chorus, saturation. Stereo."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        semis = -scoop * np.exp(-t / 0.035)
        if gate < n:
            tr = t[gate:] - t[gate]
            semis[gate:] -= dive * (1 - np.exp(-tr / max(release * 0.45, 1e-3)))
        f = freq * 2 ** (semis / 12)
        d = 2 ** (detune_cents / 1200)
        pw = 0.5 + 0.38 * np.sin(TAU * pw_rate * t)
        x = (saw(f * d, n, 0.1) + saw(f / d, n, 0.6) + 0.8 * square(f, n, 0.3, pw) + sub * saw(f * 0.5, n, 0.8))
        x = svf(x / 3.0, cutoff, 0.9, "lp")
        x = np.tanh(x * drive) / math.tanh(drive)
        x = chorus(x.astype(F32), 0.9, 4.5, 11.0, 0.6)
        x = hp(x, 70.0, 2)
        env = adsr(n, gate, 0.008, 0.25, 0.85, release, sr, curve=4.0)
        return _finish(x * env[:, None], vel, rel_fade=256)
    return inst


def rave_stab(cutoff=700.0, env_amt=7000.0, decay=0.09, drive=2.5, detune_cents=14.0, amp_decay=0.22, sr=SR):
    """Bright 90s rave chord stab: 3 detuned saws, snappy resonant LP envelope, distortion. Stereo."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, 0.05, sr)
        t = np.arange(n) / sr
        d = 2 ** (detune_cents / 1200)
        cut = np.minimum(cutoff + env_amt * vel * np.exp(-t / decay), 16000)
        chans = []
        for c, k in enumerate((d, 1 / d)):
            x = saw(freq * k, n, 0.2 * c) + saw(freq, n, 0.5 + 0.1 * c) * 0.7 + square(freq * 2 * k, n, 0.0, 0.5) * 0.25
            x = svf(x, cut, 2.2, "lp")
            chans.append(np.tanh(x * drive) / math.tanh(drive))
        env = adsr(n, gate, 0.001, amp_decay, 0.0, 0.05, sr, curve=4.0)
        return _finish(hp(np.stack(chans, axis=1), 120.0, 2) * env[:, None], vel)
    return inst


def noise_drone(q=9.0, harmonics=(1, 2, 3, 5), drift=0.08, attack=2.0, release=2.5, air=0.15, corr=0.6, sr=SR):
    """Pitched 'wind/tunnel' drone: pink noise through resonant band-passes at the note's harmonics
    with slow drift; decorrelated L/R. Use long notes."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        rng = _note_rng(freq, 11)
        chans = []
        for c in range(2):
            nz = pink(n, rng)
            y = np.zeros(n, dtype=np.float64)
            for h, k in enumerate(harmonics):
                f = freq * k * (1 + drift * 0.05 * np.sin(TAU * (0.07 + 0.03 * h) * t + c + h))
                y += svf(nz, f, q, "bp") / (1 + h * 0.6)
            y += air * hp(nz, 5000.0, 2)
            chans.append(y)
        x = decorrelate(chans[0], chans[1], corr)
        env = adsr(n, gate, attack, 1.0, 0.9, release, sr, curve=2.5)
        return _finish(x * env[:, None], vel, rel_fade=4096)
    return inst


def screech(sr=SR):
    """Settings for a hard-techno 'screech' MonoSynth (use with ``instruments.MonoSynth``)."""
    return dict(wave="saw", cutoff=900.0, res=0.9, env_mod=3.2, decay=0.12, accent=0.9, glide_ms=45.0,
                drive=4.0, dist=0.75)


# ============================================================================ harmony / melody
def chords_for(key, degs, octave=3, size=4, center=None, add9=False):
    """Voice-led diatonic chords for scale degrees ``degs`` (lists of MIDI)."""
    center = center if center is not None else key.root(octave + 1)
    out, prev = [], None
    for d in degs:
        ch = key.chord(d, octave, size)
        if add9:
            ch = ch + [key.degree(d + 8, octave)]
        ch = voice_lead(prev, ch, center=center)
        out.append(ch)
        prev = ch
    return out


ARP_PATTERNS = ("up", "updown", "down", "pedal", "three", "five", "converge", "octave")


def arp_seq(chord, pattern="up", octaves=2):
    """Note cycle for an arpeggio over ``chord`` (MIDI list)."""
    pool = sorted(chord)
    ext = [p + 12 * o for o in range(octaves) for p in pool]
    if pattern == "up":
        return ext
    if pattern == "down":
        return ext[::-1]
    if pattern == "updown":
        return ext + ext[-2:0:-1]
    if pattern == "pedal":
        root = ext[0]
        out = []
        for p in ext[1:]:
            out += [root, p]
        return out
    if pattern == "three":  # 3-note cell → 3-against-4 polyrhythm over 16ths
        return [ext[0], ext[2], ext[1]] if len(ext) > 2 else ext
    if pattern == "five":  # 5-note cell → 5-against-16
        return [ext[0], ext[1], ext[2], ext[min(3, len(ext) - 1)], ext[1]]
    if pattern == "converge":
        lo, hi, out = 0, len(ext) - 1, []
        while lo <= hi:
            out.append(ext[lo])
            if lo != hi:
                out.append(ext[hi])
            lo, hi = lo + 1, hi - 1
        return out
    if pattern == "octave":
        return [ext[0], ext[0] + 12, pool[min(2, len(pool) - 1)], ext[0] + 12]
    raise ValueError(pattern)


def arp_bar(seq, base_step, rate=1, gate=0.8, vel=(1.0, 0.72, 0.85, 0.7), skip=None):
    """One bar of arp events. ``base_step`` = absolute 16th index of the bar start (so cells that do
    not divide 16 keep running across bars → polyrhythm). ``rate`` 1 = 16ths, 2 = 8ths."""
    ev = []
    for s in range(0, 16, rate):
        k = (base_step + s) // rate
        if skip and skip(s, k):
            continue
        ev.append((s, gate * rate, seq[k % len(seq)], vel[(s // rate) % len(vel)]))
    return ev


# motif cells for 2-bar spans: (step, length, scale-step offset from the chord-tone anchor, vel)
HOOK_CELLS = {
    "anthem": ([(0, 4, 0, 1.0), (4, 2, 1, 0.8), (6, 2, 0, 0.85), (8, 6, -1, 0.95), (14, 2, 0, 0.8),
                (16, 8, 2, 1.0), (24, 6, 0, 0.9), (30, 2, -1, 0.75)],
               [(0, 4, 0, 1.0), (4, 2, 1, 0.8), (6, 2, 0, 0.85), (8, 6, -1, 0.95), (14, 2, -2, 0.8),
                (16, 14, 0, 1.0)]),
    "cathedral": ([(0, 6, 0, 1.0), (6, 2, 1, 0.8), (8, 8, 2, 0.95), (16, 12, 0, 0.9), (28, 4, -1, 0.75)],
                  [(0, 6, 0, 1.0), (6, 2, 1, 0.8), (8, 8, -1, 0.95), (16, 16, 0, 0.9)]),
    "pulse": ([(0, 2, 0, 1.0), (3, 2, 0, 0.8), (6, 2, 1, 0.9), (8, 2, 0, 0.85), (11, 2, -1, 0.8), (14, 2, 0, 0.8),
               (16, 6, 2, 1.0), (22, 2, 1, 0.8), (24, 8, 0, 0.9)],
              [(0, 2, 0, 1.0), (3, 2, 0, 0.8), (6, 2, 1, 0.9), (8, 2, 0, 0.85), (11, 2, -1, 0.8), (14, 2, 0, 0.8),
               (16, 16, -2, 1.0)]),
    "descend": ([(0, 8, 2, 1.0), (8, 4, 1, 0.85), (12, 4, 0, 0.85), (16, 12, -1, 0.95), (28, 4, 0, 0.75)],
                [(0, 8, 2, 1.0), (8, 4, 1, 0.85), (12, 4, 0, 0.85), (16, 16, 0, 0.95)]),
    "call": ([(0, 3, 0, 1.0), (3, 3, 2, 0.85), (6, 4, 1, 0.9), (10, 2, 0, 0.75), (12, 4, -1, 0.8), (20, 3, 0, 0.9),
              (23, 3, 1, 0.8), (26, 6, 0, 0.9)],
             [(0, 3, 0, 1.0), (3, 3, 2, 0.85), (6, 4, 1, 0.9), (10, 2, 0, 0.75), (12, 4, -1, 0.8), (16, 16, 0, 0.95)]),
}


def hook_events(key, chord_degs, cell="anthem", octave=4, bars_per_chord=2, start_anchor=4, lo=0, hi=11):
    """8-bar (4 chords × 2 bars) lead hook: the motif cell is restated over every chord, anchored on the
    chord tone nearest to the previous anchor (voice-leading in scale-degree space); the last chord
    uses the cell's resolving ending. Returns note events with steps from the hook start."""
    body, end = HOOK_CELLS[cell]
    ev, prev = [], start_anchor
    span = 16 * bars_per_chord
    for ci, cd in enumerate(chord_degs):
        cands = [cd + o + 7 * k for o in (0, 2, 4) for k in (-1, 0, 1, 2)]
        cands = [c for c in cands if lo <= c <= hi] or [cd]
        anchor = min(cands, key=lambda c: (abs(c - prev), c))
        cells = end if ci == len(chord_degs) - 1 else body
        for st, ln, off, v in cells:
            if st < span:
                ev.append((ci * span + st, min(ln, span - st) - 0.15, key.degree(anchor + off, octave), v))
        prev = anchor
    return ev


def bass_roll(root, pattern="roll3", rng_bar=None, fifth=7, octave_jump=True, shape=None):
    """One bar of rolling bass events avoiding the kick downbeats.

    patterns: ``roll3`` (_xxx per beat), ``roll2`` (__xx), ``offbeat`` (__x_), ``gallop`` (_x_x … ),
    ``tri`` (_xx_ x_x_ triplet feel). ``shape``: semitone offsets cycled over the hits of each beat
    (e.g. ``[0, 12, 0]`` = root-octave-root arpeggiated roll)."""
    steps = {
        "roll3": [1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15],
        "roll2": [2, 3, 6, 7, 10, 11, 14, 15],
        "offbeat": [2, 6, 10, 14],
        "gallop": [1, 3, 5, 7, 9, 11, 13, 15],
        "tri": [1, 2, 5, 7, 9, 10, 13, 15],
    }[pattern]
    ev = []
    k_in_beat, last_beat = 0, -1
    for s in steps:
        beat = s // 4
        k_in_beat = k_in_beat + 1 if beat == last_beat else 0
        last_beat = beat
        p = root + (shape[k_in_beat % len(shape)] if shape else 0)
        v = 0.95 if s % 4 == 2 else 0.78
        if octave_jump and s == 15 and not shape:
            p = root + 12
        elif fifth and s == 11 and rng_bar is not None and rng_bar.random() < 0.3:
            p = root + fifth
        ev.append((s, 0.85 if pattern != "offbeat" else 1.6, p, v))
    return ev


def poly_hits(c, period, offset=0, steps=16, reset_bars=None):
    """Step indexes of this bar for a ``period``-step polymeter (e.g. 3 = dotted 8ths against 4/4),
    counted from the section start (or reset every ``reset_bars``)."""
    i = c.i if not reset_bars else c.i % reset_bars
    base = i * steps
    return [s for s in range(steps) if (base + s - offset) % period == 0]


def steps_to_pattern(idx, steps=16, ch="x", vel_fn=None):
    p = ["."] * steps
    for k, s in enumerate(idx):
        p[s] = vel_fn(k, s) if vel_fn else ch
    return "".join(p)


# ============================================================================ transitions
def roll_buffer(song, bars, hit, divisions=None, vel_from=0.3, vel_to=1.0, pitch_up=5.0, steps=12, swell=1.6):
    """Accelerating snare/clap roll ``bars`` long ending exactly at its last sample (place with
    ``align='end'`` on the drop bar). Pitch rises by ``pitch_up`` semitones; stereo."""
    g = song.grid
    sr = song.sr
    n = int(round(bars * g.bar_sec * sr))
    buf = np.zeros((n, 2), dtype=F32)
    hit = as_stereo(hit)
    shifted = [as_stereo(pitch_shift(hit, pitch_up * k / (steps - 1))) for k in range(steps)]
    if divisions is None:
        divisions = {1: [16], 2: [8, 16], 4: [4, 8, 16, 32], 8: [4, 4, 8, 8, 8, 16, 16, 32],
                     16: [4] * 4 + [8] * 4 + [8, 8, 16, 16] + [16, 16, 32, 32]}.get(bars) or [8] * (bars - 2) + [16, 32]
    T = n
    for b, div in enumerate(divisions[:bars]):
        for k in range(div):
            t = (b + k / div) * g.bar_sec
            pos = int(round(t * sr))
            frac = pos / T
            v = vel_from + (vel_to - vel_from) * frac ** swell
            x = shifted[min(steps - 1, int(frac * steps))]
            e = min(n, pos + x.shape[0])
            buf[pos:e] += x[: e - pos] * F32(v)
    return fade(buf, 0, int(0.004 * sr))


def pitched_riser(dur_sec, f_from=110.0, f_to=1760.0, q=7.0, rng=None, saw_mix=0.35, sr=SR):
    """Pitched noise riser: resonant band-passed noise + saw following an exponential pitch sweep,
    amplitude swelling to the end (place with ``align='end'``). Stereo, peak 1."""
    rng = rng if rng is not None else np.random.default_rng(8)
    n = int(dur_sec * sr)
    t = np.linspace(0, 1, n)
    f = f_from * (f_to / f_from) ** (t ** 1.3)
    chans = []
    for c in range(2):
        nz = white(n, rng)
        y = svf(nz, f, q, "bp") * 2.0 + svf(nz, f * 2, q, "bp") * 0.8 + hp(nz, 7000.0, 2) * 0.15 * t
        y = y + saw_mix * svf(saw(f * (1 + 0.003 * c), n, 0.3 * c), f * 3, 0.8, "lp")
        chans.append(y)
    x = np.stack(chans, axis=1) * (t ** 2.0)[:, None]
    return normalize(fade(x.astype(F32), int(0.01 * sr), int(0.003 * sr)))


def ramp_points(song, kind, bars, lo, hi):
    pts = []
    for s in song.sections:
        if s.kind == kind or s.name == kind:
            pts += [(s.start_bar - bars, lo), (s.start_bar - 1e-3, hi), (s.start_bar, lo)]
    return pts or [(0, lo)]


def setup_space(song, hall_decay=None, hall_width=1.5, plate_width=1.4, long_reverb=None, delay_fb=None,
                quarter_delay=False):
    """Wider returns for the techno family (+ optional 'space' long reverb and quarter-note delay)."""
    song.returns["reverb"].width = plate_width
    song.returns["hall"].width = hall_width
    song.returns["room"].width = 1.3
    if hall_decay:
        song.returns["hall"].decay = hall_decay
    if delay_fb is not None:
        song.returns["delay"].feedback = delay_fb
    if long_reverb:
        song.returns["space"] = Return("space", "reverb", "huge", decay=long_reverb, hp=400.0, lp=7000.0,
                                       sidechain=0.55, width=1.6)
    if quarter_delay:
        song.returns["delay4"] = Return("delay4", "delay", beats=1.0, feedback=0.45, hp=500.0, lp=4000.0,
                                        sidechain=0.6, width=1.3)
