# Fuzzy Explainability

How AgroOptimize explains a single fuzzy inference: which rules fired, why, with what strength, which of them actually shaped the output, by how much, and how important each one is. Implemented in `fuzzy.engine.explain_inference`; returned in every plan explanation (`fuzzy_reasoning.inference`) and by `GET /api/fuzzy/explain`; shown in the explanation panel's "Fuzzy rules that fired" table. Context: [FUZZY_SYSTEM_ANALYSIS.md](FUZZY_SYSTEM_ANALYSIS.md).

## 1. Why a fired-rule list was not enough
Before this work the explanation listed every fired rule with its firing strength. In Mamdani max-aggregation, however, a fired rule only matters if it is the *strongest* rule concluding its output term — otherwise another rule has already cut that term higher and the weaker rule changes nothing. In the Salem Kharif example below, 6 rules fire but only 3 influence the outputs; the old list could not tell them apart and also presented the six provably inert rules as contributors.

## 2. Method (exact, reproduces the engine)
scikit-fuzzy computes, per output variable:

1. firing(rule) = min of the rule's antecedent memberships;
2. cut(term) = max of the firing strengths of the rules concluding that term;
3. aggregated set = max over terms of min(cut, term membership function), on the output universe upsampled with the cut crossing points;
4. crisp output = centroid of the aggregated set ÷ 100.

`explain_inference` rebuilds steps 1–4 with the same scikit-fuzzy primitives (`interp_membership`, `_interp_universe_fast`, `defuzz`). The rebuilt centroid equals the engine's output exactly (difference 0 on a 13 × 11 × 11 grid and 150 random points; checked on every call as `matches_engine`). From that reconstruction:

| Field | Meaning |
|---|---|
| `strength` | firing strength (unrounded min of antecedent memberships) |
| `limiting_condition` | the antecedent with the lowest membership — *why* the rule fired at this strength and no higher |
| `status` | **decisive**: the rule's strength sets at least one output term's cut; **masked**: fired, but a stronger rule set the same term's cut (`masked_by`); **not fired** |
| `tied_with` | rules with exactly the same strength for the same term (they share the credit; removing one changes nothing) |
| `contribution_pct` | per output, the rule's share of the aggregated area: the area is split exactly between the terms that form its upper envelope, and each term's part is credited to the rule(s) that set its cut. Sums to 100 % per output |
| `leave_one_out_change` | output with the rule minus output with the rule removed from the rule base (0–1 scale) — signed effect on the crisp value |
| `importance` | largest absolute leave-one-out change over the two outputs; rules are **ranked** by importance, then contribution, then strength |
| `outputs[var]` | crisp value, dominant output term and its membership (how firmly the value belongs to that label — the label's confidence), term cuts with the rules that set them, term area shares |
| `summary` | fired / decisive / masked counts |

Inert rules always have importance 0; masked rules have importance 0 by construction. Area share and leave-one-out answer different questions: share says *what the output is made of*, leave-one-out says *how much it would move without the rule* (a rule can form much of the area yet move the centroid little when another term would take its place).

## 3. Worked example — Salem, Kharif, latest year
Inputs: rainfall deviation −21.1 % (deficit 0.293), storage 62 % (medium 0.520, high 0.050), soil fertility 67.8 (medium 0.288, good 0.195).

| Rank | Rule | Strength | Status | Share of yield / risk | Leave-one-out (yield / risk) | Limited by |
|---|---|---|---|---|---|---|
| 1 | 2 — deficit ∧ water medium → risk medium, yield medium | 0.293 | decisive | 66.2 % / 90.4 % | −0.026 / +0.094 | rainfall deficit (0.293) |
| 2 | 10 — soil good → yield high | 0.195 | decisive | 33.8 % / – | +0.072 / – | soil good (0.195) |
| 3 | 24 — Canal irrigation advantage under deficit | 0.050 | decisive | – / 9.6 % | – / −0.035 | water high (0.050) |
| 4 | 19 — Post-monsoon Rabi transition | 0.195 | masked by 2 | – | 0 | soil good (0.195) |
| 5 | 3 — deficit ∧ water high → medium, medium | 0.050 | masked by 2 | – | 0 | water high (0.050) |
| 6 | 13 — water high ∧ soil good → yield high | 0.050 | masked by 10 | – | 0 | water high (0.050) |

Outputs: yield_confidence 0.636 (*medium*, membership 0.572) formed by rule 2's *medium* cut (0.293) and rule 10's *high* cut (0.195); irrigation_risk 0.465 (*medium*, 0.861) formed by rule 2's *medium* cut and rule 24's *low* cut (0.050). Reading: the season's rainfall deficit drives both outputs; good soil lifts yield confidence by 0.072; the small share of high storage lowers irrigation risk by 0.035. Rule 19 — commented as capping yield at medium — fires as strongly as rule 10 but is masked by rule 2, which already sets the *medium* cut higher.

## 4. Where it appears
* **Plan explanations** (`GET /api/results/{id}/explanation`, comparison explanations, Scenario Simulation): `fuzzy_reasoning.inference` alongside the existing `input_memberships` and `fired_rules` (unchanged).
* **API**: `GET /api/fuzzy/explain?rainfall_dev=&water_storage=&soil_fert=` for any input triple (clipped like the engine; non-finite → 422).
* **Frontend**: the explanation panel's "Fuzzy rules that fired" table is ranked by importance and shows status (with the masking or tied rule), share of yield / risk, limiting condition and importance, plus the output labels and their memberships. Older payloads without `inference` still render the plain list.

## 5. Tests
`tests/test_fuzzy_audit.py`: explanation equals an uncached scikit-fuzzy run (51 points); shares sum to 100 %; cut setters' strengths equal the cuts; masked rules have stronger maskers and zero importance; limiting membership equals strength; ranking order; leave-one-out equals rebuilding the scikit-fuzzy system without the rule; inert rules have zero importance at 40 random points; the Salem example; integration in the explanation service; endpoints. Frontend: the table renders with and without `inference`.

## 6. Limits
* Attribution is exact for this inference scheme (min/max/centroid); it is not a general causal claim about agronomy.
* Leave-one-out is one-at-a-time; interactions between two removed rules are not reported.
* Explanations describe the model as built — including the coverage and capping weaknesses documented in the analysis.
