import json
import math

import numpy as np
import pandas as pd
import pytest

from app.services import metrics


@pytest.fixture
def evaluation():
    starts = pd.date_range("2026-01-15", periods=3, freq="30min", tz="UTC")
    selected = pd.DataFrame({
        "start_time": starts, "publish_time": pd.Timestamp("2026-01-14T08:00:00Z"),
        "generation": [100, 120, 80], "horizon_hours": [16, 16.5, 17], "delivery_date": "2026-01-15",
    })
    actuals = pd.DataFrame({"start_time": starts, "generation": [90, 100, 100]})
    return metrics.build_evaluation_frame(selected, actuals)


def test_hand_computed_metrics(evaluation):
    assert evaluation["error"].tolist() == [10, 20, -20]
    result = metrics.summary(evaluation)
    assert result["n"] == 3
    assert result["mae"] == pytest.approx(50 / 3)
    assert result["rmse"] == pytest.approx(math.sqrt(300))
    assert result["bias"] == pytest.approx(10 / 3)
    assert result["nmae_pct"] == pytest.approx((50 / 3) / (290 / 3) * 100)
    assert result["p90_abs_error"] == 20
    assert result["p95_abs_error"] == 20
    assert set(["start_time", "publish_time", "horizon_hours", "delivery_date"]) <= set(evaluation)


def test_positive_bias_means_overforecasting(evaluation):
    assert metrics.summary(evaluation.iloc[:2])["bias"] == 15


def test_matching_is_by_target_and_missing_actuals_are_not_zero():
    starts = pd.date_range("2026-01-15", periods=4, freq="30min", tz="UTC")
    selected = pd.DataFrame({"start_time": starts[:3], "generation": [100, 120, 80]})
    actuals = pd.DataFrame({"start_time": [starts[2], starts[0], starts[3]], "generation": [100, 90, 999]})
    result = metrics.build_evaluation_frame(selected, actuals)
    assert result["error"].tolist() == [10, -20]
    assert result["start_time"].tolist() == [starts[0], starts[2]]


