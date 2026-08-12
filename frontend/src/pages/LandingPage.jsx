import React, { useState, useCallback } from 'react';
import { UploadCloud, CheckCircle, Play, FileText, X } from 'lucide-react';

/**
 * Auto-detect CSV object type based on column headers or filename fallback.
 */
async function detectFileType(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result || '';
      const firstLine = text.split(/\r?\n/)[0] || '';
      // Clean headers
      const headers = firstLine
        .split(',')
        .map((h) => h.trim().replace(/^["']|["']$/g, '').toLowerCase());

      const fileNameLower = file.name.toLowerCase();

      // Check header content
      const hasEmail = headers.some((h) => h.includes('email'));
      const hasCompanyDomain = headers.some(
        (h) => h.includes('domain') || h.includes('company name') || h.includes('company domain')
      );
      const hasDealName = headers.some(
        (h) => h.includes('deal name') || h.includes('amount') || h.includes('deal stage')
      );

      // Classification priority
      if (hasEmail || fileNameLower.includes('contact')) {
        resolve({ type: 'contacts', file });
      } else if (hasCompanyDomain || fileNameLower.includes('compan')) {
        resolve({ type: 'companies', file });
      } else if (hasDealName || fileNameLower.includes('deal')) {
        resolve({ type: 'deals', file });
      } else {
        // Default fallback based on filename or unknown
        resolve({ type: 'unknown', file });
      }
    };
    // Read first 4KB to parse header line
    reader.readAsText(file.slice(0, 4096));
  });
}

