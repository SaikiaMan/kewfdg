"""Synthetic HTTP tests; production lifespan and cached files are never used."""

import json
from datetime import date

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_store
from app.routers import forecast, metrics
from app.services.data_store import DataStore
from app.services.evaluation import build_decision_view

METRIC_PATHS = ["summary", "by-hour", "by-horizon", "error-distribution", "safety-buffer"]


@pytest.fixture
def store():
    actuals, forecasts = [], []
    for day, predicted, actual in [
        ("2026-01-02", 100, 90), ("2026-01-03", 120, 100),
        ("2026-01-04", 80, 100), ("2026-01-05", 110, 100),
        ("2026-02-01", 200, 150),
    ]:
        targets = pd.date_range(day, periods=48, freq="30min", tz="UTC")
        publication = (targets[0] - pd.Timedelta(days=1) + pd.Timedelta(hours=8)).isoformat()
        for i, target in enumerate(targets):
            actuals.append({"startTime": target.isoformat(), "generation": actual if i % 2 == 0 else 25000, "fuelType": "WIND"})
            if i % 2 == 0:
                forecasts.append({"startTime": target.isoformat(), "publishTime": publication, "generation": predicted})
    for publication, generation in [
        ("2025-12-31T20:00:00Z", 80),
        ("2026-01-01T09:00:00Z", 100),
        ("2026-01-01T10:00:00Z", 9999),
    ]:
        forecasts.append({"startTime": "2026-01-02T00:00:00Z", "publishTime": publication, "generation": generation})
    return DataStore.from_raw(actuals, forecasts)


def client_for(store):
    app = FastAPI()
    app.include_router(forecast.router, prefix="/api")
    app.include_router(metrics.router, prefix="/api")
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)


@pytest.fixture
def client(store):
    with client_for(store) as client:
        yield client


def test_metadata_without_store_dependency():
    app = FastAPI()
    app.include_router(forecast.router, prefix="/api")
    # No state.store exists: metadata must not resolve the store dependency.
    response = TestClient(app).get("/api/meta")
    assert response.status_code == 200
    assert response.json() == {
        "purchasing_start": "2026-01-01", "purchasing_end": "2026-01-31",
        "delivery_start": "2026-01-02", "delivery_end": "2026-02-01",
        "default_cutoff": "09:00", "timezone": "Europe/London",
        "actual_resolution_minutes": 30, "forecast_resolution_minutes": 60,
        "evaluation_alignment": "matching_start_time",
    }


def test_latest_and_exact_cutoff_native_resolution(client, store):
    response = client.get("/api/forecast", params={"delivery_date": "2026-01-02"})
    assert response.status_code == 200
    result = response.json()
    assert result["purchasing_date"] == "2026-01-01"
    assert result["cutoff_utc"] == "2026-01-01T09:00:00+00:00"
    assert len(result["points"]) == 24
    assert all(point["forecast_mw"] == 100 for point in result["points"])
    assert all(point["actual_mw"] == 90 for point in result["points"])
    assert result["points"][0]["publish_time"] == "2026-01-01T09:00:00+00:00"
    assert result["points"][0]["horizon_hours"] == 15
    assert len(store.actuals.loc[store.actuals["start_time"].dt.date == date(2026, 1, 2)]) == 48
    assert result["buffer_mw_p95"] is None
    assert result["buffer_sample_count"] == 0
    assert result["kpis"] == {"avg_mw": 100, "peak_mw": 100, "min_mw": 100, "safe_avg_mw": None}


def test_custom_cutoff_changes_selected_version(client):
    result = client.get("/api/forecast", params={"delivery_date": "2026-01-02", "cutoff": "08:30"}).json()
    assert result["points"][0]["publish_time"] == "2026-01-01T08:00:00+00:00"


@pytest.mark.parametrize("delivery", ["2026-01-01", "2026-02-02", "2025-12-31"])
def test_invalid_delivery_date(client, delivery):
    assert client.get("/api/forecast", params={"delivery_date": delivery}).status_code == 422


def test_last_delivery_date_accepted(client):
    response = client.get("/api/forecast", params={"delivery_date": "2026-02-01"})
    assert response.status_code == 200
    assert response.json()["purchasing_date"] == "2026-01-31"


