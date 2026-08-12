"""Butler Config Secrets Crypto (Deprecated).

This module is deprecated. Use butler.configuration.secrets_crypto instead.
"""
from __future__ import annotations

import warnings

warnings.warn(
    "butler.config_secrets_crypto is deprecated, use butler.configuration.secrets_crypto instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.configuration.secrets_crypto import *
try:
    from butler.configuration.secrets_crypto import __all__
except ImportError:
    pass
