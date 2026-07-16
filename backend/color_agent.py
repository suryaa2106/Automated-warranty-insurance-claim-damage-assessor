"""
color_agent.py
----------------
Uses Groq Vision (llama-4-scout-17b-16e-instruct) to:
  1. Detect the dominant color of the car in a damage photo.
  2. Semantically compare it against the vehicle's registered color.

Returns:
  {
    "match": bool,
    "detected_color": str,
    "registered_color": str,
    "confidence": "high" | "medium" | "low",
    "reason": str
  }

Decision logic:
  - match=False + confidence="high"   → orchestrator triggers AUTO-REJECT
  - match=False + confidence="medium" → orchestrator flags for MANUAL REVIEW
  - match=True  (any confidence)      → no color flag
"""

import os
import json
import base64
import logging
import httpx
from typing import Any, Dict

logger = logging.getLogger("color_agent")

MODEL_NAME = "meta-llama/llama-4-scout-17b-16e-instruct"

# Semantic color groups — colors in the same group are treated as equivalent
COLOR_GROUPS = [
    {"white", "pearl white", "off-white", "cream", "ivory"},
    {"black", "jet black", "matte black", "midnight black", "glossy black"},
    {"silver", "grey", "gray", "metallic grey", "metallic gray", "charcoal", "graphite", "dark grey", "dark gray"},
    {"red", "crimson", "maroon", "dark red", "cherry red", "wine red"},
    {"blue", "navy", "dark blue", "sky blue", "cobalt", "royal blue", "steel blue", "midnight blue"},
    {"green", "dark green", "olive", "forest green", "lime"},
    {"yellow", "gold", "golden", "mustard", "yellow-gold"},
    {"orange", "copper", "amber"},
    {"brown", "bronze", "tan", "beige", "champagne"},
    {"purple", "violet", "magenta"},
]

COLOR_PROMPT = """\
You are a vehicle color identification expert working for an insurance company.

Carefully look at the vehicle in the image and identify the PRIMARY/DOMINANT color of the car body.

Return ONLY a JSON object like this:
{
  "detected_color": "the exact dominant body color of the car (e.g. White, Black, Silver, Red, Blue)",
  "confidence": "high | medium | low",
  "notes": "brief note about any uncertainty, lighting issues, dirt, or partial visibility"
}

Rules:
- Focus ONLY on the car body paint color — ignore dirt, shadows, rust stains
- If the car is barely visible or confidence is very low, set confidence to "low"
- Use plain simple color names (White, Black, Silver, Grey, Red, Blue, Green, Yellow, Orange, Brown)
"""


def _colors_match(detected: str, registered: str) -> bool:
    """Semantic color match — checks if both colors fall in the same color group."""
    detected_lower  = detected.strip().lower()
    registered_lower = registered.strip().lower()

    # Exact match
    if detected_lower == registered_lower:
        return True

    # Group-based semantic match
    for group in COLOR_GROUPS:
        if detected_lower in group and registered_lower in group:
            return True

    return False


async def verify_color(
    image_bytes: bytes,
    registered_color: str,
    mime_type: str = "image/jpeg",
) -> Dict[str, Any]:
    """
    Detects the car color from the image and compares with the registered color.
    Falls back to a safe "inconclusive" result on any API error.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY not set — skipping color verification.")
        return _inconclusive(registered_color, "API key not configured")

    try:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": COLOR_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}
                        }
                    ]
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            result   = response.json()
            raw_text = result["choices"][0]["message"]["content"]

        parsed = json.loads(raw_text)
        detected_color = parsed.get("detected_color", "Unknown")
        confidence     = parsed.get("confidence", "low")
        notes          = parsed.get("notes", "")

        match = _colors_match(detected_color, registered_color)

        logger.info(
            "Color check — detected: %s | registered: %s | match: %s | confidence: %s",
            detected_color, registered_color, match, confidence
        )

        return {
            "match":            match,
            "detected_color":   detected_color,
            "registered_color": registered_color,
            "confidence":       confidence,
            "notes":            notes,
        }

    except Exception as exc:
        logger.error("color_agent failed, returning inconclusive: %s", exc)
        return _inconclusive(registered_color, str(exc))


def _inconclusive(registered_color: str, reason: str) -> Dict[str, Any]:
    """Returns a safe 'inconclusive' result so the pipeline never hard-crashes."""
    return {
        "match":            True,   # give benefit of the doubt on failure
        "detected_color":   "Unknown",
        "registered_color": registered_color,
        "confidence":       "low",
        "notes":            f"Color verification inconclusive: {reason}",
    }
