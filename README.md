# Wind forecast evaluation

The WindSight frontend uses TailAdmin components with forecast charts, accuracy
analytics, date/cutoff filtering, CSV export, and a responsive light/dark interface.
See [frontend setup](frontend/README.md) for local startup and validation commands.
Run `docker compose up --build` to serve the dashboard on http://localhost:8080
with the API proxied through Nginx.

FUELHH actuals are half-hourly; WINDFOR forecasts are hourly.
Accuracy metrics compare matching startTime values only.
No forecast values are interpolated or repeated.

API date parameters are delivery dates: 2 January through 1 February 2026,
corresponding to January purchasing decisions. The default decision cutoff is
09:00 Europe/London on the previous calendar day.

The forecast decision view uses matched historical delivery days strictly before
the purchasing day to estimate its empirical 95% error buffer. With no historical
matches, the buffer and safe average are null. Completed days avoid within-day
hindsight, but stored actuals have no publication times: historical availability
cannot be proved, and later actual revisions may still introduce hindsight.
Returned actual_mw values are retrospective comparisons, not values known at
purchasing time. Historical buffer coverage is not a guarantee of future coverage.
Metrics endpoints are retrospective analyses of their requested period; their
safety buffer is distinct from the restricted decision-view buffer.

API data is fetched on demand from Elexon by the synchronous `get_store`
dependency and `backend/app/data_provider.py`. Startup and `/api/meta` require
neither network access nor Parquet files. Tests can still override `get_store`
to inject synthetic DataStores. There is no persistent cache or Parquet fallback.

`/api/forecast` fetches actuals for the requested delivery day and, when needed,
completed delivery days from 2 January through two days before delivery for the
existing historical buffer. Purchasing-day actuals are not needed. `/api/metrics/*`
fetches actuals for its inclusive delivery range. Forecast publications cover the
earliest required purchasing cutoff minus `ELEXON_PUBLICATION_LOOKBACK_DAYS`
(positive integer, default 7) through the latest purchasing cutoff. A one-second
upper-bound guard includes exact-cutoff publications even if the upstream end
filter is exclusive; the existing selector rejects any post-cutoff records.
For example, 10–20 January metrics at 09:00 fetch publication history from
2 January 09:00 UTC through 19 January 09:00:01 UTC with the default lookback.
A finite lookback does **not** guarantee complete publication history: an older
eligible version can fall outside the window. Increase the setting if necessary.

Upstream contract checked against the [official Elexon OpenAPI specification](https://data.elexon.co.uk/swagger/v1/swagger.json)
and [developer portal](https://developer.data.elexon.co.uk/).
FUELHH stream accepts settlement dates and WIND fuel filtering; WINDFOR stream
accepts publication timestamps, not target delivery dates. Both return bare JSON
arrays, without pagination. The portal documents no stream data-return limits;
these two stream definitions specify no maximum date span. We nevertheless split
actuals into at most seven inclusive settlement dates and publications into at
most seven-day spans as a payload-size policy, not an asserted Elexon limit.
Publication chunks share boundaries. All chunks are combined using
`DataStore.from_raw`: exact duplicates collapse, distinct publication versions
are retained, and target/eligibility filtering remains in the existing selector.
No response is sliced or silently capped. The official API does not provide a
total count with these arrays, so completeness beyond its successful stream
response cannot be independently proved. Rate limiting (429), other upstream
errors, malformed JSON/records, and failed chunks return 502 without partial
results; upstream timeouts return 504. Successfully fetched data with no eligible
forecast still returns 404. `ELEXON_TIMEOUT_SECONDS` remains the per-call timeout;
multiple chunks can make one API request take longer. Synchronous dependencies
run in FastAPI's worker pool rather than blocking the async event loop.
