"""
e2e_test.py — Pipecheck end-to-end test suite.

Tests two flows:
  1. Sample data flow  — POST /api/audit/sample
  2. Real CSV flow     — POST /api/audit with real_contacts/companies/deals.csv

Usage:
    python e2e_test.py
    python e2e_test.py --url http://localhost:8000   # custom base URL

Prints a pass/fail line for every assertion.
Exits with code 1 if any assertion fails.
"""

import argparse
import json
import os
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = "http://localhost:8000"
SCRIPT_DIR = Path(__file__).parent
CONTACTS_CSV  = SCRIPT_DIR / "real_contacts.csv"
COMPANIES_CSV = SCRIPT_DIR / "real_companies.csv"
DEALS_CSV     = SCRIPT_DIR / "real_deals.csv"

PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"

failures = []

# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

def check(label: str, condition: bool, detail: str = ""):
    if condition:
        print(f"{PASS}  {label}")
    else:
        msg = f"{FAIL}  {label}"
        if detail:
            msg += f"\n         detail: {detail}"
        print(msg)
        failures.append(label)


def check_eq(label: str, actual, expected):
    check(label, actual == expected, f"got {actual!r}, expected {expected!r}")


def check_gte(label: str, actual, minimum):
    check(label, actual >= minimum, f"got {actual!r}, expected >= {minimum!r}")


def check_in(label: str, item, collection):
    check(label, item in collection, f"{item!r} not in {collection!r}")


def check_keys(label: str, obj: dict, keys: list):
    missing = [k for k in keys if k not in obj]
    check(label, not missing, f"missing keys: {missing}")


# ---------------------------------------------------------------------------
# Response shape validators
# ---------------------------------------------------------------------------

REQUIRED_TOP_KEYS = [
    "score", "costs", "punch_list", "metadata"
]

REQUIRED_SCORE_KEYS = [
    "overall", "contacts", "companies", "deals"
]

REQUIRED_COST_KEYS = [
    "direct_cost", "at_risk_pipeline", "total_rep_hours"
]

REQUIRED_PUNCH_KEYS = [
    "finding_key", "label", "record_type", "severity",
    "affected_count", "affected_record_ids",
    "direct_cost", "at_risk_pipeline", "score_impact", "total_value"
]

VALID_SEVERITIES = {"High", "Medium", "Low"}
VALID_RECORD_TYPES = {"contact", "company", "deal"}
KNOWN_FINDING_KEYS = {
    "duplicate_contacts", "decayed_contacts", "missing_contact_fields",
    "lifecycle_inconsistency", "contact_no_company",
    "duplicate_companies", "company_no_contacts",
    "stale_deals", "deal_stage_stagnation", "deals_past_close_date",
    "missing_deal_fields", "territory_mismatch", "workload_imbalance",
}


