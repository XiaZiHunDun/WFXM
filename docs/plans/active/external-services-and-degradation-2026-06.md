# Butler v4 外部服务需求 & 降级方案

> **版本**：1.2 | 2026-06-09
> **关联**：`post-consolidation-roadmap-2026-05.md` 轨道 A/B/D

---

## 1. 总览

Butler v4 按「本地优先、API 增强」原则设计：所有核心功能必须有**零外网依赖的降级路径**，API 仅作为体验升级层。

| 能力维度 | 纯本地可用 | API 增强后提升 |
|----------|-----------|---------------|
| LLM 推理 | ❌（必须外部） | — |
| 向量检索 | ✅ fastembed+ChromaDB (本地) | API embedding 可选 |
| 定理验证 | ✅ AST 级检查 (L1) | mypy/形式验证 |
| 经验库 | ✅ JSON 持久化 | — |
| PIM 工具 | ✅ 本地 JSON | — |
| 记忆持久化 | ✅ SQLite + FTS5 | — |
| 微信网关 | ❌（依赖 iLink） | — |
| 提醒推送 | ❌（依赖网关） | — |

---

## 2. 逐项需求与降级

### 2.1 LLM 推理服务（必需）

| 项 | 说明 |
|----|------|
| **用途** | Agent Loop 主推理、压缩摘要、Post-session 提炼、经验评估 |
| **当前支持** | MiniMax (`MINIMAX_API_KEY`)、DeepSeek (`DEEPSEEK_API_KEY`)、OpenAI 兼容端点 |
| **最低要求** | 任意 1 个 Provider 可用即可 |
| **配置** | `BUTLER_DEFAULT_PROVIDER`、`config.yaml → models.*` |
| **降级** | 无法降级——LLM 是核心依赖。但支持 provider 间自动 fallback（见 `butler/llm/provider_registry.py`） |

### 2.2 Embedding 服务

| 项 | 说明 |
|----|------|
| **用途** | 记忆向量索引、语义检索、经验匹配 |
| **Provider** | `BUTLER_EMBEDDING_PROVIDER` |
| **当前** | `fastembed`（本地 ONNX，`BAAI/bge-small-en-v1.5`，384 维）✅ 已配置 |
| **API 备选** | `dashscope`（`text-embedding-v3`，1024 维）✅ 已验证、`openai`、`minimax`（`embo-01`） |
| **降级** | `local` → `HashingEmbedder`（96 维 token hash），零外网，recall 有限但不影响功能 |
| **切换** | `.env` 设 `BUTLER_EMBEDDING_PROVIDER=fastembed` 即可，重启后自动 reindex |

**当前已验证的链路**：

```
HashingEmbedder (fallback) → fastembed (本地, ✅ 当前) → DashScope API (✅ 已验证)
```

### 2.3 定理验证器深化

| 项 | 说明 |
|----|------|
| **当前** | 10 个定理检查器（T01-T10），AST 级检查 ✅ 已实现 |
| **技术** | `ast.parse()` + visitor，AST 解析失败时回退 regex |
| **外部需求** | 无——Python `ast` 模块内置；未来可选接 `mypy` daemon 或 `ruff --fix` |
| **降级** | 始终可用：regex 启发式作为 L0 fallback |

**演进路径**（D3-5）：

| 阶段 | 技术 | 精度 | 外部依赖 | 状态 |
|------|------|------|----------|------|
| L0 | Regex 模式匹配 | ~60% | 无 | ✅ 作为 fallback |
| L1 | `ast.parse` + visitor | ~80% | 无 | ✅ 当前 |
| L2（可选） | `mypy --dmypy` / `ruff` | ~95% | mypy/ruff 安装 | — |
| L3（长期） | 形式验证（`crosshair` / SMT） | ~99% | crosshair 安装 | — |

### 2.4 经验挖掘 Agent

