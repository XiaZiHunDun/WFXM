from __future__ import annotations

from .models import SWEInstance


def _refactor_instances() -> list[SWEInstance]:
    return [
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
    ]