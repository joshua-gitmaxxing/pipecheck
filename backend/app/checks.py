"""
checks.py — 13 deterministic audit check functions.

Each function signature:
    check_<name>(data: ParsedData, cfg: AuditConfig) -> list[dict]

Finding dict schema
-------------------
Required keys (all 13 checks):
    finding_key   str    Key from the FINDING registry in config.py
    record_id     str    ID of the affected record
    record_type   str    "contact" | "company" | "deal"
    severity      str    "High" | "Medium" | "Low"
    detail        str    Human-readable explanation of the finding

Optional keys (present only where relevant, used by the cost / scoring engine):
    amount             float | None   Deal Amount (at-risk pipeline calc)
    last_activity_date Timestamp      Raw date (decay / staleness age)
    days_inactive      int            Days since last CRM activity
    deal_stage         str            Stage name at time of finding
    days_in_stage      int            Days stuck in current stage
    days_overdue       int            Days past the projected close date
    close_date         Timestamp      Raw close date (past-close-date finding)
    missing_fields     list[str]      Which specific fields are missing
    n_contacts         int            Contacts owned (workload imbalance)
    owner              str            Rep name (workload imbalance)

Severity guide (per brief):
    High   — breaks the ability to work a record
             (missing email, missing owner, duplicate contact, deal past close date)
    Medium — degrades quality without fully breaking it
             (decayed contact, stale deal, lifecycle inconsistency, stagnation)
    Low    — messy but not immediately costly
             (missing phone, workload imbalance, company with no contacts)
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional

import pandas as pd

from .config import FINDING
from .models import ParsedData, AuditConfig


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Similarity threshold for name-based fuzzy duplicate detection.
# Contacts: tighter (0.85) — personal names vary less.
# Companies: looser (0.80) — legal suffixes (Ltd, Inc, Corp) create variance.
FUZZY_CONTACT_THRESHOLD  = 0.85
FUZZY_COMPANY_THRESHOLD  = 0.80

# Email prefixes that identify a functional / role address, not a person.
ROLE_EMAIL_PREFIXES: frozenset[str] = frozenset({
    "info", "support", "admin", "noreply", "no-reply",
    "sales", "contact", "help", "team", "billing",
    "hello", "marketing", "hr", "it", "legal", "ops",
    "operations", "news", "newsletter", "enquiries", "enquiry",
    "webmaster", "postmaster", "abuse", "security", "privacy",
    "feedback", "press", "media", "service", "services",
    "office", "reception", "general", "accounts", "accounting",
    "finance", "procurement",
})

# Closed-stage labels (normalised: lowercase, no spaces).
_CLOSED_WON_NORM:   frozenset[str] = frozenset({"closedwon"})
_CLOSED_STAGES_NORM: frozenset[str] = frozenset({"closedwon", "closedlost"})

# Severity for each missing contact field (brief §Scoring Model).
_CONTACT_FIELD_SEVERITY: dict[str, str] = {
    "email":           "High",
    "contact_owner":   "High",
    "lifecycle_stage": "Medium",
    "country":         "Low",
}

# Severity ordering — lower number = higher priority.
_SEV_RANK: dict[str, int] = {"High": 0, "Medium": 1, "Low": 2}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _today() -> pd.Timestamp:
    """Midnight of today (timezone-naive)."""
    return pd.Timestamp.today().normalize()


def _days_since(ts: object) -> Optional[int]:
    """Return whole days between ts and today, or None if ts is NaT/None."""
    if ts is None or (hasattr(ts, "__class__") and pd.isna(ts)):
        return None
    delta = _today() - pd.Timestamp(ts)
    return max(0, delta.days)


def _normalise_name(name: str) -> str:
    """Lowercase, remove punctuation, collapse whitespace."""
    name = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    return re.sub(r"\s+", " ", name).strip()


def _name_similarity(a: str, b: str) -> float:
    """0–1 similarity between two name strings (SequenceMatcher, stdlib only)."""
    a, b = _normalise_name(a), _normalise_name(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _contact_full_name(row: "pd.Series | dict") -> str:
    """Return 'First Last', gracefully handling NaN parts."""
    parts = []
    for key in ("first_name", "last_name"):
        val = row.get(key) if isinstance(row, dict) else row[key] if key in row.index else ""
        s = str(val).strip()
        if s and s.lower() not in ("nan", "none", ""):
            parts.append(s)
    return " ".join(parts)


def _worst_severity(severities: list[str]) -> str:
    """Return the highest-priority severity from a list."""
    return min(severities, key=lambda s: _SEV_RANK.get(s, 99), default="Low")


def _is_field_empty(val: object) -> bool:
    """True if a field value is blank, NaN, NaT, or an empty list."""
    if isinstance(val, list):
        return len(val) == 0
    try:
        return pd.isna(val)
    except (TypeError, ValueError):
        return False


def _stage_is_open(stage: str) -> bool:
    """True when the deal stage is NOT a closed stage."""
    return stage.lower().replace(" ", "") not in _CLOSED_STAGES_NORM


# ---------------------------------------------------------------------------
# Check 1 — Duplicate contacts
# ---------------------------------------------------------------------------

def check_duplicate_contacts(data: ParsedData, cfg: AuditConfig) -> list[dict]:
    """
    Flags contacts that are likely the same person:
      A. Exact email address match (two or more records share the same email).
      B. Fuzzy full-name match within the same email domain (≥ FUZZY_CONTACT_THRESHOLD).

    Severity: High — duplicate contacts break rep workflows and inflate metrics.
    """
    findings: list[dict] = []
    contacts = data.contacts
    flagged: set[str] = set()

    # ── A. Exact email duplicates ─────────────────────────────────────────
    has_email = contacts[contacts["email"].notna()].copy()
    for email, group in has_email.groupby("email"):
        ids = list(group["record_id"].astype(str))
        if len(ids) < 2:
            continue
        all_ids_str = ", ".join(ids)
        for rid in ids:
            if rid in flagged:
                continue
            findings.append({
                "finding_key": FINDING["duplicate_contacts"],
                "record_id":   rid,
                "record_type": "contact",
                "severity":    "High",
                "detail":      (
                    f"Exact email duplicate: '{email}' appears on "
                    f"records {all_ids_str}."
                ),
            })
            flagged.add(rid)

    # ── B. Fuzzy name + same email domain ────────────────────────────────
    has_domain = contacts[
        contacts["email_domain"].notna() & (contacts["email_domain"] != "")
    ]
    for domain, group in has_domain.groupby("email_domain"):
        if len(group) < 2:
            continue
        rows = group.to_dict("records")
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                name_a = _contact_full_name(a)
                name_b = _contact_full_name(b)
                sim = _name_similarity(name_a, name_b)
                if sim < FUZZY_CONTACT_THRESHOLD:
                    continue
                for row, other_name in ((a, name_b), (b, name_a)):
                    rid = str(row["record_id"])
                    if rid in flagged:
                        continue
                    findings.append({
                        "finding_key": FINDING["duplicate_contacts"],
                        "record_id":   rid,
                        "record_type": "contact",
                        "severity":    "High",
                        "detail":      (
                            f"Likely duplicate: '{_contact_full_name(row)}' "
                            f"resembles '{other_name}' at @{domain} "
                            f"({sim:.0%} name similarity)."
                        ),
                    })
                    flagged.add(rid)

    return findings


# ---------------------------------------------------------------------------
# Check 2 — Decayed contacts
# ---------------------------------------------------------------------------

def check_decayed_contacts(data: ParsedData, cfg: AuditConfig) -> list[dict]:
    """
    Flags contacts that are unlikely to be workable:
      A. Role-based email address (info@, support@, admin@, etc.).
      B. No CRM activity for >= cfg.contact_decay_days days.

    Severity: Medium — degrades quality; contact may still exist.
    """
    findings: list[dict] = []
    threshold = cfg.contact_decay_days

    for _, row in data.contacts.iterrows():
        rid   = str(row["record_id"])
        email = str(row.get("email") or "")

        # A. Role-based email prefix
        if "@" in email:
            prefix = email.split("@")[0].lower().strip()
            if prefix in ROLE_EMAIL_PREFIXES:
                findings.append({
                    "finding_key": FINDING["decayed_contacts"],
                    "record_id":   rid,
                    "record_type": "contact",
                    "severity":    "Medium",
                    "detail":      (
                        f"Role-based email address: '{email}'. "
                        f"Functional inboxes cannot be worked as a contact."
                    ),
                })
                continue  # role-based takes priority; skip inactivity check

        # B. Inactivity
        last_act = row.get("last_activity_date")
        days = _days_since(last_act)
        if days is not None and days >= threshold:
            findings.append({
                "finding_key":       FINDING["decayed_contacts"],
                "record_id":         rid,
                "record_type":       "contact",
                "severity":          "Medium",
                "detail":            (
                    f"No CRM activity for {days} days "
                    f"(threshold: {threshold} days)."
                ),
                "last_activity_date": last_act,
                "days_inactive":      days,
            })

    return findings


# ---------------------------------------------------------------------------
# Check 3 — Missing required fields (contacts)
# ---------------------------------------------------------------------------

def check_missing_contact_fields(data: ParsedData, cfg: AuditConfig) -> list[dict]:
    """
    Flags contacts missing one or more required fields.
    One finding per contact; severity = worst of the missing fields.

    Default required fields: email, contact_owner, lifecycle_stage, country.
    """
    findings: list[dict] = []
    required = cfg.required_contact_fields

    for _, row in data.contacts.iterrows():
        missing = [
            f for f in required
            if f in row.index and _is_field_empty(row[f])
        ]
        if not missing:
            continue

        severities = [_CONTACT_FIELD_SEVERITY.get(f, "Medium") for f in missing]
        findings.append({
            "finding_key":    FINDING["missing_contact_fields"],
            "record_id":      str(row["record_id"]),
            "record_type":    "contact",
            "severity":       _worst_severity(severities),
            "detail":         f"Missing required field(s): {', '.join(missing)}.",
            "missing_fields": missing,
        })

    return findings


# ---------------------------------------------------------------------------
# Check 4 — Lifecycle stage inconsistencies
# ---------------------------------------------------------------------------

def check_lifecycle_inconsistencies(data: ParsedData, cfg: AuditConfig) -> list[dict]:
    """
    Flags two types of stage/deal mismatch (per brief):
      A. Lifecycle = 'Lead' but the contact has a Closed Won deal.
         (Stage should be 'Customer' — the win is already recorded.)
      B. Lifecycle = 'Customer' but no associated deals at all.
         (Either the deal is missing or the stage is wrong.)

    Severity: Medium.
    """
    findings: list[dict] = []
    contacts = data.contacts
    deals    = data.deals

    # Fast lookup: deal record_id → is_closed_won
    deal_won: dict[str, bool] = dict(
        zip(deals["record_id"].astype(str), deals["is_closed_won"].astype(bool))
    )

    for _, row in contacts.iterrows():
        stage    = str(row.get("lifecycle_stage") or "").strip().lower()
        deal_ids = row.get("deal_ids_list")
        if not isinstance(deal_ids, list):
            deal_ids = []
        rid = str(row["record_id"])

        # A. Lead + Closed Won deal
        if stage == "lead":
            won_ids = [d for d in deal_ids if deal_won.get(str(d), False)]
            if won_ids:
                findings.append({
                    "finding_key": FINDING["lifecycle_inconsistency"],
                    "record_id":   rid,
                    "record_type": "contact",
                    "severity":    "Medium",
                    "detail":      (
                        f"Lifecycle stage is 'Lead' but contact has "
                        f"Closed Won deal(s): {', '.join(won_ids)}. "
                        f"Stage should be updated to 'Customer'."
                    ),
                })

        # B. Customer + no deals
        elif stage == "customer":
            if not deal_ids:
                findings.append({
                    "finding_key": FINDING["lifecycle_inconsistency"],
                    "record_id":   rid,
                    "record_type": "contact",
                    "severity":    "Medium",
                    "detail":      (
                        "Lifecycle stage is 'Customer' but no associated deals found. "
                        "Either the deal record is missing or the stage is incorrect."
                    ),
                })

    return findings


# ---------------------------------------------------------------------------
# Check 5 — Contacts with no associated company
# ---------------------------------------------------------------------------

def check_contact_no_company(data: ParsedData, cfg: AuditConfig) -> list[dict]:
    """
    Flags contacts where company_id is missing or empty.
    In a B2B CRM every contact should be linked to a company record.

    Severity: Low — messy but not immediately workflow-breaking.
    """
    findings: list[dict] = []

    for _, row in data.contacts.iterrows():
        has_id = not _is_field_empty(row.get("company_id"))
        if has_id:
            continue
        findings.append({
            "finding_key": FINDING["contact_no_company"],
            "record_id":   str(row["record_id"]),
            "record_type": "contact",
            "severity":    "Low",
            "detail":      (
                "Contact has no associated company record ID. "
                "In a B2B CRM every contact should be linked to a company record."
            ),
        })

    return findings


# ---------------------------------------------------------------------------
# Check 6 — Duplicate companies
# ---------------------------------------------------------------------------

def check_duplicate_companies(data: ParsedData, cfg: AuditConfig) -> list[dict]:
    """
    Flags companies that are likely the same entity:
      A. Exact domain_name match.
      B. Fuzzy company name match across all companies (≥ FUZZY_COMPANY_THRESHOLD).

    Severity: High — duplicate company records fragment contact and deal data.
    """
    findings: list[dict] = []
    companies = data.companies
    flagged: set[str] = set()

    # ── A. Exact domain duplicates ────────────────────────────────────────
    has_domain = companies[companies["domain_name"].notna()]
    for domain, group in has_domain.groupby("domain_name"):
        ids = list(group["record_id"].astype(str))
        if len(ids) < 2:
            continue
        all_ids_str = ", ".join(ids)
        for rid in ids:
            if rid in flagged:
                continue
            findings.append({
                "finding_key": FINDING["duplicate_companies"],
                "record_id":   rid,
                "record_type": "company",
                "severity":    "High",
                "detail":      (
                    f"Domain duplicate: '{domain}' is shared by "
                    f"company records {all_ids_str}."
                ),
            })
            flagged.add(rid)

    # ── B. Fuzzy name duplicates ──────────────────────────────────────────
    rows = companies.to_dict("records")
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            name_a = str(a.get("name") or "")
            name_b = str(b.get("name") or "")
            sim = _name_similarity(name_a, name_b)
            if sim < FUZZY_COMPANY_THRESHOLD:
                continue
            for row, other_name in ((a, name_b), (b, name_a)):
                rid = str(row["record_id"])
                if rid in flagged:
                    continue
                findings.append({
                    "finding_key": FINDING["duplicate_companies"],
                    "record_id":   rid,
                    "record_type": "company",
                    "severity":    "High",
                    "detail":      (
                        f"Likely duplicate company: '{row.get('name')}' "
                        f"resembles '{other_name}' "
                        f"({sim:.0%} name similarity)."
                    ),
                })
                flagged.add(rid)

    return findings


# ---------------------------------------------------------------------------
# Check 7 — Companies with no associated contacts
# ---------------------------------------------------------------------------

def check_company_no_contacts(data: ParsedData, cfg: AuditConfig) -> list[dict]:
    """
    Flags companies that no contact record references.
    Cross-references the contacts DataFrame directly (more reliable than the
    n_associated_contacts field, which can be stale after bulk imports).

    Severity: Low — dead-weight records inflate company counts.
    """
    findings: list[dict] = []

    # Set of company_ids referenced by at least one contact
    referenced: set[str] = set(
        data.contacts["company_id"].dropna().astype(str).unique()
    )

    for _, row in data.companies.iterrows():
        rid = str(row["record_id"])
        if rid in referenced:
            continue
        n = int(row.get("n_associated_contacts") or 0)
        findings.append({
            "finding_key": FINDING["company_no_contacts"],
            "record_id":   rid,
            "record_type": "company",
            "severity":    "Low",
            "detail":      (
                f"Company '{row.get('name')}' has no contacts linked to it "
                f"(n_associated_contacts = {n}). "
                f"Investigate or archive this record."
            ),
        })

    return findings


# ---------------------------------------------------------------------------
# Check 8 — Stale deals
# ---------------------------------------------------------------------------

def check_stale_deals(data: ParsedData, cfg: AuditConfig) -> list[dict]:
    """
    Flags open deals with no CRM activity for >= cfg.deal_stale_days days.

    Severity: Medium.
    Extra fields: amount, last_activity_date, days_inactive.
    """
    findings: list[dict] = []
    threshold = cfg.deal_stale_days

    for _, row in data.deals.iterrows():
        if not row.get("is_open", True):
            continue

        last_act = row.get("last_activity_date")
        days = _days_since(last_act)
        if days is None or days < threshold:
            continue

        findings.append({
            "finding_key":        FINDING["stale_deals"],
            "record_id":          str(row["record_id"]),
            "record_type":        "deal",
            "severity":           "Medium",
            "detail":             (
                f"Deal '{row.get('deal_name')}' has had no CRM activity "
                f"for {days} days (threshold: {threshold} days)."
            ),
            "amount":             row.get("amount"),
            "last_activity_date": last_act,
            "days_inactive":      days,
        })

    return findings


# ---------------------------------------------------------------------------
# Check 9 — Deal stage stagnation
# ---------------------------------------------------------------------------

def check_deal_stage_stagnation(data: ParsedData, cfg: AuditConfig) -> list[dict]:
    """
    Flags open deals that have been in the same pipeline stage for longer
    than the per-stage limit (cfg.stage_stagnation_days).
    Stages not in the map fall back to cfg.deal_stale_days.

    Severity: Medium.
    Extra fields: amount, deal_stage, days_in_stage.
    """
    findings: list[dict] = []

    for _, row in data.deals.iterrows():
        if not row.get("is_open", True):
            continue

        stage = str(row.get("deal_stage") or "").strip()
        if not stage:
            continue

        limit = cfg.stage_stagnation_days.get(stage, cfg.deal_stale_days)

        enter_date    = row.get("enter_stage_date")
        days_in_stage = _days_since(enter_date)
        if days_in_stage is None or days_in_stage < limit:
            continue

        findings.append({
            "finding_key":  FINDING["deal_stage_stagnation"],
            "record_id":    str(row["record_id"]),
            "record_type":  "deal",
            "severity":     "Medium",
            "detail":       (
                f"Deal '{row.get('deal_name')}' has been in stage "
                f"'{stage}' for {days_in_stage} days "
                f"(per-stage limit: {limit} days)."
            ),
            "amount":       row.get("amount"),
            "deal_stage":   stage,
            "days_in_stage": days_in_stage,
        })

    return findings


# ---------------------------------------------------------------------------
# Check 10 — Deals past close date
# ---------------------------------------------------------------------------

def check_deals_past_close_date(data: ParsedData, cfg: AuditConfig) -> list[dict]:
    """
    Flags open deals whose projected close date has already passed.

    Severity: High — an overdue deal is a direct signal of pipeline risk.
    Extra fields: amount, close_date, days_overdue.
    """
    findings: list[dict] = []
    today = _today()

    for _, row in data.deals.iterrows():
        if not row.get("is_open", True):
            continue

        close_date = row.get("close_date")
        if _is_field_empty(close_date):
            continue  # missing close date → caught by check_missing_deal_fields

        close_ts = pd.Timestamp(close_date)
        if close_ts >= today:
            continue

        days_overdue = (today - close_ts).days
        findings.append({
            "finding_key": FINDING["deals_past_close_date"],
            "record_id":   str(row["record_id"]),
            "record_type": "deal",
            "severity":    "High",
            "detail":      (
                f"Deal '{row.get('deal_name')}' close date was "
                f"{close_ts.date()} — {days_overdue} day(s) overdue. "
                f"Update the forecast date or mark as Closed Lost."
            ),
            "amount":      row.get("amount"),
            "close_date":  close_date,
            "days_overdue": days_overdue,
        })

    return findings


# ---------------------------------------------------------------------------
# Check 11 — Missing required fields (deals)
# ---------------------------------------------------------------------------

def check_missing_deal_fields(data: ParsedData, cfg: AuditConfig) -> list[dict]:
    """
    Flags deals missing one or more required fields.
    One finding per deal; all missing deal fields are High severity.

    Default required fields: deal_owner, close_date, amount, associated_contact_ids.
    For associated_contact_ids the derived contact_ids_list column is also consulted.
    """
    findings: list[dict] = []
    required = cfg.required_deal_fields

    for _, row in data.deals.iterrows():
        missing: list[str] = []

        for field in required:
            # For associated_contact_ids prefer the parsed list column
            if field == "associated_contact_ids":
                ids_list = row.get("contact_ids_list", [])
                raw_val  = row.get("associated_contact_ids")
                is_empty = (
                    (isinstance(ids_list, list) and len(ids_list) == 0)
                    and _is_field_empty(raw_val)
                )
                if is_empty:
                    missing.append(field)
            elif field in row.index:
                if _is_field_empty(row[field]):
                    missing.append(field)
            else:
                missing.append(field)  # column absent from DataFrame

        if not missing:
            continue

        findings.append({
            "finding_key":    FINDING["missing_deal_fields"],
            "record_id":      str(row["record_id"]),
            "record_type":    "deal",
            "severity":       "High",
            "detail":         (
                f"Deal '{row.get('deal_name')}' is missing "
                f"required field(s): {', '.join(missing)}."
            ),
            "missing_fields": missing,
            "amount":         row.get("amount"),
        })

    return findings


# ---------------------------------------------------------------------------
# Check 12 — Territory routing mismatches
# ---------------------------------------------------------------------------

def check_territory_mismatches(data: ParsedData, cfg: AuditConfig) -> list[dict]:
    """
    Flags contacts whose country falls outside their assigned owner's territory.
    Skips contacts with a blank country or owner, and contacts whose owner is
    not present in cfg.territory_map (unconfigured reps are not checked).

    Severity: Medium — misrouted contacts degrade rep performance and metrics.
    """
    findings: list[dict] = []
    territory = cfg.territory_map

    for _, row in data.contacts.iterrows():
        owner   = str(row.get("contact_owner") or "").strip()
        country = str(row.get("country") or "").strip()

        if not owner or not country:
            continue
        if owner not in territory:
            continue  # owner has no configured territory — skip

        if country in territory[owner]:
            continue  # correctly routed

        # Find the rep who should own this country (if any)
        correct_rep = next(
            (rep for rep, countries in territory.items() if country in countries),
            None,
        )
        correction_note = (
            f" Should be routed to: {correct_rep}."
            if correct_rep
            else " No configured rep covers this country — check territory settings."
        )

        findings.append({
            "finding_key": FINDING["territory_mismatch"],
            "record_id":   str(row["record_id"]),
            "record_type": "contact",
            "severity":    "Medium",
            "detail":      (
                f"Contact is in {country} but assigned to "
                f"{owner} (territory: {', '.join(territory[owner][:3])}…)."
                + correction_note
            ),
        })

    return findings


# ---------------------------------------------------------------------------
# Check 13 — Owner workload imbalance
# ---------------------------------------------------------------------------

def check_workload_imbalance(data: ParsedData, cfg: AuditConfig) -> list[dict]:
    """
    Flags any rep who owns >= cfg.workload_imbalance_threshold of all assigned
    contacts.  Generates one finding per over-loaded owner.

    record_id is set to 'owner:<rep_name>' — there is no single record to
    flag; the finding reflects the distribution across the owner's contacts.
    Severity: Low.
    """
    findings: list[dict] = []
    threshold = cfg.workload_imbalance_threshold

    owned = data.contacts[data.contacts["contact_owner"].notna()]
    total_owned = len(owned)
    if total_owned == 0:
        return findings

    for owner, group in owned.groupby("contact_owner"):
        count    = len(group)
        fraction = count / total_owned
        if fraction < threshold:
            continue

        findings.append({
            "finding_key": FINDING["workload_imbalance"],
            "record_id":   f"owner:{owner}",
            "record_type": "contact",
            "severity":    "Low",
            "detail":      (
                f"{owner} owns {count} of {total_owned} assigned contacts "
                f"({fraction:.0%}) — exceeds the {threshold:.0%} imbalance "
                f"threshold. Review territory and redistribute accounts."
            ),
            "n_contacts": int(count),
            "owner":      str(owner),
        })

    return findings


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_CHECKS = [
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
]


def run_all_checks(data: ParsedData, cfg: AuditConfig) -> list[dict]:
    """
    Run all 13 checks and return a flat list of every Finding dict produced.
    Each Finding's finding_key identifies which check produced it.
    """
    all_findings: list[dict] = []
    for fn in ALL_CHECKS:
        all_findings.extend(fn(data, cfg))
    return all_findings
