import { etTime } from '../format.js'

export default function News({ inv }) {
  const items = inv.headlines
  return (
    <section className="card insight-card news-card">
      <div className="step">3 · What was published</div>
      <h2>{items.length} NYT headline{items.length === 1 ? '' : 's'} around the move</h2>
      {items.length === 0 ? (
        <p className="loading">
          No New York Times coverage matched {inv.symbol} in the three days around this session.
          Headlines load when <code>NYT_API_KEY</code> is set; they also depend on the NYT
          archive having covered this company that week.
        </p>
      ) : (
        <ul className="news">
          {items.map((h) => (
            <li key={h.id}>
              <div className="hid">{h.id}</div>
              <div>
                <div className="meta">{etTime(h.pub_date)}<span className="chip">{h.timing}</span></div>
                <a href={h.url} target="_blank" rel="noreferrer">{h.headline}</a>
                {h.snippet && <div className="snippet">{h.snippet}</div>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
