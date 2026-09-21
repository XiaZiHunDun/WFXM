# 安全策略 (Security Policy)

## 支持的版本 (Supported Versions)

当前活跃支持以下版本：

| 版本 | 支持状态 |
|------|---------|
| v5.x | ✅ 活跃支持 |
| v4.x | ❌ 已 EOL（见 [ADR-0001](docs/adr/2026-08-08-v4-to-v5-supersession.md)） |
| < v4 | ❌ 不支持 |

## 披露漏洞 (Reporting a Vulnerability)

### 推荐路径：GitHub Security Advisories

1. 打开 [项目仓库 Security tab](https://github.com/XiaZiHunDun/WFXM/security/advisories/new)
2. 点击 "Report a vulnerability"
3. 填写私密披露表单（GitHub 端到端加密，不公开可见）
4. 我们将：
   - **48 小时内**首次响应
   - 评估严重性并沟通修复时间线
   - 修复后通过 GitHub Security Advisory 公开致谢 + CVE ID（如适用）
   - 修复 release 标注 `🔒 security` 标签

### 备选路径：邮件

- 邮箱：`security@wfxm.dev`
- 适用：不方便用 GitHub 的报告者
- PGP 密钥：项目暂未提供（GitHub Advisories 默认加密足够）

> ⚠️ **待 owner 注册**：`security@wfxm.dev` 占位邮箱需 owner 在 GitHub Settings → Email forwarding 注册后才生效。在注册完成前，请优先使用 GitHub Security Advisories 路径。

## 安全更新订阅

- Watch 仓库 → Custom → 勾选 "Releases only"
- 关注 [CHANGELOG.md](CHANGELOG.md) "安全 (Security)" 小节
- 关注 GitHub Security Advisories 列表（修复发布后会同步出现）

## 安全最佳实践（部署者侧）

- **始终运行最新 v5.x release**：避免已知 CVE 累积
- **不在公网暴露 owner-route**：走 SSH tunnel、wireguard 或 Cloudflare Tunnel
- **secrets 加密存储**：通过 `wfxm secret set` 写入 Secret<T> 包装层（参考 [docs/architecture/dev-ops-tools-design.md](docs/architecture/dev-ops-tools-design.md)）
- **启用 audit emit**：默认开启；如手动禁用请评估后果
- **定期轮换 shared secret**：渠道入站密钥（如有）建议 90 天轮换一次
- **审计日志归档**：audit_events 表至少保留 90 天

## 已知安全限制（部署者须知）

详见 [docs/architecture/v5-production-architecture-2026-08.md](docs/architecture/v5-production-architecture-2026-08.md) § 已知限制章节。