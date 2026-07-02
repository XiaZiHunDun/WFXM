"""Tests for butler.core.tool_result_classification."""

import json

import pytest

from butler.core.tool_result_classification import (
    file_mutation_result_landed,
    mutation_result_not_landed,
)


@pytest.mark.unit
class TestFileMutationLanded:
    def test_write_file_bytes(self):
        result = json.dumps({"success": True, "path": "a.py", "bytes": 12})
        assert file_mutation_result_landed("write_file", result) is True

    def test_write_file_missing_proof(self):
        result = json.dumps({"success": True, "path": "a.py"})
        assert file_mutation_result_landed("write_file", result) is False
        assert mutation_result_not_landed("write_file", result) is True

    def test_patch_success(self):
        result = json.dumps({"success": True, "replacements": 1, "path": "a.py"})
        assert file_mutation_result_landed("patch", result) is True

    def test_patch_error_not_landed(self):
        result = json.dumps({"error": "old_string not found"})
        assert file_mutation_result_landed("patch", result) is False
        assert mutation_result_not_landed("patch", result) is False

    def test_delete_file(self):
        result = json.dumps({"success": True, "action": "deleted", "path": "a.py"})
        assert file_mutation_result_landed("delete_file", result) is True

    def test_read_file_ignored(self):
        assert file_mutation_result_landed("read_file", '{"content": "x"}') is False
