"""Music theory helpers: notes, scales, chords, voicings, progressions, Camelot wheel."""
from __future__ import annotations

import re

import numpy as np

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_ALIASES = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#", "Cb": "B", "Fb": "E", "E#": "F", "B#": "C"}

SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],            # natural minor / aeolian
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "melodic_minor": [0, 2, 3, 5, 7, 9, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "phrygian_dominant": [0, 1, 4, 5, 7, 8, 10],  # = Hijaz (Freygish)
    "hijaz": [0, 1, 4, 5, 7, 8, 10],
    "double_harmonic": [0, 1, 4, 5, 7, 8, 11],
    "minor_pentatonic": [0, 3, 5, 7, 10],
    "major_pentatonic": [0, 2, 4, 7, 9],
    "blues": [0, 3, 5, 6, 7, 10],
}

CHORDS = {
    "maj": [0, 4, 7], "min": [0, 3, 7], "dim": [0, 3, 6], "aug": [0, 4, 8],
    "sus2": [0, 2, 7], "sus4": [0, 5, 7],
    "maj7": [0, 4, 7, 11], "min7": [0, 3, 7, 10], "7": [0, 4, 7, 10], "m7b5": [0, 3, 6, 10],
    "add9": [0, 4, 7, 14], "madd9": [0, 3, 7, 14], "min9": [0, 3, 7, 10, 14], "maj9": [0, 4, 7, 11, 14],
    "min11": [0, 3, 7, 10, 14, 17], "power": [0, 7, 12], "6": [0, 4, 7, 9], "m6": [0, 3, 7, 9],
}

# Camelot wheel: minor = A, major = B
_CAMELOT_MINOR = {"G#": 1, "D#": 2, "A#": 3, "F": 4, "C": 5, "G": 6, "D": 7, "A": 8, "E": 9, "B": 10, "F#": 11, "C#": 12}
_CAMELOT_MAJOR = {"B": 1, "F#": 2, "C#": 3, "G#": 4, "D#": 5, "A#": 6, "F": 7, "C": 8, "G": 9, "D": 10, "A": 11, "E": 12}

# Progressions as scale degrees (0-based) in a minor/major key, chosen per mood.
PROGRESSIONS = {
    "minor": {
        "dark": [[0, 0, 5, 6], [0, 5, 3, 4], [0, 6, 5, 6]],
        "deep": [[0, 3, 6, 5], [0, 2, 3, 4], [0, 5, 2, 6]],
        "uplifting": [[5, 6, 0, 0], [5, 2, 6, 3], [0, 5, 2, 6]],
        "hypnotic": [[0, 0, 0, 6], [0, 0, 3, 3], [0, 6, 0, 5]],
        "emotional": [[0, 5, 2, 6], [5, 3, 0, 4], [0, 3, 5, 4]],
    },
    "major": {
        "happy": [[0, 4, 5, 3], [0, 3, 4, 3], [0, 5, 3, 4]],
        "deep": [[1, 4, 0, 5], [3, 4, 2, 5], [0, 2, 3, 4]],
        "uplifting": [[3, 4, 5, 0], [0, 4, 5, 3], [5, 3, 0, 4]],
        "funky": [[0, 3, 0, 4], [1, 4, 0, 0], [0, 6, 3, 0]],
    },
}


def note_to_midi(name: str) -> int:
    """'A1' → 33, 'C#4' → 61, 'Bb2' → 46."""
    m = re.fullmatch(r"([A-Ga-g][#b]?)(-?\d+)", name.strip())
    if not m:
        raise ValueError(f"bad note name {name!r}")
    pc = pitch_class(m.group(1))
    return 12 * (int(m.group(2)) + 1) + pc


def midi_to_name(m: int) -> str:
    return f"{NOTE_NAMES[int(m) % 12]}{int(m) // 12 - 1}"


def midi_to_hz(m) -> float | np.ndarray:
    return 440.0 * 2.0 ** ((np.asarray(m, dtype=np.float64) - 69.0) / 12.0)


def hz_to_midi(f) -> float | np.ndarray:
    return 69.0 + 12.0 * np.log2(np.asarray(f, dtype=np.float64) / 440.0)


def pitch_class(name: str) -> int:
    n = name[0].upper() + name[1:]
    n = _ALIASES.get(n, n)
    return NOTE_NAMES.index(n)


def parse_key(key: str) -> tuple[int, str]:
    """'A minor' / 'Am' / 'F#m' / 'C' / 'Bb major' → (pitch_class, 'minor'|'major')."""
    k = key.strip()
    m = re.fullmatch(r"([A-Ga-g][#b]?)\s*(m|min|minor|maj|major)?", k)
    if not m:
        raise ValueError(f"bad key {key!r}")
    q = (m.group(2) or "maj").lower()
    return pitch_class(m.group(1)), ("minor" if q in ("m", "min", "minor") else "major")


