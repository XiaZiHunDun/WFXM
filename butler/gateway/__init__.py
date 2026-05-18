"""Butler Gateway — message handling for external platforms.

Currently uses Hermes gateway subprocess for platform adapters
(Telegram, WeChat, etc.) with Butler plugins hooking into the
message pipeline. The Butler gateway module provides the message
processing logic that runs within those hooks.
"""
