"""Pydantic request/response models for the FastAPI layer."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

Preference = Literal["balanced", "max_yield", "min_cost", "min_water", "min_env_impact"]
RankingProfile = Literal["balanced", "profit", "water", "sustainability", "low_cost", "custom"]


class CustomWeightsIn(BaseModel):
    """TOPSIS weight per decision criterion for profile 'custom'
    (app/decision/criteria.py). Omitted criteria get 0; the weights must
    sum to 1."""
    yield_: Optional[float] = Field(None, ge=0, le=1, alias="yield")
    market_price: Optional[float] = Field(None, ge=0, le=1)
    income: Optional[float] = Field(None, ge=0, le=1)
    cost: Optional[float] = Field(None, ge=0, le=1)
    water: Optional[float] = Field(None, ge=0, le=1)
    env: Optional[float] = Field(None, ge=0, le=1)
    budget: Optional[float] = Field(None, ge=0, le=1)
    soil: Optional[float] = Field(None, ge=0, le=1)
    land: Optional[float] = Field(None, ge=0, le=1)
    rainfall: Optional[float] = Field(None, ge=0, le=1)

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def _sum_to_one(self):
        from app.decision.profiles import validate_custom_weights

        validate_custom_weights(self.as_dict())
        return self

    def as_dict(self) -> dict:
        d = self.model_dump(by_alias=True)
        return {k: v for k, v in d.items() if v is not None}


def _check_fuzzy_model(name: Optional[str]) -> None:
    from app.fuzzy.engine import MODELS

    if name is not None and name not in MODELS:
        raise ValueError(f"Unknown fuzzy model '{name}'. Choose one of {sorted(MODELS)}.")


class RankingProfileIn(BaseModel):
    """Optional ranking profile of a request. Unset keeps the preference
    ranking (balanced by default)."""
    profile: Optional[RankingProfile] = Field(
        None, description="TOPSIS ranking profile. 'balanced' is the default ranking; 'custom' needs custom_weights.")
    custom_weights: Optional[CustomWeightsIn] = None

    @model_validator(mode="after")
    def _profile_consistent(self):
        if self.profile == "custom" and self.custom_weights is None:
            raise ValueError("profile 'custom' needs custom_weights.")
        if self.custom_weights is not None and self.profile != "custom":
            raise ValueError("custom_weights can only be used with profile 'custom'.")
        return self


class FarmPlanRequest(RankingProfileIn):
    location: str = Field(..., examples=["Coimbatore"])
    season: str = Field(..., examples=["Kharif"])
    year: Optional[int] = Field(None, description="Defaults to the latest year in the dataset.")
    total_land_ha: float = Field(..., gt=0, examples=[5.0])
    budget_rs: Optional[float] = Field(None, gt=0, description="Optional hard budget cap (Rs).")
    preference: Preference = "balanced"
    max_candidate_crops: Optional[int] = Field(None, ge=2, le=12)

    # Preference filters applied to the Pareto front before ranking. All
    # four quantities are non-negative by construction, so a negative
    # limit could only ever filter out every plan.
    max_cost_rs: Optional[float] = Field(None, ge=0)
    max_water_liters: Optional[float] = Field(None, ge=0)
    min_yield_tonnes: Optional[float] = Field(None, ge=0)
    max_env_impact: Optional[float] = Field(None, ge=0)

    # Advanced / demo knobs. Capped server-side so a client can't request an
    # absurdly expensive run.
    pop_size: Optional[int] = Field(None, ge=8, le=300)
    n_gen: Optional[int] = Field(None, ge=5, le=500)

    # Persist this run to results/ (JSON + CSV + convergence plot)? Also
    # controls whether per-generation convergence history is tracked at
    # all, since that's the expensive part (~2-3x slower NSGA-II run).
    save_results: bool = True

    # Opaque per-browser id (see src/services/api.js) attached to a saved
    # run so GET /api/history/{location} can show it back only to the
    # client that actually generated it -- there are no real user accounts
    # in this project, so this is what keeps one visitor's saved runs from
    # appearing as another (or a brand-new) visitor's "completed" history.
    # Bounded because it is persisted verbatim into results/<run_id>.json.
    client_id: Optional[str] = Field(None, max_length=128)

    # Also rank the front under every standard profile (meta.profile_comparison).
    compare_profiles: bool = False

    # Fuzzy model for this run (GET /api/fuzzy/models). None = the server's
    # default (config.FUZZY_MODEL, "original" unless configured).
    fuzzy_model: Optional[str] = Field(None, examples=["original"])

    @model_validator(mode="after")
    def _one_weighting(self):
        if self.profile is not None and self.preference != "balanced":
            raise ValueError("Use either a preference or a ranking profile, not both.")
        return self

    @model_validator(mode="after")
    def _known_fuzzy_model(self):
        _check_fuzzy_model(self.fuzzy_model)
        return self


class SoilOut(BaseModel):
    soil_type: str
    avg_ph: float
    organic_carbon_percent: float
    n_status: str
    p_status: str
    k_status: str
    irrigation_percent: float
    fertility_index: float


class RainfallOut(BaseModel):
    avg_monthly_rainfall_mm: float
    avg_deviation_percent: float
    avg_humidity_percent: float
    avg_max_temp_c: float
    avg_min_temp_c: float
    months_used: List[str]
    effective_rainfall_mm: float


class WaterOut(BaseModel):
    avg_storage_percent: float
    groundwater_status: str
    avg_deficit_surplus_mcm: float


class CropCandidateOut(BaseModel):
    name: str
    crop_type: str
    yield_kg_ha: float
    water_req_mm: float
    rainfall_dependency: str
    irrigation_type: str
    sowing_month: str
    harvest_month: str
    crop_duration_days: int


class RegionProfileOut(BaseModel):
    location: str
    year: int
    season: str
    soil: SoilOut
    rainfall: RainfallOut
    water: WaterOut
    candidate_crops: List[CropCandidateOut]
    normalized_snapshot: Dict[str, float]
    # True when this year's CSV rows are flagged "Estimated" (carried
    # forward / scaled from 2023) rather than observed. Defaults to False
    # so records saved before this field existed still validate.
    data_year_estimated: bool = False


class FuzzyAssessmentOut(BaseModel):
    yield_confidence: float
    irrigation_risk: float
    rainfall_label: str
    water_label: str
    soil_label: str


class RankedPlanOut(BaseModel):
    rank: int
    crop_names: List[str]
    allocation_percent: List[float]
    area_ha: List[float]
    irrigation_multiplier: List[float]
    fertilizer_multiplier: List[float]
    yield_tonnes: float
    cost_rs: float
    water_liters: float
    env_impact_score: float
    feasible: bool
    composite_score: float
    normalized_scores: Dict[str, float]
    confidence_label: str
    trade_off_summary: str


class RunMeta(BaseModel):
    algorithm: str = "NSGA-II"
    pop_size: int
    n_gen: int
    crossover_prob: float
    mutation_prob: float
    preference: str
    n_pareto_solutions_found: int
    n_plans_returned: int
    optimize_seconds: float
    # Request inputs needed to explain a saved run later (budget check,
    # per-hectare figures). Optional so runs saved before they existed
    # still validate; the explanation reports them as "not recorded".
    total_land_ha: Optional[float] = None
    budget_rs: Optional[float] = None
    # Pareto-front quality indicators of the run (app/optimization/metrics.py).
    # Optional so runs saved before they existed still validate.
    quality_metrics: Optional["QualityMetricsOut"] = None
    # Weights the ranking used (profile or preference), and the front ranked
    # under every standard profile when requested (app/services/topsis_service.py).
    topsis: Optional[Dict[str, Any]] = None
    profile_comparison: Optional[Dict[str, Any]] = None
    # Fuzzy model that produced the run; absent on runs saved before models existed (= "original").
    fuzzy_model: Optional[str] = None


class MeanObjectivesOut(BaseModel):
    yield_tonnes: float
    cost_rs: float
    water_liters: float
    env_impact_score: float


class QualityMetricsOut(BaseModel):
    """Quality of the run's Pareto front. Distances and volumes are on
    objectives normalised by the reference front's ideal and nadir; the
    reference is the front plus each plan's copy with irrigation and
    fertiliser multipliers at their lower bound (never worse in this model).
    Null when the run has no feasible plan or too few plans for the metric."""
    reference_front: str
    pareto_size: int
    feasible_pareto_size: int
    constraint_satisfaction_rate: Optional[float] = Field(None, description="Share of the final population within budget.")
    dominated_by_lower_bound_copy: Optional[float] = Field(None, description="Share of the front its lower-bound copy beats.")
    runtime_seconds: Optional[float] = None
    generations: Optional[int] = None
    evaluations: Optional[int] = None
    mean_objectives: Optional[MeanObjectivesOut] = None
    hypervolume: Optional[float] = None
    hypervolume_ratio: Optional[float] = Field(None, description="Hypervolume / reference-front hypervolume (1 = converged).")
    gd: Optional[float] = Field(None, description="Generational distance (lower is better).")
    igd: Optional[float] = Field(None, description="Inverted generational distance (lower is better).")
    igd_plus: Optional[float] = Field(None, description="IGD+ (lower is better).")
    spread: Optional[float] = Field(None, description="Generalised spread (lower = more even).")
    spacing: Optional[float] = Field(None, description="Schott spacing (lower = more even).")


class ConvergencePointOut(BaseModel):
    generation: int
    population_size: int
    best_yield_tonnes: float
    mean_yield_tonnes: float
    best_cost_rs: float
    mean_cost_rs: float
    best_water_liters: float
    mean_water_liters: float
    best_env_impact: float
    mean_env_impact: float
    hypervolume: float


class SavedFilesOut(BaseModel):
    run_id: str
    json_path: str
    plans_csv_path: str
    convergence_csv_path: Optional[str] = None
    convergence_plot_path: Optional[str] = None


class FarmPlanResponse(BaseModel):
    region_profile: RegionProfileOut
    fuzzy_assessment: FuzzyAssessmentOut
    plans: List[RankedPlanOut]
    convergence_history: List[ConvergencePointOut] = []
    meta: RunMeta
    run_id: Optional[str] = None
    saved_files: Optional[SavedFilesOut] = None


class SavedRunSummaryOut(BaseModel):
    run_id: str
    location: str
    season: str
    year: int
    preference: Optional[str] = None
    ranking: Optional[str] = None
    saved_at: Optional[str] = None
    n_plans: int
    client_id: Optional[str] = None


class CatalogOut(BaseModel):
    locations: List[str]
    seasons: List[str]
    years: List[int]
    crops_by_season: Dict[str, List[str]]


# ---------------------------------------------------------------------------
# Explainable recommendations (app/services/explanation_service.py)
# ---------------------------------------------------------------------------

class ExplanationItemOut(BaseModel):
    """One explanation statement. `detail` is generated from `evidence`;
    `source` names the pipeline stage the numbers come from."""
    id: str
    title: str
    detail: str
    source: str
    evidence: Dict[str, Any] = {}
    status: Optional[str] = None      # constraints: satisfied | moderate | risk | violated | unknown | not_applicable
    severity: Optional[str] = None    # risks: high | medium | low


class ConfidenceComponentOut(BaseModel):
    id: str
    label: str
    score: Optional[float]            # 0-100, null when it cannot be computed
    weight: float
    detail: str
    source: str


class ConfidenceOut(BaseModel):
    overall_pct: float
    components: List[ConfidenceComponentOut]
    method: str
    strongest_component: str
    weakest_component: str


class ExplanationSummaryOut(BaseModel):
    location: str
    season: str
    year: int
    data_year_estimated: bool
    preference: str
    rank: int
    plans_compared: int
    plans_found: Optional[int] = None
    closeness: float
    recommendation: str
    confidence_pct: float
    total_land_ha: float
    crop_mix: List[Dict[str, Any]]
    per_ha: Dict[str, float]
    totals: Dict[str, float]
    recommendation_rule: str


class ExplanationOut(BaseModel):
    subject: Dict[str, Any]
    summary: ExplanationSummaryOut
    reasons: List[ExplanationItemOut]
    objectives: Dict[str, Any]
    trade_offs: Dict[str, Any]
    constraints: Dict[str, Any]
    benefits: List[ExplanationItemOut]
    risks: List[ExplanationItemOut]
    historical_context: Dict[str, Any]
    confidence: ConfidenceOut
    insights: List[ExplanationItemOut]
    alternatives: List[ExplanationItemOut]
    economics: Dict[str, Any]
    crop_breakdown: List[Dict[str, Any]]
    consistency_checks: Dict[str, Any]
    timeline: List[ExplanationItemOut]
    fuzzy_reasoning: Dict[str, Any]
    # Weight -> contribution -> score of this plan and why it ranks above the
    # next one (app/decision/topsis_explain.py). Optional for older clients.
    topsis: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# District Intelligence (app/services/district_service.py)
# ---------------------------------------------------------------------------

class DistrictSummaryOut(BaseModel):
    sentences: List[str]
    text: str


class DistrictIntelligenceOut(BaseModel):
    """Aggregated district profile. Sections are nested dicts documented in
    docs/handbook/DISTRICT_INTELLIGENCE.md; values the dataset does not
    contain are null with an accompanying note."""
    district: str
    overview: Dict[str, Any]
    coverage: Dict[str, Any]
    climate: Dict[str, Any]
    soil: Dict[str, Any]
    water: Dict[str, Any]
    crops: Dict[str, Any]
    suitability: Dict[str, Any]
    market: Dict[str, Any]
    insights: List[ExplanationItemOut]
    summary: DistrictSummaryOut


# ---------------------------------------------------------------------------
# Scenario Simulation
# ---------------------------------------------------------------------------

class SimulationBaseIn(BaseModel):
    location: str = Field(..., examples=["Salem"])
    season: str = Field(..., examples=["Kharif"])
    year: Optional[int] = Field(None, description="Defaults to the latest year in the dataset.")
    total_land_ha: float = Field(..., gt=0, le=100_000, examples=[5.0])
    budget_rs: Optional[float] = Field(None, gt=0)
    preference: Preference = "balanced"
    # Fuzzy model for both sides of the simulation (GET /api/fuzzy/models).
    fuzzy_model: Optional[str] = None

    @model_validator(mode="after")
    def _known_fuzzy_model(self):
        _check_fuzzy_model(self.fuzzy_model)
        return self


class PrioritiesIn(BaseModel):
    """Relative importance (0-100) of each objective; normalised into TOPSIS weights."""
    yield_: float = Field(..., ge=0, le=100, alias="yield")
    cost: float = Field(..., ge=0, le=100)
    water: float = Field(..., ge=0, le=100)
    env: float = Field(..., ge=0, le=100)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _not_all_zero(self):
        if self.yield_ + self.cost + self.water + self.env <= 0:
            raise ValueError("At least one priority must be above zero.")
        return self

    def as_dict(self) -> dict:
        return {"yield": self.yield_, "cost": self.cost, "water": self.water, "env": self.env}


class ScenarioIn(BaseModel):
    rainfall_change_pct: Literal[-30, -20, -10, 0, 10, 20, 30] = 0
    water_availability: Literal["current", "very_low", "low", "medium", "high", "very_high"] = "current"
    fertilizer_cost_change_pct: Literal[-20, -10, 0, 10, 20, 30] = 0
    market_price: Literal["decrease", "stable", "increase"] = "stable"
    total_land_ha: Optional[float] = Field(None, gt=0, le=100_000, description="Defaults to the baseline land.")
    budget_rs: Optional[float] = Field(None, gt=0, description="Defaults to the baseline budget.")
    preference: Optional[Preference] = Field(None, description="Defaults to the baseline preference.")
    priorities: Optional[PrioritiesIn] = Field(None, description="Overrides the preference's TOPSIS weights.")


class SimulationRequest(BaseModel):
    base: SimulationBaseIn
    scenario: ScenarioIn = ScenarioIn()
    client_id: Optional[str] = Field(None, max_length=128)

    def as_payload(self) -> dict:
        scenario = self.scenario.model_dump(exclude={"priorities"})
        scenario["priorities"] = self.scenario.priorities.as_dict() if self.scenario.priorities else None
        return {"base": self.base.model_dump(), "scenario": scenario}


class SimulationOut(BaseModel):
    """Scenario simulation result; see docs/handbook/SCENARIO_SIMULATION.md."""
    token: Optional[str] = None
    inputs: Dict[str, Any]
    conditions: List[Dict[str, Any]]
    baseline: Dict[str, Any]
    scenario: Dict[str, Any]
    comparison: Optional[Dict[str, Any]] = None
    impact: Optional[Dict[str, Any]] = None
    crop_effects: List[Dict[str, Any]]
    fuzzy_changes: Dict[str, Any]
    optimization: Dict[str, Any]
    constraints: List[Dict[str, Any]]
    historical: Dict[str, Any]
    decision_impact: List[ExplanationItemOut]
    trade_offs: Dict[str, Any]
    summary: Dict[str, Any]
    meta: Dict[str, Any]


class SimulationSaveIn(BaseModel):
    token: str = Field(..., min_length=8, max_length=64)
    name: Optional[str] = Field(None, max_length=80)
    client_id: str = Field(..., min_length=1, max_length=128)


class SavedSimulationSummaryOut(BaseModel):
    simulation_id: str
    name: Optional[str] = None
    saved_at: Optional[str] = None
    location: str
    season: str
    year: Optional[int] = None
    changes: List[str]
    headline: Dict[str, Any]


class SavedSimulationOut(BaseModel):
    simulation_id: str
    name: Optional[str] = None
    saved_at: Optional[str] = None
    inputs: Dict[str, Any]
    result: SimulationOut


# ---------------------------------------------------------------------------
# Dynamic TOPSIS (app/services/topsis_service.py)
# ---------------------------------------------------------------------------

class TopsisRerankIn(RankingProfileIn):
    profile: RankingProfile = "balanced"
    compare: bool = True


class TopsisRankingOut(BaseModel):
    topsis: Dict[str, Any]
    plans: List[RankedPlanOut]
    ranked_over: str
    plans_ranked: int
    explanation: Dict[str, Any]
    comparison: Optional[Dict[str, Any]] = None
