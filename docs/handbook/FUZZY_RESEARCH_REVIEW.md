# Fuzzy Research Review

Comparison of the AgroOptimize Mamdani system with established fuzzy-systems literature and agricultural reference standards. Only recommendations supported by these sources are made; no rule or agronomic relationship is invented. Measurements quoted are from [FUZZY_SYSTEM_ANALYSIS.md](FUZZY_SYSTEM_ANALYSIS.md). References are well-known foundational works; confirm page numbers against the publisher's record before citing them in the paper.

## 1. Inference scheme

| Topic | Literature | AgroOptimize | Assessment |
|---|---|---|---|
| Mamdani inference (min implication, max aggregation) | Mamdani & Assilian (1975) [2] | scikit-fuzzy Mamdani, min / max | Consistent with the paper's stated method |
| Interpretability of rule bases | Guillaume (2001) [7]: compact, non-redundant, complete rule bases with distinguishable sets | 6 of 26 rules subsumed; complete 3×3 rainfall×water grid | Redundancy should be reported (done) and, in a future version, resolved |
| Alternatives | Takagi–Sugeno (1985) [3] smoother, data-tunable; ANFIS (Jang 1993) [4] learns MFs from data | Not applicable without outcome data | Appropriate future work once realised yields are available |
| Uncertainty in the MFs themselves | Interval type-2 fuzzy systems (Mendel 2001) [8] | Type-1 | Optional future work; would strengthen "uncertainty" claims |

## 2. Membership functions

| Topic | Literature | AgroOptimize | Recommendation |
|---|---|---|---|
| Triangular MFs | Pedrycz (1994) [5]: triangles are a justified default (good reconstruction, simple) | 15 triangles | Keep triangles; shape is not the problem |
| Coverage of the universe | Lee (1990) [6]: ε-completeness, commonly ε ≥ 0.5 (adjacent sets cross at 0.5) | ε = 0.143 (rainfall), 0.231 (storage, fertility) | Widen overlaps so neighbours cross at 0.5 (M-1) |
| Anchoring sets in domain standards | Fuzzy soil classification (McBratney & Odeh 1997) [9] anchors class boundaries in established survey classes | Rainfall sets do not match IMD categories; 9 IMD-normal profiles labelled deficit/surplus | Align rainfall crossings with IMD's ±19 % "normal" band [12]; anchor fertility sets to Soil Health Card ratings [13] when the index is mapped to them |

## 3. Defuzzification

| Topic | Literature | AgroOptimize | Recommendation |
|---|---|---|---|
| Centroid properties | Van Leekwijck & Kerre (1999) [10]: centroid is continuous and widely used but cannot reach the universe extremes | Range limited to [0.150, 0.883] yield, [0.117, 0.867] risk | Document the ceiling (done). Changing the method (e.g. extending output sets beyond the universe) would change every result — versioned change only |

## 4. Agricultural grounding

| Input | Reference | Relevance |
|---|---|---|
| Rainfall deviation | IMD categories: normal −19 … +19 %, deficient −20 … −59 %, excess +20 … +59 %, large deficient ≤ −60 %, large excess ≥ +60 % [12] | Direct basis for M-1 and for the ±60 % universe (beyond it IMD uses "large" categories — 5 Pollachi Summer profiles are clipped there) |
| Crop water stress / yield response | FAO-56 crop evapotranspiration (Allen et al. 1998) [14]; FAO-33 yield response to water (Doorenbos & Kassam 1979) [15] | Supports modelling rainfall-dependence and irrigation pressure; a future version could replace the fixed 0.4 penalty in `crop_yield_confidence` with an FAO-33 response (Ky) — already listed in RESEARCH_REVIEW.md |
| Soil fertility | Soil Health Card scheme ratings [13] | The fertility index is derived from pH, OC and N/P/K statuses; set boundaries should be traceable to these ratings |

## 5. Decision layer
NSGA-II (Deb et al. 2002) [11] and TOPSIS (Hwang & Yoon 1981) [16] are unaffected: the FIS scales one objective's coefficients. The literature on fuzzy-evolutionary decision support does not require changing that coupling; it does support sensitivity analysis of the fuzzy layer (Saltelli et al. 2008) [17] — the leave-one-out importance and the audit's monotonicity checks are the first steps, and Scenario Simulation already varies the fuzzy inputs.

