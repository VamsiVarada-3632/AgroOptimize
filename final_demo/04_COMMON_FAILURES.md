# 04 – Known limitations and how to answer

| # | Limitation | Why it exists | If the examiner asks |
|---|---|---|---|
| 1 | Only one report year (2024-25); the year dropdown has one option | Only the 2024-25 Season & Crop Report was loaded; earlier district-level reports are not in the dataset | "We use only official data. Adding earlier reports is a data task, not a code change – the pipeline already takes a year parameter." |
| 2 | District level, not farm level | Official statistics are published per district | "Recommendations are for a typical farm in the district. Farm-level soil tests would refine it; the Soil Health Card portal is district-aggregated." |
| 3 | Fuzzy stage runs only where an official reservoir reading exists (9 districts, Rabi; none in Kharif) | The WRD daily reservoir record starts 1 Jan 2025 and not every district has a mapped reservoir | "Where the evidence is missing we skip the adjustment and say so on screen, instead of assuming a storage level." |
| 4 | Chennai and The Nilgiris produce no plan (HTTP 400) | Fewer than two crops have complete official data (yield, TNAU dose, MSP, CACP cost) | "The optimiser needs at least two complete crops. Chennai is urban; for the Nilgiris most crops lack an official dose or irrigation figure." |
| 5 | Pollachi is not a district | It is a taluk of Coimbatore; data is published per district | "The app explains this and points to Coimbatore." |
| 6 | Weather, mandi prices, fertiliser prices, crop calendar, cotton and rice | No official dataset loaded (IMD feed, Agmarknet, Dept of Fertilizers, TNAU calendar, kapas/paddy conversion factors) | "These nine features are listed on the Official Data page as disabled. We chose 'Official Data Not Available' over estimates." |
| 7 | Market price criterion always "Official Data Not Available" | No official mandi price dataset | Same as 6; MSP is shown separately as the official price floor |
| 8 | Different crop mix on the live site than on the slides | NSGA-II uses random mutation; arm64 macOS and x86-64 Linux differ in the last floating-point bits, so the search takes a different but equally good path | "Results are reproducible on the same platform – two production runs gave identical fingerprints. Quality is the same: over 12 district-seasons the live fronts had 0.7 % higher hypervolume on average (DEPLOYMENT_REPORT §4)." |
| 9 | Optimisation ≈10 s and simulation ≈70 s on the live site | Free hosting plan with a fraction of a CPU; locally 0.28 s and 2.9 s | "It's the hosting tier; the algorithm itself runs in under a third of a second." |
| 10 | A simulation request occasionally got no answer (2 of 7 smoke runs) | Not reproducible on demand; the instance did not restart; needs Render logs | "Seen only on the free tier under repeated heavy load; the request itself succeeds in ≈70 s." |
| 11 | Browser Back button leaves the app | The app has no URL routing (single-page state in local storage) | "Navigation is through the sidebar; reopening the site returns to the last page." |
| 12 | Offline on a page never opened shows Chrome's offline page | The page's code is downloaded on first use | "Pages already opened show a clear 'couldn't reach the server' message." |
| 13 | Login and OTP are a demo | No authentication backend; accounts are stored in the browser | "Out of scope for this research prototype; runs are scoped per browser." |
| 14 | Language switcher has no translations | Not implemented | "Planned; the content is English." |
| 15 | Saved runs disappear after a server restart | Free plan has no persistent disk | "A paid disk or database keeps them; the code already supports a results directory setting." |
| 16 | No field validation | No farm trials were run | "This is decision support verified on software and data; agronomic validation with farmers is future work." |
| 17 | Some backend sentences say "irrigation water" | Older wording in generated text; the objective is irrigated area | "The value is irrigated hectares; the label is legacy wording." |
| 18 | Fertiliser-cost scenario returns HTTP 501 | No notified fertiliser prices | Covered by 6 |
| 19 | Rice excluded although it is a major crop | Official yield is in rice, MSP/cost in paddy; no official milling factor loaded | "We don't apply an assumed milling or ginning conversion factor; that would be an estimate." |
| 20 | The PPT numbers (ragi 82.5 %) differ from the live demo | Slides were produced on a Mac (see 8) | "Both are real runs of the same code on different platforms." |
