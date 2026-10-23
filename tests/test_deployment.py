"""
Deployment configuration: settings read from the environment.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _config_value(expr: str, **env) -> str:
    """Evaluate `expr` on a freshly imported app.config with the given env."""
    full_env = {k: v for k, v in os.environ.items() if not k.startswith("AGROOPTIMIZE_")}
    full_env.update(env)
    out = subprocess.run([sys.executable, "-c", f"from app import config; print({expr})"],
                         cwd=PROJECT_ROOT, env=full_env, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_results_dir_defaults_to_project_results():
    assert _config_value("config.RESULTS_DIR") == str(PROJECT_ROOT / "results")


def test_results_dir_can_be_overridden(tmp_path):
    assert _config_value("config.RESULTS_DIR", AGROOPTIMIZE_RESULTS_DIR=str(tmp_path)) == str(tmp_path)


def test_empty_results_dir_variable_keeps_the_default():
    assert _config_value("config.RESULTS_DIR", AGROOPTIMIZE_RESULTS_DIR="") == str(PROJECT_ROOT / "results")


def test_results_dir_is_a_path():
    assert isinstance(config.RESULTS_DIR, Path)
