import { useCallback, useEffect, useRef, useState } from 'react'
import { pct } from './format.js'
import Search from './components/Search.jsx'
import Unusualness from './components/Unusualness.jsx'
import Divergence from './components/Divergence.jsx'
import SimilarMoves from './components/SimilarMoves.jsx'
import Timeline from './components/Timeline.jsx'
import ThemeToggle from './components/ThemeToggle.jsx'
import Conclusion from './components/Conclusion.jsx'
import SectionNav, { SECTIONS } from './components/SectionNav.jsx'

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
  const [theme, setTheme] = useState(() => {
    const saved = window.localStorage.getItem('finsight-theme')
    if (saved === 'light' || saved === 'dark') return saved
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  })
  const [route, setRoute] = useState(readRoute)
  const [mode, setMode] = useState('latest')
  const [inv, setInv] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [voice, setVoice] = useState('idle')
  const [playbackRate, setPlaybackRate] = useState(1)
  const [tl, setTl] = useState(null)
  const [tlLoading, setTlLoading] = useState(false)
  const [tlError, setTlError] = useState(null)
  const [warming, setWarming] = useState(false)
  const [activeSection, setActiveSection] = useState('evidence')
  const audioRef = useRef(null)
  const investigationRequest = useRef(0)
  const timelineRequest = useRef(0)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    window.localStorage.setItem('finsight-theme', theme)
  }, [theme])

  function toggleTheme() {
    setTheme((current) => current === 'dark' ? 'light' : 'dark')
  }

  const params = useCallback(
    () => new URLSearchParams({ symbol: route.symbol, mode: route.mode }),
    [route?.symbol, route?.mode]
  )

  const loadTimeline = useCallback(async (refresh = false) => {
    const requestId = ++timelineRequest.current
    setTlError(null)
    try {
      const query = params()
      if (refresh) query.set('refresh', '1')
      const r = await fetch(`/api/timeline?${query}`)
      const body = await r.json()
      if (!r.ok) throw new Error(body.error ?? `API ${r.status}`)
      if (requestId === timelineRequest.current) setTl(body)
    } catch (e) {
      if (requestId === timelineRequest.current) setTlError(e.message)
    } finally {
      if (requestId === timelineRequest.current) setTlLoading(false)
    }
  }, [params])

  const load = useCallback(async (refresh = false) => {
    const requestId = ++investigationRequest.current
    ++timelineRequest.current
    setLoading(true)
    setTlLoading(true)
    setError(null)
    setTlError(null)
    setTl(null)
    setInv(null)
    audioRef.current?.pause()
    audioRef.current = null
    setVoice('idle')
    try {
      const query = params()
      if (refresh) query.set('refresh', '1')
      const r = await fetch(`/api/investigation?${query}`)
      const body = await r.json()
      if (!r.ok) throw new Error(body.error ?? `API ${r.status}`)
      if (requestId !== investigationRequest.current) return
      setInv(body)
      // Reuse the completed investigation on the server instead of racing two price fetches.
      await loadTimeline(refresh)
    } catch (e) {
      if (requestId === investigationRequest.current) {
        setError(e.message)
        setTlError(e.message)
        setTlLoading(false)
      }
    } finally {
      if (requestId === investigationRequest.current) setLoading(false)
    }
  }, [params, loadTimeline])

  // Keep the existing timeline visible during polling; schedule only after the last
  // response, so slow requests cannot overlap or overwrite a newer ticker's results.
  useEffect(() => {
    if (!tl?.warming || tlError) return
    const id = setTimeout(() => loadTimeline(), 2500)
    return () => clearTimeout(id)
  }, [tl, tlError, loadTimeline])

  useEffect(() => {
    if (!route?.symbol) return
    load()
    return () => {
      ++investigationRequest.current
      ++timelineRequest.current
    }
  }, [route?.symbol, route?.mode, load])

  useEffect(() => {
    if (!inv || route?.view !== 'investigation') return
    const elements = SECTIONS.map((section) => document.getElementById(section.id)).filter(Boolean)
    const updateActiveSection = () => {
      const atPageEnd = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 8
      if (atPageEnd) {
        setActiveSection(elements[elements.length - 1]?.id || SECTIONS[0].id)
        return
      }
      const readingLine = window.scrollY + 170
      const current = elements.reduce(
        (active, element) => (
          element.getBoundingClientRect().top + window.scrollY <= readingLine ? element : active
        ),
        elements[0],
      )
      if (current) setActiveSection(current.id)
    }
    updateActiveSection()
    window.addEventListener('scroll', updateActiveSection, { passive: true })
    window.addEventListener('resize', updateActiveSection)
    return () => {
      window.removeEventListener('scroll', updateActiveSection)
      window.removeEventListener('resize', updateActiveSection)
    }
  }, [inv, route?.view])

  useEffect(() => {
    const onPop = () => setRoute(readRoute())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  function start(symbol) {
    setTl(null)
    setTlError(null)
    const next = { symbol, mode, view: 'investigation' }
    writeRoute(next)
    setRoute(next)
  }

  function changeMode(next) {
    setMode(next)
    if (route) {
      setTl(null)
      setTlError(null)
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
    setError(null)
  }

  async function warmTimeline() {
    setWarming(true)
    try {
      await loadTimeline(true)
    } finally {
      setWarming(false)
    }
  }

  async function toggleBriefing() {
    if (voice === 'playing' && audioRef.current) {
      audioRef.current.pause()
      setVoice('paused')
      return
    }

    if (audioRef.current) {
      if (audioRef.current.ended) audioRef.current.currentTime = 0
      try {
        await audioRef.current.play()
        setVoice('playing')
      } catch (e) {
        setVoice(`error: ${e.message}`)
      }
      return
    }

    setVoice('loading')
    try {
      const r = await fetch(`/api/briefing.mp3?${params()}`)
      if (!r.ok) throw new Error((await r.json()).error)
      const audio = new Audio(URL.createObjectURL(await r.blob()))
      audio.playbackRate = playbackRate
      audio.onended = () => setVoice('idle')
      audioRef.current = audio
      await audio.play()
      setVoice('playing')
    } catch (e) {
      setVoice(`error: ${e.message}`)
    }
  }

  function changePlaybackRate(rate) {
    setPlaybackRate(rate)
    if (audioRef.current) audioRef.current.playbackRate = rate
  }

  function scrollToSection(id) {
    setActiveSection(id)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
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
          <div className="brand-actions">
            <span className="brand-mode"><i className="status-dot" />Investigation Mode</span>
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
          </div>
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
          Data: Yahoo Finance · Evidence: NYT, Yahoo Finance News, SEC EDGAR · AI triage: Gemini · Not investment advice.
        </p>
      </div>
    )
  }

  /* ---------------- Timeline page ---------------- */
  if (route.view === 'timeline') {
    return (
      <Timeline
        key={`${route.symbol}:${route.mode}`}
        tl={tl}
        loading={tlLoading}
        error={tlError}
        warming={warming}
        onWarm={warmTimeline}
        onBack={() => go('investigation')}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
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
        <div className="brand-actions">
          <span className="brand-mode"><i className="status-dot" />Investigation Mode</span>
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
        </div>
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
        <button className="ghost" onClick={() => load(true)} disabled={loading}>
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
          <SectionNav active={activeSection} onSelect={scrollToSection} />

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
                <button
                  className="briefing-button"
                  onClick={toggleBriefing}
                  disabled={voice === 'loading'}
                  aria-pressed={voice === 'playing'}
                >
                  <span className="play-icon" aria-hidden="true">{voice === 'playing' ? '⏸' : '▶'}</span>
                  {voice === 'loading'
                    ? 'Generating briefing…'
                    : voice === 'playing'
                      ? 'Pause briefing'
                      : voice === 'paused'
                        ? 'Resume briefing'
                      : 'Voice briefing'}
                </button>
                <div className="speed-controls" role="group" aria-label="Briefing playback speed">
                  {[1, 1.5, 2].map((rate) => (
                    <button
                      key={rate}
                      type="button"
                      className={playbackRate === rate ? 'speed-button on' : 'speed-button'}
                      onClick={() => changePlaybackRate(rate)}
                      aria-pressed={playbackRate === rate}
                    >
                      {rate}×
                    </button>
                  ))}
                </div>
              </div>
              {voice.startsWith('error') && <p className="error">{voice}</p>}
              <p className="pitch"><span aria-hidden="true">◇</span> Evidence-led. No investment recommendations.</p>
            </div>
          </section>

          <div className="investigation-flow">
            <section id="evidence" className="card insight-card tl-teaser">
              <div className="step">1 · What was published</div>
              <h2>Evidence timeline</h2>
              <p className="sub">
                News and SEC filings sampled across the{' '}
                <b>{route.mode === 'unusual' ? '5 years' : '6 months'}</b> before this session,
                triaged by Gemini into the articles that bear on the move — and whether the move
                was stock-specific or market-wide.
              </p>
              <button className="primary" onClick={() => go('timeline')}>Open the timeline →</button>
            </section>

            <Unusualness inv={inv} />
            <Divergence inv={inv} />
            <SimilarMoves inv={inv} />
            <Conclusion
              timelineError={tlError}
              conclusion={
                tl?.symbol === inv.symbol && tl?.mode === inv.mode
                  ? tl.conclusion || inv.conclusion
                  : inv.conclusion
              }
            />
          </div>

          <p className="disclaimer">
            Data: Yahoo Finance · Evidence: NYT, Yahoo Finance News, SEC EDGAR · AI triage: Gemini · Not investment advice.
          </p>
        </>
      )}
    </div>
  )
}
