"""Instrument factories.

Each factory returns a callable ``inst(freq_hz, dur_sec, vel) -> np.ndarray`` (mono ``(n,)`` or
stereo ``(n, 2)``) that renders ONE note: ``dur_sec`` is the gate (key-down) time, the returned
array also contains the release tail. Output peak ≈ ``0.8 * vel`` so instruments are
level-comparable; set the mix level with the layer's ``gain_db``.

Notes layers cache renders per (pitch, length, velocity), so even long tracks only synthesise each
distinct note once.

For monophonic lines with glide/accent (acid, rolling basslines) use :class:`MonoSynth` with a
``MonoLine`` layer.
"""
from __future__ import annotations

import math

import numpy as np

from . import SR
from .dsp import F32, as_stereo, fade, hp, ladder, lp, normalize, pan, saw, sine, square, svf, triangle
from .synth import adsr, chorus, fm, formant_filter, karplus, supersaw, unison, white
from .theory import hz_to_midi

TAU = 2 * math.pi


def _finish(x, vel, gate_n=None, rel_fade=64):
    x = fade(np.asarray(x, dtype=F32), 16, rel_fade)
    return normalize(x, 0.8 * float(vel))


def _n(dur, release, sr=SR):
    gate = max(16, int(dur * sr))
    return gate, gate + int(release * sr)


# ============================================================================ basses
def bass_pluck(cutoff=500.0, env_amt=2200.0, decay=0.12, res=0.35, sub=0.6, drive=1.6, wave="saw",
               release=0.03, sustain=0.35, grit=0.35, sr=SR):
    """Tech-house style plucky bass: saw/square + sine sub through a ladder LP with envelope, plus a
    band-passed saturated 'grit' layer (400 Hz–3 kHz) so the bass reads on small speakers."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        osc = saw(freq, n) if wave == "saw" else square(freq, n, pw=0.42)
        fenv = np.exp(-t / decay)
        cut = cutoff + env_amt * vel * fenv
        x = ladder(osc * 0.8, cut, res, drive)
        if grit:
            g = np.tanh(ladder(osc, cut * 1.5 + 400, 0.2, 1.0) * 3.0)
            x = x + grit * hp(lp(g, 3000.0, 2), 350.0, 2)
        x = x + sub * sine(freq, n)
        env = adsr(n, gate, 0.002, decay * 1.5, sustain, release, sr)
        return _finish(x * env, vel)
    return inst


def sub_bass(harmonics=0.12, drive=1.0, release=0.04, attack=0.004, sr=SR):
    """Clean sine sub with a touch of 2nd/3rd harmonic (audible on small speakers)."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        x = sine(freq, n) + harmonics * sine(2 * freq, n) + harmonics * 0.5 * sine(3 * freq, n)
        if drive > 1.0:
            x = np.tanh(x * drive) / math.tanh(drive)
        env = adsr(n, gate, attack, 0.2, 0.9, release, sr)
        return _finish(x * env, vel)
    return inst


def reese(detune_cents=18.0, cutoff=700.0, res=0.2, drive=2.0, release=0.05, sr=SR):
    """Reese bass: detuned saws, phasey, low-passed and driven (DnB / dark techno)."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        a = saw(freq * 2 ** (detune_cents / 1200), n, 0.0)
        b = saw(freq * 2 ** (-detune_cents / 1200), n, 0.37)
        x = ladder((a + b) * 0.5, cutoff, res, drive) + 0.5 * sine(freq, n)
        env = adsr(n, gate, 0.005, 0.3, 0.85, release, sr)
        return _finish(x * env, vel)
    return inst


def bass_808(decay=1.4, drive=2.2, punch=1.8, release=0.06, sr=SR):
    """808 bass: sine with a fast pitch dip, long decay, saturation (hip-hop/trap)."""
    def inst(freq, dur, vel):
        gate, n = _n(max(dur, decay), release, sr)
        t = np.arange(n) / sr
        f = freq * (1 + (punch - 1) * np.exp(-t / 0.018))
        x = sine(f, n)
        x = np.tanh(x * drive) / math.tanh(drive)
        env = np.exp(-t / (decay / 3.0))
        env[gate:] *= np.exp(-(t[gate:] - t[gate]) / release)
        return _finish(x * env, vel, rel_fade=256)
    return inst


def organ_bass(drawbars=(1.0, 0.6, 0.3, 0.15), release=0.03, sr=SR):
    """Classic 90s 'M1 organ' house bass (additive, percussive)."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        x = sum(a * sine(freq * (i + 1), n) for i, a in enumerate(drawbars))
        click = np.exp(-t / 0.004) * sine(freq * 6, n) * 0.3
        env = adsr(n, gate, 0.002, 0.25, 0.4, release, sr)
        return _finish((x + click) * env, vel)
    return inst


