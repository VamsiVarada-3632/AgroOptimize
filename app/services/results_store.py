"""
Persists every optimisation run to disk under results/, so a run has a
record independent of the API response it produced (which otherwise only
exists for the lifetime of one HTTP request / CLI invocation).

Each run writes up to four files, all sharing one `run_id`
(`<location>_<season>_<year>_<UTC timestamp>`):

    results/<run_id>.json               full response + convergence history
    results/<run_id>_plans.csv          flattened ranked-plan table (Excel/Sheets-friendly)
    results/<run_id>_convergence.csv    per-generation convergence stats
    results/<run_id>_convergence.png    hypervolume + best-yield/cost convergence chart
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from app import config

# A run_id is built by make_run_id() from slugified parts, so it only ever
# contains [a-z0-9-] segments joined by "_". Anything else coming in over
# GET /api/results/{run_id} can't be a real run -- rejecting it up front
# means a crafted id can never be turned into a path outside out_dir.
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def is_valid_run_id(run_id: str) -> bool:
    return bool(_RUN_ID_PATTERN.fullmatch(str(run_id)))


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", str(text)).strip("-").lower()


def make_run_id(location: str, season: str, year: int) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{_slugify(location)}_{_slugify(season)}_{year}_{ts}"


@dataclass
class SavedRunFiles:
    run_id: str
    json_path: str
    plans_csv_path: str
    convergence_csv_path: Optional[str] = None
    convergence_plot_path: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def save_run_results(
    response: dict,
    convergence_history: List[dict],
    out_dir: Path = config.RESULTS_DIR,
    client_id: Optional[str] = None,
) -> SavedRunFiles:
    """Write one run's full results to `out_dir`. Safe to call with an
    empty `convergence_history` (e.g. when the run used
    track_history=False) -- the convergence CSV/plot are simply skipped.

    `client_id` (optional) is the per-browser id the request came in with
    -- stored on the record so GET /api/history/{location} can show this
    run back only to the client that generated it. Older records saved
    before this existed simply have no client_id and so won't match any
    real requester going forward.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    profile = response["region_profile"]
    run_id = _reserve_run_id(out_dir, make_run_id(profile["location"], profile["season"], profile["year"]))

    full_record = dict(response)
    full_record["run_id"] = run_id
    full_record["saved_at"] = datetime.now(timezone.utc).isoformat()
    full_record["client_id"] = client_id
    full_record["convergence_history"] = convergence_history

    json_path = out_dir / f"{run_id}.json"
    _atomic_write_text(json_path, json.dumps(full_record, indent=2))

    plans_csv_path = out_dir / f"{run_id}_plans.csv"
    plans_df = pd.DataFrame(response["plans"])
    for col in plans_df.columns:
        if plans_df[col].apply(lambda v: isinstance(v, (list, dict))).any():
            plans_df[col] = plans_df[col].apply(json.dumps)
    plans_df.to_csv(plans_csv_path, index=False)

    convergence_csv_path = None
    convergence_plot_path = None
    if convergence_history:
        conv_df = pd.DataFrame(convergence_history)
        convergence_csv_path = out_dir / f"{run_id}_convergence.csv"
        conv_df.to_csv(convergence_csv_path, index=False)
        convergence_plot_path = _plot_convergence(
            conv_df, out_dir / f"{run_id}_convergence.png", run_id, profile
        )

    return SavedRunFiles(
        run_id=run_id,
        json_path=str(json_path),
        plans_csv_path=str(plans_csv_path),
        convergence_csv_path=str(convergence_csv_path) if convergence_csv_path else None,
        convergence_plot_path=str(convergence_plot_path) if convergence_plot_path else None,
    )


