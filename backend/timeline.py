"""Timeline: which published articles actually bear on this move, and why.

Articles are sampled across the mode's window (6 months for `latest`, 5 years for
`unusual`) — see news.sample_articles for why that needs chunking. Gemini then triages
them: it keeps only the ones that plausibly bear on the move, labels each as stock-specific
or market-wide, and says what it thinks happened.

The stock-specific vs market-wide verdict is NOT left to the model alone. `scope_verdict`
derives it from the beta-adjusted decomposition, and the model is asked to argue that
number rather than invent one — a headline is evidence, not a verdict.

**Nothing here blocks on the network.** `build()` returns whatever is already cached and, if
work remains, starts a background warm and reports `warming: true`. Sampling is rate-limited
to ~5 requests/minute, so a cold 5-year warm takes the better part of a minute; the user
should never sit through that. The UI polls until the job settles.
"""

import json
import threading
import time
from pathlib import Path

from google import genai
from google.genai import types

import market
import news
from config import GEMINI_API_KEY, GEMINI_MODEL, scrub

CACHE_DIR = Path(__file__).parent / ".cache"

SCOPES = {"stock": "Stock-specific", "sector": "Sector-wide", "market": "Market-wide"}
MAX_ARTICLES_IN_PROMPT = 140
SNIPPET_CHARS = 260
# After a triage attempt fails (usually a spent daily quota), leave it alone for a while
# instead of retrying on every page load.
TRIAGE_RETRY_COOLDOWN = 600  # seconds

PROMPT = """You are an equity research assistant building an evidence timeline for a
retail investor trying to understand one specific price move. You do NOT give investment
advice or predictions.

Stock: {company} ({symbol}) · Sector ETF {sector_etf} · Market proxy {market}
Investigated session: {event_date} — {symbol} {move_pct:+.2f}% close-to-close
  Bigger than {percentile}% of its daily moves over the prior {history_days} trading days (z {z_score}).
  Same day: {sector_line}
  Beta to {market} over 1y: {beta_1y} → market alone implies {beta_expected_pct:+.2f}%.
  Unexplained (idiosyncratic) part: {idiosyncratic_pct:+.2f}% of a {ticker_pct:+.2f}% move.
  Our own decomposition puts this at: {verdict} ({verdict_share} of the move is idiosyncratic).

ARTICLES (NYT, {window_days} days of coverage, ids are for citation)
{articles}

TASK
Pick the articles that genuinely bear on this move — news of earnings, guidance, product or
regulatory events, litigation, leadership change, analyst action, macro shocks. Ignore
routine coverage, opinion pieces with no new facts, and anything that cannot be connected to
the move.

Hard rules:
- A headline is evidence, not a verdict. Do not treat an article as the cause just because it
  exists. If the set contains no plausible catalyst, return an empty `events` list and say so.
- The verdict is given to you as {verdict}. Argue it from the data. Only disagree in `verdict_note`
  if the articles clearly point the other way, and explain why there.
- For each kept article give `scope`: "stock" if it concerns {symbol} specifically, "sector" if it
  is about its sector, "market" if it is a broad macro or market event.
- Articles published after the session can only be labelled as reaction, never as cause.
- `significance`: "high" if a judge should read it, "medium" if relevant background, "low" if weak.

Return JSON only:
{{"events": [{{"ref": str, "scope": "stock"|"sector"|"market", "significance": "high"|"medium"|"low",
   "why": str (one sentence on why it bears on this move), "thesis": str (one sentence)}}],
  "narrative": str (2-3 sentences on what the evidence as a whole supports),
  "verdict": "{verdict}", "verdict_note": str,
  "caveat": str}}
"""


