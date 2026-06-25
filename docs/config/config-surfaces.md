# Butler 配置面四分法

> **状态**：2026-06-09（Phase A2）  
> **用途**：维护时判断「该改哪个文件」；**不**替代 [`reference.md`](reference.md) 全量 env 表。  
> **关联**：[`layered-model-config.md`](../architecture/layered-model-config.md)（角色模型 L0–L3）· [`env-config-maintainability-2026-06.md`](../plans/active/env-config-maintainability-2026-06.md)

---

## 1. 为什么要四分

Butler 配置落在四个**正交面**，合并顺序与可写入口不同。改错面会导致：密钥进 git、运行时改不动安全项、或文档与 effective 行为不一致。

```text
┌─────────────┐   ┌──────────────┐   ┌─────────────────────┐   ┌──────────────────┐
│  A. .env    │   │ B. secrets   │   │ C. ~/.butler/       │   │ D. config_service │
│  部署/进程  │   │ secrets.yaml │   │ config.yaml         │   │ 运行时白名单      │
└─────────────┘   └──────────────┘   └─────────────────────┘   └──────────────────┘
       │                 │                      │                        │
       └─────────────────┴──────────────────────┴────────────────────────┘
                                    │
                          各模块 getenv / load YAML
                                    │
                          effective 行为（见 /诊断、butler doctor）
```

**理论边界**：本文只描述工程面；**不**改变公理 A3/A4（Lead 工具隔离、权限单调）与门控实现。安全类 env **不得**通过 D 面在对话中修改（Sprint 9 SEC-9.1）。

---

## 2. 四面定义

| 面 | 路径 / 入口 | 放什么 | 不放什么 |
|----|-------------|--------|----------|
| **A. 环境变量** | 仓库 `.env`、systemd `Environment=`、shell `export` | Provider **API Key**（`*_API_KEY`）、微信凭证、部署路径（`BUTLER_HOME`、`BUTLER_PROJECTS_DIR`）、大量 `BUTLER_*` 开关与阈值 | 结构化多字段配置（用 C 面）；密钥重复写进 `config.yaml` |
| **B. 密钥文件** | `~/.butler/secrets.yaml`（`BUTLER_SECRETS_PATH` 可覆盖） | Provider `api_key`（`butler secrets set` 写入，mode 600；可选 `BUTLER_SECRETS_ENCRYPT=1` → `FERNET:` 密文） | 模型名、非密钥业务配置 |
| **C. 管家 YAML** | `~/.butler/config.yaml` | `default_provider`、`models.*`、`auxiliary.*`、`embedding.*`、`llm_fallback.*`、`gateway.*`、`butler_name` 等 | API Key（用 A/B）；绝大多数 `BUTLER_*` 尚未迁 YAML（见 §4） |
| **D. 运行时服务** | 微信 `/config`、`butler_config` 工具、`config_service.py` | **白名单内** `BUTLER_*` 的 `os.environ` 临时写入 | API Key、路径、安全/终端类（见 §5） |

**项目层扩展**：`projects/<P>/project.yaml` — 模型 L2、`permissions`、`workflows`、`tools` 等；见 [`layered-model-config.md`](../architecture/layered-model-config.md) §3.1。

---

## 3. 合并与优先级（按消费方）

### 3.1 Provider 凭证（谁提供 API Key）

```text
env *_API_KEY  →  覆盖  →  secrets.yaml providers.<name>
                →  覆盖  →  （无则 Provider 不可用）
```

- 实现：`ButlerSettings._load_env_providers` → `merge_secrets_into_settings`（`butler/config.py`、`butler/config_secrets.py`）。
- **维护**：生产至少配 A 或 B 之一；`butler secrets status` / `butler doctor`「凭证文件」行可核对 B。

### 3.2 角色 LLM 模型

见 [`layered-model-config.md`](../architecture/layered-model-config.md)：**L0 env 默认 → L1 config.yaml → L2 project.yaml → L3 runtime**；解析入口 `resolve_effective_model`。

### 3.3 正交栈（不进 role merge）

| 能力 | 配置面 | 解析入口 |
|------|--------|----------|
| 侧任务压缩 | C `auxiliary.*` | `resolve_auxiliary_config` |
| 嵌入 | C `embedding.*` ← A `BUTLER_EMBEDDING_*` | `resolve_embedding_config` |
| 记忆栈 | C `memory.*` ← A `BUTLER_MEMORY_*` / `BUTLER_SEMANTIC_*` | `resolve_memory_config` |
| 上下文栈 | C `context.*` ← A `BUTLER_CONTEXT_*` / `BUTLER_TURN_BUDGET_*` / 剪枝 / walkup | `resolve_context_config`；`/诊断` 见 `format_context_config_source_line` |
| 微信识图/STT | C `gateway.inbound_media` ← A `BUTLER_WECHAT_*` | `resolve_gateway_inbound_config`；`/诊断` 见 `format_gateway_inbound_config_source_line` |
| LLM fallback 链 | C `llm_fallback.*` | `build_fallback_chain` + `llm_fallback_extra_configs` |
| 通用 `BUTLER_*` | A 为主；默认字面量 SSOT：`butler/defaults/env_defaults.py` | 各模块 `getenv` / `env_truthy` |

### 3.4 config_service（D 面）有效值

```text
若 os.environ 已有 KEY  →  effective = env（source=env）
否则若 KEY 在白名单      →  effective = meta.default（source=default）
否则                    →  unknown
```

