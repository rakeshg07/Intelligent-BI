"""Unit tests for Grounding & Anti-Hallucination Guardrail (ADR-004 & Phase 4)."""

from app.ai.guardrails.grounding import GroundingGuardrail, extract_numbers_from_text


def test_extract_numbers_from_text():
    sample_text = (
        "Total revenue was $1,250,500.50 with a profit margin of 24.5%. Total orders: 450."
    )
    extracted = extract_numbers_from_text(sample_text)
    tokens = [t[0] for t in extracted]
    vals = [t[1] for t in extracted]

    assert "$1,250,500.50" in tokens
    assert "24.5%" in tokens
    assert 1250500.50 in vals
    assert 24.5 in vals
    assert 450.0 in vals


def test_grounding_verified_exact_match():
    query_rows = [
        ["Electronics", 1250000.0, 312500.0],
        ["Software", 840000.0, 420000.0],
    ]
    columns = ["category", "total_revenue", "total_profit"]

    text = "Electronics generated $1,250,000.00 in revenue with $312,500 profit. Software contributed $840,000."

    result = GroundingGuardrail.verify(
        response_text=text,
        query_rows=query_rows,
        columns=columns,
    )

    assert result.is_grounded is True
    assert result.grounding_score == 1.0
    assert len(result.unmatched_figures) == 0
    assert len(result.matched_figures) >= 3


def test_grounding_flags_hallucinated_figures():
    query_rows = [
        ["Electronics", 1250000.0],
    ]
    columns = ["category", "total_revenue"]

    # AI hallucinated a completely fake number: $9,999,999
    text = "Electronics generated $1,250,000 in revenue, but marketing costs reached $9,999,999."

    result = GroundingGuardrail.verify(
        response_text=text,
        query_rows=query_rows,
        columns=columns,
    )

    assert result.is_grounded is False
    assert len(result.unmatched_figures) == 1
    assert result.unmatched_figures[0]["token"] == "$9,999,999"


def test_grounding_percentage_and_count_matches():
    query_rows = [
        ["North America", 0.35, 100],
    ]
    columns = ["region", "share", "volume"]

    # 35% should match 0.35, and count 100 should match 100
    text = "North America represents 35% of total sales with 100 active transactions."

    result = GroundingGuardrail.verify(
        response_text=text,
        query_rows=query_rows,
        columns=columns,
    )

    assert result.is_grounded is True
    assert len(result.unmatched_figures) == 0
