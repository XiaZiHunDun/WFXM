# Butler 部署安全相关配置

> **状态**：2026-06-09（R8-8）  
> **关联**：[`reference.md`](reference.md) · [`config-surfaces.md`](config-surfaces.md) · Owner gate · Skill 安装

---

## 1. `BUTLER_ENV` 部署环境

| 值 | 含义 | 行为 |
|----|------|------|
| *(未设)* | 开发默认 | 允许 `BUTLER_PROJECT_CREATE_OPEN` 等开发 bypass（见下） |
| `dev` / `test` | 开发/测试 | 同上 |
| `staging` | 预发 | 非 prod 路径（bypass 仍可能生效） |
| `prod` | **生产** | 启用严格路径（见 §2） |
| 其他非空值 | 未知 | **按 prod 严格路径**处理，并打 `warning` 日志 |

设置示例（systemd / `.env`）：

```bash
BUTLER_ENV=prod
```

实现：`butler/env_parse.py` → `is_butler_prod()`；`owner_gate` 与 `skill_service` 消费。

---

## 2. `BUTLER_ENV=prod` 时禁用的能力

| 能力 | 环境变量 | prod 行为 |
|------|----------|-----------|
| Owner gate BYPASS | `BUTLER_PROJECT_CREATE_OPEN=1` | **忽略**：`/项目 新建` 等须真实 Owner allowlist |
| Skill 社区自动安装 | `BUTLER_REGISTRY_AUTO_INSTALL=1`（无确认） | **拒绝**：须显式确认或 builtin/trusted |

代码锚点：

- `butler/gateway/owner_gate.py` — Sprint 18-2 SEC-18-2-1
- `butler/registry/skill_service.py` — Sprint 19-3 SEC-19-3

---

## 3. 生产建议（微信网关）

| 项 | 建议 |
|----|------|
| `BUTLER_ENV` | 设为 `prod` |
| `WECHAT_DM_POLICY` | `allowlist` |
| `BUTLER_OWNER_WECHAT_ID` | 显式配置 Owner |
| `BUTLER_PROJECT_CREATE_OPEN` | **勿**在生产设为 `1` |
| 终端 / git push / execute_code | 保持默认关闭；见 [`permission-gate-stack.md`](../architecture/permission-gate-stack.md) |

---

## 4. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-06-09 | R8-8 初稿：`BUTLER_ENV` 与 prod 严格路径 |
