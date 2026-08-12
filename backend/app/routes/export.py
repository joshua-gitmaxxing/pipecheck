"""
export.py — Export Layer Endpoints

Exposes endpoints to generate and download Pipecheck's three distinct output files:

🟢 green.csv  — Ready to Import (mechanical formatting fixes only; narrow columns;
                 excludes duplicate merge candidates)
🟡 yellow.csv — Review First (paired current_ / proposed_ columns for email typos &
                 inferred lifecycle stages)
🔵 blue.txt   — Worklist (plain text checklist grouped by finding type for human judgment)

And a ZIP bundle endpoint:
📦 POST /api/export/zip — returns all three files in a single ZIP archive.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Optional, Union, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse
import pandas as pd

from ..models import ParsedData, AuditConfig
from ..config import build_config
from ..parser import parse_upload
from ..checks import run_all_checks

router = APIRouter()

SAMPLE_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "frontend" / "public" / "sample"
)

# Common country name normalization map
COUNTRY_NORM_MAP: dict[str, str] = {
    "us": "United States",
    "usa": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "gb": "United Kingdom",
    "united kingdom": "United Kingdom",
    "de": "Germany",
    "germany": "Germany",
    "fr": "France",
    "france": "France",
    "ca": "Canada",
    "canada": "Canada",
    "au": "Australia",
    "australia": "Australia",
    "jp": "Japan",
    "japan": "Japan",
    "br": "Brazil",
    "brazil": "Brazil",
    "in": "India",
    "india": "India",
    "sg": "Singapore",
    "singapore": "Singapore",
    "mx": "Mexico",
    "mexico": "Mexico",
    "es": "Spain",
    "spain": "Spain",
    "it": "Italy",
    "italy": "Italy",
    "nl": "Netherlands",
    "netherlands": "Netherlands",
    "uae": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates",
    "za": "South Africa",
    "south africa": "South Africa",
}

# Domain typo corrections map
EMAIL_TYPO_MAP: dict[str, str] = {
    "gmial.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gmal.com": "gmail.com",
    "gmaill.com": "gmail.com",
    "hotmial.com": "hotmail.com",
    "hotmali.com": "hotmail.com",
    "yaho.com": "yahoo.com",
    "yahooo.com": "yahoo.com",
    "outlok.com": "outlook.com",
    "outloo.com": "outlook.com",
}


# ---------------------------------------------------------------------------
# Generators for the 3 export files
# ---------------------------------------------------------------------------

def generate_green_csv(data: ParsedData, findings: list[dict]) -> str:
    """
    Generate green.csv — Ready to Import.

    Rules:
      - Mechanical formatting fixes only (trim string whitespace, standardize country names).
      - Include ONLY Record ID + changed columns.
      - EXCLUDE any record IDs that appear in duplicate findings (duplicate_contacts,
        duplicate_companies) to prevent collisions with master records.
      - Never change data meaning.
    """
    # Collect duplicate record IDs to exclude
    dup_rids = set()
    for f in findings:
        if f.get("finding_key") in ("duplicate_contacts", "duplicate_companies"):
            rid = str(f.get("record_id", ""))
            if rid and not rid.startswith("owner:"):
                dup_rids.add(rid)

    changed_rows = []

    # Process Contacts
    if not data.contacts.empty:
        for _, row in data.contacts.iterrows():
            rid = str(row.get("record_id", ""))
            if not rid or rid in dup_rids:
                continue

            row_changes = {}

            # Check whitespace on string columns
            for col in data.contacts.columns:
                val = row.get(col)
                if isinstance(val, str):
                    trimmed = val.strip()
                    if trimmed != val:
                        row_changes[col] = trimmed

            # Check country normalization
            if "country" in data.contacts.columns:
                country_val = str(row.get("country") or "").strip()
                if country_val:
                    norm = COUNTRY_NORM_MAP.get(country_val.lower())
                    if norm and norm != country_val:
                        row_changes["country"] = norm

            if row_changes:
                entry = {"Record ID": rid}
                entry.update(row_changes)
                changed_rows.append(entry)

    # Process Companies
    if not data.companies.empty:
        for _, row in data.companies.iterrows():
            rid = str(row.get("record_id", ""))
            if not rid or rid in dup_rids:
                continue

            row_changes = {}
            for col in data.companies.columns:
                val = row.get(col)
                if isinstance(val, str):
                    trimmed = val.strip()
                    if trimmed != val:
                        row_changes[col] = trimmed

            if row_changes:
                entry = {"Record ID": rid}
                entry.update(row_changes)
                changed_rows.append(entry)

    if not changed_rows:
        return "Record ID\n"

    df_green = pd.DataFrame(changed_rows)
    return df_green.to_csv(index=False)


def generate_yellow_csv(data: ParsedData, findings: list[dict]) -> str:
    """
    Generate yellow.csv — Review First.

    Rules:
      - Two columns per changed field: current_[field] and proposed_[field] side by side.
      - Covers:
          1. Probable email domain typos (e.g. gmial.com → gmail.com).
          2. Inferred missing/inconsistent lifecycle stage from deal data.
      - Never pre-applied — user decides.
    """
    review_rows = []

    # Map contacts attached to closed-won deals
    contacts_with_closed_deals = set()
    if not data.deals.empty:
        for _, deal_row in data.deals.iterrows():
            if deal_row.get("is_closed_won"):
                c_ids = deal_row.get("contact_ids_list") or []
                for cid in c_ids:
                    contacts_with_closed_deals.add(str(cid))

    if not data.contacts.empty:
        for _, row in data.contacts.iterrows():
            rid = str(row.get("record_id", ""))
            email = str(row.get("email") or "").strip()
            lstage = str(row.get("lifecycle_stage") or "").strip()

            proposed_email = None
            if "@" in email:
                user, domain = email.split("@", 1)
                domain_lower = domain.toLowerCase() if hasattr(domain, "toLowerCase") else domain.lower()
                if domain_lower in EMAIL_TYPO_MAP:
                    proposed_email = f"{user}@{EMAIL_TYPO_MAP[domain_lower]}"

            proposed_lstage = None
            if rid in contacts_with_closed_deals and lstage.lower() in ("lead", "subscriber", "opportunity", ""):
                proposed_lstage = "Customer"

            if proposed_email or proposed_lstage:
                entry = {"Record ID": rid}
                if proposed_email:
                    entry["current_email"] = email
                    entry["proposed_email"] = proposed_email
                if proposed_lstage:
                    entry["current_lifecycle_stage"] = lstage if lstage else "(blank)"
                    entry["proposed_lifecycle_stage"] = proposed_lstage
                review_rows.append(entry)

    if not review_rows:
        return "Record ID,current_email,proposed_email,current_lifecycle_stage,proposed_lifecycle_stage\n"

    df_yellow = pd.DataFrame(review_rows)
    return df_yellow.to_csv(index=False)


def generate_blue_txt(data: ParsedData, findings: list[dict]) -> str:
    """
    Generate blue.txt — Worklist.

    Rules:
      - Plain text checklist grouped by finding type.
      - Includes duplicate merges, stale deals, deals past close date, workload imbalance, etc.
      - Never importable.
    """
    lines = []
    lines.append("================================================================================")
    lines.append("PIPECHECK AUDIT WORKLIST — Human Judgment Action Plan")
    lines.append("================================================================================")
    lines.append("Review each item below in your CRM UI. Check off items as remediation completes.")
    lines.append("")

    # Group findings by finding_key
    grouped: dict[str, list[dict]] = {}
    for f in findings:
        key = f.get("finding_key", "other")
        grouped.setdefault(key, []).append(f)

    if not findings:
        lines.append("No findings require human judgment.")

    for key, items in grouped.items():
        label = items[0].get("label") or key.replace("_", " ").title()
        lines.append(f"--- {label} ({len(items)} items) ---")

        for item in items:
            rid = str(item.get("record_id", ""))
            detail = item.get("detail", "")
            sev = item.get("severity", "Low")

            if key in ("duplicate_contacts", "duplicate_companies"):
                lines.append(f"[ ] Merge duplicate record {rid}: {detail}")
            elif key in ("stale_deals", "deal_stage_stagnation"):
                lines.append(f"[ ] Review inactive deal {rid} [{sev}]: {detail}")
            elif key == "deals_past_close_date":
                lines.append(f"[ ] Update close date for deal {rid} [{sev}]: {detail}")
            elif key == "workload_imbalance":
                lines.append(f"[ ] Reassign territory workload [{sev}]: {detail}")
            else:
                lines.append(f"[ ] Remediate {rid} [{sev}]: {detail}")

        lines.append("")

    lines.append("================================================================================")
    lines.append("End of Worklist")
    lines.append("================================================================================")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Route Helpers
# ---------------------------------------------------------------------------

async def _get_parsed_data_and_findings(
    contacts: Optional[UploadFile],
    companies: Optional[UploadFile],
    deals: Optional[UploadFile],
    config_str: Optional[str] = None,
) -> tuple[ParsedData, list[dict]]:
    """Helper to read inputs or fall back to sample CSVs if not uploaded."""
    c_bytes = await contacts.read() if contacts and contacts.filename else None
    comp_bytes = await companies.read() if companies and companies.filename else None
    d_bytes = await deals.read() if deals and deals.filename else None

    # If no custom files provided, fall back to sample CSV files
    if not c_bytes:
        c_bytes = (SAMPLE_DIR / "contacts.csv").read_bytes()
    if not comp_bytes and (SAMPLE_DIR / "companies.csv").exists():
        comp_bytes = (SAMPLE_DIR / "companies.csv").read_bytes()
    if not d_bytes and (SAMPLE_DIR / "deals.csv").exists():
        d_bytes = (SAMPLE_DIR / "deals.csv").read_bytes()

    data = parse_upload(
        contacts_source=c_bytes,
        companies_source=comp_bytes,
        deals_source=d_bytes,
    )

    raw_cfg = build_config()
    if config_str:
        try:
            patch = json.loads(config_str)
            if isinstance(patch, dict):
                for k, v in patch.items():
                    if k in raw_cfg and isinstance(raw_cfg[k], dict) and isinstance(v, dict):
                        raw_cfg[k].update(v)
                    else:
                        raw_cfg[k] = v
        except Exception:
            pass

    cfg = AuditConfig.from_dict(raw_cfg)
    findings = run_all_checks(data, cfg)

    return data, findings


# ---------------------------------------------------------------------------
# POST /api/export
# ---------------------------------------------------------------------------

@router.post(
    "/export",
    summary="Generate export files (green.csv, yellow.csv, blue.txt)",
    description=(
        "Accepts optional CSV files and optional config string. Returns JSON "
        "containing all three file contents, or single file download if file_type "
        "query parameter ('green', 'yellow', 'blue') is specified."
    ),
)
async def post_export(
    contacts: Optional[UploadFile] = File(default=None),
    companies: Optional[UploadFile] = File(default=None),
    deals: Optional[UploadFile] = File(default=None),
    config: Optional[str] = Form(None),
    file_type: Optional[str] = Query(None, description="green | yellow | blue"),
):
    try:
        data, findings = await _get_parsed_data_and_findings(contacts, companies, deals, config)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse CSVs for export: {exc}")

    green_csv = generate_green_csv(data, findings)
    yellow_csv = generate_yellow_csv(data, findings)
    blue_txt = generate_blue_txt(data, findings)

    if file_type == "green":
        return Response(content=green_csv, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=green.csv"})
    elif file_type == "yellow":
        return Response(content=yellow_csv, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=yellow.csv"})
    elif file_type == "blue":
        return Response(content=blue_txt, media_type="text/plain", headers={"Content-Disposition": "attachment; filename=blue.txt"})

    return JSONResponse(content={
        "green_csv": green_csv,
        "yellow_csv": yellow_csv,
        "blue_txt": blue_txt,
        "filenames": {
            "green": "green.csv",
            "yellow": "yellow.csv",
            "blue": "blue.txt",
        },
    })


# ---------------------------------------------------------------------------
# POST /api/export/zip
# ---------------------------------------------------------------------------

@router.post(
    "/export/zip",
    summary="Download all export files bundled as a ZIP archive",
    description="Returns green.csv, yellow.csv, and blue.txt bundled in pipecheck_exports.zip.",
    response_class=StreamingResponse,
)
async def post_export_zip(
    contacts: Optional[UploadFile] = File(default=None),
    companies: Optional[UploadFile] = File(default=None),
    deals: Optional[UploadFile] = File(default=None),
    config: Optional[str] = Form(None),
):
    try:
        data, findings = await _get_parsed_data_and_findings(contacts, companies, deals, config)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse CSVs for ZIP export: {exc}")

    green_csv = generate_green_csv(data, findings)
    yellow_csv = generate_yellow_csv(data, findings)
    blue_txt = generate_blue_txt(data, findings)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("green.csv", green_csv)
        zf.writestr("yellow.csv", yellow_csv)
        zf.writestr("blue.txt", blue_txt)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=pipecheck_exports.zip"},
    )
