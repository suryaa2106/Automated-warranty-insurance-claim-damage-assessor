"""
decision_agent.py
-------------------
Combines fraud, cost, and policy signals into a single claim verdict:
'APPROVED', 'REJECTED', or 'FLAGGED_FOR_MANUAL_REVIEW', plus a confidence
score representing how certain the system is in its own verdict.

Decision logic (simple, explainable rules — easy to defend in a demo/Q&A):
1. Fraud flag raised            -> FLAGGED_FOR_MANUAL_REVIEW (never auto-reject
                                    on fraud alone; a human should confirm).
2. Policy inactive                -> REJECTED
3. Nothing covered by policy      -> REJECTED
4. Some items uncovered / capped  -> FLAGGED_FOR_MANUAL_REVIEW (partial payout
                                    needs a human sign-off)
5. Fully covered, no fraud signal -> APPROVED
"""

from typing import Any, Dict


def decide(fraud_result: Dict[str, Any], cost_result: Dict[str, Any], policy_result: Dict[str, Any]) -> Dict[str, Any]:
    reasons = []
    confidence = 95  # start high, subtract for each uncertainty signal

    if not policy_result["is_active"]:
        status = "REJECTED"
        reasons.append("Policy is not active.")
        confidence = 99
        return _build_result(status, confidence, reasons)

    if fraud_result["fraud_flag"]:
        status = "FLAGGED_FOR_MANUAL_REVIEW"
        reasons.append("Fraud signal detected — requires human review before payout.")
        if not fraud_result["exif_check"]["exif_present"]:
            reasons.append("Image metadata (EXIF) was missing or stripped.")
        if fraud_result["exif_check"].get("timestamp_valid") is False:
            reasons.append("Photo capture timestamp did not match submission time.")
        if fraud_result["duplicate_check"]["is_duplicate"]:
            reasons.append("Image closely matches a previously submitted claim photo.")
        confidence -= 35
        return _build_result(status, max(confidence, 40), reasons)

    if len(policy_result["uncovered_items"]) == len(cost_result["line_items"]) and cost_result["line_items"]:
        status = "REJECTED"
        reasons.append("None of the reported damage is covered under this policy type.")
        confidence = 90
        return _build_result(status, confidence, reasons)

    if policy_result["uncovered_items"] or policy_result["capped"]:
        status = "FLAGGED_FOR_MANUAL_REVIEW"
        if policy_result["uncovered_items"]:
            reasons.append("Some damaged parts are not covered under this policy — partial payout requires review.")
        if policy_result["capped"]:
            reasons.append("Estimated payout exceeds the policy's coverage cap.")
        confidence -= 20
        return _build_result(status, max(confidence, 50), reasons)

    status = "APPROVED"
    reasons.append("All reported damage is covered, no fraud signals detected, policy is active.")
    return _build_result(status, confidence, reasons)


def _build_result(status: str, confidence: int, reasons) -> Dict[str, Any]:
    return {
        "status": status,
        "confidence_score": confidence,
        "reasons": reasons,
    }
