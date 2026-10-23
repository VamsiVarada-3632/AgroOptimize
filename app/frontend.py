"""
Serves the built React frontend (frontend/dist) from the API server, so a
single deployment hosts both and the browser calls the API on the same
origin (no CORS, no API URL to configure).

Nothing is mounted when the build is missing, e.g. in local development
where the frontend runs on the Vite dev server instead.

* /assets/*   hashed build files, cached for a year (their names change on
              every build)
* /<file>     other files in dist/ (favicon.svg, icons.svg)
* anything    else that is not an API, docs or health path returns
              index.html, so reloading or deep-linking a page works
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config

FRONTEND_DIST = Path(os.environ.get("AGROOPTIMIZE_FRONTEND_DIST") or config.PROJECT_ROOT / "frontend" / "dist")

# Paths owned by the API; an unknown one must stay a JSON 404, never the SPA.
RESERVED_PATHS = ("api", "docs", "redoc", "openapi.json", "health")

ASSET_CACHE = "public, max-age=31536000, immutable"
PAGE_CACHE = "no-cache"


class _CachedStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = ASSET_CACHE
        return response


def _is_reserved(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in RESERVED_PATHS)


def mount_frontend(app: FastAPI, dist: Path = FRONTEND_DIST) -> bool:
    """Add the frontend routes to `app` (after every API route). Returns
    False, and adds nothing, when `dist` has no index.html."""
    dist = Path(dist).resolve()
    index = dist / "index.html"
    if not index.is_file():
        return False

    if (dist / "assets").is_dir():
        app.mount("/assets", _CachedStaticFiles(directory=dist / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend(full_path: str):
        if _is_reserved(full_path):
            raise HTTPException(status_code=404, detail="Not Found")
        if full_path:
            candidate = (dist / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(dist):
                return FileResponse(candidate, headers={"Cache-Control": PAGE_CACHE})
        return FileResponse(index, headers={"Cache-Control": PAGE_CACHE})

    return True
