"""Cross-layer Protocol contracts (ENG-6 / P1-D / R1 续).

Sink / gate protocols (do not merge — different lifecycles):

* :class:`EventsSink` — transcript / tool-audit (this module)
* ``butler.core.events_sink.EventsSink`` — compaction hooks + urgent inbound
* :class:`OwnerGate` — owner-only WeChat / gateway checks
* :class:`BridgeAccess` — outbound bridge lookup + workflow failure push

Gateway :class:`butler.gateway.events_sink_impl.GatewayEventsSink` implements
the transcript EventsSink; ``register_gateway_events_sink()`` wires the contracts
registry. ``register_gateway_contracts()`` wires OwnerGate + BridgeAccess.
"""

from butler.contracts.bridge_access import BridgeAccess
from butler.contracts.compaction_ports import LoopCompactionView, loop_compaction_view_schema_json
from butler.contracts.context_transform_ports import (
    ContextTransformPort,
    TransformContext,
)
from butler.contracts.eval_ports import EvalSuitePort, ScoreSinkPort, SuiteRunResult
from butler.contracts.events import EventsSink
from butler.contracts.gateway_registry import (
    get_bridge_access,
    get_owner_gate,
    set_bridge_access,
    set_owner_gate,
)
from butler.contracts.owner_gate import OwnerGate
from butler.contracts.sink_registry import get_events_sink, set_events_sink

__all__ = [
    "BridgeAccess",
    "ContextTransformPort",
    "EvalSuitePort",
    "EventsSink",
    "LoopCompactionView",
    "OwnerGate",
    "ScoreSinkPort",
    "SuiteRunResult",
    "TransformContext",
    "get_bridge_access",
    "get_events_sink",
    "get_owner_gate",
    "loop_compaction_view_schema_json",
    "set_bridge_access",
    "set_events_sink",
    "set_owner_gate",
]
