"""
audit.py — POST /api/audit

Single endpoint that accepts multipart CSV uploads plus an optional JSON
config override, runs the full Pipecheck audit pipeline, and returns a
structured JSON response.

──────────────────────────────────────────────────────────────────────────────

Request  (multipart/form-data)
──────────────────────────────
  contacts   : file  (required) — contacts CSV
  companies  : file  (optional) — companies CSV  (empty DataFrame if omitted)
  deals      : file  (optional) — deals CSV       (empty DataFrame if omitted)
  config     : str   (optional) — JSON-encoded config overrides; merged on
                                  top of DEFAULT_CONFIG before the run.
                                  Any key in DEFAULT_CONFIG may be overridden.

Response  (JSON)
────────────────
{
  "score": {
    "overall":         89,
    "contacts":        91,
    "companies":       91,
    "deals":           84,
    "overall_color":   "green",
    "contacts_color":  "green",
    "companies_color": "green",
    "deals_color":     "green"
  },
  "costs": {
    "direct_cost":       778.75,
    "at_risk_pipeline":  153750.00,
    "total_rep_hours":   10.38
  },
  "punch_list": [ ... 13 rows ... ],
  "metadata": {
    "record_counts": { "contacts": 50, "companies": 20, "deals": 20 },
    "source":        "upload" | "sample",
    "timestamp":     "2026-08-04T19:35:00",
    "filenames":     { "contacts": "contacts.csv", ... }
  }
}

Errors
──────
  400  — contacts file is missing or not a CSV
  422  — CSV parsing failed (malformed file)
  500  — unexpected engine error
"""

from __future__ import annotations

import io
import json
import traceback
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ..config import DEFAULT_CONFIG, build_config
from ..models import AuditConfig
from ..parser import parse_upload
from ..checks import run_all_checks
from ..scorer import score as run_scorer
from ..costs import calculate_costs
from ..punchlist import build_punch_list

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_config(user_config_json: Optional[str]) -> dict:
    """
    Merge a user-supplied JSON config patch on top of DEFAULT_CONFIG.

    Only keys that are present in DEFAULT_CONFIG are applied; unknown keys
    are silently discarded.  Deep-merges one level so that, e.g., supplying
    {"inactivity": {"contact_decay_days": 60}} only overrides that one key
    without wiping the rest of the inactivity block.
    """
    base = build_config()
    if not user_config_json:
        return base

    try:
        patch = json.loads(user_config_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"config field is not valid JSON: {exc}",
        )

    if not isinstance(patch, dict):
        raise HTTPException(
            status_code=400,
            detail="config must be a JSON object",
        )

    for top_key, top_val in patch.items():
        if top_key not in base:
            continue  # unknown top-level key — ignore
        if isinstance(base[top_key], dict) and isinstance(top_val, dict):
            base[top_key].update(top_val)   # shallow merge one level deep
        else:
            base[top_key] = top_val         # replace scalar / list outright

    return base


async def _read_upload(upload: Optional[UploadFile], label: str) -> Optional[bytes]:
    """Read an UploadFile to bytes, returning None if the file was not supplied."""
    if upload is None:
        return None
    if upload.filename == "" or upload.size == 0:
        return None
    try:
        return await upload.read()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read '{label}' file: {exc}",
        )


def _punch_list_to_json(punch_list) -> list[dict]:
    """Serialise punch list items, converting Timestamps and NA to JSON-safe types."""
    rows = []
    for item in punch_list:
        d = item.to_dict()
        # affected_record_ids is already a list[str] — safe as-is
        rows.append(d)
    return rows


# ---------------------------------------------------------------------------
# POST /api/audit
# ---------------------------------------------------------------------------

