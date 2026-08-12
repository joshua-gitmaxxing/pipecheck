import React, { useState } from 'react';

function EcgLogo() {
  return (
    <svg
      viewBox="0 0 48 32"
      className="w-10 h-7 shrink-0 text-[--color-primary]"
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

export default function DesktopOnlyNotice({ children, onContinue }) {
  const [continueAnyway, setContinueAnyway] = useState(false);

  const handleContinue = () => {
    setContinueAnyway(true);
    if (onContinue) {
      onContinue();
    }
  };

  if (continueAnyway) {
    return <>{children}</>;
  }

  return (
    <>
      {/* Mobile-only Notice (< 768px) */}
      <div className="flex md:hidden flex-col items-center justify-center min-h-[60vh] px-6 text-center py-12">
        <div className="p-6 rounded-2xl bg-white border border-[#E5E5E0] flex flex-col items-center max-w-sm w-full shadow-xs">
          <div className="p-3 rounded-xl bg-[--color-secondary] mb-4">
            <EcgLogo />
          </div>
          <h2
            className="text-xl font-semibold text-[--color-foreground] mb-2 tracking-tight"
            style={{ fontFamily: 'var(--font-display)' }}
          >
            Pipecheck is designed for desktop
          </h2>
          <p className="text-xs text-[--color-muted-foreground] leading-relaxed mb-6">
            For the full audit experience, open this on a desktop or laptop browser
          </p>
          <button
            type="button"
            onClick={handleContinue}
            className="text-xs text-[--color-muted-foreground] hover:text-[--color-primary] underline underline-offset-4 transition-colors cursor-pointer"
          >
            or continue anyway →
          </button>
        </div>
      </div>

      {/* Desktop Content (>= 768px) */}
      <div className="hidden md:block">
        {children}
      </div>
    </>
  );
}
