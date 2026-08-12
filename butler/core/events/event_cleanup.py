"""Event cleanup and archival utilities.

Provides:
- EventRetentionPolicy: Configuration for event retention
- EventCleanupService: Cleanup expired events based on policy
- EventArchiver: Archive old events to compressed storage
"""

from __future__ import annotations

import gzip
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class EventRetentionPolicy:
    """Configuration for event retention and cleanup.

    Attributes:
        max_age_days: Maximum age of events in days before archival
        archive_after_days: Age threshold for archival (None = no archival)
        max_events_per_session: Maximum events per session before forced cleanup
        archive_batch_size: Number of sessions to process per archival run
        auto_cleanup: Enable automatic cleanup on append
        cleanup_interval_hours: How often to run cleanup (in hours)
    """

    max_age_days: int = 30
    archive_after_days: int = 90
    max_events_per_session: int = 10000
    archive_batch_size: int = 100
    auto_cleanup: bool = False
    cleanup_interval_hours: float = 24.0

    @classmethod
    def from_env(cls) -> "EventRetentionPolicy":
        """Create policy from environment variables."""
        return cls(
            max_age_days=int(os.getenv("BUTLER_EVENT_MAX_AGE_DAYS", "30")),
            archive_after_days=int(os.getenv("BUTLER_EVENT_ARCHIVE_DAYS", "90")),
            max_events_per_session=int(
                os.getenv("BUTLER_EVENT_MAX_PER_SESSION", "10000")
            ),
            archive_batch_size=int(os.getenv("BUTLER_EVENT_ARCHIVE_BATCH", "100")),
            auto_cleanup=os.getenv("BUTLER_EVENT_AUTO_CLEANUP", "").lower()
            in ("1", "true", "yes", "on"),
            cleanup_interval_hours=float(
                os.getenv("BUTLER_EVENT_CLEANUP_INTERVAL", "24")
            ),
        )


