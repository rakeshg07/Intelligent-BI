"""Dashboards API Endpoints."""

import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import get_db_session, require_permission
from app.core.errors import NotFoundError
from app.db.models import Dashboard, DashboardChart, User
from app.schemas.dashboard import (
    DashboardCreate,
    DashboardOut,
    DashboardUpdate,
)

router = APIRouter(prefix="/dashboards", tags=["Dashboards"])


def generate_slug(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug or f"dashboard-{uuid.uuid4().hex[:8]}"


@router.get("/", response_model=list[DashboardOut])
async def list_dashboards(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("dashboards:read")),
) -> Any:
    """List all dashboards."""
    stmt = (
        select(Dashboard)
        .options(selectinload(Dashboard.charts), selectinload(Dashboard.filters))
        .where(Dashboard.deleted_at.is_(None))
        .order_by(Dashboard.created_at.desc())
    )
    result = await session.execute(stmt)
    dashboards = result.scalars().all()

    out = []
    for d in dashboards:
        out.append(
            DashboardOut(
                id=d.id,
                title=d.title,
                description=d.description,
                slug=d.slug,
                is_published=d.is_published,
                layout=d.layout or {},
                owners=d.owners or [],
                created_by_id=d.created_by_id,
                charts=[
                    {"id": str(c.id), "chart_id": str(c.chart_id), "position": c.position}
                    for c in d.charts
                ],
                filters=[
                    {
                        "id": str(f.id),
                        "name": f.name,
                        "filter_type": f.filter_type,
                        "target_charts": f.target_charts or [],
                        "default_value": f.default_value,
                    }
                    for f in d.filters
                ],
                created_at=d.created_at.isoformat() if d.created_at else None,
                updated_at=d.updated_at.isoformat() if d.updated_at else None,
            )
        )
    return out


