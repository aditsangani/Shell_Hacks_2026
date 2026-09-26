# FinSight — Investigation Mode

ShellHacks 2026 · Blackstone "Reimagining the Investor Experience"

> We don't tell you what to invest in. We help you investigate what happened.

Deep-dive on one move: **META +11.43% on Mon, Sep 21, 2026**.

1. **How unusual:** percentile and z-score vs 5 years of daily moves
2. **Company or market:** META vs XLC vs SPY, intraday from a Tiger Data continuous aggregate, with a beta-adjusted idiosyncratic move
3. **What was published:** NYT headlines with real timestamps, pinned on the chart
4. **Candidate explanations:** Gemini, each one citing headline IDs or data points
5. **Has this happened before:** the closest past moves and their +1/+5/+20-day returns
6. **Voice briefing:** ElevenLabs TTS

## Run locally

```bash
cp .env.example backend/.env        # fill in keys
pip install -r backend/requirements.txt
python backend/ingest.py            # load prices + NYT headlines into Tiger Data (needs DATABASE_URL, NYT_API_KEY)
python backend/app.py               # API on :5000

cd frontend && npm install && npm run dev   # UI on :5173, proxies /api
```

Every key is optional for a first run. Without `DATABASE_URL` the chart is computed from yfinance in memory. Without `NYT_API_KEY` no headlines load. Missing Gemini or ElevenLabs keys show an inline error.

Open `/#investigate` to skip the landing click during demos.

## Deploy (DigitalOcean App Platform)

One Docker service. It builds React, then Flask/gunicorn serves both the API and `frontend/dist`.

```bash
doctl apps create --spec .do/app.yaml
```

Set the secrets in the App Platform UI. The app is served at `https://finsight-xxxxx.ondigitalocean.app`.
