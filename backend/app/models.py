"""
models.py — Typed containers shared across the audit engine.

ParsedData   : holds the three dataframes produced by the parser.
AuditConfig  : typed wrapper around the raw config dict so callers
               get IDE completion and validation without a heavy schema library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Parsed data container
# ---------------------------------------------------------------------------

@dataclass
class ParsedData:
    """Holds the three dataframes returned by parser.parse_upload()."""

    contacts:  pd.DataFrame
    companies: pd.DataFrame
    deals:     pd.DataFrame

    # Convenience counts (populated by parser)
    n_contacts:  int = 0
    n_companies: int = 0
    n_deals:     int = 0

    def __post_init__(self) -> None:
        self.n_contacts  = len(self.contacts)
        self.n_companies = len(self.companies)
        self.n_deals     = len(self.deals)


# ---------------------------------------------------------------------------
# Audit config wrapper
# ---------------------------------------------------------------------------

@dataclass
class AuditConfig:
    """
    Typed wrapper around a raw config dict.

    All values are pulled from the dict at construction time so the rest of
    the engine can access them as typed attributes rather than dict keys.
    """

    # -- Inactivity thresholds (days) --
    contact_decay_days: int         = 90
    deal_stale_days:    int         = 90

    # Stage stagnation: max days a deal may sit in each named stage.
    # Any stage not listed falls back to deal_stale_days.
    stage_stagnation_days: dict[str, int] = field(default_factory=dict)

    # -- Required fields --
    required_contact_fields: list[str] = field(default_factory=list)
    required_company_fields: list[str] = field(default_factory=list)
    required_deal_fields:    list[str] = field(default_factory=list)

    # -- Cost model --
    rep_hourly_rate: float = 75.0

    # Minutes-to-fix per finding type key.
    minutes_to_fix: dict[str, float] = field(default_factory=dict)

    # -- Pipeline risk bands --
    # List of (inactivity_days_threshold, risk_fraction) tuples, sorted
    # ascending.  e.g. [(30, 0.25), (60, 0.50), (90, 0.75)]
    risk_bands: list[tuple[int, float]] = field(default_factory=list)

    # -- Territory mappings --
    # rep_name → list of country strings that belong to their territory.
    territory_map: dict[str, list[str]] = field(default_factory=dict)

    # -- Workload imbalance threshold --
    # Flag a rep if they own this fraction or more of all owned contacts.
    workload_imbalance_threshold: float = 0.50

    # -----------------------------------------------------------------------

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AuditConfig":
        """Build an AuditConfig from the raw config dict produced by config.py."""
        return cls(
            contact_decay_days   = raw["inactivity"]["contact_decay_days"],
            deal_stale_days      = raw["inactivity"]["deal_stale_days"],
            stage_stagnation_days= raw["inactivity"]["stage_stagnation_days"],

            required_contact_fields = raw["required_fields"]["contacts"],
            required_company_fields = raw["required_fields"]["companies"],
            required_deal_fields    = raw["required_fields"]["deals"],

            rep_hourly_rate = raw["cost"]["rep_hourly_rate"],
            minutes_to_fix  = raw["cost"]["minutes_to_fix"],

            risk_bands  = [
                (band["days"], band["risk_fraction"])
                for band in raw["risk_bands"]
            ],

            territory_map = raw["territory_map"],

            workload_imbalance_threshold = raw.get(
                "workload_imbalance_threshold", 0.50
            ),
        )
