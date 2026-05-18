"""Session persistence using SQLite - project-scoped conversation history."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from butler.providers.base import Message, Role, ToolCall, ToolResult


class SessionStore:
    """SQLite-backed session storage. Sessions are scoped by (user, channel, project)."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'cli',
                project TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT DEFAULT '',
                tool_calls TEXT DEFAULT NULL,
                tool_results TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_scope ON sessions(user_id, channel, project);
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        """)
        self._conn.commit()

    def create_session(self, user_id: str, channel: str = "cli", project: str = "") -> str:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO sessions (session_id, user_id, channel, project, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, user_id, channel, project, now, now),
        )
        self._conn.commit()
        return session_id

    def get_or_create_session(self, user_id: str, channel: str = "cli", project: str = "") -> str:
        """Find the latest session for (user, channel, project) or create a new one."""
        row = self._conn.execute(
            "SELECT session_id FROM sessions WHERE user_id = ? AND channel = ? AND project = ? ORDER BY updated_at DESC LIMIT 1",
            (user_id, channel, project),
        ).fetchone()
        if row:
            return row["session_id"]
        return self.create_session(user_id, channel, project)

    def append_message(self, session_id: str, message: Message) -> None:
        now = datetime.now(timezone.utc).isoformat()
        tool_calls_json = None
        if message.tool_calls:
            tool_calls_json = json.dumps([
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in message.tool_calls
            ], ensure_ascii=False)
        tool_results_json = None
        if message.tool_results:
            tool_results_json = json.dumps([
                {"tool_call_id": tr.tool_call_id, "content": tr.content, "is_error": tr.is_error}
                for tr in message.tool_results
            ], ensure_ascii=False)

        self._conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_calls, tool_results, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, message.role.value, message.content, tool_calls_json, tool_results_json, now),
        )
        self._conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id),
        )
        self._conn.commit()

    def get_history(self, session_id: str, limit: int = 50) -> list[Message]:
        rows = self._conn.execute(
            "SELECT role, content, tool_calls, tool_results FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()

        messages: list[Message] = []
        for row in reversed(rows):
            tool_calls = None
            if row["tool_calls"]:
                raw = json.loads(row["tool_calls"])
                tool_calls = [ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"]) for tc in raw]
            tool_results = None
            if row["tool_results"]:
                raw = json.loads(row["tool_results"])
                tool_results = [ToolResult(tool_call_id=tr["tool_call_id"], content=tr["content"], is_error=tr.get("is_error", False)) for tr in raw]
            messages.append(Message(
                role=Role(row["role"]), content=row["content"],
                tool_calls=tool_calls, tool_results=tool_results,
            ))
        return messages

    def clear_session(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self._conn.commit()

    def list_sessions(self, user_id: str, project: str = "", limit: int = 20) -> list[dict]:
        if project:
            rows = self._conn.execute(
                "SELECT session_id, channel, project, created_at, updated_at FROM sessions WHERE user_id = ? AND project = ? ORDER BY updated_at DESC LIMIT ?",
                (user_id, project, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT session_id, channel, project, created_at, updated_at FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def close(self):
        self._conn.close()
