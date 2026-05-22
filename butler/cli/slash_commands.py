"""Butler CLI slash-command registry, completion, and validation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from prompt_toolkit.completion import Completer, Completion

# Primary commands (first token after optional leading /)
BUILTIN_COMMANDS: tuple[str, ...] = (
    "help",
    "projects",
    "switch",
    "model",
    "new",
    "status",
    "health",
    "诊断",
    "detail",
    "steer",
    "workflow",
    "quit",
    "exit",
    "q",
)

# Memory slash commands (Chinese; routed via gateway memory_commands in main.py)
MEMORY_SLASH_COMMANDS: tuple[str, ...] = (
    "/记忆待审",
    "/pending-memory",
    "/待审记忆",
    "/记忆图谱",
    "/memory-graph",
    "/三元组",
    "/批准记忆",
    "/approve-memory",
    "/批准",
    "/拒绝记忆",
    "/reject-memory",
    "/拒绝",
    "/工作流",
    "/workflow",
)

# Aliases map to canonical names for matching only
_ALIASES: dict[str, str] = {
    "诊断": "health",
    "工作流": "workflow",
    "q": "quit",
    "exit": "quit",
}

_SUBCOMMANDS: dict[str, tuple[str, ...]] = {
    "model": ("butler", "dev_agent", "content_agent", "review_agent"),
}


def normalize_slash_token(text: str) -> str:
    raw = (text or "").strip().split(maxsplit=1)[0].lower()
    if raw.startswith("/"):
        raw = raw[1:]
    return _ALIASES.get(raw, raw)


def slash_first_token(text: str) -> str:
    raw = (text or "").strip().split(maxsplit=1)[0].lower()
    return raw if raw.startswith("/") else f"/{raw}"


_KNOWN_SLASH_TOKENS: frozenset[str] = frozenset(
    {f"/{name}" for name in BUILTIN_COMMANDS}
    | {"/诊断"}
    | set(MEMORY_SLASH_COMMANDS)
)


def is_known_slash_command(text: str) -> bool:
    return slash_first_token(text) in _KNOWN_SLASH_TOKENS


def iter_completion_words() -> Iterable[str]:
    for cmd in BUILTIN_COMMANDS:
        if cmd in _ALIASES.values() and cmd in ("quit", "exit", "health"):
            continue
        yield f"/{cmd}"
    for mem_cmd in MEMORY_SLASH_COMMANDS:
        yield mem_cmd
    for cmd, subs in _SUBCOMMANDS.items():
        for sub in subs:
            yield f"/{cmd} {sub}"


def build_slash_completer() -> Completer:
    """prompt_toolkit completer for built-in Butler slash commands."""
    from prompt_toolkit.completion import Completer, Completion

    words = sorted(set(iter_completion_words()))

    class _ButlerSlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if not text.startswith("/"):
                return
            parts = text.split()
            if len(parts) <= 1:
                prefix = parts[0] if parts else "/"
                for word in words:
                    if word.startswith(prefix) or word.split()[0].startswith(prefix):
                        yield Completion(
                            word,
                            start_position=-len(prefix),
                            display=word,
                        )
            elif len(parts) == 2 and parts[0] == "/model":
                sub_prefix = parts[1]
                for sub in _SUBCOMMANDS["model"]:
                    candidate = f"/model {sub}"
                    if candidate.startswith(text) or sub.startswith(sub_prefix):
                        yield Completion(
                            candidate,
                            start_position=-len(text),
                            display=candidate,
                        )

    return _ButlerSlashCompleter()
