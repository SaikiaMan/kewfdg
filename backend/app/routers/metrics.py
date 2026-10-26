"""Retrospective metrics for an explicitly requested historical delivery period."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from .. import schemas
from ..config import settings
from ..dependencies import Cutoff, get_store, validate_period
from ..services import evaluation, metrics
from ..services.data_store import DataStore

router = APIRouter(prefix="/metrics")


def _evaluation(
    start: date,
    end: date,
    cutoff: Cutoff = settings.cutoff_time,
    store: DataStore = Depends(get_store),
) -> Any:
    validate_period(start, end)
    return evaluation.evaluate_period(store, start, end, cutoff)


@router.get("/summary", response_model=schemas.SummaryResponse, response_model_exclude_none=True)
def summary(frame: Any = Depends(_evaluation)) -> dict:
    """Summarize matched historical errors; empty evaluations return {}."""
    return metrics.summary(frame)


@router.get("/by-hour", response_model=list[schemas.HourStat])
def by_hour(frame: Any = Depends(_evaluation)) -> list[dict]:
    """Group historical errors by UK-local target hour."""
    return metrics.by_hour(frame)


@router.get("/by-horizon", response_model=list[schemas.HorizonStat])
def by_horizon(
    bin_hours: Annotated[int, Query(ge=1, le=24)] = 6,
    frame: Any = Depends(_evaluation),
) -> list[dict]:
    """Group historical errors by forecast horizon."""
    return metrics.by_horizon(frame, bin_hours=bin_hours)


@router.get("/error-distribution", response_model=schemas.ErrorDistributionResponse)
def error_distribution(
    bins: Annotated[int, Query(ge=5, le=100)] = 30,
    frame: Any = Depends(_evaluation),
) -> dict:
    """Return a histogram and percentiles of signed historical errors."""
    return metrics.error_distribution(frame, bins=bins)


@router.get("/safety-buffer", response_model=schemas.SafetyBufferResponse)
def safety_buffer(
    confidence: Annotated[float, Query(gt=0.5, lt=1, allow_inf_nan=False)] = 0.95,
    frame: Any = Depends(_evaluation),
) -> dict:
    """Analyze the requested period retrospectively, without decision-view restrictions."""
    return {"confidence": confidence, "buffer_mw": metrics.safety_buffer(frame, confidence=confidence)}
