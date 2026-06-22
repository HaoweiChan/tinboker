# Curated foreign-market (non-TW/US) stock translations seeded on boot.
#
# FinMind (TW) and Massive (US) can't name these markets, and on-ingest discovery
# can only infer the market from the ticker shape (6-digit -> KR). This small,
# hand-curated set gives the well-known foreign names Taiwanese podcasts actually
# mention a correct market + zh-TW/English name + aliases *before* an episode
# surfaces them, so they don't sit as nameless KR stubs.
#
# Derived from the canonical registry at
# pipelines/libs/shared/src/shared/data/tickers.json. Seeded as "approved" so
# reclassify_markets() / the FinMind seed never touch them. Extend freely as more
# foreign tickers appear in the feed.
#
# (ticker, market, name_en, name_zh_tw, status, aliases)
FOREIGN_STOCK_TRANSLATIONS: list[tuple[str, str, str | None, str | None, str, list[str]]] = [
    # South Korea (KRX) — 6-digit numeric codes; ".KS" is the Yahoo/feed suffix form.
    ("005930", "KR", "Samsung Electronics", "三星電子", "approved", ["005930.KS"]),
    ("000660", "KR", "SK Hynix", "SK海力士", "approved", ["000660.KS"]),
]
