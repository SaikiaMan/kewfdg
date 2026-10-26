import logging

import pandas as pd
import pytest

from app.services.data_store import DataStore
from app.services.forecast_selector import (
    OUTPUT_COLUMNS,
    _delivery_window,
    cutoff_for_delivery_date,
    select_for_period,
    select_latest_forecast,
)


def forecasts(*records):
    return DataStore.from_raw([], list(records)).forecasts


def row(published="2026-01-14T08:00:00Z", generation=100, start="2026-01-15T00:00:00Z"):
    return {"startTime": start, "publishTime": published, "generation": generation}


def test_latest_eligible_not_earliest_or_post_cutoff():
    frame = forecasts(
        row("2026-01-13T20:00:00Z", 80),
        row("2026-01-14T08:00:00Z", 100),
        row("2026-01-14T10:00:00Z", 120),
    )
    selected = select_latest_forecast(frame, "2026-01-15")
    assert selected["generation"].tolist() == [100]
    assert selected.iloc[0]["publish_time"] == pd.Timestamp("2026-01-14T08:00:00Z")
    assert selected.iloc[0]["horizon_hours"] == 16
    assert selected["delivery_date"].tolist() == ["2026-01-15"]


def test_exact_cutoff_and_zero_generation():
    selected = select_latest_forecast(forecasts(row("2026-01-14T09:00:00Z", 0)), "2026-01-15")
    assert selected["generation"].tolist() == [0]


def test_delivery_window_filters_targets_and_sorts():
    frame = forecasts(
        row(start="2026-01-15T23:30:00Z"), row(start="2026-01-14T23:30:00Z"),
        row(start="2026-01-16T00:00:00Z"), row(start="2026-01-15T00:00:00Z"),
    )
    selected = select_latest_forecast(frame, "2026-01-15")
    assert selected["start_time"].tolist() == [pd.Timestamp("2026-01-15T00:00:00Z"), pd.Timestamp("2026-01-15T23:30:00Z")]


@pytest.mark.parametrize("delivery,expected", [
    ("2026-01-15", "2026-01-14T09:00:00Z"),
    ("2026-06-15", "2026-06-14T08:00:00Z"),
])
def test_cutoff_is_previous_uk_calendar_day(delivery, expected):
    assert cutoff_for_delivery_date(delivery) == pd.Timestamp(expected)


def test_custom_cutoff():
    assert cutoff_for_delivery_date("2026-06-15", "12:30") == pd.Timestamp("2026-06-14T11:30:00Z")


def test_missing_periods_warning(caplog):
    with caplog.at_level(logging.WARNING):
        result = select_latest_forecast(forecasts(row(), row("2026-01-14T10:00:00Z", start="2026-01-15T01:00:00Z")), "2026-01-15")
    assert len(result) == 1
    assert "23 expected hourly slots missing" in caplog.text


def test_no_eligible_rows_is_structured_empty(caplog):
    with caplog.at_level(logging.WARNING):
        result = select_latest_forecast(forecasts(row("2026-01-14T10:00:00Z")), "2026-01-15")
    assert result.empty
    assert list(result.columns) == OUTPUT_COLUMNS
    assert "24 expected hourly slots missing" in caplog.text


def test_empty_inputs_and_reversed_range():
    empty = forecasts()
    for result in (
        select_latest_forecast(empty, "2026-01-15"),
        select_for_period(empty, "2026-01-15", "2026-01-16"),
        select_for_period(empty, "2026-01-16", "2026-01-15"),
    ):
        assert result.empty
        assert list(result.columns) == OUTPUT_COLUMNS
        assert str(result["start_time"].dtype) == "datetime64[ns, UTC]"


def test_period_includes_both_endpoints_and_pilot_february_delivery():
    frame = forecasts(
        row("2026-01-30T08:00:00Z", start="2026-01-31T00:00:00Z"),
        row("2026-01-31T08:00:00Z", start="2026-02-01T00:00:00Z"),
    )
    result = select_for_period(frame, "2026-01-31", "2026-02-01")
    assert result["delivery_date"].tolist() == ["2026-01-31", "2026-02-01"]


@pytest.mark.parametrize("delivery,slots", [("2026-03-29", 23), ("2026-10-25", 25), ("2026-01-15", 24), ("2026-06-15", 24)])
def test_dst_delivery_windows_and_selection(delivery, slots, caplog):
    start, end = _delivery_window(delivery)
    targets = pd.date_range(start, end, freq="h", inclusive="left")
    assert len(targets) == slots
    frame = pd.DataFrame({"start_time": targets, "publish_time": cutoff_for_delivery_date(delivery), "generation": 0.0})
    with caplog.at_level(logging.WARNING):
        result = select_latest_forecast(frame, delivery)
    assert len(result) == slots
    assert result["start_time"].is_unique
    assert not caplog.records


def test_summer_uses_local_midnight_boundaries():
    start, end = _delivery_window("2026-06-15")
    assert start == pd.Timestamp("2026-06-14T23:00:00Z")
    assert end == pd.Timestamp("2026-06-15T23:00:00Z")


def test_equivalent_offsets_compare_as_instants():
    selected = select_latest_forecast(forecasts(row("2026-01-14T10:00:00+01:00")), "2026-01-15")
    assert selected.iloc[0]["publish_time"] == pd.Timestamp("2026-01-14T09:00:00Z")


def test_duplicate_policy():
    frame = forecasts(row(), row())
    assert len(select_latest_forecast(frame, "2026-01-15")) == 1
    with pytest.raises(ValueError, match="Conflicting"):
        select_latest_forecast(forecasts(row(generation=100), row(generation=200)), "2026-01-15")


def test_superseded_conflict_does_not_override_latest():
    selected = select_latest_forecast(forecasts(
        row("2026-01-13T20:00:00Z", 1), row("2026-01-13T20:00:00Z", 2), row(generation=3)
    ), "2026-01-15")
    assert selected["generation"].tolist() == [3]


@pytest.mark.parametrize("delivery", ["2026-03-30", "2026-10-26"])
def test_nonexistent_or_ambiguous_custom_cutoff_raises(delivery):
    with pytest.raises(Exception, match="exist|ambiguous|infer"):
        cutoff_for_delivery_date(delivery, "01:30")



@pytest.mark.parametrize("delivery", ["2026-01-15", "2026-03-29", "2026-10-25"])
def test_missing_native_hour_warns_once_including_dst(delivery, caplog):
    start, end = _delivery_window(delivery)
    targets = pd.date_range(start, end, freq="h", inclusive="left")
    missing_target = targets[1]
    supplied = targets.delete(1)
    frame = pd.DataFrame({
        "start_time": supplied,
        "publish_time": cutoff_for_delivery_date(delivery),
        "generation": 100.0,
    })
    with caplog.at_level(logging.WARNING):
        result = select_latest_forecast(frame, delivery)
    assert len(result) == len(targets) - 1
    assert missing_target not in result["start_time"].tolist()
    assert result["start_time"].tolist() == supplied.tolist()
    assert len(caplog.records) == 1
    assert "1 expected hourly slots missing an eligible forecast" in caplog.text
