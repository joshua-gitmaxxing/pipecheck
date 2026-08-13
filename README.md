# Pipecheck

**Free, portable CRM audit tool for HubSpot exports.**

Upload your contacts, companies, and deals CSVs. Get a health score, a dollar-quantified cost breakdown, and a prioritized punch list - in under a minute, with no HubSpot access required.

🔗 **Live demo:** [pipecheck-ten.vercel.app](https://pipecheck-ten.vercel.app)

---

## What it does

Most B2B sales teams know their CRM is dirty. The problem isn't awareness - it's quantification. Nobody can tell leadership what the mess is actually costing in rep hours and at-risk pipeline, so it never gets prioritized.

HubSpot gates most of its data quality tooling behind Operations Hub Pro. Pipecheck fills that gap - turning "our CRM is messy" into a dollar figure and a ranked action plan.

**Input:** HubSpot CSV exports (contacts, companies, deals)  
**Output:**
- Overall health score + category sub-scores (contacts / deals / companies)
- Direct cost in rep hours and dollars
- At-risk pipeline value, risk-adjusted by deal inactivity
- Prioritized punch list ranked by what's worth fixing first
- Three downloadable output files ready to act on

---

## Who it's for

- **RevOps teams** without Operations Hub Pro who need a structured CRM audit
- **GTM engineers and consultants** auditing a client's CRM before building outbound infrastructure - get a CSV export, run Pipecheck, arrive at the first client call with a structured report already done
- **Ops-minded founders** who need to justify CRM cleanup to leadership with a number instead of a feeling

---

## The 13 audit checks

**Contacts**
- Duplicate contacts (email + fuzzy name match)
- Decayed contacts (role-based emails or no activity in N days)
- Missing required fields (email, owner, lifecycle stage, country)
- Lifecycle stage inconsistencies (Lead with a closed deal, Customer with no deal)
- Contacts with no associated company

**Companies**
- Duplicate companies (domain + fuzzy name match)
- Companies with no associated contacts

**Deals**
- Stale deals (no activity in N days)
- Deal stage stagnation (stuck in a specific stage beyond its configured limit)
- Deals past close date
- Missing required fields (owner, close date, amount, associated contact)

**Routing**
- Territory routing mismatches (contact's country outside their owner's territory)
- Owner workload imbalance (one rep owns a disproportionate share of contacts)

---

## How the scoring works

Every record starts at 100. Deductions are applied by severity (High / Medium / Low), capped at two severity tiers per record so outlier records don't dominate the overall score. The score is averaged across all records - a larger CRM does not automatically score worse than a smaller one.

The punch list score recovery figures are **measured, not estimated** - calculated by re-running the scorer with each finding category removed and subtracting from the current score.

---

## How the cost model works

Two numbers, always kept separate:

**Direct cost** - rep hours to fix every flagged record, priced at your configured loaded hourly rate.  
Formula: `records × minutes-to-fix ÷ 60 × hourly rate`

**At-risk pipeline** - deal value risk-adjusted by inactivity window:

| Inactivity | Risk factor |
|---|---|
| 30 days | 25% of deal value |
| 60 days | 50% of deal value |
| 90+ days | 75% of deal value |

No double-counting - a deal with multiple findings has its at-risk value attributed to the single worst finding only.

---

## Everything is configurable

Nothing in the engine is hardcoded. Before running an audit, you can adjust:

- Inactivity thresholds (contact decay days, deal stale days, per-stage stagnation limits)
- Required fields per object type
- Rep hourly rate and minutes-to-fix per finding type
- Pipeline risk bands
- Rep-to-territory mappings

Defaults are sensible out of the box - most users change nothing and hit Run.

---

## Output files

| File | Contents | Purpose |
|---|---|---|
| 🟢 Ready to Import | Mechanical formatting fixes only | Safe to import directly into HubSpot |
| 🟡 Review First | Inferred corrections shown side by side | User decides what to accept |
| 🔵 Worklist | Problems requiring human judgment | Checklist - never importable |
| 📦 ZIP | All three files | Download everything at once |

---

## Tech stack

| Layer | Stack |
|---|---|
| Frontend | React + Vite + Shadcn/ui + Tailwind CSS v4 |
| Backend | FastAPI + Python + Pandas |
| Deployment | Vercel (frontend) + Render (backend) |

**Zero LLM in the engine.** Every check is deterministic Python logic. No external APIs called at runtime. Data is in-session only - nothing is saved between sessions.

---

## Running locally

**Prerequisites:** Node.js 18+, Python 3.10+

**Backend**
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload
# Runs on http://localhost:8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173
```

**Environment variables**

Create `frontend/.env.local`:
```
VITE_API_URL=http://localhost:8000
```

---

## Project structure

```
pipecheck/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app + endpoints
│   │   ├── parser.py        # CSV ingestion + column normalisation
│   │   ├── config.py        # Default config + AuditConfig model
│   │   ├── models.py        # Pydantic models / ParsedData
│   │   ├── checks.py        # 13 audit checks
│   │   ├── scorer.py        # Health scoring engine
│   │   ├── costs.py         # Direct cost + at-risk pipeline calculator
│   │   ├── punchlist.py     # Punch list builder + ranker
│   │   └── exports.py       # Green / Yellow / Blue file generation
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Main app + routing
│   │   └── pages/
│   │       ├── LandingPage.jsx
│   │       ├── ConfigPage.jsx
│   │       ├── ProcessingPage.jsx
│   │       ├── ResultsPage.jsx
│   │       └── ExportPage.jsx
│   └── public/sample/       # Sample HubSpot CSVs (all 13 finding types)
├── e2e_test.py              # End-to-end test suite (5 flows, 0 failures)
└── pipecheck-build-brief.md # Full product and engine spec
```

---

## End-to-end test

```bash
pip install requests
python e2e_test.py
```

Tests five flows: sample data, real CSV upload, export downloads, config override, and partial upload. All pass against both local and production environments.

---

## License

MIT - do what you want with it.

---

## Why I built this

*Most GTM teams can tell you their CRM is messy. Nobody has built the layer that turns that into a number an ops lead can act on. I built Pipecheck to understand what that layer looks like in practice - the data model, the scoring logic, the cost assumptions - because that's the infrastructure sitting underneath every outbound motion I'd be building for a client.*
