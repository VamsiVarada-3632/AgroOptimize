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


@lru_cache(maxsize=1)
def _build_system() -> tuple[ctrl.ControlSystem, ctrl.Antecedent, ctrl.Antecedent, ctrl.Antecedent]:
    # --- Antecedents (inputs) ---
    rainfall_dev = ctrl.Antecedent(np.arange(-60, 60.1, 1), "rainfall_dev")
    water_storage = ctrl.Antecedent(np.arange(0, 100.1, 1), "water_storage")
    soil_fert = ctrl.Antecedent(np.arange(0, 100.1, 1), "soil_fert")

    # --- Consequents (outputs) ---
    yield_conf = ctrl.Consequent(np.arange(0, 100.1, 1), "yield_conf")
    irrigation_risk = ctrl.Consequent(np.arange(0, 100.1, 1), "irrigation_risk")

    rainfall_dev["deficit"] = fuzz.trimf(rainfall_dev.universe, [-60, -60, -5])
    rainfall_dev["normal"] = fuzz.trimf(rainfall_dev.universe, [-15, 0, 15])
    rainfall_dev["surplus"] = fuzz.trimf(rainfall_dev.universe, [5, 60, 60])

    water_storage["low"] = fuzz.trimf(water_storage.universe, [0, 0, 35])
    water_storage["medium"] = fuzz.trimf(water_storage.universe, [20, 50, 75])
    water_storage["high"] = fuzz.trimf(water_storage.universe, [60, 100, 100])

    soil_fert["poor"] = fuzz.trimf(soil_fert.universe, [0, 0, 40])
    soil_fert["medium"] = fuzz.trimf(soil_fert.universe, [25, 50, 75])
    soil_fert["good"] = fuzz.trimf(soil_fert.universe, [60, 100, 100])

    yield_conf["low"] = fuzz.trimf(yield_conf.universe, [0, 0, 45])
    yield_conf["medium"] = fuzz.trimf(yield_conf.universe, [30, 55, 75])
    yield_conf["high"] = fuzz.trimf(yield_conf.universe, [65, 100, 100])

    irrigation_risk["low"] = fuzz.trimf(irrigation_risk.universe, [0, 0, 35])
    irrigation_risk["medium"] = fuzz.trimf(irrigation_risk.universe, [25, 50, 75])
    irrigation_risk["high"] = fuzz.trimf(irrigation_risk.universe, [60, 100, 100])

    # --- Mamdani rule base (domain-expert-style heuristics) ---
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
    ]

    system = ctrl.ControlSystem(rules)
    return system, rainfall_dev, water_storage, soil_fert


def evaluate_uncertainty(
    rainfall_deviation_percent: float,
    water_storage_percent: float,
    soil_fertility_index: float,
) -> UncertaintyAssessment:
    """Run the Mamdani fuzzy inference engine for one region/season snapshot.

    Inputs are clipped to the universes the membership functions were
    defined over, so extreme/out-of-range readings degrade gracefully
    instead of raising.
    """
    system, rainfall_dev, water_storage, soil_fert = _build_system()
    sim = ctrl.ControlSystemSimulation(system)

    r = float(np.clip(rainfall_deviation_percent, -60, 60))
    w = float(np.clip(water_storage_percent, 0, 100))
    s = float(np.clip(soil_fertility_index, 0, 100))

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

    return UncertaintyAssessment(
        yield_confidence=round(_clip01(yield_conf), 3),
        irrigation_risk=round(_clip01(irr_risk), 3),
        rainfall_label=_dominant_label(rainfall_dev, r),
        water_label=_dominant_label(water_storage, w),
        soil_label=_dominant_label(soil_fert, s),
    )


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
