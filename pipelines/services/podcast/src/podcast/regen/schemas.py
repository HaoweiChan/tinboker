"""Per-step output specs + lightweight validation for the regen MCP.

Single source of truth for *what the agent must produce* at each step. The
shapes mirror the ``content_builder`` node ``postprocess`` contracts and the
``content_builder/state.py`` TypedDicts, so an agent never has to read pipeline
source to learn field names.

Each ``STEP_OUTPUT[step]`` has:
  - ``schema``  — a compact, human+machine readable field map (types + enums + notes)
  - ``example`` — a tiny *valid* example the agent can pattern-match

``validate_output`` does deliberately *lenient* structural checks: it rejects
only shapes that would break the deterministic glue (so it never rejects output a
real pipeline run would have accepted), and returns actionable error strings.
"""

from __future__ import annotations

from typing import Any

# Enum vocabularies (informational — surfaced in the schema, not hard-enforced,
# because the ticker_insights exporter tolerates/normalizes these downstream).
SENTIMENTS = ["BULLISH", "BEARISH", "NEUTRAL"]
TIME_HORIZONS = ["SHORT_TERM", "MEDIUM_TERM", "LONG_TERM"]
REASON_CATEGORIES = [
    "MACRO", "MOAT", "OPERATIONAL", "DEMAND", "SUPPLY", "VALUATION", "TECHNICAL", "FUNDAMENTAL",
]
RISK_SEVERITIES = ["LOW", "MEDIUM", "HIGH"]

# Rules that apply to every step's authored JSON.
GLOBAL_NOTES = [
    "Write all Chinese as literal UTF-8 characters — never \\uXXXX escapes.",
    # Calibration, not style advice. A capable agent writing to these prompts produces
    # markedly more than the pipeline's own model does from the same transcript —
    # measured on 股癌 EP127: 6,593 chars / 10 sections / 40 ticker links / 11 tag links
    # against the pipeline's 4,090 / 8 / 15 / 3. Episodes are read side by side on the
    # site, so an agent-written one that runs half again as long and links three times
    # as densely reads as a different publication. The bands below are the live corpus
    # (60 most recent pipeline-written 股癌 episodes), not a preference.
    "LENGTH: the assembled summary should land near 4,300 characters and stay inside "
    "3,400-4,900. That is the whole document, not per section.",
    "SHAPE: 8 sections is the norm (6-9 acceptable). Merge thin Q&A items rather than "
    "giving each its own section.",
    "LINK DENSITY: link the companies the discussion is actually about — a median "
    "episode carries about 7 distinct tickers and rarely more than 11, with roughly 9 "
    "inline #ticker: links. Passing name-drops used as analogies or examples do not "
    "need a link; linking every company that appears is the most common way an "
    "agent-written episode diverges from the corpus.",
    "TAGS: about 7-8 tags, from the curated vocabulary. More tags fragment clustering "
    "rather than improving it.",
]

