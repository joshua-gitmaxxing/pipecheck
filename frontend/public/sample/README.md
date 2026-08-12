# Sample Dataset — Finding Map

Reference dates assume audit run date of **2026-08-04**.
Stale / decayed threshold defaults: **90 days** (last activity before 2026-05-06).

Territory config assumed:
| Rep | Territory |
|---|---|
| Alice Johnson | North America (US, Canada, Mexico) |
| Bob Martinez | EMEA (UK, France, Germany, Spain…) |
| Carol Kim | APAC (Japan, Australia, Singapore, India, China…) |

---

## Contact Findings

### 1. Duplicate Contacts
| Records | Reason |
|---|---|
| **1001 & 1002** — John Smith / Jon Smith | Exact email match: `john.smith@acmecorp.com` |
| **1003 & 1004** — Sarah Connor / Sara Connor | Same domain `techventures.io` + fuzzy name match |

### 2. Decayed Contacts
| Record | Reason |
|---|---|
| **1005** — Info (info@globalretail.com) | Role-based email prefix `info@` |
| **1006** — Support (support@mediainc.net) | Role-based email prefix `support@` |
| **1007** — James Olson | Last activity 2025-12-01 → 246 days inactive |
| **1008** — Patricia Wells | Last activity 2025-10-15 → 293 days inactive |

### 3. Missing Required Fields (Contacts)
| Record | Missing field |
|---|---|
| **1009** — Marcus Bell | Email |
| **1010** — Linda Torres | Contact Owner |
| **1011** — Kevin Wu | Lifecycle Stage |
| **1012** — Emma Davis | Country/Region |

### 4. Lifecycle Stage Inconsistencies
| Record | Issue |
|---|---|
| **1013** — David Park | Lifecycle = **Lead** but has Closed Won deal D001 |
| **1014** — Angela White | Lifecycle = **Customer** but has no associated deal |

### 5. Contacts With No Associated Company
| Record | Issue |
|---|---|
| **1015** — Ryan James | Company ID and Associated Company both blank |
| **1016** — Mia Chen | Company ID and Associated Company both blank |

---

## Company Findings

### 6. Duplicate Companies
| Records | Reason |
|---|---|
| **C001 & C016** — ACME Corporation / Acme Corp | Same domain `acmecorp.com` |
| **C001 & C017** — ACME Corporation / ACME Corporation Ltd | Same domain + fuzzy name match |
| **C002 & C018** — Tech Ventures Inc / TechVentures | Same domain `techventures.io` |

### 7. Companies With No Associated Contacts
| Record | Company |
|---|---|
| **C019** | Ghost Company LLC |
| **C020** | Phantom Enterprises |

---

## Deal Findings

### 8. Stale Deals (no activity ≥ 90 days)
| Record | Last Activity | Days Stale |
|---|---|---|
| **D002** — Global Retail Expansion | 2026-04-01 | 125 days |
| **D003** — Media Inc Platform Deal | 2026-03-15 | 142 days |

### 9. Deal Stage Stagnation
| Record | Stage | Enter Stage Date | Days in Stage |
|---|---|---|---|
| **D004** — Apex Industries Partnership | Presentation Scheduled | 2026-02-15 | 170 days |
| **D005** — Summit Analytics Contract | Qualified to Buy | 2026-03-01 | 156 days |

### 10. Deals Past Close Date
| Record | Close Date | Days Overdue |
|---|---|---|
| **D006** — NorthStar Annual Renewal | 2026-06-01 | 64 days |
| **D007** — Coastal Dynamics Pilot | 2026-05-15 | 81 days |
| **D008** — Iron Gate Initial Package | 2026-07-01 | 34 days |

### 11. Missing Required Fields (Deals)
| Record | Missing field |
|---|---|
| **D009** — Vantage Enterprise Deal | Amount |
| **D010** — TechFirm Upgrade | Deal Owner |
| **D011** — StartupCo Growth Package | Close Date |
| **D012** — Horizon Annual License | Associated Contact IDs |

---

## Routing & Ownership Findings

### 12. Territory Routing Mismatches
| Record | Contact | Country | Assigned Owner | Owner Territory | Should Be |
|---|---|---|---|---|---|
| **1017** | Hans Mueller | Germany | Alice Johnson | North America | Bob Martinez (EMEA) |
| **1018** | Yuki Tanaka | Japan | Bob Martinez | EMEA | Carol Kim (APAC) |
| **1019** | Carlos Ruiz | Mexico | Carol Kim | APAC | Alice Johnson (North America) |

### 13. Owner Workload Imbalance
| Owner | Contacts Owned | Share |
|---|---|---|
| Alice Johnson | 38 | 77% |
| Bob Martinez | 7 | 14% |
| Carol Kim | 4 | 8% |
| (No owner) | 1 | 2% |

Alice holds ~77% of all owned contacts. Threshold for imbalance flag: any rep owns >50% of total assigned contacts while others own <15%.

---

## Dataset Totals
- Contacts: **50**
- Companies: **20**
- Deals: **20**
- Finding types deliberately seeded: **13 / 13**
