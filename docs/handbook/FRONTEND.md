# Frontend

`stitch_agrooptimize_app/` – React 19.2, Vite 8.2, Tailwind CSS 4.3 (via `@tailwindcss/vite`), oxlint. ~5,200 lines in `src/`. No router, no state library, no chart library (all charts are hand-written SVG), no test framework. Visual design originates from Google Stitch mock-ups (the `*/code.html` folders) and the token spec `agrooptimize_structural_system/DESIGN.md`.

```bash
cd stitch_agrooptimize_app
npm install
npm run dev                                   # http://localhost:5173, talks to http://localhost:8000
VITE_API_BASE=http://localhost:8010 npm run dev   # point at another backend
npm run lint && npm run build                 # oxlint (0 warnings) + production build to dist/
```

## 1. Application shell (`src/App.jsx`)

| State | Stored | Purpose |
|---|---|---|
| `currentView` | `localStorage.agro_currentView` | which page renders: onboarding, login, register, profile-setup, dashboard, analytics, comparison, run-optimization, history, reports, settings |
| `user` | `localStorage.agro_user` | profile `{fullName, phoneNumber, email, location, landSize, primaryCrop, avatar, season}` |
| `selectedLanguage` | memory | en/hi/ta – **no translations exist**; only highlights the chosen option |
| `dashboardLayout` | memory | 'sidebar' / 'topbar' |
| `activePlanId` | memory | Comparison's "Select This Plan" |
| `backendOnline` | memory | result of one `GET /health` at start-up (footer dot) |

Guards: a shell view without a valid district (`DISTRICTS.includes(user.location)`) redirects to profile-setup (or onboarding when no user). `handleAuthSuccess` goes to the dashboard only for a login with a complete profile; otherwise profile-setup. Logout clears the two keys and returns to onboarding (the demo password digest and `client_id` are kept).

Layouts: fixed 256 px sidebar (desktop, default), sticky top bar (desktop, toggle on the dashboard), mobile header + slide-in drawer (<768 px). Footer shows backend reachability.

## 2. API layer (`src/services/api.js`)

* `API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'`.
* Constants `DISTRICTS`, `SEASONS`, `PREFERENCES` mirror backend config.
* `extractDistrict(str)` → first district name contained in the string, else "Coimbatore".
* `getOrCreateClientId()` → `crypto.randomUUID()` stored as `agro_client_id`; sent with dashboard, history and farm-plan calls.
* `ApiError {status, detail}`, `describeApiError(err)`, `BACKEND_UNREACHABLE_MSG` (dev: how to start uvicorn; prod: plain-language) – added 2026-09-29.
* Methods: `checkHealth, getCatalog, getWeather, getDashboard, getHistory, getSoilProfile, getResult, getPlans, getComparison, getFuzzyComparison, runOptimization`. `runOptimization` maps `land_area_ha→total_land_ha`, `budget→budget_rs` and always sends `save_results: true`.

`src/utils/download.js` (added): `downloadFile(name, text, mime)`, `toCsv(rows, columns)` (quotes and neutralises `= + - @` prefixes in text cells), `slug()`.

## 3. Pages

### OnboardingView (no shell)
2 s splash (logo + typewriter), then a 4-slide scroll-snap carousel (two stock images from `googleusercontent.com`, a static "Balanced / Max Yield / Safe" illustration, and Create Account / Log In). Language menu (English/हिन्दी). Canvas `ParticleBackground`. No API calls.

### AuthView (no shell) – demo authentication, device-local only
Sub-views: login (phone or email tab + password), register-1 (name, optional email, phone with `CountryCodeModal`, password ≥ 8 chars), register-2 (district from `DISTRICTS`, land size ≥ 0.5 ha, primary crop from `/api/catalog` or a fallback list), otp. The OTP is generated in the browser and shown in a fake "Messages" toast with an Auto-fill button – **no SMS is sent**. Login verifies only the password against the digest stored in `localStorage` (the phone/email typed at login is not checked). Since 2026-09-29 the password is stored as SHA-256 (`agro_register_password_sha256`), migrating any legacy plaintext entry.

### ProfileSetupView (no shell)
Step 1 name + avatar (FileReader → data-URL stored in `localStorage`, can be large), skippable. Step 2 district, current season, primary crop, land size (ha). Step 3 "Profile complete" (was "Verification completed" – nothing is verified). Calls `/api/catalog`.

### DashboardView
Calls in parallel: `getWeather(user.location)`, `getDashboard(user.location)`, `getWeather` × 4 districts. Renders: time-of-day greeting; `DataSourceNotice` (historical); **estimated-data banner** when `data_year_estimated`; 4 KPI cards (Active Plans, Estimated Yield + trend, Water Utilization bar + label, Soil Health + status) – each card navigates to Comparison/Analytics on click; Crop Allocation Overview (revenue shares); Recommended Actions with local-only "Schedule" toggles; weather card with Local / Districts tabs (live vs "Historical estimate" wording from `source`); Quick Links. Skeleton loaders per section; failure text per section.

