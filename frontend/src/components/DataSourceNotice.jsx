import React from 'react';

/**
 * Small inline banner shown on Home / Analytics / Comparison, making clear
 * that the numbers on that page are generic, district-level information --
 * not a personalized result saved to the user's own history. One shared
 * copy so every page explains the distinction the same way:
 *
 *   Historical District Data -- from historical datasets, used for
 *     analysis/trends/reference, not personalized.
 *   Optimization Results -- generated live by NSGA-II, personalized to
 *     the inputs you choose, saved to your History, usable in Reports.
 *
 * variant="historical" -- Home's KPI cards: plain historical averages
 *   (yield/soil/water/crop-mix) straight from the district's records.
 * variant="live" -- Analytics/Comparison: a real NSGA-II run, computed
 *   fresh on this visit, but still generic to the district -- not saved,
 *   not scoped to the user's own inputs.
 */
export default function DataSourceNotice({ location, variant = 'historical', onRunOptimization }) {
  const copy = variant === 'live'
    ? `Live optimization for ${location} -- recalculated fresh each time you open this page. Not personalized to you and not saved to your history.`
    : `Historical district data for ${location} -- reference figures from past seasons, not personalized to you.`;

  return (
    <div className="mb-6 font-label-sm text-label-sm bg-surface-container-high text-on-surface-variant px-4 py-3 rounded-lg flex flex-col sm:flex-row sm:items-center gap-3">
      <span className="flex items-start gap-2 flex-1">
        <span className="material-symbols-outlined text-[16px] mt-0.5 flex-shrink-0">info</span>
        <span>{copy} Personalized results that are saved to your History come from Run Optimization.</span>
      </span>
      {onRunOptimization && (
        <button
          onClick={onRunOptimization}
          className="flex-shrink-0 self-start sm:self-center px-4 py-1.5 rounded-full border border-primary text-primary font-label-sm text-label-sm hover:bg-primary/10 transition-colors cursor-pointer font-semibold whitespace-nowrap"
        >
          Run Optimization
        </button>
      )}
    </div>
  );
}
