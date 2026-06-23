"""Discount helper — intentional logic bug for head-to-head T2."""

from __future__ import annotations


def apply_discount(price: float, rate: float) -> float:
    """Apply fractional discount rate (e.g. 0.1 = 10% off)."""
    return price * (1 - rate)
