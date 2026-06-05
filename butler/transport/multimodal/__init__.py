"""Butler multimodal transport — image generation, TTS, and similar LLM-backed media APIs.

Audit R1-10 [H] layering_violation: the LLM provider clients
(``minimax_image_gen``, ``minimax_tts``) historically lived under
``butler/gateway/`` even though they are pure outbound API calls with no
gateway state — they belong in ``transport/`` alongside other provider
clients (``chat_completions``, ``anthropic_transport``).

The previous ``butler.gateway.minimax_image_gen`` and
``butler.gateway.minimax_tts`` paths are kept as thin re-export shims for
backward compatibility.
"""

from __future__ import annotations

__all__: list[str] = []
