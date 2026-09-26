import { useCallback, useEffect, useRef, useState } from 'react'
import { pct } from './format.js'
import Search from './components/Search.jsx'
import Unusualness from './components/Unusualness.jsx'
import Divergence from './components/Divergence.jsx'
import News from './components/News.jsx'
import Explanations from './components/Explanations.jsx'
import SimilarMoves from './components/SimilarMoves.jsx'

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
  return { symbol, mode: MODES.some((m) => m.id === p.get('m')) ? p.get('m') : 'latest' }
}

function writeRoute(route) {
  const next = route ? `#s=${route.symbol}&m=${route.mode}` : '#'
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
  const [expLoading, setExpLoading] = useState(false)
  const [voice, setVoice] = useState('idle')
  const audioRef = useRef(null)

  const query = (extra = '') => {
    const p = new URLSearchParams({ symbol: route.symbol, mode: route.mode })
    return `/api/investigation?${p}${extra}`
  }

  const loadExplanations = useCallback(async (refresh) => {
    setExpLoading(true)
    setExp(null)
    try {
      const r = await fetch(query(refresh ? '&refresh=1' : ''))
      setExp(r.ok ? await r.json() : { error: (await r.json().catch(() => ({}))).error ?? `API ${r.status}` })
    } catch (e) {
      setExp({ error: e.message })
    } finally {
      setExpLoading(false)
    }
  }, [route?.symbol, route?.mode])

  const load = useCallback(async (refresh) => {
    setLoading(true)
    setError(null)
    setInv(null)
    setExp(null)
    setVoice('idle')
    try {
      const r = await fetch(query(refresh ? '&refresh=1' : ''))
      const body = await r.json()
      if (!r.ok) throw new Error(body.error ?? `API ${r.status}`)
      setInv(body)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [route?.symbol, route?.mode])

  useEffect(() => {
    if (!route) return
    load(false)
    loadExplanations(false)
  }, [route, load, loadExplanations])

  useEffect(() => {
    const onPop = () => setRoute(readRoute())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  function start(symbol) {
    const next = { symbol, mode }
    setMode((m) => m) // keep the chosen mode across searches
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

  function goHome() {
    writeRoute(null)
    setRoute(null)
    setInv(null)
    setExp(null)
    setError(null)
  }

  function refresh() {
    load(true)
    loadExplanations(true)
  }

  async function playBriefing() {
    if (audioRef.current) {
      audioRef.current.currentTime = 0
      audioRef.current.play()
      return
    }
    setVoice('loading')
    try {
      const r = await fetch(query())
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
      <div className="page landing-page">
        <div className="brand">
          <div className="brand-lockup">
            <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
            <b>FinSight</b>
          </div>
          <span className="brand-mode"><i className="status-dot" />Investigation Mode</span>
        </div>

        <section className="card intro">
          <div className="intro-copy">
            <div className="eyebrow"><span />Market intelligence, with receipts</div>
            <h1 className="intro-title">Understand the move.<br /><em>Follow the evidence.</em></h1>
            <p className="intro-lead">
              Pick any traded stock and we'll investigate one of its biggest recent moves —
              how unusual it was, whether it was the company or the market, what was published
              around it, and what has happened after moves this size before.
            </p>
          </div>

          <div className="intro-console">
            <div className="console-label"><span>Start an investigation</span><small>US equities</small></div>
            <Search onPick={start} busy={loading} />

            <div className="mode-label">Choose the session</div>
            <div className="modes" role="radiogroup" aria-label="Which session to investigate">
              {MODES.map((m) => (
                <button
                  key={m.id}
                  role="radio"
                  aria-checked={mode === m.id}
                  className={mode === m.id ? 'mode on' : 'mode'}
                  onClick={() => changeMode(m.id)}
                >
                  <span className="mode-radio" aria-hidden="true" />
                  <span className="mode-copy"><b>{m.label}</b><span>{m.hint}</span></span>
                </button>
              ))}
            </div>

            <div className="examples">
              <span>Popular</span>
              {EXAMPLES.map((t) => (
                <button key={t} className="chip-btn" onClick={() => start(t)}>{t}</button>
              ))}
            </div>
          </div>

          <div className="intro-proof">
            <div><b>01</b><span>Measure the anomaly</span></div>
            <div><b>02</b><span>Compare the market</span></div>
            <div><b>03</b><span>Trace the evidence</span></div>
          </div>
        </section>

        <p className="disclaimer">
          Prices: Yahoo Finance · News: The New York Times · Explanations: Gemini.
          Historical observation only — not investment advice.
        </p>
      </div>
    )
  }

  /* ---------------- Investigation ---------------- */
  const m = inv?.move
  return (
    <div className="page investigation-page">
      <div className="brand">
        <div className="brand-lockup" onClick={goHome} role="button" tabIndex="0">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <b>FinSight</b>
        </div>
        <span className="brand-mode"><i className="status-dot" />Investigation Mode</span>
      </div>

      <div className="toolbar">
        <button className="ghost back-button" onClick={goHome}><span aria-hidden="true">←</span> Change ticker</button>
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
        <button className="ghost" onClick={refresh} disabled={loading}>
          {loading ? 'Refreshing…' : '↻ Refresh'}
        </button>
      </div>

      {error && <div className="card"><p className="error">{error}</p><button onClick={goHome}>← Change ticker</button></div>}
      {!error && loading && <div className="card"><p className="loading">Loading {route.symbol} market data…</p></div>}

      {inv && m && (
        <>
          <section className="card hero investigation-hero">
            <div className="hero-market">
              <div className="hero-kicker">Selected market event</div>
              <div className="ticker">{inv.company} · {inv.symbol}</div>
              <div className={`move ${m.move_pct >= 0 ? 'up' : 'down'}`}>{pct(m.move_pct)}</div>
              <div className="when">{inv.event_label}</div>
              <div className={`freshness ${inv.freshness.is_live ? 'live' : ''}`}>
                {inv.freshness.is_live && <span className="dot" aria-hidden="true" />}
                {inv.freshness.note}
              </div>
            </div>
            <div className="hero-briefing">
              <div className="hero-briefing-label">Audio intelligence</div>
              <h2>Hear the investigation</h2>
              <p>Get the anomaly, market context, evidence, and uncertainty in one concise briefing.</p>
              <div className="actions">
                <button className="briefing-button" onClick={playBriefing} disabled={voice === 'loading'}>
                  <span className="play-icon" aria-hidden="true">▶</span>
                  {voice === 'loading' ? 'Generating briefing…' : voice === 'playing' ? 'Replay briefing' : 'Voice briefing'}
                </button>
              </div>
              {voice.startsWith('error') && <p className="error">{voice}</p>}
              <p className="pitch"><span aria-hidden="true">◇</span> Evidence-led. No investment recommendations.</p>
            </div>
          </section>

          <div className="investigation-flow">
            <Unusualness inv={inv} />
            <Divergence inv={inv} />
            <News inv={inv} />
            <Explanations exp={exp} loading={expLoading} />
            <SimilarMoves inv={inv} />
          </div>

          <p className="disclaimer">
            Historical observation only — not investment advice. Prices: Yahoo Finance. News: The New York Times.
            Explanations: Gemini, grounded in the evidence shown.
          </p>
        </>
      )}
    </div>
  )
}
