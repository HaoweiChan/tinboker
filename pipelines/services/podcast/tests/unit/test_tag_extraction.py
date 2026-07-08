from src.pipeline.utils import extract_tags_and_tickers, extract_tags_from_markdown


def test_extract_tags_from_markdown_keeps_only_vocab_tags():
    markdown = (
        "看好[台股](#tag:TWStocks)、[供應鏈](#tag:SupplyChain)、"
        "[通膨](#tag:Inflation)，但忽略[亂造](#tag:MadeUpTheme)。"
    )

    assert extract_tags_from_markdown(markdown) == [
        "inflation",
        "supplychain",
        "twstocks",
    ]


def test_extract_tags_normalizes_case_and_separators():
    markdown = "[供應鏈](#tag:SupplyChain) [供應鏈](#tag:supply_chain)"

    assert extract_tags_from_markdown(markdown) == ["supplychain"]


def test_extract_tags_and_tickers_filters_structured_tags_through_vocabulary():
    result = extract_tags_and_tickers({
        "summary_text": "看好[台積電](#ticker:2330)與[供應鏈](#tag:SupplyChain)。",
        "tags": [
            {"display_name": "供應鏈", "tag_name": "SupplyChain"},
            {"display_name": "未收錄題材", "tag_name": "UntranslatedTheme"},
            "Inflation",
        ],
        "related_tickers": ["2330", "NVDA"],
    })

    assert result == {
        "tags": ["inflation", "supplychain"],
        "tickers": ["2330"],
    }
