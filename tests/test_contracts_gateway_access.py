"""Tests for OwnerGate + BridgeAccess contracts (R1 续)."""

from __future__ import annotations

from butler.contracts.bridge_access import BridgeAccess
from butler.contracts.gateway_registry import (
    get_bridge_access,
    get_owner_gate,
    set_bridge_access,
    set_owner_gate,
)
from butler.contracts.owner_gate import OwnerGate
from butler.gateway.gateway_contracts import register_gateway_contracts


class _RecordingOwnerGate:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def is_gateway_owner(
        self,
        *,
        platform: str,
        external_id: str | None = None,
        session_key: str = "",
    ) -> bool:
        self.calls.append(
            {
                "platform": platform,
                "external_id": external_id,
                "session_key": session_key,
            }
        )
        return platform == "wechat" and external_id == "owner-1"

    def owner_required_message(self) -> str:
        return "owner only"


class _RecordingBridgeAccess:
    def __init__(self) -> None:
        self.bridge = object()
        self.pushes: list[tuple[str, str]] = []

    def get_optional_bridge(self):
        return self.bridge

    def try_push_workflow_failure(
        self,
        workflow_name: str,
        error: Exception | str,
        *,
        session_key: str = "",
    ) -> bool:
        self.pushes.append((workflow_name, str(error)))
        return True


def test_owner_gate_protocol_shape():
    gate: OwnerGate = _RecordingOwnerGate()
    assert gate.is_gateway_owner(platform="wechat", external_id="owner-1")
    assert isinstance(gate, OwnerGate)


def test_bridge_access_protocol_shape():
    access: BridgeAccess = _RecordingBridgeAccess()
    assert access.get_optional_bridge() is not None
    assert access.try_push_workflow_failure("wf", "err", session_key="sk")
    assert isinstance(access, BridgeAccess)


def test_gateway_registry_roundtrip():
    gate = _RecordingOwnerGate()
    access = _RecordingBridgeAccess()
    set_owner_gate(gate)
    set_bridge_access(access)
    try:
        assert get_owner_gate() is gate
        assert get_bridge_access() is access
    finally:
        set_owner_gate(None)
        set_bridge_access(None)


def test_register_gateway_contracts():
    set_owner_gate(None)
    set_bridge_access(None)
    register_gateway_contracts()
    try:
        assert get_owner_gate() is not None
        assert get_bridge_access() is not None
        assert isinstance(get_owner_gate(), OwnerGate)
        assert isinstance(get_bridge_access(), BridgeAccess)
    finally:
        set_owner_gate(None)
        set_bridge_access(None)


def test_execution_context_prefers_registry(monkeypatch):
    gate = _RecordingOwnerGate()
    access = _RecordingBridgeAccess()
    set_owner_gate(gate)
    set_bridge_access(access)
    try:
        from butler.execution_context import (
            get_current_turn_bridge,
            is_current_turn_owner,
            owner_required_message,
            try_push_current_turn_workflow_failure,
        )

        assert is_current_turn_owner(platform="wechat", external_id="owner-1") is True
        assert is_current_turn_owner(platform="wechat", external_id="other") is False
        assert owner_required_message() == "owner only"
        assert get_current_turn_bridge() is access.bridge
        assert try_push_current_turn_workflow_failure("demo", "boom", session_key="sk") is True
        assert access.pushes == [("demo", "boom")]
    finally:
        set_owner_gate(None)
        set_bridge_access(None)


def test_execution_context_registry_wins_over_gateway_fallback(monkeypatch):
    monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
    gate = _RecordingOwnerGate()
    set_owner_gate(gate)
    try:
        from butler.execution_context import is_current_turn_owner

        assert is_current_turn_owner(platform="wechat", external_id="other") is False
        assert gate.calls
    finally:
        set_owner_gate(None)
