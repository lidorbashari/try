# Mashup Lab: sources, build and tests

The app at `docs/mashup-lab/index.html` (live: https://lidorbashari.github.io/try/docs/mashup-lab/) is ONE built
HTML file. This folder holds what it is built from, and the tests. The layout mirrors the working tree the app was
developed in, so every script runs from here as well.

| path | what |
|---|---|
| `lab5/engine.js` | `window.MashEngine`: decoded-buffer decks on one AudioContext, WSOLA time-stretch, key shift, beat grids, fine alignment, song-analysis use (phrase entry, key match, loudness), the word-play player (`E.wordplay`), the `<audio>` fallback and the Studio Groove synth |
| `lab5/app.html` | the UI template (Hebrew, RTL); `build.py` inlines data + engine + word-play scripts |
| `lab5/wordplay/` | word-play links (`links.json`, curated), `wordplay.js` (link finder), `timing.js` (`WordTiming.plan`: where the cut lands, from beat grids + word timestamps), `wordplay_ui.js` (the "מעברים" tab) |
| `lab5/data.json`, `src.json` | the track catalog and its sources |
| `pwa/` | service worker (same-origin only; Apple audio is never cached), manifest, icons |
| `lab5/qa/`, `lab5/app_test/`, `lab5/engine_test/` | app end-to-end, UI and engine suites |
| `lead_check/beat/`, `lead_check/wp/` | sync and word-play tests measured on recorded audio |
| `*.json` here | small fixtures the end-to-end server serves |

Data the app loads at runtime (built on GitHub Actions from the Apple previews, numbers only):
`docs/mashup-lab/previews.json` (`tools/mashup_lab_previews.py`), `beats.json` (`tools/mashup_lab_beats.py`),
`analysis.json` + `wordtimes.json` (`tools/mashup_lab_analyze.py`, Demucs + key + loudness + Whisper word times).

## Build and deploy
```bash
cd tools/mashup-lab/lab5
python3 build.py             # → ../mashup-lab.html (+ the Claude artifact fragment)
python3 deploy.py            # → docs/mashup-lab/index.html, sw.js, manifest, icons + tools/verify/mashup-lab-next.html
```
Pushing `tools/verify/**` runs the real-music checks on CI (`mashup-verify.yml`, `mashup-verify-wordplay.yml`);
their reports land in `tools/reports/`.

## Tests (Python 3 + Playwright Chromium + numpy; node for the timing unit test)
Test media are generated, never committed (no WAV in git):
```bash
python3 lab5/engine_test/make_wavs.py && mkdir -p lab5/qa/media && cp -r lab5/engine_test/wav lab5/qa/media/
(cd lead_check/beat && python3 mkwav.py) && (cd lead_check/wp && python3 mkwav.py)
node lab5/wordplay/test/t_timing.js          # word-play timing
(cd lead_check/wp && python3 t_wp.py)         # word play on recorded audio
(cd lead_check/beat && python3 t_buf.py)      # buffer sync, stretch, key shift, analysis
bash lab5/qa/run_all.sh                       # build + app E2E + UI + fallback sync
```
Rules: no copyrighted audio and no lyrics in the repo; previews stream from Apple and are decoded in memory only.