### AnalyticsView
Calls `getPlans`, `getSoilProfile`, `getFuzzyComparison` for `user.location` (always 5 ha, current season, latest year – the user's land size is **not** passed). Renders KPI row (Valid Plans, Min Yield Target, Water Limit, Soil Suitability), an SVG cost-vs-yield scatter (500×300 viewBox, hover tooltip, gold recommended point, faded non-compliant points), three range sliders (max cost/ha, min yield/ha, max water ML/ha) with reset, "Best Compliant Plan" (cheapest compliant), a hypervolume convergence line chart, and the fuzzy vs non-fuzzy table. **Export** downloads a CSV of all plans with a `meets_current_constraints` column (was an `alert()`).

### ComparisonView
Calls `getComparison(user.location)`. Renders a 6-axis SVG radar (selected plan filled, weighted recommendation dashed), a metrics table (crops, t/ha, ₹/ha, **Env. Impact/ha** with relative bar, water label), the selected plan's crop allocations (% and ha), a generic "Getting Started" 2-step template (clearly labelled as generic), an "Adjust Weights" modal (yield/cost/water sliders re-ranking A/B/C), and **Export CSV** (A/B/C metrics + radar). Removed: fabricated "Plots 1, 2, 4" labels, "View Full Calendar" and "Activated Plan" alerts, arbitrary ₹50,000 red threshold, inverted "n/20" impact.

### RunOptimizationView
Form: district (defaults to profile district, warns when different), season, year ("Latest available" or catalog years), land (≥0.5 ha), optional budget, preference. Submit fires `runOptimization` immediately and shows a full-screen 4-stage progress animation on fixed timers (≈0.9 + 3×1.3 + 0.9 s ≈ 5.7 s minimum, independent of the real ≈0.3 s run); then shows the top plan (t/ha, ₹/ha, confidence, trade-off summary, estimated-year note) with Run Another / View in History / Generate Report. Errors: 4xx → backend's `detail`; network → unreachable message.

### HistoryView
Calls `getHistory(user.location)` (client-scoped). Search box (matches season text), year filter, timeline cards (season, date, target yield, estimated cost, status), details modal (plans count, preference, fuzzy confidence/risk %). Empty state links to Run Optimization.

### ReportsView
Calls `getHistory`; lists this browser's saved runs; "Generate Report" fetches `getResult(run_id)` and adds a card to "Recently Generated" (memory only – lost on navigation). Each card: **Download report** (plain-text report built from the saved run – see [REPORT_PIPELINE.md](REPORT_PIPELINE.md)) and **Copy summary** (clipboard). Both were `alert()` stubs.

### SettingsView
Profile (name, email, phone, avatar, district dropdown, land size, primary crop) → `onUpdateUser` (localStorage only) with an inline "saved on this device" status; language buttons; notification toggles (local state only, nothing is sent); mock Google-link section now labelled "Demo only"; logout.

## 4. Shared components

| Component | Used by | Notes |
|---|---|---|
| `DataSourceNotice` | Dashboard, Analytics, Comparison | Explains historical vs live-generic vs personalised |
| `CountryCodeModal` | AuthView | searchable country list |
| `AccountAuthOverlay` | SettingsView | mock consent dialog |
| `ParticleBackground` | Onboarding | canvas animation |
| `SuccessCheckSvg` | ProfileSetup | animated check |

## 5. Styling system

`src/index.css` defines Tailwind v4 `@theme` tokens: Material-3 colour roles (primary `#005226`, secondary `#795900`, surface scale, error), font families (Montserrat headlines, Inter body), a type scale (`headline-lg`, `body-md`, `label-sm` …), spacing (`gutter`, `touch-target-min` 48 px), shadows (`soft`, `ambient`) and keyframes (`fadeIn`, `slideIn`, `shimmer`, typewriter). Icons are the Material Symbols web font loaded from Google Fonts; if that request fails the icon names render as literal words (observed in testing).

## 6. Loading, empty and error states

Every data section has a pulse skeleton while loading, an explicit empty state, and a failure message (now the shared `BACKEND_UNREACHABLE_MSG`, or the backend's own `detail`). The app never substitutes fabricated data on failure (an explicit design rule in the codebase comments).

## 7. Strengths and weaknesses

Strengths: consistent design tokens; honest empty/error states; single API module; cancellation guards on every effect; responsive layout with mobile drawer; minimal dependencies.

Weaknesses (details in [UI_UX_REVIEW.md](UI_UX_REVIEW.md) and [TECHNICAL_DEBT.md](TECHNICAL_DEBT.md)): no URL routing; no tests; inaccessible clickable `<div>` cards and icon-only buttons; language switcher does nothing; Analytics/Comparison ignore the user's land size and budget; simulated progress timing; several external image/font dependencies; large views (AuthView 700 lines, AnalyticsView 600) mixing data, layout and chart code.
