"""Load a ticker's demo session into Tiger Data: 5-min bars -> price_ticks, NYT -> news_events.

Usage:  python ingest.py                       (default ticker, latest session)
        python ingest.py NVDA unusual          (ticker + which session to chart)
        python ingest.py NVDA --no-news        (skip the NYT call to save quota)

The event session is resolved exactly as the API resolves it, so the continuous aggregate
lines up with what /api/investigation later asks for.
"""

import sys
from datetime import timedelta

import db
import investigation
import market
import news
import prices
from config import MARKET_PROXY, sector_for

DEFAULT_SYMBOL = "META"


def main() -> None:
    if not db.ENABLED:
        sys.exit("DATABASE_URL is not set — nothing to ingest into.")
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = {a for a in sys.argv[1:] if a.startswith("-")}

    symbol = (args[0] if args else DEFAULT_SYMBOL).strip().upper()
    mode = args[1] if len(args) > 1 else "latest"
    if mode not in investigation.MODES:
        sys.exit(f"mode must be one of {investigation.MODES}")

    sector_name, sector_etf = sector_for(symbol)
    symbols = [symbol] + ([sector_etf] if sector_etf else []) + [MARKET_PROXY]

    closes = prices.daily_closes(tuple(symbols))
    event, _latest = investigation.resolve_event(closes, symbol, mode)
    start, end = market.window_bounds(closes.index, event)
    print(f"{symbol} · {sector_name or 'no sector map'} · session {event} ({mode})")

    db.init_schema()
    # One extra session of lead-in so the pre-event close is always in the aggregate.
    bars = prices.intraday_bars(tuple(symbols), start - timedelta(days=5), end)
    print(f"price_ticks: inserted {db.insert_ticks(bars)} rows for {', '.join(symbols)}")

    db.refresh_aggregate(bars["time"].min().to_pydatetime(),
                         (bars["time"].max() + timedelta(minutes=5)).to_pydatetime())
    print("price_5min: continuous aggregate refreshed")

    if "--no-news" not in flags:
        company = prices.resolve_company(symbol)
        articles = news.fetch_and_store(event, symbol, company)
        print(f"news_events: {len(articles)} NYT headlines for {symbol} ({company})")


if __name__ == "__main__":
    main()
