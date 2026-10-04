"""Shared sound design for the mainstream recipes (big room, pop dance, hip-hop/trap, reggaeton,
moombahton).

Everything here is built from the engine's own primitives (``dsp``/``synth``/``drums``/``fx``) and is
fully deterministic (only seeded ``numpy`` generators). Nothing in the engine core depends on this
module; recipes import it as ``from .. import ext_mainstream as xm``.

Contents
--------
* :class:`GlideSynth` – monophonic synth with portamento, retrigger-safe envelopes, vibrato, scoop,
  unison and breath noise. Drop-in ``synth`` for :class:`~djlab.arrangement.MonoLine` layers
  (``song.line(name, GlideSynth(...), notes)``), used for 808s, toplines, pan flutes, Dutch leads.
* Note instruments (``inst(freq, dur, vel)``): :func:`rhodes`, :func:`supersaw_stab`,
  :func:`big_lead`, :func:`chant`, :func:`nylon`, :func:`wobble_bass`, :func:`deep_bass`,
  :func:`soft_pad`, :func:`square_pluck`.
* One-shots: :func:`big_room_kick`, :func:`boom_kick`, :func:`boom_snare`, :func:`timbale`,
  :func:`guiro`, :func:`trap_kick`, :func:`dusty`.
* Audio builders: :func:`pitch_shift`, :func:`build_roll` (accelerating, pitch-rising snare build),
  :func:`siren`, :func:`scratch`, :func:`vinyl_crackle` (``Custom`` layer fn), :func:`trap_hats`
  (96-step hi-hat roll patterns).
"""
from __future__ import annotations

import math
from fractions import Fraction

import numpy as np
from scipy import signal
from scipy.signal import lfilter

from . import SR, drums
from .dsp import F32, as_stereo, bp, fade, hp, ladder, lp, normalize, pan, saw, sine, square, svf, triangle
from .synth import fm, formant_filter, karplus, supersaw, white

TAU = 2 * math.pi


def _t(n, sr=SR):
    return np.arange(n) / sr


def _hz(midi):
    return 440.0 * 2.0 ** ((np.asarray(midi, dtype=np.float64) - 69.0) / 12.0)


def _onepole(x, ms, sr=SR):
    a = math.exp(-1.0 / max(1.0, ms * 1e-3 * sr))
    return lfilter([1 - a], [1, -a], x)


