"""Sentence clustering node: selects topic events and attaches sentence data."""

from typing import Any

from ..state import PipelineState

# Topics whose label contains one of these reads as on-platform financial content.
# Used to PREFER financial topics, never to hard-drop everything (see below).
_FINANCIAL_KEYWORDS = [
    "台積電", "TSMC", "股價", "股票", "投資", "市場", "財經", "營收", "獲利",
    "半導體", "AI", "記憶體", "散熱", "供應鏈", "多頭", "空頭", "買進", "賣出",
    "財報", "季報", "年報", "EPS", "本益比", "殖利率", "股息", "股利",
    "指數", "大盤", "個股", "ETF", "基金", "債券", "匯率", "利率",
    "經濟", "GDP", "通膨", "通縮", "央行", "聯準會", "FED",
    "科技股", "金融股", "傳產", "電子", "傳產股", "金融",
    "策略", "分析", "預測", "展望", "趨勢", "行情",
]

# Sponsor reads, station IDs, and opening chatter — never useful as chapters. Dropped
# from the fallback (all-topics) path so a non-keyword episode doesn't surface an ad
# as its first chapter.
_NON_CONTENT_KEYWORDS = ["廣告", "業配", "贊助", "片頭", "開場", "節目開場", "開頭問候"]


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


def cluster_sentences(state: PipelineState) -> dict[str, Any]:
    """Select topic events and attach real timestamps.

    The financial-keyword match is a PREFERENCE, not a hard gate: substring-matching
    free-form zh-TW topic labels has false negatives, and a financial episode whose
    labels just happen to miss a keyword would otherwise lose every chapter (the bug
    where summaries came back with no #time markers). So: keep the financial topics
    when any are detected; otherwise fall back to ALL topics (minus sponsor/opening
    segments) so every episode with a transcript still gets real topic chapters.
    """
    events = state.get("events", [])
    sentences_list = state.get("sentences", [])

    financial, others = [], []
    for event in events:
        topic = event.get("section_topic", "")
        built = _build_clustered(event, sentences_list)
        if built is None:
            continue
        if any(kw in topic for kw in _NON_CONTENT_KEYWORDS):
            continue  # ads / intros are never chapters
        (financial if any(kw in topic for kw in _FINANCIAL_KEYWORDS) else others).append(built)

    clustered_events = financial if financial else others
    return {"clustered_events": clustered_events}
