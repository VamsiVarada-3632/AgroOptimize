import { describe, expect, it } from 'vitest';
import { headlineQuality, qualityReportLines, qualityRows } from './qualityMetrics';

const q = {
  reference_front: 'front + lower-bound-multiplier copies (non-dominated union)',
  pareto_size: 80, feasible_pareto_size: 78, constraint_satisfaction_rate: 0.975,
  dominated_by_lower_bound_copy: 0.5, runtime_seconds: 0.2737, generations: 200, evaluations: 16000,
  mean_objectives: { yield_tonnes: 39.53, cost_rs: 180937.6, water_liters: 19067479.8, env_impact_score: 226.27 },
  hypervolume: 0.335263, hypervolume_ratio: 0.830674, gd: 0.514275, igd: 0.10979, igd_plus: 0.073573,
  spread: 0.493938, spacing: 0.12189,
};

describe('quality metrics formatting', () => {
  it('formats every metric', () => {
    const rows = Object.fromEntries(qualityRows(q).map((r) => [r.key, r.value]));
    expect(rows.hypervolume_ratio).toBe('0.831');
    expect(rows.igd).toBe('0.110');
    expect(rows.constraint_satisfaction_rate).toBe('97.5%');
    expect(rows.pareto_size).toBe('78 feasible of 80');
    expect(rows.runtime_seconds).toBe('0.27 s');
  });

  it('shows n/a for metrics the backend could not compute', () => {
    const rows = Object.fromEntries(qualityRows({ ...q, spread: null, gd: null, runtime_seconds: null }).map((r) => [r.key, r.value]));
    expect(rows.spread).toBe('n/a');
    expect(rows.gd).toBe('n/a');
    expect(rows.runtime_seconds).toBe('n/a');
  });

  it('picks four headline metrics for the report card', () => {
    expect(headlineQuality(q).map((r) => r.key)).toEqual(['hypervolume_ratio', 'igd', 'spread', 'constraint_satisfaction_rate']);
    expect(headlineQuality(undefined)).toEqual([]);
  });

  it('writes a report section, or says the run predates the metrics', () => {
    const text = qualityReportLines(q).join('\n');
    expect(text).toContain('OPTIMISATION QUALITY');
    expect(text).toContain('Hypervolume ratio');
    expect(text).toContain('39.53 t');
    expect(qualityReportLines(undefined).join('\n')).toContain('Not recorded');
  });
});
