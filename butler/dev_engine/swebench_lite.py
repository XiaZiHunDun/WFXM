"""SWE-bench Lite adapted benchmark — local instances for Butler DevEngine.

Extracts 15 representative instances from SWE-bench Lite categories,
adapted to exercise Butler's PLAN→LOCATE→EDIT→VERIFY pipeline without
requiring the full SWE-bench harness or Docker containers.

Each instance defines:
  - A simulated repository (files to create)
  - A GitHub-style issue description
  - Expected patch (the oracle fix)
  - Verification command (pytest-compatible assertion)

Categories (from SWE-bench Lite):
  - Bug fix: off-by-one, type error, edge case, null handling
  - Feature: add parameter, add method, extend API
  - Refactor: rename, extract, consolidate
  - Test fix: update assertion, add missing test case
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SWEInstance:
    """A single SWE-bench-style benchmark instance."""

    instance_id: str
    category: str
    repo_name: str
    issue_title: str
    issue_body: str
    files: dict[str, str]
    oracle_patch: dict[str, tuple[str, str]]
    test_code: str
    difficulty: str = "easy"
    tags: list[str] = field(default_factory=list)

    def setup_workspace(self, workspace: Path) -> None:
        """Create the simulated repository files in workspace."""
        for rel_path, content in self.files.items():
            fp = workspace / rel_path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(textwrap.dedent(content), encoding="utf-8")

    def apply_oracle(self, workspace: Path) -> None:
        """Apply the oracle patch to solve the issue."""
        for rel_path, (old, new) in self.oracle_patch.items():
            fp = workspace / rel_path
            text = fp.read_text(encoding="utf-8")
            fp.write_text(text.replace(old, new), encoding="utf-8")

    def verify(self, workspace: Path) -> bool:
        """Run the test code and return pass/fail."""
        test_file = workspace / "_swe_test.py"
        test_file.write_text(self.test_code, encoding="utf-8")
        import subprocess
        result = subprocess.run(
            ["python", "-m", "pytest", str(test_file), "-q", "--tb=short"],
            capture_output=True, text=True, cwd=str(workspace), timeout=30,
        )
        return result.returncode == 0


# ── Instance definitions ──

def _instances() -> list[SWEInstance]:
    """Return all SWE-bench Lite adapted instances."""
    return [
        # ── Bug Fixes ──
        SWEInstance(
            instance_id="SWE-001",
            category="bug_fix",
            repo_name="utils",
            issue_title="Off-by-one in range_inclusive",
            issue_body="range_inclusive(1, 5) returns [1,2,3,4] but should include 5.",
            files={
                "utils.py": """\
                    def range_inclusive(start, end):
                        return list(range(start, end))
                """,
            },
            oracle_patch={
                "utils.py": ("range(start, end)", "range(start, end + 1)"),
            },
            test_code="""\
import sys, os
sys.path.insert(0, os.getcwd())
from utils import range_inclusive

def test_range_inclusive():
    assert range_inclusive(1, 5) == [1, 2, 3, 4, 5]

def test_range_inclusive_single():
    assert range_inclusive(3, 3) == [3]
""",
            difficulty="easy",
            tags=["off-by-one", "boundary"],
        ),
        SWEInstance(
            instance_id="SWE-002",
            category="bug_fix",
            repo_name="validator",
            issue_title="TypeError when validating None input",
            issue_body="validate_email(None) raises TypeError instead of returning False.",
            files={
                "validator.py": """\
                    import re

                    def validate_email(email):
                        pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+$'
                        return bool(re.match(pattern, email))
                """,
            },
            oracle_patch={
                "validator.py": (
                    "return bool(re.match(pattern, email))",
                    "if email is None:\n        return False\n    return bool(re.match(pattern, email))",
                ),
            },
            test_code="""\
import sys, os
sys.path.insert(0, os.getcwd())
from validator import validate_email

def test_none_input():
    assert validate_email(None) is False

def test_valid_email():
    assert validate_email("user@example.com") is True

def test_invalid_email():
    assert validate_email("not-an-email") is False
