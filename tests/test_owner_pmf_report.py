"""PROD-P6-05: Owner PMF report smoke."""

from __future__ import annotations

from butler.ops.owner_pmf_metrics import format_owner_pmf_report


def test_format_owner_pmf_report_returns_text():
    text = format_owner_pmf_report(days=7)
    assert isinstance(text, str)
    assert text.strip()
