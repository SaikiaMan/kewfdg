"""Mock-only tests of request-scoped fetching and its HTTP integration."""
from datetime import date, timedelta
from http.client import IncompleteRead
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import data_provider as provider
from app.client import elexon
from app.dependencies import get_store
from app.main import app
from app.services.data_store import DataStore


@pytest.fixture(autouse=True)
def upstream(monkeypatch):
    calls = {'actuals': [], 'forecasts': []}
    def actuals(start, end):
        calls['actuals'].append((start, end))
        return []
    def forecasts(start, end):
        calls['forecasts'].append((start, end))
        return []
    monkeypatch.setattr(elexon, 'actual_wind', actuals)
    monkeypatch.setattr(elexon, 'wind_forecast', forecasts)
    monkeypatch.setattr(provider, 'settings', SimpleNamespace(publication_lookback_days=7))
    return calls


def test_startup_and_meta_without_parquet_or_network(monkeypatch, upstream):
    def forbidden(*args):
        pytest.fail('Parquet must not be loaded')
    monkeypatch.setattr(DataStore, 'load', forbidden)
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/api/meta').status_code == 200
        assert not hasattr(app.state, 'store')
    assert upstream == {'actuals': [], 'forecasts': []}


@pytest.mark.parametrize('delivery', ['2026-01-02', '2026-01-03', '2026-01-15', '2026-02-01'])
def test_forecast_ranges_include_exact_buffer_days(delivery, upstream):
    with TestClient(app) as client:
        response = client.get('/api/forecast', params={'delivery_date': delivery, 'cutoff': '10:30'})
    assert response.status_code == 404
    day = date.fromisoformat(delivery)
    fetched = set()
    for start, end in upstream['actuals']:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
        assert 0 <= (b - a).days < provider.CHUNK_DAYS
        fetched.update(a + timedelta(days=i) for i in range((b-a).days + 1))
    expected = {day}
    a = date(2026, 1, 2)
    while a <= day - timedelta(days=2):
        expected.add(a)
        a += timedelta(days=1)
    assert fetched == expected
    first = min(expected) - timedelta(days=1)
    assert pd.Timestamp(upstream['forecasts'][0][0]) == pd.Timestamp(f'{first}T10:30:00Z') - pd.Timedelta(days=7)
    assert pd.Timestamp(upstream['forecasts'][-1][1]) == pd.Timestamp(f'{day - timedelta(days=1)}T10:30:01Z')


@pytest.mark.parametrize('path', ['summary', 'by-hour', 'by-horizon', 'error-distribution', 'safety-buffer'])
def test_metrics_range_chunks_and_cutoffs(path, upstream):
    with TestClient(app) as client:
        response = client.get(f'/api/metrics/{path}', params={'start': '2026-01-10', 'end': '2026-01-20', 'cutoff': '08:15'})
    assert response.status_code == 200
    assert upstream['actuals'] == [('2026-01-10', '2026-01-16'), ('2026-01-17', '2026-01-20')]
    windows = upstream['forecasts']
    assert windows[0][0] == '2026-01-02T08:15:00Z'
    assert windows[-1][1] == '2026-01-19T08:15:01Z'
    for i, (start, end) in enumerate(windows):
        assert pd.Timedelta(0) < pd.Timestamp(end)-pd.Timestamp(start) <= pd.Timedelta(days=7)
        if i:
            assert start == windows[i-1][1]


def test_configurable_lookback(monkeypatch, upstream):
    monkeypatch.setattr(provider, 'settings', SimpleNamespace(publication_lookback_days=15))
    provider.metrics_store(date(2026, 1, 10), date(2026, 1, 10), '09:00')
    assert upstream['forecasts'][0][0] == '2025-12-25T09:00:00Z'
    assert len(upstream['forecasts']) == 3


def test_chunk_combination_keeps_distinct_publications(monkeypatch):
    old = {'startTime': '2026-01-10T00:00:00Z', 'publishTime': '2026-01-08T09:00:00Z', 'generation': 80}
    latest = {**old, 'publishTime': '2026-01-09T09:00:00Z', 'generation': 100}
    calls = []
    def forecasts(start, end):
        calls.append((start,end))
        return [old, old] if len(calls) == 1 else [old, latest]
    actual = {'startTime': old['startTime'], 'fuelType': 'WIND', 'generation': 90}
    monkeypatch.setattr(elexon, 'actual_wind', lambda *args: [actual, actual])
    monkeypatch.setattr(elexon, 'wind_forecast', forecasts)
    store = provider.metrics_store(date(2026,1,10), date(2026,1,20), '09:00')
    assert len(calls) > 1
    assert len(store.actuals) == 1
    assert sorted(store.forecasts.generation.tolist()) == [80,100]


