import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { pct, longDate } from '../format.js'

function BinTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const { x0, count } = payload[0].payload
  return (
    <div className="tooltip">
      <div className="t">{x0 >= 0 ? '+' : ''}{x0}% to {x0 + 1 >= 0 ? '+' : ''}{x0 + 1}%</div>
      <b>{count}</b> trading days
    </div>
  )
}

export default function Unusualness({ inv }) {
  const m = inv.move
  const eventBin = Math.floor(m.move_pct)
  const years = Math.round(m.history_days / 252)
  // √ heights so the 1-2 day tail bins stay visible next to the ~300-day center bins.
  const bins = m.histogram.map((b) => ({ ...b, h: Math.sqrt(b.count) }))

  return (
    <section id="unusualness" className="card insight-card unusualness-card">
      <div className="step">1 · How unusual</div>
      <h2>
        <span className="big">{m.percentile}%</span>
      </h2>
      <p className="sub">
        This move was bigger than {m.percentile}% of {inv.symbol}'s daily moves over the past {years} years
        ({m.history_days.toLocaleString()} trading days).
      </p>

      <div className="tiles">
        <div className="tile"><div className="label">Z-score</div><div className="value">{m.z_score.toFixed(1)}σ</div></div>
        <div className="tile"><div className="label">Typical daily move</div><div className="value">±{m.typical_abs_move}%</div></div>
        <div className="tile"><div className="label">Days this big or bigger</div><div className="value">{m.bigger_moves_count}</div></div>
        <div className="tile">
          <div className="label">Largest {m.move_pct > 0 ? 'gain' : 'drop'} since</div>
          <div className="value">{m.largest_since ? longDate(m.largest_since) : '—'}</div>
          {m.largest_since && <div className="label">{pct(m.largest_since_move)} that day</div>}
        </div>
      </div>

      <div style={{ width: '100%', height: 180 }} role="img"
        aria-label={`Distribution of ${inv.symbol} daily moves over ${years} years; the event day sits in the far tail.`}>
        <ResponsiveContainer>
          <BarChart data={bins} margin={{ top: 20, right: 56, left: 16, bottom: 0 }} barCategoryGap={2}>
            <XAxis dataKey="x0" tickFormatter={(v) => `${v}%`} interval={3} tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
              axisLine={{ stroke: 'var(--axis)' }} tickLine={false} />
            <YAxis hide />
            <Tooltip content={<BinTooltip />} cursor={{ fill: 'var(--wash)' }} />
            <ReferenceLine x={eventBin} stroke="transparent"
              label={{ value: `${inv.event_label.split(',')[0]} ${pct(m.move_pct)}`, position: 'top', fill: 'var(--text-primary)', fontSize: 12, fontWeight: 600 }} />
            <Bar dataKey="h" radius={[4, 4, 0, 0]} minPointSize={2} isAnimationActive={false}>
              {bins.map((b) => (
                <Cell key={b.x0} fill={b.x0 === eventBin ? 'var(--series-1)' : 'var(--muted-bar)'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="caveat">Daily close-to-close moves, 1% bins (√ height so the tails stay visible). Highlighted: the event day.</p>
    </section>
  )
}