# ============================================================================ chords / keys / pads
def stab(wave="saw", cutoff=900.0, env_amt=3500.0, decay=0.16, res=0.25, detune_cents=9.0,
         release=0.08, amp_decay=0.35, width=0.9, sr=SR):
    """Chord stab voice (call once per chord note): detuned osc pair through a 12 dB SVF with a snappy
    filter envelope. Stereo."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        if wave == "square":
            osc = lambda f, m, ph: square(f, m, ph, 0.45)  # noqa: E731
        else:
            osc = lambda f, m, ph: saw(f, m, ph)  # noqa: E731
        x = unison(osc, freq, n, voices=2, detune_cents=detune_cents, spread=width,
                   rng=np.random.default_rng(int(freq * 7) % 9999))
        cut = cutoff + env_amt * vel * np.exp(-t / decay)
        x = svf(x, cut, 0.7 + res * 4, "lp")
        env = adsr(n, gate, 0.002, amp_decay, 0.0, release, sr, curve=4.0)
        return _finish(x * env[:, None], vel)
    return inst


def dub_chord(cutoff=650.0, env_amt=1200.0, decay=0.22, sr=SR):
    """Deep/dub techno chord voice: soft saw+square, low-passed, short (feed into delay+reverb)."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, 0.06, sr)
        t = np.arange(n) / sr
        x = saw(freq, n) * 0.6 + square(freq * 1.002, n, 0.3, 0.5) * 0.4
        x = ladder(x, cutoff + env_amt * vel * np.exp(-t / decay), 0.45, 1.2)
        env = adsr(n, gate, 0.003, 0.3, 0.0, 0.06, sr, curve=3.0)
        return _finish(pan(x * env, 0.0), vel)
    return inst


def pad(attack=0.8, release=1.5, cutoff=1800.0, detune=0.3, lfo_rate=0.15, warmth=0.5, sr=SR):
    """Lush stereo supersaw pad with slow filter drift and chorus."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        x = supersaw(freq, n, detune=detune, mix=0.6, rng=np.random.default_rng(int(freq) % 997))
        x = x * (1 - warmth * 0.5) + as_stereo(triangle(freq, n)) * warmth * 0.5
        cut = cutoff * (1 + 0.35 * np.sin(TAU * lfo_rate * t + freq))
        x = svf(x, cut, 0.8, "lp")
        env = adsr(n, gate, attack, 0.5, 0.85, release, sr, curve=3.5)
        return _finish(x * env[:, None], vel, rel_fade=512)
    return inst


def pluck(wave="saw", cutoff=600.0, env_amt=5000.0, decay=0.12, release=0.12, width=0.5, sr=SR):
    """Bright synth pluck (trance/melodic techno arps)."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        o = (lambda f, m, ph: saw(f, m, ph)) if wave == "saw" else (lambda f, m, ph: square(f, m, ph, 0.35))
        x = unison(o, freq, n, voices=3, detune_cents=8, spread=width, rng=np.random.default_rng(int(freq) % 991))
        x = svf(x, cutoff + env_amt * vel * np.exp(-t / decay), 1.2, "lp")
        env = adsr(n, gate, 0.001, decay * 3, 0.1, release, sr)
        return _finish(x * env[:, None], vel)
    return inst


