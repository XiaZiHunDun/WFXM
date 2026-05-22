# Butler v4 人工测试手册

> 版本: v4.1 | 更新日期: 2026-05-20
> 
> 本手册覆盖 CLI 和微信两个交互界面的完整功能测试流程。

---

## 一、测试前准备

### 1.1 环境要求

| 项目 | 要求 |
|------|------|
| Python | 3.11+（见 `pyproject.toml`） |
| 操作系统 | Linux (已验证 Ubuntu 22.04) |
| MiniMax API Key | 已设置 `MINIMAX_API_KEY` 环境变量 |
| 依赖 | `pip install -e ".[wechat]"`（Python ≥3.11，见 `pyproject.toml`） |

### 1.2 验证环境

```bash
# 确认 Python 版本
python --version

# 确认环境变量
echo $MINIMAX_API_KEY | head -c 12

# 确认依赖
cd ~/projects/WFXM
PYTHONPATH=. python -c "from butler.main import main; print('OK')"

# 运行自动化测试（应 ~1093 passed，live_llm 默认 deselected）
PYTHONPATH=. python -m pytest tests/ -q

# 可选：真实 API smoke（需 .env 中 API Key + BUTLER_RUN_REAL_API_SMOKE=1）
# BUTLER_RUN_REAL_API_SMOKE=1 pytest -m live_llm tests/test_real_api_smoke.py -v
```

### 1.3 可用模型

当前 MiniMax 帐号可使用以下模型：

| 模型名称 | 说明 |
|----------|------|
| MiniMax-M2.7 | 默认模型，推理模型 |
| MiniMax-M2.7-highspeed | 高速版本 |
| MiniMax-M2.5 | 上一代模型 |
| MiniMax-M2.5-highspeed | 上一代高速版本 |
| MiniMax-M2.1 | 较旧版本 |
| MiniMax-M2 | 基础版本 |

---

## 二、CLI 测试

> **定位（2026-05）**：CLI 交互体验已冻结；以 pytest 守门为主，产品验收以 **§三 / [wechat-core-scenario.md](./wechat-core-scenario.md)** 为准。

> **CLI 分级用例（P0/P1/P2）**：见本文 **附录 A**（原 `cli-manual-test-cases.md` 已合并）。下文保留逐步说明。

**自动化回归（映射 §2.2–2.6 主体）：**

```bash
cd ~/projects/WFXM
PYTHONPATH=. python -m pytest \
  tests/test_cli_scenarios.py \
  tests/test_cli_acceptance.py \
  tests/test_main_cli.py \
  tests/test_e2e.py::TestCLIE2E \
  -q
```

**CLI 自动化维度（`test_cli_scenarios.py` + `test_cli_dimensions.py`，约 80+ 用例）：**

| 维度 | 覆盖内容 |
|------|----------|
| 呈现层 | 欢迎面板、Rich Panel 正文、统计行、ERROR/TOOL_LIMIT/中断、备用模型提示 |
| 流式输出 | 默认 **live** 逐行边框盒；`BUTLER_CLI_STREAM_MODE=buffer` 为旧 Panel 模式 |
| 回合边界 | 工具批前 `on_stream_boundary` 关盒 |
| 工具 UX | 工具起止行、预览、失败 hint、inline diff、工具计数统计 |
| 斜杠命令 | `/help` `/status` `/health` `/projects` `/switch` `/model` `/new` `/steer` `/detail` `/quit` 及边界用法 |
| 交互流 | 空输入跳过、未知 `/` 当普通消息、EOF/`/quit` 收尾、切换项目重建 Loop |
| 会话生命周期 | 多轮上下文、`/new` + post-session 异步提炼、记忆 sync 契约 |
| 异常恢复 | API 重试提示、Loop 异常不崩溃 |
| Exec 模式 | 单次 `exec` 与 chat 共用 `finish_turn` |
| 编排契约 | Callbacks 接线、stream/tool/LLM 钩子 |

建议每次改 `butler/cli/*` 或 `butler/main.py` 交互循环后运行：

```bash
PYTHONPATH=. python -m pytest tests/test_cli_scenarios.py tests/test_cli_dimensions.py -q
```

**真实 MiniMax + 完整 CLI（可选，耗 API）：**

```bash
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. pytest -m live_llm tests/test_cli_live_smoke.py -v
```

覆盖：`butler chat` 单轮对话、斜杠命令不额外调 LLM、`/new` 收尾、`butler exec` 单次执行。

### 2.1 启动交互式对话

```bash
cd ~/projects/WFXM
PYTHONPATH=. python -m butler.main chat
```

**预期结果：**
- 显示蓝色边框的欢迎面板
- 面板内容包含：管家名称（莎丽）、当前项目、当前模型
- 出现 `[Butler] > ` 提示符等待输入

**测试截图标记：** `CLI-START-001`

---

### 2.2 基础对话测试

#### 测试 2.2.1：简单问候

**操作：** 输入 `你好`

**预期：**
- 管家以角色身份回复（"莎丽"）
- 显示回复内容（Markdown 格式渲染）
- 底部显示执行统计（tokens 数、耗时）
- `<think>` 推理内容不应出现在回复中

**验证点：**
- [ ] 回复在 30 秒内返回
- [ ] 回复中不包含 `<think>` 标签
- [ ] 底部统计正确显示 tokens 和耗时

#### 测试 2.2.2：流式输出

