import { useEffect, useState } from 'react'
import Chart from 'react-apexcharts'
import Card from './vendor/tailadmin/ComponentCard'
import Button from './vendor/tailadmin/Button'
import Badge from './vendor/tailadmin/Badge'
import './App.css'

const fmt = (value, digits = 0) => value == null ? '—' : Number(value).toLocaleString('en-GB', { maximumFractionDigits: digits })
const time = (value) => new Date(value).toLocaleTimeString('en-GB', { timeZone: 'Europe/London', hour: '2-digit', minute: '2-digit' })
async function api(path, signal) {
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}${path}`, { signal })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status}). Check the backend and date range.`)
  }
  return response.json()
}
function Plot({ series, categories, type = 'line', dark }) {
  return <Chart type={type} height={300} series={series} options={{ chart: { toolbar: { show: true }, background: 'transparent', fontFamily: 'inherit', animations: { enabled: false } }, theme: { mode: dark ? 'dark' : 'light' }, colors: ['#465fff', '#12b76a', '#f79009'], stroke: { width: type === 'bar' ? 0 : 3, curve: 'straight', dashArray: [0, 5] }, dataLabels: { enabled: false }, grid: { borderColor: dark ? '#344054' : '#f2f4f7' }, xaxis: { categories, tickAmount: 8 }, yaxis: { title: { text: 'MW' }, labels: { formatter: (v) => fmt(v) } }, tooltip: { y: { formatter: (v) => `${fmt(v, 1)} MW` } }, legend: { position: 'top', horizontalAlign: 'left' }, noData: { text: 'No matched data for this selection' } }} />
}
function exportCsv(data) {
  const rows = [['Delivery time (UTC)', 'Published (UTC)', 'Horizon (hours)', 'Forecast (MW)', 'Actual (MW)'], ...data.points.map(p => [p.start_time, p.publish_time, p.horizon_hours, p.forecast_mw, p.actual_mw])]
  const url = URL.createObjectURL(new Blob([rows.map(r => r.map(v => `"${String(v ?? '').replaceAll('"', '""')}"`).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a'); a.href = url; a.download = `wind-forecast-${data.delivery_date}.csv`; a.click(); URL.revokeObjectURL(url)
}
export default function App() {
  const [page, setPage] = useState('Forecast overview')
  const [dark, setDark] = useState(() => localStorage.getItem('wind-theme') === 'dark')
  const [menu, setMenu] = useState(false)
  const [meta, setMeta] = useState(null)
  const [filters, setFilters] = useState(null)
  const [draft, setDraft] = useState(null)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  useEffect(() => { document.documentElement.classList.toggle('dark', dark); localStorage.setItem('wind-theme', dark ? 'dark' : 'light') }, [dark])
  useEffect(() => {
    const controller = new AbortController()
    api('/meta', controller.signal).then(m => {
      setMeta(m)
      const initial = { date: m.delivery_start, start: m.delivery_start, end: m.delivery_end, cutoff: m.default_cutoff }
      setFilters(initial); setDraft(initial)
    }).catch(e => { if (e.name !== 'AbortError') { setError(`Cannot connect to the API. ${e.message}`); setLoading(false) } })
    return () => controller.abort()
  }, [revision])
  useEffect(() => {
    if (!filters) return
    const controller = new AbortController()
    const run = async () => {
      setLoading(true); setError(''); setData(null)
      try {
        if (page === 'Forecast overview') {
          setData(await api(`/forecast?${new URLSearchParams({ delivery_date: filters.date, cutoff: filters.cutoff })}`, controller.signal))
        } else {
          const query = new URLSearchParams({ start: filters.start, end: filters.end, cutoff: filters.cutoff })
          const results = await Promise.all(['summary', 'by-hour', 'by-horizon', 'error-distribution', 'safety-buffer'].map(p => api(`/metrics/${p}?${query}`, controller.signal)))
          setData({ summary: results[0], hours: results[1], horizons: results[2], distribution: results[3], safety: results[4] })
        }
      } catch (e) { if (e.name !== 'AbortError') setError(e.message) }
      finally { if (!controller.signal.aborted) setLoading(false) }
    }
    run()
    return () => controller.abort()
  }, [filters, page])
  const forecast = page === 'Forecast overview'
  const updateDraft = (key, value) => setDraft({ ...draft, [key]: value })
  const metrics = forecast ? [ ['Average forecast', data?.kpis?.avg_mw, 'MW'], ['Peak generation', data?.kpis?.peak_mw, 'MW'], ['Minimum generation', data?.kpis?.min_mw, 'MW'], ['Buffered average', data?.kpis?.safe_avg_mw, 'MW'] ] : [['Mean absolute error', data?.summary?.mae, 'MW'], ['Root mean square error', data?.summary?.rmse, 'MW'], ['Forecast bias', data?.summary?.bias, 'MW'], ['Matched observations', data?.summary?.n, 'points']]
  return <div className="app-shell">
    <aside className={`sidebar ${menu ? 'open' : ''}`}>
      <a className="brand" href="#" onClick={e => { e.preventDefault(); setPage('Forecast overview') }}><span className="brand-icon">&#8803;</span> WindSight<span className="brand-dot">.</span></a>
      <div className="workspace"><span className="workspace-icon">W</span><div>Wind intelligence<small>GB electricity market</small></div><Badge size="sm">UK</Badge></div>
      <p className="nav-caption">WORKSPACE</p>
      {['Forecast overview', 'Accuracy analytics'].map((name, i) => <button key={name} className={`nav-item ${page === name ? 'active' : ''}`} onClick={() => { setPage(name); setMenu(false) }}><span>{i ? '\u25a5' : '\u25a6'}</span>{name}</button>)}
      <div className="sidebar-note"><span className="note-icon">&#8599;</span><h3>Decisions, with context.</h3><p>Explore the forecast available at your purchasing cutoff and compare it with actual generation.</p><Badge color="success">ELEXON data</Badge></div>
      <div className="sidebar-footer">Powered by TailAdmin <span>v1.0</span></div>
    </aside>
    {menu && <button className="backdrop" aria-label="Close navigation" onClick={() => setMenu(false)} />}
    <div className="main-area"><header><div className="header-left"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMenu(!menu)}>&#9776;</button><span className="header-label">Wind generation intelligence</span></div><div className="header-right"><Badge color={meta ? 'success' : 'warning'} size="sm">{meta ? 'API connected' : 'Connecting to API'}</Badge><button className="icon-button" aria-label={dark ? 'Use light theme' : 'Use dark theme'} onClick={() => setDark(!dark)}>{dark ? '\u2600' : '\u263e'}</button><span className="avatar">WS</span></div></header>
    <main><div className="page-heading"><div><p className="eyebrow">ENERGY / {forecast ? 'FORECAST' : 'PERFORMANCE'}</p><h1>{page}</h1><p>{forecast ? 'A clearer view of tomorrow’s wind generation.' : 'Understand how forecasts performed against actual generation.'}</p></div><div className="heading-actions"><Badge color="light">Historical · January 2026</Badge>{forecast && <Button variant="outline" size="sm" disabled={loading || !data?.points?.length} onClick={() => exportCsv(data)}>&#8595; Export CSV</Button>}</div></div>
    {draft && <form className="filter-bar" onSubmit={e => { e.preventDefault(); setFilters({ ...draft }) }}>
      {forecast ? <label>Delivery date<input required type="date" min={meta.delivery_start} max={meta.delivery_end} value={draft.date} onChange={e => updateDraft('date', e.target.value)} /></label> : <><label>From delivery date<input required type="date" min={meta.delivery_start} max={draft.end} value={draft.start} onChange={e => updateDraft('start', e.target.value)} /></label><label>To delivery date<input required type="date" min={draft.start} max={meta.delivery_end} value={draft.end} onChange={e => updateDraft('end', e.target.value)} /></label></>}
      <label>Purchasing cutoff · London<input required type="time" value={draft.cutoff} onChange={e => updateDraft('cutoff', e.target.value)} /></label><Button size="sm" disabled={loading}>Apply filters &#8594;</Button><p>Forecasts published by the cutoff<br />on the previous calendar day.</p>
    </form>}
    {error && <div className="error-box" role="alert"><strong>Unable to load this view</strong><p>{error}</p><Button size="sm" onClick={() => meta ? setFilters({ ...filters }) : setRevision(v => v + 1)}>Try again</Button></div>}
    {loading && <div className="loading" role="status"><span className="spinner" /> Loading wind generation data…</div>}
    {!loading && !error && data && (forecast ? data.kpis : data.summary) && <>
      <div className="stats-grid">{metrics.map(([label, value, unit], i) => <div className="stat" key={label}><div className="stat-top"><span className="stat-icon">{['\u224b', '\u2197', '\u2198', '\u25ce'][i]}</span><span>{forecast ? 'Delivery day' : 'Selected period'}</span></div><p>{label}</p><div className="stat-value">{fmt(value, 1)} <small>{unit}</small></div></div>)}</div>
      {forecast ? <>
        <div className="chart-layout"><Card title="Generation forecast" desc={`Delivery ${data.delivery_date} · Purchasing ${data.purchasing_date} · Europe/London`}><Plot dark={dark} categories={data.points.map(p => time(p.start_time))} series={[{ name: 'Forecast', data: data.points.map(p => p.forecast_mw) }, { name: 'Actual (retrospective)', data: data.points.map(p => p.actual_mw) }]} /></Card><div className="decision-panel"><Badge>DECISION CONTEXT</Badge><h2>A measured approach<br />to uncertainty.</h2><p>Empirical 95% error buffer</p><div className="buffer-value">{fmt(data.buffer_mw_p95, 1)} <small>MW</small></div><hr /><dl><div><dt>Historical matches</dt><dd>{fmt(data.buffer_sample_count)}</dd></div><div><dt>Decision cutoff (UTC)</dt><dd>{new Date(data.cutoff_utc).toLocaleString('en-GB', { timeZone: 'UTC' })}</dd></div></dl><p className="context-note">Uses completed delivery days strictly before the purchasing day. {data.buffer_mw_p95 == null ? 'Insufficient history: buffered average is unavailable.' : 'Historical coverage does not guarantee future coverage.'}</p></div></div>
        <Card title="Hourly delivery detail" desc="Native hourly forecast points. Actual values are matched by timestamp; missing values remain empty."><div className="table-scroll"><table><thead><tr>{['Delivery · London', 'Forecast MW', 'Actual MW', 'Error MW¹', 'Horizon', 'Published · UTC'].map(t => <th key={t}>{t}</th>)}</tr></thead><tbody>{data.points.map(p => <tr key={p.start_time}><td>{time(p.start_time)}</td><td>{fmt(p.forecast_mw, 1)}</td><td>{fmt(p.actual_mw, 1)}</td><td>{fmt(p.forecast_mw != null && p.actual_mw != null ? p.forecast_mw - p.actual_mw : null, 1)}</td><td>{fmt(p.horizon_hours, 1)} h</td><td>{new Date(p.publish_time).toLocaleString('en-GB', { timeZone: 'UTC' })}</td></tr>)}</tbody></table>{!data.points.length && <p>No eligible forecast points.</p>}</div><p className="fine-print">¹ Signed error = forecast - actual.</p></Card>
      </> : <>
        {!data.summary.n && <div className="empty-state">No matching forecast and actual observations for this period and cutoff. Choose another selection.</div>}
        <div className="analytics-grid"><Card title="Error by delivery hour" desc="Mean absolute error and signed bias · Europe/London"><Plot dark={dark} type="bar" categories={data.hours.map(p => `${p.hour}:00`)} series={[{ name: 'MAE', data: data.hours.map(p => p.mae) }, { name: 'Bias', data: data.hours.map(p => p.bias) }]} /></Card><Card title="Error by forecast horizon" desc="Grouped in six-hour intervals"><Plot dark={dark} type="bar" categories={data.horizons.map(p => p.horizon_bin)} series={[{ name: 'MAE', data: data.horizons.map(p => p.mae) }, { name: 'Bias', data: data.horizons.map(p => p.bias) }]} /></Card></div>
        <Card title="Signed error distribution" desc="Forecast minus actual generation · MW"><Chart type="bar" height={260} series={[{ name: 'Observations', data: data.distribution.counts }]} options={{ chart: { background: 'transparent', toolbar: { show: true } }, theme: { mode: dark ? 'dark' : 'light' }, colors: ['#465fff'], dataLabels: { enabled: false }, xaxis: { categories: data.distribution.counts.map((_, i) => `${fmt(data.distribution.edges[i])} to ${fmt(data.distribution.edges[i + 1])}`), tickAmount: 6 }, yaxis: { title: { text: 'Observations' } } }} /><div className="percentiles">{[['Normalized MAE', data.summary.nmae_pct, '%'], ['95th percentile absolute error', data.summary.p95_abs_error, 'MW'], ['Retrospective 95% buffer', data.safety.buffer_mw, 'MW']].map(([label, value, unit]) => <div key={label}><p>{label}</p><strong>{fmt(value, 1)} {unit}</strong></div>)}</div></Card>
      </>}
      <div className="method-note"><strong>About this analysis</strong><p>Actuals are retrospective comparisons. Actual publication times and later revisions are not tracked, so historical availability cannot be proved. {forecast ? 'The buffered average uses only earlier completed days.' : 'Metrics and the safety buffer describe the selected period retrospectively; they are distinct from the decision-view buffer.'} Actuals are half-hourly, forecasts hourly; only matching timestamps are compared, without interpolation.</p></div>
    </>}
    <footer>WindSight · Wind forecast evaluation<span>Built with TailAdmin · ELEXON FUELHH / WINDFOR</span></footer></main></div>
  </div>
}
