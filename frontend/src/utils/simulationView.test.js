import { describe, expect, it } from 'vitest';
import drought from '../__fixtures__/simulation-drought.json';
import infeasible from '../__fixtures__/simulation-infeasible.json';
import {
  buildRequest, confidenceCategories, contributionCategories, cropShareCategories, defaultForm, deltaItems,
  formFromInputs, formatMetric, formatPct, impactMetrics, indexedCategories, prettyStatus, priorityLevel, radarData, simulationTitle,
} from './simulationView';

describe('request building', () => {
  it('maps the form onto the API schema and drops empty optional fields', () => {
    const form = { ...defaultForm('Salem', 5), budget_rs: '', year: '2023', rainfall_change_pct: -20, scenario_land_ha: '' };
    const { base, scenario } = buildRequest(form);
    expect(base).toEqual({ location: 'Salem', season: 'Kharif', year: 2023, total_land_ha: 5, budget_rs: undefined, preference: 'balanced' });
    expect(scenario.rainfall_change_pct).toBe(-20);
    expect(scenario.total_land_ha).toBeUndefined();
    expect(scenario.priorities).toBeUndefined();
  });

  it('sends priorities only when custom priorities are switched on', () => {
    const form = { ...defaultForm('Erode'), use_priorities: true, priorities: { yield: 10, cost: 20, water: 70, env: 0 } };
    expect(buildRequest(form).scenario.priorities).toEqual({ yield: 10, cost: 20, water: 70, env: 0 });
  });

  it('reopens a saved simulation into the same form', () => {
    const form = formFromInputs(drought.inputs, 'Coimbatore');
    const again = buildRequest(form);
    expect(again.base.location).toBe(drought.inputs.base.location);
    expect(again.scenario.rainfall_change_pct).toBe(drought.inputs.scenario.rainfall_change_pct);
    expect(again.scenario.water_availability).toBe(drought.inputs.scenario.water_availability);
    expect(again.scenario.priorities).toEqual(drought.inputs.scenario.priorities);
  });
});

describe('formatting', () => {
  it('labels priority levels', () => {
    expect([0, 33, 34, 66, 67, 100].map(priorityLevel)).toEqual(['Low', 'Low', 'Medium', 'Medium', 'High', 'High']);
  });

  it('formats metrics and missing values', () => {
    expect(formatMetric('water', 21_504_151.5)).toBe('21.5 ML');
    expect(formatMetric('cost', 39589.6, true)).toMatch(/^₹39,590\/ha$/);
    expect(formatMetric('yield', null)).toBe('Data not available');
    expect(formatPct(-3.04)).toBe('-3.0%');
    expect(formatPct(null)).toBe('—');
  });
});

describe('selection from a real result', () => {
  it('builds the headline metrics in the backend basis, with verdicts', () => {
    const metrics = impactMetrics(drought);
    expect(metrics.map((m) => m.id)).toEqual(['yield', 'cost', 'water', 'env', 'profit', 'confidence']);
    const y = metrics[0];
    expect(y.baseline).toBe(drought.impact.totals[0].baseline);
    expect(y.verdictInfo.label).toBeTruthy();
    expect(impactMetrics(infeasible)).toEqual([]);
  });

  it('marks only significant changes as reliable in the delta chart', () => {
    for (const item of deltaItems(drought)) {
      const m = impactMetrics(drought).find((x) => x.id === item.key);
      expect(item.reliable).toBe(m.verdict === 'improved' || m.verdict === 'worsened');
    }
  });

  it('indexes the four objectives to the original mean = 100, ranges included', () => {
    const cats = indexedCategories(drought);
    expect(cats.map((c) => c.key)).toEqual(['yield', 'cost', 'water', 'env']);
    const water = drought.impact.totals.find((m) => m.id === 'water');
    const cat = cats.find((c) => c.key === 'water');
    expect(cat.values[0]).toBe(100);
    expect(cat.values[1]).toBeCloseTo((water.scenario / water.baseline) * 100, 6);
    expect(cat.ranges[1][1]).toBeCloseTo((water.scenario_range[1] / water.baseline) * 100, 6);
    expect(indexedCategories(infeasible)).toEqual([]);
    expect(prettyStatus('not_applicable')).toBe('not applicable');
  });

  it('selects crop shares, confidence, contributions and radar data', () => {
    const crops = cropShareCategories(drought);
    expect(crops.length).toBe(drought.comparison.crop_shares.length);
    expect(crops[0].values).toEqual([drought.comparison.crop_shares[0].baseline_share_pct, drought.comparison.crop_shares[0].scenario_share_pct]);
    expect(confidenceCategories(drought).length).toBe(drought.comparison.confidence.components.length);
    expect(contributionCategories(drought).map((c) => c.key)).toEqual(['yield', 'cost', 'water', 'env']);
    expect(radarData(drought).series[1].values).toEqual(drought.optimization.common_scale.scenario);
    expect(cropShareCategories(infeasible)).toEqual([]);
    expect(radarData(infeasible)).toBeNull();
  });

  it('titles a simulation from its changed conditions', () => {
    expect(simulationTitle(drought)).toMatch(/^Salem Kharif · Rainfall -20%/);
    expect(simulationTitle(infeasible)).toContain('Budget');
  });
});
