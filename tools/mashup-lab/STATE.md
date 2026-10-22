# Mashup Lab — working state (checkpoint file)

> Lidor asked (2026-10-22 23:42): always keep checkpoints so a new session can pick up exactly where the last one
> stopped, and continue automatically. **This file is that checkpoint.** Update it and push it after every
> meaningful step (commit with `[skip ci]` when only this file changes).

Heartbeat (UTC): 2026-10-22T20:55Z · session: https://claude.ai/code/session_01Lo7gTW4YHqF6LiS4xWstjM · status: IN PROGRESS

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
- [ ] 1. Audit the undeployed sources (engine/app/word-play) and run every local suite.
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

## Log (newest first)
- 2026-10-22 20:55Z: container was reset; repo re-cloned; this checkpoint file created.
