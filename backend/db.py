"""Tiger Data access. If DATABASE_URL is unset, callers fall back to in-memory pandas."""

from pathlib import Path

import pandas as pd
import psycopg

from config import DATABASE_URL

ENABLED = bool(DATABASE_URL) and "<host>" not in DATABASE_URL
SCHEMA = (Path(__file__).parent / "schema.sql").read_text()


def connect(autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, autocommit=autocommit)


def init_schema() -> None:
    # CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous) can't run in a transaction.
    with connect(autocommit=True) as conn:
        for stmt in SCHEMA.split(";"):
            if stmt.strip() and not all(l.strip().startswith("--") for l in stmt.strip().splitlines()):
                conn.execute(stmt)


def insert_ticks(bars: pd.DataFrame) -> int:
    rows = [(r.time.to_pydatetime(), r.symbol, float(r.price), int(r.volume))
            for r in bars.itertuples()]
    with connect() as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO price_ticks (time, symbol, price, volume) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (symbol, time) DO NOTHING", rows)
    return len(rows)


def refresh_aggregate(start, end) -> None:
    with connect(autocommit=True) as conn:
        conn.execute("CALL refresh_continuous_aggregate('price_5min', %s, %s)", (start, end))


DIVERGENCE_SQL = """
WITH base AS (
  SELECT DISTINCT ON (symbol) symbol, close AS prev_close
  FROM price_5min
  WHERE symbol = ANY(%(symbols)s) AND bucket < %(event_start)s
  ORDER BY symbol, bucket DESC
)
SELECT p.bucket AS time, p.symbol,
       (p.close - b.prev_close) / b.prev_close * 100 AS pct
FROM price_5min p JOIN base b USING (symbol)
WHERE p.bucket >= %(start)s AND p.bucket < %(end)s
ORDER BY p.bucket, p.symbol
"""


def divergence_series(symbols, event_start, start, end) -> pd.DataFrame:
    """Cumulative % vs the pre-event close, served from the continuous aggregate."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(DIVERGENCE_SQL, {"symbols": list(symbols), "event_start": event_start,
                                     "start": start, "end": end})
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["time", "symbol", "pct"])
    df["pct"] = df["pct"].astype(float)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def upsert_news(symbol: str, articles: list[dict]) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO news_events (symbol, headline, pub_date, url, snippet) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (url) DO NOTHING",
            [(symbol, a["headline"], a["pub_date"], a["url"], a["snippet"]) for a in articles])


def load_news(symbol: str, start, end) -> list[dict]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT headline, pub_date, url, snippet FROM news_events "
            "WHERE symbol = %s AND pub_date >= %s AND pub_date < %s ORDER BY pub_date",
            (symbol, start, end))
        return [{"headline": h, "pub_date": p.isoformat(), "url": u, "snippet": s}
                for h, p, u, s in cur.fetchall()]
