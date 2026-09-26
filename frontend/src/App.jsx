import { useEffect, useRef, useState } from 'react'
import { pct, longDate } from './format.js'
import Unusualness from './components/Unusualness.jsx'
import Divergence from './components/Divergence.jsx'
import News from './components/News.jsx'
import Explanations from './components/Explanations.jsx'
import SimilarMoves from './components/SimilarMoves.jsx'

export default function App() {
  const [inv, setInv] = useState(null)
  const [error, setError] = useState(null)
  const [open, setOpen] = useState(false)
  const [exp, setExp] = useState(null)
  const [voice, setVoice] = useState('idle')
  const audioRef = useRef(null)

  useEffect(() => {
    fetch('/api/investigation')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`API ${r.status}`))))
      .then(setInv)
      .catch((e) => setError(e.message))
    if (window.location.hash === '#investigate') investigate()
  }, [])

  function investigate() {
    setOpen(true)
    if (!exp) {
      fetch('/api/explanations')
        .then((r) => r.json())
        .then(setExp)
        .catch((e) => setExp({ error: e.message }))
    }
  }

  async function playBriefing() {
    if (audioRef.current) {
      audioRef.current.currentTime = 0
      audioRef.current.play()
      return
    }
    setVoice('loading')
    try {
      const r = await fetch('/api/briefing.mp3')
      if (!r.ok) throw new Error((await r.json()).error)
      const audio = new Audio(URL.createObjectURL(await r.blob()))
      audio.onended = () => setVoice('idle')
      audioRef.current = audio
      audio.play()
      setVoice('playing')
    } catch (e) {
      setVoice(`error: ${e.message}`)
    }
  }

  if (error) return <div className="page"><p className="error">Couldn't load investigation: {error}</p></div>
  if (!inv) return <div className="page"><p className="loading">Loading market data…</p></div>

  const m = inv.move
  return (
    <div className="page">
      <div className="brand">
        <b>FinSight</b>
        <span>Investigation Mode</span>
      </div>

      <section className="card hero">
        <div>
          <div className="ticker">{inv.company} · {inv.symbol}</div>
          <div className={`move ${m.move_pct >= 0 ? 'up' : 'down'}`}>{pct(m.move_pct)}</div>
          <div className="when">{inv.event_label}, {longDate(inv.event_date).split(', ')[1]}</div>
        </div>
        <div>
          <div className="actions">
            {!open && <button className="primary" onClick={investigate}>Investigate this move</button>}
            {open && (
              <button onClick={playBriefing} disabled={voice === 'loading'}>
                {voice === 'loading' ? 'Generating briefing…' : '▶ Voice briefing'}
              </button>
            )}
          </div>
          {voice.startsWith('error') && <p className="error">{voice}</p>}
          <p className="pitch">We don't tell you what to invest in. We help you investigate what happened.</p>
        </div>
      </section>

      {open && (
        <>
          <Unusualness inv={inv} />
          <Divergence inv={inv} />
          <News inv={inv} />
          <Explanations exp={exp} />
          <SimilarMoves inv={inv} />
          <p className="disclaimer">
            Historical observation only — not investment advice. Prices: Yahoo Finance. News: The New York Times.
            Explanations: Gemini, grounded in the evidence shown.
          </p>
        </>
      )}
    </div>
  )
}
