"""Tests for Jinja SQL Templating."""

from app.query.jinja import render_template_sql


def test_jinja_basic_parameters():
    raw_sql = "SELECT * FROM sales WHERE region = '{{ params.region }}' AND amount > {{ params.min_amount }}"
    rendered = render_template_sql(
        raw_sql,
        parameters={"params": {"region": "EMEA", "min_amount": 100}},
    )
    assert "region = 'EMEA'" in rendered
    assert "amount > 100" in rendered


def test_jinja_passthrough():
    raw_sql = "SELECT * FROM sales WHERE id = 10"
    rendered = render_template_sql(raw_sql, {})
    assert rendered == raw_sql
