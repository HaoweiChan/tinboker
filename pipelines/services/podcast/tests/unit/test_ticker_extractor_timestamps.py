"""Invariant-gap: source indices own evidence timestamps, never model estimates."""

from copy import deepcopy

import pytest
from src.podcast.content_builder.nodes.ticker_extractor import postprocess


@pytest.mark.parametrize('field', ['reasons', 'risks'])
@pytest.mark.parametrize('wrapper', ['ticker_insights', 'ticker_recommendations'])
def test_evidence_times_use_inclusive_sentence_boundaries(field, wrapper):
    state = {'sentences': [
        {'index': 584, 'start': 1159640, 'end': 1161200},
        {'index': 585, 'start': 1161200, 'end': 1272889},
    ]}
    payload = {wrapper: [{'ticker': 'ASML', field: [{
        'start_index': 584, 'end_index': 585,
        'start_time': 1129040, 'end_time': 1274629,
    }]}]}
    original = deepcopy(payload)
    result = postprocess(payload, state)['ticker_insights'][wrapper][0][field][0]
    assert (result['start_time'], result['end_time']) == (1159640, 1272889)
    assert payload == original


@pytest.mark.parametrize('span', [
    {'start_index': 0}, {'end_index': 0},
    {'start_index': -1, 'end_index': 0}, {'start_index': 0, 'end_index': 1},
    {'start_index': 1, 'end_index': 0}, {'start_index': True, 'end_index': 0},
    {'start_index': '0', 'end_index': 0},
])
def test_invalid_or_partial_spans_fail(span):
    with pytest.raises(ValueError, match='sentence span'):
        postprocess({'ticker_insights': [{'ticker': 'X', 'reasons': [span]}]}, {
            'sentences': [{'index': 0, 'start': 1000, 'end': 2000}],
        })


def test_legacy_time_only_evidence_is_preserved():
    payload = {'ticker_insights': [{'ticker': 'X', 'risks': [{'start_time': 1000, 'end_time': 2000}]}]}
    assert postprocess(payload, {})['ticker_insights'] == payload
