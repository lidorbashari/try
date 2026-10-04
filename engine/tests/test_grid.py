import pytest

from djlab.grid import Grid


def test_bar_positions_exact():
    g = Grid(126)
    assert g.sample(0) == 0
    assert g.bar_sec == pytest.approx(240 / 126)
    # bar 136 lands exactly where float time says (no cumulative drift)
    assert g.bar_sample(136) == round(136 * 240 / 126 * 44100)
    assert g.sample(1000, 2, 3) == round(((1000 * 4 + 2) * 4 + 3) * (60 / 126 / 4) * 44100)


def test_step_sample_matches_time():
    g = Grid(130)
    for bar in (0, 7, 63, 511):
        for st in range(16):
            assert g.step_sample(bar, st) == round((bar + st / 16) * g.bar_sec * 44100)


def test_swing_delays_odd_16ths_only():
    g = Grid(120, swing=66.0)
    straight = Grid(120)
    assert g.step_sample(3, 0) == straight.step_sample(3, 0)
    assert g.step_sample(3, 2) == straight.step_sample(3, 2)
    d = g.step_sample(3, 1) - straight.step_sample(3, 1)
    assert d == pytest.approx(0.32 * g.step_sec * 44100, abs=1)
    # explicit override
    assert g.step_sample(3, 1, swing=50.0) == straight.step_sample(3, 1)


def test_bars_for_minutes_is_phrase_multiple():
    g = Grid(126)
    assert g.bars_for_minutes(4.3) == 136
    assert Grid(130).bars_for_minutes(4.4) == 144
    for m in (2.0, 3.3, 5.1):
        assert g.bars_for_minutes(m) % 8 == 0
