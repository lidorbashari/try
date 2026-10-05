"""Big Room / EDM recipe (126–130 BPM, festival main stage).

Genre brief
-----------
* Drums: a huge punchy kick with a long tuned, saturated tail (it *is* the sub), big layered
  clap+snare on 2 and 4, 16th closed hats + off-beat open hats, tom fills on phrase ends, ride in
  the second drop, crash on every 8-bar phrase of a drop.
* Bass: pumping off-beat saw bass one octave above the kick tail (they never fight: the kick owns
  40–60 Hz, the bass sits at 65–125 Hz and is ducked 85 % by the kick).
* Two flavours, chosen deterministically from the seed:
  - **anthem**: a massive detuned supersaw lead (saw octave below, square octave above, pitch
    "zap"), chord-tone hook in call/response over a minor i–VI–III–VII-style loop, piano + pad
    breakdown, crowd "HEY!" chants.
  - **bounce**: plucky supersaw chord-stab hook in a syncopated rhythm, octave-bouncing bass, a
    zappy lead doubling the top voice, "OH!" chants, early first drop and a long melodic breakdown.
* Builds: accelerating snare roll that rises an octave in pitch, a supersaw pitch riser and a
  white-noise sweep ending exactly on the drop, kick 8ths on the penultimate bar, silence + a long
  shout on the last beat, impact + crash on the drop.
* Arrangement (120 bars ≈ 3.8 min at 128): 32-bar DJ intro (drums only for 16 bars, bass from
  bar 17) and a mirrored 32-bar outro (bass out for the last 16). All sections on the 8-bar grid.
"""
from __future__ import annotations

import numpy as np

from .. import drums, ext_mainstream as xm, fx, instruments as inst
from ..arrangement import Song
from ..theory import voice_lead
from . import register

# (name, kind, bars, energy, flex) — both sum to 120 bars (3.8 min @ 128 BPM)
TPL_ANTHEM = [("Intro", "intro", 32, 5, 0), ("Breakdown", "breakdown", 8, 4, 0), ("Build", "build", 8, 7, 0),
              ("Drop", "drop", 16, 9, 2), ("Breakdown 2", "breakdown", 8, 5, 0), ("Drop 2", "drop", 16, 10, 3),
              ("Outro", "outro", 32, 5, 0)]
TPL_BOUNCE = [("Intro", "intro", 32, 5, 0), ("Build", "build", 8, 7, 0), ("Drop", "drop", 16, 9, 2),
              ("Breakdown", "breakdown", 16, 4, 1), ("Drop 2", "drop", 16, 10, 3), ("Outro", "outro", 32, 5, 0)]

PROGS = [[0, 5, 2, 6], [5, 6, 0, 0], [0, 3, 5, 6], [5, 2, 6, 0], [0, 5, 3, 6]]

# 4-bar anthem hooks: (step from loop start, len, chord-tone index in the lead register)
HOOKS_ANTHEM = [
    [(0, 2, 4), (3, 2, 3), (6, 2, 2), (9, 2, 3), (12, 2, 2), (14, 2, 1),
     (16, 2, 4), (19, 2, 3), (22, 2, 2), (25, 2, 3), (28, 4, 4),
     (32, 2, 4), (35, 2, 3), (38, 2, 2), (41, 2, 3), (44, 2, 2), (46, 2, 1),
     (48, 2, 2), (51, 2, 3), (54, 2, 4), (57, 3, 5), (60, 4, 4)],
    [(0, 1, 2), (2, 2, 3), (5, 1, 2), (6, 2, 4), (10, 2, 3), (13, 3, 2),
     (16, 1, 2), (18, 2, 3), (21, 1, 2), (22, 2, 4), (26, 2, 5), (29, 3, 4),
     (32, 1, 2), (34, 2, 3), (37, 1, 2), (38, 2, 4), (42, 2, 3), (45, 3, 2),
     (48, 1, 2), (50, 2, 3), (53, 1, 2), (54, 2, 1), (58, 6, 0)],
    [(0, 3, 3), (3, 3, 2), (6, 4, 1), (10, 2, 2), (12, 4, 3),
     (16, 3, 4), (19, 3, 3), (22, 4, 2), (26, 2, 3), (28, 4, 2),
     (32, 3, 3), (35, 3, 2), (38, 4, 1), (42, 2, 2), (44, 4, 3),
     (48, 3, 3), (51, 3, 4), (54, 4, 5), (58, 6, 4)],
]
# bounce chord-stab rhythms (one bar, cycled over 2 bars) and top-voice tone indices
BOUNCE_RHYTHMS = [
    [[(0, 2), (3, 2), (6, 2), (10, 2), (13, 2)], [(0, 2), (3, 2), (6, 2), (8, 2), (10, 2), (12, 2), (14, 2)]],
    [[(0, 1.5), (2, 1.5), (5, 2), (8, 1.5), (11, 2), (14, 2)], [(0, 1.5), (3, 2), (6, 2), (10, 1.5), (12, 3)]],
    [[(2, 2), (5, 2), (8, 2), (11, 2), (14, 2)], [(0, 2), (3, 2), (6, 3), (10, 2), (13, 3)]],
]
BOUNCE_TOPS = [[2, 2, 3, 2, 3, 4, 3], [3, 2, 3, 4, 3, 2, 3], [2, 3, 2, 4, 3, 2, 3]]