**操作：** 输入 `请详细介绍一下你自己`

**预期：**
- 文字逐字/逐块流式输出到终端
- 输出完成后显示完整统计

**验证点：**
- [ ] 能看到逐步输出过程（非一次性全部显示）
- [ ] 最终内容完整、可读

#### 测试 2.2.3：多轮对话上下文

**操作：**
1. 输入 `我叫张三`
2. 输入 `我刚才说了什么名字？`

**预期：** 管家能正确回忆 "张三"

**验证点：**
- [ ] 第二轮回复中包含 "张三"

#### 测试 2.2.4：工具调用

**操作：** 输入 `请读取 butler/main.py 文件的前10行`

**预期：**
- 显示工具调用提示（如 "🔧 read_file" 或类似）
- 显示文件内容
- 统计中显示工具调用次数 ≥ 1

**验证点：**
- [ ] 工具调用过程有视觉反馈
- [ ] 返回正确的文件内容
- [ ] 统计显示 "1 工具调用"

#### 测试 2.2.5：终端命令执行

> 默认安全配置下 terminal 工具关闭。若要测试本节，先设置 `BUTLER_ENABLE_TERMINAL=1`，
> 并确保当前项目或 `BUTLER_TOOL_SAFE_ROOT` 指向可执行命令的工作区。启用后仍只允许基础命令 allowlist，
> 不支持 shell 管道、重定向、变量展开或解释器入口。

**操作：** 输入 `执行命令 ls -la butler/`

**预期：**
- 调用 terminal 工具（启用时）
- 返回目录列表结果

**验证点：**
- [ ] 返回 butler/ 目录下的文件列表
- [ ] 统计显示工具调用

---

### 2.3 斜杠命令测试

#### 测试 2.3.1：/help

**操作：** 输入 `/help`

**预期：** 列出所有可用命令

**验证点：**
- [ ] 列出 /projects、/switch、/model、/new、/status、/health、/steer、/detail、/quit

#### 测试 2.3.2：/status

**操作：** 输入 `/status`

**预期：** 显示当前状态信息

**验证点：**
- [ ] 显示管家名称（莎丽）
- [ ] 显示当前项目
- [ ] 显示当前模型（minimax/MiniMax-M2.7）
- [ ] 显示 Butler Home 路径

#### 测试 2.3.2b：/health（或 /诊断）

**操作：** 输入 `/health` 或 `/诊断`

**预期：** 显示运行时诊断面板

**验证点：**
- [ ] 包含压缩 / schema 降级等 Loop 诊断（若有）
- [ ] 包含当前 session 的工具审计摘要（调用次数、错误、guardrail 等）
- [ ] 新会话或无轮次时仍可看到工具审计摘要（非空 session 时）

#### 测试 2.3.3：/projects

**操作：** 输入 `/projects`

**预期：** 列出已有项目（或提示 "暂无项目"）

**验证点：**
- [ ] 正确列出项目或显示无项目提示

#### 测试 2.3.4：/model（查看）

**操作：** 输入 `/model`

**预期：** 列出各角色的模型配置

**验证点：**
- [ ] 显示 butler、dev_agent、content_agent、review_agent 的模型
- [ ] butler 角色显示 minimax/MiniMax-M2.7

#### 测试 2.3.5：/model（切换）

**操作：**
1. 输入 `/model butler minimax/MiniMax-M2.5`
2. 输入 `/status` 确认
3. 输入 `你好`（验证新模型能正常工作）
4. 输入 `/model butler minimax/MiniMax-M2.7`（恢复默认）

**预期：** 模型成功切换并正常工作

**验证点：**
- [ ] 切换提示 "已设置 butler → minimax/MiniMax-M2.5"
- [ ] /status 确认模型已变更
- [ ] 对话正常工作
- [ ] 恢复默认模型成功

#### 测试 2.3.6：/new（新建对话）

**操作：**
1. 输入 `我叫李四`
2. 输入 `/new`
3. 输入 `我之前说过什么名字？`

**预期：**
- 显示「已清空对话历史」，**会话内** messages 清空
- **身份**仍可能由 Butler 记忆层召回（答出「李四」为通过，与微信 §3.5.6 一致）
- 若问「上一轮具体聊了什么细节」，应无法完整复述

**验证点：**
- [ ] 显示 "已清空对话历史"
- [ ] 会话脉络已重置；身份是否保留按产品设计判断

#### 测试 2.3.7：/detail

**操作：** 输入 `/detail`

**预期：** 显示上一次委派任务的详细报告，或提示 "暂无"

**验证点：**
- [ ] 显示报告或 "暂无可展示的详细报告"

#### 测试 2.3.8：/quit

**操作：** 输入 `/quit`

**预期：** CLI 正常退出

**验证点：**
- [ ] 程序正常退出，无报错

---

### 2.4 项目管理测试

#### 测试 2.4.1：创建项目

```bash
PYTHONPATH=. python -m butler.main create test-project --type software --description "测试项目"
```

**预期：** 显示 "Created project test-project at ..."

**验证点：**
- [ ] 返回码为 0
- [ ] 提示创建成功

#### 测试 2.4.2：列出项目

```bash
PYTHONPATH=. python -m butler.main projects
```

**预期：** 列表中出现 test-project

#### 测试 2.4.3：切换项目（CLI 内）

**操作：**
1. 启动 `butler chat`
2. 输入 `/switch test-project`

