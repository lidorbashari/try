# DJ Lab — instructions for Claude / agents

DJ Lab is a Hebrew-first learning and music repo for a beginner DJ taking a **Rekordbox** course.
Favourite genres: House / Tech House / Afro House, Techno / Melodic Techno, Mainstream / Hip-Hop /
Mediterranean. Everything user-facing is written in **Hebrew** (DJ terms stay in English, e.g. "Beatmatching",
"Hot Cue"). Code, comments and agent prompts are in English.

## Layout
| path | what |
|---|---|
| `guide/` | the Hebrew beginner course, `NN-slug.md` chapters with YAML front matter |
| `music/tracks/<genre_slug>/` | original, royalty-free (CC0) tracks: `.mp3` + `.json` sidecar + `.jpg` cover |
| `music/practice/`, `music/transitions/` | practice drills and transition demos |
| `music/tracklist.plan.json` | master list of tracks to render — the spec |
| `music/SCHEMA.md` | **data contract** for metadata, cues, crates, catalog — read it first |
| `music/catalog.json`, `music/rekordbox/` | generated catalog and Rekordbox XML |
| `crates/` | curated lists of real (commercial) tracks with BPM/key — **never** audio files |
| `sets/` | example DJ sets with transition notes |
| `engine/djlab/` | Python synthesis/production engine; `genres/<slug>.py` = one recipe per genre |
| `tools/` | build/verify scripts (catalog, rekordbox xml, audio QA, site build, library analysis) |
| `docs/` | the static website (Hebrew, RTL), deployed to GitHub Pages |
| `.claude/agents/`, `.claude/skills/` | the DJ Lab agent team and skills |

## Hard rules
1. **No copyrighted audio.** Never add commercial songs, samples, stems or rips. Only audio rendered by
   `engine/djlab` (original, CC0). Crates contain metadata and links only.
2. Renders are deterministic: same spec + seed → same audio. Never hand-edit generated MP3/JSON; change
   the recipe and re-render.
3. Every track obeys the DJ-friendly arrangement rules in `music/SCHEMA.md` (clean intros/outros,
   8-bar phrase grid, first downbeat at 0.0 s).
4. Loudness target: ≈ -9 LUFS integrated (club genres), -11…-12 for hip-hop/lo-fi; true peak ≤ -1.0 dBTP.
5. Hebrew text: natural, friendly, precise. Use RTL-safe Markdown (no leading English words in a line
   when avoidable; wrap code/terms in backticks).
6. Keep the repo lean: MP3 320 kbps only (no WAV in git), covers ≤ 200 KB.

## Common commands
```bash
pip install -r engine/requirements.txt
cd engine && python -m djlab render --id house-05          # render one track from the plan
cd engine && python -m djlab render --genre tech_house     # render all tracks of a genre
cd engine && python -m djlab render --id house-05 --preview # fast 30-second preview
python -m pytest engine/tests -q
python tools/verify_audio.py music/tracks                  # BPM / loudness / tags QA
python tools/build_catalog.py && python tools/build_rekordbox_xml.py && python tools/build_site.py
python -m http.server -d docs 8000                         # preview the site (run from repo root: see docs/README)
python tools/analyze_library.py ~/Music/MyDJ              # BPM/key/Camelot for your own library
```
