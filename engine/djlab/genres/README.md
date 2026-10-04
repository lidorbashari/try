# Genre recipe cookbook (for producer agents)

A **recipe** turns one entry of `music/tracklist.plan.json` into a `Song`. The engine does the rest
(rendering, mixing, mastering to the target LUFS, MP3/ID3/cover/sidecar). Your job is musical:
sound design, patterns, arrangement, levels. The two reference recipes set the bar — read them first:

* [`tech_house.py`](tech_house.py) — swung groove, rolling bass, vocal chops, stabs, breakdown/riser/drop
* [`techno.py`](techno.py) — kick + rumble, acid `MonoLine`, hypnotic sequence, dub stabs, industrial FX

```bash
cd engine
python -m djlab list                                  # ✓ = recipe exists for that genre_slug
python -m djlab render --id house-05 --preview        # ~8 s: 16 bars around the first drop → scratch MP3
python -m djlab analyze $DJLAB_SCRATCH/house-05-groove-machine.preview.mp3 --genre tech_house --bpm 126
python -m djlab render --genre tech_house --jobs 4    # full renders into music/tracks/<genre_slug>/
python ../tools/verify_audio.py ../music/tracks/tech_house
```
Set `DJLAB_SCRATCH` to your scratchpad so previews never land in the repo (default: `$TMPDIR/djlab`).

---

## 1. Minimal recipe skeleton

```python
# engine/djlab/genres/afro_house.py
import numpy as np
from .. import drums, fx, instruments as inst
from ..arrangement import Song, clip, euclid
from . import register

@register("afro_house")                       # == plan["genre_slug"] == file name
def build(plan: dict, rng: np.random.Generator) -> Song:
    song = Song(plan, rng, swing=float(rng.choice([54, 56])))   # swing: 50 straight … 66 triplet
    song.arrange([                             # (name, kind, bars, energy, flex)
        ("Intro", "intro", 32, 4, 0),          # kinds drive cues: intro/groove/build/breakdown/drop/outro
        ("Groove", "groove", 32, 6, 2),        # flex > 0 = stretched/shrunk in 8-bar steps to fit
        ("Breakdown", "breakdown", 16, 3, 0),  #   plan["target_minutes"] (whole 8-bar phrases)
        ("Drop", "drop", 32, 8, 3),
        ("Outro", "outro", 32, 4, 0),
    ])
    song.mix_in_bar = song.bar("groove")       # Hot Cue B = where bass/full groove enters
    key, root = song.key, song.key.root(1)     # Key('A minor'): root(1) = A1 (MIDI 33)

    kick = drums.kick("house", tune_hz=55, rng=rng)
    song.hits("kick", kick, lambda c: None if c.kind == "breakdown" or c.before("drop") else "x...x...x...x...",
              sc_source=True)                  # sc_source → drives every sidechain
    song.hits("hats", drums.variants(drums.hat, 4, rng), "gogxgogxgogxgogx", gain_db=-14, pan=0.3)
    song.notes("bass", inst.bass_pluck(), clip([(2, 2, root, 1.0), (10, 2, root + 7, 0.9)], 1),
               bus="bass", gain_db=-4, sidechain=0.5,
               when=lambda c: c.kind not in ("intro", "breakdown"))
    song.description_he = "שורה-שתיים בעברית על הטראק"
    song.instruments = ["house kick", "shaker", "bass"]
    return song                                # mix_tips_he auto-generated if you leave it empty
```

That is a complete, renderable recipe. Everything else is taste.

## 2. The Song API

| call | what |
|---|---|
| `Song(plan, rng, swing=50, lufs=None, scale=None)` | `song.bpm`, `song.grid`, `song.key` (`theory.Key`), `song.seed`, `song.master` |
| `song.arrange(template)` | sections fitted to the plan length; `song.sections`, `song.total_bars` |
| `song.bar("drop", nth=0)` / `song.find(kind_or_name)` | start bar / `Section` (None if absent) |
| `song.hits(name, sample(s), pattern, **layer_kw)` | one-shots on a step grid |
| `song.notes(name, instrument, notes, **layer_kw)` | polyphonic notes/chords (cached per pitch/len/vel) |
| `song.line(name, MonoSynth(...), notes, **layer_kw)` | mono line with slides/accents (acid, rolling bass) |
| `song.audio(name, bus="fx").add(audio, bar, beat=0, align="start"/"end", gain_db=0)` | risers, impacts, crashes, phrases |
| `song.custom(name, fn(song, a, b) -> (b-a, 2))` | anything else (drones, resampling) |
| `song.section_points({"Breakdown": -6, "drop": 0}, default, ramp_bars=0)` | automation points per section |
| `song.buses["drums"].eq/.comp/.sat/.width/...`, `song.returns["reverb"].decay/...` | mix settings |
| `song.master.lufs = -9.0` | loudness target (−11/−12 for hip-hop & lo-fi) |
| `song.mix_in_bar`, `song.description_he`, `song.mix_tips_he`, `song.instruments` | sidecar metadata |

