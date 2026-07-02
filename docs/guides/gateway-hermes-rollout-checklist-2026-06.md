# Gateway Hermes 对标能力 — 生产切换清单

> **状态**：2026-06-30  
> **受众**：微信 gateway 运维 / Owner  
> **前置**：[`deploy-profiles-2026-06.md`](deploy-profiles-2026-06.md) gateway 剖面

本清单用于在**已有 gateway** 上启用 Hermes 对标收尾（记忆/技能审批、toolset 投影、transcript FTS 等）。dev-local 无需执行。

---

## 1. 备份与剖面

```bash
cd /path/to/WFXM
cp ~/.butler/.env ~/.butler/.env.bak.$(date +%Y%m%d) 2>/dev/null || true
python3 scripts/apply-butler-env-profile.py lead
```

确认 gateway `.env` 含（或手动追加）：

| 变量 | 建议值 |
|------|--------|
| `BUTLER_MEMORY_WRITE_APPROVAL` | `owner_scopes`（默认） |
| `BUTLER_SKILL_WRITE_APPROVAL` | `1` |
| `BUTLER_TOOLSET` | `wechat_minimal` |
| `BUTLER_TRANSCRIPT_FTS` | `1` |
| `BUTLER_MEMORY_OBSERVER_QUEUE` | `1` |
| `BUTLER_MEMORY_OBSERVATION_RECALL` | `1` |
| `BUTLER_MEMORY_UNIFIED_RECALL` | `1` |
| `BUTLER_DELEGATE_SUMMARY_MAX_CHARS` | `4000`（可选，默认已设） |

全量说明：[`reference.md`](../config/reference.md)。

---

## 2. 一次性索引重建

升级后**已有会话**需重建 FTS（新会话自动索引）：

```bash
butler transcript index --rebuild
```

预期：无报错；`~/.butler/transcripts/` 下对应 sqlite 含 `transcript_fts` 表。

---

## 3. 重启 gateway

```bash
bash scripts/butler-gateway-ops.sh restart
bash scripts/butler-gateway-ops.sh status   # active
butler doctor                                # 剖面 gateway + 关键 env
```

---

## 4. 微信冒烟（Owner）

| 步骤 | 命令 / 动作 | 预期 |
|------|-------------|------|
| 诊断 | `/诊断` | 见部署剖面；无关键 env 缺失 |
| 记忆待审 | 触发 `owner_profile` 类记忆写入后 `/记忆待审` | 列表含 `P` 前缀项；`/批准记忆` 可入库 |
| 技能待审 | `/技能学习 帮助我在合并前检查 Python 类型` | 入待审；`/技能待审` 可见；`/批准技能 1` 写入 |
| 工具投影 | 普通对话中观察可用工具 | `wechat_minimal` 子集（无 dev-only 工具） |
| 统一召回 | `butler memory search "关键词" --scope hybrid` | 需 `BUTLER_MEMORY_UNIFIED_RECALL=1`；`/诊断` 见「统一 hybrid 召回: 开」 |
| Observation | `butler memory search "路径" --scope observation` | 需 `BUTLER_MEMORY_OBSERVATION_RECALL=1` + `OBSERVER_QUEUE=1` |
| 向量写入 | `/批准记忆` 后 `/诊断 详细` | 「最近向量写入」含 `project_pending` 时间戳 |

CLI 等价（本机，非 gateway 进程内）：

```bash
butler memory pending
butler memory approve 1          # 所有者序号
butler memory approve P1         # 项目 MEMORY Pending
butler memory approve all
butler skills learn "帮助我在合并前检查 Python 类型"
butler skills pending
butler skills approve 1
```

可选 Hermes 回归门禁：

```bash
butler eval run --preset hermes
```

---

## 5. 可选：发版 eval

```bash
butler eval run --preset release   # 含 tcr + regression + 微信语料 + hermes_gate
butler eval run --preset hermes    # 仅 Hermes 对标 pytest 子集（与 release 中 hermes_gate 相同）
```

或至少：

```bash
bash scripts/butler-pytest-fast-gate.sh
```

---

## 6. 回滚

1. 恢复 `.env.bak.*`
2. `bash scripts/butler-gateway-ops.sh restart`
3. 若仅需关闭技能审批：`BUTLER_SKILL_WRITE_APPROVAL=0`（记忆审批保持 `owner_scopes` 亦可单独调）

FTS 索引可保留；设 `BUTLER_TRANSCRIPT_FTS=0` 仅禁用新索引，不删已有 sqlite。

---

## 7. 相关文档

- 部署剖面：[`deploy-profiles-2026-06.md`](deploy-profiles-2026-06.md)
- 架构模块：[`v4-architecture.md`](../architecture/v4-architecture.md)
- P2 backlog：[`roadmap-backlog` §3.2.2](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md)
