import React from 'react';

/** Placeholder shown while a page's chunk loads. */
export default function ViewLoading({ fullScreen = false }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex items-center justify-center gap-3 text-on-surface-variant font-label-md text-label-md ${fullScreen ? 'min-h-screen' : 'py-24'}`}
    >
      <span className="material-symbols-outlined animate-spin text-primary" aria-hidden="true">progress_activity</span>
      Loading…
    </div>
  );
}