def _reserve_run_id(out_dir: Path, base_id: str) -> str:
    """make_run_id() has one-second resolution, so two saves of the same
    location/season/year in the same second would share an id and the
    second would overwrite the first run's files. Claim the JSON filename
    with an exclusive create (atomic on POSIX) and fall back to -2, -3, ...
    suffixes on collision. The normal-case id format is unchanged."""
    for attempt in range(1, 1000):
        run_id = base_id if attempt == 1 else f"{base_id}-{attempt}"
        try:
            with open(out_dir / f"{run_id}.json", "x"):
                return run_id
        except FileExistsError:
            continue
    raise RuntimeError(f"Could not allocate a unique run id for {base_id}")


def _atomic_write_text(path: Path, text: str) -> None:
    """Write via a temp file + os.replace so a crash or a concurrent
    reader (list_saved_runs) never sees a half-written JSON record."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


def _plot_convergence(conv_df: pd.DataFrame, out_path: Path, run_id: str, profile: dict) -> Path:
    import matplotlib

    matplotlib.use("Agg")  # headless -- no display server in the sandbox / on a server
    import matplotlib.pyplot as plt

    fig, (ax_hv, ax_obj) = plt.subplots(1, 2, figsize=(11, 4.2))

    ax_hv.plot(conv_df["generation"], conv_df["hypervolume"], color="#2a7f3f")
    ax_hv.set_title("Hypervolume (normalised) vs. generation")
    ax_hv.set_xlabel("Generation")
    ax_hv.set_ylabel("Hypervolume")
    ax_hv.grid(alpha=0.3)

    ax_obj.plot(conv_df["generation"], conv_df["best_yield_tonnes"], color="#2a7f3f", label="best yield (t)")
    ax_obj.set_xlabel("Generation")
    ax_obj.set_ylabel("Best yield (t)", color="#2a7f3f")
    ax_obj.tick_params(axis="y", labelcolor="#2a7f3f")
    ax_obj.grid(alpha=0.3)

    ax_cost = ax_obj.twinx()
    ax_cost.plot(conv_df["generation"], conv_df["best_cost_rs"], color="#b5651d", label="best cost (Rs)")
    ax_cost.set_ylabel("Best cost (Rs)", color="#b5651d")
    ax_cost.tick_params(axis="y", labelcolor="#b5651d")
    ax_obj.set_title("Best yield & cost vs. generation")

    fig.suptitle(
        f"NSGA-II convergence -- {profile['location']} / {profile['season']} / {profile['year']}  ({run_id})",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


# Per-file summary cache keyed by (mtime_ns, size). Every dashboard/history
# request calls list_saved_runs(), and each saved record embeds a
# 200-generation convergence history, so re-parsing every JSON on every
# request grows linearly with the number of saved runs. A file is only
# re-parsed when it actually changes on disk.
_SUMMARY_CACHE: Dict[Tuple[str, str], Tuple[Tuple[int, int], dict]] = {}
_SUMMARY_CACHE_LOCK = threading.Lock()


def _run_summary(json_path: Path, record: dict) -> dict:
    return {
        "run_id": record.get("run_id", json_path.stem),
        "location": record["region_profile"]["location"],
        "season": record["region_profile"]["season"],
        "year": record["region_profile"]["year"],
        "preference": record.get("meta", {}).get("preference"),
        # Label of the weights that ranked the run (profile or preference);
        # None for runs saved before ranking profiles existed.
        "ranking": (record.get("meta", {}).get("topsis") or {}).get("label"),
        "saved_at": record.get("saved_at"),
        "n_plans": len(record.get("plans", [])),
        "client_id": record.get("client_id"),
    }


def _summarise(json_path: Path, builder: Callable[[Path, dict], dict] = _run_summary) -> Optional[dict]:
    try:
        stat = json_path.stat()
    except OSError:
        return None
    key = (str(json_path), builder.__name__)
    stamp = (stat.st_mtime_ns, stat.st_size)
    with _SUMMARY_CACHE_LOCK:
        cached = _SUMMARY_CACHE.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    try:
        summary = builder(json_path, json.loads(json_path.read_text()))
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        return None
    with _SUMMARY_CACHE_LOCK:
        _SUMMARY_CACHE[key] = (stamp, summary)
    return summary


def list_saved_runs(out_dir: Path = config.RESULTS_DIR) -> List[dict]:
    out_dir = Path(out_dir)
    if not out_dir.exists():
        return []
    runs = []
    for json_path in sorted(out_dir.glob("*.json"), reverse=True):
        summary = _summarise(json_path)
        if summary is not None:
            runs.append(dict(summary))
    return runs


def load_run(run_id: str, out_dir: Path = config.RESULTS_DIR) -> Optional[dict]:
    if not is_valid_run_id(run_id):
        return None
    out_dir = Path(out_dir)
    path = out_dir / f"{run_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Saved scenario simulations (results/simulations/<simulation_id>.json)
# ---------------------------------------------------------------------------

SIMULATIONS_DIR_NAME = "simulations"


def _simulations_dir(out_dir: Optional[Path]) -> Path:
    return Path(out_dir if out_dir is not None else config.RESULTS_DIR) / SIMULATIONS_DIR_NAME


def make_simulation_id(location: str) -> str:
    """Timestamped and with a random suffix, so ids are not guessable."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"sim_{_slugify(location)}_{ts}_{secrets.token_hex(4)}"


