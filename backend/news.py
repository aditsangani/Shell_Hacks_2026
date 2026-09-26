"""NYT Article Search.

The API allows 500 requests/day and 5 requests/minute, and a request cannot span more than
about a year of coverage (100-result cap, `newest`/`oldest` sort only). So sampling a long
window means many rate-limited requests, which is why this module is built around *not*
making them:

- **Per-chunk cache.** Every (term, chunk, page) is cached on disk individually. A second
  visit costs zero requests, an interrupted warm resumes, and because a 5-year warm's chunks
  contain the 6-month window's chunk, warming one mode pre-warms the other.
- **Budget-derived chunking.** Chunk count is chosen to fit the per-warm request budget, so a
  5-year window costs ~5 requests instead of 10.
- **A daily budget tracker.** Spend is persisted and stops at a safety margin below the real
  500 cap, so a long test session degrades to cached data instead of erroring.
- **Sleep only when actually requesting.** A fully cached warm does not sleep at all.
"""

import json
import re
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

import db
import market
from config import NYT_API_KEY, scrub

NYT_URL = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
CACHE_DIR = Path(__file__).parent / ".cache"
CHUNK_DIR = CACHE_DIR / "nyt"
BUDGET_PATH = CACHE_DIR / "nyt_budget.json"

RATE_LIMIT_PAUSE = 12.5  # 5/min == one per 12s; 0.5s of margin
NYT_DAILY_CAP = 500
NYT_SAFETY_CAP = 400  # stop here, well clear of the real cap
NYT_PER_WARM_BUDGET = 6
NYT_MAX_PAGES_PER_CHUNK = 3
MAX_CHUNK = timedelta(days=365)  # coarser chunks = fewer requests

_budget_lock = threading.Lock()


def _scrub(msg: object) -> str:
    """Backwards-compatible alias for the shared config.scrub."""
    return scrub(msg)


# --------------------------------------------------------------------------- budget

def _today_et() -> str:
    return market.now_et().date().isoformat()


def budget_state() -> dict:
    """Requests spent today. Persisted so a restart cannot silently reset the count."""
    try:
        data = json.loads(BUDGET_PATH.read_text())
        if data.get("date") == _today_et():
            return {"date": data["date"], "used": int(data.get("used", 0))}
    except (OSError, ValueError, KeyError):
        pass
    return {"date": _today_et(), "used": 0}


def budget_remaining() -> int:
    return max(0, NYT_SAFETY_CAP - budget_state()["used"])


def _spend(n: int) -> None:
    with _budget_lock:
        state = budget_state()
        state["used"] += n
        BUDGET_PATH.parent.mkdir(parents=True, exist_ok=True)
        BUDGET_PATH.write_text(json.dumps(state))


def _reusable_term_cache(term: str) -> dict:
    """Every chunk already on disk for a search term, keyed by (begin, end, page)."""
    out: dict = {}
    prefix = re.sub(r"[^a-z0-9]+", "_", term.lower()).strip("_")
    if not prefix:
        return out
    for path in CHUNK_DIR.glob(f"{prefix}__*.json"):
        try:
            blob = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        out[(blob.get("cell"), blob["page"])] = blob["articles"]
    return out


# ------------------------------------------------------------------- chunk caching

def _chunk_path(term: str, cell: str, page: int) -> Path:
    """Cache path keyed by the canonical cell id, not the clipped query range."""
    slug = re.sub(r"[^a-z0-9]+", "_", term.lower()).strip("_")[:40]
    return CHUNK_DIR / f"{slug}__cell{cell}__p{page}.json"


def _read_chunk(term: str, cell: str, page: int) -> list[dict] | None:
    path = _chunk_path(term, cell, page)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())["articles"]
    except (OSError, ValueError, KeyError):
        path.unlink(missing_ok=True)
        return None


def _write_chunk(term: str, cell: str, begin: date, end: date, page: int,
                 articles: list[dict]) -> None:
    path = _chunk_path(term, cell, page)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"term": term, "cell": cell, "begin": begin.isoformat(), "end": end.isoformat(),
         "page": page, "fetched": time.strftime("%Y-%m-%dT%H:%M:%S"), "articles": articles}))


# ------------------------------------------------------------------------ fetching

def _to_utc_iso(value: str) -> str | None:
    """Normalise a NYT pub_date to a UTC ISO string.

    The API returns ISO-8601 with an offset, but downstream code calls .tz_convert("UTC"),
    which throws on a naive timestamp — so localise defensively instead of assuming.
    """
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("UTC").isoformat()


def _fetch_nyt(query: str, begin: date, end: date, page: int = 0) -> list[dict]:
    resp = requests.get(NYT_URL, timeout=20, params={
        "q": query,
        "begin_date": begin.strftime("%Y%m%d"),
        "end_date": end.strftime("%Y%m%d"),
        "sort": "newest",
        "page": page,
        "api-key": NYT_API_KEY,
    })
    resp.raise_for_status()
    docs = (resp.json().get("response") or {}).get("docs") or []
    out = []
    for d in docs:
        pub = _to_utc_iso(d.get("pub_date") or "")
        if not pub or not d.get("web_url"):
            continue
        out.append({
            "headline": (d.get("headline") or {}).get("main", "").strip(),
            "pub_date": pub,
            "url": d["web_url"],
            "snippet": d.get("abstract") or d.get("snippet") or "",
        })
    return out


