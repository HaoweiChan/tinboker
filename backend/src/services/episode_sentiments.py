"""Per-(episode, ticker) sentiment for episode-card chips.

Sentiment lives inside each episode's ticker_recommendations JSON
(`ticker_recommendations[].sentiment` = BULLISH/BEARISH/NEUTRAL). That payload is
large (~64KB) and only reachable via a GCS/HTTP URL — it is NOT in the episode list
response. We extract a tiny `{TICKER: SENTIMENT}` map per episode and cache it
long-term in Redis (recommendations are immutable once published), so the cards can
show a sentiment chip without ever fetching the heavy file on the request path.
"""

import asyncio
import json
import logging
from typing import Optional

from src.cache.redis_client import cache_get, cache_set
from src.services.gcs_content import GCSContentService

logger = logging.getLogger(__name__)

_SENTIMENT_TTL = 7 * 24 * 3600  # 7 days — recommendations don't change once published
_EMPTY_TTL = 600  # 10 min — an empty result may be a transient miss (GCS hiccup, data
                  # not yet written); cache it briefly so it self-heals instead of
                  # sticking empty for a week.
_MAX_IDS = 80
_FETCH_CONCURRENCY = 8


def _normalize(raw) -> Optional[str]:
    """Map a raw sentiment string to the canonical BULLISH/BEARISH/NEUTRAL, or None."""
    if not isinstance(raw, str):
        return None
    s = raw.strip().upper()
    if s in ("BULLISH", "BULL", "POSITIVE", "STRONG_BULLISH"):
        return "BULLISH"
    if s in ("BEARISH", "BEAR", "NEGATIVE", "STRONG_BEARISH"):
        return "BEARISH"
    if s in ("NEUTRAL", "NEUT", "MIXED"):
        return "NEUTRAL"
    return None


def _parse(content: str) -> dict:
    """Extract {TICKER: SENTIMENT} from a ticker_recommendations JSON string."""
    try:
        data = json.loads(content)
    except Exception:
        return {}
    out: dict = {}
    for rec in (data.get("ticker_recommendations") or []):
        ticker = str(rec.get("ticker", "")).strip().upper()
        sentiment = _normalize(rec.get("sentiment"))
        if ticker and sentiment:
            out[ticker] = sentiment
    return out


class EpisodeSentimentService:
    def __init__(self, gcs: Optional[GCSContentService] = None):
        self.gcs = gcs or GCSContentService()

    async def get_sentiments(self, episode_ids: list[str]) -> dict:
        """Return {episode_id: {TICKER: SENTIMENT}} for the given ids.

        Cached maps are served from Redis; misses are resolved by fetching and
        parsing the episode's ticker_recommendations file once, then cached.
        """
        ids = list(dict.fromkeys(e.strip() for e in episode_ids if e and e.strip()))[:_MAX_IDS]
        if not ids:
            return {}

        result: dict = {}
        misses: list[str] = []
        for eid in ids:
            cached = await cache_get(f"epsent:{eid}")
            if cached is not None:
                try:
                    result[eid] = json.loads(cached)
                except Exception:
                    result[eid] = {}
            else:
                misses.append(eid)

        if misses:
            url_map = await self._resolve_urls(misses)
            sem = asyncio.Semaphore(_FETCH_CONCURRENCY)

            async def warm(eid: str) -> None:
                url = url_map.get(eid)
                if not url:
                    # No URL available now (e.g. outside the recent window) — don't
                    # cache, so it can resolve on a later request.
                    result[eid] = {}
                    return
                try:
                    async with sem:
                        content = await self.gcs.fetch_url_content(url, timeout=10.0)
                    mapping = _parse(content) if content else {}
                except Exception as e:
                    logger.warning("sentiment warm failed for %s: %s", eid, e)
                    mapping = {}
                await cache_set(f"epsent:{eid}", json.dumps(mapping), _SENTIMENT_TTL if mapping else _EMPTY_TTL)
                result[eid] = mapping

            await asyncio.gather(*[warm(e) for e in misses], return_exceptions=True)

        return result

    async def _resolve_urls(self, ids: list[str]) -> dict:
        """Map episode_id -> ticker_recommendations_public_url via the recent window."""
        from src.services.podcast import PodcastService

        try:
            episodes = await PodcastService().get_recent_episodes(limit=200, enrich_content=False)
        except Exception as e:
            logger.warning("sentiment url resolution failed: %s", e)
            return {}
        wanted = set(ids)
        return {
            ep.id: ep.ticker_recommendations_public_url
            for ep in episodes
            if ep.id in wanted and ep.ticker_recommendations_public_url
        }
