import { describe, expect, it } from 'vitest';
import rerank from '../__fixtures__/topsis-rerank-salem.json';
import {
  BALANCED_PERCENT, CRITERIA, PROFILE_OPTIONS, contributionRows, cropMixText, formatCriterionValue, normalisePercent,
  profileComparisonRows, rankChangeRows, signedRankChange, toFractions, validateCustomPercent, weightDifferenceRows, weightRows,
} from './topsisView';

describe('profile and criterion lists', () => {
  it('match the backend', () => {
    expect(PROFILE_OPTIONS.map((p) => p.value)).toEqual(['balanced', 'profit', 'water', 'sustainability', 'low_cost', 'custom']);
    expect(CRITERIA.map((c) => c.key).sort()).toEqual(Object.keys(rerank.topsis.weights).sort());
  });

  it('balanced defaults add up to 100%', () => {
    expect(validateCustomPercent(BALANCED_PERCENT).valid).toBe(true);
  });
});

describe('custom weight builder', () => {
  it('accepts weights adding up to 100%', () => {
    expect(validateCustomPercent({ yield: 40, water: 35, soil: 25 })).toMatchObject({ valid: true, total: 100 });
  });

  it('rejects totals other than 100% and out-of-range weights', () => {
    const under = validateCustomPercent({ yield: 40, water: 30 });
    expect(under.valid).toBe(false);
    expect(under.errors[0]).toContain('70.0%');
    expect(validateCustomPercent({ yield: 120, water: -20 }).errors[0]).toContain('between 0 and 100%');
    expect(validateCustomPercent({}).valid).toBe(false);
  });

  it('turns percent into fractions summing to exactly 1', () => {
    const f = toFractions(BALANCED_PERCENT);
    expect(Object.values(f).reduce((a, b) => a + b, 0)).toBeCloseTo(1, 9);
    expect(f.yield).toBeCloseTo(0.3, 5);
    expect(toFractions({ yield: 1, cost: 1, water: 1 })).toEqual({ yield: 0.333334, cost: 0.333333, water: 0.333333 });
    expect(toFractions({})).toEqual({});
    expect('income' in toFractions({ yield: 100, income: 0 })).toBe(false);
  });

  it('scales to 100% keeping proportions', () => {
    const n = normalisePercent({ yield: 10, water: 30 });
    expect(n.yield).toBe(25);
    expect(n.water).toBe(75);
    expect(normalisePercent({})).toEqual(BALANCED_PERCENT);
  });
});

describe('ranking rows', () => {
  it('lists weights largest first and skips zero weights', () => {
    const rows = weightRows(rerank.topsis.weights);
    expect(rows.every((r) => r.weight > 0)).toBe(true);
    expect(rows.map((r) => r.weight)).toEqual([...rows.map((r) => r.weight)].sort((a, b) => b - a));
    expect(rows.reduce((s, r) => s + r.percent, 0)).toBeCloseTo(100, 6);
  });

  it('formats the contribution chain of a plan', () => {
    const rows = contributionRows(rerank.explanation.plans[0]);
    expect(rows.length).toBe(rerank.explanation.plans[0].criteria.length);
    expect(rows[0].weight).toMatch(/%$/);
    expect(rows.find((r) => r.key === 'income').value).toMatch(/^₹/);
  });

  it('formats criterion values with units', () => {
    expect(formatCriterionValue({ criterion: 'water', value: 12_340_000 })).toBe('12.34 ML');
    expect(formatCriterionValue({ criterion: 'market_price', value: 1868.4 })).toBe('₹1,868/qtl');
    expect(formatCriterionValue({ criterion: 'soil', value: 0.756 })).toBe('0.76');
    expect(formatCriterionValue({ criterion: 'yield', value: null })).toBe('–');
  });

  it('summarises a crop mix', () => {
    expect(cropMixText([{ crop: 'Tapioca', share_pct: 91.3 }, { crop: 'Groundnut', share_pct: 5.4 }])).toBe('Tapioca 91%, Groundnut 5%');
  });
});

describe('profile comparison rows', () => {
  const c = rerank.comparison;

  it('has one row per profile with the reference marked', () => {
    const rows = profileComparisonRows(c);
    expect(rows.map((r) => r.profile)).toEqual(['balanced', 'profit', 'water', 'sustainability', 'low_cost']);
    const ref = rows.find((r) => r.isReference);
    expect(ref.profile).toBe('profit');
    expect(ref.tau).toBe(1);
    expect(ref.bestRankUnderReference).toBe(1);
  });

  it('shows where the reference top plans rank elsewhere', () => {
    const rows = rankChangeRows(c);
    expect(rows.length).toBe(c.top_n);
    rows.forEach((r, i) => {
      expect(r.referenceRank).toBe(i + 1);
      expect(r.ranks.find((x) => x.profile === 'profit').change).toBe(0);
    });
  });

  it('lists weights of every profile per criterion', () => {
    const rows = weightDifferenceRows(c);
    const income = rows.find((r) => r.key === 'income');
    expect(income.reference).toBeCloseTo(300 / 13, 6);
    expect(income.byProfile.balanced).toBe(0);
    expect(rows.some((r) => r.key === 'soil')).toBe(true);
  });

  it('marks rank changes', () => {
    expect(signedRankChange(0)).toBe('=');
    expect(signedRankChange(3)).toBe('↓3');
    expect(signedRankChange(-2)).toBe('↑2');
  });
});
