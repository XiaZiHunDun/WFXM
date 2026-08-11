"""测试 butler.core.validation 模块的验证工具。

覆盖:
- ValidationError 构造与字段
- ValidationResult.valid / invalid
- ToolParamValidator: validate() 正常/异常/类型检查
- ToolParamValidator: schema 支持 string/integer/array/object 类型
- ToolParamValidator: 必填字段验证
- MCPMessageValidator: request/response/notification 格式
- validate_tool_call: 合法与非法结构
- 边界情况: 空参数、额外字段、null 值
"""

from __future__ import annotations

import json
import pytest

from butler.core.validation import (
    ValidationError,
    ValidationResult,
    ToolParamValidator,
    MCPMessageValidator,
    validate_with_schema,
)


# ---------------------------------------------------------------------------
# ValidationError
# ---------------------------------------------------------------------------


class TestValidationError:
    """测试 ValidationError 的构造和字段。"""

    def test_construction_with_defaults(self):
        """使用默认值构造。"""
        err = ValidationError()
        assert err.field == ""
        assert err.message == ""
        assert err.value is None
        assert err.constraint == ""
        assert err.code == "VALIDATION_ERROR"

    def test_construction_with_all_fields(self):
        """使用所有字段构造。"""
        err = ValidationError(
            field="username",
            message="Username is too short",
            value="ab",
            constraint="min_length",
            code="MIN_LENGTH_ERROR",
        )
        assert err.field == "username"
        assert err.message == "Username is too short"
        assert err.value == "ab"
        assert err.constraint == "min_length"
        assert err.code == "MIN_LENGTH_ERROR"

    def test_to_dict(self):
        """to_dict 正确转换为字典。"""
        err = ValidationError(
            field="age",
            message="Must be positive",
            value=-5,
            constraint="positive",
            code="INVALID_AGE",
        )
        d = err.to_dict()
        assert d["field"] == "age"
        assert d["message"] == "Must be positive"
        assert d["value"] == repr(-5)
        assert d["constraint"] == "positive"
        assert d["code"] == "INVALID_AGE"

    def test_str_representation(self):
        """__str__ 输出正确格式。"""
        err = ValidationError(
            field="email",
            message="Invalid format",
            code="FORMAT_ERROR",
        )
        s = str(err)
        assert s == "[FORMAT_ERROR] email: Invalid format"


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


class TestValidationResult:
    """测试 ValidationResult 的 valid/invalid 工厂方法。"""

    def test_valid_creates_valid_result(self):
        """valid() 创建 is_valid 为 True 的结果。"""
        result = ValidationResult.valid(42)
        assert result.is_valid
        assert not result.is_invalid
        assert result.value == 42
        assert result.errors == []

    def test_invalid_creates_invalid_result(self):
        """invalid() 创建 is_valid 为 False 的结果。"""
        errors = [
            ValidationError(field="x", message="error"),
        ]
        result = ValidationResult.invalid(errors)
        assert not result.is_valid
        assert result.is_invalid
        assert result.value is None
        assert len(result.errors) == 1

    def test_is_valid_false_when_errors_present(self):
        """有错误时 is_valid 为 False。"""
        result = ValidationResult(value=42, errors=[ValidationError()])
        assert not result.is_valid

    def test_is_valid_false_when_value_none(self):
        """值为 None 且无错误时 is_valid 为 False。"""
        result = ValidationResult(value=None, errors=[])
        assert not result.is_valid

    def test_is_valid_true_when_value_and_no_errors(self):
        """有值且无错误时 is_valid 为 True。"""
        result = ValidationResult(value=0, errors=[])
        assert result.is_valid

    def test_to_result_ok(self):
        """to_result 对有效值返回 Ok。"""
        result = ValidationResult.valid("hello")
        monad = result.to_result()
        assert monad.is_ok()
        assert monad.unwrap() == "hello"

    def test_to_result_err(self):
        """to_result 对无效值返回 Err。"""
        errors = [ValidationError(field="f", message="bad")]
        result = ValidationResult.invalid(errors)
        monad = result.to_result()
        assert monad.is_err()


# ---------------------------------------------------------------------------
# ToolParamValidator - 基本验证
# ---------------------------------------------------------------------------


@pytest.fixture
def string_schema() -> dict:
    """字符串参数字典 schema。"""
    return {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
        },
    }


@pytest.fixture
def integer_schema() -> dict:
    """整数参数字典 schema。"""
    return {
        "type": "object",
        "required": ["count"],
        "properties": {
            "count": {"type": "integer"},
            "price": {"type": "number"},
        },
    }


