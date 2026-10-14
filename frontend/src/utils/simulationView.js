/**
 * Scenario Simulation view helpers: request building and selection /
 * formatting of the backend's simulation result for charts and tables.
 * Nothing here computes an outcome -- every number comes from
 * POST /api/simulations/run.
 */

export const RAINFALL_OPTIONS = [-30, -20, -10, 0, 10, 20, 30];
export const FERTILIZER_OPTIONS = [-20, -10, 0, 10, 20, 30];
export const WATER_OPTIONS = [
  { value: 'current', label: 'Current' },
  { value: 'very_low', label: 'Very low' },
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'very_high', label: 'Very high' },
];
export const MARKET_OPTIONS = [
  { value: 'decrease', label: 'Decrease' },
  { value: 'stable', label: 'Stable' },
  { value: 'increase', label: 'Increase' },
];
export const OBJECTIVES = ['yield', 'cost', 'water', 'env'];
export const OBJECTIVE_LABELS = {
  yield: 'Expected yield', cost: 'Production cost', water: 'Irrigation water', env: 'Environmental impact',
  profit: 'Indicative profit', confidence: 'Confidence',
};
export const PRIORITY_LABELS = {
  yield: 'Yield priority', cost: 'Production cost priority', water: 'Water conservation priority', env: 'Environmental priority',
};

export const VERDICTS = {
  improved: { label: 'Improved', icon: 'trending_up' },
  worsened: { label: 'Worsened', icon: 'trending_down' },
  unchanged: { label: 'No change', icon: 'trending_flat' },
  not_significant: { label: 'Within search variation', icon: 'blur_on' },
  not_available: { label: 'Data not available', icon: 'help' },
};

/** Slider position (0–100) → Low / Medium / High wording. */
export function priorityLevel(value) {
  if (value < 34) return 'Low';
  if (value < 67) return 'Medium';
  return 'High';
}

export function defaultForm(district, landHa = 5) {
  return {
    location: district, season: 'Kharif', year: '', total_land_ha: landHa, budget_rs: '', preference: 'balanced',
    rainfall_change_pct: 0, water_availability: 'current', fertilizer_cost_change_pct: 0, market_price: 'stable',
    scenario_land_ha: '', scenario_budget_rs: '', use_priorities: false,
    priorities: { yield: 50, cost: 50, water: 50, env: 50 },
  };
}

const num = (v) => (v === '' || v === null || v === undefined ? undefined : Number(v));

/** Form state → { base, scenario } for api.runSimulation. */
export function buildRequest(form) {
  const base = {
    location: form.location, season: form.season, year: num(form.year), total_land_ha: Number(form.total_land_ha),
    budget_rs: num(form.budget_rs), preference: form.preference,
  };
  const scenario = {
    rainfall_change_pct: Number(form.rainfall_change_pct), water_availability: form.water_availability,
    fertilizer_cost_change_pct: Number(form.fertilizer_cost_change_pct), market_price: form.market_price,
    total_land_ha: num(form.scenario_land_ha), budget_rs: num(form.scenario_budget_rs),
    priorities: form.use_priorities ? { ...form.priorities } : undefined,
  };
  return { base, scenario };
}

/** A saved simulation's inputs → form state (for reopening). */
export function formFromInputs(inputs, fallbackDistrict) {
  const f = defaultForm(inputs?.base?.location || fallbackDistrict, inputs?.base?.total_land_ha ?? 5);
  const b = inputs?.base || {};
  const s = inputs?.scenario || {};
  return {
    ...f,
    season: b.season || f.season, year: b.year ?? '', budget_rs: b.budget_rs ?? '', preference: b.preference || f.preference,
    rainfall_change_pct: s.rainfall_change_pct ?? 0, water_availability: s.water_availability || 'current',
    fertilizer_cost_change_pct: s.fertilizer_cost_change_pct ?? 0, market_price: s.market_price || 'stable',
    scenario_land_ha: s.total_land_ha ?? '', scenario_budget_rs: s.budget_rs ?? '',
    use_priorities: Boolean(s.priorities), priorities: s.priorities || f.priorities,
  };
}

const UNITS = { yield: 't', cost: '₹', water: 'L', env: '' };

