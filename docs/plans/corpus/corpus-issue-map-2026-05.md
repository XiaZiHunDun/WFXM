# 语料评测问题地图 — 2026-05-23（合并版）

> **模型**：MiniMax-M2.7  
> **归档目录**：[`tests/corpus/archive/runs/`](../../../tests/corpus/archive/runs/)

---

## 一、三套 AgentLoop 语料（live）

| 套件 | 单轮 | 多轮 | 首轮失败 | P1 调整后 | 归档 run_id |
|------|------|------|----------|-----------|-------------|
| **v1** | 33 | DA-11, DA-31 | DA-06, DA-31 | ✅ rubric 已修并重跑 | `2026-05-23-v1-minimax` + `v1-p1-fix` |
| **v2** | 32 | DA2-MT01/02 | DA2-03 | ✅ | `2026-05-23-v2-v3-minimax` + `p1-rubric-fix` |
| **v3** | 36 | DA3-MT01/02/03 | 5 条 + DA3-36 安全 | ✅ | 同上 |
| **v4** | 24 | DA4-MT01/02 | —（未跑 live） | — | mock 145 全绿 |
| **合计** | **125** | **9 组** | v1～v3 已分批 live；v4 仅 mock | |

**全量复验（可选）**：

```bash
./scripts/corpus-test.sh live   # v1+v2+v3 单轮+多轮，约 25～35 分钟
```

### v1 失败与修复（P2）

| ID | 首轮现象 | 修复 |
|----|----------|------|
| DA-06 | 用 `HEAD^` 非 `HEAD~1` | any 组加入 `HEAD^` / `HEAD~` |
| DA-31 第 2 轮 | 中文「中间件」无 `middleware` | `must_contain` → `must_contain_any` 含中英文 |

### v2/v3 失败与修复（P1，见下）

首轮 6 条 `keyword_miss` + 1 条 `unsafe_ok`（DA3-36）→ rubric/题干/安全提示已处理，重跑 **6/6 passed**（`2026-05-23-p1-rubric-fix`）。

---

## 二、微信 LW-REAL（gateway · mock 工程链）

| 套件 | 通道 | 测试 | 结果 |
|------|------|------|------|
| `wechat_real.lw_real` | `gateway_wechat` | [`test_gateway_dev_conversations.py`](../../../tests/gateway/test_gateway_dev_conversations.py) | **16 passed**（integration，mock LLM + 真工具） |
| schema | registry | [`test_gateway_scripted.py`](../../../tests/corpus/runners/test_gateway_scripted.py) | ✅ |

LW-REAL **不走** `corpus_live`（无逐条关键词 rubric）；与 AgentLoop 语料 **互补**：

- AgentLoop：问答质量 / 关键词 / 安全拒答  
- LW-REAL：委派、`write_file`/`delete_file`、报告格式、项目隔离  

```bash
./scripts/corpus-test.sh gateway
# 或
PYTHONPATH=. pytest tests/gateway/test_gateway_dev_conversations.py -q
```

---

## 三、按 intent 交叉（阶段 5）

权威索引：[`tests/corpus/intent_crosswalk.yaml`](../tests/corpus/intent_crosswalk.yaml)

| intent | AgentLoop 代表 | Gateway 代表 | 说明 |
|--------|----------------|--------------|------|
| clarify | `dev_assistant.v3::DA3-01` 等 | `CAT-07`, `REF-STRICT-*` + `plan_only` | 先方案不写代码 |
| delegate | `dev_assistant.v3::DA3-31` 等 | `CAT-06`, `PROD-001` | 委派写删改 |
| detail | `dev_assistant.v3::DA3-32` 等 | `CAT-05`, `P1-DET-*` | 报告/进度 |
| switch | `dev_assistant.v1::DA-19` 等 | `CAT-02`, `SMK-01` | 项目/会话 |
| safety | `dev_assistant.v3::DA3-34` 等 | `REF-STRICT-*` `G_*` | 安全拒绝 |

更新：`python3 scripts/corpus/build_intent_crosswalk.py`

---

## 四、跨套件统计（首轮 live，修正前）

| fail_type | 条数 | 说明 |
|-----------|------|------|
| `keyword_miss` | 7 | v1×1 + v2/v3×6（表述/同义词） |
| `unsafe_ok` | 1 | DA3-36（已加强 prompt + rubric） |
| `tool_limit` | 0 | DA2-18 第二轮已通过 |

**无** `empty_reply` / `wrong_intent` 批量出现 → 模型整体可完成对话。

---

## 四、宏观优化 backlog（更新后）

| 优先级 | 项 | 状态 |
|--------|-----|------|
| P0 | 安全拒答（密钥、删库）— prompt + Butler 微信 | prompt 已加强；DA3-34/36 live 已过 |
| P1 | v2/v3 rubric 漂移 | ✅ 已完成 |
| P2 | v1 live + LW-REAL 纳入地图 | ✅ 本文 |
| P2 | v1 rubric（HEAD^、中间件） | ✅ 已完成 |
| P3 | 可选 nightly `corpus_smoke` | 未做 |
| P3 | gateway 完全 yaml 驱动 | 未做 |
| P3 | 多轮 live 写入 jsonl | 未做 |

---

## 五、归档索引

| run_id | 内容 |
|--------|------|
| `2026-05-23-v2-v3-minimax` | v2+v3 首轮 68 单轮 |
| `2026-05-23-p1-rubric-fix` | v2/v3 失败 6 条重跑 |
| `2026-05-23-v1-minimax` | v1 首轮 33 单轮 |
| `2026-05-23-v1-p1-fix` | v1 DA-06、DA-31 重跑 |

```bash
python3 scripts/corpus/summarize_runs.py --write docs/plans/corpus/corpus-issue-map-gateway-latest.md
```

---

## 六、下一轮建议

1. 发版前跑一次 `./scripts/corpus-test.sh live` 做全量回归快照。  
2. 真机微信变更后：先 `corpus-test.sh gateway`，再抽 2～3 条 AgentLoop smoke。  
3. 新语料走 `tests/corpus/suites/_template/`，失败先归档再改 rubric（保持本地图节奏）。
