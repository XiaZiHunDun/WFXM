# Hermes Agent（vendored）

本目录为 Hermes 上游运行时快照，**仅供** `butler gateway --hermes-fallback` 与 `hermes` / `hermes-agent` CLI 使用。

- Butler 主路径（`butler chat`、`butler gateway --platforms wechat`）**不** import 此树。
- 新平台适配应提炼到 `butler/gateway/platforms/`，而非在此修改。
- `plugins/butler`：遗留 Hermes hook，已由 `butler/gateway/hooks.py` 取代；fallback 时仍会自动启用。

对照只读上游：`reference/hermes-agent/`（勿改动）。
