"""NYT Article Search. 500 req/day, 5/min — results are cached (Tiger Data, else a local JSON file)."""

import json
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

import db
from config import DEMO, NYT_API_KEY

NYT_URL = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
CACHE_DIR = Path(__file__).parent / ".cache"


def news_window(event_date: date) -> tuple[date, date]:
    # Covers a weekend before a Monday event plus the day after.
    return event_date - timedelta(days=3), event_date + timedelta(days=1)


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


def fetch_and_store(event_date: date) -> list[dict]:
    if not NYT_API_KEY:
        raise RuntimeError("NYT_API_KEY is not set")
    begin, end = news_window(event_date)
    by_url = {}
    for i, q in enumerate(DEMO["news_queries"]):
        if i:
            time.sleep(12)  # stay under 5 req/min
        for a in _fetch_nyt(q, begin, end):
            by_url.setdefault(a["url"], a)
    articles = sorted(by_url.values(), key=lambda a: a["pub_date"])

    if db.ENABLED:
        db.upsert_news(DEMO["symbol"], articles)
    CACHE_DIR.mkdir(exist_ok=True)
    _cache_path(event_date).write_text(json.dumps(articles, indent=2))
    return articles


def get_news(event_date: date) -> list[dict]:
    """Cached headlines for the event window; hits the NYT API only on a cold cache."""
    begin, end = news_window(event_date)
    if db.ENABLED:
        articles = db.load_news(DEMO["symbol"], begin, end + timedelta(days=1))
        if articles:
            return articles
    path = _cache_path(event_date)
    if path.exists():
        return json.loads(path.read_text())
    return fetch_and_store(event_date) if NYT_API_KEY else []


def _cache_path(event_date: date) -> Path:
    return CACHE_DIR / f"news_{DEMO['symbol']}_{event_date.isoformat()}.json"
