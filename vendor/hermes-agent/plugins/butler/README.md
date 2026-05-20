# plugins/butler（遗留）

此 Hermes 插件在 `--hermes-fallback` 子进程中注册 `pre_gateway_dispatch`，用于拦截 Butler 斜杠命令。

**Butler 原生网关** 已使用 `butler/gateway/hooks.py` HookBus，无需本插件。请勿在新功能中依赖此路径。
