"""Unit tests for Dashboard Schemas, Slug Generation, and Placement logic."""

import uuid

from app.api.v1.endpoints.dashboards import generate_slug
from app.schemas.dashboard import DashboardCreate, DashboardFilterSchema, DashboardUpdate


def test_generate_slug_clean():
    slug = generate_slug("Executive Sales Overview")
    assert slug == "executive-sales-overview"

    slug_special = generate_slug("Q3 Sales & Marketing (2025)!")
    assert "q3-sales-marketing-2025" in slug_special


def test_dashboard_create_schema():
    chart_id = uuid.uuid4()
    payload = DashboardCreate(
        title="Executive Performance",
        description="Key KPIs",
        chart_ids=[chart_id],
        layout={"columns": 12},
    )
    assert payload.title == "Executive Performance"
    assert len(payload.chart_ids) == 1
    assert payload.chart_ids[0] == chart_id
    assert payload.layout["columns"] == 12


def test_dashboard_update_and_filter_schema():
    filt = DashboardFilterSchema(
        name="region",
        filter_type="value_select",
        target_charts=["chart-1", "chart-2"],
        default_value="EMEA",
    )
    assert filt.name == "region"
    assert filt.default_value == "EMEA"

    update_payload = DashboardUpdate(
        title="Updated Dashboard Title",
        is_published=True,
        filters=[filt],
    )
    assert update_payload.title == "Updated Dashboard Title"
    assert update_payload.is_published is True
    assert len(update_payload.filters) == 1
