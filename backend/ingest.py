"""Load a ticker's session into Tiger Data, and optionally warm the article timeline.

Usage:  python ingest.py                       (default ticker, latest session)
        python ingest.py NVDA unusual          (ticker + which session to chart)
        python ingest.py NVDA --no-news        (skip the NYT call to save quota)
        python ingest.py NVDA unusual --timeline   (also warm the 5-year article pool)

--timeline is what you want before a demo: sampling a 5-year window costs one rate-limited
NYT request per 6-month chunk, which is far too slow to do while someone is watching.

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
import timeline
from config import MARKET_PROXY, sector_for

DEFAULT_SYMBOL = "META"


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = {a for a in sys.argv[1:] if a.startswith("-")}

    symbol = (args[0] if args else DEFAULT_SYMBOL).strip().upper()
    mode = args[1] if len(args) > 1 and not args[1].startswith("-") else "latest"
    if mode not in investigation.MODES:
        sys.exit(f"mode must be one of {investigation.MODES}")

    sector_name, sector_etf = sector_for(symbol)
    symbols = [symbol] + ([sector_etf] if sector_etf else []) + [MARKET_PROXY]

    closes = prices.daily_closes(tuple(symbols))
    event, _latest = investigation.resolve_event(closes, symbol, mode)
    company = prices.resolve_company(symbol)
    print(f"{symbol} ({company}) · {sector_name or 'no sector map'} · session {event} ({mode})")

    if "--timeline" in flags:
        pool = timeline.collect(event, symbol, mode, company)
        begin, end = market.article_window(event, mode)
        print(f"timeline pool: {len(pool)} articles cached for {begin} → {end}")
        print("  (run the app and open the timeline to have Gemini triage them)")

    if db.ENABLED:
        start, end = market.window_bounds(closes.index, event)
        db.init_schema()
        # One extra session of lead-in so the pre-event close is always in the aggregate.
        bars = prices.intraday_bars(tuple(symbols), start - timedelta(days=5), end)
        print(f"price_ticks: inserted {db.insert_ticks(bars)} rows for {', '.join(symbols)}")

        db.refresh_aggregate(bars["time"].min().to_pydatetime(),
                             (bars["time"].max() + timedelta(minutes=5)).to_pydatetime())
        print("price_5min: continuous aggregate refreshed")

        if "--no-news" not in flags and "--timeline" not in flags:
            articles = news.fetch_and_store(event, symbol, company)
            print(f"news_events: {len(articles)} NYT headlines for {symbol}")

    elif "--timeline" not in flags:
        print("DATABASE_URL is not set — skipping Tiger Data ingest.")


if __name__ == "__main__":
    main()
