"""
checks_smoke_test.py
====================
Runs all 13 audit check functions against the bundled sample CSVs and
asserts that each check returns at least one finding.

The sample data was deliberately seeded with every finding type, so a
well-implemented check should never return zero findings here.

Usage:
    cd backend
    .\\venv\\Scripts\\python.exe checks_smoke_test.py
"""

import sys
from pathlib import Path
from typing import Callable

import pandas as pd

# Make the app package importable when running from the backend directory
sys.path.insert(0, str(Path(__file__).parent))

from app.config import build_config, FINDING
from app.models import AuditConfig, ParsedData
from app.parser import parse_upload
from app.checks import (
    check_duplicate_contacts,
    check_decayed_contacts,
    check_missing_contact_fields,
    check_lifecycle_inconsistencies,
    check_contact_no_company,
    check_duplicate_companies,
    check_company_no_contacts,
    check_stale_deals,
    check_deal_stage_stagnation,
    check_deals_past_close_date,
    check_missing_deal_fields,
    check_territory_mismatches,
    check_workload_imbalance,
    run_all_checks,
    ALL_CHECKS,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

SAMPLE = Path(__file__).parent.parent / "frontend" / "public" / "sample"

cfg_dict = build_config()
cfg = AuditConfig.from_dict(cfg_dict)

print(f"Loading sample CSVs from: {SAMPLE}\n")
data = parse_upload(
    str(SAMPLE / "contacts.csv"),
    str(SAMPLE / "companies.csv"),
    str(SAMPLE / "deals.csv"),
)
print(
    f"Parsed: {data.n_contacts} contacts, "
    f"{data.n_companies} companies, "
    f"{data.n_deals} deals\n"
)

# ---------------------------------------------------------------------------
# Individual check tests
# ---------------------------------------------------------------------------

CHECKS: list[tuple[str, Callable, dict]] = [
    # (display_name, check_function, extra_assertions)
    (
        "1. Duplicate contacts",
        check_duplicate_contacts,
        {
            # Exact email: 1001 + 1002 (john.smith@acmecorp.com)
            # Fuzzy name: 1003 + 1004 (Sarah Connor / Sara Connor, same domain)
            "min_findings": 4,
            "record_ids_must_include": {"1001", "1002", "1003", "1004"},
            "severity_must_include": {"High"},
        },
    ),
    (
        "2. Decayed contacts",
        check_decayed_contacts,
        {
            # Role-based: 1005 (info@), 1006 (support@)
            # Inactive >90 days: 1007 (246 days), 1008 (293 days)
            "min_findings": 4,
            "record_ids_must_include": {"1005", "1006", "1007", "1008"},
            "severity_must_include": {"Medium"},
        },
    ),
    (
        "3. Missing contact fields",
        check_missing_contact_fields,
        {
            # 1009: missing email, 1010: missing owner
            # 1011: missing lifecycle, 1012: missing country
            "min_findings": 4,
            "record_ids_must_include": {"1009", "1010", "1011", "1012"},
            "severities_must_include_all": {"High", "Medium", "Low"},
        },
    ),
    (
        "4. Lifecycle inconsistencies",
        check_lifecycle_inconsistencies,
        {
            # 1013: Lead + Closed Won D001
            # 1014: Customer + no deals
            "min_findings": 2,
            "record_ids_must_include": {"1013", "1014"},
            "severity_must_include": {"Medium"},
        },
    ),
    (
        "5. Contact no company",
        check_contact_no_company,
        {
            # 1015: no company_id or associated_company
            # 1016: same
            "min_findings": 2,
            "record_ids_must_include": {"1015", "1016"},
            "severity_must_include": {"Low"},
        },
    ),
    (
        "6. Duplicate companies",
        check_duplicate_companies,
        {
            # C016 and C017 duplicate C001 (same domain acmecorp.com)
            # C018 duplicates C002 (same domain techventures.io)
            "min_findings": 3,
            "record_ids_must_include": {"C016", "C017", "C018"},
            "severity_must_include": {"High"},
        },
    ),
    (
        "7. Company no contacts",
        check_company_no_contacts,
        {
            # C019: Ghost Company LLC (no contacts reference it)
            # C020: Phantom Enterprises (same)
            "min_findings": 2,
            "record_ids_must_include": {"C019", "C020"},
            "severity_must_include": {"Low"},
        },
    ),
    (
        "8. Stale deals",
        check_stale_deals,
        {
            # D002: last activity 2026-04-01 (>90 days ago)
            # D003: last activity 2026-03-15 (>90 days ago)
            "min_findings": 2,
            "record_ids_must_include": {"D002", "D003"},
            "severity_must_include": {"Medium"},
            "findings_must_have_key": "days_inactive",
        },
    ),
    (
        "9. Deal stage stagnation",
        check_deal_stage_stagnation,
        {
            # D004: 170+ days in Presentation Scheduled (limit 60)
            # D005: 156+ days in Qualified to Buy (limit 45)
            "min_findings": 2,
            "record_ids_must_include": {"D004", "D005"},
            "severity_must_include": {"Medium"},
            "findings_must_have_key": "days_in_stage",
        },
    ),
    (
        "10. Deals past close date",
        check_deals_past_close_date,
        {
            # D006: close 2026-06-01, D007: 2026-05-15, D008: 2026-07-01
            "min_findings": 3,
            "record_ids_must_include": {"D006", "D007", "D008"},
            "severity_must_include": {"High"},
            "findings_must_have_key": "days_overdue",
        },
    ),
    (
        "11. Missing deal fields",
        check_missing_deal_fields,
        {
            # D009: no amount, D010: no owner, D011: no close date, D012: no contact
            "min_findings": 4,
            "record_ids_must_include": {"D009", "D010", "D011", "D012"},
            "severity_must_include": {"High"},
        },
    ),
    (
        "12. Territory mismatches",
        check_territory_mismatches,
        {
            # 1017: Germany / Alice (NA), 1018: Japan / Bob (EMEA)
            # 1019: Mexico / Carol (APAC)
            "min_findings": 3,
            "record_ids_must_include": {"1017", "1018", "1019"},
            "severity_must_include": {"Medium"},
        },
    ),
    (
        "13. Workload imbalance",
        check_workload_imbalance,
        {
            # Alice Johnson owns ~78% of contacts (>50% threshold)
            "min_findings": 1,
            "finding_detail_must_contain": "Alice Johnson",
            "severity_must_include": {"Low"},
        },
    ),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

errors: list[str] = []
total_checks  = 0
passed_checks = 0


def chk(label: str, condition: bool, hint: str = "") -> bool:
    global errors
    if condition:
        return True
    msg = f"    FAIL: {label}" + (f" -- {hint}" if hint else "")
    print(msg)
    errors.append(f"{label}: {hint}")
    return False


print("=" * 60)
print("CHECKS SMOKE TEST")
print("=" * 60)

for display_name, fn, assertions in CHECKS:
    total_checks += 1
    print(f"\n{display_name}")

    findings = fn(data, cfg)
    record_ids = {str(f["record_id"]) for f in findings}
    severities  = {f["severity"] for f in findings}

    check_passed = True

    # Always: must return at least one finding
    if not chk("returns at least 1 finding", len(findings) >= 1, f"got {len(findings)}"):
        check_passed = False

    # Min findings count
    if "min_findings" in assertions:
        mn = assertions["min_findings"]
        if not chk(f"returns at least {mn} findings", len(findings) >= mn, f"got {len(findings)}"):
            check_passed = False

    # Specific record IDs must be present
    if "record_ids_must_include" in assertions:
        expected = assertions["record_ids_must_include"]
        missing  = expected - record_ids
        if not chk("expected record IDs present", not missing, f"missing: {missing}"):
            check_passed = False

    # Severity must include specific values
    if "severity_must_include" in assertions:
        for sev in assertions["severity_must_include"]:
            if not chk(f"severity '{sev}' present", sev in severities):
                check_passed = False

    # All specified severities must be present across the findings
    if "severities_must_include_all" in assertions:
        for sev in assertions["severities_must_include_all"]:
            if not chk(f"severity '{sev}' present", sev in severities):
                check_passed = False

    # A specific key must exist on all findings
    if "findings_must_have_key" in assertions:
        key = assertions["findings_must_have_key"]
        bad = [f["record_id"] for f in findings if key not in f]
        if not chk(f"all findings have '{key}' key", not bad, f"missing on: {bad}"):
            check_passed = False

    # A string must appear in at least one finding's detail
    if "finding_detail_must_contain" in assertions:
        needle = assertions["finding_detail_must_contain"]
        found  = any(needle in f.get("detail", "") for f in findings)
        if not chk(f"detail contains '{needle}'", found):
            check_passed = False

    # Summary for this check
    status = "PASS" if check_passed else "FAIL"
    preview = sorted(record_ids)[:6]
    ellipsis = "..." if len(record_ids) > 6 else ""
    print(f"  -> {status}  ({len(findings)} finding(s))  records: {preview}{ellipsis}")

    if check_passed:
        passed_checks += 1


# ---------------------------------------------------------------------------
# run_all_checks() integration test
# ---------------------------------------------------------------------------

print(f"\n{'=' * 60}")
print("Integration: run_all_checks()")
all_findings = run_all_checks(data, cfg)
keys_present = {f["finding_key"] for f in all_findings}
all_keys     = set(FINDING.values())
missing_keys = all_keys - keys_present

int_ok = chk("run_all_checks covers all 13 finding keys", not missing_keys,
    f"missing keys: {missing_keys}")
print(f"  Total findings produced: {len(all_findings)}")
print(f"  Finding types covered:   {len(keys_present)} / {len(all_keys)}")

by_key = {}
for f in all_findings:
    by_key.setdefault(f["finding_key"], 0)
    by_key[f["finding_key"]] += 1

print("\n  Breakdown by finding type:")
for key in sorted(by_key):
    print(f"    {key:<35} {by_key[key]:>3} finding(s)")


# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------

print(f"\n{'=' * 60}")
print(f"RESULT: {passed_checks} / {total_checks} checks passed")

if errors:
    print(f"\n{len(errors)} assertion failure(s):")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("All assertions passed.")
    sys.exit(0)
