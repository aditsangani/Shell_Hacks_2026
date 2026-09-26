"""yfinance fetchers: ticker lookup, daily history, and 5-min intraday bars.

5-minute intraday is only available for roughly the last 60 days, so an "unusual session"
search has to stay inside that window (see UNUSUAL_WINDOW in config.py).
"""

from datetime import date, timedelta
from functools import wraps
import threading
import time as _time

import pandas as pd
import yfinance as yf

from config import CACHE_TTL, MARKET_TZ

# Yahoo's search happily returns single-stock futures and leveraged ETFs alongside the
# equity you meant. Equities and plain ETFs only, in that order.
QUOTE_TYPES = ("EQUITY", "ETF")

# Yahoo also returns Toronto/Frankfurt/London lines for US tickers. A demo audience means
# the US listing, so those are deprioritised rather than hidden.
US_EXCHANGES = {"NMS", "NYQ", "PCX", "ASE", "NGM", "NCM", "BTS", "PNK", "OQB", "OQX", "BSE"}


def ttl_cache(fn):
    """Memoise a fetcher for CACHE_TTL seconds, with an explicit `fresh=True` escape hatch.

    functools.lru_cache cannot expire, so a plain @lru_cache would pin today's *partial*
    daily bar for the life of the process and a mid-session Refresh would silently return
    stale numbers. `fresh=True` re-fetches and re-primes the entry.
    """
    store: dict = {}
    lock = threading.Lock()

    @wraps(fn)
    def wrapper(*args, fresh: bool = False, **kwargs):
        key = (args, tuple(sorted(kwargs.items())))
        now = _time.time()
        if not fresh:
            with lock:
                hit = store.get(key)
            if hit and now - hit[0] < CACHE_TTL:
                return hit[1]
        value = fn(*args, **kwargs)
        with lock:
            store[key] = (now, value)
        return value

    wrapper.cache_clear = store.clear
    return wrapper


def _close_frame(raw: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
    """yfinance drops a level from the column index for single-ticker requests."""
    close = raw["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(name=symbols[0])
    missing = [s for s in symbols if s not in close.columns]
    if missing:
        raise LookupError(f"no price data for {', '.join(missing)}")
    return close


@ttl_cache
def daily_closes(symbols: tuple[str, ...], period: str = "5y") -> pd.DataFrame:
    """Adjusted daily closes, one column per symbol, index = trading date."""
    df = yf.download(list(symbols), period=period, interval="1d",
                     auto_adjust=True, progress=False)
    if df.empty:
        raise LookupError(f"no daily history for {', '.join(symbols)}")
    out = _close_frame(df, list(symbols))
    out.index = pd.to_datetime(out.index).date
    out = out.dropna(how="all")
    # An unknown/delisted ticker comes back as a column of NaNs rather than an empty
    # frame, so every requested symbol has to be checked explicitly.
    for sym in symbols:
        if out[sym].notna().sum() < 30:
            raise LookupError(f"no usable price history for {sym}")
    return out


@ttl_cache
def intraday_bars(symbols: tuple[str, ...], start: date, end: date) -> pd.DataFrame:
    """Long-format 5-min bars: columns time (UTC), symbol, price, volume."""
    raw = yf.download(list(symbols), start=start.isoformat(),
                      end=(end + timedelta(days=1)).isoformat(),
                      interval="5m", auto_adjust=True, progress=False)
    if raw.empty:
        raise LookupError("no intraday data for that session")
    close = _close_frame(raw, list(symbols))
    volume = raw["Volume"]
    if not isinstance(volume, pd.DataFrame):
        volume = volume.to_frame(name=symbols[0])
    frames = []
    for sym in symbols:
        part = pd.DataFrame({
            "time": raw.index.tz_convert("UTC"),
            "symbol": sym,
            "price": close[sym].values,
            "volume": volume[sym].values if sym in volume.columns else 0,
        }).dropna(subset=["price"])
        frames.append(part)
    return pd.concat(frames, ignore_index=True)


def market_day_start_utc(d: date) -> pd.Timestamp:
    return pd.Timestamp(d, tz=MARKET_TZ).tz_convert("UTC")


def search_symbols(query: str, limit: int = 8) -> list[dict]:
    """Typeahead over Yahoo quotes. Fuzzy, so 'nvid' finds NVDA."""
    query = (query or "").strip()
    if not query:
        return []
    res = yf.Search(query, max_results=max(limit * 3, 12), news_count=0,
                    lists_count=0, enable_fuzzy_query=True, raise_errors=False)
    out, seen = [], set()
    for q in res.quotes or []:
        sym = (q.get("symbol") or "").strip()
        if not sym or sym in seen or q.get("quoteType") not in QUOTE_TYPES:
            continue
        seen.add(sym)
        out.append({
            "symbol": sym,
            "name": q.get("longname") or q.get("shortname") or sym,
            "exchange": q.get("exchDisp") or "",
            "type": q.get("quoteType"),
            "us": (q.get("exchange") or "").upper() in US_EXCHANGES,
        })
        if len(out) >= limit:
            break
    out.sort(key=lambda r: not r["us"])
    return out[:limit]


def resolve_company(symbol: str, fallback: str = "") -> str:
    """Display name for a ticker, without the slow rate-limited .info call."""
    try:
        res = yf.Search(symbol, max_results=10, news_count=0, lists_count=0,
                        raise_errors=False)
    except Exception:
        return fallback or symbol
    for q in res.quotes or []:
        if (q.get("symbol") or "").upper() == symbol.upper():
            return q.get("longname") or q.get("shortname") or fallback or symbol
    return fallback or symbol
