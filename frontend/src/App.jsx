import React, { useState, useEffect } from 'react';
import { Menu, X } from 'lucide-react';
import LandingPage from './pages/LandingPage';
import ConfigPage from './pages/ConfigPage';
import ProcessingPage from './pages/ProcessingPage';
import ResultsPage from './pages/ResultsPage';
import ExportPage from './pages/ExportPage';

const SCREENS = [
  { id: 'landing',    label: 'Upload' },
  { id: 'config',     label: 'Configure' },
  { id: 'processing', label: 'Processing' },
  { id: 'results',    label: 'Results' },
  { id: 'export',     label: 'Export' },
];

function EcgLogo() {
  return (
    <svg
      viewBox="0 0 48 32"
      className="w-[36px] h-[24px] md:w-[48px] md:h-[32px] shrink-0 text-[--color-primary]"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M2 16h10l3-5 4 15 5-22 5 22 4-12 3 2h10" />
    </svg>
  );
}

export default function App() {
  const [activeScreen, setActiveScreen] = useState('landing');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState({
    contacts: null,
    companies: null,
    deals: null,
  });
  const [auditData, setAuditData] = useState(null);
  const [isLoadingAudit, setIsLoadingAudit] = useState(false);

  // Direct sample audit call — skips config & processing, goes directly to results
  const handleTrySample = async () => {
    setIsLoadingAudit(true);
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/audit/sample`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        setAuditData(data);
        setActiveScreen('results'); // Direct to results per brief
      } else {
        console.error('Failed to fetch sample audit data:', res.statusText);
      }
    } catch (err) {
      console.error('Error fetching sample audit data:', err);
    } finally {
      setIsLoadingAudit(false);
    }
  };

  // Called when user selects/drops files on Landing page and clicks "Upload & Configure →"
  const handleUploadConfig = (files) => {
    setUploadedFiles(files);
    setActiveScreen('config');
  };

  // Called from Config page when user clicks "Run Audit →"
  const handleRunAudit = async (customConfig) => {
    // 1. Immediately switch to processing screen
    setActiveScreen('processing');

    try {
      const formData = new FormData();

      if (uploadedFiles.contacts) {
        formData.append('contacts', uploadedFiles.contacts);
      }
      if (uploadedFiles.companies) {
        formData.append('companies', uploadedFiles.companies);
      }
      if (uploadedFiles.deals) {
        formData.append('deals', uploadedFiles.deals);
      }

      if (customConfig) {
        formData.append('config', JSON.stringify(customConfig));
      }

      let endpoint = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/audit`;
      // If user did not upload a custom contacts file, use sample audit endpoint with custom config
      if (!uploadedFiles.contacts) {
        endpoint = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/audit/sample`;
      }

      const res = await fetch(endpoint, {
        method: 'POST',
        body: uploadedFiles.contacts ? formData : (customConfig ? new URLSearchParams({ config: JSON.stringify(customConfig) }) : null),
      });

      if (res.ok) {
        const data = await res.json();
        setAuditData(data);
      } else {
        console.error('Audit execution error:', res.statusText);
        // Fallback if custom post fails
        await handleTrySample();
      }
    } catch (err) {
      console.error('Error executing audit:', err);
      // Fallback
      await handleTrySample();
    }
  };

  // Pre-load sample data if user navigates to Results tab directly without prior state
  useEffect(() => {
    if (activeScreen === 'results' && !auditData && !isLoadingAudit) {
      handleTrySample();
    }
  }, [activeScreen, auditData, isLoadingAudit]);

  return (
    <div className="min-h-screen flex flex-col bg-[--color-background] text-[--color-foreground]">

      {/* Backdrop overlay for mobile menu */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/10 md:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Floating Card Header */}
      <header className="sticky top-4 z-50 max-w-6xl mx-auto w-full px-4 sm:px-6 mt-4">
        <div className="bg-white border border-[#E5E5E0] rounded-xl px-4 sm:px-6 py-2.5 sm:py-3 flex items-center justify-between shadow-xs">
          {/* Logo & Wordmark — deep teal */}
          <div className="flex items-center gap-2 sm:gap-3">
            <EcgLogo />
            <span
              className="font-display text-xl md:text-2xl tracking-tight"
              style={{ fontFamily: 'var(--font-display)', color: 'var(--color-primary)' }}
            >
              Pipecheck
            </span>
          </div>

          {/* Desktop Screen Tabs */}
          <nav className="hidden md:flex items-center gap-1">
            {SCREENS.map((screen) => {
              const isActive = activeScreen === screen.id;
              return (
                <button
                  key={screen.id}
                  onClick={() => setActiveScreen(screen.id)}
                  className={`px-3 py-1.5 text-xs font-medium transition-all whitespace-nowrap border-b-2 ${
                    isActive
                      ? 'border-[--color-primary] text-[--color-primary]'
                      : 'border-transparent text-[--color-muted-foreground] hover:text-[--color-foreground]'
                  }`}
                >
                  {screen.label}
                </button>
              );
            })}
          </nav>

          {/* Mobile Hamburger Toggle Button */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen((prev) => !prev)}
            className="md:hidden p-1.5 rounded-lg border border-[#E5E5E0] text-[--color-primary] hover:bg-[--color-secondary] transition-colors"
            aria-label="Toggle navigation menu"
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>

        {/* Mobile Dropdown Menu */}
        {mobileMenuOpen && (
          <div className="md:hidden mt-2 p-2 bg-white border border-[#E5E5E0] rounded-xl shadow-lg flex flex-col gap-1">
            {SCREENS.map((screen) => {
              const isActive = activeScreen === screen.id;
              return (
                <button
                  key={screen.id}
                  onClick={() => {
                    setActiveScreen(screen.id);
                    setMobileMenuOpen(false);
                  }}
                  className="px-4 py-2 text-xs font-medium transition-all text-left w-full hover:text-[--color-foreground]"
                >
                  <span
                    className={`inline-block border-b-2 ${
                      isActive
                        ? 'border-[--color-primary] text-[--color-primary]'
                        : 'border-transparent text-[--color-muted-foreground]'
                    }`}
                  >
                    {screen.label}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </header>

      {/* Page body */}
      <main className="flex-1">
        {activeScreen === 'landing'    && <LandingPage    onUploadConfig={handleUploadConfig} onTrySample={handleTrySample} />}
        {activeScreen === 'config'     && <ConfigPage     uploadedFiles={uploadedFiles} onBack={() => setActiveScreen('landing')} onNext={handleRunAudit} />}
        {activeScreen === 'processing' && <ProcessingPage onComplete={() => setActiveScreen('results')} />}
        {activeScreen === 'results'    && <ResultsPage    auditData={auditData} onNext={() => setActiveScreen('export')} />}
        {activeScreen === 'export'     && <ExportPage     onReset={() => setActiveScreen('landing')} />}
      </main>

      {/* Footer */}
      <footer className="border-t border-[#E5E5E0] py-5 text-center text-[10px] sm:text-xs text-[--color-muted-foreground] px-4">
        Pipecheck - Portable HubSpot CRM Audit Engine &nbsp;·&nbsp; Zero LLM &nbsp;·&nbsp; In-Session Only
      </footer>
    </div>
  );
}
