# 记忆模块运维与效果提升

> 个人管家试点：开满语义记忆 + 预取，用运维表与冒烟话术验证「记得住、记得准」。

## 生产推荐 `.env`

| 变量 | 推荐 |
|------|------|
| `BUTLER_SEMANTIC_MEMORY` | `1` |
| `BUTLER_QUEUE_PREFETCH` | `1` |
| `BUTLER_SYNC_CONVERSATION_MEMORY` | `0` |
| `BUTLER_MEMORY_HALF_LIFE_DAYS` | `30`（检索时间衰减） |
| `BUTLER_MEMORY_ACCESS_BOOST` | `0.12`（访问次数加权） |

详见 [`.env.example`](../../.env.example) 与 [`memory-roadmap.md`](../architecture/memory-roadmap.md)。

## 命令速查

| 命令 | 作用 |
|------|------|
| `butler memory search "<词>" --verbose` | CLI 检索调试：mode、fallback、chunk_id、混合权重 |
| `/诊断` | 向量条数、画像向量、三元组条数、衰减参数、最近检索 telemetry |
| `/记忆图谱` | 三元组只读展示（不参与检索） |
| `/记忆待审` / `/批准记忆` / `/拒绝记忆` | Pending 审批 |

## 发版 / 升级后必做

部署或合并记忆相关代码后，在仓库根目录执行一次（需 `.env` 中 `BUTLER_SEMANTIC_MEMORY=1`）：

```bash
bash scripts/butler-memory-reindex.sh
```

会重建 `memory_vectors.db`、Owner 画像向量、三元组表，并刷新各项目 `facts.json`。期望输出含 `ok: true`。

## 脚本

```bash
butler memory search "某项目决策" --scope project --verbose
butler memory search "pytest" --scope experience --json
bash scripts/butler-memory-smoke.sh      # recall fixture 回归
bash scripts/butler-memory-reindex.sh    # 重建向量（改 MEMORY / 升级记忆模块后）
# 等价: butler memory reindex
```

## 灵文1号试点

完整写入边界、运维检查表 O1–O6、微信冒烟 M1–M7：[`projects/LingWen1/docs/memory-guide.md`](../../projects/LingWen1/docs/memory-guide.md)。

## `/新对话` 行为

- 清空**本轮** Agent 上下文与会话回声
- **保留** Owner 画像、项目 MEMORY、经验库
- 对话足够长时可能提示「已提炼：长期记忆 +N 条」
