# NSGA-II Research Review

The AgroOptimize NSGA-II engine compared with the original algorithm (Deb et al. 2002) and the evolutionary-computation literature, and the literature basis of each change in this work. Measurements are in [NSGAII_PROFILE.md](NSGAII_PROFILE.md); decisions in [NSGAII_IMPROVEMENT_SUMMARY.md](NSGAII_IMPROVEMENT_SUMMARY.md). References are standard works; confirm page numbers against the publisher's record before citing them in the paper.

## 1. Conformance with Deb et al. (2002)

| Element of NSGA-II [1] | AgroOptimize | Assessment |
|---|---|---|
| Fast non-dominated sorting, O(MN²) | pymoo `fast_non_dominated_sort` | ✔ |
| Crowding distance per front, boundary points = ∞ | pymoo `calc_crowding_distance` | ✔ |
| (μ + λ) elitist survival: merge parents and offspring, fill by rank, truncate last front by crowding | pymoo `RankAndCrowding` | ✔ |
| Binary tournament with the crowded-comparison operator (rank, then crowding) | pymoo `comp_by_dom_and_crowding`: dominance between the two, then crowding | Minor variant; identical outcome when both are in the same front, which here is 96–98 % of generations (NSGAII_ANALYSIS.md §4.1) |
| Constraint handling by constrained domination | pymoo: feasibility, then constraint violation, then dominance | ✔ (Deb 2000 constrained-domination principle, as in [1] §VI) |
| Real-coded variation: SBX + polynomial mutation [17, 18] | Single-point crossover p = 0.85 + Gaussian mutation p = 0.12 per gene | As stated in the project's reference paper. SBX/PM are the usual real-coded choice; kept to stay faithful (future work) |
| Mutation rate ~1/n [20] | 0.12 for n = 6–15 genes (1/n = 0.07–0.17) | Within the usual range, but the study finds 0.05 better on this problem (NSGAII_PROFILE.md §4) |
| Population 100, generations problem-dependent | 80 × 200 | Population 160 measurably better, 40 measurably worse; 400 generations no better than 200 |
| Duplicate handling | not part of [1]; pymoo removes exact copies | ✔ (common practice) |
| Termination | fixed generation budget | ✔ (as in [1]) |

**Verdict:** the engine is a correct NSGA-II implementation that follows best practice in its survival, sorting, constraint handling and reproducibility. Its departures are (a) the variation operators, chosen to match the project's paper, and (b) a four-objective problem, for which NSGA-II is known to lose selection pressure [7, 8] — a property of the algorithm choice, not a coding fault.

## 2. Many-objective behaviour

With four objectives the whole population becomes non-dominated within 4–8 generations, after which selection relies on crowding distance alone. This is the documented weakness of Pareto-based MOEAs beyond three objectives (Purshouse & Fleming 2007 [8]; Ishibuchi et al. 2008 [7]); crowding distance is also a poor density estimate in four dimensions (Kukkonen & Deb 2006 [10]). The literature's remedies are reference-point methods (NSGA-III [15]), decomposition (MOEA/D) or archives (Laumanns et al. 2002 [9]). Replacing NSGA-II was out of scope; the accepted improvements work with the algorithm as it is by (a) starting closer to the optimal face of the decision space and (b) reducing disruptive mutation once progress stalls. Both are documented NSGA-II-compatible techniques.

## 3. Literature basis of each improvement

