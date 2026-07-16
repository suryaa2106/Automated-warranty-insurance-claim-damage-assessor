"""
vision_agent.py
----------------
Calls the Gemini API (multimodal) with the incoming claim photo and forces a
strict JSON response describing the vehicle and every damaged part detected.

Design notes:
- We use `response_mime_type="application/json"` + a `response_schema` so the
  SDK/model is constrained to return valid JSON only (no markdown fences, no
  conversational preamble). We still defensively strip fences in case the
  model or SDK version ignores the constraint.
- If the GEMINI_API_KEY env var is missing or the call fails for any reason,
  we fall back to a deterministic mock response so the rest of the pipeline
  (and the demo) keeps working out-of-the-box.
"""

import os
import json
import logging
from typing import Any, Dict

logger = logging.getLogger("vision_agent")

MODEL_NAME = "gemini-2.0-flash"

VISION_PROMPT = """You are an expert vehicle damage inspector for an insurance company.
Analyze the attached photo of a vehicle and identify EVERY visible damaged part.

Return ONLY a JSON object with this exact shape (no markdown, no commentary):
{
  "vehicle_type": string,               // e.g. "Sedan", "SUV", "Hatchback"
  "damaged_parts": [
    {
      "part_name": string,              // e.g. "Front Bumper", "Windshield"
      "damage_type": string,            // e.g. "Dent", "Scratch", "Shatter", "Total Loss"
      "severity_score": integer         // 1 (cosmetic) to 5 (severe/structural)
    }
  ]
}

If no damage is visible, return an empty "damaged_parts" array. Do not invent
damage that is not clearly visible in the image."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "vehicle_type": {"type": "string"},
        "damaged_parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "part_name": {"type": "string"},
                    "damage_type": {"type": "string"},
                    "severity_score": {"type": "integer"},
                },
                "required": ["part_name", "damage_type", "severity_score"],
            },
        },
    },
    "required": ["vehicle_type", "damaged_parts"],
}


def _mock_response() -> Dict[str, Any]:
    """Deterministic fallback so the demo never breaks without an API key."""
    return {
        "vehicle_type": "Sedan",
        "damaged_parts": [
            {"part_name": "Front Bumper", "damage_type": "Dent", "severity_score": 3},
            {"part_name": "Windshield", "damage_type": "Scratch", "severity_score": 1},
        ],
        "_mock": True,
    }


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


async def analyze_damage(image_bytes: bytes, mime_type: str = "image/jpeg") -> Dict[str, Any]:
    """
    Sends the image + prompt to Gemini and returns the parsed damage JSON.
    Falls back to a mock structure on any failure so the pipeline never
    hard-crashes during a live demo.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — using mock vision response.")
        return _mock_response()

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                VISION_PROMPT,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
                temperature=0.1,
            ),
        )

        raw_text = response.text
        cleaned = _strip_code_fences(raw_text)
        parsed = json.loads(cleaned)

        # Basic shape validation — fall back to mock if malformed.
        if "vehicle_type" not in parsed or "damaged_parts" not in parsed:
            raise ValueError("Malformed vision response shape")

        return parsed

    except Exception as exc:  # noqa: BLE001 - broad on purpose for demo resilience
        logger.error("vision_agent failed, falling back to mock: %s", exc)
        fallback = _mock_response()
        fallback["_error"] = str(exc)
        return fallback
