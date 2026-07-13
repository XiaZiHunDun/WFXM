# P2 · 架构 + 双挑战 + 关键代码

> **STAR+L**：A（Action）
> **时长**：60 秒（15s 架构 / 30s 双挑战 / 15s 关键代码）
> **核心目标**：让面试官 30 秒内判断"项目有真东西"

---

## 一、Layout 草图

```
┌────────────────────────────────────────────────────┐
│                                                    │
│        [wfxm-architecture.png · 50% 高度]          │
│                                                    │
├─────────────────────────┬──────────────────────────┤
│ 挑战一 · 跨进程工具路由  │ 挑战二 · 多源记忆治理     │
│ [tool-routing 小图]      │ [memory-system 小图]     │
│ 100+ 工具 / 多子代理     │ 3 层（Owner/项目/会话）  │
│ 2 层 15 道门（防御）     │ SSOT=文件 / 索引可重建   │
│ 3 道异常回退             │ 压前抽 fact / 锚点重注入 │
├─────────────────────────┴──────────────────────────┤
│ 关键代码（4 行）                                  │
│ butler/core/agent_loop.py  ← 主循环              │
│ butler/memory/vector_store.py ← 向量检索          │
│ butler/gateway/message_handler.py ← 微信入口      │
│ butler/tools/registry.py ← 工具注册表             │
└────────────────────────────────────────────────────┘
```

---

## 二、画面填充

### 1. 标题（28pt 左上角）

```
架构 + 双挑战 + 关键代码
```

### 2. 上半：架构图（占 50% 高度）

引用：`../png/wfxm-architecture.png`（1920×1080 @ 2x，已生成）

**重点高亮**（用红框或箭头在 PPT 上标注）：
- **Lead / Butler / Plan** 三角色（Multi-Agent）
- **delegate_task** 委派（Plan-then-Execute）
- **Boundary** 框（核心信任域）
- **MCP** 在 Boundary 外（外部能力）

### 3. 左下 · 挑战一：跨进程工具路由

引用：`../png/tool-routing.png`（左下小图，约 30% 宽度）

**关键句（18pt，3 行）**：
```
100+ 工具 / 多子代理
2 层 15 道门（防御）
3 道异常回退
```

### 4. 右下 · 挑战二：多源记忆治理

引用：`../png/memory-system.png`（右下小图，约 30% 宽度）

**关键句（18pt，3 行）**：
```
3 层（Owner / 项目 / 会话）
SSOT=文件 / 索引可重建
压前抽 fact / 锚点重注入
```

### 5. 底部 · 关键代码（4 行，14pt 等宽字体）

```
butler/core/agent_loop.py            ← 主循环
butler/memory/vector_store.py        ← 向量检索
butler/gateway/message_handler.py    ← 微信入口
butler/tools/registry.py             ← 工具注册表
```

---

## 三、口播稿（60 秒，照念即可）

> **【0-15s · 架构总览】**
> "架构是 **Multi-Agent + Plan-then-Execute 混合**——Lead / Butler / Plan 三角色，加上 `delegate_task` 委派给 dev / content / review 子代理。LLM 在信任域内，MCP 在信任域外。"
>
> **【15-45s · 双挑战】**
> "两挑战。
> **第一是跨进程工具路由**——100+ 工具横跨 Owner 对话 / dev 子代理 / 外部 MCP，用 **2 层 15 道门**防御（口播 5 道：permissions / 窄化 / read-before-edit / DELEGATE_BLOCKED / typed schema），3 道回退：llm_fallback / reactive_compact / 微信 outbox。
> **第二是多源记忆治理**——3 层架构（Owner / 项目 / 会话），SSOT 是**文件不是数据库**，压缩前抽 fact 写回 MEMORY，漂移每日报告。"
>
> **【45-60s · 关键代码】**
> "关键代码就 4 个：`agent_loop` 主循环、`vector_store` 向量检索、`message_handler` 微信入口、`registry` 工具注册表——白盒可断点，欢迎细问。"

---

## 四、关键锚点

| 元素 | 字号 / 颜色 | 作用 |
|------|-------------|------|
| **架构图** | 50% 画面高度 | 灵魂可视化，面试官 30 秒判断关键 |
| **2 层 15 道门** | 24pt / 强调 #DC2626 | 双挑战核心数字 |
| **SSOT=文件** | 24pt / 强调 #16A34A | 差异化（vs LangGraph 等框架默认 DB） |
| **4 个文件路径** | 14pt / 等宽字体 | 白盒可断点可信度 |

---

## 五、可能追问预案

| 追问 | 锚点 |
|------|------|
| 2 层 15 道门具体是什么？ | "2 层 = 入站 9 步（鉴权/语义/格式化/...）+ 工具链 6 层；具体口播 5 道核心防线" |
| 为什么 SSOT 用文件不用数据库？ | "文件可 `git diff` 审计，索引可 `reindex` 重建，'无升级风险 + 全栈可控'" |
| delegate_task 怎么防越权？ | "DELEGATE_BLOCKED 名单 + 子代理工具窄化 + typed schema 三道防线" |
| Plan-then-Execute 和 ReAct 的区别？ | "ReAct 单步迭代，Plan-then-Execute 先生成计划再分步执行——长程任务更稳" |
| 为什么不直接用 LangGraph？ | "单租户自托管 + 微信原生 + 极致可控的场景下，框架自带能力是负债" |

---

## 六、对应底层素材

- `../01-wfxm-butler/02-action.md` 全部 6 大技术细节
- `../png/wfxm-architecture.png`（架构图，已生成）
- `../png/tool-routing.png`（工具路由图，已生成）
- `../png/memory-system.png`（记忆系统图，已生成）
- `../talking-points/02-deep-dive-script.md` 3-5 分钟深讲稿（口播扩展版）