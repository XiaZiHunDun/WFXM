# 微信开发者日常对话场景 — 自动化测试设计

> **目的**：在你再次真机验收前，用「开发者日常行为习惯」组织一套可重复的对话剧本，默认 **mock LLM + 真工具 + 真 handler**，覆盖 P0/P1（`delete_file`、委派成败、`/详细` 话术）及 Lead 边界。  
> **真机黄金路径（优先）**：[`wechat-real-dialogue-test-scenarios-2026-05.md`](wechat-real-dialogue-test-scenarios-2026-05.md) — 2026-05-22 鹿角象对话衍射。  
> **机器可读目录**：[`tests/scenarios/wechat_dev_conversations.yaml`](../../../tests/scenarios/wechat_dev_conversations.yaml)  
> **实现入口**：[`tests/test_gateway_dev_conversations.py`](../../../tests/test_gateway_dev_conversations.py)  
> **与既有关系**：补全 [`test_gateway_acceptance.py`](../../../tests/test_gateway_acceptance.py) / [wechat-core-scenario.md](../../guides/wechat-core-scenario.md) 未覆盖的**开发协作微流程**，不替代 live_llm 真机。

---

## 一、设计原则

| 原则 | 说明 |
|------|------|
| **行为驱动** | 按开发者一天中会发的自然语言组织，而非按 API 罗列 |
| **两层自动化** | L1：mock LLM 编排 tool 序列（CI 默认）；L2：`live_llm` 抽检模型是否「选对工具」（发版前可选） |
| **真工具假大脑** | `dispatch_tool`、`delegate_task` 子循环、磁盘读写为真；仅 `LLMClient.complete/stream` 为剧本 |
| **可观测断言** | 磁盘、报告缓存、`get_last_report(session_key)`、handler 输出、工具审计四类证据 |
| **项目双轨** | **通用试点**（`test-project`）跑得快；**灵文1号 Lead**（`灵文1号` + `gateway_loop_role=lead`）覆盖厂长边界 |
| **与真机对齐** | 每个场景 ID 映射 [wechat-daily-smoke-checklist.md](../../guides/wechat-daily-smoke-checklist.md) 步骤或「真机扩展」 |

---

## 二、开发者日常行为 → 场景簇

```mermaid
flowchart TB
  subgraph morning["到岗 / 切换上下文"]
    A1[查状态 / 切项目]
    A2[读 README 或 state]
  end
  subgraph build["动手改仓库"]
    B1[只读探查]
    B2[委派写文档]
    B3[委派改代码 patch]
    B4[委派删临时文件]
    B5[委派失败与重试语义]
  end
  subgraph review["收尾 / 审查"]
    C1[dev 只读检查]
    C2[review 代理]
    C3[看紧凑摘要 + /详细]
  end
  subgraph session["会话与记忆"]
    D1[/新对话 清聊天]
    D2[项目记忆仍在]
    D3[跨 chat 项目绑定]
  end
  subgraph ops["运维与模板"]
    E1[/health /诊断]
    E2[/工作流 run]
    E3[runtime 只读 job]
  end
  morning --> build --> review --> session
  build --> ops
```

---

## 三、场景目录（完整）

### 簇 A — 到岗与项目上下文

| ID | 名称 | 用户话术（示例） | Mock LLM 剧本要点 | 断言要点 | 已有覆盖 |
|----|------|------------------|-------------------|----------|----------|
| A-01 | 管家在线 | `/状态` | 无 LLM | 含项目名、Provider | acceptance + handler |
| A-02 | 切换灵文 | `/切换 灵文1号` | 无 LLM | 当前项目=灵文1号；Lead 提示后缀 | handler + project_lead |
| A-03 | 读项目概况 | `请读 README 前 20 行，不要委派` | `read_file` → 文本总结 | 无 `delegate_task`；内容含 README | acceptance §3 |
| A-04 | 读 workflow state | `读 novel-factory/workflow_state.json 摘要` | `read_file` | 路径落在 workspace | **新增** DEV |

### 簇 B — 文件 CRUD（开发主路径）