STEP_OUTPUT: dict[str, dict[str, Any]] = {
    "extractor": {
        "schema": {
            "events": [
                {
                    "section_topic": "str — zh-TW topic label",
                    "start_index": "int",
                    "end_index": "int",
                    "segment_type": "sponsor|intro|outro|chitchat|analysis|guest|qa|unknown",
                    "is_substantive": "bool — for qa/guest: true if market-relevant",
                }
            ],
            "_notes": [
                "Cover EVERY sentence index 0..N-1 with no gaps; ranges may be contiguous.",
                "segment_type drives the clusterer's policy router: sponsor/intro/outro/chitchat "
                "are dropped, analysis/guest kept, qa kept only when is_substantive=true. "
                "Type segments accurately instead of dropping them; use 'unknown' only when "
                "genuinely unsure (unknown is kept as content).",
                "In a Q&A section, emit one event per question and set is_substantive per question.",
            ],
        },
        "example": {
            "events": [
                {"section_topic": "業配：保健食品", "start_index": 0, "end_index": 5,
                 "segment_type": "sponsor", "is_substantive": False},
                {"section_topic": "台積電法說會與展望", "start_index": 6, "end_index": 18,
                 "segment_type": "analysis", "is_substantive": True},
            ]
        },
    },
    "writer": {
        "schema": {
            "title": "str",
            "executive_summary": "str — 2-3 sentences",
            "sections": [
                {
                    "heading": "str — editorial headline (plain text, no ## or timestamp)",
                    "content": "str — markdown prose; embed [顯示名](#ticker:SYMBOL) and "
                    "[顯示名](#tag:Slug) links inline",
                    "start_time": "int — ms (optional)",
                    "subsections": "optional [{heading, content}]",
                }
            ],
            "conclusion": "str",
            "stock_tickers": [{"display_name": "str", "symbol": "str — e.g. 2330, NVDA"}],
            "tags": [{"display_name": "str — zh-TW", "tag_name": "str — ASCII slug, e.g. SupplyChain"}],
            "_notes": [
                "#ticker: and #tag: slugs MUST be ASCII [A-Za-z0-9_]; non-ASCII slugs are silently "
                "dropped by extraction. Put Chinese in the display text only "
                "(e.g. [供應鏈](#tag:SupplyChain), [台積電](#ticker:2330)).",
                "tag_name in the tags array must be the same canonical ASCII slug used in the #tag: links.",
                "US/HK ticker symbols must be 2-5 letters: a single-letter symbol "
                "(Visa V, Ford F, AT&T T) is rejected downstream and the link silently "
                "disappears from the rendered body. Name the company in plain text "
                "instead of leaving a dead link.",
                "Respect the LENGTH / SHAPE / LINK DENSITY / TAGS bands in global_notes — "
                "they are measured from the episodes this one will sit next to, and "
                "overshooting them is the single biggest source of drift in agent-written "
                "episodes.",
            ],
        },
        "example": {
            "title": "台積電法說會優於預期，AI 需求續強",
            "executive_summary": "台積電本季營收創高，AI 訂單能見度延伸至明年。",
            "sections": [
                {
                    "heading": "AI 需求撐起先進製程",
                    "content": "[台積電](#ticker:2330)本季在 [AI 供應鏈](#tag:AISupplyChain)需求帶動下，營收優於預期。",
                    "start_time": 0,
                }
            ],
            "conclusion": "展望樂觀，但需留意總體變數。",
            "stock_tickers": [{"display_name": "台積電", "symbol": "2330"}],
            "tags": [{"display_name": "AI 供應鏈", "tag_name": "AISupplyChain"}],
        },
    },
    "key_insights": {
        "schema": {
            "key_insights": ["str"],
            "_notes": [
                "3-8 items, most important first.",
                "Plain text only: no markdown, no [..](#..) links, no quotes/bullets. <= 80 chars each.",
            ],
        },
        "example": {"key_insights": ["台積電本季營收創高，優於市場預期", "AI 訂單能見度延伸至明年上半年"]},
    },
    "ticker_extractor": {
        "schema": {
            "ticker_recommendations": [
                {
                    "ticker": "str — e.g. 2330, NVDA",
                    "sentiment": "|".join(SENTIMENTS),
                    "sentiment_score": "float 0.0-1.0",
                    "time_horizon": "|".join(TIME_HORIZONS),
                    "bluf_thesis": "str — one-sentence bottom-line",
                    "reasons": [
                        {
                            "title": "str",
                            "description": "str",
                            "category": "|".join(REASON_CATEGORIES),
                            "start_index": "int",
                            "end_index": "int",
                            "start_time": "int — ms",
                            "end_time": "int — ms",
                        }
                    ],
                    "risks": [
                        {
                            "title": "str",
                            "description": "str",
                            "severity": "|".join(RISK_SEVERITIES),
                            "start_index": "int",
                            "end_index": "int",
                            "start_time": "int — ms",
                            "end_time": "int — ms",
                        }
                    ],
                }
            ],
            "_notes": [
                "Follow the prompt as written: it asks for ALL tickers mentioned with the "
                "insights expressed about them, and NEUTRAL exists for 'mixed or no clear "
                "direction'. Do not apply extra strictness of your own — this step feeds "
                "more than the ticker cards. A sector exposure whose constituents overlap "
                "the tickers you emit here is auto-approved; everything else is judged by "
                "an LLM verifier that rejects aggressively. Under-emitting therefore "
                "silently strips the episode's sector exposures: 股癌 EP122 was written "
                "with only 3 ticker insights and ended with ZERO sectors, against a corpus "
                "median of about 9, which keeps it off every sector and theme page.",
                "Keep the legacy wrapper key name: ticker_recommendations.",
                "Include a ticker when the host expresses an opinion OR analysis about it — "
                "NEUTRAL covers the mixed and undirectional cases. A passing name-drop with "
                "nothing said about it stays out.",
            ],
        },
        "example": {
            "ticker_recommendations": [
                {
                    "ticker": "2330",
                    "sentiment": "BULLISH",
                    "sentiment_score": 0.7,
                    "time_horizon": "LONG_TERM",
                    "bluf_thesis": "AI 需求撐起先進製程，長線看好。",
                    "reasons": [
                        {
                            "title": "AI 訂單能見度高",
                            "description": "主持人指出 AI 訂單延伸至明年。",
                            "category": "DEMAND",
                            "start_index": 0,
                            "end_index": 5,
                            "start_time": 0,
                            "end_time": 5000,
                        }
                    ],
                    "risks": [
                        {
                            "title": "總體需求轉弱",
                            "description": "若景氣下行，先進製程拉貨可能放緩。",
                            "severity": "MEDIUM",
                            "start_index": 6,
                            "end_index": 8,
                            "start_time": 6000,
                            "end_time": 8000,
                        }
                    ],
                }
            ]
        },
    },
    "marp_writer": {
        "schema": {
            "title": "str",
            "slides": [
                {
                    "heading": "str",
                    "bullet_points": ["str"],
                    "start_time": "int — ms",
                    "slide_notes": "str",
                }
            ],
        },
        "example": {
            "title": "台積電法說會重點",
            "slides": [
                {
                    "heading": "AI 需求續強",
                    "bullet_points": ["營收創高", "毛利率提升"],
                    "start_time": 0,
                    "slide_notes": "本季亮點。",
                }
            ],
        },
    },
}
# The ticker deck is built deterministically from the ticker step — this step is a
# trigger, so its submitted output is ignored (any shape, including {}, is accepted).
STEP_OUTPUT["ticker_marp_writer"] = {
    "schema": {"type": "object", "description": "ignored — submit {} to rebuild the ticker deck"},
    "example": {},
}