**预期：**
- 提示 "已切换到项目: test-project"
- 提示符变为 `[test-project] > `

**验证点：**
- [ ] 切换成功
- [ ] 提示符更新

---

### 2.5 单次执行测试

```bash
PYTHONPATH=. python -m butler.main exec "你好，请用一句话自我介绍"
```

**预期：** 输出管家的自我介绍，然后退出

**验证点：**
- [ ] 输出回复内容
- [ ] 程序正常退出

---

### 2.6 异常场景测试

#### 测试 2.6.1：空输入

**操作：** 在 CLI 中直接按回车

**预期：** 不发送消息，重新显示提示符

#### 测试 2.6.2：未知命令

**操作：** 输入 `/unknown`

**预期：** 作为普通消息发送给管家

#### 测试 2.6.3：Ctrl+C 中断

**操作：** 输入一个长问题后立即按 Ctrl+C

**预期：** 显示 "已中断"，可继续新的对话

**验证点：**
- [ ] 不崩溃
- [ ] 可继续正常使用

#### 测试 2.6.4：Ctrl+D 退出

**操作：** 按 Ctrl+D

**预期：** 显示 "再见！" 并正常退出

---

## 三、微信网关测试（Butler 原生，无 Hermes 子进程）

> **P0 业务验收（推荐先做）**：[wechat-core-scenario.md](./wechat-core-scenario.md) — 七步真机剧本（`/状态` → `/切换 灵文1号` → 读写项目 → `delegate_task` → `/新对话` → 项目记忆）。  
> 下文 §3.4–3.5 为分项清单；自动化见 `tests/test_gateway_acceptance.py`。

> v4.1 起：`butler gateway` 默认走 `butler/gateway/runner.py` + iLink 适配器。  
> 产品仅支持微信：`butler gateway`（无需 `--platforms`）。

### 3.1 前置条件

| 项 | 要求 |
|----|------|
| Python 依赖 | `pip install aiohttp cryptography certifi`（微信可选：`pip install -e ".[wechat]"` 含 qrcode）|
| LLM | `.env` 或 `~/.butler/config.yaml` 中至少一个 Provider 可用（如 `MINIMAX_API_KEY`）|
| iLink 凭证 | `WECHAT_TOKEN` + `WECHAT_ACCOUNT_ID`（见 3.2）|
| 网络 | 本机可访问 `https://ilinkai.weixin.qq.com` |

**启动前自检：**

```bash
cd ~/projects/WFXM
PYTHONPATH=. python -c "
from butler.gateway.platforms.wechat import check_wechat_requirements
from butler.config import get_butler_settings
import os
assert check_wechat_requirements(), '缺少 aiohttp/cryptography'
print('butler_home:', get_butler_settings().butler_home)
print('provider:', get_butler_settings().default_provider)
print('WECHAT_TOKEN:', bool(os.getenv('WECHAT_TOKEN') or os.getenv('WEIXIN_TOKEN')))
print('WECHAT_ACCOUNT_ID:', bool(os.getenv('WECHAT_ACCOUNT_ID') or os.getenv('WEIXIN_ACCOUNT_ID')))
"
```

### 3.2 配置 iLink 凭证（Butler 独立，勿拷贝 Hermes）

Butler 凭证目录：`~/.butler/wechat/accounts/`（与 Hermes 的 `~/.hermes/weixin/accounts/` **完全分离**）。

- **不要**把 Hermes 的 json 复制到 Butler：避免混淆，也不应影响你继续用 `hermes gateway`。
- Butler 验收应走 **Butler 自己的扫码**，写入 `~/.butler/`。

**推荐：一条命令扫码（与 Hermes `wechat-setup` 同类）**

```bash
cd ~/projects/WFXM
pip install -e ".[wechat]"    # 首次需要 aiohttp、cryptography、qrcode
set -a && source .env && set +a

butler wechat-setup
# 可选：同时写入项目 .env
butler wechat-setup --write-env
```

终端会显示二维码（或链接）；用微信扫码并在手机里确认。成功后凭证写入 `~/.butler/wechat/accounts/<account_id>.json`，并提示 `WECHAT_*` 环境变量。

也可只设 `WECHAT_ACCOUNT_ID`，由网关从 accounts 目录自动读取 token。

<details>
<summary>备用：Python 直接调用 qr_login</summary>

```bash
PYTHONPATH=. python -c "
import asyncio
from butler.config import get_butler_home
from butler.gateway.platforms.wechat import qr_login
creds = asyncio.run(qr_login(str(get_butler_home())))
print(creds)
"
```

</details>

### 3.3 启动网关

**推荐：systemd 用户服务（重启后自动拉起）**

详见 [`wechat-gateway-ops.md`](./wechat-gateway-ops.md)。

```bash
cd ~/projects/WFXM
bash scripts/install-butler-gateway-service.sh
bash scripts/butler-gateway-ops.sh status
bash scripts/butler-gateway-ops.sh logs      # tail -f logs/butler-gateway.log
```

**前台调试（不用 systemd 时）：**

```bash
cd ~/projects/WFXM
set -a && source .env && set +a
PYTHONPATH=. python -m butler.main gateway --platforms wechat
```

**Hermes 网关勿与 Butler 抢同一 Bot（开发机已 disable）：**

```bash
systemctl --user stop hermes-gateway.service
systemctl --user disable hermes-gateway.service   # 防止登录后自动拉起
pgrep -af hermes_cli || true                      # 应无 gateway 进程
```

