"""Strict JSON response models for the wind forecast API."""

from pydantic import BaseModel, ConfigDict


class JsonResponse(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class MetaResponse(JsonResponse):
    purchasing_start: str
    purchasing_end: str
    delivery_start: str
    delivery_end: str
    default_cutoff: str
    timezone: str
    actual_resolution_minutes: int
    forecast_resolution_minutes: int
    evaluation_alignment: str


class ForecastPoint(JsonResponse):
    start_time: str
    publish_time: str
    horizon_hours: float | None = None
    forecast_mw: float | None = None
    actual_mw: float | None = None


class Kpis(JsonResponse):
    avg_mw: float | None = None
    peak_mw: float | None = None
    min_mw: float | None = None
    safe_avg_mw: float | None = None


class ForecastResponse(JsonResponse):
    delivery_date: str
    purchasing_date: str
    cutoff_utc: str
    timezone: str
    points: list[ForecastPoint]
    kpis: Kpis
    buffer_mw_p95: float | None = None
    buffer_sample_count: int


class SummaryResponse(JsonResponse):
    n: int | None = None
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None
    nmae_pct: float | None = None
    p90_abs_error: float | None = None
    p95_abs_error: float | None = None


class HourStat(JsonResponse):
    hour: int
    mae: float | None = None
    bias: float | None = None
    n: int


class HorizonStat(JsonResponse):
    horizon_bin: str
    mae: float | None = None
    bias: float | None = None
    n: int


class ErrorDistributionResponse(JsonResponse):
    counts: list[int]
    edges: list[float | None]
    p5: float | None = None
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    p95: float | None = None


class SafetyBufferResponse(JsonResponse):
    confidence: float
    buffer_mw: float | None = None
