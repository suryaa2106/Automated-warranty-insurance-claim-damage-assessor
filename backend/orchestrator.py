"""
orchestrator.py
------------------
The conductor of the multi-agent pipeline. Receives the parsed request from
main.py (user data, policy ID, image bytes), runs each agent in the correct
sequence, threads state between them, and commits the final result to
Supabase (with an in-memory fallback so the demo works without a DB).

Pipeline order:
  vision_agent -> fraud_agent -> cost_agent -> policy_agent -> decision_agent
  -> explanation_agent -> persist
"""

import os
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import vision_agent
import fraud_agent
import cost_agent
import policy_agent
import decision_agent
import explanation_agent
import vehicle_db

logger = logging.getLogger("orchestrator")

# In-memory fallback "table" used when Supabase isn't configured — keeps the
# app fully functional for a live demo without any external dependency.
_IN_MEMORY_CLAIMS: Dict[str, Dict[str, Any]] = {}


def _get_supabase_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as exc:
        logger.error("Supabase client init failed: %s", exc)
        return None


async def _persist_claim(record: Dict[str, Any]) -> None:
    client = _get_supabase_client()
    if client:
        try:
            client.table("claims").insert(record).execute()
            return
        except Exception as exc:
            logger.warning("Supabase insert failed, storing in-memory instead: %s", exc)

    _IN_MEMORY_CLAIMS[record["claim_id"]] = record


async def process_claim(
    user_name: str,
    vehicle_reg_number: str,
    insurance_type: str,
    policy_id: str,
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> Dict[str, Any]:
    """
    Runs the full multi-agent pipeline for one claim submission and returns
    the complete, structured result (also persisted to Supabase / memory).
    """
    claim_id = f"CLAIM-{uuid.uuid4().hex[:10].upper()}"
    submitted_at = datetime.now(timezone.utc).isoformat()

    # 1. Vision — what's damaged?
    vision_result = await vision_agent.analyze_damage(image_bytes, mime_type)

    # 2. Fraud — is this photo trustworthy?
    fraud_result = await fraud_agent.assess_fraud(image_bytes)

    # 2b. Fetch vehicle price tier for cost scaling
    vehicle_record = vehicle_db.get_vehicle(vehicle_reg_number)
    price_tier = vehicle_record.get("price_tier", "Low") if vehicle_record else "Low"

    # 3. Cost — what will it cost to repair? (scaled by vehicle price tier)
    cost_result = cost_agent.estimate_cost(vision_result.get("damaged_parts", []), price_tier=price_tier)

    # 4. Policy — what does the customer's policy actually cover?
    policy_result = policy_agent.validate_policy(policy_id, cost_result["line_items"], cost_result["subtotal"])

    # 5. Decision — approve / reject / flag
    decision_result = decision_agent.decide(fraud_result, cost_result, policy_result)

    # 6. Explanation — human-readable summary
    summary_text = await explanation_agent.generate_explanation(
        vision_result, fraud_result, cost_result, policy_result, decision_result
    )

    record = {
        "claim_id": claim_id,
        "submitted_at": submitted_at,
        "user_name": user_name,
        "vehicle_reg_number": vehicle_reg_number,
        "insurance_type": insurance_type,
        "policy_id": policy_id,
        "vision_result": vision_result,
        "fraud_result": fraud_result,
        "cost_result": cost_result,
        "policy_result": policy_result,
        "decision_result": decision_result,
        "summary_text": summary_text,
    }

    await _persist_claim(record)

    return record


def get_claim(claim_id: str) -> Optional[Dict[str, Any]]:
    """Lookup helper used by an optional GET /claims/{id} endpoint."""
    client = _get_supabase_client()
    if client:
        try:
            response = client.table("claims").select("*").eq("claim_id", claim_id).single().execute()
            if response.data:
                return response.data
        except Exception as exc:
            logger.warning("Supabase claim fetch failed, checking memory: %s", exc)

    return _IN_MEMORY_CLAIMS.get(claim_id)
