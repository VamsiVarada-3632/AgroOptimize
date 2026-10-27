"""
Decision criteria for the TOPSIS ranking stage.

NSGA-II optimises four objectives (yield, cost, water, environmental
impact). The ranking stage can also score each Pareto-optimal plan on six
further criteria that are computed from the same plan and the same dataset
row of every crop, without touching the optimiser:

    criterion      direction  per-plan value
    yield          benefit    expected yield, t                       (NSGA-II f1)
    cost           cost       production cost, Rs                     (NSGA-II f2)
    water          cost       irrigation water, L                     (NSGA-II f3)
    env            cost       environmental impact index              (NSGA-II f4)
    market_price   benefit    tonnage-weighted crop price, Rs/quintal
    income         benefit    indicative net income: tonnes x price - cost, Rs
    budget         benefit    budget headroom: budget - cost, Rs (neutral without a budget)
    soil           benefit    nutrient-demand match of the crops to the soil's N/P/K status, 0-1
    land           benefit    land-use diversification: Shannon evenness of the allocation, 0-1
    rainfall       cost       rainfall exposure: area-weighted Rainfall_Dependency factor, 0.1-1

Prices are the dataset's MSP_Rs_Qtl column, the same source as the
explanation service's indicative economics. Definitions, sources and
caveats: docs/handbook/TOPSIS_DYNAMIC_ENGINE.md section 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

from app import config
from app.data.loader import load_all
from app.fuzzy import engine as fz

CRITERIA = ("yield", "cost", "water", "env", "market_price", "income", "budget", "soil", "land", "rainfall")
OPTIMISER_CRITERIA = ("yield", "cost", "water", "env")

CRITERIA_META: Dict[str, dict] = {
    "yield": {"label": "Yield", "direction": "benefit", "unit": "t", "source": "NSGA-II objective f1"},
    "cost": {"label": "Production cost", "direction": "cost", "unit": "₹", "source": "NSGA-II objective f2"},
    "water": {"label": "Water", "direction": "cost", "unit": "L", "source": "NSGA-II objective f3"},
    "env": {"label": "Environmental impact", "direction": "cost", "unit": "index", "source": "NSGA-II objective f4"},
    "market_price": {"label": "Market price", "direction": "benefit", "unit": "₹/quintal",
                     "source": "dataset MSP_Rs_Qtl, weighted by each crop's expected tonnes"},
    "income": {"label": "Income", "direction": "benefit", "unit": "₹",
               "source": "expected tonnes × MSP_Rs_Qtl − production cost (indicative)"},
    "budget": {"label": "Budget", "direction": "benefit", "unit": "₹",
               "source": "budget − production cost; neutral when no budget is set"},
    "soil": {"label": "Soil suitability", "direction": "benefit", "unit": "0–1",
             "source": "crop N/P/K demand matched to the district's soil N/P/K status"},
    "land": {"label": "Land use", "direction": "benefit", "unit": "0–1",
             "source": "Shannon evenness of the land allocation (crop diversification)"},
    "rainfall": {"label": "Rainfall exposure", "direction": "cost", "unit": "0.1–1",
                 "source": "area-weighted RAINFALL_DEPENDENCY_FACTOR of the crops"},
}

# Share of a nutrient the crop has to get from fertiliser rather than the
# soil, by the soil's status of that nutrient (land.csv N/P/K_Status).
SOIL_DEFICIT = {"Low": 1.0, "Medium": 0.5, "High": 0.0}


@dataclass(frozen=True)
class CropAttributes:
    """Per-crop inputs of the extra criteria, in the candidate order of the
    run (the order of every plan's crop_names)."""
    names: List[str]
    yield_t_ha: np.ndarray       # dataset yield, t/ha
    confidence: np.ndarray       # fuzzy-adjusted crop yield confidence (as in FarmPlanProblem)
    price_rs_qtl: np.ndarray     # MSP_Rs_Qtl
    soil_fit: np.ndarray         # 0-1, see soil_fit()
    rainfall_factor: np.ndarray  # RAINFALL_DEPENDENCY_FACTOR of Rainfall_Dependency


def soil_fit(npk_kg_ha: np.ndarray, statuses: Sequence[str]) -> np.ndarray:
    """0-1 match of each crop's N, P and K demand to the soil.

    For each nutrient the crop's dose is scaled by the largest dose among
    the candidates (1 = the hungriest crop) and multiplied by the soil's
    deficit for that nutrient (Low 1, Medium 0.5, High 0). The fit is one
    minus the mean over N, P and K: 1 when the soil supplies what the crop
    needs, lower for demanding crops on deficient soil.

    npk_kg_ha: (n_crops, 3) array of N, P, K doses; statuses: N, P, K status."""
    npk = np.asarray(npk_kg_ha, dtype=float)
    peak = npk.max(axis=0)
    demand = np.divide(npk, peak, out=np.zeros_like(npk), where=peak > 0)
    deficit = np.array([SOIL_DEFICIT.get(s, 0.5) for s in statuses])
    return 1.0 - (demand * deficit).mean(axis=1)


def crop_attributes(region_profile: dict, fuzzy: dict) -> CropAttributes:
    """Build CropAttributes from a run's region_profile block and fuzzy
    assessment (the FarmPlanResponse fields, live or saved). Prices and
    fertiliser doses come from the same crop.csv rows the run used."""
    rp = region_profile
    crops = rp["candidate_crops"]
    crop_df = load_all()["crop"]
    rows = crop_df[(crop_df["Location"] == rp["location"]) & (crop_df["Year"] == rp["year"])
                   & (crop_df["Season"] == rp["season"])].drop_duplicates("Crop_Name").set_index("Crop_Name")
    names = [c["name"] for c in crops]
    missing = [n for n in names if n not in rows.index]
    if missing:
        raise ValueError(f"No crop.csv row for {', '.join(missing)} in {rp['location']} {rp['season']} {rp['year']}.")
    r = rows.loc[names]
    soil = rp["soil"]
    return CropAttributes(
        names=names,
        yield_t_ha=np.array([c["yield_kg_ha"] for c in crops], dtype=float) / 1000.0,
        confidence=np.array([fz.crop_yield_confidence(fuzzy["yield_confidence"], fuzzy["irrigation_risk"],
                                                      c["rainfall_dependency"]) for c in crops]),
        price_rs_qtl=r["MSP_Rs_Qtl"].to_numpy(dtype=float),
        soil_fit=soil_fit(r[["Fertilizer_N_Kg_Ha", "Fertilizer_P_Kg_Ha", "Fertilizer_K_Kg_Ha"]].to_numpy(dtype=float),
                          [soil["n_status"], soil["p_status"], soil["k_status"]]),
        rainfall_factor=np.array([config.RAINFALL_DEPENDENCY_FACTOR.get(c["rainfall_dependency"], 0.6) for c in crops]),
    )


def _field(plan, name):
    return plan[name] if isinstance(plan, dict) else getattr(plan, name)


def plan_criteria(plans: Sequence, attrs: Optional[CropAttributes], budget_rs: Optional[float] = None,
                  keys: Sequence[str] = CRITERIA) -> Dict[str, List[float]]:
    """Raw criterion values of every plan, for the requested criteria.

    plans are FarmPlan objects or RankedPlanOut-shaped dicts. attrs may be
    None when only the four optimiser criteria are requested."""
    out: Dict[str, List[float]] = {}
    for k, field in (("yield", "yield_tonnes"), ("cost", "cost_rs"), ("water", "water_liters"), ("env", "env_impact_score")):
        if k in keys:
            out[k] = [float(_field(p, field)) for p in plans]
    extra = [k for k in keys if k not in OPTIMISER_CRITERIA]
    if not extra:
        return out
    if attrs is None:
        raise ValueError("Crop attributes are needed for criteria beyond the four optimiser objectives.")
    area = np.array([_field(p, "area_ha") for p in plans], dtype=float)          # (plans, crops)
    names = list(_field(plans[0], "crop_names")) if plans else attrs.names
    if names != attrs.names:
        raise ValueError("Plan crops do not match the crop attributes of this run.")
    land = area.sum(axis=1, keepdims=True)
    share = np.divide(area, land, out=np.zeros_like(area), where=land > 0)
    tonnes = area * attrs.yield_t_ha * attrs.confidence
    cost = np.array([float(_field(p, "cost_rs")) for p in plans])
    revenue = (tonnes * 10.0 * attrs.price_rs_qtl).sum(axis=1)                   # 1 t = 10 quintals
    total_t = tonnes.sum(axis=1)
    if "market_price" in keys:
        out["market_price"] = np.divide(revenue / 10.0, total_t, out=np.zeros_like(total_t), where=total_t > 0).tolist()
    if "income" in keys:
        out["income"] = (revenue - cost).tolist()
    if "budget" in keys:
        out["budget"] = ((budget_rs - cost) if budget_rs else np.zeros_like(cost)).tolist()
    if "soil" in keys:
        out["soil"] = (share * attrs.soil_fit).sum(axis=1).tolist()
    if "land" in keys:
        n = share.shape[1]
        logs = np.log(share, out=np.zeros_like(share), where=share > 0)
        entropy = -(share * logs).sum(axis=1)
        out["land"] = (entropy / np.log(n) if n > 1 else np.zeros(len(plans))).tolist()
    if "rainfall" in keys:
        out["rainfall"] = (share * attrs.rainfall_factor).sum(axis=1).tolist()
    return {k: out[k] for k in keys}
