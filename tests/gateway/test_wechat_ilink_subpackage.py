"""PROD-P2-01: wechat_ilink subpackage layout guard."""

from __future__ import annotations

import importlib

import pytest

_SUBMODULES = (
    "constants",
    "crypto",
    "account",
    "media",
    "transport",
    "phases",
    "direct",
    "registry",
)


@pytest.mark.unit
@pytest.mark.parametrize("name", _SUBMODULES)
def test_wechat_ilink_subpackage_modules_exist(name: str):
    mod = importlib.import_module(f"butler.gateway.platforms.wechat_ilink.{name}")
    assert mod is not None


@pytest.mark.unit
def test_transport_send_message_reexported_on_package():
    pkg = importlib.import_module("butler.gateway.platforms.wechat_ilink")
    transport = importlib.import_module("butler.gateway.platforms.wechat_ilink.transport")
    assert pkg._send_message is transport._send_message


@pytest.mark.unit
def test_crypto_aes_roundtrip_via_subpackage():
    crypto = importlib.import_module("butler.gateway.platforms.wechat_ilink.crypto")
    key = b"\x01" * 16
    plain = b"butler-p2-01"
    enc = crypto._aes128_ecb_encrypt(plain, key)
    assert crypto._aes128_ecb_decrypt(enc, key) == plain
