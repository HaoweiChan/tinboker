"""Pull a metric out of an undocumented API's object without betting on one field name.

vocus and Substack both expose read counts only through the endpoints their own
dashboards call, and neither documents the field that holds the number. A single
guessed key fails the way these platforms always fail: a 200, a plausible-looking
payload, and a zero that reads as "nobody opened it" rather than "we looked in the
wrong place". A read counter that silently reports zero is worse than no counter —
it invites the conclusion that the syndication isn't working.

So a metric is resolved against a *ranked* list of candidate keys, and the resolution
is reported alongside the number: ``field_map`` says which key each value came from,
and when nothing matched, ``sample_keys`` says what the object actually carried.
Confirming (or correcting) the mapping against the live API is then one page-load
instead of a debugging session.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

# Bounded so a malformed payload can't push a huge blob into the admin response.
MAX_SAMPLE_KEYS = 40


def dig(obj: Any, path: str) -> Any:
    """Follow a dotted path (``"stats.views"``), returning None at the first miss."""
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def as_int(value: Any) -> Optional[int]:
    """Coerce an API value to int, or None. Strings count — these APIs mix both."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip().replace(",", "")))
        except (TypeError, ValueError):
            return None
    return None


def pick_int(obj: Any, keys: Sequence[str]) -> tuple[Optional[int], Optional[str]]:
    """First candidate key that holds a number → ``(value, key)``; ``(None, None)`` if none do.

    Order is the ranking: put the field observed in a real response first and the
    plausible synonyms after it.
    """
    if not isinstance(obj, dict):
        return None, None
    for key in keys:
        found = as_int(dig(obj, key) if "." in key else obj.get(key))
        if found is not None:
            return found, key
    return None, None


def sum_int(items: Iterable[Any], keys: Sequence[str]) -> tuple[int, Optional[str], int]:
    """Total one metric across objects → ``(total, key_used, items_that_had_it)``.

    ``matched`` is what separates "every article really has 0 reads" from "the field
    isn't there": a zero total with zero matches means the mapping is wrong, and the
    caller reports that instead of a number.
    """
    total, key_used, matched = 0, None, 0
    for item in items:
        value, key = pick_int(item, keys)
        if value is None:
            continue
        total += value
        matched += 1
        key_used = key_used or key
    return total, key_used, matched


def sample_keys(items: Sequence[Any], limit: int = MAX_SAMPLE_KEYS) -> list[str]:
    """The field names the first object actually carried — the fix for a wrong mapping.

    Only ever called on our own account's data, and returns key names, never values.
    """
    for item in items:
        if isinstance(item, dict):
            return sorted(item.keys())[:limit]
    return []