@pytest.mark.parametrize("path", METRIC_PATHS)
@pytest.mark.parametrize("start,end", [
    ("2026-01-03", "2026-01-02"), ("2026-01-01", "2026-01-02"),
    ("2026-02-01", "2026-02-02"),
])
def test_invalid_metric_periods(client, path, start, end):
    assert client.get(f"/api/metrics/{path}", params={"start": start, "end": end}).status_code == 422


@pytest.mark.parametrize("cutoff", ["9am", "9:00", "24:00", "09:60", "09:00:00"])
@pytest.mark.parametrize("path", ["forecast"] + [f"metrics/{p}" for p in METRIC_PATHS])
def test_shared_cutoff_validation(client, path, cutoff):
    params = {"delivery_date": "2026-01-02"} if path == "forecast" else {"start": "2026-01-02", "end": "2026-01-02"}
    assert client.get(f"/api/{path}", params={**params, "cutoff": cutoff}).status_code == 422


def test_no_eligible_forecast_404(client):
    response = client.get("/api/forecast", params={"delivery_date": "2026-01-02", "cutoff": "07:00"})
    # The earlier-day publication remains eligible for the first target.
    assert response.status_code == 200
    empty = client_for(DataStore.from_raw([], []))
    response = empty.get("/api/forecast", params={"delivery_date": "2026-01-02"})
    assert response.status_code == 404
    assert response.json()["detail"] == "No forecast available at the decision cutoff"


def test_post_cutoff_only_is_404():
    store = DataStore.from_raw([], [{"startTime": "2026-01-02T00:00:00Z", "publishTime": "2026-01-01T09:00:01Z", "generation": 99}])
    response = client_for(store).get("/api/forecast", params={"delivery_date": "2026-01-02"})
    assert response.status_code == 404


def test_hand_computed_summary(client):
    result = client.get("/api/metrics/summary", params={"start": "2026-01-02", "end": "2026-01-04"}).json()
    assert result["n"] == 72
    assert result["mae"] == pytest.approx(50 / 3)
    assert result["bias"] == pytest.approx(10 / 3)
    assert result["rmse"] == pytest.approx(300 ** 0.5)


@pytest.mark.parametrize("path", METRIC_PATHS)
def test_all_metric_endpoints(client, path):
    response = client.get(f"/api/metrics/{path}", params={"start": "2026-01-02", "end": "2026-01-04"})
    assert response.status_code == 200
    json.dumps(response.json(), allow_nan=False)
    if path == "safety-buffer":
        assert response.json() == {"confidence": 0.95, "buffer_mw": 20}


@pytest.mark.parametrize("path", METRIC_PATHS)
def test_empty_metric_endpoints(path):
    response = client_for(DataStore.from_raw([], [])).get(
        f"/api/metrics/{path}", params={"start": "2026-01-02", "end": "2026-01-02"},
    )
    assert response.status_code == 200
    result = response.json()
    if path == "summary":
        assert result == {}
    elif path in ("by-hour", "by-horizon"):
        assert result == []
    elif path == "error-distribution":
        assert result == {"counts": [], "edges": [], "p5": None, "p25": None, "p50": None, "p75": None, "p95": None}
    else:
        assert result == {"confidence": 0.95, "buffer_mw": 0.0}
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("path,key,value", [
    ("by-horizon", "bin_hours", 0), ("by-horizon", "bin_hours", 25),
    ("by-horizon", "bin_hours", 1.5),
    ("error-distribution", "bins", 4), ("error-distribution", "bins", 101),
    ("safety-buffer", "confidence", 0.5), ("safety-buffer", "confidence", 1),
    ("safety-buffer", "confidence", "nan"), ("safety-buffer", "confidence", "inf"),
])
def test_query_bounds(client, path, key, value):
    params = {"start": "2026-01-02", "end": "2026-01-02", key: value}
    assert client.get(f"/api/metrics/{path}", params=params).status_code == 422


