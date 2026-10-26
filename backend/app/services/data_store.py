"""Normalize Elexon records and persist the supplied publication history."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ACTUAL_COLUMNS = ["start_time", "generation"]
FORECAST_COLUMNS = ["start_time", "publish_time", "generation"]


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({
        column: pd.Series(dtype="float64" if column == "generation" else "datetime64[ns, UTC]")
        for column in columns
    })


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize names, UTC timestamps (naive means UTC), and MW generation."""
    result = df.rename(columns={"startTime": "start_time", "publishTime": "publish_time"}).copy()
    if result.columns.duplicated().any():
        raise ValueError("Duplicate columns after timestamp name normalization")
    for column in ("start_time", "publish_time"):
        if column in result:
            try:
                result[column] = pd.to_datetime(
                    result[column], utc=True, format="mixed", errors="raise"
                ).astype("datetime64[ns, UTC]")
                if result[column].isna().any():
                    raise ValueError("missing timestamp")
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError(f"Invalid timestamp in {column}") from exc
    if "generation" in result:
        try:
            result["generation"] = pd.to_numeric(result["generation"], errors="raise").astype(float)
        except (ValueError, TypeError) as exc:
            raise ValueError("generation must contain numeric values") from exc
    return result


def _required(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    df = _normalize(df)
    missing = set(columns) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
    return df[columns].drop_duplicates().reset_index(drop=True)


@dataclass
class DataStore:
    """Actual wind generation and all distinct supplied forecast versions, in MW."""

    actuals: pd.DataFrame
    forecasts: pd.DataFrame

    @classmethod
    def from_raw(cls, actuals_raw: list[dict], forecasts_raw: list[dict]) -> "DataStore":
        """Filter WIND actuals, normalize fields, and remove only exact duplicates."""
        actuals = pd.DataFrame(actuals_raw)
        if actuals_raw:
            if "fuelType" not in actuals:
                raise ValueError("Actual records must contain fuelType")
            actuals = actuals.loc[actuals["fuelType"] == "WIND"]
        actuals = _required(actuals, ACTUAL_COLUMNS) if not actuals.empty else _empty(ACTUAL_COLUMNS)
        forecasts = (
            _required(pd.DataFrame(forecasts_raw), FORECAST_COLUMNS)
            if forecasts_raw else _empty(FORECAST_COLUMNS)
        )
        return cls(actuals=actuals, forecasts=forecasts)

    @classmethod
    def load(cls, data_dir: str | Path) -> "DataStore":
        """Read normalized actuals.parquet and forecasts.parquet from data_dir."""
        directory = Path(data_dir)
        return cls(
            actuals=_required(pd.read_parquet(directory / "actuals.parquet"), ACTUAL_COLUMNS),
            forecasts=_required(pd.read_parquet(directory / "forecasts.parquet"), FORECAST_COLUMNS),
        )

    def save(self, data_dir: str | Path) -> None:
        """Create data_dir and save both frames without their pandas indexes."""
        directory = Path(data_dir)
        directory.mkdir(parents=True, exist_ok=True)
        self.actuals.to_parquet(directory / "actuals.parquet", index=False)
        self.forecasts.to_parquet(directory / "forecasts.parquet", index=False)
