"""Wind forecast evaluation in MW: error = forecast - actual.

Positive error means overestimated wind and potential under-buying risk.
"""

import math

import numpy as np
import pandas as pd


def _number(value: float) -> float | None:
    value = float(value)
    return value if math.isfinite(value) else None


def _finite(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    values = df[columns].apply(pd.to_numeric, errors="raise")
    mask = np.isfinite(values.to_numpy(dtype=float)).all(axis=1)
    result = df.loc[mask].copy()
    result[columns] = values.loc[mask]
    return result


def build_evaluation_frame(selected: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Join unique targets, omit missing observations, and compute signed errors."""
    left_columns = ["start_time"] + [
        column for column in ("publish_time", "horizon_hours", "delivery_date") if column in selected
    ] + ["generation"]
    left = selected.reindex(columns=left_columns).copy()
    right = actuals.reindex(columns=["start_time", "generation"]).copy()
    for label, frame in (("selected", left), ("actuals", right)):
        frame["start_time"] = pd.to_datetime(frame["start_time"], utc=True, format="mixed", errors="raise")
        if frame["start_time"].isna().any():
            raise ValueError(f"Missing start_time in {label}")
        if frame["start_time"].duplicated().any():
            raise ValueError(f"Duplicate start_time values in {label}")
    if "publish_time" in left:
        left["publish_time"] = pd.to_datetime(left["publish_time"], utc=True, format="mixed", errors="raise")
    result = left.rename(columns={"generation": "forecast"}).merge(
        right.rename(columns={"generation": "actual"}),
        on="start_time", how="inner", validate="one_to_one",
    )
    for column in ("forecast", "actual"):
        result[column] = pd.to_numeric(result[column], errors="raise").astype(float)
    result = _finite(result, ["forecast", "actual"])
    result["error"] = result["forecast"] - result["actual"]
    result["abs_error"] = result["error"].abs()
    result["hour"] = result["start_time"].dt.tz_convert("Europe/London").dt.hour
    return result.sort_values("start_time").reset_index(drop=True)


def summary(df: pd.DataFrame) -> dict:
    """Return aggregate error metrics; missing/nonfinite observations are omitted."""
    frame = _finite(df, ["error", "actual"])
    if frame.empty:
        return {}
    error = frame["error"].to_numpy(dtype=float)
    absolute = np.abs(error)
    actual = frame["actual"].to_numpy(dtype=float)
    actual_scale = float(np.abs(actual).max())
    mean_actual = actual_scale * float(np.mean(actual / actual_scale)) if actual_scale else 0.0
    # Scaling avoids intermediate overflow in sums and squared errors.
    scale = float(absolute.max())
    mae = scale * float(np.mean(absolute / scale)) if scale else 0.0
    bias = scale * float(np.mean(error / scale)) if scale else 0.0
    rmse = scale * float(np.sqrt(np.mean((error / scale) ** 2))) if scale else 0.0
    return {
        "n": int(len(frame)),
        "mae": _number(mae),
        "rmse": _number(rmse),
        "bias": _number(bias),
        "nmae_pct": _number(mae / mean_actual * 100) if mean_actual != 0 else None,
        "p90_abs_error": _number(np.quantile(absolute, 0.90)),
        "p95_abs_error": _number(np.quantile(absolute, 0.95)),
    }


def _group_metrics(frame: pd.DataFrame) -> dict:
    return {
        "mae": _number(frame["error"].abs().mean()),
        "bias": _number(frame["error"].mean()),
        "n": int(len(frame)),
    }


def by_hour(df: pd.DataFrame) -> list[dict]:
    """Return MAE, bias, and counts ordered by observed Europe/London hour."""
    frame = _finite(df, ["error", "hour"])
    if frame.empty:
        return []
    return [
        {"hour": int(hour), **_group_metrics(group)}
        for hour, group in frame.groupby("hour", sort=True)
    ]


def by_horizon(df: pd.DataFrame, bin_hours: float = 6) -> list[dict]:
    """Group nonnegative horizons into fixed-width, left-closed bins from zero."""
    if not math.isfinite(bin_hours) or bin_hours <= 0:
        raise ValueError("bin_hours must be positive and finite")
    frame = _finite(df, ["error", "horizon_hours"])
    if frame.empty:
        return []
    frame = frame.loc[frame["horizon_hours"] >= 0].copy()
    if frame.empty:
        return []
    count = math.floor(float(frame["horizon_hours"].max()) / bin_hours) + 1
    edges = np.arange(count + 1, dtype=float) * bin_hours
    frame["horizon_bin"] = pd.cut(frame["horizon_hours"], bins=edges, right=False, include_lowest=True)
    return [
        {"horizon_bin": str(interval), **_group_metrics(group)}
        for interval, group in frame.groupby("horizon_bin", observed=True, sort=True)
    ]


def error_distribution(df: pd.DataFrame, bins: int = 30) -> dict:
    """Return a signed-error histogram and percentiles using JSON-safe types."""
    if type(bins) is not int or bins <= 0:
        raise ValueError("bins must be a positive integer")
    frame = _finite(df, ["error"])
    result = {"counts": [], "edges": [], **{f"p{p}": None for p in (5, 25, 50, 75, 95)}}
    if frame.empty:
        return result
    errors = frame["error"].to_numpy(dtype=float)
    counts, edges = np.histogram(errors, bins=bins)
    result["counts"] = [int(value) for value in counts]
    result["edges"] = [_number(value) for value in edges]
    result.update({f"p{p}": _number(np.quantile(errors, p / 100)) for p in (5, 25, 50, 75, 95)})
    return result


def safety_buffer(df: pd.DataFrame, confidence: float = 0.95) -> float:
    """Return max(error quantile, 0) MW as an empirical historical wind buffer.

    Subtract this buffer from the forecast for a historical empirical lower wind
    estimate. Historical coverage does not guarantee future coverage.
    """
    if not 0 < confidence < 1:
        raise ValueError("confidence must be strictly between zero and one")
    frame = _finite(df, ["error"])
    if frame.empty:
        return 0.0
    errors = frame["error"].to_numpy(dtype=float)
    scale = float(np.abs(errors).max())
    quantile = float(np.quantile(errors / scale, confidence)) * scale if scale else 0.0
    return float(max(quantile, 0.0))
