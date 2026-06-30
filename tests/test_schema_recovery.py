"""Tests for schema grammar recovery extraction."""

from butler.core.schema_recovery import recover_schema_after_error


def _tool(name: str, params: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": params,
        },
    }


def test_schema_recovery_strips_pattern_and_updates_diagnostics():
    class GrammarError(Exception):
        status_code = 400

    tools = [
        _tool("search", {
            "type": "object",
            "properties": {
                "date": {"type": "string", "pattern": "\\d{4}-\\d{2}-\\d{2}"},
            },
        })
    ]
    diagnostics: dict[str, object] = {}

    result = recover_schema_after_error(
        GrammarError("Unable to generate parser: json schema conversion failed"),
        tools,
        diagnostics=diagnostics,
    )

    assert result.recovered is True
    assert result.stripped == 1
    assert result.tools is not None
    assert "pattern" not in result.tools[0]["function"]["parameters"]["properties"]["date"]
    assert diagnostics["schema_recovered"] is True
    assert diagnostics["schema_keywords_stripped"] == 1


def test_schema_recovery_skips_non_grammar_errors():
    result = recover_schema_after_error(RuntimeError("rate limit"), [{"type": "function"}])

    assert result.recovered is False
    assert result.attempted is False
    assert result.tools is None
    assert result.stripped == 0


def test_schema_recovery_attempts_sanitize_even_without_pattern_format():
    class GrammarError(Exception):
        status_code = 400

    tools = [
        _tool("search", {
            "type": "object",
            "properties": {
                "maybe": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            },
        })
    ]

    result = recover_schema_after_error(
        GrammarError("Unable to generate parser: json schema conversion failed"),
        tools,
    )

    assert result.attempted is True
    assert result.recovered is True  # sanitize collapsed anyOf → grammar-safe shape
    assert result.stripped == 0
    assert result.tools is not None
    assert result.tools[0]["function"]["parameters"]["properties"]["maybe"]["type"] == "string"
