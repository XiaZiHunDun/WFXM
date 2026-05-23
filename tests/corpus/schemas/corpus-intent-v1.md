# 跨通道语料意图约定 v1 (`corpus-intent-v1`)

> AgentLoop（`dev_assistant.*`）与 Gateway（`wechat_real.lw_real`）共用意图标签，用于问题地图交叉引用与 PR 门禁。

## 标准意图（`tags.intent` / crosswalk）

| intent | 说明 | Gateway 典型 | AgentLoop 典型 |
|--------|------|--------------|----------------|
| `clarify` | 先澄清/方案，不写代码 | `clarify_first`, `plan_only` | `conversational` 先梳理 |
| `delegate` | 委派子代理写删改 | `C_*`, `delegate_*` | 委派/实现类题干 |
| `detail` | 查看报告/详情 | `detail_*`, `/详细` | 进度/结果追问 |
| `switch` | 项目/会话切换 | `A_*`, `/切换` | 上下文切换类 |
| `safety` | 安全边界拒绝 | `G_*`, `safety_*` | `safety_bounds` |
| `readonly` | 只读探查 | `B_*`, `read_*` | 读代码/文档 |
| `memory` | 记忆运维 | `E_*`, `/记忆` | — |
| `workflow` | 工作流/定时 | `F_*`, `/工作流` | — |
| `identity` | 能力/身份介绍 | `H_*`, `capabilities` | `product_butler` |
| `recap` | 复述上一轮 | `recap` | 多轮 recap |
| `off_topic` | 闲聊/离题 | `V_*` | — |
| `emotion` | 催促/情绪 | `K_*` | — |
| `multiturn` | 多轮链（元） | `MT-*` | `multi_turn` |
| `debug` | 报错/诊断 | `T_*`, `/诊断` | `incident_ops` |

## 字段

| 位置 | 字段 | 说明 |
|------|------|------|
| AgentLoop `cases[]` | `tags.intent` | 可选；缺省时由 `harness/corpus_intent.py` 推断 |
| Gateway utterance | （推断） | 由 `category` + `kind` 映射，见 `gateway_category_to_intent()` |
| 交叉索引 | `intent_crosswalk.yaml` | 每意图下列出两侧代表用例 ID |

## 维护

```bash
python3 scripts/corpus/build_intent_crosswalk.py
pytest tests/corpus/runners/test_corpus_cross_channel.py -q
```

PR 改 `butler/gateway/message_handler.py` 时跑：

```bash
./scripts/corpus-test.sh pr-gate
```
