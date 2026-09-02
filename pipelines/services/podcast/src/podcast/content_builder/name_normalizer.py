"""One proper-noun correction pass over an episode's finished artifacts.

Why this exists, and why here rather than in a prompt: the ASR mishears names
(``欣興``→``新興``, ``績優生``→``機油生``, ``Warsh``→``Walsh``) and every downstream node
inherits whatever it was handed. Only ``writer.yaml`` carries a homophone-correction
rule, and only for "financial/tech terms", so the summary quietly fixes a name while
the slides, the cards and the Threads copy — which read the *other* branch of the
graph — publish the mistranscription. The same episode then ships both spellings.

So the pass runs once, at the join, and produces a **replacement map** that is applied
to every artifact. That is the part that matters: one map, applied everywhere, means an
episode can no longer disagree with itself.

The model only proposes; :func:`vet_corrections` decides. A proposal survives only if it
is an equal-length substitution of a string that actually occurs — which is the shape of
a homophone error and is not the shape of a rewrite, a deletion, or an opinion.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from .llm import invoke_json, load_prompt

# A cosmetic pass must never rewrite the episode. Beyond ~12 substitutions the model
# has stopped correcting names and started editing prose, so the whole map is suspect.
MAX_CORRECTIONS = 12

# Enough of the episode to spot the recurring names without paying for the whole corpus;
# the map is applied to everything regardless of what it was proposed from.
_SAMPLE_CHARS = 12000

# Values that are identifiers, not prose: substituting inside them breaks links.
_OPAQUE_KEY = re.compile(r"(?:^|_)(?:url|id|ids|slug|href|src|class|kind|path|ticker|symbol|code)$")

# A correction must be homogeneous — all-CJK or all-Latin. Mixed or punctuated strings
# ("台積電 (TSMC)", "#tag:X") are anchors and markup, never a mistranscribed name.
_ALL_CJK = re.compile(r"^[㐀-鿿]+$")
_ALL_LATIN = re.compile(r"^[A-Za-z]+$")


def collect_entities(
    *, episode_title: str, source: str, ticker_names: Iterable[str]
) -> list[str]:
    """The names we know are spelled right, for the model to anchor on.

    The episode title is the strongest signal available and costs nothing: it comes
    from the show's own RSS/Spotify metadata, so it is human-written. The 8/31 財女珍妮
    episode was titled 「鷹派Warsh」 while its Threads post said "Walsh" — the correct
    spelling was in hand the whole time and nothing consulted it.
    """
    seen: list[str] = []
    for raw in [source, episode_title, *ticker_names]:
        name = (raw or "").strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def vet_corrections(raw: Any, corpus: str) -> dict[str, str]:
    """Keep only the proposals that look like a homophone fix, as a wrong→right map."""
    out: dict[str, str] = {}
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        wrong = str(item.get("wrong") or "").strip()
        right = str(item.get("right") or "").strip()
        if not wrong or not right or wrong == right:
            continue
        if len(wrong) != len(right):
            continue  # a same-sound swap is same-length; anything else is a rewrite
        if not ((_ALL_CJK.match(wrong) and _ALL_CJK.match(right))
                or (_ALL_LATIN.match(wrong) and _ALL_LATIN.match(right))):
            continue
        if wrong not in corpus:
            continue  # the model invented a string this episode never contained
        out[wrong] = right
        if len(out) >= MAX_CORRECTIONS:
            break
    return out


def apply_corrections(value: Any, mapping: dict[str, str]) -> Any:
    """Rewrite every prose string in a nested structure; leave identifiers alone."""
    if not mapping:
        return value
    if isinstance(value, str):
        for wrong, right in mapping.items():
            value = value.replace(wrong, right)
        return value
    if isinstance(value, list):
        return [apply_corrections(v, mapping) for v in value]
    if isinstance(value, dict):
        return {
            k: v if isinstance(k, str) and _OPAQUE_KEY.search(k) else apply_corrections(v, mapping)
            for k, v in value.items()
        }
    return value


def propose_corrections(
    sample: str, entities: list[str], *, source: str, episode_title: str
) -> dict[str, str]:
    """Ask the model for a wrong→right map over ``sample``. Never raises."""
    if not sample.strip():
        return {}
    prompts = load_prompt("name_normalizer")
    messages = [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": prompts["user"].format(
            source=source,
            episode_title=episode_title,
            entities="\n".join(f"- {e}" for e in entities) or "（無）",
            sample=sample[:_SAMPLE_CHARS],
        )},
    ]
    try:
        result = invoke_json("name_normalizer", messages)
    except Exception as exc:  # noqa: BLE001 — a proofreading pass must not fail a run
        print(f"  ⚠ name normalization skipped: {exc}")
        return {}
    return vet_corrections(result.get("corrections"), sample[:_SAMPLE_CHARS])


# The artifacts a reader actually sees. ``sentences_markdown`` is deliberately absent:
# the transcript is the record of what the ASR heard, and rewriting it would hide the
# defect from anyone debugging the next one.
_TARGETS = (
    "markdown_report",
    "events_markdown",
    "marp_markdown",
    "ticker_marp_markdown",
    "key_insights",
    "social_cards",
    "social_thread",
    "ticker_insights",
)

# What the model reads to find the names — the short, name-dense artifacts.
_SAMPLE_FROM = ("key_insights", "social_cards", "social_thread", "events_markdown")


def normalize_names(
    outputs: dict[str, Any], *, source: str, episode_title: str, ticker_names: Iterable[str]
) -> dict[str, Any]:
    """Apply one proper-noun correction map across every published artifact.

    Returns ``outputs`` with the text fields corrected. Best-effort throughout: with no
    model configured, or nothing worth fixing, the outputs come back untouched.
    """
    sample = "\n\n".join(
        str(outputs.get(k) or "") if isinstance(outputs.get(k), str) else repr(outputs.get(k))
        for k in _SAMPLE_FROM
    )
    entities = collect_entities(
        episode_title=episode_title, source=source, ticker_names=ticker_names
    )
    mapping = propose_corrections(
        sample, entities, source=source, episode_title=episode_title
    )
    if not mapping:
        return outputs
    print("  ✎ name fixes: " + ", ".join(f"{w}→{r}" for w, r in mapping.items()))
    for key in _TARGETS:
        if key in outputs:
            outputs[key] = apply_corrections(outputs[key], mapping)
    return outputs
