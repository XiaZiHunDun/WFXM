# 开发助手真实语料 — 分析与 Butler 测试映射

> **语料来源**：外部设计的 12 条开发场景（代码生成/解释/调试、工具、多轮、安全）。  
> **机器可读**：[`tests/scenarios/dev_assistant_corpus.yaml`](../../tests/scenarios/dev_assistant_corpus.yaml)  
> **自动化**：[`tests/test_dev_assistant_corpus.py`](../../tests/test_dev_assistant_corpus.py)

---

## 一、语料质量简评

| 维度 | 评价 |
|------|------|
| 覆盖度 | 覆盖开发日常高频 12 类，结构清晰（场景 + 输入 + 期望） |
| 可测性 | 期望回答多为**关键词可判定**（命令、API 名、概念），适合回归 rubric |
| 局限 | 未区分「纯聊天助手」与「Butler 厂长+委派」；Docker/PHP 等不在 Butler 默认工具链 |
| 建议 | 保留 12 条为 **DA-01…DA-12**；Butler 微信主路径另用 **LW-REAL**（真机对话） |

---

## 二、12 条语料 × Butler 能力矩阵

| ID | 场景 | 纯助手（CLI/直连 LLM） | 灵文1号 Lead（微信） | Butler 工具链 |
|----|------|------------------------|----------------------|---------------|
| DA-01 | Python 读 CSV | ✅ 直接生成代码 | ⚠️ 应 **delegate_task → dev** | dev: write_file |
| DA-02 | 字典推导式解释 | ✅ 纯文本 | ✅ 可文本或委派 | 通常无工具 |
| DA-03 | TypeError 调试 | ✅ 纯文本 | ✅ 可委派 dev | 无必须工具 |
| DA-04 | 冒泡排序优化 | ✅ 纯文本 | ✅ 可委派 | 无必须工具 |
| DA-05 | SQL LEFT JOIN | ✅ 纯文本 | ✅ 可文本 | 无 SQL 工具 |
| DA-06 | git reset --soft | ✅ 文本 + 可选 **git_*** | ✅ 文本；本机开 `BUTLER_ENABLE_GIT=1` 可查证 | git_status/diff/log |
| DA-07 | Docker nginx | ✅ 文本 | ✅ 文本（Lead 不跑 docker） | terminal 默认关 |
| DA-08 | 邮箱正则 | ✅ 文本 + 边界说明 | ✅ 文本 | 无 |
| DA-09 | REST 原则 | ✅ 文本 | ✅ 文本 | 无 |
| DA-10 | React useState | ✅ 文本 | ✅ 可委派 content/dev | 无 |
| DA-11 | unittest→pytest 多轮 | ✅ **上下文继承** | ✅ 同 session 多轮 | 记忆/会话 |
| DA-12 | PHP 密码硬编码 | ✅ **安全警告** | ✅ 必须警告 | 无 |

**结论**：12 条均适合评估 **「开发助手回答质量」**；其中 **DA-01** 在灵文 Lead 下行为应为委派，与「期望直接给代码」的 rubric 需在评测时分通道。

---

## 三、测试分层（已实现）

```text
L0  schema     — YAML 12 条齐全、字段合法
L1  mock+loop  — Mock LLM 注入含关键词的 canonical 回答 → AgentLoop → must_contain 断言
L2  lead-route — DA-01 经 gateway：必须 delegate_task、Lead 不 write_file
L3  live_llm   — 抽样 DA-03/06/12 真 MiniMax（默认 skip）
```

### 运行

```bash
# CI 默认（mock，约 1s）
PYTHONPATH=. pytest tests/test_dev_assistant_corpus.py -q

# 可选真模型（需 key）
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \
  pytest -m live_llm tests/test_dev_assistant_corpus.py::TestDevAssistantCorpusLive -v
```

### 本次执行结果（本地）

| 套件 | 结果 |
|------|------|
| `test_dev_assistant_corpus.py`（mock + schema + lead） | **26 passed**，12 deselected（`live_llm`） |
| `TestDevAssistantCorpusLive`（MiniMax 全 12 条） | **12 passed**（约 70s，2026-05-22） |
| 说明 | mock 验证 rubric 管道；live 验证真模型关键词覆盖 |

---

## 四、与 LW-REAL / 通用习惯场景关系

| 体系 | 侧重 |
|------|------|
| **DA-xx**（本文） | 通用开发助手 **问答质量** rubric |
| **LW-REAL** | 微信灵文 **委派/报告/删除/详细** 工程链 |
| **wechat-dev-conversation** | 习惯场景全集 |

三者互补，不互相替代。

---

## 五、语料改进建议（可选）

1. **分通道期望**：DA-01 增加 `lead_expect: delegate` 与 `direct_expect: code_block` 两套 must_contain。  
2. **DA-06**：增加 `butler_enable_git: true` 时允许工具调用 `git_log` 的变体。  
3. **DA-11**：显式写 `session_preserve: true` 与「第二轮不得重复贴出 divide 定义」。  
4. **DA-07**：标注 `out_of_scope_for_lead_terminal: true`，避免真机去开 terminal。  
5. 扩充语言/框架时保持 **must_contain / must_contain_any** 机器可判结构。

---

## 六、DA-01…DA-12 关键词 rubric 摘要

详见 yaml；核心判定：

- **DA-03**：`str` / `f-string` / `str(age)`  
- **DA-06**：`git reset --soft HEAD~1`  
- **DA-12**：环境变量或硬编码风险措辞  
- **DA-11 第 2 轮**：`pytest` + `raises`，且继承第 1 轮语境  

人工评测时可将「期望助手回答」全文与 `must_contain` 对照打分（满分 = 全命中 + 无 must_not）。
