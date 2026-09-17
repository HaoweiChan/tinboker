"""The macro indicators the pipeline may emit — ids only, one line each.

OWNER: the backend. ``backend/src/services/macro_data.py::SERIES`` decides which
indicators have a data series (and therefore a card at ``/api/og/macro/{id}.png``); this
file is the pipeline's copy because ``pipelines/`` cannot import ``backend/``. A backend
unit test (``test_macro_vocab_in_sync``) fails when the two key sets differ, so add an
indicator THERE first, then here. An id outside this list is dropped by the extractor:
a claim nobody can draw or look up is noise in ``content_mentions``.
"""

MACRO_SERIES: dict[str, str] = {
    "US10Y": "美債10年期殖利率",
    "US2Y": "美債2年期殖利率",
    "US30Y": "美債30年期殖利率",
    "US_REAL10Y": "美國10年期實質利率",
    "FED_FUNDS": "聯邦基金利率（含升降息機率、點陣圖）",
    "WTI": "WTI原油",
    "BRENT": "布蘭特原油",
    "DIESEL_US": "美國柴油零售價",
    "GASOLINE_US": "美國汽油零售價",
    "DXY": "美元指數",
    "USDJPY": "美元兌日圓",
    "USDTWD": "美元兌台幣",
    "VIX": "VIX恐慌指數",
    "US_CPI": "美國CPI／通膨",
    "US_UNEMP": "美國失業率",
}
