"""
vehicle_db.py
--------------
In-memory vehicle + customer registry with Supabase fallback.
Insurers register vehicles via the /api/insurer/register endpoint.
Customers authenticate via /api/auth/login by matching vehicle_reg_number + customer_number.

Data shape:
  {
    "vehicle_reg_number": str,
    "customer_number": str,
    "customer_name": str,
    "make": str,
    "model": str,
    "year": int,
    "price_tier": "Low" | "Mid" | "High",
    "policy_id": str,
    "insurance_type": str,
  }
"""

import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("vehicle_db")

# In-memory store (survives only for the server process lifetime)
_VEHICLES: Dict[str, Dict[str, Any]] = {
    # Pre-seeded demo vehicles
    "ABC-1234": {
        "vehicle_reg_number": "ABC-1234",
        "customer_number": "CUST-001",
        "customer_name": "Alex Johnson",
        "make": "Toyota",
        "model": "Corolla",
        "year": 2020,
        "color": "White",
        "price_tier": "Low",
        "policy_id": "POLICY-DEMO-001",
        "insurance_type": "Comprehensive",
    },
    "XYZ-5678": {
        "vehicle_reg_number": "XYZ-5678",
        "customer_number": "CUST-002",
        "customer_name": "Sarah Miller",
        "make": "BMW",
        "model": "5 Series",
        "year": 2022,
        "color": "Black",
        "price_tier": "Mid",
        "policy_id": "POLICY-DEMO-001",
        "insurance_type": "Comprehensive",
    },
    "LUX-9999": {
        "vehicle_reg_number": "LUX-9999",
        "customer_number": "CUST-003",
        "customer_name": "James Doe",
        "make": "Porsche",
        "model": "911 Carrera",
        "year": 2023,
        "color": "Silver",
        "price_tier": "High",
        "policy_id": "POLICY-DEMO-002",
        "insurance_type": "Comprehensive",
    },
}


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


def get_vehicle(vehicle_reg_number: str) -> Optional[Dict[str, Any]]:
    """Fetch a vehicle record by registration number."""
    reg = vehicle_reg_number.strip().upper()

    # Try Supabase first
    client = _get_supabase_client()
    if client:
        try:
            response = client.table("vehicles").select("*").eq("vehicle_reg_number", reg).single().execute()
            if response.data:
                return response.data
        except Exception as exc:
            logger.warning("Supabase vehicle fetch failed, checking memory: %s", exc)

    return _VEHICLES.get(reg)


def authenticate_customer(vehicle_reg_number: str, customer_number: str) -> Optional[Dict[str, Any]]:
    """
    Validates vehicle_reg_number + customer_number pair.
    Returns the vehicle record on success, None on failure.
    """
    vehicle = get_vehicle(vehicle_reg_number)
    if not vehicle:
        return None
    if vehicle.get("customer_number", "").strip().upper() == customer_number.strip().upper():
        return vehicle
    return None


def register_vehicle(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Saves a new vehicle record. Normalises the reg number to uppercase.
    Persists to Supabase if configured, always writes to in-memory store.
    """
    reg = data["vehicle_reg_number"].strip().upper()
    data["vehicle_reg_number"] = reg

    # Try Supabase
    client = _get_supabase_client()
    if client:
        try:
            client.table("vehicles").upsert(data).execute()
            logger.info("Vehicle %s saved to Supabase.", reg)
        except Exception as exc:
            logger.warning("Supabase vehicle upsert failed, storing in memory: %s", exc)

    _VEHICLES[reg] = data
    logger.info("Vehicle %s registered in memory.", reg)
    return data
