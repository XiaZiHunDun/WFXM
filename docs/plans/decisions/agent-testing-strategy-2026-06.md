# Agent 软件测试策略（LLM 时代）

> **状态**：已采纳（2026-06-25）  
> **范围**：Butler v4 全栈测试分层、断言契约、CI 与真机分工  
> **关联**：[`tests/README.md`](../../../tests/README.md) · [`evaluation-guide.md`](../../guides/evaluation-guide.md) · [`pilot-project-dev-testing.md`](../../guides/pilot-project-dev-testing.md)

---

## 1. 结论（30 秒）

| 问题 | 答案 |
|------|------|
| 传统单元测试还有用吗？ | **有用**——凡是不经过 LLM 的代码，标准不变 |
| pytest 自动化还有用吗？ | **有用**——但要 **分层 + 换断言**（契约/文件/工具，而非全文措辞） |
| LLM 随机性怎么办？ | **拆四层**：确定性 CI · 编排 replay · handler sim · live/运营 |

**不做**：在默认 CI 里对 LLM 全文做 `assert reply == "..."`；不把真机飞轮失败等同于单元测试回归。

---

## 2. 四层测试模型

```text
L-A 确定性层     Gateway / 工具 / 配置 / 格式化 / 出站附件     → 硬断言，PR 必绿
L-B 编排层       AgentLoop + tool_batch（mock LLM 脚本）      → 轮次/工具/状态契约
L-C 行为层       handler sim / pilot gate / 文件落地          → 关键词 + 文件契约
L-D 质量层       live_llm / corpus_live / LangFuse / G1-04   → 阈值 + 归档 + 真机签收
```

### L-A 确定性层（传统 pytest 完全适用）

**测什么**：斜杠命令路由、Owner 门控、队列、session、出站 `.txt` 附件、`format_detail`、VERIFY、env 契约。

**守门示例**：

- `bash scripts/butler-pytest-fast-gate.sh`
- `bash scripts/butler-domain-pytest.sh gateway`
- `tests/test_wechat_text_export.py`、`tests/gateway/test_wechat_attach_detail.py`

**断言**：精确字符串、路径、状态码、副作用（文件存在/不存在）。

### L-B 编排层（mock LLM，测 Loop 怎么用模型）

**测什么**：多轮 tool loop、`LoopStatus`、工具调用次数、schema 降级路径、压缩触发条件。

**手段**：`tests/fixtures/llm_responses/*.json` + `mock_client_from_script()`（见 [`tests/fixtures/llm_responses/README.md`](../../../tests/fixtures/llm_responses/README.md)）。

**断言**：`tool_calls_made`、`iterations`、工具名序列；**不断言**模型措辞。

**守门**：`PYTHONPATH=. pytest tests/test_llm_response_fixtures.py -q`

### L-C 行为层（handler sim，可含真 LLM opt-in）

**测什么**：微信话术 → `ButlerMessageHandler` → 委派/task_id/项目文件/禁止工具。

**手段**：`butler-wechat-*-sim.sh`、`wechat_scenario_sim` manifest（`expect_reply_any`、`verify_file_contains`）。

**断言**：文件契约、task_id、role、关键词集合；长回复用「包含」不用「相等」。

**守门**：

- 快：`butler-pilot-dev-testing.sh --no-delegate`
- 慢（需 key）：`butler-wechat-dev-delegate-sim.sh`

### L-D 质量层（概率性，不进默认 CI 硬失败）

**测什么**：意图路由准确率、委派质量、语料 rubric、生产硬反馈（OT2）。

**手段**：`live_llm`、`corpus_live`、`test_premise_v3_llm_live.py`、LangFuse、`butler-dev-flywheel-monthly.sh`、`pilot-log` 真机签收。

**断言**：通过率阈值（如 P-PIM 94%）、归档后人工归类；**允许 flaky**，用趋势而不是单次 pass。

---

## 3. CI / 本地门禁矩阵

