export default function Conclusion({ conclusion, timelineError }) {
  if (!conclusion) return null

  const displayed = timelineError
    ? {
        ...conclusion,
        evidence_status: 'untriaged',
        evidence: 'The evidence timeline could not be loaded. No claim about a published catalyst is made.',
      }
    : conclusion

  const evidenceLabels = {
    pending: 'Evidence pending',
    untriaged: 'Triage unavailable',
    possible_catalyst: 'Possible catalyst evidence',
    no_evidence: 'No relevant coverage found',
    no_published_catalyst: 'No published catalyst identified',
  }

  return (
    <section id="conclusion" className="card insight-card conclusion-card">
      <div className="step">5 · Investigation conclusion</div>
      <div className="conclusion-heading">
        <h2>{displayed.title}</h2>
        <span className={`conclusion-status ${displayed.evidence_status}`}>
          {evidenceLabels[displayed.evidence_status] || 'Computed summary'}
        </span>
      </div>

      <div className="conclusion-answer">
        <span>Answer</span>
        <p>{displayed.answer}</p>
      </div>

      <div className="conclusion-points">
        <div><span>Size of move</span><p>{displayed.move}</p></div>
        <div><span>Market context</span><p>{displayed.market_context}</p></div>
        <div><span>Published evidence</span><p>{displayed.evidence}</p></div>
        <div><span>Historical comparison</span><p>{displayed.history}</p></div>
      </div>

      <p className="caveat conclusion-caveat">{displayed.caveat}</p>
    </section>
  )
}