| ID | 名称 | 用户话术 | Mock 剧本 | 断言 | 已有 |
|----|------|----------|-----------|------|------|
| B-01 | 委派创建 | `交给内容代理：写 docs/smoke.md …` | Lead:`delegate_task`→子:`write_file` | 文件存在；摘要含「详细」；`success=True` | acceptance |
| B-02 | 委派删除成功 | `交给开发代理：删除 docs/smoke.md` | Lead:`delegate_task`→子:`delete_file` | 文件不存在；report `deleted`；headline 已完成 | **新增** DEV |
| B-03 | 委派删除失败 | `删除 docs/不存在.txt` | 子循环仅 tool error | `success=False`；headline 未能完成；`issues` 非空；微信含 ⚠ | **新增** DEV |
| B-04 | 委派 patch | `改 docs/x.py 把 foo 改成 bar` | `delegate_task`→`patch` | 磁盘内容变更；changes `modified` | **新增** DEV |
| B-05 | Lead 禁止直写 | `你直接 write_file 创建 a.txt` | 若模型调 write → 工具拒绝或未在 allowlist | Lead 轮次无成功 `write_file` | project_lead 单测 + **DEV 对话** |
| B-06 | 禁止 terminal 删 | `用终端 rm 删文件` | 不应引导用户选 shell；应 `delete_file` 委派 | 子工具名无 `terminal` 或 audit 无 rm | **新增** DEV（审计） |

### 簇 C — 报告与「看细节」

| ID | 名称 | 用户话术 | Mock | 断言 | 已有 |
|----|------|----------|------|------|------|
| C-01 | `/详细` | `/详细` | 无 LLM | 含 changes / summary；不调 loop | acceptance |
| C-02 | 中文别名 | `详细` / `详细信息` / `我要看一下详细信息` | 无 LLM | 等价 `/详细`；不调 LLM | handler + **DEV** |
| C-03 | 分节 | `/详细 变更` | 无 LLM | 仅文件列表 | acceptance |
| C-04 | 任务标注 | 委派删除后 `/详细` | 无 LLM | 首行 `【本报告任务】删除 …` | **新增** DEV |
| C-05 | 失败报告不串台 | 先创建报告再删除失败再 `/详细` | 两轮 delegate | 第二次 `/详细` 为删除任务 preview，非创建 | **新增** DEV |
| C-06 | 失败微信卡片 | （接上）紧凑回复 | — | 含「未能完成」与 issue 摘要 | **新增** DEV |

### 簇 D — 审查与只读委派

| ID | 名称 | 用户话术 | Mock | 断言 | 已有 |
|----|------|----------|------|------|------|
| D-01 | dev 只读 | `委派开发代理：只读检查 docs/x 是否存在` | `delegate`→`read_file` | 无 `write_file`/`delete_file` | acceptance §5 |
| D-02 | review | `委派审核：看 docs/x 结构` | `delegate` role=review | 回复含审查语气（文本 mock） | 可选 live |

### 簇 E — 会话、记忆、多 chat

| ID | 名称 | 用户话术 | Mock | 断言 | 已有 |
|----|------|----------|------|------|------|
| E-01 | 新对话清聊天 | `/新对话` → `刚才聊啥` | 第二轮文本否认上轮细节 | 无步骤 3–5 复述 | acceptance §6 |
| E-02 | 项目记忆仍在 | `当前什么项目？做什么的？` | 文本答项目 | 含灵文/试点描述 | acceptance §7 |
| E-03 | 双 chat 隔离 | u1 委派写；u2 `/详细` | 分 session_key | u2 无 u1 报告 | handler session |

### 簇 F — 工作流与运维

| ID | 名称 | 用户话术 | Mock | 断言 | 已有 |
|----|------|----------|------|------|------|
| F-01 | 工作流 list/run | `/工作流 list` / `run …` | patch WorkflowRunner | `/详细` 含 workflow 名 | acceptance §8 |
| F-02 | health | `/health` | 无 LLM | 结构化摘要字段 | handler |
| F-03 | steer 排队 | 长任务中 `/指引 先别改 X` | steer 桶 | 下轮注入指引 | test_steer_sessions（非对话） |

### 簇 G — 异常与边界（开发常遇）

