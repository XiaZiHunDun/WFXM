# Butler CLI 人工测试用例

> 版本: v1.0 | 日期: 2026-05-20  
> 适用: `PYTHONPATH=. python -m butler.main chat` 交互场景  
> 配套自动化: `test_cli_scenarios.py` · `test_cli_dimensions.py` · `test_cli_live_smoke.py`

---

## 0. 测试前准备（5 分钟）

| 项 | 检查 |
|----|------|
| 工作目录 | `cd ~/projects/WFXM` |
| API | `MINIMAX_API_KEY` 已设置（或 `.env` 可读） |
| 启动命令 | `PYTHONPATH=. python -m butler.main chat` |
| 记录方式 | 建议开终端录屏或复制输出；用例 ID 填「记录表 §9」 |

**可选：跑自动化打底（不耗对话额度）**

```bash
PYTHONPATH=. pytest tests/test_cli_scenarios.py tests/test_cli_dimensions.py -q
```

**可选：跑真实 API smoke（约 10 秒）**

```bash
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. pytest -m live_llm tests/test_cli_live_smoke.py -v
```

---

## 1. 用例分级

| 级别 | 说明 | 建议 |
|------|------|------|
| **P0** | 每次发版 / 改 CLI 必测；失败即阻塞 | 约 15 分钟 |
| **P1** | 每周或较大功能变更后测 | 约 25 分钟 |
| **P2** | 专项能力 / 边界 / 可选工具 | 按需 |

---

## 2. P0 — 冒烟路径（必测）

> 按顺序执行；全部通过即可认为「CLI 主路径可用」。

### CLI-P0-01 启动与欢迎面板

| 步骤 | 操作 |
|------|------|
| 1 | 执行 `PYTHONPATH=. python -m butler.main chat` |

**预期**

- [ ] 蓝色边框欢迎 Panel（标题含 `Butler v4`）
- [ ] 面板内：管家名（如「莎丽」）、当前项目、`provider/model`
- [ ] 出现输入提示（如 `[Butler] >` 或 `[项目名] >`）
- [ ] 无 `?[36m` 等乱码、无重复欢迎 Panel

**失败特征**: 只有边框无正文、ANSI 乱码、启动 traceback

---

### CLI-P0-02 单轮问候与回复展示

| 步骤 | 操作 |
|------|------|
| 1 | 输入 `你好` 并回车 |

**预期**

- [ ] 约 30 秒内返回
- [ ] 莎丽 Panel：**有正文**（非空框），标题为管家名
- [ ] 同一段回复**不重复**打印两次
- [ ] 可见 tokens / 耗时等统计（多轮或工具时更明显）
- [ ] 正文中**无** `<think>`、`</thinking>` 等标签

**失败特征**: 无输出、双份相同内容、空 Panel、推理标签外露

---

### CLI-P0-03 多轮上下文（会话内记忆）

| 步骤 | 操作 |
|------|------|
| 1 | 输入 `我叫测试员` |
| 2 | 输入 `我叫什么？` |

**预期**

- [ ] 第二轮能答出「测试员」或明确引用刚才的自我介绍
- [ ] 两轮均有正常 Panel 展示

---

### CLI-P0-04 `/new` 清空与无后台报错

| 步骤 | 操作 |
|------|------|
| 1 | 接 P0-03，输入 `/new` |
| 2 | 输入 `我叫什么？` |
| 3 | 观察 `/new` 后终端是否多出错误行 |

**预期**

- [ ] 显示 `已清空对话历史`（或同等提示）
- [ ] **不出现** `Memory extraction failed` / `Skill extraction failed`
- [ ] **不出现** `can't be used in 'await'`
- [ ] `/new` 后仍可正常输入、正常回复
- [ ] 身份是否仍被答出：按产品设计记录（答出「测试员」= 记忆层保留，可接受）

**失败特征**: `/new` 后无法对话、后台提炼报错刷屏

---

### CLI-P0-05 正常退出

| 步骤 | 操作 |
|------|------|
| 1 | 输入 `/quit`（或 Ctrl+D） |

**预期**

- [ ] 正常回到 shell，退出码 0
- [ ] Ctrl+D 时可见「再见」类提示
- [ ] 无 traceback

---

## 3. P1 — 核心能力

### CLI-P1-01 流式长回复

| 步骤 | 输入 `请用 200 字介绍一下你能帮我做什么` |
|------|--------------------------------------|

**预期**

- [ ] 等待时出现 Rich **「思考中…」** 状态（dots）
- [ ] 回复阶段可见 **逐行** 输出（`╭ 莎丽` 边框盒 + `│` 行）
- [ ] 结束后 **不** 再重复整块 Panel 全文（仅统计行）
- [ ] 无乱码（重点看 `?[`、多余 `[36m]`）

