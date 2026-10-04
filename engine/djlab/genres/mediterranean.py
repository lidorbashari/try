"""Mediterranean recipes — two variants chosen by ``plan["genre"]``:

* **Mediterranean Groove** (100–104 BPM): Israeli Mizrahi party groove. The darbuka is the heart
  (doum/tek/ka/slap strokes on maqsum, baladi, saidi, malfuf and chiftetelli, with rolls and
  fills), riq jingles, finger cymbals and crowd claps over a modern kick/bass pattern (maqsum-pop
  or dembow). Melodies live in Nahawand / harmonic minor with **Hijaz on the dominant** (the way
  Mizrahi pop uses Hijaz inside a minor key: e.g. E minor → B Hijaz B-C-D#-E), ornamented with
  grace notes, trills, slides and quarter-tone bends. Instruments: oud (Karplus-Strong), qanun
  runs, ney taqsim in the breakdown, Arabic string section (pad + unison line) and the electric
  Mizrahi keyboard lead singing the hook. Build-ups with darbuka rolls → big hook drop.
* **Mediterranean House** (124–125 BPM): organic / ethnic deep house — four-on-the-floor kick,
  darbuka and congas layered on top, deep rolling bass, Hijaz oud / ney / strings hooks, wide pads,
  big emotional breakdown, 32-bar drums-only DJ intro and outro.

Musical material (riffs, hooks, taqsim phrases) is original and written per variant; ``rng`` picks
sound-design details and pattern variations so each seed differs.
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from .. import ext_world as W
from ..theory import voice_lead
from . import register

# chord tones in semitones above the (minor) tonic
CH = {"i": [0, 3, 7], "iv": [5, 8, 12], "V": [7, 11, 14], "V7": [7, 11, 14, 17], "bVI": [8, 12, 15],
      "bVII": [10, 14, 17], "bIII": [3, 7, 10], "i9": [0, 3, 7, 14], "bVI7": [8, 12, 15, 19]}
ROOT = {k: v[0] for k, v in CH.items()}


def reg(pc: int, lo: int, hi: int | None = None) -> int:
    """MIDI note of pitch-class ``pc`` in [lo, lo+12)."""
    m = lo + ((pc - lo) % 12)
    return m


def bars(*strings) -> str:
    """Join one-bar melodic strings (each must sum to 16 steps)."""
    for s in strings:
        tot = sum(float(t.split("/")[0].lstrip("!~").split(":")[1]) for t in s.split() if not t.startswith("@"))
        assert abs(tot - 16) < 1e-6, (tot, s)
    return " ".join(strings)


# =============================================================================== material
# All melodies: semitones above the tonic (minor key). Harmonic minor; Hijaz on the 5th degree.
NIGHTS = dict(  # "Darbuka Nights" — warm, singalong, maqsum
    darb="maqsum", kick_verse="x.....x.x.......", kick_hook="x...x...x...x...", dembow=False,
    verse_prog=["i", "i", "iv", "V"],
    hook_prog=["i", "bVII", "bVI", "V", "iv", "V", "i", "i"],
    bd_prog=["i", "i", "V7", "V7", "iv", "i", "V7", "V7"],
    riff=bars("0:2 0:1 3:1 2:1 0:1 -1:1 0:1 3:2 5:2 7:2 5:1 3:1",
              "7:3/v 8:1/g+3 7:2 5:1 3:1 2:2/b-0.5 3:1 2:1 0:4/v",
              "5:2 5:1 8:1 7:1 5:1 3:1 5:1 8:2 12:2 11:1 12:1 8:2",
              "11:2/t+1 8:1 7:1 8:2 11:2 8:1 7:1 5:1 3:1 7:4/v,f-1"),
    hook_a=bars("7:3 7:1 8:2/g+3 7:2 5:2 3:2 5:2 7:2",
                "5:3 5:1 7:2 5:2 3:2 2:2 3:2 5:2",
                "3:3 3:1 5:2 3:2 2:2 0:2 2:2 3:2",
                "2:2 0:2 -1:3/t+1 -4:1/q+0.12 -5:8/v"),
    hook_b=bars("8:3 8:1 12:2 8:2 7:2 5:2 7:2 8:2",
                "11:3/g+1 11:1 12:2 11:2 8:2 7:2 8:2 11:2",
                "12:4/v 11:2 8:2 7:4/v 5:2 3:2",
                "2:2/g+1 3:2 2:1 0:1 -1:2 0:8/v"),
    # qanun fills (relative to the qanun register), placed with @step inside a 4-bar phrase
    qanun_fill=["@56 12:0.5 11:0.5 8:0.5 7:0.5 5:0.5 3:0.5 2:0.5 0:0.5 2:2/r 3:2/r",
                "@58 -5:0.5 -4:0.5 -1:0.5 0:0.5 2:0.5 3:0.5 5:0.5 7:0.5 8:0.5 11:0.5 12:4/r"],
    ney=[bars("-5:4/b-0.7 -4:2/q+0.12 -1:2 0:8/v", "r:4 0:2 2:2 3:4/v 2:2 0:2",
              "-1:4/t+1 -4:2/q+0.12 -5:10/v,f-1", "r:16"),
         bars("7:4/b-0.5 8:2/g+3 11:2 12:8/v", "r:2 11:2 12:2 14:2 15:4/v 14:2 12:2",
              "11:4/t+1 8:2 7:10/v", "5:2 3:2 2:2/b-0.5 0:10/v")],
    build_oud="7:32/r 8:32/r 11:32/r 12:16/r 14:16/r,v",
)

FIRE = dict(  # "Hijaz Fire" — driving dembow, saidi/malfuf, more ornaments
    darb="saidi", kick_verse="x...x...x...x...", kick_hook="x...x...x...x...", dembow=True,
    verse_prog=["i", "i", "iv", "V"],
    hook_prog=["i", "bVII", "bVI", "V", "iv", "V", "i", "i"],
    bd_prog=["i", "V7", "i", "iv", "V7", "iv", "V7", "V7"],
    riff=bars("0:1 0:1 3:1 2:1 0:1 2:1 3:1 5:1 7:2 8:1 7:1 5:1 3:1 2:1 3:1",
              "7:2/g+1 5:1 3:1 2:2/b-0.5 0:2 -1:1 0:1 2:1 -1:1 -4:2/q+0.12 -5:2/v",
              "5:1 5:1 8:1 7:1 5:1 7:1 8:1 10:1 12:2 10:1 8:1 7:1 5:1 7:2",
              "8:2/t+3 7:1 8:1 11:2 12:1 11:1 8:1 7:1 5:1 8:1 7:4/v,f-1"),
    hook_a=bars("!12:2 12:1 11:1 12:2 7:2 8:2 7:1 5:1 7:4/v",
                "10:2 10:1 8:1 10:2 5:2 7:2 5:1 3:1 5:4/v",
                "8:2 8:1 7:1 8:2 3:2 5:2 3:1 2:1 3:4/v",
                "2:2 3:1 2:1 -1:2/g+1 -4:2/q+0.12 -1:2 -4:1 -5:5/v,f-1"),
    hook_b=bars("5:2 5:1 7:1 8:2 7:2 5:2 3:1 2:1 3:4/v",
                "11:2/g+1 11:1 12:1 11:2 8:2 7:4/v 8:1 7:1 5:2",
                "3:2 2:1 3:1 5:2 3:2 2:2 0:2 -1:2 2:2",
                "0:4/g-1 2:1 0:1 -1:2 0:8/v,t+2"),
    qanun_fill=["@56 12:0.5 11:0.5 8:0.5 7:0.5 8:0.5 7:0.5 5:0.5 3:0.5 2:2/r 3:2/r",
                "@58 -1:0.5 0:0.5 2:0.5 3:0.5 5:0.5 7:0.5 8:0.5 11:0.5 12:0.5 11:0.5 12:3/r"],
    ney=[bars("7:4/b-0.6 8:2/q+0.12 11:2 12:8/v", "r:2 11:2 8:2 7:2/g+1 5:4 3:2 2:2",
              "0:12/v,f-1 r:4", "r:16"),
         bars("-5:4/b-0.5 -4:2/q+0.12 -1:2 0:6/v 2:2", "3:4/t+2 2:2 0:2 -1:2/g+1 -4:2/q+0.12 -5:4",
              "-5:16/v", "r:16")],
    build_oud="7:32/r 8:32/r 11:32/r 12:16/r 14:16/r,v",
)

SUNRISE = dict(  # "Mediterranean Sunrise" — warm, emotional, Andalusian cadence breakdown
    darb=["house", "maqsum"], swing=(52.0, 55.0),
    groove_prog=["i", "i", "bVI", "V"],
    drop_prog=["i", "i", "bVI", "V"],
    bd_prog=["i", "bVI", "iv", "V7"],
    hook=bars("0:2 r:1 0:1 3:1 2:1 0:1 r:1 -1:2/g+1 0:1 2:1 3:2 5:2",
              "7:3/v 5:1 3:1 2:1 3:2 2:1 0:1 -1:1 -4:1/q+0.12 -5:4/v"),
    hook2=bars("8:2 r:1 8:1 7:1 5:1 3:1 r:1 2:2 3:1 5:1 7:2 8:2",
               "11:3/t+1 8:1 7:1 5:1 7:2/v 5:1 3:1 2:1 -1:1 -5:4/v"),
    ney=[bars("7:12/b-0.6,v 8:4/g+3", "7:4 5:2 3:2 5:8/v", "3:4 2:2/b-0.5 3:2 0:8/v", "r:16"),
         bars("12:12/b-0.5,v 11:4", "12:4 14:2 15:2 14:8/v", "12:4 11:2/t+1 8:2 7:8/v", "r:16"),
         bars("15:8/b-0.5,v 14:4 12:4", "11:4/t+1 8:2 7:2 8:8/v", "7:4 5:2 3:2 2:4/b-0.5 0:4", "0:16/v")],
    bass=[(2, 1.5, 0, 1.0), (3, 1, 0, 0.55), (6, 1.5, 0, 0.9), (7, 1, 12, 0.5), (10, 1.5, 0, 1.0), (11, 1, 0, 0.55),
          (14, 1.5, 7, 0.85)],
    strings_line=bars("12:8/v 15:4 14:4", "12:12/v 11:4/t+1", "8:8/v 7:4 8:4", "7:16/v"),
)

OUDCLUB = dict(  # "Oud Club" — hypnotic oud pedal riff, tremolo oud melody, driving
    darb=["house", "ayoub"], swing=(50.0, 53.0),
    groove_prog=["i", "i", "iv", "V"],
    drop_prog=["i", "i", "iv", "V"],
    bd_prog=["i", "iv", "bVI", "V7"],
    hook=bars("0:1 0:1 7:1 0:1 8:1 0:1 7:1 5:1 3:1 0:1 2:1 3:1 2:1 0:1 -1:1/g+1 0:1",
              "0:1 0:1 7:1 0:1 8:1 0:1 11:1 12:1 11:1 8:1 7:1 5:1 3:2/v 2:1 -1:1"),
    hook2=bars("7:8/r 8:4/r 7:4/r", "5:8/r 3:4/r 2:4/r", "3:8/r 2:4/r 0:4/r", "-1:12/r,v 0:4/r"),
    ney=[bars("7:12/b-0.6,v 8:4/q+0.12", "7:4 5:2 3:2 2:8/v", "3:4 2:2 0:2 -1:4/t+1 0:4", "0:16/v"),
         bars("12:12/b-0.5,v 11:4", "8:4 11:2 12:2 14:8/v", "15:4 14:2 12:2 11:4/t+1 8:4", "7:16/v")],
    bass=[(2, 1, 0, 1.0), (3, 1, 0, 0.6), (5, 1, 12, 0.45), (6, 1, 0, 0.9), (7, 1, 0, 0.55), (10, 1, 0, 1.0),
          (11, 1, 0, 0.6), (13, 1, 12, 0.45), (14, 1, 0, 0.9), (15, 1, -2, 0.55)],
    strings_line=bars("7:8/v 8:4 7:4", "5:12/v 3:4", "3:8/v 2:4 0:4", "-1:16/v,t+1"),
)


# =============================================================================== shared helpers
def _chords(key_tonic: int, names: list[str], center: int) -> list[list[int]]:
    out, prev = [], None
    for nm in names:
        ch = voice_lead(prev, [key_tonic + s for s in CH[nm]], center=center)
        out.append(ch)
        prev = ch
    return out


def _bass_note(tonic_pc: int, name: str) -> int:
    return reg((tonic_pc + ROOT[name]) % 12, 28)


def _phrase(notes_str: str, base: int) -> tuple:
    return W.transpose(W.mel(notes_str), base)


def _fx_layer(song, rng, crash_kinds=("groove", "drop", "outro")):
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.14})
    crash = drums.crash(decay=float(rng.uniform(1.9, 2.6)), rng=rng)
    bar = song.grid.bar_sec
    for s in song.sections:
        if s.kind in crash_kinds:
            fxl.add(crash, s.start_bar, gain_db=-9.0)
        if s.kind == "drop":
            fxl.add(fx.impact(2.5, rng=rng), s.start_bar, gain_db=-8.0)
            for b in range(s.start_bar + 8, s.end_bar, 8):
                fxl.add(crash, b, gain_db=-14.0)
        nxt = song.section_after(s)
        if nxt is not None and nxt.kind == "drop" and s.kind in ("build", "breakdown"):
            nb = min(8, s.bars)
            fxl.add(fx.riser(bar * nb, "both", f_lo=250, f_hi=9000, rng=rng), s.end_bar, align="end", gain_db=-11.0)
            fxl.add(fx.reverse_cymbal(bar, rng=rng), s.end_bar, align="end", gain_db=-11.0)
        if s.kind == "breakdown":
            fxl.add(fx.downlifter(bar * 2, rng=rng), s.start_bar, gain_db=-13.0)
    return fxl


def _ramp_before(song, kind, bars_n, lo, hi):
    """gain automation: ``hi`` everywhere, ramp ``lo``→``hi`` over the bars before each ``kind``."""
    pts = [(0, hi)]
    for s in song.sections:
        if s.kind == kind or s.name == kind:
            pts += [(s.start_bar - bars_n - 0.001, hi), (s.start_bar - bars_n, lo), (s.start_bar - 0.001, hi)]
    return pts


@register("mediterranean")
def build(plan: dict, rng: np.random.Generator):
    if "house" in str(plan.get("genre", "")).lower() or float(plan["bpm"]) >= 115:
        return build_house(plan, rng)
    return build_groove(plan, rng)


# =============================================================================== GROOVE (100–104)
TPL_GROOVE = [("Intro", "intro", 16, 4, 0), ("Verse", "groove", 16, 6, 3), ("Build", "build", 8, 7, 0),
              ("Hook", "drop", 16, 8, 1), ("Breakdown", "breakdown", 8, 5, 0), ("Hook 2", "drop", 16, 9, 2),
              ("Outro", "outro", 16, 4, 0)]


def build_groove(plan, rng):
    from ..arrangement import Song

    fire = int(plan.get("energy", 7)) >= 8
    M = FIRE if fire else NIGHTS
    song = Song(plan, rng, swing=float(rng.choice([52.0, 54.0, 55.0]) if not fire else rng.choice([51.0, 53.0])))
    song.arrange(TPL_GROOVE, song.target_bars())
    key = song.key
    pc = key.root_pc
    verse, buildsec, hook = song.find("groove"), song.find("build"), song.find("drop")
    outro = song.find("outro")
    song.mix_in_bar = verse.start_bar

    T_lead = reg(pc, 62)       # E4 / A4 ...
    T_oud = reg(pc, 50)        # E3 / A3
    T_q = reg(pc, 69)          # qanun register
    T_ney = reg(pc, 60)

    def prog_at(c):
        if c.kind == "groove":
            return M["verse_prog"][c.i % 4]
        if c.kind == "build":
            return "V7"
        if c.kind == "drop":
            return M["hook_prog"][c.i % 8]
        if c.kind == "breakdown":
            return M["bd_prog"][c.i % 8]
        return None

    # ------------------------------------------------------------------ drums
    kick_s = drums.kick("house", tune_hz=W.kick_tune(key), decay=float(rng.uniform(0.3, 0.36)),
                        click=float(rng.uniform(0.35, 0.5)), drive=1.5, rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown":
            return None
        if c.kind == "build":
            if c.bars_left == 1:
                return None
            return "x.x.x.x.x.x.x.x." if c.bars_left <= 3 else "x...x...x...x..."
        if c.kind == "drop":
            return M["kick_hook"] if not c.before("breakdown", 1) else "x...x...x......."
        if c.kind == "groove":
            return M["kick_verse"] if not c.last else M["kick_verse"][:12] + "x.x."
        if c.kind == "outro" and c.bars_left <= 2 and not fire:
            return "x.....x.x......."
        return M["kick_verse"]

    song.hits("kick", kick_s, kick_pat, gain_db=-2.5, sc_source=True, humanize=0.0)

    # darbuka — the heart of the groove
    kit = W.darbuka_kit(rng, pitch=float(rng.uniform(0.95, 1.06)), metal=float(rng.uniform(0.4, 0.7)))
    base = W.RHYTHMS[M["darb"]]
    orn = base[1:]
    fills = W.FILLS["fill"]
    fpick = int(rng.integers(len(fills)))

    def darb_pat(c):
        k = c.kind
        if k == "intro":
            if c.phrase_end:
                return fills[(fpick + c.i // 8) % len(fills)]
            return base[0] if c.i < 8 else orn[(c.i // 2) % len(orn)]
        if k == "build":
            j = c.i * 4 // c.section.bars
            if c.bars_left == 1:
                return W.FILLS["roll32"][0]
            if c.bars_left == 2:
                return W.FILLS["build"][2]
            return [orn[0], W.FILLS["build"][0], W.FILLS["build"][1], W.FILLS["build"][2]][j]
        if k == "breakdown":
            if c.bars_left == 1:
                return W.FILLS["roll24"][0]
            if c.bars_left == 2:
                return W.FILLS["build"][2]
            if c.i < 2:
                return None
            ch = W.RHYTHMS["chiftetelli"][int(fire)]
            return ch[c.i % 2]
        if k == "outro":
            if c.bars_left <= 1:
                return "D.T...T.D..............."[:16]
            if c.phrase_end:
                return fills[(fpick + 1) % len(fills)]
            return orn[(c.i // 2) % len(orn)] if c.i < 8 else base[0]
        # groove / drop
        if c.before("build") or c.before("breakdown"):
            return W.FILLS["fill"][1]
        if c.phrase_end:
            return fills[(fpick + c.i // 8 + (k == "drop")) % len(fills)]
        if c.every(4):
            return orn[-1]
        if fire and k == "drop" and c.phrase % 2 == 1:
            return W.RHYTHMS["malfuf"][1 + (c.i % 2)]
        return orn[c.i % len(orn)]

    dlay = W.add_darbuka(song, darb_pat, kit, gain_db=-3.5, pan=0.05, levels={"D": -3.0, "T": 2.0, "K": -2.5, "S": 0.0},
                         sends={"room": 0.12, "reverb": 0.04}, humanize=0.08, timing_ms=1.5)
    dlay["D"].hp = 55.0
    for st in ("T", "K"):
        dlay[st].automate("gain_db", _ramp_before(song, "drop", 2, -7.0, 0.0))

    # riq: tak on the off-beats, jingles in between
    riq_tak = [W.riq("tak", np.random.default_rng(int(rng.integers(1 << 31)))) for _ in range(3)]
    riq_j = [W.riq("jingle", np.random.default_rng(int(rng.integers(1 << 31)))) for _ in range(4)]

    def riq_tak_pat(c):
        if c.kind == "breakdown" or (c.kind == "intro" and c.i < 4) or (c.kind == "outro" and c.bars_left <= 4):
            return None
        return "..x...x...x...x." if c.kind != "drop" else "..x...x...x.x.x."

    def riq_j_pat(c):
        if c.kind == "build" and c.bars_left <= 2:
            return "o" * 16
        if c.kind == "breakdown":
            return "g.....g.g.....g." if 2 <= c.i < c.section.bars - 2 else None
        if c.kind == "intro" and c.i < 2:
            return None
        return "g.og.gogg.og.gog" if c.kind != "drop" else "gxogoxogoxogoxoo"

    song.hits("riq_tak", riq_tak, riq_tak_pat, gain_db=-12.0, pan=-0.32, sends={"room": 0.1}, humanize=0.1, timing_ms=2)
    song.hits("riq_jingle", riq_j, riq_j_pat, gain_db=-15.0, pan=0.38, humanize=0.15, timing_ms=3)

    # crowd claps (party): backbeat, every beat in the last phrase of Hook 2
    claps = [W.crowd_clap(int(rng.integers(4, 7)), rng=np.random.default_rng(int(rng.integers(1 << 31)))) for _ in range(3)]

    def clap_pat(c):
        if c.kind in ("breakdown",) or (c.kind == "intro" and c.i < 8) or (c.kind == "outro" and c.bars_left <= 8):
            return None
        if c.kind == "build":
            return "....x.......x..." if c.bars_left > 2 else ("x...x...x...x..." if c.bars_left == 2 else "x.x.x.x.xxxxxxxx")
        if c.kind == "drop" and c.section.name == "Hook 2" and c.i >= c.section.bars - 8:
            return "x...x...x...x..."
        return "....x.......x..." if not c.phrase_end else "....x.......x.x."

    song.hits("claps", claps, clap_pat, gain_db=-6.5, sends={"room": 0.18, "reverb": 0.08}, timing_ms=2.0)

    if M["dembow"]:
        snr = drums.snare(tone_hz=float(rng.uniform(190, 230)), snappy=0.7, decay=0.1, kind="tight", rng=rng)
        song.hits("dembow_snare", snr,
                  lambda c: "...x..x....x..x." if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 8)
                  or (c.kind == "outro" and c.bars_left > 8) else None,
                  gain_db=-11.0, pan=0.1, sends={"room": 0.12})
    rim = drums.rimshot(float(rng.uniform(1500, 1800)), rng=rng)
    song.hits("rim", rim, lambda c: "...x..x....x..x." if (not M["dembow"]) and c.kind == "drop" else None,
              gain_db=-17.0, pan=0.25, sends={"delay8": 0.1})

    shk = drums.variants(drums.shaker, 3, rng, jitter={"length": 0.2}, length=float(rng.uniform(0.07, 0.09)))
    song.hits("shaker", shk, lambda c: "gogxgogxgogxgogx" if c.kind in ("groove", "drop", "build")
              or (c.kind == "intro" and c.i >= 8) or (c.kind == "outro" and c.bars_left > 8) else None,
              gain_db=-19.0, pan=-0.55, humanize=0.15, timing_ms=2.0)

    hat = drums.hat(decay=0.035, tone=float(rng.uniform(1.0, 1.15)), rng=rng)
    song.hits("hat", hat, lambda c: "x.x.x.x.x.x.x.x." if c.kind == "drop" else None, gain_db=-20.0, pan=0.2)

    zl = W.zills(rng=rng)

    def zill_pat(c):
        if c.kind == "drop":
            return "x.x.x..........." if c.i % 4 == 0 else ("........x.x.x..." if c.i % 4 == 2 else None)
        if c.kind == "breakdown":
            return "x..............." if c.i % 2 == 0 else None
        if c.kind in ("intro", "groove", "outro") and c.i % 8 == 0 and c.i > 0:
            return "x..............."
        return None

    song.hits("zills", zl, zill_pat, gain_db=-17.0, pan=0.45, sends={"hall": 0.3, "delay": 0.1})

    # ------------------------------------------------------------------ bass (maqsum-pop / dembow)
    if M["dembow"]:
        brh = [(0, 2.5, 0, 1.0), (3, 2, 0, 0.8), (6, 1.5, 12, 0.7), (8, 2.5, 0, 0.95), (11, 2, 0, 0.8), (14, 2, 7, 0.75)]
    else:
        brh = [(0, 3, 0, 1.0), (3, 1, 0, 0.6), (6, 2, 12, 0.8), (8, 3, 0, 0.95), (11, 1, 0, 0.6), (12, 2, 7, 0.8),
               (14, 2, 12, 0.7)]
    bass_i = inst.bass_pluck(cutoff=float(rng.uniform(150, 190)), env_amt=float(rng.uniform(500, 800)),
                             decay=float(rng.uniform(0.1, 0.14)), res=0.2, sub=1.3, drive=1.3, grit=0.2,
                             sustain=0.5, wave="saw")

    def bass_notes(c):
        if c.kind in ("intro", "outro", "breakdown"):
            return []
        nm = prog_at(c)
        r = _bass_note(pc, nm)
        if c.kind == "build":
            ev = [(s, 1.5, r + (12 if s % 4 == 2 else 0), 0.8 + 0.2 * (s % 4 == 0)) for s in range(0, 16, 2)]
            return ev if c.bars_left > 1 else ev[:4]
        ev = [(s, l, r + o, v) for s, l, o, v in brh]
        if c.before("build") or c.before("breakdown"):
            ev = [e for e in ev if e[0] < 8]
        return ev

    bass = song.notes("bass", bass_i, bass_notes, bus="bass", gain_db=-4.5, sidechain=0.3, sc_release_ms=90.0,
                      humanize=0.03)
    b0 = buildsec.start_bar
    bass.automate("lp", [(verse.start_bar, 700), (b0, 700), (hook.start_bar - 0.01, 2400), (hook.start_bar, 5000)])
    song.notes("bd_sub", inst.sub_bass(), lambda c: [(0, 63, reg(pc, 28), 0.55)] if c.kind == "breakdown" and c.i == 0
               else [], bus="bass", gain_db=-14.0)

    # ------------------------------------------------------------------ harmony: strings pad
    center = reg(pc, 57) + 2
    pad_i = W.strings_pad(attack=float(rng.uniform(0.35, 0.6)), release=1.4, cutoff=float(rng.uniform(2800, 3600)))

    def pad_notes(c):
        nm = prog_at(c)
        if nm is None:
            return []
        ch = voice_lead(None, [reg(pc, 52) + s for s in CH[nm]], center=center)
        if c.kind == "breakdown":
            return [(0, 16, ch, 0.8)]
        if c.kind == "build":
            return [(0, 16, ch + [ch[0] + 12], 0.6 + 0.3 * c.progress())]
        if c.kind == "drop":
            return [(0, 16, ch, 0.65)]
        return [(0, 16, ch, 0.5)] if c.i >= 4 else []

    pad = song.notes("strings_pad", pad_i, pad_notes, gain_db=-12.5, sends={"hall": 0.28}, width=1.5, sidechain=0.2)
    pad.automate("gain_db", song.section_points({"breakdown": 2.0, "build": 0.0, "drop": -1.0, "groove": -2.0}, 0.0,
                                                ramp_bars=1))

    # ------------------------------------------------------------------ oud riff (verse), tremolo (build)
    oud_i = W.oud(t60=float(rng.uniform(1.3, 1.8)))
    riff = _phrase(M["riff"], T_oud)
    riff_hi = _phrase(M["riff"], T_oud + 12)
    build_oud = _phrase(M["build_oud"], T_oud)
    hook_low_a = _phrase(M["hook_a"].replace("/v", "").replace(",v", ""), T_lead - 12)
    hook_low_b = _phrase(M["hook_b"].replace("/v", "").replace(",v", ""), T_lead - 12)

    def oud_phr(c):
        if c.kind == "groove" and c.i % 4 == 0:
            return [(0, riff_hi if (c.i // 4) % 4 == 2 else riff, 1.0)]
        if c.kind == "build" and c.i == 0:
            return [(0, build_oud, 0.9)]
        if c.kind == "drop" and c.i % 8 == 0:
            return [(0, hook_low_a, 0.8)]
        if c.kind == "drop" and c.i % 8 == 4:
            return [(0, hook_low_b, 0.8)]
        return []

    W.add_phrases(song, "oud", oud_i, oud_phr, gain_db=-7.0, pan=-0.12, sends={"room": 0.14, "reverb": 0.08},
                  lookback=9, width=1.3, sidechain=0.15)

    # ------------------------------------------------------------------ qanun fills / arpeggios
    q_i = W.qanun(t60=float(rng.uniform(1.8, 2.6)))
    qf = [_phrase(s, T_q) for s in M["qanun_fill"]]
    arp_cache = {}

    def q_arp(nm):
        if nm not in arp_cache:
            tones = sorted(reg((pc + s) % 12, T_q - 7) for s in CH[nm])
            seq = [tones[0], tones[1], tones[2], tones[0] + 12, tones[2], tones[1]]
            arp_cache[nm] = tuple((i * 1.0, 1.4, float(seq[i % 6]), 0.62 if i % 4 else 0.78, "") for i in range(16))
        return arp_cache[nm]

    def q_phr(c):
        out = []
        if c.kind in ("groove", "drop") and c.i % 4 == 0 and c.bars_left >= 4:
            out.append((0, qf[(c.i // 4) % 2], 0.85))
        if c.kind == "drop" and c.section.name == "Hook 2" and c.i % 4 in (0, 1, 2):
            out.append((0, q_arp(prog_at(c)), 0.6))
        return out

    W.add_phrases(song, "qanun", q_i, q_phr, gain_db=-11.0, pan=0.3, sends={"reverb": 0.14, "delay8": 0.08},
                  lookback=5, width=1.4, sidechain=0.2)

    # ------------------------------------------------------------------ Mizrahi keyboard lead (the hook)
    lead_i = W.mizrahi_lead(vib_depth=float(rng.uniform(0.28, 0.36)), vib_rate=float(rng.uniform(5.8, 6.4)),
                            drive=1.9 if fire else 1.5, nasal=float(rng.uniform(0.5, 0.7)))
    hk_a, hk_b = _phrase(M["hook_a"], T_lead), _phrase(M["hook_b"], T_lead)

    def lead_phr(c):
        if c.kind == "drop" and c.i % 4 == 0:
            return [(0, hk_a if (c.i // 4) % 2 == 0 else hk_b, 1.0)]
        return []

    W.add_phrases(song, "mizrahi_lead", lead_i, lead_phr, bus="vox", gain_db=-5.5, sends={"reverb": 0.14, "delay": 0.1},
                  lookback=5, sidechain=0.12)

    # Arabic string section doubling the hook (2nd half of Hook, octave up in Hook 2)
    su_i = W.strings_unison(voices=7)

    def su_phr(c):
        if c.kind != "drop" or c.i % 4:
            return []
        if c.section.name == "Hook" and c.i < 8:
            return []
        up = 12 if c.section.name != "Hook" else 0
        ph = M["hook_a"] if (c.i // 4) % 2 == 0 else M["hook_b"]
        return [(0, _phrase(ph, T_lead + up), 0.9)]

    W.add_phrases(song, "strings_line", su_i, su_phr, gain_db=-9.5, sends={"hall": 0.22, "reverb": 0.08}, lookback=5,
                  width=1.3, sidechain=0.15)

    # ney taqsim in the breakdown (and an echo in the build)
    ney_i = W.ney(breath=float(rng.uniform(0.3, 0.42)))
    ney_ph = [_phrase(s, T_ney) for s in M["ney"]]

    def ney_phr(c):
        if c.kind == "breakdown" and c.i % 4 == 0:
            return [(0, ney_ph[(c.i // 4) % 2], 1.0)]
        return []

    W.add_phrases(song, "ney", ney_i, ney_phr, gain_db=-5.0, pan=0.08, sends={"hall": 0.38, "delay": 0.16},
                  lookback=5)

    # ------------------------------------------------------------------ fx
    _fx_layer(song, rng)
    song.buses["drums"].eq = [("peak", 3200.0, 1.5, 0.8), ("peak", 250.0, -1.5, 1.0)]
    song.buses["music"].eq = [("peak", 2000.0, 1.0, 0.8)]
    song.buses["drums"].width = 1.2
    song.master.lufs = -9.0

    rh = {"maqsum": "מקסום", "saidi": "סעידי"}[M["darb"]]
    tonic_name = plan["key"].split()[0]
    dom_name = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][(pc + 7) % 12]
    song.instruments = ["darbuka (doum/tek/ka/slap)", "riq", "finger cymbals (zills)", "crowd claps",
                        "maqsum-pop kick" if not fire else "dembow kick & snare", "Mizrahi synth bass",
                        "oud (Karplus-Strong)", "qanun runs", "ney", "Arabic strings (pad + unison)",
                        "Mizrahi keyboard lead"]
    if fire:
        song.description_he = (
            f"גרוב ים-תיכוני לוהט ב-{int(song.bpm)} BPM בסולם {tonic_name} מינור: דרבוקה על מקצב {rh} שעובר למלפוף "
            f"בפזמון, קיק וסנר דמבו, רִק, זילים ומחיאות כפיים של קהל. המנגינות במינור הרמוני (נהוונד) עם חיג'אז על "
            f"הדרגה החמישית ({dom_name}) — טרילים, תווי חסד, גלישות ובנדים של רבע טון. עוד בטרמולו בבילד, "
            f"קאנון בריצות, נאי בברייקדאון, ולידים של קלידים מזרחיים בפזמון סינגלונג גדול.")
    else:
        song.description_he = (
            f"גרוב ים-תיכוני חם ב-{int(song.bpm)} BPM בסולם {tonic_name} מינור: הדרבוקה היא הלב — דום, טק וקה על "
            f"מקצב {rh} עם סלסולים ותופים מתגלגלים, ובברייקדאון צ'יפטטלי איטי. רִק, זילים ומחיאות כפיים, קיק ובאס "
            f"בסגנון מזרחי-פופ. מלודיות במינור הרמוני (מקאם נהוונד) עם חיג'אז על הדרגה החמישית ({dom_name}): "
            f"ריף עוד, ריצות קאנון, טקסים של נאי וליד קלידים מזרחי עם ויברטו ופורטמנטו בפזמון.")
    hook2 = song.find("Hook 2")
    nb = song.find("breakdown")
    song.mix_tips_he = (
        f"טיפ ערבוב: אינטרו של {song.sections[0].bars} תיבות תופים ודרבוקה בלבד — מכניסים מעל האאוטרו של הטראק הקודם. "
        f"הבאס והעוד נכנסים בתיבה {verse.start_bar + 1} (Hot Cue B), הבילד עם גלגולי דרבוקה בתיבה {buildsec.start_bar + 1}, "
        f"הפזמון הגדול בתיבה {hook.start_bar + 1} (Hot Cue D), ברייקדאון עם נאי בתיבה {nb.start_bar + 1} ופזמון 2 בתיבה "
        f"{hook2.start_bar + 1}. אאוטרו של {outro.bars} תיבות תופים בלבד מתיבה {outro.start_bar + 1}. "
        f"שכנים הרמוניים ב-Camelot: {plan['camelot']} ↔ " + ", ".join(_neighbours(plan["camelot"])) + ".")
    return song


def _neighbours(cam: str) -> list[str]:
    from ..theory import compatible_keys
    return compatible_keys(cam)[1:4]


# =============================================================================== HOUSE (124–125)
TPL_HOUSE_A = [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 16, 6, 2), ("Breakdown", "breakdown", 16, 4, 0),
               ("Drop", "drop", 32, 8, 3), ("Outro", "outro", 32, 4, 0)]
TPL_HOUSE_B = [("Intro", "intro", 32, 4, 0), ("Groove", "groove", 16, 6, 2), ("Breakdown", "breakdown", 8, 4, 0),
               ("Drop", "drop", 16, 8, 3), ("Breakdown 2", "breakdown", 8, 5, 0), ("Drop 2", "drop", 16, 9, 1),
               ("Outro", "outro", 32, 4, 0)]


def build_house(plan, rng):
    from ..arrangement import Song

    club = int(plan.get("energy", 7)) >= 8
    M = OUDCLUB if club else SUNRISE
    song = Song(plan, rng, swing=float(rng.uniform(*M["swing"])))
    song.arrange(TPL_HOUSE_B if club else TPL_HOUSE_A, song.target_bars())
    key = song.key
    pc = key.root_pc
    groove, drop = song.find("groove"), song.find("drop")
    outro = song.find("outro")
    song.mix_in_bar = groove.start_bar
    T_oud = reg(pc, 55) if club else reg(pc, 60)
    T_ney = reg(pc, 60)
    T_q = reg(pc, 69)
    T_str = reg(pc, 62)

    def prog_at(c):
        if c.kind == "groove":
            return M["groove_prog"][(c.i // 2) % 4]
        if c.kind == "drop":
            return M["drop_prog"][(c.i // 2) % 4]
        if c.kind == "breakdown":
            return M["bd_prog"][(c.i // 2) % 4]
        return None

    # ------------------------------------------------------------------ drums
    kick_s = drums.kick("deep" if not club else "house", tune_hz=W.kick_tune(key),
                        decay=float(rng.uniform(0.36, 0.44)), click=float(rng.uniform(0.3, 0.45)), rng=rng)

    def kick_pat(c):
        if c.kind == "breakdown":
            return None
        if c.before("breakdown", 1) or c.before("drop", 1):
            return "x...x...x......." if c.before("breakdown", 1) else None
        return "x...x...x...x..."

    song.hits("kick", kick_s, kick_pat, gain_db=-2.0, sc_source=True, humanize=0.0)

    hats = drums.variants(drums.hat, 3, rng, jitter={"decay": 0.15}, decay=float(rng.uniform(0.03, 0.045)),
                          tone=float(rng.uniform(0.95, 1.1)))
    song.hits("hats", hats, lambda c: ("gogxgogxgogxgogx" if c.kind in ("drop", "groove") or (c.kind == "intro" and c.i >= 8)
                                       or (c.kind == "outro" and c.bars_left > 8) else None),
              gain_db=-16.0, pan=0.3, humanize=0.12)
    ohat = drums.hat(open_=True, decay=float(rng.uniform(0.16, 0.22)), rng=rng)
    song.hits("open_hat", ohat, lambda c: "..x...x...x...x." if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 16)
              or (c.kind == "outro" and c.bars_left > 16) else None, gain_db=-13.0, pan=-0.15, sends={"room": 0.1})
    snap = [W.finger_snap(np.random.default_rng(int(rng.integers(1 << 31)))) for _ in range(2)]
    clap = drums.clap(tone_hz=float(rng.uniform(1100, 1350)), tail=0.16, rng=rng)
    song.hits("clap", clap, lambda c: "....x.......x..." if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 16)
              or (c.kind == "outro" and c.bars_left > 8) else None, gain_db=-6.5, sends={"reverb": 0.2, "room": 0.1})
    song.hits("snap", snap, lambda c: "....x..g....x..." if c.kind == "drop" or (c.kind == "breakdown" and c.bars_left <= 4)
              else None, gain_db=-14.0, pan=0.2, sends={"reverb": 0.25})
    shk = drums.variants(drums.shaker, 3, rng, jitter={"length": 0.2}, length=float(rng.uniform(0.07, 0.1)))
    song.hits("shaker", shk, lambda c: None if c.kind == "breakdown" or (c.kind == "intro" and c.i < 8) else "gxgogxgogxgogxgo",
              gain_db=-18.0, pan=-0.5, humanize=0.15, timing_ms=2.0)

    # darbuka on top of the house groove (doum kept light so the kick owns the low end)
    kit = W.darbuka_kit(rng, pitch=float(rng.uniform(1.0, 1.1)), metal=float(rng.uniform(0.45, 0.7)))
    hpat = W.RHYTHMS["house"]
    alt = W.RHYTHMS[M["darb"][1]]
    hp0 = int(rng.integers(len(hpat)))

    def darb_pat(c):
        k = c.kind
        if k == "intro":
            if c.i < 8:
                return None
            if c.phrase_end:
                return W.FILLS["fill"][c.i // 8 % 4]
            return hpat[(hp0 + c.i // 4) % len(hpat)]
        if k == "breakdown":
            if c.bars_left == 1:
                return W.FILLS["roll32"][0]
            if c.bars_left == 2:
                return W.FILLS["build"][2]
            if c.bars_left <= 4:
                return W.FILLS["build"][1]
            return None if c.i < c.section.bars // 2 else W.RHYTHMS["chiftetelli"][0][c.i % 2]
        if k == "outro":
            if c.bars_left <= 8:
                return None
            return hpat[(hp0 + c.i // 4) % len(hpat)] if not c.phrase_end else W.FILLS["fill"][2]
        if c.phrase_end:
            return W.FILLS["fill"][(c.i // 8) % 4]
        if k == "drop" and c.phrase % 2 == 1:
            return alt[c.i % len(alt)]
        return hpat[(hp0 + c.i // 4) % len(hpat)]

    dl = W.add_darbuka(song, darb_pat, kit, gain_db=-7.0, pan=-0.1, levels={"D": -5.0, "T": 0.0, "K": -4.0, "S": -3.0},
                       sends={"room": 0.14, "delay8": 0.04}, humanize=0.1, timing_ms=1.5)
    dl["D"].hp = 90.0
    for st in ("T", "K"):
        dl[st].automate("gain_db", _ramp_before(song, "drop", 2, -8.0, 0.0))

    congas = [drums.conga(float(rng.uniform(190, 230)), "open", rng=rng), drums.conga(float(rng.uniform(280, 320)), "slap", rng=rng),
              drums.conga(float(rng.uniform(240, 270)), "mute", rng=rng)]
    cpat = ["...x..x...x.x...", "..x..x....x..x.x", "...x.x....x...x."][int(rng.integers(3))]
    song.hits("congas", congas, lambda c: cpat if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 16)
              or (c.kind == "outro" and 8 < c.bars_left <= 24) else None,
              gain_db=-13.0, pan=0.55, sends={"room": 0.15}, humanize=0.12, timing_ms=2.5)
    riq_j = [W.riq("jingle", np.random.default_rng(int(rng.integers(1 << 31)))) for _ in range(4)]
    song.hits("riq", riq_j, lambda c: "g.o.g.x.g.o.g.xo" if c.kind == "drop" or (c.kind == "intro" and c.i >= 24)
              or (c.kind == "groove" and c.i >= 8) or (c.kind == "outro" and c.bars_left > 16) else None,
              gain_db=-16.0, pan=0.42, humanize=0.15, timing_ms=3)
    zl = W.zills(rng=rng)
    song.hits("zills", zl, lambda c: "x..............." if (c.i % 8 == 0 and c.kind in ("groove", "drop", "breakdown")) else None,
              gain_db=-17.0, pan=-0.4, sends={"hall": 0.35, "delay": 0.12})
    tom = drums.tom(float(rng.uniform(95, 120)), 0.4, rng=rng)
    song.hits("tom_fill", tom, lambda c: "..........x.x.xx" if c.phrase_end and c.i % 16 == 15 and c.kind in ("groove", "drop")
              else None, gain_db=-14.0, sends={"reverb": 0.15})

    # ------------------------------------------------------------------ deep rolling bass
    bass_i = inst.bass_pluck(cutoff=float(rng.uniform(180, 240)), env_amt=float(rng.uniform(600, 1100)),
                             decay=float(rng.uniform(0.1, 0.15)), res=0.3, sub=1.0, drive=1.3, grit=0.22,
                             sustain=0.4, wave=str(rng.choice(["saw", "square"])))
    bass_off = outro.start_bar

    def bass_notes(c):
        if c.kind in ("intro", "outro") or c.bar >= bass_off:
            return []
        nm = prog_at(c)
        r = _bass_note(pc, nm)
        if c.kind == "breakdown":
            if c.bars_left > 2:
                return [(0, 15.5, r, 0.55)] if c.i % 2 == 0 else []
            return []
        ev = [(s, l, r + o, v) for s, l, o, v in M["bass"]]
        if c.before("breakdown") or c.before("drop"):
            ev = [e for e in ev if e[0] < 8]
        return ev

    bass = song.notes("bass", bass_i, bass_notes, bus="bass", gain_db=-4.0, sidechain=0.6, sc_release_ms=140.0,
                      humanize=0.03)
    pts = [(groove.start_bar, 280), (groove.start_bar + 8, 600)]
    for s in song.sections:
        if s.kind == "drop":
            pts += [(s.start_bar - 0.01, 900), (s.start_bar, 2200)]
        if s.kind == "breakdown":
            pts += [(s.start_bar, 260)]
    bass.automate("lp", pts)

    # ------------------------------------------------------------------ pads (wide, atmospheric) + strings
    center = reg(pc, 57) + 3
    pad_i = inst.pad(attack=float(rng.uniform(0.8, 1.4)), release=2.0, cutoff=float(rng.uniform(1200, 1800)),
                     detune=0.28, warmth=0.6)

    def pad_notes(c):
        nm = prog_at(c)
        if nm is None or c.i % 2:
            return []
        ch = voice_lead(None, [reg(pc, 50) + s for s in CH[nm]], center=center)
        if c.kind == "groove" and c.i < 8:
            return []
        return [(0, 31.5, ch, 0.75 if c.kind == "breakdown" else 0.6)]

    pad = song.notes("pad", pad_i, pad_notes, gain_db=-12.0, sends={"hall": 0.3}, width=1.7, sidechain=0.45)
    lpp = []
    for s in song.sections:
        if s.kind == "breakdown":
            lpp += [(s.start_bar, 700), (s.end_bar - 0.01, 5000)]
        elif s.kind == "drop":
            lpp += [(s.start_bar, 3500)]
        elif s.kind == "groove":
            lpp += [(s.start_bar, 900), (s.end_bar - 0.01, 2500)]
    pad.automate("lp", lpp)

    str_i = W.strings_pad(attack=0.7, release=1.8, cutoff=3200.0)

    def str_notes(c):
        if c.kind == "breakdown" and c.i % 2 == 0:
            nm = prog_at(c)
            ch = voice_lead(None, [reg(pc, 50) + s for s in CH[nm]], center=center + 5)
            return [(0, 31.5, ch + [ch[0] + 12], 0.85)]
        return []

    song.notes("strings_pad", str_i, str_notes, gain_db=-10.0, sends={"hall": 0.32}, width=1.6)

    # ------------------------------------------------------------------ oud hook
    oud_i = W.oud(t60=float(rng.uniform(1.4, 1.9)))
    hook = _phrase(M["hook"], T_oud)
    hook2 = _phrase(M["hook2"], T_oud if club else T_oud)
    hook_lo = _phrase(M["hook"], T_oud - 12)

    def oud_phr(c):
        if c.kind == "groove":
            if club:
                return [(0, hook, 0.85)] if c.i % 2 == 0 and c.i >= 4 else []
            return [(0, hook, 0.9)] if c.i % 2 == 0 and c.i >= 8 else []
        if c.kind == "drop":
            if club:
                if c.phrase % 2 == 0:
                    return [(0, hook, 0.9)] if c.i % 2 == 0 else []
                return [(0, hook2, 1.0)] if c.i % 4 == 0 else []
            ph = hook if (c.i // 2) % 4 in (0, 1, 2) else hook2
            return [(0, ph, 1.0)] if c.i % 2 == 0 else []
        if c.kind == "breakdown" and c.bars_left <= 4 and c.i % 2 == 0:
            return [(0, hook_lo, 0.7)]
        return []

    oud = W.add_phrases(song, "oud", oud_i, oud_phr, gain_db=-6.5, pan=-0.1, sends={"room": 0.12, "delay": 0.14},
                        lookback=5, width=1.25, sidechain=0.3)
    oud.automate("lp", [(groove.start_bar, 2500), (groove.end_bar - 0.01, 6000), (drop.start_bar, 9000)])

    # strings unison line over the drop (2nd half) — the emotional lift
    su_i = W.strings_unison(voices=7, attack=0.12)
    sline = W.stretch(_phrase(M["strings_line"], T_str), 2.0)

    def su_phr(c):
        if c.kind == "drop" and c.i % 8 == 0 and (c.phrase % 2 == 1 or club):
            return [(0, sline, 0.85)]
        return []

    W.add_phrases(song, "strings_line", su_i, su_phr, gain_db=-11.0, sends={"hall": 0.3}, lookback=9, width=1.5,
                  sidechain=0.3)

    # qanun rolling arpeggio (drop) — 16ths through the chord with delay
    q_i = W.qanun(t60=1.6)
    arp_cache = {}

    def q_arp(nm):
        if nm not in arp_cache:
            tones = sorted(reg((pc + s) % 12, T_q - 7) for s in CH[nm])
            seq = [tones[0], tones[1], tones[2], tones[0] + 12, tones[1] + 12, tones[2], tones[1], tones[0] + 12]
            arp_cache[nm] = tuple((i * 1.0, 1.2, float(seq[i % len(seq)]), 0.7 if i % 4 == 0 else 0.5, "")
                                  for i in range(16))
        return arp_cache[nm]

    def q_phr(c):
        if c.kind == "drop" and not (club and c.section.name == "Drop" and c.phrase == 0):
            return [(0, q_arp(prog_at(c)), 0.7)]
        return []

    W.add_phrases(song, "qanun", q_i, q_phr, gain_db=-14.0, pan=0.35, sends={"delay": 0.18, "reverb": 0.12},
                  lookback=2, width=1.5, sidechain=0.35)

    # ney: call in the groove, solo in the breakdown(s)
    ney_i = W.ney(breath=float(rng.uniform(0.32, 0.45)), vib_depth=0.2)
    ney_ph = [_phrase(s, T_ney) for s in M["ney"]]

    def ney_phr(c):
        if c.kind == "breakdown" and c.i % 4 == 0 and c.bars_left > 2:
            return [(0, ney_ph[(c.i // 4) % len(ney_ph)], 1.0)]
        if c.kind == "groove" and c.i == 0:
            return [(0, ney_ph[0], 0.75)]
        return []

    W.add_phrases(song, "ney", ney_i, ney_phr, gain_db=-6.0, pan=0.12, sends={"hall": 0.4, "delay": 0.2}, lookback=5)

    # ------------------------------------------------------------------ fx
    _fx_layer(song, rng)
    song.buses["drums"].eq = [("peak", 3000.0, 1.5, 0.8)]
    song.buses["drums"].width = 1.2
    song.buses["music"].width = 1.15
    song.master.lufs = -9.0
    tonic_name = plan["key"].split()[0]
    dom_name = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][(pc + 7) % 12]
    song.instruments = ["deep house kick", "darbuka on top", "congas", "riq", "zills", "clap & snaps", "shaker",
                        "deep rolling bass", "oud hook (Karplus-Strong)", "qanun arpeggios", "ney",
                        "Arabic strings", "wide pads"]
    bd = song.find("breakdown")
    if club:
        song.description_he = (
            f"האוס ים-תיכוני מועדוני ב-{int(song.bpm)} BPM בסולם {tonic_name} מינור: ריף עוד היפנוטי על צליל עוגב (פדאל) "
            f"בחיג'אז על {dom_name}, ובדרופ השני מנגינת עוד בטרמולו עם קשתות. קיק ארבע-על-הרצפה, דרבוקה וקונגות מעל, "
            f"באס מתגלגל עמוק, ריק וזילים. שני ברייקדאונים קצרים עם נאי וצ'יפטטלי.")
    else:
        song.description_he = (
            f"האוס ים-תיכוני/אתני ב-{int(song.bpm)} BPM בסולם {tonic_name} מינור: קיק עמוק ארבע-על-הרצפה, דרבוקה "
            f"וקונגות מעליו, באס מתגלגל ופדים רחבים. הוק של עוד במינור הרמוני עם חיג'אז על {dom_name}, ארפג'ים של "
            f"קאנון, וברייקדאון רגשי גדול עם קשתות ונאי.")
    song.mix_tips_he = (
        f"טיפ ערבוב: אינטרו של {song.sections[0].bars} תיבות תופים בלבד (דרבוקה נכנסת בתיבה 9), הבאס נכנס בתיבה "
        f"{groove.start_bar + 1} (Hot Cue B), ברייקדאון בתיבה {bd.start_bar + 1}, דרופ בתיבה {drop.start_bar + 1}. "
        f"אאוטרו של {outro.bars} תיבות תופים בלבד מתיבה {outro.start_bar + 1} — מושלם להכנסת הטראק הבא. "
        f"שכנים ב-Camelot: {plan['camelot']} ↔ " + ", ".join(_neighbours(plan["camelot"])) + ".")
    return song
