# FinSight — Investigation Mode

ShellHacks 2026 · Blackstone "Reimagining the Investor Experience"

> We don't tell you what to invest in. We help you investigate what happened.

Search any traded ticker, pick which session to investigate, and get a deep-dive on one move:

1. **How unusual:** percentile and z-score vs 5 years of daily moves
2. **Company or market:** ticker vs its sector ETF vs SPY, intraday, with a beta-adjusted idiosyncratic move
3. **What was published:** NYT headlines with real timestamps, pinned on the chart
4. **Candidate explanations:** Gemini, each one citing headline IDs or data points
5. **Has this happened before:** the closest past moves and their +1/+5/+20-day returns
6. **Voice briefing:** ElevenLabs TTS

## Which session gets investigated

The intro page offers two modes:

- **Latest session** — the most recent *completed* trading day.
- **Most unusual** — the largest absolute move in the last 30 trading days.

The most recent trading day is derived from the price data itself, never from the calendar,
so weekends and market holidays are handled by the same rule. When the investigated session
is not today, the UI says so explicitly and why — a stale investigation never presents itself
as a live one. During an open session the figures are labelled live and update on refresh.

For the reference demo, `META` in **Most unusual** mode lands on **Mon, Sep 21, 2026:
+11.43%, 99.4th percentile, z = 4.0**.

## Run locally

```bash
cp .env.example backend/.env        # fill in keys
pip install -r backend/requirements.txt
python backend/app.py               # API on :5001

cd frontend && npm install && npm run dev   # UI on :5173, proxies /api
```

Optional: pre-load a ticker into Tiger Data (needs `DATABASE_URL`; add `NYT_API_KEY` for headlines).

```bash
cd backend
python ingest.py                    # default ticker, latest session
python ingest.py NVDA unusual       # ticker + mode
python ingest.py NVDA --no-news     # skip the NYT call to save quota
```

The API port is 5001 because macOS AirPlay Receiver occupies 5000 and answers
`403 Forbidden` to every request, which surfaces in the UI as
"Couldn't load investigation: API 403". To use a different port, set `PORT` and change
the target in `frontend/vite.config.js` to match.

Every key is optional for a first run. Without `DATABASE_URL` the chart is computed from
yfinance in memory. Without `NYT_API_KEY` no headlines load. Missing Gemini or ElevenLabs
keys show an inline error. Ticker search and all price analysis work with no keys at all.

Repeat searches reuse a cached bundle for 5 minutes, so browsing around does not trip
Yahoo's rate limits. **↻ Refresh** forces a virgin fetch.

### Deep links

The investigated ticker lives in the URL hash, which is handy for demos:

```
/#s=NVDA&m=unusual
/#s=META&m=latest
```

## Deploy (DigitalOcean App Platform)

One Docker service. It builds React, then Flask/gunicorn serves both the API and `frontend/dist`.

```bash
doctl apps create --spec .do/app.yaml
```

Set the secrets in the App Platform UI. The app is served at `https://finsight-xxxxx.ondigitalocean.app`.