**Common layer kwargs:** `bus` (`drums` `bass` `music` `fx` `vox`), `gain_db`, `pan` (−1…1),
`width` (stereo width >1 = wider, lows stay mono), `when` (list of section names/kinds or
`callable(ctx) -> bool`), `sends={"reverb": .2, "hall": .1, "room": .1, "delay": .2, "delay8": .1}`,
`sidechain` (0…1 ducking depth from the kick), `sc_release_ms`, `hp`/`lp` (static Hz), `fx=[callable]`
(insert effects on the layer buffer, e.g. `lambda x: fx.saturate(x, 2)`), `mute`.

**Automation:** `layer.automate(param, [(bar, value), ...])` — bars may be fractional; values hold
before the first / after the last point. Params: `gain_db`, `lp`, `hp` (Hz, log-interpolated, resonant
SVF with `res=`), `pan`, `send:<return>`, and for `MonoLine` `cutoff` / `env_mod`.

```python
d = song.bar("drop")
song.layer("bass").automate("lp", [(d - 8, 300), (d - 0.01, 1800), (d, 6000)])  # filter build → open on drop
song.layer("pad").automate("gain_db", song.section_points({"breakdown": 0, "drop": -6}, -60, ramp_bars=2))
```

## 3. The per-bar context `ctx` (`c` in lambdas)

Patterns, notes and `when` callables receive a `Ctx` for every bar:

`c.bar` (absolute) · `c.i` (bar inside section) · `c.section` · `c.name` · `c.kind` · `c.energy` ·
`c.bars_left` (1 = last bar) · `c.phrase_bar` (0..7) · `c.phrase` · `c.first` · `c.last` ·
`c.phrase_end` (bar 8 of a phrase) · `c.every(n)` (last bar of each n-bar block) · `c.next` / `c.prev`
(sections) · `c.before("drop", bars=1)` · `c.progress()` (0..1) · `c.is_("Drop", "groove")` ·
`c.rng` (deterministic per layer+bar → safe random variation).

## 4. Drum patterns (step strings)

One string = one bar. Length = steps per bar (16 = 16ths, 12 = 8th triplets, 32 = 32nds, 8 = 8ths).

| char | meaning |
|---|---|
| `X` | accent (vel 1.0) |
| `x` | normal (0.82) |
| `o` | soft (0.6) |
| `g` | ghost (0.38) |
| `1`–`9` | velocity 0.1–0.9 |
| `r` | roll: two 32nds |
| `.` `-` `_` | rest (spaces and `\|` ignored) |

A pattern may be a string, a list of strings (cycled per bar: 2-bar/4-bar patterns), a dict
`{"Drop": ..., "groove": ..., "*": default}`, or `callable(ctx)` returning any of these (or `None`
= silent bar). Swing applies to odd 16ths (`song.swing` or per-layer `swing=`). `humanize=0.06`
(velocity jitter), `timing_ms=2` (timing jitter), `vel_curve` (velocity exponent).

```python
FOUR = "x...x...x...x..."
OFFBEAT_OH = "..x...x...x...x."
CLAP = "....x.......x..."
TRESILLO = "x..x..x.x..x..x."         # afro / reggaeton family
DEMBOW_SNARE = "...x..x....x..x."
euclid(5, 16, rotate=2)                # → "..x...x..x..x..x" Euclidean percussion

def kick(c):                           # fills and drop-outs
    if c.kind == "breakdown":
        return None
    if c.before("drop"):               # kick out for the bar before the drop
        return None
    return FOUR

def hats(c):
    return "xxxxxxxxxxxxxxxx" if c.phrase_end and c.kind == "drop" else "gogxgogxgogxgogx"
```

**Drum sounds** (`drums.*`, mono one-shots, peak 1.0, transient at sample 0):
`kick(kind="tech_house"|"house"|"909"|"deep"|"techno"|"hard"|"808"|"trap"|"dnb"|"big_room", tune_hz, decay, click, drive)`,
`clap`, `snare(kind="909"|"808"|"tight"|"trap")`, `rimshot`, `snap`, `hat(open_=False, decay, tone)`, `ride`,
`crash` (stereo), `shaker`, `tambourine`, `cowbell`, `conga(pitch, "open"|"mute"|"slap")`, `bongo`, `tom`,
`darbuka("doum"|"tek"|"ka"|"slap")`, `log_drum(freq)`, `perc_blip`, `metal_hit`, `noise_hit`.
Use `drums.variants(fn, n, rng, jitter={"decay": .1}, **kw)` for round-robin variants (avoids machine-gun).
Tune kicks to the key: `tune_hz` ≈ root in the 45–60 Hz range.