def _simulation_summary(json_path: Path, record: dict) -> dict:
    return {
        "simulation_id": record["simulation_id"],
        "name": record.get("name"),
        "saved_at": record.get("saved_at"),
        "client_id": record.get("client_id"),
        "location": record["inputs"]["base"]["location"],
        "season": record["inputs"]["base"]["season"],
        "year": record["result"]["summary"].get("year"),
        "changes": [c["id"] for c in record["inputs"].get("changes", [])],
        "headline": (record["result"].get("impact") or {}).get("headline", {}),
    }


def save_simulation(record: dict, client_id: str, name: Optional[str], out_dir: Optional[Path] = None) -> dict:
    """Persist a simulation result for one browser. Returns the stored record."""
    folder = _simulations_dir(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    sim_id = make_simulation_id(record["inputs"]["base"]["location"])
    stored = {
        "simulation_id": sim_id,
        "name": name or f"{record['inputs']['base']['location']} {record['inputs']['base']['season']} scenario",
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "client_id": client_id,
        "inputs": record["inputs"],
        "result": {k: v for k, v in record.items() if k != "token"},
    }
    _atomic_write_text(folder / f"{sim_id}.json", json.dumps(stored, indent=1))
    return stored


def list_simulations(client_id: str, out_dir: Optional[Path] = None) -> List[dict]:
    folder = _simulations_dir(out_dir)
    if not client_id or not folder.exists():
        return []
    out = []
    for path in folder.glob("*.json"):
        summary = _summarise(path, _simulation_summary)
        if summary is not None and summary.get("client_id") == client_id:
            out.append({k: v for k, v in summary.items() if k != "client_id"})
    return sorted(out, key=lambda r: r.get("saved_at") or "", reverse=True)


_SIMULATION_ID_PATTERN = re.compile(r"sim_[a-z0-9-]+_\d{8}T\d{6}Z_[0-9a-f]{8}")


def load_simulation(simulation_id: str, client_id: str, out_dir: Optional[Path] = None) -> Optional[dict]:
    """The stored record, or None if it does not exist or belongs to another browser."""
    if not client_id or not _SIMULATION_ID_PATTERN.fullmatch(str(simulation_id)):
        return None
    path = _simulations_dir(out_dir) / f"{simulation_id}.json"
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return record if record.get("client_id") == client_id else None


def delete_simulation(simulation_id: str, client_id: str, out_dir: Optional[Path] = None) -> bool:
    if load_simulation(simulation_id, client_id, out_dir) is None:
        return False
    (_simulations_dir(out_dir) / f"{simulation_id}.json").unlink()
    return True
