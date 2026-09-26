"""Gemini: candidate explanations that must cite the headlines/data they rest on."""

import json

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL

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

Return JSON only:
{{"explanations": [{{"title": str, "summary": str (2-3 sentences),
   "confidence": "high"|"medium"|"low",
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
    return "\n".join(f"{h['id']} [{h['pub_date']}] {h['headline']} — {h['snippet'][:240]}"
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

    client = genai.Client(api_key=GEMINI_API_KEY)
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3),
    )
    result = json.loads(resp.text)

    # Keep only citations that resolve; attach the real headline so the UI shows evidence, not claims.
    by_id = {h["id"]: h for h in inv.get("headlines") or []}
    allowed = _refs_for(inv)
    for exp in result.get("explanations", []):
        resolved = []
        for ev in exp.get("evidence", []):
            ref = str(ev.get("ref", "")).strip()
            if ref in by_id:
                resolved.append({"kind": "headline", "ref": ref, "why": ev.get("why", ""),
                                 "headline": by_id[ref]})
            elif ref in allowed:
                resolved.append({"kind": "data", "ref": ref, "why": ev.get("why", "")})
        exp["evidence"] = resolved
    return result
