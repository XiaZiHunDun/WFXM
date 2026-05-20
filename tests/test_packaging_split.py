"""Butler-only vs hermes-vendored install boundary."""

from __future__ import annotations

import importlib.util

import pytest


@pytest.mark.unit
def test_butler_importable():
    import butler  # noqa: F401


@pytest.mark.unit
def test_hermes_cli_optional():
    """hermes_cli is optional unless hermes-vendored is installed (dev / hermes-gateway extra)."""
    spec = importlib.util.find_spec("hermes_cli")
    # In CI/dev we install .[dev]; bare butler-only installs skip this assertion in docs.
    if spec is None:
        pytest.skip("hermes-vendored not installed (expected for butler-only pip install -e .)")