**预期日志（节选）：**

- `Butler native gateway running (Wechat)`
- `[Wechat] Connected account=... base=https://ilinkai.weixin.qq.com`
- **不应**出现 `hermes gateway run` 或子进程拉起 Hermes

**另开终端确认：**

```bash
pgrep -af 'butler.main gateway'
```

**验证点：**
- [x] 无 `WeChat requires: pip install...` 报错
- [x] 无 `missing token` / `missing account` 报错
- [x] 日志含 `Butler native gateway running`
- [x] 无 Hermes gateway 子进程（systemd 已 disable）

**自动化回归（映射 §3.4–3.5）：**

```bash
cd ~/projects/WFXM
PYTHONPATH=. python -m pytest tests/test_gateway_acceptance.py tests/test_gateway_handler.py tests/test_gateway_runner.py -q
```

### 3.4 微信对话测试（真机）

#### 测试 3.4.1：基础对话

**操作：** 在微信中发送 `你好`

**预期：** 管家回复问候

**验证点：**
- [x] 收到回复（2026-05-20 真机「你好」）
- [x] 回复中不包含 `<think>` 标签（自动化 + 真机）
- [x] 回复在 30 秒内返回

#### 测试 3.4.2：多轮上下文

**操作：**
1. 发送 `我叫王五`
2. 发送 `我叫什么？`

**预期：** 管家记住 "王五"

#### 测试 3.4.3：工具调用

**操作：** 发送 `请帮我查看 butler/main.py 文件有多少行`

**预期：** 管家调用工具并返回文件行数

**验证点：**
- [ ] 返回正确的行数
- [ ] 回复格式适合微信（纯文本，无 Markdown 渲染符号）

#### 测试 3.4.4：长文本截断

**操作：** 发送一个会产生超长回复的请求，如 `请详细解释 Python 的 asyncio 模块`

**预期：** 回复不超过 2000 字符（微信限制）

---

#### 测试 3.4.5：纯媒体消息

**操作：** 只发一张图片/语音，不带文字

**预期：** 收到提示「收到媒体消息…请用文字说明」（或后续版本支持媒体理解）

#### 测试 3.4.6：/health

**操作：** 发送 `/health` 或 `/诊断`

**预期：** 返回 Butler 诊断（压缩、Skill、工具审计摘要等）

---

### 3.5 微信斜杠命令测试

#### 测试 3.5.1：/状态

**操作：** 发送 `/状态` 或 `/status`

**预期：** 返回管家状态信息

**验证点：**
- [ ] 显示管家名称
- [ ] 显示当前项目
- [ ] 显示默认 Provider

#### 测试 3.5.2：/项目

**操作：** 发送 `/项目` 或 `/projects`

**预期：** 列出项目列表

#### 测试 3.5.3：/模型

**操作：** 发送 `/模型` 或 `/model`

**预期：** 列出各角色模型配置

#### 测试 3.5.4：/模型切换

**操作：**
1. 发送 `/model butler minimax/MiniMax-M2.5`
2. 发送 `/model` 确认
3. 发送 `你好` 测试
4. 发送 `/model butler minimax/MiniMax-M2.7` 恢复

**预期：** 切换成功并正常工作

#### 测试 3.5.5：/切换

**操作：** 发送 `/switch test-project`（如已创建项目）

**预期：** 切换成功

#### 测试 3.5.6：/新对话

**操作：**
1. 发送 `我叫赵六`
2. 发送 `/新对话` 或 `/new`
3. 发送 `我叫什么？`

**预期：**
- 清空**本轮会话**的 AgentLoop 历史（回复「已清空对话历史」）
- 同时清除本会话的 `conversation` 经验条目，问「我们刚才聊过什么」**不应**复述上一轮文件/委派等细节
- **项目记忆**（`MEMORY.md` / 非 conversation 经验）仍可回答「当前是什么项目」
- 若用户只说「我叫赵六」且写入 profile/长期经验，问「我叫什么」仍可能答出——与「刚才聊过什么」不同

#### 测试 3.5.7：/详细

**操作：** 发送 `/详细` 或 `/detail`

**预期：** 返回上次任务报告或 "暂无"

---

### 3.6 核心场景串联（真机 P0）

完整步骤、记录表与排障见 **[wechat-core-scenario.md](./wechat-core-scenario.md)**。

| 步骤 | 微信发送（示例） | 通过标准 |
|------|------------------|----------|
| 1 | `/状态` | 管家名 + 当前项目 + Provider |
| 2 | `/切换 灵文1号` | 已切换到灵文1号（或 `/状态` 已为灵文1号则跳过） |
| 3 | 读 README / project.yaml 摘要 | 内容与 `projects/LingWen1` 一致 |
| 4 | 交给内容代理写 `docs/wechat-smoke.md` | 文件存在；`/详细` 有报告 |
| 5 | 委派开发代理检查该文件 | 结论正确 |
| 6 | `/新对话` → 问刚才聊过什么 | 不记得上轮细节 |
| 7 | 问当前项目与灵文1号用途 | 能答项目名与描述 |

**记录：** 填 §六「微信核心场景」行（见该表新增行）或剧本内记录表。

---

## 四、跨界面一致性测试

### 4.1 命令一致性

