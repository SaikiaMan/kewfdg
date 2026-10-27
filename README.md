# WindSight - UK wind forecast evaluation

WindSight is a pilot dashboard for a UK utility's day-ahead power purchasing team.
It shows the national wind forecasts available at a chosen purchasing cutoff and
quantifies their historical errors against reported generation. The application
uses React and Python, with Elexon as its only generation-data source.

## Submission links

- Repository: https://github.com/SaikiaMan/kewfdg
- Vercel application: https://kewfdg.vercel.app/


## Product features

- Delivery-date and purchasing-cutoff filters for the January 2026 decision period.
- Hourly forecasts and retrospective actuals in a chart and detail table.
- Average, peak, minimum, and historically buffered average wind generation.
- Accuracy analysis by delivery range, local delivery hour, and forecast horizon.
- MAE, RMSE, signed bias, normalized MAE, error percentiles, and histogram.
- Forecast CSV export, responsive navigation, light/dark themes, and error recovery.

The product supports wind-generation assessment. It does not calculate total
procurement needs because consumer demand and other generation sources are outside
this assignment's data scope.

## Start with Docker

Install Docker with Compose; on Windows, start Docker Desktop with Linux containers
enabled. Run these commands from the repository root:

```powershell
docker compose up --build -d --wait
docker compose ps
```

| Service | Local URL |
| --- | --- |
| Dashboard | http://localhost:8080 |
| Backend health | http://localhost:8000/health |
| Interactive API documentation | http://localhost:8000/docs |

The frontend waits for the backend health check. Nginx serves the built React app
and forwards `/api` requests to the backend container. Internet access is required
for image/package downloads on the first build and for Elexon data requests.
Parquet files, API keys, and data-volume mounts are not required.

Ports 8000 and 8080 must be available. Stop a separately running local backend
before starting Compose if it uses port 8000.

```powershell
# Inspect logs
docker compose logs --tail=100 backend frontend

# Stop and remove the application containers and Compose network
docker compose down
```

## Vercel multi-service deployment

The root `vercel.json` defines `backend` (FastAPI, entrypoint `app.main:app`)
and `frontend` (Vite, built with `npm ci` and `npm run build`). Import this
repository as **one project**, using the repository root as the Vercel Root
Directory, rather than selecting either service directory. Services configuration
is currently pending confirmation of the service names and public exposure.

Public routing is intentionally limited to `/api/*` for the backend; all remaining
paths go to the frontend. Service routing preserves the original request path,
so FastAPI continues to receive `/api/forecast`, `/api/meta`, and `/api/metrics/*`.
Backend `/health`, `/docs`, and `/openapi.json` are not exposed by these Vercel
rewrites. Their Docker URLs above still apply when running Compose.

The browser already fetches the same-origin `/api` base. Leave
`VITE_API_BASE_URL` unset for this deployment. No internal bindings are declared:
this frontend is static and has no server-side function calling the backend.
Binding URLs are runtime-function variables and must not be embedded into a Vite
bundle or assigned manually. The backend's outbound calls go to external Elexon,
not another service in this project. A private backend would require adding a
server-side gateway function to the frontend and binding that caller to backend;
that is a different topology from the current public API setup.

The localhost proxy in `frontend/vite.config.js` serves standalone Vite development;
the `backend:8000` hostname in Nginx serves Docker Compose. Neither is used for
Vercel production routing, which is owned by the root rewrites. Docker configuration
remains a separate way to run the same application.

With a current Vercel CLI, test all services together from the repository root:

```powershell
npx vercel dev --local
```

`--local` selects local mode without cloud authentication. Check `/api/meta`, a forecast
request such as `/api/forecast?delivery_date=2026-01-15`, and the dashboard on the
URL printed by the CLI. After confirming the topology, link the project and use
`npx vercel` for a preview deployment. Run the same checks on its public URL before
promoting it. A deployed URL will be added to the submission links after deployment.
Optional `ELEXON_TIMEOUT_SECONDS`, `ELEXON_PUBLICATION_LOOKBACK_DAYS`, and
`ELEXON_CUTOFF_TIME` belong in Vercel project environment variables. No Elexon API
key is required. This configuration uses Vercel's framework builds, not Compose
or the Dockerfiles. Multi-chunk requests remain subject to the platform's function
duration limits.

