/**
 * Presentation helpers for the District Intelligence page. They only select,
 * reshape and format values returned by GET /api/district-intelligence –
 * every statistic is computed by the backend (app/services/district_service.py).
 */
import { toCsv } from './download';

export const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export const CROP_METRICS = {
  yield_t_ha: { label: 'Yield', unit: ' t/ha', digits: 2 },
  production_t: { label: 'Production', unit: ' t', digits: 0 },
  area_ha: { label: 'Sown area', unit: ' ha', digits: 0 },
  area_share_pct: { label: 'Share of season area', unit: '%', digits: 1 },
};

/** Records matching the chosen filters ('all' or empty = no filter). */
export function filterCropRecords(records, { season, crop, year } = {}) {
  return (records || []).filter((r) =>
    (!season || season === 'all' || r.season === season)
    && (!crop || crop === 'all' || r.crop === crop)
    && (!year || year === 'all' || r.year === Number(year)));
}

/** One line per crop of a season, over the observed years; `selectedCrop` is emphasised. */
export function cropSeries(records, season, metric, selectedCrop) {
  const rows = filterCropRecords(records, { season });
  const years = [...new Set(rows.map((r) => r.year))].sort((a, b) => a - b);
  const crops = [...new Set(rows.map((r) => r.crop))].sort();
  const emphasise = selectedCrop && selectedCrop !== 'all' ? selectedCrop : null;
  return {
    xValues: years,
    series: crops.map((c) => ({
      id: c,
      label: c,
      emphasis: emphasise ? c === emphasise : true,
      points: rows.filter((r) => r.crop === c).map((r) => ({ x: r.year, y: r[metric] })),
    })),
  };
}

/** Bars of one metric for every crop in a season and year, largest first. */
export function yearDistribution(records, season, year, metric, selectedCrop) {
  return filterCropRecords(records, { season, year })
    .map((r) => ({
      key: r.crop,
      label: r.crop,
      value: r[metric],
      highlight: selectedCrop && selectedCrop !== 'all' ? r.crop === selectedCrop : undefined,
    }))
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
}

/** Monthly rainfall lines, one per observed year; the selected year is emphasised. */
export function monthlyRainSeries(monthly, selectedYear) {
  const years = [...new Set((monthly || []).map((m) => m.year))].sort((a, b) => a - b);
  const pick = selectedYear && selectedYear !== 'all' ? Number(selectedYear) : years[years.length - 1];
  return {
    xValues: MONTH_SHORT.map((_, i) => i + 1),
    selectedYear: pick,
    series: years.map((y) => ({
      id: String(y),
      label: String(y),
      emphasis: y === pick,
      points: monthly.filter((m) => m.year === y).map((m) => ({ x: m.month_index, y: m.rainfall_mm })),
    })),
  };
}

/** CSV of the district's observed crop records (for "Export district data"). */
export function cropRecordsCsv(intel) {
  return toCsv(intel.crops.records, [
    { label: 'district', value: () => intel.district },
    { label: 'year', value: 'year' },
    { label: 'season', value: 'season' },
    { label: 'crop', value: 'crop' },
    { label: 'crop_type', value: 'crop_type' },
    { label: 'area_ha', value: 'area_ha' },
    { label: 'area_share_pct', value: 'area_share_pct' },
    { label: 'production_t', value: 'production_t' },
    { label: 'yield_t_ha', value: 'yield_t_ha' },
    { label: 'price_rs_qtl_unvalidated', value: 'price_rs_qtl' },
  ]);
}

