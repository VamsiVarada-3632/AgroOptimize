# UI / UX Review

Reviewed by reading every view and by driving the running app in Chrome (2026-09-29, backend on :8010, Vite dev server). "Fixed" items were changed in this pass; everything else is a recommendation.

## 1. What works well
* Coherent visual system (Material-3 colour roles, one type scale, consistent cards and skeletons).
* Honest data provenance: `DataSourceNotice` on Home/Analytics/Comparison distinguishes historical, live-generic and personalised results; explicit empty and error states everywhere; no fabricated fallback data.
* Clear primary task: Run Optimization is the single place that creates saved results, and History/Reports both route users there from their empty states.
* Responsive shell (sidebar, optional top bar, mobile drawer).

## 2. Findings by screen

| ID | Screen | Issue | Status |
|---|---|---|---|
| U-1 | Reports | "PDF" and "share" buttons only showed `alert()` messages claiming a download / copied link | **Fixed**: real .txt report download + clipboard copy with visual confirmation |
| U-2 | Analytics / Comparison | "Export" buttons were `alert()` stubs | **Fixed**: real CSV downloads |
| U-3 | Onboarding → Register → Profile | District, land and crop are asked in Register step 2 and again in Profile Setup | Open – skip Profile step 2 when already provided |
| U-4 | Comparison | "Land Impact n/20" displayed a goodness score as impact (gentlest plan showed the largest number) | **Fixed**: real per-ha impact, lower = better, tooltip |
| U-5 | Comparison | Allocation cards showed invented "Plots 1, 2, 4" labels | **Fixed**: removed; heading renamed "Crop Allocations" |
| U-6 | Comparison | "View Full Calendar" and "Select This Plan" produced alerts; the "Irrigation Schedule" looked computed | **Fixed**: alerts removed; section renamed "Getting Started" and labelled as a generic template |
| U-7 | Comparison | Cost cells turned red above an arbitrary ₹50,000/ha | **Fixed**: removed |
| U-8 | Comparison | Radar axes normalised over only three plans exaggerate differences (always a 0 and a 100) | Open – show absolute values in tooltips, or normalise against the whole front |
| U-9 | Comparison | Two recommendations can disagree: TOPSIS "recommended" Plan A vs the weight-slider "Rec" badge (default 50/50/50 picked Plan C for Coimbatore) | Open – initialise sliders to reproduce TOPSIS, or label the badge "Your weighting" |
| U-10 | Dashboard | "Good Morning" at any time | **Fixed** (time-of-day greeting) |
| U-11 | Dashboard | "+3.0 %" yield trend and all KPIs came from estimated 2024 data with no indication | **Fixed**: warning banner when `data_year_estimated` |
| U-12 | Dashboard | "Estimated Yield" averages all crops (sugarcane with cotton) → a number no farm achieves | Open – show yield for the user's primary crop, or per crop |
| U-13 | Dashboard | "Water Utilization … Optimal" when irrigation's share of demand ≥70 % – label implies a judgement the metric can't support | Open – rename "Irrigation share of water demand", drop the badge |
| U-14 | Dashboard | "Schedule" buttons only toggle a local flag; nothing is scheduled or persisted | Open – rename "Mark as planned" or persist |
| U-15 | Dashboard | Weather CSV fallback labels month averages as "Mon, Tue, …" | Open (backend) – label with month names when `source` is historical |
| U-16 | Analytics | KPI "Avg Yield Target" actually showed the min-yield slider value | **Fixed** ("Min Yield Target") |
| U-17 | Analytics / Comparison | Always optimised for 5 ha and the current calendar season – the user's land size and chosen season are ignored | Open – pass `user.landSize`; add a season selector |
| U-18 | Analytics | "Best Compliant Plan" is the cheapest compliant plan, while the gold dot is the TOPSIS pick – two notions of "best" | Open – rename "Cheapest plan meeting your limits" |
| U-19 | Analytics | Tooltip position uses `window.innerWidth` heuristics; can overflow on small screens | Open |
| U-20 | Run Optimization | Fixed ≈5.7 s staged animation regardless of the real ≈0.3 s run; stages don't reflect real progress | Open – tie to the request, 1 s minimum |
| U-21 | Run Optimization | Backend 400s (e.g. no data) were reported as "Couldn't reach the backend" | **Fixed**: shows the backend's reason |
| U-22 | All | Production users saw "Confirm uvicorn is running on port 8000" | **Fixed**: environment-aware message |
| U-23 | Footer | "Offline — showing cached data" (there is no cache) | **Fixed**: "Server unreachable — live data unavailable" |
| U-24 | Profile setup | "Verification completed … successfully verified" though nothing is verified | **Fixed**: "Profile complete" / "Save Profile" |
| U-25 | Settings | Blocking `alert()`s; "Google account linked successfully!" with no Google involvement | **Fixed**: inline status (aria-live), "Demo only" note |
| U-26 | Auth | On-screen "SMS" toast reveals the OTP; login ignores phone/email | Open – label "Demo code" clearly |
| U-27 | Global | Language switcher (English/हिन्दी/தமிழ்) changes nothing | Open – hide until translations exist, or implement i18n |
| U-28 | Global | No URL routing: Back button leaves the app, pages can't be bookmarked or shared | Open – react-router |
| U-29 | Reports | Generated reports vanish when leaving the page | Open – persist in `localStorage` or regenerate on demand |
| U-30 | History | Search matches only the season text; no sort control; no delete | Open |

## 3. Accessibility

| Issue | Where | Recommendation |
|---|---|---|
| Clickable `<div>` cards (KPI cards, avatar, profile card) not keyboard-focusable, no role | Dashboard, App shell | use `<button>` or add `role="button" tabIndex=0` + key handlers |
| Icon-only buttons without accessible names (menu, close, share) | App, modals | `aria-label` (added for the Reports copy button) |
| Material Symbols ligatures read aloud as words ("water_drop") | everywhere | `aria-hidden="true"` on decorative icons |
| Form labels not associated (`<label>` without `htmlFor`) | Auth, Run, Settings | pair with `id` |
| Modals lack focus trap, `role="dialog"`, Escape-to-close | Comparison weights, History detail, Country modal | adopt a dialog primitive |
| Charts are SVG without text alternatives | Analytics, Comparison | add `<title>`/`aria-label` and a data-table toggle (CSV export now exists) |
| Colour-only status (valid vs faded points, gold recommended) | Analytics | add shape/legend |
| Status messages | Settings | now `role="status" aria-live="polite"` |

## 4. Onboarding and empty states
Good: every empty state names the next action (Run Optimization). Improve: a first-run checklist on the dashboard ("1. Run your first optimisation · 2. Compare plans · 3. Download a report"), and explain terms (Pareto front, TOPSIS, hypervolume) via small info tooltips on Analytics.

## 5. Wording glossary suggestions

| Current | Suggested |
|---|---|
| Water Utilization | Irrigation share of water demand |
| Estimated Yield | Average crop yield in district (all crops) |
| Soil Health % | Soil fertility index |
| Land (radar) | Fertiliser & pumping impact |
| Market (radar) | Weather independence |
| Risk (radar) | Irrigation safety (district-wide) |
