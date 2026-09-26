-- Tiger Data (TimescaleDB). Idempotent: safe to run on every ingest.

CREATE TABLE IF NOT EXISTS price_ticks (
  time   TIMESTAMPTZ NOT NULL,
  symbol TEXT        NOT NULL,
  price  NUMERIC,
  volume BIGINT
);
SELECT create_hypertable('price_ticks', 'time', if_not_exists => TRUE);
CREATE UNIQUE INDEX IF NOT EXISTS price_ticks_symbol_time ON price_ticks (symbol, time);

-- Continuous aggregate: 5-min OHLC-style bars, materialized so the divergence
-- chart reads precomputed rows instead of scanning raw ticks per request.
-- (A per-bucket last/first pct_change would always be 0 on 5-min source bars,
-- so we store open/close and compute cumulative % vs prior close at query time.)
CREATE MATERIALIZED VIEW IF NOT EXISTS price_5min
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('5 minutes', time) AS bucket,
  symbol,
  first(price, time) AS open,
  last(price, time)  AS close,
  sum(volume)        AS volume
FROM price_ticks
GROUP BY bucket, symbol
WITH NO DATA;

CREATE TABLE IF NOT EXISTS news_events (
  id       SERIAL PRIMARY KEY,
  symbol   TEXT,
  headline TEXT,
  pub_date TIMESTAMPTZ,
  url      TEXT UNIQUE,
  snippet  TEXT
);