| 门禁 | 触发 | LLM | 失败含义 |
|------|------|-----|----------|
| `ci.yml` pytest（`-m 'not live_llm'`） | push/PR | ❌ | 确定性回归 |
| `fast-gate` job | PR | ❌ | gateway + attach + CC |
| `corpus_mock` | CI / 本地 | mock | 语料管道 |
| `butler-pilot-dev-testing.sh` | 本地/周 | opt-in delegate | 试点飞轮 |
| `corpus_live` / `live_llm` | nightly / 手动 | ✅ | 模型质量 |
| 月度 `butler-dev-flywheel-monthly.sh` | 月 | ✅ | 运营 gate |
| 真机微信 | 人 | ✅ | pilot-log 签收 |
| **全量** `pytest tests/` | **维护者可选** | 混合 | **非发版阻塞**；~101 fail 技术债（`test_tools_registry` 跨测状态，见 `pilot-log`） |

默认 `pyproject.toml`：`addopts = "-m 'not live_llm'"` — **禁止**把真 API 拉进 PR 硬门禁。

---

## 4. 断言契约（Do / Don't）

### Do

- 对 **纯函数**（`format_*`、`build_health_report`、出站路径解析）做金标/快照
- 对 **工具调用** 断言 `name` + 必要参数键
- 对 **委派** 断言 `task_id`、`role`、workspace 下文件 `verify_file_contains`
- 对 **网关** 断言 `exports/*.txt` 路径行、`send_document` 无异常（日志）

### Don't

- 不断言 LLM 完整回复与某次真机截图一致
- 不把 `butler-wechat-dev-delegate-sim` 失败当「单元测试挂了」而不看是否 key/配额/模型漂移
- 不用单次 live 用例 100% 绿作为发版唯一条件
- 不把 Cursor/外部 IDE Agent 当 Butler Loop 的替代单测

---

## 5. 与本仓库现有资产的对齐

| 已有 | 在本策略中的层 |
|------|----------------|
| ~6500 默认 pytest | L-A + 部分 L-B |
| `tests/test_llm_response_fixtures.py` | L-B（新增 replay） |
| `wechat_scenario_sim` / pilot 脚本 | L-C |
| `tests/corpus/` mock vs live | L-B mock / L-D live |
| `evaluation-guide` + LangFuse | L-D 观测 |
| `theory-implementation-gap-register` G1-04 | L-D 生产硬反馈窗 |

---

## 6. 改进路线（已启动 / 后续）

| 优先级 | 项 | 状态 |
|--------|-----|------|
| P0 | 本文 + `tests/README.md` 原则节 | ✅ 2026-06-25 |
| P0 | PROD-P0-02/03 配置剖面 + gate 叙事 | ✅ 2026-06-26 |
| P0 | PROD-P0-01 `/反馈` + `/诊断` OT2 面 | ✅ 2026-06-26 |
| P2 | `tests/fixtures/llm_responses/` + `test_llm_response_fixtures.py` | ✅ 2026-06-25 |
| P2+ | 扩 manifest sim（更多契约，少措辞） | 持续 |
| P3 | corpus live 通过率仪表盘 + issue map 周报 | 运营 |
| P4 | `/详细` 附 `.txt` 时强制短摘要（`BUTLER_WECHAT_ATTACH_BRIEF_CHARS`，默认 280） | **done** |

---

## 7. 提需求 / 否决

- 新测默认写入 `tests/<domain>/`，遵循 marker（见 `tests/README.md`）
- 要把 `live_llm` 纳入 PR 硬绿 → **否决**（除非单独 job + secret + 阈值，且不与确定性 pytest 混跑）
- 理论对齐登记：重大测试哲学变更记入本文 §6，不重复开平行文档

---

## 8. 相关

- [`roadmap-backlog-and-boundaries-2026-05.md`](roadmap-backlog-and-boundaries-2026-05.md) — 产品边界  
- [`corpus-testing-module-design-2026-05.md`](../corpus/corpus-testing-module-design-2026-05.md) — 语料模块  
- [`wechat-md-file-delivery.md`](../../guides/wechat-md-file-delivery.md) — 微信附件（L-A 守门）
