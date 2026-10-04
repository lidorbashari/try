---
name: crate-research
description: Research real commercial tracks for a crate (genre, mood or gig) with BPM, key, Camelot, energy and role verified against reliable sources, and write crates/<slug>.csv + crates/<slug>.md exactly per music/SCHEMA.md section 5 (metadata + legal store links only, never audio). Use for "תמצא לי 20 טראקים של אפרו האוס", "build a crate of Israeli wedding bangers", "verify the keys in crates/techno.csv", "add newer tracks to the melodic techno crate".
argument-hint: "[crate slug or theme] [count]"
allowed-tools: Bash(python .claude/skills/crate-research/scripts/validate_crate.py *) Bash(python3 .claude/skills/crate-research/scripts/validate_crate.py *) Bash(python tools/build_catalog.py *) Bash(python3 tools/build_catalog.py *)
---

# Crate research

Theme: $ARGUMENTS

Rows are real songs by real artists → **metadata and official links only**. Never download, rip, or link to
unofficial audio. Never invent a track — if you can't confirm it exists, drop it.

## 1. Scope
Read `music/SCHEMA.md` §5–6 and the existing crates (`ls crates/`, `crates/index.json`). Extend an existing
crate when the theme matches; otherwise create a new kebab-case slug. Target 15–30 rows: ~20 % classics,
~80 % from the last 5 years, a spread of energy (warm-up → peak) and keys that connect on the Camelot wheel.

## 2. Research each track (WebSearch / WebFetch)
1. Find the official release (Beatport / Traxsource / Bandcamp / label / artist page): artist, title, mix
   (Original / Extended / Radio Edit / specific remix), label, year.
2. BPM + key from the store page; cross-check with a second source (Tunebat, SongBPM, Mixed In Key-based
   lists, Rekordbox-analysed values in DJ forums). Watch out for half/double BPM (hip-hop 85 vs 170, DnB 87 vs 174)
   and relative-key confusion (Am vs C).
3. `verified`: `yes` = BPM and key confirmed by ≥ 1 reliable source and not contradicted; `partial` = only
   one confirmed or sources disagree (say which in `notes_he`); `no` = estimate (leave BPM/key blank if you
   truly don't know — the planner skips blank rows).
4. Camelot from the key with the SCHEMA §6 table (`python tools/camelot.py <key>` prints it).
5. `energy` 1–10 and `role` (`warmup|build|peak|closing`) from listening notes/reviews and tempo/genre.
6. `notes_he`: one practical Hebrew line — where it works in a set, intro length, vocal warnings, a mixing tip.

## 3. Write
- `crates/<slug>.csv` with the exact header
  `artist,title,mix,label,year,bpm,key,camelot,energy,role,verified,notes_he` (UTF-8, quote commas).
- `crates/<slug>.md` in Hebrew: intro to the genre/mood (sound, history, BPM range, key artists, Israeli
  angle when relevant), how to mix it, the table (title, artist, BPM, Key/Camelot, energy, role), and
  "איפה קונים/מזרימים באופן חוקי" (Beatport, Traxsource, Bandcamp, Apple Music/iTunes, Beatport/SoundCloud/TIDAL
  streaming inside Rekordbox).

## 4. Validate & index
```bash
python .claude/skills/crate-research/scripts/validate_crate.py crates/<slug>.csv   # 0 errors required
python tools/build_catalog.py                                                     # rebuilds crates/index.json
```
Then report (Hebrew to the user): count, verified yes/partial/no, 3 highlight tracks with why, and how to use
the crate (`plan-dj-set` with `--include-crates`, `harmonic-next-track`).
