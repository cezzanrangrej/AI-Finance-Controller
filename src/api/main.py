"""
Main FastAPI application entry point for AI Finance Controller - Phase 3.

Provides REST API endpoints for batch execution runs, metrics, exceptions,
transaction details, audit trails, and dashboard integration.
"""

from contextlib import asynccontextmanager
import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Ensure project root on path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import src.config  # Loads .env variables

from src.api.routes import audit, evaluations, exceptions, metrics, normalizer, runs, transactions
from src.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialises database tables on application startup."""
    init_db()
    yield


app = FastAPI(
    title="ReconPilot API",
    description="Multi-source financial reconciliation and AI exception investigation platform API.",
    version="3.0.0",
    lifespan=lifespan,
)


# CORS for the React dev server.
#
# `allow_origins=["*"]` together with `allow_credentials=True` is invalid per the
# CORS spec -- a wildcard Access-Control-Allow-Origin cannot be combined with
# credentials -- and would let any site on the internet drive this API from a
# logged-in browser. Origins are therefore explicit, and credentials are only
# enabled when a concrete allow-list is configured.
_default_dev_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
_configured_origins = [
    o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()
]
_allow_origins = _configured_origins or _default_dev_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=bool(_configured_origins),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Mount API route modules
app.include_router(runs.router)
app.include_router(metrics.router)
app.include_router(exceptions.router)
app.include_router(transactions.router)
app.include_router(audit.router)
app.include_router(evaluations.router)
app.include_router(normalizer.router)

# Direct dataset operation aliases
app.add_api_route("/api/validate", runs.validate_csv_dataset, methods=["POST"])
app.add_api_route("/api/validate/", runs.validate_csv_dataset, methods=["POST"])
app.add_api_route("/api/upload", runs.create_run_from_upload, methods=["POST"], response_model=runs.RunSummaryResponse, status_code=201)
app.add_api_route("/api/upload/", runs.create_run_from_upload, methods=["POST"], response_model=runs.RunSummaryResponse, status_code=201)


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "ReconPilot API", "version": "3.0.0"}




# Static frontend files mounting if built
frontend_dist = os.path.join(_project_root, "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=True)
