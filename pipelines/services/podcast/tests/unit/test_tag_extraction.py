from src.pipeline.utils import extract_tags_and_tickers, extract_tags_from_markdown


def test_extract_tags_from_markdown_keeps_only_vocab_tags():
    markdown = (
        "看好[台股](#tag:TWStocks)、[半導體](#tag:Semiconductor)、"
        "[資料中心](#tag:DataCenter)，但忽略[亂造](#tag:MadeUpTheme)。"
    )

    assert extract_tags_from_markdown(markdown) == [
        "datacenter",
        "semiconductor",
        "twstocks",
    ]


def test_extract_tags_normalizes_case_and_separators():
    markdown = "[供應鏈](#tag:SupplyChain) [供應鏈](#tag:supply_chain)"

    assert extract_tags_from_markdown(markdown) == ["supplychain"]


def test_extract_tags_and_tickers_filters_structured_tags_through_vocabulary():
    result = extract_tags_and_tickers({
        "summary_text": "看好[台積電](#ticker:2330)與[AI](#tag:AI)。",
        "tags": [
            {"display_name": "半導體", "tag_name": "Semiconductor"},
            {"display_name": "未收錄題材", "tag_name": "UntranslatedTheme"},
            "Inflation",
        ],
        "related_tickers": ["2330", "NVDA"],
    })

    assert result == {
        "tags": ["ai", "inflation", "semiconductor"],
        "tickers": ["2330"],
    }