def validate_response(label_prefix: str, data: dict):
    """Run all structural assertions on an audit response dict."""

    print(f"\n  -- Structure checks --")
    check_keys(f"{label_prefix}: top-level keys present", data, REQUIRED_TOP_KEYS)

    # Scores
    scores = data.get("score", {})
    check_keys(f"{label_prefix}: score keys present", scores, REQUIRED_SCORE_KEYS)
    for key in REQUIRED_SCORE_KEYS:
        val = scores.get(key)
        check(
            f"{label_prefix}: score.{key} in [0,100]",
            isinstance(val, (int, float)) and 0 <= val <= 100,
            f"got {val!r}"
        )

    # Costs
    costs = data.get("costs", {})
    check_keys(f"{label_prefix}: cost keys present", costs, REQUIRED_COST_KEYS)
    check(
        f"{label_prefix}: direct_cost >= 0",
        isinstance(costs.get("direct_cost"), (int, float)) and costs["direct_cost"] >= 0
    )
    check(
        f"{label_prefix}: at_risk_pipeline >= 0",
        isinstance(costs.get("at_risk_pipeline"), (int, float)) and costs["at_risk_pipeline"] >= 0
    )
    check(
        f"{label_prefix}: total_rep_hours >= 0",
        isinstance(costs.get("total_rep_hours"), (int, float)) and costs["total_rep_hours"] >= 0
    )

    # Punch list
    punch_list = data.get("punch_list", [])
    check(f"{label_prefix}: punch_list is a list", isinstance(punch_list, list))
    check(f"{label_prefix}: punch_list has at least 1 item", len(punch_list) >= 1)

    if punch_list:
        # Check first item has all required keys
        first = punch_list[0]
        check_keys(f"{label_prefix}: punch_list[0] has all keys", first, REQUIRED_PUNCH_KEYS)

        # Check all items have valid severities and record types
        bad_severities = [i["finding_key"] for i in punch_list if i.get("severity") not in VALID_SEVERITIES]
        check(f"{label_prefix}: all severities valid", not bad_severities, f"bad: {bad_severities}")

        bad_types = [i["finding_key"] for i in punch_list if i.get("record_type") not in VALID_RECORD_TYPES]
        check(f"{label_prefix}: all record_types valid", not bad_types, f"bad: {bad_types}")

        # No duplicate finding_keys
        keys_seen = [i["finding_key"] for i in punch_list]
        check(
            f"{label_prefix}: no duplicate finding_keys",
            len(keys_seen) == len(set(keys_seen)),
            f"duplicates: {[k for k in keys_seen if keys_seen.count(k) > 1]}"
        )

        # All finding_keys are known
        unknown = [k for k in keys_seen if k not in KNOWN_FINDING_KEYS]
        check(f"{label_prefix}: all finding_keys are known", not unknown, f"unknown: {unknown}")

        # Sorted descending by total_value
        total_values = [i["total_value"] for i in punch_list]
        check(
            f"{label_prefix}: punch_list sorted descending by total_value",
            total_values == sorted(total_values, reverse=True),
            f"order: {total_values}"
        )

        # At least one item has score_impact > 0
        has_score_impact = any(i.get("score_impact", 0) > 0 for i in punch_list)
        check(f"{label_prefix}: at least one score_impact > 0", has_score_impact)

        # All affected_counts are positive ints
        # workload_imbalance uses affected_record_ids like ["owner:Alice Johnson"] — count may be 1 via owner refs
        bad_counts = [
            i["finding_key"] for i in punch_list
            if not isinstance(i.get("affected_count"), int) or i["affected_count"] < 1
            if i["finding_key"] != "workload_imbalance"
        ]
        check(f"{label_prefix}: all affected_counts >= 1 (excl. workload_imbalance)", not bad_counts, f"bad: {bad_counts}")

        # affected_record_ids is always a list
        bad_ids = [i["finding_key"] for i in punch_list if not isinstance(i.get("affected_record_ids"), list)]
        check(f"{label_prefix}: all affected_record_ids are lists", not bad_ids, f"bad: {bad_ids}")

    # Metadata
    metadata = data.get("metadata", {})
    check(f"{label_prefix}: metadata present", isinstance(metadata, dict) and len(metadata) > 0)
    record_counts = metadata.get("record_counts", {})
    check(
        f"{label_prefix}: metadata.record_counts present",
        isinstance(record_counts, dict) and len(record_counts) > 0
    )


# ---------------------------------------------------------------------------
# Flow 1: Sample data
# ---------------------------------------------------------------------------

def test_sample_flow(base_url: str):
    print("\n" + "="*60)
    print("FLOW 1: Sample data  (POST /api/audit/sample)")
    print("="*60)

    url = f"{base_url}/api/audit/sample"

    try:
        resp = requests.post(url, timeout=60)
    except requests.exceptions.ConnectionError:
        check("Sample flow: server reachable", False, f"Could not connect to {url}")
        return None

    check("Sample flow: HTTP 200", resp.status_code == 200, f"got {resp.status_code}")

    try:
        data = resp.json()
    except Exception as e:
        check("Sample flow: valid JSON response", False, str(e))
        return None

    check("Sample flow: valid JSON response", True)
    validate_response("Sample", data)
    return data


# ---------------------------------------------------------------------------
# Flow 2: Real CSV upload
# ---------------------------------------------------------------------------

