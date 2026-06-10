"""R5-15: atomic_write_text must not double-close fd after fdopen."""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.unit
def test_atomic_write_no_redundant_os_close_after_fdopen():
    from butler.io import atomic_write

    source = inspect.getsource(atomic_write.atomic_write_text)
    assert source.count("os.close(") == 0
    assert "fdopen owns fd" in source or "fdopen takes ownership" in source
