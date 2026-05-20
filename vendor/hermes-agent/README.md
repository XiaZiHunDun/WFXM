# Hermes Agent（vendored）

本目录为 Hermes 上游运行时快照，**仅供** `butler gateway --hermes-fallback` 与 `hermes` / `hermes-agent` CLI 使用。

- Butler 主路径（`butler chat`、`butler gateway --platforms wechat`）**不** import 此树。
- 新平台适配应提炼到 `butler/gateway/platforms/`（当前仅微信已提炼）；其余平台由 `butler gateway --platforms <name>` 自动拉起本子进程。
- 安装：`pip install -e ".[hermes-gateway]"`（根目录）安装本包 `hermes-vendored`。
- `plugins/butler`：遗留 Hermes hook，已由 `butler/gateway/hooks.py` 取代；fallback 时仍会自动启用。

对照只读上游：`reference/hermes-agent/`（勿改动）。