def epiano(bright=0.5, release=0.25, sr=SR):
    """FM electric piano (Rhodes/DX-ish): tine (14:1) + body (1:1), tremolo-free."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        body = fm(freq, n, 1.0, 1.2 * vel * bright + 0.3, np.exp(-t / 0.4))
        tine = fm(freq, n, 14.0, 1.0, np.exp(-t / 0.02)) * 0.25 * bright * vel
        x = body + tine
        env = np.exp(-t / (1.2 + 200 / freq)) * adsr(n, gate, 0.001, 1.0, 1.0, release, sr)
        return _finish(pan(x * env, 0.0), vel)
    return inst


def piano(bright=0.6, release=0.3, sr=SR):
    """Additive 'house piano' with slight inharmonicity and hammer noise."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        B = 0.0004
        x = np.zeros(n)
        for k in range(1, 12):
            fk = freq * k * math.sqrt(1 + B * k * k)
            if fk > 16000:
                break
            amp = (1.0 / k ** (1.4 - 0.6 * bright * vel)) * np.exp(-t * (0.6 + 0.35 * k))
            x += amp * np.sin(TAU * fk * t + k)
        ham = svf(white(n, np.random.default_rng(int(freq))), freq * 4, 1.0, "bp") * np.exp(-t / 0.01) * 0.3
        env = adsr(n, gate, 0.001, 2.0, 1.0, release, sr)
        x = (x + ham) * env
        st = np.stack([x, np.roll(x, 8)], axis=1)
        return _finish(st, vel)
    return inst


def organ(drawbars=(0.8, 1.0, 0.6, 0.4, 0.2, 0.1), perc=0.4, release=0.05, sr=SR):
    """Drawbar organ (house organ stabs/chords)."""
    ratios = (0.5, 1, 2, 3, 4, 6)

    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        x = sum(a * sine(freq * r, n) for r, a in zip(ratios, drawbars))
        x += perc * sine(freq * 3, n) * np.exp(-t / 0.06)
        env = adsr(n, gate, 0.003, 0.2, 0.9, release, sr)
        return _finish(chorus(x * env, 5.5, 1.5, 6.0, 0.4), vel)
    return inst


def string_pluck(decay=0.997, bright=0.5, body_hz=None, release=0.08, sr=SR):
    """Karplus-Strong plucked string: oud / guitar / harp / kanun-ish."""
    def inst(freq, dur, vel):
        gate, n = _n(max(dur, 0.6), release, sr)
        x = karplus(freq, n, decay, bright * (0.6 + 0.4 * vel), np.random.default_rng(int(freq * 13)))
        if body_hz:
            x = x + 0.3 * svf(x, body_hz, 2.0, "bp")
        env = adsr(n, gate, 0.0005, 5.0, 1.0, release, sr)
        return _finish(pan(x * env, 0.0), vel)
    return inst


def mallet(kind="marimba", release=0.2, sr=SR):
    """Modal mallet: marimba, kalimba, vibes, steel (inharmonic partial sets)."""
    modes = {
        "marimba": [(1, 1.0, 0.5), (3.93, 0.25, 0.12), (9.54, 0.08, 0.04)],
        "kalimba": [(1, 1.0, 0.8), (5.4, 0.18, 0.07), (13.4, 0.06, 0.02)],
        "vibes": [(1, 1.0, 1.6), (4.0, 0.3, 0.4), (10.0, 0.06, 0.1)],
        "steel": [(1, 1.0, 0.9), (2.0, 0.5, 0.5), (3.0, 0.3, 0.3), (4.1, 0.15, 0.15)],
    }[kind]

    def inst(freq, dur, vel):
        gate, n = _n(max(dur, 0.4), release, sr)
        t = np.arange(n) / sr
        x = np.zeros(n)
        for r, a, d in modes:
            if freq * r < 18000:
                x += a * np.sin(TAU * freq * r * t) * np.exp(-t / d)
        x += 0.1 * svf(white(n, np.random.default_rng(int(freq))), freq * 6, 1.0, "bp") * np.exp(-t / 0.005)
        if kind == "vibes":
            x *= 1 + 0.25 * np.sin(TAU * 5.0 * t)
        env = adsr(n, gate, 0.0005, 5.0, 1.0, release, sr)
        return _finish(pan(x * env, 0.0), vel)
    return inst


def bell(ratio=3.5, index=3.0, decay=1.2, release=0.4, sr=SR):
    """FM bell / glassy keys."""
    def inst(freq, dur, vel):
        gate, n = _n(max(dur, decay), release, sr)
        t = np.arange(n) / sr
        x = fm(freq, n, ratio, index * vel, np.exp(-t / (decay / 2)))
        env = np.exp(-t / decay) * adsr(n, gate, 0.001, 5, 1, release, sr)
        return _finish(pan(x * env, 0.0), vel)
    return inst


