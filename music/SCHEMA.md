# DJ Lab — Music Data Contract

This file is the single source of truth that the engine, tools, website and agents all agree on.
Change it only through the orchestrator.

## 1. Master plan: `music/tracklist.plan.json`
An array of track specs. Each entry:

| field | example | meaning |
|---|---|---|
| `id` | `house-03` | stable id, `<family>-<NN>` |
| `file_stem` | `house-03-hands-up-florentin` | filename without extension |
| `family` | `house` \| `techno` \| `mainstream` \| `breadth` | family / producer group |
| `genre_slug` | `tech_house` | folder name + recipe name in `engine/djlab/genres/` |
| `genre` | `Tech House` | display genre (also ID3 genre) |
| `bpm` | `126` | exact tempo; the grid is perfectly constant |
| `key` / `key_short` / `camelot` | `A minor` / `Am` / `8A` | musical key |
| `energy` | `1..10` | energy rating used for set planning |
| `role` | `warmup` \| `build` \| `peak` \| `closing` | typical slot in a set |
| `title` / `title_he` | `Groove Machine` / `מכונת גרוב` | names |
| `target_minutes` | `4.3` | approximate length (actual = whole number of 8-bar phrases) |
| `seed` | `1034` | RNG seed — renders are deterministic |
| `producer` | `house` | which producer agent owns it |

## 2. Output files per track
```
music/tracks/<genre_slug>/<file_stem>.mp3   MP3, 320 kbps CBR, 44.1 kHz, stereo
music/tracks/<genre_slug>/<file_stem>.json  metadata sidecar (below)
music/tracks/<genre_slug>/<file_stem>.jpg   cover art, 800x800 JPEG (also embedded in ID3 APIC)
```

### ID3v2.4 tags (written with mutagen)
`TIT2` title · `TPE1` "DJ Lab Originals" · `TALB` "DJ Lab — <family> Vol. 1" · `TCON` genre ·
`TBPM` bpm (integer) · `TKEY` key_short (e.g. `Am`) · `COMM` "Camelot 8A · Energy 7 · CC0" ·
`TDRC` 2026 · `TCOP` "CC0 1.0" · `APIC` cover.

### Sidecar JSON
```json
{
  "id": "house-05", "title": "Groove Machine", "title_he": "מכונת גרוב",
  "artist": "DJ Lab Originals", "genre": "Tech House", "genre_slug": "tech_house", "family": "house",
  "bpm": 126.0, "key": "A minor", "key_short": "Am", "camelot": "8A",
  "energy": 7, "role": "peak",
  "duration_sec": 258.1, "bars": 136, "beats_per_bar": 4,
  "first_downbeat_sec": 0.0,
  "sections": [ {"name": "Intro", "start_bar": 0, "bars": 32, "start_sec": 0.0, "energy": 4}, ... ],
  "cues": [ {"slot": "A", "name": "Intro", "bar": 0, "sec": 0.0, "color": "#28E214", "type": "hot"}, ... ],
  "memory_cues": [ {"name": "Breakdown", "bar": 64, "sec": 121.9} ],
  "lufs": -9.2, "true_peak_dbtp": -1.0,
  "file": "music/tracks/tech_house/house-05-groove-machine.mp3",
  "cover": "music/tracks/tech_house/house-05-groove-machine.jpg",
  "description_he": "שורה-שתיים על הטראק בעברית",
  "mix_tips_he": "טיפ ערבוב: אינטרו של 32 תיבות תופים בלבד, באס נכנס בתיבה 17…",
  "instruments": ["909 kick", "rolling bass", "shaker", "stab"],
  "seed": 1034, "license": "CC0-1.0", "engine_version": "1.0.0"
}
```
All times are in seconds from the very first sample. **Every track starts exactly on beat 1 of bar 1**
(`first_downbeat_sec` = 0.0, no leading silence) so beatgrids are trivial.

### Hot cue convention (Rekordbox slots A–H)
| slot | name | color | where |
|---|---|---|---|
| A | Intro | `#28E214` green | bar 0 |
| B | Mix-In / Groove | `#10B1E6` aqua | first bar where bass/full groove enters |
| C | Breakdown | `#E0641B` orange | first breakdown |
| D | Drop | `#E62828` red | first drop / main hook |
| E | Breakdown 2 | `#B4BE04` yellow | optional second breakdown |
| F | Drop 2 | `#DE44CF` pink | optional second drop |
| G | Outro | `#305AFF` blue | start of DJ-friendly outro |
| H | Last 16 | `#8A2BE2` purple | 16 bars before the end |

### DJ-friendly arrangement rules (all 4/4 club genres)
- Intro ≥ 16 bars (usually 32) of drums/percussion with **no bass and no melodic/tonal content in the first 16 bars**.
- Outro ≥ 16 bars (usually 32) mirroring the intro (bass out, drums only at the end).
- Every section boundary on a multiple of 8 bars. Phrase marker (subtle crash / fill) every 8 or 16 bars.
- Hip-hop / reggaeton / afrobeats / lo-fi: shorter intro/outro (8–16 bars) is fine, still phrase-aligned.

## 3. Practice & transition files
```
music/practice/<id>.mp3 + .json      kind = "practice"  (id like practice-01)
music/transitions/<id>.mp3 + .json   kind = "transition" (id like transition-01)
```
Their JSON has `id, kind, title, title_he, bpm, key?, duration_sec, description_he, exercise_he` (+ for
transitions: `from_id, to_id, technique, technique_he, steps_he[]`).

## 4. Aggregated catalog: `music/catalog.json`
Built by `tools/build_catalog.py`:
```json
{ "generated_at": "...", "engine_version": "1.0.0",
  "tracks": [ <sidecar>, ... ], "practice": [ ... ], "transitions": [ ... ] }
```
The website consumes `docs/data/catalog.js` (`window.DJLAB_CATALOG = {...}`) generated from it by
`tools/build_site.py`. Paths inside are repo-relative (`music/...`); the site prefixes a base path.

## 5. Crates (real tracks): `crates/`
`crates/<crate_slug>.csv` with header:
`artist,title,mix,label,year,bpm,key,camelot,energy,role,verified,notes_he`
- `verified`: `yes` (BPM and key confirmed by ≥1 reliable source), `partial`, or `no`.
- `crates/<crate_slug>.md`: Hebrew intro to the genre + the table + where to buy/stream legally.
- `crates/index.json`: `[{"slug","title_he","title","genres":[...],"count","file_csv","file_md"}]`.

## 6. Camelot reference
1A Abm · 1B B · 2A Ebm · 2B F# · 3A Bbm · 3B Db · 4A Fm · 4B Ab · 5A Cm · 5B Eb · 6A Gm · 6B Bb ·
7A Dm · 7B F · 8A Am · 8B C · 9A Em · 9B G · 10A Bm · 10B D · 11A F#m · 11B A · 12A C#m · 12B E
