"""Quick smoke-test for the parser and config layer."""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from app.config import DEFAULT_CONFIG, build_config, FINDING
from app.models import AuditConfig
from app.parser import parse_upload

SAMPLE = Path(__file__).parent.parent / "frontend" / "public" / "sample"

errors = []

def chk(label, cond, detail=""):
    if cond:
        print(f"  [PASS] {label}")
    else:
        print(f"  [FAIL] {label}" + (f" — {detail}" if detail else ""))
        errors.append(label)

print("\n=== 1. FINDING registry ===")
chk("13 finding keys", len(FINDING) == 13, f"got {len(FINDING)}")

print("\n=== 2. AuditConfig ===")
cfg_dict = build_config()
cfg = AuditConfig.from_dict(cfg_dict)
chk("contact_decay_days=90",  cfg.contact_decay_days == 90)
chk("deal_stale_days=90",     cfg.deal_stale_days    == 90)
chk("rep_hourly_rate=75",     cfg.rep_hourly_rate    == 75.0)
chk("3 risk bands",           len(cfg.risk_bands)    == 3)
chk("13 minutes_to_fix keys", len(cfg.minutes_to_fix) == 13)
chk("Alice territory correct",
    cfg.territory_map.get("Alice Johnson") == ["United States","Canada","Mexico"])
chk("Bob territory has Germany",
    "Germany" in cfg.territory_map.get("Bob Martinez", []))
chk("Carol territory has Japan",
    "Japan" in cfg.territory_map.get("Carol Kim", []))
chk("stage_stagnation_days has Presentation Scheduled",
    "Presentation Scheduled" in cfg.stage_stagnation_days)
chk("workload_imbalance_threshold=0.5",
    cfg.workload_imbalance_threshold == 0.50)

print("\n=== 3. Parse sample CSVs ===")
data = parse_upload(
    str(SAMPLE / "contacts.csv"),
    str(SAMPLE / "companies.csv"),
    str(SAMPLE / "deals.csv"),
)
chk("50 contacts",  data.n_contacts  == 50)
chk("20 companies", data.n_companies == 20)
chk("20 deals",     data.n_deals     == 20)

print("\n=== 4. Contacts normalisation ===")
c = data.contacts
chk("email_domain column present",    "email_domain" in c.columns)
chk("deal_ids_list column present",   "deal_ids_list" in c.columns)
chk("record_id column present",       "record_id" in c.columns)
chk("contact_owner column present",   "contact_owner" in c.columns)

# contact 1009 has blank email → should be NaN
c1009_email = c.loc[c["record_id"] == "1009", "email"]
chk("1009 email is NaN",  c1009_email.isna().all(), str(c1009_email.values))

# contact 1010 has blank owner
c1010_owner = c.loc[c["record_id"] == "1010", "contact_owner"]
chk("1010 owner is NaN", c1010_owner.isna().all(), str(c1010_owner.values))

# email domain extraction
c1001_domain = c.loc[c["record_id"] == "1001", "email_domain"].iloc[0]
chk("1001 email_domain=acmecorp.com", c1001_domain == "acmecorp.com", c1001_domain)

# deal_ids_list is a Python list
c1013_deals = c.loc[c["record_id"] == "1013", "deal_ids_list"].iloc[0]
chk("1013 deal_ids_list contains D001", "D001" in c1013_deals, str(c1013_deals))

print("\n=== 5. Deals normalisation ===")
d = data.deals
chk("is_open column present",       "is_open"       in d.columns)
chk("is_closed_won column present", "is_closed_won" in d.columns)
chk("amount column is numeric",     pd.api.types.is_float_dtype(d["amount"]))

d001 = d.loc[d["record_id"] == "D001"].iloc[0]
chk("D001 is_closed_won=True",  d001["is_closed_won"] == True)
chk("D001 is_open=False",       d001["is_open"]       == False)

d009 = d.loc[d["record_id"] == "D009"].iloc[0]
chk("D009 amount is NaN (missing)", pd.isna(d009["amount"]))

d010 = d.loc[d["record_id"] == "D010"].iloc[0]
chk("D010 deal_owner is NaN (missing)", pd.isna(d010["deal_owner"]))

d011 = d.loc[d["record_id"] == "D011"].iloc[0]
chk("D011 close_date is NaT (missing)", pd.isna(d011["close_date"]))

d012 = d.loc[d["record_id"] == "D012"].iloc[0]
chk("D012 contact_ids_list is empty list", d012["contact_ids_list"] == [])

# enter_stage_date is a Timestamp
d004 = d.loc[d["record_id"] == "D004"].iloc[0]
chk("D004 enter_stage_date parsed", pd.notna(d004["enter_stage_date"]))

print("\n=== 6. Companies normalisation ===")
co = data.companies
chk("record_id column present",   "record_id" in co.columns)
chk("domain_name column present", "domain_name" in co.columns)
chk("n_associated_contacts is int",
    pd.api.types.is_integer_dtype(co["n_associated_contacts"]))
chk("C019 has 0 contacts", co.loc[co["record_id"]=="C019","n_associated_contacts"].iloc[0] == 0)

print()
if errors:
    print(f"RESULT: {len(errors)} FAILURE(S): {errors}")
    sys.exit(1)
else:
    print(f"RESULT: All checks passed.")
