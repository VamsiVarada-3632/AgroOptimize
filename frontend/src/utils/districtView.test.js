import { OFFICIAL_DATA_NA } from '../services/officialData';
import { describe, expect, it } from 'vitest';
import salem from '../__fixtures__/district-salem.json';
import {
  compareRows, cropRecordsCsv, cropSeries, districtReportText, filterCropRecords, monthlyRainSeries, yearDistribution,
} from './districtView';

const records = salem.crops.records;

describe('filterCropRecords', () => {
  it('returns everything without filters', () => {
    expect(filterCropRecords(records)).toHaveLength(records.length);
    expect(filterCropRecords(records, { season: 'all', crop: 'all', year: 'all' })).toHaveLength(records.length);
  });

  it('applies season, crop and year together', () => {
    const rows = filterCropRecords(records, { season: 'Kharif', crop: 'maize', year: '2024' });
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ season: 'Kharif', crop: 'maize', year: 2024 });
  });

  it('handles missing input', () => {
    expect(filterCropRecords(undefined, { season: 'Kharif' })).toEqual([]);
  });
});

describe('cropSeries', () => {
  it('builds one line per crop of the season over the observed years', () => {
    const { xValues, series } = cropSeries(records, 'Kharif', 'yield_t_ha', 'all');
    const kharifCrops = new Set(records.filter((r) => r.season === 'Kharif').map((r) => r.crop));
    expect(series.map((s) => s.id).sort()).toEqual([...kharifCrops].sort());
    expect(xValues).toEqual(salem.crops.filters.years);
    expect(series.every((s) => s.emphasis)).toBe(true);
  });

  it('emphasises only the selected crop and keeps backend values unchanged', () => {
    const { series } = cropSeries(records, 'Kharif', 'production_t', 'rice');
    expect(series.filter((s) => s.emphasis).map((s) => s.id)).toEqual(['rice']);
    const paddy = series.find((s) => s.id === 'rice');
    const raw = records.filter((r) => r.season === 'Kharif' && r.crop === 'rice');
    expect(paddy.points.map((p) => p.y)).toEqual(raw.map((r) => r.production_t));
  });
});

describe('yearDistribution', () => {
  it('sorts crops by the metric, largest first, and highlights the selection', () => {
    const bars = yearDistribution(records, 'Kharif', 2024, 'area_share_pct', 'cotton');
    const values = bars.map((b) => b.value);
    expect(values).toEqual([...values].sort((a, b) => b - a));
    expect(bars.find((b) => b.key === 'cotton').highlight).toBe(true);
    expect(bars.filter((b) => b.highlight === false).length).toBe(bars.length - 1);
    expect(values.reduce((a, b) => a + b, 0)).toBeCloseTo(100, 0);
  });
});

describe('monthlyRainSeries', () => {
  it('defaults to the latest observed year and spans 12 months', () => {
    const { xValues, series, selectedYear } = monthlyRainSeries(salem.climate.monthly);
    expect(xValues).toHaveLength(12);
    expect(selectedYear).toBe(Math.max(...salem.climate.annual.map((a) => a.year)));
    expect(series.filter((s) => s.emphasis).map((s) => s.id)).toEqual([String(selectedYear)]);
    series.forEach((s) => expect(s.points).toHaveLength(12));
  });

  it('can emphasise another year', () => {
    expect(monthlyRainSeries(salem.climate.monthly, '2024').selectedYear).toBe(2024);
  });
});

describe('exports', () => {
  it('CSV has a header and one row per observed record', () => {
    const lines = cropRecordsCsv(salem).split('\n');
    expect(lines[0]).toContain('district,year,season,crop');
    expect(lines).toHaveLength(records.length + 1);
  });

  it('report text uses the backend summary and marks missing values', () => {
    const text = districtReportText(salem);
    expect(text).toContain(salem.summary.text);
    expect(text).toContain(`Agro-climatic zone : ${OFFICIAL_DATA_NA}`);
    salem.insights.forEach((i) => expect(text).toContain(i.detail));
    expect(text).not.toMatch(/undefined|NaN/);
  });
});

describe('compareRows', () => {
  it('shows "Official Data Not Available" when a section is missing', () => {
    const noWater = { ...salem, water: { available: false }, soil: { available: false } };
    const rows = compareRows(salem, noWater);
    const storage = rows.find((r) => r.label === 'Lowest seasonal storage');
    expect(storage.b).toBe(OFFICIAL_DATA_NA);
    expect(storage.a).toMatch(/%/);
    expect(rows.find((r) => r.label === 'Soil fertility index').b).toBe(OFFICIAL_DATA_NA);
  });
});
