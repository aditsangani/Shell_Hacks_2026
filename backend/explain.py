"""Gemini: candidate explanations that must cite the headlines/data they rest on."""

import json

from google import genai
from google.genai import errors, types

from config import GEMINI_API_KEY, GEMINI_FALLBACK_MODEL, GEMINI_MODEL
from language_guard import cap_confidence, guard_report, guard_statement, guard_title

PROMPT = """You are an equity research assistant helping a retail investor understand
why a stock moved. You do NOT give investment advice or predictions.

Stock: {company} ({symbol}), market proxy {market}.
Event day: {event_date}.
{sector_line}
DATA
- Move: {symbol} {move_pct:+.2f}% close-to-close. Bigger than {percentile}% of its daily
  moves over the prior {history_days} trading days (z-score {z_score}). Typical absolute
  daily move: {typical_abs_move}%. Largest same-direction move since: {largest_since}.
- Same day: {market} {market_pct:+.2f}%. Excess vs market {excess_vs_market:+.2f} pts.
  1y beta to {market}: {beta_1y}, so the market alone implies {beta_expected_pct:+.2f}%;
  unexplained (idiosyncratic) part: {idiosyncratic_pct:+.2f}%.{beta_note}
- The move above is a single completed trading session. If headlines describe events that
  happened after that session, do not present them as the cause.

HEADLINES (NYT, UTC timestamps; ids are for citation)
{headlines}

TASK
Give 2-3 candidate explanations for the move, most plausible first. Each must cite at
least one piece of evidence. Cite headlines by id (e.g. "H3"); cite data points with one of:
"percentile", "divergence", "beta", "sector". Only cite headlines published before or during
the move window if you claim they caused it. If the headlines don't support a clear
explanation, say so and lower confidence rather than inventing a catalyst.

Language rules:
- Treat every explanation as a hypothesis, not a finding of cause. Use calibrated terms such
  as "may", "could", "possible", or "consistent with".
- Never use absolute language such as definitely, certainly, clearly, proved, guaranteed, or
  "the cause". Never predict what the stock will do next.
- `confidence` may be "medium" or "low" for a causal explanation; never return "high".

Return JSON only:
{{"explanations": [{{"title": str, "summary": str (2-3 sentences),
   "confidence": "medium"|"low",
   "evidence": [{{"ref": str, "why": str}}]}}],
  "caveat": str}}
"""

DATA_REFS = {"percentile", "divergence", "beta", "sector"}


def _refs_for(inv: dict) -> set[str]:
    """"sector" is only citable when we actually have a sector comparison."""
    return DATA_REFS - {"sector"} if not inv.get("sector_known") else DATA_REFS


def _headline_block(headlines: list[dict]) -> str:
    if not headlines:
        return "(none found in the window)"
    return "\n".join(
        f"{h['id']} [{h['pub_date']}] "
        f"[{'POSSIBLE CATALYST WINDOW' if h.get('is_potential_catalyst') else 'CONTEXT ONLY — CANNOT SUPPORT CAUSATION'}] "
        f"{h['headline']} — {h['snippet'][:240]}"
        for h in headlines)


def _sector_lines(inv: dict, div: dict) -> tuple[str, str]:
    """(context line for the prompt, extra beta note). Empty strings when sector is unknown."""
    if not inv.get("sector_known"):
        return ("- No sector ETF comparison: this ticker's sector is not in our map, so it is "
                "compared against the market proxy only.\n", "")
    return (f"- Sector: {inv['sector_name']} ({inv['sector_etf']}) moved {div['sector_pct']:+.2f}%, "
            f"so excess vs sector is {div['excess_vs_sector']:+.2f} pts.\n",
            f" Note {inv['symbol']} is a large weight in {inv['sector_etf']}, so part of the "
            f"sector's move may be {inv['symbol']} itself.")


def _computed_fallback(inv: dict, caveat: str | None = None) -> dict:
    """Evidence-only explanation when every Gemini model is temporarily unavailable."""
    symbol, market = inv["symbol"], inv["market"]
    move, div = inv["move"], inv["divergence"]
    direction = "fell" if move["move_pct"] < 0 else "rose"
    explanations = [{
        "title": "The broad market does not explain most of the move",
        "summary": (
            f"{symbol} {direction} {abs(move['move_pct']):.2f}% while {market} moved "
            f"{div['market_pct']:+.2f}%. Its one-year beta implied {div['beta_expected_pct']:+.2f}%, "
            f"leaving {div['idiosyncratic_pct']:+.2f} percentage points unexplained by this simple "
            "market model. That narrows the investigation, but does not by itself identify a cause."
        ),
        "confidence": "high",
        "evidence": [
            {"ref": "divergence", "why": "The stock and broad market moved differently."},
            {"ref": "beta", "why": "The beta-adjusted residual measures what the simple market model did not explain."},
        ],
    }]
    headlines = inv.get("headlines") or []
    if headlines:
        explanations.append({
            "title": "Available coverage is context, not a confirmed catalyst",
            "summary": (
                f"The relevant NYT coverage near the session discusses {symbol}, but publication timing "
                "and topical relevance alone do not establish that it caused the price move."
            ),
            "confidence": "low",
            "evidence": [{
                "ref": headlines[0]["id"],
                "why": "This is the closest directly relevant coverage in the selected news window.",
            }],
        })
    return {
        "explanations": explanations,
        "caveat": caveat or (
            "Gemini was temporarily unavailable. These fallback observations are generated "
            "directly from the displayed calculations and filtered headlines."),
        "generated_by": "computed",
    }


