"""Compose selection and evaluation without HTTP, filesystem, or network access.

Decision buffers use completed delivery days strictly before the purchasing day.
This avoids within-day hindsight, but actual publication times are not stored:
historical availability cannot be proved and later actual revisions may introduce
hindsight. Returned actual_mw values are retrospective comparisons, not values
known at purchasing time. Empirical historical coverage is no future guarantee.
"""

import math
from datetime import date, timedelta

import pandas as pd

from ..domain import DELIVERY_START
from . import forecast_selector, metrics
from .data_store import DataStore


def _number(value: object, digits: int | None = None) -> float | None:
    if pd.isna(value):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return round(number, digits) if digits is not None else number


def evaluate_period(store: DataStore, start: date, end: date, cutoff: str) -> pd.DataFrame:
    """Evaluate exact target matches over the inclusive delivery-date range."""
    selected = forecast_selector.select_for_period(store.forecasts, start, end, cutoff)
    return metrics.build_evaluation_frame(selected, store.actuals)


def build_decision_view(store: DataStore, delivery_date: date, cutoff: str) -> dict | None:
    """Build native forecast points and a buffer from earlier completed days only.

    Missing actuals do not remove selected points. Exact duplicate actual rows
    collapse; conflicting values at a selected target raise rather than multiply
    points. Current/future actuals never contribute to the historical buffer.
    """
    selected = forecast_selector.select_latest_forecast(store.forecasts, delivery_date, cutoff)
    if selected.empty:
        return None
    actuals = store.actuals.loc[
        store.actuals["start_time"].isin(selected["start_time"]),
        ["start_time", "generation"],
    ].drop_duplicates()
    if actuals["start_time"].duplicated().any():
        raise ValueError("Conflicting duplicate actual start_time values")
    points = selected.rename(columns={"generation": "forecast_mw"}).merge(
        actuals.rename(columns={"generation": "actual_mw"}),
        on="start_time", how="left", validate="one_to_one", sort=False,
    ).sort_values("start_time")

    purchasing_date = delivery_date - timedelta(days=1)
    historical_end = purchasing_date - timedelta(days=1)
    buffer = None
    sample_count = 0
    if historical_end >= DELIVERY_START:
        # Restrict actual observations as well as selected forecasts before joining.
        # Jan/Feb London midnights are UTC, but use the shared local-day boundaries.
        history_end, _ = forecast_selector._delivery_window(purchasing_date)
        history_start, _ = forecast_selector._delivery_window(DELIVERY_START)
        historical_actuals = store.actuals.loc[
            (store.actuals["start_time"] >= history_start)
            & (store.actuals["start_time"] < history_end)
        ]
        historical_store = DataStore(historical_actuals, store.forecasts)
        historical = evaluate_period(historical_store, DELIVERY_START, historical_end, cutoff)
        sample_count = len(historical)
        if sample_count:
            buffer = _number(metrics.safety_buffer(historical, confidence=0.95))

    values = pd.to_numeric(selected["generation"], errors="raise")
    values = values.loc[values.map(lambda value: pd.notna(value) and math.isfinite(value))]
    avg = _number(values.mean())
    safe_avg = _number(max(avg - buffer, 0)) if avg is not None and buffer is not None else None
    return {
        "delivery_date": delivery_date.isoformat(),
        "purchasing_date": purchasing_date.isoformat(),
        "cutoff_utc": forecast_selector.cutoff_for_delivery_date(delivery_date, cutoff).isoformat(),
        "timezone": "Europe/London",
        "points": [
            {
                "start_time": row.start_time.isoformat(),
                "publish_time": row.publish_time.isoformat(),
                "horizon_hours": _number(row.horizon_hours, 2),
                "forecast_mw": _number(row.forecast_mw),
                "actual_mw": _number(row.actual_mw),
            }
            for row in points.itertuples(index=False)
        ],
        "kpis": {
            "avg_mw": avg,
            "peak_mw": _number(values.max()),
            "min_mw": _number(values.min()),
            "safe_avg_mw": safe_avg,
        },
        "buffer_mw_p95": buffer,
        "buffer_sample_count": int(sample_count),
    }
