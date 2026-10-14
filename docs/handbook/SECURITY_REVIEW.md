# Security Review

Scope: backend API, frontend, deployment configuration. Threat model: a public demo deployment (Vercel + Fly.io) with no real user accounts and no sensitive agricultural data, but with user-typed personal data (name, phone, email) in browsers and per-browser run histories on the server.

## 1. Summary

| ID | Finding | Severity | Status |
|---|---|---|---|
| S-1 | `GET /api/results` published every run's `client_id`, the only key scoping History → any visitor could read any other visitor's history | **High** | **Fixed** (redacted, test added) |
| S-2 | `run_id` from the URL was joined into a filesystem path without validation | Medium (Starlette blocks `/`, so no traversal was demonstrated, but defence was missing) | **Fixed** (allow-list regex, test with `../`) |
| S-3 | Demo password stored in plaintext in `localStorage` | Medium | **Fixed** (SHA-256 digest, legacy migration) |
| S-4 | No authentication/authorisation anywhere; `client_id` is a bearer token in query strings (logged by proxies) | Medium (by design for a demo) | Open – document; real auth if ever deployed for real users |
| S-5 | `POST /api/farm-plans` is unauthenticated, writes 4 files per call, and can request pop 300 × 500 generations while holding the global run lock | Medium (DoS / disk fill) | Open – rate limit, lower caps, retention |
| S-6 | No rate limiting on any endpoint; each dashboard load proxies 5 calls to Open-Meteo | Low–Medium | Open |
| S-7 | `saved_files` in responses exposes absolute server paths | Low | Open – return relative names |
| S-8 | Same-second `run_id` collision overwrote another user's run files | Medium (integrity) | **Fixed** (exclusive reservation) |
| S-9 | Unbounded `client_id` persisted verbatim to disk | Low | **Fixed** (≤128 chars) |
| S-10 | Negative/zero land or budget accepted by dashboard query params (division by zero → 500/503) | Low | **Fixed** (422) |
| S-11 | CORS `allow_credentials=True` with `*` methods/headers although no cookies are used | Low | Open – set False |
| S-12 | Fake OTP displayed on screen; login does not check phone/email | Informational (demo) | Documented in UI |
| S-13 | Container runs as root; `gcc` in the runtime image; test tools installed | Low | Open |
| S-14 | CI action `superfly/flyctl-actions@master` unpinned (supply-chain) | Low | Open – pin SHA |
| S-15 | Frontend loads images/fonts from third-party hosts (googleusercontent, Google Fonts) → visitor IP disclosure, availability risk | Low | Open – self-host |
| S-16 | Personal data (name, phone, email, photo) kept in `localStorage` in plain JSON | Low (device-local) | Documented; clear on logout (currently only `agro_user` is removed – it is) |
| S-17 | CSV exports could carry spreadsheet formulas | Low | **Mitigated** (`toCsv` prefixes `= + - @` text cells) |
| S-18 | `GET /api/results/{run_id}` needs no `client_id`; run ids are predictable (district_season_year_timestamp) | Low–Medium | Open – require matching `client_id` or add a random suffix |

## 2. Checks with no findings

| Area | Result |
|---|---|
| Hard-coded secrets | None in code. `FLY_API_TOKEN` is a GitHub secret. `.vercel/project.json` contains only project/org ids (not secrets). `.env.production` contains only the public API URL |
| Injection | No SQL, no shell, no `eval`; pandas filters use equality on validated values; `Literal` for preference |
| Deserialisation | Only `json.loads` of files the server wrote |
| XSS | React escapes all rendered strings; no `dangerouslySetInnerHTML`; avatars are data-URLs rendered in `<img>` |
| Input validation | Pydantic on POST body; `Query` bounds on dashboard params (added); location/season allow-listed |
| Error leakage | 503 detail includes the exception message (`live NSGA-II optimisation failed (…)`) – acceptable for a demo, remove for production |
| Dependency CVEs | Not audited here (no lock file); run `pip-audit` / `npm audit` in CI (TODO T-16) |

## 3. Recommendations if this ever serves real farmers
1. Real authentication (e.g. OTP via a provider, or OAuth) and server-side users; replace `client_id` scoping.
2. Rate limiting (e.g. `slowapi`) and a per-client quota on saved runs; retention policy.
3. Run as a non-root user; slim image; pinned dependencies with `pip-audit` in CI.
4. Remove `saved_files` absolute paths; add security headers on Vercel (CSP, `X-Content-Type-Options`, `Referrer-Policy`).
5. Privacy notice for phone/email even though they stay on-device.