| 命令 | CLI 写法 | 微信写法 | 预期行为 |
|------|---------|---------|---------|
| 查看项目 | `/projects` | `/projects` 或 `/项目` | 列出项目 |
| 切换项目 | `/switch <名>` | `/switch <名>` 或 `/切换 <名>` | 切换成功 |
| 查看模型 | `/model` | `/model` 或 `/模型` | 列出模型配置 |
| 切换模型 | `/model <角色> <prov/model>` | 同 CLI | 模型切换 |
| 新建对话 | `/new` | `/new` 或 `/新对话` | 清空历史 |
| 查看状态 | `/status` | `/status` 或 `/状态` | 显示状态 |
| 详细报告 | `/detail` | `/detail` 或 `/详细` | 显示报告 |

### 4.2 核心行为一致性

- [ ] 同一问题在 CLI 和微信中获得语义一致的回复
- [ ] 工具调用在两端都正常工作
- [ ] 模型切换在两端效果一致
- [ ] 新建对话在两端都能正确清空上下文

---

## 五、性能与稳定性测试

### 5.1 响应时间

| 场景 | 可接受时间 | 测试方法 |
|------|-----------|---------|
| 简单问答 | < 15s | 发送 "你好" |
| 工具调用 | < 30s | 发送 "读取某文件" |
| 复杂推理 | < 60s | 发送 "分析一段代码" |

### 5.2 连续对话稳定性

**操作：** 连续进行 10 轮以上的对话

**验证点：**
- [ ] 不会崩溃或卡死
- [ ] 上下文逐渐累积，管家能回忆之前内容
- [ ] Token 消耗统计正常递增
- [ ] 内存使用无明显泄漏

### 5.3 错误恢复

**操作：** 在对话过程中断网 5 秒后恢复

**预期：** 下次请求能正常工作（可能需要重试）

---

## 六、测试结果记录表

### CLI 测试结果

> **验收批次**：2026-05-20 | `test_cli_acceptance` + `test_main_cli` + `TestCLIE2E` **47 passed**

| 编号 | 测试项 | 状态 | 备注 |
|------|-------|------|------|
| 2.1 | 启动交互式对话 | 待人工 | 看欢迎面板与 `[项目] >` 提示符 |
| 2.2.1 | 简单问候 | ☑ | 自动化 |
| 2.2.2 | 流式输出 | 待人工 | 需肉眼看逐字输出 |
| 2.2.3 | 多轮对话上下文 | ☑ | 自动化 |
| 2.2.4 | 工具调用（读取文件）| ☑ | 自动化 read_file |
| 2.2.5 | 终端命令执行 | 跳过 | 默认 `BUTLER_ENABLE_TERMINAL=0` |
| 2.3.1 | /help | ☑ | 含 `/health` |
| 2.3.2 | /status | ☑ | 自动化 |
| 2.3.2b | /health | ☑ | 本次补齐 CLI `/health` |
| 2.3.3 | /projects | ☑ | 自动化 + 真机 `projects` 列出灵文1号 |
| 2.3.4 | /model 查看 | ☑ | 自动化 |
| 2.3.5 | /model 切换 | ☑ | `test_main_cli` |
| 2.3.6 | /new 新建对话 | ☑ | 自动化；身份可经记忆保留 |
| 2.3.7 | /detail | ☑ | 自动化 |
| 2.3.8 | /quit | 待人工 | 与 2.6.4 一并测 |
| 2.4.1 | 创建项目 | ☑ | 自动化 |
| 2.4.2 | 列出项目 | ☑ | 自动化 |
| 2.4.3 | 切换项目 | 待人工 | 看提示符 `[test-project] >` |
| 2.5 | 单次执行 | ☑ | 自动化 mock |
| 2.6.1 | 空输入 | 待人工 | |
| 2.6.2 | 未知命令 | ☑ | `test_main_cli` |
| 2.6.3 | Ctrl+C 中断 | 待人工 | |
| 2.6.4 | Ctrl+D 退出 | ☑ | 自动化 EOF |
| CLI 真机抽测 | 建议 | — | **暂缓**（试点以微信为主；见 §3 自动化） |

### 微信测试结果

> **验收批次**：2026-05-20 | Butler 原生网关 | `tests/test_gateway_acceptance.py` **19 passed** + 真机 3.4.1

| 编号 | 测试项 | 状态 | 备注 |
|------|-------|------|------|
| 3.1–3.3 | 依赖/凭证/启动 | ☑ | Hermes 凭证开发复用；`hermes-gateway` disabled |
| 3.4.1 | 基础对话 | ☑ | 真机「你好」有回复；曾修 `extract_media` 发送 bug |
| 3.4.2 | 多轮上下文 | ☑ | 自动化 mock LLM |
| 3.4.3 | 工具调用 | ☑ | 自动化 `read_file` + 行数回复 |
| 3.4.4 | 长文本截断 | ☑ | 自动化 ≤2000 字 |
| 3.4.5 | 纯媒体消息 | ☑ | 自动化提示文案 |
| 3.4.6 | /health | ☑ | 自动化 |
| 3.5.1 | /状态 | ☑ | 自动化（中英别名） |
| 3.5.2 | /项目 | ☑ | 自动化 |
| 3.5.3 | /模型 | ☑ | 自动化 |
| 3.5.4 | /模型切换 | ☑ | 自动化 |
| 3.5.5 | /切换 | ☑ | 自动化 test-project |
| 3.5.6 | /新对话 | ☑ | 自动化 |
| 3.5.7 | /详细 | ☑ | 自动化 |
| 3.x 真机抽测 | ☑ | `/状态`（莎丽/项目无/minimax）；`/new` 后仍记得身份；`__init__.py` 5 行 |
| 3.6 核心场景（灵文1号八步） | ☑ | 2026-05-22 与 [wechat-daily-smoke-checklist.md](./wechat-daily-smoke-checklist.md) 对齐 |

