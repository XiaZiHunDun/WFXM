"""Modular command handlers for the Butler gateway.

Each submodule registers its handlers with the command registry on import.
Import this package to ensure all handlers are wired up.
"""

from butler.gateway.commands import (
    dialog_commands,
    info_commands,
    lifecycle_commands,
)

__all__ = [
    "dialog_commands",
    "info_commands",
    "lifecycle_commands",
]
