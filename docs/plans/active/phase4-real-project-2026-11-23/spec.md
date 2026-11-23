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
| 项目自测 | `npm test`：25 / 25 通过 |
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
