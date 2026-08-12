"""
punchlist.py — Ranked audit punch list builder.

Takes the outputs of every upstream engine stage and assembles a single
ranked action plan with one row per finding category.

──────────────────────────────────────────────────────────────────────────────

Row Structure (PunchListItem)
─────────────────────────────
finding_key         str        Key from the FINDING registry
label               str        Human-readable category name
record_type         str        "contact" | "company" | "deal"
severity            str        Worst severity among findings of this type
affected_count      int        Unique records flagged
affected_record_ids list[str]  Sorted list of flagged record IDs
rep_hours           float      Total hours to remediate this category
direct_cost         float      Dollar cost of rep hours
at_risk_pipeline    float      Attributed at-risk pipeline (no double-counting)
score_impact        float      Points recovered in overall score if category
                               is fully remediated — measured, not estimated
total_value         float      Ranking key: direct_cost + at_risk_pipeline
                               + score_impact × SCORE_WEIGHT_PER_POINT

Ranking
───────
Descending by total_value.  The score_impact × weight term acts as a
tiebreaker that makes score-point recovery commensurable with dollar figures.

Score Impact — Measured Not Estimated
──────────────────────────────────────
For each finding category, the punch list re-runs the scorer with all
findings of that category excluded and takes the difference from the
current baseline.  This captures the non-linear effect of the per-record
penalty cap: removing one category from a record that has many issues may
recover fewer points than removing it from a record with only that issue.

The baseline is computed as a float (using score_overall_float from scorer.py)
so that small improvements in large datasets are not lost to integer rounding.

──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import FINDING
from .costs import CostResult
from .models import ParsedData, AuditConfig
from .scorer import ScoreResult, score_overall_float


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Dollar weight applied to each recovered score point when computing
# total_value.  $1 000 / pt makes score recovery commensurable with
# dollar figures while keeping it as a tiebreaker rather than a dominant term.
SCORE_WEIGHT_PER_POINT: float = 1_000.0

# Human-readable category labels (1-to-1 with FINDING registry keys)
FINDING_LABELS: dict[str, str] = {
    "duplicate_contacts":      "Duplicate Contacts",
    "decayed_contacts":        "Decayed Contacts",
    "missing_contact_fields":  "Missing Contact Fields",
    "lifecycle_inconsistency": "Lifecycle Stage Inconsistencies",
    "contact_no_company":      "Contacts Without Company",
    "duplicate_companies":     "Duplicate Companies",
    "company_no_contacts":     "Companies Without Contacts",
    "stale_deals":             "Stale Deals",
    "deal_stage_stagnation":   "Deal Stage Stagnation",
    "deals_past_close_date":   "Deals Past Close Date",
    "missing_deal_fields":     "Missing Deal Fields",
    "territory_mismatch":      "Territory Routing Mismatches",
    "workload_imbalance":      "Owner Workload Imbalance",
}

# Record type for each finding category
FINDING_RECORD_TYPE: dict[str, str] = {
    "duplicate_contacts":      "contact",
    "decayed_contacts":        "contact",
    "missing_contact_fields":  "contact",
    "lifecycle_inconsistency": "contact",
    "contact_no_company":      "contact",
    "duplicate_companies":     "company",
    "company_no_contacts":     "company",
    "stale_deals":             "deal",
    "deal_stage_stagnation":   "deal",
    "deals_past_close_date":   "deal",
    "missing_deal_fields":     "deal",
    "territory_mismatch":      "contact",
    "workload_imbalance":      "contact",
}

# Severity rank: lower = worse (used to find the worst severity in a group)
_SEV_RANK: dict[str, int] = {"High": 0, "Medium": 1, "Low": 2}


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class PunchListItem:
    """
    One row in the punch list — one per finding category.

    All monetary values are in USD.  score_impact is in score points (float).
    total_value is the composite ranking key — not a dollar amount.
    """

    finding_key:         str
    label:               str
    record_type:         str
    severity:            str
    affected_count:      int
    affected_record_ids: list[str]
    rep_hours:           float
    direct_cost:         float
    at_risk_pipeline:    float
    score_impact:        float
    total_value:         float

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "finding_key":         self.finding_key,
            "label":               self.label,
            "record_type":         self.record_type,
            "severity":            self.severity,
            "affected_count":      self.affected_count,
            "affected_record_ids": self.affected_record_ids,
            "rep_hours":           round(self.rep_hours, 2),
            "direct_cost":         round(self.direct_cost, 2),
            "at_risk_pipeline":    round(self.at_risk_pipeline, 2),
            "score_impact":        round(self.score_impact, 4),
            "total_value":         round(self.total_value, 2),
        }


# ---------------------------------------------------------------------------
# Score impact measurement
# ---------------------------------------------------------------------------

def _measure_score_impact(
    finding_key:     str,
    all_findings:    list[dict],
    baseline_float:  float,
    data:            ParsedData,
    cfg:             AuditConfig,
) -> float:
    """
    Measure the overall score improvement from eliminating one category.

    Re-runs score_overall_float() with all findings for finding_key excluded,
    then returns max(0, hypothetical - baseline).

    Using the float baseline avoids the quantisation noise of comparing two
    rounded integers, so even a 0.33-pt improvement is preserved.
    """
    filtered     = [f for f in all_findings if f.get("finding_key") != finding_key]
    hypothetical = score_overall_float(filtered, data, cfg)
    return max(0.0, hypothetical - baseline_float)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_punch_list(
    findings:     list[dict],
    score_result: ScoreResult,
    cost_result:  CostResult,
    data:         ParsedData,
    cfg:          AuditConfig,
) -> list[PunchListItem]:
    """
    Build and return the ranked punch list.

    Parameters
    ----------
    findings     : flat Finding dicts from checks.run_all_checks()
                   (use the originals, NOT the cost-enriched copy — the scorer
                    only needs finding_key / record_id / record_type / severity)
    score_result : ScoreResult from scorer.score()
    cost_result  : CostResult from costs.calculate_costs()
    data         : ParsedData — forwarded to the scorer for each re-run
    cfg          : AuditConfig — forwarded to the scorer for each re-run

    Returns
    -------
    list[PunchListItem] sorted by total_value descending.
    Always contains exactly one row per FINDING registry key (13 rows),
    including categories with zero affected records (score 0, cost 0).
    """
    # Compute the unrounded float baseline once — re-used for all 13 score diffs
    baseline_float: float = score_overall_float(findings, data, cfg)

    # Group findings by finding_key (pre-populate with empty lists for all 13)
    by_key: dict[str, list[dict]] = {k: [] for k in FINDING}
    for f in findings:
        key = f.get("finding_key", "")
        if key in by_key:
            by_key[key].append(f)

    items: list[PunchListItem] = []

    for finding_key in FINDING:
        key_findings = by_key[finding_key]

        # ── Unique record IDs ─────────────────────────────────────────────
        # Real record IDs first (sorted), synthetic "owner:*" IDs appended.
        all_rids       = sorted({str(f["record_id"]) for f in key_findings})
        real_rids      = [r for r in all_rids if not r.startswith("owner:")]
        synthetic_rids = [r for r in all_rids if r.startswith("owner:")]
        affected_record_ids = real_rids + synthetic_rids
        affected_count      = len(affected_record_ids)

        # ── Severity — worst across all findings of this type ─────────────
        severities = [f.get("severity", "Low") for f in key_findings]
        severity   = (
            min(severities, key=lambda s: _SEV_RANK.get(s, 99))
            if severities
            else "Low"
        )

        # ── Cost data — from the pre-computed breakdown ───────────────────
        cost_bd          = cost_result.breakdown.get(finding_key)
        rep_hours        = cost_bd.rep_hours        if cost_bd else 0.0
        direct_cost      = cost_bd.direct_cost      if cost_bd else 0.0
        at_risk_pipeline = cost_bd.at_risk_pipeline if cost_bd else 0.0

        # ── Score impact — measured by re-running the scorer ─────────────
        score_impact = _measure_score_impact(
            finding_key, findings, baseline_float, data, cfg
        )

        # ── Composite ranking key ─────────────────────────────────────────
        total_value = (
            direct_cost
            + at_risk_pipeline
            + score_impact * SCORE_WEIGHT_PER_POINT
        )

        items.append(PunchListItem(
            finding_key         = finding_key,
            label               = FINDING_LABELS.get(finding_key, finding_key),
            record_type         = FINDING_RECORD_TYPE.get(finding_key, "contact"),
            severity            = severity,
            affected_count      = affected_count,
            affected_record_ids = affected_record_ids,
            rep_hours           = rep_hours,
            direct_cost         = direct_cost,
            at_risk_pipeline    = at_risk_pipeline,
            score_impact        = score_impact,
            total_value         = total_value,
        ))

    # Sort descending by total_value — highest ROI fix goes first
    items.sort(key=lambda item: item.total_value, reverse=True)

    return items
