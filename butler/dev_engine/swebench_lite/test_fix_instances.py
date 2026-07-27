from __future__ import annotations

from .models import SWEInstance


def _test_fix_instances() -> list[SWEInstance]:
    return [
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
    ]