export default function LandingPage({ onUploadConfig, onTrySample }) {
  const [detectedFiles, setDetectedFiles] = useState({
    contacts: null,
    companies: null,
    deals: null,
  });
  const [isDragging, setIsDragging] = useState(false);
  const [isProcessingSample, setIsProcessingSample] = useState(false);

  // Process incoming files from input or drop
  const handleFiles = async (fileList) => {
    if (!fileList || fileList.length === 0) return;

    const filesArray = Array.from(fileList);
    const updated = { ...detectedFiles };

    for (const file of filesArray) {
      if (!file.name.toLowerCase().endsWith('.csv')) continue;

      const result = await detectFileType(file);
      if (result.type !== 'unknown') {
        updated[result.type] = file;
      } else {
        // If unknown, default to contacts if not set, else companies, else deals
        if (!updated.contacts) updated.contacts = file;
        else if (!updated.companies) updated.companies = file;
        else if (!updated.deals) updated.deals = file;
      }
    }

    setDetectedFiles(updated);
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  }, [detectedFiles]);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleFileInputChange = (e) => {
    if (e.target.files) {
      handleFiles(e.target.files);
    }
  };

  const removeFile = (type) => {
    setDetectedFiles((prev) => ({
      ...prev,
      [type]: null,
    }));
  };

  const hasContacts = !!detectedFiles.contacts;

  const handleConfigureClick = () => {
    if (hasContacts && onUploadConfig) {
      onUploadConfig(detectedFiles);
    }
  };

  const handleSampleClick = async () => {
    setIsProcessingSample(true);
    try {
      await onTrySample();
    } finally {
      setIsProcessingSample(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[75vh] sm:min-h-[80vh] text-center px-4 sm:px-6 py-8 sm:py-12">

      {/* Display heading — Instrument Serif */}
      <h1
        className="text-4xl sm:text-5xl md:text-6xl tracking-tight text-[--color-foreground] mb-4 leading-tight"
        style={{ fontFamily: 'var(--font-display)' }}
      >
        Your CRM is messy.<br />
        <em>Here's what it's costing you.</em>
      </h1>

      <p className="text-xs sm:text-base text-[--color-muted-foreground] max-w-xs sm:max-w-lg mb-6 sm:mb-10 leading-relaxed px-2 sm:px-0">
        Upload your HubSpot CSV export. Pipecheck returns a health score, a dollar-quantified cost breakdown, and a prioritised punch list in seconds.
      </p>

      {/* Drop zone */}
      <div className="w-full max-w-xl mb-6">
        <label
          htmlFor="csv-upload"
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          className={`block w-full cursor-pointer group transition-all duration-200 ${
            isDragging ? 'scale-[1.01]' : ''
          }`}
        >
          <div
            className={`flex flex-col items-center justify-center gap-3 sm:gap-4 px-6 sm:px-8 py-8 sm:py-12 border-2 border-dashed border-[#E5E5E0] rounded-2xl transition-colors duration-200 ${
              isDragging
                ? 'bg-[--color-secondary]'
                : 'bg-[#EFEFEA]'
            }`}
            style={isDragging ? { borderColor: 'var(--color-primary)' } : {}}
          >
            <div
              className="p-3 sm:p-3.5 rounded-full transition-colors duration-200"
              style={{
                backgroundColor: isDragging ? 'var(--color-primary)' : 'var(--color-secondary)',
              }}
            >
              <UploadCloud
                className="w-5 h-5 sm:w-6 sm:h-6 transition-colors duration-200"
                style={{ color: isDragging ? '#fff' : 'var(--color-muted-foreground)' }}
              />
            </div>
            <div>
              <p className="hidden md:block font-semibold text-[--color-foreground] text-sm">
                Drag & drop your HubSpot CSV exports
              </p>
              <p className="block md:hidden font-semibold text-[--color-foreground] text-sm">
                Tap to upload CSV exports
              </p>
              <p className="text-xs text-[--color-muted-foreground] mt-1">
                Upload Contacts, Companies, and Deals CSVs · Auto-detected
              </p>
            </div>
          </div>
          <input
            id="csv-upload"
            type="file"
            multiple
            accept=".csv"
            className="hidden"
            onChange={handleFileInputChange}
          />
        </label>
      </div>

      {/* Confirmation chips for detected files */}
      <div className="w-full max-w-xl mb-8">
        {(detectedFiles.contacts || detectedFiles.companies || detectedFiles.deals) ? (
          <div className="flex flex-wrap items-center justify-center gap-2 sm:gap-2.5 p-3 sm:p-4 border border-[--color-border] rounded-xl bg-white">
            <span className="text-xs text-[--color-muted-foreground] font-medium mr-1">
              Detected Files:
            </span>

            {/* Contacts Chip */}
            {detectedFiles.contacts && (
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-medium">
                <CheckCircle className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                <span className="truncate max-w-[140px]" title={detectedFiles.contacts.name}>
                  {detectedFiles.contacts.name}
                </span>
                <span className="text-[10px] text-emerald-600 font-mono">(Contacts)</span>
                <button
                  type="button"
                  onClick={() => removeFile('contacts')}
                  className="hover:opacity-75 text-emerald-700 ml-0.5"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            )}

            {/* Companies Chip */}
            {detectedFiles.companies && (
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-medium">
                <CheckCircle className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                <span className="truncate max-w-[140px]" title={detectedFiles.companies.name}>
                  {detectedFiles.companies.name}
                </span>
                <span className="text-[10px] text-emerald-600 font-mono">(Companies)</span>
                <button
                  type="button"
                  onClick={() => removeFile('companies')}
                  className="hover:opacity-75 text-emerald-700 ml-0.5"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            )}

            {/* Deals Chip */}
            {detectedFiles.deals && (
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-medium">
                <CheckCircle className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                <span className="truncate max-w-[140px]" title={detectedFiles.deals.name}>
                  {detectedFiles.deals.name}
                </span>
                <span className="text-[10px] text-emerald-600 font-mono">(Deals)</span>
                <button
                  type="button"
                  onClick={() => removeFile('deals')}
                  className="hover:opacity-75 text-emerald-700 ml-0.5"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-[--color-muted-foreground]">
            No CSV files selected yet. Drag & drop files or click to browse.
          </p>
        )}
      </div>

      {/* Actions */}
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3 w-full max-w-xs sm:max-w-none">
        {/* Upload & Configure CTA (Visible when contacts CSV is detected) */}
        {hasContacts && (
          <button
            onClick={handleConfigureClick}
            className="inline-flex items-center justify-center gap-2 px-6 py-2.5 rounded-lg bg-[--color-primary] text-[--color-primary-foreground] text-sm font-medium hover:opacity-85 transition-opacity shadow-xs w-full sm:w-auto"
          >
            Upload &amp; Configure →
          </button>
        )}

        {/* Try sample data button (Routes DIRECTLY to Results screen) */}
        <button
          onClick={handleSampleClick}
          disabled={isProcessingSample}
          className="inline-flex items-center justify-center gap-1.5 sm:gap-2 px-3.5 sm:px-5 py-1.5 sm:py-2.5 rounded-lg border border-[--color-border] bg-white text-[--color-foreground] text-xs sm:text-sm font-medium hover:bg-[--color-secondary] transition-colors disabled:opacity-50 w-auto self-center sm:self-auto"
        >
          <Play className="w-3 h-3 sm:w-3.5 sm:h-3.5 fill-current" />
          {isProcessingSample ? 'Loading sample data…' : 'Try sample data'}
        </button>
      </div>

    </div>
  );
}
