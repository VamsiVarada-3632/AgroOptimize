# Rice <-> paddy and lint <-> kapas: official conversion search

Policy: never estimate, never hardcode, official sources only. Table: `data/official/raw/conversion_table.csv`; loader: `app/datasets/conversion_loader.py`; tests: `tests/datasets/test_conversion.py`.

## Searched
1. Downloaded datasets (`crops_by_district`, `crops_state_series`, etc.): units only (`kg / ha`, `bales of 170 kg lint`, `kg lint / ha`); no factor.
2. Downloaded PDFs (MSP notifications 2021-26, PIB release, Copra report): text-less scans or no conversion text.
3. TN Season & Crop Report (DES TN 2025 chapter 4; TNAU copy 2021): labels "Paddy - in terms of Rice" (pp. 108, 117, 129) and "Cotton in bales of 170 kg lint" (pp. 108, 122); **states no factor**.
4. CACP (cacp.da.gov.in): not reachable through the search tools; no factor retrieved. TODO: read the Price Policy reports directly.
5. ICAR / CICR: only variety-specific ginning % ranges (22-44 % etc.), not a general factor.
6. Ministry of Textiles cotton note: blocked by robots.txt for the fetch tool; not read. CCI tender (2020-21): a contractual minimum lint % for one branch, not a crop conversion - not used.

## Result
| Pair | Official factor found? | Detail |
|---|---|---|
| paddy -> rice | **Yes (milling norm)** | 0.67 (raw/common rice; 0.68 par-boiled) - PIB release 27-Oct-2024 (MoCAF&PD, "67% OTR set by FCI"); CAG Report 31 of 2015 ch.2 fn.17 p.13 (Gokak Committee 1994) |
| kapas <-> lint | **No** | no general official ginning outturn located |

## Status in the application
- **Cotton stays disabled.** No row in the table.
- **Rice stays disabled** (`verified_applicable_to_dataset_units = no`). 0.67 is the official procurement milling norm; no source seen states that the Season & Crop Report's "in terms of rice" yield was derived with 0.67, so applying it to the MSP/CACP basis would be an assumption. Decision needed: accept 0.67 as the official paddy->rice basis (flip the flag to `yes`, then wire `conversion_factor("rice","paddy","rice")` into the MSP/cost prices), or obtain DES TN's stated method.
