"""Grounding and Anti-Hallucination Guardrail (ADR-004 & Phase 4).

Strict verification ensures that every single numeric figure, percentage,
or monetary value stated in the AI Assistant's answer is directly traced
to the actual executed database query results.
"""

import re
from typing import Any


def _normalize_number(num_str: str) -> float | None:
    """Normalize numeric strings like '$1,234.50', '45.2%', '12k', '1.5M' to float."""
    cleaned = num_str.strip().replace("$", "").replace(",", "").replace("%", "").strip()
    multiplier = 1.0

    if cleaned.endswith("k") or cleaned.endswith("K"):
        multiplier = 1000.0
        cleaned = cleaned[:-1]
    elif cleaned.endswith("m") or cleaned.endswith("M"):
        multiplier = 1000000.0
        cleaned = cleaned[:-1]
    elif cleaned.endswith("b") or cleaned.endswith("B"):
        multiplier = 1000000000.0
        cleaned = cleaned[:-1]

    try:
        return float(cleaned) * multiplier
    except (ValueError, TypeError):
        return None


def extract_numbers_from_text(text: str) -> list[tuple[str, float]]:
    """Extract all candidate numeric expressions from natural language text.

    Returns tuples of (raw_token, parsed_float_value).
    """
    pattern = r"\$?\s*\d[\d,]*(?:\.\d+)?%?[kKmMbB]?"

    matches = [m.group(0).strip() for m in re.finditer(pattern, text) if m.group(0).strip()]
    results: list[tuple[str, float]] = []

    for token in matches:
        val = _normalize_number(token)
        if val is not None:
            # Skip obvious year tokens (e.g., 1950-2050) if token has no decimal/currency
            if (
                1950 <= val <= 2050
                and "." not in token
                and "$" not in token
                and "%" not in token
                and "," not in token
            ):
                continue
            results.append((token, val))

    return results


def extract_numbers_from_query_results(
    rows: list[list[Any]] | list[dict[str, Any]],
    columns: list[str] | None = None,
) -> set[float]:
    """Extract all reference numbers present in executed SQL query result rows."""
    reference_numbers: set[float] = set()

    # Add row count as a valid reference number
    reference_numbers.add(float(len(rows)))

    for row in rows:
        values = row.values() if isinstance(row, dict) else row
        for val in values:
            if val is None:
                continue
            if isinstance(val, (int, float)):
                reference_numbers.add(float(val))
            elif isinstance(val, str):
                num = _normalize_number(val)
                if num is not None:
                    reference_numbers.add(num)

    return reference_numbers


class GroundingResult:
    def __init__(
        self,
        is_grounded: bool,
        grounding_score: float,
        matched_figures: list[dict[str, Any]],
        unmatched_figures: list[dict[str, Any]],
        details: str,
    ):
        self.is_grounded = is_grounded
        self.grounding_score = grounding_score
        self.matched_figures = matched_figures
        self.unmatched_figures = unmatched_figures
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_grounded": self.is_grounded,
            "grounding_score": round(self.grounding_score, 4),
            "matched_figures": self.matched_figures,
            "unmatched_figures": self.unmatched_figures,
            "details": self.details,
        }


class GroundingGuardrail:
    """Verifies that every figure in an AI response comes from executed SQL results."""

    @classmethod
    def verify(
        cls,
        response_text: str,
        query_rows: list[list[Any]] | list[dict[str, Any]],
        columns: list[str] | None = None,
        relative_tolerance: float = 0.015,  # 1.5% tolerance for rounding / format precision
    ) -> GroundingResult:
        """Verify natural language response against executed SQL data."""
        extracted = extract_numbers_from_text(response_text)
        references = extract_numbers_from_query_results(query_rows, columns)

        if not extracted:
            # No numbers claimed in text; grounded by default
            return GroundingResult(
                is_grounded=True,
                grounding_score=1.0,
                matched_figures=[],
                unmatched_figures=[],
                details="No numeric claims made in response; grounded.",
            )

        matched: list[dict[str, Any]] = []
        unmatched: list[dict[str, Any]] = []

        for token, val in extracted:
            is_match = False
            for ref in references:
                if ref == 0 and val == 0:
                    is_match = True
                    break
                # Check exact or percentage tolerance
                diff = abs(val - ref)
                if diff < 1e-4:
                    is_match = True
                    break
                if ref != 0 and (diff / abs(ref)) <= relative_tolerance:
                    is_match = True
                    break
                # Check percentage equivalence: 0.25 vs 25%
                if "%" in token and ref != 0:
                    if (
                        abs((val / 100.0) - ref) <= relative_tolerance
                        or abs(val - (ref * 100.0)) <= relative_tolerance
                    ):
                        is_match = True
                        break

            item = {"token": token, "parsed_value": val}
            if is_match:
                matched.append(item)
            else:
                unmatched.append(item)

        total_figures = len(extracted)
        matched_count = len(matched)
        score = matched_count / total_figures if total_figures > 0 else 1.0
        is_grounded = len(unmatched) == 0

        details = (
            f"Verified {matched_count}/{total_figures} figures grounded in query results."
            if is_grounded
            else f"Detected {len(unmatched)} ungrounded figure(s): {[u['token'] for u in unmatched]}."
        )

        return GroundingResult(
            is_grounded=is_grounded,
            grounding_score=score,
            matched_figures=matched,
            unmatched_figures=unmatched,
            details=details,
        )
