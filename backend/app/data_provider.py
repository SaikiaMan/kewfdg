"""Request-scoped Elexon I/O; selection and evaluation remain pure services."""

from datetime import date, timedelta
from http.client import HTTPException
from urllib.error import HTTPError, URLError

from .client import elexon
from .config import settings
from .domain import DELIVERY_START
from .services.data_store import DataStore
from .services.forecast_selector import cutoff_for_delivery_date

# The official stream specs impose no maximum date span or row/page limit.
# Seven-day chunks bound payload size; this is our policy, not an API limit.
CHUNK_DAYS = 7


class UpstreamError(Exception):
    """An Elexon request failed or returned an invalid payload."""


class UpstreamTimeout(UpstreamError):
    """An Elexon request timed out."""


def _records(fetch, *args):
    try:
        result = fetch(*args)
    except HTTPError as exc:
        if exc.code in (408, 504):
            raise UpstreamTimeout("Elexon request timed out") from exc
        raise UpstreamError("Elexon request failed") from exc
    except TimeoutError as exc:
        raise UpstreamTimeout("Elexon request timed out") from exc
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise UpstreamTimeout("Elexon request timed out") from exc
        raise UpstreamError("Elexon request failed") from exc
    except (OSError, ValueError, HTTPException) as exc:
        raise UpstreamError("Elexon request failed") from exc
    # Stream endpoints return bare arrays, never paginated response envelopes.
    # Reject errors/envelopes rather than treating them as empty successful data.
    if not isinstance(result, list) or any(not isinstance(row, dict) for row in result):
        raise UpstreamError("Elexon returned an invalid record array")
    return result


def _actuals(start: date, end: date) -> list[dict]:
    rows = []
    while start <= end:
        last = min(start + timedelta(days=CHUNK_DAYS - 1), end)
        rows.extend(_records(elexon.actual_wind, start.isoformat(), last.isoformat()))
        start = last + timedelta(days=1)
    return rows


def _publications(first_delivery: date, last_delivery: date, cutoff: str) -> list[dict]:
    start = cutoff_for_delivery_date(first_delivery, cutoff) - timedelta(days=settings.publication_lookback_days)
    # The spec does not define boundary inclusivity. Include the cutoff even
    # if the upstream upper bound is exclusive; the selector rejects later rows.
    end = cutoff_for_delivery_date(last_delivery, cutoff) + timedelta(seconds=1)
    rows = []
    while start < end:
        last = min(start + timedelta(days=CHUNK_DAYS), end)
        # Share boundaries so neither inclusive nor exclusive upper bounds can
        # lose the start of the next chunk. from_raw collapses exact duplicates.
        rows.extend(_records(elexon.wind_forecast, start.isoformat().replace('+00:00', 'Z'), last.isoformat().replace('+00:00', 'Z')))
        start = last
    return rows


def _store(actuals: list[dict], forecasts: list[dict]) -> DataStore:
    try:
        # Removes exact normalized duplicates while retaining publication versions.
        return DataStore.from_raw(actuals, forecasts)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise UpstreamError("Elexon returned invalid records") from exc


def forecast_store(delivery: date, cutoff: str) -> DataStore:
    actuals = []
    history_end = delivery - timedelta(days=2)
    first_delivery = delivery
    if history_end >= DELIVERY_START:
        first_delivery = DELIVERY_START
        actuals.extend(_actuals(DELIVERY_START, history_end))
    # Purchasing-day actuals are not needed by the existing historical buffer.
    actuals.extend(_actuals(delivery, delivery))
    return _store(actuals, _publications(first_delivery, delivery, cutoff))


def metrics_store(start: date, end: date, cutoff: str) -> DataStore:
    return _store(_actuals(start, end), _publications(start, end, cutoff))
