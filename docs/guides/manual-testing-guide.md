# Butler v4 人工测试手册

> 版本: v4.1 | 更新日期: 2026-05-20
> 
> 本手册覆盖 CLI 和微信两个交互界面的完整功能测试流程。

---

## 一、测试前准备

### 1.1 环境要求

| 项目 | 要求 |
|------|------|
| Python | 3.10+ |
| 操作系统 | Linux (已验证 Ubuntu 22.04) |
| MiniMax API Key | 已设置 `MINIMAX_API_KEY` 环境变量 |
| 依赖 | `pip install -r requirements.txt` |

### 1.2 验证环境

```bash
# 确认 Python 版本
python --version

# 确认环境变量
echo $MINIMAX_API_KEY | head -c 12

# 确认依赖
cd ~/projects/WFXM
PYTHONPATH=. python -c "from butler.main import main; print('OK')"

# 运行自动化测试（应 733 passed，8 项 live_llm 默认 deselected）
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

**预期：** 新对话不记得之前的内容

**验证点：**
- [ ] 显示 "已清空对话历史"
- [ ] 管家无法回忆 "李四"

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

> v4.1 起：`butler gateway` 默认走 `butler/gateway/runner.py` + iLink 适配器。  
> 仅当需要 Telegram 等平台时使用 `butler gateway --hermes-fallback`。

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

```bash
cd ~/projects/WFXM
set -a && source .env && set +a   # 加载 LLM 等配置

PYTHONPATH=. python <<'PY'
import asyncio
from butler.config import get_butler_home
from butler.gateway.platforms.wechat import qr_login

async def main():
    creds = await qr_login(str(get_butler_home()))
    if not creds:
        raise SystemExit("登录失败或超时")
    print("\n请写入 .env（或仅设 ACCOUNT_ID，token 已从 ~/.butler/wechat/accounts/ 持久化）：")
    print(f"WECHAT_ACCOUNT_ID={creds['account_id']}")
    print(f"WECHAT_TOKEN={creds['token']}")
    print(f"WECHAT_BASE_URL={creds.get('base_url', 'https://ilinkai.weixin.qq.com')}")

asyncio.run(main())
PY
```

扫码成功后可将 `WECHAT_ACCOUNT_ID` / `WECHAT_TOKEN` 写入 `.env`；也可只设 `WECHAT_ACCOUNT_ID`，由适配器从 `~/.butler/wechat/accounts/<id>.json` 读取 token。

### 3.3 启动网关

```bash
cd ~/projects/WFXM
# 加载 .env（若使用 dotenv）
set -a && source .env && set +a

PYTHONPATH=. python -m butler.main gateway --platforms wechat
# 或: butler gateway
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

**预期：** 新对话中无法回忆之前内容

#### 测试 3.5.7：/详细

**操作：** 发送 `/详细` 或 `/detail`

**预期：** 返回上次任务报告或 "暂无"

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

| 编号 | 测试项 | 状态 | 备注 |
|------|-------|------|------|
| 2.1 | 启动交互式对话 | ☐ | |
| 2.2.1 | 简单问候 | ☐ | |
| 2.2.2 | 流式输出 | ☐ | |
| 2.2.3 | 多轮对话上下文 | ☐ | |
| 2.2.4 | 工具调用（读取文件）| ☐ | |
| 2.2.5 | 终端命令执行 | ☐ | |
| 2.3.1 | /help | ☐ | |
| 2.3.2 | /status | ☐ | |
| 2.3.3 | /projects | ☐ | |
| 2.3.4 | /model 查看 | ☐ | |
| 2.3.5 | /model 切换 | ☐ | |
| 2.3.6 | /new 新建对话 | ☐ | |
| 2.3.7 | /detail | ☐ | |
| 2.3.8 | /quit | ☐ | |
| 2.4.1 | 创建项目 | ☐ | |
| 2.4.2 | 列出项目 | ☐ | |
| 2.4.3 | 切换项目 | ☐ | |
| 2.5 | 单次执行 | ☐ | |
| 2.6.1 | 空输入 | ☐ | |
| 2.6.2 | 未知命令 | ☐ | |
| 2.6.3 | Ctrl+C 中断 | ☐ | |
| 2.6.4 | Ctrl+D 退出 | ☐ | |

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
| 3.x 真机抽测 | 建议 | ☐ | 微信再发一轮 `/状态`、`/new`、工具问句作 spot-check |

---

## 七、已知限制

1. **微信网关**：默认 `butler gateway` 为 Butler 原生 iLink（`butler/gateway/platforms/wechat_ilink.py`）；仅 Telegram 等多平台需 `--hermes-fallback`
2. **模型限制**：当前仅配置了 MiniMax 模型，切换到其他厂商需要额外配置 API key
3. **推理模型延迟**：MiniMax-M2.7 是推理模型，首次响应可能较慢（含思考时间）
4. **微信消息长度**：微信单条消息限 2000 字符，超长回复会被截断
5. **工具超时**：terminal 工具默认关闭；设置 `BUTLER_ENABLE_TERMINAL=1` 后，默认 30 秒超时，长时间运行的命令会被终止
6. **delegate_task**：子代理委派功能需要在系统提示中触发，简单问答不会触发

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
