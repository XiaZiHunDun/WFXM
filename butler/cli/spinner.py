"""Simple terminal spinner for LLM wait (stdout-safe)."""

from __future__ import annotations

import sys
import threading
import time

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class WaitSpinner:
    """Background spinner; disabled when stdout is prompt_toolkit proxy."""

    def __init__(self) -> None:
        self._active = False
        self._label = ""
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._start_time = 0.0

    @staticmethod
    def _can_spin() -> bool:
        stdout = sys.stdout
        mod = type(stdout).__module__
        if "patch_stdout" in mod or "StdoutProxy" in type(stdout).__name__:
            return False
        return sys.stdout.isatty()

    def start(self, label: str = "思考中") -> None:
        self.stop()
        if not self._can_spin():
            return
        self._label = label
        self._active = True
        self._stop.clear()
        self._start_time = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        i = 0
        while not self._stop.wait(0.12):
            if not self._active:
                break
            frame = _FRAMES[i % len(_FRAMES)]
            elapsed = time.monotonic() - self._start_time
            sys.stdout.write(f"\r  {frame} {self._label} ({elapsed:.1f}s)")
            sys.stdout.flush()
            i += 1
        sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()

    def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None
