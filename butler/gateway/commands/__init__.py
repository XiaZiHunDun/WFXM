"""Modular command handlers for the Butler gateway.

Each submodule registers its handlers with the command registry on import.
Import this package to ensure all handlers are wired up.
"""

from butler.gateway.commands import (
    dev_commands,
    dialog_commands,
    info_commands,
    lifecycle_commands,
    memory_commands,
    permission_commands,
    project_commands,
    runtime_commands,
)

__all__ = [
    "dev_commands",
    "dialog_commands",
    "info_commands",
    "lifecycle_commands",
    "memory_commands",
    "permission_commands",
    "project_commands",
    "runtime_commands",
]
