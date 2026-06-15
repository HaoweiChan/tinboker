"""Per-show structure profiles.

A *profile* tunes the generic segment-typing pipeline for one podcast WITHOUT
adding any code branches: it carries a free-text ``structure_hint`` (injected into
the extractor prompt as a prior on the show's typical layout) and an optional
``policy`` override map (``segment_type -> action``) consumed by the clusterer's
policy router.

Profiles are static repo data (``show_profiles.json``), loaded once and cached —
no network or DB read (respects the Firestore read freeze). A show with no entry
falls back to ``default``; a show entry's ``policy`` is merged *over* the default
policy key-by-key, so a profile only has to list the keys it changes.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_PROFILES_PATH = Path(__file__).parent / "show_profiles.json"


@lru_cache(maxsize=1)
def _all_profiles() -> dict[str, Any]:
    with _PROFILES_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_profile(source: str | None) -> dict[str, Any]:
    """Return the resolved profile for ``source`` (a podcast name).

    The result always has a ``structure_hint`` (str) and a complete ``policy``
    (the default policy with the show's overrides applied), so callers never have
    to handle a missing show or a partial policy.
    """
    profiles = _all_profiles()
    default = profiles.get("default", {})
    default_policy = dict(default.get("policy", {}))

    show = profiles.get(source or "", {})
    policy = {**default_policy, **(show.get("policy") or {})}

    return {
        "structure_hint": show.get("structure_hint") or default.get("structure_hint") or "",
        "policy": policy,
    }
