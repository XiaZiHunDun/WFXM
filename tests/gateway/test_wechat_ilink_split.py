"""R1-4 + R1-4a wechat_ilink.py god-module split — backward-compat guard.

Asserts the public API of the original ``wechat_ilink`` module still works
exactly as before, even after extraction of pure constants and pure
utility helpers into sibling modules.

New sibling modules:
- ``butler.gateway.platforms.wechat_ilink_constants`` (URLs / codes / enums)
- ``butler.gateway.platforms.wechat_ilink_utils`` (crypto / CDN / account / parsing)
- ``butler.gateway.platforms.wechat_ilink_phases`` (R1-4a — WeChatAdapter
  god-method phase functions, mirroring the R1-6 / R1-8 pattern)

Backward-compat: every previously-importable symbol must still be reachable
via ``butler.gateway.platforms.wechat_ilink`` (the adapter module).
"""

from __future__ import annotations

import importlib
import inspect

import pytest


WECHAT_ILINK_PATH = "butler.gateway.platforms.wechat_ilink"
WECHAT_ILINK_CONSTANTS_PATH = "butler.gateway.platforms.wechat_ilink_constants"
WECHAT_ILINK_UTILS_PATH = "butler.gateway.platforms.wechat_ilink_utils"
WECHAT_ILINK_PHASES_PATH = "butler.gateway.platforms.wechat_ilink_phases"


@pytest.mark.unit
class TestSplitModulesExist:
    def test_constants_module_exists(self):
        mod = importlib.import_module(WECHAT_ILINK_CONSTANTS_PATH)
        assert mod is not None

    def test_utils_module_exists(self):
        mod = importlib.import_module(WECHAT_ILINK_UTILS_PATH)
        assert mod is not None


@pytest.mark.unit
class TestBackwardCompatSymbols:
    """Symbols that test files and other modules import from wechat_ilink.

    Re-exports must keep them reachable via the original import path so
    test patches and runtime imports stay green.
    """

    @pytest.mark.parametrize(
        "name",
        [
            "WeChatAdapter",
            "SESSION_EXPIRED_ERRCODE",
            "TYPING_START",
            "ITEM_IMAGE",
            "ITEM_TEXT",
            "ITEM_VOICE",
            "ITEM_FILE",
            "ITEM_VIDEO",
            "MEDIA_IMAGE",
            "MEDIA_VIDEO",
            "MEDIA_FILE",
            "MEDIA_VOICE",
            "MSG_TYPE_BOT",
            "MSG_STATE_FINISH",
            "TYPING_STOP",
            "ILINK_BASE_URL",
            "WECHAT_CDN_BASE_URL",
            "EP_GET_UPDATES",
            "EP_SEND_MESSAGE",
            "ContextTokenStore",
            "check_wechat_requirements",
            "qr_login",
            "send_wechat_direct",
        ],
    )
    def test_symbol_importable_from_wechat_ilink(self, name):
        mod = importlib.import_module(WECHAT_ILINK_PATH)
        assert hasattr(mod, name), f"{name} missing from {WECHAT_ILINK_PATH}"

    @pytest.mark.parametrize(
        "name",
        [
            "_extract_text",
            "_assert_wechat_cdn_url",
            "_download_and_decrypt_media",
            "_download_bytes",
            "_account_file",
            "load_wechat_account",
            "save_wechat_account",
            "_make_ssl_connector",
            "_safe_id",
            "_headers",
            "_random_wechat_uin",
        ],
    )
    def test_helper_importable_from_wechat_ilink(self, name):
        mod = importlib.import_module(WECHAT_ILINK_PATH)
        assert hasattr(mod, name), f"{name} missing from {WECHAT_ILINK_PATH}"


