# FinSight — Investigation Mode
ShellHacks 2026 — Blackstone "Reimagining the Investor Experience" track

## Core Concept
Not a portfolio dashboard. The app answers "why did this stock move?" for one ticker in depth.
User sees a big move (e.g. NVDA -7.4%), clicks Investigate, gets:
1. How unusual the move is (percentile vs 5yr history)
2. Company-specific vs sector/market-wide (divergence chart vs sector ETF + SPY)
3. What news was published around that time (real headlines, real timestamps)
4. AI-generated candidate explanations citing that evidence
5. Similar historical moves and what happened after

Pitch line: "We don't tell you what to invest in. We help you investigate what happened."

This idea came from a much bigger brainstorm doc (38 features, full "investigation OS" vision).
That doc is aspirational — most of it is 3-4 months of work, not one hackathon night. Only the
scope below is in play. Do not build features from the bigger doc unless explicitly told to
expand scope.

## Locked MVP scope — build in this order
1. yfinance intraday (5-min interval) for ticker + sector ETF + SPY → Tiger Data hypertable
2. yfinance 5yr daily history → compute z-score / percentile of the session's move
   ("bigger than 97.8% of NVDA's daily moves over the past 5 years")
3. NYT Article Search API → headlines for the ticker/company in the date window, with real
   pub timestamps → plot as markers on the price chart
4. Gemini: feed it (a) divergence numbers (ticker vs sector vs SPY), (b) percentile/z-score,
   (c) headlines → generate 2-3 candidate explanations, each citing which headline/data point
   supports it
5. Historical similarity: from the 5yr daily history, find 2-3 past days with similar % move,
   show what happened in the following days (present as historical observation, not prediction)
6. Evidence display: render the actual NYT headline + link under each Gemini explanation
7. ElevenLabs voice briefing — text-to-speech of a scripted summary (see "Team's prior
   hackathon context" for why the Bay Hacks code wasn't reusable)
8. Deploy to DigitalOcean (use their free subdomain, not a custom domain)

## Generic tickers — built after the META demo worked
Originally hardcoded to META. Now any traded ticker, at the user's request, so the demo is
not a one-trick pony. Constraints that shaped it:
- Sector comes from a hand-maintained GICS map in `config.py` (`TICKER_SECTORS` → `SECTOR_ETFS`).
  Yahoo's sector field needs a slow, rate-limited `.info` call. An unmapped symbol gets **no**
  sector line rather than a guessed one — a wrong comparison is worse than none.
- The investigated session is chosen at request time: `latest` (most recent completed session)
  or `unusual` (largest move in the last 30 trading days). The reference demo is preserved as
  META + unusual = Sep 21, 2026.
- The event date comes from the trading days yfinance returns, never the calendar. `market.describe`
  renders an explicit freshness note, because a stale investigation must not look live.
- `app.py` caches per `(symbol, mode)` with a 5-min TTL. A single global cache entry would serve
  one ticker's data to every ticker. `prices.py` uses `ttl_cache` rather than `lru_cache` so an
  explicit Refresh re-fetches — `lru_cache` cannot expire and would pin a partial intraday bar.
- `ingest.py` now takes a ticker and mode and resolves the session through the same code path the
  API uses, so the continuous aggregate lines up with what the API later queries.


Stretch only if time allows: MongoDB to store saved investigations as documents (natural fit,
~30 min of work). Do not build it earlier than step 8.

## Explicitly cut — do not build
Correlation explorer, contradiction detector, relationship graph, SEC filing diffs, options
data, macro/earnings investigation, market replay slider, portfolio-wide investigation, voice
input/search, alerts, event relationship graph, investigation comparison, PDF report export,
Solana (any form), Snowflake (redundant with Tiger Data), GoDaddy custom domain.

## MLH tracks — final answer
Gemini, Tiger Data, ElevenLabs, DigitalOcean. (MongoDB only as a stretch add.)
Do not add Solana or Snowflake even if there's spare time — not worth the setup tax tonight.

## Tech stack
- Frontend: React
- Backend: Flask
- Time-series DB: Tiger Data (TimescaleDB / Postgres extension)
- Relational data (news, users): same Tiger Data instance, plain tables — one unified DB
- AI: Gemini (analysis/explanation layer)
- Voice: ElevenLabs text-to-speech (backend/voice.py)
- Deploy: DigitalOcean App Platform, free subdomain

## Data sources
- yfinance: intraday + historical price data (free, no key). Also `yf.Search` powers ticker
  typeahead (fuzzy, so "nvid" → NVDA). US listings are sorted first; futures are filtered out.
- NYT Article Search API: https://developer.nytimes.com — free key, must enable
  "Article Search API" specifically on the app or you get 401s. Rate limit 500 req/day, 5/min.
  Query params: q=<company>, begin_date, end_date (YYYYMMDD format). Each investigation can
  burn 2 queries (company name + ticker), so `news.py` caches to `backend/.cache` keyed by
  symbol *and* event date.
- Alpha Vantage News Sentiment API: not wired up; `news.py` is the only news path.
- WSJ: explicitly excluded — no free API, paywalled content, not worth the time

## Tiger Data schema
Source of truth: `backend/schema.sql` (idempotent; `python backend/ingest.py` applies it).
- `price_ticks` hypertable (time, symbol, price, volume) + unique (symbol, time).
- `price_5min` continuous aggregate: time_bucket 5 min → first/last price, sum volume.
  The original `pct_change_5min` design (last − first within a bucket) is always 0 on
  5-min yfinance bars (one row per bucket), so it was replaced. Cumulative % vs the pre-event
  close is computed at query time on top of the aggregate (`db.DIVERGENCE_SQL`).
- `news_events` (url UNIQUE) caches NYT headlines so the demo doesn't burn API quota.
Use the continuous aggregate to serve the divergence chart instead of recomputing from raw
ticks per request — this is the judges' talking point for "why Tiger Data specifically."
Continuous aggregates are materialized-only by default: ingest calls
`refresh_continuous_aggregate` after inserting.

## Reference demo — META, Mon 2026-09-21
META +11.43% vs XLC +3.90% vs SPY +1.55%.
Bigger than 99.4% of META's daily moves over 5 years (z = 4.0); beta-adjusted, +9.3 pts is
META-specific. Sector ETF XLC, market SPY.
Reachable in the shipped app as META + "Most unusual" (deep link `/#s=META&m=unusual`), since
Sep 21 is the largest move in the trailing 30-session window. Use this for demos — it is the
strongest story in the dataset.
yfinance 5-min data only goes back ~60 days — ingest into Tiger Data before ~Nov 20, 2026
or the intraday chart can't be rebuilt from yfinance. Past that, `/api/investigation` degrades
to the daily comparison and sets `chart_source: "unavailable"` with a caveat.

## Team's prior hackathon context
Built NeuroTriage-Home at Bay Hacks 2026 (2nd place, Render track), 4-person team, with React,
Flask, Supabase/PostgreSQL, ElevenLabs voice agent. Repo: aditsangani/Bay_Hacks_2026.
That repo only used the ElevenLabs Conversational AI *widget* (voice input — cut here), so
there was no TTS code to reuse. Step 7 is a direct TTS REST call in `backend/voice.py`.

## Working style
- Direct, non-hedged answers. No filler, no "it depends" hedging.
- This is a hackathon under a hard deadline — prioritize a working demo over feature breadth
  every time. If a feature isn't in the locked MVP scope above, don't suggest adding it
  mid-build unless asked.
