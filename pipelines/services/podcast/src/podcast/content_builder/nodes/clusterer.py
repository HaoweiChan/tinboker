"""Sentence clustering node: filters financial events and attaches sentence data."""

from typing import Any

from ..state import PipelineState

_FINANCIAL_KEYWORDS = [
    "台積電", "TSMC", "股價", "股票", "投資", "市場", "財經", "營收", "獲利",
    "半導體", "AI", "記憶體", "散熱", "供應鏈", "多頭", "空頭", "買進", "賣出",
    "財報", "季報", "年報", "EPS", "本益比", "殖利率", "股息", "股利",
    "指數", "大盤", "個股", "ETF", "基金", "債券", "匯率", "利率",
    "經濟", "GDP", "通膨", "通縮", "央行", "聯準會", "FED",
    "科技股", "金融股", "傳產", "電子", "傳產股", "金融",
    "策略", "分析", "預測", "展望", "趨勢", "行情",
]


def cluster_sentences(state: PipelineState) -> dict[str, Any]:
    """Filter financial events and attach sentence data with timestamps."""
    events = state.get("events", [])
    sentences_list = state.get("sentences", [])

    clustered_events = []
    for event in events:
        start_index = event.get("start_index", 0)
        end_index = event.get("end_index", 0)
        section_topic = event.get("section_topic", "")

        is_financial = any(kw in section_topic for kw in _FINANCIAL_KEYWORDS)
        if not is_financial:
            continue

        event_sentences = []
        start_time = None
        end_time = None

        for i in range(start_index, end_index + 1):
            if i < len(sentences_list):
                sentence = sentences_list[i]
                event_sentences.append(sentence)
                if start_time is None and "start" in sentence:
                    start_time = sentence.get("start")
                if "end" in sentence:
                    end_time = sentence.get("end")

        if event_sentences and start_time is not None and end_time is not None:
            clustered_events.append({
                "section_topic": section_topic,
                "sentences": event_sentences,
                "start": start_time,
                "end": end_time,
            })

    return {"clustered_events": clustered_events}
