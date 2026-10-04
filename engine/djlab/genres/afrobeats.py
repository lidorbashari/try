"""Afrobeats recipe (102–108 BPM, major keys).

Bouncy, swung West-African pop groove: syncopated kick, 3-3-2 accented shakers, rim + clap
backbeat, wooden log percussion, conga, agogo bell, talking drum (pitch-bent membrane) answering
the groove; warm highlife guitar riffs (variable-pitch Karplus-Strong), bright marimba / kalimba
hooks, Rhodes-style chords and warm pads over a deep melodic bass with slides. Feel-good major
progressions. A "dancehall-tinged" variant (higher energy/seed choice or a "riddim" title) adds a
dembow snare, off-beat guitar skank chops and a kalimba hook.

Arrangement (phrase-aligned, 16-bar drums-only intro and outro):
Intro 16 → Verse 16 (bass + guitar, Hot Cue B) → Hook 16 (Hot Cue D) → Verse 2 8 → Breakdown 8
(no kick: pads, mallets, talking drum) → Hook 2 16 → Outro 16.
"""
from __future__ import annotations

import numpy as np

from .. import drums, fx, instruments as inst
from .. import ext_world as W
from ..arrangement import Song
from ..theory import voice_lead
from . import register

# major-key chords (semitones above the tonic)
CH = {"I": [0, 4, 7], "ii": [2, 5, 9], "iii": [4, 7, 11], "IV": [5, 9, 12], "V": [7, 11, 14], "vi": [9, 12, 16],
      "Imaj7": [0, 4, 7, 11], "IVmaj7": [5, 9, 12, 16], "vi7": [9, 12, 16, 19], "V9sus": [7, 12, 14, 17],
      "ii7": [2, 5, 9, 12], "iii7": [4, 7, 11, 14]}
ROOT = {k: v[0] for k, v in CH.items()}


def bars(*strings) -> str:
    for s in strings:
        tot = sum(float(t.split("/")[0].lstrip("!~").split(":")[1]) for t in s.split() if not t.startswith("@"))
        assert abs(tot - 16) < 1e-6, (tot, s)
    return " ".join(strings)


LAGOS = dict(
    prog=["Imaj7", "vi7", "IVmaj7", "V9sus"],
    bd_prog=["IVmaj7", "IVmaj7", "Imaj7", "Imaj7", "vi7", "vi7", "V9sus", "V9sus"],
    kick=["x.....x.x.......", "x.....x.x.....x."],
    hook=bars("7:1.5 9:1.5 7:1 4:2 2:2 0:2 2:2 4:4",
              "7:1.5 9:1.5 7:1 4:2 2:2 4:2 7:2 9:4",
              "12:1.5 11:1.5 9:1 7:2 4:2 7:2 9:2 7:4",
              "9:1.5 7:1.5 4:1 2:2 r:2 2:1 4:1 2:2 -1:4"),
    counter=bars("r:8 16:1 14:1 12:2 r:4", "r:8 16:1 19:1 16:2 r:4", "r:8 19:1 16:1 14:2 r:4",
                 "r:8 14:1 12:1 11:2 r:4"),
    mallet="marimba", mallet2="kalimba", dancehall=False,
)
SUNSHINE = dict(
    prog=["I", "IV", "vi", "V"],
    bd_prog=["IV", "IV", "I", "I", "vi", "vi", "V", "V"],
    kick=["x.....x.x.....x.", "x.....x.x..x...."],
    hook=bars("0:1 4:1 7:1 r:1 9:2 7:2 4:1 r:1 2:1 4:1 7:4",
              "7:1 9:1 12:1 r:1 11:2 9:2 7:1 r:1 4:1 7:1 5:4",
              "4:1 7:1 9:1 r:1 11:2 9:2 7:1 r:1 4:1 2:1 4:4",
              "4:1 2:1 0:1 r:1 -3:2 0:2 2:1 r:1 4:1 7:1 4:2 2:2"),
    counter=bars("r:4 12:2 11:2 9:4 r:4", "r:4 14:2 12:2 9:4 r:4", "r:4 11:2 9:2 7:4 r:4", "r:4 9:2 7:2 4:4 r:4"),
    mallet="kalimba", mallet2="marimba", dancehall=True,
)

