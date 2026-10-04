---
name: new-genre
description: Create a new genre recipe for the DJ Lab synthesis engine (engine/djlab/genres/<slug>.py) following the cookbook in engine/djlab/genres/README.md, then plan and render a first track to prove it. Use when the user wants a style the repo doesn't have yet ("add Melodic House", "I want Baile Funk / Jersey Club / Organic House / Israeli trance"), or when a genre_slug in the plan has no recipe.
argument-hint: "[genre name or slug]"
---

# Add a new genre to the engine

Genre requested: **$ARGUMENTS**

All audio is synthesized by our engine — original, CC0. Research the *style* (tempo, groove, instruments,
arrangement), never copy a specific song's melody, hook, lyrics, vocal or sample.

## 1. Understand the engine
1. Read `CLAUDE.md`, `music/SCHEMA.md` (arrangement rules, cues, loudness) and the cookbook
   **`engine/djlab/genres/README.md`** (recipe API, building blocks, how recipes are registered/discovered).
2. List existing recipes: `ls engine/djlab/genres/`. Pick the 1–2 closest relatives (e.g. organic house →
   `afro_house` + `deep_house`; jersey club → `ukg`/`breaks`) and read them fully.

## 2. Genre brief (write it as a docstring at the top of the recipe)
- slug (snake_case, e.g. `organic_house`), display name, family (`house|techno|mainstream|breadth`)
- BPM range and default; swing/shuffle amount; time feel (4/4, half-time, dembow, 2-step, breakbeat)
- drum pattern per 16th step (kick, clap/snare, hats, percussion), bass style, harmony (typical modes /
  progressions), lead/pad/texture palette, FX (risers, crashes, phrase markers)
- arrangement (bars per section) that obeys SCHEMA: intro ≥ 16 bars drums only (no bass/tonal content in
  bars 1–16), outro mirrors intro, 8-bar grid, first downbeat at 0.0 s; short-form genres (hip-hop, reggaeton,
  afrobeats, lo-fi) may use 8–16-bar intros
- loudness target (-9 LUFS club, -11…-12 hip-hop/lo-fi), true peak ≤ -1.0 dBTP
Use WebSearch for tempo/groove facts if unsure (e.g. "amapiano log drum pattern BPM"), but write the parts
yourself.

## 3. Implement
- Create `engine/djlab/genres/<slug>.py` following the cookbook exactly (same function signature/registration
  as the other recipes). Reuse engine building blocks (`drums`, `synth`, `instruments`, `fx`, `arrangement`,
  `mixer`, `master`); don't modify engine core — if something is missing, note it for the orchestrator.
- Deterministic: all randomness from the seed passed in.
- If `engine/tests` has per-genre tests or a registry test, make sure the new recipe is covered
  (`python -m pytest engine/tests -q`).

## 4. Prove it with a first track
Run the `produce-track` skill for 1 track of the new genre (plan entry → render → verify). Listen-check via
the numbers: `python -m djlab analyze`, `python tools/verify_audio.py music/tracks/<slug>`, and
`python tools/analyze_library.py music/tracks/<slug> --out /tmp/x.csv --force`.

## 5. Report (Hebrew to the user)
What the genre is (2–3 lines), BPM range, what makes our recipe sound like it, the first track's details,
and suggestions for 2–3 more tracks. Mention `crate-research` if the user wants real tracks of this genre.
