# 微信核心场景验收剧本

> **产品主路径**：微信 → 管家（莎丽）→ 当前项目 →（必要时）项目 Agent  
> **默认验收项目**：**`灵文1号`**（目录 `projects/LingWen1/`，`project.yaml` 中 `name: 灵文1号`）  
> **说明**：与仓库外「正式灵文」隔离；2026-05-20 真机曾用旧名「灵文」/`LingWen` 通过，路径与切换命令已按试点更名。  
> **CLI**：仅作 pytest 回归守门，本剧本不要求 CLI 逐步对照。

---

## 一、目标与范围

验证 Butler 能否在微信上完成「替代 Hermes、承接主路径开发协作」的核心闭环（本机 Claude Code/Cursor 为**主机工具**，不登记为 Butler 项目类型）：

1. 管家身份与状态可查  
2. 项目切换后，读写落在**项目 workspace**  
3. 需要动手时能通过 `delegate_task` 拉起 dev/content/review 代理  
4. 委派结果可摘要查看（`/详细`）  
5. `/新对话` 清空会话后，**项目记忆**仍可回答项目相关问题  
6. `/工作流` 跑项目 DAG（如 `novel-factory`）— 2026-05-20 真机已通过

**不在本剧本内**：CLI 流式体验、Hermes fallback、跨界面 §四 一致性。

**日常冒烟**：推送或重启网关后，用精简表 [wechat-daily-smoke-checklist.md](./wechat-daily-smoke-checklist.md)（含步骤 8 工作流）。  
**Owner 画像**：冒烟通过后见 [owner-profile-setup.md](./owner-profile-setup.md)。

---

## 二、前置条件

| 项 | 说明 |
|----|------|
| 网关 | `systemctl --user status butler-gateway` 或前台 `python -m butler.main gateway --platforms wechat` |
| LLM | `.env` 中 `MINIMAX_API_KEY` 有效 |
| 微信 | `butler wechat-setup` 扫码绑定；凭证在 `~/.butler/wechat/accounts/`，勿与 Hermes 抢 Bot |
| 项目 | 仓库内存在 `projects/LingWen1/project.yaml`，且 `name: 灵文1号`；建议 `.env` 设 `BUTLER_DEFAULT_PROJECT=灵文1号` |

**自动化守门（改 gateway/orchestrator 后必跑）：**

```bash
cd ~/projects/WFXM
PYTHONPATH=. python -m pytest \
  tests/test_project_session_isolation.py \
  tests/test_project_tools_filter.py \
  tests/test_report_format.py \
  tests/gateway/test_wechat_session_reset.py \
  tests/gateway/test_gateway_acceptance.py \
  tests/gateway/test_gateway_handler.py \
  tests/test_session_lifecycle.py \
  tests/test_post_session.py \
  -q
```

---

## 三、七步真机剧本

按顺序在微信私聊 Bot 执行。每步记录：**实际回复摘要**、**是否调工具**（看 `/health` 或日志）、**通过/失败**。

### 步骤 1：管家在线

| 项 | 内容 |
|----|------|
| 发送 | `/状态` 或 `/status` |
| 预期 | 含管家名（如「莎丽」）、当前项目、默认 Provider |
| 失败时查 | 网关是否运行；`logs/butler-gateway.log` 有无 inbound/outbound |

### 步骤 2：绑定项目

| 项 | 内容 |
|----|------|
| 发送 | `/切换 灵文1号` 或 `/switch 灵文1号`（也可用 `/项目` 确认列表中有 `灵文1号`） |
| 预期 | 「已切换到项目: 灵文1号」；再发 `/状态` 当前项目为 `灵文1号`；其它项目对话历史保留 |
| 注意 | 项目名以 `project.yaml` 的 `name` 为准，不是目录名 `LingWen1`；已设默认项目时可跳过本步 |
| 失败时查 | `projects/LingWen1/project.yaml` 是否存在；`ProjectManager` 日志 |

### 步骤 3：项目内只读（管家直调工具）

