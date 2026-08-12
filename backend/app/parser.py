"""
parser.py — CSV ingestion and normalisation layer.

Responsibilities
----------------
1. Accept raw CSV bytes for contacts, companies, and deals (either uploaded by
   the user or read from the bundled sample files).
2. Map HubSpot export column names → canonical internal names so the rest of
   the engine never has to care about the source column spelling.
3. Parse dates, coerce numeric columns, and split multi-value fields
   (e.g. "Associated Deal IDs" is a semicolon-separated string in HubSpot).
4. Return a ParsedData instance ready for the audit checks.

Nothing here performs any audit logic — it only reads and normalises.
"""

from __future__ import annotations

import io
import re
from typing import Union

import pandas as pd

from .models import ParsedData


# ---------------------------------------------------------------------------
# Column name maps
# HubSpot export header → internal canonical name
# ---------------------------------------------------------------------------

CONTACTS_COLUMN_MAP: dict[str, str] = {
    "Record ID":            "record_id",
    "First Name":           "first_name",
    "Last Name":            "last_name",
    "Email":                "email",
    "Phone Number":         "phone",
    "Associated Company":   "associated_company",
    "Company ID":           "company_id",
    "Lifecycle Stage":      "lifecycle_stage",
    "Contact Owner":        "contact_owner",
    "Country/Region":       "country",
    "Last Activity Date":   "last_activity_date",
    "Create Date":          "create_date",
    "Associated Deal IDs":  "associated_deal_ids",
}

COMPANIES_COLUMN_MAP: dict[str, str] = {
    "Record ID":                    "record_id",
    "Name":                         "name",
    "Domain Name":                  "domain_name",
    "Industry":                     "industry",
    "Country/Region":               "country",
    "Number of Associated Contacts":"n_associated_contacts",
    "Company Owner":                "company_owner",
    "Create Date":                  "create_date",
}

DEALS_COLUMN_MAP: dict[str, str] = {
    "Record ID":              "record_id",
    "Deal Name":              "deal_name",
    "Amount":                 "amount",
    "Deal Stage":             "deal_stage",
    "Close Date":             "close_date",
    "Deal Owner":             "deal_owner",
    "Associated Contact IDs": "associated_contact_ids",
    "Associated Company IDs": "associated_company_ids",
    "Last Activity Date":     "last_activity_date",
    "Create Date":            "create_date",
    "Pipeline":               "pipeline",
    "Enter Stage Date":       "enter_stage_date",
}

# Date columns per object type (to be coerced with pd.to_datetime)
CONTACTS_DATE_COLS:  list[str] = ["last_activity_date", "create_date"]
COMPANIES_DATE_COLS: list[str] = ["create_date"]
DEALS_DATE_COLS:     list[str] = [
    "close_date", "last_activity_date", "create_date", "enter_stage_date"
]

# Lifecycle stages that count as "closed" (won only — not lost)
CLOSED_WON_STAGES = {"closed won", "closedwon"}

# Open-deal stages (everything that is not definitively closed)
CLOSED_STAGES = {"closed won", "closed lost", "closedwon", "closedlost"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_csv(source: Union[bytes, str, io.IOBase]) -> pd.DataFrame:
    """Accept bytes, filepath string, or file-like object and return a DataFrame."""
    if isinstance(source, bytes):
        return pd.read_csv(io.BytesIO(source), dtype=str, keep_default_na=False)
    if isinstance(source, str):
        return pd.read_csv(source, dtype=str, keep_default_na=False)
    return pd.read_csv(source, dtype=str, keep_default_na=False)


def _rename_columns(df: pd.DataFrame, column_map: dict[str, str]) -> pd.DataFrame:
    """
    Rename columns using column_map.  Columns not in the map are kept as-is
    (lowercased and stripped) so unexpected extra columns don't break parsing.
    Unknown columns are prefixed with 'extra_' for traceability.
    """
    df.columns = [c.strip() for c in df.columns]

    # Build rename dict — only rename known columns
    rename = {col: column_map[col] for col in df.columns if col in column_map}
    df = df.rename(columns=rename)

    # Lowercase any remaining unmapped columns
    leftover = {c: f"extra_{c.lower().replace(' ', '_')}" for c in df.columns if c not in column_map.values()}
    df = df.rename(columns=leftover)

    return df


def _strip_strings(df: pd.DataFrame) -> pd.DataFrame:
    """Strip leading/trailing whitespace from every string cell."""
    return df.apply(lambda col: col.str.strip() if col.dtype == object else col)


def _parse_dates(df: pd.DataFrame, date_cols: list[str]) -> pd.DataFrame:
    """Coerce known date columns to datetime (NaT for blanks / unparseable)."""
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=False)
    return df


def _split_ids(series: pd.Series) -> pd.Series:
    """
    HubSpot multi-value fields are semicolon-separated.
    Return a Series of Python lists (empty list for blank cells).
    """
    def _split(val: str) -> list[str]:
        if not val or pd.isna(val):
            return []
        return [v.strip() for v in re.split(r"[;,]", str(val)) if v.strip()]

    return series.apply(_split)


def _extract_email_domain(email_series: pd.Series) -> pd.Series:
    """Return the domain portion of an email address, or '' if invalid."""
    def _domain(email: str) -> str:
        if not email or pd.isna(email):
            return ""
        parts = str(email).split("@")
        return parts[1].lower().strip() if len(parts) == 2 else ""

    return email_series.apply(_domain)


# ---------------------------------------------------------------------------
# Public parsing functions
# ---------------------------------------------------------------------------

