# 开发助手语料 v3 — 生成方案（可复用）

> **目标**：在 v1/v2 之外，用**可重复的槽位法**批量产出「正常中文开发对话」语料，先扩覆盖、再统一 live 归档、最后做宏观问题地图。  
> **产出**：[`tests/scenarios/dev_assistant_corpus_v3.yaml`](../../tests/scenarios/dev_assistant_corpus_v3.yaml)（**39 条**：36 单轮 + 3 组×3 轮多轮）

---

## 一、生成哲学（与 v2 的差异）

| 原则 | v2 | v3 |
|------|----|----|
| 问法 | 技术栈痛点、偏「考题」 | **口语化、带上下文碎片**（日志片段、改口、先讨论再写） |
| 维度 | 迁移/调试/框架/运维… | **对话控制、评审、可观测、事故、Butler 产品句** |
| Rubric | 技术词命中 | 同 harness，但 **any 组更宽**，减少 live 表述漂移误杀 |
| 用途 | 单轮质量 | **为「跑一轮 → 归类失败」**服务，不追求首轮 100% pass |

---

## 二、槽位矩阵（Slot = 一条语料）

每条语料由五元组定义，生成时填表再落 YAML：

```text
S = (维度 D, 意图 I, 难度 L, 问法风格 U, 期望形态 E)
```

### 2.1 维度 D（v3 共 12 类 × 3 单轮 = 36）

| 代码 | 维度 | 单轮条数 | 典型用户说法 |
|------|------|----------|--------------|
| `conversational` | 对话控制 | 3 | 「先别写代码」「改成…」「只要思路」 |
| `code_review` | 代码评审 | 3 | 「帮看下这段 PR」「有没有竞态」 |
| `performance` | 性能 | 3 | 「接口 P99 高」「内存涨」 |
| `observability` | 可观测 | 3 | 「日志里全是 timeout」「trace 断了」 |
| `api_design` | API/契约 | 3 | 「Breaking change」「版本兼容」 |
| `data_engineering` | 数据工程 | 3 | 「Airflow 失败重试」「幂等写入」 |
| `incident_ops` | 事故/值班 | 3 | 「凌晨告警」「回滚步骤」 |
| `git_advanced` | Git 进阶 | 3 | `rebase` 冲突、`cherry-pick` |
| `messaging` | 消息队列 | 3 | Kafka 重复消费、Rabbit 死信 |
| `graphql_api` | GraphQL | 3 | N+1、分页、错误格式 |
| `product_butler` | Butler/灵文产品句 | 3 | 项目路径、委派、进度（与 LW-REAL 互补） |
| `safety_bounds` | 安全边界 | 3 | 拒绝删库、生产变更确认 |

### 2.2 意图 I（每条必选其一）

- `clarify` — 先要澄清/步骤，不立刻堆代码  
- `implement` — 要可运行示例或配置片段  
- `diagnose` — 贴错误/日志求根因  
- `compare` — A vs B 选型  
- `refine` — 在上一轮基础上改需求（**仅多轮**）  
- `delegate` — 期望提到委派/项目/开发者（**product_butler**）

### 2.3 难度 L

- `L1` 单技术点、一句问  
- `L2` 带 2～5 行上下文（日志、配置片段）  
- `L3` 多约束（性能+安全、兼容+迁移）

### 2.4 问法风格 U

- `oral` — 口语、无标点严谨要求  
- `paste` — 用户粘贴栈/日志  
- `imperative` — 「帮我」「给个」  

### 2.5 期望形态 E（写入 rubric，不写入 user）

- `explain` — `must_contain_any` 偏概念词  
- `snippet` — 必须出现语言/工具名 + API 名  
- `command` — 出现 CLI/命令关键词  
- `refuse_or_confirm` — `safety_bounds`：`must_contain_any` 含确认/备份/禁止  

---

## 三、Rubric 自动生成规则

对每条 `user` 文本，按维度套用模板（生成器人工/Agent 执行同一规则）：

1. **硬词** `must_contain`：至多 1 个，且优先英文技术名（大小写不敏感）。  
2. **any 组**：每组 3～6 个同义词（中英文混排）。  
3. **any2/any3**：第二、三组表达「答到另一侧面」；避免互斥过窄。  
4. **must_not_contain**（可选）：`safety_bounds` 禁止「直接执行 rm -rf」类鼓励句 — 用 `删库` + 要求出现 `确认|备份|staging`。  
5. **多轮**：每轮独立 rubric；首轮放宽（v2 DA2-MT01 教训）。  
6. **不生成**逐字标准答案 — mock 层用 `build_canonical_answer` 拼关键词即可。

---

## 四、多轮链（3 组 × 3 轮）

| ID | 链式意图 | 轮次叙事 |
|----|----------|----------|
| DA3-MT01 | clarify → implement → refine | 短链服务设计 → 要 FastAPI 骨架 → 加限流 |
| DA3-MT02 | implement → refine → test | Express 路由 → 加 JWT → supertest |
| DA3-MT03 | diagnose → diagnose → implement | 贴日志 → 追问指标 → 给修复清单 |

---

## 五、ID 与版本

- 单轮：`DA3-01` … `DA3-36`（按维度块顺序编号）  
- 多轮：`DA3-MT01` … `DA3-MT03`  
- `meta.version`: `2026-05-23-v3`  
- `live_model`: `MiniMax-M2.7`（与 v1/v2 可比）  
- `live_smoke_ids`: 每维度抽 1 条共 6 条 + 不抽 MT（MT 单独 live 用例）

---

## 六、生成流水线（以后扩 v4 时复用）

```text
1. 填槽位表（CSV/表格）→ D,I,L,U,E
2. 按模板写 user 中文（oral/paste）
3. 按第三节规则写 must_contain*
4. 校验 YAML schema（pytest TestCorpusV3Schema）
5. mock 全量（秒级）
6. 归档 live 一轮 → docs/plans/corpus-live-run-*.md（失败分类，不改断言优先）
7. 宏观优化方案（工具预算、路由、话术）再改产品
```

---

## 七、与 v1/v2/LW-REAL 的关系

| 套件 | 条数 | 角色 |
|------|------|------|
| v1 DA | 12～35 | 基础能力 |
| v2 DA2 | 34 | 栈深度痛点 |
| **v3 DA3** | **39** | **正常对话 + 产品句 + 事故/可观测** |
| LW-REAL | 16 | 微信真机工程链 |

v3 **不替代** v2 live 回归；三套合并跑一轮后做「问题地图」。

---

## 八、本次已生成文件

| 文件 | 说明 |
|------|------|
| `tests/scenarios/dev_assistant_corpus_v3.yaml` | 39 条语料 |
| `tests/test_dev_assistant_corpus_v3.py` | mock + live 分层 |
| `docs/plans/dev-assistant-corpus-v3-analysis-2026-05.md` | 分簇索引与命令 |
