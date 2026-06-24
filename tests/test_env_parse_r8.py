"""R8 env_parse helpers: init_dotenv, int_env, float_env, deploy env."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


def test_config_module_has_no_import_time_load_dotenv():
    src = Path("butler/config.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if not isinstance(node, ast.Expr):
            continue
        call = node.value
        if isinstance(call, ast.Call) and getattr(call.func, "id", None) == "load_dotenv":
            pytest.fail("butler/config.py must not call load_dotenv() at import time")


def test_init_dotenv_skipped_under_pytest(monkeypatch):
    import butler.env_parse as ep

    ep._dotenv_loaded = False
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_env_parse_r8.py::test")
    ep.init_dotenv()
    assert ep._dotenv_loaded is True


def test_int_env_invalid_falls_back(monkeypatch, caplog):
    from butler.env_parse import int_env

    monkeypatch.setenv("BUTLER_TEST_INT_FOO", "abc")
    assert int_env("BUTLER_TEST_INT_FOO", 7, min=1, max=10) == 7
    assert "invalid" in caplog.text.lower()


def test_int_env_empty_uses_default(monkeypatch):
    from butler.env_parse import int_env

    monkeypatch.setenv("BUTLER_TEST_INT_EMPTY", "")
    assert int_env("BUTLER_TEST_INT_EMPTY", 42) == 42


def test_float_env_clamp_warns(monkeypatch, caplog):
    from butler.env_parse import float_env

    monkeypatch.setenv("BUTLER_TEST_FLOAT_CLAMP", "1.5")
    assert float_env("BUTLER_TEST_FLOAT_CLAMP", 0.75, min=0.5, max=0.95) == 0.95
    assert "clamp" in caplog.text.lower()


def test_env_truthy_default_true(monkeypatch):
    from butler.env_parse import env_truthy

    monkeypatch.delenv("BUTLER_TEST_TRUTHY_UNSET", raising=False)
    assert env_truthy("BUTLER_TEST_TRUTHY_UNSET", default=True) is True
    monkeypatch.setenv("BUTLER_TEST_TRUTHY_UNSET", "0")
    assert env_truthy("BUTLER_TEST_TRUTHY_UNSET", default=True) is False


def test_is_butler_prod_unknown_strict(monkeypatch, caplog):
    from butler.env_parse import is_butler_prod

    monkeypatch.setenv("BUTLER_ENV", "weird")
    assert is_butler_prod() is True
    assert "unknown" in caplog.text.lower()


def test_is_butler_prod_dev_not_prod(monkeypatch):
    from butler.env_parse import is_butler_prod

    monkeypatch.setenv("BUTLER_ENV", "dev")
    assert is_butler_prod() is False


def test_float_env_invalid_falls_back(monkeypatch, caplog):
    from butler.env_parse import float_env

    monkeypatch.setenv("BUTLER_TEST_FLOAT_FOO", "not-a-number")
    assert float_env("BUTLER_TEST_FLOAT_FOO", 2.5) == 2.5
    assert "invalid" in caplog.text.lower()


def test_no_raw_float_getenv_in_butler():
    import subprocess

    try:
        subprocess.run(["rg", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("ripgrep not installed")

    out = subprocess.run(
        ["rg", "float\\(os\\.getenv", "butler/", "-l"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 1, f"raw float(os.getenv) remains:\n{out.stdout}"