def _guard_gemini_result(result: dict) -> dict:
    """Replace overconfident model prose before it can reach the UI or voice briefing."""
    adjustments: list[str] = []
    safe_explanations = []
    for explanation in result.get("explanations", []):
        title, flags = guard_title(explanation.get("title"))
        adjustments.extend(flags)
        summary, flags = guard_statement(
            explanation.get("summary"),
            "The cited evidence is relevant to this move, but it does not establish a cause. "
            "Treat this as a possible explanation rather than a confirmed account.",
            require_uncertainty=True,
        )
        adjustments.extend(flags)
        confidence, flags = cap_confidence(explanation.get("confidence"))
        adjustments.extend(flags)

        safe_evidence = []
        for evidence in explanation.get("evidence", []):
            why, flags = guard_statement(
                evidence.get("why"),
                "This evidence is relevant context, but it does not establish causation.",
            )
            adjustments.extend(flags)
            safe_evidence.append({**evidence, "why": why})
        safe_explanations.append({
            **explanation,
            "title": title,
            "summary": summary,
            "confidence": confidence,
            "evidence": safe_evidence,
        })

    caveat, flags = guard_statement(
        result.get("caveat"),
        "These are evidence-limited possibilities, not confirmed causes or predictions.",
    )
    adjustments.extend(flags)
    result["explanations"] = safe_explanations
    if adjustments:
        notice = "Overconfident generated wording was automatically qualified or replaced."
        caveat = f"{caveat} {notice}".strip()
    result["caveat"] = caveat
    result["language_guard"] = guard_report(adjustments)
    return result


def explain(inv: dict) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    sector_line, beta_note = _sector_lines(inv, inv["divergence"])
    move = dict(inv["move"])
    move["largest_since"] = move["largest_since"] or "not repeated in this history"
    prompt = PROMPT.format(
        symbol=inv["symbol"], company=inv["company"], market=inv["market"],
        event_date=inv["event_date"], sector_line=sector_line, beta_note=beta_note,
        headlines=_headline_block(inv.get("headlines") or []),
        **{**move, **inv["divergence"]},
    )

    client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(
            timeout=20_000,
            retry_options=types.HttpRetryOptions(
                attempts=2, initial_delay=0.5, max_delay=1.0, exp_base=2.0,
                jitter=0.2, http_status_codes=[429, 500, 502, 503, 504],
            ),
        ),
    )
    generation_config = types.GenerateContentConfig(
        response_mime_type="application/json", temperature=0.3)
    models = [GEMINI_MODEL]
    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL:
        models.append(GEMINI_FALLBACK_MODEL)
    result = None
    for index, model in enumerate(models):
        try:
            resp = client.models.generate_content(
                model=model, contents=prompt, config=generation_config)
            result = json.loads(resp.text)
            result["generated_by"] = "gemini"
            result["model"] = model
            result = _guard_gemini_result(result)
            break
        except errors.ClientError as exc:
            # RESOURCE_EXHAUSTED can be scoped to one model's rate/token quota. Try the
            # alternate model, then use the computed fallback if that quota is exhausted too.
            if exc.code != 429 and index == 0:
                raise
            continue
        except errors.ServerError:
            # If bounded retries are exhausted, move to the fallback model immediately.
            continue
    if result is None:
        result = _computed_fallback(inv)

    # Keep only citations that resolve; attach the real headline so the UI shows evidence, not claims.
    by_id = {h["id"]: h for h in inv.get("headlines") or []}
    allowed = _refs_for(inv)
    resolved_explanations = []
    for exp in result.get("explanations", []):
        resolved = []
        invalid_evidence = False
        for ev in exp.get("evidence", []):
            ref = str(ev.get("ref", "")).strip()
            if ref in by_id and by_id[ref].get("is_potential_catalyst"):
                resolved.append({"kind": "headline", "ref": ref, "why": ev.get("why", ""),
                                 "headline": by_id[ref]})
            elif ref in allowed:
                resolved.append({"kind": "data", "ref": ref, "why": ev.get("why", "")})
            else:
                # Reject the whole explanation if any cited source is nonexistent or outside
                # the catalyst window. Keeping its other citations could leave the unsupported
                # claim intact while merely hiding the evidence that made it invalid.
                invalid_evidence = True
        exp["evidence"] = resolved
        if resolved and not invalid_evidence:
            resolved_explanations.append(exp)
    result["explanations"] = resolved_explanations
    if result.get("generated_by") == "gemini" and not resolved_explanations:
        guarded = result.get("language_guard") or {"adjusted": 0, "reasons": []}
        fallback = _computed_fallback(
            inv,
            "Gemini's candidate explanations were withheld because none had eligible, "
            "resolvable evidence. The observations shown are calculated directly from the data.",
        )
        fallback["language_guard"] = {
            "adjusted": guarded.get("adjusted", 0) + 1,
            "reasons": sorted(set(guarded.get("reasons", []) + ["unsupported_explanation"])),
        }
        return fallback
    return result
