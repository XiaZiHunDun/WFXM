"""Tool call optimizer — caching, deduplication, and batching.

Improves tool call efficiency through:
1. Result caching with TTL
2. Duplicate call detection
3. Call batching for certain tools
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ToolCallCache:
    """LRU cache for tool call results."""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: float = 300):
        self._cache: dict[str, tuple[str, float, float]] = {}  # key → (result, timestamp, ttl)
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0}
    
    def _make_key(self, tool_name: str, args: dict[str, Any]) -> str:
        """Create a cache key from tool name and args."""
        # Sort args for consistent hashing
        args_str = str(sorted(args.items()))
        content = f"{tool_name}:{args_str}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def get(self, tool_name: str, args: dict[str, Any]) -> str | None:
        """Get cached result if available and not expired."""
        key = self._make_key(tool_name, args)
        
        with self._lock:
            if key not in self._cache:
                self._stats["misses"] += 1
                return None
            
            result, timestamp, ttl = self._cache[key]
            if time.time() - timestamp > ttl:
                del self._cache[key]
                self._stats["misses"] += 1
                return None
            
            self._stats["hits"] += 1
            return result
    
    def set(self, tool_name: str, args: dict[str, Any], result: str, ttl: float | None = None) -> None:
        """Cache a result."""
        key = self._make_key(tool_name, args)
        ttl = ttl or self._ttl
        
        with self._lock:
            # Evict oldest if at capacity
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
            
            self._cache[key] = (result, time.time(), ttl)
    
    def invalidate(self, tool_name: str, args: dict[str, Any] | None = None) -> None:
        """Invalidate cache entries."""
        with self._lock:
            if args is None:
                # Invalidate all entries for this tool
                keys_to_remove = [
                    k for k in self._cache
                    if k.startswith(hashlib.md5(tool_name.encode()).hexdigest()[:8])
                ]
                for k in keys_to_remove:
                    del self._cache[k]
            else:
                key = self._make_key(tool_name, args)
                self._cache.pop(key, None)
    
    def clear(self) -> None:
        """Clear all cached results."""
        with self._lock:
            self._cache.clear()
    
    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total if total > 0 else 0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": round(hit_rate, 4),
            }


class DuplicateCallDetector:
    """Detects and prevents duplicate tool calls within a time window."""
    
    def __init__(self, window_seconds: float = 1.0):
        self._window = window_seconds
        self._calls: dict[str, float] = {}  # key → timestamp
        self._lock = threading.Lock()
        self._stats = {"duplicates_blocked": 0}
    
    def _make_key(self, tool_name: str, args: dict[str, Any]) -> str:
        """Create a key for deduplication."""
        args_str = str(sorted(args.items()))
        return hashlib.md5(f"{tool_name}:{args_str}".encode()).hexdigest()
    
    def check(self, tool_name: str, args: dict[str, Any]) -> bool:
        """Check if this is a duplicate call.
        
        Returns:
            True if this is a duplicate (should be blocked)
        """
        key = self._make_key(tool_name, args)
        now = time.time()
        
        with self._lock:
            # Clean old entries
            cutoff = now - self._window
            old_keys = [k for k, t in self._calls.items() if t < cutoff]
            for k in old_keys:
                del self._calls[k]
            
            # Check for duplicate
            if key in self._calls:
                self._stats["duplicates_blocked"] += 1
                return True
            
            # Record this call
            self._calls[key] = now
            return False
    
    def get_stats(self) -> dict[str, Any]:
        """Get deduplication statistics."""
        with self._lock:
            return {
                "window_seconds": self._window,
                "tracked_calls": len(self._calls),
                "duplicates_blocked": self._stats["duplicates_blocked"],
            }


class ToolCallOptimizer:
    """Combines caching, deduplication, and batching for tool calls."""
    
    # Tools that are safe to cache
    CACHEABLE_TOOLS = {
        "read_file",
        "search_files",
        "list_directory",
        "skills_list",
        "skill_view",
        "web_fetch",
    }
    
    # Tools that should be deduplicated
    DEDUPABLE_TOOLS = {
        "read_file",
        "search_files",
        "web_search",
        "web_fetch",
    }
    
    def __init__(self):
        self._cache = ToolCallCache()
        self._dedup = DuplicateCallDetector()
        self._lock = threading.Lock()
    
    def should_cache(self, tool_name: str) -> bool:
        """Check if a tool's results should be cached."""
        return tool_name in self.CACHEABLE_TOOLS
    
    def should_dedup(self, tool_name: str) -> bool:
        """Check if a tool's calls should be deduplicated."""
        return tool_name in self.DEDUPABLE_TOOLS
    
    def check_cache(self, tool_name: str, args: dict[str, Any]) -> str | None:
        """Check cache for a tool call result."""
        if not self.should_cache(tool_name):
            return None
        return self._cache.get(tool_name, args)
    
    def set_cache(self, tool_name: str, args: dict[str, Any], result: str) -> None:
        """Cache a tool call result."""
        if self.should_cache(tool_name):
            self._cache.set(tool_name, args, result)
    
    def check_duplicate(self, tool_name: str, args: dict[str, Any]) -> bool:
        """Check if this is a duplicate call."""
        if not self.should_dedup(tool_name):
            return False
        return self._dedup.check(tool_name, args)
    
    def optimize_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        handler: Callable[[], str],
    ) -> tuple[str, bool]:
        """Execute a tool call with optimizations.
        
        Args:
            tool_name: Name of the tool
            args: Tool arguments
            handler: Function to call if not cached/duplicate
            
        Returns:
            Tuple of (result, was_cached_or_blocked)
        """
        # Check cache first
        cached = self.check_cache(tool_name, args)
        if cached is not None:
            logger.debug("Cache hit for %s", tool_name)
            return cached, True
        
        # Check for duplicate
        if self.check_duplicate(tool_name, args):
            logger.debug("Duplicate call blocked for %s", tool_name)
            return '{"ok": false, "code": "DUPLICATE_BLOCKED"}', True
        
        # Execute the call
        result = handler()
        
        # Cache the result
        self.set_cache(tool_name, args, result)
        
        return result, False
    
    def get_stats(self) -> dict[str, Any]:
        """Get optimization statistics."""
        return {
            "cache": self._cache.get_stats(),
            "dedup": self._dedup.get_stats(),
        }
    
    def clear_cache(self) -> None:
        """Clear all cached results."""
        self._cache.clear()


# Singleton
_optimizer: ToolCallOptimizer | None = None


def get_tool_optimizer() -> ToolCallOptimizer:
    """Get the singleton tool optimizer instance."""
    global _optimizer
    if _optimizer is None:
        _optimizer = ToolCallOptimizer()
    return _optimizer


def optimize_tool_call(
    tool_name: str,
    args: dict[str, Any],
    handler: Callable[[], str],
) -> tuple[str, bool]:
    """Convenience function to optimize a tool call."""
    return get_tool_optimizer().optimize_call(tool_name, args, handler)