# 记忆模块运维与效果提升

> 个人管家试点：开满语义记忆 + 预取，用运维表与冒烟话术验证「记得住、记得准」。

## 生产推荐 `.env`

| 变量 | 推荐 |
|------|------|
| `BUTLER_SEMANTIC_MEMORY` | `1` |
| `BUTLER_QUEUE_PREFETCH` | `1` |
| `BUTLER_SYNC_CONVERSATION_MEMORY` | `0` |

详见 [`.env.example`](../../.env.example) 与 [`memory-roadmap.md`](../architecture/memory-roadmap.md)。

## 脚本

```bash
bash scripts/butler-memory-smoke.sh      # recall fixture 回归
bash scripts/butler-memory-reindex.sh    # 重建向量（改 MEMORY 后）
```

## 灵文1号试点

完整写入边界、运维检查表 O1–O6、微信冒烟 M1–M7：[`projects/LingWen1/docs/memory-guide.md`](../../projects/LingWen1/docs/memory-guide.md)。

## `/新对话` 行为

- 清空**本轮** Agent 上下文与会话回声
- **保留** Owner 画像、项目 MEMORY、经验库
- 对话足够长时可能提示「已提炼：长期记忆 +N 条」
