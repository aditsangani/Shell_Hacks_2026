"""Unusualness, divergence, and historical-similarity math on daily closes."""

from datetime import date

import numpy as np
import pandas as pd

FORWARD_DAYS = (1, 5, 20)


def daily_returns(closes: pd.Series) -> pd.Series:
    return (closes.pct_change() * 100).dropna()


def move_stats(closes: pd.Series, event_date: date) -> dict:
    """How unusual is the event-day move vs the prior 5 years of daily moves."""
    rets = daily_returns(closes)
    move = float(rets.loc[event_date])
    history = rets.loc[rets.index < event_date]

    percentile = float((history.abs() < abs(move)).mean() * 100)
    z = float((move - history.mean()) / history.std())

    same_or_bigger = history[(np.sign(history) == np.sign(move)) & (history.abs() >= abs(move))]
    last_bigger = same_or_bigger.index[-1] if len(same_or_bigger) else None

    # 1%-wide bins for the distribution chart; tails clipped into the edge bins.
    edge = max(12, int(np.ceil(abs(move))) + 1)
    bins = np.arange(-edge, edge + 1, 1.0)
    with_event = pd.concat([history, rets.loc[[event_date]]])
    counts, _ = np.histogram(with_event.clip(-edge + 0.01, edge - 0.01), bins=bins)

    return {
        "histogram": [{"x0": float(b), "count": int(c)} for b, c in zip(bins[:-1], counts)],
        "move_pct": round(move, 2),
        "percentile": round(percentile, 1),
        "z_score": round(z, 2),
        "history_days": int(len(history)),
        "history_start": history.index[0].isoformat(),
        "typical_abs_move": round(float(history.abs().median()), 2),
        "bigger_moves_count": int((history.abs() >= abs(move)).sum()),
        "largest_since": last_bigger.isoformat() if last_bigger else None,
        "largest_since_move": round(float(same_or_bigger.iloc[-1]), 2) if last_bigger else None,
    }


def divergence(closes: pd.DataFrame, event_date: date, symbol: str, sector: str, market: str) -> dict:
    """Ticker vs sector ETF vs SPY on the event day, plus a beta-adjusted expected move."""
    rets = closes.pct_change() * 100
    day = rets.loc[event_date]

    trailing = rets.loc[rets.index < event_date].tail(252).dropna()
    beta = float(np.cov(trailing[symbol], trailing[market])[0, 1] / trailing[market].var())
    expected = beta * float(day[market])

    return {
        "ticker_pct": round(float(day[symbol]), 2),
        "sector_pct": round(float(day[sector]), 2),
        "market_pct": round(float(day[market]), 2),
        "excess_vs_sector": round(float(day[symbol] - day[sector]), 2),
        "excess_vs_market": round(float(day[symbol] - day[market]), 2),
        "beta_1y": round(beta, 2),
        "beta_expected_pct": round(expected, 2),
        "idiosyncratic_pct": round(float(day[symbol]) - expected, 2),
    }


def similar_moves(closes: pd.Series, event_date: date, n: int = 3) -> list[dict]:
    """Past days with the closest same-direction move, and what the stock did afterwards."""
    rets = daily_returns(closes)
    move = rets.loc[event_date]
    positions = {d: i for i, d in enumerate(closes.index)}

    candidates = rets.loc[(rets.index < event_date) & (np.sign(rets) == np.sign(move))]
    closest = (candidates - move).abs().sort_values().index[:n]

    out = []
    for d in sorted(closest, reverse=True):
        i = positions[d]
        fwd = {}
        for k in FORWARD_DAYS:
            j = i + k
            fwd[f"d{k}"] = (round(float((closes.iloc[j] / closes.iloc[i] - 1) * 100), 2)
                            if j < len(closes) and closes.index[j] < event_date else None)
        out.append({"date": d.isoformat(), "move_pct": round(float(rets.loc[d]), 2), **fwd})
    return out


def pct_from_prev_close(bars: pd.DataFrame, event_start_utc: pd.Timestamp) -> pd.DataFrame:
    """Pandas fallback for db.divergence_series when Tiger Data isn't configured."""
    out = []
    for sym, g in bars.sort_values("time").groupby("symbol"):
        prev = g.loc[g["time"] < event_start_utc, "price"]
        if prev.empty:
            continue
        base = prev.iloc[-1]
        out.append(pd.DataFrame({"time": g["time"], "symbol": sym,
                                 "pct": (g["price"] - base) / base * 100}))
    return pd.concat(out, ignore_index=True)
