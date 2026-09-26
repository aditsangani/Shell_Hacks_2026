import { pct, longDate } from '../format.js'

const Cell = ({ v }) => <td className={v == null ? '' : v >= 0 ? 'up' : 'down'}>{pct(v)}</td>

export default function SimilarMoves({ inv }) {
  return (
    <section className="card">
      <div className="step">4 · Has this happened before?</div>
      <h2>Closest past moves and what followed</h2>
      <p className="sub">
        The {inv.similar.length} days in the last 5 years closest in size to {pct(inv.move.move_pct)}.
        This is historical observation, not a prediction.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Date</th><th>Move</th><th>Next day</th><th>+5 days</th><th>+20 days</th></tr>
          </thead>
          <tbody>
            <tr className="event">
              <td>{longDate(inv.event_date)} (this move)</td>
              <td>{pct(inv.move.move_pct)}</td><td>—</td><td>—</td><td>—</td>
            </tr>
            {inv.similar.map((s) => (
              <tr key={s.date}>
                <td>{longDate(s.date)}</td>
                <td>{pct(s.move_pct)}</td>
                <Cell v={s.d1} /><Cell v={s.d5} /><Cell v={s.d20} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="caveat">Returns measured from the close of each move day.</p>
    </section>
  )
}
