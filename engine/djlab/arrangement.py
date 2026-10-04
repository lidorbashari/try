"""Song model: sections, layers (tracks), patterns, automation, cues.

A recipe builds a :class:`Song`, defines its sections (8-bar aligned), adds layers to buses and
returns it. The mixer/master turn it into audio; :meth:`Song.cues` & co. produce the metadata.

Layer types
-----------
* :class:`Hits`     – one-shot samples triggered by step patterns (``"x...x...x...x..."``)
* :class:`Notes`    – polyphonic instrument playing note events (chords, stabs, pads, leads)
* :class:`MonoLine` – continuous monophonic synth (acid / rolling bass with glide & accents)
* :class:`Audio`    – free placement of rendered audio (risers, impacts, crashes, vocal phrases)
* :class:`Custom`   – any callable that renders a sample range

Every layer accepts ``when=`` (section names/kinds, or ``callable(ctx) -> bool``) and automation
via :meth:`Layer.automate` (``gain_db``, ``lp``, ``hp``, ``pan``, ``send:<name>`` and layer-
specific params like ``cutoff`` for MonoLine).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from . import SR
from .dsp import F32, as_stereo, mix_into, pan as _pan
from .grid import Grid
from .theory import Key, midi_to_hz

# ============================================================================ sections
SECTION_KINDS = ("intro", "groove", "build", "breakdown", "drop", "bridge", "verse", "chorus", "outro")


@dataclass
class Section:
    name: str
    kind: str
    bars: int
    energy: int = 5
    start_bar: int = 0

    @property
    def end_bar(self) -> int:
        return self.start_bar + self.bars


def fit_sections(template, total_bars: int) -> list[Section]:
    """Build sections from a template and stretch/shrink the ``flex`` ones (in 8-bar steps) so the
    total equals ``total_bars``.

    template rows: ``(name, kind, bars, energy)`` or ``(name, kind, bars, energy, flex)`` where
    ``flex`` is a priority weight (0 = fixed; higher = stretched first)."""
    rows = []
    for r in template:
        name, kind, bars, energy = r[:4]
        flex = r[4] if len(r) > 4 else (1 if kind in ("groove", "drop") else 0)
        rows.append([name, kind, int(bars), int(energy), flex])
    diff = total_bars - sum(r[2] for r in rows)
    flex_rows = sorted([r for r in rows if r[4]], key=lambda r: -r[4]) or rows
    i = 0
    guard = 0
    while diff != 0 and guard < 500:
        r = flex_rows[i % len(flex_rows)]
        if diff > 0:
            r[2] += 8
            diff -= 8
        elif r[2] > 8:
            r[2] -= 8
            diff += 8
        i += 1
        guard += 1
    out, bar = [], 0
    for name, kind, bars, energy, _ in rows:
        out.append(Section(name, kind, bars, energy, bar))
        bar += bars
    return out


# ============================================================================ per-bar context
class Ctx:
    """What a pattern callable receives for each bar.

    Attributes: ``bar`` (absolute, 0-based), ``section``, ``i`` (bar in section), ``song``,
    ``rng`` (deterministic per layer+bar). Helpers below."""

    __slots__ = ("bar", "section", "i", "song", "rng", "layer")

    def __init__(self, song, bar, layer=None):
        self.song = song
        self.bar = bar
        self.section = song.section_at(bar)
        self.i = bar - self.section.start_bar
        self.layer = layer
        seed = (song.seed * 1_000_003 + bar * 7919 + (hash_name(layer.name) if layer else 0)) % (2 ** 32)
        self.rng = np.random.default_rng(seed)

    # --- section info
    @property
    def name(self):
        return self.section.name

    @property
    def kind(self):
        return self.section.kind

    @property
    def energy(self):
        return self.section.energy

    @property
    def bars_left(self) -> int:
        """Bars remaining in the section including this one (1 = last bar)."""
        return self.section.bars - self.i

    @property
    def phrase_bar(self) -> int:
        """Position inside the 8-bar phrase (0..7)."""
        return self.i % 8

    @property
    def phrase(self) -> int:
        """Index of the 8-bar phrase inside the section."""
        return self.i // 8

    @property
    def first(self) -> bool:
        return self.i == 0

    @property
    def last(self) -> bool:
        return self.i == self.section.bars - 1

    @property
    def phrase_end(self) -> bool:
        return self.i % 8 == 7

    def every(self, n: int, offset: int = 0) -> bool:
        """True on the last bar of every ``n``-bar block (fills every 4/8/16 bars)."""
        return (self.i - offset) % n == n - 1

    @property
    def next(self):
        return self.song.section_after(self.section)

    @property
    def prev(self):
        return self.song.section_before(self.section)

    def before(self, kind: str, bars: int = 1) -> bool:
        """True if this bar is within the last ``bars`` bars before a section of ``kind``
        (e.g. ``ctx.before('drop')`` → drop the kick for the bar before the drop)."""
        nx = self.next
        return nx is not None and (nx.kind == kind or nx.name == kind) and self.bars_left <= bars

    def progress(self) -> float:
        """0..1 progress through the section (for builds)."""
        return self.i / max(1, self.section.bars - 1)

    def is_(self, *names) -> bool:
        return self.section.name in names or self.section.kind in names


def hash_name(s: str) -> int:
    h = 2166136261
    for ch in s.encode():
        h = ((h ^ ch) * 16777619) % (2 ** 32)
    return h


# ============================================================================ step patterns
_VEL = {"X": 1.0, "x": 0.82, "o": 0.6, "g": 0.38}


def parse_pattern(p: str) -> tuple[int, list[tuple[float, float]]]:
    """Step string → (steps, [(step, vel), ...]).

    Characters: ``X`` 1.0 (accent) · ``x`` 0.82 · ``o`` 0.6 · ``g`` 0.38 (ghost) · ``1``–``9``
    velocity 0.1–0.9 · ``r`` roll (two 32nds, 0.7) · ``. - _`` rest. Spaces and ``|`` are ignored.
    Length = steps per bar (16 = 16ths, 12 = triplet 8ths, 32 = 32nds, 8 = 8ths)."""
    s = p.replace(" ", "").replace("|", "")
    hits = []
    for i, ch in enumerate(s):
        if ch in _VEL:
            hits.append((float(i), _VEL[ch]))
        elif ch.isdigit() and ch != "0":
            hits.append((float(i), int(ch) / 10.0))
        elif ch == "r":
            hits.append((float(i), 0.7))
            hits.append((i + 0.5, 0.55))
    return len(s), hits


def euclid(k: int, n: int = 16, rotate: int = 0, hit: str = "x") -> str:
    """Euclidean rhythm as a step string, e.g. ``euclid(3, 8)`` → ``"x..x..x."``."""
    pattern = ["." for _ in range(n)]
    for i in range(n):
        if (i * k) % n < k:
            pattern[i] = hit
    pattern = pattern[-rotate:] + pattern[:-rotate] if rotate else pattern
    return "".join(pattern)


def _resolve_pattern(pattern, ctx):
    p = pattern(ctx) if callable(pattern) else pattern
    if isinstance(p, dict):
        p = p.get(ctx.section.name, p.get(ctx.section.kind, p.get("*")))
    if isinstance(p, (list, tuple)) and p and isinstance(p[0], str):
        p = p[ctx.i % len(p)]
    return p


# ============================================================================ layers
class Layer:
    """Base class. Subclasses implement :meth:`render_dry` returning a stereo buffer for samples
    ``[a, b)`` of the song (or None if silent)."""

    def __init__(self, name: str, bus: str = "music", gain_db: float = 0.0, pan: float = 0.0,
                 when=None, sends: dict | None = None, sidechain: float = 0.0, sc_release_ms: float | None = None,
                 lp: float | None = None, hp: float | None = None, res: float = 0.707,
                 fx: list | None = None, width: float | None = None, mute: bool = False):
        self.name = name
        self.bus = bus
        self.gain_db = gain_db
        self.pan = pan
        self.when = when
        self.sends = dict(sends or {})
        self.sidechain = sidechain
        self.sc_release_ms = sc_release_ms
        self.lp = lp
        self.hp = hp
        self.res = res
        self.fx = list(fx or [])
        self.width = width
        self.mute = mute
        self.auto: dict[str, tuple[list, str]] = {}

    # ---- activity
    def active(self, ctx: Ctx) -> bool:
        w = self.when
        if w is None:
            return True
        if callable(w):
            return bool(w(ctx))
        if isinstance(w, str):
            w = [w]
        return ctx.section.name in w or ctx.section.kind in w

    # ---- automation
    def automate(self, param: str, points, interp: str | None = None):
        """``points``: [(bar, value), ...] (bars may be fractional). Params: ``gain_db``, ``lp``,
        ``hp`` (Hz, log interpolation), ``pan``, ``send:<return>``, or instrument params
        (``cutoff``, ``env_mod`` for MonoLine). Before the first point the first value holds, after
        the last point the last value holds."""
        pts = sorted((float(b), float(v)) for b, v in points)
        if interp is None:
            interp = "log" if param in ("lp", "hp", "cutoff") else "linear"
        self.auto[param] = (pts, interp)
        return self

    def curve(self, song, param: str, a: int, b: int, default=None):
        """Per-sample curve for ``param`` over [a, b) or ``default`` (scalar) if not automated."""
        if param not in self.auto:
            return default
        pts, interp = self.auto[param]
        xs = np.array([song.grid.bar_sample(p[0]) for p in pts], dtype=np.float64)
        ys = np.array([p[1] for p in pts], dtype=np.float64)
        idx = np.arange(a, b, dtype=np.float64)
        if interp == "log":
            return np.exp(np.interp(idx, xs, np.log(np.maximum(ys, 1e-6))))
        return np.interp(idx, xs, ys)

    def render_dry(self, song, a: int, b: int):  # pragma: no cover - abstract
        raise NotImplementedError

    def bars_in(self, song, a, b, lookback=0):
        g = song.grid
        b0 = max(0, int(math.floor(a / (g.bar_sec * g.sr))) - lookback)
        b1 = min(song.total_bars, int(math.ceil(b / (g.bar_sec * g.sr))) + 1)
        return range(b0, b1)


class Hits(Layer):
    """One-shot sample(s) triggered by step patterns.

    ``sample``: array or list of arrays (round-robin variants, picked deterministically at random).
    ``pattern``: step string | list of strings (cycled per bar) | dict {section name/kind: pattern,
    "*": default} | ``callable(ctx) -> any of these or None``.
    ``humanize``: velocity jitter (fraction). ``timing_ms``: random timing jitter (± ms).
    ``sc_source=True`` makes this layer's hits drive all sidechain ducking (the kick).
    """

    def __init__(self, name, sample, pattern, bus="drums", swing=None, humanize=0.06, timing_ms=0.0,
                 sc_source=False, vel_curve=1.0, **kw):
        super().__init__(name, bus=bus, **kw)
        self.samples = sample if isinstance(sample, (list, tuple)) else [sample]
        self.samples = [np.asarray(s, dtype=F32) for s in self.samples]
        self.pattern = pattern
        self.swing = swing
        self.humanize = humanize
        self.timing_ms = timing_ms
        self.sc_source = sc_source
        self.vel_curve = vel_curve

    def events(self, song, a, b):
        """[(sample_pos_abs, vel, variant_idx)] for bars overlapping [a, b)."""
        ev = []
        g = song.grid
        sw = song.swing if self.swing is None else self.swing
        for bar in self.bars_in(song, a, b, lookback=1):
            ctx = Ctx(song, bar, self)
            if not self.active(ctx):
                continue
            p = _resolve_pattern(self.pattern, ctx)
            if not p:
                continue
            steps, hits = parse_pattern(p)
            for st, v in hits:
                pos = g.step_sample(bar, st, steps, sw)
                if self.timing_ms:
                    pos += int(ctx.rng.uniform(-1, 1) * self.timing_ms * 1e-3 * g.sr)
                vel = v * (1 + self.humanize * ctx.rng.uniform(-1, 1))
                ev.append((max(0, pos), float(np.clip(vel, 0.0, 1.2)) ** self.vel_curve,
                           int(ctx.rng.integers(len(self.samples)))))
        return ev

    def render_dry(self, song, a, b):
        n = b - a
        buf = np.zeros((n, 2), dtype=F32)
        st = [as_stereo(s) for s in self.samples]
        any_hit = False
        for pos, vel, vi in self.events(song, a, b):
            if pos >= b or pos + st[vi].shape[0] <= a:
                continue
            mix_into(buf, st[vi], pos - a, vel)
            any_hit = True
        return buf if any_hit else None


NoteEv = tuple  # (step, length_steps, midi | [midis], vel[, flags])


def _resolve_notes(notes, ctx):
    ev = notes(ctx) if callable(notes) else notes
    if isinstance(ev, dict):
        ev = ev.get(ctx.section.name, ev.get(ctx.section.kind, ev.get("*")))
    return ev or []


class Notes(Layer):
    """Polyphonic instrument. ``notes``: list of note tuples ``(step, length_steps, midi_or_list,
    vel)`` for one bar, or ``callable(ctx) -> list`` (steps are 16ths from the bar start, may be
    fractional / exceed 16 for notes crossing the bar line). Use :func:`clip` for multi-bar
    sequences. ``transpose`` in semitones."""

    def __init__(self, name, instrument: Callable, notes, bus="music", transpose=0, swing=None,
                 humanize=0.05, timing_ms=0.0, **kw):
        super().__init__(name, bus=bus, **kw)
        self.instrument = instrument
        self.notes = notes
        self.transpose = transpose
        self.swing = swing
        self.humanize = humanize
        self.timing_ms = timing_ms
        self._cache: dict = {}

    def note_events(self, song, a, b, lookback=8):
        g = song.grid
        sw = song.swing if self.swing is None else self.swing
        out = []
        for bar in self.bars_in(song, a, b, lookback=lookback):
            ctx = Ctx(song, bar, self)
            if not self.active(ctx):
                continue
            for ev in _resolve_notes(self.notes, ctx):
                st, ln, pitch, vel = ev[:4]
                flags = ev[4] if len(ev) > 4 else ""
                pos = g.step_sample(bar, st, 16, sw)
                end = g.step_sample(bar, st + ln, 16, None)
                if self.timing_ms:
                    pos += int(ctx.rng.uniform(-1, 1) * self.timing_ms * 1e-3 * g.sr)
                v = float(np.clip(vel * (1 + self.humanize * ctx.rng.uniform(-1, 1)), 0.05, 1.2))
                pitches = pitch if isinstance(pitch, (list, tuple)) else [pitch]
                for p in pitches:
                    out.append((max(0, pos), max(32, end - pos), p + self.transpose, v, flags))
        return out

    def _render_note(self, song, midi, length, vel):
        key = (round(float(midi), 3), int(length // 32), round(vel * 24) / 24)
        x = self._cache.get(key)
        if x is None:
            x = as_stereo(self.instrument(float(midi_to_hz(midi)), length / song.sr, key[2]))
            self._cache[key] = x
        return x

    def render_dry(self, song, a, b):
        n = b - a
        buf = np.zeros((n, 2), dtype=F32)
        hit = False
        for pos, length, midi, vel, _ in self.note_events(song, a, b):
            if pos >= b:
                continue
            x = self._render_note(song, midi, length, vel)
            if pos + x.shape[0] <= a:
                continue
            mix_into(buf, x, pos - a)
            hit = True
        return buf if hit else None


class MonoLine(Notes):
    """Monophonic continuous synth line (see :class:`djlab.instruments.MonoSynth`). Note tuples may
    carry flags as 5th element: ``"s"`` = slide into next note, ``"a"`` = accent. Automatable params:
    ``cutoff`` (Hz), ``env_mod`` (octaves)."""

    def __init__(self, name, synth, notes, bus="bass", **kw):
        super().__init__(name, instrument=None, notes=notes, bus=bus, **kw)
        self.synth = synth

    def render_dry(self, song, a, b):
        evs = self.note_events(song, a, b, lookback=1)
        if not evs:
            return None
        ev2 = [(pos - a, length, midi, vel, "s" in fl, "a" in fl) for pos, length, midi, vel, fl in evs]
        n = b - a
        cut = self.curve(song, "cutoff", a, b, None)
        env = self.curve(song, "env_mod", a, b, None)
        y = self.synth.render([e for e in ev2 if e[0] + e[1] > 0], n, cutoff_curve=cut, env_curve=env)
        return as_stereo(y)


class Audio(Layer):
    """Free placements of pre-rendered audio. ``align='end'`` makes the audio END exactly at the
    position (risers into drops); ``align='start'`` starts it there."""

    def __init__(self, name, bus="fx", **kw):
        super().__init__(name, bus=bus, **kw)
        self.items: list[tuple[float, float, np.ndarray, str, float]] = []

    def add(self, audio, bar: float, beat: float = 0.0, align: str = "start", gain_db: float = 0.0):
        self.items.append((float(bar), float(beat), as_stereo(audio), align, gain_db))
        return self

    def render_dry(self, song, a, b):
        n = b - a
        buf = np.zeros((n, 2), dtype=F32)
        hit = False
        for bar, beat, x, align, gdb in self.items:
            pos = song.grid.sample(bar, beat)
            if align == "end":
                pos -= x.shape[0]
            if pos >= b or pos + x.shape[0] <= a:
                continue
            mix_into(buf, x, pos - a, 10 ** (gdb / 20))
            hit = True
        return buf if hit else None


class Custom(Layer):
    """``fn(song, a, b) -> (b-a, 2) array`` – anything (drones, granular textures, resampled buses)."""

    def __init__(self, name, fn, bus="music", **kw):
        super().__init__(name, bus=bus, **kw)
        self.fn = fn

    def render_dry(self, song, a, b):
        y = self.fn(song, a, b)
        return None if y is None else as_stereo(y)


def clip(events: list, bars: int):
    """Turn a multi-bar sequence (steps counted from the clip start, 16 per bar) into a per-bar
    notes callable that loops every ``bars`` bars (relative to the section start)."""
    def fn(ctx):
        off = (ctx.i % bars) * 16
        out = []
        for ev in events:
            if off <= ev[0] < off + 16:
                out.append((ev[0] - off,) + tuple(ev[1:]))
        return out
    return fn


# ============================================================================ song
@dataclass
class MasterSettings:
    lufs: float = -9.0
    ceiling_dbtp: float = -1.6
    mono_below: float = 110.0
    low_shelf_db: float = 0.0
    low_shelf_hz: float = 80.0
    high_shelf_db: float = 0.0
    high_shelf_hz: float = 11000.0
    mud_cut_db: float = 0.0  # peak cut at ~300 Hz
    glue_ratio: float = 2.0
    glue_gr_db: float = 2.0  # approximate glue gain reduction target
    clip_threshold: float = 0.72
    limiter_release_ms: float = 90.0
    width: float = 1.0


class Song:
    """A track under construction. ``plan`` = entry from ``tracklist.plan.json``."""

    def __init__(self, plan: dict, rng: np.random.Generator | None = None, lufs: float | None = None,
                 swing: float = 50.0, sr: int = SR, scale: str | None = None):
        from .mixer import default_buses, default_returns

        self.plan = dict(plan)
        self.sr = sr
        self.bpm = float(plan["bpm"])
        self.seed = int(plan.get("seed", 0))
        self.rng = rng if rng is not None else np.random.default_rng(self.seed)
        self.swing = swing
        self.grid = Grid(self.bpm, sr, 4, 4, swing)
        self.key = Key(plan.get("key", "A minor"), scale)
        self.layers: list[Layer] = []
        self.sections: list[Section] = []
        self.buses = default_buses()
        self.returns = default_returns(self.bpm)
        self.master = MasterSettings(lufs=lufs if lufs is not None else float(plan.get("lufs", -9.0)))
        self.mix_in_bar: int | None = None
        self.description_he: str = ""
        self.mix_tips_he: str = ""
        self.instruments: list[str] = []

    # ---- structure
    @property
    def total_bars(self) -> int:
        return sum(s.bars for s in self.sections)

    def target_bars(self, phrase: int = 8) -> int:
        return self.grid.bars_for_minutes(float(self.plan.get("target_minutes", 4.0)), phrase)

    def arrange(self, template, total_bars: int | None = None) -> list[Section]:
        """Set sections from a template (see :func:`fit_sections`), fitted to the plan length."""
        self.sections = fit_sections(template, total_bars or self.target_bars())
        assert all(s.start_bar % 8 == 0 for s in self.sections), "sections must start on 8-bar phrases"
        return self.sections

    def section_at(self, bar: int) -> Section:
        for s in self.sections:
            if s.start_bar <= bar < s.end_bar:
                return s
        return self.sections[-1]

    def section_after(self, sec: Section):
        i = self.sections.index(sec)
        return self.sections[i + 1] if i + 1 < len(self.sections) else None

    def section_before(self, sec: Section):
        i = self.sections.index(sec)
        return self.sections[i - 1] if i > 0 else None

    def find(self, kind_or_name: str, nth: int = 0):
        hits = [s for s in self.sections if s.kind == kind_or_name or s.name == kind_or_name]
        return hits[nth] if nth < len(hits) else None

    def bar(self, kind_or_name: str, nth: int = 0) -> int | None:
        s = self.find(kind_or_name, nth)
        return s.start_bar if s else None

    def ctx(self, bar: int, layer=None) -> Ctx:
        return Ctx(self, bar, layer)

    def section_points(self, values: dict, default: float, ramp_bars: float = 0.0):
        """Automation points from per-section values: ``{"Breakdown": -6, "drop": 0}`` (names or
        kinds). With ``ramp_bars`` > 0 each change ramps over the bars before the section start."""
        pts = []
        for s in self.sections:
            v = values.get(s.name, values.get(s.kind, default))
            if ramp_bars and pts:
                pts.append((s.start_bar - ramp_bars, pts[-1][1]))
            elif pts:
                pts.append((s.start_bar - 1e-3, pts[-1][1]))
            pts.append((s.start_bar, v))
        pts.append((self.total_bars, pts[-1][1]))
        return pts

    # ---- layers
    def add(self, layer: Layer) -> Layer:
        if any(l.name == layer.name for l in self.layers):
            raise ValueError(f"duplicate layer name {layer.name!r}")
        self.layers.append(layer)
        return layer

    def hits(self, name, sample, pattern, **kw) -> Hits:
        return self.add(Hits(name, sample, pattern, **kw))

    def notes(self, name, instrument, notes, **kw) -> Notes:
        return self.add(Notes(name, instrument, notes, **kw))

    def line(self, name, synth, notes, **kw) -> MonoLine:
        return self.add(MonoLine(name, synth, notes, **kw))

    def audio(self, name, bus="fx", **kw) -> Audio:
        return self.add(Audio(name, bus=bus, **kw))

    def custom(self, name, fn, **kw) -> Custom:
        return self.add(Custom(name, fn, **kw))

    def layer(self, name) -> Layer:
        for l in self.layers:
            if l.name == name:
                return l
        raise KeyError(name)

    # ---- metadata
    def sections_meta(self) -> list[dict]:
        return [{"name": s.name, "start_bar": s.start_bar, "bars": s.bars,
                 "start_sec": round(self.grid.bar_time(s.start_bar), 3), "energy": s.energy}
                for s in self.sections]

    def cues(self) -> list[dict]:
        """Hot cues A–H per SCHEMA (only those that exist)."""
        g = self.grid
        intro_end = self.sections[1].start_bar if len(self.sections) > 1 else 0
        mix_in = self.mix_in_bar if self.mix_in_bar is not None else intro_end
        spec = [
            ("A", "Intro", 0, "#28E214"),
            ("B", "Mix-In", mix_in, "#10B1E6"),
            ("C", "Breakdown", self.bar("breakdown", 0), "#E0641B"),
            ("D", "Drop", self.bar("drop", 0), "#E62828"),
            ("E", "Breakdown 2", self.bar("breakdown", 1), "#B4BE04"),
            ("F", "Drop 2", self.bar("drop", 1), "#DE44CF"),
            ("G", "Outro", self.bar("outro", 0), "#305AFF"),
            ("H", "Last 16", max(0, self.total_bars - 16), "#8A2BE2"),
        ]
        out = []
        for slot, name, bar, color in spec:
            if bar is None:
                continue
            out.append({"slot": slot, "name": name, "bar": int(bar), "sec": round(g.bar_time(bar), 3),
                        "color": color, "type": "hot"})
        return out

    def memory_cues(self) -> list[dict]:
        return [{"name": s.name, "bar": s.start_bar, "sec": round(self.grid.bar_time(s.start_bar), 3)}
                for s in self.sections]

    def auto_mix_tips_he(self) -> str:
        """Generic Hebrew mixing tip derived from the structure (recipes may override)."""
        intro = self.sections[0]
        outro = self.find("outro")
        parts = [f"אינטרו של {intro.bars} תיבות להכנסה נקייה"]
        if self.mix_in_bar is not None:
            parts.append(f"הבאס נכנס בתיבה {self.mix_in_bar + 1} (Hot Cue B)")
        bd = self.find("breakdown")
        if bd:
            parts.append(f"ברייקדאון בתיבה {bd.start_bar + 1}")
        dr = self.find("drop")
        if dr:
            parts.append(f"דרופ בתיבה {dr.start_bar + 1}")
        if outro:
            parts.append(f"אאוטרו של {outro.bars} תיבות מתיבה {outro.start_bar + 1} — מושלם למיקס החוצה")
        return "טיפ ערבוב: " + ", ".join(parts) + "."

    # ---- rendering
    def render(self, start_bar: int = 0, end_bar: int | None = None):
        """Mix (pre-master) for bars [start_bar, end_bar). Returns float32 stereo."""
        from .mixer import mix

        end_bar = self.total_bars if end_bar is None else end_bar
        return mix(self, self.grid.bar_sample(start_bar), self.grid.bar_sample(end_bar))