FOUR = "x...x...x...x..."
CLAP = "....x.......x..."
CLAP_FILL = ["....x.......x.xx", "....x.......xxxx", "....x...x...x.x."]
HATS = ["ogxgogxgogxgogxg", "o.x.o.x.o.x.o.xg", "gox.gox.gox.goxo"]
OPEN_HAT = "..x...x...x...x."
TOM_FILLS = [("..........x.x...", "..............xx"), ("........x.x.x...", "..............x."),
             ("..........xx.x..", "..............x.")]


def tones_in_range(chord, lo, count=8):
    """Chord pitch classes stacked upward from MIDI ``lo`` (the lead register)."""
    pcs = sorted({n % 12 for n in chord})
    out, m = [], lo
    while len(out) < count:
        if m % 12 in pcs:
            out.append(m)
        m += 1
    return out


def in_range(m, lo, hi):
    while m > hi:
        m -= 12
    while m < lo:
        m += 12
    return m


@register("big_room")
def build(plan: dict, rng: np.random.Generator) -> Song:
    anthem = int(plan.get("seed", 0)) % 2 == 0
    song = Song(plan, rng, swing=50.0)
    key = song.key
    song.arrange(TPL_ANTHEM if anthem else TPL_BOUNCE, song.target_bars())
    intro, outro = song.find("intro"), song.find("outro")
    drops = [s for s in song.sections if s.kind == "drop"]
    song.mix_in_bar = 16
    bass_off = outro.end_bar - 16
    bar_sec = song.grid.bar_sec

    # build windows: roll + riser ending on each drop
    windows = []
    for d in drops:
        prev = song.section_before(d)
        rb = 8 if (prev.kind == "build" or prev.bars >= 16) else 4
        windows.append((d.start_bar - rb, d.start_bar))

    def to_drop(bar):
        for a, b in windows:
            if a <= bar < b:
                return b - bar
        return None

    # ---------------------------------------------------------------- harmony
    degs = PROGS[int(rng.integers(len(PROGS)))]
    chords, prev = [], None
    for d in degs:
        ch = voice_lead(prev, key.chord(d, 3, 3), center=key.root(4) - 3)
        chords.append(ch)
        prev = ch
    roots = [in_range(key.degree(d, 2), 36, 47) for d in degs]
    lead_lo = key.root(4) - 3

    def chord_at(c):
        return chords[c.i % 4]

    # ---------------------------------------------------------------- drums
    root_hz = 440 * 2 ** ((in_range(key.root(1), 28, 39) - 69) / 12)
    kick_hz = float(np.clip(root_hz if root_hz <= 58 else root_hz * 2 ** (-5 / 12), 42, 58))
    kick = xm.big_room_kick(tune_hz=kick_hz, tail=float(rng.uniform(0.4, 0.5)), drive=float(rng.uniform(2.3, 2.9)),
                            click=float(rng.uniform(0.75, 0.95)), rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown" and to_drop(c.bar) is None:
            return "X..............." if c.first else None
        tb = to_drop(c.bar)
        if tb is not None:
            if c.kind == "breakdown":
                return "x.x.x.x.x.x.x.x." if tb == 2 else None
            if tb == 1:
                return None
            if tb == 2:
                return "x.x.x.x.x.x.x.x."
            return FOUR
        return FOUR

    song.hits("kick", kick, kick_pat, gain_db=-1.0, sc_source=True, humanize=0.0)

    clp = drums.clap(tightness=0.9, tone_hz=float(rng.uniform(1100, 1400)), tail=0.22, bursts=4, rng=rng)
    snr = drums.snare(tone_hz=float(rng.uniform(190, 230)), snappy=0.8, decay=0.2, kind="909", rng=rng)
    n = max(clp.shape[0], snr.shape[0])
    big_clap = np.zeros(n, dtype=np.float32)
    big_clap[:clp.shape[0]] += clp
    big_clap[:snr.shape[0]] += snr * 0.6
    big_clap = xm.normalize(big_clap)
    cfill = CLAP_FILL[int(rng.integers(len(CLAP_FILL)))]

    def clap_pat(c):
        tb = to_drop(c.bar)
        if c.kind == "breakdown" or (tb is not None and tb <= 4):
            return None
        if c.kind == "intro" and c.i < 8:
            return None
        if c.kind == "outro" and c.bars_left <= 8:
            return None
        if c.kind == "drop" and c.phrase_end:
            return cfill
        return CLAP

    song.hits("clap", big_clap, clap_pat, gain_db=-3.5, sends={"reverb": 0.18, "room": 0.08}, humanize=0.03)

    hat = drums.variants(drums.hat, 4, rng, jitter={"decay": 0.15}, decay=float(rng.uniform(0.028, 0.04)),
                         tone=float(rng.uniform(1.0, 1.2)))
    hp_ = HATS[int(rng.integers(len(HATS)))]

    def hat_pat(c):
        tb = to_drop(c.bar)
        if c.kind == "breakdown" and tb is None:
            return None
        if tb is not None and tb <= 2:
            return None
        return hp_

    song.hits("hats", hat, hat_pat, gain_db=-12.0, pan=0.25, humanize=0.08)
    ohat = drums.hat(open_=True, decay=0.2, tone=1.1, rng=rng)

    def ohat_pat(c):
        if c.kind in ("breakdown", "build"):
            return None
        if c.kind == "intro" and c.i < 8:
            return None
        if c.kind == "outro" and c.bars_left <= 8:
            return None
        return OPEN_HAT

    song.hits("open_hat", ohat, ohat_pat, gain_db=-13.0, pan=-0.2, sends={"room": 0.08})
    ride = drums.ride(decay=1.2, bell=0.4, rng=rng)
    song.hits("ride", ride, lambda c: "x.x.x.x.x.x.x.x." if c.name == "Drop 2" else None, gain_db=-18.0, pan=0.35)

    tf = TOM_FILLS[int(rng.integers(len(TOM_FILLS)))]
    tom_hi = drums.tom(float(rng.uniform(150, 180)), decay=0.35, rng=rng)
    tom_lo = drums.tom(float(rng.uniform(95, 115)), decay=0.45, rng=rng)

    def tom_pat(which):
        def f(c):
            if c.kind in ("intro", "outro", "drop") and c.phrase_end and not (c.kind == "drop" and c.last):
                return tf[which]
            return None
        return f

    song.hits("tom_hi", tom_hi, tom_pat(0), gain_db=-9.0, pan=0.3, sends={"room": 0.2})
    song.hits("tom_lo", tom_lo, tom_pat(1), gain_db=-8.0, pan=-0.3, sends={"room": 0.2})

    # snare roll builds (pitch rising, accelerating)
    roll_snare = drums.snare(tone_hz=float(rng.uniform(210, 240)), snappy=0.9, decay=0.13, kind="tight", rng=rng)
    roll = song.audio("roll", bus="drums", sends={"reverb": 0.15})
    for a, b in windows:
        buf = xm.build_roll(song, roll_snare, a, b - a, semis=(0.0, 12.0), vel=(0.3, 1.0), last_beat_rest=True)
        roll.add(buf, a, gain_db=-7.0)

    # ---------------------------------------------------------------- bass (off-beat pump)
    bass_inst = inst.bass_pluck(cutoff=float(rng.uniform(650, 850)), env_amt=2600.0, decay=0.11, res=0.3, sub=0.55,
                                drive=1.8, wave="saw", sustain=0.5, grit=0.45)

    def bass_on(c):
        if c.bar < 16 or c.bar >= bass_off or c.kind == "breakdown":
            return False
        tb = to_drop(c.bar)
        return tb is None or tb > 4

    def bass_notes(c):
        if not bass_on(c):
            return []
        r = roots[c.i % 4] if c.kind in ("drop", "build") else roots[0]
        if anthem:
            ev = [(2, 1.6, r, 1.0), (6, 1.6, r, 0.9), (10, 1.6, r, 1.0), (14, 1.6, r, 0.9)]
        else:
            ev = [(2, 1.6, r, 1.0), (6, 1.6, r + 12, 0.85), (10, 1.6, r, 1.0), (14, 1.6, r + 12, 0.85)]
        return ev

    bl = song.notes("bass", bass_inst, bass_notes, bus="bass", gain_db=-5.0, sidechain=0.85, sc_release_ms=170.0)
    bl.automate("lp", [(16, 350), (31.99, 2400), (32, 9000), (bass_off - 8, 9000), (bass_off, 600)])

    # ---------------------------------------------------------------- lead / hook
    if anthem:
        hook = HOOKS_ANTHEM[int(rng.integers(len(HOOKS_ANTHEM)))]
        lead_inst = xm.big_lead(detune=float(rng.uniform(0.45, 0.6)), cutoff=float(rng.uniform(6000, 8000)),
                                zap=float(rng.uniform(5, 8)), oct_down=0.5, square_up=0.16, drive=1.8,
                                sustain=0.7, release=0.16)

        def hook_events(c, oct_=0):
            loop = c.i % 4
            ch = chords[loop]
            tones = tones_in_range(ch, lead_lo)
            return [(s - 16 * loop, ln, tones[k] + oct_, 0.95 if (s % 4 == 0) else 0.85)
                    for s, ln, k in hook if 16 * loop <= s < 16 * (loop + 1)]

        def lead_notes(c):
            tb = to_drop(c.bar)
            if c.kind == "drop":
                ev = hook_events(c)
                return ev
            if tb is not None:
                ev = hook_events(c)
                return [e for e in ev if e[0] < 12] if tb == 1 else ev
            return []

        lead = song.notes("lead", lead_inst, lead_notes, gain_db=-6.5, width=1.5, sidechain=0.55, sc_release_ms=160.0,
                          sends={"reverb": 0.12, "delay": 0.1})
        song.notes("lead_hi", lead_inst, lambda c: hook_events(c, 12) if c.name == "Drop 2" else [],
                   gain_db=-13.0, width=1.7, sidechain=0.55, sc_release_ms=160.0, sends={"reverb": 0.15})
        # breakdown: piano plays the hook softly over the pad
        piano = inst.piano(bright=0.55, release=0.4)

        def piano_notes(c):
            if c.kind == "breakdown" and to_drop(c.bar) is None:
                ev = [(s, ln, m - 12, 0.7) for s, ln, m, v in hook_events(c)]
                return ev + [(0, 14, sorted(chord_at(c))[0] - 12, 0.5)]
            return []

        song.notes("piano", piano, piano_notes, gain_db=-7.5, sends={"hall": 0.3, "delay": 0.15}, width=1.3)
    else:
        rh = BOUNCE_RHYTHMS[int(rng.integers(len(BOUNCE_RHYTHMS)))]
        tops = BOUNCE_TOPS[int(rng.integers(len(BOUNCE_TOPS)))]
        stab_inst = xm.supersaw_stab(detune=float(rng.uniform(0.4, 0.55)), cutoff=1400.0, env_amt=7500.0, f_decay=0.12,
                                     decay=0.28, sustain=0.0, release=0.1, drive=1.5, oct_down=0.35)
        zap_inst = xm.big_lead(detune=0.35, mix=0.6, cutoff=6500.0, zap=12.0, zap_ms=15.0, oct_down=0.0,
                               square_up=0.3, drive=2.0, decay=0.12, sustain=0.25, release=0.1)

        def stab_events(c, top_only=False):
            ch = chord_at(c)
            tones = tones_in_range(ch, lead_lo - 5)
            pat = rh[c.i % 2]
            out = []
            for j, (s, ln) in enumerate(pat):
                top = tones[tops[j % len(tops)] + 1]
                v = 1.0 if j == 0 else 0.85
                if top_only:
                    out.append((s, ln, top + 12, v))
                else:
                    body = [m for m in tones[:6] if m < top][-3:]
                    out.append((s, ln, body + [top], v))
            return out

        def stab_notes(c):
            tb = to_drop(c.bar)
            if c.kind == "drop" or tb is not None:
                ev = stab_events(c)
                return [e for e in ev if e[0] < 12] if tb == 1 else ev
            if c.kind == "intro" and c.i >= 24:
                return stab_events(c)[:2]
            if c.kind == "outro" and c.bar < bass_off:
                return stab_events(c)[:3]
            return []

        lead = song.notes("lead", stab_inst, stab_notes, gain_db=-6.0, width=1.6, sidechain=0.6, sc_release_ms=150.0,
                          sends={"reverb": 0.12, "delay8": 0.08})
        song.notes("lead_zap", zap_inst, lambda c: stab_events(c, True) if c.kind == "drop" else [],
                   gain_db=-11.0, width=1.2, sidechain=0.5, sends={"delay": 0.12, "reverb": 0.1})
        bell = inst.pluck(wave="square", cutoff=900.0, env_amt=4500.0, decay=0.18, release=0.3)

        def bell_notes(c):
            if c.kind == "breakdown" and to_drop(c.bar) is None:
                return [(s, ln, m, 0.75) for s, ln, m, v in stab_events(c, True)]
            return []

        song.notes("bd_pluck", bell, bell_notes, gain_db=-9.0, sends={"delay": 0.3, "hall": 0.25}, width=1.4)

    # lead filter: closed at the start of every build, opening into the drop
    pts = [(0, 600.0)]
    for a, b in windows:
        pts += [(a, 450.0), (b - 0.02, 7000.0), (b, 18000.0)]
    end_last_drop = drops[-1].end_bar
    pts += [(end_last_drop - 0.01, 18000.0), (end_last_drop, 2500.0), (bass_off, 500.0)]
    lead.automate("lp", pts)
    gpts = [(0, 0.0)]
    for a, b in windows:
        gpts += [(a - 0.01, 0.0), (a, -6.0), (b - 0.02, -2.0), (b, 0.0)]
    lead.automate("gain_db", gpts)

    # pad (breakdowns + builds), sidechained
    pad = song.notes("pad", xm.soft_pad(attack=0.4, cutoff=float(rng.uniform(1500, 2200)), detune=0.25),
                     lambda c: [(0, 16, chord_at(c), 0.75)] if (c.kind in ("breakdown", "build", "drop")) else [],
                     gain_db=-11.5, width=1.6, sidechain=0.6, sends={"hall": 0.3})
    pad.automate("gain_db", song.section_points({"breakdown": 0.0, "build": -5.0, "drop": -6.0}, -60.0))

    # crowd chant: "HEY!" (anthem) / "OH!" (bounce)
    shout = xm.chant(vowel="e" if anthem else "o", vowel_to="i" if anthem else "a", voices=6, shift=1.05,
                     fall=-2.5, breath=0.25, spread=0.9)
    shout_pitch = in_range(key.root(3), 50, 61)

    def chant_notes(c):
        tb = to_drop(c.bar)
        if tb == 1:
            return [(12, 4, shout_pitch, 1.0)]
        if c.kind == "drop":
            if anthem:
                return [(12, 2, shout_pitch, 0.95)] if c.i % 2 == 1 else []
            return [(6, 1.5, shout_pitch, 0.85), (14, 2, shout_pitch + 2 if c.i % 2 else shout_pitch, 0.95)] \
                if c.i % 4 == 3 else []
        return []

    song.notes("chant", shout, chant_notes, bus="vox", gain_db=-7.0, sends={"reverb": 0.25, "delay": 0.12},
               sidechain=0.3, width=1.3)

    # ---------------------------------------------------------------- fx
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.1})
    crash = drums.crash(decay=2.4, rng=rng)
    for d in drops:
        for k in range(0, d.bars, 8):
            fxl.add(crash, d.start_bar + k, gain_db=-8.0 if k == 0 else -11.0)
        fxl.add(fx.impact(3.0, rng=rng), d.start_bar, gain_db=-10.0)
        fxl.add(fx.reverse_cymbal(bar_sec, rng=rng), d.start_bar, align="end", gain_db=-10.0)
    for a, b in windows:
        fxl.add(fx.riser((b - a) * bar_sec, "both", pitch_from=key.root(3), pitch_to=key.root(6), rng=rng), b,
                align="end", gain_db=-12.0)
        fxl.add(fx.noise_sweep((b - a) * bar_sec, up=True, rng=rng), b, align="end", gain_db=-19.0)
    for s in song.sections:
        if s.kind == "breakdown":
            fxl.add(fx.downlifter(bar_sec * 2, rng=rng), s.start_bar, gain_db=-11.0)
    for b in (8, 16, 24):
        fxl.add(fx.noise_sweep(bar_sec * 4, up=True, rng=rng), b, align="end", gain_db=-22.0)
    for b in (16, outro.start_bar, bass_off):
        fxl.add(crash, b, gain_db=-12.0)
    fxl.add(fx.noise_sweep(bar_sec * 8, up=True, rng=rng), intro.end_bar, align="end", gain_db=-16.0)

    # ---------------------------------------------------------------- mix
    song.buses["drums"].eq = [("lowshelf", 55.0, -3.0 - max(0.0, 50.0 - kick_hz) / 2.0, 0.7), ("peak", 4200.0, 2.0, 0.8), ("peak", 250.0, -2.0, 1.0)]
    song.buses["bass"].eq = [("peak", 220.0, -2.5, 1.0)]
    song.buses["music"].eq = [("peak", 3000.0, 1.5, 0.7), ("peak", 400.0, -2.0, 0.9)]
    song.master.lufs = -9.0
    song.master.high_shelf_db = 2.0

    progname = "–".join(["i", "ii°", "III", "iv", "v", "VI", "VII"][d] for d in degs)
    first = drops[0]
    second = drops[1]
    bd1 = song.find("breakdown")
    if anthem:
        song.instruments = ["big room kick with tuned tail", "layered clap+snare", "pumping off-beat saw bass",
                            "detuned supersaw lead (zap)", "piano", "warm pad", "crowd chant (HEY!)",
                            "pitch-rising snare roll", "supersaw riser", "white-noise sweeps", "impacts", "toms"]
        song.description_he = (f"ביג רום פסטיבלי ב-{int(song.bpm)} BPM בסולם {plan['key']}: קיק ענק עם זנב מכוון "
                               f"לסולם, באס סאו שפועם על האוף-ביט והוק ענק של סופרסאו (Detuned) בשיטת שאלה-תשובה "
                               f"על הלופ {progname}. בברייקדאון פסנתר ופד, בבילד רול סנר מאיץ שעולה בגובה, רייזר "
                               f"וסוויפ של רעש לבן — ואז דרופ עם אימפקט וקריאות \"HEY!\" של הקהל. נבנה לרגע השיא "
                               f"של הסט.")
    else:
        song.instruments = ["big room kick with tuned tail", "layered clap+snare", "octave-bouncing saw bass",
                            "plucky supersaw chord-stab hook", "zap lead", "square pluck", "warm pad",
                            "crowd chant (OH!)", "pitch-rising snare roll", "supersaw riser", "white-noise sweeps",
                            "impacts", "toms", "ride"]
        song.description_he = (f"ביג רום קופצני ב-{int(song.bpm)} BPM בסולם {plan['key']}: הוק של אקורדי סופרסאו "
                               f"קצרים ופלאקיים בריתם מסונכפ, באס שקופץ באוקטבות, ליד \"זאפ\" שמכפיל את הקול העליון "
                               f"וקריאות \"OH!\". הדרופ הראשון מגיע מוקדם, אחריו ברייקדאון מלודי ארוך ובילד עם רול "
                               f"סנר מאיץ ורייזר, ובדרופ השני נכנסים רייד ועוד אנרגיה. מושלם לרגע של ידיים באוויר.")
    cam = plan.get("camelot", "")
    partners = xm.partners_he(plan)
    song.mix_tips_he = (
        f"טיפ ערבוב: אינטרו של 32 תיבות — 16 התיבות הראשונות תופים בלבד, הבאס נכנס בתיבה 17 (Hot Cue B). "
        + (f"ברייקדאון בתיבה {bd1.start_bar + 1}, " if bd1 else "")
        + f"הבילד מתחיל בתיבה {windows[0][0] + 1} והדרופ נוחת בתיבה {first.start_bar + 1} (Hot Cue D); "
        f"דרופ שני בתיבה {second.start_bar + 1}. האאוטרו מתחיל בתיבה {outro.start_bar + 1}, הבאס יוצא בתיבה "
        f"{bass_off + 1} ו-16 התיבות האחרונות הן תופים בלבד — מצוין ל-Bass Swap. "
        f"{xm.wheel_he(cam)} " + (partners + ". " if partners else "")
        + "אל תשכבו שני דרופים של ביג רום זה על זה — הזנבות של הקיקים יתנגשו; עשו Bass Swap בתחילת פרייז.")
    return song