TPL = [("Intro", "intro", 16, 4, 0), ("Verse", "groove", 16, 6, 2), ("Hook", "drop", 16, 7, 1),
       ("Verse 2", "groove", 8, 6, 3), ("Breakdown", "breakdown", 8, 4, 0), ("Hook 2", "drop", 16, 8, 2),
       ("Outro", "outro", 16, 4, 0)]
SHAKER = ["xgoxgoxgxgoxgoxg", "xgoxgoxoxgoxgoxo", "Xgoxgoxgxgoxgoxg"]
LOGS = ["..x..x....x..x..", "...x..x...x.x...", "..x...x...x..x.x"]
CONGA = ["...x..x...x..xx.", "..x..x.x..x...x.", "...x.x....x.x.x."]
BELL = "x..x..x...x.x..."


@register("afrobeats")
def build(plan: dict, rng: np.random.Generator) -> Song:
    dance = "riddim" in str(plan.get("title", "")).lower() or int(plan["seed"]) % 2 == 1
    M = SUNSHINE if dance else LAGOS
    song = Song(plan, rng, swing=float(rng.uniform(56.0, 59.0) if not dance else rng.uniform(54.0, 57.0)))
    song.arrange(TPL, song.target_bars())
    key = song.key
    pc = key.root_pc
    verse, hook = song.find("groove"), song.find("drop")
    outro = song.find("outro")
    song.mix_in_bar = verse.start_bar

    def prog_at(c):
        if c.kind in ("groove", "drop"):
            return M["prog"][c.i % 4]
        if c.kind == "breakdown":
            return M["bd_prog"][c.i % 8]
        return None

    def reg(p, lo):
        return lo + ((p - lo) % 12)

    # ------------------------------------------------------------------ drums
    kick_s = drums.kick("house", tune_hz=W.kick_tune(key, 46.0, 58.0, 50.0), decay=float(rng.uniform(0.3, 0.36)),
                        click=float(rng.uniform(0.25, 0.4)), drive=1.3, rng=rng)
    kpat = M["kick"]

    def kick_pat(c):
        if c.kind == "breakdown":
            return None
        if c.before("drop", 1) and c.kind != "intro":
            return "x.....x........." if c.prev is not None else kpat[0]
        if c.kind == "outro" and c.bars_left <= 1:
            return "x..............."
        return kpat[c.i % 2] if c.kind != "intro" or c.i >= 4 else "x.......x......."

    song.hits("kick", kick_s, kick_pat, gain_db=-2.5, sc_source=True, humanize=0.0)

    rim = drums.rimshot(float(rng.uniform(1450, 1750)), rng=rng)
    clap = drums.variants(drums.clap, 2, rng, tone_hz=float(rng.uniform(1150, 1400)), tail=0.14)
    song.hits("clap", clap, lambda c: "....x.......x..." if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 8)
              or (c.kind == "outro" and c.bars_left > 8) or (c.kind == "breakdown" and c.bars_left <= 2) else None,
              gain_db=-6.5, sends={"reverb": 0.16, "room": 0.1})
    song.hits("rim", rim, lambda c: ("....x..x....x..." if not M["dancehall"] else "...x..x....x..x.")
              if c.kind in ("groove", "drop", "outro") or (c.kind == "intro" and c.i >= 4) else None,
              gain_db=-13.0, pan=0.12, sends={"room": 0.12})
    if M["dancehall"]:
        snr = drums.snare(tone_hz=float(rng.uniform(200, 240)), snappy=0.75, decay=0.1, kind="tight", rng=rng)
        song.hits("dembow_snare", snr, lambda c: "...x..x....x..x." if c.kind == "drop" else None,
                  gain_db=-9.0, pan=-0.08, sends={"reverb": 0.1})
    shk = drums.variants(drums.shaker, 4, rng, jitter={"length": 0.2}, length=float(rng.uniform(0.06, 0.085)))
    sp = SHAKER[int(rng.integers(len(SHAKER)))]
    song.hits("shaker", shk, lambda c: sp if c.kind != "breakdown" or c.i >= 2 else None,
              gain_db=-12.0, pan=0.42, humanize=0.15, timing_ms=2.0)
    hats = drums.variants(drums.hat, 3, rng, decay=float(rng.uniform(0.028, 0.04)), tone=float(rng.uniform(1.0, 1.2)))
    song.hits("hats", hats, lambda c: "gogxgogxgogxgogx" if c.kind == "drop" or (c.kind == "groove" and c.i >= 8) else None,
              gain_db=-16.0, pan=-0.3, humanize=0.12)
    ohat = drums.hat(open_=True, decay=0.18, rng=rng)
    song.hits("open_hat", ohat, lambda c: "..x...x...x...x." if c.kind == "drop" else None, gain_db=-13.0, pan=0.2,
              sends={"room": 0.1})

    logs = [W.log_perc(float(rng.uniform(380, 460)), rng=rng), W.log_perc(float(rng.uniform(560, 680)), rng=rng)]
    lp_ = LOGS[int(rng.integers(len(LOGS)))]
    song.hits("log_perc", logs, lambda c: lp_ if c.kind not in ("breakdown",) and not (c.kind == "intro" and c.i < 2)
              and not (c.kind == "outro" and c.bars_left <= 4) else None,
              gain_db=-13.0, pan=-0.45, sends={"room": 0.15, "delay8": 0.06}, humanize=0.1, timing_ms=1.5)
    congas = [drums.conga(float(rng.uniform(200, 230)), "open", rng=rng), drums.conga(float(rng.uniform(290, 330)), "slap", rng=rng),
              drums.conga(float(rng.uniform(250, 270)), "mute", rng=rng)]
    cp = CONGA[int(rng.integers(len(CONGA)))]
    song.hits("congas", congas, lambda c: cp if c.kind in ("groove", "drop") or (c.kind == "intro" and c.i >= 8)
              or (c.kind == "outro" and c.bars_left > 8) else None,
              gain_db=-14.0, pan=0.55, sends={"room": 0.14}, humanize=0.12, timing_ms=2.0)
    bell = W.agogo(float(rng.uniform(780, 900)), rng=rng)
    song.hits("bell", bell, lambda c: BELL if c.kind == "drop" else None, gain_db=-19.0, pan=-0.6,
              sends={"delay8": 0.1})
    # talking drum: answers at the end of every 2nd bar (bend up / down variants)
    talk = [W.talking_drum(float(rng.uniform(140, 165)), 5.0, 0.09, rng=rng),
            W.talking_drum(float(rng.uniform(190, 215)), -4.0, 0.08, rng=rng),
            W.talking_drum(float(rng.uniform(165, 180)), 3.0, 0.06, 0.25, rng=rng)]
    tpat = ["..........x.x.x.", "........x..x.x..", "..........xx..x.", "........x.x...x."]

    def talk_pat(c):
        if c.kind == "breakdown":
            return tpat[c.i % 4] if c.i % 2 == 1 else "x.....x.........."[:16]
        if (c.kind == "intro" and c.i >= 8) or c.kind in ("groove", "drop") or (c.kind == "outro" and c.bars_left > 8):
            return tpat[(c.i // 2) % 4] if c.i % 2 == 1 else None
        return None

    song.hits("talking_drum", talk, talk_pat, gain_db=-10.0, pan=-0.2, sends={"room": 0.15, "reverb": 0.06},
              humanize=0.1, timing_ms=3.0)

    # roll into the hooks
    snr2 = drums.snare(tone_hz=210.0, snappy=0.6, decay=0.08, kind="tight", rng=rng)

    def roll(c):
        if c.before("drop", 1):
            return "....x...x.x.xxxx"
        return None

    song.hits("snare_roll", snr2, roll, gain_db=-12.0, sends={"reverb": 0.15})

    # ------------------------------------------------------------------ deep melodic bass (mono, slides)
    synth = inst.MonoSynth(wave=str(rng.choice(["saw", "square"])), cutoff=float(rng.uniform(260, 340)), res=0.18,
                           env_mod=float(rng.uniform(0.8, 1.3)), decay=0.22, glide_ms=70.0, drive=1.3, sub=0.9,
                           sustain=0.7, amp_decay=0.5)

    def bass_root(nm):
        return reg((pc + ROOT[nm]) % 12, 28)

    def bass_notes(c):
        nm = prog_at(c)
        if nm is None or c.kind == "outro":
            return []
        r = bass_root(nm)
        if c.kind == "breakdown":
            return [(0, 14, r, 0.7, "")] if c.i % 2 == 0 and c.bars_left > 2 else []
        nxt = song.ctx(c.bar + 1)
        nn = prog_at(nxt) if nxt.section is c.section else None
        appr = key.quantize(bass_root(nn) - 1) if nn else r + 7
        if appr - r > 9:
            appr -= 12
        ev = [(0, 2.5, r, 1.0, "a"), (3, 1, r, 0.7, ""), (6, 1.5, r + 7, 0.85, ""), (8, 1.5, r + 12, 0.9, ""),
              (10, 1, r + 7, 0.7, ""), (11, 2, r + 9 if "vi" not in nm else r + 10, 0.75, ""),
              (14, 1.6, appr, 0.8, "s" if nn else "")]
        if c.before("drop", 1) or c.before("breakdown", 1):
            ev = ev[:3]
        return ev

    bass = song.line("bass", synth, bass_notes, bus="bass", gain_db=-2.0, sidechain=0.35, sc_release_ms=110.0)
    bass.automate("cutoff", [(verse.start_bar, 240), (verse.start_bar + 8, 320), (hook.start_bar, 420)])

    # ------------------------------------------------------------------ chords: Rhodes + warm pad
    center = reg(pc, 60) + 2
    ep = inst.epiano(bright=0.45)

    def chord_of(nm, ctr=center):
        return voice_lead(None, [reg(pc, 55) + s for s in CH[nm]], center=ctr)

    def keys_notes(c):
        nm = prog_at(c)
        if nm is None or (c.kind == "groove" and c.section.name == "Verse" and c.i < 8):
            return []
        ch = chord_of(nm)
        if M["dancehall"] and c.kind == "drop":
            return [(2, 1, ch, 0.75), (6, 1, ch, 0.65), (10, 1, ch, 0.75), (14, 1, ch, 0.65)]
        if c.kind == "breakdown":
            return [(0, 8, ch, 0.6)] if c.i % 2 == 0 else []
        return [(0, 3, ch, 0.7), (6, 1.5, ch, 0.55), (10, 2, ch, 0.6)]

    song.notes("rhodes", ep, keys_notes, gain_db=-14.5, pan=-0.15, hp=220.0, sends={"reverb": 0.15, "delay": 0.08},
               width=1.4, sidechain=0.3)
    pad_i = inst.pad(attack=0.6, release=1.6, cutoff=float(rng.uniform(1300, 1900)), detune=0.22, warmth=0.75)

    def pad_notes(c):
        nm = prog_at(c)
        if nm is None or c.kind == "groove" and c.i < 4:
            return []
        return [(0, 16, chord_of(nm, center + 5), 0.65 if c.kind != "breakdown" else 0.8)]

    pad = song.notes("pad", pad_i, pad_notes, gain_db=-16.5, hp=200.0, sends={"hall": 0.25}, width=1.6, sidechain=0.4)
    pad.automate("gain_db", song.section_points({"breakdown": 3.0, "drop": 0.0, "groove": -2.0}, 0.0, ramp_bars=1))

    # ------------------------------------------------------------------ highlife guitar (KS)
    gtr = W.guitar(t60=float(rng.uniform(1.0, 1.4)))
    gtr_cache = {}

    def gtr_bar(nm):
        if nm not in gtr_cache:
            tones = sorted(reg((pc + s) % 12, 62) for s in CH[nm][:3])
            r, t, f = tones
            seq = [(0, f), (2, r + 12), (3, t), (5, f), (6, r + 12), (8, t), (10, f), (11, r + 12), (13, t), (14, f)]
            gtr_cache[nm] = tuple((float(s), 1.4, float(m), 0.85 if s in (0, 6, 10) else 0.65, "") for s, m in seq)
        return gtr_cache[nm]

    def gtr_phr(c):
        nm = prog_at(c)
        if nm is None or c.kind == "breakdown":
            return []
        if M["dancehall"] and c.kind == "drop":
            return []
        return [(0, gtr_bar(nm), 0.9)]

    W.add_phrases(song, "guitar", gtr, gtr_phr, gain_db=-4.5, pan=0.3, sends={"room": 0.12, "delay8": 0.1},
                  lookback=2, width=1.3, sidechain=0.25)

    if M["dancehall"]:  # off-beat skank chops (muted guitar) in the hooks
        mut = W.guitar(muted=True)
        skank_cache = {}

        def skank(nm):
            if nm not in skank_cache:
                tones = sorted(reg((pc + s) % 12, 60) for s in CH[nm][:3])
                ev = []
                for s in (2, 6, 10, 14):
                    for k, m in enumerate(tones):
                        ev.append((s + 0.06 * k, 0.8, float(m), 0.8, ""))
                skank_cache[nm] = tuple(ev)
            return skank_cache[nm]

        W.add_phrases(song, "skank", mut, lambda c: [(0, skank(prog_at(c)), 0.9)] if c.kind == "drop" else [],
                      gain_db=-10.0, pan=-0.35, sends={"delay8": 0.12, "room": 0.1}, lookback=2, width=1.2,
                      sidechain=0.2)

    # ------------------------------------------------------------------ mallet hooks
    T_m = reg(pc, 64) if M["mallet"] == "marimba" else reg(pc, 70)
    hook_n = W.transpose(W.mel(M["hook"]), T_m)
    counter_n = W.transpose(W.mel(M["counter"]), reg(pc, 60))
    mal = inst.mallet(M["mallet"])
    mal2 = inst.mallet(M["mallet2"])

    def mal_notes(c):
        if c.kind == "drop" or (c.kind == "breakdown" and c.i >= 4):
            off = (c.i % 4) * 16
            return [(st - off, ln, m, v) for st, ln, m, v, o in hook_n if off <= st < off + 16]
        return []

    song.notes("mallet_hook", mal, mal_notes, gain_db=-10.0, pan=0.1, hp=240.0, sends={"reverb": 0.15, "delay": 0.12},
               width=1.3, sidechain=0.15)

    def mal2_notes(c):
        if (c.kind == "drop" and c.section.name == "Hook 2") or (c.kind == "groove" and c.section.name == "Verse 2"):
            off = (c.i % 4) * 16
            return [(st - off, ln, m, v) for st, ln, m, v, o in counter_n if off <= st < off + 16]
        if c.kind == "breakdown" and c.i < 4:
            off = (c.i % 4) * 16
            return [(st - off, ln, m + 12, v * 0.8) for st, ln, m, v, o in hook_n if off <= st < off + 16]
        return []

    song.notes("mallet_counter", mal2, mal2_notes, gain_db=-12.0, pan=-0.3, hp=240.0, sends={"delay": 0.2, "reverb": 0.15},
               width=1.4)

    # vocal-like chant (formant chops) answering the hook: "oh-eh"
    vox = inst.vocal_chop(vowel="o", vowel_to="e", shift=1.1, scoop=-1.0)
    chant = [(10, 1.5, 7, 0.85), (12, 3, 9, 0.9)] if not dance else [(11, 1, 4, 0.85), (12, 3, 7, 0.9)]

    def chant_notes(c):
        if c.kind == "drop" and c.i % 2 == 1:
            return [(s, l, reg(pc, 60) + d, v) for s, l, d, v in chant]
        return []

    song.notes("chant", vox, chant_notes, bus="vox", gain_db=-10.0, sends={"reverb": 0.2, "delay": 0.18},
               sidechain=0.2)

    # ------------------------------------------------------------------ fx
    fxl = song.audio("fx", bus="fx", sends={"hall": 0.12})
    crash = drums.crash(decay=2.0, rng=rng)
    bar = song.grid.bar_sec
    for s in song.sections:
        if s.kind in ("groove", "drop", "outro"):
            fxl.add(crash, s.start_bar, gain_db=-11.0)
        if s.kind == "drop":
            fxl.add(fx.impact(2.0, rng=rng), s.start_bar, gain_db=-12.0)
            fxl.add(fx.riser(bar * 4, "noise", f_lo=400, f_hi=8000, rng=rng), s.start_bar, align="end", gain_db=-15.0)
        if s.kind == "breakdown":
            fxl.add(fx.downlifter(bar * 2, rng=rng), s.start_bar, gain_db=-14.0)

    song.buses["drums"].eq = [("peak", 2800.0, 1.5, 0.8)]
    song.buses["drums"].width = 1.25
    song.buses["music"].eq = [("peak", 2200.0, 1.0, 0.8)]
    song.master.lufs = -9.0
    song.master.low_shelf_db, song.master.low_shelf_hz = 1.0, 55.0

    tonic = plan["key"].split()[0]
    song.instruments = ["syncopated afrobeats kick", "3-3-2 shakers", "rim & clap", "log percussion", "congas",
                        "agogo bell", "talking drum", "deep melodic bass (slides)", "highlife guitar (Karplus-Strong)",
                        M["mallet"], M["mallet2"], "Rhodes chords", "warm pad", "vocal chant chops"]
    if dance:
        song.instruments += ["dembow snare", "off-beat guitar skank"]
        song.description_he = (
            f"אפרוביטס עם טאץ' של דאנסהול ב-{int(song.bpm)} BPM בסולם {tonic} מז'ור: קיק מסונכרן, סנר דמבו בפזמון, "
            f"שייקרים בחלוקה 3-3-2, טוקינג דראם שעונה לגרוב, סקאנק גיטרה על האופביט, הוק של קלימבה מבריק ובאס "
            f"מלודי עמוק עם גלישות. מהלך אקורדים שמח ומזמין (I–IV–vi–V).")
    else:
        song.description_he = (
            f"אפרוביטס שמשי ב-{int(song.bpm)} BPM בסולם {tonic} מז'ור: קיק מסונכרן ושייקרים מקפצים, רים וקלאפ, "
            f"כלי הקשה מעץ, קונגות, פעמון אגוגו וטוקינג דראם. גיטרת הייליף חמה, הוק של מרימבה, אקורדי רודס "
            f"ופד חם מעל באס מלודי עמוק — מהלך מז'ור מרגיש-טוב (Imaj7–vi7–IVmaj7–V).")
    bd = song.find("breakdown")
    from ..theory import compatible_keys
    song.mix_tips_he = (
        f"טיפ ערבוב: אינטרו של {song.sections[0].bars} תיבות תופים וכלי הקשה בלבד, הבאס והגיטרה נכנסים בתיבה "
        f"{verse.start_bar + 1} (Hot Cue B), הפזמון בתיבה {hook.start_bar + 1} (Hot Cue D), ברייקדאון בלי קיק בתיבה "
        f"{bd.start_bar + 1}. אאוטרו של {outro.bars} תיבות תופים בלבד מתיבה {outro.start_bar + 1}. "
        f"שכנים ב-Camelot: {plan['camelot']} ↔ " + ", ".join(compatible_keys(plan["camelot"])[1:4]) + ".")
    return song
