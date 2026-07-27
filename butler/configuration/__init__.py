"""Butler Configuration Module.

Organizational namespace grouping configuration-related modules:
- settings: core config
- gateway: gateway settings
- memory: memory settings
- context: context settings
- secrets: secrets config
- service: service config
- provider_presets: provider presets
"""
from __future__ import annotations

__all__ = [
    "settings",
    "settings_ops",
    "gateway",
    "gateway_ops",
    "memory",
    "memory_ops",
    "context",
    "context_ops",
    "secrets",
    "secrets_ops",
    "secrets_crypto",
    "secrets_crypto_ops",
    "service",
    "provider_presets",
    "provider_presets_ops",
]

from . import settings
from . import settings_ops
from . import gateway
from . import gateway_ops
from . import memory
from . import memory_ops
from . import context
from . import context_ops
from . import secrets
from . import secrets_ops
from . import secrets_crypto
from . import secrets_crypto_ops
from . import service
from . import provider_presets
from . import provider_presets_ops