---
name: harmonic-next-track
description: Suggest what to play next after a given track (or a key + BPM) - ranks DJ Lab originals, crate tracks and the user's analyzed library by Camelot compatibility, BPM distance (half/double aware) and energy direction, and recommends a transition technique for each. Use for "מה לנגן אחרי Groove Machine?", "what mixes with 8A at 124?", "I'm in Am 95, what's next for the wedding?".
argument-hint: "[track title | id | \"8A 124\"] [up|down|keep]"
allowed-tools: Bash(python .claude/skills/harmonic-next-track/scripts/next_track.py *) Bash(python3 .claude/skills/harmonic-next-track/scripts/next_track.py *) Bash(python tools/camelot.py *) Bash(python3 tools/camelot.py *)
---

# What should I play next?

Query: $ARGUMENTS

Reply in **Hebrew**, short and practical.

## 1. Run
```bash
python .claude/skills/harmonic-next-track/scripts/next_track.py "<title | id | 8A 124 | Am 95>" \
    [--energy up|down|keep] [--genres tech_house,afro_house] [--top 8] [--max-bpm-change 6] [--no-crates]
```
- Sources: `music/catalog.json` (or the plan), `crates/*.csv`, and `library/my_library.csv` automatically if it
  exists (`--library PATH` for another CSV).
- Energy direction: infer from the user's words ("להרים" = up, "להוריד/להרגיע" = down, otherwise keep).
- Quick wheel reference: `python tools/camelot.py 8A 124` (all compatible keys + BPM ±4 % window).

## 2. Answer
Give the top 3–5: title — artist, BPM, Camelot, energy, source (DJ Lab / crate = buy legally / your library),
why it fits (same key, ±1, relative, energy boost), and the transition in one line
(technique + which Hot Cue to start on + bar count). Flag crate rows with `verified` ≠ `yes`
("בדקו Key ב-Rekordbox לפני").

## 3. Camelot cheat-sheet (for explanations)
- Same number+letter = same key (perfect). ±1 same letter = neighbour (safe). Same number, other letter =
  relative major/minor (safe, changes mood). +1 with A→B = diagonal (usually fine).
- +2 = energy shift (short mix). +7 = one semitone up = "energy boost" (cut on the drop).
- Anything else = clash → only with Filter / Echo Out / a drums-only intro.
- BPM: ±2 % unnoticeable, ±4 % fine, ±6 % max stretch; beyond that use Echo Out or half/double time.
