"""Deterministically derive sector/theme exposures from clustered events."""

from __future__ import annotations

from typing import Any

from shared.sectors import resolve_clustered_events

from ..state import PipelineState


def derive_sector_exposures(state: PipelineState) -> dict[str, Any]:
    """Return resolved sector/theme exposure metadata and flat index arrays."""
    return resolve_clustered_events(state.get("clustered_events", []))
