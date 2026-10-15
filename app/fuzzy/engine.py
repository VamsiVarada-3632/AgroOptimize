"""
Fuzzy Uncertainty Modelling module (reference paper, Section III-C).

Converts the intrinsically imprecise agricultural inputs (rainfall
adequacy, water availability, soil fertility) into fuzzy linguistic sets
via triangular membership functions, runs them through a Mamdani-type
fuzzy inference engine with a hand-authored rule base, and defuzzifies
(centroid method, scikit-fuzzy's default) into two crisp scenario-weight
outputs:

  * yield_confidence  in [0, 1] - how much of the "book" yield the system
    expects to actually be realised this season, given current conditions.
  * irrigation_risk    in [0, 1] - how much extra irrigation pressure the
    season is likely to put on the farm (used to scale up the water
    objective / flag risk in the decision output).

These two scenario weights are what Section III-A calls "scenario-weighted
inputs for the multiple objective optimization module".
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl

from app import config


@dataclass
class UncertaintyAssessment:
    yield_confidence: float       # 0-1, higher = more confident of book yield
    irrigation_risk: float        # 0-1, higher = more irrigation pressure expected
    rainfall_label: str
    water_label: str
    soil_label: str


def _dominant_label(antecedent: ctrl.Antecedent, value: float) -> str:
    """Return the fuzzy set with the highest membership for `value`."""
    best_label, best_degree = "unknown", -1.0
    for label, mf in antecedent.terms.items():
        degree = fuzz.interp_membership(antecedent.universe, mf.mf, value)
        if degree > best_degree:
            best_label, best_degree = label, degree
    return best_label


# Triangular membership functions [a, b, c] of every linguistic term, in
# definition order. Values unchanged from the original inline definitions.
MEMBERSHIP_FUNCTIONS = {
    "rainfall_dev": {"deficit": (-60, -60, -5), "normal": (-15, 0, 15), "surplus": (5, 60, 60)},
    "water_storage": {"low": (0, 0, 35), "medium": (20, 50, 75), "high": (60, 100, 100)},
    "soil_fert": {"poor": (0, 0, 40), "medium": (25, 50, 75), "good": (60, 100, 100)},
    "yield_conf": {"low": (0, 0, 45), "medium": (30, 55, 75), "high": (65, 100, 100)},
    "irrigation_risk": {"low": (0, 0, 35), "medium": (25, 50, 75), "high": (60, 100, 100)},
}


@lru_cache(maxsize=1)
def _build_system() -> tuple[ctrl.ControlSystem, ctrl.Antecedent, ctrl.Antecedent, ctrl.Antecedent]:
    # --- Antecedents (inputs) ---
    rainfall_dev = ctrl.Antecedent(np.arange(-60, 60.1, 1), "rainfall_dev")
    water_storage = ctrl.Antecedent(np.arange(0, 100.1, 1), "water_storage")
    soil_fert = ctrl.Antecedent(np.arange(0, 100.1, 1), "soil_fert")

    # --- Consequents (outputs) ---
    yield_conf = ctrl.Consequent(np.arange(0, 100.1, 1), "yield_conf")
    irrigation_risk = ctrl.Consequent(np.arange(0, 100.1, 1), "irrigation_risk")

    # Membership functions come from MEMBERSHIP_FUNCTIONS (same triangles as
    # before, now in one table that the audit and docs read as well).
    for variable in (rainfall_dev, water_storage, soil_fert, yield_conf, irrigation_risk):
        for label, abc in MEMBERSHIP_FUNCTIONS[variable.label].items():
            variable[label] = fuzz.trimf(variable.universe, list(abc))

    # --- Mamdani rule base (domain-expert-style heuristics) ---
    # Rules 1-14 below are the original 3x3 rainfall x water_storage grid
    # plus 5 soil-interaction rules. Rules 15-26 (added 2026-09-16, Task 3
    # of the panel-review prep list) extend the base to 26 rules, each tied
    # to a named agro-climatic scenario so the rule base reads as domain
    # reasoning, not an arbitrary grid search. They cover 3-way
    # rainfall x water x soil combinations the original 14 rules never
    # exercised (e.g. deficit+low-water+poor-soil as a single conjunction,
    # rather than relying on two separate 2-way rules to co-fire), plus two
    # agronomically real effects the original rule base didn't model at
    # all: (a) extreme rainfall surplus combined with poor soil drainage
    # should *cap* yield confidence via waterlogging/leaching risk instead
    # of always reading as good news, and (b) ample stored/canal water can
    # blunt irrigation risk even when soil or rainfall alone look
    # unfavourable.
    rules = [
        ctrl.Rule(rainfall_dev["deficit"] & water_storage["low"],
                  [irrigation_risk["high"], yield_conf["low"]]),
        ctrl.Rule(rainfall_dev["deficit"] & water_storage["medium"],
                  [irrigation_risk["medium"], yield_conf["medium"]]),
        ctrl.Rule(rainfall_dev["deficit"] & water_storage["high"],
                  [irrigation_risk["medium"], yield_conf["medium"]]),
        ctrl.Rule(rainfall_dev["normal"] & water_storage["low"],
                  [irrigation_risk["medium"], yield_conf["medium"]]),
        ctrl.Rule(rainfall_dev["normal"] & water_storage["medium"],
                  [irrigation_risk["low"], yield_conf["high"]]),
        ctrl.Rule(rainfall_dev["normal"] & water_storage["high"],
                  [irrigation_risk["low"], yield_conf["high"]]),
        ctrl.Rule(rainfall_dev["surplus"] & water_storage["low"],
                  [irrigation_risk["low"], yield_conf["medium"]]),
        ctrl.Rule(rainfall_dev["surplus"] & water_storage["medium"],
                  [irrigation_risk["low"], yield_conf["high"]]),
        ctrl.Rule(rainfall_dev["surplus"] & water_storage["high"],
                  [irrigation_risk["low"], yield_conf["high"]]),
        ctrl.Rule(soil_fert["good"], yield_conf["high"]),
        ctrl.Rule(soil_fert["poor"], yield_conf["low"]),
        ctrl.Rule(soil_fert["medium"] & rainfall_dev["normal"], yield_conf["medium"]),
        ctrl.Rule(water_storage["high"] & soil_fert["good"], yield_conf["high"]),
        ctrl.Rule(water_storage["low"] & soil_fert["poor"], [yield_conf["low"], irrigation_risk["high"]]),

        # 15. Severe/compound drought stress: deficit rainfall, low storage
        # AND poor soil all at once -- reinforces rule 1/14 with the full
        # 3-way conjunction so a genuine triple-stress season reads as
        # unambiguously worse than any single factor alone.
        ctrl.Rule(rainfall_dev["deficit"] & water_storage["low"] & soil_fert["poor"],
                  [yield_conf["low"], irrigation_risk["high"]]),

        # 16. Flood / waterlogging stress: extreme rainfall surplus with
        # high storage AND poor (poorly-draining) soil should NOT read as
        # good news the way plain surplus+high does elsewhere in the rule
        # base -- waterlogging and nutrient leaching cap yield confidence.
        ctrl.Rule(rainfall_dev["surplus"] & water_storage["high"] & soil_fert["poor"],
                  yield_conf["medium"]),

        # 17. Canal/reservoir irrigation advantage: ample stored water can
        # blunt irrigation risk even when soil fertility itself is poor
        # (the farmer isn't short of water, just soil quality).
        ctrl.Rule(water_storage["high"] & soil_fert["poor"], irrigation_risk["low"]),

        # 18. Groundwater depletion risk: low storage plus only medium soil
        # still signals real irrigation pressure, independent of the
        # current season's rainfall reading -- captures a farm running down
        # its groundwater/tank reserves over successive seasons.
        ctrl.Rule(water_storage["low"] & soil_fert["medium"], irrigation_risk["high"]),

        # 19. Post-monsoon Rabi transition: a rainfall deficit carried into
        # Rabi with only medium stored water isn't rescued to "high" yield
        # confidence just because the soil is good -- caps it at medium.
        ctrl.Rule(rainfall_dev["deficit"] & water_storage["medium"] & soil_fert["good"],
                  yield_conf["medium"]),

        # 20. Summer drought risk: rainfall deficit combined with poor soil
        # is a bad combination on its own, regardless of how much water is
        # currently in storage (elevated summer evapotranspiration can
        # outpace what stored water alone can offset).
        ctrl.Rule(rainfall_dev["deficit"] & soil_fert["poor"],
                  [yield_conf["low"], irrigation_risk["high"]]),

        # 21. Optimal combined conditions: the unambiguous best case
        # (normal rainfall, high storage, good soil) explicitly reinforced
        # as a 3-way conjunction rather than left to two 2-way rules.
        ctrl.Rule(rainfall_dev["normal"] & water_storage["high"] & soil_fert["good"],
                  [yield_conf["high"], irrigation_risk["low"]]),

        # 22. Semi-wet transitional zone (e.g. Erode-like conditions):
        # normal rainfall with only medium storage AND medium soil is a
        # genuinely middling case, distinct from the "normal+medium water"
        # 2-way rule (rule 5) which assumes soil isn't the limiting factor.
        ctrl.Rule(rainfall_dev["normal"] & water_storage["medium"] & soil_fert["medium"],
                  [yield_conf["medium"], irrigation_risk["medium"]]),

        # 23. Wet-zone transitional (e.g. Coimbatore/Pollachi-like
        # conditions): rainfall surplus doesn't guarantee a high outcome by
        # itself if both storage and soil are only medium -- reads as a
        # moderate, not optimal, season.
        ctrl.Rule(rainfall_dev["surplus"] & water_storage["medium"] & soil_fert["medium"],
                  yield_conf["medium"]),

        # 24. Canal irrigation advantage under deficit: even with a
        # rainfall deficit, high stored/canal water plus at least medium
        # soil keeps irrigation risk low and yield moderate rather than
        # falling to the generic "deficit+high water" 2-way rule's medium
        # risk reading.
        ctrl.Rule(rainfall_dev["deficit"] & water_storage["high"] & soil_fert["medium"],
                  [irrigation_risk["low"], yield_conf["medium"]]),

        # 25. Wet-zone optimal case (e.g. Coimbatore in a strong monsoon
        # year): rainfall surplus, high storage AND good soil together --
        # the clearest possible "very confident" reading.
        ctrl.Rule(rainfall_dev["surplus"] & water_storage["high"] & soil_fert["good"],
                  [yield_conf["high"], irrigation_risk["low"]]),

        # 26. Dry-zone marginal case (e.g. Salem in a weaker monsoon year):
        # rainfall deficit, only medium storage AND poor soil -- a real,
        # if less extreme than rule 15, stress combination.
        ctrl.Rule(rainfall_dev["deficit"] & water_storage["medium"] & soil_fert["poor"],
                  [yield_conf["low"], irrigation_risk["high"]]),
    ]

    system = ctrl.ControlSystem(rules)
    return system, rainfall_dev, water_storage, soil_fert


# Input universes (the clipping range of every crisp input). Previously the
# same bounds were written out in two places; one table keeps them in step.
INPUT_BOUNDS = {"rainfall_dev": (-60.0, 60.0), "water_storage": (0.0, 100.0), "soil_fert": (0.0, 100.0)}
OUTPUT_VARIABLES = ("yield_conf", "irrigation_risk")

# Scenario names of rules 15-26, taken verbatim from the comments in
# _build_system (no new agronomic content); rules 1-14 are described by
# their conditions alone.
RULE_SCENARIOS = {
    15: "Severe/compound drought stress",
    16: "Flood / waterlogging stress",
    17: "Canal/reservoir irrigation advantage",
    18: "Groundwater depletion risk",
    19: "Post-monsoon Rabi transition",
    20: "Summer drought risk",
    21: "Optimal combined conditions",
    22: "Semi-wet transitional zone",
    23: "Wet-zone transitional",
    24: "Canal irrigation advantage under deficit",
    25: "Wet-zone optimal case",
    26: "Dry-zone marginal case",
}


@dataclass(frozen=True)
class RuleSpec:
    """Read-only description of one rule, in rule-base order (1-26)."""
    number: int
    antecedents: tuple      # ((variable, term), ...) AND-ed
    consequents: tuple      # ((variable, term), ...)
    text_if: str
    text_then: str
    scenario: str | None


@lru_cache(maxsize=1)
def rule_specs() -> tuple:
    """The rule base as plain data, built once from the compiled system so
    explanations, audits and fired_rules all read the same definition."""
    system, *_ = _build_system()
    specs = []
    for number, rule in enumerate(system.rules, start=1):
        terms = list(rule.antecedent_terms)
        specs.append(RuleSpec(
            number=number,
            antecedents=tuple((t.parent.label, t.label) for t in terms),
            consequents=tuple((c.term.parent.label, c.term.label) for c in rule.consequent),
            text_if=" AND ".join(f"{t.parent.label} is {t.label}" for t in terms),
            text_then=", ".join(f"{c.term.parent.label} is {c.term.label}" for c in rule.consequent),
            scenario=RULE_SCENARIOS.get(number),
        ))
    return tuple(specs)


def _clipped_inputs(rainfall_deviation_percent, water_storage_percent, soil_fertility_index):
    return {
        "rainfall_dev": float(np.clip(rainfall_deviation_percent, *INPUT_BOUNDS["rainfall_dev"])),
        "water_storage": float(np.clip(water_storage_percent, *INPUT_BOUNDS["water_storage"])),
        "soil_fert": float(np.clip(soil_fertility_index, *INPUT_BOUNDS["soil_fert"])),
    }


def evaluate_uncertainty(
    rainfall_deviation_percent: float,
    water_storage_percent: float,
    soil_fertility_index: float,
) -> UncertaintyAssessment:
    """Run the Mamdani fuzzy inference engine for one region/season snapshot.

    Inputs are clipped to the universes the membership functions were
    defined over, so extreme/out-of-range readings degrade gracefully
    instead of raising.

    The inference itself is memoised on the clipped inputs (see
    _evaluate_cached): the engine is a pure function of them, and the same
    region profile is evaluated repeatedly (dashboard, comparison,
    explanations, the ten runs of a scenario simulation). Each call still
    returns a new UncertaintyAssessment, so callers can never share state.
    """
    x = _clipped_inputs(rainfall_deviation_percent, water_storage_percent, soil_fertility_index)
    yield_conf, irr_risk, rain_label, water_label, soil_label = _evaluate_cached(
        x["rainfall_dev"], x["water_storage"], x["soil_fert"])
    return UncertaintyAssessment(
        yield_confidence=yield_conf,
        irrigation_risk=irr_risk,
        rainfall_label=rain_label,
        water_label=water_label,
        soil_label=soil_label,
    )


@lru_cache(maxsize=4096)
def _evaluate_cached(r: float, w: float, s: float) -> tuple:
    """scikit-fuzzy Mamdani inference for already-clipped inputs. Unchanged
    from the original evaluate_uncertainty body; only moved here so its
    result can be memoised."""
    system, rainfall_dev, water_storage, soil_fert = _build_system()
    sim = ctrl.ControlSystemSimulation(system)

    sim.input["rainfall_dev"] = r
    sim.input["water_storage"] = w
    sim.input["soil_fert"] = s

    try:
        sim.compute()
        yield_conf = float(sim.output["yield_conf"]) / 100.0
        irr_risk = float(sim.output["irrigation_risk"]) / 100.0
    except (KeyError, ValueError):
        # No rule fired strongly enough (can happen at extreme universe
        # edges) -- fall back to a neutral, mildly cautious estimate.
        yield_conf, irr_risk = 0.5, 0.5

    return (
        round(_clip01(yield_conf), 3),
        round(_clip01(irr_risk), 3),
        _dominant_label(rainfall_dev, r),
        _dominant_label(water_storage, w),
        _dominant_label(soil_fert, s),
    )


def _raw_memberships(x: dict) -> dict:
    """Unrounded membership degrees of clipped inputs (the values the engine uses)."""
    _, rainfall_dev, water_storage, soil_fert = _build_system()
    return {
        antecedent.label: {
            label: float(fuzz.interp_membership(antecedent.universe, term.mf, x[antecedent.label]))
            for label, term in antecedent.terms.items()
        }
        for antecedent in (rainfall_dev, water_storage, soil_fert)
    }


@lru_cache(maxsize=4096)
def _memberships_cached(r: float, w: float, s: float) -> tuple:
    raw = _raw_memberships({"rainfall_dev": r, "water_storage": w, "soil_fert": s})
    return tuple((var, tuple((label, round(v, 3)) for label, v in terms.items())) for var, terms in raw.items())


def input_memberships(rainfall_deviation_percent, water_storage_percent, soil_fertility_index) -> dict:
    """Membership degree of each input in each of its fuzzy sets, using the
    same membership functions and clipping as evaluate_uncertainty
    (rounded to 3 decimals). Memoised; returns a fresh dict each call."""
    x = _clipped_inputs(rainfall_deviation_percent, water_storage_percent, soil_fertility_index)
    return {var: dict(terms) for var, terms in _memberships_cached(x["rainfall_dev"], x["water_storage"], x["soil_fert"])}


@lru_cache(maxsize=4096)
def _fired_cached(r: float, w: float, s: float) -> tuple:
    degrees = {var: dict(terms) for var, terms in _memberships_cached(r, w, s)}
    fired = []
    for spec in rule_specs():
        strength = min(degrees[var][term] for var, term in spec.antecedents)
        if strength <= 0:
            continue
        fired.append((spec.number, spec.text_if, spec.text_then, round(strength, 3)))
    return tuple(sorted(fired, key=lambda r: (-r[3], r[0])))


def fired_rules(rainfall_deviation_percent, water_storage_percent, soil_fertility_index) -> list:
    """Firing strength of every rule (min over its AND-ed antecedent
    memberships, using the 3-decimal memberships of input_memberships),
    strongest first; rule numbers match _build_system's order (1-26).
    Rules that do not fire (strength 0) are omitted. Memoised; returns new
    dicts each call."""
    x = _clipped_inputs(rainfall_deviation_percent, water_storage_percent, soil_fertility_index)
    return [{"rule": n, "if": i, "then": t, "strength": st}
            for n, i, t, st in _fired_cached(x["rainfall_dev"], x["water_storage"], x["soil_fert"])]


def output_term(variable: str, value01: float) -> tuple:
    """Dominant linguistic term (and all membership degrees) of a fuzzy
    OUTPUT value in [0, 1], read off the model's own output sets
    ("yield_conf" or "irrigation_risk")."""
    system, *_ = _build_system()
    consequent = next(c for c in system.consequents if c.label == variable)
    x = float(np.clip(value01, 0, 1)) * 100
    degrees = {
        label: round(float(fuzz.interp_membership(consequent.universe, term.mf, x)), 3)
        for label, term in consequent.terms.items()
    }
    return max(degrees, key=degrees.get), degrees


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def crop_yield_confidence(base_yield_confidence: float, irrigation_risk: float, rainfall_dependency: str) -> float:
    """Adjust the region-level yield confidence per crop, based on how
    rain-dependent that specific crop is (dataset column
    `Rainfall_Dependency`). A drip-irrigated, "Very Low" dependency crop
    barely feels a rainfall deficit; a rainfed "High" dependency crop feels
    it fully.
    """
    dep_factor = config.RAINFALL_DEPENDENCY_FACTOR.get(rainfall_dependency, 0.5)
    penalty = irrigation_risk * dep_factor * 0.4  # cap the max penalty at 40%
    return round(_clip01(base_yield_confidence * (1.0 - penalty)), 3)


# ---------------------------------------------------------------------------
# Rule-level explanation
#
# scikit-fuzzy's Mamdani step, as implemented in skfuzzy.control
# (CrispValueCalculator.find_memberships / defuzz), is:
#   firing(rule)  = min over the rule's antecedent memberships
#   cut(term)     = max over the firing of every rule concluding that term
#   output(y)     = max over terms of min(cut(term), mf_term(y)) on the
#                   output universe upsampled with each cut's crossing points
#   crisp         = centroid(output)
# _aggregate below repeats that with the same skfuzzy primitives, so the
# centroid it produces equals the engine's output (checked on every call and
# in the tests). That makes an exact rule attribution possible:
#   * a fired rule only influences the output if its firing *sets* a cut
#     (it is the strongest rule for that term); otherwise it is masked;
#   * the aggregated area splits exactly into the parts where each term is
#     the maximum, and each part is credited to the rule(s) setting its cut;
#   * removing a rule and recomputing gives its leave-one-out importance.
# Nothing here feeds the optimiser; evaluate_uncertainty is unchanged.
# ---------------------------------------------------------------------------

from skfuzzy.fuzzymath.fuzzy_ops import _interp_universe_fast  # noqa: E402

CONSISTENCY_TOLERANCE = 1e-9   # explanation centroid vs engine output (0-1 scale)


def _consequent(variable: str):
    system, *_ = _build_system()
    return next(c for c in system.consequents if c.label == variable)


def _aggregate(variable: str, cuts: dict):
    """Aggregated output set for `cuts` ({term: cut or None}), exactly as
    skfuzzy builds it. Returns (universe, output_mf, {term: clipped mf})."""
    consequent = _consequent(variable)
    new_values = []
    for label, term in consequent.terms.items():
        if cuts.get(label) is None:
            continue
        new_values.extend(_interp_universe_fast(consequent.universe, term.mf, cuts[label]).tolist())
    universe = np.union1d(consequent.universe, new_values)
    output = np.zeros_like(universe, dtype=np.float64)
    term_mfs = {}
    for label, term in consequent.terms.items():
        if cuts.get(label) is None:
            continue
        term_mfs[label] = np.minimum(cuts[label], fuzz.interp_membership(consequent.universe, term.mf, universe))
        np.maximum(output, term_mfs[label], output)
    return universe, output, term_mfs


def _centroid01(variable: str, cuts: dict):
    """Crisp output in [0, 1], or None when the aggregated set is empty
    (the engine then falls back to 0.5)."""
    universe, output, _ = _aggregate(variable, cuts)
    if not np.any(output > 0):
        return None
    return float(fuzz.defuzz(universe, output, "centroid")) / 100.0


def _term_cuts(firing: dict, exclude: int | None = None) -> dict:
    """{variable: {term: (cut, [setting rules])}} from rule firing strengths."""
    cuts = {v: {} for v in OUTPUT_VARIABLES}
    for spec in rule_specs():
        if spec.number == exclude:
            continue
        for var, term in spec.consequents:
            cut, setters = cuts[var].get(term, (None, []))
            f = firing[spec.number]
            if cut is None or f > cut:
                cuts[var][term] = (f, [spec.number])
            elif f == cut:
                setters.append(spec.number)
    return cuts


def _area(universe, mf) -> float:
    return float(np.trapezoid(mf, universe))


def explain_inference(rainfall_deviation_percent, water_storage_percent, soil_fertility_index) -> dict:
    """Why the fuzzy engine produced its outputs for these inputs.

    Returns the clipped inputs and their memberships; for every rule its
    firing strength, limiting condition, status (decisive / masked / not
    fired), share of each output's aggregated area and leave-one-out
    importance; rules ranked by importance; per output the term cuts, the
    rules setting them, each term's area share, the crisp value, its
    linguistic term and membership (a confidence for the label), and a
    consistency check against evaluate_uncertainty.
    """
    x = _clipped_inputs(rainfall_deviation_percent, water_storage_percent, soil_fertility_index)
    memberships = _raw_memberships(x)
    firing = {spec.number: min(memberships[v][t] for v, t in spec.antecedents) for spec in rule_specs()}
    cuts = _term_cuts(firing)
    engine = vars(evaluate_uncertainty(x["rainfall_dev"], x["water_storage"], x["soil_fert"]))
    engine_key = {"yield_conf": "yield_confidence", "irrigation_risk": "irrigation_risk"}

    outputs, crisp_values, rule_share = {}, {}, {spec.number: {} for spec in rule_specs()}
    for var in OUTPUT_VARIABLES:
        plain = {term: c for term, (c, _) in cuts[var].items()}
        universe, output, term_mfs = _aggregate(var, plain)
        total = _area(universe, output)
        crisp = _centroid01(var, plain)
        # Split the aggregated area between the terms that form it (ties split equally).
        winners = {t: np.isclose(mf, output) & (output > 0) for t, mf in term_mfs.items()}
        n_win = np.maximum(sum(w.astype(int) for w in winners.values()), 1)
        shares = {t: (_area(universe, np.where(winners[t], output / n_win, 0.0)) / total * 100 if total > 0 else 0.0)
                  for t in term_mfs}
        for term, (cut, setters) in cuts[var].items():
            if cut > 0:
                for n in setters:
                    rule_share[n][var] = rule_share[n].get(var, 0.0) + shares.get(term, 0.0) / len(setters)
        value = crisp if crisp is not None else 0.5
        crisp_values[var] = value
        label, degrees = output_term(var, value)
        rounded = round(_clip01(value), 3)
        outputs[var] = {
            "value": rounded,
            "term": label,
            "term_membership": degrees[label],
            "term_memberships": degrees,
            "term_cuts": {t: {"cut": round(c, 4), "set_by": s if c > 0 else []} for t, (c, s) in cuts[var].items()},
            "term_area_share_pct": {t: round(v, 1) for t, v in shares.items()},
            "fallback_used": crisp is None,
            "matches_engine": abs(rounded - engine[engine_key[var]]) <= CONSISTENCY_TOLERANCE,
        }

    rules = []
    for spec in rule_specs():
        f = firing[spec.number]
        decisive = {var: share for var, share in rule_share[spec.number].items()}
        loo = {}
        if f > 0 and decisive:
            without = _term_cuts(firing, exclude=spec.number)
            for var in decisive:
                alt = _centroid01(var, {t: c for t, (c, _) in without[var].items()})
                # Unrounded on both sides, so a rule whose removal changes
                # nothing (e.g. one tied with the rule that subsumes it) shows 0.
                loo[var] = round(crisp_values[var] - (alt if alt is not None else 0.5), 4)
        masked_by = sorted({n for var, term in spec.consequents
                            for n in cuts[var][term][1] if n != spec.number and cuts[var][term][0] > f})
        tied_with = sorted({n for var, term in spec.consequents
                            if spec.number in cuts[var][term][1] and cuts[var][term][0] > 0
                            for n in cuts[var][term][1] if n != spec.number})
        limiting = min(spec.antecedents, key=lambda vt: memberships[vt[0]][vt[1]])
        status = "not fired" if f <= 0 else ("decisive" if decisive else "masked")
        rules.append({
            "rule": spec.number,
            "scenario": spec.scenario,
            "if": spec.text_if,
            "then": spec.text_then,
            "strength": round(f, 4),
            "status": status,
            "limiting_condition": None if f <= 0 else {
                "variable": limiting[0], "term": limiting[1], "membership": round(memberships[limiting[0]][limiting[1]], 4)},
            "masked_by": masked_by if status == "masked" else [],
            "tied_with": tied_with,
            "contribution_pct": {var: round(v, 1) for var, v in decisive.items()},
            "leave_one_out_change": loo,
            "importance": round(max((abs(v) for v in loo.values()), default=0.0), 4),
        })
    ranked = sorted((r for r in rules if r["status"] != "not fired"),
                    key=lambda r: (-r["importance"], -sum(r["contribution_pct"].values()), -r["strength"], r["rule"]))
    return {
        "inputs": {var: {"value": x[var], "memberships": {t: round(v, 4) for t, v in memberships[var].items()},
                         "dominant": max(memberships[var], key=memberships[var].get)} for var in INPUT_BOUNDS},
        "outputs": outputs,
        "rules": rules,
        "ranking": [r["rule"] for r in ranked],
        "summary": {"fired": sum(r["status"] != "not fired" for r in rules),
                    "decisive": sum(r["status"] == "decisive" for r in rules),
                    "masked": sum(r["status"] == "masked" for r in rules)},
        "method": ("Firing = min of antecedent memberships; each output term is cut at the strongest firing of the rules "
                   "concluding it (max aggregation); the output is the union of the cut terms, defuzzified by centroid. "
                   "Contribution = share of the aggregated area where the rule's term is the maximum (split equally between "
                   "rules tied for the same cut); masked rules fired but a stronger rule set the same term's cut. Leave-one-out change = output with the rule minus "
                   "output without it (0-1 scale)."),
    }
