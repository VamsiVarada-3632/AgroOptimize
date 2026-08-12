"""
Central configuration and "assumption constants" for AgroOptimize.

Every number in this file that is NOT sourced directly from the datasets in
data/raw/ is a modelling assumption. They are collected here (instead of
being scattered as magic numbers through the codebase) for two reasons:

1. It makes the whole system easy to re-tune (e.g. if fertilizer prices
   change, edit one line).
2. It gives a single place to point to during the viva when asked
   "where does this number come from?" -- see notes/methodology_notes.md
   for the justification of each assumption below.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
RESULTS_DIR = PROJECT_ROOT / "results"

# ---------------------------------------------------------------------------
# Dataset structure (data/raw/<location>_<kind>.csv)
# ---------------------------------------------------------------------------
LOCATIONS = ["Coimbatore", "Erode", "Salem", "Pollachi"]
DATASET_KINDS = ["crop", "land", "rainfall", "water_availability"]

# Agricultural (cropping) seasons used in crop.csv / land.csv
AG_SEASONS = ["Kharif", "Rabi", "Summer"]

# Meteorological months that fall inside each agricultural season. Used to
# aggregate the monthly rainfall.csv / water_availability.csv records onto
# the coarser Kharif/Rabi/Summer granularity used for cropping decisions.
# This mapping follows the standard Tamil Nadu agricultural calendar and is
# a documented modelling assumption (see methodology notes, Section 2).
SEASON_MONTH_MAP = {
    "Kharif": ["June", "July", "August", "September"],
    "Rabi": ["October", "November", "December", "January", "February", "March"],
    "Summer": ["February", "March", "April", "May"],
}

# ---------------------------------------------------------------------------
# Candidate crop selection
# ---------------------------------------------------------------------------
# A farmer plan mixes at most this many crops (matches the 3-crop-style
# combinations reported in the reference paper's results, e.g. "Sugarcane +
# Wheat + Groundnut"). If fewer crops are available for a location/season,
# all of them are used.
DEFAULT_MAX_CANDIDATE_CROPS = 6
MIN_CANDIDATE_CROPS = 2

# ---------------------------------------------------------------------------
# Economic assumptions (₹) -- used to turn dataset fields into a cost figure
# ---------------------------------------------------------------------------
# Approximate wholesale price per kg of nutrient (not per kg of fertilizer
# product) for Urea (N), DAP (P) and MOP (K), India, typical 2024-25 retail
# range. Documented assumption -- tune to current prices if needed.
FERTILIZER_PRICE_RS_PER_KG_NUTRIENT = {
    "N": 6.5,
    "P": 27.0,
    "K": 17.0,
}
LABOR_WAGE_RS_PER_DAY = 400.0

# ---------------------------------------------------------------------------
# Water assumptions
# ---------------------------------------------------------------------------
# 1 mm of water applied over 1 hectare = 10,000 litres (standard conversion:
# 1 mm/ha = 10 m^3/ha = 10,000 L/ha).
LITERS_PER_MM_PER_HA = 10_000.0

# Fraction of seasonal rainfall that is agronomically usable by the crop
# (rest is lost to runoff / deep percolation / evaporation). Used to derive
# "effective rainfall" that offsets the irrigation requirement.
RAINFALL_UTILIZATION_FACTOR = 0.7

# ---------------------------------------------------------------------------
# Environmental impact proxy weights (Section III-D of the reference paper:
# "environmental impact score calculated as the product of the chemical
# leaching risk and carbon emission proxies")
# ---------------------------------------------------------------------------
CARBON_FERTILIZER_FACTOR = 0.15   # synthetic carbon-proxy units per kg NPK applied
CARBON_PUMPING_FACTOR = 0.01      # synthetic carbon-proxy units per mm irrigation per ha

# Dependency of a crop's yield confidence on rainfall adequacy, keyed off
# the dataset's own `Rainfall_Dependency` column (Very Low/Low/Medium/High).
RAINFALL_DEPENDENCY_FACTOR = {
    "Very Low": 0.1,
    "Low": 0.3,
    "Medium": 0.6,
    "High": 1.0,
}

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
# Decision output
# ---------------------------------------------------------------------------
MAX_RETURNED_PLANS = 50
