# Mashup Lab — working state (checkpoint file)

> Lidor asked (2026-10-22 23:42): always keep checkpoints so a new session can pick up exactly where the last one
> stopped, and continue automatically. **This file is that checkpoint.** Update it and push it after every
> meaningful step (commit with `[skip ci]` when only this file changes).

Heartbeat (UTC): 2026-10-23T02:03Z · session: https://claude.ai/code/session_01Lo7gTW4YHqF6LiS4xWstjM · status: IN PROGRESS (resume from "Next actions")

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
- [~] 3. Matching v2 (`lab5/match.js`, unit test `lab5/test/t_match.js` 11/11; app: `mPair()` in findPairs when both
        previews are measured, MIN_MEASURED 70; engine 6.3: `E.setPlan` / loadPair(v,b,r,plan): entry bars + lead,
        fractional key shift, B unclean when it doesn't sing there, vocal gate on A from `vr`). Needs calibration on
        the real listen.json once CI lands. Matching v2 from the analysis: rank by measured key fit (with best ±2 semitone shift), vocal clash,
        beat-side vocal share, energy, loudness; explain "why it works" with the measured numbers.
- [~] 4. Word play v2 (wordplay_ui.js: "disc" links found by listening, default filter = words heard in both
        previews, time chips, diagram of the move with a playhead; e2e kept compatible). Word play v2: words found in more links (auto-discover links from transcripts), cut lands on the grid,
        B beat-matched + key-shifted to A, teaching timeline.
- [x] 5. Liquid Glass motion system (ui/liquid.js + ui/liquid.css, committed c6f456b; screenshots looked right in
        light + dark). Liquid Glass motion system: spring physics, lens that magnifies/refracts the tab bar items while it
        moves and when dragged, morphing segmented controls, sheet + mini-player transitions, reduced-motion.
- [~] 6. Finished-product pass (welcome sheet on first run, share button + #m=vi.bi deep links, matching text in the
        about sheet, measured badge + reasons on cards). Finished-product pass: onboarding, empty/loading/error states, share/deep links, install prompt, about +
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

## Next actions (in order)
0. Done since the last checkpoint (all pushed): analysis v2 merged (7c0bba7); matcher v2.1 (cccd8a6); engine 6.4 hit
   lock + Tempo Ride (06ad5f3); word-play key by ear (187e3f0); ride stripe on the diagram (80609b8); skills proposed
   to Lidor (mashup-listening, liquid-glass-web, dj-wordplay-transitions improvement — drafts in scratchpad/skills).
   Full local QA green on the final build: t_buf 141/141, t_match 13/13, t_timing OK, grep 32, e2e_audio 35,
   e2e_wordplay 25, UI 32/26/55, sync 58. Build bbf3ce92d2 pushed to tools/verify (69ab29c) → CI runs
   39887177487 (sync) and 39887177489 (word play) started 02:00Z.
1. (done) CI checks running on build bbf3ce92d2. Reports: tools/reports/mashup-verify.txt, mashup-wordplay.txt (want: sync hits ≤ 10 ms as before;
   word play share_beat_continues well above the old 0.51, ride links measured while holding).
2. If the reports are good: deploy docs/ (index.html, sw.js, manifest, icons) — `python3 deploy.py` and commit
   docs/mashup-lab/* — push both branches (`claude/dj-course-music-agents-suitm3` and `mashup-lab-site`); message Lidor
   in Hebrew (what changed, how to try it).
3. Propose skills with propose_skills (drafts in scratchpad/skills: mashup-listening, liquid-glass-web,
   dj-wordplay-transitions improvement) — update them with: Pearson profiles + calibration numbers, hit lock, tempo ride.
4. Still open: more well-known techno and amapiano tracks (task 8); word-play key choice from the measured profiles
   (hc/vc Pearson) instead of Camelot labels (idea).

## Research notes (2026-10-22, for the skills)
- AutoMashUpper (Davies et al., IEEE TASLP 2014): beat-synchronous chroma cross-correlated over all 12 shifts;
  rhythm = kick + snare onsets at 12 positions per beat (24 dims); spectral balance = flatness of the summed
  low (<220 Hz) / mid (220–1760) / high band loudness; tuning correction skipped within 0.5 %; wide shifts hurt vocals,
  most when raising female or lowering male voices; ratings correlate better when the vocals don't overlap.
- iOS 26 tab bar (MacStories review): long-press turns the highlight into a selection bubble with lensing + chromatic
  aberration, sliding shows the content inside it; scrolling down collapses to the current tab as a circle; tapping
  the selected tab re-expands; the mini player slides down next to the collapsed tab.
- Liquid Glass API notes (github.com/conorluddy/LiquidGlassReference): interactive glass = scale, bounce, shimmer,
  touch-point illumination; samples use .bouncy(0.35–0.4) and spring(response .3, damping .6) for drag release;
  GlassEffectContainer spacing ≈ 20–40 pt is the merge distance for morphs; Reduce Motion tones elastic effects down.
- Word play (We Are Crossfader, 12 high-energy transitions): 1-beat echo on A just before the line, 4-beat loop on
  A's line while B starts on the same beat, cut A's fader after the line, repeat for 16 bars, then echo A out;
  loop roll = 1-beat loop halved into B's drop.

## Log (newest first)
- 2026-10-23 02:03Z: QA all green; build bbf3ce92d2 in CI real-music checks; skills proposed.
- 2026-10-23 02:20Z: resumed after the usage pause (Lidor: continue from the state file). Matcher v2.1, engine 6.4 (hit lock + tempo ride) pushed; full QA running.
- 2026-10-22 21:53Z: Lidor warned the session limit is near; checkpoint pushed (see Next actions 0).
- 2026-10-22 21:46Z: container restarted once (disk kept). Verify scripts now play through the app path and log
  the plan; word-play check adds the discovered links.
- 2026-10-22 21:36Z: Liquid layer + matcher + word play v2 + welcome/share written and building; waiting for the
  analysis v2 CI run (12/22 jobs done) to calibrate the matcher on real data, then all suites + CI checks + deploy.
- 2026-10-22 21:00Z: analysis v2 dispatched; current build in CI real-music checks; auto-resume scheduled
  (send_later trig_01Q5YdujST43ePkxZzTNRdGn at 23:15Z).
- 2026-10-22 20:55Z: container was reset; repo re-cloned; this checkpoint file created.
