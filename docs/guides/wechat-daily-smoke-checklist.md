# 微信日常冒烟检查表（个人助手）

> 推送代码或重启 `butler-gateway` 后，用本表在**微信私聊 Bot** 走一遍（约 15–25 分钟）。  
> 完整剧本见 [wechat-core-scenario.md](./wechat-core-scenario.md)。  
> **网关安装/发版/排障**见 [wechat-gateway-ops.md](./wechat-gateway-ops.md)。  
> **验收项目**：WFXM 仓库内 **`灵文1号`**（`projects/LingWen1/`），与仓库外「正式灵文」隔离。

---

## 运维前置（终端）

**人工测试前**（`main` 最新，2026-05-22 `7ea224d` 起建议跑一遍）：

```bash
cd ~/projects/WFXM
git pull --ff-only
bash scripts/install-butler-ops-bundle.sh          # runtime --all-projects + push-drain
bash scripts/install-butler-logrotate.sh user --install-cron   # 可选
bash scripts/butler-gateway-ops.sh restart
bash scripts/butler-gateway-ops.sh reindex         # 或 upgrade（含 pull+重装+reindex）
bash scripts/butler-pre-release-smoke.sh 灵文1号   # 一键守门（约 3–5 分钟）
```

| 检查项 | 结果 |
|--------|------|
| `butler-gateway.service` active | ☑ 2026-05-22 restart |
| `butler-runtime-lingwen.timer` + `butler-push-drain.timer` | ☑ 2026-05-22 ops-bundle |
| logrotate cron 03:00 | ☑ 2026-05-22 `--install-cron` |
| 试点路径 + `~/.butler/wechat/accounts/` | ☑ |
| `.env`：`BUTLER_DEFAULT_PROJECT=灵文1号`、`SYNC_CONVERSATION_MEMORY=0` | ☑ |
| `.env` 记忆：`SEMANTIC_MEMORY=1`、`QUEUE_PREFETCH=1`（推荐） | ☑ |
| `~/.butler/config.yaml` 可选（`setup-butler-config.sh`；本机已合并 gateway/auxiliary） | ☑ 2026-05-22 |
| `butler-pre-release-smoke.sh` 全绿 | ☑ 2026-05-22（1121 pytest + 各 smoke） |
| Owner 画像 SSOT | ☑ |

```bash
# 分项守门（与 pre-release 相同，可单独跑）
bash scripts/butler-gateway-ops.sh preflight
bash scripts/butler-wechat-memory-smoke.sh
bash scripts/butler-wechat-gateway-smoke.sh
bash scripts/butler-inbound-media-smoke.sh
bash scripts/butler-runtime-smoke.sh 灵文1号
# 默认不推微信；真机推送：BUTLER_RUNTIME_SMOKE_PUSH=1 或 butler-wechat-push-verify.sh
```

**可选 live（真 MiniMax，发版前建议跑）**：

```bash
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \
  pytest -m live_llm tests/test_cli_live_smoke.py tests/test_wechat_gateway_live_smoke.py -v
```

**Runtime 推送真机（间隔发送，防限流）**：

```bash
bash scripts/butler-wechat-push-verify.sh 灵文1号
```

微信应收到：`[Butler] 推送验证 1/2` + `factory-status-daily` 摘要。

| live 用例 | 对应真机 |
|-----------|----------|
| `test_live_gateway_one_turn_minimax` | 网关能对话 |
| `test_live_gateway_read_file_no_delegate` | 步骤 3 |
| `test_live_gateway_delegate_writes_file` | 步骤 4–4c |
| `test_live_gateway_owner_profile_nickname` | Owner 画像 |

| 检查项 | 通过 |
|--------|------|
| 网关 `active` | ☑（Agent 2026-05-21） |
| `MINIMAX_API_KEY` 已配置 | ☑（沿用既有） |
| 微信凭证在 `~/.butler/wechat/accounts/` | ☑ |
| 记忆守门 pytest | ☑（15 passed） |

---

## 真机步骤（按顺序复制发送）

**默认项目**：`灵文1号`（`project.yaml` 的 `name`；目录 `projects/LingWen1/`）。  
若 `.env` 已设 `BUTLER_DEFAULT_PROJECT=灵文1号`，步骤 **1–2 可跳过**，以步骤 0 显示当前项目为准。

| # | 发送内容 | 预期（摘要） | 通过 | 备注 |
|---|----------|--------------|------|------|
| 0 | `/状态` | 含莎丽/管家名、当前项目为 `灵文1号`、**环境默认项目**、Provider | ☑ | 2026-05-21 |
| 1 | `/切换 灵文1号` | 已切换到项目: 灵文1号（未设默认项目时必做） | ☑ | 可跳过 |
| 2 | `/状态` | 当前项目为 `灵文1号` | ☑ | 2026-05-21 |
| 3 | `请读取当前项目 README 或 project.yaml 的前 15 行，用纯文字摘要` | 内容与磁盘一致；**不必**委派；约 20–40s 内出现「正在输入」后回复 | ☑ | |
| 4 | `请交给内容代理：在 docs 目录写 wechat-smoke.md，标题「微信验收」，正文写今天日期和一句说明，不要改其他文件` | 明确已委派；回复为**紧凑摘要**（非长文） | ☑ | |
| 4b | `/详细` 或发「详细」（无需斜杠） | 有 headline；变更里可见 wechat-smoke.md | ☑ | |
| 4c | （服务器）`ls projects/LingWen1/docs/wechat-smoke.md` | 文件存在 | ☑ | |
| 5 | `请委派开发代理：只检查 docs/wechat-smoke.md 是否存在并读前几行，不要改代码` | 结论含存在与否 | ☑ | |
| 6 | `/新对话` | 已清空对话历史 | ☑ | |
| 6b | `我们刚才聊过什么？` | **不应**复述步骤 3–5 细节 | ☑ | |
| 7 | `当前是什么项目？灵文1号项目是做什么的？` | 能答「灵文1号」与试点/小说工厂描述（项目记忆） | ☑ | |
| 8 | `/工作流 list` | 列表含 `novel-factory`（可执行） | ☑ | |
| 8b | `/工作流 run novel-factory 写一句个人助手验收说明` | 两步摘要（draft/review）；不刷屏 | ☑ | |
| 8c | `/详细` | 工作流 headline / 各步 OK 或 FAIL | ☑ | |
| P1-1 | `/状态` | 显示 **环境默认项目：灵文1号** | ☑ | |
| P1-2 | `/工作流 run novel-factory-status` | 汇报 workflow phase/step，简短 | ☑ | |
| P1-3 | `请记住：试点验收日期 2026-05-21` → `/记忆待审` → `/批准记忆 全部`（若有待审） | Pending 闭环 | ☑ | |

