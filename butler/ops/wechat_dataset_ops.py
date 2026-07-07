"""WeChat dataset YAML load best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def safe_load_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore[import-untyped]

        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        logger.warning("PyYAML not installed; attempting JSON fallback for %s", path.name)
        return None
    except Exception as exc:
        logger.warning("Failed to load %s: %s", path, exc)
        return None
