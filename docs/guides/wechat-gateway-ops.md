# 微信网关运维手册（systemd）

> 个人助手 Butler：**仅微信**网关，用户级 systemd，日志在仓库 `logs/butler-gateway.log`。  
> 真机验收见 [wechat-daily-smoke-checklist.md](./wechat-daily-smoke-checklist.md)（试点项目 **灵文1号** / `projects/LingWen1/`）。  
> OpenCode 对标能力（导出/委派/回滚等）速查：[opencode-parity.md](./opencode-parity.md)。

---

## 一键命令

```bash
cd ~/projects/WFXM

# 安装/刷新 systemd 单元并重启
bash scripts/install-butler-gateway-service.sh

# 日常运维入口
bash scripts/butler-gateway-ops.sh status      # 状态 + 最近日志
bash scripts/butler-gateway-ops.sh preflight   # 环境检查（不重启）
butler doctor                                # 静态安全配置审计（与 preflight Owner warn 对照）
bash scripts/butler-pre-release-smoke.sh     # 发版前 9 步自动化守门
bash scripts/butler-gateway-ops.sh restart     # 发版后重启
bash scripts/butler-gateway-ops.sh logs        # tail -f 日志
bash scripts/butler-gateway-ops.sh upgrade     # git pull + 重装单元 + 重启 + memory-reindex
bash scripts/butler-gateway-ops.sh reindex     # 仅重建记忆向量（默认灵文1号）
bash scripts/install-butler-logrotate.sh       # 网关日志轮转（user 模式，无需 sudo）
```

**`~/.butler/config.yaml`**：可复制 [`docs/config/config.yaml.example`](../config/config.yaml.example) 配置 `gateway` / `auxiliary`（`/model save` 不会覆盖这两段）。

---

## 首次部署清单

| 步骤 | 命令 | 说明 |
|------|------|------|
| 1 | `pip install -e ".[wechat]"` | iLink 依赖 |
| 2 | `cp .env.example .env` 并填 `MINIMAX_API_KEY` + **P0 生产项**（见下） | 网关 LLM 与安全 |
| 3 | `butler wechat-setup` | 扫码，凭证 → `~/.butler/wechat/accounts/` |
| 4 | `bash scripts/install-butler-gateway-service.sh` | 安装 user unit |
| 5 | `sudo loginctl enable-linger $USER` | **仅当** preflight 提示 `linger=no` |
| 6 | 微信发 `你好` 或 `/状态` | 真机连通；`/状态` 当前项目宜为 **灵文1号**（若已设 `BUTLER_DEFAULT_PROJECT`） |

**勿与 Hermes 共用 Bot**：安装脚本会自动 `disable` `hermes-gateway.service`（若存在）。

### P0 生产环境变量（写入 `.env`）

```bash
WECHAT_DM_POLICY=allowlist
WECHAT_ALLOWED_USERS=<你的微信 user id>
BUTLER_OWNER_WECHAT_ID=<同上或 Owner chat_id；runtime 推送、terminal 批准>
# BUTLER_GATEWAY_ALLOWLIST=<可选备用 allowlist，doctor 与 Owner 二选一>
# WFXM 小说工厂试点（与仓库外「正式灵文」隔离；name 须与 project.yaml 一致）
BUTLER_DEFAULT_PROJECT=灵文1号
BUTLER_TOOL_SAFE_ROOT=/home/you/projects/WFXM/projects
MINIMAX_API_KEY=...
```

`bash scripts/butler-gateway-ops.sh preflight` 会对 `open` DM、未设 safe root / 默认项目给出 **warn**。未设 `BUTLER_DEFAULT_PROJECT` 时，新微信会话需先 `/切换 灵文1号` 再读写项目文件。

**Owner 画像**（可选但推荐）：`~/.butler/tenants/default/memory/profile.json` 中默认项目条目宜写 **灵文1号**，模板见 [owner-profile.example.json](./owner-profile.example.json)。修改后无需重启网关，下一轮对话生效。

**记忆（P0 试点）**：

```bash
BUTLER_SYNC_CONVERSATION_MEMORY=0   # 默认：不把每轮聊天写入 experience；用户说「请记住」仍会记该轮
```

管家工具 `butler_remember` / `butler_recall` 已进注册表；写入对照见 [projects/LingWen1/docs/memory-guide.md](../../projects/LingWen1/docs/memory-guide.md)。`/新对话` 结束时会尝试 LLM 提炼并回复「已提炼：…」；`/诊断` 可见 `记忆提炼模型(post_session)`。

**长任务（单人推荐）**：

```bash
BUTLER_GATEWAY_HANDLER_TIMEOUT=600    # 默认已 600s，委派/工作流可再调大
BUTLER_GATEWAY_HANDLER_WORKERS=2      # 长任务进行中仍可处理 /详细 等短命令（不同 worker）
```

**Agent / Gateway 线束（上下文落盘、入站队列、流式预取）** — 默认多数开启，见 [`config/reference.md`](../config/reference.md) 与 [`plans/cc-butler-gap-analysis-2026-05.md`](../plans/cc-butler-gap-analysis-2026-05.md)：

