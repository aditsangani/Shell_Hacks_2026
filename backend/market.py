"""Trading-session resolution and staleness disclosure.

The event date is derived from the trading days yfinance actually returns, never from the
calendar. That handles weekends *and* market holidays (Juneteenth, Thanksgiving, Christmas)
with one rule: the most recent day that has a bar. Whatever that turns out to be, the UI is
told about it so a stale investigation never looks like a live one.
"""

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from config import MARKET_TZ, UNUSUAL_WINDOW

ET = ZoneInfo(MARKET_TZ)
SESSION_OPEN = dtime(9, 30)
SESSION_CLOSE = dtime(16, 0)


def now_et() -> datetime:
    return datetime.now(ET)


def latest_session(trading_days) -> date:
    """The most recent day that has a price bar."""
    days = list(trading_days)
    if not days:
        raise ValueError("no trading days in the price history")
    return days[-1]


def unusual_session(closes: pd.Series, window: int = UNUSUAL_WINDOW) -> date:
    """Largest absolute close-to-close move in the last `window` trading days.

    Includes the final day so a big move *today* still wins over an older one.
    """
    rets = (closes.pct_change() * 100).dropna()
    if rets.empty:
        raise ValueError("no daily returns to choose from")
    day = rets.tail(window).abs().idxmax()
    return day if isinstance(day, date) else pd.Timestamp(day).date()


def session_complete(event: date) -> bool:
    """True once the regular session has closed on the event day."""
    now = now_et()
    if now.date() > event:
        return True
    if now.date() < event:
        return False
    return now.time() >= SESSION_CLOSE


def describe(event: date, mode: str, latest: date | None = None,
             today: date | None = None) -> dict:
    """How fresh is this investigation? Rendered verbatim in the UI.

    `latest` is the most recent day that actually traded, which is not always `today`.
    """
    today = today or now_et().date()
    latest = latest or today
    gap = (today - event).days
    base = {
        "event_date": event.isoformat(),
        "event_label": f"{event:%A, %B} {event.day}, {event.year}",
        "event_short": f"{event:%A, %B} {event.day}",
        "mode": mode,
        "today": today.isoformat(),
        "today_label": f"{today:%A, %B} {today.day}",
        "latest_session": latest.isoformat(),
        "latest_session_label": f"{latest:%A, %B} {latest.day}",
        "gap_days": gap,
        "is_live": False,
        "session_complete": session_complete(event),
        "note": "",
    }

    if event == today:
        if base["session_complete"]:
            base["note"] = f"Showing the completed session for {today:%a %b %d}."
        else:
            base["is_live"] = True
            base["note"] = (f"{today:%A} is a trading day and the session is still open "
                            f"(closes 4:00 PM ET). Figures are live and will change until the close.")
        return base

    if mode == "unusual":
        # Stale by design, not by accident — say so, and name the session we skipped.
        base["note"] = (f"Not the latest session. This is the most unusual session in the last "
                        f"{UNUSUAL_WINDOW} trading days ({event:%A, %B} {event.day}) — "
                        f"{gap} days ago. The latest session is {latest:%A, %B} {latest.day}.")
        return base

    # mode == "latest": the event is stale because the market is shut.
    weekend = today.weekday() >= 5
    why = ("it is the weekend and markets are closed" if weekend and gap <= 3
           else "markets are closed today for a holiday")
    base["note"] = (f"Today is {today:%A, %B} {today.day}, so this is the most recent completed "
                    f"session ({event:%A, %B} {event.day}) — {why}. Live data cannot change "
                    f"until the next open.")
    return base


def previous_session(trading_days, event: date) -> date | None:
    days = [d for d in trading_days if d < event]
    return days[-1] if days else None


def window_bounds(trading_days, event: date) -> tuple[date, date]:
    """(start, end) date bounds for an intraday fetch bracketing `event`."""
    idx = list(trading_days).index(event)
    lo = max(idx - 1, 0)
    hi = min(idx + 1, len(trading_days) - 1)
    return list(trading_days)[lo], list(trading_days)[hi]


def search_window(event: date) -> tuple[date, date]:
    """News window: a few days before the event through the day after.

    Catches a weekend-ahead-of-a-Monday-event release without pulling in stale news.
    """
    return event - timedelta(days=3), event + timedelta(days=1)
