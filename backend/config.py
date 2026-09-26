"""Runtime configuration.

The investigation target is chosen at request time (any ticker, either the latest session
or the most unusual recent one), so there is no hardcoded demo symbol here. Only the
market proxy, the sector map and the API keys are fixed.
"""

import os
import re

from dotenv import load_dotenv

load_dotenv()

MARKET_TZ = "America/New_York"
MARKET_PROXY = "SPY"

# How far back to hunt for the most unusual session when mode=unusual.
UNUSUAL_WINDOW = 30  # trading days

# Repeat searches for the same ticker inside this window reuse the cached bundle.
# Yahoo rate-limits hard, so a virgin fetch on every keystroke is not an option.
CACHE_TTL = 300  # seconds

# GICS sector -> Select Sector SPDR. Used for the "company vs sector vs market" panel.
SECTOR_ETFS = {
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Information Technology": "XLK",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}

# Yahoo's sector field is not reachable without a slow, rate-limited .info call, so the
# large caps are mapped by hand. Symbols missing here simply get no sector line
# (the investigation still runs, compared against SPY only).
TICKER_SECTORS = {
    "AAPL": "Information Technology", "MSFT": "Information Technology",
    "NVDA": "Information Technology", "AVGO": "Information Technology",
    "CRM": "Information Technology", "ORCL": "Information Technology",
    "ADBE": "Information Technology", "CSCO": "Information Technology",
    "INTC": "Information Technology", "AMD": "Information Technology",
    "TXN": "Information Technology", "QCOM": "Information Technology",
    "IBM": "Information Technology", "ACN": "Information Technology",
    "NFLX": "Communication Services", "DIS": "Communication Services",
    "CMCSA": "Communication Services", "T": "Communication Services",
    "VZ": "Communication Services", "META": "Communication Services",
    "GOOGL": "Communication Services", "GOOG": "Communication Services",
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    "HD": "Consumer Discretionary", "MCD": "Consumer Discretionary",
    "NKE": "Consumer Discretionary", "SBUX": "Consumer Discretionary",
    "LOW": "Consumer Discretionary", "BKNG": "Consumer Discretionary",
    "PG": "Consumer Staples", "KO": "Consumer Staples",
    "PEP": "Consumer Staples", "COST": "Consumer Staples",
    "WMT": "Consumer Staples", "PM": "Consumer Staples",
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "SLB": "Energy",
    "JPM": "Financials", "BAC": "Financials", "WFC": "Financials",
    "GS": "Financials", "MS": "Financials", "V": "Financials",
    "MA": "Financials", "AXP": "Financials", "SCHW": "Financials",
    "BLK": "Financials", "SPGI": "Financials",
    "JNJ": "Health Care", "UNH": "Health Care", "LLY": "Health Care",
    "PFE": "Health Care", "ABBV": "Health Care", "MRK": "Health Care",
    "TMO": "Health Care", "ABT": "Health Care", "ISRG": "Health Care",
    "CAT": "Industrials", "BA": "Industrials", "GE": "Industrials",
    "HON": "Industrials", "UPS": "Industrials", "LMT": "Industrials",
    "DE": "Industrials", "RTX": "Industrials", "UNP": "Industrials",
    "LIN": "Materials", "SHW": "Materials", "APD": "Materials",
    "FCX": "Materials", "NEM": "Materials",
    "PLD": "Real Estate", "AMT": "Real Estate", "SPG": "Real Estate",
    "O": "Real Estate", "DLR": "Real Estate", "EQIX": "Real Estate",
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities",
    "D": "Utilities", "AEP": "Utilities", "EXC": "Utilities",
    "BRK-B": "Financials", "BRK.B": "Financials", "BF-B": "Financials",
}

# Sector-ETF lookup for the market proxy itself is meaningless (SPY is not a sector).
NO_SECTOR = {MARKET_PROXY} | {v for v in SECTOR_ETFS.values()}


def sector_for(symbol: str) -> tuple[str | None, str | None]:
    """(sector_name, sector_etf) for a symbol, or (None, None) when unknown.

    None means "run the investigation without a sector line" rather than guessing a
    wrong sector — a wrong comparison is worse than no comparison.
    """
    if symbol in NO_SECTOR:
        return None, None
    sector = TICKER_SECTORS.get(symbol.upper())
    if not sector:
        return None, None
    return sector, SECTOR_ETFS[sector]


DATABASE_URL = os.getenv("DATABASE_URL", "")
NYT_API_KEY = os.getenv("NYT_API_KEY", "")
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "FinSight educational research app")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")

# PORT is set by the Docker image for gunicorn; 5001 locally because macOS AirPlay
# Receiver occupies 5000 and answers 403 to every request.
PORT = int(os.getenv("PORT", 5001))

_SECRETS = (DATABASE_URL, NYT_API_KEY, GEMINI_API_KEY, ELEVENLABS_API_KEY)


def scrub(msg) -> str:
    """Redact every configured secret from a message.

    The NYT key travels as a query parameter, so requests' HTTPError text embeds a URL
    containing it verbatim. Exception text reaches log files and JSON responses, so it gets
    redacted in one place instead of trusting every call site to remember.
    """
    text = str(msg)
    for secret in _SECRETS:
        if secret and len(secret) > 8:
            text = text.replace(secret, "***")
    # Also catch key-shaped query params from any provider, present or future.
    return re.sub(r"((?:api[-_]?key|key|token)=)[^&\s\"']+", r"\1***", text, flags=re.I)