def _is_list_of_objects(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(i, dict) for i in v)


def validate_output(step: str, output: Any) -> list[str]:
    """Lenient structural validation. Returns a list of actionable error strings.

    Mirrors each node's ``postprocess`` tolerance (e.g. extractor accepts a bare
    list; key_insights accepts the ``insights`` alias) so it never rejects output
    a real pipeline run would have accepted.
    """
    errors: list[str] = []

    if step == "extractor":
        events = output if isinstance(output, list) else (output or {}).get("events")
        if not _is_list_of_objects(events):
            errors.append('extractor: expected {"events": [{section_topic, start_index, end_index}, ...]}.')
        else:
            for i, ev in enumerate(events):
                missing = [k for k in ("section_topic", "start_index", "end_index") if k not in ev]
                if missing:
                    errors.append(f"extractor: events[{i}] missing {missing}.")
                    break

    elif step == "writer":
        if not isinstance(output, dict):
            errors.append("writer: expected an object with title/sections/...")
        else:
            sections = output.get("sections")
            if not _is_list_of_objects(sections) or not sections:
                errors.append('writer: "sections" must be a non-empty array of {heading, content} objects.')
            else:
                for i, s in enumerate(sections):
                    if "content" not in s:
                        errors.append(f'writer: sections[{i}] missing "content".')
                        break

    elif step == "key_insights":
        if not isinstance(output, dict):
            errors.append('key_insights: expected {"key_insights": ["...", ...]}.')
        else:
            items = output.get("key_insights")
            if items is None:
                items = output.get("insights")
            if not isinstance(items, list):
                errors.append('key_insights: "key_insights" must be an array of plain-text strings.')

    elif step == "ticker_extractor":
        # Accept BOTH wrapper keys, matching the node postprocess and the
        # exporter (exporters/ticker_insights.py) — ticker_extractor.yaml asks the
        # model for "ticker_insights", so rejecting it here broke regen runs.
        recs = None
        if isinstance(output, dict):
            recs = output.get("ticker_insights")
            if not isinstance(recs, list):
                recs = output.get("ticker_recommendations")
        if not isinstance(recs, list):
            errors.append('ticker_extractor: expected {"ticker_insights": [...]} (or legacy "ticker_recommendations").')
        else:
            for i, r in enumerate(recs):
                if not isinstance(r, dict) or "ticker" not in r:
                    errors.append(f'ticker_extractor: ticker_insights[{i}] missing "ticker".')
                    break

    elif step == "marp_writer":
        if not isinstance(output, dict) or not _is_list_of_objects(output.get("slides")):
            errors.append(f'{step}: expected {{title, slides: [{{heading, bullet_points, ...}}]}}.')
    # ticker_marp_writer output is ignored (deck built deterministically) — accept anything.

    return errors
