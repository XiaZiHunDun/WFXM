# 贡献指南

## 微信 Gateway 语料与路由

修改以下路径时，请在提交前跑通 **语料 PR 门禁**（与 CI `corpus-pr-gate` job 一致）：

- `butler/gateway/message_handler.py` 及 `butler/gateway/`
- `tests/corpus/`
- `tests/test_gateway_dev_conversations.py`

```bash
./scripts/corpus-test.sh drift    # 生成物与脚本一致
./scripts/corpus-test.sh pr-gate  # 有 diff 时跑 unified mock（AgentLoop + 微信语料 + 交叉索引）
```

也可强制全量：

```bash
CORPUS_PR_GATE_FORCE=1 ./scripts/corpus-test.sh pr-gate
```

本地对照 PR 基线：

```bash
CORPUS_PR_GATE_BASE=origin/main ./scripts/corpus-test.sh pr-gate
```

## 常用语料命令

| 命令 | 说明 |
|------|------|
| `./scripts/corpus-test.sh gateway` | L0–L2 微信 mock 一键 |
| `./scripts/corpus-test.sh unified` | 全量 mock + cross_channel |
| `./scripts/corpus-test.sh gateway-live` | L3 live（需 `.env` 与 `MINIMAX_API_KEY`） |
| `./scripts/corpus-test.sh drift` | YAML 漂移检查 |

设计说明见 `docs/plans/corpus-testing-module-design-2026-05.md` 与 `tests/corpus/suites/wechat_real/lw_real/meta.yaml`。
