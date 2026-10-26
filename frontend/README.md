# WindSight frontend

React dashboard built with TailAdmin components and Tailwind CSS. Source attribution
and the upstream MIT license are in `src/vendor/tailadmin/`.

## Run locally

Use Python 3.11+ for the backend. From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to localhost:8000.
Set `VITE_API_BASE_URL` before building to target a different API (include `/api`).

## Docker

From the project root, run `docker compose up --build`, then open
http://localhost:8080. Nginx forwards `/api` to the backend service.
The backend fetches Elexon data on demand; Parquet files are not required.
The frontend waits for backend health before starting. Keep Docker Desktop running,
and leave ports 8000 and 8080 free before starting Compose.

## Features and data limits

- Forecast overview: delivery date, purchasing cutoff, hourly chart and table,
  generation KPIs, historical decision buffer, CSV export.
- Accuracy analytics: date range and cutoff, summary metrics, hourly and horizon
  errors, error histogram, retrospective safety buffer.
- Responsive navigation, persistent light/dark theme, loading and error recovery.

The API supports delivery dates 2 January–1 February 2026 and fetches Elexon records
on demand. The initial view uses 2 January. An allowed date may still have no
eligible forecast within the configured publication lookback. Missing actuals and
buffers remain missing. Actuals are retrospective; buffer limitations appear in
the UI. See the [main README](../README.md) for architecture, data assumptions,
configuration, verification results, and AI-use disclosure.

## Validation

```powershell
npm run test
npm run lint
npm run build
# From backend, with the virtual environment active:
python -m pytest -q
```

Frontend interaction tests cover API requests, filters, navigation, missing buffer
handling, and retry after a backend error. Chart rendering is mocked in these tests.