# ============================================================================ glide synth (MonoLine)
class GlideSynth:
    """Monophonic synth for ``MonoLine`` layers.

    Events (from MonoLine): ``(start, gate, midi, vel, slide, accent)``; ``slide`` = this note glides
    into the next one with the gate held (TB-303 semantics), so 808 glides / legato toplines are just
    ``"s"`` flags in the note tuples.

    ``osc``: ``saw`` | ``square`` | ``tri`` | ``sine`` | ``808`` (sine + punch + drive) |
    ``flute`` (sine/tri + breath). Envelopes are retriggered from the *current* level (no clicks),
    the filter envelope restarts on every non-slid note, vibrato fades in after ``vib_delay``.
    """

    def __init__(self, osc="saw", voices=1, detune_cents=0.0, spread=0.6, sub=0.0, pw=0.5,
                 cutoff=4000.0, res=0.15, env_amt=0.0, env_decay=0.15, attack=0.005, decay=0.3, sustain=0.8,
                 release=0.08, glide_ms=60.0, vib_cents=0.0, vib_hz=5.5, vib_delay=0.25, scoop=0.0, scoop_ms=35.0,
                 punch=0.0, punch_ms=18.0, drive=1.0, breath=0.0, chiff=0.0, amp_decay=None, gain=0.7, seed=1,
                 sr=SR):
        self.__dict__.update({k: v for k, v in locals().items() if k != "self"})

    # ---- per-sample control curves
    def _controls(self, events, n):
        sr = self.sr
        pitch = np.zeros(n)
        age = np.zeros(n)          # seconds since last retrigger
        env = np.zeros(n)
        vel_arr = np.zeros(n)
        events = sorted([e for e in events if e[0] < n], key=lambda e: e[0])
        if not events:
            return None
        gl = max(1, int(self.glide_ms * 1e-3 * sr))
        rel_tc = max(1e-4, self.release / 4.0)
        prev_slide, prev_midi, level = False, None, 0.0
        trig_start, trig_vel = 0, 1.0
        # group events into retrigger chains (slid notes continue the chain)
        for i, (s, g, midi, vel, slide, accent) in enumerate(events):
            s = int(max(0, s))
            end = int(events[i + 1][0]) if i + 1 < len(events) else n
            end = min(n, max(end, s + 1))
            seg = end - s
            k = np.arange(seg)
            if prev_slide and prev_midi is not None:
                m = min(gl, seg)
                p = np.full(seg, float(midi))
                p[:m] = prev_midi + (midi - prev_midi) * (0.5 - 0.5 * np.cos(np.pi * k[:m] / m))
                pitch[s:end] = p
                a0 = (s - trig_start) / sr
                age[s:end] = a0 + k / sr
                v = trig_vel
            else:
                pitch[s:end] = midi
                age[s:end] = k / sr
                trig_start, trig_vel = s, float(vel) * (1.0 + 0.25 * bool(accent))
                v = trig_vel
            vel_arr[s:end] = v
            # amplitude envelope for this segment (gate end: slide holds to next note)
            gate_n = seg if slide else int(min(seg, max(16, g)))
            tt = age[s:end]
            a = max(self.attack, 1e-4)
            dec = self.amp_decay if self.amp_decay else self.decay
            ads = np.where(tt < a, tt / a, self.sustain + (1 - self.sustain) * np.exp(-(tt - a) / max(dec, 1e-4)))
            if not (prev_slide and prev_midi is not None):
                # attack starts from the level the previous note had reached (click-free retrigger)
                ads = np.where(tt < a, level / max(v, 1e-6) + (1 - level / max(v, 1e-6)) * (tt / a), ads)
            e = ads * v
            if gate_n < seg:
                lv = e[gate_n - 1] if gate_n > 0 else level
                e[gate_n:] = lv * np.exp(-(np.arange(seg - gate_n) / sr) / rel_tc)
            env[s:end] = e
            level = float(e[-1])
            prev_slide = bool(slide)
            prev_midi = float(midi)
        first = int(events[0][0])
        env[:max(0, first)] = 0.0
        return pitch, age, _onepole(env, 0.7, sr), vel_arr

    def render(self, events, n, cutoff_curve=None, res_curve=None, env_curve=None):
        sr = self.sr
        c = self._controls(events, n)
        if c is None:
            return np.zeros((n, 2), dtype=F32)
        pitch, age, env, vel = c
        first = int(max(0, min(e[0] for e in events)))
        rng = np.random.default_rng(self.seed)
        # pitch modulation: scoop / 808 punch on retrigger, delayed vibrato
        p = pitch.copy()
        if self.scoop:
            p += self.scoop * np.exp(-age / (self.scoop_ms * 1e-3))
        if self.punch:
            p += self.punch * np.exp(-age / (self.punch_ms * 1e-3))
        if self.vib_cents:
            ramp = np.clip((age - self.vib_delay) / 0.25, 0.0, 1.0)
            p += (self.vib_cents / 100.0) * ramp * np.sin(TAU * self.vib_hz * np.arange(n) / sr)
        f = _hz(p)
        f[:first] = f[first] if first < n else 55.0
        osc = self.osc
        stereo = None
        if osc in ("808", "sine"):
            x = sine(f, n)
            if osc == "808":
                x = x + 0.12 * sine(2 * f, n)
        elif osc == "flute":
            x = sine(f, n) * 0.8 + triangle(f, n) * 0.25 + 0.06 * sine(2 * f, n)
        else:
            def one(ff, ph):
                if osc == "square":
                    return square(ff, n, ph, self.pw)
                if osc == "tri":
                    return triangle(ff, n, ph)
                return saw(ff, n, ph)
            if self.voices > 1:
                stereo = np.zeros((n, 2), dtype=np.float64)
                for v in range(self.voices):
                    pos = (v / (self.voices - 1)) * 2 - 1
                    y = one(f * 2 ** (pos * self.detune_cents / 1200.0), rng.random())
                    stereo += pan(y, pos * self.spread)
                stereo /= math.sqrt(self.voices)
                x = None
            else:
                x = one(f, rng.random())
        if self.sub:
            s = sine(f / 2, n) * self.sub
            if stereo is not None:
                stereo += s[:, None]
            else:
                x = x + s
        if self.breath:
            nz = white(n, rng).astype(np.float64)
            br = svf(nz, np.clip(f * 2.0, 200, 12000), 2.5, "bp") * 0.6 + hp(nz, 4000.0) * 0.15
            br = br * (0.35 + 0.65 * np.exp(-age / 0.08))
            if stereo is not None:
                stereo += (self.breath * br)[:, None]
            else:
                x = x + self.breath * br
        # filter
        cut = np.asarray(cutoff_curve if cutoff_curve is not None else self.cutoff, dtype=np.float64)
        amt = np.asarray(env_curve if env_curve is not None else self.env_amt, dtype=np.float64)
        if np.any(amt):
            cut = cut * 2.0 ** (amt * np.exp(-age / max(self.env_decay, 1e-3)) * np.clip(vel, 0.3, 1.3))
        cut = np.clip(cut * np.ones(n), 30.0, 18000.0)
        q = 0.707 + 4.0 * float(self.res)
        if stereo is not None:
            y = svf(stereo.astype(F32), cut, q, "lp")
        else:
            y = svf(np.asarray(x, dtype=F32), cut, q, "lp")
        if self.drive > 1.0:
            y = np.tanh(y * self.drive) / math.tanh(self.drive)
        y = y * (env[:, None] if y.ndim == 2 else env)
        if self.chiff:
            nz2 = hp(white(n, rng), 2500.0).astype(np.float64) * np.exp(-age / 0.02) * self.chiff * env
            y = y + (nz2[:, None] if y.ndim == 2 else nz2)
        y = hp(np.asarray(y, dtype=F32), 25.0, 2)
        return (np.asarray(y) * self.gain).astype(F32)


