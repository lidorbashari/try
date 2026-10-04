# djlab — the DJ Lab synthesis & production engine

Renders every DJ Lab track **from scratch** (no samples, no copyrighted audio): drum synthesis,
band-limited synths, effects, arrangement, bus mixing, mastering to a LUFS target, MP3 320 kbps with
ID3v2.4 tags, procedural cover art and a JSON sidecar per `music/SCHEMA.md`.

```bash
pip install -r engine/requirements.txt          # numpy scipy numba soundfile mutagen Pillow librosa pyloudnorm
cd engine
python -m djlab list                            # plan entries; ✓ = recipe exists
python -m djlab render --id house-05            # → music/tracks/tech_house/house-05-*.mp3/.json/.jpg
python -m djlab render --id house-05 --preview  # 16 bars around the first drop → $DJLAB_SCRATCH (fast)
python -m djlab render --genre techno --jobs 4  # or --family house | --all
python -m djlab analyze ../music/tracks/techno/techno-01-concrete-pulse.mp3
cd .. && python -m pytest engine/tests -q
python tools/verify_audio.py music/tracks       # QA gate (exit 1 on failure)
```
The plan path is resolved from the package location, so the CLI works from any cwd (run it from
`engine/` or put `engine/` on `PYTHONPATH`). Temp files go to `$DJLAB_SCRATCH` (default
`$TMPDIR/djlab`) — never into the repo.

## Architecture

```
plan entry ──► genres/<slug>.py recipe ──► Song (sections, layers, automation, buses, returns)
                                              │
            arrangement.py: Hits / Notes / MonoLine / Audio / Custom layers render per bar
                                              │
            mixer.py: layer fx → hp/lp automation → width/pan → gain automation → sidechain
                      → bus (EQ, glue comp, saturation, mono-below) + sends → reverb/delay returns
                                              │
            master.py: HP 20 Hz → mono < 110 Hz → tone EQ → glue comp → [gain → 2× soft clip →
                       4×-oversampled look-ahead true-peak limiter] loop until target LUFS
                                              │
            export.py: float WAV → ffmpeg libmp3lame 320k CBR → decode & re-measure (TP ≤ −1.0) →
                       ID3v2.4 (mutagen) + cover.py JPEG + sidecar JSON
```