@pytest.mark.unit
class TestLiveAdaptersRegistryUntouched:
    """R1-12 owns the live-adapter registry; the dict shape is gone.

    The audit split was intentional: R1-4 (this issue) only relocated
    symbols without touching the registry, and R1-12 later replaced
    ``_LIVE_ADAPTERS: Dict`` with ``_ADAPTER_REGISTRY: AdapterRegistry``.
    This test now locks in the *new* contract: a module-level
    ``_ADAPTER_REGISTRY`` of type :class:`AdapterRegistry` on the
    original import path, with the public methods the R1-4 split
    assumes (``register`` / ``unregister`` / ``get``).
    """

    def test_live_adapters_is_registry(self):
        from butler.gateway.platforms.wechat_ilink_registry import (
            AdapterRegistry,
        )

        mod = importlib.import_module(WECHAT_ILINK_PATH)
        assert isinstance(mod._ADAPTER_REGISTRY, AdapterRegistry)
        # Public surface the 3 call sites rely on:
        for method in ("register", "unregister", "get", "live_count"):
            assert callable(getattr(mod._ADAPTER_REGISTRY, method)), (
                f"_ADAPTER_REGISTRY must expose {method}() for the R1-4 call sites"
            )


@pytest.mark.unit
class TestConstantsModuleContent:
    def test_ilink_base_url_value(self):
        from butler.gateway.platforms.wechat_ilink_constants import ILINK_BASE_URL

        assert ILINK_BASE_URL == "https://ilinkai.weixin.qq.com"

    def test_session_expired_errcode_value(self):
        from butler.gateway.platforms.wechat_ilink_constants import SESSION_EXPIRED_ERRCODE

        assert SESSION_EXPIRED_ERRCODE == -14

    def test_rate_limit_errcode_value(self):
        from butler.gateway.platforms.wechat_ilink_constants import RATE_LIMIT_ERRCODE

        assert RATE_LIMIT_ERRCODE == -2


@pytest.mark.unit
class TestUtilsModuleContent:
    def test_safe_id_truncates(self):
        from butler.gateway.platforms.wechat_ilink_utils import _safe_id

        assert _safe_id("") == "?"
        assert _safe_id("short") == "short"
        assert _safe_id("a-very-long-identifier-1234567890", keep=4) == "a-ve"

    def test_extract_text_plain(self):
        from butler.gateway.platforms.wechat_ilink_constants import ITEM_TEXT
        from butler.gateway.platforms.wechat_ilink_utils import _extract_text

        items = [{"type": ITEM_TEXT, "text_item": {"text": "hello"}}]
        assert _extract_text(items) == "hello"

    def test_assert_wechat_cdn_url_rejects_evil(self):
        from butler.gateway.platforms.wechat_ilink_utils import _assert_wechat_cdn_url

        with pytest.raises(ValueError, match="allowlist"):
            _assert_wechat_cdn_url("https://evil.example.com/x.jpg")

    def test_assert_wechat_cdn_url_accepts_official(self):
        from butler.gateway.platforms.wechat_ilink_utils import _assert_wechat_cdn_url

        _assert_wechat_cdn_url("https://novac2c.cdn.wechat.qq.com/c2c/abc")


# ---------------------------------------------------------------------------
# R1-4a — WeChatAdapter god-method phase split
# ---------------------------------------------------------------------------

import ast as _ast
import pathlib as _pathlib


# The 9 WeChatAdapter god methods that R1-4a must thin to < 50L. Each
# keeps its public/class signature unchanged; the body is reduced to
# thin orchestrators that delegate to phase functions in
# ``wechat_ilink_phases.py``.
WECHAT_GOD_METHODS = [
    "__init__",
    "connect",
    "_poll_loop",
    "_process_message",
    "_send_text_chunk",
    "send",
    "_send_file",
    "_outbound_media_builder",
    # _coerce_list (8L) is below the cap; locked here for back-compat.
    "_coerce_list",
    # _split_text (4L) is a stable helper; locked here for back-compat.
    "_split_text",
]


# Phase functions that the new ``wechat_ilink_phases`` module must export.
# These are the new building blocks the thinned host methods call into.
WECHAT_PHASE_FUNCTIONS = [
    # init sub-phases
    "_phase_init_account",
    "_phase_init_chunks",
    "_phase_init_policies",
    "_phase_init_dedup",
    # connect sub-phases
    "_phase_connect_validate",
    "_phase_connect_open_sessions",
    # poll sub-phases
    "_phase_poll_handle_response",
    # process_message sub-phases
    "_phase_inbound_dedup",
    "_phase_inbound_chat_policy",
    "_phase_inbound_build_event",
    # send_text_chunk sub-phases
    "_phase_chunk_attempt",
    "_phase_chunk_handle_response",
    # send sub-phases
    "_phase_send_attachments",
    "_phase_send_text_chunks",
    # _send_file sub-phases
    "_phase_file_request_upload",
    "_phase_file_dispatch_message",
    # _outbound_media_builder sub-phases
    "_build_image_item",
    "_build_video_item",
    "_build_voice_item",
    "_build_audio_item",
    "_build_file_item",
]


