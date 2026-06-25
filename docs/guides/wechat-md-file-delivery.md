# 微信 · MD/TXT 文件承载长内容

> **替代 HTML 链接方案**：不依赖 HTTPS 公网入口；用微信 **文件消息** 承载完整报告。  
> **已有**：`/导出` 会话 transcript → `.md` 附件（`export_handlers.py`）

---

## 1. 机制（已实现）

Butler 在出站文本末尾追加 **单独一行的绝对路径**（如 `/home/.../.butler/exports/delegate_task_xxx.md`）。  
`WeChatAdapter.send()` 识别该路径后，从 `exports/` 目录取出文件，以 **微信文件** 形式发送（与 `/导出` 相同）。

**安全**：仅允许

- `~/.butler/exports/*.md|*.txt`
- `<项目>/.butler/exports/*.md|*.txt`

默认单条消息最多 **2** 个附件，单文件 ≤ **5MB**（`BUTLER_EXPORT_SEND_WECHAT_MAX_BYTES`）。

---

## 2. 自动附带场景

| 场景 | 微信内摘要 | 附件内容 |
|------|------------|----------|
| 委派完成推送 | `format_for_wechat` 短摘要 | 完整 `format_detail` → `.md` |
| `/详细` | 前 ~500 字 + 提示 | 完整报告 / 子会话 transcript → `.md` |
| `/诊断 详细` | 前 12 行 + 提示 | 完整运维快照 → `.md` |
| Runtime **失败**推送 | `max_summary_chars` 摘要 | stdout/stderr 全文 → `.txt` |
| `/导出` | 导出说明 | 会话 transcript → `.md`（原有） |

**不自动附带**：普通 Lead 回复、成功 runtime 心跳、短于阈值的 `/详细`。

---

## 3. 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_EXPORT_SEND_WECHAT_FILE` | `1` | **总开关**（关则只发文字路径提示） |
| `BUTLER_EXPORT_SEND_WECHAT_MAX_BYTES` | `5242880` | 附件大小上限 |
| `BUTLER_WECHAT_ATTACH_MIN_CHARS` | `400` | 超过此长度才生成附件 |
| `BUTLER_WECHAT_ATTACH_DELEGATE` | `1` | 委派完成推送附带完整报告 |
| `BUTLER_WECHAT_ATTACH_DETAIL` | `1` | `/详细` 附带 |
| `BUTLER_WECHAT_ATTACH_DIAGNOSTIC` | `1` | `/诊断 详细` 附带 |
| `BUTLER_WECHAT_ATTACH_RUNTIME` | `1` | Runtime **失败**时附带日志 |

实现：`butler/gateway/wechat_text_export.py` · 出站解析：`butler/gateway/outbound_files.py`

---

## 4. Owner 使用方式

1. 收到微信 **文字摘要** + **文件气泡**（`.md` / `.txt`）
2. 点开文件 → 系统预览或「用其他应用打开」
3. 需要会话全量历史时，仍可用 **`/导出`** 或 **`/导出 200`**

人工验收（真机）：

```
/切换 灵文1号
（触发一次 dev 委派）
/详细
/诊断 详细
```

期望：摘要在聊天里，完整内容在附件。

---

## 5. 与 HTML 方案对比

| | MD/TXT 附件 | HTML 链接 |
|--|-------------|-----------|
| 公网 HTTPS | **不需要** | 需要 |
| 手机体验 | 文件预览 | 浏览器 |
| 实现复杂度 | **低**（已接入出站链） | 高 |
| 交互 | 只读 | 易膨胀为第二产品界面 |

---

## 6. 相关

- [`opencode-parity.md`](opencode-parity.md) §Transcript 导出  
- [`pilot-project-dev-testing.md`](pilot-project-dev-testing.md)
