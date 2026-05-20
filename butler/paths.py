"""Butler path resolution — no Hermes imports."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_hermes_home() -> Path:
    """Hermes config root (``HERMES_HOME`` or ``~/.hermes``).

    Used only for co-installed Gateway / legacy display; Butler data lives in
    ``get_butler_home()`` via ``butler.config``.
    """
    val = os.environ.get("HERMES_HOME", "").strip()
    if val:
        return Path(val).expanduser().resolve()
    return (Path.home() / ".hermes").resolve()
