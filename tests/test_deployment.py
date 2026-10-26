"""
Deployment: settings read from the environment, serving the built
frontend from the API server, and response compression.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import config
from app.frontend import ASSET_CACHE, mount_frontend
from app.main import app as real_app

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


# ---------------------------------------------------------------------------
# Serving the built frontend (app/frontend.py)
# ---------------------------------------------------------------------------


INDEX_HTML = '<!doctype html><html><body><div id="root"></div><script src="/assets/index-abc123.js"></script></body></html>'


@pytest.fixture()
def dist(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(INDEX_HTML)
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log('app');")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("outside the build")
    return tmp_path


@pytest.fixture()
def site(dist):
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"pong": True}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    assert mount_frontend(app, dist)
    return TestClient(app)


def test_index_is_served_at_root(site):
    res = site.get("/")
    assert res.status_code == 200
    assert res.text == INDEX_HTML
    assert res.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path", ["/history", "/reports/2024", "/some/deep/link"])
def test_unknown_page_paths_fall_back_to_index(site, path):
    res = site.get(path)
    assert res.status_code == 200 and res.text == INDEX_HTML


def test_hashed_assets_are_served_with_long_cache(site):
    res = site.get("/assets/index-abc123.js")
    assert res.status_code == 200
    assert "javascript" in res.headers["content-type"]
    assert res.headers["cache-control"] == ASSET_CACHE


def test_missing_asset_is_a_404_not_the_index(site):
    assert site.get("/assets/missing.js").status_code == 404


def test_root_files_are_served(site):
    res = site.get("/favicon.svg")
    assert res.status_code == 200 and res.text == "<svg/>"


@pytest.mark.parametrize("path", ["/api/unknown", "/api", "/docs/extra", "/health/x", "/openapi.json/x"])
def test_api_and_docs_paths_never_return_the_index(site, path):
    res = site.get(path)
    assert res.status_code == 404
    assert res.json() == {"detail": "Not Found"}


def test_api_routes_still_win(site):
    assert site.get("/api/ping").json() == {"pong": True}
    assert site.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"])
def test_files_outside_the_build_are_not_served(site, path):
    res = site.get(path)
    assert "outside the build" not in res.text


@pytest.mark.parametrize("path", ["/", "/history", "/assets/index-abc123.js"])
def test_head_requests_are_answered(site, path):
    assert site.head(path).status_code == 200


def test_head_on_the_real_health_check():
    assert TestClient(real_app).head("/health").status_code == 200


def test_nothing_is_mounted_without_a_build(tmp_path):
    app = FastAPI()
    assert mount_frontend(app, tmp_path) is False
    assert TestClient(app).get("/").status_code == 404


# ---------------------------------------------------------------------------
# The real application
# ---------------------------------------------------------------------------


def test_unknown_api_path_is_json_404_on_the_real_app():
    res = TestClient(real_app).get("/api/does-not-exist")
    assert res.status_code == 404 and res.json() == {"detail": "Not Found"}


def test_large_responses_are_gzipped_without_changing_content():
    client = TestClient(real_app)
    plain = client.get("/api/district-intelligence/salem", headers={"Accept-Encoding": "identity"})
    zipped = client.get("/api/district-intelligence/salem", headers={"Accept-Encoding": "gzip"})
    assert zipped.headers.get("content-encoding") == "gzip"
    assert "content-encoding" not in plain.headers
    assert zipped.json() == plain.json()


def test_small_responses_are_not_compressed():
    res = TestClient(real_app).get("/health", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in res.headers
