import numpy as np
import pytest

from djlab import drums, fx, instruments as inst
from djlab.arrangement import Song, clip
from djlab.master import lufs, master
from djlab.dsp import true_peak_db

PLAN = {"id": "test-01", "file_stem": "test-01-unit", "family": "house", "genre_slug": "tech_house",
        "genre": "Tech House", "bpm": 128, "key": "A minor", "key_short": "Am", "camelot": "8A", "energy": 5,
        "role": "build", "title": "Unit Test", "title_he": "בדיקה", "target_minutes": 0.25, "seed": 42}


def tiny_song(seed=42):
    rng = np.random.default_rng(seed)
    s = Song(dict(PLAN, seed=seed), rng, swing=56)
    s.arrange([("Intro", "intro", 8, 3, 0), ("Drop", "drop", 8, 8, 0)], 16)
    s.mix_in_bar = 8
    s.hits("kick", drums.kick("tech_house", rng=rng), "x...x...x...x...", sc_source=True)
    s.hits("hat", drums.variants(drums.hat, 3, rng), "gogxgogxgogxgogx", gain_db=-14, pan=0.3)
    s.hits("clap", drums.clap(rng=rng), "....x.......x...", gain_db=-6, sends={"reverb": 0.2}, when=["drop"])
    s.notes("bass", inst.bass_pluck(), clip([(2, 1.5, 33, 1.0), (6, 1.5, 33, 0.9), (10, 1.5, 45, 1.0), (14, 1, 36, 0.8)], 1),
            bus="bass", gain_db=-4, sidechain=0.5, when="drop").automate("lp", [(8, 300), (16, 3000)])
    s.notes("stab", inst.stab(), lambda c: [(3, 1, [57, 60, 64, 67], 0.9)], gain_db=-10, sends={"delay": 0.2},
            when="drop")
    s.line("acid", inst.MonoSynth(), lambda c: [(i, 0.6, 45 + (i % 3) * 3, 0.9, "s" if i % 5 == 0 else "a")
                                                for i in range(0, 16, 2)], bus="music", gain_db=-10, when="drop")
    s.audio("fx").add(fx.riser(2.0), 8, align="end", gain_db=-8).add(drums.crash(rng=rng), 8, gain_db=-10)
    return s


def test_mix_is_deterministic_and_finite():
    a = tiny_song().render()
    b = tiny_song().render()
    assert a.shape == b.shape == (tiny_song().grid.total_samples(16), 2)
    assert np.isfinite(a).all()
    assert np.array_equal(a, b)
    c = tiny_song(seed=7).render()
    assert not np.array_equal(a, c)


def test_master_hits_target_without_clipping():
    s = tiny_song()
    y, L = master(s.render(), s.master)
    assert np.isfinite(y).all()
    assert np.abs(y).max() < 1.0
    assert true_peak_db(y) <= s.master.ceiling_dbtp + 0.15
    assert abs(lufs(y) - s.master.lufs) < 1.0
    # first downbeat is at sample 0: the kick transient starts immediately
    assert np.abs(y[:200]).max() > 0.05


def test_cues_and_sections():
    s = tiny_song()
    cues = s.cues()
    slots = [c["slot"] for c in cues]
    assert slots[0] == "A" and "D" in slots and "B" in slots
    for c in cues:
        assert c["sec"] == pytest.approx(c["bar"] * 240 / 128, abs=1e-3)
    assert s.sections_meta()[1]["start_bar"] == 8
