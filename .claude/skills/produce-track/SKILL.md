---
name: produce-track
description: Add one or more new ORIGINAL (CC0) DJ Lab tracks end to end - plan entry in music/tracklist.plan.json, genre recipe, render with the djlab engine, verify BPM/key/LUFS/arrangement, then rebuild catalog, Rekordbox XML and site. Use when the user asks to add/make/produce tracks ("תוסיף 5 טראקים של אפרו האוס", "make two more melodic techno tracks", "add a 100 BPM mediterranean track").
argument-hint: "[genre_slug] [count] [notes]"
arguments: [genre, count]
allowed-tools: Bash(python .claude/skills/produce-track/scripts/plan_helper.py *) Bash(python3 .claude/skills/produce-track/scripts/plan_helper.py *)
---

# Produce new DJ Lab tracks

Request: genre `$genre`, count `$count`. Full request: $ARGUMENTS

Instructions are in English; everything you show the user is in **Hebrew** (DJ terms in English).
Hard rule: only audio rendered by `engine/djlab` — no samples, loops, stems or melodies of existing songs.
If the user asks for "a track like <famous song>", make an original track in that *genre/mood* and say so.

## 0. Context
- Read `CLAUDE.md` and `music/SCHEMA.md` §1–2 (plan fields, outputs, cues, arrangement rules).
- Current state: `python .claude/skills/produce-track/scripts/plan_helper.py status`
- If `engine/djlab/genres/$genre.py` doesn't exist → run the `new-genre` skill first.

## 1. Plan entries
1. `python .claude/skills/produce-track/scripts/plan_helper.py next --genre $genre --count $count`
   gives free ids, unique seeds and Camelot keys that are wheel-neighbours of the genre's existing tracks.
2. Fill in each stub: English + Hebrew title (Israeli flavour welcome: places, beaches, neighbourhoods),
   `file_stem` = `<id>-<kebab-title>`, BPM inside the genre's real range (vary ±2 BPM), energy 1–10 and
   role (`warmup|build|peak|closing`) so the genre covers a range of set slots, `target_minutes`.
3. Append to `music/tracklist.plan.json` (keep the file's formatting; ids and seeds must stay unique).
   Re-run `plan_helper.py status` — it must report no duplicates/mismatches.

## 2. Render (delegate to the `music-producer` agent when doing more than one track)
```bash
cd engine && python -m djlab render --id <id> --preview   # 30 s sanity check
cd engine && python -m djlab render --id <id>             # full render: mp3 + json + jpg
```
Change the recipe/seed, never the generated files.

## 3. Verify (all must pass)
```bash
cd engine && python -m djlab analyze ../music/tracks/<genre>/<file_stem>.mp3
python tools/verify_audio.py music/tracks/<genre>
python tools/analyze_library.py music/tracks/<genre> --out /tmp/djlab-check.csv --force --quiet
```
- measured BPM == plan BPM; measured Camelot == plan (or its relative A↔B)
- LUFS ≈ -9 (club) / -11…-12 (hip-hop, lo-fi); true peak ≤ -1.0 dBTP
- first downbeat 0.0 s; intro ≥ 16 bars with no bass/tonal content in the first 16 bars; sections on 8-bar
  boundaries; Hot Cues A–H per SCHEMA
- determinism: rendering the same id twice gives the same audio (compare `md5sum` of the mp3s)

## 4. Publish locally
```bash
python tools/build_catalog.py && python tools/build_rekordbox_xml.py && python tools/build_site.py
```
Optionally run the `release-check` skill (`--quick` is enough for a single track).

## 5. Tell the user (Hebrew)
For each track: title / שם, BPM, Key + Camelot, energy, role, path, and one mixing tip ("מתחבר מעולה
ל-<existing track> — שכן ב-Camelot"). Remind how to import: Rekordbox → File → Import → the folder, or the
Rekordbox XML in `music/rekordbox/` (Hot Cues included). Do not commit unless asked.
