"""Shared environment variable parsing for Butler."""

from __future__ import annotations

import builtins
import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_FALSEY = frozenset({"0", "false", "no", "off", ""})
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_KNOWN_DEPLOY_ENVS = frozenset({"dev", "staging", "prod", "test"})

_dotenv_loaded = False
_warned_unknown_deploy_env = False


def init_dotenv(*, force: bool = False) -> None:
    """Load repository ``.env`` once (no-op under pytest; ``override=False``)."""
    global _dotenv_loaded
    if _dotenv_loaded and not force:
        return
    if os.getenv("PYTEST_CURRENT_TEST"):
        _dotenv_loaded = True
        return
    load_dotenv()
    _dotenv_loaded = True


def env_truthy(name: str, *, default: bool = False) -> bool:
    """Return True when ``name`` is a truthy flag (1/true/yes/on); falsey on 0/false/no/off/empty."""
    raw = os.getenv(name)
    if raw is None:
        return default
    stripped = raw.strip().lower()
    if not stripped:
        return default
    if stripped in _FALSEY:
        return False
    if stripped in _TRUTHY:
        return True
    return default


def int_env(
    name: str,
    default: int,
    *,
    min: int | None = None,
    max: int | None = None,
) -> int:
    """Parse integer env; invalid or empty → ``default`` with warning."""
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        value = default
    else:
        try:
            value = int(str(raw).strip())
        except ValueError:
            logger.warning("%s=%r invalid, using default %s", name, raw, default)
            value = default
    if min is not None:
        value = builtins.max(min, value)
    if max is not None:
        value = builtins.min(max, value)
    return value


def float_env(
    name: str,
    default: float,
    *,
    min: float | None = None,
    max: float | None = None,
    warn_on_clamp: bool = True,
) -> float:
    """Parse float env; invalid → ``default``; optional clamp with warning."""
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        value = default
    else:
        try:
            value = float(str(raw).strip())
        except ValueError:
            logger.warning("%s=%r invalid, using default %s", name, raw, default)
            value = default
    if min is not None and value < min:
        if warn_on_clamp:
            logger.warning("%s=%s below minimum %s, clamped", name, value, min)
        value = min
    if max is not None and value > max:
        if warn_on_clamp:
            logger.warning("%s=%s above maximum %s, clamped", name, value, max)
        value = max
    return float(value)


def butler_deploy_env() -> str:
    """Normalized ``BUTLER_ENV`` (lowercase) or empty if unset."""
    return os.getenv("BUTLER_ENV", "").strip().lower()


def is_butler_prod() -> bool:
    """True when deploy env is ``prod`` or unknown non-empty (strict path)."""
    global _warned_unknown_deploy_env
    env = butler_deploy_env()
    if not env:
        return False
    if env == "prod":
        return True
    if env in _KNOWN_DEPLOY_ENVS:
        return False
    if not _warned_unknown_deploy_env:
        logger.warning(
            "BUTLER_ENV=%r unknown (expected dev/staging/prod/test); treating as prod (strict)",
            env,
        )
        _warned_unknown_deploy_env = True
    return True
