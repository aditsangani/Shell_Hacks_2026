"""Deterministic confidence limits for model-generated financial explanations.

Prompts ask the model to calibrate its language, but displayed claims must not depend on
prompt compliance. This module rejects absolute, predictive, and unqualified causal wording
and makes every inferential statement explicitly uncertain.
"""

import re


_ABSOLUTE = (
    re.compile(r"\b(definitely|certainly|undoubtedly|unquestionably|conclusively|obviously)\b", re.I),
    re.compile(r"(?<!not )\bclearly\b", re.I),
    re.compile(r"\b(proves?|proved|demonstrates?|establishes?|guarantees?|guaranteed|inevitably|must have)\b", re.I),
    re.compile(r"\bconfirms? that\b", re.I),
    re.compile(r"\b(most likely|decisively|compelling evidence)\b", re.I),
    re.compile(r"\b(?:strongly|overwhelmingly) (?:suggests?|indicates?)\b", re.I),
    re.compile(r"\b(without (?:a |any )?doubt|no reasonable doubt)\b", re.I),
    re.compile(r"\b(the|this) (?:sole|primary|definitive|actual|real) (?:cause|reason)\b", re.I),
    re.compile(r"\b(?:primary|key|main|decisive) catalyst\b", re.I),
)

_CAUSAL = (
    re.compile(r"\b(caused?|drove|driven|triggered|sparked|prompted)\b", re.I),
    re.compile(r"\b(led to|resulted in|was responsible for|stems? from|came from)\b", re.I),
    re.compile(r"\b(due to|because of|on account of|attributable to)\b", re.I),
    re.compile(r"\b(explains? (?:the move|why)|accounts? for (?:the move|the rally|the decline))\b", re.I),
    re.compile(r"\b(sent|pushed) (?:the )?(?:shares?|stock|price) (?:higher|lower|up|down)\b", re.I),
    re.compile(r"\b(?:investors?|the market) (?:reacted|responded) to\b", re.I),
    re.compile(r"\b(?:the |this )?(?:news|announcement|event) made (?:shares?|the stock|the price)\b", re.I),
    re.compile(r"\b(?:shares?|the stock|the price) (?:rose|fell|rallied|dropped) on (?:the|this) news\b", re.I),
    re.compile(r"\b(?:the |this )?move (?:reflects|is explained by|was driven by|was sparked by)\b", re.I),
    re.compile(r"\b(?:was behind the move|is why (?:shares?|the stock|the price))\b", re.I),
)

_PREDICTIVE = (
    re.compile(r"\bwill (?:rise|fall|increase|decrease|rally|drop|surge|plunge|outperform|underperform)\b", re.I),
    re.compile(r"\b(?:is|are) (?:certain|sure|guaranteed|bound) to\b", re.I),
)

_UNCERTAINTY = re.compile(
    r"\b(may|might|could|possible|possibly|potential|potentially|plausible|likely|"
    r"suggests?|appears?|seems?|consistent with|candidate|uncertain|cannot establish)\b",
    re.I,
)


def guard_statement(text: object, fallback: str, *, require_uncertainty: bool = False) -> tuple[str, list[str]]:
    """Return safe display text and a list of adjustments applied."""
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return fallback, ["missing_statement"]

    reasons: list[str] = []
    if any(pattern.search(cleaned) for pattern in _ABSOLUTE):
        reasons.append("absolute_certainty")
    hedged = bool(_UNCERTAINTY.search(cleaned))
    if any(pattern.search(cleaned) for pattern in _CAUSAL) and not hedged:
        reasons.append("unqualified_causality")
    if any(pattern.search(cleaned) for pattern in _PREDICTIVE):
        reasons.append("unsupported_prediction")
    if reasons:
        return fallback, reasons

    if require_uncertainty and not hedged:
        return f"One possible reading of the cited evidence is: {cleaned}", ["uncertainty_added"]
    return cleaned, []


def guard_title(text: object, fallback: str = "Possible factor in the move") -> tuple[str, list[str]]:
    """Make short model-generated headings visibly provisional."""
    safe, reasons = guard_statement(text, fallback)
    if reasons:
        return safe, reasons
    if not _UNCERTAINTY.search(safe):
        return f"Possible factor: {safe}", ["uncertainty_added"]
    return safe, []


def cap_confidence(value: object) -> tuple[str, list[str]]:
    """Gemini cannot label a causal market explanation as high confidence."""
    confidence = str(value or "low").strip().lower()
    if confidence == "high":
        return "medium", ["confidence_capped"]
    if confidence not in {"medium", "low"}:
        return "low", ["invalid_confidence"]
    return confidence, []


def guard_report(adjustments: list[str]) -> dict:
    return {"adjusted": len(adjustments), "reasons": sorted(set(adjustments))}
