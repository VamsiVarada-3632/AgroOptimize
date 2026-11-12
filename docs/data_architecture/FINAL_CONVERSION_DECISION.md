# Final decision: Rice and Cotton remain disabled

**Decision (12 Nov 2026):** rice (paddy <-> rice) and cotton (kapas <-> lint) stay excluded from optimisation. No official document found explicitly authorises a conversion for yield statistics, MSP or cost of cultivation. Nothing is estimated or assumed. `UNIT_BASIS_MISMATCH` in `app/datasets/units.py` implements the exclusion; `data/official/raw/conversion_table.csv` records the rice norm as *not applicable* (`verified_applicable_to_dataset_units = no`).

## 1. Why the question arises
| Quantity | Official basis |
|---|---|
| Yield / production (Season & Crop Report) | Rice: "in terms of Rice"; Cotton: "bales of 170 kg lint", yield "kg lint / ha" |
| MSP (Cabinet / PIB notifications) | per quintal of **Paddy**; per quintal of cotton (medium/long staple) |
| Cost of production (CACP, as published with the MSP release) | per quintal of the MSP commodity (paddy; kapas) |

Revenue = yield x MSP and cost = cost/quintal x yield would mix commodities (rice with paddy, lint with kapas), overstating or understating by roughly a factor of three. A conversion factor is therefore needed, and it must be official.

## 2. Acceptance test
A document is accepted only if it (a) is issued by an official body, (b) states the paddy-rice or kapas-lint ratio, and (c) says the ratio is meant for agricultural statistics, economics, procurement or cost calculation. General milling ratios, industry averages and research papers are excluded.

## 3. Evidence reviewed (priority order)
| # | Source | Document / page | Finding | Accepted? |
|---|---|---|---|---|
| 1 | DES Tamil Nadu | Statistical Hand Book of TN 2022-23, Agriculture chapter (pp 108, 117, 122, 129) | Labels "Paddy - In terms of Rice", "Cotton - bales of 170 Kg lint". **No ratio, no method.** | No |
| 2 | TN Season & Crop Report | 2012 report (TNAU copy) pp 26, 36, 47: "In terms of Rice Production", "Production in bales of 170 kg lint each", "Cotton: ... (Yield rate in terms of lint)"; 2021 report text has no note either | Units declared; **no conversion stated** | No |
| 3 | Dept of Agriculture & Farmers Welfare | MSP notifications / PIB releases 2021-2025 (OCR of the four scanned notifications, text of the 2024-25 and 2025-26 releases) | MSP per quintal of Paddy and cotton; cost data note: "not separately compiled for Paddy (Grade A) ... Cotton (Long staple)". **No conversion** | No |
| 3b | DA&FW / GoI DES | *Agricultural Statistics at a Glance* 2022, 2023 | Site blocks the fetch tool (robots.txt) - **not read** | Not verifiable |
| 4 | CACP | Price Policy reports | cacp.da.gov.in unreachable (client error) and search returned no report text - **not read** | Not verifiable |
| 5/6 | FCI / Ministry of Consumer Affairs, Food & PD | PIB release 27 Oct 2024 (PRID 2068671): "the existing 67% OTR (Out Turn Ratio from paddy to rice) set by FCI" | A 67% milling out-turn ratio exists for procurement/custom milling. The primary FCI/DFPD order was **not located**; the PIB text is a passing reference, silent on MSP, cost of cultivation or yield statistics | See section 4 |
| 5/6 | Ministry of Consumer Affairs, Food & PD | PIB release 14 Oct 2024 (PRID 2064778) | OTR "discussed"; "A study on OTR and Driage of Paddy is ongoing at IIT Kharagpur" - the ratio is under review | See section 4 |
| 5 | CAG of India (audit of FCI/DFPD) | Report 31 of 2015, ch. 2, footnote 17, p 13 (also pp 21, 27) | "Out-turn Ratio ... 67 per cent of raw rice and 68 per cent of par-boiled out of one quintal paddy was **recommended by Gokak Committee during 1994**" - a recommendation, applied by the Ministry when fixing cost sheets for milling | See section 4 |
| 7 | Cotton Corporation of India | G&P tender 2020-21, pp 13, 17 | Contractual *minimum lint %* for one branch (31.80-33.70 %), monthly - a job-work term, not a crop conversion | No |
| 8/9 | ICAR / CICR | AICRP Cotton annual report 2024-25 (p 31 and trial tables); CICR dataset tables | Only variety-specific ginning outturn percentages (ranges such as 22-44 %). No general factor | No |
| 8 | TNAU (ICAR system) | Crop Production Guide, PDF pp 265-266 | Variety-specific ginning outturn (MCU 5 34 %, MCU 7 33.2 %, MCU 12 34.8 %, CO 14 34.8 %, SVPR 2 36.4 %, KC 2 37.5 %) and seed-cotton yield per variety. Not a district-level or statistical conversion | No |
| 10 | Ministry of Textiles | PIB 19 Dec 2025 (PRID 2206688): production "in lakh bales of 170 Kg each"; MSP Rs 7,710 / 8,110 per quintal | Bale weight only; no kapas-lint ratio. Annexure-VII cotton note blocked by robots.txt - **not read** | No |

## 4. Rice: why the 67 % out-turn ratio is not accepted
1. **Scope.** The ratio is a milling/procurement norm for custom-milled rice delivered to the Central Pool. No document found says it governs how the Season & Crop Report derived "in terms of Rice" yields, nor how paddy MSP or cost of cultivation is restated per quintal of rice. Applying it to our yields or prices would be an assumption about another body's method.
2. **Authority not established.** The only primary-looking text is a CAG footnote describing a 1994 committee *recommendation* and a PIB sentence attributing the figure to FCI. The operative DFPD/FCI order was not found.
3. **Currency.** In October 2024 the Ministry itself reported an OTR study under way at IIT Kharagpur, so the 67 % value is not a settled constant.
4. **Direction of error.** Our inputs are Tamil Nadu district yields; the owner of that method is DES Tamil Nadu, which does not publish it.

## 5. Cotton: why nothing qualifies
Official statistics fix the *reporting unit* (bale = 170 kg lint) but publish no kapas-lint ratio. Every ratio found is variety-specific (CICR, TNAU) or contractual (CCI). Without the variety mix per district, any single factor would be an estimate.

## 6. Limits of this search (stated for the viva)
Not readable with the available tools: GoI *Agricultural Statistics at a Glance* (robots.txt), CACP Price Policy reports and website, Ministry of Textiles Annexure-VII note, the FCI/DFPD out-turn orders. Absence of evidence in documents read is therefore reported as "no explicit authorisation found", not "none exists".

## 7. What re-enables each crop
- **Rice:** a written statement from DES Tamil Nadu of the factor used for "in terms of Rice", or a DFPD/FCI/CACP document extending the OTR to MSP/cost restatement. Then set `verified_applicable_to_dataset_units = yes` in `conversion_table.csv`, remove `rice` from `UNIT_BASIS_MISMATCH`, and convert **prices** (never estimate yields).
- **Cotton:** an official kapas-lint ratio for statistics/MSP (CACP, CCI, Ministry of Textiles, DES) or district variety-wise kapas yields from the Season & Crop Report.
- Suggested route: RTI / e-mail to DES Tamil Nadu (Chennai), CACP and CCI asking exactly this question.

## 8. Viva answer in one line
"Official sources define the units but never authorise converting between them for yield, MSP or cost; the one ratio that exists (67 % out-turn) is a procurement norm of uncertain scope and under review, so using it would be an assumption - rice and cotton are therefore disabled rather than approximated."
