"""Historical selection from supplied records; history completeness is not assumed."""

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger(__name__)
LONDON = ZoneInfo("Europe/London")
OUTPUT_COLUMNS = ["start_time", "publish_time", "generation", "horizon_hours", "delivery_date"]


def _date(value: date | str) -> date:
    if isinstance(value, str):
        return date.fromisoformat(value)
    if type(value) is not date:
        raise ValueError("Expected a calendar date or ISO YYYY-MM-DD string")
    return value


def _empty() -> pd.DataFrame:
    return pd.DataFrame({
        "start_time": pd.Series(dtype="datetime64[ns, UTC]"),
        "publish_time": pd.Series(dtype="datetime64[ns, UTC]"),
        "generation": pd.Series(dtype="float64"),
        "horizon_hours": pd.Series(dtype="float64"),
        "delivery_date": pd.Series(dtype="str"),
    })


def cutoff_for_delivery_date(delivery_date: date | str, cutoff_hhmm: str = "09:00") -> pd.Timestamp:
    """Return the previous calendar day's UK-local cutoff as a UTC timestamp.

    Ambiguous or nonexistent local cutoff times raise rather than guessing a fold.
    """
    previous_day = _date(delivery_date) - timedelta(days=1)
    cutoff_time = time.fromisoformat(cutoff_hhmm)
    if cutoff_time.tzinfo is not None:
        raise ValueError("cutoff_hhmm must be a UK-local wall-clock time without an offset")
    local = pd.Timestamp(datetime.combine(previous_day, cutoff_time))
    return local.tz_localize(LONDON, ambiguous="raise", nonexistent="raise").tz_convert("UTC")


def _delivery_window(delivery_date: date | str) -> tuple[pd.Timestamp, pd.Timestamp]:
    day = _date(delivery_date)
    start = pd.Timestamp(datetime.combine(day, time.min)).tz_localize(LONDON).tz_convert("UTC")
    end = pd.Timestamp(datetime.combine(day + timedelta(days=1), time.min)).tz_localize(LONDON).tz_convert("UTC")
    return start, end


def select_latest_forecast(
    forecasts: pd.DataFrame, delivery_date: date | str, cutoff_hhmm: str = "09:00"
) -> pd.DataFrame:
    """Select the latest eligible version per supplied target, preserving zeros.

    Missing native hourly slots generate a warning; no values are resampled.
    Identical duplicates collapse; conflicting
    values in the latest publication for a target raise a clear error.
    """
    day = _date(delivery_date)
    start, end = _delivery_window(day)
    cutoff = cutoff_for_delivery_date(day, cutoff_hhmm)
    # WINDFOR is hourly; local-day boundaries yield 23/24/25 native slots.
    expected = pd.date_range(start, end, freq="h", inclusive="left")
    if forecasts.empty:
        selected = _empty()
    else:
        frame = forecasts[["start_time", "publish_time", "generation"]].copy()
        for column in ("start_time", "publish_time"):
            frame[column] = pd.to_datetime(frame[column], utc=True, format="mixed", errors="raise")
            if frame[column].isna().any():
                raise ValueError(f"Missing timestamp in {column}")
        eligible = frame.loc[
            (frame["start_time"] >= start)
            & (frame["start_time"] < end)
            & (frame["publish_time"] <= cutoff)
        ].drop_duplicates()
        latest = eligible.groupby("start_time")["publish_time"].transform("max")
        selected = eligible.loc[eligible["publish_time"] == latest].copy()
        if selected["start_time"].duplicated().any():
            raise ValueError("Conflicting forecasts for identical start_time and latest publish_time")
        selected = selected.sort_values("start_time").reset_index(drop=True)
        selected["horizon_hours"] = (
            selected["start_time"] - selected["publish_time"]
        ).dt.total_seconds() / 3600
        selected["delivery_date"] = day.isoformat()
        if selected.empty:
            selected = _empty()
    missing = len(expected.difference(pd.DatetimeIndex(selected["start_time"])))
    if missing:
        logger.warning("Delivery %s: %d expected hourly slots missing an eligible forecast", day, missing)
    return selected[OUTPUT_COLUMNS]


def select_for_period(
    forecasts: pd.DataFrame, start: date | str, end: date | str, cutoff_hhmm: str = "09:00"
) -> pd.DataFrame:
    """Select each local delivery date in the inclusive range, without fetching."""
    day, final_day = _date(start), _date(end)
    frames = []
    while day <= final_day:
        selected = select_latest_forecast(forecasts, day, cutoff_hhmm)
        if not selected.empty:
            frames.append(selected)
        day += timedelta(days=1)
    return pd.concat(frames, ignore_index=True) if frames else _empty()
