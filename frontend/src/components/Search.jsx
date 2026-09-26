import { useEffect, useRef, useState } from 'react'

const DEBOUNCE_MS = 220

export default function Search({ onPick, busy }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [cursor, setCursor] = useState(0)
  const boxRef = useRef(null)
  const abortRef = useRef(null)

  useEffect(() => {
    const query = q.trim()
    if (query.length < 1) {
      setResults([])
      setLoading(false)
      return
    }
    setLoading(true)
    const timer = setTimeout(async () => {
      abortRef.current?.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl
      try {
        const r = await fetch(`/api/search?q=${encodeURIComponent(query)}`, { signal: ctrl.signal })
        const body = r.ok ? await r.json() : { results: [] }
        setResults(body.results ?? [])
        setCursor(0)
        setOpen(true)
      } catch (e) {
        if (e.name !== 'AbortError') setResults([])
      } finally {
        setLoading(false)
      }
    }, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [q])

  useEffect(() => {
    const onDocClick = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  function pick(r) {
    onPick(r.symbol, r.name)
    setQ('')
    setResults([])
    setOpen(false)
  }

  function onKeyDown(e) {
    if (!open || !results.length) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => (c + 1) % results.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => (c - 1 + results.length) % results.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      pick(results[cursor])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="search" ref={boxRef}>
      <input
        className="search-input"
        value={q}
        autoFocus
        disabled={busy}
        placeholder="Search any stock — try NVDA, AAPL, JPM, TSLA"
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={onKeyDown}
        onFocus={() => results.length && setOpen(true)}
        aria-label="Search for a ticker or company"
        aria-expanded={open}
        aria-autocomplete="list"
      />
      {loading && <span className="search-spin" aria-hidden="true" />}

      {open && results.length > 0 && (
        <ul className="results" role="listbox">
          {results.map((r, i) => (
            <li key={r.symbol} role="option" aria-selected={i === cursor}>
              <button
                type="button"
                className={i === cursor ? 'result on' : 'result'}
                onMouseEnter={() => setCursor(i)}
                onClick={() => pick(r)}
              >
                <span className="rsym">{r.symbol}</span>
                <span className="rname">{r.name}</span>
                <span className="rexch">{r.exchange}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && !loading && q.trim() && results.length === 0 && (
        <div className="results empty">No traded symbol matches “{q.trim()}”.</div>
      )}
    </div>
  )
}