See [Vercel Services](https://vercel.com/docs/services),
[routing](https://vercel.com/docs/services/routing), and
[bindings](https://vercel.com/docs/services/bindings) for the platform contract.

## Start without Docker

Use Python 3.11+ and Node.js 22.12+ (or a newer supported LTS release).
The commands below use PowerShell and create a virtual environment in this repository.

Terminal 1, from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Terminal 2, from the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Vite forwards `/api` requests to localhost:8000.
On macOS/Linux, use `.venv/bin/python` in place of `.venv\Scripts\python.exe`.

## Repository structure

| Path | Purpose |
| --- | --- |
| `compose.yaml` | Builds and starts the frontend and backend; configures health ordering and ports. |
| `vercel.json` | Multi-service Vercel framework builds and ordered public routing. |
| `.gitignore` | Excludes generated Vercel project/runtime state. |
| `backend/Dockerfile` | Python runtime, dependencies, non-root application user, and health check. |
| `backend/requirements.txt` | Backend runtime and test dependencies. |
| `backend/app/main.py` | FastAPI application, router registration, CORS, and health endpoint. |
| `backend/app/config.py` | Elexon timeout, default cutoff, and publication-lookback settings. |
| `backend/app/domain.py` | Supported purchasing and delivery dates. |
| `backend/app/dependencies.py` | Request-scoped data dependency, validation, and upstream HTTP error mapping. |
| `backend/app/data_provider.py` | Fetch-range planning, chunked Elexon calls, and DataStore construction. |
| `backend/app/client/elexon.py` | Synchronous FUELHH and WINDFOR HTTP client functions. |
| `backend/app/services/data_store.py` | Normalizes source records, filters WIND actuals, and removes exact duplicates; also supports optional Parquet utilities. |
| `backend/app/services/forecast_selector.py` | Latest eligible forecast selection per target timestamp. |
| `backend/app/services/metrics.py` | Alignment, metric calculations, grouped errors, histogram, and empirical buffer. |
| `backend/app/services/evaluation.py` | Composes selection, retrospective evaluation, and historical decision views. |
| `backend/app/routers/` | Metadata, forecast, and metrics HTTP endpoints. |
| `backend/app/schemas.py` | JSON response models. |
| `backend/tests/` | Synthetic unit/API tests and mocked upstream orchestration tests. |
| `backend/data/` | Legacy sample Parquet files; not used by API startup or request loading. |
| `backend/check_real_data.py` | Legacy single-day download/check utility; not the production loading path. |
| `frontend/src/App.jsx` | Dashboard views, API requests, filters, charts, export, and theme state. |
| `frontend/src/App.test.jsx` | Frontend interaction tests. |
| `frontend/src/App.css`, `frontend/src/index.css` | Application layout and TailAdmin/Tailwind styling. |
| `frontend/src/vendor/tailadmin/` | Imported TailAdmin components, attribution, and upstream MIT license. |
| `frontend/public/`, `frontend/src/assets/` | Static assets, including remaining starter assets. |
| `frontend/vite.config.js` | React/Tailwind build configuration and local API proxy. |
| `frontend/nginx.conf` | Production static serving, SPA fallback, and API proxy. |
| `frontend/Dockerfile` | Node build stage and Nginx runtime stage. |

## Architecture and request flow

```text
React dashboard
  -> /api through Vite (development) or Nginx (Docker)
  -> FastAPI router / synchronous get_store dependency
  -> data_provider -> Elexon FUELHH and WINDFOR stream endpoints
  -> DataStore.from_raw
  -> forecast selection and evaluation services
  -> validated JSON response -> charts and tables
```

React does not call Elexon directly. Startup, `/health`, and `/api/meta` do not
fetch generation data. Each forecast or metrics request constructs a fresh
DataStore; there is no persistent cache or Parquet fallback. Synchronous fetching
runs in FastAPI's worker pool rather than blocking the async event loop. Pure
selection and calculation services are separate from network orchestration.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Application health. |
| `GET /api/meta` | Supported dates, default cutoff, timezone, and resolutions. |
| `GET /api/forecast?delivery_date=2026-01-15&cutoff=09:00` | Eligible forecasts, retrospective actuals, generation KPIs, and historical buffer. |
| `GET /api/metrics/summary?start=2026-01-02&end=2026-02-01&cutoff=09:00` | Period accuracy summary. |
| `GET /api/metrics/by-hour` | MAE and bias grouped by London-local target hour. |
| `GET /api/metrics/by-horizon` | MAE and bias grouped by forecast horizon; `bin_hours` defaults to 6. |
| `GET /api/metrics/error-distribution` | Signed-error histogram and percentiles; `bins` defaults to 30. |
| `GET /api/metrics/safety-buffer` | Retrospective period buffer; `confidence` defaults to 0.95. |

All metrics endpoints accept `start`, `end`, and optional `cutoff`. See `/docs`
for parameter bounds and response schemas. Invalid dates/ranges return 422.
Upstream failures, malformed records, and rate limiting return controlled 502
responses; upstream timeouts return 504. A successful fetch with no eligible
forecast returns 404. Failed chunks never produce a successful partial result.

## Data sources and decision assumptions

Official source endpoints:

- [FUELHH stream](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream): reported half-hourly generation, restricted to `fuelType=WIND`.
- [WINDFOR stream](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream): wind forecasts with target `startTime`, version `publishTime`, and generation in MW.

Purchasing dates are **1-31 January 2026**, corresponding to delivery dates
**2 January-1 February 2026**. API date parameters are delivery dates. The default
cutoff is **09:00 Europe/London on the previous calendar day**; this is a
configurable pilot assumption, not a claim about a universal market gate closure.

For each target timestamp, the selector takes the latest forecast publication at
or before that delivery day's purchasing cutoff. Later publications are excluded.
FUELHH actuals are half-hourly and WINDFOR forecasts are hourly in this application.
Evaluation compares exact matching target timestamps only: forecasts are never
repeated or interpolated. Non-finite or missing paired values are excluded from
metrics; available forecast points remain visible even when actuals are missing.
Conflicting duplicate observations are rejected rather than averaged silently.

### Fetch windows and completeness

Forecast requests fetch actuals for the delivery day plus the earlier completed
delivery days required by the historical buffer: 2 January through two days before
the requested delivery date. Purchasing-day actuals are not required by that buffer.
Metrics requests fetch actuals for their inclusive delivery range.

WINDFOR filters refer to **publication times**, not target delivery dates.
Publication fetching starts at the earliest required purchasing cutoff minus the
configured lookback and ends one second after the latest required cutoff. The
one-second guard includes exact-cutoff publications if the upstream upper bound
is exclusive; the selector still excludes post-cutoff versions.

The default lookback is seven days. A finite lookback **does not guarantee complete
publication history**: an older eligible forecast can lie outside the window.
For example, metrics for 10-20 January at 09:00 fetch publications from 2 January
09:00 UTC through 19 January 09:00:01 UTC with the default setting.

The [official OpenAPI specification](https://data.elexon.co.uk/swagger/v1/swagger.json)
defines bare JSON arrays for both stream responses, without pagination. The
[developer portal](https://developer.data.elexon.co.uk/) documents no stream
return limits, and these endpoint definitions specify no maximum date span.
Requests nevertheless use seven-day publication chunks and at most seven inclusive
settlement dates per actuals chunk to bound payload size. This is an application
policy, not an asserted upstream maximum. Publication chunks share boundaries;
exact duplicates collapse and distinct forecast publication versions remain.
Results are not sliced or capped. Upstream arrays provide no total count with
which to independently prove historical completeness.

## Accuracy and buffer definitions

Let `F` be forecast generation, `A` actual generation, and `e = F - A`, all in MW.
Positive error means the forecast overestimated wind generation.

| Measure | Calculation / interpretation |
| --- | --- |
| Matched count | Number of finite, timestamp-matched pairs. |
| MAE | `mean(abs(e))`, typical absolute error in MW. |
| RMSE | `sqrt(mean(e^2))`, gives greater weight to large errors. |
| Bias | `mean(e)`, indicates systematic over/underestimation. |
| Normalized MAE | `100 * MAE / mean(A)`; null if mean actual generation is zero. |
| Absolute-error percentiles | 90th and 95th percentiles of `abs(e)`. |
| Histogram percentiles | Percentiles of signed errors, distinct from absolute-error percentiles. |
| Empirical buffer | `max(quantile(e, confidence), 0)`, default confidence 95%. |
| Buffered average | `max(average forecast - decision buffer, 0)`. |

The decision-view buffer uses matched historical delivery days **strictly before
the purchasing day**, avoiding purchasing-day and delivery-day actuals in the
calculation. With no historical matches, its buffer and buffered average are null.
The metrics safety-buffer endpoint is retrospective over the selected period and
returns zero for an empty evaluation; it is distinct from the decision-view buffer.

Actuals displayed next to forecasts are retrospective comparisons, not values
known at purchasing time. Actual publication times are not retained, so historical
availability cannot be proved and later revisions may introduce hindsight.
Historical empirical coverage is not a guarantee of future coverage. The buffered
average is an analytical indicator, not a guaranteed generation floor.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ELEXON_TIMEOUT_SECONDS` | `30` | Per-upstream-call timeout; several chunks can make the total API request longer. |
| `ELEXON_PUBLICATION_LOOKBACK_DAYS` | `7` | Positive integer; history before the earliest required purchasing cutoff. |
| `ELEXON_CUTOFF_TIME` | `09:00` | Backend default cutoff in London-local `HH:MM`; individual API requests can override it. |
| `VITE_API_BASE_URL` | `/api` | Frontend build-time API base, including the `/api` suffix. |

Compose forwards the timeout and lookback variables. To change them in PowerShell:

```powershell
$env:ELEXON_TIMEOUT_SECONDS = '60'
$env:ELEXON_PUBLICATION_LOOKBACK_DAYS = '14'
docker compose up -d --force-recreate
```

The cutoff variable must be supplied to a locally started backend or explicitly
added to Compose's backend environment to change the container default. The
frontend API base must be set before building for a separately hosted backend;
changing a runtime environment variable cannot rewrite an existing React bundle.
Nginx allows 300 seconds between upstream reads. Each analytics endpoint fetches
its own data, so loading analytics makes multiple upstream request sequences.

## Tests and verification

From the repository root, after creating the local environment above:

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
```

From `frontend/`:

```powershell
npm run test
npm run lint
npm run build
```

The backend suite covers native timestamp alignment, forecast versions and exact
cutoffs, date validation, duplicates, missing/non-finite values, hindsight guards,
metric calculations, request ranges, chunk combination, startup without Parquet,
metadata without network access, and upstream error/timeout mapping. Network calls
are mocked in automated tests. The shared `get_store` dependency can be overridden
to inject synthetic data. Frontend tests cover filtering, navigation, missing
buffers, and error recovery; chart rendering is mocked.

Verification completed during development:

- **192 backend tests passed**, including inside the Linux Docker image.
- **3 frontend interaction tests passed**; frontend lint and production build passed.
- Docker built and started both services; frontend assets, Nginx proxy, backend
  health, and live Elexon requests worked without Parquet files in the image.
- Independent live Elexon comparisons for delivery dates 2 January, 15 January,
  and 1 February found no mismatches across all 24 hourly forecasts, publication
  timestamps, and corresponding actuals on each sampled day.
- The complete January purchasing period returned **744 matched hourly pairs**.
  At the default cutoff, the checked period had MAE approximately **2,022.47 MW**,
  RMSE **2,497.41 MW**, and bias **+1,745.94 MW**. These are historical observations
  from the verification run and can change if Elexon revises its records.

These checks do not establish public deployment availability or constitute visual
browser verification. Deployment and public-link access checks remain pending.
Vercel CLI 65.3.1 local-services verification also passed: the dashboard HTML and
React module returned 200, `/api/meta` returned 200, a live 2 January forecast
returned 24 hourly points, and an unknown API route returned the backend's 404.

## AI assistance and third-party attribution

**AI tools were used in this project.** OpenAI ChatGPT/Codex assisted with code
inspection, implementation, frontend integration, test creation, debugging,
Docker validation, live-data comparisons, and documentation. AI-assisted output
was checked through automated tests, builds, and live API comparisons as described
above. Generated or mocked values are not used as production Elexon data.

UI components and base styling were adapted from
[TailAdmin's free React Tailwind dashboard](https://github.com/TailAdmin/free-react-tailwind-admin-dashboard).
The imported components' source attribution and MIT license are preserved in
`frontend/src/vendor/tailadmin/`. Contains BMRS data; Elexon remains the source of
the generation records linked above.
