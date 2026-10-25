/**
 * Formatting of a run's Pareto-front quality metrics (backend:
 * app/optimization/metrics.py, returned as meta.quality_metrics). Nothing is
 * computed here; a missing value is shown as "n/a".
 */

const num = (v, digits = 3) => (v === null || v === undefined ? 'n/a' : Number(v).toFixed(digits));
const pct = (v) => (v === null || v === undefined ? 'n/a' : `${(Number(v) * 100).toFixed(1)}%`);

/** Rows for display: label, formatted value and what "good" means. */
export function qualityRows(q) {
  if (!q) return [];
  return [
    { key: 'hypervolume_ratio', label: 'Hypervolume ratio', value: num(q.hypervolume_ratio), hint: 'share of the reference front covered; 1 = converged' },
    { key: 'hypervolume', label: 'Hypervolume', value: num(q.hypervolume, 4), hint: 'normalised, higher is better' },
    { key: 'gd', label: 'Generational distance (GD)', value: num(q.gd), hint: 'distance to the reference front, lower is better' },
    { key: 'igd', label: 'Inverted generational distance (IGD)', value: num(q.igd), hint: 'lower is better' },
    { key: 'igd_plus', label: 'IGD+', value: num(q.igd_plus), hint: 'lower is better' },
    { key: 'spread', label: 'Spread', value: num(q.spread), hint: 'lower = more evenly spread' },
    { key: 'spacing', label: 'Spacing', value: num(q.spacing), hint: 'lower = more evenly spaced' },
    { key: 'pareto_size', label: 'Pareto solutions', value: `${q.feasible_pareto_size} feasible of ${q.pareto_size}`, hint: '' },
    { key: 'constraint_satisfaction_rate', label: 'Constraint satisfaction', value: pct(q.constraint_satisfaction_rate), hint: 'final population within budget' },
    { key: 'dominated_by_lower_bound_copy', label: 'Beaten by lower-input copy', value: pct(q.dominated_by_lower_bound_copy), hint: 'lower is better' },
    { key: 'runtime_seconds', label: 'Runtime', value: q.runtime_seconds === null || q.runtime_seconds === undefined ? 'n/a' : `${Number(q.runtime_seconds).toFixed(2)} s`, hint: `${q.generations ?? 'n/a'} generations, ${q.evaluations ?? 'n/a'} evaluations` },
  ];
}

/** The four headline metrics shown on a report card. */
export function headlineQuality(q) {
  const keys = ['hypervolume_ratio', 'igd', 'spread', 'constraint_satisfaction_rate'];
  return qualityRows(q).filter((r) => keys.includes(r.key));
}

/** Plain-text section of the downloadable report. */
export function qualityReportLines(q) {
  if (!q) {
    return ['OPTIMISATION QUALITY', '  Not recorded for this run (saved before quality metrics were added).', ''];
  }
  const mean = q.mean_objectives;
  return [
    'OPTIMISATION QUALITY (Pareto front of this run)',
    ...qualityRows(q).map((r) => `  ${r.label.padEnd(36)}: ${r.value}${r.hint ? `  (${r.hint})` : ''}`),
    mean
      ? `  ${'Mean of the front'.padEnd(36)}: ${mean.yield_tonnes.toFixed(2)} t, Rs ${Math.round(mean.cost_rs).toLocaleString('en-IN')}, ${Math.round(mean.water_liters).toLocaleString('en-IN')} L, impact ${mean.env_impact_score.toFixed(2)}`
      : `  ${'Mean of the front'.padEnd(36)}: n/a`,
    `  Reference front: ${q.reference_front}; distances on objectives normalised to its ideal and nadir.`,
    '',
  ];
}
