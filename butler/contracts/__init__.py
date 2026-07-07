"""Cross-layer Protocol contracts (ENG-6 / P1-D / R1 续).

Sink / gate protocols:

* :class:`EventsSink` — unified transcript + compaction hooks + urgent inbound
  (``butler.core.events_sink`` re-exports contracts registry shims)
* :class:`OwnerGate` — owner-only WeChat / gateway checks
* :class:`BridgeAccess` — outbound bridge lookup + workflow failure push

Gateway :class:`butler.gateway.events_sink_impl.GatewayEventsSink` implements
:class:`EventsSink`; ``register_gateway_events_sink()`` wires the contracts
registry. ``register_gateway_contracts()`` wires OwnerGate + BridgeAccess.
"""

from butler.contracts.bridge_access import BridgeAccess
from butler.contracts.compaction_ports import LoopCompactionView, loop_compaction_view_schema_json
from butler.contracts.dev_context_ports import DevVerifyView, dev_verify_view_schema_json
from butler.contracts.dev_state_ports import LoopDevStateView, loop_dev_state_view_schema_json
from butler.contracts.memory_ports import LoopMemoryView, loop_memory_view_schema_json
from butler.contracts.message_ports import LoopApiMessageView, loop_api_message_view_schema_json
from butler.contracts.review_ports import DevReviewView, dev_review_view_schema_json
from butler.contracts.context_transform_ports import (
    ContextTransformPort,
    TransformContext,
)
from butler.contracts.eval_ports import EvalSuitePort, ScoreSinkPort, SuiteRunResult
from butler.contracts.hook_context_ports import HookContextView, hook_context_view_schema_json
from butler.contracts.events import EventsSink
from butler.contracts.gateway_registry import (
    get_bridge_access,
    get_owner_gate,
    set_bridge_access,
    set_owner_gate,
)
from butler.contracts.owner_gate import OwnerGate
from butler.contracts.sink_registry import get_events_sink, set_events_sink

import butler.contracts.approval_store_impl as _approval_store_impl  # noqa: F401 — register ApprovalStore

__all__ = [
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
]