## 5. Notes, bass lines, chords

Note tuple: `(step, length_steps, midi_or_list_of_midis, velocity[, flags])` with steps in 16ths from
the bar start (fractional OK, may exceed 16 to cross the bar line). `clip(events, bars)` loops a
multi-bar sequence (steps counted from the clip start) relative to the section start.

```python
k = song.key
riff = [(2, 1.5, k.root(1), 1.0), (6, 1.5, k.root(1), .9), (10, 1, k.root(2), .8), (14, 1.5, k.degree(4, 1), .9)]
song.notes("bass", inst.bass_pluck(cutoff=350, env_amt=2200, grit=.35), clip(riff, 1), bus="bass",
           gain_db=-4, sidechain=.55, sc_release_ms=150, when=["groove", "drop"])

from djlab.theory import progression, voice_lead
chords = progression(k, mood="deep", rng=rng, octave=3, size=4)   # voice-led 7th chords
song.notes("stabs", inst.stab(), lambda c: [(3, 1, chords[(c.i // 2) % 4], .9), (11, 1, chords[(c.i // 2) % 4], .7)],
           gain_db=-8, sends={"delay": .25, "reverb": .15}, width=1.5, sidechain=.5)
```

`theory`: `Key("D minor", scale="hijaz")`, `key.degree(d, octave)`, `key.chord(deg, octave, size)`,
`key.notes()`, `key.quantize(m)`, `SCALES` (major, minor, harmonic/melodic minor, dorian, phrygian,
phrygian_dominant = hijaz, double_harmonic, pentatonics, blues), `CHORDS`, `chord(root, "min9")`,
`invert`, `voice_lead`, `progression(key, mood)` (moods: minor → dark, deep, uplifting, hypnotic,
emotional; major → happy, deep, uplifting, funky), `camelot()`, `compatible_keys()`.

**Instruments** (`instruments.*` factories → `inst(freq, dur, vel)`): `bass_pluck`, `sub_bass`, `reese`,
`bass_808`, `organ_bass`, `stab`, `dub_chord`, `pad`, `pluck`, `epiano`, `piano`, `organ`,
`string_pluck` (Karplus-Strong: oud/guitar/kanun), `mallet("marimba"|"kalimba"|"vibes"|"steel")`, `bell`,
`lead_saw` (supersaw), `brass`, `vocal_chop(vowel, vowel_to, shift)`, `seq_blip`, `fm_stab`,
`log_drum_inst`, `sampler(one_shot, root_hz)`. Write your own: any `f(freq, dur, vel) -> np.ndarray`
built from `synth.*` (PolyBLEP `saw/square/triangle/sine`, `supersaw`, `unison`, `fm`, `wavetable`,
`white/pink/brown`, `adsr/ad/lfo/lfo_sync/glide/pitch_env`, `svf/svf24/ladder` with per-sample cutoff,
`formant_filter`, `chorus`, `karplus`). End notes with a short fade (`dsp.fade`) to avoid clicks and
return peak ≈ `0.8 * vel`.

**MonoLine** (acid / rolling bass): `inst.MonoSynth(wave, cutoff, res, env_mod, decay, accent, glide_ms,
drive, sub, dist)`; flags `"s"` = slide into the next note (gate held, pitch glides), `"a"` = accent.
Automate `cutoff` over the arrangement — that is the "acid build".

## 6. FX, transitions, fills

`fx.riser(seconds, "noise"|"pitch"|"both")` (place with `align="end"` on the drop bar),
`fx.downlifter`, `fx.noise_sweep(up=True)`, `fx.reverse_cymbal`, `fx.impact` (drop downbeat),
`drums.crash` on phrase starts, `fx.reverb(x, "room"|"plate"|"hall"|"dark"|"short"|"huge")`,
`fx.tempo_delay(x, bpm, beats=.75)`, `fx.saturate`, `fx.tape`, `fx.distort`, `fx.bitcrush`,
`fx.rumble(kick_layer_buffer, bpm)` (techno rumble, use as a layer `fx=`), `fx.widen`, `fx.haas`,
`fx.filter_sweep`, `synth.chorus`.

Arrangement conventions that make tracks DJ-friendly (SCHEMA rules):
* Intro ≥ 16 bars (usually 32) **drums only for the first 16 bars** (no bass/tonal content — tests check
  this for the reference recipes). Outro mirrors it: bass out, last 16 bars drums only.
