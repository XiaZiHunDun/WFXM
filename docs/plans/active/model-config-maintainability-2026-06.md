# 模型配置可维护性完善方案（2026-06）

> **性质**：纯工程梳理；**不**改变产品行为边界，**不**绑定理论登记册（G1–G4）。  
> **目的**：单一解析路径、配置面可枚举、文档与代码一致，降低改模型时的 grep/排错成本。  
> **SSOT 现状**：[`layered-model-config.md`](../../architecture/layered-model-config.md)（行为）+ [`config/reference.md`](../../config/reference.md)（env）+ `butler/model_resolve.py`（角色 LLM）。

---

## 1. 非目标

| 不做 | 原因 |
|------|------|
| 新增模型厂商 / 多模态主 Loop | 产品边界 |
| `/model` UX 增强、诊断 UI 改版 | 本方案面向维护，非体验 |
| 按实测自动选优 / 成本路由 | 属运营策略，另立项 |
| 理论差距登记或 G2 验收改动 | 与本文正交 |

---

## 2. 现状维护债（审计摘要）

### 2.1 双解析路径（高优先级）

| API | 合并层 | 调用方 |
|-----|--------|--------|
| `resolve_effective_model(role, project=…)` | L0→L1→**L2**→L3 | `orchestrator._model_credentials`、`get_project_agent_kwargs` |
| `ButlerSettings.get_model_config(role)` | L0→L1→L3（**无 L2**） | `auxiliary_client`（butler 回退）、`model_context.resolve_max_output_tokens`、部分 live smoke |

**风险**：同一进程内「发请求用的模型」与「上下文预算读的 max_tokens」可能不一致。

### 2.2 配置面分散

| 维度 | YAML | env | 代码硬编码 |
|------|:----:|:---:|:----------:|
| 四角色 LLM | ✓ | L0 `*_MODEL` | `default_provider=minimax` |
| auxiliary | ✓ | — | 扫描顺序 `minimax,deepseek,openai,claude` |
| gateway VLM/STT | ✓ | `BUTLER_WECHAT_*` | `minimax` / `coding_plan/vlm` / `small` |
| embedding | ✗ | `BUTLER_EMBEDDING_*` | `hashing-v1`、`text-embedding-3-small` 等 |
| provider fallback 链 | ✗ | 间接（有 key 才进链） | minimax 主模型时追加 deepseek/qwen/openai |
| remote compact body | ✗ | — | `"gpt-4.1-mini"` |
| vision OpenAI 降级 | ✗ | `OPENAI_VISION_MODEL` | 顺序 `openai,ocr` |
| transport 注册表 | ✗ | — | 各 provider `default_model` |

### 2.3 文档与实现漂移

- `layered-model-config.md` §3.1：莎丽主对话 L2 ✗ → 代码 **会** merge `project.models.butler`。
- `/model save`：`butler` 写 global；`dev/content/review` 写 project — **读可 L2、写不对称**。

### 2.4 角色别名与列表源

- `lead` → `butler`（模型层）与 `lead_agent`（`agent_profiles` 画像）并存，新人易混淆。
- `_LIST_ROLES` / `LayeredModelConfig` / `project.yaml models` 键无 schema 校验。

---

## 3. 目标架构（维护心智模型）

### 3.1 单一解析入口

```text
所有「需要知道 effective provider/model」的生产代码
  → resolve_effective_model(role, project?, settings?)
  → model_config_to_credentials(cfg, settings?)

例外（正交栈，禁止 merge 进 role）：
  → resolve_auxiliary_config(task)
  → resolve_gateway_inbound_config()
  → resolve_embedding_config()          # 新增，统一 embedding
  → build_fallback_chain(primary, extra?) # extra 来自配置，非硬编码
```

`get_model_config(role)` **弃用**（先 thin-wrapper 调 `resolve_effective_model(..., project=None).config`，再删直调）。

### 3.2 配置面三分法（团队约定）

| 类 | 放哪里 | 示例 |
|----|--------|------|
| **A. 结构化选型** | `config.yaml` / `project.yaml` | `models.*`、`auxiliary.*`、`gateway.*`、`embedding.*`、`llm_fallback.*` |
| **B. 密钥与部署** | `.env` only | `*_API_KEY`、`*_BASE_URL`、`BUTLER_HOME` |
| **C. 实现常量** | `butler/defaults/model_defaults.py`（新建） | provider 注册表 default_model、hashing 维度、OpenAPI 路径 — **一处 grep** |

规则：**禁止**在业务模块散落 `ModelConfig(provider="minimax", …)`；仅 `model_defaults.py` 与测试 fixture 可出现字面量。

### 3.3 建议 `config.yaml` 结构（向后兼容）

```yaml
default_provider: minimax

models: { butler, dev_agent, content_agent, review_agent }

auxiliary:
  compression: { provider, model }
  post_session: { provider, model }
  # 可选：mode_classifier, auto_review, injection_score — 默认 inherit compression

gateway:
  inbound_media: { vision, speech }   # 已有

embedding:                            # 新增（env 覆盖 yaml）
  provider: fastembed
  model: BAAI/bge-small-en-v1.5

llm_fallback:                         # 新增（env 可整段禁用）
  enabled: true
  chain: []                           # 空 = 仅 primary，不自动追加
  # 或显式：chain: [{ provider: deepseek, model: deepseek-chat }, ...]

remote_compact:                       # 新增
  model: ""                           # 空 = 跟 auxiliary.compression.model
```

`project.yaml` 保持 `models.<role>`；**不**新增 `vision_agent` 等于项。

---

## 4. 代码改动清单（按优先级）