def test_decision_buffer_uses_only_completed_days(store):
    baseline = build_decision_view(store, date(2026, 1, 5), "09:00")
    assert baseline["buffer_sample_count"] == 48
    assert baseline["buffer_mw_p95"] == 20
    assert baseline["kpis"]["safe_avg_mw"] == 90
    changed = DataStore(store.actuals.copy(), store.forecasts.copy())
    # Purchasing day, delivery day, and future actuals cannot enter the buffer.
    changed.actuals.loc[changed.actuals["start_time"] >= pd.Timestamp("2026-01-04T00:00:00Z"), "generation"] = 1e6
    changed.forecasts.loc[changed.forecasts["start_time"] >= pd.Timestamp("2026-01-06T00:00:00Z"), "generation"] = 1e6
    after = build_decision_view(changed, date(2026, 1, 5), "09:00")
    assert after["buffer_mw_p95"] == baseline["buffer_mw_p95"]
    assert after["buffer_sample_count"] == baseline["buffer_sample_count"]
    assert after["kpis"]["safe_avg_mw"] == baseline["kpis"]["safe_avg_mw"]


def test_earlier_errors_change_buffer(store):
    baseline = build_decision_view(store, date(2026, 1, 5), "09:00")
    store.actuals.loc[store.actuals["start_time"] < pd.Timestamp("2026-01-04T00:00:00Z"), "generation"] = 0
    result = build_decision_view(store, date(2026, 1, 5), "09:00")
    assert result["buffer_mw_p95"] > baseline["buffer_mw_p95"]
    assert result["kpis"]["safe_avg_mw"] == 0


def test_missing_and_nonfinite_actuals_keep_points(store):
    first = pd.Timestamp("2026-01-02T00:00:00Z")
    second = pd.Timestamp("2026-01-02T01:00:00Z")
    store.actuals = store.actuals.loc[store.actuals["start_time"] != first].copy()
    store.actuals.loc[store.actuals["start_time"] == second, "generation"] = float("inf")
    response = client_for(store).get("/api/forecast", params={"delivery_date": "2026-01-02"})
    assert response.status_code == 200
    result = response.json()
    assert len(result["points"]) == 24
    assert result["points"][0]["actual_mw"] is None
    assert result["points"][1]["actual_mw"] is None
    json.dumps(result, allow_nan=False)


def test_nonfinite_forecast_values_are_null(store):
    store.forecasts.loc[store.forecasts["start_time"] == pd.Timestamp("2026-01-02T01:00:00Z"), "generation"] = float("nan")
    store.forecasts.loc[store.forecasts["start_time"] == pd.Timestamp("2026-01-02T02:00:00Z"), "generation"] = float("inf")
    result = client_for(store).get("/api/forecast", params={"delivery_date": "2026-01-02"}).json()
    assert result["points"][1]["forecast_mw"] is None
    assert result["points"][2]["forecast_mw"] is None
    assert result["kpis"]["avg_mw"] == 100
    json.dumps(result, allow_nan=False)


def test_conflicting_actual_duplicates_are_rejected(store):
    conflicting = store.actuals.iloc[:1].assign(generation=999)
    store.actuals = pd.concat([store.actuals, conflicting], ignore_index=True)
    with pytest.raises(ValueError, match="Conflicting duplicate actual"):
        build_decision_view(store, date(2026, 1, 2), "09:00")


def test_identical_actual_duplicates_do_not_multiply_points(store):
    store.actuals = pd.concat([store.actuals, store.actuals.iloc[:1]], ignore_index=True)
    result = build_decision_view(store, date(2026, 1, 2), "09:00")
    assert len(result["points"]) == 24


def test_openapi_paths_and_response_schemas(client):
    document = client.get("/openapi.json").json()
    assert set(document["paths"]) == {"/api/meta", "/api/forecast"} | {f"/api/metrics/{path}" for path in METRIC_PATHS}
    expected = {"MetaResponse", "ForecastPoint", "Kpis", "ForecastResponse", "SummaryResponse", "HourStat", "HorizonStat", "ErrorDistributionResponse", "SafetyBufferResponse"}
    assert expected <= set(document["components"]["schemas"])
    for path in document["paths"].values():
        assert path["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    json.dumps(document, allow_nan=False)
