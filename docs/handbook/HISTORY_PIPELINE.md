# History Pipeline

"History" = the list of optimisation runs **this browser** saved for a district. There are no user accounts; a random per-browser `client_id` is the only scoping key.

## 1. Identity

`src/services/api.js::getOrCreateClientId()` creates `crypto.randomUUID()` once and stores it in `localStorage.agro_client_id`. It is sent as:
* body field `client_id` on `POST /api/farm-plans` (stored in the run JSON),
* query `client_id` on `GET /api/history/{district}` and `GET /api/dashboard/{district}`.

## 2. Write path
Run Optimization → `POST /api/farm-plans {…, save_results: true, client_id}` → `results_store.save_run_results(response, history, client_id=…)` → `results/<run_id>.json` containing `client_id` and `saved_at`.

## 3. Read path (`dashboard_service.get_history`)

```mermaid
flowchart TB
    A[GET /api/history/salem?client_id=X] --> B[resolve_location → Salem]
    B --> C[results_store.list_saved_runs<br/>summaries, cached by mtime]
    C --> D{location == Salem<br/>and client_id == X?}
    D -- no --> skip[skip]
    D -- yes --> E[load_run run_id]
    E --> F[plan #1: yield_tonnes / Σarea_ha → "t/ha"<br/>cost_rs / Σarea_ha → "₹/ha"]
    F --> G[row: id, "Season Year", date, target_yield, est_cost,<br/>status "Completed", num_plans, preference, fuzzy_weights, is_estimated false]
    G --> H[sort by saved_at, newest first]
    H --> I["{history: [...]}"]
```

Rules:
* No `client_id`, or a mismatch, or a legacy run without `client_id` → excluded. A brand-new browser gets `[]` (product decision; no CSV "estimated" filler rows).
* Ordering was previously by the display string `"Kharif 2023"` (alphabetical by season name); fixed to newest save first.
* `is_estimated` is always `false` (kept for response compatibility with an earlier version that mixed in CSV rows).
* Runs with zero plans (e.g. an infeasible budget) appear with `"--"` yield and cost.

## 4. Consumers

| Consumer | Uses |
|---|---|
| HistoryView | timeline cards, search by season text, year filter, details modal (fuzzy confidence/risk %) |
| ReportsView | list of runs to build reports from; `id` → `GET /api/results/{id}` |
| Dashboard "Active Plans" | same filter, count only (`get_dashboard`) |

## 5. Limitations and risks
* **Not a security boundary.** Anyone who learns a `client_id` can read that browser's history. `GET /api/results` used to publish all `client_id`s; now redacted. Run ids are predictable (district_season_year_timestamp), and `GET /api/results/{run_id}` needs no `client_id`.
* **Device-bound.** Clearing site data or switching browsers loses access; runs stay on the server forever.
* **Cost O(#runs).** Each request scans every JSON in `results/` (summaries cached; each matching run is fully parsed again to read plan #1).
* **No deletion** endpoint or UI.
