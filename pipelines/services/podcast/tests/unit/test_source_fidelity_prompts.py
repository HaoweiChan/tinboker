"""Prompt regressions for claims that must stay attached to source evidence."""

from src.podcast.content_builder.nodes import (
    extractor,
    key_insights_extractor,
    marp_writer,
    ticker_extractor,
    writer,
)

_NUMERIC_CONFLICT = (
    "每月投入1萬元、連續十年，並提到年化10%；同段又出現207萬元與634萬元，"
    "但口述沒有說清楚每個結果對應哪個條件。00991A完整持有75.2%，"
    "錯過最佳五天後另提2.34%，同時說少了51.4個百分點。"
)
_AMBIGUOUS_NAMES = "逐字稿中的公司名稱疑似ASR近音，未能確認，不可推定為宏碁或合晶。"



def _flat(text: str) -> str:
    """YAML block prompts wrap sentences across lines; compare on single spaces."""
    return " ".join(text.split())


def test_writer_and_slides_keep_numeric_scenarios_separate_and_unreconciled():
    events = [{"event_id": "E1", "text": _NUMERIC_CONFLICT}]
    writer_system = _flat(writer.build_messages({"chapter_events": events})[0]["content"])
    slides_system = _flat(marp_writer.build_messages({"clustered_events": events})[0]["content"])

    for system in (writer_system, slides_system):
        assert "Keep every number attached to its exact source, period, unit, and scenario" in system
        assert "Do not combine separate examples or calculate a missing result" in system
    assert "state that the source is unclear or inconsistent" in writer_system
    assert "hypothetical calculation" in writer_system
    assert "State when figures are unclear or contradictory" in slides_system


def test_extractor_preserves_ambiguous_names_without_guessing_ticker_identity():
    prompt = _flat(extractor.build_messages({
        "source": "Show",
        "episode_title": "Episode",
        "sentences": [{"index": 0, "text": _NUMERIC_CONFLICT + _AMBIGUOUS_NAMES}],
    })[0]["content"])

    assert "Keep each numerical claim tied to its own conditions and time period" in prompt
    assert "Do not calculate or reconcile figures the speaker leaves unclear or contradictory" in prompt
    assert "Never infer a company name or ticker from an uncertain sound-alike" in prompt


def test_key_insights_do_not_strengthen_uncertain_summary_claims():
    messages = key_insights_extractor.build_messages({
        "markdown_report": _NUMERIC_CONFLICT + _AMBIGUOUS_NAMES,
        "source": "Show",
        "episode_title": "Episode",
    })
    system = _flat(messages[0]["content"])

    assert "Do not combine numbers from separate examples or infer missing assumptions" in system
    assert "Do not turn a hypothetical calculation into actual fund performance" in system
    assert "Keep uncertainty and contradictions visible" in system


def test_ticker_extractor_does_not_map_ambiguous_names_or_merge_numeric_claims():
    prompt = _flat(ticker_extractor.build_messages({
        "source": "Show",
        "episode_title": "Episode",
        "clustered_events": [{"event_id": "E1", "text": _NUMERIC_CONFLICT + _AMBIGUOUS_NAMES}],
    })[0]["content"])

    assert "Only map a ticker when the source clearly identifies the listed company" in prompt
    assert "Do not guess a ticker from an ASR sound-alike" in prompt
    assert "Never derive a return by subtracting or combining figures" in prompt
