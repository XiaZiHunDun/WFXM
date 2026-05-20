# Hermes Agent（计划迁仓位）

根目录的 `agent/`、`gateway/`、`hermes_cli/` 等将迁入本目录，供 `butler-system[hermes-gateway]` 与 `butler gateway --hermes-fallback` 使用。

迁仓完成前，`butler/hermes_runtime.py` 会回退到仓库根目录。详见 `docs/architecture/hermes-decoupling.md` 阶段 C。
