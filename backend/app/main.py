"""
main.py — FastAPI application entry point for Pipecheck.

Endpoints
---------
GET  /                       health probe
GET  /api/health             health probe (JSON)
GET  /api/config/defaults    return the full default config dict
GET  /api/parse-sample       parse the bundled sample CSVs, return record counts
POST /api/parse              accept user-uploaded CSVs, return record counts
POST /api/audit              full audit pipeline (parse→checks→score→costs→punchlist)
POST /api/audit/sample       run full audit against the bundled sample dataset
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import DEFAULT_CONFIG, build_config
from .parser import parse_upload
from .models import AuditConfig
from .routes.audit import router as audit_router
from .routes.export import router as export_router

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Pipecheck API",
    description="Backend API for the Pipecheck HubSpot CRM Audit Engine",
    version="1.0.0",
)

# Accept requests from both Vite dev-server ports (5173 and 5174)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "https://pipecheck-ten.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers — provides /api/audit and /api/export endpoints
app.include_router(audit_router, prefix="/api")
app.include_router(export_router, prefix="/api")

# Path to the bundled sample CSVs served as static assets by Vite.
# When running the backend standalone, resolve relative to this file.
SAMPLE_DIR = Path(__file__).parent.parent.parent / "frontend" / "public" / "sample"


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

@app.get("/")
def read_root():
    return {"message": "Pipecheck API is running"}


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "pipecheck-backend"}


# ---------------------------------------------------------------------------
# Config endpoint — lets the frontend fetch defaults to pre-fill the Config UI
# ---------------------------------------------------------------------------

@app.get("/api/config/defaults")
def get_default_config():
    """Return the full default audit configuration as JSON."""
    return JSONResponse(content=DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# Parse: sample data
# ---------------------------------------------------------------------------

@app.get("/api/parse-sample")
def parse_sample():
    """
    Parse the bundled sample CSVs and return record counts + column lists.

    Used by the frontend when the user clicks 'Try with sample data'.
    The audit itself is triggered separately once config is confirmed.
    """
    contacts_path  = SAMPLE_DIR / "contacts.csv"
    companies_path = SAMPLE_DIR / "companies.csv"
    deals_path     = SAMPLE_DIR / "deals.csv"

    for p in (contacts_path, companies_path, deals_path):
        if not p.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Sample file not found: {p.name}. "
                       "Ensure frontend/public/sample/ CSVs are present.",
            )

    data = parse_upload(
        contacts_source=str(contacts_path),
        companies_source=str(companies_path),
        deals_source=str(deals_path),
    )

    return {
        "source": "sample",
        "record_counts": {
            "contacts":  data.n_contacts,
            "companies": data.n_companies,
            "deals":     data.n_deals,
        },
        "columns": {
            "contacts":  list(data.contacts.columns),
            "companies": list(data.companies.columns),
            "deals":     list(data.deals.columns),
        },
        "sample_rows": {
            "contacts":  _df_preview(data.contacts),
            "companies": _df_preview(data.companies),
            "deals":     _df_preview(data.deals),
        },
    }


# ---------------------------------------------------------------------------
# Parse: user-uploaded CSVs
# ---------------------------------------------------------------------------

@app.post("/api/parse")
async def parse_user_upload(
    contacts:  UploadFile = File(...),
    companies: UploadFile = File(...),
    deals:     UploadFile = File(...),
):
    """
    Accept multipart CSV uploads and return parsed record counts.

    Request body (multipart/form-data):
      contacts  : contacts CSV file
      companies : companies CSV file
      deals     : deals CSV file

    Returns record counts and column names so the frontend can display the
    file confirmation on the Config screen before the audit runs.
    """
    try:
        contacts_bytes  = await contacts.read()
        companies_bytes = await companies.read()
        deals_bytes     = await deals.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded files: {exc}")

    try:
        data = parse_upload(
            contacts_source=contacts_bytes,
            companies_source=companies_bytes,
            deals_source=deals_bytes,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"CSV parsing error: {exc}")

    return {
        "source": "upload",
        "record_counts": {
            "contacts":  data.n_contacts,
            "companies": data.n_companies,
            "deals":     data.n_deals,
        },
        "columns": {
            "contacts":  list(data.contacts.columns),
            "companies": list(data.companies.columns),
            "deals":     list(data.deals.columns),
        },
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _df_preview(df, n: int = 3) -> list[dict]:
    """Return the first n rows of a DataFrame as a list of dicts (JSON-safe)."""
    preview = df.head(n).copy()
    # Convert non-serialisable types (Timestamps, lists, NaT, NA)
    for col in preview.columns:
        preview[col] = preview[col].apply(_json_safe)
    return preview.to_dict(orient="records")


def _json_safe(val):
    """Convert a single cell value to a JSON-serialisable type."""
    import pandas as pd
    if isinstance(val, list):
        return val
    if pd.isna(val) if not isinstance(val, list) else False:
        return None
    if hasattr(val, "isoformat"):          # datetime / Timestamp
        return val.isoformat()
    return val
