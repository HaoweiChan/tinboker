"""Discrete news-pipeline steps, one module per stage.

1. ``fetch_feeds``  — feedparser → candidate articles
2. ``dedup``        — deterministic slug + content-hash skip
3. ``extract``      — trafilatura full-text → paragraphs, RSS fallback
4. ``dict_prepass`` — alias-index dictionary match (cheap, pre-LLM)
5. ``llm_enrich``   — one OpenRouter call → typed claims + tags + mentions
6. ``resolve``      — mentions → canonical entity slugs (L1 exact, L3 LLM)
7. ``wiki_write``   — ingest_news_article() into the shared wiki
"""
