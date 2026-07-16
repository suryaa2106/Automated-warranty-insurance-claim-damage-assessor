"""
cost_agent.py
--------------
Turns the structured damage list from vision_agent into a dollar estimate
using a hardcoded lookup table. This keeps the hackathon build fast and
deterministic — swap for a real parts/labor pricing API post-hackathon.

Pricing keys are matched on a normalized "part_name + damage_type" basis,
with graceful fallback to a generic per-severity estimate when no exact
lookup entry exists (so unseen part/damage combos still produce a price
instead of crashing the pipeline).
"""

from typing import Any, Dict, List

# (part_name, damage_type) -> flat USD cost, lowercased for matching.
COST_LOOKUP = {
    ("front bumper", "dent"): 400,
    ("rear bumper", "dent"): 400,
    ("front bumper", "scratch"): 180,
    ("rear bumper", "scratch"): 180,
    ("windshield", "scratch"): 250,
    ("windshield", "shatter"): 900,
    ("windshield", "total loss"): 1200,
    ("headlight", "crack"): 220,
    ("headlight", "total loss"): 350,
    ("side mirror", "crack"): 150,
    ("side mirror", "total loss"): 220,
    ("door panel", "dent"): 500,
    ("door panel", "scratch"): 200,
    ("fender", "dent"): 380,
    ("hood", "dent"): 450,
    ("taillight", "crack"): 180,
    ("taillight", "total loss"): 300,
    ("wheel/rim", "scratch"): 150,
    ("wheel/rim", "total loss"): 600,
}

# Fallback per-severity flat rate ($) when part/damage combo isn't in the table.
SEVERITY_FALLBACK = {1: 100, 2: 200, 3: 400, 4: 700, 5: 1200}


def _lookup_cost(part_name: str, damage_type: str, severity_score: int) -> Dict[str, Any]:
    key = (part_name.strip().lower(), damage_type.strip().lower())
    if key in COST_LOOKUP:
        return {"cost": COST_LOOKUP[key], "source": "lookup_table"}

    fallback_cost = SEVERITY_FALLBACK.get(severity_score, SEVERITY_FALLBACK[3])
    return {"cost": fallback_cost, "source": "severity_fallback"}


def estimate_cost(damaged_parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    damaged_parts: list of {part_name, damage_type, severity_score}
    Returns an itemized breakdown plus a subtotal.
    """
    line_items = []
    subtotal = 0

    for part in damaged_parts:
        part_name = part.get("part_name", "Unknown Part")
        damage_type = part.get("damage_type", "Unknown Damage")
        severity_score = int(part.get("severity_score", 3))

        priced = _lookup_cost(part_name, damage_type, severity_score)
        line_items.append({
            "part_name": part_name,
            "damage_type": damage_type,
            "severity_score": severity_score,
            "estimated_cost": priced["cost"],
            "pricing_source": priced["source"],
        })
        subtotal += priced["cost"]

    return {
        "line_items": line_items,
        "subtotal": subtotal,
    }
