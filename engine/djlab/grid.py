"""Sample-exact tempo grid.

Every event position is computed from float time and rounded *per event* (never by accumulating
sample counts), so there is no drift even after thousands of bars. Bar/beat/step indices are
0-based: ``bar=0, beat=0, step=0`` is sample 0 (the first downbeat).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import SR


@dataclass(frozen=True)
class Grid:
    bpm: float
    sr: int = SR
    beats_per_bar: int = 4
    steps_per_beat: int = 4  # 16th notes
    swing: float = 50.0  # MPC-style percentage: 50 = straight, 66.7 = triplet shuffle

    # ---- durations (float seconds / samples) ----
    @property
    def beat_sec(self) -> float:
        return 60.0 / float(self.bpm)

    @property
    def bar_sec(self) -> float:
        return self.beat_sec * self.beats_per_bar

    @property
    def step_sec(self) -> float:
        return self.beat_sec / self.steps_per_beat

    @property
    def steps_per_bar(self) -> int:
        return self.beats_per_bar * self.steps_per_beat

    def beats_to_sec(self, beats: float) -> float:
        return beats * self.beat_sec

    def ms_to_samples(self, ms: float) -> int:
        return int(round(ms * 1e-3 * self.sr))

    # ---- positions ----
    def swing_offset_steps(self, step_index: int, swing: float | None = None) -> float:
        """Delay (in 16th steps) applied to an odd 16th for the given swing percentage."""
        sw = self.swing if swing is None else swing
        if step_index % 2 == 1 and sw != 50.0:
            return 2.0 * sw / 100.0 - 1.0
        return 0.0

    def time(self, bar: float, beat: float = 0.0, step: float = 0.0, swing: float | None = None) -> float:
        """Seconds from sample 0 for a (bar, beat, 16th-step) position. Swing applies to odd 16ths
        when ``step`` (counted from the bar start or beat start) is an integer."""
        total_steps = (bar * self.beats_per_bar + beat) * self.steps_per_beat + step
        if float(total_steps).is_integer():
            total_steps += self.swing_offset_steps(int(total_steps), swing)
        return total_steps * self.step_sec

    def sample(self, bar: float, beat: float = 0.0, step: float = 0.0, swing: float | None = None) -> int:
        return int(round(self.time(bar, beat, step, swing) * self.sr))

    def bar_sample(self, bar: float) -> int:
        return int(round(bar * self.bar_sec * self.sr))

    def bar_time(self, bar: float) -> float:
        return bar * self.bar_sec

    def step_sample(self, bar: int, step: float, steps_per_bar: int = 16, swing: float | None = None) -> int:
        """Sample of step ``step`` inside ``bar`` when the bar is divided into ``steps_per_bar`` steps.
        Swing is applied to odd steps of a 16-step (or 32-step: odd 16ths) grid only."""
        spb = steps_per_bar
        frac = step / spb
        t = (bar + frac) * self.bar_sec
        if float(step).is_integer():
            st = int(step)
            if spb == 16 and st % 2 == 1:
                t += self.swing_offset_steps(1, swing) * self.step_sec
            elif spb == 32 and st % 4 == 2:
                t += self.swing_offset_steps(1, swing) * self.step_sec
        return int(round(t * self.sr))

    def total_samples(self, bars: float) -> int:
        """Length in samples of ``bars`` bars starting at bar 0."""
        return self.bar_sample(bars)

    def bars_for_minutes(self, minutes: float, phrase: int = 8) -> int:
        """Whole number of ``phrase``-bar phrases closest to ``minutes``."""
        bars = minutes * 60.0 / self.bar_sec
        n = max(1, int(round(bars / phrase)))
        return n * phrase