@pytest.mark.unit
class TestR14aPhasesModuleExists:
    """R1-4a introduces ``wechat_ilink_phases.py`` — verify it loads and
    carries the audit-required docstring marker."""

    def test_phases_module_loads(self):
        mod = importlib.import_module(WECHAT_ILINK_PHASES_PATH)
        assert mod is not None

    def test_phases_module_docstring_mentions_r14a(self):
        mod = importlib.import_module(WECHAT_ILINK_PHASES_PATH)
        assert mod.__doc__ and "R1-4a" in mod.__doc__, (
            f"{WECHAT_ILINK_PHASES_PATH} docstring must reference R1-4a audit source"
        )

    def test_phases_module_logger(self):
        mod = importlib.import_module(WECHAT_ILINK_PHASES_PATH)
        assert hasattr(mod, "logger"), (
            f"{WECHAT_ILINK_PHASES_PATH} must define module-level logger"
        )


@pytest.mark.unit
class TestR14aPhaseFunctionsPresent:
    @pytest.mark.parametrize("name", WECHAT_PHASE_FUNCTIONS)
    def test_phase_symbol_present(self, name: str):
        mod = importlib.import_module(WECHAT_ILINK_PHASES_PATH)
        assert hasattr(mod, name), (
            f"{WECHAT_ILINK_PHASES_PATH}.{name} missing — extraction is incomplete"
        )
        assert callable(getattr(mod, name)), (
            f"{WECHAT_ILINK_PHASES_PATH}.{name} must be callable"
        )


@pytest.mark.unit
class TestR14aPhaseFunctionsUnder50Lines:
    """R1-4a size contract: every phase helper must be < 50 source lines."""

    @pytest.mark.parametrize("name", WECHAT_PHASE_FUNCTIONS)
    def test_phase_function_under_50_lines(self, name: str):
        mod = importlib.import_module(WECHAT_ILINK_PHASES_PATH)
        assert hasattr(mod, name), f"{WECHAT_ILINK_PHASES_PATH}.{name} missing"
        fn = getattr(mod, name)
        assert callable(fn), f"{WECHAT_ILINK_PHASES_PATH}.{name} not callable"
        src = inspect.getsource(fn)
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        assert len(body_lines) < 50, (
            f"{WECHAT_ILINK_PHASES_PATH}.{name} is {len(body_lines)} non-blank lines; "
            f"R1-4a size contract requires < 50. Split into helpers."
        )


@pytest.mark.unit
class TestR14aWeChatAdapterGodMethodsThinned:
    """All 9 WeChatAdapter god methods must be < 50L after R1-4a."""

    @pytest.mark.parametrize("name", WECHAT_GOD_METHODS)
    def test_god_method_under_50_lines(self, name: str):
        mod = importlib.import_module(WECHAT_ILINK_PATH)
        cls = mod.WeChatAdapter
        assert hasattr(cls, name), f"WeChatAdapter.{name} disappeared"
        method = getattr(cls, name)
        # Some methods are static/classmethod/staticmethod wrapped
        src = inspect.getsource(method)
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        assert len(body_lines) < 50, (
            f"WeChatAdapter.{name} is {len(body_lines)} non-blank lines; "
            f"R1-4a split target is < 50."
        )


# R1-4b: ``qr_login`` and ``send_wechat_direct`` are now part of R1-4b's
# scope. The global AST scan below enforces the < 50L cap on EVERY
# top-level function in ``wechat_ilink.py`` (no reserved exceptions).
R14B_RESERVED = frozenset()


