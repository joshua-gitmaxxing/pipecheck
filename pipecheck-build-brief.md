# Pipecheck — Full Build Brief

## What This File Is

This is the complete project brief for Pipecheck. It covers everything — what the product is, why it exists, the full feature set, the engine logic, the scoring model, the cost model, the UI flow, and the tech stack. The agent should read this file in full at the start of every session and reference it whenever making decisions about architecture, logic, or UI.

---

## Product Name

**Pipecheck**

---

## What It Is

Pipecheck is a free, portable CRM audit tool. It accepts a HubSpot CSV export and returns:

- A health score (overall + by category)
- A dollar-quantified cost breakdown (rep hours + at-risk pipeline)
- A prioritized punch list ranked by what's actually worth fixing first
- Downloadable output files ready to act on

It does what HubSpot's native tooling doesn't — attach a dollar figure to CRM decay, so cleanup can be justified to leadership with a number instead of a feeling.

---

## Why It Exists

CRM decay is universal in B2B sales. Every team knows their CRM is dirty. The problem isn't awareness — it's quantification. Nobody can tell you what the mess is costing in rep hours and at-risk pipeline, so it never gets prioritized.

HubSpot gates most of its data quality tooling behind Operations Hub Pro. Teams not on that tier have no structured way to audit their data. Teams that are on it still can't quantify the cost.

Pipecheck fills the quantification layer — turning "our CRM is messy" into "here's the number, here's what to fix first, and here's what fixing it recovers."

---

## Who It's For

**Primary user:** A RevOps person, ops-minded founder, or GTM engineer at a small to mid-size B2B company. Not on Operations Hub Pro, or on it but still can't quantify data problems in dollar terms.

**Secondary user:** A GTM engineer or consultant auditing a client's CRM before building outbound infrastructure on top of it. Needs a fast diagnostic without portal access — gets a CSV export, runs Pipecheck, arrives at the first client call with a structured report already done.

---

## Core Design Principle

**Everything configurable, nothing hardcoded.**

Every threshold, assumption, and definition lives in a config layer. The UI exposes these as controls the user adjusts before running the audit. The engine reads from config at runtime. When a user changes a value, the audit reruns against their specific settings — not generic defaults.

This includes:
- Inactivity thresholds (days before contact is decayed, days before deal is stale, days per stage)
- Required field definitions (which fields count as required for contacts, companies, deals)
- Rep hourly rate (loaded cost per hour for direct cost calculation)
- Minutes-to-fix estimates (per finding type — used in direct cost calculation)
- Risk bands (inactivity windows and their pipeline risk percentages)
- Rep-to-territory mappings (assign each rep name in the export to a region)

---

## Tech Stack

**Frontend:**
- React
- Vite (scaffolding and local dev server)
- Shadcn/ui (component library — use this for all UI components)
- Tailwind CSS (comes bundled with Shadcn — handles all styling)

**Backend:**
- FastAPI (API layer)
- Python (audit engine)
- Pandas (CSV reading and processing)

**Rules:**
- Zero LLM in the engine. Everything is deterministic pure Python logic.
- No external APIs called at runtime.
- Everything runs locally — nothing saved to a database.
- Data is in-session only. When the session ends, nothing persists.

---

## Audit Checks

### Contact Checks
1. **Duplicate contacts** — match by email, domain, and fuzzy name match
2. **Decayed contacts** — role-based emails (info@, support@, admin@ etc) or no activity in N days (configurable)
3. **Missing required fields** — configurable set, defaults: email, owner, lifecycle stage, country
4. **Lifecycle stage inconsistencies** — contacts marked Lead with a closed-won deal attached, or marked Customer with no deal at all
5. **Contacts with no associated company** — unlinked contact records in a B2B CRM

### Company Checks
6. **Duplicate companies** — match by domain and fuzzy name match
7. **Companies with no associated contacts** — dead weight company records with nothing linked

### Deal Checks
8. **Stale deals** — no activity in N days globally (configurable)
9. **Deal stage stagnation** — deals stuck in the same specific stage for N days (configurable per stage, not global)
10. **Deals past close date** — open deals where the projected close date has already passed
11. **Missing required fields on deals** — configurable set, defaults: owner, close date, deal value, associated contact

### Routing & Ownership Checks
12. **Territory routing mismatches** — contact's country does not match the assigned owner's configured territory
13. **Owner workload imbalance** — one rep owns a disproportionate share of open contacts or pipeline relative to the team

