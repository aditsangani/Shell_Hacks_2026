import { useMemo, useState } from 'react'
import { monthYear, etTime, longDate } from '../format.js'

const SCOPE = {
  stock: { label: 'Stock-specific', color: 'var(--series-1)', lane: 'up', blurb: 'about this company' },
  sector: { label: 'Sector-wide', color: 'var(--series-2)', lane: 'up', blurb: 'about its sector' },
  market: { label: 'Market-wide', color: 'var(--series-3)', lane: 'down', blurb: 'about the market' },
}
const TIMING = {
  background: { label: 'Background', tone: 'background' },
  premarket_catalyst: { label: 'Possible pre-market catalyst', tone: 'catalyst' },
  intraday_catalyst: { label: 'Possible intraday catalyst', tone: 'catalyst' },
  reaction: { label: 'Post-session context', tone: 'reaction' },
}
const RADIUS = { high: 7, medium: 5, low: 3.5 }
const W = 1000
const PAD = 28
const AXIS_Y = 150

const VERDICT = {
  stock_specific: { label: 'Stock-specific move', tone: 'stock' },
  market_wide: { label: 'Market-wide move', tone: 'market' },
  mixed: { label: 'Mixed — partly market, partly the company', tone: 'mixed' },
  flat: { label: 'No material move', tone: 'flat' },
}

/** Spread dots within a lane so same-day articles do not stack on one another. */
function layout(events, xOf) {
  const lanes = { up: [], down: [] }
  const placed = []
  for (const e of events) {
    const lane = SCOPE[e.scope]?.lane ?? 'up'
    const taken = lanes[lane]
    // Stack upward in the top lane, downward in the bottom one.
    const step = taken.length % 3
    let x = xOf(e.pub_date)
    const y = lane === 'up' ? AXIS_Y - 34 - step * 15 : AXIS_Y + 34 + step * 15
    // Nudge right while colliding with something already in this lane.
    let guard = 0
    while (taken.some((p) => Math.abs(p.x - x) < 11 && Math.abs(p.y - y) < 11) && guard < 40) {
      x += 11
      guard += 1
    }
    taken.push({ x, y })
    placed.push({ ...e, x, y })
  }
  return placed
}

function axisTicks(begin, end) {
  const out = []
  const start = new Date(`${begin}T12:00:00Z`)
  const stop = new Date(`${end}T12:00:00Z`)
  const spanDays = (stop - start) / 86400000
  // A 5-year axis wants year marks; a 6-month axis wants months.
  if (spanDays > 400) {
    for (let y = start.getUTCFullYear(); y <= stop.getUTCFullYear(); y += 1) {
      const d = new Date(Date.UTC(y, 0, 1, 12))
      if (d >= start && d <= stop) out.push(d)
    }
  } else {
    const cur = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1, 12))
    while (cur <= stop) {
      if (cur >= start) out.push(new Date(cur))
      cur.setUTCMonth(cur.getUTCMonth() + 1)
    }
  }
  return out
}

function Plot({ tl, selected, onSelect }) {
  const { window: win, event_date: eventDate, events } = tl
  const t0 = Date.parse(`${win.begin}T12:00:00Z`)
  const t1 = Date.parse(`${win.end}T12:00:00Z`)
  const xOf = (iso) => {
    const t = Date.parse(`${iso.slice(0, 10)}T12:00:00Z`)
    const f = (t - t0) / Math.max(1, t1 - t0)
    return PAD + f * (W - PAD * 2)
  }
  const dots = useMemo(() => layout(events, xOf), [events])
  const ticks = useMemo(() => axisTicks(win.begin, win.end), [win.begin, win.end])
  const evX = xOf(eventDate)
  const move = tl.move_pct

  return (
    <div className="tl-plot-wrap">
      <svg className="tl-plot" viewBox={`0 0 ${W} 250`} role="img"
        aria-label={`Timeline of ${events.length} selected articles from ${longDate(win.begin)} to ${longDate(win.end)}, with the investigated session on ${longDate(eventDate)} marked.`}>
        {/* lanes */}
        <text x={PAD} y={AXIS_Y - 78} className="tl-lane-label">Company &amp; sector news</text>
        <text x={PAD} y={AXIS_Y + 78} className="tl-lane-label">Market news</text>
        <line x1={PAD} x2={W - PAD} y1={AXIS_Y - 84} y2={AXIS_Y - 84} className="tl-lane-rule" />
        <line x1={PAD} x2={W - PAD} y1={AXIS_Y + 84} y2={AXIS_Y + 84} className="tl-lane-rule" />

        {ticks.map((d) => (
          <g key={d.toISOString()}>
            <line x1={xOf(d.toISOString())} x2={xOf(d.toISOString())} y1={AXIS_Y - 84} y2={AXIS_Y + 84} className="tl-grid" />
            <text x={xOf(d.toISOString())} y={AXIS_Y + 104} className="tl-tick">{monthYear(d.toISOString().slice(0, 10))}</text>
          </g>
        ))}

        <line x1={PAD} x2={W - PAD} y1={AXIS_Y} y2={AXIS_Y} className="tl-axis" />

        {/* the move */}
        <line x1={evX} x2={evX} y1={AXIS_Y - 96} y2={AXIS_Y + 96} className="tl-event-line" />
        <polygon
          points={`${evX},${AXIS_Y + 96} ${evX - 7},${AXIS_Y + 110} ${evX + 7},${AXIS_Y + 110}`}
          className="tl-event-mark"
        />
        <text x={evX} y={AXIS_Y + 126} className="tl-event-label" textAnchor="middle">
          {longDate(eventDate)} · {move > 0 ? '+' : ''}{move?.toFixed(2)}%
        </text>

        {dots.map((d) => (
          <g key={d.ref} className={selected?.ref === d.ref ? 'tl-dot on' : 'tl-dot'}
            onClick={() => onSelect(selected?.ref === d.ref ? null : d)}>
            <circle cx={d.x} cy={d.y} r={RADIUS[d.significance] + 7} fill="transparent" />
            <circle cx={d.x} cy={d.y} r={RADIUS[d.significance]} fill={SCOPE[d.scope]?.color ?? 'var(--series-1)'} />
          </g>
        ))}
      </svg>

      <div className="tl-legend">
        {Object.entries(SCOPE).map(([k, v]) => (
          <span key={k}><span className="swatch" style={{ background: v.color }} />{v.label}</span>
        ))}
        <span className="tl-legend-sep" />
        <span>Dot size = significance · click a dot for detail</span>
      </div>
    </div>
  )
}