---

## 七、已知限制

1. **微信网关**：`butler gateway` 为 Butler 原生 iLink（`butler/gateway/platforms/wechat_ilink.py`）；不支持其它平台
2. **模型限制**：当前仅配置了 MiniMax 模型，切换到其他厂商需要额外配置 API key
3. **推理模型延迟**：MiniMax-M2.7 是推理模型，首次响应可能较慢（含思考时间）
4. **微信消息长度**：微信单条消息限 2000 字符，超长回复会被截断
5. **工具超时**：terminal 工具默认关闭；设置 `BUTLER_ENABLE_TERMINAL=1` 后，默认 30 秒超时，长时间运行的命令会被终止
6. **delegate_task**：须用明确委派措辞（见 [wechat-core-scenario.md](./wechat-core-scenario.md) §5.1）；简单只读可不委派

---

## 八、快速故障排查

| 问题 | 可能原因 | 解决方法 |
|------|---------|---------|
| "LLM 调用失败" | API key 无效/过期 | 检查 `echo $MINIMAX_API_KEY` |
| 回复为空 | 模型返回仅含 `<think>` | 检查日志中的 reasoning 内容 |
| Gateway 启动失败 | 缺 aiohttp/cryptography 或 WECHAT_* | `check_wechat_requirements()`；检查 `.env` |
| 工具调用超时 | 命令执行过慢 | 使用更简单的命令测试 |
| 提示符不更新 | 项目切换后未 rebuild | 重启 CLI |
| 微信无回复 | 发送阶段异常或 Hermes 抢线 | `tail logs/butler-gateway.log`；`systemctl --user stop hermes-gateway` |
| 有 inbound 无 outbound | 曾见 `extract_media` UnboundLocalError | 已修；重启 `butler gateway` |

---

## 附录 A：CLI 分级用例清单

> 原 `cli-manual-test-cases.md` 已合并入本文。
## 0. 测试前准备（5 分钟）

| 项 | 检查 |
|----|------|
| 工作目录 | `cd ~/projects/WFXM` |
| API | `MINIMAX_API_KEY` 已设置（或 `.env` 可读） |
| 启动命令 | `PYTHONPATH=. python -m butler.main chat` |
| 记录方式 | 建议开终端录屏或复制输出；用例 ID 填「记录表 §9」 |

**可选：跑自动化打底（不耗对话额度）**

```bash
PYTHONPATH=. pytest tests/test_cli_scenarios.py tests/test_cli_dimensions.py -q
```

**可选：跑真实 API smoke（约 10 秒）**

```bash
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. pytest -m live_llm tests/test_cli_live_smoke.py -v
```

---

## 1. 用例分级

| 级别 | 说明 | 建议 |
|------|------|------|
| **P0** | 每次发版 / 改 CLI 必测；失败即阻塞 | 约 15 分钟 |
| **P1** | 每周或较大功能变更后测 | 约 25 分钟 |
| **P2** | 专项能力 / 边界 / 可选工具 | 按需 |

---

## 2. P0 — 冒烟路径（必测）

> 按顺序执行；全部通过即可认为「CLI 主路径可用」。

### CLI-P0-01 启动与欢迎面板

| 步骤 | 操作 |
|------|------|
| 1 | 执行 `PYTHONPATH=. python -m butler.main chat` |

**预期**

- [ ] 蓝色边框欢迎 Panel（标题含 `Butler v4`）
- [ ] 面板内：管家名（如「莎丽」）、当前项目、`provider/model`
- [ ] 出现输入提示（如 `[Butler] >` 或 `[项目名] >`）
- [ ] 无 `?[36m` 等乱码、无重复欢迎 Panel

**失败特征**: 只有边框无正文、ANSI 乱码、启动 traceback

---

### CLI-P0-02 单轮问候与回复展示

| 步骤 | 操作 |
|------|------|
| 1 | 输入 `你好` 并回车 |

**预期**

- [ ] 约 30 秒内返回
- [ ] 莎丽 Panel：**有正文**（非空框），标题为管家名
- [ ] 同一段回复**不重复**打印两次
- [ ] 可见 tokens / 耗时等统计（多轮或工具时更明显）
- [ ] 正文中**无** `<think>`、`</thinking>` 等标签

**失败特征**: 无输出、双份相同内容、空 Panel、推理标签外露

---

### CLI-P0-03 多轮上下文（会话内记忆）

| 步骤 | 操作 |
|------|------|
| 1 | 输入 `我叫测试员` |
| 2 | 输入 `我叫什么？` |

**预期**

- [ ] 第二轮能答出「测试员」或明确引用刚才的自我介绍
- [ ] 两轮均有正常 Panel 展示

---

### CLI-P0-04 `/new` 清空与无后台报错

| 步骤 | 操作 |
|------|------|
| 1 | 接 P0-03，输入 `/new` |
| 2 | 输入 `我叫什么？` |
| 3 | 观察 `/new` 后终端是否多出错误行 |