```bash
BUTLER_TOOL_RESULT_SPILL=1
BUTLER_GATEWAY_MESSAGE_QUEUE=1
BUTLER_GATEWAY_QUEUE_PUSH_VIA_BRIDGE=1
BUTLER_STREAMING_TOOLS=1
BUTLER_CACHE_SAFE_DELEGATE=1
```

**长任务完成提醒（出站推送，见 CONTRIBUTING § Gateway 长任务）** — 完整变量见仓库根 `.env.example`：

```bash
BUTLER_GATEWAY_COMPLETION_NOTIFY=1
BUTLER_GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS=90
BUTLER_GATEWAY_DELEGATE_COMPLETION_MODE=last   # 同轮多次委派只推最后一次
BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS=25        # 与 runtime 推送共用间隔
BUTLER_RUNTIME_PUSH_QUEUE=1                    # 限流失败入队，due 时 drain
```

发版后 `/诊断` 应含 **出站策略** 与 **出站推送本轮** 统计。真机抽测见 [wechat-daily-smoke-checklist.md](./wechat-daily-smoke-checklist.md) § 线束与完成提醒。

---

## 后续完善项（登记）

| 项 | 说明 |
|----|------|
| DM pairing | Hermes 式陌生人配对码 + `butler pairing approve`；单人自用已用 allowlist |
| 入站图片/语音 | **已实施** [`wechat-inbound-media.md`](../architecture/wechat-inbound-media.md)（网关层，非 `project.yaml`）；模型分层见 [`layered-model-config.md`](../architecture/layered-model-config.md) |

**个人管家（非多租户）**：全局记忆仅在 `~/.butler/tenants/default/`；无需配置 `project.yaml` 的 `tenant` 字段。

---

## 发版节奏（推荐）

```bash
cd ~/projects/WFXM
git pull
PYTHONPATH=. pytest tests/test_gateway_acceptance.py tests/test_wechat_ilink_*.py -q   # 快守门
# 可选: BUTLER_RUN_REAL_API_SMOKE=1 pytest -m live_llm tests/test_wechat_gateway_live_smoke.py -v
bash scripts/butler-gateway-ops.sh upgrade    # 或 install + restart
bash scripts/butler-gateway-ops.sh status
# 大改时: 微信走 wechat-daily-smoke-checklist 真机 0–8c
```

---

## systemd 单元说明

| 项 | 值 |
|----|-----|
| 单元文件 | `~/.config/systemd/user/butler-gateway.service`（由模板生成） |
| 工作目录 | 仓库根 `WFXM` |
| 环境 | `PYTHONPATH` + `EnvironmentFile=-.env` |
| 进程 | `python3 -m butler.main gateway --platforms wechat` |
| 重启 | `Restart=on-failure`，间隔 30s |
| 停止超时 | 120s（长任务友好） |
| 日志 | `logs/butler-gateway.log`（append，非 journal 主路径） |

常用 systemctl：

```bash
systemctl --user status butler-gateway.service
systemctl --user restart butler-gateway.service
systemctl --user stop butler-gateway.service
journalctl --user -u butler-gateway.service -n 50 --no-pager   # 仅启动/崩溃事件
```

---

## 开机自启（user systemd）

用户服务默认在**登出后停止**。要「重启机器后无人登录也跑网关」：

```bash
loginctl show-user "$USER" -p Linger    # 期望 Linger=yes
sudo loginctl enable-linger "$USER"     # 一次性
systemctl --user enable butler-gateway.service
```

---

## 日志与轮转

- **查看**：`bash scripts/butler-gateway-ops.sh logs` 或 `tail -f logs/butler-gateway.log`
- **正常关键字**：`Butler native gateway running`、`[Wechat] Connected`、`inbound` / `outbound`
- **异常**：`missing token`、`WeChat requires: pip install`、`hermes gateway`

日志轮转：`bash scripts/install-butler-logrotate.sh user --install-cron`。  
运维一键：`bash scripts/install-butler-ops-bundle.sh`（runtime timer 全项目 + push-drain + logrotate）。`upgrade` 会自动刷新 timer 单元。

---

## 故障排查

| 现象 | 处理 |
|------|------|
| `inactive (dead)` | `bash scripts/butler-gateway-ops.sh preflight` → 修 .env/依赖/账号 → `restart` |
| 单元改了未生效 | `systemctl --user daemon-reload && systemctl --user restart butler-gateway` |
| 微信无回复 | `status` + `tail logs`；确认无第二个 gateway 进程；查 API Key |
| 扫码过期 | `butler wechat-setup`，再 `restart` |
| 与 Hermes 抢 Bot | `systemctl --user stop hermes-gateway`；`disable` |
| 登出后网关停 | `sudo loginctl enable-linger $USER` |

---

## 相关文档

- [wechat-daily-smoke-checklist.md](./wechat-daily-smoke-checklist.md) — 发版后真机冒烟  
- [wechat-core-scenario.md](./wechat-core-scenario.md) — 八步剧本详解  
- [manual-testing-guide.md](./manual-testing-guide.md) — CLI + 微信完整手册  
- `scripts/systemd/butler-gateway.service` — 单元模板
