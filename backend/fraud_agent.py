"""
fraud_agent.py
---------------
Two independent fraud signals, combined into a single verdict:

1. EXIF timestamp / software check
   - Reads 'DateTimeOriginal' from EXIF and compares it to server time.
     Photos taken more than a small threshold in the past (or future) are
     suspicious for a "submit immediately after the incident" flow.
   - If EXIF is missing entirely (often a sign of screenshotting, re-saving,
     or an image editor stripping metadata) or lists known editing software
     in the 'Software' tag, we flag it too.

2. Perceptual hash duplicate check
   - Hashes the incoming image with `imagehash.phash` and compares it
     (Hamming distance) against a mocked "previous claims" array. A close
     match means this exact photo (or a lightly-edited copy) was already
     used in another claim.

This agent never blocks the pipeline by itself — it produces a signal that
decision_agent.py weighs alongside cost and policy checks.
"""

import io
import logging
import time
from typing import Any, Dict, List

import piexif
import imagehash
from PIL import Image

logger = logging.getLogger("fraud_agent")

# How far (in seconds) the EXIF capture time may drift from "now" before
# we treat it as suspicious. 2 minutes, per spec.
TIMESTAMP_THRESHOLD_SECONDS = 120

# Software tag substrings commonly left behind by editing tools.
SUSPICIOUS_SOFTWARE_MARKERS = [
    "photoshop", "gimp", "lightroom", "snapseed", "picsart", "facetune",
]

# Mocked "database" of perceptual hashes from prior claim submissions.
# In production this would be a Supabase table queried per policy/user.
MOCK_PRIOR_CLAIM_HASHES: List[str] = [
    "ffff0000ffff0000",  # placeholder example hash
]

DUPLICATE_HAMMING_THRESHOLD = 6  # lower = stricter match


def _check_exif(image_bytes: bytes) -> Dict[str, Any]:
    result = {
        "exif_present": False,
        "timestamp_valid": None,
        "suspicious_software": False,
        "reason": None,
    }

    try:
        exif_dict = piexif.load(image_bytes)
    except Exception:
        result["reason"] = "EXIF data missing or unreadable (possible screenshot/edit)"
        return result

    exif_ifd = exif_dict.get("Exif", {})
    zeroth_ifd = exif_dict.get("0th", {})

    result["exif_present"] = bool(exif_ifd or zeroth_ifd)

    # DateTimeOriginal check
    dt_original = exif_ifd.get(piexif.ExifIFD.DateTimeOriginal)
    if dt_original:
        try:
            dt_str = dt_original.decode() if isinstance(dt_original, bytes) else dt_original
            capture_epoch = time.mktime(time.strptime(dt_str, "%Y:%m:%d %H:%M:%S"))
            drift = abs(time.time() - capture_epoch)
            result["timestamp_valid"] = drift <= TIMESTAMP_THRESHOLD_SECONDS
            if not result["timestamp_valid"]:
                result["reason"] = f"Capture time drift of {int(drift)}s exceeds {TIMESTAMP_THRESHOLD_SECONDS}s threshold"
        except Exception:
            result["timestamp_valid"] = False
            result["reason"] = "Could not parse DateTimeOriginal"
    else:
        result["timestamp_valid"] = False
        result["reason"] = (result["reason"] or "") + " | No DateTimeOriginal tag present"

    # Software tag check
    software = zeroth_ifd.get(piexif.ImageIFD.Software)
    if software:
        software_str = (software.decode() if isinstance(software, bytes) else software).lower()
        if any(marker in software_str for marker in SUSPICIOUS_SOFTWARE_MARKERS):
            result["suspicious_software"] = True
            result["reason"] = (result["reason"] or "") + f" | Software tag flagged: {software_str}"

    return result


def _check_duplicate(image_bytes: bytes) -> Dict[str, Any]:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        phash = imagehash.phash(img)
    except Exception as exc:
        logger.error("Could not compute perceptual hash: %s", exc)
        return {"is_duplicate": False, "closest_distance": None, "reason": "hash computation failed"}

    closest_distance = None
    for prior_hex in MOCK_PRIOR_CLAIM_HASHES:
        try:
            prior_hash = imagehash.hex_to_hash(prior_hex)
            distance = phash - prior_hash
            if closest_distance is None or distance < closest_distance:
                closest_distance = distance
        except Exception:
            continue

    # Cast numpy types → native Python so FastAPI/JSON can serialize them
    is_duplicate = bool(closest_distance is not None and closest_distance <= DUPLICATE_HAMMING_THRESHOLD)
    return {
        "is_duplicate": is_duplicate,
        "closest_distance": int(closest_distance) if closest_distance is not None else None,
        "current_hash": str(phash),
    }


async def assess_fraud(image_bytes: bytes) -> Dict[str, Any]:
    """
    Runs both fraud checks and returns a combined verdict.
    `fraud_flag=True` means the claim should be treated as high-risk;
    decision_agent.py decides what to do with that signal.
    """
    exif_result = _check_exif(image_bytes)
    duplicate_result = _check_duplicate(image_bytes)

    exif_flag = (not exif_result["exif_present"]) or exif_result["suspicious_software"] or (exif_result["timestamp_valid"] is False)
    fraud_flag = exif_flag or duplicate_result["is_duplicate"]

    return {
        "fraud_flag": fraud_flag,
        "exif_check": exif_result,
        "duplicate_check": duplicate_result,
    }