| 项 | 内容 |
|----|------|
| 发送 | `请读取当前项目 README 或 project.yaml 的前 20 行，用纯文字摘要` |
| 预期 | 内容与 `projects/LingWen1/` 下文件一致；回复适合微信（少 Markdown 符号） |
| 说明 | 已选项目时，`read_file` 根目录为项目 workspace，此步**不要求**委派 |
| 失败时查 | 是否仍停留在别的项目；路径是否落在 `projects/LingWen1` |

### 步骤 4：项目内写入（content 代理）

| 项 | 内容 |
|----|------|
| 发送 | `请交给内容代理：在 docs 目录写一份 wechat-smoke.md，标题「微信验收」，正文写今天日期和一句说明，不要改其他文件` |
| 预期 | 明确告知已委派；完成后 `projects/LingWen1/docs/wechat-smoke.md` 存在 |
| 验证 | 委派完成后微信侧先收**紧凑摘要**（headline + 文件统计）；发 `/详细` 看全文，或 `/详细 changes` / `/详细 变更` 只看文件列表；磁盘上确认文件 |
| 失败时查 | 模型是否未调用 `delegate_task`（见 §五）；API 超时；`read_file` 写权限 |

### 步骤 5：开发代理检查（dev 代理）

| 项 | 内容 |
|----|------|
| 发送 | `请委派开发代理：只检查 docs/wechat-smoke.md 是否存在并读前几行，把结论告诉我，不要改代码` |
| 预期 | `delegate_task` role=`dev`；回复含文件存在与否 |
| 失败时查 | 步骤 4 文件是否已创建；系统提示是否被「直接 read_file」绕过 |

### 步骤 6：会话重置

| 项 | 内容 |
|----|------|
| 发送 | `/新对话` 或 `/new` |
| 预期 | 「已清空对话历史。」 |
| 再发 | `我们刚才聊过什么？` |
| 预期 | **不应**复述步骤 3–5 的对话细节（AgentLoop 与本轮 `conversation` 经验已清） |
| 说明 | 仍可回答**当前项目**用途（步骤 7），那是项目记忆，不是上轮聊天 |

### 步骤 7：项目记忆（跨会话）

| 项 | 内容 |
|----|------|
| 发送 | `当前是什么项目？灵文1号项目是做什么的？` |
| 预期 | 能答「灵文1号」及小说工厂试点/内容类描述（来自 `project.yaml` 或 `ProjectMemory`） |
| 失败时查 | `projects/LingWen1/.butler/memory/`；`on_project_switch` 是否加载项目记忆 |

### 步骤 8：工作流 DAG（可选，建议纳入日常冒烟）

| 项 | 内容 |
|----|------|
| 发送 | `/工作流 list` |
| 预期 | 列出 `novel-factory` 等（灵文1号 `project.yaml` 已登记名称时会合并内置两阶段模板） |
| 发送 | `/工作流 run novel-factory 写一句个人助手验收说明` |
| 预期 | 返回 `draft` / `review` 两步摘要；可用 `/详细` 钻取；不应超过微信长度刷屏 |
| 失败时查 | 是否已 `/切换 灵文1号`；日志 `TaskOrchestrator`；`tests/test_workflows.py` |

---

**自动化模拟（不经 iLink，需 LLM key）**

| 脚本 | 范围 |
|------|------|
| `bash scripts/butler-wechat-owner-sim.sh --list` | 查看全部 track |
| `bash scripts/butler-wechat-owner-sim.sh --quick` | **推荐**：core + slash + memory + search（约 5–15 分钟） |
| `bash scripts/butler-wechat-owner-sim.sh` | 含 ext / delegate 全量 |
| `bash scripts/butler-wechat-owner-sim.sh --track ext,delegate` | MCP + 委派（步骤 4–5 写/读 `docs/owner-sim-smoke.md`） |
| `bash scripts/butler-wechat-core-sim.sh` | G1-11 子集（与 owner-sim `core` track 重叠） |

Manifest：`.butler/simulation/wechat-owner-scenarios.yaml`（可增删 case，不必改 Python）。委派验收写 `docs/owner-sim-smoke-{日期}.md`（已 gitignore，跑前清理旧文件）。

