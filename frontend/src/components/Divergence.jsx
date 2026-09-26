import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { pct, etTime, etDate } from '../format.js'

function SameDayBars({ inv }) {
  const d = inv.divergence
  const rows = [
    { sym: inv.symbol, v: d.ticker_pct, color: 'var(--series-1)' },
    ...(inv.sector_known ? [{ sym: inv.sector_etf, v: d.sector_pct, color: 'var(--series-2)' }] : []),
    { sym: inv.market, v: d.market_pct, color: 'var(--series-3)' },
  ]
  const max = Math.max(...rows.map((r) => Math.abs(r.v)))
  return (
    <div className="cmp">
      {rows.map((r) => (
        <div key={r.sym} style={{ display: 'contents' }}>
          <div className="sym"><span className="swatch" style={{ background: r.color }} />{r.sym}</div>
          <div className="track"><div className="bar" style={{ width: `${(Math.abs(r.v) / max) * 100}%`, background: r.color }} /></div>
          <div className="val">{pct(r.v)}</div>
        </div>
      ))}
    </div>
  )
}

function ChartTooltip({ active, payload, series }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="tooltip">
      <div className="t">{etTime(p.time)}</div>
      {series.map((s) => (
        <div className="row" key={s.key}>
          <span className="swatch" style={{ background: s.color }} />{s.key}<b>{pct(p[s.key])}</b>
        </div>
      ))}
      {p.news && <div className="t" style={{ marginTop: 4 }}>News: {p.news}</div>}
    </div>
  )
}

export default function Divergence({ inv }) {
  const d = inv.divergence
  const series = [
    { key: inv.symbol, color: 'var(--series-1)' },
    ...(inv.sector_known ? [{ key: inv.sector_etf, color: 'var(--series-2)' }] : []),
    { key: inv.market, color: 'var(--series-3)' },
  ]

  // Category axis by bar index so overnight/weekend gaps don't stretch the chart.
  const markers = {}
  for (const h of inv.headlines) if (h.chart_time) (markers[h.chart_time] ??= []).push(h.id)
  const data = inv.chart.map((p, i) => ({ ...p, i, news: markers[p.time]?.join(', ') }))
  const sessionStarts = data.filter((p, i) => i === 0 || etDate(p.time) !== etDate(data[i - 1].time))
  const last = data[data.length - 1]

  const endLabel = (key) => (props) =>
    props.index === data.length - 1 ? (
      <text x={props.x + 6} y={props.y} dy={4} fontSize={12} fill="var(--text-secondary)">{key}</text>
    ) : null

  return (
    <section id="market-context" className="card insight-card divergence-card">
      <div className="step">3 · Company-specific or market-wide?</div>
      <h2>
        {inv.sector_known
          ? `${d.excess_vs_sector > 0 ? 'Outperformed' : 'Underperformed'} its sector by ${Math.abs(d.excess_vs_sector).toFixed(1)} pts`
          : `${d.excess_vs_market > 0 ? 'Outperformed' : 'Underperformed'} the market by ${Math.abs(d.excess_vs_market).toFixed(1)} pts`}
      </h2>
      <p className="sub">
        With a 1-year beta of {d.beta_1y} to {inv.market}, the market alone implies {pct(d.beta_expected_pct)}.
        That leaves <b>{pct(d.idiosyncratic_pct)}</b> specific to {inv.symbol}.
        {inv.sector_known
          ? ` (${inv.symbol} is a large holding in ${inv.sector_etf}, so some of the sector's move is ${inv.symbol} itself.)`
          : ` ${inv.symbol}'s sector isn't in our comparison map, so only the market proxy is shown.`}
      </p>

      <SameDayBars inv={inv} />

      {data.length === 0 ? (
        <p className="caveat">{inv.chart_caveat || 'No intraday data available for this session.'}</p>
      ) : (
        <>
          <div className="legend">
            {series.map((s) => (
              <span key={s.key}><span className="swatch" style={{ background: s.color }} />{s.key}</span>
            ))}
            {Object.keys(markers).length > 0 && <span><span className="news-key" />NYT headline (H#)</span>}
          </div>
          <div style={{ width: '100%', height: 320 }} role="img"
            aria-label={`Intraday % change vs prior close for ${series.map((s) => s.key).join(', ')}, with news markers.`}>
            <ResponsiveContainer>
              <LineChart data={data} margin={{ top: 24, right: 48, left: 0, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--grid)" />
                <XAxis dataKey="i" type="number" domain={[0, last.i]} ticks={sessionStarts.map((p) => p.i)}
                  tickFormatter={(i) => etDate(data[i].time)} tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                  axisLine={{ stroke: 'var(--axis)' }} tickLine={false} />
                <YAxis tickFormatter={(v) => `${v}%`} tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
                  axisLine={false} tickLine={false} width={48} />
                <ReferenceLine y={0} stroke="var(--axis)" />
                {Object.entries(markers).map(([t, ids]) => {
                  const p = data.find((x) => x.time === t)
                  return p ? (
                    <ReferenceLine key={t} x={p.i} stroke="var(--text-muted)" strokeDasharray="3 3"
                      label={{ value: ids.length > 2 ? `${ids[0]}–${ids[ids.length - 1]}` : ids.join(','), position: 'top', fill: 'var(--text-secondary)', fontSize: 11 }} />
                  ) : null
                })}
                <Tooltip content={<ChartTooltip series={series} />} cursor={{ stroke: 'var(--axis)' }} />
                {series.map((s) => (
                  <Line key={s.key} dataKey={s.key} stroke={s.color} strokeWidth={2} dot={false}
                    label={endLabel(s.key)} isAnimationActive={false} activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="caveat">
            5-minute bars, % change vs the close before the session shown.
            {inv.chart_source === 'tiger_data' ? ' Served from a Tiger Data continuous aggregate. ' : ''}
            {Object.keys(markers).length > 0 ? 'Headlines are pinned to the first bar after publication (when the market could react).' : ''}
          </p>
        </>
      )}
      {inv.chart_caveat && data.length > 0 && <p className="caveat">{inv.chart_caveat}</p>}
    </section>
  )
}
