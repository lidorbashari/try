import numpy as np
import pytest

from djlab.genres import UnknownGenre, get_recipe
from djlab.render import build_song, load_plan, plan_entry


@pytest.mark.parametrize("tid", ["house-05", "techno-01"])
def test_reference_recipe_structure(tid):
    plan = plan_entry(tid)
    s = build_song(plan)
    assert s.total_bars == s.grid.bars_for_minutes(plan["target_minutes"])
    assert all(x.start_bar % 8 == 0 and x.bars % 8 == 0 for x in s.sections)
    assert s.sections[0].kind == "intro" and s.sections[0].bars >= 16
    assert s.sections[-1].kind == "outro" and s.sections[-1].bars >= 16
    cues = {c["slot"]: c for c in s.cues()}
    assert cues["A"]["bar"] == 0 and cues["H"]["bar"] == s.total_bars - 16
    assert cues["B"]["bar"] >= 16  # no bass in the first 16 bars
    # no bass / tonal layers sound in the first 16 bars
    for l in s.layers:
        if l.bus in ("bass", "music", "vox"):
            a, b = 0, s.grid.bar_sample(16)
            y = l.render_dry(s, a, b)
            assert y is None or np.abs(y).max() < 1e-6, l.name


@pytest.mark.parametrize("tid", ["house-05", "techno-01"])
def test_recipe_deterministic_and_seed_sensitive(tid):
    plan = plan_entry(tid)
    s1, s2 = build_song(plan), build_song(plan)
    d = s1.bar("drop")
    a, b = s1.grid.bar_sample(d), s1.grid.bar_sample(d + 1)
    from djlab.mixer import mix
    m1, m2 = mix(s1, a, b), mix(s2, a, b)
    assert np.array_equal(m1, m2)
    assert np.isfinite(m1).all() and np.abs(m1).max() > 0.01
    s3 = build_song(dict(plan, seed=plan["seed"] + 1))
    d3 = s3.bar("drop")
    m3 = mix(s3, s3.grid.bar_sample(d3), s3.grid.bar_sample(d3 + 1))
    assert m3.shape != m1.shape or not np.array_equal(m1, m3)


def test_unknown_genre_errors_clearly():
    with pytest.raises(UnknownGenre):
        get_recipe("polka_core")


def test_plan_is_readable():
    plan = load_plan()
    assert len(plan) >= 2 and all("seed" in e for e in plan)
