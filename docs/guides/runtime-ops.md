# 项目 Runtime 运维手册（systemd timer）

> **试点**：灵文1号 · `projects/LingWen1/runtime/jobs.yaml`  
> 设计：[`architecture/project-runtime-automation.md`](../architecture/project-runtime-automation.md)  
> 与网关独立：runtime 在子进程跑脚本，**不阻塞**微信对话。

---

## 一键命令

```bash
cd ~/projects/WFXM

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

---

## 任务说明（灵文试点）

| id | mode | 默认 | 说明 |
|----|------|------|------|
| `factory-status-daily` | readonly | 开 | 08:00 UTC 日报；可 `/运行` |
| `consistency-weekly` | readonly | 开 | 周一 09:00 UTC 一致性脚本（较慢） |
| `publish-preflight` | mutating | **关** | 须 `enabled: true` + `/批准运行` |

---

## 排障

| 现象 | 处理 |
|------|------|
| timer 无输出 | `tail logs/butler-runtime.log`；非 cron 到点会显示「没有到期的任务」 |
| 未收到推送 | 查 `WECHAT_TOKEN`、`BUTLER_OWNER_WECHAT_ID`；`BUTLER_RUNTIME_PUSH=1` |
| 一致性摘要无路径 | `consistency-weekly` 成功后会附 `novel-factory/06_意见仓库/07_一致性检查/*.md`；失败推送含 `审计: …json` |
| `/运行` 改盘被拒 | 正常；用 `/批准运行` 或保持 job 关闭 |
| 任务一直「运行中」 | 删锁：`~/.butler/runtime/locks/<项目>__<job_id>.lock`（或等 2h 过期） |

---

## 真机验收（按需）

- **3a**：`/定时`、`/运行 factory-status-daily` — 已通过（2026-05-21）
- **3b**：等到 08:00/周一 或手动 `butler runtime due` — 暂缓
- **3c**：`/批准运行 publish-preflight` — 暂缓（job 默认 disabled）
