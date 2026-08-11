"""Type safety utilities with runtime validation.

Provides:
- Tool parameter validation using pydantic
- MCP message validation
- Structured error types for validation failures
- ValidationResult for functional validation

These utilities add runtime type safety to:
1. Tool call parameters (preventing malformed tool invocations)
2. MCP message format (ensuring protocol compliance)
3. API inputs (validating before processing)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar

from butler.core.effects import Result, Ok, Err

T = TypeVar("T")
E = TypeVar("E")


@dataclass
class ValidationError:
    """Structured validation error.

    Provides detailed information about validation failures,
    including the field that failed and the reason.

    Attributes:
        field: The field that failed validation.
        message: Human-readable error description.
        value: The invalid value.
        constraint: The constraint that was violated.
        code: Machine-readable error code.
    """

    field: str = ""
    message: str = ""
    value: Any = None
    constraint: str = ""
    code: str = "VALIDATION_ERROR"

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "message": self.message,
            "value": repr(self.value),
            "constraint": self.constraint,
            "code": self.code,
        }

    def __str__(self) -> str:
        return f"[{self.code}] {self.field}: {self.message}"


@dataclass
class ValidationResult(Generic[T]):
    """Result of a validation operation.

    Wraps the validated value or a list of errors,
    following the Result monad pattern.

    Attributes:
        value: The validated value (if valid).
        errors: List of validation errors (if invalid).
        is_valid: Whether validation passed.
    """

    value: T | None = None
    errors: list[ValidationError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0 and self.value is not None

    @property
    def is_invalid(self) -> bool:
        return len(self.errors) > 0

    def to_result(self) -> Result[T, list[ValidationError]]:
        """Convert to a Result type."""
        if self.is_valid:
            return Ok(self.value)  # type: ignore[return-value]
        return Err(self.errors)

    @classmethod
    def valid(cls, value: T) -> "ValidationResult[T]":
        """Create a valid result."""
        return cls(value=value, errors=[])

    @classmethod
    def invalid(cls, errors: list[ValidationError]) -> "ValidationResult[T]":
        """Create an invalid result."""
        return cls(value=None, errors=errors)


class ToolParamValidator:
    """Validates tool call parameters against a schema.

    Supports both pydantic models and plain dict-based schemas
    for maximum flexibility.

    Example:
        from pydantic import BaseModel

        class WriteParams(BaseModel):
            path: str
            content: str
            append: bool = False

        validator = ToolParamValidator(WriteParams)
        result = validator.validate({"path": "/tmp/test.txt", "content": "hello"})
        if result.is_valid:
            process(result.value)
    """

    def __init__(self, schema: type | dict[str, Any]) -> None:
        self._schema = schema

    def validate(self, params: dict[str, Any]) -> ValidationResult[Any]:
        """Validate parameters against the schema.

        Args:
            params: The parameters to validate.

        Returns:
            ValidationResult containing the validated value or errors.
        """
        if isinstance(self._schema, dict):
            return self._validate_dict_schema(params)
        else:
            return self._validate_pydantic(params)

    def _validate_dict_schema(
        self, params: dict[str, Any]
    ) -> ValidationResult[dict[str, Any]]:
        """Validate against a dict-based schema."""
        errors: list[ValidationError] = []
        schema = self._schema

        # Check required fields
        required = schema.get("required", [])
        for field_name in required:
            if field_name not in params:
                errors.append(
                    ValidationError(
                        field=field_name,
                        message=f"Required field '{field_name}' is missing",
                        constraint="required",
                        code="FIELD_REQUIRED",
                    )
                )

        # Check field types
        properties = schema.get("properties", {})
        for field_name, field_value in params.items():
            if field_name in properties:
                expected_type = properties[field_name].get("type", "")
                type_valid = self._check_type(field_value, expected_type)
                if not type_valid:
                    errors.append(
                        ValidationError(
                            field=field_name,
                            message=f"Field '{field_name}' should be {expected_type}, got {type(field_value).__name__}",
                            value=field_value,
                            constraint=expected_type,
                            code="TYPE_MISMATCH",
                        )
                    )

        if errors:
            return ValidationResult.invalid(errors)
        return ValidationResult.valid(params)

    def _validate_pydantic(
        self, params: dict[str, Any]
    ) -> ValidationResult[Any]:
        """Validate using a pydantic model."""
        try:
            import pydantic

            if not hasattr(self._schema, "model_validate"):
                # Fallback for older pydantic versions
                if hasattr(self._schema, "parse_obj"):
                    instance = self._schema.parse_obj(params)
                else:
                    instance = self._schema(**params)
            else:
                instance = self._schema.model_validate(params)
            return ValidationResult.valid(instance)
        except ImportError:
            return ValidationResult.invalid([
                ValidationError(
                    field="",
                    message="pydantic is not installed",
                    code="IMPORT_ERROR",
                )
            ])
        except Exception as e:
            errors = self._extract_pydantic_errors(e)
            return ValidationResult.invalid(errors)

    def _check_type(self, value: Any, expected_type: Any) -> bool:
        """Check if a value matches the expected type."""
        if isinstance(expected_type, list):
            # Handle union types like ["string", "integer"]
            type_map: dict[str, tuple[type, ...]] = {
                "string": (str,),
                "integer": (int,),
                "number": (int, float),
                "boolean": (bool,),
                "array": (list,),
                "object": (dict,),
                "null": (type(None),),
            }
            for t in expected_type:
                types = type_map.get(t, ())
                if types and isinstance(value, types):
                    return True
            return False

        type_map: dict[str, tuple[type, ...]] = {
            "string": (str,),
            "integer": (int,),
            "number": (int, float),
            "boolean": (bool,),
            "array": (list,),
            "object": (dict,),
            "null": (type(None),),
        }
        types = type_map.get(expected_type, ())
        if not types:
            return True  # Unknown type, skip check
        return isinstance(value, types)

    def _extract_pydantic_errors(
        self, error: Exception
    ) -> list[ValidationError]:
        """Extract errors from a pydantic validation error."""
        errors: list[ValidationError] = []

        # Try to extract structured errors
        if hasattr(error, "errors"):
            for err in error.errors():
                loc = ".".join(str(l) for l in err.get("loc", []))
                errors.append(
                    ValidationError(
                        field=loc,
                        message=err.get("msg", str(error)),
                        value=err.get("input"),
                        constraint=err.get("type", ""),
                        code="PYDANTIC_ERROR",
                    )
                )
        elif hasattr(error, "args") and error.args:
            errors.append(
                ValidationError(
                    field="",
                    message=str(error),
                    code="VALIDATION_ERROR",
                )
            )
        else:
            errors.append(
                ValidationError(
                    field="",
                    message=str(error),
                    code="UNKNOWN_ERROR",
                )
            )

        return errors


class MCPMessageValidator:
    """Validates MCP (Model Context Protocol) messages.

    Ensures messages conform to the expected protocol format
    before processing.

    Supports:
    - Request validation (method, params)
    - Response validation (result, error)
    - Notification validation
    """

    def __init__(self) -> None:
        self._request_schema = {
            "type": "object",
            "required": ["jsonrpc", "method"],
            "properties": {
                "jsonrpc": {"type": "string"},
                "method": {"type": "string"},
                "params": {"type": "object"},
                "id": {"type": ["string", "integer"]},
            },
        }
        self._response_schema = {
            "type": "object",
            "required": ["jsonrpc", "id"],
            "properties": {
                "jsonrpc": {"type": "string"},
                "id": {"type": ["string", "integer"]},
                "result": {},
                "error": {"type": "object"},
            },
        }
        self._notification_schema = {
            "type": "object",
            "required": ["jsonrpc", "method"],
            "properties": {
                "jsonrpc": {"type": "string"},
                "method": {"type": "string"},
                "params": {"type": "object"},
            },
        }

    def validate_request(
        self, message: dict[str, Any]
    ) -> ValidationResult[dict[str, Any]]:
        """Validate an MCP request message."""
        validator = ToolParamValidator(self._request_schema)
        result = validator.validate(message)

        if result.is_valid and message.get("jsonrpc") != "2.0":
            return ValidationResult.invalid([
                ValidationError(
                    field="jsonrpc",
                    message="JSON-RPC version must be 2.0",
                    constraint="2.0",
                    code="VERSION_MISMATCH",
                )
            ])

        return result

    def validate_response(
        self, message: dict[str, Any]
    ) -> ValidationResult[dict[str, Any]]:
        """Validate an MCP response message."""
        validator = ToolParamValidator(self._response_schema)
        return validator.validate(message)

    def validate_notification(
        self, message: dict[str, Any]
    ) -> ValidationResult[dict[str, Any]]:
        """Validate an MCP notification."""
        # Notifications must not have an id
        if "id" in message:
            return ValidationResult.invalid([
                ValidationError(
                    field="id",
                    message="Notifications must not have an id",
                    constraint="no_id",
                    code="INVALID_NOTIFICATION",
                )
            ])
        validator = ToolParamValidator(self._notification_schema)
        return validator.validate(message)

    def validate_tool_call(
        self, call_id: str, tool_name: str, arguments: str | dict[str, Any]
    ) -> ValidationResult[dict[str, Any]]:
        """Validate a tool call structure.

        Args:
            call_id: The tool call ID.
            tool_name: Name of the tool being called.
            arguments: Tool arguments as JSON string or dict.

        Returns:
            ValidationResult with parsed arguments.
        """
        errors: list[ValidationError] = []

        if not call_id:
            errors.append(
                ValidationError(
                    field="call_id",
                    message="Tool call ID cannot be empty",
                    code="EMPTY_ID",
                )
            )

        if not tool_name:
            errors.append(
                ValidationError(
                    field="tool_name",
                    message="Tool name cannot be empty",
                    code="EMPTY_TOOL_NAME",
                )
            )

        # Parse arguments
        parsed_args: dict[str, Any] = {}
        if isinstance(arguments, str):
            try:
                parsed_args = json.loads(arguments)
            except json.JSONDecodeError as e:
                errors.append(
                    ValidationError(
                        field="arguments",
                        message=f"Invalid JSON: {e}",
                        value=arguments[:100],
                        code="INVALID_JSON",
                    )
                )
        elif isinstance(arguments, dict):
            parsed_args = arguments
        else:
            errors.append(
                ValidationError(
                    field="arguments",
                    message=f"Arguments must be str or dict, got {type(arguments).__name__}",
                    code="TYPE_ERROR",
                )
            )

        if errors:
            return ValidationResult.invalid(errors)
        return ValidationResult.valid(parsed_args)


def validate_with_schema(
    value: Any,
    schema: dict[str, Any] | type,
) -> ValidationResult[Any]:
    """Validate a value against a schema.

    Convenience function for one-off validations.
    """
    validator = ToolParamValidator(schema)
    return validator.validate(value)


__all__ = [
    # Error types
    "ValidationError",
    "ValidationResult",
    # Validators
    "ToolParamValidator",
    "MCPMessageValidator",
    # Utilities
    "validate_with_schema",
]
