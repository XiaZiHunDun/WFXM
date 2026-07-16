"""Conversation State Persistence using SQLite.

This module provides persistent storage for ConversationState objects,
enabling long-running conversations to survive restarts and enabling
session recovery.

Key features:
- SQLite-based persistent storage
- Automatic schema migration
- Thread-safe operations
- Session recovery support
- Cleanup of old sessions
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Optional

from butler.core.conversation_state import ConversationState

logger = logging.getLogger(__name__)


class ConversationStore:
    _SCHEMA_VERSION = 2
    
    def __init__(self, db_path: str | None = None):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        default_data_dir = os.path.join(project_root, ".wfxm_data")

        self._db_path = db_path or os.path.join(
            default_data_dir, "conversations.db"
        )
        self._lock = threading.Lock()
        self._ensure_schema()
    
    def _ensure_schema(self) -> None:
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("PRAGMA user_version")
                current_version = cursor.fetchone()[0]
                
                if current_version == 0:
                    cursor.execute("""
                        CREATE TABLE conversations (
                            id TEXT PRIMARY KEY,
                            goal TEXT,
                            state_json TEXT NOT NULL,
                            last_updated INTEGER NOT NULL,
                            turn_count INTEGER DEFAULT 0
                        )
                    """)
                    cursor.execute("CREATE INDEX idx_conversations_last_updated ON conversations(last_updated)")
                    current_version = 1
                
                if current_version == 1:
                    cursor.execute("ALTER TABLE conversations ADD COLUMN key_technologies TEXT")
                    cursor.execute("ALTER TABLE conversations ADD COLUMN chapter_count INTEGER DEFAULT 0")
                    current_version = 2
                
                cursor.execute(f"PRAGMA user_version = {self._SCHEMA_VERSION}")
                conn.commit()
    
    def save(self, conversation_id: str, state: ConversationState) -> None:
        state_dict = state.to_full_state()
        state_json = json.dumps(state_dict, ensure_ascii=False)
        
        now = int(time.time())
        turn_count = len(state.turn_summaries)
        chapter_count = len(state.chapter_summaries)
        key_technologies = json.dumps(state.key_technologies, ensure_ascii=False)
        
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO conversations
                    (id, goal, state_json, last_updated, turn_count, key_technologies, chapter_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    conversation_id,
                    state.conversation_goal,
                    state_json,
                    now,
                    turn_count,
                    key_technologies,
                    chapter_count,
                ))
                conn.commit()
    
    def load(self, conversation_id: str) -> Optional[ConversationState]:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT state_json FROM conversations WHERE id = ?
                """, (conversation_id,))
                row = cursor.fetchone()
                
                if row is None:
                    return None
                
                state_json = row[0]
        
        try:
            state_dict = json.loads(state_json)
            return ConversationState.from_dict(state_dict)
        except json.JSONDecodeError:
            logger.error("Failed to decode state for conversation %s", conversation_id)
            return None
    
    def exists(self, conversation_id: str) -> bool:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 1 FROM conversations WHERE id = ?
                """, (conversation_id,))
                return cursor.fetchone() is not None
    
    def list_conversations(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, goal, last_updated, turn_count, chapter_count, key_technologies
                    FROM conversations
                    ORDER BY last_updated DESC
                    LIMIT ?
                """, (limit,))
                
                results = []
                for row in cursor.fetchall():
                    techs = []
                    try:
                        if row[5]:
                            techs = json.loads(row[5])
                    except json.JSONDecodeError:
                        pass
                    
                    results.append({
                        "id": row[0],
                        "goal": row[1],
                        "last_updated": row[2],
                        "turn_count": row[3],
                        "chapter_count": row[4],
                        "key_technologies": techs,
                    })
        
        return results
    
    def delete(self, conversation_id: str) -> bool:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
                conn.commit()
                return cursor.rowcount > 0
    
    def cleanup_old_conversations(self, max_age_days: int = 30) -> int:
        max_age_seconds = max_age_days * 24 * 60 * 60
        cutoff = int(time.time()) - max_age_seconds
        
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM conversations WHERE last_updated < ?", (cutoff,))
                conn.commit()
                return cursor.rowcount
    
    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM conversations")
                total = cursor.fetchone()[0]
                
                cursor.execute("SELECT SUM(turn_count) FROM conversations")
                total_turns = cursor.fetchone()[0] or 0
                
                cursor.execute("SELECT SUM(chapter_count) FROM conversations")
                total_chapters = cursor.fetchone()[0] or 0
        
        return {
            "total_conversations": total,
            "total_turns": total_turns,
            "total_chapters": total_chapters,
            "db_path": self._db_path,
        }


_singleton: Optional[ConversationStore] = None


def get_conversation_store() -> ConversationStore:
    global _singleton
    if _singleton is None:
        _singleton = ConversationStore()
    return _singleton


__all__ = [
    "ConversationStore",
    "get_conversation_store",
]