def synth_808(decay=1.2, drive=2.4, punch=7.0, glide_ms=70.0, release=0.09, tone=1.0, gain=0.75, seed=8):
    """Tuned trap/reggaeton 808 for MonoLine layers (sine + 2nd harmonic, pitch punch, drive, glides)."""
    return GlideSynth(osc="808", attack=0.002, decay=decay, sustain=0.0, amp_decay=decay / 2.2, release=release,
                      glide_ms=glide_ms, punch=punch, punch_ms=14.0, drive=drive, cutoff=900.0 * tone, res=0.0,
                      gain=gain, seed=seed)


# ============================================================================ note instruments
def _finish(x, vel, rel_fade=128):
    x = fade(np.asarray(x, dtype=F32), 16, rel_fade)
    return normalize(x, 0.8 * float(vel))


def _n(dur, release, sr=SR):
    gate = max(16, int(dur * sr))
    return gate, gate + int(release * sr)


def _adsr(n, gate, a, d, s, r, sr=SR):
    t = _t(n, sr)
    env = np.where(t < a, t / max(a, 1e-5), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-5)))
    if gate < n:
        lv = env[gate - 1]
        env[gate:] = lv * np.exp(-(t[gate:] - t[gate]) / max(r / 4.0, 1e-5))
    return env


def rhodes(bright=0.55, bark=0.6, trem_hz=4.2, trem=0.22, wow_cents=6.0, release=0.35, sr=SR):
    """FM Rhodes-style electric piano: 1:1 body with velocity 'bark', 14:1 tine, stereo tremolo,
    slight tape wow, soft saturation. Stereo."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = _t(n, sr)
        wob = 2 ** ((wow_cents / 1200.0) * np.sin(TAU * 0.55 * t + 1.3))
        f = freq * wob
        idx_env = np.exp(-t / (0.18 + 0.25 * (1 - vel)))
        body = fm(f, n, 1.0, 0.25 + bark * vel * 1.6, idx_env)
        tine = fm(f, n, 14.0, 0.9 * bright, np.exp(-t / 0.012)) * (0.3 * bright * vel)
        oct2 = np.sin(TAU * np.cumsum(f * 2.0) / sr) * 0.08 * np.exp(-t / 0.5)
        x = body + tine + oct2
        x = np.tanh(x * (1.0 + 0.8 * vel * bark)) / math.tanh(1.0 + 0.8 * vel * bark)
        dec = np.exp(-t / (1.6 + 180.0 / freq))
        env = dec * _adsr(n, gate, 0.002, 2.0, 1.0, release, sr)
        x = x * env
        tr = trem * np.sin(TAU * trem_hz * t)
        st = np.stack([x * (1 - tr), x * (1 + tr)], axis=1)
        return _finish(st, vel, 256)
    return inst


def supersaw_stab(detune=0.4, mix=0.75, cutoff=2500.0, env_amt=6000.0, f_decay=0.18, attack=0.003,
                  decay=0.35, sustain=0.0, release=0.12, res=0.15, drive=1.3, oct_down=0.0, sr=SR):
    """Supersaw chord voice: pluck (sustain 0) or held (sustain > 0) with a filter envelope. Stereo."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = _t(n, sr)
        x = supersaw(freq, n, detune=detune, mix=mix, rng=np.random.default_rng(int(freq * 10) % 99991))
        if oct_down:
            x = x + as_stereo(saw(freq / 2, n, 0.13)) * oct_down
        cut = np.clip(cutoff + env_amt * vel * np.exp(-t / f_decay), 80, 18000)
        x = svf(x, cut, 0.707 + res * 3, "lp")
        if drive > 1:
            x = np.tanh(x * drive) / math.tanh(drive)
        env = _adsr(n, gate, attack, decay, sustain, release, sr)
        return _finish(x * env[:, None], vel, 256)
    return inst


def big_lead(detune=0.5, mix=0.85, cutoff=7000.0, zap=7.0, zap_ms=22.0, oct_down=0.55, square_up=0.18,
             drive=1.8, attack=0.002, decay=0.25, sustain=0.75, release=0.18, sr=SR):
    """Festival big-room lead: wide supersaw + saw an octave below + thin square an octave above, a
    fast pitch 'zap' into each note, drive. Stereo, huge."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = _t(n, sr)
        fz = freq * 2 ** (zap * np.exp(-t / (zap_ms * 1e-3)) / 12.0)
        rng = np.random.default_rng(int(freq * 7) % 77777)
        x = supersaw(fz, n, detune=detune, mix=mix, rng=rng)
        x = x + as_stereo(saw(fz / 2, n, 0.31)) * oct_down
        if square_up:
            x = x + pan(square(fz * 2, n, 0.2, 0.5), 0.0) * square_up
        cut = np.clip(cutoff * (0.55 + 0.45 * vel) * (1 + 1.5 * np.exp(-t / 0.06)), 200, 18000)
        x = svf(x, cut, 0.9, "lp")
        x = np.tanh(x * drive) / math.tanh(drive)
        env = _adsr(n, gate, attack, decay, sustain, release, sr)
        return _finish(x * env[:, None], vel, 256)
    return inst


def chant(vowel="e", vowel_to="i", voices=6, shift=1.0, fall=-3.0, breath=0.25, spread=0.9, release=0.08,
          sr=SR):
    """Crowd-style vowel shout ("HEY!" / "OH!"): several detuned glottal voices with individual timing,
    vibrato and formant shifts through a vowel morph, plus a breathy noise layer. Stereo."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = _t(n, sr)
        out = np.zeros((n, 2), dtype=np.float64)
        rng = np.random.default_rng(int(freq * 3) % 65521)
        for v in range(voices):
            det = rng.uniform(-22, 22)
            off = int(rng.uniform(0, 0.022) * sr)
            fv = freq * 2 ** ((det + 100 * fall * np.clip((t - dur * 0.55) / max(dur * 0.45, 1e-3), 0, 1)
                               + 25 * np.sin(TAU * rng.uniform(4.5, 6.5) * t + rng.random() * TAU)) / 1200.0)
            src = saw(fv, n, rng.random()) * 0.8 + square(fv, n, rng.random(), 0.3) * 0.2
            src = src + breath * white(n, rng)
            y = formant_filter(src, vowel, vowel_to, shift * rng.uniform(0.92, 1.1), sr)
            y = np.concatenate([np.zeros(off), y[: n - off]])
            out += pan(y.astype(F32), (v / max(1, voices - 1) * 2 - 1) * spread)
        nz = svf(white(n, rng), 1800.0 * shift, 1.2, "bp") * np.exp(-t / 0.05) * 0.6
        out += as_stereo(nz)
        env = _adsr(n, gate, 0.012, 0.25, 0.7, release, sr)
        out = hp(out * env[:, None], 220.0)
        return _finish(out, vel, 256)
    return inst