---

## Scoring Model

### Structure
Every record starts at 100. The audit deducts points per finding, weighted by severity. The score is averaged across all records to produce a volume-normalized health score.

### Severity Tiers
- **High** — directly breaks the ability to work a record. Missing email, missing owner, duplicate contact, deal past close date. Highest point deduction per record.
- **Medium** — degrades quality but doesn't fully break it. Decayed contact, stale deal, lifecycle stage inconsistency, deal stage stagnation. Medium deduction.
- **Low** — messy but not immediately costly. Missing phone, owner workload imbalance, company with no contacts. Low deduction.

### Per-Record Cap
Maximum penalty of two severity tiers per record. A record with five problems only loses points for the worst two. This prevents outlier records from dominating the overall score and ensures the health score reflects average population health, not total damage count.

### Volume Normalization
Score is averaged across all records — a larger CRM does not automatically score worse than a smaller one. The score represents average record health.

### Category Scores
Alongside the overall score, Pipecheck surfaces three sub-scores:
- **Contact health:** X/100
- **Deal health:** X/100
- **Company health:** X/100

Color coding: Green above 80, Amber 60–80, Red below 60.

---

## Cost Model

Two types of cost. Always kept separate. Never mixed or combined into a single figure.

### 1. Direct Cost — Rep Hours
Every finding type carries a minutes-to-fix estimate (configurable). Total minutes across all affected records is calculated, then priced at the user's configured loaded hourly rate.

**Formula:** (records affected × minutes per fix) ÷ 60 × hourly rate = direct cost in dollars

**Example:** 33 duplicates × 15 minutes = 8.25 hours × $75/hr = $618

### 2. At-Risk Pipeline
Applies to deal findings only. Takes deal value and applies a risk factor based on inactivity, banded as follows (all configurable):

| Inactivity | Risk Factor |
|---|---|
| 30 days no activity | 25% of deal value at risk |
| 60 days no activity | 50% of deal value at risk |
| 90+ days no activity | 75% of deal value at risk |

Capped below 100% — a neglected deal is not certainly dead. The at-risk figure represents unreliable pipeline, not confirmed lost revenue.

**Why risk-adjust:** Using face value would be alarmist and easy to dismiss. Risk-adjusting makes the number defensible and honest.

**Important — bands should match the user's actual sales cycle.** A 60-day-inactive deal in a 12-month enterprise sales cycle is normal. The same deal in a 14-day transactional cycle is almost certainly dead. This is why the bands are configurable.

### No Double-Counting Rule
A deal with multiple findings has its at-risk value attributed to the single worst finding only. All other findings for that deal show $0 at-risk pipeline. Summing any column or subset of the punch list always produces a correct total with no inflation.

---

## Punch List

### What It Is
A ranked action plan — not just a list of problems. Every finding category appears as a row, ranked by what fixing it is worth, not by how many records are affected.

### Ranking Logic
Each finding category is ranked by combined value across three dimensions:
1. Rep hours recovered
2. At-risk pipeline recovered
3. Score points recovered

The finding that recovers the most across all three ranks first. That's what gets fixed first.

### Score Recovery — Measured Not Estimated
For each finding category, the score recovery figure is calculated by re-running the scorer with that category's findings removed and taking the difference from the current score. This accounts for the non-linear effect of per-record penalty capping. Do not estimate this — measure it.

### Punch List Columns
| Column | Description |
|---|---|
| Finding | Category name |
| Records Affected | Count of flagged records |
| Severity | High / Medium / Low |
| Rep Hours | Hours to remediate |
| Direct Cost | Dollar value of rep hours |
| At-Risk Pipeline | Dollar value of at-risk deals |
| Score Recovery | Points recovered if fixed |

Each row is expandable to show the individual affected records within that finding category.

---

## Output / Export Layer

Three types of downloadable output. Never mix them. Each serves a different purpose.

### 🟢 Ready to Import
Mechanical, safe corrections only. Formatting fixes — trimming whitespace, standardizing country names, correcting obvious formatting errors. The data meaning never changes, only the formatting.

**Rules:**
- Include only Record ID and changed columns — narrow blast radius
- Fields not being changed are excluded entirely (blank cells can clear values in HubSpot importer)
- Never include records queued for merging in this file (prevents collision with master record)

### 🟡 Review First
Inferred corrections the engine cannot be certain about. Probable email domain typos, inferred missing values. Never pre-applied.

