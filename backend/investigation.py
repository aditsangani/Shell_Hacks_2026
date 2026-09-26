"""Assembles one investigation bundle for the requested ticker and session."""

import pandas as pd

import analysis
import db
import market
import news
import prices
from config import MARKET_PROXY, sector_for

MODES = ("latest", "unusual")


def resolve_event(closes: pd.DataFrame, symbol: str, mode: str) -> tuple:
    """(event_date, most_recent_session) for the requested mode."""
    days = list(closes.index)
    latest = market.latest_session(days)
    if mode == "unusual":
        return market.unusual_session(closes[symbol].dropna()), latest
    return latest, latest


def _timing(pub_utc: pd.Timestamp, event) -> str:
    et = pub_utc.tz_convert(market.ET)
    if et.date() < event:
        return "before event day"
    if et.date() > event:
        return "after event day"
    minutes = et.hour * 60 + et.minute
    if minutes < 9 * 60 + 30:
        return "pre-market"
    return "during session" if minutes < 16 * 60 else "after close"


def _headlines(event, bar_times: pd.Series, symbol: str) -> list[dict]:
    out = []
    for i, a in enumerate(news.get_news(event, symbol), start=1):
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


def _intraday(event, closes: pd.DataFrame, symbols: list[str],
              fresh: bool = False) -> tuple[pd.DataFrame, str, str]:
    """(series, source, caveat). Degrades to daily-only if 5-min bars are gone."""
    start, end = market.window_bounds(closes.index, event)
    event_start = prices.market_day_start_utc(event)

    if db.ENABLED:
        try:
            df = db.divergence_series(symbols, event_start,
                                      prices.market_day_start_utc(start),
                                      prices.market_day_start_utc(end + pd.Timedelta(days=1)))
            if not df.empty:
                return df, "tiger_data", ""
        except Exception:
            pass  # Tiger Data only holds whatever was ingested; fall through to yfinance.

    try:
        bars = prices.intraday_bars(tuple(symbols), start, end, fresh=fresh)
    except Exception:
        return pd.DataFrame(columns=["time", "symbol", "pct"]), "unavailable", (
            "5-minute intraday bars are only retained by Yahoo for roughly the last 60 days, "
            "so this session can no longer be charted minute-by-minute. The daily comparison below is unaffected.")
    return analysis.pct_from_prev_close(bars, event_start), "yfinance", ""


def build(symbol: str, mode: str = "latest", company: str | None = None,
          fresh: bool = False) -> dict:
    symbol = symbol.strip().upper()
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")

    sector_name, sector_etf = sector_for(symbol)
    symbols = [symbol] + ([sector_etf] if sector_etf else []) + [MARKET_PROXY]

    closes = prices.daily_closes(tuple(symbols), fresh=fresh)
    event, latest = resolve_event(closes, symbol, mode)
    freshness = market.describe(event, mode, latest=latest)

    series, chart_source, chart_caveat = _intraday(event, closes, symbols, fresh=fresh)
    if series.empty:
        chart, bar_times = [], pd.Series([], dtype="datetime64[ns, UTC]")
    else:
        wide = series.pivot_table(index="time", columns="symbol", values="pct").sort_index()
        chart = [{"time": t.isoformat(),
                  **{s: round(float(v), 3) for s, v in row.items() if pd.notna(v)}}
                 for t, row in wide.iterrows()]
        bar_times = pd.Series(wide.index)

    company = company or prices.resolve_company(symbol)
    return {
        "symbol": symbol,
        "company": company,
        "sector_etf": sector_etf,
        "sector_name": sector_name,
        "sector_known": sector_etf is not None,
        "market": MARKET_PROXY,
        "mode": mode,
        "event_date": event.isoformat(),
        "event_label": freshness["event_label"],
        "event_short": freshness["event_short"],
        "freshness": freshness,
        "move": analysis.move_stats(closes[symbol].dropna(), event),
        "divergence": analysis.divergence(closes, event, symbol, sector_etf, MARKET_PROXY),
        "chart": chart,
        "chart_source": chart_source,
        "chart_caveat": chart_caveat,
        "headlines": _headlines(event, bar_times, symbol),
        "similar": analysis.similar_moves(closes[symbol].dropna(), event),
    }
