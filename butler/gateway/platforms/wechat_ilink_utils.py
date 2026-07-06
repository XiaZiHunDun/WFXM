"""Backward-compat shim — canonical: ``butler.gateway.platforms.wechat_ilink._utils_legacy``."""

from __future__ import annotations

import importlib

_canonical = importlib.import_module("butler.gateway.platforms.wechat_ilink._utils_legacy")

__doc__ = _canonical.__doc__ or ""
logger = _canonical.logger

for _name in dir(_canonical):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_canonical, _name)

del _canonical, _name
