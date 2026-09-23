"""Batch attention uses the chart's population and never fills a missing day."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import threading

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from src.database.models import ContentMention
from src.services.attention import attention_level, batch_attention_levels
from src.services.trending import TrendingService


def test_batch_queries_once_per_population_with_scope_and_variants(monkeypatch):
    today = date(2026, 9, 23)
    engine = create_engine('sqlite://')
    ContentMention.__table__.create(engine)
    with Session(engine) as db:
        rows = []
        market, bare, combined = {}, {}, {}
        for age in range(160):
            day = today - timedelta(days=age)
            bare[day], combined[day], market[day] = 1, 3, 8
            for ticker, count, show, kind in [('2330', 1, 'TW', 'ticker'),
                    ('2330.TW', 2, 'TW', 'ticker'), ('OTHER', 5, 'TW', 'ticker'),
                    ('2330', 3, 'EN', 'ticker'), ('2330', 2, 'TW', 'sector')]:
                for _ in range(count):
                    rows.append(dict(mention_key=str(len(rows)), episode_id='ep',
                        ticker=ticker, mentioned_at=datetime.combine(day, datetime.min.time()),
                        podcaster=show, mention_type=kind, extraction_method='test'))
        rows.append({**rows[0], 'mention_key': 'old', 'mentioned_at': datetime(2020, 1, 1)})
        db.execute(ContentMention.__table__.insert(), rows)
        db.commit()
        monkeypatch.setattr('src.services.attention.get_session', lambda: iter([db]))
        queries = []
        event.listen(engine, 'before_cursor_execute', lambda *args: queries.append(args[2]))
        with patch('src.services.attention.attention_level', wraps=attention_level) as compute:
            out = batch_attention_levels(['2330', '2330.tw', 'MISSING'], allowed=frozenset({'TW'}), today=today)
        assert compute.call_args_list[0].args[:2] == (bare, market)
        assert compute.call_args_list[1].args[:2] == (combined, market)
        assert compute.call_args_list[2].args[:2] == ({}, market)
        assert len(queries) == 2
        for ticker, daily in [('2330', bare), ('2330.tw', combined)]:
            expected = attention_level(daily, market, today)[-1]
            assert out[ticker] == {'attention_level': expected['p'], 'attention_as_of': expected['d']}
        assert out['MISSING'] == {'attention_level': None, 'attention_as_of': None}
        assert batch_attention_levels(['2330'], allowed=frozenset(), today=today)['2330']['attention_level'] is None
        queries.clear()
        assert batch_attention_levels([], allowed=None, today=today) == {}
        assert not queries
    engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('failed', [False, True])
async def test_recent_buzz_batch_contract_and_failure_isolation(failed):
    now = datetime.now(timezone.utc)
    podcast = SimpleNamespace(
        get_recent_episodes=AsyncMock(return_value=[SimpleNamespace(id='ep',
            released_at_ms=int(now.timestamp() * 1000), created_time=None,
            related_tickers=['2330', 'NVDA'])]),
        _allowed_podcast_names=AsyncMock(return_value=frozenset({'TW'})))
    service = TrendingService(podcast_service=podcast, stock_service=object())
    service._get_translations_batch = AsyncMock(return_value={})
    main_thread = threading.get_ident()

    def batch(tickers, *, allowed, today):
        assert threading.get_ident() != main_thread
        assert tickers == ['2330', 'NVDA']
        assert allowed == frozenset({'TW'}) and today == now.date()
        if failed:
            raise RuntimeError('unavailable')
        return {'2330': {'attention_level': 0, 'attention_as_of': today.isoformat()}}

    with patch('src.services.trending.cache_get', AsyncMock(return_value=None)) as get, \
         patch('src.services.trending.cache_set', AsyncMock()) as put, \
         patch('src.services.trending.batch_attention_levels', side_effect=batch) as compute, \
         patch('src.services.episode_sentiments.EpisodeSentimentService.get_sentiments', AsyncMock(return_value={})):
        out = await service.get_recent_buzz()
        assert compute.call_count == 1
        assert get.call_args.args[0].endswith(':v6')
        assert put.call_args.args[2] == 1800
    assert out['tickers'][0]['attention_level'] == (None if failed else 0)
    assert out['tickers'][0]['attention_as_of'] == (None if failed else now.date().isoformat())
    assert out['tickers'][1]['attention_level'] is None
    assert out['tickers'][1]['attention_as_of'] is None