@pytest.mark.unit
class TestR14aWeChatAdapterAllMethodsUnder50Lines:
    """Project-wide rule from common/coding-style.md: every method ≤ 50 lines.

    AST-walk ``wechat_ilink.py`` and assert each function/method body is
    below the cap. Catches the next god-method refactor. R1-4b reserved
    methods are exempted — they belong to a follow-up issue.
    """

    def test_no_method_exceeds_50_lines(self):
        src_path = _pathlib.Path(importlib.import_module(WECHAT_ILINK_PATH).__file__)
        text = src_path.read_text(encoding="utf-8")
        tree = _ast.parse(text)
        offenders: list[tuple[str, int, int]] = []
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                if node.name in R14B_RESERVED:
                    continue  # R1-4b: not in this issue's scope
                end = getattr(node, "end_lineno", None) or node.lineno
                src_lines = text.splitlines()
                body = src_lines[node.lineno - 1:end]
                non_blank = [ln for ln in body if ln.strip()]
                if len(non_blank) > 50:
                    offenders.append((node.name, node.lineno, len(non_blank)))
        assert not offenders, (
            "wechat_ilink.py methods over 50 lines: "
            + ", ".join(f"{n}@{ln}={sz}L" for n, ln, sz in offenders)
        )


@pytest.mark.unit
class TestR14aBackwardsCompat:
    """R1-4a must not remove anything from the public WeChatAdapter surface."""

    @pytest.mark.parametrize(
        "name",
        [
            "_coerce_list",
            "_schedule_typing_ticket_bg",
            "connect",
            "disconnect",
            "_poll_loop",
            "_process_message",
            "_is_dm_allowed",
            "_collect_media",
            "_send_text_chunk",
            "send",
            "send_typing",
            "stop_typing",
            "send_image",
            "send_image_file",
            "send_document",
            "send_video",
            "send_voice",
            "_send_file",
            "_outbound_media_builder",
            "get_chat_info",
            "extract_local_files",
            "format_message",
            "_split_text",
        ],
    )
    def test_method_still_on_wechat_adapter(self, name: str):
        mod = importlib.import_module(WECHAT_ILINK_PATH)
        cls = mod.WeChatAdapter
        assert hasattr(cls, name), f"WeChatAdapter.{name} disappeared after R1-4a"
        assert callable(getattr(cls, name)), (
            f"WeChatAdapter.{name} must remain callable"
        )

    def test_split_text_helper_preserved(self):
        """The 4-line ``_split_text`` helper signature must be preserved.

        Tests and other call sites use it; R1-4a leaves it as a thin
        wrapper around ``_split_text_for_wechat_delivery``.
        """
        from butler.gateway.platforms.wechat_ilink import WeChatAdapter

        mod = importlib.import_module("butler.gateway.platforms.wechat_ilink")
        # The class has it as a method
        assert hasattr(WeChatAdapter, "_split_text")
        # Module-level backward-compat re-export may or may not exist —
        # we just verify the class method is still callable.
        assert callable(getattr(WeChatAdapter, "_split_text"))


@pytest.mark.unit
def test_aes_padded_size_reexported_for_send_file():
    """Regression: _send_file uses _aes_padded_size; must be imported after R1-4 split."""
    mod = importlib.import_module("butler.gateway.platforms.wechat_ilink")
    assert hasattr(mod, "_aes_padded_size")
    assert mod._aes_padded_size(1) == 16
    assert mod._aes_padded_size(16) == 32


@pytest.mark.unit
def test_file_upload_crypto_helpers_reexported():
    """Regression: wechat_ilink_phases imports crypto helpers from wechat_ilink."""
    mod = importlib.import_module("butler.gateway.platforms.wechat_ilink")
    for name in ("_aes128_ecb_encrypt", "_aes128_ecb_decrypt", "_upload_ciphertext"):
        assert hasattr(mod, name), f"missing re-export: {name}"
    assert mod._aes128_ecb_encrypt(b"abc", b"\x00" * 16)


