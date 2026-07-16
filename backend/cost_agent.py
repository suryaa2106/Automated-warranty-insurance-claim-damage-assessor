"""
cost_agent.py
--------------
Turns the structured damage list from vision_agent into a dollar estimate
using a hardcoded lookup table + a vehicle price-tier multiplier.

Tier multipliers:
  Low  -> 1.0x  (economy parts, widely available)
  Mid  -> 1.4x  (mid-range parts)
  High -> 2.2x  (luxury/rare OEM parts, specialist labour)

Pricing keys are matched on a normalised "part_name + damage_type" basis,
with graceful fallback to a generic per-severity estimate when no exact
lookup entry exists.
"""

from typing import Any, Dict, List

# (part_name, damage_type) -> base USD cost (Low-tier baseline), lowercased.
COST_LOOKUP = {
    ("front bumper", "dent"): 400,
    ("rear bumper", "dent"): 400,
    ("front bumper", "scratch"): 180,
    ("rear bumper", "scratch"): 180,
    ("windshield", "scratch"): 250,
    ("windshield", "shatter"): 900,
    ("windshield", "crack"): 700,
    ("windshield", "total loss"): 1200,
    ("headlight", "crack"): 220,
    ("headlight", "total loss"): 350,
    ("side mirror", "crack"): 150,
    ("side mirror", "total loss"): 220,
    ("door panel", "dent"): 500,
    ("door panel", "scratch"): 200,
    ("fender", "dent"): 380,
    ("fender", "scratch"): 180,
    ("hood", "dent"): 450,
    ("hood", "scratch"): 220,
    ("taillight", "crack"): 180,
    ("taillight", "total loss"): 300,
    ("wheel/rim", "scratch"): 150,
    ("wheel/rim", "total loss"): 600,
    ("trunk", "dent"): 420,
    ("trunk", "scratch"): 190,
    ("roof", "dent"): 550,
    ("roof panel", "dent"): 550,
    ("quarter panel", "dent"): 480,
}

# Fallback per-severity flat rate ($) when part/damage combo isn't in the table.
SEVERITY_FALLBACK = {1: 100, 2: 200, 3: 400, 4: 700, 5: 1200}

# Price tier cost multipliers
TIER_MULTIPLIERS = {
    "Low": 1.0,
    "Mid": 1.4,
    "High": 2.2,
}


def _lookup_cost(part_name: str, damage_type: str, severity_score: int) -> Dict[str, Any]:
    key = (part_name.strip().lower(), damage_type.strip().lower())
    if key in COST_LOOKUP:
        return {"cost": COST_LOOKUP[key], "source": "lookup_table"}

    fallback_cost = SEVERITY_FALLBACK.get(severity_score, SEVERITY_FALLBACK[3])
    return {"cost": fallback_cost, "source": "severity_fallback"}


def estimate_cost(damaged_parts: List[Dict[str, Any]], price_tier: str = "Low") -> Dict[str, Any]:
    """
    damaged_parts: list of {part_name, damage_type, severity_score}
    price_tier:   "Low", "Mid", or "High" — scales all costs by tier multiplier
    Returns an itemised breakdown plus a subtotal.
    """
    multiplier = TIER_MULTIPLIERS.get(price_tier, 1.0)
    line_items = []
    subtotal = 0

    for part in damaged_parts:
        part_name = part.get("part_name", "Unknown Part")
        damage_type = part.get("damage_type", "Unknown Damage")
        severity_score = int(part.get("severity_score", 3))

        priced = _lookup_cost(part_name, damage_type, severity_score)
        base_cost = priced["cost"]
        scaled_cost = round(base_cost * multiplier)

        line_items.append({
            "part_name": part_name,
            "damage_type": damage_type,
            "severity_score": severity_score,
            "base_cost": base_cost,
            "estimated_cost": scaled_cost,
            "pricing_source": priced["source"],
            "tier_multiplier": multiplier,
        })
        subtotal += scaled_cost

    return {
        "line_items": line_items,
        "subtotal": subtotal,
        "price_tier": price_tier,
        "tier_multiplier": multiplier,
    }
