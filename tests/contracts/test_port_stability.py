"""契约测试套件：验证 butler/contracts/ Port 接口稳定性。

这些测试确保 AI 工具修改代码时不会破坏已有的接口契约。
每个 Port 接口都有对应的测试，验证：
1. Protocol 类定义存在且可导入
2. 方法签名（参数名、类型）不变
3. __all__ 导出列表完整
4. runtime_checkable 装饰器存在（如适用）
"""

from __future__ import annotations

import inspect
import importlib
from pathlib import Path

import pytest

from butler.contracts import (
    BridgeAccess,
    ContextTransformPort,
    DevVerifyView,
    DevReviewView,
    LoopDevStateView,
    EvalSuitePort,
    EventsSink,
    HookContextView,
    LoopApiMessageView,
    LoopCompactionView,
    LoopMemoryView,
    OwnerGate,
    ScoreSinkPort,
    SuiteRunResult,
    TransformContext,
    get_bridge_access,
    get_events_sink,
    get_owner_gate,
    set_bridge_access,
    set_events_sink,
    set_owner_gate,
)

# 项目根目录：tests/contracts/test_port_stability.py → 上溯三级到项目根
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONTRACTS_DIR = REPO_ROOT / "butler" / "contracts"


# === 契约：__init__.py 导出列表稳定性 ===

EXPECTED_EXPORTS = {
    "BridgeAccess",
    "ContextTransformPort",
    "DevVerifyView",
    "DevReviewView",
    "LoopDevStateView",
    "EvalSuitePort",
    "EventsSink",
    "HookContextView",
    "LoopApiMessageView",
    "LoopCompactionView",
    "LoopMemoryView",
    "OwnerGate",
    "ScoreSinkPort",
    "SuiteRunResult",
    "TransformContext",
    "get_bridge_access",
    "get_events_sink",
    "get_owner_gate",
    "hook_context_view_schema_json",
    "dev_verify_view_schema_json",
    "dev_review_view_schema_json",
    "loop_dev_state_view_schema_json",
    "loop_compaction_view_schema_json",
    "loop_memory_view_schema_json",
    "loop_api_message_view_schema_json",
    "set_bridge_access",
    "set_events_sink",
    "set_owner_gate",
}


def test_contracts_all_exports_present():
    """contracts.__init__.py 的 __all__ 必须包含所有预期导出。"""
    import butler.contracts as contracts_mod
    actual = set(contracts_mod.__all__)
    missing = EXPECTED_EXPORTS - actual
    extra = actual - EXPECTED_EXPORTS
    assert not missing, f"contracts.__init__.__all__ 缺少导出: {missing}"
    assert not extra, f"contracts.__init__.__all__ 有多余导出: {extra}"


# === 契约：Port Protocol 类有 runtime_checkable ===

PORT_PROTOCOLS = [
    "ToolDispatchPort",
    "ContextTransformPort",
    "EvalSuitePort",
    "ScoreSinkPort",
]


@pytest.mark.parametrize("port_name", PORT_PROTOCOLS)
def test_port_protocol_is_runtime_checkable(port_name: str):
    """Port Protocol 必须有 @runtime_checkable 装饰器。"""
    found = False
    for py_file in CONTRACTS_DIR.glob("*.py"):
        if py_file.stem == "__init__":
            continue
        try:
            mod = importlib.import_module(f"butler.contracts.{py_file.stem}")
        except ImportError:
            continue
        if hasattr(mod, port_name):
            cls = getattr(mod, port_name)
            # runtime_checkable Protocol 有 __protocol_attrs__
            assert hasattr(cls, "__protocol_attrs__"), (
                f"{port_name} in {py_file.name} 不是 @runtime_checkable Protocol"
            )
            found = True
            break
    if not found:
        pytest.skip(f"Port {port_name} not found in contracts/")


# === 契约：Port 方法签名稳定性 ===

EXPECTED_METHODS = {
    "ToolDispatchPort": ["dispatch_one_tool"],
    "OwnerGate": ["is_gateway_owner", "owner_required_message"],
    "BridgeAccess": ["get_optional_bridge", "try_push_workflow_failure"],
    "EventsSink": [
        "record_generic_event",
        "record_tool_action",
        "invoke_hook",
        "emit_context_compaction",
        "pop_urgent_inbound",
    ],
}


@pytest.mark.parametrize("port_name,expected_methods", EXPECTED_METHODS.items())
def test_port_methods_exist(port_name: str, expected_methods: list[str]):
    """Port 必须包含所有预期方法。"""
    found = False
    for py_file in CONTRACTS_DIR.glob("*.py"):
        if py_file.stem == "__init__":
            continue
        mod_name = f"butler.contracts.{py_file.stem}"
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        if hasattr(mod, port_name):
            cls = getattr(mod, port_name)
            for method_name in expected_methods:
                assert hasattr(cls, method_name), (
                    f"{port_name} 缺少方法 {method_name}"
                )
            found = True
            break
    if not found:
        pytest.skip(f"Port {port_name} not found")


# === 契约：Registry 函数签名 ===

REGISTRY_FUNCTIONS = {
    "get_bridge_access": [],
    "set_bridge_access": ["access"],
    "get_owner_gate": [],
    "set_owner_gate": ["gate"],
    "get_events_sink": [],
    "set_events_sink": ["sink"],
}


@pytest.mark.parametrize("func_name,expected_params", REGISTRY_FUNCTIONS.items())
def test_registry_function_signature(func_name: str, expected_params: list[str]):
    """Registry 函数签名必须稳定。"""
    func = globals()[func_name]
    sig = inspect.signature(func)
    actual_params = [
        p for p in sig.parameters
        if p != "self" and not p.startswith("*")
    ]
    assert actual_params == expected_params, (
        f"{func_name} 签名变化: 期望参数 {expected_params}, 实际 {actual_params}"
    )


# === 契约：Port 文件清单完整性 ===

EXPECTED_PORT_FILES = [
    "approval_ports.py",
    "compaction_ports.py",
    "completion_ports.py",
    "context_transform_ports.py",
    "dev_context_ports.py",
    "dev_state_ports.py",
    "eval_ports.py",
    "gateway_registry.py",
    "health_diagnostic_ports.py",
    "hook_context_ports.py",
    "inbound_idempotency_ports.py",
    "memory_ports.py",
    "message_ports.py",
    "review_ports.py",
    "tool_dispatch_ports.py",
    "tool_registry_ports.py",
    "workflow_gate_ports.py",
]


@pytest.mark.parametrize("filename", EXPECTED_PORT_FILES)
def test_port_file_exists(filename: str):
    """Port 文件必须存在。"""
    assert (CONTRACTS_DIR / filename).exists(), (
        f"契约文件 {filename} 不存在 — 可能被误删或重命名"
    )


# === 契约：tool_dispatch_ports.py 接口稳定性 ===

def test_tool_dispatch_port_signature():
    """ToolDispatchPort.dispatch_one_tool 方法签名必须稳定。"""
    from butler.contracts.tool_dispatch_ports import ToolDispatchPort
    sig = inspect.signature(ToolDispatchPort.dispatch_one_tool)
    params = list(sig.parameters.keys())
    expected = ["self", "name", "args", "tool_call_id", "batch_guard", "prefetched", "guardrails", "dispatch_tool"]
    assert params == expected, (
        f"ToolDispatchPort.dispatch_one_tool 签名变化: 期望 {expected}, 实际 {params}"
    )
