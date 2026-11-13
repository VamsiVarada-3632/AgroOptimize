/**
 * Formatting of a run's Pareto-front quality metrics (backend:
 * app/optimization/metrics.py, returned as meta.quality_metrics). Nothing is
 * computed here; a metric the backend could not compute (no feasible plan,
 * fewer than two plans) is shown as NOT_COMPUTED. Labels use plain words
 * (FIELD_LABELS); the backend keys stay unchanged.
 */
import { FIELD_LABELS, isMissing } from '../services/officialData';

export const NOT_COMPUTED = 'Not computed for this run';

const num = (v, digits = 3) => (isMissing(v) ? NOT_COMPUTED : Number(v).toFixed(digits));
const pct = (v) => (isMissing(v) ? NOT_COMPUTED : `${(Number(v) * 100).toFixed(1)}%`);

/** Rows for display: label, formatted value and what "good" means. */
export function qualityRows(q) {
  if (!q) return [];
  return [
    { key: 'hypervolume_ratio', label: FIELD_LABELS.hypervolume, value: num(q.hypervolume_ratio), hint: 'hypervolume ratio: share of the best known front covered; 1 = best' },
    { key: 'hypervolume', label: `${FIELD_LABELS.hypervolume} (raw hypervolume)`, value: num(q.hypervolume, 4), hint: 'normalised, higher is better' },
    { key: 'gd', label: 'Generational distance (GD)', value: num(q.gd), hint: 'distance to the reference front, lower is better' },
    { key: 'igd', label: FIELD_LABELS.igd, value: num(q.igd), hint: 'inverted generational distance (IGD), lower is better' },
    { key: 'igd_plus', label: FIELD_LABELS.igd_plus, value: num(q.igd_plus), hint: 'IGD+, lower is better' },
    { key: 'spread', label: 'Spread', value: num(q.spread), hint: 'lower = more evenly spread' },
    { key: 'spacing', label: 'Spacing', value: num(q.spacing), hint: 'lower = more evenly spaced' },
    { key: 'pareto_size', label: 'Pareto solutions', value: `${q.feasible_pareto_size} feasible of ${q.pareto_size}`, hint: '' },
    { key: 'constraint_satisfaction_rate', label: 'Constraint satisfaction', value: pct(q.constraint_satisfaction_rate), hint: 'final population within budget' },
    { key: 'dominated_by_lower_bound_copy', label: 'Beaten by lower-input copy', value: pct(q.dominated_by_lower_bound_copy), hint: 'lower is better' },
    { key: 'runtime_seconds', label: 'Runtime', value: isMissing(q.runtime_seconds) ? NOT_COMPUTED : `${Number(q.runtime_seconds).toFixed(2)} s`, hint: `${q.generations ?? NOT_COMPUTED} generations, ${q.evaluations ?? NOT_COMPUTED} evaluations` },
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
      ? `  ${'Mean of the front'.padEnd(36)}: ${mean.yield_tonnes.toFixed(2)} t, Rs ${Math.round(mean.cost_rs).toLocaleString('en-IN')}, ${mean.irrigated_ha.toFixed(2)} ha irrigated, nutrient load ${mean.env_impact_score.toFixed(2)} kg`
      : `  ${'Mean of the front'.padEnd(36)}: ${NOT_COMPUTED}`,
    `  Reference front: ${q.reference_front}; distances on objectives normalised to its ideal and nadir.`,
    '',
  ];
}