def sample_articles(event: date, mode: str, symbol: str, company: str = "",
                    log=print, budget: int | None = None, on_progress=None) -> list[dict]:
    """Collect a spread of articles across the mode's window, reusing cached chunks.

    Returns whatever it can get. Exhausted budget or a rate-limited chunk yields a partial
    pool rather than an exception — a short timeline beats an error page.

    `on_progress` is called with the running article list after every cell, so a caller can
    publish partial results. A cold 5-year warm takes the better part of a minute at 5 req/min;
    without this the timeline would sit empty until the very end instead of filling in.
    """
    if not NYT_API_KEY:
        return []
    budget = NYT_PER_WARM_BUDGET if budget is None else budget
    begin, end = market.article_window(event, mode)
    term = short_company(company) or symbol
    cells = market.plan_cells(begin, end, budget)
    pages_each = max(1, min(NYT_MAX_PAGES_PER_CHUNK, budget // max(1, len(cells))))
    reusable = _reusable_term_cache(term)
    log(f"  timeline: {begin} → {end} · {len(cells)} cell(s) {','.join(c for c, _, _ in cells)} "
        f"· up to {pages_each} page(s) each · q={term!r}")

    by_url: dict[str, dict] = {}
    calls = cached = skipped = 0
    for cell, cb, ce in cells:
        for page in range(pages_each):
            hit = reusable.get((cell, page))
            if hit is None:
                hit = _read_chunk(term, cell, page)
            if hit is not None:
                cached += 1
                for a in hit:
                    by_url.setdefault(a["url"], a)
                if not hit:
                    break  # chunk exhausted; no point asking for later pages
                continue
            if calls >= budget:
                skipped += 1
                continue
            if budget_remaining() <= 0:
                log(f"  timeline: daily NYT budget spent ({NYT_SAFETY_CAP}/day); "
                    "serving cached chunks only")
                skipped += 1
                continue
            if calls:
                time.sleep(RATE_LIMIT_PAUSE)
            calls += 1
            _spend(1)
            try:
                found = _fetch_nyt(term, cb, ce, page)
            except requests.HTTPError as e:
                code = e.response.status_code if e.response is not None else 0
                if code in (429, 401, 403):
                    # Don't cache the failure: it should be retried once the quota resets.
                    log(f"  timeline: NYT rejected the request ({code}); "
                        f"{len(by_url)} cached article(s) kept")
                    skipped += 1
                    break
                log(f"  chunk {cb} page {page} failed: {_scrub(e)[:140]}")
                continue
            except requests.RequestException as e:
                log(f"  chunk {cb} page {page} failed: {_scrub(e)[:140]}")
                continue
            _write_chunk(term, cell, cb, ce, page, found)
            for a in found:
                by_url.setdefault(a["url"], a)
            if len(found) < 10:
                break  # short page means there are no more results in this chunk
        if on_progress is not None:
            on_progress(sorted(by_url.values(), key=lambda a: a["pub_date"]))
        if skipped and calls >= budget:
            break

    articles = sorted(by_url.values(), key=lambda a: a["pub_date"])
    log(f"  timeline: {len(articles)} article(s) from {calls} request(s), "
        f"{cached} chunk(s) reused, {skipped} skipped · NYT budget "
        f"{budget_state()['used']}/{NYT_SAFETY_CAP} today")
    return articles


# ------------------------------------------------------------------ name shortening

LEGAL_SUFFIXES = re.compile(
    r",?\s*\b(incorporated|inc|corp|corporation|co|company|plc|ltd|limited|llc|lp|holdings?|"
    r"group|technologies|technology|systems|international|sa|nv|ag|ab|as)\b\.?", re.I)

CONNECTORS = {"&", "and", "of", "the", "for", "de", "van", "von", "a", "an"}


def short_company(name: str, max_words: int = 3) -> str:
    """The name as a news outlet would actually write it.

    Searching the full legal name is very low recall against the NYT archive: the paper
    writes "Nvidia" and "Apple", not "NVIDIA Corporation" or "Apple Inc.". Stripping the
    legal suffix is the difference between ~40 hits over five years and a few hundred.
    Short names are kept whole so "Johnson & Johnson" does not become "Johnson &".
    """
    name = re.sub(r"\s+", " ", LEGAL_SUFFIXES.sub("", name or "").strip(" ,."))
    words = [w for w in name.split() if w]
    # Drop trailing connectors left behind by the suffix strip ("JPMorgan Chase & Co." -> "&").
    while words and words[-1].lower().strip(",.") in CONNECTORS:
        words.pop()
    if not words:
        return name
    if len(words) <= max_words:
        return " ".join(words)
    out = words[:max_words]
    while out and out[-1].lower().strip(",.") in CONNECTORS:
        out.pop()
    return " ".join(out)


def queries_for(symbol: str, company: str) -> list[str]:
    """Search terms for a ticker: the short company name plus the symbol itself."""
    short = short_company(company)
    out = [short] if short else []
    if symbol and symbol.lower() != short.lower():
        out.append(symbol)
    return out or [symbol]


# ------------------------------------------------------------- tight window (chart)

def fetch_and_store(event_date: date, symbol: str, company: str = "") -> list[dict]:
    if not NYT_API_KEY:
        raise RuntimeError("NYT_API_KEY is not set")
    begin, end = market.search_window(event_date)
    by_url = {}
    for i, q in enumerate(queries_for(symbol, company)):
        if i:
            time.sleep(RATE_LIMIT_PAUSE)
        _spend(1)
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
    if not NYT_API_KEY or budget_remaining() <= 0:
        return []
    try:
        return fetch_and_store(event_date, symbol, company)
    except Exception:
        return []  # never let a news failure take down the investigation


def _cache_path(symbol: str, event_date: date) -> Path:
    return CACHE_DIR / f"news_{symbol.upper()}_{event_date.isoformat()}.json"
