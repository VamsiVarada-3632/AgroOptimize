# TOPSIS Explainability

Every ranked plan can be explained from its weights to its score with numbers that reproduce the ranking exactly. This document defines what is reported, how it is computed (`app/decision/topsis_explain.py`), and where it appears.

## 1. What is explained

For every recommendation:

| Question | Answer given | Field |
|---|---|---|
| Which profile was used? | profile name and label (or the classic preference / custom priorities) | `meta.topsis.profile`, `.label` |
| Which weights were applied? | weight of every criterion, summing to 1 | `meta.topsis.weights`, `.criteria` |
| How did the weights affect this plan? | per criterion: weight → normalised value → weighted contribution → gap to the best and worst plan → share of the distance to the best plan | `plan.criteria[]` |
| What is the final score? | distances to the ideal and anti-ideal plan and the closeness | `plan.closeness`, `distance_to_ideal`, `distance_to_anti_ideal` |
| Why does plan A rank above plan B? | criteria sorted by weighted advantage, with a sentence | `pairs[]`, `versus_next`, `versus_previous` |
| Would another profile agree? | rank of the plan under every standard profile | `rank_by_profile` |

## 2. Weight → contribution → score

For plan i and criterion j with weight wⱼ and normalised value gᵢⱼ (1 = best in the set):

```
weighted value        vᵢⱼ = wⱼ · gᵢⱼ
gap to the ideal      √d⁺ᵢⱼ = A⁺ⱼ − vᵢⱼ        (A⁺ⱼ = best weighted value in the set)
gap to the anti-ideal √d⁻ᵢⱼ = vᵢⱼ − A⁻ⱼ        (A⁻ⱼ = worst weighted value in the set)
distances             D⁺ᵢ = √Σⱼ d⁺ᵢⱼ,  D⁻ᵢ = √Σⱼ d⁻ᵢⱼ
score                 Cᵢ = D⁻ᵢ / (D⁺ᵢ + D⁻ᵢ)
share of the distance to the ideal = d⁺ᵢⱼ / Σⱼ d⁺ᵢⱼ
```

The squared distances add up over criteria, so each criterion's share of D⁺ᵢ² says exactly how much of the plan's shortfall comes from it. The tests rebuild D⁺, D⁻ and C from the reported terms.

### Worked example

Salem Kharif, 5 ha, budget ₹400,000, Profit priority, the #1 plan when the run is re-ranked (tapioca on all the land):

| Criterion | Weight | Value | Normalised | Weighted | Gap to best | Share of distance to best |
|---|---|---|---|---|---|---|
| Yield | 0.2308 | 69.81 t | 1.00 | 0.2308 | 0.0000 | 0 % |
| Production cost | 0.1538 | ₹201,301 | 0.21 | 0.0323 | 0.1215 | 20.9 % |
| Water | 0.0769 | 22.65 ML | 0.52 | 0.0397 | 0.0373 | 2.0 % |
| Environmental impact | 0.0769 | 198.8 | 0.52 | 0.0398 | 0.0371 | 1.9 % |
| Market price | 0.2308 | ₹721/qtl | 0.00 | 0.0000 | 0.2308 | 75.2 % |
| Income | 0.2308 | ₹302,174 | 1.00 | 0.2308 | 0.0000 | 0 % |

D⁺ = 0.2661, D⁻ = 0.3327, so C = 0.3327 / (0.2661 + 0.3327) = 0.5557.

Reading:
* The plan has the best yield and income in the set, which together carry 46 % of the weight.
* It has the lowest price per quintal (tapioca is cheap per quintal), which is three quarters of its distance from the ideal plan.
* Its cost accounts for the remaining fifth.

Why it ranks above #2, as the engine words it:

> Plan #1 ranks above plan #2 (closeness 0.5557 vs 0.5450). It is better on water (+0.040), environmental impact (+0.004), yield (+0.001) and worse on production cost (-0.001).

The number in brackets is the **weighted advantage** wⱼ(gₐⱼ − g_bⱼ). Both plans are measured against the same ideal and anti-ideal, so the plan with the larger weighted value is closer to the ideal and farther from the anti-ideal on that criterion. Criteria are listed by the size of the advantage. Advantages that round to 0.000 stay in the table but are left out of the sentence. The exact squared-distance terms of both plans are in `pairs[].criteria`.

## 3. Where it appears

| Place | Content |
|---|---|
| Run Optimization → TOPSIS ranking → **Ranking** | selected profile, weight distribution chart, top plans with TOPSIS scores |
| Run Optimization → **Reasoning** | why each of the top plans beats the next; the #1 plan's contribution chart (weighted value against the best in the set) with a table view |
| Run Optimization → **Compare profiles** | [TOPSIS_COMPARISON.md](TOPSIS_COMPARISON.md) |
| "Why this plan?" (saved runs and the Comparison page) | TOPSIS score section: weight, normalised value, contribution and share of the gap per criterion; the sentences against the previous and next plan; the rank under every profile |
| Reasons in every explanation | "Ranked #k of n plans under the '…' ranking profile …" for profile runs; unchanged wording for preference runs |
| API | `GET/POST /api/results/{run_id}/topsis` → `explanation` (top 10 plans and their pairs); `…/explanation` → `topsis` |

## 4. Guarantees

* **Exact.** The breakdown uses the ranking's own normalisation and distance code (`ranking.criteria_closeness`). Its closeness, rounded to 4 places, equals each ranked plan's `composite_score`, and its ranks equal the ranked order. This is tested for every profile.
* **Same plan set.** A saved run is explained over the front it was ranked from (`ranked_over: ranked_front`). Runs saved before the front was stored are explained over their returned plans and say so (`ranked_over: returned_plans`).
* **Nothing invented.** If the crop data a profile needs is missing, the section says it is unavailable instead of falling back to other numbers.
* **Older explanations unchanged.** Explanations of runs ranked by a preference are identical to before, apart from the new optional `topsis` section (checked against `main`).

## 5. Limits of the explanation

* **Relative scores.** "Normalised 1.00" means the best in this set, not good in absolute terms.
* **The weighted advantage is a per-criterion reading.** The ranking itself comes from the Euclidean distances, so a plan can lead on the sum of advantages and still rank lower when its distances are unbalanced. The reported closeness values always decide.
* **Neighbouring plans are often near-ties.** Close neighbours can differ by less than 0.001 in closeness. The sentence states the gap so the reader can see when the order is marginal.
