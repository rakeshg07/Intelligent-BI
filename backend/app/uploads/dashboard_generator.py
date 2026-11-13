"""Automatic Dynamic Dashboard & Chart Generator for Uploaded Files."""

import re
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chart, Dashboard, DashboardChart, Dataset, DatasetColumn, User

NUMERIC_TYPES = ("INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC")
ID_LIKE_NAMES = {"id", "no", "sl_no", "sl_number", "row_id", "index"}
HIGH_CARDINALITY_HINTS = (
    "email",
    "mobile",
    "phone",
    "first_name",
    "last_name",
    "full_name",
    "address",
    "url",
    "uuid",
)


def _is_numeric_col(col: DatasetColumn) -> bool:
    return any(t in (col.data_type or "").upper() for t in NUMERIC_TYPES)


def _rank_dimension_cols(cols: list[DatasetColumn]) -> list[DatasetColumn]:
    """Order dimension columns so low/medium-cardinality grouping columns come first."""
    dims = [c for c in cols if c.is_dimension and not c.is_datetime]

    def score(c: DatasetColumn) -> int:
        n = c.name.lower()
        if any(h in n for h in HIGH_CARDINALITY_HINTS) or n in ID_LIKE_NAMES:
            return 2
        return 0

    return sorted(dims, key=score)


def _rank_numeric_cols(cols: list[DatasetColumn]) -> list[DatasetColumn]:
    """Order numeric columns so meaningful measures come before row IDs."""
    nums = [c for c in cols if _is_numeric_col(c)]
    return sorted(
        nums,
        key=lambda c: 1 if c.name.lower() in ID_LIKE_NAMES or c.name.lower().endswith("_id") else 0,
    )


