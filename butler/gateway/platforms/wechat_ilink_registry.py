"""Backward-compat shim — canonical: ``butler.gateway.platforms.wechat_ilink.registry``."""

from __future__ import annotations

import importlib

_canonical = importlib.import_module("butler.gateway.platforms.wechat_ilink.registry")

__doc__ = _canonical.__doc__
logger = getattr(_canonical, "logger", None)

for _name in dir(_canonical):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_canonical, _name)

del _canonical, _name
