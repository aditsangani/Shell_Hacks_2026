import { useCallback, useEffect, useRef, useState } from 'react'
import { pct } from './format.js'
import Search from './components/Search.jsx'
import Unusualness from './components/Unusualness.jsx'
import Divergence from './components/Divergence.jsx'
import SimilarMoves from './components/SimilarMoves.jsx'
import Timeline from './components/Timeline.jsx'

const MODES = [
  { id: 'latest', label: 'Latest session', hint: 'The most recent completed trading day.' },
  { id: 'unusual', label: 'Most unusual', hint: 'Biggest move in the last 30 trading days.' },
]
const EXAMPLES = ['NVDA', 'AAPL', 'TSLA', 'JPM', 'META']

// Route lives in the hash so the static build works on any host without server rewrites.
function readRoute() {
  const raw = window.location.hash.replace(/^#/, '')
  if (!raw || raw === 'investigate') return null
  const p = new URLSearchParams(raw)
  const symbol = (p.get('s') || '').toUpperCase()
  if (!symbol) return null
  const m = p.get('m')
  return {
    symbol,
    mode: MODES.some((x) => x.id === m) ? m : 'latest',
    view: p.get('view') === 'timeline' ? 'timeline' : 'investigation',
  }
}

function writeRoute(route) {
  const next = route
    ? `#s=${route.symbol}&m=${route.mode}` + (route.view === 'timeline' ? '&view=timeline' : '')
    : '#'
  if (window.location.hash !== next) {
    window.history.pushState(null, '', window.location.pathname + window.location.search + next)
  }
}

export default function App() {
  const [route, setRoute] = useState(readRoute)
  const [mode, setMode] = useState('latest')
  const [inv, setInv] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [exp, setExp] = useState(null)
  const [voice, setVoice] = useState('idle')
  const [tl, setTl] = useState(null)
  const [tlLoading, setTlLoading] = useState(false)
  const [tlError, setTlError] = useState(null)
  const [warming, setWarming] = useState(false)
  const audioRef = useRef(null)

  const params = useCallback(
    () => new URLSearchParams({ symbol: route.symbol, mode: route.mode }),
    [route?.symbol, route?.mode]
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setInv(null)
    setVoice('idle')
    try {
      const r = await fetch(`/api/investigation?${params()}`)
      const body = await r.json()
      if (!r.ok) throw new Error(body.error ?? `API ${r.status}`)
      setInv(body)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [params])

  const loadTimeline = useCallback(async () => {
    setTlLoading(true)
    setTlError(null)
    try {
      const r = await fetch(`/api/timeline?${params()}`)
      const body = await r.json()
      if (!r.ok) throw new Error(body.error ?? `API ${r.status}`)
      setTl(body)
    } catch (e) {
      setTlError(e.message)
    } finally {
      setTlLoading(false)
    }
  }, [params])

  // A cold warm runs on the server (~5 req/min, so up to a minute). Poll instead of
  // blocking, and stop as soon as the server says the job has settled.
  useEffect(() => {
    if (!tl?.warming) return
    const id = setInterval(loadTimeline, 2500)
    return () => clearInterval(id)
  }, [tl?.warming, loadTimeline])

  useEffect(() => {
    if (!route) return
    load()
    if (route.view === 'timeline') loadTimeline()
  }, [route, load, loadTimeline])

  useEffect(() => {
    const onPop = () => setRoute(readRoute())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  function start(symbol) {
    const next = { symbol, mode, view: 'investigation' }
    writeRoute(next)
    setRoute(next)
  }

  function changeMode(next) {
    setMode(next)
    if (route) {
      const r = { ...route, mode: next }
      writeRoute(r)
      setRoute(r)
    }
  }

  function go(view) {
    const r = { ...route, view }
    writeRoute(r)
    setRoute(r)
  }

  function goHome() {
    writeRoute(null)
    setRoute(null)
    setInv(null)
    setTl(null)
    setExp(null)
    setError(null)
  }

  async function warmTimeline() {
    setWarming(true)
    setTlError(null)
    try {
      const r = await fetch(`/api/timeline/warm?${params()}`, { method: 'POST' })
      const body = await r.json()
      if (!r.ok) throw new Error(body.error ?? `API ${r.status}`)
      setTl(null)
      await loadTimeline()
    } catch (e) {
      setTlError(e.message)
    } finally {
      setWarming(false)
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
      const r = await fetch(`/api/briefing.mp3?${params()}`)
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

  /* ---------------- Intro ---------------- */
  if (!route) {
    return (
      <div className="page">
        <div className="brand">
          <b>FinSight</b>
          <span>Investigation Mode</span>
        </div>

        <section className="card intro">
          <h1 className="intro-title">What happened?</h1>
          <p className="intro-lead">
            Pick any traded stock and we'll investigate one of its biggest recent moves —
            how unusual it was, whether it was the company or the market, what was published
            around it, and what has happened after moves this size before.
          </p>

          <Search onPick={start} busy={loading} />

          <div className="modes" role="radiogroup" aria-label="Which session to investigate">
            {MODES.map((m) => (
              <button
                key={m.id}
                role="radio"
                aria-checked={mode === m.id}
                className={mode === m.id ? 'mode on' : 'mode'}
                onClick={() => changeMode(m.id)}
              >
                <b>{m.label}</b>
                <span>{m.hint}</span>
              </button>
            ))}
          </div>

          <div className="examples">
            Try:
            {EXAMPLES.map((t) => (
              <button key={t} className="chip-btn" onClick={() => start(t)}>{t}</button>
            ))}
          </div>
        </section>

        <p className="disclaimer">
          Prices: Yahoo Finance · News: The New York Times · Explanations: Gemini.
          Historical observation only — not investment advice.
        </p>
      </div>
    )
  }

  /* ---------------- Timeline page ---------------- */
  if (route.view === 'timeline') {
    return (
      <Timeline
        tl={tl}
        loading={tlLoading}
        error={tlError}
        warming={warming}
        onWarm={warmTimeline}
        onBack={() => go('investigation')}
      />
    )
  }

  /* ---------------- Investigation ---------------- */
  const m = inv?.move
  return (
    <div className="page">
      <div className="brand">
        <b onClick={goHome} style={{ cursor: 'pointer' }}>FinSight</b>
        <span>Investigation Mode</span>
      </div>

      <div className="toolbar">
        <button className="ghost" onClick={goHome}>← Change ticker</button>
        <div className="modes inline" role="radiogroup" aria-label="Which session to investigate">
          {MODES.map((mo) => (
            <button
              key={mo.id}
              role="radio"
              aria-checked={route.mode === mo.id}
              className={route.mode === mo.id ? 'mode on' : 'mode'}
              onClick={() => changeMode(mo.id)}
            >
              <b>{mo.label}</b>
            </button>
          ))}
        </div>
        <button className="ghost" onClick={load} disabled={loading}>
          {loading ? 'Refreshing…' : '↻ Refresh'}
        </button>
      </div>

      {error && (
        <div className="card">
          <p className="error">{error}</p>
          <button onClick={goHome}>← Change ticker</button>
        </div>
      )}
      {!error && loading && <div className="card"><p className="loading">Loading {route.symbol} market data…</p></div>}

      {inv && m && (
        <>
          <section className="card hero">
            <div>
              <div className="ticker">{inv.company} · {inv.symbol}</div>
              <div className={`move ${m.move_pct >= 0 ? 'up' : 'down'}`}>{pct(m.move_pct)}</div>
              <div className="when">{inv.event_label}</div>
              <div className={`freshness ${inv.freshness.is_live ? 'live' : ''}`}>
                {inv.freshness.is_live && <span className="dot" aria-hidden="true" />}
                {inv.freshness.note}
              </div>
            </div>
            <div>
              <div className="actions">
                <button onClick={playBriefing} disabled={voice === 'loading'}>
                  {voice === 'loading' ? 'Generating briefing…' : '▶ Voice briefing'}
                </button>
              </div>
              {voice.startsWith('error') && <p className="error">{voice}</p>}
              <p className="pitch">We don't tell you what to invest in. We help you investigate what happened.</p>
            </div>
          </section>

          <Unusualness inv={inv} />
          <Divergence inv={inv} />

          <section className="card tl-teaser">
            <div className="step">3 · What was published</div>
            <h2>Evidence timeline</h2>
            <p className="sub">
              New York Times coverage sampled across the{' '}
              <b>{route.mode === 'unusual' ? '5 years' : '6 months'}</b> before this session,
              triaged by Gemini into the articles that bear on the move — and whether the move
              was stock-specific or market-wide.
            </p>
            <button className="primary" onClick={() => go('timeline')}>Open the timeline →</button>
          </section>

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
