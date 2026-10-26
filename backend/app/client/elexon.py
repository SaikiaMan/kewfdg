"""Fetch actual and forecast wind generation from Elexon BMRS."""

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..config import BASE_URL, TIMEOUT


def _fetch(dataset: str, params: dict[str, str]) -> Any:
    """Return decoded JSON; HTTP, network and JSON errors propagate to the caller."""
    query = urlencode({**params, "format": "json"})
    request = Request(
        f"{BASE_URL.rstrip('/')}/datasets/{dataset}/stream?{query}",
        headers={"Accept": "application/json"},
    )
    with urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def actual_wind(settlement_date_from: str, settlement_date_to: str) -> Any:
    """Fetch actual WIND generation for dates in YYYY-MM-DD format."""
    return _fetch(
        "FUELHH",
        {
            "settlementDateFrom": settlement_date_from,
            "settlementDateTo": settlement_date_to,
            "fuelType": "WIND",
        },
    )


def wind_forecast(publish_datetime_from: str, publish_datetime_to: str) -> Any:
    """Fetch wind forecasts published between ISO 8601 datetimes (use UTC Z)."""
    return _fetch(
        "WINDFOR",
        {
            "publishDateTimeFrom": publish_datetime_from,
            "publishDateTimeTo": publish_datetime_to,
        },
    )