class EventArchiver:
    """Archive old events to compressed storage.

    Moves expired events from the active store to compressed archive files.
    Supports incremental archiving with cursor tracking.
    """

    def __init__(
        self,
        base_dir: str | Path | None = None,
        archive_dir: str | Path | None = None,
    ) -> None:
        if base_dir is None:
            base_dir = Path.home() / ".butler" / "events"
        if archive_dir is None:
            archive_dir = Path.home() / ".butler" / "events_archive"

        self._base_dir = Path(base_dir)
        self._archive_dir = Path(archive_dir)
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        self._cursor_file = self._archive_dir / ".archive_cursor"

    def _get_archive_path(self, session_key: str) -> Path:
        """Get the archive path for a session."""
        safe_key = session_key.replace(":", "_").replace("/", "_")
        date_str = datetime.now().strftime("%Y%m")
        return self._archive_dir / f"{safe_key}_{date_str}.jsonl.gz"

    def archive_session(self, session_key: str) -> int:
        """Archive all events for a session and remove from active store.

        Returns the number of events archived.
        """
        active_file = self._base_dir / f"{session_key.replace(':', '_')}.jsonl"
        if not active_file.exists():
            return 0

        # Read all events
        events = []
        with open(active_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(line)

        if not events:
            active_file.unlink()
            return 0

        # Write to compressed archive
        archive_path = self._get_archive_path(session_key)
        with gzip.open(archive_path, "at", encoding="utf-8") as f:
            for event_line in events:
                f.write(event_line + "\n")

        # Remove active file
        active_file.unlink()

        logger.info(
            "Archived %d events for session %s to %s",
            len(events),
            session_key,
            archive_path.name,
        )
        return len(events)

    def restore_session(self, session_key: str) -> int:
        """Restore a session's events from archive to active store.

        Returns the number of events restored.
        """
        safe_key = session_key.replace(":", "_").replace("/", "_")
        pattern = f"{safe_key}_*.jsonl.gz"

        restored = 0
        for archive_file in sorted(self._archive_dir.glob(pattern)):
            active_file = self._base_dir / f"{safe_key}.jsonl"

            with gzip.open(archive_file, "rt", encoding="utf-8") as gz_file:
                with open(active_file, "a", encoding="utf-8") as active_out:
                    for line in gz_file:
                        active_out.write(line)
                        restored += 1

            logger.info(
                "Restored %d events for session %s from %s",
                restored,
                session_key,
                archive_file.name,
            )

        return restored

    def list_archives(self) -> list[dict]:
        """List all archived sessions with metadata."""
        archives = []
        for archive_file in sorted(self._archive_dir.glob("*.jsonl.gz")):
            # Parse session key from filename
            parts = archive_file.stem.replace(".gz", "").split("_")
            if len(parts) >= 2:
                session_key = parts[0]
                for i in range(1, len(parts)):
                    if parts[i].isdigit() and len(parts[i]) == 6:
                        session_key = "_".join(parts[:i])
                        break

            # Count events in archive
            event_count = 0
            try:
                with gzip.open(archive_file, "rt", encoding="utf-8") as f:
                    event_count = sum(1 for line in f if line.strip())
            except Exception:
                pass

            archives.append({
                "session_key": session_key,
                "file": archive_file.name,
                "size_bytes": archive_file.stat().st_size,
                "event_count": event_count,
                "modified": datetime.fromtimestamp(
                    archive_file.stat().st_mtime
                ).isoformat(),
            })

        return archives

    def get_archive_size(self) -> int:
        """Get total size of all archives in bytes."""
        total = 0
        for f in self._archive_dir.glob("*.jsonl.gz"):
            total += f.stat().st_size
        return total


class EventCleanupService:
    """Service for cleaning up old events based on retention policy.

    Supports both manual and automatic cleanup with configurable policies.
    """

    def __init__(
        self,
        base_dir: str | Path | None = None,
        policy: EventRetentionPolicy | None = None,
    ) -> None:
        if base_dir is None:
            base_dir = Path.home() / ".butler" / "events"

        self._base_dir = Path(base_dir)
        self._policy = policy or EventRetentionPolicy.from_env()
        self._archiver = EventArchiver(base_dir=base_dir)
        self._last_cleanup = 0.0

    @property
    def policy(self) -> EventRetentionPolicy:
        return self._policy

    @policy.setter
    def policy(self, value: EventRetentionPolicy) -> None:
        self._policy = value

    def _should_run_cleanup(self) -> bool:
        """Check if cleanup should run based on interval."""
        if not self._policy.auto_cleanup:
            return False

        interval_seconds = self._policy.cleanup_interval_hours * 3600
        return (time.time() - self._last_cleanup) >= interval_seconds

    def cleanup_expired_sessions(self, force: bool = False) -> dict:
        """Archive and remove expired sessions.

        Args:
            force: Force cleanup regardless of interval

        Returns:
            Summary of cleanup operations
        """
        if not force and not self._should_run_cleanup():
            return {"status": "skipped", "reason": "interval_not_reached"}

        cutoff_date = datetime.now() - timedelta(days=self._policy.max_age_days)
        sessions_processed = 0
        events_archived = 0
        events_cleaned = 0

        # Get all session files
        session_files = sorted(
            self._base_dir.glob("*.jsonl"),
            key=lambda f: f.stat().st_mtime,
        )

        for session_file in session_files:
            if sessions_processed >= self._policy.archive_batch_size:
                break

            try:
                mtime = datetime.fromtimestamp(session_file.stat().st_mtime)

                # Check if session is expired
                if mtime < cutoff_date:
                    session_key = session_file.stem.replace("_", ":")

                    # Archive if old enough
                    archive_cutoff = datetime.now() - timedelta(
                        days=self._policy.archive_after_days
                    )
                    if mtime < archive_cutoff:
                        count = self._archiver.archive_session(session_key)
                        events_archived += count
                    else:
                        # Just remove the old events (truncate)
                        with open(session_file, "r", encoding="utf-8") as f:
                            lines = f.readlines()

                        # Keep only recent events
                        keep_lines = lines[-self._policy.max_events_per_session:]
                        events_cleaned += len(lines) - len(keep_lines)

                        with open(session_file, "w", encoding="utf-8") as f:
                            f.writelines(keep_lines)

                sessions_processed += 1

            except Exception as e:
                logger.error("Error processing %s: %s", session_file, e)

        self._last_cleanup = time.time()

        return {
            "status": "completed",
            "sessions_processed": sessions_processed,
            "events_archived": events_archived,
            "events_cleaned": events_cleaned,
            "archived_size_bytes": self._archiver.get_archive_size(),
        }

    def check_session_size(self, session_key: str) -> dict:
        """Check if a session needs cleanup based on size.

        Returns cleanup recommendation.
        """
        session_file = self._base_dir / f"{session_key.replace(':', '_')}.jsonl"
        if not session_file.exists():
            return {"session": session_key, "status": "not_found"}

        # Count events
        event_count = 0
        with open(session_file, "r", encoding="utf-8") as f:
            event_count = sum(1 for line in f if line.strip())

        needs_cleanup = event_count > self._policy.max_events_per_session

        return {
            "session": session_key,
            "event_count": event_count,
            "max_events": self._policy.max_events_per_session,
            "needs_cleanup": needs_cleanup,
            "file_size_bytes": session_file.stat().st_size,
        }

    def cleanup_oversized_session(self, session_key: str) -> dict:
        """Force cleanup of an oversized session."""
        check = self.check_session_size(session_key)
        if not check.get("needs_cleanup"):
            return {"status": "skipped", "reason": "not_oversized"}

        session_file = self._base_dir / f"{session_key.replace(':', '_')}.jsonl"
        max_events = self._policy.max_events_per_session

        with open(session_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Keep the most recent events
        keep_lines = lines[-max_events:]
        removed_count = len(lines) - len(keep_lines)

        with open(session_file, "w", encoding="utf-8") as f:
            f.writelines(keep_lines)

        return {
            "status": "completed",
            "session": session_key,
            "removed_events": removed_count,
            "kept_events": len(keep_lines),
        }

    def get_storage_stats(self) -> dict:
        """Get storage statistics for event files."""
        active_sessions = list(self._base_dir.glob("*.jsonl"))
        active_size = sum(f.stat().st_size for f in active_sessions)

        return {
            "active_sessions_count": len(active_sessions),
            "active_events_size_bytes": active_size,
            "active_events_size_kb": active_size / 1024,
            "archive_sessions_count": len(list(self._archiver._archive_dir.glob("*.jsonl.gz"))),
            "archive_size_bytes": self._archiver.get_archive_size(),
            "last_cleanup": datetime.fromtimestamp(self._last_cleanup).isoformat()
            if self._last_cleanup > 0
            else None,
            "policy": {
                "max_age_days": self._policy.max_age_days,
                "archive_after_days": self._policy.archive_after_days,
                "max_events_per_session": self._policy.max_events_per_session,
            },
        }


__all__ = [
    "EventRetentionPolicy",
    "EventArchiver",
    "EventCleanupService",
]
