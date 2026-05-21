# Owner 画像设置（个人助手）

> 个人助手**不需要**配置多租户；全局偏好写在默认存储即可。  
> 路径：`~/.butler/tenants/default/memory/profile.json`（旧布局会自动迁到此处）。

---

## 文件格式

```json
{
  "entries": [
    "称呼：主公；管家自称莎丽。",
    "渠道：微信回复宜短，少 Markdown，要点分条。",
    "默认项目：日常聊 WFXM 小说工厂试点先发 /切换 灵文1号。",
    "委派：改项目文件、多步开发必须 delegate_task，不要管家自己写大段代码。",
    "时区：Asia/Shanghai；日期用本地今天。"
  ]
}
```

每条为一行自由文本，总字数上限约 **2000**（见 `ProfileStore`）。可增删改 `entries` 数组中的字符串。

---

## 推荐条目（复制后按需删改）

| 主题 | 示例条目 |
|------|----------|
| 称呼 | `称呼：XXX；管家用「莎丽」。` |
| 回复风格 | `微信：每次回复控制在 3–8 行；列表用 1. 2. 3.，避免 ## 标题。` |
| 默认项目 | `未说明项目时，默认当前项目为「灵文1号」（WFXM 试点，非正式灵文）。` |
| 委派习惯 | `只读用管家 read_file；写入/检查文件用 content 或 dev 代理。` |
| 禁忌 | `不要未经确认删除文件；不要跑长时间 shell 除非我明确要求。` |
| 语言 | `一律简体中文。` |

---

## 三种写入方式

### 方式 A：真机对话（推荐）

在微信对莎丽发送类似内容（可多轮）：

```text
请记住：以后微信回复尽量简短，不要超过 8 行。
请记住：叫我主公，涉及改项目文件请委派内容或开发代理。
请记住：我常用项目是灵文1号，讨论 WFXM 小说工厂试点默认 /切换 灵文1号。
```

管家在回合结束后会通过 **post_session / experience** 提取；重要偏好也可由你**直接编辑** `profile.json` 保底。

### 方式 B：直接编辑文件

仓库内可复制模板：[`owner-profile.example.json`](./owner-profile.example.json)

```bash
mkdir -p ~/.butler/tenants/default/memory
cp docs/guides/owner-profile.example.json ~/.butler/tenants/default/memory/profile.json
# 按需改称呼/项目名；保存后无需重启 gateway（下一轮对话会加载）
```

### 方式 C：CLI 一次性写入（可选）

若已配置 Butler CLI 且接有 `butler_remember` 类工具，可对管家说「把 XXX 记入 owner profile」。无工具时以 A/B 为准。

---

## 如何验证画像生效

1. `/新对话` 清空会话（避免上轮对话干扰）  
2. 发送：`用一句话说明你会怎么称呼我、微信回复要多长。`  
3. 预期：与 `profile.json` 中条目一致，而非泛化客套话  

若不符：检查文件路径是否为 `tenants/default/memory/profile.json`，并确认条目无「ignore previous」等误触过滤词。

**自动化（mock LLM）**：`tests/test_owner_profile_gateway.py`  
**可选 live**：`BUTLER_RUN_REAL_API_SMOKE=1 pytest -m live_llm tests/test_wechat_gateway_live_smoke.py::test_live_gateway_owner_profile_nickname`

---

## 与「项目记忆」的区别

| 层级 | 位置 | 记什么 |
|------|------|--------|
| Owner 画像 | `~/.butler/tenants/default/memory/profile.json` | 你是谁、怎么说话、全局习惯 |
| 项目记忆 | `projects/<目录>/.butler/memory/` | 灵文1号试点进度、决策（如 `LingWen1`） |
| 会话 | AgentLoop + `/新对话` 清空 | 仅当前聊天，不长期保留 |

个人助手优先把 **Owner 画像** 写清楚，比再加平台功能更能提升日常体感。

---

## 相关文档

- [wechat-daily-smoke-checklist.md](./wechat-daily-smoke-checklist.md) — 建议画像在冒烟通过后再打磨  
- [design.md](../design/design.md) §五点五 — 租户目录说明（个人可始终用 `default`）
