import React, { useState, useEffect } from 'react';
import { ArrowLeft, Play, FileText, Check, Settings, ShieldCheck, DollarSign, Layers, Globe } from 'lucide-react';
import DesktopOnlyNotice from '../components/DesktopOnlyNotice';

const REGION_COUNTRY_MAP = {
  Unassigned: [
    "United States", "Canada", "United Kingdom", "Germany", "France",
    "Australia", "Japan", "Brazil", "Singapore", "India", "Mexico", "Spain", "Italy"
  ],
  Global: [
    "United States", "Canada", "United Kingdom", "Germany", "France",
    "Australia", "Japan", "Brazil", "Singapore", "India", "Mexico", "Spain", "Italy"
  ],
  'North America': ["United States", "Canada", "Mexico"],
  EMEA: ["United Kingdom", "Germany", "France", "Spain", "Italy", "Netherlands", "United Arab Emirates", "South Africa"],
  APAC: ["Australia", "Japan", "Singapore", "India", "China", "South Korea", "New Zealand"],
  LATAM: ["Brazil", "Mexico", "Argentina", "Colombia", "Chile"],
};

const DEFAULT_OWNERS = [
  'Alice Johnson',
  'Bob Smith',
  'Carol Danvers',
  'David Miller',
  'Eva Green',
];

