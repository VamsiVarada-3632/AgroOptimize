"""
Switches and parameters of the NSGA-II engine, read from app/config.py.

Two modes are defined there: "original" (the published engine, the default)
and "enhanced" (experimental). Each improvement is an independent flag, so a
caller or benchmark can start from either mode and flip any single feature:

    settings = engine_settings("original")
    run_nsga2(problem, engine=dataclasses.replace(settings, early_stopping=True))
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields

from app import config

MODES = ("original", "enhanced")


@dataclass(frozen=True)
class EngineSettings:
    mode: str = "original"
    adaptive_mutation: bool = False
    adaptive_crossover: bool = False
    smart_initialization: bool = False
    duplicate_removal: bool = False
    early_stopping: bool = False
    lhs_initialization: bool = False
    constraint_aware_initialization: bool = False
    duplicate_avoidance: bool = False
    diversity_monitoring: bool = True
    runtime_profiling: bool = True
    # Base per-gene mutation probability (the adaptive rule starts from it).
    mutation_prob: float = config.NSGA2_MUTATION_PROB
    # Parameters of the individual features (copied so a run records exactly what it used).
    adaptive_mutation_params: dict = field(default_factory=lambda: dict(config.NSGA2_ADAPTIVE_MUTATION))
    adaptive_crossover_params: dict = field(default_factory=lambda: dict(config.NSGA2_ADAPTIVE_CROSSOVER))
    smart_init_fraction: float = config.NSGA2_SMART_INIT_FRACTION
    duplicate_tolerance: float = config.NSGA2_DUPLICATE_TOLERANCE
    early_stopping_params: dict = field(default_factory=lambda: dict(config.NSGA2_EARLY_STOPPING))

    @property
    def changes_outputs(self) -> bool:
        """True when any feature that alters the search is on (the observers do not)."""
        return any(getattr(self, name) for name in FEATURES_CHANGING_OUTPUTS)

    def enabled_features(self) -> list:
        return [f.name for f in fields(self) if isinstance(getattr(self, f.name), bool) and getattr(self, f.name)]

    def describe(self) -> dict:
        """What a run records about its engine (stored in the run's meta)."""
        out = {"mode": self.mode, "features": self.enabled_features(), "mutation_prob": self.mutation_prob}
        if self.adaptive_mutation:
            out["adaptive_mutation"] = dict(self.adaptive_mutation_params)
        if self.adaptive_crossover:
            out["adaptive_crossover"] = dict(self.adaptive_crossover_params)
        if self.smart_initialization:
            out["smart_init_fraction"] = self.smart_init_fraction
        if self.duplicate_removal:
            out["duplicate_tolerance"] = self.duplicate_tolerance
        if self.early_stopping:
            out["early_stopping"] = dict(self.early_stopping_params)
        return out


FEATURES_CHANGING_OUTPUTS = (
    "adaptive_mutation",
    "adaptive_crossover",
    "smart_initialization",
    "duplicate_removal",
    "early_stopping",
    "lhs_initialization",
    "constraint_aware_initialization",
    "duplicate_avoidance",
)


def engine_settings(mode: str | None = None) -> EngineSettings:
    """Settings for a mode; None means the configured default (NSGA2_ENGINE_MODE)."""
    mode = (mode or config.NSGA2_ENGINE_MODE).strip().lower()
    if mode not in MODES:
        raise ValueError(f"Unknown NSGA-II engine mode {mode!r}; expected one of {MODES}")
    return EngineSettings(mode=mode, mutation_prob=config.NSGA2_ENGINE_MUTATION_PROB[mode],
                          **config.NSGA2_ENGINE_FEATURES[mode])
