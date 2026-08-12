"""
config.py — Default audit configuration.

ALL configurable thresholds, assumptions, and mappings live here.
Nothing in the engine is hardcoded — every check reads from an AuditConfig
instance built from this dict (or from a user-supplied override of it).

The frontend sends a JSON body matching this schema when the user hits
"Run Audit".  If no overrides are supplied, the engine uses DEFAULT_CONFIG.

Schema reference (matches the brief verbatim):
  inactivity              — days before decay / stale / stage stagnation
  required_fields         — which fields must be present per object type
  cost                    — rep hourly rate + minutes-to-fix per finding
  risk_bands              — pipeline risk by deal inactivity window
  territory_map           — rep name → list of countries in their territory
  workload_imbalance_threshold — fraction at which a single rep is over-loaded
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Finding type keys — used as keys in minutes_to_fix and throughout the engine
# ---------------------------------------------------------------------------

FINDING = {
    # Contact checks
    "duplicate_contacts":          "duplicate_contacts",
    "decayed_contacts":            "decayed_contacts",
    "missing_contact_fields":      "missing_contact_fields",
    "lifecycle_inconsistency":     "lifecycle_inconsistency",
    "contact_no_company":          "contact_no_company",
    # Company checks
    "duplicate_companies":         "duplicate_companies",
    "company_no_contacts":         "company_no_contacts",
    # Deal checks
    "stale_deals":                 "stale_deals",
    "deal_stage_stagnation":       "deal_stage_stagnation",
    "deals_past_close_date":       "deals_past_close_date",
    "missing_deal_fields":         "missing_deal_fields",
    # Routing checks
    "territory_mismatch":          "territory_mismatch",
    "workload_imbalance":          "workload_imbalance",
}


# ---------------------------------------------------------------------------
# Default configuration dict
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {

    # ── Inactivity thresholds ─────────────────────────────────────────────
    # How many calendar days of silence before a contact or deal is flagged.
    # Stage stagnation is per-stage and separate from the global deal threshold.
    "inactivity": {
        "contact_decay_days": 90,   # contact with no activity in N days → decayed
        "deal_stale_days":    90,   # deal with no activity in N days → stale

        # Per-stage stagnation limits (days a deal may sit in this stage).
        # Stages not listed here fall back to deal_stale_days.
        "stage_stagnation_days": {
            "Appointment Scheduled":      30,
            "Qualified to Buy":           45,
            "Presentation Scheduled":     60,
            "Decision Maker Bought-In":   60,
            "Contract Sent":              30,
        },
    },

    # ── Required fields ───────────────────────────────────────────────────
    # Column names must match exactly what the parser normalises them to
    # (see parser.py COLUMN_MAP for the canonical internal names).
    "required_fields": {
        "contacts": [
            "email",
            "contact_owner",
            "lifecycle_stage",
            "country",
        ],
        "companies": [
            "name",
            "domain_name",
            "company_owner",
        ],
        "deals": [
            "deal_owner",
            "close_date",
            "amount",
            "associated_contact_ids",
        ],
    },

    # ── Cost model ────────────────────────────────────────────────────────
    # rep_hourly_rate : loaded cost per rep hour (fully-burdened).
    # minutes_to_fix  : estimated minutes of rep time to remediate one record
    #                   for each finding type.  Keys match FINDING above.
    "cost": {
        "rep_hourly_rate": 75.0,   # USD

        "minutes_to_fix": {
            "duplicate_contacts":      15,   # review + merge two records
            "decayed_contacts":        10,   # validate or delete
            "missing_contact_fields":   8,   # look up and fill one field
            "lifecycle_inconsistency": 12,   # investigate + correct stage
            "contact_no_company":      10,   # find and link company record
            "duplicate_companies":     20,   # review + merge two records
            "company_no_contacts":      5,   # investigate or archive
            "stale_deals":             15,   # review deal status with rep
            "deal_stage_stagnation":   15,   # review + advance or close
            "deals_past_close_date":   10,   # update close date or close lost
            "missing_deal_fields":      8,   # look up and fill one field
            "territory_mismatch":      10,   # reassign + notify rep
            "workload_imbalance":      30,   # redistribute territory / accounts
        },
    },

    # ── Pipeline risk bands ───────────────────────────────────────────────
    # Applied to open deal findings only (stale, stagnation, past close date).
    # Bands are evaluated in order; the first matching band wins.
    # risk_fraction is multiplied by deal Amount to get at-risk pipeline value.
    # All thresholds and fractions are configurable — users with long sales
    # cycles (e.g. 12-month enterprise) should increase these accordingly.
    "risk_bands": [
        {"days": 30,  "risk_fraction": 0.25},
        {"days": 60,  "risk_fraction": 0.50},
        {"days": 90,  "risk_fraction": 0.75},
    ],

    # ── Territory mappings ────────────────────────────────────────────────
    # Maps each rep's full name (as it appears in the CSV "Contact Owner"
    # column) to the list of countries they are responsible for.
    # Country strings must match the "Country/Region" values in the CSV.
    # The engine flags any contact whose country is NOT in their owner's list.
    "territory_map": {
        "Alice Johnson": [
            "United States",
            "Canada",
            "Mexico",
        ],
        "Bob Martinez": [
            "United Kingdom",
            "Germany",
            "France",
            "Spain",
            "Italy",
            "Netherlands",
            "Belgium",
            "Sweden",
            "Denmark",
            "Norway",
            "Switzerland",
            "Austria",
            "Poland",
            "Portugal",
            "Ireland",
        ],
        "Carol Kim": [
            "Japan",
            "Australia",
            "Singapore",
            "India",
            "China",
            "South Korea",
            "Hong Kong",
            "New Zealand",
            "Indonesia",
            "Malaysia",
            "Thailand",
            "Philippines",
            "Vietnam",
        ],
    },

    # ── Workload imbalance threshold ──────────────────────────────────────
    # A rep is flagged as over-loaded if they own this fraction or more of
    # all assigned contacts.  0.50 = flag if any rep owns ≥ 50 % of the CRM.
    "workload_imbalance_threshold": 0.50,
}


# ---------------------------------------------------------------------------
# Helper: merge user overrides onto the defaults
# ---------------------------------------------------------------------------

def build_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Return a config dict by deep-merging `overrides` onto DEFAULT_CONFIG.

    Only the keys present in `overrides` are replaced — all other defaults
    are preserved.  The merge is one level deep within each top-level section
    (e.g. overriding `inactivity` replaces only the keys you specify).

    Usage::

        cfg = build_config({"cost": {"rep_hourly_rate": 100.0}})
    """
    import copy
    result = copy.deepcopy(DEFAULT_CONFIG)

    if not overrides:
        return result

    for section, values in overrides.items():
        if section in result and isinstance(result[section], dict) and isinstance(values, dict):
            result[section].update(values)
        else:
            result[section] = values

    return result