async def generate_dashboard_for_dataset(
    session: AsyncSession,
    dataset: Dataset,
    columns: list[DatasetColumn],
    user: User | None,
    filename: str = "",
) -> Dashboard:
    """Create (or refresh) a dynamic Dashboard + Charts tailored to the dataset's schema."""
    table_slug = re.sub(
        r"[^a-zA-Z0-9_-]+", "-", (dataset.table_name or dataset.name).lower()
    ).strip("-")
    slug = f"{table_slug}-overview"

    # Remove existing auto-generated dashboard with the same slug so re-uploads stay fresh
    existing_stmt = select(Dashboard).where(Dashboard.slug == slug, Dashboard.deleted_at.is_(None))
    existing_res = await session.execute(existing_stmt)
    existing_dash = existing_res.scalar_one_or_none()
    if existing_dash:
        old_chart_ids = [dc.chart_id for dc in (existing_dash.charts or [])]
        await session.delete(existing_dash)
        await session.flush()
        if old_chart_ids:
            await session.execute(delete(Chart).where(Chart.id.in_(old_chart_ids)))
            await session.flush()

    dt_cols = [c for c in columns if c.is_datetime]
    dim_cols = _rank_dimension_cols(columns)
    num_cols = _rank_numeric_cols(columns)

    count_metric = {"name": "count", "label": "Total Rows", "expression": "COUNT(*)"}
    primary_num = num_cols[0] if num_cols else None
    secondary_num = num_cols[1] if len(num_cols) > 1 else None

    chart_specs: list[dict[str, Any]] = []

    # 1. Top KPI Row: Total Records
    chart_specs.append(
        {
            "title": f"Total {dataset.name} Records",
            "viz_type": "big_number",
            "params": {
                "dimensions": [],
                "metrics": [count_metric],
                "row_limit": 1,
                "options": {},
            },
            "position": {"x": 0, "y": 0, "w": 4 if primary_num else 12, "h": 3},
        }
    )

    if primary_num:
        p_label = primary_num.verbose_name or primary_num.name
        chart_specs.append(
            {
                "title": f"Average {p_label}",
                "viz_type": "big_number",
                "params": {
                    "dimensions": [],
                    "metrics": [
                        {
                            "name": f"avg_{primary_num.name}",
                            "label": f"AVG({primary_num.name})",
                            "expression": f"AVG({primary_num.name})",
                        }
                    ],
                    "row_limit": 1,
                    "options": {},
                },
                "position": {"x": 4, "y": 0, "w": 4, "h": 3},
            }
        )

        target_num = secondary_num or primary_num
        t_label = target_num.verbose_name or target_num.name
        agg_fn = "AVG" if secondary_num else "SUM"
        chart_specs.append(
            {
                "title": f"{'Average' if agg_fn == 'AVG' else 'Total'} {t_label}",
                "viz_type": "big_number",
                "params": {
                    "dimensions": [],
                    "metrics": [
                        {
                            "name": f"{agg_fn.lower()}_{target_num.name}",
                            "label": f"{agg_fn}({target_num.name})",
                            "expression": f"{agg_fn}({target_num.name})",
                        }
                    ],
                    "row_limit": 1,
                    "options": {},
                },
                "position": {"x": 8, "y": 0, "w": 4, "h": 3},
            }
        )

    current_y = 3

    # 2. Categorical Bar + Pie Charts if dimension columns exist
    if dim_cols:
        d1 = dim_cols[0]
        d1_label = d1.verbose_name or d1.name
        bar_metric = (
            {
                "name": f"avg_{primary_num.name}",
                "label": f"AVG({primary_num.name})",
                "expression": f"AVG({primary_num.name})",
            }
            if primary_num and not dt_cols
            else count_metric
        )
        chart_specs.append(
            {
                "title": f"{dataset.name} by {d1_label}",
                "viz_type": "bar",
                "params": {
                    "dimensions": [d1.name],
                    "metrics": [count_metric]
                    if bar_metric == count_metric
                    else [count_metric, bar_metric],
                    "row_limit": 25,
                    "options": {},
                },
                "position": {"x": 0, "y": current_y, "w": 6, "h": 4},
            }
        )

        d2 = dim_cols[1] if len(dim_cols) > 1 else d1
        d2_label = d2.verbose_name or d2.name
        chart_specs.append(
            {
                "title": f"Distribution by {d2_label}",
                "viz_type": "pie",
                "params": {
                    "dimensions": [d2.name],
                    "metrics": [count_metric],
                    "row_limit": 15,
                    "options": {"isDonut": True},
                },
                "position": {"x": 6, "y": current_y, "w": 6, "h": 4},
            }
        )
        current_y += 4

    # 3. Time Series Line Chart if datetime column exists
    if dt_cols:
        dt = dt_cols[0]
        dt_label = dt.verbose_name or dt.name
        ts_metrics = (
            [
                {"name": f"avg_{c.name}", "label": f"AVG({c.name})", "expression": f"AVG({c.name})"}
                for c in num_cols[:2]
            ]
            if num_cols
            else [count_metric]
        )
        chart_specs.append(
            {
                "title": f"{dataset.name} Trend Over {dt_label}",
                "viz_type": "line",
                "params": {
                    "dimensions": [],
                    "time_column": dt.name,
                    "time_grain": "month",
                    "metrics": ts_metrics,
                    "row_limit": 200,
                    "options": {"smooth": True},
                },
                "position": {"x": 0, "y": current_y, "w": 12, "h": 4},
            }
        )
        current_y += 4

    # 4. Summary Table
    table_dims = [dim_cols[0].name] if dim_cols else []
    table_time = dt_cols[0].name if (not dim_cols and dt_cols) else None
    table_metrics = [count_metric] + [
        {"name": f"avg_{c.name}", "label": f"AVG({c.name})", "expression": f"AVG({c.name})"}
        for c in num_cols[:2]
    ]
    chart_specs.append(
        {
            "title": f"{dataset.name} Summary Table",
            "viz_type": "table",
            "params": {
                "dimensions": table_dims,
                "time_column": table_time,
                "time_grain": "month" if table_time else None,
                "metrics": table_metrics,
                "row_limit": 50,
                "options": {},
            },
            "position": {"x": 0, "y": current_y, "w": 12, "h": 4},
        }
    )

    owner_list = [user.email] if user else []
    created_by = user.id if user else None

    dashboard = Dashboard(
        title=f"{dataset.name} Dashboard",
        description=f"Auto-generated dynamic dashboard from '{filename or dataset.table_name}'",
        slug=slug,
        is_published=True,
        layout={"auto_generated": True},
        owners=owner_list,
        created_by_id=created_by,
    )
    session.add(dashboard)
    await session.flush()

    for spec in chart_specs:
        chart = Chart(
            title=spec["title"],
            description=f"Auto-generated from {dataset.name}",
            dataset_id=dataset.id,
            viz_type=spec["viz_type"],
            params=spec["params"],
            query_context={},
            owners=owner_list,
            created_by_id=created_by,
        )
        session.add(chart)
        await session.flush()

        session.add(
            DashboardChart(
                dashboard_id=dashboard.id,
                chart_id=chart.id,
                position=spec["position"],
            )
        )

    return dashboard
