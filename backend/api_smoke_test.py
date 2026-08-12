"""
api_smoke_test.py
=================
Tests POST /api/audit against the full live FastAPI application using
httpx's ASGITransport (in-process, no port required, no race conditions).

Tests:
  [0]  GET /api/health
  [1]  POST /api/audit — upload 3 sample CSVs
  [2]  POST /api/audit — config override (doubling hourly rate doubles cost)
  [3]  POST /api/audit/sample — bundled sample data shortcut
  [4]  POST /api/audit — contacts-only upload (no companies/deals)
  [5]  POST /api/audit — missing contacts file (expect 4xx)

Asserts (from user spec):
  HTTP 200, 4 top-level keys, punch_list has 13 rows, score.overall 0-100.

Usage:
    cd backend
    .\\venv\\Scripts\\python.exe api_smoke_test.py
"""

import asyncio
import json
import sys
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

PUNCH_REQUIRED = [
    "finding_key", "label", "record_type", "severity",
    "affected_count", "affected_record_ids",
    "rep_hours", "direct_cost", "at_risk_pipeline",
    "score_impact", "total_value",
]
SCORE_REQUIRED  = [
    "overall", "contacts", "companies", "deals",
    "overall_color", "contacts_color", "companies_color", "deals_color",
]
COSTS_REQUIRED  = ["direct_cost", "at_risk_pipeline", "total_rep_hours"]
META_REQUIRED   = ["record_counts", "source", "timestamp", "filenames"]

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
    print("API SMOKE TEST -- POST /api/audit")
    print("=" * 65)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:

        # ── [0] Health ────────────────────────────────────────────────────
        print("\n[0] Health check")
        r = await c.get("/api/health")
        chk("GET /api/health returns 200", r.status_code == 200,
            f"status={r.status_code}")

        # ── [1] Full upload ───────────────────────────────────────────────
        print("\n[1] POST /api/audit -- upload 3 sample CSVs")
        resp = await c.post(
            "/api/audit",
            files={
                "contacts":  ("contacts.csv",  CONTACTS_BYTES,  "text/csv"),
                "companies": ("companies.csv", COMPANIES_BYTES, "text/csv"),
                "deals":     ("deals.csv",     DEALS_BYTES,     "text/csv"),
            },
        )

        chk("HTTP 200", resp.status_code == 200,
            f"status={resp.status_code}  body={resp.text[:300]}")

        if resp.status_code != 200:
            print("\nCannot continue -- server error.")
            return

        body = resp.json()

        # Print summary
        print()
        sc = body.get("score", {})
        co = body.get("costs", {})
        md = body.get("metadata", {})
        rc = md.get("record_counts", {})
        print(f"  Top-level keys : {list(body.keys())}")
        print(f"  Score          : overall={sc.get('overall')} ({sc.get('overall_color')}), "
              f"contacts={sc.get('contacts')}, companies={sc.get('companies')}, "
              f"deals={sc.get('deals')}")
        print(f"  Costs          : direct=${co.get('direct_cost'):,.2f}, "
              f"at_risk=${co.get('at_risk_pipeline'):,.2f}, "
              f"hours={co.get('total_rep_hours'):.2f}h")
        print(f"  Punch list     : {len(body.get('punch_list', []))} rows")
        print(f"  Record counts  : contacts={rc.get('contacts')}, "
              f"companies={rc.get('companies')}, deals={rc.get('deals')}")
        print(f"  Source/ts      : {md.get('source')}  {md.get('timestamp')}")
        print()

        # Top-level structure
        for key in ("score", "costs", "punch_list", "metadata"):
            chk(f"response has '{key}' key", key in body)

        # score
        chk("score.overall in [0, 100]",
            0 <= sc.get("overall", -1) <= 100, str(sc.get("overall")))

        missing_sc = [k for k in SCORE_REQUIRED if k not in sc]
        chk("score has all 8 keys", not missing_sc, str(missing_sc))

        valid_colors = {"green", "amber", "red"}
        bad_colors = [
            f"{k}={sc[k]}"
            for k in ("overall_color", "contacts_color", "companies_color", "deals_color")
            if sc.get(k) not in valid_colors
        ]
        chk("all color values valid", not bad_colors, str(bad_colors))

        # costs
        missing_co = [k for k in COSTS_REQUIRED if k not in co]
        chk("costs has all required keys", not missing_co, str(missing_co))

        neg_co = [f"{k}={co[k]}" for k in COSTS_REQUIRED if k in co and co[k] < 0]
        chk("all cost values >= 0", not neg_co, str(neg_co))

        chk("costs.direct_cost > 0",
            co.get("direct_cost", 0) > 0, str(co.get("direct_cost")))

        chk("costs.at_risk_pipeline > 0",
            co.get("at_risk_pipeline", 0) > 0, str(co.get("at_risk_pipeline")))

        # punch_list
        punch = body.get("punch_list", [])
        chk("punch_list has 13 rows", len(punch) == 13, f"got {len(punch)}")

        rows_missing = []
        for row in punch:
            missing = [k for k in PUNCH_REQUIRED if k not in row]
            if missing:
                rows_missing.append(f"{row.get('finding_key','?')}: {missing}")
        chk("all punch_list rows have required keys", not rows_missing,
            "; ".join(rows_missing))

        tvs = [row.get("total_value", 0) for row in punch]
        sort_ok = all(tvs[i] >= tvs[i+1] for i in range(len(tvs)-1))
        chk("punch_list sorted descending by total_value", sort_ok,
            str([round(v,1) for v in tvs]))

        # metadata
        missing_md = [k for k in META_REQUIRED if k not in md]
        chk("metadata has all required keys", not missing_md, str(missing_md))

        chk("record_counts.contacts == 50",  rc.get("contacts")  == 50, str(rc.get("contacts")))
        chk("record_counts.companies == 20", rc.get("companies") == 20, str(rc.get("companies")))
        chk("record_counts.deals == 20",     rc.get("deals")     == 20, str(rc.get("deals")))

        chk("metadata.source == 'upload'",
            md.get("source") == "upload", md.get("source"))

        # ── [2] Config override ───────────────────────────────────────────
        print("\n[2] POST /api/audit -- config override (rep_hourly_rate=150)")
        resp2 = await c.post(
            "/api/audit",
            files={
                "contacts":  ("contacts.csv",  CONTACTS_BYTES,  "text/csv"),
                "companies": ("companies.csv", COMPANIES_BYTES, "text/csv"),
                "deals":     ("deals.csv",     DEALS_BYTES,     "text/csv"),
            },
            data={"config": json.dumps({"cost": {"rep_hourly_rate": 150}})},
        )
        chk("HTTP 200 with config override", resp2.status_code == 200,
            f"status={resp2.status_code}")

        if resp2.status_code == 200:
            body2 = resp2.json()
            orig   = co.get("direct_cost", 0)
            double = body2.get("costs", {}).get("direct_cost", 0)
            chk("doubling hourly rate doubles direct_cost",
                abs(double - orig * 2) < 0.02,
                f"expected ${orig*2:.2f}, got ${double:.2f}")

        # ── [3] /api/audit/sample ─────────────────────────────────────────
        print("\n[3] POST /api/audit/sample -- bundled data shortcut")
        resp3 = await c.post("/api/audit/sample")
        chk("HTTP 200 from /api/audit/sample",
            resp3.status_code == 200, f"status={resp3.status_code}")

        if resp3.status_code == 200:
            body3 = resp3.json()
            chk("sample: has 'score' key", "score" in body3)
            chk("sample: punch_list has 13 rows",
                len(body3.get("punch_list", [])) == 13,
                str(len(body3.get("punch_list", []))))
            chk("sample: metadata.source == 'sample'",
                body3.get("metadata", {}).get("source") == "sample",
                body3.get("metadata", {}).get("source"))
            chk("upload and sample return same overall score",
                sc.get("overall") == body3.get("score", {}).get("overall"),
                f"upload={sc.get('overall')}, sample={body3.get('score',{}).get('overall')}")

        # ── [4] Contacts-only upload ──────────────────────────────────────
        print("\n[4] POST /api/audit -- contacts-only (no companies/deals)")
        resp4 = await c.post(
            "/api/audit",
            files={"contacts": ("contacts.csv", CONTACTS_BYTES, "text/csv")},
        )
        chk("HTTP 200 with contacts-only upload",
            resp4.status_code == 200, f"status={resp4.status_code}")

        if resp4.status_code == 200:
            body4 = resp4.json()
            rc4 = body4.get("metadata", {}).get("record_counts", {})
            chk("contacts-only: companies == 0",
                rc4.get("companies") == 0, str(rc4.get("companies")))
            chk("contacts-only: deals == 0",
                rc4.get("deals") == 0, str(rc4.get("deals")))

        # ── [5] Missing contacts → 4xx ────────────────────────────────────
        print("\n[5] POST /api/audit -- missing contacts file (expect 4xx)")
        resp5 = await c.post(
            "/api/audit",
            files={"companies": ("companies.csv", COMPANIES_BYTES, "text/csv")},
        )
        chk("missing contacts -> 4xx",
            resp5.status_code in (400, 422), f"got {resp5.status_code}")


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
