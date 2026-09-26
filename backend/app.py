"""FinSight API. Serves the built React app from ../frontend/dist in production."""

import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

import explain
import investigation
import market
import news
import prices
import timeline
import voice
from config import CACHE_TTL, PORT, scrub

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app = Flask(__name__, static_folder=None)
CORS(app)

_lock = threading.Lock()
# Keyed by (symbol, mode). A single global entry would serve one ticker's data to every
# other ticker, and would pin "live" figures for the life of the process.
_cache: dict = {}


def _key(symbol: str, mode: str) -> str:
    return f"{symbol.strip().upper()}:{mode}"


def _get_cached(key: str, ttl: int = CACHE_TTL):
    with _lock:
        hit = _cache.get(key)
    return hit[1] if hit and (ttl is None or time.time() - hit[0] < ttl) else None


def _set_cached(key: str, value) -> None:
    with _lock:
        _cache[key] = (time.time(), value)


def _investigation(symbol: str, mode: str, refresh: bool) -> dict:
    key = _key(symbol, mode)
    if not refresh:
        hit = _get_cached(key)
        if hit is not None:
            return hit
    inv = investigation.build(symbol, mode, fresh=refresh)
    _set_cached(key, inv)
    return inv


def _explanations(symbol: str, mode: str, refresh: bool) -> dict:
    key = f"{_key(symbol, mode)}:expl"
    if not refresh:
        hit = _get_cached(key)
        if hit is not None:
            return hit
    inv = _investigation(symbol, mode, refresh=refresh)
    result = explain.explain(inv)
    _set_cached(key, result)
    return result


def _timeline(symbol: str, mode: str, refresh: bool) -> dict:
    """Deliberately NOT response-cached.

    The payload is now built from disk in ~1ms and never touches the network, so caching it
    bought nothing — while actively breaking the polling loop: a cached "warming: true,
    pool: 0" response would be replayed for the whole TTL, so the UI would poll for minutes
    and never see the background warm land.
    """
    inv = _investigation(symbol, mode, refresh=False)
    return timeline.build(symbol, mode, inv, refresh=refresh)


def _args() -> tuple[str, str, bool]:
    symbol = (request.args.get("symbol") or "").strip()
    mode = (request.args.get("mode") or "latest").strip()
    refresh = bool(request.args.get("refresh"))
    if not symbol:
        raise ValueError("symbol is required")
    if mode not in investigation.MODES:
        raise ValueError(f"mode must be one of {investigation.MODES}")
    return symbol, mode, refresh


def _prefetch_timeline(symbol: str, mode: str, inv: dict) -> None:
    """Start warming the article pool in the background the moment an investigation is served.

    By the time the user opens the timeline the chunks are usually already cached, so the
    page renders instantly. Entirely best-effort: a failure here must not affect the
    investigation response.
    """
    try:
        # build() is disk-only and already owns the schema, cooldown, and missing-work
        # checks. Calling it here also warms Yahoo/SEC when NYT chunks are already cached.
        timeline.build(symbol, mode, inv, log=app.logger.info)
    except Exception:
        pass


@app.get("/api/health")
def health():
    return {"ok": True, "modes": list(investigation.MODES),
            "today": market.now_et().date().isoformat(),
            "nyt_budget": {"used": news.budget_state()["used"], "cap": news.NYT_SAFETY_CAP}}


@app.get("/api/search")
def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"results": []})
    return jsonify({"results": prices.search_symbols(q, limit=request.args.get("limit", 8))})


@app.get("/api/session")
def session_info():
    """Latest trading session for the UI to describe before any symbol is chosen."""
    try:
        closes = prices.daily_closes(("SPY",))
        latest = market.latest_session(closes.index)
        return jsonify(market.describe(latest, "latest", latest=latest))
    except Exception as e:
        return jsonify({"error": scrub(e)}), 502


@app.get("/api/investigation")
def get_investigation():
    try:
        symbol, mode, refresh = _args()
        inv = _investigation(symbol, mode, refresh)
        _prefetch_timeline(symbol, mode, inv)
        return jsonify(inv)
    except LookupError as e:
        return jsonify({"error": f"No price history for {request.args.get('symbol')!r}. "
                                 "Check the ticker and that it is a traded US symbol."}), 404
    except ValueError as e:
        return jsonify({"error": scrub(e)}), 400
    except Exception as e:
        return jsonify({"error": scrub(e)}), 502


@app.get("/api/explanations")
def get_explanations():
    try:
        symbol, mode, refresh = _args()
        return jsonify(_explanations(symbol, mode, refresh))
    except ValueError as e:
        return jsonify({"error": scrub(e)}), 400
    except Exception as e:  # surface missing keys / model errors to the UI instead of a 500 page
        return jsonify({"error": scrub(e)}), 502


@app.get("/api/briefing.mp3")
def get_briefing():
    try:
        symbol, mode, refresh = _args()
        inv = _investigation(symbol, mode, refresh)
    except LookupError:
        return jsonify({"error": f"No price history for {request.args.get('symbol')!r}."}), 404
    except ValueError as e:
        return jsonify({"error": scrub(e)}), 400
    except Exception as e:
        return jsonify({"error": scrub(e)}), 502
    try:
        exp = _explanations(symbol, mode, refresh=False)
    except Exception:
        exp = None  # Gemini down or out of quota: still brief on the numbers
    try:
        audio = voice.synthesize(voice.briefing_script(inv, exp))
    except Exception as e:
        return jsonify({"error": scrub(e)}), 502
    return Response(audio, mimetype="audio/mpeg")


@app.get("/api/timeline")
def get_timeline():
    """Article timeline for the mode's window: 6 months for latest, 5 years for unusual.

    Returns cached data immediately. Sampling is rate-limited to ~5 req/min, so a cold warm
    runs on a background thread and the response reports `warming: true` — poll until it
    clears. Pre-warm with `ingest.py <symbol> <mode> --timeline`.
    """
    try:
        symbol, mode, refresh = _args()
        return jsonify(_timeline(symbol, mode, refresh))
    except ValueError as e:
        return jsonify({"error": scrub(e)}), 400
    except Exception as e:
        return jsonify({"error": scrub(e)}), 502


@app.post("/api/timeline/warm")
def warm_timeline():
    """Start a background warm and return immediately."""
    try:
        symbol, mode, _refresh = _args()
        inv = _investigation(symbol, mode, refresh=False)
        todo = timeline.missing_chunks(_event_date(inv), symbol, mode, inv["company"])
        started = timeline.start_warm(symbol, mode, inv, log=app.logger.info)
    except ValueError as e:
        return jsonify({"error": scrub(e)}), 400
    except Exception as e:
        return jsonify({"error": scrub(e)}), 502
    return jsonify({"ok": True, "started": started, "pending_requests": todo,
                    "job": timeline.job_state(symbol, mode)})


def _event_date(inv: dict):
    from datetime import date
    return date.fromisoformat(inv["event_date"])


@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def frontend(path):
    if path and (DIST / path).is_file():
        return send_from_directory(DIST, path)
    if (DIST / "index.html").is_file():
        return send_from_directory(DIST, "index.html")
    return "Frontend not built. Run `npm run build` in frontend/, or use `npm run dev`.", 404


if __name__ == "__main__":
    app.run(port=PORT, debug=True)