@pytest.mark.unit
class TestR14aSplitTextBehaviour:
    """Behavioral smoke: ``_split_text`` still produces expected chunks."""

    def test_split_text_passes_max_length(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.gateway.platforms.types import PlatformConfig
        from butler.gateway.platforms.wechat_ilink import WeChatAdapter

        adapter = WeChatAdapter(PlatformConfig(token="t", extra={"account_id": "a"}))
        chunks = adapter._split_text("abcdefghij" * 100)
        # _split_text_for_wechat_delivery respects MAX_MESSAGE_LENGTH = 2000
        assert all(len(c) <= WeChatAdapter.MAX_MESSAGE_LENGTH for c in chunks)
        # All non-empty
        assert all(c.strip() for c in chunks)


@pytest.mark.unit
class TestR14aSendStateDataclass:
    """``WeChatSendState`` carrier mirrors the R1-8 ``TurnBodyState`` pattern."""

    def test_wechat_send_state_is_dataclass(self):
        from dataclasses import is_dataclass

        from butler.gateway.platforms.wechat_ilink_phases import WeChatSendState

        assert is_dataclass(WeChatSendState), (
            "WeChatSendState must be a @dataclass to serve as a phase carrier"
        )

    def test_wechat_send_state_has_expected_fields(self):
        from butler.gateway.platforms.wechat_ilink_phases import WeChatSendState

        field_names = {f.name for f in WeChatSendState.__dataclass_fields__.values()}
        for expected in ("retried_without_token",):
            assert expected in field_names, (
                f"WeChatSendState missing field: {expected}"
            )


# ---------------------------------------------------------------------------
# R1-4b — qr_login + send_wechat_direct god-function split
# ---------------------------------------------------------------------------

# Modules that R1-4b introduces or extends.
WECHAT_ILINK_DIRECT_PATH = "butler.gateway.platforms.wechat_ilink_direct"


# Top-level god functions that R1-4b must thin to < 50L in
# ``wechat_ilink.py``. After this issue, the entire file should pass
# the 50-line cap.
R14B_GOD_FUNCTIONS = [
    "qr_login",
    "send_wechat_direct",
]


# Phase functions that the new ``wechat_ilink_phases`` module must export
# for the QR login flow. Added in R1-4b on top of R1-4a's list.
R14B_QR_PHASE_FUNCTIONS = [
    "_phase_qr_request_code",
    "_phase_qr_render",
    "_phase_qr_poll_iteration",
    "_phase_qr_refresh",
    "_phase_qr_finalize",
    "_phase_qr_poll_step",
]


# Phase functions that the new ``wechat_ilink_direct`` module must export
# for the ``send_wechat_direct`` flow.
R14B_DIRECT_PHASE_FUNCTIONS = [
    "_phase_direct_resolve_credentials",
    "_phase_direct_send_via_live_adapter",
    "_phase_direct_send_via_fresh_adapter",
]


@pytest.mark.unit
class TestR14bDirectModuleExists:
    """R1-4b introduces ``wechat_ilink_direct.py`` — verify it loads."""

    def test_direct_module_loads(self):
        mod = importlib.import_module(WECHAT_ILINK_DIRECT_PATH)
        assert mod is not None

    def test_direct_module_docstring_mentions_r14b(self):
        mod = importlib.import_module(WECHAT_ILINK_DIRECT_PATH)
        assert mod.__doc__ and "R1-4b" in mod.__doc__, (
            f"{WECHAT_ILINK_DIRECT_PATH} docstring must reference R1-4b audit source"
        )

    def test_direct_module_logger(self):
        mod = importlib.import_module(WECHAT_ILINK_DIRECT_PATH)
        assert hasattr(mod, "logger"), (
            f"{WECHAT_ILINK_DIRECT_PATH} must define module-level logger"
        )


@pytest.mark.unit
class TestR14bQrPhasesExtended:
    """R1-4b extends ``wechat_ilink_phases.py`` with QR-login phases."""

    def test_phases_module_docstring_mentions_r14b(self):
        mod = importlib.import_module(WECHAT_ILINK_PHASES_PATH)
        assert mod.__doc__ and "R1-4b" in mod.__doc__, (
            f"{WECHAT_ILINK_PHASES_PATH} docstring must reference R1-4b audit source"
        )

    @pytest.mark.parametrize("name", R14B_QR_PHASE_FUNCTIONS)
    def test_qr_phase_symbol_present(self, name: str):
        mod = importlib.import_module(WECHAT_ILINK_PHASES_PATH)
        assert hasattr(mod, name), (
            f"{WECHAT_ILINK_PHASES_PATH}.{name} missing — R1-4b extraction incomplete"
        )
        assert callable(getattr(mod, name)), (
            f"{WECHAT_ILINK_PHASES_PATH}.{name} must be callable"
        )


@pytest.mark.unit
class TestR14bDirectPhaseFunctionsPresent:
    @pytest.mark.parametrize("name", R14B_DIRECT_PHASE_FUNCTIONS)
    def test_direct_phase_symbol_present(self, name: str):
        mod = importlib.import_module(WECHAT_ILINK_DIRECT_PATH)
        assert hasattr(mod, name), (
            f"{WECHAT_ILINK_DIRECT_PATH}.{name} missing — R1-4b extraction incomplete"
        )
        assert callable(getattr(mod, name)), (
            f"{WECHAT_ILINK_DIRECT_PATH}.{name} must be callable"
        )


@pytest.mark.unit
class TestR14bPhaseFunctionsUnder50Lines:
    """R1-4b size contract: every new phase helper must be < 50 source lines."""

    @pytest.mark.parametrize("name", R14B_QR_PHASE_FUNCTIONS)
    def test_qr_phase_function_under_50_lines(self, name: str):
        mod = importlib.import_module(WECHAT_ILINK_PHASES_PATH)
        assert hasattr(mod, name), f"{WECHAT_ILINK_PHASES_PATH}.{name} missing"
        fn = getattr(mod, name)
        assert callable(fn), f"{WECHAT_ILINK_PHASES_PATH}.{name} not callable"
        src = inspect.getsource(fn)
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        assert len(body_lines) < 50, (
            f"{WECHAT_ILINK_PHASES_PATH}.{name} is {len(body_lines)} non-blank lines; "
            f"R1-4b size contract requires < 50. Split into helpers."
        )

    @pytest.mark.parametrize("name", R14B_DIRECT_PHASE_FUNCTIONS)
    def test_direct_phase_function_under_50_lines(self, name: str):
        mod = importlib.import_module(WECHAT_ILINK_DIRECT_PATH)
        assert hasattr(mod, name), f"{WECHAT_ILINK_DIRECT_PATH}.{name} missing"
        fn = getattr(mod, name)
        assert callable(fn), f"{WECHAT_ILINK_DIRECT_PATH}.{name} not callable"
        src = inspect.getsource(fn)
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        assert len(body_lines) < 50, (
            f"{WECHAT_ILINK_DIRECT_PATH}.{name} is {len(body_lines)} non-blank lines; "
            f"R1-4b size contract requires < 50. Split into helpers."
        )


@pytest.mark.unit
class TestR14bTopLevelGodFunctionsThinned:
    """``qr_login`` and ``send_wechat_direct`` must be < 50L after R1-4b."""

    @pytest.mark.parametrize("name", R14B_GOD_FUNCTIONS)
    def test_god_function_under_50_lines(self, name: str):
        mod = importlib.import_module(WECHAT_ILINK_PATH)
        assert hasattr(mod, name), f"{WECHAT_ILINK_PATH}.{name} missing"
        fn = getattr(mod, name)
        assert callable(fn), f"{WECHAT_ILINK_PATH}.{name} not callable"
        src = inspect.getsource(fn)
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        assert len(body_lines) < 50, (
            f"{WECHAT_ILINK_PATH}.{name} is {len(body_lines)} non-blank lines; "
            f"R1-4b split target is < 50."
        )


@pytest.mark.unit
class TestR14bWeChatIlinkAllTopLevelUnder50Lines:
    """Project-wide rule: every top-level function in wechat_ilink.py ≤ 50 lines.

    After R1-4b, the file must pass the size contract end-to-end
    (no reserved exceptions left). Catches the next god-function
    refactor in this file.
    """

    def test_no_top_level_function_exceeds_50_lines(self):
        src_path = _pathlib.Path(importlib.import_module(WECHAT_ILINK_PATH).__file__)
        text = src_path.read_text(encoding="utf-8")
        tree = _ast.parse(text)
        src_lines = text.splitlines()
        offenders: list[tuple[str, int, int]] = []
        # Walk only the module body (not class bodies) for top-level funcs.
        for node in tree.body:
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", None) or node.lineno
                body = src_lines[node.lineno - 1:end]
                non_blank = [ln for ln in body if ln.strip()]
                if len(non_blank) > 50:
                    offenders.append((node.name, node.lineno, len(non_blank)))
        assert not offenders, (
            "wechat_ilink.py top-level functions over 50 lines: "
            + ", ".join(f"{n}@{ln}={sz}L" for n, ln, sz in offenders)
        )


@pytest.mark.unit
class TestR14bBackwardCompat:
    """R1-4b must not remove ``qr_login`` / ``send_wechat_direct`` from the
    original import path; the thinned orchestrators must remain on
    ``butler.gateway.platforms.wechat_ilink``."""

    @pytest.mark.parametrize("name", ["qr_login", "send_wechat_direct"])
    def test_symbol_still_on_wechat_ilink(self, name: str):
        mod = importlib.import_module(WECHAT_ILINK_PATH)
        assert hasattr(mod, name), f"{name} disappeared from {WECHAT_ILINK_PATH}"
        assert callable(getattr(mod, name)), (
            f"{WECHAT_ILINK_PATH}.{name} must remain callable"
        )

    def test_qr_login_is_coroutine(self):
        import inspect as _inspect

        mod = importlib.import_module(WECHAT_ILINK_PATH)
        assert _inspect.iscoroutinefunction(mod.qr_login), (
            "qr_login must remain an async function for back-compat"
        )

    def test_send_wechat_direct_is_coroutine(self):
        import inspect as _inspect

        mod = importlib.import_module(WECHAT_ILINK_PATH)
        assert _inspect.iscoroutinefunction(mod.send_wechat_direct), (
            "send_wechat_direct must remain an async function for back-compat"
        )


@pytest.mark.unit
class TestR14bQrLoginStateDataclass:
    """``QrLoginState`` carrier — mirrors the R1-4a ``WeChatSendState`` pattern."""

    def test_qr_login_state_is_dataclass(self):
        from dataclasses import is_dataclass

        from butler.gateway.platforms.wechat_ilink_phases import QrLoginState

        assert is_dataclass(QrLoginState), (
            "QrLoginState must be a @dataclass to serve as a phase carrier"
        )

    def test_qr_login_state_has_expected_fields(self):
        from butler.gateway.platforms.wechat_ilink_phases import QrLoginState

        field_names = {f.name for f in QrLoginState.__dataclass_fields__.values()}
        for expected in ("refresh_count", "current_base_url", "qrcode_value", "qr_scan_data"):
            assert expected in field_names, (
                f"QrLoginState missing field: {expected}"
            )


@pytest.mark.unit
class TestEng13AdapterInbound:
    def test_adapter_inbound_module_exists(self):
        mod = importlib.import_module(
            "butler.gateway.platforms.wechat_ilink.adapter_inbound"
        )
        assert hasattr(mod, "dispatch_poll_response")
        assert hasattr(mod, "process_message")

    def test_poll_backoff_seconds_ladder(self):
        from butler.gateway.platforms.wechat_ilink.adapter_inbound import poll_backoff_seconds
        from butler.gateway.platforms.wechat_ilink.constants import (
            BACKOFF_DELAY_SECONDS,
            MAX_CONSECUTIVE_FAILURES,
            RETRY_DELAY_SECONDS,
        )

        assert poll_backoff_seconds(1) == RETRY_DELAY_SECONDS
        assert poll_backoff_seconds(MAX_CONSECUTIVE_FAILURES) == BACKOFF_DELAY_SECONDS


@pytest.mark.unit
class TestR14bSendWechatDirectMissingToken:
    """Behavioral smoke: ``send_wechat_direct`` returns error dict (not raises)
    when the token is missing. Mirrors the original function's contract."""

    def test_missing_token_returns_error_dict(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        # Ensure no env fallback leaks in
        for var in ("WECHAT_TOKEN", "WECHAT_ACCOUNT_ID"):
            monkeypatch.delenv(var, raising=False)
        from butler.gateway.platforms.wechat_ilink import send_wechat_direct

        result = await_obj = None
        import asyncio

        async def _run():
            return await send_wechat_direct(
                extra={},
                token=None,
                chat_id="peer-1",
                message="hi",
            )

        result = asyncio.run(_run())
        assert isinstance(result, dict)
        assert "error" in result
        assert "token" in result["error"].lower()

