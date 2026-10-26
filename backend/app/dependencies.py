"""Shared HTTP dependencies and request validation."""

from datetime import date
import re
from typing import Annotated

from fastapi import HTTPException, Query, Request

from .domain import DELIVERY_END, DELIVERY_START
from . import data_provider
from .config import settings
from .services.data_store import DataStore

CUTOFF_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
Cutoff = Annotated[str, Query(pattern=CUTOFF_PATTERN)]


def get_store(request: Request) -> DataStore:
    """Fetch this request's data in FastAPI's synchronous worker pool.

    Kept as the shared override point for synthetic DataStore injection.
    Validate before I/O: route-body validation otherwise occurs too late.
    """
    query = request.query_params
    cutoff = query.get("cutoff", settings.cutoff_time)
    if not re.fullmatch(CUTOFF_PATTERN, cutoff):
        raise HTTPException(status_code=422, detail="Invalid cutoff")
    try:
        if request.url.path.rstrip("/").endswith("/forecast"):
            delivery = date.fromisoformat(query["delivery_date"])
            validate_period(delivery, delivery)
            return data_provider.forecast_store(delivery, cutoff)
        start, end = date.fromisoformat(query["start"]), date.fromisoformat(query["end"])
        validate_period(start, end)
        return data_provider.metrics_store(start, end, cutoff)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid or missing delivery date range") from exc
    except data_provider.UpstreamTimeout as exc:
        raise HTTPException(status_code=504, detail="Elexon request timed out") from exc
    except data_provider.UpstreamError as exc:
        raise HTTPException(status_code=502, detail="Unable to retrieve valid data from Elexon") from exc


def validate_period(start: date, end: date) -> None:
    """Reject reversed or unsupported delivery-date ranges with HTTP 422."""
    if start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")
    if not (DELIVERY_START <= start <= end <= DELIVERY_END):
        raise HTTPException(
            status_code=422,
            detail=f"Delivery dates must be between {DELIVERY_START} and {DELIVERY_END}",
        )