**预期**

- [ ] 显示 `已清空对话历史`（或同等提示）
- [ ] **不出现** `Memory extraction failed` / `Skill extraction failed`
- [ ] **不出现** `can't be used in 'await'`
- [ ] `/new` 后仍可正常输入、正常回复
- [ ] 身份是否仍被答出：按产品设计记录（答出「测试员」= 记忆层保留，可接受）

**失败特征**: `/new` 后无法对话、后台提炼报错刷屏

---

### CLI-P0-05 正常退出

| 步骤 | 操作 |
|------|------|
| 1 | 输入 `/quit`（或 Ctrl+D） |

**预期**

- [ ] 正常回到 shell，退出码 0
- [ ] Ctrl+D 时可见「再见」类提示
- [ ] 无 traceback

---

## 3. P1 — 核心能力

### CLI-P1-01 流式长回复

| 步骤 | 输入 `请用 200 字介绍一下你能帮我做什么` |
|------|--------------------------------------|

**预期**

- [ ] 等待时出现 Rich **「思考中…」** 状态（dots）
- [ ] 回复阶段可见 **逐行** 输出（`╭ 莎丽` 边框盒 + `│` 行）
- [ ] 结束后 **不** 再重复整块 Panel 全文（仅统计行）
- [ ] 无乱码（重点看 `?[`、多余 `[36m]`）

> 调试：`BUTLER_CLI_STREAM_MODE=buffer` 可恢复旧「仅结束 Panel」行为。

---

### CLI-P1-02 工具读取文件

| 步骤 | 输入 `请读取 butler/cli/session_ui.py 的前 15 行并概括` |
|------|--------------------------------------------------------|

**预期**

- [ ] 出现工具行（`┊` + 📖 read 等）
- [ ] 统计含「工具调用」
- [ ] 回复内容与文件相关（非胡编）

---

### CLI-P1-03 `/status` 与 `/health`

| 步骤 | 1. `/status`  2. `/health` |
|------|---------------------------|

**预期**

- [ ] `/status`：管家名、项目、模型、Butler Home
- [ ] `/health`：诊断信息；有对话轮次时含 Loop/工具审计相关字段
- [ ] 均**不**触发一轮 LLM 对话（无莎丽回复 Panel）

---

### CLI-P1-04 `/help`、Tab 补全与未知斜杠

| 步骤 | 1. `/help`  2. 输入 `/he` + Tab  3. `/foobar` |
|------|-----------------------------------------------|

**预期**

- [ ] `/help` 列出 projects / switch / model / new / health / quit 等
- [ ] Tab 可补全为 `/help` 等内置命令
- [ ] `/foobar` 提示 **未知命令**，**不**调用 LLM、不消耗 API

---

### CLI-P1-05 空行忽略

| 步骤 | 直接连按两次回车，再输入 `ping` |
|------|--------------------------------|

**预期**

- [ ] 空行不触发回复
- [ ] 仅 `ping` 触发一轮对话

---

### CLI-P1-06 `butler exec` 单次执行

```bash
PYTHONPATH=. python -m butler.main exec "用一句话自我介绍"
```

**预期**

- [ ] 打印一句自我介绍后进程结束
- [ ] 有可见正文，无 thinking 标签
- [ ] 退出码 0

---

### CLI-P1-07 Ctrl+C 中断

| 步骤 | 输入较长问题后立刻 **Ctrl+C** |
|------|------------------------------|

**预期**

- [ ] 显示「已中断」或同等提示
- [ ] 不崩溃，可继续输入下一条
- [ ] 若已有部分流式缓冲，可能显示已缓冲片段（记录实际表现）

---

## 4. P1 — 斜杠命令专项

| ID | 操作 | 预期 | □ |
|----|------|------|---|
| CLI-P1-C01 | `/projects` | 列出项目或「暂无项目」 | |
| CLI-P1-C02 | `/switch <已有项目>` | 「已切换到项目」；提示符项目名变化 | |
| CLI-P1-C03 | `/switch 不存在` | 红色/明确「未找到」；不崩溃 | |
| CLI-P1-C04 | `/model` | 列出 butler / dev_agent / content_agent / review_agent | |
| CLI-P1-C05 | `/model butler minimax/MiniMax-M2.5` → `/status` → `你好` | 切换成功、对话正常 | |
| CLI-P1-C06 | 恢复 `/model butler minimax/MiniMax-M2.7` | 与默认一致 | |
| CLI-P1-C07 | `/steer 接下来优先读 README` | 提示已加入指引；下一轮行为可观察（主观） | |
| CLI-P1-C08 | `/detail` | 有委派报告则展示，否则「暂无」 | |
| CLI-P1-C09 | `/诊断` | 与 `/health` 等效 | |

---

## 5. P1 — 项目与提示符

| ID | 操作 | 预期 | □ |
|----|------|------|---|
| CLI-P1-P01 | `create cli-manual-test --type software -d "人工测试"` | 命令行创建成功 | |
| CLI-P1-P02 | chat 内 `/projects` | 列表含 `cli-manual-test` | |
| CLI-P1-P03 | `/switch cli-manual-test` | 提示符为 `[cli-manual-test] >` | |
| CLI-P1-P04 | 在项目下问「当前项目是什么」 | 回答与项目名一致或合理 | |

---

## 6. P2 — 边界与可选

### CLI-P2-01 `/new` 后「细节」vs「身份」