function Verdict({ tl }) {
  const v = VERDICT[tl.verdict.verdict] ?? VERDICT.mixed
  const inv = tl.against_market
  return (
    <div className={`tl-verdict ${v.tone}`}>
      <div className="tl-verdict-head">
        <span className="tl-verdict-label">{v.label}</span>
        <span className="tl-verdict-share">
          {Math.round(tl.verdict.share * 100)}% of the move is not explained by the market
        </span>
      </div>
      <div className="meter" role="img"
        aria-label={`${Math.round(tl.verdict.share * 100)} percent of the move is idiosyncratic rather than market-driven`}>
        <div className="meter-idio" style={{ width: `${Math.max(2, tl.verdict.share * 100)}%` }} />
      </div>
      <p className="sub" style={{ margin: '10px 0 0' }}>
        Beta-adjusted against {tl.market}, {Math.round(tl.verdict.share * 100)}% of the{' '}
        {Math.abs(tl.move_pct).toFixed(2)}% move is {tl.symbol}-specific.
        {inv && ' The market was moving against it, which makes the company-specific part larger still.'}
        {tl.verdict_note && <> Gemini: {tl.verdict_note}</>}
      </p>
    </div>
  )
}

function EventCard({ e, onClose }) {
  const s = SCOPE[e.scope] ?? SCOPE.stock
  const timing = TIMING[e.timing_role]
  return (
    <div className="tl-detail" style={{ borderLeftColor: s.color }}>
      <button className="tl-close" onClick={onClose} aria-label="Close detail">×</button>
      <div className="tl-detail-meta">
        <span className="chip" style={{ marginLeft: 0 }}>{e.ref}</span>
        <span className="chip" style={{ marginLeft: 0, background: s.color, color: '#fff' }}>{s.label}</span>
        {timing && <span className={`chip timing-chip ${timing.tone}`}>{timing.label}</span>}
        <span className="chip" style={{ marginLeft: 0 }}>{e.significance} significance</span>
        <span className="tl-detail-date">{etTime(e.pub_date)}</span>
      </div>
      <a className="tl-detail-headline" href={e.url} target="_blank" rel="noreferrer">{e.headline}</a>
      <p className="sub" style={{ margin: '8px 0 0' }}>{e.why}</p>
      {e.thesis && <p className="sub" style={{ margin: '4px 0 0' }}>{e.thesis}</p>}
      {e.snippet && <p className="caveat" style={{ margin: '8px 0 0' }}>{e.snippet}</p>}
    </div>
  )
}

