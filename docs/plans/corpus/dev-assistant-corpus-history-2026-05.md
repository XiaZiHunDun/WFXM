# 开发助手语料 — 版本史与索引（v1–v4）

> **活跃设计**：[`corpus-testing-module-design-2026-05.md`](corpus-testing-module-design-2026-05.md)  
> **v3 生成方案**（仍引用）：[`dev-assistant-corpus-v3-generation-scheme-2026-05.md`](dev-assistant-corpus-v3-generation-scheme-2026-05.md)  
> **门禁**：[`../../CONTRIBUTING.md`](../../../CONTRIBUTING.md) · `./scripts/corpus-test.sh`

旧版分析文档（`dev-assistant-corpus-analysis`、`v2-analysis`、`v3-analysis`、`v4-expansion`）已缩为索引页，**以本文为准**。

---

## 版本一览

| 版本 | 规模 | 语料路径 | 测试 |
|------|------|----------|------|
| **v1** | 12 单轮 DA-01…12 | `tests/scenarios/dev_assistant_corpus.yaml` | `tests/test_dev_assistant_corpus.py` |
| **v2** | 34（32 单轮 + 2×3 多轮） | `tests/scenarios/dev_assistant_corpus_v2.yaml` | `tests/test_dev_assistant_corpus_v2.py` |
| **v3** | 39（36 + 3×3 多轮） | `tests/corpus/suites/dev_assistant/v3/corpus.yaml` | `tests/corpus/runners/test_agent_loop_rubric.py` |
| **v4** | 26（24 + 2×3 多轮） | `tests/corpus/suites/dev_assistant/v4/corpus.yaml` | 同上 `-k dev_assistant.v4` |

**微信真机**：另见 `tests/corpus/suites/wechat_real/`、[`wechat-real-coverage-matrix-2026-05.md`](wechat-real-coverage-matrix-2026-05.md)。

---

## v1（DA-01…12）

- **定位**：开发日常 12 类（生成/解释/Git/React/安全等）
- **Butler**：适合评「开发助手回答质量」；灵文 Lead 下 DA-01 应委派 dev
- **分层**：L0 schema → L1 mock loop → L2 lead-route → L3 live_llm

---

## v2（DA2-xx）

- **定位**：实战痛点与栈深度（迁移/调试/K8s/安全/多轮等）
- **分簇**：代码转换、调试、框架、算法、系统设计、运维、DB、安全、测试、工具、文本、多轮
- **默认**：直连 AgentLoop 评问答（非微信 Lead 路径）

---

## v3（DA3-xx）

- **12 维 × 3**：conversational、code_review、performance、observability、api_design、data_engineering、incident_ops、git_advanced、messaging、graphql_api、product_butler、safety_bounds
- **命令**：`PYTHONPATH=. pytest tests/corpus -k dev_assistant.v3 -m corpus_mock -q`

---

## v4（DA4-xx）

- **补盲区**：cloud_native、llm_integration、mobile_dev、frontend_a11y、compliance_audit、finops、butler_product、edge_cases
- **live_smoke**：DA4-02、05、10、16、19、24
- **命令**：`PYTHONPATH=. pytest tests/corpus -k dev_assistant.v4 -m corpus_mock -q`

---

## 相关规划

| 文档 | 用途 |
|------|------|
| [`corpus-issue-map-2026-05.md`](corpus-issue-map-2026-05.md) | issue 映射 |
| [`corpus-scale-target-2026-05.md`](corpus-scale-target-2026-05.md) | 规模目标 |
| [`wechat-dev-conversation-scenarios-2026-05.md`](wechat-dev-conversation-scenarios-2026-05.md) | 开发对话场景 |