| 项 | 说明 |
|----|------|
| **D3-6** | 工作区/CHANGELOG/feed 挖掘 → `review_candidate`（CT3）→ 待审 `mining_pending.json` → 批准入库 |
| **委派路径** | 任务成功后 `extract_experience_candidate`（dual_verify 通过后） |
| **入口** | 微信 `/经验挖掘`；CLI `python -m butler.memory.experience_mining_cli` |
| **定时** | `builtin:experience_mining_weekly`（灵文 `experience-mining-weekly`，周日 04:00；`auto_ingest=False`） |
| **外部 feed** | `~/.butler/feeds/experience_feeds.jsonl`（每行 JSON） |
| **LLM 增强** | 未来 opt-in：`BUTLER_CODING_EXPERIENCE_LLM_EXTRACT=1` |
| **配置** | `BUTLER_EXPERIENCE_MINING*`、`BUTLER_EXPERIENCE_MINING_AUTO_INGEST` |

### 2.5 微信网关

| 项 | 说明 |
|----|------|
| **用途** | 用户入站消息、提醒推送、PIM 只读命令 |
| **依赖** | iLink WebSocket 服务 |
| **配置** | `WECHAT_TOKEN`、`WECHAT_ACCOUNT_ID` |
| **降级** | CLI 模式（`butler chat`）+ 本地 API（`butler serve`）可完全替代，仅丢失微信通道 |
| **限流缓解** | iLink rate limit 时入队 `durable_outbox`；`BUTLER_RUNTIME_PUSH_DRAIN_COOLDOWN_SECONDS`（默认 300s）冷却内跳过 drain；末批真机复验见 `pilot-log.md` |

### 2.6 语义记忆检索增强

| 项 | 说明 |
|----|------|
| **当前** | SQLite + 暴力 cosine（`SemanticMemoryIndex`） |
| **增强** | ChromaDB ✅ 已安装，`get_vector_store()` 自动优先使用 |
| **外部需求** | `chromadb` pip 包（本地运行，无需外部服务）✅ 已安装 |
| **降级** | `InMemoryVectorStore` 暴力搜索对 <10K 条记录性能足够 |
| **接入** | `get_vector_store()` 自动检测 ChromaDB 可用性，无需手动切换 |

### 2.7 Rerank 模型

| 项 | 说明 |
|----|------|
| **当前** | RRF 融合 + 时间衰减 + 访问频率加权（`retrieval_ranking.py`） |
| **增强** | Cross-encoder rerank 模型 |
| **API 选项** | Cohere Rerank API、Jina Rerank、本地 `sentence-transformers` |
| **降级** | 当前 RRF + 启发式对 ≤50 条候选足够 |
| **配置** | `BUTLER_RERANK_PROVIDER`（未来） |

---

## 3. 依赖分级汇总

| 等级 | 服务 | 说明 |
|------|------|------|
| **必需** | LLM Provider（任一） | 无法降级，是 Agent 核心 |
| **强烈推荐** | `fastembed` 本地 embedding | ✅ 已安装配置，无需外网 |
| **推荐** | iLink 微信网关 | 启用微信通道；CLI/API 可替代 |
| **可选** | OpenAI/MiniMax Embedding API | 比 fastembed 精度略高，需外网 |
| **可选** | ChromaDB | ✅ 已安装，自动生效 |
| **可选** | Rerank API | 检索精度微调，当前 RRF 够用 |
| **长期** | `crosshair` / SMT solver | 形式化定理验证，当前 regex+AST 够用 |

---

## 4. 最小可运行配置

```bash
# 最小配置（仅 CLI）
MINIMAX_API_KEY=sk-xxx          # 或 DEEPSEEK_API_KEY
BUTLER_EMBEDDING_PROVIDER=local  # 默认，无需显式设

# 推荐配置（CLI + 高质量检索）
MINIMAX_API_KEY=sk-xxx
BUTLER_EMBEDDING_PROVIDER=fastembed
BUTLER_SEMANTIC_MEMORY=1

# 完整配置（微信 + 高质量检索 + API Embedding）
MINIMAX_API_KEY=sk-xxx
BUTLER_EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-xxx
BUTLER_SEMANTIC_MEMORY=1
WECHAT_TOKEN=xxx
WECHAT_ACCOUNT_ID=xxx
```
