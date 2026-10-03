"""API router composition."""

from fastapi import APIRouter

from app.api.routes import anomalies, contributors, dashboard, evidence_bundles, health, metrics

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(metrics.router)
api_router.include_router(anomalies.router)
api_router.include_router(contributors.router)
api_router.include_router(dashboard.router)
api_router.include_router(evidence_bundles.router)