> 调试：`BUTLER_CLI_STREAM_MODE=buffer` 可恢复旧「仅结束 Panel」行为。

---

### CLI-P1-02 工具读取文件

| 步骤 | 输入 `请读取 butler/cli/session_ui.py 的前 15 行并概括` |
|------|--------------------------------------------------------|

**预期**

- [ ] 出现工具行（`┊` + 📖 read 等）
- [ ] 统计含「工具调用」
- [ ] 回复内容与文件相关（非胡编）

---

### CLI-P1-03 `/status` 与 `/health`

| 步骤 | 1. `/status`  2. `/health` |
|------|---------------------------|

**预期**

- [ ] `/status`：管家名、项目、模型、Butler Home
- [ ] `/health`：诊断信息；有对话轮次时含 Loop/工具审计相关字段
- [ ] 均**不**触发一轮 LLM 对话（无莎丽回复 Panel）

---

### CLI-P1-04 `/help`、Tab 补全与未知斜杠

| 步骤 | 1. `/help`  2. 输入 `/he` + Tab  3. `/foobar` |
|------|-----------------------------------------------|

**预期**

- [ ] `/help` 列出 projects / switch / model / new / health / quit 等
- [ ] Tab 可补全为 `/help` 等内置命令
- [ ] `/foobar` 提示 **未知命令**，**不**调用 LLM、不消耗 API

---

### CLI-P1-05 空行忽略

| 步骤 | 直接连按两次回车，再输入 `ping` |
|------|--------------------------------|

**预期**

- [ ] 空行不触发回复
- [ ] 仅 `ping` 触发一轮对话

---

### CLI-P1-06 `butler exec` 单次执行

```bash
PYTHONPATH=. python -m butler.main exec "用一句话自我介绍"
```

**预期**

- [ ] 打印一句自我介绍后进程结束
- [ ] 有可见正文，无 thinking 标签
- [ ] 退出码 0

---

### CLI-P1-07 Ctrl+C 中断

| 步骤 | 输入较长问题后立刻 **Ctrl+C** |
|------|------------------------------|

**预期**

- [ ] 显示「已中断」或同等提示
- [ ] 不崩溃，可继续输入下一条
- [ ] 若已有部分流式缓冲，可能显示已缓冲片段（记录实际表现）

---

## 4. P1 — 斜杠命令专项

| ID | 操作 | 预期 | □ |
|----|------|------|---|
| CLI-P1-C01 | `/projects` | 列出项目或「暂无项目」 | |
| CLI-P1-C02 | `/switch <已有项目>` | 「已切换到项目」；提示符项目名变化 | |
| CLI-P1-C03 | `/switch 不存在` | 红色/明确「未找到」；不崩溃 | |
| CLI-P1-C04 | `/model` | 列出 butler / dev_agent / content_agent / review_agent | |
| CLI-P1-C05 | `/model butler minimax/MiniMax-M2.5` → `/status` → `你好` | 切换成功、对话正常 | |
| CLI-P1-C06 | 恢复 `/model butler minimax/MiniMax-M2.7` | 与默认一致 | |
| CLI-P1-C07 | `/steer 接下来优先读 README` | 提示已加入指引；下一轮行为可观察（主观） | |
| CLI-P1-C08 | `/detail` | 有委派报告则展示，否则「暂无」 | |
| CLI-P1-C09 | `/诊断` | 与 `/health` 等效 | |

---

## 5. P1 — 项目与提示符

| ID | 操作 | 预期 | □ |
|----|------|------|---|
| CLI-P1-P01 | `create cli-manual-test --type software -d "人工测试"` | 命令行创建成功 | |
| CLI-P1-P02 | chat 内 `/projects` | 列表含 `cli-manual-test` | |
| CLI-P1-P03 | `/switch cli-manual-test` | 提示符为 `[cli-manual-test] >` | |
| CLI-P1-P04 | 在项目下问「当前项目是什么」 | 回答与项目名一致或合理 | |

---

## 6. P2 — 边界与可选

### CLI-P2-01 `/new` 后「细节」vs「身份」

| 步骤 | 1. 聊具体事实：`项目 WFXM 使用 MiniMax-M2.7`  2. `/new`  3a. `我上一轮具体说了哪个模型？`  3b. `我叫测试员，请记住` → `/new` → `我叫什么` |
|------|--------------------------------------------------------------------------------------------------------------------------------------------------|

**记录**

- [ ] 3a：应**无法**复述上一轮细节（或明确表示不记得）
- [ ] 3b：身份是否保留（与 P0-04 一致，记录实际）

---

### CLI-P2-02 写文件与 diff（可选）

