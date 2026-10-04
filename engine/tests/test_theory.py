from djlab import theory

SCHEMA = ("1A Abm · 1B B · 2A Ebm · 2B F# · 3A Bbm · 3B Db · 4A Fm · 4B Ab · 5A Cm · 5B Eb · 6A Gm · 6B Bb · "
          "7A Dm · 7B F · 8A Am · 8B C · 9A Em · 9B G · 10A Bm · 10B D · 11A F#m · 11B A · 12A C#m · 12B E")


def test_camelot_table_matches_schema():
    for item in SCHEMA.split(" · "):
        code, key = item.split()
        assert theory.camelot(key) == code, key


def test_compatible_keys():
    assert theory.compatible_keys("8A") == ["8A", "9A", "7A", "8B", "10A"]
    assert "1A" in theory.compatible_keys("12A")


def test_key_degrees_and_chords():
    k = theory.Key("A minor")
    assert k.root(2) == 45
    assert k.degree(0, 3) == 57 and k.degree(2, 3) == 60 and k.degree(7, 3) == 69
    assert k.chord(0, 3) == [57, 60, 64]
    assert theory.note_to_midi("A4") == 69 and theory.midi_to_name(61) == "C#4"
    h = theory.Key("E minor", scale="hijaz")
    assert [n - h.root(3) for n in h.notes(3)] == [0, 1, 4, 5, 7, 8, 10]
