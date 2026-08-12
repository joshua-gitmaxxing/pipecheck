"""
scorer_costs_smoke_test.py
==========================
Full pipeline smoke test:  parse -> checks -> score -> costs

Asserts:
  1. All four health scores are in [0, 100].
  2. The overall score is less than 100  (the sample data is dirty).
  3. The contact, company, and deal sub-scores are all in [0, 100].
  4. Direct cost > $0 (there are findings with a non-zero minutes-to-fix).
  5. At-risk pipeline > $0 (open stale deals exist with non-zero amounts).
  6. No individual deal's at-risk pipeline value exceeds that deal's Amount
     (the cap is working).
  7. The no-double-counting rule holds: summing at_risk_pipeline across ALL
     findings for each deal gives exactly the value attributed to its worst
     finding (no inflation from multiple attributions).
  8. Every enriched finding has the three cost keys: rep_hours, direct_cost,
     at_risk_pipeline.
  9. The breakdown dict contains every finding key that appears in the findings.
 10. total_rep_hours == sum of individual rep_hours in the findings list.

Usage:
    cd backend
    .\\venv\\Scripts\\python.exe scorer_costs_smoke_test.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from app.config import build_config
from app.models import AuditConfig, ParsedData
from app.parser import parse_upload
from app.checks import run_all_checks
from app.scorer import score, SEVERITY_DEDUCTION, PER_RECORD_CAP
from app.costs import calculate_costs

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE = Path(__file__).parent.parent / "frontend" / "public" / "sample"

cfg_dict = build_config()
cfg      = AuditConfig.from_dict(cfg_dict)

print(f"Loading sample CSVs from: {SAMPLE}\n")
data = parse_upload(
    str(SAMPLE / "contacts.csv"),
    str(SAMPLE / "companies.csv"),
    str(SAMPLE / "deals.csv"),
)
print(f"Parsed: {data.n_contacts} contacts, {data.n_companies} companies, {data.n_deals} deals")

findings = run_all_checks(data, cfg)
print(f"Checks : {len(findings)} findings produced\n")

score_result = score(findings, data, cfg)
cost_result  = calculate_costs(findings, data, cfg)

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
# Section 1: Health Scores
# ---------------------------------------------------------------------------

print("=" * 60)
print("SECTION 1: Health Scores")
print("=" * 60)

print(f"\n  overall   = {score_result.overall}  ({score_result.overall_color})")
print(f"  contacts  = {score_result.contacts}  ({score_result.contacts_color})")
print(f"  companies = {score_result.companies}  ({score_result.companies_color})")
print(f"  deals     = {score_result.deals}  ({score_result.deals_color})")
print()

chk("overall score in [0, 100]",
    0 <= score_result.overall <= 100, str(score_result.overall))

chk("contacts score in [0, 100]",
    0 <= score_result.contacts <= 100, str(score_result.contacts))

chk("companies score in [0, 100]",
    0 <= score_result.companies <= 100, str(score_result.companies))

chk("deals score in [0, 100]",
    0 <= score_result.deals <= 100, str(score_result.deals))

chk("overall score < 100 (sample data is not clean)",
    score_result.overall < 100,
    f"got {score_result.overall}")

chk("at least one sub-score < 95 (meaningful findings present)",
    any(s < 95 for s in [
        score_result.contacts, score_result.companies, score_result.deals
    ]),
    f"contacts={score_result.contacts}, companies={score_result.companies}, "
    f"deals={score_result.deals}")

chk("color codes are valid strings",
    all(c in ("green", "amber", "red") for c in [
        score_result.overall_color,
        score_result.contacts_color,
        score_result.companies_color,
        score_result.deals_color,
    ]))

# Verify colour bands match score values
for name, sc, col in [
    ("overall",   score_result.overall,   score_result.overall_color),
    ("contacts",  score_result.contacts,  score_result.contacts_color),
    ("companies", score_result.companies, score_result.companies_color),
    ("deals",     score_result.deals,     score_result.deals_color),
]:
    expected_col = "green" if sc >= 80 else ("amber" if sc >= 50 else "red")
    chk(f"{name} color matches score ({sc} -> {expected_col})",
        col == expected_col, f"got '{col}'")

# Per-record cap: no record should have a deduction > 2 * max_single_deduction
max_possible_penalty = PER_RECORD_CAP * SEVERITY_DEDUCTION["High"]  # 60
chk("per-record cap: every record scores >= 0",
    all(s >= 0 for s in score_result.record_detail.values()))

chk("per-record cap: every record scores >= 100 - max_cap",
    all(s >= 100 - max_possible_penalty for s in score_result.record_detail.values()),
    f"cap={max_possible_penalty}, min found={min(score_result.record_detail.values(), default=100)}")

# Workload imbalance synthetic finding must NOT affect any per-record score
# (It has a record_id "owner:..." and should be excluded)
synthetic_ids = [f["record_id"] for f in findings if f["record_id"].startswith("owner:")]
for sid in synthetic_ids:
    chk(f"synthetic '{sid}' absent from record_detail",
        sid not in score_result.record_detail)

print(f"\n  record_detail covers {len(score_result.record_detail)} records "
      f"(expect {data.n_contacts + data.n_companies + data.n_deals})")


# ---------------------------------------------------------------------------
# Section 2: Direct Cost
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print("SECTION 2: Direct Cost")
print("=" * 60)
print()

ef = cost_result.findings  # enriched findings

chk("direct_cost > $0",
    cost_result.total_direct_cost > 0,
    f"got ${cost_result.total_direct_cost:.2f}")

chk("total_rep_hours > 0",
    cost_result.total_rep_hours > 0,
    f"got {cost_result.total_rep_hours:.2f}")

chk("all enriched findings have rep_hours key",
    all("rep_hours" in f for f in ef))

chk("all enriched findings have direct_cost key",
    all("direct_cost" in f for f in ef))

chk("all enriched findings have at_risk_pipeline key",
    all("at_risk_pipeline" in f for f in ef))

chk("all rep_hours >= 0",
    all(f["rep_hours"] >= 0 for f in ef))

chk("all direct_cost >= 0",
    all(f["direct_cost"] >= 0 for f in ef))

# Verify totals match sum of individual values
computed_cost  = sum(f["direct_cost"] for f in ef)
computed_hours = sum(f["rep_hours"]   for f in ef)
chk("total_direct_cost == sum(individual direct_costs)",
    abs(cost_result.total_direct_cost - computed_cost) < 0.01,
    f"{cost_result.total_direct_cost:.2f} vs {computed_cost:.2f}")

chk("total_rep_hours == sum(individual rep_hours)",
    abs(cost_result.total_rep_hours - computed_hours) < 0.01,
    f"{cost_result.total_rep_hours:.2f} vs {computed_hours:.2f}")

print(f"\n  Total rep hours   : {cost_result.total_rep_hours:.2f} h")
print(f"  Total direct cost : ${cost_result.total_direct_cost:,.2f}")

# Verify breakdown covers all finding keys
finding_keys_in_findings = {f["finding_key"] for f in ef}
for key in finding_keys_in_findings:
    chk(f"breakdown contains '{key}'",
        key in cost_result.breakdown)


# ---------------------------------------------------------------------------
# Section 3: At-Risk Pipeline
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print("SECTION 3: At-Risk Pipeline")
print("=" * 60)
print()

chk("at_risk_pipeline > $0",
    cost_result.total_at_risk_pipeline > 0,
    f"got ${cost_result.total_at_risk_pipeline:.2f}")

print(f"  Total at-risk pipeline: ${cost_result.total_at_risk_pipeline:,.2f}")

# ── Cap check: no deal's at-risk value may exceed its deal Amount ─────────
# Build deal amount lookup
deal_amounts: dict[str, float] = {}
for _, row in data.deals.iterrows():
    amt = row.get("amount")
    if amt is not None:
        try:
            if not pd.isna(amt):
                deal_amounts[str(row["record_id"])] = float(amt)
        except (TypeError, ValueError):
            pass

deal_findings = [f for f in ef if f.get("record_type") == "deal"]
cap_violations = []
for f in deal_findings:
    rid      = str(f["record_id"])
    at_risk  = f["at_risk_pipeline"]
    if at_risk <= 0:
        continue
    amount = deal_amounts.get(rid)
    if amount is None:
        continue
    if at_risk > amount:
        cap_violations.append((rid, at_risk, amount))

chk("no deal at-risk value exceeds its Amount (cap < 100%)",
    len(cap_violations) == 0,
    f"violations: {cap_violations}")

# ── No-double-counting check ──────────────────────────────────────────────
# For each deal_id, sum up all at_risk_pipeline values.
# Only ONE finding per deal should have a non-zero value.
from collections import defaultdict
deal_at_risk_by_rid: dict[str, list[float]] = defaultdict(list)
for f in deal_findings:
    deal_at_risk_by_rid[str(f["record_id"])].append(f["at_risk_pipeline"])

double_counted = []
for rid, values in deal_at_risk_by_rid.items():
    nonzero = [v for v in values if v > 0]
    if len(nonzero) > 1:
        double_counted.append((rid, nonzero))

chk("no-double-counting: at most one non-zero at_risk_pipeline per deal",
    len(double_counted) == 0,
    f"doubles: {double_counted}")

# ── Verify at-risk only on open deals ────────────────────────────────────
closed_deal_ids = set(
    str(row["record_id"])
    for _, row in data.deals.iterrows()
    if not row.get("is_open", True)
)
closed_with_risk = [
    f for f in deal_findings
    if str(f["record_id"]) in closed_deal_ids and f["at_risk_pipeline"] > 0
]
chk("closed deals have at_risk_pipeline = 0",
    len(closed_with_risk) == 0,
    f"closed with risk: {[(f['record_id'], f['at_risk_pipeline']) for f in closed_with_risk]}")

# ── Show which deals contribute at-risk pipeline ─────────────────────────
print("\n  Deals with at-risk pipeline:")
for f in sorted(deal_findings, key=lambda f: f["at_risk_pipeline"], reverse=True):
    atr = f["at_risk_pipeline"]
    if atr > 0:
        print(f"    {f['record_id']} [{f['finding_key']}] "
              f"severity={f['severity']} -> ${atr:,.2f}")


# ---------------------------------------------------------------------------
# Section 4: to_dict() serialisation
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print("SECTION 4: Serialisation")
print("=" * 60)
print()

score_dict = score_result.to_dict()
cost_dict  = cost_result.to_dict()

chk("score_result.to_dict() has all keys",
    all(k in score_dict for k in [
        "overall", "contacts", "companies", "deals",
        "overall_color", "contacts_color", "companies_color", "deals_color",
    ]))

chk("cost_result.to_dict() has all keys",
    all(k in cost_dict for k in [
        "total_direct_cost", "total_rep_hours", "total_at_risk_pipeline", "breakdown"
    ]))

chk("breakdown serialises correctly",
    isinstance(cost_dict["breakdown"], dict))


# ---------------------------------------------------------------------------
# Final result
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print(f"RESULT: {len(errors)} failure(s)" if errors else "RESULT: All assertions passed.")
print("=" * 60)

if errors:
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)

sys.exit(0)
