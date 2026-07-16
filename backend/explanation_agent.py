"""
explanation_agent.py
----------------------
Takes the raw numerical/conditional outputs from every other agent and asks
Gemini to synthesize a short, empathetic, plain-English summary that the
customer will actually read — explaining what was found and why the
decision came out the way it did.

Falls back to a template-based summary (no API call) if GEMINI_API_KEY is
missing or the call fails, so the pipeline always returns a usable summary.
"""

import os
import logging
import httpx
from typing import Any, Dict

logger = logging.getLogger("explanation_agent")

MODEL_NAME = "llama-3.3-70b-versatile"


def _template_summary(vision_result: Dict, cost_result: Dict, policy_result: Dict, decision_result: Dict) -> str:
    status = decision_result["status"]
    parts = ", ".join(p["part_name"] for p in vision_result.get("damaged_parts", [])) or "no damage"
    subtotal = cost_result["subtotal"]
    payout = policy_result["final_payout_estimate"]

    if status == "APPROVED":
        return (
            f"Good news — your claim has been approved. We identified damage to: {parts}, "
            f"totaling an estimated ${subtotal}. After your ${policy_result['deductible_applied']} "
            f"deductible, your estimated payout is ${payout}. Funds are typically processed within "
            "3-5 business days."
        )
    if status == "REJECTED":
        return (
            f"We're sorry, but your claim could not be approved at this time. "
            f"{' '.join(decision_result['reasons'])} If you believe this is an error, "
            "please contact support with your claim ID for a manual review."
        )
    return (
        f"Your claim is currently under manual review. We identified damage to: {parts}, "
        f"with an estimated cost of ${subtotal}. {' '.join(decision_result['reasons'])} "
        "A claims adjuster will follow up within 1-2 business days."
    )


async def generate_explanation(
    vision_result: Dict[str, Any],
    fraud_result: Dict[str, Any],
    cost_result: Dict[str, Any],
    policy_result: Dict[str, Any],
    decision_result: Dict[str, Any],
) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY not set — using template explanation.")
        return _template_summary(vision_result, cost_result, policy_result, decision_result)

    prompt = f"""You are a claims support assistant writing directly to a customer.
Write a short (3-5 sentence), warm, clear, empathetic paragraph explaining the outcome of
their vehicle damage claim. Do not use markdown. Be factual and avoid overpromising.

Data:
- Detected vehicle type: {vision_result.get('vehicle_type')}
- Damaged parts: {vision_result.get('damaged_parts')}
- Estimated repair subtotal: ${cost_result.get('subtotal')}
- Policy deductible: ${policy_result.get('deductible_applied')}
- Estimated payout: ${policy_result.get('final_payout_estimate')}
- Final decision: {decision_result.get('status')}
- Reasons: {decision_result.get('reasons')}

Write only the paragraph, addressed to the customer."""

    try:
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            text = result["choices"][0]["message"]["content"].strip()

        return text if text else _template_summary(vision_result, cost_result, policy_result, decision_result)
    except Exception as exc:  # noqa: BLE001
        logger.error("explanation_agent failed, falling back to template: %s", exc)
        return _template_summary(vision_result, cost_result, policy_result, decision_result)
