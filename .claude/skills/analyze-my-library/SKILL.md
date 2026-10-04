---
name: analyze-my-library
description: Analyze a folder of the user's OWN legally bought music (mp3/wav/aiff/flac/m4a) with tools/analyze_library.py - BPM (half/double corrected), key + Camelot with confidence, LUFS, duration, energy estimate and existing tag BPM/key mismatches - write a CSV and explain the results in Hebrew with practical Rekordbox suggestions. Use for "תנתח לי את התיקייה של השירים שקניתי", "what keys are my tracks in?", "check my library's BPM tags".
argument-hint: "[folder path]"
allowed-tools: Bash(python tools/analyze_library.py *) Bash(python3 tools/analyze_library.py *)
---

# Analyze the user's own music library

Folder: `$ARGUMENTS`

The audio stays where it is. Only a CSV of numbers is written (default `library/my_library.csv`).
**Never copy, convert, upload or commit the user's audio files into this repo**, and don't analyze
anything the user says isn't theirs to use.

## 1. Check inputs
- If no folder was given, ask for it in Hebrew (e.g. `~/Music/DJ` on Mac, `C:\Users\<name>\Music` on Windows,
  or the folder Rekordbox imports from). In a cloud session the user's computer isn't reachable — explain
  that they need to run Claude Code locally (or run the command themselves and share the CSV).
- Count files first: `find "<folder>" -type f \( -iname '*.mp3' -o -iname '*.wav' -o -iname '*.aif*' -o -iname '*.flac' -o -iname '*.m4a' \) | wc -l`
- Dependencies: `python -c "import librosa, pyloudnorm, mutagen"` and `ffmpeg -version`; if missing →
  `pip install -r engine/requirements.txt` / install ffmpeg.

## 2. Run
```bash
# < 300 files: full analysis
python tools/analyze_library.py "<folder>" --jobs 4
# big libraries: 60 s from the middle of each track (5-10x faster), incremental on re-runs
python tools/analyze_library.py "<folder>" --jobs 4 --sample 60
```
Re-runs skip unchanged files (size + mtime); `--force` re-analyzes everything. `--out` changes the CSV path.

## 3. Explain (Hebrew, concise)
Use the tool's Hebrew summary plus the CSV (`library/my_library.csv`, columns: `bpm, bpm_alt, bpm_confidence,
key, camelot, key_confidence, key_alt_camelot, lufs, energy_est, tag_bpm, tag_key, bpm_check, key_check`):
- BPM distribution → which genres/set types the library supports; gaps ("אין לך כמעט טראקים ב-100–115").
- Keys: most common Camelot codes and harmonic "clusters" the user can mix within.
- `bpm_check = half_double` → harmless display difference; `mismatch` → fix the Beatgrid in Rekordbox.
- `key_check = relative` → same Camelot number, still compatible; `mismatch` → trust ears / Beatport.
- Low `key_confidence` (< 0.35) or empty key → drum tools / atonal tracks; use `key_alt_camelot` or ears.
- Loudness outliers (±3 LU from the median) → `Auto Gain` / `Trim`.
- `energy_est` is a rough 1–10 guess (loudness + density + tempo) — useful for set planning, not gospel.
Rekordbox tips: show Camelot (Preferences → View → Key display format → Alphanumeric), analyze with
"Dynamic" BPM only for live-drummer tracks, and keep the tool's numbers as a second opinion.

## 4. Next steps to offer
- `plan-dj-set` with `--library library/my_library.csv` ("תכין לי סט מהשירים שלי").
- `harmonic-next-track` ("מה לנגן אחרי <טראק>?").
- If the repo is public, mention the CSV lists their track names; offer to keep it out of git.
