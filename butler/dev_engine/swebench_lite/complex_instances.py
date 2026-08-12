from __future__ import annotations

from .models import SWEInstance


def _complex_instances() -> list[SWEInstance]:
    return [
        SWEInstance(
            instance_id="SWE-013",
            category="bug_fix",
            repo_name="api",
            issue_title="API response missing status field",
            issue_body="make_response should include 'status' in the returned dict.",
            files={
                "api/response.py": """\
                    def make_response(data, code=200):
                        return {
                            "data": data,
                            "code": code,
                        }
                """,
                "api/__init__.py": "",
            },
            oracle_patch={
                "api/response.py": (
                    '"code": code,\n    }',
                    '"code": code,\n        "status": "ok" if code < 400 else "error",\n    }',
                ),
            },
            test_code="""\
import sys, os
sys.path.insert(0, os.getcwd())
from api.response import make_response

def test_success_response():
    r = make_response({"id": 1})
    assert r["status"] == "ok"
    assert r["code"] == 200

def test_error_response():
    r = make_response(None, 404)
    assert r["status"] == "error"
""",
            difficulty="medium",
            tags=["api", "missing-field"],
        ),
        SWEInstance(
            instance_id="SWE-014",
            category="feature",
            repo_name="events",
            issue_title="Add event listener unsubscribe",
            issue_body="EventBus.on() should return an unsubscribe function.",
            files={
                "events.py": """\
                    class EventBus:
                        def __init__(self):
                            self._listeners = {}

                        def on(self, event, callback):
                            if event not in self._listeners:
                                self._listeners[event] = []
                            self._listeners[event].append(callback)

                        def emit(self, event, *args):
                            for cb in self._listeners.get(event, []):
                                cb(*args)
                """,
            },
            oracle_patch={
                "events.py": (
                    "self._listeners[event].append(callback)",
                    "self._listeners[event].append(callback)\n\n        def unsubscribe():\n            try:\n                self._listeners[event].remove(callback)\n            except (KeyError, ValueError):\n                pass\n\n        return unsubscribe",
                ),
            },
            test_code="""\
import sys, os
sys.path.insert(0, os.getcwd())
from events import EventBus

def test_subscribe_emit():
    bus = EventBus()
    results = []
    bus.on('test', lambda x: results.append(x))
    bus.emit('test', 42)
    assert results == [42]

def test_unsubscribe():
    bus = EventBus()
    results = []
    unsub = bus.on('test', lambda x: results.append(x))
    bus.emit('test', 1)
    unsub()
    bus.emit('test', 2)
    assert results == [1]
""",
            difficulty="medium",
            tags=["event-bus", "unsubscribe"],
        ),
        SWEInstance(
            instance_id="SWE-015",
            category="bug_fix",
            repo_name="queue",
            issue_title="Priority queue pops in wrong order",
            issue_body="PriorityQueue should pop highest priority first (lower number = higher priority).",
            files={
                "priority_queue.py": """\
                    class PriorityQueue:
                        def __init__(self):
                            self._items = []

                        def push(self, item, priority=0):
                            self._items.append((priority, item))

                        def pop(self):
                            if not self._items:
                                raise IndexError("Queue is empty")
                            self._items.sort()
                            return self._items.pop()[1]

                        def __len__(self):
                            return len(self._items)
                """,
            },
            oracle_patch={
                "priority_queue.py": ("self._items.sort()\n        return self._items.pop()[1]",
                             "self._items.sort()\n        return self._items.pop(0)[1]"),
            },
            test_code="""\
import sys, os
sys.path.insert(0, os.getcwd())
from priority_queue import PriorityQueue

def test_priority_order():
    pq = PriorityQueue()
    pq.push("low", 10)
    pq.push("high", 1)
    pq.push("mid", 5)
    assert pq.pop() == "high"
    assert pq.pop() == "mid"
    assert pq.pop() == "low"
""",
            difficulty="medium",
            tags=["priority-queue", "sort-order"],
        ),
    ]
