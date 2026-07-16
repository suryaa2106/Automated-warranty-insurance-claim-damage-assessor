"""
classifier_agent.py
---------------------
Uses Groq (llama-3.3-70b-versatile) to classify a vehicle into a price tier
(Low, Mid, or High) based on its make, model, and year.

Tier Definitions:
  Low  — Economy/Budget cars (e.g. Toyota Corolla, Honda Civic, Hyundai i10)
  Mid  — Mid-range/SUV/Family cars (e.g. Toyota Camry, Honda CR-V, BMW 3-Series)
  High — Luxury/Sports/Premium EVs (e.g. BMW 7-Series, Mercedes S-Class, Porsche, Tesla Model S)

Falls back to rule-based tier estimation if the API call fails.
"""

import os
import json
import logging
import httpx
from typing import Any, Dict

logger = logging.getLogger("classifier_agent")

MODEL_NAME = "llama-3.3-70b-versatile"

CLASSIFIER_PROMPT = """\
You are a vehicle price classification expert for an insurance company.
Given a vehicle's make, model, and year, classify it into one of three tiers:
- "Low": Economy and budget vehicles. Repair parts are cheaply available. Examples: Toyota Corolla, Honda Civic, Hyundai i10, Maruti Suzuki, Nissan Micra.
- "Mid": Mid-range vehicles, family SUVs, entry-level luxury. Examples: Toyota Camry, Honda CR-V, BMW 3-Series, Mercedes C-Class, Tesla Model 3.
- "High": Luxury, sports, or premium electric vehicles. Repair parts are rare and expensive. Examples: BMW 7-Series, Mercedes S-Class, Porsche 911, Bentley, Ferrari, Lamborghini, Tesla Model S, Range Rover.

Return ONLY a JSON object like this:
{
  "tier": "Low" | "Mid" | "High",
  "reason": "brief one-sentence reason"
}
"""

FALLBACK_RULES = {
    "ferrari": "High", "lamborghini": "High", "porsche": "High", "bentley": "High",
    "rolls-royce": "High", "aston martin": "High", "maserati": "High",
    "bmw": "Mid", "mercedes": "Mid", "mercedes-benz": "Mid", "audi": "Mid",
    "tesla": "Mid", "lexus": "Mid", "volvo": "Mid", "jaguar": "Mid",
    "toyota": "Low", "honda": "Low", "hyundai": "Low", "kia": "Low",
    "ford": "Low", "chevrolet": "Low", "nissan": "Low", "suzuki": "Low",
    "maruti": "Low", "renault": "Low", "volkswagen": "Low", "skoda": "Low",
}


def _fallback_classify(make: str, model: str, year: int) -> Dict[str, Any]:
    """Simple rule-based fallback when Groq is unavailable."""
    make_lower = make.strip().lower()
    tier = FALLBACK_RULES.get(make_lower, "Mid")

    # Boost tier for known luxury model names
    model_lower = model.strip().lower()
    high_models = ["s-class", "model s", "7 series", "a8", "q8", "range rover", "escalade"]
    if any(m in model_lower for m in high_models):
        tier = "High"

    return {"tier": tier, "reason": f"Rule-based classification for {make}", "_fallback": True}


async def classify_vehicle(make: str, model: str, year: int) -> Dict[str, Any]:
    """
    Classifies the vehicle into Low / Mid / High tier.
    Returns a dict with keys: tier, reason, and optionally _fallback.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY not set — using rule-based vehicle classification.")
        return _fallback_classify(make, model, year)

    user_message = f"Vehicle: {year} {make} {model}. Classify it."

    try:
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()
            raw = result["choices"][0]["message"]["content"]

        parsed = json.loads(raw)
        tier = parsed.get("tier", "Mid")

        # Normalise — only allow Low / Mid / High
        if tier not in ("Low", "Mid", "High"):
            tier = "Mid"

        logger.info("Vehicle %d %s %s classified as %s", year, make, model, tier)
        return {"tier": tier, "reason": parsed.get("reason", ""), "make": make, "model": model, "year": year}

    except Exception as exc:
        logger.error("classifier_agent failed, using rule-based fallback: %s", exc)
        return _fallback_classify(make, model, year)