@pytest.fixture
def array_schema() -> dict:
    """数组参数字典 schema。"""
    return {
        "type": "object",
        "required": ["items"],
        "properties": {
            "items": {"type": "array"},
            "tags": {"type": "array"},
        },
    }


@pytest.fixture
def object_schema() -> dict:
    """对象参数字典 schema。"""
    return {
        "type": "object",
        "required": ["config"],
        "properties": {
            "config": {"type": "object"},
            "meta": {"type": "object"},
        },
    }


class TestToolParamValidatorBasic:
    """测试 ToolParamValidator 的基本验证功能。"""

    def test_valid_string_params(self, string_schema):
        """正确的字符串参数验证通过。"""
        validator = ToolParamValidator(string_schema)
        result = validator.validate({"name": "test", "description": "a test"})
        assert result.is_valid

    def test_missing_required_field(self, string_schema):
        """缺少必填字段时验证失败。"""
        validator = ToolParamValidator(string_schema)
        result = validator.validate({"description": "no name"})
        assert not result.is_valid
        assert result.is_invalid
        assert any(e.code == "FIELD_REQUIRED" for e in result.errors)

    def test_type_mismatch_string(self, string_schema):
        """字符串字段传入整数时类型错误。"""
        validator = ToolParamValidator(string_schema)
        result = validator.validate({"name": 123})
        assert not result.is_valid
        assert any(e.code == "TYPE_MISMATCH" for e in result.errors)

    def test_valid_integer_params(self, integer_schema):
        """正确的整数参数验证通过。"""
        validator = ToolParamValidator(integer_schema)
        result = validator.validate({"count": 10, "price": 9.99})
        assert result.is_valid

    def test_integer_type_check_fails_on_string(self, integer_schema):
        """整数字段传入字符串时类型错误。"""
        validator = ToolParamValidator(integer_schema)
        result = validator.validate({"count": "ten"})
        assert not result.is_valid

    def test_valid_array_params(self, array_schema):
        """正确的数组参数验证通过。"""
        validator = ToolParamValidator(array_schema)
        result = validator.validate({"items": [1, 2, 3], "tags": ["a", "b"]})
        assert result.is_valid

    def test_array_type_check_fails_on_string(self, array_schema):
        """数组字段传入字符串时类型错误。"""
        validator = ToolParamValidator(array_schema)
        result = validator.validate({"items": "not an array"})
        assert not result.is_valid

    def test_valid_object_params(self, object_schema):
        """正确的对象参数验证通过。"""
        validator = ToolParamValidator(object_schema)
        result = validator.validate({"config": {"key": "val"}, "meta": {}})
        assert result.is_valid

    def test_object_type_check_fails_on_string(self, object_schema):
        """对象字段传入字符串时类型错误。"""
        validator = ToolParamValidator(object_schema)
        result = validator.validate({"config": "not an object"})
        assert not result.is_valid

    def test_multiple_errors(self, string_schema):
        """多个验证错误同时存在。"""
        validator = ToolParamValidator(string_schema)
        result = validator.validate({"name": 123})
        # name 字段类型错误 + 缺少必填字段?
        # 实际上 name 不在 params 中 (只有 name: 123) ，但类型不对
        assert not result.is_valid

    def test_boolean_type(self):
        """布尔类型验证。"""
        schema = {
            "type": "object",
            "required": ["enabled"],
            "properties": {
                "enabled": {"type": "boolean"},
            },
        }
        validator = ToolParamValidator(schema)
        result = validator.validate({"enabled": True})
        assert result.is_valid

        result = validator.validate({"enabled": "yes"})
        assert not result.is_valid


# ---------------------------------------------------------------------------
# ToolParamValidator - 边界情况
# ---------------------------------------------------------------------------