@router.post(
    "/audit",
    summary="Run the full Pipecheck audit pipeline",
    description=(
        "Accepts multipart CSV uploads for contacts (required), companies "
        "(optional), and deals (optional), plus an optional JSON config body. "
        "Runs parse → checks → score → costs → punchlist and returns a "
        "complete audit result."
    ),
    response_class=JSONResponse,
)
async def run_audit(
    contacts:  UploadFile                = File(...,  description="HubSpot contacts CSV export"),
    companies: Optional[UploadFile]      = File(default=None, description="HubSpot companies CSV export (optional)"),
    deals:     Optional[UploadFile]      = File(default=None, description="HubSpot deals CSV export (optional)"),
    config:    Optional[str]       = Form(None, description="JSON-encoded config overrides"),
):
    """
    Run the full Pipecheck audit pipeline and return a structured result.
    """
    # ── 1. Read uploaded files ───────────────────────────────────────────
    if contacts is None or not contacts.filename:
        raise HTTPException(status_code=400, detail="'contacts' file is required.")

    contacts_bytes  = await _read_upload(contacts,  "contacts")
    companies_bytes = await _read_upload(companies, "companies")
    deals_bytes     = await _read_upload(deals,     "deals")

    if not contacts_bytes:
        raise HTTPException(
            status_code=400,
            detail="'contacts' file is empty or missing.",
        )

    # ── 2. Build config ──────────────────────────────────────────────────
    try:
        raw_config = _merge_config(config)
        cfg        = AuditConfig.from_dict(raw_config)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid config: {exc}",
        )

    # ── 3. Parse CSVs ────────────────────────────────────────────────────
    try:
        data = parse_upload(
            contacts_source=contacts_bytes,
            companies_source=companies_bytes,   # None → empty DataFrame
            deals_source=deals_bytes,           # None → empty DataFrame
        )
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"CSV parsing failed: {exc}",
        )

    # ── 4. Run the audit pipeline ────────────────────────────────────────
    try:
        findings     = run_all_checks(data, cfg)
        score_result = run_scorer(findings, data, cfg)
        cost_result  = calculate_costs(findings, data, cfg)
        punch_list   = build_punch_list(findings, score_result, cost_result, data, cfg)
    except Exception as exc:
        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Audit engine error: {exc}\n{tb}",
        )

    # ── 5. Assemble response ─────────────────────────────────────────────
    response = {
        "score": score_result.to_dict(),
        "costs": {
            "direct_cost":       round(cost_result.total_direct_cost, 2),
            "at_risk_pipeline":  round(cost_result.total_at_risk_pipeline, 2),
            "total_rep_hours":   round(cost_result.total_rep_hours, 2),
        },
        "punch_list": _punch_list_to_json(punch_list),
        "metadata": {
            "record_counts": {
                "contacts":  data.n_contacts,
                "companies": data.n_companies,
                "deals":     data.n_deals,
            },
            "source":    "upload",
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
            "filenames": {
                "contacts":  contacts.filename  or "",
                "companies": (companies.filename if companies else "") or "",
                "deals":     (deals.filename     if deals     else "") or "",
            },
        },
    }

    return JSONResponse(content=response)


# ---------------------------------------------------------------------------
# POST /api/audit/sample
# (convenience: run the full audit against the bundled sample data without
#  requiring the user to upload anything)
# ---------------------------------------------------------------------------

from pathlib import Path

SAMPLE_DIR = (
    Path(__file__).parent.parent.parent.parent  # backend/
    / "frontend" / "public" / "sample"
)


@router.post(
    "/audit/sample",
    summary="Run the full audit against the bundled sample dataset",
    response_class=JSONResponse,
)
async def run_audit_sample(
    config: Optional[str] = Form(None, description="JSON-encoded config overrides"),
):
    """
    Run the complete audit pipeline against the pre-loaded sample CSVs.
    Equivalent to uploading the sample files manually.
    """
    contacts_path  = SAMPLE_DIR / "contacts.csv"
    companies_path = SAMPLE_DIR / "companies.csv"
    deals_path     = SAMPLE_DIR / "deals.csv"

    for p in (contacts_path, companies_path, deals_path):
        if not p.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Sample file missing: {p.name}",
            )

    try:
        raw_config = _merge_config(config)
        cfg        = AuditConfig.from_dict(raw_config)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid config: {exc}")

    try:
        data = parse_upload(
            contacts_source=str(contacts_path),
            companies_source=str(companies_path),
            deals_source=str(deals_path),
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"CSV parsing failed: {exc}")

    try:
        findings     = run_all_checks(data, cfg)
        score_result = run_scorer(findings, data, cfg)
        cost_result  = calculate_costs(findings, data, cfg)
        punch_list   = build_punch_list(findings, score_result, cost_result, data, cfg)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Audit engine error: {exc}")

    return JSONResponse(content={
        "score":      score_result.to_dict(),
        "costs": {
            "direct_cost":      round(cost_result.total_direct_cost, 2),
            "at_risk_pipeline": round(cost_result.total_at_risk_pipeline, 2),
            "total_rep_hours":  round(cost_result.total_rep_hours, 2),
        },
        "punch_list": _punch_list_to_json(punch_list),
        "metadata": {
            "record_counts": {
                "contacts":  data.n_contacts,
                "companies": data.n_companies,
                "deals":     data.n_deals,
            },
            "source":    "sample",
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
            "filenames": {
                "contacts":  "contacts.csv",
                "companies": "companies.csv",
                "deals":     "deals.csv",
            },
        },
    })
