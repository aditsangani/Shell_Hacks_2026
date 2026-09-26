"""ElevenLabs text-to-speech briefing.

Bay Hacks 2026 used the ElevenLabs Conversational AI widget (voice *input*), which is
out of scope here; a briefing only needs one TTS call.
"""

import requests

from config import ELEVENLABS_API_KEY, ELEVENLABS_MODEL, ELEVENLABS_VOICE_ID

TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def briefing_script(inv: dict, explanations: dict | None) -> str:
    m, d = inv["move"], inv["divergence"]
    direction = "rose" if m["move_pct"] > 0 else "fell"
    lines = [
        f"Here's your briefing on {inv['company']}.",
        f"On {inv['event_label']}, {inv['symbol']} {direction} {abs(m['move_pct']):.1f} percent.",
        f"That's bigger than {m['percentile']:.0f} percent of its daily moves over the past five years.",
        f"The {inv['sector_name']} sector moved {d['sector_pct']:+.1f} percent and the S&P 500 "
        f"{d['market_pct']:+.1f} percent, so most of this move was specific to {inv['symbol']}.",
    ]
    exps = (explanations or {}).get("explanations") or []
    if exps:
        lines.append(f"The most likely explanation: {exps[0]['title']}. {exps[0]['summary']}")
    lines.append("This is a look at what happened, not investment advice.")
    return " ".join(lines)


def synthesize(text: str) -> bytes:
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    resp = requests.post(
        TTS_URL.format(voice_id=ELEVENLABS_VOICE_ID),
        headers={"xi-api-key": ELEVENLABS_API_KEY, "accept": "audio/mpeg"},
        json={"text": text, "model_id": ELEVENLABS_MODEL},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content
