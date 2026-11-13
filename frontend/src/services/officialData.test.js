import { describe, expect, it } from 'vitest';
import { ApiError } from './api';
import {
  OFFICIAL_DATA_NA, catalogCrops, describeRun, isCatalogDistrict, isMissing, isOfficialDataUnavailable, showValue,
} from './officialData';

describe('missing values', () => {
  it('treats null, undefined, empty text and NaN as missing, but not 0', () => {
    for (const v of [null, undefined, '', '  ', NaN, Infinity]) expect(isMissing(v)).toBe(true);
    for (const v of [0, 'Low', false, []]) expect(isMissing(v)).toBe(false);
  });

  it('formats present values and replaces missing ones', () => {
    expect(showValue(null)).toBe(OFFICIAL_DATA_NA);
    expect(showValue(12.5, (v) => `${v} mm`)).toBe('12.5 mm');
    expect(showValue(0, (v) => `${v}%`)).toBe('0%');
  });
});

describe('official-data errors', () => {
  it('maps 400, 404 and 501 to "not available" and leaves other failures alone', () => {
    expect(isOfficialDataUnavailable(new ApiError('x', 501, 'disabled'))).toBe(true);
    expect(isOfficialDataUnavailable(new ApiError('x', 404, ''))).toBe(true);
    expect(isOfficialDataUnavailable(new ApiError('x', 400, ''))).toBe(true);
    expect(isOfficialDataUnavailable(new ApiError('x', 500, ''))).toBe(false);
    expect(isOfficialDataUnavailable(new TypeError('network'))).toBe(false);
  });
});

describe('catalog helpers', () => {
  const catalog = { locations: ['Salem', 'The Nilgiris'], crops_by_season: { Kharif: ['ragi', 'maize'], Rabi: ['maize', 'jowar'] } };

  it('lists each crop once, sorted', () => {
    expect(catalogCrops(catalog)).toEqual(['jowar', 'maize', 'ragi']);
    expect(catalogCrops(null)).toEqual([]);
  });

  it('recognises only catalog districts', () => {
    expect(isCatalogDistrict(catalog, 'Salem')).toBe(true);
    expect(isCatalogDistrict(catalog, 'Pollachi')).toBe(false);
    expect(isCatalogDistrict(catalog, '')).toBe(false);
  });
});

describe('describeRun', () => {
  it('reads the fuzzy model and recognises official-data runs by their crop sources', () => {
    const official = { meta: { fuzzy_model: 'official' }, region_profile: { candidate_crops: [{ name: 'ragi', sources: { crop_statistics: 'TN Season & Crop Report 2024-25' } }] } };
    expect(describeRun(official)).toMatchObject({ model: 'official', official: true });
    const legacy = { meta: {}, region_profile: { candidate_crops: [{ name: 'Paddy', sources: {} }] } };
    expect(describeRun(legacy)).toMatchObject({ model: 'original', modelLabel: 'Original Model', official: false });
    expect(describeRun({ meta: { fuzzy_model: 'improved' } }).modelLabel).toBe('Improved Model');
  });
});