---

## 四、结果记录表

复制到 `manual-testing-guide.md` §六 或 issue 评论：

| 步骤 | 通过 | 备注（工具/耗时/异常） |
|------|------|------------------------|
| 1 /状态 | ☑ | |
| 2 /切换 灵文1号 | ☑ | 默认项目时可跳过；2026-05-22 复验 |
| 3 读项目文件 | ☑ | |
| 4 content 写 docs | ☑ | |
| 5 dev 检查文件 | ☑ | |
| 6 /新对话 | ☑ | 不复述上轮细节（需重启 gateway 加载修复） |
| 7 项目记忆 | ☑ | |
| 8 /工作流 novel-factory | ☑ | list + run + /详细；2026-05-22 复验 |

**批次**：2026-05-20 真机（项目名灵文）| 2026-05-21 灵文1号首轮 | **2026-05-22 复验通过**（见 [wechat-daily-smoke-checklist.md](./wechat-daily-smoke-checklist.md)）

---

## 五、常见问题

### 5.1 简单对话不触发 `delegate_task`

**原因**：管家拥有 `read_file`/`write_file`，模型可能直接在管家层操作；或用户指令不够明确。

**处理**：

- 使用剧本中的「交给内容代理 / 委派开发代理」等明确措辞  
- 系统提示已强调：涉及**改项目文件、跑命令、多步开发**时必须 `delegate_task`（见 `butler/prompts/butler_system.md`）  
- 真机仍不委派时：发 `/health` 看 `工具调用` 计数；查日志 `delegate_task`

### 5.2 回复超过 2000 字

委派回合默认走 `format_for_wechat` 紧凑摘要；其它回合在 `wechat_response_text` 中截断为 1997+`...`。需要全文时用 `/详细`；需要某一段时用 `/详细 changes|decisions|issues`（中文别名：`变更`、`决策`、`问题`）。

### 5.2b 项目工具白名单

`project.yaml` 的 `tools` 列表会限制管家/委派 Agent 可见工具（别名：`edit_file`→`patch`，`search_code`→`search_files`，`run_shell`→`terminal`，`skill_list`→`skills_list`）。管家层始终保留 `delegate_task`、`skills_list`、`skill_view`。列表为空表示不限制。

### 5.3 `/切换` 后行为异常

`/切换` **不会**清空其它项目的对话历史（Session 键含项目名）。若看到别的项目上下文，检查 `/状态` 当前项目；workspace 与 `ProjectMemory` 应随 `current_project` 更新。

### 5.4 与 Hermes 混淆

Butler 凭证：`~/.butler/`；Hermes：`~/.hermes/`。开发机勿同时拉起两个 gateway 抢同一 Bot。

---

## 六、代码改动优先级（剧本失败时）

| 优先级 | 区域 | 典型修复 |
|--------|------|----------|
| P0 | `butler/gateway/message_handler.py` | 截断、斜杠、platform 格式化 |
| P0 | `butler/orchestrator.py` + `butler/prompts/butler_system.md` | 委派规则、项目上下文 |
| P1 | `butler/tools/registry.py` | `delegate_task`、workspace 根 |
| P1 | `butler/project_manager.py` | 切换、模糊匹配项目名 |
| P2 | `butler/report.py` | `/详细` 与微信摘要格式 |
| 延后 | `butler/cli/*` | 除非共用 AgentLoop 回归失败 |

---

## 七、相关文档

- [wechat-daily-smoke-checklist.md](./wechat-daily-smoke-checklist.md) — 可复制检查表（运维 + 步骤 0–8，灵文1号）  
- [projects/LingWen1/docs/pilot-setup.md](../../projects/LingWen1/docs/pilot-setup.md) — 试点说明  
- [owner-profile-setup.md](./owner-profile-setup.md) — Owner 画像模板与验证  
- [manual-testing-guide.md](./manual-testing-guide.md) §三（网关与斜杠）、§六（记录表）  
- [hermes-decoupling.md](../architecture/hermes-decoupling.md)  
- [design.md](../design/design.md) §1.2（产品痛点）
