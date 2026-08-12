"""
costs.py — Direct cost and at-risk pipeline calculator.

Implements the two-cost model from the Pipecheck build brief.
Both numbers are ALWAYS kept strictly separate.  They are never combined.

──────────────────────────────────────────────────────────────────────────────

1. Direct Cost (Rep Hours)
   ─────────────────────────
   Every finding type has a minutes-to-fix estimate (from AuditConfig).
   Each finding occurrence is charged that many minutes.

   Formula (per finding occurrence):
       rep_hours   = minutes_to_fix[finding_key] / 60
       direct_cost = rep_hours × rep_hourly_rate

   Total direct cost = Σ direct_cost across all findings.

2. At-Risk Pipeline
   ─────────────────
   Applies to open deal findings only.  The risk is based on deal inactivity
   (days since last_activity_date), applied to the deal's Amount.

   Risk bands (configurable in AuditConfig.risk_bands):
       ≥ 30 days no activity → 25 % of Amount at risk
       ≥ 60 days no activity → 50 % of Amount at risk
       ≥ 90 days no activity → 75 % of Amount at risk
       < 30 days             →  0 % (no material risk)

   No-double-counting rule:
       A deal appearing in multiple findings has its at-risk value attributed
       to the SINGLE WORST finding (highest severity) only.  All other
       findings for that deal carry at_risk_pipeline = 0.  Summing the
       at_risk_pipeline column across any subset always gives the correct
       total with no inflation.

──────────────────────────────────────────────────────────────────────────────

Output: CostResult dataclass
    findings            : list[dict]    — enriched findings (adds rep_hours,
                                          direct_cost, at_risk_pipeline to each)
    total_direct_cost   : float         — total USD direct cost
    total_rep_hours     : float         — total rep hours
    total_at_risk_pipeline : float      — total at-risk pipeline USD
    breakdown           : dict          — per-finding-key summary used by the
                                          punch list
"""

from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from .models import ParsedData, AuditConfig


# Severity ranking used to pick the "worst" finding for a deal.
# Lower rank = worse (High is worst).
_SEV_RANK: dict[str, int] = {"High": 0, "Medium": 1, "Low": 2}


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FindingKeyCost:
    """Cost summary for one finding type (used in punch list)."""
    finding_key:       str
    n_records:         int
    rep_hours:         float
    direct_cost:       float
    at_risk_pipeline:  float

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_key":      self.finding_key,
            "n_records":        self.n_records,
            "rep_hours":        round(self.rep_hours, 2),
            "direct_cost":      round(self.direct_cost, 2),
            "at_risk_pipeline": round(self.at_risk_pipeline, 2),
        }


@dataclass
class CostResult:
    """
    Full cost calculation result.

    Attributes
    ----------
    findings : list[dict]
        Each original finding dict, enriched with three extra keys:
            rep_hours        : float  — hours to fix this one record
            direct_cost      : float  — dollar cost for this one record
            at_risk_pipeline : float  — attributed at-risk pipeline (deal
                                        findings only; 0 for non-primary)

    total_direct_cost : float
        Sum of all direct_cost values.

    total_rep_hours : float
        Sum of all rep_hours values.

    total_at_risk_pipeline : float
        Sum of all at_risk_pipeline values (no double-counting applied).

    breakdown : dict[str, FindingKeyCost]
        Aggregated cost data keyed by finding_key.  Used by the punch list
        to build each row.
    """

    findings:              list[dict]
    total_direct_cost:     float
    total_rep_hours:       float
    total_at_risk_pipeline: float
    breakdown:             dict[str, FindingKeyCost] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_direct_cost":      round(self.total_direct_cost, 2),
            "total_rep_hours":        round(self.total_rep_hours, 2),
            "total_at_risk_pipeline": round(self.total_at_risk_pipeline, 2),
            "breakdown": {k: v.to_dict() for k, v in self.breakdown.items()},
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _today() -> pd.Timestamp:
    """Midnight of today (timezone-naive)."""
    return pd.Timestamp.today().normalize()


def _days_since(ts: object) -> Optional[int]:
    """Calendar days between ts and today, or None if ts is NaT / None."""
    if ts is None:
        return None
    try:
        if pd.isna(ts):
            return None
    except (TypeError, ValueError):
        pass
    delta = _today() - pd.Timestamp(ts)
    return max(0, delta.days)


def _apply_risk_band(
    days_inactive: Optional[int],
    risk_bands: list[tuple[int, float]],
) -> float:
    """
    Return the risk fraction for a deal with the given inactivity.

    Iterates through risk_bands (sorted ascending by days threshold) and
    returns the fraction for the highest applicable threshold.
    Example: days=125, bands=[(30,0.25),(60,0.50),(90,0.75)] → 0.75
    """
    if days_inactive is None:
        return 0.0
    fraction = 0.0
    for threshold, rf in sorted(risk_bands, key=lambda b: b[0]):
        if days_inactive >= threshold:
            fraction = rf
        else:
            break  # bands are sorted ascending; no higher band will apply
    return fraction


