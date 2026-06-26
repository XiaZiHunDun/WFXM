# Butler 部署剖面（推荐入口）

> **状态**：2026-06-26（PROD-P0-02）  
> **用途**：新 Owner / 运维 **优先读本页**，再按需查 [`docs/config/reference.md`](../config/reference.md)。  
> **勿用**：裸扫 `.env.example`（~540 项）当作上手清单。

---

## 1. 三剖面速选

| 剖面 | 谁在用什么 | pip | 终端 env | 典型脚本 |
|------|------------|-----|----------|----------|
| **gateway** | 微信生产机，常驻网关 | `BUTLER_DEPLOY_PROFILE=gateway`<br>`pip install -e ".[gateway]"` | 通常不设，或 `lead` | `butler-gateway-ops.sh` · `install-butler-gateway-service.sh` |
| **dev-local** | 本机改 core、跑 pytest | `BUTLER_DEPLOY_PROFILE=dev`<br>`pip install -e ".[dev]"` | `BUTLER_ENV_PROFILE=dev-local` | `butler-pytest-fast-gate.sh` · `butler-smoke.sh quick` |
| **dev-remote** | 远程沙箱 + CC 桥接试点 | 同 gateway 或 dev | `BUTLER_ENV_PROFILE=dev-remote` | `apply-butler-env-profile.py` · `/沙箱` |

应用终端剖面：

```bash
python3 scripts/apply-butler-env-profile.py dev-local   # 写入当前 shell 建议 env
python3 scripts/apply-butler-env-profile.py dev-remote
```

---

## 2. 必填 env（每剖面 ≤10）

### gateway（微信生产）

| 变量 | 说明 |
|------|------|
| `MINIMAX_API_KEY`（或等价 LLM key） | 对话与委派 |
| `BUTLER_OWNER_WECHAT_ID` | Owner 门控 |
| `BUTLER_PROJECTS_DIR` | 项目根（默认 `projects/`） |
| `BUTLER_EXPORT_SEND_WECHAT_FILE` | 长文 `.txt` 附件（默认 `1`） |
| `BUTLER_EVAL_PROD_EVIDENCE` | G1-04 委派生产记账（默认 `1`） |
| `BUTLER_GATEWAY_DURABLE_OUTBOX` | 完成推送 outbox（默认 `1`） |

**推荐（Owner UX，PROD-P3）**：

| 变量 | 说明 |
|------|------|
| `BUTLER_GATEWAY_DELEGATE_PROGRESS_NOTIFY=1` | 委派执行中心跳（长任务防「卡死」感） |
| `BUTLER_WORKFLOW_AUTO_RESUME=1` | 工作流确认后自动续跑（灵文 DAG） |
| `BUTLER_ONBOARDING_WELCOME=1` | 首次绑定三步引导 |

可选：`BUTLER_MCP_ENABLED=1` · `BUTLER_SEMANTIC_MEMORY=1`

**Owner 首周**：[`owner-first-week-2026-06.md`](owner-first-week-2026-06.md)

**期望**：`butler doctor` 显示 `推荐剖面: gateway`；`butler-gateway-ops.sh status` active；微信 `/诊断` 见部署剖面 + OT2 块。

### dev-local（本机开发）

| 变量 | 说明 |
|------|------|
| `MINIMAX_API_KEY`（或等价） | 跑 sim / 可选 live |
| `BUTLER_DEPLOY_PROFILE=dev` | pip 剖面 |
| `BUTLER_ENV_PROFILE=dev-local` | 终端策略 |
| `PYTHONPATH=.` | pytest / butler CLI |

可选：`BUTLER_TERMINAL_SANDBOX=1` · `BUTLER_WECHAT_OWNER_SIM=1`

**期望**：`bash scripts/butler-pytest-fast-gate.sh` 绿；**不要**在本机 dev 剖面误跑第二个 gateway（singleton lock）。

### dev-remote（远程开发试点）

| 变量 | 说明 |
|------|------|
| 同 gateway 或 dev-local 基础项 | |
| `BUTLER_ENV_PROFILE=dev-remote` | 启用远程策略 |
| `BUTLER_CC_BRIDGE=1` | CC CLI 桥接（opt-in） |
| `BUTLER_TERMINAL_PROFILE` | 项目沙箱白名单名 |

**期望**：微信 `/沙箱` 有 dev-remote 说明；`/分工` 可读。

---

## 3. 检查命令（人话三档）

| 命令 | 作用 |
|------|------|
| `butler doctor` | 依赖 + **部署剖面** + G1-04 + 安全审计 |
| 微信 `/诊断` | Owner 简要：健康灯 + **剖面 5–8 项** + OT2 |
| `butler project preflight --project <名>` | 项目接入：**通过 / 需修复 / 可忽略** 顶栏 |
| `bash scripts/butler-gateway-ops.sh preflight` | 网关启动前检查 |

preflight 顶栏示例：

```text
【需修复】需修复 1 项
  缺少 project.yaml
```

---

## 4. 与全量配置的关系

- **全量 SSOT**：[`reference.md`](../config/reference.md) + [`.env.example`](../../.env.example)  
- **分层说明**：[`config-surfaces.md`](../config/config-surfaces.md) · [`dependency-terminology-2026-06.md`](dependency-terminology-2026-06.md) §4  
- **产品立项**：[`roadmap-backlog` §3.6](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md#36-产品评估立项2026-06--p0p1-带验收)

---

## 5. Owner 硬反馈（G1-04）

自动 `prod_delegate_*` 记账 **不等于** Owner 主观纠正。请用：

```text
/反馈 委派摘要不对，应该只读
/反馈 驳回 验收未通过：测试未绿
```

窗满前每周：`bash scripts/butler-g1-04-closure-check.sh`（窗未满 exit 2 为预期）。