""",
            difficulty="easy",
            tags=["null-handling", "type-safety"],
        ),
        SWEInstance(
            instance_id="SWE-003",
            category="bug_fix",
            repo_name="parser",
            issue_title="CSV parser fails on empty lines",
            issue_body="parse_csv crashes with IndexError when input has empty lines.",
            files={
                "parser.py": """\
                    def parse_csv(text, delimiter=','):
                        rows = []
                        for line in text.strip().split('\\n'):
                            rows.append(line.split(delimiter))
                        return rows
                """,
            },
            oracle_patch={
                "parser.py": (
                    "rows.append(line.split(delimiter))",
                    "if line.strip():\n            rows.append(line.split(delimiter))",
                ),
            },
            test_code="""\
import sys, os
sys.path.insert(0, os.getcwd())
from parser import parse_csv

def test_normal():
    result = parse_csv("a,b\\nc,d")
    assert result == [["a", "b"], ["c", "d"]]

def test_empty_lines():
    result = parse_csv("a,b\\n\\nc,d\\n")
    assert result == [["a", "b"], ["c", "d"]]
""",
            difficulty="easy",
            tags=["edge-case", "empty-input"],
        ),
        SWEInstance(
            instance_id="SWE-004",
            category="bug_fix",
            repo_name="math_utils",
            issue_title="Division by zero in calculate_average",
            issue_body="calculate_average([]) raises ZeroDivisionError.",
            files={
                "math_utils.py": """\
                    def calculate_average(numbers):
                        return sum(numbers) / len(numbers)
                """,
            },
            oracle_patch={
                "math_utils.py": (
                    "return sum(numbers) / len(numbers)",
                    "if not numbers:\n        return 0.0\n    return sum(numbers) / len(numbers)",
                ),
            },
            test_code="""\
import sys, os
sys.path.insert(0, os.getcwd())
from math_utils import calculate_average

def test_empty():
    assert calculate_average([]) == 0.0

def test_normal():
    assert calculate_average([1, 2, 3]) == 2.0
""",
            difficulty="easy",
            tags=["division-by-zero", "edge-case"],
        ),
        SWEInstance(
            instance_id="SWE-005",
            category="bug_fix",
            repo_name="string_utils",
            issue_title="truncate doesn't handle multi-byte chars",
            issue_body="truncate('你好世界', 2) should return '你好...' not crash.",
            files={
                "string_utils.py": """\
                    def truncate(text, max_chars, suffix='...'):
                        if len(text) <= max_chars:
                            return text
                        return text[:max_chars] + suffix
                """,
            },
            oracle_patch={
                "string_utils.py": (
                    "if len(text) <= max_chars:",
                    "if not text or max_chars <= 0:\n        return suffix if text else ''\n    if len(text) <= max_chars:",
                ),
            },
            test_code="""\
import sys, os
sys.path.insert(0, os.getcwd())
from string_utils import truncate

def test_chinese():
    assert truncate('你好世界', 2) == '你好...'

def test_short():
    assert truncate('hi', 10) == 'hi'

def test_empty():
    result = truncate('', 5)
    assert result == ''
""",
            difficulty="easy",
            tags=["unicode", "edge-case"],
        ),

        # ── Feature Additions ──
        SWEInstance(
            instance_id="SWE-006",
            category="feature",
            repo_name="config",
            issue_title="Add default parameter to Config.get",
            issue_body="Config.get('key') should accept a default parameter like dict.get.",
            files={
                "config.py": """\
                    class Config:
                        def __init__(self):
                            self._data = {}

                        def set(self, key, value):
                            self._data[key] = value

                        def get(self, key):
                            return self._data[key]
                """,
            },
            oracle_patch={
                "config.py": (
                    "def get(self, key):\n        return self._data[key]",
                    "def get(self, key, default=None):\n        return self._data.get(key, default)",
                ),
            },
            test_code="""\
import sys, os
sys.path.insert(0, os.getcwd())
from config import Config

def test_get_existing():
    c = Config()
    c.set('a', 1)
    assert c.get('a') == 1

def test_get_missing_default():
    c = Config()
    assert c.get('missing', 42) == 42

def test_get_missing_none():
    c = Config()
    assert c.get('missing') is None
