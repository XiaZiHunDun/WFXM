# 开发助手语料 v2 — 分析与测试设计

> **语料**：第二批 32 条单轮 + 2 组多轮（6 轮），覆盖迁移/调试/框架/算法/架构/运维/DB/安全/测试/工具/文本。  
> **模型**：**MiniMax-M2.7**（`LLMClient(provider="minimax", model=...)`，与 v1 一致）  
> **YAML**：[`tests/scenarios/dev_assistant_corpus_v2.yaml`](../../tests/scenarios/dev_assistant_corpus_v2.yaml)  
> **测试**：[`tests/test_dev_assistant_corpus_v2.py`](../../tests/test_dev_assistant_corpus_v2.py)  
> **共享 harness**：[`tests/corpus_harness.py`](../../tests/corpus_harness.py)

---

## 一、与 v1（DA-01…12）的关系

| 维度 | v1 | v2 |
|------|----|----|
| 定位 | 基础 12 类（生成/解释/Git/React…） | **实战痛点**与栈深度 |
| 条数 | 12 | **34**（32 单轮 + 2×3 轮多轮） |
| 多轮 | 1 组（unittest→pytest） | 2 组（装饰器链、Terraform RDS） |
| Butler 微信 | 另见 LW-REAL | v2 默认 **直连 AgentLoop** 评问答质量 |

---

## 二、语料分簇与场景 ID

| 簇 | 条数 | ID 范围 | 评测重点 |
|----|------|---------|----------|
| 代码转换与适配 | 3 | DA2-01～03 | Axios/Kotlin/CMake 关键词 |
| 调试与报错 | 3 | DA2-04～06 | Spring/FastAPI/编码 根因 |
| 框架与库 | 4 | DA2-07～10 | Nest/React/Go/Sequelize API |
| 算法与数据结构 | 2 | DA2-11～12 | O(1) 窗口 / 大文件 TopK 思路 |
| 系统设计 | 3 | DA2-13～15 | 短链/拆库/读写延迟 |
| 运维与部署 | 3 | DA2-16～18 | Docker TZ / K8s HPA / Ansible |
| 数据库与缓存 | 3 | DA2-19～21 | 最左前缀 / Redis 模式 / Seq Scan |
| 安全实践 | 3 | DA2-22～24 | JWT / SVG / OAuth CSRF |
| 测试 | 3 | DA2-25～27 | Jest / WS / pytest.raises |
| 效率工具 | 3 | DA2-28～30 | VSCode / bisect / find |
| 正则与文本 | 2 | DA2-31～32 | grep awk IPv4 / CSV 求和 |
| 多轮上下文 | 2×3 轮 | DA2-MT01/02 | logger 参数、TF 副本与 tags |

---

## 三、Rubric 设计原则

1. **must_contain**：硬性技术词（如 `axios`、`CORS`、`bisect`）。  
2. **must_contain_any / any2 / any3**：多组「至少命中其一」，模拟「答到点子上即可」——例如 DA2-01 需同时出现 axios、拦截器类词、token 类词。  
3. **不逐字比对**：避免模型用中文同义词导致误杀（v1 的 `total`→`总销售额` 已验证）。  
4. **多轮**：每轮独立 rubric，不强制第二轮重复贴第一轮代码（由 live 抽检上下文）。

---

## 四、测试分层

```text
L0  schema       — 34 cases、live_model=MiniMax-M2.7
L1  mock×32      — 注入 canonical 回答 → 全关键词命中
L1b mock×2 MT    — DA2-MT01/02 各 3 轮
L2  live 全量    — 32 单轮 parametrized（发版前可选，约 3～6 分钟）
L3  live smoke   — 5 条代表性单轮：04/06/12/19/22
L4  live MT      — DA2-MT01 + DA2-MT02（各 3 次 API）
```

### 命令

```bash
# CI 默认（mock，约数秒）
PYTHONPATH=. pytest tests/test_dev_assistant_corpus_v2.py -q

# 发版前快速 live 抽检（5 单轮 + 2 多轮 ≈ 7+6 次调用）
set -a && source .env && set +a
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \
  pytest -m live_llm tests/test_dev_assistant_corpus_v2.py::TestCorpusV2LiveMiniMax::test_live_smoke_subset -v

# 全量 live 32 单轮（耗时）
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \
  pytest -m live_llm tests/test_dev_assistant_corpus_v2.py::TestCorpusV2LiveMiniMax::test_live_single_turn_full -v
```

---

## 五、Butler 产品映射（可选通道）

| 语料类型 | 灵文 Lead 微信 | 建议 |
|----------|----------------|------|
| 写代码/改配置（01/11/18） | 委派 dev | 与 DA-01 v1 相同 |
| 纯知识问答（04～24 多数） | Lead 可直接答 | 用 v2 live 评模型 |
| 跑命令（30/31） | 慎开 terminal | rubric 只查命令文本 |
| 多轮（MT01/02） | 同 session | 依赖会话不 `/新对话` 打断 |

---

## 六、live_smoke 抽样理由

| ID | 为何入选 |
|----|----------|
| DA2-04 | Spring 配置类高频误报 |
| DA2-06 | CORS 需精确中间件名 |
| DA2-12 | 开放性「思路」题 |
| DA2-19 | 索引最左前缀易错 |
| DA2-22 | 安全权衡题 |
| DA2-MT01/02 | 多轮上下文（单独 live 用例） |

---

## 七、已知局限

- Mock 层**不验证**答案正确性，只验证 rubric 管道。  
- Live 全量 32 条对 API 耗时/费用较高，日常 CI 不跑。  
- 部分题（DA2-18 Ansible 回滚）模型可能给多种写法，需根据 live 失败迭代 `must_contain_any`。  
- 与微信 **LW-REAL**、**v1 DA** 三套互补，合并看才能覆盖「问答 + 工程链」。

---

## 八、后续扩充

新增语料时复制 yaml 条目，补全 `must_contain*` 三组即可；多轮用 `turns:` 列表。可选将 `live_smoke_ids` 轮换覆盖各维度。