def lead_saw(detune=0.35, cutoff=4500.0, res=0.2, attack=0.005, release=0.25, sr=SR):
    """Big supersaw lead (trance / big room)."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        x = supersaw(freq, n, detune=detune, mix=0.8, rng=np.random.default_rng(int(freq) % 977))
        x = x + as_stereo(square(freq / 2, n, pw=0.5)) * 0.25
        x = svf(x, cutoff * (0.6 + 0.4 * vel), 0.7 + res * 3, "lp")
        env = adsr(n, gate, attack, 0.3, 0.8, release, sr)
        return _finish(x * env[:, None], vel, rel_fade=256)
    return inst


def brass(cutoff=2500.0, release=0.12, sr=SR):
    """Synth brass: saws with a slow filter swell."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        x = unison(lambda f, m, ph: saw(f, m, ph), freq, n, 3, 10, 0.5, np.random.default_rng(int(freq)))
        cut = 300 + cutoff * vel * (1 - np.exp(-t / 0.08))
        x = svf(x, cut, 1.0, "lp")
        env = adsr(n, gate, 0.03, 0.2, 0.85, release, sr)
        return _finish(x * env[:, None], vel)
    return inst


def vocal_chop(vowel="a", vowel_to=None, shift=1.12, vibrato=0.25, breath=0.08, scoop=-1.0,
               release=0.06, sr=SR):
    """Vocal-like formant chop: glottal saw (+breath) through a formant bank. ``scoop``: semitones
    the pitch slides up from at the start (classic chopped vocal feel)."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        f = freq * 2 ** ((scoop * np.exp(-t / 0.03) + vibrato * 0.2 * np.sin(TAU * 5.5 * t) * (1 - np.exp(-t / 0.2))) / 12)
        src = saw(f, n) * 0.8 + square(f, n, 0.0, 0.2) * 0.2
        src = src + breath * white(n, np.random.default_rng(int(freq)))
        x = formant_filter(src, vowel, vowel_to, shift, sr)
        x = hp(x, 180.0)
        env = adsr(n, gate, 0.006, 0.15, 0.75, release, sr)
        return _finish(x * env, vel)
    return inst


def seq_blip(wave="square", cutoff=1400.0, env_amt=2500.0, decay=0.05, res=0.55, release=0.02, sr=SR):
    """Short hypnotic sequence voice (techno 16ths)."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        osc = square(freq, n, pw=0.3) if wave == "square" else saw(freq, n)
        x = ladder(osc, cutoff + env_amt * vel * np.exp(-t / decay), res, 1.5)
        env = adsr(n, gate, 0.001, decay * 2, 0.2, release, sr)
        return _finish(x * env, vel)
    return inst


def fm_stab(ratio=2.0, index=4.0, decay=0.12, release=0.05, sr=SR):
    """Metallic/percussive FM stab (techno, industrial)."""
    def inst(freq, dur, vel):
        gate, n = _n(dur, release, sr)
        t = np.arange(n) / sr
        x = fm(freq, n, ratio, index * vel, np.exp(-t / decay))
        env = adsr(n, gate, 0.001, decay * 2, 0.0, release, sr)
        return _finish(x * env, vel)
    return inst


def log_drum_inst(decay=0.45, knock=0.6, bend=5.0, sr=SR):
    """Pitched amapiano log drum as a Notes instrument."""
    from .drums import log_drum

    def inst(freq, dur, vel):
        return normalize(log_drum(freq, decay, knock, bend, np.random.default_rng(int(freq * 3)), sr), 0.8 * vel)
    return inst


def sampler(one_shot, root_hz=261.63, sr=SR):
    """Repitch a one-shot by resampling (classic sampler; duration follows pitch)."""
    from scipy.signal import resample

    src = np.asarray(one_shot, dtype=F32)

    def inst(freq, dur, vel):
        ratio = freq / root_hz
        m = max(16, int(src.shape[0] / ratio))
        y = resample(src, m, axis=0).astype(F32)
        gate = int(dur * sr) + int(0.05 * sr)
        return normalize(fade(y[:gate], 0, 128), 0.8 * vel)
    return inst