def nylon(bright=0.42, decay=0.9965, body_hz=210.0, pick=0.25, release=0.12, sr=SR):
    """Nylon-guitar-like Karplus-Strong pluck with body resonance and pick noise (Latin arps). Stereo."""
    def inst(freq, dur, vel):
        gate, n = _n(max(dur, 0.5), release, sr)
        t = _t(n, sr)
        rng = np.random.default_rng(int(freq * 13) % 65521)
        x = karplus(freq, n, decay, bright * (0.6 + 0.4 * vel), rng).astype(np.float64)
        x = x + 0.35 * svf(x.astype(F32), body_hz, 1.8, "bp") + 0.15 * svf(x.astype(F32), body_hz * 2.3, 2.0, "bp")
        x = x + pick * svf(white(n, rng), 3200.0, 1.2, "bp") * np.exp(-t / 0.004)
        x = lp(x, 7000.0)
        env = _adsr(n, gate, 0.0005, 6.0, 1.0, release, sr)
        x = x * env
        d = int(0.0006 * sr)
        st = np.stack([x, np.concatenate([np.zeros(d), x[:-d]])], axis=1)
        return _finish(st, vel, 256)
    return inst


def square_pluck(pw=0.35, cutoff=900.0, env_amt=5000.0, decay=0.09, release=0.08, detune=7.0, sr=SR):
    """Short square/saw pluck (reggaeton / moombahton / pop plucks). Stereo."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = _t(n, sr)
        a = square(freq * 2 ** (detune / 1200), n, 0.1, pw)
        b = saw(freq * 2 ** (-detune / 1200), n, 0.6)
        x = np.stack([a * 0.7 + b * 0.3, a * 0.3 + b * 0.7], axis=1)
        x = svf(x, np.clip(cutoff + env_amt * vel * np.exp(-t / decay), 80, 18000), 1.3, "lp")
        env = _adsr(n, gate, 0.001, decay * 3.0, 0.12, release, sr)
        return _finish(x * env[:, None], vel)
    return inst


def soft_pad(attack=0.6, release=1.2, cutoff=1600.0, detune=0.22, warmth=0.6, sr=SR):
    """Warm stereo pad (supersaw + triangle), slow filter drift."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = _t(n, sr)
        x = supersaw(freq, n, detune=detune, mix=0.5, rng=np.random.default_rng(int(freq) % 997))
        x = x * (1 - warmth * 0.5) + as_stereo(triangle(freq, n)) * warmth * 0.6
        cut = cutoff * (1 + 0.3 * np.sin(TAU * 0.11 * t + freq))
        x = svf(x, cut, 0.8, "lp")
        env = _adsr(n, gate, attack, 0.6, 0.85, release, sr)
        return _finish(x * env[:, None], vel, 1024)
    return inst


def deep_bass(cutoff=420.0, harm=0.35, drive=1.6, attack=0.004, decay=0.35, sustain=0.6, release=0.06,
              slide_semis=0.0, sr=SR):
    """Round hip-hop/R&B bass: sine + soft triangle/saw harmonics, low-passed, gently driven. Mono."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = _t(n, sr)
        f = freq * 2 ** (slide_semis * np.exp(-t / 0.04) / 12.0)
        x = sine(f, n) + harm * triangle(f, n) + harm * 0.35 * saw(f, n)
        x = lp(x, cutoff * (0.8 + 0.4 * vel))
        x = np.tanh(x * drive) / math.tanh(drive)
        env = _adsr(n, gate, attack, decay, sustain, release, sr)
        return _finish(x * env, vel, 256)
    return inst


def wobble_bass(bpm, beats=0.5, lo=180.0, hi=2600.0, res=0.55, detune=14.0, drive=2.6, sub=0.8,
                shape="sine", release=0.05, sr=SR):
    """Moombahton/dubstep wobble: detuned saw+square through a resonant ladder whose cutoff is swept by
    a tempo-synced LFO (one cycle per ``beats``), sine sub underneath. Mono."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = _t(n, sr)
        rate = bpm / 60.0 / beats
        ph = (rate * t) % 1.0
        if shape == "saw":
            l = 1.0 - ph
        elif shape == "square":
            l = np.where(ph < 0.5, 1.0, 0.0)
            l = _onepole(l, 4.0, sr)
        else:
            l = 0.5 - 0.5 * np.cos(TAU * ph + np.pi)  # starts open on the downbeat
        cut = lo * (hi / lo) ** l
        o = saw(freq * 2 ** (detune / 1200), n, 0.0) * 0.5 + square(freq * 2 ** (-detune / 1200), n, 0.4, 0.5) * 0.5
        y = ladder(o, cut, res, drive)
        y = y + sub * sine(freq, n) * 0.9
        y = np.tanh(y * 1.4) / math.tanh(1.4)
        env = _adsr(n, gate, 0.004, 0.5, 0.95, release, sr)
        return _finish(y * env, vel, 256)
    return inst


