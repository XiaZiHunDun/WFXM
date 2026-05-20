# 微信网关运维手册（systemd）

> 个人助手 Butler：**仅微信**网关，用户级 systemd，日志在仓库 `logs/butler-gateway.log`。  
> 真机验收见 [wechat-daily-smoke-checklist.md](./wechat-daily-smoke-checklist.md)。

---

## 一键命令

```bash
cd ~/projects/WFXM

# 安装/刷新 systemd 单元并重启
bash scripts/install-butler-gateway-service.sh

# 日常运维入口
bash scripts/butler-gateway-ops.sh status      # 状态 + 最近日志
bash scripts/butler-gateway-ops.sh preflight   # 环境检查（不重启）
bash scripts/butler-gateway-ops.sh restart     # 发版后重启
bash scripts/butler-gateway-ops.sh logs        # tail -f 日志
bash scripts/butler-gateway-ops.sh upgrade     # git pull + 重装单元 + 重启
```

---

## 首次部署清单

| 步骤 | 命令 | 说明 |
|------|------|------|
| 1 | `pip install -e ".[wechat]"` | iLink 依赖 |
| 2 | `cp .env.example .env` 并填 `MINIMAX_API_KEY` | 网关 LLM |
| 3 | `butler wechat-setup` | 扫码，凭证 → `~/.butler/wechat/accounts/` |
| 4 | `bash scripts/install-butler-gateway-service.sh` | 安装 user unit |
| 5 | `sudo loginctl enable-linger $USER` | **仅当** preflight 提示 `linger=no` |
| 6 | 微信发 `你好` 或 `/状态` | 真机连通 |

**勿与 Hermes 共用 Bot**：安装脚本会自动 `disable` `hermes-gateway.service`（若存在）。

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

可选 logrotate（复制到 `/etc/logrotate.d/butler-gateway`，路径按本机改）：

```bash
# 见 scripts/logrotate/butler-gateway.conf
```

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