export default function ConfigPage({ uploadedFiles, onBack, onNext }) {
  // File counts state (null means file is missing)
  const [counts, setCounts] = useState({
    contacts: 50,
    companies: 20,
    deals: 20,
  });

  // Section 1: Inactivity Thresholds
  const [decayDays, setDecayDays] = useState(180);
  const [staleDays, setStaleDays] = useState(30);
  const [stageStagnationDays, setStageStagnationDays] = useState(14);

  // Section 2: Required Fields
  const [requiredFields, setRequiredFields] = useState({
    contacts: {
      email: true,
      contact_owner: true,
      lifecycle_stage: true,
      country: true,
      phone: false,
    },
    companies: {
      name: false,
      domain_name: true,
      company_owner: true,
    },
    deals: {
      deal_owner: true,
      close_date: true,
      amount: true,
      associated_contact_ids: true,
    },
  });

  // Section 3: Cost Assumptions
  const [repRate, setRepRate] = useState(75);
  const [minutesToFix, setMinutesToFix] = useState({
    duplicate_contacts: 15,
    duplicate_companies: 15,
    missing_contact_fields: 5,
    missing_deal_fields: 5,
    decayed_contacts: 10,
    stale_deals: 8,
    lifecycle_inconsistency: 12,
    deal_stage_stagnation: 8,
    deals_past_close_date: 5,
    territory_mismatch: 10,
    workload_imbalance: 20,
    contact_no_company: 5,
    company_no_contacts: 5,
  });

  // Section 4: Risk Bands
  const [riskBands, setRiskBands] = useState([
    { days: 30, riskPct: 25 },
    { days: 60, riskPct: 50 },
    { days: 90, riskPct: 75 },
  ]);

  // Section 5: Territory Mappings
  const [ownersList, setOwnersList] = useState(DEFAULT_OWNERS);
  const [territoryRegions, setTerritoryRegions] = useState({
    'Alice Johnson': 'Unassigned',
    'Bob Smith': 'Unassigned',
    'Carol Danvers': 'Unassigned',
    'David Miller': 'Unassigned',
    'Eva Green': 'Unassigned',
  });

  // Client-side CSV line counting & owner extraction
  useEffect(() => {
    const parseUploadedCSVs = async () => {
      const newCounts = {
        contacts: uploadedFiles?.contacts ? null : 50,
        companies: uploadedFiles?.companies ? null : 20,
        deals: uploadedFiles?.deals ? null : 20,
      };

      const countLines = (file) =>
        new Promise((resolve) => {
          if (!file) return resolve(null);
          const reader = new FileReader();
          reader.onload = (e) => {
            const text = e.target?.result || '';
            const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
            resolve(Math.max(0, lines.length - 1));
          };
          reader.readAsText(file);
        });

      if (uploadedFiles?.contacts) {
        const cCount = await countLines(uploadedFiles.contacts);
        newCounts.contacts = cCount;
      }
      if (uploadedFiles?.companies) {
        const compCount = await countLines(uploadedFiles.companies);
        newCounts.companies = compCount;
      } else if (uploadedFiles && 'companies' in uploadedFiles && !uploadedFiles.companies) {
        newCounts.companies = null;
      }

      if (uploadedFiles?.deals) {
        const dCount = await countLines(uploadedFiles.deals);
        newCounts.deals = dCount;
      } else if (uploadedFiles && 'deals' in uploadedFiles && !uploadedFiles.deals) {
        newCounts.deals = null;
      }

      setCounts(newCounts);

      // Extract unique owners from contacts CSV if present
      if (uploadedFiles?.contacts) {
        const reader = new FileReader();
        reader.onload = (e) => {
          const text = e.target?.result || '';
          const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
          if (lines.length >= 2) {
            const headers = lines[0].split(',').map((h) => h.trim().replace(/^["']|["']$/g, '').toLowerCase());
            const ownerIdx = headers.findIndex((h) => h.includes('owner') || h.includes('contact owner'));
            if (ownerIdx !== -1) {
              const extracted = new Set();
              for (let i = 1; i < lines.length; i++) {
                const row = lines[i].split(',');
                const val = row[ownerIdx]?.trim().replace(/^["']|["']$/g, '');
                if (val && val !== 'null' && val !== 'undefined') {
                  extracted.add(val);
                }
              }
              const foundOwners = Array.from(extracted);
              if (foundOwners.length > 0) {
                setOwnersList(foundOwners);
                const initialRegions = {};
                foundOwners.forEach((owner) => {
                  initialRegions[owner] = 'Unassigned';
                });
                setTerritoryRegions(initialRegions);
              }
            }
          }
        };
        reader.readAsText(uploadedFiles.contacts);
      }
    };

    parseUploadedCSVs();
  }, [uploadedFiles]);

  const toggleRequiredField = (category, field) => {
    setRequiredFields((prev) => ({
      ...prev,
      [category]: {
        ...prev[category],
        [field]: !prev[category][field],
      },
    }));
  };

  const handleRunClick = () => {
    const territoryMap = {};
    ownersList.forEach((owner) => {
      const region = territoryRegions[owner] || 'Unassigned';
      territoryMap[owner] = REGION_COUNTRY_MAP[region] || REGION_COUNTRY_MAP.Unassigned;
    });

    const reqContacts = Object.keys(requiredFields.contacts).filter((k) => requiredFields.contacts[k]);
    const reqCompanies = Object.keys(requiredFields.companies).filter((k) => requiredFields.companies[k]);
    const reqDeals = Object.keys(requiredFields.deals).filter((k) => requiredFields.deals[k]);

    const formattedConfig = {
      inactivity: {
        contact_decay_days: Number(decayDays),
        deal_stale_days: Number(staleDays),
        stage_stagnation_days: {
          Prospecting: Number(stageStagnationDays),
          Qualified: Number(stageStagnationDays),
          Proposal: Number(stageStagnationDays),
          Negotiation: Number(stageStagnationDays),
          'Contract Sent': Number(stageStagnationDays),
        },
      },
      required_fields: {
        contacts: reqContacts,
        companies: reqCompanies,
        deals: reqDeals,
      },
      cost: {
        rep_hourly_rate: Number(repRate),
        minutes_to_fix: minutesToFix,
      },
      risk_bands: riskBands.map((b) => ({
        days: Number(b.days),
        risk_fraction: Number(b.riskPct) / 100,
      })),
      territory_map: territoryMap,
    };

    if (onNext) {
      onNext(formattedConfig);
    }
  };

  return (
    <DesktopOnlyNotice>
      <div className="max-w-4xl mx-auto py-10 px-6 pb-24">

        {/* Back Button */}
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1.5 text-xs text-[--color-muted-foreground] hover:text-[--color-foreground] transition-colors mb-6"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to upload
        </button>

        {/* Page Heading */}
        <div className="mb-8 border-b border-[--color-border] pb-6">
          <h1
            className="text-4xl tracking-tight text-[--color-foreground] mb-2"
            style={{ fontFamily: 'var(--font-display)' }}
          >
            Configure audit settings
          </h1>
          <p className="text-sm text-[--color-muted-foreground] max-w-xl">
            Review and tune engine parameters before executing. Defaults match industry standards.
          </p>
        </div>

        {/* File Confirmation Strip */}
        <div className="mb-10 p-4 rounded-xl bg-[--color-secondary] border border-[--color-border] flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-[--color-foreground]" />
            <span className="text-xs font-semibold uppercase tracking-wider text-[--color-foreground]">
              File Summary
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs font-medium">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-white border border-[--color-border] text-[--color-foreground]">
              {counts.contacts !== null && <Check className="w-3.5 h-3.5 text-[--color-score-green]" />}
              Contacts: <strong className="tabular-nums">{counts.contacts !== null ? `${counts.contacts} records` : '-'}</strong>
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-white border border-[--color-border] text-[--color-foreground]">
              {counts.companies !== null && <Check className="w-3.5 h-3.5 text-[--color-score-green]" />}
              Companies: <strong className="tabular-nums">{counts.companies !== null ? `${counts.companies} records` : '-'}</strong>
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-white border border-[--color-border] text-[--color-foreground]">
              {counts.deals !== null && <Check className="w-3.5 h-3.5 text-[--color-score-green]" />}
              Deals: <strong className="tabular-nums">{counts.deals !== null ? `${counts.deals} records` : '-'}</strong>
            </span>
          </div>
        </div>

        {/* Config Sections Container */}
        <div className="space-y-8 mb-12">

          {/* Section 1 — Inactivity Thresholds */}
          <div className="p-6 border border-[--color-border] rounded-xl bg-white space-y-6">
            <div className="flex items-center gap-2.5 border-b border-[--color-border] pb-4">
              <Settings className="w-4 h-4 text-[--color-foreground]" />
              <h2
                className="text-2xl text-[--color-foreground]"
                style={{ fontFamily: 'var(--font-display)' }}
              >
                Section 1 - Inactivity Thresholds
              </h2>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
              <div>
                <label className="block text-xs font-medium text-[--color-foreground] mb-1.5">
                  Contact Decay (Days)
                </label>
                <input
                  type="number"
                  value={decayDays}
                  onChange={(e) => setDecayDays(e.target.value)}
                  className="w-full px-3 py-2 border border-[--color-input] rounded-lg text-sm bg-white focus:outline-none focus:border-[--color-foreground] tabular-nums"
                />
                <p className="text-[11px] text-[--color-muted-foreground] mt-1">
                  Default: 180 days
                </p>
              </div>

              <div>
                <label className="block text-xs font-medium text-[--color-foreground] mb-1.5">
                  Deal Stale Threshold (Days)
                </label>
                <input
                  type="number"
                  value={staleDays}
                  onChange={(e) => setStaleDays(e.target.value)}
                  className="w-full px-3 py-2 border border-[--color-input] rounded-lg text-sm bg-white focus:outline-none focus:border-[--color-foreground] tabular-nums"
                />
                <p className="text-[11px] text-[--color-muted-foreground] mt-1">
                  Default: 30 days
                </p>
              </div>

              <div>
                <label className="block text-xs font-medium text-[--color-foreground] mb-1.5">
                  Stage Stagnation Limit (Days)
                </label>
                <input
                  type="number"
                  value={stageStagnationDays}
                  onChange={(e) => setStageStagnationDays(e.target.value)}
                  className="w-full px-3 py-2 border border-[--color-input] rounded-lg text-sm bg-white focus:outline-none focus:border-[--color-foreground] tabular-nums"
                />
                <p className="text-[11px] text-[--color-muted-foreground] mt-1">
                  Default: 14 days
                </p>
              </div>
            </div>
          </div>

          {/* Section 2 — Required Fields */}
          <div className="p-6 border border-[--color-border] rounded-xl bg-white space-y-6">
            <div className="flex items-center gap-2.5 border-b border-[--color-border] pb-4">
              <ShieldCheck className="w-4 h-4 text-[--color-foreground]" />
              <h2
                className="text-2xl text-[--color-foreground]"
                style={{ fontFamily: 'var(--font-display)' }}
              >
                Section 2 - Required Fields
              </h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Contacts required fields */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-[--color-muted-foreground] mb-3">
                  Contacts
                </h3>
                <div className="space-y-2.5">
                  {[
                    { id: 'email', label: 'Email' },
                    { id: 'contact_owner', label: 'Owner' },
                    { id: 'lifecycle_stage', label: 'Lifecycle Stage' },
                    { id: 'country', label: 'Country' },
                  ].map((item) => (
                    <label key={item.id} className="flex items-center gap-2.5 cursor-pointer text-xs">
                      <input
                        type="checkbox"
                        checked={!!requiredFields.contacts[item.id]}
                        onChange={() => toggleRequiredField('contacts', item.id)}
                        className="rounded border-[--color-border] text-[--color-primary] focus:ring-0"
                      />
                      <span className="text-[--color-foreground]">{item.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Companies required fields */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-[--color-muted-foreground] mb-3">
                  Companies
                </h3>
                <div className="space-y-2.5">
                  {[
                    { id: 'domain_name', label: 'Domain' },
                    { id: 'company_owner', label: 'Owner' },
                  ].map((item) => (
                    <label key={item.id} className="flex items-center gap-2.5 cursor-pointer text-xs">
                      <input
                        type="checkbox"
                        checked={!!requiredFields.companies[item.id]}
                        onChange={() => toggleRequiredField('companies', item.id)}
                        className="rounded border-[--color-border] text-[--color-primary] focus:ring-0"
                      />
                      <span className="text-[--color-foreground]">{item.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Deals required fields */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-[--color-muted-foreground] mb-3">
                  Deals
                </h3>
                <div className="space-y-2.5">
                  {[
                    { id: 'deal_owner', label: 'Owner' },
                    { id: 'close_date', label: 'Close Date' },
                    { id: 'amount', label: 'Deal Value (Amount)' },
                    { id: 'associated_contact_ids', label: 'Associated Contact' },
                  ].map((item) => (
                    <label key={item.id} className="flex items-center gap-2.5 cursor-pointer text-xs">
                      <input
                        type="checkbox"
                        checked={!!requiredFields.deals[item.id]}
                        onChange={() => toggleRequiredField('deals', item.id)}
                        className="rounded border-[--color-border] text-[--color-primary] focus:ring-0"
                      />
                      <span className="text-[--color-foreground]">{item.label}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Section 3 — Cost Assumptions */}
          <div className="p-6 border border-[--color-border] rounded-xl bg-white space-y-6">
            <div className="flex items-center gap-2.5 border-b border-[--color-border] pb-4">
              <DollarSign className="w-4 h-4 text-[--color-foreground]" />
              <h2
                className="text-2xl text-[--color-foreground]"
                style={{ fontFamily: 'var(--font-display)' }}
              >
                Section 3 - Cost Assumptions
              </h2>
            </div>

            <div className="max-w-xs mb-4">
              <label className="block text-xs font-medium text-[--color-foreground] mb-1.5">
                Loaded Rep Hourly Rate ($/hr)
              </label>
              <input
                type="number"
                value={repRate}
                onChange={(e) => setRepRate(e.target.value)}
                className="w-full px-3 py-2 border border-[--color-input] rounded-lg text-sm bg-white tabular-nums"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-[--color-foreground] mb-3">
                Minutes-to-Fix per Finding Type (13 Types)
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 text-xs">
                {[
                  { key: 'duplicate_contacts', label: 'Duplicate Contacts' },
                  { key: 'duplicate_companies', label: 'Duplicate Companies' },
                  { key: 'missing_contact_fields', label: 'Missing Contact Fields' },
                  { key: 'missing_deal_fields', label: 'Missing Deal Fields' },
                  { key: 'decayed_contacts', label: 'Decayed Contacts' },
                  { key: 'stale_deals', label: 'Stale Deals' },
                  { key: 'lifecycle_inconsistency', label: 'Lifecycle Inconsistency' },
                  { key: 'deal_stage_stagnation', label: 'Stage Stagnation' },
                  { key: 'deals_past_close_date', label: 'Deals Past Close Date' },
                  { key: 'territory_mismatch', label: 'Territory Mismatch' },
                  { key: 'workload_imbalance', label: 'Workload Imbalance' },
                  { key: 'contact_no_company', label: 'Orphaned Contacts' },
                  { key: 'company_no_contacts', label: 'Orphaned Companies' },
                ].map((item) => (
                  <div key={item.key} className="flex items-center justify-between p-2.5 border border-[--color-border] rounded-lg bg-[--color-card]">
                    <span className="text-[--color-foreground] truncate pr-2" title={item.label}>
                      {item.label}
                    </span>
                    <div className="flex items-center gap-1 shrink-0">
                      <input
                        type="number"
                        value={minutesToFix[item.key] || 0}
                        onChange={(e) =>
                          setMinutesToFix({
                            ...minutesToFix,
                            [item.key]: Number(e.target.value),
                          })
                        }
                        className="w-14 px-2 py-1 border border-[--color-input] rounded text-right tabular-nums bg-white"
                      />
                      <span className="text-[10px] text-[--color-muted-foreground]">m</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Section 4 — Risk Bands */}
          <div className="p-6 border border-[--color-border] rounded-xl bg-white space-y-6">
            <div className="flex items-center gap-2.5 border-b border-[--color-border] pb-4">
              <Layers className="w-4 h-4 text-[--color-foreground]" />
              <h2
                className="text-2xl text-[--color-foreground]"
                style={{ fontFamily: 'var(--font-display)' }}
              >
                Section 4 - Risk Bands (Pipeline Inactivity Risk)
              </h2>
            </div>

            <div className="space-y-3 max-w-lg">
              {riskBands.map((band, idx) => (
                <div key={idx} className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 md:gap-4 p-3 sm:p-4 border border-[--color-border] rounded-lg bg-[--color-card] text-xs">
                  <div className="flex flex-col md:flex-row md:items-center gap-1.5 md:gap-2">
                    <span className="font-medium text-[--color-foreground]">Inactivity Window:</span>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        value={band.days}
                        onChange={(e) => {
                          const updated = [...riskBands];
                          updated[idx].days = Number(e.target.value);
                          setRiskBands(updated);
                        }}
                        className="w-16 px-2 py-1 border border-[--color-input] rounded text-center tabular-nums bg-white"
                      />
                      <span className="text-[--color-muted-foreground]">days</span>
                    </div>
                  </div>

                  <div className="flex flex-col md:flex-row md:items-center gap-1.5 md:gap-2">
                    <span className="font-medium text-[--color-foreground]">Risk %:</span>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        value={band.riskPct}
                        onChange={(e) => {
                          const updated = [...riskBands];
                          updated[idx].riskPct = Number(e.target.value);
                          setRiskBands(updated);
                        }}
                        className="w-16 px-2 py-1 border border-[--color-input] rounded text-center tabular-nums bg-white"
                      />
                      <span className="text-[--color-muted-foreground]">%</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Section 5 — Territory Mappings */}
          <div className="p-6 border border-[--color-border] rounded-xl bg-white space-y-6">
            <div className="flex items-center gap-2.5 border-b border-[--color-border] pb-4">
              <Globe className="w-4 h-4 text-[--color-foreground]" />
              <h2
                className="text-2xl text-[--color-foreground]"
                style={{ fontFamily: 'var(--font-display)' }}
              >
                Section 5 - Territory Mappings
              </h2>
            </div>

            <p className="text-xs text-[--color-muted-foreground]">
              Assign each rep owner from the export to a target region for routing mismatch checks.
            </p>

            <div className="divide-y divide-[--color-border] border border-[--color-border] rounded-lg overflow-hidden">
              {ownersList.map((owner) => (
                <div key={owner} className="flex items-center justify-between px-4 py-3 bg-white text-xs">
                  <span className="font-medium text-[--color-foreground]">{owner}</span>
                  <select
                    value={territoryRegions[owner] || 'Unassigned'}
                    onChange={(e) =>
                      setTerritoryRegions({
                        ...territoryRegions,
                        [owner]: e.target.value,
                      })
                    }
                    className="px-3 py-1.5 border border-[--color-input] rounded-md bg-white text-xs text-[--color-foreground] focus:outline-none focus:border-[--color-primary]"
                  >
                    <option value="Unassigned">Unassigned</option>
                    <option value="North America">North America</option>
                    <option value="EMEA">EMEA</option>
                    <option value="APAC">APAC</option>
                    <option value="LATAM">LATAM</option>
                  </select>
                </div>
              ))}
            </div>
          </div>

        </div>

        {/* Prominent Run Audit CTA */}
        <div className="flex items-center justify-end">
          <button
            onClick={handleRunClick}
            className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl bg-[--color-primary] text-[--color-primary-foreground] text-sm font-semibold hover:opacity-85 transition-opacity shadow-xs"
          >
            <Play className="w-4 h-4 fill-current" /> Run Audit →
          </button>
        </div>

      </div>
    </DesktopOnlyNotice>
  );
}
