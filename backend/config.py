"""Demo configuration. One ticker, one event — deliberately not multi-ticker."""

import os

from dotenv import load_dotenv

load_dotenv()

DEMO = {
    "symbol": "META",
    "company": "Meta Platforms",
    "sector_etf": "XLC",
    "sector_name": "Communication Services",
    "market": "SPY",
    # Mon 2026-09-21: META +11.43% vs XLC +3.90% vs SPY +1.55%
    "event_date": os.getenv("DEMO_EVENT_DATE", "2026-09-21"),
    # NYT q= searches run separately and are merged/deduped by URL.
    "news_queries": ["Meta Platforms", "Zuckerberg"],
}

SYMBOLS = [DEMO["symbol"], DEMO["sector_etf"], DEMO["market"]]
MARKET_TZ = "America/New_York"

DATABASE_URL = os.getenv("DATABASE_URL", "")
NYT_API_KEY = os.getenv("NYT_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")
