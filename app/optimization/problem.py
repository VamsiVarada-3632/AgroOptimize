"""
Multi-Objective Genetic Optimization engine (reference paper, Section III-D) - OFFICIAL-DATA objectives.

FarmPlanProblem is a pymoo Problem whose decision variables are a per-crop land allocation plus
irrigation/fertilizer intensity multipliers. All four objectives are computed from official values only
(no estimated constants):

    f1 = -expected yield (t)           yield (TN Season & Crop Report, district) x fuzzy confidence    [maximise]
    f2 =  cultivation cost (Rs)        yield (q/ha) x CACP projected cost of cultivation A2+FL (Rs/q)   [minimise]
    f3 =  irrigation demand (ha)       area x irrigation multiplier x the crop's irrigated area share   [minimise]
    f4 =  nutrient load (kg NPK)       area x fertiliser multiplier x TNAU blanket N+P2O5+K2O dose       [minimise]

f3 is irrigated hectare-equivalents rather than litres, and f4 is kilograms of nutrient rather than an
emission score, because the official data publishes neither a crop water requirement (mm) nor emission
factors; those would have to be estimated. An optional inequality constraint keeps total cost under the
farmer's budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from pymoo.core.problem import Problem

from app import config
from app.data.preprocessing import CropCandidate, RegionSeasonProfile
from app.fuzzy.engine import UncertaintyAssessment, crop_yield_confidence


@dataclass
class CropVector:
    """Per-crop scalar arrays, precomputed once so `_evaluate` is fully vectorised."""

    names: List[str]
    yield_kg_ha: np.ndarray
    fert_n_kg_ha: np.ndarray
    fert_p_kg_ha: np.ndarray
    fert_k_kg_ha: np.ndarray
    cost_rs_ha: np.ndarray            # yield (q/ha) x CACP cost (Rs/q)
    irrigated_share: np.ndarray       # official irrigated area / total area of the crop in the district
    rainfed_share: np.ndarray
    crop_yield_confidence: np.ndarray  # fuzzy-adjusted, per crop

    @classmethod
    def from_candidates(
        cls, crops: List[CropCandidate], assessment: Optional[UncertaintyAssessment], use_fuzzy: bool = True
    ) -> "CropVector":
        """`use_fuzzy=False` (or no assessment, when an official fuzzy input is unavailable for the district)
        leaves the official yield unadjusted (confidence = 1.0)."""
        if use_fuzzy and assessment is not None:
            conf = np.array([crop_yield_confidence(assessment.yield_confidence, assessment.irrigation_risk, c.rainfed_share)
                             for c in crops])
        else:
            conf = np.ones(len(crops))
        return cls(
            names=[c.name for c in crops],
            yield_kg_ha=np.array([c.yield_kg_ha for c in crops]),
            fert_n_kg_ha=np.array([c.fert_n_kg_ha for c in crops]),
            fert_p_kg_ha=np.array([c.fert_p_kg_ha for c in crops]),
            fert_k_kg_ha=np.array([c.fert_k_kg_ha for c in crops]),
            cost_rs_ha=np.array([c.cost_rs_ha for c in crops]),
            irrigated_share=np.array([c.irrigated_share for c in crops]),
            rainfed_share=np.array([c.rainfed_share for c in crops]),
            crop_yield_confidence=conf,
        )


class FarmPlanProblem(Problem):
    def __init__(
        self,
        profile: RegionSeasonProfile,
        assessment: Optional[UncertaintyAssessment],
        total_land_ha: float,
        budget_rs: Optional[float] = None,
        use_fuzzy: bool = True,
        fertilizer_price_factor: float = 1.0,
    ):
        if fertilizer_price_factor != 1.0:
            raise ValueError("Fertiliser-price scenarios are disabled: no official fertiliser price dataset is loaded "
                             "(the cost objective uses the CACP cost of cultivation).")
        self.profile = profile
        self.assessment = assessment
        self.total_land_ha = float(total_land_ha)
        self.budget_rs = budget_rs
        self.use_fuzzy = use_fuzzy
        self.fertilizer_price_factor = 1.0

        self.crop_vec = CropVector.from_candidates(profile.candidate_crops, assessment, use_fuzzy=use_fuzzy)
        self.n_crops = len(profile.candidate_crops)
        n = self.n_crops

        xl = np.concatenate([np.full(n, config.ALLOC_MIN), np.full(n, config.IRRIGATION_MULT_MIN), np.full(n, config.FERTILIZER_MULT_MIN)])
        xu = np.concatenate([np.full(n, config.ALLOC_MAX if config.ALLOC_MAX > 0 else 1.0),
                             np.full(n, config.IRRIGATION_MULT_MAX), np.full(n, config.FERTILIZER_MULT_MAX)])
        xl[0:n] = 1e-4   # avoid a degenerate zero-width allocation bound
        n_ieq_constr = 1 if budget_rs else 0

        cv = self.crop_vec
        self._yield_t_per_ha = cv.yield_kg_ha / 1000.0          # multiplied by confidence after area
        self._cost_rs_per_ha = cv.cost_rs_ha
        self._npk_kg_ha = cv.fert_n_kg_ha + cv.fert_p_kg_ha + cv.fert_k_kg_ha
        super().__init__(n_var=3 * n, n_obj=4, n_ieq_constr=n_ieq_constr, xl=xl, xu=xu)

    def _evaluate(self, X, out, *args, **kwargs):
        n = self.n_crops
        cv = self.crop_vec

        alloc = X[:, 0:n]
        alloc = alloc / np.clip(alloc.sum(axis=1, keepdims=True), 1e-9, None)
        irr_mult = X[:, n : 2 * n]
        fert_mult = X[:, 2 * n : 3 * n]
        area_ha = alloc * self.total_land_ha  # (pop, n_crops)

        f1 = -(area_ha * self._yield_t_per_ha * cv.crop_yield_confidence).sum(axis=1)       # tonnes
        total_cost = (area_ha * self._cost_rs_per_ha).sum(axis=1)                            # Rs
        f2 = total_cost
        f3 = (area_ha * irr_mult * cv.irrigated_share).sum(axis=1)                           # irrigated ha-equivalents
        f4 = (area_ha * fert_mult * self._npk_kg_ha).sum(axis=1)                             # kg N+P2O5+K2O

        out["F"] = np.column_stack([f1, f2, f3, f4])
        if self.budget_rs:
            out["G"] = (total_cost - self.budget_rs).reshape(-1, 1)

    def single_crop_metrics(self) -> List[dict]:
        """Objective values for each candidate crop grown alone at baseline
        input levels (irrigation and fertiliser multipliers 1.0), scaled to
        one hectare. Evaluated through _evaluate itself, so the numbers are
        exactly what the optimiser would compute for such a plan."""
        n = self.n_crops
        X = np.hstack([np.eye(n), np.ones((n, n)), np.ones((n, n))])
        F = self.evaluate(X, return_as_dictionary=True)["F"]
        land = self.total_land_ha or 1.0
        return [
            {
                "crop": name,
                "crop_confidence": float(self.crop_vec.crop_yield_confidence[i]),
                "yield_t_ha": float(-F[i, 0] / land),
                "cost_rs_ha": float(F[i, 1] / land),
                "irrigated_ha_per_ha": float(F[i, 2] / land),
                "env_per_ha": float(F[i, 3] / land),
            }
            for i, name in enumerate(self.crop_vec.names)
        ]

    def decode(self, x: np.ndarray) -> dict:
        """Decode a single chromosome (1D array) into farmer-readable fields."""
        n = self.n_crops
        cv = self.crop_vec
        alloc = x[0:n]
        alloc = alloc / max(alloc.sum(), 1e-9)
        irr_mult = x[n : 2 * n]
        fert_mult = x[2 * n : 3 * n]
        area_ha = alloc * self.total_land_ha
        return {
            "crop_names": cv.names,
            "allocation_fraction": alloc.tolist(),
            "area_ha": area_ha.tolist(),
            "irrigation_multiplier": irr_mult.tolist(),
            "fertilizer_multiplier": fert_mult.tolist(),
        }
