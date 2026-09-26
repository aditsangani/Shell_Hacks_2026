"""Load the demo event into Tiger Data: 5-min bars -> price_ticks, NYT headlines -> news_events.

Usage:  python ingest.py            (prices + news)
        python ingest.py --no-news  (skip the NYT call to save quota)
"""

import sys
from datetime import timedelta

import db
import news
import prices
from config import DEMO, SYMBOLS
from investigation import event_date


def main() -> None:
    if not db.ENABLED:
        sys.exit("DATABASE_URL is not set — nothing to ingest into.")
    event = event_date()

    db.init_schema()
    closes = prices.daily_closes(tuple(SYMBOLS))
    start, end = prices.session_window(event, closes)
    bars = prices.intraday_bars(tuple(SYMBOLS), start - timedelta(days=5), end)
    print(f"price_ticks: inserted {db.insert_ticks(bars)} rows for {', '.join(SYMBOLS)}")

    db.refresh_aggregate(bars["time"].min().to_pydatetime(),
                         (bars["time"].max() + timedelta(minutes=5)).to_pydatetime())
    print("price_5min: continuous aggregate refreshed")

    if "--no-news" not in sys.argv:
        articles = news.fetch_and_store(event)
        print(f"news_events: {len(articles)} NYT headlines for {DEMO['symbol']}")


if __name__ == "__main__":
    main()