def parse_contacts(source: Union[bytes, str, io.IOBase]) -> pd.DataFrame:
    """
    Parse a HubSpot contacts CSV export.

    Returns a DataFrame with canonical internal column names, parsed dates,
    and two derived columns:
      - email_domain   : domain extracted from the email address
      - deal_ids_list  : list of deal ID strings (split from Associated Deal IDs)
    """
    df = _read_csv(source)
    df = _rename_columns(df, CONTACTS_COLUMN_MAP)
    df = _strip_strings(df)
    df = _parse_dates(df, CONTACTS_DATE_COLS)

    # Derived columns
    if "email" in df.columns:
        df["email_domain"] = _extract_email_domain(df["email"])
    else:
        df["email_domain"] = ""

    if "associated_deal_ids" in df.columns:
        df["deal_ids_list"] = _split_ids(df["associated_deal_ids"])
    else:
        df["deal_ids_list"] = pd.Series([[] for _ in range(len(df))])

    # Normalise empty strings to actual NaN for required-field detection
    _blank_to_nan(df, [
        "email", "contact_owner", "lifecycle_stage", "country",
        "company_id", "associated_company",
    ])

    return df


def parse_companies(source: Union[bytes, str, io.IOBase]) -> pd.DataFrame:
    """
    Parse a HubSpot companies CSV export.

    Returns a DataFrame with canonical internal column names and parsed dates.
    """
    df = _read_csv(source)
    df = _rename_columns(df, COMPANIES_COLUMN_MAP)
    df = _strip_strings(df)
    df = _parse_dates(df, COMPANIES_DATE_COLS)

    # Coerce contact count to numeric
    if "n_associated_contacts" in df.columns:
        df["n_associated_contacts"] = pd.to_numeric(
            df["n_associated_contacts"], errors="coerce"
        ).fillna(0).astype(int)

    _blank_to_nan(df, ["name", "domain_name", "company_owner"])

    return df


def parse_deals(source: Union[bytes, str, io.IOBase]) -> pd.DataFrame:
    """
    Parse a HubSpot deals CSV export.

    Returns a DataFrame with canonical internal column names, parsed dates,
    coerced numeric Amount, and split ID list columns:
      - contact_ids_list  : list of associated contact ID strings
      - company_ids_list  : list of associated company ID strings
      - is_open           : bool — True if the deal stage is not a closed stage
      - is_closed_won     : bool — True if stage is Closed Won
    """
    df = _read_csv(source)
    df = _rename_columns(df, DEALS_COLUMN_MAP)
    df = _strip_strings(df)
    df = _parse_dates(df, DEALS_DATE_COLS)

    # Numeric Amount
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")  # NaN where blank

    # Split multi-value ID columns
    for col, derived in [
        ("associated_contact_ids", "contact_ids_list"),
        ("associated_company_ids", "company_ids_list"),
    ]:
        df[derived] = _split_ids(df[col]) if col in df.columns else pd.Series(
            [[] for _ in range(len(df))]
        )

    # Stage booleans
    if "deal_stage" in df.columns:
        stage_lower = df["deal_stage"].str.lower().str.replace(" ", "", regex=False)
        df["is_open"]       = ~stage_lower.isin({s.replace(" ", "") for s in CLOSED_STAGES})
        df["is_closed_won"] =  stage_lower.isin({s.replace(" ", "") for s in CLOSED_WON_STAGES})
    else:
        df["is_open"]       = True
        df["is_closed_won"] = False

    _blank_to_nan(df, ["deal_owner", "close_date", "associated_contact_ids"])

    return df


def _blank_to_nan(df: pd.DataFrame, cols: list[str]) -> None:
    """In-place: convert empty string cells to NaN for the specified columns."""
    for col in cols:
        if col in df.columns:
            df[col] = df[col].replace("", pd.NA)


def _empty_companies_df() -> pd.DataFrame:
    """Return an empty DataFrame with the canonical companies column schema."""
    extra = ["email_domain", "n_associated_contacts"]
    # dict.fromkeys preserves insertion order and deduplicates
    cols = list(dict.fromkeys(list(COMPANIES_COLUMN_MAP.values()) + extra))
    return pd.DataFrame(columns=cols)


def _empty_deals_df() -> pd.DataFrame:
    """Return an empty DataFrame with the canonical deals column schema."""
    extra = ["contact_ids_list", "company_ids_list", "is_open", "is_closed_won"]
    cols = list(dict.fromkeys(list(DEALS_COLUMN_MAP.values()) + extra))
    return pd.DataFrame(columns=cols)


def parse_upload(
    contacts_source:  Union[bytes, str, io.IOBase],
    companies_source: Union[bytes, str, io.IOBase, None] = None,
    deals_source:     Union[bytes, str, io.IOBase, None] = None,
) -> ParsedData:
    """
    Parse all three CSV sources and return a single ParsedData container.

    Parameters
    ----------
    contacts_source  : bytes, filepath, or file-like for contacts CSV (required)
    companies_source : bytes, filepath, or file-like for companies CSV, or None
    deals_source     : bytes, filepath, or file-like for deals CSV, or None

    If companies_source or deals_source is None (or empty bytes), an empty
    DataFrame with the correct column schema is used so the rest of the engine
    works without modification.

    Returns
    -------
    ParsedData
        .contacts   — normalised contacts DataFrame
        .companies  — normalised companies DataFrame (may be empty)
        .deals      — normalised deals DataFrame (may be empty)
        .n_*        — record counts for each object type
    """
    contacts  = parse_contacts(contacts_source)

    if companies_source is None or companies_source == b"":
        companies = _empty_companies_df()
    else:
        companies = parse_companies(companies_source)

    if deals_source is None or deals_source == b"":
        deals = _empty_deals_df()
    else:
        deals = parse_deals(deals_source)

    return ParsedData(
        contacts=contacts,
        companies=companies,
        deals=deals,
    )