@router.post("/", response_model=DashboardOut, status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    payload: DashboardCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("dashboards:write")),
) -> Any:
    """Create a new dashboard."""
    slug = payload.slug or generate_slug(payload.title)

    # Check unique slug
    existing = await session.execute(
        select(Dashboard).where(Dashboard.slug == slug, Dashboard.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none():
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    dashboard = Dashboard(
        title=payload.title,
        description=payload.description,
        slug=slug,
        is_published=payload.is_published,
        layout=payload.layout or {},
        created_by_id=current_user.id,
        owners=[current_user.email],
    )
    session.add(dashboard)
    await session.flush()

    # Place initial charts if given
    for idx, chart_id in enumerate(payload.chart_ids):
        placement = DashboardChart(
            dashboard_id=dashboard.id,
            chart_id=chart_id,
            position={"x": (idx % 2) * 6, "y": (idx // 2) * 4, "w": 6, "h": 4},
        )
        session.add(placement)

    await session.commit()
    await session.refresh(dashboard, ["charts", "filters"])

    return DashboardOut(
        id=dashboard.id,
        title=dashboard.title,
        description=dashboard.description,
        slug=dashboard.slug,
        is_published=dashboard.is_published,
        layout=dashboard.layout or {},
        owners=dashboard.owners or [],
        created_by_id=dashboard.created_by_id,
        charts=[
            {"id": str(c.id), "chart_id": str(c.chart_id), "position": c.position}
            for c in dashboard.charts
        ],
        filters=[],
        created_at=dashboard.created_at.isoformat() if dashboard.created_at else None,
        updated_at=dashboard.updated_at.isoformat() if dashboard.updated_at else None,
    )


@router.get("/{id}", response_model=DashboardOut)
async def get_dashboard(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("dashboards:read")),
) -> Any:
    """Get dashboard with placed charts and native filters."""
    stmt = (
        select(Dashboard)
        .options(selectinload(Dashboard.charts), selectinload(Dashboard.filters))
        .where(Dashboard.id == id, Dashboard.deleted_at.is_(None))
    )
    result = await session.execute(stmt)
    dashboard = result.scalar_one_or_none()
    if not dashboard:
        raise NotFoundError("Dashboard not found.")

    return DashboardOut(
        id=dashboard.id,
        title=dashboard.title,
        description=dashboard.description,
        slug=dashboard.slug,
        is_published=dashboard.is_published,
        layout=dashboard.layout or {},
        owners=dashboard.owners or [],
        created_by_id=dashboard.created_by_id,
        charts=[
            {"id": str(c.id), "chart_id": str(c.chart_id), "position": c.position}
            for c in dashboard.charts
        ],
        filters=[
            {
                "id": str(f.id),
                "name": f.name,
                "filter_type": f.filter_type,
                "target_charts": f.target_charts or [],
                "default_value": f.default_value,
            }
            for f in dashboard.filters
        ],
        created_at=dashboard.created_at.isoformat() if dashboard.created_at else None,
        updated_at=dashboard.updated_at.isoformat() if dashboard.updated_at else None,
    )


@router.put("/{id}", response_model=DashboardOut)
async def update_dashboard(
    id: uuid.UUID,
    payload: DashboardUpdate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("dashboards:write")),
) -> Any:
    """Update dashboard configuration, layout grid, and filters."""
    stmt = (
        select(Dashboard)
        .options(selectinload(Dashboard.charts), selectinload(Dashboard.filters))
        .where(Dashboard.id == id, Dashboard.deleted_at.is_(None))
    )
    result = await session.execute(stmt)
    dashboard = result.scalar_one_or_none()
    if not dashboard:
        raise NotFoundError("Dashboard not found.")

    if payload.title is not None:
        dashboard.title = payload.title
    if payload.description is not None:
        dashboard.description = payload.description
    if payload.is_published is not None:
        dashboard.is_published = payload.is_published
    if payload.layout is not None:
        dashboard.layout = payload.layout

    if payload.chart_ids is not None:
        # Replace charts
        for c in list(dashboard.charts):
            await session.delete(c)
        await session.flush()

        for idx, chart_id in enumerate(payload.chart_ids):
            # Check layout for coordinates or fallback
            layout_items = payload.layout.get("items", []) if payload.layout else []
            pos = next((item for item in layout_items if item.get("i") == str(chart_id)), None)
            if not pos:
                pos = {"x": (idx % 2) * 6, "y": (idx // 2) * 4, "w": 6, "h": 4}

            placement = DashboardChart(
                dashboard_id=dashboard.id,
                chart_id=chart_id,
                position=pos,
            )
            session.add(placement)

    await session.commit()
    await session.refresh(dashboard, ["charts", "filters"])

    return DashboardOut(
        id=dashboard.id,
        title=dashboard.title,
        description=dashboard.description,
        slug=dashboard.slug,
        is_published=dashboard.is_published,
        layout=dashboard.layout or {},
        owners=dashboard.owners or [],
        created_by_id=dashboard.created_by_id,
        charts=[
            {"id": str(c.id), "chart_id": str(c.chart_id), "position": c.position}
            for c in dashboard.charts
        ],
        filters=[
            {
                "id": str(f.id),
                "name": f.name,
                "filter_type": f.filter_type,
                "target_charts": f.target_charts or [],
                "default_value": f.default_value,
            }
            for f in dashboard.filters
        ],
        created_at=dashboard.created_at.isoformat() if dashboard.created_at else None,
        updated_at=dashboard.updated_at.isoformat() if dashboard.updated_at else None,
    )


@router.delete("/{id}")
async def delete_dashboard(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_permission("dashboards:write")),
) -> dict[str, str]:
    """Delete a dashboard."""
    stmt = select(Dashboard).where(Dashboard.id == id, Dashboard.deleted_at.is_(None))
    result = await session.execute(stmt)
    dashboard = result.scalar_one_or_none()
    if not dashboard:
        raise NotFoundError("Dashboard not found.")

    await session.delete(dashboard)
    await session.commit()
    return {"message": "Dashboard deleted successfully."}
