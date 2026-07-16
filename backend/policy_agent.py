"""
policy_agent.py
-----------------
Fetches the customer's policy bounds (deductible, coverage cap, active
status, covered categories) and validates the itemized cost breakdown
against them.

Tries Supabase first (table: `policies`, keyed by `policy_id`). If Supabase
isn't configured or the row isn't found, falls back to an in-memory mock
policy so the pipeline still runs end-to-end for a demo.
"""

import os
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("policy_agent")

MOCK_POLICIES = {
    "POLICY-DEMO-001": {
        "policy_id": "POLICY-DEMO-001",
        "active": True,
        "deductible": 250,
        "coverage_cap": 5000,
        "covered_categories": ["dent", "scratch", "crack", "shatter", "total loss"],
        "policy_type": "Comprehensive",
    },
    "POLICY-DEMO-002": {
        "policy_id": "POLICY-DEMO-002",
        "active": True,
        "deductible": 500,
        "coverage_cap": 2000,
        "covered_categories": ["dent", "scratch"],  # liability-lite, no glass/total-loss
        "policy_type": "Basic Liability",
    },
}

DEFAULT_MOCK_POLICY = MOCK_POLICIES["POLICY-DEMO-001"]


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


def fetch_policy(policy_id: str) -> Dict[str, Any]:
    client = _get_supabase_client()
    if client:
        try:
            response = client.table("policies").select("*").eq("policy_id", policy_id).single().execute()
            if response.data:
                return {**response.data, "_source": "supabase"}
        except Exception as exc:
            logger.warning("Supabase policy fetch failed, using mock: %s", exc)

    policy = MOCK_POLICIES.get(policy_id, DEFAULT_MOCK_POLICY)
    return {**policy, "_source": "mock"}


def validate_policy(policy_id: str, line_items: List[Dict[str, Any]], subtotal: int) -> Dict[str, Any]:
    policy = fetch_policy(policy_id)

    uncovered_items = [
        item for item in line_items
        if item["damage_type"].strip().lower() not in policy["covered_categories"]
    ]

    payout_before_cap = max(subtotal - policy["deductible"], 0)
    capped = payout_before_cap > policy["coverage_cap"]
    final_payout = min(payout_before_cap, policy["coverage_cap"])

    return {
        "policy": policy,
        "uncovered_items": uncovered_items,
        "is_active": policy["active"],
        "deductible_applied": policy["deductible"],
        "coverage_cap": policy["coverage_cap"],
        "payout_before_cap": payout_before_cap,
        "capped": capped,
        "final_payout_estimate": final_payout,
        "fully_covered": len(uncovered_items) == 0 and policy["active"] and not capped,
    }
