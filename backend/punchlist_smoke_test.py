"""
punchlist_smoke_test.py
=======================
Full pipeline smoke test:  parse -> checks -> score -> costs -> punchlist

Asserts:
  1.  Punch list has exactly 13 rows (one per finding_key in the FINDING registry).
  2.  No finding_key appears twice.
  3.  Each row has all required keys.
  4.  First row has the highest total_value (sorted descending).
  5.  total_value values are non-negative.
  6.  score_impact >= 0 for all rows.
  7.  score_impact > 0 for at least one row (sample has real record-level findings).
  8.  affected_count == len(affected_record_ids) for every row.
  9.  Each row's total_value == direct_cost + at_risk_pipeline + score_impact * 1000.
 10.  Labels are non-empty strings.
 11.  record_type is one of "contact", "company", "deal" for every row.
 12.  severity is one of "High", "Medium", "Low" for every row.

Prints the full ranked punch list as a table, then a final PASS / FAIL line.

Usage:
    cd backend
    .\\venv\\Scripts\\python.exe punchlist_smoke_test.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.config import build_config, FINDING
from app.models import AuditConfig
from app.parser import parse_upload
from app.checks import run_all_checks
from app.scorer import score
from app.costs import calculate_costs
from app.punchlist import build_punch_list, SCORE_WEIGHT_PER_POINT

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE = Path(__file__).parent.parent / "frontend" / "public" / "sample"

cfg      = AuditConfig.from_dict(build_config())
data     = parse_upload(
    str(SAMPLE / "contacts.csv"),
    str(SAMPLE / "companies.csv"),
    str(SAMPLE / "deals.csv"),
)
findings     = run_all_checks(data, cfg)
score_result = score(findings, data, cfg)
cost_result  = calculate_costs(findings, data, cfg)

print(f"Loaded : {data.n_contacts} contacts, {data.n_companies} companies, {data.n_deals} deals")
print(f"Findings: {len(findings)} total")
print(f"Scores  : overall={score_result.overall}, contacts={score_result.contacts}, "
      f"companies={score_result.companies}, deals={score_result.deals}")
print()

punch = build_punch_list(findings, score_result, cost_result, data, cfg)

# ---------------------------------------------------------------------------
# Print the ranked punch list as a readable table
# ---------------------------------------------------------------------------

REQUIRED_KEYS = [
    "finding_key", "label", "record_type", "severity",
    "affected_count", "affected_record_ids",
    "rep_hours", "direct_cost", "at_risk_pipeline",
    "score_impact", "total_value",
]

COL_W = {
    "rank":      4,
    "label":     36,
    "sev":       8,
    "cnt":       5,
    "hrs":       6,
    "cost":      12,
    "atrisk":    14,
    "impact":    8,
    "total":     14,
}

header = (
    f"{'#':>{COL_W['rank']}}  "
    f"{'Finding':<{COL_W['label']}}  "
    f"{'Sev':<{COL_W['sev']}}  "
    f"{'Recs':>{COL_W['cnt']}}  "
    f"{'Hrs':>{COL_W['hrs']}}  "
    f"{'Direct $':>{COL_W['cost']}}  "
    f"{'At-Risk $':>{COL_W['atrisk']}}  "
    f"{'Pts':>{COL_W['impact']}}  "
    f"{'Total Value':>{COL_W['total']}}"
)
sep = "-" * len(header)

print(sep)
print("PUNCH LIST — ranked by total value (highest first)")
print(sep)
print(header)
print(sep)

for i, item in enumerate(punch, 1):
    d = item.to_dict()
    label_trunc = d["label"][:COL_W["label"]]
    print(
        f"{i:>{COL_W['rank']}}  "
        f"{label_trunc:<{COL_W['label']}}  "
        f"{d['severity']:<{COL_W['sev']}}  "
        f"{d['affected_count']:>{COL_W['cnt']}}  "
        f"{d['rep_hours']:>{COL_W['hrs']}.2f}  "
        f"${d['direct_cost']:>{COL_W['cost'] - 1},.2f}  "
        f"${d['at_risk_pipeline']:>{COL_W['atrisk'] - 1},.2f}  "
        f"{d['score_impact']:>{COL_W['impact']}.3f}  "
        f"${d['total_value']:>{COL_W['total'] - 1},.2f}"
    )

print(sep)
print()

# ---------------------------------------------------------------------------
# Assertions
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


print("Assertions")
print("-" * 50)

# 1. Exactly 13 rows
chk("13 rows in punch list",
    len(punch) == 13,
    f"got {len(punch)}")

# 2. No duplicate finding_key
seen_keys: set[str] = set()
dupes: list[str] = []
for item in punch:
    if item.finding_key in seen_keys:
        dupes.append(item.finding_key)
    seen_keys.add(item.finding_key)
chk("no finding_key appears twice", not dupes, f"dupes: {dupes}")

# 3. Every finding_key from the registry is present
missing_keys = set(FINDING.values()) - {item.finding_key for item in punch}
chk("all 13 registry keys present",
    not missing_keys,
    f"missing: {missing_keys}")

# 4. Each row has all required keys (via to_dict())
rows_missing_keys: list[str] = []
for item in punch:
    d = item.to_dict()
    missing = [k for k in REQUIRED_KEYS if k not in d]
    if missing:
        rows_missing_keys.append(f"{item.finding_key}: {missing}")
chk("all rows have required keys", not rows_missing_keys,
    "; ".join(rows_missing_keys))

# 5. First row has the highest total_value (list is sorted descending)
if len(punch) > 1:
    chk("first row has highest total_value",
        punch[0].total_value >= punch[1].total_value,
        f"{punch[0].total_value:.2f} vs {punch[1].total_value:.2f}")

# Also check full sort order
sort_violations = [
    i for i in range(len(punch) - 1)
    if punch[i].total_value < punch[i + 1].total_value
]
chk("punch list sorted descending by total_value",
    not sort_violations,
    f"violations at positions: {sort_violations}")

# 6. total_value values are non-negative
negatives = [item.finding_key for item in punch if item.total_value < 0]
chk("all total_value >= 0", not negatives, f"negatives: {negatives}")

# 7. score_impact >= 0 for all rows
neg_impact = [item.finding_key for item in punch if item.score_impact < 0]
chk("all score_impact >= 0", not neg_impact, f"negatives: {neg_impact}")

# 8. score_impact > 0 for at least one row
chk("at least one row has score_impact > 0",
    any(item.score_impact > 0 for item in punch),
    "all score_impact == 0")

# 9. affected_count == len(affected_record_ids)
count_mismatches = [
    f"{item.finding_key}: count={item.affected_count}, ids={len(item.affected_record_ids)}"
    for item in punch
    if item.affected_count != len(item.affected_record_ids)
]
chk("affected_count == len(affected_record_ids) for all rows",
    not count_mismatches,
    "; ".join(count_mismatches))

# 10. total_value formula is consistent
formula_violations: list[str] = []
for item in punch:
    expected = item.direct_cost + item.at_risk_pipeline + item.score_impact * SCORE_WEIGHT_PER_POINT
    if abs(expected - item.total_value) > 0.01:
        formula_violations.append(
            f"{item.finding_key}: expected {expected:.2f}, got {item.total_value:.2f}"
        )
chk("total_value = direct_cost + at_risk + score_impact * 1000",
    not formula_violations, "; ".join(formula_violations))

# 11. Labels are non-empty strings
empty_labels = [item.finding_key for item in punch if not item.label]
chk("all labels are non-empty", not empty_labels, f"empty: {empty_labels}")

# 12. record_type valid
valid_rtypes = {"contact", "company", "deal"}
bad_rtypes = [
    f"{item.finding_key}={item.record_type}"
    for item in punch
    if item.record_type not in valid_rtypes
]
chk("all record_type values are valid", not bad_rtypes, f"bad: {bad_rtypes}")

# 13. severity valid
valid_sevs = {"High", "Medium", "Low"}
bad_sevs = [
    f"{item.finding_key}={item.severity}"
    for item in punch
    if item.severity not in valid_sevs
]
chk("all severity values are valid", not bad_sevs, f"bad: {bad_sevs}")

# 14. Spot-check: stale_deals should be near the top (largest at-risk pipeline)
stale_idx = next(
    (i for i, item in enumerate(punch) if item.finding_key == "stale_deals"), -1
)
chk("stale_deals is in the top 3 (largest at-risk pipeline)",
    stale_idx <= 2,
    f"found at position {stale_idx + 1}")

# 15. to_dict() is JSON-safe (all values are str/int/float/list)
import json
json_violations: list[str] = []
for item in punch:
    try:
        json.dumps(item.to_dict())
    except (TypeError, ValueError) as e:
        json_violations.append(f"{item.finding_key}: {e}")
chk("all rows serialise to JSON without error",
    not json_violations, "; ".join(json_violations))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("=" * 60)
if errors:
    print(f"RESULT: {len(errors)} failure(s)")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("RESULT: All assertions passed.")
    print("=" * 60)
    sys.exit(0)
