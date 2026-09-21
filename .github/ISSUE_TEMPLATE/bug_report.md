---
name: 🐛 Bug 报告
about: 报告一个具体 bug 或异常行为
title: '[Bug] '
labels: ['bug', 'triage']
assignees: []
---

## 描述

<!-- 清晰描述发生了什么 -->

## 复现步骤

1.
2.
3.

## 期望行为

<!-- 按文档预期应该发生什么 -->

## 实际行为

<!-- 实际发生了什么 -->

## 环境

- **WFXM 版本**：v5.x.y（`git describe --tags` 或 `wfxm --version`）
- **部署模式**：自托管 / Docker / pnpm dev
- **OS**：Linux/macOS/Windows 版本
- **Node.js 版本**：`node --version`
- **数据库**：PostgreSQL 版本 / PGlite（开发）
- **LLM Provider**：Anthropic / OpenAI / 其他 + 模型名

## 严重程度

- [ ] 🔴 阻塞（核心功能不可用）
- [ ] 🟡 降级（有 workaround）
- [ ] 🟢 轻微（边界 / 文案）

## 截图 / 日志

<!-- 粘贴 `wfxm debug bundle` 输出或 owner-side error 截图 -->

## 自检

- [ ] 已搜索 [已有 issues](https://github.com/XiaZiHunDun/WFXM/issues?q=is%3Aissue+bug) 无重复
- [ ] 已查阅 [docs/](https://github.com/XiaZiHunDun/WFXM/tree/main/docs) 和 [butler-v5/README.md](https://github.com/XiaZiHunDun/WFXM/tree/main/butler-v5)
- [ ] 已查阅 [CHANGELOG.md](https://github.com/XiaZiHunDun/WFXM/blob/main/CHANGELOG.md) 确认非已知回归
- [ ] ⚠️ **安全问题**：漏洞请走 [SECURITY.md](https://github.com/XiaZiHunDun/WFXM/blob/main/SECURITY.md)，**不要**在此公开