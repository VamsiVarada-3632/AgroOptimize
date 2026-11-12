"""
Central configuration and "assumption constants" for AgroOptimize.

Every number in this file that is NOT sourced directly from the datasets in
the official datasets (see official_dataset_mapping.json) is a modelling assumption. They are collected here (instead of
being scattered as magic numbers through the codebase) for two reasons:

1. It makes the whole system easy to re-tune (e.g. if fertilizer prices
   change, edit one line).
2. It gives a single place to point to during the viva when asked
   "where does this number come from?" -- see notes/methodology_notes.md
   for the justification of each assumption below.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
OFFICIAL_DATA_DIR = PROJECT_ROOT / "data" / "official"
# Saved runs and simulations. Overridable so a deployment can point it at a
# persistent disk (e.g. a Render disk mounted at /var/data/results).
RESULTS_DIR = Path(os.environ.get("AGROOPTIMIZE_RESULTS_DIR") or PROJECT_ROOT / "results")

# ---------------------------------------------------------------------------
# Dataset structure - everything below is derived from the OFFICIAL database
# ---------------------------------------------------------------------------
# Agricultural (cropping) seasons of the official Tamil Nadu reports. There is no "Summer" season in them.
AG_SEASONS = ["Kharif", "Rabi"]

# IMD-season windows used to aggregate official monthly rainfall / reservoir data (documented crosswalk,
# app/datasets/reference.py): Kharif = South-West monsoon, Rabi = North-East monsoon + winter.
from app.datasets.reference import SEASON_MONTHS as SEASON_MONTH_MAP  # noqa: E402

_LAZY = {}


def __getattr__(name):
    """LOCATIONS = the official districts that have crop statistics (38 in the 2024-25 reports); resolved lazily
    from the database so importing config never touches the database."""
    if name == "LOCATIONS":
        if "LOCATIONS" not in _LAZY:
            from app.data import official_view
            _LAZY["LOCATIONS"] = official_view.locations()
        return list(_LAZY["LOCATIONS"])
    raise AttributeError(name)


# ---------------------------------------------------------------------------
# Candidate crop selection
# ---------------------------------------------------------------------------
# Upper bound on how many candidate crops (top-N by historical revenue) enter
# the chromosome. Every candidate always receives a small non-zero share
# (allocation lower bound 1e-4 in problem.py), so this is also the maximum
# number of crops in a plan. The dataset has at most 5 crops per
# location/season/year, so in practice all available crops are used. (The
# reference paper's reported plans mix 3 crops, e.g. "Sugarcane + Wheat +
# Groundnut"; this value does not enforce that.)
DEFAULT_MAX_CANDIDATE_CROPS = 6
MIN_CANDIDATE_CROPS = 2

# Fuzzy model (see docs/handbook/FUZZY_MODEL_IMPROVEMENTS.md). "original" is
# the published Mamdani system (reproducible with the paper tag); "official" (default) calibrates the sets on the official data; other
# models in app/fuzzy/engine.MODELS change the fuzzy outputs and must be
# selected here, with the AGROOPTIMIZE_FUZZY_MODEL environment variable, or
# per request (FarmPlanRequest.fuzzy_model).
FUZZY_MODEL = os.environ.get("AGROOPTIMIZE_FUZZY_MODEL", "official")

# ---------------------------------------------------------------------------
# Decision variable bounds (chromosome design, Section III-D)
# ---------------------------------------------------------------------------
ALLOC_MIN, ALLOC_MAX = 0.0, 1.0           # land allocation fraction per crop
IRRIGATION_MULT_MIN, IRRIGATION_MULT_MAX = 0.7, 1.3   # multiplier on baseline water need
FERTILIZER_MULT_MIN, FERTILIZER_MULT_MAX = 0.7, 1.3   # multiplier on baseline fertilizer dose

# ---------------------------------------------------------------------------
# NSGA-II hyperparameters -- match the values reported in the reference
# paper (Section III-D): 200 generations, single-point crossover p=0.85,
# Gaussian mutation p=0.12.
# ---------------------------------------------------------------------------
NSGA2_POP_SIZE = 80
NSGA2_N_GEN = 200
NSGA2_CROSSOVER_PROB = 0.85
NSGA2_MUTATION_PROB = 0.12
NSGA2_MUTATION_SIGMA = 0.12
NSGA2_SEED = 42

# Fast settings used by automated tests / quick smoke checks so the whole
# suite runs in a couple of seconds instead of ~10s per optimisation run.
NSGA2_FAST_POP_SIZE = 24
NSGA2_FAST_N_GEN = 15

# ---------------------------------------------------------------------------
# NSGA-II engine modes (see docs/handbook/NSGAII_IMPROVEMENTS.md).
#
# "original" is the published engine: it reproduces every published result
# bit for bit and is the default. "enhanced" is the experimental engine; it
# changes the optimisation outputs and must be selected explicitly, either
# here or with the AGROOPTIMIZE_NSGA2_MODE environment variable. Each
# improvement is a separate switch, so any one of them can be benchmarked on
# its own (scripts/benchmark_nsga2.py) on top of either mode.
#
# Diversity monitoring and runtime profiling only observe the run (they draw
# no random numbers), so they are on in both modes without changing results.
# Enhanced mode = the switches the benchmark accepted: smart initialisation,
# adaptive mutation (PR #12), constraint-aware initialisation and duplicate
# avoidance; the others are available for ablation runs but measured no
# benefit (docs/handbook/NSGAII_BENCHMARK_RESULTS.md).
# ---------------------------------------------------------------------------
NSGA2_ENGINE_MODE = os.environ.get("AGROOPTIMIZE_NSGA2_MODE", "original")

NSGA2_ENGINE_FEATURES = {
    "original": {
        "adaptive_mutation": False,
        "adaptive_crossover": False,
        "smart_initialization": False,
        "duplicate_removal": False,
        "early_stopping": False,
        "lhs_initialization": False,
        "constraint_aware_initialization": False,
        "duplicate_avoidance": False,
        "parallel_evaluation": False,
        "diversity_monitoring": True,
        "runtime_profiling": True,
    },
    "enhanced": {
        "adaptive_mutation": True,
        "adaptive_crossover": False,
        "smart_initialization": True,
        "duplicate_removal": False,
        "early_stopping": False,
        "lhs_initialization": False,
        "constraint_aware_initialization": True,
        "duplicate_avoidance": True,
        "parallel_evaluation": False,
        "diversity_monitoring": True,
        "runtime_profiling": True,
    },
}

# Base per-gene mutation probability of each mode. The original engine uses
# the paper's 0.12; the parameter study found 0.05 better on this problem
# (NSGAII_PROFILE.md section 4), so the enhanced engine starts from 0.05 and
# adapts it from there.
NSGA2_ENGINE_MUTATION_PROB = {"original": NSGA2_MUTATION_PROB, "enhanced": 0.05}

# Adaptive mutation: the per-gene probability rises when decision-space
# diversity falls below `diversity_floor` x its initial value, and is scaled
# by `converged_scale` once the front has stagnated, within [min, max].
# Tuned on seeds 100-104 (NSGAII_PROFILE.md); evaluated on seeds 0-9.
NSGA2_ADAPTIVE_MUTATION = {"min_prob": 0.02, "max_prob": 0.30, "diversity_floor": 0.5, "converged_scale": 0.2}

# Adaptive crossover. schedule "linear": probability moves linearly from
# `start_prob` (exploration) in the first generation to `end_prob`
# (exploitation) in the last. schedule "diversity": `high_diversity_prob`
# while allocation diversity is at its peak so far, rising towards
# `low_diversity_prob` as it falls to `diversity_floor` x that peak (more
# recombination to escape stagnation).
NSGA2_ADAPTIVE_CROSSOVER = {"schedule": "linear", "start_prob": 0.95, "end_prob": 0.70,
                            "high_diversity_prob": 0.85, "low_diversity_prob": 0.95, "diversity_floor": 0.5}

# Smart initialisation: share of the initial population seeded from the
# district's candidate crops; the rest is drawn uniformly at random (or by
# Latin Hypercube sampling when lhs_initialization is on).
NSGA2_SMART_INIT_FRACTION = 0.2

# Duplicate removal: offspring closer than this (Euclidean distance in the
# decision space normalised to [0, 1] per gene) to another individual are
# rejected. pymoo's default rejects only exact copies (1e-16).
NSGA2_DUPLICATE_TOLERANCE = 1e-4

# Parallel evaluation: number of threads the population is split over when
# the parallel_evaluation switch is on.
NSGA2_PARALLEL_WORKERS = 4

# Early stopping. criterion "hypervolume": stop when the hypervolume of the
# first front has improved by less than `tolerance` (relative) over the last
# `patience` generations, never before `min_generations`. criterion
# "objective_space": pymoo's robust multi-objective termination (Blank & Deb
# 2020) -- stop when the movement of the decision vectors (`xtol`), of the
# constraint violation and of the front in objective space (`ftol`, ideal,
# nadir and front change) has stayed below tolerance for `period`
# generations, checked every `n_skip`.
# (`patience` and `tolerance` also set when adaptive mutation regards the
# front as stagnant.)
NSGA2_EARLY_STOPPING = {"criterion": "hypervolume", "patience": 30, "tolerance": 1e-4, "min_generations": 60,
                        "xtol": 0.0005, "ftol": 0.005, "period": 50, "n_skip": 5}

# ---------------------------------------------------------------------------
# Decision output
# ---------------------------------------------------------------------------
MAX_RETURNED_PLANS = 50
