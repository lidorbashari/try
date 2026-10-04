"""Genre recipe registry.

A recipe is a function ``build(plan: dict, rng: np.random.Generator) -> Song`` registered under
the plan's ``genre_slug``::

    from djlab.genres import register

    @register("tech_house")
    def build(plan, rng):
        song = Song(plan, rng)
        ...
        return song

Recipe modules live next to this file as ``<genre_slug>.py`` and are imported lazily by
:func:`get_recipe`. See ``README.md`` in this folder for the cookbook.
"""
from __future__ import annotations

import importlib
from typing import Callable

_REGISTRY: dict[str, Callable] = {}


class UnknownGenre(KeyError):
    pass


def register(slug: str):
    """Decorator registering a recipe for ``slug`` (must equal the plan's ``genre_slug``)."""
    def deco(fn):
        _REGISTRY[slug] = fn
        fn.genre_slug = slug
        return fn
    return deco


def get_recipe(slug: str) -> Callable:
    if slug not in _REGISTRY:
        try:
            importlib.import_module(f"{__name__}.{slug}")
        except ModuleNotFoundError as e:
            if e.name and e.name.endswith(slug):
                raise UnknownGenre(
                    f"No recipe for genre_slug {slug!r}: create engine/djlab/genres/{slug}.py with "
                    f"@register({slug!r}). Available: {sorted(available())}") from None
            raise
    if slug not in _REGISTRY:
        raise UnknownGenre(f"engine/djlab/genres/{slug}.py exists but does not @register({slug!r})")
    return _REGISTRY[slug]


def available() -> list[str]:
    from pathlib import Path

    here = Path(__file__).parent
    return sorted(p.stem for p in here.glob("*.py") if not p.stem.startswith("_"))
