/**
 * Central API client for the AgroOptimize FastAPI backend.
 *
 * Every view should go through the `api` object below instead of calling
 * `fetch` directly -- this file is the single place that knows the
 * backend's base URL, its real field names, and how a free-text user
 * location resolves to one of the 4 Tamil Nadu districts the backend
 * actually has data for (Coimbatore / Erode / Salem / Pollachi).
 *
 * Run the backend locally with:
 *   uvicorn app.main:app --reload --port 8000
 */

// Vite exposes build-time env vars prefixed VITE_ on import.meta.env. Set
// VITE_API_BASE in a Vercel (or other host) project's environment config to
// point the deployed frontend at a real deployed backend -- local dev
// (`npm run dev`) keeps working unchanged via the localhost fallback.
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export const DISTRICTS = ['Coimbatore', 'Erode', 'Salem', 'Pollachi'];

export const SEASONS = ['Kharif', 'Rabi', 'Summer'];

export const PREFERENCES = [
  { value: 'balanced', label: 'Balanced' },
  { value: 'max_yield', label: 'Max Yield' },
  { value: 'min_cost', label: 'Min Cost' },
  { value: 'min_water', label: 'Min Water Use' },
  { value: 'min_env_impact', label: 'Min Environmental Impact' },
];

/**
 * The backend only knows about the 4 districts above. The frontend's user
 * profile stores `location` as one of those 4 names (e.g. "Coimbatore"),
 * chosen from a dropdown during profile setup -- never free text. This
 * pulls out whichever known district name appears in a given string,
 * case-insensitively, and falls back to Coimbatore if none match. That
 * fallback only matters for legacy/malformed values; App.jsx already
 * requires a real, valid district before any dashboard view can render,
 * so in practice every call here receives a genuine user-chosen district.
 */
export function extractDistrict(locationString) {
  if (!locationString) return 'Coimbatore';
  const lower = String(locationString).toLowerCase();
  const found = DISTRICTS.find((d) => lower.includes(d.toLowerCase()));
  return found || 'Coimbatore';
}

/**
 * This project has no real backend user accounts -- districts are the only
 * thing scoping most data, which is fine for live weather/dashboard/plans
 * (that's genuinely regional, not personal). But saved optimization RUNS
 * (History's "Completed" entries) need *some* way to tell "a run this
 * browser generated" apart from "a run anyone else, or the project's own
 * demo/seed data, generated for the same district" -- otherwise every new
 * user who picks an existing district would see other people's saved runs
 * as if they were their own history.
 *
 * This is that mechanism: a random id generated once and kept in
 * localStorage for the lifetime of this browser profile. It identifies a
 * *browser*, not a person -- clearing site data or switching browsers
 * starts a new one, same as the rest of this app's client-only "auth".
 */
