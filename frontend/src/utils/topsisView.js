/**
 * Formatting and validation for the dynamic TOPSIS ranking
 * (backend: app/decision/profiles.py, app/services/topsis_service.py).
 *
 * The backend is the authority on weights and scores; these helpers only
 * turn its payloads into rows for tables and charts, and check the custom
 * weight builder before a request is sent (the backend checks again).
 */

/** Fallbacks so the selector renders before GET /api/topsis/profiles answers. */
export const PROFILE_OPTIONS = [
  { value: 'balanced', label: 'Balanced', summary: 'The published ranking: yield against the three footprint objectives.' },
  { value: 'profit', label: 'Profit priority', summary: 'Favours income, crop price and yield.' },
  { value: 'water', label: 'Water saving', summary: 'Favours low irrigation water and low environmental impact.' },
  { value: 'sustainability', label: 'Sustainability', summary: 'Favours low impact, low water use and crops that suit the soil.' },
  { value: 'low_cost', label: 'Low cost', summary: 'Favours low production cost and budget headroom.' },
  { value: 'custom', label: 'Custom', summary: 'Set your own weight for each criterion.' },
];

export const CRITERIA = [
  { key: 'yield', label: 'Yield', direction: 'benefit' },
  { key: 'market_price', label: 'Market price', direction: 'benefit' },
  { key: 'income', label: 'Income', direction: 'benefit' },
  { key: 'cost', label: 'Production cost', direction: 'cost' },
  { key: 'water', label: 'Water', direction: 'cost' },
  { key: 'env', label: 'Environmental impact', direction: 'cost' },
  { key: 'budget', label: 'Budget', direction: 'benefit' },
  { key: 'soil', label: 'Soil suitability', direction: 'benefit' },
  { key: 'land', label: 'Land use', direction: 'benefit' },
  { key: 'rainfall', label: 'Rainfall exposure', direction: 'cost' },
];

/** Balanced weights in percent (yield 30, cost/water/env 23.33 each). */
export const BALANCED_PERCENT = { yield: 30, cost: 70 / 3, water: 70 / 3, env: 70 / 3 };

const LABELS = Object.fromEntries(CRITERIA.map((c) => [c.key, c.label]));
export const criterionLabel = (key) => LABELS[key] || key;
export const profileLabel = (value) => PROFILE_OPTIONS.find((p) => p.value === value)?.label || value;

/** Custom-builder state (percent per criterion) -> validation result. */
export function validateCustomPercent(percent) {
  const entries = CRITERIA.map((c) => [c.key, Number(percent?.[c.key] ?? 0)]);
  const bad = entries.filter(([, v]) => !Number.isFinite(v) || v < 0 || v > 100).map(([k]) => criterionLabel(k));
  const total = entries.reduce((s, [, v]) => s + (Number.isFinite(v) ? v : 0), 0);
  const errors = [];
  if (bad.length) errors.push(`Each weight must be between 0 and 100% (${bad.join(', ')}).`);
  if (Math.abs(total - 100) > 0.01) errors.push(`Weights must add up to 100% (they add up to ${total.toFixed(1)}%).`);
  return { valid: errors.length === 0, total, errors };
}

/** Percent per criterion -> fractions summing to exactly 1 (zeros left out). */
export function toFractions(percent) {
  const entries = CRITERIA.map((c) => [c.key, Number(percent?.[c.key] ?? 0)]).filter(([, v]) => v > 0);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  if (total <= 0) return {};
  const out = Object.fromEntries(entries.map(([k, v]) => [k, Number((v / total).toFixed(6))]));
  // Put the rounding remainder on the largest weight so the sum is exactly 1.
  const drift = 1 - Object.values(out).reduce((s, v) => s + v, 0);
  const largest = entries.reduce((a, b) => (b[1] > a[1] ? b : a))[0];
  out[largest] = Number((out[largest] + drift).toFixed(6));
  return out;
}

