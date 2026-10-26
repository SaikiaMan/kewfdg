"""Metadata and historical purchasing-decision HTTP endpoints."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..config import settings
from ..dependencies import Cutoff, get_store, validate_period
from ..domain import DELIVERY_END, DELIVERY_START, PURCHASING_END, PURCHASING_START
from ..services import evaluation
from ..services.data_store import DataStore

router = APIRouter()


@router.get("/meta", response_model=schemas.MetaResponse)
def meta() -> dict:
    """Describe supported dates and the native data resolutions."""
    return {
        "purchasing_start": PURCHASING_START.isoformat(),
        "purchasing_end": PURCHASING_END.isoformat(),
        "delivery_start": DELIVERY_START.isoformat(),
        "delivery_end": DELIVERY_END.isoformat(),
        "default_cutoff": settings.cutoff_time,
        "timezone": "Europe/London",
        "actual_resolution_minutes": 30,
        "forecast_resolution_minutes": 60,
        "evaluation_alignment": "matching_start_time",
    }


@router.get("/forecast", response_model=schemas.ForecastResponse)
def forecast(
    delivery_date: date,
    cutoff: Cutoff = settings.cutoff_time,
    store: DataStore = Depends(get_store),
) -> dict:
    """Show eligible forecasts; actuals are retrospective comparison values.

    The empirical buffer uses earlier completed days only. Actual publication
    availability and later revisions are not tracked, so hindsight cannot be
    eliminated and future coverage is not guaranteed.
    """
    validate_period(delivery_date, delivery_date)
    result = evaluation.build_decision_view(store, delivery_date, cutoff)
    if result is None:
        raise HTTPException(status_code=404, detail="No forecast available at the decision cutoff")
    return result