@pytest.mark.parametrize("duplicate_side", ["selected", "actuals"])
def test_duplicate_target_raises(duplicate_side):
    frame = pd.DataFrame({"start_time": ["2026-01-15T00:00:00Z"], "generation": [10]})
    duplicate = pd.concat([frame, frame], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate start_time"):
        metrics.build_evaluation_frame(duplicate if duplicate_side == "selected" else frame, duplicate if duplicate_side == "actuals" else frame)


def test_equivalent_offset_targets_are_duplicates():
    selected = pd.DataFrame({"start_time": ["2026-01-15T00:00:00Z", "2026-01-15T01:00:00+01:00"], "generation": [10, 20]})
    with pytest.raises(ValueError, match="Duplicate"):
        metrics.build_evaluation_frame(selected, pd.DataFrame())


def test_missing_observations_omitted_and_zero_kept():
    starts = pd.date_range("2026-01-15", periods=3, freq="30min", tz="UTC")
    result = metrics.build_evaluation_frame(
        pd.DataFrame({"start_time": starts, "generation": [0, 1, np.nan]}),
        pd.DataFrame({"start_time": starts, "generation": [0, np.nan, 2]}),
    )
    assert len(result) == 1
    assert result.iloc[0]["actual"] == 0
    assert metrics.summary(result)["nmae_pct"] is None


def test_hour_is_uk_local_and_sorted():
    starts = pd.to_datetime(["2026-06-01T23:30:00Z", "2026-06-01T08:00:00Z"], utc=True)
    result = metrics.build_evaluation_frame(
        pd.DataFrame({"start_time": starts, "generation": [30, 20]}),
        pd.DataFrame({"start_time": starts, "generation": [10, 10]}),
    )
    assert metrics.by_hour(result) == [
        {"hour": 0, "mae": 20.0, "bias": 20.0, "n": 1},
        {"hour": 9, "mae": 10.0, "bias": 10.0, "n": 1},
    ]


def test_horizon_bins_numerically_ordered_and_zero_included():
    frame = pd.DataFrame({"horizon_hours": [24, 0, 12, 6, 5.9], "error": [1, 2, 3, 4, 5]})
    result = metrics.by_horizon(frame)
    assert [r["horizon_bin"] for r in result] == ["[0.0, 6.0)", "[6.0, 12.0)", "[12.0, 18.0)", "[24.0, 30.0)"]
    assert [r["n"] for r in result] == [2, 1, 1, 1]


@pytest.mark.parametrize("width", [0, -1, float("nan"), float("inf")])
def test_invalid_horizon_bin_width(width):
    with pytest.raises(ValueError, match="bin_hours"):
        metrics.by_horizon(pd.DataFrame(), width)


def test_safety_buffer():
    assert metrics.safety_buffer(pd.DataFrame({"error": [-20, -10, -1]})) == 0
    assert metrics.safety_buffer(pd.DataFrame({"error": [10, 20, -20]})) == pytest.approx(19)


@pytest.mark.parametrize("confidence", [0, 1, -0.1, 1.1, float("nan")])
def test_invalid_confidence(confidence):
    with pytest.raises(ValueError, match="confidence"):
        metrics.safety_buffer(pd.DataFrame(), confidence)


def test_signed_histogram_and_percentiles(evaluation):
    result = metrics.error_distribution(evaluation, bins=2)
    assert result["counts"] == [1, 2]
    assert result["edges"] == [-20.0, 0.0, 20.0]
    assert result["p50"] == 10
    assert result["p5"] == pytest.approx(-17)


def test_empty_inputs():
    empty = pd.DataFrame()
    frame = metrics.build_evaluation_frame(empty, empty)
    assert frame.empty
    assert list(frame.columns) == ["start_time", "forecast", "actual", "error", "abs_error", "hour"]
    assert metrics.summary(empty) == {}
    assert metrics.by_hour(empty) == []
    assert metrics.by_horizon(empty) == []
    assert metrics.safety_buffer(empty) == 0.0
    assert metrics.error_distribution(empty) == {"counts": [], "edges": [], "p5": None, "p25": None, "p50": None, "p75": None, "p95": None}


def test_empty_evaluation_preserves_optional_columns(evaluation):
    selected = evaluation.rename(columns={"forecast": "generation"}).iloc[:0]
    frame = metrics.build_evaluation_frame(selected, pd.DataFrame())
    assert frame.empty
    assert {"publish_time", "horizon_hours", "delivery_date"} <= set(frame.columns)


def test_nonfinite_metric_inputs_and_strict_json(evaluation):
    dirty = pd.concat([evaluation, evaluation.iloc[:1].assign(error=np.inf, actual=np.nan)], ignore_index=True)
    outputs = [metrics.summary(dirty), metrics.by_hour(dirty), metrics.by_horizon(dirty), metrics.error_distribution(dirty), metrics.safety_buffer(dirty)]
    for output in outputs:
        json.dumps(output, allow_nan=False)
    assert metrics.summary(dirty)["n"] == 3


def test_nonfinite_summary_output_becomes_none():
    frame = pd.DataFrame({"error": [1e308, 1e308], "actual": [1e-308, 1e-308]})
    result = metrics.summary(frame)
    assert result["nmae_pct"] is None
    json.dumps(result, allow_nan=False)



@pytest.mark.parametrize("delivery,actual_count,forecast_count", [
    ("2026-01-15", 48, 24),
    ("2026-03-29", 46, 23),
    ("2026-10-25", 50, 25),
])
def test_native_resolution_exact_matching(delivery, actual_count, forecast_count):
    from app.services.data_store import DataStore
    from app.services.forecast_selector import (
        _delivery_window, cutoff_for_delivery_date, select_latest_forecast,
    )

    start, end = _delivery_window(delivery)
    actual_targets = pd.date_range(start, end, freq="30min", inclusive="left")
    forecast_targets = pd.date_range(start, end, freq="h", inclusive="left")
    published = cutoff_for_delivery_date(delivery).isoformat()
    actuals_raw = [
        {"startTime": target.isoformat(), "generation": float(i), "fuelType": "WIND"}
        for i, target in enumerate(actual_targets)
    ]
    forecasts_raw = [
        {"startTime": target.isoformat(), "publishTime": published, "generation": float(100 + i)}
        for i, target in enumerate(forecast_targets)
    ]
    store = DataStore.from_raw(actuals_raw, forecasts_raw)
    original_actuals = store.actuals.copy(deep=True)
    selected = select_latest_forecast(store.forecasts, delivery)
    evaluation = metrics.build_evaluation_frame(selected, store.actuals)

    assert len(store.actuals) == actual_count
    assert len(store.forecasts) == len(selected) == len(evaluation) == forecast_count
    assert selected["start_time"].tolist() == forecast_targets.tolist()
    assert selected["generation"].tolist() == [float(100 + i) for i in range(forecast_count)]
    assert evaluation["start_time"].tolist() == forecast_targets.tolist()
    assert evaluation["actual"].tolist() == [float(2 * i) for i in range(forecast_count)]
    pd.testing.assert_frame_equal(store.actuals, original_actuals)
