"""Track rendering pipeline: plan entry → recipe → Song → mix → master → MP3 + JPG + JSON."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from . import PLAN_PATH, SR, TRACKS_DIR, scratch_dir
from .arrangement import Song
from .genres import get_recipe


def load_plan(path: Path = PLAN_PATH) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def plan_entry(track_id: str, plan: list[dict] | None = None) -> dict:
    for e in plan or load_plan():
        if e["id"] == track_id:
            return e
    raise KeyError(f"unknown track id {track_id!r}")


def build_song(plan: dict) -> Song:
    recipe = get_recipe(plan["genre_slug"])
    rng = np.random.default_rng(int(plan["seed"]))
    song = recipe(plan, rng)
    if not isinstance(song, Song):
        raise TypeError(f"recipe for {plan['genre_slug']} must return a Song")
    validate_song(song)
    return song


def validate_song(song: Song) -> None:
    if not song.sections:
        raise ValueError("song has no sections (call song.arrange(...))")
    for s in song.sections:
        if s.start_bar % 8 or s.bars % 8:
            raise ValueError(f"section {s.name} not on the 8-bar grid ({s.start_bar}, {s.bars})")
    if not song.layers:
        raise ValueError("song has no layers")


def preview_window(song: Song, bars: int = 16) -> tuple[int, int]:
    d = song.bar("drop")
    if d is None:
        d = song.mix_in_bar or song.sections[min(1, len(song.sections) - 1)].start_bar
    start = max(0, d - bars // 2)
    end = min(song.total_bars, start + bars)
    return start, end


def render_track(plan: dict, preview: bool = False, out_dir: Path | None = None, verbose: bool = True) -> dict:
    from .cover import envelope_from_audio, make_cover
    from .export import decode, encode_mp3, export_mp3_safe, measure, sidecar, write_json, write_tags
    from .master import master
    from .mixer import mix

    t0 = time.time()
    song = build_song(plan)
    sr = song.sr
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    log(f"[{plan['id']}] {plan['title']} — {plan['genre']} {plan['bpm']} BPM {plan['key_short']} · "
        f"{song.total_bars} bars · {len(song.layers)} layers")
    if preview:
        s, e = preview_window(song)
        pre = min(2, s)
        a, b = song.grid.bar_sample(s - pre), song.grid.bar_sample(e)
        m = mix(song, a, b, verbose=False)
        m = m[song.grid.bar_sample(s) - a:]
        y, L = master(m, song.master, sr)
        out_dir = Path(out_dir or scratch_dir())
        path = out_dir / f"{plan['file_stem']}.preview.mp3"
        encode_mp3(y, path, sr)
        dec = decode(path, sr)
        L, tp = measure(dec, sr)
        dt = time.time() - t0
        log(f"[{plan['id']}] preview bars {s}-{e} → {path}  ({L} LUFS, TP {tp} dBTP, {dt:.1f}s)")
        return {"id": plan["id"], "path": str(path), "lufs": L, "true_peak": tp, "seconds": dt, "preview": True}

    m = mix(song, 0, song.grid.total_samples(song.total_bars), verbose=verbose)
    t1 = time.time()
    y, L = master(m, song.master, sr, verbose=verbose)
    t2 = time.time()
    out_dir = Path(out_dir or (TRACKS_DIR / plan["genre_slug"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    mp3 = out_dir / f"{plan['file_stem']}.mp3"
    jpg = out_dir / f"{plan['file_stem']}.jpg"
    dec, L, tp = export_mp3_safe(y, mp3, sr, max_tp=-1.0, verbose=verbose)
    cover = make_cover(plan, envelope_from_audio(y))
    jpg.write_bytes(cover)
    write_tags(mp3, plan, cover)
    meta = sidecar(song, plan, mp3, jpg, L, tp, dec.shape[0] / sr)
    write_json(out_dir / f"{plan['file_stem']}.json", meta)
    dt = time.time() - t0
    log(f"[{plan['id']}] mix {t1 - t0:.1f}s · master {t2 - t1:.1f}s · total {dt:.1f}s → {mp3}  "
        f"({L} LUFS, TP {tp} dBTP, {meta['duration_sec']:.1f}s)")
    return {"id": plan["id"], "path": str(mp3), "lufs": L, "true_peak": tp, "seconds": round(dt, 1),
            "duration": meta["duration_sec"], "preview": False}


def _worker(args):
    plan, preview = args
    try:
        return render_track(plan, preview=preview, verbose=True)
    except Exception as e:  # report and continue with other tracks
        import traceback

        traceback.print_exc()
        return {"id": plan["id"], "error": f"{type(e).__name__}: {e}"}


def render_many(plans: list[dict], preview=False, jobs=1) -> list[dict]:
    if jobs <= 1 or len(plans) == 1:
        return [_worker((p, preview)) for p in plans]
    import multiprocessing as mp

    ctx = mp.get_context("fork")
    with ctx.Pool(jobs, maxtasksperchild=1) as pool:
        return pool.map(_worker, [(p, preview) for p in plans], chunksize=1)
