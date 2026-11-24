# Phase 4 — 真实开发能力验证（2026-11-23）

> **状态**：✅ 首个项目已交付并通过浏览器验收
> **目标**：用 Butler / WFXM 通过真实 LLM 从零开发一个实际可用项目，验证
> 「对话 → 写文件 → 审批 → 运行 → 浏览器验收」闭环。

## 1. 项目选择

**Ledger Lite — 本地个人记账 Web 应用**，位于 [`projects/ledger-lite/`](../../../../projects/ledger-lite/)。

选择理由：

- 真实可用：记账、筛选、月度汇总、分类统计、删除、CSV 导出都是日常需求；
- 可验证：金额与汇总有明确数字，浏览器与 API 都能端到端验收；
- 零外部依赖：只用 Node 内置模块，不需要安装依赖或外部服务；
- 适合验证开发闭环：需要多文件协作、参数校验、持久化、前后端联调与测试。

## 2. 开发方式

- Demo 控制台新增真实模式：`BUTLER_V5_DEMO_REAL_LLM=1`，工作区由
  `BUTLER_V5_DEMO_WORKSPACE` 指定（默认 `projects/ledger-lite`）。
- 默认仍为脚本化 LLM + 内存 PGlite；真实模式不影响既有 4 个 Playwright E2E。
- 开发过程全程通过浏览器操作控制台：逐条发送需求，`write_file` / `run_command`
  逐项审批；WFXM 真实模型生成代码并自行运行测试。

启动方式：

```bash
BUTLER_V5_DEMO_REAL_LLM=1 \
BUTLER_V5_DEMO_WORKSPACE=/home/ailearn/projects/WFXM/projects/ledger-lite \
pnpm demo:real
```

## 3. 交付物

| 文件 | 职责 |
|------|------|
| `server.js` | `node:http` 服务：静态文件、交易 CRUD、汇总、CSV 导出 |
| `store.js` | JSON 持久化（临时文件 + fsync + rename 原子写）、过滤、汇总、CSV 转义 |
| `public/index.html` | 记账页面：月份 / 类型 / 分类筛选、汇总卡、表单、列表 |
| `public/style.css` | 响应式布局与配色 |
| `public/app.js` | DOM 渲染、表单提交、删除、筛选、CSV 链接、错误提示 |
| `test/store.test.js` | 存储层单测（过滤、汇总、删除、CSV 转义、非法输入） |
| `test/server.test.js` | HTTP 层单测（201/400/404、列表、汇总、导出） |
| `package.json` | `start` / `test` 脚本，零第三方依赖 |
| `README.md` | 功能、启动、测试、API、数据目录与 CSV 说明 |

## 4. 验收证据

| 项 | 结果 |
|----|------|
| 项目自测 | 首轮 `npm test`：25 / 25 通过；加入奶茶账本后 40 / 40 通过 |
| 浏览器录入 | 3 笔交易 → 收入 5,000.00、支出 88.50、结余 4,911.50 |
| 筛选 | 分类「餐饮」→ 仅 1 行 |
| 删除 | 删除「打车」→ 2 行，支出变为 38.50 |
| CSV | `text/csv; charset=utf-8`，正确下载文件名，含表头与 2 行数据 |
| Demo 回归 | `pnpm test:e2e:demo`：4 passed |
| 工程回归 | `pnpm typecheck` / `pnpm lint` / `pnpm format:check` 全绿 |

## 5. 过程中发现并修复

| 问题 | 处理 |
|------|------|
| Node 22 下 `node --test test/` 把目录当模块，`npm test` 失败 | WFXM 将脚本改为 `node --test test/*.test.js`，复跑 25/25 通过 |
| 3100 端口被本机 Langfuse 占用 | 验收改用 3210（环境冲突，非项目缺陷） |

## 6. 复现命令

```bash
cd projects/ledger-lite
npm test
PORT=3210 LEDGER_DATA_DIR=/tmp/ledger-e2e npm start
# 浏览器打开 http://127.0.0.1:3210/
```

## 7. 后续可选

- CSV 金额统一两位小数；
- 编辑交易、分页、月度图表；
- 多用户与鉴权（当前定位为本地单用户）。

## 8. 开放任务对话验证（2026-11-23）

