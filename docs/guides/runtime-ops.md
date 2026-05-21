# 项目 Runtime 运维手册（systemd timer）

> **试点**：灵文1号 · `projects/LingWen1/runtime/jobs.yaml`  
> 设计：[`architecture/project-runtime-automation.md`](../architecture/project-runtime-automation.md)  
> 与网关独立：runtime 在子进程跑脚本，**不阻塞**微信对话。

---

## 一键命令

```bash
cd ~/projects/WFXM

# 运维冒烟（list + factory-status + 禁用 mutating 校验 + pytest）
bash scripts/butler-runtime-smoke.sh
# 含慢任务一致性：BUTLER_RUNTIME_RUN_CONSISTENCY=1 bash scripts/butler-runtime-smoke.sh

# 安装/刷新 timer（每 15 分钟扫到期任务）
bash scripts/install-butler-runtime-timer.sh

# 手动跑「当前到期」任务（只读执行；改盘仅推送待批准）
bash scripts/butler-runtime-due.sh
# 或
butler runtime due --project 灵文1号

# 手动跑单个任务
butler runtime run factory-status-daily --project 灵文1号
bash scripts/butler-runtime-run.sh factory-status-daily

# 列出任务与上次运行
butler runtime list --project 灵文1号
```

---

## 微信指令（需 `/切换 灵文1号`）

| 指令 | 作用 |
|------|------|
| `/定时` | 列出 jobs、上次/下次运行 |
| `/运行 <id>` | 立刻跑 **只读** 任务 |
| `/批准运行 <id>` | **改盘** 任务：批准并执行一次（消耗批准） |
| `/诊断` | 含 runtime 最近运行摘要（3d） |

网关发版或更新 runtime 微信命令后：`bash scripts/butler-gateway-ops.sh restart`。

---

## systemd 单元

| 项 | 路径 |
|----|------|
| Service | `~/.config/systemd/user/butler-runtime-lingwen.service` |
| Timer | `~/.config/systemd/user/butler-runtime-lingwen.timer` |
| 日志 | `logs/butler-runtime.log` |
| 审计 | `~/.butler/runtime/runs/<项目>/<job_id>/*.json` |
| 批准 | `~/.butler/runtime/approvals/<项目>/<job_id>.json` |

```bash
systemctl --user status butler-runtime-lingwen.timer
systemctl --user list-timers 'butler-runtime*'
tail -f logs/butler-runtime.log
```

**停用定时器**：`systemctl --user disable --now butler-runtime-lingwen.timer`

---

## 环境变量（`.env`）

| 变量 | 说明 |
|------|------|
| `BUTLER_RUNTIME_ENABLED` | `0` 关闭所有 run/due |
| `BUTLER_RUNTIME_PUSH` | `0` 不推微信（CLI 仍写 audit） |
| `BUTLER_OWNER_WECHAT_ID` | 推送目标；未设则用 `WECHAT_ALLOWED_USERS` 首项 |
| `WECHAT_TOKEN` / `WECHAT_ACCOUNT_ID` | 推送必填 |
| `BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS` | 两次 runtime 推送最小间隔（默认 **25s**，防 iLink 限流） |
| `WECHAT_SEND_CHUNK_RETRIES` / `WECHAT_SEND_CHUNK_RETRY_DELAY_SECONDS` | 微信发送重试（验证脚本建议 6 / 2） |
| `BUTLER_RUNTIME_PUSH_QUEUE` | `1` 时限流失败写入 `~/.butler/runtime/push_queue.jsonl`，`runtime due` 时重试 |

**推送真机验证**：`bash scripts/butler-wechat-push-verify.sh 灵文1号`（短 ping + factory-status，带冷却）。

---

## 任务说明（灵文试点）

| id | mode | 默认 | 说明 |
|----|------|------|------|
| `factory-status-daily` | readonly | 开 | 08:00 UTC 日报；可 `/运行` |
| `consistency-weekly` | readonly | 开 | 周一 09:00 UTC；**P0=0 即 runtime 成功**（P1 为有条件通过） |
| `publish-preflight` | readonly | 开 | 周日 07:00 UTC；`run_publish.sh preflight`（只读，不 archive） |

**不实施**（见 [`project-runtime-automation.md` §11](../architecture/project-runtime-automation.md)）：`workflow-report`；失败同日自动重试。流水线状态看 **`factory-status-daily`** 或问厂长 / `/工作流 run novel-factory-status`。

---

## 排障

| 现象 | 处理 |
|------|------|
| timer 无输出 | `tail logs/butler-runtime.log`；非 cron 到点会显示「没有到期的任务」 |
| 未收到推送 | 查 `WECHAT_TOKEN`、`BUTLER_OWNER_WECHAT_ID`；`BUTLER_RUNTIME_PUSH=1`；连跑多任务时加大 `BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS` 或跑 `butler-wechat-push-verify.sh` |
| 一致性摘要无路径 | `consistency-weekly` 成功后会附 `novel-factory/06_意见仓库/07_一致性检查/*.md`；失败推送含 `审计: …json` |
| `/运行` 改盘被拒 | 正常；用 `/批准运行` 或保持 job 关闭 |
| 任务一直「运行中」 | 删锁：`~/.butler/runtime/locks/<项目>__<job_id>.lock`（或等 2h 过期） |

---

## 真机验收（按需）

- **3a**：`/定时`、`/运行 factory-status-daily` — 已通过（2026-05-21）
- **3b**：timer 已 enable；`butler runtime due` / 定时扫 — **2026-05-21 CLI 冒烟通过**
- **3c**：`publish-preflight` 只读预检可 `/运行`；mutating 发布仍须 `/批准运行`（`pytest test_approve_mutating_one_shot`）

**说明**：一致性脚本 **exit 0 当 P0=0**（仅 P1 时进程可能仍 exit 1，runner 会按 stdout/JSON 将 `success=true`、`outcome=passed_with_warnings`）。人物 **存活→死亡** 不再报 P1；仅 **死后复活** 报 `ALIVE_CONFLICT`。
