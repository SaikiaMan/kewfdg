// @vitest-environment jsdom
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App'
vi.mock('react-apexcharts', () => ({ default: () => <div>Chart</div> }))
const metadata = { delivery_start: '2026-01-02', delivery_end: '2026-02-01', default_cutoff: '09:00' }
const forecast = { delivery_date: '2026-01-02', purchasing_date: '2026-01-01', cutoff_utc: '2026-01-01T09:00:00Z', points: [{ start_time: '2026-01-02T00:00:00Z', publish_time: '2026-01-01T08:00:00Z', forecast_mw: 100, actual_mw: 90, horizon_hours: 16 }], kpis: { avg_mw: 100, peak_mw: 100, min_mw: 100, safe_avg_mw: null }, buffer_sample_count: 0, buffer_mw_p95: null }
let failForecast
beforeEach(() => {
  failForecast = false
  localStorage.clear()
  vi.stubGlobal('fetch', vi.fn(async url => {
    let body = metadata
    let ok = true
    if (url.includes('/forecast?')) { body = failForecast ? { detail: 'No forecast available at the decision cutoff' } : forecast; ok = !failForecast }
    else if (url.includes('/summary?')) body = { n: 1, mae: 10, rmse: 10, bias: 10 }
    else if (url.includes('/by-hour?')) body = [{ hour: 0, mae: 10, bias: 10, n: 1 }]
    else if (url.includes('/by-horizon?')) body = [{ horizon_bin: '12-18', mae: 10, bias: 10, n: 1 }]
    else if (url.includes('/error-distribution?')) body = { counts: [1], edges: [5, 15] }
    else if (url.includes('/safety-buffer?')) body = { confidence: .95, buffer_mw: 10 }
    return { ok, json: async () => body }
  }))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })
test('loads forecasts, preserves missing buffer, and applies cutoff and delivery filters', async () => {
  render(<App />)
  await screen.findByText('Hourly delivery detail')
  expect(screen.getByText(/Insufficient history/)).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Delivery date'), { target: { value: '2026-01-03' } })
  fireEvent.change(screen.getByLabelText('Purchasing cutoff · London'), { target: { value: '10:30' } })
  fireEvent.click(screen.getByRole('button', { name: 'Apply filters →' }))
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/forecast?delivery_date=2026-01-03&cutoff=10%3A30', expect.anything()))
})
test('switches between analytics and forecast without rendering stale response shapes', async () => {
  render(<App />)
  await screen.findByText('Hourly delivery detail')
  fireEvent.click(screen.getByRole('button', { name: /Accuracy analytics/ }))
  await screen.findByText('Signed error distribution')
  expect(screen.getByText('Matched observations')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /Forecast overview/ }))
  await screen.findByText('Hourly delivery detail')
})
test('shows backend errors and recovers on retry', async () => {
  failForecast = true
  render(<App />)
  await screen.findByRole('alert')
  expect(screen.getByText('No forecast available at the decision cutoff')).toBeTruthy()
  failForecast = false
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  await screen.findByText('Hourly delivery detail')
})
