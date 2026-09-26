"""Assembles one investigation bundle for the demo event."""

from datetime import date, timedelta

import pandas as pd

import analysis
import db
import news
import prices
from config import DEMO, MARKET_TZ, SYMBOLS


def event_date() -> date:
    return date.fromisoformat(DEMO["event_date"])


def _timing(pub_utc: pd.Timestamp, event: date) -> str:
    et = pub_utc.tz_convert(MARKET_TZ)
    if et.date() < event:
        return "before event day"
    if et.date() > event:
        return "after event day"
    minutes = et.hour * 60 + et.minute
    if minutes < 9 * 60 + 30:
        return "pre-market"
    return "during session" if minutes < 16 * 60 else "after close"


def _headlines(event: date, bar_times: pd.Series) -> list[dict]:
    out = []
    for i, a in enumerate(news.get_news(event), start=1):
        pub = pd.Timestamp(a["pub_date"]).tz_convert("UTC")
        # Pin each headline to the first bar at/after publication: when the market could react.
        later = bar_times[bar_times >= pub]
        out.append({
            **a,
            "id": f"H{i}",
            "pub_date": pub.isoformat(),
            "timing": _timing(pub, event),
            "chart_time": later.iloc[0].isoformat() if len(later) else None,
        })
    return out


def _intraday(event: date, closes: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    start, end = prices.session_window(event, closes)
    event_start = prices.market_day_start_utc(event)
    if db.ENABLED:
        df = db.divergence_series(SYMBOLS, event_start,
                                  prices.market_day_start_utc(start),
                                  prices.market_day_start_utc(end + timedelta(days=1)))
        if not df.empty:
            return df, "tiger_data"
    bars = prices.intraday_bars(tuple(SYMBOLS), start, end)
    return analysis.pct_from_prev_close(bars, event_start), "yfinance"


def build() -> dict:
    event = event_date()
    closes = prices.daily_closes(tuple(SYMBOLS))
    sym = DEMO["symbol"]

    series, chart_source = _intraday(event, closes)
    wide = series.pivot_table(index="time", columns="symbol", values="pct").sort_index()
    chart = [{"time": t.isoformat(), **{s: round(float(v), 3) for s, v in row.items() if pd.notna(v)}}
             for t, row in wide.iterrows()]

    return {
        "symbol": sym,
        "company": DEMO["company"],
        "sector_etf": DEMO["sector_etf"],
        "sector_name": DEMO["sector_name"],
        "market": DEMO["market"],
        "event_date": event.isoformat(),
        "event_label": f"{event:%A, %B} {event.day}",
        "move": analysis.move_stats(closes[sym].dropna(), event),
        "divergence": analysis.divergence(closes, event, sym, DEMO["sector_etf"], DEMO["market"]),
        "chart": chart,
        "chart_source": chart_source,
        "headlines": _headlines(event, pd.Series(wide.index)),
        "similar": analysis.similar_moves(closes[sym].dropna(), event),
    }