export default function Timeline({ tl, loading, error, onWarm, warming, onBack }) {
  const [selected, setSelected] = useState(null)

  if (error) {
    return (
      <div className="page">
        <button className="ghost" onClick={onBack}>← Back to the investigation</button>
        <div className="card"><p className="error">{error}</p></div>
      </div>
    )
  }
  if (loading || !tl) {
    return (
      <div className="page">
        <button className="ghost" onClick={onBack}>← Back to the investigation</button>
        <div className="card"><p className="loading">Building the evidence timeline…</p></div>
      </div>
    )
  }

  const counts = tl.events.reduce((a, e) => ({ ...a, [e.scope]: (a[e.scope] ?? 0) + 1 }), {})

  return (
    <div className="page">
      <div className="toolbar">
        <button className="ghost" onClick={onBack}>← Back to the investigation</button>
        <span className="tl-title">Evidence timeline · {tl.symbol}</span>
        {!tl.warming && (
          <button className="ghost" onClick={onWarm} disabled={warming}>
            {tl.pool_size === 0 ? 'Load articles' : tl.pending_requests > 0 ? 'Finish sampling' : '↻ Re-sample'}
          </button>
        )}
      </div>

      {tl.warming && (
        <div className="tl-progress" role="status">
          <span className="tl-spin" aria-hidden="true" />
          <span>
            Sampling New York Times coverage in the background
            {tl.pending_requests > 0 && <> — {tl.pending_requests} request{tl.pending_requests === 1 ? '' : 's'} left</>}
            . Rate-limited to 5/min, so this takes under a minute. The page updates itself.
          </span>
        </div>
      )}

      <section className="card">
        <div className="step">What was published, and what it implies</div>
        <h2>{tl.company} · {tl.event_label}</h2>
        <p className="sub">
          {tl.pool_size} New York Times article{tl.pool_size === 1 ? '' : 's'} sampled across the{' '}
          {tl.window.label} before the session{window_tail(tl)}.
          {tl.triage_note
            ? ' Relevance classification is pending.'
            : ` Gemini kept ${tl.events.length} as bearing on the move.`}
          {counts.stock ? ` ${counts.stock} company-specific.` : ''}
          {counts.market ? ` ${counts.market} market-wide.` : ''}
          {counts.sector ? ` ${counts.sector} sector-wide.` : ''}
        </p>

        {tl.pool_size === 0 ? (
          <div className="tl-cold">
            <p className="loading">
              {tl.warming
                ? 'Sampling in the background…'
                : <>No articles sampled yet. This needs <code>NYT_API_KEY</code> and <code>GEMINI_API_KEY</code> set.</>}
            </p>
            <button className="primary" onClick={onWarm} disabled={warming}>
              {warming ? 'Sampling…' : 'Sample articles now'}
            </button>
            <p className="caveat">
              A {tl.window.label} window costs one rate-limited NYT request per 6-month chunk
              (up to {Math.max(1, Math.round(tl.window.days / 183))} requests), so this can take a
              minute. Pre-warm it with <code>python ingest.py {tl.symbol} {tl.mode} --timeline</code>.
            </p>
          </div>
        ) : (
          <>
            {(tl.quota_exhausted || tl.triage_note) && (
              <div className="tl-quota">
                <b>Showing {tl.pool_size} articles, untriaged</b>
                {tl.triage_note ? ` ${tl.triage_note}` : ''}
                {tl.mode && <> Re-run <code>ingest.py {tl.symbol} {tl.mode} --timeline</code> when
                the quota resets.</>}
              </div>
            )}
            <Verdict tl={tl} />
            {!tl.triage_note && (
              <>
                {tl.cause_conclusion && (
                  <div className="tl-conclusion">
                    <b>Timing conclusion</b>
                    <span>{tl.cause_conclusion}</span>
                  </div>
                )}
                <Plot tl={tl} selected={selected} onSelect={setSelected} />
                {selected
                  ? <EventCard e={selected} onClose={() => setSelected(null)} />
                  : <p className="caveat">Select a dot to read the article and why it matters.</p>}
              </>
            )}
          </>
        )}
        {tl.caveat && <p className="caveat">{tl.caveat}</p>}
      </section>

      {tl.events.length > 0 && (
        <section className="card">
          <div className="step">In date order</div>
          <ul className="tl-list">
            {tl.events.map((e) => (
              <li key={e.ref} style={{ borderLeftColor: SCOPE[e.scope]?.color }}>
                <div className="tl-list-meta">
                  <span className="chip" style={{ marginLeft: 0 }}>{e.ref}</span>
                  <span className="tl-list-date">{etTime(e.pub_date)}</span>
                  <span className="chip" style={{ marginLeft: 0, color: SCOPE[e.scope]?.color }}>{SCOPE[e.scope]?.label}</span>
                  {TIMING[e.timing_role] && (
                    <span className={`chip timing-chip ${TIMING[e.timing_role].tone}`}>
                      {TIMING[e.timing_role].label}
                    </span>
                  )}
                </div>
                <a href={e.url} target="_blank" rel="noreferrer">{e.headline}</a>
                <div className="tl-list-why">{e.why}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="disclaimer">
        Historical observation only — not investment advice. Article selection and reasoning by
        Gemini, grounded in the coverage shown. Publication timing and causal eligibility are
        enforced by market-session rules; every article links to its source.
      </p>
    </div>
  )
}

function window_tail(tl) {
  return tl.mode === 'unusual'
    ? ' (the window widens to 5 years when investigating an unusual move)'
    : ' (a 6-month look-back)'
}
