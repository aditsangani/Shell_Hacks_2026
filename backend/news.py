"""NYT Article Search. 500 req/day, 5/min — results are cached (Tiger Data, else a local JSON file).

Cache is keyed by symbol *and* event date, so a multi-ticker demo does not re-query the API
for a session another ticker already warmed.
"""

import json
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

import db
import market
from config import NYT_API_KEY

NYT_URL = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
CACHE_DIR = Path(__file__).parent / ".cache"
RATE_LIMIT_PAUSE = 12  # seconds between queries; NYT allows 5/min


def _fetch_nyt(query: str, begin: date, end: date) -> list[dict]:
    resp = requests.get(NYT_URL, timeout=20, params={
        "q": query,
        "begin_date": begin.strftime("%Y%m%d"),
        "end_date": end.strftime("%Y%m%d"),
        "sort": "newest",
        "api-key": NYT_API_KEY,
    })
    resp.raise_for_status()
    docs = (resp.json().get("response") or {}).get("docs") or []
    return [{
        "headline": (d.get("headline") or {}).get("main", "").strip(),
        "pub_date": pd.Timestamp(d["pub_date"]).tz_convert("UTC").isoformat(),
        "url": d.get("web_url"),
        "snippet": d.get("abstract") or d.get("snippet") or "",
    } for d in docs if d.get("pub_date") and d.get("web_url")]


def queries_for(symbol: str, company: str) -> list[str]:
    """Search terms for a ticker: the company name plus the symbol itself."""
    name = (company or "").strip()
    if name and name.lower() != symbol.lower():
        return [name, symbol]
    return [symbol]


def fetch_and_store(event_date: date, symbol: str, company: str = "") -> list[dict]:
    if not NYT_API_KEY:
        raise RuntimeError("NYT_API_KEY is not set")
    begin, end = market.search_window(event_date)
    by_url = {}
    terms = queries_for(symbol, company)
    for i, q in enumerate(terms):
        if i:
            time.sleep(RATE_LIMIT_PAUSE)
        for a in _fetch_nyt(q, begin, end):
            by_url.setdefault(a["url"], a)
    articles = sorted(by_url.values(), key=lambda a: a["pub_date"])

    if db.ENABLED:
        try:
            db.upsert_news(symbol, articles)
        except Exception:
            pass  # the local cache below is still worth writing
    CACHE_DIR.mkdir(exist_ok=True)
    _cache_path(symbol, event_date).write_text(json.dumps(articles, indent=2))
    return articles


def get_news(event_date: date, symbol: str, company: str = "") -> list[dict]:
    """Cached headlines for the event window; hits the NYT API only on a cold cache."""
    if db.ENABLED:
        try:
            begin, end = market.search_window(event_date)
            articles = db.load_news(symbol, begin, end + timedelta(days=1))
            if articles:
                return articles
        except Exception:
            pass
    path = _cache_path(symbol, event_date)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            path.unlink(missing_ok=True)
    if not NYT_API_KEY:
        return []
    try:
        return fetch_and_store(event_date, symbol, company)
    except Exception:
        return []  # never let a news failure take down the investigation


def _cache_path(symbol: str, event_date: date) -> Path:
    return CACHE_DIR / f"news_{symbol.upper()}_{event_date.isoformat()}.json"
