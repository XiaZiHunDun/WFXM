"""Backward-compatible re-export of :mod:`butler.transport.multimodal.minimax_image_gen`.

Audit R1-10 [H] layering_violation: the implementation moved to
``butler.transport.multimodal`` because it is a pure outbound LLM
provider call (no gateway state). This shim preserves the historical
``from butler.gateway.minimax_image_gen import generate_image`` import
path for existing callers (other gateway modules, tests).

New code should import from :mod:`butler.transport.multimodal.minimax_image_gen`.
"""

from __future__ import annotations

from butler.transport.multimodal.minimax_image_gen import generate_image

__all__ = ["generate_image"]
