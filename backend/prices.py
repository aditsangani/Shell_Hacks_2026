"""yfinance fetchers. 5-min intraday is only available for the last ~60 days."""

from datetime import date, timedelta
from functools import lru_cache

import pandas as pd
import yfinance as yf

from config import MARKET_TZ


@lru_cache(maxsize=4)
def daily_closes(symbols: tuple[str, ...], period: str = "5y") -> pd.DataFrame:
    """Adjusted daily closes, one column per symbol, index = trading date."""
    df = yf.download(list(symbols), period=period, interval="1d",
                     auto_adjust=True, progress=False)["Close"]
    df.index = pd.to_datetime(df.index).date
    return df.dropna(how="all")


@lru_cache(maxsize=4)
def intraday_bars(symbols: tuple[str, ...], start: date, end: date) -> pd.DataFrame:
    """Long-format 5-min bars: columns time (UTC), symbol, price, volume."""
    raw = yf.download(list(symbols), start=start.isoformat(),
                      end=(end + timedelta(days=1)).isoformat(),
                      interval="5m", auto_adjust=True, progress=False)
    frames = []
    for sym in symbols:
        part = pd.DataFrame({
            "time": raw.index.tz_convert("UTC"),
            "symbol": sym,
            "price": raw["Close"][sym].values,
            "volume": raw["Volume"][sym].values,
        }).dropna(subset=["price"])
        frames.append(part)
    return pd.concat(frames, ignore_index=True)


def session_window(event_date: date, closes: pd.DataFrame) -> tuple[date, date]:
    """Prior trading session through the session after the event (if it exists)."""
    days = list(closes.index)
    i = days.index(event_date)
    return days[max(i - 1, 0)], days[min(i + 1, len(days) - 1)]


def market_day_start_utc(d: date) -> pd.Timestamp:
    return pd.Timestamp(d, tz=MARKET_TZ).tz_convert("UTC")
