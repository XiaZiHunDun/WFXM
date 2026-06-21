# Butler 依赖术语表（2026-06）

> **用途**：统一「Skill / MCP / 插件」等叫法，避免与 Claude IDE 插件混淆。  
> **分层 SSOT**：[`dependency-policy-2026-05.md`](dependency-policy-2026-05.md) · 项目清单 [`projects/LingWen1/stack.yaml`](../../projects/LingWen1/stack.yaml)

---

## 1. 三类执行面（Butler 官方）

| 术语 | 是什么 | 如何接入 | 是否「下载」 |
|------|--------|----------|--------------|
| **Skill** | Markdown 方法论（`*.md` + frontmatter） | `butler skills install` · Registry 七源 | ✅ 外部拉取或仓库 bundled |
| **Builtin Tool** | `butler/tools/registry.py` 内置工具 | 随 `pip install -e .` | ❌ 代码自带 |
| **MCP Server** | 子进程工具（`mcp_<server>_<tool>`） | `butler mcp add` · `mcp.yaml` · npx/uvx | ✅ 运行时拉包 |

**不做**：统一插件市场 · 全量 MCP Host · 读取 `~/.claude/plugins/`。

---

## 2. 易混叫法对照

| 口语 | Butler 实际 | 说明 |
|------|-------------|------|
| 「插件」 | **多义** | 见下表 §3 |
| Claude Plugin | **非 Butler 源** | IDE 缓存目录，Butler 不读 |
| 微信插件 | 无此概念 | 用 Gateway + Skill/MCP |
| Firecrawl 插件 | **MCP Server** | `firecrawl` in `mcp.yaml` |
| webnovel 插件 | **Skill 包** | `marketplace:webnovel-writer/*` → GitHub 目录型安装 |

**Claude Plugin 兼容卡**（解构进口，非整包）：

| 字段 | 位置 | 作用 |
|------|------|------|
| `compatibility` | `butler/registry/catalog/skills/*-marketplace.json` | adopted / not_adopted / mcp_suggested |
| `plugin_adoption` | `projects/<名>/stack.yaml` | 项目侧 SSOT；`/诊断` 展示 |
| `directory_skills` | `stack.yaml` `skills:` | 要求目录型 skill（含 `references/`） |

---

## 3. Butler 内四种「plugin」

| 名称 | 模块/路径 | 作用 | 下载？ |
|------|-----------|------|--------|
| **Skill** | `tenants/.../skills/*.md` | 流程参考 | Registry |
| **MCP** | `~/.butler/mcp.yaml` | 工具子进程 | catalog + npx |
| **`project.yaml` `plugins:`** | `butler/project/plugins.py` | 注入 `BUTLER_*` env | ❌ 仅配置 |
| **loop_plugins** | `butler/core/loop_plugins.py` | 进程内钩子 | ❌ 代码注册 |

---

## 4. 分层与安装剖面

| 层 | 内容 | 安装/运维 |
|----|------|-----------|
| **L0** | Python core + optional-extra | `pip install -e ".[gateway]"`（生产 Gateway） |
| **L1** | mihomo、systemd、LangFuse、Node | 主机运维；`.env` `HTTP_PROXY` 等 |
| **L2** | `runtime/jobs.yaml`、novel-factory 脚本 | 项目盘 + timer |
| **L3** | Skill、MCP、外部 API | Registry / mcp.yaml / `.env` keys |

**部署剖面**（`BUTLER_DEPLOY_PROFILE`）：

| 剖面 | pip | 场景 |
|------|-----|------|
| `gateway`（默认，Gateway 在跑时） | `[gateway]` | 微信生产机 |
| `dev` | `[gateway,dev]` | 改 core + 跑 pytest |
| `all` | `[all]` | 全便捷集（仍不含 mcp 时可另装 gateway） |

脚本：`butler-gateway-ops.sh upgrade` · `butler-deploy.sh update` · `deploy-new-env.sh --gateway`。

---

## 5. Skill 下载渠道

| 源 | 标识示例 |
|----|----------|
| bundled | 仓库 catalog |
| project | `projects/<名>/skills/` → sync 到 `.butler/skills/` |
| github | `github:owner/repo/.../SKILL.md` |
| marketplace | `marketplace:webnovel-writer/webnovel-write` |
| clawhub / lobehub | `clawhub:slug` / `lobehub:slug` |
| url | HTTPS 直链 |

---

## 6. 清单与诊断

| 工件 | 路径 |
|------|------|
| 项目依赖清单 | `projects/<名>/stack.yaml` |
| Gateway 预检 | `bash scripts/butler-gateway-ops.sh preflight` |
| 微信诊断 | `/诊断` → **项目 stack** 段 |

`stack.yaml` v2 字段：`process_env`（`HTTP_PROXY` 等）· `skills.skills_expected`（lockfile/租户目录对照）· `skills.directory_skills`（目录型校验）。

**租户 → 项目同步**（registry 技能装到租户后）：

```bash
butler skills sync --project projects/LingWen1
# 仅同步 lockfile ∩ stack.yaml skills_expected；可用 --only webnovel-write,webnovel-review
# install/upgrade 后默认自动同步（BUTLER_SKILL_AUTO_SYNC_PROJECT=1，且默认项目含 stack.yaml）
```

`/诊断` stack 段另校验：`apis` 必填 env、`marketplace_install` ↔ lockfile、`deploy_profile` ↔ pip extra。

**EXT-3 文档 ingest**（参考书 PDF/Office → 语义检索）：

| 项 | 说明 |
|----|------|
| 状态 | **Verify ✅**（2026-06-20 灵文试点） |
| 开关 | `BUTLER_INGEST_ENABLED=1`（默认 0） |
| 试点目录 | `stack.yaml` `ingest_pilot_dirs` |
| 参考书 | `novel-factory/references/` 00–09 + mood-samples |
| 命令 | `butler memory ingest --project <名> [--reindex]` |
| 检索 | `butler memory search "<词>" --scope project --project 灵文1号` |
| PDF | `references/external/` + `butler-ingest-pilot.sh` |

---

## 7. 扩展接入顺序

见 [`extension-rd-loop-2026-06.md`](../plans/active/extension-rd-loop-2026-06.md)：

**MCP → optional-extra → builtin（最后）**

---

## 8. 维护

改分层、剖面或 Registry 源时，同步：本文 · `dependency-policy` · `reference.md` §安装 · 相关 `stack.yaml`。
