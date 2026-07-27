from __future__ import annotations

from .models import SWEInstance


def _bug_fix_instances() -> list[SWEInstance]:
    return [
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
    ]