class TestToolParamValidatorEdgeCases:
    """测试 ToolParamValidator 的边界情况。"""

    def test_empty_params_with_required(self):
        """空参数但有必填字段时验证失败。"""
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
            },
        }
        validator = ToolParamValidator(schema)
        result = validator.validate({})
        assert not result.is_valid
        assert len(result.errors) >= 1

    def test_empty_params_no_required(self):
        """空参数且无必填字段时验证通过。"""
        schema = {
            "type": "object",
            "required": [],
            "properties": {
                "name": {"type": "string"},
            },
        }
        validator = ToolParamValidator(schema)
        result = validator.validate({})
        assert result.is_valid

    def test_extra_fields_allowed(self, string_schema):
        """额外字段不影响验证通过。"""
        validator = ToolParamValidator(string_schema)
        result = validator.validate({
            "name": "test",
            "extra_field": "should be fine",
        })
        assert result.is_valid

    def test_null_value_handling(self, string_schema):
        """null 值被视为有效 (类型检查通过)。"""
        validator = ToolParamValidator(string_schema)
        # null 对于 string 类型，isinstance(None, str) 为 False，应该失败
        result = validator.validate({"name": None})
        assert not result.is_valid

    def test_unknown_type_skipped(self):
        """未知类型跳过检查。"""
        schema = {
            "type": "object",
            "required": ["data"],
            "properties": {
                "data": {"type": "custom_type"},
            },
        }
        validator = ToolParamValidator(schema)
        result = validator.validate({"data": "anything"})
        assert result.is_valid  # 未知类型跳过检查

    def test_union_type(self):
        """联合类型检查。"""
        schema = {
            "type": "object",
            "required": ["value"],
            "properties": {
                "value": {"type": ["string", "integer"]},
            },
        }
        validator = ToolParamValidator(schema)
        assert validator.validate({"value": "hello"}).is_valid
        assert validator.validate({"value": 42}).is_valid
        assert not validator.validate({"value": [1, 2]}).is_valid


# ---------------------------------------------------------------------------
# MCPMessageValidator
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_validator() -> MCPMessageValidator:
    """MCPMessageValidator 实例。"""
    return MCPMessageValidator()


class TestMCPMessageValidator:
    """测试 MCPMessageValidator 的 request/response/notification。"""

    # --- Request ---

    def test_valid_request(self, mcp_validator):
        """合法的请求消息验证通过。"""
        result = mcp_validator.validate_request({
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": "1",
            "params": {},
        })
        assert result.is_valid

    def test_valid_request_with_integer_id(self, mcp_validator):
        """使用整数 ID 的请求验证通过。"""
        result = mcp_validator.validate_request({
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 42,
        })
        assert result.is_valid

    def test_request_missing_method(self, mcp_validator):
        """缺少 method 字段时验证失败。"""
        result = mcp_validator.validate_request({
            "jsonrpc": "2.0",
            "id": "1",
        })
        assert not result.is_valid

    def test_request_missing_jsonrpc(self, mcp_validator):
        """缺少 jsonrpc 字段时验证失败。"""
        result = mcp_validator.validate_request({
            "method": "tools/list",
            "id": "1",
        })
        assert not result.is_valid

    def test_request_wrong_jsonrpc_version(self, mcp_validator):
        """jsonrpc 版本不是 2.0 时验证失败。"""
        result = mcp_validator.validate_request({
            "jsonrpc": "1.0",
            "method": "tools/list",
            "id": "1",
        })
        assert not result.is_valid
        assert any(e.code == "VERSION_MISMATCH" for e in result.errors)

    def test_request_method_type_mismatch(self, mcp_validator):
        """method 字段不是字符串时验证失败。"""
        result = mcp_validator.validate_request({
            "jsonrpc": "2.0",
            "method": 123,
            "id": "1",
        })
        assert not result.is_valid

    # --- Response ---

    def test_valid_response(self, mcp_validator):
        """合法的响应消息验证通过。"""
        result = mcp_validator.validate_response({
            "jsonrpc": "2.0",
            "id": "1",
            "result": {"ok": True},
        })
        assert result.is_valid

    def test_response_with_error(self, mcp_validator):
        """包含错误的响应验证通过 (error 字段为对象)。"""
        result = mcp_validator.validate_response({
            "jsonrpc": "2.0",
            "id": "1",
            "error": {"code": -1, "message": "error"},
        })
        assert result.is_valid

    def test_response_missing_id(self, mcp_validator):
        """缺少 id 字段时验证失败。"""
        result = mcp_validator.validate_response({
            "jsonrpc": "2.0",
            "result": "ok",
        })
        assert not result.is_valid

    def test_response_missing_jsonrpc(self, mcp_validator):
        """缺少 jsonrpc 字段时验证失败。"""
        result = mcp_validator.validate_response({
            "id": "1",
            "result": "ok",
        })
        assert not result.is_valid

    # --- Notification ---

    def test_valid_notification(self, mcp_validator):
        """合法的通知消息验证通过 (无 id)。"""
        result = mcp_validator.validate_notification({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        })
        assert result.is_valid

    def test_notification_with_id_rejected(self, mcp_validator):
        """通知消息包含 id 时验证失败。"""
        result = mcp_validator.validate_notification({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "id": "1",
        })
        assert not result.is_valid
        assert any(e.code == "INVALID_NOTIFICATION" for e in result.errors)

    def test_notification_missing_method(self, mcp_validator):
        """通知缺少 method 字段时验证失败。"""
        result = mcp_validator.validate_notification({
            "jsonrpc": "2.0",
        })
        assert not result.is_valid

    def test_notification_missing_jsonrpc(self, mcp_validator):
        """通知缺少 jsonrpc 字段时验证失败。"""
        result = mcp_validator.validate_notification({
            "method": "notifications/initialized",
        })
        assert not result.is_valid