| module | contents |
|---|---|
| `grid.py` | `Grid(bpm)`: sample of any (bar, beat, 16th) computed from float time and rounded per event (no drift), MPC-style swing on odd 16ths, `bars_for_minutes` (whole 8-bar phrases) |
| `dsp.py` | numba kernels: TPT state-variable filter & Moog-style ladder with per-sample cutoff, PolyBLEP oscillators, compressor, ping-pong delay, modulated delay, Karplus-Strong, true-peak (4× oversampled) helpers; RBJ EQ shelves/peaks, Butterworth HP/LP |
| `synth.py` | saw/square/pulse/triangle/sine, `unison`, `supersaw` (7 voices, stereo), `fm`, `wavetable` morph, white/pink/brown noise, `adsr` (sample-accurate release), `ad`, `lfo`/`lfo_sync`, `glide`, `pitch_env`, `chorus`, `formant_filter` |
| `drums.py` | kicks (tech_house, house, 909, deep, techno, hard, 808, trap, dnb, big_room), clap, snares, rim, snap, 808/909 hats (6-osc metallic cluster + noise), ride, crash, shaker, tambourine, cowbell, congas/bongos, toms, darbuka (doum/tek/ka/slap), log drum, perc blips, metal hits, `variants()` round-robin humanisation |
| `instruments.py` | note instruments (`bass_pluck`, `sub_bass`, `reese`, `bass_808`, `organ_bass`, `stab`, `dub_chord`, `pad`, `pluck`, `epiano`, `piano`, `organ`, `string_pluck`, `mallet`, `bell`, `lead_saw`, `brass`, `vocal_chop`, `seq_blip`, `fm_stab`, `log_drum_inst`, `sampler`) and `MonoSynth` (303-style slides/accents) |
| `fx.py` | convolution reverb with synthesised frequency-dependent stereo IRs (room/plate/hall/dark/short/huge), tempo delay, saturation/soft-clip/tape/distort/bitcrush, sidechain envelopes from kick triggers, risers/downlifters/noise sweeps/reverse cymbal/impact, filter-sweep helpers, techno `rumble`, `widen` (mono below X Hz), `haas` |
| `theory.py` | note↔MIDI↔Hz, scales (incl. Hijaz / phrygian dominant, double harmonic), chords, inversions, voice leading, mood progressions, Camelot + compatible keys |
| `arrangement.py` | `Song`, `Section`, `fit_sections`, per-bar `Ctx`, step-pattern parser, `euclid`, `clip`, layers, automation, cues A–H + memory cues, Hebrew mix-tip generator |
| `mixer.py` / `master.py` | buses, returns, mastering chain, `lufs()`, `limiter()` |
| `cover.py` | 800×800 covers: family palette, gradient + geometric motif + radial waveform from the real audio envelope, English + Hebrew title (raqm), BPM/Camelot badge, DJ LAB mark, ≤ 200 KB |
| `export.py` | MP3 encode/decode, tags, sidecar |
| `analysis.py` | objective report (`python -m djlab analyze`) used by agents and `tools/verify_audio.py` |
| `render.py` / `cli.py` | pipeline, `--preview`, multiprocessing `--jobs` |
| `genres/` | recipe registry + **[cookbook](djlab/genres/README.md)** + reference recipes `tech_house.py`, `techno.py` |

## Writing a genre recipe
See **[`djlab/genres/README.md`](djlab/genres/README.md)** — API, skeleton, patterns, bass/chords,
automation, fills/risers, mix levels, analysis targets and genre reference curves.

## Guarantees
* **Deterministic:** same plan entry + seed → bit-identical audio (all randomness from the seeded
  `rng`; per-bar `ctx.rng` derived from seed + layer name + bar). Tested.
* **Sample-exact grid:** sample 0 is beat 1 of bar 1; every hit lands on `round(time·sr)`.
* **Loudness:** integrated LUFS within ±0.3 of the recipe target (−9 club, −11/−12 hip-hop/lo-fi);
  true peak ≤ −1.0 dBTP measured on the decoded MP3 (the exporter re-encodes with less gain if LAME
  overshoots).
* **Clean:** DC removed, no NaN, short fades on every note end, raised-cosine fades on one-shots,
  sub band mono (bass bus mono < 180 Hz, master mono < 110 Hz).

## LAME encoder-delay caveat (first downbeat at 0.0 s)
MP3 encoders prepend an encoder delay (LAME: 576 samples + 529 decoder delay) and pad the last frame.
ffmpeg writes a **Xing/LAME info header** recording the exact delay and padding; decoders that honour it
(ffmpeg/libav, Rekordbox, Serato, Traktor, browsers, foobar2000) remove them, so the decoded MP3 starts
exactly on our sample 0 = beat 1 (`tests/test_export.py` checks a lag of 0 samples and equal length).
Players that ignore the header would start ≈ 25 ms late — irrelevant for beatgridding since Rekordbox
analyses the grid itself, but never strip the Xing frame (e.g. by re-muxing without `-write_xing 1`).

## Performance
A 4.3–4.4 min track renders in ~75 s on one core (mix ~40 s, master ~20 s, export ~10 s); `--preview`
takes ~8 s. Numba kernels compile once and are cached (`__pycache__`). Use `--jobs N` for batches
(each job peaks at ~1.5 GB RAM).

## Known limitations
* Synthesised "vocals" are formant chops (vowel-like), not words.
* Reverbs are static convolution (no modulation); fine for club music, less lush than high-end plates.
* The click detector in `analysis.py` is heuristic (warning only).