def scope_verdict(div: dict) -> dict:
    """Stock-specific vs market-wide, from the beta-adjusted decomposition.

    Grounded in arithmetic rather than in the model's reading of a headline: the share of
    the move that the market's beta does not explain.
    """
    total = abs(div.get("ticker_pct") or 0.0)
    idio = abs(div.get("idiosyncratic_pct") or 0.0)
    if total < 1e-9:
        return {"verdict": "flat", "share": 0.0, "label": "No material move",
                "raw_share": 0.0, "against_market": False}
    raw = idio / total
    # The ratio can exceed 1 when the market's beta implies a move in the *opposite*
    # direction, which makes the move more stock-specific, not less. Clamp for display.
    share = min(1.0, raw)
    if share >= 0.6:
        verdict, label = "stock_specific", "Stock-specific"
    elif share <= 0.35:
        verdict, label = "market_wide", "Market-wide"
    else:
        verdict, label = "mixed", "Mixed"
    return {"verdict": verdict, "share": round(share, 3), "label": label,
            "raw_share": round(raw, 3), "against_market": raw > 1.0}


# ------------------------------------------------------------------ cached artefacts

def _pool_path(symbol: str, event, mode: str) -> Path:
    return CACHE_DIR / f"pool_{symbol.upper()}_{event}_{mode}.json"


def _triage_path(symbol: str, event, mode: str) -> Path:
    return CACHE_DIR / f"timeline_{symbol.upper()}_{event}_{mode}.json"


def _read_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _write_json(path: Path, blob) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob, indent=2))


# ----------------------------------------------------------------------- background

_jobs: dict[str, dict] = {}
_job_lock = threading.Lock()


def _job_key(symbol: str, mode: str) -> str:
    return f"{symbol.upper()}:{mode}"


def job_state(symbol: str, mode: str) -> dict:
    with _job_lock:
        return dict(_jobs.get(_job_key(symbol, mode)) or {})


def _set_job(symbol: str, mode: str, **fields) -> None:
    with _job_lock:
        job = _jobs.setdefault(_job_key(symbol, mode), {})
        job.update(fields)
        job["updated"] = time.time()