/** Plain-text district report assembled from the backend's generated text. */
export function districtReportText(intel) {
  const o = intel.overview;
  const na = (v, suffix = '') => (v === null || v === undefined ? 'Data not available' : `${v}${suffix}`);
  const lines = [
    `AGROOPTIMIZE DISTRICT INTELLIGENCE REPORT – ${intel.district.toUpperCase()}`,
    '='.repeat(60),
    `Generated            : ${new Date().toLocaleString()}`,
    `Observed years       : ${intel.coverage.observed_years.join(', ') || 'none'}`,
    `Excluded (estimated) : ${intel.coverage.estimated_years.join(', ') || 'none'}`,
    `Dataset last updated : ${na(intel.coverage.last_dataset_update)}`,
    '',
    'SUMMARY',
    `  ${intel.summary.text}`,
    '',
    'OVERVIEW',
    `  Agricultural area  : ${na(o.agricultural_area_ha, ' ha')} (${o.land_year_basis ?? '–'})`,
    `  Irrigated share    : ${na(o.irrigated_pct, '%')}`,
    `  Soil types         : ${o.soil_types.join(', ') || 'Data not available'}`,
    `  Annual rainfall    : ${na(o.average_annual_rainfall_mm, ' mm')} (stated normal ${na(o.stated_annual_normal_mm, ' mm')})`,
    `  Mean temperature   : ${na(o.average_temperature_c, ' °C')}`,
    `  Agro-climatic zone : Data not available`,
    `  Irrigation sources : ${o.primary_irrigation_sources.map((s) => `${s.source} (${s.share_of_months_pct}% of months)`).join(', ') || 'Data not available'}`,
    '',
    'INSIGHTS',
    ...intel.insights.map((i) => `  - ${i.title}: ${i.detail}`),
    '',
    `CROP SUITABILITY (basis year ${intel.suitability.year_basis ?? '–'})`,
    ...(intel.suitability.rankings || []).map((r) => `  ${String(r.rank).padStart(2)}. ${r.crop} (${r.season}) – score ${r.score}`),
    `  Method: ${intel.suitability.method || 'Data not available'}`,
    '',
    'MARKET (historical, not live)',
    `  ${intel.market.note}`,
    '',
  ];
  return lines.join('\n');
}

/** Key indicators used by the "Compare district" panel. */
export function compareRows(a, b) {
  const lowestStorage = (x) => {
    const s = x.water.available ? [...x.water.storage_by_season].sort((p, q) => p.storage_pct - q.storage_pct)[0] : null;
    return s ? `${s.storage_pct}% (${s.season})` : 'Data not available';
  };
  const top = (x) => (x.suitability.rankings?.[0] ? `${x.suitability.rankings[0].crop} (${x.suitability.rankings[0].season}, ${x.suitability.rankings[0].score})` : 'Data not available');
  const val = (v, suffix = '') => (v === null || v === undefined ? 'Data not available' : `${v.toLocaleString('en-IN')}${suffix}`);
  return [
    { label: 'Agricultural area', a: val(a.overview.agricultural_area_ha, ' ha'), b: val(b.overview.agricultural_area_ha, ' ha') },
    { label: 'Irrigated share', a: val(a.overview.irrigated_pct, '%'), b: val(b.overview.irrigated_pct, '%') },
    { label: 'Average annual rainfall', a: val(a.overview.average_annual_rainfall_mm, ' mm'), b: val(b.overview.average_annual_rainfall_mm, ' mm') },
    { label: 'Mean temperature', a: val(a.overview.average_temperature_c, ' °C'), b: val(b.overview.average_temperature_c, ' °C') },
    { label: 'Soil', a: a.overview.soil_types.join(', ') || 'Data not available', b: b.overview.soil_types.join(', ') || 'Data not available' },
    { label: 'Soil fertility index', a: a.soil.available ? `${a.soil.latest.fertility_index_mean} (${a.soil.latest.fuzzy_set})` : 'Data not available', b: b.soil.available ? `${b.soil.latest.fertility_index_mean} (${b.soil.latest.fuzzy_set})` : 'Data not available' },
    { label: 'Lowest seasonal storage', a: lowestStorage(a), b: lowestStorage(b) },
    { label: 'Largest crop by area', a: a.overview.major_crops[0] ? `${a.overview.major_crops[0].crop} (${a.overview.major_crops[0].season})` : 'Data not available', b: b.overview.major_crops[0] ? `${b.overview.major_crops[0].crop} (${b.overview.major_crops[0].season})` : 'Data not available' },
    { label: 'Top suitability score', a: top(a), b: top(b) },
  ];
}