为贴近手机端真实用法，第二轮不提供文件名、API 或编码指令，只给模糊需求：

> 帮我给 Ledger Lite 加一个「奶茶账本」：我平时正常记账，只要分类或备注里提到奶茶，
> 就自动统计我本月奶茶花了多少钱、喝了几次，还能看最近半年的趋势。最好打开首页就能
> 直接看到，不用多点。你看着实现，完成后告诉我怎么用。

WFXM 自行决定实现方式，结果：

| 层 | 结果 |
|----|------|
| 数据 | `store.milkTeaStats`：识别分类 / 备注含「奶茶」的支出，输出本月杯数、总额、均价、近 6 个月趋势与最近记录 |
| 接口 | `GET /api/milktea?month=YYYY-MM` |
| 首页 | 新增「奶茶账本」区域：本月花费、杯数、均价、6 个月趋势与最近几杯 |
| 测试 | 新增 `test/milk-tea.test.js`，总测试 40 / 40 通过 |

验收证据：

| 项 | 结果 |
|----|------|
| 本月统计 | 2 杯 / 40.00 / 均价 20.00；收入含「奶茶」不计入 |
| 表单联动 | 页面表单新增 15 元奶茶 → 3 杯 / 55.00 / 18.33；删除后恢复 2 杯 / 40.00 |
| 趋势 | 补一笔 2026-10-15 的 20 元奶茶 → 10 月 1 杯 / 20.00、11 月 2 杯 / 40.00、合计 3 杯 / 60.00 |
| 回归 | 原有 25 个测试仍通过；页面筛选、删除正常；控制台无报错 |

过程中发现并修复：首次实现把 `pad2` 声明在 `state` 之后，`state.month` 初始化时触发
暂时性死区，导致首页所有按钮失效。用用户口吻反馈「页面没反应、控制台提到 pad2」后，
WFXM 将 `pad2` 前移并补充注释，页面恢复。

## 9. 多项目 / 模糊需求 / 真实微信入口（2026-11-24）

### 9.1 沙箱 Git 身份

问题：沙箱 `HOME` 指向临时目录，读不到宿主 `~/.gitconfig`，`git commit` 报
`Author identity unknown`。

修复：`resolveSandboxGitIdentityEnv` 在宿主侧解析全局 `user.name` / `user.email`，
仅对 `git` 命令注入 `GIT_AUTHOR_*` / `GIT_COMMITTER_*`，不暴露 git 配置的其他字段。
显式传入的 `GIT_*` 优先。

验证：沙箱内 `git init / add / commit` 成功，作者为 `XiaZiHunDun <cuiyangjs@163.com>`；
新增 4 条单测，typecheck / lint 全绿。

### 9.2 第二项目与模糊需求

第二个独立工作区 `projects/wakeup-cli`，初始需求只有一句：

> 我最近总是起不来，能不能帮我做个小工具，让我能坚持早起？

WFXM 没有直接写代码，而是先追问形态与目标起床时间；补充「命令行、7:00、记录打卡与
连续天数」后，自行实现 `apps/cli/wakeup.mjs` 与 README。

| 项 | 结果 |
|----|------|
| 打卡 | `--at 06:45` 记录成功，连续 1 天 |
| 改时间 | 同日 `--at 08:10` 覆盖为迟到 |
| 查看 | `status` 显示最近记录与连续天数 |
| 隔离 | Ledger Lite 仓库保持干净，未被第二项目改动 |

### 9.3 真实微信入口

通过真实 iLink 微信通道发送：

> 你好，帮我看一下projects目录里有哪些项目，简单列一下

网关记录：

| 项 | 值 |
|----|----|
| runId | `80389008-6edd-4c0c-91d4-50e75b794263` |
| 触发 | `channel` / `wechat` |
| 时间 | 2026-11-24 10:26（Asia/Shanghai） |
| 工具 | `list_dir`，参数 `projects` |
| 结果 | `run.succeeded`，owner 已收到回复 |

### 9.4 遗留

- SSH 重连后浏览器控制台（4521）在本机可访问，但浏览器代理无法连接，wakeup-cli 的
  自动测试未补；不影响本轮「多项目 + 模糊需求」结论。
- 运行中的网关进程仍是修复前的代码，需重启后 Git 身份注入才会在线上生效。