| ID | 名称 | 用户话术 | Mock | 断言 | 已有 |
|----|------|----------|------|------|------|
| G-01 | 超长回复截断 | 委派返回 >2000 字 | 长 summary | `len(out)<=2000` | handler truncation |
| G-02 | 路径越界 | `读 ../../../etc/passwd` | `read_file` error | error 不入 success changes | registry 单测 |
| G-03 | 并发 /详细 | 委派进行中发 `/详细` | 可选 | 旧报告或提示暂无 | **暂缓** |
| G-04 | 删目录被拒 | `delete_file` 对目录 | tool error | issues 含 regular files | registry 单测 |

---

## 四、推荐自动化执行顺序

人工测试前在本地跑（约 30–60 秒）：

```bash
cd ~/projects/WFXM
PYTHONPATH=. pytest tests/test_gateway_dev_conversations.py -q
PYTHONPATH=. pytest tests/test_gateway_acceptance.py tests/test_gateway_handler.py -q
bash scripts/butler-wechat-gateway-smoke.sh
```

发版前可选 live 抽检（验证模型**是否**会选 `delegate_task`，非 CI 必过）：

```bash
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \
  pytest -m live_llm tests/test_wechat_gateway_live_smoke.py -v
```

建议为 live 增加（待实现）：

- `test_live_delegate_delete_file` — 真机步骤 B-02 对应
- `test_live_detail_alias_详细信息` — C-02

---

## 五、Mock LLM 剧本模板

与 [`test_gateway_acceptance.py`](../../../tests/test_gateway_acceptance.py) 相同辅助函数：

```python
_tool_response("delegate_task", {"role": "dev", "task": "删除 docs/smoke.md"})
_tool_response("delete_file", {"path": "docs/smoke.md"})
_text_response("已删除。")
# Lead 外层再一轮总结
_text_response("已委派开发代理删除，发 /详细 查看。")
```

**子代理循环**：`patch_llm` 的 `side_effect` 列表按 **调用次序** 消费；父 Lead 与子 dev 共用同一 mock（与 acceptance 一致）。

**session_key**：`wechat:{chat_id}:{project_name}`，灵文为 `wechat:u1:灵文1号`。

---

## 六、断言清单（按场景类型）

| 类型 | 函数/来源 | 示例 |
|------|-----------|------|
| 磁盘 | `Path.is_file()` | B-02 删除后不存在 |
| 报告 | `get_last_report(sk)` | `success`, `task_preview`, `changes[].action` |
| 微信文案 | `handle_message` 返回值 | `未能完成`, `详细`, `⚠` |
| 无 LLM | `mock_get_loop.assert_not_called` | C-02 别名 |
| 工具审计 | `spy.call_args_list` | D-01 无 write；B-05 无 Lead write |
| 允许列表 | `allowed_tool_names_for_project(..., role="lead")` | B-05 静态 |

---

## 七、实现状态（2026-05-22）

| 场景 ID | 自动化文件 | 状态 |
|---------|------------|------|
| B-02, B-03, C-02, C-04, C-05, C-06, B-05 | `test_gateway_dev_conversations.py` | ✅ 首批 |
| A-03, B-01, D-01, E-01… | `test_gateway_acceptance.py` | ✅ 已有 |
| A-04, B-04, B-06, D-02, G-03 | yaml 已登记 | 📋 待补 |
| B-02, C-02 live | `test_wechat_gateway_live_smoke.py` | 📋 待补 |

---

## 八、真机人工测试对照表

自动化通过后，真机按此顺序复验（约 10 分钟，聚焦新能力）：

1. `/切换 灵文1号` → `/状态`
2. 委派创建 `docs/wechat-auto-{date}.md`（内容代理）
3. `详细信息` → 应出现完整报告（非仅短卡片）
4. 委派删除该文件（开发代理）→ 磁盘确认无文件
5. 再发 `详细信息` → 标题应为「未能完成」或「已完成」且 **【本报告任务】** 为删除句
6. `/新对话` → `刚才删了哪个文件？` → 不应编造上轮路径

完整八步仍见 [wechat-core-scenario.md](../../guides/wechat-core-scenario.md)。

---

## 九、维护约定

- 新增用户可见行为 → 在 yaml 增场景 ID → 在 `test_gateway_dev_conversations.py` 或 acceptance 实现 → 更新本表 §七。
- 场景 ID 稳定，便于 CI 日志与真机记录表交叉引用。
- 不把真机临时文件路径写进场景默认路径；统一 `docs/.wechat-scenario-*` 前缀便于 `.gitignore`。