* All sections on 8-bar boundaries; mark phrases: crash at section starts / every 16 bars in drops,
  small fills (`c.phrase_end`) every 8 bars.
* Before drops: kick out for 1 bar (`c.before("drop")`), riser ending exactly on the drop, snare/clap
  roll (`["x...x...x...x...", "x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx"]` over the last bars), impact on 1.
* Breakdowns: kick out, pad/chords up, bass out (or a quiet sub), filter sweeps opening.
* Use `rng` for genuine variety: pattern pools, sound parameters (`rng.uniform`), template choice.
  Never use Python's `random` or time — renders must be deterministic.

## 7. Choosing mix levels

The master normalises loudness, so only **relative** levels matter. Starting points (gain_db, one-shots
peak 1.0, instruments peak 0.8·vel):

| element | gain_db | notes |
|---|---|---|
| kick | −1.5 … −3.5 | louder kicks (techno drive) need less; always `sc_source=True` |
| bass / rumble | −4 … −6.5 | bus `bass` (mono < 180 Hz), sidechain 0.5–1.0 |
| clap / snare | −2.5 … −8 | send a little `reverb`/`room` |
| closed hats | −12 … −15 | pan ±0.2–0.35 |
| open hat / ride | −11 … −17 | |
| shaker / perc | −12 … −17 | pan wide (±0.4–0.6) for stereo image |
| chords / stabs / leads | −7 … −11 | `width` 1.3–1.7, sidechain 0.3–0.5, delay sends |
| pads | −9 … −12 | `hall` send 0.3, automate `lp` |
| vocal chops | −5 … −9 | bus `vox` (compressed), delay + reverb |
| FX (risers, crashes) | −8 … −13 | bus `fx` |

Bus defaults (override via `song.buses[...]`): drums glue comp + light saturation, bass mono-below-180 Hz
+ comp, music HP 120 Hz, fx HP 140 Hz, vox comp + HP. Returns: `reverb` (plate), `hall`, `room`,
`delay` (dotted 8th), `delay8` (8th) — all sidechained to the kick.

## 8. Validate with your "ears": `analysis.py`

```
python -m djlab analyze file.mp3 [--genre slug] [--bpm 126]
```
Reports LUFS / true peak / crest / PLR, BPM check, leading silence, clipping, click detector,
side/mid width, **band balance vs the genre reference curve** with advice, per-band stereo correlation
(sub must be ≈ 1.00 = mono) and loudness per 8-bar phrase (your arrangement's energy curve: breakdowns
should dip 4–8 dB, drops should be the loudest).

Iterate on `--preview` renders (16 bars around the first drop). Aim for: every band Δref within ±3 dB,
sub corr ≥ 0.95, side/mid between −20 and −8 dB, crest ≥ 8 dB, no clicks. To find which layer causes a
problem, mute layers (`layer.mute = True`) and render `mix(song, a, b)` in Python.

Reference curves (band power relative to total, dB) — `analysis.REFERENCE` / `GENRE_CURVE`:

| curve | sub <60 | low 60–250 | low-mid –800 | mid –3k | high-mid –8k | air >8k | genres |
|---|---|---|---|---|---|---|---|
| four_on_floor | −6.5 | −3.8 | −9.5 | −11.5 | −15.5 | −21 | house, deep/tech/afro house, mediterranean, afrobeats, breaks |
| techno | −6.0 | −3.6 | −10 | −12 | −15.5 | −21 | techno, hypnotic, hard techno, psytrance |
| melodic | −6.5 | −4.0 | −9 | −11 | −15 | −20.5 | melodic techno |
| bass_heavy | −4.0 | −4.5 | −10.5 | −12.5 | −16 | −21.5 | hip-hop, reggaeton, moombahton, amapiano, dnb, dubstep, ukg |
| bright | −7.5 | −4.5 | −9 | −10 | −13.5 | −18.5 | big room, pop dance, nu disco, trance |
| lofi | −7.0 | −3.5 | −8 | −11 | −17 | −24 | lo-fi |

Loudness targets: −9 LUFS (club), `song.master.lufs = -11` for hip-hop, `-12` for lo-fi. True peak is
always ≤ −1.0 dBTP after MP3 encoding (the exporter checks the decoded MP3 and trims if needed).

## 9. Performance & determinism tips

* Pre-render one-shots once (top of the recipe); `Notes` caches per (pitch, length, velocity).
* Long notes (pads 8+ bars) are fine; avoid thousands of *distinct* note lengths/velocities.
* A 4.5-min track renders in ~60–80 s. Use `--preview` while iterating, `--jobs 4` for batches.
* Same plan entry + seed ⇒ bit-identical audio. Only derive randomness from `rng` / `c.rng`.
