"""Sentence clustering node: routes typed events to chapters and attaches timing.

Each extractor event carries a ``segment_type`` (sponsor/intro/outro/chitchat/
analysis/guest/qa/unknown) and an ``is_substantive`` flag. This node is a pure-code
POLICY ROUTER: for each event it looks up the action for its ``segment_type`` in the
resolved show policy (``state["show_profile"]["policy"]``) and keeps / drops /
keeps-if-substantive accordingly, then attaches the real sentence-level start/end ms.

This replaces the previous brittle approach (substring-matching free-form zh-TW topic
labels against hardcoded finance/ad keyword lists), which let conversational sponsor
reads slip through as "financial content".
"""

from typing import Any

from ..profiles import load_profile
from ..state import PipelineState

# Action constants for a policy entry (segment_type -> action).
_KEEP = "keep"
_DROP = "drop"
_SUBSTANTIVE_ONLY = "substantive_only"

# Types that must never become a chapter even in the empty-result safety net below —
# surfacing an ad/intro as a chapter is the exact bug we are preventing.
_FALLBACK_DROP_TYPES = {"sponsor", "intro", "outro"}


def _build_clustered(event: dict, sentences_list: list) -> dict | None:
    """Attach the real sentence-level start/end (ms) for one extractor event."""
    start_index = event.get("start_index", 0)
    end_index = event.get("end_index", 0)
    section_topic = event.get("section_topic", "")

    event_sentences = []
    start_time = end_time = None
    for i in range(start_index, end_index + 1):
        if i < len(sentences_list):
            sentence = sentences_list[i]
            event_sentences.append(sentence)
            if start_time is None and "start" in sentence:
                start_time = sentence.get("start")
            if "end" in sentence:
                end_time = sentence.get("end")

    if event_sentences and start_time is not None and end_time is not None:
        return {"section_topic": section_topic, "sentences": event_sentences,
                "start": start_time, "end": end_time}
    return None


def _policy(state: PipelineState) -> dict[str, str]:
    """The resolved segment policy, always complete.

    ``load_profile`` already returns a fully-merged policy, but we merge over the
    default again so a hand-built or partial ``show_profile.policy`` can't leave a
    known segment_type unspecified (which would silently fall through to keep).
    """
    default = load_profile(None)["policy"]
    policy = (state.get("show_profile") or {}).get("policy") or {}
    return {**default, **policy}


def _keeps(event: dict, policy: dict[str, str]) -> bool:
    """Whether the policy keeps this event. Unknown types/actions default to keep."""
    seg = event.get("segment_type") or "unknown"
    action = policy.get(seg, _KEEP)
    if action == _DROP:
        return False
    if action == _SUBSTANTIVE_ONLY:
        return bool(event.get("is_substantive"))
    return True  # _KEEP or any unrecognized action -> keep (never silently drop content)


def cluster_sentences(state: PipelineState) -> dict[str, Any]:
    """Route typed topic events to chapters via the show policy and attach timestamps.

    Safety net: if the policy keeps nothing but events exist (e.g. the extractor
    mis-typed everything, or an episode is genuinely all chitchat), fall back to
    keeping every timed event EXCEPT ads/intros/outros — so an episode with a
    transcript always gets real topic chapters, but never surfaces an ad as one.
    """
    events = state.get("events", [])
    sentences_list = state.get("sentences", [])
    policy = _policy(state)

    kept: list[dict] = []
    for event in events:
        if not _keeps(event, policy):
            continue
        built = _build_clustered(event, sentences_list)
        if built is not None:
            kept.append(built)

    if not kept:
        for event in events:
            if (event.get("segment_type") or "unknown") in _FALLBACK_DROP_TYPES:
                continue
            built = _build_clustered(event, sentences_list)
            if built is not None:
                kept.append(built)

    return {"clustered_events": kept}
