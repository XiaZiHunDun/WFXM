# 语料跨通道协同（阶段 5）

> AgentLoop（`dev_assistant.v1～v5`）与 Gateway（`wechat_real.lw_real`）共用 **intent** 标签，用于问题地图与 PR 回归。

## 意图与索引

| 资源 | 路径 |
|------|------|
| 约定 | [`tests/corpus/schemas/corpus-intent-v1.md`](../tests/corpus/schemas/corpus-intent-v1.md) |
| 交叉表 | [`tests/corpus/intent_crosswalk.yaml`](../tests/corpus/intent_crosswalk.yaml) |
| 生成 | `python3 scripts/corpus/build_intent_crosswalk.py` |

P0 意图（两侧都要有代表用例）：`clarify`、`delegate`、`detail`、`switch`、`safety`。

## PR 改网关路由时

若 diff 触及：

- `butler/gateway/message_handler.py`
- `tests/corpus/**`
- `tests/gateway/test_gateway_dev_conversations.py`

请跑：

```bash
./scripts/corpus-test.sh pr-gate
# 等价于（强制全量）
CORPUS_PR_GATE_FORCE=1 ./scripts/corpus-test.sh unified
```

`unified` = AgentLoop rubric mock + 微信 L0～L4 mock + `test_corpus_cross_channel`。

## 与问题地图

1. Live 跑批后：`./scripts/corpus-test.sh ops`  
2. 更新 [`corpus-issue-map-2026-05.md`](corpus-issue-map-2026-05.md) 第四节「按 intent」  
3. 失败用例标注 `intent`，对照 crosswalk 查另一侧是否已有覆盖

## 维护 crosswalk

语料增删后：

```bash
python3 scripts/corpus/build_intent_crosswalk.py
pytest tests/corpus/runners/test_corpus_cross_channel.py -q
git add tests/corpus/intent_crosswalk.yaml
```

可选：在 AgentLoop `cases[]` 上增加 `tags.intent: delegate` 等显式标签（优先于推断）。
