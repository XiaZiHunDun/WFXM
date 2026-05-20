# 微信日常冒烟检查表（个人助手）

> 推送代码或重启 `butler-gateway` 后，用本表在**微信私聊 Bot** 走一遍（约 15–25 分钟）。  
> 完整剧本见 [wechat-core-scenario.md](./wechat-core-scenario.md)。

---

## 运维前置（终端，2 分钟）

```bash
systemctl --user status butler-gateway.service   # 期望 active
systemctl --user is-active butler-gateway.service

# 可选：看最近日志
journalctl --user -u butler-gateway.service -n 30 --no-pager

# 自动化守门（改 gateway/orchestrator 后）
cd ~/projects/WFXM
PYTHONPATH=. pytest \
  tests/test_project_manager.py \
  tests/test_wechat_session_reset.py \
  tests/test_gateway_acceptance.py \
  tests/test_wechat_ilink_inbound.py \
  tests/test_wechat_ilink_outbound.py \
  tests/test_wechat_ilink_media.py \
  tests/test_owner_profile_gateway.py \
  tests/test_workflows.py \
  -q
```

**可选 live（真 MiniMax，耗额度）**：

```bash
BUTLER_RUN_REAL_API_SMOKE=1 MINIMAX_API_KEY=... PYTHONPATH=. \
  pytest -m live_llm tests/test_wechat_gateway_live_smoke.py -v
```

| 检查项 | 通过 |
|--------|------|
| 网关 `active` | ☑ |
| `MINIMAX_API_KEY` 已配置 | ☑ |
| 微信凭证在 `~/.butler/wechat/accounts/`（首次绑定：`butler wechat-setup`） | ☑ |
| pytest 上述三条全绿 | ☑ |

---

## 真机步骤（按顺序复制发送）

**默认项目**：先 `/切换 灵文`（项目名以 `project.yaml` 的 `name` 为准）。

| # | 发送内容 | 预期（摘要） | 通过 | 备注 |
|---|----------|--------------|------|------|
| 0 | `/状态` | 含莎丽/管家名、当前项目、Provider | ☑ | |
| 1 | `/切换 灵文` | 已切换到项目: 灵文 | ☑ | |
| 2 | `/状态` | 当前项目为 `灵文` | ☑ | |
| 3 | `请读取当前项目 README 或 project.yaml 的前 15 行，用纯文字摘要` | 内容与磁盘一致；**不必**委派；约 20–40s 内出现「正在输入」后回复 | ☑ | |
| 4 | `请交给内容代理：在 docs 目录写 wechat-smoke.md，标题「微信验收」，正文写今天日期和一句说明，不要改其他文件` | 明确已委派；回复为**紧凑摘要**（非长文） | ☑ | |
| 4b | `/详细` 或发「详细」（无需斜杠） | 有 headline；变更里可见 wechat-smoke.md | ☑ | |
| 4c | （服务器）`ls projects/LingWen/docs/wechat-smoke.md` | 文件存在 | ☑ | |
| 5 | `请委派开发代理：只检查 docs/wechat-smoke.md 是否存在并读前几行，不要改代码` | 结论含存在与否 | ☑ | |
| 6 | `/新对话` | 已清空对话历史 | ☑ | |
| 6b | `我们刚才聊过什么？` | **不应**复述步骤 3–5 细节 | ☑ | |
| 7 | `当前是什么项目？灵文项目是做什么的？` | 能答项目名与用途（项目记忆） | ☑ | |
| 8 | `/工作流 list` | 列表含 `novel-factory`（可执行） | ☑ | 需先 `/切换 灵文` |
| 8b | `/工作流 run novel-factory 写一句个人助手验收说明` | 两步摘要（draft/review）；不刷屏 | ☑ | |
| 8c | `/详细` | 工作流 headline / 各步 OK 或 FAIL | ☑ | |

**Owner 画像**：已配置 `~/.butler/tenants/default/memory/profile.json`；模板见 `owner-profile.example.json`。

**批次**：2026-05-20 | **验收人**：真机 | **日期**：2026-05-20

---

## 失败时快速定位

| 现象 | 先看 |
|------|------|
| 无回复 / 超时 | `journalctl --user -u butler-gateway -f`；API Key；长任务应见「正在输入」，>30s 可能有一条「仍在处理」 |
| 不委派、自己 read/write | 措辞用「交给内容代理 / 委派开发代理」；`/health` 工具计数 |
| `/新对话` 仍复述上轮 | 是否重启 gateway；`tests/test_wechat_session_reset.py` |
| `/详细` 显示旧报告 | 先完成步骤 4 或 8 再 `/详细` |
| `/工作流` 找不到 | 是否已 `/切换` 到含 `workflows` 的项目 |

---

## 相关文档

- [wechat-core-scenario.md](./wechat-core-scenario.md) — 八步详解与 FAQ（本表步骤 0–8c 已于 2026-05-20 真机通过）  
- [owner-profile-setup.md](./owner-profile-setup.md) — Owner 画像  
- [manual-testing-guide.md](./manual-testing-guide.md) — CLI + 微信完整手册
