# 指南文档索引

> 个人助手 Butler：**主场景为微信**；CLI 为本地开发与调试。

| 文档 | 用途 |
|------|------|
| [wechat-gateway-ops.md](./wechat-gateway-ops.md) | **生产运维**：systemd 安装、发版、日志、排障 |
| [wechat-daily-smoke-checklist.md](./wechat-daily-smoke-checklist.md) | **发版后真机冒烟**（约 15–25 分钟） |
| [wechat-core-scenario.md](./wechat-core-scenario.md) | 微信八步剧本详解与 FAQ |
| [owner-profile-setup.md](./owner-profile-setup.md) | Owner 画像配置 |
| [manual-testing-guide.md](./manual-testing-guide.md) | CLI + 微信完整人工测试手册 |

## 推荐顺序

1. 首次：`wechat-gateway-ops.md` → `butler wechat-setup` → 安装 systemd  
2. 日常发版：`butler-gateway-ops upgrade` → `wechat-daily-smoke-checklist.md`（大改时）  
3. 深入理解场景：`wechat-core-scenario.md`