def _worst_finding_idx(findings_for_deal: list[dict]) -> int:
    """
    Return the list index of the worst (highest severity) finding
    for a single deal.  Ties broken by list order (first encountered).
    """
    return min(
        range(len(findings_for_deal)),
        key=lambda i: _SEV_RANK.get(findings_for_deal[i].get("severity", "Low"), 99),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_costs(
    findings: list[dict],
    data: ParsedData,
    cfg: AuditConfig,
) -> CostResult:
    """
    Enrich each finding with direct cost and at-risk pipeline data, then
    return aggregated totals.

    Parameters
    ----------
    findings  : flat list of Finding dicts from checks.run_all_checks()
    data      : ParsedData — deals DataFrame needed for last_activity_date
                and amount lookups when applying the risk band
    cfg       : AuditConfig — provides minutes_to_fix, rep_hourly_rate,
                risk_bands

    Returns
    -------
    CostResult with enriched findings and aggregated totals.
    """
    today = _today()

    # ── Build deal lookup from the deals DataFrame ────────────────────────
    # deal_id → {last_activity_date, amount, is_open}
    deal_lookup: dict[str, dict] = {}
    for _, row in data.deals.iterrows():
        deal_lookup[str(row["record_id"])] = {
            "last_activity_date": row.get("last_activity_date"),
            "amount":             row.get("amount"),   # may be NaN
            "is_open":            bool(row.get("is_open", True)),
        }

    # ── Deep-copy findings so we don't mutate the caller's list ──────────
    enriched = [copy.deepcopy(f) for f in findings]

    # ── Step 1: Compute direct cost for every finding ─────────────────────
    for f in enriched:
        key     = f.get("finding_key", "")
        minutes = cfg.minutes_to_fix.get(key, 0.0)
        hours   = minutes / 60.0
        cost    = hours * cfg.rep_hourly_rate

        f["rep_hours"]        = hours
        f["direct_cost"]      = cost
        f["at_risk_pipeline"] = 0.0   # will be overwritten for deal findings

    # ── Step 2: Compute at-risk pipeline for deal findings ────────────────
    #
    # Algorithm:
    #   a. Group all deal-type findings by deal record_id.
    #   b. For each deal:
    #      - Look up last_activity_date and amount from the deals DataFrame.
    #      - Calculate days_inactive → apply risk band → risk_fraction.
    #      - at_risk_value = risk_fraction × amount  (0 if amount is NaN or
    #        deal is closed).
    #      - Identify the worst finding (highest severity) for this deal.
    #      - Assign at_risk_value to that finding; keep 0 on all others.
    #
    # Only open deals contribute at-risk pipeline.

    # Index enriched findings by position so we can update them in-place.
    # deal_findings_idx: deal_id → list of indexes into `enriched`
    deal_findings_idx: dict[str, list[int]] = defaultdict(list)
    for idx, f in enumerate(enriched):
        if f.get("record_type") == "deal":
            rid = str(f.get("record_id", ""))
            deal_findings_idx[rid].append(idx)

    for deal_id, idxs in deal_findings_idx.items():
        deal_info = deal_lookup.get(deal_id)
        if not deal_info or not deal_info["is_open"]:
            continue  # closed deal → no at-risk pipeline

        amount = deal_info["amount"]
        if amount is None or (hasattr(amount, "__float__") and pd.isna(amount)):
            continue  # amount missing → cannot calculate pipeline risk

        amount = float(amount)

        last_act      = deal_info["last_activity_date"]
        days_inactive = _days_since(last_act)
        risk_fraction = _apply_risk_band(days_inactive, cfg.risk_bands)

        if risk_fraction == 0.0:
            continue  # deal is active enough → no at-risk attribution

        # Cap: at-risk value must be strictly below 100 % of deal amount.
        # Max risk band is 75 %, so this cap is a safety net.
        at_risk_value = min(risk_fraction * amount, amount * 0.99)

        # Find the worst finding for this deal (lowest severity rank = worst)
        deal_findings_for_this = [enriched[i] for i in idxs]
        worst_pos = _worst_finding_idx(deal_findings_for_this)
        worst_idx = idxs[worst_pos]

        enriched[worst_idx]["at_risk_pipeline"] = at_risk_value

    # ── Step 3: Aggregate totals ──────────────────────────────────────────
    total_direct_cost      = sum(f["direct_cost"]      for f in enriched)
    total_rep_hours        = sum(f["rep_hours"]         for f in enriched)
    total_at_risk_pipeline = sum(f["at_risk_pipeline"]  for f in enriched)

    # ── Step 4: Build per-finding-key breakdown ───────────────────────────
    # n_records = number of findings for this key
    # (caller can de-dup on record_id if they want unique record count)
    breakdown_raw: dict[str, dict] = defaultdict(
        lambda: {"n_records": 0, "rep_hours": 0.0,
                 "direct_cost": 0.0, "at_risk_pipeline": 0.0}
    )
    for f in enriched:
        key = f.get("finding_key", "unknown")
        b   = breakdown_raw[key]
        b["n_records"]         += 1
        b["rep_hours"]         += f["rep_hours"]
        b["direct_cost"]       += f["direct_cost"]
        b["at_risk_pipeline"]  += f["at_risk_pipeline"]

    breakdown: dict[str, FindingKeyCost] = {
        key: FindingKeyCost(
            finding_key=key,
            n_records=vals["n_records"],
            rep_hours=vals["rep_hours"],
            direct_cost=vals["direct_cost"],
            at_risk_pipeline=vals["at_risk_pipeline"],
        )
        for key, vals in breakdown_raw.items()
    }

    return CostResult(
        findings=enriched,
        total_direct_cost=total_direct_cost,
        total_rep_hours=total_rep_hours,
        total_at_risk_pipeline=total_at_risk_pipeline,
        breakdown=breakdown,
    )