function getOrCreateClientId() {
  const KEY = 'agro_client_id';
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : `client-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    localStorage.setItem(KEY, id);
  }
  return id;
}

/**
 * Shown whenever the backend can't be reached at all (network error, server
 * down). Local development gets the concrete fix; a deployed build gets
 * wording that makes sense to a farmer.
 */
export const BACKEND_UNREACHABLE_MSG = import.meta.env.DEV
  ? "Couldn't reach the backend. Start it with `uvicorn app.main:app --port 8000` and try again."
  : "Couldn't reach the AgroOptimize server. Check your connection and try again in a moment.";

/** Error thrown for any non-2xx response; `status` is the HTTP code and
 * `detail` the backend's human-readable reason (FastAPI's `detail`). */
export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function extractDetail(body) {
  const detail = body?.detail;
  if (!detail) return '';
  if (typeof detail === 'string') return detail;
  // 422 validation errors: [{ loc, msg, type }, ...]
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
  // 503 from /api/plans: { error, message, location }
  return detail.message || detail.error || JSON.stringify(detail);
}

async function toApiError(res, method, path) {
  let detail = '';
  try {
    detail = extractDetail(await res.json());
  } catch {
    detail = '';
  }
  return new ApiError(`${method} ${path} failed: ${res.status}${detail ? ` -- ${detail}` : ''}`, res.status, detail);
}

/**
 * User-facing text for a failed API call: the backend's own explanation for
 * 4xx/5xx responses, or the "unreachable" message when there was no
 * response at all.
 */
export function describeApiError(err) {
  if (err instanceof ApiError) {
    if (err.detail) return err.detail;
    return `The server returned an error (HTTP ${err.status}). Please try again.`;
  }
  return BACKEND_UNREACHABLE_MSG;
}

async function fetchAPI(path, params = {}) {
  const url = new URL(`${API_BASE}${path}`);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, value);
    }
  });
  const res = await fetch(url.toString());
  if (!res.ok) throw await toApiError(res, 'GET', path);
  return res.json();
}

async function postAPI(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await toApiError(res, 'POST', path);
  return res.json();
}

/**
 * Shape of GET .../explanation responses (backend: app/schemas.py ExplanationOut).
 * Every item's `detail` text is generated by the backend from `evidence`.
 * @typedef {{id: string, title: string, detail: string, source: string,
 *   evidence: Object, status?: string, severity?: 'high'|'medium'|'low'}} ExplanationItem
 * @typedef {{id: string, label: string, score: number|null, weight: number,
 *   detail: string, source: string}} ConfidenceComponent
 * @typedef {{
 *   subject: Object,
 *   summary: {location: string, season: string, year: number, data_year_estimated: boolean,
 *     preference: string, rank: number, plans_compared: number, closeness: number,
 *     recommendation: string, confidence_pct: number, crop_mix: Array<{crop: string, share_pct: number, area_ha: number}>,
 *     per_ha: Object, totals: Object, recommendation_rule: string},
 *   reasons: ExplanationItem[], benefits: ExplanationItem[], risks: ExplanationItem[],
 *   insights: ExplanationItem[], alternatives: ExplanationItem[], timeline: ExplanationItem[],
 *   objectives: {objectives: Object[], strongest: string, compromise: string},
 *   trade_offs: {items: ExplanationItem[], marginal_rates: Object[]},
 *   constraints: {items: ExplanationItem[]},
 *   historical_context: Object,
 *   confidence: {overall_pct: number, components: ConfidenceComponent[], method: string},
 *   economics: Object, crop_breakdown: Object[], consistency_checks: Object, fuzzy_reasoning: Object
 * }} Explanation
 */

export const api = {
  /** GET /health -- used for the app-startup connectivity check. */
  checkHealth: () => fetchAPI('/health'),

  /** GET /api/catalog -- locations/seasons/years/crops the dataset covers. */
  getCatalog: () => fetchAPI('/api/catalog'),

  /** GET /api/weather/{district} */
  getWeather: (location) =>
    fetchAPI(`/api/weather/${extractDistrict(location).toLowerCase()}`),

  /**
   * GET /api/dashboard/{district} -- KPI summary. Passes this browser's
   * client_id so "Active Plans" only counts runs *it* actually generated
   * (same pattern as getHistory below); a brand-new browser correctly
   * gets 0 instead of counting other people's/seed saved runs.
   */
  getDashboard: (location) =>
    fetchAPI(`/api/dashboard/${extractDistrict(location).toLowerCase()}`, {
      client_id: getOrCreateClientId(),
    }),

  /**
   * GET /api/history/{district} -- past optimization runs. Passes this
   * browser's client_id so only runs *it* actually generated come back
   * flagged "Completed"; a brand-new browser correctly gets none.
   */
  getHistory: (location) =>
    fetchAPI(`/api/history/${extractDistrict(location).toLowerCase()}`, {
      client_id: getOrCreateClientId(),
    }),

  /** GET /api/soil-profile/{district} */
  getSoilProfile: (location) =>
    fetchAPI(`/api/soil-profile/${extractDistrict(location).toLowerCase()}`),

  /** GET /api/catalog for years is on getCatalog above; GET /api/results/{run_id}
   * -- full saved record for one of THIS browser's own past runs (id comes
   * from getHistory's list). Used by the Reports page to build a report
   * from an existing run instead of launching a new optimization. */
  getResult: (runId) => fetchAPI(`/api/results/${encodeURIComponent(runId)}`),

  /** GET /api/plans/{district} -- up to ~100 Pareto-optimal plans. */
  getPlans: (location, { totalLandHa, budgetRs } = {}) =>
    fetchAPI(`/api/plans/${extractDistrict(location).toLowerCase()}`, {
      total_land_ha: totalLandHa,
      budget_rs: budgetRs,
    }),

  /** GET /api/comparison/{district} -- Plan A (balanced) / B (max yield) / C (min cost). */
  getComparison: (location, { totalLandHa, budgetRs } = {}) =>
    fetchAPI(`/api/comparison/${extractDistrict(location).toLowerCase()}`, {
      total_land_ha: totalLandHa,
      budget_rs: budgetRs,
    }),

  /**
   * GET /api/compare-fuzzy/{district} -- fuzzy-vs-non-fuzzy comparison
   * study: runs NSGA-II with the Mamdani fuzzy uncertainty adjustment on
   * and off over the same region/season, returns per-hectare summary
   * stats for both so AnalyticsView can render them side by side.
   */
  getFuzzyComparison: (location, { season, year, totalLandHa, budgetRs } = {}) =>
    fetchAPI(`/api/compare-fuzzy/${extractDistrict(location).toLowerCase()}`, {
      season,
      year,
      total_land_ha: totalLandHa,
      budget_rs: budgetRs,
    }),

  /**
   * GET /api/results/{run_id}/explanation -- structured explanation of one
   * plan in a saved run (rank 1 = the recommended plan).
   * @param {string} runId
   * @param {number} [rank=1]
   * @returns {Promise<Explanation>}
   */
  getResultExplanation: (runId, rank = 1) =>
    fetchAPI(`/api/results/${encodeURIComponent(runId)}/explanation`, { rank }),

  /**
   * GET /api/comparison/{district}/explanation -- explanation of Plan A, B
   * or C from the Comparison page (same Pareto front as getComparison).
   * @param {string} location
   * @param {'A'|'B'|'C'} plan
   * @returns {Promise<Explanation>}
   */
  getComparisonExplanation: (location, plan, { totalLandHa, budgetRs } = {}) =>
    fetchAPI(`/api/comparison/${extractDistrict(location).toLowerCase()}/explanation`, {
      plan,
      total_land_ha: totalLandHa,
      budget_rs: budgetRs,
    }),

  /**
   * POST /api/farm-plans -- runs the full preprocessing -> fuzzy -> NSGA-II
   * -> TOPSIS ranking pipeline live and returns the ranked plans.
   *
   * Accepts the friendlier `land_area_ha` / `budget` field names and maps
   * them onto the real FarmPlanRequest schema (`total_land_ha` /
   * `budget_rs`) here, so callers don't need to know the backend's exact
   * schema.
   */
  runOptimization: ({
    location,
    season = 'Kharif',
    year,
    land_area_ha = 5.0,
    budget,
    preference = 'balanced',
  } = {}) =>
    postAPI('/api/farm-plans', {
      location: extractDistrict(location),
      season,
      year,
      total_land_ha: land_area_ha,
      budget_rs: budget || undefined,
      preference,
      save_results: true,
      client_id: getOrCreateClientId(),
    }),
};

export default api;
