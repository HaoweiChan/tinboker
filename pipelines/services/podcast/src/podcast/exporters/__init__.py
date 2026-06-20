"""Outbound exporters: write structured pipeline output into stable contracts.

Currently:
    * :mod:`ticker_insights` writes the per-(episode, ticker) Firestore
      ``ticker_insights/{episode_id}/tickers/{ticker}`` documents that satisfy
      the platform-side contract in ``docs/firestore-contract.md``.
    * :mod:`trending_tickers` recomputes the ``trending_tickers/{ticker}``
      aggregate consumed by the Stock Index page.
"""
