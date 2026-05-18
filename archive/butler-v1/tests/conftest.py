"""Shared fixtures for Butler system tests."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir():
    """Create a temporary directory and clean up after test."""
    d = Path(tempfile.mkdtemp(prefix="butler_test_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def butler_home(tmp_dir):
    """Create a temporary butler home directory."""
    home = tmp_dir / "butler_home"
    home.mkdir()
    return home


@pytest.fixture
def project_workspace(tmp_dir):
    """Create a temporary project workspace."""
    ws = tmp_dir / "test_project"
    ws.mkdir()
    return ws
