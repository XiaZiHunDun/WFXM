"""Tool JSON schemas for Butler builtin tools, extracted from registry.py."""

from __future__ import annotations

from typing import Any


from butler.tools.file_io import MAX_READ_FILE_LINES
from butler.tools.terminal_impl import MAX_TERMINAL_TIMEOUT_SECONDS


def read_file_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path"},
            "offset": {
                "type": "integer",
                "description": "Line number to start from (1-indexed)",
                "default": 1,
            },
            "limit": {
                "type": "integer",
                "description": f"Max lines to read (1-{MAX_READ_FILE_LINES})",
                "default": 500,
                "minimum": 1,
                "maximum": MAX_READ_FILE_LINES,
            },
        },
        "required": ["path"],
    }


def write_file_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    }


def patch_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "old_string": {"type": "string", "description": "Exact text to find"},
            "new_string": {"type": "string", "description": "Replacement text"},
        },
        "required": ["path", "old_string", "new_string"],
    }


def delete_file_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to delete"},
        },
        "required": ["path"],
    }


def terminal_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {
                "type": "integer",
                "description": f"Timeout in seconds (1-{MAX_TERMINAL_TIMEOUT_SECONDS})",
                "default": 30,
                "minimum": 1,
                "maximum": MAX_TERMINAL_TIMEOUT_SECONDS,
            },
            "workdir": {"type": "string", "description": "Working directory"},
        },
        "required": ["command"],
    }


def search_files_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Search pattern (regex)"},
            "path": {
                "type": "string",
                "description": "Directory or file to search in",
                "default": ".",
            },
            "include": {"type": "string", "description": "Glob pattern to filter files"},
        },
        "required": ["pattern"],
    }


def list_directory_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path", "default": "."},
        },
    }


def delegate_task_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "description": "Agent role: 'dev', 'content', or 'review'",
                "enum": ["dev", "content", "review"],
            },
            "category": {
                "type": "string",
                "description": "Optional preset: quick, deep, ultrabrain, ui-build",
            },
            "task": {"type": "string", "description": "Task description"},
            "context": {
                "type": "string",
                "description": "Additional context for the agent",
            },
        },
        "required": ["role", "task"],
    }


def run_workflow_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Workflow name (e.g. novel-factory)",
            },
            "hint": {
                "type": "string",
                "description": "Optional user goal appended to each step",
                "default": "",
            },
        },
        "required": ["name"],
    }


__all__ = [
    "read_file_schema",
    "write_file_schema",
    "patch_schema",
    "delete_file_schema",
    "terminal_schema",
    "search_files_schema",
    "list_directory_schema",
    "delegate_task_schema",
    "run_workflow_schema",
]
