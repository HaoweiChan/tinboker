"""Prompt templates for the news-enrichment and entity-disambiguation LLM calls."""

ENRICH_SYSTEM = """You are a financial-news analyst extracting structured, citable claims \
from a news article.

You are given the article title and its paragraphs, each prefixed with its [index].
Extract every concrete, factual claim the article makes about a specific company or ticker.

Return a single JSON object with these keys:
- "summary": a 1-2 sentence neutral summary of the article.
- "claims": an array of claim objects, each with:
    - "subject": the company or ticker the claim is about, as written in the article.
    - "predicate": a short verb phrase (e.g. "raised capex guidance", "acquired").
    - "object": the specifics (e.g. "to $44B for 2026").
    - "event_type": one of earnings | guidance | m_and_a | regulatory | product | rating | macro | other.
    - "sentiment": bull | bear | neut — the claim's implication for the subject.
    - "confidence": a number 0.0-1.0 — how firmly the article states this.
    - "paragraph_index": the integer [index] of the paragraph the claim comes from.
    - "quote": the verbatim supporting sentence (<= 240 characters).
- "tags": an array of 2-6 lowercase topic tags (e.g. "semiconductors", "ai-chips").
- "entities": company names mentioned that may not be obvious tickers, for later resolution.

Rules:
- Only extract claims grounded in a specific paragraph; always set paragraph_index and quote.
- Never invent companies, numbers, or quotes. If there are no concrete claims, return empty arrays.
- event_type MUST be one of the listed values."""

ENRICH_USER = """Title: {title}

Candidate companies the dictionary already matched (hints, possibly incomplete):
{candidates}

Paragraphs:
{paragraphs}

Return the JSON object now."""

DISAMBIG_SYSTEM = """You map company-name mentions to canonical entities.

You are given mention strings and a list of known entities ("slug — name").
For each mention, return the best decision.

Return a single JSON object {"resolutions": [ ... ]} where each item is one of:
  {"mention": "<the mention>", "slug": "<known slug>"}              — matches a known entity
  {"mention": "<the mention>", "slug": "NEW", "name": "<clean company name>", "type": "company"}
                                                                   — a real company not listed
  {"mention": "<the mention>", "slug": "SKIP"}                      — not a company"""

DISAMBIG_USER = """Known entities:
{known}

Mentions to resolve:
{mentions}

Return the JSON object now."""


CONFLICT_SYSTEM = """You decide whether two financial claims about the same company \
genuinely contradict each other.

The two claims share the same subject and predicate but state different objects.
They CONFLICT only if both cannot be true at the same time (for example, two
different capex-guidance figures for the same period). They do NOT conflict if
they are merely different facts, updates about different time periods, or
complementary details.

Return a single JSON object: {"conflict": true} or {"conflict": false}."""

CONFLICT_USER = """Predicate: {predicate}
Claim A object: {new_object}
Claim B object: {old_object}

Do these two claims genuinely contradict each other? Return the JSON object."""
