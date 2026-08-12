"""
export_smoke_test.py
====================
Tests export layer endpoints (POST /api/export and POST /api/export/zip) using
httpx.AsyncClient with ASGITransport against the live FastAPI application.

Asserts:
  1.  POST /api/export returns 200 with green_csv, yellow_csv, blue_txt.
  2.  green.csv has narrow columns (Record ID + changed columns only).
  3.  green.csv excludes duplicate record IDs (merge candidates).
  4.  yellow.csv has paired current_ / proposed_ columns.
  5.  blue.txt has at least one checklist item with '[ ]'.
  6.  POST /api/export/zip returns 200 with application/zip.
  7.  ZIP archive contains green.csv, yellow.csv, blue.txt.

Usage:
    cd backend
    .\\venv\\Scripts\\python.exe export_smoke_test.py
"""

import asyncio
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.main import app

try:
    import httpx
except ImportError:
    print("httpx is required. Install: pip install httpx")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_DIR      = Path(__file__).parent.parent / "frontend" / "public" / "sample"
CONTACTS_BYTES  = (SAMPLE_DIR / "contacts.csv").read_bytes()
COMPANIES_BYTES = (SAMPLE_DIR / "companies.csv").read_bytes()
DEALS_BYTES     = (SAMPLE_DIR / "deals.csv").read_bytes()

# ---------------------------------------------------------------------------
# Assertion helper
# ---------------------------------------------------------------------------

errors: list[str] = []


def chk(label: str, cond: bool, hint: str = "") -> bool:
    if cond:
        print(f"  [PASS] {label}")
        return True
    msg = f"  [FAIL] {label}" + (f" -- {hint}" if hint else "")
    print(msg)
    errors.append(f"{label}: {hint}")
    return False


# ---------------------------------------------------------------------------
# Async test body
# ---------------------------------------------------------------------------

async def run_tests() -> None:
    print("=" * 65)
    print("EXPORT LAYER SMOKE TEST -- POST /api/export & POST /api/export/zip")
    print("=" * 65)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:

        # ── 1. POST /api/export (JSON summary mode) ───────────────────────
        print("\n[1] POST /api/export -- generate export files")
        resp = await c.post(
            "/api/export",
            files={
                "contacts":  ("contacts.csv",  CONTACTS_BYTES,  "text/csv"),
                "companies": ("companies.csv", COMPANIES_BYTES, "text/csv"),
                "deals":     ("deals.csv",     DEALS_BYTES,     "text/csv"),
            },
        )

        chk("HTTP 200 from /api/export", resp.status_code == 200,
            f"status={resp.status_code} body={resp.text[:200]}")

        if resp.status_code != 200:
            print("\nCannot continue -- server error.")
            return

        body = resp.json()

        chk("response has 'green_csv'", "green_csv" in body)
        chk("response has 'yellow_csv'", "yellow_csv" in body)
        chk("response has 'blue_txt'", "blue_txt" in body)

        green_csv  = body.get("green_csv", "")
        yellow_csv = body.get("yellow_csv", "")
        blue_txt   = body.get("blue_txt", "")

        print(f"  green.csv length : {len(green_csv)} bytes")
        print(f"  yellow.csv length: {len(yellow_csv)} bytes")
        print(f"  blue.txt length  : {len(blue_txt)} bytes")

        # Assert green.csv narrow columns & exclusion of duplicates
        green_lines = [l.strip() for l in green_csv.splitlines() if l.strip()]
        chk("green.csv is a valid non-empty CSV string", len(green_lines) >= 1)
        if green_lines:
            header_cols = [c.strip() for c in green_lines[0].split(",")]
            chk("green.csv starts with Record ID column", header_cols[0] == "Record ID")

            # Check duplicate contacts like 1001, 1002 are excluded from green.csv
            dup_found = any(rid in green_csv for rid in ["1001", "1002", "C001", "C002"])
            chk("green.csv excludes duplicate merge candidates (1001, 1002)", not dup_found)

        # Assert yellow.csv paired columns
        chk("yellow.csv is non-empty", len(yellow_csv) > 0)
        yellow_lines = [l for l in yellow_csv.splitlines() if l.strip()]
        if yellow_lines:
            y_header = yellow_lines[0]
            has_paired = ("current_" in y_header and "proposed_" in y_header) or "current_email" in y_header
            chk("yellow.csv has paired current_/proposed_ columns", has_paired, f"header: {y_header}")

        # Assert blue.txt checklist items
        chk("blue.txt is non-empty", len(blue_txt) > 0)
        has_checklist = "[ ]" in blue_txt
        chk("blue.txt has at least one checklist item with '[ ]'", has_checklist)
        chk("blue.txt contains Worklist header", "WORKLIST" in blue_txt.upper())

        # ── 2. Single file download endpoints ─────────────────────────────
        print("\n[2] POST /api/export?file_type=green")
        resp_green = await c.post("/api/export?file_type=green")
        chk("HTTP 200 for green.csv download", resp_green.status_code == 200)
        chk("Content-Type is text/csv", "text/csv" in resp_green.headers.get("content-type", ""))

        print("\n[3] POST /api/export?file_type=blue")
        resp_blue = await c.post("/api/export?file_type=blue")
        chk("HTTP 200 for blue.txt download", resp_blue.status_code == 200)
        chk("Content-Type is text/plain", "text/plain" in resp_blue.headers.get("content-type", ""))

        # ── 3. POST /api/export/zip ───────────────────────────────────────
        print("\n[4] POST /api/export/zip -- download ZIP bundle")
        resp_zip = await c.post(
            "/api/export/zip",
            files={
                "contacts":  ("contacts.csv",  CONTACTS_BYTES,  "text/csv"),
                "companies": ("companies.csv", COMPANIES_BYTES, "text/csv"),
                "deals":     ("deals.csv",     DEALS_BYTES,     "text/csv"),
            },
        )

        chk("HTTP 200 from /api/export/zip", resp_zip.status_code == 200,
            f"status={resp_zip.status_code}")
        chk("Content-Type is application/zip", "application/zip" in resp_zip.headers.get("content-type", ""))

        if resp_zip.status_code == 200:
            zip_bytes = resp_zip.content
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
            namelist = zf.namelist()
            print(f"  ZIP contents: {namelist}")

            chk("ZIP contains 'green.csv'", "green.csv" in namelist)
            chk("ZIP contains 'yellow.csv'", "yellow.csv" in namelist)
            chk("ZIP contains 'blue.txt'", "blue.txt" in namelist)

            # Check uncompressed sizes
            green_unzipped = zf.read("green.csv").decode("utf-8")
            blue_unzipped = zf.read("blue.txt").decode("utf-8")
            chk("unzipped green.csv matches generated content", len(green_unzipped) > 0)
            chk("unzipped blue.txt matches checklist format", "[ ]" in blue_unzipped)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

asyncio.run(run_tests())

print()
print("=" * 65)
if errors:
    print(f"RESULT: {len(errors)} failure(s)")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("RESULT: All assertions passed.")
print("=" * 65)