/** Human-readable value for an objective (totals or per hectare). */
export function formatMetric(id, value, perHa = false) {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'Data not available';
  const suffix = perHa ? '/ha' : '';
  if (id === 'cost' || id === 'profit') return `₹${Math.round(value).toLocaleString('en-IN')}${suffix}`;
  if (id === 'water') return `${(value / 1e6).toLocaleString('en-IN', { maximumFractionDigits: 2 })} ML${suffix}`;
  if (id === 'yield') return `${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })} t${suffix}`;
  if (id === 'confidence') return `${value.toFixed(1)}%`;
  return `${value.toLocaleString('en-IN', { maximumFractionDigits: 1 })}${UNITS[id] || ''}${suffix ? ' per ha' : ''}`;
}

export function formatPct(v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}%`;
}

/** Headline metrics (in the basis the backend chose) for the before/after cards. */
export function impactMetrics(result) {
  const impact = result?.impact;
  if (!impact) return [];
  const perHa = impact.basis === 'per_ha';
  const list = perHa ? impact.per_ha : impact.totals;
  return [...list, impact.profit, impact.confidence].map((m) => ({
    ...m,
    perHa: perHa && m.id !== 'confidence',
    baselineText: formatMetric(m.id, m.baseline, perHa && m.id !== 'confidence'),
    scenarioText: formatMetric(m.id, m.scenario, perHa && m.id !== 'confidence'),
    verdictInfo: VERDICTS[m.verdict] || VERDICTS.not_available,
  }));
}

/** Items for DeltaBarChart. */
export function deltaItems(result) {
  return impactMetrics(result).map((m) => ({
    key: m.id, label: OBJECTIVE_LABELS[m.id] || m.label, change: m.change_pct,
    reliable: m.verdict === 'improved' || m.verdict === 'worsened', verdictLabel: m.verdictInfo.label,
  }));
}

/**
 * The four objectives on one axis, indexed so the original mean = 100
 * (different units cannot share an axis otherwise). Ranges are indexed the
 * same way; the absolute values stay available in the table view.
 */
export function indexedCategories(result) {
  const impact = result?.impact;
  if (!impact) return [];
  const list = impact.basis === 'per_ha' ? impact.per_ha : impact.totals;
  return list.filter((m) => m.baseline).map((m) => {
    const idx = (v) => (v === null || v === undefined ? null : (v / m.baseline) * 100);
    return {
      key: m.id, label: OBJECTIVE_LABELS[m.id], values: [100, idx(m.scenario)],
      ranges: m.baseline_range ? [m.baseline_range.map(idx), m.scenario_range.map(idx)] : undefined,
    };
  });
}

export const prettyStatus = (s) => (s ? String(s).replace(/_/g, ' ') : '—');

/** Crop share categories: the two recommended plans side by side. */
export function cropShareCategories(result) {
  return (result?.comparison?.crop_shares || []).map((r) => ({
    key: r.crop, label: r.crop, values: [r.baseline_share_pct, r.scenario_share_pct],
  }));
}

export function confidenceCategories(result) {
  return (result?.comparison?.confidence?.components || []).map((c) => ({
    key: c.id, label: c.label.replace(/ \(.*\)$/, ''), values: [c.baseline, c.scenario],
  }));
}

export function contributionCategories(result) {
  const c = result?.optimization?.contributions;
  if (!c) return [];
  return OBJECTIVES.map((o, i) => ({
    key: o, label: OBJECTIVE_LABELS[o], values: [c.baseline[i].weighted, c.scenario[i].weighted],
  }));
}

export function radarData(result) {
  const cs = result?.optimization?.common_scale;
  if (!cs) return null;
  return {
    axes: OBJECTIVES.map((o) => ({ key: o, label: { yield: 'Yield', cost: 'Low cost', water: 'Low water', env: 'Low impact' }[o] })),
    series: [{ label: 'Original plan', values: cs.baseline }, { label: 'Simulated plan', values: cs.scenario }],
  };
}

export function changedConditions(result) {
  return (result?.conditions || []).filter((c) => c.changed);
}

export function simulationTitle(result) {
  const b = result?.inputs?.base || {};
  const changes = changedConditions(result).map((c) => `${c.label} ${c.scenario}`);
  return `${b.location} ${b.season}${changes.length ? ` · ${changes.join(', ')}` : ' · no changes'}`;
}
