# Mashup Lab — working state (checkpoint file)

> Lidor asked (2026-10-22 23:42): always keep checkpoints so a new session can pick up exactly where the last one
> stopped, and continue automatically. **This file is that checkpoint.** Update it and push it after every
> meaningful step (commit with `[skip ci]` when only this file changes).

Heartbeat (UTC): 2026-10-22T21:02Z · session: https://claude.ai/code/session_01Lo7gTW4YHqF6LiS4xWstjM · status: IN PROGRESS

## How to resume in a fresh session
1. Attach the repo with push access (`add_repo lidorbashari/try`), clone to `/home/claude/try`, branch
   `claude/dj-course-music-agents-suitm3` (GitHub Pages deploys from it; `mashup-lab-site` is a mirror, push both
   when deploying).
2. Read this file, then `tools/mashup-lab/README.md` (layout, build, tests).
3. Build: `cd tools/mashup-lab/lab5 && python3 build.py && python3 deploy.py` (deploy writes `docs/mashup-lab/`
   and `tools/verify/mashup-lab-next.html`; pushing `tools/verify/**` runs the real-music CI checks).
4. Live app: https://lidorbashari.github.io/try/docs/mashup-lab/ · reply to Lidor in Hebrew, always.
5. Container tools: Playwright Chromium at /opt/pw-browsers (no WebKit locally); the container cannot reach
   Apple's CDN — anything that needs the real previews runs on GitHub Actions.

## What Lidor wants now (2026-10-22 23:24 + 23:42)
- "Listen to the songs" and match them much better (pairs that truly fit: key/melody, vocals, phrases, energy).
- Word-play transitions (מעברי מילים) exactly on the beat, same BPM, in key — sounding good, and clear enough
  to learn how to do them.
- Learn from the web, write skills, do whatever is needed.
- A **finished product**, excellent not just good — including animations: real Apple-like Liquid Glass that
  moves/morphs like glass when switching between items (tab bar lens, segmented controls, sheets, mini player).
- Checkpoints + automatic continuation after a session ends.

## Status
### Done before this session (all in git)
- App (one HTML, Hebrew RTL) with 1,271 tracks, pairs, mixer, decks, crossfader, word-play tab, PWA files.
- Original Apple previews via `previews.json` (1,200 found). Beat grids for 1,200 previews (`beats.json`,
  Beat This!, fit v2). Decoded-buffer playback, WSOLA stretch, fine alignment (live since 4c53287).
- Song analysis on GitHub Actions (`tools/mashup_lab_analyze.py`, `mashup-analyze.yml`): Demucs stems, key
  (essentia), harmonic + vocal chroma, LUFS, vocal/energy per beat, sections → `docs/mashup-lab/analysis.json`
  (1,200 ok). Whisper word times for the curated word-play links → `wordtimes.json` (27/95 links with both words).
- Sources + tests committed under `tools/mashup-lab/` (engine with key shift, phrase entry, loudness match,
  `E.wordplay` player; `wordplay/timing.js`). **Not deployed yet**: live index.html is still 4c53287.

### This session — plan (tick as done)
- [x] 1. Audit the undeployed sources (engine/app/word-play) and run every local suite. All green on 2026-10-22 21:00Z:
        timing 22, t_wp 27/27, t_buf 115/115, grep 32, e2e_audio 35, e2e_wordplay 25, UI 32/26/55, sync 58.
        Pushed that build to `tools/verify/` (14c91eb) → CI real-music checks (sync + word play) running; publish to
        docs/ only if both reports are good (`tools/reports/mashup-verify.txt`, `mashup-wordplay.txt`).
- [~] Analysis v2 on CI (run 39853312250, dispatched with part=tracks force=true): listen.json (vb/hb per-bar notes
        and chords, vr vocal level per beat), analysis.json + tc/vp/rp, title words heard in every preview →
        `tools/reports/mashup-titlewords.json` and wordtimes.json `disc` (links found by listening). ~1 h.
- [ ] 2. Research (web): mashability, harmonic mixing + key shift limits, phrase matching, word-play technique,
        Liquid Glass motion; write skills.
- [ ] 3. Matching v2 from the analysis: rank by measured key fit (with best ±2 semitone shift), vocal clash,
        beat-side vocal share, energy, loudness; explain "why it works" with the measured numbers.
- [ ] 4. Word play v2: words found in more links (auto-discover links from transcripts), cut lands on the grid,
        B beat-matched + key-shifted to A, teaching timeline.
- [ ] 5. Liquid Glass motion system: spring physics, lens that magnifies/refracts the tab bar items while it
        moves and when dragged, morphing segmented controls, sheet + mini-player transitions, reduced-motion.
- [ ] 6. Finished-product pass: onboarding, empty/loading/error states, share/deep links, install prompt, about +
        attribution, dark mode, performance.
- [ ] 7. Verify (local suites + CI real-music checks + screenshots), deploy, update Lidor.

## Design notes for the next steps
- Matching v2 (app, `lab5/match.js` to be written): AutoMashUpper-style. For a pair (V vocal, B beat) with listen.json:
  best (vocal 8-bar window, beat start bar, key shift s ∈ −2..2 + tuning cents) maximising bar-aligned cosine of
  V's sung notes vs B's chords, minus B's vocal level during V's singing (clash), tempo stretch, shift cost
  (raising a high voice / lowering a low one costs more, `vp`), groove similarity (`rp`). Engine gets a plan
  {semis (float), aAt, bAt} instead of its own Camelot key shift + first-phrase entry.
- Beat deck clean-up only when B actually sings in the window (vr); otherwise B plays full (snares, synths).
- Word play: curated links (27/95 with both words) + `disc` links (A sings B's title, both found in the previews).
- Liquid Glass: Safari can't do SVG backdrop-filter; do refraction on our own content: a magnified copy of the
  tab row inside the lens (+ feDisplacementMap via CSS filter on that copy), spring physics with velocity stretch,
  lift on press/drag, chromatic rim while lifted, tab bar minimises on scroll (iOS 26), sheets with springs.

## Log (newest first)
- 2026-10-22 21:00Z: analysis v2 dispatched; current build in CI real-music checks; auto-resume scheduled
  (send_later trig_01Q5YdujST43ePkxZzTNRdGn at 23:15Z).
- 2026-10-22 20:55Z: container was reset; repo re-cloned; this checkpoint file created.