`/config set` **只写 `os.environ`**，不修改 C 面 YAML；重启 Gateway 后 env 未持久化则丢失（level C 项需重启才完全生效）。

---

## 4. C 面：`config.yaml` 段索引

模板：[`config.yaml.example`](config.yaml.example)。`save_butler_config()` / `/model save butler` 会写 `models`，并**保留**已有 `gateway`、`auxiliary`、`embedding`、`llm_fallback`、`remote_compact`。

| 段 | 用途 |
|----|------|
| `default_provider` | L0 兜底 provider 名 |
| `models.{butler,dev_agent,content_agent,review_agent}` | L1 四角色；未知键会 warning |
| `auxiliary.{compression,post_session,...}` | 压缩 / 会后提取等侧任务模型 |
| `embedding.{provider,model}` | 向量嵌入（env 覆盖） |
| `llm_fallback.{enabled,chain}` | 主 LLM 失败降级（`auto` 兼容 minimax 链） |
| `remote_compact.{model}` | OpenAI 式 compact API model |
| `gateway.inbound_media` | 识图 VLM、STT、whisper |
| `gateway.queue` | 入站队列 mode / cap / drop / collect_debounce_ms（env `BUTLER_GATEWAY_QUEUE_*` 覆盖）；`/诊断` 见 `format_gateway_queue_config_source_line` |
| `memory.*` | 语义记忆、混合权重、索引 cap、衰减、观测 store 等（env `BUTLER_MEMORY_*` / `BUTLER_SEMANTIC_*` 覆盖） |
| `context.*` | 上下文预算、轮次 token 预算、工具 micro/向后剪枝、instruction walkup（env 覆盖） |

**尚未进 YAML 的域**（仍用 A 面 env）：多数 CC 线束开关 — 默认见 `env_defaults.py` 与 [`reference.md`](reference.md)。嵌入模型见 `embedding.*`（`resolve_embedding_config`）。

---

## 5. D 面：运行时白名单

**入口**：微信 `/config` · Agent 工具 `butler_config`（须 Owner）· `butler/config_service.py`

**分组**（`config_categories()`）：网络、记忆、开发、网关、日常、扩展、系统 — **无「安全」可写分组**。

**Level**（`config_set` 返回值）：

| Level | 含义 |
|-------|------|
| A | 立即生效（仅当前进程 `environ`） |
| B | 建议重建 AgentLoop 会话 |
| C | 需重启 Gateway |

**故意不可运行时修改**（须改 A/C 或重启前 env，Sprint 9）：

- 安全：`BUTLER_DOOM_LOOP_*`、`BUTLER_TERMINAL_DANGER_CHECK`、`BUTLER_IO_GUARDRAIL`、`BUTLER_READ_BEFORE_EDIT` 等
- 高危开发：`BUTLER_ENABLE_TERMINAL`、`BUTLER_ENABLE_GIT_PUSH`、`BUTLER_EXECUTE_CODE`

全量 `BUTLER_*` 列表见 [`reference.md`](reference.md)；**可写子集**以 `config_service._MUTABLE_KEYS` 为准（`rg '_register\(' butler/config_service.py`）。

---

## 6. B 面：`secrets.yaml` 格式

```yaml
providers:
  minimax:
    api_key: "sk-..."
  deepseek:
    api_key: "sk-..."
```

- CLI：`butler secrets set <provider> <api_key>` · `butler secrets status`
- 关闭：`BUTLER_SECRETS_FILE=0`
- 路径：`BUTLER_SECRETS_PATH` 或 `~/.butler/secrets.yaml`

---

## 7. 运维速查

| 我想… | 改这里 |
|--------|--------|
| 换 LLM API Key | A `.env` 或 B `secrets.yaml`（勿进 C） |
| 换管家/委派默认模型 | C `models.*` 或 `/model save` |
| 换项目内模型 | `project.yaml` `models.*` 或 `/model save dev/...` |
| 关首次欢迎语 | D `/config set BUTLER_ONBOARDING_WELCOME 0` 或 A env |
| 调压缩阈值 | A `BUTLER_CONTEXT_*`（默认 `env_defaults.py`） |
| 开语义记忆 | A `BUTLER_SEMANTIC_MEMORY=1` + C `embedding` 或 A `BUTLER_EMBEDDING_*` |
| 看 effective 配置 | 微信 `/诊断` · `butler doctor` · `/model` |

---

## 8. 维护检查表（改配置时）

1. 密钥是否只出现在 **A 或 B**？  
2. 新 `BUTLER_*` 是否写入 [`reference.md`](reference.md) + [`.env.example`](../../.env.example)？默认是否进 `butler/defaults/env_defaults.py`？域是否登记 [`env-domains.md`](env-domains.md)？  
3. 若加入 D 面白名单：是否 **非**安全/终端类？`meta.default` 是否与 `getenv` 默认一致？  
4. 若扩展 C 面段：是否更新 `config.yaml.example` + `ButlerSettings._apply_yaml_dict` + `save_butler_config` preserve 列表？  
5. 角色模型是否仍只走 `resolve_effective_model`？（见 [`model-config-maintainability-2026-06.md`](../plans/active/model-config-maintainability-2026-06.md)）  
6. 动门控/扩展路径是否只更新文档矩阵？（见 [`permission-gate-stack.md`](../architecture/permission-gate-stack.md)、[`extension-registry-paths.md`](../architecture/extension-registry-paths.md)）

---

## 9. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-06-09 | Phase A2 初稿：四面定义、优先级、白名单边界、运维速查 |