| 步骤 | `在 /tmp 或项目下创建 test-butler-cli.txt，写入 hello，再读取确认` |
|------|------------------------------------------------------------------|

**预期**

- [ ] write / read 工具行可见
- [ ] 若 patch/write，可能看到 inline diff（dim 块）

---

### CLI-P2-03 终端工具（需开启）

```bash
export BUTLER_ENABLE_TERMINAL=1
# 可选: export BUTLER_TOOL_SAFE_ROOT=~/projects/WFXM
```

| 步骤 | `执行 ls butler` |
|------|------------------|

**预期**

- [ ] terminal 工具调用成功或明确 guardrail 拒绝（记录哪一种）

---

### CLI-P2-04 推理显式开启（开发向）

```bash
BUTLER_CLI_SHOW_REASONING=1 PYTHONPATH=. python -m butler.main chat
```

| 步骤 | 输入 `你好` |
|------|-------------|

**预期**

- [ ] 额外出现「推理:」段落；默认关闭时不应出现

---

### CLI-P2-05 长会话后退出（post-session）

| 步骤 | 连续对话 ≥4 轮（可闲聊）→ `/quit` |
|------|-----------------------------------|

**预期**

- [ ] 退出正常
- [ ] 退出前/后无 post-session 相关 ERROR 日志（允许 debug 级静默失败，但不应刷屏）

---

## 7. 推荐执行套餐

**发版前自动化（建议先跑）：**

```bash
PYTHONPATH=. pytest tests/test_cli_stream_live.py tests/test_cli_scenarios.py \
  tests/test_cli_dimensions.py tests/test_cli_slash_commands.py -q
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. pytest -m live_llm tests/test_cli_live_smoke.py -v
```

### 套餐 A — 发版前最小集（≈15 分钟）

`P0-01` → `P0-02` → `P0-03` → `P0-04` → `P0-05` → `P1-06`

### 套餐 B — 完整 CLI 回归（≈45–60 分钟）

套餐 A + 全部 **P1** + 自选 **P2** 中与本次改动相关的项

### 套餐 C — 仅改显示/交互（本次重点）

`P0-01` `P0-02` `P0-04` `P1-01` `P1-04` `P1-07` + 自动化：

```bash
PYTHONPATH=. pytest tests/test_cli_scenarios.py tests/test_cli_dimensions.py -q
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. pytest -m live_llm tests/test_cli_live_smoke.py -v
```

---

## 8. 通过标准

| 级别 | 标准 |
|------|------|
| **通过** | P0 全部勾选；P1 无阻塞缺陷；已知问题已记入记录表 |
| **有条件通过** | P0 通过；P1 有非主路径问题（如 `/steer` 效果弱） |
| **不通过** | 任一 P0 失败：无回复、重复/乱码、/new 报错、无法退出 |

---

## 9. 测试记录表（复制使用）

```
测试人: ____________  日期: ____________  分支/提交: ____________
环境: Ubuntu _____  Python _____  模型: minimax/___________

| 用例 ID     | 结果 P/F | 备注 |
|-------------|----------|------|
| CLI-P0-01   |          |      |
| CLI-P0-02   |          |      |
| CLI-P0-03   |          |      |
| CLI-P0-04   |          |      |
| CLI-P0-05   |          |      |
| CLI-P1-01   |          |      |
| CLI-P1-02   |          |      |
| ...         |          |      |

结论: [ ] 通过  [ ] 有条件通过  [ ] 不通过
```

---

## 10. 与自动化的对应关系

| 人工 ID | 自动化参考 |
|---------|------------|
| P0-02 / P1-01 展示 | `test_cli_scenarios` · `TestFinishTurnDisplayRegression` |
| P0-04 `/new` | `test_cli_scenarios` · `TestScriptedInteractiveChat` |
| P1-04 斜杠 | `test_cli_dimensions` · `TestCliSlashCommandMatrix` |
| P1-06 exec | `test_cli_dimensions` · `TestCliExecMode` |
| 真实 MiniMax | `test_cli_live_smoke.py` |

---

## 11. 常见问题速查

| 现象 | 可能原因 | 建议 |
|------|----------|------|
| 只有 Panel 边框无字 | `finish_turn` 在 `patch_stdout` 内或 buffer 空 | 查 `main.py` 是否在 patch 外调用 `finish_turn` |
| 回复打印两遍 | 流式直写 + Panel 重复 | 查 `StreamRenderer` 是否仅缓冲 |
| `?[36m` 乱码 | Rich markup 未关闭 | 查 `highlight=False`、勿手写 ANSI |
| `/new` 后 await 报错 | post-session LLM 工厂非 async | 查 `auxiliary_llm_call_factory` |
| 流式不逐字 | 设计为结束统一 Panel | 非缺陷，除非要求实时 tty 刷新 |