/** Rescale the builder so it adds up to 100% (keeps the proportions). */
export function normalisePercent(percent) {
  const total = CRITERIA.reduce((s, c) => s + Math.max(0, Number(percent?.[c.key] ?? 0) || 0), 0);
  if (total <= 0) return { ...BALANCED_PERCENT };
  return Object.fromEntries(CRITERIA.map((c) => [c.key, Math.round((Math.max(0, Number(percent?.[c.key] ?? 0) || 0) / total) * 1000) / 10]));
}

/** {criterion: weight} -> rows with a positive weight, largest first. */
export function weightRows(weights) {
  return CRITERIA.filter((c) => (weights?.[c.key] ?? 0) > 0)
    .map((c) => ({ key: c.key, label: c.label, direction: c.direction, weight: weights[c.key], percent: weights[c.key] * 100 }))
    .sort((a, b) => b.weight - a.weight);
}

const pct = (v) => `${(v * 100).toFixed(1)}%`;

export function formatCriterionValue(row) {
  const v = row.value;
  if (v === null || v === undefined) return '–';
  switch (row.criterion) {
    case 'cost': case 'income': case 'budget':
      return `₹${Math.round(v).toLocaleString('en-IN')}`;
    case 'market_price':
      return `₹${Math.round(v).toLocaleString('en-IN')}/qtl`;
    case 'water':
      return `${(v / 1e6).toFixed(2)} ML`;
    case 'yield':
      return `${v.toFixed(2)} t`;
    case 'soil': case 'land': case 'rainfall':
      return v.toFixed(2);
    default:
      return v.toFixed(2);
  }
}

/** One plan's weight -> contribution -> score chain as table rows. */
export function contributionRows(planTerms) {
  return (planTerms?.criteria || []).map((r) => ({
    key: r.criterion,
    label: r.label,
    weight: pct(r.weight),
    value: formatCriterionValue(r),
    goodness: r.goodness.toFixed(2),
    weighted: r.weighted.toFixed(3),
    gap: `${r.share_of_distance_to_ideal_pct.toFixed(0)}%`,
  }));
}

/** Short crop mix text, e.g. "Tapioca 91%, Groundnut 5%". */
export function cropMixText(mix) {
  return (mix || []).map((c) => `${c.crop} ${Math.round(c.share_pct)}%`).join(', ');
}

/** Comparison payload -> one row per profile (best plan, overlap, tau). */
export function profileComparisonRows(comparison) {
  return (comparison?.profiles || []).map((p) => ({
    profile: p.profile,
    label: p.label,
    bestPlan: cropMixText(p.best_plan.crop_mix),
    bestScore: p.best_plan.closeness,
    bestRankUnderReference: p.best_plan.rank_under_reference,
    referenceTopRank: p.reference_top_plan_rank,
    tau: p.kendall_tau_vs_reference,
    overlap: `${p.top_n_overlap}/${comparison.top_n}`,
    isReference: p.profile === comparison.reference,
  }));
}

/** Rank of each of the reference profile's top plans under every profile. */
export function rankChangeRows(comparison) {
  const names = (comparison?.profiles || []).map((p) => p.profile);
  return (comparison?.rank_changes || []).map((r) => ({
    plan: `#${r.reference_rank} ${cropMixText(r.crop_mix)}`,
    referenceRank: r.reference_rank,
    ranks: names.map((n) => ({ profile: n, rank: r.ranks[n], change: r.ranks[n] - r.reference_rank })),
  }));
}

/** Weight of each criterion under every profile, as grouped chart categories. */
export function weightDifferenceRows(comparison) {
  const ref = comparison?.profiles?.find((p) => p.profile === comparison.reference);
  if (!ref) return [];
  return CRITERIA.map((c) => ({
    key: c.key,
    label: c.label,
    reference: ref.weights[c.key] * 100,
    byProfile: Object.fromEntries(comparison.profiles.map((p) => [p.profile, p.weights[c.key] * 100])),
  })).filter((r) => Object.values(r.byProfile).some((v) => v > 0));
}

export function signedRankChange(change) {
  if (change === 0) return '=';
  return change > 0 ? `↓${change}` : `↑${-change}`;
}