| Improvement | Literature | How it is applied here | Outcome |
|---|---|---|---|
| Adaptive mutation | Parameter control: Eiben, Hinterding & Michalewicz 1999 [3]; adaptive probabilities: Srinivas & Patnaik 1994 [2]; diversity-guided EAs: Ursem 2002 [4] | Starts from p = 0.05 (the parameter study's better value, §5); raised in inverse proportion when allocation diversity falls below half its initial value (cap 0.30); scaled by 0.2 (floor 0.02) once the first-front hypervolume has risen by < 0.01 % in 30 generations | **Accepted** (enhanced) |
| Adaptive crossover | Deterministic parameter control [3]; [2] | Probability 0.95 → 0.70 linearly over the run | Rejected: no measurable effect |
| Knowledge-based initialisation | Seeding MOEAs: Friedrich & Wagner 2015 [5]; seeding with problem knowledge is standard in applied MOO | 20 % of the initial population from the district's candidate crops (dominant-crop plans; land in proportion to fuzzy-adjusted historical yield, yield per rupee and per litre; an even split), multipliers at the lower bound, which is never worse on any objective in this model | **Accepted** (enhanced) |
| Duplicate removal with a tolerance | Duplicate elimination preserves diversity (pymoo [14]) | Rejects offspring within 1e-4 (normalised Euclidean) of another individual | Rejected: no measurable effect beyond pymoo's exact-copy removal |
| Early stopping | Stopping criteria for MOEAs based on indicator stagnation: Martí et al. 2016 [16] | Stops when the first-front hypervolume rises by < 1e-4 (relative) in 30 generations, not before generation 60 | Rejected for enhanced: saves 65 % of the evaluations but lowers quality (HV worse in 117 of 160 paired runs), because the front keeps changing after progress appears to stall (§2). Available as a switch for time-limited use |
| Diversity monitoring | Population entropy and crowding as diversity measures (Zitzler et al. 2003 [21]) | Entropy, allocation diversity, mean crowding, first-front size and duplicate ratio per generation | Implemented (observational, both modes) |
| Runtime profiling | — | Total time, generations, evaluations, Pareto size, time per generation, in the log and the saved run | Implemented (observational, both modes) |
| Code optimisation | — | Vectorised crossover and tournament (same random draws), cached constants, history without deep copies | Implemented (both modes, bit-identical) |

## 4. Evaluation methodology

| Practice | Literature | Applied |
|---|---|---|
| Unary quality indicators on a common normalisation | Zitzler et al. 2003 [21] | Objectives normalised per problem by the reference front's ideal and nadir |
| Hypervolume (Pareto-compliant) | Zitzler & Thiele 1999 [6] | Reference point 1.1 in every objective |
| IGD+ (weakly Pareto-compliant) | Ishibuchi et al. 2015 [11] | Against the reference front: non-dominated union of all fronts of all variants, plus each solution's lower-bound-multiplier copy |
| Spread for > 2 objectives | Generalised spread, Zhou et al. 2006 [12]; spacing, Schott 1995 [13] | Both reported |
| Multiple independent runs, paired non-parametric test | Derrac et al. 2011 [19] | 16 problems × 10 seeds, Wilcoxon signed-rank against the original on the same (problem, seed) |
| Tuning separated from evaluation | standard practice | Parameters tuned on seeds 100–104; the reported study uses seeds 0–9 |

## 5. Parameter review against the literature

| Parameter | Value | Literature guidance | Evidence here (NSGAII_PROFILE.md §4) | Recommendation |
|---|---|---|---|---|
| Population | 80 | NSGA-II commonly 100 [1] | 160 better on HV in 78/80 paired runs (2× evaluations); 40 worse | Keep 80 for the published mode; 100–160 when time allows |
| Generations | 200 | problem-dependent | 400 no better; 100 slightly worse | 200 is adequate |
| Crossover probability | 0.85 | 0.8–0.95 typical [1, 20] | 0.95 ≈ 0.85; 0.6 worse | Keep |
| Mutation probability | 0.12 per gene | ~1/n [20] | 0.05 better in 76/80; 0.25 worse in 74/80 | Lower (≈ 0.05) or adaptive — the enhanced mode adapts it |
| Mutation σ | 0.12 × range | — | 0.05 slightly better; 0.25 worse | Keep, or lower slightly |
| Tournament size | 2 | binary tournament [1] | not varied (pymoo NSGA-II supports only 2) | Keep |
| Crowding distance | standard | weak for ≥ 4 objectives [10] | front saturates by generation 8 | Future: a many-objective density estimator |
| Elitism | (μ + λ) | [1] | — | Keep |
| Stopping | fixed 200 | [16] | stagnation stopping costs quality | Keep fixed for published runs |

## 6. References
1. Deb, K., Pratap, A., Agarwal, S., & Meyarivan, T. (2002). A fast and elitist multiobjective genetic algorithm: NSGA-II. *IEEE Transactions on Evolutionary Computation*, 6(2), 182–197.
2. Srinivas, M., & Patnaik, L. M. (1994). Adaptive probabilities of crossover and mutation in genetic algorithms. *IEEE Transactions on Systems, Man, and Cybernetics*, 24(4), 656–667.
3. Eiben, Á. E., Hinterding, R., & Michalewicz, Z. (1999). Parameter control in evolutionary algorithms. *IEEE Transactions on Evolutionary Computation*, 3(2), 124–141.
4. Ursem, R. K. (2002). Diversity-guided evolutionary algorithms. In *Parallel Problem Solving from Nature – PPSN VII*, LNCS 2439, 462–471. Springer.
5. Friedrich, T., & Wagner, M. (2015). Seeding the initial population of multi-objective evolutionary algorithms: A computational study. *Applied Soft Computing*, 33, 223–230. Elsevier.
6. Zitzler, E., & Thiele, L. (1999). Multiobjective evolutionary algorithms: A comparative case study and the strength Pareto approach. *IEEE Transactions on Evolutionary Computation*, 3(4), 257–271.
7. Ishibuchi, H., Tsukamoto, N., & Nojima, Y. (2008). Evolutionary many-objective optimization: A short review. In *Proc. IEEE Congress on Evolutionary Computation (CEC 2008)*, 2419–2426.
8. Purshouse, R. C., & Fleming, P. J. (2007). On the evolutionary optimization of many conflicting objectives. *IEEE Transactions on Evolutionary Computation*, 11(6), 770–784.
9. Laumanns, M., Thiele, L., Deb, K., & Zitzler, E. (2002). Combining convergence and diversity in evolutionary multiobjective optimization. *Evolutionary Computation*, 10(3), 263–282.
10. Kukkonen, S., & Deb, K. (2006). A fast and effective method for pruning of non-dominated solutions in many-objective problems. In *PPSN IX*, LNCS 4193, 553–562. Springer.
11. Ishibuchi, H., Masuda, H., Tanigaki, Y., & Nojima, Y. (2015). Modified distance calculation in generational distance and inverted generational distance. In *Evolutionary Multi-Criterion Optimization (EMO 2015)*, LNCS 9019, 110–125. Springer.
12. Zhou, A., Jin, Y., Zhang, Q., Sendhoff, B., & Tsang, E. (2006). Combining model-based and genetics-based offspring generation for multi-objective optimization using a convergence criterion. In *Proc. IEEE CEC 2006*, 892–899.
13. Schott, J. R. (1995). *Fault tolerant design using single and multicriteria genetic algorithm optimization*. Master's thesis, Massachusetts Institute of Technology.
14. Blank, J., & Deb, K. (2020). pymoo: Multi-objective optimization in Python. *IEEE Access*, 8, 89497–89509.
15. Deb, K., & Jain, H. (2014). An evolutionary many-objective optimization algorithm using reference-point-based nondominated sorting approach, Part I. *IEEE Transactions on Evolutionary Computation*, 18(4), 577–601.
16. Martí, L., García, J., Berlanga, A., & Molina, J. M. (2016). A stopping criterion for multi-objective optimization evolutionary algorithms. *Information Sciences*, 367–368, 700–718. Elsevier.
17. Deb, K., & Agrawal, R. B. (1995). Simulated binary crossover for continuous search space. *Complex Systems*, 9(2), 115–148.
18. Deb, K., & Goyal, M. (1996). A combined genetic adaptive search (GeneAS) for engineering design. *Computer Science and Informatics*, 26(4), 30–45.
19. Derrac, J., García, S., Molina, D., & Herrera, F. (2011). A practical tutorial on the use of nonparametric statistical tests as a methodology for comparing evolutionary and swarm intelligence algorithms. *Swarm and Evolutionary Computation*, 1(1), 3–18. Elsevier.
20. Deb, K. (2001). *Multi-Objective Optimization Using Evolutionary Algorithms*. Wiley.
21. Zitzler, E., Thiele, L., Laumanns, M., Fonseca, C. M., & da Fonseca, V. G. (2003). Performance assessment of multiobjective optimizers: An analysis and review. *IEEE Transactions on Evolutionary Computation*, 7(2), 117–132.
