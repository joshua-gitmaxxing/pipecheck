import React, { useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import DesktopOnlyNotice from '../components/DesktopOnlyNotice';

const STEPS = [
  'Reading records',
  'Running duplicate checks',
  'Running contact checks',
  'Running deal checks',
  'Running company checks',
  'Running routing checks',
  'Scoring records',
  'Calculating cost model',
  'Building punch list',
  'Preparing exports',
];

export default function ProcessingPage({ onComplete }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [isStarted, setIsStarted] = useState(() => {
    if (typeof window !== 'undefined' && window.innerWidth >= 768) {
      return true;
    }
    return false;
  });

  useEffect(() => {
    if (!isStarted) return;

    // 340ms * 10 steps = 3.4 seconds total animation duration
    const interval = setInterval(() => {
      setCurrentStep((s) => {
        if (s >= STEPS.length - 1) {
          clearInterval(interval);
          // Wait 500ms on final step before notifying parent completion
          setTimeout(() => {
            if (onComplete) onComplete();
          }, 500);
          return STEPS.length - 1;
        }
        return s + 1;
      });
    }, 340);

    return () => clearInterval(interval);
  }, [isStarted, onComplete]);

  const progress = Math.round(((currentStep + 1) / STEPS.length) * 100);

  return (
    <DesktopOnlyNotice onContinue={() => setIsStarted(true)}>
      <div className="flex flex-col items-center justify-center min-h-[80vh] px-6 py-12">
        <div className="w-full max-w-md p-8 border border-[--color-border] rounded-2xl bg-white">

          {/* Heading — Instrument Serif */}
          <h2
            className="text-3xl text-[--color-foreground] tracking-tight mb-1 text-center"
            style={{ fontFamily: 'var(--font-display)' }}
          >
            Analysing your CRM…
          </h2>
          <p className="text-xs text-[--color-muted-foreground] mb-8 text-center">
            Running 13 deterministic audit checks with no LLM and no guesswork.
          </p>

          {/* Progress bar — teal fill */}
          <div className="w-full h-1.5 bg-[--color-secondary] rounded-full mb-8 overflow-hidden border border-[--color-border]">
            <div
              className="h-full rounded-full transition-all duration-300 ease-out"
              style={{ width: `${progress}%`, backgroundColor: 'var(--color-primary)' }}
            />
          </div>

          {/* Step list */}
          <ul className="space-y-3">
            {STEPS.map((step, i) => {
              const isDone    = i < currentStep;
              const isRunning = i === currentStep;
              const isQueued  = i > currentStep;

              return (
                <li key={step} className="flex items-center justify-between text-xs transition-colors">
                  <div className="flex items-center gap-2.5">
                    <div
                      className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                        isDone
                          ? 'bg-emerald-50 text-[--color-score-green] border border-emerald-200'
                          : isRunning
                          ? 'text-white font-bold'
                          : 'bg-[--color-secondary] text-[--color-muted-foreground] border border-[--color-border]'
                      }`}
                      style={isRunning ? { backgroundColor: 'var(--color-primary)' } : {}}
                    >
                      {isDone ? (
                        <Check className="w-3 h-3 text-[--color-score-green]" />
                      ) : (
                        i + 1
                      )}
                    </div>
                    <span
                      className={
                        isDone
                          ? 'font-medium text-[--color-foreground]'
                          : isRunning
                          ? 'font-semibold'
                          : 'text-[--color-muted-foreground] opacity-60'
                      }
                      style={isRunning ? { color: 'var(--color-primary)' } : {}}
                    >
                      {step}
                    </span>
                  </div>

                  {isDone && (
                    <span className="text-[11px] font-medium text-[--color-score-green]">
                      Done
                    </span>
                  )}
                  {isRunning && (
                    <span className="text-[11px] font-semibold animate-pulse" style={{ color: 'var(--color-primary)' }}>
                      Running…
                    </span>
                  )}
                  {isQueued && (
                    <span className="text-[11px] text-[--color-muted-foreground] opacity-40">
                      -
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </DesktopOnlyNotice>
  );
}
