"""
scorer.py — Health score calculator.

Implements the scoring model from the Pipecheck build brief:

  - Every record starts at 100.
  - Deductions: High = 30 pts, Medium = 15 pts, Low = 5 pts.
  - Per-record cap: only the worst two findings on a record contribute to
    its penalty.  A record with five problems only loses points for the worst
    two.  (This prevents outlier records from dominating the average.)
  - Volume normalization: category score = arithmetic mean across ALL records
    in that category (including clean records that score 100).
  - Overall score = mean across every record in the dataset (all types).
  - Color bands (per brief): green >= 80, amber 50-79, red < 50.

Aggregate / synthetic findings (e.g. workload_imbalance, whose record_id
starts with "owner:") are excluded from per-record scoring — they are
CRM-level findings rather than record-level findings.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from statistics import mean
from typing import Any

import pandas as pd

from .models import ParsedData, AuditConfig


# ---------------------------------------------------------------------------
# Severity → deduction mapping (configurable via the dataclass if ever
# we expose it in the config layer, but kept as module constants for now)
# ---------------------------------------------------------------------------

SEVERITY_DEDUCTION: dict[str, int] = {
    "High":   30,
    "Medium": 15,
    "Low":     5,
}

# Maximum number of severity deductions to count per record.
PER_RECORD_CAP: int = 2


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class ScoreResult:
    """
    Health scores for an audit run.

    Attributes
    ----------
    overall, contacts, companies, deals : int
        Integer health scores in [0, 100].
    *_color : str
        "green" | "amber" | "red" — for UI colour-coding.
    record_detail : dict[str, int]
        Mapping of every record_id to its individual health score.
        Useful for highlighting the worst offenders in the UI.
    """

    overall:   int
    contacts:  int
    companies: int
    deals:     int

    overall_color:   str = "green"
    contacts_color:  str = "green"
    companies_color: str = "green"
    deals_color:     str = "green"

    # Per-record scores (record_id → score).  Populated during calculation.
    record_detail: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict (omits record_detail for brevity)."""
        return {
            "overall":         self.overall,
            "contacts":        self.contacts,
            "companies":       self.companies,
            "deals":           self.deals,
            "overall_color":   self.overall_color,
            "contacts_color":  self.contacts_color,
            "companies_color": self.companies_color,
            "deals_color":     self.deals_color,
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _colour(score: int) -> str:
    """Return the colour band for a health score."""
    if score >= 80:
        return "green"
    if score >= 50:
        return "amber"
    return "red"


def _record_score(deductions: list[int]) -> int:
    """
    Compute one record's health score, applying the per-record cap.

    Takes the ``PER_RECORD_CAP`` worst (largest) deductions, sums them,
    and subtracts from 100.  Floor at 0.
    """
    top = sorted(deductions, reverse=True)[:PER_RECORD_CAP]
    return max(0, 100 - sum(top))


def _category_score(
    all_ids: list[str],
    penalties: dict[str, list[int]],
    detail_out: dict[str, int],
) -> int:
    """
    Compute the volume-normalised health score for one record category.

    Parameters
    ----------
    all_ids    : every record_id in this category (including clean ones)
    penalties  : record_id → list of severity deduction values
    detail_out : mutable dict to accumulate per-record scores for the caller

    Returns
    -------
    Integer average score across all records.
    """
    scores: list[int] = []
    for rid in all_ids:
        s = _record_score(penalties.get(rid, []))
        detail_out[rid] = s
        scores.append(s)
    return round(mean(scores)) if scores else 100


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score(
    findings: list[dict],
    data: ParsedData,
    cfg: AuditConfig,
) -> ScoreResult:
    """
    Calculate overall and per-category health scores from a findings list.

    Parameters
    ----------
    findings  : flat list of Finding dicts from checks.run_all_checks()
    data      : ParsedData — needed for total record counts (clean records
                score 100 and must be included in the average)
    cfg       : AuditConfig — included for API consistency; not currently used
                by the scorer itself (deductions are fixed per the brief)

    Returns
    -------
    ScoreResult with four integer scores (0–100) and their colour bands.
    """
    # Accumulate deduction values per record_id, separated by category
    contact_penalties:  dict[str, list[int]] = defaultdict(list)
    company_penalties:  dict[str, list[int]] = defaultdict(list)
    deal_penalties:     dict[str, list[int]] = defaultdict(list)

    for f in findings:
        rid   = str(f.get("record_id", ""))
        rtype = f.get("record_type", "")
        sev   = f.get("severity", "")

        # Synthetic findings (e.g. "owner:Alice Johnson") are not per-record
        if rid.startswith("owner:"):
            continue

        deduction = SEVERITY_DEDUCTION.get(sev, 0)
        if deduction == 0:
            continue

        if rtype == "contact":
            contact_penalties[rid].append(deduction)
        elif rtype == "company":
            company_penalties[rid].append(deduction)
        elif rtype == "deal":
            deal_penalties[rid].append(deduction)

    # All record IDs per category (including clean records)
    contact_ids  = list(data.contacts["record_id"].astype(str))
    company_ids  = list(data.companies["record_id"].astype(str))
    deal_ids     = list(data.deals["record_id"].astype(str))

    record_detail: dict[str, int] = {}

    contacts_score  = _category_score(contact_ids,  contact_penalties,  record_detail)
    companies_score = _category_score(company_ids,  company_penalties,  record_detail)
    deals_score     = _category_score(deal_ids,     deal_penalties,     record_detail)

    # Overall: merge all penalty maps and average over all records
    merged: dict[str, list[int]] = defaultdict(list)
    for penalties in (contact_penalties, company_penalties, deal_penalties):
        for rid, vals in penalties.items():
            merged[rid].extend(vals)

    all_ids     = contact_ids + company_ids + deal_ids
    all_scores  = [_record_score(merged.get(rid, [])) for rid in all_ids]
    overall_score = round(mean(all_scores)) if all_scores else 100

    return ScoreResult(
        overall=overall_score,
        contacts=contacts_score,
        companies=companies_score,
        deals=deals_score,
        overall_color=_colour(overall_score),
        contacts_color=_colour(contacts_score),
        companies_color=_colour(companies_score),
        deals_color=_colour(deals_score),
        record_detail=record_detail,
    )


def score_overall_float(
    findings: list[dict],
    data: ParsedData,
    cfg: AuditConfig,
) -> float:
    """
    Return the overall health score as an unrounded float.

    Identical calculation to ``score()``, but skips the final ``round()`` on
    the overall mean.  Used by the punch list to measure score_impact with
    full precision — e.g. 1.33 instead of collapsing to 1 — so that small
    improvements in large datasets are not lost to rounding.

    Parameters
    ----------
    findings : flat Finding dicts (same as score())
    data     : ParsedData
    cfg      : AuditConfig

    Returns
    -------
    float in [0, 100]
    """
    contact_penalties:  dict[str, list[int]] = defaultdict(list)
    company_penalties:  dict[str, list[int]] = defaultdict(list)
    deal_penalties:     dict[str, list[int]] = defaultdict(list)

    for f in findings:
        rid   = str(f.get("record_id", ""))
        rtype = f.get("record_type", "")
        sev   = f.get("severity", "")

        if rid.startswith("owner:"):
            continue

        deduction = SEVERITY_DEDUCTION.get(sev, 0)
        if deduction == 0:
            continue

        if rtype == "contact":
            contact_penalties[rid].append(deduction)
        elif rtype == "company":
            company_penalties[rid].append(deduction)
        elif rtype == "deal":
            deal_penalties[rid].append(deduction)

    contact_ids = list(data.contacts["record_id"].astype(str))
    company_ids = list(data.companies["record_id"].astype(str))
    deal_ids    = list(data.deals["record_id"].astype(str))

    merged: dict[str, list[int]] = defaultdict(list)
    for penalties in (contact_penalties, company_penalties, deal_penalties):
        for rid, vals in penalties.items():
            merged[rid].extend(vals)

    all_ids    = contact_ids + company_ids + deal_ids
    all_scores = [_record_score(merged.get(rid, [])) for rid in all_ids]
    return mean(all_scores) if all_scores else 100.0
