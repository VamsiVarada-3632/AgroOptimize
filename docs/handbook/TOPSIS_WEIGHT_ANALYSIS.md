# TOPSIS Weight Analysis

An audit of the weights the published ranking uses: why each exists, how it was chosen, whether it is hard-coded or configurable, and whether it is justified. Numbers come from `scripts/benchmark_topsis.py` (120 Pareto fronts: 4 districts × 3 seasons, with and without a budget, seeds 0–4, published NSGA-II settings) unless stated otherwise. Raw results: `benchmarks/topsis_benchmark.json`.

## 1. The weights

| Preference | yield | cost | water | env | Defined in |
|---|---|---|---|---|---|
| balanced (default) | 0.300 | 0.2333 | 0.2333 | 0.2333 | `ranking._PREFERENCE_WEIGHTS`, from `_YIELD_GROUP_WEIGHT = 0.30` |
| max_yield | 0.55 | 0.15 | 0.15 | 0.15 | same dict |
| min_cost | 0.15 | 0.55 | 0.15 | 0.15 | same dict |
| min_water | 0.15 | 0.15 | 0.55 | 0.15 | same dict |
| min_env_impact | 0.15 | 0.15 | 0.15 | 0.55 | same dict |
| Scenario Simulation priorities | user sliders 0–100, normalised | | | | `PrioritiesIn` → `normalise_weights` |

## 2. Findings per weight

### 2.1 Balanced: yield 0.30, the others 0.70/3 each

**Why it exists.** Balanced is the default recommendation: one plan that is good on all four objectives, like the reference paper's "Plan #1 (Best)".

**How it was chosen.** By hand, against real Pareto fronts. The code comment and `notes/methodology_notes.md` give the reason: yield is strongly correlated with the other three objectives, so equal weights let the three "footprint" objectives outvote yield and push the #1 plan to a low-input corner.

**Is the reason right?** Yes. Median Spearman correlation across the 120 fronts:

| pair | ρ |
|---|---|
| yield ~ cost | +0.96 |
| yield ~ water | +0.90 |
| yield ~ env | +0.90 |
| water ~ env | +0.72 |

On a Pareto front more yield almost always means more of everything else, so the three cost-type objectives act largely as one criterion.

**Does 0.30 do what it claims?** Measured on 72 fronts (seeds 0–2), as the position of the #1 plan's yield within its front:

| yield weight | #1 plan's yield percentile (median) | #1 is a corner plan (≤ 5th or ≥ 95th percentile) |
|---|---|---|
| 0.25 (equal) | 25th | 11 % |
| **0.30 (balanced)** | **41st** | **6 %** |
| 0.40 | 91st | 40 % |

0.30 gives the most central pick and the fewest corner plans of the three. It does what it was tuned to do.

**How stable is it?** Not very, at the level of the single #1 plan. Moving the yield weight to 0.27 or 0.33 (±10 %) changes the #1 plan on 97 % of fronts. The replacement is close: its median rank under 0.30 is 4 (worst 37), and its closeness is 0.0028 lower (median). But it differs by up to 17.8 % (median) on at least one objective. The front is dense (80 plans along a near-continuous surface), so the closeness surface near the top is flat. This is a property of the problem, not of the weight. It is the main reason the dynamic engine shows the top plans, the reasoning between neighbours and a profile comparison, not a single answer.

**Is it scientifically justified?** Partly. The direction (more weight on yield than on any single footprint objective) is justified by the measured correlations and the centrality result above. The exact value 0.30 is a hand-tuned choice: there is no elicitation from farmers and no derivation from a weighting method.

For reference, two objective weighting methods applied to the same fronts' normalised objectives (median over fronts):

| method | yield | cost | water | env |
|---|---|---|---|---|
| entropy (Hwang & Yoon 1981) | 0.278 | 0.298 | 0.195 | 0.200 |
| CRITIC (Diakoulaki et al. 1995) | 0.457 | 0.182 | 0.188 | 0.172 |
| balanced | 0.300 | 0.233 | 0.233 | 0.233 |

CRITIC rewards criteria that conflict with the others; because yield conflicts with all three footprint objectives, it gives yield the largest weight. The balanced weights sit between the two methods, which supports giving yield more weight than equal shares without pinning down 0.30.

### 2.2 Single-objective preferences: 0.55 / 0.15

**Why they exist.** Comparison plans B (max_yield) and C (min_cost), and the Run Optimization drop-down.

**How they were chosen.** Convention: one criterion gets a clear majority, and the rest keep enough weight to break ties. No tuning is documented.

**Justified?** As a tie-breaking convention, yes. With 0.55 the named objective dominates, but a plan that is marginally better on it and much worse elsewhere does not automatically win. The value itself is arbitrary.

### 2.3 Hard-coded or configurable?

| Weight | Status before this work | Status now |
|---|---|---|
| balanced, preferences | hard-coded in `ranking.py`, not in `config.py`, not exposed through the API | unchanged (the published ranking) |
| Scenario Simulation priorities | user-configurable, 4 objectives | unchanged |
| any other criteria | did not exist | ranking profiles and custom weights over 10 criteria ([TOPSIS_PROFILE_GUIDE.md](TOPSIS_PROFILE_GUIDE.md)) |

## 3. Problems found

1. **The weights could only express the optimiser's objectives.** A farmer could not ask for "profit" or "suits my soil". Price, rainfall dependency and soil status are in the dataset, but did not reach the ranking.
2. **No explanation of the weights' effect.** The explanation reported the weights and the closeness, but not how each criterion contributed or why one plan beat the next.
3. **The single #1 is sensitive** (§2.1). The interface presented it as *the* plan.
4. **Redundancy among the extra criteria** (measured for the new ones; see [TOPSIS_DYNAMIC_ENGINE.md](TOPSIS_DYNAMIC_ENGINE.md) §3.3):
   * income ranks plans like yield (ρ = +1.00);
   * budget headroom ranks them exactly opposite to cost (ρ = −1.00);
   * soil suitability is close to the reverse of environmental impact (ρ = −0.86).

   Weight on two redundant criteria acts like extra weight on one.

## 4. What the dynamic engine does about it

* **Balanced is untouched.** It is still the default, and still the exact published ranking (120/120 fronts identical, bit for bit).
* **Profiles state their weights' origin.** Each profile is three importance tiers turned into weights with one published rule: rank-sum weights (Stillwell, Seaver & Edwards 1981). They are not tuned numbers.
* **Custom weights are validated.** Each must be between 0 and 1, and they must sum to 1.
* **Explanations show the effect of the weights:** weight → contribution → score, why each plan beats the next, and the rank under every profile.
* **The interface shows the top plans and the profile comparison,** so the sensitivity of the single #1 is visible rather than hidden.
* **Redundancy is documented** with each criterion's definition and kept out of the standard profiles where it would double-count. For example, Profit does not weight budget, and Low cost uses budget only as a deliberate emphasis on cost.