**Format:** Current value + proposed value side by side. User decides what to accept.

### 🔵 Worklist
Problems requiring human judgment. Merging duplicates, reassigning accounts, deciding if a silent deal is actually dead. No mechanical fix exists.

**Format:** A checklist, not an import file. Never importable directly — duplicate merges especially cannot be undone in HubSpot.

### Download Options
- Download each file individually
- Download all three as a single ZIP

---

## UI Flow — Screen by Screen

### Screen 1 — Landing / Upload
**Job:** Get the file uploaded. Nothing else.

**Contains:**
- Tool name (Pipecheck) and one line describing what it does
- Drag and drop file zone — CSV only
- "Try with sample data" button — preloads a sample HubSpot export so the user sees a full report without uploading anything

**Design principle:** One obvious action. User knows what to do within two seconds of landing.

---

### Screen 2 — Config
**Job:** Let the user review and adjust settings before the audit runs. Appears after upload, before run.

**Contains:**
- File confirmation — record counts for contacts, deals, companies confirming data came in correctly
- Config sections (all pre-filled with sensible defaults):
  1. **Inactivity thresholds** — days before contact is decayed, days before deal is stale, days per stage for stagnation
  2. **Required fields** — checkboxes for which fields are required on contacts, companies, deals
  3. **Cost assumptions** — loaded rep hourly rate, minutes-to-fix per finding type
  4. **Risk bands** — inactivity windows (30/60/90 days) and their pipeline risk percentages (25/50/75%)
  5. **Territory mappings** — assign each rep name found in the export to a region via dropdown
- "Run Audit" button — clear and prominent at the bottom

**Design principle:** This is a review screen, not a form. Defaults should be good enough that most users change nothing and just hit Run. Config is there for the ones who want to tune it.

---

### Screen 3 — Processing
**Job:** Show the audit is running. Not frozen.

**Contains:**
- Progress bar with labeled steps showing what the engine is doing:
  - "Reading records"
  - "Running duplicate checks"
  - "Running contact checks"
  - "Running deal checks"
  - "Running company checks"
  - "Running routing checks"
  - "Scoring records"
  - "Calculating cost model"
  - "Building punch list"
  - "Preparing exports"

**Design principle:** Labeled steps build trust in the output before the user has seen it. They see the engine working through real checks, not just a spinner.

---

### Screen 4 — Results Dashboard
**Job:** Surface the health score, cost figure, and punch list simultaneously. All three at once.

**Layout (top to bottom):**

**Row 1 — Score Strip**
Four numbers side by side. Overall health score large and prominent. Contact health, Deal health, Company health smaller on either side. Color coded green/amber/red.

**Row 2 — Cost Summary**
Two stat cards side by side:
- Total direct cost (rep hours + dollar figure)
- Total at-risk pipeline (dollar figure)

**Row 3 — Punch List Table**
Full width. Every finding category as a row. Columns as defined above. Sorted by combined value highest first. Each row expandable to show affected records.

**Row 4 — Export Bar**
Pinned to bottom. Buttons: Download Ready to Import, Download Review First, Download Worklist, Download All as ZIP.

**Design principle:** Readable and actionable within ten seconds. Score at the top tells you the overall health. Cost tells you what it's worth fixing. Punch list tells you what to fix first. No scrolling required to find the primary action on any screen.

---

## Sample Data

The tool ships with a preloaded sample HubSpot export that demonstrates every finding type. When the user clicks "Try with sample data" on the landing screen, this dataset loads and the audit runs automatically — producing a full results dashboard without the user uploading anything.

The sample data should include deliberate examples of every check: duplicates, decayed contacts, missing fields, misrouted contacts, stale deals, deals past close date, lifecycle inconsistencies, orphaned contacts and companies, stage stagnation, and workload imbalance.

---

## What This Is Not

- Not a live HubSpot integration — CSV export only
- Not a database — nothing is saved between sessions
- Not an LLM-powered tool — every check is deterministic Python logic
- Not a product being sold — portfolio project and internal tooling

---

## Portfolio Framing

*"Most GTM teams can tell you their CRM is messy. Nobody has built the layer that turns that into a number an ops lead can act on. I built Pipecheck to understand what that layer looks like in practice — the data model, the scoring logic, the cost assumptions — because that's the infrastructure sitting underneath every outbound motion I'd be building for a client."*

---

*End of brief. Agent should reference this document throughout the entire build.*