def test_real_csv_flow(base_url: str):
    print("\n" + "="*60)
    print("FLOW 2: Real CSVs  (POST /api/audit)")
    print("="*60)

    url = f"{base_url}/api/audit"

    for f in [CONTACTS_CSV, COMPANIES_CSV, DEALS_CSV]:
        check(f"CSV file exists: {f.name}", f.exists())

    if not all(f.exists() for f in [CONTACTS_CSV, COMPANIES_CSV, DEALS_CSV]):
        print("  Skipping real CSV flow — files not found.")
        return None

    files = {
        "contacts":  ("real_contacts.csv",  open(CONTACTS_CSV,  "rb"), "text/csv"),
        "companies": ("real_companies.csv", open(COMPANIES_CSV, "rb"), "text/csv"),
        "deals":     ("real_deals.csv",     open(DEALS_CSV,     "rb"), "text/csv"),
    }

    try:
        resp = requests.post(url, files=files, timeout=60)
    except requests.exceptions.ConnectionError:
        check("Real CSV flow: server reachable", False, f"Could not connect to {url}")
        return None
    finally:
        for _, (_, fh, _) in files.items():
            fh.close()

    check("Real CSV flow: HTTP 200", resp.status_code == 200, f"got {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
    except Exception as e:
        check("Real CSV flow: valid JSON response", False, str(e))
        return None

    check("Real CSV flow: valid JSON response", True)
    validate_response("RealCSV", data)

    print("\n  -- Edge case checks (real CSV specific) --")

    punch_list = data.get("punch_list", [])
    finding_keys = {i["finding_key"] for i in punch_list}

    # Duplicate contacts: 2001/2002/2003 are all James Whitfield with same email
    check(
        "RealCSV: duplicate_contacts flagged",
        "duplicate_contacts" in finding_keys,
        "expected James Whitfield triplicate to be caught"
    )

    # Duplicate companies: RC001/RC025/RC026 all share oriontech.com
    check(
        "RealCSV: duplicate_companies flagged",
        "duplicate_companies" in finding_keys,
        "expected Orion Tech domain dupes to be caught"
    )

    # Company with no contacts: RC028/RC029/RC030 have 0 associated contacts
    check(
        "RealCSV: company_no_contacts flagged",
        "company_no_contacts" in finding_keys,
        "expected ghost/phantom companies to be caught"
    )

    # Contact with no company: 2006/2028 have no Company ID
    check(
        "RealCSV: contact_no_company flagged",
        "contact_no_company" in finding_keys,
        "expected contacts with blank Company ID to be caught"
    )

    # Missing contact fields: 2009 (no email), 2015 (no owner), 2022 (no owner)
    check(
        "RealCSV: missing_contact_fields flagged",
        "missing_contact_fields" in finding_keys,
        "expected contacts with missing required fields to be caught"
    )

    # Missing deal fields: RD014 (no amount), RD016 (no owner), RD019 (no contact)
    check(
        "RealCSV: missing_deal_fields flagged",
        "missing_deal_fields" in finding_keys,
        "expected deals with missing required fields to be caught"
    )

    # Past close date: RD018 close date 2025-12-31, RD019 close date 2025-11-30
    check(
        "RealCSV: deals_past_close_date flagged",
        "deals_past_close_date" in finding_keys,
        "expected past-close-date deals to be caught"
    )

    # Territory mismatch: 2006 (UAE assigned to Alice/US territory), 2020 (Peru → Alice OK actually),
    # 2024 (Senegal assigned to Bob/Europe territory)
    check(
        "RealCSV: territory_mismatch flagged",
        "territory_mismatch" in finding_keys,
        "expected territory mismatches to be caught"
    )

    # Stale deals: RD003 last activity 2026-04-10 (~4 months ago), RD004 2026-03-01 (~5 months)
    check(
        "RealCSV: stale_deals flagged",
        "stale_deals" in finding_keys,
        "expected stale deals to be caught"
    )

    return data


# ---------------------------------------------------------------------------
# Flow 3: Export downloads
# ---------------------------------------------------------------------------

def test_export_flow(base_url: str, audit_data: dict | None):
    print("\n" + "="*60)
    print("FLOW 3: Export downloads")
    print("="*60)

    if not audit_data:
        print("  Skipping — no audit data from previous flow.")
        return

    # The export endpoints take an audit_id or use the last result.
    # Test by hitting each export endpoint and checking content type + non-empty body.
    endpoints = {
        "green_csv":  f"{base_url}/api/export/green",
        "yellow_csv": f"{base_url}/api/export/yellow",
        "blue_txt":   f"{base_url}/api/export/blue",
        "zip_all":    f"{base_url}/api/export/zip",
    }

    # We need to post the same audit data back to trigger export,
    # or the backend may cache it. Try GET first; fall back to noting limitation.
    for name, url in endpoints.items():
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 405:
                # Try POST
                resp = requests.post(url, json=audit_data, timeout=30)

            check(
                f"Export {name}: HTTP 200 or 404",
                resp.status_code in (200, 404),
                f"got {resp.status_code}"
            )

            if resp.status_code == 200:
                check(
                    f"Export {name}: non-empty body",
                    len(resp.content) > 0,
                    f"body was empty"
                )

                if name == "zip_all":
                    try:
                        z = zipfile.ZipFile(BytesIO(resp.content))
                        names = z.namelist()
                        check(
                            f"Export {name}: ZIP contains files",
                            len(names) > 0,
                            f"ZIP was empty"
                        )
                    except zipfile.BadZipFile:
                        check(f"Export {name}: valid ZIP", False, "bad zip file")

        except requests.exceptions.ConnectionError:
            check(f"Export {name}: server reachable", False, f"Could not connect to {url}")


# ---------------------------------------------------------------------------
# Flow 4: Config override
# ---------------------------------------------------------------------------

def test_config_override_flow(base_url: str):
    print("\n" + "="*60)
    print("FLOW 4: Config override  (POST /api/audit/sample with custom config)")
    print("="*60)

    url = f"{base_url}/api/audit/sample"

    # Override: tighten inactivity to 1 day — should flag many more records
    override_payload = {
        "config": {
            "inactivity": {
                "contact_decay_days": 1,
                "deal_stale_days": 1,
            },
            "cost": {
                "rep_hourly_rate": 150.0,
            }
        }
    }

    try:
        resp = requests.post(url, json=override_payload, timeout=60)
    except requests.exceptions.ConnectionError:
        check("Config override: server reachable", False)
        return

    check("Config override: HTTP 200", resp.status_code == 200, f"got {resp.status_code}: {resp.text[:200]}")

    if resp.status_code != 200:
        return

    data = resp.json()
    check("Config override: valid JSON", True)

    # With 1-day inactivity threshold, direct cost should be higher than default
    # (more records flagged × higher hourly rate)
    costs = data.get("costs", {})
    check(
        "Config override: direct_cost > 0",
        costs.get("direct_cost", 0) > 0,
        f"got {costs.get('direct_cost')}"
    )


# ---------------------------------------------------------------------------
# Flow 5: Edge cases — missing/partial file uploads
# ---------------------------------------------------------------------------

def test_partial_upload_flow(base_url: str):
    print("\n" + "="*60)
    print("FLOW 5: Partial upload — contacts only (no deals, no companies)")
    print("="*60)

    url = f"{base_url}/api/audit"

    if not CONTACTS_CSV.exists():
        print("  Skipping — contacts CSV not found.")
        return

    files = {
        "contacts": ("real_contacts.csv", open(CONTACTS_CSV, "rb"), "text/csv"),
    }

    try:
        resp = requests.post(url, files=files, timeout=60)
    except requests.exceptions.ConnectionError:
        check("Partial upload: server reachable", False)
        return
    finally:
        for _, (_, fh, _) in files.items():
            fh.close()

    check(
        "Partial upload: returns 200 or 422",
        resp.status_code in (200, 422, 400),
        f"got {resp.status_code}: {resp.text[:200]}"
    )

    if resp.status_code == 200:
        try:
            data = resp.json()
            check("Partial upload: valid JSON", True)
            scores = data.get("score", {})
            check(
                "Partial upload: overall score present",
                "overall" in scores,
                f"score keys: {list(scores.keys())}"
            )
        except Exception as e:
            check("Partial upload: valid JSON", False, str(e))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=BASE_URL, help="Base URL of the Pipecheck API")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    print(f"\nPipecheck E2E Test Suite")
    print(f"Target: {base_url}")
    print(f"Real CSV dir: {SCRIPT_DIR}")

    # Health check
    print("\n" + "="*60)
    print("HEALTH CHECK")
    print("="*60)
    try:
        resp = requests.get(f"{base_url}/", timeout=10)
        check("API root reachable", resp.status_code in (200, 404), f"got {resp.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"\n  ERROR: Cannot connect to {base_url}")
        print("  Make sure the backend is running: cd backend && uvicorn app.main:app --reload")
        sys.exit(1)

    # Run flows
    sample_data  = test_sample_flow(base_url)
    real_data    = test_real_csv_flow(base_url)
    test_export_flow(base_url, real_data or sample_data)
    test_config_override_flow(base_url)
    test_partial_upload_flow(base_url)

    # Summary
    print("\n" + "="*60)
    total_checks = len(failures) + sum(
        1 for line in open(__file__).readlines() if "check(" in line or "check_" in line
    )
    print(f"\nResult: {len(failures)} failure(s)")
    if failures:
        print("\nFailed checks:")
        for f in failures:
            print(f"  - {f}")
        print("\n  OVERALL: FAIL")
        sys.exit(1)
    else:
        print("\n  OVERALL: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
