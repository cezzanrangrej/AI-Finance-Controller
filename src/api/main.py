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

from src.api.routes import audit, evaluations, exceptions, metrics, runs, transactions
from src.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialises database tables on application startup."""
    init_db()
    yield


app = FastAPI(
    title="AI Finance Controller API",
    description="Multi-source financial reconciliation and AI exception investigation platform API.",
    version="3.0.0",
    lifespan=lifespan,
)


# Enable CORS for React frontend development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API route modules
app.include_router(runs.router)
app.include_router(metrics.router)
app.include_router(exceptions.router)
app.include_router(transactions.router)
app.include_router(audit.router)
app.include_router(evaluations.router)



@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "AI Finance Controller API", "version": "3.0.0"}



# Static frontend files mounting if built
frontend_dist = os.path.join(_project_root, "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=True)
