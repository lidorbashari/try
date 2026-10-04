"""DJ Lab synthesis & production engine.

Everything here renders original audio from scratch (no samples): drums, synths, effects,
arrangement, mixing, mastering, MP3/ID3 export, cover art and objective audio analysis.

Quick start (from the ``engine/`` directory)::

    python -m djlab list
    python -m djlab render --id house-05 --preview
    python -m djlab render --id house-05
    python -m djlab analyze ../music/tracks/tech_house/house-05-groove-machine.mp3
"""
from __future__ import annotations

import os
from pathlib import Path

SR = 44100
ENGINE_VERSION = "1.0.0"
ARTIST = "DJ Lab Originals"

PKG_DIR = Path(__file__).resolve().parent
ENGINE_DIR = PKG_DIR.parent
REPO_ROOT = ENGINE_DIR.parent
PLAN_PATH = REPO_ROOT / "music" / "tracklist.plan.json"
TRACKS_DIR = REPO_ROOT / "music" / "tracks"


def scratch_dir() -> Path:
    """Directory for temporary renders (never inside the repo)."""
    import tempfile

    d = Path(os.environ.get("DJLAB_SCRATCH") or (Path(tempfile.gettempdir()) / "djlab"))
    d.mkdir(parents=True, exist_ok=True)
    return d


__all__ = ["SR", "ENGINE_VERSION", "ARTIST", "REPO_ROOT", "PLAN_PATH", "TRACKS_DIR", "scratch_dir"]
