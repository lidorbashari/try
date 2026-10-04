---
name: plan-dj-set
description: Plan a DJ set for a real gig - asks duration, crowd/event, venue and time slot, genres and sources, then builds an ordered set (BPM, key/Camelot, energy, transition technique per pair) from the DJ Lab catalog, crates and the user's analyzed library with tools/set_planner.py and saves it to sets/. Use for "תכין לי סט של שעה לחתונה", "plan a 90-minute techno set", "warm-up set for a bar on Thursday", "סט לבר מצווה".
argument-hint: "[minutes] [event/crowd] [genres]"
allowed-tools: Bash(python tools/set_planner.py *) Bash(python3 tools/set_planner.py *)
---

# Plan a DJ set

Request: $ARGUMENTS

Talk to the user in **Hebrew**. Output file in Hebrew. Never add audio — crate tracks must be bought/streamed legally.

## 1. Brief (ask only what's missing — one short message, or AskUserQuestion with options)
1. משך (minutes) and time slot: warm-up / peak / closing / all night.
2. אירוע וקהל: club, bar, wedding (חתונה), bar/bat mitzvah, house party, beach/rooftop, corporate; ages.
3. ז'אנרים / must-plays / no-go tracks.
4. מקורות: DJ Lab originals only? add crates (real tracks to buy)? the user's library
   (`library/my_library.csv` — if missing, offer the `analyze-my-library` skill)?
If the user says "תחליט אתה", use the presets below and list your assumptions.

## 2. Presets (starting points — adjust to the brief)
| event | curve | start → peak | genres (`--genres`) |
|---|---|---|---|
| club warm-up | `ramp` | 3 → 6 | `deep_house,house,afro_house,melodic_techno` |
| club peak | `arc` | 6 → 9 | `tech_house,techno,melodic_techno` |
| techno night | `arc` | 5 → 10 | `family:techno` |
| bar / lounge | `flat` | 4 → 6 | `nu_disco,deep_house,afro_house,afrobeats` |
| wedding dance floor (Israeli) | `wave` | 6 → 9 | `pop_dance,mediterranean,reggaeton,hip_hop,big_room,afro_house` |
| wedding reception (קבלת פנים) | `flat` | 3 → 5 | `nu_disco,deep_house,afrobeats,lofi` |
| bar/bat mitzvah | `wave` | 6 → 9 | `pop_dance,big_room,reggaeton,mediterranean,hip_hop` |
| house party | `arc` | 5 → 8 | `all` |
Open-format sets (weddings) jump genres and tempos: allow it, but keep 3–5-track genre blocks and use
`--bpm-range` per block if needed (run the planner per block and concatenate).

## 3. Build
```bash
python tools/set_planner.py --minutes <M> --start-energy <S> --peak-energy <P> --curve <arc|ramp|wave|flat> \
  --genres <g1,g2> [--include-crates] [--library library/my_library.csv] [--prefer library] \
  --title "<Hebrew title>" --out sets/<yyyy-mm-dd>-<event-slug>.md
```
Read the table it prints. Check like a DJ: no BPM zig-zag; > 6 % tempo jumps only with Echo Out / cut;
key clashes only with a filter/echo; the peak lands where the slot needs it; vocals don't collide.
Re-run with other options (`--beam 32`, `--bpm-range`, different genres) or reorder by hand and explain why.
For a quick "what next?" use the `harmonic-next-track` skill.

## 4. Finish the file (edit `sets/<…>.md`)
Keep the tool's front matter + table, then add in Hebrew:
- **הנחות** (assumptions) and **בלוקים** (sections of the set with their purpose)
- per transition: start on which Hot Cue (A Intro / B Mix-In / C Breakdown / D Drop / G Outro / H Last 16),
  how many bars, EQ moves — the tool's tips are a starting point
- 2–3 **backup tracks** per block (same key ±1, same BPM ±2 %)
- **צ'קליסט לפני ההופעה**: buy/stream every crate track legally and analyze it in Rekordbox, check Beatgrids,
  set Hot Cues, Auto Gain / Trim, export to USB (Export mode) and test on the venue's player, headphones + adapter.

## 5. Reply (Hebrew)
Path of the file, length and track count, the energy curve in one line, the 2 trickiest transitions and how to
nail them, and an offer: "רוצה שאכין לך תרגיל של היום על המעברים האלה?" (→ `practice-coach`).