def camelot(key: str) -> str:
    pc, q = parse_key(key)
    name = NOTE_NAMES[pc]
    return f"{_CAMELOT_MINOR[name]}A" if q == "minor" else f"{_CAMELOT_MAJOR[name]}B"


def camelot_to_key(code: str) -> str:
    num, letter = int(code[:-1]), code[-1].upper()
    table = _CAMELOT_MINOR if letter == "A" else _CAMELOT_MAJOR
    for k, v in table.items():
        if v == num:
            return f"{k}m" if letter == "A" else k
    raise ValueError(code)


def compatible_keys(code: str) -> list[str]:
    """Harmonic-mixing neighbours: same, ±1 on the wheel, relative major/minor, +2 energy boost."""
    num, letter = int(code[:-1]), code[-1].upper()
    other = "B" if letter == "A" else "A"
    wrap = lambda x: (x - 1) % 12 + 1  # noqa: E731
    return [f"{num}{letter}", f"{wrap(num + 1)}{letter}", f"{wrap(num - 1)}{letter}", f"{num}{other}",
            f"{wrap(num + 2)}{letter}"]


class Key:
    """A musical key with scale-aware helpers. ``Key('A minor').degree(0, octave=2)`` → MIDI of A2."""

    def __init__(self, key: str, scale: str | None = None):
        self.root_pc, self.quality = parse_key(key)
        self.scale_name = scale or self.quality
        self.scale = SCALES[self.scale_name]

    @property
    def name(self) -> str:
        return NOTE_NAMES[self.root_pc] + ("m" if self.quality == "minor" else "")

    def root(self, octave: int = 2) -> int:
        return 12 * (octave + 1) + self.root_pc

    def degree(self, deg: int, octave: int = 3) -> int:
        """MIDI note of scale degree ``deg`` (0-based, may be negative or ≥7) in ``octave``."""
        n = len(self.scale)
        o, d = divmod(deg, n)
        return self.root(octave + o) + self.scale[d]

    def notes(self, octave: int = 3, count: int | None = None) -> list[int]:
        count = count or len(self.scale)
        return [self.degree(i, octave) for i in range(count)]

    def chord(self, deg: int, octave: int = 3, size: int = 3, spread: int = 2) -> list[int]:
        """Diatonic chord stacked in thirds on scale degree ``deg`` (size 3 = triad, 4 = 7th, 5 = 9th)."""
        return [self.degree(deg + spread * i, octave) for i in range(size)]

    def quantize(self, midi: int) -> int:
        pcs = {(self.root_pc + s) % 12 for s in self.scale}
        m = int(round(midi))
        for d in (0, -1, 1, -2, 2):
            if (m + d) % 12 in pcs:
                return m + d
        return m


def chord(root_midi: int, quality: str = "min") -> list[int]:
    return [root_midi + i for i in CHORDS[quality]]


def invert(notes: list[int], n: int = 1) -> list[int]:
    notes = sorted(notes)
    for _ in range(n):
        notes = notes[1:] + [notes[0] + 12]
    return notes


def voice_lead(prev: list[int] | None, target: list[int], center: int = 60) -> list[int]:
    """Choose the inversion/octave of ``target`` closest to ``prev`` (or to ``center``)."""
    pcs = sorted({n % 12 for n in target}, key=lambda p: (p - target[0] % 12) % 12)
    best, best_cost = None, 1e9
    ref = sorted(prev) if prev else [center - 5 + 4 * i for i in range(len(target))]
    for base_oct in range(2, 7):
        for inv in range(len(pcs)):
            rot = pcs[inv:] + pcs[:inv]
            notes, last = [], 12 * base_oct - 1
            for p in rot:
                n = 12 * (last // 12) + p
                while n <= last:
                    n += 12
                notes.append(n)
                last = n
            while len(notes) < len(target):
                notes.append(notes[len(notes) - len(pcs)] + 12)
            cost = sum(abs(a - b) for a, b in zip(sorted(notes), ref)) + abs(np.mean(notes) - center) * 0.3
            if cost < best_cost:
                best, best_cost = notes, cost
    return sorted(best)


def progression(key: Key, mood: str = "deep", rng=None, octave: int = 3, size: int = 4,
                voice_leading: bool = True) -> list[list[int]]:
    """Pick a mood progression for the key and return voiced chords (lists of MIDI notes)."""
    rng = rng or np.random.default_rng(0)
    table = PROGRESSIONS[key.quality]
    options = table.get(mood) or next(iter(table.values()))
    degs = options[int(rng.integers(len(options)))]
    chords, prev = [], None
    for d in degs:
        c = key.chord(d, octave, size)
        if voice_leading:
            c = voice_lead(prev, c, center=12 * (octave + 1) + 7)
        chords.append(c)
        prev = c
    return chords
