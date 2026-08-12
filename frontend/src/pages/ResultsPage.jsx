import React, { useState } from 'react';
import {
  DollarSign,
  AlertTriangle,
  ListChecks,
  ChevronDown,
  ChevronUp,
  Download,
  ArrowRight,
  ShieldAlert,
} from 'lucide-react';

// Map API colorKey strings to CSS token classes
const SCORE_COLOR_MAP = {
  green: 'text-[--color-score-green]',
  amber: 'text-[--color-score-amber]',
  red:   'text-[--color-score-red]',
};

// Derive color class from a numeric score value
function scoreNumericColor(val) {
  if (val === undefined || val === null) return 'text-[--color-foreground]';
  if (val >= 80) return 'text-[--color-score-green]';
  if (val >= 60) return 'text-[--color-score-amber]';
  return 'text-[--color-score-red]';
}

const SEVERITY_BADGE_STYLE = {
  High:   'border',
  Medium: 'border',
  Low:    'border',
};

const SEVERITY_BADGE_INLINE = {
  High:   { background: 'var(--color-badge-high-bg)',   color: 'var(--color-badge-high-text)',   borderColor: 'var(--color-badge-high-text)' },
  Medium: { background: 'var(--color-badge-medium-bg)', color: 'var(--color-badge-medium-text)', borderColor: 'var(--color-badge-medium-text)' },
  Low:    { background: 'var(--color-badge-low-bg)',    color: 'var(--color-badge-low-text)',    borderColor: 'var(--color-badge-low-text)' },
};