# ============================================================================ drums / one-shots
def dusty(x, bits=12, rate_div=1, lp_hz=9500.0, drive=1.4):
    """'Sampled through an old sampler' processing: low-pass, bit reduction, saturation."""
    y = np.asarray(x, dtype=F32)
    if lp_hz:
        y = lp(y, lp_hz, 2)
    q = 2 ** (bits - 1)
    y = np.round(y * q) / q
    if rate_div > 1:
        idx = (np.arange(y.shape[0]) // rate_div) * rate_div
        y = lp(y[idx], 11000.0, 2)
    y = np.tanh(y * drive) / math.tanh(drive)
    return normalize(y.astype(F32))


def big_room_kick(tune_hz=50.0, tail=0.6, drive=2.6, click=0.85, rng=None, sr=SR):
    """Festival kick: hard punchy transient + long saturated tuned tail."""
    rng = rng if rng is not None else np.random.default_rng(0)
    base = drums.kick("big_room", tune_hz=tune_hz, decay=0.3, click=click, drive=drive, length=0.32, rng=rng)
    n = int((0.32 + tail) * sr)
    t = _t(n, sr)
    f = tune_hz * (1 + 0.35 * np.exp(-t / 0.05))
    body = np.sin(TAU * np.cumsum(f) / sr)
    env = np.exp(-t / (tail / 3.0)) * np.clip((t - 0.015) / 0.03, 0, 1)
    tl = np.tanh(body * env * 2.2) * 0.55
    x = np.zeros(n)
    x[: base.shape[0]] += base
    x += tl
    x = np.tanh(x * 1.3) / math.tanh(1.3)
    x = hp(x, 28.0, 2)
    return normalize(fade(x.astype(F32), 0, int(0.03 * sr)))


def trap_kick(tune_hz=52.0, rng=None, sr=SR):
    """Short, punchy, clicky kick that sits in front of a long 808."""
    rng = rng if rng is not None else np.random.default_rng(0)
    k = drums.kick("tech_house", tune_hz=tune_hz, decay=0.2, click=0.75, drive=2.0, length=0.3, rng=rng)
    return normalize(hp(k, 35.0, 2))


def boom_kick(tune_hz=56.0, rng=None, sr=SR):
    """Dusty boom-bap kick: round thump with a knocky beater, sampled-sounding."""
    rng = rng if rng is not None else np.random.default_rng(0)
    k = drums.kick("909", tune_hz=tune_hz, decay=0.34, click=0.55, drive=1.8, length=0.45, rng=rng)
    n = k.shape[0]
    t = _t(n, sr)
    knock = svf(white(n, rng), 1300.0, 1.5, "bp") * np.exp(-t / 0.006) * 0.35
    return dusty(k + knock, bits=12, lp_hz=8000.0, drive=1.6)


def boom_snare(tone_hz=195.0, snappy=0.62, body=0.6, room=0.18, rng=None, sr=SR):
    """Crisp boom-bap snare: tonal body + bright snap + a tight clap layer + short room tail."""
    rng = rng if rng is not None else np.random.default_rng(0)
    s = drums.snare(tone_hz=tone_hz, snappy=snappy, decay=0.2, rng=rng)
    c = drums.clap(tightness=0.6, tone_hz=1500.0, tail=0.1, bursts=3, rng=rng)
    n = max(s.shape[0], c.shape[0]) + int(0.25 * sr)
    x = np.zeros(n, dtype=F32)
    x[: s.shape[0]] += s * (0.8 + 0.2 * body)
    x[: c.shape[0]] += c * 0.45
    t = _t(n, sr)
    tail = bp(white(n, rng), 600.0, 7000.0) * np.exp(-t / 0.09) * room
    x = x + tail * np.clip(t / 0.01, 0, 1)
    return dusty(hp(x, 110.0), bits=12, lp_hz=11000.0, drive=1.5)


def timbale(pitch_hz=520.0, ring=0.5, rng=None, sr=SR):
    """Timbale: bright pitched shell with metallic ring and stick crack."""
    rng = rng if rng is not None else np.random.default_rng(0)
    n = int(0.45 * sr)
    t = _t(n, sr)
    f = pitch_hz * (1 + 0.18 * np.exp(-t / 0.01))
    ph = TAU * np.cumsum(f) / sr
    body = np.sin(ph) * np.exp(-t / 0.09)
    rng_part = (0.5 * np.sin(1.47 * ph + 0.3) * np.exp(-t / 0.12) + 0.35 * np.sin(2.31 * ph) * np.exp(-t / 0.15)
                + 0.2 * np.sin(3.9 * ph) * np.exp(-t / 0.08)) * ring
    crack = hp(white(n, rng), 3000.0) * np.exp(-t / 0.004) * 0.8
    x = body + rng_part + crack
    return normalize(fade(hp(x, 180.0), 0, int(0.02 * sr)))


def guiro(length=0.16, teeth=14, rng=None, sr=SR):
    """Güiro scrape: a fast train of tiny band-passed noise ticks with a rising rate."""
    rng = rng if rng is not None else np.random.default_rng(0)
    n = int(length * sr)
    x = np.zeros(n)
    pos = np.cumsum(np.linspace(1.4, 0.7, teeth))
    pos = (pos / pos[-1] * (n - int(0.004 * sr))).astype(int)
    tick = svf(white(int(0.004 * sr), rng), 4200.0, 2.0, "bp") * np.exp(-_t(int(0.004 * sr)) / 0.0012)
    for p in pos:
        x[p:p + tick.shape[0]] += tick * rng.uniform(0.6, 1.0)
    x = bp(x, 1500.0, 9000.0)
    env = np.clip(_t(n) / 0.01, 0, 1) * np.exp(-_t(n) / (length * 1.2))
    return normalize(fade((x * env).astype(F32), 0, int(0.005 * sr)))


# ============================================================================ audio builders / FX
def pitch_shift(x, semis):
    """Repitch (sampler-style, duration changes) by polyphase resampling."""
    if not semis:
        return np.asarray(x, dtype=F32)
    ratio = Fraction(2 ** (-semis / 12.0)).limit_denominator(96)
    y = signal.resample_poly(np.asarray(x, dtype=np.float64), ratio.numerator, ratio.denominator, axis=0)
    return fade(y.astype(F32), 0, 64)


def build_roll(song, sample, start_bar, bars, schedule=None, semis=(0.0, 12.0), vel=(0.35, 1.0),
               lp_hz=(1500.0, 16000.0), last_beat_rest=False):
    """Accelerating snare/clap build that RISES IN PITCH (big room / EDM style). Returns stereo audio
    to place at ``start_bar`` (``song.audio(...).add(buf, start_bar)``). ``schedule``: hits per beat
    for each bar (default for 8 bars: 1,1,2,2,4,4,8,8)."""
    g = song.grid
    if schedule is None:
        base = [1, 1, 2, 2, 4, 4, 8, 8]
        schedule = base[-bars:] if bars <= 8 else [1] * (bars - 8) + base
    total = g.bar_sample(start_bar + bars) - g.bar_sample(start_bar)
    out = np.zeros((total + int(0.6 * song.sr), 2), dtype=F32)
    cache = {}
    nh = 0
    hits = []
    for b in range(bars):
        per = schedule[b]
        for beat in range(4):
            if last_beat_rest and b == bars - 1 and beat == 3:
                continue
            for k in range(per):
                hits.append((b, beat + k / per))
    for i, (b, bt) in enumerate(hits):
        prog = (b + bt / 4.0) / bars
        st = round(semis[0] + (semis[1] - semis[0]) * prog ** 1.3, 1)
        if st not in cache:
            cache[st] = as_stereo(pitch_shift(sample, st))
        x = cache[st]
        v = vel[0] + (vel[1] - vel[0]) * prog ** 1.2
        pos = g.sample(start_bar + b, bt) - g.bar_sample(start_bar)
        e = min(out.shape[0], pos + x.shape[0])
        out[pos:e] += x[: e - pos] * v
        nh += 1
    cut = lp_hz[0] * (lp_hz[1] / lp_hz[0]) ** (np.linspace(0, 1, out.shape[0]) ** 1.5)
    out = svf(out, cut, 0.8, "lp")
    return normalize(out[:total + int(0.3 * song.sr)])


def siren(dur_sec=4.0, f_lo=500.0, f_hi=1400.0, rate=2.0, rng=None, sr=SR):
    """Dancehall/reggaeton siren FX (LFO-swept square through a band-pass), stereo, ends quiet."""
    n = int(dur_sec * sr)
    t = _t(n, sr)
    f = f_lo + (f_hi - f_lo) * (0.5 + 0.5 * np.sin(TAU * rate * t - np.pi / 2))
    x = square(f, n, 0.0, 0.5) * 0.6 + saw(f * 1.005, n, 0.3) * 0.4
    x = bp(x, 400.0, 5000.0)
    env = np.clip(t / 0.05, 0, 1) * (1 - t / dur_sec) ** 0.6
    st = np.stack([x * env, np.concatenate([np.zeros(300), (x * env)[:-300]])], axis=1)
    return normalize(fade(st, 0, int(0.05 * sr)))


def scratch(source, bpm, beats=1.0, moves=(1, -1, 1, -1), cut=True, sr=SR):
    """Turntable 'baby scratch' synthesised from a short source sound: the playback position follows a
    back-and-forth curve (rate ∝ hand speed, so pitch sweeps like vinyl), optional crossfader cuts.
    Returns stereo audio of ``beats`` beats."""
    src = np.asarray(source, dtype=np.float64)
    if src.ndim == 2:
        src = src.mean(axis=1)
    n = int(beats * 60.0 / bpm * sr)
    seg = n // len(moves)
    pos = np.zeros(n)
    p = 0.0
    span = min(src.shape[0] - 2, int(0.18 * sr))
    for i, d in enumerate(moves):
        k = np.arange(seg)
        stroke = 0.5 - 0.5 * np.cos(np.pi * k / seg)
        pos[i * seg:(i + 1) * seg] = p + d * span * stroke
        p = p + d * span
    pos[len(moves) * seg:] = p
    pos = np.clip(pos, 0, src.shape[0] - 2)
    y = np.interp(pos, np.arange(src.shape[0]), src)
    speed = np.abs(np.gradient(pos))
    y = y * np.clip(speed / (np.max(speed) + 1e-9) * 1.6, 0, 1)
    if cut:
        gate = np.ones(n)
        for i in range(len(moves)):
            a = i * seg + int(seg * 0.82)
            gate[a:(i + 1) * seg] = 0.0
        y = y * _onepole(gate, 1.5, sr)
    y = hp(lp(y.astype(F32), 7000.0), 250.0)
    return normalize(fade(as_stereo(y), 32, 256))


def vinyl_crackle(seed, level=1.0, hiss=0.35, rate=26.0, pops=0.6, sr=SR):
    """Custom-layer function ``fn(song, a, b)`` → vinyl crackle + hiss. Generated in fixed 1-second
    blocks seeded by (seed, block), so any render window gives identical samples."""
    blk = sr

    def block(i):
        r = np.random.default_rng((int(seed) * 7919 + i * 104729) % (2 ** 32))
        out = np.zeros((blk, 2), dtype=np.float64)
        h = svf(white(blk, r), 5200.0, 0.5, "bp") * 0.02 * hiss
        out += np.stack([h, np.roll(h, 37)], axis=1)
        nclick = r.poisson(rate)
        for _ in range(nclick):
            p = int(r.integers(0, blk - 64))
            a = r.exponential(0.12) * 0.5
            ch = int(r.integers(0, 3))
            ln = int(r.integers(6, 24))
            tick = np.exp(-np.arange(ln) / (ln / 4.0)) * a * (1 if r.random() < 0.5 else -1)
            if ch in (0, 2):
                out[p:p + ln, 0] += tick
            if ch in (1, 2):
                out[p:p + ln, 1] += tick
        for _ in range(r.poisson(pops)):
            p = int(r.integers(0, blk - 600))
            ln = 500
            pop = svf(white(ln, r), 900.0, 1.0, "bp") * np.exp(-np.arange(ln) / 90.0) * r.uniform(0.1, 0.35)
            out[p:p + ln] += pop[:, None]
        return out

    def fn(song, a, b):
        n = b - a
        y = np.zeros((n, 2), dtype=np.float64)
        i0, i1 = a // blk, (b - 1) // blk
        for i in range(i0, i1 + 1):
            x = block(i)
            s0 = i * blk
            lo, hi = max(a, s0), min(b, s0 + blk)
            y[lo - a:hi - a] = x[lo - s0:hi - s0]
        y = bp(y.astype(F32), 700.0, 9000.0)
        return (y * level).astype(F32)

    return fn


# ============================================================================ pattern helpers
def trap_hats(rng, base=2, rolls=1, energy=1.0):
    """One bar of trap hi-hats as a 96-step string (24 steps per beat, so 1/8, 1/16, 1/16-triplet,
    1/32 and 1/32-triplet all land exactly). ``base``: 2 = 8ths, 4 = 16ths. ``rolls``: number of beats
    that get a roll. Velocity accents on the beat."""
    steps = ["."] * 96
    beats_roll = set(rng.choice(4, size=min(4, rolls), replace=False).tolist()) if rolls else set()
    for beat in range(4):
        b0 = beat * 24
        if beat in beats_roll:
            kind = int(rng.integers(0, 5))
            if kind == 0:     # 1/16 triplets
                pos = [0, 4, 8, 12, 16, 20]
            elif kind == 1:   # 1/32
                pos = [0, 3, 6, 9, 12, 15, 18, 21]
            elif kind == 2:   # 8th then 1/32 triplet burst
                pos = [0, 12, 14, 16, 18, 20, 22]
            elif kind == 3:   # 16ths then 32nd triplets
                pos = [0, 6, 12, 14, 16, 18, 20, 22]
            else:             # half-beat 1/16-triplet + 1/32
                pos = [0, 4, 8, 12, 15, 18, 21]
            for j, p in enumerate(pos):
                v = 3 + int(6 * (j + 1) / len(pos) * energy)
                steps[b0 + p] = str(min(9, max(2, v)))
        else:
            sub = 24 // base
            for k in range(base):
                steps[b0 + k * sub] = "x" if k == 0 else ("o" if base == 2 else ("g" if k % 2 else "o"))
    return "".join(steps)


def chord_roots(chords):
    return [min(c) for c in chords]


# ============================================================================ melody / harmony helpers
def scale_pcs(key):
    return {(key.root_pc + s) % 12 for s in key.scale}


def voiced(key, degrees, octave=3, size=3, center=None):
    """Voice-led diatonic chords for scale degrees (0-based)."""
    from .theory import voice_lead

    out, prev = [], None
    c0 = center if center is not None else key.root(octave) + 7
    for d in degrees:
        ch = voice_lead(prev, key.chord(d, octave, size), center=c0)
        out.append(ch)
        prev = ch
    return out


def make_melody(rng, key, chords, rhythm, lo, hi, contour=None, start=None, resolve=True, phrase_bars=2,
                extra_pcs=None):
    """Chord-aware hook generator.

    ``rhythm``: ``[(step, len, vel), ...]`` for one *phrase* of ``phrase_bars`` bars (steps from 0).
    ``chords``: one chord (list of MIDI) per bar; the phrase is repeated over all chords
    (call → response), re-pitched to fit each bar's harmony while keeping the same rhythm and contour
    (classic pop sequencing). Strong notes (on beats 1/3 or long) snap to chord tones, the rest move
    stepwise in the scale; the last note of the last phrase resolves to the tonic.
    Returns events ``(step, len, midi, vel)`` with steps from the start of the loop."""
    spcs = set(scale_pcs(key)) | set(extra_pcs or ())
    pool = [m for m in range(lo, hi + 1) if m % 12 in spcs]
    if contour is None:
        contour = [int(rng.choice([-2, -1, -1, 0, 1, 1, 2, 3, -3])) for _ in rhythm]
    nph = max(1, len(chords) // phrase_bars)
    if start is None:
        mid = (lo + hi) / 2
        start = min((m for m in pool if m % 12 in {x % 12 for x in chords[0]}), key=lambda m: abs(m - mid))
    out = []
    for p in range(nph):
        prev = start
        for j, (s, l, v) in enumerate(rhythm):
            ch = chords[(p * phrase_bars + int(s) // 16) % len(chords)]
            cpcs = {x % 12 for x in ch}
            strong = (int(s) % 8 == 0) or l >= 3 or j == 0
            i0 = min(range(len(pool)), key=lambda k: abs(pool[k] - prev))
            tgt = pool[int(np.clip(i0 + (0 if j == 0 else contour[j]), 0, len(pool) - 1))]
            if j == 0:
                tgt = start if p == 0 else tgt
            if strong:
                cands = [m for m in pool if m % 12 in cpcs] or pool
                d = contour[j] if j else 0
                tgt = min(cands, key=lambda m: abs(m - tgt) + (0.4 if (m - prev) * d < 0 else 0))
            if resolve and p == nph - 1 and j == len(rhythm) - 1:
                roots = [m for m in pool if m % 12 == key.root_pc]
                tgt = min(roots, key=lambda m: abs(m - prev))
            out.append((float(s) + 16 * phrase_bars * p, l, int(tgt), v))
            prev = tgt
    return out


def bars_events(events, bars):
    """Split a multi-bar event list into a per-bar notes callable (like ``arrangement.clip``) but
    keeping optional 5th-element flags."""
    from .arrangement import clip

    return clip(events, bars)


# ============================================================================ Hebrew mix-tip helpers
def camelot_neighbors(cam):
    """'8A' → ['7A', '9A', '8B'] (±1 on the wheel + relative major/minor)."""
    num, letter = int(cam[:-1]), cam[-1].upper()
    wrap = lambda x: (x - 1) % 12 + 1  # noqa: E731
    return [f"{wrap(num - 1)}{letter}", f"{wrap(num + 1)}{letter}", f"{num}{'B' if letter == 'A' else 'A'}"]


def partners_he(plan, max_n=3, bpm_tol=0.05):
    """Hebrew phrase naming DJ Lab tracks (from the master plan) that mix harmonically (same Camelot,
    ±1, relative) and within ``bpm_tol`` tempo (half/double aware). Empty string if none."""
    from .render import load_plan

    cam = plan.get("camelot", "")
    ok = set([cam] + camelot_neighbors(cam)) if cam else set()
    bpm = float(plan["bpm"])
    out = []
    for e in load_plan():
        if e["id"] == plan["id"] or e.get("camelot") not in ok:
            continue
        b = float(e["bpm"])
        if not any(abs(b * m - bpm) <= bpm * bpm_tol for m in (1.0, 0.5, 2.0)):
            continue
        same_fam = e.get("family") == plan.get("family")
        out.append((0 if e["camelot"] == cam else 1, 0 if same_fam else 1, abs(b - bpm), e))
    out.sort(key=lambda r: r[:3])
    names = [f"{r[3]['title']} ({r[3]['camelot']}, {int(r[3]['bpm'])} BPM)" for r in out[:max_n]]
    if not names:
        return ""
    return "מתחבר מעולה ל-" + (", ".join(names[:-1]) + " ול-" + names[-1] if len(names) > 1 else names[0])


def wheel_he(cam):
    """'8A' → 'בגלגל הקמלוט הטראק יושב על 8A ומתערבב חלק עם 7A, 9A ו-8B.'"""
    nb = camelot_neighbors(cam)
    return f"בגלגל הקמלוט הטראק יושב על {cam} ומתערבב חלק עם {nb[0]}, {nb[1]} ו-{nb[2]}."
