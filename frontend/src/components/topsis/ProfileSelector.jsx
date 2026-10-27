import React from 'react';
import { BALANCED_PERCENT, CRITERIA, PROFILE_OPTIONS, normalisePercent, validateCustomPercent } from '../../utils/topsisView';

/**
 * Ranking-profile picker with the custom weight builder. Controlled:
 * `profile` is a PROFILE_OPTIONS value, `customPercent` maps every
 * criterion to a 0-100 weight (used only for 'custom').
 *
 * `profiles` (optional) is GET /api/topsis/profiles' list; its summaries
 * replace the built-in ones when available.
 */
export default function ProfileSelector({ profile, onProfileChange, customPercent, onCustomChange, profiles, compact = false }) {
  const summaries = Object.fromEntries((profiles || []).map((p) => [p.profile, p.summary]));
  const check = validateCustomPercent(customPercent);

  const setWeight = (key, value) => onCustomChange({ ...customPercent, [key]: value === '' ? 0 : Number(value) });

  return (
    <fieldset className="space-y-3">
      <legend className="block font-label-sm text-label-sm text-on-surface-variant mb-1 font-semibold">Ranking profile</legend>
      <div className={`grid gap-2 ${compact ? 'grid-cols-2 sm:grid-cols-3' : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'}`} role="radiogroup">
        {PROFILE_OPTIONS.map((p) => {
          const selected = p.value === profile;
          return (
            <label
              key={p.value}
              className={`flex items-start gap-2 rounded-lg border px-3 py-2 cursor-pointer transition-colors ${
                selected ? 'border-primary bg-primary/5' : 'border-outline-variant hover:bg-surface-container-low'}`}
            >
              <input
                type="radio"
                name="ranking-profile"
                value={p.value}
                checked={selected}
                onChange={() => onProfileChange(p.value)}
                className="mt-1 accent-[#1f6b3a]"
              />
              <span>
                <span className="block text-sm font-semibold text-on-surface">{p.label}</span>
                {!compact && <span className="block text-xs text-on-surface-variant">{summaries[p.value] || p.summary}</span>}
              </span>
            </label>
          );
        })}
      </div>

      {profile === 'custom' && (
        <div className="rounded-lg border border-outline-variant/60 p-3 space-y-2" aria-label="Custom weights">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-on-surface-variant">Give each criterion a weight. The weights must add up to 100%.</p>
            <div className="flex gap-2">
              <button type="button" onClick={() => onCustomChange(normalisePercent(customPercent))}
                className="text-xs font-semibold text-primary border border-outline-variant rounded-full px-3 py-1 hover:bg-surface-container-low cursor-pointer">
                Scale to 100%
              </button>
              <button type="button" onClick={() => onCustomChange({ ...BALANCED_PERCENT })}
                className="text-xs font-semibold text-on-surface-variant border border-outline-variant rounded-full px-3 py-1 hover:bg-surface-container-low cursor-pointer">
                Reset to Balanced
              </button>
            </div>
          </div>
          {CRITERIA.map((c) => {
            const value = Number(customPercent?.[c.key] ?? 0);
            return (
              <div key={c.key} className="grid grid-cols-[minmax(0,9rem)_1fr_4.5rem] items-center gap-2">
                <label htmlFor={`w-${c.key}`} className="text-xs text-on-surface">
                  {c.label} <span className="text-on-surface-variant">({c.direction === 'benefit' ? 'higher is better' : 'lower is better'})</span>
                </label>
                <input id={`w-${c.key}`} type="range" min="0" max="100" step="1" value={Math.round(value)}
                  onChange={(e) => setWeight(c.key, e.target.value)} className="w-full accent-[#1f6b3a]" />
                <input type="number" min="0" max="100" step="0.1" aria-label={`${c.label} weight (%)`}
                  value={Number.isInteger(value) ? value : value.toFixed(1)}
                  onChange={(e) => setWeight(c.key, e.target.value)}
                  className="h-8 px-2 rounded border border-outline-variant bg-surface-bright text-sm text-right" />
              </div>
            );
          })}
          <p className={`text-xs font-semibold ${check.valid ? 'text-primary' : 'text-error'}`} role="status">
            Total {check.total.toFixed(1)}%{check.valid ? ' ✓' : ` – ${check.errors.join(' ')}`}
          </p>
        </div>
      )}
    </fieldset>
  );
}