// Helper formatters
const formatCurrency = (val) => {
  if (val === undefined || val === null || isNaN(val)) return '$0.00';
  return `$${Number(val).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};

const formatNumber = (val) => {
  if (val === undefined || val === null || isNaN(val)) return '0';
  return Number(val).toLocaleString('en-US');
};

const formatScoreImpact = (impact) => {
  if (!impact || impact <= 0) return '+0.0 pts';
  // Format to 1 decimal place if clean, or up to 2 decimal places
  const formatted = impact % 1 === 0 ? impact.toFixed(0) : impact.toFixed(1);
  return `+${formatted} pts`;
};

// ScorePill — hero=true gives the Overall card a deep teal background
function ScorePill({ label, score, colorKey, large, hero }) {
  // For numeric color coding: use the score value itself for coloring
  // The colorKey from API is used as a fallback, but we compute from value for accuracy
  const numericColor = scoreNumericColor(score);
  const scoreColorClass = hero ? 'text-white' : (SCORE_COLOR_MAP[colorKey] || numericColor);

  if (hero) {
    return (
      <div
        className="flex flex-col items-center justify-center p-5 rounded-xl"
        style={{ background: 'var(--color-primary)', borderRadius: 'var(--radius-card)' }}
      >
        <span className="text-[10px] uppercase tracking-widest font-medium mb-2" style={{ color: 'rgba(255,255,255,0.7)' }}>
          {label}
        </span>
        <span className={`font-semibold tabular-nums text-4xl sm:text-5xl text-white`}>
          {score !== undefined ? score : '-'}
          <span className="text-sm font-normal" style={{ color: 'rgba(255,255,255,0.7)' }}>/100</span>
        </span>
      </div>
    );
  }

  return (
    <div
      className="flex flex-col items-center justify-center p-5 bg-white"
      style={{ border: '1px solid var(--color-border)', borderRadius: 'var(--radius-card)' }}
    >
      <span className="text-[10px] uppercase tracking-widest text-[--color-muted-foreground] font-medium mb-2">
        {label}
      </span>
      <span className={`font-semibold tabular-nums ${large ? 'text-4xl sm:text-5xl' : 'text-2xl sm:text-3xl'} ${scoreColorClass}`}>
        {score !== undefined ? score : '-'}
        <span className="text-sm font-normal text-[--color-muted-foreground]">/100</span>
      </span>
    </div>
  );
}

const DEFAULT_PUNCH_LIST = [
  {
    finding_key: 'stale_deals',
    label: 'Stale Deals',
    record_type: 'deal',
    severity: 'Medium',
    affected_count: 2,
    affected_record_ids: ['D002', 'D003'],
    rep_hours: 0.5,
    direct_cost: 37.5,
    at_risk_pipeline: 153750.0,
    score_impact: 0.3333,
    total_value: 154120.83,
  },
  {
    finding_key: 'deals_past_close_date',
    label: 'Deals Past Close Date',
    record_type: 'deal',
    severity: 'High',
    affected_count: 3,
    affected_record_ids: ['D006', 'D007', 'D008'],
    rep_hours: 0.5,
    direct_cost: 37.5,
    at_risk_pipeline: 7500.0,
    score_impact: 1.0,
    total_value: 8537.5,
  },
  {
    finding_key: 'duplicate_companies',
    label: 'Duplicate Companies',
    record_type: 'company',
    severity: 'High',
    affected_count: 5,
    affected_record_ids: ['C001', 'C002', 'C016', 'C017', 'C018'],
    rep_hours: 1.67,
    direct_cost: 125.0,
    at_risk_pipeline: 0.0,
    score_impact: 1.6667,
    total_value: 1791.67,
  },
  {
    finding_key: 'duplicate_contacts',
    label: 'Duplicate Contacts',
    record_type: 'contact',
    severity: 'High',
    affected_count: 4,
    affected_record_ids: ['1001', '1002', '1003', '1004'],
    rep_hours: 1.0,
    direct_cost: 75.0,
    at_risk_pipeline: 0.0,
    score_impact: 1.3333,
    total_value: 1408.33,
  },
  {
    finding_key: 'missing_deal_fields',
    label: 'Missing Deal Fields',
    record_type: 'deal',
    severity: 'High',
    affected_count: 4,
    affected_record_ids: ['D009', 'D010', 'D011', 'D012'],
    rep_hours: 0.53,
    direct_cost: 40.0,
    at_risk_pipeline: 0.0,
    score_impact: 1.3333,
    total_value: 1373.33,
  },
  {
    finding_key: 'lifecycle_inconsistency',
    label: 'Lifecycle Stage Inconsistencies',
    record_type: 'contact',
    severity: 'Medium',
    affected_count: 7,
    affected_record_ids: ['1007', '1012', '1013', '1014', '1023', '1033', '1041'],
    rep_hours: 1.4,
    direct_cost: 105.0,
    at_risk_pipeline: 0.0,
    score_impact: 1.1111,
    total_value: 1216.11,
  },
  {
    finding_key: 'deal_stage_stagnation',
    label: 'Deal Stage Stagnation',
    record_type: 'deal',
    severity: 'Medium',
    affected_count: 6,
    affected_record_ids: ['D002', 'D003', 'D004', 'D005', 'D006', 'D007'],
    rep_hours: 1.5,
    direct_cost: 112.5,
    at_risk_pipeline: 0.0,
    score_impact: 1.0,
    total_value: 1112.5,
  },
  {
    finding_key: 'missing_contact_fields',
    label: 'Missing Contact Fields',
    record_type: 'contact',
    severity: 'High',
    affected_count: 4,
    affected_record_ids: ['1009', '1010', '1011', '1012'],
    rep_hours: 0.53,
    direct_cost: 40.0,
    at_risk_pipeline: 0.0,
    score_impact: 0.8333,
    total_value: 873.33,
  },
  {
    finding_key: 'territory_mismatch',
    label: 'Territory Routing Mismatches',
    record_type: 'contact',
    severity: 'Medium',
    affected_count: 5,
    affected_record_ids: ['1012', '1016', '1017', '1018', '1019'],
    rep_hours: 0.83,
    direct_cost: 62.5,
    at_risk_pipeline: 0.0,
    score_impact: 0.7778,
    total_value: 840.28,
  },
  {
    finding_key: 'decayed_contacts',
    label: 'Decayed Contacts',
    record_type: 'contact',
    severity: 'Medium',
    affected_count: 4,
    affected_record_ids: ['1005', '1006', '1007', '1008'],
    rep_hours: 0.67,
    direct_cost: 50.0,
    at_risk_pipeline: 0.0,
    score_impact: 0.6667,
    total_value: 716.67,
  },
  {
    finding_key: 'company_no_contacts',
    label: 'Companies Without Contacts',
    record_type: 'company',
    severity: 'Low',
    affected_count: 5,
    affected_record_ids: ['C016', 'C017', 'C018', 'C019', 'C020'],
    rep_hours: 0.42,
    direct_cost: 31.25,
    at_risk_pipeline: 0.0,
    score_impact: 0.2778,
    total_value: 309.03,
  },
  {
    finding_key: 'contact_no_company',
    label: 'Contacts Without Company',
    record_type: 'contact',
    severity: 'Low',
    affected_count: 2,
    affected_record_ids: ['1015', '1016'],
    rep_hours: 0.33,
    direct_cost: 25.0,
    at_risk_pipeline: 0.0,
    score_impact: 0.1111,
    total_value: 136.11,
  },
  {
    finding_key: 'workload_imbalance',
    label: 'Owner Workload Imbalance',
    record_type: 'contact',
    severity: 'Low',
    affected_count: 1,
    affected_record_ids: ['owner:Alice Johnson'],
    rep_hours: 0.5,
    direct_cost: 37.5,
    at_risk_pipeline: 0.0,
    score_impact: 0.0,
    total_value: 37.5,
  },
];

export default function ResultsPage({ auditData, onNext }) {
  // Local state to track expanded row finding keys
  const [expandedRows, setExpandedRows] = useState({});

  const toggleRow = (key) => {
    setExpandedRows((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  // Safe fallback data structure if auditData is not yet provided
  const score = auditData?.score || {
    overall: 89,
    contacts: 91,
    deals: 84,
    companies: 91,
    overall_color: 'green',
    contacts_color: 'green',
    deals_color: 'green',
    companies_color: 'green',
  };

  const costs = auditData?.costs || {
    direct_cost: 778.75,
    at_risk_pipeline: 153750.0,
    total_rep_hours: 10.38,
  };

  const punchList = auditData
    ? (auditData.punch_list || auditData.punchList || [])
    : DEFAULT_PUNCH_LIST;
  const metadata = auditData?.metadata || {};

  // Handlers for export action buttons (placeholder logging per brief)
  const handleDownload = (type) => {
    console.log(`[Export Action] Requesting download for: ${type}`);
    alert(`Downloading export file: ${type}`);
  };

  return (
    <div className="max-w-6xl mx-auto py-6 sm:py-10 px-4 sm:px-6 pb-28">

      {/* Page Heading */}
      <div className="mb-6 sm:mb-8 flex flex-col sm:flex-row sm:items-end justify-between gap-4 border-b border-[--color-border] pb-6">
        <div>
          <h1
            className="text-3xl sm:text-4xl md:text-5xl tracking-tight text-[--color-foreground] mb-2"
            style={{ fontFamily: 'var(--font-display)' }}
          >
            Audit results
          </h1>
          <p className="text-xs sm:text-sm text-[--color-muted-foreground]">
            CRM data health · Quantified decay cost · Prioritised punch list
          </p>
        </div>

        {metadata.timestamp && (
          <div className="text-xs text-[--color-muted-foreground] font-mono bg-[--color-secondary] px-3 py-1.5 rounded-md border border-[--color-border] self-start sm:self-auto">
            Audit run: {new Date(metadata.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
        )}
      </div>

      {/* Row 1 — Score Strip */}
      <div className="mb-8">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-[--color-muted-foreground] mb-3">
          CRM Health Scores
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
          {/* Overall — deep teal hero card */}
          <ScorePill
            label="Overall health"
            score={score.overall}
            colorKey={score.overall_color}
            large
            hero
          />
          <ScorePill
            label="Contact health"
            score={score.contacts}
            colorKey={score.contacts_color}
          />
          <ScorePill
            label="Deal health"
            score={score.deals}
            colorKey={score.deals_color}
          />
          <ScorePill
            label="Company health"
            score={score.companies}
            colorKey={score.companies_color}
          />
        </div>
      </div>

      {/* Row 2 — Cost Cards */}
      <div className="mb-8">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-[--color-muted-foreground] mb-3">
          Quantified Cost Impact
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Card 1: Direct Remediation Cost */}
          <div className="flex items-center justify-between p-5 sm:p-6 border border-[--color-border] rounded-xl bg-white">
            <div>
              <p className="text-xs text-[--color-muted-foreground] uppercase tracking-wider font-medium mb-1">
                Direct Remediation Cost
              </p>
              <p className="text-3xl sm:text-4xl font-semibold tabular-nums text-[--color-foreground]">
                {formatCurrency(costs.direct_cost)}
              </p>
              <p className="text-xs text-[--color-muted-foreground] mt-1.5">
                {formatNumber(costs.total_rep_hours)} rep hours @ $75/hr loaded rate
              </p>
            </div>
            <div className="p-3 sm:p-3.5 rounded-full bg-[--color-secondary] border border-[--color-border] shrink-0 ml-2">
              <DollarSign className="w-5 h-5 sm:w-6 sm:h-6 text-[--color-foreground]" />
            </div>
          </div>

          {/* Card 2: At-Risk Pipeline */}
          <div className="flex items-center justify-between p-5 sm:p-6 border border-[--color-border] rounded-xl bg-white">
            <div>
              <p className="text-xs text-[--color-muted-foreground] uppercase tracking-wider font-medium mb-1">
                At-Risk Pipeline
              </p>
              <p className={`text-3xl sm:text-4xl font-semibold tabular-nums ${costs.at_risk_pipeline > 0 ? 'text-[--color-score-red]' : 'text-[--color-foreground]'}`}>
                {formatCurrency(costs.at_risk_pipeline)}
              </p>
              <p className="text-xs text-[--color-muted-foreground] mt-1.5">
                Risk-adjusted across inactive open deals (30/60/90d bands)
              </p>
            </div>
            <div className="p-3 sm:p-3.5 rounded-full bg-red-50 border border-red-100 shrink-0 ml-2">
              <AlertTriangle className="w-5 h-5 sm:w-6 sm:h-6 text-[--color-score-red]" />
            </div>
          </div>
        </div>
      </div>

      {/* Row 3 — Punch List Table */}
      <div className="mb-10 border border-[--color-border] rounded-xl overflow-hidden bg-white">
        <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b border-[--color-border] bg-[--color-secondary]">
          <div className="flex items-center gap-2">
            <ListChecks className="w-4 h-4 text-[--color-foreground]" />
            <span className="text-xs sm:text-sm font-semibold text-[--color-foreground]">
              Prioritised Punch List
            </span>
          </div>
          <span className="text-[11px] sm:text-xs text-[--color-muted-foreground]">
            Ranked by recovery value
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs sm:text-sm text-left">
            <thead>
              <tr className="border-b border-[--color-border] bg-white text-[--color-muted-foreground] text-[11px] sm:text-xs font-medium uppercase tracking-wider">
                <th className="px-2 sm:px-4 py-3 text-center w-8 sm:w-10">#</th>
                <th className="px-3 sm:px-5 py-3">Finding</th>
                <th className="hidden md:table-cell px-4 py-3">Record Type</th>
                <th className="px-2 sm:px-4 py-3">Severity</th>
                <th className="px-2 sm:px-4 py-3 text-right">Records</th>
                <th className="hidden md:table-cell px-4 py-3 text-right">Direct Cost</th>
                <th className="px-2 sm:px-4 py-3 text-right">At-Risk Pipeline</th>
                <th className="hidden md:table-cell px-4 py-3 text-right">Score Impact</th>
                <th className="px-3 sm:px-5 py-3 text-right">Total Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[--color-border]">
              {punchList.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-6 py-8 text-center text-xs text-[--color-muted-foreground]">
                    No findings detected. Your CRM data is clean!
                  </td>
                </tr>
              ) : (
                punchList.map((item, index) => {
                  const isExpanded = !!expandedRows[item.finding_key];
                  const severityClass = SEVERITY_BADGE_STYLE[item.severity] || SEVERITY_BADGE_STYLE.Low;

                  return (
                    <React.Fragment key={item.finding_key || index}>
                      {/* Main Row */}
                      <tr
                        onClick={() => toggleRow(item.finding_key)}
                        className={`cursor-pointer transition-colors hover:bg-[--color-secondary]/60 ${
                          isExpanded ? 'bg-[--color-secondary]/40' : 'bg-white'
                        }`}
                      >
                        <td className="px-2 sm:px-4 py-3.5 text-center font-mono text-xs text-[--color-muted-foreground]">
                          {index + 1}
                        </td>
                        <td className="px-3 sm:px-5 py-3.5 font-medium text-[--color-foreground]">
                          <div className="flex items-center gap-1.5 sm:gap-2">
                            {isExpanded ? (
                              <ChevronUp className="w-3.5 h-3.5 text-[--color-muted-foreground] shrink-0" />
                            ) : (
                              <ChevronDown className="w-3.5 h-3.5 text-[--color-muted-foreground] shrink-0" />
                            )}
                            <span className="line-clamp-2 sm:line-clamp-none">{item.label}</span>
                          </div>
                        </td>
                        <td className="hidden md:table-cell px-4 py-3.5 text-xs text-[--color-muted-foreground] capitalize">
                          {item.record_type}
                        </td>
                        <td className="px-2 sm:px-4 py-3.5">
                          <span
                            className={`inline-flex items-center px-1.5 sm:px-2 py-0.5 rounded text-[11px] sm:text-xs font-medium border ${SEVERITY_BADGE_STYLE[item.severity] || SEVERITY_BADGE_STYLE.Low}`}
                            style={SEVERITY_BADGE_INLINE[item.severity] || SEVERITY_BADGE_INLINE.Low}
                          >
                            {item.severity}
                          </span>
                        </td>
                        <td className="px-2 sm:px-4 py-3.5 text-right tabular-nums text-[--color-foreground]">
                          {formatNumber(item.affected_count)}
                        </td>
                        <td className="hidden md:table-cell px-4 py-3.5 text-right tabular-nums text-[--color-foreground]">
                          {formatCurrency(item.direct_cost)}
                        </td>
                        <td className={`px-2 sm:px-4 py-3.5 text-right tabular-nums font-medium ${
                          item.at_risk_pipeline > 0 ? 'text-[--color-score-red]' : 'text-[--color-muted-foreground]'
                        }`}>
                          {item.at_risk_pipeline > 0 ? formatCurrency(item.at_risk_pipeline) : '-'}
                        </td>
                        <td className="hidden md:table-cell px-4 py-3.5 text-right tabular-nums font-medium text-[--color-score-green]">
                          {formatScoreImpact(item.score_impact)}
                        </td>
                        <td className="px-3 sm:px-5 py-3.5 text-right tabular-nums font-semibold text-[--color-foreground]">
                          {formatCurrency(item.total_value)}
                        </td>
                      </tr>

                      {/* Expanded Row Detail */}
                      {isExpanded && (
                        <tr className="bg-[--color-secondary]/30 border-b border-[--color-border]">
                          <td colSpan={9} className="px-4 sm:px-6 py-4">
                            <div className="space-y-2">
                              <div className="flex items-center justify-between text-xs text-[--color-muted-foreground] font-medium">
                                <span>
                                  Affected Record IDs ({item.affected_count || item.affected_record_ids?.length || 0}):
                                </span>
                                <span>Remediation est: {item.rep_hours ? `${item.rep_hours} hrs` : 'N/A'}</span>
                              </div>

                              {item.affected_record_ids && item.affected_record_ids.length > 0 ? (
                                <div className="flex flex-wrap gap-1.5 pt-1">
                                  {item.affected_record_ids.map((id) => (
                                    <span
                                      key={id}
                                      className="inline-flex items-center px-2.5 py-1 rounded text-xs font-mono bg-white text-[--color-foreground]"
                                      style={{ border: '1px solid var(--color-border)' }}
                                    >
                                      {id}
                                    </span>
                                  ))}
                                </div>
                              ) : (
                                <p className="text-xs text-[--color-muted-foreground] italic">
                                  No specific record IDs associated.
                                </p>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Row 4 — Export Bar (Pinned to bottom of viewport) */}
      <div className="fixed bottom-0 left-0 right-0 bg-white/95 backdrop-blur-md border-t border-[#E5E5E0] py-3.5 px-4 sm:px-6 z-40">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 sm:gap-4">
          {/* Action description */}
          <div className="hidden md:flex items-center gap-2 text-xs text-[--color-muted-foreground]">
            <Download className="w-4 h-4 text-[--color-primary]" />
            <span className="font-semibold text-[--color-primary]">Export Action Plan:</span>
            <span>Download remediation files ready to fix in CRM</span>
          </div>

          {/* Export buttons */}
          <div className="flex items-center justify-start sm:justify-end gap-2 w-full sm:w-auto overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
            <button
              onClick={() => handleDownload('Ready to Import')}
              className="shrink-0 px-3.5 py-2 rounded-lg border border-[#E5E5E0] bg-white text-[--color-primary] text-xs font-semibold hover:bg-[--color-secondary] transition-colors"
            >
              Ready to Import
            </button>
            <button
              onClick={() => handleDownload('Review First')}
              className="shrink-0 px-3.5 py-2 rounded-lg border border-[#E5E5E0] bg-white text-[--color-primary] text-xs font-semibold hover:bg-[--color-secondary] transition-colors"
            >
              Review First
            </button>
            <button
              onClick={() => handleDownload('Worklist')}
              className="shrink-0 px-3.5 py-2 rounded-lg border border-[#E5E5E0] bg-white text-[--color-primary] text-xs font-semibold hover:bg-[--color-secondary] transition-colors"
            >
              Worklist
            </button>
            <button
              onClick={() => handleDownload('All as ZIP')}
              className="shrink-0 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-[#E5E5E0] bg-white text-[--color-primary] text-xs font-semibold hover:bg-[--color-secondary] transition-colors"
            >
              <Download className="w-3.5 h-3.5 text-[--color-primary]" />
              Download All (ZIP)
            </button>
            {onNext && (
              <button
                onClick={onNext}
                className="shrink-0 inline-flex items-center gap-1 px-3 py-2 rounded-lg text-xs font-medium text-[--color-muted-foreground] hover:text-[--color-primary] transition-colors ml-1"
              >
                Export Details <ArrowRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </div>

    </div>
  );
}