### 记忆模块验收（P0–P2，2026-05-21 通过）

| # | 发送内容 | 预期（摘要） | 通过 | 备注 |
|---|----------|--------------|------|------|
| M1 | `/诊断`（可无会话） | 记忆分层；**运维快照**；gateway 识图/语音；推送队列（若有） | ☑ | 2026-05-22 13:45；推送队列 2 条已 drain |
| M2 | 「灵文试点统一测试是哪天？」（不说 2026-05-22） | 答 **2026-05-22**（项目 Notes 备忘） | ☐ | 2026-05-22 13:51 答 **2026-05-21**（MEMORY 旧条，已修正见下） |
| M3 | 决策句 → `/记忆待审` → `/拒绝记忆 1` | Pending 减、向量不增正式条 | ☐ | 话术见下方 |
| M4 | 同一问题连发两遍 → `/诊断` | 「上轮预取缓存: 命中」 | ☐ | 间隔 20–90s |
| M1b | `/记忆图谱` | 三元组或空状态提示 | ☐ | |
| O7 | `/诊断` | knowledge.db 键数、混合检索权重、半衰期/访问加权 | ☑ | 含于 M1 |
| Ops | `/开发状态` | 显示 terminal/git/git_write 开关（生产 git_write 宜 0） | ☐ | 可选 |
| RT1 | `/定时` | 列出 jobs；含 consistency-weekly / factory-status | ☐ | |
| RT2 | `/运行 factory-status-daily` | 收到摘要或 audit 路径 | ☑ | M1 时段已收到 factory-status 推送摘要 |

**Owner 画像**：`~/.butler/tenants/default/memory/profile.json`；**勿**在画像写死默认项目名（见 `owner-profile-setup.md`）。

### 阶段 1 · 只读读工厂（冒烟通过后）

| # | 发送内容 | 通过 |
|---|----------|------|
| R1 | `读取 novel-factory/README.md 前 30 行并摘要` | ☑ |
| R2 | `读取 workflow_state.json，说明当前 phase 和 step` | ☑ |
| R3 | `请委派内容代理：只读 docs/reference-snapshot/小说工厂问题记录.md 并给 3 条要点，不要改任何文件` | ☑ |
| R4 | `在 docs/pilot-log.md 写一条：今日日期、微信验收通过、当前 workflow phase 一行摘要；若不存在则创建` | ☑ |

### M3 / M4 真机复现话术（可选核对）

**M3 — 拒绝待审**

1. `我们决定采用某某方案做试点缓存`（决策语气）
2. `/记忆待审` → 应出现 1 条 Pending
3. `/拒绝记忆 1` → 应提示已拒绝；再 `/记忆待审` 为空；`/诊断` 向量条数不应因该条增加

**M4 — 预取缓存**

1. 先发：`灵文试点统一测试是哪天`（等回复结束）
2. **再发同一句**（等回复结束；与第 1 句间隔 **>20 秒且 <90 秒**——缓存 TTL 默认 90s；过久会显示「未命中」但「当前句缓存: 就绪」）
3. `/诊断` → 应含 **「上轮预取缓存: 命中」** 与 **「当前句缓存: 就绪」**（第二轮对话结束后查看）

> 说明：2026-05-21 曾用 300s 正文去重导致「第 2 句无回复」；已改为 `BUTLER_WECHAT_CONTENT_DEDUP_TTL=20`（仅防 iLink 重复推送）。

**批次**：2026-05-20 初验（项目名「灵文」）| **2026-05-21**：灵文1号 冒烟 + P1 + 阶段1 只读 + **记忆 P0–P2（M1–M4）** **全通过**（主公确认 + pytest）

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

## 入站媒体（代码守门 + 可选真机）

```bash
bash scripts/butler-inbound-media-smoke.sh
```

| 步骤 | 发送 | 期望 |
|------|------|------|
| M-img | 发一张项目相关截图 | 管家能描述图中要点（VLM） |
| M-voice | 发一段短语音（<30s） | 能转写并回复内容要点 |

---

## 相关文档

- [wechat-core-scenario.md](./wechat-core-scenario.md) — 八步详解与 FAQ（2026-05-20 真机通过；项目名已更新为灵文1号）  
- [projects/LingWen1/docs/pilot-setup.md](../../projects/LingWen1/docs/pilot-setup.md) — 试点与工作副本说明  
- [owner-profile-setup.md](./owner-profile-setup.md) — Owner 画像  
- [manual-testing-guide.md](./manual-testing-guide.md) — CLI + 微信完整手册