""",
            difficulty="easy",
            tags=["api-extension", "default-param"],
        ),
        SWEInstance(
            instance_id="SWE-007",
            category="feature",
            repo_name="cache",
            issue_title="Add TTL support to SimpleCache",
            issue_body="Cache entries should expire after a configurable TTL.",
            files={
                "cache.py": """\
                    class SimpleCache:
                        def __init__(self):
                            self._store = {}

                        def set(self, key, value):
                            self._store[key] = value

                        def get(self, key):
                            return self._store.get(key)
                """,
            },
            oracle_patch={
                "cache.py": (
                    "class SimpleCache:\n        def __init__(self):\n            self._store = {}",
                    "import time\n\n    class SimpleCache:\n        def __init__(self, default_ttl=0):\n            self._store = {}\n            self._expiry = {}\n            self._default_ttl = default_ttl",
                ),
            },
            test_code="""\
import sys, os, time
sys.path.insert(0, os.getcwd())
from cache import SimpleCache

def test_basic_set_get():
    c = SimpleCache()
    c.set('a', 1)
    assert c.get('a') == 1

def test_missing_key():
    c = SimpleCache()
    assert c.get('x') is None
""",
            difficulty="medium",
            tags=["ttl", "feature-add"],
        ),
        SWEInstance(
            instance_id="SWE-008",
            category="feature",
            repo_name="logger",
            issue_title="Add JSON output format to Logger",
            issue_body="Logger should support format='json' to output structured logs.",
            files={
                "logger.py": """\
                    import datetime

                    class Logger:
                        def __init__(self, name):
                            self.name = name

                        def log(self, level, message):
                            ts = datetime.datetime.now().isoformat()
                            print(f"[{ts}] {level}: {self.name} - {message}")
                """,
            },
            oracle_patch={
                "logger.py": (
                    "def __init__(self, name):\n        self.name = name",
                    "def __init__(self, name, fmt='text'):\n        self.name = name\n        self.fmt = fmt",
                ),
            },
            test_code="""\
import sys, os
sys.path.insert(0, os.getcwd())
from logger import Logger

def test_default_format():
    lg = Logger('test')
    assert lg.name == 'test'

def test_json_format_attr():
    lg = Logger('test', fmt='json')
    assert lg.fmt == 'json'
""",
            difficulty="medium",
            tags=["structured-logging", "format"],
        ),

        # ── Refactoring ──
        SWEInstance(
            instance_id="SWE-009",
            category="refactor",
            repo_name="handlers",
            issue_title="Extract common validation logic",
            issue_body="create_user and update_user duplicate email validation. Extract to validate_email.",
            files={
                "handlers.py": """\
                    import re

                    def create_user(name, email):
                        if not re.match(r'^[\\w.+-]+@[\\w-]+\\.[\\w.]+$', email):
                            raise ValueError("Invalid email")
                        return {"name": name, "email": email, "action": "created"}

                    def update_user(user_id, email):
                        if not re.match(r'^[\\w.+-]+@[\\w-]+\\.[\\w.]+$', email):
                            raise ValueError("Invalid email")
                        return {"id": user_id, "email": email, "action": "updated"}
                """,
            },
            oracle_patch={
                "handlers.py": (
                    "def create_user(name, email):\n        if not re.match(r'^[\\w.+-]+@[\\w-]+\\.[\\w.]+$', email):\n            raise ValueError(\"Invalid email\")",
                    "def _validate_email(email):\n        if not re.match(r'^[\\w.+-]+@[\\w-]+\\.[\\w.]+$', email):\n            raise ValueError(\"Invalid email\")\n\n    def create_user(name, email):\n        _validate_email(email)",
                ),
            },
            test_code="""\
import sys, os, pytest
sys.path.insert(0, os.getcwd())
from handlers import create_user, update_user

def test_create_valid():
    r = create_user("Alice", "alice@test.com")
    assert r["action"] == "created"

def test_create_invalid():
    with pytest.raises(ValueError):
        create_user("Bob", "invalid")

def test_update_valid():
    r = update_user("u1", "bob@test.com")
    assert r["action"] == "updated"
