"""API router composition."""

from fastapi import APIRouter

from app.api.routes import (
    actions,
    anomalies,
    briefs,
    contributors,
    dashboard,
    evaluations,
    evidence,
    evidence_bundles,
    health,
    metrics,
    system,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(metrics.router)
api_router.include_router(anomalies.router)
api_router.include_router(contributors.router)
api_router.include_router(dashboard.router)
api_router.include_router(evidence_bundles.router)
api_router.include_router(briefs.router)
api_router.include_router(evidence.router)
api_router.include_router(actions.router)
api_router.include_router(evaluations.router)
api_router.include_router(system.router)