@pytest.mark.parametrize('failure,status', [
    (HTTPError('url',500,'private detail',None,None),502),
    (HTTPError('url',429,'rate limited',None,None),502),
    (HTTPError('url',504,'timeout',None,None),504),
    (HTTPError('url',408,'timeout',None,None),504),
    (URLError('private connection details'),502),
    (TimeoutError('private timeout details'),504),
    (URLError(TimeoutError('private timeout details')),504),
    (ValueError('invalid JSON with private details'),502),
    (IncompleteRead(b'partial upstream response'),502),
])
@pytest.mark.parametrize('client_name', ['actual_wind', 'wind_forecast'])
def test_upstream_failures_are_controlled(monkeypatch, failure, status, client_name):
    def fail(*args):
        raise failure
    monkeypatch.setattr(elexon, client_name, fail)
    with TestClient(app) as client:
        result = client.get('/api/forecast?delivery_date=2026-01-02')
    assert result.status_code == status
    assert 'private' not in result.text
    assert 'Traceback' not in result.text


@pytest.mark.parametrize('payload', [{}, {'data': [], 'total': 100}, None, [1], [{'wrong': 'fields'}]])
@pytest.mark.parametrize('client_name', ['actual_wind', 'wind_forecast'])
def test_invalid_upstream_payload_is_not_empty_success(monkeypatch, payload, client_name):
    monkeypatch.setattr(elexon, client_name, lambda *args: payload)
    with TestClient(app) as client:
        assert client.get('/api/forecast?delivery_date=2026-01-02').status_code == 502


def test_failed_later_chunk_never_returns_partial_success(monkeypatch):
    calls = []
    def forecasts(*args):
        calls.append(args)
        if len(calls) > 1:
            raise URLError('later chunk failed')
        return [{'startTime':'2026-01-10T00:00:00Z','publishTime':'2026-01-09T08:00:00Z','generation':100}]
    monkeypatch.setattr(elexon,'wind_forecast', forecasts)
    with TestClient(app) as client:
        result = client.get('/api/metrics/summary?start=2026-01-10&end=2026-01-20')
    assert result.status_code == 502


def test_publication_before_first_cutoff_is_eligible(monkeypatch, upstream):
    monkeypatch.setattr(elexon, 'wind_forecast', lambda *args: [{
        'startTime': '2026-01-02T00:00:00Z',
        'publishTime': '2025-12-31T08:00:00Z', 'generation': 80,
    }])
    with TestClient(app) as client:
        result = client.get('/api/forecast?delivery_date=2026-01-02')
    assert result.status_code == 200
    assert result.json()['points'][0]['forecast_mw'] == 80
    assert result.json()['points'][0]['actual_mw'] is None


@pytest.mark.parametrize('query', [
    'start=2026-01-20&end=2026-01-10',
    'start=2026-01-01&end=2026-01-10',
    'start=no&end=2026-01-10',
    'start=2026-01-10',
])
def test_invalid_metrics_range_does_not_fetch(query, upstream):
    with TestClient(app) as client:
        assert client.get('/api/metrics/summary?' + query).status_code == 422
    assert upstream == {'actuals': [], 'forecasts': []}


@pytest.mark.parametrize('query', ['delivery_date=2026-01-01', 'delivery_date=no', 'delivery_date=2026-01-02&cutoff=25:00', ''])
def test_invalid_forecast_does_not_fetch(query, upstream):
    with TestClient(app) as client:
        assert client.get('/api/forecast?' + query).status_code == 422
    assert upstream == {'actuals': [], 'forecasts': []}


def test_dependency_override_remains_available(monkeypatch, upstream):
    app.dependency_overrides[get_store] = lambda: DataStore.from_raw([], [])
    try:
        with TestClient(app) as client:
            assert client.get('/api/forecast?delivery_date=2026-01-20').status_code == 404
    finally:
        app.dependency_overrides.clear()
    assert upstream == {'actuals': [], 'forecasts': []}


def test_fetched_data_uses_existing_cutoff_and_hindsight_rules(monkeypatch):
    actuals, forecasts = [], []
    for day, predicted, actual in [('2026-01-02',100,90), ('2026-01-03',120,100), ('2026-01-04',9000,1), ('2026-01-05',110,1)]:
        actuals.append({'startTime': day+'T00:00:00Z', 'fuelType':'WIND','generation':actual})
        publication = (date.fromisoformat(day)-timedelta(days=1)).isoformat()+'T09:00:00Z'
        forecasts.append({'startTime':day+'T00:00:00Z','publishTime':publication,'generation':predicted})
        forecasts.append({'startTime':day+'T00:00:00Z','publishTime':publication.replace('09:00','10:00'),'generation':99999})
    # Include an eligible version before the earliest cutoff too.
    forecasts.append({'startTime':'2026-01-02T00:00:00Z','publishTime':'2025-12-31T08:00:00Z','generation':80})
    monkeypatch.setattr(elexon, 'actual_wind', lambda *args: actuals)
    monkeypatch.setattr(elexon, 'wind_forecast', lambda *args: forecasts)
    with TestClient(app) as client:
        result = client.get('/api/forecast?delivery_date=2026-01-05').json()
    assert result['buffer_sample_count'] == 2
    assert result['buffer_mw_p95'] == pytest.approx(19.5)
    assert result['kpis']['safe_avg_mw'] == pytest.approx(90.5)
    assert result['points'][0]['forecast_mw'] == 110
    assert result['points'][0]['publish_time'] == '2026-01-04T09:00:00+00:00'
