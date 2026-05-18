"""Repair and retry logic for malformed LLM tool call outputs.

Domestic LLMs often produce:
- Incomplete JSON (missing brackets/quotes)
- Missing required parameters
- Wrong parameter types
- Tool calls embedded in text rather than structured output
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

MAX_REPAIR_ATTEMPTS = 2


def repair_json(broken: str) -> dict | None:
    """Attempt to repair broken JSON from LLM output."""
    # Strategy 1: direct parse
    try:
        return json.loads(broken)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", broken.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 3: fix common issues
    fixed = broken
    # Fix trailing commas
    fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
    # Fix single quotes to double quotes
    fixed = re.sub(r"(?<=[{,:\[])\s*'([^']*?)'\s*(?=[},:\]])", r'"\1"', fixed)
    # Fix unquoted keys
    fixed = re.sub(r"(?<=[{,])\s*(\w+)\s*:", r'"\1":', fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Strategy 4: extract JSON object from surrounding text
    brace_start = fixed.find("{")
    if brace_start >= 0:
        depth = 0
        for i in range(brace_start, len(fixed)):
            if fixed[i] == "{":
                depth += 1
            elif fixed[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(fixed[brace_start : i + 1])
                    except json.JSONDecodeError:
                        break

    # Strategy 5: fix unclosed brackets
    open_braces = fixed.count("{") - fixed.count("}")
    open_brackets = fixed.count("[") - fixed.count("]")
    if open_braces > 0 or open_brackets > 0:
        fixed = fixed.rstrip()
        fixed += "]" * max(0, open_brackets) + "}" * max(0, open_braces)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    return None


def extract_tool_calls_from_text(text: str) -> list[dict]:
    """Extract tool call intentions from freeform text when model fails structured output."""
    # Look for patterns like: 使用 tool_name(param=value) or call tool_name with {"key": "val"}
    calls = []

    # Pattern: tool_name({"key": "value"})
    pattern = r"(\w+)\s*\(\s*(\{[^}]+\})\s*\)"
    for match in re.finditer(pattern, text):
        name = match.group(1)
        try:
            args = json.loads(match.group(2))
            calls.append({"name": name, "arguments": args})
        except json.JSONDecodeError:
            pass

    return calls


def build_retry_prompt(tool_name: str, error: str, original_args: dict | None = None) -> str:
    """Build a correction prompt when tool call parsing fails."""
    parts = [f"你上次对工具 `{tool_name}` 的调用存在格式问题：{error}"]

    if original_args:
        parts.append(f"你尝试传递的参数（部分解析）: {json.dumps(original_args, ensure_ascii=False)[:500]}")

    parts.append(
        "请重新生成正确的工具调用。确保：\n"
        "1. 所有必填参数都已提供\n"
        "2. JSON 格式正确（双引号、无尾逗号）\n"
        "3. 参数类型正确（string/integer/boolean）"
    )
    return "\n".join(parts)


def validate_tool_call(
    tool_name: str,
    arguments: dict,
    tool_schema: dict | None = None,
) -> tuple[bool, str]:
    """Validate a tool call against its schema. Returns (valid, error_message)."""
    if not isinstance(arguments, dict):
        return False, f"参数必须是 JSON 对象，收到: {type(arguments).__name__}"

    if tool_schema is None:
        return True, ""

    params = tool_schema.get("function", {}).get("parameters", {})
    required = params.get("required", [])
    properties = params.get("properties", {})

    # Check required params
    missing = [r for r in required if r not in arguments]
    if missing:
        return False, f"缺少必填参数: {', '.join(missing)}"

    # Check types (basic)
    for key, value in arguments.items():
        if key in properties:
            expected_type = properties[key].get("type")
            if expected_type == "string" and not isinstance(value, str):
                arguments[key] = str(value)  # auto-coerce
            elif expected_type == "integer" and isinstance(value, str):
                try:
                    arguments[key] = int(value)
                except ValueError:
                    return False, f"参数 '{key}' 应为整数，收到: {value!r}"
            elif expected_type == "boolean" and isinstance(value, str):
                arguments[key] = value.lower() in ("true", "1", "yes")

    return True, ""
