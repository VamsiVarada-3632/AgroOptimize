"""
Ranking profiles: named TOPSIS weight vectors over the decision criteria.

Balanced is the published ranking: the "balanced" preference weights over
the four optimiser objectives, unchanged. Every other profile is defined
by three importance tiers (high, medium, low) and turned into weights with
rank-sum weighting over the tiers (Stillwell, Seaver & Edwards 1981): a
criterion in tier t gets 3, 2 or 1 points, normalised to sum to 1.
Criteria a profile does not list get weight 0 and do not enter its ranking.

A custom profile is a weight per criterion supplied by the user; the
weights must sum to 1. Definitions and rationale:
docs/handbook/TOPSIS_PROFILE_GUIDE.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional

from app.decision.criteria import CRITERIA, CRITERIA_META
from app.decision.ranking import _PREFERENCE_WEIGHTS

TIER_POINTS = {"high": 3, "medium": 2, "low": 1}
WEIGHT_SUM_TOLERANCE = 1e-6

PROFILES: Dict[str, dict] = {
    "balanced": {
        "label": "Balanced",
        "summary": "The published ranking: yield against the three footprint objectives.",
        "method": "fixed weights of the 'balanced' preference (app/decision/ranking.py)",
    },
    "profit": {
        "label": "Profit priority",
        "summary": "Favours income, crop price and yield; water and environmental impact count least.",
        "tiers": {"high": ("income", "market_price", "yield"), "medium": ("cost",), "low": ("water", "env")},
    },
    "water": {
        "label": "Water saving",
        "summary": "Favours low irrigation water and low environmental impact; yield and income count least.",
        "tiers": {"high": ("water", "env"), "medium": ("cost",), "low": ("yield", "income")},
    },
    "sustainability": {
        "label": "Sustainability",
        "summary": "Favours low environmental impact, low water use and crops that suit the soil; income counts least.",
        "tiers": {"high": ("env", "water", "soil"), "medium": ("yield", "cost", "rainfall"), "low": ("income",)},
    },
    "low_cost": {
        "label": "Low cost",
        "summary": "Favours low production cost and budget headroom; yield counts least.",
        "tiers": {"high": ("cost", "budget"), "medium": ("water", "env"), "low": ("yield",)},
    },
}
PROFILE_NAMES = tuple(PROFILES) + ("custom",)


def rank_sum_weights(tiers: Mapping[str, tuple]) -> Dict[str, float]:
    points = {c: TIER_POINTS[t] for t, crits in tiers.items() for c in crits}
    total = sum(points.values())
    return {c: points.get(c, 0) / total for c in CRITERIA}


def balanced_weights() -> Dict[str, float]:
    w = _PREFERENCE_WEIGHTS["balanced"]
    return {c: float(w.get(c, 0.0)) for c in CRITERIA}


def profile_weights(name: str) -> Dict[str, float]:
    if name == "balanced":
        return balanced_weights()
    if name not in PROFILES:
        raise ValueError(f"Unknown profile '{name}'. Use one of: {', '.join(PROFILE_NAMES)}.")
    return rank_sum_weights(PROFILES[name]["tiers"])


def validate_custom_weights(weights: Optional[Mapping[str, float]]) -> Dict[str, float]:
    """Full criterion -> weight dict for a custom profile. Missing criteria
    get 0; every weight must be in [0, 1] and the weights must sum to 1."""
    if not weights:
        raise ValueError("A custom profile needs custom_weights.")
    unknown = sorted(set(weights) - set(CRITERIA))
    if unknown:
        raise ValueError(f"Unknown criteria: {', '.join(unknown)}. Use: {', '.join(CRITERIA)}.")
    out = {c: float(weights.get(c, 0.0)) for c in CRITERIA}
    bad = [c for c, w in out.items() if not 0.0 <= w <= 1.0]
    if bad:
        raise ValueError(f"Weights must be between 0 and 1: {', '.join(bad)}.")
    total = sum(out.values())
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ValueError(f"Custom weights must sum to 1 (they sum to {total:.6g}).")
    return out


@dataclass(frozen=True)
class WeightSpec:
    """The weights one ranking uses, with where they came from."""
    profile: str                 # a PROFILE_NAMES entry
    label: str
    weights: Dict[str, float]    # every criterion, summing to 1

    @property
    def active(self):
        """Criteria with a positive weight, in CRITERIA order."""
        return tuple(c for c in CRITERIA if self.weights[c] > 0)

    @property
    def needs_crop_attributes(self) -> bool:
        return any(c not in ("yield", "cost", "water", "env") for c in self.active)

    def as_dict(self) -> dict:
        return {
            "profile": self.profile, "label": self.label,
            "weights": {c: self.weights[c] for c in CRITERIA},
            "criteria": [{"key": c, **{k: CRITERIA_META[c][k] for k in ("label", "direction")}, "weight": self.weights[c]}
                         for c in self.active],
        }


def resolve(profile: str, custom_weights: Optional[Mapping[str, float]] = None) -> WeightSpec:
    if profile == "custom":
        return WeightSpec("custom", "Custom", validate_custom_weights(custom_weights))
    if custom_weights:
        raise ValueError("custom_weights can only be used with profile 'custom'.")
    weights = profile_weights(profile)
    return WeightSpec(profile, PROFILES[profile]["label"], weights)


def catalogue() -> dict:
    """Every profile with its weights and every criterion's definition, for
    GET /api/topsis/profiles and the frontend's profile selector."""
    profiles = []
    for name, p in PROFILES.items():
        entry = {"profile": name, "label": p["label"], "summary": p["summary"], "weights": profile_weights(name)}
        if "tiers" in p:
            entry["tiers"] = {t: list(c) for t, c in p["tiers"].items()}
            entry["method"] = "rank-sum weights over importance tiers (high 3, medium 2, low 1 points)"
        else:
            entry["method"] = p["method"]
        profiles.append(entry)
    return {
        "default_profile": "balanced",
        "profiles": profiles,
        "criteria": [{"key": c, **CRITERIA_META[c]} for c in CRITERIA],
        "custom": {"default_weights": balanced_weights(), "sum_to": 1.0, "tolerance": WEIGHT_SUM_TOLERANCE,
                   "min": 0.0, "max": 1.0},
    }
