"""Root API v1 Router aggregating all endpoint routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    ai,
    auth,
    charts,
    dashboards,
    databases,
    datasets,
    health,
    sqllab,
    uploads,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(databases.router)
api_router.include_router(datasets.router)
api_router.include_router(charts.router)
api_router.include_router(dashboards.router)
api_router.include_router(sqllab.router)
api_router.include_router(uploads.router)
api_router.include_router(ai.router)
api_router.include_router(admin.router)
