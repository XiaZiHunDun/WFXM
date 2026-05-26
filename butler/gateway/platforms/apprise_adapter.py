"""Multi-channel notification adapter via apprise (optional extra [notify])."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_APPRISE_OBJ: Any = None
_APPRISE_TRIED = False


def _notify_urls() -> list[str]:
    """Parse BUTLER_NOTIFY_URLS (comma-separated apprise URL strings)."""
    raw = (os.getenv("BUTLER_NOTIFY_URLS", "") or "").strip()
    if not raw:
        return []
    return [u.strip() for u in raw.split(",") if u.strip()]


def apprise_enabled() -> bool:
    """True when apprise is installed AND at least one notify URL is configured."""
    if not _notify_urls():
        return False
    try:
        import apprise  # type: ignore[import-untyped]  # noqa: F401
        return True
    except ImportError:
        return False


def _get_apprise() -> Any:
    """Lazily create and cache the apprise.Apprise instance."""
    global _APPRISE_OBJ, _APPRISE_TRIED
    if _APPRISE_TRIED:
        return _APPRISE_OBJ
    _APPRISE_TRIED = True
    urls = _notify_urls()
    if not urls:
        return None
    try:
        import apprise  # type: ignore[import-untyped]

        ap = apprise.Apprise()
        for url in urls:
            ap.add(url)
        _APPRISE_OBJ = ap
        logger.info("Apprise adapter initialized with %d notify URL(s)", len(urls))
        return ap
    except ImportError:
        logger.debug("apprise not installed; multi-channel notifications disabled")
        return None
    except Exception as exc:
        logger.warning("apprise init failed: %s", exc)
        return None


def send_notification(
    body: str,
    *,
    title: str = "Butler",
    notify_type: str = "info",
) -> bool:
    """Send a notification to all configured apprise channels.

    Returns True if at least one channel succeeded.
    """
    ap = _get_apprise()
    if ap is None:
        return False
    try:
        import apprise as apprise_mod  # type: ignore[import-untyped]

        type_map = {
            "info": apprise_mod.NotifyType.INFO,
            "success": apprise_mod.NotifyType.SUCCESS,
            "warning": apprise_mod.NotifyType.WARNING,
            "failure": apprise_mod.NotifyType.FAILURE,
        }
        nt = type_map.get(notify_type, apprise_mod.NotifyType.INFO)
        result = ap.notify(
            body=body,
            title=title,
            notify_type=nt,
        )
        if result:
            logger.info("Apprise notification sent: title=%r len=%d", title, len(body))
        else:
            logger.warning("Apprise notification returned False")
        return bool(result)
    except Exception as exc:
        logger.warning("Apprise notification failed: %s", exc)
        return False


def reset_apprise() -> None:
    """Reset cached apprise instance (for testing)."""
    global _APPRISE_OBJ, _APPRISE_TRIED
    _APPRISE_OBJ = None
    _APPRISE_TRIED = False


__all__ = ["apprise_enabled", "send_notification", "reset_apprise"]
