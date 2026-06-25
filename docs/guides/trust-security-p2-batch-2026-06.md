# 安全信任补丁批次（PROD-P2-03，2026-06）

> **Backlog**：[PROD-P2-03](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md#prod-p2-03-安全信任补丁批次)

本批次（≤5 项）聚焦 **出站 PII 扩展**、**secrets.yaml Fernet**、**MCP HTTP SSRF 字面量私网 IP**。不含 DNS 重绑定全量加固（registry `url_safety` 已有 pinning）。

## 1. 出站 PII 扩展

实现：`butler/gateway/pii_scrub.py`

| 新增/扩展 | 说明 |
|-----------|------|
| Bearer 令牌 | `Authorization: Bearer …` |
| AWS Access Key | `AKIA…` |
| GitHub PAT | `ghp_` / `github_pat_` |
| Link-local IPv4 | `169.254.x.x`（含 metadata 169.254.169.254） |

开关：`BUTLER_OUTBOUND_PII_SCRUB=1`（默认开）、`BUTLER_OUTBOUND_PII_SCRUB_EMAIL=1`（默认开）。

## 2. secrets.yaml Fernet（可选）

实现：`butler/config_secrets_crypto.py` · `butler/config_secrets.py`

```bash
# 生成密钥（一次性保存到 .env，勿提交）
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# .env
BUTLER_SECRETS_ENCRYPT=1
BUTLER_SECRETS_ENCRYPT_KEY=<base64-fernet-key>

# 写入（自动加密 api_key 字段）
butler secrets set minimax sk-...

# 迁移既有明文
butler secrets encrypt          # dry-run
butler secrets encrypt --apply

butler secrets status           # 显示 encrypted/total
```

依赖：`cryptography`（与微信 extra 同包；未安装时回退明文 + WARN）。

## 3. MCP HTTP SSRF 守门

实现：`butler/mcp/config.py` → `validate_http_url`

- 字面量 IP 经 `ipaddress` 判定 private/loopback/link-local/reserved/multicast → 拒绝
- `hosts_allow` **不能**绕过私网/metadata（除非 `BUTLER_MCP_HTTP_ALLOW_PRIVATE=1`）
- 子域后缀匹配仍为 `host == h or host.endswith('.' + h)`（无子串 bypass）

远程 catalog：`BUTLER_MCP_CATALOG_URLS` 仍走 `registry/url_safety.is_safe_url`。

## 守门

```bash
bash scripts/butler-trust-p2-gate.sh
```

## 发版 note（摘要）

- **Operator**：若启用 `BUTLER_SECRETS_ENCRYPT=1`，发版前确认 `.env` 含 `BUTLER_SECRETS_ENCRYPT_KEY` 且已 `butler secrets encrypt --apply`。
- **MCP**：HTTP transport 指向内网 IP 的配置在默认设置下将被拒绝；内网调试需显式 `BUTLER_MCP_HTTP_ALLOW_PRIVATE=1`。
- **微信出站**：新增 Bearer/AWS/GitHub/link-local 脱敏；无 env 变更（除可选 secrets 加密）。
