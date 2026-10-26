import pandas as pd
import pytest

from app.services.data_store import ACTUAL_COLUMNS, FORECAST_COLUMNS, DataStore, _normalize


def test_normalization_wind_filter_and_preserve_versions():
    actuals = [
        {"startTime": "2026-01-15 00:00", "generation": "10", "fuelType": "WIND", "extra": 1},
        {"startTime": "2026-01-15T01:00:00+01:00", "generation": 10, "fuelType": "WIND", "extra": 2},
        {"startTime": "2026-01-15 00:30", "generation": 99, "fuelType": "CCGT"},
    ]
    forecasts = [
        {"startTime": "2026-01-15 00:00", "publishTime": "2026-01-14 07:00", "generation": "10"},
        {"startTime": "2026-01-15 00:00", "publishTime": "2026-01-14 08:00", "generation": 20},
        {"startTime": "2026-01-15 00:00", "publishTime": "2026-01-14 08:00", "generation": 20},
        {"startTime": "2026-01-15 00:00", "publishTime": "2026-01-14 08:00", "generation": 21},
    ]
    store = DataStore.from_raw(actuals, forecasts)
    assert list(store.actuals) == ACTUAL_COLUMNS
    assert list(store.forecasts) == FORECAST_COLUMNS
    assert len(store.actuals) == 1
    assert len(store.forecasts) == 3
    assert store.actuals.iloc[0]["start_time"] == pd.Timestamp("2026-01-15T00:00:00Z")
    assert str(store.actuals["generation"].dtype) == "float64"
    assert str(store.forecasts["publish_time"].dtype) == "datetime64[ns, UTC]"


def test_empty_typed_frames():
    store = DataStore.from_raw([], [])
    for frame, columns in ((store.actuals, ACTUAL_COLUMNS), (store.forecasts, FORECAST_COLUMNS)):
        assert frame.empty
        assert list(frame.columns) == columns
        for column in columns:
            assert str(frame[column].dtype) == ("float64" if column == "generation" else "datetime64[ns, UTC]")


@pytest.mark.parametrize("column,value,match", [
    ("startTime", "not-a-date", "Invalid timestamp in start_time"),
    ("startTime", None, "Invalid timestamp in start_time"),
    ("publishTime", "not-a-date", "Invalid timestamp in publish_time"),
    ("generation", "many", "numeric"),
])
def test_invalid_values_are_clear(column, value, match):
    row = {"startTime": "2026-01-15 00:00", "publishTime": "2026-01-14 08:00", "generation": 10}
    row[column] = value
    with pytest.raises(ValueError, match=match):
        DataStore.from_raw([], [row])


def test_normalize_does_not_mutate_input():
    original = pd.DataFrame({"startTime": ["2026-01-15 00:00"], "generation": ["10"]})
    before = original.copy(deep=True)
    _normalize(original)
    pd.testing.assert_frame_equal(original, before)


@pytest.mark.parametrize("empty", [True, False])
def test_parquet_round_trip(tmp_path, empty):
    actuals = [] if empty else [{"startTime": "2026-01-15 00:00", "generation": 0, "fuelType": "WIND"}]
    forecasts = [] if empty else [{"startTime": "2026-01-15 00:00", "publishTime": "2026-01-14 08:00", "generation": 10}]
    store = DataStore.from_raw(actuals, forecasts)
    directory = tmp_path / "nested" / "data"
    store.save(directory)
    loaded = DataStore.load(directory)
    pd.testing.assert_frame_equal(loaded.actuals, store.actuals)
    pd.testing.assert_frame_equal(loaded.forecasts, store.forecasts)
    assert "__index_level_0__" not in pd.read_parquet(directory / "actuals.parquet").columns