""",
            difficulty="medium",
            tags=["extract-method", "DRY"],
        ),
        SWEInstance(
            instance_id="SWE-010",
            category="refactor",
            repo_name="data",
            issue_title="Rename 'getData' to 'get_data' (PEP8)",
            issue_body="Function names should use snake_case per PEP 8.",
            files={
                "data.py": """\
                    def getData(source):
                        return {"source": source, "items": []}

                    def processData(data):
                        return getData(data["source"])
                """,
            },
            oracle_patch={
                "data.py": ("def getData(", "def get_data("),
            },
            test_code="""\
import sys, os
sys.path.insert(0, os.getcwd())
from data import get_data

def test_get_data():
    r = get_data("test")
    assert r["source"] == "test"
""",
            difficulty="easy",
            tags=["rename", "pep8"],
        ),

        # ── Test Fixes ──
        SWEInstance(
            instance_id="SWE-011",
            category="test_fix",
            repo_name="calculator",
            issue_title="Test expects wrong result for negative multiply",
            issue_body="test_multiply_negative expects 6 but -2*3=-6.",
            files={
                "calculator.py": """\
                    def multiply(a, b):
                        return a * b
                """,
                "test_calculator.py": """\
                    from calculator import multiply

                    def test_multiply_positive():
                        assert multiply(2, 3) == 6

                    def test_multiply_negative():
                        assert multiply(-2, 3) == 6
                """,
            },
            oracle_patch={
                "test_calculator.py": ("== 6\n", "== -6\n"),
            },
            test_code="""\
import sys, os
sys.path.insert(0, os.getcwd())
from calculator import multiply

def test_multiply_positive():
    assert multiply(2, 3) == 6

def test_multiply_negative():
    assert multiply(-2, 3) == -6

def test_multiply_zero():
    assert multiply(0, 5) == 0
""",
            difficulty="easy",
            tags=["test-assertion", "negative"],
        ),
        SWEInstance(
            instance_id="SWE-012",
            category="test_fix",
            repo_name="sorter",
            issue_title="Sorting test fails for empty list",
            issue_body="sort_items([]) should return [] but test expects None.",
            files={
                "sorter.py": """\
                    def sort_items(items):
                        return sorted(items)
                """,
                "test_sorter.py": """\
                    from sorter import sort_items

                    def test_sort_normal():
                        assert sort_items([3, 1, 2]) == [1, 2, 3]

                    def test_sort_empty():
                        assert sort_items([]) is None
                """,
            },
            oracle_patch={
                "test_sorter.py": ("is None", "== []"),
            },
            test_code="""\
import sys, os
sys.path.insert(0, os.getcwd())
from sorter import sort_items

def test_sort_normal():
    assert sort_items([3, 1, 2]) == [1, 2, 3]

def test_sort_empty():
    assert sort_items([]) == []
""",
            difficulty="easy",
            tags=["test-assertion", "empty-list"],
        ),

        # ── Multi-file / Complex ──
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


def get_all_instances() -> list[SWEInstance]:
    """Return all SWE-bench Lite adapted instances."""
    return _instances()


def get_instance(instance_id: str) -> SWEInstance | None:
    """Get a specific instance by ID."""
    for inst in _instances():
        if inst.instance_id == instance_id:
            return inst
    return None


def get_instances_by_category(category: str) -> list[SWEInstance]:
    """Get all instances in a category."""
    return [i for i in _instances() if i.category == category]


def run_oracle_verification(workspace: Path) -> dict[str, Any]:
    """Run all instances with oracle patches and verify they pass.

    Used to validate the benchmark instances themselves.
    Returns summary dict.
    """
    import tempfile

    results: list[dict[str, Any]] = []
    for inst in _instances():
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            inst.setup_workspace(ws)
            inst.apply_oracle(ws)
            from butler.dev_engine.swebench_lite_ops import verify_swebench_instance_safe

            passed, error = verify_swebench_instance_safe(inst, ws)
            if error:
                results.append({
                    "id": inst.instance_id,
                    "passed": False,
                    "error": error,
                })
                continue
            results.append({
                "id": inst.instance_id,
                "category": inst.category,
                "passed": passed,
            })

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / max(1, total),
        "results": results,
    }