def missing_chunks(event, symbol: str, mode: str, company: str,
                   budget: int | None = None) -> int:
    """How many NYT requests a warm would still need. Cheap: disk reads only.

    Mirrors the sampler's stop conditions exactly. The important part is breaking on a
    *cached empty page*: the sampler records one when a cell runs out of results, and a
    naive count that keeps asking for deeper pages would report pending work forever and
    re-trigger a warm that has nothing left to do.
    """
    if not news.NYT_API_KEY:
        return 0
    budget = news.NYT_PER_WARM_BUDGET if budget is None else budget
    begin, end = market.article_window(event, mode)
    term = news.short_company(company) or symbol
    cells = market.plan_cells(begin, end, budget)
    pages = max(1, min(news.NYT_MAX_PAGES_PER_CHUNK, budget // max(1, len(cells))))
    reusable = news._reusable_term_cache(term)
    n = 0
    for cell, _cb, _ce in cells:
        for page in range(pages):
            hit = reusable.get((cell, page))
            if hit is not None:
                if not hit:
                    break  # this cell is exhausted; deeper pages would return nothing
                continue
            n += 1
            if n >= budget:
                return n
    return n


def _triage(inv: dict, pool: list[dict], verdict: dict, window_days: int) -> dict:
    prompt = PROMPT.format(
        company=inv["company"], symbol=inv["symbol"],
        sector_etf=inv["sector_etf"] or "n/a", market=inv["market"],
        event_date=inv["event_date"],
        articles=_article_block(pool), window_days=window_days,
        sector_line=_sector_line(inv),
        verdict=verdict["verdict"], verdict_share=f"{verdict['share'] * 100:.0f}%",
        **{**inv["move"], **inv["divergence"]},
    )
    client = genai.Client(api_key=GEMINI_API_KEY)
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
    )
    return json.loads(resp.text)


def _run_warm(symbol: str, mode: str, inv: dict, log=print) -> None:
    """Blocking warm. Runs on a worker thread when triggered by a request."""
    from datetime import date as _date

    event = _date.fromisoformat(inv["event_date"])
    _set_job(symbol, mode, state="running", started=time.time())
    try:
        pool = collect(event, symbol, mode, inv["company"], log=log)
        if not pool:
            _set_job(symbol, mode, state="done", pool_size=0, note="no articles found")
            return
        _set_job(symbol, mode, pool_size=len(pool))
        if not GEMINI_API_KEY:
            _set_job(symbol, mode, state="done", pool_size=len(pool),
                     note="GEMINI_API_KEY is not set; articles left untriaged")
            return
        quota, reason = False, ""
        try:
            begin, end = market.article_window(event, mode)
            verdict = scope_verdict(inv["divergence"])
            triaged = _triage(inv, pool, verdict, (end - begin).days)
        except Exception as e:
            quota, reason = _triage_failure(e)
            log(f"  timeline: triage unavailable — {reason}")
            _set_job(symbol, mode, state="done", pool_size=len(pool), quota_exhausted=quota,
                     note=reason)
            return
        _write_json(_triage_path(symbol, event, mode), triaged)
        _set_job(symbol, mode, state="done", pool_size=len(pool),
                 triaged=len(triaged.get("events", [])))
    except Exception as e:
        log(f"  timeline: warm failed — {scrub(e)[:160]}")
        _set_job(symbol, mode, state="error", note=scrub(e)[:200])
    finally:
        _set_job(symbol, mode, finished=time.time())


def start_warm(symbol: str, mode: str, inv: dict, log=print) -> bool:
    """Kick off a warm if one is not already running. Returns True if one was started."""
    key = _job_key(symbol, mode)
    with _job_lock:
        if _jobs.get(key, {}).get("state") == "running":
            return False
        _jobs[key] = {"state": "running", "started": time.time()}
    threading.Thread(target=_run_warm, args=(symbol, mode, inv, log),
                     daemon=True, name=f"warm-{key}").start()
    return True


def warm_now(symbol: str, mode: str, inv: dict, log=print) -> dict:
    """Synchronous warm for the CLI, where blocking is the point.

    Settles the job registry on the way out so a UI polling `build()` sees a finished job
    rather than waiting on a background thread that this call made redundant.
    """
    from datetime import date as _date
    event = _date.fromisoformat(inv["event_date"])
    _set_job(symbol, mode, state="running", started=time.time())
    try:
        pool = collect(event, symbol, mode, inv["company"], log=log)
        if pool and GEMINI_API_KEY:
            begin, end = market.article_window(event, mode)
            try:
                triaged = _triage(inv, pool, scope_verdict(inv["divergence"]), (end - begin).days)
                _write_json(_triage_path(symbol, event, mode), triaged)
                _set_job(symbol, mode, state="done", pool_size=len(pool),
                         triaged=len(triaged.get("events", [])))
                log(f"  timeline: triaged {len(triaged.get('events', []))} event(s)")
            except Exception as e:
                quota, reason = _triage_failure(e)
                log(f"  timeline: triage unavailable — {reason}")
                _set_job(symbol, mode, state="done", pool_size=len(pool),
                         quota_exhausted=quota, note=reason)
        else:
            _set_job(symbol, mode, state="done", pool_size=len(pool))
        return {"pool_size": len(pool)}
    finally:
        _set_job(symbol, mode, finished=time.time())


def collect(event, symbol: str, mode: str, company: str = "", log=print) -> list[dict]:
    """Article pool for the window, with citation ids, aggregated from the chunk cache.

    Publishes each partial result as it arrives, so the timeline fills in progressively
    instead of staying blank for the whole warm.
    """
    def publish(found: list[dict]) -> None:
        pool = [{**a, "ref": f"A{i}"} for i, a in enumerate(found[:MAX_ARTICLES_IN_PROMPT], 1)]
        _write_json(_pool_path(symbol, event, mode), pool)

    articles = news.sample_articles(event, mode, symbol, company, log=log,
                                    on_progress=publish)
    publish(articles)
    return [{**a, "ref": f"A{i}"} for i, a in
            enumerate(articles[:MAX_ARTICLES_IN_PROMPT], start=1)]


# -------------------------------------------------------------------------- building

def _article_block(articles: list[dict]) -> str:
    if not articles:
        return "(none found in the window)"
    return "\n".join(
        f"{a['ref']} [{a['pub_date'][:10]}] {a['headline']} — {a['snippet'][:SNIPPET_CHARS]}"
        for a in articles)


def _sector_line(inv: dict) -> str:
    d = inv["divergence"]
    if not inv.get("sector_known"):
        return f"{inv['market']} {d['market_pct']:+.2f}% (no sector comparison available)"
    return (f"{inv['sector_etf']} {d['sector_pct']:+.2f}%, {inv['market']} {d['market_pct']:+.2f}%, "
            f"excess vs sector {d['excess_vs_sector']:+.2f} pts, vs market {d['excess_vs_market']:+.2f} pts")


_QUOTA_MARKERS = ("429", "RESOURCE_EXHAUSTED", "QUOTA", "EXCEEDED YOUR CURRENT",
                  "FREE TIER", "FREE-TIER", "RATE LIMIT", "RATE_LIMIT", "503",
                  "UNAVAILABLE", "OVERLOADED", "MODEL IS CURRENTLY")
_KEY_MARKERS = ("API_KEY_INVALID", "APIKEYINVALID", "PERMISSION_DENIED", "401", "403")


def _triage_failure(e: Exception) -> tuple[bool, str]:
    """Classify why Gemini could not triage. Returns (quota_or_availability, reason).

    The free tier does not fail consistently: a spent daily cap surfaces as 429
    RESOURCE_EXHAUSTED on one call and as 503 "model is currently experiencing high demand"
    on the next. Both mean the same thing during a demo, so both are caught here instead of
    matching on 429 alone.
    """
    text = scrub(e).upper()
    if any(m in text for m in _KEY_MARKERS) and not any(m in text for m in _QUOTA_MARKERS):
        return False, "Gemini rejected GEMINI_API_KEY. Check the key and that the model is enabled."
    if any(m in text for m in _QUOTA_MARKERS):
        return True, ("Gemini is unavailable right now. The free tier allows 20 requests per "
                      "day and this project has spent today's, or the model is under high "
                      "load. The articles below are real — only the triage is missing.")
    return False, f"Gemini call failed: {scrub(e)[:200]}"


def _unstaged(pool: list[dict], note: str) -> list[dict]:
    """Show the sampled articles even when triage could not run.

    The articles are real evidence, so hiding them because the model is unavailable would
    throw away the one part of this page that does not need a key.
    """
    return [{"ref": a["ref"], "scope": "stock", "significance": "low",
             "why": note, "thesis": "", "pub_date": a["pub_date"],
             "headline": a["headline"], "url": a["url"], "snippet": a["snippet"]}
            for a in pool]


def build(symbol: str, mode: str, inv: dict, refresh: bool = False, log=print) -> dict:
    """Timeline payload from cache only. Never blocks on the network.

    If work remains (missing chunks, or no triage yet) a background warm is started and the
    payload reports `warming: true` so the caller can poll.
    """
    from datetime import date as _date

    event = _date.fromisoformat(inv["event_date"])
    begin, end = market.article_window(event, mode)
    window_days = (end - begin).days
    verdict = scope_verdict(inv["divergence"])

    if refresh:
        _set_job(symbol, mode, state="idle")

    pool_blob = _read_json(_pool_path(symbol, event, mode))
    pool = pool_blob if isinstance(pool_blob, list) else []
    for i, a in enumerate(pool, start=1):
        a.setdefault("ref", f"A{i}")
    triaged = _read_json(_triage_path(symbol, event, mode))
    if refresh:
        triaged = None

    todo = missing_chunks(event, symbol, mode, inv["company"])
    job = job_state(symbol, mode)

    def _should_warm() -> bool:
        """Only spend another request when there is genuinely something left to do.

        Without the cooldown, a spent Gemini quota meant every poll kicked off another
        doomed triage: the job never settled, `warming` stayed true forever, and each page
        load burned another of the 20 daily calls.
        """
        if refresh:
            return True
        if todo > 0:
            return True  # sampling work remains
        if not (pool and triaged is None and GEMINI_API_KEY):
            return False  # nothing cached-and-untriaged to do
        failed = job.get("state") == "done" and (job.get("quota_exhausted") or job.get("note"))
        if failed and time.time() - job.get("finished", 0) < TRIAGE_RETRY_COOLDOWN:
            return False
        return True

    warming = job.get("state") == "running" or (todo > 0 and not pool)
    if _should_warm():
        warming = start_warm(symbol, mode, inv, log=log) or warming
    elif job.get("state") == "running":
        warming = True

    payload = {
        "symbol": symbol,
        "company": inv["company"],
        "market": inv["market"],
        "move_pct": inv["move"]["move_pct"],
        "mode": mode,
        "event_date": inv["event_date"],
        "event_label": inv["event_label"],
        "event_short": inv["event_short"],
        "window": {"begin": begin.isoformat(), "end": end.isoformat(), "days": window_days,
                   "label": _window_label(window_days)},
        "verdict": verdict,
        "against_market": verdict["against_market"],
        "pool_size": len(pool),
        "pending_requests": todo,
        "warming": bool(warming),
        "job": job,
        "nyt_budget": {"used": news.budget_state()["used"], "cap": news.NYT_SAFETY_CAP},
        "freshness": inv["freshness"],
        "events": [],
        "narrative": "",
        "caveat": "",
    }

    if not pool:
        if not news.NYT_API_KEY:
            payload["caveat"] = "Set NYT_API_KEY to load coverage."
        elif news.budget_remaining() <= 0:
            payload["caveat"] = (f"NYT's daily request cap is spent "
                                 f"({news.budget_state()['used']}/{news.NYT_DAILY_CAP}). "
                                 "It resets at midnight ET.")
        else:
            payload["caveat"] = ("No articles cached yet."
                                 + (" Sampling in the background." if warming else ""))
        return payload

    if triaged is None:
        quota = bool(job.get("quota_exhausted"))
        payload["quota_exhausted"] = quota
        payload["triage_note"] = job.get("note") or (
            "Not triaged yet." if warming else "Not triaged — Gemini was unavailable.")
        payload["events"] = _unstaged(pool, "Not triaged yet." if warming
                                      else "Not triaged — Gemini was unavailable.")
        return payload

    by_ref = {a["ref"]: a for a in pool}
    events = []
    for e in triaged.get("events", []):
        art = by_ref.get(str(e.get("ref", "")).strip())
        if not art:
            continue  # only citations that resolve to a real article are shown
        events.append({
            "ref": art["ref"],
            "scope": e.get("scope") if e.get("scope") in SCOPES else "stock",
            "significance": e.get("significance") if e.get("significance") in
                            ("high", "medium", "low") else "medium",
            "why": e.get("why", ""), "thesis": e.get("thesis", ""),
            "pub_date": art["pub_date"], "headline": art["headline"],
            "url": art["url"], "snippet": art["snippet"],
        })
    events.sort(key=lambda e: e["pub_date"])

    payload["events"] = events
    payload["narrative"] = triaged.get("narrative", "")
    payload["caveat"] = triaged.get("caveat", "")
    payload["verdict_note"] = triaged.get("verdict_note", "")
    if triaged.get("verdict") and triaged["verdict"] != verdict["verdict"]:
        # The model disagreed with the arithmetic. Keep the arithmetic as the headline
        # verdict and surface the disagreement rather than silently swapping it.
        payload["verdict_note"] = (f"Gemini read the evidence as {triaged['verdict']}, but the "
                                   f"beta-adjusted decomposition ({verdict['share'] * 100:.0f}% "
                                   f"idiosyncratic) is shown above. " + payload["verdict_note"])
    return payload


def _window_label(days: int) -> str:
    if days >= 365 * 4:
        return f"{round(days / 365)} years"
    if days >= 60:
        return f"{round(days / 30)} months"
    return f"{days} days"