| 步骤 | 1. 聊具体事实：`项目 WFXM 使用 MiniMax-M2.7`  2. `/new`  3a. `我上一轮具体说了哪个模型？`  3b. `我叫测试员，请记住` → `/new` → `我叫什么` |
|------|--------------------------------------------------------------------------------------------------------------------------------------------------|

**记录**

- [ ] 3a：应**无法**复述上一轮细节（或明确表示不记得）
- [ ] 3b：身份是否保留（与 P0-04 一致，记录实际）

---

### CLI-P2-02 写文件与 diff（可选）

| 步骤 | `在 /tmp 或项目下创建 test-butler-cli.txt，写入 hello，再读取确认` |
|------|------------------------------------------------------------------|

**预期**

- [ ] write / read 工具行可见
- [ ] 若 patch/write，可能看到 inline diff（dim 块）

---

### CLI-P2-03 终端工具（需开启）

```bash
export BUTLER_ENABLE_TERMINAL=1
# 可选: export BUTLER_TOOL_SAFE_ROOT=~/projects/WFXM
```

| 步骤 | `执行 ls butler` |
|------|------------------|

**预期**

- [ ] terminal 工具调用成功或明确 guardrail 拒绝（记录哪一种）

---

### CLI-P2-04 推理显式开启（开发向）

```bash
BUTLER_CLI_SHOW_REASONING=1 PYTHONPATH=. python -m butler.main chat
```

| 步骤 | 输入 `你好` |
|------|-------------|

**预期**

- [ ] 额外出现「推理:」段落；默认关闭时不应出现

---

### CLI-P2-05 长会话后退出（post-session）

| 步骤 | 连续对话 ≥4 轮（可闲聊）→ `/quit` |
|------|-----------------------------------|

**预期**

- [ ] 退出正常
- [ ] 退出前/后无 post-session 相关 ERROR 日志（允许 debug 级静默失败，但不应刷屏）

---

## 7. 推荐执行套餐

**发版前自动化（建议先跑）：**

```bash
PYTHONPATH=. pytest tests/test_cli_stream_live.py tests/test_cli_scenarios.py \
  tests/test_cli_dimensions.py tests/test_cli_slash_commands.py -q
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. pytest -m live_llm tests/test_cli_live_smoke.py -v
```

### 套餐 A — 发版前最小集（≈15 分钟）

`P0-01` → `P0-02` → `P0-03` → `P0-04` → `P0-05` → `P1-06`

### 套餐 B — 完整 CLI 回归（≈45–60 分钟）

套餐 A + 全部 **P1** + 自选 **P2** 中与本次改动相关的项

### 套餐 C — 仅改显示/交互（本次重点）

`P0-01` `P0-02` `P0-04` `P1-01` `P1-04` `P1-07` + 自动化：

```bash
PYTHONPATH=. pytest tests/test_cli_scenarios.py tests/test_cli_dimensions.py -q
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. pytest -m live_llm tests/test_cli_live_smoke.py -v
```

---

## 8. 通过标准

| 级别 | 标准 |
|------|------|
| **通过** | P0 全部勾选；P1 无阻塞缺陷；已知问题已记入记录表 |
| **有条件通过** | P0 通过；P1 有非主路径问题（如 `/steer` 效果弱） |
| **不通过** | 任一 P0 失败：无回复、重复/乱码、/new 报错、无法退出 |

---

## 9. 测试记录表（复制使用）

```
测试人: ____________  日期: ____________  分支/提交: ____________
环境: Ubuntu _____  Python _____  模型: minimax/___________

| 用例 ID     | 结果 P/F | 备注 |
|-------------|----------|------|
| CLI-P0-01   |          |      |
| CLI-P0-02   |          |      |
| CLI-P0-03   |          |      |
| CLI-P0-04   |          |      |
| CLI-P0-05   |          |      |
| CLI-P1-01   |          |      |
| CLI-P1-02   |          |      |
| ...         |          |      |

结论: [ ] 通过  [ ] 有条件通过  [ ] 不通过
```

---

## 10. 与自动化的对应关系

| 人工 ID | 自动化参考 |
|---------|------------|
| P0-02 / P1-01 展示 | `test_cli_scenarios` · `TestFinishTurnDisplayRegression` |
| P0-04 `/new` | `test_cli_scenarios` · `TestScriptedInteractiveChat` |
| P1-04 斜杠 | `test_cli_dimensions` · `TestCliSlashCommandMatrix` |
| P1-06 exec | `test_cli_dimensions` · `TestCliExecMode` |
| 真实 MiniMax | `test_cli_live_smoke.py` |

---

## 11. 常见问题速查

| 现象 | 可能原因 | 建议 |
|------|----------|------|
| 只有 Panel 边框无字 | `finish_turn` 在 `patch_stdout` 内或 buffer 空 | 查 `main.py` 是否在 patch 外调用 `finish_turn` |
| 回复打印两遍 | 流式直写 + Panel 重复 | 查 `StreamRenderer` 是否仅缓冲 |
| `?[36m` 乱码 | Rich markup 未关闭 | 查 `highlight=False`、勿手写 ANSI |
| `/new` 后 await 报错 | post-session LLM 工厂非 async | 查 `auxiliary_llm_call_factory` |
| 流式不逐字 | 设计为结束统一 Panel | 非缺陷，除非要求实时 tty 刷新 |
