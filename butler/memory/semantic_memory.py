"""Semantic Memory Index — cold layer memory using ChromaDB.

This module implements a semantic retrieval layer that stores conversation
summaries as embeddings, enabling context-aware retrieval of historical
information across long conversations.

Key features:
- Turn-level embedding storage
- Chapter-level embedding storage
- Semantic search across historical context
- Automatic embedding generation
- Thread-safe operations
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Disable ChromaDB telemetry to avoid capture() errors
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.debug("ChromaDB not installed, semantic memory disabled")


class SemanticMemory:
    def __init__(self, collection_name: str = "wfxm_conversation", persist_directory: str | None = None):
        self._collection_name = collection_name
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        default_data_dir = os.path.join(project_root, ".wfxm_data")

        self._persist_directory = persist_directory or os.path.join(
            default_data_dir, "chromadb"
        )
        self._client: Any = None
        self._collection: Any = None
        self._lock = threading.Lock()
        self._initialized = False
    
    @property
    def available(self) -> bool:
        return CHROMADB_AVAILABLE
    
    def _initialize(self) -> None:
        if not CHROMADB_AVAILABLE:
            raise RuntimeError("ChromaDB not installed")
        
        with self._lock:
            if self._initialized:
                return
            
            os.makedirs(self._persist_directory, exist_ok=True)
            
            self._client = chromadb.PersistentClient(
                path=self._persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                ),
            )
            
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"description": "WFXM conversation semantic memory"},
            )
            
            self._initialized = True
            logger.debug("Semantic memory initialized at %s", self._persist_directory)
    
    def add_turn_summary(
        self,
        turn_number: int,
        user_intent: str,
        assistant_action: str,
        result_summary: str,
        conversation_id: str = "default",
        files_touched: list[str] | None = None,
    ) -> None:
        if not CHROMADB_AVAILABLE:
            return
        
        self._initialize()
        
        document = f"Turn {turn_number}: {user_intent} | {assistant_action} | {result_summary}"
        metadata = {
            "type": "turn",
            "turn_number": turn_number,
            "conversation_id": conversation_id,
            "user_intent": user_intent[:200],
            "assistant_action": assistant_action[:200],
            "result_summary": result_summary[:200],
            "files_touched": json.dumps(files_touched or []),
        }
        
        with self._lock:
            self._collection.upsert(
                documents=[document],
                metadatas=[metadata],
                ids=[f"turn_{conversation_id}_{turn_number}"],
            )
    
    def add_chapter_summary(
        self,
        chapter_number: int,
        start_turn: int,
        end_turn: int,
        summary: str,
        conversation_id: str = "default",
        key_decisions: list[str] | None = None,
        key_files: list[str] | None = None,
        key_technologies: list[str] | None = None,
    ) -> None:
        if not CHROMADB_AVAILABLE:
            return
        
        self._initialize()
        
        document = f"Chapter {chapter_number} (Turn {start_turn}-{end_turn}): {summary}"
        metadata = {
            "type": "chapter",
            "chapter_number": chapter_number,
            "start_turn": start_turn,
            "end_turn": end_turn,
            "conversation_id": conversation_id,
            "key_decisions": json.dumps(key_decisions or []),
            "key_files": json.dumps(key_files or []),
            "key_technologies": json.dumps(key_technologies or []),
        }
        
        with self._lock:
            self._collection.upsert(
                documents=[document],
                metadatas=[metadata],
                ids=[f"chapter_{conversation_id}_{chapter_number}"],
            )
    
    def search(
        self,
        query: str,
        conversation_id: str = "default",
        top_k: int = 5,
        include_turns: bool = True,
        include_chapters: bool = True,
    ) -> list[dict[str, Any]]:
        if not CHROMADB_AVAILABLE:
            return []
        
        self._initialize()
        
        where: dict[str, Any] = {}
        conditions: list[dict[str, Any]] = []
        
        conditions.append({"conversation_id": conversation_id})
        
        types_filter: list[str] = []
        if include_turns:
            types_filter.append("turn")
        if include_chapters:
            types_filter.append("chapter")
        if types_filter:
            conditions.append({"type": {"$in": types_filter}})
        
        if len(conditions) == 1:
            where = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}
        
        with self._lock:
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where if where else None,
                include=["documents", "metadatas", "distances"],
            )
        
        matches = []
        for i, (doc, meta, dist) in enumerate(
            zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ):
            match = {
                "id": results["ids"][0][i],
                "document": doc,
                "metadata": meta,
                "distance": dist,
                "type": meta.get("type"),
            }
            if meta.get("type") == "turn":
                match["turn_number"] = meta.get("turn_number")
            elif meta.get("type") == "chapter":
                match["chapter_number"] = meta.get("chapter_number")
                match["start_turn"] = meta.get("start_turn")
                match["end_turn"] = meta.get("end_turn")
            matches.append(match)
        
        matches.sort(key=lambda x: x["distance"])
        return matches
    
    def get_relevant_context(
        self,
        query: str,
        conversation_id: str = "default",
        max_context_chars: int = 2000,
    ) -> str:
        matches = self.search(query, conversation_id=conversation_id, top_k=5)
        
        context_parts: list[str] = []
        total_chars = 0
        
        for match in matches:
            if total_chars >= max_context_chars:
                break
            
            doc = match["document"]
            if total_chars + len(doc) <= max_context_chars:
                context_parts.append(doc)
                total_chars += len(doc)
        
        return "\n\n".join(context_parts)
    
    def get_chapter_context(
        self,
        conversation_id: str = "default",
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        matches = self.search(
            "",
            conversation_id=conversation_id,
            top_k=top_k,
            include_turns=False,
            include_chapters=True,
        )
        return matches
    
    def reset(self, conversation_id: str = "default") -> None:
        if not CHROMADB_AVAILABLE:
            return
        
        self._initialize()
        
        with self._lock:
            self._collection.delete(
                where={"conversation_id": conversation_id}
            )
    
    def get_stats(self) -> dict[str, Any]:
        if not CHROMADB_AVAILABLE:
            return {"available": False}
        
        self._initialize()
        
        with self._lock:
            count = self._collection.count()
        
        return {
            "available": True,
            "total_documents": count,
            "persist_directory": self._persist_directory,
        }


_singleton: Optional[SemanticMemory] = None


def get_semantic_memory() -> SemanticMemory:
    global _singleton
    if _singleton is None:
        _singleton = SemanticMemory()
    return _singleton


__all__ = [
    "SemanticMemory",
    "get_semantic_memory",
    "CHROMADB_AVAILABLE",
]
