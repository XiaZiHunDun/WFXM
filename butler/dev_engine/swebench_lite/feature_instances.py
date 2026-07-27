from __future__ import annotations

from .models import SWEInstance


def _feature_instances() -> list[SWEInstance]:
    return [
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
    ]