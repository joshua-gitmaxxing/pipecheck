import React from 'react';
import { Download, CheckCircle, AlertCircle, FileText, Archive, ArrowLeft } from 'lucide-react';
import DesktopOnlyNotice from '../components/DesktopOnlyNotice';

export default function ExportPage({ onReset }) {
  const triggerDownload = async (fileType) => {
    try {
      const endpoint =
        fileType === 'zip'
          ? 'http://localhost:8000/api/export/zip'
          : `http://localhost:8000/api/export?file_type=${fileType}`;

      const res = await fetch(endpoint, { method: 'POST' });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download =
          fileType === 'zip'
            ? 'pipecheck_exports.zip'
            : fileType === 'blue'
            ? 'blue.txt'
            : `${fileType}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } else {
        console.error('Failed to download file:', res.statusText);
      }
    } catch (err) {
      console.error('Export download error:', err);
    }
  };

  const EXPORTS = [
    {
      type: 'green',
      icon: CheckCircle,
      badge: 'Ready to import',
      badgeStyle: {
        background: 'var(--color-badge-green-bg)',
        color: 'var(--color-badge-green-text)',
        borderColor: 'var(--color-badge-green-text)',
      },
      title: 'Mechanical fixes (green.csv)',
      desc: 'Formatting corrections only, including whitespace and standardized country names. Includes Record ID + changed columns only. Excludes duplicate merge candidates.',
      btnLabel: 'Download',
    },
    {
      type: 'yellow',
      icon: AlertCircle,
      badge: 'Review first',
      badgeStyle: {
        background: 'var(--color-badge-amber-bg)',
        color: 'var(--color-badge-amber-text)',
        borderColor: 'var(--color-badge-amber-text)',
      },
      title: 'Inferred fixes (yellow.csv)',
      desc: 'Probable domain typos and inferred values with current value and proposed value side by side. Never pre-applied.',
      btnLabel: 'Download',
    },
    {
      type: 'blue',
      icon: FileText,
      badge: 'Worklist',
      badgeStyle: {
        background: 'var(--color-badge-blue-bg)',
        color: 'var(--color-badge-blue-text)',
        borderColor: 'var(--color-badge-blue-text)',
      },
      title: 'Manual action items (blue.txt)',
      desc: 'Duplicate merges, account reassignments, dead deal decisions. Checklist grouped by finding type, not importable directly.',
      btnLabel: 'Download',
    },
  ];

  return (
    <DesktopOnlyNotice>
      <div className="max-w-4xl mx-auto py-12 px-6 pb-24">

        <h1
          className="text-4xl tracking-tight text-[--color-foreground] mb-2"
          style={{ fontFamily: 'var(--font-display)' }}
        >
          Download your audit outputs
        </h1>
        <p className="text-sm text-[--color-muted-foreground] mb-10 max-w-xl">
          Three separate files, never mixed. Each serves a distinct purpose in the CRM cleanup workflow.
        </p>

        {/* Three export cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
          {EXPORTS.map((e) => {
            const Icon = e.icon;
            return (
              <div
                key={e.title}
                className="flex flex-col bg-white p-5"
                style={{ border: '1px solid var(--color-border)', borderRadius: 'var(--radius-card)' }}
              >
                <div className="mb-4">
                  <span
                    className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded border"
                    style={e.badgeStyle}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    {e.badge}
                  </span>
                </div>
                <p className="text-sm font-semibold text-[--color-foreground] mb-1.5">{e.title}</p>
                <p className="text-xs text-[--color-muted-foreground] leading-relaxed flex-1 mb-6">{e.desc}</p>
                <button
                  onClick={() => triggerDownload(e.type)}
                  className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-xs font-medium transition-opacity hover:opacity-85 text-[--color-primary-foreground]"
                  style={{ backgroundColor: 'var(--color-primary)' }}
                >
                  <Download className="w-3.5 h-3.5" />
                  {e.btnLabel}
                </button>
              </div>
            );
          })}
        </div>

        {/* ZIP bundle row */}
        <div
          className="flex flex-col sm:flex-row items-center justify-between gap-4 p-6 mb-10"
          style={{ background: 'var(--color-secondary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-card)' }}
        >
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-lg bg-white" style={{ border: '1px solid var(--color-border)' }}>
              <Archive className="w-6 h-6 text-[--color-foreground]" />
            </div>
            <div>
              <p className="text-sm font-semibold text-[--color-foreground]">Download complete audit bundle</p>
              <p className="text-xs text-[--color-muted-foreground] mt-0.5">All three files (green.csv, yellow.csv, blue.txt) as a single ZIP archive</p>
            </div>
          </div>
          <button
            onClick={() => triggerDownload('zip')}
            className="shrink-0 inline-flex items-center gap-2 px-6 py-3 rounded-lg text-xs font-semibold hover:opacity-85 transition-opacity text-[--color-primary-foreground]"
            style={{ backgroundColor: 'var(--color-primary)' }}
          >
            <Archive className="w-4 h-4" /> Download all (ZIP)
          </button>
        </div>

        <div className="flex items-center justify-between border-t border-[--color-border] pt-6">
          <button
            onClick={onReset}
            className="inline-flex items-center gap-1.5 text-xs text-[--color-muted-foreground] hover:text-[--color-foreground] transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Start a new audit
          </button>
        </div>

      </div>
    </DesktopOnlyNotice>
  );
}
