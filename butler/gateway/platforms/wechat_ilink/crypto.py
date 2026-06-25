"""AES-128-ECB + PKCS#7 helpers for iLink CDN media (PROD-P2-01)."""

from butler.gateway.platforms.wechat_ilink._utils_legacy import (
    _aes128_ecb_decrypt,
    _aes128_ecb_encrypt,
    _aes_padded_size,
    _parse_aes_key,
    _pkcs7_pad,
)

__all__ = [
    "_aes128_ecb_decrypt",
    "_aes128_ecb_encrypt",
    "_aes_padded_size",
    "_parse_aes_key",
    "_pkcs7_pad",
]
