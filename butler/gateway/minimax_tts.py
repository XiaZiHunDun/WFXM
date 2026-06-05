"""Backward-compatible re-export of :mod:`butler.transport.multimodal.minimax_tts`.

Audit R1-10 [H] layering_violation: the implementation moved to
``butler.transport.multimodal`` because it is a pure outbound LLM
provider call (no gateway state). This shim preserves the historical
``from butler.gateway.minimax_tts import synthesize_speech`` import path
for existing callers (other gateway modules, tests).

New code should import from :mod:`butler.transport.multimodal.minimax_tts`.
"""

from __future__ import annotations

from butler.transport.multimodal.minimax_tts import synthesize_speech

__all__ = ["synthesize_speech"]
