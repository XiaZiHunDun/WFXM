"""Langfuse Integration — Observability and evaluation tracking.

This module implements integration with Langfuse for:
- LLM call tracing
- Prompt versioning
- Evaluation metrics tracking
- Memory retrieval monitoring

Key features:
- Turn-level tracing
- Memory retrieval tracing
- Custom metrics for conversation quality
- Seamless integration with the agent loop
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from langfuse import Langfuse
    from langfuse.decorators import langfuse_context, observe
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    logger.debug("Langfuse not installed, tracing disabled")


class LangfuseTracker:
    def __init__(self):
        self._client: Any = None
        self._enabled = False
        self._session_id: str = ""
        
        if LANGFUSE_AVAILABLE:
            try:
                self._client = Langfuse()
                self._enabled = True
                logger.info("Langfuse tracker initialized")
            except Exception as e:
                logger.debug("Langfuse initialization failed: %s", e)
    
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    def start_session(self, session_id: str, metadata: Dict[str, Any] | None = None) -> None:
        if not self._enabled:
            return
        self._session_id = session_id
    
    def end_session(self, metadata: Dict[str, Any] | None = None) -> None:
        if not self._enabled:
            return
        self._session_id = ""
    
    def trace_turn(
        self,
        turn_number: int,
        user_message: str,
        assistant_response: str,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        if not self._enabled:
            return
        
        try:
            trace = self._client.trace(
                name=f"turn_{turn_number}",
                session_id=self._session_id,
                metadata=metadata or {},
            )
            
            trace.generation(
                name="user_message",
                input=user_message,
                output=assistant_response,
                metadata=metadata or {},
            )
        except Exception as e:
            logger.debug("Langfuse trace failed: %s", e)
    
    def trace_memory_retrieval(
        self,
        query: str,
        results: list,
        retrieval_type: str = "semantic",
        latency_ms: float = 0.0,
    ) -> None:
        if not self._enabled:
            return
        
        try:
            trace = self._client.trace(
                name=f"memory_retrieval_{retrieval_type}",
                session_id=self._session_id,
            )
            
            trace.generation(
                name=f"{retrieval_type}_retrieval",
                input=query,
                output=str(results),
                metadata={
                    "retrieval_type": retrieval_type,
                    "result_count": len(results),
                    "latency_ms": latency_ms,
                },
            )
        except Exception as e:
            logger.debug("Langfuse memory trace failed: %s", e)
    
    def trace_knowledge_graph(
        self,
        query: str,
        entities_found: int,
        relations_found: int,
        paths_found: int,
    ) -> None:
        if not self._enabled:
            return
        
        try:
            trace = self._client.trace(
                name="knowledge_graph_query",
                session_id=self._session_id,
            )
            
            trace.generation(
                name="graph_query",
                input=query,
                output=f"entities={entities_found}, relations={relations_found}, paths={paths_found}",
                metadata={
                    "entities_found": entities_found,
                    "relations_found": relations_found,
                    "paths_found": paths_found,
                },
            )
        except Exception as e:
            logger.debug("Langfuse KG trace failed: %s", e)
    
    def track_metric(
        self,
        name: str,
        value: float,
        turn_number: int | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        if not self._enabled:
            return
        
        try:
            self._client.score(
                trace_id=self._session_id,
                name=name,
                value=value,
                metadata={
                    "turn_number": turn_number,
                    **(metadata or {}),
                },
            )
        except Exception as e:
            logger.debug("Langfuse metric tracking failed: %s", e)
    
    def track_conversation_metrics(
        self,
        turn_number: int,
        memory_recall_rate: float,
        task_progress: float,
        context_tokens: int,
        reasoning_depth: int,
    ) -> None:
        if not self._enabled:
            return
        
        metrics = [
            ("memory_recall_rate", memory_recall_rate),
            ("task_progress", task_progress),
            ("context_tokens", float(context_tokens)),
            ("reasoning_depth", float(reasoning_depth)),
        ]
        
        for name, value in metrics:
            self.track_metric(name, value, turn_number=turn_number)


_singleton: Optional[LangfuseTracker] = None


def get_langfuse_tracker() -> LangfuseTracker:
    global _singleton
    if _singleton is None:
        _singleton = LangfuseTracker()
    return _singleton


__all__ = [
    "LangfuseTracker",
    "get_langfuse_tracker",
    "LANGFUSE_AVAILABLE",
]