# ---------------------------------------------------------------------------
# validate_tool_call
# ---------------------------------------------------------------------------


class TestValidateToolCall:
    """测试 validate_tool_call 的合法与非法结构。"""

    def test_valid_tool_call_with_dict_args(self):
        """使用字典参数的合法工具调用。"""
        validator = MCPMessageValidator()
        result = validator.validate_tool_call(
            call_id="call_001",
            tool_name="read_file",
            arguments={"path": "/tmp/test.txt"},
        )
        assert result.is_valid
        assert result.value == {"path": "/tmp/test.txt"}

    def test_valid_tool_call_with_json_string(self):
        """使用 JSON 字符串参数的合法工具调用。"""
        validator = MCPMessageValidator()
        result = validator.validate_tool_call(
            call_id="call_002",
            tool_name="write_file",
            arguments=json.dumps({"path": "/tmp/test.txt", "content": "hello"}),
        )
        assert result.is_valid
        assert result.value == {"path": "/tmp/test.txt", "content": "hello"}

    def test_empty_call_id_rejected(self):
        """空 call_id 验证失败。"""
        validator = MCPMessageValidator()
        result = validator.validate_tool_call(
            call_id="",
            tool_name="read_file",
            arguments={},
        )
        assert not result.is_valid
        assert any(e.code == "EMPTY_ID" for e in result.errors)

    def test_empty_tool_name_rejected(self):
        """空 tool_name 验证失败。"""
        validator = MCPMessageValidator()
        result = validator.validate_tool_call(
            call_id="call_001",
            tool_name="",
            arguments={},
        )
        assert not result.is_valid
        assert any(e.code == "EMPTY_TOOL_NAME" for e in result.errors)

    def test_invalid_json_arguments(self):
        """参数为非法 JSON 字符串时验证失败。"""
        validator = MCPMessageValidator()
        result = validator.validate_tool_call(
            call_id="call_001",
            tool_name="read_file",
            arguments="not valid json {{{",
        )
        assert not result.is_valid
        assert any(e.code == "INVALID_JSON" for e in result.errors)

    def test_wrong_arguments_type(self):
        """参数类型既不是 str 也不是 dict 时验证失败。"""
        validator = MCPMessageValidator()
        result = validator.validate_tool_call(
            call_id="call_001",
            tool_name="read_file",
            arguments=12345,  # type: ignore[arg-type]
        )
        assert not result.is_valid
        assert any(e.code == "TYPE_ERROR" for e in result.errors)

    def test_empty_dict_args(self):
        """空字典参数验证通过。"""
        validator = MCPMessageValidator()
        result = validator.validate_tool_call(
            call_id="call_001",
            tool_name="ping",
            arguments={},
        )
        assert result.is_valid

    def test_multiple_errors_in_tool_call(self):
        """call_id 和 tool_name 都为空时产生多个错误。"""
        validator = MCPMessageValidator()
        result = validator.validate_tool_call(
            call_id="",
            tool_name="",
            arguments={},
        )
        assert not result.is_valid
        assert len(result.errors) >= 2

    def test_empty_json_string_args(self):
        """空字符串参数解析后为空对象。"""
        validator = MCPMessageValidator()
        result = validator.validate_tool_call(
            call_id="call_001",
            tool_name="test",
            arguments="{}",
        )
        assert result.is_valid
        assert result.value == {}


# ---------------------------------------------------------------------------
# validate_with_schema 便捷函数
# ---------------------------------------------------------------------------


class TestValidateWithSchema:
    """测试 validate_with_schema 便捷函数。"""

    def test_validates_correctly(self):
        """便捷函数正确调用验证。"""
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
            },
        }
        result = validate_with_schema({"name": "test"}, schema)
        assert result.is_valid

    def test_fails_on_invalid(self):
        """便捷函数正确检测无效输入。"""
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
            },
        }
        result = validate_with_schema({}, schema)
        assert not result.is_valid