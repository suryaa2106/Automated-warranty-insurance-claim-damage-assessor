"""
main.py
---------
FastAPI entry point. Exposes:

  POST /api/claims          -> submit a new claim (multipart form: image + fields)
  GET  /api/claims/{id}     -> fetch a previously processed claim
  GET  /api/health          -> simple health check for uptime pings

CORS is wide-open for the hackathon (frontend on Vercel, backend on Render —
different origins). Tighten `allow_origins` before any real deployment.
"""

import json
import logging
import traceback

import numpy as np
from dotenv import load_dotenv
load_dotenv()  # loads backend/.env automatically

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

import orchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")


# ── Numpy-safe JSON encoder: converts all numpy scalars/arrays to native Python ──
class NumpySafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


class NumpySafeJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, cls=NumpySafeEncoder).encode("utf-8")


app = FastAPI(
    title="Automated Warranty/Insurance Claim Damage Assessor",
    default_response_class=NumpySafeJSONResponse,
)

# ── CORS must be added BEFORE the exception handler so headers are injected ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your Vercel domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global error handler: ensures CORS headers are present on 500s too ──
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {exc}"},
        headers={"Access-Control-Allow-Origin": "*"},
    )



class ClaimResponse(BaseModel):
    claim_id: str
    submitted_at: str
    vision_result: dict
    fraud_result: dict
    cost_result: dict
    policy_result: dict
    decision_result: dict
    summary_text: str




@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/docs")


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


@app.post("/api/claims", response_model=ClaimResponse)
async def submit_claim(
    user_name: str = Form(...),
    vehicle_reg_number: str = Form(...),
    insurance_type: str = Form(...),
    policy_id: str = Form(...),
    image: UploadFile = File(...),
):
    if image.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="Unsupported image type. Use JPEG, PNG, or WEBP.")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image upload.")

    try:
        result = await orchestrator.process_claim(
            user_name=user_name,
            vehicle_reg_number=vehicle_reg_number,
            insurance_type=insurance_type,
            policy_id=policy_id,
            image_bytes=image_bytes,
            mime_type=image.content_type,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("Claim processing failed")
        raise HTTPException(status_code=500, detail=f"Claim processing failed: {exc}") from exc


@app.get("/api/claims/{claim_id}")
async def get_claim(claim_id: str):
    record = orchestrator.get_claim(claim_id)
    if not record:
        raise HTTPException(status_code=404, detail="Claim not found.")
    return record


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