## 6. Recommendations supported by the review

| ID | Recommendation | Basis | Implemented? |
|---|---|---|---|
| L-1 | Report redundancy, effective rule count and per-rule contribution | [7] | Yes (audit, explanations) |
| L-2 | ε ≥ 0.5 partitions | [6] | Proposed (changes outputs) |
| L-3 | Rainfall sets aligned to IMD categories | [12] | Proposed (changes outputs) |
| L-4 | Keep triangular MFs | [5] | Yes (no change) |
| L-5 | Document centroid ceiling | [10] | Yes |
| L-6 | Sensitivity analysis of the fuzzy layer | [17] | Partly (leave-one-out, monotonicity); global sensitivity proposed |
| L-7 | Data-driven tuning (ANFIS / TSK) once outcome data exist | [3, 4] | Future work |
| L-8 | Type-2 MFs for membership uncertainty | [8] | Future work |

## References
1. Zadeh, L. A. (1965). Fuzzy sets. *Information and Control*, 8(3), 338–353.
2. Mamdani, E. H., & Assilian, S. (1975). An experiment in linguistic synthesis with a fuzzy logic controller. *International Journal of Man-Machine Studies*, 7(1), 1–13.
3. Takagi, T., & Sugeno, M. (1985). Fuzzy identification of systems and its applications to modeling and control. *IEEE Transactions on Systems, Man, and Cybernetics*, 15(1), 116–132.
4. Jang, J.-S. R. (1993). ANFIS: Adaptive-network-based fuzzy inference system. *IEEE Transactions on Systems, Man, and Cybernetics*, 23(3), 665–685.
5. Pedrycz, W. (1994). Why triangular membership functions? *Fuzzy Sets and Systems*, 64(1), 21–30.
6. Lee, C. C. (1990). Fuzzy logic in control systems: Fuzzy logic controller, Parts I and II. *IEEE Transactions on Systems, Man, and Cybernetics*, 20(2), 404–435.
7. Guillaume, S. (2001). Designing fuzzy inference systems from data: An interpretability-oriented review. *IEEE Transactions on Fuzzy Systems*, 9(3), 426–443.
8. Mendel, J. M. (2001). *Uncertain Rule-Based Fuzzy Logic Systems: Introduction and New Directions*. Prentice Hall.
9. McBratney, A. B., & Odeh, I. O. A. (1997). Application of fuzzy sets in soil science: fuzzy logic, fuzzy measurements and fuzzy decisions. *Geoderma*, 77(2–4), 85–113.
10. Van Leekwijck, W., & Kerre, E. E. (1999). Defuzzification: criteria and classification. *Fuzzy Sets and Systems*, 108(2), 159–178.
11. Deb, K., Pratap, A., Agarwal, S., & Meyarivan, T. (2002). A fast and elitist multiobjective genetic algorithm: NSGA-II. *IEEE Transactions on Evolutionary Computation*, 6(2), 182–197.
12. India Meteorological Department. Rainfall categories (departure from the long-period average): normal −19 % to +19 %; deficient −20 % to −59 %; excess +20 % to +59 %; large deficient −60 % or less; large excess +60 % or more. Used in IMD climate summaries, e.g. https://mausam.imd.gov.in/Forecast/marquee_data/IMD%20HQ%20%20Monthly_Clim_Summary_MAR_2023_.pdf
13. Government of India, Soil Health Card scheme — operational guidelines and nutrient rating classes. https://ies.gov.in/arthapedia/concept/soil-health-card-shc
14. Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998). *Crop evapotranspiration — Guidelines for computing crop water requirements*. FAO Irrigation and Drainage Paper 56. FAO, Rome.
15. Doorenbos, J., & Kassam, A. H. (1979). *Yield response to water*. FAO Irrigation and Drainage Paper 33. FAO, Rome.
16. Hwang, C.-L., & Yoon, K. (1981). *Multiple Attribute Decision Making: Methods and Applications*. Springer.
17. Saltelli, A., et al. (2008). *Global Sensitivity Analysis: The Primer*. Wiley.