# ============================================================================ monophonic line synth
class MonoSynth:
    """Monophonic synth for acid lines and rolling basslines, rendered as one continuous voice so
    glides and filter envelopes behave like hardware.

    Events: list of ``(start_sample, gate_samples, midi, vel, slide, accent)``. ``slide`` means
    *this* note glides into the next one (TB-303 semantics: the gate stays open)."""

    def __init__(self, wave="saw", cutoff=400.0, res=0.75, env_mod=2.2, decay=0.18, accent=0.6,
                 glide_ms=55.0, drive=2.0, sub=0.0, amp_decay=None, sustain=0.85, release_ms=8.0,
                 dist=0.0, sr=SR):
        self.__dict__.update(locals())
        del self.__dict__["self"]

    def render(self, events, n, cutoff_curve=None, res_curve=None, env_curve=None):
        sr = self.sr
        events = sorted(events, key=lambda e: e[0])
        target = np.zeros(n)
        gate = np.zeros(n, dtype=F32)
        fenv = np.zeros(n)
        aenv = np.zeros(n)
        acc = np.zeros(n)
        if not events:
            return np.zeros(n, dtype=F32)
        prev_slide = False
        prev_hz = None
        rel = max(1, int(self.release_ms * 1e-3 * sr))
        gl = max(1, int(self.glide_ms * 1e-3 * sr))
        for i, (s, g, midi, vel, slide, accent) in enumerate(events):
            s = int(s)
            if s >= n:
                break
            nxt = int(events[i + 1][0]) if i + 1 < len(events) else n
            end = min(n, nxt)
            hz = 440.0 * 2 ** ((midi - 69) / 12)
            seg = end - s
            if seg <= 0:
                continue
            k = np.arange(seg)
            if prev_slide and prev_hz is not None:
                m = min(gl, seg)
                lf = np.full(seg, math.log(hz))
                lf[:m] = math.log(prev_hz) + (math.log(hz) - math.log(prev_hz)) * (k[:m] / m)
                target[s:end] = np.exp(lf)
            else:
                target[s:end] = hz
            g_end = end if slide else min(end, s + int(g))
            gate[s:g_end] = 1.0
            if not prev_slide:
                tt = k / sr
                fenv[s:end] = np.exp(-tt / (self.decay * (0.6 if accent else 1.0)))
                ad = self.amp_decay or self.decay * 3
                aenv[s:end] = self.sustain + (1 - self.sustain) * np.exp(-tt / ad)
                acc[s:end] = 1.0 if accent else 0.0
                aenv[s:end] *= vel
            else:
                fenv[s:end] = fenv[s - 1] if s > 0 else 0.0
                aenv[s:end] = aenv[s - 1] if s > 0 else vel
                acc[s:end] = acc[s - 1] if s > 0 else 0.0
            prev_slide = bool(slide)
            prev_hz = hz
        # smooth gate (≈3 ms attack/release → no clicks, sample-accurate note ends)
        from scipy.signal import lfilter
        a = math.exp(-1.0 / max(1.0, rel * 0.4))
        g_s = lfilter([1 - a], [1, -a], gate).astype(F32)
        f = target
        f[f <= 0] = 55.0
        if self.wave == "square":
            osc = square(f, n, pw=0.5)
        else:
            osc = saw(f, n)
        if self.sub:
            osc = osc + self.sub * sine(f / 2, n)
        cut0 = np.asarray(cutoff_curve if cutoff_curve is not None else self.cutoff, dtype=np.float64)
        envm = np.asarray(env_curve if env_curve is not None else self.env_mod, dtype=np.float64)
        cut = cut0 * 2 ** (fenv * (envm + acc * self.accent * 2.0))
        res = float(np.mean(res_curve)) if res_curve is not None else self.res
        y = ladder(osc * 0.7, np.clip(cut, 30, 16000), res, self.drive)
        y = y * aenv * (1 + acc * self.accent * 0.5) * g_s
        if self.dist:
            y = np.tanh(y * (1 + self.dist * 4)) / math.tanh(1 + self.dist * 4)
        y = hp(y, 35.0, 2)
        return normalize(y.astype(F32), 0.8)


__all__ = [n for n in dir() if not n.startswith("_")] + ["hz_to_midi", "lp", "chorus"]
