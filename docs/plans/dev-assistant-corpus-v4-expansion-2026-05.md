# 开发助手语料 v4 — 扩充说明

> **语料**：[`tests/corpus/suites/dev_assistant/v4/corpus.yaml`](../../tests/corpus/suites/dev_assistant/v4/corpus.yaml)  
> **测试**：自动纳入 [`tests/corpus/runners/test_agent_loop_rubric.py`](../../tests/corpus/runners/test_agent_loop_rubric.py)

## 规模

| 类型 | 数量 | ID |
|------|------|-----|
| 单轮 | 24 | DA4-01 … DA4-24 |
| 多轮 | 2×3 轮 | DA4-MT01、DA4-MT02 |
| **合计** | **26** | |

## 与 v1～v3 的差异（补盲区）

| 维度 | 条数 | 覆盖点 |
|------|------|--------|
| cloud_native | 3 | Helm、CrashLoop、Ingress TLS |
| llm_integration | 3 | RAG chunk、prompt 注入、embedding 维度 |
| mobile_dev | 3 | Flutter、iOS 后台、RN 热更新 |
| frontend_a11y | 3 | a11y 名称、表单错误、对比度 |
| compliance_audit | 3 | 审计日志、GDPR、日志脱敏 |
| finops | 3 | 账单、K8s requests、S3 生命周期 |
| butler_product | 3 | 新对话、切项目、删文件确认 |
| edge_cases | 3 | DST、cron、JSON 大整数、幂等 TTL |

## 命令

```bash
PYTHONPATH=. pytest tests/corpus -k dev_assistant.v4 -m corpus_mock -q
```

## live_smoke（6）

DA4-02、05、10、16、19、24
