#!/usr/bin/env python3
"""
Standalone CLI demo -- no server required. Good for a quick guide-review or
viva demo: "run one command, see the whole pipeline work end to end."

Examples:
    python3 run_demo.py --location Coimbatore --season Kharif --land 5 --budget 200000
    python3 run_demo.py --location Erode --season Rabi --land 3 --preference max_yield --top 3
"""

from __future__ import annotations

import argparse
import sys

from app import config
from app.schemas import FarmPlanRequest
from app.services.plan_service import generate_farm_plans


def parse_args():
    parser = argparse.ArgumentParser(description="AgroOptimize CLI demo")
    parser.add_argument("--location", default="Coimbatore", choices=config.LOCATIONS)
    parser.add_argument("--season", default="Kharif", choices=config.AG_SEASONS)
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--land", type=float, default=5.0, help="Total land in hectares")
    parser.add_argument("--budget", type=float, default=None, help="Optional budget cap (Rs)")
    parser.add_argument(
        "--preference",
        default="balanced",
        choices=["balanced", "max_yield", "min_cost", "min_water", "min_env_impact"],
    )
    parser.add_argument("--top", type=int, default=5, help="How many ranked plans to print")
    parser.add_argument("--pop-size", type=int, default=None)
    parser.add_argument("--n-gen", type=int, default=None)
    parser.add_argument(
        "--no-save", action="store_true",
        help="Skip persisting this run to results/ (saving is on by default).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    request = FarmPlanRequest(
        location=args.location,
        season=args.season,
        year=args.year,
        total_land_ha=args.land,
        budget_rs=args.budget,
        preference=args.preference,
        pop_size=args.pop_size,
        n_gen=args.n_gen,
        save_results=not args.no_save,
    )

    print(f"Running AgroOptimize for {args.location} / {args.season} "
          f"(land={args.land} ha, budget={args.budget}, preference={args.preference}) ...")
    response = generate_farm_plans(request)

    profile = response["region_profile"]
    fz = response["fuzzy_assessment"]
    meta = response["meta"]

    print("\n=== Region snapshot ===")
    print(f"Location/Year/Season : {profile['location']} / {profile['year']} / {profile['season']}")
    print(f"Soil                 : {profile['soil']['soil_type']}, pH {profile['soil']['avg_ph']}, "
          f"fertility index {profile['soil']['fertility_index']}/100")
    print(f"Rainfall             : {profile['rainfall']['avg_monthly_rainfall_mm']} mm/month avg, "
          f"deviation {profile['rainfall']['avg_deviation_percent']}%")
    print(f"Water storage        : {profile['water']['avg_storage_percent']}% "
          f"(groundwater: {profile['water']['groundwater_status']})")
    print(f"Candidate crops      : {', '.join(c['name'] for c in profile['candidate_crops'])}")

    print("\n=== Fuzzy uncertainty assessment ===")
    print(f"Yield confidence     : {fz['yield_confidence']} ({fz['soil_label']} soil, {fz['rainfall_label']} rainfall)")
    print(f"Irrigation risk      : {fz['irrigation_risk']} ({fz['water_label']} water storage)")

    print(f"\n=== NSGA-II run: pop={meta['pop_size']} gen={meta['n_gen']} "
          f"({meta['optimize_seconds']}s) -> {meta['n_pareto_solutions_found']} Pareto solutions ===")

    print(f"\nTop {min(args.top, len(response['plans']))} ranked plans (preference: {args.preference}):\n")
    header = f"{'Rank':<5}{'Crop mix':<45}{'Yield(t)':>10}{'Cost(Rs)':>12}{'Water(kL)':>12}{'EnvImpact':>11}"
    print(header)
    print("-" * len(header))
    for plan in response["plans"][: args.top]:
        mix = ", ".join(
            f"{name} {pct:.0f}%" for name, pct in zip(plan["crop_names"], plan["allocation_percent"]) if pct >= 1
        )
        print(
            f"{plan['rank']:<5}{mix[:44]:<45}{plan['yield_tonnes']:>10.1f}"
            f"{plan['cost_rs']:>12,.0f}{plan['water_liters']/1000:>12,.0f}{plan['env_impact_score']:>11.1f}"
        )
        print(f"      -> {plan['trade_off_summary']}")

    if response.get("convergence_history"):
        hv = response["convergence_history"]
        print(f"\nConvergence: hypervolume {hv[0]['hypervolume']} (gen 1) -> "
              f"{hv[-1]['hypervolume']} (gen {hv[-1]['generation']})")

    if response.get("saved_files"):
        sf = response["saved_files"]
        print(f"\n=== Saved to results/ (run_id: {sf['run_id']}) ===")
        print(f"Full JSON            : {sf['json_path']}")
        print(f"Ranked plans (CSV)   : {sf['plans_csv_path']}")
        if sf.get("convergence_csv_path"):
            print(f"Convergence (CSV)    : {sf['convergence_csv_path']}")
        if sf.get("convergence_plot_path"):
            print(f"Convergence (chart)  : {sf['convergence_plot_path']}")
    else:
        print("\n(Run not saved -- pass without --no-save to persist it to results/.)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
