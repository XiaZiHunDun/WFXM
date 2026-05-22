# 归档代码

本目录存放**已退出主线**的 Butler 实现，不参与构建与测试。

## Butler v1

v1 完整树已从 `main` 移除，保留在 Git 标签：

| 标签 | 说明 |
|------|------|
| **`archive/butler-v1-20260522`** | 2026-05-22 快照（原 `archive/butler-v1/`） |

**恢复目录到工作区：**

```bash
git archive archive/butler-v1-20260522 archive/butler-v1 | tar -x
# 或查看某文件：
git show archive/butler-v1-20260522:archive/butler-v1/butler/main.py | head
```

当前产品与文档见仓库根 [`butler/`](../butler/) 与 [`docs/`](../docs/)。

## 请勿修改

- [`reference/`](../reference/) — **主公维护**的外部竞品/标本对照区，与归档无关。
