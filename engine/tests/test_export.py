import json

import numpy as np
from mutagen.id3 import ID3

from djlab.export import decode, export_mp3_safe, sidecar, write_json, write_tags
from djlab.cover import make_cover
from djlab.master import master
from test_render import PLAN, tiny_song


def test_mp3_roundtrip_alignment_and_tags(tmp_path):
    s = tiny_song()
    y, _ = master(s.render(), s.master)
    mp3 = tmp_path / "t.mp3"
    dec, L, tp = export_mp3_safe(y, mp3)
    assert tp <= -1.0
    # LAME encoder delay is compensated: same length and sample-aligned
    assert abs(dec.shape[0] - y.shape[0]) <= 2
    n = 44100
    a, b = y[:n, 0], dec[:n, 0]
    lags = range(-50, 51)
    corr = [np.dot(a[100:n - 100], b[100 + k:n - 100 + k]) for k in lags]
    assert list(lags)[int(np.argmax(corr))] == 0
    cover = make_cover(PLAN, np.abs(y[:, 0])[::1000])
    assert cover[:2] == b"\xff\xd8" and len(cover) <= 200 * 1024
    write_tags(mp3, PLAN, cover)
    t = ID3(str(mp3))
    assert t.version[:2] == (2, 4)
    assert str(t["TIT2"].text[0]) == "Unit Test"
    assert str(t["TPE1"].text[0]) == "DJ Lab Originals"
    assert str(t["TBPM"].text[0]) == "128"
    assert str(t["TKEY"].text[0]) == "Am"
    assert any(k.startswith("APIC") for k in t.keys())
    meta = sidecar(s, PLAN, mp3, tmp_path / "t.jpg", L, tp, dec.shape[0] / 44100)
    write_json(tmp_path / "t.json", meta)
    back = json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))
    for k in ("id", "bpm", "sections", "cues", "memory_cues", "lufs", "true_peak_dbtp", "first_downbeat_sec"):
        assert k in back
    assert back["first_downbeat_sec"] == 0.0 and back["bars"] == 16
    # decoding again gives identical audio (deterministic encode)
    assert np.array_equal(decode(mp3), dec)
