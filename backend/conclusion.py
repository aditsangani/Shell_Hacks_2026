"""Rules-based synthesis of an investigation and its time-filtered evidence."""

from statistics import median


def scope_verdict(div: dict) -> dict:
    """Classify the beta-adjusted share of a move without model inference."""
    total = abs(div.get("ticker_pct") or 0.0)
    idio = abs(div.get("idiosyncratic_pct") or 0.0)
    if total < 1e-9:
        return {"verdict": "flat", "share": 0.0, "label": "No material move",
                "raw_share": 0.0, "against_market": False}
    raw = idio / total
    share = min(1.0, raw)
    if share >= 0.6:
        verdict, label = "stock_specific", "Stock-specific"
    elif share <= 0.35:
        verdict, label = "market_wide", "Market-wide"
    else:
        verdict, label = "mixed", "Mixed"
    return {"verdict": verdict, "share": round(share, 3), "label": label,
            "raw_share": round(raw, 3), "against_market": raw > 1.0}


def _move_reading(inv: dict) -> tuple[str, str]:
    move = inv["move"]
    percentile = float(move["percentile"])
    if percentile >= 99:
        strength = "extreme"
    elif percentile >= 95:
        strength = "highly unusual"
    elif percentile >= 80:
        strength = "unusual"
    else:
        strength = "within its broader historical range"
    direction = "gain" if move["move_pct"] >= 0 else "decline"
    sentence = (
        f"{inv['symbol']}'s {move['move_pct']:+.2f}% {direction} was larger in absolute terms "
        f"than {percentile:.1f}% of its prior daily moves across "
        f"{move['history_days']:,} trading sessions. The rules-based classification is {strength}."
    )
    return strength, sentence


def _market_reading(inv: dict, verdict: dict) -> str:
    div = inv["divergence"]
    share = float(verdict.get("share") or 0) * 100
    label = verdict.get("label") or "Mixed"
    if verdict.get("verdict") == "flat":
        return "The selected session did not contain a material move to decompose."
    opposite = " The market model pointed in the opposite direction." if verdict.get("against_market") else ""
    return (
        f"A one-year beta model implied {div['beta_expected_pct']:+.2f}% from the broad market, "
        f"leaving {div['idiosyncratic_pct']:+.2f} percentage points outside that simple model. "
        f"That residual is {share:.0f}% of the move in absolute terms, producing a {label.lower()} "
        f"classification.{opposite}"
    )


def _evidence_reading(evidence: dict | None) -> tuple[str, str]:
    if evidence is None:
        return "pending", "The published-evidence review is still pending."

    if evidence.get("triage_note"):
        return (
            "untriaged",
            "Candidate articles or filings were found, but relevance triage did not finish. "
            "No claim about a published catalyst is made.",
        )

    events = evidence.get("events") or []
    catalysts = [event for event in events if event.get("can_explain_move")]
    if catalysts:
        count = len(catalysts)
        sources = sorted({event.get("publisher") or event.get("source") for event in catalysts})
        source_text = f" across {len(sources)} source{'s' if len(sources) != 1 else ''}" if sources else ""
        return (
            "possible_catalyst",
            f"{count} selected evidence item{'s were' if count != 1 else ' was'} published inside "
            f"the possible catalyst window{source_text}. The timing makes a relationship possible, "
            "but it does not establish that the evidence caused the move.",
        )

    if evidence.get("warming"):
        return "pending", "The evidence scan is still running, so catalyst status remains pending."
    if int(evidence.get("pool_size") or 0) == 0:
        return (
            "no_evidence",
            "The checked NYT, Yahoo Finance, and SEC sources did not return relevant published "
            "evidence for this investigation window.",
        )
    return (
        "no_published_catalyst",
        "No selected evidence item was published inside the possible catalyst window. "
        "Any retained later coverage is reaction or context rather than an explanation for this session.",
    )


def _history_reading(inv: dict) -> str:
    similar = inv.get("similar") or []
    for key, label in (("d20", "20"), ("d5", "5"), ("d1", "one")):
        values = [float(item[key]) for item in similar if item.get(key) is not None]
        if values:
            positive = sum(value > 0 for value in values)
            session_word = "session" if label == "one" else "trading days"
            return (
                f"Among {len(values)} closest prior same-direction moves, {positive} finished positive "
                f"after {label} {session_word}; the median return was {median(values):+.2f}%. "
                "This is a small historical comparison, not a forecast."
            )
    return "Comparable prior moves do not yet have enough forward data for an outcome summary."


def _best_answer(inv: dict, evidence: dict | None, verdict: dict) -> str:
    """Give one direct answer while staying inside what the evidence can support."""
    symbol = inv["symbol"]
    move_pct = float(inv["move"]["move_pct"])
    direction = "rose" if move_pct >= 0 else "fell"
    pressure = "buying" if move_pct >= 0 else "selling"
    events = (evidence or {}).get("events") or []
    catalysts = [event for event in events if event.get("can_explain_move")]
    if catalysts:
        rank = {"high": 0, "medium": 1, "low": 2}
        lead = min(catalysts, key=lambda event: rank.get(event.get("significance"), 3))
        headline = (lead.get("headline") or "the leading event published during the catalyst window")
        return (f"{symbol} {direction} primarily because investors reacted to “{headline},” "
                "the highest-ranked evidence published inside the catalyst window.")

    label = verdict.get("verdict")
    if label == "market_wide":
        return (f"{symbol} {direction} mainly because the broader market moved the stock through "
                f"its normal beta exposure; the market model explains most of the {move_pct:+.2f}% move.")
    if label == "mixed":
        return (f"{symbol} {direction} because broad-market movement and stock-specific {pressure} "
                "both contributed, with neither factor dominating the beta-adjusted decomposition.")
    if label == "flat":
        return (f"{symbol} was effectively flat because buying and selling pressure balanced out; "
                "the session did not contain a material directional move.")
    return (f"{symbol} {direction} because stock-specific {pressure} pressure dominated the session. "
            "No timely published catalyst was identified, so the best-supported explanation is "
            "company-specific positioning or order flow rather than the broader market.")


def build(inv: dict, evidence: dict | None = None) -> dict:
    """Return a deterministic synthesis; no model or network call is made here."""
    verdict = evidence.get("verdict") if evidence else None
    verdict = verdict or scope_verdict(inv["divergence"])
    strength, move = _move_reading(inv)
    evidence_status, evidence_text = _evidence_reading(evidence)
    label = verdict.get("label", "Mixed").lower()
    return {
        "title": f"{strength.capitalize()} move with a {label} classification",
        "answer": _best_answer(inv, evidence, verdict),
        "move": move,
        "market_context": _market_reading(inv, verdict),
        "evidence": evidence_text,
        "evidence_status": evidence_status,
        "history": _history_reading(inv),
        "method": "computed",
        "caveat": (
            "This conclusion is assembled from displayed calculations and time-filtered evidence. "
            "It does not establish causation, recommend an investment, or predict future performance."
        ),
    }
