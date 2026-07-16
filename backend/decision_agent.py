"""
decision_agent.py
-------------------
Combines fraud, cost, policy, and color-verification signals into a single
claim verdict: 'APPROVED', 'REJECTED', or 'FLAGGED_FOR_MANUAL_REVIEW'.

Decision logic:
1. Color mismatch (high confidence)   -> REJECTED  (vehicle identity fraud)
2. Color mismatch (medium confidence) -> FLAGGED_FOR_MANUAL_REVIEW
3. Fraud flag raised                  -> FLAGGED_FOR_MANUAL_REVIEW
4. Policy inactive                    -> REJECTED
5. Nothing covered by policy          -> REJECTED
6. Some items uncovered / capped      -> FLAGGED_FOR_MANUAL_REVIEW
7. Fully covered, no signals          -> APPROVED
"""

from typing import Any, Dict, Optional


def decide(
    fraud_result: Dict[str, Any],
    cost_result: Dict[str, Any],
    policy_result: Dict[str, Any],
    color_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    reasons = []
    confidence = 95  # start high, subtract for each uncertainty signal

    # ── 1. Color verification (highest priority — identity check) ──
    if color_result and not color_result.get("match", True):
        detected   = color_result.get("detected_color", "Unknown")
        registered = color_result.get("registered_color", "Unknown")
        col_conf   = color_result.get("confidence", "low")

        if col_conf == "high":
            reasons.append(
                f"Vehicle color mismatch detected with high confidence — "
                f"registered color is '{registered}' but image shows '{detected}'. "
                f"Claim auto-rejected to prevent potential vehicle identity fraud."
            )
            return _build_result("REJECTED", 97, reasons)

        elif col_conf == "medium":
            reasons.append(
                f"Possible vehicle color mismatch — registered '{registered}', "
                f"detected '{detected}' (medium confidence). Flagged for manual review."
            )
            confidence -= 30
            return _build_result("FLAGGED_FOR_MANUAL_REVIEW", max(confidence, 50), reasons)

        # low confidence → give benefit of the doubt, add informational note
        else:
            reasons.append(
                f"Color verification inconclusive (low confidence) — "
                f"registered '{registered}', detected '{detected}'. Proceeding with standard checks."
            )

    # ── 2. Policy active check ──
    if not policy_result["is_active"]:
        reasons.append("Policy is not active.")
        return _build_result("REJECTED", 99, reasons)

    # ── 3. Fraud flag ──
    if fraud_result["fraud_flag"]:
        reasons.append("Fraud signal detected — requires human review before payout.")
        if not fraud_result["exif_check"]["exif_present"]:
            reasons.append("Image metadata (EXIF) was missing or stripped.")
        if fraud_result["exif_check"].get("timestamp_valid") is False:
            reasons.append("Photo capture timestamp did not match submission time.")
        if fraud_result["duplicate_check"]["is_duplicate"]:
            reasons.append("Image closely matches a previously submitted claim photo.")
        confidence -= 35
        return _build_result("FLAGGED_FOR_MANUAL_REVIEW", max(confidence, 40), reasons)

    # ── 4. Nothing covered ──
    if len(policy_result["uncovered_items"]) == len(cost_result["line_items"]) and cost_result["line_items"]:
        reasons.append("None of the reported damage is covered under this policy type.")
        return _build_result("REJECTED", 90, reasons)

    # ── 5. Partial coverage / cap ──
    if policy_result["uncovered_items"] or policy_result["capped"]:
        if policy_result["uncovered_items"]:
            reasons.append("Some damaged parts are not covered under this policy — partial payout requires review.")
        if policy_result["capped"]:
            reasons.append("Estimated payout exceeds the policy's coverage cap.")
        confidence -= 20
        return _build_result("FLAGGED_FOR_MANUAL_REVIEW", max(confidence, 50), reasons)

    # ── 6. All clear ──
    reasons.append("All reported damage is covered, no fraud signals detected, policy is active.")
    return _build_result("APPROVED", confidence, reasons)


def _build_result(status: str, confidence: int, reasons) -> Dict[str, Any]:
    return {
        "status": status,
        "confidence_score": confidence,
        "reasons": reasons,
    }
