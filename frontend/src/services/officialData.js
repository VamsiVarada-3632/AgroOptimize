import { useEffect, useState } from 'react';
import { api, ApiError } from './api';

/**
 * Shared access to the backend's official-data reference responses (catalog,
 * fuzzy models, dataset registry) and the rules for showing values the
 * official datasets do not publish.
 */

/** Text shown wherever the official datasets have no value. */
export const OFFICIAL_DATA_NA = 'Official Data Not Available';

/** True for a value the backend did not supply (null, undefined, empty text, NaN). */
export function isMissing(value) {
  if (value === null || value === undefined) return true;
  if (typeof value === 'number') return !Number.isFinite(value);
  if (typeof value === 'string') return value.trim() === '';
  return false;
}

/**
 * Formats a backend value, or returns OFFICIAL_DATA_NA when it is missing.
 * `format` receives the value only when it is present.
 */
export function showValue(value, format = (v) => String(v)) {
  return isMissing(value) ? OFFICIAL_DATA_NA : format(value);
}

/**
 * True when an API error means "the official datasets have nothing for this"
 * rather than a server fault: 400 (e.g. a district without two complete crops),
 * 404 (unknown district or record) and 501 (feature disabled until its official
 * dataset is loaded).
 */
export function isOfficialDataUnavailable(err) {
  return err instanceof ApiError && [400, 404, 501].includes(err.status);
}

/**
 * Plain-language labels for backend fields. The field names stay as the
 * backend sends them; only what the user reads changes.
 */
export const FIELD_LABELS = {
  water_liters: 'Water Requirement',
  irrigated_ha: 'Irrigated Area',
  crop_evidence: 'Why this crop was selected',
  soil_ph: 'Soil pH',
  ph: 'Soil pH',
  organic_carbon: 'Organic Carbon',
  npk: 'Fertilizer Recommendation',
  ec: 'Soil Salinity',
  electrical_conductivity: 'Soil Salinity',
  topsis_score: 'Overall Score',
  composite_score: 'Overall Score',
  nsga_rank: 'Optimization Rank',
  hypervolume: 'Optimization Quality',
  igd: 'Solution Accuracy',
  igd_plus: 'Improved Solution Accuracy',
};

/** Display name of a crop evidence criterion (crop_evidence[].criteria[].id). */
export const EVIDENCE_LABELS = {
  rainfall: 'Rainfall',
  soil: 'Soil',
  water: 'Water',
  budget: 'Budget',
  fertiliser: 'Fertilizer',
  fertilizer: 'Fertilizer',
  msp: 'MSP',
  market_price: 'Market Price',
  yield: 'Yield',
  duration: 'Duration',
  risks: 'Risks',
};

// One request per resource per page load; a failed request is retried next time.
const cache = new Map();

function loadOnce(key, loader) {
  if (!cache.has(key)) {
    cache.set(key, loader().catch((err) => {
      cache.delete(key);
      throw err;
    }));
  }
  return cache.get(key);
}

/** Test hook: forget every cached response. */
export function clearOfficialDataCache() {
  cache.clear();
}

function useCached(key, loader) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let cancelled = false;
    loadOnce(key, loader)
      .then((data) => { if (!cancelled) setState({ data, error: null, loading: false }); })
      .catch((error) => { if (!cancelled) setState({ data: null, error, loading: false }); });
    return () => { cancelled = true; };
  }, [key, loader]);
  return state;
}

/** GET /api/catalog: { locations, seasons, years, crops_by_season, taluk_notes, data_sources }. */
export const loadCatalog = () => loadOnce('catalog', api.getCatalog);
export const useCatalog = () => useCached('catalog', api.getCatalog);

/** GET /openapi.json: the backend's version and schema defaults. */
export const useOpenApi = () => useCached('openapi', api.getOpenApi);

/** GET /api/fuzzy/models: { default, models: [{ name, description, ... }] }. */
export const useFuzzyModels = () => useCached('fuzzy-models', api.getFuzzyModels);

/** GET /api/datasets: { datasets, disabled_features }. */
export const useDatasets = () => useCached('datasets', api.getDatasets);

/** Every crop the catalog lists for any season, sorted. */
export function catalogCrops(catalog) {
  const set = new Set();
  Object.values(catalog?.crops_by_season ?? {}).forEach((list) => list.forEach((c) => set.add(c)));
  return Array.from(set).sort();
}

/** True when `location` is one of the catalog's districts. */
export function isCatalogDistrict(catalog, location) {
  return Boolean(location) && (catalog?.locations ?? []).includes(location);
}

/**
 * Display name of a fuzzy model: the backend's model names are identifiers,
 * so they are shown in words. Unknown names are shown as sent.
 */
export function fuzzyModelLabel(name) {
  const labels = {
    official: 'Official (calibrated on official data)',
    original: 'Original (published)',
    improved: 'Improved',
    strong_partition: 'Strong partition',
    imd_rainfall: 'IMD rainfall bands',
    pruned_rules: 'Pruned rules',
  };
  return labels[name] ?? name;
}

/**
 * Which fuzzy model and which data a saved run (GET /api/results/{run_id})
 * used. Runs saved before fuzzy models existed used the published one
 * (backend: RunMeta.fuzzy_model). A run counts as official data when its
 * candidate crops cite official sources (CropCandidateOut.sources), which
 * runs made on the earlier synthetic datasets do not have.
 */
export function describeRun(run) {
  const model = run?.meta?.fuzzy_model || 'original';
  const crops = run?.region_profile?.candidate_crops ?? [];
  const official = crops.some((c) => c?.sources && Object.keys(c.sources).length > 0);
  return { model, modelLabel: MODEL_BADGES[model] ?? fuzzyModelLabel(model), official };
}

const MODEL_BADGES = {
  original: 'Original Model',
  improved: 'Improved Model',
  official: 'Official-Data Model',
};