### P0 — 去双路径（行为不变或仅修复明显不一致）

| 项 | 改动 | 验收 |
|----|------|------|
| P0-1 | `get_model_config` → 内部调用 `resolve_effective_model`；增加可选 `project` 参数 | `test_butler_config` + 新测：有 project override 时两者一致 |
| P0-2 | `model_context.resolve_max_output_tokens` 传 `project=pm.get_current(...)` | 单测：project butler max_tokens 生效 |
| P0-3 | `auxiliary_client` butler 回退改用 `resolve_effective_model("butler", project=None)` | auxiliary 测试仍绿 |
| P0-4 | 全仓 `rg 'get_model_config\('` 仅保留 wrapper / 测试 | grep 守门 |

### P1 — 硬编码收口

| 项 | 改动 | 验收 |
|----|------|------|
| P1-1 | 新建 `butler/defaults/model_defaults.py`：L0 provider 默认 model、gateway 默认、embedding 默认、fallback 扫描顺序（仅作 **未配置时** fallback） | 无业务文件直接写 `MiniMax-M2.7` 等（测试除外） |
| P1-2 | `build_fallback_chain`：默认 **不** 自动追加；`llm_fallback.enabled` + `chain` 显式配置时追加 | 默认行为：仅 primary（**行为变更** — 见 §5） |
| P1-3 | `remote_compact` body model = `auxiliary.compression` 解析结果，去掉 `gpt-4.1-mini` 字面量 | `test_remote_compact` |
| P1-4 | `resolve_embedding_config()`：`yaml embedding.*` ← env `BUTLER_EMBEDDING_*` | `test_premise_memory_theory` / embedding 相关 |

### P2 — 文档与可观测

| 项 | 改动 | 验收 |
|----|------|------|
| P2-1 | 修订 `layered-model-config.md` §3.1/§3.2：L2 对 butler **读**路径、save 写路径表 | 与代码一致 |
| P2-2 | `config/reference.md` + `config.yaml.example`：embedding、llm_fallback、remote_compact | doctor 不报错 |
| P2-3 | `format_model_diagnostic_lines` 增加 embedding + llm_fallback 有效配置一行 | `/诊断` 肉眼可核对 |
| P2-4 | `CONTRIBUTING.md` 或 AGENTS.md 增「改模型配置检查表」3 行 | — |

### P3 — 可选（维护体验）

| 项 | 说明 |
|----|------|
| P3-1 | `butler doctor` 子命令 `doctor models`：打印四角色 + auxiliary + gateway + embedding effective + sources |
| P3-2 | 启动时一次 `logger.info` 汇总 effective butler（脱敏） |
| P3-3 | JSON Schema / pydantic 校验 `config.yaml` models 键（拒绝未知 role） |

---

## 5. 行为变更策略

仅 **P1-2 fallback 链** 可能改变生产行为（现网 minimax 失败会自动切 deepseek）。

建议：

1. **默认保持兼容**：`llm_fallback.enabled` 默认 `true`，`chain: auto` 保留现逻辑（minimax → 有 key 的 deepseek/qwen/openai）。
2. **显式 `chain: []`** 或 `enabled: false` → 仅 primary。
3. 文档标明：`auto` 为遗留行为，新部署推荐显式 `chain`。

其余 P0/P1 项为 **梳理与一致性修复**，不改变默认 effective 模型。

---

## 6. 测试守门

```bash
# 配置与解析
PYTHONPATH=. pytest tests/test_butler_config.py tests/test_model_resolve.py -q

# gateway / auxiliary
PYTHONPATH=. pytest tests/test_message_queue.py tests/test_gateway_handler.py \
  tests/test_vision_fallback.py -q

# 记忆嵌入
PYTHONPATH=. pytest tests/test_premise_memory_theory.py tests/test_memory_metrics_benchmark.py -q

# 全量（发版前）
PYTHONPATH=. pytest -m "not live_llm" -q
```

新增建议：

- `tests/test_model_config_single_resolver.py`：同一 settings+project 下，orchestrator / model_context / auxiliary 回退路径对 butler 的 model 字段一致。
- `tests/test_model_defaults_no_literals.py`（可选）：静态检查 `butler/` 下禁止新增散落模型字面量（allowlist `defaults/`、`provider_presets.py`）。

---

## 7. 实施分期

| 阶段 | 交付 | 预估 |
|------|------|------|
| **M0** | 本文 + `layered-model-config.md` §3 勘误（只文档） | 0.5d |
| **M1** | P0 双路径合并 | 1d |
| **M2** | P1 defaults 模块 + embedding yaml + remote_compact | 1–2d |
| **M3** | P1-2 fallback 可配置 + example/reference | 1d |
| **M4** | P2 诊断 + P3 doctor（可选） | 1d |

**建议顺序**：M0 → M1 → M2 → M3；M4 按需。

---

## 8. 维护检查表（改模型配置时）

1. 是否走 `resolve_effective_model` / 正交 `resolve_*_config`？  
2. 新字面量是否只进 `butler/defaults/model_defaults.py`？  
3. 是否同步 `config.yaml.example`、`reference.md`、`layered-model-config.md`（若改合并语义）？  
4. `rg 'get_model_config|ModelConfig\(provider'` 无新增业务直调？

---

## 9. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-06-09 | 初稿：维护向审计 + P0–P3 分期 |
| 2026-06-09 | M0–M3 落地：单一解析、`model_defaults`、embedding/llm_fallback/remote_compact 配置面 |
| 2026-06-09 | P3 收口：`models` 未知键 warning；`butler doctor` 复用 `format_model_diagnostic_lines`（跳过启动日志、跳过 JSON Schema） |
